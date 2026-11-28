# Credential consistency sau restore

## 1. Vì sao khôi phục PAM chưa đồng nghĩa khôi phục được truy cập

Một nền tảng quản lý truy cập đặc quyền (PAM) có thể khởi động thành công sau restore, hiển thị đầy đủ tài khoản và đọc được dữ liệu trong vault, nhưng vẫn không đăng nhập được vào máy chủ đích. Ngược lại, hệ thống có thể đăng nhập được bằng một credential cũ mà chính sách hiện tại đã yêu cầu thu hồi. Cả hai trường hợp đều cho thấy thành công của thao tác phục hồi dữ liệu chưa đủ để khẳng định trạng thái truy cập an toàn.

**Credential consistency sau restore** là trạng thái nhất quán giữa dữ liệu định danh, phiên bản credential, hiệu lực tại nơi xác thực, quyền được cấp và các consumer sử dụng credential đó, trong một phạm vi phục hồi đã xác định.

Trong module PAM, credential có thể là mật khẩu quản trị, mật khẩu tài khoản dịch vụ, SSH key, API token, chứng thư hoặc thông tin xác thực phục vụ connector. Cơ chế kiểm tra của mỗi loại khác nhau, nhưng cùng phải trả lời các câu hỏi:

- Vault có giữ đúng credential mà hệ thống đích đang chấp nhận không?
- Credential ấy có được phép tiếp tục sử dụng sau sự cố không?
- Ứng dụng, dịch vụ và tác vụ tự động có nhận đúng phiên bản không?
- Policy, quy trình phê duyệt và giới hạn phiên có phản ánh trạng thái hiện hành không?
- Có đủ bằng chứng để biết đã kiểm tra điều gì, lúc nào và bởi ai không?

Mục tiêu của bài là xây dựng cách đối soát, xử lý và chứng minh sự nhất quán đó. Một bản backup giải quyết khả năng lấy lại dữ liệu; một quy trình phục hồi PAM hoàn chỉnh còn phải đưa đường truy cập đặc quyền trở về trạng thái đã kiểm soát.

## 2. Mô hình các thành phần cần nhất quán

Không nên xem credential như một chuỗi bí mật nằm đơn lẻ trong vault. Một credential được sử dụng trong một chuỗi quan hệ:

```text
Danh tính / tài khoản
        |
        v
Policy + phê duyệt + thời hạn quyền
        |
        v
Bản ghi credential trong vault
        |
        +----> Connector / session broker ----> Hệ thống đích
        |
        +----> Ứng dụng / service / job tự động

Audit và lịch sử rotation cung cấp bằng chứng cho toàn chuỗi.
```

Có thể phân chia trạng thái cần đối soát thành sáu lớp:

| Lớp | Câu hỏi cần kiểm tra | Dấu hiệu lệch sau restore |
|---|---|---|
| Danh tính | Đúng tài khoản, môi trường và hệ thống đích chưa? | Bản ghi trỏ tới máy cũ hoặc tài khoản đã đổi tên |
| Bí mật | Credential trong vault có xác thực được ở đích không? | Vault giữ mật khẩu trước lần rotation gần nhất |
| Vòng đời | Credential còn hiệu lực, chưa bị thu hồi và còn đúng mục đích không? | Token đã bị thu hồi lại xuất hiện trong dữ liệu phục hồi |
| Quyền | Quyền, phê duyệt, JIT/JEA có còn hợp lệ không? | Vai trò cũ hoặc grant hết hạn bị đưa trở lại |
| Consumer | Mọi consumer trong phạm vi có sử dụng đúng phiên bản không? | Một service còn cache mật khẩu cũ và liên tục retry |
| Bằng chứng | Có thể chứng minh trạng thái và quyết định phục hồi không? | Audit chỉ còn tới mốc backup, thiếu các thay đổi sau đó |

Một bài kiểm tra đăng nhập thành công chỉ chứng minh được một phần của lớp bí mật tại thời điểm thử. Nó không tự chứng minh rằng quyền cấp là hợp lệ, token cũ đã bị vô hiệu hóa hay tất cả consumer đều hoạt động.

### 2.1. Những điều kiện nên được coi là bất biến

Với mỗi tài khoản trong phạm vi phục hồi, nhóm vận hành cần xác lập các điều kiện kiểm tra rõ ràng:

1. Định danh tài khoản được liên kết chính xác với hệ thống đích và môi trường.
2. Credential được công bố là hiện hành phải xác thực được qua đường sử dụng dự kiến.
3. Credential cũ thuộc diện thu hồi không còn được chấp nhận theo tiêu chí đã định.
4. Consumer được phép sử dụng credential hiện hành; consumer ngoài phạm vi không nhận được bí mật.
5. Quyền hiện tại không vượt quá chính sách đã được phê duyệt.
6. Rotation và giám sát có thể tiếp tục hoạt động mà không gây thay đổi xung đột.
7. Mỗi kết luận quan trọng đều có bằng chứng không chứa giá trị bí mật.

Điều kiện thứ ba cần diễn giải theo loại credential. Với token ngắn hạn, có thể chờ hết thời hạn trong một cửa sổ cô lập được phê duyệt hoặc thực hiện thu hồi sớm. Với mật khẩu dùng chung cho nhiều consumer, thay đổi mật khẩu và cập nhật consumer thường là một phần của kế hoạch phục hồi. Không nên áp dụng một thao tác duy nhất cho mọi loại.

## 3. Cửa sổ không nhất quán giữa backup và sự cố

Giả sử có chuỗi sự kiện sau:

```text
01:00  Backup vault: tài khoản svc-report dùng phiên bản V17
01:20  Rotation thành công: target và vault chuyển sang V18
01:25  Service báo cáo nhận V18
01:40  PAM gặp sự cố
02:10  Restore vault từ bản backup 01:00
```

Sau restore:

- Vault phục hồi về dữ liệu V17.
- Hệ thống đích vẫn chấp nhận V18 vì hệ thống đích không bị restore.
- Service đang chạy có thể vẫn giữ V18 trong bộ nhớ hoặc cấu hình.
- Lịch sử trong vault phục hồi có thể không còn sự kiện rotation lúc 01:20.

Nếu mở lại truy cập ngay, PAM có thể gửi V17 tới đích và nhận lỗi. Nếu tự động retry nhiều lần, tài khoản có thể bị khóa. Nếu operator thấy service còn hoạt động rồi kết luận hệ thống đã ổn, sai lệch vẫn tồn tại và chỉ xuất hiện khi service khởi động lại hoặc khi một phiên quản trị mới được tạo.

Khoảng từ mốc snapshot tới thời điểm gián đoạn là **cửa sổ thay đổi cần tái dựng**. Trong cửa sổ đó có thể xảy ra nhiều sự kiện hơn rotation:

- Tạo mới hoặc xóa tài khoản.
- Thu hồi API token hay chứng thư.
- Thay đổi thành viên nhóm quản trị.
- Cấp quyền tạm thời và hết hạn quyền JIT.
- Thay đổi khóa SSH hoặc trust của CA.
- Đổi connector, endpoint hoặc phương thức xác thực.
- Truy xuất credential khẩn cấp theo quy trình break-glass.

RPO cho biết mức mất dữ liệu có thể chấp nhận được của hệ thống được backup. RPO không tự bảo đảm rằng một credential trong snapshot vẫn đồng bộ với một hệ thống đích độc lập. Mỗi thay đổi có hiệu lực bên ngoài PAM đều có thể tạo ra lệch trạng thái dù backup đáp ứng RPO.

## 4. Các tình huống lệch phổ biến

### 4.1. Chỉ vault được restore

Đây là trường hợp dễ thấy nhất: vault trở về thời điểm cũ còn tài khoản trên server, database hoặc thiết bị mạng giữ trạng thái mới.

Ví dụ, rotation đã thay mật khẩu trên database nhưng snapshot phục hồi chỉ chứa mật khẩu trước rotation. Cách giải quyết phải dựa trên xác minh hiện trạng và phương án cập nhật được hỗ trợ; không tự động ép database dùng lại mật khẩu cũ chỉ để khớp snapshot.

### 4.2. Chỉ hệ thống đích được restore

Vault giữ credential mới nhưng server hoặc database được phục hồi từ một bản backup cũ hơn. Tùy loại hệ thống và phạm vi backup, trạng thái tài khoản có thể quay lại credential trước đó.

Không được mặc định mọi restore của hệ điều hành đều phục hồi credential giống nhau. Cần xác định tài khoản được xác thực cục bộ, qua directory hay bởi dịch vụ bên ngoài. Restore một máy thành viên không đồng nghĩa restore cả directory.

### 4.3. Vault và hệ thống đích đều được restore nhưng khác mốc

Hai bản backup có thể đều hợp lệ nhưng không thuộc cùng một thời điểm logic. Chọn hai snapshot có timestamp gần nhau cũng chưa chứng minh rằng một rotation nằm giữa hai snapshot đã hoàn tất ở cả hai phía.

Một rotation có thể có các bước riêng: đổi ở đích, xác minh, cập nhật vault, cập nhật consumer và ghi audit. Nếu gián đoạn giữa các bước, cần đối soát từng phần thay vì chỉ so timestamp.

### 4.4. Hai bản đều cùng mốc nhưng consumer chưa đồng bộ

Ứng dụng có thể vẫn cache credential mới hơn hoặc cũ hơn dữ liệu vừa restore. Một số consumer tải bí mật mỗi lần dùng; một số chỉ đọc lúc khởi động; một số có connection pool tồn tại lâu.

Kết nối hiện hữu tiếp tục hoạt động không có nghĩa kết nối mới sẽ thành công. Kế hoạch phục hồi cần kiểm thử đường tạo kết nối mới và cơ chế nạp lại bí mật phù hợp với consumer.

### 4.5. Credential còn dùng được nhưng đã bị thu hồi vì sự cố

Trong một vụ lộ bí mật, snapshot trước thời điểm thu hồi có thể chứa credential từng bị đánh dấu không an toàn. Sự xuất hiện trở lại trong vault không phải căn cứ để tái cho phép sử dụng.

Ở đây có hai câu hỏi độc lập:

- Credential có còn được hệ thống đích chấp nhận không?
- Theo quyết định xử lý sự cố, credential có được phép sử dụng không?

Nếu một credential đã bị lộ nhưng vẫn xác thực được, đó là trạng thái cần xử lý, không phải bằng chứng phục hồi thành công.

### 4.6. Credential đúng nhưng quyền hoặc policy sai

Một tài khoản có thể đăng nhập được, nhưng policy phục hồi lại cho phép truy xuất mật khẩu trực tiếp, bỏ phê duyệt hoặc duy trì quyền quản trị lâu hơn quy định hiện hành.

Đối với PAM, tính nhất quán phải bao gồm quyền và đường sử dụng. “Đăng nhập được” không thể thay thế kiểm tra least privilege, JIT/JEA và các điều kiện kiểm soát phiên.

## 5. Xác định nguồn quyết định cho từng loại trạng thái

Không có một bản ghi duy nhất luôn làm nguồn chuẩn cho tất cả thuộc tính. Cần xác định nguồn quyết định theo câu hỏi cần trả lời.

| Câu hỏi | Nguồn cần đối chiếu | Giới hạn |
|---|---|---|
| Hệ thống hiện chấp nhận credential nào? | Nơi xác thực thực tế và cơ chế xác minh được hỗ trợ | Không chứng minh credential an toàn để tiếp tục dùng |
| Phiên bản nào được phát hành gần nhất? | Lịch sử rotation, audit và bằng chứng thay đổi độc lập | Log có thể thiếu, trễ hoặc nằm trong phần đã bị restore |
| Credential nào phải bị thu hồi? | Hồ sơ sự cố và quyết định thu hồi được phê duyệt | Không được suy ra chỉ từ snapshot cũ |
| Ai được phép sử dụng tài khoản? | Chính sách hiện hành và nguồn quản trị danh tính có thẩm quyền | Bản sao policy trong backup có thể đã lỗi thời |
| Consumer nào phụ thuộc vào credential? | Danh mục phụ thuộc, cấu hình được quản lý và quan sát vận hành | Chỉ dùng inventory cũ có thể bỏ sót consumer mới |
| Grant tạm thời còn hợp lệ không? | Thời gian thực, phê duyệt và thời hạn gốc | Restore không được khởi động lại thời hạn quyền |

Ví dụ, mật khẩu hash trên hệ thống đích thường không cho phép lấy lại mật khẩu rõ để nhập vào vault. Khi không có một bản credential hiện hành có thể phục hồi an toàn, hướng xử lý có thể là đặt credential mới qua một kênh quản trị đã được xác thực và được phê duyệt. Không biến bước đối soát thành việc trích xuất bí mật từ nơi không được phép.

Một bản ghi “V18” trong log cũng không đủ để tái tạo mật khẩu. Phiên bản, dấu thời gian và kết quả thao tác là dữ liệu đối soát; chúng không thay thế giá trị credential được lưu giữ hợp lệ.

## 6. Lập inventory phục hồi và phân loại rủi ro

Trước khi cho phép truy cập, cần có một danh sách các tài khoản và đường truy cập thuộc phạm vi. Danh sách tối thiểu nên chứa:

```yaml
accountRef: pam-prod-db-report
targetRef: db-report-prod
accountType: service-account
credentialType: password
restoredVaultVersion: V17
observedRotationAfterBackup: true
dependentConsumers:
  - report-api
  - report-batch
restoredPolicyReviewed: false
reconciliationState: UNKNOWN
recoveryOwner: database-operations
evidenceRef: REC-EXAMPLE-042
```

Đây là minh họa một bản ghi đối soát, không phải schema của một sản phẩm PAM cụ thể. Bản ghi không chứa mật khẩu, token hay private key.

Phân loại rủi ro giúp xác định thứ tự xử lý:

- **Tài khoản kiểm soát nền tảng:** tài khoản quản trị PAM, directory, khóa mã hóa và đường break-glass.
- **Tài khoản dịch vụ quan trọng:** credential mà sai lệch có thể gây gián đoạn ứng dụng hoặc liên tục khóa tài khoản.
- **Tài khoản đặc quyền cao trên đích:** quản trị hệ điều hành, database, thiết bị mạng, nền tảng ảo hóa.
- **Credential có dấu hiệu lộ hoặc đã thu hồi:** cần tuân thủ quyết định ứng phó sự cố ngay cả khi còn dùng được.
- **Tài khoản ít phụ thuộc:** có thể dùng làm canary nếu có phạm vi và quyền phù hợp.

Không nên chỉ ưu tiên theo số lượng tài khoản. Một credential dùng bởi nhiều job sản xuất có thể cần điều phối phức tạp hơn hàng chục tài khoản quản trị ít sử dụng.

Inventory cũng phải có chủ sở hữu chịu trách nhiệm chấp nhận kết quả. Nếu không biết consumer nào sử dụng một tài khoản dịch vụ, trạng thái hợp lý là cần điều tra thêm, chưa phải “đã nhất quán”.

## 7. Quy trình phục hồi có kiểm soát

### Bước 1 — Cô lập môi trường phục hồi

Đưa PAM vừa restore vào vùng kiểm soát trước khi nối lại toàn bộ hệ thống đích. Tạm giữ các đường tự động có thể gây thay đổi hoặc phát hành credential:

- Rotation theo lịch.
- Job đồng bộ tự động.
- Cấp phát credential cho consumer.
- Tạo phiên quản trị mới.
- Các cơ chế retry hàng loạt.

Phạm vi tạm giữ cần theo khả năng nền tảng và tác động nghiệp vụ. Ghi lại những luồng nào đã dừng, những luồng nào vẫn được cho phép và ai chịu trách nhiệm mở lại.

Đặc biệt tránh để một bản PAM cũ vẫn hoạt động song song và cùng rotation tài khoản với bản vừa phục hồi. Chỉ một bên được phép điều khiển thay đổi credential trong phạm vi đã chọn tại một thời điểm.

### Bước 2 — Kiểm tra khả năng giải mã và định danh

Xác minh bản backup, vật liệu khóa, chứng thư hoặc các phụ thuộc giải mã theo quy trình phục hồi của nền tảng. Đọc được tên tài khoản trong giao diện không chứng minh đọc và sử dụng được credential.

Đồng thời kiểm tra ánh xạ tới hệ thống đích: endpoint, môi trường, domain, account identifier và connector. Một credential đúng nhưng trỏ nhầm môi trường vẫn là một lỗi nghiêm trọng.

Không xuất hàng loạt credential ra file rõ để “kiểm tra nhanh”. Ưu tiên kiểm tra qua cơ chế được hỗ trợ và giới hạn người có thể truy cập bí mật.

### Bước 3 — Tái dựng thay đổi sau mốc backup

Đối chiếu mốc backup với lịch sử rotation, log của hệ thống đích, hồ sơ thay đổi và bằng chứng sự cố.

Với mỗi tài khoản, phân biệt:

- Không có bằng chứng thay đổi.
- Có bằng chứng thay đổi đã hoàn tất.
- Có thay đổi nhưng không rõ đã hoàn tất ở những phía nào.
- Đã bị thu hồi hoặc nghi lộ.
- Không đủ bằng chứng để xác định.

“Không thấy log” không đồng nghĩa “không có thay đổi”, nhất là khi chính kho log cũng bị restore hoặc có khoảng trống thu thập.

### Bước 4 — Xác minh hiện trạng trong ngân sách thử đã giới hạn

Sử dụng cơ chế xác minh credential hoặc thử xác thực được hỗ trợ, với quyền và số lần thử được kiểm soát. Xác định trước chính sách khóa tài khoản, độ trễ và cách dừng nếu có lỗi.

Không thử lần lượt nhiều mật khẩu lịch sử. Không chạy đồng thời nhiều worker kiểm tra cùng một tài khoản. Nếu trạng thái chưa rõ, dừng và chuyển sang một phương án phục hồi được phê duyệt.

Kết quả cần phân biệt lỗi credential với các lỗi khác như DNS, mạng, thời gian hệ thống, TLS, account disabled, quyền đăng nhập hoặc cấu hình connector. Mọi lỗi xác thực đều không nên bị quy thành “sai mật khẩu”.

### Bước 5 — Chọn phương án hòa giải

Căn cứ vào bằng chứng, có thể:

1. Xác nhận credential phục hồi vẫn hiện hành và được phép sử dụng.
2. Khôi phục bản credential hiện hành từ nguồn phục hồi được phép, nếu nền tảng có cơ chế phù hợp.
3. Đặt một credential mới ở hệ thống đích bằng đường quản trị hợp lệ, sau đó cập nhật vault và consumer.
4. Thu hồi và cấp mới token, key hoặc chứng thư khi không thể hoặc không nên khôi phục credential cũ.
5. Giữ tài khoản ở trạng thái cô lập để xử lý thủ công nếu chưa đủ điều kiện.

Thao tác cụ thể phụ thuộc loại credential và sản phẩm. Không coi “reconcile” là một lệnh chung luôn có cùng ý nghĩa. Trong một số nền tảng, chức năng mang tên này có thể thay đổi mật khẩu ở đích, vì vậy phải hiểu tác động trước khi thực hiện.

### Bước 6 — Cập nhật consumer và kiểm thử đầu cuối

Với tài khoản dịch vụ, lập danh sách consumer và cách nhận bí mật của từng consumer. Sau khi cập nhật:

- Yêu cầu nạp lại bí mật hoặc tạo kết nối mới theo cơ chế được hỗ trợ.
- Kiểm tra một giao dịch nghiệp vụ đại diện bằng quyền tối thiểu.
- Quan sát lỗi xác thực, retry và khóa tài khoản.
- Xác nhận consumer không phụ thuộc vào một bản bí mật cũ còn sót lại.
- Ghi lại consumer nào đã xác minh và consumer nào còn ngoại lệ.

Không tự động restart mọi service nếu không cần thiết. Việc restart, reload hay làm mới connection pool phải dựa trên cơ chế của ứng dụng và kế hoạch phục hồi.

### Bước 7 — Mở lại theo từng nhóm và tiếp tục giám sát

Chỉ mở lại những tài khoản đạt gate. Bắt đầu bằng nhóm canary phù hợp, sau đó mở rộng theo mức độ quan trọng và phụ thuộc.

Trước khi bật rotation trở lại, xác nhận không có job đối soát đang dở, không có hai bên cùng điều khiển và consumer đã sẵn sàng nhận thay đổi tiếp theo. Tiếp tục giám sát ít nhất qua các chu kỳ liên quan đã được xác định: nạp lại bí mật, tạo kết nối mới, job định kỳ và rotation.

## 8. Ma trận quyết định khi vault và đích lệch nhau

| Hiện trạng quan sát | Cách xử lý phù hợp | Điều không được kết luận vội |
|---|---|---|
| Credential trong vault xác thực được, policy hợp lệ, không có chỉ dấu thu hồi | Kiểm tra consumer và đường truy cập trước khi mở lại | Một lần login thành công là đủ cho mọi consumer |
| Credential trong vault thất bại, có bằng chứng rotation sau backup | Xác minh nguồn hiện hành hoặc đặt credential mới qua đường quản trị hợp lệ | Đích phải bị rollback để khớp vault |
| Credential dùng được nhưng thuộc diện nghi lộ hoặc đã có lệnh thu hồi | Thu hồi/thay mới theo quyết định sự cố, cập nhật consumer | Còn dùng được nghĩa là an toàn |
| Cả vault và đích đều không rõ phiên bản | Cô lập, điều tra và chọn phương án cấp mới có kiểm soát | Thử các bản mật khẩu cũ cho tới khi có bản thành công |
| Consumer đang hoạt động nhưng kết nối mới thất bại | Kiểm tra cache, pool và đường lấy bí mật | Dịch vụ còn chạy nghĩa là trạng thái đã đồng bộ |
| Phiên bản đã đồng bộ nhưng policy là bản cũ | Đối soát chính sách, phê duyệt và quyền hiện hành | Đồng bộ mật khẩu nghĩa là đã phục hồi PAM đầy đủ |
| Không có quyền quản trị hợp lệ để đặt lại credential | Dùng quy trình break-glass hoặc escalation đã định | Tự tạo tài khoản quyền cao ngoài kiểm soát |

Một quyết định hòa giải nên nêu rõ lý do, tác động, phạm vi và phương án phục hồi khi thao tác thất bại. Đối với tài khoản có nhiều consumer, cần có kế hoạch xử lý trạng thái hoàn tất một phần.

## 9. Những lưu ý theo loại credential

### 9.1. Mật khẩu quản trị và tài khoản dịch vụ

Mật khẩu thường chỉ có một giá trị hiện hành, nhưng không nên giả định như vậy cho mọi hệ thống: một số môi trường có cơ chế chuyển tiếp hoặc nhiều đường xác thực khác nhau.

Khi cần đặt mật khẩu mới:

1. Xác định đường quản trị có quyền đặt lại.
2. Giữ quyền sử dụng đường đó trong phạm vi và thời hạn phục hồi.
3. Thực hiện thay đổi theo cơ chế được hỗ trợ.
4. Xác minh mật khẩu mới ở đích.
5. Công bố đúng phiên bản trong vault.
6. Đồng bộ consumer và kiểm thử.
7. Đóng quyền tạm thời, lưu bằng chứng và tiếp tục theo dõi.

Nếu bước cập nhật vault thất bại sau khi đích đã đổi, không được đánh dấu hoàn tất hay tự chuyển sang dùng bản cũ. Giữ trạng thái trung gian rõ ràng, bảo vệ credential mới bằng cơ chế phục hồi được phép và tiếp tục từ bằng chứng thực tế.

### 9.2. SSH key

Đối soát cần bao gồm private key được bảo vệ, public key được chấp nhận ở đúng tài khoản, fingerprint và phạm vi cài đặt.

Nếu private key đã nghi lộ, việc phục hồi lại key đó không giải quyết sự cố. Cần cấp key mới và thu hồi public key cũ ở mọi đích trong phạm vi. Một key cũ bị bỏ sót trên một máy vẫn có thể tạo đường truy cập ngoài dự kiến.

Không chỉ kiểm tra một file trên đĩa nếu hệ thống còn có nguồn phân phối key tập trung hoặc cơ chế xác thực khác.

### 9.3. API token và credential ngắn hạn

Token có thể đã hết hạn hoặc bị thu hồi độc lập với vault. Snapshot chứa token không làm mới thời hạn và không đảo ngược trạng thái thu hồi tại issuer.

Khi cấp mới, kiểm tra scope, audience, thời hạn và consumer sử dụng. Không cấp token rộng hơn hoặc sống lâu hơn chỉ để đơn giản hóa phục hồi.

Không dùng token thật trong ticket, bản ghi đối soát hay ví dụ kiểm tra. Bằng chứng nên ghi token reference hoặc định danh an toàn do nền tảng cung cấp.

### 9.4. Chứng thư và danh tính dựa trên CA

Cần kiểm tra private key tương ứng, hiệu lực thời gian, chuỗi tin cậy, trạng thái thu hồi theo cơ chế áp dụng và danh tính được chứng thư đại diện.

Một chứng thư chưa hết hạn vẫn có thể không còn được tin cậy hoặc thuộc diện đã thu hồi. Nếu CA, trust store hoặc thành phần xác minh cũng được restore, phạm vi đối soát phải bao gồm các thay đổi đó.

### 9.5. Grant JIT và phiên đang tồn tại

Restore không được cấp lại một grant đã hết hạn hoặc làm thời hạn tính lại từ thời điểm phục hồi. Cần đối chiếu thời gian hết hạn gốc với thời gian thực và quyết định phê duyệt.

Đổi mật khẩu hoặc thu hồi credential cũng không mặc định chấm dứt mọi phiên, session token hay kết nối đang tồn tại. Phải kiểm tra cơ chế của từng đích và xử lý phiên theo quyết định phục hồi, đặc biệt trong kịch bản nghi xâm nhập.

## 10. Ví dụ đầy đủ: tài khoản dịch vụ báo cáo

### Bối cảnh

Tài khoản `svc-report` được PAM quản lý, dùng để truy cập một database báo cáo với quyền đọc giới hạn. Hai consumer là `report-api` và `report-batch`.

Backup vault tại 01:00 chứa V17. Rotation lúc 01:20 chuyển tài khoản sang V18; hai consumer đã nhận V18. Sau sự cố, vault được restore từ mốc 01:00, còn database và consumer không bị restore.

### Phát hiện

Trong giai đoạn cô lập, nhóm phục hồi đối chiếu audit độc lập và phát hiện rotation sau backup. Họ không mở lại job rotation và không thử hàng loạt V17.

Một phép xác minh được kiểm soát xác nhận credential phục hồi không đăng nhập được. Bằng chứng rotation cho biết đã có thay đổi, nhưng nguồn phục hồi được phép không cung cấp lại giá trị V18 cho vault.

Trạng thái lúc này:

```text
Vault:       V17
Database:    trạng thái sau rotation V18
report-api:  đang dùng V18
report-batch:đang dùng V18
Kết luận:    chưa nhất quán; chưa cho phép PAM phục vụ tài khoản này
```

### Quyết định hòa giải

Nhóm database và chủ sở hữu ứng dụng phê duyệt cấp V19 qua một đường quản trị phục hồi hợp lệ. Thời điểm thực hiện được phối hợp để hai consumer nhận thay đổi trong cùng cửa sổ kiểm soát.

Quy trình:

1. Giữ tài khoản trong nhóm phục hồi, giới hạn truy cập mới qua PAM.
2. Xác nhận danh sách đầy đủ consumer và cơ chế nạp lại bí mật.
3. Đặt V19 ở database bằng đường quản trị đã được phê duyệt.
4. Xác minh V19 ở database bằng một phép thử giới hạn.
5. Cập nhật vault để phiên bản hiện hành là V19.
6. Cho `report-api` nạp lại bí mật và tạo một kết nối mới.
7. Cho `report-batch` thực hiện một job kiểm thử đại diện bằng V19.
8. Kiểm tra quyền tài khoản vẫn chỉ trong phạm vi đọc cần thiết.
9. Xác nhận trạng thái V18 không còn hợp lệ theo cơ chế xác thực áp dụng; xử lý các phiên cũ nếu yêu cầu phục hồi đặt ra.
10. Mở lại đường sử dụng qua PAM, tiếp tục giám sát rồi bật rotation theo kế hoạch.

Sau đó, cả ba phía vault, database và consumer đều dùng trạng thái V19 đã xác minh. Hồ sơ ghi các reference của phiên bản, kết quả và người thực hiện; không ghi giá trị V17, V18 hay V19.

### Nếu một consumer cập nhật thất bại

Giả sử `report-api` đã dùng V19 nhưng `report-batch` vẫn dùng V18. Không đánh dấu toàn tài khoản “đã hoàn tất”.

Cần giữ rõ trạng thái từng consumer, hạn chế retry của batch để tránh khóa tài khoản và sửa đường nạp bí mật. Không đổi database về V18 một cách tự phát vì sẽ làm consumer đã chuyển sang V19 lỗi và có thể khôi phục credential không còn được phép dùng.

Nếu phải thay đổi phương án phục hồi, phải có quyết định mới dựa trên hiện trạng, tác động và phạm vi được phép. Trong nhiều trường hợp, tiếp tục đưa consumer còn lại sang phiên bản mới là hướng hợp lý hơn rollback bí mật, nhưng lựa chọn cụ thể cần dựa trên thiết kế hệ thống.

## 11. Thiết kế trạng thái và tự động hóa đối soát

Một bảng trạng thái đơn giản giúp tránh việc công cụ tự động công bố thành công quá sớm:

```text
UNKNOWN
   |
   v
ISOLATED
   |
   v
ASSESSING
   |
   +----> MANUAL_REVIEW / BLOCKED
   |
   v
RECONCILING
   |
   v
VERIFYING
   |
   +----> MANUAL_REVIEW / BLOCKED
   |
   v
READY
   |
   v
MONITORED
```

Đây là mô hình vận hành minh họa. Tên trạng thái không cần giống một sản phẩm cụ thể; điều quan trọng là điều kiện chuyển trạng thái và bằng chứng đi kèm.

Một hệ thống tự động hóa có thể sử dụng logic khái quát:

```text
for each account in approvedRecoveryScope:
    acquireExclusiveRecoveryOwnership(account)

    verifyTargetIdentity(account)
    inspectRotationAndRevocationEvidence(account)

    if account.hasCompromiseIndicator:
        routeToApprovedRevocationAndReissuePlan(account)
    else:
        assessCurrentCredentialWithBoundedAttempts(account)
        executeApprovedReconciliationIfNeeded(account)

    verifyCurrentCredentialThroughIntendedPath(account)
    verifyPolicyAndOriginalExpiry(account)
    verifyAllRequiredConsumers(account)
    verifySupersededAccessHandledByApprovedPlan(account)

    if everyRequiredGatePasses:
        markReadyWithEvidence(account)
    else:
        keepRestrictedAndRecordUnresolvedItems(account)

    releaseExclusiveRecoveryOwnership(account)
```

Đây là giả mã, không phải lệnh chạy trực tiếp. Khi triển khai cần bổ sung:

- Một chủ thể điều khiển thay đổi trên mỗi tài khoản.
- Giới hạn số lần thử và tốc độ theo chính sách đích.
- Timeout và điều kiện dừng.
- Phân biệt lỗi credential với lỗi kết nối hoặc cấu hình.
- Ghi trạng thái trước và sau từng bước có tác động.
- Khả năng tiếp tục từ trạng thái hoàn tất một phần.
- Kiểm soát truy cập tới log và bằng chứng.
- Không đưa giá trị bí mật vào thông báo lỗi.

“Retry an toàn” phải dựa trên việc biết thao tác trước đã hoàn tất ở phía nào. Không lặp lại một lệnh rotation chỉ vì client timeout: đích có thể đã nhận thay đổi dù client chưa nhận phản hồi.

## 12. Gate xác minh trước khi mở lại

Có thể dùng bộ tiêu chí sau cho mỗi tài khoản hoặc nhóm tài khoản có cùng kế hoạch phục hồi:

| Gate | Bằng chứng cần có | Khi chưa đạt |
|---|---|---|
| Đúng tài khoản và đích | Account reference, target reference, môi trường đã xác minh | Giữ cô lập và sửa ánh xạ |
| Đọc được credential theo đường hợp lệ | Kết quả kiểm tra giải mã/truy xuất qua cơ chế được phép | Chưa cấp quyền sử dụng |
| Credential hiện hành xác thực được | Kết quả phép thử giới hạn và thời điểm kiểm tra | Phân loại nguyên nhân, đối soát tiếp |
| Không hồi sinh quyền cũ | Kết quả kiểm tra policy, grant, thời hạn và phê duyệt | Sửa theo nguồn thẩm quyền hiện hành |
| Consumer bắt buộc hoạt động | Kết quả kết nối mới và giao dịch đại diện của từng consumer | Giữ trạng thái chưa hoàn tất |
| Credential/phiên cũ được xử lý | Bằng chứng thu hồi, hết hạn hoặc xử lý phiên theo kế hoạch | Chưa kết luận phục hồi truy cập an toàn |
| Rotation có thể tiếp tục | Một bên điều khiển, lịch và consumer sẵn sàng | Chưa bật tự động hóa |
| Có thể truy vết quyết định | Evidence reference, người thực hiện, người chấp nhận | Hoàn thiện hồ sơ trước bàn giao |

Không bắt buộc đưa mọi tài khoản về READY cùng lúc. Có thể phục hồi theo từng nhóm, nhưng báo cáo phải nêu rõ số đã xác minh, số đang cô lập và ngoại lệ đang được chấp nhận. Tỷ lệ thành công chung không được che khuất một tài khoản quản trị quan trọng chưa được đối soát.

## 13. Bằng chứng và bàn giao vận hành

Hồ sơ phục hồi nên cho phép một người không tham gia trực tiếp trả lời được:

- Đã dùng bản backup nào, của thành phần nào và ở mốc nào?
- Những hệ thống nào không bị restore?
- Thay đổi sau backup được tái dựng từ nguồn nào?
- Đã chọn nguồn quyết định nào cho credential, quyền và thu hồi?
- Tài khoản nào được xác minh, bằng cách nào và vào lúc nào?
- Consumer nào đã kiểm tra bằng kết nối mới?
- Những quyền tạm thời, phiên cũ và credential cũ đã được xử lý ra sao?
- Có ngoại lệ nào còn mở và ai chịu trách nhiệm?
- Rotation và các luồng cấp phát được mở lại lúc nào?
- Ai chấp nhận kết quả bàn giao?

Không ghi mật khẩu, private key, token, response chứa bí mật hoặc ảnh màn hình lộ credential vào hồ sơ. Ngay cả việc tạo hash trực tiếp từ mật khẩu để “so sánh cho tiện” cũng không nên tự phát; dùng version identifier, fingerprint phù hợp với loại khóa hoặc reference an toàn được nền tảng cung cấp.

Sau bàn giao, giám sát tập trung vào lỗi xác thực mới, account lockout, rotation thất bại, consumer còn dùng phiên bản cũ và các đường truy cập đặc quyền ngoài kế hoạch. Thời gian quan sát phải đủ bao phủ những consumer hoặc job không chạy liên tục.

## 14. Những sai lầm cần tránh

### “Restore xong, giao diện xanh là được”

Health check ứng dụng không kiểm tra toàn bộ quan hệ credential với đích và consumer. Cần gate ở cấp tài khoản và đường sử dụng.

### “Lấy snapshot mới nhất rồi mở lại toàn bộ”

Snapshot mới nhất vẫn có thể đi trước một lần rotation hoặc đi trước quyết định thu hồi. Phải đối soát cửa sổ thay đổi và trạng thái hiện tại.

### “Đổi hết về mật khẩu trong backup cho đồng bộ”

Cách này có thể phục hồi mật khẩu đã lộ, phá consumer đang dùng phiên bản mới và làm mất dấu trạng thái thực tế. Sự nhất quán phải hướng tới một trạng thái được phép sử dụng, không chỉ tới hai nơi giữ cùng một giá trị.

### “Nếu login lỗi thì cứ thử lại”

Retry không giới hạn có thể khóa tài khoản và làm sự cố lan rộng. Cần ngân sách thử, phân loại lỗi và điều kiện dừng.

### “Đã đổi mật khẩu thì mọi phiên cũ đều mất hiệu lực”

Không phải hệ thống nào cũng chấm dứt mọi phiên hoặc token khi đổi mật khẩu. Phải kiểm tra và xử lý các phiên còn tồn tại theo cơ chế thực tế.

### “Service còn chạy nên consumer đã đồng bộ”

Kết nối cũ hoặc credential cache có thể che lỗi. Cần kiểm thử kết nối mới và một giao dịch đại diện.

### “Đã khớp credential thì bật rotation ngay”

Rotation mới có thể xung đột với job phục hồi còn dở hoặc consumer chưa cập nhật. Chỉ bật lại khi quyền điều khiển và các gate đã rõ ràng.

## 15. Bài thực hành tư duy

Một vault được backup lúc 03:00. Tài khoản quản trị máy chủ được rotation lúc 03:15. Token phục vụ một job tự động bị thu hồi lúc 03:25 vì nghi lộ. Quyền JIT của một kỹ sư hết hạn lúc 03:30. Vault được restore về mốc 03:00 lúc 04:00; các hệ thống đích và issuer token không bị restore.

Hãy xác định cách xử lý cho từng đối tượng.

**Tài khoản quản trị:** credential trong snapshot có nguy cơ không khớp đích. Cần đối chiếu rotation, xác minh có giới hạn và chọn phương án hòa giải phù hợp. Không mặc định ép đích trở về credential lúc 03:00.

**Token của job:** bản sao token xuất hiện lại trong vault không làm token hết bị thu hồi. Phải giữ quyết định thu hồi, kiểm tra phạm vi ảnh hưởng và cấp mới theo quy trình được phê duyệt nếu job cần tiếp tục.

**Quyền JIT:** grant đã hết hạn ở thời gian thực. Không cho phép restore làm kỹ sư có thêm thời gian quyền. Nếu cần truy cập phục hồi, phải có một grant hợp lệ theo quy trình hiện hành.

**Báo cáo phục hồi:** phải nêu rõ ba loại xử lý riêng biệt: đồng bộ credential, duy trì thu hồi và bảo toàn thời hạn quyền. Không dùng một kết quả “vault đã restore thành công” để thay cho cả ba.

## 16. Kết luận

Credential consistency sau restore là việc đưa vault, nơi xác thực, consumer và cơ chế cấp quyền về một trạng thái hiện hành có thể chứng minh. Trạng thái đó phải vừa hoạt động được, vừa tuân theo quyết định thu hồi và phạm vi quyền được phép.

Một quy trình tốt bắt đầu bằng cô lập, tái dựng thay đổi, đối soát từng tài khoản và chọn phương án hòa giải có kiểm soát. Nó chỉ kết thúc khi đường sử dụng thực tế đã được kiểm thử, các consumer bắt buộc đã đồng bộ, quyền cũ không bị hồi sinh và bằng chứng đủ để bàn giao vận hành.
