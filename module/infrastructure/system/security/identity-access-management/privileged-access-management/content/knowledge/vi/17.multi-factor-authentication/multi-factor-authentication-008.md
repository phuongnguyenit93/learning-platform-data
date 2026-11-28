# MFA của vendor trong quản lý truy cập đặc quyền

## 1. MFA cho người dùng nhà cung cấp giải quyết điều gì?

**Vendor** trong bài này là nhà cung cấp, đối tác hỗ trợ hoặc bên thứ ba có người cần truy cập đặc quyền vào tài nguyên của tổ chức. Ví dụ, kỹ sư bảo trì cần chẩn đoán thiết bị mạng, hỗ trợ ứng dụng production hoặc xử lý sự cố cơ sở dữ liệu.

**MFA của vendor** bao gồm cách người dùng bên thứ ba thực hiện xác thực nhiều yếu tố, cách tổ chức tiếp nhận bằng chứng đó và cách kết quả được sử dụng trong PAM.

Một nhà cung cấp thông báo “đã bật MFA” chưa trả lời đủ các câu hỏi:

- MFA áp dụng cho tài khoản nào và ở luồng đăng nhập nào?
- Từng kỹ sư có danh tính riêng hay đang dùng chung tài khoản?
- Phương thức chính, phương thức dự phòng và phục hồi có đáp ứng yêu cầu không?
- PAM có nhận và kiểm tra được bằng chứng phù hợp không?
- Bằng chứng còn đủ mới khi mở phiên đặc quyền không?
- Khi kỹ sư nghỉ việc, mất thiết bị hoặc hết hợp đồng, tổ chức có dừng truy cập kịp thời không?

Mục tiêu là giữ trách nhiệm cá nhân và kiểm soát truy cập qua ranh giới tổ chức. MFA cần được kết hợp với kiểm kê tài khoản, least privilege, JIT/JEA, vault, quản lý phiên và bằng chứng kiểm toán.

## 2. Ranh giới tin cậy và trách nhiệm

Một luồng thường có ít nhất ba bên:

1. **Tổ chức sở hữu tài nguyên** quyết định ai được truy cập target, quyền gì và điều kiện nào.
2. **Vendor** quản lý nhân sự, thiết bị, nguồn danh tính hoặc một phần quy trình xác thực.
3. **PAM và các thành phần liên quan** thực thi policy, cấp phiên và liên kết bằng chứng.

Nếu vendor vận hành IdP, tổ chức đang tin cậy một nguồn xác thực bên ngoài trong phạm vi đã xác định. Điều đó không đồng nghĩa vendor có quyền tự cấp entitlement tới mọi tài nguyên của tổ chức.

| Nội dung | Trách nhiệm cần xác định |
|---|---|
| Xác nhận kỹ sư thuộc vendor | Vendor và quy trình tiếp nhận đã thống nhất |
| Chấp nhận cá nhân vào phạm vi hỗ trợ | Owner hoặc người bảo trợ của tổ chức |
| Đăng ký và phục hồi authenticator | Bên quản lý authenticator, với cơ chế được chấp nhận |
| Phát hành kết quả xác thực | Nguồn danh tính hoặc dịch vụ xác thực tương ứng |
| Chấp nhận phương thức MFA cho PAM | Tổ chức sở hữu tài nguyên |
| Cấp target, role và thời gian | Policy và thẩm quyền của tổ chức |
| Ghi nhận phiên và hoạt động tại đích | Các thành phần trong phạm vi kiểm soát tương ứng |
| Thông báo nghỉ việc hoặc mất thiết bị | Vendor theo quy trình phối hợp |
| Thu hồi quyền và phiên trong PAM | Tổ chức và hệ thống thực thi của mình |

Bảng trách nhiệm phải gắn với một quy trình có thể vận hành. Nếu bên nào cũng cho rằng bên kia sẽ khóa tài khoản, một người đã hết nhiệm vụ có thể vẫn giữ quyền.

Tổ chức cần có khả năng ngừng cấp truy cập trong phạm vi của mình mà không phải chờ vendor hoàn thành mọi thao tác trên IdP của họ.

## 3. Danh tính cá nhân trước khi bàn về yếu tố xác thực

### 3.1. Mỗi kỹ sư cần được phân biệt

Tài khoản dùng chung như “vendor-support” làm suy giảm khả năng quy trách nhiệm. Nếu nhiều người dùng chung mật khẩu và điện thoại nhận OTP, log MFA chỉ chứng minh tài khoản chung đã vượt bước xác thực; nó chưa xác định cá nhân nào thực hiện.

Một hồ sơ người dùng bên thứ ba nên liên kết được:

~~~text
Danh tính cá nhân
  → vendor và người liên hệ có trách nhiệm
  → người bảo trợ trong tổ chức
  → phạm vi hợp đồng hoặc nhiệm vụ
  → entitlement được cấp
  → yêu cầu, phiên và hoạt động.
~~~

Có thể tài khoản đích vẫn là tài khoản kỹ thuật do giới hạn nền tảng. Trong trường hợp đó, PAM cần giữ liên kết từ người yêu cầu riêng tới tài khoản tại đích, thay vì dùng tài khoản chung làm danh tính duy nhất.

### 3.2. Không chỉ dùng email làm căn cứ ổn định

Email có thể đổi, được tái sử dụng hoặc là alias. Trong federation, cần dùng định danh theo cơ chế của nền tảng và nguồn phát hành để tránh gộp nhầm người dùng từ những miền tin cậy khác nhau.

Việc một tài khoản có địa chỉ email thuộc tên miền vendor không tự chứng minh:

- Cá nhân vẫn đang làm việc cho vendor.
- Cá nhân có nhiệm vụ hỗ trợ hợp lệ.
- Tài khoản đã thực hiện MFA phù hợp.
- Người đó được phép vào target đang yêu cầu.

Danh sách người hỗ trợ được duyệt và vòng đời quyền vẫn cần được quản lý.

### 3.3. Nhà thầu phụ và thay người

Nếu vendor dùng nhà thầu phụ, cần biết ai thực sự nhận quyền. Không tự mở rộng quyền cho toàn bộ đối tác của vendor chỉ từ việc đã tin cậy một tổ chức ban đầu.

Khi thay kỹ sư, tạo hoặc cập nhật quan hệ danh tính phù hợp và đánh giá quyền cho người mới. Không chuyển authenticator và tài khoản cá nhân của người cũ cho người mới để giữ nguyên lịch sử.

## 4. Các mô hình MFA có thể sử dụng

### 4.1. Tổ chức quản lý danh tính và MFA

Tổ chức cấp tài khoản riêng cho từng kỹ sư và kiểm soát phương thức xác thực.

Ưu điểm có thể là chủ động hơn với policy, đăng ký, phục hồi và bằng chứng. Đổi lại, tổ chức phải quản lý thêm vòng đời tài khoản ngoài biên chế, hỗ trợ thiết bị và tránh tài khoản tồn đọng.

Tài khoản do tổ chức cấp vẫn cần người bảo trợ và thời hạn. Quyền kiểm soát danh tính không tự làm nhu cầu truy cập luôn hợp lệ.

### 4.2. Liên kết với IdP của vendor

Kỹ sư xác thực tại IdP của vendor. PAM hoặc hệ thống trung gian tiếp nhận kết quả theo một cơ chế federation được cấu hình tin cậy.

Mô hình này cần làm rõ:

- Nguồn phát hành nào được tin cậy.
- Tập chủ thể nào được tiếp nhận.
- Bằng chứng nào cho biết phương thức và thời điểm xác thực.
- Luồng nào có thể dùng fallback.
- Ai quản lý đăng ký và phục hồi.
- Cách thông báo thay đổi hoặc sự cố ảnh hưởng tới mức tin cậy.

Một kết quả có chữ ký hợp lệ chứng minh nguồn phát hành đã tạo thông điệp và thông điệp không bị sửa theo cơ chế được kiểm tra. Nó không tự chứng minh quy trình MFA của nguồn phát hành được thiết kế và vận hành đúng.

Do đó, cấu hình tin cậy cần đi cùng kiểm chứng hành vi và trách nhiệm phối hợp.

### 4.3. Federation kết hợp step-up do tổ chức kiểm soát

Tổ chức có thể dùng danh tính từ vendor nhưng yêu cầu thêm bước xác thực đáp ứng policy trước khi mở phiên nhạy cảm.

Khả năng này phụ thuộc nền tảng và cách liên kết danh tính. Cần bảo đảm bước bổ sung thuộc đúng người dùng và đúng yêu cầu, thay vì tạo hai tài khoản không liên kết được.

Hai lần nhập mật khẩu ở hai hệ thống vẫn chỉ là sử dụng thông tin biết. Không được gọi đó là MFA chỉ vì có hai màn hình đăng nhập.

Mô hình kết hợp cũng cần cân nhắc trải nghiệm, phục hồi và bằng chứng. Nhiều lời nhắc không tự đồng nghĩa với mức bảo đảm tốt hơn.

## 5. Xác định profile MFA được chấp nhận

### 5.1. Profile cần mô tả đặc tính

Một profile cho người dùng vendor có thể xác định:

- Các phương thức hoặc đặc tính xác thực được chấp nhận.
- Yêu cầu xác minh người dùng của authenticator khi áp dụng.
- Độ mới của bằng chứng ở thời điểm mở phiên.
- Điều kiện tái sử dụng SSO.
- Phương thức dự phòng và tình huống không được dùng.
- Điều kiện đăng ký, thay thiết bị và phục hồi.
- Hành vi khi không xác minh được thuộc tính bắt buộc.

Không chỉ ghi “vendor phải có MFA” rồi để từng bên diễn giải khác nhau.

### 5.2. Phân biệt các phương thức

Mật khẩu kết hợp OTP có thể bổ sung một yếu tố, nhưng luồng OTP thông thường có thể bị lừa cung cấp mã. Push có thể bị xác nhận nhầm hoặc bị lợi dụng bằng nhiều yêu cầu không mong muốn.

Thông tin ngữ cảnh rõ và các biện pháp đối chiếu có thể giảm một số rủi ro. Chúng không tự biến mọi luồng push thành phương thức chống phishing theo giao thức.

Một số cơ chế khóa công khai ràng buộc phản hồi với bên xác minh hợp lệ. Khi sử dụng, cần kiểm tra thuộc tính thực tế, cấu hình và yêu cầu xác minh người dùng. Không suy từ nhãn “passkey” hoặc “security key” rằng mọi cách dùng đều có cùng đặc tính.

Nếu khóa hoặc passkey có đồng bộ, quy trình bảo vệ tài khoản đồng bộ, thêm thiết bị và phục hồi cũng ảnh hưởng tới ranh giới tin cậy.

### 5.3. Fallback là một phần của profile

Một luồng chính mạnh có thể bị suy giảm nếu người dùng dễ chuyển sang phương thức dự phòng không đáp ứng yêu cầu.

Cần kiểm tra các tình huống như:

- Chọn phương thức khác tại màn hình đăng nhập.
- Sử dụng recovery code.
- Nhờ helpdesk đặt lại MFA.
- Thêm một authenticator mới.
- Khôi phục tài khoản sau khi mất thiết bị.
- Sử dụng một IdP trung gian khác.

Nếu một trường hợp không đạt profile nhưng được phép vì ngoại lệ, hồ sơ cần ghi đúng ngoại lệ. Không báo cáo nó như đã đáp ứng profile thông thường.

## 6. Tiếp nhận và đăng ký người dùng vendor

Một quy trình tiếp nhận có thể gồm:

1. Owner xác nhận nhu cầu hỗ trợ và người bảo trợ.
2. Xác minh cá nhân và quan hệ với vendor theo quy trình đã thống nhất.
3. Tạo hoặc liên kết danh tính đúng người.
4. Kiểm tra nguồn xác thực và profile MFA áp dụng.
5. Đăng ký authenticator theo thẩm quyền.
6. Cấp entitlement hẹp, có thời hạn phù hợp.
7. Kiểm tra một luồng truy cập đại diện và bằng chứng liên quan.

Việc nhận được email yêu cầu đăng ký không tự chứng minh người gửi có thẩm quyền đưa thêm kỹ sư vào phạm vi hỗ trợ. Khi cần đối chiếu, sử dụng thông tin liên hệ đã được thiết lập qua quy trình của tổ chức.

Không yêu cầu người dùng gửi OTP, recovery code hoặc private key cho người quản trị để “kiểm tra MFA”. Kiểm tra cần dựa trên kết quả xác thực và khả năng hệ thống, không thu thập secret của authenticator.

Nếu tổ chức cấp thiết bị xác thực, cần có hồ sơ cấp phát, thu hồi, mất thiết bị và khóa dự phòng. Nếu vendor quản lý thiết bị, cần thống nhất điều kiện tương ứng và cách cung cấp bằng chứng cần thiết.

## 7. Chấp nhận bằng chứng MFA qua federation

### 7.1. Kiểm tra thông điệp theo giao thức

PAM hoặc thành phần tiếp nhận cần xác minh theo giao thức và tích hợp được hỗ trợ. Các nội dung cần được xử lý phù hợp gồm nguồn phát hành, bên nhận, tính toàn vẹn, thời hạn, chủ thể và liên kết với yêu cầu xác thực.

Không nhận một cờ do trình duyệt tự khai như “vendor_mfa=true” làm căn cứ đủ.

Nếu có thành phần trung gian, cần hiểu nó xác minh dữ liệu nào và chuyển tiếp bằng chứng ra sao. Chỉ kiểm tra chặng cuối mà không biết ý nghĩa dữ liệu từ chặng trước có thể tạo ra sự tin cậy không đúng phạm vi.

### 7.2. Hiểu ý nghĩa của phương thức và mức xác thực

Tên hoặc mã phương thức giữa các hệ thống có thể khác nhau. Cần có ánh xạ đã xác định: bằng chứng nào từ nguồn nào đáp ứng profile nào trong PAM.

Một nhãn chung như “MFA” có thể không cho biết người dùng đã dùng phương thức nào, có xác minh người dùng hay không hoặc có sử dụng fallback không.

Nếu thông tin cần thiết không được phát hành hoặc không được PAM kiểm tra, phải coi đó là giới hạn cần giải quyết. Không tự bổ sung một giá trị mặc định để mọi phiên đều được coi là đạt.

### 7.3. Kiểm tra độ mới

Token hoặc thông điệp mới được phát hành có thể dựa trên một phiên SSO cũ. Thời điểm phát hành không tự bằng thời điểm người dùng vừa thực hiện MFA.

Cần hiểu trường dữ liệu nào thể hiện sự kiện xác thực phù hợp và cách nguồn phát hành tạo trường đó. Nếu policy yêu cầu xác thực mới, phải kiểm tra cả hành vi của luồng chứ không chỉ tham số được gửi đi.

Khi không xác minh được độ mới, hệ thống có thể cần step-up được hỗ trợ hoặc không cấp theo luồng thông thường. Không mặc định bằng chứng thiếu thời gian là luôn mới.

### 7.4. Thay đổi trust cần có owner

Thay chứng thư ký, thay IdP, đổi mapping thuộc tính hoặc sửa policy MFA của vendor có thể ảnh hưởng cách tổ chức tiếp nhận bằng chứng.

Cần có người chịu trách nhiệm, quy trình cập nhật và khả năng phát hiện thay đổi không mong đợi. Không mở rộng sang mọi tenant, nguồn phát hành hoặc nhóm người dùng chỉ để xử lý một lỗi federation chưa phân loại.

## 8. Luồng truy cập đặc quyền của vendor

~~~mermaid
sequenceDiagram
    participant U as Kỹ sư vendor
    participant I as Nguồn xác thực
    participant P as PAM của tổ chức
    participant O as Owner hoặc approver
    participant G as Gateway
    participant T as Target
    U->>P: Yêu cầu target, role và cửa sổ
    P->>P: Kiểm tra danh tính được tiếp nhận và entitlement
    P->>O: Xin phê duyệt nếu policy yêu cầu
    O-->>P: Quyết định có phạm vi
    P->>I: Xác thực hoặc step-up theo tích hợp
    I->>U: Tương tác MFA
    U->>I: Hoàn thành tương tác
    I-->>P: Kết quả xác thực
    P->>P: Kiểm tra bằng chứng và các điều kiện hiện tại
    P->>G: Quyền mở phiên giới hạn
    G->>T: Kết nối bằng tài khoản được quản lý
    G-->>P: Kết quả phiên và định danh bằng chứng
~~~

Thứ tự phê duyệt và xác thực có thể khác theo kiến trúc. Những ràng buộc cần giữ là:

- Chủ thể nhận quyền được xác định rõ.
- MFA đạt không bỏ qua entitlement hoặc phê duyệt.
- Quyết định gắn với target, role và thời gian phù hợp.
- Điều kiện được kiểm tra trước khi quyền có thể sử dụng.
- Gateway không trở thành đường tới đích tùy ý.
- Hoạt động tại đích có thể liên kết về người dùng vendor.

Nếu tổ chức tin cậy MFA do vendor thực hiện, vẫn cần giữ quyền quyết định truy cập tại tổ chức. Một kỹ sư xác thực thành công tại vendor không tự trở thành thành viên nhóm quản trị production.

## 9. Kết hợp với least privilege, JIT/JEA và vault

### 9.1. MFA xác thực, role giới hạn tác vụ

Role “support” có thể rộng hơn công việc thực tế. Cần kiểm tra quyền hiệu lực: xem dữ liệu gì, sửa gì, mở shell hay công cụ nào, có thể tạo tài khoản hoặc lấy secret khác không.

Một tài khoản vendor có MFA vẫn có thể gây ảnh hưởng lớn nếu được toàn quyền trên nhiều target. Phạm vi quyền cần theo công việc và khả năng thực thi tại đích.

JEA có thể giới hạn tác vụ nếu nền tảng hỗ trợ và cấu hình đã được kiểm chứng. Một ghi chú “chỉ chẩn đoán” không tạo ra giới hạn kỹ thuật.

### 9.2. JIT giảm thời gian giữ quyền

Thời hạn tài khoản, entitlement, phê duyệt, quyền mở phiên và session có thể khác nhau. Cần thiết kế sự phối hợp, thay vì chỉ đặt một ngày hết hạn hợp đồng.

Ví dụ, tài khoản kỹ sư có thể tồn tại trong thời gian hợp tác nhưng quyền vào production chỉ kích hoạt cho từng công việc. Sau khi cửa sổ kết thúc, không được tiếp tục cấp phiên từ entitlement tạm đã hết hạn.

Gia hạn cần được xử lý theo policy. MFA mới không tự gia hạn phê duyệt hoặc cửa sổ hỗ trợ.

### 9.3. Vault và credential tại đích

Gateway có thể dùng credential từ vault để kỹ sư không cần biết secret. Đây là một cách giảm phơi lộ, nhưng vẫn cần kiểm soát quyền của gateway và các đường dùng tài khoản đích.

Nếu vendor được checkout secret, MFA tại thời điểm checkout chưa chứng minh mỗi lần dùng secret về sau đều được xác thực lại.

Khi hết nhu cầu, xử lý credential theo loại và dependency: thu hồi grant, hết hạn credential tạm, rotation hoặc biện pháp phù hợp khác. Không tự rotation một credential dùng chung với dịch vụ mà chưa đánh giá ảnh hưởng.

## 10. Ví dụ: kỹ sư vendor hỗ trợ một máy chủ production

### 10.1. Bối cảnh và policy minh họa

Kỹ sư Mai thuộc vendor A cần chẩn đoán app-prod-a. Người bảo trợ trong tổ chức xác nhận danh tính, nhiệm vụ và phạm vi.

Giả định hệ thống hỗ trợ role chẩn đoán đã kiểm chứng và một gateway có khả năng ghi nhận theo yêu cầu của tình huống.

Policy minh họa:

- Chỉ Mai được nhận quyền theo yêu cầu này.
- Chỉ app-prod-a và role chẩn đoán được cấp.
- Cửa sổ công việc từ 20:00 đến 20:30 theo UTC+07:00.
- Bằng chứng MFA dùng để mở phiên không quá 5 phút.
- Không xuất credential và không mở đường truyền dữ liệu chưa duyệt.
- Không cho thời lượng phiên vượt cuối cửa sổ.
- Reconnect phải được kiểm tra theo policy hiện tại.

Các giá trị thời gian chỉ phục vụ ví dụ. Triển khai cần policy phù hợp với môi trường.

### 10.2. Đánh giá MFA từ vendor

Mai xác thực tại IdP của vendor. PAM nhận thông điệp hợp lệ nhưng chỉ thấy kết quả dựa trên một phiên cũ, chưa xác minh được bằng chứng MFA đủ mới.

Có thể cần yêu cầu xác thực lại qua cơ chế được hỗ trợ hoặc dùng step-up do tổ chức kiểm soát. Nếu không có cách đáp ứng, yêu cầu chưa đủ điều kiện cấp theo luồng thông thường.

Không sửa mapping thành “luôn đạt MFA” để xử lý việc thiếu dữ liệu. Nếu công việc thật sự cần một ngoại lệ, phải đi qua thẩm quyền và điều kiện ngoại lệ riêng.

### 10.3. Mở phiên

Khi bằng chứng đạt, PAM kiểm tra lại entitlement, phê duyệt và cửa sổ. Quyền mở phiên gắn với Mai, target và role được cấp.

Gateway xác minh target, lấy credential theo quyền và mở phiên. Log cần liên kết được sự kiện xác thực với request, grant, gateway session và tài khoản tại đích.

Nếu Mai đổi sang máy chủ khác hoặc cần quyền sửa cấu hình, đó là thay đổi phạm vi. MFA thành công không tự làm thay đổi này hợp lệ.

### 10.4. Kết thúc và reconnect

Nếu mất kết nối lúc 20:20, thao tác resume không tự tạo một cửa sổ 30 phút mới. Các giới hạn đã định vẫn áp dụng.

Đến 20:30, hệ thống xử lý quyền và phiên theo thiết kế. Nếu gateway đã ngắt nhưng trạng thái tại đích chưa được xác nhận, cần ghi đúng phần còn chờ.

Sau công việc, người bảo trợ và quy trình liên quan xử lý quyền tạm, bằng chứng và các việc còn tồn tại. Đóng ticket không tự chứng minh credential, token và mọi phiên đã hết hiệu lực.

## 11. Thiết bị vendor và khả năng chiếm phiên

MFA giúp giảm một số rủi ro chiếm danh tính, nhưng không tự bảo vệ mọi hoạt động trên một endpoint đã bị kiểm soát.

Thiết bị vendor có thể chứa phần mềm không phù hợp, bị mất hoặc có khả năng làm lộ nội dung hiển thị và dữ liệu phiên. Các kiểm soát theo khả năng môi trường có thể gồm:

- Điều kiện thiết bị hoặc môi trường truy cập được chấp nhận.
- Workspace quản trị do tổ chức kiểm soát.
- Hạn chế clipboard, tải tệp hoặc kênh bổ sung theo nhu cầu.
- Không tiết lộ credential tại đích.
- Phiên có thời hạn và cơ chế can thiệp.
- Giám sát hoạt động và hành vi bất thường.

Một workspace từ xa không làm biến mất mọi rủi ro của thiết bị đầu cuối. Người dùng vẫn có thể xem hoặc nhập dữ liệu qua client; mức bảo vệ cần được đánh giá đúng khả năng.

Cookie, token và quyền mở phiên sau MFA cũng cần được bảo vệ. Nếu một đối tượng cho phép tiếp tục truy cập khi bị lấy, MFA ban đầu không tự ngăn việc dùng lại đối tượng đó.

Không đưa token, liên kết resume nhạy cảm hoặc credential vào log và ticket không cần thiết.

## 12. Mất thiết bị, đổi phương thức và phục hồi

### 12.1. Xác định bên có quyền xử lý

Nếu vendor quản lý authenticator, helpdesk của tổ chức có thể không có quyền reset tại IdP của vendor. Ngược lại, vendor không tự có quyền bỏ điều kiện PAM của tổ chức.

Quy trình phối hợp cần xác định ai xác minh danh tính, ai thực hiện thay đổi và ai quyết định truy cập trở lại.

Một yêu cầu từ số điện thoại hoặc email tự khai chưa đủ để bỏ MFA. Cần sử dụng quy trình và nguồn đối chiếu đã thiết lập, đặc biệt khi yêu cầu có tính khẩn cấp.

### 12.2. Xử lý truy cập trong lúc chưa xác minh

Theo tình huống và policy, có thể cần chặn cấp mới hoặc xử lý các phiên liên quan trong phạm vi của tổ chức trong khi vendor điều tra thiết bị mất.

Cần phân biệt:

- Khóa hoặc thay authenticator.
- Khóa tài khoản nguồn.
- Thu hồi quyền ở PAM.
- Vô hiệu token hoặc cookie.
- Kết thúc gateway session.
- Xác nhận kết quả tại target.

Một thao tác reset MFA không tự thực hiện mọi hành động còn lại.

### 12.3. Phương thức dự phòng

Có thể có phương thức dự phòng đáp ứng profile đã định. Việc cấp và lưu giữ chúng cần giữ trách nhiệm cá nhân và khả năng thu hồi.

Không chia sẻ recovery code cho cả đội hỗ trợ để tránh gián đoạn. Nếu phương thức dự phòng yếu hơn mức bắt buộc, cần xử lý đúng policy ngoại lệ thay vì coi là tương đương.

Sau phục hồi, kiểm tra lịch sử thay đổi và truy cập liên quan. Nếu có dấu hiệu giả mạo, việc người dùng đã đăng nhập lại thành công chưa đủ để đóng sự cố.

## 13. Vendor rời dự án, đổi nhân sự hoặc có sự cố

### 13.1. Thu hồi theo sự kiện

Các sự kiện cần đưa vào vòng đời quyền gồm:

- Kỹ sư nghỉ việc hoặc đổi vai trò.
- Kết thúc nhiệm vụ, hợp đồng hoặc quan hệ với nhà thầu phụ.
- Mất thiết bị hoặc nghi lộ tài khoản.
- Vendor thay đổi IdP, phương thức MFA hoặc quy trình phục hồi.
- Phát hiện sự cố có thể ảnh hưởng miền tin cậy của vendor.

Thời gian và kênh thông báo cần được thống nhất theo nhu cầu của tổ chức. Không dựa duy nhất vào việc “đến lần rà soát sau sẽ kiểm tra”.

### 13.2. Thu hồi trong phạm vi tổ chức

Một kế hoạch có thể cần:

~~~text
Ngừng tiếp nhận hoặc cấp mới cho chủ thể liên quan.
Thu hồi entitlement và các grant theo phạm vi.
Vô hiệu quyền mở phiên chưa dùng.
Xử lý token, cookie và phiên của hệ thống liên quan.
Ngắt hoặc kết thúc gateway session theo thẩm quyền.
Xác minh trạng thái tại đích trong phạm vi hỗ trợ.
Xử lý credential có nguy cơ đã bị sử dụng ngoài luồng.
Lưu bằng chứng và phần còn chờ xử lý.
~~~

Đăng xuất khỏi IdP của vendor không tự chứng minh mọi phiên ứng dụng và PAM đã mất hiệu lực. Hệ thống đích có thể có vòng đời riêng.

Nếu nghi nguồn xác thực của vendor bị ảnh hưởng, chỉ yêu cầu vendor phát lại bằng chứng MFA có thể chưa giải quyết ranh giới tin cậy đã bị suy giảm. Cần đánh giá phạm vi và quyết định tiếp nhận bằng chứng theo quy trình ứng phó.

### 13.3. Không gộp hoạt động con người với workload

Vendor có thể có cả kỹ sư tương tác và dịch vụ tự động tích hợp. Hai loại cần được kiểm kê riêng.

Một workload không thực hiện MFA tương tác như người dùng, nhưng vẫn cần danh tính máy, quyền hẹp, credential được quản lý và bằng chứng phù hợp. Không dùng một tài khoản kỹ sư với mã OTP chia sẻ để chạy automation lâu dài.

## 14. Sự cố dịch vụ MFA và đường khẩn cấp

Cần định nghĩa hành vi khi IdP, dịch vụ MFA hoặc tích hợp federation không hoạt động:

- Có cấp phiên mới từ bằng chứng đã có không, và trong giới hạn nào?
- Những phiên đang hoạt động chịu điều kiện gì?
- Reconnect hoặc nâng quyền được xử lý ra sao?
- Khi nào được dùng đường khẩn cấp đã được ủy quyền?
- Ai chịu trách nhiệm quyết định và hậu kiểm?

Không mặc định mọi phiên phải dừng ngay hoặc mọi yêu cầu mới được bỏ MFA. Hành vi phải dựa trên policy và khả năng thực thi của từng luồng.

Nếu có break-glass cho hỗ trợ vendor, đường đó cần danh tính có trách nhiệm, phạm vi hẹp, thời hạn và bằng chứng theo điều kiện sự cố. Có thể cần một hình thức thực hiện khác theo thiết kế, chẳng hạn người vận hành của tổ chức thực hiện tác vụ trong một quy trình hỗ trợ có giám sát.

Sau sử dụng phải xử lý quyền tạm, credential và ngoại lệ. Phiên mở theo ngoại lệ không được ghi thành “MFA đạt” nếu thực tế không có bằng chứng tương ứng.

## 15. Bằng chứng để kiểm toán và điều tra

Một chuỗi bằng chứng hữu ích cần liên kết:

~~~text
Cá nhân và vendor
  → người bảo trợ, nhiệm vụ và thời hạn
  → nguồn xác thực, sự kiện và profile được chấp nhận
  → quyết định policy và các phê duyệt
  → entitlement hoặc grant
  → gateway session và tài khoản tại đích
  → hoạt động quan sát được
  → kết thúc, thu hồi và phần chưa xác minh.
~~~

Thông tin có thể bao gồm định danh sự kiện xác thực, nguồn phát hành, thời điểm được đánh giá, kết quả kiểm tra profile, request ID và session ID. Dữ liệu cụ thể phụ thuộc khả năng tích hợp.

Không lưu OTP, private key, recovery code, token đầy đủ hoặc dữ liệu sinh trắc học thô để chứng minh MFA đã xảy ra. Bằng chứng cần đủ cho mục đích và có quyền truy cập phù hợp.

Tổ chức và vendor cần thống nhất cách phối hợp đối chiếu khi xảy ra sự cố, kể cả múi giờ, định danh và khả năng truy xuất dữ liệu. Nếu chỉ vendor giữ một nguồn log quan trọng, cần biết giới hạn và cơ chế tiếp cận; không mặc định tổ chức sẽ luôn có dữ liệu ngay khi cần.

Một log “MFA thành công” không chứng minh mọi thao tác trong phiên đều hợp lệ. Điều tra hoạt động vẫn cần bằng chứng phiên và target.

## 16. Kiểm chứng triển khai

| Tình huống | Kết quả cần quan sát theo policy |
|---|---|
| Kỹ sư có danh tính riêng, đúng nhiệm vụ và MFA đạt | Chỉ mở phạm vi được cấp |
| Tài khoản vendor không nằm trong danh sách được tiếp nhận | Không cấp chỉ vì xác thực thành công |
| Người dùng tự khai cờ đã MFA | Không được coi là bằng chứng tin cậy |
| Kết quả từ nguồn phát hành ngoài phạm vi | Không được tiếp nhận như nguồn đã cấu hình |
| Thông điệp mới nhưng sự kiện xác thực cũ | Áp dụng đúng yêu cầu độ mới |
| Luồng fallback không đạt profile | Không âm thầm ánh xạ thành đã đạt |
| Đổi target hoặc role sau xác thực | Không vượt phạm vi bằng tham số đã sửa |
| Hai người dùng chung tài khoản hoặc authenticator | Không kết luận đã có trách nhiệm cá nhân chỉ từ log MFA |
| Kỹ sư bị gỡ quyền ở PAM nhưng IdP vendor còn hoạt động | Không cấp mới từ quyền đã bị thu hồi |
| Reset MFA hoặc thêm thiết bị | Có bằng chứng và kiểm tra truy cập liên quan |
| Reconnect ngoài cửa sổ công việc | Không tự kéo dài quyền |
| Đường quản trị trực tiếp ngoài gateway | Được phát hiện và xử lý theo phạm vi |
| Vendor đổi IdP hoặc cấu hình phát hành thuộc tính | Có quy trình cập nhật và kiểm chứng tương ứng |
| Nguồn MFA không hoạt động | Dùng đúng hành vi thường hoặc khẩn cấp đã định |
| Vendor hoặc kỹ sư hết nhiệm vụ | Thu hồi quyền, phiên và đối tượng liên quan theo thiết kế |

Thử nghiệm cần sử dụng tài khoản và tài nguyên được phép. Không thu thập mã OTP thật vào báo cáo; dùng các định danh sự kiện và kết quả kiểm tra.

Khi truy cập thất bại, phân biệt lỗi federation, bằng chứng không đạt, entitlement, phê duyệt, đường mạng và credential tại đích. Không tắt MFA hoặc mở trust rộng chỉ để xử lý một thông báo lỗi chung.

## 17. Chỉ số và sai lầm thường gặp

Các chỉ số có thể hỗ trợ vận hành gồm:

- Người dùng vendor có sponsor, nhiệm vụ và thời hạn rõ.
- Phiên có thể liên kết với bằng chứng MFA đáp ứng profile.
- Yêu cầu bị từ chối do bằng chứng cũ, thiếu thuộc tính hoặc fallback.
- Tài khoản không còn người bảo trợ hoặc nhiệm vụ hợp lệ.
- Thời gian từ thông báo rời dự án tới kết quả thu hồi trong từng lớp.
- Ngoại lệ MFA quá hạn.
- Thay đổi authenticator hoặc trust chưa được đối chiếu.
- Đường truy cập vendor chưa nằm trong phạm vi PAM.

Mẫu số phải rõ. Tỷ lệ đạt trong các phiên qua gateway không đại diện cho mọi đường quản trị nếu còn VPN, web, API hoặc console ngoài phạm vi.

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Tin câu “vendor có MFA” mà không xác định profile | Các bên hiểu mức bảo đảm khác nhau | Thống nhất đặc tính và kiểm chứng luồng |
| Cho cả tên miền vendor quyền vào production | Phạm vi chủ thể quá rộng | Kiểm soát từng danh tính và entitlement |
| Dùng tài khoản hỗ trợ chung với một điện thoại | Khó quy trách nhiệm | Danh tính và authenticator cá nhân |
| Coi token mới là MFA mới | Chấp nhận xác thực quá cũ | Kiểm tra semantics của bằng chứng |
| Ánh xạ mọi fallback thành MFA đạt | Bỏ qua yêu cầu bắt buộc | Phân biệt phương thức và ngoại lệ |
| MFA đạt là bỏ qua phê duyệt | Cấp quyền không đúng nhu cầu | Tách xác thực khỏi ủy quyền |
| Vendor khóa tài khoản là coi mọi phiên đã dừng | Token và session tại tổ chức có thể còn | Thu hồi và xác minh từng lớp |
| Reset MFA qua yêu cầu chưa xác minh | Có thể chuyển quyền cho kẻ giả mạo | Quy trình phục hồi có thẩm quyền |
| Hết hợp đồng chỉ xóa một tài khoản | Bỏ sót grant, credential hoặc đường khác | Kiểm kê và thu hồi toàn bộ phạm vi liên quan |
| Không có owner cho trust federation | Thay đổi có thể không được kiểm soát | Gắn trách nhiệm và vòng đời thay đổi |

## 18. Bài tập áp dụng

Một doanh nghiệp cho đội vendor dùng chung tài khoản VPN và một tài khoản PAM. Vendor cho biết đã bật MFA tại IdP, nhưng PAM không lưu được thông tin phương thức hoặc thời điểm xác thực. Khi đổi kỹ sư, đội chỉ chuyển điện thoại nhận mã cho người mới. Kết thúc đợt hỗ trợ, người bảo trợ đóng ticket nhưng chưa kiểm tra phiên và quyền còn lại.

Hãy xây dựng phương án trả lời:

1. Danh tính nào cần được tách để giữ trách nhiệm cá nhân?
2. Thông tin nào cần kiểm chứng trước khi tin cậy MFA từ vendor?
3. Tổ chức và vendor chịu trách nhiệm gì trong đăng ký, phục hồi và thu hồi?
4. Làm thế nào gắn yêu cầu với đúng target, role và cửa sổ công việc?
5. Những đường truy cập hoặc credential nào có thể còn dùng ngoài phiên PAM?
6. Cần bằng chứng nào để xác nhận quyền đã kết thúc?
7. Nếu vendor chưa phát hành được bằng chứng đủ mới, phương án nào có thể đáp ứng policy và ai quyết định ngoại lệ nếu cần?

Một phương án đạt mục tiêu cần chỉ rõ người sử dụng, nguồn bằng chứng, policy tiếp nhận, lớp thực thi và vòng đời thu hồi. Chỉ bật một tùy chọn MFA hoặc thêm một dòng cam kết trong hợp đồng chưa đủ để chứng minh truy cập đặc quyền của vendor đã được kiểm soát.
