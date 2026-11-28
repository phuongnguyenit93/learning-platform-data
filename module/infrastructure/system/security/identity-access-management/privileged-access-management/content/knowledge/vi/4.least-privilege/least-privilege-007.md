# Permission theo action

## 1. Permission theo action là gì?

**Permission theo action** là cách mô tả và kiểm tra quyền dựa trên hành động cụ thể mà một danh tính muốn thực hiện. Thay vì chỉ hỏi người dùng có phải “quản trị viên” hay không, hệ thống xác định người dùng có được thực hiện một thao tác trên một tài nguyên, trong những điều kiện nhất định hay không.

Ví dụ, một kỹ sư được phép xem trạng thái và khởi động lại dịch vụ thanh toán trên máy chủ được giao. Quyền đó không mặc nhiên bao gồm sửa cấu hình dịch vụ, đọc credential, tạo người dùng hoặc khởi động lại mọi dịch vụ khác.

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), action là một đơn vị quan trọng để áp dụng least privilege. Nó giúp chuyển nhu cầu quản trị thành những khả năng có thể cấp, thực thi, quan sát và thu hồi.

Bài học trong chương Least privilege giúp người học:

- Phân biệt action với vai trò, endpoint, câu lệnh và phương thức HTTP.
- Thiết kế permission theo danh tính, action, tài nguyên và điều kiện.
- Quản lý tham số, quyền phụ thuộc và các đường tác động gián tiếp.
- Kết hợp action với JIT, JEA, vault và giám sát phiên.
- Kiểm chứng ranh giới quyền và quản lý thay đổi danh mục action.

Các tên action trong bài là quy ước minh họa, không phải tên quyền có thể áp dụng trực tiếp cho mọi hệ điều hành, cloud hoặc sản phẩm PAM.

## 2. Một permission cần nhiều hơn tên action

Một action mô tả **việc gì được thực hiện**. Một permission hoàn chỉnh cần xác định thêm **ai**, **trên tài nguyên nào** và **trong điều kiện nào**.

Có thể dùng mô hình khái niệm sau:

```text
Quyết định truy cập =
    đánh giá chính sách(
        danh tính,
        action,
        tài nguyên,
        tham số liên quan,
        ngữ cảnh
    )
```

Mô hình này không quy định thuật toán kết hợp chính sách của một sản phẩm. Khi triển khai, phải hiểu cách hệ thống đích xử lý quyền gán trực tiếp, quyền kế thừa, điều kiện và các giới hạn khác.

| Thành phần | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Danh tính | Ai thực hiện hoặc yêu cầu tác vụ? | Tài khoản quản trị cá nhân của kỹ sư trực |
| Action | Hành động nào được yêu cầu? | `service.restart` |
| Tài nguyên | Đối tượng nào bị tác động? | Dịch vụ `payment-api` trên `prod-app-03` |
| Tham số | Hành động được phép biến thiên đến đâu? | Chỉ đúng dịch vụ, không cho chọn chương trình tùy ý |
| Ngữ cảnh | Điều kiện nào phải được đáp ứng? | Ticket còn hiệu lực, thời hạn kích hoạt, thiết bị phù hợp |
| Bằng chứng | Cần ghi nhận điều gì? | Người yêu cầu, quyết định, đích, kết quả và thu hồi |

Hai permission cùng có action `service.restart` vẫn khác nhau nếu một quyền chỉ áp dụng cho một dịch vụ còn quyền kia áp dụng cho mọi máy production.

Tên action có vẻ hẹp cũng chưa đủ. Nếu một action nhận tham số cho phép chọn script bất kỳ, nó có thể tạo khả năng rộng hơn nhiều so với tên gọi.

## 3. Phân biệt action với các khái niệm dễ nhầm

### 3.1. Action và vai trò

Vai trò thường gom nhiều permission phục vụ một nhóm nhiệm vụ. Action mô tả một khả năng cụ thể bên trong tập quyền đó.

Ví dụ, vai trò `PaymentOperator` có thể chứa:

- `service.readStatus`.
- `service.readOperationalLogs`.
- `service.restart`.

Tuy nhiên, tên vai trò không chứng minh nó chỉ chứa ba action này, cũng không xác định tài nguyên được áp dụng. Cần xem nội dung và phạm vi của vai trò.

Tổ chức có thể dùng RBAC để gán permission theo vai trò và dùng điều kiện để giới hạn thêm. Permission theo action không bắt buộc phải loại bỏ mô hình vai trò.

### 3.2. Action và endpoint API

Một endpoint có thể phục vụ một hoặc nhiều thao tác. Ngược lại, nhiều endpoint hoặc phiên bản API có thể thực hiện cùng một hành vi nghiệp vụ.

Cần có ánh xạ rõ từ yêu cầu thực tế sang action được kiểm tra. Nếu API cũ và API mới đều sửa cấu hình, cả hai phải tuân theo giới hạn tương ứng. Chỉ bảo vệ một đường giao diện sẽ để lại đường truy cập khác.

Phương thức HTTP không đủ để quyết định quyền. Một yêu cầu có thể mang tên “xem” nhưng gọi thành phần làm thay đổi trạng thái; một thao tác dùng cùng phương thức có thể có mức tác động rất khác nhau.

### 3.3. Action và câu lệnh quản trị

Một câu lệnh có thể cho phép nhiều hành vi tùy tham số, cấu hình, đường dẫn và thành phần được gọi. Việc cho phép một tên chương trình không bảo đảm đã giới hạn được action nghiệp vụ.

Ví dụ, tác vụ “khởi động lại dịch vụ đã chỉ định” khác với việc cho phép chạy một công cụ quản trị hệ thống với mọi tham số. Nếu người gọi còn sửa được script hoặc cấu hình mà tác vụ sử dụng, phạm vi quyền có thể rộng hơn dự kiến.

### 3.4. Action và xác thực

Xác thực trả lời người gọi là ai hoặc đang kiểm soát phương tiện xác thực nào. Phân quyền theo action quyết định người đó được làm gì trong yêu cầu cụ thể.

MFA, ticket và phê duyệt có thể là điều kiện cấp quyền. Chúng không tự giới hạn tập action sau khi một phiên toàn quyền đã được mở.

### 3.5. Action và kết quả nghiệp vụ

Một nhiệm vụ như “khôi phục dịch vụ” có thể cần nhiều action. Cần phân rã thành các bước và nhận diện bước nào bắt buộc, bước nào chỉ là tiện ích của công cụ.

Nếu một công cụ tự tải metadata trước khi thực hiện thay đổi, hãy xác định dữ liệu tối thiểu mà nó cần đọc. Không mặc nhiên cấp quyền đọc toàn bộ môi trường để làm cho một công cụ hoạt động.

## 4. Thiết kế danh mục action

### 4.1. Đặt tên theo đối tượng và hành vi

Một quy ước như `đối_tượng.hành_động` giúp người duyệt hiểu ý nghĩa, ví dụ `service.restart` hoặc `identity.grantRole`. Quan trọng hơn quy ước tên là mô tả hành vi thực tế.

Một action cần có:

- Mục đích và tác động được phép.
- Loại tài nguyên và cách xác định phạm vi.
- Tham số được nhận và giới hạn của chúng.
- Quyền hoặc thao tác phụ thuộc.
- Dữ liệu có thể được trả về.
- Bằng chứng có thể thu thập.
- Chủ sở hữu chịu trách nhiệm khi hành vi thay đổi.

### 4.2. Danh mục minh họa cho vận hành dịch vụ

| Action | Hành vi dự kiến | Giới hạn cần chú ý |
| --- | --- | --- |
| `service.readStatus` | Xem trạng thái vận hành | Không trả về secret hoặc cấu hình nhạy cảm ngoài nhu cầu |
| `service.readOperationalLogs` | Đọc phần log phục vụ nhiệm vụ | Giới hạn dịch vụ, nội dung và khoảng thời gian |
| `service.restart` | Khởi động lại đúng dịch vụ | Không cho chọn dịch vụ hoặc chương trình ngoài phạm vi |
| `service.updateApprovedConfig` | Thay cấu hình đã xác định | Giới hạn trường, giá trị và trạng thái trước thay đổi |
| `service.deployVersion` | Triển khai phiên bản phù hợp quy trình | Kiểm soát nguồn, phiên bản và quyền của workload |
| `identity.grantRole` | Thay quyền của danh tính | Phân tách với thao tác vận hành thông thường |
| `secret.read` | Lấy hoặc xem một bí mật | Có thể mở đường tới quyền của danh tính khác |
| `audit.changeRetention` | Thay chính sách lưu bằng chứng | Không gom vào vai trò thao tác trên ứng dụng |

Các action trong bảng không có cùng mức rủi ro. Việc đọc secret có thể tạo đặc quyền rất cao; triển khai mã có thể dẫn tới sử dụng quyền của ứng dụng; thay chính sách audit có thể làm giảm khả năng điều tra.

### 4.3. Chọn độ chi tiết có thể vận hành

Action quá rộng như `system.manage` khó giải thích phạm vi. Danh mục quá vụn, tách những khác biệt không ảnh hưởng chính sách, có thể làm tăng gánh nặng quản lý mà không tăng khả năng kiểm soát.

Một action nên đủ rõ để chủ tài nguyên hiểu tác động, người duyệt đánh giá nhu cầu và điểm thực thi phân biệt được với hành vi khác. Có thể dùng tham số được kiểm soát thay vì tạo tên action mới cho từng máy.

Không nên tạo một action mang tên hẹp nếu cơ chế đích vẫn chỉ cấp shell toàn quyền. Khi chưa thực thi được giới hạn, phải mô tả rõ khoảng trống và phần quyền rộng còn lại.

## 5. Gắn action với đúng tài nguyên

### 5.1. Xác định tài nguyên từ dữ liệu đáng tin cậy

Yêu cầu có thể chứa tên máy, mã dịch vụ hoặc mã tài nguyên. Hệ thống cần đối chiếu chúng với tài nguyên thực tế trước khi phân quyền và thực hiện.

Không chỉ dựa vào một trường do người gọi tự khai như “môi trường thử nghiệm”. Tài nguyên thực tế có thể thuộc production hoặc ánh xạ sang một đối tượng khác.

Nếu tên có thể được đổi hoặc tái sử dụng, cần cân nhắc định danh ổn định và cách xử lý vòng đời tài nguyên. Một phê duyệt cho dịch vụ cũ không nên tự trở thành phê duyệt cho mọi đối tượng mới dùng lại tên đó.

### 5.2. Phạm vi theo nhãn và thuộc tính

Một chính sách có thể cho phép action trên tài nguyên có nhãn ứng dụng hoặc môi trường phù hợp. Khi đó, quyền sửa nhãn là một phần của mô hình bảo mật.

Nếu người dùng tự sửa được thuộc tính quyết định phạm vi, họ có thể đưa tài nguyên khác vào tập được phép. Cần xác định ai quản lý thuộc tính và cách thay đổi được kiểm tra.

### 5.3. Tài nguyên cha và quyền kế thừa

Một permission hẹp ở cấp tài nguyên có thể cùng tồn tại với quyền rộng ở cấp dự án, nhóm hoặc tổ chức. Quyền hiệu lực phải được tính từ các nguồn liên quan theo cơ chế của nền tảng.

Không suy ra rằng thêm một vai trò hẹp sẽ tự giảm quyền rộng đã có. Việc thu hẹp thường cần xử lý quyền cũ và đường chuyển sang danh tính khác.

### 5.4. Action trên tài nguyên chưa tồn tại

Với thao tác tạo mới, hệ thống cần kiểm soát nơi được tạo, loại đối tượng, cấu hình và các quyền mà đối tượng mới có thể nhận. Chỉ kiểm tra “được tạo tài nguyên” là chưa đủ nếu người gọi được gắn một danh tính rất mạnh hoặc cấu hình quan hệ tin cậy tùy ý.

Cần xem cả quyền quản lý đối tượng sau khi tạo và khả năng đối tượng đó ảnh hưởng tài nguyên khác.

## 6. Kiểm soát tham số, phụ thuộc và hiệu ứng gián tiếp

### 6.1. Tham số là một phần của ranh giới quyền

Các tham số nhạy cảm có thể gồm tên dịch vụ, đường dẫn, tài nguyên đích, danh tính thực thi, trường cấu hình và phạm vi dữ liệu. Hệ thống cần kiểm tra chúng theo cấu trúc và tập giá trị được phép.

Ví dụ, action `service.restart` không nên cho người gọi tùy chọn một script để thực thi dưới quyền quản trị. Một tác vụ đổi cấu hình không nên cho thay cả cấu hình xác thực nếu nhiệm vụ chỉ cho đổi giới hạn xử lý.

### 6.2. Quyền phụ thuộc cần được giải thích riêng

Một thao tác có thể cần đọc metadata, khóa đối tượng hoặc kiểm tra phiên bản trước khi thay đổi. Các quyền phụ thuộc phải được giới hạn theo nhu cầu và ghi nhận trong thiết kế.

Khi thiếu quyền, nên xác định bước thất bại và nguyên nhân. Việc cấp `*` để vượt lỗi có thể mở thêm cả những khả năng không liên quan, bao gồm quản trị danh tính và bằng chứng.

### 6.3. Thay đổi cấu hình và mã có thể dẫn tới thực thi đặc quyền

Quyền sửa script, pipeline hoặc mã ứng dụng có thể cho phép tác động bằng danh tính của thành phần sẽ chạy mã đó. Vì vậy, action “cập nhật cấu hình” hoặc “triển khai” cần được đánh giá theo mức ảnh hưởng thực tế.

Tương tự, quyền đọc credential có thể dẫn tới action của tài khoản sở hữu credential. Permission theo action phải xem các đường này, thay vì chỉ giới hạn API mà người dùng gọi trực tiếp.

### 6.4. Gọi tác vụ qua một dịch vụ trung gian

Một dịch vụ có thể chạy với danh tính mạnh hơn người yêu cầu. Trước khi dùng quyền của mình để xử lý, dịch vụ cần kiểm tra người yêu cầu được phép gọi action trên tài nguyên đó.

Hệ thống cũng phải ràng buộc yêu cầu đã được duyệt với đúng tài nguyên và tham số khi thực hiện. Nếu kiểm tra một tài nguyên nhưng sau đó thực thi trên đích do người gọi thay đổi, ranh giới quyền có thể bị phá vỡ.

Bằng chứng nên giữ cả danh tính người yêu cầu và danh tính thực thi. Chỉ ghi tên tài khoản dịch vụ sẽ làm mất thông tin ai đã khởi tạo tác vụ đặc quyền.

## 7. Thực thi permission tại nơi có thể chặn hành động

### 7.1. Kiểm tra trước khi tạo tác động

Điểm xử lý yêu cầu cần xác định danh tính, action, tài nguyên và điều kiện trước khi thực hiện hành vi được bảo vệ. Việc ghi nhận một yêu cầu đã bị từ chối không có giá trị ngăn chặn nếu thay đổi đã được thực hiện trước đó.

Một luồng khái niệm:

```text
Nhận yêu cầu và xác minh danh tính.
Xác định action chuẩn từ thao tác được hỗ trợ.
Đối chiếu tài nguyên và kiểm tra tham số.
Đánh giá quyền hiệu lực cùng điều kiện.
Nếu không được cho phép: từ chối và ghi lý do phù hợp.
Nếu được cho phép: thực hiện đúng thao tác đã kiểm tra.
Ghi kết quả, danh tính yêu cầu và danh tính thực thi.
```

Đây là mô tả hành vi, không phải mã triển khai. Trong hệ thống thực tế, việc kiểm tra và thao tác cần được thiết kế để tránh thay đổi đối tượng hoặc điều kiện giữa hai bước theo cách vượt quyền.

### 7.2. Mặc định từ chối và action không được nhận diện

Một đường xử lý chưa có ánh xạ action rõ ràng không nên được mặc nhiên cho phép chỉ vì người dùng đã đăng nhập. Action mới, endpoint mới và phiên bản API mới cần đi qua quy trình thiết kế quyền.

Mặc định từ chối phải được cấu hình và kiểm chứng trong cơ chế thực thi. Việc không liệt kê một action trong tài liệu không bảo đảm nền tảng sẽ chặn nó, nhất là khi danh tính còn quyền từ nguồn khác.

### 7.3. Nhiều giao diện phải dùng cùng ranh giới

Console, CLI, SDK và tác vụ tự động có thể dẫn tới cùng hành vi. Các đường đó cần tuân theo phân quyền phù hợp, kể cả khi giao diện người dùng đã ẩn thao tác.

Với máy chủ, proxy hoặc agent PAM có thể kiểm soát một phần luồng quản trị. Hệ điều hành hoặc ứng dụng vẫn cần thực thi giới hạn tại đích. Nếu người dùng có credential cho đường kết nối trực tiếp, phải kiểm soát cả đường đó.

### 7.4. Bằng chứng không thay cho kiểm soát ngăn chặn

Log và bản ghi phiên giúp hiểu ai làm gì. Chúng không tự giới hạn action nếu tài khoản phía sau có toàn quyền và không có lớp thực thi bổ sung.

Một action được ghi rõ trong ticket cũng không tự hạn chế shell quản trị. Cần chứng minh nơi nào ngăn hành động ngoài ticket hoặc ghi rõ phần quyền rộng còn tồn tại.

## 8. Ví dụ xuyên suốt: vận hành dịch vụ thanh toán

### 8.1. Nhiệm vụ

Kỹ sư Lan xử lý sự cố của `payment-api` trên `prod-app-03`, gắn với ticket `INC-6284`. Lan cần xem trạng thái, đọc phần log phục vụ chẩn đoán và khởi động lại đúng dịch vụ nếu cần.

Nhóm vận hành trước đây có quyền quản trị toàn máy. Thiết kế mới phân rã nhiệm vụ thành ba action với phạm vi rõ ràng.

| Action | Tài nguyên và dữ liệu | Điều kiện minh họa |
| --- | --- | --- |
| `service.readStatus` | Trạng thái của `payment-api` trên `prod-app-03` | Danh tính đúng nhóm nhiệm vụ |
| `service.readOperationalLogs` | Phần log được phép của cùng dịch vụ | Giới hạn nội dung và khoảng thời gian |
| `service.restart` | Đúng dịch vụ trên đúng máy | Kích hoạt theo ticket trong thời hạn cho phép |

Lan không được nhận thêm quyền quản lý danh tính, đọc mọi secret hoặc đổi chính sách lưu bằng chứng chỉ vì tham gia xử lý sự cố.

### 8.2. Mô hình permission

Đoạn JSON sau mô tả ý định chính sách. Đây là **mô hình minh họa**, không phải cấu hình tương thích trực tiếp với một sản phẩm PAM hoặc hệ điều hành. Tên trường và action phải được ánh xạ sang cơ chế thực thi thực tế.

```json
{
  "permissionId": "payment-incident-operations",
  "subject": "admin-lan",
  "resource": {
    "environment": "production",
    "host": "prod-app-03",
    "service": "payment-api"
  },
  "allowedActions": [
    "service.readStatus",
    "service.readOperationalLogs",
    "service.restart"
  ],
  "constraints": {
    "requireActiveTicket": "INC-6284",
    "requireStrongAuthentication": true,
    "requireApprovedAdminDevice": true,
    "maxLogWindowMinutes": 30
  },
  "activation": {
    "mode": "justInTime",
    "maxDurationMinutes": 20
  },
  "evidence": [
    "request",
    "decision",
    "target",
    "actionResult",
    "revocationResult"
  ]
}
```

Các thời lượng 20 và 30 phút chỉ là giả định của ví dụ. Thời lượng kích hoạt và phạm vi đọc log cần được chọn theo nhiệm vụ và chính sách của tổ chức.

Danh sách action trong mô hình không tự xóa quyền Lan có qua nhóm khác. Trước khi coi thiết kế đã giới hạn đủ, cần xử lý quyền quản trị toàn máy cũ và các đường truy cập thay thế.

### 8.3. Cách thực hiện action cần được giới hạn

Nếu action khởi động lại được triển khai bằng một tác vụ đặc quyền, hệ thống cần:

- Cố định hoặc kiểm tra chặt tài nguyên đích.
- Không nhận chương trình, đường dẫn hoặc lệnh tùy ý từ người gọi.
- Bảo vệ mã và cấu hình của tác vụ khỏi bị người gọi thay đổi ngoài thẩm quyền.
- Dùng danh tính thực thi với quyền phù hợp cơ chế.
- Ghi được người khởi tạo, tài khoản thực thi và kết quả.

Nếu công nghệ hiện tại chỉ mở được shell quản trị toàn máy, ba tên action trong JSON chưa tạo ra ranh giới hành động. Có thể cần một endpoint quản trị giới hạn hoặc một cơ chế khác tại đích.

### 8.4. Kết thúc và thay đổi nhiệm vụ

Khi ticket kết thúc hoặc quyền hết hạn, hệ thống chặn khả năng cấp mới và xử lý phiên hoặc token theo thiết kế. Cần xác nhận kết quả tại điểm thực thi.

Nếu Lan phát hiện cần sửa cấu hình, action đó phải được xem xét theo yêu cầu tương ứng. Không âm thầm mở rộng `service.restart` thành quyền sửa mọi cấu hình vì cùng nằm trong một sự cố.

## 9. JIT, JEA, vault và phiên đặc quyền

### 9.1. JIT giới hạn thời gian action khả dụng

Just-in-Time access cho phép kích hoạt tập permission khi có nhiệm vụ. Cần xác định thời điểm bắt đầu, hết hạn, gia hạn và điều kiện kết thúc sớm.

Giảm thời gian không làm action rộng trở thành action hẹp. Một quyền `system.manage` trong mười phút vẫn có thể gây tác động lớn.

### 9.2. JEA giới hạn khả năng quản trị

Just Enough Administration hướng tới việc chỉ cho thực hiện những tác vụ quản trị đủ dùng. Trong thiết kế theo action, JEA cần có ánh xạ từ tác vụ sang hành vi mà hệ thống đích thực thi được.

Việc giới hạn cần bao gồm tham số và phụ thuộc, không chỉ danh sách tên lệnh. Một tác vụ gọi script bất biến với đầu vào được kiểm soát có tính chất khác một tác vụ cho người gọi thay script.

### 9.3. Vault bảo vệ credential được dùng để thực hiện

Vault quản lý bí mật và quyền sử dụng chúng. Môi giới truy cập có thể giảm việc người dùng nhìn thấy credential, tùy cách triển khai.

Tuy nhiên, credential của tài khoản toàn quyền vẫn có sức mạnh toàn quyền khi được sử dụng. Nếu người dùng được lấy credential và đăng nhập trực tiếp, ranh giới action tại cổng PAM có thể bị bỏ qua.

Cần giới hạn ai được đọc secret, phân biệt quyền sử dụng qua luồng với quyền xem giá trị, và xử lý credential đã lộ theo chính sách.

### 9.4. Thu hồi phải tính đến các trạng thái đã phát hành

Gỡ permission ở nguồn không luôn vô hiệu hóa ngay token, phiên hoặc tiến trình đã tồn tại. Tùy nền tảng, cần kết thúc phiên, thu hồi token, đổi credential hoặc áp dụng giới hạn tại điểm thực thi.

Nếu một loại token chỉ mất hiệu lực khi hết hạn, phải biết khoảng thời gian còn lại. Trạng thái “đã thu hồi” phải diễn đạt đúng phần đã hoàn tất và phần chưa thể xác nhận.

## 10. Workload, tác vụ bất đồng bộ và yêu cầu theo lô

### 10.1. Danh tính workload

Pipeline và dịch vụ cần action theo nhiệm vụ riêng. Một pipeline triển khai ứng dụng không mặc nhiên cần quyền đọc mọi secret hoặc quản lý toàn bộ danh tính.

Quyền sửa pipeline, nguồn triển khai và cấu hình runtime cần được xét cùng action được cấp. Người không có quyền triển khai trực tiếp vẫn có thể điều khiển tác vụ nếu được thay nguồn mà pipeline sẽ chạy.

Với workload, cơ chế danh tính và credential phải phù hợp tự động hóa. Không nên yêu cầu người dùng nhập MFA cho từng lần máy gọi API; điều kiện phát hành quyền phải xác minh được đúng workload và phạm vi hoạt động.

### 10.2. Tác vụ xếp hàng

Một yêu cầu được chấp thuận khi đưa vào hàng đợi có thể được thực hiện sau khi quyền hết hạn hoặc tài nguyên đổi trạng thái. Thiết kế cần xác định có đánh giá lại tại lúc thực hiện không và điều kiện nào còn phải hợp lệ.

Hệ thống phải giữ được người khởi tạo, action, tài nguyên, tham số đã được duyệt và danh tính thực thi. Không nên để worker tự mở rộng phạm vi chỉ vì nó chạy bằng tài khoản mạnh hơn.

Tác vụ dài hạn cần chính sách cho việc hủy, tiếp tục hoặc chuyển giao khi quyền kết thúc. Hủy đột ngột có thể gây trạng thái dở dang; tiếp tục không kiểm soát cũng có thể tạo rủi ro. Quyết định cần gắn với loại tác vụ và được mô tả trước.

### 10.3. Yêu cầu tác động nhiều tài nguyên

Một action theo lô cần kiểm tra quyền đối với từng tài nguyên liên quan. Quyền trên một phần danh sách không tự tạo quyền trên toàn bộ danh sách.

Cần quy định rõ hệ thống từ chối cả yêu cầu hay chỉ xử lý các phần được phép. Kết quả, bằng chứng và cách xử lý lỗi phải phù hợp, tránh tạo thay đổi từng phần ngoài dự kiến hoặc tiết lộ thông tin tài nguyên ngoài thẩm quyền.

### 10.4. Thực hiện lại và tác dụng lặp

Một yêu cầu có thể được gửi lại do mất kết nối hoặc cơ chế thử lại. Quyền cho phép gọi action không tự bảo đảm việc lặp lại an toàn.

Với tác vụ nhạy cảm, cần xem xét cách nhận diện lần thực hiện, trạng thái công việc và điều kiện trước thay đổi. Cơ chế phân quyền và cơ chế kiểm soát tác dụng lặp giải quyết những vấn đề liên quan nhưng khác nhau.

## 11. Quản lý wildcard và thay đổi danh mục action

### 11.1. Wildcard mở rộng phạm vi theo thời gian

Một mẫu như `service.*` có thể bao gồm các action hiện tại và có thể bao gồm action được thêm sau này, tùy cách nền tảng xử lý mẫu.

Nếu sau này danh mục có thêm `service.changeIdentity`, một permission cũ dùng wildcard có thể nhận thêm khả năng mà người duyệt ban đầu chưa đánh giá. Cần xác định chính xác hành vi của nền tảng và quản lý thay đổi tương ứng.

Dùng danh sách action rõ ràng giúp người duyệt nhìn thấy phạm vi, nhưng vẫn cần rà soát khi ý nghĩa của một action thay đổi.

### 11.2. Thay đổi ngữ nghĩa cũng là thay đổi quyền

Giữ nguyên tên action nhưng bổ sung khả năng như đọc dữ liệu nhạy cảm, gọi tác vụ mới hoặc thay nhiều tài nguyên hơn có thể làm mở rộng đặc quyền.

Chủ sở hữu cần đánh giá tác động của thay đổi tới người đang có quyền, bằng chứng và các kiểm soát phụ thuộc. Có thể cần action hoặc phiên bản chính sách mới thay vì âm thầm mở rộng hành vi.

### 11.3. Quản lý quyền phụ thuộc và action ngừng dùng

Khi một công cụ hoặc API thay đổi, các quyền phụ thuộc có thể thay đổi theo. Cần cập nhật ánh xạ nhiệm vụ, kiểm chứng luồng hợp lệ và loại bỏ permission không còn cần.

Một endpoint cũ còn hoạt động nhưng không nằm trong bản đồ quyền hiện tại là khoảng trống cần xử lý. Danh mục action phải phản ánh các đường thực thi đang tồn tại.

## 12. Kiểm chứng permission theo action

Phần này mô tả tiêu chí kiểm chứng cho hệ thống thực tế, không yêu cầu chạy lệnh từ bài học.

| Tình huống | Kết quả cần xác nhận |
| --- | --- |
| Đúng danh tính, action, tài nguyên và điều kiện | Tác vụ hợp lệ thực hiện được và có bằng chứng |
| Đúng action nhưng khác tài nguyên | Bị chặn tại điểm thực thi phù hợp |
| Đúng tài nguyên nhưng action ngoài tập được cấp | Bị chặn, không tạo tác động trái phép |
| Thay tham số sang dịch vụ hoặc đường dẫn khác | Không vượt được giới hạn đã duyệt |
| Gọi cùng hành vi qua CLI, API hoặc giao diện khác | Cùng tuân theo ranh giới permission |
| Có quyền rộng từ nhóm hoặc vai trò khác | Quyền hiệu lực được nhận diện và xử lý |
| Action không được nhận diện | Không được cho phép mặc nhiên |
| Yêu cầu theo lô có tài nguyên ngoài phạm vi | Hành vi từ chối hoặc xử lý từng phần đúng thiết kế |
| Quyền hết hạn trước lúc tác vụ xếp hàng chạy | Được xử lý theo chính sách vòng đời đã xác định |
| Gỡ quyền khi phiên hoặc token còn sống | Hiệu lực thu hồi và giới hạn còn lại được ghi nhận |
| Người gọi sửa được thành phần thực thi | Đường tác động được ngăn hoặc ghi rõ là khoảng trống |
| Thêm action mới vào danh mục | Không mở rộng quyền ngoài dự kiến của chính sách |

Chỉ thấy tác vụ hợp lệ thành công chưa chứng minh ranh giới quyền hoạt động. Chỉ thấy nhiều yêu cầu bị chặn cũng chưa chứng minh hệ thống đáp ứng được công việc. Cần xác nhận cả hai phía.

Khi điểm thực thi không phản hồi, phải phân biệt đã gửi yêu cầu với đã xác nhận kết quả. Đặc biệt với thu hồi hoặc thay đổi nhạy cảm, việc báo thành công giả sẽ làm sai trạng thái quản lý.

## 13. Bằng chứng và quản trị vòng đời permission

### 13.1. Hồ sơ permission

Một permission nên có chủ sở hữu, mục đích, danh tính hoặc nhóm được nhận, action, phạm vi tài nguyên, điều kiện, thời hạn và cách rà soát. Với ngoại lệ, ghi rõ lý do và người chịu trách nhiệm.

Khi người dùng đổi nhiệm vụ, khi workload được thay thế hoặc khi tài nguyên bị loại bỏ, cần rà soát permission liên quan. Quyền có thể tích lũy qua các nhóm và vai trò dù từng lần cấp ban đầu đều hợp lệ.

Không dùng việc “chưa thấy action được gọi” làm bằng chứng duy nhất để thu hồi. Nhiệm vụ khôi phục hoặc tác vụ định kỳ hiếm gặp cần được đối chiếu với chủ sở hữu.

### 13.2. Bằng chứng theo từng quyết định

Chuỗi cần nối được là:

**danh tính nguồn → yêu cầu → action và tài nguyên → quyết định → danh tính thực thi → kết quả → kết thúc quyền**.

Dữ liệu hữu ích gồm mã yêu cầu, mã phiên hoặc tác vụ, phiên bản chính sách, thời điểm và lý do từ chối phù hợp. Không ghi secret hoặc dữ liệu nhạy cảm không cần thiết vào log chỉ để lưu toàn bộ tham số.

Quyền sửa chính sách, đọc secret và quản trị bằng chứng cần được phân định. Một người tự mở rộng action rồi xóa log có thể làm mất nhiều lớp kiểm soát.

### 13.3. Chỉ số theo dõi

| Chỉ số | Câu hỏi hỗ trợ trả lời |
| --- | --- |
| Permission dùng wildcard hoặc phạm vi tài nguyên quá rộng | Đâu là nơi dễ mở rộng quyền ngoài dự kiến? |
| Action chưa có chủ sở hữu hoặc mô tả tác động | Danh mục còn thiếu trách nhiệm ở đâu? |
| Endpoint hoặc tác vụ chưa ánh xạ được action | Có đường thực thi chưa được quản lý không? |
| Quyền thường trực cho action nhạy cảm | Cần xem xét JIT hoặc thu hẹp ở đâu? |
| Tác vụ hợp lệ bị chặn và số lần mở rộng quyền | Thiết kế có thiếu quyền phụ thuộc hoặc sai phạm vi không? |
| Phiên và token còn hiệu lực sau thu hồi | Giới hạn kết thúc quyền còn ở đâu? |
| Sự kiện không nối được người yêu cầu với người thực thi | Bằng chứng quy trách nhiệm còn khoảng trống nào? |

Số lượng action ít không tự chứng minh least privilege: một action rất rộng có thể nguy hiểm hơn một tập action hẹp. Chỉ số cần phản ánh phạm vi và khả năng tác động thực tế.

## 14. Sai lầm thường gặp

| Cách làm | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Kiểm tra người dùng có phải admin không | Không phân biệt nhiệm vụ, tài nguyên và mức tác động | Kiểm tra permission cho yêu cầu cụ thể |
| Chỉ kiểm tra tên action | Tham số hoặc tài nguyên có thể mở rộng phạm vi | Ràng buộc action, tài nguyên và đầu vào |
| Cấp wildcard để sửa lỗi thiếu quyền | Có thể mở thêm hành động không liên quan | Xác định quyền phụ thuộc tối thiểu |
| Cho phép tên câu lệnh với mọi tham số | Có thể tạo hành vi vượt action nghiệp vụ | Công cụ hoặc endpoint có đầu vào được kiểm soát |
| Bảo vệ giao diện nhưng để API khác bỏ qua | Cùng hành vi vẫn thực hiện được qua đường thay thế | Thực thi phân quyền trên mọi đường xử lý |
| Ghi ticket là đủ để cấp shell toàn quyền | Mục đích được ghi nhưng quyền thực tế vẫn rộng | Giới hạn tác vụ hoặc mô tả ngoại lệ có kiểm soát |
| Thu hồi vai trò rồi bỏ qua phiên đã phát hành | Action có thể vẫn được thực hiện trong phiên cũ | Xử lý và xác nhận vòng đời tại đích |
| Đổi hành vi action mà không rà soát người có quyền | Permission cũ có thể mạnh hơn quyết định ban đầu | Quản lý thay đổi danh mục và chính sách |
| Chỉ ghi danh tính dịch vụ trung gian | Không biết ai khởi tạo thao tác | Liên kết danh tính yêu cầu và thực thi |

## 15. Thực hành thiết kế một tập permission

Chọn nhiệm vụ “xử lý sự cố của một ứng dụng production” và phân rã thành xem trạng thái, đọc log, khởi động lại dịch vụ và thay một cấu hình được duyệt.

Với từng action, hãy ghi:

1. Hành vi và tác động thực tế.
2. Tài nguyên và dữ liệu được phép tiếp cận.
3. Tham số được nhận và giới hạn.
4. Quyền phụ thuộc và đường tác động gián tiếp.
5. Điều kiện cấp, thời hạn và cách gia hạn.
6. Điểm thực thi và đường truy cập thay thế.
7. Cách kết thúc quyền, phiên hoặc tác vụ.
8. Bằng chứng cho phép và từ chối.

Sau đó kiểm tra ba trường hợp: người dùng chuyển sang tài nguyên khác, một action mới được thêm vào danh mục, và quyền hết hạn khi tác vụ còn đang chờ.

Nếu chưa biết nơi nào thực thi giới hạn hoặc token nào còn hiệu lực, ghi rõ đó là phần chưa được kiểm chứng. Một danh sách tên action chỉ trở thành kiểm soát khi được kết nối với hành vi thực tế.

## 16. Ghi nhớ

Permission theo action chuyển đặc quyền từ nhãn quản trị chung thành khả năng thực hiện việc cụ thể. Ranh giới đầy đủ gồm danh tính, action, tài nguyên, tham số và điều kiện.

Trong PAM, JIT giới hạn thời gian, JEA thu hẹp tác vụ, vault quản lý credential và bằng chứng hỗ trợ quy trách nhiệm. Hiệu quả phụ thuộc vào quyền thực tế tại đích, các đường tác động gián tiếp, việc quản lý thay đổi action và khả năng kết thúc truy cập.
