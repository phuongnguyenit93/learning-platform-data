# Xác định privileged actor

## 1. Privileged actor là ai và vì sao phải xác định sớm?

**Privileged actor** là chủ thể có khả năng thực hiện những hành động đặc quyền đối với tài sản hoặc hệ thống trong một phạm vi và điều kiện cụ thể. Những hành động này có thể vượt quyền sử dụng thông thường, ảnh hưởng nhiều người, thay đổi cơ chế bảo vệ hoặc tạo ra quyền mới.

Chủ thể đó có thể là con người, một dịch vụ, workload, pipeline triển khai hoặc hệ thống của nhà cung cấp. Vì vậy, việc tìm một vai trò tên `ADMIN` trong ứng dụng không đủ để xác định toàn bộ privileged actor.

Ví dụ, một kỹ sư không có quyền đọc dữ liệu khách hàng trong giao diện nhưng có thể sửa pipeline triển khai. Nếu pipeline được phép đưa mã tùy ý vào dịch vụ đang có quyền đọc dữ liệu đó, kỹ sư có thể có một đường tác động gián tiếp đến dữ liệu. Ngược lại, tài khoản được đặt tên “admin báo cáo” nhưng chỉ đọc số liệu công khai trong một phạm vi hẹp không mặc nhiên có đặc quyền quản trị hệ thống.

Xác định privileged actor là một phần của việc làm rõ **bối cảnh và phạm vi yêu cầu bảo mật**. Kết quả cần trả lời:

- Chủ thể nào có thể tác động đến tài sản nào, bằng hành động gì?
- Quyền có hiệu lực trong tenant, môi trường và thời gian nào?
- Quyền được cấp trực tiếp hay hình thành qua một chuỗi tác động?
- Ai sở hữu, phê duyệt, sử dụng, thu hồi và kiểm tra quyền đó?
- Hệ thống phải ngăn chặn, ghi nhận và phục hồi ra sao nếu quyền bị lạm dụng?

Mục đích là chuyển các đường đặc quyền thành yêu cầu cụ thể, đo được và có thể kiểm chứng. Danh sách tên tài khoản chỉ là một phần đầu vào, chưa phải kết quả đầy đủ.

## 2. Phân biệt chủ thể, tài khoản, vai trò và quyền

Các thuật ngữ dễ bị trộn lẫn cần được tách rõ:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Actor — chủ thể | Thực thể thực hiện hoặc khởi tạo một hành động trong ngữ cảnh đang xét. | Nhân viên hỗ trợ, dịch vụ lập chỉ mục, pipeline triển khai. |
| Account — tài khoản | Bản ghi danh tính được một hệ thống quản lý. | Tài khoản định danh doanh nghiệp của một kỹ sư. |
| Principal — thực thể mang danh tính khi đánh giá quyền | Danh tính mà điểm kiểm soát truy cập dùng để quyết định cho phép hoặc từ chối. | Người dùng đã xác thực, service account, danh tính workload. |
| Role — vai trò | Cách nhóm quyền hoặc trách nhiệm trong mô hình phân quyền. | Quản trị tenant, hỗ trợ kỹ thuật, người phê duyệt triển khai. |
| Permission — quyền | Khả năng thực hiện một hành động trên tài nguyên theo điều kiện. | Cấp vai trò cho thành viên trong tenant A. |
| Credential — thông tin dùng để chứng minh danh tính hoặc quyền truy cập | Phương tiện mà cơ chế xác thực hoặc ủy quyền kiểm tra. | Khóa truy cập, chứng thư, token phiên. |
| Session hoặc grant — phiên hoặc lần cấp quyền | Ngữ cảnh truy cập có thời hạn và điều kiện cụ thể. | Phiên hỗ trợ được cấp trong 15 phút cho một yêu cầu xử lý sự cố. |

Một người có thể dùng nhiều tài khoản. Một tài khoản có thể có nhiều vai trò. Một dịch vụ có thể dùng nhiều danh tính ở các môi trường khác nhau. Một token không nhất thiết thể hiện toàn bộ quyền hiện hành nếu quyền đã thay đổi hoặc token chỉ có phạm vi hẹp.

Khi một nhân viên khởi chạy tác vụ và tác vụ chạy bằng service account, nên phân biệt **chủ thể khởi tạo** với **danh tính thực thi**. Nếu chỉ biết service account đã đọc dữ liệu mà không liên kết được lần chạy và người khởi tạo khi có người tham gia, khả năng quy trách nhiệm sẽ bị hạn chế.

Cũng không được coi trường `role=admin`, `actorId` hoặc `tenantId` do client tự gửi là bằng chứng đặc quyền. Điểm thực thi quyền phải dựa trên nguồn danh tính và chính sách đã được xác minh theo quan hệ tin cậy của hệ thống.

## 3. Nhận diện đặc quyền theo năng lực và tác động

### 3.1. Những câu hỏi để phát hiện một privileged actor

Một chủ thể đáng được xem xét như privileged actor nếu có khả năng:

1. Cấp, thu hồi, mở rộng hoặc ủy quyền truy cập cho người khác hay cho chính mình.
2. Vượt ranh giới tenant, lớp dữ liệu hoặc phạm vi quản lý thông thường.
3. Đọc dữ liệu nhạy cảm hàng loạt hoặc truy cập khóa, bí mật và bản sao lưu có thể mở đường đến dữ liệu.
4. Sửa, xóa hoặc khôi phục dữ liệu với tác động rộng hoặc ngoài quy trình nghiệp vụ thông thường.
5. Thay đổi chính sách bảo mật, cấu hình xác thực, điểm thực thi phân quyền hoặc cấu hình mạng liên quan.
6. Thay đổi mã, quy trình build, artifact hoặc cấu hình triển khai của thành phần có quyền cao.
7. Dừng dịch vụ, làm cạn tài nguyên, vô hiệu hóa cảnh báo hoặc can thiệp dấu vết điều tra.
8. Sử dụng cơ chế khẩn cấp để thực hiện hành động không được phép trong luồng thông thường.

Các câu hỏi này là cách tìm ứng viên, không phải phép gán nhãn tự động. Phải xét thêm các giới hạn có hiệu lực: phê duyệt độc lập, chính sách từ chối, phạm vi tài nguyên, môi trường, khóa mã hóa, giới hạn danh tính và thời gian.

### 3.2. Đặc quyền luôn tương đối với tài sản và phạm vi

Quyền quản lý thành viên trong tenant A không đồng nghĩa có quyền quản lý tenant B. Quyền triển khai ở môi trường kiểm thử không tự tạo quyền triển khai production. Tuy nhiên, nếu môi trường kiểm thử chứa bản sao dữ liệu thật hoặc dùng chung bí mật với production, cần ghi lại đường tác động đó thay vì kết luận môi trường kiểm thử không có rủi ro đặc quyền.

Một hành động cũng có thể đặc quyền trong hoàn cảnh này nhưng bình thường trong hoàn cảnh khác. Người dùng sửa hồ sơ của chính mình thường là chức năng thông thường. Nhân viên sửa hồ sơ của mọi người mà không cần sự tham gia của chủ sở hữu là năng lực cần kiểm soát đặc quyền.

Có thể mô tả đặc quyền theo nhiều chiều:

| Chiều đánh giá | Ví dụ cần phân biệt |
|---|---|
| Phạm vi dữ liệu | Một tài liệu, một tenant, toàn bộ tenant. |
| Loại hành động | Đọc, sửa, xóa, xuất, cấp quyền, thay đổi chính sách. |
| Lớp kiểm soát | Ứng dụng, cơ sở dữ liệu, hệ điều hành, nền tảng đám mây, định danh, CI/CD. |
| Thời gian | Quyền thường trực, quyền kích hoạt theo nhiệm vụ, quyền khẩn cấp. |
| Đường có được quyền | Gán trực tiếp, thành viên nhóm, ủy quyền, thay đổi cấu hình hoặc chiếm danh tính khác. |
| Tác động | Bí mật dữ liệu, toàn vẹn nghiệp vụ, sẵn sàng dịch vụ, khả năng điều tra và phục hồi. |

Không cần gộp tất cả thành một điểm số duy nhất. Một hồ sơ nêu rõ phạm vi và đường tác động thường hữu ích cho thiết kế hơn nhãn “rủi ro cao” không có giải thích.

## 4. Ví dụ bối cảnh: dịch vụ quản lý tài liệu nhiều tenant

Giả sử dịch vụ lưu trữ tài liệu nội bộ cho nhiều tổ chức. Người dùng đọc hoặc sửa tài liệu theo quyền được cấp. Quản trị viên tổ chức quản lý thành viên trong tenant. Đội hỗ trợ xử lý sự cố. Đội nền tảng vận hành hạ tầng. Pipeline triển khai đưa phiên bản mới vào production. Một dịch vụ khác tạo và phục hồi bản sao lưu.

Các tài sản chính gồm nội dung tài liệu, metadata, thành viên và quyền, bí mật dịch vụ, khóa mã hóa, cấu hình triển khai, nhật ký kiểm toán và bản sao lưu. Metadata như tiêu đề, tên người sở hữu hay đường dẫn cũng có thể nhạy cảm, không được mặc định là dữ liệu công khai.

Danh sách ứng viên đặc quyền ban đầu có thể là:

| Ứng viên | Năng lực cần khảo sát | Giới hạn và câu hỏi còn phải làm rõ |
|---|---|---|
| Quản trị viên tenant | Quản lý thành viên, nhóm và một số vai trò trong tenant. | Có thể tự cấp quyền đọc tài liệu không? Có thể cấp vai trò cao hơn mình hoặc tác động tenant khác không? |
| Nhân viên hỗ trợ | Xem thông tin chẩn đoán, chạy một số thao tác hỗ trợ. | Có xem nội dung tài liệu, tải tệp hoặc mạo danh người dùng không? Ai cho phép và trong bao lâu? |
| Kỹ sư nền tảng | Sửa cấu hình runtime, quản lý workload và xử lý sự cố. | Có thể đọc bí mật, chạy lệnh trong workload hoặc gắn danh tính có quyền cao không? |
| Pipeline triển khai | Phát hành artifact và cập nhật dịch vụ production. | Ai sửa được workflow, nguồn mã, artifact, biến cấu hình và danh tính triển khai? |
| Dịch vụ sao lưu/phục hồi | Đọc dữ liệu nguồn, lưu bản sao, thực hiện khôi phục. | Có quyền giải mã không? Có thể ghi đè production hoặc khôi phục quyền truy cập đã hết hiệu lực không? |
| Nhà cung cấp tích hợp | Gọi API hoặc truy cập vận hành theo hợp đồng. | Quyền thực tế nằm ở API, tài khoản hỗ trợ hay kênh quản trị nào? Có cơ chế ngắt truy cập không? |
| Danh tính truy cập khẩn cấp | Thao tác khi đường quản trị thông thường không dùng được. | Ai được dùng, xác thực thế nào, ai biết việc sử dụng và làm sao kết thúc quyền sau sự cố? |

Bảng này không khẳng định mọi ứng viên đều có tất cả năng lực được nêu. Đó là tập câu hỏi cần xác minh. Những năng lực chưa biết phải được đánh dấu chưa xác minh và gắn người xử lý, không tự coi là có hoặc không có quyền.

## 5. Quy trình xác định privileged actor

### Bước 1: Xác định tài sản và hành động nhạy cảm

Bắt đầu từ nghiệp vụ và khả năng vận hành: ai có thể cấp quyền, đọc hàng loạt, sửa dữ liệu ngoài luồng, thay cấu hình, triển khai hoặc phục hồi? Với mỗi hành động, ghi tài sản, tác động và ranh giới có thể bị vượt qua.

Không chỉ bắt đầu từ chức danh nhân sự. “Kỹ sư vận hành” là mô tả công việc; “có thể thay danh tính runtime của dịch vụ tài liệu trong production” mới là năng lực giúp viết yêu cầu bảo mật.

### Bước 2: Tìm các danh tính có thể thực hiện hành động

Trong một dự án thực tế, nguồn bằng chứng có thể gồm mô hình phân quyền, cấu hình định danh, danh sách service account, chính sách hạ tầng, workflow triển khai, cấu hình sao lưu và quy trình nhà cung cấp. Chỉ phỏng vấn chủ hệ thống mà không đối chiếu cấu hình có thể bỏ sót quyền còn tồn tại; chỉ đọc cấu hình mà không hiểu quy trình lại có thể bỏ sót đường hỗ trợ thủ công.

Bài học mô tả phương pháp thực hiện; các ví dụ không phải kết quả kiểm kê của một hệ thống đang vận hành.

### Bước 3: Mở rộng sang các đường đặc quyền gián tiếp

Với mỗi danh tính, hỏi tiếp: ai có thể điều khiển danh tính đó, thay đổi điều kiện thực thi hoặc cấp cho nó thêm quyền? Ví dụ:

```text
Người có quyền sửa workflow
        |
        v
Pipeline có quyền triển khai production
        |
        v
Mã chạy bằng danh tính dịch vụ
        |
        v
Tài nguyên mà danh tính dịch vụ được phép truy cập
```

Đường này chỉ tồn tại nếu các điều kiện ở từng bước thực sự cho phép. Cơ chế bảo vệ nhánh, phê duyệt độc lập, xác minh artifact hoặc giới hạn danh tính có thể chặn một số đường. Phải ghi điều kiện và bằng chứng, không suy rằng mọi người sửa mã đều tự động có quyền đọc mọi dữ liệu.

### Bước 4: Xác định phạm vi và điều kiện có hiệu lực

Ghi rõ tenant, môi trường, tài nguyên, loại hành động, thời hạn, điều kiện kích hoạt và các ràng buộc. Với quyền tạm thời, ghi cả cách quyền bị vô hiệu hóa tại API, phiên, cache, tác vụ nền và đường tải tệp liên quan.

Cần phân biệt quyền đang có, quyền có thể yêu cầu kích hoạt và quyền có thể tự cấp. Một người chưa kích hoạt quyền cao nhưng có thể tự phê duyệt để kích hoạt vẫn là điểm cần phân tích.

### Bước 5: Gắn sở hữu và trách nhiệm

Mỗi danh tính đặc quyền cần có chủ sở hữu chịu trách nhiệm về mục đích, phạm vi và vòng đời. Với danh tính máy, chủ sở hữu thường là nhóm hoặc vai trò tổ chức được chỉ định, không phải “hệ thống tự quản lý”.

Tách người yêu cầu, người phê duyệt, người thực hiện và người rà soát ở những hoạt động cần phân tách nhiệm vụ. Cần xét cùng một người dùng nhiều tài khoản hoặc có thể điều khiển tài khoản dịch vụ; khác tên tài khoản chưa chứng minh độc lập về người quyết định.

### Bước 6: Xác minh và ghi khoảng trống

Mỗi nhận định nên có căn cứ và trạng thái, chẳng hạn đã xác minh, đề xuất hoặc chưa xác minh. Ví dụ “tài khoản sao lưu không đọc được bản rõ” cần đối chiếu cả quyền lấy dữ liệu, quyền dùng khóa và các đường phục hồi, không chỉ tên vai trò.

Nếu chưa biết ai có thể thay cấu hình nhà cung cấp định danh, ghi khoảng trống kèm chủ sở hữu và thời điểm cần làm rõ. Khoảng trống có thể ảnh hưởng kết luận về độ tin cậy của toàn bộ quyền ứng dụng.

### Bước 7: Duy trì khi bối cảnh thay đổi

Kiểm kê không phải việc chỉ làm trước lần phát hành đầu. Thêm tích hợp, đổi pipeline, dùng dữ liệu thật trong môi trường mới, mở chức năng hỗ trợ hoặc thay cơ chế phục hồi đều có thể tạo privileged actor mới hoặc mở rộng đặc quyền của actor cũ.

## 6. Lập hồ sơ privileged actor để dùng được trong đặc tả

### 6.1. Các trường cần có

Một hồ sơ hữu ích cần đủ thông tin để người thiết kế và người kiểm thử hiểu cùng một phạm vi:

| Trường | Nội dung cần ghi |
|---|---|
| Mã actor và loại | Mã ổn định; con người, workload, pipeline hoặc bên thứ ba. |
| Mục đích và chủ sở hữu | Vì sao cần đặc quyền, ai chịu trách nhiệm và ai xác nhận nhu cầu còn tồn tại. |
| Cách ràng buộc danh tính | Nguồn định danh, tài khoản liên quan, danh tính thực thi và cách nhận biết người khởi tạo nếu có. |
| Hành động và tài sản | Các thao tác cụ thể, đối tượng dữ liệu, cấu hình hoặc hệ thống chịu tác động. |
| Phạm vi | Tenant, môi trường, tập tài nguyên, số lượng hoặc giới hạn tác động. |
| Đường đặc quyền | Quyền trực tiếp, nhóm, ủy quyền và các đường gián tiếp đã xác định. |
| Điều kiện và thời hạn | Cách kích hoạt, yêu cầu xác thực, phê duyệt, thời gian hết hạn và điều kiện dùng quyền. |
| Giới hạn và phân tách nhiệm vụ | Những việc không được làm, tổ hợp quyền bị cấm, yêu cầu người quyết định độc lập. |
| Vòng đời | Cấp, thay đổi, rà soát, thu hồi, xử lý khi chuyển nhóm hoặc hệ thống ngừng hoạt động. |
| Dấu vết | Sự kiện phải ghi, cách liên kết phiên/tác vụ và nơi bằng chứng được bảo vệ. |
| Phụ thuộc và tình huống lỗi | Phụ thuộc định danh, cấp quyền, log và cách xử lý khi không xác minh được điều kiện. |
| Căn cứ và trạng thái | Nguồn bằng chứng, ngày xác minh, người xác minh, giả định và câu hỏi còn mở. |

Không lưu mật khẩu, khóa bí mật hoặc token đang có hiệu lực vào hồ sơ actor. Hồ sơ chỉ nên chứa định danh và tham chiếu quản lý phù hợp; chính danh sách đặc quyền cũng cần được giới hạn quyền truy cập vì nó mô tả các đường có tác động cao.

### 6.2. Một phần danh mục minh họa

Các dòng dưới đây là mô hình giả định để học cách đặc tả, không phải trạng thái đã xác minh của một triển khai thực:

| Mã | Actor | Năng lực giả định | Phạm vi dự kiến | Điểm phải kiểm soát |
|---|---|---|---|---|
| PA-H-01 | Quản trị viên tenant | Quản lý thành viên và các vai trò được phép giao. | Một tenant. | Không cấp vượt trần quyền được ủy nhiệm; xét khả năng tự mở quyền qua nhóm. |
| PA-H-02 | Nhân viên hỗ trợ | Đọc một tập thông tin chẩn đoán đã xác định. | Một tenant và tài liệu trong yêu cầu hỗ trợ. | Cấp theo nhiệm vụ, có thời hạn; không bao gồm nội dung tài liệu. |
| PA-W-01 | Pipeline triển khai | Cập nhật dịch vụ bằng artifact được chấp nhận. | Dịch vụ và môi trường production cụ thể. | Kiểm soát người sửa workflow, nguồn artifact và quyền gắn danh tính runtime. |
| PA-W-02 | Dịch vụ phục hồi | Khôi phục dữ liệu theo nhiệm vụ được phê duyệt. | Tập dữ liệu và môi trường đích được chỉ định. | Không mở quyền truy cập từ bản sao cũ; bảo vệ khóa và ghi nhận nhiệm vụ. |
| PA-E-01 | Danh tính truy cập khẩn cấp | Các thao tác khẩn cấp được định nghĩa riêng. | Tài nguyên trong kịch bản sự cố. | Xác thực, quy trách nhiệm, cảnh báo và kết thúc quyền theo quy trình khẩn cấp. |

Một dòng trong danh mục không thay cho chính sách chi tiết. Ví dụ PA-W-01 cần được nối tới ai có thể sửa workflow và các điều kiện để artifact được chấp nhận. Nếu thiếu quan hệ đó, đặc tả có thể bảo vệ tài khoản pipeline nhưng bỏ qua người điều khiển pipeline.

## 7. Xem xét quyền hiệu lực và các đường leo thang

### 7.1. Quyền được gán khác với quyền có thể thực hiện

**Quyền hiệu lực** là kết quả của các chính sách, quan hệ danh tính và điều kiện thực tế khi đánh giá một hành động. Nó có thể chịu ảnh hưởng của vai trò trực tiếp, nhóm lồng nhau, ủy quyền, chính sách tài nguyên, giới hạn tổ chức, điều kiện môi trường và quy tắc từ chối.

Không nên cộng cơ học tất cả vai trò rồi cho rằng đó là quyền hiệu lực. Một chính sách từ chối hoặc ràng buộc tài nguyên có thể ngăn hành động. Ngược lại, chỉ nhìn một bảng vai trò ứng dụng có thể bỏ sót quyền ở cơ sở dữ liệu hoặc nền tảng triển khai.

Để phân tích một đường quyền, có thể ghi:

```text
Điểm bắt đầu: danh tính hoặc khả năng của actor
Bước chuyển: hành động actor có thể thực hiện
Điều kiện: cấu hình, phê duyệt và giới hạn phải thỏa
Điểm đến: quyền hoặc tài sản actor có thể tác động
Bằng chứng: cách xác nhận từng bước và điểm chặn
```

### 7.2. Các đường thường bị bỏ sót

| Quyền ban đầu | Khả năng gián tiếp cần xem xét | Điều kiện cần xác minh |
|---|---|---|
| Đổi nhóm hoặc vai trò | Tự thêm mình hoặc danh tính mình kiểm soát vào nhóm quyền cao. | Giới hạn ủy nhiệm, nhóm lồng nhau, phê duyệt và các quy tắc từ chối. |
| Đặt lại thông tin xác thực | Kiểm soát một tài khoản có quyền cao hơn. | Cơ chế xác nhận chủ sở hữu, yếu tố xác thực còn lại và giới hạn của thao tác đặt lại. |
| Đọc bí mật dịch vụ | Dùng danh tính dịch vụ để gọi tài nguyên khác. | Bí mật còn hiệu lực, phạm vi, điều kiện sử dụng và quyền thực tế của danh tính. |
| Sửa workflow hoặc artifact | Thay mã được triển khai vào vùng có quyền cao. | Quy tắc nguồn tin cậy, xác minh artifact, người phê duyệt và danh tính thực thi. |
| Tạo tác vụ hoặc workload | Gắn danh tính mạnh hơn vào mã do mình điều khiển. | Quyền chọn danh tính, admission policy và giới hạn runtime. |
| Phục hồi cơ sở dữ liệu | Đưa trở lại dữ liệu, quyền hoặc tài khoản cũ. | Phạm vi restore, kiểm soát ghi đè và cách áp chính sách quyền hiện hành. |
| Quản lý log hoặc cảnh báo | Xóa dấu vết hoặc che giấu lạm dụng. | Phân tách quyền ghi/đọc/quản trị, thời hạn lưu và nơi lưu độc lập. |

Không phải mọi đường đều là lỗ hổng: một số năng lực được cấp có chủ đích để vận hành hệ thống. Tuy nhiên, chúng vẫn phải xuất hiện trong mô hình đe dọa và yêu cầu bảo mật vì có thể bị lạm dụng hoặc bị chiếm quyền.

Cần xét **tổ hợp quyền**. Một người được sửa workflow và cũng được tự phê duyệt phát hành có thể có năng lực mà từng vai trò riêng lẻ chưa tạo ra. Khi đánh giá phân tách nhiệm vụ, phải xét những gì người đó có thể điều khiển, không chỉ những gì tài khoản đang dùng được gán trực tiếp.

## 8. Chuyển kết quả nhận diện thành yêu cầu bảo mật

### 8.1. Cấp quyền có mục đích, phạm vi và vòng đời

Một phát biểu như “chỉ admin được quản trị” còn quá mơ hồ. Cần nêu hành động nào, admin nào, ở đâu và trong điều kiện gì.

**REQ-PA-01 — Giới hạn việc cấp đặc quyền**

> Hệ thống chỉ cho phép chủ thể được ủy nhiệm cấp các quyền trong tập quyền, tenant, tài nguyên và thời hạn mà chính sách cho phép họ giao. Việc kiểm tra phải áp dụng với cấp trực tiếp, thay đổi nhóm và các đường ủy quyền thuộc phạm vi. Không cho phép vượt giới hạn bằng cách cấp cho một danh tính trung gian do người yêu cầu kiểm soát.

Yêu cầu này phải được cụ thể hóa bằng danh sách quyền được giao và các quan hệ danh tính cần đánh giá. Bằng chứng gồm ca cấp quyền hợp lệ, cấp vượt phạm vi, cấp qua nhóm và thử tự mở rộng quyền. Đối với đường không thể ngăn bằng chính sách kỹ thuật hiện có, phải ghi rõ giới hạn và biện pháp quản trị được chấp nhận thay vì tuyên bố đã ngăn hoàn toàn.

Vòng đời còn phải bao gồm nghỉ việc, chuyển nhóm, ngừng hợp đồng nhà cung cấp, xóa workload và thu hồi thông tin xác thực khi có sự cố. Quyền không có chủ sở hữu hoặc không còn mục đích là khoảng trống cần xử lý, không phải một vai trò mặc định để giữ lại.

### 8.2. Xác thực phù hợp với con người và danh tính máy

Với con người, các thao tác đặc quyền có thể cần xác thực đa yếu tố và bằng chứng xác thực đủ mới. Với workload hoặc pipeline, cần ràng buộc danh tính với workload, môi trường và mục đích được phép; thông tin xác thực phải có phạm vi và vòng đời phù hợp.

Không áp dụng nguyên xi yêu cầu “người dùng phải nhập MFA” cho một tác vụ tự động. Cũng không bỏ xác thực mạnh cho danh tính máy chỉ vì không có người trực tiếp đăng nhập. Yêu cầu cần hướng đến cách xác minh chủ thể thực thi và chống sử dụng sai danh tính đó.

Nếu dùng token hoặc cơ chế liên kết danh tính, cần xác định nguồn phát hành được tin cậy, đối tượng nhận, phạm vi và điều kiện chấp nhận theo thiết kế. Việc token hợp lệ về một mặt không tự chứng minh chủ thể được phép làm mọi hành động.

### 8.3. Tách yêu cầu, phê duyệt và thực hiện ở nơi cần thiết

**REQ-PA-02 — Không tự phê duyệt thao tác tác động cao**

> Với tập thao tác tác động cao được liệt kê, người yêu cầu không được đồng thời là người phê duyệt cuối cùng, kể cả khi sử dụng các tài khoản khác nhau được liên kết với cùng một người. Quyền thực hiện chỉ được kích hoạt sau khi các điều kiện phê duyệt, phạm vi và thời hạn đều hợp lệ.

Tập thao tác có thể gồm phục hồi ghi đè production, mở quyền truy cập diện rộng hoặc thay đổi chính sách đặc quyền. Không cần áp dụng cùng một quy trình nặng cho mọi thao tác; mức kiểm soát phải tương ứng tác động và nhu cầu vận hành.

Với nhà cung cấp và tài khoản dịch vụ, phải xác định mức độ liên kết được danh tính và giới hạn chứng minh độc lập. Khác tài khoản chưa đủ để khẳng định khác người điều khiển.

### 8.4. Logging phải phục vụ quy trách nhiệm

**REQ-PA-03 — Ghi nhận vòng đời và việc sử dụng đặc quyền**

> Hệ thống phải ghi nhận yêu cầu cấp quyền, quyết định phê duyệt, kích hoạt, sử dụng, từ chối, hết hạn và thu hồi đối với tập đặc quyền đã xác định. Sự kiện phải cho phép liên kết chủ thể khởi tạo, danh tính thực thi, tenant, tài nguyên, hành động, kết quả, phiên hoặc tác vụ và mã tương quan phù hợp. Không ghi mật khẩu, khóa bí mật, token hay nội dung tài liệu vào log này.

Nếu cần truy xuất được sự kiện trong một thời hạn, phải định nghĩa điểm bắt đầu đo, nơi truy vấn, tải và ngưỡng. “Đã ghi log ở tiến trình” khác với “đã truy vấn được tại nơi điều tra”.

Bảo vệ nhật ký cần dựa trên mô hình đe dọa. Nếu một người có thể thực hiện thao tác và đồng thời sửa toàn bộ dấu vết ở cùng một miền quản trị, không thể mặc định log đó chống được việc che giấu của người ấy. Thiết kế phải nêu cơ chế, ranh giới quản trị độc lập hoặc giới hạn còn lại.

### 8.5. Thu hồi và phục hồi phải bao phủ đường thực thi thực tế

Yêu cầu thu hồi phải xét phiên đang mở, token còn hạn, cache quyền, tác vụ nền và liên kết tải xuống. Cần phân biệt request mới với thao tác đã bắt đầu; nếu yêu cầu hủy cả tác vụ đang chạy thì phải đặc tả riêng cách dừng, trạng thái và xử lý tác dụng phụ.

Phục hồi dữ liệu không được vô tình tái kích hoạt quyền đã thu hồi hoặc danh tính đã ngừng sử dụng. Quy trình phải đối chiếu trạng thái quyền hiện hành và các điều kiện truy cập trước khi mở lại chức năng nhạy cảm. Bằng chứng phục hồi vì vậy cần kiểm tra cả dữ liệu, quyền, khả năng dùng khóa và dấu vết, thay vì chỉ xác nhận cơ sở dữ liệu khởi động được.

## 9. Ví dụ đầy đủ: quyền hỗ trợ chẩn đoán có thời hạn

### 9.1. Mô hình đe dọa và giới hạn nghiệp vụ

Nhân viên hỗ trợ cần kiểm tra vì sao một tài liệu không được lập chỉ mục. Trong ví dụ này, công việc chỉ cần một tập metadata chẩn đoán gồm mã tài liệu, trạng thái xử lý, trạng thái lập chỉ mục và mã lỗi đã phân loại. Không cần nội dung, tiêu đề tài liệu, tên người sở hữu, khóa truy cập hay thông báo lỗi thô.

Các rủi ro gồm truy cập sai tenant, mở rộng sang tài liệu khác, dùng quyền sau khi kết thúc yêu cầu hỗ trợ và không truy được người thực sự thao tác. Cơ chế hỗ trợ không được biến thành quyền đọc thường trực cho mọi nhân viên hỗ trợ.

Phân biệt phạm vi quyền kỹ thuật với giới hạn sử dụng dữ liệu: nếu hệ thống cho một người đọc bản rõ, không thể chỉ bằng việc ẩn nút tải xuống mà bảo đảm người ấy không sao chép nội dung đã đọc. Ví dụ này tránh cấp quyền đọc nội dung ngay từ đầu vì nhiệm vụ không cần đến nó.

### 9.2. Bản ghi cấp quyền minh họa

```text
Actor: nhân viên hỗ trợ có danh tính cá nhân đã xác minh
Mục đích: chẩn đoán yêu cầu hỗ trợ SUP-42
Tenant: T-A
Tài nguyên: tài liệu D-123
Hành động: document.diagnostic.read
Dữ liệu được trả: documentId, processingStatus, indexStatus, errorCategory
Người phê duyệt: đại diện tenant có quyền phê duyệt hỗ trợ theo chính sách
Thời hạn: tối đa 15 phút kể từ khi kích hoạt
Xác thực: MFA của nhân viên hỗ trợ còn mới trong 5 phút khi kích hoạt
Không bao gồm: nội dung, tiêu đề, người sở hữu, tệp xuất, cấp quyền khác
Thu hồi: yêu cầu mới từ thời điểm thu hồi có hiệu lực phải bị từ chối
```

Các mốc 15 phút, 5 phút và ngưỡng thu hồi bên dưới là **số liệu giả định để minh họa yêu cầu**, không phải chuẩn chung. Dự án phải lựa chọn chúng dựa trên rủi ro, trải nghiệm và năng lực kiến trúc.

### 9.3. Yêu cầu kiểm chứng được

**REQ-SUP-01 — Cấp quyền đúng nhiệm vụ**

> Chỉ kích hoạt quyền chẩn đoán sau khi xác minh danh tính nhân viên, tư cách hỗ trợ còn hiệu lực, bằng chứng MFA đủ mới, người phê duyệt có quyền trong tenant và bản ghi nhiệm vụ có tài nguyên cụ thể. Người hỗ trợ không được tự phê duyệt. Quyền chỉ áp dụng cho hành động và các trường được phép trong bản ghi cấp quyền.

**REQ-SUP-02 — Kiểm tra phạm vi tại điểm trả dữ liệu**

> Mọi yêu cầu đọc thông tin chẩn đoán phải kiểm tra tenant, tài liệu, hành động và hiệu lực của lần cấp quyền ở máy chủ trước khi trả dữ liệu. Đổi đường dẫn, tham số, cache hoặc gọi trực tiếp API không được mở rộng phạm vi. Quyền này không cho phép đọc nội dung tài liệu hoặc tải tệp xuất qua đường khác.

**REQ-SUP-03 — Hết hạn và thu hồi**

> Quyền hết hiệu lực theo thời điểm kết thúc của lần cấp quyền, dựa trên nguồn thời gian tin cậy của hệ thống. Khi thao tác thu hồi được xác nhận thành công tại t0, mọi yêu cầu chẩn đoán mới bắt đầu từ t0 + 60 giây phải bị từ chối nếu không có một lần cấp quyền độc lập còn hợp lệ. Request đã bắt đầu được xử lý theo chính sách riêng đã công bố; yêu cầu này không tự hứa hủy mọi request đang chạy.

Giới hạn thu hồi này cho phép một khoảng trễ tối đa trong ví dụ. Không nên mô tả nó là “thu hồi tức thời”. Nếu dữ liệu hoặc nhiệm vụ không chấp nhận khoảng trễ đó, cần yêu cầu và kiến trúc khác.

**REQ-SUP-04 — Ghi nhận và chế độ lỗi**

> Sự kiện cấp, sử dụng, từ chối và thu hồi phải liên kết với SUP-42, danh tính nhân viên, người phê duyệt, lần cấp quyền và tài nguyên. Nếu không xác minh được quyền hỗ trợ hợp lệ, hệ thống không trả dữ liệu chẩn đoán. Thiết kế phải nêu cách lưu sự kiện theo cam kết và phản ứng khi đường chuyển log lỗi; không được mất dấu vết một cách im lặng.

### 9.4. Bộ tiêu chí chấp nhận tối thiểu

| Ca kiểm chứng | Kết quả cần quan sát |
|---|---|
| Nhân viên hợp lệ, được phê duyệt cho T-A/D-123, trong thời hạn | Nhận đúng bốn trường chẩn đoán được phép; có sự kiện sử dụng. |
| Đổi D-123 thành tài liệu khác | Không nhận dữ liệu chẩn đoán ngoài phạm vi; có kết quả từ chối theo hợp đồng. |
| Đổi tenant trong request hoặc dùng tài nguyên tenant khác | Không vượt ranh giới tenant, kể cả khi client tự gửi tenant hợp lệ về định dạng. |
| Gọi API đọc nội dung hoặc xuất tài liệu bằng cùng phiên hỗ trợ | Không được cho phép chỉ nhờ quyền chẩn đoán. |
| Người hỗ trợ phê duyệt yêu cầu của chính mình bằng tài khoản liên kết khác | Không kích hoạt quyền nếu vi phạm chính sách độc lập người phê duyệt. |
| Hết hạn hoặc gửi request mới sau giới hạn thu hồi | Bị từ chối trên cả cache hit và cache miss theo hợp đồng thời gian. |
| Phụ thuộc kiểm tra quyền không xác lập được kết quả hợp lệ | Không trả dữ liệu chẩn đoán; xử lý lỗi và ghi nhận theo yêu cầu. |
| Đối chiếu dấu vết | Liên kết được người thao tác, người phê duyệt, nhiệm vụ, quyền và kết quả; không có dữ liệu bị cấm. |

Bộ ca này cần được điều chỉnh theo các đường truy cập thực tế. Việc tất cả ca đã định nghĩa đều đạt là bằng chứng cho phạm vi đó, không phải chứng minh không tồn tại mọi đường lạm dụng có thể có.

## 10. Privileged actor trong kịch bản khẩn cấp

**Break-glass**, hay truy cập khẩn cấp, là cơ chế cho phép thực hiện các thao tác đã xác định khi luồng quản trị thông thường không dùng được hoặc không đáp ứng kịp tình huống sự cố. Nó không phải ngoại lệ để bỏ qua đặc tả bảo mật.

Cần nêu rõ điều kiện kích hoạt, người có quyền sử dụng, tài nguyên, thao tác, thời hạn, cách xác thực và đường ghi nhận. Nếu cơ chế được tạo để dùng khi hệ thống định danh chính bị lỗi, không thể coi việc chỉ kiểm tra qua chính hệ thống đó là một giải pháp khẩn cấp hoàn chỉnh.

Đồng thời phải bảo vệ phương tiện truy cập khẩn cấp, quy trách nhiệm được người sử dụng, phát hiện việc dùng, rà soát sau sự cố và vô hiệu hóa hoặc thay thế thông tin xác thực theo chính sách. Quy trình phục hồi bình thường cần bao gồm kết thúc quyền khẩn cấp còn mở.

Có thể có trường hợp không thực hiện được phê duyệt trước giống quy trình thông thường. Khi đó, yêu cầu phải mô tả rõ ngoại lệ, bằng chứng, thông báo và hậu kiểm, thay vì để người vận hành tự suy diễn lúc đang xử lý sự cố.

Diễn tập cần kiểm tra cơ chế thực sự dùng được khi phụ thuộc chính không sẵn sàng, đồng thời không mở đường truy cập thường trực không được giám sát. Đây là nơi yêu cầu bảo mật và phục hồi phải được thiết kế cùng nhau.

## 11. Các lỗi nhận diện thường gặp

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| Chỉ liệt kê vai trò có chữ `admin` | Bỏ sót pipeline, danh tính máy, nhóm và quyền hạ tầng. | Đi từ hành động nhạy cảm, tài sản và các đường thực thi. |
| Coi mọi quản trị viên có cùng quyền | Không thấy khác biệt tenant, môi trường và lớp kiểm soát. | Ghi từng phạm vi và điều kiện có hiệu lực. |
| Chỉ ghi quyền được cấp trực tiếp | Bỏ qua nhóm lồng nhau, ủy quyền và khả năng tự mở quyền. | Xem quyền hiệu lực, tổ hợp quyền và đường gián tiếp. |
| Tin rằng không có quyền ứng dụng thì không tác động được dữ liệu | Bỏ sót quyền sửa runtime, mã, bí mật hoặc bản sao lưu. | Phân tích cả mặt phẳng quản trị và xử lý dữ liệu. |
| Có log nhưng không biết ai khởi tạo tác vụ | Khó quy trách nhiệm khi danh tính máy dùng chung cho nhiều luồng. | Nối người khởi tạo khi có, danh tính thực thi, phiên và lần chạy. |
| Hai tài khoản khác tên được coi là hai người độc lập | Kiểm soát phê duyệt có thể bị cùng một người vượt qua. | Xét liên kết danh tính và quyền điều khiển tài khoản. |
| Quyền tạm hết hạn trên giao diện nhưng API vẫn dùng được | Không thực sự kết thúc đặc quyền. | Kiểm chứng tại API, cache, token và tác vụ liên quan. |
| Ghi mọi điều chưa biết là không có quyền | Tạo cảm giác phạm vi đã đầy đủ khi còn khoảng trống. | Giữ trạng thái chưa xác minh, chủ sở hữu và hành động làm rõ. |

## 12. Bài tập áp dụng

Một công ty bổ sung dịch vụ lập chỉ mục tìm kiếm cho tài liệu. Dịch vụ đọc nội dung từ kho chính, tạo chỉ mục và được triển khai qua pipeline. Nhóm hỗ trợ cần chạy lại một tác vụ lỗi; nhà cung cấp bên ngoài có quyền hỗ trợ nền tảng tìm kiếm trong một số sự cố.

Hãy thực hiện các bước sau:

1. Liệt kê privileged actor là con người và danh tính máy, bao gồm những người có thể điều khiển pipeline, danh tính dịch vụ và quyền hỗ trợ nhà cung cấp.
2. Chọn ít nhất ba hành động nhạy cảm, ghi tài sản, tenant, môi trường và tác động đến bí mật, toàn vẹn hoặc sẵn sàng.
3. Vẽ một đường đặc quyền gián tiếp và chỉ rõ các điều kiện phải thỏa cùng điểm kiểm soát có thể chặn đường đó.
4. Lập hồ sơ cho một actor, có mục đích, chủ sở hữu, phạm vi, thời hạn, phê duyệt, dấu vết, thu hồi và trạng thái xác minh.
5. Viết yêu cầu cho chạy lại tác vụ sao cho không tự mở rộng phạm vi dữ liệu hoặc sử dụng quyền đã thu hồi; nêu rõ chính sách với tác vụ đang chạy.
6. Đề xuất ca được phép, ca bị từ chối, ca hết hạn và ca phụ thuộc bị lỗi. Chỉ rõ bằng chứng quan sát được và các câu hỏi chưa thể kết luận.

Một kết quả tốt không dừng ở tên tài khoản có quyền cao. Nó giải thích được actor có thể làm gì, bằng đường nào, trong điều kiện nào và cơ chế nào bảo đảm quyền chỉ được sử dụng đúng mục đích. Từ đó, người thiết kế có thể đặt điểm kiểm soát, người kiểm thử có tiêu chí chấp nhận và nhóm vận hành có trách nhiệm rõ ràng khi quyền thay đổi hoặc có sự cố.
