# AttributeStatement, thuộc tính đơn trị và đa trị trong SAML 2.0

> **Phạm vi:** Spring Security – federation → Mô hình SAML2. Bài học tập trung vào cách SAML Assertion biểu diễn thuộc tính người dùng qua `AttributeStatement`, phân biệt 0/1/nhiều giá trị, cách SP đọc và dùng chúng trong Spring Security, cùng các giới hạn bảo mật và tương tác với IdP.

## 1. Vì sao cần hiểu cardinality của thuộc tính?

Khi ứng dụng đăng nhập bằng SAML 2.0, IdP có thể gửi thông tin như email, mã nhân viên, phòng ban, danh sách nhóm hoặc các thuộc tính nghiệp vụ. Một lỗi phổ biến là nghĩ rằng mọi thuộc tính đều là **một chuỗi**. Thực tế, một `<saml:Attribute>` có thể chứa **không có, một hoặc nhiều** `<saml:AttributeValue>`. Nhận một giá trị đầu tiên khi dữ liệu thật là nhiều giá trị có thể làm mất thông tin; tự tách một chuỗi duy nhất thành danh sách có thể làm thay đổi nghĩa của thuộc tính.

Ví dụ:

- `mail` thường được hợp đồng IdP/SP quy định chỉ có **một** email dùng cho ứng dụng.
- `groups` thường có **nhiều** nhóm như `portal-readers` và `invoice-approvers`.
- `employeeId` có thể bắt buộc là **một** mã định danh.
- `costCenters` có thể có **0 đến nhiều** mã nếu nhân viên phụ trách nhiều đơn vị.
- `displayName` là thông tin hiển thị, có thể không được cấp; thiếu `displayName` không nhất thiết có nghĩa xác thực thất bại.

**Mục tiêu:** đọc đúng cấu trúc SAML; hiểu hợp đồng dữ liệu từng thuộc tính; tránh dùng `getFirstAttribute()` cho thông tin vốn đa trị; xác minh assertion trước khi tin attributes; và không tự biến groups từ IdP thành toàn bộ quyền của ứng dụng.

## 2. Vị trí của AttributeStatement trong SAML Assertion

SAML 2.0 phân biệt một số loại statement:

| Thành phần | Vai trò |
| --- | --- |
| `<saml:Subject>` / `<saml:NameID>` | Xác định subject được assertion nhắc đến |
| `<saml:AuthnStatement>` | Khẳng định lần/phương thức xác thực; có thể chứa `AuthnInstant`, `SessionIndex`, `AuthnContext` |
| `<saml:AttributeStatement>` | Tập thuộc tính mô tả subject qua `Attribute` / `AttributeValue` |
| `<saml:AuthzDecisionStatement>` | Một loại statement khác về quyết định phân quyền, ít dùng trong Web SSO thông thường |
| `<saml:Conditions>` | Giới hạn hiệu lực assertion, audience và điều kiện khác |

Sơ đồ cấu trúc điển hình (đã giản lược):

```text
<samlp:Response>
  └── <saml:Assertion>                       [được xác minh bằng cơ chế ký phù hợp]
       ├── <saml:Issuer> ...
       ├── <saml:Subject>
       │    └── <saml:NameID> ...
       ├── <saml:Conditions> ...
       ├── <saml:AuthnStatement> ...
       └── <saml:AttributeStatement>
            ├── <saml:Attribute Name="...mail">
            │    └── <saml:AttributeValue>linh@example.org
            ├── <saml:Attribute Name="...groups">
            │    ├── <saml:AttributeValue>portal-readers
            │    └── <saml:AttributeValue>invoice-approvers
            └── <saml:Attribute Name="...costCenter">
                 └── (không có AttributeValue)
```

Đây là **sơ đồ**, không phải XML độc lập hợp lệ. Trong tài liệu SAML, `AttributeStatement` thuộc **assertion**; nó không phải phần được ứng dụng tùy ý thêm vào sau khi SP đã xác thực. Một assertion có thể có nhiều statement; ứng dụng không được suy luận rằng luôn có một `AttributeStatement` hay có đúng một loại thuộc tính. `EncryptedAttribute` có thể xuất hiện thay cho attribute rõ, tùy IdP/profile và khả năng giải mã được cấu hình ở SP.

**Điểm phân biệt:** `NameID` **không phải** một `Attribute` của `AttributeStatement`. Chúng có thể chứa chuỗi giống nhau (ví dụ email), nhưng không mặc định tương đương về tính duy nhất, độ ổn định, đối tượng nhận hoặc chính sách sử dụng. Tùy ứng dụng, `NameID`/subject identifier thường được dùng làm đầu vào cho account mapping; `mail`/`displayName` là claims bổ sung.

## 3. Giải phẫu một Attribute

Một `<saml:Attribute>` có ba XML attributes quan trọng:

| Trường | Bắt buộc? | Ý nghĩa |
| --- | --- | --- |
| `Name` | Có | Tên kỹ thuật của SAML attribute, ví dụ `urn:example:claims:groups` hoặc một OID URI |
| `NameFormat` | Không | Định dạng/miền tên của `Name`, ví dụ `urn:oasis:names:tc:SAML:2.0:attrname-format:uri` |
| `FriendlyName` | Không | Tên dễ đọc cho người cấu hình, ví dụ `groups`; **không** là định danh chuẩn để so khớp chính thức |
| `AttributeValue` (phần tử con) | 0 đến nhiều | Mỗi phần tử mang một giá trị của attribute; có thể đơn giản hoặc phức hợp |

Ví dụ một `AttributeStatement` **đầy đủ về mặt hình thức đoạn XML**, dùng giá trị giả lập; đây **không** phải SAML Assertion đã ký và không thể tự dùng để đăng nhập:

```xml
<saml:AttributeStatement
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">

    <!-- Một giá trị -->
    <saml:Attribute
        Name="urn:example:claims:mail"
        NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
        FriendlyName="mail">
        <saml:AttributeValue xsi:type="xs:string">linh@example.org</saml:AttributeValue>
    </saml:Attribute>

    <!-- Nhiều giá trị: hai AttributeValue trong một Attribute -->
    <saml:Attribute
        Name="urn:example:claims:groups"
        NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
        FriendlyName="groups">
        <saml:AttributeValue xsi:type="xs:string">portal-readers</saml:AttributeValue>
        <saml:AttributeValue xsi:type="xs:string">invoice-approvers</saml:AttributeValue>
    </saml:Attribute>

    <!-- Thuộc tính có mặt nhưng chưa có giá trị -->
    <saml:Attribute
        Name="urn:example:claims:costCenters"
        NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
        FriendlyName="costCenters"/>
</saml:AttributeStatement>
```

Đọc theo từng lớp:

1. `AttributeStatement` chứa nhiều **attribute khác nhau**: `mail`, `groups` và `costCenters`.
2. Mỗi `Attribute` có một **tên kỹ thuật** `Name` và danh sách **giá trị**. `mail` có một, `groups` có hai, `costCenters` không có.
3. `FriendlyName="groups"` chỉ thuận tiện cho người đọc; khi tích hợp phải dùng định danh được IdP/SP thỏa thuận (bao gồm `NameFormat` khi cần phân biệt namespace).
4. Giá trị `xsi:type="xs:string"` cho biết dữ liệu kiểu XML Schema string trong ví dụ. SAML `AttributeValue` có kiểu nền `xs:anyType`; IdP có thể cung cấp giá trị kiểu đơn giản khác hoặc XML phức hợp, tùy profile.
5. Đoạn XML chưa có SAML Response, signature, `Issuer`, `Conditions` và `SubjectConfirmation`. Không được “tin” một attribute chỉ vì nó parse được.

### 3.1. NameFormat: cùng Name có luôn là cùng thuộc tính?

Không nên giả định. SAML Core và Errata lưu ý định danh attribute có thể cần xét **cặp `(NameFormat, Name)`**; một `Name` đứng riêng có thể không đủ nếu IdP sử dụng nhiều không gian đặt tên. `NameFormat` vắng mặt được hiểu theo `unspecified` trong SAML Core; không tự suy ra thành `uri`. Giá trị phổ biến:

- `urn:oasis:names:tc:SAML:2.0:attrname-format:unspecified` – không có quy tắc đặt tên cụ thể.
- `urn:oasis:names:tc:SAML:2.0:attrname-format:uri` – tên ở dạng URI.
- `urn:oasis:names:tc:SAML:2.0:attrname-format:basic` – namespace tên đơn giản theo quy tắc SAML.

Ví dụ hợp đồng có thể chọn `Name=urn:example:claims:groups` và `NameFormat=...:uri`. Không tự dùng `FriendlyName=groups` làm khóa ánh xạ nếu `Name` thật là URI.

**Trong Spring Security 6.x**, `Saml2AuthenticatedPrincipal#getAttributes()` trình bày thuộc tính bằng `Map<String, List<Object>>` và tra cứu bằng **tên chuỗi**. Đây là mô hình ánh xạ tiện dụng, **không phơi bày nguyên vẹn tất cả metadata của mỗi `Attribute`**. Nếu hai attributes cùng `Name` nhưng khác `NameFormat`, ứng dụng phải kiểm soát schema/IdP mapping trước khi rút chúng xuống một khóa chuỗi; không giả định getter tự phát hiện hoặc giải quyết mọi xung đột namespace.

### 3.2. Kiểu của AttributeValue

`<saml:AttributeValue>` là giá trị XML, không có bảo đảm “mọi thứ là Java String”. Ví dụ:

```xml
<saml:Attribute
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    Name="urn:example:claims:employeeLevel">
    <saml:AttributeValue xsi:type="xs:integer">4</saml:AttributeValue>
</saml:Attribute>
```

Trong ngữ nghĩa XML Schema, `4` thuộc kiểu số nguyên theo `xsi:type`. Nhưng khi đi qua bộ chuyển đổi cụ thể, giá trị Java có thể được hiện thực hóa theo các quy tắc thư viện và phiên bản. Ứng dụng cần **xác nhận dạng đối tượng thực tế** trước khi ép kiểu, đồng thời quy định schema giữa IdP/SP. Không gọi `toString()` bừa bãi cho một XML object phức hợp rồi coi là giá trị nghiệp vụ.

Nếu `Attribute` có nhiều `AttributeValue` và các giá trị khai báo `xsi:type`, SAML Core yêu cầu các type được khai báo thống nhất trong cùng attribute. Một giá trị phức hợp có thể cần schema và converter riêng; cần test chính xác profile IdP.

## 4. Thuộc tính đơn trị, đa trị, vắng mặt và giá trị rỗng

### 4.1. Cardinality thực tế

| XML nguồn | Số `AttributeValue` | Ngữ nghĩa kỹ thuật | Chính sách gợi ý khi app đọc |
| --- | ---: | --- | --- |
| Không có `<Attribute Name="mail">` | Không áp dụng | Attribute vắng mặt | Required → từ chối mapping; optional → dùng trạng thái thiếu |
| Có `<Attribute Name="mail"/>` | 0 | Attribute có mặt nhưng không có giá trị | Không tự coi là chuỗi rỗng hay null; xử lý theo hợp đồng |
| Có một `<AttributeValue>linh@example.org</...>` | 1 | Một giá trị | Cho phép với thuộc tính hợp đồng đơn trị |
| Có hai `<AttributeValue>reader</...>` và `<AttributeValue>editor</...>` | 2 | Hai giá trị độc lập | Đọc danh sách, không chọn ngẫu nhiên giá trị đầu |
| Có một `<AttributeValue>reader,editor</...>` | 1 | **Một** chuỗi chứa dấu phẩy | Chỉ split nếu IdP/SP thỏa thuận encoding CSV |
| Có một `<AttributeValue></AttributeValue>` | 1 | Một giá trị có nội dung rỗng theo encoding | Khác với việc không có value; cân nhắc từ chối cho required |
| Hai `<Attribute>` trùng tên | Phụ thuộc từng phần tử | Hai lần khai báo cùng attribute name | Có chính sách merge/deduplicate/reject rõ ràng, không dựa vào thứ tự |

> **Điểm quan trọng:** “Đơn trị”/“đa trị” thường là **hợp đồng của một thuộc tính** trong ứng dụng hoặc SAML profile, chứ phần tử `Attribute` nói chung không có cờ `single=true`. XML schema của `AttributeValue` cho phép từ 0 đến nhiều.

### 4.2. Không trộn lẫn bốn trường hợp

**A. Vắng mặt:** Không có key tương ứng. Với Spring Security `getAttribute(name)` thường trả `null` khi attribute không có trong map. Đừng xử lý `null` như danh sách có một phần tử `null`.

**B. Có attribute nhưng không có values:** XML có `Attribute` và zero `AttributeValue`. Khi chuyển sang Java, cần kiểm thử bộ chuyển đổi: có thể là danh sách rỗng hoặc bị bỏ qua tùy implementation/mapping. Đừng suy ra duy nhất từ một dạng trả về nếu logic phải phân biệt hai trạng thái.

**C. Có một value nhưng nội dung là chuỗi rỗng hoặc toàn khoảng trắng:** Đây là một giá trị thực tế về mặt cấu trúc. Ứng dụng có thể cấm nó theo contract của `employeeId`/`mail`, nhưng không tự biến mọi chuỗi rỗng thành “vắng mặt” nếu thuộc tính cho phép rỗng.

**D. Có nhiều values:** Mỗi phần tử mang một giá trị. Thứ tự XML không nên trở thành ưu tiên quyền nếu hợp đồng không định nghĩa thứ tự. Với nhóm/roles, thường nên dùng tư duy **tập hợp** sau khi đã chuẩn hóa đúng hợp đồng; với địa chỉ liên hệ có thứ tự ưu tiên, có thể cần metadata khác thay vì mặc định “phần tử đầu là primary”.

### 4.3. Chuỗi chứa dấu phân tách không bằng nhiều giá trị

Hai biểu diễn sau **không tương đương** trừ khi IdP/SP có thỏa thuận rõ:

```xml
<!-- 2 giá trị SAML -->
<saml:Attribute xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                Name="urn:example:claims:groups">
    <saml:AttributeValue>team-a</saml:AttributeValue>
    <saml:AttributeValue>team-b</saml:AttributeValue>
</saml:Attribute>
```

```xml
<!-- 1 giá trị SAML; dấu phẩy là dữ liệu của chuỗi -->
<saml:Attribute xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                Name="urn:example:claims:groups">
    <saml:AttributeValue>team-a,team-b</saml:AttributeValue>
</saml:Attribute>
```

Nếu nhà cung cấp thực sự gửi CSV trong một AttributeValue, định nghĩa delimiter, escape, khoảng trắng, giá trị rỗng, thứ tự, xử lý dấu phẩy nằm trong tên và giới hạn độ dài. Nếu không có hợp đồng, **không tự tách** bằng `String.split(",")` rồi gán roles.

### 4.4. Hai Attribute cùng tên: xử lý nhất quán

Một số dữ liệu liên thông có thể chứa `Attribute` trùng `Name` trong cùng hoặc các statement khác nhau. Hành vi mà thư viện ánh xạ thành `Map<String, List<Object>>` có thể phụ thuộc cách nó gom/ghi đè/ưu tiên. Với thuộc tính nhạy cảm:

- Ưu tiên cấu hình IdP phát **một Attribute có nhiều AttributeValue** thay vì nhiều Attribute trùng tên khi cần đa trị.
- Tài liệu hóa hành vi duplicate: reject, merge theo chính sách hay xem như lỗi schema; không “chọn phần tử xuất hiện sau cùng” vì attacker có thể lợi dụng ambiguity.
- Test dữ liệu có hai `Name` giống nhau, `NameFormat` khác nhau, FriendlyName khác nhau, giá trị mâu thuẫn và thứ tự đảo ngược.
- Với required scalar như `employeeId`, từ chối có nhiều giá trị bất kể chúng giống/khác nhau, trừ khi business contract thật sự cho phép và có quy tắc rõ.

## 5. Quy trình ánh xạ attributes sau xác thực

```text
IdP phát Assertion
  │
  ▼
Browser gửi SAMLResponse đến ACS của SP
  │
  ▼
Spring Security / OpenSAML:
  xác minh issuer, signature/trust, destination, audience,
  điều kiện thời gian, subject confirmation và giao dịch login
  │
  ▼
Giải mã EncryptedAttribute (nếu được cấu hình và cần thiết)
  │
  ▼
Trích AttributeStatement theo quy tắc converter
  │
  ▼
Map<String, List<Object>> trên authenticated principal
  │
  ▼
APPLICATION MAPPING:
  1. chọn tên attribute đã ký kết
  2. kiểm tra presence + cardinality + kiểu + format
  3. chuẩn hóa có kiểm soát
  4. liên kết (issuer, subject, tenant) với user nội bộ
  5. chuyển claims thành quyền theo allowlist/policy
  │
  ▼
SecurityContext + session; các request tiếp theo áp dụng authorization
```

**Ranh giới bảo mật:** Attribute chỉ đáng tin **sau** khi thành công validation SAML cho đúng IdP/SP và đúng assertion được dùng. Đọc XML đã Base64 decode, lấy email/groups từ request ACS trước khi signature validation, hoặc tự parse XML bằng XPath không ràng buộc vùng ký có thể gây nguy cơ giả mạo principal và XML signature wrapping.

**Tính thời điểm:** Groups/department trong assertion là **snapshot** IdP cấp lúc đăng nhập. Khi groups đổi ở IdP, session nội bộ có thể chưa phản ánh ngay. Hệ thống yêu cầu thu hồi đặc quyền nhanh cần session timeout/re-auth, re-fetch quyền từ nguồn nghiệp vụ hoặc chính sách revoke phù hợp; không dựa vào AttributeStatement tự cập nhật.

## 6. Đọc thuộc tính bằng Spring Security 6.x

Ở ứng dụng Servlet đăng nhập SAML qua `saml2Login()`, `Saml2Authentication#getPrincipal()` thường là một `Saml2AuthenticatedPrincipal` sau khi validation thành công. Javadoc Spring Security 6.x định nghĩa các getter:

```java
<A> A getFirstAttribute(String name)
<A> List<A> getAttribute(String name)
Map<String, List<Object>> getAttributes()
```

- `getAttributes()`: map toàn bộ tên attribute đã được chuyển đổi sang danh sách giá trị Java.
- `getAttribute("...")`: lấy **danh sách**, thường `null` nếu không có attribute; generic type `<A>` **không bảo đảm runtime type** của mọi phần tử.
- `getFirstAttribute("...")`: lấy giá trị đầu tiên hoặc `null`. Chỉ dùng khi IdP contract định nghĩa thuộc tính **đơn trị** và dữ liệu sai cardinality đã được xử lý; getter này **không tự xác nhận** danh sách có đúng một giá trị.
- `getName()` của principal theo cấu hình SAML mặc định thường ánh xạ từ `NameID`; không đồng nghĩa với `getFirstAttribute("mail")`.

Ví dụ ngắn gọn cho việc phân biệt:

```java
// Fragment nằm trong controller/service, chỉ sau khi SAML authentication thành công.
String mail = principal.getFirstAttribute("urn:example:claims:mail");
List<Object> groups = principal.getAttribute("urn:example:claims:groups");
Map<String, List<Object>> attributes = principal.getAttributes();
```

Đây chỉ là fragment; nó giả định `principal` là biến kiểu `Saml2AuthenticatedPrincipal` đã được Spring Security cung cấp. **Không** dùng `List<String> groups = principal.getAttribute(...)` mà không kiểm tra type nếu IdP có thể gửi XML/giá trị phức hợp.

### 6.1. Controller ví dụ: xử lý scalar và list có kiểm tra

Ví dụ dưới đây dành cho ứng dụng Spring MVC có dependency Spring Security SAML2 Service Provider và đã cấu hình IdP. Nó là **class Java độc lập ở mức source** trong project Spring, nhưng không chạy chỉ bằng `javac` thuần vì cần thư viện Spring và một ứng dụng đã đăng nhập SAML.

Tạo `SamlProfileController.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class SamlProfileController {

    private static final String MAIL = "urn:example:claims:mail";
    private static final String GROUPS = "urn:example:claims:groups";

    public record Profile(String subject, String mail, List<String> groups) {}

    @GetMapping("/api/me/saml")
    public Profile profile(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {

        if (principal == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        String mail = requiredScalarString(principal.getAttribute(MAIL));
        List<String> groups = optionalStringList(principal.getAttribute(GROUPS));
        return new Profile(principal.getName(), mail, groups);
    }

    private static String requiredScalarString(List<Object> values) {
        if (values == null || values.size() != 1) {
            throw new ResponseStatusException(
                    HttpStatus.FORBIDDEN, "Invalid cardinality for mail");
        }
        Object raw = values.get(0);
        if (!(raw instanceof String)) {
            throw new ResponseStatusException(
                    HttpStatus.FORBIDDEN, "Invalid type for mail");
        }
        String value = (String) raw;
        if (value.isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.FORBIDDEN, "Empty required mail");
        }
        return value;
    }

    private static List<String> optionalStringList(List<Object> values) {
        if (values == null) {
            return List.of();
        }
        Set<String> distinct = new LinkedHashSet<>();
        for (Object raw : values) {
            if (!(raw instanceof String)) {
                throw new ResponseStatusException(
                        HttpStatus.FORBIDDEN, "Invalid groups value type");
            }
            String group = (String) raw;
            if (group.isBlank()) {
                throw new ResponseStatusException(
                        HttpStatus.FORBIDDEN, "Blank groups value");
            }
            distinct.add(group);
        }
        return new ArrayList<>(distinct);
    }
}
```

**Giải thích chính xác:**

- `MAIL` và `GROUPS` là **tên do IdP/SP thống nhất**; đổi thành tên thực tế, không tự thay bằng `FriendlyName`. Ví dụ trả các claims đã chọn cho **chính user đang login**. Endpoint phải có rule `authenticated()` và chính sách bảo vệ thông tin cá nhân phù hợp; không đưa toàn bộ assertion ra JSON.
- `requiredScalarString` **kiểm tra danh sách có đúng 1 phần tử** rồi mới lấy nó. Email có nhiều giá trị sẽ bị từ chối theo hợp đồng ví dụ, thay vì âm thầm chọn một giá trị.
- `optionalStringList` xử lý trường hợp thiếu như danh sách rỗng và chủ động từ chối giá trị không phải String. `LinkedHashSet` loại trùng và giữ thứ tự xuất hiện trong dữ liệu của ví dụ; **việc loại trùng chỉ hợp lý cho nhóm được coi là tập hợp**, không áp dụng mù quáng với mọi attribute.
- Trong ứng dụng thật, lỗi schema IdP có thể được phản hồi bằng lỗi nghiệp vụ/log phù hợp; `403` trong ví dụ là lựa chọn minh họa cho yêu cầu claim không đáp ứng policy của endpoint, **không phải status bắt buộc của SAML protocol**. Tránh để các validation message nội bộ lộ chi tiết quá mức ra client.
- Generic `principal.getAttribute(MAIL)` được Java suy diễn kiểu theo tham số `List<Object>`; trong runtime vẫn phải kiểm tra từng phần tử. Với giá trị phức hợp cần converter/validation riêng.
- Vì mã nằm trong Spring MVC, không tự chạy chương trình này bằng `java SamlProfileController`; nó cần startup của ứng dụng Spring, IdP registration và một session SAML hợp lệ.

### 6.2. Đăng nhập SAML và truy cập principal

Lớp security configuration tối thiểu (cần dependency/config IdP thực tế):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/me/saml").authenticated()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Spring Security cần `RelyingPartyRegistration`/metadata IdP tin cậy, certificate ký, `entityId`, ACS URL và các thiết lập phù hợp. Đường dẫn ACS mặc định và cơ chế certificate/validator thay đổi theo phiên bản/cấu hình, không phụ thuộc vào controller `/api/me/saml`. Controller chỉ được gọi sau khi hệ thống đã cấp Authentication thành công.

**Lưu ý phiên bản:** ví dụ dùng API phổ biến của **Spring Security 6.x**. Khi nâng cấp Spring Security major version, kiểm tra Javadoc và migration guide vì lớp authentication/principal và converter có thể được thay đổi; không lấy một mẫu cũ rồi mặc định là API ổn định mãi mãi.

## 7. Bài thực hành Java 17 thuần: đếm và kiểm tra cardinality

Để quan sát “đơn trị khác đa trị” mà không cần kết nối IdP, ta giả lập **map đã được kiểm tra và chuyển đổi**. Chương trình sau **không nhận hoặc xác thực SAML XML**; nó chỉ diễn giải danh sách các giá trị đã có.

Lưu `AttributeCardinalityDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class AttributeCardinalityDemo {

    static String requiredOneString(
            Map<String, List<Object>> attributes, String name) {

        List<Object> values = attributes.get(name);
        if (values == null || values.size() != 1) {
            throw new IllegalArgumentException("Expected one value: " + name);
        }
        Object raw = values.get(0);
        if (!(raw instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException("Invalid string: " + name);
        }
        return text;
    }

    static List<String> optionalStringSet(
            Map<String, List<Object>> attributes, String name) {

        List<Object> values = attributes.get(name);
        if (values == null) {
            return List.of();
        }
        Set<String> distinct = new LinkedHashSet<>();
        for (Object raw : values) {
            if (!(raw instanceof String text) || text.isBlank()) {
                throw new IllegalArgumentException("Invalid value: " + name);
            }
            distinct.add(text);
        }
        return new ArrayList<>(distinct);
    }

    public static void main(String[] args) {
        Map<String, List<Object>> attributes = new LinkedHashMap<>();
        attributes.put("mail", List.<Object>of("linh@example.org"));
        attributes.put("groups", List.<Object>of(
                "portal-readers", "invoice-approvers", "portal-readers"));
        attributes.put("costCenters", List.of());

        System.out.println("mail = "
                + requiredOneString(attributes, "mail"));
        System.out.println("groups = "
                + optionalStringSet(attributes, "groups"));
        System.out.println("costCenters present = "
                + attributes.containsKey("costCenters"));
        System.out.println("costCenters values = "
                + attributes.get("costCenters").size());
        System.out.println("department present = "
                + attributes.containsKey("department"));

        try {
            requiredOneString(attributes, "groups");
        } catch (IllegalArgumentException ex) {
            System.out.println("groups as scalar = rejected");
        }
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac AttributeCardinalityDemo.java
java AttributeCardinalityDemo
```

Stdout chính xác:

```text
mail = linh@example.org
groups = [portal-readers, invoice-approvers]
costCenters present = true
costCenters values = 0
department present = false
groups as scalar = rejected
```

Quan sát quan trọng:

- `mail` có đúng một chuỗi → đọc scalar được.
- `groups` có ba giá trị gốc, trong đó `portal-readers` xuất hiện hai lần. Chính sách demo coi nhóm như tập hợp nên kết quả là hai nhóm. **SAML gốc không tự động xóa giá trị trùng.**
- `costCenters` có key nhưng danh sách rỗng → **present-empty**. `department` không có key → **absent**. Trong SAML real-world converter có thể làm khác khi chuyển một Attribute không có values; bài demo chỉ phân biệt hai trạng thái trong Java map.
- Cố đọc `groups` như scalar bị từ chối thay vì lẳng lặng lấy phần tử đầu. Đó là quyết định nghiệp vụ đúng với hợp đồng đa trị của ví dụ.
- Kết quả không chứng minh chữ ký, subject, issuer, audience hoặc source-of-truth của bất kỳ assertion nào. Hệ thống thật phải xác thực SAML **trước** khi chạy các hàm này.

## 8. Ánh xạ các attributes sang domain model

Cùng một SAML payload không nên được truyền nguyên xi tới mọi tầng ứng dụng. Nên tạo một lớp biên chuyển đổi **external claims → internal profile**, định nghĩa schema rõ ràng:

```text
SAML Claim (issuer, NameFormat, Name, values)
       ↓ validation & policy
ExternalIdentity {
  issuer
  subjectId
  tenantId / registrationId
  email: Optional<String>
  department: Optional<String>
  groups: Set<String>
}
       ↓ identity linking / business authorization
InternalUser {
  userId
  tenantId
  active
  appRoles
  object-level permissions
}
```

Không bắt buộc app dùng model y hệt, nhưng phải có **hợp đồng** cho từng trường.

| Thuộc tính | Hợp đồng minh họa | Nếu sai hợp đồng |
| --- | --- | --- |
| `employeeId` | Exactly one, non-blank, String, đúng issuer/tenant | Reject account mapping / báo lỗi cấp phát thuộc tính |
| `mail` | Zero or one, chuẩn email nếu app dùng gửi thông báo | Không dùng làm khóa duy nhất; tùy policy default/không hiển thị |
| `displayName` | Zero or one, độ dài và escaping phù hợp UI | Dùng subject ID làm fallback hiển thị nếu hợp lý |
| `groups` | Zero or many, mỗi value là một group ID đã cho phép | Absent → không có quyền nhóm, wrong type → reject hoặc fail closed |
| `costCenters` | Zero or many, mã đơn vị hợp lệ | Đánh dấu dữ liệu thiếu thay vì đoán một đơn vị |
| `locale` | Zero or one theo BCP 47 nếu profile quy định | Dùng locale mặc định của ứng dụng |
| `isContractor` | Zero or one, boolean theo profile type | Không suy diễn tùy ý từ text `"false"`/`"0"` |

### 8.1. Thứ tự xử lý hợp lý

1. **Verify SAML** bằng provider tin cậy và đúng registration; không đọc raw XML vào domain model trước đó.
2. **Resolve canonical identity** dựa trên issuer/subject/tenant. Email chỉ là một claim, không phải ID toàn cầu bảo đảm ổn định.
3. **Select** attributes theo tên kỹ thuật/schema đã thỏa thuận; nếu cần xét NameFormat, kiểm tra tại tầng cấu hình/converter thích hợp, vì getter map có thể đã mất context này.
4. **Validate cardinality**: required 1 → chính xác 1; optional 1 → 0 hoặc 1; collection → 0..N theo giới hạn.
5. **Validate type và content**: String/number/bool/complex XML, độ dài, allowed character set, format theo hợp đồng; giá trị malformed phải thất bại an toàn.
6. **Normalize** có mục đích: trim/lowercase chỉ khi business contract quy định. Ví dụ group ID có thể phân biệt hoa thường; email normalization và Unicode handling cần policy riêng.
7. **Authorize**: ánh xạ external groups vào allowlist roles, hoặc tra quyền từ database nội bộ. Không tin mọi group string đều là một Spring `ROLE_*` hợp lệ.
8. **Persist/cache tối thiểu**: chỉ giữ những claims cần dùng, có TTL và quy trình refresh/revoke khi IdP thay đổi.

### 8.2. “Groups” không đương nhiên là GrantedAuthority

Giả sử IdP gửi:

```text
groups = ["portal-readers", "invoice-approvers"]
```

Ứng dụng có thể chủ động quy định:

| External group được IdP gửi | Internal authority | Chính sách |
| --- | --- | --- |
| `portal-readers` | `ROLE_PORTAL_READER` | Chỉ đọc thông tin portal |
| `invoice-approvers` | `INVOICE_APPROVE` | Được tham gia phê duyệt nếu còn thỏa object/tenant policy |
| Group ngoài allowlist | Không có authority tương ứng | Mặc định không nâng quyền |

Spring Security không mặc định biến toàn bộ `groups` thành authority có quyền tương đương chuỗi gốc. Việc mapping thành `GrantedAuthority` là **quyết định cấu hình/ứng dụng**. Nếu dùng custom authentication converter/authorities mapper, phải **giữ các kiểm tra SAML mặc định** và chỉ xử lý claims **sau validation**. Đừng cấu hình `hasRole("ADMIN")` chỉ dựa vào substring `"admin"` trong một nhóm nào đó.

Đối với nhiều tenant, cần phân biệt key nguồn như `(issuer, tenant, subject)` và mapping nhóm theo tenant. Group `admins` của tenant A không thể tự động trở thành `ROLE_ADMIN` của tenant B.

### 8.3. Không tự chọn “primary” từ danh sách đa trị

Nếu IdP trả hai email hoặc hai địa chỉ, `getFirstAttribute("mail")` sẽ che khuất bất thường. Ứng dụng cần:

- Thêm một thuộc tính riêng như `preferredMail` có hợp đồng đơn trị, **hoặc**
- Quy định một quy tắc xác định primary có nguồn dữ liệu/hợp đồng cụ thể, **hoặc**
- Từ chối mơ hồ, yêu cầu quản trị IdP điều chỉnh mapping.

Không dựa vào thứ tự XML vì phía IdP có thể thay đổi thứ tự trong lần phát assertion tiếp theo.

## 9. AttributeStatement và requested attributes trong metadata

IdP có thể biết SP cần dữ liệu gì thông qua cấu hình kết nối hoặc `AttributeConsumingService` trong SAML SP metadata, bên trong có các `RequestedAttribute`. Tuy vậy, **requested** chỉ biểu đạt nhu cầu/điều khoản liên thông, không chứng minh IdP đã phát dữ liệu.

Ví dụ fragment metadata minh họa:

```xml
<md:AttributeConsumingService
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    index="1">
    <md:ServiceName xml:lang="en">Learning Portal</md:ServiceName>
    <md:RequestedAttribute
        Name="urn:example:claims:mail"
        NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
        isRequired="true"/>
    <md:RequestedAttribute
        Name="urn:example:claims:groups"
        NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
        isRequired="false"/>
</md:AttributeConsumingService>
```

- `RequestedAttribute` trong **metadata** khác `Attribute` thực tế trong **AttributeStatement**.
- `isRequired="true"` thể hiện nhu cầu SP theo profile/thoả thuận; SP vẫn phải kiểm tra dữ liệu thực nhận và chính sách khi nó vắng mặt.
- Không phải IdP nào cũng tự đọc/đáp ứng metadata hoàn toàn theo cách giống nhau; có nhà cung cấp cấu hình attribute release thủ công.
- Nếu SP cần mảng groups, hợp đồng phải ghi rõ **giá trị đa trị thực**: nhiều `AttributeValue`; nếu provider chỉ xuất một chuỗi kết hợp, phải thống nhất parser.
- Không nhét nhiều dữ liệu cá nhân “cho tiện” khi ứng dụng chỉ cần vài trường. Data minimization giảm rủi ro lộ thông tin và ràng buộc đồng bộ phức tạp.

## 10. Các lỗi tích hợp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra và xử lý |
| --- | --- | --- |
| `getFirstAttribute("groups")` chỉ thấy một nhóm | Dùng getter đơn trị cho thuộc tính đa trị | Dùng `getAttribute("groups")`, xác nhận số `AttributeValue` sau validation |
| Getter trả `null` dù IdP “đã cấu hình groups” | Lệch `Name`/`NameFormat`, thiếu release policy, sai registration | Đối chiếu tên kỹ thuật/cấu hình IdP, kết quả principal đã xác thực |
| Chỉ có `NameID`, không có `mail` | IdP không phát AttributeStatement hoặc mapping thiếu | Không giả định NameID tự tạo thuộc tính email |
| Nhận một chuỗi `"A;B;C"` thay vì 3 phần tử | IdP serialize list vào một value | Thống nhất schema, ưu tiên nhiều `AttributeValue`; chỉ parse theo hợp đồng |
| Ép `List<String>` rồi gặp ClassCastException | Giá trị Java thực tế khác kiểu mong đợi | Dùng `List<Object>`, kiểm tra `instanceof` và parser cụ thể |
| Groups có hai value trùng nhau | IdP tạo trùng, hoặc mapping tổng hợp | Với semantics set, dedup có chủ đích; test đặc điểm dữ liệu |
| Attribute có hai `NameFormat` khác nhau nhưng cùng `Name` | Namespace/schema không đồng nhất | Kiểm tra cấu hình/converter trước khi đưa vào map key string |
| Có `FriendlyName=mail` nhưng `Name` là OID | Code tìm `mail` thay vì tên chuẩn | Dùng `Name` thực tế, không dùng FriendlyName thay khóa |
| Permission quá rộng | Direct group → ROLE không có allowlist, không check tenant | Mapping quyền rõ ràng + policy theo tài nguyên |
| Đổi group ở IdP nhưng app vẫn thấy quyền cũ | Session giữ snapshot claims từ login trước | Định nghĩa refresh/re-login/revoke và timeout |
| Assertion có `EncryptedAttribute` nhưng getter thiếu | SP không có khóa/cấu hình giải mã phù hợp hoặc lỗi decrypt | Kiểm tra khả năng giải mã OpenSAML/Spring và lỗi authentication |
| Attribute complex XML bị thành chuỗi khó hiểu | Converter không hỗ trợ kiểu phức hợp | Thiết kế codec/schema phù hợp, kiểm tra sau validation |
| Production khác môi trường dev | IdP config khác, metadata/certificate phiên bản khác | Version hóa mapping, test assertion mẫu giả và log mã lỗi an toàn |

### 10.1. Quy trình debug không rò dữ liệu

1. Kiểm tra đăng nhập SAML **có thành công** không. Nếu chưa thành công, điều tra signature/trust/time/audience/ACS trước; đừng điều chỉnh cardinality để “bỏ qua” lỗi authentication.
2. Sau validation trong môi trường kiểm thử, chỉ log tên của các keys/có bao nhiêu values và Java class type, **không log giá trị danh tính** nếu không cần. Với production, dữ liệu keys cũng có thể nhạy cảm; sử dụng allowlist và hạn chế audit.
3. So sánh hợp đồng mapping: `Name` chính xác, `NameFormat`, số values, type và encoding; kiểm tra IdP attribute release.
4. Thử 0/1/2+ values cho từng trường có ràng buộc, nhất là required scalar và groups.
5. Đối chiếu behavior của phiên bản Spring Security/OpenSAML đang sử dụng; đừng dựa vào một screenshot SAML từ phiên bản provider khác.
6. Chỉ sau khi đúng dữ liệu, mới kiểm tra mapping domain và authorization.

## 11. Bảo mật: attributes là claims, không phải giấy phép vượt quyền

### 11.1. Kiểm tra assertion là điều kiện tiên quyết

SAML attribute có thể đi qua browser dưới dạng XML/Base64, nên SP phải kiểm tra:

- Signing key thuộc đúng IdP được tin; signature hợp lệ và bảo vệ **đúng assertion được dùng**.
- `Issuer`, SP `entityID`/`AudienceRestriction`, `Destination`, ACS/`Recipient` và `InResponseTo` khi áp dụng.
- `NotBefore`/`NotOnOrAfter`, subject confirmation, response validity, anti-replay theo policy.
- Decryption của `EncryptedAttribute` nếu có, dùng khóa/cấu hình phù hợp; encryption **không thay thế** signature validation.
- Registration/tenant/account mapping đúng trust boundary; không liên kết users bằng email từ hai IdP mà chưa có quy trình tin cậy.

Cần bảo vệ khỏi XML signature wrapping: không dùng một assertion được ký để “bật đèn xanh” rồi đọc attributes từ assertion chưa được ký khác trong cùng XML. Tránh tự parse raw SAMLResponse trong controller. Ứng dụng nên dùng kết quả **đã xác thực** do Spring Security tạo.

### 11.2. Cardinality tác động đến an toàn

**Scalar confusion:** Nếu trường `isAdmin` được quy định là boolean đơn trị nhưng IdP gửi `true` và `false`, chọn phần tử đầu hoặc cuối khiến kết quả phụ thuộc thứ tự. Phải reject input trái hợp đồng hoặc có chính sách an toàn xác định.

**Group injection:** Nếu groups là danh sách và code dùng `contains("admin")` trên toàn chuỗi CSV, `not-admin` có thể bị hiểu nhầm thành admin. Kiểm tra **phần tử nguyên vẹn** sau mapping rõ ràng, không substring.

**Type confusion:** Value kiểu XML phức hợp hoặc kiểu số được converter đưa vào Java object khác với String. Ép kiểu không kiểm tra có thể gây lỗi, hoặc nếu gọi `toString()` rồi parse sai sẽ sinh quyền không mong muốn.

**Cardinality explosion:** Attribute đa trị có thể chứa rất nhiều values hoặc value quá dài. Dù được IdP ký, ứng dụng cần giới hạn hợp lý để tránh bộ nhớ/log/CPU tăng đột biến; các giá trị ngoại lệ nên bị xử lý rõ ràng.

**Duplicate ambiguity:** Với cùng key xuất hiện nhiều lần, các thành phần có thể chọn merge/first/last khác nhau. Cấu hình chính sách nhất quán, test dữ liệu đối nghịch và reject xung đột ở thuộc tính nhạy cảm.

**XSS/PII:** `displayName`, `department`, `mail` có thể chứa chuỗi không phù hợp HTML/JSON log. Dùng escaping/output encoding khi hiển thị; không trả toàn bộ `getAttributes()` ra client mặc định.

**Authorization:** Attribute groups chỉ là nguồn dữ liệu để **quyết định mapping**. Spring Security cần authority policy và kiểm tra quyền đối với endpoint, tenant và object. Login thành công không tự động cho phép truy cập mọi dữ liệu.

### 11.3. Không lưu claims vô thời hạn

Assertion thường tồn tại ngắn để xác thực, còn phiên ứng dụng có thể dài hơn. Sau SSO, thuộc tính được giữ theo phiên hoặc account cache tùy ứng dụng. Nếu nhóm bị thu hồi ở IdP, quyền trong session có thể cũ; hệ thống nhạy cảm cần timeout ngắn, kiểm tra quyền động hoặc cơ chế yêu cầu đăng nhập lại/tái phát claims. Cần thống nhất ai là **source of truth** cho mỗi thuộc tính: IdP, HR, directory service hay ứng dụng.

## 12. Bài tập tích hợp có tiêu chí chấp nhận

Thiết kế một ứng dụng SAML SP với hợp đồng:

```yaml
# Hợp đồng tài liệu minh họa, KHÔNG phải Spring Boot properties
issuer: "https://idp.example.org/saml"
attributes:
  employeeId:
    samlName: "urn:example:claims:employeeId"
    type: string
    cardinality: "1..1"
  mail:
    samlName: "urn:example:claims:mail"
    type: string
    cardinality: "0..1"
  groups:
    samlName: "urn:example:claims:groups"
    type: string
    cardinality: "0..N"
    semantics: set
    allowedValues:
      - portal-readers
      - invoice-approvers
  costCenters:
    samlName: "urn:example:claims:costCenters"
    type: string
    cardinality: "0..N"
```

Đọc hợp đồng:

- `employeeId` là bắt buộc đơn trị: thiếu, trống hoặc 2 values phải **thất bại mapping**.
- `mail` có thể thiếu, nhưng nếu có phải duy nhất và đúng validation format.
- `groups` là tập hợp đa trị, được allowlist khi chuyển sang app roles. Group lạ **không** làm tăng quyền.
- `costCenters` là danh sách tùy chọn, không tự lấy trung tâm chi phí đầu tiên làm “default”.
- `issuer` là IdP đã tin; hợp đồng này **không thay** cấu hình xác minh signature và các điều kiện SAML.

### 12.1. Bộ test gợi ý

| Dữ liệu input giả lập sau validation | Expected result |
| --- | --- |
| `employeeId=["E-123"]`, `groups=["portal-readers","invoice-approvers"]` | Accept; user có 2 groups, quyền chỉ theo mapping |
| `employeeId=[]` | Reject required scalar |
| `employeeId=["E-123","E-124"]` | Reject multiple values |
| `groups=[]` hoặc missing | Accept user không có group-specific roles (nếu policy cho phép) |
| `groups=["portal-readers","portal-readers"]` | Dedup theo chính sách set |
| `groups=["portal-readers,invoice-approvers"]` | Một value; không split nếu contract không quy định |
| `groups=["ROLE_ADMIN"]` ngoài allowlist | Không cấp authority quản trị |
| `mail=["a@example.org","b@example.org"]` | Reject sai cardinality 0..1 |
| `mail=[""]` | Reject nếu email phải non-blank khi hiện diện |
| `costCenters=["C01","C02","C03"]` | Giữ cả 3 values; không tự chọn C01 |
| Group value là đối tượng không phải String | Reject/schema error; không ép kiểu mù |
| FriendlyName đúng nhưng Name sai | Không ánh xạ nhầm sang attribute yêu cầu |
| Cùng Name khác NameFormat, cấu hình chưa rõ | Reject hoặc sửa hợp đồng mapping, không âm thầm gộp |
| Assertion signature invalid hoặc wrong audience | Từ chối authentication **trước** khi đụng mapping |
| Có hai assertions, provider chọn sai nội dung | Chỉ dùng attributes từ assertion đã được xác minh và hỗ trợ theo converter |

Test **SAML nhận thực** cần IdP kiểm thử hoặc bộ fixture được ký bằng khóa **test** và môi trường tách biệt. Không gửi dữ liệu khách hàng hoặc assertions thật qua công cụ debug công khai. Test **mapping logic** có thể dùng unit tests chỉ với `Map<String, List<Object>>` như bài Java thuần.

### 12.2. Tiêu chí một tích hợp hoàn chỉnh

- Đã thống nhất `Name`, `NameFormat`, kiểu dữ liệu, cardinality, optional/required và semantics cho từng attribute với IdP.
- Đã xác thực hiện vật SAML và tin cậy IdP/SP bằng Spring Security trước khi lấy claims.
- Mỗi scalar được kiểm tra đúng 0..1 hay 1..1; mỗi multi-value được giữ đủ giá trị hoặc chuẩn hóa theo quy tắc minh bạch.
- Không dùng `FriendlyName` làm khóa canonical, không dùng `getFirstAttribute()` để làm mất thông tin đa trị.
- Không cấp quyền trực tiếp từ unrecognized group hay từ thuộc tính chưa map.
- Có test âm tính cho missing/empty/duplicate/wrong type, test nhiều IdP và test nhóm chứa dấu phân tách.
- Có cơ chế refresh/revoke quyền khi claim thay đổi, và log không tiết lộ PII hoặc raw assertion.
- Đã đối chiếu Spring Security version để biết chính xác behavior của bộ chuyển đổi SAML attributes.

## 13. Câu hỏi ôn tập

**1. Một `Attribute` có hai `AttributeValue` nghĩa là gì?**  
Đó là **hai giá trị** của cùng một thuộc tính; không phải hai thuộc tính đơn trị. Với `groups`, dùng danh sách và áp dụng policy; không chỉ lấy phần tử đầu.

**2. `FriendlyName=groups` có đủ để chọn attribute không?**  
Không. `FriendlyName` là nhãn dễ đọc, không phải định danh chuẩn. Dùng `Name` và xét `NameFormat`/namespace theo hợp đồng IdP/SP.

**3. `NameID` có tự xuất hiện trong `getAttributes().get("mail")` không?**  
Không mặc định. `NameID` nằm trong `Subject`; thuộc tính mail chỉ xuất hiện nếu IdP phát attribute tương ứng và converter ánh xạ nó.

**4. `getFirstAttribute("department")` trả `null` có nghĩa không có `AttributeStatement`?**  
Không thể kết luận. Có thể attribute absent, mapping name sai, value list rỗng hoặc provider xử lý dữ liệu theo cách khác. Kiểm tra hợp đồng và kết quả principal đã xác minh.

**5. Hai values `"reader"` và `"editor"` có tương đương một value `"reader,editor"` không?**  
Không. Một chuỗi có delimiter vẫn là một `AttributeValue`; chỉ parse nếu hợp đồng quy định serialization như vậy.

**6. Đọc `groups` từ authenticated principal có đồng nghĩa được phép cấp `ROLE_ADMIN`?**  
Không. Authenticated principal chứa claims từ IdP đã tin, nhưng quyền ứng dụng phải đi qua allowlist/mapping và kiểm tra authorization.

**7. Spring Security getter trả `List<A>` thì có thể chắc chắn đó là `List<String>`?**  
Không. Generic không chứng minh kiểu ở runtime. Cần validate từng phần tử theo schema đã thống nhất.

**8. Tại sao email không nên luôn là khóa liên kết account giữa các IdP?**  
Email có thể thay đổi, trùng, chưa xác minh hoặc không ổn định; cần phân biệt issuer, subject và tenant, dùng cơ chế account linking có kiểm soát.

## 14. Tài liệu chuẩn và tài liệu Spring Security

- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf) – `AttributeStatement`, `Attribute`, `AttributeValue`, `NameFormat`, `FriendlyName` và quy định về giá trị.
- [OASIS SAML 2.0 Errata 05](https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html) – làm rõ cách định danh attribute qua `NameFormat` và `Name`.
- [Spring Security: Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html) – sử dụng `Saml2AuthenticatedPrincipal` và `getFirstAttribute`/`getAttribute`, customization.
- [Spring Security: SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) – vị trí AttributeStatement trong login flow và quá trình tạo principal.
- [Spring Security 6.5 Javadoc: Saml2AuthenticatedPrincipal](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html) – chữ ký kiểu Java của `getAttributes()`, `getAttribute()` và `getFirstAttribute()`.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet) – sử dụng assertion an toàn, XML signature, audience và điều kiện xác thực.

**Ghi nhớ:** `AttributeStatement` mang các **thuộc tính** của subject; mỗi `Attribute` có thể mang **0, 1 hoặc nhiều AttributeValue**. Ứng dụng phải hiểu cardinality theo hợp đồng IdP/SP, kiểm tra kiểu, chọn đúng tên định danh, giữ đủ dữ liệu đa trị và chỉ chuyển claims đã xác minh thành quyền theo chính sách của mình.