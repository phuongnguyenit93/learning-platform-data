# Tách tài khoản admin và user

## 1. Vì sao một người cần hai tài khoản?

Một kỹ sư có thể vừa trả lời email, đọc tài liệu, tham gia họp, vừa quản trị máy chủ hoặc thay đổi chính sách truy cập. Những hoạt động này thuộc cùng một người nhưng không nên luôn mang cùng mức quyền.

Nếu tài khoản dùng hằng ngày đồng thời có quyền quản trị, một thao tác tưởng như bình thường — mở tệp đính kèm, đăng nhập vào trang giả mạo hoặc cài tiện ích trình duyệt — có thể tạo điểm xuất phát cho việc lạm dụng đặc quyền. Vấn đề không chỉ là mật khẩu mạnh hay yếu: phần mềm độc hại có thể sử dụng phiên đang đăng nhập, token đang có hoặc các quyền mà tài khoản được cấp sẵn.

**Tách tài khoản admin và user** là sử dụng các tài khoản riêng biệt cho hoạt động thông thường và hoạt động quản trị. Hai tài khoản gắn với cùng một con người để truy vết trách nhiệm, nhưng có tập quyền, điều kiện truy cập và phiên làm việc khác nhau.

Ví dụ, kỹ sư Lan có:

- `lan`: đọc email, sử dụng công cụ cộng tác và truy cập ứng dụng nghiệp vụ.
- `lan-admin`: thực hiện những tác vụ quản trị đã được cho phép, trong phạm vi cần thiết.

Mục tiêu là để việc sử dụng đặc quyền trở thành một hành động có chủ đích, có kiểm soát và có bằng chứng, thay vì là trạng thái mặc định trong cả ngày làm việc.

## 2. Tách tài khoản khác với đổi tên hiển thị

Hai tên đăng nhập chưa đủ tạo ra sự phân tách có ý nghĩa. Cần xem xét cả danh tính, quyền, thông tin xác thực và ngữ cảnh sử dụng.

| Thành phần | Tài khoản user | Tài khoản admin |
| --- | --- | --- |
| Mục đích | Công việc thông thường | Tác vụ quản trị xác định trước |
| Quyền | Quyền nghiệp vụ theo công việc | Quyền quản trị theo tài nguyên và nhiệm vụ |
| Trạng thái đặc quyền | Không có quyền quản trị thường trực | Ưu tiên kích hoạt quyền có thời hạn khi cần |
| Hoạt động thường ngày | Email, tài liệu, cộng tác | Không dùng cho các hoạt động này |
| Điều kiện đăng nhập | Theo chính sách chung của tổ chức | Chính sách chặt hơn, phù hợp độ nhạy của tài nguyên |
| Phiên và token | Dành cho ứng dụng thông thường | Phiên riêng, thời hạn phù hợp, kiểm soát việc lưu token |
| Kiểm toán | Ghi nhận hoạt động sử dụng | Gắn với tác vụ, lần kích hoạt quyền và thay đổi thực tế |

Nếu cả hai tài khoản dùng chung mật khẩu, cùng giữ vai trò quản trị thường trực và đăng nhập lẫn lộn trên cùng một môi trường không đáng tin cậy, giá trị bảo vệ sẽ giảm đáng kể.

Sự phân tách cần đi xuyên suốt luồng IAM: cấp phát danh tính, xác thực, cấp quyền, quản lý phiên, thu hồi quyền và kiểm toán. Tên có hậu tố `-admin` chỉ giúp nhận diện; nó không tự tạo ra chính sách bảo mật.

## 3. Giảm phạm vi ảnh hưởng khi tài khoản bị chiếm đoạt

### 3.1. Khi chỉ có một tài khoản

Giả sử tài khoản `lan` có quyền đọc email và quản trị môi trường production. Khi kẻ tấn công chiếm được phiên phù hợp, chúng có thể tìm cách sử dụng các quyền đang có để thay đổi cấu hình, tạo danh tính mới hoặc cấp thêm quyền.

Trong mô hình này, công việc ít nhạy cảm và quyền rất nhạy cảm cùng nằm trên một danh tính. Sai sót trong tác vụ thông thường có thể dẫn đến hậu quả vượt xa phạm vi tác vụ đó.

### 3.2. Khi có tài khoản quản trị riêng

Nếu `lan` không có quyền quản trị, việc chiếm tài khoản này không tự động mang lại quyền của `lan-admin`. Kẻ tấn công phải vượt qua thêm những ranh giới như thông tin xác thực riêng, điều kiện thiết bị, bước xác thực bổ sung hoặc quy trình kích hoạt quyền.

Tuy nhiên, tách tài khoản không bảo đảm rằng sự cố ở tài khoản user không bao giờ ảnh hưởng tài khoản admin. Ranh giới có thể bị phá vỡ nếu:

- Phiên admin được mở trên thiết bị đã bị kiểm soát.
- Tài khoản user được phép tự đặt lại thông tin xác thực cho tài khoản admin.
- Mật khẩu, mã khôi phục hoặc khóa của admin nằm trong nơi mà tài khoản user có thể đọc.
- Cơ chế liên kết hoặc chuyển đổi tài khoản cấp đặc quyền mà không đánh giá lại điều kiện truy cập.
- Token quản trị được sao chép vào công cụ dùng hằng ngày.

Vì vậy, phải bảo vệ cả đường đăng nhập, đường khôi phục tài khoản và môi trường thực hiện quản trị.

## 4. Thiết kế tài khoản theo người, nhiệm vụ và phạm vi

### 4.1. Mỗi tài khoản quản trị phải có chủ thể chịu trách nhiệm

Tài khoản quản trị cá nhân cần liên kết được với người sở hữu. Một bản ghi quản lý có thể thể hiện:

```text
Người sở hữu: employee-1042
Tài khoản thường: lan
Tài khoản quản trị: lan-admin
Phạm vi được xét cấp: hệ thống ứng dụng A
Vai trò đủ điều kiện kích hoạt: application-operator
Người phê duyệt: chủ sở hữu hệ thống A
Ngày rà soát tiếp theo: theo chu kỳ quản trị quyền của tổ chức
```

Đây là ví dụ dữ liệu quản lý, không phải định dạng bắt buộc của một sản phẩm IAM.

Không nên thay tài khoản quản trị cá nhân bằng một tài khoản dùng chung mà mọi người đều biết mật khẩu. Tài khoản dùng chung làm khó việc xác định ai thực hiện thay đổi, ai đã tiết lộ thông tin xác thực và phải thu hồi quyền của ai khi một người rời nhóm.

Nếu một hệ thống cũ buộc phải dùng tài khoản đích dùng chung, cần cơ chế trung gian phù hợp để gắn từng phiên sử dụng với người thực hiện, kiểm soát cấp phát thông tin xác thực và lưu bằng chứng. Hạn chế của tài khoản đích vẫn phải được ghi nhận.

### 4.2. Không mặc định tài khoản admin là toàn quyền

Tách tài khoản chỉ là một phần của nguyên tắc ít quyền nhất. Một người vận hành ứng dụng không đương nhiên cần quản trị danh tính, sửa chính sách bảo mật hoặc quản trị mọi hệ thống khác.

Có thể phân chia quyền theo các chiều:

- **Tài nguyên:** chỉ ứng dụng A hoặc một nhóm máy chủ được giao.
- **Môi trường:** development, staging và production.
- **Hành động:** xem cấu hình, khởi động lại dịch vụ, cập nhật cấu hình hoặc quản lý quyền.
- **Thời gian:** chỉ trong khoảng thực hiện nhiệm vụ.
- **Điều kiện:** thiết bị quản trị đáp ứng chính sách, phiên xác thực phù hợp, yêu cầu thay đổi hợp lệ.

RBAC giúp gom các quyền thành vai trò công việc. Chính sách dựa trên thuộc tính hoặc điều kiện có thể giới hạn thêm ngữ cảnh sử dụng. Không nên dùng một vai trò `admin` quá rộng để thay cho việc xác định nhu cầu thực tế.

### 4.3. Có thể cần nhiều ranh giới quản trị

Một tài khoản quản trị duy nhất cho mọi hệ thống vẫn có thể tạo phạm vi ảnh hưởng quá lớn. Quản trị nền tảng danh tính, quản trị máy chủ và quản trị ứng dụng có thể cần các tài khoản hoặc ranh giới phiên riêng, tùy mức độ tin cậy và mức độ ảnh hưởng.

Ví dụ, tài khoản có quyền thay đổi hệ thống xác thực trung tâm không nên được dùng để đăng nhập vào một máy thử nghiệm có độ tin cậy thấp. Nếu thông tin xác thực đặc quyền cao bị lộ tại đó, sự phân tách giữa các tầng có thể mất tác dụng.

Không cần tạo nhiều tài khoản một cách máy móc. Mỗi ranh giới phải có lý do rõ ràng, người sở hữu, quy trình sử dụng và khả năng quản lý vòng đời.

## 5. Một phiên quản trị nên diễn ra như thế nào?

Một quy trình mẫu cho tác vụ thay đổi cấu hình production:

1. Lan dùng tài khoản user để tiếp nhận yêu cầu và xác định nhiệm vụ.
2. Yêu cầu thay đổi ghi rõ hệ thống, hành động, thời gian và cách khôi phục nếu thay đổi không đạt kết quả.
3. Lan mở môi trường quản trị được tổ chức cho phép và đăng nhập bằng tài khoản quản trị.
4. Hệ thống kiểm tra trạng thái tài khoản, phương thức xác thực, điều kiện thiết bị và các điều kiện cấp quyền.
5. Vai trò cần thiết được kích hoạt trong khoảng thời gian đã xác định, có phê duyệt nếu chính sách yêu cầu.
6. Lan thực hiện đúng tác vụ, kiểm tra kết quả và ghi nhận bằng chứng.
7. Khi công việc kết thúc, quyền tạm thời bị thu hồi và phiên quản trị được kết thúc theo khả năng của hệ thống.

Luồng khái quát:

```text
Tài khoản user tiếp nhận công việc
                |
                v
Yêu cầu tác vụ và xác định phạm vi
                |
                v
Tài khoản admin đăng nhập trong môi trường quản trị
                |
                v
Đánh giá điều kiện + kích hoạt quyền có thời hạn
                |
                v
Thực hiện tác vụ + ghi nhật ký
                |
                v
Thu hồi quyền + kết thúc phiên + đóng yêu cầu
```

Tách tài khoản không có nghĩa là một yêu cầu hợp lệ sẽ tự động được thực hiện. Người dùng vẫn cần được xác thực và được ủy quyền cho đúng hành động trên đúng tài nguyên ở thời điểm thực hiện.

SSO có thể giúp giảm số lần nhập thông tin xác thực, nhưng việc chuyển sang ngữ cảnh quản trị phải tuân thủ chính sách dành cho tài khoản quản trị. Không mặc định rằng phiên user hiện có đã đáp ứng mọi điều kiện của phiên admin.

## 6. Tách phiên làm việc và thông tin xác thực

### 6.1. Bảo vệ phương thức xác thực và khôi phục

Không dùng chung mật khẩu giữa tài khoản thường và tài khoản quản trị. Tài khoản quản trị cần phương thức xác thực mạnh phù hợp với rủi ro; ưu tiên phương thức có khả năng chống lừa đảo khi hạ tầng hỗ trợ.

Cần đánh giá toàn bộ chuỗi khôi phục. Ví dụ, nếu chỉ cần đọc hộp thư của tài khoản user là có thể đặt lại mật khẩu admin mà không có kiểm soát bổ sung, hộp thư đó trở thành đường gián tiếp để chiếm đặc quyền.

Không phải mọi tổ chức đều phải cấp hai thiết bị xác thực vật lý khác nhau cho một người. Điều cần xác định là một sự cố đơn lẻ có thể làm mất những phương thức nào, tài khoản nào sẽ bị ảnh hưởng và quy trình khôi phục được kiểm soát ra sao.

### 6.2. Tách môi trường sử dụng theo mức rủi ro

Tài khoản admin không nên được dùng để đọc email, duyệt web thông thường, tải phần mềm tùy ý hoặc tham gia công cụ cộng tác không phục vụ tác vụ quản trị.

Các biện pháp có thể gồm môi trường quản trị chuyên dụng, máy trạm quản trị được kiểm soát, máy trung gian hoặc công cụ quản lý phiên đặc quyền. Thiết kế cụ thể phụ thuộc vào tài nguyên và mô hình vận hành.

Một hồ sơ trình duyệt riêng có thể giảm nhầm lẫn cookie và tài khoản, nhưng không tạo mức cách ly tương đương một thiết bị hay môi trường quản trị được bảo vệ riêng. Phần mềm độc hại trên thiết bị có thể ảnh hưởng nhiều hồ sơ hoặc phiên.

### 6.3. Quản lý token, khóa và phiên lệnh

Tài khoản đã tách nhưng token quản trị vẫn tồn tại lâu dài trong terminal hoặc công cụ phát triển thì đặc quyền vẫn có thể bị sử dụng ngoài ý muốn.

Cần xem xét:

- Token đang đại diện cho tài khoản và vai trò nào.
- Token có quyền trên môi trường nào, còn hiệu lực bao lâu.
- Công cụ có lưu thông tin xác thực hoặc tự gia hạn phiên không.
- Quy trình kết thúc công việc có xóa thông tin xác thực tạm hoặc kết thúc phiên theo thiết kế không.
- Những phiên hoặc token nào có thể bị vô hiệu hóa khi có sự cố.

Việc gỡ vai trò hoặc khóa tài khoản không luôn làm mọi token đã phát hành mất hiệu lực ngay lập tức. Cần hiểu cơ chế của từng hệ thống và kết hợp thời hạn token, thu hồi phiên, đánh giá quyền tại tài nguyên cùng các kiểm soát có sẵn.

## 7. Ví dụ phân quyền cho nhóm vận hành ứng dụng

Nhóm vận hành có nhiệm vụ theo dõi và khởi động lại ứng dụng A ở production. Họ không có nhiệm vụ tạo tài khoản mới hoặc sửa chính sách IAM.

Một thiết kế minh họa:

| Tài khoản/ngữ cảnh | Quyền được cấp | Điều kiện và giới hạn |
| --- | --- | --- |
| `lan` | Đọc tài liệu, tạo yêu cầu vận hành | Không có quyền thay đổi production |
| `lan-admin` trước kích hoạt | Đăng nhập cổng quản trị, gửi yêu cầu kích hoạt vai trò | Chưa có quyền vận hành production tương ứng |
| `lan-admin` khi kích hoạt `application-operator` | Xem trạng thái và khởi động lại ứng dụng A | Có thời hạn, đúng tài nguyên và yêu cầu hợp lệ |
| `lan-admin` sau kết thúc | Trở về trạng thái không có quyền tạm thời | Kiểm tra việc thu hồi và xử lý phiên còn tồn tại |

Mã giả sau thể hiện ý tưởng đánh giá quyền, không phải cấu hình triển khai:

```text
allow(request):
    require request.account.type == "ADMIN"
    require request.account.enabled
    require request.session.satisfies_admin_policy
    require active_grant.matches(request.account, "application-operator")
    require active_grant.is_within_validity_period
    require request.resource == "production/application-A"
    require request.action in {"read-status", "restart"}
    require request.change_reference.is_valid
    return true

otherwise:
    return false
```

Hậu tố của tên đăng nhập không xuất hiện trong quyết định cấp quyền. Hệ thống phải dựa vào dữ liệu danh tính và chính sách đáng tin cậy. Trường `account.type` trong ví dụ cũng phải do hệ thống quản lý, không lấy từ giá trị mà người gọi tự khai báo.

Nếu Lan cần thay đổi chính sách IAM, vai trò vận hành ứng dụng không đáp ứng yêu cầu đó. Cần một quy trình và quyền riêng thay vì mở rộng vai trò hiện có cho tiện.

## 8. Tách tài khoản không thay thế phân tách nhiệm vụ

**Tách tài khoản** tập trung vào việc một người sử dụng các ngữ cảnh quyền khác nhau. **Phân tách nhiệm vụ** tập trung vào việc phân bổ những trách nhiệm không nên do cùng một người tự hoàn tất.

Ví dụ:

- Lan dùng `lan` để tạo yêu cầu và `lan-admin` để thực hiện thay đổi: đây là tách tài khoản.
- Minh xét duyệt yêu cầu của Lan trước khi Lan kích hoạt quyền: đây là một dạng phân tách nhiệm vụ.

Nếu Lan dùng hai tài khoản của chính mình để vừa yêu cầu vừa tự phê duyệt, việc có hai tài khoản không tạo ra sự phê duyệt độc lập. Hệ thống cần liên kết các tài khoản với cùng người sở hữu để đánh giá các ràng buộc này.

Điều tương tự áp dụng cho rà soát quyền: người sở hữu tài khoản admin không nên được coi là người rà soát độc lập chỉ vì họ dùng tài khoản user để xác nhận quyền của mình.

## 9. Quản lý vòng đời cả hai tài khoản

### 9.1. Khi cấp phát

Tài khoản quản trị cần có lý do nghiệp vụ, chủ sở hữu, phạm vi quyền và cơ chế rà soát. Không tự động cấp tài khoản admin cho mọi nhân viên kỹ thuật chỉ vì họ thuộc một phòng ban rộng.

Quy trình cấp phát phải liên kết tài khoản user và tài khoản admin với cùng một định danh nhân sự hoặc chủ thể quản lý ổn định. Mối liên kết này phục vụ kiểm toán, chống tự phê duyệt và thu hồi đầy đủ khi có thay đổi nhân sự.

### 9.2. Khi chuyển vị trí hoặc đổi nhiệm vụ

Quyền quản trị cũ cần được rà soát và thu hồi theo nhiệm vụ mới. Giữ lại tài khoản chỉ vì có thể cần trong tương lai dễ dẫn đến tích lũy đặc quyền.

Cần kiểm tra cả quyền trực tiếp, nhóm, vai trò đủ điều kiện kích hoạt, quyền trên hệ thống đích và thông tin xác thực còn tồn tại. Việc xóa một nhóm ở hệ thống danh tính trung tâm chưa chắc xử lý hết các tài khoản cục bộ đã tạo trước đó.

### 9.3. Khi nghỉ việc hoặc xảy ra sự cố

Không chỉ khóa tài khoản user rồi giả định tài khoản admin cũng đã bị khóa. Quy trình phải xử lý mọi tài khoản liên quan, quyền đủ điều kiện, phiên, phương thức xác thực, khóa cá nhân và thông tin khôi phục trong phạm vi quản lý.

Nếu nghi ngờ thiết bị user bị chiếm quyền, cần đánh giá liệu phiên admin từng hoạt động trên thiết bị đó có bị ảnh hưởng không. Kết quả điều tra sẽ quyết định phạm vi thu hồi phiên, thay thông tin xác thực và kiểm tra các thay đổi đặc quyền.

### 9.4. Với tài khoản khẩn cấp và workload

Tài khoản khẩn cấp phục vụ tình huống cơ chế quản trị thông thường không hoạt động cần được quản lý riêng, giám sát chặt và kiểm tra định kỳ. Không dùng tài khoản khẩn cấp làm tài khoản admin hằng ngày để bỏ qua quy trình.

Ứng dụng, tác vụ tự động và pipeline nên sử dụng danh tính workload hoặc cơ chế dành cho tự động hóa phù hợp. Không đưa mật khẩu hay token của tài khoản admin cá nhân vào script chạy định kỳ. Cách làm đó gắn quyền của hệ thống tự động với vòng đời một người và làm khó việc truy vết ai thực hiện tác vụ.

## 10. Kiểm toán: từ con người đến hành động thực tế

Nhật ký hữu ích cần cho phép liên kết được:

```text
Người sở hữu
    -> Tài khoản admin
    -> Sự kiện xác thực / phiên
    -> Lần kích hoạt quyền
    -> Yêu cầu công việc
    -> Hành động trên tài nguyên
    -> Kết quả và thời điểm kết thúc
```

Chỉ ghi “admin đã đăng nhập” là chưa đủ để giải thích ai đã đổi chính sách hoặc vì sao một dịch vụ bị khởi động lại. Ngược lại, chỉ có yêu cầu thay đổi đã được duyệt cũng chưa chứng minh thay đổi thực tế đúng phạm vi.

Những trường dữ liệu thường hữu ích gồm định danh chủ thể ổn định, tài khoản thực hiện, tài nguyên đích, hành động, thời gian, vai trò đang hoạt động, kết quả và mã tương quan. Không đưa mật khẩu, mã xác thực hay token vào nhật ký.

Các dấu hiệu cần xem xét có thể gồm tài khoản admin xuất hiện trong ứng dụng email, đăng nhập từ thiết bị không dành cho quản trị, sử dụng sau khi nhiệm vụ kết thúc, kích hoạt quyền bất thường hoặc thay đổi đường khôi phục tài khoản. Ý nghĩa của từng dấu hiệu cần được đánh giá trong bối cảnh vận hành cụ thể.

## 11. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Tạo tên `-admin` nhưng giữ cùng quyền và mật khẩu | Ranh giới chủ yếu tồn tại trên tên gọi | Tách thông tin xác thực, vai trò và điều kiện sử dụng |
| Dùng tài khoản admin để đọc email | Đưa đặc quyền vào hoạt động tiếp xúc nhiều nội dung bên ngoài | Dùng tài khoản user cho hoạt động thường ngày |
| Cho user tự đặt lại admin qua một đường khôi phục yếu | Tạo đường vòng để chiếm đặc quyền | Đánh giá đường khôi phục như một phần của kiểm soát admin |
| Cho mọi admin quyền quản trị toàn hệ thống | Một tài khoản bị lạm dụng gây ảnh hưởng rộng | Giới hạn quyền theo nhiệm vụ, tài nguyên và thời gian |
| Dùng tài khoản quản trị chung không truy vết | Khó gắn thay đổi với người thực hiện | Ưu tiên tài khoản cá nhân; quản lý phiên trung gian khi có hạn chế hệ thống cũ |
| Đăng nhập đặc quyền cao vào môi trường ít tin cậy | Có thể lộ thông tin xác thực có giá trị cao | Thiết kế ranh giới quản trị theo mức độ tin cậy |
| Thu hồi vai trò nhưng bỏ qua phiên và token | Quyền có thể còn sử dụng được trong một khoảng thời gian | Kiểm tra cơ chế hiệu lực, thu hồi và thời hạn của từng hệ thống |
| Khóa tài khoản thường khi nhân viên nghỉ việc | Tài khoản quản trị liên quan có thể vẫn hoạt động | Thu hồi theo người sở hữu và toàn bộ danh tính liên kết |

## 12. Triển khai theo một phạm vi có thể kiểm chứng

Bắt đầu với một nhóm quản trị và một nhóm tài nguyên có chủ sở hữu rõ ràng. Kiểm kê ai đang có quyền quản trị, qua tài khoản nào, quyền đến từ đâu và thông tin xác thực được sử dụng ở đâu.

Sau đó xác định mô hình tài khoản, quyền nền, quyền có thể kích hoạt và môi trường quản trị. Cần chuẩn bị quy trình tác nghiệp đủ rõ để người vận hành thực hiện được công việc hợp lệ, kể cả tình huống khẩn cấp đã xác định.

Trước khi mở rộng, kiểm chứng bằng các tình huống cụ thể:

- Tài khoản user không thể thực hiện tác vụ quản trị thuộc phạm vi đã tách.
- Tài khoản admin chỉ có quyền đúng nhiệm vụ, tài nguyên và điều kiện được cấp.
- Một người không thể dùng hai tài khoản của mình để vượt qua yêu cầu phê duyệt độc lập.
- Kết thúc thời hạn kích hoạt dẫn đến kết quả thu hồi quyền và xử lý phiên đúng thiết kế.
- Khi chuyển vị trí hoặc nghỉ việc, mọi tài khoản và quyền liên quan đều được xử lý.
- Nhật ký cho phép truy từ hành động trên tài nguyên về đúng người và yêu cầu công việc.

Thành công của việc tách tài khoản được thể hiện ở các ranh giới này, không nằm ở số lượng tài khoản mới được tạo. Một mô hình tốt giúp người dùng làm việc thông thường với quyền thấp, sử dụng đặc quyền đúng lúc và để lại dấu vết đủ rõ cho vận hành lẫn kiểm toán.
