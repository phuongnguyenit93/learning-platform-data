# Phân biệt registrationId, entityId và tên hiển thị nhà cung cấp trong đăng ký SAML 2.0

## 1. Vấn đề cần giải quyết

Một ứng dụng Spring Boot sử dụng **Spring Security SAML 2.0 Login** có thể cho người dùng đăng nhập qua một hoặc nhiều Identity Provider (IdP). Khi thiết lập từng kết nối, nhóm phát triển thường thấy ba giá trị trông giống nhau:

- **`registrationId`**: mã cấu hình **cục bộ của Spring Security**, dùng để tìm một `RelyingPartyRegistration`.
- **`entityId`**: mã định danh **theo giao thức SAML** của Service Provider (SP) hoặc IdP; tham gia vào hợp đồng tin cậy và kiểm tra thông điệp.
- **Tên hiển thị nhà cung cấp** (*display name*): chuỗi cho con người đọc trên giao diện, ví dụ **“Đăng nhập bằng tài khoản công ty”**.

Dù đều có thể trông như “tên nhà cung cấp”, ba giá trị trả lời **ba câu hỏi khác nhau**:

| Câu hỏi | Giá trị trả lời |
| --- | --- |
| “Spring Security phải chọn cấu hình kết nối nào?” | `registrationId` |
| “Thông điệp do SP nào yêu cầu, IdP nào phát hành, assertion dành cho SP nào?” | SP/IdP `entityId` |
| “Trên trang đăng nhập, nút này ghi chữ gì để người dùng nhận ra?” | Tên hiển thị trong UI |

**Không dùng một giá trị để thay thế tùy tiện cho giá trị khác.** Đặc biệt, đổi nhãn nút đăng nhập không phải lý do để đổi SAML Entity ID; dùng đúng Entity ID nhưng chọn sai registration/certificate vẫn có thể gây lỗi hoặc vi phạm ranh giới tin cậy.

Bài học thuộc nhóm **Đăng ký SAML2**. Trọng tâm là cách đặt tên, cấu hình và vận hành mối quan hệ giữa ba loại giá trị trên, không phải thay thế toàn bộ quy trình xác minh SAML bằng một phép so sánh chuỗi.

## 2. RelyingPartyRegistration là gì?

Trong Spring Security SAML 2.0:

- **Relying Party (RP)** đồng nghĩa **Service Provider (SP)**: chính ứng dụng Spring Boot phục vụ người dùng.
- **Asserting Party (AP)** đồng nghĩa **Identity Provider (IdP)**: hệ thống xác thực và phát hành SAML Response/Assertion.
- **`RelyingPartyRegistration`** mô tả **một mối quan hệ RP–AP**: định danh hai bên, endpoint, certificate, cách gửi/nhận thông điệp và các tùy chọn bảo mật.
- **`RelyingPartyRegistrationRepository`** là nơi Spring Security tìm registration khi cần tạo AuthnRequest, xử lý Response hoặc công bố metadata.

Một tổ chức có thể tạo nhiều registration cho cùng ứng dụng:

```text
Ứng dụng Spring Boot (Service Provider)
    |
    +-- registrationId = employee
    |     +-- SP entityId  = urn:example:portal:prod:sp
    |     +-- IdP entityId = https://sso.company.example.test/saml/idp
    |     +-- UI label     = Tài khoản nhân viên
    |
    +-- registrationId = partner
          +-- SP entityId  = urn:example:portal:prod:sp
          +-- IdP entityId = https://login.partner.example.test/issuer
          +-- UI label     = Tài khoản đối tác
```

Hai registration có thể dùng cùng **SP Entity ID** nếu cả hai quan hệ được cấu hình và các IdP chấp nhận cùng định danh SP đó. Chúng vẫn là **hai cấu hình khác nhau** do IdP, endpoint/certificate hoặc chính sách khác nhau.

Cũng có những triển khai cấp **SP Entity ID riêng cho từng registration hoặc môi trường**. Điều này phụ thuộc hợp đồng đã đăng ký với IdP; không có quy tắc bắt buộc mọi registration phải chia sẻ một entity ID hoặc mọi registration phải có entity ID khác nhau.

## 3. registrationId: mã tra cứu nội bộ của Spring Security

`registrationId` là **một chuỗi do ứng dụng chọn** để phân biệt các `RelyingPartyRegistration` trong repository. Ví dụ:

```text
employee
partner
corp-adfs
customer-okta
```

Đặc điểm:

1. **Duy nhất trong repository**: mỗi registration cần một khóa tra cứu riêng trong tập cấu hình đang sử dụng.
2. **Do ứng dụng sở hữu**: tên có thể được đặt là `employee` dù IdP có tên sản phẩm thương mại hoàn toàn khác.
3. **Tham gia định tuyến mặc định**: thường có `/saml2/authenticate/{registrationId}`, `/login/saml2/sso/{registrationId}`, và `/saml2/metadata/{registrationId}`.
4. **Không phải bí mật**: giá trị có thể xuất hiện trong đường dẫn công khai; không dùng làm mật khẩu, token hay bằng chứng xác thực.
5. **Không mặc nhiên là Entity ID**: `employee` chỉ là key Spring; nó không tự trở thành giá trị `<saml:Issuer>` hoặc `<saml:Audience>`.

Theo Spring Security, URL:

```text
GET /saml2/authenticate/employee
```

thường yêu cầu ứng dụng lấy registration có `registrationId=employee` và khởi tạo AuthnRequest tới IdP đã được cấu hình trong registration ấy.

Ở chiều nhận, SAML Response có thể được POST tới:

```text
POST /login/saml2/sso/employee
```

Tuy nhiên, **Spring Security không chỉ dựa vào path registrationId trong mọi trường hợp**. Khi xử lý Response, framework có thể tìm registration qua request đã lưu/correlated state hoặc issuer của Response, tùy phiên bản và cấu hình. Định danh registration vẫn là khóa quản lý cặp RP–AP. Không nên tự viết bộ xử lý Response chỉ tin suffix URL.

### 3.1. Vì sao nên đặt registrationId ổn định?

Giả sử có nút đăng nhập dẫn đến `/saml2/authenticate/employee`. Nếu đổi key thành `staff`, link cũ không còn tìm được registration (trừ khi ứng dụng có alias/logic chuyển tiếp). Ngoài ra, ACS URL dùng `{registrationId}` sẽ đổi:

```text
Trước: https://portal.example.test/login/saml2/sso/employee
Sau:   https://portal.example.test/login/saml2/sso/staff
```

Nếu IdP vẫn lưu ACS cũ, nó có thể từ chối AuthnRequest hoặc gửi Response về nơi không phù hợp. Cấu hình metadata, allowlist, login links và luồng SAML đang diễn ra cũng cần được kiểm tra trước khi đổi.

**Lưu ý quan trọng:** đổi `registrationId` **không nhất thiết làm đổi SP Entity ID** nếu SP Entity ID được đặt cố định. Ngược lại, nếu SP Entity ID sử dụng placeholder `{registrationId}`, đổi key có thể **làm đổi cả Entity ID sau khi mở rộng template**. Luôn đọc giá trị **thực tế trong metadata** thay vì suy luận từ tên YAML.

### 3.2. Quy ước đặt tên hợp lý

Nên chọn mã ngắn, dễ dùng trong URL, ổn định và có ý nghĩa kỹ thuật:

- `employee` cho IdP nhân viên.
- `partner-acme` cho IdP đối tác được quản trị riêng.
- `corp-adfs-prod` khi cần chỉ rõ hệ thống/môi trường, nhưng tránh nhúng chi tiết dễ đổi nếu không cần.

Không nên dùng tên marketing dài có dấu, email, URL nguyên vẹn hoặc nhãn hiển thị chứa khoảng trắng làm registration ID. Đây là **quy ước vận hành khuyến nghị**, không phải một quy tắc SAML buộc mọi registration ID phải theo định dạng trên.

## 4. entityId: danh tính SAML của hai bên

`entityId` là **định danh logic của một SAML entity**. Metadata của mỗi bên công bố một giá trị qua `<md:EntityDescriptor entityID="...">`.

Trong một registration có **hai Entity ID**:

1. **SP Entity ID / Relying Party Entity ID**: định danh **ứng dụng Spring** trong federation.
2. **IdP Entity ID / Asserting Party Entity ID**: định danh **máy chủ xác thực**.

Ví dụ:

```text
registrationId      = employee
SP entityId         = urn:example:portal:prod:sp
IdP entityId        = https://sso.company.example.test/saml/idp
Tên hiển thị        = Đăng nhập bằng tài khoản nhân viên
```

SP Entity ID có thể là URI dạng `urn:` hoặc `https:`. **Nó không tự động là URL trình duyệt cần mở**. IdP Entity ID cũng có thể giống một URL, nhưng không bắt buộc trùng địa chỉ đăng nhập IdP.

### 4.1. Entity ID xuất hiện trong thông điệp SAML

Trong **SP-initiated login**, phần tử `<saml:Issuer>` bên trong `AuthnRequest` do SP tạo thường chứa **SP Entity ID**:

```xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req_001"
    Version="2.0"
    IssueInstant="2026-01-01T10:00:00Z"
    Destination="https://sso.company.example.test/saml/sso">
    <saml:Issuer>urn:example:portal:prod:sp</saml:Issuer>
</samlp:AuthnRequest>
```

Trong SAML Response/Assertion từ IdP, `Issuer` chỉ **IdP Entity ID** và `AudienceRestriction/Audience` thường chỉ **SP Entity ID**:

```xml
<saml:Issuer
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    https://sso.company.example.test/saml/idp
</saml:Issuer>

<saml:AudienceRestriction
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    <saml:Audience>urn:example:portal:prod:sp</saml:Audience>
</saml:AudienceRestriction>
```

Các đoạn XML này **chỉ minh họa vị trí hai định danh**; chúng không phải AuthnRequest/Response/Assertion đầy đủ, không có chữ ký và **không dùng như bằng chứng đăng nhập**.

Cặp Entity ID thuộc **hợp đồng tin cậy SAML**, nên:

- IdP đối chiếu `AuthnRequest/Issuer` với SP mà IdP đã đăng ký.
- SP đối chiếu IdP issuer trong Response/Assertion với nhà phát hành đáng tin cậy.
- SP kiểm tra audience assertion phù hợp với **SP Entity ID** của mình.
- SP còn phải kiểm tra chữ ký bằng certificate đúng, `Destination`, `Recipient`, thời gian, `InResponseTo`, SubjectConfirmation và chống replay theo luồng/profile.

**Không tin một assertion chỉ vì các chuỗi Entity ID khớp**: attacker có thể tự viết XML chứa đúng chuỗi. Chữ ký và trust configuration mới giúp xác minh nguồn phát hành.

### 4.2. Entity ID khác metadata URL và endpoint

| Khái niệm | Ví dụ | Chức năng |
| --- | --- | --- |
| SP Entity ID | `urn:example:portal:prod:sp` | Định danh ứng dụng trong SAML; dùng trong AuthnRequest Issuer/Audience |
| IdP Entity ID | `https://sso.company.example.test/saml/idp` | Định danh nhà phát hành assertion |
| SP metadata URL | `https://portal.example.test/saml2/metadata/employee` | Nơi tải metadata của SP |
| IdP metadata URL | `https://sso.company.example.test/saml/metadata` | Nơi tải metadata của IdP |
| Assertion Consumer Service (ACS) | `https://portal.example.test/login/saml2/sso/employee` | Endpoint SP nhận SAML Response |
| Single Sign-On (SSO) URL | `https://sso.company.example.test/saml/sso` | Endpoint IdP nhận AuthnRequest |
| `registrationId` | `employee` | Mã tra cứu registration bên trong Spring Security |
| UI display name | “Tài khoản nhân viên” | Chữ hiển thị trên nút hoặc danh sách đăng nhập |
| `NameID` | `user-418` (giả định) | Định danh **người dùng** trong assertion, không phải nhà cung cấp |

Metadata URL, ACS và SSO URL có thể trông giống IdP/SP Entity ID. Dù cùng hostname, **không được thay thế lẫn nhau** nếu phía IdP/SP đã ký kết các giá trị riêng.

### 4.3. Hai Entity ID và phạm vi duy nhất

- Hai IdP khác nhau nên được nhận diện theo **đúng Entity ID và trust credentials** của từng bên.
- Một nhà cung cấp thương mại có thể vận hành nhiều tenant/realm với **các IdP Entity ID khác nhau**.
- Hai registration cục bộ có thể trỏ đến cùng IdP Entity ID nếu có lý do cấu hình, nhưng việc chọn đúng RP–AP phải còn dựa trên các ràng buộc của từng registration.
- Một SP có thể giữ cùng Entity ID qua nhiều registration IdP, hoặc cấp Entity ID khác nhau theo tenant/môi trường. Cần thỏa thuận trước với IdP.

Không suy một IdP Entity ID từ hãng phần mềm (“Okta”, “ADFS”), từ hostname hoặc tên doanh nghiệp. **Lấy giá trị từ IdP metadata đã được xác thực hoặc hợp đồng cấu hình được duyệt**.

## 5. Tên hiển thị nhà cung cấp: dữ liệu của giao diện

Tên hiển thị là **nhãn thân thiện với người dùng**. Ví dụ:

```text
Tài khoản nhân viên
Đăng nhập qua SSO đối tác
Tài khoản nhà cung cấp
```

Tên này giúp người dùng chọn đúng hệ thống đăng nhập, đặc biệt khi ứng dụng hỗ trợ nhiều IdP. Nó **không phải** một thành phần bắt buộc trong SAML AuthnRequest, Response hoặc AudienceRestriction.

Một trang đăng nhập được thiết kế riêng có thể có dữ liệu:

| registrationId | displayName | loginUrl |
| --- | --- | --- |
| `employee` | Đăng nhập bằng tài khoản nhân viên | `/saml2/authenticate/employee` |
| `partner` | Đăng nhập bằng tài khoản đối tác | `/saml2/authenticate/partner` |

Trong bảng này, ứng dụng quản lý ánh xạ `registrationId -> displayName`. Cần phân biệt **nhãn hiển thị do UI quyết định** với những thông tin có thể có trong metadata bên IdP như `OrganizationDisplayName` hoặc mở rộng `mdui:DisplayName`. Metadata SAML không bảo đảm mọi IdP đều công bố tên thân thiện nhất quán; cũng không bảo đảm Spring Security tự ánh xạ metadata đó thành một property tên hiển thị chuẩn trong cấu hình registration.

**Khuyến nghị:** nếu cần kiểm soát văn bản, ngôn ngữ, thứ tự, logo và trải nghiệm chọn IdP, hãy xây **trang chọn IdP của riêng ứng dụng** với mapping được quản trị. Trang đăng nhập tự sinh của Spring Security và cách nó hiển thị các provider có thể thay đổi theo phiên bản/cấu hình; đừng coi text hiển thị mặc định là hợp đồng giao thức.

### 5.1. Đổi tên hiển thị ảnh hưởng điều gì?

Nếu trước kia nút ghi “Corporate SSO” và nay đổi thành “Tài khoản nhân viên”, với **cùng registrationId và hai Entity ID**, thì:

- Người dùng thấy nhãn mới.
- URL đăng nhập, SP/IdP metadata và quan hệ tin cậy vẫn giữ nguyên.
- Chữ ký SAML, issuer/audience không bị thay đổi.
- Không cần cập nhật IdP chỉ vì nút được đổi chữ (trừ quy trình quản trị thương hiệu riêng).

Ngược lại, nếu người dùng bấm “Tài khoản nhân viên” nhưng link trỏ `/saml2/authenticate/partner`, hệ thống có thể bắt đầu luồng ở **sai IdP**. Đây là lỗi ánh xạ giao diện sang registration, dù bản thân chuỗi displayName không có quyền kỹ thuật.

### 5.2. Không dùng tên hiển thị để phân quyền

Nhãn “Đăng nhập quản trị” không trao quyền admin. Các quyền phát sinh từ danh tính đã xác minh, ánh xạ tài khoản, membership, chính sách của ứng dụng và thông tin SAML được tin cậy theo hợp đồng. Không đặt logic bảo mật như:

```text
if (providerDisplayName == "Admin SSO") allowAll()
```

Đây là mẫu **không an toàn**: display name chỉ là UI text, có thể thay theo ngôn ngữ hoặc thương hiệu. Ngoài ra, tên hiển thị không phải mã định danh người dùng; người dùng được xác định bằng NameID/attributes được xác minh và chính sách liên kết danh tính riêng.

## 6. Bảng so sánh ba khái niệm quan trọng nhất

| Tiêu chí | registrationId | entityId | Tên hiển thị nhà cung cấp |
| --- | --- | --- | --- |
| Thuộc lớp nào? | Cấu hình Spring Security | Giao thức SAML/federation | UI/UX của ứng dụng |
| Do ai chọn? | Đội phát triển/vận hành ứng dụng | SP và IdP theo hợp đồng, metadata | Product/UI/đội vận hành |
| Phạm vi | Repository đăng ký của ứng dụng | Không gian định danh SAML của từng entity | Giao diện/ngôn ngữ |
| Ví dụ | `employee` | `urn:example:portal:prod:sp`, `https://sso.company.example.test/saml/idp` | “Tài khoản nhân viên” |
| Có xuất hiện ở URL? | Thường có, trong endpoint mặc định | Có thể là URI nhưng không phải endpoint bắt buộc | Không cần |
| Có trong metadata SAML? | Không phải `entityID`; có thể là phần của URL metadata | Có: `EntityDescriptor/@entityID` | Có thể có metadata tên UI, nhưng không phải trường xác thực |
| Có trong SAML Issuer/Audience? | Không phải giá trị mặc định để so sánh trust | Có, đúng vai trò SP/IdP | Không |
| Đổi giá trị có thể làm hỏng SSO? | Có, khi URL/template/correlation phụ thuộc | Có, thay đổi hợp đồng trust | Thường không, nếu chỉ đổi UI label |
| Dùng để tra người dùng nội bộ? | Không | Không dùng một mình làm user ID | Không |
| Dùng để quyết định quyền nghiệp vụ? | Không | Không | Không |

**Lưu ý về tính phụ thuộc:** mặc dù khác khái niệm, một số cấu hình cho phép SP `entityId` chứa placeholder `{registrationId}`. Khi đó thay `registrationId` có thể **gián tiếp làm đổi Entity ID**. Quan hệ phụ thuộc do **template do người phát triển chọn**, không phải vì bản chất hai trường giống nhau.

## 7. Ví dụ cấu hình hai IdP bằng Spring Boot

Đây là ví dụ cho **Spring Boot 3.x / Spring Security 6.x**. Cần các dependency thích hợp cho Spring Web/Security và SAML 2.0 Service Provider; IdP thực tế phải được đăng ký và công bố metadata/certificate hợp lệ.

Tệp `src/main/resources/application.yml`:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          employee:
            entity-id: "urn:example:portal:prod:sp"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            assertingparty:
              metadata-uri: "https://sso.company.example.test/saml/metadata"
          partner:
            entity-id: "urn:example:portal:prod:sp"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            assertingparty:
              metadata-uri: "https://login.partner.example.test/saml/metadata"

# Đây là cấu hình riêng của ứng dụng, không phải property SAML chuẩn.
app:
  login-providers:
    employee: "Đăng nhập bằng tài khoản nhân viên"
    partner: "Đăng nhập bằng tài khoản đối tác"
```

Đọc cấu hình:

1. `employee` và `partner` là **registrationId**.
2. `entity-id` ngay dưới mỗi registration là **SP Entity ID**. Ví dụ dùng cùng giá trị cho cả hai vì giả định cả IdP đều đã đăng ký SP đó.
3. `assertingparty.metadata-uri` là **URL tải metadata IdP**, **không phải IdP Entity ID**. IdP Entity ID nằm trong XML metadata của từng nhà cung cấp, ví dụ `<EntityDescriptor entityID="...">`.
4. `acs.location` chứa placeholder `{registrationId}`; URL ACS mỗi registration sẽ khác nhau, dù SP Entity ID giống nhau.
5. `app.login-providers` chỉ là **dữ liệu nhãn UI do ứng dụng tự định nghĩa**, sẽ không tự sinh nút đăng nhập nếu không viết code đọc và sử dụng nó.

Mẫu chỉ nêu mối liên hệ giữa ba loại giá trị; để vận hành cần xác nhận certificate ký/xác minh, IdP metadata đáng tin, binding/ACS, HTTPS, logout nếu dùng, key rotation, và chính sách phát/nhận response. Phiên bản Spring Boot khác nhau có thể đổi tên hoặc khả năng property; cần đối chiếu configuration metadata của đúng phiên bản.

### 7.1. IdP entityId lấy từ đâu?

Ví dụ `https://sso.company.example.test/saml/metadata` trả metadata đáng tin:

```xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://sso.company.example.test/saml/idp">
    <md:IDPSSODescriptor
        protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        <md:SingleSignOnService
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
            Location="https://sso.company.example.test/saml/sso"/>
    </md:IDPSSODescriptor>
</md:EntityDescriptor>
```

Từ đoạn này:

- URL tải metadata: `.../saml/metadata`.
- **IdP Entity ID**: `.../saml/idp`.
- IdP SSO endpoint: `.../saml/sso`.

Ba địa chỉ có ý nghĩa khác nhau. XML được cắt gọn để giải thích, chưa bao gồm chứng thư xác minh. Trong thực tế, ứng dụng phải đối chiếu issuer và chứng thư IdP từ nguồn metadata được quản trị tin cậy; không tin một XML bất kỳ chỉ vì URL có tên miền giống.

### 7.2. SP metadata có những gì?

Khi Spring Security xuất metadata SP cho registration `employee`, các trường quan trọng về mặt khái niệm là:

```xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="urn:example:portal:prod:sp">
    <md:SPSSODescriptor
        protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        <md:AssertionConsumerService
            index="0"
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
            Location="https://portal.example.test/login/saml2/sso/employee"/>
    </md:SPSSODescriptor>
</md:EntityDescriptor>
```

Đây là **minh họa rút gọn cấu trúc**; metadata thật có thể chứa certificate/chữ ký và nhiều endpoint. SP `entityID` không phải `employee`, còn `employee` chỉ xuất hiện như một phần của ACS URL theo cấu hình template.

Nếu IdP cần đăng ký mới, nên dùng **metadata SP được ứng dụng xuất ra ở môi trường đích** hoặc cung cấp chính xác SP Entity ID, ACS, certificate/binding mà IdP yêu cầu. Tránh tự gõ một “Entity ID trông giống URL đăng nhập” rồi để hai bên lệch nhau.

## 8. Cấu hình Java Spring Security cho đăng nhập SAML

Ví dụ cấu hình filter chain cho ứng dụng Servlet Spring Boot, với thư viện Spring Security SAML 2.0 Service Provider và các registration từ Boot.

Tệp `src/main/java/com/example/portal/SecurityConfig.java`:

```java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/assets/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
```

Giải thích:

- `saml2Login()` cấu hình luồng SAML 2.0 login của SP.
- `saml2Metadata()` cho phép công bố SP metadata để tích hợp/kiểm thử; URL mặc định tùy phiên bản/cấu hình nhưng các mẫu phổ biến là `/saml2/metadata` và `/saml2/metadata/{registrationId}`.
- `RelyingPartyRegistrationRepository` do Spring Boot cấu hình từ YAML nếu đủ metadata cần thiết. Spring Security dùng repository để tra registration và xử lý trust.
- Chương trình này **không có nút “Tài khoản nhân viên” cố định**. Nếu muốn nhãn hiển thị chính xác và bố cục tùy biến, phải xây UI đăng nhập riêng.
- Đây là lớp trong **dự án Spring Boot có dependencies**, không phải file Java biên dịch bằng JDK thuần. Để chạy được còn cần package/project build, IdP metadata hợp lệ và trust configuration.

### 8.1. Nếu tự tạo RelyingPartyRegistration bằng Java

Với Spring Security hiện đại, có thể dùng `RelyingPartyRegistrations.fromMetadataLocation(...).registrationId(...).entityId(...).build()` để tạo RP/AP pair. Một đoạn minh họa (trong lớp cấu hình đã có repository):

```java
RelyingPartyRegistration registration = RelyingPartyRegistrations
    .fromMetadataLocation(
        "https://sso.company.example.test/saml/metadata"
    )
    .registrationId("employee")
    .entityId("urn:example:portal:prod:sp")
    .build();
```

Đoạn này là **trích đoạn API**, không phải một class độc lập. Cách truy cập metadata và builder API có thể đổi theo phiên bản. Đối với triển khai thực tế cần xét credential SP, chính sách ký/yêu cầu xác minh và nguồn metadata đáng tin.

**Quan trọng:** builder `.registrationId("employee")` không tự quyết định `assertingParty.entityId`: thông tin IdP lấy từ metadata hoặc được cấu hình riêng. Việc dùng tên `employee` không có nghĩa IdP có issuer `employee`.

### 8.2. Cách đọc lại registration đã cấu hình

Các getter dưới đây giúp **quan sát giá trị logic** từ registration, không thay thế kiểm tra metadata/runtime:

```java
RelyingPartyRegistration r =
    repository.findByRegistrationId("employee");

String localRegistrationId = r.getRegistrationId();
String spEntityId = r.getEntityId();
String idpEntityId = r.getAssertingPartyMetadata().getEntityId();
String acsTemplate = r.getAssertionConsumerServiceLocation();
```

Đây là trích đoạn trong một method có biến `repository`, không phải chương trình standalone. Theo ngữ cảnh, một số trường có thể còn placeholder cần mở rộng hoặc URL phụ thuộc public base URL của request. Hãy so với metadata **đã được Spring xuất ra ở địa chỉ deploy thật**.

Không ghi trực tiếp các trường này trong log sản xuất kèm certificate riêng/secret/SAMLResponse chưa che thông tin; có thể log cấu hình định danh ở mức được kiểm soát để gỡ lỗi.

## 9. Thiết kế trang chọn nhà cung cấp đăng nhập

Giả sử ứng dụng có hai nút:

```text
+--------------------------------------+
|            Đăng nhập Portal          |
|                                      |
| [ Đăng nhập bằng tài khoản nhân viên ]|
| [ Đăng nhập bằng tài khoản đối tác  ] |
+--------------------------------------+
```

Mỗi nút phải chuyển đến **registrationId đúng**:

```html
<a href="/saml2/authenticate/employee">
  Đăng nhập bằng tài khoản nhân viên
</a>
<a href="/saml2/authenticate/partner">
  Đăng nhập bằng tài khoản đối tác
</a>
```

Đây là HTML minh họa: phải bảo đảm trang đăng nhập được phép truy cập khi chưa đăng nhập và liên kết tương ứng với `RelyingPartyRegistrationRepository`. Nếu sử dụng Spring MVC/Thymeleaf, có thể dựng danh sách từ cấu hình riêng của ứng dụng và render các link này. Mặc định `/saml2/authenticate/{registrationId}` là endpoint khởi tạo AuthnRequest, không phải IdP Entity ID.

Không xây URL từ **tên hiển thị chưa kiểm soát**. Nhãn UI phải ánh xạ tới một `registrationId` đã được cho phép; người dùng có thể chọn trong danh sách, nhưng **không được cấp quyền tự khai IdP metadata, issuer hoặc certificate mới**.

### 9.1. Mô hình dữ liệu UI đề xuất

Một record ứng dụng có thể lưu thông tin:

```text
LoginProviderOption:
  registrationId = employee
  displayName    = Đăng nhập bằng tài khoản nhân viên
  enabled        = true
  sortOrder      = 10
```

`displayName` có thể đa ngôn ngữ (`vi`, `en`), có thể chứa logo và mô tả ngắn. Đây là dữ liệu của sản phẩm, không ghi đè vào `EntityDescriptor/@entityID`.

Nếu dùng metadata từ IdP để gợi ý tên trong UI, phải xử lý tính xác thực metadata, tính nhất quán thương hiệu và encoding/HTML escaping. Nhãn động từ nguồn ngoài không được phép tạo HTML/script tùy ý.

## 10. Ví dụ Java 17 thuần: ba trường độc lập

Ví dụ sau biên dịch/chạy với JDK 17 trở lên, **không cần Spring Security**. Nó mô phỏng một registry giúp quan sát rằng tên hiển thị, mã registration và hai Entity ID được dùng cho những mục đích khác nhau. Hàm kiểm tra cuối chỉ so sánh chuỗi để dạy khái niệm, **không xác minh chữ ký SAML**.

Tệp `SamlRegistrationNamesDemo.java`:

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class SamlRegistrationNamesDemo {
    record Provider(
        String registrationId,
        String spEntityId,
        String idpEntityId,
        String displayName
    ) {
        String loginPath() {
            return "/saml2/authenticate/" + registrationId;
        }
    }

    static boolean matchesDeclaredIds(
            Provider provider,
            String responseIssuer,
            String audience) {
        return provider.idpEntityId().equals(responseIssuer)
            && provider.spEntityId().equals(audience);
    }

    public static void main(String[] args) {
        Map<String, Provider> registry = new LinkedHashMap<>();
        Provider employee = new Provider(
            "employee",
            "urn:example:portal:prod:sp",
            "https://sso.company.example.test/saml/idp",
            "Tài khoản nhân viên"
        );
        Provider partner = new Provider(
            "partner",
            "urn:example:portal:prod:sp",
            "https://login.partner.example.test/issuer",
            "Tài khoản đối tác"
        );
        registry.put(employee.registrationId(), employee);
        registry.put(partner.registrationId(), partner);

        System.out.println("lookup=" + registry.get("employee").displayName());
        System.out.println("loginPath=" + employee.loginPath());
        System.out.println("spEntityId=" + employee.spEntityId());
        System.out.println("idpEntityId=" + employee.idpEntityId());

        Provider relabeled = new Provider(
            employee.registrationId(),
            employee.spEntityId(),
            employee.idpEntityId(),
            "Đăng nhập SSO công ty"
        );
        System.out.println("sameRegistration="
            + employee.registrationId().equals(relabeled.registrationId()));
        System.out.println("sameSp="
            + employee.spEntityId().equals(relabeled.spEntityId()));
        System.out.println("labelChanged="
            + !employee.displayName().equals(relabeled.displayName()));

        System.out.println("issuerAndAudienceOk=" + matchesDeclaredIds(
            employee,
            "https://sso.company.example.test/saml/idp",
            "urn:example:portal:prod:sp"
        ));
        System.out.println("wrongIdpIssuer=" + matchesDeclaredIds(
            employee,
            partner.idpEntityId(),
            employee.spEntityId()
        ));
        System.out.println("wrongSpAudience=" + matchesDeclaredIds(
            employee,
            employee.idpEntityId(),
            "urn:example:other:sp"
        ));
    }
}
```

Chạy:

```bash
javac SamlRegistrationNamesDemo.java
java SamlRegistrationNamesDemo
```

Stdout chính xác:

```text
lookup=Tài khoản nhân viên
loginPath=/saml2/authenticate/employee
spEntityId=urn:example:portal:prod:sp
idpEntityId=https://sso.company.example.test/saml/idp
sameRegistration=true
sameSp=true
labelChanged=true
issuerAndAudienceOk=true
wrongIdpIssuer=false
wrongSpAudience=false
```

Ý nghĩa:

1. `registry.get("employee")` dùng **registrationId** để lấy bản cấu hình.
2. `loginPath()` tạo **đường dẫn khởi động SAML** bằng registrationId.
3. `spEntityId` và `idpEntityId` vẫn là giá trị URI của hai thực thể SAML.
4. Đổi `displayName` không làm đổi registrationId hay SP Entity ID.
5. Issuer của **IdP đối tác** không được nhận như issuer của IdP nhân viên.
6. Audience của SP khác không được xem là audience của ứng dụng hiện tại.

Hàm `matchesDeclaredIds` **không đủ làm hệ thống xác thực SAML thực tế**. Nó không kiểm tra chữ ký, certificate, binding, Recipient/Destination, SubjectConfirmation, thời gian, `InResponseTo` hoặc chống replay. Spring Security/OpenSAML phải thực hiện những việc đó sau khi chọn đúng registration.

## 11. Đổi giá trị nào thì phải sửa ở đâu?

| Thay đổi | Ảnh hưởng chính | Nơi cần kiểm tra/cập nhật |
| --- | --- | --- |
| Đổi displayName | Nội dung nút, bản dịch, logo | UI config/template, nội dung, test giao diện |
| Đổi registrationId | Tra cứu repository, login URL, ACS/metadata URL có placeholder | Source config, link UI, endpoint/route, IdP ACS nếu URL đổi, SAML state đang chạy |
| Đổi SP Entity ID | `AuthnRequest/Issuer`, SAML audience, SP metadata và hợp đồng với IdP | SP config, IdP SP registration, metadata, kiểm thử issuer/audience |
| Đổi IdP Entity ID | Giá trị issuer được SP tin, IdP metadata/trust | Asserting-party metadata, xác minh issuer/certificate, định danh liên kết user nếu sử dụng IdP issuer |
| Đổi IdP SSO URL | Địa điểm gửi AuthnRequest | IdP metadata/endpoint, binding, network |
| Đổi SP ACS URL | Địa điểm nhận SAML Response | SP route/metadata, IdP ACS allowlist, Destination/Recipient |
| Xoay certificate | Khóa dùng ký/xác minh hoặc mã hóa/giải mã | SP/IdP trust credentials, overlap keys, chính sách rotation; Entity ID thường giữ nguyên |
| Đổi provider thương mại | Có thể ảnh hưởng IdP Entity ID, certificate, SSO URL và subject | Đánh giá migration đầy đủ, không chỉ đổi displayName |

### 11.1. Ví dụ: chỉ đổi nhãn

Trước:

```text
registrationId = employee
spEntityId     = urn:example:portal:prod:sp
idpEntityId    = https://sso.company.example.test/saml/idp
displayName    = Corporate SSO
```

Sau:

```text
registrationId = employee
spEntityId     = urn:example:portal:prod:sp
idpEntityId    = https://sso.company.example.test/saml/idp
displayName    = Đăng nhập bằng tài khoản nhân viên
```

Đây là **thay đổi giao diện**. Không phải một cấu hình IdP/SP mới; không cần xoay certificate hoặc đăng ký lại Entity ID nếu mọi thông số giao thức giữ nguyên.

### 11.2. Ví dụ: đổi registrationId nhưng Entity ID cố định

Trước:

```text
registrationId = employee
spEntityId     = urn:example:portal:prod:sp
acs            = .../login/saml2/sso/employee
```

Sau:

```text
registrationId = staff
spEntityId     = urn:example:portal:prod:sp
acs            = .../login/saml2/sso/staff
```

SP Entity ID giữ nguyên, nhưng ACS có thể đổi vì template chứa registrationId. IdP phải chấp nhận ACS mới và ứng dụng phải cập nhật login links. Không chỉ đổi key YAML rồi bỏ qua metadata.

### 11.3. Ví dụ: đổi registrationId làm thay Entity ID theo template

Nếu SP dùng:

```text
entityId = {baseUrl}/saml2/service-provider-metadata/{registrationId}
```

thì tại `https://portal.example.test`:

```text
employee -> https://portal.example.test/saml2/service-provider-metadata/employee
staff    -> https://portal.example.test/saml2/service-provider-metadata/staff
```

Trong trường hợp này, đổi registrationId **đồng thời tạo SP Entity ID mới**, vì chính template đã ràng buộc hai trường. Phải phối hợp lại SP registration/Audience với IdP. Khi SP cần Entity ID không đổi qua lần đổi key local, cân nhắc khai báo Entity ID **cố định** và quản lý ACS/metadata độc lập.

## 12. Đa IdP và nhiều môi trường

### 12.1. Cùng IdP, nhiều ứng dụng SP

Giả sử cùng IdP doanh nghiệp phục vụ Portal và Payroll:

```text
IdP entityId = https://sso.company.example.test/saml/idp

Portal SP entityId  = urn:example:portal:prod:sp
Payroll SP entityId = urn:example:payroll:prod:sp
```

Hai ứng dụng có thể đặt `registrationId=employee` **giống nhau trong repository riêng** mà không xung đột: registrationId chỉ có phạm vi cục bộ. Nhưng SAML assertion dành cho Portal không được đưa sang Payroll, vì **AudienceRestriction và các điều kiện xác minh** hướng tới SP cụ thể.

### 12.2. Cùng ứng dụng, nhiều IdP

Một ứng dụng có hai registration:

```text
employee -> IdP công ty, certificate A, displayName "Tài khoản nhân viên"
partner  -> IdP đối tác, certificate B, displayName "Tài khoản đối tác"
```

Mỗi IdP có entityId và nguồn metadata được tin cậy riêng. Không chọn IdP theo displayName từ query string tự do. Không ghép sai certificate A cho issuer B. Không tự tải metadata từ URL do người gọi truyền vào rồi chấp nhận khóa ký mới không qua quản trị.

### 12.3. DEV, UAT, PROD

Các môi trường có thể dùng registrationId giống nhau, ví dụ `employee`, nếu repository độc lập. SP Entity ID và ACS phải đúng hợp đồng môi trường:

```text
DEV:  SP entityId = urn:example:portal:dev:sp
UAT:  SP entityId = urn:example:portal:uat:sp
PROD: SP entityId = urn:example:portal:prod:sp
```

Đây là ví dụ quy ước, không phải cú pháp SAML bắt buộc. Cần tách certificate, metadata/IdP registration, domain và callback theo chính sách. Không được để assertion cho DEV chấp nhận tại PROD chỉ vì hai môi trường cùng `registrationId=employee`.

Tên hiển thị có thể giống nhau giữa các môi trường nếu UI có ngữ cảnh rõ, nhưng nên tránh người dùng nhầm môi trường khi thực hiện thao tác nhạy cảm.

## 13. Lỗi vận hành thường gặp

### 13.1. Dùng tên hiển thị làm registrationId

**Sai lầm:** nút ghi `"Đăng nhập bằng SSO nhân viên"` và code gọi:

```text
/saml2/authenticate/Đăng nhập bằng SSO nhân viên
```

Nếu registration thật là `employee`, repository không tìm ra cấu hình, hoặc URL bị encode/route không đúng. **Cách sửa:** tách `displayName` khỏi `registrationId`, chỉ đặt link từ key đã đăng ký.

### 13.2. Đặt registrationId bằng IdP Entity ID

**Sai lầm:** dùng nguyên `https://idp.example.test/saml/idp` làm `registrationId` rồi nhét vào path. Về mặt khái niệm đây là định danh khác mục đích; trong URL nó còn tạo ký tự cần encoding. **Cách sửa:** đặt registration key gọn như `employee`, giữ IdP Entity ID ở asserting-party metadata/trust.

### 13.3. Cho rằng registrationId là SAML Issuer

**Sai lầm:** IdP đăng ký SP Entity ID bằng `employee`, trong khi `AuthnRequest/Issuer` thật là `urn:example:portal:prod:sp`. IdP có thể báo unknown SP/invalid issuer. **Cách sửa:** lấy **SP Entity ID thực tế từ SP metadata** và cung cấp cho IdP.

### 13.4. Cho rằng metadata URL chính là IdP Entity ID

**Sai lầm:** IdP metadata tải từ `https://sso.example.test/metadata`, nhưng XML khai báo `entityID="https://sso.example.test/issuer"`. Nếu SP kỳ vọng `/metadata` làm issuer, Response có thể bị từ chối. **Cách sửa:** đối chiếu `EntityDescriptor/@entityID`; đừng suy từ URL tải XML.

### 13.5. Đổi logo/brand rồi đổi Entity ID theo

**Sai lầm:** nhà cung cấp được đổi tên trên giao diện và kỹ sư đồng thời thay `entity-id` trong Spring. SAML audience hoặc issuer trở nên không khớp. **Cách sửa:** branding/UI là thay đổi displayName; chỉ sửa Entity ID khi IdP/SP thực sự thay đổi hợp đồng.

### 13.6. Đổi registrationId nhưng không cập nhật ACS

**Sai lầm:** đổi `employee` thành `staff` trong YAML; IdP vẫn POST tới `.../employee` hoặc từ chối ACS mới. **Cách sửa:** đối chiếu `acs.location`, metadata và allowlist của IdP; kiểm thử cả SP-initiated lẫn IdP-initiated nếu có.

### 13.7. Metadata xuất host nội bộ sau reverse proxy

Nếu `{baseUrl}` phát ra `http://service:8080` thay vì `https://portal.example.test`, ACS/Entity ID dạng template có thể sai. **Cách sửa:** cấu hình public base URL/forwarded headers từ proxy đáng tin, kiểm tra metadata được xuất ra tại URL công khai; ngăn phía ngoài tự giả mạo proxy headers.

### 13.8. Nhầm đăng nhập với phân quyền

Nút “Admin SSO” không làm người dùng trở thành admin; một SAML Response hợp lệ còn cần ánh xạ principal sang tài khoản nội bộ và kiểm tra quyền trên dữ liệu. **Cách sửa:** phân quyền dựa trên danh tính đã xác minh, membership, policy của ứng dụng và quyền đối tượng; không dùng label làm nguồn quyền.

### 13.9. Nhận Response chỉ vì URL có registrationId đúng

Attacker có thể gọi `/login/saml2/sso/employee` với SAMLResponse tự tạo. **Cách sửa:** dùng validation đầy đủ của Spring Security/OpenSAML: khóa xác minh của đúng IdP, issuer, audience, destination/recipient, thời gian, correlation và replay.

## 14. Phương pháp kiểm tra trong một lần tích hợp thật

Thực hiện với một registration, ví dụ `employee`:

1. **Đọc cấu hình local**: xác nhận key `registrationId=employee` trong `spring.security.saml2.relyingparty.registration` hoặc repository custom.
2. **Đọc metadata IdP từ nguồn đã được duyệt**: ghi lại `EntityDescriptor/@entityID`, SSO URL, binding, certificate.
3. **Đọc metadata SP được ứng dụng xuất**: ghi lại `EntityDescriptor/@entityID`, ACS URL, certificate/binding. Với `saml2Metadata()`, có thể dùng `/saml2/metadata/employee` nếu phiên bản/cấu hình hỗ trợ.
4. **Đọc cấu hình ứng dụng ở IdP**: SP Entity ID và ACS allowlist phải khớp metadata SP; chính sách ký yêu cầu phải tương thích.
5. **Kiểm tra link người dùng bấm**: nút “Tài khoản nhân viên” phải trỏ `/saml2/authenticate/employee`.
6. **Kiểm tra AuthnRequest** bằng công cụ phân tích SAML có kiểm soát: Issuer là SP Entity ID, Destination là IdP SSO endpoint; không nhầm `employee` với issuer.
7. **Kiểm tra SAML Response** bằng validation của framework: issuer là IdP Entity ID, audience là SP Entity ID, cùng signature, destination/recipient, correlation, thời hạn và replay.
8. **Kiểm tra user mapping**: khi đã xác thực, `NameID`/attributes đúng người dùng và không tự đồng nhất user khác chỉ vì trùng email.
9. **Kiểm tra thay đổi thử nghiệm**: đổi displayName mà không đổi registration/Entity ID phải giữ nguyên luồng; đổi registrationId hoặc Entity ID ở môi trường thử nghiệm phải thể hiện đúng tác động đến link/metadata.
10. **Kiểm tra nhật ký an toàn**: có thể ghi registration key và mã lỗi validation theo chính sách, nhưng không ghi toàn bộ SAMLResponse, assertion chứa dữ liệu nhạy cảm, khóa riêng hoặc secret ra log.

### 14.1. Ma trận kiểm thử

| Trường hợp | Thiết lập / thao tác | Kỳ vọng |
| --- | --- | --- |
| Chọn đúng provider | Bấm nhãn nhân viên ánh xạ tới `employee` | Bắt đầu AuthnRequest bằng registration nhân viên |
| Chọn nhầm link | Nhãn nhân viên lại trỏ `partner` | Test UI thất bại; sửa mapping nhãn–registration |
| Đổi nhãn | `displayName` thay, các ID giữ nguyên | Login URL/trust không đổi |
| registrationId không tồn tại | Truy cập `/saml2/authenticate/unknown` | Không khởi tạo federation với IdP chưa cấu hình |
| SP Entity ID sai | AuthnRequest Issuer lệch SP đăng ký tại IdP | IdP từ chối theo chính sách |
| IdP Entity ID sai | Response/Assertion từ issuer không tin cậy | Spring Security/SP từ chối |
| Audience sai | Assertion dành cho SP khác | SP từ chối |
| Chữ ký sai | Issuer/audience trông đúng nhưng signature không hợp lệ | SP từ chối |
| Đổi registration key, Entity ID cố định | `employee` -> `staff` | SAML trust ID giữ nguyên; phải cập nhật URL có placeholder |
| Đổi registration key, Entity ID template | ID chứa `{registrationId}` | SP Entity ID sau mở rộng đổi; cần cập nhật IdP |
| Reverse proxy | Base URL nội bộ khác public URL | Metadata/ACS cuối cùng dùng public URL được tin cậy |
| Hai IdP | `employee` và `partner` có issuer/certificate khác | Không chấp nhận Response của A trong trust của B |
| Hai ứng dụng cùng registrationId | Mỗi app có repository riêng; SP IDs khác | Không có collision cục bộ; audience vẫn phân biệt |
| IdP-initiated SSO | IdP gửi Response không do SP vừa khởi tạo | Chỉ hỗ trợ khi profile/chính sách được thiết kế và validation phù hợp |

Một bài kiểm thử **chỉ xem nút đăng nhập có hoạt động hay không** chưa đủ: cần negative tests cho issuer, audience, chữ ký, ACS, thời gian và kết quả liên kết người dùng.

## 15. Checklist chọn giá trị ngay từ đầu

- [ ] Mỗi registration trong một repository có `registrationId` duy nhất, dễ đọc, ổn định và an toàn để đặt trong URL.
- [ ] Đã ghi rõ **SP Entity ID** riêng với **IdP Entity ID** trong tài liệu cấu hình liên kết.
- [ ] SP Entity ID được đối chiếu từ metadata mà ứng dụng thật sự phát hành, IdP Entity ID từ metadata/contract IdP đáng tin.
- [ ] Không nhầm metadata URL, SSO URL, ACS URL hoặc NameID với Entity ID.
- [ ] Đã xác định `entityId` có chứa `{registrationId}` hay không, để biết tác động khi đổi registration key.
- [ ] Nhãn nút đăng nhập là dữ liệu UI riêng, ánh xạ sang registration key đã được cho phép.
- [ ] Nút từng IdP dẫn đến đúng endpoint và chứng thư/trust của registration tương ứng.
- [ ] Cấu hình proxy/public URL, ACS và IdP allowlist đã đồng bộ cho đúng môi trường.
- [ ] Có quy trình cập nhật metadata/certificate khi thay đổi issuer/entity ID/endpoint hoặc certificate.
- [ ] Cấu hình chống response/assertion giả, replay, sai issuer/audience và thiếu quyền nghiệp vụ vẫn hoạt động.
- [ ] Có test tự động cho nhãn UI, link, registration lookup, metadata values, SAML negative cases.
- [ ] Không dùng registrationId hoặc tên hiển thị làm khóa tài khoản người dùng hoặc nguồn phân quyền.

## 16. Tự kiểm tra kiến thức

**Câu 1.** Ứng dụng có `registrationId=corp`, SP `entityId=urn:example:app:sp`. IdP phải đăng ký SP identifier nào?

**Trả lời:** `urn:example:app:sp`, theo hợp đồng/metadata SP; `corp` là key Spring và thường chỉ dùng trong URL tìm registration.

**Câu 2.** Người dùng bấm nút “SSO công ty”, nhưng YAML khai `registrationId=employee`. Đường dẫn khởi tạo mặc định nên dùng giá trị nào?

**Trả lời:** `/saml2/authenticate/employee`; tên nút là `SSO công ty` và không cần xuất hiện trong URL.

**Câu 3.** Đổi tên hiển thị từ “SSO công ty” thành “Tài khoản nhân viên” có làm SAML Response không hợp lệ không?

**Trả lời:** Thông thường không nếu chỉ đổi text UI; Entity ID, endpoint, trust config và mapping không đổi.

**Câu 4.** Đổi `registrationId` có luôn làm đổi SP Entity ID không?

**Trả lời:** Không. Chỉ gián tiếp khi SP entity ID template phụ thuộc `{registrationId}`; dù không đổi entity ID, các URL có placeholder có thể đổi.

**Câu 5.** Nếu IdP metadata được tải tại `/metadata`, thì `/metadata` là IdP entityId?

**Trả lời:** Không thể kết luận. Phải đọc giá trị `EntityDescriptor/@entityID` trong metadata đáng tin.

**Câu 6.** Có thể dùng cùng `registrationId=employee` cho Portal và Payroll không?

**Trả lời:** Có, nếu mỗi ứng dụng có repository riêng. SP Entity ID và assertion audience vẫn phải phân biệt đúng ứng dụng được phục vụ.

**Câu 7.** SAML Response khai đúng IdP Entity ID nhưng chữ ký sai thì có thể nhận đăng nhập không?

**Trả lời:** Không. Entity ID chỉ là một phần của trust check; xác minh chữ ký và các điều kiện SAML khác vẫn bắt buộc.

**Câu 8.** Tại sao “Admin Login” không phải bằng chứng người dùng có quyền admin?

**Trả lời:** Đó chỉ là display name. Quyền phát sinh từ người dùng được xác thực và kiểm tra nghiệp vụ, không phải văn bản nút đăng nhập.

**Câu 9.** Một registration có bao nhiêu entityId đáng quan tâm?

**Trả lời:** Ít nhất phải phân biệt **SP Entity ID** và **IdP Entity ID** của cặp RP–AP. Spring Boot `registration.<id>.entity-id` chỉ SP, còn IdP issuer nằm trong asserting-party metadata/config.

**Câu 10.** Khi di chuyển môi trường sang hostname mới, bước kiểm tra ưu tiên là gì?

**Trả lời:** Đối chiếu metadata SP thực tế và các template `{baseUrl}`/`{registrationId}` với SP Entity ID, ACS và cấu hình IdP; tránh dùng URL nội bộ do reverse proxy.

## Nguồn tham khảo kỹ thuật

- Spring Security, **SAML 2.0 Login Overview** — `RelyingPartyRegistration`, `registrationId`, URI patterns: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security, **SAML 2.0 Metadata** — nhập metadata IdP, xuất metadata SP: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security, **Producing AuthnRequests** — endpoint và bảo vệ luồng khởi tạo: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security, **Authenticating Responses** — xử lý và chọn registration khi nhận Response: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security, **RelyingPartyRegistration API**: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html
- OASIS, **SAML 2.0 Metadata** — `EntityDescriptor/@entityID`, role descriptor và endpoint: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf

**Ghi nhớ:** `registrationId` là khóa tìm cấu hình của Spring Security; **SP/IdP Entity ID** là định danh giao thức dùng để xác lập và kiểm tra quan hệ tin cậy; **displayName** là nhãn do ứng dụng hiển thị cho người dùng. Ghi đúng ba giá trị, hiểu khi nào chúng phụ thuộc vào template URL và kiểm thử đồng bộ metadata/endpoint giúp tránh phần lớn sự cố đăng ký SAML2.