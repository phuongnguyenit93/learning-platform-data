# Phone takeover signal

## 1. Tín hiệu chiếm quyền số điện thoại là gì?

Phone takeover signal là thông tin cho thấy quyền nhận SMS hoặc cuộc gọi tại một số điện thoại có thể đã thay đổi, bị can thiệp hoặc không còn gắn với chủ tài khoản như hệ thống từng biết.

Trong khôi phục tài khoản, số điện thoại thường được dùng để nhận mã đặt lại mật khẩu, xác minh yêu cầu thay MFA hoặc liên hệ hỗ trợ. Khi người khác kiểm soát kênh này, họ có thể nhận đúng mã mà hệ thống vừa gửi. Mã OTP vẫn hợp lệ về mặt kỹ thuật, nhưng việc nhận được mã không còn đủ để kết luận người yêu cầu là chủ tài khoản trước đây.

Cần phân biệt ba điều:

- **Sự kiện thay đổi:** có lần cấp lại SIM, chuyển eSIM, chuyển mạng hoặc thay đổi liên quan.
- **Chỉ báo rủi ro:** sự kiện và bối cảnh khiến hệ thống cần thêm kiểm soát.
- **Chiếm quyền đã được xác nhận:** có đủ bằng chứng theo quy trình xử lý sự cố.

Người dùng hợp lệ cũng thay SIM hỏng, đổi máy hoặc chuyển nhà mạng. Vì vậy, một sự kiện đổi SIM không tự chứng minh gian lận; nó cho biết mức độ tin cậy vào kênh điện thoại cần được đánh giá lại.

NIST SP 800-63B-4 coi xác minh ngoài băng qua PSTN là phương thức bị hạn chế và khuyến nghị xem xét các chỉ báo như đổi thiết bị, đổi SIM, chuyển số trước khi dùng kênh đó gửi bí mật xác thực. Hướng dẫn cũng yêu cầu có loại authenticator thay thế phù hợp trong phạm vi áp dụng. [NIST SP 800-63B-4, mục 3.1.3.3](https://pages.nist.gov/800-63-4/sp800-63b.html#pstn)

**Phạm vi minh họa:** trạng thái, khoảng thời gian, cấu trúc dữ liệu và mã Java trong bài là thiết kế học tập. Chúng không phải ngưỡng bắt buộc của nhà mạng, NIST hoặc OWASP.

## 2. Những tình huống có thể làm thay đổi quyền kiểm soát

| Tình huống | Điều có thể thay đổi | Cách nhìn trong phục hồi |
| --- | --- | --- |
| SIM swap hoặc cấp lại SIM | Liên kết số thuê bao với SIM đang hoạt động | Kiểm tra sự kiện gần đây và bối cảnh; chưa kết luận chủ ý |
| Chuyển eSIM sang thiết bị khác | Thiết bị hoặc hồ sơ SIM được dùng cho thuê bao | Cần biết nguồn dữ liệu có quan sát được loại chuyển đổi này không |
| Chuyển mạng giữ số | Nhà mạng phục vụ số điện thoại | Có thể hợp lệ hoặc bị thực hiện trái phép |
| Số điện thoại được thu hồi rồi cấp lại | Người sử dụng số đã thay đổi theo vòng đời thuê bao | Người nhận OTP mới có thể không phải chủ tài khoản cũ |
| Điện thoại bị mất hoặc bị truy cập trái phép | Người có thể đọc tin nhắn và thông báo | Không nhất thiết xuất hiện sự kiện đổi SIM |
| Phần mềm đọc hoặc chuyển tiếp SMS | Nội dung mã có thể tới người khác | API đổi SIM có thể không phát hiện |
| Chuyển tiếp cuộc gọi | Nơi nhận cuộc gọi thoại | Không suy ra SMS cũng bị chuyển tiếp |
| Tài khoản nhà mạng bị chiếm quyền | Khả năng yêu cầu đổi cấu hình hoặc chuyển số | Cần quy trình xử lý tương ứng, không chỉ gửi thêm mã |

SIM swap và chuyển mạng giữ số là những khái niệm khác nhau. Một nguồn dữ liệu có thể quy chúng vào nhóm sự kiện chung; nguồn khác cung cấp riêng. Adapter tích hợp phải giữ đúng ý nghĩa của nhà cung cấp thay vì giả định mọi API đều quan sát cùng một loại thay đổi.

Số điện thoại giống hệt trên cơ sở dữ liệu không bảo đảm người nhận vẫn là cùng một người. Mối quan hệ cần bảo vệ là:

~~~text
tài khoản ứng dụng
    ↔ số điện thoại đã liên kết
    ↔ lịch sử liên kết và xác minh
    ↔ quyền sử dụng số tại thời điểm phục hồi
~~~

## 3. Chuỗi chiếm đoạt qua đường phục hồi

Một kịch bản phòng thủ cần nhận diện có thể diễn ra như sau:

1. Tài khoản ứng dụng đã có số điện thoại phục hồi.
2. Quyền nhận SMS tại số đó chuyển sang người khác.
3. Người này khởi tạo yêu cầu quên mật khẩu hoặc mất MFA.
4. Hệ thống gửi OTP đến số đang lưu.
5. Người nhận mới nhập OTP chính xác.
6. Nếu quy trình chỉ kiểm tra OTP, họ có thể thay credential và giữ quyền truy cập.

Điểm quan trọng nằm ở bước 5: không có lỗi mật mã hoặc lỗi so sánh mã nào xảy ra. Vấn đề là hệ thống đã gán ý nghĩa quá rộng cho bằng chứng “nhận được SMS hiện tại”.

Không dùng OTP qua số điện thoại làm bằng chứng duy nhất cho mọi thao tác thay MFA hoặc passkey. Chính sách của từng thao tác cần quy định bộ bằng chứng và mức bảo đảm phù hợp.

Một SIM bị chuyển không tự tiết lộ khóa riêng của passkey hoặc seed TOTP. Tuy nhiên, nếu dịch vụ cho phép dùng SMS để đặt lại các yếu tố đó, đường fallback có thể làm suy yếu bảo vệ của toàn tài khoản.

OWASP mô tả nguy cơ chiếm số để nhận OTP và khuyến nghị theo dõi thay đổi số hoặc sự kiện thay SIM, đồng thời ưu tiên phương thức ít phụ thuộc vào SMS/thoại. [OWASP Multifactor Authentication Cheat Sheet, SIM Swap and Phone Number Takeover](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#sim-swap-and-phone-number-takeover)

## 4. Thu thập tín hiệu từ nguồn nào?

### 4.1. Nguồn bên ngoài

Nhà mạng hoặc nhà cung cấp tín hiệu có thể cung cấp thời điểm thay đổi SIM, kết quả kiểm tra có thay đổi trong một khoảng nhìn lại hoặc thông tin khác theo hợp đồng.

Không phải số nào, nhà mạng nào hoặc quốc gia nào cũng được hỗ trợ. Cần xác định:

- Loại sự kiện được quan sát, kể cả giới hạn với eSIM và multi-SIM.
- Độ phủ, khoảng lịch sử và độ trễ cập nhật.
- Ý nghĩa của kết quả âm tính, trường null và lỗi.
- Cơ chế xác thực, phạm vi quyền truy vấn và ràng buộc sử dụng dữ liệu.
- Đơn vị thời gian và mốc kết thúc khoảng được kiểm tra.
- Cách xác định đúng thuê bao hoặc số mà kết quả đang nói đến.

Đặc tả CAMARA SIM Swap có thao tác lấy ngày thay SIM và kiểm tra thay đổi trong khoảng quá khứ. Trong bản phát hành được dẫn, một giá trị ngày null có ngữ nghĩa gắn với giới hạn lưu lịch sử; không được tùy tiện diễn giải thành “số này chưa từng đổi SIM”. Adapter phải xét cả khoảng giám sát và ngữ nghĩa của đúng phiên bản tích hợp. [CAMARA SIM Swap, đặc tả r4.3](https://github.com/camaraproject/SimSwap/blob/r4.3/code/API_definitions/sim-swap.yaml)

Kết quả không có sự kiện chỉ có giá trị đối với phạm vi quan sát được xác định. Nó không loại trừ mất điện thoại, phần mềm đọc SMS hoặc các hình thức can thiệp ngoài khả năng của nguồn.

### 4.2. Nguồn nội bộ

Ứng dụng có thể quan sát các sự kiện như:

| Tín hiệu | Giá trị hỗ trợ | Giới hạn |
| --- | --- | --- |
| Số phục hồi vừa được đổi | Cho biết thay đổi liên kết trong ứng dụng | Không cho biết nhà mạng đã đổi SIM |
| Thiết bị mới yêu cầu xóa MFA | Làm tăng mức nhạy cảm của yêu cầu | Người dùng hợp lệ mất máy cũng có thể gặp |
| Nhiều lần xin hoặc nhập OTP sai | Giúp phát hiện lạm dụng | Không chứng minh quyền kiểm soát số đã đổi |
| Người dùng báo mất sóng và mất quyền tài khoản | Căn cứ mở quy trình xác minh sự cố | Báo cáo ban đầu cần được đánh giá |
| Đổi email rồi thay số trong thời gian ngắn | Cho thấy chuỗi thay đổi bảo mật đáng xem xét | Có thể là cập nhật hợp lệ |
| Số lâu không được xác minh lại | Cho biết liên kết lịch sử có thể đã cũ | Không đồng nghĩa số đã được cấp lại |

Không lấy phoneTakeover=false từ request của client làm căn cứ. Trình duyệt và người yêu cầu không phải nguồn tin cậy để xác nhận kênh đang an toàn.

## 5. Mô hình hóa tín hiệu cùng độ đầy đủ của dữ liệu

Một boolean simChanged không đủ thể hiện mọi tình huống. Nên tách **nội dung quan sát** khỏi **chất lượng và phạm vi quan sát**.

~~~text
eventState:
    CHANGE_OBSERVED
    NO_CHANGE_OBSERVED_IN_WINDOW
    UNKNOWN

coverage:
    SUPPORTED_FOR_REQUESTED_SCOPE
    PARTIAL
    UNSUPPORTED

quality:
    FRESH
    STALE
    UNAVAILABLE
    INVALID_RESPONSE
~~~

Các trường hợp cần giữ khác nhau:

| Kết quả | Cách hiểu |
| --- | --- |
| Có thay đổi trong khoảng chính sách quan tâm | Cần áp dụng kiểm soát với kênh điện thoại |
| Không có thay đổi trong khoảng được quan sát đầy đủ | Giảm một phần bất định của loại tín hiệu đó |
| Chỉ quan sát được 24 giờ nhưng chính sách cần 72 giờ | Chưa đủ dữ liệu cho yêu cầu hiện tại |
| Timeout hoặc không có quyền truy vấn | Không biết, không phải kết quả an toàn |
| Phản hồi hết hạn | Cần làm mới hoặc dùng đường thay thế |
| Dữ liệu trả về cho số hoặc phiên liên kết khác | Không được dùng cho hồ sơ này |

Ví dụ snapshot nội bộ đã chuẩn hóa:

~~~json
{
  "signalId": "phone-signal-example",
  "caseRef": "recovery-case-example",
  "phoneBindingRevision": 12,
  "eventState": "CHANGE_OBSERVED",
  "eventAt": "2026-11-23T02:00:00Z",
  "checkedAt": "2026-11-23T03:00:00Z",
  "validUntil": "2026-11-23T03:05:00Z",
  "observationWindowHours": 72,
  "coverage": "SUPPORTED_FOR_REQUESTED_SCOPE",
  "quality": "FRESH",
  "sourceRef": "approved-source-ref",
  "policyVersion": "phone-recovery-policy-v4"
}
~~~

Đây không phải schema API của nhà cung cấp cụ thể. Khoảng 72 giờ và thời hạn năm phút chỉ minh họa hai khái niệm khác nhau:

- Khoảng nhìn lại xác định loại sự kiện quá khứ cần xem.
- Thời hạn snapshot xác định kết quả có thể được tái sử dụng đến lúc nào.

Một kết quả vừa truy vấn có thể nói về dữ liệu nguồn cập nhật chậm. Cần đánh giá cả độ trễ nguồn, không chỉ checkedAt.

### 5.1. Xử lý thời gian không hợp lệ

Thời điểm thay đổi ở tương lai có thể do sai đơn vị, múi giờ hoặc dữ liệu lỗi. Không ép tuổi sự kiện âm về 0 rồi coi đó là sự kiện hợp lệ mà không ghi nhận bất thường.

Dùng định dạng thời gian có múi giờ khi trao đổi và chuẩn hóa về mốc thời gian nhất quán. Chính sách cần nêu rõ biên của cửa sổ: sự kiện đúng tại biên có được tính hay không.

Không dùng đồng hồ của client để tính độ mới của kết quả hoặc thời hạn hồ sơ.

## 6. Chuyển tín hiệu thành quyết định về kênh

Phone takeover signal nên ảnh hưởng trước hết tới việc **có được dựa vào kênh điện thoại cho thao tác này hay không**.

| Tình huống | Hành động minh họa |
| --- | --- |
| Có thay đổi gần đây nhưng chưa có bằng chứng gian lận | Yêu cầu phương thức độc lập; hạn chế dùng điện thoại làm căn cứ quyết định |
| Đã xác nhận số bị chiếm quyền theo quy trình | Ngừng dùng kênh đó cho phục hồi và chuyển xử lý sự cố |
| Nguồn bắt buộc bị timeout hoặc độ phủ không đủ | Thử lại có giới hạn hoặc dùng đường phục hồi không phụ thuộc số |
| Không quan sát thấy thay đổi, dữ liệu phù hợp và còn hạn | Tiếp tục toàn bộ chính sách phục hồi; không tự chấp thuận |
| Người dùng đổi SIM hợp lệ và còn authenticator khác | Dùng authenticator đó theo chính sách để tiếp tục |
| Người dùng mất mọi phương tiện | Chuyển sang quy trình thay thế được phê duyệt nếu có |

“Không dùng kênh điện thoại làm căn cứ quyết định” không nhất thiết đồng nghĩa khóa toàn bộ tài khoản hoặc chặn mọi phiên hiện có. Biện pháp bảo vệ tài khoản phải phù hợp mức bằng chứng và phạm vi sự cố.

Một request reset từ người chưa xác minh không nên đủ để khóa đăng nhập hợp lệ của nạn nhân. Kẻ tấn công có thể cố tình tạo nhiều yêu cầu hoặc báo cáo giả để gây từ chối dịch vụ.

### 6.1. Phương thức bổ sung phải có tính độc lập

Gửi SMS rồi gọi thoại tới cùng số thường vẫn phụ thuộc vào cùng quyền kiểm soát thuê bao. Gửi hai mã SMS khác nhau cũng không tạo thêm một kênh độc lập.

Email dự phòng chỉ hữu ích theo mức bảo đảm của nó. Nếu email đó có thể được đặt lại ngay bằng cùng số điện thoại đang bị nghi ngờ, đường phục hồi vẫn có phụ thuộc vòng.

Những lựa chọn có thể được cân nhắc theo chính sách gồm authenticator đã đăng ký còn khả dụng, recovery code đã cấp trước hoặc quy trình xác minh hỗ trợ. Không tự coi mọi lựa chọn là tương đương; điều kiện cho đặt lại mật khẩu có thể khác điều kiện gỡ MFA.

### 6.2. Thời gian chờ không chứng minh danh tính

Có thể áp dụng giai đoạn chờ cho một số thay đổi nhạy cảm, nhưng hết thời gian chờ không làm cho số đang bị chiếm quyền trở lại an toàn.

Ví dụ, nếu quy tắc chỉ kiểm tra “đổi SIM trong 24 giờ qua”, người kiểm soát trái phép có thể tiếp tục giữ số sau thời điểm đó. Cần xét lịch sử sự cố, trạng thái xử lý và bằng chứng độc lập, thay vì tự cho phép khi sự kiện ra khỏi cửa sổ.

## 7. Ví dụ Java: định tuyến theo tình trạng tín hiệu

Ví dụ dưới đây kiểm tra khả năng sử dụng snapshot và chọn nhánh xử lý. Nó không gọi API nhà mạng, gửi OTP, xác minh danh tính hoặc thay đổi credential. Record yêu cầu Java 16 trở lên.

~~~java
import java.time.Instant;
import java.util.Objects;

public final class PhoneRecoveryPolicy {
    public enum SignalState {
        RECENT_CHANGE,
        NO_CHANGE_IN_REQUIRED_WINDOW,
        UNKNOWN
    }

    public enum Route {
        INCIDENT_REVIEW,
        RECHECK_OR_NON_PHONE_RECOVERY,
        REQUIRE_INDEPENDENT_RECOVERY,
        CONTINUE_FULL_RECOVERY_POLICY
    }

    public record Observation(
            String phoneRef,
            long bindingRevision,
            SignalState state,
            Instant checkedAt,
            Instant validUntil) {
        public Observation {
            Objects.requireNonNull(phoneRef);
            Objects.requireNonNull(state);
            Objects.requireNonNull(checkedAt);
            Objects.requireNonNull(validUntil);
            if (bindingRevision < 0 || !validUntil.isAfter(checkedAt)) {
                throw new IllegalArgumentException("Invalid observation");
            }
        }
    }

    public static Route route(
            Observation observation,
            String expectedPhoneRef,
            long currentBindingRevision,
            boolean confirmedPhoneCompromise,
            Instant now) {
        Objects.requireNonNull(expectedPhoneRef);
        Objects.requireNonNull(now);

        // This flag must refer to the current account and phone binding.
        if (confirmedPhoneCompromise) {
            return Route.INCIDENT_REVIEW;
        }

        if (observation == null
                || !observation.phoneRef().equals(expectedPhoneRef)
                || observation.bindingRevision() != currentBindingRevision
                || observation.checkedAt().isAfter(now)
                || !now.isBefore(observation.validUntil())) {
            return Route.RECHECK_OR_NON_PHONE_RECOVERY;
        }

        return switch (observation.state()) {
            case RECENT_CHANGE -> Route.REQUIRE_INDEPENDENT_RECOVERY;
            case UNKNOWN -> Route.RECHECK_OR_NON_PHONE_RECOVERY;
            case NO_CHANGE_IN_REQUIRED_WINDOW ->
                    Route.CONTINUE_FULL_RECOVERY_POLICY;
        };
    }

    private PhoneRecoveryPolicy() {}
}
~~~

Adapter chỉ được tạo NO_CHANGE_IN_REQUIRED_WINDOW khi nguồn dữ liệu thực sự bao phủ yêu cầu chính sách. Không ánh xạ kết quả không được hỗ trợ, null chưa rõ nghĩa hoặc lỗi xác thực API sang trạng thái này.

confirmedPhoneCompromise phải bắt nguồn từ quy trình có thẩm quyền và được gắn đúng tài khoản, số và phiên liên kết hiện tại. Không nhận trực tiếp boolean đó từ người yêu cầu.

CONTINUE_FULL_RECOVERY_POLICY chỉ có nghĩa tiếp tục các kiểm tra còn lại. Nó không cấp quyền đặt lại mật khẩu, gỡ MFA hoặc phát hành session.

Phiên bản chính sách và phạm vi quan sát cần được ràng buộc trong hệ thống thật. Ví dụ rút gọn không mang đủ metadata để tự xác nhận các điều kiện đó.

## 8. Kiểm tra ở thời điểm nào trong luồng phục hồi?

Không chỉ kiểm tra ở lúc gửi SMS đầu tiên. Một sự kiện đổi SIM có thể xảy ra sau khi khởi tạo hồ sơ nhưng trước khi người nhận nộp mã.

~~~mermaid
sequenceDiagram
    participant U as Người yêu cầu
    participant R as Dịch vụ phục hồi
    participant S as Nguồn tín hiệu điện thoại
    participant P as Bộ chính sách
    U->>R: Khởi tạo yêu cầu phục hồi
    R->>R: Chống lạm dụng và tạo hồ sơ
    R->>S: Tra cứu cho số đã liên kết
    S-->>R: Kết quả cùng phạm vi quan sát
    R->>P: Đánh giá kênh và yêu cầu bằng chứng
    P-->>R: Đường xử lý được phép
    R-->>U: Hướng dẫn phù hợp với quyền xem
    U->>R: Nộp bằng chứng và yêu cầu tiếp tục
    R->>R: Kiểm tra trạng thái và độ mới của dữ liệu
    R->>P: Đánh giá lại khi cần
    P-->>R: Quyết định hiện tại
    R->>R: Thực hiện thao tác nếu đủ mọi điều kiện
~~~

Các điểm kiểm tra quan trọng:

1. Trước khi dựa vào SMS hoặc thoại để cấp bằng chứng phục hồi.
2. Sau thay đổi số điện thoại hoặc thông tin bảo mật có liên quan.
3. Trước khi hoàn tất thay credential, đặc biệt khi hồ sơ kéo dài.
4. Khi có sự kiện hoặc báo cáo sự cố đã được xác minh.

Nếu số trên tài khoản thay đổi trong lúc hồ sơ đang mở, không tự lấy kết quả tra cứu của số cũ áp cho số mới. Dùng revision hoặc cơ chế kiểm soát đồng thời để phát hiện thay đổi.

Token vẫn cần được ràng buộc với đúng tài khoản, hồ sơ, mục đích và phiên liên kết thích hợp. Việc token chỉ dùng một lần không sửa được lỗi gửi token tới kênh đã mất tin cậy.

Khi thay credential, cập nhật trạng thái hồ sơ và tiêu thụ bằng chứng dùng một lần theo cơ chế nhất quán. Chính sách vô hiệu phiên hoặc refresh token phải được thực thi theo loại thay đổi và mức sự cố.

## 9. Tích hợp nguồn tín hiệu mà không tạo điểm yếu mới

### 9.1. Truy vấn từ máy chủ và gắn đúng đối tượng

Số dùng cho tra cứu cần lấy từ liên kết tài khoản trên máy chủ hoặc từ quy trình thay số đã được kiểm soát. Không cho client truyền tùy ý một số khác rồi dùng kết quả của số đó để duyệt hồ sơ.

Chuẩn hóa số theo quy tắc phù hợp, bao gồm mã quốc gia và xử lý đầu vào mơ hồ. Định dạng đúng không chứng minh quyền sở hữu.

Nếu nguồn yêu cầu xác minh quyền truy vấn hoặc sự cho phép của người dùng, thực hiện đúng cơ chế đó. Không biến endpoint phục hồi thành dịch vụ tra cứu lịch sử thuê bao của bất kỳ số nào.

### 9.2. Timeout, retry và circuit breaker

Quy định thời gian chờ, số lần thử lại có giới hạn và cách xử lý khi dịch vụ không sẵn sàng. Retry nên tránh tạo bão truy vấn hoặc tăng chi phí không kiểm soát.

Khi circuit breaker mở, ghi trạng thái nguồn không khả dụng. Không dùng một giá trị mặc định như noSwap=true để giữ luồng SMS chạy bình thường.

Nếu tín hiệu là điều kiện bắt buộc của đường dùng điện thoại, đường đó cần tạm dừng hoặc chuyển sang phương thức khác đã được phép. Không cần làm ngừng mọi hình thức phục hồi độc lập nếu các hình thức đó vẫn đáp ứng chính sách.

### 9.3. Cache phải giữ nguyên ý nghĩa

Một cache key và bản ghi cache cần đủ để phân biệt số, nguồn, phạm vi truy vấn và phiên bản chuẩn hóa liên quan. Khi dùng kết quả cho tài khoản, kiểm tra lại phiên liên kết số và chính sách.

Không tái sử dụng kết quả “không đổi trong 24 giờ” như kết quả “không đổi trong 72 giờ”. Không kéo dài validUntil chỉ vì một request khác vừa đọc cache.

Với nguồn sự kiện bất đồng bộ, xử lý sự kiện trùng, đến muộn và sai thứ tự. Một sự kiện cũ đến sau không được ghi đè trạng thái mới hơn mà không có quy tắc rõ ràng.

Dữ liệu cập nhật theo lô hoặc có độ trễ vẫn để lại khoảng không quan sát. Với thao tác nhạy cảm, cần thiết kế bằng chứng độc lập thay vì giả định API đã loại bỏ mọi nguy cơ.

## 10. Tình huống thực tế và cách diễn giải

### 10.1. Người dùng đổi SIM hỏng rồi quên mật khẩu

Nguồn báo đổi SIM cách đây một giờ; người dùng vẫn có khóa bảo mật đã đăng ký.

Hệ thống không cần quy kết gian lận. Có thể yêu cầu dùng khóa bảo mật theo chính sách và giữ kênh điện thoại ở trạng thái cần kiểm soát bổ sung. Kết quả xác minh authenticator được kiểm tra riêng với tín hiệu điện thoại.

### 10.2. Không có đổi SIM nhưng điện thoại bị mất

Nguồn báo không quan sát thay SIM trong khoảng yêu cầu. Chủ tài khoản báo mất máy; người cầm máy có thể nhìn thấy SMS trên màn hình khóa hoặc truy cập ứng dụng.

Kết quả API không phủ nhận tình huống này. Luồng xử lý phải dựa thêm vào trạng thái mất thiết bị và bằng chứng có thẩm quyền, không tiếp tục coi SMS là phương tiện đáng tin duy nhất.

### 10.3. Nguồn không hỗ trợ nhà mạng hiện tại

Kết quả là UNSUPPORTED, không phải NO_CHANGE_OBSERVED_IN_WINDOW. Hệ thống dùng quy trình thay thế hoặc yêu cầu bổ sung theo chính sách đã định.

Người dùng ở khu vực có độ phủ tín hiệu thấp cần đường phục hồi thực sự khả dụng; không nên bị mắc kẹt trong vòng lặp thử lại cùng một tra cứu không được hỗ trợ.

### 10.4. Số được cấp lại cho người mới

Người mới nhận được mã SMS của tài khoản cũ. Điều đó không chứng minh họ có quyền với tài khoản cũ.

Không tự động hợp nhất tài khoản hoặc chuyển quyền chỉ vì số hiện tại trùng số lịch sử. Việc sửa liên kết số cần quy trình riêng, đồng thời bảo vệ dữ liệu của cả hai người.

### 10.5. Có đổi SIM trước khi gửi mã, không có cảnh báo khác

Hệ thống có thể chỉ hạn chế đường phục hồi dựa vào điện thoại và yêu cầu bằng chứng độc lập. Chưa đủ căn cứ để khóa mọi phiên hợp lệ hoặc tuyên bố tài khoản đã bị đánh cắp.

Phạm vi hành động phải theo mức xác nhận của sự cố, không theo mức độ đáng sợ của tên tín hiệu.

## 11. Thông báo, xử lý sự cố và bảo vệ phiên

Thông báo công khai ở bước nhập email hoặc số không được xác nhận tài khoản tồn tại hay công bố lịch sử thuê bao.

Trong ngữ cảnh phục hồi đã được xác minh phù hợp, có thể dùng thông báo:

> Hiện chưa thể sử dụng phương thức điện thoại để hoàn tất yêu cầu này. Hãy chọn một cách xác minh khả dụng khác hoặc dùng quy trình hỗ trợ khôi phục.

Không hứa “đợi hết 24 giờ là chắc chắn được chấp thuận”. Không công khai chi tiết ngưỡng hoặc nhà cung cấp tín hiệu sau mỗi lần thử.

Khi đã xác nhận bị chiếm số:

- Hạn chế sử dụng kênh điện thoại liên quan cho phục hồi theo phạm vi sự cố.
- Dùng kênh thông báo khác đã được thiết lập và đánh giá phù hợp.
- Rà soát thay đổi mật khẩu, MFA, passkey và session trong khoảng liên quan.
- Thu hồi hoặc hạn chế phiên, refresh token và credential nghi bị ảnh hưởng theo quy trình.
- Khôi phục liên kết số và các phương thức xác thực bằng bằng chứng được chấp nhận.
- Chỉ kết thúc trạng thái sự cố khi điều kiện xử lý đã đạt, không chỉ khi sự kiện đổi SIM đã cũ.

Thông báo gửi tới chính số bị chiếm quyền không phải xác nhận độc lập. Việc xử lý với nhà mạng và việc khôi phục quyền trong ứng dụng là hai quy trình có liên quan nhưng không thay thế nhau.

## 12. Dữ liệu vận hành, quyền riêng tư và các lỗi thường gặp

Bản ghi nên giúp truy xuất quyết định mà không sao chép bí mật:

~~~text
caseRef
accountRef
phoneBindingRevision
signalSourceRef
eventState
coverage
quality
checkedAt
validUntil
policyVersion
decision
reasonCodes
~~~

Không ghi OTP, token đặt lại mật khẩu hoặc toàn bộ phản hồi có dữ liệu cá nhân vào log chung. Số điện thoại và lịch sử thuê bao cần quyền truy cập, mục đích sử dụng và thời hạn lưu rõ ràng.

Nếu dùng định danh giả cho số, một hash thông thường không tự bảo đảm ẩn danh vì không gian số điện thoại có thể bị dò. Chọn cơ chế định danh có khóa hoặc kho ánh xạ được kiểm soát khi phù hợp; vẫn coi dữ liệu liên kết được là nhạy cảm.

Theo dõi độ phủ nguồn, tỷ lệ timeout, độ trễ, tỷ lệ hồ sơ hợp lệ bị chuyển nhánh và sự cố được xác nhận sau phục hồi. Không lấy mọi sự kiện thay SIM làm nhãn gian lận để huấn luyện mô hình.

| Sai lầm | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| OTP đúng đồng nghĩa chủ tài khoản đúng | Người kiểm soát số mới có thể chiếm tài khoản | Đánh giá kênh và yêu cầu bằng chứng đúng thao tác |
| Không có đổi SIM đồng nghĩa không có takeover | Bỏ sót mất máy hoặc đọc trộm SMS | Ghi rõ giới hạn từng tín hiệu |
| Timeout được đổi thành kết quả không đổi | Lỗi hạ tầng làm giảm bảo vệ | Giữ trạng thái UNKNOWN hoặc UNAVAILABLE |
| Đổi SIM luôn là gian lận | Chặn nhầm người dùng hợp lệ | Kết hợp bối cảnh và đường xác minh độc lập |
| SMS cộng cuộc gọi cùng số là hai kênh độc lập | Cùng phụ thuộc quyền kiểm soát thuê bao | Đánh giá phụ thuộc thực tế |
| Hết cửa sổ theo dõi thì tự cho phép | Người chiếm số chỉ cần chờ | Giữ trạng thái sự cố và yêu cầu bằng chứng |
| Tín hiệu số cũ áp cho số mới | Quyết định sai đối tượng | Ràng buộc phiên liên kết và kiểm tra revision |
| Nhiều request nghi ngờ làm khóa toàn tài khoản | Tạo công cụ gây từ chối dịch vụ | Hạn chế đúng request hoặc kênh theo bằng chứng |
| Dùng cùng số để khôi phục cả ứng dụng và email dự phòng | Tạo phụ thuộc vòng | Thiết kế đường phục hồi độc lập |

Phone takeover signal giúp đánh giá độ tin cậy của một kênh tại một thời điểm và trong một phạm vi quan sát. Quyền khôi phục tài khoản vẫn cần bộ bằng chứng phù hợp, trạng thái hiện tại hợp lệ và kiểm soát nhất quán khi thay credential hoặc session.
