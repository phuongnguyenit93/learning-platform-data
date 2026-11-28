# Authentication Assurance Level

## 1. AAL trả lời câu hỏi nào trong IAM?

**Authentication Assurance Level (AAL)** là mức bảo đảm của quá trình xác thực: hệ thống có cơ sở mạnh đến đâu để tin người đang truy cập kiểm soát authenticator đã gắn với tài khoản? Authenticator có thể là mật khẩu, ứng dụng tạo mã hoặc thiết bị giữ khóa mật mã.

Trong hệ thống IAM, đăng nhập thành công mới là điểm bắt đầu của quyết định truy cập. Cùng một tài khoản có thể được dùng để đọc thông tin thông thường, thay đổi cấu hình đăng nhập hoặc cấp quyền quản trị. Hậu quả khi xác thực nhầm ở ba tình huống đó khác nhau; ứng dụng cần diễn đạt được yêu cầu xác thực tương ứng.

Ví dụ, Lan là quản trị viên và đã đăng ký khóa bảo mật. Sáng nay Lan chỉ đăng nhập bằng mật khẩu. Việc tài khoản có khóa bảo mật không chứng minh Lan đã sử dụng nó trong lần đăng nhập này. Nếu API cấp quyền yêu cầu bằng chứng mạnh hơn, API phải kiểm tra ngữ cảnh xác thực thực tế hoặc yêu cầu xác thực bổ sung.

Bài học sử dụng cách phân mức của **NIST SP 800-63B-4**, bản công bố tháng 7/2025. AAL1, AAL2 và AAL3 là các tập yêu cầu, không phải nhãn tùy ý cho tính năng đăng nhập của sản phẩm. [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html).

## 2. Phân biệt AAL với IAL, FAL và quyền truy cập

Một hệ thống danh tính có nhiều loại bằng chứng. Không nên gộp chúng vào một trường chung như `securityLevel=high`.

| Khái niệm | Câu hỏi chính |
| --- | --- |
| IAL — Identity Assurance Level | Quá trình kiểm chứng danh tính ngoài đời đáng tin cậy đến đâu? |
| AAL — Authentication Assurance Level | Quá trình xác thực chứng minh quyền kiểm soát authenticator đến đâu? |
| FAL — Federation Assurance Level | Luồng liên kết danh tính bảo vệ assertion và việc sử dụng assertion như thế nào? |
| Authorization | Chủ thể được thực hiện hành động nào trên tài nguyên nào? |

NIST tách các quá trình kiểm chứng danh tính, xác thực và federation thành những phần riêng trong mô hình danh tính số. [NIST — Digital Identity Model](https://pages.nist.gov/800-63-4/sp800-63/model/).

Trong ví dụ của Lan, hồ sơ nhân sự, lần đăng nhập bằng khóa bảo mật và role quản trị là ba nguồn thông tin khác nhau. API cấp quyền cần đánh giá từng nguồn đúng mục đích. Một người xác thực rất mạnh vẫn có thể không được phép cấp role; một người được cấp role vẫn có thể cần xác thực lại trước khi sử dụng quyền đó.

## 3. Ba mức AAL của NIST

| Mức | Đặc điểm cốt lõi |
| --- | --- |
| AAL1 | Cho phép xác thực bằng một yếu tố; cũng có thể sử dụng nhiều yếu tố. |
| AAL2 | Yêu cầu hai loại yếu tố; verifier phải cung cấp ít nhất một lựa chọn chống phishing. |
| AAL3 | Yêu cầu chống phishing, khóa riêng không xuất được và xác thực mật mã khóa công khai. |

Authenticator có khả năng đồng bộ khóa không đáp ứng yêu cầu khóa không xuất được của AAL3. Ngoài phương thức đăng nhập, việc đáp ứng AAL còn phụ thuộc các yêu cầu về verifier, mật mã và quản lý xác thực. Bảng trên chỉ nêu những điểm phân biệt, không thay thế toàn bộ tiêu chuẩn. [NIST — Authentication Assurance Levels](https://pages.nist.gov/800-63-4/sp800-63b/aal/).

Vì vậy, các câu như “đã bật MFA nên đạt AAL2” hoặc “dùng khóa USB nên đạt AAL3” cần thêm bằng chứng. Nhóm triển khai phải chỉ ra phương thức nào được phép, máy chủ kiểm tra điều gì, khóa được bảo vệ ra sao và đường khôi phục có ảnh hưởng thế nào đến quá trình sử dụng tài khoản.

Khi một tổ chức công bố đáp ứng một mức, cần ghi rõ phiên bản tiêu chuẩn và phạm vi đánh giá. Bài học này trình bày nền tảng thiết kế; một ví dụ cấu hình hoặc đoạn code không phải chứng nhận phù hợp tiêu chuẩn cho hệ thống.

## 4. Đếm loại yếu tố, không đếm số màn hình

Các loại yếu tố thường gặp gồm thông tin người dùng biết, vật hoặc bí mật người dùng giữ, và đặc điểm sinh trắc học. Hai lần nhập bí mật không tự tạo thành hai loại yếu tố độc lập.

Mật khẩu và một PIN khác đều có thể là yếu tố kiến thức. Ngược lại, PIN dùng để kích hoạt thiết bị giữ khóa có vai trò khác với mật khẩu gửi đến máy chủ: quá trình xác thực có thể kết hợp quyền sở hữu khóa và yếu tố kích hoạt cục bộ. Sinh trắc học không được NIST xem là authenticator độc lập. [NIST — Authenticator and Verifier Requirements](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/).

Hãy xét ba giao diện minh họa:

- Giao diện A yêu cầu mật khẩu rồi hỏi thêm “tên thú cưng”. Có hai màn hình nhưng vẫn dựa vào bí mật người dùng biết.
- Giao diện B yêu cầu mật khẩu và mã từ ứng dụng giữ bí mật tạo OTP. Nhóm thiết kế cần đánh giá cả quá trình đăng ký, bảo vệ và kiểm tra OTP.
- Giao diện C chỉ có một thao tác xác nhận trên thiết bị. Bên trong thao tác đó có thể là mở khóa authenticator bằng PIN rồi ký challenge bằng khóa riêng.

Số thao tác nhìn thấy không đủ để so sánh mức bảo đảm. Tài liệu thiết kế nên mô tả bằng chứng mà verifier nhận được và điều kiện để tạo ra bằng chứng đó.

## 5. Phishing resistance và passkey

### 5.1. Mã dùng một lần không giải quyết mọi hình thức giả mạo

Giả sử một trang giả yêu cầu Lan nhập mật khẩu và mã OTP hiện tại. Kẻ tấn công chuyển ngay cả hai sang trang thật. Mã có thể chưa từng được dùng trước đó nhưng vẫn bị sử dụng cho phiên của kẻ tấn công.

Ví dụ này cho thấy hai câu hỏi khác nhau: bằng chứng cũ có dùng lại được không, và bằng chứng đang tạo có bị chuyển sang bên giả mạo không? Khi đánh giá phương thức, cần kiểm tra đúng dạng tấn công mà chính sách muốn ngăn chặn.

Với thao tác cấp quyền quản trị, nhóm sản phẩm có thể chọn yêu cầu chống phishing ngay cả khi chính sách cơ bản cho các thao tác khác chấp nhận những phương thức khác. Đây là lựa chọn của hệ thống trong ví dụ, không phải bảng ánh xạ bắt buộc cho mọi ứng dụng.

### 5.2. Tên “passkey” chưa mô tả đủ thuộc tính

WebAuthn sử dụng credential khóa công khai gắn với RP. Khi chính sách yêu cầu user verification, máy chủ cần kiểm tra cờ `UV` trong kết quả đã xác minh; không chỉ tin rằng giao diện đã hiển thị yêu cầu xác nhận. Các cờ backup eligibility và backup state cung cấp những thông tin riêng về credential. [W3C — WebAuthn, Verifying an Authentication Assertion](https://www.w3.org/TR/webauthn-3/#sctn-verifying-assertion).

Trong đánh giá triển khai, hãy đặt các câu hỏi cụ thể:

- Credential có thể được sao lưu hoặc đồng bộ sang thiết bị khác không?
- Khóa được tạo và sử dụng trong môi trường nào?
- Verifier xác minh những thuộc tính nào, từ nguồn bằng chứng nào?
- Luồng thực tế có yêu cầu yếu tố kích hoạt phù hợp không?
- Những yêu cầu còn lại của mức muốn công bố đã được đáp ứng chưa?

Không suy ra toàn bộ thuộc tính từ hình dáng thiết bị. Tương tự, một cờ báo credential không đủ để chứng minh mọi yêu cầu về bảo vệ khóa hay kiểm định mật mã.

## 6. Tách mức yêu cầu, khả năng tài khoản và mức đã đạt

Ba giá trị sau có thể khác nhau:

| Giá trị | Ý nghĩa trong ví dụ của Lan |
| --- | --- |
| `requiredAssurance` | API cấp role yêu cầu ngữ cảnh xác thực theo chính sách của API. |
| `supportedAssurance` | Những quá trình xác thực tài khoản Lan có khả năng hoàn thành. |
| `achievedAssurance` | Mức được xác nhận từ lần xác thực đã diễn ra. |

`supportedAssurance` giúp chọn phương thức khi cần xác thực bổ sung. Nó không được dùng để thay cho `achievedAssurance` trong quyết định cho phép thao tác.

Một lỗi dễ gặp là lưu `mfaEnabled=true` vào tài khoản rồi coi mọi phiên đều đã dùng MFA. Giá trị đó chỉ mô tả cấu hình. Hệ thống còn cần bằng chứng về lần xác thực cụ thể: tài khoản nào, phương thức nào, thời điểm nào và nguồn xác nhận nào.

Một lỗi khác là tin nhãn do trình duyệt gửi, chẳng hạn `X-AAL: 3`. Người gọi có thể tự đặt header này. Nếu kiến trúc dùng gateway truyền ngữ cảnh, backend phải có cách phân biệt dữ liệu gateway đã xác thực với dữ liệu người gọi tự cung cấp, đồng thời ngăn đường truy cập bỏ qua gateway.

## 7. Chuyển nhu cầu nghiệp vụ thành chính sách

Trước khi chọn phương thức, xác định hậu quả khi kẻ khác truy cập nhầm tài khoản. NIST đặt việc lựa chọn assurance trong quá trình đánh giá rủi ro danh tính, bao gồm tác động đến người dùng và tổ chức. [NIST — Digital Identity Risk Management](https://pages.nist.gov/800-63-4/sp800-63/dirm/).

Một nhóm phát triển có thể xây dựng chính sách minh họa như sau:

| Thao tác | Yêu cầu minh họa của ứng dụng | Điều kiện cần đánh giá thêm |
| --- | --- | --- |
| Xem tùy chọn giao diện | Đăng nhập theo chính sách cơ bản | Tài khoản còn hoạt động. |
| Đổi phương thức đăng nhập | Xác thực bổ sung phù hợp | Phiên có dấu hiệu bị chiếm dụng không? |
| Gán role quản trị | Xác thực chống phishing mới thực hiện | Người cấp có quyền trên đúng tenant không? |
| Dùng tài khoản đặc quyền khẩn cấp | Chính sách riêng cho tình huống khẩn cấp | Phê duyệt, giới hạn thời gian và bằng chứng kiểm toán. |

Các dòng trên là bài tập thiết kế, không phải quy định AAL theo tên chức năng. Chẳng hạn, “xem báo cáo” có thể ít rủi ro ở hệ thống này nhưng làm lộ thông tin quan trọng ở hệ thống khác.

Chính sách tốt cũng mô tả trường hợp người dùng không có phương thức đáp ứng yêu cầu. Ứng dụng cần trả về hướng xử lý rõ ràng, chẳng hạn đăng ký authenticator phù hợp qua quy trình được kiểm soát, thay vì âm thầm giảm yêu cầu để thao tác tiếp tục.

## 8. Step-up: yêu cầu bằng chứng bổ sung trước thao tác

**Step-up authentication** là cách yêu cầu người dùng hoàn thành quá trình xác thực bổ sung khi ngữ cảnh hiện tại chưa đáp ứng chính sách.

Luồng minh họa cho thao tác gán role:

1. Backend nhận yêu cầu và kiểm tra người gọi có quyền gán role trong tenant đích.
2. Backend xác định yêu cầu assurance và độ mới cho thao tác.
3. Nếu ngữ cảnh chưa đủ, backend chưa thực hiện thay đổi và khởi tạo luồng step-up.
4. Người dùng hoàn thành phương thức phù hợp qua dịch vụ xác thực.
5. Backend xác minh kết quả, liên kết với đúng tài khoản và phiên đang thao tác.
6. Backend kiểm tra lại quyền và điều kiện nghiệp vụ trước khi thực hiện thay đổi.

Việc kiểm tra lại ở bước cuối tránh sử dụng một quyết định cũ sau khi trạng thái đã thay đổi. Ví dụ, trong lúc Lan xác thực bổ sung, một quản trị viên khác có thể đã thu hồi quyền cấp role của Lan.

Với thao tác nhạy cảm, nhóm thiết kế còn cần xác định bằng chứng step-up được dùng cho thao tác nào và có thể dùng trong bao lâu. Một lần xác thực bổ sung không nên trở thành lý do bỏ qua mọi kiểm tra của các thao tác sau đó.

### Ví dụ logic kiểm tra trong Java

Đoạn code sau chỉ minh họa một phần quyết định ở ứng dụng. Đầu vào `VerifiedContext` được giả định đã được thành phần tin cậy tạo sau khi xác minh xác thực; code không tự đánh giá một phương thức có đáp ứng NIST hay không.

```java
import java.time.Duration;
import java.time.Instant;

enum Assurance {
    UNKNOWN(0), AAL1(1), AAL2(2), AAL3(3);

    private final int rank;

    Assurance(int rank) {
        this.rank = rank;
    }

    boolean meets(Assurance required) {
        return this != UNKNOWN && rank >= required.rank;
    }
}

record VerifiedContext(
        String subject,
        Assurance achieved,
        boolean phishingResistant,
        Instant authenticatedAt) {}

record Requirement(
        Assurance minimum,
        boolean phishingResistanceRequired,
        Duration maximumAge) {}

final class AssuranceGate {
    static boolean needsStepUp(
            VerifiedContext context,
            Requirement requirement,
            Instant now) {
        if (context == null || context.achieved() == null
                || context.authenticatedAt() == null) {
            return true;
        }

        Duration age = Duration.between(context.authenticatedAt(), now);
        if (age.isNegative() || age.compareTo(requirement.maximumAge()) > 0) {
            return true;
        }

        if (!context.achieved().meets(requirement.minimum())) {
            return true;
        }

        return requirement.phishingResistanceRequired()
                && !context.phishingResistant();
    }
}
```

Ví dụ ứng dụng có thể đặt yêu cầu cho thao tác gán role là tối thiểu AAL2, có chống phishing và thời gian xác thực không quá năm phút. **Năm phút là giả định nghiệp vụ của ví dụ**, không phải thời hạn NIST chung cho AAL2.

Ở đây cờ chống phishing cho phép ứng dụng diễn đạt điều kiện bổ sung rõ ràng. Trong triển khai thật, thành phần tạo context cần bảo đảm các thuộc tính nhất quán; không tạo một context tự nhận AAL3 trong khi báo không chống phishing. Cấu hình `Requirement` phải được kiểm tra hợp lệ. Quyền truy cập, tenant, trạng thái phiên, tài khoản bị khóa và thu hồi authenticator vẫn do các kiểm tra khác xử lý.

## 9. Truyền assurance qua SSO và OpenID Connect

Trong OIDC, `acr` mô tả lớp ngữ cảnh xác thực, `amr` mô tả phương thức, còn `auth_time` là thời điểm xác thực người dùng. Ý nghĩa giá trị `acr` cần được các bên thống nhất. Tham số `acr_values` biểu đạt yêu cầu, không chứng minh kết quả đã đạt. [OpenID Connect Core — ID Token và Authentication Request](https://openid.net/specs/openid-connect-core-1_0.html#IDToken).

Ví dụ nhóm triển khai tự định nghĩa một lớp:

```text
issuer: https://idp.example.invalid
acr: urn:example:authentication:privileged-v1
```

Đây là giá trị minh họa, không phải mã AAL do NIST cấp. Tài liệu tích hợp của lớp này cần xác định các điều kiện thực tế để phát hành và cách RP sử dụng nó.

RP nên ánh xạ theo cả issuer và lớp đã thỏa thuận. Hai nhà cung cấp có chuỗi giống nhau không nhất thiết đưa ra cùng bằng chứng. RP cũng cần xử lý trường hợp lớp bị thiếu, không nhận biết được hoặc không đạt yêu cầu; không mặc định nâng lên mức cao nhất.

Chỉ sử dụng thông tin sau khi token và luồng liên quan đã được xác minh phù hợp. Việc đọc được payload không tạo ra sự tin cậy cho claim.

Khi làm mới token, `auth_time` vẫn chỉ thời điểm xác thực ban đầu, không phải thời điểm phát hành token mới. [OpenID Connect Core — Refresh Token Response Validation](https://openid.net/specs/openid-connect-core-1_0.html#RefreshTokenResponseValidation).

Vì thế, nếu Lan đã xác thực từ lâu, một token vừa được phát hành không tự đáp ứng điều kiện “xác thực trong năm phút” của ví dụ.

## 10. Phiên đăng nhập phải giữ đúng giới hạn của bằng chứng

Một phiên có thể kế thừa mức từ sự kiện xác thực tạo ra nó nhưng không được coi có AAL cao hơn sự kiện đó. Quản lý phiên cần thực thi giới hạn thời gian và điều kiện xác thực lại. [NIST — Session Management](https://pages.nist.gov/800-63-4/sp800-63b/session/).

Ứng dụng nên phân biệt ít nhất ba loại thời gian:

- Thời gian sống của phiên: khi nào phiên còn được chấp nhận.
- Thời gian sống của token: khi nào token cụ thể còn hợp lệ.
- Độ mới cần thiết cho thao tác: bằng chứng xác thực gần đây đến mức nào.

Ba loại thời gian này có mục đích khác nhau. Trong ví dụ, phiên có thể còn hoạt động để Lan đọc trang cấu hình nhưng lần xác thực đã quá cũ để gán role. Ứng dụng yêu cầu step-up cho thao tác đó mà không cần coi mọi tương tác khác đều tương đương.

Khi triển khai theo tiêu chuẩn, phải đọc đúng yêu cầu tái xác thực của phiên bản được chọn. Không sao chép một con số timeout từ tài liệu cũ rồi coi nó áp dụng giống nhau cho mọi mức, mọi loại thời hạn và mọi hành động.

## 11. Đăng ký, thay thế và khôi phục authenticator

Quá trình sử dụng tài khoản bao gồm cả đăng ký authenticator, thay thế thiết bị và khôi phục khi mất quyền kiểm soát. NIST yêu cầu lưu đặc tính authenticator đã gắn với tài khoản để verifier đánh giá các mức, và quy định riêng về binding cũng như recovery. [NIST — Authenticator Event Management](https://pages.nist.gov/800-63-4/sp800-63b/events/).

Xét tình huống Lan mất khóa bảo mật. Nếu nhân viên hỗ trợ có thể thêm khóa mới chỉ sau một cuộc gọi dễ giả mạo, kẻ tấn công có thể lấy quyền kiểm soát tài khoản mà không cần đánh bại luồng đăng nhập thông thường.

Trong thiết kế minh họa, nhóm phát triển cần trả lời:

- Ai được phép đăng ký thiết bị thay thế và phải đưa ra bằng chứng nào?
- Khóa cũ được đánh dấu mất hoặc thu hồi như thế nào?
- Phiên hiện có có cần bị vô hiệu hóa theo chính sách không?
- Sau recovery, ứng dụng yêu cầu bước xác thực nào trước thao tác đặc quyền?
- Chủ tài khoản nhận được thông báo bằng kênh nào?

Recovery thành công không có nghĩa một lần xác thực AAL3 đã diễn ra. Các bước khôi phục, gắn authenticator mới và xác thực bằng authenticator đó cần được phân biệt trong trạng thái và lịch sử sự kiện.

## 12. Bằng chứng và tình huống kiểm tra

Để giải thích một quyết định, ứng dụng có thể ghi lại: thao tác, chủ thể, phiên hoặc mã liên kết phù hợp, chính sách áp dụng, mức yêu cầu, context đã xác minh và kết quả. Chọn dữ liệu đủ cho mục đích điều tra; không ghi mật khẩu, OTP, khóa riêng hoặc toàn bộ token vào audit.

Bảng sau là các tình huống kiểm tra do ví dụ bài học đề xuất:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Tài khoản có khóa bảo mật nhưng phiên chỉ dùng mật khẩu | Quyết định dựa trên bằng chứng phiên, không dựa vào cờ đã đăng ký khóa. |
| Người gọi tự gửi header khai báo AAL3 | Không coi header tự khai là bằng chứng tin cậy. |
| Step-up trả về đúng chủ thể nhưng tenant thao tác không thuộc quyền | Từ chối thao tác theo kiểm tra authorization. |
| Lớp `acr` chưa có trong thỏa thuận với issuer | Không ánh xạ tùy ý sang mức cao. |
| Token mới nhưng thời điểm xác thực đã quá cũ | Yêu cầu bằng chứng mới nếu thao tác đòi hỏi. |
| Quyền gán role bị thu hồi trong lúc step-up | Kiểm tra lại và không thực hiện thay đổi. |
| Kết quả step-up thuộc tài khoản khác | Không gắn kết quả vào yêu cầu đang chờ. |
| IdP không đáp ứng mức được yêu cầu | Không âm thầm giảm điều kiện để tiếp tục. |

Khi giải thích một cơ chế IAM, hãy mô tả đồng thời điều kiện xác thực và điều kiện cấp quyền. AAL giúp diễn đạt chất lượng bằng chứng xác thực; việc sử dụng bằng chứng đó đúng trong phiên, SSO và vòng đời tài khoản là phần công việc của toàn bộ hệ thống.
