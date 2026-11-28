# Elevation by hash

## 1. Mục tiêu và tình huống sử dụng

Elevation by hash là cách nhận diện chính xác một tệp đã được phê duyệt bằng giá trị băm, rồi dùng nhận diện đó làm điều kiện cho phép tiến trình chạy với quyền cao hơn. Trong Endpoint PAM, cơ chế này giúp người dùng giữ tài khoản tiêu chuẩn nhưng vẫn thực hiện được một tác vụ quản trị cụ thể, chẳng hạn sửa cấu hình thiết bị hoặc chạy công cụ bảo trì.

Giả sử nhóm hỗ trợ cần dùng công cụ nội bộ AcmeDeviceRepair phiên bản 2.4.1 để sửa dịch vụ của một thiết bị. Công việc chỉ phát sinh vài lần mỗi tháng. Thay vì cấp local administrator lâu dài cho cả nhóm, tổ chức có thể phê duyệt đúng bản công cụ, đúng nhóm hỗ trợ, đúng các máy được quản lý và đúng cách sử dụng đã kiểm thử.

Tên công cụ, nhóm người dùng, rule và mã thay đổi trong bài đều là dữ liệu minh họa. Chúng không đại diện cho một sản phẩm hoặc gói phần mềm có thật.

Sau bài học, người học có thể:

- Phân biệt nhận diện tệp bằng hash với quyết định cho phép nâng quyền.
- Thu thập SHA-256 từ bản phần mềm có nguồn gốc được kiểm chứng.
- Thiết kế rule có phạm vi người dùng, thiết bị và hành vi rõ ràng.
- Phân tích giới hạn của hash trước tham số, thư viện, plugin và tiến trình con.
- Cập nhật, thu hồi và lưu bằng chứng cho một rule theo vòng đời phần mềm.
- Thiết lập thử nghiệm cho cả trường hợp được phép lẫn trường hợp phải bị chặn.

## 2. Hash giải quyết câu hỏi nào?

Một hàm băm mật mã nhận nội dung đầu vào và tạo ra một giá trị có độ dài cố định. Với SHA-256, kết quả có 256 bit, thường biểu diễn bằng 64 ký tự thập lục phân.

~~~text
H = SHA256(các byte của tệp)
~~~

Trong rule dựa trên hash, quản trị viên lưu giá trị băm của bản đã được duyệt. Khi có yêu cầu nâng quyền, cơ chế thực thi kiểm tra tệp đích theo cách mà sản phẩm hỗ trợ và đối chiếu với điều kiện của rule.

~~~text
Tệp được phê duyệt ── SHA-256 ──> hash chuẩn trong rule
Tệp được yêu cầu   ── SHA-256 ──> hash quan sát

Hash trùng + các điều kiện còn lại đạt → có thể cho phép nâng quyền
Hash khác hoặc điều kiện không đạt    → không cấp quyền theo rule này
~~~

Hash trả lời câu hỏi: “Nội dung được kiểm tra có khớp với bản đã được phê duyệt hay không?”. Nó không tự trả lời: “Bản đó có đáng tin không?”, “Ai được dùng?” hay “Công cụ sẽ làm gì sau khi chạy?”.

### 2.1. Hash gắn với nội dung

Với phép băm SHA-256 toàn bộ tệp:

- Đổi tên hoặc di chuyển tệp mà không đổi nội dung không làm đổi hash.
- Thay đổi nội dung làm kết quả băm gần như chắc chắn thay đổi.
- Hai tệp có cùng tên và cùng chuỗi phiên bản vẫn có thể có hash khác nhau.
- Các bản x86, x64 hoặc các gói được đóng lại có thể là những artifact khác nhau.

Đổi tên một tệp thành tên ứng dụng được phép không đủ để vượt qua kiểm tra hash. Ngược lại, nếu rule chỉ xét hash, bản sao nguyên vẹn của tệp đã duyệt vẫn có thể thỏa điều kiện nội dung ở vị trí khác.

Một số cơ chế nhận diện hoặc chữ ký có quy tắc tính digest riêng. Không mặc định mọi trường “hash” đều tương đương phép băm toàn bộ byte của Get-FileHash. Khi triển khai, cần kiểm tra thuật toán, đối tượng được băm và định dạng mà chính agent yêu cầu.

### 2.2. Chọn thuật toán và định dạng phù hợp

Trong thiết kế mới của bài này, dùng SHA-256 và lưu tên thuật toán cùng digest. Không rút ngắn hash khi đưa vào rule hoặc so sánh. Có thể chuẩn hóa chữ hoa, chữ thường trong biểu diễn hex; không bỏ bớt ký tự hoặc so khớp theo tiền tố.

PowerShell cung cấp Get-FileHash để tính digest. Tài liệu Microsoft nêu SHA-256 là mặc định và khuyến cáo không dùng MD5, SHA-1 cho việc bảo vệ tệp trước tấn công hoặc sửa đổi có chủ ý. [Tài liệu Get-FileHash](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/get-filehash?view=powershell-7.5).

Giá trị băm là định danh nội dung có độ tin cậy thực tế cao khi dùng thuật toán phù hợp, không phải bảo đảm toán học rằng không thể tồn tại va chạm. Trong vận hành PAM, sai nguồn artifact hoặc sai phạm vi cấp quyền thường là vấn đề trực tiếp hơn việc tạo được va chạm SHA-256.

### 2.3. Không nhầm với pass-the-hash

Elevation by hash trong bài này liên quan đến hash của tệp thực thi hoặc artifact được quản lý. Pass-the-hash liên quan đến lạm dụng vật liệu xác thực để truy cập dưới danh tính khác. Hai khái niệm khác đối tượng, mục đích và biện pháp kiểm soát.

Không đưa password hash, credential hay bí mật xác thực vào rule nhận diện ứng dụng. Digest của tệp không phải mật khẩu quản trị.

## 3. Nhận diện đúng chưa đồng nghĩa cấp quyền đúng

Có thể diễn đạt yêu cầu cấp quyền bằng mô hình:

~~~text
Cho phép nâng quyền =
    artifact khớp bản đã duyệt
    AND người yêu cầu thuộc phạm vi được phép
    AND thiết bị thuộc phạm vi được phép
    AND rule còn hiệu lực và đã được áp dụng
    AND ngữ cảnh thực thi đáp ứng điều kiện
    AND phương thức xác nhận/phê duyệt đã hoàn thành
~~~

Đây là mô hình yêu cầu, không phải cú pháp hoặc thứ tự xử lý chung của mọi sản phẩm. Từng điều kiện phải được ánh xạ vào khả năng thực tế của giải pháp Endpoint PAM. Nếu một điều kiện quan trọng không thực thi được, cần đổi cách cung cấp tác vụ thay vì chỉ ghi nó trong tài liệu.

| Câu hỏi | Bằng chứng minh họa | Sai lầm thường gặp |
|---|---|---|
| Đây là tệp nào? | SHA-256 và artifact chuẩn | Chỉ nhìn tên tệp |
| Vì sao tệp được tin cậy cho tác vụ? | Nguồn phát hành, kiểm thử, người duyệt | Có hash thì cho là an toàn |
| Ai được nâng quyền, ở đâu? | Nhóm hỗ trợ, nhóm thiết bị, thời hạn | Cấp rule cho toàn bộ người dùng |
| Quyền được dùng để làm gì? | Chức năng, đầu vào, thành phần phụ thuộc | Chỉ kiểm tra tiến trình mở được |

Hash không biến chương trình thành sandbox. Công cụ có quyền quản trị và có chức năng tùy ý sửa hệ thống vẫn có thể thực hiện thay đổi ngoài mục tiêu ban đầu. Để áp dụng least privilege, phải đánh giá năng lực thực tế của chương trình.

Cũng không mặc định nâng quyền tương đương thêm người dùng vào nhóm Administrators. Giải pháp có thể dùng một ngữ cảnh hoặc tài khoản thực thi khác. Bằng chứng kiểm toán cần nối được người yêu cầu với tiến trình nhận quyền, kể cả khi danh tính yêu cầu và danh tính thực thi không giống nhau.

## 4. Khi nào nên dùng rule dựa trên hash?

Hash phù hợp khi cần gắn sự cho phép với một artifact cụ thể và tổ chức có khả năng quản lý từng lần cập nhật.

| Tình huống | Mức phù hợp | Điểm cần xử lý |
|---|---|---|
| Công cụ nội bộ ít thay đổi, tác vụ hẹp | Tốt | Lưu bản phát hành và owner |
| Bản vá cần dùng trong thời gian ngắn | Tốt | Có thời hạn và thu hồi sau tác vụ |
| Ứng dụng cập nhật thường xuyên | Có thể dùng | Tự động hóa tiếp nhận và duyệt hash mới |
| Bộ cài tải thêm payload | Cần phân tích | Hash bootstrapper chưa bao phủ mọi thành phần |
| Shell, trình thông dịch, công cụ quản trị đa năng | Rủi ro cao | Tệp đúng vẫn có thể chạy nội dung tùy ý |
| Công cụ lạ do người dùng gửi | Chưa đủ điều kiện | Xác minh nguồn và nhu cầu trước |

Rule theo publisher hoặc chữ ký có thể giảm công việc cập nhật khi phần mềm đổi phiên bản, nhưng phạm vi tin cậy cũng thay đổi. Chuyển từ một artifact cụ thể sang một tập phần mềm rộng hơn là quyết định cấp quyền mới cần được đánh giá.

Microsoft Intune EPM là một ví dụ có rule nhận diện bằng hash và thiết lập riêng cho tiến trình con. Tài liệu sản phẩm khuyến nghị dùng thuộc tính nhận diện mạnh và tránh rule quá rộng cho ứng dụng có thể khởi chạy chương trình khác. [Tạo elevation rule trong Intune EPM](https://learn.microsoft.com/en-us/intune/epm/create-elevation-rules).

Các phần tiếp theo là quy trình thiết kế và tình huống minh họa cho Endpoint PAM. Không giả định mọi sản phẩm có cùng trường cấu hình, khả năng giới hạn hay cách xử lý xung đột.

## 5. Xây dựng chuỗi tin cậy cho hash chuẩn

### 5.1. Hash do người yêu cầu gửi chưa phải hash đã phê duyệt

Người dùng có thể gửi tên tệp, hash và lý do sử dụng để mở yêu cầu. Thông tin đó giúp định vị sự việc nhưng chưa chứng minh artifact đáng tin.

Nếu ai cũng có thể gửi hash của một chương trình rồi được cấp quyền, hệ thống chỉ thay thao tác “cho chạy tệp” bằng “cho chạy hash của tệp”. Tính digest không bổ sung một nguồn tin cậy độc lập.

Trong ví dụ, nhóm quản lý phần mềm lấy AcmeDeviceRepair 2.4.1 từ kho phát hành nội bộ đã xác minh, thay vì trực tiếp dùng bản đính kèm do người yêu cầu cung cấp. Sau đó mới tính hash và kiểm thử.

### 5.2. Hồ sơ phê duyệt artifact

Hồ sơ nên nối được:

1. Tác vụ cần thực hiện và lý do cần quyền cao.
2. Chủ sở hữu nghiệp vụ và người chịu trách nhiệm kỹ thuật.
3. Nguồn phát hành, phiên bản, kiến trúc, thời điểm tiếp nhận.
4. Artifact được lưu tại kho có kiểm soát thay đổi.
5. Thuật toán và hash tính từ chính artifact đó.
6. Kết quả kiểm tra chữ ký, quét mã độc và kiểm thử, nếu áp dụng.
7. Người duyệt, ticket thay đổi và phạm vi cấp quyền.
8. Kế hoạch cập nhật, thu hồi và xử lý sự cố.

Chữ ký hợp lệ không đồng nghĩa mọi chức năng của phần mềm đều phù hợp để được nâng quyền. Tệp không có chữ ký cũng không thể được cho phép chỉ vì hash rất cụ thể. Tổ chức cần xác lập lý do tin cậy và chấp nhận rủi ro của chính artifact đó.

Artifact và bản ghi hash cùng nằm ở vị trí mà người yêu cầu có quyền sửa không tạo thành hai nguồn kiểm chứng độc lập. Phải bảo vệ cả bản phần mềm chuẩn lẫn hồ sơ phê duyệt.

### 5.3. Tách quyền đề xuất và quyền phát hành

Người yêu cầu dùng công cụ không nên tự duyệt việc nâng quyền của mình. Với tác vụ nhạy cảm, có thể tách người xác minh artifact khỏi người phát hành chính sách.

Nhóm phần mềm xác nhận bản phát hành, chủ hệ thống xác nhận nhu cầu, người quản trị PAM triển khai đúng phạm vi. Khi tổ chức nhỏ không thể tách mọi vai trò, vẫn cần lưu dấu người thực hiện và một bước rà soát độc lập phù hợp.

## 6. Thu thập SHA-256 bằng PowerShell

Các lệnh dưới đây minh họa việc đọc thuộc tính và tính hash trên máy thí nghiệm hoặc máy chuẩn bị artifact. Chúng không tạo rule, không cấp quyền và không chạy công cụ đích.

Giả sử artifact đã được tiếp nhận vào thư mục được bảo vệ:

~~~powershell
$artifactPath = 'C:\PAM-Lab\Approved\AcmeDeviceRepair-2.4.1.exe'

$artifact = Get-Item -LiteralPath $artifactPath -ErrorAction Stop
$digest = Get-FileHash -LiteralPath $artifactPath -Algorithm SHA256 -ErrorAction Stop

[pscustomobject]@{
    FileName  = $artifact.Name
    FullPath  = $artifact.FullName
    SizeBytes = $artifact.Length
    Algorithm = $digest.Algorithm
    SHA256    = $digest.Hash
}
~~~

LiteralPath xử lý đường dẫn như giá trị nguyên văn. Chỉ định SHA256 rõ ràng giúp hồ sơ không phụ thuộc vào việc người đọc nhớ thuật toán mặc định.

Có thể rút gọn digest khi trình bày trên sơ đồ. Trong rule chính thức phải dùng đủ 64 ký tự hex. Các ký hiệu H1, H2 trong bài chỉ phục vụ diễn giải.

### 6.1. So sánh với digest được duyệt

Ví dụ tiếp theo yêu cầu nhập digest chuẩn từ hồ sơ phê duyệt độc lập. Giá trị vừa tính từ artifact không tự trở thành giá trị chuẩn.

~~~powershell
$artifactPath = 'C:\PAM-Lab\Approved\AcmeDeviceRepair-2.4.1.exe'
$expectedHash = (Read-Host 'Nhap SHA-256 tu ho so da duyet').Trim()

if ($expectedHash -notmatch '\A[0-9A-Fa-f]{64}\z') {
    throw 'Digest chuan phai gom dung 64 ky tu hex.'
}

$actualHash = (Get-FileHash -LiteralPath $artifactPath -Algorithm SHA256 -ErrorAction Stop).Hash

if (-not [string]::Equals(
    $expectedHash,
    $actualHash,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw 'Hash khong khop. Dung quy trinh, khong tu thay digest chuan.'
}

[pscustomobject]@{
    Artifact = $artifactPath
    SHA256   = $actualHash
    Match    = $true
}
~~~

Match bằng true chỉ xác nhận phép đối chiếu trong lần đọc này. Nó không chứng minh nguồn artifact, không thay bước duyệt và không bảo vệ khoảng thời gian từ kiểm tra đến thực thi.

Không dùng mô hình “tính hash rồi Start-Process -Verb RunAs” như một cơ chế Endpoint PAM tự xây. Quyết định phải gắn với tệp thực sự được thực thi qua thành phần tin cậy của giải pháp. Script trong ngữ cảnh người dùng không thay thế được ranh giới bảo vệ đó.

### 6.2. Xử lý kết quả không khớp

Hash khác bản chuẩn có thể do chọn sai bản, tự cập nhật, đóng gói lại, tệp bị hỏng hoặc thay đổi trái phép.

Hash mismatch là lý do không cấp quyền theo rule cũ, chưa đủ để kết luận có mã độc. Cần giữ bằng chứng và xác minh nguyên nhân. Không tự động lấy hash mới thay cho hash đã được duyệt.

## 7. Thiết kế rule cho tác vụ cụ thể

Trước hết thử tác vụ bằng tài khoản tiêu chuẩn để xác định phần nào thực sự cần quyền cao. Nếu ứng dụng chỉ ghi vào thư mục dữ liệu bị cấu hình sai quyền, sửa thiết kế lưu trữ có thể thích hợp hơn việc nâng toàn bộ ứng dụng.

Giả sử AcmeDeviceRepair thực sự cần sửa một dịch vụ máy. Nhóm quản trị lập bản thiết kế:

| Thành phần | Giá trị minh họa | Mục đích |
|---|---|---|
| Artifact | AcmeDeviceRepair 2.4.1 x64 | Chốt đúng bản kiểm thử |
| Nhận diện | SHA-256 H1, theo cách agent yêu cầu | Gắn rule với artifact chuẩn |
| Người được dùng | Endpoint-Support-L2 | Thu hẹp đối tượng |
| Thiết bị | Workstation-Repair-Pilot | Triển khai ban đầu có giới hạn |
| Vị trí | Thư mục có ACL bảo vệ | Giảm khả năng sửa thành phần |
| Cách nâng quyền | Người dùng khởi tạo, có lý do | Ghi nhận nhu cầu |
| Tiến trình con | Chỉ thành phần đã duyệt nếu cần | Kiểm soát quyền lan truyền |
| Thời hạn | Theo vòng đời bản phát hành và lịch rà soát | Tránh quyền tồn đọng |
| Thu hồi | Có owner và cách xác minh | Dừng sử dụng khi cần |

Bảng này mô tả yêu cầu của tổ chức. Trước khi phát hành phải chỉ ra từng dòng được thực thi bởi agent, cơ chế quản lý thiết bị hay quy trình hỗ trợ. Không coi điều kiện đã được bảo vệ chỉ vì nó xuất hiện trong ticket.

### 7.1. Phối hợp điều kiện nhận diện

Có thể kết hợp hash với vị trí bảo vệ, chữ ký hoặc thuộc tính khác nếu giải pháp hỗ trợ đúng quan hệ logic mong muốn.

Nếu yêu cầu đồng thời hash và đường dẫn, cần xác minh sản phẩm thực sự dùng quan hệ AND. Hai rule độc lập có thể cho phép một tập rộng hơn điều kiện kết hợp trong một rule.

Không tự giả định “deny luôn thắng” hoặc “rule cụ thể nhất luôn thắng”. Cần thử cách giải pháp xử lý rule trùng, kế thừa, thứ tự ưu tiên và chính sách cache. Rule hash hẹp chưa đủ nếu thiết bị còn một đường nâng quyền rộng hơn.

### 7.2. Thời hạn rule khác thời hạn tiến trình

Phân biệt ba mốc:

- Thời hạn người dùng được phép yêu cầu nâng quyền.
- Thời điểm chính sách ngừng cho phép những lần chạy mới.
- Thời gian tiến trình đã nhận quyền tiếp tục tồn tại.

Thu hồi rule không tự bảo đảm tiến trình đang chạy mất quyền hoặc bị dừng. Với công cụ chạy lâu, cần theo dõi tiến trình, xử lý công việc còn lại và kết thúc phiên theo khả năng của nền tảng.

Nếu sản phẩm không có thời hạn trên từng rule, dùng quản lý thay đổi để gỡ rule vào thời điểm đã định và xác minh endpoint nhận chính sách. Nếu yêu cầu là tự hết hạn ngay cả khi máy offline, lịch gỡ ở máy chủ chưa đáp ứng yêu cầu đó.

## 8. Giới hạn: hash không bao phủ toàn bộ hành vi

### 8.1. Tham số dòng lệnh

Một tệp có thể cung cấp cả thao tác hẹp lẫn thao tác mạnh. Hash không đổi khi người dùng đổi tham số.

~~~text
AcmeDeviceRepair.exe --repair-managed-service
AcmeDeviceRepair.exe --load-plugin <duong-dan-do-nguoi-dung-chon>
~~~

Nếu chương trình có chức năng thứ hai và nạp mã tùy ý, duyệt hash của tệp khởi chạy chưa giới hạn quyền vào tác vụ sửa dịch vụ.

Cần kiểm thử tham số, cấu hình và đường dẫn đầu vào. Khi sản phẩm có kiểm soát tham số, xác minh cách so khớp, xử lý dấu ngoặc, đường dẫn tương đương và tùy chọn bổ sung. “Tham số được phép” trong tài liệu không tự trở thành cơ chế cưỡng chế.

Nếu không thể giới hạn đủ hẹp, có thể cung cấp thao tác qua công cụ chuyên dụng hoặc dịch vụ quản trị có giao diện kiểm tra đầu vào. Thành phần đó cũng phải được đánh giá; thêm wrapper không tự làm chương trình gốc an toàn.

### 8.2. DLL, plugin và cấu hình

Hash của EXE không tự đo lường mọi thư viện và plugin được nạp. Nếu thành phần phụ thuộc nằm trong thư mục người dùng có thể sửa, EXE vẫn đúng hash nhưng hành vi có thể bị ảnh hưởng.

Microsoft mô tả nguy cơ ứng dụng nạp DLL từ vị trí mà kẻ tấn công kiểm soát, đặc biệt khi ứng dụng đang chạy với quyền quản trị. [Bảo mật thư viện động trên Windows](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-security).

Cần khảo sát:

- Thư mục chứa EXE và DLL phụ thuộc.
- Thư mục làm việc hiện tại.
- Cấu hình, plugin trong hồ sơ người dùng.
- Đường dẫn do biến môi trường hoặc tham số quyết định.
- File tạm và các giai đoạn giải nén của bộ cài.

Tên đường dẫn giống thư mục hệ thống không chứng minh vị trí được bảo vệ. Phải kiểm tra quyền ghi thực tế và những cách có thể thay đối tượng tại vị trí đó.

### 8.3. Script và trình thông dịch

Nếu chỉ duyệt hash của trình thông dịch, nội dung nó thực thi có thể vẫn do người dùng kiểm soát. Rule cho một chương trình hợp lệ khi đó có thể trở thành quyền chạy mã tùy ý.

Nếu sản phẩm hỗ trợ nhận diện script, cần biết nó kiểm tra script nào và có kiểm soát nội dung tải hoặc gọi tiếp hay không. Script đã duyệt nhưng đọc lệnh từ file cấu hình có thể sửa vẫn có ranh giới tin cậy rộng hơn chính script.

Không diễn giải “một tệp script có hash hợp lệ” thành “mọi lệnh của trình thông dịch được phép chạy với quyền cao”.

### 8.4. Bộ cài và payload tải về sau

Hash của bootstrapper nhận diện tệp khởi động đó, không tự phê duyệt mọi gói nó sẽ tải trong tương lai.

Tác vụ cài đặt có thể gồm nhiều tệp và nhiều tiến trình. Cần kiểm soát nguồn payload, manifest hoặc chữ ký gói, vị trí giải nén và hành vi thành phần con. Triển khai qua kênh quản lý phần mềm tập trung có thể phù hợp hơn việc nâng quyền một downloader.

Nếu hồ sơ ghi hash của gói đóng ngoài nhưng agent đánh giá một tệp đã giải nén, hai đối tượng có thể khác hash. Phải ghi rõ rule áp dụng cho đối tượng nào.

## 9. Kiểm soát tiến trình con và quyền liên quan

Tiến trình đã nâng quyền có thể tạo tiến trình con. Cách kế thừa quyền phụ thuộc vào hệ điều hành và cơ chế quản lý của sản phẩm.

Không giả định mỗi tiến trình con đều được kiểm tra bằng hash vì tiến trình cha dùng rule hash. Chế độ cho mọi tiến trình con kế thừa quyền có thể mở rộng đáng kể phạm vi. Trong Intune EPM, tài liệu nêu tùy chọn cho tiến trình con chạy nâng quyền có thể bỏ qua đánh giá rule của tiến trình con. [Hành vi tiến trình con trong elevation rule](https://learn.microsoft.com/en-us/intune/epm/create-elevation-rules).

Với công cụ minh họa, cần xác định:

1. Tác vụ có cần tạo tiến trình con không?
2. Nếu có, tiến trình nào, từ artifact nào và với đầu vào nào?
3. Người dùng có thể khiến công cụ mở shell, trình duyệt hoặc editor không?
4. Chức năng mở log, trợ giúp hoặc liên kết có gọi chương trình ngoài không?
5. Sau tác vụ có tiến trình hoặc thành phần đặc quyền nào tiếp tục hoạt động không?

Chỉ chọn mode sau khi biết kết quả. Cấm kế thừa quyền có thể ảnh hưởng chức năng, nhưng cho cả cây tiến trình quyền cao để “chạy cho được” là mở rộng cấp quyền.

Ngoài cây tiến trình, ứng dụng còn có thể gửi yêu cầu tới dịch vụ hoặc tác vụ đã có quyền cao. Quan hệ đặc quyền khi đó không thể hiện đầy đủ qua parent-child process. Phải đánh giá giao diện dịch vụ, quyền gọi và kiểm tra đầu vào.

Hash cũng không tách quyền cục bộ khỏi quyền truy cập từ xa. Nếu công cụ dùng token, chứng chỉ hoặc credential để truy cập hệ thống khác, cần đánh giá riêng đường đó. Không nhúng mật khẩu quản trị dùng chung vào công cụ để tránh hỏi người dùng.

## 10. Khoảng thời gian từ kiểm tra đến sử dụng

Một thiết kế thiếu bảo vệ có thể:

~~~text
1. Script tính hash ở đường dẫn X.
2. Đối tượng tại X bị thay sau khi kiểm tra.
3. Thành phần khác chạy đường dẫn X với quyền cao.
~~~

Tệp đã kiểm tra và tệp thực sự chạy có thể không phải cùng đối tượng. Đây là vấn đề kiểm tra trước, sử dụng sau, thường gọi là TOCTOU.

Quyết định cấp quyền phải gắn với đúng artifact được thực thi qua thành phần tin cậy của giải pháp. Một lần tính hash trong script hoặc màn hình hiển thị tên tệp không đủ chứng minh yêu cầu này.

Cần xác minh:

- Agent đánh giá tệp ở thời điểm nào?
- Khi không đọc được tệp hoặc không kiểm tra được toàn vẹn, hành vi là gì?
- Vị trí triển khai có cho phép thay tệp, thư mục hoặc liên kết không?
- Agent và kho chính sách cục bộ có được bảo vệ khỏi sửa đổi không?
- Sự kiện ghi nhận đối tượng đã đánh giá hay chỉ đường dẫn yêu cầu?

Thử nghiệm ranh giới này trong môi trường được phép với artifact vô hại. Không suy từ một lệnh Get-FileHash thành bảo đảm rằng cơ chế thực thi không có khoảng trống.

## 11. Cập nhật phiên bản và quản lý nhiều hash

Giả sử bản 2.4.1 có hash H1 và bản 2.4.2 có hash H2. Hash đổi là điều bình thường khi nội dung đổi. Rule H1 không nên tự chấp nhận H2 chỉ vì tên tệp hoặc nhà phát hành giống nhau.

~~~mermaid
flowchart TD
    A[Tiếp nhận artifact mới] --> B[Xác minh nguồn và tính hash]
    B --> C[Đánh giá thay đổi và kiểm thử]
    C --> D{Được phê duyệt?}
    D -- Không --> E[Giữ bản được phép hiện hành hoặc dừng sử dụng]
    D -- Có --> F[Phát hành rule mới cho nhóm thử nghiệm]
    F --> G[Đo kết quả và kiểm tra phạm vi]
    G --> H[Triển khai artifact mới và rule tương ứng]
    H --> I[Gỡ rule cũ theo kế hoạch]
    I --> J[Xác minh thiết bị nhận chính sách]
~~~

Trong chuyển đổi có thể cho phép cả H1 và H2, nhưng cần lý do, phạm vi và thời hạn. Mỗi hash thêm vào tương ứng một artifact được cấp quyền.

Nếu H1 có lỗ hổng nghiêm trọng, không tự giữ H1 để thuận tiện rollback. Có thể cần dừng chức năng, dùng bản sửa khác hoặc chuyển tác vụ sang quy trình hỗ trợ kiểm soát được.

Với phần mềm cập nhật thường xuyên, có thể tự động tiếp nhận artifact, tính hash và tạo đề xuất thay đổi. Không để trình tự cập nhật trên endpoint tự gửi hash mới rồi được tin ngay. Phải giữ ranh giới giữa thu thập thông tin và phê duyệt quyền.

### 11.1. Quản lý biến thể artifact

Một phiên bản có thể có nhiều bản theo kiến trúc, ngôn ngữ, kênh phát hành hoặc gói đóng lại. Không suy “cùng phiên bản” thành “cùng hash”.

~~~text
Sản phẩm + phiên bản + kiến trúc + biến thể
    → artifact chuẩn
    → thuật toán/hash
    → rule đang cấp quyền
    → nhóm thiết bị nhận bản đó
~~~

Ánh xạ giúp giải thích từ chối sau cập nhật mà không phải cho phép mọi tệp cùng tên.

## 12. Thu hồi và thiết bị offline

Thu hồi gồm ít nhất ba lớp: bỏ quyết định cho phép ở trung tâm, endpoint nhận và áp dụng chính sách mới, rồi xác minh tình trạng các tiến trình đã chạy.

Ticket “đã đóng” không chứng minh cả ba lớp đã hoàn thành.

Khi H1 không còn phù hợp để nâng quyền:

1. Xác định rule và mọi nhóm nhận rule H1.
2. Phát hành thu hồi theo cơ chế sản phẩm.
3. Theo dõi thiết bị chưa đồng bộ hoặc offline.
4. Kiểm tra bằng tài khoản tiêu chuẩn rằng lần chạy mới không còn được rule đó cấp quyền.
5. Xử lý tiến trình đang chạy hoặc thay đổi đã thực hiện nếu cần.
6. Lưu bằng chứng revision có hiệu lực trên các nhóm thiết bị.

Không giả định endpoint offline tự mất quyền ngay khi quản trị viên gỡ rule trên máy chủ. Hành vi phụ thuộc cache, thời hạn, đồng bộ và thiết kế thực thi.

Tổ chức phải quyết định trước có chấp nhận nâng quyền offline hay không, điều kiện hết hạn cục bộ và bằng chứng đồng bộ lại. Nếu sản phẩm không đáp ứng thời hạn bắt buộc, chọn cách cung cấp tác vụ khác.

Rule hash chỉ quản lý một đường cấp quyền. Người dùng còn local admin, credential quản trị hoặc công cụ hỗ trợ cấp quyền rộng vẫn có thể nâng quyền bằng đường khác. Gỡ H1 không tự loại bỏ các đường đó.

## 13. Bằng chứng kiểm toán và giám sát

Mục tiêu là trả lời: ai yêu cầu, trên máy nào, artifact nào được đánh giá, rule nào cho phép, ai duyệt và tiến trình nào nhận quyền.

| Nhóm dữ liệu | Trường minh họa | Giá trị sử dụng |
|---|---|---|
| Danh tính | Người yêu cầu, nhóm được xét, người duyệt | Quy trách nhiệm |
| Thiết bị | Device ID, nhóm quản lý, trạng thái agent | Xác định phạm vi |
| Artifact | Thuật toán, hash đầy đủ, tên, phiên bản, vị trí | Đối chiếu bản chuẩn |
| Chính sách | Rule ID, revision, bản đã áp dụng | Giải thích quyết định |
| Yêu cầu | Thời gian, lý do, ticket, kết quả | Dựng lại chuỗi sự kiện |
| Thực thi | Process ID, thời gian bắt đầu, ngữ cảnh quyền, cây tiến trình | Nối yêu cầu với hành vi |
| Vòng đời | Ngày duyệt, hết hạn, thu hồi, rà soát | Phát hiện quyền tồn đọng |

Không phải agent nào cũng xuất mọi trường. Nếu một trường quan trọng không có, phải nêu giới hạn và cách liên kết thêm, chẳng hạn request ID với log chính sách hoặc dữ liệu EDR. Không báo rằng một tín hiệu đã được thu thập nếu hệ thống không cung cấp nó.

Dòng lệnh có thể chứa dữ liệu nhạy cảm. Cần loại bỏ bí mật trước khi ghi log, giới hạn người đọc và đặt thời hạn lưu. Hash của tệp không phải bí mật xác thực nhưng có thể tiết lộ danh mục phần mềm nội bộ.

Tín hiệu giám sát hữu ích gồm:

- Lượt nâng quyền tăng đột biến trên một thiết bị hoặc tài khoản.
- Công cụ chạy ngoài phạm vi hoặc thời điểm dự kiến.
- Hash mismatch trên nhiều máy ngay sau cập nhật.
- Rule cũ vẫn được dùng sau thời hạn thu hồi.
- Tiến trình con hoặc hành vi khác mẫu kiểm thử.
- Endpoint giữ revision cũ quá thời gian đồng bộ cho phép.

Mỗi tín hiệu cần ngữ cảnh. Cập nhật hợp lệ có thể gây nhiều mismatch; một yêu cầu hiếm vẫn đáng chú ý nếu người yêu cầu không đúng vai trò.

## 14. Ma trận kiểm thử trước phát hành

Dùng tài khoản tiêu chuẩn và endpoint đã nhận đúng revision. Chạy thử bằng tài khoản có quyền quản trị độc lập chưa chứng minh rule PAM hoạt động.

| Ca | Điều kiện | Kết quả mong đợi |
|---|---|---|
| T1 | H1, đúng người, đúng máy, đủ điều kiện | Tác vụ nhận quyền theo rule |
| T2 | H1, người ngoài nhóm | Không cấp quyền theo rule |
| T3 | H1, máy ngoài phạm vi | Không cấp quyền theo rule |
| T4 | Tệp vô hại cùng tên, hash khác | Không khớp H1 |
| T5 | H2 chưa được duyệt | Không cấp quyền theo rule H1 |
| T6 | H1 sao chép sang vị trí khác | Phản ánh đúng điều kiện vị trí đã thiết kế |
| T7 | H1 với đầu vào ngoài tác vụ | Bị giới hạn; nếu quyền vẫn rộng thì chưa đạt |
| T8 | H1 gọi thành phần con chưa duyệt | Không nhận quyền ngoài thiết kế |
| T9 | Thu hồi H1, máy đã nhận revision mới | Lần yêu cầu mới không được rule cũ cấp quyền |
| T10 | Máy offline hoặc agent không đáp ứng | Theo chính sách đã duyệt, có thể kiểm chứng |

Với T6, nếu rule chỉ dựa trên hash thì bản sao nguyên vẹn vẫn khớp nội dung. Muốn chỉ chạy ở vị trí bảo vệ phải có điều kiện cưỡng chế được và kiểm thử lại.

Với T7, thông báo “không đúng tham số” ở giao diện chưa đủ nếu người dùng có thể gọi trực tiếp EXE theo cách khác. Phải kiểm tra đường thực thi thực tế.

Với T8, phân biệt: không tạo tiến trình con; tạo với quyền tiêu chuẩn; hoặc nhận quyền cao theo rule riêng. Không gộp cả ba thành nhãn “blocked”.

Lưu người chạy, thời gian, policy revision, đầu vào vô hại, quyết định agent và bằng chứng ngữ cảnh quyền. Việc cửa sổ không xuất hiện chưa đủ chứng minh tác vụ bị chặn đúng chính sách.

## 15. Chẩn đoán khi hành vi khác dự kiến

### 15.1. Hash đúng nhưng vẫn bị từ chối

Kiểm tra theo thứ tự:

1. Người dùng có yêu cầu nâng quyền bằng đúng cơ chế của giải pháp không?
2. Endpoint đã nhận đúng revision và agent hoạt động không?
3. Artifact thực tế có đúng hash, thuật toán và loại đối tượng được đánh giá không?
4. Điều kiện tên, vị trí, chữ ký hoặc thuộc tính khác có đạt không?
5. Người và thiết bị có đúng phạm vi không?
6. Có rule xung đột hoặc bước duyệt chưa hoàn thành không?
7. Tệp chính đã chạy nhưng thao tác con bị chặn hay chưa?

Ứng dụng không hoàn thành công việc không đồng nghĩa nâng quyền ban đầu bị từ chối. Ví dụ, công cụ chạy được nhưng helper chưa được duyệt không nhận quyền. Phải đọc sự kiện từng giai đoạn.

### 15.2. Tệp khác hash vẫn chạy với quyền cao

Không vội kết luận kiểm tra hash đã bị vượt qua. Có thể lần chạy dùng rule rộng hơn, tài khoản có quyền sẵn, một đường cấp quyền khác hoặc quyền từ tiến trình cha.

~~~text
Lần chạy nào?
    → người yêu cầu và tài khoản thực thi
    → tiến trình cha và tệp thực tế
    → chính sách tại endpoint
    → rule hoặc đường cấp quyền đã cho phép
~~~

Kết quả “chạy được” có ý nghĩa khi đã xác định ngữ cảnh quyền và nguồn cấp quyền thực tế.

### 15.3. Sự cố sau cập nhật

Khi nội dung đổi, rule hash cũ có thể không còn khớp. Không sửa ngay thành rule theo tên hoặc wildcard rộng để giảm cuộc gọi hỗ trợ.

Tiếp nhận bản mới, xác định thay đổi, kiểm thử, duyệt và phát hành rule tương ứng. Nếu cần xử lý khẩn cấp, dùng ngoại lệ có thời hạn, phạm vi và hồ sơ rủi ro rõ ràng.

## 16. Bài tập tình huống

### Tình huống A: cùng hash, thư mục khác

H1 được duyệt cho công cụ trong thư mục bảo vệ. Người dùng sao chép đúng tệp sang Downloads. Rule chỉ xét hash và phạm vi người dùng.

Câu hỏi: bản ở Downloads có tự mất tính hợp lệ về hash không?

Gợi ý: không. Nội dung không đổi nên hash vẫn khớp. Nếu yêu cầu chỉ chạy ở vị trí bảo vệ, rule hiện tại chưa thực thi đủ. Cần kiểm soát vị trí và thành phần phụ thuộc theo khả năng thực tế của giải pháp.

### Tình huống B: bản vá cùng publisher

Bản 2.4.2 giữ tên tệp và publisher nhưng có hash H2. Người dùng muốn thêm H2 vì “chỉ sửa lỗi nhỏ”.

Câu hỏi: có thể bỏ duyệt vì H1 đã được cho phép không?

Gợi ý: không. H2 là artifact khác. Có thể tái sử dụng ngữ cảnh và tự động hóa bước kỹ thuật, nhưng vẫn cần xác minh nguồn, thay đổi hành vi và quyết định cấp quyền cho bản mới.

### Tình huống C: plugin từ thư mục cá nhân

EXE khớp H1 nhưng cho chọn plugin do người dùng cung cấp. Plugin chạy trong tiến trình đã nâng quyền.

Câu hỏi: kiểm tra hash EXE đã đủ chưa?

Gợi ý: chưa. Phạm vi mã được chạy lớn hơn EXE. Phải kiểm soát plugin, quyền sửa và vị trí hoặc đổi cách cung cấp tác vụ nếu không tạo được ranh giới đủ hẹp.

### Tình huống D: gỡ rule nhưng tiến trình vẫn tồn tại

Quản trị viên thu hồi H1 lúc 10:00. Tiến trình chạy từ 09:55 vẫn hoạt động lúc 10:05.

Câu hỏi: có tự chứng minh thu hồi thất bại không?

Gợi ý: chưa. Phân biệt chặn yêu cầu mới với kết thúc tiến trình cũ. Kiểm tra revision, thử lần yêu cầu mới và xem cơ chế xử lý phiên hiện hữu.

### Tình huống E: hash của công cụ chưa rõ nguồn

Người dùng gửi SHA-256 đầy đủ, ảnh quét không phát hiện mã độc và đề nghị chạy “một lần duy nhất”.

Câu hỏi: còn thiếu gì?

Gợi ý: nguồn artifact có thể kiểm chứng, nhu cầu nghiệp vụ, owner, phạm vi hành vi, kiểm thử và người có thẩm quyền duyệt. Một lần chạy với quyền cao vẫn có thể tạo thay đổi lâu dài; thời gian ngắn không thay bước đánh giá quyền.

## 17. Tiêu chí đưa vào vận hành

Một rule có thể vận hành khi chứng minh được liên hệ từ nhu cầu đến artifact, quyết định cấp quyền và kết quả thực thi.

- Artifact chuẩn có nguồn gốc, owner và hash tính từ đúng bản được duyệt.
- Người dùng giữ tài khoản tiêu chuẩn; phạm vi người và thiết bị đã xác minh.
- Đầu vào, thành phần phụ thuộc và tiến trình con không mở rộng quyền vượt tác vụ được chấp nhận.
- Có thử cả trường hợp cho phép và từ chối trong đúng ngữ cảnh.
- Cập nhật, thu hồi có người chịu trách nhiệm và bằng chứng chính sách đã áp dụng.
- Log nối được yêu cầu, artifact, revision và tiến trình; giới hạn quan sát được ghi rõ.

Elevation by hash đem lại độ chính xác khi nhận diện một bản phần mềm. Giá trị kiểm soát PAM xuất hiện khi kết hợp nhận diện đó với nguồn tin cậy, phạm vi quyền hẹp, thành phần thực thi bảo vệ được quyết định và vòng đời có thể kiểm toán.
