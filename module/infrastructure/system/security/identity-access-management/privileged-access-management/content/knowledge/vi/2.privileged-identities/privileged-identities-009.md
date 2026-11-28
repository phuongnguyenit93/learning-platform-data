# Security administrator identity

## 1. Mục tiêu và bối cảnh

Trong chương **Danh tính đặc quyền**, *security administrator identity* là danh tính được cấp quyền quản trị các cơ chế bảo mật trong một phạm vi xác định. Danh tính này có thể thay đổi cách hệ thống bảo vệ tài nguyên, quyết định truy cập, phát hiện sự kiện hoặc lưu bằng chứng.

Vì vậy, PAM cần quản lý không chỉ tài khoản quản trị máy chủ hay cơ sở dữ liệu, mà cả những danh tính có thể thay đổi chính các lớp bảo vệ đó. Một thay đổi nhỏ trong chính sách xác thực, cấu hình giám sát hoặc quyền truy cập vault có thể tác động đến nhiều tài khoản và dịch vụ khác.

Sau bài học, bạn có thể:

- Nhận diện danh tính quản trị bảo mật dựa trên quyền thực tế.
- Phân biệt vai trò này với phân tích an ninh, quản trị hệ thống và kiểm toán.
- Lập phạm vi quyền theo chức năng, tài nguyên, môi trường và nguồn cấp quyền.
- Áp dụng least privilege, JIT/JEA, quản lý credential và tách trách nhiệm.
- Thiết kế chuỗi bằng chứng cho thay đổi bảo mật và xử lý khi danh tính bị nghi xâm nhập.

## 2. Khái niệm: danh tính có khả năng thay đổi cơ chế bảo vệ

### 2.1. Danh tính, tài khoản và vai trò là những lớp khác nhau

**Danh tính** biểu diễn một người hoặc một workload. **Tài khoản** là cách hệ thống nhận diện chủ thể đó để xác thực và gắn quyền. **Vai trò** là một cách tập hợp hoặc cấp quyền; một danh tính có thể nhận nhiều vai trò qua nhiều nguồn.

Trong bài này, security administrator identity được hiểu theo khả năng thực tế, không phải một tên vai trò cố định của sản phẩm. Hai nền tảng cùng có vai trò mang tên “Security Administrator” vẫn có thể cho phép những hành động rất khác nhau.

Các chức năng có thể thuộc phạm vi quản trị bảo mật gồm:

- Thay đổi chính sách xác thực hoặc điều kiện truy cập.
- Cấu hình quy tắc bảo vệ, phát hiện và phản ứng của công cụ bảo mật.
- Thay đổi chính sách truy cập một vùng của vault hoặc nền tảng PAM.
- Quản lý cấu hình thu thập log và chuyển tiếp sự kiện.
- Thiết lập chính sách quản lý khóa, chứng thư hoặc phương thức xác thực trong phạm vi được giao.

Không phải một danh tính quản trị bảo mật phải có toàn bộ các quyền trên. Tập quyền cần phụ thuộc vào nhiệm vụ và ranh giới quản trị cụ thể.

### 2.2. Tại sao đây là danh tính đặc quyền?

Đặc quyền của danh tính này thể hiện ở khả năng tác động đến các điều kiện mà những danh tính khác phải tuân theo.

| Khả năng | Tác động cần đánh giá |
| --- | --- |
| Sửa chính sách xác thực | Có thể thay đổi ai đăng nhập được và cần bằng chứng xác thực nào |
| Sửa chính sách phân quyền | Có thể làm tăng hoặc giảm khả năng truy cập của chủ thể khác |
| Sửa quy tắc phát hiện | Có thể thay đổi sự kiện nào được chú ý hoặc bỏ sót |
| Sửa cơ chế thu thập log | Có thể làm thay đổi độ đầy đủ của bằng chứng |
| Quản lý ngoại lệ bảo vệ | Có thể mở một khoảng giảm bảo vệ cho tài nguyên |
| Quản lý cấu hình PAM hoặc vault | Có thể ảnh hưởng đến cách credential được cấp và quyền quản trị được sử dụng |

Một quyền cấu hình không trực tiếp đọc dữ liệu nghiệp vụ vẫn có thể gián tiếp tạo điều kiện để dữ liệu bị truy cập. Ngược lại, không nên kết luận mọi quyền cấu hình đều tương đương toàn quyền hệ thống: cần xác định đường tác động và những ràng buộc thực sự còn hiệu lực.

### 2.3. Quyền đọc cũng cần phân loại

Một chuyên viên có quyền đọc log có thể thấy dữ liệu nhạy cảm, nhưng điều đó không tự khiến họ trở thành người quản trị cấu hình bảo mật. Cần phân biệt quyền đọc dữ liệu, quyền quản lý dữ liệu và quyền thay đổi cơ chế bảo vệ.

Mỗi loại vẫn có thể là đặc quyền trong ngữ cảnh phù hợp. Việc phân loại giúp chọn đúng biện pháp kiểm soát thay vì gom tất cả vào nhãn “security”.

## 3. Phân biệt với các danh tính liên quan

| Danh tính hoặc nhiệm vụ | Trọng tâm | Điều cần phân biệt |
| --- | --- | --- |
| Security analyst | Phân tích sự kiện, đánh giá cảnh báo, hỗ trợ điều tra | Không mặc nhiên cần sửa chính sách hoặc xóa bằng chứng |
| Security administrator | Cấu hình và quản lý một tập cơ chế bảo mật | Không mặc nhiên cần quản trị mọi tài nguyên nghiệp vụ |
| System administrator | Vận hành hệ điều hành, dịch vụ hoặc hạ tầng | Có thể tác động đến lớp bảo mật tại chỗ; cần kiểm tra quyền giao nhau |
| IAM administrator | Quản lý danh tính, vai trò hoặc chính sách truy cập | Có thể là một phần của quản trị bảo mật, tùy mô hình tổ chức |
| Auditor hoặc reviewer | Xem bằng chứng và đánh giá kiểm soát | Thường cần tính độc lập với người thay đổi chính kiểm soát đó |
| Emergency privileged identity | Khôi phục quyền kiểm soát trong tình huống khẩn cấp | Có điều kiện sử dụng riêng, không thay thế danh tính quản trị thường lệ |
| Security automation identity | Tự động hóa thao tác bảo mật | Cần quyền riêng theo workload, không dùng credential cá nhân của người quản trị |

Các nhiệm vụ có thể giao nhau, đặc biệt trong nhóm nhỏ. Tuy nhiên, việc một người làm nhiều nhiệm vụ không có nghĩa mọi tài khoản hoặc phiên của họ đều cần tập quyền hợp nhất.

Ví dụ, một người có thể phân tích cảnh báo bằng tài khoản làm việc thông thường, sau đó kích hoạt một quyền quản trị riêng để thay đổi quy tắc đã được duyệt. Cách tách này giúp giảm thời gian đặc quyền tồn tại và làm rõ mục đích sử dụng.

## 4. Kiểm kê quyền theo chức năng và tài nguyên

### 4.1. Bắt đầu từ nhiệm vụ cụ thể

Thay vì mô tả “được quản trị hệ thống bảo mật”, hãy xác định chức năng cần thiết: sửa quy tắc nào, trên hệ thống nào, cho nhóm tài nguyên nào và trong môi trường nào.

Ví dụ:

| Nhiệm vụ | Quyền cần xem xét | Quyền không tự suy ra từ nhiệm vụ |
| --- | --- | --- |
| Điều chỉnh một quy tắc phát hiện cho dịch vụ A | Đọc và sửa quy tắc được giao; kiểm tra kết quả áp dụng | Tắt toàn bộ giám sát hoặc xóa lịch sử sự kiện |
| Sửa chính sách truy cập của phân vùng vault A | Quản lý chính sách đúng phân vùng | Đọc mọi giá trị bí mật trong vault |
| Cập nhật cấu hình chuyển tiếp log | Sửa cấu hình trên các nguồn được giao | Thay chính sách lưu giữ của mọi kho bằng chứng |
| Quản lý chính sách xác thực của một miền | Sửa các chính sách được ủy quyền | Tự gán toàn quyền hoặc thay phương thức xác thực của mọi người dùng |
| Quản lý chính sách vòng đời khóa | Thực hiện các thao tác quản lý được giao | Dùng khóa để giải mã dữ liệu nếu nghiệp vụ không yêu cầu |

Khả năng tách các quyền trên phụ thuộc vào nền tảng. Nếu sản phẩm gộp nhiều quyền trong cùng vai trò, phải nhận diện phần quyền vượt nhu cầu và chọn cơ chế bổ sung hoặc chấp nhận ngoại lệ có trách nhiệm rõ ràng.

### 4.2. Kiểm tra nguồn quyền và quyền hiệu lực

Danh tính có thể nhận quyền qua cấp trực tiếp, thành viên nhóm, vai trò kế thừa, chính sách tài nguyên hoặc ủy quyền. Quyền hiệu lực còn phụ thuộc vào điều kiện truy cập và trạng thái phiên.

Một bản kiểm kê hữu ích cần giải thích được chuỗi:

> Danh tính → tài khoản → nhóm hoặc vai trò → chính sách → hành động → tài nguyên → điều kiện hiệu lực.

Không nên chỉ dựa vào tên vai trò. Một người có vai trò tưởng như hẹp nhưng có quyền sửa nhóm quản trị hoặc thay cấu hình tác vụ chạy bằng danh tính mạnh hơn vẫn cần được xem xét về đường mở rộng quyền.

Cũng phải xác định ai có thể sửa chính các chính sách giới hạn người quản trị. Nếu danh tính được cấp quyền tự loại bỏ mọi ràng buộc của nó, cơ chế giới hạn trên giấy có thể không đạt mục tiêu.

### 4.3. Bản ghi kiểm kê tối thiểu

| Trường | Nội dung cần ghi |
| --- | --- |
| Danh tính và loại chủ thể | Cá nhân hoặc workload; tài khoản được dùng tại hệ thống đích |
| Chủ sở hữu | Người hoặc nhóm chịu trách nhiệm về nhu cầu và vòng đời |
| Chức năng | Thao tác quản trị bảo mật cụ thể |
| Phạm vi | Tài nguyên, miền quản trị và môi trường |
| Nguồn quyền | Vai trò, nhóm, chính sách, cơ chế kích hoạt |
| Trạng thái | Thường trực, đủ điều kiện hay đang hiệu lực |
| Điều kiện | Thời hạn, phê duyệt, xác thực và đường truy cập |
| Credential | Loại phương tiện, nơi quản lý theo tham chiếu; không lưu giá trị bí mật |
| Bằng chứng | Nguồn ghi nhận cấp quyền, thay đổi cấu hình và kết quả |
| Rà soát, thu hồi | Người xác nhận nhu cầu và cách kết thúc quyền, phiên, credential |

## 5. Tách trách nhiệm để tránh tự kiểm soát toàn bộ vòng đời

### 5.1. Vì sao phải tách?

Nếu cùng một danh tính có thể tự xin quyền, tự duyệt, thay chính sách bảo mật và xóa bằng chứng về thay đổi đó, việc phát hiện sai sót hoặc lạm dụng sẽ khó hơn.

Tách trách nhiệm nhằm tạo điểm kiểm tra độc lập ở những bước quan trọng. Các cặp cần xem xét gồm:

- Người đề xuất và người phê duyệt thay đổi nhạy cảm.
- Người thay đổi quy tắc và người xác nhận tác động thực tế.
- Người quản trị nguồn log và người quản lý kho bằng chứng.
- Người quản lý chính sách vault và người có quyền nhận bí mật, nếu nền tảng cho phép tách.
- Người quản trị cơ chế cấp quyền và người rà soát kết quả cấp quyền.

Không phải mọi thao tác đều cần hai người cùng thực hiện. Mức độ tách nên phù hợp với tác động của thao tác, khả năng tự động kiểm tra và quy mô tổ chức.

### 5.2. Phê duyệt cần ràng buộc với nội dung được duyệt

Một quyết định “được thay cấu hình” là quá chung. Cần xác định đối tượng, thay đổi dự kiến, lý do, thời hạn và tiêu chí xác nhận kết quả.

Nếu người thực hiện đổi tài nguyên hoặc mở rộng phạm vi sau khi được duyệt, phải đánh giá lại theo chính sách. Nếu không, phê duyệt dễ trở thành một thủ tục không còn gắn với thao tác thực tế.

### 5.3. Hiểu giới hạn của việc tách quyền

Tách quyền ở giao diện một công cụ có thể chưa đủ nếu một danh tính khác có toàn quyền trên máy chủ, kho dữ liệu hoặc nền tảng bên dưới. Người có quyền tại lớp hạ tầng có thể có khả năng thay đổi cấu hình hoặc bằng chứng ngoài giao diện đã giới hạn.

Do đó, cần xác định ranh giới tin cậy và những chủ thể còn có khả năng vượt qua nó. Mục tiêu là biết giới hạn thực tế và bảo vệ các điểm có tác động lớn, thay vì khẳng định có tính độc lập tuyệt đối chỉ từ sơ đồ vai trò.

## 6. Áp dụng PAM cho danh tính quản trị bảo mật

### 6.1. Tách danh tính sử dụng thông thường và danh tính quản trị

Với con người, nên dùng tài khoản có thể quy trách nhiệm và tách hoạt động quản trị khỏi công việc thông thường theo khả năng của nền tảng. Việc đọc thư, duyệt nội dung không liên quan hoặc dùng ứng dụng thường ngày bằng tài khoản đang mang đặc quyền làm tăng cơ hội phơi lộ quyền đó.

Tài khoản tách biệt không thay thế cho giới hạn quyền. Vẫn cần kiểm soát nhóm, vai trò, phương thức khôi phục xác thực và người có khả năng thay credential của tài khoản quản trị.

### 6.2. Xác thực và điểm truy cập phù hợp

Cần áp dụng phương thức xác thực mạnh phù hợp với nền tảng, bảo vệ phương tiện xác thực và hạn chế điểm truy cập quản trị theo mức độ nhạy cảm. Máy trạm hoặc broker quản trị cần đủ tin cậy để không làm lộ credential và phiên.

Đường khôi phục tài khoản cũng cần được bảo vệ. Nếu một tài khoản quản trị được xác thực rất chặt nhưng một chủ thể ít quyền hơn có thể tùy ý thay phương thức xác thực của nó, chuỗi kiểm soát có điểm yếu cần xử lý.

### 6.3. JIT giới hạn thời gian quyền hiệu lực

Một người có thể đủ điều kiện nhận quyền quản trị bảo mật nhưng chỉ kích hoạt khi có nhiệm vụ. Yêu cầu kích hoạt cần gắn với chức năng, tài nguyên, thời lượng và các điều kiện phù hợp.

Ví dụ, người quản trị được sửa quy tắc của dịch vụ A trong 25 phút theo một thay đổi đã duyệt. Con số này chỉ minh họa, không phải thời hạn chuẩn. Thời lượng thực tế phải đủ cho nhiệm vụ và phù hợp với mức độ tác động.

Khi thời hạn kết thúc, cần kiểm tra cơ chế thu hồi của nền tảng. Gỡ vai trò không mặc nhiên chấm dứt token hoặc phiên đã được tạo. Cổng PAM hiển thị “expired” chưa chứng minh hệ thống đích đã từ chối mọi thao tác tiếp theo.

### 6.4. JEA giới hạn chức năng và phạm vi

Just-enough administration giới hạn những gì có thể thực hiện cho nhiệm vụ. Trong ví dụ trên, người quản trị chỉ cần sửa quy tắc được giao, không cần vô hiệu hóa toàn bộ công cụ hoặc thay quyền truy cập mọi dự án.

Cơ chế thực hiện có thể là vai trò hẹp, API được kiểm soát hoặc cổng thay đổi chỉ chấp nhận một tập thao tác và tham số nhất định. Những đường truy cập khác cũng phải được kiểm kê; một giao diện giới hạn không có nhiều ý nghĩa nếu cùng người vẫn có credential toàn quyền để đi đường khác.

### 6.5. Vault và luân chuyển credential

Credential đặc quyền cần được quản lý theo vòng đời rõ ràng. Vault có thể hỗ trợ bảo quản, cấp phát và theo dõi truy xuất; luân chuyển credential xử lý việc thay giá trị xác thực theo chính sách hoặc khi có nguy cơ lộ.

Tuy nhiên, cất credential trong vault không tự làm hẹp quyền của tài khoản. Thay bí mật cũng không tự xóa vai trò hoặc chấm dứt mọi phiên. Cần phối hợp quản lý credential với quyền và trạng thái sử dụng thực tế.

Nếu người quản trị bảo mật cũng quản trị vault, phải đánh giá quyền đó có cho phép họ tự mở rộng truy cập bí mật hay không. Không nên suy ra quyền đọc bí mật chỉ từ nhu cầu quản lý chính sách nếu hai khả năng có thể tách được.

## 7. Quản trị bảo mật bằng tự động hóa

Một pipeline hoặc tác vụ tự động có thể cập nhật quy tắc, đồng bộ cấu hình hoặc triển khai chính sách. Danh tính của tác vụ đó cũng cần được coi là danh tính đặc quyền nếu có khả năng thay đổi cơ chế bảo vệ.

Không nên dùng credential cá nhân của một người quản trị làm danh tính lâu dài cho workload. Cần có chủ sở hữu, danh tính riêng theo phạm vi và phương thức cấp credential phù hợp; có thể dùng credential ngắn hạn khi nền tảng hỗ trợ và kiểm tra điều kiện cấp mới.

Các câu hỏi cần trả lời gồm:

- Workload nào được phép thực hiện thay đổi và trong môi trường nào?
- Ai được sửa mã, tham số hoặc nguồn cấu hình của tác vụ?
- Quy trình nào xác nhận nội dung thay đổi được phép triển khai?
- Credential có bị lộ trong log hoặc đầu ra của tác vụ không?
- Khi tác vụ bị hủy, quyền, token và kết nối còn hiệu lực được xử lý ra sao?
- Làm thế nào nối người duyệt, phiên bản thay đổi, lần chạy và hành động tại đích?

Một quy trình không có thao tác người dùng trực tiếp vẫn cần bằng chứng. Bản ghi phiên tương tác không thể thay thế log API, danh tính workload và kết quả triển khai trong trường hợp này.

## 8. Ví dụ xuyên suốt: điều chỉnh quy tắc phát hiện

### 8.1. Bối cảnh và nhu cầu

Một quy tắc phát hiện tạo nhiều cảnh báo trùng cho dịch vụ A. Nhóm phân tích đề xuất điều chỉnh một tham số để giảm trùng lặp, đồng thời vẫn nhận diện được hành vi cần phát hiện.

Nhu cầu là thay đổi đúng quy tắc và đánh giá tác động. Nhu cầu này không tự kéo theo quyền tắt toàn bộ thu thập sự kiện, sửa chính sách lưu giữ log hoặc cấp thêm vai trò quản trị.

### 8.2. Phân chia công việc

| Chủ thể | Nhiệm vụ | Phạm vi quyền |
| --- | --- | --- |
| Chuyên viên phân tích | Mô tả vấn đề và tiêu chí kiểm tra | Xem dữ liệu được giao, đề xuất thay đổi |
| Người phê duyệt | Đánh giá nội dung và tác động | Duyệt thay đổi trong phạm vi được giao |
| Người quản trị bảo mật | Áp dụng thay đổi đã duyệt | Sửa đúng quy tắc, có giới hạn thời gian |
| Danh tính triển khai, nếu dùng | Đưa phiên bản cấu hình vào hệ thống | Chỉ triển khai cấu hình thuộc phạm vi |
| Người rà soát | Đối chiếu kết quả và bằng chứng | Xem phiên bản, log và kết quả kiểm tra |

Một người có thể đảm nhận nhiều nhiệm vụ nếu tổ chức cho phép, nhưng cần nhận diện các trường hợp thiếu kiểm tra độc lập và có biện pháp phù hợp.

### 8.3. Ràng buộc thay đổi với yêu cầu

Đặc tả dưới đây là mã giả để minh họa, không phải cấu hình triển khai:

```text
Yêu cầu:
  loại_thay_đổi = điều_chỉnh_quy_tắc_phát_hiện
  tài_nguyên = quy_tắc_được_giao_cho_dịch_vụ_A
  môi_trường = sản_xuất
  phiên_bản_hiện_tại = phiên_bản_đã_được_đối_chiếu
  nội_dung_mới = thay_đổi_đã_được_duyệt
  thời_hạn = giới_hạn_được_chấp_nhận

Chỉ cho phép khi:
  danh_tính có tư_cách_thực_hiện trong phạm_vi này
  phê_duyệt còn_hợp_lệ và khớp nội_dung_thay_đổi
  quyền đã_kích_hoạt và chưa_hết_hạn
  tài_nguyên vẫn khớp phiên_bản cần thay_đổi

Sau khi áp dụng:
  ghi danh_tính, mã_yêu_cầu, phiên_bản và kết_quả
  kiểm_tra hệ_thống đã_nhận cấu_hình mới
  đánh_giá theo tiêu_chí đã_định
  hoàn_tác nếu cần theo phương_án đã_chuẩn_bị
  kết_thúc quyền và xác_nhận trạng_thái_thu_hồi
```

Kiểm tra phiên bản giúp tránh ghi đè một thay đổi khác vừa xảy ra sau khi nội dung được duyệt. Xác nhận hệ thống nhận cấu hình giúp phân biệt “đã gửi yêu cầu” với “đã áp dụng thành công”.

### 8.4. Kiểm tra kết quả và hoàn tác

Tiêu chí thành công không chỉ là số cảnh báo giảm. Cần kiểm tra việc giảm cảnh báo có phù hợp với mục tiêu và còn duy trì khả năng phát hiện theo tiêu chí được xác định hay không.

Nếu cần hoàn tác, phải biết phiên bản trước, điều kiện thực hiện và ai có quyền quyết định. Kết thúc cửa sổ thay đổi không nên làm mất khả năng phục hồi cấu hình khi một lỗi vừa được phát hiện; phương án xử lý tiếp phải có thẩm quyền và ghi nhận rõ.

Sau cùng, đối chiếu log thay đổi, kết quả triển khai, hoạt động liên quan và trạng thái quyền. Không nên đóng yêu cầu chỉ vì người thực hiện đã thoát giao diện quản trị.

## 9. Bằng chứng cho kiểm toán và ứng phó sự cố

Một chuỗi bằng chứng cần nối từ người chịu trách nhiệm đến thay đổi và kết quả thực tế:

> Yêu cầu → đánh giá và phê duyệt → kích hoạt quyền → danh tính thực thi → thay đổi tại đích → kiểm tra kết quả → thu hồi.

| Nhóm bằng chứng | Nội dung |
| --- | --- |
| Nhu cầu | Mã yêu cầu, lý do, tài nguyên và môi trường |
| Quyết định | Người hoặc chính sách phê duyệt, phạm vi và phiên bản nội dung |
| Cấp quyền | Nguồn quyền, thời điểm kích hoạt, thời hạn và kết quả |
| Thực thi | Người khởi tạo, danh tính tại đích, hành động và kết quả |
| Cấu hình | Phiên bản trước và sau, đối tượng thay đổi, xác nhận áp dụng |
| Kiểm tra | Kết quả đối chiếu tiêu chí và hoàn tác nếu có |
| Kết thúc | Thu hồi quyền, xử lý phiên hoặc token, lỗi cần tiếp tục xử lý |

Bản ghi “đăng nhập thành công” không cho biết người dùng đã sửa chính sách nào. Bản ghi “cập nhật thành công” cũng chưa cho biết ai yêu cầu và nội dung đó có được duyệt hay không.

Nếu cấu hình hoặc log chứa bí mật, cần lưu bằng chứng bằng hình thức phù hợp mà không sao chép giá trị nhạy cảm. Không ghi mật khẩu, token hoặc khóa vào ticket, log tác vụ và bản chụp dùng cho kiểm toán.

Nguồn bằng chứng cần được bảo vệ khỏi việc sửa hoặc xóa trái phép. Nếu người quản trị được phép thay cấu hình thu thập log, cần đánh giá cơ chế nào giúp phát hiện thay đổi đó và nguồn nào còn độc lập để đối chiếu.

## 10. Vòng đời của danh tính quản trị bảo mật

### 10.1. Tạo và cấp tư cách

Chủ sở hữu xác nhận nhiệm vụ, tài nguyên và tập quyền cần có. Việc cấp tư cách kích hoạt hoặc quyền thường trực phải có căn cứ, có thể truy vết và được kiểm tra với những quyền sẵn có của chủ thể.

Một quyền ít nhạy cảm riêng lẻ có thể trở nên quan trọng khi kết hợp với quyền khác. Ví dụ, quyền sửa cấu hình tác vụ và quyền yêu cầu chạy tác vụ bằng danh tính mạnh cần được xem xét cùng nhau.

### 10.2. Rà soát trong quá trình sử dụng

Cần đối chiếu nhu cầu hiện tại với quyền thực tế: người đó còn phụ trách miền quản trị không, quyền có được sử dụng đúng mục đích không, nhóm hoặc chính sách nào đã làm phạm vi rộng thêm.

Những sự kiện như thay công cụ, mở rộng môi trường, thay nhóm trực hoặc đổi chủ sở hữu dịch vụ có thể làm kết quả rà soát cũ không còn phù hợp. Với workload, cần kiểm tra nó còn hoạt động và ai đang kiểm soát cấu hình triển khai.

### 10.3. Đổi nhiệm vụ hoặc chấm dứt sử dụng

Thu hồi phải xem xét cả quyền trực tiếp, nhóm, tư cách kích hoạt, credential, phương thức khôi phục, token và phiên liên quan. Xóa một vai trò hiển thị không đủ nếu chủ thể vẫn nhận quyền tương đương từ nguồn khác.

Với credential của workload, cần phối hợp với chủ sở hữu dịch vụ để chuyển đổi hoặc kết thúc đúng cách. Việc xử lý vòng đời phải bảo đảm công việc hợp lệ còn được vận hành mà không duy trì quyền của danh tính đã hết nhu cầu.

## 11. Khi danh tính bị nghi xâm nhập

Danh tính quản trị bảo mật bị chiếm đoạt có thể làm thay đổi lớp bảo vệ hoặc bằng chứng, nên quá trình ứng phó cần xem cả hành động trên tài nguyên và thay đổi trong cơ chế kiểm soát.

Những việc cần đưa vào kế hoạch ứng phó gồm:

1. Xác định phạm vi quyền và các nguồn cấp quyền của danh tính.
2. Lưu bằng chứng cần thiết từ những nguồn còn đủ tin cậy.
3. Cô lập hoặc thu hồi khả năng truy cập theo cơ chế của nền tảng, gồm phiên và credential liên quan.
4. Rà soát thay đổi chính sách, quy tắc, ngoại lệ, phương thức xác thực và quyền đã cấp thêm.
5. Kiểm tra các danh tính, tác vụ hoặc credential khác có thể đã được tạo để duy trì truy cập.
6. Khôi phục cấu hình từ nguồn đã xác minh và xác nhận lại hoạt động bảo vệ, thu thập log.
7. Theo dõi việc tái diễn và giải quyết nguyên nhân gốc của việc mất quyền kiểm soát.

Thay mật khẩu riêng lẻ chưa đủ nếu phiên vẫn hoạt động hoặc một vai trò khác đã được tạo. Tương tự, khôi phục giao diện quản trị không chứng minh rằng mọi thay đổi trong cơ chế phát hiện đã được xử lý.

Khi công cụ quản trị hoặc danh tính thông thường không còn đáng tin, cần dùng kế hoạch phục hồi và đường truy cập khẩn cấp đã được chuẩn bị. Việc thu hồi không nên vô tình loại bỏ mọi đường quản trị hợp lệ trước khi có phương án phục hồi phù hợp.

## 12. Sai lầm thường gặp

| Sai lầm | Vấn đề | Hướng điều chỉnh |
| --- | --- | --- |
| Ai thuộc nhóm bảo mật cũng nhận toàn quyền | Chức danh bị dùng thay cho phân tích nhiệm vụ | Cấp theo chức năng, tài nguyên và môi trường |
| Chuyên viên phân tích luôn có quyền sửa hoặc xóa log | Quyền quan sát bị gộp với quyền thay đổi bằng chứng | Tách khả năng theo nhu cầu và mô hình sản phẩm |
| Người sửa kiểm soát có thể tự duyệt mọi thay đổi | Thiếu điểm kiểm tra độc lập | Ràng buộc phê duyệt và rà soát với tác động thực tế |
| Quyền quản trị vault đồng nghĩa đọc mọi bí mật | Phạm vi credential vượt nhu cầu cấu hình | Tách quyền chính sách và quyền nhận bí mật khi có thể |
| Đã có JIT nên có thể cấp toàn quyền | Thời gian ngắn vẫn có thể gây tác động lớn | Kết hợp JIT với least privilege và JEA |
| Dùng credential cá nhân cho tự động hóa | Khó tách trách nhiệm và xử lý khi nhân sự đổi vai trò | Dùng danh tính workload có chủ sở hữu và phạm vi riêng |
| Chỉ ghi hình phiên | Bỏ sót API, tác vụ tự động và nội dung cấu hình | Liên kết dữ liệu phiên với log tại đích và phiên bản thay đổi |
| Gỡ vai trò là coi như đã thu hồi hoàn toàn | Phiên, token hoặc nguồn quyền khác có thể còn | Xác nhận cơ chế và trạng thái quyền hiệu lực |
| Người quản trị có thể xóa toàn bộ dấu vết | Thiếu nguồn đối chiếu đáng tin | Bảo vệ bằng chứng và đánh giá quyền ở cả lớp hạ tầng |

## 13. Bài tập vận dụng

Một tổ chức cấp cùng một vai trò rộng cho mọi thành viên nhóm bảo mật. Vai trò đó cho phép xem cảnh báo, sửa quy tắc, thay chính sách truy cập vault và quản lý kho log. Một pipeline cập nhật quy tắc dùng token của trưởng nhóm. Mỗi lần thay đổi chỉ có bản ghi đăng nhập, không lưu phiên bản cấu hình hoặc yêu cầu liên quan.

Hãy phân tích:

1. Những chức năng đặc quyền nào đang bị gộp chung?
2. Nhiệm vụ nào của chuyên viên phân tích không đòi hỏi toàn bộ vai trò hiện tại?
3. Cần tách danh tính con người và workload như thế nào?
4. JIT/JEA có thể giới hạn điều gì và còn cần kiểm soát nào khác?
5. Những bằng chứng nào cần bổ sung để nối yêu cầu, người duyệt, lần triển khai và kết quả?
6. Nếu token pipeline bị lộ, chỉ đổi token có giải quyết được mọi thay đổi đã xảy ra không?

**Định hướng trả lời:** tách nhu cầu quan sát, sửa cấu hình, quản lý chính sách truy cập và quản lý bằng chứng. Dùng danh tính workload riêng cho pipeline, giới hạn phạm vi và kiểm soát người được sửa quy trình triển khai. Gắn kích hoạt quyền với thay đổi đã duyệt, lưu phiên bản và kết quả tại đích. Khi token bị lộ, cần xử lý cả phiên, quyền và các thay đổi đã tạo trong thời gian bị ảnh hưởng, thay vì chỉ thay phương tiện xác thực.

## 14. Ghi nhớ

Security administrator identity có thể thay đổi cách hệ thống bảo vệ tài nguyên và quan sát hoạt động. Vì thế, quản lý danh tính này đòi hỏi phạm vi quyền rõ, khả năng quy trách nhiệm và kiểm tra các quan hệ có thể làm mở rộng quyền.

Hãy bắt đầu từ chức năng cần thực hiện, giới hạn tài nguyên và thời gian, quản lý credential theo vòng đời, rồi nối toàn bộ thay đổi với bằng chứng tại đích. Tách trách nhiệm và bảo vệ nguồn bằng chứng giúp cơ chế PAM vẫn có thể giải thích, kiểm toán và phục hồi khi một danh tính quản trị bảo mật bị sử dụng sai hoặc bị chiếm đoạt.