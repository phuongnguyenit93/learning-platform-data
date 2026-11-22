# NameIDPolicy và thỏa thuận định dạng định danh với IdP

> **Module:** Spring Security – federation. **Chủ đề cha:** Tùy chỉnh AuthnRequest. Bài học tập trung vào phần tử `<samlp:NameIDPolicy>` trong SAML 2.0, cách chọn định dạng định danh giữa Service Provider (SP) và Identity Provider (IdP), cấu hình Spring Security và kiểm tra kết quả SSO thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **`NameIDPolicy` trong AuthnRequest** với **`NameID` trong Assertion/Subject** và với khóa định danh tài khoản nội bộ của ứng dụng.
2. Hiểu ba thuộc tính `Format`, `SPNameQualifier`, `AllowCreate`, trường hợp nên bỏ từng thuộc tính và các giới hạn theo SAML Core/Errata.
3. So sánh `persistent`, `transient`, `emailAddress`, `unspecified`, đặc biệt về tính bền vững, tính duy nhất, phạm vi và quyền riêng tư.
4. Thỏa thuận với IdP một “identity contract” có thể kiểm thử được: issuer, SP entity ID, NameID format, qualifiers, account mapping, lifecycle, migration và error behavior.
5. Tùy chỉnh AuthnRequest theo registration bằng `OpenSaml4AuthenticationRequestResolver` trên Spring Boot 3.3/Spring Security 6.3 mà vẫn giữ kiểm tra an ninh SAML.
6. Kiểm chứng **định danh IdP thật sự phát hành** sau khi Response/Assertion đã được xác minh, không coi việc SP gửi NameIDPolicy là điều kiện đủ.
7. Nhận diện lỗi tương tác với IdP, các trường hợp không thể dùng NameID làm khóa tài khoản lâu dài và cách xử lý an toàn.

## 2. Tình huống điển hình

Ứng dụng **Partner Orders Portal** dùng SAML SSO. Nhân viên của Đối tác A cần quay lại đúng tài khoản nội bộ, kể cả khi họ đổi email. Ở lần đăng nhập đầu, IdP phát:

~~~xml
<saml:NameID
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:transient">
    _tmp_7a31
</saml:NameID>
~~~

Lần đăng nhập tiếp theo, IdP lại phát `_tmp_b22c`. Hai Assertion có thể đều hợp lệ; nhưng **SP không thể nhận diện ổn định cùng một user bằng NameID transient**. Nếu dùng giá trị đó làm khóa tài khoản, ứng dụng có thể tạo tài khoản mới cho mỗi lần SSO hoặc không tìm được quyền cũ.

Một hướng khác là yêu cầu IdP phát `persistent` NameID. Tuy nhiên, chỉ gửi `NameIDPolicy Format=persistent` không làm IdP tự động cam kết thay đổi: IdP có thể không hỗ trợ, yêu cầu cấu hình riêng, trả lỗi hoặc triển khai cách diễn giải riêng. Do đó phải có ba lớp:

1. **Thỏa thuận trước với IdP:** định dạng, nguồn giá trị, phạm vi, tính ổn định, thời gian tồn tại, migration.
2. **Yêu cầu qua giao thức:** khi phù hợp, đặt `NameIDPolicy` vào AuthnRequest bằng API chuẩn của Spring Security/OpenSAML.
3. **Xác nhận sau đăng nhập:** chỉ xử lý NameID **trong Assertion đã được xác minh**, kiểm tra format/scope và liên kết với local user theo chính sách.

**Thông điệp cốt lõi:** `NameIDPolicy` là **điều SP đề nghị IdP làm**; `Subject/NameID` trong Assertion hợp lệ là **điều IdP đã thực sự khẳng định**; quyền ứng dụng là **điều SP tự quyết định**.

## 3. Vị trí của NameIDPolicy trong SAML2 Web Browser SSO

~~~text
Browser                SP (Spring Security)              IdP
   |                           |                            |
   | GET /private              |                            |
   |-------------------------->|                            |
   |                           | Build AuthnRequest         |
   |                           | - Issuer = SP entity ID    |
   |                           | - NameIDPolicy             |
   |                           | - ACS + ID + timing        |
   |<------ Redirect/POST -----|                            |
   |--------------------- SAMLRequest --------------------->|
   |                           |                 Authenticate|
   |<-------------------- SAMLResponse ---------------------|
   | POST ACS                  |                            |
   |-------------------------->| Validate signature,        |
   |                           | issuer, time, audience,     |
   |                           | recipient, InResponseTo     |
   |                           | then Subject/NameID        |
   |                           | Link local user + authorize|
   |<------ SP session --------|                            |
~~~

SAML2 dùng hai XML namespace:

| Đối tượng | Namespace | Ý nghĩa |
| --- | --- | --- |
| `<samlp:AuthnRequest>` | `urn:oasis:names:tc:SAML:2.0:protocol` | Thông điệp yêu cầu xác thực mà SP gửi đi. |
| `<samlp:NameIDPolicy>` | `urn:oasis:names:tc:SAML:2.0:protocol` | Mong muốn về định dạng/phạm vi identifier. |
| `<saml:Assertion>` | `urn:oasis:names:tc:SAML:2.0:assertion` | Khẳng định do IdP phát hành. |
| `<saml:Subject>` | `urn:oasis:names:tc:SAML:2.0:assertion` | Chủ thể của lời khẳng định. |
| `<saml:NameID>` | `urn:oasis:names:tc:SAML:2.0:assertion` | Identifier IdP thực sự phát cho chủ thể. |

`NameIDPolicy` là phần tử **không bắt buộc** của AuthnRequest; nó **không nằm trong Assertion**. Nếu SP không gửi nó, IdP thường dùng cấu hình ứng dụng SAML hoặc hợp đồng đã thiết lập để chọn format. Không có NameIDPolicy không đồng nghĩa SP được bỏ kiểm tra NameID trong Assertion.

### Ví dụ AuthnRequest có NameIDPolicy

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req-a42"
    Version="2.0"
    IssueInstant="2030-05-01T10:00:00Z"
    Destination="https://idp.partner.example/saml/sso"
    AssertionConsumerServiceURL="https://sp.example/login/saml2/sso/partner">
    <saml:Issuer>https://sp.example/saml2/sp/partner</saml:Issuer>
    <samlp:NameIDPolicy
        Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
        SPNameQualifier="https://sp.example/saml2/sp/partner"
        AllowCreate="true"/>
</samlp:AuthnRequest>
~~~

XML này **chỉ minh họa cấu trúc, chưa ký số và không dùng để đăng nhập thật**. Một request dùng HTTP-Redirect Binding có thể được mã hóa bằng DEFLATE, Base64 và URL encoding; chữ ký Redirect Binding cũng có quy tắc riêng. Khi dùng Spring Security, để resolver tạo và sửa OpenSAML object **trước bước serialization/signing**, không tự chỉnh chuỗi XML request sau khi ký.

### Ba cấp ràng buộc khác nhau

- **Tên SP (`Issuer`):** SP là thực thể nào đang yêu cầu đăng nhập.
- **`NameIDPolicy`:** mong nhận định danh ở định dạng/ngữ cảnh nào.
- **Các điều kiện response:** IdP có thực sự trả một Assertion dành cho đúng SP, còn hạn và hợp lệ không? SP phải kiểm tra những điều này **độc lập** với NameIDPolicy.

Không nhầm `NameIDPolicy` với `RequestedAuthnContext`: RequestedAuthnContext nói tới **ngữ cảnh/phương thức xác thực**, không nói tới định dạng định danh.

## 4. Ba thuộc tính của NameIDPolicy

### 4.1. Format

`Format` là URI mô tả loại identifier SP muốn IdP dùng khi biểu diễn subject trong Assertion.

~~~xml
<samlp:NameIDPolicy
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"/>
~~~

Không nhầm `Format` với chính giá trị `NameID`: URI `persistent` không chứa username, còn NameID value thực tế có thể là một chuỗi giả danh như `p-6f91`.

Khi IdP không đáp ứng được, nó có thể trả Status code liên quan `InvalidNameIDPolicy` hoặc cách phản hồi khác theo sản phẩm/profile. **Không có bảo đảm mọi IdP sẽ tự động thực hiện yêu cầu trong mọi môi trường**. Cần kiểm tra khả năng tương tác với đúng IdP, đúng tenant và đúng cấu hình SAML application.

### 4.2. SPNameQualifier

`SPNameQualifier` cho biết ngữ cảnh **SP hoặc SP affiliation** mà identifier mong muốn gắn với. Nó thường đặc biệt quan trọng với định danh persistent/pairwise trong liên kết giữa nhiều bên.

~~~xml
<samlp:NameIDPolicy
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
    SPNameQualifier="https://sp.example/saml2/sp/partner"/>
~~~

Cần nhớ:

- Không tự coi `SPNameQualifier` là ACS endpoint. **ACS là URL nhận SAMLResponse**, còn SPNameQualifier chỉ ngữ cảnh identifier.
- Có thể dùng SP entity ID hoặc một affiliation ID **nếu và chỉ nếu IdP–SP đã thỏa thuận**.
- Một số IdP không hỗ trợ hoặc không yêu cầu field này. Với họ, thêm qualifier có thể khiến request bị từ chối.
- Trong `<saml:NameID>` phản hồi, `NameQualifier` thường liên quan bên cung cấp định danh (IdP) và `SPNameQualifier` liên quan phạm vi SP/affiliation; các thuộc tính có thể vắng mặt theo format/profile. Không đoán giá trị thiếu nếu cần ràng buộc security.
- Không cho trình duyệt tự cung cấp SPNameQualifier để “chọn” issuer/tenant/permission khác; lấy từ registration tin cậy.

### 4.3. AllowCreate

`AllowCreate` là Boolean chỉ việc SP cho phép IdP tạo hoặc liên kết identifier phục vụ relying party trong lúc thực hiện request. **SAML 2.0 Approved Errata 05** đã làm rõ ý nghĩa này.

| Giá trị | Ý nghĩa cần hiểu | Không có nghĩa |
| --- | --- | --- |
| `true` | Cho phép IdP tạo/thiết lập liên kết identifier mới khi cần, tùy chính sách và profile. | Tạo user local, tự động JIT provision, tự cấp permission. |
| `false` | SP mong IdP chỉ dùng định danh/liên kết đã được thiết lập phù hợp, nếu ngữ cảnh áp dụng. | Chắc chắn IdP không có thao tác cấp identifier ở mọi trường hợp. |
| Không có thuộc tính | Theo errata, mặc định `false`. | Mọi IdP đều tuân chính xác cùng một hành vi triển khai. |

Theo errata, trong trường hợp **Format=transient**, **MUST NOT dùng `AllowCreate`**. Transient identifier vốn không duy trì sự liên kết bền vững theo ngữ nghĩa này. Ví dụ **không hợp lệ về chính sách sử dụng**:

~~~xml
<!-- SAI: khong dung AllowCreate voi transient -->
<samlp:NameIDPolicy
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:transient"
    AllowCreate="true"/>
~~~

**Cẩn thận với triển khai thực tế:** Microsoft Entra ID công bố `AllowCreate` bị bỏ qua trong cách xử lý SAML NameIDPolicy của họ. Đây là một minh họa rằng **hợp đồng giao thức phải được thử với IdP cụ thể**, không chỉ xem thuộc tính có tên hợp lý.

**AllowCreate và Just-in-Time provisioning khác nhau.** IdP được phép tạo identifier không có quyền tạo local account trong database SP; logic tạo user, gán tenant và cấp quyền là quy trình riêng phải được ứng dụng kiểm soát.

## 5. So sánh các định dạng NameID

| Định dạng | Format URI đúng | Đặc trưng | Khóa tài khoản lâu dài? |
| --- | --- | --- | --- |
| **persistent** | `urn:oasis:names:tc:SAML:2.0:nameid-format:persistent` | Định danh bền vững theo quan hệ IdP–SP/affiliation, thường pseudonymous. | **Có thể**, khi issuer/scope/lifecycle được IdP bảo đảm. |
| **transient** | `urn:oasis:names:tc:SAML:2.0:nameid-format:transient` | Định danh tạm cho một ngữ cảnh SSO, không bảo đảm lặp lại. | **Không**, nếu chỉ dựa vào NameID. |
| **emailAddress** | `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress` | Định danh biểu diễn dạng email. | Không nên mặc định; email đổi hoặc tái sử dụng. |
| **unspecified** | `urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified` | Không quy định cú pháp/ý nghĩa trong URI. | Chỉ khi hợp đồng định rõ tính bền vững/duy nhất. |
| **entity** | `urn:oasis:names:tc:SAML:2.0:nameid-format:entity` | Định danh SAML entity, không mặc định là người dùng. | Không phải lựa chọn mặc định cho người dùng. |
| **X509SubjectName** | `urn:oasis:names:tc:SAML:1.1:nameid-format:X509SubjectName` | Tên chủ thể theo cú pháp X.509. | Chỉ trong profile/ứng dụng đặc thù. |

Chú ý **emailAddress** và **unspecified** vẫn dùng URI namespace **SAML:1.1** dù SAML 2.0 sử dụng chúng. Không “sửa” thành `SAML:2.0` chỉ vì đang cấu hình SAML 2.0.

### 5.1. Persistent không có nghĩa toàn cục

~~~text
IdP A + SP Orders:   subject persistent = "p-4af2"
IdP A + SP Payroll:  subject persistent = "p-729c"
IdP B + SP Orders:   subject persistent = "p-4af2"
~~~

Ba chuỗi trên **không tự chứng minh bất kỳ cặp nào là cùng một người**. Một người ở IdP A có thể có pairwise identifier khác nhau ở hai SP; hai IdP khác nhau có thể phát cùng một chuỗi nhưng trỏ hai người hoàn toàn khác nhau.

SP cần một key theo **nguồn + phạm vi** như `IdP entity ID + NameID Format + qualifiers/SP scope + NameID value`, có thể kèm registration/tenant context theo hợp đồng. Không khóa chỉ bằng `NameID value` hoặc email.

### 5.2. Transient và bài toán liên kết tài khoản

~~~text
Login #1: NameID transient = "T-089f"
Login #2: NameID transient = "T-5dc2"
~~~

Kể cả đăng nhập cùng một tài khoản IdP, hai NameID có thể khác nhau. Nếu ứng dụng cần lưu giỏ hàng, đơn hàng, vai trò hoặc lịch sử dài hạn, hãy dùng một **external identifier khác đã được chứng minh ổn định** hoặc thương lượng persistent NameID. Không ghép hai lần login theo email một cách âm thầm để chữa lỗi.

### 5.3. EmailAddress thường thuận tiện nhưng không bất biến

Một người đổi tên miền công ty, email hoặc được chuyển bộ phận có thể có NameID email khác trước. Một địa chỉ email cũ cũng có thể được cấp lại cho người khác. Vì vậy `emailAddress` hữu ích cho hiển thị/liên hệ nhưng không phải lựa chọn mặc định cho khóa identity có quyền truy cập dữ liệu nhạy cảm.

Nếu IdP chỉ hỗ trợ emailAddress, cần hợp đồng về uniqueness, xác minh, tái sử dụng, đổi giá trị, thông báo/deprovision và quy trình migration. Ngay cả khi email được IdP khẳng định trong assertion đã ký, **chữ ký không tự khiến email trở thành immutable ID**.

### 5.4. Unspecified không phải “không có định danh”

Một IdP có thể phát `NameID Format=unspecified` nhưng nội dung là ID directory ổn định. IdP khác cũng dùng unspecified nhưng giá trị là username có thể tái sử dụng. SP không thể suy ngữ nghĩa từ URI này; phải có **cam kết rõ ràng về nội dung, phạm vi và lifecycle**.

### 5.5. Quy tắc chọn format

1. Cần local user bền vững → ưu tiên `persistent` hoặc một immutable attribute có trust contract đầy đủ.
2. Chỉ cần xác thực cho một phiên, không link user xuyên phiên bằng NameID → `transient` có thể phù hợp.
3. Cần email để hiển thị/thông báo → có thể nhận qua Attribute riêng; tách khỏi external ID dùng cho authorization.
4. IdP chỉ hỗ trợ `unspecified` → yêu cầu văn bản xác nhận ý nghĩa kỹ thuật và thử nhiều lượt login.
5. Multi-tenant/multi-IdP → luôn lưu nguồn issuer và phạm vi identifier để tránh nhầm người dùng.

## 6. Thỏa thuận định danh với IdP

Không nên coi NameIDPolicy là “cấu hình một phía”. SP cần thống nhất với đội quản trị IdP các điểm có thể kiểm tra bằng test.

| Nội dung | Câu hỏi cần chốt | Ví dụ minh họa |
| --- | --- | --- |
| SP entity ID | SP được IdP nhận diện bằng URI nào? | `https://sp.example/saml2/sp/partner` |
| IdP entity ID | Issuer đáng tin được phép phát assertion? | `https://idp.partner.example/saml` |
| SSO/ACS | Endpoint, binding, chữ ký, redirect, context path? | `/login/saml2/sso/partner` |
| NameID Format | URI chuẩn hoặc policy của IdP? | `...:persistent` |
| NameID source | Object ID, pairwise pseudonym, email, username? | Stable directory subject scoped cho SP. |
| SPNameQualifier | Cần hay không? Giá trị nào? | SP entity ID/affiliation theo hợp đồng. |
| AllowCreate | Có hỗ trợ không; tác động tới identifier nào? | `true` nếu cho phép tạo/liên kết. |
| Uniqueness | Phạm vi đảm bảo không trùng? | Issuer + SP scope. |
| Stability | Đổi email/tên/department có đổi NameID không? | Không đổi do đổi email. |
| Migration | Đổi tenant/IdP/directory thì mapping xử lý thế nào? | Có mapping old→new được phê duyệt. |
| Deprovision | Khi nhân viên nghỉ việc hoặc account bị khóa? | SP vô hiệu local link/quyền kịp thời. |
| Unsupported format | IdP trả `InvalidNameIDPolicy` hay fallback? | Ghi rõ và kiểm thử. |
| Privacy | Có được log/persist NameID không? | Giới hạn truy cập, retention, audit. |

### Tài liệu hợp đồng minh họa

~~~yaml
# Tài liệu ký kết kỹ thuật; KHÔNG phải property có sẵn của Spring
partner: partner-a
spEntityId: "https://sp.example/saml2/sp/partner-a"
idpEntityId: "https://idp.partner-a.example/saml"
nameId:
  expectedFormat: "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
  spNameQualifier: "https://sp.example/saml2/sp/partner-a"
  allowCreate: true
  stableAcrossEmailRename: true
  uniquenessScope: "IdP-SP pair"
  migrationProcess: "admin-approved link update"
accountLink:
  automaticEmailMatch: false
  requireApprovedLocalMapping: true
~~~

Đây là **thỏa thuận triển khai**, không được Spring Boot tự xử lý nếu chỉ đặt trong YAML. Cần cấu hình IdP, code SP và kiểm tra response thật tương ứng.

### Điều gì cần làm nếu IdP không hỗ trợ persistent?

- Xác định format/attribute IdP **thật sự** phát ra và có bảo đảm ổn định nào.
- Nếu IdP dùng `unspecified` nhưng value là immutable object ID, ghi rõ ngữ nghĩa và scope.
- Nếu chỉ phát `transient`, không cố biến nó thành persistent bằng việc giữ kết quả một lần rồi tái sử dụng sai ngữ cảnh.
- Nếu chỉ emailAddress, đánh giá rủi ro cập nhật email/reuse; có thể bổ sung quy trình account linking có duyệt thay vì tự động match.
- Nếu chuyển đổi format, **không cấp quyền lại cho “user mới” vô điều kiện**; thực hiện migration identity mapping có audit.
- Mọi ngoại lệ phải có giới hạn tenant, issuer, permission và khả năng thu hồi.

## 7. Spring Security 6.3: tùy chỉnh AuthnRequest

Trong **Spring Boot 3.3.x / Spring Security 6.3.x**, sử dụng `OpenSaml4AuthenticationRequestResolver` với `setAuthnRequestCustomizer(...)` để thay đổi OpenSAML `AuthnRequest` trước khi phát. Điều này tốt hơn so với việc tự parse/sửa XML `SAMLRequest`.

Mẫu dưới đây là ứng dụng Java 17+ theo hướng Servlet/SP, có cấu hình `partner-a` qua metadata IdP. Việc **build được** không đồng nghĩa login chạy được nếu chưa có IdP, certificate, entity ID và ACS thật.

### 7.1. Cấu trúc dự án

~~~text
saml-nameid-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/nameiddemo/
    │   ├── NameIdDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── IdentityController.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'saml-nameid-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
    // Một số OpenSAML artifacts có thể được tải từ Shibboleth.
    maven {
        url 'https://build.shibboleth.net/maven/releases/'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

`spring-security-saml2-service-provider` là dependency SAML2 SP; `spring-security-oauth2-client` phục vụ OAuth2/OIDC và **không thay thế** SAML2. Cần dùng các phiên bản Java, Gradle và dependency tương thích với Boot 3.3.

### 7.2. Application.java

`src/main/java/com/example/nameiddemo/NameIdDemoApplication.java`:

~~~java
package com.example.nameiddemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NameIdDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(NameIdDemoApplication.class, args);
    }
}
~~~

### 7.3. application.yml

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}
~~~

Biến môi trường `PARTNER_A_IDP_METADATA_URI` là metadata URL thực, được tin cậy của IdP. IdP phải biết SP entity ID, ACS URL và signing certificate của SP nếu yêu cầu. Metadata URI **không phải** NameID Format; việc tùy chỉnh yêu cầu nằm ở Java configuration.

### 7.4. SecurityConfig.java

`src/main/java/com/example/nameiddemo/SecurityConfig.java`:

~~~java
package com.example.nameiddemo;

import org.opensaml.saml.saml2.core.AuthnRequest;
import org.opensaml.saml.saml2.core.NameIDPolicy;
import org.opensaml.saml.saml2.core.NameIDType;
import org.opensaml.saml.saml2.core.impl.NameIDPolicyBuilder;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.RelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.authentication.OpenSaml4AuthenticationRequestResolver;
import org.springframework.security.saml2.provider.service.web.authentication.Saml2AuthenticationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    Saml2AuthenticationRequestResolver authenticationRequestResolver(
            RelyingPartyRegistrationRepository repository) {

        RelyingPartyRegistrationResolver registrationResolver =
            new DefaultRelyingPartyRegistrationResolver(repository);

        OpenSaml4AuthenticationRequestResolver resolver =
            new OpenSaml4AuthenticationRequestResolver(registrationResolver);

        resolver.setAuthnRequestCustomizer(context -> {
            if (!"partner-a".equals(
                    context.getRelyingPartyRegistration().getRegistrationId())) {
                return; // Không áp chính sách đối tác A lên IdP khác.
            }

            AuthnRequest request = context.getAuthnRequest();
            NameIDPolicy policy = request.getNameIDPolicy();
            if (policy == null) {
                policy = new NameIDPolicyBuilder().buildObject();
                request.setNameIDPolicy(policy);
            }

            policy.setFormat(NameIDType.PERSISTENT);
            policy.setAllowCreate(Boolean.TRUE);

            // Nếu đã thỏa thuận SPNameQualifier với IdP:
            // policy.setSPNameQualifier(
            //     context.getRelyingPartyRegistration().getEntityId());
        });

        return resolver;
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            Saml2AuthenticationRequestResolver requestResolver)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(saml -> saml
                .authenticationRequestResolver(requestResolver)
            )
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }
}
~~~

**Giải thích từng bước:**

1. `RelyingPartyRegistrationRepository` cung cấp cặp SP–IdP đã đăng ký. `DefaultRelyingPartyRegistrationResolver` chọn registration phù hợp với đường dẫn/flow.
2. `OpenSaml4AuthenticationRequestResolver` tạo AuthnRequest bằng OpenSAML 4 và các thông số giao thức từ Spring Security. Tên class và method là API có trong Spring Security 6.3.
3. `setAuthnRequestCustomizer(...)` được gọi khi resolver xây AuthnRequest; context cho phép truy cập AuthnRequest và RelyingPartyRegistration.
4. Kiểm tra `registrationId` trước khi áp chính sách; không buộc `partner-b` dùng format của `partner-a`.
5. Nếu request chưa có `NameIDPolicy`, dùng `NameIDPolicyBuilder().buildObject()`; nếu có, sửa object hiện có. Không giả định default của thư viện luôn giống nhau ở mọi version.
6. `NameIDType.PERSISTENT` là hằng URI OpenSAML, tránh nhầm namespace format.
7. `AllowCreate=true` là **lựa chọn theo hợp đồng**. Nếu IdP không hỗ trợ hoặc không được phép tạo/ghép identifier, thay chính sách chứ không mặc định bật mọi đối tác.
8. `SPNameQualifier` chỉ được bật nếu IdP xác nhận yêu cầu giá trị cụ thể; **không tùy tiện gửi** trong mọi request.
9. Gắn resolver bằng `.saml2Login(...authenticationRequestResolver(...))` để filter thực sự sử dụng cấu hình tùy chỉnh.
10. `.saml2Metadata(...)` publish SP metadata; bước này không tự ép IdP phải trả một loại NameID.

**Điều ví dụ không làm:** không tự ký XML thủ công, không thay metadata/certificate tin cậy và không bỏ qua signature, issuer, audience, recipient, time, InResponseTo hay replay checks. NameIDPolicy không phải lý do để vô hiệu hóa các validator này.

### 7.5. Controller quan sát principal

`src/main/java/com/example/nameiddemo/IdentityController.java`:

~~~java
package com.example.nameiddemo;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/")
    public String home() {
        return "Open /me to start SAML login";
    }

    @GetMapping("/me")
    public Map<String, Object> me(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("nameIdValue", principal.getName());
        result.put("registrationId",
                   principal.getRelyingPartyRegistrationId());
        return result;
    }
}
~~~

`Saml2AuthenticatedPrincipal.getName()` thường chứa **giá trị NameID**, nhưng **không cung cấp đầy đủ Format/NameQualifier/SPNameQualifier qua chỉ riêng chuỗi này**. Nếu ứng dụng bắt buộc kiểm tra format trong response, cần validator/converter làm việc trên **Assertion đã được provider xác minh**; không được chỉ tin value của principal hoặc tự parse raw browser XML.

### 7.6. Chạy

Với Gradle Wrapper phù hợp và Java 17+:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell có thể chạy:

~~~powershell
.\gradlew.bat bootRun
~~~

Quy trình tích hợp IdP test:

1. Đặt `PARTNER_A_IDP_METADATA_URI` bằng metadata URL thực.
2. Khởi động ứng dụng. Nếu metadata không tải được, có thể không dựng được registration; đây là lỗi cấu hình cần sửa.
3. Mở `/saml2/metadata/partner-a` và đối chiếu SP entity ID/ACS với cấu hình IdP.
4. Mở `/saml2/authenticate/partner-a` để xem AuthnRequest thực sự có NameIDPolicy persistent/AllowCreate đúng hợp đồng.
5. IdP hoàn tất SSO, gửi response có chữ ký về ACS. Spring Security xác minh SAML response.
6. Mở `/me` sau xác thực. Trường `nameIdValue` phụ thuộc người dùng và IdP; **không có JSON cố định** dùng được ở mọi môi trường.
7. Thực hiện hai lần SSO với cùng người dùng, kiểm tra định danh stable **nếu IdP đã cam kết persistent**.

Đây là dự án SP, **không tạo IdP giả hay chứng thư tin cậy tự động**. Không POST XML minh họa chưa ký ở mục 3 rồi coi là bằng chứng đăng nhập thành công.

## 8. Các trường hợp tùy chỉnh khác

### 8.1. Transient

Nếu hợp đồng yêu cầu transient, sửa bên trong customizer:

~~~java
policy.setFormat(NameIDType.TRANSIENT);
policy.setAllowCreate(null); // Không gửi thuộc tính AllowCreate.
~~~

Đoạn này là **mảnh code trong customizer**, không phải class riêng. Gọi `setAllowCreate(null)` để biểu diễn bỏ thuộc tính; kiểm tra XML phát ra với phiên bản OpenSAML cụ thể. Không dùng NameID transient làm khóa account ổn định.

### 8.2. EmailAddress

~~~java
policy.setFormat(NameIDType.EMAIL);
policy.setAllowCreate(null);
~~~

`NameIDType.EMAIL` ánh xạ URI `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress`. Không tự động ghép local user theo email khi chưa có quy trình an toàn.

### 8.3. Unspecified

~~~java
policy.setFormat(NameIDType.UNSPECIFIED);
policy.setAllowCreate(null);
~~~

Điều này chỉ nói SP không đưa ra cú pháp NameID cụ thể qua format. Nội dung thật của NameID vẫn phải đúng hợp đồng IdP–SP; không tự coi `unspecified` là identifier vô nghĩa hoặc luôn bền vững.

### 8.4. Không gửi NameIDPolicy

Khi IdP có cấu hình hợp đồng mặc định và không muốn nhận NameIDPolicy, bên trong customizer có thể dùng:

~~~java
request.setNameIDPolicy(null);
~~~

Nếu bỏ hoàn toàn element này, **không được bỏ kiểm tra Assertion/NameID nhận về**. SP phải kiểm tra kết quả so với hợp đồng dù request không nói rõ format.

### 8.5. Theo từng registration

~~~java
// Mảnh code bên trong customizer; thay logic của riêng dự án.
String registrationId =
    context.getRelyingPartyRegistration().getRegistrationId();

switch (registrationId) {
    case "partner-a" -> {
        policy.setFormat(NameIDType.PERSISTENT);
        policy.setAllowCreate(Boolean.TRUE);
    }
    case "partner-b" -> {
        policy.setFormat(NameIDType.TRANSIENT);
        policy.setAllowCreate(null);
    }
    default -> throw new IllegalStateException(
        "No NameID contract for " + registrationId);
}
~~~

Trong production phải bảo đảm không áp dụng một identifier/issuer ngoài danh sách được tin cậy. **Không chọn format từ một query parameter do trình duyệt gửi** để vượt qua chính sách tích hợp.

## 9. Kiểm tra NameID trong Assertion thực nhận

### 9.1. NameID do IdP trả

Ví dụ Subject trong một Assertion đã được xác thực:

~~~xml
<saml:Subject
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    <saml:NameID
        Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
        NameQualifier="https://idp.partner.example/saml"
        SPNameQualifier="https://sp.example/saml2/sp/partner">
        p-6f91
    </saml:NameID>
    <saml:SubjectConfirmation
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <!-- SubjectConfirmationData rang buoc Recipient/InResponseTo/NotOnOrAfter -->
    </saml:SubjectConfirmation>
</saml:Subject>
~~~

Đây chỉ là mảnh XML diễn giải, không chứa chữ ký hoặc response bao ngoài. **SP phải xác minh toàn bộ Response/Assertion phù hợp trước khi tin NameID**: chữ ký với certificate IdP tin cậy, issuer, audience, ACS recipient, request correlation, time, replay và các conditions.

### 9.2. Danh sách validation sau khi provider chấp nhận assertion

| Yếu tố | Phải kiểm tra | Vì sao? |
| --- | --- | --- |
| IdP Issuer | Khớp registration/tenant đã được tin cậy. | Hai IdP có thể phát cùng một NameID string. |
| Format | Khớp hợp đồng đã thỏa thuận; xử lý trường hợp absent/unspecified có chủ đích. | Request Format không bảo đảm response Format. |
| NameID value | Giá trị hợp lệ, không rỗng/không thuộc mẫu trái hợp đồng. | Không tạo account từ ID không xác định. |
| NameQualifier | Đúng nguồn/namespace nếu profile yêu cầu. | Xác định scope của subject. |
| SPNameQualifier | Đúng SP/affiliation nếu có yêu cầu. | Tránh trộn định danh giữa SP/tenant. |
| Stability | Đăng nhập lặp lại cho cùng người vẫn giữ ID theo cam kết. | Tránh “user mới” mỗi lần SSO. |
| Local link | Map tới local account đã phê duyệt/được provisioning theo policy. | Không cấp quyền chỉ vì SAML login thành công. |
| Authorization | Local account active và có quyền trên tài nguyên/tenant cụ thể. | Identity không phải permission. |

### 9.3. Vị trí tích hợp với Spring Security

Mẫu ở mục 7 chỉ **thay đổi AuthnRequest** và sau login xem chuỗi NameID. Nó **chưa** bắt buộc IdP trả đúng `Format` bằng một validator riêng. Nếu nghiệp vụ yêu cầu NameID format tuyệt đối, cần thêm kiểm tra trên **OpenSAML Assertion đã được xác minh**, qua response validation/conversion extension point thích hợp của phiên bản Spring Security đang chạy.

**Không làm:** trong controller tự lấy `SAMLResponse` từ HTTP request, decode Base64 và dùng XPath `//NameID[1]` để phân quyền. Bên ngoài provider, kỹ thuật đó có thể đọc **phần tử XML khác với phần tử đã được xác minh chữ ký** và tạo nguy cơ XML Signature Wrapping.

Có thể mô tả tiêu chí validation bằng pseudocode:

~~~text
verifiedAssertion = assertion đã được Spring Security/OpenSAML verify
subjectNameID = verifiedAssertion.Subject.NameID

REQUIRE verifiedAssertion.issuer == configuredIdP.issuer
REQUIRE subjectNameID != null
REQUIRE subjectNameID.format == configuredContract.expectedFormat
REQUIRE scope/qualifiers satisfy configuredContract
localUser = lookupTrustedIdentityLink(issuer, format, qualifiers, value)
REQUIRE localUser.status == ACTIVE

# Sau đó vẫn phải áp permission/tenant cho từng request nghiệp vụ.
~~~

Đây là **thuật toán thiết kế**, không phải API Java được hứa sẽ compile. Tên method và vị trí hook cho validated Assertion phụ thuộc Spring Security/OpenSAML version; phải đối chiếu tài liệu của bản đang sử dụng.

### 9.4. Thiết kế khóa liên kết danh tính

Một cấu trúc dữ liệu tham khảo:

~~~text
external_identity
-------------------------------------------------------------------
idp_entity_id     format       sp_scope     name_id_value   local_user
IdP-A             persistent   SP-Orders    p-6f91          user_104
IdP-B             persistent   SP-Orders    p-6f91          user_999

local_user
-------------------------------------------------------------------
id        tenant_id       status        permissions
user_104  partner_A       ACTIVE        ORDER_READ
user_999  partner_B       ACTIVE        ORDER_READ
~~~

Hai user này **không được gộp** vì issuer khác nhau, dù NameID value giống. Unique key thực tế phải phản ánh **issuer + format + qualifier/SP scope + value** và tenant/registration khi hợp đồng yêu cầu. SP có thể chọn cách chuẩn hóa qualifier vắng mặt nhưng phải được chứng minh an toàn, không tự gán scope tùy ý.

**Không tự ghép bằng email:** email có thể đổi/reuse, và một email xuất hiện ở hai IdP khác nhau không chứng minh đây cùng một user. Khi provisioning lần đầu, có thể tạo trạng thái `PENDING` rồi đợi approval; không cấp admin authority mặc định.

### 9.5. Đổi định dạng trong hệ thống đã hoạt động

Từ `emailAddress` sang `persistent` có thể làm mọi tài khoản trông khác đi. Migration an toàn thường cần:

1. Freeze hợp đồng hiện tại, xuất danh sách liên kết user có kiểm soát; giới hạn truy cập dữ liệu PII.
2. Nhận từ IdP ánh xạ **old ID → new persistent ID** bằng nguồn đã được xác minh và phê duyệt.
3. Thử nghiệm với tập account không nhạy cảm; kiểm tra không trùng người hoặc trộn tenant.
4. Đưa schema hỗ trợ nhiều external identity/link có hiệu lực trong một khoảng migration nếu policy cho phép.
5. Thay liên kết theo transaction, audit ai duyệt, phát hiện ambiguous mappings và rollback.
6. Loại bỏ cách fallback theo email sau cutover; không để attacker lợi dụng cả hai format để chiếm user khác.
7. Kiểm tra thu hồi quyền, session đang tồn tại và lưu trữ định danh cũ theo retention policy.

Không được đổi NameIDPolicy một chiều ở SP rồi tự động “link” tài khoản mới tới tài khoản cũ chỉ từ tên/email hiển thị.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| IdP trả `InvalidNameIDPolicy`. | Format/qualifier/AllowCreate không được hỗ trợ. | Kiểm tra đúng URI, hợp đồng và cấu hình IdP. |
| SP yêu cầu persistent nhưng nhận transient. | IdP không thực thi yêu cầu hoặc đang dùng default. | Phân tích outbound request và assertion thật; sửa IdP hoặc hợp đồng. |
| Mỗi lần đăng nhập tạo local account mới. | Dùng transient NameID làm khóa lâu dài. | Dùng persistent hoặc immutable subject khác có mapping. |
| Sau khi đổi email, user mất quyền. | Khóa identity bằng email. | Tách email khỏi immutable subject và migration an toàn. |
| `AllowCreate=true` mà SP không có user mới. | Nhầm tạo identifier ở IdP với provisioning ở SP. | Thiết kế JIT/local account provisioning riêng. |
| Gửi `AllowCreate` với transient. | Trái quy tắc SAML Errata 05. | Bỏ thuộc tính trong customizer. |
| Thêm SPNameQualifier khiến login lỗi. | IdP không hỗ trợ/giá trị không đúng contract. | Thương lượng chính xác hoặc bỏ trường khi phù hợp. |
| Một NameID bị ghép nhầm người ở IdP B. | Chỉ lưu chuỗi NameID, không lưu issuer. | Thêm issuer/format/scope trong unique link. |
| Request không có NameIDPolicy dù đã viết bean. | Filter chưa sử dụng resolver mới, hoặc flow không khởi phát từ SP. | Gắn resolver vào `saml2Login`, kiểm tra endpoint/IdP-initiated. |
| Đổi NameIDPolicy làm chữ ký AuthnRequest lỗi. | Tự chỉnh XML/binding sau khi ký. | Chỉnh OpenSAML AuthnRequest trong customizer trước khi ký. |
| SP-initiated login đúng nhưng IdP-initiated khác format. | Không có AuthnRequest của SP trong flow unsolicited. | Cấu hình IdP + validate Assertion; không chỉ dựa customizer. |
| Login thành công nhưng API trả 403. | Thiếu permission/tenant hoặc tài khoản local inactive. | Xử lý authorization riêng; không bỏ kiểm tra chữ ký SAML. |
| Mã `OpenSaml4AuthenticationRequestResolver` không compile ở thế hệ mới. | Khác Spring Security/OpenSAML major version. | Tra Javadoc của bản được resolve và migration guide. |
| `unspecified` value thay đổi sau migration. | Hợp đồng chưa quy định tính bền vững. | Làm rõ nguồn ID và quy trình đổi subject. |

### Đừng nhầm các thuộc tính AuthnRequest

- `ForceAuthn` yêu cầu IdP xác thực lại thay vì dựa vào phiên cũ.
- `IsPassive` hướng dẫn IdP tránh tương tác user theo profile.
- `RequestedAuthnContext` mô tả bối cảnh/phương thức xác thực mong muốn.
- `AssertionConsumerServiceURL` là ACS của SP nhận response.
- `NameIDPolicy` là yêu cầu **định dạng/ngữ cảnh identifier**.
- `RelayState` phục vụ liên kết trạng thái qua binding, **không phải** định danh người dùng.

Chỉ đổi `NameIDPolicy` không làm IdP phát quyền admin, không đồng nghĩa MFA, không thay đổi expiration Assertion và không xử lý SLO.

## 11. Theo phiên bản Spring Security

**Spring Security 6.3 / Spring Boot 3.3**:

- Có `Saml2AuthenticationRequestResolver` và `OpenSaml4AuthenticationRequestResolver` để tùy chỉnh AuthnRequest.
- `setAuthnRequestCustomizer` sử dụng đối tượng `AuthnRequestContext` cung cấp AuthnRequest/registration.
- OpenSAML 4 dùng `org.opensaml.saml.saml2.core.NameIDPolicy` và `NameIDType` như ví dụ.
- API 6.3 là baseline ví dụ runnable ở mục 7.

**Spring Security 6.4/6.5**:

- Có các thay đổi tương thích OpenSAML 4/5 tùy dependency được quản lý; cần tra đúng class resolver trong version thực.
- Không chỉ đổi tên class trong source mà bỏ qua build và test: OpenSAML major version có thể ảnh hưởng API.

**Spring Security 7.x**:

- Tài liệu hiện đại minh họa `OpenSaml5AuthenticationRequestResolver`; cần kiểm tra migration, Java baseline, classpath và method hiện có.
- Không dùng `spring-security-saml` extension đời cũ như thể nó là API tương đương cho Servlet SAML2 Login hiện đại.

Kiểm tra dependency thực:

~~~bash
./gradlew dependencyInsight --dependency spring-security-saml2-service-provider --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opensaml-saml-api --configuration runtimeClasspath
~~~

Với PowerShell, dùng `.\gradlew.bat`. Nếu đã override BOM, số phiên bản Boot **không đủ** để khẳng định runtime dùng class resolver nào.

## 12. Bộ kiểm thử và bài thực hành

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| N01 | SP phát AuthnRequest cho partner-a. | NameIDPolicy.Format=persistent, AllowCreate đúng hợp đồng. |
| N02 | SP phát AuthnRequest cho partner-b. | Không tự áp policy partner-a lên registration khác. |
| N03 | IdP trả persistent NameID, issuer/qualifier/subject đúng. | Nhận sau khi SAML signature/conditions và local link hợp lệ. |
| N04 | IdP trả transient trong khi hợp đồng bắt buộc persistent. | Từ chối mapping hoặc authentication theo policy, không tự coi transient là persistent. |
| N05 | IdP chỉ hỗ trợ emailAddress. | Không tự tạo local admin account theo email. |
| N06 | IdP không hỗ trợ format SP yêu cầu. | Có lỗi/khả năng fallback được ghi rõ, không bỏ validation. |
| N07 | SP gửi transient cùng AllowCreate. | Outbound test thất bại; sửa không gửi AllowCreate. |
| N08 | SPNameQualifier không khớp scope đã thỏa thuận. | Từ chối hoặc xử lý lỗi cấu hình; không ánh xạ sai tenant. |
| N09 | Hai IdP phát cùng NameID value. | Hai external identity khác nhau. |
| N10 | Cùng user đăng nhập hai phiên persistent. | Đúng local account theo key có scope. |
| N11 | Raw AuthnRequest bị sửa sau khi ký. | Chữ ký/kiểm tra không còn hợp lệ. |
| N12 | IdP-initiated login không có AuthnRequest. | Vẫn kiểm tra actual NameID; không giả định customizer được chạy. |
| N13 | Subject hợp lệ nhưng local account bị disable. | Không cấp quyền nghiệp vụ. |
| N14 | Assertion sai issuer/audience/recipient/time/signature. | Authentication bị từ chối trước khi account linking. |
| N15 | IdP đổi format sau migration. | Quy trình mapping old→new có kiểm chứng, audit và rollback. |

**Ranh giới rõ ràng:** ví dụ runnable ở mục 7 chứng minh **outbound NameIDPolicy** và principal cơ bản sau login. Các test N04, N08, N12, N15 đòi kiểm tra actual NameID và quy trình local identity riêng; chưa thể coi chúng được đáp ứng chỉ bằng customizer.

### 12.1. Kiểm tra outbound request

1. Dùng môi trường IdP test được kiểm soát; mở `/saml2/authenticate/partner-a`.
2. Bắt `SAMLRequest` bằng công cụ SAML tracer đáng tin và chỉ trong môi trường thử nghiệm.
3. Với **HTTP-Redirect**, decode URL encoding, Base64 và DEFLATE đúng binding; với POST binding, decode Base64 theo quy tắc.
4. Parse XML và tìm `samlp:AuthnRequest/samlp:NameIDPolicy`. Đối chiếu Format/AllowCreate/SPNameQualifier với thỏa thuận.
5. Kiểm tra SP Issuer/ACS và chữ ký request khi IdP yêu cầu; không tự chỉnh bytes sau khi ký.
6. Cho IdP phát một Assertion thật có chữ ký hợp lệ, so sánh actual NameID/qualifiers với hợp đồng.
7. Test nhiều lượt login, user khác nhau và tenant khác nhau để xác nhận ổn định và uniqueness.
8. Xóa trace/raw SAMLResponse khi hoàn tất; không tải dữ liệu định danh lên các công cụ debug công cộng.

### 12.2. Câu hỏi tự đánh giá

**Câu 1.** Vì sao `NameIDPolicy` không chứng minh danh tính?  
**Trả lời:** Vì nó do SP gửi đi, không phải Assertion đã xác minh từ IdP.

**Câu 2.** Format persistent có đảm bảo một người dùng cùng NameID ở mọi SP không?  
**Trả lời:** Không; scope có thể theo IdP–SP/affiliation.

**Câu 3.** `AllowCreate=true` có tự tạo user trong DB SP không?  
**Trả lời:** Không; nó liên quan tạo/liên kết identifier ở IdP theo policy.

**Câu 4.** Có nên gửi AllowCreate với transient?  
**Trả lời:** Không; Errata 05 yêu cầu không dùng.

**Câu 5.** Vì sao không nên khóa external identity bằng emailAddress?  
**Trả lời:** Email có thể đổi/tái sử dụng; chữ ký Assertion không khiến email bất biến.

**Câu 6.** SPNameQualifier có phải ACS URL không?  
**Trả lời:** Không; nó xác định ngữ cảnh SP/affiliation cho identifier.

**Câu 7.** Khi IdP trả unspecified, phải làm gì?  
**Trả lời:** Thỏa thuận cụ thể NameID value là gì, tính ổn định và scope; không đoán.

**Câu 8.** Vì sao chỉ xem `principal.getName()` chưa đủ?  
**Trả lời:** Nó thường là NameID value, không đầy đủ Format/qualifiers; cần validated Assertion khi policy đòi hỏi.

**Câu 9.** Một IdP phát cùng NameID như IdP khác thì có thể gộp user không?  
**Trả lời:** Không; issuer là thành phần ranh giới tin cậy của khóa liên kết.

**Câu 10.** IdP-initiated SSO có đi qua AuthnRequest customizer không?  
**Trả lời:** Không có request do SP tạo trong luồng đó, nên cần kiểm soát format tại IdP và trong response validation.

## 13. Checklist triển khai

- [ ] Đã chốt URI format chuẩn với IdP; phân biệt `persistent`, `transient`, `emailAddress`, `unspecified`.
- [ ] Nếu dùng persistent, đã xác nhận scope, uniqueness, lifecycle và cách đổi ID.
- [ ] `SPNameQualifier` chỉ xuất hiện khi có thỏa thuận cụ thể, không sao chép ACS vào trường này.
- [ ] `AllowCreate` phù hợp hợp đồng; **không xuất hiện khi transient**.
- [ ] Cấu hình Spring Security đúng resolver theo version thực; gắn customizer vào filter.
- [ ] Chính sách phân theo `registrationId`, không nhận format từ request không đáng tin.
- [ ] Có IdP metadata/certificate tin cậy; không bỏ signature/issuer/audience/recipient/time/correlation/replay checks.
- [ ] Đã kiểm tra outbound AuthnRequest và inbound NameID trên Assertion hợp lệ.
- [ ] Identity link chứa issuer + scope + format + value theo hợp đồng; không map user chỉ bằng email.
- [ ] Có quy trình user mới, deprovision, khóa tài khoản và migration identifier.
- [ ] Kiểm tra IdP-initiated SSO riêng nếu được cho phép.
- [ ] Nội dung SAML nhạy cảm không bị ghi vào log công khai hoặc dịch vụ debug bên thứ ba.
- [ ] Đã chạy các test N01–N15 hoặc bộ test tương đương.
- [ ] Kiểm soát quyền nghiệp vụ ở SP sau khi SAML authentication thành công.

**Ghi nhớ:** `NameIDPolicy` là lời đề nghị định dạng từ SP. `NameID` trong Assertion đã xác minh mới là khẳng định danh tính của IdP. Muốn account linking an toàn, phải có **hợp đồng định danh bền vững, scoped đúng issuer/SP, được kiểm thử và có quy trình đổi identifier**. Tùy chỉnh AuthnRequest không thay thế xác minh response hoặc phân quyền nội bộ.

### Tài liệu chính thức

- [OASIS — SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `NameIDPolicy`, `NameID`, định dạng NameID và các điều kiện AuthnRequest/Assertion.
- [OASIS — Approved SAML 2.0 Errata 05](https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html): `AllowCreate` và quy tắc không dùng với transient.
- [Spring Security — Producing SAML2 AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): resolver, customizer, request binding và chữ ký.
- [Spring Security 6.3.5 — OpenSaml4AuthenticationRequestResolver Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/saml2/provider/service/web/authentication/OpenSaml4AuthenticationRequestResolver.html): API phù hợp ví dụ Boot 3.3.
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): filter, registration, metadata, ACS.
- [Spring Security — Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): principal, assertion và response validation.
- [OpenSAML 4 — NameIDType](https://javadoc.io/static/org.opensaml/opensaml-saml-api/4.0.1/org/opensaml/saml/saml2/core/NameIDType.html): hằng URI `PERSISTENT`, `TRANSIENT`, `EMAIL`, `UNSPECIFIED`.
- [Microsoft Entra — SAML SSO protocol](https://learn.microsoft.com/azure/active-directory/develop/single-sign-on-saml-protocol): ví dụ thực tế về NameIDPolicy và cách triển khai IdP có thể bỏ qua AllowCreate.
