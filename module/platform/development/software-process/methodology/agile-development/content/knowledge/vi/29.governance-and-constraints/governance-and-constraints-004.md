# Xử lý thời hạn bắt buộc và phạm vi có thể thương lượng

Một nhóm Agile xây dựng nền tảng học tập có lịch mở đăng ký workshop vào **ngày 15 tháng 12** theo cam kết với đối tác. Còn ba tuần, nhiều chức năng vẫn chưa hoàn tất: đăng ký giữ chỗ, xem trạng thái, email xác nhận, tìm kiếm nâng cao, xuất báo cáo và giao diện lịch tháng. Stakeholder yêu cầu “phải xong hết đúng ngày”; Developers lo kiểm thử đồng thời và phân quyền chưa đầy đủ; Product Owner cần quyết định điều gì thật sự phải có khi mở đăng ký. Nếu nhóm chỉ đáp lại “Agile nên linh hoạt deadline”, họ có thể bỏ qua một cam kết thật. Nếu nhóm cố giao mọi thứ bằng cách bỏ kiểm thử, họ có thể giao **một hệ thống không đáng tin** đúng ngày.

**Xử lý thời hạn bắt buộc và phạm vi có thể thương lượng** là nghệ thuật **làm rõ những ràng buộc không thể vi phạm, đưa ra lựa chọn về phạm vi và phương án triển khai, duy trì chất lượng, đồng thời dự báo trung thực với người có thẩm quyền**. Agile không hứa rằng mọi khối lượng công việc đều vừa trong một thời hạn. Agile cung cấp cách **nhận phản hồi sớm, giảm kích thước lô công việc và thích ứng với bằng chứng thực tế** để tạo giá trị cao nhất trong các giới hạn đã biết.

Bài thuộc chương **Quản trị và ràng buộc** của module **AGILE_DEVELOPMENT**. Nội dung liên kết giá trị và nguyên tắc Agile với **Product Backlog, user story, Scrum, Kanban, XP, dòng công việc, chất lượng liên tục và phát hành tăng dần**. Bài dùng một bối cảnh workshop giả định xuyên suốt, kèm công cụ phân loại ràng buộc, mẫu quyết định, ví dụ dự báo, sơ đồ và bài tập.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt **deadline thực sự bắt buộc**, mốc kế hoạch, mục tiêu mong muốn và giả định cần xác minh.
2. Nhận diện các loại ràng buộc: **thời gian, pháp lý/hợp đồng, ngân sách, chất lượng, bảo mật, năng lực, phụ thuộc, vận hành**.
3. Tách **outcome bắt buộc** khỏi danh sách tính năng được mong muốn, xác định **phạm vi tối thiểu an toàn và có giá trị**.
4. Thương lượng phạm vi theo bằng chứng, nêu rõ **phần giữ lại, hoãn, thay thế hoặc bỏ** và hệ quả của từng lựa chọn.
5. Dự báo bằng năng lực và dữ liệu dòng công việc, thể hiện **bất định, giả định, rủi ro và mốc quyết định** thay vì cam kết giả.
6. Phân biệt **Sprint Goal, Sprint Backlog, Product Goal và Definition of Done** khi có thay đổi gần mốc bắt buộc.
7. Lập kế hoạch kiểm chứng, tích hợp, phát hành và khôi phục theo giai đoạn mà **không đánh đổi tiêu chuẩn chất lượng**.
8. Thiết lập cơ chế quản trị và đường ra quyết định cho trường hợp mâu thuẫn giữa deadline, phạm vi và an toàn.
9. Áp dụng ví dụ workshop, bảng trade-off và checklist để hướng dẫn một cuộc trao đổi khó với stakeholder.

## 2. Agile không có nghĩa mọi thứ đều có thể linh hoạt

Agile nhấn mạnh **phản ứng với thay đổi hơn là bám theo kế hoạch**, nhưng không nói rằng đội ngũ có thể tự ý bỏ qua hợp đồng, nghĩa vụ an toàn, giới hạn ngân sách hay sự kiện khách hàng không thể dời. Một số ràng buộc đến từ môi trường thực:

- **Sự kiện theo lịch:** Cổng đăng ký phải sẵn sàng trước ngày khai giảng hoặc hội nghị.
- **Cam kết hợp đồng:** Phải bàn giao một năng lực đã được mô tả vào mốc đã thỏa thuận.
- **Quy định/kiểm toán:** Cần cung cấp hồ sơ, bằng chứng hoặc kiểm soát theo thời hạn có hiệu lực.
- **Phụ thuộc đối tác:** API cũ ngừng hỗ trợ hoặc nhà cung cấp đóng cửa sổ chuyển đổi.
- **Giới hạn tài chính:** Không có ngân sách không giới hạn để kéo dài dự án.
- **An toàn và chất lượng:** Không được để dữ liệu người dùng bị lộ hoặc giao dịch ghi sai chỉ để giao nhanh.

**Điều Agile giúp làm tốt là nhìn thấy lựa chọn và rủi ro sớm hơn**, không biến giới hạn thành không tồn tại.

### 2.1. Cần phân biệt “bắt buộc” ở mức nào

Hai câu sau có thể cùng được gọi là “deadline cứng” nhưng ý nghĩa khác nhau:

1. “Đối tác sẽ ngừng nhận giao dịch qua API cũ vào ngày D; sau mốc đó hệ thống hiện tại không hoạt động.” → Có **sự kiện phụ thuộc bên ngoài** cần xác minh và ứng phó.
2. “Tôi muốn có giao diện lịch tháng vào ngày D để báo cáo đẹp.” → Có **mục tiêu quản trị hoặc mong muốn**, không tự động là điều kiện không thể thương lượng.

Ngay cả trong tình huống thứ nhất, **ngày có thể cố định nhưng giải pháp không nhất thiết cố định**. Có thể chọn tích hợp tối thiểu, tuyến xử lý thủ công được kiểm soát, giảm phạm vi phục vụ hoặc phương án chuyển tiếp khác nếu hợp lệ và an toàn.

### 2.2. Không biến Agile thành lý do thất hứa

Nếu nhóm đã biết sớm rằng phạm vi vượt năng lực, nhưng giữ im lặng đến sát mốc rồi mới nói “Agile không cam kết”, đó là **thiếu minh bạch**, không phải thích ứng tốt. Một kế hoạch có trách nhiệm cần **đánh giá lại thường xuyên, nêu rủi ro khi còn lựa chọn và báo đúng người có quyền quyết định**.

## 3. Bốn câu hỏi mở đầu khi có deadline bắt buộc

Trước khi tăng tốc hoặc cắt tính năng, hãy làm rõ:

| Câu hỏi | Mục đích | Ví dụ workshop |
| --- | --- | --- |
| **Vì sao mốc này tồn tại?** | Phân biệt ràng buộc thực với mong muốn | Đối tác tổ chức workshop đã công bố ngày đăng ký |
| **Điều gì phải đúng vào mốc đó?** | Xác định outcome và điều kiện nghiệm thu | Học viên đủ điều kiện giữ được chỗ đúng, biết trạng thái |
| **Điều gì vẫn có thể chọn?** | Tìm biên thương lượng về phạm vi/cách triển khai | Email nhắc, lịch tháng, lọc nâng cao có thể đến sau |
| **Ai có quyền quyết định?** | Tránh tự tiện đổi hợp đồng, chất lượng hoặc ưu tiên | Product Owner, người đại diện hợp đồng, bộ phận bảo mật/vận hành theo chính sách |

Một mốc không thể dời không tự động làm mọi tính năng, mọi giả định và mọi cách triển khai trở thành bất biến.

## 4. Bảng phân loại ràng buộc: cố định, có điều kiện, có thể thương lượng

Không nên dùng hai nhãn “cứng/mềm” rồi bỏ qua sắc thái. Một ràng buộc có thể **cố định trong một phạm vi cụ thể** nhưng **có phương án tuân thủ khác**.

| Nhóm ràng buộc | Ví dụ | Câu hỏi kiểm tra | Lựa chọn khả dĩ |
| --- | --- | --- | --- |
| **Ngày bên ngoài đã xác thực** | API đối tác ngừng hỗ trợ phiên bản cũ ngày D | Có thông báo/hợp đồng chính thức? Phạm vi ảnh hưởng? | Chuyển đường tích hợp, giảm chức năng phụ, phương án cầu nối được chấp thuận |
| **Nghĩa vụ an toàn/tuân thủ** | Quyền truy cập và dữ liệu phải được bảo vệ | Tiêu chuẩn nào áp dụng? Ai xác nhận? | Giữ kiểm soát, chọn triển khai hẹp hoặc chưa mở tính năng |
| **Ngân sách tối đa** | Giới hạn chi phí nhà cung cấp và nhân lực | Ngân sách cho phạm vi nào, ai duyệt thay đổi? | Cắt phạm vi, thay phương án, trình quyết định đầu tư |
| **Năng lực nhóm** | Chỉ có một chuyên gia dữ liệu trong ba tuần | Có dự phòng, việc khác, thời gian chờ? | Giảm WIP, ưu tiên bottleneck, pairing, điều chỉnh phạm vi |
| **Phụ thuộc** | Đối tác cần hoàn tất kiểm thử hợp đồng trước mở đăng ký | Đầu vào nào, đến khi nào, có SLA? | Spike sớm, mock/contract test, chuẩn bị đường dự phòng |
| **Mong muốn sản phẩm** | Lịch tháng, bộ lọc nâng cao | Có bắt buộc để đạt outcome ban đầu? | Hoãn, chia lát cắt, loại khỏi lần phát hành đầu |
| **Mốc nội bộ** | Muốn demo toàn bộ ở Sprint Review | Là yêu cầu minh bạch hay điều kiện hợp đồng? | Demo Increment Done, nêu trung thực phần chưa xong |

### 4.1. Đừng tự nhận mình biết một nghĩa vụ pháp lý

Nếu có thời hạn theo luật, hợp đồng hoặc kiểm toán, nhóm kỹ thuật cần **xác định nguồn quy định có hiệu lực và phối hợp người có chuyên môn/thẩm quyền phù hợp**. Không nên suy rằng “pháp luật yêu cầu tất cả chức năng hoàn chỉnh ngày D” chỉ từ một lời truyền miệng.

### 4.2. Một ràng buộc có thể đổi sau quyết định chính thức

“Không thể dời” đôi khi nghĩa là **nhóm kỹ thuật không có quyền dời**, chứ không phải không ai có quyền đàm phán lại. Nếu muốn sửa hợp đồng, phạm vi pháp lý hoặc lịch công bố, hãy **đưa phương án và hệ quả tới người có thẩm quyền**; không tự ý điều chỉnh hoặc tự giả định chắc được chấp thuận.

## 5. Ghi ràng buộc thành thông tin có thể kiểm chứng

Khi deadline chỉ xuất hiện dưới dạng câu “phải xong trước ngày D”, nhóm thiếu thông tin để dự báo và quản trị rủi ro.

### 5.1. Mẫu constraint record

~~~text
TEN RANG BUOC:
NGUON: Hop dong / su kien / quy dinh / quyet dinh noi bo / phu thuoc
MO TA DIEU BAT BUOC:
NGAY / MOC / MUI GIO VA DIEU KIEN HIEU LUC:
TAI LIEU HOAC BANG CHUNG GOC:
NGUOI CO THAM QUYEN XAC NHAN:
DOI TUONG VA HE THONG BI ANH HUONG:
TIEU CHI DAT / KHONG DAT:
NHUNG GIA DINH CAN XAC MINH:
RUI RO NEU KHONG DAT:
NHUNG DIEU CO THE THUONG LUONG:
PHU THUOC / MOC KIEM TRA TRUOC:
CAC PHUONG AN GIAI QUYET:
QUYET DINH HIEN TAI / NGUOI CHIU TRACH NHIEM:
NGAY XEM LAI:
~~~

Mẫu là **công cụ học tập**, không phải artifact chính thức bắt buộc của Scrum. Mức chi tiết phải tương xứng rủi ro.

### 5.2. Ví dụ bản ghi cho sự kiện mở đăng ký

| Trường | Giá trị giả định |
| --- | --- |
| Ràng buộc | Mở nhận đăng ký vào ngày 15/12 theo lịch đối tác |
| Điều bắt buộc | Có cách đăng ký hợp lệ, kiểm soát sức chứa và trạng thái đáng tin |
| Mốc | 15/12, thời điểm cụ thể và múi giờ phải được xác nhận |
| Bằng chứng | Lịch sự kiện và cam kết đã được người có thẩm quyền xác minh |
| Phần có thể thay | Hình thức giao diện, email nhắc, bộ lọc nâng cao, thời điểm mở cho từng nhóm |
| Không được đánh đổi | Bảo vệ dữ liệu, phân quyền, tính đúng của xác nhận |
| Phụ thuộc | Thử nghiệm tải, danh sách workshop chính xác, quyền vận hành |
| Người quyết định | Product Owner với phạm vi sản phẩm; chủ cam kết/pháp lý và vận hành theo thẩm quyền |
| Mốc xem lại | Sau kiểm thử tích hợp/đánh giá rủi ro ở thời điểm đã định |

Ví dụ **không khẳng định có nghĩa vụ pháp lý cụ thể** và ngày chỉ phục vụ tình huống học tập.

## 6. Giữ cố định outcome cần có, thương lượng giải pháp và phạm vi

Khi deadline không đổi, việc đầu tiên không phải “chọn những story ngắn nhất để làm”. Cần hỏi **“người dùng hoặc bên nhận kết quả phải có khả năng gì vào đúng ngày đó?”**

### 6.1. Ví dụ phân rã một yêu cầu lớn

Stakeholder nói:

> “Ngày 15/12 phải có đầy đủ hệ thống workshop: đăng ký, email, bộ lọc, lịch tháng, hủy, báo cáo, dashboard và tích hợp ngoài.”

Nhóm làm rõ:

| Khả năng | Có cần cho lần mở đăng ký an toàn? | Lý do hoặc điều kiện |
| --- | --- | --- |
| Xem workshop có chỗ và điều kiện tham dự | **Có** | Người học phải chọn đúng chương trình phù hợp |
| Đăng ký đúng một chỗ và nhận trạng thái rõ | **Có** | Là hành vi cốt lõi, cần tính nhất quán và phân quyền |
| Xem lại đăng ký của chính mình | **Thường cần** | Giảm trạng thái mơ hồ, hỗ trợ đối soát |
| Cách hỗ trợ khi lỗi/đăng ký thất bại | **Có ở mức phù hợp** | Có đường xử lý người dùng bị ảnh hưởng |
| Email nhắc trước ngày học | Có thể hoãn | Chỉ bắt buộc nếu cam kết/điều kiện sản phẩm yêu cầu |
| Lịch tháng nhiều lớp | Có thể hoãn | Không phải điều kiện để đăng ký hợp lệ nếu giao diện đơn giản đủ dùng |
| Bộ lọc nâng cao | Có thể hoãn | Danh sách phù hợp có thể thay bằng cách đơn giản |
| Dashboard báo cáo đầy đủ | Có thể chia | Báo cáo bắt buộc cần xác minh; phần phân tích nâng cao có thể đến sau |
| Cơ chế hủy chỗ | Phải làm rõ | Có thể là nghĩa vụ nghiệp vụ; không mặc định bỏ được |

**Các nhãn là giả định của ví dụ**, không phải quy tắc cố định cho mọi sản phẩm. Nếu hợp đồng yêu cầu email hoặc chính sách bắt buộc có hủy chỗ ngay khi mở đăng ký, các phần ấy phải được đưa vào phạm vi bắt buộc.

### 6.2. Minimum Viable Scope khác “làm thiếu rồi gọi MVP”

**Phạm vi tối thiểu khả thi** trong thời hạn bắt buộc phải:

1. Tạo ra hành vi có giá trị hoặc đáp ứng nghĩa vụ.
2. Đáp ứng **điều kiện chấp nhận và chất lượng** tương ứng.
3. Có thể kiểm chứng/tích hợp và vận hành với giới hạn rõ.
4. Có cách xử lý trường hợp lỗi hoặc ngoại lệ cần thiết.
5. Không dựa trên một chức năng phụ **chưa sẵn sàng** mà không có phương án được chấp thuận.

**Minimum** nói về số khả năng được chọn, **không nói được phép giảm mức an toàn tối thiểu**.

### 6.3. Giữ một lõi hoàn chỉnh thay vì nhiều mảnh dở

Một hệ thống có UI đăng ký, API dở dang và email đẹp nhưng database chưa kiểm chứng **không phải một lát cắt giá trị hoàn chỉnh**. Một luồng “xem còn chỗ → giữ một chỗ → xác nhận đúng → xem lại trạng thái” đơn giản, có test và vận hành phù hợp, thường đáng tin hơn.

## 7. Phân biệt “must-have”, “should-have”, “could-have” và “won't-now”

Một kỹ thuật trao đổi phạm vi là chia hạng mục theo mức cần thiết cho **một mốc cụ thể**. Ví dụ cách gọi gần với MoSCoW:

| Nhóm | Ý nghĩa trong một mốc cụ thể | Ví dụ workshop |
| --- | --- | --- |
| **Must** | Không có thì không đạt outcome/nghĩa vụ hoặc không thể vận hành an toàn | Xác nhận chỗ đúng; quyền truy cập; trạng thái có thể đối soát |
| **Should** | Giá trị cao nhưng có phương án tạm/hoãn được chấp thuận | Email xác nhận nếu trạng thái đã được xem rõ trong ứng dụng và không có ràng buộc khác |
| **Could** | Có ích khi còn năng lực, không làm hại phần bắt buộc | Bộ lọc nâng cao, tiện ích chia sẻ |
| **Won't now** | Không đưa vào lần phát hành đang xét; có thể xem lại | Lịch tháng phức tạp, cá nhân hóa sâu |

### 7.1. “Must” phải có lý do

Nếu mọi hạng mục đều được gọi Must thì **không còn khả năng ưu tiên**. Với mỗi Must, hỏi:

- Nếu thiếu, **outcome bắt buộc** nào bị phá?
- Có yêu cầu pháp lý/hợp đồng hoặc rủi ro cụ thể nào?
- Có phương án tối thiểu khác vẫn đáp ứng điều kiện không?
- Ai có thẩm quyền xác nhận Must?
- Nếu không thể hoàn tất, **kế hoạch thay thế** là gì?

### 7.2. Ưu tiên không phải cuộc bỏ phiếu đơn giản

Product Owner chịu trách nhiệm tối đa hóa giá trị và thứ tự Product Backlog trong Scrum. Nhưng với nghĩa vụ tuân thủ, quyền vận hành và cam kết ngoài phạm vi Product Owner, **các bên có thẩm quyền liên quan phải tham gia**. Không bỏ yêu cầu bảo mật chỉ vì số phiếu chọn Could nhiều hơn.

## 8. Ba đòn bẩy hợp lệ khi thời gian thực sự cố định

Khi thời hạn được giữ, nhóm cần lựa chọn trong những biến có thể đổi mà **không giả vờ chất lượng là phần tùy chọn**.

### 8.1. Đòn bẩy 1 — Phạm vi

- Hoãn chức năng ít cần thiết.
- Giảm số đường đi nghiệp vụ chỉ khi vẫn hợp lệ.
- Hạn chế số biến thể trải nghiệm ở lần phát hành đầu.
- Thay chức năng đầy đủ bằng quy trình đơn giản hơn **được chấp thuận và kiểm chứng**.
- Chia giai đoạn mà người dùng vẫn nhận được một kết quả hoàn chỉnh.

### 8.2. Đòn bẩy 2 — Phương án thực hiện

- Chọn giải pháp kỹ thuật đơn giản hơn trong phạm vi chấp nhận được.
- Tích hợp/thử nghiệm sớm để giảm rủi ro.
- Dùng contract test để phát hiện sai lệch phụ thuộc trước môi trường thật, nhưng **không tuyên bố đã kiểm chứng tích hợp thật** nếu chưa có.
- Tăng phối hợp trên nút thắt: review sớm, pairing, cùng giải quyết blocker.
- Tự động hóa thao tác lặp để giữ nhịp phản hồi.

### 8.3. Đòn bẩy 3 — Kế hoạch tiếp cận người dùng

- Mở cho một nhóm hợp lệ trước rồi mở rộng khi guardrail đạt.
- Dùng feature flag hoặc release theo pha khi phù hợp.
- Chuẩn bị quy trình hỗ trợ/giảm tải trong giai đoạn đầu.
- Thỏa thuận thay đổi đối tượng hoặc phạm vi phục vụ **nếu cam kết cho phép**.
- Chuẩn bị hướng thông báo trung thực nếu một chức năng chưa sẵn sàng.

### 8.4. Những đòn bẩy không được dùng như “mẹo”

- Bỏ kiểm thử dữ liệu/phân quyền quan trọng.
- Đánh dấu Done cho PBI chưa đạt Definition of Done.
- Sửa số liệu tiến độ hoặc che lỗi còn mở.
- Bắt mọi người làm thêm giờ kéo dài như giả định năng lực cố định.
- Triển khai code chưa được kiểm chứng rồi hy vọng production sẽ tìm lỗi.
- Tự ý đổi nghĩa vụ hợp đồng hoặc quyền của người dùng.
- Tăng số người ở phút cuối mà không tính chi phí phối hợp và onboarding.

## 9. Giữ chất lượng không đồng nghĩa cố định mọi chi tiết kỹ thuật

**Chất lượng** gồm những đặc tính mà Increment phải có để đáng tin và phù hợp mục đích. Một phần là **điều kiện bắt buộc**; phần khác có thể được điều chỉnh theo rủi ro và sử dụng thực tế.

| Thành phần | Điều cần bảo vệ | Điều có thể thiết kế khác |
| --- | --- | --- |
| Tính đúng của đăng ký | Không xác nhận vượt sức chứa hoặc tạo dữ liệu mâu thuẫn | Cơ chế giao dịch/khóa/ràng buộc sau khi đánh giá phù hợp |
| Phân quyền | Không xem/sửa dữ liệu người khác trái phép | Cách tổ chức module hoặc framework xác thực |
| Phản hồi người dùng | Trạng thái đúng, có thể hiểu | Giao diện tối giản thay lịch tháng phong phú |
| Khả năng vận hành | Phát hiện lỗi quan trọng, ứng phó và khôi phục | Chọn mức tự động hóa/phân tầng theo rủi ro |
| Kiểm thử | Bằng chứng đủ cho hành vi rủi ro cao | Kết hợp test nhanh, integration và thẩm định theo loại lỗi |
| Bảo trì | Không tạo rủi ro không kiểm soát được cho thay đổi tiếp | Có thể hoãn tối ưu kiến trúc không cần thiết |

### 9.1. “Bỏ polish” khác “bỏ an toàn”

Nhóm có thể bỏ animation, tối ưu giao diện không cốt lõi hoặc giảm số biến thể thiết kế. Nhưng không nên gọi việc bỏ audit, kiểm soát quyền hoặc cơ chế chống ghi trùng là “cắt polish”.

### 9.2. Không dùng ngưỡng kiểm thử tùy tiện để khẳng định an toàn

“Coverage 90%” không tự chứng minh giao dịch đồng thời đúng; “pipeline xanh” chỉ cho biết **những bước đã cấu hình** đạt. Nhóm cần dựa vào **rủi ro sản phẩm và bằng chứng kiểm chứng thích hợp**.

## 10. Backlog là công cụ ra quyết định phạm vi

**Product Backlog** là danh sách có thứ tự những gì cần cải thiện sản phẩm. Khi có hạn bắt buộc, nhóm nên làm rõ từng hạng mục liên hệ thế nào tới outcome, rủi ro và phụ thuộc.

### 10.1. Bảng ra quyết định Product Backlog

| PBI | Outcome/nghĩa vụ hỗ trợ | Rủi ro/phụ thuộc | Trạng thái bằng chứng | Quyết định mốc đầu |
| --- | --- | --- | --- | --- |
| Xem workshop phù hợp | Người học chọn đúng buổi | Dữ liệu lịch/sức chứa | Đã thử luồng cơ bản | Giữ |
| Đăng ký chỗ cuối | Giao dịch cốt lõi | Đồng thời, dữ liệu, quyền | Test đồng thời chưa đạt | Giữ và ưu tiên kiểm chứng |
| Xem đăng ký của mình | Trạng thái rõ | Quyền xem dữ liệu | API đang review | Giữ theo phạm vi tối thiểu |
| Email nhắc lịch | Tiện ích sau đăng ký | Dịch vụ email đối tác | Chưa có contract test | Hoãn nếu không là nghĩa vụ |
| Bộ lọc nâng cao | Tiện sử dụng | Tương tác UI | Chưa có bằng chứng thiết yếu | Hoãn |
| Xuất báo cáo bắt buộc | Phục vụ cam kết báo cáo | Cần xác minh định dạng/thời điểm | Chưa làm rõ yêu cầu | **Làm rõ ngay** trước khi quyết định |

### 10.2. Không ưu tiên dựa trên điểm số máy móc

Một ma trận giá trị/chi phí có thể hỗ trợ trao đổi, nhưng **điều kiện pháp lý và an toàn không nên bị loại chỉ vì “giá trị kinh doanh” của chúng khó định lượng**. Những ràng buộc bắt buộc phải được nêu rõ ở tầng quyết định trước khi tối ưu thứ tự.

### 10.3. “Defer” cần nghĩa thực tế

Hoãn một hạng mục có nghĩa:

- Không đưa nó vào cam kết lần giao đang xét.
- Ghi lý do, giả định và ảnh hưởng đối với người dùng.
- Nêu ai được quyền quyết định thứ tự làm tiếp.
- Cập nhật thông tin đối với stakeholder có liên quan.
- Không để phụ thuộc ẩn của hạng mục Must trông như đã được giải quyết.

Không nên gọi một phần **bắt buộc về an toàn** là “sẽ làm ở Sprint sau” nếu điều đó khiến lần phát hành này không đủ điều kiện.

## 11. Chia lát cắt dọc để đạt giá trị sớm

Một deadline cứng càng làm lộ nhược điểm của việc xây theo các đợt **“xong toàn bộ backend → xong UI → cuối cùng test”**.

### 11.1. Ví dụ chia thành lát cắt có thể kiểm chứng

| Lát cắt | Giá trị hoàn chỉnh | Kiểm chứng cần thiết |
| --- | --- | --- |
| A. Xem danh sách workshop phù hợp | Người học thấy buổi có điều kiện tham dự và chỗ trống | Dữ liệu, hiển thị và quyền phù hợp |
| B. Đăng ký workshop còn chỗ | Một yêu cầu hợp lệ được xác nhận đúng | Quy tắc, giao dịch, đồng thời, lỗi và trạng thái |
| C. Xem đăng ký của mình | Người học xác minh kết quả | Phân quyền và tính nhất quán dữ liệu |
| D. Hủy theo chính sách | Người học giải phóng chỗ đúng cách | Thời hạn hủy, trạng thái, quyền và dữ liệu |
| E. Nhắc lịch | Người học ít bỏ lỡ | Contract email, trạng thái gửi và quyền dữ liệu |

Nếu mốc đầu chỉ cần A+B+C, nhóm có thể đạt một **luồng từ đầu tới cuối**, còn D/E được quyết định theo nghĩa vụ và ưu tiên thật.

### 11.2. Task kỹ thuật không đồng nghĩa Increment

Các task “tạo bảng database”, “viết controller” và “dựng giao diện” có thể cần thiết, nhưng **từng task đơn lẻ chưa chắc tạo giá trị sử dụng được**. Một lát cắt dọc phải được **tích hợp và đáp ứng tiêu chuẩn hoàn tất**.

### 11.3. Kết nối với feedback sớm

Khi A có bản chạy được, nhóm có thể kiểm tra người học hiểu điều kiện workshop. Khi B sẵn sàng, có thể thực hiện integration test và thẩm định luồng giao dịch. Khi C xong, có thể thử hành trình người dùng. **Không phải chờ tất cả Could đều hoàn tất mới nhận phản hồi**.

## 12. Scrum: giữ Sprint Goal, thương lượng phạm vi Sprint Backlog

Trong Scrum, **Product Goal** là mục tiêu dài hạn của sản phẩm; **Sprint Goal** là một mục tiêu đơn nhất cho Sprint; **Sprint Backlog** gồm Sprint Goal, các PBI được chọn và kế hoạch thực hiện do Developers quản lý.

### 12.1. Điều gì có thể đổi trong Sprint?

Scrum Guide 2020 quy định trong Sprint:

- **Không có thay đổi làm nguy hại Sprint Goal.**
- **Chất lượng không được giảm.**
- Product Backlog được **refine khi cần**.
- Phạm vi có thể được **làm rõ và thương lượng với Product Owner** khi nhóm học được thêm.

Vì vậy, nếu một PBI phụ không còn vừa năng lực, Developers có thể trao đổi Product Owner để điều chỉnh phạm vi mà **vẫn giữ Sprint Goal và DoD**. Không nên bí mật xóa một tiêu chí nghiệm thu cần thiết để giữ biểu đồ burndown đẹp.

### 12.2. Sprint Goal không phải danh sách toàn bộ tính năng

Ví dụ Sprint Goal:

> “Học viên đủ điều kiện có thể đăng ký workshop còn chỗ và nhận trạng thái đáng tin.”

Các PBI email nhắc hoặc lịch tháng có thể là tùy chọn đối với Sprint Goal **nếu đã xác minh không có nghĩa vụ khác ràng buộc**. Nếu phát hiện luồng đăng ký chỉ đúng khi có cơ chế hủy hoặc báo cáo nào đó, nhóm cần làm rõ điều kiện trước khi cắt.

### 12.3. Khi Sprint Goal trở nên lỗi thời

**Hủy Sprint** trong Scrum chỉ khi **Sprint Goal trở nên lỗi thời**; **chỉ Product Owner có thẩm quyền hủy Sprint**. Deadline đến gần hoặc một PBI chưa hoàn tất **không tự động là lý do hủy Sprint**. Nếu vẫn có thể đạt Sprint Goal bằng cách thương lượng phạm vi trong điều kiện chất lượng giữ nguyên, nhóm nên ưu tiên thích ứng kế hoạch.

### 12.4. Definition of Done không phải nút giảm độ khó

Nếu PBI chưa đạt Definition of Done, nó **không được tính là Increment Done**. Khi hết Sprint, phần chưa hoàn tất được trả về Product Backlog để xem xét lại; không tự động kéo Sprint dài thêm hoặc mặc định phải vào Sprint sau.

Deadline của một release bên ngoài **không làm mất ý nghĩa của DoD**; nếu cần phương án tạm, nó vẫn phải đáp ứng tiêu chuẩn chất lượng và nghĩa vụ tương ứng với phạm vi đã thỏa thuận.

## 13. Kanban: nhìn năng lực dòng công việc thay vì số người “bận”

Một nhóm có thể có nhiều Developers đang viết mã, nhưng mọi PBI đều chờ một người review dữ liệu hoặc môi trường test. **Tăng số việc đang làm không làm tăng khả năng hoàn tất**.

### 13.1. Bảng ví dụ

| Ready | Developing | Waiting for review | Testing/integration | Done |
| --- | --- | --- | --- | --- |
| Bộ lọc nâng cao | Đăng ký chỗ cuối | Xem đăng ký của mình | Danh sách workshop | Thông tin workshop |

Nếu deadline còn ngắn, bảng phải làm hiện rõ **phần nào đang chờ**, không chỉ số thẻ được mở.

### 13.2. Bốn chỉ số có ích

| Chỉ số | Dùng để hiểu điều gì? | Cách tránh lạm dụng |
| --- | --- | --- |
| **WIP** | Có quá nhiều item mở cùng lúc không? | Không lấy WIP từng người làm bảng năng suất |
| **Throughput** | Hệ thống thật sự hoàn tất bao nhiêu item theo chính sách Done? | Không đếm task “dev xong” như Increment |
| **Work item age** | Item nào đang già đi trước khi Done? | Hỏi về blocker và hỗ trợ, không quy chậm trễ cho tác giả |
| **Cycle time** | Item hoàn tất mất bao lâu trong luồng đã định nghĩa? | Nhìn phân phối/loại việc, không dùng một trung bình như cam kết |

### 13.3. Một giới hạn WIP minh họa

Giả sử nhóm thử giới hạn **3 PBI đang phát triển** và **2 PBI chờ/đang review**. Khi vùng review đầy, Developers có thể hỗ trợ làm rõ test, chuẩn bị môi trường hoặc cùng giải quyết một blocker thay vì mở một PBI Could khác.

Các con số **chỉ minh họa**, không phải mức WIP chuẩn cho mọi nhóm. Quy tắc phải được xem lại theo dữ liệu và tính chất công việc.

## 14. Dự báo: nói về khoảng khả thi, không hứa ngày giả

Khi deadline cố định, dự báo giúp trả lời câu hỏi:

> “Với năng lực, dữ liệu và điều kiện hiện tại, chúng ta có thể hoàn tất **phần Must** tới mức nào, với những bất định nào?”

Không nên bắt đầu bằng việc cộng mọi số ước lượng rồi buộc người thực hiện làm đủ.

### 14.1. Dữ liệu hữu ích

- Throughput/cycle time của **các PBI tương tự và cùng chính sách Done**.
- Năng lực thực tế: nghỉ phép, on-call, sự cố, công việc hỗ trợ và phụ thuộc.
- Kích thước, mức mới lạ và rủi ro của những PBI còn lại.
- Thời gian cần cho review, kiểm thử tích hợp, bảo mật và vận hành.
- Sự sẵn sàng của đối tác và môi trường kiểm chứng.
- Lịch sử thay đổi yêu cầu và tỷ lệ phải làm lại.

### 14.2. Ví dụ năng lực theo dữ liệu

Giả sử trong sáu tuần gần đây, nhóm hoàn tất số PBI tương đối đồng đều:

| Tuần | PBI đạt Done |
| --- | ---: |
| 1 | 4 |
| 2 | 5 |
| 3 | 3 |
| 4 | 4 |
| 5 | 6 |
| 6 | 2 |

Trung bình:

\[
\bar{t}=\frac{4+5+3+4+6+2}{6}=4\ \text{PBI/tuần}.
\]

Nếu còn ba tuần, phép tính sơ bộ **12 PBI** có thể tạo một điểm thảo luận. Nhưng **không được suy ra chắc chắn sẽ giao 12 PBI**: những PBI còn lại có thể lớn hơn, phụ thuộc hơn, và tuần thứ sáu chỉ đạt hai item có thể phản ánh rủi ro đang tiếp diễn.

### 14.3. Tách Must và Could trong dự báo

Giả sử còn:

- 6 PBI Must, trong đó 2 PBI có rủi ro dữ liệu cao.
- 4 PBI Should.
- 8 PBI Could.

Phép tính **6 + 4 + 8 = 18 PBI** so với mức trung bình sơ bộ 12 đã chỉ ra toàn bộ phạm vi khó phù hợp nếu độ lớn tương tự. Nhưng ngay cả **6 Must** cũng chưa chắc khả thi nếu rủi ro tích hợp lớn. Cần **đánh giá chi tiết phần bắt buộc, thực hiện thử nghiệm rủi ro sớm, cập nhật dự báo**.

### 14.4. Cập nhật dự báo khi có sự thật mới

Nếu một integration test phát hiện lỗi đồng thời, dự báo phải **thay đổi minh bạch**. Không nên giữ ngày nội bộ và vẫn công bố “đúng tiến độ” bằng cách đổi nhãn Done trước khi kiểm chứng.

### 14.5. Không so sánh dự báo với năng suất cá nhân

Throughput là đặc tính của **luồng công việc**, không phải “mỗi Developer phải đóng bốn PBI”. Năng lực của nhóm phụ thuộc phối hợp, hàng đợi, review, test và rủi ro, không thể quy đổi đều cho mỗi người.

## 15. Dự báo xác suất và phân phối: khi nào hữu ích?

Một đường trung bình có thể che biến động. Nếu dự án có dữ liệu phù hợp, nhóm có thể dùng **mô phỏng dự báo theo throughput lịch sử** để xem phân phối kết quả khả dĩ.

### 15.1. Cách mô tả kết quả có trách nhiệm

Thay vì:

> “Chắc chắn hoàn tất 10 PBI vào ngày D.”

Hãy nói:

> “Dựa trên dữ liệu lịch sử của nhóm PBI tương tự và những giả định đang giữ, có các kịch bản hoàn tất khác nhau. Mức khả thi của phạm vi Must cần được xác nhận lại sau kiểm thử tích hợp ngày X; những phụ thuộc còn mở có thể làm dự báo thay đổi.”

Nếu đưa ra phần trăm xác suất, cần giải thích **phương pháp, dữ liệu, giả định và giới hạn**. Không tạo con số **“85% tự tin”** từ trực giác rồi trình bày như kết quả thống kê.

### 15.2. Khi không nên làm mô phỏng phức tạp

- Mẫu lịch sử quá nhỏ hoặc điều kiện hiện tại rất khác.
- PBI còn lại có tính chất khác hẳn những item đã làm.
- Ranh giới Done thay đổi giữa các chu kỳ.
- Phụ thuộc bên ngoài quyết định gần hết tiến độ.
- Người ra quyết định cần biết trước một rủi ro Must rất rõ.

Trong các trường hợp này, **bản đồ phụ thuộc, lát cắt thử sớm và dự báo theo kịch bản có thể hữu ích hơn một đồ thị xác suất đẹp nhưng thiếu căn cứ**.

## 16. Nhận diện và xử lý phụ thuộc trước khi thành đường găng

Deadline cứng thường bị đe dọa bởi công việc **không nằm hoàn toàn trong tay nhóm**.

| Phụ thuộc | Rủi ro | Hành động sớm |
| --- | --- | --- |
| API đối tác | Contract khác dự kiến, token/test account đến muộn | Thử contract, đặt mốc tích hợp, kênh escalation |
| Database/schema | Migration cần kiểm chứng dữ liệu hoặc downtime | Thử trên dữ liệu phù hợp, xác định rollback và người phê duyệt |
| Bảo mật/quyền | Chưa xong review cho dữ liệu người học | Mời chuyên môn từ đầu, chốt tiêu chí và lịch review |
| Hạ tầng/CI | Môi trường test không ổn định | Xử lý độ tin cậy, chuẩn bị fixture/runner |
| Thiết kế nghiệp vụ | Chưa rõ trường hợp hủy/đăng ký trùng | Làm rõ bằng ví dụ trước khi code |
| Người review chuyên sâu | Chỉ một người biết cơ chế dữ liệu | Pairing, review sớm, giảm WIP, dự phòng có kỹ năng |
| Kênh hỗ trợ/vận hành | Chưa có người xử lý khi mở đăng ký | Runbook, quyền, lịch trực và đường liên hệ |

### 16.1. Không đợi “xong phần mình”

Nếu một phụ thuộc phải có trước ngày D, nhóm nên **thử hoặc xác nhận nó sớm**, ngay cả khi toàn bộ tính năng chưa được xây. Ví dụ gọi endpoint đối tác bằng một hợp đồng tối thiểu trong môi trường thử trước khi viết cả module.

### 16.2. Mock không thay thế bằng chứng tích hợp thật

Mock hoặc stub có thể giảm phụ thuộc khi phát triển, nhưng chỉ kiểm chứng **giả định của nhóm**. Trước khi gọi là hoàn tất theo chất lượng cần thiết, phải thực hiện những kiểm chứng thật phù hợp và ghi rõ giới hạn nếu chưa thực hiện được.

### 16.3. Có phương án dự phòng hợp lệ

Nếu đối tác không kịp cung cấp API:

- Phần nào có thể chạy độc lập?
- Có cách tiếp nhận đăng ký tạm thời an toàn, được phép và có khả năng đối soát không?
- Có nên giới hạn nhóm người dùng hoặc tạm chưa mở chức năng phụ thuộc?
- Ai chấp thuận thay đổi cam kết hoặc thông báo cho khách hàng?

**Không tự dựng một đường xử lý thủ công thiếu kiểm soát dữ liệu chỉ để tuyên bố đã kịp deadline.**

## 17. Vòng ra quyết định khi deadline và phạm vi xung đột

Một flow thực dụng giúp nhóm không quay vòng tranh luận “cần thêm người” hay “bỏ QA”.

~~~mermaid
flowchart TD
    A["Có yêu cầu hoàn thành trước mốc D"] --> B["Xác minh nguồn và quyền quyết định"]
    B --> C{"Mốc và outcome thực sự bắt buộc?"}
    C -->|"Chưa rõ"| D["Làm rõ cam kết, tiêu chí đạt, rủi ro"]
    D --> B
    C -->|"Có"| E["Tách Must/Should/Could và chất lượng tối thiểu"]
    E --> F["Kiểm tra năng lực, phụ thuộc, dữ liệu, môi trường"]
    F --> G{"Must có đường khả thi?"}
    G -->|"Có, còn rủi ro"| H["Chọn lát cắt, giảm WIP, kiểm chứng sớm"]
    H --> I["Đo tiến độ tới Done và guardrail"]
    I --> J{"Bằng chứng có đổi?"}
    J -->|"Có"| F
    J -->|"Không"| K["Release có kiểm soát theo điều kiện"]
    G -->|"Chưa"| L["Đề xuất phương án: giảm phạm vi, thay giải pháp, mở theo pha, đàm phán"]
    L --> M["Đưa người có thẩm quyền quyết định"]
    M --> N{"Phương án được chấp thuận?"}
    N -->|"Có"| H
    N -->|"Không"| O["Báo rủi ro không đáp ứng; chọn cách bảo vệ người dùng/tuân thủ"]
~~~

### 17.1. “Không khả thi” là dữ kiện cần quản trị

Nếu những điều kiện bắt buộc **không thể hoàn tất an toàn trong thời gian và ngân sách còn lại**, nhóm phải nói rõ điều đó sớm. Không thể giải bài toán bằng việc yêu cầu **vừa giữ mọi scope, vừa giữ deadline, vừa giữ chất lượng** khi năng lực và phụ thuộc không cho phép.

### 17.2. Người kỹ thuật không tự tuyên bố đã thương lượng thành công

Một đề xuất như “chỉ mở đăng ký cho 100 học viên” có thể phù hợp kỹ thuật nhưng **chưa chắc đáp ứng hợp đồng hoặc nghĩa vụ đối với người dùng**. Nó phải được đánh giá và chấp thuận bởi bên có quyền.

## 18. Quản trị quyết định: rõ ai chịu trách nhiệm và ai có quyền

Khi có thời hạn bắt buộc, một quyết định có thể chạm tới **giá trị sản phẩm, cam kết thương mại, rủi ro an toàn, khả năng vận hành và chi phí**. Nếu không làm rõ ranh giới quyền, nhóm dễ mắc hai thái cực:

- **Tự ý quyết:** Developers cắt một điều kiện hợp đồng hoặc bật tính năng khi chưa đủ kiểm chứng.
- **Chờ vô hạn:** Mọi lựa chọn nhỏ đều phải qua nhiều cấp phê duyệt dù nằm trong quyền tự quản của nhóm.

### 18.1. Bản đồ trách nhiệm theo loại quyết định

| Quyết định | Người/chức năng thường chịu trách nhiệm chính | Người cần phối hợp |
| --- | --- | --- |
| Thứ tự Product Backlog, tối đa hóa giá trị | **Product Owner** trong Scrum | Developers, stakeholder, người hiểu nghiệp vụ |
| Kế hoạch kỹ thuật, cách tạo Increment và dự báo năng lực | **Developers** trong Scrum | Product Owner và các chuyên môn cần thiết |
| Làm rõ Sprint Goal và điều chỉnh phạm vi trong Sprint | **Scrum Team**, với thương lượng scope giữa Developers và Product Owner | Stakeholder khi có tác động quan trọng |
| Xác minh và thay đổi cam kết/hợp đồng | Chủ sở hữu cam kết/người được ủy quyền theo tổ chức | Product Owner, pháp lý/thương mại, khách hàng |
| Chấp nhận rủi ro bảo mật hoặc tuân thủ | Chủ thể có thẩm quyền theo chính sách | Bảo mật, quản trị rủi ro, kỹ thuật, sản phẩm |
| Quyết định go/no-go phát hành | Vai trò hoặc hội đồng được ủy quyền tùy tổ chức/rủi ro | Product, kỹ thuật, bảo mật, vận hành |
| Ứng phó sự cố khẩn | Incident commander/đầu mối được trao quyền theo quy trình | Vận hành, kỹ thuật, bảo mật, hỗ trợ |
| Cải thiện hiệu quả áp dụng Scrum | Scrum Team; Scrum Master chịu trách nhiệm về hiệu quả của Scrum Team | Các bộ phận gây hoặc tháo trở ngại |

**Bảng là mẫu phân quyền tham khảo, không phải RACI cố định của Scrum.** Một tổ chức có thể kết hợp trách nhiệm, nhưng quyền ra quyết định về nghĩa vụ bên ngoài hoặc an toàn phải được thiết lập rõ.

### 18.2. Product Owner không phải người bỏ mọi kiểm soát

Product Owner có quyền ưu tiên giá trị và quản lý Product Backlog. Điều đó không tự cấp quyền **bỏ quy định bảo mật, thay hợp đồng hoặc cho phép deploy production ngoài chính sách**.

Ngược lại, một quy trình phê duyệt an toàn cũng không nên biến Product Owner thành người chỉ nhận yêu cầu bị chia sẵn và không thể đưa ra lựa chọn giá trị.

### 18.3. Người quyết định cần được cung cấp phương án, không chỉ vấn đề

Thay vì gửi:

> “Chúng tôi không thể làm kịp. Xin chỉ đạo.”

Hãy gửi:

> “Mốc mở đăng ký ngày D vẫn giữ theo cam kết. Hiện A+B+C là đường tối thiểu đạt outcome; D và E có thể hoãn nếu bên chủ cam kết xác nhận. Rủi ro chỗ cuối đã được phát hiện trong test và cần xử lý trước release. Chúng tôi đề nghị phương án 1, kèm điều kiện quyết định trước ngày X; nếu không có phương án được chấp thuận, không thể xác nhận hệ thống đủ điều kiện mở toàn bộ.”

**Dữ liệu, phương án, trade-off và hạn quyết định** giúp quản trị thực sự giảm rủi ro thay vì chỉ đẩy trách nhiệm.

## 19. Mẫu trao đổi thương lượng phạm vi với stakeholder

Một cuộc thương lượng có ích không bắt đầu bằng “bỏ cái gì?” mà bằng **giữ outcome, nêu ràng buộc và lựa chọn cụ thể**.

### 19.1. Kịch bản hội thoại

> **Stakeholder:** “Ngày 15/12 bắt buộc phải có cả lịch tháng, email, hủy và đăng ký.”
>
> **Product Owner:** “Tôi muốn xác nhận điều kiện thành công của ngày đó. Cam kết bên ngoài là học viên có thể đăng ký hợp lệ, hay hợp đồng đã liệt kê mọi chức năng vừa nêu?”
>
> **Người quản lý cam kết:** “Hợp đồng yêu cầu cổng đăng ký, trạng thái xác nhận và quy trình hỗ trợ; chưa bắt buộc lịch tháng.”
>
> **Developers:** “Luồng giữ chỗ và quyền đang trong kiểm thử tích hợp. Theo năng lực hiện tại, lịch tháng sẽ cạnh tranh với việc hoàn tất luồng cốt lõi. Chúng tôi có thể giao giao diện danh sách đơn giản đã kiểm chứng và tạm hoãn lịch tháng.”
>
> **Stakeholder:** “Nhưng email xác nhận giúp người học yên tâm.”
>
> **Product Owner:** “Đúng, đó là giá trị cao. Ta có thể chọn thông báo trong ứng dụng và mục xem lại trạng thái cho mốc đầu, đồng thời xác minh với bên cam kết xem email có phải điều kiện bắt buộc. Nếu bắt buộc, ta sẽ điều chỉnh phần khác, không cắt kiểm thử dữ liệu.”
>
> **Người quản lý cam kết:** “Tôi sẽ xác nhận bằng văn bản trước ngày X.”

Cuộc trao đổi có **vấn đề, bằng chứng, quyền xác nhận và thời điểm trả lời**, không phải “Developer phản đối yêu cầu” hay “stakeholder ép người khác làm việc nhiều hơn”.

### 19.2. Các câu cần tránh và câu thay thế

| Câu dễ gây tranh luận | Cách nói giúp ra quyết định |
| --- | --- |
| “Agile nên chúng tôi không cam kết.” | “Chúng tôi giữ cam kết đã xác nhận và sẽ cập nhật dự báo dựa trên bằng chứng cùng các phương án phạm vi.” |
| “Tất cả đều quan trọng như nhau.” | “Hãy xác định điều nào làm mốc này thất bại nếu thiếu và điều nào có thể triển khai sau.” |
| “Thêm người thì chắc chắn nhanh.” | “Nút thắt nằm ở đâu, người mới có thể giúp trong thời gian còn lại hay cần onboarding?” |
| “QA cản tiến độ.” | “Kiểm thử đã phát hiện rủi ro nào? Làm sao đưa kiểm chứng sớm hơn?” |
| “Không kịp thì cứ release rồi sửa.” | “Rủi ro nào được phép tồn dư, ai có quyền chấp nhận, điều gì không thể release khi chưa đáp ứng?” |
| “Deadline này vô lý.” | “Nguồn của mốc, điều kiện thành công và phương án có thể thương lượng là gì?” |

### 19.3. Không nhầm đàm phán với làm mờ thông tin

Một quyết định hoãn email chỉ hợp lệ khi **đã ghi rõ ai bị ảnh hưởng, có phương án thông báo trạng thái nào và người có thẩm quyền đã đồng ý**. Đừng làm một scope nhỏ hơn trên giấy nhưng để stakeholder nghĩ vẫn đang nhận toàn bộ hệ thống.

## 20. Bảng so sánh phương án: trade-off có bằng chứng

Khi khó quyết định, hãy đưa ít nhất hai hoặc ba phương án có **tác động tới giá trị, chất lượng, chi phí và rủi ro**.

| Phương án giả định | Nội dung tại mốc D | Lợi ích | Rủi ro/giới hạn | Điều kiện để chọn |
| --- | --- | --- | --- | --- |
| **A. Lát cắt cốt lõi** | Xem workshop, đăng ký đúng chỗ, xem trạng thái, hỗ trợ tối thiểu | Giữ outcome và tập trung chất lượng | Thiếu email/lịch nâng cao | Cam kết cho phép, test và vận hành đạt |
| **B. Cốt lõi + email** | A và thông báo email đã kiểm chứng | Trải nghiệm đầy đủ hơn | Phụ thuộc dịch vụ email, rủi ro timeout/lặp gửi | Có đủ thời gian tích hợp và xử lý lỗi |
| **C. Mở theo pha** | Nhóm đầu hợp lệ có thể dùng luồng cốt lõi, mở rộng khi guardrail đạt | Giới hạn tác động nếu có vấn đề chưa lường trước | Có thể chưa đáp ứng mốc “mở cho toàn bộ” | Được bên có quyền chấp thuận và đáp ứng nghĩa vụ |
| **D. Thỏa thuận lại mốc/phạm vi** | Điều chỉnh cam kết chính thức | Tránh giao thiếu an toàn | Ảnh hưởng thương mại, danh tiếng, kế hoạch đối tác | Người có thẩm quyền đàm phán và phê duyệt |
| **E. Không mở cho người dùng khi chưa an toàn** | Ngừng/hoãn release rủi ro | Bảo vệ người dùng và dữ liệu | Chưa đạt ngày mục tiêu; cần xử lý hệ quả | Khi không có phương án release đáp ứng điều kiện tối thiểu |

**Không tồn tại phương án A luôn đúng.** Nếu nghĩa vụ bắt buộc yêu cầu email thì A không đủ; nếu hệ thống chưa bảo đảm không ghi vượt sức chứa thì cả A/B/C chưa thể coi là an toàn.

### 20.1. Mỗi phương án cần điểm quyết định

Ví dụ:

- Ngày X: Bên hợp đồng xác nhận email bắt buộc hay không.
- Ngày Y: Chạy integration test và kiểm tra dữ liệu.
- Ngày Z: Quyết định có mở rộng hay kích hoạt phương án khác.

Các mốc X/Y/Z phải được **lên lịch theo thực tế dự án**, không giả định chỉ cần “trước ngày release một ngày”.

## 21. Phát hành theo pha: giảm rủi ro mà không thay nghĩa vụ

**Deploy** là đưa mã/cấu hình tới môi trường; **release** là cho phép người dùng sử dụng khả năng; **exposure** là lúc người dùng thật sự tiếp cận tính năng. Ba việc có thể tách nhau.

### 21.1. Các phương án có thể cân nhắc

- **Internal pilot:** Nhân sự hoặc nhóm thử được phép thực hiện hành trình trong môi trường phù hợp.
- **Limited release:** Mở cho một nhóm nhỏ với điều kiện an toàn và chấp thuận rõ.
- **Canary rollout:** Theo dõi tín hiệu sản phẩm/vận hành khi mở dần một bản mới.
- **Feature flag:** Giữ tính năng mới tắt hoặc bật theo đối tượng có kiểm soát.
- **Phát hành lõi trước:** Những khả năng Must đạt Done được mở, các phần Could đến sau.
- **Phương án thủ công có kiểm soát:** Chỉ khi được phép, có năng lực, audit và đối soát dữ liệu phù hợp.

### 21.2. Feature flag không miễn trừ kiểm thử

Nếu một luồng chưa kiểm chứng phân quyền, không nên nói **“cứ bật cho 5% người dùng để test”**. Phát hành hẹp giúp hạn chế phạm vi ảnh hưởng của **rủi ro chưa lường trước**, không hợp thức hóa việc biết rõ có nguy cơ gây hại.

### 21.3. Rollback không tự đảo ngược dữ liệu

Nếu ứng dụng đã ghi hai xác nhận cho một chỗ, rollback code có thể **không xóa xung đột dữ liệu đã phát sinh**. Kế hoạch cần có:

- Cách xác định người dùng/giao dịch bị ảnh hưởng.
- Quy trình giảm tác động, đối soát và khắc phục với thẩm quyền phù hợp.
- Liên hệ Support và thông báo theo nghĩa vụ.
- Kiểm chứng sau khôi phục bằng nguồn sự thật.
- Bài học đưa về test, pipeline và runbook.

### 21.4. Không coi release theo pha là cách “lách deadline”

Nếu hợp đồng yêu cầu mọi học viên đủ điều kiện có thể đăng ký ngày D, chỉ mở cho 5% người dùng **có thể vi phạm cam kết**. Phương án pha phải được **xác minh ý nghĩa pháp lý/thương mại với chủ cam kết** trước khi chọn.

## 22. Quality gate và điểm “go/no-go” trước mốc bắt buộc

**Quality gate** là bộ điều kiện kiểm chứng trước một quyết định như merge, tạo artifact hoặc mở tính năng. **Go/no-go** là quyết định có thẩm quyền về việc phát hành trong bối cảnh toàn bộ bằng chứng/rủi ro.

### 22.1. Ví dụ quality gate cho đăng ký workshop

| Điều kiện | Bằng chứng | Nếu chưa đạt |
| --- | --- | --- |
| Build và kiểm thử bắt buộc đạt | Pipeline trên đúng commit/artifact | Sửa, điều tra hoặc áp quy trình ngoại lệ có căn cứ |
| Không vượt sức chứa | Test transaction/concurrency trên cơ chế phù hợp | Không mở luồng có rủi ro ghi sai |
| Không xem/sửa dữ liệu trái phép | Test phân quyền, review phù hợp | Không phát hành chức năng quyền chưa được kiểm chứng |
| Luồng trạng thái rõ và đúng | Acceptance tests/kiểm tra hành trình | Thu hẹp giải pháp hoặc hoàn tất kiểm chứng |
| Có hỗ trợ khi lỗi quan trọng | Runbook, theo dõi và kênh Support | Bổ sung trước khi mở phạm vi cần thiết |
| Phụ thuộc đối tác đã xác nhận | Contract test và tích hợp phù hợp | Kích hoạt phương án có thẩm quyền hoặc không mở |
| Phương án khôi phục được hiểu | Hướng dẫn/diễn tập phù hợp rủi ro | Điều tra giới hạn trước khi release |
| Cam kết đã được xác minh | Xác nhận scope/time/đối tượng | Chưa tuyên bố mốc đã đáp ứng |

### 22.2. Gate kỹ thuật không thay thế quyết định quản trị

Pipeline xanh chỉ biết những check được cấu hình đã đạt. Nó không tự xác nhận **đúng phạm vi hợp đồng, đúng đối tượng, nghĩa vụ thông báo hoặc tác động kinh doanh**.

Ngược lại, một người quản lý quyết định “go” **không làm biến mất rủi ro chưa kiểm chứng**; nếu có điều kiện an toàn bắt buộc chưa đạt, phải nêu rõ thiếu gì và phương án nào còn hợp lệ.

### 22.3. Biết dừng khi không đủ điều kiện

**No-go** có thể là một quyết định có trách nhiệm khi không còn phương án giao an toàn. Điều đó không tự phủ nhận nỗ lực của nhóm; cần ghi **rủi ro, tác động, người được thông báo và kế hoạch hành động**, đồng thời cập nhật cam kết theo đúng quyền.

## 23. Kết hợp backlog, release plan và bảng rủi ro

Product Backlog trả lời **“còn gì cần cho sản phẩm?”**, Sprint Backlog trả lời **“Developers lập kế hoạch gì để đạt Sprint Goal?”**, còn kế hoạch phát hành/rủi ro giúp các bên biết **“điều kiện để cung cấp một khả năng vào mốc bên ngoài là gì?”**

### 23.1. Bảng theo dõi quyết định sát deadline

| Hạng mục/điều kiện | Mức cần cho mốc | Tình trạng | Rủi ro | Bước tiếp | Người quyết định |
| --- | --- | --- | --- | --- | --- |
| Đăng ký chỗ cuối | Must | Đang sửa lỗi concurrency | Dữ liệu sai | Sửa, test lại, đánh giá rủi ro | Developers + thẩm quyền release |
| Xem đăng ký của mình | Must nếu trạng thái không có phương án hợp lệ khác | Chờ review phân quyền | Lộ thông tin | Review + test hai tài khoản | Developers/chuyên môn bảo mật |
| Tích hợp email | Should hoặc Must tùy cam kết | Phụ thuộc đối tác | Chậm hoặc gửi sai | Xác minh nghĩa vụ và contract | PO/chủ cam kết |
| Lịch tháng | Could | Chưa triển khai | Chiếm năng lực lõi | Hoãn nếu có đồng thuận | PO |
| Khả năng Support tiếp nhận lỗi | Must theo mức phù hợp | Còn thiếu runbook | Người dùng không được hỗ trợ | Chuẩn bị quy trình và diễn tập | Vận hành/Support |
| Xác nhận phạm vi hợp đồng | Must | Chờ trả lời | Chọn sai phạm vi | Escalate đúng người, đặt hạn | Chủ cam kết |

### 23.2. Dùng trạng thái rõ và thật

**“Đang code”**, **“chờ test”**, **“đang review”**, **“blocked”**, **“Done”** cần quy tắc. Không đổi nhãn để biểu đồ đẹp; nhiều PBI đã “dev xong” nhưng đang chờ kiểm thử vẫn là **WIP chưa giao giá trị**.

### 23.3. Mỗi rủi ro quan trọng cần chủ sở hữu hành động

Một ô “risk: high” không đủ. Nó cần:

- Dấu hiệu hoặc điều kiện khiến rủi ro xảy ra.
- Ảnh hưởng tới outcome, người dùng và deadline.
- Hành động giảm rủi ro trước ngày D.
- Người phối hợp và quyền quyết định.
- Bằng chứng xác nhận và thời điểm xem lại.

## 24. Làm sao tránh ép thêm giờ và làm nhiều việc cùng lúc?

Khi thời gian cố định, áp lực dễ biến thành **mệnh lệnh tăng năng suất 30%**. Tuy nhiên:

- Mọi người có giới hạn tập trung và thời gian.
- Công việc tích hợp/review/test có nút thắt.
- Thêm người vào cuối dự án tốn thời gian onboarding và phối hợp.
- Làm thêm giờ kéo dài có thể tăng lỗi, giảm khả năng phản ứng sự cố.
- Chuyển ngữ cảnh giữa nhiều PBI làm giảm thời gian tập trung.

### 24.1. Những cách tăng khả năng hoàn tất hợp lý hơn

1. **Ngừng mở việc Could** khi Must đang bị chặn.
2. **Swarming có mục tiêu:** Người có kỹ năng cùng tháo blocker quan trọng.
3. **Review sớm:** Không chờ một lô PR lớn sát ngày.
4. **Giữ CI đáng tin:** Nhìn lỗi tích hợp khi thay đổi còn nhỏ.
5. **Chuẩn bị test/môi trường ngay từ lúc làm rõ**.
6. **Tách lát cắt có giá trị**, kiểm tra mỗi phần đã đạt DoD.
7. **Làm rõ quyết định kịp thời** để tránh chờ Product Owner/đối tác.
8. **Cập nhật dự báo**, không cố giữ một chỉ tiêu đã mất điều kiện.

### 24.2. Nhân sự bổ sung có khi nào giúp?

Có thể giúp nếu công việc **độc lập, người mới có kỹ năng phù hợp, hạ tầng/onboarding sẵn sàng và điểm nghẽn thực sự nằm ở năng lực thiếu**. Không nên xem số người tăng là công thức tuyến tính “thêm hai người thì tốc độ gấp đôi”.

## 25. Kết nối deadline với quản trị thay đổi và truyền thông

Một rủi ro lớn thường không phải thiếu giải pháp, mà là **các bên tiếp tục dùng kỳ vọng phạm vi khác nhau**.

### 25.1. Điều cần truyền đạt khi thay scope

- **Điều không đổi:** Ngày, outcome hoặc nghĩa vụ đã được xác minh.
- **Điều thay:** Hạng mục nào hoãn, thay cách triển khai hoặc mở theo pha.
- **Tại sao:** Giá trị, rủi ro, phụ thuộc, năng lực và dữ liệu mới.
- **Ảnh hưởng:** Người dùng/đối tác, hỗ trợ, vận hành, báo cáo.
- **Bằng chứng:** Test, dự báo, tình trạng Done, xác minh hợp đồng.
- **Người quyết định:** Ai đồng ý trong phạm vi thẩm quyền?
- **Mốc xem lại:** Khi nào có kết quả mới, điều gì có thể làm đổi quyết định?

### 25.2. Mẫu thông báo phạm vi

~~~text
CHU DE: Dieu chinh pham vi mo dang ky workshop tai moc D
MOC GOC / NGUON CAM KET:
OUTCOME VA DIEU KIEN KHONG THAY DOI:

PHAM VI GIU TAI MOC:
- Dang ky hop le, khong vuot suc chua
- Xem trang thai dang ky dung quyen
- Duong ho tro/van hanh phu hop

PHAM VI DE NGHI HOAN / THAY:
- Lich thang nang cao -> sau moc
- Bo loc nang cao -> sau moc
- Email -> cho xac nhan co la nghia vu Must hay khong

BANG CHUNG:
- Nang luc/dong viec:
- Tinh trang DoD, integration/security tests:
- Phu thuoc va rui ro:

CAC PHUONG AN CAN QUYET:
- A: Pham vi loi day du an toan
- B: Mo theo pha neu duoc phe duyet
- C: Dam phan lai cam ket neu A/B khong dat

NGUOI CO THAM QUYEN / HAN QUYET DINH:
ANH HUONG DEN NGUOI DUNG VA TRUYEN THONG:
LAN CAP NHAT TIEP THEO:
~~~

**Thông báo không tự làm thay đổi hợp đồng**. Nếu cần văn bản hoặc thủ tục theo chính sách, phải hoàn tất với bên có quyền trước khi coi phạm vi mới đã được chấp thuận.

### 25.3. Không đợi có “tin tốt” mới cập nhật

Một dự báo xấu nhưng tới sớm cho phép nhiều lựa chọn: đổi phạm vi, thay hướng, hỗ trợ phụ thuộc, đàm phán. Một dự báo được làm đẹp cho tới ngày D có thể **làm mất hết thời gian phản ứng** của stakeholder.

## 26. Tình huống xuyên suốt: nền tảng workshop có mốc 15/12

**Giả định học tập:** Một đối tác đã công bố ngày mở đăng ký **15/12**, và cam kết đã được xác minh là học viên đủ điều kiện phải **có cách đăng ký đúng, nhận trạng thái đáng tin và được hỗ trợ khi phát sinh vấn đề**. Những tiện ích như lịch tháng nâng cao **không nằm trong nghĩa vụ đã xác minh**.

Nhóm có ba tuần, một Product Owner, các Developers với kỹ năng khác nhau và hỗ trợ chuyên môn về bảo mật/vận hành. Có một nhà cung cấp email bên ngoài.

### 26.1. Phạm vi ban đầu

| Mã PBI | Khả năng | Nhận định ban đầu | Điểm chưa chắc |
| --- | --- | --- | --- |
| W1 | Xem workshop phù hợp | Must | Dữ liệu số chỗ cập nhật ra sao? |
| W2 | Đăng ký giữ chỗ đúng | Must | Concurrency và rollback giao dịch |
| W3 | Xem trạng thái của mình | Must | Quyền xem và tính nhất quán |
| W4 | Hủy đăng ký | Cần xác minh | Chính sách hủy bắt buộc ngay hay sau? |
| W5 | Email xác nhận | Should | Đối tác có yêu cầu email không? |
| W6 | Lịch tháng | Could | Có cần cho mục tiêu mở đăng ký? |
| W7 | Bộ lọc nâng cao | Could | Có giá trị hơn luồng cốt lõi? |
| W8 | Dashboard báo cáo | Tách phần Must/Should | Báo cáo nào phải có khi mở? |
| W9 | Runbook/giám sát tối thiểu | Must theo rủi ro | Đã có người xử lý khi lỗi? |

### 26.2. Kết quả xác minh cam kết

Nhóm nhận được ba kết luận có chứng cứ:

1. **Ngày mở 15/12** chưa được thay theo cơ chế hiện có.
2. Cần **luồng đăng ký đúng, trạng thái đáng tin và hỗ trợ** ở mốc đó.
3. **Email nhắc, lịch tháng và bộ lọc nâng cao** chưa được xác nhận là điều kiện phải giao vào ngày 15/12.

Ngoài ra, quy tắc hủy và báo cáo đang được **người có thẩm quyền làm rõ**, nên chưa tự động coi chúng là Could.

### 26.3. Bằng chứng kỹ thuật ngày đầu

- W1 gần Done.
- W2 đã có API, nhưng test đồng thời cho chỗ cuối thất bại.
- W3 đang chờ review quyền truy cập.
- Dịch vụ email chưa có contract test thật.
- Môi trường staging chậm và một job CI flaky.
- Nút thắt là người review giao dịch và hạ tầng test, không phải thiếu task để Developer bắt đầu.

**Điều cần làm trước tiên:** Không mở thêm W6/W7, làm rõ W4/W8, ưu tiên test và sửa W2/W3, khôi phục môi trường kiểm chứng và chuẩn bị Support.

### 26.4. Kế hoạch lựa chọn theo từng tuần

| Tuần | Trọng tâm | Bằng chứng muốn có |
| --- | --- | --- |
| **Tuần 1** | Xác minh phạm vi Must; spike rủi ro đồng thời; làm rõ hủy/báo cáo; đưa test/CI vào luồng | Rủi ro lớn xuất hiện sớm; quyết định và phụ thuộc rõ |
| **Tuần 2** | Hoàn tất lát cắt W1–W3, kiểm chứng quyền/giao dịch; runbook tối thiểu; kiểm tra cùng Support | Increment cốt lõi đạt DoD hoặc biết chính xác điều còn thiếu |
| **Tuần 3** | Kiểm chứng phát hành, thử nghiệm người dùng/đối tác phù hợp, go/no-go theo điều kiện; chỉ nhận thêm Should khi an toàn | Quyết định release có thẩm quyền; thông báo và khôi phục sẵn sàng |

Bảng chỉ là **lộ trình giả định**; khi có thông tin mới, phải kiểm tra và thích ứng. Không đẩy mọi tích hợp sang ngày cuối của tuần 3.

### 26.5. Tại sao không dùng “70% chức năng hoàn thành”?

Nếu bảy trong chín PBI đã xong nhưng W2 chưa chống được xác nhận vượt sức chứa, **outcome bắt buộc vẫn có thể chưa đạt**. Ngược lại, nếu W1/W2/W3/W9 đạt DoD và các nghĩa vụ W4/W8 đã được xử lý thỏa đáng, lần mở đầu có thể tạo giá trị dù nhiều tiện ích Could chưa làm.

**Đếm số tính năng Done** chỉ hỗ trợ quản lý; nó không thay điều kiện an toàn và giá trị.

### 26.6. Các lựa chọn trước ngày quyết định

**Tình huống A — Must đạt:** Giữ ngày 15/12 với phạm vi cốt lõi đã phê duyệt; phát hành và theo dõi guardrail.

**Tình huống B — phần tiện ích chưa đạt:** Hoãn W5/W6/W7 và một số nâng cao theo thỏa thuận; không hạ DoD để làm xong tất cả.

**Tình huống C — test W2 vẫn thất bại:** Không mở luồng có rủi ro ghi sai. Đưa phương án hẹp/khác tới người có quyền; nếu không có phương án an toàn phù hợp cam kết, báo **không thể đáp ứng đầy đủ mốc** và kích hoạt điều chỉnh cam kết/chăm sóc người dùng thích hợp.

**Tình huống D — đối tác đòi mở cho mọi người:** Không tự biến một lần pilot 5% thành tuyên bố đã đáp ứng nghĩa vụ. Cần xác minh phạm vi phục vụ bắt buộc và thực hiện phương án được phê duyệt.

## 27. Một ví dụ định lượng về trade-off phạm vi

Giả sử còn **15 ngày làm việc** tới mốc, nhóm có năng lực làm việc thực tế đã tính nghỉ phép, hỗ trợ và vận hành. Sau khi kiểm tra phụ thuộc, nhóm đưa ra **các khoảng nỗ lực minh họa**:

| Hạng mục | Khoảng ngày công nhóm giả định | Nhận xét |
| --- | ---: | --- |
| Kiểm chứng và sửa luồng giữ chỗ | 5–9 | Rủi ro dữ liệu, test đồng thời |
| Xem trạng thái + phân quyền | 3–5 | Review quyền và test |
| Chuẩn bị phát hành/runbook/hỗ trợ | 2–4 | Không phải “việc ngoài dự án” |
| Email xác nhận | 3–6 | Phụ thuộc đối tác |
| Lịch tháng/bộ lọc nâng cao | 5–9 | Không thuộc outcome tối thiểu |

Các khoảng là **dữ liệu giả định**, không phải ước lượng cho dự án thực. Chúng không được cộng như giờ của cùng một người và có thể có việc song song hoặc phụ thuộc nối tiếp.

### 27.1. Tổng ngày công không bằng lịch hoàn thành

Tổng khoảng cho ba phần cốt lõi đầu là:

\[
(5+3+2)\text{ đến }(9+5+4)=10\text{ đến }18
\]

ngày công nhóm, **không có nghĩa chắc chắn hoàn tất trong 10–18 ngày lịch**. Năng lực song song, thứ tự phụ thuộc, thời gian chờ kiểm thử và người chuyên môn có thể làm lịch khác xa phép cộng.

Nếu cố thêm email và lịch nâng cao, khoảng nỗ lực thô tăng thêm **8–15 ngày công nhóm**, làm độ bất định và cạnh tranh năng lực lớn hơn.

### 27.2. Quyết định dựa trên khoảng và rủi ro

Một quyết định thận trọng là **ưu tiên ba phần cốt lõi và kiểm chứng phụ thuộc sớm**, không phân bổ toàn bộ thời gian còn lại cho các tiện ích Should/Could. Nếu W2 khó hơn dự kiến, nhóm còn khả năng xử lý thay vì bị kẹt với nhiều hạng mục mở.

### 27.3. Đừng giả định “cứ làm thêm giờ là có thêm năng lực tương ứng”

Một Developer làm 12 giờ/ngày trong tuần cuối có thể mệt mỏi và gây lỗi; người review bảo mật hoặc môi trường test vẫn có thể là nút thắt. Tăng giờ làm **không loại bỏ phụ thuộc và độ bất định**.

## 28. Theo dõi rủi ro bằng mốc kiểm chứng thay vì chỉ ngày hoàn thành

Một kế hoạch chỉ có “hoàn thành W2 ngày 10/12” thường báo vấn đề khi đã quá muộn. Cần **leading signals** về điều kiện hoàn tất.

### 28.1. Ví dụ các cổng thông tin sớm

| Mốc | Câu hỏi kiểm chứng | Quyết định nếu không đạt |
| --- | --- | --- |
| Trước khi code sâu | Có thống nhất quy tắc đồng thời, trạng thái và quyền? | Làm rõ/giảm phạm vi, không đoán |
| Sau lát cắt thử đầu | Có test tái hiện được rủi ro chỗ cuối? | Điều chỉnh thiết kế/gắn chuyên môn |
| Trước khi mở rộng tích hợp | Contract đối tác được xác nhận? | Thử đường khác hoặc hoãn hạng mục phụ thuộc |
| Trước release candidate | Must đã đạt DoD trên artifact tương ứng? | Không tự gọi là hoàn tất |
| Trước khi mở người dùng | Có bằng chứng an toàn, quyền, Support và khôi phục? | Go/no-go theo thẩm quyền |
| Sau release | Guardrail và outcome có đúng kỳ vọng? | Dừng mở rộng/sửa/điều chỉnh backlog |

### 28.2. Tần suất cập nhật phải phù hợp rủi ro

Có thể trao đổi hằng ngày khi sát mốc và rủi ro lớn, nhưng **không biến Daily Scrum thành cuộc họp báo cáo số giờ cho quản lý**. Developers kiểm tra tiến độ tới Sprint Goal và thích ứng kế hoạch; stakeholder cần báo cáo quyết định/rủi ro riêng ở mức phù hợp.

## 29. Bài học khi kế hoạch không còn khả thi

Có lúc mọi nỗ lực hợp lý vẫn không tạo phương án **đúng ngày, đúng nghĩa vụ và đủ an toàn**. Nhóm cần thừa nhận **tam giác lựa chọn**:

- **Giữ ngày + giữ chất lượng:** Phải điều chỉnh phạm vi hoặc phương án trong giới hạn được phép.
- **Giữ phạm vi + giữ chất lượng:** Cần nguồn lực/điều kiện khác hoặc thay đổi ngày nếu có quyền và khả thi.
- **Giữ ngày + giữ phạm vi bất chấp mọi thứ:** Nếu năng lực/phụ thuộc không đáp ứng, đây là **mong muốn**, không phải kế hoạch đáng tin; giảm chất lượng không phải đòn bẩy mặc định.

### 29.1. Khi nghĩa vụ không thể thay đổi

Nếu deadline, nội dung nghĩa vụ và điều kiện chất lượng đều thực sự cố định, nhưng năng lực/điều kiện còn lại không đủ, nhóm phải **escalate sớm với bằng chứng**, xem phương án thay thế hợp lệ và xử lý hệ quả hợp đồng/vận hành theo thẩm quyền.

**Không có framework Agile nào biến một bài toán bất khả thi thành khả thi bằng cách đổi tên công việc.**

### 29.2. Phương án “không phát hành” cũng cần kế hoạch

Nếu không thể mở đăng ký an toàn:

- Ai quyết định không mở và theo quy trình nào?
- Ai thông báo cho đối tác/người dùng?
- Có kênh hỗ trợ hoặc biện pháp thay thế được phép không?
- Các giao dịch/dữ liệu đang tồn tại được bảo vệ ra sao?
- Khi nào kiểm chứng lại điều kiện go?
- Những nguyên nhân lập kế hoạch cần được cải tiến thế nào?

Không phát hành là **một lựa chọn quản trị cần chuẩn bị**, không phải bỏ mặc hệ thống.

## 30. Các sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách điều chỉnh |
| --- | --- | --- |
| “Agile nên không cần giữ deadline” | Bỏ qua nghĩa vụ và niềm tin đối tác | Xác minh ràng buộc, quản trị sớm |
| “Deadline cố định thì mọi scope cũng cố định” | Không còn lựa chọn hợp lệ | Tách outcome bắt buộc khỏi giải pháp |
| “Stakeholder nói Must nên chắc là Must” | Ưu tiên mất ý nghĩa | Yêu cầu lý do, nguồn và người có quyền |
| “Nếu chưa có văn bản, cứ bỏ qua” | Có thể tồn tại nghĩa vụ thật chưa được tìm | Xác minh với chủ cam kết |
| “Minimum scope nghĩa là bỏ kiểm thử” | Đẩy lỗi sang người dùng | Giảm số khả năng, không hạ chất lượng |
| “Chia mọi thứ thành task nhỏ là xong” | Nhiều task Done nhưng không có Increment | Lát cắt dọc có giá trị và DoD |
| “Đếm PBI Done là phần trăm nghĩa vụ hoàn tất” | Một Must quan trọng có thể chưa xong | Theo dõi điều kiện thành công và rủi ro |
| “Thêm người phút cuối chắc chắn tăng tốc” | Onboarding, phối hợp và bottleneck | Đánh giá loại việc, kỹ năng và phụ thuộc |
| “Làm thêm giờ là nguồn lực miễn phí” | Tăng lỗi và giảm nhịp bền vững | Điều chỉnh phạm vi/WIP và phối hợp |
| “Pipeline xanh nên có thể release” | Check chưa bao phủ hợp đồng/giá trị | Go/no-go kết hợp kỹ thuật và quản trị |
| “Rollback sẽ xóa mọi hậu quả” | Dữ liệu đã ghi hoặc thông báo đã gửi có thể còn | Đối soát, giảm tác động, khôi phục phù hợp |
| “Pilot 5% tự động đáp ứng cam kết toàn bộ” | Có thể vi phạm nghĩa vụ phạm vi phục vụ | Xin chấp thuận theo quyền |
| “QA làm chậm nên chuyển test sang sau release” | Lỗi quan trọng lọt tới người dùng | Test theo rủi ro trong từng lát cắt |
| “Mock chạy được nghĩa là tích hợp đối tác xong” | Chưa kiểm chứng hợp đồng và môi trường thật | Contract/integration test thích hợp |
| “Burndown đẹp chứng minh Sprint Goal đạt” | Số điểm không chứng minh Increment Done | Xem Sprint Goal và DoD |
| “Phát hiện khó khăn mới thì cứ giữ dự báo cũ” | Bỏ lỡ thời điểm điều chỉnh | Cập nhật dự báo cùng bằng chứng |
| “Nếu PO ưu tiên thì có thể bỏ mọi kiểm soát” | Sai ranh giới quyền an toàn/hợp đồng | Phân biệt Product Backlog và thẩm quyền khác |
| “Mọi quyết định đều phải chờ cấp cao” | Chậm thích ứng trong phạm vi tự quản | Làm rõ quyền quyết định |
| “Hủy Sprint khi một PBI trễ” | Sai điều kiện Scrum, bỏ cơ hội thích ứng | Chỉ PO hủy khi Sprint Goal lỗi thời |
| “PBI chưa Done vẫn có thể tính Increment” | Mất minh bạch, phát hành thiếu chất lượng | Không tính phần chưa đạt DoD |
| “Gọi No-go là thất bại cá nhân” | Khuyến khích che rủi ro | Quản trị và học từ điều kiện hệ thống |
| “Không truyền thông scope thay đổi” | Stakeholder dùng kỳ vọng cũ | Ghi quyết định, ảnh hưởng và thông báo |
| “Tất cả số ước lượng là ngày lịch” | Phụ thuộc và năng lực bị hiểu sai | Phân biệt effort, elapsed time và uncertainty |
| “Mọi bug phải sửa trước deadline bất kể tác động” | Lệch ưu tiên và không dựa rủi ro | Triage theo DoD, mức nghiêm trọng và nghĩa vụ |
| “Lỗi nghiêm trọng có thể hoãn vì là việc ngoài Sprint” | Gây hại người dùng | Ứng phó theo quy trình sự cố ngay |

## 31. Checklist lập kế hoạch dưới deadline bắt buộc

Đây là **mẫu thực hành**, không phải văn bản quản trị bắt buộc của một framework Agile.

~~~text
XAC MINH RANG BUOC
[ ] Deadline co nguon/nguoi xac nhan?
[ ] Moc co gio, mui gio va dieu kien hieu luc?
[ ] Co phan biet ngay, outcome, chat luong va pham vi?
[ ] Co nghia vu phap ly/hop dong can tham dinh chuyen mon?
[ ] Co nguoi co tham quyen doi cam ket/chap nhan phuong an?

CHON PHAM VI
[ ] Outcome toi thieu duoc mo ta bang hanh vi nguoi dung?
[ ] Moi Must co ly do va bang chung?
[ ] Should/Could/Won't now duoc thong nhat va ghi ro?
[ ] Cac phu thuoc an giua Must va Should da duoc kiem tra?
[ ] Lat cat dau tien co the dung va dat Done?

DU BAO VA DONG CONG VIEC
[ ] Nang luc thuc te, on-call, nghi phep, phu thuoc duoc xem xet?
[ ] Du lieu lich su co tuong dong va ran gioi Done nhat quan?
[ ] Ranh gioi cua uoc luong/dieu chua chac duoc neu ro?
[ ] WIP, work item age va blocker co duoc nhin thay?
[ ] Co moc kiem chung som cho rui ro lon?
[ ] Co phuong an neu du bao khong con phu hop?

CHAT LUONG / PHAT HANH
[ ] DoD va quality gate khong bi ha chi de du kip?
[ ] Test nghiep vu, dong thoi, phan quyen theo rui ro phu hop?
[ ] Da kiem chung phu thuoc va moi truong quan trong?
[ ] Co release plan, monitoring, Support va phuc hoi?
[ ] Go/no-go va nguoi quyet dinh da ro?
[ ] Phuong an theo pha duoc xac minh khong trai cam ket?

QUAN TRI / TRUYEN THONG
[ ] Ai so huu Product Backlog, ai so huu hop dong, ai quyet release?
[ ] Phuong an co loi ich, rui ro, anh huong va dieu kien ro?
[ ] Scope de nghi thay da duoc chap thuan dung tham quyen?
[ ] Stakeholder va nguoi dung lien quan duoc cap nhat trung thuc?
[ ] Co thoi diem xem lai, khong doi den ngay cuoi?

CAI TIEN
[ ] Ket qua release/No-go duoc kiem chung bang evidence?
[ ] Bai hoc duoc dua vao backlog, test, runbook va retrospective?
[ ] Khong dung metric de phat nguoi noi som ve rui ro?
~~~

Không cần biến từng ô thành giấy ký mỗi ngày. Mục tiêu là **không quên điều kiện quyết định quan trọng**, đặc biệt khi áp lực thời hạn làm các bên dễ tối ưu số lượng đầu ra thay vì chất lượng thực.

## 32. Bài tập 1 — Phân loại ràng buộc trước khi thương lượng

**Bối cảnh:** Một nền tảng đào tạo dự kiến mở đăng ký ngày 15/12. Trong cuộc họp, các bên đưa ra tuyên bố:

1. “Đối tác đã công bố ngày, không thể đổi.”
2. “Phải có lịch tháng vì người dùng thích nhìn lịch.”
3. “Không được lộ dữ liệu đăng ký của học viên.”
4. “Cần email xác nhận vì chúng tôi thường gửi email.”
5. “Nhà cung cấp sẽ đóng API cũ cuối tháng.”
6. “Đợt này không thể vượt ngân sách đã được duyệt.”
7. “Nếu chưa có test đồng thời, có thể bật cho 100 người trước.”
8. “Phải có báo cáo theo đúng định dạng đã cam kết.”

### Câu hỏi

1. Với từng câu, điều gì là **ràng buộc đã có bằng chứng**, điều gì là **mong muốn**, và điều gì **cần xác minh**?
2. Ràng buộc nào cần người có chuyên môn về hợp đồng/pháp lý xác nhận?
3. Vì sao “bật cho 100 người” không phải phương án an toàn khi đã biết nguy cơ xác nhận vượt sức chứa?
4. Mỗi ràng buộc cần ghi thêm nguồn, mốc, phạm vi hay quyền quyết định nào?
5. Đề xuất một khả năng Should/Could có thể hoãn mà không làm sai outcome.
6. Viết một câu hỏi giúp làm rõ liệu email là nhu cầu giá trị hay nghĩa vụ.

### Gợi ý hướng giải

Đừng chấp nhận tất cả nhãn “phải” như đã được chứng minh. **Bảo vệ dữ liệu** là điều kiện chất lượng/rủi ro cần giữ; **API ngừng hỗ trợ** có thể là ràng buộc bên ngoài cần đối chiếu thông báo chính thức; **lịch tháng** thường là lựa chọn giải pháp cần kiểm chứng giá trị; **báo cáo đúng định dạng** có thể là Must nếu cam kết đã xác nhận.

Mở hẹp không thay thế kiểm thử một lỗi nguy hiểm đã biết. Nhóm cần có giải pháp an toàn và quyết định theo thẩm quyền trước khi cho người dùng sử dụng.

## 33. Bài tập 2 — Chọn phạm vi tối thiểu an toàn

**Đề bài:** Nhóm có ba tuần. Lát cắt A (xem workshop) đã Done; B (đăng ký giữ chỗ) còn lỗi đồng thời; C (xem trạng thái) đang chờ review phân quyền; D (email) chưa có integration test; E (bộ lọc) đã code nhưng chưa Done; F (runbook) chưa thử.

Stakeholder yêu cầu demo A–F vào ngày cuối. Cam kết đã xác minh chỉ bắt buộc **đăng ký hợp lệ, trạng thái đúng, kênh hỗ trợ và bảo vệ dữ liệu**.

### Yêu cầu

1. Xếp A–F thành Must/Should/Could cho mốc đầu và nêu điều kiện.
2. Việc gì cần **hoàn tất trước khi mở thêm PBI mới**?
3. Vì sao E “đã code xong” không được tính là Increment nếu chưa đạt DoD?
4. B và C cần loại kiểm chứng nào?
5. F có giá trị gì trong một deadline cứng?
6. Có nên tập trung hoàn tất D trước B vì D dễ hơn không?
7. Nếu hết Sprint B chưa Done, xử lý Scrum như thế nào?
8. Viết một thông báo phạm vi ngắn cho stakeholder.

### Gợi ý hướng giải

**A** đã Done. **B/C** là phần cốt lõi nhưng chưa đủ điều kiện; ưu tiên sửa và kiểm chứng đúng rủi ro. **F** góp phần bảo đảm khả năng hỗ trợ vận hành khi mở; mức hoàn thiện phụ thuộc rủi ro và chính sách. **D/E** có thể hoãn nếu không có nghĩa vụ khác. “Code xong” không tương đương Done; phần chưa đạt DoD không trở thành Increment nhờ đổi nhãn.

Trong Scrum, phần chưa hoàn tất được xem lại trong Product Backlog; không tự kéo dài Sprint để hoàn tất mọi thứ. Sprint Goal và kế hoạch cần được thích ứng trong phạm vi quy tắc Scrum.

## 34. Bài tập 3 — Ra quyết định khi không thể giao đủ Must

**Bối cảnh:** Còn bốn ngày trước mốc mở đăng ký. Integration test cho thấy hai học viên có thể cùng xác nhận chỗ cuối. Người có chuyên môn dữ liệu đề xuất sửa có kiểm chứng nhưng cần thêm thời gian. Đối tác vẫn muốn giữ ngày. Một quản lý đề xuất:

> “Tắt test đó trong CI, chỉ mở cho 10% người dùng trước. Nếu có vấn đề thì rollback. Đánh dấu PBI Done để kịp báo cáo.”

### Câu hỏi

1. Những điều nào trong đề xuất đang **đánh đổi chất lượng không hợp lệ**?
2. Vì sao giới hạn 10% người dùng không làm bug đồng thời trở nên an toàn?
3. Vì sao rollback code có thể không khôi phục đầy đủ trạng thái dữ liệu?
4. Những phương án nào có thể đề xuất tới chủ cam kết? Cần kiểm chứng điều gì?
5. Ai được quyền quyết định thay đổi hợp đồng, ai chịu trách nhiệm xác minh test và ai quyết định release?
6. Nếu không có phương án khả thi, thông báo no-go cần chứa những thông tin nào?
7. Khi Sprint Goal vẫn có giá trị, chỉ một PBI chưa xong có phải lý do hủy Sprint không?
8. Viết một bản ghi ngắn về rủi ro và hành động tiếp theo, không đổ lỗi cá nhân.

### Gợi ý hướng giải

Không bỏ test để che lỗi, không đánh dấu Done giả và không đưa lỗi dữ liệu đã biết vào production chỉ vì phạm vi người dùng nhỏ. Cần **ưu tiên sửa/kiểm chứng**, đánh giá phương án xử lý thay thế an toàn và **đưa quyết định phạm vi/mốc tới người có quyền**. Nếu không có lựa chọn đáp ứng chất lượng và nghĩa vụ, nêu rõ không thể xác nhận go. **Sprint chỉ bị hủy khi Sprint Goal trở nên lỗi thời và chỉ Product Owner có quyền hủy**, không vì “PBI này trễ bốn ngày”.

## 35. Bài tập 4 — Dùng dự báo mà không ép năng suất

**Đề bài:** Throughput sáu tuần là **4, 5, 3, 4, 6, 2 PBI/tuần**. Còn ba tuần, 6 PBI Must và 12 PBI Should/Could. Hai PBI Must có rủi ro tích hợp; một người review chính sắp nghỉ phép.

### Câu hỏi

1. Tính throughput trung bình lịch sử.
2. Nếu dùng số trung bình để tính “12 PBI trong ba tuần”, giả định nào đang bị ẩn?
3. Vì sao có thể vẫn không hoàn tất 6 Must dù tổng số 6 nhỏ hơn 12?
4. Nên kiểm chứng phụ thuộc và năng lực review từ lúc nào?
5. Bạn đề xuất một giới hạn WIP hoặc hành động swarming ra sao?
6. Chọn ba guardrail cần giữ khi giảm cycle time.
7. Phương pháp dự báo theo kịch bản có ưu điểm gì hơn một lời hứa cố định?
8. Khi phát hiện rủi ro mới, cần báo stakeholder thế nào?

### Gợi ý hướng giải

Throughput trung bình là **4 PBI/tuần** trong mẫu quan sát, nhưng item khác nhau về độ khó, chính sách Done và phụ thuộc. Tồn tại người review duy nhất nghỉ phép có thể khiến vài Must bị chặn, bất kể tổng số item.

Cách làm tốt hơn là **phân tích nhóm Must, thử tích hợp sớm, giảm WIP, bố trí dự phòng và cập nhật dự báo theo bằng chứng**, kèm guardrail về dữ liệu, phân quyền và ổn định vận hành. Không chuyển “4 PBI/tuần” thành chỉ tiêu điểm của mỗi Developer.

## 36. Câu hỏi tự kiểm tra

1. Vì sao một deadline bên ngoài có thể cố định trong khi phạm vi giải pháp vẫn có lựa chọn?
2. Phân biệt ràng buộc đã xác minh, giả định, mục tiêu nội bộ và mong muốn stakeholder.
3. Điều gì cần ghi trong một constraint record để tránh tranh luận mơ hồ?
4. “Outcome bắt buộc” khác danh sách tính năng ban đầu ở đâu?
5. Khi nào một tính năng Should có thể trở thành Must?
6. Minimum viable scope khác “giảm chất lượng để đủ ngày” như thế nào?
7. Những phần nào là đòn bẩy hợp lệ khi thời gian cố định?
8. Vì sao tăng người hoặc tăng giờ làm không bảo đảm tăng tốc tuyến tính?
9. PBI code complete nhưng chưa đạt DoD có được tính là Increment không?
10. Sprint Goal khác Product Goal và danh sách PBI trong Sprint Backlog thế nào?
11. Trong Sprint, phạm vi có thể thương lượng với ai và giới hạn gì không được vi phạm?
12. Điều kiện hủy Sprint trong Scrum là gì? Ai có thẩm quyền?
13. Bốn Kanban flow metrics giúp nhận diện rủi ro sát deadline thế nào?
14. Dự báo throughput trung bình cần những giả định gì?
15. Vì sao effort không thể quy đổi trực tiếp thành elapsed time?
16. Mock API đối tác có thể giúp gì và chưa chứng minh điều gì?
17. Ai có quyền xác nhận thay đổi nghĩa vụ hợp đồng hoặc rủi ro tuân thủ?
18. Feature flag và canary giúp giảm những rủi ro gì, không giảm được rủi ro nào?
19. Vì sao rollback code không giải quyết hết hậu quả dữ liệu?
20. Một bảng go/no-go cần những loại bằng chứng nào?
21. Khi một điều Must không khả thi, phải trình bày những lựa chọn nào?
22. Vì sao thay scope mà không thông báo có thể làm hỏng niềm tin?
23. Một bản cập nhật dự báo xấu có thể giúp stakeholder quyết định sớm ra sao?
24. Nếu vẫn không có phương án release an toàn đúng ngày, cách hành động có trách nhiệm là gì?

## 37. Ghi nhớ: bảo vệ điều không thể đánh đổi, thương lượng điều có thể đổi

**Xử lý thời hạn bắt buộc và phạm vi có thể thương lượng** không có nghĩa chọn giữa **“giữ lời hứa bằng mọi giá”** và **“Agile nên bỏ deadline”**. Cách tiếp cận có trách nhiệm là xác minh **nguồn của ràng buộc, điều kiện thành công, quyền quyết định, năng lực và những rủi ro cần bảo vệ**; từ đó đề xuất phạm vi hoặc phương án thực hiện có thể kiểm chứng.

Những nguyên tắc cốt lõi:

1. **Xác thực deadline và nghĩa vụ:** Phân biệt ngày thực, mục tiêu nội bộ và giả định chưa có chứng cứ.
2. **Giữ outcome, không đóng băng mọi giải pháp:** Một lát cắt nhỏ, hoàn chỉnh có thể đạt giá trị hơn nhiều tính năng dở.
3. **Thương lượng phạm vi minh bạch:** Must/Should/Could được quyết định trên lý do, quyền và ảnh hưởng thật.
4. **Không dùng chất lượng làm biến điều chỉnh tùy tiện:** Bảo vệ dữ liệu, phân quyền, DoD và kiểm chứng rủi ro.
5. **Ưu tiên dòng công việc hoàn tất:** Giảm WIP, tháo blocker, tích hợp và kiểm thử sớm.
6. **Dự báo với bất định:** Nêu dữ liệu, giả định, phương án và mốc kiểm chứng; không tạo cam kết giả.
7. **Phân biệt quyền quyết định:** Product Owner, Developers, chủ cam kết, bảo mật và vận hành có vai trò khác nhau.
8. **Phát hành theo pha chỉ khi hợp lệ:** Pilot/canary/feature flag không thay thế kiểm thử hoặc tự điều chỉnh hợp đồng.
9. **Báo sớm khi không khả thi:** Đưa trade-off đúng người, không che rủi ro bằng biểu đồ hay nhãn Done.
10. **Học từ kết quả:** Kiểm tra outcome và guardrail sau release hoặc no-go; cải tiến cách chọn scope và nhận phản hồi.

Trước khi nhận thêm một hạng mục sát deadline, hãy hỏi: **“Điều gì bắt buộc phải đúng vào mốc này, ai xác nhận điều ấy, chúng ta còn quyền thay đổi phần nào và bằng chứng nào cho thấy lát cắt được chọn đã đủ chất lượng để giao?”** Trả lời được câu hỏi đó giúp nhóm Agile **giữ cam kết có trách nhiệm, giao giá trị tăng dần và thích ứng theo thực tế mà không đánh đổi sự an toàn hoặc lòng tin của người dùng**.
