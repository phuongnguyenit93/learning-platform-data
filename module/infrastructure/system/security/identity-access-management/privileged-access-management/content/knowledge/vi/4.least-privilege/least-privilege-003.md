# Tách quyền cấu hình và vận hành

## Mục tiêu bài học

Trong chương **Least privilege**, tách quyền cấu hình và vận hành là thiết kế các tập quyền để **thay đổi cách hệ thống hoạt động** và **thực hiện những tác vụ đã được cho phép trên hệ thống** không mặc nhiên nằm trong cùng một quyền quản trị tổng quát.

Trong phạm vi **Privileged Access Management (PAM)**, việc phân tách này áp dụng cho tài khoản quản trị, dịch vụ và các thành phần hạ tầng nhạy cảm. Cần kiểm soát quyền thực tế, đường sử dụng, credential, thời gian cấp quyền và bằng chứng, thay vì chỉ tạo hai role có tên khác nhau.

Sau bài học, bạn có thể:

- Phân biệt quyền cấu hình và quyền vận hành theo khả năng thực tế.
- Nhận diện những đường biến quyền vận hành thành quyền sửa cấu hình hoặc thực thi tùy ý.
- Thiết kế role, luồng thay đổi và tác vụ tự động theo least privilege.
- Kết hợp JIT/JEA, vault, luân chuyển credential và giám sát phiên.
- Xác định bằng chứng để kiểm toán, điều tra và xử lý thay đổi ngoài quy trình.

## 1. Hai loại quyền khác nhau ở điểm nào?

### Quyền cấu hình

Quyền cấu hình cho phép thay đổi các quy tắc, tham số hoặc thành phần quyết định hành vi hệ thống.

Ví dụ:

- Sửa định nghĩa dịch vụ, chương trình được chạy hoặc tham số khởi động.
- Thay chính sách IAM, ACL hoặc quan hệ tin cậy.
- Sửa cấu hình mạng, nơi ghi log và chính sách sao lưu.
- Thay cấu trúc triển khai, workflow hoặc mã quản trị.
- Chọn bí mật, danh tính hoặc khóa mà một workload được sử dụng.

### Quyền vận hành

Quyền vận hành cho phép thực hiện các tác vụ trong một khuôn khổ đã được xác định.

Ví dụ:

- Xem trạng thái của dịch vụ được giao.
- Khởi động lại một dịch vụ theo điều kiện cho phép.
- Chạy một tác vụ bảo trì đã được kiểm soát.
- Kích hoạt một job sao lưu với phạm vi xác định.
- Theo dõi và xác nhận kết quả triển khai.

Ranh giới này phụ thuộc kiến trúc và nhiệm vụ. Một nút “chạy lại job” có thể là thao tác vận hành hẹp nếu chỉ chạy định nghĩa cố định; cũng có thể tương đương quyền cấu hình nếu người gọi được thay chương trình, danh tính hoặc đích thực thi.

Vì vậy:

> Phân loại quyền theo những gì chủ thể có thể làm thay đổi, không chỉ theo tên nút, lệnh, API hoặc chức danh người sử dụng.

## 2. Vì sao cần phân tách?

### 2.1. Giảm phạm vi tác động của tài khoản vận hành

Người trực vận hành có thể cần quan sát và xử lý một số sự cố thường xuyên, nhưng không nhất thiết cần sửa chính sách bảo mật hoặc thay mã chạy dưới quyền cao.

Nếu cùng một tài khoản có mọi khả năng, một sai sót hoặc một lần bị chiếm quyền có thể tác động cả trạng thái dịch vụ lẫn những cơ chế quyết định dịch vụ được phép làm gì.

### 2.2. Giữ thay đổi có thể được xem xét và truy vết

Cấu hình thay đổi qua một luồng có phiên bản giúp đối chiếu ý định, quyết định chấp nhận và trạng thái thực tế.

Ngược lại, nếu mọi người có thể sửa trực tiếp production bằng cùng credential dùng cho vận hành, cấu hình thực tế có thể khác cấu hình đã được xem xét mà không có bằng chứng rõ ràng.

### 2.3. Hạn chế khả năng tự mở rộng quyền

Một người được phép vận hành công cụ nhưng cũng sửa được chính sách hoặc mã của công cụ đó có thể làm mất giới hạn ban đầu.

Ví dụ, giao diện cho phép “khởi động lại dịch vụ A” không còn là ranh giới hẹp nếu người dùng có thể sửa định nghĩa dịch vụ A để nó thực hiện bất kỳ chương trình nào.

### 2.4. Hỗ trợ ứng phó và phục hồi

Khi biết cấu hình nào được chấp nhận và ai đã thực hiện thao tác nào, đội ứng phó có cơ sở để:

- Phân biệt thay đổi dự kiến với thay đổi ngoài quy trình.
- Khoanh vùng quyền và credential liên quan.
- Chọn trạng thái khôi phục.
- Xác nhận đã xử lý đường thay đổi trái phép.

Tách quyền không bảo đảm cấu hình được chấp nhận luôn đúng. Nội dung thay đổi vẫn cần được đánh giá tương xứng với mức tác động.

## 3. Phân tách khả năng, không mặc định chia tổ chức thành hai đội

Một đội có thể vừa phát triển cấu hình vừa chịu trách nhiệm vận hành. Tách quyền không bắt buộc mọi công việc phải chuyển qua hai phòng ban độc lập.

Cần phân biệt ba lớp:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Phân tách tập quyền | Hệ thống cho phép những khả năng nào? | Role vận hành không được sửa định nghĩa dịch vụ |
| Phân tách điều kiện sử dụng | Khi nào và trong ngữ cảnh nào được dùng quyền? | Quyền cấu hình chỉ được kích hoạt cho một thay đổi có thời hạn |
| Phân tách trách nhiệm quyết định | Ai được đề xuất, chấp nhận và thực hiện? | Một số thay đổi nhạy cảm cần người khác xem xét theo chính sách |

Hai tài khoản của cùng một người có thể giúp tách ngữ cảnh, nhưng không tự tạo ra sự xem xét độc lập. Nếu chính sách yêu cầu người phê duyệt khác người đề xuất, việc đổi tài khoản không đáp ứng yêu cầu đó.

Ngược lại, có hai đội khác nhau cũng chưa chắc tạo tách biệt thực tế nếu họ cùng dùng một tài khoản quản trị và có thể sửa mọi chính sách.

## 4. Lập bản đồ hành động trước khi thiết kế role

Không nên bắt đầu bằng hai role rất rộng có tên “Config Admin” và “Operator”. Trước hết cần liệt kê hành động, tài nguyên, tham số và hậu quả.

| Hành động | Phân loại ban đầu | Điều cần làm rõ |
| --- | --- | --- |
| Xem trạng thái dịch vụ A | Vận hành | Kết quả có làm lộ bí mật hoặc dữ liệu nhạy cảm không? |
| Khởi động lại dịch vụ A | Vận hành có tác động | Có sửa được chương trình, tham số hoặc danh tính thực thi không? |
| Sửa biến môi trường dịch vụ | Cấu hình | Có thay credential, đích kết nối hoặc hành vi bảo mật không? |
| Thay số bản sao dịch vụ | Thay đổi cấu hình hoặc vận hành theo thiết kế | Phạm vi, giới hạn và tác động chi phí, sẵn sàng là gì? |
| Chạy job bảo trì cố định | Vận hành | Có chọn được đối tượng ngoài phạm vi hoặc truyền nội dung tùy ý không? |
| Thay định nghĩa job | Cấu hình | Ai xem xét và danh tính nào sẽ thực thi định nghĩa mới? |
| Phục hồi bản sao lưu | Thao tác nhạy cảm cần kiểm soát riêng | Có ghi đè dữ liệu hoặc tạo bản sao ở nơi ít được bảo vệ không? |
| Sửa chính sách audit | Cấu hình bảo mật | Có làm mất khả năng quan sát hoặc sửa bằng chứng không? |
| Cấp quyền cho người khác | Quản trị quyền | Có thể tự mở rộng phạm vi hoặc vượt tách biệt nhiệm vụ không? |

Không phải mọi thao tác vận hành đều có rủi ro thấp. Kết thúc phiên, chuyển đổi dự phòng, phục hồi hoặc khởi động lại hàng loạt có thể tác động lớn tới nghiệp vụ.

Một số thao tác có thể được giới hạn bằng phạm vi và điều kiện thay vì bắt buộc quy trình giống mọi thay đổi cấu hình. Cách xử lý cần dựa trên khả năng và mức tác động thực tế.

## 5. Những đường làm mất ranh giới phân quyền

### 5.1. Được vận hành nhưng cũng sửa được nội dung sẽ chạy

Một người có thể chỉ được phép khởi động dịch vụ, nhưng lại có quyền ghi vào:

- File chương trình hoặc script của dịch vụ.
- File cấu hình quyết định chương trình và tham số.
- Thư mục cho phép thay thế thành phần được dịch vụ sử dụng.
- Artifact hoặc kho mã mà hệ thống sẽ lấy khi khởi động.

Khi đó, thao tác khởi động có thể kích hoạt nội dung do chính người đó thay đổi. Cần kiểm tra quyền sửa ở toàn bộ đường dẫn liên quan, không chỉ quyền trên một file dễ nhìn thấy.

### 5.2. Tham số vận hành quá linh hoạt

Một API “chạy job” có thể nhận tên tài nguyên, đường dẫn, câu lệnh hoặc danh tính thực thi do người gọi cung cấp.

Nếu không giới hạn đúng tham số, API có thể trở thành giao diện cấu hình hoặc thực thi tùy ý. Cần thiết kế tập hành động và tập giá trị được chấp nhận theo nhiệm vụ, không dựa vào một nhãn “bảo trì”.

### 5.3. Sửa được cơ chế kiểm soát

Ranh giới suy yếu nếu người dùng có thể:

- Tự sửa role hoặc thêm mình vào nhóm mạnh hơn.
- Thay chính sách phê duyệt.
- Sửa mã của công cụ quản trị có quyền cao.
- Thay principal mà pipeline sử dụng.
- Sửa điều kiện cấp credential từ vault.
- Tắt audit hoặc chuyển log sang nơi họ toàn quyền kiểm soát.

Các khả năng này phải được kiểm kê như đường đặc quyền gián tiếp.

### 5.4. Có đường quản trị tổng quát đi ngoài luồng

Một giao diện vận hành hẹp không đủ nếu cùng người dùng vẫn có credential để mở shell quản trị, gọi API rộng hoặc kết nối trực tiếp bằng tài khoản mạnh.

Cần kiểm soát các đường truy cập tương đương và quản lý ngoại lệ. Chỉ ẩn nút sửa cấu hình trên giao diện không phải cơ chế phân quyền đầy đủ.

### 5.5. Bản sao cấu hình chứa bí mật

Quyền đọc cấu hình có thể đồng thời cho phép đọc credential. Nếu credential đó có quyền sửa hệ thống, quyền “chỉ đọc” có thể mở một đường quản trị khác.

Cần tách giá trị bí mật khỏi phần cấu hình không nhạy cảm khi phù hợp, giới hạn quyền lấy bí mật và đánh giá quyền của credential được tham chiếu.

## 6. Một mô hình phân tách khả năng

Xét dịch vụ ứng dụng A trên production. Có thể thiết kế các vai trò theo ý định sau:

| Vai trò | Khả năng dự kiến | Giới hạn cần thực thi |
| --- | --- | --- |
| Người đề xuất cấu hình | Soạn thay đổi ở nơi quản lý phiên bản | Không tự sửa trực tiếp production hoặc bỏ qua điều kiện chấp nhận |
| Người xem xét phù hợp | Đánh giá thay đổi theo thẩm quyền | Không coi một thao tác phê duyệt là thay thế cho kiểm tra nội dung |
| Danh tính áp dụng cấu hình | Đưa phiên bản được chấp nhận lên đúng tài nguyên | Không được lấy nội dung hoặc đích tùy ý từ người gọi không được tin cậy |
| Người vận hành | Xem trạng thái, thực hiện tập tác vụ cho phép | Không sửa định nghĩa, chương trình, danh tính hoặc quyền |
| Người quản lý bảo mật | Quản lý những chính sách được giao | Kiểm soát khả năng tự cấp quyền và ảnh hưởng audit |
| Người xem bằng chứng | Đối chiếu yêu cầu, thay đổi và hành động | Giới hạn quyền đọc dữ liệu nhạy cảm và quyền sửa bằng chứng |

Đây là mô hình tham khảo, không phải yêu cầu mọi hệ thống phải có đúng sáu role.

Một người có thể được giao nhiều trách nhiệm nếu chính sách cho phép. Tuy nhiên, phải chỉ rõ khi nào cần kích hoạt từng quyền và trường hợp nào cần quyết định độc lập.

### Danh tính áp dụng cấu hình cũng là danh tính đặc quyền

Tách người sửa cấu hình khỏi production thường dẫn đến việc pipeline hoặc dịch vụ tự động có quyền áp dụng thay đổi. Quyền không biến mất; nó được chuyển sang một chủ thể cần quản lý.

Cần bảo vệ:

- Mã và cấu hình của pipeline.
- Nguồn artifact hoặc phiên bản được phép sử dụng.
- Điều kiện được nhận credential.
- Danh sách tài nguyên đích.
- Khả năng sửa bước kiểm tra và phê duyệt.
- Runtime thực thi và các bên có thể chạy mã trong đó.

Nếu người dùng sửa được pipeline để bỏ qua mọi kiểm soát, việc không cấp credential production trực tiếp cho họ chưa tạo ranh giới đầy đủ.

## 7. Ví dụ xuyên suốt: cấu hình và khởi động lại dịch vụ A

### Thiết kế ban đầu

Nhóm trực vận hành dùng một tài khoản quản trị chung để:

- Xem trạng thái.
- Sửa cấu hình.
- Thay script khởi động.
- Khởi động lại dịch vụ.
- Thay quyền truy cập và nơi ghi log.

Thiết kế này khó giới hạn tác động của một lượt đăng nhập. Nhu cầu khởi động lại dịch vụ kéo theo quyền thay đổi cả cơ chế thực thi và bằng chứng.

### Thiết kế được thu hẹp

Một hướng cải thiện:

1. Mỗi người sử dụng danh tính cá nhân ở luồng yêu cầu.
2. Role vận hành chỉ có các tác vụ được giao trên dịch vụ A.
3. Cấu hình và script được quản lý theo phiên bản, với quyền sửa riêng.
4. Danh tính tự động áp dụng phiên bản được chấp nhận vào production.
5. Người vận hành không được sửa chương trình, file hoặc thư mục quyết định nội dung thực thi.
6. Quyền tác động lớn hơn đi qua một yêu cầu riêng hoặc luồng khẩn cấp phù hợp.
7. Audit liên kết người, tác vụ, phiên và phiên bản cấu hình đang sử dụng.

### Mô tả chính sách ở mức ý định

Ví dụ sau **không phải cấu hình để nạp vào một sản phẩm cụ thể**:

```yaml
operation_access:
  actor: application-a-operator
  target: production/application-a
  allowed_actions:
    - view-approved-status
    - restart-fixed-service-definition

operation_constraints:
  executable_definition: protected
  runtime_identity: fixed-by-approved-configuration
  caller_supplied_command: not-accepted
  target_selection: limited-to-application-a

configuration_access:
  source: version-controlled-configuration
  apply_identity: application-a-config-applier
  accepted_revision: required
  production_write: limited-to-apply-workflow

evidence:
  correlate:
    - access-request-id
    - personal-or-workload-identity
    - operation-session-id
    - applied-configuration-revision
    - action-result
```

Các giá trị trong ví dụ chỉ diễn đạt yêu cầu. Khi triển khai, phải ánh xạ chúng thành quyền và điều kiện mà hệ thống thực sự hỗ trợ, rồi kiểm tra các đường sửa hoặc gọi trực tiếp.

### Những điều vẫn cần kiểm soát

Dù không sửa được cấu hình, người vận hành vẫn có thể gây gián đoạn nếu khởi động lại quá nhiều lần hoặc chọn thời điểm không phù hợp.

Có thể cần giới hạn tần suất, phạm vi, điều kiện vận hành hoặc quy trình cho thao tác hàng loạt. Phân tách quyền cấu hình không làm các hành động vận hành trở nên vô hại.

## 8. Luồng thay đổi cấu hình có kiểm soát

Một luồng khái niệm:

```text
Đề xuất thay đổi
       |
       v
Kiểm tra phạm vi và nội dung
       |
       v
Quyết định chấp nhận theo thẩm quyền
       |
       v
Chọn đúng phiên bản / artifact
       |
       v
Danh tính được phép áp dụng vào đúng tài nguyên
       |
       v
Xác nhận trạng thái thực tế và kết quả vận hành
       |
       v
Giữ bằng chứng, xử lý sai lệch hoặc khôi phục
```

Cần bảo vệ sự liên tục giữa nội dung được xem xét và nội dung thực sự áp dụng. Nếu sau khi được chấp nhận vẫn có thể thay artifact hoặc đổi đích mà không kiểm tra lại, quyết định ban đầu có thể không còn bao phủ thao tác thực tế.

Chữ ký, mã băm hoặc định danh phiên bản có thể hỗ trợ xác định nội dung và nguồn theo cơ chế sử dụng. Chúng không tự chứng minh cấu hình đúng nghiệp vụ hay không gây sự cố.

### Sai lệch giữa cấu hình mong muốn và thực tế

Thay đổi trực tiếp trong sự cố có thể tạo ra cấu hình thực tế khác bản đã quản lý.

Cần:

- Phát hiện sai lệch.
- Xác định thay đổi có được phép hay không.
- Ghi lý do và người thực hiện.
- Đánh giá việc giữ, đưa vào cấu hình chính thức hoặc hoàn tác.
- Tránh đồng bộ mù quáng làm mất một thay đổi khẩn cấp vẫn còn cần thiết.

Quản lý sai lệch là một phần của kiểm soát vòng đời, không chỉ là tìm rồi ghi đè mọi khác biệt.

## 9. JIT/JEA và credential cho từng luồng

### 9.1. JIT: cấp quyền khi có nhiệm vụ

Quyền cấu hình có thể chỉ được kích hoạt trong một đợt thay đổi. Một số quyền vận hành cũng có thể cần cấp theo sự cố thay vì tồn tại thường trực.

Yêu cầu cần nêu:

- Người hoặc workload.
- Tài nguyên và môi trường.
- Hành động, nội dung hoặc phiên bản liên quan.
- Lý do và thời hạn.
- Điều kiện kết thúc và cách xử lý phiên.

Hết hạn ở hệ thống PAM không mặc nhiên đóng mọi phiên hoặc thu hồi mọi token đích. Cần hiểu hành vi của hệ thống thực thi.

### 9.2. JEA: giới hạn tập hành động

JEA giúp chuyển yêu cầu chung “cần quyền quản trị” thành tác vụ đủ hẹp. Ví dụ, chỉ cho thao tác cố định trên dịch vụ A thay vì shell toàn quyền.

Tuy nhiên, phải kiểm tra:

- Ai sửa được định nghĩa tác vụ?
- Tham số có cho phép vượt phạm vi không?
- Tác vụ chạy với danh tính nào?
- Có thể sửa nội dung mà tác vụ sẽ nạp không?
- Có đường sử dụng credential để bỏ qua giao diện tác vụ không?

JEA ở đây là nguyên tắc giới hạn quản trị; cơ chế triển khai phụ thuộc nền tảng.

### 9.3. Vault và luân chuyển

Credential cho vận hành, áp dụng cấu hình và quản trị bảo mật nên được quản lý theo những ranh giới phù hợp. Nếu mọi luồng vẫn dùng cùng một credential toàn quyền, phân tách trên giao diện có thể không được duy trì ở hệ thống đích.

Vault hỗ trợ bảo vệ và phân phối bí mật, nhưng không tự thu hẹp quyền của credential. Cần quản lý:

- Chủ sở hữu và mục đích.
- Bên được lấy hoặc sử dụng credential.
- Phạm vi quyền ở đích.
- Bản sao và bên phụ thuộc.
- Cách luân chuyển, thu hồi và kiểm tra kết quả.

Đổi credential vận hành không xử lý một đường sửa cấu hình trực tiếp vẫn còn mở. Ngược lại, xóa quyền sửa cấu hình không tự thu hồi credential quản trị đã bị sao chép.

## 10. Bằng chứng cho kiểm toán và ứng phó sự cố

Cần phân biệt bằng chứng của **thay đổi cấu hình** và bằng chứng của **thao tác vận hành**, rồi liên kết chúng khi cần.

| Nhóm bằng chứng | Nội dung nên làm rõ |
| --- | --- |
| Yêu cầu quyền | Chủ thể, mục đích, phạm vi, thời gian, quyết định |
| Thay đổi cấu hình | Nội dung hoặc định danh phiên bản, người đề xuất, quyết định chấp nhận |
| Áp dụng | Danh tính thực thi, tài nguyên đích, phiên bản thực tế, thời gian và kết quả |
| Vận hành | Người hoặc workload, tác vụ, tham số an toàn, phiên và kết quả |
| Quyền và credential | Quyền đã cấp, đường cấp credential, sự kiện đổi hoặc thu hồi |
| Sai lệch và ngoại lệ | Thay đổi ngoài luồng, lý do, người chịu trách nhiệm, thời hạn xử lý |
| Bảo vệ bằng chứng | Ai xem, sửa, xóa hoặc thay cấu hình thu thập log |

Ví dụ, sau khi khởi động lại dịch vụ, có thể cần biết dịch vụ dùng phiên bản cấu hình nào. Chỉ biết “người A đã restart” chưa đủ nếu cấu hình đã bị sửa trước đó.

Ngược lại, một thay đổi được chấp nhận chưa chứng minh nó đã được áp dụng đúng đích hoặc vận hành thành công.

### Không biến bằng chứng thành nơi lộ bí mật

Cấu hình, dòng lệnh, biến môi trường và đầu ra tác vụ có thể chứa dữ liệu nhạy cảm. Cần chọn mức chi tiết phù hợp, che giấu khi khả thi và giới hạn người xem.

Không chủ động ghi mật khẩu, token hoặc khóa đầy đủ để hỗ trợ điều tra. Nên dùng định danh tham chiếu và dữ liệu đối chiếu an toàn.

Bản ghi phiên tương tác cũng không nhất thiết bao phủ API hoặc tác vụ tự động. Cần bổ sung audit phù hợp với từng đường thực thi.

## 11. Trường hợp khẩn cấp và đội quy mô nhỏ

### Thay đổi khẩn cấp

Có sự cố cần thay cấu hình nhanh để khôi phục dịch vụ. Một luồng khẩn cấp có thể cho phép quyền mạnh hơn với điều kiện được xác định, thay vì mở quyền vô thời hạn.

Cần làm rõ:

- Ai được kích hoạt và trong trường hợp nào.
- Phạm vi, thời hạn và credential sử dụng.
- Cảnh báo và bằng chứng.
- Cách xử lý phiên và thu hồi sau sử dụng.
- Việc xem xét và đưa cấu hình thực tế về trạng thái được quản lý.

Quy trình khẩn cấp cần khả dụng khi thành phần chính gặp sự cố. Không nên phụ thuộc hoàn toàn vào đúng thành phần đang cần khôi phục mà không có phương án phù hợp.

### Đội ít người

Một người có thể vừa soạn cấu hình vừa trực vận hành. Vẫn có thể giảm rủi ro bằng:

- Role hẹp theo tác vụ.
- Kích hoạt quyền cấu hình khi cần.
- Quản lý phiên bản và bằng chứng.
- Giới hạn đường áp dụng và phạm vi tài nguyên.
- Xem xét độc lập cho thay đổi có mức tác động cần thiết.
- Ghi nhận ngoại lệ có chủ sở hữu và thời hạn.

Nếu không thể đáp ứng mức tách biệt mong muốn, cần mô tả giới hạn và biện pháp bù đắp. Không nên gọi một bước tự phê duyệt bằng tài khoản khác là sự phê duyệt độc lập.

## 12. Triển khai phân tách mà vẫn giữ khả năng vận hành

Một cách tiếp cận có thể gồm:

1. **Kiểm kê hành động thực tế.** Xác định tác vụ thường xuyên, thay đổi cấu hình và thao tác có tác động lớn.
2. **Tìm phụ thuộc và đường gián tiếp.** Bao gồm file, mã, workflow, principal và credential.
3. **Thiết kế tập quyền theo nhiệm vụ.** Nêu rõ tài nguyên, tham số, thời gian và quyền cấp tiếp.
4. **Thiết lập luồng cấu hình.** Bảo vệ nội dung, quyết định chấp nhận, danh tính áp dụng và đích.
5. **Thiết lập luồng vận hành.** Cho phép tập tác vụ cần thiết mà không để sửa chính ranh giới kiểm soát.
6. **Xác nhận các khả năng được phép và bị giới hạn.** Kiểm tra tác vụ hợp lệ vẫn làm được và đường cấu hình không mong muốn đã được xử lý.
7. **Chuyển đổi credential và thu hồi quyền cũ.** Có kế hoạch cho các công cụ, dịch vụ và phiên còn phụ thuộc.
8. **Theo dõi ngoại lệ, sai lệch và nhu cầu mới.** Cập nhật quyền qua quy trình thay vì mở rộng vĩnh viễn sau mỗi sự cố.

Khi xác nhận thiết kế ở hệ thống thực tế, các tình huống hữu ích gồm:

| Tình huống | Kết quả mong đợi theo thiết kế |
| --- | --- |
| Người vận hành xem trạng thái dịch vụ được giao | Thực hiện được trong phạm vi dữ liệu cho phép |
| Người vận hành thực hiện tác vụ cố định | Thực hiện được khi đáp ứng điều kiện |
| Người vận hành sửa định nghĩa hoặc danh tính thực thi | Bị giới hạn nếu nhiệm vụ không cho phép |
| Người vận hành chọn tài nguyên ngoài phạm vi | Bị giới hạn |
| Người dùng sửa pipeline để bỏ qua quyết định chấp nhận | Không có đường ngoài thẩm quyền |
| Hết nhiệm vụ | Quyền, credential và phiên được xử lý theo chính sách |
| Phát hiện thay đổi khẩn cấp | Có bằng chứng, chủ sở hữu và hướng xử lý sai lệch |

Bảng này là hướng dẫn thực hành cho người học, không phải khẳng định mọi hệ thống đều có cùng cơ chế cưỡng chế.

## 13. Tình huống tự đánh giá

Một đội tạo role “Operator” chỉ được gọi tác vụ khởi động lại dịch vụ A. Tuy nhiên:

- Người thuộc role sửa được script khởi động.
- Tác vụ có tham số chọn đường dẫn script.
- Pipeline áp dụng cấu hình dùng credential toàn quyền.
- Cùng người đó sửa được pipeline và chính sách chấp nhận thay đổi.
- Log chỉ ghi “restart thành công”, không có định danh cấu hình.

### Phân tích

**Quyền sửa nội dung thực thi:** người dùng có thể thay đổi hành vi sẽ chạy dù API vận hành có tên hẹp.

**Tham số vượt phạm vi:** chọn đường dẫn tùy ý làm cho tác vụ không còn gắn với định nghĩa cố định.

**Danh tính tự động quá rộng:** credential toàn quyền làm tăng hậu quả nếu pipeline bị sửa hoặc runtime bị chiếm.

**Ranh giới quyết định không được bảo vệ:** người sửa nội dung cũng sửa được cơ chế yêu cầu chấp nhận.

**Bằng chứng thiếu ngữ cảnh:** không biết phiên bản nào đã chạy nên khó đối chiếu giữa ý định và thực tế.

### Hướng cải thiện

- Bảo vệ script, cấu hình và các vị trí có thể thay nội dung thực thi.
- Giới hạn tác vụ vào định nghĩa và tập tham số cần thiết.
- Thu hẹp quyền danh tính áp dụng theo tài nguyên và hành động.
- Bảo vệ workflow, nguồn phiên bản và chính sách chấp nhận.
- Kiểm soát đường quản trị trực tiếp và credential ngoài luồng.
- Liên kết yêu cầu, chủ thể, phiên bản cấu hình, tác vụ và kết quả.
- Có cách xử lý thay đổi khẩn cấp, thu hồi quyền và phục hồi.

Nếu thao tác vận hành thực sự cần sửa cấu hình, nên tạo một nhiệm vụ có phạm vi và điều kiện rõ ràng cho nhu cầu đó, thay vì âm thầm mở mọi quyền của role vận hành.

## 14. Những điểm cần ghi nhớ

- Quyền cấu hình thay đổi cách hệ thống hoạt động; quyền vận hành thực hiện những tác vụ trong khuôn khổ được xác định.
- Phân loại theo khả năng thực tế. Một tác vụ có tham số hoặc nội dung thực thi sửa được có thể trở thành quyền cấu hình gián tiếp.
- Tách role phải đi cùng kiểm soát file, workflow, principal, chính sách và đường truy cập trực tiếp.
- Danh tính tự động áp dụng cấu hình là một danh tính đặc quyền cần least privilege, credential được quản lý và bằng chứng.
- JIT giới hạn thời gian; JEA giới hạn hành động; vault và luân chuyển quản lý phương tiện truy cập.
- Bằng chứng cần liên kết được **ai thay cấu hình gì, ai thực hiện tác vụ nào, trên phiên bản và tài nguyên nào, với quyền gì và kết quả ra sao**.