# Audience restriction

Một doanh nghiệp dùng chung Identity Provider (IdP) cho cổng nhân sự và hệ thống kế toán. Người dùng đăng nhập thành công vào cổng nhân sự, nhận một SAML assertion do IdP hợp lệ phát hành. Nếu hệ thống kế toán chỉ kiểm tra chữ ký và tên người dùng, nó có thể chấp nhận nhầm assertion vốn được cấp cho cổng nhân sự.

Audience restriction giúp Service Provider (SP) trả lời câu hỏi: **“Assertion này có được cấp để chính dịch vụ của tôi sử dụng hay không?”** Đây là một ranh giới quan trọng khi nhiều ứng dụng cùng tin cậy một IdP.

## 1. Audience là bên dự kiến sử dụng assertion

Trong SAML, `AudienceRestriction` là điều kiện thuộc `Conditions`; các phần tử `Audience` định danh những bên mà assertion hướng tới bằng URI. Một SP phải đáp ứng điều kiện này để sử dụng assertion. Audience không định danh người đăng nhập và cũng không biểu thị vai trò của họ. Xem định nghĩa tại [SAML Core 2.0, mục 2.5.1.4](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf#page=23).

Ví dụ dưới đây chỉ minh họa phần điều kiện, không phải assertion hoàn chỉnh để gửi vào hệ thống thật:

```xml
<saml:Conditions xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    <saml:AudienceRestriction>
        <saml:Audience>urn:example:sp:hr:prod</saml:Audience>
    </saml:AudienceRestriction>
</saml:Conditions>
```

Với cấu hình ví dụ này, `urn:example:sp:hr:prod` là danh tính của SP nhân sự ở môi trường production. Nó không phải tên người dùng, nhóm nhân viên hay địa chỉ trình duyệt đang mở.

Các câu hỏi phải được tách riêng khi thiết kế luồng đăng nhập:

| Câu hỏi | Dữ liệu hoặc bước xử lý liên quan |
|---|---|
| Ai phát hành thông tin này? | Issuer và quan hệ tin cậy với IdP |
| Thông tin có được bảo vệ khỏi sửa đổi không? | Xác minh chữ ký và đối tượng được chữ ký bảo vệ |
| Assertion có dành cho SP này không? | Audience restriction |
| Assertion nói về người dùng nào? | Subject, NameID và quy tắc ánh xạ tài khoản |
| Người dùng được làm gì trong ứng dụng? | Chính sách phân quyền của ứng dụng |

Ứng dụng nhân sự nhận đúng audience vẫn cần kiểm tra tài khoản có đang hoạt động và người dùng có quyền xem bảng lương hay không. Không thể suy quyền nghiệp vụ chỉ từ việc audience hợp lệ.

## 2. Chọn đúng entityID của SP

Metadata SAML dùng `entityID` để định danh một SAML entity. `entityID` và endpoint phục vụ HTTP là hai cấu hình khác nhau; metadata mô tả chúng ở các vị trí khác nhau. Xem [SAML Metadata 2.0, mục 2.3.2 và 2.4.4](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf#page=10).

Trong một triển khai minh họa, ta có:

```text
IdP entityID:  https://idp.example.org/saml
SP entityID:   urn:example:sp:hr:prod
SP ACS URL:    https://hr.example.org/saml/acs
Audience:      urn:example:sp:hr:prod
```

Ở đây, Assertion Consumer Service (ACS) là endpoint tiếp nhận phản hồi SAML. Audience đối chiếu với danh tính SP đã thỏa thuận, không mặc nhiên đối chiếu với URL ACS.

Một `entityID` cũng có thể được đặt ở dạng URL, chẳng hạn `https://hr.example.org/saml/metadata`. Việc nhìn giống URL không khiến nó trở thành địa chỉ callback và không yêu cầu ứng dụng tải URL ấy để quyết định có chấp nhận audience hay không.

Với Web Browser SSO dùng bearer subject confirmation, profile yêu cầu assertion chứa audience restriction có định danh duy nhất của SP. Vì vậy, thiếu audience restriction trong trường hợp này phải được xử lý như lỗi kiểm tra profile, thay vì hiểu là assertion dành cho mọi ứng dụng. Xem [SAML Profiles 2.0, mục 4.1.4.2](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf#page=19).

## 3. Phân biệt Audience, Recipient và Destination

Giả sử cổng nhân sự có entityID `urn:example:sp:hr:prod` và ACS `https://hr.example.org/saml/acs`. Khi quan sát một phản hồi, người vận hành có thể gặp ba giá trị phục vụ các mục đích khác nhau:

| Trường | Ý nghĩa khi kiểm tra phản hồi |
|---|---|
| `Conditions/AudienceRestriction/Audience` | Assertion có dành cho danh tính SP đang xử lý hay không |
| `SubjectConfirmationData/@Recipient` | Subject confirmation có hướng tới endpoint nhận phù hợp hay không |
| `Response/@Destination` | Thông điệp phản hồi có hướng tới địa chỉ đích phù hợp theo binding và profile hay không |

Ví dụ, phản hồi được chuyển tới đúng ACS của cổng nhân sự nhưng assertion bên trong có audience `urn:example:sp:accounting:prod`. Địa chỉ giao nhận đúng không sửa được việc assertion được cấp cho hệ thống kế toán.

Ngược lại, audience đúng cũng không thay cho kiểm tra recipient. Browser SSO yêu cầu SP kiểm tra `Recipient` của bearer subject confirmation với ACS nhận phản hồi; còn có kiểm tra thời hạn và tương quan `InResponseTo` theo luồng. Xem [SAML Profiles 2.0, mục 4.1.4.3](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf#page=19).

Trong thiết kế kiểm tra, nên xem các bước này như những điều kiện đồng thời. Không dùng một trường để suy rằng các trường khác chắc chắn hợp lệ.

## 4. Nhiều audience: OR bên trong, AND giữa các restriction

Một restriction có thể nêu nhiều audience; các audience trong cùng restriction kết hợp theo OR. Nếu assertion có nhiều restriction, từng restriction đều phải đạt, tức kết hợp theo AND. Đây là điểm được làm rõ trong [SAML 2.0 Approved Errata](https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-approved-errata-2.0.pdf).

### 4.1. Hai audience trong cùng restriction

```xml
<saml:Conditions xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    <saml:AudienceRestriction>
        <saml:Audience>urn:example:sp:hr:prod</saml:Audience>
        <saml:Audience>urn:example:sp:accounting:prod</saml:Audience>
    </saml:AudienceRestriction>
</saml:Conditions>
```

Trong ví dụ, SP nhân sự hoặc SP kế toán có thể thỏa riêng điều kiện audience này. Điều đó không có nghĩa hai ứng dụng cùng phải tham gia một lần đăng nhập, và cũng không có nghĩa các kiểm tra khác đã đạt.

### 4.2. Hai restriction độc lập

```xml
<saml:Conditions xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    <saml:AudienceRestriction>
        <saml:Audience>urn:example:sp:hr:prod</saml:Audience>
        <saml:Audience>urn:example:sp:accounting:prod</saml:Audience>
    </saml:AudienceRestriction>
    <saml:AudienceRestriction>
        <saml:Audience>urn:example:sp:accounting:prod</saml:Audience>
        <saml:Audience>urn:example:sp:reporting:prod</saml:Audience>
    </saml:AudienceRestriction>
</saml:Conditions>
```

Nếu trong mô hình ví dụ mỗi SP chỉ dùng đúng một entityID, kết quả là:

| SP đang xử lý | Restriction thứ nhất | Restriction thứ hai | Kết quả audience |
|---|---|---|---|
| Nhân sự | Đạt | Không đạt | Từ chối |
| Kế toán | Đạt | Đạt | Đạt |
| Báo cáo | Không đạt | Đạt | Từ chối |

Không được gộp toàn bộ audience của assertion thành một danh sách phẳng rồi chỉ tìm một giá trị khớp. Cách đó làm mất quan hệ AND, khiến SP nhân sự và báo cáo được chấp nhận sai trong ví dụ này.

## 5. Đối chiếu audience từ cấu hình tin cậy

Giá trị mong đợi phải đến từ cấu hình SP hoặc registration đã xác định bằng ngữ cảnh tin cậy. Không lấy audience trong assertion rồi tự đặt nó làm expected audience; phép so sánh như vậy luôn đúng và không còn kiểm tra ranh giới dịch vụ.

SAML quy định cách so sánh định danh URI theo dạng chuỗi, không tùy ý chuẩn hóa URL. Khi triển khai, hãy để thư viện SAML xử lý theo chuẩn và giữ giá trị cấu hình thống nhất với metadata. Xem [SAML Core 2.0, mục 1.3.1–1.3.2](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf#page=9).

Những cách “so khớp linh hoạt” sau là lựa chọn thiết kế nguy hiểm:

- Chỉ so tên miền và bỏ phần đường dẫn hoặc hậu tố môi trường.
- Dùng `startsWith` để chấp nhận mọi giá trị có cùng tiền tố.
- Dùng wildcard cho cả một họ ứng dụng.
- Tự bỏ dấu `/` cuối hoặc đổi chữ hoa thành chữ thường để che lỗi cấu hình.
- Chấp nhận audience của mọi tenant vì các tenant dùng chung một IdP.

Ví dụ, nếu cấu hình SP là `urn:example:sp:hr:prod`, các chuỗi `urn:example:sp:hr:prod-admin` và `urn:example:sp:hr:test` không được chấp nhận chỉ vì cùng bắt đầu bằng `urn:example:sp:hr:`.

### Minh họa thuật toán bằng Java

Đoạn mã sau chỉ minh họa phép kết hợp audience cho mô hình một SP có một entityID. Nó không parse XML, không xác minh chữ ký và không phải bộ xác thực SAML hoàn chỉnh.

```java
import java.util.List;

public final class AudienceRuleExample {
    private AudienceRuleExample() {
    }

    public static boolean matches(
            String expectedSpEntityId,
            List<List<String>> restrictions) {

        if (expectedSpEntityId == null || expectedSpEntityId.isEmpty()) {
            return false;
        }

        // Chính sách minh họa cho Browser SSO bearer:
        // không chấp nhận assertion thiếu audience restriction.
        if (restrictions == null || restrictions.isEmpty()) {
            return false;
        }

        for (List<String> audiences : restrictions) {
            if (audiences == null || audiences.isEmpty()) {
                return false;
            }

            boolean currentRestrictionMatches = false;
            for (String audience : audiences) {
                if (expectedSpEntityId.equals(audience)) {
                    currentRestrictionMatches = true;
                    break;
                }
            }

            if (!currentRestrictionMatches) {
                return false;
            }
        }

        return true;
    }
}
```

Vòng lặp trong tìm ít nhất một audience phù hợp. Vòng lặp ngoài yêu cầu tất cả restriction đều đạt. Dữ liệu đầu vào ở ví dụ là giá trị sau khi XML đã được parse; trong hệ thống thật, ứng dụng phải sử dụng đúng assertion mà thư viện đã xác minh và đánh giá điều kiện.

Việc một hàm tự viết trả về `true` không đủ để tạo phiên. Thư viện SAML vẫn phải thực hiện toàn bộ quy trình xác thực, với các validator cần thiết được bật và cấu hình đúng.

## 6. Đặt kiểm tra audience trước khi tạo phiên

Một cách tổ chức luồng xử lý ở SP là:

```text
Nhận phản hồi tại endpoint đã cấu hình
    → thư viện parse và xác minh thông điệp theo profile
    → kiểm tra issuer, chữ ký và các ràng buộc giao thức
    → kiểm tra Conditions, bao gồm audience và thời gian
    → kiểm tra tương quan yêu cầu, subject confirmation, chống phát lại
    → ánh xạ tài khoản và áp dụng chính sách ứng dụng
    → tạo phiên khi mọi kiểm tra bắt buộc đều đạt
```

Đây là mô hình tổ chức để hiểu trách nhiệm, không phải yêu cầu tự viết lại thứ tự nội bộ của một thư viện. Điểm cần giữ là mọi kiểm tra bắt buộc phải hoàn tất trước khi ứng dụng coi đăng nhập là thành công.

Khi dùng kết quả xác thực, không tìm một assertion bất kỳ trong XML theo tên phần tử rồi đọc lại thuộc tính người dùng. Dữ liệu dùng để tạo phiên phải thuộc chính đối tượng mà bộ xác thực đã chấp nhận. Nếu kiểm tra audience trên assertion A nhưng đọc NameID từ assertion B, ứng dụng đã tự phá mối liên kết giữa kiểm tra và dữ liệu sử dụng.

Audience restriction cũng không bảo vệ tính bí mật. Assertion vẫn có thể bị đọc nếu bị lộ; yêu cầu mã hóa, bảo vệ kênh truyền và xử lý dữ liệu nhạy cảm cần được giải quyết riêng. Tương tự, audience đúng không ngăn assertion bị gửi lại cho chính SP đó; cơ chế chống phát lại vẫn cần hoạt động.

## 7. Áp dụng cho nhiều môi trường và nhiều tenant

Trong một thiết kế minh họa, nên cấp danh tính SP phân biệt cho các ranh giới cần cách ly:

```text
urn:example:sp:hr:development
urn:example:sp:hr:staging
urn:example:sp:hr:production
```

Nếu staging và production dùng chung entityID, audience không còn phân biệt được hai môi trường ấy. Các kiểm tra khác có thể vẫn chặn một phản hồi sai, nhưng thiết kế đã làm yếu khả năng phát hiện chuyển nhầm assertion bằng audience.

Với ứng dụng nhiều tenant, có thể có một SP dùng chung hoặc nhiều registration SP riêng. Hai mô hình có hệ quả khác nhau:

- Nếu mỗi tenant có entityID riêng, chọn đúng registration từ ngữ cảnh yêu cầu đáng tin cậy và kiểm tra audience tương ứng.
- Nếu mọi tenant thật sự dùng chung entityID, audience chỉ xác nhận SP chung. Việc ràng buộc người dùng với tenant phải dựa vào chính sách và dữ liệu đã xác thực khác.

Không chọn tenant chỉ bằng một audience chưa được xác thực, rồi dùng chính tenant vừa chọn để kết luận assertion hợp lệ. Tương tự, không coi email có cùng hậu tố tên miền là bằng chứng đầy đủ cho quyền truy cập tenant.

Khi đổi entityID, cách chuyển đổi cần được thiết kế rõ. Một phương án là cấu hình các registration được kiểm soát cho danh tính cũ và mới, quy định thời gian chuyển tiếp và kiểm thử độc lập. Tránh thêm mọi giá trị từng thấy vào một allowlist toàn cục chỉ để loại bỏ lỗi đăng nhập.

## 8. Chẩn đoán lỗi audience mismatch

Giả sử người dùng xác thực thành công ở IdP nhưng SP từ chối phản hồi với lỗi audience. Hãy thu hẹp vấn đề ở cấu hình liên kết giữa đúng IdP application và đúng SP registration.

Một trình tự kiểm tra hữu ích là:

1. Xác nhận ứng dụng, tenant và môi trường đang xử lý lần đăng nhập.
2. Đọc expected entityID từ cấu hình hiệu lực của registration đó.
3. Trong công cụ chẩn đoán được kiểm soát, xem các audience theo từng restriction của assertion liên quan.
4. Đối chiếu cấu hình audience phía IdP với entityID SP đã thống nhất.
5. Kiểm tra có nhầm ACS URL, IdP entityID, alias cũ hoặc giá trị từ môi trường khác hay không.
6. Sửa nguồn cấu hình sai và thử lại cả trường hợp đúng lẫn trường hợp phải bị từ chối.

Ví dụ các lỗi cấu hình có thể gặp:

| Cấu hình SP mong đợi | Giá trị IdP phát hành | Điều cần kiểm tra |
|---|---|---|
| `urn:example:sp:hr:prod` | `https://hr.example.org/saml/acs` | Có dùng nhầm ACS làm audience không |
| `urn:example:sp:hr:prod` | `https://idp.example.org/saml` | Có điền nhầm danh tính IdP không |
| `urn:example:sp:hr:prod` | `urn:example:sp:hr:staging` | Có chọn nhầm ứng dụng hoặc môi trường không |
| `urn:example:sp:hr:prod` | `urn:example:sp:hr:prod-old` | Hai phía đã hoàn tất chuyển đổi entityID chưa |

Các giá trị trong bảng là ví dụ của một cấu hình cụ thể, không phải quy tắc rằng ACS URL tuyệt đối không thể đồng thời được chọn làm entityID. Vấn đề là phải dùng đúng định danh đã thỏa thuận, thay vì suy từ hình thức chuỗi.

Không tắt audience validation để xử lý sự cố. Làm như vậy biến lỗi cấu hình có thể phát hiện thành một lỗ hổng trong việc giới hạn assertion cho đúng ứng dụng.

Log chẩn đoán nên chứa mã lỗi, registration, correlation ID và thông tin cần thiết theo chính sách của tổ chức. Hạn chế ghi toàn bộ assertion, NameID và thuộc tính cá nhân; nếu cần thu thập dữ liệu mẫu, phải kiểm soát nơi lưu và thời gian lưu. Đừng tạo phiên tạm chỉ vì người dùng đã nhập đúng mật khẩu ở IdP.

## 9. Tự kiểm tra bằng các tình huống

Với SP có entityID `urn:example:sp:hr:prod`, hãy dự đoán kết quả riêng của audience validation:

| Tình huống | Kết quả mong đợi |
|---|---|
| Một restriction chứa đúng entityID SP | Đạt điều kiện audience |
| Một restriction chỉ chứa entityID hệ thống kế toán | Từ chối |
| Chữ ký hợp lệ nhưng audience dành cho staging | Từ chối |
| Hai restriction, chỉ restriction đầu chứa entityID SP | Từ chối |
| Không có restriction trong assertion Browser SSO bearer | Từ chối theo yêu cầu profile |
| Audience đúng nhưng assertion hết hạn | Audience có thể đạt, nhưng đăng nhập vẫn phải bị từ chối |
| Audience đúng nhưng người dùng không có quyền xem bảng lương | Không suy ra quyền xem bảng lương |

Một câu hỏi thiết kế cần tự trả lời là: nếu thêm một ứng dụng mới cùng tin cậy IdP hiện tại, assertion cấp cho ứng dụng đó có thể được chấp nhận tại SP của mình không? Câu trả lời phải được chứng minh bằng cấu hình audience, phạm vi registration và kiểm thử từ chối, không chỉ bằng việc hai ứng dụng dùng cùng chứng thư IdP.

Audience restriction chỉ phát huy tác dụng khi SP thực sự kiểm tra nó trên assertion đã được xác thực. Giữ danh tính SP rõ ràng, đánh giá đúng từng restriction và chỉ tạo phiên sau khi toàn bộ ràng buộc đạt sẽ giúp duy trì ranh giới giữa các ứng dụng trong hệ thống IAM.
