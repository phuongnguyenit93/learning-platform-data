# Privileged account standard

**Privileged account standard** là bộ yêu cầu cụ thể mà tổ chức đặt ra để tạo, sử dụng, giám sát và kết thúc vòng đời tài khoản đặc quyền. Standard biến định hướng quản lý truy cập đặc quyền (Privileged Access Management — PAM) thành các điều kiện có thể triển khai và kiểm chứng: tài khoản phải có owner nào, quyền được cấp theo cách nào, credential được bảo vệ ra sao và bằng chứng nào chứng minh kiểm soát đang hoạt động.

Bài học thuộc chương **Governance**, áp dụng cho tài khoản quản trị, tài khoản dịch vụ và truy cập tới hạ tầng nhạy cảm. Nội dung kết nối kiểm kê quyền, least privilege, JIT/JEA, vault, luân chuyển credential, giám sát phiên, kiểm toán và ứng phó sự cố thành một bộ yêu cầu thống nhất.

Các yêu cầu và mã kiểm soát dưới đây là **mẫu phục vụ học tập và thiết kế standard nội bộ**. Chúng không phải một tiêu chuẩn đã được cơ quan bên ngoài ban hành, không thay thế quy định riêng của tổ chức và không giả định một sản phẩm PAM cụ thể.

## 1. Standard khác policy và procedure như thế nào?

| Loại tài liệu | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Policy | Tổ chức muốn đạt điều gì và ai có thẩm quyền? | Quyền đặc biệt phải được kiểm soát theo nhu cầu và mức rủi ro |
| Standard | Yêu cầu tối thiểu nào phải được đáp ứng? | Mọi tài khoản đặc quyền trong phạm vi phải có owner được xác nhận và mục đích sử dụng |
| Procedure/runbook | Thực hiện yêu cầu bằng những bước nào? | Quy trình onboarding một tài khoản database vào vault |
| Cấu hình kỹ thuật | Hệ thống thực thi yêu cầu bằng gì? | Chính sách cấp quyền, connector, thời hạn và bộ lọc phiên |
| Evidence | Điều gì chứng minh đã thực hiện và có hiệu lực? | Hồ sơ phê duyệt, trạng thái quyền trên đích và sự kiện thu hồi |

Một yêu cầu như “bảo vệ tài khoản quản trị phù hợp” khó kiểm tra vì không xác định được điều kiện đạt. Một hướng dẫn dài về nút bấm của sản phẩm cũng chưa thay thế standard, vì nó có thể không nói yêu cầu nào là bắt buộc hoặc xử lý thế nào khi không áp dụng được.

Một standard hữu ích cần mô tả rõ **phạm vi, điều kiện bắt buộc, trách nhiệm, bằng chứng và cơ chế ngoại lệ**.

## 2. Xác định phạm vi theo khả năng thực tế

Tài khoản đặc quyền không chỉ là tài khoản mang tên `root`, `admin` hoặc `administrator`. Đặc quyền được đánh giá theo khả năng có hiệu lực, kể cả quyền gián tiếp qua nhóm, vai trò, ủy quyền hoặc thao tác có thể làm thay đổi cơ chế bảo vệ.

Các khả năng cần xem xét gồm quản trị hệ thống, thay đổi chính sách quyền, cấp credential, cài hoặc nạp mã, đọc dữ liệu nhạy cảm vượt nhiệm vụ thông thường, thay đổi log và kiểm soát thành phần bảo mật.

| Loại tài khoản/danh tính | Ví dụ | Nội dung standard cần bao phủ |
| --- | --- | --- |
| Tài khoản quản trị cá nhân | Tài khoản vận hành production của một người | Định danh người dùng, phê duyệt, MFA, JIT và giám sát |
| Tài khoản cục bộ/tích hợp sẵn | Tài khoản quản trị máy chủ hoặc thiết bị | Kiểm kê, quản lý credential, đường truy cập và khôi phục |
| Tài khoản dùng chung | Tài khoản mà hệ thống cũ chưa hỗ trợ tách cá nhân | Quy trách nhiệm mỗi lần dùng và ngoại lệ có kiểm soát |
| Danh tính dịch vụ/workload | Tài khoản job, pipeline, agent | Phụ thuộc, gắn danh tính workload và quyền hẹp |
| Danh tính quản trị nền tảng | Vai trò quản trị cloud, cluster hoặc ứng dụng | Phạm vi quyền, điều kiện kích hoạt và quyền kế thừa |
| Tài khoản nhà cung cấp | Truy cập hỗ trợ hoặc bảo trì | Đầu mối bảo trợ, thời hạn và đích được duyệt |
| Tài khoản khẩn cấp | Break-glass | Điều kiện sử dụng, khả năng khôi phục và xem xét sau dùng |

Credential như khóa, token hoặc chứng thư cần được quản lý cùng danh tính và phạm vi quyền liên quan. Một hệ thống không dùng mật khẩu vẫn nằm trong phạm vi nếu danh tính của nó có đặc quyền.

Standard phải bao phủ các đường truy cập được phép: qua PAM, API, tự động hóa, console cục bộ và kênh khẩn cấp. Đưa một tài khoản vào vault không tự làm những đường truy cập trực tiếp khác biến mất.

## 3. Quy ước viết yêu cầu có thể kiểm chứng

Trong mẫu của bài học:

- **PHẢI:** điều kiện bắt buộc trong phạm vi áp dụng; không đáp ứng cần được xử lý hoặc có ngoại lệ hợp lệ.
- **NÊN:** thực hành ưu tiên; lựa chọn khác cần có lý do phù hợp.
- **CÓ THỂ:** phương án được phép nếu đáp ứng các điều kiện liên quan.

Không dùng những từ này để che sự mơ hồ. Một yêu cầu nên nêu được đối tượng, kết quả cần đạt và cách xác minh.

```text
Mã: PA-01
Đối tượng: mọi tài khoản đặc quyền thuộc phạm vi
Yêu cầu: PHẢI có owner hợp lệ đã nhận trách nhiệm và mục đích sử dụng
Trách nhiệm: account owner xác nhận; đội inventory duy trì liên kết
Bằng chứng: định danh principal, owner, chấp nhận và thời điểm xác minh
Xử lý thiếu: ghi trạng thái chưa xác định, điều tra và escalation theo rủi ro
```

Những tham số như thời lượng JIT, hạn xem xét hoặc thời gian lưu bằng chứng cần nằm trong profile được phê duyệt, có phiên bản và phù hợp từng nhóm rủi ro. Standard không nên để một giá trị quan trọng là “tùy cấu hình mặc định” mà không xác định ai chịu trách nhiệm chọn và kiểm tra nó.

## 4. Vai trò và quyền ra quyết định

| Vai trò | Trách nhiệm điển hình |
| --- | --- |
| Chủ sở hữu standard | Duy trì yêu cầu, phạm vi, phiên bản và lịch xem xét |
| Account owner | Xác nhận nhu cầu tồn tại, mục đích và vòng đời tài khoản |
| Resource owner | Phê duyệt điều kiện tác động lên tài nguyên thuộc thẩm quyền |
| Technical owner | Hiểu phụ thuộc, thiết kế thay đổi và khôi phục |
| Đội IAM/PAM | Triển khai các cơ chế quản lý được giao, lưu trạng thái và sự kiện |
| Security/đội ứng phó | Đánh giá kiểm soát, theo dõi rủi ro và phối hợp sự cố |
| Người có thẩm quyền chấp nhận rủi ro | Quyết định ngoại lệ trong phạm vi được ủy quyền |
| Bên kiểm tra độc lập | Đánh giá bằng chứng và mức đáp ứng với độ độc lập phù hợp |

Ownership không tự cấp quyền đăng nhập hoặc đọc secret. Người vận hành vault cũng không mặc nhiên có thẩm quyền xác nhận nhu cầu nghiệp vụ của mọi tài khoản được lưu trong đó.

Cần phân tách người yêu cầu, người phê duyệt và người thực thi ở các điểm có xung đột theo chính sách. Nếu một người giữ nhiều vai trò, standard phải xác định kiểm soát bổ sung thay vì để người đó tự phê duyệt toàn bộ quyền của mình.

## 5. Nhóm yêu cầu về inventory và vòng đời

### PA-01 — Định danh, owner và tài sản liên quan

Mỗi tài khoản đặc quyền PHẢI có bản ghi kiểm kê liên kết đúng principal nguồn, realm/tenant, loại tài khoản, mục đích, account owner và tài nguyên chịu tác động quyền.

Tên tài khoản hoặc IP không đủ làm định danh duy nhất. Cần phân biệt nơi định nghĩa principal, tài nguyên nơi quyền có hiệu lực và workload sử dụng credential. Owner phải hợp lệ, đã nhận trách nhiệm và có đường dự phòng/escalation.

**Bằng chứng:** dữ liệu nguồn, định danh ổn định, chấp nhận ownership, liên kết asset và mốc xác minh. Chỉ có tên owner trong một bảng chưa chứng minh trách nhiệm đã được nhận.

### PA-02 — Tạo và thay đổi có thẩm quyền

Tạo tài khoản, thay đổi phạm vi quyền và thay đổi điều kiện sử dụng PHẢI có yêu cầu và quyết định đúng thẩm quyền, gắn với mục đích và tài nguyên cụ thể. Tài khoản mới không được mặc nhiên nhận quyền rộng hoặc nhận lại toàn bộ quyền của tài khoản mẫu nếu chưa có lý do.

Mẫu cấu hình, image và tự động hóa provisioning cũng thuộc phạm vi kiểm soát thay đổi, vì chúng có thể tạo đặc quyền hàng loạt.

**Bằng chứng:** yêu cầu, người phê duyệt, phạm vi được duyệt, phiên bản cấu hình và trạng thái thực tế sau triển khai.

### PA-03 — Xem xét và kết thúc vòng đời

Quyền và nhu cầu tài khoản PHẢI được xem xét theo lịch đã phê duyệt và khi có sự kiện như nghỉ việc, chuyển nhiệm vụ, đổi owner, ngừng ứng dụng hoặc thay đổi tài nguyên.

Khi hết nhu cầu, PHẢI có quyết định và thực hiện thu hồi các đường quyền, credential và phiên liên quan theo khả năng nền tảng. Không chỉ xóa bản ghi inventory hoặc chuyển một ticket sang trạng thái hoàn tất.

Với tài khoản phát hiện chưa rõ owner, phải ghi nhận thiếu sót và xử lý theo rủi ro cùng phụ thuộc vận hành. Không giữ mãi trạng thái “đang điều tra”, nhưng cũng không tự vô hiệu hóa mọi tài khoản production khi chưa đánh giá tác động và thẩm quyền cần thiết.

**Bằng chứng:** lần xem xét, quyết định vòng đời, xử lý phụ thuộc và xác nhận quyền không còn hiệu lực trên phạm vi đích liên quan.

## 6. Nhóm yêu cầu về phạm vi và thời gian quyền

### PA-04 — Least privilege và JEA

Tài khoản PHẢI chỉ có các capability và phạm vi tài nguyên cần cho nhiệm vụ được duyệt. Việc đánh giá PHẢI xét quyền hiệu lực, bao gồm nhóm, vai trò, kế thừa và khả năng mở rộng quyền gián tiếp liên quan.

Nếu tác vụ chỉ cần nạp lại một dịch vụ, không nên cấp shell quản trị toàn máy như quyền thông thường. Với cơ chế giới hạn lệnh, phải kiểm soát tham số, đích, cấu hình và phụ thuộc có thể thay đổi ý nghĩa của lệnh.

**Bằng chứng:** hợp đồng tác vụ/quyền, chính sách trên đích và kiểm tra các biến thể ngoài phạm vi trong môi trường được phép. Tên role có chữ “limited” không phải bằng chứng quyền đã hẹp.

### PA-05 — JIT và quyền thường trực

Quyền đặc biệt của người dùng NÊN được kích hoạt theo nhu cầu và có giới hạn thời gian khi nền tảng đáp ứng. Mọi quyền thường trực còn lại PHẢI có lý do, owner và cơ chế xem xét theo mức rủi ro.

Standard phải phân biệt quyền eligible, quyền đang hoạt động và quyền đã thu hồi. Thời hạn JIT phải được áp dụng tại những điểm thực thi liên quan; đóng cửa sổ PAM không tự chứng minh token hoặc phiên trên đích đã hết quyền.

**Bằng chứng:** điều kiện kích hoạt, phê duyệt khi cần, khoảng hiệu lực thực tế, kết quả thu hồi và các trường hợp tồn dư/chưa xác định.

### PA-06 — Danh tính sử dụng và phân tách nhiệm vụ

Người thực hiện PHẢI được nhận diện qua danh tính riêng khi nền tảng hỗ trợ. Hoạt động quản trị của con người NÊN được tách khỏi hoạt động làm việc thông thường theo thiết kế của tổ chức.

Không cho người yêu cầu tự thay owner, đích, nhãn môi trường hoặc người phê duyệt để vượt điều kiện cấp quyền. Danh tính dịch vụ không được dùng như một cách đăng nhập quản trị cá nhân ngoài mục đích được duyệt.

**Bằng chứng:** ánh xạ danh tính, quy tắc phê duyệt, quyền sửa metadata/chính sách và sự kiện sử dụng thực tế.

## 7. Nhóm yêu cầu về xác thực và credential

### PA-07 — Xác thực phù hợp loại chủ thể

Truy cập quản trị tương tác của con người PHẢI sử dụng cơ chế xác thực mạnh theo profile đã phê duyệt. Mẫu standard yêu cầu MFA cho đường quản trị tương tác khi nền tảng hỗ trợ; trường hợp không hỗ trợ phải được đánh giá và xử lý bằng cơ chế ngoại lệ cùng kiểm soát bù.

NÊN ưu tiên phương thức chống phishing phù hợp khả năng nền tảng và yêu cầu vận hành. Không coi việc đã xác thực ở giao diện PAM là đủ nếu một đường truy cập trực tiếp tới đích vẫn chỉ cần credential yếu.

Workload không tương tác cần được xác thực bằng cơ chế dành cho máy, gắn đúng workload và ngữ cảnh tin cậy. Không áp dụng máy móc yêu cầu nhập mã MFA của con người cho job tự động; cũng không coi token có tên pipeline do phía gọi tự khai là bằng chứng danh tính.

**Bằng chứng:** cấu hình xác thực, điều kiện liên kết danh tính, các đường truy cập trong phạm vi và kiểm tra phù hợp với từng loại chủ thể.

### PA-08 — Bảo vệ và cấp phát secret

Credential đặc quyền PHẢI được quản lý trong cơ chế được phê duyệt, như vault hoặc hệ thống cấp credential/danh tính workload tương đương. Không lưu secret trong mã nguồn, ticket, tài liệu inventory, log hoặc tệp chia sẻ không được bảo vệ.

Quyền xem, cấp phát, thay đổi và khôi phục secret phải được phân quyền riêng. NÊN sử dụng cơ chế cấp phiên hoặc cấp credential hẹp mà không tiết lộ secret dài hạn cho người gọi khi thiết kế hỗ trợ.

PHẢI kiểm soát cả credential của chính connector, tài khoản quản trị vault và phương án khôi phục. Tập trung secret vào vault làm tăng tầm quan trọng của việc bảo vệ nền tảng này; nó không tự giảm quyền vốn có của tài khoản trên đích.

**Bằng chứng:** nguồn quản lý secret, chính sách truy cập, sự kiện cấp phát đã lọc dữ liệu nhạy cảm và cấu hình các bên có thể đọc hoặc thay đổi secret.

### PA-09 — Luân chuyển, hết hạn và phụ thuộc

Mỗi loại credential PHẢI có chính sách vòng đời phù hợp với mức rủi ro và khả năng nền tảng: cấp mới, thời hạn nếu có, điều kiện luân chuyển, thu hồi và khôi phục.

Không dùng một chu kỳ đổi mật khẩu giống nhau cho mọi chủ thể rồi coi đó là toàn bộ quản lý credential. Cần xử lý theo loại credential và tình huống, đặc biệt khi có lộ lọt, thay đổi người được biết secret hoặc không còn nhu cầu sử dụng.

Với tài khoản dịch vụ, PHẢI đánh giá consumer, cache, kết nối dài hạn và khả năng cập nhật trước luân chuyển theo kế hoạch. Nếu credential cũ và mới cùng được chấp nhận trong giai đoạn chuyển đổi, phải có giới hạn, theo dõi và xác nhận kết thúc giai đoạn đó.

Token hết hạn ngắn nhưng được tự động tái cấp vô hạn cho cùng một quyền vẫn có thể duy trì khả năng đặc quyền thường trực. Cần xem xét đồng thời chính sách cấp lại và quyền của danh tính nguồn.

**Bằng chứng:** chính sách theo loại credential, danh sách phụ thuộc đã biết, kết quả cấp/luân chuyển/thu hồi và kiểm tra trạng thái thực tế. Sự kiện “rotation requested” không chứng minh credential cũ đã mất tác dụng.

## 8. Nhóm yêu cầu về giám sát, bằng chứng và thu hồi

### PA-10 — Quy trách nhiệm và giám sát hành động

Hoạt động đặc quyền PHẢI tạo bằng chứng đủ để liên kết chủ thể yêu cầu, principal thực thi, tài nguyên đích, thời gian, quyền hoặc hành động và kết quả trong phạm vi hệ thống hỗ trợ.

Đối với phiên tương tác, profile cần quy định mức giám sát và ghi phiên phù hợp. Đối với API hoặc workload, sự kiện thao tác có cấu trúc và log trên đích có thể quan trọng hơn video màn hình. Không yêu cầu ghi mọi đầu vào một cách mù quáng vì có thể thu cả secret và dữ liệu không cần thiết.

PHẢI bảo vệ bằng chứng khỏi sửa hoặc xóa trái phép, kiểm soát người được xem, chuẩn hóa thời gian và áp dụng chính sách lưu giữ đã được tổ chức xác định. Thời gian lưu phải được chọn theo nhu cầu điều tra, vận hành và các yêu cầu áp dụng, không tự coi một con số trong ví dụ là nghĩa vụ chung.

Các dấu hiệu như truy cập ngoài đích được duyệt, hành vi ngoài hợp đồng tác vụ, hoạt động bất thường của tài khoản dịch vụ hoặc sử dụng break-glass cần có nơi tiếp nhận và quy trình xử lý. Có log nhưng không có đầu mối xem xét là một khoảng trống vận hành.

**Bằng chứng:** sự kiện có mã tương quan, log tại đích, cấu hình bảo vệ/lưu giữ, cảnh báo và hồ sơ xử lý tương ứng.

### PA-11 — Thu hồi hiệu lực và ứng phó sự cố

PHẢI có cơ chế thu hồi theo thời hạn và theo sự kiện, cùng quy trình xử lý khi nghi credential bị lộ hoặc tài khoản bị lạm dụng. Cần xác định ai được quyết định, ai thực hiện và cách cân nhắc ảnh hưởng dịch vụ.

Thu hồi cần xét nhóm/role, credential thứ cấp, token đã phát hành, phiên dài hạn và các đường truy cập khác có liên quan. Không khẳng định đã chặn toàn bộ chỉ vì một tài khoản bị khóa ở nguồn quản lý.

Nếu chưa xác nhận được kết quả, PHẢI ghi trạng thái chưa xác định và tiếp tục xử lý. Hết thời gian chờ không chứng minh thao tác chưa xảy ra; tự thử lại có thể tạo tác động lặp hoặc gián đoạn thêm.

**Bằng chứng:** mốc yêu cầu thu hồi, mốc mất quyền được xác nhận, phạm vi kiểm tra, phần tồn dư và hồ sơ ứng phó. Chỉ số độ trễ thu hồi phải phân biệt trường hợp đã xác nhận với trường hợp chưa biết kết quả.

## 9. Yêu cầu bổ sung theo loại tài khoản

### 9.1. Tài khoản dùng chung

NÊN thay bằng danh tính cá nhân hoặc ủy quyền theo tác vụ khi khả thi. Nếu còn phải dùng chung, PHẢI có lý do, owner, tập người được phép và cơ chế quy trách nhiệm mỗi lần dùng.

Cần xác định cách checkout/cấp phiên, quy tắc sử dụng đồng thời, điều kiện xử lý credential sau dùng và khả năng truy cập trực tiếp ngoài PAM. Một log chỉ ghi tên `admin_shared` mà không xác định được người sử dụng chưa đáp ứng mục tiêu quy trách nhiệm.

### 9.2. Danh tính dịch vụ và tự động hóa

PHẢI có owner, workload liên quan, mục đích và phạm vi quyền. Không cho phép sử dụng tương tác ngoài nhiệm vụ đã duyệt; nếu nền tảng hỗ trợ, thực thi giới hạn đó bằng cấu hình thay vì chỉ ghi trong tài liệu.

NÊN ưu tiên danh tính workload và credential có vòng đời phù hợp, tránh phân phối secret quản trị rộng cho nhiều job. Khi nhiều workload dùng chung một tài khoản, cần đánh giá việc tách danh tính để giảm phụ thuộc và cải thiện quy trách nhiệm.

Quyền thay đổi pipeline, script, image hoặc cấu hình có thể là đường để sử dụng đặc quyền của workload. Standard cần đưa những thành phần đó vào phạm vi kiểm soát thay đổi và phân tách quyền liên quan.

### 9.3. Tài khoản nhà cung cấp

PHẢI có bên bảo trợ trong tổ chức, công việc, người dùng thực tế, phạm vi tài nguyên và điều kiện kết thúc. Thời hạn hợp tác không tự được chuyển thành quyền truy cập liên tục tới mọi hệ thống.

Cấp quyền theo nhiệm vụ và thời gian phù hợp, giám sát theo profile, xem xét lại khi nhân sự hoặc công việc thay đổi. Đầu mối nhà cung cấp không phải người duy nhất có thẩm quyền phê duyệt quyền trên tài nguyên của tổ chức.

### 9.4. Tài khoản break-glass

PHẢI có điều kiện sử dụng, người có thẩm quyền, cơ chế lấy quyền/credential, đầu mối dự phòng, bằng chứng và xem xét sau sử dụng. Quyền khẩn cấp không được trở thành cách vận hành thường ngày để bỏ qua quy trình.

Thiết kế cần xét tình huống IAM/PAM thông thường không khả dụng, nhưng vẫn bảo vệ secret và khả năng quy trách nhiệm. Cần kiểm tra phương án khôi phục theo kế hoạch được phép, tránh để quy trình chỉ tồn tại trên giấy.

Sau sử dụng phải xem lại lý do, thao tác, phạm vi, kết quả và các quyền hoặc credential cần xử lý. Một tài khoản break-glass giữ quyền thường trực vẫn phải xuất hiện trong kiểm kê standing privilege, dù được phân tích riêng theo mục đích.

## 10. Khi thành phần kiểm soát bị lỗi

Standard PHẢI xác định hành vi khi IAM, vault, PAM, hệ thống phê duyệt hoặc kho kiểm toán không khả dụng. Không để hành vi mặc định không được xem xét quyết định việc cấp quyền.

| Tình huống | Điều cần quy định |
| --- | --- |
| Không xác minh được danh tính hoặc phạm vi quyền | Không tự cấp quyền mới dựa trên dữ liệu do phía gọi tự khai |
| Nguồn phê duyệt không truy cập được | Cách từ chối, trì hoãn hoặc sử dụng đường khẩn cấp đúng thẩm quyền |
| Kho bằng chứng gián đoạn | Khi nào phải chặn thao tác mới, khi nào được dùng bộ đệm bền vững có kiểm soát |
| Không xác nhận được thu hồi | Giữ trạng thái chưa xác định, tăng theo dõi và escalation |
| Vault không cấp được credential | Dừng/trì hoãn hoặc kích hoạt phương án khôi phục đã được duyệt |

Nếu dùng bộ đệm bằng chứng, phải quy định bảo vệ, dung lượng, giới hạn thời gian, chống mất dữ liệu và đối soát sau khôi phục. Không coi việc bỏ log là một lựa chọn do người yêu cầu tự bật.

Đường khẩn cấp cần điều kiện riêng và được xem xét sau sự kiện. Nó không phải cờ `skip-controls` cho mọi phiên khi hệ thống gặp lỗi.

## 11. Ngoại lệ có thời hạn

### PA-12 — Quản lý ngoại lệ và rủi ro còn lại

Trường hợp chưa đáp ứng yêu cầu PHẢI được ghi nhận với mã kiểm soát, tài khoản/tài nguyên, lý do, rủi ro, kiểm soát bù, người có thẩm quyền quyết định, thời hạn và kế hoạch xử lý.

```text
Mã ngoại lệ: EX-204
Yêu cầu liên quan: PA-07, PA-09
Phạm vi: tài khoản cục bộ trên một thiết bị legacy xác định
Lý do: chưa hỗ trợ cơ chế xác thực/cấp credential theo profile mục tiêu
Kiểm soát bù: giới hạn nguồn kết nối, cấp phiên có kiểm soát, tăng giám sát
Owner xử lý: đầu mối được chỉ định
Chấp nhận rủi ro: người đúng thẩm quyền theo chính sách tổ chức
Hạn hiệu lực và mốc xem xét: được ghi trong hồ sơ đã duyệt
Kế hoạch: nâng cấp hoặc thay thế, kèm kiểm tra lại sau thay đổi
```

Đây là mẫu hồ sơ, không phải một ngoại lệ đã được phê duyệt. Kiểm soát bù cần được kiểm chứng và không mặc nhiên tương đương yêu cầu bị thiếu.

Người vận hành không tự có quyền chấp nhận mọi rủi ro chỉ vì họ cần hệ thống tiếp tục chạy. Gia hạn ngoại lệ cần quyết định mới hoặc quy trình xem xét được định nghĩa; không tự động gia hạn vô hạn.

Khi ngoại lệ hết hạn, phải có escalation và quyết định xử lý theo rủi ro, phụ thuộc và thẩm quyền. Không âm thầm coi ngoại lệ là còn hiệu lực; cũng không tạo sự cố production bằng một hành động tự động chưa được thiết kế và phê duyệt.

Tài khoản có ngoại lệ hợp lệ vẫn cần được báo riêng. “Được phép tạm thời không đáp ứng” khác với “đã đáp ứng yêu cầu”.

## 12. Ví dụ profile triển khai

YAML dưới đây là cấu trúc tự định nghĩa để diễn đạt một profile quản trị tương tác production. Đây không phải cấu hình có thể nhập trực tiếp vào một sản phẩm PAM.

```yaml
standard_id: PAM-STD-01
standard_version: example-1.0
profile_id: production-human-admin-example
subject_type: human
access_type: interactive
resource_environment: production

identity:
  named_subject_required: true
  authentication_profile_ref: approved-strong-authentication

approval:
  policy_ref: production-privilege-approval
  requester_cannot_approve_own_request: true

privilege:
  task_catalog_ref: approved-production-admin-tasks
  target_inventory_ref: verified-production-assets
  jit_required: true
  max_activation_minutes: 30
  standing_grants_require_exception: true

credential:
  delivery: brokered-session
  management_policy_ref: approved-credential-lifecycle

audit:
  require_durable_start_record: true
  event_profile_ref: attributable-privileged-operation
  retention_policy_ref: approved-audit-retention

revocation:
  require_effective_end_evidence: true
  unresolved_result: investigate-and-escalate

exceptions:
  policy_ref: time-bounded-risk-acceptance
```

Giới hạn 30 phút chỉ là giá trị minh họa của profile này. Tổ chức cần chọn và phê duyệt giá trị theo công việc, mức rủi ro, khả năng thực thi và khả năng thu hồi; không mặc định dùng cho mọi tài khoản hoặc workload.

Các tham chiếu trong profile phải dẫn tới chính sách có nội dung, owner và phiên bản được quản lý. `jit_required: true` hoặc `require_effective_end_evidence: true` chỉ diễn đạt yêu cầu; chúng không chứng minh hệ thống đã thực thi được.

Khi nền tảng không thể đáp ứng một điều kiện, cần thay đổi thiết kế hoặc đi qua quy trình ngoại lệ. Không đánh dấu đáp ứng chỉ vì tệp cấu hình chứa đúng tên thuộc tính.

## 13. Ma trận yêu cầu, thực thi và bằng chứng

Bảng sau là hướng dẫn thiết kế việc kiểm chứng trong hệ thống triển khai, không phải kết quả kiểm tra một môi trường thực tế.

| Mã | Ví dụ cơ chế thực thi | Điều cần xác minh |
| --- | --- | --- |
| PA-01 | Inventory liên kết principal, owner và asset | Principal đúng, owner còn hợp lệ và đã chấp nhận |
| PA-02 | Workflow và provisioning có kiểm soát | Quyền sau triển khai khớp phạm vi được duyệt |
| PA-03 | Xem xét định kỳ và xử lý sự kiện vòng đời | Quyền hết nhu cầu được thu hồi trên đích |
| PA-04 | Role hẹp, adapter tác vụ, giới hạn tham số/đích | Tác vụ hợp lệ làm được và biến thể vượt phạm vi bị chặn |
| PA-05 | Kích hoạt JIT và cơ chế hết hạn | Yêu cầu mới bị chặn sau hết hạn, phần quyền còn lại được xử lý |
| PA-06 | Danh tính cá nhân và tách người phê duyệt | Không thể tự sửa metadata hoặc tự duyệt để vượt điều kiện |
| PA-07 | Profile xác thực cho người và workload | Các đường truy cập tương ứng chịu kiểm soát đúng loại |
| PA-08 | Vault, cấp phiên hoặc cơ chế credential được duyệt | Secret không bị trả/lưu ngoài phạm vi được phép |
| PA-09 | Luân chuyển/cấp lại theo loại credential | Consumer hoạt động đúng, credential cũ hết tác dụng khi phải kết thúc |
| PA-10 | Log đích, sự kiện PAM và giám sát phiên | Liên kết được chủ thể với tác động, bằng chứng được bảo vệ |
| PA-11 | Thu hồi, xử lý phiên và quy trình ứng phó | Có kết quả theo từng đích, không che phần chưa xác định |
| PA-12 | Hồ sơ ngoại lệ, hạn hiệu lực và escalation | Đúng thẩm quyền, đúng phạm vi và kiểm soát bù thực sự hoạt động |

Cần phân biệt ba mức bằng chứng:

1. **Ý định:** yêu cầu hoặc cấu hình cho thấy tổ chức muốn điều gì.
2. **Triển khai:** trạng thái hệ thống cho thấy cơ chế đã được thiết lập.
3. **Hiệu lực:** dữ liệu hoặc kiểm tra phù hợp cho thấy cơ chế thực sự tạo ra kết quả mong muốn.

Một yêu cầu truy cập bị từ chối ở giao diện chưa chứng minh API phía sau cũng từ chối. Một thông báo thu hồi thành công từ PAM chưa chứng minh mọi token trên đích đã mất hiệu lực. Kiểm tra cần đi tới đúng ranh giới thực thi, trong phạm vi được phép và với kế hoạch phù hợp.

Bằng chứng cũng phải đủ mới và đúng phạm vi. Kết quả ở môi trường thử nghiệm hoặc một thiết bị đại diện chỉ chứng minh những gì phương pháp lấy mẫu cho phép kết luận; không tự áp dụng cho toàn bộ production.

## 14. Quản trị standard trong vận hành

### 14.1. Phiên bản và thay đổi

Standard cần có owner tài liệu, bên phê duyệt, ngày hiệu lực, phạm vi áp dụng, kỳ xem xét và lịch sử thay đổi. Khi yêu cầu thay đổi, cần đánh giá tác động tới profile, cấu hình, runbook, đào tạo, bằng chứng và các ngoại lệ đang tồn tại.

Không thay đổi nội dung tiêu chí giữa kỳ đánh giá rồi so số liệu như thể phương pháp không đổi. Báo cáo cần ghi phiên bản standard và profile được sử dụng.

### 14.2. Lộ trình áp dụng

Có thể triển khai theo nhóm tài khoản và mức nhạy cảm, nhưng phải xác định rõ phần đã áp dụng, phần đang chuyển đổi và phần chưa được đánh giá. Các hệ thống mới nên dùng baseline được phê duyệt ngay từ provisioning để tránh tạo thêm quyền thường trực ngoài kế hoạch.

Với hệ thống cũ, cần kế hoạch giảm khoảng trống, chủ sở hữu việc xử lý và mốc quyết định. Một lộ trình không có đầu mối hoặc thời hạn có thể biến thành ngoại lệ không giới hạn.

### 14.3. Báo cáo mức đáp ứng

Tối thiểu cần phân biệt:

| Trạng thái | Ý nghĩa |
| --- | --- |
| Đạt | Có bằng chứng phù hợp rằng yêu cầu được đáp ứng trong phạm vi đánh giá |
| Không đạt | Có bằng chứng yêu cầu áp dụng nhưng chưa được đáp ứng |
| Ngoại lệ hợp lệ | Có quyết định chấp nhận sai lệch trong phạm vi và thời hạn cụ thể |
| Chưa đủ dữ liệu | Chưa thể kết luận đạt hoặc không đạt |
| Không áp dụng | Có lý do và phạm vi được xác nhận cho yêu cầu không liên quan |

Ví dụ, một yêu cầu áp dụng cho 100 tài khoản có 90 đạt, 5 ngoại lệ, 3 không đạt và 2 chưa đủ dữ liệu. Khi báo tỷ lệ đạt trên toàn bộ 100 tài khoản, kết quả là 90%; không cộng 5 ngoại lệ thành 95% đã đáp ứng.

Mẫu số phải rõ. Nếu loại các trường hợp không áp dụng, cần công bố số bị loại và lý do. Dữ liệu thiếu hoặc hệ thống chưa được kiểm kê không được tự coi là đạt. Khi không có đối tượng áp dụng, báo không áp dụng thay vì tự tạo tỷ lệ 100%.

Ngoài số lượng tài khoản đạt, nên theo dõi standing privilege còn lại, quyền mới phát sinh, độ trễ thu hồi, ngoại lệ quá hạn, độ bao phủ bằng chứng và tác động tới công việc. Thời gian chờ cấp quyền hoặc số lần phải dùng break-glass có thể chỉ ra profile đang thiếu tác vụ cần thiết.

## 15. Bài thực hành áp dụng standard

Bạn nhận được một tài khoản dịch vụ production có đặc điểm:

```text
Owner cũ đã chuyển đội
Credential nằm trong vault và có lịch luân chuyển
Tài khoản giữ quyền quản trị rộng trên database
Job chạy hằng đêm và không hỗ trợ MFA tương tác
Log hiện chỉ ghi tên tài khoản dịch vụ
Chưa có bằng chứng thu hồi khi job kết thúc
```

### Yêu cầu phân tích

- Chọn các mã PA liên quan và xác định dữ liệu còn thiếu.
- Phân biệt những kiểm soát đã triển khai với những điều chưa chứng minh được hiệu lực.
- Xác định account owner, resource owner và technical owner cần tham gia.
- Đề xuất trạng thái đánh giá, kế hoạch xử lý và ngoại lệ nếu thực sự cần.

### Hướng xử lý minh họa

PA-01 và PA-03 cần xử lý ownership không còn hợp lệ và xem xét lại nhu cầu. PA-04 cần phân tích quyền job thực sự cần, kể cả khả năng gián tiếp; không coi quyền quản trị rộng là hợp lệ chỉ vì job hiện chạy được.

PA-07 cần cơ chế xác thực workload phù hợp, không yêu cầu người trực nhập MFA mỗi đêm như cách khắc phục mặc định. PA-08 và PA-09 có dấu hiệu đã triển khai vault/luân chuyển, nhưng vẫn phải kiểm tra phụ thuộc, quyền lấy secret và kết quả credential cũ hết hiệu lực.

PA-10 cần liên kết hoạt động với workload hoặc lần chạy cụ thể và đích thực tế. Nếu thiết kế mục tiêu dùng quyền JIT, PA-05 và PA-11 cần bằng chứng thời gian hiệu lực cùng thu hồi; nếu chưa đáp ứng, không tự điền thời điểm kết thúc bằng thời gian job dự kiến.

Kế hoạch thay đổi phải có kiểm tra tương thích và phương án khôi phục. Không tự vô hiệu hóa tài khoản hoặc đổi credential production chỉ để nhanh chóng làm hồ sơ đạt chuẩn.

## 16. Tự kiểm tra kiến thức

**1. Vì sao standard không nên chỉ viết “mọi tài khoản quản trị phải an toàn”?**  
Vì không có điều kiện rõ để triển khai và đánh giá. Cần chỉ ra phạm vi, yêu cầu, trách nhiệm, bằng chứng và xử lý sai lệch.

**2. Đưa tài khoản vào vault có chứng minh đã đáp ứng standard không?**  
Không. Vẫn phải xác minh owner, quyền, các đường truy cập, cấp phát credential, giám sát, vòng đời và các yêu cầu áp dụng khác.

**3. Job không hỗ trợ MFA tương tác có tự động là tài khoản không thể quản lý an toàn không?**  
Không. Cần cơ chế xác thực máy phù hợp, gắn danh tính workload với nguồn tin cậy và kiểm soát phạm vi quyền. Không dùng yêu cầu dành cho người tương tác để thay thế thiết kế danh tính máy.

**4. Ngoại lệ hợp lệ có được tính như đã đáp ứng yêu cầu không?**  
Không. Đó là sai lệch được chấp nhận trong phạm vi, điều kiện và thời hạn cụ thể, cần báo riêng.

**5. Phiên PAM đóng có nghĩa quyền trên đích đã mất chưa?**  
Chưa chắc. Token, phiên khác hoặc đường cấp quyền còn lại có thể vẫn có hiệu lực. Phải đối chiếu theo khả năng của hệ thống đích.

**6. Một cấu hình ghi thời lượng JIT 30 phút có đủ chứng minh hiệu lực không?**  
Không. Cần kiểm tra cách áp dụng thời hạn, trạng thái quyền thực tế và các trường hợp thu hồi thất bại hoặc chưa xác nhận.

Privileged account standard có giá trị khi mỗi yêu cầu nối được tới cơ chế thực thi, người chịu trách nhiệm và bằng chứng đủ để kiểm chứng. Governance nhờ đó trở thành khả năng quản lý quyền đặc biệt trong vận hành, thay vì chỉ là một tài liệu đã được ký duyệt.