# Service Provider

## 1. Service Provider trong federation là ai?

Trong quản lý danh tính liên kết, **Service Provider (SP)** là bên cung cấp ứng dụng hoặc dịch vụ mà người dùng muốn truy cập, đồng thời dựa vào thông tin xác thực do một **Identity Provider (IdP)** đáng tin cậy phát hành.

Ví dụ, cổng quản lý chi phí của công ty là SP. Nhân viên đăng nhập tại IdP của công ty, sau đó quay lại cổng chi phí. Cổng không cần trực tiếp kiểm tra mật khẩu của nhân viên trong giao dịch federation đó; nó kiểm tra thông điệp từ IdP, xác định tài khoản tương ứng và áp dụng chính sách truy cập của mình.

Trong mô hình SAML Web SSO, IdP và SP là hai vai trò giao thức; SP tiêu thụ assertion để hỗ trợ truy cập tài nguyên theo chính sách của mình. [OASIS — SAML Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html).

Điểm cần nhớ là SP **ủy thác một phần việc xác thực, không từ bỏ trách nhiệm bảo vệ ứng dụng**. SP vẫn phải xác minh đầu vào, quản lý phiên, liên kết đúng danh tính và kiểm tra quyền trên từng hành động nghiệp vụ.

“Service Provider” trong bài này là một vai trò trong federation. Nó không nhất thiết là nhà cung cấp Internet, nhà cung cấp cloud hoặc một công ty bên ngoài. Một ứng dụng nội bộ cũng có thể là SP.

## 2. Phân chia trách nhiệm giữa IdP, SP và trình duyệt

| Thành phần | Trách nhiệm chính trong ví dụ đăng nhập liên kết |
|---|---|
| Người dùng | Khởi tạo truy cập và hoàn tất các bước xác thực cần thiết |
| Trình duyệt | Chuyển hướng, mang thông điệp và cookie theo giao thức |
| IdP | Xác thực người dùng theo chính sách của IdP và phát hành kết quả cho bên nhận phù hợp |
| SP | Kiểm tra kết quả, liên kết với danh tính tại ứng dụng, tạo phiên và kiểm soát truy cập |
| Nguồn quản trị quyền | Xác định tài khoản, vai trò hoặc quyền được phép tồn tại theo quy trình quản trị |

Trình duyệt là phương tiện truyền thông điệp, không phải nguồn thẩm quyền. Việc một payload xuất hiện ở endpoint đăng nhập không chứng minh payload đó hợp lệ.

IdP thường biết người dùng đã được xác thực như thế nào. SP hiểu các tài nguyên và thao tác nghiệp vụ của ứng dụng. Chẳng hạn, IdP có thể xác nhận Lan là nhân viên công ty; ứng dụng chi phí mới là nơi cần quyết định Lan được tạo đề nghị, xem báo cáo hay duyệt hoàn tiền.

### SP và Relying Party

Trong OpenID Connect, phía ứng dụng sử dụng kết quả xác thực được gọi là **Relying Party (RP)**, cũng là một OpenID Connect Client. ID Token chứa thông tin về kết quả xác thực; RP phải xử lý và kiểm tra token theo luồng sử dụng. [OpenID Connect Core — Authentication](https://openid.net/specs/openid-connect-core-1_0.html#Authentication).

Có thể dùng “bên ứng dụng dựa vào IdP” để hiểu mối liên hệ về vai trò, nhưng không nên coi cấu hình SAML SP và OIDC RP là cùng một định dạng hoặc cùng một giao thức.

| Ngữ cảnh | Phía phát hành kết quả xác thực | Phía ứng dụng sử dụng kết quả |
|---|---|---|
| SAML Web SSO | Identity Provider | Service Provider |
| OpenID Connect | OpenID Provider | Relying Party/Client |

Một API nhận access token để bảo vệ tài nguyên còn có vai trò resource server. ID Token dùng cho kết quả đăng nhập của RP không nên được mặc nhiên dùng làm access token cho API. Ứng dụng có thể đảm nhiệm nhiều vai trò, nhưng từng loại thông điệp phải được xử lý đúng mục đích.

## 3. Quan hệ tin cậy của SP phải được thiết lập trước

Federation không phải là “ai gửi được thông tin người dùng thì SP tin người đó”. SP cần có cấu hình xác định IdP nào được tin và trong phạm vi nào.

Các nội dung cần thống nhất thường gồm:

- Định danh của IdP và của ứng dụng.
- Endpoint được sử dụng cho các bước trao đổi.
- Khóa hoặc cơ chế xác minh thông điệp từ IdP.
- Giao thức, profile và các lựa chọn bảo vệ được hỗ trợ.
- Định danh người dùng cùng ý nghĩa các thuộc tính được gửi.
- Những tổ chức, tenant hoặc nhóm người dùng được phép tham gia.
- Yêu cầu về xác thực, thời gian và quản lý phiên.
- Cách cập nhật khóa, thay đổi cấu hình và xử lý sự cố.

### Định danh không đồng nghĩa endpoint

Trong SAML, entity ID nhận diện một thực thể, còn Assertion Consumer Service (ACS) là nơi SP nhận thông điệp theo cấu hình. Hai giá trị có thể có hình thức giống URL nhưng không có nghĩa có thể tráo đổi cho nhau.

Trong OIDC, issuer, client ID và redirect URI cũng có vai trò riêng. Không nên dùng “địa chỉ đăng nhập” như một tên chung cho tất cả trường cấu hình.

Sai một giá trị có thể khiến ứng dụng nhận kết quả dành cho hệ thống khác, không tương quan được giao dịch hoặc liên kết sai tổ chức.

### Khóa phải gắn với IdP đã được tin cậy

Một thông điệp tự mang theo khóa công khai không có nghĩa khóa đó được phép đại diện cho IdP. Nếu SP tin bất kỳ khóa nào xuất hiện trong payload, kẻ gửi có thể tự tạo khóa và tự ký thông điệp.

Thông tin xác minh phải được lấy qua cơ chế tin cậy đã thiết lập. Metadata hoặc cấu hình quan hệ tin cậy cũng cần được bảo vệ, kiểm tra nguồn gốc và quản lý thay đổi.

HTTPS bảo vệ kết nối trong phạm vi của nó nhưng không thay thế việc kiểm tra nội dung thông điệp, bên phát hành và bên nhận dự kiến.

## 4. Luồng SP-initiated SSO dưới góc nhìn của ứng dụng

Một luồng SAML do SP khởi tạo có thể được hiểu ở mức khái niệm:

```text
1. Người dùng mở tài nguyên tại SP.
2. SP chưa có phiên phù hợp nên khởi tạo yêu cầu đăng nhập.
3. Trình duyệt chuyển người dùng đến IdP đã cấu hình.
4. IdP xác thực hoặc sử dụng phiên IdP còn đáp ứng yêu cầu.
5. Kết quả được chuyển về endpoint nhận của SP.
6. SP kiểm tra thông điệp và tương quan giao dịch.
7. SP liên kết tài khoản, áp dụng chính sách rồi tạo phiên ứng dụng.
8. Người dùng tiếp tục đến tài nguyên được phép.
```

Cách chuyển thông điệp cụ thể phụ thuộc profile và binding. Mô tả này là luồng khái niệm, không phải hướng dẫn tự triển khai giao thức.

### SP cần giữ ngữ cảnh giao dịch

Ngữ cảnh có thể gồm IdP dự kiến, giao dịch đang chờ, yêu cầu về xác thực và đích điều hướng sau đăng nhập. Các giá trị nhận lại cần được kiểm tra theo quy tắc giao thức, không chỉ giải mã để đọc tên người dùng.

Đích điều hướng sau đăng nhập cần được quản lý để tránh đưa người dùng đến URL tùy ý do bên ngoài cung cấp. Trạng thái điều hướng cũng không phải bằng chứng xác thực.

### Khi đăng nhập bắt đầu từ IdP

Một số môi trường SAML cho phép người dùng bấm ô ứng dụng trên cổng IdP và gửi kết quả về SP mà không có một yêu cầu trước đó do SP tạo.

Đây là trường hợp khác với luồng có tương quan yêu cầu–phản hồi. SP cần xác định rõ có hỗ trợ hay không và có cơ chế bảo vệ tương ứng. Không bỏ kiểm tra trên mọi phản hồi chỉ để hỗ trợ một luồng không có yêu cầu chờ.

Nếu thiết kế yêu cầu SP khởi tạo và theo dõi giao dịch, phản hồi không thuộc một giao dịch phù hợp phải được xử lý theo chính sách đó. Chữ ký đúng không tự giải quyết việc thông điệp bị chèn vào sai phiên trình duyệt.

## 5. SP phải kiểm tra gì trước khi tạo phiên?

SP không nên coi việc đọc được assertion hoặc token là xác thực thành công. Một nhóm kiểm tra cơ bản gồm:

| Câu hỏi | Mục tiêu bảo vệ |
|---|---|
| Ai phát hành? | Đúng IdP được tin cho quan hệ này |
| Nội dung được bảo vệ ra sao? | Chữ ký hoặc cơ chế bảo vệ hợp lệ theo giao thức và cấu hình |
| Thông điệp dành cho ai? | Đúng bên nhận/audience dự kiến |
| Có còn hiệu lực không? | Đúng khoảng thời gian được phép chấp nhận |
| Thuộc giao dịch nào? | Không gắn phản hồi vào sai quá trình đăng nhập |
| Đã bị dùng lại không? | Ngăn sử dụng lại thông điệp trái với quy tắc của luồng |
| Đang nói về chủ thể nào? | Liên kết đúng danh tính trong đúng miền tin cậy |

NIST mô tả các bảo vệ của assertion nhằm hạn chế giả mạo, dùng lại và sử dụng tại sai relying party; audience là một ràng buộc quan trọng cần được bên nhận kiểm tra. [NIST SP 800-63C-4 — Common Federation Requirements](https://pages.nist.gov/800-63-4/sp800-63c/Federation/).

### Chữ ký hợp lệ chỉ là một điều kiện

Một assertion được ký đúng vẫn có thể dành cho ứng dụng khác, đã hết hạn hoặc không phù hợp với giao dịch hiện tại.

Khóa xác minh cũng phải đúng với IdP dự kiến. Không chọn một issuer bất kỳ từ payload rồi tự động tin khóa của issuer đó.

Với SAML/XML, thành phần dùng để xác định chủ thể và quyền phải là nội dung đã được xác minh đúng theo profile, không phải một phần tử khác chỉ vì nó xuất hiện cùng tài liệu. Đây là lý do nên dùng thư viện giao thức được duy trì và cấu hình đúng, thay vì tự ghép kiểm tra chữ ký với thao tác tìm XML tùy ý.

### Tương quan và chống phát lại

Cơ chế cụ thể phụ thuộc giao thức và luồng, có thể liên quan đến request ID, nonce hoặc định danh thông điệp. Khi SP chạy nhiều instance, dữ liệu theo dõi giao dịch và chống lặp cần hoạt động nhất quán trong kiến trúc đó.

Giới hạn thời gian giúp giảm cửa sổ rủi ro nhưng không tự thay thế kiểm tra giao dịch hoặc chống phát lại. Ngược lại, ghi nhận một thông điệp đã dùng không sửa được việc ứng dụng chấp nhận sai audience.

### Ví dụ phía OIDC RP

ID Token validation có các điều kiện như issuer đúng, audience chứa client ID phù hợp, thời gian hiệu lực hợp lệ và các kiểm tra bổ sung theo luồng. Nếu yêu cầu có nonce, giá trị trả về cần được kiểm tra theo quy tắc áp dụng. Các kiểm tra chữ ký, thuật toán và khóa cũng phải theo giao thức, không chỉ dựa vào việc decode JWT. [OpenID Connect Core — ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation).

Các ví dụ trên giúp hiểu trách nhiệm của bên nhận; khi triển khai phải theo đầy đủ yêu cầu của profile và thư viện sử dụng.

## 6. Liên kết danh tính với tài khoản trong SP

Sau khi thông điệp hợp lệ, SP còn phải xác định chủ thể bên ngoài tương ứng với tài khoản nào tại ứng dụng.

### Danh tính phải nằm trong ngữ cảnh bên phát hành

Hai IdP có thể cùng phát hành một giá trị chủ thể giống nhau cho hai người khác nhau. Vì vậy, không nên chỉ dùng một chuỗi subject rời khỏi issuer hoặc miền tin cậy của nó.

Trong OIDC, cặp issuer và subject là cơ sở quan trọng để nhận diện chủ thể trong ngữ cảnh của RP. Với SAML, cần hiểu định dạng và phạm vi định danh đã thỏa thuận; không mặc định mọi NameID đều ổn định và phù hợp làm khóa liên kết lâu dài.

Một mô hình liên kết khái niệm:

```text
Định danh bên ngoài:
    quan hệ tin cậy + chủ thể từ IdP

Liên kết được quản lý:
    định danh bên ngoài → tài khoản nội bộ

Tài khoản nội bộ:
    trạng thái hoạt động + quyền + lịch sử + dữ liệu nghiệp vụ
```

Email có thể đổi, trùng trong những nguồn không kiểm soát hoặc được tái sử dụng. Một claim email khớp không đủ để tự động chiếm quyền sở hữu một tài khoản nội bộ đã tồn tại.

### Account linking cần có kiểm soát

Nếu ứng dụng cho phép liên kết thêm IdP vào tài khoản hiện có, cần có cơ chế chứng minh quyền kiểm soát tài khoản và kiểm tra quan hệ liên kết theo chính sách. Không gắn hai tài khoản chỉ vì người dùng gửi cùng tên hiển thị.

Khi thay IdP, thay tenant hoặc thay dạng định danh, cần có kế hoạch chuyển liên kết. Nếu chỉ bật cấu hình mới, người dùng có thể bị tạo tài khoản thứ hai hoặc được gắn nhầm vào dữ liệu của người khác.

### Just-in-time provisioning

SP có thể tạo tài khoản nội bộ khi người dùng đăng nhập hợp lệ lần đầu. Cách này thường được gọi là JIT provisioning.

JIT vẫn cần điều kiện: ai được tạo tài khoản, thuộc tổ chức nào, quyền mặc định nào được phép và thông tin nào là bắt buộc. Tạo tài khoản thành công không đồng nghĩa được cấp mọi quyền mà IdP gửi trong một claim.

JIT cũng không tự giải quyết deprovisioning. Nếu người dùng không đăng nhập lại, thông tin quyền tại SP có thể không được cập nhật qua luồng đăng nhập. Vòng đời tài khoản và quyền cần một cơ chế quản lý phù hợp ngoài việc chờ lần đăng nhập kế tiếp.

## 7. SP vẫn chịu trách nhiệm authorization

Federation hỗ trợ SP biết đang giao dịch với chủ thể nào theo quan hệ tin cậy. Quyết định người đó được làm gì vẫn cần chính sách của ứng dụng.

Một biểu thức khái niệm:

```text
Cho phép hành động =
    phiên đáp ứng yêu cầu xác thực
    AND tài khoản nội bộ được phép hoạt động
    AND chính sách cho phép hành động trên tài nguyên cụ thể
    AND các điều kiện cần thiết khác được đáp ứng
```

Các điều kiện thực tế còn phụ thuộc mô hình ứng dụng; biểu thức chỉ minh họa việc xác thực không phải điều kiện duy nhất.

### Ánh xạ nhóm và vai trò

SP có thể sử dụng thuộc tính hoặc nhóm từ IdP như đầu vào cho RBAC/ABAC. Cần quy định rõ:

- IdP nào có thẩm quyền cung cấp thuộc tính đó.
- Giá trị được hiểu trong tổ chức hoặc tenant nào.
- Giá trị nào được phép ánh xạ sang quyền nội bộ.
- Quyền nào cần phê duyệt hoặc quản lý riêng.
- Xử lý thế nào khi thuộc tính thiếu, sai hoặc không còn phù hợp.

Ví dụ, claim nhóm có giá trị `admin` từ một tổ chức đối tác không được mặc nhiên chuyển thành quản trị toàn ứng dụng. Ý nghĩa phải gắn với nguồn và phạm vi đã được chấp thuận.

Nếu không đủ dữ liệu để cấp một quyền nhạy cảm, SP cần từ chối hoặc chuyển sang xử lý theo chính sách. Không cấp quyền rộng để tránh lỗi trải nghiệm.

### Tài khoản nội bộ bị đình chỉ

IdP có thể xác thực thành công nhưng tài khoản tại SP đang bị đình chỉ vì lý do nghiệp vụ hoặc an ninh. SP cần tôn trọng điều kiện tại ứng dụng, không tự mở lại tài khoản chỉ vì nhận một kết quả đăng nhập hợp lệ.

Việc kích hoạt lại phải thuộc quy trình có thẩm quyền. Nếu cơ chế provisioning liên tục bật lại tài khoản bị khóa, cần xử lý mâu thuẫn về nguồn quản lý trạng thái.

### MFA và step-up

Một hành động nhạy cảm có thể yêu cầu mức xác thực hoặc độ mới của xác thực cao hơn phiên hiện tại. SP cần hiểu ý nghĩa thông tin về ngữ cảnh xác thực được IdP cung cấp và yêu cầu bổ sung khi cần.

Không coi một claim có tên gợi ý “MFA” là bằng chứng đủ nếu chưa có thỏa thuận về ngữ nghĩa và cách kiểm chứng. Tương tự, đăng nhập từ một IdP hỗ trợ MFA không có nghĩa giao dịch cụ thể đã sử dụng MFA theo yêu cầu của SP.

## 8. Phiên của SP khác phiên của IdP

Trong SSO, thường tồn tại ít nhất hai ngữ cảnh phiên:

```text
Trình duyệt ↔ IdP: phiên tại IdP
Trình duyệt ↔ ứng dụng: phiên do SP quản lý
```

Chính nhờ phiên IdP, người dùng có thể vào ứng dụng khác mà không phải nhập lại thông tin xác thực nếu chính sách cho phép. Tuy nhiên, mỗi SP vẫn có trạng thái và thời hạn phiên riêng.

### Hết hạn thông điệp không nhất thiết kết thúc phiên

Assertion hoặc ID Token có cửa sổ chấp nhận cho mục đích xác thực. Sau khi SP tạo phiên nội bộ, vòng đời phiên phải được quản lý riêng.

Không nên kéo dài phiên vô hạn chỉ vì đăng nhập ban đầu thành công. Cần cân nhắc thời hạn tuyệt đối, thời gian không hoạt động, yêu cầu xác thực lại và rủi ro của tài nguyên.

### Đăng xuất không luôn lan đến mọi nơi

Đăng xuất khỏi SP thường kết thúc phiên tại SP theo khả năng ứng dụng. Đăng xuất khỏi IdP cũng không tự bảo đảm mọi SP đã hủy phiên ngay lập tức.

Các cơ chế logout liên kết hoặc tín hiệu vòng đời có thể hỗ trợ, nhưng phải được hai phía triển khai, cấu hình và kiểm chứng. Việc khóa tài khoản IdP chủ yếu ảnh hưởng những bước xác thực cần đến IdP; các phiên hoặc phương thức truy cập khác tại SP vẫn cần được đánh giá.

Khi thu hồi quyền khẩn cấp, cần biết kiến trúc ứng dụng có thể kết thúc phiên, cập nhật quyền đang dùng hoặc vô hiệu hóa token như thế nào.

### Bảo vệ phiên ứng dụng

Sau xác thực, SP cần tạo hoặc cập nhật định danh phiên an toàn, ngăn sử dụng tiếp một định danh phiên không phù hợp và bảo vệ cookie.

Các thuộc tính cookie và hành vi callback phải được chọn phù hợp với luồng chuyển hướng hoặc gửi form qua các miền. Không áp một cấu hình máy móc rồi tắt kiểm tra bảo mật khi callback không hoạt động.

Các endpoint nghiệp vụ vẫn cần kiểm tra phiên, quyền và các bảo vệ ứng dụng liên quan. Federation không thay thế bảo vệ chống XSS, CSRF hoặc kiểm soát truy cập tài nguyên.

## 9. SP trong môi trường nhiều IdP và nhiều tenant

Một SP có thể phục vụ nhân viên nội bộ, khách hàng doanh nghiệp và đối tác. Mỗi nhóm có thể dùng một IdP khác nhau.

### Định tuyến đăng nhập không tạo ra tin cậy

Tên miền email, tenant hint hoặc lựa chọn trên màn hình có thể giúp chọn luồng đăng nhập. Chúng chưa chứng minh người dùng thuộc tổ chức được phép hoặc issuer nhận lại là đúng.

SP cần gắn giao dịch với quan hệ tin cậy dự kiến và kiểm tra kết quả trong ngữ cảnh đó. Không chấp nhận một IdP khác chỉ vì người dùng đổi tham số trong URL.

### Tách phạm vi tenant

Nếu ứng dụng nhiều tenant, cần bảo đảm liên kết tài khoản và quyền đều mang phạm vi tenant đúng. Người dùng đăng nhập hợp lệ ở tenant A không tự có quyền với tài nguyên tenant B.

Cấu hình cùng một IdP cho nhiều tenant cũng không có nghĩa mọi tài khoản từ IdP đó được phép vào tất cả tenant. Điều kiện thành viên, liên kết tài khoản và quyền ứng dụng vẫn phải được kiểm tra.

### Vai trò thay đổi theo quan hệ

Một identity broker có thể là SP hoặc RP đối với IdP phía trên, đồng thời đóng vai trò IdP đối với ứng dụng phía dưới.

```text
IdP gốc → Broker → Ứng dụng
          ↑            ↑
   bên nhận ở chặng 1   SP ở chặng 2
   bên phát ở chặng 2
```

Ứng dụng phía dưới cần tin đúng bên phát hành trực tiếp theo kiến trúc đã thiết kế. Không mặc định có thể bỏ qua broker để tự diễn giải hoặc tin mọi thông tin từ upstream.

Mỗi chặng cần xác định trách nhiệm về định danh, thuộc tính, khóa và mức xác thực được chuyển tiếp.

## 10. Ví dụ: ứng dụng quản lý chi phí là SP

Công ty triển khai một cổng chi phí với ba quyền: tạo đề nghị, xem báo cáo và duyệt hoàn tiền. Nhân viên xác thực tại IdP doanh nghiệp.

Một thiết kế trách nhiệm có thể là:

| Quyết định hoặc thao tác | Bên chịu trách nhiệm |
|---|---|
| Kiểm tra thông tin xác thực và MFA theo chính sách đăng nhập | IdP |
| Chỉ chấp nhận kết quả từ IdP đã cấu hình cho công ty | SP |
| Liên kết chủ thể với đúng tài khoản cổng chi phí | SP cùng nguồn quản lý liên kết |
| Xác định quyền duyệt hoàn tiền còn phù hợp | Chính sách và quy trình quản trị quyền |
| Chặn thao tác duyệt khi tài khoản không có quyền | SP tại endpoint nghiệp vụ |
| Quản lý phiên cổng chi phí | SP |
| Cập nhật tài khoản khi nhân viên nghỉ việc | Quy trình vòng đời phối hợp IdP, IAM và SP |

Lan đăng nhập thành công nhưng chỉ có quyền tạo đề nghị. Nếu Lan gọi chức năng duyệt hoàn tiền, SP phải từ chối dù kết quả xác thực hoàn toàn hợp lệ.

Khi Lan chuyển bộ phận và mất quyền duyệt, SP cần nhận hoặc tính lại trạng thái quyền theo cơ chế quản trị. Một assertion cũ hoặc phiên cũ không nên trở thành lý do duy trì quyền trái với chính sách.

Nếu IdP gặp sự cố, SP cần thực hiện chính sách khả dụng và phiên đã được thiết kế. Không giải quyết bằng cách chấp nhận thông điệp chưa xác minh hoặc bật một đường đăng nhập đặc quyền thiếu kiểm soát.

## 11. Các tình huống lỗi và cách suy luận

| Biểu hiện | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Phản hồi về sai endpoint | Cấu hình callback/ACS, tên miền, môi trường hoặc proxy sai | Đối chiếu giá trị đã đăng ký và địa chỉ công khai thực tế |
| Chữ ký không xác minh được | Sai khóa, thay khóa, sai bên phát hoặc thông điệp không hợp lệ | Kiểm tra quan hệ tin cậy và lịch thay khóa; giữ nguyên kiểm tra bảo mật |
| Audience không phù hợp | Dùng cấu hình của ứng dụng khác hoặc sai định danh SP/client | Sửa cấu hình đúng môi trường và bên nhận |
| Thông điệp bị coi quá hạn | Sai lệch đồng hồ, độ trễ hoặc cấu hình hiệu lực | Kiểm tra đồng hồ và nguyên nhân; không mở rộng thời gian tùy ý |
| Không tìm thấy tài khoản | Thiếu provisioning hoặc liên kết danh tính sai | Xử lý theo nguồn liên kết và chính sách JIT đã xác định |
| Đăng nhập được nhưng thiếu quyền | Ánh xạ nhóm, vai trò hoặc đồng bộ quyền chưa phù hợp | Kiểm tra authorization riêng với authentication |
| Chỉ lỗi ở một instance | Trạng thái giao dịch hoặc phiên chưa chia sẻ đúng | Kiểm tra thiết kế lưu trạng thái khi mở rộng nhiều instance |
| Người dùng vào sai tenant | Định tuyến và liên kết không giữ phạm vi tổ chức | Kiểm tra issuer, giao dịch, tài khoản và quyền theo tenant |

Nếu có reverse proxy, SP cần biết địa chỉ bên ngoài đúng nhưng không được tin mọi header do client cung cấp. Cấu hình tin cậy proxy phải phù hợp hạ tầng, tránh để đầu vào không kiểm soát làm thay đổi URL được sử dụng trong kiểm tra.

### Logging và kiểm chứng

Log nên có mã tương quan giao dịch, quan hệ tin cậy, thời điểm, kết quả kiểm tra và mã lỗi phù hợp. Không ghi toàn bộ assertion, token, cookie phiên hoặc bí mật vào log chỉ để tiện chẩn đoán.

Khi kiểm chứng tích hợp, cần có cả tình huống chấp nhận đầu vào hợp lệ và từ chối đầu vào không phù hợp: sai issuer, sai audience, quá hạn, sai tương quan, dùng lại hoặc tài khoản bị đình chỉ.

Một ca đăng nhập thành công không chứng minh mọi kiểm tra từ chối đang hoạt động. Tương tự, thông báo “access denied” cần được phân loại để biết thất bại ở bước xác thực thông điệp, liên kết tài khoản hay authorization.

## 12. Quản lý SP trong vận hành IAM

Một SP cần có chủ ứng dụng và người chịu trách nhiệm cho quan hệ federation. Các cấu hình quan trọng nên được quản lý như thay đổi bảo mật.

### Thay khóa và cập nhật metadata

Thay khóa cần phối hợp khả năng hỗ trợ của hai bên, thời điểm hiệu lực và cách cập nhật thông tin xác minh. Nếu có khoảng chuyển tiếp, chỉ chấp nhận các khóa còn thuộc chính sách tin cậy trong giai đoạn đó.

Không giữ khóa cũ vô thời hạn, cũng không tắt xác minh chữ ký khi gặp lỗi sau thay khóa. Khi nghi ngờ khóa bị lộ, cần quy trình xử lý sự cố, đánh giá thông điệp và phiên có thể bị ảnh hưởng theo kiến trúc thực tế.

### Vòng đời tài khoản và quyền

Federation cần phối hợp với provisioning, deprovisioning, quản trị vai trò và rà soát quyền. SP nên xác định rõ hệ thống nào có thẩm quyền về trạng thái tài khoản, thuộc tính và từng nhóm quyền.

Nếu một thay đổi thủ công tại SP bị hệ thống đồng bộ đảo ngược, đó là dấu hiệu mô hình nguồn có thẩm quyền hoặc cơ chế ngoại lệ chưa rõ.

### Giảm dữ liệu chia sẻ

SP chỉ nên yêu cầu thuộc tính cần cho mục đích được xác định. Không cần nhận toàn bộ hồ sơ nhân sự để biết người dùng có được truy cập một cổng báo cáo hay không.

Thông tin nhận được cũng cần được bảo vệ tại ứng dụng. Việc IdP truyền dữ liệu qua một thông điệp hợp lệ không làm mất trách nhiệm quản lý dữ liệu và quyền đọc tại SP.

### Những điều cần giữ rõ

- Tin IdP nào, cho tổ chức nào và dựa trên cấu hình nào.
- Thông điệp đã được kiểm tra đúng mục đích hay chưa.
- Danh tính ngoài ứng dụng được liên kết với tài khoản nào.
- Quyền nào do SP quyết định hoặc nhận từ nguồn quản trị.
- Phiên kết thúc, quyền thay đổi và tài khoản nghỉ việc được xử lý ra sao.
- Bằng chứng nào đủ để xác nhận từng bước trong phạm vi thực tế.

Service Provider là nơi kết quả xác thực liên kết trở thành một phiên ứng dụng và các quyết định truy cập cụ thể. Một SP được thiết kế tốt giữ được ranh giới giữa tin cậy IdP, nhận diện tài khoản và cho phép hành động, đồng thời quản lý vòng đời quyền cùng phiên theo nhu cầu của dịch vụ.
