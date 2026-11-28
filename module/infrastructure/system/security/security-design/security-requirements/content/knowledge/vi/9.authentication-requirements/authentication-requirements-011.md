# Brute-force defense

## 1. Từ mục tiêu bảo vệ tài khoản đến yêu cầu kiểm chứng được

**Brute-force defense** là tập biện pháp giới hạn, phát hiện và ứng phó với việc thử bí mật xác thực có hệ thống. Trong thiết kế yêu cầu bảo mật, mục tiêu không dừng ở câu “chặn đăng nhập sai nhiều lần”. Cần chỉ rõ đối tượng được bảo vệ, đơn vị đếm, cửa sổ thời gian, nơi giữ trạng thái, hành vi khi vượt ngưỡng và bằng chứng chứng minh giới hạn vẫn đúng khi hệ thống chạy phân tán.

Một đặc tả có ích phải đồng thời giải quyết ba mục tiêu:

- Giảm số bí mật mà đối phương có thể kiểm tra trực tuyến.
- Bảo vệ CPU, bộ nhớ và khả năng phục vụ của hệ thống xác thực.
- Hạn chế việc đối phương lợi dụng chính sách phòng vệ để cản người dùng hợp lệ.

Bài này thuộc chương **Yêu cầu xác thực**. Trọng tâm là chuyển mô hình đe dọa thành yêu cầu có ID, tiêu chí đo và liên kết với kiến trúc, dữ liệu vận hành, phục hồi và kiểm thử. Các con số trong tình huống minh họa là quyết định thiết kế giả định, cần được đánh giá cho hệ thống thực tế trước khi áp dụng.

### 1.1. Phân biệt các kiểu thử bí mật

| Kiểu tấn công | Cách thử | Vì sao một bộ đếm đơn giản có thể bỏ sót |
| --- | --- | --- |
| Đoán mật khẩu cho một tài khoản | Nhiều mật khẩu cho cùng định danh | Đổi IP hoặc gửi đồng thời để vượt bộ đếm cục bộ |
| Password spraying | Một số mật khẩu phổ biến cho nhiều tài khoản | Mỗi tài khoản chỉ có một vài lần sai |
| Credential stuffing | Thử các cặp định danh và mật khẩu lấy từ nơi khác | Có thể đúng ngay lần đầu, không tạo nhiều thất bại trên một tài khoản |
| Thử mã xác thực | Đoán OTP, mã phục hồi hoặc mã đặt lại | Tạo challenge mới để tìm cách đặt lại ngân sách thử |
| Thử ngoại tuyến | Đoán trên bản sao dữ liệu xác minh đã bị đánh cắp | Không gửi yêu cầu đến dịch vụ, nên không chịu rate limit trực tuyến |

Các thuật ngữ guessing, spraying và stuffing mô tả những mẫu tấn công khác nhau; thiết kế cần quan sát cả theo tài khoản lẫn theo nhiều tài khoản. [OWASP Credential Stuffing Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html)

Bộ giới hạn đăng nhập không bảo vệ được một bảng băm mật khẩu đã bị lấy ra ngoài. Rủi ro ngoại tuyến phải liên kết với yêu cầu lưu trữ credential: hàm dẫn xuất dành cho mật khẩu, salt, chi phí tính toán và kiểm soát truy cập. Không dùng kết quả kiểm thử rate limit để kết luận rằng mất cơ sở dữ liệu đã được xử lý đầy đủ.

## 2. Mô hình đe dọa và phạm vi của một tình huống mẫu

Xét một cổng học tập có tài khoản học viên và quản trị. Dịch vụ xác thực chạy trên ba instance sau bộ cân bằng tải. Người dùng có thể đăng nhập từ web hoặc ứng dụng di động; quản trị phải hoàn tất MFA. Một identity realm xác định không gian định danh và chính sách xác thực; các bí danh của cùng một tài khoản trong realm phải quy về cùng chủ thể.

Đối phương có thể gửi yêu cầu trực tiếp đến API, sử dụng nhiều IP, thay đổi tên đăng nhập, tạo yêu cầu đồng thời và khởi tạo nhiều luồng quên mật khẩu. Đối phương chưa được giả định đã điều khiển máy chủ hoặc thiết bị của người dùng.

| Mã rủi ro | Điều kiện tấn công | Tác động | Mục tiêu yêu cầu |
| --- | --- | --- | --- |
| R-BF-01 | Thử nhiều mật khẩu vào một tài khoản | Chiếm quyền truy cập | Giới hạn số phép xác minh được cấp |
| R-BF-02 | Thử chậm, rải trên nhiều tài khoản và nhiều nguồn | Chiếm hàng loạt tài khoản | Phát hiện chiến dịch, yêu cầu yếu tố bổ sung khi phù hợp |
| R-BF-03 | Gọi KDF liên tục hoặc gửi đầu vào rất lớn | Cạn CPU/RAM, tăng độ trễ | Chặn trước phép tính tốn kém, giới hạn tài nguyên |
| R-BF-04 | Cố tình gửi sai vào tài khoản nạn nhân | Khóa người dùng hợp lệ | Hạn chế có thời hạn, không gia hạn bởi yêu cầu bị chặn |
| R-BF-05 | Thử trên nhiều instance hoặc tuyến API khác nhau | Nhân số lượt được phép | Trạng thái dùng chung, phạm vi thống nhất |
| R-BF-06 | Dựa vào lỗi, mã HTTP hoặc thời gian phản hồi | Liệt kê tài khoản | Hợp đồng phản hồi không tiết lộ thông tin thừa |
| R-BF-07 | Bộ đếm mất dữ liệu hoặc mất kết nối | Mất khả năng cưỡng chế chính sách | Hành vi lỗi và phục hồi được đặc tả |
| R-BF-08 | Bí mật rơi vào log hoặc công cụ quan sát | Rò rỉ credential | Sự kiện đủ điều tra nhưng không chứa bí mật |

Các API sau phải được kiểm kê: đăng nhập web, đăng nhập di động, đăng nhập phiên bản cũ còn phục vụ, xác thực lại khi đổi dữ liệu nhạy cảm, xác minh MFA và xác minh bằng chứng phục hồi. Mỗi API có thể có ngân sách riêng, nhưng không được tạo một đường thử mật khẩu không chịu ngân sách của cùng chủ thể.

Tài khoản máy, API key và token ngẫu nhiên có mô hình sử dụng khác tài khoản con người. Nếu nằm trong phạm vi sản phẩm, cần đặc tả riêng về không gian bí mật, tốc độ hợp lệ và cách thu hồi; không sao chép nguyên ngưỡng đăng nhập người dùng sang mọi giao thức.

## 3. Xác định rõ điều gì được đếm

### 3.1. Bốn đại lượng không nên trộn lẫn

| Đại lượng | Thời điểm ghi nhận | Mục đích |
| --- | --- | --- |
| Yêu cầu đến endpoint | Khi cổng vào nhận yêu cầu thuộc phạm vi | Phòng chống lạm dụng và quá tải trước xử lý sâu |
| Lượt xác minh được cấp | Khi dịch vụ cấp quyền thực hiện một phép kiểm tra bí mật | Giới hạn số cơ hội thử và chi phí xử lý |
| Kết quả xác minh sai | Khi phép kiểm tra hoàn tất và xác định bí mật sai | Tín hiệu tấn công, kích hoạt thời gian hạn chế |
| Kết quả hoàn tất xác thực | Khi mọi yếu tố bắt buộc đã đạt | Cấp phiên, đánh giá rủi ro và ghi sự kiện nghiệp vụ |

Một lần bị từ chối trước KDF không phải một lần đã xác minh mật khẩu sai. Lỗi kho credential hoặc lỗi thư viện cũng không phải bằng chứng người dùng nhập sai.

Ngược lại, nếu cùng một mật khẩu sai được gửi và được xác minh năm lần, đó là năm cơ hội thử đã dùng. Không cần lưu hay so sánh nguyên văn các mật khẩu để “gộp” chúng. Không cho phép client tự chọn một idempotency key rồi dùng nó để được thử vô hạn mà chỉ tính một lượt.

### 3.2. Chọn khóa giới hạn đúng chủ thể

Một khóa giới hạn tài khoản có thể gồm loại thao tác, identity realm và ID nội bộ của chủ thể. Email, username hoặc bí danh đăng nhập cần được phân giải nhất quán trước khi chọn khóa. Đổi cách viết định danh không được tạo ngân sách mới.

Nếu một chủ thể dùng chung credential xuyên nhiều tenant, cần xác định phần ngân sách dùng chung theo chủ thể đó. Không tự tách theo tenant chỉ vì đường dẫn API có tenant ID. Ngược lại, hai chủ thể độc lập ở hai realm không được gộp chỉ vì trùng tên hiển thị.

Với tài khoản không tồn tại, có thể tạo khóa tổng hợp từ định danh đã xử lý bằng cơ chế có khóa, kèm thời hạn và giới hạn số lượng bản ghi. Không lưu vô hạn mọi chuỗi ngẫu nhiên mà đối phương gửi. Khóa tổng hợp giúp thực thi một chính sách công khai tương tự mà không cần tạo tài khoản thật.

Đối với nguồn truy cập, chỉ sử dụng thông tin IP từ chuỗi proxy tin cậy đã cấu hình. Header do client tự gửi không được trở thành nguồn sự thật. IP, dải mạng, thiết bị và vị trí là các tín hiệu có giới hạn: NAT có thể gộp nhiều người dùng; VPN, mạng di động và IPv6 có thể làm nguồn thay đổi. Không xem một IP là một người dùng.

Mật khẩu, OTP và token phục hồi không được làm khóa bộ đếm, nhãn metric hoặc dữ liệu tra cứu trong log.

## 4. Đặc tả một hồ sơ phòng vệ đo được

Trong tình huống mẫu, nhóm đề xuất hồ sơ dưới đây để nghiệm thu. Đây là cấu hình minh họa, không phải tuyên bố rằng một tiêu chuẩn bắt buộc đúng các ngưỡng này.

| Mã | Phạm vi | Quy tắc mẫu | Hành vi khi không đạt |
| --- | --- | --- | --- |
| SR-BF-01 | Mỗi chủ thể, mọi tuyến kiểm tra mật khẩu | Tối đa 5 lượt được cấp trong cửa sổ trượt 60 giây | Không thực hiện phép xác minh tiếp theo |
| SR-BF-02 | Mỗi chủ thể | Tối đa 1 phép xác minh mật khẩu đang xử lý | Từ chối yêu cầu chồng lấn; không tự tạo hàng đợi dài theo tài khoản |
| SR-BF-03 | Mỗi chủ thể | Từ 5 kết quả sai trong cửa sổ trượt 15 phút thì hạn chế thêm 60 giây | Không cấp lượt mới khi thời gian hạn chế chưa hết |
| SR-BF-04 | Mỗi nguồn truy cập tin cậy | Tối đa 120 yêu cầu xác minh mỗi 60 giây và 20 mỗi 5 giây | Hạn chế trước tác vụ tốn kém |
| SR-BF-05 | Tín hiệu chiến dịch | Một nguồn thử từ 20 định danh khác nhau trong 5 phút tạo tín hiệu rủi ro | Ghi sự kiện, đánh giá và áp biện pháp bổ sung theo chính sách |
| SR-BF-06 | Mỗi instance | Tối đa 8 tác vụ KDF đồng thời; chờ tài nguyên không quá 2 giây trong hàng đợi tối đa 32 yêu cầu | Phản hồi quá tải có kiểm soát; không tạo tác vụ vô hạn |
| SR-BF-07 | Trạng thái giới hạn dùng chung | Các instance sử dụng cùng ngân sách; không cấp lượt nếu không xác nhận được quyền thử | Trả lỗi tạm thời, không bỏ qua bộ giới hạn |
| SR-BF-08 | API xác thực công khai | Không công bố tài khoản tồn tại, trạng thái đặc quyền hoặc bộ đếm nội bộ trong phản hồi thất bại | Dùng hợp đồng phản hồi chung, kiểm tra thêm tín hiệu thời gian |

**Cửa sổ trượt 60 giây** trong hồ sơ được định nghĩa tại thời điểm t là các sự kiện có thời gian lớn hơn t − 60 giây và không lớn hơn t. Sự kiện đúng tại biên t − 60 giây đã rời cửa sổ. Thời gian do dịch vụ giữ trạng thái xác định, không do client cung cấp.

Ngân sách lượt được cấp tính cả kết quả đúng và sai. Thành công không hoàn lại lượt đã sử dụng và không xóa lịch sử trong cửa sổ. Nhờ vậy, một lần đăng nhập thành công không làm mất tín hiệu spraying hoặc cho phép lặp tác vụ KDF không giới hạn.

Thời gian hạn chế bắt đầu khi kết quả sai làm số thất bại trong 15 phút đạt ít nhất năm. Yêu cầu bị chặn không tăng bộ đếm sai và không dịch chuyển mốc hết hạn. Sau khi hết hạn, một thất bại mới trong lúc số thất bại của cửa sổ vẫn từ năm trở lên có thể kích hoạt một khoảng 60 giây mới.

Tín hiệu “20 định danh” không đồng nghĩa tự động cấm vĩnh viễn nguồn. Một mạng trường học có thể có nhiều người dùng hợp lệ đăng nhập cùng lúc. Cần đánh giá thêm tốc độ, tỷ lệ sai, lịch sử và tác động trước khi chọn hành động.

Ngưỡng theo nguồn trong ví dụ phải được kiểm tra với lưu lượng NAT thực tế. Nếu cần ngoại lệ cho một nguồn hợp lệ có nhiều người dùng, ngoại lệ phải có phạm vi và thời hạn; không đồng thời loại bỏ ngân sách theo chủ thể hoặc MFA.

## 5. Cưỡng chế giới hạn khi có nhiều instance và yêu cầu đồng thời

### 5.1. Cấp quyền thử trước khi xác minh bí mật

Thiết kế “đọc bộ đếm, chạy KDF, rồi tăng bộ đếm” có lỗ hổng cạnh tranh. Khi bộ đếm đang là bốn, nhiều instance có thể cùng nhìn thấy giá trị bốn và cùng cho phép thử. Kết quả cuối có thể bị chặn nhưng đối phương đã nhận thêm nhiều cơ hội kiểm tra.

Yêu cầu cần có thao tác **đặt chỗ hoặc cấp vé thử nguyên tử** trước KDF. Vé gắn với chủ thể, loại thao tác, phiên bản chính sách và trạng thái tác vụ. “Nguyên tử” ở đây nghĩa là các yêu cầu cạnh tranh không cùng tiêu cùng một phần ngân sách hoặc cùng chiếm một vị trí xử lý.

Không nhất thiết phải có một giao dịch duy nhất cho mọi chiều giới hạn. Ví dụ, có thể tiêu ngân sách nguồn trước rồi đặt chỗ theo tài khoản, miễn là chỉ chạy KDF sau khi tất cả điều kiện cần thiết đã đạt. Nếu một ngân sách đã bị trừ nhưng bước sau từ chối, hành vi giữ nguyên phần đã trừ cần được công bố như lựa chọn bảo thủ của hồ sơ.

Tính nguyên tử trong một tiến trình hoặc một bản sao cache không chứng minh tính nguyên tử toàn cụm. Cần nêu công nghệ lưu trữ, ranh giới giao dịch, hành vi replication và failover. Một script nguyên tử trên một shard không tự giải quyết mọi khóa nằm ở shard khác.

### 5.2. Luồng xử lý minh họa

~~~text
xu_ly_dang_nhap(request):
    kiem_tra_gioi_han_request_tai_cong_vao()
    chuan_hoa_dinh_danh_theo_hop_dong()
    principal = phan_giai_chu_the_hoac_khoa_tong_hop()

    neu khong_tieu_duoc_ngan_sach_nguon():
        tra_phan_hoi_han_che_chung()

    slot = xin_tai_nguyen_xac_minh_voi_thoi_gian_cho_huu_han()
    neu khong_co_slot:
        tra_loi_qua_tai()

    ticket = xin_ve_theo_chu_the_nguyen_tu()
    neu khong_co_ticket:
        giai_phong_slot()
        tra_phan_hoi_han_che_chung()

    result = xac_minh_credential_that_hoac_gia_co_gioi_han()

    neu result.la_loi_he_thong:
        ket_thuc_ticket_khong_ghi_nhan_sai_mat_khau()
        giai_phong_slot_khi_tac_vu_da_dung()
        tra_loi_tam_thoi()

    ket_thuc_ticket_mot_lan_va_cap_nhat_ket_qua()
    giai_phong_slot()

    neu result.sai:
        tra_loi_thong_tin_xac_thuc_khong_hop_le()

    neu chua_dat_cac_yeu_to_bat_buoc_khac:
        chuyen_sang_buoc_xac_thuc_tiep_theo_co_gioi_han()

    cap_phien_theo_chinh_sach()
~~~

Đây là mã giả mô tả nghĩa vụ, chưa bao gồm toàn bộ xử lý ngoại lệ, chống CSRF hoặc giao thức MFA. Khi hiện thực, mọi đường thoát phải kết thúc hoặc chuyển giao quyền sở hữu tài nguyên rõ ràng.

Nếu dịch vụ không xác nhận được thao tác cấp vé đã commit hay chưa, không tự chạy KDF. Có thể truy vấn trạng thái bằng ID tác vụ do máy chủ quản lý; nếu vẫn không xác định được, xử lý bảo thủ. Tính thêm một lượt đã giữ chỗ nhưng chưa thực thi có thể giảm khả dụng, song không được biến sự mơ hồ thành lượt thử miễn phí.

Hoàn tất vé phải có tính idempotent ở máy chủ: cùng một kết quả không tăng hai lần vì gửi lại sự kiện. Điều này khác với việc cho client tự khai báo một ID để vô hiệu hóa việc đếm.

### 5.3. Timeout không đồng nghĩa công việc đã dừng

Một timeout HTTP không chứng minh KDF đã ngừng chạy. Nếu giải phóng vị trí đang xử lý ngay khi client ngắt kết nối, các yêu cầu tiếp theo có thể tạo nhiều KDF hơn giới hạn.

Yêu cầu phải nêu khi nào tác vụ được coi là kết thúc, ai được giải phóng slot và cách thu hồi vé của tiến trình chết. Lease hết hạn chỉ an toàn khi có cơ chế bảo đảm tác vụ cũ không còn tiếp tục gây vượt giới hạn hoặc không thể sử dụng kết quả để đi tiếp. TTL chỉ để dọn dữ liệu không thay thế cơ chế điều phối.

Đối với tiến trình chết, bộ điều phối có thể đối chiếu quyền sở hữu tác vụ trước khi thu hồi. Thiết kế cụ thể tùy nền tảng, nhưng bằng chứng nghiệm thu phải bao gồm việc mất tiến trình, gửi lại sự kiện và timeout giữa các bước.

## 6. Hạn chế, trì hoãn và khóa tài khoản

Một biện pháp có thể làm giảm số lượt đoán nhưng đồng thời tạo công cụ từ chối dịch vụ. Đặc tả cần phân biệt các hành động sau:

| Hành động | Mục đích | Điều cần đặc tả |
| --- | --- | --- |
| Giới hạn tốc độ | Giới hạn số yêu cầu hoặc lượt thử trong một khoảng | Thuật toán, khóa, cửa sổ, độ chính xác |
| Thời gian hạn chế | Tạm không cấp thêm lượt sau tín hiệu rủi ro | Thời điểm bắt đầu/kết thúc và điều kiện kích hoạt lại |
| Trì hoãn tăng dần | Làm chậm nhịp thử | Trần thời gian, trạng thái dùng chung và giới hạn tài nguyên chờ |
| Challenge chống tự động hóa | Tăng chi phí của bot | Khi áp dụng, khả năng tiếp cận và hành vi khi dịch vụ challenge lỗi |
| Yêu cầu yếu tố bổ sung | Đòi bằng chứng độc lập trước khi cấp phiên | Phương thức được chấp nhận và chống đi vòng |
| Đình chỉ tài khoản | Dừng sử dụng khi có căn cứ về xâm phạm hoặc vi phạm | Người có quyền quyết định, lý do và quy trình phục hồi |

Không giữ một thread phục vụ ngủ nhiều phút chỉ để làm chậm đối phương. Có thể biểu diễn thời điểm được thử tiếp trong trạng thái giới hạn và từ chối sớm bằng phản hồi được kiểm soát.

Trong tình huống mẫu, đối phương không được kéo dài thời gian hạn chế chỉ bằng việc gửi thêm các yêu cầu đã bị chặn. Tuy nhiên, sau khi thời gian kết thúc, đối phương vẫn có thể tiếp tục thử sai và kích hoạt lần mới. Vì vậy, giới hạn có thời hạn không loại bỏ hoàn toàn rủi ro gây khó cho nạn nhân; cần giám sát và lối phục hồi có bằng chứng phù hợp.

Không dùng “mở khóa qua email” như thao tác xóa mọi ngân sách mà ai cũng khởi tạo được. Việc gửi yêu cầu phục hồi chỉ là bắt đầu một luồng; nó không chứng minh quyền kiểm soát tài khoản.

CAPTCHA, danh tiếng IP và dấu vân tay thiết bị là lớp bổ sung. Chúng không phải yếu tố sở hữu tài khoản. Hoàn thành CAPTCHA không được xóa ngân sách thử mật khẩu hoặc thay thế MFA bắt buộc.

## 7. Phản hồi API và chống liệt kê tài khoản

SR-BF-08 cần bao phủ nội dung phản hồi, mã HTTP, header, URL chuyển hướng và nhánh thời gian. Ví dụ, trả cùng một câu nhưng dùng 404 cho tài khoản không tồn tại và 401 cho tài khoản tồn tại vẫn để lộ thông tin.

Có thể định nghĩa hợp đồng công khai theo ba nhóm:

| Nhóm kết quả | Ví dụ phản hồi | Điều kiện nhất quán |
| --- | --- | --- |
| Bí mật hoặc định danh không hợp lệ | Thông tin xác thực không hợp lệ | Không phân biệt công khai “không có tài khoản” và “sai mật khẩu” |
| Đang bị hạn chế | Vui lòng thử lại sau | Hành vi giới hạn của định danh tổng hợp và tài khoản thật có cùng chính sách công khai |
| Phụ thuộc hoặc năng lực tạm lỗi | Tạm thời không thể xác thực | Không ghi lỗi hạ tầng thành mật khẩu sai hoặc ngụ ý tài khoản bị khóa |

Nếu dùng HTTP 429 cho hạn chế và 503 cho quá tải hoặc lỗi phụ thuộc, cần áp dụng theo hợp đồng endpoint thống nhất. Không trả thêm chi tiết như số lần sai còn lại, “tài khoản quản trị đang khóa” hoặc ID nội bộ. Header chỉ dẫn thử lại, nếu có, phải được đánh giá như một tín hiệu công khai.

Tài khoản không tồn tại không nên có nhánh trả sớm rõ rệt so với tài khoản tồn tại. Có thể dùng phép xác minh giả có chi phí phù hợp, nhưng phép tính đó vẫn phải nằm sau các cổng giới hạn và chịu cùng ngân sách tài nguyên. Các profile credential cũ/mới có chi phí khác nhau cũng cần được đánh giá về tín hiệu thời gian. [OWASP Authentication, phần Authentication and Error Messages](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#authentication-and-error-messages)

Yêu cầu “mọi phản hồi phải có thời gian bằng nhau tuyệt đối” không thực tế trên mạng. Cần xác định phép đo có kiểm soát, cỡ mẫu và tiêu chí tìm tín hiệu phân biệt đáng kể; xử lý các nhánh trả sớm có thể khai thác. Một lần quan sát hai phản hồi gần bằng nhau chưa phải bằng chứng.

Giới hạn theo lịch sử vẫn có thể tạo những khác biệt quan sát được. Mục tiêu của yêu cầu là giảm tiết lộ không cần thiết và không biến lỗi nghiệp vụ thành công cụ tra cứu tài khoản, không hứa rằng mọi tín hiệu phụ đều biến mất.

## 8. Không để MFA và phục hồi trở thành đường thử miễn phí

Mật khẩu đúng mới chỉ hoàn tất một bước nếu tài khoản bắt buộc có MFA. Không cấp phiên đầy đủ trước yếu tố tiếp theo. Bước trung gian phải gắn với đúng tài khoản và giao dịch, có thời hạn, có giới hạn số lượt và không được dùng như token phiên thông thường.

Với OTP hoặc mã phục hồi, cần đặc tả riêng:

- Lượt thử tính theo challenge, chủ thể và mục đích nào.
- Khởi tạo lại challenge có giữ ngân sách theo chủ thể hay không.
- Challenge cũ hết hiệu lực khi nào và hai yêu cầu dùng cùng mã được xử lý ra sao.
- Điều gì xảy ra khi mã sai, hết hạn, dùng lại hoặc phụ thuộc xác minh lỗi.
- Thời điểm được cấp lại mã và cách chống lạm dụng gửi email/SMS.

Một ví dụ toán học cho thấy vì sao số lượt phải gắn với không gian bí mật: nếu mã gồm sáu chữ số được sinh đồng đều, không có rò rỉ và đối phương thử năm giá trị khác nhau trong thời gian mã còn hiệu lực, xác suất đoán trúng mã đó là 5/1.000.000. Đây không phải đánh giá rủi ro đầy đủ; tạo liên tiếp nhiều mã mới hoặc khai thác kênh phục hồi có thể làm mô hình này không còn mô tả đúng hệ thống.

Do đó, “mỗi challenge chỉ thử năm lần” chưa đủ nếu đối phương được tạo vô hạn challenge. Phải có ngân sách cấp và xác minh ở cấp chủ thể hoặc luồng phục hồi theo rủi ro.

Luồng quên mật khẩu cũng có giới hạn gửi, giới hạn xác minh và chính sách thu hồi bằng chứng sau thành công. Việc khởi tạo phục hồi không được tự khóa tài khoản hoặc xóa trạng thái phòng vệ. Token đặt lại cần ngẫu nhiên, có hạn, dùng một lần và được bảo vệ trong lưu trữ. [OWASP Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

MFA giúp giảm tác động của mật khẩu bị đoán hoặc dùng lại, nhưng vẫn cần bảo vệ bước mật khẩu để giảm lạm dụng tài nguyên. Phương thức MFA, chống phishing và khôi phục yếu tố bị mất cần những yêu cầu riêng. Mật khẩu và một câu hỏi bí mật vẫn cùng nhóm điều người dùng biết, không tạo ra hai yếu tố độc lập.

## 9. Thiết kế hành vi khi phụ thuộc lỗi và khi khôi phục hệ thống

Không đủ để yêu cầu “lưu bộ đếm trong cache”. Phải nêu dữ liệu nào cần độ tin cậy nào và hệ thống làm gì nếu không thể xác nhận trạng thái.

| Sự cố | Hành vi của tình huống mẫu | Bằng chứng cần có |
| --- | --- | --- |
| Kho giới hạn mất kết nối hoặc không xác nhận được quyền thử | Không cấp vé mới, trả lỗi tạm thời chung | Không có KDF hoặc phiên mới được tạo qua nhánh bỏ giới hạn |
| Kho credential không truy cập được | Kết thúc tác vụ với lỗi hệ thống, không ghi nhận mật khẩu sai | Bộ đếm thất bại không tăng do lỗi hạ tầng |
| KDF lỗi hoặc quá hạn | Dừng/kiểm soát công việc, xử lý vé và slot theo trạng thái thực | Không có tác vụ mồ côi làm vượt giới hạn |
| Dịch vụ danh tiếng nguồn lỗi | Duy trì các giới hạn nền và yếu tố bắt buộc | Không tự bỏ ngân sách theo tài khoản hoặc MFA |
| Kho telemetry tạm lỗi | Đệm có giới hạn, phát tín hiệu mất quan sát, không lưu bí mật để bù | Không tăng vô hạn bộ nhớ hoặc chặn hệ thống vì log không gửi được |
| Instance khởi động lại | Đọc trạng thái chia sẻ, không tự cấp lại toàn bộ ngân sách tài khoản | Luân phiên hoặc khởi động lại instance không tạo thêm lượt |
| Failover kho trạng thái | Chỉ cấp lượt khi xác nhận trạng thái đủ tin cậy theo chính sách | Không vượt hard limit do đọc bản sao cũ hoặc mất cập nhật |

Nếu kho trạng thái có thể tự loại bỏ bản ghi khi đầy, đối phương có thể tạo nhiều định danh để làm mất bộ đếm của tài khoản bị nhắm đến. Yêu cầu cần tách trạng thái quan trọng khỏi cache dễ bị eviction, giới hạn cardinality của khóa tổng hợp và kiểm thử áp lực bộ nhớ.

Cửa sổ và thời gian hạn chế phải dùng nguồn thời gian được kiểm soát. Thay đồng hồ client hoặc chuyển instance không được làm hết hạn sớm. TTL phục vụ dọn dữ liệu cần đủ để giữ nghĩa của cửa sổ; không đặt một TTL ngắn hơn lịch sử mà chính sách cần dùng.

Lựa chọn không cấp lượt khi mất trạng thái có chi phí khả dụng. Nhóm thiết kế phải ghi nhận chi phí đó trong yêu cầu năng lực và phục hồi của dịch vụ giới hạn. Một chế độ suy giảm, nếu được cho phép ở hệ thống khác, phải có ngân sách bảo thủ và ranh giới rõ ràng; không chỉ viết “cho qua để tránh gián đoạn”.

Các phiên đang hợp lệ được xử lý theo chính sách phiên riêng. Sự cố bộ đếm đăng nhập không tự động chứng minh rằng mọi phiên hiện tại đều bị xâm phạm.

## 10. Kiến trúc, dữ liệu quan sát và quyền riêng tư

### 10.1. Phân công điểm cưỡng chế

~~~mermaid
flowchart LR
    C["Client / đối phương"] --> G["Gateway: kích thước và giới hạn nguồn"]
    G --> A["Các instance xác thực"]
    A --> L["Dịch vụ giới hạn dùng chung"]
    A --> K["Vùng tài nguyên KDF hữu hạn"]
    K --> D["Kho credential"]
    A --> M["MFA và cấp phiên"]
    A --> E["Sự kiện bảo mật không chứa bí mật"]
    E --> O["Phát hiện chiến dịch và ứng phó"]
~~~

Gateway hỗ trợ chống lạm dụng sớm nhưng không thay thế giới hạn theo chủ thể trong dịch vụ xác thực. Đường truy cập nội bộ, endpoint di động hoặc phiên bản API cũ cũng phải chịu chính sách. Chỉ gắn WAF trước trang web không chứng minh API phía sau đã được bảo vệ.

Nếu một nhà cung cấp định danh chịu trách nhiệm xác minh, cần ghi rõ phần nào được ủy thác, phần nào ứng dụng vẫn phải làm và bằng chứng nào xác nhận cấu hình. Lối đăng nhập dự phòng cần được kiểm kê để tránh một tuyến yếu hơn.

### 10.2. Dữ liệu sự kiện mẫu

~~~json
{
  "eventType": "AUTH_ATTEMPT_REJECTED",
  "reasonClass": "RATE_LIMIT",
  "realmId": "realm-demo",
  "principalRef": "opaque-demo-reference",
  "operation": "PASSWORD_VERIFY",
  "policyVersion": "bf-profile-v1",
  "requestId": "server-generated-demo-id",
  "enforcementPoint": "auth-service"
}
~~~

Ví dụ chỉ minh họa cấu trúc, không chứa định danh hay bí mật thật. Có thể cần thêm thời gian và tham chiếu nguồn đã giảm thiểu theo mục đích điều tra. Nhãn lý do nội bộ có thể chi tiết hơn phản hồi công khai, nhưng quyền đọc phải được giới hạn.

SR-BF-09 yêu cầu không ghi mật khẩu, OTP, token phục hồi, cookie, access token hoặc bản ghi băm xác minh vào log và trace. Phạm vi bao gồm debug, thông báo lỗi, APM, analytics và bản ghi hỗ trợ. [OWASP Logging, phần Data to Exclude](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude)

Băm nhanh mật khẩu rồi đưa vào telemetry vẫn tạo dữ liệu giúp đoán bí mật. Chỉ ghi việc phép kiểm tra đã được cấp, bị từ chối hoặc hoàn tất với loại kết quả nào.

### 10.3. Số đo cần phục vụ quyết định

| Số đo | Câu hỏi vận hành |
| --- | --- |
| Lượt được cấp và bị từ chối theo lớp giới hạn | Chính sách có thực sự cưỡng chế hay chỉ phát cảnh báo? |
| Số chủ thể và nguồn trong một chiến dịch | Có spraying hoặc stuffing phân tán không? |
| Số KDF đang chạy, độ dài hàng đợi, CPU/RAM và độ trễ | Phòng vệ có bảo vệ được năng lực xác thực không? |
| Tỷ lệ người dùng hợp lệ bị hạn chế | Ngưỡng có làm hỏng trải nghiệm trên NAT hoặc mạng di động không? |
| Lỗi kho trạng thái và thời gian không cấp được vé | Phụ thuộc phòng vệ có đáp ứng yêu cầu sẵn sàng không? |
| Độ trễ phát hiện và ứng phó | Hệ thống có hành động kịp khi một lớp phòng vệ bị vượt qua không? |

Không chỉ đếm thất bại; stuffing có thể tạo các lần thành công bất thường. Quy trình phát hiện cần có người chịu trách nhiệm và hành động được phép: xác minh sự kiện, tăng thách thức theo chính sách, thu hồi phiên có căn cứ hoặc hướng dẫn phục hồi.

Thời gian lưu, quyền truy cập và cách xử lý địa chỉ IP cần phù hợp mục đích. Không dùng email hoặc định danh tùy ý làm nhãn metric có cardinality không giới hạn.

## 11. Viết yêu cầu hoàn chỉnh và liên kết bằng chứng

Một yêu cầu cần cho người triển khai và người kiểm thử cùng hiểu một hành vi. Ví dụ hoàn chỉnh cho ngân sách theo chủ thể:

| Trường | Đặc tả mẫu |
| --- | --- |
| ID | SR-BF-01 |
| Mục tiêu | Giới hạn số phép kiểm tra mật khẩu trực tuyến cho một chủ thể |
| Rủi ro liên kết | R-BF-01, R-BF-03, R-BF-05 |
| Phạm vi | Mọi API kiểm tra cùng credential, mọi instance trong identity realm |
| Nghĩa vụ | Không cấp quá 5 lượt trong cửa sổ trượt 60 giây; một lượt chỉ được thực hiện khi có vé hợp lệ |
| Đơn vị đếm | Lượt được cấp, gồm cả kết quả đúng, sai hoặc lỗi sau khi đã cấp |
| Nơi thực thi | Dịch vụ xác thực và dịch vụ giới hạn dùng chung |
| Điều kiện lỗi | Không xác nhận được quyền thử thì không chạy KDF |
| Quan hệ | Kết hợp SR-BF-02 về tác vụ đang xử lý và SR-BF-03 về thời gian hạn chế |
| Chủ sở hữu | Nhóm định danh triển khai; vận hành bảo đảm phụ thuộc; an toàn thông tin duyệt chính sách |
| Tiêu chí nghiệm thu | Thử qua nhiều instance, alias và tuyến API vẫn không vượt ngân sách đã định nghĩa |
| Ngoại lệ | Phải có phạm vi, người chịu trách nhiệm rủi ro, thời hạn và bằng chứng biện pháp bù |

Ma trận truy vết rút gọn:

| Yêu cầu | Rủi ro | Thành phần liên quan | Bằng chứng |
| --- | --- | --- | --- |
| SR-BF-01, SR-BF-02 | R-BF-01, R-BF-05 | Bộ cấp vé, khóa chủ thể, các instance | Kiểm thử cửa sổ, alias và cạnh tranh |
| SR-BF-03 | R-BF-04 | Trạng thái hạn chế, luồng phục hồi | Yêu cầu bị chặn không gia hạn mốc hết hạn |
| SR-BF-04, SR-BF-05 | R-BF-02 | Gateway, bộ phát hiện chiến dịch | Kịch bản spraying và lưu lượng NAT hợp lệ |
| SR-BF-06 | R-BF-03 | KDF, hàng đợi, ingress | Tải, tài nguyên, timeout và ngắt kết nối |
| SR-BF-07 | R-BF-07 | Kho trạng thái và quy trình failover | Lỗi mạng, restart, mất cập nhật và eviction |
| SR-BF-08 | R-BF-06 | API, giao diện, nhánh xác minh giả | So sánh phản hồi và đo tín hiệu thời gian |
| SR-BF-09 | R-BF-08 | Log, trace, analytics, công cụ hỗ trợ | Dữ liệu tổng hợp đánh dấu không xuất hiện trong telemetry |

Viện dẫn tài liệu hướng dẫn chỉ cung cấp căn cứ thiết kế. Bằng chứng đạt yêu cầu phải đến từ hành vi và cấu hình của hệ thống trong phạm vi đã cam kết.

## 12. Kế hoạch nghiệm thu theo tình huống tấn công

Các ca dưới đây là kế hoạch kiểm thử cho hồ sơ mẫu, không phải kết quả đã chạy.

| Mã ca | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| AT-BF-01 | Dùng tài khoản có bí mật đúng, hoàn tất các bước cần thiết và thực hiện 6 lượt trong chưa đầy 60 giây | Không có hơn 5 vé; thành công không hoàn ngân sách |
| AT-BF-02 | Kiểm tra sự kiện ở t − 60 giây và ngay hai phía biên | Hành vi đúng định nghĩa cửa sổ, không theo mốc phút trên đồng hồ |
| AT-BF-03 | Gửi 50 yêu cầu đồng thời vào cùng chủ thể qua ba instance | Tối đa 1 phép kiểm tra mật khẩu đang xử lý; tổng lượt vẫn chịu cửa sổ |
| AT-BF-04 | Xen kẽ username, email, web, mobile và phiên bản API cũ | Cùng credential vẫn dùng chung phạm vi ngân sách |
| AT-BF-05 | Đổi IP sau mỗi lần thử sai một tài khoản | Giới hạn theo chủ thể còn hiệu lực |
| AT-BF-06 | Thử ít lần trên mỗi tài khoản nhưng nhiều tài khoản | Tín hiệu chiến dịch được tạo; không chỉ dựa vào bộ đếm một tài khoản |
| AT-BF-07 | Sau lần sai thứ năm, gửi liên tục các yêu cầu đã bị chặn | Không chạy thêm KDF và không kéo dài mốc 60 giây của đợt hạn chế |
| AT-BF-08 | Sau khi hết hạn chế, thử sai khi lịch sử 15 phút vẫn đủ ngưỡng | Đợt hạn chế mới được kích hoạt theo hồ sơ |
| AT-BF-09 | Giả mạo header nguồn từ kết nối không thuộc proxy tin cậy | Không tạo được IP nguồn tùy ý để vượt giới hạn |
| AT-BF-10 | Nhiều người dùng hợp lệ từ cùng NAT | Đo được ảnh hưởng, có bằng chứng đánh giá ngưỡng và ngoại lệ nếu cần |
| AT-BF-11 | Ngắt kết nối client trong lúc KDF chạy rồi gửi lại | Số công việc thực vẫn không vượt giới hạn; không giải phóng slot sớm |
| AT-BF-12 | Mất kết nối kho giới hạn hoặc timeout lúc cấp vé | Không cấp phiên qua đường bỏ giới hạn; kết quả mơ hồ không tạo lượt miễn phí |
| AT-BF-13 | Restart instance, failover kho trạng thái và gây áp lực eviction | Không tự tạo lại ngân sách mới; thực hiện đúng chính sách trạng thái không tin cậy |
| AT-BF-14 | Lỗi kho credential trong nhiều lần thử | Không tăng số thất bại như thể mật khẩu sai |
| AT-BF-15 | Gửi lại sự kiện hoàn tất cùng vé | Chỉ ghi nhận kết quả một lần |
| AT-BF-16 | So sánh tài khoản thật và định danh không tồn tại ở các trạng thái tương ứng | Không có thông báo, mã lỗi hoặc nhánh trả sớm làm lộ thông tin ngoài hợp đồng |
| AT-BF-17 | Tạo challenge OTP hoặc phục hồi mới sau khi hết lượt | Không nhận ngân sách vô hạn bằng việc khởi tạo lại |
| AT-BF-18 | Nhập đúng mật khẩu quản trị rồi bỏ bước MFA | Không nhận phiên đầy đủ hoặc quyền quản trị |
| AT-BF-19 | Gửi payload rất lớn và tải vượt khả năng KDF | Từ chối hoặc quá tải có kiểm soát; số tác vụ và hàng đợi hữu hạn |
| AT-BF-20 | Dùng bí mật tổng hợp đánh dấu qua đường thành công, sai và lỗi | Không tìm thấy bí mật trong log, trace, analytics hoặc công cụ hỗ trợ |

Ca kiểm tra thời gian cần đo nhiều mẫu trong môi trường có kiểm soát. Ca kiểm tra khả dụng cần ghi cả tỷ lệ người dùng hợp lệ bị từ chối và mức tài nguyên; chỉ báo “chặn được bot” chưa đủ.

Khi tính hard limit, đo số phép xác minh thực sự được khởi chạy hoặc được cấp, không chỉ đếm số phản hồi 429. Một hệ thống có thể trả lỗi cho client nhưng vẫn tiêu tài nguyên ở tác vụ nền nếu quản lý hủy công việc không đúng.

## 13. Duy trì yêu cầu trong vòng đời phát triển

Ở giai đoạn phân tích, nhóm xác định tài sản, đối phương, các đường thử bí mật và mức tác động. Ở giai đoạn thiết kế, nhóm quyết định chiều giới hạn, đơn vị đếm, mô hình thời gian và ranh giới nguyên tử. Khi triển khai, phiên bản cấu hình phải gắn với nơi cưỡng chế và dữ liệu quan sát.

Khi nghiệm thu, nối từng yêu cầu với kịch bản bình thường, cạnh tranh và lỗi phụ thuộc. Trong vận hành, đánh giá đồng thời khả năng giảm tấn công và ảnh hưởng đến người dùng hợp lệ. Mọi thay đổi ngưỡng cần có người chịu trách nhiệm, căn cứ và khả năng quay về cấu hình trước; không lặng lẽ xóa một lớp bảo vệ để làm giảm số lỗi.

Những thay đổi cần xem lại đặc tả gồm thêm API đăng nhập, chuyển nhà cung cấp định danh, thay chi phí KDF, mở thêm region, đổi cấu hình proxy, thêm tenant dùng chung chủ thể hoặc thay luồng MFA và phục hồi.

Đối với triển khai nhiều region, phải nói rõ ngân sách là toàn cục hay theo region. Nếu cho mỗi region một hạn mức độc lập, tổng số lượt đối phương nhận được có thể tăng theo số region; đó là quyết định rủi ro cần được ghi nhận, không phải chi tiết triển khai vô hại.

Brute-force defense đạt giá trị khi mọi cơ hội kiểm tra bí mật đều nằm trong một chính sách có thể cưỡng chế, đo và giải thích. Số ngưỡng chỉ là một phần; phạm vi chủ thể, tính nguyên tử, hành vi lỗi, khả năng phục hồi và bằng chứng kiểm thử mới quyết định giới hạn đó có giữ đúng trong hệ thống thực tế hay không.
