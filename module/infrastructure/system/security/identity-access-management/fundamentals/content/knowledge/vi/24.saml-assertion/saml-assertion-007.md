# NameID

Trong SAML, Identity Provider (IdP) xác thực người dùng rồi gửi assertion cho Service Provider (SP). SP còn phải giải quyết một việc: chủ thể được mô tả trong assertion tương ứng với tài khoản nào trong ứng dụng? `NameID` là một cách biểu diễn định danh chủ thể để phục vụ việc đó.

Chọn sai định danh có thể khiến người dùng mất liên kết với dữ liệu sau khi đổi email, sinh tài khoản trùng hoặc nhận nhầm tài khoản của người khác. Bài học tập trung vào ý nghĩa của NameID và cách thiết kế liên kết danh tính trong một hệ thống IAM.

## 1. Phân biệt định danh, thông tin hồ sơ và quyền

Giả sử ứng dụng quản lý đào tạo có tài khoản nội bộ `usr_2048`. Nhân viên Lan đăng nhập qua IdP của công ty. Ứng dụng cần liên kết danh tính bên ngoài với `usr_2048`; tên hiển thị và email được dùng cho giao diện, thông báo.

Ba câu hỏi cần tách riêng:

| Câu hỏi | Dữ liệu cần xem xét |
|---|---|
| Đây là chủ thể nào trong quan hệ liên kết? | NameID và ngữ cảnh kết nối IdP–SP |
| Hồ sơ hiện tại của chủ thể là gì? | Email, họ tên, phòng ban và các thuộc tính được phát hành |
| Chủ thể được làm gì trong ứng dụng? | Chính sách phân quyền, vai trò, thuộc tính và trạng thái tài khoản |

Không suy luận rằng chuỗi NameID chứa từ `admin` thì người dùng có quyền quản trị. Trong thiết kế ứng dụng, bước tìm tài khoản và bước quyết định quyền phải có trách nhiệm riêng.

## 2. Đọc một NameID

Ví dụ dưới đây chỉ minh họa một phần `Subject`, không phải assertion đầy đủ hay thông điệp có thể dùng để đăng nhập:

```xml
<saml:Subject xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      NameQualifier="https://idp.example.org/metadata"
      SPNameQualifier="https://training.example.org/saml/metadata"
  >p_N8vQ6xR2mL7cT9sK4aH5</saml:NameID>
</saml:Subject>
```

Nội dung phần tử là giá trị định danh; `Format` mô tả cách diễn giải. `NameQualifier` bổ sung miền định danh, còn `SPNameQualifier` bổ sung phạm vi SP hoặc nhóm SP. Ý nghĩa cụ thể phụ thuộc format. `SPProvidedID`, nếu được sử dụng, là một định danh thay thế do SP cung cấp. Xem định nghĩa `NameIDType` tại [SAML Core, mục 2.2.2–2.2.3](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf).

Các URL trong ví dụ là định danh cấu hình. Khi xử lý NameID, ứng dụng không cần tự truy cập những URL do thông điệp mang đến để quyết định có tin người dùng hay không.

## 3. Các format thường gặp

| Format | Ý nghĩa chính | Điểm cần chú ý khi thiết kế |
|---|---|---|
| `persistent` | Định danh giả danh, ổn định trong quan hệ IdP–SP hoặc nhóm SP | Phù hợp liên kết lâu dài khi được cấp phát đúng ngữ nghĩa |
| `transient` | Định danh tạm thời, được xử lý như giá trị opaque | Không dùng làm khóa tài khoản lâu dài |
| `emailAddress` | Giá trị có dạng địa chỉ email | Cần tính đến đổi địa chỉ và tái cấp phát hộp thư |
| `unspecified` | Cách diễn giải do triển khai thỏa thuận | Phải có hợp đồng ánh xạ rõ ràng |

URI đầy đủ cần dùng đúng:

```text
persistent   = urn:oasis:names:tc:SAML:2.0:nameid-format:persistent
transient    = urn:oasis:names:tc:SAML:2.0:nameid-format:transient
emailAddress = urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress
unspecified  = urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified
```

Phần `1.1` trong hai URI cuối vẫn xuất hiện trong định nghĩa của SAML 2.0. Các format được mô tả tại [SAML Core, mục 8.3](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf).

### Persistent và tính pairwise

Một persistent NameID đúng ngữ nghĩa có tính opaque và pairwise: SP thường nhận một giá trị riêng cho người dùng đó, thay vì mọi SP cùng nhận một mã công khai. Tài liệu [Shibboleth về persistent NameID](https://shibboleth.atlassian.net/wiki/spaces/IDP5/pages/3199507892/PersistentNameIDGenerationConfiguration) giải thích các đặc tính này và những chiến lược sinh định danh.

Ví dụ minh họa quan hệ, không phải thuật toán sinh NameID:

| Người dùng tại IdP | SP nhận assertion | Persistent NameID |
|---|---|---|
| Lan | Ứng dụng đào tạo | `p_N8vQ6xR2mL7cT9sK4aH5` |
| Lan | Ứng dụng đặt lịch | `p_B3dF7wJ9rA2uE6zC8kM4` |

Ứng dụng đào tạo không nên giả định có thể lấy NameID của mình để tìm Lan bên ứng dụng đặt lịch. Tính pairwise giảm khả năng đối chiếu danh tính chỉ dựa vào định danh được chia sẻ; nó không tự loại bỏ thông tin nhận dạng nằm trong những thuộc tính khác.

Trong vận hành, cần bảo vệ dữ liệu ánh xạ hoặc đầu vào sinh định danh. Nếu thay cấu hình làm giá trị đổi hàng loạt, SP có thể nhìn thấy nhiều danh tính bên ngoài chưa từng được liên kết.

## 4. NameIDPolicy là yêu cầu về định danh

SP có thể nêu yêu cầu trong `AuthnRequest`:

```xml
<samlp:NameIDPolicy
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
    AllowCreate="true" />
```

`Format` đề nghị dạng NameID mong muốn. `AllowCreate` liên quan đến việc IdP được phép tạo định danh mới để biểu diễn chủ thể; không phải chỉ thị cấp tài khoản hay quyền tại SP. Khả năng đáp ứng còn phụ thuộc IdP và cấu hình kết nối. Ví dụ, [tài liệu giao thức SAML của Microsoft Entra ID](https://learn.microsoft.com/en-us/entra/identity-platform/single-sign-on-saml-protocol) mô tả riêng các giá trị NameIDPolicy mà sản phẩm hỗ trợ.

Phân biệt hai tình huống:

- IdP tạo một định danh liên kết mới cho Lan.
- SP tạo tài khoản ứng dụng mới cho Lan theo chính sách Just-in-Time provisioning.

Đây là hai quyết định khác nhau. SP có thể yêu cầu tài khoản được cấp trước, dù IdP đã trả về NameID hợp lệ. Khi SP cần persistent nhưng nhận transient, cần xử lý lỗi cấu hình hoặc chính sách; không âm thầm dùng transient như định danh ổn định.

## 5. Thiết kế ánh xạ vào tài khoản nội bộ

Phần này là một phương án thiết kế minh họa, không phải schema bắt buộc của SAML.

Nên tách khóa nội bộ của ứng dụng khỏi định danh bên ngoài. Một bản ghi liên kết có thể chứa:

```json
{
  "connectionId": "corp-a-saml",
  "tenantId": "tenant-a",
  "issuer": "https://idp.example.org/metadata",
  "nameIdFormat": "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent",
  "nameQualifier": "https://idp.example.org/metadata",
  "spNameQualifier": "https://training.example.org/saml/metadata",
  "nameIdValue": "p_N8vQ6xR2mL7cT9sK4aH5",
  "localUserId": "usr_2048"
}
```

`connectionId` đại diện cho kết nối đã được ứng dụng cấu hình và tin cậy. Không cho phép dữ liệu chưa xác minh trong assertion tự chọn tenant hay kết nối có đặc quyền hơn.

Một quy trình ánh xạ đề xuất:

1. Thư viện SAML xác minh thông điệp theo cấu hình kết nối và profile được hỗ trợ.
2. Ứng dụng kiểm tra NameID đáp ứng hợp đồng định danh của kết nối đó.
3. Hệ thống tra liên kết trong đúng tenant và namespace đã cấu hình.
4. Nếu có đúng một liên kết, lấy `localUserId` và kiểm tra trạng thái tài khoản.
5. Nếu chưa có, áp dụng chính sách cấp phát hoặc chuyển sang quy trình liên kết được kiểm soát.
6. Nếu dữ liệu ánh xạ mâu thuẫn, từ chối và ghi nhận sự kiện để xử lý.

Đặt ràng buộc duy nhất cho khóa liên kết theo thiết kế để tránh hai yêu cầu đăng nhập đồng thời sinh hai tài khoản. Với qualifier bị lược bỏ, sử dụng quy tắc suy ra từ ngữ cảnh đã được thống nhất cho format và kết nối; đừng tự coi mọi chuỗi rỗng là cùng một miền định danh.

### Không tra tài khoản chỉ bằng chuỗi NameID

Giả sử hai đối tác có IdP riêng đều phát hành NameID `user-17`. Nếu ứng dụng chỉ truy vấn `WHERE external_id = 'user-17'`, người dùng của đối tác B có thể bị ghép vào tài khoản đối tác A.

Vì vậy, khóa tra cứu cần bao gồm phạm vi kết nối và tenant phù hợp. Với dữ liệu opaque, thiết kế mặc định nên bảo toàn giá trị, thay vì tự lowercase, cắt tiền tố hoặc biến đổi thành email. Mọi phép chuẩn hóa cần có hợp đồng và đánh giá nguy cơ làm hai định danh khác nhau trở thành một.

## 6. Chỉ sử dụng NameID từ thông điệp đã được xác minh

Một XML chứa NameID trông hợp lệ chưa đủ để đăng nhập. Cần kiểm tra chữ ký với trust đã cấu hình, phạm vi audience, thời hạn, recipient và tương quan request khi luồng yêu cầu; đồng thời có biện pháp chống replay. NameID mà ứng dụng tiêu thụ phải thuộc đúng nội dung được chữ ký hợp lệ bảo vệ, tránh lỗi XML Signature Wrapping. Những nguyên tắc này được trình bày tại [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html).

Với ví dụ đào tạo ở trên, ứng dụng chỉ tìm `usr_2048` sau khi lớp xác minh trả về chủ thể đáng tin cậy. Không tự quét XML bằng cách lấy phần tử `NameID` đầu tiên rồi dùng nó làm người dùng hiện hành.

Việc xác định danh tính cũng không thay thế quản lý trạng thái. Nếu `usr_2048` đã bị khóa, ứng dụng cần áp dụng chính sách khóa dù dữ liệu định danh vẫn ánh xạ thành công.

## 7. Email không phải lúc nào cũng là khóa phù hợp

Trong nhiều sản phẩm, nguồn dữ liệu phát hành NameID có thể được cấu hình từ thuộc tính hồ sơ. Cần phân biệt nguồn dữ liệu với format được khai báo. [Microsoft Entra ID: tùy chỉnh SAML claims](https://learn.microsoft.com/en-us/entra/identity-platform/saml-claims-customization) mô tả riêng việc chọn format, thuộc tính nguồn và hành vi khi nguồn hoặc phép biến đổi không có giá trị hợp lệ.

Một tình huống thiết kế cần tránh:

1. Lan có email `lan@example.org`, được ứng dụng dùng làm khóa liên kết.
2. Lan nghỉ việc; hộp thư sau đó được cấp cho Mai.
3. Mai đăng nhập với cùng địa chỉ.
4. Ứng dụng ghép Mai vào tài khoản cũ của Lan và mở dữ liệu lịch sử.

Đây là lý do cần thỏa thuận rõ tính ổn định, tính duy nhất và chính sách tái sử dụng của thuộc tính định danh. Khai báo format email không giải quyết được vòng đời tài khoản của tổ chức.

Nếu một tích hợp bắt buộc dùng email, hãy đưa rủi ro đổi và tái cấp phát email vào quy trình vận hành. Không tự động gộp hai tài khoản hiện hữu chỉ vì địa chỉ email của chúng giống nhau.

## 8. Xử lý thay đổi trong vòng đời danh tính

Các quyết định sau là khuyến nghị thiết kế cho hệ thống minh họa:

| Sự kiện | Cách xử lý đề xuất |
|---|---|
| Lan đổi email, persistent NameID giữ nguyên | Cập nhật hồ sơ theo nguồn được phép; giữ liên kết với `usr_2048` |
| Ứng dụng nhận NameID mới sau thay đổi cấu hình IdP | Điều tra thay đổi; dùng kế hoạch migration thay vì tự tạo trùng tài khoản |
| Tài khoản IdP bị xóa rồi tạo lại | Xem đây có thể là chủ thể mới; yêu cầu bằng chứng trước khi khôi phục liên kết cũ |
| Lan chuyển bộ phận | Đánh giá lại quyền theo chính sách; không dùng việc đổi NameID để thay thế quản lý quyền |
| Doanh nghiệp chuyển sang IdP khác | Lập ánh xạ được kiểm chứng giữa liên kết cũ, liên kết mới và tài khoản nội bộ |
| Lan rời tổ chức | Thực hiện thu hồi quyền và phiên theo quy trình offboarding của ứng dụng |

Một migration nên có kiểm kê liên kết, nguồn chứng minh chủ thể, khả năng quay lại, nhật ký người phê duyệt và kiểm tra tài khoản trùng. Với tài khoản quản trị, quy trình liên kết mới cần kiểm soát tương xứng với đặc quyền đang giữ.

NameID cũng cần được đối xử như dữ liệu danh tính. Trong log vận hành thông thường, nên ưu tiên mã kết nối, mã yêu cầu và mã tài khoản nội bộ phù hợp; hạn chế ghi assertion hoặc NameID nguyên văn, giới hạn quyền xem và thời gian lưu.

## 9. Khoanh vùng lỗi tích hợp

Ví dụ, người dùng đăng nhập thành công tại IdP nhưng ứng dụng báo không tìm thấy tài khoản. Cách điều tra đề xuất là đối chiếu theo từng lớp:

| Hiện tượng | Câu hỏi cần kiểm tra |
|---|---|
| Chỉ một người không có NameID như dự kiến | Thuộc tính nguồn có thiếu hoặc có phép biến đổi thất bại không? |
| Mọi người bắt đầu có NameID mới | Có thay cấu hình generator, dữ liệu nguồn hoặc định danh SP không? |
| Cứ đăng nhập lại là tạo tài khoản khác | Ứng dụng có đang dùng transient làm khóa lâu dài không? |
| Một số người bị trùng tài khoản sau đổi email | Khóa liên kết có phụ thuộc email và thiếu quy trình đổi địa chỉ không? |
| Người của tenant B nhìn thấy tài khoản tenant A | Truy vấn ánh xạ có bỏ qua tenant hoặc kết nối IdP không? |

Chỉ dùng thông điệp chẩn đoán được thu thập trong phạm vi cho phép, che dữ liệu cá nhân khi chia sẻ. Mục tiêu là tìm khác biệt giữa hợp đồng định danh và giá trị thực nhận, sau đó sửa đúng lớp cấu hình hoặc ánh xạ.

## 10. Tự kiểm tra qua tình huống

**Tình huống 1:** Lan đổi email nhưng NameID và liên kết bên ngoài không đổi. Có cần tạo tài khoản ứng dụng mới không?

Không, trong thiết kế minh họa, liên kết vẫn trỏ tới `usr_2048`. Chỉ cập nhật thuộc tính hồ sơ theo chính sách; quyền được đánh giá độc lập.

**Tình huống 2:** Một ứng dụng dùng transient NameID làm khóa lưu kết quả học tập. Cần sửa điểm nào?

Cần có hợp đồng định danh ổn định cho tài khoản và kế hoạch chuyển các liên kết hiện có. Không giải quyết bằng cách kéo dài thời gian sống của phiên rồi coi transient là persistent.

**Tình huống 3:** IdP mới gửi email giống tài khoản quản trị cũ. Có nên tự gộp không?

Không. Cần xác minh việc liên kết qua quy trình được kiểm soát, chứng minh chủ thể và ghi nhận thay đổi. Sự trùng email không đủ để trao tài khoản quản trị.

Khi triển khai SSO, hãy coi NameID là một phần của hợp đồng liên kết danh tính: xác định rõ nguồn cấp, format, phạm vi, độ ổn định và cách xử lý thay đổi. Chất lượng hợp đồng đó quyết định ứng dụng có nhận diện đúng người qua nhiều lần đăng nhập và nhiều thay đổi tổ chức hay không.
