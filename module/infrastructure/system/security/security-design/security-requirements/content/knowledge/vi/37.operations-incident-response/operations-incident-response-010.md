# Security patch SLA: đặc tả thời hạn vá bảo mật và kiểm chứng việc hoàn tất

## 1. Patch SLA cần giải quyết vấn đề gì?

Một thông báo lỗ hổng được tiếp nhận nhưng không có người sở hữu, thời hạn hoặc điều kiện đóng có thể tồn tại nhiều tuần dưới trạng thái “đang xử lý”. Ngược lại, một ticket báo đã cài patch có thể được đóng dù tiến trình còn chạy phiên bản cũ hoặc một nhóm node chưa được cập nhật.

Security patch SLA quy định cam kết xử lý bản vá bảo mật trong phạm vi đã thống nhất: đối tượng nào phải xử lý, đồng hồ bắt đầu khi nào, deadline được tính ra sao, thế nào là hoàn tất và phải phản ứng gì khi không đạt.

Trong chương Vận hành và incident của module Security Requirements, trọng tâm là chuyển mục tiêu giảm phơi nhiễm thành yêu cầu đo được, có chủ sở hữu và có bằng chứng trên hệ thống thực tế.

NIST SP 800-40 Rev. 4 mô tả quản lý bản vá doanh nghiệp bao gồm nhận diện, ưu tiên, thu nhận, cài đặt và xác minh việc cài đặt các bản vá, cập nhật và nâng cấp. Vì vậy, cam kết thời gian cần theo được cả quá trình đến kiểm chứng, không chỉ tới lúc bắt đầu triển khai. [Nguồn: NIST SP 800-40 Rev. 4](https://csrc.nist.gov/pubs/sp/800/40/r4/final).

Sau bài học, người học có thể:

- Đặc tả phạm vi, mốc thời gian và điều kiện hoàn tất của patch SLA.
- Kết hợp mức nghiêm trọng, dấu hiệu khai thác, khả năng tiếp cận và tác động tài sản.
- Tách thời hạn đánh giá, giảm phơi nhiễm và vá đã xác minh.
- Xử lý trường hợp chưa có patch, phụ thuộc nhà cung cấp, change freeze hoặc rollback.
- Đo kết quả mà không che phần quá hạn, thiếu quan sát hoặc ngoại lệ.

Mọi ngưỡng, mức ưu tiên, mã định danh và tình huống trong bài là ví dụ cho một tổ chức giả định. Chúng không phải thời hạn bắt buộc chung từ NIST, FIRST hoặc một cơ quan quản lý.

## 2. Phân biệt SLA, mục tiêu nội bộ và các hình thức xử lý

Trong thực tế, tên “patch SLA” thường được dùng cả cho cam kết nội bộ. Cần ghi rõ tính chất của văn bản thay vì suy ra một hợp đồng có hiệu lực chỉ từ tên gọi.

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| SLA | Thỏa thuận về mức dịch vụ, phạm vi, trách nhiệm và điều kiện đánh giá | Cam kết xử lý giữa tổ chức và nhà cung cấp hoặc giữa các bên có thỏa thuận |
| SLO | Mục tiêu mức dịch vụ được dùng để vận hành và đo | Hoàn tất vá đã xác minh trong thời hạn của mức ưu tiên |
| Cam kết phối hợp nội bộ | Chia trách nhiệm và thời gian giữa các nhóm | Nhóm nền tảng bàn giao bản image trong một phần thời gian của deadline |
| Patch | Thay đổi phần mềm nhằm sửa vấn đề được xác định | Áp dụng bản cập nhật theo thông báo nhà cung cấp |
| Mitigation | Giảm khả năng khai thác hoặc hậu quả | Tắt đường bị ảnh hưởng hoặc hạn chế kết nối |
| Remediation | Xử lý khoảng trống theo phương án được chấp nhận | Vá, nâng cấp, thay thế hoặc ngừng thành phần có kiểm chứng |
| Risk acceptance | Quyết định chấp nhận phần rủi ro còn lại theo thẩm quyền | Cho phép vận hành giới hạn trong một thời hạn xác định |

Biện pháp giảm phơi nhiễm có thể cần thực hiện trước patch, nhưng không tự chứng minh phần mềm đã được sửa. Một ngoại lệ được duyệt cũng không biến bản vá chưa triển khai thành bản vá đã hoàn tất.

Nếu hợp đồng cho phép nhiều hình thức xử lý, cần nêu rõ điều kiện đóng cho từng hình thức. Không gộp “đã vá”, “đã tắt chức năng” và “đang chờ nhà cung cấp” vào cùng một trạng thái hoàn tất.

## 3. Phạm vi và đơn vị theo dõi

Một CVE có thể ảnh hưởng nhiều dịch vụ, phiên bản, máy chủ hoặc image. Một tài sản cũng có thể có nhiều lỗ hổng. Vì vậy, cần xác định đơn vị được đo.

Ví dụ đơn vị công việc:

~~~text
Lỗ hổng hoặc thông báo bảo mật
  + thành phần và phiên bản bị ảnh hưởng
  + tài sản hoặc nhóm triển khai được quản lý
  + môi trường
  + đường phơi nhiễm liên quan
~~~

Mã CVE không phải điều kiện duy nhất để bắt đầu quy trình. Một thông báo bảo mật đáng tin cậy của nhà cung cấp có thể cần xử lý trước khi có đầy đủ mã hoặc điểm số.

Danh mục cần bao phủ các đối tượng có liên quan:

- Hệ điều hành, appliance, runtime và middleware.
- Thư viện trực tiếp, gián tiếp, thành phần đóng gói cùng ứng dụng.
- Container image, máy ảo và nguồn tạo instance mới.
- Hệ thống danh tính, cơ chế quyền, mã hóa, audit và backup.
- Dịch vụ được quản lý hoặc SaaS theo phần trách nhiệm đã thỏa thuận.

Không chỉ đếm những tài sản đang gửi kết quả scanner. Tài sản mất quan sát vẫn cần được đối soát với inventory, nguồn triển khai và người sở hữu.

### Tài sản xuất hiện sau thông báo

Nếu tạo instance mới từ image cũ, không được coi đó là một cơ hội bắt đầu lại thời hạn cho cùng vấn đề đã biết mà policy yêu cầu chặn trước triển khai.

Cần quy định cách kế thừa finding, kiểm tra nguồn triển khai và xử lý tài sản mới. Khi tài sản đã tồn tại nhưng bị phát hiện muộn, ghi rõ khoảng trống quan sát; không chỉnh lịch sử để làm vấn đề trông như vừa xuất hiện.

## 4. Ưu tiên theo rủi ro, không chỉ theo một điểm số

Các yếu tố cần kết hợp:

| Yếu tố | Ý nghĩa khi đánh giá |
| --- | --- |
| Mức nghiêm trọng kỹ thuật | Khả năng và hậu quả được mô tả trong điều kiện của lỗ hổng |
| Dấu hiệu khai thác | Có bằng chứng khai thác thực tế, nhắm mục tiêu hoặc dấu hiệu trong môi trường không |
| Khả năng tiếp cận | Thành phần có phơi Internet, được gọi từ vùng không tin cậy hoặc qua chuỗi phụ thuộc không |
| Tác động tài sản | Vai trò của tài sản đối với dữ liệu, quyền, nghiệp vụ và phụ thuộc |
| Điều kiện khai thác | Cấu hình, tính năng, quyền hoặc tương tác cần thiết có tồn tại không |
| Kiểm soát hiện tại | Biện pháp nào đang có hiệu lực và bằng chứng cho tác dụng của chúng |
| Khả năng xử lý | Patch đã có, cần thay phiên bản lớn, phải reboot hoặc có phụ thuộc không |

CVSS cung cấp thông tin về mức nghiêm trọng; việc dùng điểm số cần giữ đúng phiên bản và ngữ cảnh. Không lấy một điểm cơ sở làm toàn bộ quyết định rủi ro của tài sản. [Nguồn: FIRST — CVSS v4.0 User Guide](https://www.first.org/cvss/v4.0/user-guide).

EPSS ước tính khả năng một CVE bị khai thác trong thực tế trong 30 ngày tiếp theo. Nó không phải xác suất tài sản cụ thể của tổ chức chắc chắn bị xâm nhập; cần kết hợp bối cảnh và tác động. [Nguồn: FIRST — EPSS FAQ](https://www.first.org/epss/faq).

Một thành phần có điểm nghiêm trọng cao nhưng không có đường khai thác trong cấu hình hiện tại vẫn cần căn cứ và theo dõi. Ngược lại, bằng chứng khai thác đang diễn ra có thể đòi phản ứng khẩn cấp dù điểm số chưa được cập nhật đầy đủ.

Nếu đã có dấu hiệu incident trong môi trường, kích hoạt quy trình ứng phó tương ứng song song với xử lý bản vá. Cài patch không tự điều tra hoặc loại bỏ những gì đã xảy ra trước đó.

## 5. Đồng hồ SLA: bắt đầu, kết thúc và không tự đặt lại

### 5.1. Ghi riêng các mốc

| Mốc | Ý nghĩa |
| --- | --- |
| t_signal | Thời điểm sớm nhất kênh quy định của tổ chức tiếp nhận tín hiệu đáng tin cậy liên quan tới thành phần đang sử dụng |
| t_vendor | Thời điểm nhà cung cấp phát hành bản sửa hoặc phiên bản hỗ trợ phù hợp với phạm vi |
| t_triage | Thời điểm hoàn tất đánh giá khả năng bị ảnh hưởng, ưu tiên và người sở hữu |
| t_mitigated | Thời điểm biện pháp giảm phơi nhiễm đã được kiểm chứng |
| t_installed | Thời điểm hoàn tất thao tác triển khai hoặc cài đặt |
| t_verified | Thời điểm có bằng chứng runtime và phạm vi đã đáp ứng điều kiện đóng |
| t_closed | Thời điểm hồ sơ được đóng theo quy trình |

Các mốc không thay thế nhau. Tạo ticket lúc 14:00 không cho phép bỏ qua cảnh báo đã tiếp nhận lúc 08:00. Đã cài lúc 10:00 không chứng minh t_verified cũng là 10:00.

Trong chính sách minh họa:

- Thời hạn triage và giảm phơi nhiễm tính từ t_signal.
- Thời hạn vá đã xác minh tính từ t_patch_start = thời điểm muộn hơn giữa t_signal và t_vendor.
- Nếu patch đã có trước khi tổ chức tiếp nhận tín hiệu, t_patch_start là t_signal.
- Nếu patch chưa có, vẫn theo dõi tuổi phơi nhiễm và deadline giảm phơi nhiễm từ t_signal.

Đây là một lựa chọn thiết kế đồng hồ. Tổ chức có thể quy định khác, nhưng phải nêu rõ; không chọn lại mốc có lợi sau khi biết kết quả.

### 5.2. “Bản vá có sẵn” phải có định nghĩa

t_vendor không phải lúc nhóm triển khai tải xong, có thời gian thử hoặc nhận được lịch maintenance. Những việc đó thuộc thời gian xử lý của tổ chức.

Cần xác định phiên bản, nhánh sản phẩm và nguồn phát hành phù hợp. Nếu nhà cung cấp không có bản sửa cho nhánh đã hết hỗ trợ, phải có kế hoạch nâng cấp, thay thế hoặc kết thúc sử dụng; không để trạng thái “chưa có patch” kéo dài mà không có quyết định.

### 5.3. Các khoảng thời gian bị bỏ sót

Policy cần quy định giờ lịch hay giờ làm việc, múi giờ, cuối tuần, ngày nghỉ, maintenance window và sự cố hệ thống theo dõi.

Trong ví dụ, thời hạn dùng giờ lịch liên tục. Change freeze, chờ nhà cung cấp trả lời hoặc chờ phê duyệt nội bộ không tự dừng những đồng hồ đã bắt đầu.

Nếu một thỏa thuận thực sự cho phép tạm dừng trong điều kiện nhất định, phải ghi điều kiện, người có thẩm quyền, thời gian và lịch sử; báo cáo cần thể hiện thời gian thực tế cùng cách tính theo thỏa thuận.

## 6. Ma trận thời hạn minh họa

Ví dụ chọn mức ưu tiên cao nhất thỏa điều kiện đã được xác nhận:

| Mức | Điều kiện minh họa | Hoàn tất triage từ t_signal | Vá đã xác minh từ t_patch_start |
| --- | --- | --- | --- |
| P0 | Có bằng chứng khai thác liên quan và đường ảnh hưởng có khả năng gây hậu quả nghiêm trọng; hoặc dấu hiệu xâm nhập trong môi trường | 1 giờ | 24 giờ |
| P1 | Đường tiếp cận không tin cậy, tác động cao và điều kiện khai thác có trong cấu hình | 4 giờ | 72 giờ |
| P2 | Thành phần bị ảnh hưởng, tác động đáng kể nhưng mức tiếp cận hoặc điều kiện hiện tại hạn chế hơn | 24 giờ | 14 ngày lịch |
| P3 | Rủi ro còn lại thấp hơn theo đánh giá có căn cứ | 3 ngày lịch | 30 ngày lịch |

Trong ví dụ, P0 còn có deadline giảm phơi nhiễm đã kiểm chứng trong 4 giờ từ t_signal; P1 là 24 giờ. Nếu chưa có patch, các deadline đó vẫn có hiệu lực.

Ma trận chỉ mô tả một policy giả định. Năng lực triển khai, loại tài sản, tác động gián đoạn và nghĩa vụ thực tế phải được đánh giá trước khi chọn cam kết.

### Chưa xác định được khả năng ảnh hưởng

Không đủ dữ liệu không đồng nghĩa tài sản không bị ảnh hưởng. Trong thời hạn triage, cần làm rõ hoặc gắn trạng thái chưa xác định cùng người xử lý và cách giảm phơi nhiễm phù hợp.

Một scanner không nhìn thấy package không tự chứng minh thành phần không tồn tại. Cần xét thư viện đóng gói, bản sao gián tiếp, image hoặc runtime khác theo kiến trúc.

### Thay đổi mức ưu tiên

Khi có tín hiệu làm tăng rủi ro, policy cần chỉ rõ cách rút ngắn deadline. Ví dụ:

~~~text
deadline_mới = thời điểm sớm hơn giữa:
  deadline đang có
  thời điểm tiếp nhận tín hiệu nâng mức + thời hạn của mức mới
~~~

Giả sử tại D0 08:00, finding P1 có patch sẵn nên hạn là D3 08:00. Tại D0 12:00, bằng chứng mới làm finding thành P0:

~~~text
Hạn cũ: D3 08:00
Hạn theo tín hiệu nâng mức: D1 12:00
Hạn mới: D1 12:00
~~~

Không đặt lại thành một cửa sổ đầy đủ chỉ vì đổi tên ticket. Nếu finding đã quá hạn, nâng mức không xóa lịch sử quá hạn.

Hạ mức hoặc thay đổi căn cứ cần bằng chứng và cơ chế quyết định tương ứng. Không tự kéo dài deadline chỉ vì người xử lý đổi nhãn.

## 7. Đặc tả một yêu cầu patch SLA

Ví dụ:

**PATCH-REQ-01:** với các đối tượng thuộc danh mục quản lý, tổ chức phải đánh giá tín hiệu bảo mật theo thời hạn triage, triển khai biện pháp giảm phơi nhiễm khi policy yêu cầu và hoàn tất bản sửa đã xác minh theo mức ưu tiên, với lịch sử mốc thời gian và phạm vi đầy đủ.

Một hồ sơ công việc nên ghi:

| Trường | Nội dung |
| --- | --- |
| Định danh vấn đề | CVE hoặc mã advisory/finding đáng tin cậy |
| Phạm vi | Thành phần, phiên bản, tài sản, môi trường và đường phơi nhiễm |
| Chủ sở hữu | Người hoặc nhóm chịu trách nhiệm, nhóm phối hợp và tuyến escalation |
| Căn cứ ảnh hưởng | Advisory, inventory, cấu hình, bằng chứng runtime |
| Căn cứ ưu tiên | Dấu hiệu khai thác, khả năng tiếp cận, tác động, kiểm soát và độ không chắc chắn |
| Mốc thời gian | t_signal, t_vendor, triage, mitigation, cài đặt, kiểm chứng |
| Deadline | Giá trị cụ thể, policy phiên bản nào, quy tắc tính |
| Phương án | Patch, nâng cấp, thay thế, ngừng sử dụng hoặc mitigation tạm thời |
| Triển khai | Artifact, nguồn patch, nhóm canary, reboot hoặc restart cần thiết |
| Kiểm chứng | Điều kiện hoàn tất và bằng chứng cho từng nhóm tài sản |
| Ngoại lệ | Phạm vi, rủi ro còn lại, người phê duyệt và thời hạn |
| Kết quả | Đúng hạn, quá hạn, chưa xác định hoặc hình thức đóng phù hợp |

### Tiêu chí chấp nhận tối thiểu

1. t_signal không bị thay bởi thời điểm mở ticket hoặc thời điểm scanner chạy lại.
2. Mức ưu tiên và deadline có căn cứ, phiên bản và lịch sử thay đổi.
3. Tất cả tài sản thuộc phạm vi được ánh xạ, kể cả phần chưa có kết quả quan sát.
4. Mitigation có kết quả kiểm tra riêng, không được ghi thành patch hoàn tất.
5. t_verified chỉ được ghi sau khi điều kiện runtime và phạm vi đạt.
6. Phần không đạt được chuyển cấp xử lý theo thời hạn đã quy định.

Nếu có một deadline bên ngoài thực sự áp dụng, phải lưu nguồn, phạm vi và cách phối hợp với deadline nội bộ. Không suy ra mọi tổ chức đều chịu cùng một thời hạn từ một danh mục hoặc một ví dụ chính sách bên ngoài.

## 8. Từ patch có sẵn tới patch có hiệu lực

Một quy trình triển khai có thể gồm:

1. Xác định phạm vi và hướng xử lý theo advisory đáng tin cậy.
2. Thu nhận bản sửa từ nguồn được chấp nhận, kiểm tra tính xác thực và toàn vẹn phù hợp.
3. Đánh giá tương thích, phụ thuộc, restart hoặc reboot và phương án phục hồi.
4. Thực hiện các phép kiểm tra gắn với phần thay đổi và rủi ro.
5. Triển khai theo nhóm hoặc canary khi phù hợp.
6. Xác minh phiên bản, cấu hình và điều kiện runtime trên phạm vi.
7. Cập nhật nguồn triển khai, bằng chứng, kết quả và finding.

Các bước có thể chồng lấn hoặc tự động hóa, nhưng không được bỏ điều kiện bắt buộc chỉ để kịp một con số trên dashboard.

### Dành thời gian cho kiểm chứng

SLA kết thúc ở t_verified cần bao gồm thời gian lấy quyền, chuẩn bị thay đổi, triển khai và thu bằng chứng. Nếu nhóm chỉ phân bổ thời gian đến t_installed, phần còn lại có thể vượt deadline.

Thỏa thuận phối hợp nội bộ nên để đủ khoảng cho bước sau. Không để mỗi nhóm tự có một cửa sổ đầy đủ bằng toàn bộ SLA rồi cộng chúng thành thời gian thực tế dài hơn cam kết.

### Bản vá không được phá điều kiện bảo mật khác

Các phép kiểm tra cần theo phần bị ảnh hưởng:

| Thành phần được vá | Điều cần chú ý |
| --- | --- |
| IdP, gateway hoặc thư viện xác thực | Luồng hợp lệ, điều kiện xác thực, phiên và thu hồi |
| Policy engine hoặc middleware quyền | Hành vi được phép, bị cấm và ranh giới dữ liệu |
| Database hoặc thư viện mã hóa | Tính nhất quán, quyền truy cập, cơ chế bảo vệ và khóa |
| Audit collector hoặc agent | Sự kiện, danh tính, độ trễ và tính đầy đủ |
| Công cụ backup hoặc hạ tầng phục hồi | Khả năng đọc nguồn, phục hồi và quyền trong môi trường khôi phục |

Không tự tắt MFA, kiểm tra quyền hoặc audit để làm bản cập nhật “chạy ổn” rồi kết luận mục tiêu bảo mật đã đạt.

Nếu đã có dấu hiệu khai thác, việc triển khai patch cần phối hợp với incident. Bản sửa có thể ngăn một đường khai thác nhưng không tự thu hồi bí mật bị lộ hoặc xử lý dữ liệu đã bị thay đổi.

## 9. Điều kiện đóng: xác minh runtime và toàn bộ phạm vi

### 9.1. Bằng chứng cần chứng minh

Một điều kiện hoàn tất có thể yêu cầu:

- Bản sửa hoặc phiên bản thay thế đáp ứng advisory cho đúng sản phẩm và nhánh.
- Artifact, package hoặc cấu hình đã được áp dụng lên các đối tượng thuộc phạm vi.
- Tiến trình, kernel hoặc thành phần đang phục vụ thực sự dùng trạng thái đã sửa.
- Restart, reboot hoặc bước kích hoạt bắt buộc đã hoàn tất.
- Phép kiểm tra phù hợp không còn xác nhận điều kiện dễ bị ảnh hưởng trong phạm vi.
- Kiểm tra chức năng và thuộc tính bảo mật liên quan đạt.
- Nguồn tạo instance mới không tiếp tục đưa lại trạng thái đã biết là có lỗi.
- Phần chưa kiểm chứng, mất quan sát hoặc loại trừ được thể hiện rõ.

Không phải mọi finding cần chạy khai thác thực tế. Có thể dùng kiểm tra phiên bản, cấu hình, công cụ xác nhận của nhà cung cấp hoặc đánh giá chuyên môn phù hợp. Phương pháp phải đủ hỗ trợ kết luận và không vượt phạm vi đã cho phép.

### 9.2. Các trường hợp dễ đóng nhầm

| Trường hợp | Vì sao chưa đủ |
| --- | --- |
| Package đã cập nhật nhưng tiến trình chưa restart | Bản đang phục vụ có thể vẫn nạp thành phần cũ |
| Kernel mới đã cài nhưng chưa reboot khi cần | Kernel hiệu lực có thể chưa được thay |
| Thư viện nguồn đã nâng nhưng chưa build và deploy | Artifact đang chạy chưa thay đổi |
| Một dependency đã nâng nhưng còn bản đóng gói khác | Chưa bao phủ mọi bản sao thuộc ứng dụng |
| Image mới đã build nhưng node chưa thay | Runtime vẫn dùng image cũ |
| Node hiện tại đã sửa nhưng template vẫn cũ | Autoscaling hoặc phục hồi có thể tạo lại đối tượng lỗi |
| Canary đã đạt | Chưa chứng minh các nhóm còn lại đã được xử lý |
| Scanner không còn báo ở một node | Có thể mất quyền quét, thiếu dữ liệu hoặc phạm vi chưa đủ |

Với bản sửa được backport, phiên bản upstream có thể không đổi theo cách scanner đơn giản mong đợi. Cần đối chiếu package, build và advisory của nhà cung cấp thay vì chỉ so một chuỗi phiên bản. Nếu kết luận scanner là sai, lưu căn cứ cụ thể; không bỏ qua mọi cảnh báo cùng tên.

### 9.3. Cluster, node offline và nguồn triển khai

Tài sản offline chưa có bằng chứng vá không được tự biến mất khỏi phạm vi. Cần xác định có tiếp tục tồn tại, có thể quay lại và điều kiện kiểm tra trước khi tái tham gia.

Nếu ngừng sử dụng là hình thức remediation được chấp nhận, phải chứng minh nó không còn phục vụ, không còn quyền liên quan và không bị nguồn tự động tạo lại. Xóa một dòng khỏi inventory chưa đủ.

Một dịch vụ có 9/10 node đã vá cần báo đúng phần đã hoàn tất và node còn lại. Tỷ lệ cao không chứng minh dịch vụ đã đạt một tiêu chí yêu cầu bao phủ toàn bộ.

### 9.4. Nhiều hình thức đóng phải có tên riêng

Có thể dùng các kết quả như:

- PATCHED_VERIFIED: bản sửa đã có hiệu lực và được kiểm chứng.
- UPGRADED_VERIFIED: phiên bản thay thế xử lý vấn đề và đã được kiểm chứng.
- RETIRED_VERIFIED: phạm vi được ngừng sử dụng theo điều kiện chấp nhận.
- NOT_AFFECTED: có căn cứ phù hợp rằng đối tượng không thuộc điều kiện bị ảnh hưởng.

MITIGATED, WAITING_VENDOR hoặc EXCEPTION_APPROVED cần được theo dõi riêng nếu phần mềm còn chưa sửa. Không dùng các nhãn đó để làm tăng số tài sản đã được vá.

Đánh giá không bị ảnh hưởng cần theo đúng sản phẩm, cấu hình và thời điểm. Nếu một thay đổi sau đó làm xuất hiện điều kiện khai thác, phải xem xét lại căn cứ cũ.

## 10. Trường hợp chưa có patch, EOL và phụ thuộc nhà cung cấp

### Chưa có bản sửa phù hợp

Trong chính sách ví dụ, chưa có t_vendor nghĩa là đồng hồ vá chưa bắt đầu, nhưng tuổi phơi nhiễm và deadline giảm phơi nhiễm vẫn tính từ t_signal.

Hồ sơ cần có:

- Biện pháp giảm phơi nhiễm và kết quả kiểm chứng.
- Phần rủi ro còn lại và người có trách nhiệm.
- Mốc xem xét lại, theo dõi nguồn nhà cung cấp và trigger nâng mức.
- Phương án thay thế hoặc ngừng chức năng nếu không thể giữ rủi ro trong điều kiện được phép.
- Cách xác định t_vendor khi bản sửa xuất hiện.

Không đóng finding chỉ vì chưa có patch. “Chưa có bản sửa” là trạng thái kỹ thuật; “được phép tiếp tục” là quyết định quản trị có điều kiện.

### Thành phần đã hết hỗ trợ

Nếu không có nhánh sửa được hỗ trợ, cần deadline chuyển đổi có chủ sở hữu và tiêu chí riêng. Không cho EOL trở thành lý do giữ WAITING_VENDOR vô thời hạn.

Biện pháp tạm thời phải được theo dõi trong suốt quá trình chuyển đổi. Thêm một lớp hạn chế truy cập chưa tự chứng minh mọi đường khai thác đã được xử lý.

### Dịch vụ bên ngoài

Với SaaS hoặc dịch vụ được quản lý, xác định phần nhà cung cấp sửa và phần khách hàng phải làm. Bằng chứng nhà cung cấp cần ánh xạ tới sản phẩm, tenant hoặc phạm vi, thời gian và loại xử lý phù hợp.

Không tự coi một thông báo chung “đã cập nhật” là bằng chứng mọi phạm vi đã hoàn tất. Các cấu hình, agent, connector hoặc phiên bản tích hợp do tổ chức quản lý vẫn cần được xem xét.

## 11. Change freeze, rollback và ngoại lệ

### Change freeze

Một lịch đóng băng thay đổi không tự dừng SLA. Cần có cơ chế xử lý khẩn cấp hoặc quyết định có thẩm quyền, cùng biện pháp giảm phơi nhiễm và giới hạn vận hành.

Việc chờ lịch maintenance phải thể hiện trong tuổi công việc và báo cáo. Nếu một thỏa thuận cho phép thay deadline, giữ cả căn cứ và lịch sử; không sửa âm thầm mốc ban đầu.

### Rollback

Nếu rollback đưa runtime về trạng thái bị ảnh hưởng, finding không còn được xem là đã sửa trong hiện trạng. Cần mở lại hoặc liên kết hồ sơ tái xuất hiện theo policy, giữ lịch sử và không tự cấp một cửa sổ mới chỉ vì đã đổi deployment.

Trong ví dụ, rollback của đợt xử lý đang thực hiện không đặt lại deadline gốc. Phải kiểm chứng biện pháp bảo vệ, tác động nghiệp vụ và phương án tiếp theo.

Từng thời điểm đã đạt hoặc chưa đạt cần được giữ đúng. Không xóa lần kiểm chứng trước, nhưng cũng không dùng nó để chứng minh trạng thái sau rollback.

### Ngoại lệ

Hồ sơ ngoại lệ cần có phạm vi, lý do, rủi ro còn lại, biện pháp bù đắp, chủ rủi ro, người phê duyệt, hạn kết thúc và trigger thu hồi.

Tách kết quả kỹ thuật khỏi kết quả quản trị: phần mềm chưa vá vẫn chưa vá; ngoại lệ giải thích điều kiện tiếp tục vận hành. Việc một nghĩa vụ bên ngoài có cho phép phương án đó hay không phải được xác định theo căn cứ thực sự áp dụng.

## 12. Tình huống: deadline rút ngắn và một node hoàn tất muộn

### 12.1. Bối cảnh

Một gateway của dịch vụ hóa đơn có bốn node thuộc phạm vi. Advisory giả định ADV-DEMO-01 ảnh hưởng phiên bản đang chạy; bản sửa phù hợp đã được phát hành trước khi tổ chức tiếp nhận thông báo.

Áp dụng policy minh họa ở trên:

| Mốc | Sự kiện | Kết quả |
| --- | --- | --- |
| D0 08:00 | Kênh quy định tiếp nhận advisory, patch đã có | t_signal và t_patch_start là D0 08:00 |
| D0 08:45 | Triage xác nhận ảnh hưởng, xếp P1 | Đạt hạn triage P1; deadline vá là D3 08:00 |
| D0 12:00 | Có bằng chứng mới làm rủi ro thành P0 | Deadline được tính lại theo quy tắc rút ngắn |
| D0 12:30 | Hoàn tất đánh giá lại và giao trách nhiệm khẩn cấp | Có căn cứ, phạm vi và người xử lý |
| D0 13:30 | Biện pháp giảm phơi nhiễm được kiểm chứng | Theo dõi riêng với việc vá |
| D1 12:20 | Node cuối cùng hoàn tất kiểm chứng runtime | Toàn phạm vi đã sửa, nhưng sau deadline |

Deadline vá mới là thời điểm sớm hơn giữa D3 08:00 và D1 12:00, tức D1 12:00.

Áp dụng quy tắc rút ngắn riêng cho đồng hồ giảm phơi nhiễm: hạn P1 cũ là D1 08:00; hạn theo tín hiệu P0 là D0 16:00. Biện pháp được xác minh lúc D0 13:30 nên đáp ứng hạn giảm phơi nhiễm.

### 12.2. Kết quả từng node

| Node | t_installed | t_verified | So với deadline D1 12:00 |
| --- | --- | --- | --- |
| N1 | D1 08:30 | D1 09:00 | Đúng hạn |
| N2 | D1 09:15 | D1 09:45 | Đúng hạn |
| N3 | D1 10:00 | D1 10:40 | Đúng hạn |
| N4 | D1 11:50 | D1 12:20 | Muộn 20 phút |

Nếu chỉ dùng thời điểm cài đặt, báo cáo có thể ghi cả bốn node đúng hạn. Nhưng policy yêu cầu runtime được kiểm chứng, nên N4 không đạt thời hạn.

Tại deadline, độ bao phủ đã xác minh là 3/4. Sau D1 12:20, trạng thái kỹ thuật có thể là 4/4 đã sửa, còn kết quả SLA vẫn ghi một đối tượng hoàn tất muộn.

### 12.3. Các kết luận cần tách

- Đánh giá ban đầu hoàn tất trong hạn P1.
- Rủi ro được nâng mức và deadline được rút ngắn có lịch sử.
- Biện pháp giảm phơi nhiễm đạt deadline riêng.
- Toàn phạm vi đã được vá và kiểm chứng sau D1 12:20.
- Cam kết hoàn tất đúng hạn không đạt cho N4.
- Nguyên nhân chậm cần được phân tích và chuyển thành cải tiến cụ thể.

Không đổi deadline thành D1 12:20 để làm báo cáo xanh. Cũng không bỏ finding khỏi báo cáo quá hạn chỉ vì nó đã được xử lý ngay sau đó.

## 13. Evidence cho patch SLA

Một hồ sơ kiểm chứng nên có:

1. Nguồn advisory, thời điểm tiếp nhận và căn cứ ảnh hưởng.
2. Tập tài sản, phiên bản, người sở hữu và lịch sử ánh xạ phạm vi.
3. Policy, mức ưu tiên, deadline và các thay đổi có căn cứ.
4. Tình trạng bản sửa theo nguồn nhà cung cấp.
5. Biện pháp giảm phơi nhiễm cùng phép kiểm chứng và thời hạn hiệu lực.
6. Nguồn patch, artifact hoặc package được triển khai.
7. Phiên bản và trạng thái runtime, restart hoặc reboot khi cần.
8. Kết quả kiểm tra kỹ thuật, chức năng và bảo mật liên quan.
9. Phần chưa quan sát, node chưa hoàn tất và ngoại lệ.
10. Mốc đóng, hình thức đóng và kết quả đúng hạn hoặc quá hạn.

Ví dụ bản ghi nội bộ:

~~~text
Work item: PATCH-RUN-042-N4
Advisory: ADV-DEMO-01
Asset: N4, gateway của dịch vụ hóa đơn
Affected state: phiên bản và cấu hình được ghi nhận
Priority history: P1 -> P0, có căn cứ và thời điểm

Signal received: D0 08:00
Vendor fix available: trước D0 08:00
Effective patch deadline: D1 12:00
Installed: D1 11:50
Verified: D1 12:20

Technical result: PATCHED_VERIFIED
SLA result: LATE, 20 phút
Mitigation: tham chiếu kết quả kiểm chứng riêng
Evidence: advisory, artifact, runtime, kết quả kiểm tra
~~~

Các giá trị là minh họa, không phải kết quả đã thực hiện trên hệ thống thật.

Bằng chứng cần gắn với đúng bản triển khai. Một báo cáo scan cũ hoặc kết quả từ canary không thay thế kết quả của N4. Khi dùng bằng chứng nhà cung cấp hoặc công cụ, ghi rõ phạm vi và giới hạn.

Không đưa thông tin xác thực, token truy cập máy chủ hoặc bí mật triển khai vào report chia sẻ. Tham chiếu an toàn tới nguồn được bảo vệ khi cần xem chi tiết.

## 14. Chỉ số và cách tránh báo cáo sai lệch

### Tỷ lệ đúng hạn

Có thể chọn cohort gồm các đơn vị công việc có deadline trong kỳ và đã xác định thuộc phạm vi:

~~~text
Tỷ lệ hoàn tất đúng hạn
  = số đơn vị có t_verified <= deadline
    / tổng số đơn vị áp dụng có deadline trong kỳ
~~~

Nếu cho phép hình thức remediation khác, phải định nghĩa rõ loại nào thuộc chỉ số. Không gọi tất cả chúng là “tỷ lệ đã vá” khi có đối tượng chỉ được ngừng sử dụng.

Ví dụ có 100 đơn vị đến hạn:

- 90 hoàn tất đúng hạn.
- 5 đã hoàn tất nhưng muộn.
- 3 vẫn quá hạn.
- 2 chưa có đủ bằng chứng kiểm chứng và đã qua deadline.

Tỷ lệ đúng hạn là 90/100 = 90%. Tỷ lệ đã hoàn tất có bằng chứng là 95/100 = 95%, nhưng không thay thế kết quả đúng hạn. Hai đơn vị thiếu bằng chứng không được loại khỏi mẫu số chỉ để tăng tỷ lệ.

### Các chỉ số bổ sung

- Số đối tượng quá hạn theo ưu tiên, dịch vụ và chủ sở hữu.
- Tuổi phơi nhiễm tính từ t_signal, kể cả thời gian chưa có patch.
- Thời gian chờ patch nhà cung cấp và thời gian xử lý sau khi patch có.
- Độ bao phủ inventory và độ mới của bằng chứng runtime.
- Số ngoại lệ, thời hạn và hiệu lực biện pháp bù đắp.
- Finding tái xuất hiện do rollback, image cũ hoặc triển khai mới.
- Mức hoàn tất theo tài sản quan trọng, không chỉ theo số lượng tổng.

Thời gian trung bình chỉ tính trên việc đã đóng có thể che các việc mở rất lâu. Cần giữ nhóm chưa hoàn tất và phân bố theo mức rủi ro.

Một CVE ảnh hưởng 100 node và một CVE ảnh hưởng 1 node không phải cùng đơn vị đo nếu chỉ đếm mã CVE. Chỉ số phải ghi rõ đang đo finding, cặp lỗ hổng–tài sản, dịch vụ hay nhóm triển khai.

### Trạng thái kỹ thuật và trạng thái cam kết

Đã sửa hiện tại, đã hoàn tất đúng hạn, được chấp nhận ngoại lệ và chưa đủ bằng chứng là các thông tin khác nhau. Dashboard nên thể hiện chúng riêng.

Một ngoại lệ có thể cho phép vận hành trong điều kiện giới hạn, nhưng không được âm thầm loại khỏi mọi báo cáo phơi nhiễm hoặc quá hạn. Cách tính theo thỏa thuận và sự thật kỹ thuật cần được giữ rõ.

## 15. Phân công trách nhiệm và kiểm chứng quy trình

| Vai trò | Trách nhiệm minh họa |
| --- | --- |
| Nhóm quản lý lỗ hổng | Tiếp nhận, đối soát phạm vi, điều phối ưu tiên và theo dõi thời gian |
| Chủ dịch vụ / tài sản | Chịu trách nhiệm xử lý trong phạm vi, phụ thuộc và tác động nghiệp vụ |
| Nhóm phát triển | Nâng thư viện, rebuild artifact và kiểm chứng thay đổi ứng dụng |
| Nhóm nền tảng / vận hành | Triển khai, reboot, thay node và cập nhật nguồn tạo tài sản |
| Nhóm bảo mật | Đánh giá dấu hiệu khai thác, mitigation, kiểm chứng và phối hợp incident |
| Chủ rủi ro / người có thẩm quyền | Quyết định ngoại lệ, giới hạn và phương án tiếp tục |
| Đầu mối nhà cung cấp | Theo dõi bản sửa, phạm vi dịch vụ và bằng chứng bên ngoài |

Chuyển ticket sang nhóm khác không được làm mất chủ sở hữu hoặc đặt lại đồng hồ. Khi trách nhiệm thay đổi, ghi rõ người tiếp nhận và phần việc còn lại.

Có thể kiểm chứng chính hệ thống theo dõi SLA bằng các tình huống:

- Một cảnh báo lặp lại không đặt lại t_signal.
- Mở ticket muộn vẫn giữ mốc tiếp nhận ban đầu.
- Patch đã có trước cảnh báo không bắt đầu tính từ lúc tải về.
- Nâng mức ưu tiên rút ngắn deadline đúng quy tắc.
- Canary đạt không đóng toàn bộ cluster.
- Node mất dữ liệu quan sát được giữ là chưa xác minh.
- Rollback trong đợt xử lý không tự cấp cửa sổ mới.
- Ngoại lệ hết hạn kích hoạt xử lý theo policy.
- Triển khai từ image cũ làm finding được liên kết và xử lý đúng.

Các tình huống này xác nhận khả năng đo và điều phối. Chúng không thay thế kiểm chứng bản vá trên tài sản thật thuộc phạm vi.

## 16. Những lỗi thường gặp và cách sửa

| Lỗi | Hệ quả | Điều cần thay đổi |
| --- | --- | --- |
| Chỉ dùng CVSS để gán mọi deadline | Bỏ qua khai thác, tiếp cận và tác động thực tế | Kết hợp bối cảnh và lưu căn cứ |
| Lấy lúc mở ticket làm mốc mặc định | Che thời gian phát hiện hoặc phân công chậm | Dùng mốc tiếp nhận theo policy |
| Chờ maintenance rồi mới bắt đầu tính | Làm cam kết mất ý nghĩa | Tính lịch rõ ràng và có tuyến xử lý khẩn cấp |
| Chưa có patch nên đóng finding | Mất theo dõi tuổi phơi nhiễm | Theo dõi mitigation, xem xét lại và phương án thay thế |
| Cài xong là đóng | Runtime có thể vẫn dùng bản lỗi | Kiểm tra kích hoạt và trạng thái đang phục vụ |
| Chỉ vá node hiện tại | Image hoặc template tạo lại tài sản lỗi | Kiểm soát nguồn triển khai và tài sản mới |
| Một kết quả scan sạch được coi là đủ | Có thể thiếu quyền hoặc mất phạm vi | Đối soát nguồn bằng chứng và inventory |
| Rollback rồi tạo ticket mới | Lịch sử và deadline bị đặt lại | Liên kết finding và giữ quy tắc thời gian |
| Mitigation được ghi thành patch | Báo cáo giảm rủi ro sai bản chất | Tách trạng thái và điều kiện kết thúc |
| Chỉ báo số đã đóng | Che nhóm tồn đọng lâu và quá hạn | Báo cả cohort đến hạn, tuổi mở và mức rủi ro |

## 17. Thực hành đặc tả patch SLA

Với dịch vụ hóa đơn giả định, lập policy có phạm vi tài sản, nguồn tín hiệu, mốc thời gian, ưu tiên, deadline, người sở hữu và điều kiện đóng.

Áp dụng cho ba tình huống: patch đã có khi tiếp nhận cảnh báo; chưa có patch nhưng đường bị ảnh hưởng đang phơi ra vùng không tin cậy; patch phải rollback sau canary. Với mỗi tình huống, ghi các đồng hồ, biện pháp giảm phơi nhiễm, phần chưa đạt và bằng chứng cần thu thập.

Bổ sung một node được tạo từ image cũ sau khi đợt vá hoàn tất. Xác định cách phát hiện, liên kết phạm vi và xử lý mà không che lịch sử vấn đề đã biết.

Security patch SLA có giá trị khi thời gian được tính nhất quán, phạm vi không bị bỏ sót và việc hoàn tất được chứng minh trên trạng thái đang phục vụ. Cam kết đó phải dẫn tới giảm phơi nhiễm thực tế, đồng thời giữ rõ các phần chưa sửa, quá hạn và rủi ro còn được quản lý.
