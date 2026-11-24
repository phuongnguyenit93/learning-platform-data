# Thu hồi API credential trong Account deprovisioning

Một nhân viên đã nghỉ việc có thể không đăng nhập được qua Single Sign-On (SSO) nhưng vẫn gọi API của doanh nghiệp bằng **personal access token (PAT)** từng tạo trước đó. Một tác vụ tự động cũng có thể tiếp tục sử dụng **API key** của người đã rời tổ chức nếu bí mật ấy được sao chép vào biến môi trường hoặc hệ thống CI/CD. Vì vậy, **khóa tài khoản đăng nhập chưa đủ để khẳng định mọi đường truy cập API đã chấm dứt**.

Trong **Identity and Access Management (IAM)**, *thu hồi API credential* là quá trình làm mất hiệu lực những thông tin xác thực dùng để truy cập API, kiểm tra các hệ thống đích thực sự từ chối credential không còn hợp lệ và ngăn chúng bị sử dụng trở lại. Bài học thuộc chương **Account deprovisioning** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, liên hệ quy trình **Joiner–Mover–Leaver (JML)** với xác minh danh tính, quản lý tài khoản và quyền, **IdP**, **SSO**, **SCIM**, **RBAC/ABAC**, tài khoản dịch vụ và kiểm toán nhằm giảm quyền truy cập tồn dư.

Sau bài học, người học có thể:

- Nhận diện các loại API credential và phân biệt **thu hồi**, **vô hiệu hóa**, **xoay vòng bí mật**, **hết hạn** và **thu hồi quyền**.
- Xác định đúng chủ thể, tài khoản, ứng dụng và các workload đang sử dụng một credential trước khi deprovision.
- Thiết kế quy trình thu hồi theo JML, xử lý PAT cá nhân và credential của service account mà vẫn duy trì các dịch vụ hợp lệ.
- Giải thích giới hạn thu hồi của OAuth access token, JWT tự chứa, khóa API, credential lưu trong bộ nhớ đệm và các tích hợp không nằm trong IdP/SCIM.
- Kiểm tra kết quả tại API đích, điều tra trường hợp credential còn hoạt động và lưu bằng chứng kiểm toán an toàn.

## 1. API credential là gì?

**API credential** là bằng chứng mà một hệ thống hoặc người gọi trình bày để được API xác thực. Credential có thể đại diện cho một **người dùng**, **ứng dụng**, **service account**, **service principal** hoặc **workload**. Nó có thể được gửi dưới dạng giá trị bí mật, token mang quyền truy cập hoặc cơ chế mật mã như chứng chỉ khách hàng.

Một API credential **không tự đồng nghĩa** với quyền truy cập: sau khi xác thực danh tính, máy chủ còn có thể đánh giá **scope, role, policy, thuộc tính và tài nguyên** để quyết định được phép làm gì. Tuy vậy, trong nhiều thiết kế, credential chứa hoặc tham chiếu tới các quyền đã được cấp, nên việc để credential hoạt động sau khi chủ thể hết thẩm quyền là rủi ro đáng kể.

### Các loại credential thường gặp

| Loại | Cách sử dụng | Điểm cần biết khi thu hồi |
| --- | --- | --- |
| **API key** | Chuỗi khóa ứng dụng/dự án/tài khoản dùng để gọi API. | Nhà cung cấp có thể cho xóa, disable hoặc rotate key; cần kiểm tra key còn được hệ thống đích chấp nhận không. |
| **Personal Access Token (PAT)** | Token do người dùng tạo để gọi API, Git, CLI hoặc công cụ tự động. | Có thể nằm ngoài phiên SSO; cần kiểm kê theo người sở hữu, scope, hạn dùng và nơi đang sử dụng. |
| **OAuth 2.0 access token** | Token để resource server cho phép truy cập tài nguyên trong khoảng hiệu lực. | Khả năng vô hiệu hóa ngay phụ thuộc mô hình token và cách resource server kiểm tra. |
| **OAuth 2.0 refresh token** | Credential dùng để xin access token mới theo grant được cấp. | Thu hồi để ngăn lấy token mới; access token đã phát hành có thể vẫn còn hiệu lực một thời gian. |
| **OAuth client secret** | Bí mật dùng bởi client được cấu hình là confidential client để xác thực với authorization server. | Xoay/thu hồi bí mật và đánh giá các grant, token đã phát hành; thay client secret không mặc nhiên thu hồi mọi access token cũ. |
| **Khóa truy cập đám mây** | Access key/secret hoặc credential dài hạn của danh tính cloud. | Tắt hoặc xóa từng khóa, rà soát các phiên/credential tạm thời và quyền IAM liên quan. |
| **Chứng chỉ mTLS / khóa ký** | Xác thực client hoặc chứng minh quyền sở hữu khóa bằng mật mã. | Thu hồi/thay chứng chỉ hoặc mapping trust, cập nhật cơ chế kiểm tra của API đích; CRL/OCSP chỉ có tác dụng khi hệ thống thực sự kiểm tra. |
| **Credential ngắn hạn của workload** | Token do nền tảng cấp theo danh tính workload, thường có hạn ngắn. | Thu hồi quan hệ tin cậy/quyền cấp token mới và xem xét token còn sống cho tới hết hạn. |

Token SSO, cookie phiên trình duyệt, khóa SSH và mật khẩu **có thể tạo ra đường truy cập liên quan**, nhưng không phải tất cả đều là cùng một loại API credential. Inventory của deprovisioning cần bao quát những đường truy cập thực tế mà tổ chức sử dụng.

## 2. Phân biệt những hành động dễ bị đánh đồng

| Hành động | Ý nghĩa | Điều chưa chắc đã xảy ra |
| --- | --- | --- |
| **Revoke credential** | Làm một credential hoặc grant không còn hợp lệ theo cơ chế của hệ thống phát hành/kiểm tra. | Không bảo đảm mọi bản sao token tự chứa bị từ chối tức thì nếu resource server chỉ kiểm tra chữ ký và hạn dùng. |
| **Disable account/principal** | Khóa danh tính hoặc tài khoản ở IdP, cloud hoặc ứng dụng. | Không chắc vô hiệu hóa PAT, API key hay phiên cục bộ đã cấp độc lập. |
| **Rotate credential** | Phát credential mới, thay ở bên dùng và vô hiệu hóa credential cũ theo kế hoạch. | Nếu bỏ quên bước hủy credential cũ thì hai credential có thể cùng hoạt động. |
| **Expire** | Credential tự mất hiệu lực sau thời điểm hết hạn đã quy định. | Chờ hết hạn không nhất thiết đáp ứng yêu cầu khóa ngay của Leaver. |
| **Revoke entitlement** | Thu hồi role, nhóm, scope, policy hoặc quyền ở hệ thống đích. | Một credential vẫn có thể xác thực thành công nhưng bị từ chối quyền cụ thể, hoặc được dùng ở hệ thống khác. |
| **Delete secret from vault/config** | Loại bỏ bản sao bí mật tại nơi ứng dụng lưu. | Key/token ở nhà cung cấp có thể vẫn hoạt động nếu chưa bị thu hồi tại nguồn. |
| **Delete account** | Xóa tài khoản và tài nguyên theo hành vi của provider. | Có thể làm mất hồ sơ kiểm toán và dữ liệu nghiệp vụ; không được mặc định là giải pháp phù hợp nhất. |

**Quy tắc:** thu hồi một đường truy cập là đạt được khi **credential liên quan không còn cung cấp quyền truy cập ngoài ý muốn tại hệ thống đích**, với bằng chứng phù hợp về trạng thái và giới hạn kỹ thuật. Ticket “đã gửi lệnh revoke” chỉ xác nhận một bước của quy trình.

## 3. Vì sao API credential dễ bị bỏ sót khi Leaver?

API credential thường được tạo trong nhiều thời điểm và lưu tại nhiều nơi:

- Nhân viên dùng PAT để chạy script tích hợp CRM với bảng dữ liệu.
- Developer tạo token cho Git, hệ thống quản lý issue, công cụ triển khai.
- Job CI/CD dùng API key trong biến môi trường hoặc kho bí mật.
- Ứng dụng dùng OAuth grant hoặc service principal để gọi API bên thứ ba.
- Người vận hành tạo khóa phụ khi xử lý sự cố và không khai báo vào danh mục IAM.
- API key được sao chép vào ứng dụng cũ, file cấu hình, bản backup hoặc notebook kỹ thuật.

**Không thể hoàn toàn dựa vào một bảng tài khoản IdP để tìm các credential này**. Một số credential do chính ứng dụng SaaS, nền tảng cloud hoặc máy chủ API cấp và kiểm tra; những hệ thống ấy có thể có vòng đời riêng, không tự đồng bộ mọi key/token qua SCIM.

### Ba dạng tồn dư khác nhau

1. **Credential của người đã rời tổ chức vẫn hợp lệ:** PAT cá nhân còn được API chấp nhận dù tài khoản SSO đã khóa.
2. **Credential dùng chung có người nghỉ việc từng biết:** key không gắn trực tiếp với Leaver nhưng có nguy cơ bị họ tiếp tục sử dụng; cần thay key hoặc điều chỉnh trust.
3. **Credential dịch vụ không còn owner hợp lệ:** một service principal tiếp tục chạy đúng chức năng, nhưng không có người chịu trách nhiệm rà soát quyền, lưu bí mật và xử lý sự cố.

Ba trường hợp cần xử lý khác nhau. Việc xóa tất cả service account mà người nghỉ từng tạo có thể làm gián đoạn hệ thống; việc giữ nguyên mọi key vì sợ gián đoạn lại để lại quyền truy cập không được kiểm soát.

## 4. Chuẩn bị danh mục credential và liên kết chủ sở hữu

Deprovisioning chỉ đáng tin cậy nếu biết credential thuộc **chủ thể nào**, do **hệ thống nào phát hành**, còn được **workload nào sử dụng** và có **quyền gì**.

### Các trường cần thiết trong inventory

| Thuộc tính | Ý nghĩa | Ghi chú bảo mật |
| --- | --- | --- |
| \`credentialId\` / key ID | Định danh tham chiếu tới credential. | Không lưu raw secret trong bảng inventory. |
| \`credentialType\` | API key, PAT, refresh token, certificate, cloud access key... | Quy định cách thu hồi tương ứng. |
| \`issuer\` / provider | Hệ thống phát hành hoặc quản lý credential. | Quyết định API/console kiểm tra trạng thái. |
| \`subjectId\` / principal ID | Danh tính người hoặc máy mà credential đại diện. | Dùng ID ổn định, có namespace; tránh gắn bằng email đơn thuần. |
| \`ownerSubjectId\` / \`ownerTeamId\` | Người/nhóm chịu trách nhiệm quản lý credential. | Có thể khác principal kỹ thuật dùng credential. |
| \`applicationId\`, \`workloadId\` | Ứng dụng, pipeline, job hoặc dịch vụ đang sử dụng. | Hỗ trợ đánh giá tác động khi rotate/revoke. |
| \`environment\`, \`resource\` | Môi trường và API đích. | Phân biệt production với thử nghiệm. |
| \`scope\`, \`role\` hoặc policy | Phạm vi quyền hiện được cấp. | Đọc từ nguồn có thẩm quyền, không suy đoán từ tên key. |
| \`issuedAt\`, \`expiresAt\`, \`lastUsedAt\` | Các mốc vòng đời và dữ liệu sử dụng. | \`lastUsedAt\` có thể chậm hoặc không đầy đủ; không sử dụng làm bằng chứng duy nhất. |
| \`status\`, \`lastVerifiedAt\` | Trạng thái tại nhà cung cấp và lần xác minh gần nhất. | Phân biệt \`ACTIVE\`, \`REVOKE_REQUESTED\`, \`REVOKED_VERIFIED\`. |
| \`secretLocationRef\` | Tham chiếu kho bí mật/vị trí cấu hình đã đăng ký. | Chỉ lưu đường tham chiếu được bảo vệ, không lưu giá trị key. |
| \`retentionClass\`, \`auditRef\` | Quy tắc giữ metadata và chuỗi bằng chứng. | Không lưu bí mật đã thu hồi chỉ để tiện kiểm toán. |

Ví dụ bản ghi kiểm kê **không chứa giá trị bí mật**:

~~~json
{
  "credentialId": "pat-7841",
  "credentialType": "PERSONAL_ACCESS_TOKEN",
  "issuer": "source-control-platform",
  "subjectId": "person-1042",
  "ownerSubjectId": "person-1042",
  "applicationId": "release-automation",
  "environment": "production",
  "scopes": ["repository-read", "pipeline-trigger"],
  "issuedAt": "2026-08-15T08:30:00Z",
  "expiresAt": "2027-02-15T08:30:00Z",
  "status": "ACTIVE",
  "secretLocationRef": "vault-ref:team/release/pat",
  "auditRef": "IAM-CRED-502"
}
~~~

**Không nên đưa API key, private key, bearer token hay refresh token vào log, ticket, file CSV hoặc ví dụ minh họa thật.** Trong trường hợp cần so sánh credential, ưu tiên ID do provider cấp hoặc giá trị nhận diện dẫn xuất không thể dùng để đăng nhập, theo thiết kế bảo mật được phê duyệt.

### Nguồn dữ liệu kiểm kê

Inventory thường phải tổng hợp từ **IdP/IGA**, bảng API key ở SaaS, công cụ quản lý cloud IAM, **secrets manager**, hệ thống CI/CD, API gateway, công cụ quản lý đặc quyền và chủ sở hữu ứng dụng. Nếu không kiểm kê được một provider, cần ghi rõ **khoảng trống bao phủ** và người chịu trách nhiệm xử lý; không kết luận “không có credential” khi nguồn chưa thể kiểm tra.

## 5. Luồng thu hồi API credential trong Account deprovisioning

~~~mermaid
flowchart TD
    A["Nguồn có thẩm quyền<br/>HRIS / hợp đồng / owner workload"] --> B["IAM/IGA tiếp nhận sự kiện JML"]
    B --> C["Xác minh chủ thể và inventory<br/>credential + quyền + hệ thống đích"]
    C --> D{"Credential gắn<br/>người hay dịch vụ?"}
    D -->|Người| E["Thu hồi credential cá nhân<br/>và hạn chế truy cập ngay theo chính sách"]
    D -->|Dịch vụ| F["Xác định owner mới<br/>đánh giá thay secret / chuyển trust"]
    F --> G["Triển khai credential thay thế<br/>đã được phê duyệt"]
    G --> H["Thu hồi credential cũ"]
    E --> I["Kiểm tra provider và<br/>API/resource server"]
    H --> I
    I --> J{"Đã xác minh<br/>không còn quyền?"}
    J -->|Chưa| K["Cảnh báo / retry / biện pháp hạn chế<br/>ngoại lệ có owner và hạn xử lý"]
    K --> I
    J -->|Rồi| L["Lưu bằng chứng kiểm toán<br/>đối soát và đóng tác vụ"]
~~~

### Bước 1. Xác định sự kiện, đúng danh tính và thời điểm hiệu lực

Với Leaver, nguồn có thẩm quyền có thể là **HRIS** đối với Employee hoặc hệ thống hợp đồng/sponsor đối với Contractor. Sự kiện cần có mã chủ thể/engagement, thời điểm có hiệu lực, loại thay đổi và mức ưu tiên (ví dụ chấm dứt khẩn).

Với Mover, việc thay vai trò, bộ phận hoặc trách nhiệm có thể khiến một credential không còn được phép sử dụng dù chủ thể vẫn là nhân viên. Không nên chờ tới Leaver mới đánh giá key quá rộng hoặc credential cá nhân đang chạy hộ workload.

### Bước 2. Tìm đầy đủ credential và đường truy cập phụ thuộc

Tra theo ID ổn định của người dùng, principal ID, service account, ứng dụng và owner. Phân loại:

- Credential cá nhân phải thu hồi.
- Credential dùng chung/người nghỉ từng biết phải thay hoặc thu hồi theo rủi ro.
- Credential thuộc workload hợp lệ cần owner mới và kế hoạch chuyển đổi an toàn.
- Credential không rõ owner hoặc không rõ ứng dụng cần cô lập, đánh giá trước khi tiếp tục cho phép.

Làm rõ tác động tới job production và các tích hợp phía sau; một credential có thể đang được nhiều hệ thống dùng do từng bị sao chép ngoài quy trình.

### Bước 3. Chặn khả năng tiếp tục phát sinh truy cập

Tùy loại credential, ưu tiên **disable/revoke tại issuer**, thu hồi grant, khóa principal hoặc sửa trust/policy tại resource server. Với credential gắn người rời tổ chức, chính sách thường yêu cầu chấm dứt khả năng truy cập tại thời điểm Leaver có hiệu lực. Nếu một token cũ có thể vẫn sống đến lúc hết hạn, cần đánh giá biện pháp giảm thiểu tương ứng: denylist, introspection, vô hiệu hóa tài khoản ở resource server, thay policy hoặc thu ngắn thời hạn token nếu nền tảng hỗ trợ.

### Bước 4. Di chuyển workload hợp lệ sang credential an toàn

Với tác vụ tự động cần tiếp tục chạy, có thể chuyển sang **workload identity** hoặc service principal riêng với owner nhóm, scope tối thiểu và credential ngắn hạn. Nếu phải rotate secret, cần triển khai key mới ở nơi dùng, kiểm tra chức năng rồi thu hồi key cũ.

**Không kéo dài hiệu lực PAT cá nhân sau ngày Leaver chỉ vì job đang dùng nó.** Cần phương án chuyển workload sang principal được phép; nếu chưa hoàn tất trong thời gian yêu cầu, áp dụng quy trình ngoại lệ và biện pháp giảm thiểu được phê duyệt, không bỏ qua thu hồi.

### Bước 5. Xác minh tại hệ thống phát hành và API đích

Kiểm tra trạng thái key/token ở provider, kết quả API thu hồi, trạng thái grant và kết quả thực tế của các API thuộc phạm vi. Với hệ thống nhạy cảm, xác nhận không còn các lời gọi được **chấp nhận** từ credential đã bị thu hồi; theo dõi các nỗ lực sử dụng key cũ và lỗi phân quyền.

Phản hồi \`200 OK\` từ thao tác revoke hoặc \`active=false\` trên tài khoản chưa luôn đủ để kết luận mọi resource server và cache đã ngừng chấp nhận credential. Phải dựa trên **cơ chế kiểm tra cụ thể** của hệ thống đích.

### Bước 6. Ghi bằng chứng, quản lý lỗi và đối soát

Kết quả của từng credential cần có trạng thái riêng: được phát hiện, đã yêu cầu thu hồi, đã gửi tới provider, đã nhận phản hồi, đã xác minh vô hiệu hoặc đang có ngoại lệ. Gắn mọi bước với sự kiện JML và lưu log phù hợp, tránh ghi giá trị bí mật.

## 6. Thu hồi theo từng loại API credential

### 6.1. API key và Personal Access Token (PAT)

API key/PAT có thể được cấp trực tiếp trong ứng dụng SaaS hoặc cloud. Để thu hồi, thường cần thao tác tại **chính provider sở hữu key**, không chỉ đổi mật khẩu hoặc khóa SSO.

Quy trình:

1. Liệt kê key/PAT theo owner/principal và phạm vi ứng dụng.
2. Đối chiếu ID key, quyền, môi trường, thời hạn và nơi sử dụng.
3. Disable hoặc revoke/delete key bằng API quản trị/console của provider theo quy định.
4. Kiểm tra key ở danh sách quản trị đã mất hiệu lực, đồng thời kiểm tra API đích hoặc nhật ký từ chối khi thích hợp.
5. Gỡ key khỏi secrets manager, pipeline, biến môi trường và nơi sao chép **sau khi đã xử lý quyền tại nguồn**; đánh giá backup/vòng đời bản sao.
6. Nếu key do nhiều workload cùng dùng, chuyển từng workload sang credential riêng trước khi hủy theo kế hoạch đã phê duyệt.

Việc **xóa chuỗi key trong cấu hình** chỉ xóa một bản sao, không chứng minh provider đã vô hiệu hóa nó. Ngược lại, **thu hồi key tại provider** có thể làm ứng dụng đang dùng gặp lỗi; phải đánh giá tác động và theo dõi dịch vụ trong kế hoạch xử lý.

### 6.2. OAuth 2.0 refresh token

Refresh token thường có khả năng xin access token mới mà không cần người dùng nhập lại thông tin xác thực. Một nhân viên nghỉ việc nhưng refresh token vẫn hợp lệ có thể tiếp tục lấy access token tùy hành vi của authorization server.

Các bước phù hợp:

- Thu hồi refresh token hoặc grant/session tương ứng bằng cơ chế provider hỗ trợ; trường hợp cần thiết thu hồi toàn bộ grant liên quan người dùng/client.
- Kiểm tra có thể cấp access token mới bằng grant cũ hay không qua cơ chế kiểm soát phù hợp; không phát tán refresh token để “thử”.
- Đánh giá các access token đã phát hành trước khi thu hồi refresh token vì chúng **có thể còn hiệu lực tới khi hết hạn** hoặc tới khi resource server nhận được tín hiệu thu hồi.
- Nếu server sử dụng *refresh token rotation*, xử lý họ token/token family theo cơ chế provider thay vì chỉ hủy một bản sao đã biết.

RFC 7009 định nghĩa một **token revocation endpoint** cho OAuth 2.0, nhưng việc provider có hỗ trợ token nào, hiệu lực dây chuyền với các token liên quan và khả năng các resource server nhận biết ngay vẫn phụ thuộc triển khai. Không giả định “revoke refresh token” đồng nghĩa mọi access token đang sống đều bị vô hiệu tức thì.

### 6.3. OAuth 2.0 access token và JWT

Đây là trường hợp cần phân biệt kiến trúc:

| Cách resource server kiểm tra | Khả năng làm access token mất hiệu lực trước khi hết hạn |
| --- | --- |
| **Opaque/reference token** tra trạng thái ở authorization server hoặc introspection endpoint. | Có thể ngừng cho phép sớm nếu nguồn kiểm tra cập nhật trạng thái và cache được xử lý đúng. |
| **JWT tự chứa**, resource server chỉ kiểm chữ ký, \`aud\`, \`iss\`, \`exp\`, scope. | Có thể vẫn được chấp nhận tới hạn \`exp\` nếu không có cơ chế revocation/denylist/policy cập nhật. |
| **JWT với denylist/token version hoặc tra quyền hiện tại** tại API. | Có thể chặn sớm nếu dữ liệu thu hồi được truyền tới mọi resource server có liên quan. |
| **Token ràng buộc khóa/chứng chỉ** (sender-constrained). | Cần kiểm tra cả trạng thái token và khóa/chứng chỉ hoặc quan hệ tin cậy tương ứng theo triển khai. |

Biện pháp thiết kế có thể gồm access token sống ngắn, thu hồi refresh token, kiểm tra quyền hiện hành tại API, introspection, denylist được đồng bộ, thay đổi phiên bản hoặc policy của principal. Không có một “lệnh thu hồi JWT” mang hiệu lực chung cho mọi hệ thống.

Khi đánh giá sự cố, ghi rõ **khoảng thời gian token còn có thể hoạt động** và biện pháp kiểm soát được triển khai; không tuyên bố đã chặn tức thì nếu resource server chỉ kiểm \`exp\`.

### 6.4. OAuth client secret, certificate và service principal

Một **client secret** hoặc chứng chỉ thường xác thực ứng dụng, khác với access token mà ứng dụng dùng để gọi API. Khi người phụ trách rời tổ chức hoặc một secret bị lộ:

1. Xác định client/service principal, owner, workload, môi trường và các token/grant liên quan.
2. Thiết lập credential thay thế theo chính sách, cập nhật nơi sử dụng và kiểm tra hoạt động nếu dịch vụ cần tiếp tục.
3. Vô hiệu hóa secret/chứng chỉ cũ tại provider; rà soát quyền client và grant có còn hợp lệ không.
4. Đánh giá token đã phát hành, khả năng giữ phiên, trust relationship và đường truy cập từ workload cũ.
5. Lưu bằng chứng thời gian chuyển đổi và tình trạng từng đích; xử lý nơi còn secret cũ trong cấu hình, backup hoặc máy chạy.

**Xoay client secret không nhất thiết thu hồi access token đã phát hành trước đó.** Phải đánh giá cả credential xác thực client và token dùng tại resource server.

### 6.5. Credential đám mây và workload identity

Nhiều nền tảng cloud cho phép phát hành access key dài hạn, session token ngắn hạn hoặc credential từ workload identity federation. Việc thu hồi cần phân biệt:

- **Khóa dài hạn**: disable/delete key theo tính năng provider; loại bỏ khỏi máy và kho bí mật.
- **Phiên tạm thời**: đánh giá thời gian hiệu lực và cơ chế provider hỗ trợ để từ chối phiên/token đã phát hành.
- **Quyền của principal**: cập nhật role, policy, trust relationship và quyền assume/impersonate.
- **Workload identity federation**: chặn việc phát hành credential mới từ nguồn không còn tin cậy, đồng thời đánh giá token còn hiệu lực.

Với workload, ưu tiên credential ngắn hạn hoặc danh tính máy gắn chặt vào môi trường chạy khi nền tảng hỗ trợ; như vậy giảm rủi ro có một API key lâu năm không rõ owner.

## 7. API credential trong Joiner–Mover–Leaver

Thu hồi là bước nổi bật của Leaver nhưng việc quản lý credential phải bắt đầu từ khi chủ thể được cấp quyền.

| Giai đoạn | Cách xử lý API credential | Điểm kiểm soát |
| --- | --- | --- |
| **Joiner** | Cấp credential chỉ sau khi xác minh, có owner, scope, hạn dùng và mục đích rõ. | Tránh tạo PAT cá nhân làm credential cố định cho hệ thống sản xuất. |
| **Mover** | Rà soát scope, quyền, ứng dụng phụ thuộc, manager/owner và credential liên quan vai trò cũ. | Thu hồi/rotate credential không còn phù hợp, không chỉ cộng quyền mới. |
| **Leaver** | Thu hồi credential cá nhân; xử lý key dùng chung người nghỉ từng biết; chuyển service account owner và secret hợp lệ. | Xác minh provider và API đích, phát hiện quyền tồn dư ngoài SSO. |
| **Rehire** | Xác minh lại người thật và quan hệ mới; cấp credential mới theo chính sách. | Không tự phục hồi PAT, khóa hoặc grant của giai đoạn làm việc đã kết thúc. |
| **Workload decommission** | Hủy trust, token, key, certificate và quyền của dịch vụ không còn vận hành. | Kiểm tra các ứng dụng đích và bản sao bí mật trước khi đóng. |

### Sự kiện Mover có thể cần thu hồi cả khi người dùng vẫn đăng nhập bình thường

Ví dụ một kỹ sư chuyển khỏi đội vận hành sản xuất nhưng vẫn là Employee. Tài khoản IdP có thể giữ nguyên, trong khi cloud API key có quyền quản trị, PAT triển khai và token truy cập hệ thống quan sát cần được thu hồi hoặc giới hạn. **Trạng thái Employee = ACTIVE không bảo đảm mọi credential cũ vẫn được phép dùng.**

### Thời điểm thu hồi và tính nhất quán

Với sự kiện có hiệu lực trong tương lai, workflow cần lên lịch và **kiểm tra lại dữ liệu nguồn hiện tại khi đến hạn**. Với chấm dứt khẩn, cần ưu tiên hạn chế ngay các đường truy cập theo chính sách. Tác vụ thu hồi phải hỗ trợ sự kiện lặp, đến trễ, thất bại một phần và trạng thái không rõ. Không cho sự kiện cũ tự động khôi phục credential sau khi đã bị thu hồi.

## 8. IdP, SSO, SCIM và RBAC/ABAC liên quan thế nào?

### IdP và SSO

**IdP** quản lý xác thực và có thể cấp OAuth/OIDC token cho các ứng dụng. **SSO** giúp người dùng đăng nhập tập trung, nhưng nhiều API credential được quản lý **bên ngoài** IdP (PAT của SaaS, key trong cloud, credential của API gateway). Khóa SSO có thể chặn cấp token mới qua một số luồng, nhưng không tự chứng minh token, key và phiên đã cấp ở mọi hệ thống đã vô hiệu.

### SCIM

**SCIM** chủ yếu chuẩn hóa quản lý tài nguyên User và Group. Lệnh đặt \`active=false\` cho SCIM User có thể vô hiệu hóa tài khoản ứng dụng theo cách provider thực thi, **nhưng SCIM không phải giao thức tổng quát để liệt kê hoặc thu hồi mọi API key, OAuth grant, refresh token, chứng chỉ hay service principal**. Những đối tượng đó thường cần API quản trị riêng, tích hợp cloud, công cụ secrets hoặc thao tác chuyên biệt.

Khi thiết kế offboarding, nên lưu ma trận **ứng dụng × loại credential × phương thức thu hồi × kết quả kiểm chứng** để biết chính xác hệ thống nào cần nhiều hơn thao tác SCIM.

### RBAC/ABAC và least privilege

**RBAC** quyết định quyền từ vai trò, còn **ABAC** có thể dựa vào thuộc tính người dùng, tài nguyên và ngữ cảnh. Thu hồi vai trò/quyền có thể khiến một credential còn xác thực được nhưng không thể thực hiện API nhạy cảm; đó là một lớp bảo vệ hữu ích. Tuy nhiên, nếu credential còn được chấp nhận ở API khác hoặc một policy/cache chưa cập nhật, rủi ro vẫn tồn tại.

Nên kết hợp:

- Thu hồi credential đã hết nhu cầu.
- Thu hồi nhóm, scope, role hoặc trust liên quan.
- Phân quyền tối thiểu cho credential mới.
- Ràng buộc vào workload, môi trường và thời hạn khi có thể.
- Rà soát quyền đặc quyền và separation of duties đối với người duyệt ngoại lệ.

## 9. Đảm bảo dịch vụ tiếp tục hoạt động mà không giữ credential của Leaver

Một lỗi kiến trúc phổ biến là dùng PAT do nhân viên cấp để chạy công việc tự động lâu dài. Khi người đó nghỉ việc, nhóm vận hành có thể muốn trì hoãn thu hồi để hệ thống “không bị ngắt”.

**Tình huống:** PAT của Minh kích hoạt pipeline triển khai sản xuất. Minh nghỉ việc lúc 17:00, còn pipeline được lên lịch 18:00.

Phương án phù hợp:

1. Xác định pipeline, permission/scopes, chủ sở hữu nghiệp vụ và môi trường đang dùng PAT.
2. Tạo danh tính workload/service principal riêng, thuộc nhóm có trách nhiệm và có quyền tối thiểu cho công việc triển khai.
3. Lưu credential mới trong secrets manager hoặc dùng workload identity federation/credential ngắn hạn khi được hỗ trợ.
4. Kiểm tra pipeline trong phạm vi có kiểm soát; cập nhật deployment/configuration, bảo đảm không còn tham chiếu tới PAT của Minh.
5. Thu hồi PAT cá nhân của Minh tại provider **trong thời hạn được chính sách Leaver yêu cầu**; kiểm chứng việc không còn truy cập.
6. Ghi owner mới, log thay đổi, kết quả job và mọi ngoại lệ chưa giải quyết.

Nếu không thể hoàn tất chuyển đổi trước hạn thu hồi, phải ưu tiên kiểm soát truy cập và quy trình xử lý sự cố/ngoại lệ theo rủi ro. **Không dùng việc dịch vụ đang phụ thuộc vào key cá nhân làm lý do mặc định giữ key đó hoạt động sau khi chủ sở hữu mất thẩm quyền.**

### Chọn chiến lược thay credential

| Chiến lược | Khi nào phù hợp | Điều kiện an toàn |
| --- | --- | --- |
| **Revoke ngay** | PAT người đã nghỉ, key bị lộ, principal không còn hợp lệ. | Biết tác động và có khả năng khôi phục dịch vụ bằng đường được phép; xử lý ưu tiên theo chính sách. |
| **Create → migrate → revoke** | Workload hợp lệ phải tiếp tục dùng một credential dài hạn. | Thời gian chồng lấn ngắn và có phê duyệt, secret mới phân phối an toàn, key cũ bị hủy đúng hạn. |
| **Chuyển sang workload identity/short-lived token** | Nền tảng hỗ trợ danh tính máy và phát credential theo phiên. | Trust giới hạn đúng workload/môi trường, owner rõ ràng, token có tuổi thọ và scope phù hợp. |
| **Thu hồi grant/quyền và giữ bản ghi audit** | Cần chấm dứt khả năng cấp token nhưng phải giữ bằng chứng hoạt động. | Không giữ raw secret; đối soát token còn sống và thời hạn lưu log. |

Không nên tạo một shared key mới rồi chia qua email hoặc ticket; cách đó chỉ chuyển rủi ro sang bí mật khác.

## 10. Quy trình xử lý sự kiện và trạng thái

Một thông điệp Leaver minh họa:

~~~json
{
  "eventId": "hr-evt-20261130-142",
  "eventType": "ENGAGEMENT_TERMINATED",
  "sourceSystem": "HRIS",
  "subjectId": "person-1042",
  "engagementId": "EMP-5812",
  "effectiveAt": "2026-11-30T17:00:00+07:00",
  "recordVersion": 17,
  "reasonCode": "EMPLOYMENT_ENDED"
}
~~~

Một orchestrator có thể xử lý ở mức giả mã:

~~~text
onTrustedLifecycleEvent(event):
    verifySourceAndSchema(event)
    if alreadyProcessed(event.eventId):
        return
    if eventIsStale(event):
        recordIgnoredEvent(event)
        return

    subject = resolveSubjectAndEngagement(event)
    credentials = listCredentialsAcrossRegisteredProviders(subject)
    for credential in credentials:
        classifyOwnershipAndRisk(credential)
        if credential.belongsToTerminatedPerson:
            enqueueRevocation(credential, event)
        else if credential.isSharedOrWorkloadDependency:
            enqueueOwnerTransferAndCredentialReplacement(credential, event)
        else:
            openReviewCase(credential, event)

onRevocationJob(job):
    current = reloadCredentialAndLifecycleState(job.credentialId)
    if current.isAlreadyRevoked:
        verifyAndRecord(job, current)
        return
    if not current.revocationStillAuthorized:
        holdAndEscalate(job)
        return

    result = callProviderRevocation(current.credentialId)
    recordProviderResponse(job, result)
    verifyIssuerAndEffectiveApiState(job)
    if verificationFailedOrUnknown(job):
        openTrackedException(job)
    else:
        markRevokedVerified(job)
~~~

**Giả mã chỉ biểu diễn quy trình**, không phải triển khai API cụ thể. Trên thực tế cần xác thực thông điệp nguồn, chống xử lý trùng, giới hạn quyền của worker, retry có backoff, xử lý rate limit, bảo vệ bí mật, kiểm soát phiên bản và cách xác minh theo từng nhà cung cấp.

### 10.1. Trạng thái từng credential

| Trạng thái gợi ý | Ý nghĩa | Phải làm gì tiếp? |
| --- | --- | --- |
| \`DISCOVERED\` | Credential đã được phát hiện. | Liên kết owner/principal, phân loại và đánh giá rủi ro. |
| \`REVOCATION_REQUIRED\` | Có căn cứ phải thu hồi. | Xác định nguồn phát hành và cách thu hồi được phép. |
| \`REQUESTED\` | Tác vụ đã được tạo hoặc chấp thuận. | Điều phối tới provider. |
| \`SENT\` | Đã gửi yêu cầu thu hồi. | Chờ/kiểm tra kết quả ở provider. |
| \`ACKNOWLEDGED\` | Provider đã phản hồi theo giao thức. | Xem ngữ nghĩa phản hồi; có thể cần kiểm tra thêm tại API đích. |
| \`REVOKED_VERIFIED\` | Đã xác minh credential không còn truy cập trái phép trong phạm vi và giả định đã ghi. | Lưu bằng chứng, đóng tác vụ. |
| \`FAILED\` / \`UNKNOWN\` | Lỗi hoặc chưa có xác nhận đủ tin cậy. | Retry/cảnh báo, hạn chế quyền bổ sung, tạo ngoại lệ có owner. |
| \`EXCEPTION_APPROVED\` | Có ngoại lệ hợp lệ, giới hạn rõ về lý do/thời hạn. | Giám sát liên tục và đóng khi điều kiện ngoại lệ kết thúc. |

Từ \`SENT\` sang \`REVOKED_VERIFIED\` **không phải là thay đổi trạng thái tự động chỉ dựa trên HTTP success**. Với provider khác nhau, phải hiểu rõ phản hồi chứng minh được điều gì.

### 10.2. Xử lý lỗi và sự kiện cạnh tranh

- **Idempotency:** cùng sự kiện Leaver không được gây tạo thêm key, cấp lại credential hoặc làm hỏng trạng thái đã thu hồi.
- **Stale events:** sự kiện Mover/Joiner cũ đến muộn không được kích hoạt lại credential của Leaver.
- **Partial failure:** một SaaS thành công nhưng API key ở cloud vẫn hoạt động; giữ trạng thái riêng cho từng mục.
- **Rate limit/timeout:** timeout không chứng minh lệnh thất bại; cần kiểm tra trạng thái provider trước khi retry.
- **Rehire:** một người được tuyển lại là quan hệ mới có xác minh; cấp credential mới theo chính sách, không phục hồi token/PAT đã bị thu hồi.
- **Emergency revoke:** với dấu hiệu key bị lộ hoặc truy cập trái phép, áp dụng ưu tiên xử lý sự cố thay vì chờ chu kỳ deprovision thông thường.

## 11. Xác minh thu hồi: bằng chứng nào đủ?

Đánh dấu “đã thu hồi” phải dựa trên **nhiều loại bằng chứng phù hợp với provider**:

| Bằng chứng | Điều có thể xác nhận | Giới hạn |
| --- | --- | --- |
| **API/console quản trị** | Key/token/grant đã bị disable/revoke theo hệ thống phát hành. | Không tự chứng minh resource server không còn dùng cache cũ. |
| **Resource server từ chối credential** | Một lần yêu cầu có kiểm soát bị từ chối bởi API đích. | Chỉ kiểm tra đường đi, thời điểm và phạm vi cụ thể; không đại diện mọi API. |
| **Log ứng dụng/API gateway** | Lệnh gọi sử dụng credential đã dừng được chấp nhận hoặc phát sinh từ chối. | Thiếu log không chắc có nghĩa không có truy cập; log có thể trễ. |
| **Đối soát quyền/principal** | Scope, role, trust và account status đã phù hợp trạng thái mong đợi. | Credential khác cùng principal có thể vẫn truy cập; cần kiểm kê. |
| **Xác minh đổi credential của workload** | Dịch vụ đã chuyển sang principal/key mới, key cũ bị thu hồi. | Cần kiểm tra job phụ, máy cũ và fallback configuration. |
| **Giới hạn hiệu lực token** | Thời gian tối đa token còn có thể được chấp nhận theo thiết kế. | Dựa trên giả định đồng hồ, cache, verifier, token TTL và policy thực tế. |

**Không nên sao chép raw credential vào ticket hoặc thử gửi credential đó đến endpoint không được kiểm soát.** Việc kiểm thử âm tính, nếu cần, phải do quy trình bảo mật được phép thực hiện trong môi trường/đường gọi phù hợp và không làm lộ bí mật. Trong nhiều trường hợp có thể xác minh qua ID key, trạng thái issuer, policy và log của API đích mà không cần nắm giá trị bí mật.

### Đánh giá cửa sổ truy cập tồn dư

Có thể phân biệt:

- **Effective termination time:** thời điểm nguồn có thẩm quyền xác nhận chủ thể không còn quyền.
- **Revocation requested at:** thời điểm IAM gửi yêu cầu.
- **Issuer disabled at:** thời điểm issuer ghi nhận credential/grant bị vô hiệu.
- **Target enforcement verified at:** thời điểm kiểm tra được API đích từ chối truy cập hoặc hết quyền theo cơ chế đã mô tả.
- **Potential residual access window:** khoảng thời gian credential có thể còn được chấp nhận do cache, token đã phát hành hoặc hệ thống đích chưa cập nhật.

Nếu không đo được toàn bộ cửa sổ truy cập tồn dư, hãy **ghi rõ giới hạn quan sát** thay vì báo “0 giây” hay “đã xóa mọi truy cập”.

## 12. Truy vết và kiểm toán không làm lộ credential

Đối với một tác vụ thu hồi, thông tin tối thiểu nên gồm:

| Trường | Ví dụ hoặc ý nghĩa |
| --- | --- |
| \`eventId\`, \`traceId\`, \`requestId\` | Liên kết sự kiện JML và mọi thao tác tại provider. |
| \`subjectId\`, \`engagementId\` | Người/quan hệ làm việc bị tác động. |
| \`credentialId\`, \`credentialType\`, \`issuer\` | Credential nào, loại gì, do hệ thống nào phát hành. |
| \`ownerId\`, \`applicationId\` | Người/nhóm chịu trách nhiệm và ứng dụng sử dụng. |
| \`action\`, \`reasonCode\` | Thu hồi do Leaver, Mover, hết hạn, key bị lộ hoặc decommission. |
| \`effectiveAt\`, \`requestedAt\`, \`verifiedAt\` | Thời điểm nghiệp vụ, yêu cầu và xác minh ở hệ thống đích. |
| \`providerResult\`, \`verificationMethod\` | Provider trả gì và đã kiểm tra trạng thái thế nào. |
| \`policyId\`, \`policyVersion\` | Quy tắc kiểm soát dẫn đến hành động. |
| \`exceptionId\`, \`evidenceRef\` | Tham chiếu lỗi, ngoại lệ, bằng chứng phê duyệt và kết quả. |

Ví dụ bản ghi audit **không chứa bí mật**:

~~~json
{
  "eventType": "API_CREDENTIAL_REVOKE_VERIFIED",
  "eventId": "evt-20261130-0874",
  "traceId": "leaver-person-1042-20261130",
  "subjectId": "person-1042",
  "engagementId": "EMP-5812",
  "credentialId": "pat-7841",
  "credentialType": "PERSONAL_ACCESS_TOKEN",
  "issuer": "source-control-platform",
  "applicationId": "release-automation",
  "action": "REVOKE",
  "reasonCode": "EMPLOYMENT_ENDED",
  "providerResult": "REVOKED",
  "verificationMethod": "ISSUER_STATUS_AND_API_POLICY",
  "effectiveAt": "2026-11-30T17:00:00+07:00",
  "verifiedAt": "2026-11-30T10:02:19Z",
  "evidenceRef": "audit://IAM-CRED-502"
}
~~~

Các tên trường và trạng thái ở đây chỉ là **schema minh họa**. Trong triển khai thật phải ghi rõ kiểm chứng nào được thực hiện và kết luận bị giới hạn bởi hệ thống nào.

Log phải được bảo vệ khỏi chỉnh sửa/xóa trái phép, phân quyền theo nhu cầu, có thời hạn lưu hợp lệ và chỉ lưu **metadata hoặc fingerprint an toàn theo thiết kế**. Việc thu hồi credential không yêu cầu giữ giá trị credential gốc trong hồ sơ kiểm toán.

## 13. Tình huống thực hành: SSO bị khóa nhưng API vẫn chạy

**Bối cảnh:** Hải nghỉ việc lúc 17:00 ngày 30/11. Nhóm bảo mật thấy tài khoản IdP đã bị khóa nhưng từ 17:20 một API key vẫn gọi thành công API báo cáo. Sau khi kiểm tra, đây là key từng cấp cho Hải để tích hợp thử nghiệm và bị sao chép vào script ngoài quy trình.

| Mốc (giờ Việt Nam, giả định) | Bằng chứng | Ý nghĩa |
| --- | --- | --- |
| **16:00** | HRIS gửi sự kiện Leaver hiệu lực 17:00. | IAM có căn cứ lên lịch thu hồi. |
| **17:00** | IdP ghi tài khoản Hải bị disable. | Đường đăng nhập tập trung đã thay đổi trạng thái. |
| **17:01** | IGA gửi yêu cầu revoke PAT ở hệ thống nguồn mã. | Chỉ xác nhận thao tác với PAT được liệt kê. |
| **17:20** | API gateway ghi một yêu cầu hợp lệ bằng key của Hải trong công cụ báo cáo. | Có credential nằm ngoài phạm vi thu hồi ban đầu. |
| **17:25** | Owner API xác định key và ứng dụng sử dụng, disable key tại issuer. | Bắt đầu xử lý đường truy cập còn sót. |
| **17:27** | Kiểm tra provider và API gateway xác nhận key bị từ chối; rà soát log trước đó. | Có bằng chứng thu hồi đối với API đích đã kiểm tra. |

**Các bước xử lý và điều tra:**

1. Gắn API key với \`credentialId\`, issuer, principal/owner của Hải và các hệ thống có thể đang sử dụng; không đưa raw key lên ticket.
2. Kiểm tra các lệnh trong offboarding để biết vì sao key không có trong inventory: provider chưa tích hợp, key có owner khác, hay dữ liệu kiểm kê bị thiếu.
3. Thu hồi key tại provider và đánh giá các API/token/quyền liên quan; ưu tiên giới hạn truy cập đang bị khai thác.
4. Nếu script đó là công việc hợp lệ cần tiếp tục, chuyển sang workload identity/service principal được phê duyệt và cấp quyền tối thiểu.
5. Kiểm tra kết quả tại API đích, các credential phụ và những ứng dụng đã lưu bản sao key; phân tích log hoạt động trong khoảng có thể truy cập sai.
6. Bổ sung kiểm soát inventory, quy trình rà soát PAT/API key và cảnh báo key của chủ thể đã terminated còn được chấp nhận.

**Bài học:** thành công của bước khóa IdP **không chứng minh** đã thu hồi tất cả API credential; cần quản lý từng issuer, principal, ứng dụng và bằng chứng thực tế.

## 14. Chỉ số đánh giá chất lượng thu hồi API credential

| Chỉ số | Cách đo gợi ý | Rủi ro cần kiểm soát |
| --- | --- | --- |
| **Tỷ lệ credential có owner hợp lệ** | Credential hoạt động có principal/owner và mục đích được xác minh ÷ tổng credential trong phạm vi. | Key mồ côi, không người chịu trách nhiệm. |
| **Tỷ lệ Leaver được kiểm kê đầy đủ** | Leaver có danh sách credential từ toàn bộ provider bắt buộc ÷ tổng Leaver cần xử lý. | Bỏ sót PAT hoặc key nằm ngoài IdP. |
| **Tỷ lệ revoke đã xác minh** | Credential phải thu hồi đã có bằng chứng issuer/API đích phù hợp ÷ tổng credential cần thu hồi. | Lệnh gửi thành công nhưng quyền vẫn tồn tại. |
| **Độ trễ thu hồi** | Từ thời điểm JML có hiệu lực đến thời điểm xác minh credential không còn quyền theo khả năng hệ thống. | Cửa sổ truy cập tồn dư. |
| **Credential còn hoạt động sau Leaver** | Số key/token của principal đã terminated vẫn được provider chấp nhận. | Truy cập trái phép sau nghỉ việc. |
| **Tỷ lệ workload chuyển khỏi PAT cá nhân** | Job hợp lệ đã chuyển sang credential dịch vụ được duyệt ÷ job còn phụ thuộc PAT người dùng. | Dịch vụ gián đoạn hoặc buộc trì hoãn thu hồi. |
| **Số ngoại lệ quá hạn** | Tác vụ revoke/rotate chưa xác nhận, thiếu owner hoặc vượt thời hạn xử lý. | Tồn dư không được giải quyết. |
| **Tỷ lệ key có hạn dùng/quyền tối thiểu** | Credential đáp ứng chính sách TTL, scope và môi trường ÷ số credential kiểm tra. | Key dài hạn/quyền quá rộng. |
| **Số API chấp nhận credential đã bị thu hồi** | Sự kiện xác thực thành công sau thời điểm revoke có hiệu lực, được xác minh. | Cache, propagation, lỗ hổng thực thi chính sách. |

Ngưỡng vận hành phải dựa vào rủi ro hệ thống, yêu cầu doanh nghiệp và tính năng provider. Chỉ số cần công bố **phạm vi nhà cung cấp/API**, vì không thể kết luận “100% credential đã thu hồi” nếu chưa kiểm kê được các nền tảng nằm ngoài tích hợp.

## 15. Checklist triển khai và kiểm tra

1. Đã lập **inventory API key, PAT, OAuth token/grant, cloud access key, certificate và credential workload** theo từng nhà cung cấp chưa?
2. Mỗi credential có **principal, owner, ứng dụng, môi trường, scope, hạn dùng** và phương thức thu hồi rõ ràng không?
3. Có phân biệt key cá nhân phải revoke với key dịch vụ cần owner mới/rotate, đồng thời bảo vệ dịch vụ hợp lệ không?
4. Leaver từ HRIS/hệ thống hợp đồng có kích hoạt thu hồi đúng chủ thể, đúng thời điểm và xử lý cả tài khoản phụ ngoài SSO không?
5. Mover có rà soát PAT/key liên quan vai trò cũ và quyền đặc quyền, tránh tích lũy quyền không?
6. Có hiểu đúng giới hạn của OAuth refresh-token revocation, access token/JWT tự chứa và cache của resource server không?
7. SCIM \`active=false\` có được phân biệt với thao tác thu hồi key/token/grant riêng của provider không?
8. Có kiểm tra issuer, API gateway/resource server và trạng thái quyền thực tế trước khi đánh dấu \`REVOKED_VERIFIED\` không?
9. Khi API revoke timeout hoặc thất bại một phần, có retry an toàn, cảnh báo, owner và thời hạn xử lý không?
10. Có ngăn key bị sao chép vào log, ticket, email, source code và quản lý bản sao trong secrets manager/CI/CD không?
11. Có giữ **audit trail** đủ từ sự kiện JML tới quyết định, lệnh revoke, kết quả provider và bằng chứng xác minh mà không chứa raw secret không?
12. Có cơ chế phát hiện credential của người đã rời tổ chức vẫn được API chấp nhận và kiểm tra lại sau restore/backups không?

**Ghi nhớ:** Thu hồi API credential trong **Account deprovisioning** là xử lý **mọi đường xác thực API còn hiệu lực** gắn với người, dịch vụ hoặc quan hệ công việc đã mất thẩm quyền. Cần xác định đúng issuer, principal và owner; thực hiện revoke/rotate/điều chỉnh quyền theo loại credential; xác minh tác động ở resource server; xử lý phiên/token còn sống; và lưu bằng chứng kiểm toán an toàn. **Khóa SSO, disable tài khoản hoặc xóa secret khỏi cấu hình chỉ là một phần của chuỗi kiểm soát**, không tự chứng minh đã loại bỏ toàn bộ quyền truy cập tồn dư.
