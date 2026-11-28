# Giới hạn lệnh được phép

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), cấp quyền trong thời gian ngắn chưa đủ để kiểm soát những gì tài khoản quản trị có thể làm. Một tài khoản chỉ tồn tại mười phút vẫn có thể thay đổi cấu hình bảo mật, lấy credential hoặc tạo cơ chế truy cập lâu dài nếu được mở một shell với quyền quá rộng.

Trong chương **JIT và JEA**, giới hạn lệnh được phép là cách biến nhu cầu vận hành thành tập thao tác cụ thể, có phạm vi và có thể kiểm toán. **Just-in-Time (JIT)** giới hạn thời điểm và thời lượng được sử dụng quyền; **Just Enough Administration (JEA)** giới hạn chức năng quản trị có thể thực hiện. Hai cơ chế bổ sung cho nhau khi bảo vệ tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm.

Bài học tập trung vào thiết kế danh sách lệnh cho phép, kiểm soát tham số và đối tượng tác động, nhận diện đường vòng, rồi liên kết việc thực thi với phê duyệt, nhật ký phiên và bằng chứng kiểm toán.

## 1. Cấp quyền cho một hành động nghiệp vụ

Yêu cầu “cho phép trực ca xử lý sự cố dịch vụ thanh toán” còn quá rộng để đưa thẳng vào chính sách. Cần chuyển thành các hành động rõ ràng, chẳng hạn:

- Xem trạng thái dịch vụ `ContosoBillingAgent` trên máy chủ ứng dụng được giao.
- Khởi động lại đúng dịch vụ đó sau khi được duyệt trong một cửa sổ JIT.
- Đọc một tập thông tin chẩn đoán đã loại bỏ dữ liệu nhạy cảm.

Các thao tác sửa cấu hình dịch vụ, thay tệp thực thi, tạo tài khoản, đọc bí mật trong vault hoặc chạy mã tùy ý không tự động thuộc yêu cầu trên.

Một đơn vị cấp quyền hữu ích có dạng:

> Chủ thể đã xác thực → hành động đã duyệt → đối tượng xác định → tham số giới hạn → danh tính thực thi → điều kiện và thời hạn.

Ví dụ:

| Thành phần | Phạm vi của một lần cấp quyền |
| --- | --- |
| Chủ thể | Nhân viên trực ca đã xác thực và được gán vai trò phù hợp |
| Hành động | Khởi động lại dịch vụ thanh toán |
| Đối tượng | Dịch vụ `ContosoBillingAgent` trên máy chủ `APP-PAY-02` |
| Tham số | Không cho chọn dịch vụ khác, máy khác hoặc chạy chương trình phụ |
| Danh tính thực thi | Danh tính có quyền cần thiết trên dịch vụ đích |
| Điều kiện | Có yêu cầu thay đổi được duyệt và đang trong cửa sổ JIT |
| Bằng chứng | Người gọi, mã yêu cầu, máy đích, hành động, thời điểm và kết quả |

Tên lệnh chỉ là một phần của quyền. `Restart-Service` với đối tượng cố định và `Restart-Service` cho mọi dịch vụ là hai quyền có mức tác động rất khác nhau.

## 2. Kết hợp JIT, JEA và quyền thực tế trên tài nguyên

Có thể mô tả quyết định cho phép bằng biểu thức khái niệm:

```text
Cho phép thực thi =
    xác thực hợp lệ
    VÀ được truy cập endpoint
    VÀ quyền JIT đang hiệu lực
    VÀ hành động thuộc vai trò JEA
    VÀ tham số, đối tượng, điều kiện hợp lệ
    VÀ danh tính thực thi có quyền trên tài nguyên
```

Biểu thức này là mô hình thiết kế, không phải tính năng tự có của mọi sản phẩm PAM. Đội triển khai phải xác định thành phần nào chịu trách nhiệm kiểm tra từng điều kiện và cơ chế nào cưỡng chế điều kiện đó.

Có ba lớp cần phối hợp:

1. **Lớp cấp quyền:** quyết định ai được vào vai trò nào, trong khoảng thời gian nào và sau phê duyệt nào.
2. **Lớp hành động:** chỉ cung cấp những chức năng phù hợp với nhiệm vụ; kiểm tra tham số trước khi thực thi.
3. **Lớp tài nguyên:** giới hạn quyền của danh tính thực thi trên hệ điều hành, dịch vụ, cơ sở dữ liệu hoặc API đích.

Nếu người vận hành vẫn có đường đăng nhập quản trị trực tiếp bằng cùng quyền rộng, họ có thể bỏ qua endpoint hạn chế. Cần kiểm kê cả tài khoản cục bộ, nhóm quản trị, khóa SSH, credential dịch vụ và những đường truy cập khác có cùng khả năng tác động.

Tương tự, việc ẩn lệnh trong một cổng PAM không làm mất quyền của danh tính ở hệ thống đích. Một endpoint hạn chế và một tài khoản thực thi có đặc quyền quá rộng vẫn tạo ra rủi ro lớn nếu chức năng được phép có lỗi.

## 3. Từ nhu cầu vận hành đến danh sách cho phép

### 3.1. Bắt đầu từ công việc cần hoàn thành

Thu thập các tác vụ vận hành thực tế: xem trạng thái, khởi động lại, thu thập chẩn đoán hoặc triển khai một cấu hình đã được phê duyệt. Với mỗi tác vụ, ghi rõ đầu vào, đầu ra, quyền cần dùng và tác động phụ.

Không bắt đầu bằng việc sao chép toàn bộ bộ lệnh mà quản trị viên thường sử dụng. Thói quen làm việc trong một shell quản trị đầy đủ thường bao gồm những quyền vượt quá nhiệm vụ của người trực ca.

Một ma trận ban đầu có thể như sau:

| Nhu cầu | Giao diện được cấp | Ràng buộc chính | Không nằm trong vai trò này |
| --- | --- | --- | --- |
| Kiểm tra dịch vụ | `Get-BillingAgentStatus` | Chỉ dịch vụ được giao; trả về tên và trạng thái | Đọc mọi cấu hình hoặc bí mật của dịch vụ |
| Khởi động lại | `Restart-BillingAgent` | Máy đích cố định theo endpoint; yêu cầu JIT phù hợp | Dừng mọi dịch vụ hoặc thay cấu hình khởi động |
| Lấy chẩn đoán | Chức năng xuất báo cáo riêng | Nguồn dữ liệu, khoảng thời gian và dung lượng giới hạn | Đọc đường dẫn bất kỳ hoặc xuất credential |
| Thay cấu hình | Luồng thay đổi riêng | Mẫu cấu hình được duyệt, kiểm tra và có khả năng khôi phục | Mở trình soạn thảo với quyền quản trị |

Không phải mọi chức năng trong ma trận đều phải được triển khai trong một vai trò. Vai trò chỉ xem trạng thái có thể tách khỏi vai trò được khởi động lại để tránh cấp thêm quyền không cần thiết.

### 3.2. Mặc định từ chối, mở dần theo bằng chứng

Với một giao diện quản trị, thao tác chưa được mô tả và kiểm thử phải bị từ chối mặc định. Khi xuất hiện nhu cầu mới, bổ sung hành động cụ thể cùng ràng buộc và bằng chứng kiểm thử.

Danh sách cấm đơn lẻ thường không đủ vì có thể còn chương trình, alias, mô-đun hoặc API khác thực hiện cùng kết quả. Thay vì chỉ cấm một tên shell, cần xác định hành vi nào không được phép và kiểm soát mọi giao diện có thể dẫn tới hành vi đó trong phạm vi triển khai.

Việc từ chối cũng cần được ghi nhận. Một lệnh bị chặn có thể phản ánh lỗi thao tác, chính sách chưa đáp ứng công việc hoặc một nỗ lực vượt quyền. Không tự động mở quyền chỉ vì có nhiều yêu cầu bị chặn.

## 4. Giới hạn cả tham số và đối tượng

### 4.1. Tên lệnh được phép chưa xác định đủ quyền

Các thành phần dưới đây cần được xét cùng nhau:

| Thành phần | Câu hỏi cần trả lời | Cách giới hạn điển hình |
| --- | --- | --- |
| Lệnh hoặc hàm | Có thực hiện đúng một nhiệm vụ không? | Công bố hàm chuyên dụng thay cho giao diện tổng quát |
| Tham số | Có thể đổi tác động hoặc bật chế độ nguy hiểm không? | Chỉ nhận các tham số cần thiết; ràng buộc kiểu và miền giá trị |
| Đối tượng | Có thể chuyển sang máy, dịch vụ, tenant hoặc tài nguyên khác không? | Ràng buộc đối tượng với vai trò và yêu cầu được duyệt |
| Đường dẫn | Có thể thoát khỏi thư mục hoặc đi qua liên kết không? | Chuẩn hóa, phân giải đích thực tế và kiểm tra quyền trên đích |
| Đầu vào thực thi | Có nhận mã, script block hoặc chuỗi lệnh không? | Tránh cung cấp khả năng chạy mã tùy ý |
| Đầu ra | Có làm lộ dữ liệu hoặc trả credential không? | Chỉ trả các trường cần cho tác vụ |
| Danh tính chạy | Khi lệnh chạy, hệ thống sử dụng quyền của ai? | Dùng quyền tối thiểu đủ thực hiện hành động |

Một tham số mang tên “tệp chẩn đoán” có thể trở thành quyền đọc bí mật nếu cho phép nhập đường dẫn bất kỳ. Một tham số “máy chủ” có thể mở rộng quyền sang hạ tầng khác nếu hệ thống không đối chiếu với tài sản đã được duyệt.

### 4.2. Ưu tiên giá trị hữu hạn và cấu trúc rõ ràng

Nếu chỉ có vài đối tượng hợp lệ, dùng danh sách giá trị cụ thể hoặc một bảng ánh xạ được bảo vệ. Nếu cần mẫu, xác định chính xác cú pháp, giới hạn độ dài và miền giá trị; tránh mẫu quá rộng.

Không ghép chuỗi người dùng nhập vào một lệnh shell chạy với đặc quyền cao. Khi cần gọi chương trình, truyền đối số qua giao diện có cấu trúc và xác thực ý nghĩa của từng đối số. Tách đối số khỏi shell giúp giảm lỗi diễn giải ký tự, nhưng không ngăn một tùy chọn hợp lệ của chương trình gây tác động vượt quyền.

Nếu nhận đường dẫn, chỉ kiểm tra tiền tố chuỗi thường chưa đủ. Cần xét đường dẫn tương đối, thành phần `..`, liên kết tượng trưng, junction và khả năng tệp đích bị thay giữa lúc kiểm tra và sử dụng. Khi khó bảo đảm an toàn, cung cấp mã báo cáo hoặc mã đối tượng để hệ thống tự chọn đường dẫn được bảo vệ.

### 4.3. Kiểm soát pipeline, đầu vào gián tiếp và kết hợp vai trò

Một chính sách cần xem xét cách truyền đối tượng qua pipeline, bí danh, tên lệnh đủ điều kiện mô-đun, nạp mô-đun và các dạng đầu vào gián tiếp mà công nghệ sử dụng cho phép.

Trong PowerShell JEA, khi một người dùng được ánh xạ tới nhiều role capability, các quyền có thể được cộng gộp. Không nên suy luận rằng một vai trò hẹp sẽ thu hẹp một vai trò rộng hơn cùng được cấp. Phải kiểm tra tập quyền hiệu lực sau khi kết hợp tất cả vai trò và cấu hình endpoint.

Ràng buộc từng lệnh cũng chưa bảo đảm ràng buộc cả chuỗi hành động. Ví dụ, nếu người dùng vừa được sửa tệp thực thi của dịch vụ vừa được khởi động lại dịch vụ, họ có thể làm cho mã do mình sửa chạy dưới danh tính của dịch vụ.

## 5. Ví dụ PowerShell JEA: hai chức năng cho một dịch vụ

Giả sử người trực ca cần xem trạng thái và khởi động lại `ContosoBillingAgent` trên một máy chủ Windows thành viên. Thay vì công bố một shell quản trị đầy đủ, endpoint JEA chỉ công bố hai hàm chuyên dụng:

- `Get-BillingAgentStatus`: trả về tên và trạng thái của dịch vụ đã cố định.
- `Restart-BillingAgent`: khởi động lại dịch vụ đó và trả về trạng thái sau thao tác.

Ví dụ role capability dưới đây minh họa nội dung của một tệp `.psrc`. Nó không tự thiết lập nhóm JIT, phê duyệt, endpoint, quyền dịch vụ hoặc nơi lưu bằng chứng.

```powershell
@{
    GUID = '94d0b8e6-18c5-4d4b-a0f7-840f83d96f73'
    Author = 'PAM Platform Team'
    Description = 'Thao tác giới hạn với ContosoBillingAgent'

    ModulesToImport = @('Microsoft.PowerShell.Management')

    VisibleCmdlets = @()
    VisibleExternalCommands = @()
    VisibleProviders = @()

    VisibleFunctions = @(
        'Get-BillingAgentStatus'
        'Restart-BillingAgent'
    )

    FunctionDefinitions = @(
        @{
            Name = 'Get-BillingAgentStatus'
            ScriptBlock = {
                [CmdletBinding()]
                param()

                $service = Microsoft.PowerShell.Management\Get-Service `
                    -Name 'ContosoBillingAgent' `
                    -ErrorAction Stop

                [pscustomobject]@{
                    Name = $service.Name
                    Status = [string]$service.Status
                }
            }
        }
        @{
            Name = 'Restart-BillingAgent'
            ScriptBlock = {
                [CmdletBinding()]
                param()

                Microsoft.PowerShell.Management\Restart-Service `
                    -Name 'ContosoBillingAgent' `
                    -ErrorAction Stop

                $service = Microsoft.PowerShell.Management\Get-Service `
                    -Name 'ContosoBillingAgent' `
                    -ErrorAction Stop

                [pscustomobject]@{
                    Name = $service.Name
                    Status = [string]$service.Status
                }
            }
        }
    )
}
```

### 5.1. Những giới hạn được thể hiện

Hai hàm không có tham số nghiệp vụ cho người gọi chọn dịch vụ, đường dẫn, máy chủ hoặc chuỗi lệnh. Các common parameter của PowerShell vẫn cần được tính đến khi đánh giá hành vi; `param()` không có nghĩa là loại bỏ toàn bộ tham số của một advanced function.

Các hàm gọi cmdlet quản lý bằng tên đầy đủ của mô-đun và dùng tên dịch vụ cố định. Kết quả chỉ gồm những trường được chọn, thay vì trả toàn bộ thông tin cấu hình dịch vụ.

Các danh sách `VisibleCmdlets`, `VisibleExternalCommands` và `VisibleProviders` rỗng cho biết role capability này không chủ động mở thêm các giao diện tương ứng. Một endpoint JEA vẫn có các lệnh nền phục vụ phiên tùy loại cấu hình và có thể nhận quyền từ role capability khác. Phải kiểm tra quyền hiệu lực; không xem đoạn cấu hình trên là bằng chứng rằng phiên chỉ có đúng hai lệnh trong mọi triển khai.

### 5.2. Điều kiện triển khai đi cùng ví dụ

Role capability phải được đặt trong mô-đun PowerShell theo cấu trúc JEA phù hợp, rồi được tham chiếu bởi role definition của một session configuration dùng `RestrictedRemoteServer`. Tệp capability, mô-đun và cấu hình endpoint phải do bên quản trị chính sách kiểm soát; người được cấp vai trò không được sửa chúng.

Danh tính thực thi của endpoint cần quyền truy vấn và điều khiển dịch vụ tương ứng. Việc chạy bằng virtual account không tự bảo đảm least privilege; cần xác định chính xác nhóm và quyền thực tế mà tài khoản đó nhận trong môi trường triển khai. Không áp dụng nguyên xi giả định của máy chủ thành viên cho domain controller.

Endpoint trong ví dụ cố định máy đích bằng nơi phiên được thiết lập. Chính sách truy cập endpoint phải ràng buộc máy chủ này với yêu cầu JIT. Không mở thêm lệnh remoting hoặc tham số máy đích cho người gọi nếu chưa có nhu cầu và kiểm soát tương ứng.

Tệp thực thi, thư mục cài đặt, cấu hình và những thành phần được dịch vụ nạp phải có quyền ghi phù hợp. Nếu người gọi có thể thay mã mà dịch vụ sẽ nạp, việc chỉ cho phép khởi động lại một dịch vụ vẫn có thể dẫn đến thực thi mã bằng quyền của dịch vụ.

`Restart-BillingAgent` chỉ thực hiện thao tác điều khiển dịch vụ và đọc lại trạng thái. Trạng thái `Running` chưa chứng minh ứng dụng đã phục hồi hoặc giao dịch thanh toán đã hoạt động. Nếu nhiệm vụ cần xác nhận sức khỏe ứng dụng, bổ sung một chức năng kiểm tra sức khỏe có phạm vi rõ ràng.

### 5.3. Phần JIT nằm ngoài role capability

Một thiết kế thực tế có thể cấp quyền truy cập endpoint khởi động lại thông qua nhóm tạm thời, hệ thống PAM hoặc cổng điều phối có thời hạn. Vai trò chỉ xem trạng thái có thể dùng nhóm riêng với quyền hẹp hơn.

Không xem việc ghi một mã phiếu vào tham số là bằng chứng đã phê duyệt. Nếu hệ thống nhận mã yêu cầu, nó phải đối chiếu với nguồn phê duyệt có thẩm quyền và kiểm tra người gọi, hành động, tài sản, thời hạn cùng các điều kiện liên quan.

Khi cửa sổ JIT kết thúc, việc xóa thành viên nhóm không bảo đảm tự đóng phiên đã được xác thực hoặc dừng tác vụ đang chạy. Cần thiết kế và kiểm thử cơ chế kết thúc phiên, thu hồi token hoặc kiểm tra thời hạn ở điểm thực thi phù hợp. Hành vi cụ thể phụ thuộc hệ thống xác thực và cách triển khai endpoint.

## 6. Nhận diện những quyền nhỏ có thể mở đường lớn

### 6.1. Chạy mã tùy ý

Các giao diện thực thi chuỗi lệnh, script block, chương trình con hoặc script do người dùng ghi thường vượt ra ngoài một tác vụ quản trị hẹp. Với vai trò chỉ cần thao tác dịch vụ, không có lý do mặc định để mở shell con, công cụ thực thi tổng quát hay hàm nhận nội dung mã.

Một wrapper chỉ đổi tên cho lệnh thực thi tùy ý vẫn giữ nguyên mức quyền nguy hiểm. Wrapper có giá trị khi nó giới hạn được đầu vào, đối tượng và hành vi bên trong.

### 6.2. Tệp, cấu hình và cơ chế nạp mã

Quyền sửa một tệp có thể tương đương với quyền chạy mã nếu tệp đó được một tiến trình đặc quyền nạp. Cần xét cấu hình có hook, plugin, mô-đun, thư viện, tác vụ định kỳ và script khởi động.

Quyền ghi vào thư mục chứa mô-đun JEA hoặc wrapper cũng có thể làm mất ý nghĩa của danh sách lệnh. Bảo vệ mã và cấu hình chính sách là một phần của ranh giới đặc quyền.

### 6.3. Đọc dữ liệu và truy cập vault

“Chỉ đọc” không đồng nghĩa với mức rủi ro thấp. Lệnh đọc tệp, biến môi trường, cấu hình hoặc log có thể làm lộ mật khẩu, token và khóa riêng. Nếu tài khoản người dùng chỉ cần khởi động lại dịch vụ, không mặc nhiên cho phép lấy credential của dịch vụ từ vault.

Khi workflow cần một bí mật để thực thi, ưu tiên cơ chế để thành phần thực thi được phép sử dụng bí mật mà không trả giá trị bí mật cho người gọi. Credential dài hạn bị lộ có thể còn sử dụng được sau khi cửa sổ JIT đã kết thúc; vòng đời và luân chuyển credential cần được quản lý riêng.

### 6.4. Ghi log và bảo vệ bằng chứng

Không cấp cùng một vai trò quyền thực hiện hành động đặc quyền và quyền xóa bằng chứng của hành động đó. Giới hạn quyền sửa log cục bộ và chuyển bằng chứng tới nơi có quyền truy cập độc lập khi thiết kế yêu cầu kiểm toán.

Transcript hữu ích nhưng không thay thế toàn bộ log thực thi hoặc log của tài nguyên đích. Nội dung đầu ra và thông báo lỗi cũng có thể chứa dữ liệu nhạy cảm; cần kiểm soát những gì được ghi và ai được xem.

## 7. Kiểm chứng giới hạn trước khi đưa vào sử dụng

Cần kiểm chứng cả tác vụ được phép và những biến thể phải bị từ chối. Các trường hợp dưới đây là gợi ý để xây dựng kiểm thử trong môi trường thử nghiệm của hệ thống đích.

| Trường hợp | Kỳ vọng | Bằng chứng cần đối chiếu |
| --- | --- | --- |
| Người đủ quyền gọi hàm xem trạng thái | Trả đúng tên và trạng thái dịch vụ | Người gọi, endpoint, kết quả |
| Người có JIT hợp lệ gọi hàm khởi động lại | Chỉ dịch vụ đã giao bị tác động | Quyết định cấp quyền và sự kiện ở máy đích |
| Truyền tên dịch vụ khác vào hàm không nhận tham số này | Bị từ chối trước khi thay đổi tài nguyên | Lỗi ràng buộc tham số và trạng thái tài nguyên |
| Gọi trực tiếp cmdlet quản trị không được mở | Bị từ chối theo quyền hiệu lực của endpoint | Log phiên và quyết định chính sách |
| Tìm cách chạy chương trình hoặc mã tùy ý | Không thực thi được trong vai trò này | Sự kiện từ chối; không có tác động ngoài phạm vi |
| Dùng alias, pipeline hoặc dạng gọi khác | Không vượt qua ràng buộc hành động | Kết quả tương đương chính sách dự kiến |
| Người dùng đồng thời có nhiều vai trò | Không xuất hiện quyền rộng ngoài thiết kế | Danh sách quyền hiệu lực đã tổng hợp |
| JIT hết hạn nhưng phiên còn mở | Thực thi tiếp bị chặn hoặc phiên bị kết thúc theo thiết kế | Mốc hết hạn và kết quả thử trên phiên cũ |
| Cố sửa wrapper hoặc mã dịch vụ | Bị từ chối nếu không có vai trò thay đổi riêng | Quyền trên tệp và log truy cập |
| Tác vụ lỗi hoặc dịch vụ không tồn tại | Báo lỗi rõ ràng, không chuyển sang cơ chế rộng hơn | Lỗi thực thi và không có hành động phụ ngoài phạm vi |

Kiểm thử cần dùng đúng danh tính, endpoint và cách kết hợp vai trò mà người vận hành sẽ dùng. Thử bằng tài khoản quản trị toàn quyền có thể che khuất lỗi quyền hoặc tạo ra kết quả không đại diện.

Sau khi cập nhật mô-đun, wrapper, cấu hình endpoint hoặc chương trình được gọi, cần đánh giá lại các giả định liên quan. Một bản cập nhật làm xuất hiện tham số mới hoặc đổi hành vi nạp cấu hình có thể thay đổi khả năng thực tế của lệnh được cấp.

## 8. Liên kết lệnh với phiên và bằng chứng kiểm toán

Với mỗi hành động đặc quyền, cần truy được ít nhất:

- Danh tính người yêu cầu, phương thức xác thực và danh tính thực thi ở đích.
- Mã yêu cầu hoặc phiên cấp quyền cùng quyết định phê duyệt tương ứng.
- Vai trò, phiên bản chính sách hoặc phiên bản wrapper áp dụng khi thực thi.
- Endpoint, tài nguyên đích, hành động và tham số đã được chuẩn hóa.
- Thời điểm bắt đầu, kết thúc, kết quả và lý do từ chối nếu có.
- Tham chiếu tới log phiên và sự kiện liên quan trên tài nguyên đích.

Không ghi giá trị bí mật vào bằng chứng chỉ để tăng khả năng truy vết. Với đầu vào nhạy cảm, ghi định danh hoặc thuộc tính cần thiết theo thiết kế bảo vệ dữ liệu.

Việc liên kết cần được thực hiện bằng định danh đáng tin cậy từ hệ thống, không chỉ dựa vào dòng mô tả do người gọi tự khai. Nếu nhiều phiên dùng chung một danh tính thực thi, phải có cơ chế đối chiếu đủ chính xác để xác định người và yêu cầu đứng sau từng hành động.

Khi điều tra sự cố, câu hỏi cần trả lời là: ai đã được cấp quyền gì, trong điều kiện nào, thực sự làm gì và tác động lên tài nguyên nào. Danh sách tên lệnh được phép chỉ trả lời một phần của chuỗi đó.

## 9. Xử lý nhu cầu vượt phạm vi hiện tại

Khi một thao tác hợp lệ bị chặn, ghi nhận tác vụ cần hoàn thành, tài sản liên quan, nguyên nhân bị chặn và những quyền tối thiểu còn thiếu. Sau đó cập nhật vai trò hoặc tạo workflow chuyên biệt với kiểm thử tương ứng.

Trường hợp khẩn cấp cần cơ chế break-glass được định nghĩa trước: người đủ điều kiện, phạm vi quyền, thời hạn, ghi nhận lý do và rà soát sau sử dụng. Không biến lỗi thiếu quyền của một wrapper thành cơ chế tự động mở shell quản trị đầy đủ.

Mỗi lần bổ sung hành động nên cập nhật ma trận quyền, tài liệu vận hành, trường hợp kiểm thử và bằng chứng phiên bản chính sách. Định kỳ loại bỏ những quyền không còn phục vụ tác vụ thực tế, đồng thời đối chiếu với log sử dụng và nhu cầu trực ca.

## 10. Nguyên tắc ghi nhớ

Giới hạn lệnh có hiệu quả khi ràng buộc được **hành động, tham số, đối tượng, danh tính và điều kiện thực thi**. Một danh sách tên lệnh đơn thuần không đủ nếu người dùng còn có thể chạy mã gián tiếp, sửa thành phần được tiến trình đặc quyền nạp hoặc truy cập một đường quản trị khác.

Trong PAM, JIT thu hẹp thời gian sử dụng quyền; JEA thu hẹp khả năng quản trị được cung cấp; quyền tối thiểu trên tài nguyên giới hạn tác động nếu có sai sót. Kết hợp ba lớp với kiểm kê đường truy cập, bảo vệ credential, giám sát phiên và lưu bằng chứng giúp quyền đặc biệt gắn với đúng nhiệm vụ đã được duyệt.
