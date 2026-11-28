# Human privileged identity

## 1. Danh tính đặc quyền của con người là gì?

**Human privileged identity** là danh tính của một con người có khả năng thực hiện các hành động nhạy cảm trên hệ thống, dữ liệu hoặc cơ chế kiểm soát truy cập. Trong ngữ cảnh PAM — Privileged Access Management, danh tính này cần được quản lý sao cho quyền quản trị được cấp đúng người, đúng nhiệm vụ, đúng phạm vi và có thể truy vết, thu hồi.

Một kỹ sư quản trị máy chủ, một quản trị viên cơ sở dữ liệu, một người quản lý hệ thống nhận dạng và một nhân viên hỗ trợ được phép đặt lại yếu tố xác thực đều có thể sử dụng danh tính đặc quyền. Điểm quyết định là **khả năng thực tế được trao**, không phải chức danh, tên tài khoản hay việc tài khoản có chứa từ `admin` hay không.

Ví dụ:

- Một tài khoản tên `operator` được phép sửa chính sách truy cập có thể có đặc quyền rất lớn.
- Một tài khoản chỉ được đọc nhưng có thể xuất toàn bộ dữ liệu khách hàng nhạy cảm vẫn cần kiểm soát tương xứng với mức ảnh hưởng.
- Một kỹ sư không có quyền quản trị production trực tiếp nhưng được sửa pipeline triển khai vào production có thể có đường tác động gián tiếp cần được đánh giá.
- Một tài khoản mang tên `admin-training` chỉ có quyền trong môi trường thực hành biệt lập có phạm vi ảnh hưởng khác với quản trị viên hệ thống nhận dạng của tổ chức.

Do đó, danh sách “người có đặc quyền” không nên chỉ được tạo bằng cách tìm tên tài khoản quản trị. Cần xác định những người có thể thay đổi hệ thống, truy cập dữ liệu nhạy cảm, cấp quyền cho người khác hoặc làm suy yếu khả năng bảo vệ và phục hồi.

## 2. Phân biệt con người, danh tính, tài khoản, quyền và phiên

Các khái niệm này liên quan nhưng không thay thế cho nhau.

| Khái niệm | Ý nghĩa trong bài học | Ví dụ |
|---|---|---|
| Con người | Cá nhân thực hiện hoặc chịu trách nhiệm cho hoạt động | Một kỹ sư thuộc nhóm vận hành |
| Danh tính số | Biểu diễn của người đó trong một miền quản lý danh tính | Danh tính nhân viên trong hệ thống nhận dạng doanh nghiệp |
| Tài khoản hoặc principal | Thực thể mà hệ thống dùng để xác thực, gán quyền hoặc ghi nhận hoạt động | Tài khoản cá nhân, tài khoản quản trị riêng, principal trong nền tảng cloud |
| Role hoặc nhóm | Cơ chế gom và gán tập quyền | Nhóm vận hành ứng dụng, role quản trị cơ sở dữ liệu |
| Quyền hiệu lực | Những hành động thực tế được phép sau khi xét các cơ chế áp dụng | Đọc log của một ứng dụng, khởi động lại dịch vụ, sửa chính sách truy cập |
| Credential hoặc token | Bằng chứng hoặc phương tiện được dùng để xác thực và sử dụng danh tính | Mật khẩu, khóa, token truy cập |
| Phiên đặc quyền | Một ngữ cảnh truy cập có quyền nhạy cảm trong thời gian cụ thể | Phiên quản trị qua PAM hoặc phiên API dùng role được kích hoạt tạm thời |

Một người có thể có nhiều tài khoản trên nhiều hệ thống. Ngược lại, một tài khoản đích dùng chung trong hệ thống cũ có thể được nhiều người sử dụng qua PAM. Hai quan hệ này khiến việc kiểm kê theo tài khoản đơn thuần chưa đủ để trả lời “ai đã làm gì”.

Chuỗi cần hiểu và liên kết được là:

```text
Con người cụ thể
    -> Danh tính cá nhân đã xác thực
    -> Tài khoản hoặc principal sử dụng
    -> Role / nhóm / quyền hiệu lực
    -> Phiên và hành động trên tài nguyên đích
```

Đây là mô hình khái niệm, không phải một luồng kỹ thuật bắt buộc giống nhau ở mọi nền tảng. Một số hệ thống dùng tài khoản quản trị riêng; hệ thống khác cho danh tính cá nhân nhận role tạm thời. Yêu cầu cốt lõi là giữ được ranh giới sử dụng đặc quyền và liên kết hoạt động với người khởi tạo.

### Đăng nhập thành công chưa trả lời câu hỏi về đặc quyền

**Xác thực** trả lời danh tính nào đang truy cập và có đáp ứng điều kiện đăng nhập hay không. **Cấp quyền** quyết định danh tính đó được làm gì trên tài nguyên nào.

MFA làm tăng độ tin cậy của việc xác thực nhưng không tự thu hẹp quyền. Một người xác thực đúng vẫn có thể được cấp quá nhiều quyền, thao tác sai hoặc có phiên bị chiếm dụng. Vì vậy, quản lý human privileged identity phải kết hợp bảo vệ danh tính với quản lý quyền hiệu lực và hoạt động trong phiên.

## 3. Phân biệt danh tính đặc quyền của con người và danh tính máy

PAM cần quản lý cả người lẫn máy. Tuy nhiên, cách sử dụng và vòng đời của hai nhóm khác nhau.

| Tiêu chí | Danh tính đặc quyền của con người | Danh tính workload hoặc dịch vụ |
|---|---|---|
| Chủ thể sử dụng chính | Một cá nhân thực hiện nhiệm vụ | Tiến trình, ứng dụng, tác vụ tự động |
| Ngữ cảnh truy cập | Công việc quản trị, xử lý sự cố, hỗ trợ, bảo trì | Chức năng vận hành của phần mềm hoặc hạ tầng |
| Cách liên kết trách nhiệm | Liên kết với người, vai trò công việc và phiên | Liên kết với workload, chủ sở hữu dịch vụ và lần thực thi |
| Điều kiện cấp quyền thường gặp | Nhu cầu công việc, xác thực phù hợp, phê duyệt theo rủi ro, thời hạn | Danh tính workload, chính sách tài nguyên, môi trường chạy, vòng đời tác vụ |
| Thay đổi vòng đời quan trọng | Gia nhập, chuyển nhiệm vụ, kết thúc hợp đồng, nghỉ việc | Triển khai, thay thế, di chuyển, dừng dịch vụ |
| Rủi ro điển hình | Lừa đảo, lạm dụng quyền, quyền tích lũy, mất thiết bị hoặc phiên | Secret nhúng sẵn, credential dùng chung, quyền rộng, workload bị chiếm dụng |

Một quản trị viên chạy script bằng danh tính cá nhân vẫn đang sử dụng quyền của con người, dù thao tác có tự động hóa. Ngược lại, một tác vụ chạy theo lịch bằng danh tính riêng của ứng dụng là hoạt động của workload, dù có một con người làm chủ sở hữu.

Cần phân biệt **người sở hữu danh tính dịch vụ** với **người trực tiếp sử dụng danh tính đó**. Có tên người phụ trách trong hồ sơ không biến tài khoản dịch vụ thành tài khoản cá nhân. Nếu credential của dịch vụ bị nhiều người dùng để đăng nhập quản trị tùy ý, tổ chức đang làm mờ ranh giới giữa hai loại danh tính và làm khó việc truy vết.

Một API token do người quản trị tạo cũng cần được phân loại theo cách sử dụng. Token phục vụ thao tác cá nhân phải được quản lý trong vòng đời quyền của người đó; token dành cho tác vụ tự động cần cơ chế danh tính workload phù hợp, tránh phụ thuộc không rõ ràng vào tài khoản của một nhân viên.

## 4. Những nhóm người có thể sử dụng đặc quyền

Danh sách dưới đây giúp mở rộng kiểm kê ra ngoài nhóm quản trị hệ điều hành.

| Nhóm người hoặc chức năng | Khả năng nhạy cảm có thể có | Điểm cần kiểm tra |
|---|---|---|
| Quản trị hệ điều hành, mạng và nền tảng | Cài phần mềm, sửa cấu hình, điều khiển kết nối, quản lý máy chủ | Phạm vi máy, môi trường, khả năng truy cập secret và hệ thống khác |
| Quản trị cơ sở dữ liệu | Đọc hoặc sửa dữ liệu, quản lý tài khoản, thay cấu hình sao lưu | Dữ liệu nhạy cảm, quyền xuất dữ liệu, khả năng phá phục hồi |
| Quản trị hệ thống nhận dạng | Tạo tài khoản, sửa nhóm, đặt lại xác thực, cấp role | Khả năng giả mạo hoặc nâng quyền của nhiều danh tính |
| Người vận hành nền tảng cloud và ảo hóa | Tạo tài nguyên, gán danh tính, thay chính sách, truy cập máy ảo | Quyền trên nhiều tài khoản, tenant hoặc miền quản trị |
| Kỹ sư phát triển, phát hành và DevOps | Sửa mã triển khai, cấu hình pipeline, phát hành ứng dụng | Khả năng thực thi mã bằng danh tính production hoặc lấy secret |
| Nhân viên hỗ trợ và quản trị ứng dụng | Đặt lại tài khoản, thay cấu hình nghiệp vụ, truy cập hồ sơ người dùng | Quyền mạo danh, dữ liệu nhạy cảm, thao tác ảnh hưởng nhiều người |
| Nhân sự bảo mật và quản trị PAM | Sửa chính sách kiểm soát, quản lý vault, xử lý cảnh báo | Khả năng tắt kiểm soát, lấy credential, sửa hoặc xóa bằng chứng |
| Người quản lý sao lưu và khôi phục | Khôi phục dữ liệu, xóa bản sao, sửa chính sách lưu giữ | Khả năng làm mất cả dữ liệu và phương án phục hồi |
| Nhà thầu, chuyên gia hoặc nhà cung cấp | Truy cập hỗ trợ theo thời hạn và nhiệm vụ | Người cụ thể sử dụng, thời hạn hợp đồng, phạm vi truy cập và thu hồi |

Không phải mọi người trong một nhóm đều cần cùng mức quyền. Chức danh là đầu vào để xem xét nhu cầu; quyền phải bám vào nhiệm vụ thực tế và phạm vi được giao.

### Quyền gián tiếp cũng cần được nhận diện

Hãy xem một người có thể:

- Thêm chính mình hoặc người khác vào nhóm có đặc quyền.
- Đặt lại mật khẩu hoặc yếu tố xác thực của một tài khoản mạnh hơn.
- Đọc credential, phát hành token hoặc sử dụng cơ chế chuyển sang danh tính khác.
- Sửa script, plugin, cấu hình hoặc pipeline sẽ được chạy với quyền cao.
- Thay điểm thực thi policy, tắt giám sát hoặc thay đổi cơ chế phê duyệt.
- Điều khiển nơi lưu trữ hoặc phục hồi dữ liệu của hệ thống nhạy cảm.

Không phải mỗi quyền kể trên đều dẫn đến cùng hậu quả trên mọi hệ thống. Cần xét điều kiện thực thi và các ràng buộc liên quan. Tuy nhiên, bỏ qua chúng vì “người này không có role quản trị trực tiếp” sẽ làm thiếu bức tranh về đặc quyền.

## 5. Thiết kế danh tính để làm việc hằng ngày và quản trị

### 5.1. Giới hạn việc dùng đặc quyền vào đúng ngữ cảnh

Một người quản trị vẫn có nhiều công việc không cần đặc quyền: đọc tài liệu, trao đổi nội bộ, viết mã hoặc theo dõi yêu cầu hỗ trợ. Duy trì quyền cao trong mọi hoạt động làm tăng cơ hội credential hoặc phiên quản trị bị lộ ở nơi không cần thiết.

Hai mô hình thường gặp là:

| Mô hình | Cách sử dụng | Điều cần bảo đảm |
|---|---|---|
| Tài khoản quản trị riêng | Một người có tài khoản thông thường và tài khoản quản trị được quản lý riêng | Hai tài khoản được liên kết với cùng người; hạn chế dùng tài khoản quản trị ngoài nhiệm vụ |
| Danh tính cá nhân nhận quyền tạm thời | Người dùng kích hoạt hoặc nhận role nhạy cảm khi có nhu cầu | Điều kiện cấp quyền, thời hạn, phạm vi và kết thúc hiệu lực được kiểm soát rõ |

Có thể kết hợp hai mô hình. Không nên áp dụng một quy tắc số lượng tài khoản giống nhau cho mọi nền tảng. Cần lựa chọn cách tách ngữ cảnh mà hệ thống thực sự thực thi được và tổ chức có thể quản lý trong toàn bộ vòng đời.

Việc có hai tài khoản cũng không tự tạo ra ranh giới nếu cả hai dùng chung credential, đăng nhập trên môi trường không phù hợp hoặc đều có quyền cao thường trực.

### 5.2. Least privilege: cấp quyền theo công việc

Với human privileged identity, least privilege nghĩa là xác định rõ:

1. Người nào cần làm công việc gì.
2. Hành động nào là cần thiết cho công việc đó.
3. Hành động áp dụng trên tài nguyên, môi trường và dữ liệu nào.
4. Quyền cần liên tục hay chỉ cần theo từng yêu cầu.
5. Những đường có thể mở rộng quyền ra ngoài nhiệm vụ.

Ví dụ, người trực ứng dụng có thể cần xem trạng thái và khởi động lại một dịch vụ. Không nên mặc định rằng nhu cầu này kéo theo quyền sửa hệ thống nhận dạng, đọc secret của mọi ứng dụng hay mở shell toàn quyền trên mọi máy chủ.

Các thao tác đọc cũng cần đánh giá. Quyền đọc log có thể cho thấy dữ liệu cá nhân, token hoặc thông tin vận hành nhạy cảm nếu ứng dụng ghi log không phù hợp. Phạm vi đọc phải gắn với nhu cầu và cách dữ liệu được bảo vệ.

### 5.3. JIT và JEA

**JIT — just-in-time access** giới hạn thời điểm và thời hạn được sử dụng quyền. Ví dụ, người vận hành được yêu cầu quyền xử lý một nhóm tài nguyên trong cửa sổ bảo trì cụ thể thay vì luôn giữ quyền đó.

**JEA — just-enough administration** giới hạn thao tác quản trị ở đúng khả năng cần thiết. Ví dụ, một endpoint chỉ cho phép xem trạng thái và khởi động lại dịch vụ đã chỉ định thay vì cho thực thi lệnh tùy ý.

Khi kết hợp hai cách tiếp cận, một người vừa không giữ quyền cao ngoài nhu cầu, vừa không có quyền rộng hơn nhiệm vụ trong thời gian được cấp.

Cần quản lý cả quyền yêu cầu đặc quyền. Nếu một người có thể tự chọn mọi role, tự duyệt và liên tục gia hạn, việc gắn nhãn JIT chưa bảo đảm quyền đã được giới hạn phù hợp.

### 5.4. Phân tách trách nhiệm theo mức rủi ro

Với thao tác có hậu quả lớn, người yêu cầu, người phê duyệt, người thay đổi policy và người kiểm tra bằng chứng không nên được gom quyền thiếu kiểm soát vào cùng một người.

Không phải mọi thao tác đều cần nhiều cấp phê duyệt. Cần lựa chọn cơ chế tương xứng với rủi ro và khả năng vận hành. Điểm cần tránh là một cá nhân có thể tự mở rộng quyền, sử dụng quyền đó rồi xóa dấu vết mà không có kiểm soát độc lập.

## 6. Bảo vệ quá trình xác thực và sử dụng credential

Đặc quyền chỉ được giới hạn đúng khi danh tính và phiên cũng được bảo vệ. Các điểm cần xem xét gồm:

- Cơ chế xác thực đủ mạnh cho mức nhạy cảm của tác vụ; ưu tiên khả năng chống lừa đảo khi nền tảng và mô hình triển khai hỗ trợ.
- Quản lý chặt việc đăng ký, thay đổi và khôi phục yếu tố xác thực.
- Điều kiện thiết bị và môi trường truy cập phù hợp với hoạt động quản trị.
- Hạn chế dùng credential quản trị trong tệp ghi chú, mã nguồn, hội thoại hoặc công cụ không được quản lý.
- Quản lý phiên, token và credential được phát hành sau đăng nhập.
- Theo dõi các sự kiện đăng nhập, kích hoạt quyền và thay đổi cơ chế xác thực có liên quan.

Khôi phục tài khoản có thể là một đường đặc quyền quan trọng. Nếu một người có thể vượt qua xác thực mạnh chỉ bằng quy trình hỗ trợ yếu, việc bảo vệ luồng đăng nhập chính sẽ không đủ.

### Vai trò của vault trong truy cập của con người

Khi tích hợp phù hợp, vault và cơ chế mở phiên có thể cho người dùng sử dụng tài khoản đích mà không phải biết trực tiếp mật khẩu. PAM kiểm soát việc cấp hoặc sử dụng credential và liên kết phiên với danh tính cá nhân.

Điều này giúp giảm sao chép mật khẩu và hỗ trợ luân chuyển credential. Tuy nhiên:

- Người có quyền đọc credential vẫn có thể lấy credential nếu policy cho phép.
- Phiên hợp lệ vẫn có thể bị lạm dụng trong phạm vi được cấp.
- Đường đăng nhập trực tiếp ngoài PAM có thể bỏ qua một phần kiểm soát.
- Luân chuyển mật khẩu không đồng nghĩa mọi token hoặc phiên trước đó đã bị vô hiệu hóa.
- Tài khoản quản trị vault và policy cấp secret cũng là các đặc quyền cần được kiểm soát.

Credential cần được luân chuyển và thu hồi theo cơ chế của hệ thống đích, có xem xét các phụ thuộc. Không nên xử lý tài khoản dùng chung bằng cách đổi mật khẩu tùy ý mà không biết dịch vụ hoặc người nào còn đang phụ thuộc vào nó.

## 7. Kiểm kê human privileged identity

Một bản kiểm kê hữu ích phải trả lời được “người nào có khả năng đặc quyền gì, ở đâu, vì sao và đến khi nào”. Không lưu mật khẩu, khóa riêng hay token thực tế trong hồ sơ kiểm kê.

| Nhóm thông tin | Nội dung cần biết |
|---|---|
| Liên kết với con người | Mã định danh cá nhân ổn định, đơn vị hoặc bên cung cấp, trạng thái làm việc |
| Tài khoản và miền danh tính | Các principal liên quan, hệ thống nguồn, tài khoản quản trị đích nếu có |
| Nhu cầu công việc | Nhiệm vụ, chủ sở hữu tài nguyên và căn cứ cấp quyền |
| Phạm vi hiệu lực | Role, nhóm, tài nguyên, môi trường, dữ liệu và quyền gián tiếp đáng chú ý |
| Cách sử dụng quyền | Thường trực, cấp theo yêu cầu, qua PAM, qua API hoặc đường khác |
| Vòng đời | Ngày bắt đầu, ngày kết thúc nếu có, điều kiện rà soát và thu hồi |
| Kiểm soát truy cập | Yêu cầu xác thực, phê duyệt theo rủi ro, điều kiện thiết bị hoặc kết nối |
| Credential và phiên | Tham chiếu đối tượng quản lý, cơ chế cấp và thu hồi; không chứa giá trị bí mật |
| Trách nhiệm | Người sử dụng, người phê duyệt hoặc chủ sở hữu chịu trách nhiệm cho phạm vi quyền |
| Bằng chứng | Tham chiếu yêu cầu, quyết định cấp quyền, lần rà soát và nhật ký liên quan |

Ví dụ bản ghi khái niệm cho một danh tính cá nhân:

```json
{
  "personRef": "person-042",
  "identityType": "human",
  "principalRef": "idp:operator-042",
  "privilegedContext": "payments-production-operations",
  "resourceScope": ["payments-production-service-group"],
  "allowedTasks": ["read-service-status", "restart-designated-service"],
  "grantMode": "time-bound",
  "requestRef": "change-208",
  "resourceOwnerRef": "team-payments",
  "accessEndsAt": "2026-12-01T10:00:00Z"
}
```

Đây là ví dụ dữ liệu minh họa, không phải schema hay cấu hình có thể áp dụng trực tiếp cho một sản phẩm PAM. Các trường mô tả nhiệm vụ cũng không tự thực thi quyền; cần ánh xạ chúng vào cơ chế cấp quyền và ràng buộc cụ thể của hệ thống đích.

Một tài khoản có chủ sở hữu rõ ràng vẫn có thể có quyền quá rộng. Ngược lại, một tài khoản có policy hẹp nhưng không xác định được ai sử dụng sẽ gây khó khăn cho điều tra và thu hồi. Cả liên kết với con người lẫn phạm vi quyền đều phải được quản lý.

## 8. Vòng đời quyền đặc biệt của một người

### 8.1. Khi gia nhập hoặc bắt đầu nhiệm vụ

Trước khi cấp quyền, cần xác minh người nhận, mục đích, phạm vi tài nguyên và chủ sở hữu chấp thuận. Đối với nhà thầu hoặc nhân sự bên ngoài, cần liên kết quyền với nhiệm vụ và thời hạn hợp đồng hoặc đợt hỗ trợ.

Tài khoản hoặc role nên được thiết lập theo nhu cầu cụ thể. Sao chép toàn bộ nhóm quyền của một người lâu năm dễ mang theo những quyền đã tích lũy qua nhiều nhiệm vụ.

### 8.2. Khi yêu cầu và sử dụng đặc quyền

Một luồng tham khảo:

```text
Người dùng nêu nhiệm vụ và phạm vi cần truy cập
    -> Hệ thống kiểm tra danh tính, điều kiện và quyền yêu cầu
    -> Phê duyệt nếu policy của tác vụ yêu cầu
    -> Cấp role hoặc mở phiên với giới hạn phù hợp
    -> Ghi nhận hành động và liên kết với yêu cầu
    -> Kết thúc quyền / phiên theo cơ chế đã xác định
```

Mỗi bước có thể được tự động hóa hoặc có người tham gia tùy nhiệm vụ. Điều quan trọng là quyền được cấp khớp với yêu cầu, người nhận không tự mở rộng được phạm vi ngoài policy và hoạt động có dấu vết phù hợp.

### 8.3. Khi chuyển nhóm hoặc thay đổi công việc

Một người chuyển từ nhóm cơ sở dữ liệu sang nhóm ứng dụng có thể cần quyền mới nhưng không còn cần quyền quản trị cơ sở dữ liệu cũ. Nếu chỉ cộng quyền mới mà không xét quyền cũ, đặc quyền sẽ tích lũy theo thời gian.

Cần xem xét cả nhóm lồng nhau, role tạm thời chưa hết hạn, quyền tại hệ thống đích, token cá nhân và các ngoại lệ đã cấp trước đây. Không nên chỉ kiểm tra danh sách nhóm ở một hệ thống trung tâm rồi coi như toàn bộ quyền đã được cập nhật.

### 8.4. Khi kết thúc nhiệm vụ hoặc rời tổ chức

Thu hồi cần bao gồm các danh tính liên quan, khả năng yêu cầu đặc quyền, role đang kích hoạt, credential cá nhân, token, phiên và đường truy cập tại hệ thống đích.

Khóa tài khoản trung tâm có thể ngăn đăng nhập mới nhưng chưa chắc kết thúc các phiên hiện hữu hoặc làm mất hiệu lực mọi token. Cần biết cơ chế thực tế của từng hệ thống và ghi nhận thời điểm thu hồi có hiệu lực.

Nếu người đó từng biết credential dùng chung, cần xem xét luân chuyển credential và xử lý các phụ thuộc. Nếu một tác vụ tự động đang chạy bằng token cá nhân của người nghỉ việc, cần chuyển sang cơ chế danh tính phù hợp cho workload thay vì duy trì tài khoản cá nhân vô thời hạn.

### 8.5. Rà soát trong quá trình làm việc

Rà soát không chỉ hỏi “tài khoản còn hoạt động không” mà phải xác nhận nhu cầu của từng phạm vi quyền. Chủ sở hữu tài nguyên và người hiểu nhiệm vụ cần có đủ thông tin để quyết định giữ, giảm hoặc thu hồi.

Việc chưa thấy sử dụng quyền trong một khoảng thời gian là tín hiệu để xem xét, không tự chứng minh quyền đó không còn cần. Quyền dự phòng cho một nhiệm vụ hiếm gặp có thể vẫn hợp lệ nhưng nên có căn cứ, phạm vi và điều kiện kích hoạt rõ ràng.

## 9. Tài khoản đích dùng chung và truy cập khẩn cấp

### 9.1. Khi hệ thống cũ buộc dùng tài khoản quản trị chung

Một số hệ thống chỉ cung cấp tài khoản quản trị đích dùng chung hoặc có hạn chế tích hợp. Khi chưa thể chuyển sang tài khoản cá nhân tại đích, PAM có thể hỗ trợ kiểm soát việc sử dụng.

Các điểm cần thiết gồm:

- Mỗi người xác thực bằng danh tính cá nhân trước khi được cấp truy cập.
- Ghi nhận ai yêu cầu, phạm vi được duyệt, thời điểm sử dụng và phiên tương ứng.
- Hạn chế để người dùng biết hoặc sao chép credential đích khi tích hợp cho phép.
- Kiểm soát truy cập đồng thời hoặc thiết lập cơ chế liên kết đủ rõ giữa người và hoạt động.
- Hạn chế các đường dùng tài khoản đích trực tiếp ngoài quy trình.
- Luân chuyển credential và kiểm tra khả năng thu hồi theo cách hệ thống hỗ trợ.

Nếu mật khẩu chung đã được cung cấp cho nhiều người và họ có thể đăng nhập ngoài PAM, một bản ghi đặt chỗ credential trong vault không đủ để chứng minh chính xác người thực hiện từng hành động.

### 9.2. Truy cập khẩn cấp

Truy cập khẩn cấp, thường gọi là **break-glass access**, phục vụ tình huống cần khôi phục hoặc xử lý hệ thống khi luồng truy cập thông thường không đáp ứng được. Đây vẫn là một hình thức đặc quyền cần được quản lý.

Cần xác định trước:

- Tình huống nào được dùng và ai được phép kích hoạt.
- Phạm vi quyền cần cho khôi phục.
- Cách bảo quản, cấp và sử dụng credential khi một thành phần phụ thuộc bị lỗi.
- Cách ghi nhận người sử dụng, thời điểm và hoạt động ngay cả khi một phần hạ tầng không sẵn sàng.
- Việc kết thúc truy cập, xử lý credential và xem lại hoạt động sau sử dụng.

Thiết kế phải tính đến khả năng thực sự cần dùng khi hệ thống gặp sự cố, đồng thời tránh biến tài khoản khẩn cấp thành đường quản trị thường ngày ít được giám sát.

## 10. Truy vết hoạt động và bằng chứng kiểm toán

Đối với human privileged identity, một câu hỏi trọng tâm là: **có thể liên kết một hành động nhạy cảm với danh tính cá nhân, phạm vi được cấp và ngữ cảnh công việc hay không?**

Một chuỗi bằng chứng hữu ích gồm:

| Mốc hoạt động | Bằng chứng nên liên kết |
|---|---|
| Xác thực | Danh tính, thời điểm, phương thức và kết quả xác thực phù hợp |
| Yêu cầu quyền | Nhiệm vụ, tài nguyên, role hoặc tác vụ, thời hạn, mã yêu cầu |
| Quyết định cấp quyền | Policy hoặc người phê duyệt, phạm vi được chấp thuận |
| Tạo phiên hoặc token | Principal đích, ngữ cảnh quyền, thời điểm và mã liên kết |
| Thực hiện hành động | Sự kiện tại tài nguyên, thao tác, kết quả và đối tượng bị tác động |
| Kết thúc hoặc thu hồi | Lý do, mốc thời gian, trạng thái thực tế của quyền và phiên |
| Rà soát | Quyết định giữ, thay đổi hoặc loại bỏ quyền cùng người chịu trách nhiệm |

Mã liên kết phiên, định danh người dùng và thời gian nhất quán giúp đối chiếu nhật ký từ hệ thống nhận dạng, PAM và tài nguyên đích. Không phải thao tác nào cũng xuất hiện trong video phiên; API, tác vụ chạy nền và công cụ quản trị khác có thể cần nguồn nhật ký riêng.

Nhật ký cần được bảo vệ khỏi sửa hoặc xóa trái phép. Đồng thời, bằng chứng không nên chứa mật khẩu, token hoặc dữ liệu nhạy cảm vượt quá mục đích theo dõi cần thiết. Nếu bản ghi phiên có thể thu thập nội dung nhạy cảm, cần có kiểm soát truy cập và cơ chế xử lý phù hợp cho chính bằng chứng đó.

Liên kết được với một tài khoản cá nhân hỗ trợ quy trách nhiệm nhưng không tự chứng minh cá nhân đó đã chủ ý thực hiện mọi thao tác. Khi nghi có chiếm dụng danh tính hoặc phiên, điều tra phải xét thêm bằng chứng liên quan.

### Các tín hiệu cần xem xét

- Một người yêu cầu hoặc sử dụng đặc quyền ngoài phạm vi nhiệm vụ quen thuộc.
- Có thay đổi yếu tố xác thực gần thời điểm kích hoạt quyền nhạy cảm.
- Một phiên truy cập nhiều tài nguyên ngoài nhóm được giao.
- Có hành động đọc hàng loạt secret, tự cấp thêm quyền hoặc thay đổi giám sát.
- Một tài khoản đã chuyển nhiệm vụ hoặc hết hợp đồng vẫn còn sử dụng quyền.
- Nhật ký tại đích ghi nhận hoạt động quản trị nhưng không có yêu cầu hoặc phiên tương ứng trong luồng PAM dự kiến.

Các tín hiệu này cần được phân tích theo ngữ cảnh. Một hoạt động khác thường chưa đủ để kết luận có tấn công, nhưng có thể là căn cứ để xác minh, hạn chế quyền hoặc khoanh vùng theo quy trình ứng cứu.

## 11. Ví dụ xuyên suốt: kỹ sư vận hành production

Lan là kỹ sư mới của nhóm vận hành ứng dụng thanh toán. Nhiệm vụ hiện tại là xem trạng thái và khởi động lại một dịch vụ production khi có yêu cầu xử lý sự cố phù hợp.

### Cách cấp quyền dễ gây vấn đề

Để thuận tiện, nhóm đưa Lan vào nhóm quản trị chung của toàn bộ máy chủ và gửi mật khẩu tài khoản đích dùng chung. Quyền không có ngày xem xét lại và vẫn được giữ sau khi đợt trực kết thúc.

Thiết kế này gây ra nhiều vấn đề:

- Quyền vượt quá tác vụ, ứng dụng và thời gian cần thiết.
- Khó thu hồi triệt để một mật khẩu đã được biết và có thể sao chép.
- Nhật ký chỉ có tài khoản đích dùng chung khó liên kết chắc chắn với từng người.
- Việc Lan chuyển nhóm hoặc nghỉ việc đòi hỏi tìm lại nhiều quyền và phụ thuộc không được ghi rõ.
- Nếu danh tính hoặc thiết bị của Lan bị chiếm dụng, phạm vi ảnh hưởng có thể vượt khỏi dịch vụ thanh toán.

### Cách thiết kế gắn với human privileged identity

| Thành phần | Cách thiết kế minh họa |
|---|---|
| Liên kết cá nhân | Dùng danh tính cá nhân của Lan và ghi nhận các principal quản trị liên quan |
| Phạm vi tài nguyên | Chỉ nhóm dịch vụ thanh toán production được giao |
| Phạm vi hành động | Xem trạng thái và khởi động lại dịch vụ được chỉ định qua cơ chế hạn chế phù hợp |
| Điều kiện truy cập | Xác thực và điều kiện môi trường phù hợp; yêu cầu công việc và phê duyệt khi policy yêu cầu |
| Thời gian | Cấp quyền có thời hạn theo yêu cầu xử lý; không duy trì role quản trị rộng ngoài nhu cầu |
| Credential đích | PAM quản lý khi nền tảng hỗ trợ; hạn chế hiển thị mật khẩu cho người vận hành |
| Bằng chứng | Liên kết danh tính Lan, yêu cầu, role hiệu lực, phiên và sự kiện tại dịch vụ |
| Kết thúc nhiệm vụ | Thu hồi quyền và xử lý phiên theo cơ chế thực tế; rà soát lại khi đổi nhiệm vụ |

Ngay cả với quyền hẹp, thao tác khởi động lại sai lúc vẫn có thể gây gián đoạn. Cần phối hợp với điều kiện vận hành của ứng dụng, khả năng chịu lỗi và quy trình xử lý sự cố.

### Khi nghi danh tính của Lan bị chiếm dụng

Đội ứng cứu cần xác định quyền và phiên nào đang tồn tại, hạn chế khả năng nhận thêm quyền, kết thúc các truy cập liên quan theo cơ chế hỗ trợ và bảo toàn bằng chứng.

Nếu có khả năng credential hoặc secret đã bị đọc, phải xem xét phạm vi liên đới và thu hồi tương ứng. Nếu kẻ tấn công đã tạo quyền mới, khóa tài khoản ban đầu chưa chắc loại bỏ được đường truy cập đó.

Ví dụ cho thấy quản lý con người không dừng ở việc tạo một tài khoản có tên riêng. Cần theo dõi toàn bộ quan hệ giữa người, quyền, credential, phiên và tài nguyên trong suốt vòng đời công việc.

## 12. Những lỗi thường gặp

| Cách làm | Vấn đề phát sinh | Hướng điều chỉnh |
|---|---|---|
| Chỉ kiểm kê nhóm có tên quản trị | Bỏ sót quyền gián tiếp, quyền đọc dữ liệu nhạy cảm hoặc khả năng đặt lại danh tính | Kiểm kê theo khả năng hiệu lực và các đường cấp quyền |
| Coi tài khoản có tên riêng là đã đủ truy vết | Không liên kết được với tài khoản đích, token hoặc phiên dùng chung | Duy trì chuỗi liên kết từ người đến hoạt động tại tài nguyên |
| Dùng tài khoản quản trị cho mọi công việc | Tăng thời gian và bề mặt tiếp xúc của đặc quyền | Tách ngữ cảnh và chỉ cấp quyền khi cần |
| Sao chép toàn bộ quyền của đồng nghiệp | Mang theo đặc quyền dư thừa hoặc đã tích lũy | Cấp theo nhiệm vụ, tài nguyên và thời hạn |
| Chỉ bảo vệ đăng nhập mà bỏ qua khôi phục tài khoản | Tạo đường vượt qua kiểm soát xác thực | Quản lý cả đăng ký, thay đổi và phục hồi yếu tố xác thực |
| Cho nhà cung cấp dùng chung một danh tính không phân biệt người | Khó xác định người sử dụng và thu hồi từng cá nhân | Liên kết truy cập với người cụ thể và thời hạn nhiệm vụ |
| Coi việc hết hạn role là đã kết thúc mọi truy cập | Phiên hoặc token có thể còn hiệu lực | Xác định và xử lý từng loại quyền, phiên, credential |
| Giữ tài khoản người nghỉ việc để tác vụ tự động tiếp tục chạy | Làm mờ trách nhiệm và cản trở thu hồi | Chuyển tác vụ sang danh tính workload phù hợp |
| Cho rằng quản trị viên PAM không cần kiểm soát riêng | Tập trung khả năng cấp quyền, lấy secret hoặc thay bằng chứng | Phân tách trách nhiệm và bảo vệ quản trị nền tảng PAM |

## 13. Bài tập nhận diện và thiết kế

Xét bốn trường hợp:

1. Một nhân viên hỗ trợ có thể đặt lại MFA của quản trị viên hệ thống nhận dạng.
2. Một kỹ sư không đăng nhập production nhưng sửa được pipeline chạy với role triển khai production.
3. Một nhà cung cấp dùng tài khoản chung để hỗ trợ nhiều ứng dụng, không có thời hạn kết thúc.
4. Một quản trị viên cơ sở dữ liệu đã chuyển sang nhóm khác nhưng vẫn còn token cá nhân truy cập cơ sở dữ liệu cũ.

Với mỗi trường hợp, hãy trả lời:

- Người sử dụng, principal và cơ chế đặc quyền là gì?
- Quyền trực tiếp hoặc gián tiếp nào làm trường hợp này nhạy cảm?
- Phạm vi nào cần giới hạn: hành động, tài nguyên, dữ liệu, thời gian hay khả năng cấp quyền tiếp?
- Cần liên kết những bằng chứng nào để truy vết?
- Khi kết thúc nhiệm vụ hoặc nghi có chiếm dụng, cần thu hồi những đối tượng nào?

Gợi ý: trường hợp thứ nhất liên quan khả năng kiểm soát danh tính khác; trường hợp thứ hai liên quan quyền thực thi mã gián tiếp; trường hợp thứ ba thiếu liên kết cá nhân và ranh giới vòng đời; trường hợp thứ tư cho thấy thay đổi công việc chưa được phản ánh đầy đủ vào credential và quyền ở hệ thống đích.

## 14. Ghi nhớ

Human privileged identity phải được quản lý dựa trên con người thực, khả năng hiệu lực và ngữ cảnh sử dụng. Tên tài khoản, chức danh hay một lần đăng nhập có MFA không đủ để xác định quyền đã được kiểm soát phù hợp.

Một thiết kế PAM đầy đủ cần biết ai có đặc quyền, vì sao cần quyền đó, quyền tác động được vào đâu, tồn tại bao lâu và hoạt động được ghi nhận như thế nào. Kiểm kê, least privilege, JIT/JEA, quản lý credential, giám sát phiên và thu hồi phải cùng phục vụ chuỗi quản lý đó.
