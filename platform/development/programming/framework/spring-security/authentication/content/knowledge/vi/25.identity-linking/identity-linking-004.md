# Ánh xạ thuộc tính SAML, NameID và tài khoản nội bộ trong liên kết danh tính

## 1. Bài toán: SSO thành công nhưng ứng dụng nhận diện ai?

Trong ứng dụng dùng **Spring Security SAML 2.0 Service Provider (SP)**, Identity Provider (IdP) xác thực một người dùng và gửi `SAML Response` chứa `Assertion`. Sau khi SP **xác minh** assertion, ứng dụng phải trả lời thêm câu hỏi nghiệp vụ: **danh tính bên IdP này tương ứng với tài khoản nội bộ nào?** Đó là quá trình *identity linking/account linking*.

Ví dụ, hệ thống quản lý học tập có tài khoản nội bộ `user_id=u-42`. IdP gửi:
- `NameID`: `opaque-abc-789`, định dạng `persistent`.
- `email`: `lan@old.example`.
- `displayName`: `Lan Nguyen`.
- `department`: `Training`.

Sau vài tháng, người dùng đổi email thành `lan@new.example` nhưng vẫn giữ `NameID` ổn định. Hệ thống phải đăng nhập **đúng `u-42`**, không tự tạo tài khoản khác. Ngược lại, nếu một IdP khác tình cờ gửi cùng chuỗi `opaque-abc-789`, hệ thống **không được** coi đó là cùng người.

Sau bài này, bạn sẽ:
1. Đọc đúng `NameID`, `Format`, `NameQualifier`, `SPNameQualifier` và SAML attributes.
2. Chọn khóa liên kết danh tính bền vững, có ranh giới IdP/SP/tenant rõ ràng.
3. Tách **xác thực assertion** khỏi **tìm hoặc liên kết tài khoản nội bộ**.
4. Xử lý đăng nhập lần đầu, đổi email, đổi NameID, trùng khóa, xóa/khóa tài khoản và thay đổi nhóm quyền.
5. Hiểu vị trí của `Saml2AuthenticatedPrincipal`, `RelyingPartyRegistration` và service ánh xạ trong Spring Security.
6. Kiểm thử logic liên kết bằng chương trình Java 17+ cùng các ca âm tính quan trọng.

**Phạm vi:** SAML 2.0 Web Browser SSO, ứng dụng Java/Spring Security servlet, quá trình ánh xạ danh tính sang tài khoản của **chính ứng dụng**. Đây không phải bài về cách tự tạo chữ ký SAML hoặc tự viết SAML parser.

## 2. Ba lớp dữ liệu không được nhập nhằng

| Lớp | Ai quyết định | Ví dụ | Được tin cậy đến đâu? |
| --- | --- | --- | --- |
| **SAML authentication** | SP xác minh assertion từ IdP đã tin cậy | `Issuer`, `Subject/NameID`, `AudienceRestriction`, `InResponseTo`, chữ ký, thời hạn | Chỉ sau khi xác minh thành công theo cấu hình RP |
| **Identity linking** | Ứng dụng quản lý tài khoản nội bộ | External identity key → `local_account.id` | Do luật liên kết, dữ liệu đã được phê duyệt và ràng buộc unique của ứng dụng quyết định |
| **Application authorization** | Ứng dụng + chính sách nghiệp vụ | `u-42` có được xem báo cáo hay quản trị tenant A không? | Không suy ra chỉ từ sự kiện SSO thành công |

Luồng chuẩn:

~~~text
Browser -> Service Provider (Spring Security) -> Identity Provider
             ^                                  |
             |----- SAML Response (qua browser)-|
             |
   [1] Xác minh Response/Assertion theo metadata/cert của IdP
             |
   [2] Tạo Authentication đã xác thực + đọc NameID/attributes tin cậy
             |
   [3] Resolve (tenant, SP, IdP, NameID) -> local_account.id
             |
   [4] Kiểm tra tài khoản nội bộ active và chính sách cấp quyền
             |
   [5] Tạo phiên ứng dụng / cho truy cập đúng dữ liệu của tài khoản
~~~

**Không bao giờ làm [3] trước [1].** Các trường trong SAML XML chưa xác minh cũng chỉ là dữ liệu do bên gửi tự khai. Chỉ truyền một đối tượng danh tính đã đi qua SAML authentication đáng tin cậy tới thành phần linking.

## 3. NameID là gì, dùng làm khóa lúc nào?

Trong một SAML Assertion, `<Subject><NameID>...` mô tả tên định danh của principal theo **một định dạng và phạm vi nhất định**. NameID **không mặc định là email** và cũng không mặc định ổn định qua các phiên.

Các thành phần cần đọc:

- **Value**: nội dung text của NameID, có thể là opaque identifier, UPN/email hoặc chuỗi khác.
- **Format**: URI cho biết cách hiểu identifier.
- **NameQualifier**: ngữ cảnh định danh do namespace/IdP gắn; với persistent identifiers có ngữ nghĩa liên quan nơi tạo identifier.
- **SPNameQualifier**: ngữ cảnh service provider mà identifier hướng tới, quan trọng khi dùng định danh *pairwise*.
- **SPProvidedID**: optional attribute theo SAML, có thể xuất hiện trong một số mô hình identifier; chỉ dùng nếu đã thiết kế rõ với IdP, không mặc định thay khóa chính.
- **Assertion/Response Issuer**: danh tính của bên phát hành/khẳng định; **phải được kiểm chứng** với IdP đã đăng ký.
- **Relying party / SP entity ID**: định danh service provider đích, giúp tránh liên kết chéo môi trường và ứng dụng.

### 3.1. Các NameID Format quan trọng

| Format | Đặc tính | Chính sách linking |
| --- | --- | --- |
| `urn:oasis:names:tc:SAML:2.0:nameid-format:persistent` | IdP dự định cung cấp identifier **ổn định, không dễ suy ra danh tính**, thường gắn với quan hệ IdP–SP | **Ưu tiên** cho khóa liên kết dài hạn khi IdP cam kết lifecycle và phạm vi |
| `urn:oasis:names:tc:SAML:2.0:nameid-format:transient` | Identifier ngắn hạn, có thể thay đổi qua phiên hoặc giao dịch | **Không** dùng làm khóa liên kết dài hạn |
| `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress` | Value thể hiện địa chỉ email theo format SAML | Không mặc định ổn định hoặc duy nhất vĩnh viễn; có thể đổi/tái cấp |
| `urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified` | Không đưa ra cam kết cụ thể về kiểu/semantics của value | Chỉ dùng nếu hai bên có hợp đồng thuộc tính, uniqueness, lifecycle rõ |
| `urn:oasis:names:tc:SAML:2.0:nameid-format:entity` | Thường là entity identifier, không phải lựa chọn bình thường cho user account | Không tự dùng để liên kết tài khoản cá nhân |

**Đặc biệt:** một `persistent` NameID được mong đợi ổn định, nhưng ứng dụng vẫn cần hợp đồng với IdP về việc tái tạo tài khoản, tenant, đổi cấu hình, chuyển IdP, thay đổi SP entity ID. Đừng lấy riêng chuỗi `NameID.Value` làm unique key toàn cục.

### 3.2. Ví dụ XML minh họa

Đây là **một mảnh Assertion chưa ký để minh họa tên trường**; không phải SAML Response hợp lệ để đăng nhập và không dùng để thử bypass xác minh.

~~~xml
<saml:Subject xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      NameQualifier="https://idp.training.example/saml"
      SPNameQualifier="https://app.training.example/saml">
    opaque-abc-789
  </saml:NameID>
</saml:Subject>
~~~

Một `AttributeStatement` độc lập có thể chứa:

~~~xml
<saml:AttributeStatement xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Attribute Name="urn:example:claims:email" FriendlyName="email">
    <saml:AttributeValue>lan@new.example</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="urn:example:claims:department" FriendlyName="department">
    <saml:AttributeValue>Training</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="urn:example:claims:groups" FriendlyName="groups">
    <saml:AttributeValue>reader</saml:AttributeValue>
    <saml:AttributeValue>trainer</saml:AttributeValue>
  </saml:Attribute>
</saml:AttributeStatement>
~~~

SAML attribute **Name** (và có thể `NameFormat`) là hợp đồng kỹ thuật cần thống nhất; `FriendlyName` chỉ giúp con người đọc, không nên là khóa ánh xạ mặc định. Một attribute có **nhiều `AttributeValue`**: nhóm quyền thường là list; không được lấy giá trị đầu tiên rồi coi đó là toàn bộ membership.

## 4. Thuộc tính nào thuộc profile và thuộc tính nào dùng để định danh?

| Thuộc tính | Mục đích thường gặp | Có nên dùng làm khóa liên kết? |
| --- | --- | --- |
| Stable/persistent `NameID` đúng issuer, format, qualifiers, SP | Định danh IdP–SP | Có, khi thỏa hợp đồng lifecycle |
| `employeeId`/immutable directory object ID được IdP bảo đảm | Định danh người nội bộ theo chính sách tổ chức | Có thể, nhưng cần ràng buộc tenant/IdP, uniqueness và chính sách tái cấp |
| `email` | Liên hệ, thông báo, hiển thị | **Không tự động**; có thể đổi, trùng, tái cấp hoặc chưa được xác minh |
| `displayName`, `givenName`, `sn` | Hiển thị giao diện | Không; thay đổi tự nhiên và không unique |
| `department` | Thông tin tổ chức | Không; có thể dùng trong policy khi nguồn đã tin cậy |
| `groups`/`roles` | Gợi ý quyền theo nhóm IdP | Không; cần allowlist và mapping quyền theo từng IdP/tenant |
| `tenantId` do tổ chức thống nhất | Tách miền dữ liệu khách hàng | Không đơn lẻ; nên là **namespace của key** và kiểm tra phù hợp |
| `sessionIndex` | Liên quan phiên SAML/logout | Không; không phải định danh người dài hạn |

Một hệ thống an toàn thường lưu `local_account.id` là mã bất biến của ứng dụng. Các liên kết SSO chỉ là quan hệ **external identity → local account**; email/profile có thể thay đổi độc lập mà `local_account.id` vẫn giữ nguyên.

**Nguyên tắc:** đừng gọi hàm “findByEmailAndLogin” rồi tự nối hai account chỉ vì email giống. Nếu attacker kiểm soát một IdP kém tin cậy hoặc tài khoản email được tái sử dụng, cách làm này có thể khiến họ nhận được dữ liệu của một tài khoản đã có.

## 5. Thiết kế khóa định danh từ IdP tới tài khoản nội bộ

Khóa ứng dụng nên tách rõ **danh tính bên ngoài** và **danh tính nội bộ**:

~~~text
External identity key
  tenant_id
  relying_party_entity_id     # hoặc mã RP ổn định do ứng dụng quản lý
  idp_entity_id               # lấy từ cấu hình IdP đã xác minh
  name_id_format
  name_qualifier              # giữ nguyên nếu hiện diện
  sp_name_qualifier           # giữ nguyên nếu hiện diện
  name_id_value               # opaque; giữ nguyên chính xác

                         UNIQUE
                            |
                            v
                     local_account.id
~~~

**Lưu ý về `registrationId` Spring Security:** `RelyingPartyRegistration` có `registrationId` như một chỉ mục cấu hình, hữu ích khi đọc principal và route. Nếu registrationId có thể đổi tên qua deployment, **không nên dùng nó một mình làm định danh lâu dài**. Dùng một ID nội bộ ổn định của quan hệ SP/IdP, đồng thời kiểm tra entity ID của IdP và RP theo metadata đã cấu hình. Nếu dùng `registrationId` trong key thì phải có kế hoạch migrate dữ liệu khi đổi tên cấu hình.

Khi so sánh opaque NameID:
- Giữ nguyên value đã nhận, không tự động `trim()`, lowercase, Unicode normalize hoặc cắt prefix/suffix khi chưa có hợp đồng với IdP.
- Áp dụng ràng buộc kích thước, null/blank và kiểu dữ liệu phù hợp; tránh ghi raw NameID vào log.
- Không dùng hash **chưa có salt/khóa** như một biện pháp bảo mật hoàn chỉnh; nếu cần privacy trong lưu trữ, cân nhắc keyed hash và đánh giá khả năng xoay khóa/migrate.
- `NameQualifier` và `SPNameQualifier` có thể bị lược bỏ theo chuẩn trong một số trường hợp. Có quy tắc canonical hóa **dựa trên contract** và không tự gán ngầm giá trị “trông có vẻ đúng”.
- Không dùng một key chung giữa production, staging, các tenant hoặc giữa hai IdP. Một chuỗi giống nhau không xác minh được hai account là một.

### 5.1. Phác thảo schema dữ liệu

Ví dụ SQL minh họa (PostgreSQL), dùng giá trị trong link theo hợp đồng định danh:

~~~sql
CREATE TABLE local_account (
    id UUID PRIMARY KEY,
    display_name TEXT NOT NULL,
    email TEXT,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'DISABLED'))
);

CREATE TABLE external_identity_link (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES local_account(id),
    tenant_id TEXT NOT NULL,
    sp_entity_id TEXT NOT NULL,
    idp_entity_id TEXT NOT NULL,
    name_id_format TEXT NOT NULL,
    name_qualifier TEXT NOT NULL DEFAULT '',
    sp_name_qualifier TEXT NOT NULL DEFAULT '',
    name_id_value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    linked_by TEXT NOT NULL,
    UNIQUE (
        tenant_id, sp_entity_id, idp_entity_id,
        name_id_format, name_qualifier, sp_name_qualifier, name_id_value
    )
);
~~~

Unique constraint ngăn **một external identity trỏ tới hai tài khoản nội bộ**. Tùy nghiệp vụ, một local account có thể liên kết nhiều IdP đã được phê duyệt, nhưng không được tạo liên kết hai chiều không kiểm soát. Trong môi trường nhiều tenant, khóa ngoại và tra cứu cũng phải kiểm tra tenant của `local_account` để tránh cross-tenant account takeover; ví dụ schema trên chỉ minh họa ý tưởng, cần bổ sung ràng buộc tenant ở mô hình production.

**Tính nguyên tử:** nếu đăng nhập đồng thời hoặc hai tiến trình cố liên kết cùng NameID, transaction + unique index là chốt bảo vệ cuối. Không nên chỉ `SELECT trước, INSERT sau` mà không xử lý xung đột.

## 6. Quy trình linking: tạo tài khoản, liên kết lần đầu, truy cập lần sau

### Trường hợp A — Pre-provisioning (khuyến nghị khi quyền cao)

1. Quản trị viên hoặc hệ thống HR/SCIM đã có `local_account.id=u-42`.
2. Qua quy trình xác minh danh tính được phê duyệt, ghi trước external identity key → `u-42`.
3. Người dùng SSO: SP xác thực SAML Response, đọc key ổn định, tra link duy nhất, xác minh local account còn active, tạo phiên ứng dụng.
4. Các attribute như `email`/`displayName` có thể đồng bộ theo quy tắc riêng, không thay khóa.

**Ưu điểm:** giảm nhầm lẫn tài khoản có dữ liệu nhạy cảm. **Đánh đổi:** cần quy trình cấp link và duy trì dữ liệu từ trước.

### Trường hợp B — Người dùng tự liên kết khi đã đăng nhập nội bộ

1. Người dùng đang có phiên nội bộ được xác thực mạnh và bắt đầu thao tác “Liên kết SSO”.
2. Ứng dụng tạo request SAML có state/relay state/correlation thích hợp, áp dụng CSRF/session binding và xác minh response đầy đủ.
3. Xác định external identity duy nhất, hỏi/ghi nhận ý định liên kết của người dùng theo thiết kế.
4. Trong transaction, bảo đảm key chưa thuộc account khác rồi gắn vào **account hiện đang đăng nhập**.
5. Ghi audit: tác nhân, thời điểm, provider, loại link, kết quả; tránh đưa raw assertion, private key hoặc NameID nhạy cảm vào log.

**Cấm đường tắt:** callback SSO bất kỳ không được quyết định tài khoản mục tiêu bằng một trường `accountId` tự nhập trong query/RelayState.

### Trường hợp C — Just-in-time provisioning (JIT)

Có thể tạo **tài khoản mới** khi assertion đã xác minh, NameID đạt chính sách ổn định, tenant/IdP cho phép JIT, và hệ thống chưa có link. Việc tạo mới phải dùng transaction và uniqueness. Nếu email trùng account cũ nhưng key không trùng, **không tự ghép**: chuyển sang xác minh bổ sung, pre-provisioning hoặc xử lý thủ công.

JIT không phù hợp với mọi dịch vụ; với hệ thống tài chính, HR hay quản trị quyền cao, thường cần approval hoặc pre-provision trước.

## 7. Đổi email, đổi tên, chuyển IdP, đổi NameID: xử lý thế nào?

| Tình huống | Quy tắc xử lý | Kết quả mong muốn |
| --- | --- | --- |
| Người dùng đổi email, NameID ổn định | Tra external key như cũ; cập nhật profile theo chính sách | Vẫn nhận đúng local account |
| Đổi tên/phòng ban | Đồng bộ thuộc tính hiển thị nếu đã cho phép | Không đổi owner của dữ liệu |
| IdP đổi `NameID.Value` do migration | Có mapping migration đã được xác minh, approval, audit và unique check | Link mới được nối có kiểm soát vào cùng local account |
| IdP khác phát cùng value | IdP entity ID trong key khác | Không lấy account của IdP cũ |
| Staging và production phát cùng value | RP/tenant/environment namespace khác | Không liên kết chéo |
| NameID `transient` | Không tạo persistent link | Từ chối linking dài hạn, chọn cơ chế khác |
| Tài khoản nội bộ bị disable | Link có thể còn để phục vụ audit, nhưng login bị chặn | Không được mở quyền lại chỉ vì IdP vẫn trả “success” |
| Một external identity đang gắn vào account A mà có yêu cầu gắn B | Unique conflict, yêu cầu quy trình giải quyết rõ | Không âm thầm thay chủ sở hữu |
| Account bị xóa/merge theo nghiệp vụ | Quản trị liên kết, quyền, dữ liệu và lịch sử | Không để link cũ tạo takeover |
| User bị xóa tại IdP rồi username/email tái cấp | Phải dựa vào ID không tái sử dụng hoặc quy trình lifecycle IdP | Không nhận nhầm người mới thành người cũ |

Khi IdP đổi tên `entityId`, thay SP entity ID hoặc đổi NameID policy, **đó là thay đổi định danh** có thể làm tất cả liên kết cũ không match. Phải có migration được đánh giá và audit; không tự fallback sang email để “chữa lỗi đăng nhập”.

## 8. Ánh xạ AttributeStatement vào dữ liệu nội bộ

Một contract kỹ thuật nên ghi rõ tên thuộc tính, kiểu, cardinality, nguồn và quy tắc cập nhật:

| SAML attribute Name (ví dụ nội bộ) | Kiểu/kỳ vọng | Thuộc tính local | Quy tắc |
| --- | --- | --- | --- |
| `urn:example:claims:email` | 0..1 string, định dạng email | `local_account.email` | Chỉ cập nhật theo chính sách verified contact, không dùng để nối account |
| `urn:example:claims:displayName` | 0..1 string | `display_name` | Giới hạn độ dài, escape khi hiển thị; không là khóa |
| `urn:example:claims:department` | 0..1 string | `department_code` | Ánh xạ qua bảng mã hợp lệ, không tự quyền admin |
| `urn:example:claims:groups` | 0..N strings | external groups / derived role | Dùng allowlist theo IdP và tenant; xác định quy tắc revoke |
| `urn:example:claims:employeeId` | 0..1 string, phải bảo đảm uniqueness/immutability | external staff identity nếu dùng | Chỉ dùng linking sau khi có hợp đồng dữ liệu rõ |

**Cardinality:** khi một thuộc tính đáng lẽ đơn trị lại trả hai email hoặc hai mã nhân viên, đừng tùy ý lấy phần tử đầu tiên. Đó có thể là lỗi cấu hình IdP hoặc dữ liệu; fail closed/quarantine theo policy.

**Cách hiển thị:** profile attributes có thể chứa dấu, Unicode, ký tự HTML. Lưu và render đúng charset, escape theo ngữ cảnh xuất hiện; không nối trực tiếp attribute từ IdP vào SQL, query filter hoặc template HTML không escape.

**Mapping groups → roles:** không ánh xạ tất cả tên group thành `ROLE_*` rồi tự tin cậy trong ứng dụng; thiết lập bảng mapping:
- IdP A / tenant training / group `training-readers` → `REPORT_READ`.
- IdP A / tenant training / group `training-admins` → `REPORT_ADMIN` chỉ khi role đã được phê duyệt.
- Các group khác không tạo quyền mặc định.

Quyền có thể cần được cập nhật mỗi login, theo cache ngắn hạn hoặc đồng bộ provisioning. Chọn chiến lược và thời gian thu hồi phù hợp vì session đang mở có thể vẫn giữ quyền cũ nếu ứng dụng không refresh.

## 9. Bảo mật: điều kiện trước khi tin bất kỳ NameID/attribute nào

SAML Response đi qua user-agent, vì vậy backend chỉ được sử dụng NameID/attributes **sau khi cơ chế SP xác minh** thành công. Kiểm tra phù hợp với cấu hình IdP và giao thức:

1. **Chữ ký và trust:** xác minh signature trên response/assertion theo profile, dùng certificate và issuer từ metadata IdP được quản trị; không bật “accept unsigned assertion”.
2. **Destination/Recipient:** response và bearer SubjectConfirmation phải nhắm đúng ACS của SP.
3. **Issuer và audience:** nguồn phát hành đúng IdP đã đăng ký; audience restriction khớp SP entity ID.
4. **Thời gian:** `NotBefore`, `NotOnOrAfter`, thời điểm phát hành và clock skew hữu hạn; không chấp nhận token hết hạn.
5. **Request correlation:** với SP-initiated SSO, đối chiếu `InResponseTo` và giao dịch đã khởi tạo; unsolicited/IdP-initiated SSO cần policy riêng, không tự cho phép mọi response.
6. **Replay:** có cơ chế chống sử dụng lại assertion/response ID khi profile và rủi ro yêu cầu; kiểm tra callback nhiều lần không tạo phiên mới bất hợp lệ.
7. **Signature wrapping/XML:** dùng thư viện SAML đã kiểm chứng; không tự parse XML rồi tách NameID bằng XPath từ một assertion chưa chắc là assertion được xác thực.
8. **Mã hóa và bảo vệ dữ liệu:** TLS, giải mã nếu assertion/attribute được mã hóa, bảo vệ private key và truststore.
9. **Chọn đúng IdP:** không tin `Issuer` do client gửi để tự động tải metadata từ URL tùy ý; metadata/cert đã nằm trong allowlist cấu hình.
10. **Authorization local:** sau khi SSO thành công, vẫn kiểm tra account active, tenant, policy và quyền nghiệp vụ; profile attribute không tự thành role.

**Identity linking không thay thế SAML validation.** Đối tượng đã “đọc được NameID” bằng decode Base64 chưa có nghĩa SSO hợp lệ. Nếu tự chỉnh converter/validator Spring Security, phải giữ các kiểm tra mặc định hoặc chứng minh bộ mới tương đương và test các trường hợp âm tính.

## 10. Áp dụng trong Spring Security SAML2 (Servlet)

Spring Security 6.x hỗ trợ SP thông qua dependency `org.springframework.security:spring-security-saml2-service-provider`; Spring Boot hỗ trợ `RelyingPartyRegistration` cấu hình theo IdP metadata. Đối với WebFlux/reactive, API cấu hình và mức hỗ trợ không tương đương code servlet dưới đây; chỉ dùng ví dụ này cho Spring MVC/Servlet.

### 10.1. Mẫu cấu hình SP

Trích `build.gradle` trong ứng dụng Spring Boot 3.3.x có plugin quản lý dependency tương ứng:

~~~groovy
repositories {
    mavenCentral()
    // Tùy phiên bản OpenSAML, có thể cần repository Shibboleth chính thức.
    maven { url 'https://build.shibboleth.net/maven/releases' }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

Bean `SecurityFilterChain` (một lớp Java biên dịch khi project đã có các dependency trên):

~~~java
package demo.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

Đoạn `application.yml` dành cho **IdP lab** (entityId, SSO URL và certificate là ví dụ cần thay bằng metadata thật đã được quản trị):

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp-lab:
            assertingparty:
              entity-id: https://idp.training.example/saml
              singlesignon:
                url: https://idp.training.example/sso
                binding: POST
              verification:
                credentials:
                  - certificate-location: classpath:corp-lab-idp.crt
~~~

Với các phiên bản/config Spring Boot cụ thể, tên property nested của SSO URL/binding có thể khác; đối chiếu tài liệu của đúng version và metadata IdP khi cấu hình thực tế. Cách dùng metadata URL của IdP hoặc xây `RelyingPartyRegistration` theo API chính thức cũng được hỗ trợ.

SP-initiated login thường bắt đầu tại `/saml2/authenticate/{registrationId}`; ACS thường là `/login/saml2/sso/{registrationId}`. Trong bài `corp-lab` là mã registration ở **phía SP**, không phải NameID của người dùng.

### 10.2. Đọc principal sau khi Spring Security xác thực

Sau một SAML authentication hợp lệ, Spring Security tạo `Saml2Authentication` với `Saml2AuthenticatedPrincipal`. Ví dụ service chỉ trích xuất một số attribute để chuyển sang tầng nghiệp vụ:

~~~java
package demo.saml;

import java.util.List;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.stereotype.Component;

@Component
public class SamlClaimsReader {

    public SamlProfile read(Saml2AuthenticatedPrincipal principal) {
        String nameIdValue = principal.getName();
        String registrationId = principal.getRelyingPartyRegistrationId();
        String email =
                principal.getFirstAttribute("urn:example:claims:email");
        String displayName =
                principal.getFirstAttribute("urn:example:claims:displayName");
        List<String> groups =
                principal.getAttribute("urn:example:claims:groups");

        return new SamlProfile(
                registrationId, nameIdValue, email, displayName,
                groups == null ? List.of() : List.copyOf(groups));
    }

    public record SamlProfile(
            String registrationId,
            String nameIdValue,
            String email,
            String displayName,
            List<String> groups) {}
}
~~~

API `getFirstAttribute` trả `null` nếu thiếu; một claim có thể có nhiều giá trị, do đó `getAttribute` trả danh sách phù hợp cho `groups`. Đừng gọi tên attribute `email` nếu IdP đã cấu hình một URI khác; mapping phải khớp hợp đồng.

**Điểm cực kỳ quan trọng:** `principal.getName()` ở flow mặc định thường được lấy từ `NameID.Value`, nhưng `Saml2AuthenticatedPrincipal` **không tự cung cấp đủ tất cả các trường Format/qualifier/issuer đã xác minh cho composite key**. Service trên chỉ đọc **một phần** dữ liệu; nó **chưa được phép tự liên kết tài khoản** bằng mỗi `registrationId + getName()`. Cần có adapter được bảo vệ ở tầng kết quả SAML validation để thu thập NameID metadata/issuer từ assertion đã kiểm chứng và đối chiếu `RelyingPartyRegistration`. Dùng API converter/provider tương ứng với phiên bản Spring Security đang chạy; không lấy Format từ request parameter do browser gửi và không parse lại untrusted XML.

Sau khi có `VerifiedExternalIdentity` do adapter tin cậy tạo, gọi `AccountLinkService.resolve(...)`, lấy local ID, chặn account disabled và áp dụng quy tắc mapping. Tích hợp vào success handler/principal mapping theo contract của hệ thống; không sửa nội dung kiểm tra cryptographic của SAML provider chỉ để đổi trường principal name.

## 11. Ví dụ Java 17+ chạy độc lập: map SAML identity đã xác minh vào account

Ví dụ sau mô phỏng **tầng linking sau khi SAML assertion đã được thư viện xác minh**. Lớp `VerifiedIdentity` là dữ liệu test tạo thủ công, **không có chức năng kiểm tra signature hoặc parse SAML**; ở production chỉ adapter tin cậy của backend được phép tạo dữ liệu tương đương. Logic cố tình chỉ cho phép NameID `persistent`, không tự nối bằng email và không JIT tạo account.

Tạo file `SamlAccountLinkDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class SamlAccountLinkDemo {
    private static final String PERSISTENT =
            "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent";
    private static final String TRANSIENT =
            "urn:oasis:names:tc:SAML:2.0:nameid-format:transient";

    record ExternalKey(
            String tenant,
            String spEntityId,
            String idpEntityId,
            String nameIdFormat,
            String nameQualifier,
            String spNameQualifier,
            String nameIdValue) {}

    record VerifiedIdentity(ExternalKey key, String email) {}

    record LocalAccount(String id, String email, boolean active) {}

    static final class LinkDirectory {
        private final Map<String, LocalAccount> accounts = new HashMap<>();
        private final Map<ExternalKey, String> links = new HashMap<>();

        void addAccount(LocalAccount account) {
            if (accounts.putIfAbsent(account.id(), account) != null) {
                throw new IllegalStateException("Duplicate local account");
            }
        }

        void linkApproved(ExternalKey key, String localId) {
            requireStableKey(key);
            if (!accounts.containsKey(localId)) {
                throw new IllegalArgumentException("Unknown local account");
            }

            String previous = links.putIfAbsent(key, localId);
            if (previous != null && !previous.equals(localId)) {
                throw new IllegalStateException("Identity already linked");
            }
        }

        Optional<LocalAccount> resolve(VerifiedIdentity identity) {
            Objects.requireNonNull(identity);
            requireStableKey(identity.key());
            String localId = links.get(identity.key());
            if (localId == null) {
                return Optional.empty();
            }
            LocalAccount account = accounts.get(localId);
            if (account == null || !account.active()) {
                return Optional.empty();
            }
            return Optional.of(account);
        }

        private static void requireStableKey(ExternalKey key) {
            Objects.requireNonNull(key);
            if (!PERSISTENT.equals(key.nameIdFormat())) {
                throw new IllegalArgumentException("Unsupported NameID format");
            }
            if (blank(key.tenant()) || blank(key.spEntityId())
                    || blank(key.idpEntityId()) || blank(key.nameIdValue())
                    || key.nameQualifier() == null
                    || key.spNameQualifier() == null) {
                throw new IllegalArgumentException("Incomplete SAML identity");
            }
        }

        private static boolean blank(String value) {
            return value == null || value.isBlank();
        }
    }

    private static String resolvedId(
            LinkDirectory directory, VerifiedIdentity identity) {
        return directory.resolve(identity)
                .map(LocalAccount::id)
                .orElse("NONE");
    }

    public static void main(String[] args) {
        ExternalKey stable = new ExternalKey(
                "tenant-a",
                "https://app.training.example/saml",
                "https://idp.training.example/saml",
                PERSISTENT,
                "https://idp.training.example/saml",
                "https://app.training.example/saml",
                "opaque-abc-789");

        LinkDirectory directory = new LinkDirectory();
        directory.addAccount(new LocalAccount(
                "u-42", "lan@old.example", true));
        directory.addAccount(new LocalAccount(
                "u-77", "other@example.test", true));

        // Liên kết đã được phê duyệt từ trước; không dựa vào email.
        directory.linkApproved(stable, "u-42");

        System.out.println("Initial: " +
                resolvedId(directory,
                        new VerifiedIdentity(stable, "lan@old.example")));
        System.out.println("Email changed: " +
                resolvedId(directory,
                        new VerifiedIdentity(stable, "lan@new.example")));

        ExternalKey anotherIdp = new ExternalKey(
                stable.tenant(), stable.spEntityId(),
                "https://idp.other.example/saml", PERSISTENT,
                stable.nameQualifier(), stable.spNameQualifier(),
                stable.nameIdValue());
        System.out.println("Other IdP: " +
                resolvedId(directory,
                        new VerifiedIdentity(anotherIdp, "lan@new.example")));

        ExternalKey transientId = new ExternalKey(
                stable.tenant(), stable.spEntityId(),
                stable.idpEntityId(), TRANSIENT,
                stable.nameQualifier(), stable.spNameQualifier(),
                "session-only-id");
        try {
            directory.resolve(new VerifiedIdentity(
                    transientId, "lan@new.example"));
            System.out.println("Transient: ALLOWED");
        } catch (IllegalArgumentException expected) {
            System.out.println("Transient: REJECTED");
        }

        try {
            directory.linkApproved(stable, "u-77");
            System.out.println("Conflicting link: ALLOWED");
        } catch (IllegalStateException expected) {
            System.out.println("Conflicting link: REJECTED");
        }
    }
}
~~~

Chạy bằng JDK 17+ (không cần thư viện ngoài):

~~~bash
javac SamlAccountLinkDemo.java
java SamlAccountLinkDemo
~~~

Stdout đúng theo logic chương trình:

~~~text
Initial: u-42
Email changed: u-42
Other IdP: NONE
Transient: REJECTED
Conflicting link: REJECTED
~~~

Giải thích:
- Hai lần đầu cùng composite key nên resolve về `u-42` dù email trong assertion giả lập đổi.
- Khi `idpEntityId` đổi, composite key khác và không tìm được link.
- `transient` bị từ chối vì không phù hợp làm khóa dài hạn.
- Một key đã gắn với `u-42` không được gắn thêm cho `u-77`.

**Đây là bài test logic, chưa phải production implementation.** `HashMap` không hỗ trợ đồng thời hoặc bền vững; production dùng cơ sở dữ liệu, transaction, unique constraint, audit và kiểm tra active/tenant. Ví dụ không cố xử lý clock skew, chứng chỉ hay SAML assertion; việc đó phải nằm ở SAML authentication trước khi tạo `VerifiedIdentity`. Nếu dùng một định danh bất biến từ attribute thay vì `persistent NameID`, cần thay đổi chính sách và test dựa trên hợp đồng IdP tương ứng.

## 12. Chiến lược kiểm thử từ mapping đơn vị đến SSO end-to-end

**Unit tests cho linking policy** (không cần IdP):
- Cùng persistent NameID với email mới vẫn trả cùng local ID.
- Same NameID value nhưng issuer/tenant/SP khác **không** trỏ nhầm account.
- `transient` hoặc thiếu issuer/qualifier dữ liệu sai chính sách bị từ chối.
- Một external key không thể gắn vào hai account.
- Account internal disabled hoặc chưa được provision không được đăng nhập.
- Nếu allowlist roles chỉ chứa `reader`, claim `super-admin` lạ không tự biến thành quyền.

**Integration tests với IdP thử nghiệm**:
- Tạo SAML Response **được ký đúng** theo metadata test; xác nhận SP xử lý `NameID`, attributes và tạo principal theo hợp đồng.
- Response sai chữ ký/cert, issuer, audience, recipient/destination, thời hạn hoặc `InResponseTo` bị từ chối trước khi gọi linking service.
- Lặp response cũ không được tạo thêm phiên trái policy; thử case có nhiều assertions/attributes để loại bỏ nhầm lẫn.
- IdP đổi email/profile giữa các lần login, link vẫn giữ đúng ID nội bộ.
- IdP đổi NameID/format: phải yêu cầu liên kết hoặc migration hợp lệ, không fallback email.
- Dữ liệu trùng attribute, multi-valued group, thiếu attribute bắt buộc được xử lý theo policy.
- Concurrent linking tạo duy nhất một external key record; conflict không ghi đè.
- Metadata/cert rotation có quy trình tin cậy; không tự chấp nhận chứng chỉ từ request.

**E2E với tài khoản staging riêng**:
- Login trước/sau IdP thay đổi email.
- Logout, disable internal account, disable IdP account và kiểm chứng hệ quả thực tế của session/SSO (logout SP và logout IdP có thể khác nhau).
- Dữ liệu tài khoản A không thể truy cập bằng assertion của B.
- Multi-tenant: một tài khoản IdP ở tenant B không mở dữ liệu tenant A.
- Ghi nhận kết quả mà không in raw SAML, NameID nhạy cảm, token hoặc credential trong log.

Không dùng assert “login trả HTTP 200” làm bằng chứng linking đúng. Phải kiểm tra **local account ID** và quyền theo từng kịch bản, kể cả âm tính.

## 13. Checklist triển khai vận hành

1. **Thỏa thuận IdP contract:** entity ID, metadata URL/cert, SP entity ID, NameID Format, qualifiers, NameID lifecycle, attribute names/types và khi nào thay đổi.
2. **Chọn key và uniqueness:** luôn kèm IdP/tenant/SP context; không dùng email làm khóa mặc định.
3. **Xác thực trước linking:** dùng Spring Security SAML provider, giữ kiểm tra signature, issuer, audience, thời gian, recipient, correlation; không tự viết XML verification.
4. **Đăng ký tài khoản:** pre-provision hoặc JIT có kiểm soát; xác minh việc gắn account và chống duplicate.
5. **Profile mapping riêng:** email/tên/phòng ban được cập nhật theo nguồn đáng tin cậy, không ghi đè thuộc tính nội bộ do người dùng sở hữu một cách tùy tiện.
6. **Group-to-role mapping:** allowlist, tenant scoping, chính sách thu hồi quyền và kiểm tra local authorization.
7. **Account lifecycle:** disabled, deleted, merged, reactivated, change IdP/NameID và unlink đều có quy trình audit.
8. **Privacy:** hạn chế lưu, dùng và chia sẻ persistent NameID; log metadata tối thiểu, truy cập có phân quyền và retention.
9. **Kiểm thử âm tính:** collision, transient, stale assertion, thiếu claims, sai issuer/audience, tenant mismatch, race và replay.
10. **Khả năng phục hồi:** nếu IdP thay metadata hoặc NameID policy, có quy trình migration được phê duyệt thay vì bypass kiểm tra.

## 14. Câu hỏi tự luyện

**Câu 1.** Cùng một SAML `NameID.Value` xuất hiện từ hai IdP khác nhau. Có phải cùng user?  
**Không.** Phải tách theo issuer và context của RP/tenant. Trùng chuỗi không chứng minh liên kết.

**Câu 2.** Người dùng đổi email, `persistent NameID` vẫn giữ. Cần tạo account mới?  
**Không.** Nếu link hợp lệ đã trỏ về `u-42` và tài khoản còn active, email chỉ là thuộc tính profile.

**Câu 3.** Một SAML Response có chữ ký hợp lệ nhưng `AudienceRestriction` nhắm SP khác. Có được liên kết tài khoản?  
**Không.** Audience sai thì assertion không hợp lệ cho SP hiện tại.

**Câu 4.** Có thể dùng `transient NameID` để nối với tài khoản nội bộ cho tất cả lần login sau?  
**Không.** Dữ liệu transient không cam kết bền vững; dùng stable identifier có contract hoặc cơ chế linking khác.

**Câu 5.** `getFirstAttribute("groups")` trả "reader", nhưng assertion chứa cả "admin". Mapping đã đầy đủ chưa?  
**Chưa.** Group là thuộc tính đa trị, phải đọc tất cả giá trị và áp dụng allowlist; không mù quáng cấp admin.

**Câu 6.** SP đã xác thực SAML xong. Đã đủ để cho phép truy cập dữ liệu của local account không?  
**Chưa.** Cần resolve link duy nhất, xác minh account active, tenant, role và quyền trên dữ liệu.

**Câu 7.** Khi IdP đổi cấu hình NameID khiến mọi người bị báo “chưa liên kết”, có thể tìm account cũ theo email?  
**Không nên.** Phải dùng kế hoạch migration/approval, vì email có thể bị tái cấp hoặc không verified.

## 15. Tài liệu chuẩn

- [OASIS — SAML 2.0 Core Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `NameIDType`, `NameID Format`, persistent/transient identifiers, `SubjectConfirmation` và `AttributeStatement`.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html): luồng SP SSO, principal sau xác thực và các endpoint.
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html): xác thực assertion, tùy chỉnh validation và authority mapping.
- [Spring Security API — Saml2AuthenticatedPrincipal](https://docs.spring.io/spring-security/site/docs/6.5.11/api/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html): `getName()`, `getAttribute()`, `getFirstAttribute()` và `getRelyingPartyRegistrationId()`.
- [Spring Boot 3.3 — SAML 2.0 Configuration](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html#web.security.saml2): cấu hình relying party/IdP.
- [OWASP — SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): các lưu ý xác minh chữ ký, trust, callback và assertion.

**Điểm cần nhớ:** NameID là một định danh có **format và phạm vi**, không phải “email đăng nhập” mặc định. Ứng dụng phải xác minh assertion trước, tra external identity key duy nhất theo ngữ cảnh IdP/SP/tenant, rồi kiểm tra local account và quyền nghiệp vụ. SSO hợp lệ không tự chứng minh rằng account linking và authorization đã đúng.