# Key passphrase

## 1. Mục tiêu và bối cảnh PAM

Trong chương **SSH và key**, passphrase là lớp bảo vệ cho khóa riêng SSH được lưu dưới dạng tệp. Với tài khoản quản trị, mất tệp khóa riêng có thể dẫn đến mất quyền kiểm soát máy chủ, thiết bị mạng hoặc dữ liệu nhạy cảm. Một passphrase được chọn và vận hành đúng giúp giảm khả năng kẻ lấy được tệp khóa sử dụng ngay thông tin xác thực đó.

Bài học thuộc phạm vi **Privileged Access Management (PAM)**: quản lý khóa của người quản trị và dịch vụ, gắn quyền với chủ sở hữu, giới hạn thời gian sử dụng và lưu bằng chứng vận hành. Passphrase chỉ giải quyết một phần của bài toán; việc một khóa có được phép đăng nhập, được chạy lệnh gì và phải đi qua quy trình phê duyệt nào vẫn cần kiểm soát riêng.

Sau bài học, người học có thể:

- Phân biệt passphrase của khóa riêng với mật khẩu tài khoản, mã PIN thiết bị và yếu tố xác thực bổ sung.
- Giải thích passphrase bảo vệ được gì khi tệp khóa bị sao chép và vì sao bảo vệ đó có giới hạn.
- Tạo hoặc cập nhật khóa có passphrase bằng OpenSSH mà không đưa bí mật vào dòng lệnh.
- Sử dụng agent có thời hạn mà vẫn nhận biết rủi ro trên máy trạm và qua máy trung gian.
- Chọn cách xử lý đúng khi quên passphrase, mất thiết bị hoặc nghi ngờ lộ khóa.
- Xác định bằng chứng có thể thu thập cho PAM mà không ghi lại passphrase hay khóa riêng.

Các lệnh minh họa sử dụng OpenSSH trên môi trường Unix với shell tương thích POSIX. Đường dẫn, agent và cơ chế lưu bí mật của Windows, macOS hoặc sản phẩm PAM có thể khác. Khi thực hành, dùng tài khoản và khóa thử nghiệm; không thay khóa quản trị đang vận hành chỉ để làm bài lab.

## 2. Passphrase nằm ở đâu trong cơ chế SSH?

### 2.1. Khóa công khai, khóa riêng và passphrase

Một cặp khóa SSH gồm hai thành phần có vai trò khác nhau:

| Thành phần | Vai trò | Cách bảo quản |
| --- | --- | --- |
| Public key, thường là tệp có đuôi `.pub` | Cho bên xác minh nhận diện khóa và kiểm tra chữ ký | Phân phối có kiểm soát đến đúng tài khoản, máy chủ hoặc hệ thống cấp chứng chỉ |
| Private key | Tạo chữ ký để chứng minh đang có quyền sử dụng khóa tương ứng | Giữ bí mật; giới hạn nơi lưu, người truy cập và khả năng sao chép |
| Passphrase của private key | Mở khóa vật liệu khóa riêng đã được mã hóa trong tệp | Không chia sẻ, không ghi cùng tệp khóa, không gửi cho máy chủ để đăng nhập |

Với xác thực public key thông thường, SSH client sử dụng khóa riêng để ký dữ liệu xác thực của kết nối. Máy chủ kiểm tra chữ ký bằng khóa công khai được tin cậy. Passphrase dùng để mở tệp khóa trên phía client; nó không trở thành mật khẩu của tài khoản đích.

Một public key có thể được chấp nhận trên nhiều máy chủ. Đổi passphrase không thay đổi danh tính mật mã của cặp khóa và không tự thu hẹp số máy chủ đang tin khóa đó. Vì vậy, kiểm kê nơi sử dụng public key vẫn là nhiệm vụ của PAM.

### 2.2. Phân biệt các lời nhắc thường gặp

| Lời nhắc hoặc bí mật | Ai cần xử lý? | Ý nghĩa |
| --- | --- | --- |
| `Enter passphrase for key '...'` | Client hoặc thành phần mở khóa cục bộ | Cần mở khóa riêng đã mã hóa |
| Mật khẩu đăng nhập tài khoản đích | Cơ chế xác thực của hệ thống đích | Đang dùng hoặc bổ sung phương thức xác thực bằng mật khẩu |
| Mã OTP hoặc phê duyệt đăng nhập | Hệ thống xác thực bổ sung | Kiểm tra yếu tố hoặc điều kiện ngoài khóa |
| PIN của security key | Thiết bị và phần mềm tích hợp | Cho phép một thao tác theo chính sách của thiết bị |

Việc nhập passphrase rồi đăng nhập thành công không tự chứng minh hệ thống đã triển khai MFA ở máy chủ. Nếu client hoặc agent đã mở khóa, phía máy chủ thường chỉ nhìn thấy một lần xác thực bằng khóa. Muốn yêu cầu MFA cho quyền quản trị, phải thiết kế và kiểm tra luồng xác thực tương ứng tại bastion, PAM gateway, hệ thống cấp chứng chỉ hoặc máy chủ.

Không nhập passphrase của khóa vào một biểu mẫu, ticket hay lời nhắc không rõ nguồn chỉ vì màn hình có chữ “SSH”. Khi xuất hiện lời nhắc bất thường, cần xác định chương trình và thao tác nào đang yêu cầu bí mật.

## 3. Cách bảo vệ và giới hạn của passphrase

### 3.1. Mã hóa tệp khóa và chi phí đoán ngoại tuyến

Khi lưu một khóa riêng có passphrase, phần mềm dùng passphrase cùng tham số dẫn xuất khóa để bảo vệ vật liệu khóa trong tệp. Người chỉ lấy được tệp mã hóa cần tìm được passphrase hoặc khai thác một điểm yếu khác trước khi sử dụng vật liệu đó.

OpenSSH hỗ trợ tùy chọn `ssh-keygen -a` để điều chỉnh số vòng của hàm dẫn xuất khóa khi lưu private key; tăng số vòng làm thao tác mở khóa tốn thời gian hơn. Ví dụ `-a 100` trong bài là tham số thực hành, không phải mức bắt buộc cho mọi tổ chức. Cần đo độ trễ trên thiết bị thực tế và áp dụng chính sách đã thống nhất. Tham chiếu cú pháp tại [ssh-keygen — OpenBSD](https://man.openbsd.org/ssh-keygen).

Chi phí dẫn xuất khóa và độ khó đoán của passphrase bổ sung cho nhau. Một bí mật dựa trên tên công ty, tên dự án hoặc mẫu bàn phím vẫn có thể nằm trong những thử đoán đầu tiên. Tăng chi phí xử lý không biến một bí mật dễ đoán thành bí mật mạnh.

Nếu kẻ tấn công đã có bản sao tệp, việc đoán có thể diễn ra ngoại tuyến. Cơ chế khóa tài khoản sau nhiều lần đăng nhập sai trên máy chủ không chặn được quá trình đoán trên bản sao này. Log SSH cũng không cho biết số lần kẻ đó đã thử mở tệp ở máy khác.

### 3.2. Mô hình đe dọa

| Tình huống | Vai trò của passphrase | Kiểm soát cần bổ sung |
| --- | --- | --- |
| Bản sao tệp khóa bị lấy khỏi thiết bị đang tắt | Cản việc sử dụng trực tiếp vật liệu khóa đã mã hóa | Mã hóa ổ đĩa, giới hạn bản sao, điều tra và thu hồi theo rủi ro |
| Người khác đọc được thư mục backup | Giảm khả năng sử dụng ngay khóa có trong backup | Phân quyền backup, tách bí mật mở khóa, quản lý vòng đời bản sao |
| Máy trạm có mã độc khi người dùng mở khóa | Không bảo đảm bí mật nhập vào hoặc thao tác ký còn an toàn | Bảo vệ endpoint, cô lập thiết bị, thay thông tin xác thực từ môi trường sạch |
| Agent đang sẵn sàng ký | Tệp trên đĩa có thể vẫn được mã hóa nhưng quyền dùng khóa đang mở | Giới hạn thời gian agent, bảo vệ socket và phiên người dùng |
| Khóa đã được cấp quyền quản trị quá rộng | Không giảm quyền mà máy chủ đã cấp cho public key | Least privilege, phân tầng quản trị, JIT/JEA |
| Người cũ vẫn có bản sao khóa và biết passphrase | Không ngăn được người đó dùng bản sao cũ | Thu hồi public key hoặc chứng chỉ, thay cặp khóa và rà soát phiên |
| Phiên SSH đã xác thực đang tồn tại | Không tự kết thúc phiên | Chính sách timeout và cơ chế đóng phiên trong hệ thống quản trị |

Một cách kiểm tra thiết kế là hỏi đồng thời: **kẻ tấn công lấy được gì, lúc nào, và họ còn cần điều kiện nào để sử dụng quyền?** Câu trả lời “khóa đã có passphrase” chưa đủ nếu cả tệp, bí mật mở khóa và agent đều nằm trong cùng vùng đã bị chiếm quyền.

### 3.3. Ba đồng hồ không thay thế nhau

Trong vận hành PAM, ba thời hạn thường bị nhầm lẫn:

1. **Thời gian giữ khóa trong agent:** ảnh hưởng đến khả năng agent ký cho các lần xác thực tiếp theo.
2. **Thời hạn quyền hoặc chứng chỉ:** ảnh hưởng đến việc hệ thống đích còn chấp nhận một lần xác thực mới hay không.
3. **Thời hạn phiên đã mở:** ảnh hưởng đến phiên đang hoạt động sau khi đã xác thực.

Agent hết hạn không có nghĩa phiên SSH đang mở bị đóng. Chứng chỉ hết hạn cũng không mặc nhiên cắt phiên đã được thiết lập. Muốn kết thúc quyền thao tác đúng thời điểm, PAM cần quản lý cả ba, phù hợp với cách hệ thống triển khai.

## 4. Chọn passphrase và chính sách sử dụng

### 4.1. Ưu tiên tính khó đoán, duy nhất và khả năng sử dụng

Passphrase nên được tạo từ nguồn ngẫu nhiên đáng tin cậy hoặc bằng công cụ quản lý bí mật được tổ chức chấp thuận. Nếu dùng nhiều từ để dễ nhập, các từ cần được chọn ngẫu nhiên, không phải một câu quen thuộc do người dùng tự nghĩ.

Một minh họa về không gian lựa chọn: nếu mỗi từ được chọn độc lập, đều nhau từ danh sách 2.048 từ, sáu từ tạo ra `2048^6` khả năng, tương đương 66 bit về mặt lý thuyết. Con số này không áp dụng cho sáu từ trích từ lời bài hát, một câu nói phổ biến hay quy luật đã biết. Nó cũng không tự quyết định chính sách cho mọi khóa quản trị.

Các nguyên tắc vận hành cần đi cùng độ khó đoán:

- Dùng bí mật riêng cho khóa quản trị; không tái sử dụng mật khẩu đăng nhập hoặc mật khẩu cá nhân.
- Không đưa tên khách hàng, môi trường hoặc thông tin dễ tra cứu thành quy luật tạo bí mật.
- Không dùng ví dụ trong tài liệu làm passphrase thật.
- Không lưu bí mật trong cùng thư mục, cùng gói nén hoặc cùng ticket với private key.
- Cân nhắc cách nhập trên thiết bị được phép sử dụng, đặc biệt khi có nhiều bố cục bàn phím.
- Xác minh cách khôi phục quyền truy cập trước khi triển khai diện rộng.

Unicode và khoảng trắng có thể xuất hiện trong passphrase, nhưng khả năng nhập nhất quán giữa các công cụ cần được kiểm thử. Tránh để một thay đổi bàn phím hoặc quy tắc xử lý ký tự khiến quy trình khẩn cấp không thực hiện được.

### 4.2. Tách chính sách theo loại danh tính

| Loại danh tính | Hướng thiết kế | Câu hỏi PAM phải trả lời |
| --- | --- | --- |
| Quản trị viên tương tác | Khóa cá nhân có bảo vệ, thiết bị được quản lý, agent có thời hạn | Ai là chủ sở hữu? Khi nào được mở khóa? Quyền nào được cấp? |
| Nhà thầu hoặc truy cập tạm thời | Danh tính cá nhân, phạm vi hẹp, thời hạn rõ và thu hồi theo hợp đồng | Có thể vô hiệu hóa quyền mà không phải thu lại mọi bản sao tệp không? |
| Workload chạy tự động | Danh tính riêng của workload, ưu tiên thông tin xác thực ngắn hạn hoặc cơ chế cấp phát phù hợp | Thành phần nào được quyền yêu cầu và sử dụng credential? |
| Tài khoản break-glass | Quy trình khẩn cấp được kiểm soát, có giám sát, thử nghiệm và hậu kiểm | Khi người giữ passphrase không sẵn sàng thì hệ thống phục hồi ra sao? |

Không giải quyết việc một job không thể nhập passphrase bằng cách đặt tệp khóa và passphrase vào cùng script. Nếu job đọc được cả hai, người chiếm quyền chạy job thường có thể đạt quyền sử dụng tương tự.

Với hệ thống buộc phải dùng khóa tĩnh, cần ghi nhận ngoại lệ và áp dụng các giới hạn có thể thực thi: tài khoản riêng, môi trường chạy được quản lý, quyền tối thiểu, đích kết nối cụ thể, nơi lưu bí mật được kiểm soát và quy trình thay khóa. Một vault có thể giúp quản lý việc cấp phát và bằng chứng truy cập, nhưng vẫn phải xác định workload nào được phép lấy hoặc yêu cầu sử dụng khóa.

Passphrase của khóa người quản trị không nên trở thành bí mật chung của cả nhóm. Mỗi người cần danh tính có thể truy vết; việc chia sẻ một cặp khóa làm yếu trách nhiệm cá nhân, kể cả khi tệp được mã hóa.

## 5. Quy trình tạo và kiểm tra khóa có passphrase

### 5.1. Chuẩn bị một đích lưu riêng

Các lệnh sau minh họa việc tạo khóa thử nghiệm mới. Kiểm tra trước rằng tên tệp chưa tồn tại. Nếu công cụ hỏi có ghi đè một tệp hiện có hay không, dừng lại và chọn đường dẫn khác.

~~~bash
umask 077
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

ssh-keygen -t ed25519 -a 100 \
  -f "$HOME/.ssh/pam_passphrase_lab" \
  -C "pam-passphrase-lab"
~~~

Nhập passphrase tại lời nhắc tương tác, rồi nhập lại để xác nhận. Không để trống trong bài thực hành này. Nếu môi trường có yêu cầu thuật toán khác, sử dụng thuật toán đã được phê duyệt thay vì cố áp dụng Ed25519 cho mọi nền tảng.

Hai tệp được tạo có mục đích khác nhau:

~~~text
~/.ssh/pam_passphrase_lab       # private key: không phân phối
~/.ssh/pam_passphrase_lab.pub   # public key: dùng để đăng ký quyền
~~~

Không đưa giá trị bí mật vào tham số dòng lệnh, shell history, biến cấu hình của dự án hoặc tài liệu thao tác. Quy trình nhập tương tác cũng cần chạy trên terminal và máy trạm tin cậy.

### 5.2. Kiểm tra cục bộ trước khi đăng ký quyền

~~~bash
chmod 600 "$HOME/.ssh/pam_passphrase_lab"

ssh-keygen -y -f "$HOME/.ssh/pam_passphrase_lab" > /dev/null

ssh-keygen -lf "$HOME/.ssh/pam_passphrase_lab.pub"
~~~

Lệnh đầu bảo vệ quyền đọc tệp trên hệ thống Unix. Lệnh `-y` yêu cầu công cụ đọc khóa riêng và sinh public key; chuyển đầu ra vào `/dev/null` để không cần in dữ liệu ra terminal. Với tệp khóa đã mã hóa, hãy kiểm tra việc nhập passphrase đúng và sai trong môi trường thử nghiệm. Lệnh `-lf` giúp ghi nhận fingerprint của public key. Các tùy chọn này được mô tả trong [ssh-keygen](https://man.openbsd.org/ssh-keygen).

Kết quả kiểm tra cần được diễn giải đúng: mở khóa cục bộ thành công chứng minh tệp đọc được với bí mật đã nhập; nó không chứng minh khóa đã được cấp quyền đúng trên máy chủ. Ngược lại, kết nối SSH thành công có thể sử dụng một identity khác hoặc một agent đã mở khóa, nên cũng chưa đủ để kết luận tệp đang được bảo vệ đúng.

Không kiểm tra bằng cách in private key hoặc ghi passphrase vào log. Dòng đầu của tệp private key không phải bằng chứng đầy đủ rằng tệp đã được mã hóa bằng một passphrase phù hợp.

### 5.3. Đăng ký public key theo quy trình PAM

Trước khi cho phép sử dụng khóa với quyền quản trị, hồ sơ tối thiểu nên liên kết được:

- Người hoặc workload sở hữu khóa.
- Fingerprint của public key.
- Thiết bị hoặc môi trường được phép giữ private key.
- Tài khoản đích, phạm vi máy chủ và mức quyền được cấp.
- Người phê duyệt, thời điểm cấp và thời điểm rà soát hoặc hết quyền.
- Quy trình thu hồi nếu thiết bị hoặc thông tin xác thực bị nghi ngờ xâm phạm.

Chỉ chuyển public key qua quy trình đăng ký. Không gửi cả thư mục `.ssh` để “cài cho nhanh”. Với tổ chức dùng SSH certificate, việc ký và cấp certificate cần tuân theo chính sách danh tính, phạm vi và thời hạn; passphrase vẫn bảo vệ khóa riêng tương ứng trên phía sử dụng.

## 6. Đổi passphrase khác với thay cặp khóa

### 6.1. Thay lớp bảo vệ của tệp hiện có

Có thể thêm hoặc đổi passphrase cho tệp khóa đang quản lý bằng thao tác tương tác:

~~~bash
ssh-keygen -p -a 100 -f "$HOME/.ssh/pam_passphrase_lab"
~~~

Công cụ yêu cầu passphrase cũ nếu có, rồi yêu cầu passphrase mới. Không nhập rỗng khi chính sách yêu cầu mã hóa tệp. Sau thay đổi, kiểm tra lại việc mở khóa và đối chiếu fingerprint đã ghi nhận.

Thao tác này bảo vệ lại tệp đang được xử lý; nó không sửa những bản sao đã tồn tại ở backup, máy cũ hoặc tay người khác. Một bản sao được mã hóa bằng passphrase cũ vẫn cần xử lý theo trạng thái riêng của bản sao đó.

### 6.2. Khi nào phải thay cả cặp khóa?

| Sự kiện | Đổi passphrase có đủ không? | Hướng xử lý |
| --- | --- | --- |
| Cần cập nhật bí mật mở khóa, không có dấu hiệu lộ khóa | Có thể phù hợp theo chính sách | Cập nhật tệp và các bản sao hợp lệ; kiểm tra agent và khả năng phục hồi |
| Chỉ nghi ngờ passphrase bị lộ, chưa xác định có ai lấy được tệp | Chưa thể kết luận | Điều tra phạm vi; cân nhắc thay khóa theo mức quyền và độ tin cậy của thiết bị |
| Private key đã bị sao chép ngoài phạm vi quản lý | Không | Thu hồi quyền của khóa cũ và cấp cặp khóa mới |
| Máy trạm quản trị bị chiếm quyền | Không | Xử lý thiết bị, phiên và credential từ môi trường sạch |
| Người có bản sao khóa rời tổ chức | Không | Thu hồi khóa hoặc chứng chỉ, loại bỏ quyền liên quan và kiểm tra truy cập |
| Chỉ mất tệp `.pub`, khóa riêng vẫn an toàn và mở được | Không nhất thiết phải thay khóa | Có thể tái tạo public key rồi xác minh fingerprint |

Không dùng “đã đổi passphrase” làm bằng chứng rằng một private key bị lấy cắp đã mất giá trị. Máy chủ vẫn nhận cùng public key nếu chưa thu hồi nó.

Một quy trình thay khóa có kiểm soát thường gồm: tạo cặp mới trên thiết bị sạch, đăng ký quyền mới có phê duyệt, kiểm tra một đường truy cập độc lập, thu hồi khóa cũ ở mọi điểm liên quan và xác minh khóa cũ không mở được một lần xác thực mới. Khi đang xử lý sự cố, thứ tự thu hồi và khôi phục phải theo mức độ khẩn cấp của việc ngăn truy cập trái phép; không kéo dài quyền của khóa nghi lộ chỉ để thuận tiện chuyển đổi.

## 7. Sử dụng agent mà vẫn giữ giới hạn vận hành

### 7.1. Lợi ích và đánh đổi

Một agent cho phép client yêu cầu ký mà không phải nhập passphrase cho từng kết nối. Với khóa phần mềm, có thể hiểu rằng tệp mã hóa vẫn nằm trên đĩa, còn khả năng sử dụng khóa đã được mở trong một thành phần đang chạy.

Điều đó cải thiện thao tác của quản trị viên nhưng tạo thêm ranh giới cần bảo vệ. Người có khả năng sử dụng agent có thể không cần biết passphrase để yêu cầu những thao tác mà agent cho phép. Vì vậy, “không ai biết passphrase” không đồng nghĩa “không ai dùng được khóa đang nạp”.

Máy trạm cần được khóa màn hình, quản lý phiên và bảo vệ trước mã độc. Tuy nhiên, không nên mặc định khóa màn hình sẽ tự xóa identity khỏi mọi loại agent. Cần kiểm tra hành vi của agent và cơ chế tích hợp thực tế.

### 7.2. Nạp có thời hạn và gỡ đúng identity

Nếu môi trường đã có agent được quản lý, dùng agent đó theo chính sách. Nếu chưa có, có thể tạo một agent riêng cho shell thực hành:

~~~bash
eval "$(ssh-agent -s)"
~~~

Sau đó nạp khóa thử nghiệm trong 15 phút:

~~~bash
ssh-add -t 15m "$HOME/.ssh/pam_passphrase_lab"
ssh-add -l
~~~

Kết thúc bài thực hành hoặc ca thao tác, gỡ identity cụ thể:

~~~bash
ssh-add -d "$HOME/.ssh/pam_passphrase_lab.pub"
ssh-add -l
~~~

Nếu đã tạo agent riêng chỉ cho bài lab, có thể kết thúc agent từ chính shell đó:

~~~bash
ssh-agent -k
~~~

Trong OpenSSH, `ssh-add -t` đặt thời gian giữ identity; `-l` liệt kê fingerprint; `-d` gỡ identity được chỉ định. `-c` có thể yêu cầu xác nhận khi sử dụng nhưng cần môi trường xác nhận hoạt động đúng. Xem [ssh-add](https://man.openbsd.org/ssh-add). Ví dụ 15 phút là thời hạn minh họa, cần điều chỉnh theo công việc được cấp phép.

Không gỡ toàn bộ identity của một agent dùng chung chỉ để dọn bài lab. Nếu thêm tùy chọn xác nhận, hãy thử một thao tác ký hợp lệ và xác nhận cả hành vi từ chối; không coi việc lệnh nạp khóa chạy thành công là bằng chứng rằng mọi lần sử dụng đều được người dùng xem xét.

### 7.3. Bảo vệ đường đi qua máy trung gian

Forward agent khiến khả năng yêu cầu agent ký có thể được tiếp cận từ phía máy trung gian trong phạm vi kết nối chuyển tiếp. Một máy trung gian bị chiếm quyền vì vậy có thể trở thành đường sử dụng identity đang nạp, ngay cả khi không sao chép được private key qua giao diện agent. OpenSSH mô tả rủi ro này và cơ chế jump host tại [ssh](https://man.openbsd.org/ssh.1).

Trong thiết kế PAM, ưu tiên luồng kết nối đã được kiểm soát và giới hạn việc forward agent theo nhu cầu cụ thể. Không bật chuyển tiếp cho mọi máy chỉ vì thao tác thuận tiện. Tách khóa theo môi trường và cấp quyền ngắn hạn giúp hạn chế hậu quả khi một vùng quản trị gặp sự cố.

TTL của agent cũng không thay thế kiểm soát phiên ở bastion hoặc PAM gateway. Nếu một phiên quản trị đã mở, việc identity hết hạn trong agent không thu lại những thao tác còn được phép qua phiên đó.

## 8. Kiểm thử luồng sử dụng mà không kết luận nhầm

### 8.1. Định nghĩa kết quả cần chứng minh

Có ba phép kiểm tra độc lập:

1. **Bảo vệ tệp:** công cụ mở khóa cần bí mật đúng và không chấp nhận bí mật sai.
2. **Sử dụng identity:** lần xác thực thử nghiệm dùng đúng fingerprint dự kiến.
3. **Quyền và phiên:** hệ thống chỉ cho phép đích, tài khoản, thời gian và thao tác đã được phê duyệt.

Một lần đăng nhập thành công không bao phủ cả ba. Tương tự, lần đăng nhập thất bại không tự xác định passphrase sai; có thể public key chưa được cấp quyền hoặc chính sách tài khoản từ chối đăng nhập.

### 8.2. Ví dụ kiểm tra trên máy chủ lab

Giả sử public key thử nghiệm đã được cấp quyền cho tài khoản `pam-lab` trên máy chủ lab do bạn quản lý. Địa chỉ dưới đây là ví dụ; thay bằng hệ thống thực hành được phép sử dụng. Fingerprint host phải được xác minh và đăng ký trước theo quy trình tin cậy.

~~~bash
ssh -F /dev/null \
  -o IdentityAgent=none \
  -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey \
  -o PasswordAuthentication=no \
  -o KbdInteractiveAuthentication=no \
  -o StrictHostKeyChecking=yes \
  -o ControlMaster=no \
  -o ControlPath=none \
  -i "$HOME/.ssh/pam_passphrase_lab" \
  pam-lab@ssh-lab.example.net
~~~

Ví dụ cố ý dùng cấu hình kiểm tra riêng, chọn tệp khóa cụ thể và tránh dùng lại một kết nối có sẵn. Nó phù hợp với lab chỉ yêu cầu public key; không dùng nguyên lệnh này để đánh giá một môi trường production bắt buộc MFA hoặc cần cấu hình bastion riêng.

`IdentityAgent=none` loại agent khỏi lần thử; `IdentitiesOnly=yes` hạn chế identity theo cấu hình; các tùy chọn password và keyboard-interactive tránh việc thử thành công qua phương thức khác. `StrictHostKeyChecking=yes` giữ yêu cầu tin cậy host key. Xem mô tả tùy chọn tại [ssh_config](https://man.openbsd.org/ssh_config.5).

Không vô hiệu hóa kiểm tra host key để vượt qua lỗi trong bài lab. Khi host chưa được nhận diện tin cậy, kết quả phù hợp là dừng và xác minh fingerprint. Nếu cần thu thập debug log, xem lại log trước khi chia sẻ vì nó có thể chứa tên tài khoản, đích kết nối, đường dẫn nội bộ và fingerprint.

### 8.3. Giải thích kết quả

| Quan sát | Có thể giải thích thế nào? | Kiểm tra tiếp |
| --- | --- | --- |
| Tệp mở được khi nhập đúng passphrase | Bí mật tương ứng mở được bản tệp đang thử | Fingerprint và quyền trên máy chủ |
| SSH thành công mà không hỏi passphrase | Có thể đang dùng agent, identity khác, tệp không mã hóa hoặc kết nối đã có | Xác định đúng tệp, agent và cơ chế tái sử dụng kết nối |
| Đã nhập đúng nhưng vẫn bị từ chối | Mở tệp không đồng nghĩa được máy chủ cho phép | Public key được cấp quyền, tài khoản, certificate và chính sách |
| Agent đã hết TTL nhưng shell vẫn chạy | Phiên đã xác thực vẫn tồn tại | Cơ chế kết thúc phiên và quyền của tiến trình |
| Đổi passphrase xong mà bản sao cũ vẫn mở bằng bí mật cũ | Mỗi bản tệp giữ lớp bảo vệ tại thời điểm tạo nó | Kiểm kê bản sao; thay khóa nếu bản sao đã mất kiểm soát |

## 9. Quên passphrase và xử lý sự cố

### 9.1. Quên bí mật nhưng chưa có dấu hiệu xâm phạm

Không có quy trình quản trị tiêu chuẩn để “đặt lại” passphrase trên máy chủ rồi giải mã tệp khóa riêng ở client. Nếu không còn cách mở khóa hợp lệ, hướng phục hồi là dùng danh tính hoặc đường truy cập khác đã được phê duyệt để cấp một cặp khóa mới.

Quy trình gợi ý:

1. Xác minh người yêu cầu và ghi nhận sự kiện, tránh biến hỗ trợ khôi phục thành đường cấp quyền tùy tiện.
2. Kiểm tra phương án phục hồi được tổ chức chấp thuận, chẳng hạn kho bí mật có phân quyền hoặc danh tính quản trị độc lập.
3. Tạo khóa mới trên thiết bị tin cậy và cấp đúng phạm vi quyền.
4. Thu hồi public key hoặc chứng chỉ cũ theo hồ sơ kiểm kê.
5. Thử truy cập với khóa mới và xác minh khóa cũ không còn được chấp nhận.
6. Cập nhật hồ sơ owner, fingerprint và bằng chứng thay đổi.

Nếu agent vẫn có thể ký, khả năng đó không phải là chức năng lấy lại passphrase và không bảo đảm xuất lại được private key. Chỉ tận dụng đường truy cập còn hợp lệ trong phạm vi được phê duyệt, có bằng chứng và không biến nó thành ngoại lệ dài hạn.

### 9.2. Tệp khóa hoặc thiết bị bị mất kiểm soát

Khi nghi ngờ private key bị sao chép, cần đánh giá cả khả năng passphrase bị lộ, độ tin cậy của máy trạm, thời điểm agent đang mở và phạm vi public key được chấp nhận.

Các việc cần phối hợp trong ứng phó:

- Cô lập thiết bị hoặc luồng truy cập có dấu hiệu xâm phạm theo quy trình.
- Thu hồi quyền của khóa và chứng chỉ liên quan tại các điểm thực sự kiểm tra chúng.
- Đánh giá các phiên quản trị đang hoạt động và kết thúc phiên khi cần.
- Tạo credential thay thế từ môi trường sạch.
- Rà soát truy cập và các thay đổi đặc quyền trong khoảng thời gian liên quan.
- Xử lý bản sao, backup và bí mật đã từng được sử dụng trên thiết bị bị ảnh hưởng.

Việc xóa một tệp cục bộ, xóa một identity khỏi agent hoặc thay passphrase không tương đương thu hồi khóa trên máy chủ. Tương tự, tạo danh sách thu hồi chỉ có hiệu lực khi các điểm xác thực được cấu hình sử dụng và đã nhận bản cập nhật cần thiết.

Không yêu cầu người dùng gửi private key kèm passphrase để đội hỗ trợ “kiểm tra hộ”. Bằng chứng phù hợp thường là fingerprint, thông báo lỗi đã lọc, thời điểm thao tác và định danh thiết bị.

## 10. Bằng chứng và tiêu chí kiểm soát PAM

### 10.1. Bằng chứng không chứa bí mật

Một hồ sơ vận hành hữu ích có thể gồm các trường sau:

| Trường | Ví dụ nội dung hợp lệ |
| --- | --- |
| Identity owner | Mã nhân sự hoặc định danh workload chịu trách nhiệm |
| Key fingerprint | Fingerprint SHA-256 lấy từ public key |
| Device hoặc runtime | Mã máy trạm được quản lý hay môi trường thực thi |
| Phạm vi quyền | Tài khoản đích, nhóm máy và vai trò được phê duyệt |
| Cơ chế bảo vệ | Tệp khóa được mã hóa; hoặc thiết bị giữ khóa theo thiết kế |
| Chính sách mở khóa | Cách phê duyệt, thời hạn sử dụng agent, yêu cầu xác nhận nếu có |
| Lifecycle | Thời điểm cấp, rà soát, thay thế hoặc thu hồi |
| Kết quả kiểm tra | Đúng identity, quyền đúng phạm vi, đường khôi phục hoạt động |

Không đưa vào hồ sơ passphrase, nội dung private key, ảnh chụp trường bí mật hay bản ghi thao tác có thể tái hiện bí mật. Nếu phiên được ghi hình hoặc ghi terminal, cần kiểm tra cơ chế thu thập để tránh lưu thông tin nhạy cảm ngoài mục đích.

Máy chủ không thể suy ra đầy đủ chất lượng passphrase chỉ từ việc một public key xác thực thành công. Vì vậy, bằng chứng về bảo vệ khóa cần đến từ quy trình tạo, công cụ được quản lý hoặc kiểm tra endpoint có kiểm soát. Không thu passphrase để chứng minh rằng người dùng đã tuân thủ.

### 10.2. Các câu hỏi đánh giá

Một triển khai có thể được xem là vận hành đúng khi trả lời được các câu hỏi sau bằng bằng chứng:

- Khóa thuộc về ai và được dùng ở đâu?
- Tệp hoặc thiết bị giữ khóa được bảo vệ ra sao?
- Ai có thể mở khóa hoặc yêu cầu agent ký?
- Thời gian cho phép sử dụng có phù hợp với công việc đã phê duyệt không?
- Có thể thu hồi quyền của một khóa mà không cần thu lại mọi bản sao tệp không?
- Có thể phục hồi truy cập khi owner quên passphrase mà không chia sẻ khóa giữa các cá nhân không?
- Các phiên tồn tại sau khi hết quyền được xử lý như thế nào?

Các tiêu chí này nối bảo vệ khóa với least privilege, JIT, giám sát và ứng phó sự cố. Passphrase chỉ có ý nghĩa vận hành đầy đủ khi nằm trong vòng đời danh tính đó.

## 11. Bài thực hành và tình huống tự đánh giá

### 11.1. Bài lab: kiểm tra đầy đủ một vòng đời

Thực hiện trong môi trường riêng, không sử dụng khóa production:

1. Chọn một đường dẫn tệp mới và tạo khóa có passphrase bằng lệnh ở mục 5.
2. Ghi fingerprint của public key; không ghi passphrase vào báo cáo.
3. Kiểm tra mở tệp bằng passphrase đúng và sai. Ghi kết quả đạt hoặc không đạt.
4. Nạp vào agent có thời hạn, đối chiếu fingerprint và gỡ đúng identity.
5. Đổi passphrase, kiểm tra tệp sau thay đổi và xác nhận fingerprint public key vẫn khớp.
6. Nếu có máy chủ lab, đăng ký public key với quyền hạn chế rồi kiểm tra một lần xác thực riêng biệt.
7. Thu hồi quyền lab và xác nhận khóa không còn mở được một lần xác thực mới.

Báo cáo cần tách rõ việc đọc được tệp, sử dụng được identity và được cấp quyền. Một báo cáo chỉ ghi “SSH OK” chưa đủ để đánh giá vòng đời khóa.

### 11.2. Tình huống: laptop quản trị viên bị mất

Một quản trị viên dùng khóa cá nhân có passphrase. Laptop bị mất khi chưa rõ trạng thái khóa màn hình; người dùng nói đã nạp khóa vào agent trước đó và public key được chấp nhận trên nhiều máy chủ.

Cách lập luận phù hợp:

- Passphrase làm giảm rủi ro đối với bản tệp được mã hóa, nhưng trạng thái endpoint và agent chưa được xác định.
- Cần kiểm kê điểm sử dụng fingerprint, đánh giá phiên đang có và thực hiện thu hồi theo rủi ro.
- Credential thay thế phải được tạo từ thiết bị tin cậy.
- Không kết thúc xử lý chỉ bằng cách đổi passphrase trên một bản backup còn giữ được.

### 11.3. Tình huống: pipeline giữ hai bí mật cạnh nhau

Một pipeline chứa private key có passphrase và một biến chứa passphrase để chạy không tương tác. Người vận hành kết luận rằng credential đã được bảo vệ hai lớp.

Đánh giá: tệp được mã hóa, nhưng cần kiểm tra ai có thể đọc biến, tải artifact hoặc thực thi job. Nếu cùng một quyền cho phép lấy cả hai, lớp mã hóa không tạo ra ranh giới độc lập đối với người có quyền đó. Hướng cải thiện là danh tính workload riêng, quyền tối thiểu, cơ chế cấp phát có kiểm soát và giảm thời gian có thể sử dụng credential.

### 11.4. Câu hỏi kiểm tra kiến thức

**Câu 1.** Đổi passphrase có khiến máy chủ ngừng tin public key cũ không?

Không. Public key vẫn tương ứng với cùng cặp khóa; muốn ngừng chấp nhận phải thực hiện thu hồi tại điểm xác thực.

**Câu 2.** Vì sao khóa tài khoản sau nhiều lần đăng nhập sai không đủ bảo vệ tệp khóa bị lấy cắp?

Kẻ tấn công có thể đoán bí mật trên bản sao ngoại tuyến, không gửi mỗi lần thử đến máy chủ.

**Câu 3.** Vì sao agent hết TTL nhưng phiên quản trị vẫn có thể hoạt động?

Thời hạn identity trong agent giới hạn khả năng ký tiếp; phiên đã xác thực có vòng đời riêng.

**Câu 4.** Có nên dùng passphrase chung cho khóa của cả nhóm trực vận hành?

Không nên. Cần danh tính cá nhân và cơ chế truy cập khẩn cấp được quản lý, có trách nhiệm và bằng chứng.

**Câu 5.** Nếu lệnh SSH không hỏi passphrase, có thể kết luận khóa chưa được mã hóa không?

Chưa thể. Phải loại trừ agent, identity khác, tích hợp lưu bí mật và kết nối đã được xác thực trước đó.

**Câu 6.** Khi nào thay passphrase không còn là biện pháp xử lý đủ?

Khi private key hoặc môi trường sử dụng đã mất kiểm soát, cần đánh giá thu hồi và thay cặp khóa, đồng thời xử lý phiên và thiết bị liên quan.
