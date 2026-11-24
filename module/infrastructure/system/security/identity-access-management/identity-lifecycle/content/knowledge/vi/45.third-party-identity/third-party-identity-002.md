# Partner identity: quản lý danh tính đối tác trong IAM

## 1. Partner identity là gì?

Trong **Identity and Access Management (IAM)**, *partner identity* là cách một hệ thống **nhận diện, xác minh, thiết lập quan hệ tin cậy và quản lý quyền truy cập gắn với một tổ chức đối tác**. Đối tác có thể là nhà phân phối, nhà cung cấp, đơn vị triển khai, công ty logistics, đại lý, doanh nghiệp cùng vận hành một dịch vụ hoặc tổ chức trao đổi dữ liệu qua API.

Đối tượng quản lý không chỉ là một người dùng. Một mối quan hệ đối tác thường có ba lớp danh tính:

1. **Danh tính tổ chức đối tác:** bản ghi tổ chức B, định danh ổn định, tình trạng hợp đồng, người phụ trách, điều kiện tin cậy và phạm vi hợp tác với tổ chức A.
2. **Danh tính con người thuộc đối tác:** tài khoản của nhân viên B đăng nhập ứng dụng A, thông qua IdP của B hoặc tài khoản khách được A quản lý.
3. **Danh tính ứng dụng hoặc workload của đối tác:** client, service account, chứng thư số hoặc workload identity đại diện cho một tích hợp tự động của B gọi API A.

Ví dụ: Công ty A cung cấp nền tảng quản lý đơn hàng cho nhiều đại lý. Công ty B ký hợp đồng làm đại lý của A. A tạo bản ghi partner B với mã ổn định, xác minh đầu mối quản trị của B, cho phép đăng nhập liên kết (federation) từ IdP của B và đăng ký một OAuth client để B đồng bộ đơn hàng bằng API. Các nhân viên và client của B chỉ được xem dữ liệu thuộc quan hệ hợp tác B–A.

Partner identity giúp trả lời các câu hỏi:

- **Đây là đối tác nào?** Có phải tổ chức đã được xác minh và được phép hợp tác với A không?
- **Ai hoặc hệ thống nào đang đại diện cho đối tác?** Người dùng hoặc workload có gắn với đúng đối tác không?
- **Quan hệ tin cậy được thiết lập dựa trên điều kiện gì?** Có IdP, chứng thư, client và kênh provisioning nào đã được phê duyệt?
- **Đối tác được truy cập phạm vi nào?** Quyền theo tenant, hợp đồng, dự án, môi trường và loại dữ liệu ra sao?
- **Điều gì xảy ra khi quan hệ thay đổi hoặc chấm dứt?** Các danh tính, khóa, phiên và quyền liên quan có được cập nhật, thu hồi và kiểm chứng không?

**Phân biệt:** *Partner identity* mô tả danh tính và quan hệ tin cậy cấp đối tác; *external user* là một chủ thể con người cụ thể truy cập từ bên ngoài. Một partner có thể chứa hàng trăm external user, nhiều client tích hợp và các mối quan hệ quyền khác nhau. Đăng nhập SSO thành công của một người thuộc B **không có nghĩa** mọi người của B tự động được truy cập tất cả tài nguyên A.

## 2. Mô hình khái niệm: đối tác, danh tính và quyền

### 2.1. Những thực thể cần tách rõ

| Thực thể | Mục đích | Ví dụ |
|---|---|---|
| Partner organization | Đại diện tổ chức đối tác trong hệ thống A | partner_id = P-2048 |
| Partner relationship | Quan hệ hợp tác và phạm vi nghiệp vụ giữa A và B | Hợp đồng phân phối 2026, hiệu lực đến 31/12/2026 |
| Identity trust configuration | Nguồn xác thực và điều kiện tin cậy | OIDC issuer được phép, SAML entityID, bộ khóa tin cậy |
| External human principal | Người dùng cụ thể gắn với B | (OIDC issuer, subject), local user ID |
| Workload principal | Ứng dụng hoặc dịch vụ của B | OAuth client_id, mTLS certificate identity |
| Partner membership | Liên kết principal với partner và trạng thái | User U thuộc P-2048, active |
| Entitlement/grant | Quyền được cấp trên phạm vi cụ thể | orders.read trên tenant B, dự án F1 |
| Sponsor / partner owner | Người phía A chịu trách nhiệm quan hệ và quyền | Chủ nhóm vận hành đối tác |
| Review/revocation record | Bằng chứng rà soát và thu hồi | Ai duyệt, thời gian và kết quả |

**Partner organization khác tenant.** Trong nhiều hệ thống B2B, mỗi đối tác được gắn với một tenant riêng, nhưng ánh xạ này không luôn là một-một. Một đối tác có thể vận hành nhiều tenant theo khu vực, hoặc nhiều đơn vị pháp lý có hợp đồng khác nhau dùng chung nền tảng. Cần có quy tắc ánh xạ rõ thay vì mặc định rằng tên tổ chức, domain email và tenant ID là đồng nhất.

**Partner organization cũng khác IdP.** Nhiều đối tác có thể sử dụng chung một nhà cung cấp IdP; một đối tác có thể dùng nhiều IdP sau sáp nhập hoặc theo khu vực. Việc tin cậy IdP chỉ cho phép đánh giá xác thực từ nguồn đó, không tự chứng minh chủ thể được gán vào đúng partner hay có quyền truy cập.

### 2.2. Định danh ổn định

Thiết kế thường cần một **partner_id nội bộ, bất biến** do A phát hành và một hoặc nhiều định danh bên ngoài đã xác minh:

| Cấp | Định danh phù hợp | Không nên dùng một mình |
|---|---|---|
| Tổ chức | partner_id nội bộ; external organization ID đã kiểm chứng và gắn nguồn | Tên hiển thị, tên miền email |
| Người dùng OIDC | Cặp (issuer, subject) đã kiểm tra trong ID token | Email hoặc display name |
| Người dùng SAML | Định danh ổn định từ issuer/entityID cùng NameID/thuộc tính thỏa thuận | Email có thể đổi hoặc tái sử dụng |
| SCIM user | ID tại hệ thống đích; externalId có namespace và nguồn được xác định | externalId không được gắn nguồn |
| API client | Client identifier cùng authorization server/issuer và partner mapping | Client ID do đối tác tự khai trong body |
| Chứng thư workload | Public key/chứng thư được tin cậy và ràng buộc danh tính đã thẩm định | Chỉ common name chưa xác minh |

Không tự nối hai partner vì có cùng domain, cũng không tự chuyển quyền khi đối tác đổi tên hoặc thay IdP. Các thay đổi liên quan khóa định danh phải có quy trình xác minh, ánh xạ, kiểm thử và lưu dấu vết.

### 2.3. Bản ghi quan hệ đối tác tham khảo

Mẫu dữ liệu sau chỉ là mô hình khái niệm để giải thích quan hệ, không phải một chuẩn API bắt buộc:

~~~yaml
partner:
  id: "P-2048"
  display_name: "Cong ty B"
  legal_entity_ref: "verified-entity-B"
  state: "active"
  owner_team: "partner-operations"
  sponsor_id: "internal-owner-17"
  relationship:
    contract_ref: "CTR-2026-042"
    valid_until: "2026-12-31"
    purposes:
      - "order-fulfillment"
  tenants:
    - "tenant-b-vn"
  federation:
    protocol: "oidc"
    allowed_issuers:
      - "https://idp.partner.example/organization-b"
  access_review:
    next_review_at: "2026-12-01"
~~~

Ở hệ thống thật, khóa bí mật, thông tin liên hệ nhạy cảm và credential không nên lưu trực tiếp trong cấu hình thường hoặc log. Các tham chiếu hợp đồng và bằng chứng xác minh cần được quản trị theo chính sách bảo mật dữ liệu.

## 3. Ba lớp tin cậy trong hợp tác B2B

Một thiết kế an toàn tách ba quyết định thường bị đánh đồng:

1. **Business trust (tin cậy quan hệ):** Tổ chức B có được A xác minh và chấp thuận tham gia hệ sinh thái không? Hợp đồng, mục đích chia sẻ dữ liệu, đầu mối chịu trách nhiệm có còn hiệu lực không?
2. **Identity trust (tin cậy xác thực):** A có chấp nhận chứng cứ xác thực từ IdP, authorization server hoặc chứng thư của B không? Khóa, issuer, audience, quy tắc xác minh và quy trình thay đổi có được thiết lập an toàn không?
3. **Authorization (quyền truy cập):** Chủ thể cụ thể của B được làm gì, trên tài nguyên nào, với điều kiện nào và tới thời điểm nào?

Một quyết định **allow** cần đáp ứng đồng thời các điều kiện thích hợp ở cả ba lớp. Hợp đồng hợp lệ không thay cho xác thực; token hợp lệ không thay cho quyền; quyền từng được cấp không nên tồn tại vô hạn khi hợp đồng chấm dứt.

### Sơ đồ kiến trúc

~~~mermaid
flowchart LR
    subgraph B["Tổ chức đối tác B"]
      USER["Nhân viên B"]
      IDP["IdP B"]
      CLIENT["Ứng dụng tích hợp B"]
      PROV["Nguồn provisioning"]
      USER --> IDP
    end
    subgraph A["Nền tảng A"]
      SP["Cổng đối tác / SSO"]
      IAM["Partner registry + IAM"]
      API["API gateway / Resource server"]
      POLICY["Policy engine: RBAC + ABAC"]
      DATA["Dữ liệu tenant / dự án"]
      AUDIT["Audit + review + reconciliation"]
      SP --> POLICY
      API --> POLICY
      POLICY --> IAM
      POLICY --> DATA
      IAM --> AUDIT
      SP --> AUDIT
      API --> AUDIT
    end
    IDP -->|"OIDC / SAML federation"| SP
    PROV -->|"SCIM nếu có"| IAM
    CLIENT -->|"OAuth access token, có thể kết hợp mTLS"| API
    OWNER["Sponsor/chủ tài nguyên A"] -->|"Phê duyệt và rà soát"| IAM
~~~

Lưu ý: **SCIM không phải giao thức SSO**. SCIM hỗ trợ đồng bộ bản ghi người dùng và nhóm khi có tích hợp; OIDC/SAML phục vụ xác thực liên kết; OAuth 2.0 giúp cấp quyền truy cập API; RBAC/ABAC là cơ chế quyết định quyền trên tài nguyên của A.

## 4. Joiner: đưa một đối tác mới vào hệ thống

Khác với Joiner của một nhân viên, **Partner Joiner** bắt đầu từ việc xác minh và phê duyệt **quan hệ giữa hai tổ chức**. Chỉ sau đó mới đưa người dùng và tích hợp vào phạm vi đã duyệt.

### 4.1. Bước 1 — Xác minh tổ chức và quyền đại diện

Đội phụ trách đối tác cần xác định:

- Pháp nhân hoặc đơn vị hợp tác là ai, tên pháp lý và định danh doanh nghiệp nếu cần;
- Người đại diện và đầu mối kỹ thuật/an ninh là ai, đã được xác thực qua kênh tin cậy chưa;
- Hợp đồng, dịch vụ, dự án, khu vực và mục đích sử dụng dữ liệu nào được phê duyệt;
- Dữ liệu nào có thể chia sẻ, với thời hạn và nghĩa vụ xử lý ra sao;
- Ai ở A làm sponsor/chủ tài nguyên, ai chịu trách nhiệm ra quyết định khi có sự cố.

Khi kiểm tra yêu cầu cập nhật email đầu mối, IdP hoặc khóa tích hợp, nên xác nhận qua một kênh đã được thiết lập độc lập. Chỉ email tự xưng “IT admin của B” không đủ để thay đổi quan hệ tin cậy.

### 4.2. Bước 2 — Tạo partner record và phạm vi truy cập

IAM phát hành một mã partner nội bộ duy nhất, liên kết hợp đồng, owner, tenant, phân loại dữ liệu, hạn hiệu lực và trạng thái ban đầu. Các trạng thái có thể là:

| Trạng thái minh họa | Ý nghĩa | Tác động truy cập |
|---|---|---|
| requested | Đã có yêu cầu hợp tác, đang xét duyệt | Chưa cấp quyền tài nguyên |
| verified | Danh tính và quyền đại diện đã được kiểm chứng | Có thể bắt đầu cấu hình kỹ thuật có kiểm soát |
| active | Quan hệ và các điều kiện tin cậy hợp lệ | Cho phép chủ thể có quyền cụ thể truy cập |
| restricted | Bị giới hạn một phần do thay đổi hoặc rủi ro | Chỉ cho phép quyền còn được phê duyệt |
| suspended | Tạm đình chỉ quan hệ, chờ xác minh hoặc xử lý sự cố | Chặn truy cập theo chính sách đình chỉ |
| offboarded | Quan hệ truy cập đã kết thúc, đã xử lý thu hồi | Không còn cấp quyền hoạt động |
| archived | Bản ghi lưu trữ theo chính sách | Phục vụ kiểm toán, không cấp quyền |

Đây là các trạng thái thiết kế gợi ý. Một tổ chức có thể đặt tên khác, nhưng phải xác định rõ **trạng thái nào cho phép hoặc từ chối truy cập** và cách chuyển trạng thái được ghi nhận.

### 4.3. Bước 3 — Thiết lập federation với IdP đối tác

Nếu A cho phép nhân viên B đăng nhập bằng IdP của B, các bên cần chốt:

1. **Giao thức và điểm cuối:** OIDC hoặc SAML, client/ứng dụng nhận, issuer hoặc entityID và metadata cần thiết.
2. **Trust anchor:** Chữ ký, khóa/certificate hợp lệ và quy trình xoay khóa; chỉ chấp nhận cấu hình đã được phê duyệt.
3. **Điều kiện xác thực:** MFA theo độ nhạy, cách xử lý đăng nhập rủi ro, phiên, logout khi hỗ trợ và kênh báo cáo sự cố.
4. **Attribute mapping:** Cách diễn giải subject, organization/tenant, nhóm, vai trò; thuộc tính nào là tin cậy và thuộc tính nào chỉ để hiển thị.
5. **Provisioning và deprovisioning:** Dùng SCIM, lời mời, JIT provisioning hoặc quy trình thủ công có kiểm soát; trách nhiệm báo người nghỉ việc/đổi vai trò.
6. **Tình huống chuyển đổi:** Đổi IdP, đổi domain, merge/split tổ chức, xoay signing key hoặc hủy trust.

#### Kiểm tra token/assertion là bắt buộc

Với OIDC, ứng dụng nhận phải kiểm tra chữ ký và các điều kiện áp dụng như **issuer, audience, expiration, nonce và tính hợp lệ của luồng đăng nhập**. Định danh người dùng nên được liên kết với cặp **(iss, sub)**. Nếu có nhiều IdP/tenant, phải ánh xạ issuer đã xác minh đến partner được phê duyệt. Không tìm partner chỉ từ email domain do người dùng gửi.

Với SAML, cần xác thực chữ ký, issuer, audience, recipient/destination, điều kiện thời gian, InResponseTo khi áp dụng và cơ chế chống replay. Một assertion được ký hợp lệ bởi một IdP vẫn không đủ để cấp quyền nếu IdP đó chưa được ánh xạ tới đúng partner và ứng dụng.

**Không mặc định tin role do đối tác gửi.** Nếu A chấp nhận claim nhóm/role của B, phải có danh sách ánh xạ do A quản trị, ví dụ nhóm “B-Order-Read” chỉ tương ứng quyền “orders.read” của tenant B, và cần phê duyệt tăng quyền nhạy cảm.

### 4.4. Bước 4 — Provision user và workload

Hai loại principal thường được tạo theo hai luồng:

| Người dùng con người | Workload / tích hợp máy |
|---|---|
| Liên kết external subject với partner_id và local user ID | Đăng ký OAuth client hoặc workload identity gắn partner_id |
| Mời, SCIM hoặc JIT có ràng buộc sponsor và phạm vi | Xác minh owner, ứng dụng, môi trường, mục đích và thời hạn |
| Cấp role và membership theo tenant/dự án | Cấp scope/API permission tối thiểu, tách production và sandbox |
| MFA, SSO và quản lý phiên người dùng | Credential/certificate trong secret manager, xoay khóa có kế hoạch |
| Thu hồi khi nghỉ việc hoặc đổi vai trò | Thu hồi khi ngừng tích hợp, sự cố hoặc kết thúc hợp đồng |

**JIT provisioning** có thể tạo local user khi lần đầu đăng nhập, nhưng không nên tự cấp quyền rộng chỉ vì authentication thành công. Phải có cơ sở hợp lệ như lời mời/sponsor, membership và quy tắc cấp quyền đã được phê duyệt.

### 4.5. Bước 5 — Kiểm thử trước khi kích hoạt

Ít nhất kiểm tra luồng đúng và các ca từ chối:

- Nhân viên B có quyền xem dữ liệu tenant B nhưng không đọc được tenant C;
- Người chưa được phê duyệt từ cùng IdP B không tự có quyền;
- Role chỉ đọc không thực hiện được thao tác ghi;
- Token sai issuer/audience, hết hạn hoặc sai chữ ký bị từ chối;
- User hết hạn, partner bị suspended hoặc contract không còn hiệu lực bị từ chối;
- Client B không dùng được API ngoài scope và không truy cập môi trường khác;
- Log phản ánh đúng partner_id, principal_id, resource, hành động và kết quả.

## 5. Mover: khi tổ chức đối tác thay đổi

Mover trong Partner IAM là thay đổi cấu trúc tổ chức, quan hệ hợp tác hoặc tin cậy kỹ thuật. Nó có thể ảnh hưởng đồng thời tới hàng trăm người dùng và nhiều workload.

| Sự kiện Mover | Quyết định cần xem lại | Thực hiện và bằng chứng |
|---|---|---|
 B mở rộng sang dự án mới | Quyền mới có nằm trong hợp đồng và phạm vi dữ liệu được duyệt không? | Phê duyệt dự án, grant mới có scope và expiry |
 B ngừng một dịch vụ | Quyền nào không còn lý do tồn tại? | Thu hồi grants liên quan, giữ dịch vụ khác nếu được phép |
 B đổi IdP hoặc tenant IdP | Nguồn nào được tin cậy? Làm thế nào chứng minh đây vẫn là B? | Xác minh ngoài băng, thay federation config có kiểm soát, chuyển subject mapping |
 B sáp nhập/tách pháp nhân | Partner_id, hợp đồng, owner và tenant có còn đúng? | Đánh giá quan hệ mới, tách/di chuyển membership theo phê duyệt |
 Sponsor phía A thay đổi | Ai chịu trách nhiệm về quyền và review? | Bổ nhiệm owner mới, không để tài khoản mồ côi |
 B thay đổi nhóm vận hành | Ai có quyền quản trị user/grant? | Đánh giá delegated admin, thu hồi quyền quản trị cũ |
 B xoay certificate, secret hoặc signing key | Có gián đoạn hoặc tin cậy khóa không xác định không? | Cấu hình phiên bản khóa, kiểm thử, giám sát và loại bỏ khóa cũ |

Nguyên tắc khi Mover: **đánh giá lại quyền hiện hữu, thu hồi quyền thừa rồi mới hoàn tất quyền mới**. Tránh cộng dồn mọi role của quá khứ, đặc biệt khi các dự án có mức nhạy cảm hoặc tenant khác nhau.

### Ví dụ: đối tác đổi IdP

Giả sử B chuyển từ IdP-Old sang IdP-New:

1. A xác minh yêu cầu thay đổi qua đầu mối B đã được kiểm chứng.
2. A đăng ký IdP-New và kiểm tra issuer, chứng thư/khóa, client, callback và chính sách xác thực.
3. Với từng principal, A xác nhận liên kết định danh cũ–mới qua thủ tục đáng tin cậy; **không ghép tự động theo email**.
4. A kiểm tra lại membership và grant, đăng nhập thử và đối soát user không có ánh xạ.
5. A thu hồi trust IdP-Old sau khi chuyển đổi xong theo kế hoạch đã duyệt và ghi lại thay đổi.

Một kẻ tấn công kiểm soát domain email hoặc IdP khác có thể tìm cách tự nhận là B. Bởi vậy việc đổi issuer phải được xem như thay đổi ranh giới tin cậy, không phải sửa một chuỗi cấu hình đơn giản.

## 6. Leaver: kết thúc một quan hệ đối tác

Leaver có thể do hết hợp đồng, đối tác ngừng sử dụng dịch vụ, chấm dứt nhà cung cấp, vi phạm an ninh, tranh chấp cần đình chỉ hoặc chuyển sang pháp nhân khác. Mục tiêu là **thu hồi toàn bộ quyền phụ thuộc vào quan hệ đã kết thúc** mà vẫn bảo toàn dữ liệu và bằng chứng theo chính sách.

### 6.1. Thứ tự xử lý tham khảo

1. **Xác nhận phạm vi chấm dứt:** toàn bộ partner hay chỉ một hợp đồng/tenant/dự án? Xác định thời điểm có hiệu lực, người phê duyệt và các nghĩa vụ chuyển giao.
2. **Chặn cấp quyền mới:** cập nhật partner/relationship sang suspended hoặc offboarded theo quy trình; chặn tự động tạo user, membership và token/grant mới đối với phạm vi bị kết thúc.
3. **Thu hồi quyền người dùng:** vô hiệu hóa membership/grant, group, quyền delegated administration và quyền chia sẻ tại ứng dụng đích.
4. **Thu hồi quyền workload:** vô hiệu hóa OAuth client, credential, key, certificate trust, webhook subscription hoặc token do tích hợp tạo ra; xoay các secret từng chia sẻ khi cần.
5. **Xử lý phiên và token:** đăng xuất/hủy session, refresh token, và giảm hiệu lực access token đã cấp bằng cơ chế được hệ thống hỗ trợ. Không mặc định việc khóa partner khiến JWT tự hết hiệu lực ngay lập tức.
6. **Ngừng trust và provisioning:** vô hiệu hóa cấu hình federation/SCIM khi không còn quan hệ nào dùng chúng; bảo đảm các tác vụ đồng bộ trễ không tái tạo user/grant đã thu hồi.
7. **Kiểm tra hệ thống liên quan:** ứng dụng phụ, môi trường thử nghiệm, data share, BI, kho tài liệu và các tài khoản được cấp qua cơ chế thủ công.
8. **Xử lý dữ liệu và chứng cứ:** lưu, trả, xóa hoặc ẩn danh dữ liệu theo hợp đồng và quy định; giữ audit evidence theo chính sách. Hoàn tất đối soát và biên bản thu hồi.

Thứ tự chi tiết có thể thay đổi theo khủng hoảng bảo mật, kiến trúc và hợp đồng. Trong sự cố cần ngăn truy cập ngay, việc **khóa khả năng truy cập** có ưu tiên cao hơn các bước hành chính.

### 6.2. Không đồng nhất việc khóa IdP với việc thu hồi ở A

Ngay cả khi B xóa tài khoản nhân viên khỏi IdP B, A vẫn có thể giữ local user, session đang sống, refresh token, chia sẻ dữ liệu hoặc API credentials. Việc chấm dứt relationship còn phải xử lý danh tính workload của B, bởi workload thường không đi theo HR lifecycle của một nhân viên.

### 6.3. Phân biệt offboarding một người, một tích hợp và cả đối tác

| Phạm vi kết thúc | Tác động mong muốn | Không nên thu hồi nhầm |
|---|---|---|
 Một nhân viên B rời dự án | Membership, grant và phiên của người đó trong dự án | Các nhân viên B khác vẫn đủ điều kiện |
 Một workload B bị thay thế | Client, token, chứng thư và quyền của workload cũ | Tích hợp hợp lệ khác của B |
 Một hợp đồng hoặc tenant kết thúc | Toàn bộ quyền phát sinh từ relationship tương ứng | Hợp đồng khác còn hiệu lực nếu được tách riêng |
 Toàn bộ hợp tác A–B kết thúc | Mọi grant, federation, provisioning và workload chỉ phục vụ B | Dữ liệu và log có nghĩa vụ lưu giữ |

## 7. RBAC/ABAC: tách danh tính đối tác khỏi quyết định quyền

Một người hoặc một client thuộc B cần được xét theo **quan hệ với B, tư cách principal, phạm vi tài nguyên và điều kiện hiện tại**.

### RBAC

RBAC ánh xạ vai trò sang quyền, ví dụ:

- partner_order_viewer: orders.read, reports.read;
- partner_operator: orders.read, orders.update_status trên dự án được gán;
- partner_integration_client: orders.read hoặc orders.create theo từng API contract;
- partner_admin_delegated: quản lý thành viên B trong giới hạn quyền được A ủy quyền.

Quyền delegated admin không mặc nhiên bao gồm quyền tự cấp administrator toàn cục hoặc truy cập tenant khác. A vẫn kiểm soát trần quyền và audit mọi thao tác do partner admin thực hiện.

### ABAC và scope

ABAC xét thêm thuộc tính đối tác, quan hệ, hành động và tài nguyên: partner.status, contract_validity, principal.kind, membership.status, tenant, project, dữ liệu nhạy cảm, thời gian và ngữ cảnh bảo mật.

~~~text
authorize(subject, action, resource, context):
    if not context.authentication_valid: deny

    partner = load_partner(subject.partner_id)
    if partner.status != "active": deny

    relationship = load_relationship(subject.partner_id, resource.context_id)
    if relationship.status != "active": deny
    if now >= relationship.valid_until: deny

    if not subject.active: deny
    if not has_valid_partner_membership(subject, partner.id): deny
    if not resource_in_allowed_scope(subject, relationship, resource): deny
    if not entitlement_allows(subject, action, resource): deny
    if not satisfies_data_policy(subject, resource, context): deny

    allow
~~~

Đây là **mã giả chính sách**, không phải một engine đặc thù. Trong ứng dụng thực tế, kiểm tra quyền phải diễn ra tại resource server/backend đối với từng thao tác nhạy cảm; ẩn nút trên giao diện không đủ để bảo vệ API.

### Bẫy cross-tenant access

Giả sử user U thuộc B có vai trò “viewer”. Nếu API chỉ kiểm tra U có role viewer mà không kiểm tra **resource.tenant_id thuộc membership/grant của B**, U có thể đọc đơn hàng C bằng cách thay ID trên đường dẫn. Đây là lỗi phân quyền đối tượng/cross-tenant access.

Đúng hơn: quyết định quyền phải kết hợp **role + partner_id/tenant + resource ownership + contract scope**. Khi U có nhiều membership với nhiều đối tác, hệ thống phải chọn rõ ngữ cảnh truy cập và không trộn các tập quyền giữa các partner.

## 8. Federation, SSO và provisioning trong quản lý partner identity

### 8.1. OIDC/SAML trả lời câu hỏi xác thực

Federation giúp A tin cậy chứng cứ đăng nhập từ IdP của B khi đáp ứng cấu hình đã thỏa thuận. A cần xử lý:

- **Issuer pinning:** chỉ chấp nhận issuer/entityID đã đăng ký cho partner tương ứng;
- **Audience/client binding:** token dành cho ứng dụng khác không được dùng lại;
- **Signature/key validation:** kiểm tra khóa và metadata đã tin cậy, xử lý xoay khóa;
- **Subject mapping:** cặp issuer + subject hoặc định danh SAML ổn định;
- **Token/session security:** thời gian hiệu lực, anti-replay, redirect/callback được cho phép;
- **Authorization mapping:** chỉ đưa vào các quyền đã được A duyệt.

Một số IdP hỗ trợ nhóm, tenant identifier hoặc organization claim; các claim đó có thể giúp ánh xạ membership **khi đã được thỏa thuận và xác minh**, nhưng không tự động trở thành quyết định phân quyền.

### 8.2. SCIM quản lý vòng đời bản ghi

Khi A tích hợp SCIM với B, hệ thống provisioning có thể tạo, cập nhật hoặc vô hiệu hóa user/group tại A. Các biến đổi cần được kiểm soát:

| Sự kiện provisioning | Hành động mong muốn ở A | Điều cần xác minh |
|---|---|---|
 Create user | Tạo local principal chưa có, gắn đúng partner | Chống trùng/ghép nhầm, trạng thái invitation |
 Change attributes | Cập nhật thuộc tính hợp lệ | Không để thuộc tính tùy ý nâng quyền |
 Add group membership | Ánh xạ sang entitlement được chấp thuận | Scope của nhóm và quyền quản trị |
 Remove group membership | Thu hồi grant phát sinh từ nhóm | Quyền có bị tồn dư ở ứng dụng khác? |
 Deactivate user | Khóa truy cập và xử lý phiên/grant theo chính sách | Xác nhận ở resource server |
 Sync failure | Retry có kiểm soát và cảnh báo | Phát hiện bất nhất giữa desired và actual state |

**SCIM không thay thế owner approval, access review hoặc session revocation.** Cần đối soát định kỳ giữa nguồn danh tính, bản ghi IAM và quyền thực tế ở ứng dụng. Đặc biệt không để bản ghi từ luồng sync cũ tái kích hoạt quyền sau khi partner đã offboarded.

### 8.3. JIT provisioning và ràng buộc invitation

JIT tiện khi B có nhiều nhân viên ít đăng nhập: local user chỉ được tạo lúc đăng nhập lần đầu. Tuy vậy, JIT cần điều kiện cho phép rõ ràng như invitation còn hạn, sponsor đã duyệt, partner active và ánh xạ issuer đúng. Nếu ứng dụng cấp sẵn quyền cho mọi tài khoản thuộc domain B thì bất kỳ người dùng nào ở B cũng có thể vượt qua quy trình duyệt.

## 9. Workload identity của đối tác: API và tích hợp tự động

Mối quan hệ đối tác thường có các tác vụ không có người đăng nhập: đồng bộ tồn kho, gửi webhook, báo cáo giao nhận và xử lý hóa đơn. Các tác vụ đó cần **danh tính workload riêng** gắn với partner.

### 9.1. Một mẫu OAuth 2.0 client credentials

Một client do B vận hành lấy access token từ authorization server được A chấp nhận rồi gọi API của A. Luồng tham khảo:

~~~mermaid
sequenceDiagram
    participant C as Workload của B
    participant AS as Authorization Server
    participant API as API của A
    participant P as Policy / Partner Registry
    C->>AS: Client authentication + grant client_credentials
    AS-->>C: Access token (audience, scope, expiry)
    C->>API: HTTPS + access token
    API->>API: Validate token (issuer, audience, signature, expiry)
    API->>P: Kiểm tra partner, client, scope, tenant, relationship
    P-->>API: Allow hoặc deny
    API-->>C: Kết quả được phép hoặc lỗi truy cập
~~~

Để triển khai an toàn:

1. A cấp/đăng ký **client riêng theo đối tác, ứng dụng, môi trường và mục đích**; liên kết client đến partner_id đã xác minh.
2. Client xác thực với authorization server bằng phương thức phù hợp như private_key_jwt, mTLS hoặc client secret được bảo vệ đúng cách.
3. Access token có audience, scope và thời gian sống phù hợp; resource server phải kiểm tra token đúng cách trước khi xử lý.
4. Policy kiểm tra quyền cụ thể và tình trạng hiện tại của partner; không dùng một scope “admin” chung cho tất cả tích hợp.
5. Secret, private key và chứng thư được lưu trong secret manager, có owner, nhật ký sử dụng và kế hoạch xoay vòng/thu hồi.

**ID token của OIDC dùng để mô tả xác thực người dùng; không thay access token khi gọi API.** Mọi API có dữ liệu đối tác phải phân quyền tại backend ngay cả khi token đã hợp lệ.

### 9.2. mTLS và chứng thư

mTLS có thể xác thực cả hai đầu kết nối và trong một số thiết kế có thể ràng buộc access token với chứng thư phía client. Tuy nhiên, **chứng thư hợp lệ chỉ chứng minh sở hữu khóa và mối quan hệ tin cậy được cấu hình**; API vẫn cần kiểm tra partner, client, hành động, tenant và contract scope. Hết hạn hoặc xoay chứng thư cần được phối hợp để tránh gián đoạn và tránh giữ khóa cũ quá lâu.

### 9.3. Nguyên tắc với service account

Nếu một hệ thống không hỗ trợ workload federation/OAuth và cần service account, tài khoản đó vẫn phải có:

- Owner bên A và đầu mối vận hành bên B;
- Mục đích, tài nguyên, quyền tối thiểu và hạn sử dụng hoặc review;
- Credential quản lý tập trung, rotation, tách biệt môi trường;
- Khả năng vô hiệu hóa độc lập, log theo identity của workload;
- Liên kết rõ với partner relationship để tự động thu hồi khi kết thúc hợp tác.

Không dùng tài khoản con người của nhân viên B làm robot lâu dài và không chia sẻ một credential duy nhất giữa nhiều đối tác; làm vậy sẽ phá vỡ khả năng truy vết và thu hồi chọn lọc.

## 10. Giảm quyền tồn dư và phát hiện sai lệch

Một hệ thống chỉ quản lý *desired state* trong IAM có thể bỏ sót quyền thực tế trên ứng dụng hoặc kho dữ liệu. Đặc biệt với partner có nhiều ứng dụng, cần **reconciliation** giữa:

1. Quan hệ và hợp đồng còn hiệu lực;
2. Danh tính đã được đồng bộ/provision;
3. Group, role, grant và resource share đã cấu hình;
4. Session/credential/token còn hoạt động trong các giới hạn hệ thống hỗ trợ;
5. Quyền và tài khoản thực tế trên các hệ thống đích.

Ví dụ: partner B kết thúc dự án F1, IAM gỡ group F1 nhưng ứng dụng BI đã sao chép quyền đọc vào một ACL riêng. Nếu không đối soát ACL BI, quyền truy cập tồn dư vẫn tồn tại.

**Access review theo mức rủi ro:** sponsor và resource owner xác nhận theo chu kỳ: “B có còn là đối tác hợp lệ không?”, “ai cần quyền nào?”, “quyền máy nào còn dùng?”, “tích hợp nào không hoạt động?”, “có admin được ủy quyền nào vượt phạm vi?”. Khi có thay đổi lớn như hợp đồng mới, đổi owner hoặc sự cố, kích hoạt review bổ sung.

### Các chỉ số hữu ích

| Chỉ số | Ý nghĩa vận hành |
|---|---|
 Partner active không có owner/sponsor hợp lệ | Nguy cơ quan hệ không ai chịu trách nhiệm |
 Số partner hết hợp đồng nhưng còn principal active | Nguy cơ quyền tồn dư trực tiếp |
 Số grant quá hạn hoặc chưa được review | Tính hiệu lực và bằng chứng phê duyệt yếu |
 Thời gian từ sự kiện Leaver đến khi revoke tại hệ thống đích | Đo độ trễ thu hồi, so sánh với SLA theo rủi ro |
 Số lỗi SCIM/provisioning chưa đối soát | Khả năng IAM và ứng dụng lệch trạng thái |
 Workload không có owner/rotation | Nguy cơ credential bị bỏ quên |
 Cross-tenant authorization denial | Tín hiệu cần điều tra, không mặc định là tấn công |

Ngưỡng cảnh báo và tần suất review phải phù hợp độ nhạy của ứng dụng, hợp đồng và yêu cầu vận hành; không có một chu kỳ duy nhất đúng cho mọi đối tác.

## 11. Audit: ai đã cấp, ai đã dùng và ai đã thu hồi quyền?

Audit không chỉ ghi lần đăng nhập. Với partner identity, dấu vết cần bao phủ cấp **tổ chức**, **principal**, **grant** và **request truy cập**.

| Loại sự kiện | Thông tin cần ghi |
|---|---|
 Tạo/duyệt partner | partner_id, yêu cầu, người xác minh, sponsor, hợp đồng/phạm vi |
 Thay federation trust | Issuer/entityID trước–sau, người duyệt, thời điểm hiệu lực |
 Provision user/client | Principal, nguồn sự kiện, phương thức, trạng thái, owner |
 Cấp/thay/thu hồi quyền | Người yêu cầu/duyệt, role, tenant, resource, thời hạn, kết quả |
 Đăng nhập và gọi API | Partner, principal/client, resource, hành động, thời điểm, allow/deny |
 Rotation/credential revoke | Client, key/certificate reference, thời điểm, trạng thái |
 Review và offboarding | Quyền trước–sau, hệ thống đã xác nhận, lỗi chưa giải quyết |

Ví dụ log dạng minh họa, bỏ qua dữ liệu nhạy cảm:

~~~json
{
  "event_type": "partner.grant.revoked",
  "timestamp": "2026-11-20T09:00:00Z",
  "partner_id": "P-2048",
  "principal_id": "user-835",
  "tenant_id": "tenant-b-vn",
  "resource": "project-F1",
  "grant": "orders.read",
  "reason": "contract_scope_changed",
  "requested_by": "partner-owner-17",
  "approved_by": "resource-owner-3",
  "result": "applied",
  "correlation_id": "change-82f3"
}
~~~

Tránh ghi access token, mật khẩu, private key hoặc dữ liệu cá nhân vượt quá mục đích điều tra. Audit log phải được giới hạn quyền đọc, bảo vệ toàn vẹn và có chính sách lưu giữ. Với quyền tác động tới dữ liệu nhạy cảm, cần đủ correlation ID để lần theo yêu cầu từ IAM tới các ứng dụng đích.

## 12. Những lỗi thiết kế thường gặp

| Lỗi | Vì sao nguy hiểm | Cách xử lý |
|---|---|---|
 Dùng email domain để xác định partner | Domain có thể đổi, dùng chung hoặc bị kiểm soát sai; không nói lên quyền | Gắn partner_id với nguồn đã xác minh và membership cụ thể |
 Coi token hợp lệ là có quyền | Token chỉ chứng minh những điều kiện nhất định về xác thực/ủy quyền được cấp | Kiểm tra relationship, entitlement và resource scope |
 Gộp tất cả đối tác vào một role chung | Dễ lộ dữ liệu chéo tenant | RBAC kết hợp kiểm tra ABAC/tenant tại backend |
 Cho IdP đối tác quyết định toàn bộ quyền admin | Bên ngoài có thể tự nâng quyền vượt điều A chấp thuận | A duy trì role mapping, trần quyền và duyệt đặc quyền |
 Chỉ xử lý Leaver ở IdP bên B | Phiên, local grant, API client tại A vẫn có thể sống | Thu hồi xuyên hệ thống và đối soát kết quả |
 Chia sẻ OAuth client giữa nhiều đối tác | Không truy vết/thu hồi riêng được | Client và credential riêng theo partner, môi trường, chức năng |
 Xóa bản ghi partner ngay khi ngừng hợp tác | Mất liên kết audit và bằng chứng hợp đồng | Vô hiệu hóa rồi lưu/xóa theo retention policy |
 Đổi IdP chỉ dựa trên yêu cầu email | Có thể bị chiếm quan hệ tin cậy | Xác minh ngoài băng, phê duyệt, kiểm thử và migration có kiểm soát |
 Đồng bộ SCIM thất bại mà không cảnh báo | Quyền thực tế lệch trạng thái mong muốn | Retry, dead-letter/queue nếu dùng, cảnh báo và reconciliation |

## 13. Case study xuyên suốt: đối tác cung ứng B

Công ty A vận hành hệ thống đặt hàng. B là nhà cung cấp vận chuyển, cần ba nhân viên cùng một ứng dụng tự động:

| Mốc | Diễn biến | IAM cần thực hiện |
|---|---|---|
 Ngày 1 — Joiner | A ký hợp đồng với B cho dịch vụ vận chuyển tại Việt Nam | Xác minh B, tạo partner_id, ghi sponsor và scope, thiết lập ngày hết hạn |
 Ngày 5 — Federation | B đề xuất IdP OIDC | Đăng ký issuer tin cậy, kiểm tra đăng nhập, MFA và cách ánh xạ principal |
 Ngày 6 — Human access | Ba người B cần xem đơn hàng | Mời/SCIM theo phê duyệt; gán viewer giới hạn tenant B và dự án giao nhận |
 Ngày 7 — Workload | Ứng dụng B cần API cập nhật trạng thái | Đăng ký OAuth client riêng, cấp scope orders.update_status trong phạm vi B |
 Ngày 40 — Mover | B mở thêm vùng miền Trung | Phê duyệt phạm vi mới, cập nhật quyền và loại bỏ các grant không phù hợp |
 Ngày 65 — Leaver cá nhân | Một nhân viên B nghỉ việc | Disable membership, thu hồi session và grant của người này, đối soát |
 Ngày 80 — Key rotation | B xoay khóa client | Kiểm tra credential mới, chuyển đổi có giám sát, loại bỏ khóa cũ |
 Ngày 120 — Kết thúc hợp đồng | B ngừng cung ứng | Chặn partner, thu hồi mọi user/client/grant liên quan, kiểm chứng và xử lý dữ liệu |

Nếu A chỉ xóa ba user mà bỏ qua OAuth client, ứng dụng B vẫn có thể gọi API sau ngày 120. Nếu A chỉ vô hiệu hóa client mà quên quyền trên cổng web, nhân viên B vẫn có thể truy cập. **Hoàn tất Partner Leaver phải kiểm tra đầy đủ cả người dùng, workload, trust và các ứng dụng đích**.

### Hai quyết định phân quyền khác nhau

**Yêu cầu hợp lệ:** Nhân viên B đã đăng nhập từ issuer được A tin cậy; tài khoản được gắn partner B, membership active, hợp đồng còn hiệu lực; hành động xem đơn thuộc dự án được duyệt. Kết quả: cho phép khi các điều kiện bảo mật liên quan đều thỏa mãn.

**Yêu cầu bị từ chối:** Cùng người dùng đó đổi mã đơn hàng sang đơn của đối tác C. Dù OIDC token hợp lệ và có role viewer, tài nguyên không thuộc tenant/scope B. Kết quả: từ chối tại API, ghi log và có thể phát cảnh báo theo hành vi.

## 14. Checklist triển khai Partner IAM

Trước khi cho một partner truy cập production, đội kỹ thuật, bảo mật và chủ tài nguyên nên kiểm tra:

1. Partner có định danh nội bộ ổn định, pháp nhân được xác minh, sponsor/owner và mục đích hợp tác rõ ràng.
2. Hợp đồng, hạn quan hệ, tenant, dự án và loại dữ liệu được quản lý như các điều kiện cấp quyền.
3. Federation OIDC/SAML có trust configuration và cách ánh xạ issuer → partner an toàn; có quy trình thay IdP/khóa.
4. User và workload principal đều gắn partner_id, owner, scope và lifecycle riêng.
5. SCIM/JIT/invitation không tự mở rộng quyền ngoài phê duyệt; lỗi đồng bộ được theo dõi.
6. RBAC/ABAC kiểm tra partner state, membership, contract validity và tenant/resource scope ở backend.
7. Credential máy được bảo vệ, phân tách môi trường, xoay vòng và thu hồi.
8. Có quy trình Joiner–Mover–Leaver cho cả cấp tổ chức, người dùng và workload.
9. Có offboarding xuyên ứng dụng, kiểm tra session/token/grant và cơ chế reconciliation.
10. Có audit log, lịch access review, báo cáo partner mồ côi và chỉ số thu hồi quyền tồn dư.

## 15. Tự kiểm tra

**Câu 1.** Partner B có IdP đã được A chấp nhận. Một nhân viên mới của B đăng nhập thành công, vậy người đó có quyền xem mọi đơn hàng của B không?

**Trả lời:** Không. Chỉ xác thực thành công chưa đủ. Phải có bản ghi principal/membership hợp lệ, phê duyệt quyền, role, tenant/project scope và điều kiện truy cập đang còn hiệu lực.

**Câu 2.** Tại sao partner_id nên tách khỏi email domain hoặc issuer của đối tác?

**Trả lời:** Vì domain và IdP có thể đổi, được dùng chung hoặc có nhiều cấu hình. Partner_id nội bộ ổn định giúp giữ quan hệ hợp tác, lịch sử quyền và audit, còn các định danh bên ngoài được ánh xạ có kiểm soát.

**Câu 3.** Chấm dứt hợp đồng với B nhưng chỉ khóa đăng nhập SSO, đã đủ chưa?

**Trả lời:** Chưa. Phải xử lý local user, grants, group, session, ứng dụng downstream, OAuth clients/service accounts, credential, trust configuration và dữ liệu còn chia sẻ; xác minh thu hồi thành công.

**Câu 4.** Khi B đổi IdP, có thể ghép người dùng bằng email để giữ nguyên quyền không?

**Trả lời:** Không nên tự động ghép. Cần xác minh yêu cầu thay đổi, xác thực liên kết danh tính cũ–mới bằng phương pháp đáng tin cậy, kiểm tra lại quyền và loại bỏ trust cũ đúng quy trình.

**Câu 5.** SCIM đã đồng bộ “active=false” thì có thể bỏ qua access review và kiểm tra API client không?

**Trả lời:** Không. SCIM chỉ tác động các bản ghi và tích hợp đã cấu hình, không tự kiểm soát mọi session, credential máy và resource grant. Access review và đối soát ở các hệ thống đích vẫn cần thiết.

## Kết luận

Partner identity là nền tảng quản trị danh tính **cấp quan hệ đối tác** trong IAM. Nó nối **xác minh tổ chức, IdP/SSO và federation, SCIM/provisioning, RBAC/ABAC, danh tính người dùng và workload, kiểm toán, rà soát và thu hồi quyền** thành một vòng đời thống nhất. Áp dụng mô hình **Joiner–Mover–Leaver** ở cả cấp tổ chức và principal giúp bảo đảm đối tác chỉ có các quyền phục vụ quan hệ đang hiệu lực, đồng thời giảm tài khoản mồ côi, credential bị bỏ quên và quyền truy cập tồn dư sau thay đổi hoặc chấm dứt hợp tác.
