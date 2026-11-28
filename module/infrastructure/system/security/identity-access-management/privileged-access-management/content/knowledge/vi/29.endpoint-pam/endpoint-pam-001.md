# Local admin removal: loại bỏ quyền quản trị thường trực trên endpoint

## 1. Bài học này giải quyết vấn đề gì?

Một nhân viên đăng nhập laptop hằng ngày bằng tài khoản thuộc nhóm quản trị cục bộ. Tài khoản đó được dùng để đọc thư, mở tài liệu, truy cập hệ thống nội bộ và thỉnh thoảng cài phần mềm. Cách vận hành này thuận tiện, nhưng cũng khiến những hoạt động thông thường diễn ra dưới một danh tính có khả năng thực hiện thao tác quản trị máy.

Nếu tài khoản hoặc phiên làm việc bị chiếm dụng, kẻ tấn công có thể tìm cách lợi dụng quyền đó để thay đổi cấu hình, cài dịch vụ, tạo cơ chế tồn tại hoặc truy cập dữ liệu nhạy cảm trên máy. Một số hành vi còn phụ thuộc UAC, quyền của tiến trình, cơ chế bảo vệ và cách khai thác cụ thể; tư cách thành viên nhóm quản trị không có nghĩa mọi tiến trình luôn chạy với toàn bộ đặc quyền. Tuy vậy, duy trì quyền quản trị thường trực làm tăng đáng kể khả năng bị lạm dụng.

**Local admin removal** là quá trình loại bỏ quyền quản trị cục bộ không cần thiết, đặc biệt khỏi tài khoản sử dụng hằng ngày, rồi cung cấp cách thực hiện công việc đặc quyền có kiểm soát. Trong phạm vi Endpoint PAM, đây là một thay đổi về mô hình vận hành, không chỉ là một lệnh xóa thành viên nhóm.

Bài học tập trung vào endpoint Windows để minh họa. Nguyên tắc tương tự áp dụng cho máy macOS hoặc Linux, nhưng nhóm quản trị, sudo, token, công cụ kiểm kê và cơ chế cấp quyền khác nhau; không áp dụng nguyên xi câu lệnh Windows sang hệ điều hành khác.

Sau bài học, bạn có thể:

- Phân biệt quyền quản trị thường trực, quyền hiệu lực và quyền nâng tạm thời.
- Kiểm kê các đường cấp quyền quản trị trên endpoint.
- Thiết kế trạng thái đích dựa trên least privilege.
- Triển khai loại bỏ quyền theo pilot, có điều kiện dừng và phương án khôi phục.
- Xác minh quyền đã hết hiệu lực trong phiên mới, thay vì chỉ nhìn danh sách nhóm.
- Lưu bằng chứng đủ để giải thích ai đã thay đổi quyền gì, vì sao và kết quả ra sao.

## 2. Phân biệt những khái niệm dễ nhầm

| Khái niệm | Ý nghĩa | Điều cần tránh suy diễn |
|---|---|---|
| Local administrator | Danh tính có quyền quản trị cục bộ thông qua nhóm hoặc cơ chế cấp quyền tương ứng | Không đồng nghĩa với quản trị toàn bộ domain |
| Standard user | Tài khoản làm việc thông thường, không được cấp quyền quản trị máy thường trực | Không có nghĩa không thể thực hiện bất kỳ công việc đặc quyền nào |
| Standing privilege | Quyền tồn tại liên tục, không gắn với một nhu cầu và thời hạn ngắn | Không trở thành an toàn chỉ vì ít được sử dụng |
| Just-in-time, JIT | Cấp quyền trong một khoảng thời gian gắn với nhu cầu được chấp thuận | Không tự bảo đảm phạm vi thao tác đã đủ hẹp |
| Just-enough administration, JEA | Giới hạn tập thao tác quản trị cần thiết theo nhiệm vụ | Không tương đương với đưa người dùng vào nhóm Administrators |
| Application elevation | Cho phép một chương trình hoặc hành động được thực thi với đặc quyền theo chính sách | Không nên biến thành quyền chạy tùy ý chương trình con hoặc câu lệnh khác |
| Break-glass | Cơ chế truy cập quản trị khẩn cấp khi đường vận hành thông thường gặp sự cố | Không phải tài khoản tiện dụng để bỏ qua quy trình hằng ngày |

Một người không còn nằm trong nhóm Administrators trực tiếp vẫn có thể nhận quyền qua nhóm danh tính trung gian. Ngược lại, một ứng dụng hỗ trợ nâng quyền có thể cho phép một thao tác quản trị mà không cấp tư cách thành viên quản trị thường trực cho người dùng.

Vì vậy, câu hỏi cần trả lời là: **danh tính này có thể thực hiện thao tác quản trị nào, trên thiết bị nào, theo đường cấp quyền nào và trong bao lâu?**

## 3. Mối đe dọa và giới hạn của biện pháp

Loại bỏ local admin nhằm giảm đặc quyền có sẵn cho hoạt động thường ngày. Nó tạo thêm ranh giới giữa phiên người dùng và thao tác quản trị, giảm khả năng một hành vi phát sinh trong phiên thông thường trực tiếp trở thành thay đổi toàn hệ thống.

| Tình huống | Tác dụng mong đợi của local admin removal | Kiểm soát vẫn cần đi kèm |
|---|---|---|
| Người dùng mở tài liệu chứa mã độc | Giảm đặc quyền sẵn có để thay đổi máy | Bảo vệ endpoint, lọc nội dung, quản lý bản vá |
| Phần mềm yêu cầu quyền quản trị để cập nhật | Chuyển việc cập nhật sang kênh quản lý được kiểm soát | Đóng gói, kiểm thử và phân phối phần mềm |
| Help desk hỗ trợ từ xa | Tách quyền hỗ trợ khỏi tài khoản làm việc của nhân viên | Danh tính riêng, giới hạn phạm vi, nhật ký phiên |
| Một tài khoản quản trị bị lộ | Giảm số nơi tài khoản có quyền thường trực | Credential riêng theo phạm vi, rotation, giám sát |
| Chính sách cũ tự thêm lại người dùng | Phát hiện sai lệch sau thay đổi | Quản lý cấu hình, xác định nguồn chính sách |

Biện pháp này không ngăn mọi dạng tấn công. Mã độc chạy dưới người dùng vẫn có thể đọc dữ liệu mà người dùng được phép đọc, sử dụng phiên ứng dụng của họ hoặc phá hoại tài liệu trong phạm vi quyền đó. Lỗ hổng leo thang đặc quyền, cấu hình dịch vụ yếu và lạm dụng công cụ nâng quyền vẫn cần được xử lý riêng.

Cũng không nên coi việc xóa thành viên nhóm là bước thay thế cho ứng phó sự cố. Nếu thiết bị đã bị chiếm quyền, cần thực hiện quy trình điều tra và khôi phục phù hợp; việc thu hồi quyền của một danh tính không tự loại bỏ cơ chế tồn tại mà kẻ tấn công đã tạo.

## 4. Kiểm kê quyền hiệu lực trước khi thay đổi

### 4.1. Theo dõi toàn bộ đường cấp quyền

Ví dụ một đường cấp quyền gián tiếp:

~~~text
Tài khoản làm việc
    -> nhóm hỗ trợ trong hệ thống danh tính
        -> nhóm được gán vào Administrators của endpoint
            -> quyền quản trị trên endpoint
~~~

Nếu chỉ xóa một mục tài khoản trực tiếp trong nhóm cục bộ, đường cấp quyền qua nhóm trung gian vẫn có thể tồn tại. Tương tự, một chính sách quản lý thiết bị có thể thêm lại tài khoản sau chu kỳ đồng bộ tiếp theo.

Kiểm kê cần xem xét ít nhất:

- Thành viên trực tiếp của nhóm quản trị cục bộ.
- Nhóm domain hoặc nhóm danh tính được đưa vào nhóm cục bộ và quan hệ thành viên liên quan.
- Cách gán vai trò quản trị thiết bị theo mô hình tham gia hệ thống danh tính của tổ chức.
- Cơ chế cấp quyền tạm thời, công cụ Endpoint PAM hoặc agent hỗ trợ nâng quyền.
- Chính sách quản lý có khả năng duy trì hoặc khôi phục thành viên nhóm.
- Danh tính dịch vụ, tác vụ định kỳ và quy trình hỗ trợ phụ thuộc quyền hiện tại.
- Phiên đang hoạt động và tiến trình đã được tạo trước thời điểm thu hồi.

Danh sách thành viên nhóm cục bộ chỉ là một phần của bằng chứng. Không dùng riêng kết quả đó để khẳng định đã loại bỏ mọi đường quản trị của người dùng.

### 4.2. Thu thập dữ liệu đủ để ra quyết định

| Trường dữ liệu | Ví dụ minh họa | Mục đích |
|---|---|---|
| Định danh thiết bị | EP-FIN-0142 | Tránh thay đổi nhầm máy |
| Chủ sở hữu nghiệp vụ | Nhóm tài chính | Xác định người kiểm thử |
| Loại và mức nhạy cảm | Laptop xử lý dữ liệu khách hàng | Chọn độ chặt và thứ tự triển khai |
| Danh tính được cấp quyền | SID của tài khoản hoặc nhóm | Tránh nhầm tên hiển thị |
| Đường cấp quyền | Trực tiếp, qua nhóm, qua chính sách | Chọn đúng nơi cần sửa |
| Lý do đang cần quyền | Cập nhật một công cụ kế toán | Tìm phương án thay thế |
| Cơ chế quản lý | Kênh quản lý endpoint đang sử dụng | Chọn nguồn cấu hình có thẩm quyền |
| Trạng thái kết nối | Online, offline, đồng bộ chậm | Diễn giải kết quả triển khai |
| Đường phục hồi | Hỗ trợ có kiểm soát, tài khoản khẩn cấp | Bảo đảm khả năng xử lý sự cố |
| Thời điểm và nguồn bằng chứng | Thời gian kiểm kê, công cụ thu thập | Đối chiếu thay đổi theo thời gian |

Không thu thập mật khẩu, token hoặc nội dung vault vào bảng kiểm kê. Bằng chứng cần xác định quyền và sự kiện sử dụng; không cần sao chép credential.

## 5. Ví dụ kiểm kê nhóm quản trị cục bộ trên Windows

Ví dụ dưới đây là thao tác chỉ đọc, dùng trong môi trường Windows có sẵn các cmdlet LocalAccounts. Quyền chạy, khả năng phân giải danh tính và sự hiện diện của module cần được kiểm tra trên môi trường thực tế.

Dùng SID của nhóm Administrators tích hợp giúp tránh phụ thuộc vào tên nhóm đã được bản địa hóa:

~~~powershell
$adminGroup = Get-LocalGroup -SID 'S-1-5-32-544' -ErrorAction Stop
$members = @(Get-LocalGroupMember -Group $adminGroup -ErrorAction Stop)

[pscustomobject]@{
    ComputerName = $env:COMPUTERNAME
    GroupName    = $adminGroup.Name
    GroupSid     = $adminGroup.SID.Value
    CapturedAt   = (Get-Date).ToUniversalTime().ToString('o')
}

$members | ForEach-Object {
    [pscustomobject]@{
        MemberName      = $_.Name
        MemberSid       = $_.SID.Value
        ObjectClass     = $_.ObjectClass
        PrincipalSource = $_.PrincipalSource
    }
}
~~~

Cách đọc kết quả:

1. Xác nhận đúng thiết bị và SID nhóm đích.
2. Phân biệt tài khoản cá nhân, nhóm trung gian và danh tính quản trị được tổ chức cho phép.
3. Đối chiếu SID với danh tính có thẩm quyền; không dựa riêng vào tên trùng hoặc tên đã đổi.
4. Nếu kết quả chứa nhóm, kiểm tra quan hệ thành viên qua nguồn danh tính tương ứng.
5. Nếu truy vấn lỗi hoặc không phân giải được một danh tính, đánh dấu kiểm kê chưa đầy đủ và điều tra nguyên nhân.

Lệnh này không tự mở rộng mọi nhóm lồng nhau, không kiểm kê mọi vai trò từ hệ thống danh tính và không cho biết toàn bộ token đang tồn tại. Một kết quả rỗng do truy vấn lỗi cũng không chứng minh máy không còn quản trị viên.

Nếu không dùng được LocalAccounts, chọn phương thức kiểm kê phù hợp với môi trường. Không đổi sang một nguồn có phạm vi hẹp hơn rồi coi hai kết quả là tương đương.

## 6. Thiết kế trạng thái đích theo least privilege

Trạng thái đích thường có bốn thành phần:

- Tài khoản làm việc hằng ngày hoạt động như standard user.
- Nhu cầu đặc quyền được chuyển sang tác vụ quản lý, nâng quyền theo hành động hoặc danh tính quản trị riêng.
- Có đường hỗ trợ và phục hồi được quản lý, kiểm thử và giám sát.
- Hệ thống phát hiện việc quyền thường trực xuất hiện trở lại.

Một baseline minh họa cho laptop nhân viên:

| Loại danh tính | Trạng thái đích |
|---|---|
| Tài khoản làm việc của nhân viên | Không có quyền quản trị thường trực |
| Tài khoản hỗ trợ kỹ thuật | Chỉ có quyền trên phạm vi thiết bị và thời gian được giao |
| Tài khoản quản trị cục bộ khẩn cấp | Được quản lý credential, hạn chế sử dụng và kiểm toán |
| Tài khoản dịch vụ | Chỉ giữ quyền được chứng minh cần thiết cho dịch vụ |
| Nhóm không rõ chủ sở hữu | Điều tra và xử lý theo quy trình; không mặc nhiên coi là hợp lệ |

Local admin removal không đồng nghĩa với xóa toàn bộ tài khoản quản trị khỏi mọi endpoint. Một thiết bị vẫn cần đường quản trị hợp lệ để bảo trì và phục hồi. Đường này phải được kiểm soát, không chia sẻ mật khẩu cố định rộng rãi và không khuyến khích sử dụng danh tính đặc quyền trong phiên làm việc thông thường.

Nếu dùng cơ chế quản lý mật khẩu tài khoản quản trị cục bộ, cần quản lý cả quyền đọc credential, vòng đời mật khẩu và quy trình sử dụng. Cơ chế đó không tự động thu hồi quyền quản trị đang cấp cho tài khoản người dùng khác.

Với quyền theo thời gian, cần phân biệt hai thời hạn:

- Thời hạn được phép bắt đầu thao tác hoặc nhận quyền.
- Thời điểm các phiên, tiến trình và tài nguyên được tạo trong thời gian có quyền thực sự không còn sử dụng được.

Không giả định rằng hết hạn tư cách thành viên nhóm sẽ tự kết thúc mọi tiến trình đã nâng quyền.

## 7. Phân tích ứng dụng trước khi thu hồi quyền

Một phản hồi thường gặp là: “Ứng dụng này cần local admin”. Cần chuyển câu đó thành yêu cầu kỹ thuật có thể kiểm chứng.

Ví dụ:

- Cài đặt lần đầu có cần quyền hay mỗi lần chạy đều cần?
- Ứng dụng ghi vào thư mục dữ liệu người dùng hay thư mục được bảo vệ?
- Việc cập nhật do người dùng thực hiện hay có thể chuyển sang kênh quản lý?
- Tác vụ thay đổi dịch vụ, driver, cấu hình mạng hay chỉ đọc thông tin?
- Có thành phần nào được cấu hình sai khiến người dùng phải nâng quyền để khắc phục?
- Công việc đặc quyền có tần suất, thời lượng và phạm vi cụ thể nào?

| Nhu cầu thực tế | Phương án ưu tiên để đánh giá |
|---|---|
| Cài ứng dụng đã được phê duyệt | Phân phối qua kênh quản lý phần mềm |
| Cập nhật ứng dụng | Kênh cập nhật được quản lý hoặc gói triển khai |
| Đọc log trong một thư mục | Cấp quyền đọc đúng thư mục nếu phù hợp |
| Thực hiện một tác vụ hỗ trợ | Tác vụ quản trị giới hạn đầu vào và phạm vi |
| Chạy một công cụ cần đặc quyền | Chính sách nâng quyền gắn với công cụ và điều kiện cụ thể |
| Sửa cấu hình hệ thống hiếm khi cần | Phiên quản trị riêng hoặc quyền tạm thời có phê duyệt |

Không khắc phục lỗi ghi file bằng cách cấp quyền Modify cho người dùng trên toàn bộ thư mục chương trình, thư mục hệ thống hoặc đường dẫn chứa file thực thi của dịch vụ đặc quyền. Cấu hình như vậy có thể tạo đường leo thang đặc quyền.

Tương tự, không cho phép nâng quyền một trình thông dịch, shell, trình chỉnh sửa có khả năng thực thi mã hoặc chương trình chấp nhận đầu vào tùy ý chỉ vì nó có chữ ký hợp lệ. Cần đánh giá tham số, file được mở, tiến trình con, cơ chế plugin và nguồn nội dung mà chương trình có thể thực thi.

Mục tiêu là đáp ứng đúng công việc, không tái tạo quyền quản trị toàn máy dưới một tên chính sách khác.

## 8. Chọn đúng nguồn cấu hình có thẩm quyền

Một endpoint có thể nhận cấu hình từ nhiều nguồn: chính sách domain, quản lý thiết bị, công cụ cấu hình, agent PAM hoặc quy trình hỗ trợ thủ công. Nếu hai nguồn cùng điều khiển thành viên nhóm theo cách khác nhau, quyền có thể bị thêm lại hoặc baseline hợp lệ bị xóa.

Trước khi triển khai, cần xác định:

1. Nguồn nào quyết định trạng thái đích của nhóm quản trị trên loại thiết bị này.
2. Nguồn nào chỉ bổ sung quyền tạm thời.
3. Nguồn nào còn giữ chính sách cũ cần ngừng áp dụng.
4. Khi có xung đột, thiết bị thực tế sẽ nhận trạng thái nào và sau chu kỳ nào.

Cần đặc biệt phân biệt:

| Kiểu thao tác | Tác dụng | Rủi ro khi hiểu sai |
|---|---|---|
| Xóa một thành viên xác định | Loại bỏ đúng mục được chọn | Các đường cấp quyền khác vẫn tồn tại |
| Thêm một thành viên | Bổ sung một đường cấp quyền | Không bảo đảm baseline đã sạch |
| Thay thế danh sách thành viên | Áp đặt tập thành viên theo cấu hình | Có thể loại bỏ đường quản trị hoặc phục hồi hợp lệ |
| Hết hạn quyền tạm thời | Kết thúc một cơ chế cấp quyền theo thời gian | Token và tiến trình cũ có thể còn hiệu lực |

Chi tiết hành vi phụ thuộc công cụ và chính sách đang dùng. Phải kiểm thử cách hợp nhất, thay thế và áp dụng lại trong pilot; không suy luận từ tên gọi giao diện.

Nếu một nhóm trung gian dùng chung cho nhiều mục đích, thay đổi thành viên của nhóm đó có thể ảnh hưởng các hệ thống ngoài endpoint đang xử lý. Đánh giá phạm vi trước và ưu tiên sửa đúng đường gán quyền tại endpoint khi đó là nơi cần thay đổi.

## 9. Quy trình triển khai theo từng giai đoạn

### Giai đoạn A — Đánh giá và chuẩn bị

- Kiểm kê thiết bị, chủ sở hữu, thành viên quản trị và nguồn chính sách.
- Lập danh sách ứng dụng cùng những công việc thực sự cần quyền.
- Kiểm thử đường hỗ trợ, phân phối phần mềm và phục hồi.
- Xác định tập thành viên hợp lệ theo loại thiết bị.
- Đặt điều kiện thành công, điều kiện dừng và người chịu trách nhiệm.

Kết quả của giai đoạn này phải cho biết chính xác nhóm thiết bị nào được thay đổi, đường quyền nào bị thu hồi và cách xử lý nếu công việc nghiệp vụ bị gián đoạn.

### Giai đoạn B — Pilot

Chọn nhóm nhỏ nhưng đại diện: người dùng thông thường, nhóm có ứng dụng chuyên biệt, thiết bị thường offline và trường hợp hỗ trợ từ xa.

Pilot cần bao gồm cả:

- Tình huống người dùng được hỗ trợ qua kênh quản lý.
- Tình huống mạng hoặc agent không sẵn sàng.
- Đăng xuất và tạo phiên mới sau thu hồi.
- Chu kỳ đồng bộ chính sách tiếp theo.
- Quyền tạm thời hết hạn và cách xử lý tiến trình còn mở.
- Tình huống phải sử dụng đường phục hồi.

Không chỉ chọn những máy dễ nhất rồi suy ra toàn bộ môi trường sẽ hoạt động tương tự.

### Giai đoạn C — Mở rộng theo vòng

Mở rộng theo nhóm thiết bị hoặc đơn vị nghiệp vụ sau khi điều kiện pilot được đáp ứng. Giữa các vòng, đánh giá lỗi ứng dụng, yêu cầu hỗ trợ, sự xuất hiện trở lại của quyền và các thiết bị chưa nhận cấu hình.

Máy offline cần trạng thái riêng như “chưa áp dụng” hoặc “chưa xác minh”. Không tính máy đó vào nhóm đã hoàn thành chỉ vì hệ thống quản lý đã tiếp nhận yêu cầu triển khai.

### Giai đoạn D — Duy trì

Theo dõi sai lệch, duyệt lại ngoại lệ, kiểm tra đường nâng quyền và đánh giá tác động của phần mềm mới. Một đợt thu hồi thành công không bảo đảm quyền không xuất hiện trở lại sau vài tuần.

## 10. Ví dụ thu hồi một thành viên trực tiếp trong lab

Ví dụ sau chỉ minh họa cách chọn đúng một thành viên bằng SID và xem trước thao tác. SID trong ví dụ là giá trị giả; phải thay bằng SID đã được kiểm kê của đúng danh tính trong lab.

Trước khi thực hiện thật, đã cần xác nhận đây không phải đường quản trị phục hồi duy nhất, không phải danh tính đang cần để duy trì phiên quản trị và không phải tài khoản dịch vụ còn phụ thuộc chưa được xử lý.

~~~powershell
$targetMemberSid = 'S-1-5-21-111111111-222222222-333333333-1003'

$adminGroup = Get-LocalGroup -SID 'S-1-5-32-544' -ErrorAction Stop
$members = @(Get-LocalGroupMember -Group $adminGroup -ErrorAction Stop)
$target = @(
    $members | Where-Object { $_.SID.Value -eq $targetMemberSid }
)

if ($target.Count -ne 1) {
    throw 'Phai xac dinh dung mot thanh vien truc tiep truoc khi thay doi.'
}

$target | Select-Object Name, SID, ObjectClass, PrincipalSource

Remove-LocalGroupMember -Group $adminGroup -Member $target[0] -WhatIf
~~~

Tham số WhatIf chỉ xem trước, chưa thay đổi thành viên. Trong lab, sau khi đối chiếu đúng danh tính và kiểm thử đường phục hồi, có thể thực hiện thao tác tương ứng không có WhatIf theo quy trình thay đổi đã được chấp thuận. Sau đó phải kiểm kê lại và kiểm thử phiên mới.

Các giới hạn của ví dụ:

- Chỉ xử lý một mục thành viên trực tiếp.
- Không sửa thành viên bên trong nhóm domain hoặc nhóm danh tính khác.
- Không thay đổi nguồn chính sách có thể thêm lại quyền.
- Không chấm dứt phiên đăng nhập hoặc tiến trình đang có đặc quyền.
- Không phải script triển khai hàng loạt cho môi trường sản xuất.

Trong triển khai thật, ưu tiên kênh quản lý có kiểm soát phiên bản, phạm vi thiết bị, ghi nhận kết quả và khả năng phục hồi, thay vì chạy lệnh rời rạc trên nhiều máy.

## 11. Vì sao xóa thành viên nhóm chưa có nghĩa quyền hết ngay?

Khi một phiên đăng nhập được tạo, hệ điều hành xây dựng ngữ cảnh bảo mật từ thông tin danh tính và nhóm tại thời điểm tương ứng. Tiến trình trong phiên sử dụng token được cấp; chỉnh sửa thành viên nhóm không đồng nghĩa mọi token đang tồn tại được tạo lại ngay.

Với tài khoản thuộc nhóm quản trị, UAC còn làm xuất hiện sự khác biệt giữa tiến trình thông thường và tiến trình đã nâng quyền. Vì vậy, danh sách thành viên, trạng thái nâng quyền của tiến trình và khả năng thực hiện một tác vụ cụ thể là các loại bằng chứng khác nhau.

Một chuỗi thay đổi cần được quan sát:

~~~text
Kiểm kê quyền hiện tại
    -> Thu hồi đường cấp quyền
    -> Áp dụng và xác nhận cấu hình
    -> Kết thúc hoặc làm mới các phiên liên quan theo kế hoạch
    -> Tạo phiên người dùng mới
    -> Thử thao tác cần quyền
    -> Theo dõi quyền có xuất hiện trở lại hay không
~~~

Đăng xuất rồi đăng nhập lại thường là bước quan trọng để kiểm thử phiên mới. Với phiên từ xa, tác vụ định kỳ, dịch vụ hoặc tiến trình đặc quyền tồn tại độc lập, phải kiểm tra cơ chế và vòng đời riêng. Khởi động lại có thể là một phần của kế hoạch, nhưng không nên dùng như lời giải thay thế cho việc hiểu đường cấp quyền.

Nếu có quyền được cấp qua hệ thống danh tính và chính sách phân tán, còn cần tính đến đồng bộ, cache và sự khác nhau giữa các kiểu đăng nhập. Không đưa ra cam kết “thu hồi trong một giây” khi chưa đo được toàn bộ chuỗi thực thi.

## 12. Xác minh bằng nhiều lớp bằng chứng

### 12.1. Cấu hình

- Danh tính bị thu hồi không còn ở đường cấp quyền đã chọn.
- Tập thành viên hợp lệ vẫn còn nguyên theo baseline.
- Nguồn chính sách đã được sửa đúng và thiết bị đã áp dụng.
- Không có một chính sách khác phục hồi quyền ngoài ý muốn.

### 12.2. Quyền hiệu lực trong phiên mới

Tạo phiên mới bằng tài khoản làm việc và thử một thao tác cần quyền quản trị trong môi trường kiểm thử. Kết quả mong đợi là thao tác bị từ chối hoặc đi qua quy trình nâng quyền được tổ chức thiết kế.

Không dùng thao tác phá hủy hoặc tắt công cụ bảo vệ chỉ để chứng minh thiếu quyền. Chọn một phép thử có thể hoàn tác, phạm vi nhỏ và được thống nhất trước.

Có thể dùng các lệnh chẩn đoán như sau để quan sát ngữ cảnh phiên:

~~~powershell
whoami /user
whoami /groups
whoami /priv
~~~

Kết quả cần được diễn giải theo token hiện tại. Một SID xuất hiện với thuộc tính deny-only không đồng nghĩa tiến trình đang có quyền quản trị đầy đủ. Ngược lại, một cửa sổ lệnh chưa nâng quyền không đủ chứng minh tài khoản không thể nâng quyền qua một cơ chế khác.

Do đó, kết hợp thông tin nhóm, nguồn cấp quyền, token và thử nghiệm hành động; không đưa ra kết luận chỉ từ một dòng trong đầu ra.

### 12.3. Khả năng làm việc và hỗ trợ

- Ứng dụng nghiệp vụ khởi động, lưu dữ liệu và cập nhật qua đường đã thiết kế.
- Nhân viên có thể yêu cầu hỗ trợ khi cần.
- Help desk sử dụng danh tính đúng phạm vi.
- Đường khẩn cấp hoạt động và để lại bằng chứng truy cập.
- Các ngoại lệ được ghi nhận rõ thay vì giải quyết bằng cách cấp lại quyền vô thời hạn.

### 12.4. Tính bền vững

Kiểm tra sau một chu kỳ quản lý cấu hình phù hợp, sau lần kết nối lại và sau tình huống bảo trì tiêu biểu. Nếu quyền quay lại, điều tra nguồn khôi phục; không lặp lệnh xóa liên tục để che giấu xung đột chính sách.

## 13. Ngoại lệ phải có phạm vi và ngày hết hạn

Một số ứng dụng cũ hoặc thiết bị chuyên dụng chưa thể chuyển đổi ngay. Ngoại lệ có thể cần thiết, nhưng phải được xem như khoản nợ cần xử lý có người chịu trách nhiệm.

Hồ sơ ngoại lệ tối thiểu gồm:

| Trường | Nội dung cần ghi |
|---|---|
| Phạm vi | Danh tính và thiết bị cụ thể |
| Lý do | Công việc nào thất bại khi không có quyền |
| Bằng chứng | Kết quả kiểm thử hoặc yêu cầu kỹ thuật |
| Phương án đã đánh giá | Đóng gói, sửa cấu hình, cấp quyền hẹp, nâng theo hành động |
| Chủ sở hữu | Người chịu trách nhiệm nghiệp vụ và kỹ thuật |
| Thời hạn | Ngày cần thu hồi hoặc đánh giá lại |
| Kiểm soát bổ sung | Hạn chế đăng nhập, giám sát, phạm vi kết nối phù hợp |
| Kế hoạch kết thúc | Thay ứng dụng, thay quy trình hoặc sửa cấu hình |

Một ngoại lệ “tất cả developer đều local admin trên mọi máy” thường quá rộng để phản ánh nhu cầu. Cần phân biệt máy phát triển có thể tái tạo, môi trường thử nghiệm, máy chứa credential nhạy cảm và endpoint làm việc hằng ngày.

Không biến hết hạn hồ sơ thành hành động thu hồi mù quáng trên thiết bị chưa có phương án thay thế. Hệ thống cần cảnh báo trước, có người xử lý và thực thi thu hồi theo kế hoạch; việc gia hạn cũng phải có lý do mới, không mặc nhiên kéo dài.

## 14. Phục hồi khi thay đổi gây gián đoạn

Phương án khôi phục phải được chuẩn bị trước khi thu hồi, có người thực hiện và đường truy cập đã được kiểm thử.

Một quy trình phục hồi có thể gồm:

1. Xác định gián đoạn do thu hồi quyền, lỗi ứng dụng hay sự cố quản lý khác.
2. Thu thập lỗi và tác vụ bị ảnh hưởng; tránh cấp lại quyền trước khi biết nguyên nhân.
3. Dùng danh tính hỗ trợ hợp lệ để khôi phục đúng chức năng cần thiết.
4. Nếu buộc cấp lại quyền, giới hạn danh tính, thiết bị và thời gian.
5. Sửa cả nguồn chính sách để trạng thái không dao động giữa hai cấu hình.
6. Xác minh công việc hoạt động, ghi nhận ngoại lệ và lên kế hoạch thu hồi lại.

Không sao chép nguyên danh sách quản trị cũ như một hành động khôi phục mặc định. Danh sách cũ có thể chứa các quyền dư thừa chính là đối tượng cần loại bỏ. Khôi phục nên hướng tới trạng thái đã được phê duyệt hoặc một ngoại lệ có phạm vi rõ ràng.

Khi sử dụng credential khẩn cấp, ghi nhận ai đã truy cập, lý do, thiết bị và hành động. Thực hiện thay đổi credential sau sử dụng theo cơ chế quản lý và chính sách của tổ chức; kiểm tra cả khả năng đồng bộ và các phụ thuộc trước khi coi quy trình đã khép kín.

## 15. Nhật ký và bằng chứng kiểm toán

Một chuỗi bằng chứng có ích cần kết nối được:

~~~text
Yêu cầu thay đổi
    -> Quyền trước thay đổi
    -> Quyết định thu hồi hoặc ngoại lệ
    -> Kết quả áp dụng trên từng thiết bị
    -> Phiên mới và kiểm thử quyền
    -> Kết quả nghiệp vụ
    -> Theo dõi sai lệch
~~~

Các nguồn có thể gồm nhật ký quản lý cấu hình, thay đổi thành viên nhóm, cấp quyền PAM, truy cập credential, đăng nhập, hành động nâng quyền và phiên hỗ trợ. Khả năng ghi nhận sự kiện phụ thuộc cấu hình audit; không mặc định mọi sự kiện đã được thu thập đầy đủ.

Trong môi trường Windows có bật audit tương ứng, có thể đối chiếu sự kiện thay đổi nhóm bảo mật cục bộ với bản ghi từ hệ thống quản lý. Cần xác nhận đúng loại nhóm, thiết bị phát sinh, tài khoản thực hiện và thời điểm. Không chỉ tìm một mã sự kiện rồi coi đó là bằng chứng đầy đủ cho mọi đường quyền.

Nên lưu:

- Định danh thiết bị và danh tính bằng giá trị ổn định như SID.
- Thời gian có múi giờ hoặc chuẩn thời gian thống nhất.
- Người hoặc dịch vụ thực hiện thay đổi.
- Định danh yêu cầu, phiên hoặc chính sách liên quan.
- Kết quả áp dụng, lỗi và trạng thái chờ xác minh.
- Chứng cứ kiểm thử và người xác nhận.

Bằng chứng cần được bảo vệ khỏi sửa đổi trái phép, có kiểm soát truy cập và thời hạn lưu phù hợp. Không đưa mật khẩu hay token vào ticket, ảnh chụp màn hình hoặc nội dung log.

## 16. Chỉ số vận hành: đo đúng mẫu số

Tỷ lệ hoàn thành dễ bị thổi phồng khi chỉ đếm số yêu cầu đã gửi hoặc số endpoint online.

Ví dụ một vòng triển khai có 100 thiết bị trong phạm vi:

- 82 thiết bị đã áp dụng và xác minh phiên mới thành công.
- 8 thiết bị đã nhận cấu hình nhưng chưa kiểm thử phiên mới.
- 6 thiết bị offline, chưa xác nhận áp dụng.
- 4 thiết bị đang giữ ngoại lệ đã phê duyệt.

Có thể báo tỷ lệ **đã xác minh thu hồi** là 82/100. Không gọi 90/100 là “đã loại bỏ quyền hoàn toàn” chỉ vì 8 thiết bị đã nhận cấu hình. Cũng không gộp ngoại lệ vào thành công mà không giải thích.

Các chỉ số hữu ích:

| Chỉ số | Cách sử dụng |
|---|---|
| Tỷ lệ endpoint đã xác minh không còn quyền thường trực ngoài baseline | Theo dõi kết quả thực tế |
| Số đường quyền ngoài baseline còn tồn tại | Phân biệt nhiều đường cấp quyền trên cùng một máy |
| Số ngoại lệ và tuổi ngoại lệ | Phát hiện quyền tạm thời trở thành lâu dài |
| Thời gian từ quyết định thu hồi đến quyền hết hiệu lực | Đánh giá cả chính sách và phiên |
| Tỷ lệ quyền xuất hiện trở lại | Phát hiện drift hoặc xung đột nguồn cấu hình |
| Tỷ lệ yêu cầu nâng quyền được đáp ứng đúng quy trình | Đánh giá khả năng phục vụ công việc |
| Gián đoạn nghiệp vụ liên quan thay đổi | Điều chỉnh cách đóng gói và hỗ trợ |

Cần đọc các chỉ số cùng nhau. Ít yêu cầu hỗ trợ chưa chắc là thành công: người dùng có thể đã tìm một đường cấp quyền không được quản lý. Ngược lại, nhiều yêu cầu trong pilot có thể phản ánh việc phát hiện đúng những phụ thuộc cần sửa.

## 17. Tình huống thực hành: laptop của bộ phận kế toán

Một bộ phận có 60 laptop. Nhân viên được cấp local admin từ nhiều năm trước vì phần mềm kế toán cập nhật bằng tay. Nhóm hỗ trợ cũng có quyền quản trị thường trực trên toàn bộ laptop. Một số máy thường làm việc ngoài văn phòng.

### Phân tích ban đầu

Nhóm triển khai phát hiện:

- Tài khoản làm việc được thêm trực tiếp trên một số máy.
- Một nhóm danh tính trung gian cấp quyền trên các máy còn lại.
- Chính sách cũ có thể thêm lại thành viên sau đồng bộ.
- Nhu cầu thực tế chủ yếu là cài bản cập nhật, không phải quản trị liên tục.
- Có một thiết bị dùng thành phần cũ chưa được đóng gói lại.

Nếu chỉ chạy lệnh xóa tài khoản trực tiếp, một phần người dùng vẫn giữ quyền qua nhóm trung gian. Nếu xóa toàn bộ danh sách quản trị, đường hỗ trợ hoặc phục hồi có thể bị ảnh hưởng.

### Thiết kế thay đổi

Nhóm triển khai:

1. Chọn một nguồn cấu hình có thẩm quyền và xử lý chính sách cũ.
2. Đóng gói bản cập nhật qua kênh phân phối phần mềm.
3. Tách tài khoản làm việc khỏi quyền quản trị thường trực.
4. Chuyển hỗ trợ sang danh tính đúng phạm vi và thời gian.
5. Kiểm thử đường khẩn cấp, quyền đọc credential và nhật ký truy cập.
6. Ghi ngoại lệ có thời hạn cho thiết bị dùng thành phần cũ.

### Kiểm chứng pilot

Sáu máy đại diện được chọn. Trên từng máy, nhóm lưu trạng thái trước thay đổi, thu hồi đúng đường cấp quyền, tạo phiên mới, thử cập nhật qua kênh quản lý và thực hiện một yêu cầu hỗ trợ mẫu.

Một máy không nhận chính sách do offline được giữ ở trạng thái chờ, không được đánh dấu thành công. Một máy xuất hiện lại quyền sau đồng bộ giúp nhóm phát hiện cấu hình cũ chưa được loại bỏ hoàn toàn.

Chỉ sau khi xử lý nguyên nhân, kiểm thử lại và xác nhận các tác vụ nghiệp vụ, nhóm mới mở rộng vòng tiếp theo.

Bài học của tình huống là: số thành viên đã xóa không phản ánh đầy đủ chất lượng local admin removal. Kết quả phải bao gồm quyền hiệu lực, tính bền vững của cấu hình và khả năng làm việc của người dùng.

## 18. Các lỗi thường gặp và cách nhận ra

| Lỗi | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Chỉ kiểm tra thành viên trực tiếp | Người dùng vẫn quản trị được qua nhóm khác | Truy nguyên đường quyền gián tiếp |
| Bỏ qua phiên cũ | Nhóm đã sạch nhưng tiến trình nâng quyền vẫn hoạt động | Xử lý vòng đời phiên và kiểm thử phiên mới |
| Hai nguồn chính sách xung đột | Quyền bị xóa rồi xuất hiện lại | Xác định nguồn có thẩm quyền và sửa nguồn gây drift |
| Xóa toàn bộ nhóm theo danh sách chưa kiểm chứng | Mất đường hỗ trợ hoặc phục hồi | Định nghĩa baseline và kiểm thử trước |
| Thay local admin bằng nâng shell tùy ý | Người dùng vẫn có thể thực hiện gần như mọi thao tác quản trị | Thu hẹp chương trình, đầu vào và hành động |
| Cấp quyền ghi vào file thực thi đặc quyền | Ứng dụng chạy được nhưng hình thành đường leo thang | Sửa ứng dụng hoặc cấp quyền đúng tài nguyên dữ liệu |
| Tính máy offline là đã hoàn tất | Báo cáo đẹp nhưng trạng thái thực tế không rõ | Theo dõi chờ áp dụng và chờ xác minh riêng |
| Ngoại lệ không có chủ sở hữu | Quyền dư thừa tồn tại qua nhiều vòng đánh giá | Gắn người chịu trách nhiệm và kế hoạch kết thúc |

## 19. Bài tập tự kiểm tra

Trong một lab có khả năng phục hồi, xây dựng baseline và kiểm chứng cho một endpoint:

1. Ghi lại các đường cấp quyền quản trị của một tài khoản thử nghiệm.
2. Chọn đúng một đường quyền thường trực để loại bỏ.
3. Định nghĩa phương án đáp ứng tác vụ cần đặc quyền và đường khôi phục.
4. Thu hồi quyền bằng kênh đã chọn, ghi nhận kết quả áp dụng.
5. Tạo phiên mới và thực hiện phép thử quản trị có phạm vi nhỏ.
6. Xác nhận ứng dụng nghiệp vụ và kênh hỗ trợ vẫn hoạt động.
7. Kiểm tra sau chu kỳ đồng bộ và ghi nhận quyền có quay lại hay không.
8. Tổng hợp bằng chứng trước/sau, giới hạn kiểm chứng và việc còn chờ.

Tự trả lời các câu hỏi:

- Vì sao xóa một tài khoản khỏi nhóm Administrators có thể chưa đủ?
- Một tiến trình đã nâng quyền trước thời điểm thu hồi cần được xử lý thế nào?
- Khi nào nên sửa đường gán quyền trên endpoint thay vì sửa thành viên một nhóm dùng chung?
- Bạn chứng minh máy offline đã nhận thay đổi bằng bằng chứng nào?
- Nếu một tác vụ bị hỏng, phương án phục hồi hẹp nhất đáp ứng công việc là gì?

## 20. Tiêu chí hoàn thành

Local admin removal trên một endpoint chỉ nên được coi là đã xác minh khi có đủ bằng chứng rằng quyền thường trực ngoài baseline đã được thu hồi qua các đường liên quan, phiên mới thể hiện quyền đúng thiết kế và các nhu cầu công việc có đường thực hiện hợp lệ.

Kết quả còn cần cho thấy cấu hình duy trì qua chu kỳ quản lý, hỗ trợ và phục hồi hoạt động, ngoại lệ có người chịu trách nhiệm, và chuỗi bằng chứng giải thích được thay đổi. Đây là cách kết nối Endpoint PAM với least privilege, JIT/JEA, quản lý credential và giám sát phiên trong một quy trình vận hành có thể kiểm chứng.
