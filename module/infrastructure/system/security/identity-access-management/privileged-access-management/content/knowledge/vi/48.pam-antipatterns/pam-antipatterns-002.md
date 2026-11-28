# Dùng root cho tác vụ thường

## 1. Anti-pattern: lấy quyền cao nhất làm điểm xuất phát

Một kỹ sư đăng nhập máy chủ bằng `root`, mở terminal rồi lần lượt xem log, kiểm tra dung lượng, tìm tiến trình và sửa một tệp cấu hình. Chỉ thao tác cuối có thể cần đặc quyền, nhưng toàn bộ phiên đã chạy với quyền cao nhất. Khi cách làm này trở thành thói quen, doanh nghiệp không còn cấp quyền theo nhu cầu của tác vụ; doanh nghiệp đang trao một môi trường quản trị toàn quyền và trông chờ người dùng tự giới hạn hành vi.

Trong Linux, `root` thường là tài khoản có UID 0. Trong ngữ cảnh thông thường của máy chủ, tiến trình chạy với UID 0 có khả năng quản trị rất rộng. Các cơ chế như namespace, capabilities và kiểm soát truy cập bắt buộc có thể giới hạn một phần quyền lực đó, nhưng không nên mặc định rằng mọi phiên root đều đã được cô lập an toàn. Phải đánh giá quyền thực tế trên đúng môi trường.

Anti-pattern của bài này là **dùng root hoặc quyền tương đương cho công việc vốn chỉ cần quyền người dùng, quyền đọc giới hạn hoặc một thao tác quản trị hẹp**. Một tài khoản tên `operator` nhưng có thể chạy mọi lệnh qua `sudo` vẫn thuộc phạm vi rủi ro này. Ngược lại, một thao tác thật sự cần đặc quyền và được cấp đúng phạm vi, đúng thời gian không tự động là anti-pattern.

Trong quản lý truy cập đặc quyền, hay PAM, mục tiêu không phải làm cho tài khoản root biến mất. Mục tiêu là kiểm soát ai có thể sử dụng quyền đó, phục vụ tác vụ nào, trong bao lâu, với những giới hạn và bằng chứng gì.

## 2. Nhận diện quyền cần thiết trước khi chọn tài khoản

### 2.1. Phân loại tác vụ thay vì phân loại con người

Một người thuộc đội vận hành không có nghĩa mọi hành động của họ đều cần quyền quản trị. Cùng một kỹ sư có thể thực hiện nhiều loại việc trong một ca trực:

| Tác vụ | Điểm xuất phát phù hợp | Khi nào cần xem xét nâng quyền? |
|---|---|---|
| Xem danh tính và nhóm của chính mình | Tài khoản cá nhân thông thường | Không cần chỉ để chạy `id` |
| Kiểm tra dung lượng filesystem đã được phép truy cập | Công cụ đọc thông thường | Khi truy cập một vùng bị giới hạn và có nhu cầu được duyệt |
| Xem log ứng dụng | Hệ thống log tập trung hoặc quyền đọc đúng nguồn | Khi log thuộc vùng đặc quyền và chưa có kênh đọc an toàn |
| Xem trạng thái ứng dụng | Dashboard hoặc công cụ kiểm tra được cấp quyền | Khi endpoint quản trị yêu cầu một quyền bổ sung cụ thể |
| Khởi động lại một dịch vụ hệ thống | Quyền thao tác với đúng dịch vụ | Khi tác vụ đã được xác nhận cần thiết |
| Sửa cấu hình hệ điều hành | Luồng thay đổi có kiểm soát | Cần quyền ghi trên đúng tài nguyên, kèm kiểm chứng thay đổi |
| Chạy ứng dụng phục vụ yêu cầu người dùng | Tài khoản dịch vụ riêng | Chỉ phần khởi tạo thật sự cần đặc quyền, nếu có |

Phân loại này cũng áp dụng cho tài khoản dịch vụ. Một job đọc báo cáo không nên chạy dưới root chỉ vì thư mục báo cáo ban đầu thuộc root. Có thể cần sửa thiết kế quyền của dữ liệu thay vì tăng quyền cho toàn bộ job.

### 2.2. Bốn câu hỏi cho mỗi lần nâng quyền

Trước khi cấp đặc quyền, cần trả lời được:

1. Tác vụ cụ thể nào không thể hoàn thành bằng quyền hiện tại?
2. Tài nguyên hoặc thao tác tối thiểu nào cần được cho phép?
3. Quyền đó cần trong khoảng thời gian nào và trên những hệ thống nào?
4. Bằng chứng nào chứng minh đúng người đã thực hiện đúng tác vụ và quyền đã kết thúc?

Câu trả lời “để tiện xử lý mọi thứ nếu phát sinh” là tín hiệu quyền đang được cấp rộng hơn nhu cầu đã biết. Có thể tồn tại nhu cầu ứng cứu chưa dự đoán được, nhưng phải đưa nó vào luồng khẩn cấp riêng thay vì dùng làm lý do duy trì root thường trực.

## 3. Vì sao thói quen dùng root hình thành?

### 3.1. Quyền toàn cục che khuất thiết kế quyền kém

Khi đội vận hành liên tục gặp lỗi quyền truy cập log hoặc thư mục làm việc, giải pháp nhanh thường là chuyển sang root. Tác vụ hoàn thành ngay, nên nguyên nhân gốc như thiếu nhóm đọc log, ownership sai hoặc công cụ quản trị chưa phân quyền tiếp tục tồn tại.

Về lâu dài, người dùng không còn biết việc nào thật sự cần root. Runbook cũng bắt đầu bằng “đăng nhập root”, làm cho quyền cao nhất trở thành điều kiện mặc định của cả quy trình.

### 3.2. Runbook và automation kế thừa môi trường quản trị

Một script được viết và thử trong root shell có thể vô tình phụ thuộc vào thư mục, biến môi trường và quyền ghi chỉ root mới có. Khi đưa vào lịch chạy, đội vận hành giữ nguyên tài khoản root để tránh lỗi. Sau nhiều lần sửa, script có thể xử lý dữ liệu bên ngoài, gọi chương trình phụ hoặc sử dụng thư mục tạm mà chưa từng được đánh giá dưới góc độ đặc quyền.

### 3.3. Nhầm xác thực mạnh với quyền hạn phù hợp

MFA và vault giúp bảo vệ bước truy cập, nhưng không trả lời liệu người dùng có cần mọi quyền sau khi đăng nhập hay không. Một phiên root qua MFA vẫn là phiên root. Một mật khẩu root được luân chuyển thường xuyên vẫn có thể cấp phạm vi quá rộng nếu được lấy ra cho mọi tác vụ đọc log.

PAM phải kết hợp bảo vệ credential với giảm đặc quyền, giới hạn phiên, kiểm soát thời gian và thu thập bằng chứng. Triển khai vault đơn lẻ không tự sửa anti-pattern này.

## 4. Cơ chế làm tăng rủi ro

### 4.1. Mở rộng hậu quả của lỗi thao tác

Một lệnh chạy dưới tài khoản thông thường thường bị giới hạn bởi quyền của tài khoản đó. Cùng lỗi đường dẫn hoặc biến rỗng trong root shell có thể tác động tới cấu hình hệ thống, dữ liệu của nhiều ứng dụng hoặc cơ chế khởi động dịch vụ.

Không nên dùng khả năng “người vận hành sẽ cẩn thận” làm hàng rào chính. Giới hạn quyền giúp giảm hậu quả ngay cả khi con người hoặc script có lỗi.

### 4.2. Biến dữ liệu không tin cậy thành đầu vào của tiến trình đặc quyền

Đọc log, giải nén tệp, mở tài liệu và chạy công cụ hỗ trợ đều có thể xử lý dữ liệu từ nguồn khác. Nếu công cụ gặp lỗ hổng hoặc thực hiện hành vi ngoài dự kiến, quyền của tiến trình quyết định phạm vi hậu quả.

Một công cụ kiểm tra được chạy bằng root không chỉ có quyền đọc dữ liệu cần kiểm tra. Tùy môi trường, nó có thể đọc credential, sửa cấu hình hoặc ảnh hưởng tới tiến trình khác. Vì vậy, cả các tác vụ được gọi là “chỉ xem” cũng cần được xem xét trong ngữ cảnh thực thi cụ thể.

### 4.3. Tăng cơ hội đánh cắp và sử dụng quyền

Nếu tài khoản cá nhân luôn mở được root shell, kẻ chiếm được phiên của tài khoản có một đường ngắn tới đặc quyền. Nếu một ứng dụng thường xuyên chạy bằng root, việc khai thác ứng dụng có thể mang lại quyền hệ thống ngay trong tiến trình bị khai thác.

Đưa mật khẩu vào vault không thu hẹp quyền của một root shell đã được mở. Luân chuyển mật khẩu cũng không nên được coi là biện pháp tự động đóng mọi phiên hoặc vô hiệu hóa mọi cơ chế truy cập khác như khóa SSH và token.

### 4.4. Làm suy yếu khả năng quy trách nhiệm

Tài khoản root dùng chung làm mất liên kết trực tiếp giữa danh tính con người và tài khoản trên máy đích. Có thể khôi phục một phần liên kết bằng gateway, log xác thực và bản ghi phiên, nhưng cần chứng minh được tính liên tục của chuỗi bằng chứng đó.

Ngay cả với `sudo`, cần phân biệt hai tình huống:

- Nâng quyền cho một lệnh cụ thể: sự kiện có thể thể hiện rõ lệnh đã được yêu cầu.
- Nâng quyền thành shell toàn quyền: sự kiện ban đầu chủ yếu cho biết shell được mở; muốn biết các thao tác bên trong cần thêm cơ chế ghi nhận phù hợp.

Shell history có thể thiếu, bị tắt hoặc bị sửa; không phải nguồn bằng chứng duy nhất đáng tin cậy. Người có quyền root rộng cũng có khả năng tác động tới nhiều nguồn log cục bộ. Cần chuyển bằng chứng ra hệ thống khác với quyền quản trị được tách biệt.

## 5. Những biến thể trông có vẻ an toàn nhưng vẫn quá rộng

| Cách triển khai | Khoảng trống còn lại | Hướng xử lý |
|---|---|---|
| Đổi tên tài khoản root hoặc tạo tài khoản khác có UID 0 | Quyền hiệu lực vẫn rất lớn | Kiểm kê UID và khả năng thực thi, không chỉ tên tài khoản |
| Dùng tài khoản cá nhân rồi mở `sudo -i` cho cả ca trực | Đã có điểm vào cá nhân nhưng toàn bộ phiên vẫn toàn quyền | Nâng quyền theo thao tác; root shell dùng cho trường hợp có lý do riêng |
| Cho phép `sudo` mọi lệnh, yêu cầu nhập mật khẩu | Xác thực không thu hẹp tập thao tác được phép | Áp dụng chính sách quyền có phạm vi và thời hạn |
| Chỉ cho phép một trình soạn thảo chạy bằng root | Công cụ có thể ghi tệp tùy ý hoặc mở shell | Dùng luồng chỉnh sửa kiểm soát đúng tệp và kiểm tra khả năng thoát phạm vi |
| Cho phép một script nhưng người dùng sửa được script đó | Người dùng có thể thay nội dung được chạy bằng root | Bảo vệ script, thư mục cha, phụ thuộc và cấu hình |
| Chỉ ghi hình phiên root | Có bằng chứng để xem lại nhưng quyền vẫn quá rộng | Kết hợp kiểm soát trước thao tác với phát hiện và điều tra |
| Cấp quyền quản trị ngắn hạn nhưng không xử lý phiên đang mở | Hết hạn cấp mới chưa chắc kết thúc quyền đang dùng | Xác định hành vi thu hồi với phiên, tiến trình và credential |
| Chuyển job sang container chạy root rồi coi như đã hết rủi ro | Quyền còn phụ thuộc cấu hình container, capability và host mount | Đánh giá quyền thực tế trong container lẫn tác động lên host |

Một số quyền khác cũng có thể dẫn tới quyền quản trị rất rộng: truy cập socket quản trị container engine, sửa chương trình được dịch vụ đặc quyền gọi, hoặc quản lý một control plane mạnh. Không nên khẳng định đã loại bỏ root chỉ dựa vào việc người dùng không còn đăng nhập bằng tên `root`.

## 6. Thiết kế thay thế: đặc quyền xuất phát từ tác vụ

### 6.1. Dùng danh tính cá nhân và tách tài khoản dịch vụ

Con người đăng nhập bằng danh tính cá nhân có thể truy vết. Ứng dụng và job có danh tính dịch vụ riêng với chủ sở hữu rõ ràng. Tài khoản ứng dụng không được dùng làm tài khoản đăng nhập tiện lợi cho cả nhóm.

Việc tách danh tính giúp phân biệt:

- Ai yêu cầu thao tác.
- Chính sách nào đã cho phép thao tác.
- Tiến trình hoặc tài khoản đích nào thực hiện thao tác.
- Dữ liệu và tài nguyên nào nằm trong phạm vi quyền đó.

Danh tính cá nhân là nền tảng quy trách nhiệm, nhưng vẫn phải giới hạn quyền hiệu lực của danh tính ấy.

### 6.2. Tạo kênh quan sát không cần root

Đội vận hành thường dùng root để tìm thông tin. Trước khi thiết kế cơ chế nâng quyền, hãy cung cấp dashboard, log tập trung, quyền đọc đúng nguồn và lệnh kiểm tra thông thường.

Ví dụ các lệnh dưới đây có thể được chạy trong phiên người dùng thông thường để kiểm tra thông tin cơ bản. Kết quả cụ thể phụ thuộc quyền và cấu hình máy:

```sh
id
df -h
ps -u "$(id -un)" -o pid,comm,etime
```

Không tự động thêm `sudo` khi một lệnh đọc thất bại. Trước hết xác định dữ liệu cần xem và quyền đọc tối thiểu tương ứng. Việc thêm người dùng vào một nhóm đọc mọi log cũng có thể làm lộ dữ liệu nhạy cảm; “read-only” không đồng nghĩa dữ liệu nào cũng được phép đọc.

### 6.3. Kết hợp least privilege, JEA và JIT

Ba ý tưởng bổ trợ cho nhau:

- **Least privilege:** chỉ có quyền cần thiết cho công việc đã xác định.
- **JEA, Just Enough Administration:** chỉ cho thực hiện các chức năng quản trị cần thiết, bằng cơ chế phù hợp với nền tảng. Trên Linux có thể thiết kế các lệnh hoặc endpoint hẹp; không mặc định mọi nền tảng dùng cùng một sản phẩm JEA.
- **JIT, Just In Time:** chỉ cấp quyền trong khoảng thời gian có nhu cầu được chấp thuận, thay vì giữ quyền thường trực.

Cấp toàn quyền root trong 15 phút có thể giảm thời gian phơi lộ, nhưng phạm vi trong 15 phút vẫn rất rộng. Cho phép một thao tác hẹp thường trực có thể giảm phạm vi, nhưng vẫn để lại đường đặc quyền tồn tại lâu dài. Thiết kế phù hợp thường cần xét cả phạm vi lẫn thời gian, không dùng một chiều để thay thế chiều còn lại.

### 6.4. Minh họa quyền khởi động lại đúng một dịch vụ

Giả sử đội trực chỉ cần khởi động lại `payments-api.service` sau một bước chẩn đoán. Trên một máy Linux dùng systemd và sudo, một mảnh chính sách minh họa có thể là:

```sudoers
Cmnd_Alias PAYMENTS_RESTART = /usr/bin/systemctl restart payments-api.service
%payments-ops ALL=(root) PAYMENTS_RESTART
```

Ví dụ này chỉ minh họa ý tưởng khớp lệnh và đối số cụ thể. Trước khi triển khai phải xác minh đường dẫn chương trình, cú pháp được hỗ trợ, chính sách sudo tổng thể và phạm vi host trong môi trường thật. Dùng `visudo` để sửa hoặc kiểm tra cấu hình theo quy trình quản trị của hệ thống; không sao chép mảnh cấu hình vào production mà bỏ qua kiểm thử.

Người được cấp quyền yêu cầu đúng thao tác:

```sh
sudo /usr/bin/systemctl restart payments-api.service
```

Các điều kiện quan trọng nằm cả ngoài dòng sudoers:

1. Người dùng không sửa được binary, unit, drop-in, chương trình khởi động hoặc cấu hình khiến dịch vụ đặc quyền chạy mã tùy ý.
2. Mọi thư mục và phụ thuộc ảnh hưởng tới đường thực thi được bảo vệ phù hợp; chỉ bảo vệ tệp cuối cùng là chưa đủ.
3. Có kiểm soát đối với quyền khởi động lại dịch vụ khác, shell, editor và công cụ có khả năng vượt phạm vi.
4. Quyền từ các rule khác, nhóm khác hoặc cơ chế khác không vô tình cấp lại toàn quyền.
5. Tác động vận hành của restart được chấp nhận; một thao tác có phạm vi hẹp vẫn có thể gây gián đoạn.

Mảnh cấu hình này tự nó không triển khai JIT, phê duyệt hay MFA trung tâm. Nếu cần các kiểm soát đó, phải tích hợp với hệ thống cấp quyền tương ứng và kiểm tra cách chính sách được phân phối, hết hạn và thu hồi.

Tránh các mẫu cho phép đối số quá rộng như cho chạy tùy ý `systemctl`, một shell hoặc một trình thông dịch bằng root. Cho phép một script root-owned cũng cần kiểm tra đầu vào, lệnh phụ, đường dẫn tìm kiếm, tệp cấu hình và tài nguyên mà script sử dụng. Một wrapper nhận lệnh bất kỳ rồi thực thi bằng root chỉ chuyển điểm cấp toàn quyền sang nơi khác.

### 6.5. Giữ root đầy đủ cho nhu cầu được xác định

Có công việc sửa lỗi hệ thống hoặc khôi phục mà một tập lệnh hẹp chưa đáp ứng được. Khi đó, quyền root đầy đủ cần đi qua luồng riêng với lý do, phạm vi máy, người phê duyệt nếu chính sách yêu cầu, thời hạn và điều kiện kết thúc phiên.

Luồng khẩn cấp phải hoạt động khi một số thành phần PAM hoặc hệ thống danh tính gặp sự cố. Tuy nhiên, credential khẩn cấp không nên biến thành credential vận hành hằng ngày. Cần có người chịu trách nhiệm, cảnh báo khi sử dụng, bằng chứng sử dụng và bước khôi phục trạng thái kiểm soát sau sự kiện.

## 7. Ví dụ: từ “root để xem log” sang xử lý sự cố có phạm vi

### 7.1. Hiện trạng

Ứng dụng thanh toán có lỗi tăng cao. Runbook cũ yêu cầu kỹ sư lấy mật khẩu root từ vault, SSH vào máy, xem log, kiểm tra tiến trình rồi restart dịch vụ nếu cần. Phiên root thường được giữ mở đến hết ca để tránh đăng nhập lại.

Nhu cầu thực tế gồm ba phần khác nhau:

1. Quan sát lỗi và tài nguyên: chủ yếu là quyền đọc thông tin đã được cho phép.
2. Quyết định restart: cần bối cảnh vận hành và trách nhiệm phê duyệt theo chính sách.
3. Thực thi restart: cần quyền điều khiển đúng dịch vụ trên đúng máy.

Runbook cũ gộp cả ba phần vào một phiên toàn quyền. Vault bảo vệ mật khẩu nhưng không phân tách được phạm vi tác vụ bên trong phiên đó.

### 7.2. Luồng thay thế

Kỹ sư xem dashboard và log tập trung bằng danh tính cá nhân. Nếu có căn cứ restart, họ yêu cầu quyền tạm thời cho đúng dịch vụ trên máy đích. Hệ thống áp dụng chính sách, ghi nhận quyết định rồi cho phép thao tác hẹp. Sau thao tác, kỹ sư kiểm tra lại tình trạng ứng dụng qua kênh quan sát thông thường.

Ví dụ bản ghi yêu cầu dưới đây là dữ liệu minh họa, không phải cấu hình của một sản phẩm PAM:

```yaml
requestId: PAM-EXAMPLE-042
subject: engineer.lan
task: restart-service
target:
  host: payments-node-02
  service: payments-api.service
validity:
  start: "2026-11-27T10:00:00+07:00"
  end: "2026-11-27T10:15:00+07:00"
reason: "Ứng dụng lỗi sau thay đổi cấu hình đã được xác minh"
approvalReference: CHANGE-EXAMPLE-108
```

Thời lượng 15 phút chỉ là giả định của ví dụ. Thời hạn thực tế phải phù hợp với thao tác, khả năng thu hồi, quy trình ứng cứu và yêu cầu của tổ chức.

### 7.3. Khi tác vụ không nằm trong quyền được cấp

Nếu restart không giải quyết được lỗi và cần sửa cấu hình hệ thống, kỹ sư không mở rộng yêu cầu bằng cách tìm đường vào shell từ công cụ hiện có. Họ chuyển sang yêu cầu quyền mới hoặc luồng ứng cứu phù hợp, nêu rõ tài nguyên và thao tác bổ sung.

Đây là một điểm kiểm soát hữu ích: sự thay đổi nhu cầu đặc quyền được thể hiện thành sự kiện rõ ràng, thay vì âm thầm diễn ra trong root shell đang mở.

## 8. Chuyển đổi khỏi root thường trực mà không làm hỏng vận hành

### Bước 1: Kiểm kê đường đi tới đặc quyền

Ghi nhận tài khoản UID 0, đăng nhập root trực tiếp, khóa SSH, rule sudo, tài khoản dịch vụ, lịch chạy đặc quyền và cơ chế quản trị tương đương. Đối chiếu quyền được cấu hình với cách quyền thực sự được sử dụng.

Mỗi đường truy cập cần có chủ sở hữu, mục đích và hệ thống đích. Một tài khoản ít sử dụng không tự động an toàn; nó có thể là đường dự phòng chưa được kiểm soát hoặc credential bị quên.

### Bước 2: Quan sát tác vụ và tách nhu cầu

Chọn một nhóm máy hoặc một dịch vụ để làm thí điểm. Ghi lại các tác vụ thường làm dưới root và phân loại thành: không cần đặc quyền, cần đọc giới hạn, cần thao tác quản trị hẹp, hoặc thật sự cần quyền quản trị rộng.

Không chỉ sao chép nguyên các lệnh đã thấy vào allowlist. Cần hiểu mục đích, đầu vào và phụ thuộc của lệnh; một lệnh ngắn vẫn có thể mở shell, đọc secret hoặc ghi tệp tùy ý.

### Bước 3: Chuẩn bị đường thay thế trước khi thu hồi

Cung cấp đủ quyền đọc, công cụ quan sát và thao tác hẹp cho nhóm thí điểm. Kiểm tra tác vụ trong điều kiện bình thường lẫn khi một phụ thuộc bị gián đoạn. Cập nhật runbook để không còn yêu cầu mở root shell làm bước đầu tiên.

Với job và ứng dụng, thử chạy dưới danh tính dịch vụ riêng, xác định thư mục cần đọc hoặc ghi, credential cần lấy và phần khởi tạo cần đặc quyền nếu có. Không giải quyết lỗi bằng cách cấp quyền ghi rộng cho mọi người hoặc chuyển hàng loạt tệp hệ thống sang chủ sở hữu ứng dụng.

### Bước 4: Thu hồi quyền rộng theo đợt có kiểm chứng

Loại bỏ quyền root thường trực hoặc đường đăng nhập trực tiếp trong phạm vi đã sẵn sàng. Kiểm tra các quyền tương đương còn lại và các phiên đang tồn tại. Việc sửa rule chỉ tác động tới lần kiểm tra quyền tiếp theo trong nhiều cơ chế; không mặc định mọi tiến trình cũ đã mất quyền.

Thay đổi nhóm, credential, chính sách gateway và token có thể có thời điểm hiệu lực khác nhau. Định nghĩa rõ cần kết thúc phiên nào, làm mới ngữ cảnh nào và xác minh trên máy đích bằng cách nào.

### Bước 5: Theo dõi và xử lý nhu cầu chưa được đáp ứng

Theo dõi số yêu cầu bị từ chối, thời gian xử lý sự cố và số lần dùng luồng khẩn cấp. Phân tích trường hợp phát sinh để bổ sung quyền đúng tác vụ nếu có căn cứ, thay vì lập tức khôi phục quyền toàn cục cho cả đội.

Nếu cần hoàn tác một thay đổi để bảo đảm vận hành, ghi rõ phạm vi, người chịu trách nhiệm và hạn xử lý tiếp. Một lần hoàn tác có kiểm soát không nên trở thành ngoại lệ root vĩnh viễn.

## 9. Kiểm chứng kiểm soát bằng cả ca cho phép và ca từ chối

Thiết kế quyền chỉ đáng tin khi hành vi thực tế khớp với mục đích. Trong môi trường kiểm thử hoặc cửa sổ được phê duyệt, có thể xây dựng các ca sau:

| Ca kiểm chứng | Kỳ vọng | Bằng chứng cần giữ |
|---|---|---|
| Người chưa được cấp quyền xem dashboard và log trong phạm vi công việc | Làm được công việc quan sát cần thiết | Kết quả truy cập và nguồn dữ liệu |
| Người được cấp quyền restart đúng dịch vụ trên đúng máy | Thao tác được phép, ứng dụng được kiểm tra sau restart | Danh tính, quyết định cấp quyền, lệnh và kết quả |
| Cùng người đó yêu cầu restart dịch vụ khác | Bị từ chối nếu ngoài phạm vi | Sự kiện từ chối có ngữ cảnh |
| Người dùng yêu cầu root shell bằng quyền của tác vụ hẹp | Bị từ chối | Quyết định chính sách và nguồn kiểm tra |
| Người dùng thử sửa script hoặc cấu hình chi phối đường thực thi đặc quyền | Bị từ chối nếu không có quyền thay đổi riêng | Quyền tài nguyên và kết quả kiểm tra |
| Yêu cầu đã hết hạn được dùng để mở thao tác mới | Bị từ chối | Thời điểm hiệu lực và kết quả tại đích |
| Phiên hoặc tiến trình đã mở trước lúc hết hạn | Được xử lý theo chính sách thu hồi đã định nghĩa | Bằng chứng phiên kết thúc hoặc trạng thái còn tồn tại được chấp thuận |
| Hệ thống PAM không sẵn sàng | Luồng khẩn cấp vận hành đúng phạm vi đã thiết kế | Sự kiện sử dụng và đối soát sau phục hồi |

Không thử lệnh phá hủy để chứng minh người dùng thiếu quyền trên production. Có thể dùng môi trường thử, tài nguyên giả hoặc yêu cầu thao tác không gây tác động đã được chuẩn bị. Một phép thử thất bại vì dịch vụ không tồn tại không chứng minh rằng chính sách đã chặn quyền.

Với sudo, xem quyền hiệu lực bằng `sudo -l` có thể hỗ trợ kiểm tra, nhưng vẫn cần đối chiếu chính sách tổng thể và kiểm chứng hành vi phù hợp. Không chạy một lệnh gây gián đoạn chỉ để xem nó có được phép hay không.

## 10. Bằng chứng, giám sát và ứng phó sự cố

### 10.1. Chuỗi bằng chứng của một thao tác đặc quyền

Tối thiểu cần liên kết được danh tính yêu cầu, tác vụ, tài nguyên đích, quyết định cấp quyền, thời gian hiệu lực, phiên hoặc lần thực thi và kết quả. Mã yêu cầu hoặc mã phiên giúp nối các nguồn log mà không phải suy đoán chỉ từ timestamp.

Nên giữ cả sự kiện bị từ chối, lỗi phân phối chính sách và kết quả thu hồi quyền. Chỉ có bản ghi “đã phê duyệt” chưa chứng minh máy đích áp dụng đúng chính sách. Chỉ có video phiên cũng chưa chứng minh quyền đã hết hạn.

Chuyển bằng chứng tới hệ thống tập trung, giới hạn người có thể sửa hoặc xóa, đồng bộ thời gian và áp dụng thời hạn lưu phù hợp. Việc thu thập output hoặc nội dung phiên có thể chứa secret và dữ liệu nhạy cảm; cần kiểm soát truy cập, lọc hoặc che dữ liệu theo khả năng của hệ thống, tránh tạo thêm kho secret trong log.

### 10.2. Dấu hiệu cần điều tra

Các tín hiệu đáng chú ý gồm root shell kéo dài ngoài nhu cầu, đăng nhập root trực tiếp ngoài luồng được duyệt, tài khoản dịch vụ mở phiên tương tác, yêu cầu quyền cho nhiều máy không liên quan và việc thay đổi script hoặc unit đi kèm thao tác đặc quyền.

Một tín hiệu riêng lẻ chưa đủ để kết luận có tấn công. Đội phản ứng cần đối chiếu thay đổi được phê duyệt, lịch ứng cứu, người chịu trách nhiệm và trạng thái thực tế trên máy đích.

### 10.3. Khi nghi ngờ phiên root bị chiếm dụng

Thực hiện theo quy trình ứng phó sự cố của tổ chức: xác định phạm vi, bảo toàn bằng chứng, hạn chế đường truy cập và phối hợp xử lý máy bị ảnh hưởng. Phải xem xét phiên đang mở, khóa SSH, token, credential đã có thể bị đọc và cơ chế duy trì truy cập; đổi một mật khẩu không đủ để suy ra toàn bộ đặc quyền đã bị thu hồi.

Nếu đối tượng đã có quyền root rộng, độ tin cậy của hệ điều hành và log cục bộ có thể bị ảnh hưởng. Quyết định phục hồi hoặc tái tạo máy phải dựa vào đánh giá sự cố, không chỉ kết quả xóa một tài khoản hoặc kết thúc một phiên.

## 11. Đo tiến triển mà không che khuất quyền tương đương root

Các chỉ số hữu ích cần gắn với phạm vi kiểm kê và nguồn dữ liệu rõ ràng:

- Số danh tính có quyền root hoặc khả năng quản trị tương đương thường trực, phân biệt con người và dịch vụ.
- Tỷ lệ tác vụ vận hành đã có đường thực hiện bằng quyền đọc hoặc quyền thao tác hẹp.
- Số và thời lượng phiên root đầy đủ, kèm lý do và tham chiếu phê duyệt.
- Kết quả kiểm chứng thu hồi quyền, gồm độ trễ hiệu lực và phiên còn tồn tại.
- Tần suất dùng luồng khẩn cấp và tỷ lệ sự kiện được đối soát sau sử dụng.
- Thời gian hoàn thành tác vụ vận hành và nguyên nhân bị từ chối để phát hiện thiết kế quyền chưa đáp ứng công việc.

Không dùng riêng chỉ số “không còn đăng nhập bằng root” làm kết luận thành công. Mục tiêu có thể chưa đạt nếu mọi người vẫn chạy được shell qua sudo hoặc sửa mã mà dịch vụ root sẽ thực thi. Cũng không nên giảm số lần nâng quyền bằng cách kéo dài phiên root: chỉ số ít sự kiện hơn có thể đi cùng thời gian phơi lộ lớn hơn.

## 12. Những điểm cần ghi nhớ

Dùng root cho tác vụ thường làm cho lỗi thao tác, lỗ hổng công cụ và việc chiếm phiên xảy ra trong bối cảnh có quyền quá lớn. Vault, MFA và ghi phiên hỗ trợ kiểm soát truy cập nhưng không thay thế việc xác định quyền cần thiết của từng tác vụ.

Thiết kế tốt bắt đầu từ danh tính rõ ràng, kênh quan sát không cần đặc quyền, quyền quản trị có phạm vi và thời hạn phù hợp. Khi quyền root đầy đủ thật sự cần thiết, phải có luồng sử dụng, kết thúc và lưu bằng chứng rõ ràng.

Một tác vụ vận hành được kiểm soát tốt cần chứng minh được cả hai mặt: người dùng hoàn thành công việc được giao và không thể vượt sang phạm vi quản trị khác bằng chính quyền đã được cấp.
