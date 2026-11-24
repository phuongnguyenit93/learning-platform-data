# Passkey sync và device — Đồng bộ passkey và xác thực giữa các thiết bị

> **Chương:** Passkey và WebAuthn  
> **Chủ đề:** Passkey sync và device  
> **Phạm vi:** Security Authentication Fundamentals — cách passkey được gắn với authenticator, đồng bộ giữa thiết bị, sử dụng thiết bị khác để đăng nhập, quản lý vòng đời credential và đánh giá ranh giới tin cậy.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **passkey đồng bộ (syncable passkey)**, **passkey gắn với thiết bị (device-bound passkey)** và **xác thực liên thiết bị (cross-device authentication)**.
2. Mô tả vai trò của credential ID, khóa công khai, khóa riêng, authenticator, relying party và nhà cung cấp đồng bộ.
3. Giải thích các cờ WebAuthn **Backup Eligibility (BE)** và **Backup State (BS)** ở mức mà relying party có thể quan sát.
4. Đánh giá đánh đổi giữa khả năng phục hồi, tính tiện dụng, chống phishing, bảo vệ khóa và mức kiểm soát thiết bị.
5. Thiết kế chính sách đăng ký, đăng nhập, thu hồi và khôi phục passkey khi người dùng thêm, mất hoặc thay thiết bị.
6. Xác định các kiểm tra cần có ở server để tránh nhầm việc đồng bộ credential với việc chuyển giao danh tính hoặc quyền truy cập.

## 1. Passkey sync và device là vấn đề gì?

Passkey là credential dựa trên mật mã khóa công khai, được dùng qua các giao thức như **FIDO2/WebAuthn**. Khi đăng ký, relying party (RP) lưu credential ID và khóa công khai. Authenticator giữ khóa riêng và dùng nó để ký challenge mới khi người dùng đăng nhập. Khóa riêng không cần được gửi tới website.

Khi người dùng có nhiều thiết bị, có hai nhu cầu khác nhau:

- **Dùng cùng một passkey trên nhiều thiết bị:** người dùng đăng ký credential có khả năng sao lưu/đồng bộ qua hệ sinh thái của nhà cung cấp passkey. Credential có thể xuất hiện trên nhiều thiết bị đã được liên kết với tài khoản đồng bộ.
- **Dùng một thiết bị để đăng nhập trên thiết bị khác:** ví dụ điện thoại có passkey giúp đăng nhập vào website đang mở trên laptop. Đây là cross-device authentication; khóa riêng vẫn được sử dụng bởi authenticator trên điện thoại.

Hai cách này thường bị gọi chung là “đăng nhập từ thiết bị khác”, nhưng mô hình khóa và ranh giới tin cậy khác nhau. **Đồng bộ passkey** liên quan vòng đời bản sao credential giữa các thiết bị. **Cross-device authentication** là cách một thiết bị authenticator thực hiện một lần xác thực cho client ở thiết bị khác.

### Ba khái niệm cần tách biệt

| Khái niệm | Điều gì xảy ra? | Ví dụ |
| --- | --- | --- |
| **Device-bound passkey** | Credential gắn với authenticator/thiết bị và không được thiết kế để đồng bộ sang thiết bị khác | Passkey trên khóa bảo mật phần cứng hoặc authenticator thiết bị không backup |
| **Synced passkey** | Credential đủ điều kiện backup và được nhà cung cấp đồng bộ tới các thiết bị thuộc cùng hệ sinh thái/tài khoản | Passkey được đồng bộ giữa điện thoại, tablet và laptop của cùng người dùng |
| **Cross-device authentication** | Thiết bị đang mở website yêu cầu một authenticator ở thiết bị khác thực hiện WebAuthn | Laptop hiển thị QR, người dùng dùng điện thoại quét để đăng nhập |

Một người dùng có thể vừa có passkey đồng bộ, vừa có khóa bảo mật device-bound, đồng thời sử dụng điện thoại để xác thực cho laptop. Không nên gộp tất cả thành một thuộc tính “passkey trên thiết bị”.

## 2. Thành phần của một passkey

Trong một credential WebAuthn:

| Thành phần | Vai trò |
| --- | --- |
| **Relying Party (RP)** | Website/dịch vụ yêu cầu đăng ký và xác thực; được định danh bằng RP ID |
| **Authenticator** | Thiết bị hoặc phần mềm bảo vệ khóa riêng và thực hiện thao tác xác thực |
| **Credential ID** | Định danh credential được gửi trong assertion để RP tìm bản ghi tương ứng |
| **Private key** | Khóa riêng được authenticator giữ và sử dụng để ký; không gửi cho RP |
| **Public key** | Khóa công khai RP lưu khi đăng ký và dùng để kiểm tra chữ ký |
| **User handle** | Định danh nội bộ do RP cung cấp để liên kết credential với tài khoản |
| **Challenge** | Giá trị mới do RP tạo cho từng lần đăng nhập, giúp chống replay |
| **Sync provider** | Hệ sinh thái/quản lý credential có thể backup và phân phối passkey tới các thiết bị đã liên kết |

RP thường không cần biết private key được lưu trong chip bảo mật cụ thể nào để xác minh assertion. Nó cần kiểm tra đúng credential, chữ ký, challenge, origin, RP ID và chính sách user verification.

### Passkey thường là discoverable credential

Passkey thường được tạo dưới dạng **discoverable credential** (trước đây hay gọi là resident credential), cho phép authenticator tìm credential phù hợp với RP mà không cần RP gửi trước danh sách credential ID. Điều này hỗ trợ luồng đăng nhập không cần nhập username: authenticator cung cấp thông tin định danh/credential phù hợp trong assertion.

Discoverable không đồng nghĩa với đồng bộ. Một discoverable credential có thể là device-bound hoặc syncable, tùy authenticator và chính sách backup.

## 3. Device-bound passkey

**Device-bound passkey** là credential gắn với một authenticator cụ thể và không được thiết kế để backup/đồng bộ theo cơ chế passkey sync. Khóa riêng thường được bảo vệ bởi phần cứng hoặc vùng bảo mật của thiết bị, tùy nền tảng.

Ví dụ:

- Passkey được tạo trên khóa bảo mật FIDO2 có khả năng lưu credential nhưng không cung cấp backup/sync.
- Credential nền tảng được chính sách thiết bị doanh nghiệp giữ cố định trên thiết bị được quản lý.
- Một authenticator có khả năng lưu khóa không xuất được và không hỗ trợ chuyển credential sang thiết bị khác.

### Ưu điểm

- **Giảm phạm vi sao chép credential:** khóa riêng không được đồng bộ sang nhiều thiết bị theo cơ chế passkey sync.
- **Kiểm soát thiết bị:** tổ chức có thể quản lý thiết bị, khóa bảo mật, vòng đời và thu hồi vật lý theo chính sách.
- **Phù hợp một số yêu cầu assurance:** khi cần chứng minh credential được gắn với authenticator cụ thể hoặc thiết bị được quản lý, device-bound có thể phù hợp hơn.

### Hạn chế

- Mất hoặc hỏng thiết bị có thể làm người dùng mất credential.
- Cần thiết lập nhiều authenticator dự phòng hoặc quy trình khôi phục đủ an toàn.
- Chi phí cấp phát, hỗ trợ, thay thế và kiểm kê thiết bị có thể cao.
- Thiết bị bị chiếm quyền vẫn có thể bị lạm dụng trong thời gian attacker kiểm soát phiên hoặc khả năng sử dụng authenticator.

**Device-bound không có nghĩa là tuyệt đối an toàn.** Nếu malware điều khiển trình duyệt hoặc kẻ tấn công lấy được session sau đăng nhập, việc private key không sync không tự bảo vệ mọi request tiếp theo.

## 4. Synced passkey — passkey có khả năng đồng bộ

**Synced passkey** là passkey được tạo trong một hệ sinh thái có khả năng backup và phân phối credential tới các thiết bị khác thuộc tài khoản/nhóm thiết bị được phép. Nhà cung cấp có thể sử dụng mã hóa đầu cuối và cơ chế xác minh thiết bị để bảo vệ dữ liệu đồng bộ; chi tiết cụ thể phụ thuộc nền tảng, cấu hình và chính sách của nhà cung cấp.

Ví dụ về trải nghiệm:

1. Người dùng tạo passkey trên điện thoại.
2. Nhà cung cấp passkey lưu bản backup được bảo vệ trong hệ sinh thái của người dùng.
3. Người dùng đăng nhập tài khoản đồng bộ trên tablet mới và hoàn thành điều kiện bảo mật của nhà cung cấp.
4. Passkey trở nên khả dụng trên tablet; người dùng có thể xác thực với cùng RP mà không phải đăng ký một credential mới tại website.

### Lợi ích

- Người dùng có thể đăng nhập từ nhiều thiết bị mà không phải nhớ mật khẩu.
- Mất một thiết bị không nhất thiết đồng nghĩa mất mọi passkey.
- Giảm số lần phải dùng quy trình recovery riêng của từng website.
- Hỗ trợ trải nghiệm passwordless trên nhiều nền tảng và form factor.

### Đánh đổi

- Tài khoản đồng bộ trở thành một phần quan trọng của mô hình tin cậy.
- Khả năng khôi phục tài khoản sync provider có thể ảnh hưởng tới khả năng lấy lại passkey.
- Thiết bị mới được thêm vào hệ sinh thái có thể làm mở rộng nơi credential khả dụng.
- Chính sách backup, mã hóa, recovery và xác minh thiết bị không giống nhau giữa các nhà cung cấp.
- RP không nhất thiết quan sát được chi tiết cách nhà cung cấp bảo vệ backup hoặc ai đang kiểm soát tài khoản đồng bộ.

Không nên suy luận rằng mọi synced passkey đều được bảo vệ giống nhau chỉ vì cùng dùng WebAuthn. **WebAuthn định nghĩa cách RP và authenticator trao đổi bằng chứng; chính sách đồng bộ và khôi phục thuộc hệ sinh thái authenticator/provider.**

## 5. Backup Eligibility (BE) và Backup State (BS)

WebAuthn có hai cờ trong authenticator data liên quan trạng thái backup của credential:

- **BE — Backup Eligibility:** cho biết credential có đủ điều kiện để được backup hay không.
- **BS — Backup State:** cho biết credential hiện đang ở trạng thái đã được backup hay chưa.

Các cờ này giúp RP hiểu một phần đặc tính backup của credential mà authenticator báo trong ceremony. Chúng **không cung cấp toàn bộ thông tin** về nhà cung cấp sync, vị trí lưu backup, chất lượng mã hóa hoặc mức bảo vệ tài khoản đồng bộ.

| BE | BS | Diễn giải khái quát |
| --- | --- | --- |
| 0 | 0 | Credential không đủ điều kiện backup; trạng thái không backup |
| 1 | 0 | Credential đủ điều kiện backup nhưng hiện chưa báo trạng thái đã backup |
| 1 | 1 | Credential đủ điều kiện backup và hiện báo đã backup |

Trong mô hình WebAuthn, BE được thiết lập khi credential được tạo và không được thay đổi trong vòng đời credential; BS có thể phản ánh trạng thái backup hiện tại. Tổ hợp BE=0, BS=1 là trạng thái không hợp lệ theo ý nghĩa của các cờ.

### RP nên sử dụng BE/BS như thế nào?

1. Đọc cờ từ authenticator data sau khi xác minh assertion đúng giao thức.
2. Ghi nhận trạng thái cùng credential và sự kiện đăng ký/xác thực.
3. Dùng thông tin đó làm **một tín hiệu trong policy**, ví dụ phân biệt credential có thể backup với credential không backup.
4. Không tự suy ra rằng BE=1 nghĩa là credential chắc chắn đang nằm trên cloud; hãy xét BS và ngữ cảnh.
5. Không tự suy ra rằng BE=0 đảm bảo thiết bị chưa từng bị xâm phạm hoặc không thể bị sao chép bằng mọi hình thức.
6. Không xem BE/BS là bằng chứng về chất lượng mã hóa, bảo mật tài khoản sync provider hoặc mức kiểm soát thiết bị.

### Ví dụ quyết định chính sách

Một ứng dụng ngân hàng có thể:

- Cho phép synced passkey để đăng nhập thông thường.
- Yêu cầu step-up hoặc authenticator device-bound cho một số thao tác quản trị rủi ro cao, nếu mô hình assurance của tổ chức yêu cầu.
- Ghi nhận BE/BS như metadata để hỗ trợ phân tích và phát hiện thay đổi.
- Không từ chối mọi credential BE=1 theo mặc định nếu chưa có yêu cầu rủi ro hoặc tuân thủ rõ ràng.

Đây là ví dụ chính sách. Việc một credential backup-eligible có đủ assurance hay không phải được đánh giá trong toàn bộ hồ sơ xác thực, không chỉ bằng một bit.

## 6. Sync passkey và cross-device authentication không giống nhau

Hai cơ chế có thể cùng xuất hiện trong trải nghiệm người dùng nhưng giải quyết hai vấn đề riêng:

| Tiêu chí | Passkey sync | Cross-device authentication |
| --- | --- | --- |
| Mục đích | Làm credential khả dụng trên nhiều thiết bị | Dùng authenticator ở thiết bị khác để hoàn tất một lần đăng nhập |
| Khóa riêng | Có thể được backup/phân phối theo cơ chế sync provider | Vẫn được dùng tại authenticator thiết bị đang giữ credential |
| Thiết bị mới | Credential có thể được khôi phục/đồng bộ khi thiết bị tham gia hệ sinh thái | Thiết bị mới có thể chỉ là client yêu cầu đăng nhập, không cần lưu passkey |
| Ví dụ | Passkey trên điện thoại đồng bộ sang tablet | Laptop hiển thị QR, điện thoại xác thực cho laptop |
| Ranh giới tin cậy chính | Tài khoản sync provider, backup, recovery và các thiết bị liên kết | Ghép nối phiên, xác minh thiết bị gần đó, kênh truyền và authenticator |

### Cross-device flow bằng điện thoại

Một kịch bản thường gặp:

1. Người dùng mở trang đăng nhập trên laptop.
2. Browser/RP khởi tạo WebAuthn request và cung cấp challenge.
3. Giao diện đề xuất dùng thiết bị khác và hiển thị QR.
4. Người dùng quét QR bằng điện thoại có authenticator/passkey.
5. Cơ chế hybrid transport có thể dùng Bluetooth Low Energy (BLE) để hỗ trợ xác minh khoảng cách/proximity, cùng kênh liên lạc được bảo vệ để phối hợp phiên.
6. Điện thoại hiển thị thông tin website/yêu cầu và thực hiện user verification theo policy.
7. Authenticator trên điện thoại ký challenge; assertion được chuyển về luồng đăng nhập trên laptop.
8. RP xác minh assertion như một WebAuthn response bình thường rồi quyết định tạo phiên.

**Private key không cần được sao chép sang laptop.** Laptop là client nhận kết quả của ceremony; điện thoại là authenticator tạo assertion.

### Sơ đồ luồng khái quát

`````````mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant L as Laptop / Browser
    participant RP as Website / RP
    participant P as Điện thoại / Authenticator
    U->>L: Chọn đăng nhập bằng thiết bị khác
    L->>RP: Yêu cầu WebAuthn
    RP-->>L: Challenge và RP context
    L-->>U: Hiển thị QR
    U->>P: Quét QR
    P->>P: Xác minh ngữ cảnh RP và thiết lập liên kết hybrid
    P->>U: User verification trên điện thoại
    U-->>P: Hoàn tất xác minh
    P->>P: Ký challenge bằng passkey
    P-->>L: Chuyển assertion qua phiên cross-device
    L->>RP: Gửi assertion
    RP->>RP: Kiểm tra chữ ký, challenge, origin/RP ID và policy
    RP-->>L: Hoàn tất login nếu hợp lệ
`````````

Chi tiết giao thức hybrid có thể khác theo trình duyệt, hệ điều hành và authenticator. QR/BLE là một phần của cơ chế phối hợp và proximity; chúng không thay thế kiểm tra chữ ký WebAuthn tại RP.

## 7. Mô hình tin cậy của sync provider

Với synced passkey, RP cần hiểu rằng có thêm một thành phần trong chuỗi tin cậy: **dịch vụ quản lý credential và tài khoản đồng bộ**.

Các câu hỏi cần đặt ra:

- Người dùng xác thực thế nào khi truy cập tài khoản sync provider?
- Việc thêm thiết bị mới có cần xác minh thiết bị hiện có, passkey, khóa khôi phục hoặc yếu tố tăng cường không?
- Backup có được mã hóa đầu cuối không? Ai có thể khôi phục khóa mã hóa?
- Nhà cung cấp có thể đọc credential hay chỉ phân phối ciphertext? Cam kết này dựa trên tài liệu/chính sách nào?
- Khi người dùng mất toàn bộ thiết bị, cơ chế recovery có thể mở lại passkey bằng cách nào?
- Thiết bị cũ bị mất có thể bị loại khỏi tài khoản đồng bộ và ngừng truy cập backup ra sao?
- Người dùng có nhận thông báo khi thiết bị mới tham gia hoặc credential được khôi phục không?

### Tài khoản sync provider là một điểm tập trung rủi ro

Nếu attacker chiếm tài khoản đồng bộ, họ có thể tìm cách lấy quyền truy cập tới passkey backup hoặc thêm thiết bị mới, tùy mô hình bảo vệ của provider. Do đó:

- Bảo vệ tài khoản sync provider bằng phương thức chống phishing và recovery mạnh.
- Bật thông báo đăng nhập/thiết bị mới nếu nền tảng hỗ trợ.
- Xem xét thu hồi thiết bị đã mất khỏi hệ sinh thái đồng bộ.
- Không dùng kênh recovery yếu hơn mức bảo vệ mà ứng dụng yêu cầu cho tài khoản đích.
- Có thể yêu cầu step-up tại RP trước hành động rủi ro cao, ngay cả khi passkey được đồng bộ.

RP thường **không có khả năng tự kiểm toán** quá trình backup nội bộ của provider. Hệ thống cần tránh tuyên bố mức đảm bảo vượt quá bằng chứng thực tế mà giao thức cung cấp.

## 8. Chọn synced hay device-bound?

Không có lựa chọn phù hợp cho mọi hệ thống. Quyết định cần dựa trên mức rủi ro, khả năng quản lý thiết bị, nhu cầu khôi phục và chi phí hỗ trợ.

| Tiêu chí | Synced passkey | Device-bound passkey |
| --- | --- | --- |
| Tiện lợi nhiều thiết bị | Cao trong hệ sinh thái hỗ trợ | Cần đăng ký credential riêng trên thiết bị khác |
| Phục hồi khi mất thiết bị | Có thể dễ hơn nếu còn tài khoản/thiết bị sync hợp lệ | Cần authenticator dự phòng hoặc recovery riêng |
| Phụ thuộc provider | Có; chính sách sync/recovery là một phần trust model | Thường ít phụ thuộc sync provider |
| Kiểm soát thiết bị | Phụ thuộc khả năng quản lý thiết bị của provider/tổ chức | Có thể gắn với thiết bị/khóa bảo mật cụ thể |
| Phạm vi credential | Có thể mở rộng qua nhiều thiết bị đã liên kết | Hạn chế ở authenticator đã đăng ký |
| Vận hành doanh nghiệp | Thuận tiện cho BYOD nhưng cần policy rõ | Có thể phù hợp thiết bị được quản lý và yêu cầu phần cứng |
| Rủi ro khi account sync bị chiếm | Có thể ảnh hưởng nhiều passkey | Không có đường sync này, nhưng thiết bị riêng vẫn có thể bị chiếm |

### Ví dụ theo bối cảnh

**Ứng dụng tiêu dùng:** Người dùng thay điện thoại thường xuyên, cần khả năng đăng nhập từ laptop/tablet. Synced passkey có thể cải thiện trải nghiệm và giảm lockout; cần truyền thông rõ cách bảo vệ tài khoản đồng bộ.

**Cổng quản trị doanh nghiệp:** Tổ chức quản lý thiết bị, yêu cầu khóa bảo mật phần cứng hoặc credential device-bound cho nhóm admin. Cần quy trình cấp khóa dự phòng và offboarding.

**Tài khoản rủi ro cao:** Có thể chấp nhận synced passkey cho login thường, nhưng yêu cầu step-up khác cho chuyển tiền, thay đổi recovery hoặc thêm authenticator. Chính sách phải căn cứ mô hình đe dọa, không chỉ tên loại credential.

## 9. Đăng ký passkey và lưu metadata ở RP

Dù passkey có sync hay không, RP vẫn thực hiện WebAuthn registration và lưu thông tin credential đã được xác minh.

### Registration flow

1. Xác định tài khoản và xác minh người dùng hiện có đủ quyền đăng ký authenticator mới.
2. Tạo challenge ngẫu nhiên, một lần, gắn với tài khoản, RP ID và transaction.
3. Cung cấp yêu cầu WebAuthn với user verification policy phù hợp.
4. Authenticator tạo credential; nếu hỗ trợ backup, credential có thể báo BE tương ứng trong authenticator data.
5. RP xác minh client data, challenge, origin, RP ID hash, attestation theo policy và cấu trúc credential.
6. Lưu credential ID, public key, user handle, transports/metadata cần thiết, thời điểm đăng ký và các cờ backup được xác minh.
7. Thông báo đăng ký và cho người dùng quản lý tên thiết bị/credential theo trải nghiệm sản phẩm.

### Dữ liệu nên lưu

| Trường | Mục đích |
| --- | --- |
| Credential ID | Tìm credential khi assertion tới |
| User/account reference | Liên kết credential với tài khoản nội bộ |
| Public key và algorithm | Kiểm tra chữ ký |
| User handle | Ánh xạ định danh theo WebAuthn |
| BE / BS đã xác minh | Ghi nhận trạng thái backup mà authenticator báo |
| Sign counter/metadata liên quan | Hỗ trợ đánh giá hành vi authenticator theo giới hạn của cơ chế |
| Created at / last used at | Quản lý vòng đời và hiển thị thiết bị |
| Display name / label | Giúp người dùng nhận biết credential; không phải bằng chứng mật mã |
| Revocation state | Chặn credential đã bị thu hồi |

Không lưu private key. Không đặt tên thiết bị do client cung cấp thành căn cứ tin cậy cho authorization. Metadata như model, platform, transport hoặc attestation cần được xử lý theo mục đích và quyền riêng tư; không phải trường nào cũng chứng minh danh tính phần cứng.

## 10. Đăng nhập bằng synced passkey

Quá trình assertion về cơ bản vẫn là WebAuthn:

1. RP tạo challenge mới, gắn với transaction và thời hạn.
2. Browser gọi WebAuthn API để yêu cầu credential phù hợp với RP.
3. Authenticator/provider tìm passkey có thể dùng trên thiết bị hiện tại.
4. Người dùng thực hiện user verification theo policy.
5. Authenticator ký challenge bằng private key.
6. Browser gửi assertion tới RP.
7. RP xác minh chữ ký, challenge, origin, RP ID, credential ID, UP/UV và trạng thái account/credential.
8. RP áp dụng risk policy, sau đó tạo session nếu mọi điều kiện đạt.

Đối với RP, **không cần biết người dùng đã khôi phục passkey từ backup lúc nào** để kiểm tra chữ ký. Nhưng policy có thể xem xét BE/BS và các tín hiệu bổ sung nếu có yêu cầu.

### Những kiểm tra không được bỏ qua

- Challenge mới, ngẫu nhiên và chỉ tiêu thụ một lần.
- Origin chính xác và RP ID hash phù hợp.
- Chữ ký được xác minh bằng public key đã lưu.
- Credential ID thuộc đúng tài khoản hoặc user handle đã được xác định.
- UP/UV đáp ứng policy.
- Account đang active và credential chưa revoke.
- Nếu cần assurance bổ sung, yêu cầu step-up hoặc kiểm tra lại tại thao tác nhạy cảm.

**Đồng bộ không làm mất ràng buộc RP ID.** Một passkey đồng bộ vẫn được dùng để ký assertion dành cho RP hợp lệ; website giả không thể chỉ lấy một assertion bất kỳ rồi dùng cho website thật nếu verifier kiểm tra origin, RP ID và challenge đúng.

## 11. Cross-device authentication: thiết kế an toàn

Cross-device authentication thường dùng cơ chế hybrid để phối hợp browser trên máy tính với authenticator trên điện thoại.

### Thành phần rủi ro

- QR có thể bị chụp hoặc chuyển tiếp; phải ràng buộc phiên và challenge đúng.
- Kênh BLE/proximity có thể không khả dụng hoặc bị gây nhiễu; không nên coi BLE đơn lẻ là bằng chứng danh tính.
- Người dùng có thể bị dụ quét QR do attacker tạo trên một website giả.
- Thông tin RP hiển thị trên điện thoại phải rõ ràng để người dùng biết đang xác thực cho dịch vụ nào.
- Một assertion hợp lệ vẫn cần được kiểm tra tại RP; không tin client desktop tự báo “điện thoại đã xác thực”.

### Nguyên tắc bảo vệ

1. Challenge được tạo bởi RP và gắn với phiên đăng nhập cụ thể.
2. Mã QR/handshake phải khó đoán, có thời hạn và không thể dùng lại.
3. Thiết bị authenticator cần kiểm tra ngữ cảnh RP, không chỉ ký một yêu cầu mù.
4. Dùng giao thức hybrid chuẩn được nền tảng hỗ trợ; không tự thiết kế QR token và BLE handshake thay cho WebAuthn hybrid.
5. Sau khi assertion quay lại, RP xác minh như WebAuthn bình thường.
6. Hủy phiên chờ nếu người dùng cancel, hết hạn hoặc bắt đầu giao dịch mới.

## 12. Vòng đời: thêm, mất, thay và thu hồi thiết bị

Passkey có thể xuất hiện trên nhiều thiết bị, nhưng RP vẫn cần quản lý **credential registration** và trạng thái tài khoản.

| Sự kiện | Việc người dùng/provider thực hiện | Việc RP nên thực hiện |
| --- | --- | --- |
| Thêm thiết bị sync mới | Xác thực tài khoản provider và đáp ứng policy thiết bị | Có thể không cần đăng ký credential mới nếu credential đã sync; theo dõi tín hiệu đăng nhập và risk |
| Đăng ký passkey mới trên thiết bị | Thực hiện WebAuthn registration mới | Lưu credential ID/public key mới, audit và thông báo |
| Mất một thiết bị | Khóa/xóa thiết bị khỏi tài khoản provider hoặc MDM | Đánh giá session, credential và nguy cơ; revoke credential cụ thể nếu cần |
| Mất tài khoản sync provider | Khôi phục theo quy trình của provider | Có thể yêu cầu recovery tại RP; không giả định credential vẫn khả dụng |
| Thay điện thoại | Đồng bộ passkey hoặc đăng ký credential mới | Cung cấp quản lý credential, thông báo và phương án dự phòng |
| Nhân viên nghỉ việc | Thu hồi thiết bị/quyền tổ chức và tài khoản sync được quản lý nếu có | Disable account, revoke session/token/credential theo phạm vi |
| Credential nghi bị lộ | Thu hồi hoặc ngừng sử dụng credential | Chặn assertion từ credential ID đó và yêu cầu đăng ký lại |
| Tài khoản bị disable | Trạng thái tài khoản không còn được phép sử dụng | Từ chối login/refresh/API kể cả passkey còn hợp lệ về chữ ký |

### Một thiết bị mất không nhất thiết đồng nghĩa phải xóa mọi passkey

Nếu passkey được đồng bộ, người dùng có thể còn thiết bị khác hoặc cơ chế phục hồi hợp lệ. Nhưng nếu thiết bị bị mất khi đang mở khóa hoặc có session hoạt động, cần đánh giá:

- Session của RP trên thiết bị đó còn tồn tại không?
- Thiết bị có được bảo vệ bằng screen lock và user verification không?
- Tài khoản sync provider có thể bị truy cập từ thiết bị mất không?
- Có cần revoke credential, session hoặc thiết bị ở provider?
- Có dấu hiệu attacker đã thêm authenticator mới hoặc đổi kênh recovery không?

Không nên xóa credential ở RP một cách tự động chỉ vì người dùng đổi điện thoại; cần xác định credential nào bị ảnh hưởng và giữ trải nghiệm recovery an toàn.

## 13. Khôi phục tài khoản và ranh giới yếu nhất

Passkey giảm phụ thuộc mật khẩu nhưng không loại bỏ account recovery. Người dùng có thể mất mọi thiết bị, mất quyền truy cập tài khoản sync provider hoặc cần thay đổi thiết bị trong môi trường doanh nghiệp.

Một recovery flow cần trả lời:

- Ai có quyền yêu cầu recovery và xác minh bằng chứng gì?
- Có thiết bị/passkey dự phòng không?
- Tài khoản sync provider có cơ chế khôi phục riêng? Mức bảo vệ của nó là gì?
- Nếu phải nhờ hỗ trợ, nhân viên hỗ trợ có thể bị social engineering không?
- Sau recovery, session/token cũ có bị thu hồi không?
- Các passkey và authenticator cũ được giữ, disable hay revoke theo điều kiện nào?
- Có thông báo qua kênh độc lập khi thêm passkey hoặc khôi phục quyền truy cập không?

### Quy trình phục hồi tham khảo

1. Người dùng khai báo mất thiết bị hoặc mất quyền truy cập.
2. Hệ thống kiểm tra các authenticator dự phòng hoặc recovery method đã đăng ký.
3. Nếu cần recovery thủ công, áp dụng xác minh phù hợp với mức rủi ro và chính sách tổ chức; không dựa duy nhất vào thông tin công khai/dễ đoán.
4. Đánh giá dấu hiệu chiếm tài khoản, thay đổi email/phone gần đây, thiết bị mới và session bất thường.
5. Thu hồi session/token và credential bị nghi lộ.
6. Cho phép đăng ký passkey mới sau khi đã xác minh đủ quyền.
7. Thông báo, ghi audit và áp dụng thời gian chờ/giới hạn giao dịch nếu policy yêu cầu.

**Recovery phải mạnh tương xứng với login.** Nếu đăng nhập yêu cầu passkey nhưng recovery chỉ cần mã email dễ bị chiếm, attacker có thể đi vòng qua toàn bộ lợi ích chống phishing.

## 14. Rủi ro bảo mật và cách giảm thiểu

| Rủi ro | Mô tả | Kiểm soát |
| --- | --- | --- |
| **Sync account takeover** | Attacker chiếm tài khoản provider có quyền truy cập backup | Bảo vệ account provider, MFA chống phishing, cảnh báo thiết bị mới, recovery chặt |
| **Device compromise** | Malware hoặc người khác kiểm soát thiết bị đã mở khóa | Screen lock, user verification, cập nhật thiết bị, session protection và revoke |
| **Cross-device phishing** | Người dùng quét QR từ trang giả hoặc chấp nhận nhầm RP | Hiển thị RP context, challenge binding, hybrid flow chuẩn |
| **Credential confusion** | RP gắn credential ID vào sai user hoặc tenant | Ràng buộc user handle/account, kiểm tra credential ownership |
| **Replay** | Assertion/challenge cũ được gửi lại | Challenge single-use, expiry và transaction binding |
| **Session theft** | Attacker lấy cookie/token sau khi passkey login thành công | Cookie an toàn, chống XSS/CSRF, TTL, revoke và reauthentication |
| **Weak recovery** | Hỗ trợ hoặc email fallback làm yếu assurance | Step-up/recovery policy, audit, thông báo và kiểm soát thủ công |
| **Stale credential state** | RP chưa biết credential đã revoke hoặc account bị disable | Trạng thái có thẩm quyền, propagation và kiểm tra tại resource API |
| **Misuse of BE/BS** | Dùng backup flags như bằng chứng tuyệt đối về bảo mật provider | Xem đây là tín hiệu; không suy diễn quá mức |
| **Device inventory drift** | Tổ chức không biết thiết bị nào còn thuộc người dùng/nhân viên | Quản lý lifecycle, offboarding, device inventory và audit |

### Phishing resistance không phụ thuộc vào sync

Passkey đồng bộ và device-bound passkey đều có thể sử dụng WebAuthn để ràng buộc assertion với RP ID/origin. Vì vậy, **syncable không tự động đồng nghĩa phishing-vulnerable**, và device-bound không tự động đồng nghĩa phishing-resistant hơn. Khả năng chống phishing đến từ giao thức, kiểm tra origin/RP ID, challenge và cách triển khai verifier.

Điểm khác biệt giữa hai loại chủ yếu liên quan **khả năng backup, phân phối khóa, ranh giới thiết bị và khôi phục**. Hãy đánh giá các thuộc tính này riêng thay vì dùng một nhãn duy nhất để kết luận an toàn.

## 15. Chính sách cho doanh nghiệp

Doanh nghiệp cần cân bằng trải nghiệm passwordless với quản trị thiết bị, offboarding, compliance và khả năng phục hồi.

### Mẫu chính sách theo nhóm

| Nhóm tài khoản | Chính sách passkey có thể cân nhắc | Kiểm soát bổ sung |
| --- | --- | --- |
| Nhân viên phổ thông | Cho phép synced passkey trên hệ sinh thái được phê duyệt | Quản lý account sync, recovery và thông báo thiết bị mới |
| Quản trị viên hệ thống | Yêu cầu authenticator mạnh; có thể yêu cầu device-bound/security key theo risk policy | Hai authenticator dự phòng, step-up, phê duyệt thay đổi đặc quyền |
| Nhà thầu/BYOD | Cho phép thiết bị cá nhân theo điều kiện | Giới hạn tenant/resource, thời hạn membership, revoke khi hợp đồng kết thúc |
| Workload/service account | Dùng credential máy như chứng chỉ hoặc khóa dịch vụ | Không dùng passkey người dùng thay cho workload identity |
| Tài khoản break-glass | Có credential dự phòng riêng, lưu giữ và giám sát đặc biệt | Kiểm soát nhiều người, alert ngay khi sử dụng, diễn tập định kỳ |

### Offboarding

Khi nhân viên rời tổ chức:

1. Disable tài khoản nội bộ tại nguồn có thẩm quyền.
2. Thu hồi session/token và các credential thuộc phạm vi tổ chức.
3. Thu hồi membership, quyền truy cập ứng dụng, API key và delegated access.
4. Nếu thiết bị được tổ chức quản lý, xử lý theo MDM/device lifecycle.
5. Nếu passkey đồng bộ qua tài khoản cá nhân, không mặc định doanh nghiệp có quyền xóa credential khỏi tài khoản cá nhân; thay vào đó, chặn tài khoản nội bộ và revoke credential tại RP theo policy.
6. Kiểm tra propagation tới các resource API và lưu audit.

**Disable account tại RP vẫn cần thiết**, kể cả khi người dùng còn giữ passkey trong tài khoản đồng bộ cá nhân. Passkey chứng minh quyền sử dụng credential; trạng thái tài khoản nội bộ quyết định nó còn được chấp nhận cho dịch vụ hay không.

## 16. Kiểm thử và đo lường

### Kiểm thử chức năng

| Trường hợp | Cách thử | Kết quả kỳ vọng |
| --- | --- | --- |
| Đăng ký device-bound credential | Tạo passkey trên authenticator không backup | RP lưu credential/public key và BE theo dữ liệu xác minh |
| Đăng ký backup-eligible credential | Tạo passkey trên authenticator có hỗ trợ backup | RP xác minh và lưu BE/BS được báo |
| Đăng nhập từ thiết bị sync khác | Dùng credential đã đồng bộ | Assertion hợp lệ được chấp nhận; không yêu cầu đăng ký lại nếu cùng credential |
| Cross-device login | Laptop hiển thị QR, điện thoại xác thực | Assertion gắn đúng challenge/RP được xác minh |
| Challenge hết hạn | Gửi assertion sau TTL | Từ chối |
| Replay assertion | Gửi lại assertion đã dùng | Từ chối |
| Sai RP ID/origin | Dùng response từ miền khác | Từ chối |
| Credential thuộc user khác | Thử gắn credential ID vào account khác | Từ chối hoặc không tìm thấy credential phù hợp |
| Credential revoked | Thu hồi rồi đăng nhập lại | Từ chối credential |
| Account disabled | Passkey vẫn ký được nhưng account disabled | Không cấp session/token |
| Thiết bị mất | Thu hồi session/credential theo kịch bản | Truy cập bị chặn theo SLA |
| Recovery | Mất thiết bị chính, dùng phương thức dự phòng | Chỉ khôi phục sau khi policy đạt; audit và notification |
| BE/BS transition | Quan sát assertion từ credential backup-eligible qua các trạng thái | Ghi nhận trạng thái đúng; không tự gán mức assurance tuyệt đối |
| Provider unavailable | Mất kết nối hệ sinh thái sync | Hành vi lỗi rõ; không fallback sang luồng yếu ngoài policy |

### Chỉ số vận hành

- **Passkey adoption:** số tài khoản có ít nhất một passkey / tổng tài khoản trong phạm vi.
- **Synced vs device-bound distribution:** số credential theo BE/BS đã xác minh, phân đoạn theo policy và thời gian.
- **Cross-device completion rate:** tỷ lệ giao dịch hybrid hoàn tất trên số giao dịch bắt đầu.
- **Credential revocation latency:** thời gian từ khi revoke tới khi RP từ chối assertion.
- **Recovery rate and abuse:** số recovery hợp lệ, thất bại, ngoại lệ và sự cố chiếm tài khoản.
- **Post-disable acceptance:** số request được chấp nhận sau khi tài khoản đã disable theo mốc hiệu lực.
- **Authentication friction:** thời gian hoàn tất, lỗi thiết bị, tỷ lệ bỏ dở và số lần hỗ trợ.

Không nên tối ưu riêng adoption hoặc completion rate. Nếu recovery yếu hoặc mọi tài khoản quản trị đều được phép dùng phương thức dự phòng kém hơn, tỷ lệ sử dụng passkey cao không đủ chứng minh assurance.

## 17. Tình huống thiết kế: nhân viên đổi điện thoại và đăng nhập laptop

Lan có passkey đồng bộ trong tài khoản của nhà cung cấp nền tảng. Cô dùng passkey trên điện thoại để đăng nhập cổng nội bộ từ laptop. Một tuần sau, điện thoại bị mất và Lan chuyển sang điện thoại mới.

### Phân tích

1. Lần đăng nhập trên laptop là **cross-device authentication**: laptop là client; điện thoại thực hiện assertion.
2. Việc passkey khả dụng trên điện thoại mới là **passkey sync/recovery** trong hệ sinh thái provider.
3. RP kiểm tra assertion, challenge, origin/RP ID, credential ID, user verification và trạng thái tài khoản; RP không cần nhận private key.
4. Khi mất điện thoại, cần thu hồi session trên thiết bị cũ và đánh giá nguy cơ truy cập tài khoản sync provider.
5. Nếu Lan còn thiết bị sync khác hoặc recovery hợp lệ, cô có thể lấy lại passkey theo quy trình provider; RP vẫn cần theo dõi đăng nhập bất thường.
6. Nếu cổng nội bộ đã disable tài khoản Lan, passkey đồng bộ còn hợp lệ vẫn không được cấp session.

### Quyết định thiết kế

- Cổng nội bộ cho phép synced passkey cho đăng nhập thường, nhưng yêu cầu step-up với thao tác thay đổi thông tin thanh toán.
- Admin có thêm security key device-bound dự phòng.
- Mất thiết bị kích hoạt thu hồi session và quy trình thông báo; không tự động xóa mọi credential của người dùng.
- RP ghi nhận BE/BS như metadata nhưng không tuyên bố biết chính xác chất lượng mã hóa backup của provider.
- Account status được kiểm tra tại token issuer và resource API.

## 18. Checklist triển khai

- **Khái niệm:** Đã phân biệt synced passkey, device-bound passkey và cross-device authentication chưa?
- **Authenticator:** Ai giữ private key? Khóa được backup, đồng bộ hay giữ cố định ở đâu?
- **WebAuthn:** RP có kiểm tra challenge, origin, RP ID, chữ ký, credential ownership, UP/UV và trạng thái account không?
- **Backup flags:** Có đọc BE/BS đúng từ authenticator data? Có tránh suy luận quá mức về sync provider không?
- **Provider:** Tài khoản sync provider, thêm thiết bị và recovery được bảo vệ thế nào?
- **Thiết bị:** Có inventory, screen lock, device management, remote revoke hoặc quy trình xử lý thiết bị mất không?
- **Cross-device:** QR/handshake có ràng buộc phiên, hết hạn, chống replay và hiển thị RP context không?
- **Recovery:** Người dùng mất mọi thiết bị có phương án phục hồi đủ mạnh? Có thông báo và thu hồi session cũ không?
- **Authorization:** Tài khoản disabled hoặc thiếu quyền có bị chặn dù assertion đúng không?
- **Doanh nghiệp:** Có offboarding, tenant isolation, break-glass và phân biệt tài khoản cá nhân/tổ chức không?
- **Monitoring:** Có theo dõi adoption, BE/BS, revocation latency, recovery abuse và post-disable acceptance không?
- **Testing:** Đã kiểm thử synced, device-bound, hybrid flow, mất thiết bị, replay, sai origin, disable và provider outage chưa?

### Câu hỏi tự kiểm tra

1. Synced passkey khác device-bound passkey ở khả năng backup và ranh giới tin cậy nào?
2. Vì sao cross-device authentication không đồng nghĩa private key được chuyển từ điện thoại sang laptop?
3. BE và BS biểu thị điều gì? Vì sao RP không thể dùng chúng để kết luận nhà cung cấp sync có mã hóa đầu cuối?
4. Một discoverable credential có nhất thiết là synced passkey không?
5. Passkey đồng bộ có thể chống phishing không? Điều gì trong WebAuthn tạo ra khả năng đó?
6. Nếu tài khoản sync provider bị chiếm, những tài sản và luồng nào có thể bị ảnh hưởng?
7. Tổ chức nên xử lý thế nào khi nhân viên rời công ty nhưng passkey được lưu trong tài khoản cá nhân?
8. Tại sao account disabled vẫn phải bị từ chối dù assertion WebAuthn có chữ ký hợp lệ?

## Kết luận

**Passkey sync và device là hai khía cạnh của vòng đời credential và cách người dùng truy cập từ nhiều thiết bị.** Device-bound passkey gắn với authenticator cụ thể và thường cần dự phòng riêng; synced passkey tăng khả năng sử dụng và phục hồi nhưng đưa tài khoản đồng bộ cùng cơ chế backup vào mô hình tin cậy; cross-device authentication cho phép một thiết bị ký challenge cho phiên đăng nhập đang mở ở thiết bị khác mà không cần chuyển private key sang client. RP vẫn phải xác minh WebAuthn đúng chuẩn, hiểu giới hạn của BE/BS, quản lý trạng thái credential/account, bảo vệ session và thiết kế recovery đủ mạnh. Lựa chọn phù hợp phụ thuộc mức rủi ro, khả năng quản lý thiết bị và nhu cầu phục hồi của hệ thống.
