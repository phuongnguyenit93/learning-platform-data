# Federated authentication trong PAM

## Mục tiêu bài học

**Federated authentication**, hay xác thực liên kết, cho phép một hệ thống dựa vào kết quả xác thực do một hệ thống định danh được tin cậy cung cấp. Trong Privileged Access Management (PAM), người quản trị có thể xác thực tại Identity Provider (IdP), sau đó truy cập PAM mà PAM không cần trực tiếp nhận mật khẩu đăng nhập của người đó trong luồng liên kết.

Điều này tập trung việc xác thực, MFA và một phần chính sách định danh. Tuy nhiên, PAM vẫn phải kiểm tra bằng chứng, ánh xạ đúng danh tính và quyết định quyền sử dụng tài sản đặc biệt.

Sau bài học, bạn có thể:

- Phân biệt xác thực liên kết, SSO, cấp phát tài khoản và cấp quyền đặc biệt.
- Giải thích vai trò của IdP, PAM và hệ thống đích.
- Nhận biết các điểm kiểm tra trong luồng SAML hoặc OpenID Connect.
- Thiết kế ánh xạ danh tính, nhóm và vai trò mà không mở rộng quyền ngoài ý định.
- Xử lý thay đổi khóa, ngừng hoạt động tài khoản, nhiều phiên và sự cố IdP.
- Lưu bằng chứng để truy từ danh tính liên kết đến phiên hoặc tài khoản đặc quyền tại đích.

Tên hệ thống, claim, mã nhóm và cấu trúc dữ liệu trong bài là minh họa. Các đoạn cấu hình mô tả ý định thiết kế, không phải cấu hình có thể nạp trực tiếp vào một sản phẩm.

## 1. Liên kết xác thực thay đổi điều gì?

Một mô hình đăng nhập trực tiếp có thể yêu cầu người dùng gửi mật khẩu đến PAM để PAM tự kiểm tra hoặc chuyển kiểm tra đến nguồn danh tính.

Trong mô hình liên kết:

1. PAM chuyển người dùng đến IdP hoặc sử dụng một luồng liên kết được cấu hình.
2. IdP xác thực người dùng và áp dụng các chính sách liên quan.
3. PAM nhận kết quả theo giao thức đã thiết lập.
4. PAM xác minh kết quả và ánh xạ về một danh tính nội bộ.
5. PAM tạo phiên của mình nếu các điều kiện được đáp ứng.
6. Quyền đặc biệt được xét riêng khi người dùng yêu cầu tài sản hoặc hành động.

PAM không nên coi một thông báo “đăng nhập thành công” do trình duyệt tự khai là bằng chứng. Kết quả cần được kiểm tra theo giao thức và cấu hình tin cậy.

### Ví dụ

Mai là kỹ sư vận hành. Mai đăng nhập IdP doanh nghiệp bằng phương thức MFA phù hợp, sau đó được quay lại cổng PAM.

Kết quả này giúp PAM xác định Mai là ai. Nó không tự cho Mai quyền đọc mọi bí mật trong vault hoặc mở mọi phiên sản xuất.

PAM có thể chỉ cho Mai thấy các tài sản thuộc phạm vi công việc. Để sử dụng vai trò quản trị trong một giờ, Mai vẫn phải có phê duyệt, grant JIT và các điều kiện phiên theo chính sách.

## 2. Phân biệt những khái niệm dễ nhầm

| Khái niệm | Ý nghĩa | Điều không tự được bảo đảm |
|---|---|---|
| Federation | Quan hệ tin cậy để chấp nhận kết quả xác thực từ một bên khác | Không tự cấp mọi quyền tại ứng dụng nhận |
| Single Sign-On (SSO) | Trải nghiệm dùng phiên đăng nhập để truy cập nhiều dịch vụ | Không nhất thiết tạo lần xác thực mới ở mỗi dịch vụ |
| Provisioning | Tạo, cập nhật hoặc vô hiệu hóa đối tượng tài khoản | Không chứng minh một người đang đăng nhập hợp lệ |
| Authorization | Quyết định người dùng được thực hiện hành động nào | Không chỉ dựa vào việc IdP đã xác thực thành công |
| JIT provisioning | Tạo tài khoản khi người dùng đăng nhập theo điều kiện đã định | Không đồng nghĩa quyền đặc biệt chỉ tồn tại có thời hạn |
| JIT privileged access | Cấp quyền đặc biệt trong cửa sổ hoặc thời lượng được kiểm soát | Không thay thế việc xác thực người sử dụng |

Một triển khai có thể dùng liên kết xác thực và một cơ chế đồng bộ tài khoản riêng. Hai luồng cần phối hợp nhưng không nên bị coi là cùng một việc.

Tương tự, PAM có thể dùng thư mục để lấy nhóm hoặc thông tin nhân sự. Việc kiểm tra mật khẩu trực tiếp qua một giao thức thư mục không tự trở thành liên kết xác thực theo mô hình assertion hoặc token.

## 3. Vai trò và ranh giới tin cậy

```text
                     Nguồn nhân sự / danh tính
                              |
                              v
Người quản trị <-----------> IdP
      |                       |
      | kết quả xác thực      | chính sách xác thực, MFA,
      | theo giao thức        | khóa ký, phiên IdP
      v                       |
PAM: Service Provider / Relying Party
  - kiểm tra bằng chứng
  - ánh xạ danh tính
  - tạo phiên PAM
  - xét quyền, JIT/JEA và phê duyệt
      |
      +----> Vault / cơ chế cấp credential hoặc quyền
      |
      v
Session broker / cơ chế truy cập
      |
      v
Tài sản đích: máy chủ, cơ sở dữ liệu, hạ tầng
```

Đây là sơ đồ chức năng. Các thành phần có thể được tích hợp hoặc triển khai riêng.

### 3.1. IdP chịu trách nhiệm gì?

IdP quản lý việc xác thực theo chính sách của mình, tạo bằng chứng và bảo vệ khóa hoặc cơ chế phát hành bằng chứng đó. IdP cũng có thể cung cấp thuộc tính như định danh, nhóm hoặc phương thức xác thực.

Vì PAM tin kết quả từ IdP, việc xâm nhập IdP hoặc quyền quản trị liên kết có thể ảnh hưởng trực tiếp đến truy cập đặc quyền. Cần bảo vệ tài khoản quản trị IdP, khóa ký, cấu hình ứng dụng và quy trình thay đổi.

### 3.2. PAM chịu trách nhiệm gì?

PAM xác định IdP nào được tin, bằng chứng nào hợp lệ và danh tính nào được chấp nhận. PAM cần kiểm tra các điều kiện như bên phát hành, bên nhận, thời hạn và liên hệ với giao dịch đăng nhập.

Sau đó, PAM quyết định quyền trong miền của mình. Việc IdP phát một claim nhóm không có nghĩa nhóm đó được phép tạo quản trị viên PAM nếu chưa có ánh xạ rõ ràng.

### 3.3. Hệ thống đích có tự nhận danh tính liên kết không?

Không nhất thiết. Một máy chủ cũ có thể chỉ hiểu tài khoản cục bộ hoặc một giao thức xác thực khác.

PAM có thể giữ credential trong vault, thiết lập phiên và ánh xạ danh tính cá nhân của Mai tới tài khoản kỹ thuật tại máy đích. Luồng đó cần kiểm soát credential và bằng chứng riêng.

Không chuyển ID token hoặc assertion đăng nhập cổng PAM sang máy đích rồi mặc định máy đích phải chấp nhận. Mỗi bằng chứng có bên nhận, mục đích và phạm vi được thiết kế riêng.

## 4. SAML và OpenID Connect ở mức cần thiết cho PAM

Hai cơ chế thường gặp là SAML và OpenID Connect (OIDC). Chúng có cách biểu diễn, trao đổi và kiểm tra bằng chứng khác nhau; không nên trộn lẫn quy tắc của chúng.

### 4.1. SAML

Trong một luồng SAML, PAM thường đóng vai trò Service Provider (SP), còn IdP cung cấp thông điệp hoặc assertion về người dùng.

Ở mức khái niệm:

1. PAM khởi tạo yêu cầu đăng nhập.
2. Trình duyệt được chuyển đến IdP.
3. IdP xác thực hoặc đánh giá phiên hiện có.
4. Kết quả SAML được chuyển về endpoint đã cấu hình của PAM.
5. PAM kiểm tra thông điệp bằng thư viện và cấu hình tin cậy.
6. PAM ánh xạ danh tính rồi xét việc tạo phiên.

Các kiểm tra liên quan có thể gồm bên phát hành, chữ ký trên thành phần cần được tin cậy, khóa tin cậy, audience, recipient, destination, thời hạn và tương quan với yêu cầu ban đầu.

PAM cần sử dụng chính nội dung đã được xác minh khi xử lý danh tính. Một chữ ký hợp lệ trên một phần thông điệp không cho phép ứng dụng tin mọi phần khác.

Với luồng dự kiến do SP khởi tạo, cần kiểm tra tương quan với yêu cầu đang chờ. Nếu hỗ trợ luồng do IdP khởi tạo, phải có cấu hình và đánh giá riêng, không vô tình chấp nhận thông điệp không gắn giao dịch chỉ vì chữ ký đúng.

Việc xử lý XML và chữ ký có nhiều chi tiết bảo mật. Nên dùng thư viện được duy trì và cấu hình phù hợp; không tự viết bộ kiểm tra chữ ký từ đầu.

### 4.2. OpenID Connect

OIDC là một lớp xác thực xây dựng trên OAuth 2.0. OAuth 2.0 phục vụ cấp quyền truy cập; một access token tùy ý không tự là bằng chứng đăng nhập OIDC hợp lệ.

PAM thường là Relying Party hoặc client. Một luồng authorization code có thể được mô tả như sau:

1. PAM tạo giao dịch đăng nhập và chuyển người dùng đến IdP.
2. IdP xác thực người dùng theo chính sách.
3. IdP trả authorization code về callback được đăng ký.
4. Thành phần phù hợp của PAM đổi code theo cơ chế đã cấu hình.
5. PAM xác minh ID token và các ràng buộc giao dịch.
6. PAM ánh xạ danh tính, xét điều kiện và tạo phiên.

PKCE giúp bảo vệ việc sử dụng authorization code. Việc quản lý bí mật client phụ thuộc loại client; không nhúng bí mật của client bí mật vào mã chạy ở trình duyệt.

PAM cần kiểm tra những thuộc tính giao thức liên quan như issuer, audience, thời hạn, chữ ký hoặc cơ chế bảo vệ phù hợp với cấu hình, cùng các ràng buộc yêu cầu ban đầu.

Các giá trị như `state` và `nonce` có vai trò khác nhau trong liên kết giao dịch và bảo vệ luồng. Chúng phải được tạo, lưu và kiểm tra theo thư viện cùng mô hình triển khai; không coi việc có một tham số trong URL là đã bảo vệ đầy đủ.

ID token dành cho client đăng nhập không phải vật thay thế chung cho access token của mọi API. API cần kiểm tra bằng chứng đúng mục đích và bên nhận của nó.

### 4.3. Những điểm cấu hình chung cần làm rõ

| Điểm cấu hình | Mục đích |
|---|---|
| IdP/issuer được tin cậy | Không nhận danh tính từ bên phát hành ngoài phạm vi |
| Bên nhận và ứng dụng | Không nhận bằng chứng dành cho ứng dụng khác |
| Endpoint callback hoặc nhận thông điệp | Đưa kết quả về đúng nơi và hạn chế chuyển hướng sai |
| Khóa và nguồn metadata | Chỉ dùng thông tin tin cậy để kiểm tra bằng chứng |
| Thuật toán được cho phép | Không chấp nhận tùy ý mọi cách ký hoặc bảo vệ |
| Thời hạn và tương quan giao dịch | Hạn chế bằng chứng cũ, dùng lại hoặc gắn sai phiên |
| Claim định danh và ánh xạ | Chuyển đúng danh tính bên ngoài thành người dùng PAM |

Không lấy khóa kiểm tra tùy ý từ một URL do chính thông điệp không tin cậy chỉ định. Nguồn khóa và metadata phải thuộc quan hệ tin cậy được cấu hình, có cách cập nhật được kiểm soát.

## 5. Ánh xạ danh tính: điểm dễ cấp nhầm quyền

### 5.1. Dùng định danh ổn định trong đúng miền tin cậy

Tên hiển thị và email có thể thay đổi hoặc được tái sử dụng. Không nên dùng chúng làm khóa duy nhất để tự động nối một danh tính mới với tài khoản PAM đặc quyền hiện có.

Với OIDC, cặp issuer và subject thường là cơ sở quan trọng để phân biệt danh tính trong ngữ cảnh ứng dụng. Subject không nên được coi là định danh toàn cục độc lập với issuer. Một số mô hình phát subject khác nhau cho các client, nên thay ứng dụng hoặc thay mô hình phát hành cần kế hoạch ánh xạ.

Với SAML, cần chọn định danh có tính ổn định và duy nhất phù hợp với miền IdP, đồng thời hiểu ngữ nghĩa của thuộc tính hoặc NameID được sử dụng. Không phải mọi NameID đều có vòng đời hoặc tính ổn định giống nhau.

Một ánh xạ khái niệm có thể gồm:

```yaml
identity_mapping:
  trusted_issuer: corp-idp
  external_subject: subject-7258
  local_principal_id: pam-person-041
  display_name: Mai Nguyen
  status: active
```

Đây là bản ghi minh họa. `trusted_issuer` trong hệ thống thực phải liên hệ với cấu hình bên phát hành cụ thể đã được kiểm tra, không chỉ một tên tùy ý do người dùng cung cấp.

### 5.2. Liên kết tài khoản phải có kiểm soát

Nếu một người đã có tài khoản PAM nội bộ rồi bắt đầu dùng federation, việc liên kết cần chứng minh đúng chủ thể và được thực hiện theo quy trình.

Tự động nối tài khoản chỉ vì email giống nhau có thể gây chiếm tài khoản nếu:

- Một IdP khác phát được cùng địa chỉ email.
- Email được tái sử dụng sau khi nhân sự cũ rời tổ chức.
- Thuộc tính chưa được xác minh hoặc không thuộc miền quản trị mong đợi.
- Nhiều tenant hoặc tổ chức có quy tắc đặt tên khác nhau.

Một migration cần lưu ánh xạ trước và sau, kiểm tra trùng lặp, xử lý tài khoản bị khóa và có cách phục hồi có kiểm soát. Không bỏ qua trạng thái khóa của tài khoản địa phương khi tạo liên kết mới.

### 5.3. Nhiều tenant và người dùng bên ngoài

Nếu chấp nhận nhiều IdP hoặc tenant, mỗi miền tin cậy phải được giới hạn rõ. Không chấp nhận một issuer bất kỳ chỉ vì token có chữ ký hợp lệ theo một khóa nào đó.

Nhân sự nhà cung cấp có thể được xác thực tại tổ chức của họ, nhưng quyền vào PAM của tổ chức sở hữu tài sản vẫn cần điều kiện tiếp nhận và người bảo trợ phù hợp.

Một IdP bên ngoài xác thực được một kỹ thuật viên không có nghĩa kỹ thuật viên đó được tự đăng ký thành quản trị viên PAM.

## 6. Ánh xạ claim sang quyền tối thiểu

### 6.1. Claim là đầu vào, không phải lệnh cấp quyền tùy ý

IdP có thể phát nhóm hoặc thuộc tính. PAM chỉ nên sử dụng các claim đã định nghĩa từ bên phát hành được phép, với quy tắc ánh xạ rõ ràng.

Ví dụ:

```yaml
federation_access_policy:
  issuer_reference: corp-idp-trust-01
  accepted_subjects: governed_workforce_identities
  unknown_identity: deny_until_onboarded
  default_privileged_role: none
  allowed_group_mapping:
    - external_group_id: group-platform-ops-stable-id
      pam_role: request-platform-maintenance
  privileged_activation:
    require_approval: true
    require_jit_grant: true
    enforce_asset_scope: true
```

Mẫu này mô tả ý định: thành viên nhóm có thể được phép yêu cầu một loại công việc, nhưng không tự nhận mọi quyền quản trị thường trực.

Nếu tổ chức cho phép JIT provisioning, tài khoản mới chỉ nên nhận mức truy cập ban đầu đã xác định. Tạo tài khoản khi đăng nhập không đồng nghĩa cấp sẵn quyền vault hoặc quyền quản trị hệ thống.

### 6.2. Dùng định danh nhóm và quy tắc đủ hẹp

Tên nhóm hiển thị có thể đổi hoặc trùng. Khi có thể, dùng định danh nhóm ổn định trong miền tin cậy và quản lý ánh xạ như cấu hình bảo mật.

Cần hiểu:

- Ai có thể thêm người vào nhóm nguồn.
- Nhóm lồng nhau được xử lý thế nào.
- Thuộc tính được cập nhật bao lâu một lần.
- Khi người dùng thuộc nhiều nhóm, quyền được kết hợp ra sao.
- Claim thiếu, bị cắt giảm hoặc được biểu diễn qua cơ chế tham chiếu thì xử lý thế nào.

Không coi claim nhóm bị thiếu là lý do gán một vai trò mặc định rộng. Nếu cần lấy thông tin bổ sung, phải dùng một nguồn được xác thực và có thẩm quyền phù hợp.

### 6.3. Bảo vệ chính sách ánh xạ

Người có quyền sửa ánh xạ nhóm sang vai trò có thể làm thay đổi phạm vi quyền của nhiều người mà không sửa từng tài khoản. Vì vậy thay đổi này cần kiểm soát đặc quyền, kiểm tra, phê duyệt phù hợp và lưu bằng chứng.

Nếu một nhóm nguồn có thể tạo quản trị viên PAM, quyền quản lý thành viên của nhóm đó trở thành một phần đường kiểm soát đặc quyền. Không chỉ bảo vệ giao diện PAM rồi bỏ qua nhóm tại IdP.

Vai trò quản trị PAM, vai trò sử dụng bí mật và vai trò xem bằng chứng cũng nên được phân tách theo mục tiêu tổ chức. Đăng nhập liên kết không yêu cầu gộp chúng thành một vai trò chung.

## 7. MFA, độ mới xác thực và chính sách tại PAM

Federation có thể giúp PAM sử dụng kết quả MFA ở IdP, nhưng cần biết kết quả đó thực sự có ý nghĩa gì.

Các câu hỏi cần làm rõ:

- Phương thức nào đã được dùng cho lần xác thực liên quan?
- Khi nào lần xác thực đó xảy ra?
- Bằng chứng có được nguồn tin cậy phát và kiểm tra đúng không?
- Mức bảo đảm có đáp ứng hành động PAM đang được yêu cầu không?
- IdP có chỉ tái sử dụng phiên SSO cũ mà không tạo bằng chứng mới không?

Token mới hoặc lần chuyển hướng mới không tự chứng minh người dùng vừa xác thực tương tác. Nếu thao tác như tiết lộ credential yêu cầu bằng chứng mới hơn hoặc mạnh hơn, PAM cần yêu cầu phù hợp và kiểm tra kết quả.

Tên claim hoặc cách biểu diễn mức bảo đảm phụ thuộc giao thức và hợp đồng tích hợp. Không suy ra “MFA mạnh” chỉ từ một chuỗi tùy ý chưa có ánh xạ ngữ nghĩa được thống nhất.

Xác thực mạnh cũng không thay thế điều kiện thiết bị, phê duyệt, JIT hoặc khả năng giám sát phiên.

## 8. Ba vòng đời phiên cần phối hợp

Sau đăng nhập liên kết, có thể tồn tại nhiều trạng thái riêng:

| Lớp | Ví dụ |
|---|---|
| Phiên IdP | Cookie hoặc trạng thái đăng nhập tại nhà cung cấp định danh |
| Phiên PAM | Phiên web hoặc token cho cổng PAM |
| Quyền và phiên tại đích | Grant JIT, kết nối SSH/RDP, phiên cơ sở dữ liệu hoặc token liên quan |

Đăng xuất khỏi một lớp không tự bảo đảm mọi lớp còn lại kết thúc.

### 8.1. Logout không đồng nghĩa thu hồi toàn bộ

Tính năng logout liên kết phụ thuộc giao thức, cấu hình và khả năng của các bên. Cần kiểm chứng thay vì giả định.

Một phiên PAM đã được tạo có thể tiếp tục theo vòng đời của nó dù phiên IdP đã kết thúc. Token đã phát cũng có thể còn hiệu lực cho đến khi hết hạn hoặc bị từ chối theo cơ chế thực tế.

Một kết nối quản trị được mở qua PAM có thể tồn tại độc lập với trang web đăng nhập. Cần biết ai có thể ngắt kết nối và trạng thái trên máy đích sau khi ngắt.

### 8.2. Vô hiệu hóa người dùng

Khi nhân sự nghỉ việc hoặc bị khóa khẩn cấp, cần có quy trình xử lý:

1. Chặn việc xác thực hoặc tạo phiên mới từ nguồn định danh liên quan.
2. Vô hiệu hóa hoặc hạn chế tài khoản PAM theo cơ chế vòng đời.
3. Kết thúc phiên hoặc token PAM khi hệ thống hỗ trợ và chính sách yêu cầu.
4. Thu hồi grant tạm, phiên quản trị và quyền tại đích liên quan.
5. Xử lý credential đã tiết lộ hoặc cấp theo loại bí mật và phụ thuộc.
6. Kiểm chứng kết quả thực tế và khoảng trễ còn lại.

Khóa tài khoản ở IdP là một bước quan trọng nhưng không tự xóa mọi quyền hoặc phiên đã tồn tại. Cần phối hợp sự kiện, đồng bộ, kiểm tra lại hoặc các cơ chế thu hồi phù hợp.

Tương tự, bỏ người khỏi nhóm không bảo đảm một phiên PAM đang dùng bản chụp quyền cũ sẽ cập nhật ngay. Cần xác định thời gian hiệu lực, cache và điểm đánh giá lại.

### 8.3. Danh tính máy và workload

Một tác vụ tự động không nên dùng cookie SSO của quản trị viên hoặc chia sẻ phương thức MFA để hoạt động lâu dài.

Danh tính workload cần cơ chế xác thực và cấp quyền riêng phù hợp với nền tảng, cùng credential có vòng đời được quản lý. Federation của người dùng ở cổng PAM không tự là thiết kế xác thực cho mọi dịch vụ phía sau.

## 9. Vận hành quan hệ tin cậy và xử lý sự cố

### 9.1. Vòng đời khóa và metadata

IdP có thể thay khóa ký hoặc thông tin endpoint. PAM cần có cách cập nhật nguồn tin cậy được xác thực và kiểm soát.

Một kế hoạch thay khóa nên xác định:

- Nguồn metadata hoặc tập khóa nào được phép sử dụng.
- Cách xác thực nguồn và bảo vệ cấu hình.
- Thời gian cache và cách phát hiện khóa mới.
- Khoảng chuyển tiếp với khóa cũ, nếu được thiết kế.
- Cách kiểm thử trước và giám sát lỗi.
- Cách dừng tin cậy một khóa bị nghi ngờ lộ.

Không giữ khóa cũ vô thời hạn chỉ để tránh gián đoạn. Ngược lại, xóa khóa cũ quá sớm có thể làm hỏng các luồng đang trong giai đoạn chuyển tiếp hợp lệ.

Nếu có nghi ngờ khóa ký bị lộ, thay khóa có thể chưa đủ. Cần đánh giá bằng chứng hoặc phiên đã được tạo từ quan hệ tin cậy đó, xem xét thu hồi và kiểm tra truy cập đặc quyền liên quan.

### 9.2. IdP không sẵn sàng

Nếu PAM không nhận được bằng chứng hợp lệ, không tự chuyển sang bỏ qua xác thực.

Tổ chức có thể cần một đường truy cập khẩn cấp độc lập cho sự cố IdP, nhưng đường đó phải được thiết kế, bảo vệ và kiểm thử trước. Cần xác định tài khoản, người có trách nhiệm, giới hạn tài sản, credential, thời hạn và bằng chứng.

Không để một lỗi SAML hoặc OIDC tự kích hoạt một tài khoản mặc định có quyền rộng. Đường khẩn cấp phải là một quyết định vận hành có kiểm soát, không phải kết quả vô tình của tích hợp lỗi.

### 9.3. Lỗi đồng hồ, chứng thực và cấu hình

Thời gian lệch có thể làm bằng chứng chưa có hiệu lực hoặc đã hết hạn. Cần đồng bộ thời gian và giới hạn sai lệch được phép rõ ràng.

Cấu hình sai issuer, audience, callback hoặc khóa có thể gây từ chối đăng nhập. Khi xử lý, đối chiếu nguồn cấu hình và log an toàn; không “sửa nhanh” bằng cách tắt chữ ký, bỏ kiểm tra audience hoặc chấp nhận mọi issuer.

Thông báo cho người dùng nên đủ để hỗ trợ nhưng không tiết lộ token hoặc chi tiết nhạy cảm. Log hỗ trợ cần được lọc để tránh giữ nguyên assertion hoặc token ở nơi không được bảo vệ.

### 9.4. Những rủi ro cần theo dõi

| Tình huống | Kiểm soát cần xem xét |
|---|---|
| Kết quả đăng nhập dành cho ứng dụng khác | Kiểm tra bên nhận và cấu hình ứng dụng |
| Bằng chứng bị dùng lại ngoài giao dịch | Tương quan, thời hạn và cơ chế chống dùng lại phù hợp giao thức |
| Issuer hoặc tenant ngoài phạm vi | Danh sách tin cậy cụ thể và điều kiện tiếp nhận |
| Claim bị ánh xạ thành vai trò quá rộng | Quy tắc tối thiểu, kiểm soát thay đổi và thử nghiệm |
| Cookie hoặc phiên sau đăng nhập bị đánh cắp | Bảo vệ phiên, thiết bị, độ mới xác thực và thu hồi |
| IdP hoặc quản trị ứng dụng liên kết bị xâm nhập | Bảo vệ quyền quản trị, khóa, cấu hình và giám sát |
| Danh tính cũ bị nối nhầm với tài khoản mới | Định danh ổn định và quy trình liên kết tài khoản |

MFA tại IdP giúp bảo vệ một phần đường xác thực nhưng không loại bỏ rủi ro mất phiên, cấu hình tin cậy sai hoặc quyền đã cấp quá rộng.

## 10. Tình huống thực hành: kỹ sư vận hành vào PAM

### 10.1. Bối cảnh

Mai thuộc nhóm vận hành nền tảng và cần đọc log trên `app-prod-02` theo ticket `INC-842`.

Thiết kế của tình huống:

- PAM chỉ tin một cấu hình IdP doanh nghiệp đã định nghĩa.
- Danh tính ngoài được ánh xạ về một principal PAM bằng định danh ổn định.
- Nhóm nguồn cho phép Mai yêu cầu vai trò bảo trì, không tự cấp quản trị.
- Công việc sản xuất cần phê duyệt theo chính sách.
- PAM mở phiên qua broker và giữ credential đích trong vault nếu cơ chế hỗ trợ.
- Quyền và phiên phải có thời hạn và bằng chứng.

### 10.2. Luồng hợp lệ

```text
Mai yêu cầu đăng nhập PAM
  -> PAM tạo giao dịch liên kết
  -> IdP xác thực và áp dụng chính sách
  -> PAM xác minh kết quả dành cho mình
  -> Ánh xạ về principal của Mai
  -> Tạo phiên PAM với phạm vi ban đầu
  -> Mai yêu cầu đọc log app-prod-02
  -> Đủ phê duyệt và điều kiện JIT
  -> PAM cấp quyền/mở phiên hạn chế
  -> Kết thúc công việc, thu hồi và đối soát
```

Ở mỗi bước, kết quả bước trước là điều kiện cần trong luồng này nhưng không thay thế tất cả điều kiện của bước sau.

### 10.3. Các biến thể cần xử lý

| Biến thể | Hành vi phù hợp |
|---|---|
| Người từ một IdP khác có cùng email với Mai | Không tự ánh xạ thành tài khoản đặc quyền của Mai |
| Kết quả có chữ ký hợp lệ nhưng audience khác | Từ chối theo kiểm tra giao thức |
| Mai có danh tính hợp lệ nhưng chưa được tiếp nhận vào PAM | Từ chối hoặc thực hiện onboarding theo chính sách, không gán quyền rộng |
| Claim nhóm bị thiếu | Không suy diễn thành quyền mặc định đặc biệt |
| Phiên SSO cũ không đáp ứng độ mới cho checkout | Yêu cầu bằng chứng phù hợp và kiểm tra kết quả |
| Mai bị khóa trong lúc phiên PAM còn mở | Kích hoạt quy trình thu hồi các lớp liên quan |
| IdP thay khóa theo kế hoạch | PAM cập nhật nguồn tin cậy và kiểm chứng chuyển tiếp |
| IdP không hoạt động | Áp dụng hành vi lỗi hoặc đường khẩn cấp được thiết kế |
| Người dùng logout khỏi cổng PAM | Kiểm tra riêng trạng thái IdP, token và phiên quản trị theo chính sách |

### 10.4. Một lỗi ánh xạ có tác động lớn

Giả sử cấu hình dùng quy tắc: bất kỳ ai có claim tên nhóm chứa chuỗi `admin` đều nhận vai trò quản trị PAM.

Một nhóm không liên quan như `training-admin-assistants` có thể vô tình khớp. Nếu nhà cung cấp bên ngoài cũng phát nhóm có tên tương tự, phạm vi ảnh hưởng có thể rộng hơn.

Cần thay bằng ánh xạ định danh nhóm cụ thể trong đúng miền tin cậy, xác định ai quản lý nhóm, không cấp vai trò vượt mục đích và kiểm thử trường hợp không được phép.

Sau khi sửa cấu hình, phải rà soát những tài khoản, grant hoặc phiên đã được tạo bởi quy tắc cũ. Chỉ sửa cấu hình không tự thu hồi mọi quyền đã tồn tại.

## 11. Kiểm chứng trước khi đưa vào vận hành

Thử nghiệm trên môi trường, danh tính và tài sản được phép. Ngoài luồng đăng nhập thành công, cần xác nhận các trường hợp phải bị chặn.

| Phép thử | Kết quả mong đợi |
|---|---|
| Kết quả từ issuer hoặc tenant ngoài phạm vi | Không tạo phiên PAM |
| Bằng chứng cho bên nhận khác | Bị từ chối |
| Chữ ký hoặc bảo vệ giao thức không hợp lệ | Bị từ chối, không tiếp tục ánh xạ tin cậy |
| Bằng chứng hết hạn hoặc chưa có hiệu lực | Xử lý theo kiểm tra thời gian đã cấu hình |
| Kết quả không khớp giao dịch đang chờ | Không tạo hoặc gắn nhầm phiên |
| Callback hoặc đường chuyển hướng ngoài cấu hình | Không chuyển kết quả đến đích tùy ý |
| Bằng chứng đăng nhập cũ được dùng lại trái thiết kế | Không được tái sử dụng ngoài điều kiện cho phép |
| Email trùng từ danh tính khác | Không chiếm tài khoản PAM hiện có |
| Nhóm thiếu, trùng tên hoặc ngoài danh sách | Không sinh quyền đặc biệt mặc định |
| Đổi thành viên nhóm nguồn | Quyền cập nhật hoặc thu hồi trong giới hạn đã xác định |
| Tài khoản nguồn bị khóa | Chặn mới và kiểm chứng các lớp phiên/grant theo quy trình |
| Thay khóa theo kế hoạch | Chuyển tiếp đúng mà vẫn giữ kiểm tra tin cậy |
| Khóa không rõ nguồn xuất hiện trong thông điệp | Không tự tải hoặc tin khóa ngoài cấu hình |
| Lỗi IdP | Không tự bỏ qua xác thực |
| Logout một lớp | Quan sát và xác nhận hành vi của các lớp còn lại |
| Gọi trực tiếp API PAM sau thay đổi quyền | API vẫn kiểm tra quyền và trạng thái phù hợp |

Tùy giao thức, một phép thử cần được điều chỉnh theo đúng luồng được hỗ trợ. Không giả định mọi sản phẩm có cùng cơ chế logout, chống dùng lại hoặc cập nhật nhóm.

Nên thử thêm việc khôi phục cấu hình và đường khẩn cấp. Một quy trình chỉ tồn tại trên tài liệu có thể không hoạt động khi IdP hoặc khóa tin cậy thực sự gặp sự cố.

## 12. Bằng chứng vận hành và kiểm toán

Để truy vết một lần truy cập đặc quyền qua federation, cần nối được:

```text
Issuer + định danh ngoài
    -> Principal PAM
    -> Sự kiện đăng nhập và bằng chứng xác thực liên quan
    -> Quyết định quyền và phê duyệt
    -> Grant JIT hoặc yêu cầu vault
    -> Phiên PAM và tài khoản đích
    -> Hoạt động, kết thúc và thu hồi
```

Các thông tin hữu ích gồm:

- Cấu hình quan hệ tin cậy và phiên bản áp dụng.
- Định danh người dùng ổn định, mã phiên và mã tương quan.
- Thời điểm, kết quả kiểm tra và loại lỗi an toàn để ghi log.
- Ánh xạ claim/nhóm sang vai trò đã áp dụng.
- Kết quả phê duyệt, grant và tài sản được truy cập.
- Thay đổi cấu hình issuer, endpoint, khóa hoặc mapping.
- Sự kiện vòng đời như khóa tài khoản và thu hồi.
- Kết quả thực thi tại đích khi cần xác nhận tác động.

Không ghi mật khẩu, private key, cookie phiên, authorization code hoặc token nguyên vẹn vào log thông thường. Assertion cũng có thể chứa dữ liệu cá nhân hoặc đủ thông tin nhạy cảm để cần bảo vệ.

Có thể dùng tham chiếu hoặc dữ liệu đã giảm nhạy cảm để tương quan. Bộ log phải có phân quyền, thời hạn lưu và kiểm soát sửa/xóa phù hợp.

Đồng bộ thời gian và ghi rõ múi giờ giúp đối chiếu IdP, PAM, vault và máy đích. Khi có khoảng trễ đồng bộ hoặc khoảng trống log, cần ghi nhận giới hạn thay vì kết luận thu hồi tức thì mà không có bằng chứng.

## 13. Những sai lầm thường gặp

**Coi federation là cấp quyền tự động.** Nó giúp xác định người dùng từ một miền tin cậy; quyền PAM vẫn cần chính sách riêng.

**Coi access token bất kỳ là bằng chứng đăng nhập.** Token và assertion cần đúng giao thức, mục đích, bên nhận và kiểm tra tương ứng.

**Dùng email làm khóa nối tài khoản duy nhất.** Email có thể đổi, tái sử dụng hoặc trùng giữa miền tin cậy. Cần định danh và quy trình liên kết đủ chặt.

**Tin một claim nhóm mà không biết ai quản lý nhóm.** Quyền quản lý nhóm có thể trở thành đường cấp đặc quyền gián tiếp.

**Đồng nhất JIT provisioning với JIT quyền.** Tài khoản tạo lúc đăng nhập vẫn có thể nhận quyền thường trực nếu thiết kế sai.

**Tắt kiểm tra chữ ký hoặc audience để xử lý lỗi.** Cách này làm suy yếu chính quan hệ tin cậy; cần sửa cấu hình hoặc áp dụng đường khẩn cấp đúng quy trình.

**Cho rằng logout IdP kết thúc mọi phiên đích.** Phải kiểm chứng vòng đời từng lớp và có cơ chế thu hồi thực tế.

**Giữ phiên người dùng để chạy tác vụ tự động lâu dài.** Workload cần danh tính và vòng đời credential riêng.

## 14. Tự kiểm tra

1. PAM tin điều gì khi chấp nhận kết quả từ IdP?
2. Vì sao một người đăng nhập liên kết thành công chưa được phép đọc mọi bí mật trong vault?
3. SSO khác một lần xác thực mới như thế nào?
4. Vì sao issuer và định danh ổn định quan trọng hơn tên hiển thị khi ánh xạ tài khoản?
5. JIT provisioning khác JIT privileged access như thế nào?
6. Nếu IdP khóa tài khoản, cần xem thêm những trạng thái nào?
7. Khi IdP thay khóa, vì sao không nên chấp nhận mọi khóa để tránh lỗi?
8. Những bằng chứng nào giúp truy từ người dùng liên kết đến tài khoản quản trị tại đích?

### Gợi ý trả lời

1. PAM chấp nhận một kết quả xác thực trong phạm vi quan hệ tin cậy, sau khi kiểm tra giao thức, cấu hình và ngữ cảnh.
2. Xác thực xác định danh tính; quyền vault còn phụ thuộc vai trò, tài sản, phê duyệt, JIT và điều kiện sử dụng.
3. SSO có thể tái sử dụng phiên IdP cũ; chỉ khi có bằng chứng đáp ứng yêu cầu mới có thể kết luận đã xác thực mới.
4. Tên và email có thể thay đổi hoặc trùng; định danh phải được hiểu trong đúng miền tin cậy và vòng đời.
5. Một cơ chế tạo tài khoản theo lần đăng nhập; cơ chế còn lại giới hạn thời gian quyền đặc biệt tồn tại.
6. Phiên/token PAM, grant, phiên đích, quyền tạm và credential đã cấp hoặc tiết lộ.
7. Khóa là một phần căn cứ tin cậy. Chấp nhận tùy ý có thể cho phép bằng chứng do bên ngoài tạo.
8. Ánh xạ issuer-subject về principal PAM, mã phiên, yêu cầu/phê duyệt, grant, tài sản và tài khoản đích cùng log thực thi.

## Kết luận

Federated authentication giúp PAM sử dụng một nguồn xác thực được quản trị tập trung, đồng thời tạo một ranh giới tin cậy cần được bảo vệ và kiểm chứng. Cấu hình đúng giao thức, ánh xạ đúng danh tính và giới hạn claim là nền tảng của ranh giới đó.

Quyền đặc biệt vẫn cần least privilege, JIT/JEA, vault, kiểm soát phiên và thu hồi có bằng chứng. Khi quản lý đầy đủ cả phiên IdP, phiên PAM và trạng thái tại đích, tổ chức có thể truy vết từ người đã xác thực đến quyền thực sự được dùng và thời điểm quyền đó chấm dứt.
