# Mapping control với risk

## 1. Mục tiêu của việc mapping

Trong quản trị truy cập đặc quyền (Privileged Access Management — PAM), có vault, MFA và ghi hình phiên chưa đủ để trả lời câu hỏi: **những kiểm soát này đang giảm rủi ro nào, ở đâu và bằng cách nào?**

Mapping control với risk là việc xây dựng quan hệ có thể giải thích và kiểm chứng giữa một kịch bản rủi ro với các kiểm soát được dùng để xử lý kịch bản đó. Kết quả phải cho thấy:

- Sự kiện bất lợi nào có thể xảy ra, trên tài sản nào và gây hậu quả gì.
- Kiểm soát tác động vào điều kiện hoặc bước nào của kịch bản.
- Kiểm soát bao phủ những tài khoản, quyền, hệ thống và đường truy cập nào.
- Bằng chứng nào chứng minh kiểm soát được triển khai và vận hành.
- Phần rủi ro nào vẫn còn, ai chịu trách nhiệm xử lý hoặc chấp nhận.

Trong chương Compliance, mapping giúp nối yêu cầu quản trị với việc vận hành PAM hằng ngày. Một ma trận có nhiều dòng đánh dấu không tự chứng minh hệ thống an toàn hoặc đáp ứng mọi nghĩa vụ tuân thủ. Giá trị của ma trận nằm ở khả năng truy ngược từ rủi ro đến thiết kế, hoạt động thực tế và bằng chứng của kiểm soát.

### Tình huống xuyên suốt

Một doanh nghiệp có cơ sở dữ liệu thanh toán, máy chủ ứng dụng và tài khoản hỗ trợ của nhà cung cấp. Doanh nghiệp đã mua giải pháp PAM, đưa phần lớn mật khẩu quản trị vào vault và bật ghi hình phiên.

Tuy nhiên:

- Một số quản trị viên vẫn đăng nhập trực tiếp vào cơ sở dữ liệu.
- Tài khoản nhà cung cấp còn hiệu lực sau khi hợp đồng kết thúc.
- Pipeline triển khai giữ credential dài hạn ngoài vault.
- Người quản trị PAM có thể thay đổi chính sách rồi tự rà soát log của mình.

Nếu chỉ map “PAM platform → rủi ro truy cập trái phép”, cả bốn điểm yếu có thể bị che khuất. Bài học này chuyển từ cách map tên sản phẩm sang cách map từng cơ chế kiểm soát với từng kịch bản cụ thể.

## 2. Phân biệt risk, control objective và control activity

Ba khái niệm này thường bị trộn vào một ô, khiến người đọc không biết cần kiểm tra điều gì.

| Thành phần | Câu hỏi cần trả lời | Ví dụ trong PAM |
|---|---|---|
| Tài sản hoặc quy trình | Điều gì cần được bảo vệ? | Cơ sở dữ liệu thanh toán production |
| Kịch bản rủi ro | Ai có thể làm gì, nhờ điều kiện nào, gây hậu quả gì? | Người có credential quản trị bị lộ đăng nhập trực tiếp và sửa dữ liệu thanh toán |
| Mục tiêu kiểm soát | Trạng thái mong muốn là gì? | Chỉ người được xác thực, phê duyệt và cấp quyền đúng phạm vi mới được quản trị |
| Hoạt động kiểm soát | Cơ chế hoặc hoạt động cụ thể nào tạo ra trạng thái đó? | Cấp role theo yêu cầu có thời hạn, chặn đường quản trị trực tiếp, đối soát phiên |
| Kiểm thử | Làm cách nào đánh giá kiểm soát? | Thử truy cập ngoài đường được phép và kiểm tra role bị thu hồi sau thời hạn |
| Bằng chứng | Dữ liệu nào hỗ trợ kết luận? | Policy có phiên bản, log cấp/thu hồi role, log target, kết quả thử nghiệm |
| Rủi ro còn lại | Điều gì vẫn có thể xảy ra sau khi áp dụng kiểm soát? | Người được cấp quyền hợp lệ vẫn có thể lạm dụng quyền trong cửa sổ được duyệt |

“Quản lý tài khoản đặc quyền” thường là một mục tiêu hoặc nhóm hoạt động quá rộng. “Mỗi tài khoản đặc quyền production có owner; đối soát hằng ngày với inventory; tài khoản không có owner bị cách ly theo quy trình đã duyệt” là mô tả có thể giao việc và kiểm thử.

### 2.1. Viết risk statement có thể hành động

Một mẫu hữu ích:

> Do **điều kiện yếu**, **tác nhân hoặc sự kiện** có thể thực hiện **hành động bất lợi** trên **tài sản/phạm vi**, dẫn đến **hậu quả nghiệp vụ**.

Ví dụ:

> Do tài khoản nhà cung cấp không tự hết hạn và chưa được đối soát với trạng thái hợp đồng, người từng hỗ trợ hệ thống có thể tiếp tục truy cập đặc quyền vào máy chủ production, dẫn đến thay đổi trái phép hoặc lộ dữ liệu vận hành.

Mô tả này tốt hơn “rủi ro vendor” vì nó chỉ rõ điều kiện cần xử lý: vòng đời truy cập không gắn với hợp đồng. MFA có thể giảm một số nguy cơ chiếm dụng danh tính, nhưng không tự làm hết hạn quyền của một danh tính vẫn được xác thực hợp lệ.

### 2.2. Không gọi thiếu kiểm soát là toàn bộ rủi ro

“Không có vault” là một thiếu hụt về thiết kế hoặc triển khai. Cần diễn giải tiếp:

- Credential nào đang tồn tại ngoài cơ chế quản lý?
- Ai có thể lấy hoặc sử dụng credential đó?
- Credential mở được quyền trên target nào?
- Hành động nào có thể gây tổn thất?

Nếu không nối tới kịch bản, tổ chức dễ mua công cụ để đóng một dòng kiểm toán nhưng vẫn để nguyên đường khai thác.

## 3. Mô hình liên kết từ rủi ro đến bằng chứng

Có thể hình dung chuỗi truy vết như sau:

~~~mermaid
flowchart TD
    A["Kịch bản rủi ro trên tài sản cụ thể"] --> B["Mục tiêu kiểm soát"]
    B --> C["Hoạt động kiểm soát PAM"]
    C --> D["Phạm vi triển khai và phụ thuộc"]
    D --> E["Kiểm thử và bằng chứng vận hành"]
    E --> F["Đánh giá hiệu lực"]
    F --> G["Rủi ro còn lại và quyết định xử lý"]
    G --> H["Theo dõi thay đổi và rà soát mapping"]
    H --> A
~~~

Đây không phải quan hệ một-một:

- Một rủi ro có thể cần nhiều kiểm soát ở các lớp khác nhau.
- Một kiểm soát có thể hỗ trợ nhiều rủi ro.
- Một kiểm soát chỉ có hiệu lực trong phạm vi triển khai thực tế.
- Nhiều kiểm soát có thể cùng phụ thuộc vào một thành phần và cùng thất bại khi thành phần đó lỗi.

Ví dụ, MFA, phê duyệt JIT và danh tính người dùng đều có thể phụ thuộc vào cùng một hệ thống định danh. Không nên mặc định ba dòng kiểm soát tương đương ba lớp bảo vệ độc lập.

### Định danh cần ổn định

Dùng ID riêng cho từng đối tượng để theo dõi thay đổi:

~~~text
R-PAM-001     Kịch bản rủi ro
O-PAM-001     Mục tiêu kiểm soát
C-PAM-001     Hoạt động kiểm soát
M-PAM-001     Quan hệ giữa một risk và một control
T-PAM-001     Thủ tục kiểm thử
E-PAM-001     Hồ sơ bằng chứng
EX-PAM-001    Ngoại lệ
~~~

ID ở đây chỉ là quy ước minh họa nội bộ, không phải mã của một tiêu chuẩn. Khi nội dung risk thay đổi, cần lưu phiên bản và lịch sử thay vì đổi ý nghĩa của ID mà không để lại dấu vết.

## 4. Quy trình mapping trong thực tế

### Bước 1 — Chốt phạm vi và đường truy cập

Xác định tài sản, môi trường, loại tài khoản và đường truy cập trước khi chọn kiểm soát.

Với một hệ thống production, cần xem ít nhất:

- Tài khoản con người: quản trị viên, hỗ trợ, nhà cung cấp.
- Tài khoản phi con người: dịch vụ, job định kỳ, pipeline, workload.
- Quyền thường trực, quyền cấp theo yêu cầu và quyền khẩn cấp.
- Đường qua PAM broker và đường trực tiếp như console, SSH, API hoặc kết nối cơ sở dữ liệu.
- Quyền quản trị bản thân hệ thống PAM, kho bằng chứng và cấu hình tích hợp.

Nếu chỉ xét phiên đi qua PAM, mapping có thể bỏ qua chính đường truy cập làm mất hiệu lực của kiểm soát.

### Bước 2 — Phân rã kịch bản thành các điều kiện

Với rủi ro sửa dữ liệu bằng credential quản trị bị lộ, một chuỗi điều kiện có thể là:

~~~text
Credential bị lấy
    → credential vẫn có hiệu lực
    → target chấp nhận kết nối từ đường trực tiếp
    → tài khoản có quyền ghi quá rộng
    → hành động không bị ngăn hoặc phát hiện kịp thời
    → dữ liệu bị sửa, khó xác định người thực hiện
~~~

Một kiểm soát cần tác động vào ít nhất một mắt xích có ý nghĩa. Nếu không giải thích được mắt xích đó, quan hệ mapping có thể chỉ là gắn nhãn.

### Bước 3 — Chọn kiểm soát theo cơ chế tác động

Xem xét ba vai trò chính:

| Vai trò | Cơ chế điển hình | Giới hạn cần ghi rõ |
|---|---|---|
| Phòng ngừa | JIT/JEA, giới hạn đường truy cập, phê duyệt, MFA, credential ngắn hạn | Có thể bị bypass hoặc sai policy; chỉ hiệu lực trên phạm vi được bao phủ |
| Phát hiện | Cảnh báo hành vi, đối soát log target với PAM, rà soát quyền | Phụ thuộc độ đầy đủ của dữ liệu và thời gian phát hiện |
| Khắc phục hoặc phục hồi | Thu hồi quyền, vô hiệu hóa credential, kết thúc phiên, phục hồi cấu hình | Chỉ giảm hậu quả nếu thực hiện đủ nhanh và đúng đối tượng |

Một hoạt động có thể đóng nhiều vai trò. Rotate credential sau phiên giúp hạn chế tái sử dụng credential cũ; rotate khẩn cấp sau nghi ngờ lộ lọt còn là hành động xử lý sự cố. Cần mô tả đúng tình huống sử dụng, tránh chỉ đếm số loại kiểm soát.

### Bước 4 — Viết lý do cho từng quan hệ

Mỗi quan hệ risk–control cần một câu giải thích:

> C-PAM-004 giảm khả năng tái sử dụng credential quản trị bị lộ bằng cách thay credential và xác nhận target từ chối credential cũ sau khi hoàn tất rotation.

Câu này cũng gợi ý cách kiểm thử. Nếu chỉ có log “rotation job succeeded” mà không xác nhận trạng thái tại target, bằng chứng có thể chưa đủ để kết luận credential cũ đã mất hiệu lực.

Có thể phân loại quan hệ:

- **Trực tiếp:** tác động vào một điều kiện của kịch bản.
- **Hỗ trợ:** cung cấp danh tính, inventory, dữ liệu hoặc khả năng quản trị để kiểm soát khác hoạt động.
- **Bù đắp:** xử lý một phần mục tiêu khi kiểm soát dự kiến chưa áp dụng được; phải có phạm vi, giới hạn và đánh giá riêng.

“Bù đắp” không có nghĩa là tự động tương đương. Ghi hình phiên không thay thế hoàn toàn việc giới hạn quyền hoặc chặn truy cập trái phép.

### Bước 5 — Gắn owner, kiểm thử và bằng chứng

Một mapping dùng được phải có người chịu trách nhiệm cho hoạt động và nguồn bằng chứng. Cần phân biệt:

- Risk owner quyết định ưu tiên xử lý và chấp nhận rủi ro theo thẩm quyền.
- Control owner chịu trách nhiệm thiết kế và hiệu lực của kiểm soát.
- Người vận hành thực hiện công việc, xử lý lỗi và lưu bằng chứng.
- Người đánh giá kiểm tra kết quả với mức độc lập phù hợp.

Một người có thể giữ nhiều vai trò trong tổ chức nhỏ, nhưng xung đột nhiệm vụ phải được nhận diện. Việc tự thay policy, tự chọn mẫu và tự kết luận đạt làm giảm độ tin cậy của đánh giá.

### Bước 6 — Đánh giá rủi ro còn lại

Sau khi biết kiểm soát nào vận hành hiệu quả và bao phủ tới đâu, mới đánh giá phần rủi ro còn lại. Không hạ mức rủi ro chỉ vì:

- Công cụ đã được mua.
- Policy đã được ký.
- Tính năng đang bật.
- Có một phiên thành công trong buổi demo.
- Một yêu cầu kiểm toán đã có tài liệu đính kèm.

Rủi ro còn lại phải gắn với giới hạn, ngoại lệ và dữ liệu thực tế của kỳ đánh giá.

## 5. Ma trận risk–control cho một phạm vi PAM

Bảng dưới dùng các kịch bản minh họa. Tần suất, ngưỡng và thời hạn cần được tổ chức lựa chọn theo mức độ nhạy cảm và khả năng vận hành.

| Risk ID và kịch bản | Kiểm soát chính | Cơ chế giảm rủi ro | Bằng chứng phù hợp | Phần cần theo dõi |
|---|---|---|---|---|
| R-PAM-001: Dùng credential quản trị bị lộ để sửa dữ liệu production | JIT; giới hạn đường quản trị; rotation; đối soát target log | Giảm thời gian quyền tồn tại, hạn chế đường sử dụng và phát hiện bypass | Log cấp/thu hồi quyền, kiểm thử đường trực tiếp, trạng thái rotation tại target | Phiên còn sống sau khi quyền hết hạn; quyền khẩn cấp |
| R-PAM-002: Người đã nghỉ vẫn dùng tài khoản đặc quyền | Kết nối vòng đời danh tính; đối soát account; vô hiệu hóa tài khoản liên quan | Chấm dứt khả năng truy cập sau sự kiện kết thúc quan hệ | Sự kiện nghỉ việc, inventory tài khoản liên kết, log vô hiệu hóa và thử từ chối truy cập | Tài khoản local hoặc tài khoản dùng chung không liên kết đúng người |
| R-PAM-003: Pipeline lộ secret dài hạn có quyền production | Workload identity; credential ngắn hạn; role tối thiểu; kiểm soát phát hành secret | Giảm secret tĩnh và giới hạn quyền mà workload nhận được | Policy cấp token, log phát hành, scope role, kết quả thử token hết hạn | Workload đã bị chiếm vẫn có thể xin token trong phạm vi được cấp |
| R-PAM-004: Nhà cung cấp truy cập ngoài thời gian và phạm vi hỗ trợ | Sponsor; ngày hết hạn; phê duyệt theo ticket; giới hạn target và cửa sổ truy cập | Giới hạn điều kiện cấp quyền cho bên thứ ba | Hợp đồng hoặc yêu cầu hỗ trợ, approval, log phiên, log thu hồi | Cấp lại quyền không có căn cứ mới; sponsor không còn phù hợp |
| R-PAM-005: Break-glass bị dùng như đường truy cập thường ngày | Giữ quyền khẩn cấp có kiểm soát; cảnh báo ngay; rà soát độc lập sau sử dụng | Tăng khả năng phát hiện và trách nhiệm giải trình của truy cập khẩn cấp | Log lấy credential, alert, ticket sự cố, biên bản rà soát, rotation sau sử dụng | Cơ chế khẩn cấp phải hoạt động khi một số dịch vụ thông thường lỗi |
| R-PAM-006: Quản trị viên xóa bằng chứng để che giấu hành động | Gửi log ra vùng quản trị tách biệt; bảo vệ lưu trữ; giới hạn quyền xóa; giám sát pipeline log | Giảm khả năng một chủ thể vừa hành động vừa xóa toàn bộ dấu vết | Policy lưu trữ, log truy cập kho, kiểm thử quyền xóa, cảnh báo mất log | Log nguồn có thể chưa được tạo hoặc chưa kịp gửi |
| R-PAM-007: PAM ngừng hoạt động làm gián đoạn xử lý sự cố production | HA; kiểm thử phục hồi; quy trình truy cập khẩn cấp có kiểm soát | Duy trì hoặc khôi phục đường quản trị cần thiết | Kết quả diễn tập, thời gian phục hồi, kết quả truy cập và audit sau sự cố | Phụ thuộc chung vào mạng, định danh, DNS hoặc khóa giải mã |
| R-PAM-008: Người quản trị PAM tự nới policy để cấp quyền cho mình | Tách nhiệm vụ; phê duyệt thay đổi nhạy cảm; ghi log độc lập; đối soát cấu hình | Hạn chế hoặc phát hiện thay đổi cấu hình vì lợi ích cá nhân | Lịch sử policy, approval khác người, log quản trị, kết quả so sánh cấu hình | Quyền siêu quản trị và quy trình khẩn cấp có thể vượt cơ chế thường |

Bảng tổng hợp giúp nhìn khoảng trống, nhưng chưa thay hồ sơ chi tiết. Đặc biệt, từ “JIT” không cho biết quyền gì được cấp, cho ai, trên target nào và ai bảo đảm quyền thật sự bị thu hồi.

## 6. Ví dụ chi tiết: credential quản trị cơ sở dữ liệu bị lộ

### 6.1. Hồ sơ rủi ro

~~~text
Risk ID: R-PAM-001
Tài sản: Cơ sở dữ liệu thanh toán production
Kịch bản: Credential quản trị bị lộ được dùng để thay đổi dữ liệu trái phép
Điều kiện: Credential dài hạn; có đường kết nối trực tiếp; quyền ghi rộng
Hậu quả: Sai lệch giao dịch, gián đoạn xử lý, khó quy trách nhiệm
Risk owner: Chủ sở hữu dịch vụ thanh toán
Phạm vi đánh giá: Tài khoản quản trị con người trên cụm DB production
Ngoài phạm vi hiện tại: Tài khoản ứng dụng; phải có risk/mapping liên quan riêng
~~~

Việc ghi rõ ngoài phạm vi giúp tránh diễn giải “đã kiểm soát tài khoản quản trị” thành “mọi truy cập cơ sở dữ liệu đã được kiểm soát”.

### 6.2. Các kiểm soát phối hợp

**C-PAM-001 — Cấp quyền tạm thời theo danh tính cá nhân.**

Người quản trị yêu cầu role phù hợp với tác vụ. Yêu cầu có lý do, target, phạm vi quyền và thời hạn. Quyền được phê duyệt theo chính sách và được thu hồi khi hết điều kiện.

Kiểm soát này giảm quyền thường trực và hỗ trợ quy trách nhiệm. Nó không tự chặn việc dùng một tài khoản local còn tồn tại ngoài quy trình.

**C-PAM-002 — Giới hạn đường quản trị đến target.**

Target và mạng chỉ cho phép các đường quản trị đã xác định, có xử lý riêng cho tình huống khẩn cấp. Cấu hình phải bao phủ các giao diện liên quan, bao gồm API, console hoặc kết nối quản trị khác nếu có.

Kiểm soát này làm giảm khả năng dùng credential từ một đường không được quản lý. Cần kiểm thử từ vị trí bị cấm và xác nhận cơ chế từ chối nằm ở lớp dự kiến.

**C-PAM-003 — Giới hạn quyền thực thi.**

Role chỉ có quyền cần cho tác vụ. Đọc log không đòi hỏi quyền sửa dữ liệu; kiểm tra trạng thái không mặc định cần quyền quản trị toàn bộ cụm.

JEA hoặc cơ chế tương đương có thể giới hạn thao tác ở nơi được hỗ trợ. Tuy nhiên, một chương trình hoặc lệnh được cho phép có thể chứa khả năng gọi thao tác khác; vì vậy chỉ giới hạn tên lệnh chưa chắc đã giới hạn được năng lực thực tế.

**C-PAM-004 — Quản lý vòng đời credential.**

Credential được lưu và cung cấp bằng cơ chế có kiểm soát; rotation được xác nhận tại target. Khi có nghi ngờ lộ lọt, quy trình xử lý xác định cả credential liên quan, phiên đang sống, bản sao và phụ thuộc ứng dụng.

Đổi password không nên được coi là bằng chứng rằng mọi phiên hoặc token đã phát hành đều mất hiệu lực. Cần kiểm tra semantics của từng target và cơ chế xác thực.

**C-PAM-005 — Phát hiện và xử lý truy cập không khớp.**

Đối soát target log với dữ liệu PAM và yêu cầu được duyệt. Sự kiện quản trị không tìm thấy căn cứ hợp lệ phải được điều tra. Dữ liệu cần có định danh đủ chính xác để phân biệt người dùng, tài khoản target, role, phiên và tác vụ tự động.

Kiểm soát phát hiện cần có owner nhận cảnh báo và thời hạn phản ứng. Một alert không ai xử lý chỉ là dữ liệu đã được tạo.

### 6.3. Giải thích quan hệ thay vì cộng số lượng

| Control | Điểm tác động | Điều kiện để có hiệu lực | Điều không thể kết luận riêng từ control |
|---|---|---|---|
| C-PAM-001 | Giảm thời gian và phạm vi quyền tồn tại | Cơ chế cấp/thu hồi đúng; không còn quyền thường trực ngoài policy | Mọi đường truy cập trực tiếp đã bị chặn |
| C-PAM-002 | Hạn chế đường dùng credential | Bao phủ đầy đủ đường quản trị; cấu hình target/mạng nhất quán | Người đi đúng đường không thể lạm dụng quyền |
| C-PAM-003 | Giảm năng lực thực hiện tác vụ gây hại | Role đúng với tác vụ; không có đường nâng quyền ngoài dự kiến | Dữ liệu bằng chứng đã đầy đủ |
| C-PAM-004 | Hạn chế tái sử dụng credential | Target đồng bộ thành công; xử lý đúng phiên/token và phụ thuộc | Người có phiên hợp lệ đã bị buộc ngắt |
| C-PAM-005 | Phát hiện hành động ngoài quy trình | Dữ liệu đầy đủ; đối soát đáng tin; có người phản ứng | Hành động đầu tiên đã được phòng ngừa |

Năm kiểm soát trên tạo thành một chuỗi phụ thuộc và bổ sung. Không có cơ sở để nói “mỗi control giảm 20%, vậy rủi ro bằng không”.

## 7. Kiểm thử ở ba mức: thiết kế, triển khai và vận hành

### 7.1. Hiệu lực thiết kế

Hỏi cơ chế dự kiến có giải quyết được kịch bản hay không.

Ví dụ: policy chỉ yêu cầu MFA khi vào cổng PAM, nhưng target vẫn chấp nhận credential trực tiếp từ mạng quản trị. Thiết kế hiện tại không xử lý đầy đủ đường sử dụng credential bị lộ, dù MFA tại cổng hoạt động đúng.

Các câu hỏi thiết kế:

- Có đường bypass nào nằm ngoài cơ chế?
- Điều gì xảy ra khi thành phần phụ thuộc mất kết nối?
- Ai có thể thay policy hoặc tự phê duyệt?
- Quyền hết hạn có làm mất quyền tại target và xử lý phiên như mong muốn không?
- Ngoại lệ nào mở lại điều kiện của risk?

### 7.2. Mức triển khai

Hỏi thiết kế đã được áp dụng cho phạm vi đã khai báo chưa.

Ví dụ: policy JIT đúng nhưng chỉ bao phủ 18 trong 20 cụm DB. Hai cụm còn lại vẫn có account quản trị thường trực.

Kết luận phù hợp là triển khai chưa đầy đủ; không phải “JIT hiệu quả trên toàn bộ cơ sở dữ liệu”. Cần ghi rõ hai cụm, độ nhạy cảm, owner và thời hạn xử lý.

### 7.3. Hiệu lực vận hành

Hỏi kiểm soát có hoạt động nhất quán trong kỳ quan sát không.

Một thủ tục kiểm thử JIT có thể gồm:

1. Xác định toàn bộ lần cấp quyền trong kỳ và nguồn dùng để đánh giá tính đầy đủ.
2. Kiểm tra các yêu cầu được duyệt, bị từ chối, hết hạn và các trường hợp lỗi.
3. Đối chiếu quyền được cấp với danh tính, target, scope và thời hạn đã duyệt.
4. Xác minh quyền bị thu hồi tại target; kiểm tra hành vi của phiên còn sống.
5. Kiểm tra thay đổi policy trong kỳ và tác động tới các lần cấp quyền.
6. Ghi nhận sai lệch, nguyên nhân, mức ảnh hưởng và hành động xử lý.

Không có một cỡ mẫu cố định phù hợp cho mọi kiểm soát. Chọn mẫu theo rủi ro, quy mô, tính tự động, mức biến động và phương pháp đánh giá của tổ chức. Nếu chỉ chọn các phiên thành công đẹp nhất, mẫu không hỗ trợ kết luận về toàn bộ kỳ.

### 7.4. Phép thử âm và dữ liệu không khớp

Phép thử âm giúp kiểm tra những gì hệ thống phải từ chối, chẳng hạn:

- Yêu cầu vượt quyền người dùng được phép xin.
- Yêu cầu hết cửa sổ hỗ trợ của vendor.
- Credential cũ sau rotation.
- Kết nối từ đường quản trị bị cấm.
- Quyền đã hết hạn nhưng phiên cũ vẫn cố thực hiện thao tác.

Thực hiện trong môi trường và cửa sổ đã được phép, với tác vụ không gây hại. Đối với kiểm soát bằng chứng, còn cần mô phỏng mất một nguồn log hoặc dữ liệu đến trễ để xác nhận hệ thống không tự kết luận “không có truy cập”.

## 8. Thiết kế bằng chứng có thể truy vết

### 8.1. Bằng chứng phải chứng minh điều đã tuyên bố

Một ảnh chụp cấu hình có thể hỗ trợ nhận định “tính năng đang bật tại thời điểm chụp”. Nó không tự chứng minh tính năng đã hoạt động liên tục trong ba tháng, bao phủ mọi target hoặc xử lý mọi ngoại lệ.

Tương tự:

- Ticket được duyệt không chứng minh quyền tại target đúng với ticket.
- Log cấp quyền không chứng minh quyền đã được thu hồi.
- Log rotation thành công không tự chứng minh credential cũ bị target từ chối.
- Session recording không chứng minh các phiên ngoài PAM cũng được ghi.
- Chính sách lưu trữ không chứng minh log đã được gửi đủ vào kho.

Một evidence package cần kết hợp cấu hình, sự kiện vận hành và kết quả kiểm thử phù hợp với mục tiêu.

### 8.2. Chuỗi định danh tối thiểu

Với một lần truy cập đặc quyền, có thể cần nối:

~~~text
Danh tính người hoặc workload
    ↔ Yêu cầu/ticket và người phê duyệt
    ↔ Grant ID cùng phiên bản policy
    ↔ Tài khoản/role tại target
    ↔ Session ID hoặc operation ID
    ↔ Sự kiện tại target
    ↔ Sự kiện thu hồi/rotation và kết quả xác minh
~~~

Không phải target nào cũng có cùng các trường dữ liệu. Khi không thể join trực tiếp, cần nêu phương pháp tương quan, độ tin cậy và giới hạn; không gán một sự kiện cho một người chỉ vì thời gian gần nhau.

Các metadata hữu ích gồm phạm vi, kỳ bằng chứng, múi giờ, thời điểm trích xuất, nguồn, người thu thập, truy vấn hoặc bộ lọc, phiên bản control và nơi lưu bằng chứng. Đồng bộ thời gian và chuẩn hóa thời điểm giúp tránh kết luận sai về thứ tự phê duyệt, cấp quyền và truy cập.

### 8.3. Độ đầy đủ của population

Nếu lấy danh sách phiên từ PAM làm tổng số truy cập, bạn có thể không thấy phiên bypass. Để đánh giá coverage, cần đối soát với nguồn độc lập phù hợp như inventory, cấu hình quyền tại target hoặc audit event của target.

Ví dụ:

~~~text
PAM ghi nhận 950 phiên có approval.
Target ghi nhận thêm 30 lần kết nối quản trị không tương quan được.

Chưa thể kết luận coverage = 100%.
Cần phân loại 30 lần kết nối: bypass, job tự động, lỗi join,
chênh lệch thời gian, sự kiện trùng hoặc đường khẩn cấp.
~~~

Khi nguồn độc lập cũng chưa đầy đủ, kết luận phải phản ánh mức không chắc chắn. “Không tìm thấy sai lệch trong dữ liệu hiện có” khác với “đã chứng minh không có bypass”.

### 8.4. Bảo vệ bằng chứng

Bằng chứng PAM thường chứa tên tài khoản, target nhạy cảm và nội dung thao tác. Chỉ lưu dữ liệu cần thiết; không đưa password, token hoặc private key vào hồ sơ mapping. Dùng ID hoặc tham chiếu tới nguồn được kiểm soát quyền truy cập.

Hash giúp phát hiện thay đổi của một file sau thời điểm tính hash nếu giá trị hash được bảo vệ đáng tin cậy. Hash tự nó không chứng minh ai tạo file, nguồn có đầy đủ hay dữ liệu ban đầu đúng.

Thời hạn lưu, quyền truy cập và cơ chế bảo vệ cần gắn với chính sách và nghĩa vụ áp dụng cho tổ chức. Không tự coi một con số retention minh họa là yêu cầu chung cho mọi hệ thống.

## 9. Đánh giá coverage và rủi ro còn lại

### 9.1. Coverage phải có mẫu số

Một chỉ số đơn giản:

~~~text
Coverage JIT =
    số tài khoản/role trong phạm vi đã được xác minh dùng JIT
    / tổng số tài khoản/role thuộc phạm vi yêu cầu JIT
~~~

Cần công bố đơn vị tính. Đếm account, role, target và session tạo ra các chỉ số khác nhau; không dùng lẫn mà vẫn giữ cùng một tên.

Ví dụ, 96 trên 100 tài khoản đã dùng JIT tương đương coverage theo số lượng là 96%. Nhưng nếu bốn tài khoản còn lại có quyền quản trị hệ thống định danh và vault, 4% chưa bao phủ có thể chi phối phần lớn mức rủi ro.

Nếu dùng trọng số theo độ nhạy cảm, phải mô tả cách đặt trọng số và giới hạn của mô hình. Coverage cao không thay thế đánh giá đường tấn công cụ thể.

### 9.2. Tách coverage khỏi effectiveness

| Tình huống | Coverage | Hiệu lực | Cách diễn giải |
|---|---|---|---|
| Policy đúng, chỉ áp dụng một nửa target | Thấp | Có thể tốt trong phần đã áp dụng | Cần mở rộng triển khai và đánh giá phần chưa bao phủ |
| Policy áp dụng toàn bộ nhưng thu hồi quyền lỗi | Cao theo cấu hình | Không đạt mục tiêu vận hành | Cần xử lý cơ chế thu hồi và ảnh hưởng của các grant tồn đọng |
| Ghi hình mọi phiên qua broker nhưng có bypass | Chưa đủ cơ sở cho toàn phạm vi | Chỉ chứng minh trên đường broker | Cần inventory đường truy cập và đối soát nguồn độc lập |
| Không có dữ liệu kỳ hiện tại | Không rõ | Chưa kết luận | Cần thu thập bằng chứng; không gắn nhãn hiệu quả mặc định |

Có thể dùng trạng thái riêng như “đã thiết kế”, “triển khai một phần”, “chưa đủ bằng chứng”, “vận hành đạt” và “vận hành không đạt”. Không ép mọi tình huống thành một ô xanh hoặc đỏ làm mất thông tin.

### 9.3. Ví dụ chấm điểm định tính

Giả sử tổ chức dùng thang khả năng và tác động từ 1 đến 5, cùng ma trận phân loại đã thống nhất. Với R-PAM-001:

- Trước khi xét các kiểm soát đang đánh giá: khả năng 4, tác động 5.
- Sau khi xác minh JIT, giới hạn đường truy cập và đối soát vận hành: khả năng có thể giảm xuống 2 theo tiêu chí của tổ chức.
- Tác động vẫn là 5 nếu một lần truy cập thành công vẫn có thể sửa dữ liệu quan trọng.
- Hai target ngoại lệ có thể cần đánh giá riêng và quyết định mức tổng hợp thận trọng.

Nếu tổ chức dùng tích số, 4 × 5 = 20 và 2 × 5 = 10 là điểm theo quy ước, không phải xác suất hoặc tổn thất kỳ vọng. Không diễn giải điểm giảm một nửa thành tổn thất thực tế chắc chắn giảm 50%.

Cần ghi căn cứ cho thay đổi mức khả năng. Chỉ nói “đã bật PAM” không đủ để hỗ trợ kết luận.

### 9.4. Rủi ro của chính kiểm soát

Kiểm soát cũng có thể tạo phụ thuộc hoặc nguy cơ mới:

- Vault lỗi có thể ảnh hưởng khả năng quản trị hoặc rotation.
- Rotation sai có thể làm ứng dụng mất kết nối.
- Cấp quyền quá chặt nhưng không có quy trình khẩn cấp có thể kéo dài sự cố.
- Kho ghi hình tập trung có thể trở thành nguồn lộ dữ liệu nhạy cảm.
- Một role quản trị PAM quá mạnh có thể làm suy yếu nhiều control cùng lúc.

Mapping nên ghi nhận các phụ thuộc và liên kết tới kịch bản liên quan, thay vì coi control luôn chỉ tạo lợi ích.

## 10. Ngoại lệ và kiểm soát bù đắp

Một target cũ chưa hỗ trợ cơ chế credential ngắn hạn. Nhóm vận hành đề xuất giữ tài khoản dài hạn trong một thời gian chuyển đổi.

Hồ sơ ngoại lệ cần làm rõ:

- Target, account, quyền và đường truy cập được ngoại lệ.
- Risk và control nào bị ảnh hưởng.
- Lý do chưa áp dụng được kiểm soát dự kiến.
- Biện pháp tạm thời và cơ chế giảm rủi ro của từng biện pháp.
- Bằng chứng, owner, người chấp nhận rủi ro theo thẩm quyền.
- Thời điểm hết hạn, kế hoạch khắc phục và tiêu chí đóng ngoại lệ.

Ví dụ biện pháp bù đắp có thể gồm giới hạn nguồn mạng, yêu cầu truy cập có phê duyệt, bảo vệ credential, giám sát target độc lập và kiểm tra sau phiên. Tuy nhiên, cần đánh giá lại liệu credential có thể được sử dụng ngoài đường được theo dõi hay không.

Không đổi trạng thái control gốc thành “đạt” chỉ vì ngoại lệ đã được ký. Có thể ghi:

~~~text
Control gốc: Triển khai một phần
Ngoại lệ: EX-PAM-014, còn hiệu lực đến mốc đã duyệt
Bù đắp: C-PAM-021 và C-PAM-022
Rủi ro còn lại: Được risk owner chấp nhận trong phạm vi và thời hạn cụ thể
Điều kiện: Có giám sát; không mở thêm account; theo dõi kế hoạch chuyển đổi
~~~

Khi ngoại lệ hết hạn, không tự gia hạn im lặng. Cần đánh giá lại trạng thái, hiệu lực biện pháp tạm thời và thẩm quyền quyết định.

## 11. Mẫu hồ sơ mapping có cấu trúc

Ví dụ YAML dưới đây minh họa nội dung một hồ sơ GRC hoặc control register. Đây là mẫu học tập trong bài, không phải schema bắt buộc của công cụ PAM hay metadata bài học.

~~~yaml
mappingId: M-PAM-001
version: 1
scope:
  environment: production
  assetGroup: payment-database
  identityType: human-admin
  accessPaths:
    - pam-broker
    - emergency-access
  exclusions:
    - scope: application-service-accounts
      reason: tracked-in-separate-risk-record
risk:
  id: R-PAM-001
  statement: >
    Credential quản trị bị lộ có thể được dùng để thay đổi
    dữ liệu thanh toán trái phép qua đường truy cập chưa kiểm soát.
  ownerRole: payment-service-owner
  consequence:
    - unauthorized-data-change
    - service-disruption
    - insufficient-attribution
controlLinks:
  - controlId: C-PAM-001
    relationship: direct
    mechanism: >
      Cấp role theo danh tính cá nhân, đúng tác vụ và có thời hạn
      để giảm quyền thường trực.
    controlOwnerRole: privileged-access-owner
    implementationState: partial
    operatingEffectiveness: not-concluded
    dependencies:
      - identity-provider
      - target-role-provisioning
    tests:
      - T-PAM-001
    evidenceRefs:
      - E-PAM-001
    exceptionRefs:
      - EX-PAM-014
  - controlId: C-PAM-005
    relationship: direct
    mechanism: >
      Đối soát sự kiện quản trị tại target với grant và phiên PAM
      để phát hiện truy cập không có căn cứ hợp lệ.
    controlOwnerRole: security-monitoring-owner
    implementationState: implemented
    operatingEffectiveness: not-concluded
    dependencies:
      - target-audit-events
      - time-synchronization
      - event-correlation
    tests:
      - T-PAM-005
    evidenceRefs:
      - E-PAM-005
    exceptionRefs: []
assessment:
  period: defined-in-assessment-record
  evidenceCompleteness: pending-validation
  residualRiskStatus: not-concluded
  rationale: >
    Chưa hạ mức rủi ro khi còn target ngoại lệ và chưa hoàn tất
    xác minh độ đầy đủ của dữ liệu đối soát.
review:
  accountableRole: payment-service-owner
  triggers:
    - new-privileged-access-path
    - control-failure
    - material-policy-change
    - exception-expiry
~~~

Điểm đáng chú ý là hồ sơ phân biệt phạm vi triển khai, hiệu lực vận hành và quyết định rủi ro. Trạng thái “implemented” không tự làm “operatingEffectiveness” thành “effective”.

Trong hệ thống thực tế, có thể tách risk, control, mapping, test và evidence thành các đối tượng riêng. Khi cập nhật một control dùng chung, phải xác định những mapping nào cần đánh giá lại.

## 12. Mapping với yêu cầu compliance

Yêu cầu tuân thủ và risk có quan hệ nhưng không đồng nhất:

~~~text
Yêu cầu áp dụng
    → Mục tiêu cần đáp ứng
    → Kiểm soát được thiết kế
    → Kịch bản rủi ro được xử lý
    → Kiểm thử, bằng chứng và kết luận trong phạm vi
~~~

Một yêu cầu có thể liên quan nhiều kiểm soát; một kiểm soát có thể hỗ trợ nhiều yêu cầu. Tuy nhiên, không nên suy luận:

> Control C hỗ trợ yêu cầu A; yêu cầu A giống yêu cầu B; vậy C chắc chắn đáp ứng B.

Cần đối chiếu nội dung, phạm vi, đối tượng, kỳ đánh giá và tiêu chí bằng chứng của từng yêu cầu. Khi ghi mã tham chiếu, lưu đúng phiên bản và xác nhận tính áp dụng với bộ phận phụ trách. Bài này không gán mã điều khoản cụ thể vì mục tiêu là phương pháp mapping, không diễn giải một bộ yêu cầu riêng.

Cũng cần tránh suy luận ngược: đáp ứng một yêu cầu được kiểm tra không có nghĩa mọi risk của tài sản đã được xử lý. Chẳng hạn, có log đầy đủ vẫn chưa ngăn một role production được cấp quá rộng.

## 13. Duy trì mapping trong vòng đời hệ thống

Mapping dễ trở nên lỗi thời khi kiến trúc hoặc cách sử dụng quyền thay đổi. Các sự kiện cần kích hoạt rà soát gồm:

- Thêm target, tài khoản đặc quyền hoặc đường quản trị mới.
- Chuyển từ đăng nhập tương tác sang API hoặc workload identity.
- Thay policy, phiên bản tích hợp hoặc semantics thu hồi quyền.
- Phát hiện bypass, lỗi rotation, mất log hoặc hành vi lạm dụng.
- Thay owner, hợp đồng vendor, phân loại dữ liệu hoặc độ nhạy cảm tài sản.
- Gia hạn hay hết hạn ngoại lệ.
- Diễn tập khôi phục cho thấy kiểm soát phụ thuộc không hoạt động như dự kiến.

Một vòng rà soát thực tế có thể diễn ra như sau:

1. Chủ sở hữu thay đổi khai báo phạm vi và đường truy cập bị ảnh hưởng.
2. Control owner xác định các control và mapping liên quan.
3. Đánh giá thiết kế mới, kiểm tra triển khai và thu thập bằng chứng phù hợp.
4. Cập nhật kết luận hiệu lực và rủi ro còn lại.
5. Risk owner quyết định xử lý phần còn lại theo thẩm quyền.
6. Lưu phiên bản, căn cứ thay đổi và mốc rà soát tiếp theo.

Không sửa mapping cũ để trông như kiểm soát đã tồn tại trong quá khứ. Bằng chứng và kết luận của từng kỳ phải phản ánh trạng thái thực tế của kỳ đó.

### Chỉ số theo dõi có ý nghĩa

Có thể theo dõi tỷ lệ risk quan trọng có control owner, tỷ lệ mapping có kiểm thử và bằng chứng còn phù hợp, số ngoại lệ quá hạn, số grant không thu hồi đúng điều kiện, số sự kiện quản trị chưa tương quan và thời gian xử lý sai lệch.

Các chỉ số cần được đọc cùng phạm vi và mức độ nghiêm trọng. Số mapping tăng không tự chứng minh risk giảm; số cảnh báo giảm cũng có thể do nguồn log bị mất.

## 14. Những lỗi mapping thường gặp

| Lỗi | Vì sao kết luận yếu | Cách sửa |
|---|---|---|
| Map một tên sản phẩm vào mọi risk | Không mô tả cơ chế hoặc phạm vi | Tách thành hoạt động kiểm soát có owner và kiểm thử |
| Dùng “có MFA” để đóng risk quyền quá rộng | Xác thực không tự giới hạn quyền hợp lệ | Map thêm cơ chế phân quyền, JIT/JEA và review quyền |
| Dùng recording làm kiểm soát phòng ngừa mặc định | Ghi lại không đồng nghĩa ngăn hành động | Phân loại vai trò và bổ sung khả năng phản ứng |
| Chỉ lấy dữ liệu từ PAM để kết luận không có bypass | Nguồn không nhìn thấy đường ngoài PAM | Đối soát inventory, cấu hình và target telemetry phù hợp |
| Cộng phần trăm giảm risk của từng control | Bỏ qua phụ thuộc và quan hệ chồng lấn | Phân tích kịch bản và căn cứ đánh giá |
| Chấp nhận ngoại lệ rồi đổi control thành đạt | Che khuất phần chưa triển khai | Ghi riêng ngoại lệ, bù đắp và rủi ro được chấp nhận |
| Có policy nhưng không có dữ liệu vận hành | Chưa chứng minh hoạt động trong kỳ | Thiết kế evidence package và thủ tục kiểm thử |
| Một người tự thay policy và tự chứng nhận | Dễ bỏ sót xung đột hoặc lựa chọn bằng chứng có lợi | Tạo cơ chế phê duyệt/rà soát độc lập phù hợp |
| Kết luận đạt khi dữ liệu thiếu | Nhầm thiếu quan sát với không có sai lệch | Ghi “chưa đủ bằng chứng” và xử lý thiếu dữ liệu |

## 15. Bài thực hành: tìm khoảng trống trong một mapping

### Đề bài

Một hệ thống có các đặc điểm:

- Quản trị viên vào cổng PAM bằng MFA.
- PAM ghi hình các phiên SSH đi qua broker.
- Tài khoản local trên máy chủ vẫn có password dài hạn.
- Vendor có account riêng nhưng chưa đặt ngày hết hạn.
- Mạng quản trị cho phép SSH trực tiếp từ một số máy hỗ trợ.
- Nhóm vận hành kết luận: “MFA và recording đã xử lý risk truy cập trái phép của vendor”.

Hãy trả lời:

1. Viết lại risk statement đủ cụ thể.
2. Chỉ ra điều kiện nào chưa được hai kiểm soát hiện tại xử lý.
3. Đề xuất một nhóm kiểm soát và lý do mapping từng kiểm soát.
4. Chọn bằng chứng để kiểm tra khả năng vendor truy cập sau khi hết hỗ trợ.
5. Nêu phần rủi ro còn lại nếu chưa thể đóng đường SSH trực tiếp.

### Gợi ý lời giải

Risk statement có thể là:

> Do account vendor không gắn ngày hết hạn và còn đường SSH trực tiếp dùng password dài hạn, người từng được cấp quyền hỗ trợ có thể tiếp tục đăng nhập đặc quyền vào máy chủ production sau khi hết nhu cầu, dẫn đến thay đổi trái phép hoặc lộ dữ liệu.

MFA ở cổng PAM không xử lý việc account vẫn hợp lệ sau khi hết nhu cầu, và không bao phủ đường SSH trực tiếp nếu đường đó không đi qua cơ chế xác thực tương ứng. Recording của broker cũng không chứng minh đường trực tiếp được ghi lại.

Nhóm kiểm soát có thể gồm:

- Gắn owner/sponsor và thời hạn truy cập với yêu cầu hỗ trợ.
- Thu hồi account, quyền và credential theo sự kiện hết hạn.
- Giới hạn đường SSH trực tiếp hoặc đặt đường đó trong phạm vi kiểm soát rõ ràng.
- Cấp quyền tối thiểu theo tác vụ và cửa sổ được duyệt.
- Đối soát target log để phát hiện sự kiện không có căn cứ hỗ trợ hợp lệ.
- Kiểm tra rotation và xử lý phiên còn sống khi chấm dứt truy cập.

Bằng chứng cần nối được yêu cầu hỗ trợ, thời hạn được duyệt, account tại target, thời điểm thu hồi, kết quả thử từ chối truy cập và trạng thái phiên liên quan. Nên xác minh inventory account để tránh bỏ sót account local thứ hai.

Nếu chưa đóng đường trực tiếp, phải ghi ngoại lệ theo đúng máy nguồn, target, account và thời hạn. Tăng giám sát không làm mất hoàn toàn khả năng hành động trái phép trước khi được phát hiện. Risk owner cần thấy giới hạn đó khi quyết định.

## 16. Kết quả đầu ra mong đợi

Một mapping PAM đủ dùng cho quản trị và kiểm toán phải cho người khác đi hết chuỗi:

> Risk cụ thể → điều kiện gây risk → control tác động vào điều kiện đó → phạm vi triển khai → kiểm thử và bằng chứng → kết luận hiệu lực → rủi ro còn lại.

Khi đọc một dòng mapping, hãy tự kiểm tra ba câu hỏi:

1. Nếu control thất bại, kịch bản bất lợi nào trở nên khả thi hơn?
2. Bằng chứng nào có thể khiến mình thay đổi kết luận rằng control đang hiệu quả?
3. Phần nào của risk vẫn tồn tại dù control hoạt động đúng?

Nếu ba câu trả lời còn mơ hồ, mapping cần thêm thông tin trước khi dùng để quyết định mức rủi ro hoặc tuyên bố mức đáp ứng yêu cầu.
