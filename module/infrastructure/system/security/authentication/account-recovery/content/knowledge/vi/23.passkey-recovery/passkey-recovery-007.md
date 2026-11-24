# Passkey recovery limitations — Giới hạn của khôi phục tài khoản dùng passkey

## 1. Mục tiêu và phạm vi

Trong chương **Passkey Recovery** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, câu hỏi quan trọng là: khi người dùng mất thiết bị, mất quyền truy cập nhà cung cấp passkey hoặc không còn phương tiện xác thực, hệ thống thực sự có thể khôi phục điều gì?

Passkey giúp bảo vệ đường xác thực bằng mật mã khóa công khai. Khả năng lấy lại quyền tài khoản còn phụ thuộc vào cách lưu giữ credential, phương tiện dự phòng, chính sách xác minh và phạm vi sự cố. Một đường đăng nhập tốt vẫn có thể bị vượt qua nếu nhánh khôi phục cho phép người không đủ bằng chứng đăng ký credential mới.

Bài học giúp người đọc:

- Phân biệt khôi phục credential với cấp lại quyền truy cập tài khoản.
- Nhận diện giới hạn của đồng bộ, backup và chuyển hệ sinh thái.
- Đánh giá bằng chứng mà RP có thể kiểm tra và những điều RP chưa thể biết.
- Giải thích vì sao có trường hợp người dùng hợp lệ vẫn không khôi phục được.
- Thiết kế trạng thái, quyền khôi phục và thông báo phù hợp với giới hạn thực tế.
- Kiểm soát credential, session và phương tiện khôi phục sau sự cố.

**Relying Party, viết tắt RP**, là dịch vụ chấp nhận passkey để xác thực tài khoản. **Nhà cung cấp passkey** quản lý nơi lưu và, nếu được hỗ trợ, đồng bộ credential. Một tổ chức có thể đảm nhiệm nhiều vai trò, nhưng các quyền và bí mật của từng vai trò vẫn cần được phân biệt.

Các mô hình, trạng thái và mã giả trong bài là phân tích thiết kế minh họa. Chúng không phải API chuẩn WebAuthn, không xác lập một mức bảo đảm AAL và không thay thế việc đối chiếu chính sách áp dụng cho sản phẩm.

## 2. “Khôi phục passkey” có thể chỉ những kết quả khác nhau

### 2.1. Bốn kết quả cần tách biệt

| Kết quả | Điều thực sự được thực hiện | Điều chưa thể suy ra |
| --- | --- | --- |
| Dùng lại credential còn hoạt động | Một authenticator còn khả dụng tạo được bằng chứng xác thực | Mọi thiết bị mất đã bị vô hiệu hóa |
| Khôi phục bản sao credential | Nhà cung cấp hoặc cơ chế backup đưa credential đã lưu trở lại môi trường sử dụng được | Người dùng đã được cấp một credential độc lập tại RP |
| Khôi phục quyền tài khoản | RP chấp nhận bằng chứng theo chính sách rồi cho phép gắn authenticator mới | Private key cũ đã được tái tạo |
| Khôi phục dữ liệu mã hóa | Có lại khóa hoặc khả năng giải mã dữ liệu ứng dụng | Chỉ đăng nhập lại là đủ để đọc toàn bộ dữ liệu cũ |

Ví dụ, người dùng đăng nhập lại được vào một dịch vụ ghi chú nhưng vẫn mất khóa giải mã các ghi chú riêng tư. Giao diện có thể báo đúng rằng quyền đăng nhập đã phục hồi, đồng thời phải giải thích riêng về dữ liệu chưa thể giải mã.

Ngược lại, passkey được đồng bộ sang máy khác có thể vẫn là cùng credential mà RP đã biết. Số thiết bị sử dụng được tăng lên không đồng nghĩa RP có thêm một binding độc lập để thu hồi riêng.

### 2.2. RP không có nút đặt lại private key cũ

Trong mô hình xác thực khóa công khai, RP sử dụng public key đã đăng ký để kiểm tra bằng chứng từ authenticator. Public key và credential ID không phải bản backup của private key.

Với hệ mật mã và triển khai an toàn, RP không thể tính lại private key từ public key. Backup cơ sở dữ liệu RP giúp phục hồi các binding và trạng thái phía server; nó không bổ sung phần bí mật đã mất ở authenticator.

Nếu bản duy nhất của một private key không thể khôi phục đã mất, khả năng tiếp tục ký bằng key đó cũng mất. Đường còn lại, nếu sản phẩm hỗ trợ, là chứng minh quyền khôi phục để đăng ký một credential khác.

Thiết kế một dịch vụ riêng giữ bản sao bí mật là thay đổi mô hình quản lý khóa và ranh giới tin cậy. Không được mặc định rằng RP có bản sao như vậy chỉ vì dịch vụ hỗ trợ passkey.

## 3. Giới hạn phụ thuộc cách lưu credential

### 3.1. Credential gắn với một thiết bị

Xét một credential chỉ sử dụng được trên authenticator ban đầu và không có cơ chế phục hồi bí mật:

1. Authenticator hỏng hoặc bị mất.
2. RP vẫn còn public key và binding.
3. Người dùng không còn thiết bị có thể tạo assertion bằng credential đó.
4. Việc giữ nguyên hàng dữ liệu phía RP không tạo lại được quyền ký.

Một khóa dự phòng đã đăng ký từ trước giúp người dùng xác thực bằng credential khác. Mua một thiết bị cùng model sau sự cố không mang lại private key của thiết bị cũ.

“Cùng tài khoản nhà cung cấp”, “cùng loại máy” hoặc “cùng vân tay người dùng” cũng không tự biến một authenticator mới thành authenticator đã đăng ký.

### 3.2. Credential có khả năng backup hoặc đồng bộ

Đồng bộ có thể giảm nguy cơ mất quyền truy cập do một thiết bị hỏng. Nó bổ sung các điều kiện phụ thuộc:

- Bản credential cần thiết đã được lưu hoặc đồng bộ thành công.
- Người dùng còn đáp ứng được điều kiện mở kho khóa hay khôi phục của nhà cung cấp.
- Môi trường mới có thể sử dụng nhà cung cấp và credential tương ứng.
- Tài khoản nhà cung cấp chưa bị vô hiệu hóa theo cách ngăn phục hồi.
- Credential vẫn được RP chấp nhận và đáp ứng chính sách hiện tại.

Danh sách này là mô hình phân tích sự cố, không mô tả một quy trình chung cho mọi nhà cung cấp. Có sản phẩm dùng thiết bị tin cậy, bí mật mở khóa, recovery key hoặc tổ hợp điều kiện khác nhau.

Đăng nhập được vào tài khoản cloud và giải mã được kho passkey là hai khả năng cần kiểm tra riêng. Đặc biệt, khi kho được bảo vệ bằng bí mật mà nhà cung cấp không nắm giữ, đặt lại mật khẩu tài khoản có thể chưa đủ để mở dữ liệu cũ.

### 3.3. Nhiều credential chưa chắc tạo dự phòng độc lập

Giả sử RP có hai credential C1 và C2, nhưng cả hai cùng nằm trong một kho P:

~~~text
Tài khoản tại RP
    C1 -> kho P
    C2 -> kho P

Sự cố: người dùng mất khả năng mở kho P
Kết quả có thể xảy ra: cả C1 và C2 đều không sử dụng được
~~~

Hai credential độc lập về khóa vẫn có thể cùng thất bại vì phụ thuộc chung. Hai thiết bị đang dùng cùng kho cũng có thể cùng mất quyền nếu cả hai cần một điều kiện phục hồi đã mất.

Vì vậy, thiết kế dự phòng cần xác định **sự kiện nào làm mất từng đường truy cập**, thay vì chỉ đếm thiết bị hoặc số dòng trong danh sách passkey.

## 4. Cờ backup cung cấp tín hiệu, không cung cấp cam kết phục hồi

WebAuthn có hai cờ trong authenticator data:

| BE | BS | Ý nghĩa |
| --- | --- | --- |
| 0 | 0 | Credential thuộc loại single-device |
| 1 | 0 | Credential có khả năng backup, hiện chưa được báo là đã backup |
| 1 | 1 | Credential có khả năng backup và được báo là đã backup |
| 0 | 1 | Tổ hợp không hợp lệ |

BE là thuộc tính cố định của credential; BS có thể thay đổi. RP cần xử lý các giá trị trong phản hồi đã được xác minh theo giao thức. [W3C WebAuthn, Credential Backup State](https://www.w3.org/TR/webauthn-3/#sctn-credential-backup)

Từ góc độ thiết kế khả năng khôi phục, một lần quan sát BS không trả lời đầy đủ:

- Người dùng còn biết bí mật cần để mở bản backup hay không.
- Nhà cung cấp có cho phép phục hồi trong sự cố cụ thể hay không.
- Thiết bị mới có tương thích với kho credential đó hay không.
- Người dùng sẽ mất bao lâu để lấy lại quyền sử dụng.
- Bản credential có đang nằm ngoài quyền kiểm soát của người dùng hay không.

Không nên dùng một cột `backed_up = true` để hiển thị “chắc chắn lấy lại được tài khoản”. Tín hiệu giao thức và cam kết dịch vụ là hai loại kết luận có phạm vi khác nhau.

Một bản ghi lâu không được cập nhật cũng không mô tả chắc chắn tình trạng kho passkey hiện tại. Thông tin lịch sử có thể hữu ích khi tư vấn thiết lập dự phòng, nhưng không đủ để tự cấp quyền khôi phục.

## 5. Phụ thuộc vào nhà cung cấp và vòng lặp khôi phục

### 5.1. Khả năng phục hồi có nhiều lớp

~~~mermaid
flowchart TD
    A["Muốn truy cập tài khoản tại RP"] --> B["Cần credential được chấp nhận"]
    B --> C["Credential còn trên thiết bị dùng được"]
    B --> D["Credential trong kho đồng bộ"]
    D --> E["Cần mở hoặc phục hồi kho"]
    E --> F["Cần điều kiện tin cậy của nhà cung cấp"]
    A --> G["Hoặc dùng nhánh khôi phục tại RP"]
    G --> H["Cần bằng chứng đã được chính sách chấp nhận"]
~~~

Sơ đồ thể hiện các phụ thuộc có thể gặp. Nó không yêu cầu mọi lượt đăng nhập đều liên hệ nhà cung cấp; một credential đã có sẵn và sử dụng được trên thiết bị có thể tiếp tục hoạt động dù một dịch vụ đồng bộ đang lỗi.

RP có thể điều khiển nhánh khôi phục của mình, nhưng thường không có quyền bỏ qua điều kiện giải mã hoặc khôi phục kho của nhà cung cấp khác.

### 5.2. Vòng lặp giữa email và kho passkey

Ví dụ một cấu hình có vấn đề:

~~~text
Muốn mở kho P:
    cần mã xác nhận gửi đến email E

Muốn đăng nhập email E:
    cần passkey chỉ có trong kho P

Thiết bị duy nhất đã mất:
    không còn bản credential dùng được bên ngoài vòng lặp
~~~

Cả P và E đều có chức năng “khôi phục”, nhưng tổ hợp của chúng vẫn có thể không có điểm bắt đầu.

Một recovery code nằm trong chính kho đang bị khóa cũng không tạo đường thoát. Đường dự phòng chỉ có ích nếu người dùng có thể tiếp cận nó trong sự cố mà nó được dùng để xử lý.

Khi hướng dẫn thiết lập, sản phẩm nên giúp người dùng kiểm tra một câu cụ thể: “Nếu mất quyền vào kho này, tôi lấy bằng chứng cần thiết từ đâu?” Không yêu cầu người dùng gửi vị trí cất mã hoặc bí mật thực tế cho nhân viên hỗ trợ.

### 5.3. Phục hồi nhà cung cấp có thể lan rộng phạm vi sự cố

Nếu một kho chứa passkey cho nhiều RP, quyền mở kho có thể ảnh hưởng nhiều tài khoản. Ngược lại, thay đổi credential ở một RP không xử lý quyền mở kho và credential tại các RP khác.

NIST dành riêng hướng dẫn cho việc bảo vệ sync fabric, bao gồm kiểm soát truy cập và rủi ro từ quá trình khôi phục quyền vào môi trường đồng bộ. [NIST SP 800-63B-4, Syncable Authenticators](https://pages.nist.gov/800-63-4/sp800-63b/syncable/)

Từ đó, khi nghi kho bị chiếm quyền, phạm vi xử lý cần bao gồm cả nguồn đồng bộ. Chỉ tạo passkey mới rồi để nó tiếp tục đi vào kho đang bị người khác kiểm soát có thể tái tạo đường truy cập cho đối tượng tấn công.

## 6. Giới hạn của chuyển thiết bị và chuyển hệ sinh thái

### 6.1. Cross-device authentication cần credential còn dùng được

FIDO mô tả cross-device authentication như cách dùng passkey trên một thiết bị để đăng nhập ở thiết bị khác, có thể qua luồng QR. Đây là sử dụng credential còn tồn tại, không phải tạo lại bí mật đã mất. [FIDO Alliance, Passkeys — Cross-Device Authentication](https://fidoalliance.org/passkeys/)

Hệ quả trong thiết kế:

- Nếu mọi thiết bị giữ credential đều không dùng được, một mã QR mới không tự bổ sung bằng chứng còn thiếu.
- Một lượt đăng nhập qua điện thoại không tự chứng minh laptop đã nhận bản sao passkey.
- Sau khi đăng nhập ở thiết bị mới, việc gắn credential mới vẫn cần quyền quản lý authenticator phù hợp.
- Người dùng cần hiểu họ đang xác thực tài khoản nào và chấp thuận hành động gì.

### 6.2. Chuẩn giao thức không bảo đảm mọi kho trao đổi được dữ liệu

RP hỗ trợ WebAuthn và một kho hỗ trợ nhập hoặc xuất passkey là hai khả năng khác nhau. Khả năng di chuyển còn phụ thuộc nhà cung cấp, nền tảng, phiên bản, loại credential và chính sách tổ chức.

Nếu sản phẩm có chức năng migration, cần kiểm tra cả chiều xuất và chiều nhập. Không dùng một hướng dẫn của một nhà cung cấp để hứa rằng mọi passkey đều chuyển được sang mọi hệ sinh thái.

Với credential không có đường chuyển phù hợp, người dùng có thể cần dùng đường truy cập còn hợp lệ để đăng ký credential tại môi trường mới. Nếu đường truy cập đó cũng mất, việc đổi điện thoại trở thành bài toán khôi phục tài khoản.

### 6.3. Lỗi sử dụng không đồng nghĩa mất bí mật

Không thấy passkey trong giao diện có thể xuất phát từ:

- Đang chọn sai kho hoặc sai tài khoản.
- Client hiện tại không hỗ trợ cách kết nối cần thiết.
- Chính sách thiết bị hoặc tổ chức chặn phương thức đó.
- RP đang yêu cầu một đặc tính mà authenticator không đáp ứng.
- Credential đã bị thu hồi tại RP.

Thông báo lỗi cần hướng người dùng xác định loại sự cố trước khi khởi tạo thay đổi bảo mật. Một timeout đơn lẻ không phải căn cứ tự xóa credential, bỏ user verification hoặc chuyển ngay sang nhánh yếu hơn.

## 7. RP thấy bằng chứng mật mã, không thấy toàn bộ lịch sử kiểm soát

### 7.1. Giới hạn của một assertion hợp lệ

Verifier phía server kiểm tra các điều kiện như challenge, RP ID, origin, chữ ký và yêu cầu hiện diện hoặc xác minh người dùng. Việc kiểm tra phải theo giao thức và chính sách thực tế; một cờ thành công do frontend tự gửi không thay thế verifier. [Google for Developers, Server-side passkey authentication](https://developers.google.com/identity/passkeys/developer-guides/server-authentication)

Sau bước đó, hệ thống vẫn cần quyết định quyền nào được cấp. Chẳng hạn, một assertion hợp lệ cho C1 có thể đủ để đăng nhập thông thường nhưng còn cần kiểm tra freshness, trạng thái sự cố và chính sách trước khi thay toàn bộ phương tiện khôi phục.

Đặc biệt, khi hai bên đều có khả năng dùng cùng một credential đã bị đưa ra ngoài kiểm soát, chữ ký đúng không tự phân biệt bên nào là chủ tài khoản hợp lệ.

### 7.2. User verification không tự tái định danh chủ tài khoản

Trong thiết kế khôi phục, cần tách:

- **Xác minh tại authenticator:** người thao tác đáp ứng cơ chế mở khóa cục bộ.
- **Xác thực với RP:** credential có binding hợp lệ đáp ứng ceremony.
- **Xác minh quyền khôi phục:** bằng chứng được chính sách chấp nhận cho hành động cần làm.
- **Định danh con người:** liên kết người yêu cầu với danh tính đã được thiết lập, nếu dịch vụ có mô hình này.

Không thể dùng câu “đã mở khóa bằng sinh trắc học” để tự điền mọi kết luận còn lại.

Ví dụ, đối tượng đã chiếm quyền mở kho và đưa credential lên thiết bị của họ có thể đáp ứng bước mở khóa cục bộ của thiết bị đó. RP cần xử lý sự cố quyền kiểm soát credential; yêu cầu chạm hoặc mở khóa thêm một lần không tự khắc phục nguồn sự cố.

### 7.3. Metadata không thay bằng chứng quyền tài khoản

Tên người dùng đặt cho passkey, loại kết nối hoặc tên model có thể giúp chọn credential hay giải thích sự cố. Chúng không tự cấp quyền thay đổi binding.

Tương tự, thuộc tính phần cứng của một authenticator mới có thể quan trọng với chính sách chấp nhận credential. Việc sở hữu phần cứng đáp ứng chính sách chưa chứng minh người cầm nó có quyền thêm credential vào tài khoản đích.

Với môi trường cần thuộc tính thiết bị được chứng minh mạnh hơn, phải thiết kế nguồn bằng chứng và cách xác minh phù hợp. Không biến metadata mô tả thành kết luận về danh tính.

## 8. Giới hạn của bằng chứng thay thế

### 8.1. Kênh liên lạc chỉ chứng minh được phạm vi của nó

| Dữ kiện | Kết luận có thể hỗ trợ | Kết luận còn thiếu |
| --- | --- | --- |
| Nhận mã ở email đã thiết lập | Đang có quyền tiếp cận kênh email đó | Kênh chưa bị chiếm và đủ điều kiện cho toàn bộ hành động |
| Xác nhận email mới tự nhập | Đang tiếp cận được email mới | Quan hệ với tài khoản cũ |
| Trả lời thông tin công khai | Biết các dữ kiện về tài khoản | Có quyền quản lý tài khoản |
| Có session cũ | Có thể trình session secret còn được chấp nhận | Session chưa bị đánh cắp và đủ quyền thay authenticator |
| Trình recovery code hợp lệ | Có bằng chứng theo nhánh cấp code | Đã đáp ứng toàn bộ tổ hợp mà chính sách yêu cầu |
| Có ảnh giấy tờ thật | Có thể có bằng chứng về một danh tính | Danh tính đó gắn với tài khoản đích theo cơ sở đáng tin |

Một email link có thời hạn ngắn vẫn có thể bị dùng bởi người đã chiếm email. Chống replay giải quyết việc tái sử dụng token; nó không xác định lại người đang kiểm soát kênh.

Tương tự, gộp nhiều câu hỏi dựa trên cùng dữ liệu đã lộ không tự tạo các nguồn bằng chứng độc lập.

### 8.2. Không thể luôn áp dụng “gửi giấy tờ để lấy lại tài khoản”

Tài khoản dùng bí danh có thể chưa từng được gắn với danh tính pháp lý. Đưa giấy tờ vào sau sự cố có thể chứng minh một người tồn tại, nhưng chưa chứng minh người đó sở hữu tài khoản bí danh đang tranh chấp.

NIST phân biệt recovery theo các phương thức đã bố trí và việc lặp lại identity proofing. Nhánh reproofing cần liên hệ được với danh tính đã thiết lập trước đó; tài khoản chưa identity-proofed không có sẵn đường reproofing này. [NIST SP 800-63B-4, Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b/events/#recovery)

Trong sản phẩm cụ thể, quyền quản trị doanh nghiệp hoặc quy trình pháp lý có thể tạo nguồn thẩm quyền khác. Nguồn đó cần được mô tả và kiểm soát riêng, thay vì ngụy trang thành một assertion passkey hoặc một lần khôi phục thông thường.

### 8.3. Review thủ công có giới hạn

Nhân viên hỗ trợ có thể kiểm tra hồ sơ, phát hiện mâu thuẫn và thực hiện hành động trong thẩm quyền. Họ không thể tạo ra quan hệ sở hữu chắc chắn chỉ từ một câu chuyện thuyết phục.

Hai reviewer cùng xem một dữ kiện yếu có thể giảm nguy cơ một người tự ý bỏ qua quy trình. Cách tổ chức đó không làm dữ kiện trở thành một bằng chứng mạnh hơn về chủ tài khoản.

Chính sách cần có kết quả “chưa đủ bằng chứng” hoặc “không thể khôi phục theo phương thức được hỗ trợ”. Áp lực thời gian, giá trị khách hàng và việc người yêu cầu tỏ ra khẩn cấp không tự tạo quyền đăng ký passkey mới.

## 9. Giới hạn của mức bảo đảm và quyền sau khôi phục

### 9.1. Khôi phục thành công cần được hiểu theo chính sách đã chọn

Một tài khoản có thể cho phép đọc nội dung thông thường sau một nhánh recovery, nhưng yêu cầu điều kiện bổ sung trước khi đổi chủ sở hữu tổ chức, thay thông tin chi trả hoặc quản lý credential đặc quyền.

Các quyền cần được xác định khi thiết kế. Không để frontend tự suy luận rằng trạng thái `recovered` đồng nghĩa mọi hành động nhạy cảm đều được phép.

Nếu một đường thay thế yếu cho phép thêm passkey của người yêu cầu, passkey mới có thể hoạt động đúng giao thức trong những lần đăng nhập sau. Tuy nhiên, gốc cấp quyền sai ở lần enrollment vẫn tồn tại.

Yêu cầu người đó xác thực thêm bằng chính passkey vừa được cấp không tự xác minh lại quyền sở hữu tài khoản ban đầu.

### 9.2. Nhãn “passkey” không tự xác lập AAL

NIST yêu cầu AAL3 sử dụng private key không thể xuất và không cho phép syncable authenticators ở mức này. Việc đáp ứng một đặc tính riêng lẻ chưa đủ để khẳng định toàn bộ luồng đạt AAL3. [NIST SP 800-63B-4, Authentication Assurance Levels](https://pages.nist.gov/800-63-4/sp800-63b/aal/#aal3)

Với bài toán khôi phục, cần đánh giá riêng:

1. Bằng chứng nào cho phép bắt đầu và hoàn tất recovery.
2. Authenticator mới có đặc tính nào được xác minh.
3. Ceremony xác thực mới đáp ứng các điều kiện nào.
4. Session được cấp có quyền và điều kiện sử dụng gì.
5. Hành động nhạy cảm còn yêu cầu gì.

Nếu sản phẩm tự đặt các mức rủi ro nội bộ như “thông thường” và “đặc quyền”, cần dùng đúng tên của chúng. Không tự đổi nhãn thành AAL2 hoặc AAL3 khi chưa đánh giá đầy đủ yêu cầu của khung đó.

## 10. Thu hồi credential có phạm vi hẹp hơn “xóa quyền trên thiết bị”

### 10.1. Credential đồng bộ có thể được dùng từ nhiều nơi

Xét C1 được sử dụng trên điện thoại và laptop thông qua cùng bản credential được đồng bộ:

~~~text
RP:
    C1 -> public key PK1 -> tài khoản A

Các môi trường sử dụng:
    điện thoại có khả năng dùng C1
    laptop có khả năng dùng C1

Thu hồi C1 tại RP:
    RP từ chối C1, bất kể assertion đến từ môi trường nào
~~~

Từ binding C1 đơn thuần, RP không có sẵn một credential ID khác dành riêng cho mỗi bản sao vật lý. Nếu sản phẩm không có cơ chế tin cậy bổ sung để phân biệt thiết bị, nó không thể hứa “chỉ thu hồi bản trên điện thoại mất” bằng cách cập nhật một hàng credential chung.

Metadata của session hay cơ chế quản lý thiết bị có thể cung cấp thêm phạm vi tác động, nhưng cần đánh giá khả năng thực tế của từng cơ chế. Không suy ra tính năng thu hồi từng bản sao từ việc credential có thể đồng bộ.

### 10.2. Các mặt phẳng thu hồi cần xử lý riêng

| Thao tác | Phạm vi trực tiếp | Phần cần xem xét thêm |
| --- | --- | --- |
| Thu hồi binding tại RP | RP ngừng chấp nhận credential | Session và token đã được cấp |
| Xóa mục passkey trong một kho | Thay đổi dữ liệu theo cơ chế kho | Trạng thái binding tại RP và các bản sao khác |
| Đăng xuất tài khoản nhà cung cấp trên thiết bị | Thay đổi quyền tại nhà cung cấp | Session ứng dụng và hiệu lực credential tại RP |
| Thu hồi một session | Ngăn tiếp tục dùng session đó theo cơ chế server | Đường đăng nhập lại bằng credential còn active |
| Thay passkey tại RP A | Thay phương tiện xác thực tại A | Credential tại RP B, RP C và nguồn đồng bộ |

Sản phẩm cần mô tả tác động đã thực thi được, kể cả độ trễ. Một access token còn được chấp nhận ở dịch vụ khác có thể tiếp tục có hiệu lực nếu kiến trúc chỉ kiểm tra chữ ký và thời hạn mà không kiểm tra trạng thái thu hồi.

### 10.3. Khôi phục không thu hồi được dữ liệu đã lộ

Nếu đối tượng đã tải nội dung, xuất bí mật hoặc tạo quyền truy cập khác trước khi sự cố được chặn, thay passkey không lấy lại được các bản dữ liệu họ đã có.

Phạm vi xử lý có thể bao gồm refresh token, API key, ứng dụng được ủy quyền, kênh khôi phục và credential mới xuất hiện trong thời gian bị chiếm quyền. Mỗi loại cần được kiểm tra theo bằng chứng sự cố và chính sách.

Khi đã có căn cứ credential bị lộ, không trì hoãn biện pháp ngừng chấp nhận chỉ để đợi người dùng hoàn tất enrollment thay thế. Quyền báo mất và quyền thu hồi vẫn phải được kiểm tra để tránh người ngoài khóa tài khoản nạn nhân.

## 11. Khôi phục tài khoản không bảo đảm khôi phục dữ liệu mã hóa

Một ứng dụng có thể dùng khóa dữ liệu được bọc bằng bí mật riêng hoặc cơ chế gắn với authenticator. Trong mô hình đó, có hai câu hỏi:

~~~text
Ai được server cho phép truy cập tài khoản?
Ai có thể giải mã dữ liệu đã lưu?
~~~

Server có thể giải quyết câu đầu qua quy trình recovery mà vẫn không có vật liệu mật mã để giải quyết câu sau.

Thiết kế cần xác định trước:

- Khóa dữ liệu được tạo, giữ và backup ở đâu.
- Có cơ chế recovery key, chia sẻ quyền giải mã hoặc escrow được chấp thuận hay không.
- Thêm authenticator mới có thể mở dữ liệu cũ bằng cơ chế nào.
- Reset kho mã hóa có làm mất nội dung cũ hay không.
- Người dùng cần được cảnh báo về mất dữ liệu tại thời điểm nào.

Đây là một phần của thiết kế mã hóa ứng dụng, không phải tính năng tự động của luồng recovery WebAuthn.

Nếu mọi bản khóa giải mã và mọi đường phục hồi hợp lệ đều mất, sản phẩm cần phản ánh khả năng mất dữ liệu vĩnh viễn. Không hứa “hỗ trợ sẽ mở lại toàn bộ” khi mô hình bảo mật không cho phép điều đó.

## 12. Thiết kế quyết định khi có giới hạn khôi phục

### 12.1. Phân loại theo điều còn khả dụng

| Tình huống | Hướng xử lý phù hợp | Giới hạn phải giữ |
| --- | --- | --- |
| Còn credential đáp ứng yêu cầu | Xác thực lại, quản lý phương tiện theo quyền | Kiểm tra credential và session còn được chấp nhận |
| Chỉ mất khả năng đồng bộ, credential cục bộ còn dùng được | Dùng đường cục bộ được hỗ trợ | Không mặc định cần reset tài khoản |
| Cần phục hồi kho nhà cung cấp | Hướng dẫn đến quy trình chính thức tương ứng | RP không tự bỏ điều kiện của kho |
| Có bằng chứng recovery được hỗ trợ | Xử lý theo nhánh và phạm vi đã định | Không tự bỏ các thành phần bằng chứng khác |
| Phụ thuộc xác minh đang lỗi | Chờ, thử lại có kiểm soát hoặc dùng nhánh khác đã hỗ trợ | Không chấp nhận mặc định khi không xác minh được |
| Không còn bằng chứng đủ điều kiện | Giữ trạng thái chưa đủ hoặc kết thúc theo chính sách | Không tự thêm credential chỉ vì không còn cách tiện hơn |
| Có căn cứ kho hoặc thiết bị bị chiếm | Kết hợp recovery với xử lý sự cố | Không coi thay một passkey là kết thúc mọi rủi ro |

### 12.2. Mô hình trạng thái minh họa

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> COLLECTING_EVIDENCE
    COLLECTING_EVIDENCE --> WAITING_FOR_DEPENDENCY: Dịch vụ cần thiết chưa khả dụng
    WAITING_FOR_DEPENDENCY --> COLLECTING_EVIDENCE: Có thể xác minh trở lại
    COLLECTING_EVIDENCE --> RECOVERY_AUTHORIZED: Đủ bằng chứng theo chính sách
    COLLECTING_EVIDENCE --> CANNOT_RECOVER_UNDER_POLICY: Không đáp ứng nhánh được hỗ trợ
    RECOVERY_AUTHORIZED --> REPLACEMENT_PENDING
    REPLACEMENT_PENDING --> COMPLETED: Kiểm tra và commit hợp lệ
    RECOVERY_AUTHORIZED --> EXPIRED
    REPLACEMENT_PENDING --> EXPIRED
    COMPLETED --> [*]
    EXPIRED --> [*]
    CANNOT_RECOVER_UNDER_POLICY --> [*]
~~~

`REQUESTED` chỉ có nghĩa yêu cầu đã được tiếp nhận. Nó không cấp quyền xem danh sách passkey, khóa tài khoản hoặc thay kênh liên lạc.

`WAITING_FOR_DEPENDENCY` khác với kết luận người yêu cầu không đủ điều kiện. Nếu chuyển sang nhánh khác, nhánh đó cần có chính sách được phê duyệt từ trước.

`CANNOT_RECOVER_UNDER_POLICY` là kết quả của một hồ sơ theo chính sách và bằng chứng hiện có. Kết quả này không chứng minh người yêu cầu chắc chắn là kẻ tấn công; người dùng hợp lệ cũng có thể không còn bằng chứng được chấp nhận.

Các trạng thái nội bộ có thể chi tiết hơn phản hồi công khai. Trước khi xác minh quyền, phản hồi cần tránh làm lộ sự tồn tại của tài khoản, loại passkey hoặc phương tiện khôi phục đã thiết lập.

### 12.3. Mã giả quyết định

~~~text
evaluateRecovery(case, now):
    nếu case không còn hiệu lực:
        trả EXPIRED

    nếu có credential còn dùng được và đáp ứng chính sách hành động:
        yêu cầu xác thực theo ceremony hợp lệ
        tiếp tục nhánh quản lý authenticator đã được cấp quyền

    nếu verifier bắt buộc đang không khả dụng:
        trả WAITING_FOR_DEPENDENCY

    kiểm tra evidence gắn với đúng account, case, purpose và thời hạn
    đánh giá các điều kiện của nhánh recovery được hỗ trợ

    nếu evidence chưa đủ:
        trả NEED_MORE_ACCEPTED_EVIDENCE

    nếu không còn nhánh đáp ứng được trong chính sách:
        trả CANNOT_RECOVER_UNDER_POLICY

    tạo quyền recovery giới hạn cho đúng hành động
    trả RECOVERY_AUTHORIZED
~~~

Mã giả thể hiện thứ tự quyết định nghiệp vụ. Nó chưa bao gồm verifier WebAuthn, transaction, xử lý cạnh tranh hoặc cơ chế lưu bí mật của một triển khai hoàn chỉnh.

Không dùng điểm rủi ro thấp như một phép thay thế tự động cho bằng chứng bắt buộc. IP quen thuộc hoặc thiết bị trông giống thiết bị cũ có thể hỗ trợ đánh giá, nhưng còn cần xét khả năng giả mạo, dùng chung hoặc bị chiếm quyền.

## 13. Biện pháp giảm rủi ro và giới hạn của từng biện pháp

### 13.1. Token một lần bảo vệ việc sử dụng quyền đã cấp

Trong một thiết kế recovery, token ngắn hạn có thể trao quyền tiếp tục hồ sơ hoặc đăng ký credential thay thế. Token cần được gắn với account, case, mục đích và thời hạn; việc tiêu thụ cần chống dùng lại và xử lý cạnh tranh.

OWASP khuyến nghị token recovery có tính ngẫu nhiên an toàn, được lưu an toàn, có thời hạn và dùng một lần. Đây là hướng dẫn cho reset mật khẩu; áp dụng sang recovery passkey cần giữ đúng mô hình cấp quyền riêng của luồng mới. [OWASP, Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

Giới hạn cần nhớ: token tốt bảo vệ quyết định đã cấp, nhưng không sửa được một quyết định cấp quyền sai ngay từ đầu.

Ví dụ, nếu hệ thống gửi token cho một email mới do người ngoài tự khai, làm token dài hơn hoặc hết hạn nhanh hơn vẫn chưa chứng minh được quan hệ với tài khoản đích.

### 13.2. Thời gian chờ tạo cơ hội phát hiện

Một khoảng chờ có thể giúp chủ tài khoản nhận cảnh báo hoặc đội vận hành xem xét tín hiệu. Nó không tự tạo thêm bằng chứng về người yêu cầu.

Chính sách cần quy định:

- Khi nào bắt đầu tính thời gian chờ.
- Thay đổi evidence hoặc candidate có yêu cầu đánh giá lại hay không.
- Ai có quyền phản đối, tạm dừng và mở lại hồ sơ.
- Hết thời gian chờ còn cần điều kiện gì để hoàn tất.

Không chuyển từ “chưa đủ bằng chứng” sang “đã xác minh” chỉ vì một bộ đếm đã kết thúc.

### 13.3. Thông báo phụ thuộc kênh còn tin cậy

Gửi cảnh báo có thể giúp phát hiện recovery trái phép. Nếu email nằm trên thiết bị bị mất hoặc chính email đã bị chiếm, người hợp lệ có thể không thấy cảnh báo và đối tượng tấn công có thể đọc được.

Vì vậy, việc gửi thông báo thành công không đồng nghĩa người dùng đã chấp thuận. Cơ chế phản đối cũng cần được bảo vệ để tránh người ngoài hủy hoặc khóa hồ sơ hợp lệ.

### 13.4. Hạn mức giảm lạm dụng, không xác minh chủ tài khoản

Hạn mức theo tài khoản, nguồn yêu cầu, hồ sơ và chi phí xác minh giúp chống dò mã, spam và gây quá tải. Thiết kế cần tránh cho phép một nguồn ngoài làm cạn hạn mức theo cách khóa chủ tài khoản trong thời gian dài.

Một request vượt CAPTCHA hoặc chưa chạm rate limit vẫn chỉ là một request. Kết quả chống bot không thay thế bằng chứng quyền recovery.

### 13.5. Kiểm tra credential mới chỉ chứng minh khả năng sử dụng

Một thiết kế có thể yêu cầu assertion bằng credential vừa đăng ký trước khi kích hoạt. Bước này giúp phát hiện lỗi sử dụng, nhưng người không có quyền cũng có thể dùng thành công passkey do họ tạo.

Trước commit, cần kiểm tra lại ít nhất:

- Quyền recovery còn hiệu lực và đúng phạm vi.
- Candidate là credential đã được đăng ký, kiểm tra và chấp thuận cho hồ sơ này.
- Account và credential version chưa thay đổi ngoài điều được quyết định.
- Không có sự cố hoặc hold có thẩm quyền buộc đánh giá lại.
- Việc tiêu thụ quyền, kích hoạt credential và ghi kết quả có tính nhất quán.

Một session recovery chỉ cần quyền phục vụ luồng đó. Không cấp sẵn toàn bộ session ứng dụng để người yêu cầu đi vào trang cài đặt rồi bỏ qua các điều kiện còn lại.

## 14. Giao diện và hỗ trợ cần phản ánh đúng khả năng

### 14.1. Những lời hứa cần diễn đạt chính xác hơn

| Cách diễn đạt dễ gây hiểu lầm | Diễn đạt phù hợp hơn |
| --- | --- |
| “Passkey luôn lấy lại được khi mất điện thoại” | “Khả năng lấy lại quyền phụ thuộc passkey còn dùng được hoặc phương thức khôi phục bạn đã thiết lập” |
| “Đã backup nên tài khoản chắc chắn an toàn” | “Credential được báo đã backup; hãy kiểm tra bạn còn đáp ứng điều kiện sử dụng hoặc phục hồi kho” |
| “Quét QR để tạo lại passkey đã mất” | “Dùng passkey còn hoạt động trên thiết bị khác nếu phương thức này được hỗ trợ” |
| “Xóa passkey là đăng xuất mọi thiết bị” | “Credential này sẽ bị ngừng chấp nhận; session và token được xử lý theo phạm vi hiển thị” |
| “Đặt passkey mới sẽ lấy lại toàn bộ dữ liệu” | “Quyền đăng nhập và khả năng giải mã dữ liệu có thể cần các bước riêng” |
| “Gửi giấy tờ là hỗ trợ sẽ mở tài khoản” | “Hỗ trợ sẽ kiểm tra những phương thức và bằng chứng được chính sách chấp nhận” |

### 14.2. Hướng dẫn tại thời điểm còn truy cập được

Giảm nguy cơ mất quyền có thể bắt đầu trước sự cố:

1. Giúp người dùng hiểu passkey đang được quản lý ở đâu.
2. Giải thích đường dự phòng nào đã được thiết lập và phạm vi của nó.
3. Khuyến khích kiểm tra khả năng sử dụng phương tiện dự phòng trong điều kiện an toàn.
4. Nhắc kiểm tra phụ thuộc chung giữa email, kho passkey và recovery code.
5. Thông báo rõ các trường hợp sản phẩm không hỗ trợ khôi phục.

Việc kiểm tra dự phòng không nên yêu cầu xóa phương tiện chính. Không thu thập private key, PIN thiết bị hoặc recovery code thô vào ticket chỉ để chứng minh người dùng “đã chuẩn bị”.

### 14.3. Hỗ trợ có thể tiếp tục làm gì khi chưa phục hồi được

Một hồ sơ chưa đủ bằng chứng vẫn có thể được hỗ trợ bằng cách:

- Giải thích phương thức nào sản phẩm thực sự chấp nhận.
- Phân biệt lỗi tương thích, lỗi nhà cung cấp và mất phương tiện xác thực.
- Chỉ dẫn đến quy trình chính thức của nhà cung cấp mà không thu bí mật của kho.
- Tiếp nhận báo cáo sự cố và áp dụng biện pháp trong phạm vi đã có thẩm quyền.
- Giải thích kết quả và đường khiếu nại hoặc bổ sung bằng chứng nếu chính sách cho phép.

Không có cam kết mọi hồ sơ sẽ thành công. Có thể cam kết quy trình rõ ràng, bảo vệ dữ liệu và áp dụng điều kiện nhất quán.

## 15. Ví dụ áp dụng

### 15.1. Điện thoại mất, credential còn trên laptop

Minh có C1 được đồng bộ và vẫn dùng được trên laptop tin cậy. Khi điện thoại mất, Minh đăng nhập bằng C1 trên laptop.

Khả năng đăng nhập còn lại giúp Minh có một đường xác thực. Nó chưa chứng minh điện thoại đã mất khả năng dùng credential, cũng chưa thu hồi session trên điện thoại.

Nếu quyết định sự cố yêu cầu thu hồi C1, RP cần giải thích tác động lên mọi lượt xác thực bằng C1. Minh có thể cần thiết lập một credential khác theo quyền hợp lệ trước hoặc trong kế hoạch thay thế, tùy mức độ khẩn cấp và chính sách.

Khi có căn cứ bị lộ, biện pháp ngừng chấp nhận cần được triển khai kịp thời; sự thuận tiện của việc đăng ký lại không phải lý do tự giữ credential bị lộ hoạt động.

### 15.2. Mất mọi đường truy cập vào cùng một kho

Lan có hai thiết bị và hai credential tại RP, nhưng tất cả đều phụ thuộc kho P. Cả hai thiết bị không còn dùng được; Lan cũng mất bí mật cần để phục hồi P.

RP chỉ còn các public key. Lan không có phương thức recovery khác được chấp nhận và tài khoản chưa được gắn với danh tính có thể reproof.

Trong mô hình này, RP không có bằng chứng đủ để phân biệt Lan với người khác biết thông tin công khai của tài khoản. Kết quả có thể là không khôi phục được theo chính sách, dù Lan là chủ tài khoản thật.

Thêm bước review hoặc kéo dài thời gian chờ không tự tạo đường mật mã hay bằng chứng còn thiếu.

### 15.3. Kho passkey bị chiếm quyền

Hà phát hiện đối tượng đã có quyền dùng kho chứa C1. Hà vẫn giữ một khóa dự phòng độc lập C2 đã đăng ký ở RP.

Luồng xử lý cần xem xét:

1. Dùng C2 và các điều kiện cần thiết để xác minh quyền quản lý.
2. Ngừng credential bị ảnh hưởng theo quyết định sự cố.
3. Kiểm tra session, token, kênh recovery và credential mới được thêm trong thời gian nghi bị chiếm.
4. Khôi phục quyền kiểm soát kho hoặc chọn nơi lưu mới được chính sách chấp nhận.
5. Đăng ký credential thay thế qua quyền hợp lệ và kiểm tra khả năng sử dụng.

Nếu chỉ làm bước 5 và credential mới lại đi vào kho đang bị chiếm, đối tượng có thể tiếp tục có phương tiện truy cập. Phục hồi credential ở RP và phục hồi ranh giới tin cậy của kho phải được phối hợp.

## 16. Các tình huống cần kiểm chứng khi triển khai

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Chỉ còn public key, private key duy nhất đã mất | Không có chức năng tái tạo private key từ dữ liệu RP |
| BE bằng 1, BS bằng 0 | Không hiển thị đã backup hoặc bảo đảm phục hồi |
| BE bằng 0, BS bằng 1 | Phản hồi không hợp lệ được xử lý theo verifier giao thức |
| BS từng bằng 1 nhưng người dùng mất điều kiện mở kho | Không coi tín hiệu backup là bằng chứng đã phục hồi được |
| Hai credential cùng phụ thuộc một kho bị khóa | Nhận diện phụ thuộc chung thay vì đếm là hai đường khả dụng |
| Kho và email tạo vòng lặp recovery | Hướng dẫn phản ánh việc chưa có điểm bắt đầu |
| Dịch vụ đồng bộ lỗi nhưng credential cục bộ còn dùng được | Vẫn xét đường xác thực cục bộ hợp lệ |
| Không còn credential dùng được mà người dùng quét QR mới | Không tự cấp quyền tài khoản |
| Email mới do người yêu cầu tự khai đã được xác nhận | Chưa đủ để thay binding của tài khoản cũ |
| Có giấy tờ nhưng tài khoản chưa gắn danh tính tương ứng | Không tự kết luận quyền sở hữu tài khoản |
| Assertion hợp lệ bằng credential đã thu hồi | Bị từ chối vì trạng thái binding |
| Một credential được dùng trên nhiều thiết bị | Thu hồi phản ánh phạm vi credential, không hứa thu hồi riêng từng bản sao |
| Thu hồi credential nhưng access token cũ còn hiệu lực | Áp dụng cơ chế session/token đã thiết kế và công bố đúng giới hạn |
| Thêm credential mới vào kho vẫn bị chiếm | Không đánh dấu đã xử lý xong nguồn sự cố |
| Hết thời gian chờ nhưng evidence vẫn thiếu | Không tự cấp quyền recovery |
| Nhà cung cấp xác minh bắt buộc đang lỗi | Chờ hoặc dùng nhánh hợp lệ khác, không mặc định chấp nhận |
| Hai request cùng dùng recovery token | Chỉ tác động một lần trong phạm vi được cấp |
| Candidate thay đổi sau khi quyền được cấp | Kiểm tra lại binding và quyết định theo revision phù hợp |
| Chỉ đăng nhập lại được, khóa giải mã dữ liệu vẫn mất | Hiển thị tách biệt quyền tài khoản và khả năng đọc dữ liệu |
| Người yêu cầu không đủ bằng chứng | Không làm lộ chi tiết tài khoản và không cấp session đầy đủ |
| Log và ticket được kiểm tra | Không chứa PIN, private key, session secret hoặc recovery token thô |

## 17. Những điểm cần ghi nhớ

- Passkey hỗ trợ xác thực mạnh; khả năng khôi phục còn phụ thuộc vào mô hình giữ khóa và bằng chứng thay thế.
- Public key tại RP không phải bản sao private key, và backup dữ liệu RP không tạo lại bí mật đã mất.
- Đồng bộ giúp chống một số dạng mất thiết bị nhưng thêm phụ thuộc vào kho, điều kiện mở khóa và quy trình nhà cung cấp.
- Số thiết bị, số credential và tính độc lập của các đường dự phòng là những đại lượng khác nhau.
- Cờ backup, một assertion hợp lệ và một token một lần đều có phạm vi chứng minh riêng.
- Thu hồi credential, thu hồi session, kiểm soát lại kho và khôi phục dữ liệu mã hóa cần được xử lý theo từng phạm vi.
- Khi mọi đường được hỗ trợ đều mất, kết quả không thể khôi phục có thể là giới hạn thực tế của mô hình đã chọn. Sản phẩm cần giải thích giới hạn đó trước sự cố và áp dụng quy trình nhất quán khi sự cố xảy ra.
