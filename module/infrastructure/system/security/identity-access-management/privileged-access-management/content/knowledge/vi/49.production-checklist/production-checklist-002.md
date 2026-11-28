# Đã tách account thường và admin

## 1. Mục tiêu của mục kiểm tra

Trong checklist production của hệ thống quản lý truy cập đặc quyền (Privileged Access Management — PAM), “đã tách account thường và admin” phải thể hiện bằng cách hệ thống thực sự cấp, sử dụng và thu hồi quyền. Hai tên đăng nhập khác nhau chưa đủ để kết luận đã tách quyền.

Tài khoản thường phục vụ công việc hằng ngày: đọc thư, trao đổi, viết tài liệu, làm việc trên hệ thống nghiệp vụ và gửi yêu cầu truy cập. Tài khoản quản trị phục vụ những thao tác đặc quyền được cho phép trên phạm vi xác định, thông qua môi trường và quy trình quản trị tương ứng.

Mục tiêu là làm giảm khả năng một sự cố trong hoạt động hằng ngày biến ngay thành sự cố quản trị. Khi tài khoản thường bị chiếm, kẻ tấn công không được tự động có quyền quản trị hạ tầng, đọc kho bí mật, cấp quyền cho bản thân hoặc chiếm một phiên admin đã mở sẵn trong cùng môi trường bị xâm nhập.

Tách account là một lớp kiểm soát. Nó cần kết hợp với least privilege, JIT/JEA, xác thực phù hợp, vault, kiểm soát thiết bị, giám sát phiên và bằng chứng kiểm toán. Bản thân việc tạo thêm account không bảo đảm các lớp này đã hoạt động.

Sau bài học, người học cần có khả năng:

- Phân biệt tách danh tính với chỉ đổi tên account hoặc tách cửa sổ trình duyệt.
- Lập bản đồ giữa một con người, account thường, account admin và phạm vi quản trị.
- Kiểm tra quyền hiệu lực và các đường có thể gián tiếp dẫn tới đặc quyền.
- Thiết kế thử nghiệm dương tính, âm tính và thu hồi quyền để nghiệm thu.
- Đưa ra quyết định PASS, FAIL hoặc ngoại lệ được phê duyệt dựa trên bằng chứng.

## 2. Tách account nghĩa là tách những gì?

### 2.1. Ba khái niệm cần phân biệt

**Con người** là chủ thể chịu trách nhiệm, ví dụ một nhân viên có mã nhân sự ổn định.

**Danh tính hoặc account** là đối tượng mà hệ thống nhận diện và xác thực. Một người có thể sở hữu nhiều account phục vụ các mục đích khác nhau.

**Quyền hiệu lực** là tập hợp hành động chủ thể có thể thực hiện tại một thời điểm, sau khi xét quyền trực tiếp, nhóm, vai trò, chính sách, điều kiện, phiên đang hoạt động và các cơ chế ủy quyền.

Account không mang chữ “admin” vẫn có thể có đặc quyền. Ngược lại, account mang hậu tố “admin” có thể chưa được cấp quyền nào. Checklist phải kiểm tra khả năng thực thi hành động, không dùng quy ước đặt tên làm bằng chứng duy nhất.

Ví dụ minh họa:

| Thành phần | Danh tính minh họa | Mục đích | Giới hạn cần kiểm tra |
|---|---|---|---|
| Người chịu trách nhiệm | Mã nhân sự P-0187 | Gắn các account với cùng một chủ sở hữu | Không dùng tên hiển thị làm khóa duy nhất |
| Account thường | mai.nguyen | Công việc hằng ngày, gửi yêu cầu PAM | Không quản trị production, không tự cấp quyền admin |
| Account admin máy chủ | mai.ops-admin | Quản trị nhóm máy chủ ứng dụng được giao | Không mặc nhiên quản trị hệ thống danh tính hoặc toàn bộ cloud |
| Account admin danh tính | mai.identity-admin | Nhiệm vụ quản trị danh tính riêng nếu có | Tách phạm vi và đường sử dụng theo mô hình phân tầng |
| Workload identity | svc-payment-deploy | Triển khai tự động | Có owner nhưng không phải account admin cá nhân của Mai |

Không phải tổ chức nào cũng cần cùng một số account cho mỗi người. Số lượng và cách tách phụ thuộc ranh giới tin cậy, nền tảng và phạm vi nhiệm vụ. Tuy nhiên, không nên gom mọi cấp quản trị vào một account chỉ vì đã có một account thường riêng.

### 2.2. Bốn mặt cần tách

| Mặt kiểm soát | Điều cần chứng minh | Ví dụ chưa đạt |
|---|---|---|
| Danh tính | Account thường và admin là các đối tượng nhận diện riêng, có mục đích và owner rõ ràng | Hai bí danh cùng trỏ tới một đối tượng đang có quyền admin |
| Quyền | Account thường không có đặc quyền trực tiếp hoặc đường tự nâng quyền ngoài quy trình | Account thường vẫn thuộc nhóm quản trị lồng nhau |
| Ngữ cảnh sử dụng | Phiên admin đi qua thiết bị, kênh và ứng dụng quản trị được cho phép | Người dùng mở thư, tải tệp tùy ý trong phiên đang giữ token admin |
| Vòng đời và truy vết | Cấp, thay đổi, thu hồi và điều tra liên kết được từng account với con người | Nhân viên chuyển bộ phận nhưng account admin cũ không được rà soát |

Sự tách biệt về xác thực và khôi phục cũng phải được đánh giá. Hai account dùng chung một mật khẩu hoặc được lưu sẵn trong cùng trình duyệt tạo ra đường lan truyền dễ thấy. Với đăng nhập liên kết hoặc passwordless, cần kiểm tra chính sách thực tế thay vì giả định rằng “không dùng mật khẩu” đồng nghĩa đã độc lập.

Hai account có thể cùng phụ thuộc một nhà cung cấp danh tính và cùng một thiết bị xác thực đã được tổ chức phê duyệt. Khi đó vẫn tồn tại ranh giới tin cậy dùng chung. Cần hiểu rõ rủi ro đó và áp dụng chính sách cho thao tác admin; không tuyên bố hai account hoàn toàn độc lập chỉ vì chúng có ID khác nhau.

### 2.3. Tách account khác với JIT

JIT — Just-In-Time — giới hạn thời điểm và thời gian có quyền. Tách account giới hạn danh tính nào được dùng cho hoạt động đặc quyền.

Một mô hình phù hợp có thể là:

1. Nhân viên dùng account thường để gửi yêu cầu công việc.
2. PAM đánh giá yêu cầu, người phê duyệt và điều kiện truy cập.
3. Account admin hoặc phiên đặc quyền được gắn với danh tính quản trị đã định nghĩa.
4. Quyền hoặc phiên hết hiệu lực khi hết hạn hoặc bị thu hồi.
5. Log liên kết người yêu cầu, account admin, vai trò, tài nguyên và hành động.

Trong mô hình này, quyền gửi yêu cầu PAM của account thường không đồng nghĩa account thường đã trở thành admin của tài nguyên đích.

Ngược lại, nếu quy trình JIT chỉ thêm vai trò admin trực tiếp vào account dùng để đọc thư, đó là cấp quyền theo thời gian cho account thường. Nó chưa đáp ứng một tiêu chí yêu cầu tách account thường và account admin. Cần ghi rõ mô hình này để người nghiệm thu quyết định theo chính sách, thay vì đánh dấu PASS nhờ có nhãn JIT.

## 3. Tại sao hai account vẫn có thể cùng bị chiếm?

### 3.1. Quyền quản trị còn sót trên account thường

Một kỹ sư đã được tạo account admin riêng, nhưng account thường vẫn nằm trong nhóm có quyền sửa chính sách truy cập. Khi account thường bị chiếm, kẻ tấn công có thể cấp cho nó quyền quản trị, hoặc sửa cơ chế bảo vệ để sử dụng đặc quyền sau đó.

Những đường dẫn cần chú ý gồm:

- Quyền quản trị trực tiếp và quyền nhận từ nhóm lồng nhau.
- Khả năng sửa thành viên của nhóm có đặc quyền.
- Quyền đặt lại thông tin xác thực hoặc thay đổi cấu hình MFA của account admin.
- Quyền sửa chính sách, cấu hình ủy quyền hoặc cơ chế tạo token.
- Quyền đọc bí mật giúp đăng nhập bằng một danh tính đặc quyền khác.
- Quyền sửa pipeline, runner hoặc cấu hình triển khai có thể tác động production.

Quyền sửa một pipeline production có thể là một đường tác động đặc quyền, kể cả người sửa không có vai trò admin trong cloud. Cần xét các điều kiện bảo vệ trung gian, như phê duyệt thay đổi và danh tính triển khai, trước khi kết luận đường đó có thể khai thác được.

### 3.2. Tách account nhưng dùng chung phiên không an toàn

Nếu cả hai account được đăng nhập trong một môi trường đã bị xâm nhập, kẻ tấn công có thể tìm cách lợi dụng phiên admin, lấy token hoặc điều khiển hành động trong phiên đó. MFA không ngăn được mọi hành vi lạm dụng sau khi phiên đã được thiết lập.

Các trường hợp dễ bị hiểu sai:

- Hai cửa sổ trình duyệt trên cùng máy không tạo ra ranh giới tương đương hai môi trường được bảo vệ.
- Profile trình duyệt khác nhau hỗ trợ giảm nhầm account, nhưng không tự cô lập khỏi mã độc có quyền đủ cao trên máy.
- Máy ảo nằm trên máy cá nhân bị chiếm không mặc nhiên có mức bảo đảm như một thiết bị quản trị được quản lý riêng.
- Jump host hoặc proxy phiên có ích, nhưng cần kiểm tra cách nó xác thực, giữ bí mật, ghi log và hạn chế đường truy cập trực tiếp.

Mức tách môi trường cần được lựa chọn theo độ nhạy của quyền. Quản trị nền tảng danh tính thường cần ranh giới chặt hơn thao tác hạn chế trên một ứng dụng ít nhạy cảm.

### 3.3. Account thường kiểm soát được cơ chế khôi phục của admin

Nếu việc chiếm hộp thư của account thường cho phép đặt lại account admin ngay lập tức, quá trình khôi phục đã nối lại hai ranh giới.

Không thể kết luận có lỗ hổng chỉ vì email thông báo của admin gửi về hộp thư công việc. Câu hỏi cần trả lời là: người kiểm soát hộp thư đó có thể hoàn tất khôi phục, đổi yếu tố xác thực hoặc lấy đặc quyền mà không qua một kiểm soát độc lập hay không?

Cần xem cả quy trình hỗ trợ thủ công. Một help desk có thể vô tình bỏ qua sự tách biệt nếu cho phép reset account admin chỉ dựa vào thông tin hoặc phiên account thường bị chiếm.

### 3.4. Account admin dùng cho công việc hằng ngày

Account admin được tách riêng nhưng lại được dùng để đọc thư, duyệt nội dung tùy ý hoặc đăng nhập ứng dụng cá nhân sẽ tiếp xúc thêm các nguồn rủi ro.

Nếu nền tảng không có tính năng hộp thư cho account admin, việc “không cấp hộp thư” là một biện pháp tốt trong phạm vi đó. Nếu account admin vẫn có thể đăng nhập webmail, ứng dụng SaaS khác hoặc dịch vụ qua SSO, cần kiểm tra và áp dụng hạn chế tại lớp phù hợp. Không được đánh dấu “đã chặn” chỉ vì chưa cài ứng dụng trên máy.

## 4. Thiết lập mô hình account trước khi nghiệm thu

### 4.1. Xác định phạm vi đặc quyền

Liệt kê các hệ thống mà checklist sẽ bao phủ:

- Nền tảng danh tính và hệ thống cấp quyền.
- Máy chủ, hệ điều hành, thiết bị mạng và cơ sở dữ liệu.
- Tài khoản, dự án, subscription hoặc phạm vi quản trị cloud.
- Kubernetes, nền tảng container và hệ thống quản lý cấu hình.
- Vault, PAM, hệ thống backup và nền tảng ghi log.
- Công cụ CI/CD, kho mã và các workload có quyền triển khai.

Danh sách phải bao gồm cả control plane lẫn quyền truy cập dữ liệu nhạy cảm khi chúng thuộc phạm vi PAM. Có quyền thay đổi cấu hình và có quyền đọc toàn bộ dữ liệu là hai loại tác động khác nhau, nhưng cả hai đều có thể cần được bảo vệ như đặc quyền.

Phạm vi không được kiểm kê phải được ghi là chưa xác minh. Không suy rộng kết quả kiểm tra một nhóm máy chủ sang toàn bộ production.

### 4.2. Gắn account với owner ổn định

Đối với account admin cá nhân, cần có ít nhất:

- Mã chủ sở hữu ổn định.
- ID kỹ thuật của account và hệ thống quản lý account đó.
- Mục đích, nhóm tài nguyên và vai trò cho phép.
- Người phê duyệt, đơn vị vận hành và cơ chế thu hồi.
- Đường truy cập hợp lệ và yêu cầu xác thực.
- Ngày rà soát hoặc điều kiện phải rà soát lại.

Địa chỉ email hoặc tên hiển thị có thể đổi. Nên sử dụng một khóa ổn định và ánh xạ tới ID account ở từng hệ thống để tránh gán nhầm trách nhiệm.

Không cần đưa mật khẩu, khóa riêng, mã khôi phục hay token vào bảng kiểm kê. Bảng kiểm kê giữ tham chiếu tới hệ thống quản lý bí mật và hồ sơ phê duyệt.

### 4.3. Phân loại account ngoại lệ

Không ép mọi danh tính về mô hình “một người — một account thường — một account admin”:

| Loại danh tính | Cách kiểm soát phù hợp | Điểm không được bỏ qua |
|---|---|---|
| Account admin cá nhân | Ánh xạ trực tiếp với người sử dụng | Không chia sẻ thông tin xác thực giữa nhiều người |
| Account đặc quyền dùng chung ở hệ thống cũ | PAM cấp phiên hoặc checkout có quy trách nhiệm cá nhân | Log đăng nhập account dùng chung tại đích chưa đủ để xác định người dùng |
| Workload identity | Owner chịu trách nhiệm, quyền tối thiểu, quản lý credential/token | Không dùng account thường hoặc admin cá nhân để chạy dịch vụ lâu dài |
| Account khẩn cấp | Quy trình khẩn cấp riêng, kiểm tra khả dụng, giám sát mọi lần dùng | Không dùng hằng ngày và không loại khỏi kiểm kê |
| Account vendor | Gắn người và tổ chức cung cấp, phạm vi và thời hạn | Không coi tên nhà cung cấp chung là đủ để quy trách nhiệm |

Một ngoại lệ có kiểm soát vẫn phải hiện diện trong báo cáo. Ngoại lệ không làm tiêu chí gốc tự động trở thành PASS.

### 4.4. Quy định đường sử dụng admin

Với từng lớp quyền, xác định:

- Thiết bị hoặc môi trường quản trị được cho phép.
- Cách xác thực và yêu cầu xác thực tăng cường khi cần.
- Vai trò được phép yêu cầu và ai phê duyệt.
- Cơ chế JIT hoặc phạm vi JEA nếu được áp dụng.
- Thời hạn phiên, cách kết thúc và cách thu hồi.
- Đường log, cảnh báo và nơi lưu bằng chứng.
- Trường hợp nào được dùng đường khẩn cấp.

Nếu account admin có thể đi vòng qua PAM bằng SSH, RDP, console cloud hoặc API trực tiếp, cần chứng minh đường đó đã bị chặn hoặc là một đường được chấp thuận và được kiểm soát riêng. Có một đường PAM hoạt động không chứng minh những đường còn lại đã bị kiểm soát.

## 5. Quy trình triển khai và kiểm tra an toàn

### Bước 1 — Chụp trạng thái quyền hiện tại

Thu thập account, nhóm, vai trò và các quan hệ ủy quyền trong phạm vi. Với hệ thống cấp quyền theo điều kiện, ghi thêm điều kiện và thời điểm quan sát.

Phân biệt rõ:

- Quyền đang có hiệu lực.
- Quyền đủ điều kiện kích hoạt.
- Quyền đã cấu hình nhưng bị chặn bởi điều kiện.
- Phiên hoặc token được cấp trước một thay đổi quyền.

Ảnh chụp cấu hình chỉ là bằng chứng ở một thời điểm. Kết quả cần được đối chiếu với thử nghiệm hành vi.

### Bước 2 — Tạo hoặc xác nhận danh tính admin riêng

Kiểm tra rằng account admin là đúng đối tượng độc lập, có owner và mục đích, không phải một alias khác của account thường.

Áp dụng quyền tối thiểu theo nhiệm vụ và ranh giới quản trị. Nếu một người quản trị nhiều tầng nhạy cảm khác nhau, cần đánh giá việc tách tiếp các danh tính hoặc ngữ cảnh quản trị. Không tự động cấp quyền rộng cho account mới để “tránh thiếu quyền”.

### Bước 3 — Chuẩn bị xác thực, thiết bị và đường truy cập

Kiểm tra đường admin trước khi xóa quyền cũ:

1. Account admin xác thực được bằng cách đã phê duyệt.
2. Điều kiện thiết bị và kênh quản trị hoạt động.
3. PAM cấp đúng vai trò hoặc phiên cho tài nguyên thử nghiệm.
4. Giám sát ghi nhận được chủ thể cá nhân và hành động.
5. Có đường xử lý nếu cấu hình mới làm gián đoạn truy cập hợp lệ.

Thực hiện thử trên phạm vi nhỏ được phê duyệt trước khi mở rộng. Không kiểm tra bằng cách vô hiệu hóa hàng loạt account hay chủ động khóa toàn bộ đội vận hành.

### Bước 4 — Loại bỏ đặc quyền khỏi account thường

Gỡ các quyền trực tiếp và gián tiếp không thuộc mục đích hằng ngày. Đồng thời xử lý những đường tự cấp lại quyền, đọc credential hoặc sửa cơ chế tin cậy dẫn đến đặc quyền.

Một account thường vẫn có thể có quyền nghiệp vụ cần thiết, chẳng hạn chỉnh sửa tài liệu hoặc gửi yêu cầu triển khai. Cần phân biệt quyền nghiệp vụ đó với khả năng bỏ qua phê duyệt, sửa môi trường chạy hoặc thực thi thay đổi tùy ý trên production.

Ghi lại quyền đã gỡ, người phê duyệt và kết quả kiểm tra sau thay đổi. Không chỉ ghi “đã remove admin”.

### Bước 5 — Xử lý phiên và credential tồn tại từ trước

Thay đổi nhóm hoặc vai trò không bảo đảm mọi phiên cũ bị vô hiệu hóa ngay trên mọi nền tảng. Các hệ thống khác nhau có thể đánh giá quyền ở những thời điểm khác nhau.

Do đó cần kiểm tra:

- Phiên đăng nhập hiện có của account thường.
- Token và credential được cấp trước thay đổi.
- Kết nối dài hạn, phiên proxy và công việc đang chạy.
- Credential admin đã lưu trên máy hoặc trong công cụ của account thường.
- Khả năng sử dụng lại credential sau khi quyền đã được thu hồi.

Cách xử lý phải dựa trên cơ chế của từng hệ thống và kế hoạch thay đổi được phê duyệt: kết thúc phiên, thu hồi token, thay credential đã lộ hoặc đợi thời hạn có kiểm soát nếu chính sách cho phép. Không mặc định một thao tác “revoke” sẽ chấm dứt mọi loại token và kết nối.

### Bước 6 — Chạy kiểm thử và nghiệm thu

Dùng account thử nghiệm hoặc tài nguyên thử phù hợp, trong cửa sổ được cho phép. Các thao tác chứng minh quyền nên có tác động thấp, tránh dùng xóa dữ liệu hoặc thay đổi cấu hình nhạy cảm làm phép thử.

Sau mỗi thử nghiệm, lưu kết quả được phép hoặc bị từ chối, lý do, thời gian và tham chiếu log. Không ghi token hay secret vào ảnh chụp màn hình để chứng minh đã đăng nhập thành công.

## 6. Ma trận kiểm thử nghiệm thu

Bảng dưới là mẫu cần điều chỉnh theo nền tảng. “Thao tác quản trị thử” phải được định nghĩa trước, có thể quan sát và có tác động an toàn trong phạm vi kiểm tra.

| Mã | Chủ thể và điều kiện | Hành động kiểm tra | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|---|
| T01 | Account thường, phiên mới | Thao tác quản trị thử trên production trong phạm vi | Bị từ chối | Log quyết định quyền và ID account |
| T02 | Account thường | Sửa nhóm, vai trò hoặc chính sách để tự nhận đặc quyền | Bị chặn theo mô hình quyền | Quan hệ quyền được kiểm tra và log từ chối |
| T03 | Account thường | Đọc secret admin hoặc truy cập phiên admin qua đường không được phép | Bị từ chối | Log vault/PAM và cấu hình kiểm soát |
| T04 | Account admin, đúng thiết bị và kênh | Thực hiện đúng tác vụ đã duyệt | Được phép trong phạm vi | Yêu cầu, phê duyệt, phiên và hành động |
| T05 | Account admin | Quản trị tài nguyên ngoài phạm vi được giao | Bị từ chối | Log kiểm tra quyền tại tài nguyên đích |
| T06 | Account admin, sai điều kiện thiết bị/kênh | Đăng nhập hoặc mở phiên quản trị | Bị chặn tại điểm kiểm soát đã định nghĩa | Log điều kiện truy cập |
| T07 | Account admin | Sử dụng ứng dụng hằng ngày bị chính sách cấm | Bị chặn hoặc không được cấp khả năng đó | Chính sách ứng dụng và kiểm tra thực tế |
| T08 | Account thường từng có quyền | Dùng phiên hoặc token được cấp trước khi gỡ quyền | Không còn đặc quyền sau mốc thu hồi đã phê duyệt | Mốc thời gian và kết quả trước/sau |
| T09 | Người dùng hết nhiệm vụ | Tiếp tục hoặc tạo lại phiên admin sau thu hồi | Không vượt thời hạn thu hồi đã định nghĩa | Log PAM, IdP và hệ thống đích |
| T10 | Account thường | Yêu cầu quyền qua workflow PAM | Có thể gửi yêu cầu nếu được phép; chưa có quyền admin tại đích | Log yêu cầu và kiểm tra quyền trước phê duyệt |
| T11 | Account thường bị giả lập chiếm quyền | Hoàn tất reset admin chỉ bằng quyền của account thường | Không thể bỏ qua kiểm soát khôi phục độc lập đã thiết kế | Kịch bản kiểm thử quy trình hỗ trợ |
| T12 | Account khẩn cấp trong diễn tập được duyệt | Mở truy cập khẩn cấp và đóng phiên | Hoạt động theo runbook, phát sinh cảnh báo và dấu vết đầy đủ | Hồ sơ diễn tập và log |

T07 phải dựa trên khả năng thực tế của nền tảng. Nếu một lớp chưa hỗ trợ chặn ứng dụng theo account, ghi rõ giới hạn và biện pháp bù trừ được phê duyệt. Không viết kết quả mong đợi giả tạo rồi đánh dấu PASS bằng việc người dùng hứa không sử dụng.

T08 và T09 phải có mốc thời gian do tổ chức định nghĩa. Không áp dụng một con số mặc định cho mọi loại token, tài nguyên và mức rủi ro. Nếu nền tảng không đáp ứng thời hạn thu hồi yêu cầu, đó là một khoảng trống cần xử lý.

Thử nghiệm dương tính cho biết công việc hợp lệ vẫn thực hiện được. Thử nghiệm âm tính cho biết ranh giới đã chặn đường không hợp lệ. Cần cả hai; chỉ đăng nhập admin thành công chưa nghiệm thu được sự tách biệt.

## 7. Gói bằng chứng để đánh dấu checklist

### 7.1. Nội dung tối thiểu

Một hồ sơ nghiệm thu có thể gồm:

1. Phạm vi tài nguyên, hệ thống danh tính và thời điểm kiểm tra.
2. Bảng ánh xạ owner, account thường, account admin và vai trò.
3. Kết quả kiểm tra quyền trực tiếp, gián tiếp và các đường tự nâng quyền.
4. Chính sách cho ứng dụng, thiết bị, kênh admin và khôi phục account.
5. Kết quả các ca kiểm thử áp dụng, bao gồm thu hồi phiên hoặc token cũ.
6. Tham chiếu tới log cá nhân, phiên và tài nguyên đích.
7. Danh sách ngoại lệ, người chấp nhận rủi ro và thời hạn xử lý.
8. Người thực hiện, người rà soát và quyết định cuối cùng.

Người rà soát nên có mức độc lập phù hợp với rủi ro. Việc một admin tự xác nhận toàn bộ quyền của chính mình mà không có đối chiếu làm giảm giá trị kiểm soát.

Bằng chứng chứa thông tin về cấu trúc quyền và hoạt động quản trị cũng là dữ liệu nhạy cảm. Cần phân quyền truy cập, giới hạn dữ liệu thu thập và lưu theo chính sách của tổ chức.

### 7.2. Mẫu ghi nhận một lần kiểm tra

Mẫu YAML sau chỉ minh họa hồ sơ vận hành, không phải cấu hình triển khai và không chứa thông tin xác thực:

```yaml
checkId: PAM-ACCOUNT-SEPARATION
scope:
  environment: production
  systems:
    - identity-platform
    - application-server-group-a
inspection:
  reviewer: security-reviewer-02
  privilegeSnapshotRef: evidence/access-review-184
  identityMappingRef: evidence/identity-map-184
  testRunRef: evidence/test-run-184
results:
  ordinaryAccountAdminRights: FAIL
  approvedAdminPath: PASS
  traceability: PASS
findings:
  - id: FINDING-021
    description: Account thường còn quyền sửa nhóm quản trị qua nhóm lồng nhau
    owner: identity-operations
    disposition: REMEDIATION_REQUIRED
decision: NO_GO_FOR_AFFECTED_SCOPE
```

Điểm quan trọng là quyết định phù hợp với finding. Hồ sơ không được ghi “đã tách account” trong khi chính kết quả kiểm tra còn cho thấy account thường có thể cấp lại đặc quyền.

Sau khi khắc phục, tạo bằng chứng kiểm tra lại liên kết với finding cũ. Giữ lịch sử trước và sau để người rà soát hiểu điều gì đã thay đổi.

### 7.3. Truy vết xuyên hệ thống

Một chuỗi bằng chứng hữu ích cần nối được:

```text
Người chịu trách nhiệm
  -> account gửi yêu cầu
  -> yêu cầu và phê duyệt
  -> account hoặc danh tính quản trị tại đích
  -> vai trò / phạm vi được cấp
  -> phiên hoặc token có liên quan
  -> hành động trên tài nguyên
  -> kết thúc / thu hồi quyền
```

Các ID ở từng bước có thể khác nhau. Cần có khóa tương quan hoặc ánh xạ đủ tin cậy; trùng tên hiển thị không phải cơ chế tương quan chắc chắn.

Với hệ thống đích chỉ thấy account dùng chung, PAM phải cung cấp bằng chứng ai được cấp phiên hoặc checkout tại thời điểm đó. Nếu nhiều người cùng dùng một credential ngoài PAM và không có cơ chế phân biệt hành động, không thể suy ra chắc chắn người thực hiện chỉ từ log đăng nhập account chung.

## 8. Cách đo mức độ hoàn thành

Không nên dùng riêng chỉ số “đã tạo bao nhiêu account admin”. Chỉ số đó đo việc provision account, chưa đo việc tách quyền.

Có thể theo dõi các chỉ số sau, với mẫu số được định nghĩa rõ:

| Chỉ số | Mẫu số | Điều kiện được tính đạt |
|---|---|---|
| Tỷ lệ người dùng đặc quyền đã được kiểm tra tách account | Người có khả năng sử dụng đặc quyền trong phạm vi | Có ánh xạ account và đã kiểm tra quyền, đường truy cập, thu hồi theo tiêu chí |
| Tỷ lệ danh tính có owner hợp lệ | Mọi danh tính đặc quyền được kiểm kê, kể cả khẩn cấp và workload | Owner còn hợp lệ và có người chịu trách nhiệm vòng đời |
| Tỷ lệ ranh giới đã kiểm thử | Cặp danh tính — phạm vi quyền được lựa chọn theo kế hoạch kiểm thử | Có kết quả dương tính, âm tính và bằng chứng tương ứng |
| Số đường đặc quyền còn tồn tại trên account thường | Toàn bộ finding trong phạm vi | Theo dõi số còn mở và mức độ tác động, không chỉ số account |
| Số ngoại lệ quá hạn | Mọi ngoại lệ được phê duyệt | Không còn được coi là ngoại lệ hợp lệ khi đã hết hạn |

Ví dụ: một đơn vị có 24 người sử dụng đặc quyền. Cả 24 người đều đã có account admin riêng, nhưng 2 người vẫn dùng account thường có quyền sửa nhóm admin. Khi đó:

- Tỷ lệ tạo account admin riêng là 24/24.
- Số người đã chứng minh tách quyền không thể báo là 24/24.
- Nếu 22 người còn lại đã hoàn tất đầy đủ tiêu chí kiểm tra, tỷ lệ đạt theo người là 22/24.
- Cần báo riêng các hệ thống chưa kiểm kê và những loại danh tính không thuộc mẫu số theo người.

Một finding liên quan nhóm dùng chung có thể tác động nhiều người. Không được suy diễn rằng “chỉ có một finding” nghĩa là chỉ có một account bị ảnh hưởng.

Các tỷ lệ giúp theo dõi tiến độ nhưng không thay thế đánh giá rủi ro. Một account thường có thể quản trị nền tảng danh tính vẫn có thể là lý do chặn go-live của phạm vi liên quan, dù tỷ lệ hoàn thành chung rất cao.

## 9. Quyết định PASS, FAIL và ngoại lệ

### 9.1. Khi nào có thể PASS?

Trong phạm vi được đánh giá, có thể đề xuất PASS khi:

- Account thường và admin được nhận diện riêng, có owner và mục đích rõ ràng.
- Account thường không giữ đặc quyền trái chính sách hoặc khả năng tự cấp lại đặc quyền ngoài kiểm soát.
- Account admin có phạm vi nhiệm vụ, đường truy cập và điều kiện sử dụng được thực thi.
- Không còn phiên hoặc credential cũ làm vô hiệu hóa kết quả tách quyền theo tiêu chí thu hồi.
- Các ca kiểm thử áp dụng đã có kết quả và bằng chứng.
- Account đặc thù được xử lý theo mô hình riêng và được báo cáo đầy đủ.
- Người có thẩm quyền đã rà soát kết quả, phạm vi và các giới hạn.

PASS chỉ có giá trị cho phạm vi và thời điểm được ghi nhận. Thêm quyền, đổi nhóm, thay phương thức khôi phục hoặc thay kiến trúc truy cập có thể khiến cần kiểm tra lại.

### 9.2. Những dấu hiệu nên ghi FAIL

Các ví dụ thường làm tiêu chí chưa đạt:

- Account thường còn quyền admin hoặc có thể tự thêm mình vào nhóm admin.
- Account admin không ánh xạ được tới người sử dụng hoặc đang dùng chung ngoài kiểm soát.
- Có đường truy cập trực tiếp vượt qua cơ chế admin đã thiết kế.
- Account thường có thể lấy credential admin từ nơi lưu không được bảo vệ.
- Thay đổi quyền đã thực hiện nhưng phiên cũ vẫn giữ đặc quyền vượt yêu cầu thu hồi.
- Không có bằng chứng kiểm tra; chỉ có lời xác nhận hoặc danh sách tên account.
- Mô hình khôi phục cho phép dùng riêng account thường để chiếm account admin trái chính sách.

Mức độ chặn go-live cần gắn với phạm vi bị ảnh hưởng và chính sách rủi ro. Không dùng tỷ lệ hoàn thành của toàn dự án để che một đường chiếm quyền quan trọng.

### 9.3. Ngoại lệ phải có giới hạn

Một hệ thống cũ có thể chỉ hỗ trợ một account quản trị chung. Ngoại lệ có thể được xem xét khi có lý do kỹ thuật và biện pháp bù trừ, chẳng hạn:

- Xác thực cá nhân trước khi mở phiên qua PAM.
- Hạn chế truy cập trực tiếp từ mạng hoặc thiết bị khác.
- Cấp phiên hoặc checkout theo quy trình được phê duyệt.
- Ghi nhận hành động và kiểm tra tương quan với người sử dụng.
- Quản lý, thay đổi credential theo khả năng nền tảng và chính sách.
- Theo dõi một kế hoạch loại bỏ giới hạn của hệ thống cũ.

Hồ sơ cần có phạm vi, rủi ro còn lại, owner, người chấp nhận rủi ro, thời hạn và ngày rà soát. Ghi quyết định như “GO_WITH_APPROVED_EXCEPTION” nếu quy trình tổ chức cho phép, đồng thời thể hiện tiêu chí gốc chưa được đáp ứng hoàn toàn. Không đổi ngoại lệ thành PASS tuyệt đối.

Không phải rủi ro nào cũng có thể được bù trừ bằng ghi hình phiên. Nếu không ngăn hoặc phát hiện được việc dùng credential ở đường ngoài PAM, bản ghi phiên qua PAM không bao phủ hành vi đó.

## 10. Tình huống thực hành

Một nhóm vận hành có 24 kỹ sư quản trị production. Dự án PAM đã tạo account admin riêng cho từng người, yêu cầu truy cập qua một cổng quản trị và ghi log phiên.

Trong đợt nghiệm thu, nhóm phát hiện:

1. Hai account thường vẫn nhận quyền sửa thành viên nhóm quản trị qua một nhóm lồng nhau.
2. Một account admin vẫn đăng nhập được ứng dụng thư điện tử qua SSO.
3. Một phiên quản trị được mở trước khi gỡ quyền vẫn thực hiện được thao tác trong khoảng thời gian chưa được nhóm đánh giá.
4. Bốn máy chủ cũ sử dụng một account admin chung; ba máy đã đi qua PAM, máy còn lại cho phép truy cập trực tiếp.
5. Bảng ánh xạ chỉ có email, thiếu ID account tại một số hệ thống.

### 10.1. Đánh giá

Không thể kết luận đã hoàn tất tách account chỉ vì cả 24 kỹ sư đều có hai account.

Hai account thường có quyền sửa nhóm cho thấy còn đường tác động đặc quyền. Cần phân tích quyền hiệu lực và loại bỏ đường này theo thiết kế, sau đó kiểm tra lại bằng một thao tác an toàn.

Việc account admin đăng nhập được thư điện tử là khoảng trống nếu chính sách cấm admin dùng ứng dụng hằng ngày. Cần chặn tại nơi thực thi phù hợp hoặc ghi ngoại lệ đúng quy trình nếu nền tảng chưa hỗ trợ.

Phiên cũ đòi hỏi xác định hành vi thu hồi thực tế, thời hạn yêu cầu và cơ chế kết thúc phiên. Không đủ dữ liệu để tuyên bố đã đạt hay tự chọn một thời hạn chấp nhận.

Máy chủ cho phép dùng account chung ngoài PAM có khoảng trống truy vết và kiểm soát đường truy cập. Cần xử lý đường đi vòng hoặc một ngoại lệ có giới hạn được phê duyệt.

Bảng ánh xạ cần được hoàn thiện bằng định danh ổn định để phục vụ thay đổi nhân sự và đối chiếu log.

### 10.2. Thứ tự xử lý có thể áp dụng

- Xác định và kiểm soát các đường khiến account thường có thể tác động đặc quyền.
- Kiểm tra đường admin hợp lệ để bảo đảm vận hành vẫn thực hiện được nhiệm vụ.
- Gỡ quyền cũ và xử lý phiên, token hoặc credential còn hiệu lực.
- Hạn chế ứng dụng hằng ngày trên danh tính admin theo chính sách.
- Đóng hoặc kiểm soát đường truy cập trực tiếp vào máy chủ dùng account chung.
- Hoàn thiện ánh xạ và kiểm tra lại các ca liên quan.
- Gửi kết quả, phạm vi còn mở và ngoại lệ tới người quyết định go-live.

Thứ tự thực tế phải xét tác động vận hành. Không khóa hàng loạt account trước khi chứng minh có đường admin hợp lệ và phương án khôi phục phù hợp.

### 10.3. Câu hỏi tự kiểm tra

**Có hai tên đăng nhập khác nhau thì đã tách account chưa?**

Chưa đủ. Cần xác nhận hai đối tượng danh tính, quyền hiệu lực, đường sử dụng và vòng đời. Hai tên khác nhau có thể vẫn dẫn tới cùng một đối tượng hoặc cùng giữ đặc quyền.

**Account thường được gửi yêu cầu PAM có vi phạm không?**

Không tự động vi phạm. Cần phân biệt quyền gửi yêu cầu với quyền quản trị tại đích. Phiên hoặc danh tính thực hiện thao tác đặc quyền phải đáp ứng mô hình đã phê duyệt.

**Bỏ account thường khỏi một nhóm admin đã đủ chưa?**

Chưa chắc. Có thể còn nhóm lồng nhau, quyền trực tiếp, vai trò khác, đường cấp lại quyền hoặc phiên cũ. Kết quả phải dựa trên quyền hiệu lực và thử nghiệm.

**Hai profile trình duyệt có thay thế được môi trường quản trị riêng không?**

Không nên coi là tương đương. Profile giúp tách trạng thái trình duyệt nhưng vẫn dùng chung hệ điều hành và có thể cùng bị tác động khi thiết bị bị chiếm.

**Dịch vụ chạy bằng account admin của kỹ sư có được tính là đã tách không?**

Không đáp ứng mục tiêu vòng đời riêng giữa con người và workload. Dịch vụ cần danh tính và owner phù hợp, quyền tối thiểu và quy trình credential/token riêng.

**Tài khoản khẩn cấp có thể bị bỏ qua để dễ PASS không?**

Không. Nó cần được kiểm kê, kiểm thử và giám sát theo quy trình khẩn cấp. Không dùng hàng ngày không có nghĩa là không có đặc quyền.

## 11. Checklist dùng trước khi ký nghiệm thu

- [ ] Phạm vi hệ thống, tài nguyên và thời điểm kiểm tra đã được ghi rõ.
- [ ] Mọi danh tính đặc quyền trong phạm vi được kiểm kê và phân loại.
- [ ] Account admin cá nhân liên kết với owner bằng khóa ổn định.
- [ ] Account thường và admin là các đối tượng danh tính riêng theo mô hình đã duyệt.
- [ ] Quyền trực tiếp, nhóm lồng nhau, vai trò và các đường tự nâng quyền đã được kiểm tra.
- [ ] Account thường không thể lấy credential hoặc chiếm quyền admin qua đường khôi phục trái chính sách.
- [ ] Phạm vi quyền và đường sử dụng từng lớp account admin được xác định.
- [ ] Chính sách thiết bị, xác thực và ứng dụng hằng ngày đã được kiểm thử tại điểm thực thi.
- [ ] Đường truy cập ngoài PAM hoặc ngoài kênh quản trị được kiểm soát rõ ràng.
- [ ] Phiên, token và credential có trước thay đổi đã được xử lý theo yêu cầu thu hồi.
- [ ] Kiểm thử hợp lệ, bị từ chối và thu hồi đã có kết quả.
- [ ] Log liên kết được người dùng, account admin, phiên và hành động tại đích.
- [ ] Workload, vendor, account dùng chung và account khẩn cấp có kiểm soát riêng.
- [ ] Finding và ngoại lệ còn mở có owner, quyết định và thời hạn.
- [ ] Người rà soát đã đối chiếu bằng chứng trước khi ký quyết định.

Khi ký, ghi rõ phạm vi đạt, bằng chứng tham chiếu, những giới hạn còn lại và điều kiện phải đánh giá lại. Một dấu tích chỉ có giá trị khi người vận hành có thể dùng hồ sơ đó để chứng minh ranh giới giữa công việc hằng ngày và hoạt động đặc quyền đang được thực thi.
