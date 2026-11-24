# Platform passkey recovery

## Mục tiêu và phạm vi

Platform passkey recovery là bài toán lấy lại khả năng đăng nhập bằng passkey được sử dụng thông qua nền tảng thiết bị, chẳng hạn điện thoại hoặc máy tính, khi người dùng mất thiết bị, mất quyền mở khóa hoặc mất quyền truy cập nơi lưu passkey. Kết quả có thể là sử dụng lại credential đã tồn tại, hoặc khôi phục tài khoản tại dịch vụ để đăng ký credential thay thế. Hai kết quả này cần những bằng chứng và kiểm soát khác nhau.

Trong chương **Passkey Recovery** của module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, mục tiêu là thiết kế đường lấy lại tài khoản mà không tạo một lối tắt cho kẻ tấn công. Bài học liên kết việc khôi phục passkey với đánh giá rủi ro, token dùng một lần, xác minh danh tính, chống lạm dụng và kiểm soát session khi người dùng mất phương thức xác thực.

Sau bài này, người học cần có khả năng:

- Phân biệt khôi phục quyền sử dụng thiết bị, khôi phục kho passkey của nhà cung cấp và khôi phục tài khoản tại dịch vụ.
- Chọn đường xử lý theo nơi lưu credential và bằng chứng còn sử dụng được.
- Thiết kế quyền đăng ký passkey thay thế, thời gian chờ và giới hạn sau recovery.
- Thu hồi credential và session đúng phạm vi khi thiết bị hoặc tài khoản nền tảng có nguy cơ bị chiếm đoạt.

Các thời hạn và hạn mức bên dưới là ví dụ chính sách cho một dịch vụ giả định, không phải giá trị bắt buộc của WebAuthn hay cam kết của nhà cung cấp nền tảng.

## 1. Ba lớp khôi phục cần tách biệt

Một người dùng nói “tôi mất passkey” có thể đang mô tả ba vấn đề khác nhau.

| Lớp | Tình huống điển hình | Bên kiểm soát | Điều chưa được chứng minh |
| --- | --- | --- | --- |
| Thiết bị và mở khóa cục bộ | Quên PIN thiết bị, hỏng cảm biến, máy không khởi động | Hệ điều hành, authenticator và người dùng | Người liên hệ hỗ trợ đã có quyền trên tài khoản dịch vụ |
| Kho credential hoặc tài khoản nền tảng | Không truy cập được tài khoản đồng bộ, quên bí mật mở khóa kho | Nhà cung cấp passkey hoặc quản trị viên nền tảng | Credential cụ thể đã được phục hồi và dùng thành công |
| Tài khoản tại dịch vụ | Không còn phương thức đăng nhập nào được dịch vụ chấp nhận | Dịch vụ sử dụng WebAuthn, gọi là Relying Party hoặc RP | Người yêu cầu xứng đáng được gắn một credential mới |

Ví dụ, lấy lại được Apple Account hoặc Google Account chưa tự nó chứng minh rằng người dùng đã giải mã được kho passkey. Ngược lại, một điện thoại không hiển thị passkey có thể chỉ đang chọn nhầm tài khoản hoặc nhầm trình quản lý credential.

RP giữ public key và bản ghi liên kết credential với tài khoản. RP không có bản sao private key để gửi lại, cũng không thể tự đặt lại PIN hệ điều hành. “Đặt lại passkey” ở phía RP thường là cho phép đăng ký một cặp khóa mới sau một quy trình cấp quyền phù hợp.

**Ranh giới trách nhiệm:** nhà cung cấp phục hồi khả năng sử dụng credential trong hệ sinh thái của họ; RP quyết định credential hoặc bằng chứng nào được chấp nhận để lấy lại quyền trên tài khoản dịch vụ.

## 2. Xác định credential nào thực sự có thể khôi phục

### 2.1. Platform không đồng nghĩa với có đồng bộ

Platform authenticator gắn với thiết bị đang sử dụng. Cách gắn authenticator và khả năng sao lưu là hai thuộc tính khác nhau; `authenticatorAttachment: "platform"` không cam kết passkey có bản sao phục hồi. [W3C WebAuthn Level 3](https://www.w3.org/TR/webauthn-3/)

Về thiết kế recovery, cần phân biệt hai trường hợp:

- **Credential chỉ gắn với một thiết bị:** nếu authenticator và vật liệu khóa không còn dùng được, RP cần một phương thức xác thực khác hoặc quy trình khôi phục tài khoản để cho phép tạo credential thay thế.
- **Credential có thể dùng trên nhiều thiết bị:** một nhà cung cấp có thể làm credential đã tồn tại khả dụng trên thiết bị khác. Điều kiện truy cập phụ thuộc tài khoản, cơ chế bảo vệ kho và chính sách của nhà cung cấp. Việc có cơ chế đồng bộ vẫn không loại bỏ nhu cầu chuẩn bị phương án mất toàn bộ quyền truy cập. [FIDO Alliance — Synced Passkey Deployment](https://fidoalliance.org/wp-content/uploads/2024/05/Synced-Passkey-Deployment_-Emerging-Practices-for-Consumer-Use-Cases_2024-Final.pdf)

Không chọn nhánh xử lý chỉ bằng câu “người dùng dùng iPhone” hoặc “người dùng dùng Windows”. Một hệ điều hành có thể cung cấp nhiều nơi lưu passkey, và một trình duyệt có thể gọi nhà cung cấp khác với nơi người dùng dự đoán.

### 2.2. Đọc tín hiệu BE và BS đúng giới hạn

Authenticator data có các cờ sau:

| BE | BS | Ý nghĩa |
| --- | --- | --- |
| 0 | 0 | Credential một thiết bị |
| 0 | 1 | Tổ hợp không hợp lệ |
| 1 | 0 | Có khả năng sao lưu, hiện chưa được sao lưu |
| 1 | 1 | Có khả năng sao lưu, hiện được sao lưu |

BE là thuộc tính cố định của credential; BS có thể thay đổi. Các cờ không cho RP biết số bản sao, vị trí thiết bị hoặc lịch sử phục hồi tài khoản nhà cung cấp. [W3C — Credential Backup State](https://www.w3.org/TR/webauthn-3/#sctn-credential-backup)

Hệ quả khi thiết kế là không dùng `BS=1` để bỏ bước xác thực, không dùng `BS=0` để kết luận chắc chắn người dùng đã mất tài khoản, và không gọi thay đổi BS là “sự kiện recovery của nhà cung cấp”. Server chỉ cập nhật tín hiệu từ phản hồi WebAuthn đã được xác minh; không nhận cờ do giao diện tự khai báo.

### 2.3. Không đồng nhất credential với một chiếc máy

Một credential được đồng bộ có thể xuất hiện trên nhiều thiết bị với cùng credential ID. Ngược lại, một tài khoản dịch vụ có thể đăng ký nhiều credential ID độc lập.

Vì vậy:

- Số credential không phải số thiết bị.
- Tên do người dùng đặt như “điện thoại chính” chỉ là nhãn hỗ trợ nhận biết.
- AAGUID có thể giúp nhận biết loại authenticator trong bối cảnh phù hợp, nhưng không phải số định danh duy nhất của máy hay bằng chứng người dùng đã khôi phục danh tính.
- Thu hồi một credential ID tại RP ảnh hưởng đến mọi bản sao sử dụng credential đó, không chỉ máy được ghi trong nhãn.

Đây là cơ sở để tránh giao diện gây hiểu nhầm: nút “thu hồi passkey” cần diễn giải tác động theo credential, còn việc xóa một thiết bị khỏi tài khoản nền tảng thuộc phạm vi nhà cung cấp.

## 3. Chẩn đoán trước khi chuyển sang account recovery

Đừng chuyển ngay từ một lỗi trình duyệt sang quy trình cấp credential mới. Trước hết, phân loại tình huống mà không yêu cầu người dùng cung cấp bí mật nền tảng.

| Người dùng gặp gì? | Hướng xử lý ban đầu | Điều kiện chuyển sang recovery của RP |
| --- | --- | --- |
| Không thấy passkey trong hộp chọn | Kiểm tra đúng tài khoản dịch vụ, hồ sơ trình duyệt và nhà cung cấp credential | Không tìm thấy phương thức còn dùng được sau các bước phù hợp |
| Cảm biến sinh trắc học không hoạt động | Dùng phương thức mở khóa cục bộ thay thế mà nền tảng cho phép | Không thể sử dụng authenticator, đồng thời không còn đường xác thực khác |
| Đổi máy, vẫn còn thiết bị cũ | Đăng nhập bằng credential còn dùng được; cân nhắc đăng ký thêm phương thức độc lập | Thiết bị cũ cũng không còn truy cập được |
| Mất máy, còn truy cập kho đồng bộ | Làm theo quy trình chính thức của nhà cung cấp rồi thử đăng nhập WebAuthn | Kho không thể phục hồi hoặc credential không còn được RP chấp nhận |
| Mất máy chứa credential cục bộ duy nhất | Thử passkey khác, khóa bảo mật hoặc phương án recovery đã chuẩn bị | Không còn phương thức được chấp nhận theo chính sách |
| Nghi thiết bị hoặc tài khoản nền tảng bị chiếm đoạt | Xử lý như sự cố bảo mật, đánh giá credential và session liên quan | Cần tái lập quyền truy cập qua bằng chứng độc lập với miền nghi bị lộ |

Một lỗi như `NotAllowedError` có thể liên quan đến hủy thao tác, hết thời gian hoặc không có credential phù hợp; nó không phải bằng chứng credential đã bị xóa. Khả năng hỗ trợ WebAuthn của trình duyệt cũng không chứng minh passkey cụ thể đang tồn tại.

### 3.1. Ví dụ với hệ sinh thái Apple

Passkey trong iCloud Keychain được bảo vệ và có cơ chế khôi phục keychain của Apple. Các điều kiện recovery thuộc chính sách Apple, không phải một API do RP điều khiển. [Apple — About the security of passkeys](https://support.apple.com/en-ca/102195)

Thiết kế hỗ trợ nên hướng người dùng tới hướng dẫn chính thức và quay về bước đăng nhập của dịch vụ sau khi hoàn tất. Nhân viên RP không được yêu cầu người dùng đọc mã mở khóa thiết bị, mã khôi phục hoặc thông tin đăng nhập Apple cho mình. Ảnh chụp màn hình đăng nhập thành công vào Apple cũng không thay thế assertion của RP.

### 3.2. Ví dụ với Google Password Manager

Google Password Manager có PIN dùng để bảo vệ việc truy cập passkey trên thiết bị mới. Tài liệu Google mô tả khả năng đổi PIN trên một thiết bị đủ điều kiện đã sử dụng kho trước đó. Nếu không còn khôi phục được PIN, thao tác reset passkeys có thể xóa toàn bộ passkey trong kho, buộc đăng ký lại ở từng dịch vụ. [Google — Manage your Google Password Manager PIN](https://support.google.com/chrome/answer/16608973?hl=en)

Do đó, hướng dẫn của RP phải phân biệt “thử khôi phục quyền truy cập kho” với “xóa dữ liệu passkey để thiết lập lại”. Không đưa thao tác xóa kho thành bước sửa lỗi đầu tiên. Dù tài khoản Google đã đăng nhập, RP vẫn cần một assertion hợp lệ hoặc một quy trình khôi phục tài khoản riêng.

### 3.3. Ví dụ với Windows

Microsoft phân biệt nơi lưu cục bộ trên Windows bằng Windows Hello với nơi lưu trong credential manager có đồng bộ. Vì vậy, không viết quy tắc “passkey trên Windows luôn phục hồi được” hoặc “passkey trên Windows luôn chỉ có một bản”. [Microsoft — Create and save a passkey](https://support.microsoft.com/en-us/accounts-billing/security/create-save-passkey)

Với passkey lưu cục bộ trong Windows Hello, tài liệu Chrome cảnh báo mất máy hoặc cài lại hệ điều hành có thể khiến passkey không thể khôi phục. [Google — Manage passkeys in Chrome](https://support.google.com/chrome/answer/13168025?hl=en)

Tình huống này cần được giải quyết bằng phương thức đã đăng ký khác hoặc quy trình cấp credential thay thế của RP. Đặt lại mật khẩu tài khoản nền tảng không phải cam kết phục hồi private key cục bộ đã mất.

## 4. Chọn đường xử lý theo bằng chứng còn lại

Đối với một dịch vụ giả định, có thể dùng ba đường sau. Đây là chính sách thiết kế minh họa, cần điều chỉnh theo mức rủi ro và loại tài khoản.

### Đường A: Vẫn có credential được RP chấp nhận

Người dùng sử dụng passkey từ một thiết bị còn hoạt động, từ khóa bảo mật hoặc từ kho đã phục hồi. RP nhận assertion và thực hiện quy trình xác thực thông thường.

Cross-device authentication cho phép dùng authenticator trên thiết bị khác để tạo phản hồi WebAuthn; nó không tự sao chép passkey vào máy đang mở trang. Sau khi người dùng được xác thực đủ mạnh, dịch vụ có thể đề nghị thiết lập passkey tại nơi phù hợp. [passkeys.dev — Bootstrapping](https://passkeys.dev/docs/use-cases/bootstrapping/)

Nếu không có dấu hiệu xâm nhập và bằng chứng đáp ứng chính sách, không cần gán mọi lần chuyển thiết bị là một vụ account recovery. Nếu có báo mất máy hoặc dấu hiệu rủi ro, cần bổ sung bước quản lý credential và session, thay vì chỉ kết thúc ở đăng nhập thành công.

### Đường B: Không dùng được passkey, còn bằng chứng recovery đã chuẩn bị

Ví dụ: recovery code được lưu riêng, một phương thức xác thực độc lập còn sử dụng được, hoặc quy trình phục hồi do tổ chức thiết lập từ trước.

RP phải kiểm tra bằng chứng đó có đủ quyền cho hành động **đăng ký phương thức xác thực mới** hay chỉ đủ cho một hành động hẹp hơn. Việc chứng minh đang kiểm soát email không mặc nhiên cho phép thay toàn bộ credential của tài khoản đặc quyền.

### Đường C: Không còn bằng chứng đủ mạnh

Chuyển sang xác minh bổ sung hoặc hỗ trợ theo chính sách; chỉ sử dụng quy trình có thể gắn lại người yêu cầu với tài khoản một cách đáng tin cậy. Với tài khoản từng được định danh, có thể áp dụng tái xác minh danh tính tương xứng với rủi ro và dữ liệu đã có.

Không phải dịch vụ nào cũng có căn cứ định danh để kiểm tra giấy tờ. Một tài khoản ẩn danh không tự nhiên trở nên xác minh được chỉ vì người yêu cầu gửi ảnh căn cước. Nếu thiếu căn cứ đáng tin cậy, kết quả hợp lệ có thể là chưa thể phục hồi quyền truy cập.

## 5. Đánh giá rủi ro và sự độc lập của bằng chứng

Điểm nguy hiểm của platform recovery là nhiều bằng chứng có thể nằm trong cùng một miền bị chiếm đoạt.

Ví dụ, kẻ tấn công kiểm soát tài khoản đồng bộ có thể truy cập cả email phục hồi lẫn passkey của một dịch vụ. Yêu cầu “email cộng passkey” trong tình huống này chưa chắc tạo ra hai nguồn tin cậy độc lập. Tương tự, hai bản sao của cùng credential trong cùng kho giúp tăng khả năng truy cập nhưng không tạo ra hai credential độc lập.

Khi lập threat model, hãy vẽ quan hệ phụ thuộc:

~~~text
Tài khoản nền tảng P
  ├─ Kho passkey của dịch vụ R
  ├─ Hộp thư nhận email recovery của R
  └─ Thiết bị nhận thông báo xác nhận

Nếu P bị chiếm đoạt, cả ba đường có thể cùng mất độ tin cậy.
~~~

Các câu hỏi cần giải quyết bằng chính sách nội bộ gồm:

- Bằng chứng đang dựa vào một thiết bị vừa báo mất hay một kho nghi bị lộ không?
- Recovery code có được lưu tách khỏi miền đó không? Server có dữ liệu để khẳng định hay chỉ có lời khai?
- Người yêu cầu vừa thay đổi email, số điện thoại hoặc thêm credential khác không?
- Tài khoản có quyền quản trị, dữ liệu nhạy cảm hoặc quyền cấp truy cập cho người khác không?
- Có session bất thường, nhiều yêu cầu recovery đồng thời hoặc báo cáo phủ nhận từ chủ tài khoản không?

IP quen thuộc, cookie cũ và tên thiết bị là tín hiệu hỗ trợ. Chúng có thể điều chỉnh việc yêu cầu thêm bằng chứng, nhưng không thay thế phép kiểm tra quyền khi gắn credential mới. Cookie phiên bị đánh cắp cũng không trở thành bằng chứng mạnh chỉ vì được dùng từ một thiết bị từng thấy.

Một giới hạn quan sát cần ghi rõ: WebAuthn thông thường không cung cấp cho RP một thông báo đáng tin cậy rằng tài khoản nhà cung cấp vừa được phục hồi. Nếu có tích hợp bổ sung, phải xác định nguồn, độ xác thực và quyền sử dụng dữ liệu đó; nếu không có, không suy diễn lịch sử recovery từ BE, BS hay tên trình quản lý.

## 6. Luồng khôi phục tại RP

### 6.1. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A[Người dùng không đăng nhập được bằng passkey] --> B{Còn credential dùng được?}
    B -->|Có| C[Xác minh assertion tại RP]
    C --> D{Hợp lệ và đáp ứng chính sách?}
    D -->|Có| E[Đăng nhập và rà soát credential, session nếu cần]
    D -->|Không| F[Thử phương thức khác được phép]
    B -->|Chưa rõ| G[Kiểm tra tài khoản, nơi lưu và hướng dẫn nền tảng]
    G --> H{Dùng lại được credential?}
    H -->|Có| C
    H -->|Không| F
    B -->|Không| F
    F --> I{Đủ bằng chứng recovery?}
    I -->|Không| J[Xác minh bổ sung hoặc chưa thể phục hồi]
    I -->|Có| K[Cấp quyền recovery có giới hạn]
    K --> L[Đăng ký credential thay thế ở trạng thái pending]
    L --> M[Chứng minh sử dụng được credential mới]
    M --> N{Đủ điều kiện kích hoạt theo chính sách?}
    N -->|Chưa| O[Chờ hoặc chuyển đánh giá bổ sung]
    O --> N
    N -->|Có| P[Kích hoạt, thu hồi theo phạm vi, tạo session mới]
    P --> Q[Áp dụng giới hạn sau recovery và thông báo]
~~~

Các bước “pending” và thời gian chờ trong sơ đồ là mô hình ứng dụng đề xuất. WebAuthn không tự quản lý quy trình account recovery này.

### 6.2. Bắt đầu recovery mà không làm lộ tài khoản

Endpoint bắt đầu recovery nên trả thông điệp trung tính như: “Nếu thông tin phù hợp, bạn sẽ nhận được hướng dẫn tiếp theo.” Không trả về danh sách tên passkey, tài khoản nền tảng hoặc số lượng thiết bị cho người chưa được xác thực.

Áp dụng hạn mức theo nhiều chiều: tài khoản đích ở dạng định danh nội bộ phù hợp, nguồn yêu cầu và tổng mức sử dụng dịch vụ. Hạn mức theo IP đơn lẻ dễ bị né tránh và có thể chặn nhầm nhiều người dùng sau cùng một mạng.

Không vô hiệu hóa passkey hay session đang hoạt động chỉ vì có người nhập email để yêu cầu recovery. Kẻ tấn công có thể dùng chính hành vi này để gây từ chối dịch vụ cho chủ tài khoản.

### 6.3. Tạo quyền recovery hẹp và ngắn hạn

Sau khi bằng chứng đạt yêu cầu, server tạo một recovery grant gắn với:

- Tài khoản đích và recovery attempt cụ thể.
- Mục đích, ví dụ `REGISTER_REPLACEMENT_PASSKEY`.
- Kết quả đánh giá bằng chứng và phiên bản chính sách đã áp dụng.
- Thời điểm hết hạn, trạng thái sử dụng và phiên bản bảo mật của tài khoản.
- Recovery session hoặc client context được bảo vệ để giảm tráo đổi luồng.

Ví dụ, opaque token tạo bằng bộ sinh số ngẫu nhiên mật mã với 32 byte entropy, TTL 10 phút, chỉ lưu digest hoặc HMAC phía server. Không đặt token vào log hoặc URL được chuyển tiếp sang bên thứ ba. Nếu token đi qua liên kết email, trang nhận cần kiểm soát referrer, tránh tài nguyên bên thứ ba, và trao đổi token sang trạng thái recovery được bảo vệ trước các thao tác tiếp theo.

Phải tách token dùng một lần, recovery session và challenge WebAuthn. Chúng có thời hạn và mục đích khác nhau. Tiêu thụ grant nguyên tử tại bước hoàn tất hành động mà grant cho phép; các challenge đăng ký/xác thực cũng chỉ được dùng cho đúng ceremony của chúng. Việc gửi lại yêu cầu bắt đầu không được vô hạn kéo dài hiệu lực bằng chứng.

Nếu thời gian chờ dài hơn TTL của grant đăng ký, tiêu thụ grant đó khi hoàn tất tạo credential pending và lưu trạng thái chờ bền vững ở server. Sau thời gian chờ, kiểm tra lại bằng chứng, recovery context và chính sách trước khi cấp một grant kích hoạt riêng, chẳng hạn `ACTIVATE_REPLACEMENT_PASSKEY`, có TTL ngắn. Không giữ token đăng ký 10 phút hợp lệ suốt thời gian chờ 24 giờ. Bằng chứng quá cũ phải được xác minh lại theo chính sách.

### 6.4. Giới hạn quyền trong lúc khôi phục

Recovery session chỉ được đi vào các endpoint phục hồi cần thiết. Nó chưa được đổi email chính, cấp API key, xuất dữ liệu nhạy cảm, xóa mọi MFA hoặc thực hiện thao tác quản trị.

Một session cũ còn mở có thể giúp điều hướng người dùng, nhưng hành động thêm credential cần xác thực lại hoặc bằng chứng thay thế đủ mạnh. Reauthentication cho hành động nhạy cảm phải gắn với đúng tài khoản và không để người dùng âm thầm đổi tài khoản trong ceremony. [passkeys.dev — Reauthentication](https://passkeys.dev/docs/use-cases/reauth/)

Áp dụng kiểm tra quyền phía server, bảo vệ CSRF khi dùng cookie và kiểm tra origin theo mô hình triển khai. Không chỉ ẩn nút ở giao diện. Các API đăng ký passkey thông thường cũng phải chịu cùng chính sách, nếu không kẻ tấn công có thể đi vòng qua endpoint recovery.

### 6.5. Đăng ký và xác nhận credential thay thế

Tài khoản nhận credential phải lấy từ recovery context đã được server xác minh. Không nhận một `userId` tùy ý trong body rồi dùng nó để quyết định chủ sở hữu public key.

Ở ceremony đăng ký, server phát challenge mới, khóa vào attempt và account đích, yêu cầu user verification phù hợp với chính sách. Một thư viện WebAuthn được duy trì phải kiểm tra phản hồi, bao gồm challenge, origin, RP ID, loại ceremony và các cờ cần thiết. Khóa công khai chỉ được lưu sau xác minh thành công.

RP cũng phải kiểm tra credential ID không đang thuộc tài khoản khác. Không tự chuyển credential giữa các tài khoản hoặc tạo một tài khoản mới chỉ vì thấy email hay `userHandle` khác với dự kiến. Các quy tắc liên kết tài khoản phải độc lập với thao tác đăng ký passkey.

Trong mô hình minh họa, credential mới được lưu là `PENDING_RECOVERY`. Sau đó người dùng thực hiện một assertion riêng bằng credential này để chứng minh có thể dùng nó. Credential pending chỉ được phép tham gia ceremony xác nhận recovery; đường login thông thường phải từ chối hoặc chuyển về đúng recovery context.

**Điểm then chốt:** assertion bằng credential vừa tạo chứng minh khả năng sử dụng khóa mới, không chứng minh quyền sở hữu tài khoản trước khi recovery. Kẻ tấn công cũng có thể tự tạo một passkey hoàn toàn hợp lệ. Mức tin cậy của việc khôi phục vẫn bắt nguồn từ bằng chứng đã cấp quyền đăng ký.

### 6.6. Kích hoạt theo chính sách đã định

Đối với đường dùng credential độc lập còn hợp lệ, dịch vụ có thể cho phép hoàn tất sớm nếu mức xác thực đạt yêu cầu. Đối với đường dựa vào bằng chứng yếu hơn hoặc có dấu hiệu rủi ro, có thể giữ thời gian chờ, yêu cầu phê duyệt bổ sung hoặc không chấp nhận recovery.

Ví dụ chính sách ứng dụng: chờ 24 giờ trước khi credential thay thế được dùng cho quyền đầy đủ sau một quy trình hỗ trợ thủ công. Thời gian này chỉ tạo cơ hội phát hiện và phản ứng; nó không tự làm bằng chứng ban đầu trở nên đáng tin cậy hơn.

Ngay khi quyền đăng ký thay thế được cấp hoặc credential được tạo, gửi thông báo tới các kênh đã được thiết lập trước sự kiện, phù hợp với chính sách. Không chỉ thông báo tới một địa chỉ vừa được người yêu cầu cung cấp. Thông báo cần nêu hành động, thời điểm có hiệu lực và cách báo cáo bất thường để khoảng chờ có giá trị phát hiện thực tế.

Điều kiện kích hoạt cần được đánh giá lại ở server: grant còn hiệu lực, bằng chứng chưa bị phủ nhận, thời gian chờ đã đủ, tài khoản chưa chuyển sang trạng thái sự cố khác và credential mới đã được xác nhận. Một đăng nhập bằng chính credential pending không được tự động xóa các điều kiện này.

## 7. Mô hình trạng thái và tính nguyên tử

### 7.1. Trạng thái tối thiểu

~~~text
RecoveryAttempt:
  INITIATED -> EVIDENCE_VERIFIED -> ENROLLMENT_AUTHORIZED
            -> CREDENTIAL_PENDING -> READY_TO_ACTIVATE -> COMPLETED

  Trạng thái kết thúc khác: EXPIRED, CANCELLED, REJECTED

ReplacementCredential:
  PENDING_RECOVERY -> ACTIVE
                  -> REVOKED khi attempt hết hạn hoặc bị hủy

Account:
  ACTIVE hoặc RECOVERY_RESTRICTED hoặc SECURITY_HOLD
~~~

Attempt bị hủy hoặc hết hạn phải làm credential pending liên quan mất khả năng kích hoạt. Không để một public key “mồ côi” tồn tại rồi vô tình được đường đăng nhập coi là active.

Không nhất thiết chuyển toàn bộ tài khoản sang restricted ngay khi nhận yêu cầu công khai. Chỉ đặt trạng thái hạn chế tài khoản khi có quyết định bảo mật đủ căn cứ; trước đó giới hạn recovery session là phù hợp hơn. Cách này tránh việc bất kỳ ai cũng có thể gây gián đoạn tài khoản bằng một email.

### 7.2. Dữ liệu cần lưu

| Bản ghi | Trường quan trọng | Mục đích |
| --- | --- | --- |
| Recovery attempt | Account ID, trạng thái, bằng chứng tham chiếu, policy version, expiresAt, readyAt | Khóa quyền vào một quy trình cụ thể |
| Recovery grant | Token digest/HMAC, purpose, account ID, attempt ID, security version, consumedAt | Chống dùng sai mục đích, replay và sử dụng sau biến động bảo mật |
| WebAuthn ceremony | Challenge, loại, account ID, attempt ID, expiresAt, consumedAt | Chống tráo ceremony và dùng lại phản hồi |
| Credential | Credential ID, public key, trạng thái, recovery attempt ID, BE/BS đã xác minh, thời điểm tạo và dùng | Kiểm soát credential nào được phép xác thực |
| Account security state | Phiên bản bảo mật, mức hạn chế, trạng thái sự cố | Buộc mọi đường xác thực tuân theo cùng chính sách |
| Audit/outbox | Mã sự kiện, phạm vi thu hồi, thời gian, kết quả thông báo | Theo dõi thay đổi và gửi tác vụ sau commit |

Không lưu PIN nền tảng, mã sinh trắc học hay private key trong các bản ghi này. Dữ liệu chứng minh danh tính, nếu có, cần giới hạn mục đích, thời gian lưu và quyền xem phù hợp.

### 7.3. Mã giả hoàn tất recovery

Đoạn dưới mô tả ranh giới giao dịch của ứng dụng, không phải thư viện WebAuthn có thể chép để chạy ngay. Grant trong hàm này có mục đích kích hoạt credential thay thế, khác với grant đăng ký đã được tiêu thụ trước đó. Việc kiểm tra ceremony và ghi nhận bằng chứng sử dụng credential mới diễn ra ở bước trước bằng thư viện phù hợp.

~~~java
RecoveryResult completeRecovery(RecoveryContext context) {
    return transaction.execute(() -> {
        // Thứ tự khóa cần thống nhất ở mọi đường thay đổi bảo mật.
        Account account = accounts.lock(context.accountId());
        RecoveryAttempt attempt = attempts.lock(context.attemptId());
        RecoveryGrant grant = grants.lock(context.grantId());
        Instant now = clock.instant();

        requireBoundToSameAccountAndAttempt(context, account, attempt, grant);
        requireExpectedSecurityVersion(account, grant);
        requireValidUnconsumedGrant(grant, now);
        requireActivationState(attempt);

        Credential replacement = credentials.lock(attempt.replacementId());
        requirePendingCredentialOwnedBy(replacement, account, attempt);
        requireValidatedPossessionProof(attempt, replacement);

        // Đánh giá từ bằng chứng recovery ban đầu và trạng thái hiện tại.
        // Không nâng độ tin cậy nhờ chính passkey vừa được tạo.
        Decision decision = policy.evaluateActivation(account, attempt, now);
        requireApprovedAndWaitingPeriodSatisfied(decision, attempt, now);

        grant.consume(now);
        replacement.activate(now);
        credentials.revokeAffected(decision.revocationScope(), now);
        account.advanceSecurityVersion();
        account.applyPostRecoveryRestrictions(decision.restrictions());
        sessions.invalidateAccordingTo(decision.sessionScope(), account);
        attempt.complete(now);

        outbox.appendRecoveryCompleted(account, attempt, decision);
        return RecoveryResult.committed(account.securityVersion(),
                                        decision.restrictions());
    });
}
~~~

Các hàm kiểm tra phải kiểm soát cả giá trị và trạng thái. Chẳng hạn, `requireValidatedPossessionProof` chỉ chấp nhận bằng chứng server đã ghi nhận từ đúng ceremony, không chấp nhận một cờ `verified=true` do client gửi.

Phạm vi thu hồi phải loại trừ credential thay thế vừa được duyệt và được xác định bằng chính sách server. Toàn bộ thao tác tiêu thụ grant, kích hoạt credential, cập nhật phiên bản bảo mật và hoàn tất attempt phải cùng thành công hoặc cùng rollback. Hai yêu cầu hoàn tất đồng thời không được tạo ra hai quyền kích hoạt độc lập.

Nếu request bị mất phản hồi sau commit, server có thể trả trạng thái hoàn tất cho đúng recovery context khi retry, nhưng không tái sử dụng grant để tạo một thay đổi bảo mật mới. Chỉ phát session đăng nhập mới sau khi giao dịch thành công; session phải mang đúng giới hạn hiện hành.

Thông báo hoặc tác vụ ở hệ thống ngoài nên đi qua outbox bền vững để có thể retry. Không báo rollback một thay đổi đã commit chỉ vì gửi email tạm thời thất bại.

## 8. Thu hồi credential và session sau recovery

### 8.1. Chọn đúng phạm vi thu hồi

| Sự cố | Phạm vi cần cân nhắc tại RP | Việc phải làm ở nơi khác |
| --- | --- | --- |
| Mất một máy, credential được đồng bộ, chưa có dấu hiệu bị lộ | Đánh giá có cần giữ hay thay credential dùng chung; kiểm tra session của máy mất | Khóa hoặc xóa thiết bị theo khả năng của nền tảng |
| Mất thiết bị chứa credential cục bộ duy nhất | Thu hồi credential cũ sau khi có đường thay thế đủ tin cậy; xử lý session liên quan | Quy trình bảo vệ thiết bị bị mất |
| Kho đồng bộ hoặc tài khoản nền tảng nghi bị chiếm đoạt | Xác định và thay các credential có thể nằm trong kho; xem xét mọi session có nguồn gốc liên quan | Bảo vệ lại tài khoản nhà cung cấp và các thiết bị được tin cậy |
| Phát hiện credential do kẻ tấn công thêm | Thu hồi credential trái phép; đánh giá các thay đổi bảo mật phát sinh cùng thời điểm | Điều tra nguồn xâm nhập và quyền truy cập liên quan |

RP không thể xóa một bản sao private key khỏi riêng chiếc máy bị mất bằng cách cập nhật cơ sở dữ liệu. Nếu credential đồng bộ bị thu hồi ở RP, các bản sao của credential đó đều không còn được RP chấp nhận. Khi vẫn cần cho người dùng truy cập qua kho đó, phải cân nhắc tạo credential thay thế sau khi miền lưu trữ đã được bảo vệ lại.

Nếu nơi lưu mới vẫn là kho đang bị chiếm đoạt, việc tạo một credential ID mới có thể chỉ đưa khóa mới trở lại tay kẻ tấn công. Trong trường hợp này cần môi trường đã được làm sạch hoặc phương thức độc lập, thay vì chỉ xoay credential trên cùng miền rủi ro.

### 8.2. Thu hồi credential chưa thu hồi session

Một access token hoặc cookie được cấp trước khi thu hồi credential có thể tiếp tục hoạt động nếu tầng kiểm tra session không biết thay đổi đó. Vì vậy, chính sách cần bao gồm session web, refresh token, phiên trên ứng dụng và các quyền dài hạn liên quan đến sự cố.

Có thể tăng `securityVersion` của tài khoản và buộc các session cũ không còn đáp ứng phiên bản hiện tại. Tuy nhiên, cách này chỉ có hiệu lực nhanh khi API và dịch vụ tiêu thụ token thực sự kiểm tra phiên bản hoặc một trạng thái thu hồi tương đương. JWT chỉ được kiểm tra chữ ký và thời hạn sẽ không tự biết biến động bảo mật.

Sau recovery, tạo session ID mới để tránh session fixation. Nếu áp dụng giới hạn tài khoản, mọi session mới cũng phải chịu giới hạn đó; không chỉ gắn cờ vào recovery session. Nếu không, người dùng hoặc kẻ tấn công có thể đăng nhập lại bằng credential mới rồi thoát khỏi thời gian hạn chế.

### 8.3. Các thao tác có thể cần chặn tạm thời

Tùy dịch vụ, giới hạn sau recovery có thể áp dụng cho xuất toàn bộ dữ liệu, cấp quyền quản trị, tạo API key, thay kênh recovery hoặc xóa phương thức xác thực cuối cùng còn lại. Server phải xác định rõ điều kiện kết thúc giới hạn.

Không dùng quy tắc “đăng nhập bằng passkey bất kỳ là gỡ hạn chế” nếu passkey vừa được tạo trong chính recovery đó. Việc gỡ hạn chế phải dựa trên điều kiện đã đặt trước: bằng chứng độc lập đủ mạnh, thời gian chờ kết hợp đánh giá rủi ro, hoặc phê duyệt theo quy trình phù hợp.

## 9. Chống lạm dụng và thiết kế trải nghiệm

### 9.1. Đe dọa cần xử lý

| Cách lạm dụng | Kiểm soát cụ thể |
| --- | --- |
| Thử recovery code hoặc token hàng loạt | Entropy đủ lớn, giới hạn lần thử, thời hạn, phát hiện nhiều nguồn và không log bí mật |
| Dùng grant của A để gắn credential vào B | Bind account, attempt, purpose và ceremony ở server; bỏ qua account ID không được cấp quyền từ client |
| Lặp lại phản hồi đăng ký/xác thực cũ | Challenge mới, TTL, kiểm tra ceremony và tiêu thụ nguyên tử |
| Dùng recovery session gọi API thêm passkey thông thường | Cùng chính sách phân quyền trên mọi endpoint tạo credential |
| Chiếm session cũ rồi tự đăng ký credential | Xác thực lại cho hành động nhạy cảm, giới hạn độ mới và mức tin cậy của bằng chứng |
| Gây khóa tài khoản bằng nhiều yêu cầu phục hồi | Hạn mức yêu cầu và thông báo; không thu hồi credential từ một yêu cầu chưa xác minh |
| Giả hỗ trợ để xin PIN hoặc bí mật kho | Hướng dẫn về trang chính thức, thông điệp hỗ trợ nhất quán, không thu thập bí mật nền tảng |
| Dùng passkey vừa tạo để vượt thời gian chờ | Trạng thái credential và giới hạn tài khoản được kiểm tra tại server cho mọi session |

Một liên kết “không phải tôi” trong thông báo cần được thiết kế theo quyền hẹp. Nếu chỉ cần truy cập email là có thể xóa credential hoặc kiểm soát vĩnh viễn tài khoản, thông báo đã trở thành một đường recovery nguy hiểm. Có thể ghi nhận báo cáo và chuyển sang đánh giá phù hợp thay vì trao ngay quyền quản trị tài khoản.

### 9.2. Nội dung giao diện cần rõ ràng

Trước recovery, hiển thị những lựa chọn có thể hành động: dùng passkey khác, dùng khóa bảo mật, kiểm tra nơi đã lưu passkey hoặc bắt đầu khôi phục tài khoản. Không đẩy người dùng sang hàng loạt thao tác reset khi chưa biết credential nằm ở đâu.

Sau đăng ký thay thế, có thể thông báo:

> Bạn đã thiết lập passkey thay thế. Một số thay đổi bảo mật đang được giới hạn đến thời điểm hiển thị bên dưới. Hãy kiểm tra các phương thức đăng nhập và phiên hoạt động của tài khoản.

Nếu người dùng đang định thu hồi credential đồng bộ, thông báo cần cho biết các thiết bị dùng cùng passkey có thể cùng mất khả năng đăng nhập. Không hứa “chỉ đăng xuất điện thoại bị mất” khi hệ thống chỉ biết credential ID.

Nếu cần chuyển sang nhà cung cấp nền tảng, giải thích đúng phạm vi: người dùng đang lấy lại quyền truy cập nơi lưu passkey, rồi phải quay lại đăng nhập hoặc hoàn tất recovery tại dịch vụ. Liên kết hỗ trợ nên trỏ tới miền chính thức và được duy trì theo sản phẩm thực tế.

### 9.3. Chuẩn bị trước khi sự cố xảy ra

Khi người dùng đã xác thực đủ mạnh, dịch vụ có thể đề nghị bổ sung phương thức truy cập dự phòng. Mục tiêu là giảm phụ thuộc vào một máy hoặc một kho duy nhất, không phải chỉ tăng số lượng bản sao trong cùng kho.

Ví dụ, một credential dự phòng trên authenticator độc lập và recovery code lưu riêng có giá trị khác với hai điện thoại cùng dùng một tài khoản đồng bộ. Dịch vụ nên giải thích sự khác biệt này, đồng thời tránh khẳng định đã biết nơi người dùng cất recovery code nếu không có bằng chứng.

## 10. Ba tình huống minh họa

### 10.1. Mất điện thoại, còn máy tính truy cập được kho

Lan mất điện thoại nhưng vẫn dùng được passkey của dịch vụ trên máy tính. Lan đăng nhập bằng assertion được RP xác minh, sau đó xác thực lại khi quản lý phương thức đăng nhập nếu chính sách yêu cầu.

RP không tạo bản ghi credential mới chỉ vì Lan chuyển thiết bị. Lan kiểm tra session liên quan đến điện thoại đã mất và xử lý thiết bị trong tài khoản nền tảng. Nếu quyết định thu hồi credential đồng bộ hiện tại, Lan cần chuẩn bị credential thay thế phù hợp vì thao tác thu hồi ảnh hưởng đến mọi bản sao của credential đó.

Bài học: mất thiết bị không luôn đồng nghĩa mất credential; khôi phục truy cập và xử lý sự cố mất thiết bị có thể cùng cần thực hiện.

### 10.2. Cài lại máy, passkey cục bộ không còn dùng được

Minh từng chỉ tạo passkey trong Windows Hello trên một máy và không còn dùng được credential sau khi cài lại. Minh vẫn có recovery code đã tạo trước đó, lưu ngoài máy.

Dịch vụ xác minh recovery code theo chính sách, cấp grant đúng tài khoản, cho tạo credential pending rồi xác nhận sử dụng. Việc kích hoạt, thu hồi credential cũ và kiểm soát session tuân theo mức rủi ro của tài khoản. Nếu mã dự phòng không đủ cho tài khoản đặc quyền, hệ thống yêu cầu bằng chứng bổ sung trước khi kích hoạt.

Bài học: đây là cấp credential thay thế sau account recovery. RP không phục hồi private key cũ từ public key hay mật khẩu tài khoản hệ điều hành.

### 10.3. Tài khoản đồng bộ nghi bị chiếm đoạt

Hà báo rằng email nền tảng và kho passkey có thể đã bị người khác truy cập. Kẻ tấn công gửi yêu cầu recovery và có thể đọc liên kết qua email.

Trong tình huống này, email và passkey trong cùng miền nghi bị lộ không được tính thành hai bằng chứng độc lập. RP cần một đường phục hồi có căn cứ khác phù hợp với tài khoản. Sau khi xác minh, việc tạo credential mới phải diễn ra trên môi trường đủ tin cậy; chỉ tạo khóa mới trong kho chưa được bảo vệ lại không giải quyết nguyên nhân.

RP rà soát credential trái phép, session và các thay đổi cấp quyền đã phát sinh. Gỡ toàn bộ hạn chế ngay sau assertion đầu tiên của passkey mới sẽ biến cơ chế xác thực mạnh thành công cụ duy trì truy cập cho người đã vượt qua đường recovery yếu.

Bài học: mức bảo vệ của passkey còn phụ thuộc vào cách cấp quyền đăng ký, quy trình phục hồi và kiểm soát phiên sau sự cố.

## 11. Các nguyên tắc cần giữ khi triển khai

- Phân loại vấn đề ở lớp thiết bị, kho credential và tài khoản RP trước khi chọn hành động.
- Xác minh credential đang dùng được trước; không tự suy ra trạng thái phục hồi từ hệ điều hành, BS hoặc nhãn thiết bị.
- Cấp quyền đăng ký passkey mới từ bằng chứng recovery đủ mạnh, với account và purpose được khóa ở server.
- Giữ credential pending và quyền recovery có giới hạn cho tới khi đủ điều kiện kích hoạt.
- Dùng assertion của credential mới để xác nhận khả năng sử dụng; không coi nó là bằng chứng độc lập về chủ sở hữu cũ.
- Hoàn tất thay đổi bảo mật nguyên tử, tiêu thụ grant một lần và kiểm soát retry.
- Thu hồi credential theo phạm vi sự cố, đồng thời xử lý session và các quyền dài hạn liên quan.
- Thực thi giới hạn sau recovery ở cấp tài khoản để mọi đường đăng nhập đều tuân thủ.
- Thừa nhận trường hợp chưa đủ bằng chứng để phục hồi; không thay việc xác minh bằng thông tin cá nhân dễ thu thập hoặc một khoảng thời gian chờ đơn thuần.

Platform passkey recovery an toàn đòi hỏi một chuỗi cấp quyền nhất quán: bằng chứng nào cho phép lấy lại tài khoản, quyền đó cho phép đăng ký credential nào, khi nào credential được kích hoạt và session nào còn hợp lệ sau thay đổi. Sự nhất quán này quyết định liệu quá trình khôi phục giúp chủ tài khoản lấy lại quyền truy cập hay mở đường cho người khác chiếm giữ tài khoản.
