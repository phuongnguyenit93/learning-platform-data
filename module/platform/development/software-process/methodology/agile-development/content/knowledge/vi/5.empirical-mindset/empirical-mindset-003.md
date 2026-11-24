# Tư duy thực nghiệm: Kiểm tra kết quả và điều chỉnh dựa trên bằng chứng

Phát triển phần mềm luôn chứa những điều chưa biết: người dùng có thực sự cần tính năng không, thiết kế có dễ hiểu không, một quy trình làm việc có giảm thời gian chờ không, và liệu thay đổi kỹ thuật có tạo ra lỗi mới không. **Tư duy thực nghiệm (empirical mindset)** giúp nhóm đưa ra quyết định dựa trên những gì đã quan sát và kiểm chứng được, đồng thời sẵn sàng điều chỉnh khi bằng chứng khác với giả định ban đầu.

Trong mô-đun **AGILE_DEVELOPMENT**, trọng tâm là phát triển thích ứng bằng **phản hồi sớm**, **bàn giao sản phẩm tăng dần** và **cải tiến liên tục**. Tư duy thực nghiệm tạo cầu nối giữa các giá trị Agile với việc thực hành user story, Product Backlog, Scrum, Kanban, XP và đo lường dòng công việc. Các thực hành này có ích khi giúp nhóm học từ kết quả thật; tự thân số cuộc họp, số story đóng hoặc số lần phát hành chưa chứng minh sản phẩm đã tạo giá trị.

Bài này tập trung vào một năng lực cụ thể: **kiểm tra kết quả, đánh giá bằng chứng và điều chỉnh hành động tiếp theo**. Mục đích không phải trở thành nhà thống kê trước khi bắt đầu làm Agile, mà là biết đặt câu hỏi đúng, thu thập dữ liệu vừa đủ, tránh kết luận vội và biến điều học được thành thay đổi có thể kiểm chứng.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Giải thích quan hệ giữa **minh bạch – kiểm tra – thích ứng** trong kiểm soát quá trình theo kinh nghiệm thực tế.
2. Phân biệt **giả định**, **giả thuyết**, **quan sát**, **bằng chứng**, **kết luận tạm thời** và **quyết định**.
3. Phân biệt đầu ra của nhóm phát triển với kết quả người dùng đạt được; chọn chỉ số phù hợp với câu hỏi cần trả lời.
4. Thiết kế một vòng kiểm chứng nhỏ có mốc so sánh, cách thu thập dữ liệu, tiêu chí ra quyết định và chỉ số bảo vệ chất lượng.
5. Kết hợp dữ liệu định lượng với phản hồi định tính, phát hiện giới hạn của mẫu và những yếu tố có thể làm sai lệch kết luận.
6. Dùng kết quả kiểm tra để cập nhật Product Backlog, thay đổi cách làm trong Scrum/Kanban hoặc cải thiện kỹ thuật bằng XP.
7. Đề xuất một cải tiến cụ thể có người phụ trách, thời điểm xem lại và bằng chứng để quyết định giữ, điều chỉnh hoặc dừng.

## 2. Nền tảng: minh bạch, kiểm tra và thích ứng

Trong Scrum, **empiricism** dựa trên việc hiểu biết đến từ kinh nghiệm và quyết định được đưa ra từ những gì đã quan sát. Ba trụ cột hỗ trợ là **transparency (minh bạch)**, **inspection (kiểm tra)** và **adaptation (thích ứng)**. Ba điều này cũng là khung tư duy hữu ích ngoài Scrum.

| Trụ cột | Câu hỏi cần trả lời | Ví dụ khi phát triển phần mềm |
| --- | --- | --- |
| **Minh bạch** | Mọi người có cùng hiểu trạng thái và tiêu chuẩn đánh giá không? | Backlog có thứ tự rõ; các story có tiêu chí chấp nhận; mọi người thống nhất khi nào việc được tính là hoàn thành. |
| **Kiểm tra** | Quan sát thực tế cho thấy điều gì đang xảy ra? | Dùng thử một luồng đăng ký, xem lỗi phát sinh, quan sát thời gian chờ và phản hồi người dùng. |
| **Thích ứng** | Với kết quả mới, nhóm cần thay đổi điều gì? | Sửa thứ tự backlog, chia story nhỏ hơn, thay quy trình review mã, cải thiện thông báo cho người dùng. |

Ba bước liên kết với nhau. **Không minh bạch**, số liệu dễ bị hiểu khác nhau: một người đánh dấu “Done” khi viết mã xong, người khác chỉ tính khi đã kiểm thử và triển khai. **Không kiểm tra**, nhóm tiếp tục làm theo suy đoán. **Không thích ứng**, việc thu thập phản hồi chỉ trở thành hình thức.

~~~mermaid
flowchart LR
    A[Minh bạch: mục tiêu, trạng thái, tiêu chuẩn] --> B[Kiểm tra: quan sát kết quả và sự khác biệt]
    B --> C[Thích ứng: quyết định thay đổi]
    C --> D[Thực hiện thay đổi trong phạm vi nhỏ]
    D --> E[Kiểm tra tác động của thay đổi]
    E --> A
~~~

Vòng lặp này diễn ra liên tục. Không phải mọi kiểm tra đều dẫn đến thay đổi; đôi khi bằng chứng xác nhận nên giữ cách làm hiện tại. Cũng không nên chờ đến cuối Sprint mới xử lý một vấn đề nghiêm trọng đã rõ.

### 2.1. Phân biệt sự thật quan sát được với cách diễn giải

Giả sử nhóm nhận phản hồi: “Trang tạo yêu cầu hỗ trợ khó dùng”.

- **Quan sát:** trong 12 lượt dùng thử, có 5 lượt dừng ở bước chọn loại sự cố.
- **Phản hồi định tính:** ba người nói họ không hiểu tên các loại sự cố.
- **Giả thuyết:** cách đặt tên phân loại khiến người dùng không biết chọn gì.
- **Kết luận tạm thời:** bước phân loại có dấu hiệu gây khó khăn và đáng được kiểm tra kỹ hơn.
- **Quyết định:** thử thay các nhãn bằng từ ngữ gần với cách người dùng mô tả sự cố, rồi quan sát một nhóm người mới.

Không thể nhảy trực tiếp từ “5 người dừng” đến “nguyên nhân chắc chắn là màu nút bấm”. Có thể họ gặp lỗi kỹ thuật, không tìm thấy lựa chọn phù hợp hoặc đang làm tác vụ không liên quan. Tư duy thực nghiệm đòi hỏi **tách điều đã thấy khỏi điều đang suy đoán**.

### 2.2. Bằng chứng không phải lúc nào cũng là con số

Bằng chứng có thể đến từ bản ghi hệ thống, quan sát người dùng thao tác, cuộc phỏng vấn, lỗi tái hiện được, phản hồi hỗ trợ, kiểm thử tự động hoặc kết quả vận hành. Điều quan trọng là **nguồn có phù hợp với câu hỏi và được thu thập đáng tin cậy không**.

Ví dụ:

- Muốn biết **người dùng hiểu trạng thái yêu cầu ra sao**: quan sát và phỏng vấn theo tình huống rất hữu ích.
- Muốn biết **tỷ lệ gửi yêu cầu thành công**: cần sự kiện đo được trong sản phẩm và định nghĩa rõ mẫu số.
- Muốn biết **mã mới có phá quy tắc phân quyền không**: cần kiểm thử phù hợp, review và theo dõi sự cố.
- Muốn biết **công việc chờ ở khâu kiểm thử bao lâu**: cần mốc chuyển trạng thái trên bảng công việc.

Một cuộc phỏng vấn sâu có thể chỉ ra **vì sao** người dùng vướng, nhưng không tự cho biết **bao nhiêu phần trăm toàn bộ người dùng** gặp vấn đề. Một dashboard cho biết **đã xảy ra điều gì**, nhưng đôi khi không giải thích được **vì sao**.

## 3. Kiểm tra đúng kết quả: đầu ra, kết quả và tác động

Khi đánh giá một Sprint hoặc một lần bàn giao, nhóm thường có xu hướng báo “đã hoàn thành bao nhiêu chức năng”. Đó là thông tin cần thiết nhưng chưa đủ để biết khách hàng có hài lòng hơn hay không.

| Tầng quan sát | Ý nghĩa | Ví dụ với hệ thống yêu cầu hỗ trợ nội bộ |
| --- | --- | --- |
| **Hoạt động (activity)** | Nhóm đã làm gì | Họp refinement, viết mã, review pull request, chạy kiểm thử. |
| **Đầu ra (output)** | Nhóm đã tạo ra thứ gì | Màn hình tra cứu trạng thái, API và chức năng gửi thông báo. |
| **Kết quả (outcome)** | Hành vi hoặc lợi ích người dùng đã thay đổi thế nào | Nhân viên ít phải nhắn hỏi trạng thái hơn; biết yêu cầu nào đang được xử lý. |
| **Tác động (impact)** | Giá trị rộng hơn, thường xuất hiện sau một thời gian | Giảm gián đoạn công việc, bộ phận hỗ trợ vận hành ổn định hơn. |

Một chức năng đã được phát hành là **bằng chứng về đầu ra**. Để khẳng định đã tạo **kết quả**, nhóm cần quan sát hành vi hoặc lợi ích liên quan; để nói đến **tác động**, có thể cần nhiều vòng theo dõi và tính đến yếu tố khác.

Ví dụ nhóm vừa thêm trang tra cứu trạng thái. Dashboard ghi 1.000 lượt xem là tín hiệu tính năng được mở, nhưng vẫn chưa chứng minh người dùng tìm được câu trả lời hoặc số lần phải hỏi hỗ trợ đã giảm. Một chỉ số gần với giá trị hơn có thể là **tỷ lệ yêu cầu cần người gửi nhắn hỏi lại trạng thái trong vòng 7 ngày**, được xác định bằng quy tắc ghi nhận nhất quán.

### 3.1. Mỗi chỉ số phải đi cùng một quyết định

Trước khi đo, hỏi: **Nếu chỉ số này tăng, giảm hoặc không đổi thì nhóm sẽ quyết định điều gì?** Nếu câu trả lời là “không biết”, có thể nhóm đang đo cho đẹp báo cáo.

Một số nhóm câu hỏi hữu ích:

| Câu hỏi cần quyết định | Loại bằng chứng | Quyết định khả dĩ |
| --- | --- | --- |
| Người dùng có tự tạo yêu cầu thành công không? | Tỷ lệ hoàn tất luồng, lỗi thao tác, ghi nhận dùng thử | Sửa nội dung hướng dẫn hoặc chia lại luồng nhập liệu. |
| Việc xem trạng thái có giảm nhắn hỏi không? | Số lần hỏi lại trên mỗi yêu cầu, phân nhóm trước/sau | Mở rộng thử nghiệm, điều chỉnh thông báo hoặc dừng. |
| Công việc bị chờ ở đâu? | WIP, work item age, cycle time, thời gian ở từng trạng thái | Giảm WIP, thay chính sách review, gỡ phụ thuộc. |
| Phát hành thường xuyên có giữ được chất lượng không? | Kiểm thử, sự cố, lỗi phát sinh sau phát hành | Tăng mức kiểm chứng, cải thiện CI hoặc điều chỉnh phạm vi release. |
| Phần việc tiếp theo đáng ưu tiên nhất là gì? | Phản hồi người dùng, tác động kinh doanh, rủi ro, chi phí | Sắp lại Product Backlog và thay mục tiêu vòng tiếp theo. |

Không có “bộ KPI Agile” cố định phù hợp cho mọi nhóm. Chỉ số chỉ hữu ích khi phản ánh đúng mục tiêu và có định nghĩa ổn định.

## 4. Chuyển giả định thành giả thuyết có thể kiểm chứng

### 4.1. Giả định và giả thuyết khác nhau thế nào?

- **Giả định:** điều nhóm đang tin nhưng chưa đủ bằng chứng, ví dụ “nhân viên thường hỏi lại vì không thấy trạng thái yêu cầu”.
- **Giả thuyết:** phát biểu có thể kiểm chứng, nêu thay đổi dự kiến và bằng chứng cần quan sát, ví dụ “nếu hiển thị trạng thái và người phụ trách rõ ràng, tỷ lệ yêu cầu cần hỏi lại sẽ giảm”.
- **Phép kiểm tra:** cách tạo cơ hội quan sát giả thuyết, chẳng hạn thử chức năng cho một bộ phận trước khi mở rộng.
- **Tiêu chí đánh giá:** điều kiện giúp quyết định giữ, thay đổi hoặc dừng; cần xác định trước khi nhìn kết quả nếu có thể.

Một khung viết thực hành:

> **Chúng tôi tin rằng** [thay đổi] **sẽ giúp** [nhóm người dùng] **đạt** [kết quả mong muốn]. **Chúng tôi sẽ kiểm tra bằng** [bằng chứng và cách thu thập] **trong** [phạm vi, thời gian]. **Nếu** [tiêu chí], **chúng tôi sẽ** [quyết định tiếp theo].

Ví dụ:

> Chúng tôi tin rằng việc hiển thị trạng thái yêu cầu kèm thời điểm cập nhật gần nhất sẽ giúp nhân viên gửi yêu cầu ít phải nhắn hỏi bộ phận hỗ trợ. Chúng tôi sẽ thử với một bộ phận trong hai tuần, đo tỷ lệ yêu cầu phát sinh câu hỏi “đang xử lý đến đâu?” trong 7 ngày kể từ khi tạo, và phỏng vấn một số người dùng. Nếu tỷ lệ giảm mà thời gian giải quyết và số lỗi không xấu đi đáng kể, chúng tôi sẽ xem xét mở rộng thử nghiệm.

Thời hạn, ngưỡng giảm và điều kiện mở rộng phải được nhóm thống nhất theo dữ liệu nền, nguồn lực và mức rủi ro thực tế. Không nên chọn ngưỡng chỉ vì nó giúp kết quả trông đẹp.

### 4.2. Tránh giả thuyết không thể bác bỏ

“Làm dashboard hiện đại sẽ khiến người dùng thích hệ thống” quá mơ hồ: thế nào là “hiện đại”, thế nào là “thích”, đo bằng cách nào?

Thay bằng: “Khi trang danh sách hiển thị rõ trạng thái và hành động tiếp theo, tỷ lệ người dùng cần hỏi bộ phận hỗ trợ về tiến độ yêu cầu sẽ giảm trong nhóm được thử nghiệm”. Giả thuyết mới có thể sai; **khả năng bị bác bỏ là ưu điểm**, vì nó giúp nhóm học điều gì cần thay đổi.

### 4.3. Chọn thước đo chính và thước đo bảo vệ

Khi thử một cải tiến, nên phân biệt:

- **Chỉ số chính (primary outcome):** đo kết quả mà giả thuyết muốn cải thiện.
- **Chỉ số bảo vệ (guardrail):** theo dõi điều không được làm xấu đi, như lỗi, trải nghiệm của nhóm khác, chất lượng dịch vụ hoặc thời gian giải quyết.
- **Chỉ số chẩn đoán:** giúp hiểu tại sao kết quả thay đổi, chẳng hạn số lần mở trang trạng thái, thời gian ở bước “chờ xử lý”, lý do người dùng hỏi lại.

Trong ví dụ trên, mục tiêu “ít hỏi lại” không nên đạt bằng cách làm người dùng **khó tìm kênh liên hệ**. Đó có thể giảm số câu hỏi được ghi nhận mà không cải thiện trải nghiệm. Nhóm cần kiểm tra liệu người dùng thực sự **hiểu trạng thái, tin tưởng tiến độ** và vẫn có đường hỗ trợ khi cần.

## 5. Thiết kế phép kiểm tra có thể tin được

Không phải mọi quyết định đều cần A/B test hay một nghiên cứu lớn. Nhưng kể cả thử nghiệm nhỏ cũng cần thiết kế để tránh tự đánh lừa mình.

### 5.1. Bước 1 — Xác định thời điểm, đối tượng và điểm xuất phát

Một tỷ lệ vô nghĩa nếu không rõ mẫu số. Ví dụ “20% yêu cầu phải hỏi lại” cần giải thích:

- Mẫu số là **số yêu cầu đã tạo** trong khoảng thời gian nào?
- Một yêu cầu có nhiều lần nhắn hỏi được tính là một hay nhiều?
- Câu hỏi về lỗi hệ thống có bị gộp với câu hỏi về trạng thái không?
- Người dùng nào nằm trong phạm vi: một bộ phận, toàn công ty, người dùng mới hay đã quen hệ thống?
- Có theo dõi đủ 7 ngày cho mọi yêu cầu không, hay có yêu cầu vừa tạo hôm qua?

Trước khi thay đổi, thu thập **baseline (đường cơ sở)** bằng cùng quy tắc đo. Nếu chưa có khả năng đo chính xác, cần ghi nhận giới hạn thay vì gán độ chắc chắn giả tạo cho dữ liệu.

### 5.2. Bước 2 — Thống nhất cách ghi nhận

Ví dụ một hệ thống hỗ trợ có thể phát sự kiện:

~~~text
request_created
request_status_viewed
request_followup_sent
request_resolved
request_reopened
~~~

Mỗi bản ghi cần mốc thời gian, mã yêu cầu và loại sự kiện phù hợp; có thể cần mã người dùng hoặc nhóm ở mức đã được phép thu thập. Nhóm phải tránh lưu nội dung nhạy cảm không cần thiết và tuân thủ quyền truy cập dữ liệu.

**Định nghĩa minh họa:** “Tỷ lệ hỏi lại trạng thái trong 7 ngày” = **số yêu cầu có ít nhất một lần hỏi lại vì chưa rõ tiến độ trong 7 ngày kể từ khi tạo / tổng số yêu cầu thuộc nhóm quan sát đã có đủ 7 ngày theo dõi**. Nếu số sự kiện được gửi trùng do lỗi ghi log, việc đếm phải xử lý trùng trước khi đưa vào mẫu số hay tử số.

### 5.3. Bước 3 — Chọn cách so sánh phù hợp

| Cách kiểm tra | Khi nào phù hợp | Hạn chế |
| --- | --- | --- |
| **Dùng thử có quan sát** | Luồng mới chưa rõ có dễ hiểu không | Mẫu nhỏ, môi trường thử khác thực tế, không ước lượng tốt tỷ lệ toàn bộ người dùng. |
| **Phát hành giới hạn (pilot)** | Muốn kiểm chứng giá trị và vận hành với mức rủi ro kiểm soát được | Nhóm thử có thể khác nhóm sẽ triển khai rộng. |
| **So sánh trước–sau** | Có số liệu nền và thay đổi vào thời điểm xác định | Mùa vụ, loại yêu cầu, nhân sự và sự kiện khác có thể gây khác biệt. |
| **A/B test hoặc nhóm so sánh hợp lý** | Có lưu lượng đủ lớn, phân nhóm phù hợp và tác động có thể đo | Cần thiết kế kiểm soát, đủ dữ liệu, tránh ảnh hưởng chéo và bảo vệ người dùng. |
| **Đo liên tục trên bảng công việc** | Cải tiến dòng công việc nội bộ | Cần thống nhất cách ghi trạng thái và theo dõi đủ lâu để thấy xu hướng. |

Không nên chọn A/B test chỉ vì “nghe có vẻ khoa học”. Với lượng người dùng thấp hoặc rủi ro cao, dùng thử có giám sát, kiểm thử kỹ thuật, đối chiếu nhóm tương đồng và nghiên cứu định tính có thể phù hợp hơn.

### 5.4. Bước 4 — Quy định cách ra quyết định trước

Một thỏa thuận kiểm tra tối thiểu có thể ghi:

| Trường | Ví dụ |
| --- | --- |
| Mục tiêu | Giảm nhu cầu hỏi lại tiến độ hỗ trợ |
| Giả thuyết | Trang trạng thái rõ ràng giúp người gửi tự theo dõi |
| Đối tượng | Một bộ phận tham gia pilot, với quyền hỗ trợ như trước |
| Phạm vi quan sát | Các yêu cầu mới trong hai tuần; theo dõi đủ 7 ngày mỗi yêu cầu |
| Chỉ số chính | Tỷ lệ yêu cầu có ít nhất một câu hỏi lại về tiến độ |
| Chỉ số bảo vệ | Thời gian giải quyết, tỷ lệ mở lại yêu cầu, khiếu nại |
| Bằng chứng định tính | Quan sát cách người dùng giải thích trạng thái, phỏng vấn ngắn |
| Quyết định dự kiến | Mở rộng có kiểm soát / sửa rồi thử lại / dừng |
| Người tổng hợp | Product Owner hoặc người được nhóm thống nhất |

Với mẫu rất nhỏ, nhóm nên đặt tiêu chí ra quyết định theo cách **khám phá**: có tín hiệu sử dụng hữu ích, không xuất hiện lỗi đáng kể, và đã hiểu các khó khăn chính. Không nên tạo ấn tượng chắc chắn bằng một ngưỡng phần trăm tùy ý.

## 6. Ví dụ đầy đủ: kiểm tra kết quả rồi điều chỉnh backlog

Một nhóm xây hệ thống hỗ trợ nội bộ đã phát hành cho một phòng ban chức năng **xem trạng thái yêu cầu**. Trước khi làm, nhóm tin rằng nhiều cuộc nhắn hỏi lặp lại xuất phát từ việc người gửi không biết yêu cầu đang ở đâu.

### 6.1. Dữ liệu quan sát minh họa

Giả sử nhóm thu thập được dữ liệu sau, với cùng định nghĩa sự kiện và phạm vi người dùng tương đối giống nhau:

| Chỉ số | Trước thay đổi | Giai đoạn thử | Diễn giải ban đầu |
| --- | ---: | ---: | --- |
| Yêu cầu đủ điều kiện quan sát | 120 | 120 | Hai giai đoạn có cùng số yêu cầu, nhưng chưa biết cơ cấu yêu cầu có giống nhau không. |
| Yêu cầu có nhắn hỏi lại trạng thái | 36 | 18 | Tỷ lệ giảm từ 30% xuống 15%. |
| Thời gian giải quyết trung vị | 20 giờ | 29 giờ | Có dấu hiệu chờ giải quyết lâu hơn. |
| Yêu cầu bị mở lại sau khi đóng | 6 | 9 | Tỷ lệ tăng từ 5% lên 7,5%. |
| Phỏng vấn nhanh | Người dùng thường phải hỏi nhân viên | Một số người hiểu trạng thái, một số vẫn không rõ bước tiếp theo | Cần tìm hiểu mức độ rõ ràng của thông tin và kỳ vọng phản hồi. |

Từ số liệu minh họa:

- Trước: **36 / 120 = 30%** yêu cầu phát sinh hỏi lại trạng thái.
- Sau: **18 / 120 = 15%** yêu cầu phát sinh hỏi lại trạng thái.
- Chênh lệch quan sát: **giảm 15 điểm phần trăm**; đây là khác biệt giữa hai tỷ lệ, không phải giảm “15% tương đối”.
- Tỷ lệ mở lại: **6 / 120 = 5%** trước và **9 / 120 = 7,5%** sau, tăng **2,5 điểm phần trăm**.
- Thời gian giải quyết trung vị tăng từ **20 giờ** lên **29 giờ**; cần xem phân bố, loại yêu cầu và điểm nghẽn.

**Lưu ý:** toàn bộ số liệu ở bảng là **dữ liệu giả định để học cách phân tích**, không phải kết quả nghiên cứu thật. Việc hai giai đoạn có cùng 120 yêu cầu **không** làm chúng trở thành hai nhóm tương đương hoặc chứng minh tính nhân quả.

### 6.2. Điều dữ liệu cho phép kết luận

Nhóm có thể nói:

> Trong hai khoảng thời gian được quan sát, tỷ lệ yêu cầu có hỏi lại trạng thái giảm, nhưng thời gian giải quyết trung vị và tỷ lệ mở lại tăng. Các tín hiệu này cần được giải thích trước khi quyết định phát hành rộng.

Nhóm **chưa** thể khẳng định:

- “Tính năng mới chắc chắn làm giảm một nửa số câu hỏi”: có thể giai đoạn sau gồm nhiều yêu cầu đơn giản hơn, kênh nhắn hỏi thay đổi hoặc cách ghi nhận bỏ sót sự kiện.
- “Tính năng mới gây chậm xử lý”: thời gian chậm có thể đến từ thiếu nhân sự, sự cố độc lập hoặc cơ cấu yêu cầu khó hơn.
- “Người dùng chắc chắn hài lòng hơn”: giảm hỏi lại có thể do họ tìm thấy thông tin, nhưng cũng có thể do họ không tìm được nơi hỏi.

**Bằng chứng tiếp theo nên thu thập:** phân loại yêu cầu theo độ khó; so sánh thời gian ở từng trạng thái; kiểm tra kênh hỗ trợ có thay đổi không; quan sát cách người dùng diễn giải trạng thái; phỏng vấn nhân viên về số lần chờ người có quyền duyệt.

### 6.3. Quyết định thích ứng có trách nhiệm

Một quyết định hợp lý có thể là:

1. **Giữ pilot giới hạn** trong khi kiểm tra chất lượng và số liệu bổ sung; chưa xem giảm số lần hỏi lại là bằng chứng đủ để mở toàn công ty.
2. **Ưu tiên làm rõ thông báo trạng thái**: với yêu cầu đang chờ, nêu rõ ai xử lý tiếp, người gửi cần làm gì và khi nào có cập nhật theo quy định thực tế.
3. **Điều tra điểm nghẽn ở khâu giải quyết**: xem thời gian chờ, phân công, tiêu chí đóng yêu cầu và nguyên nhân mở lại.
4. **Thử một cải tiến nhỏ**, ví dụ cho phép người phụ trách cập nhật trạng thái khi chuyển bước; theo dõi cùng bộ chỉ số trong vòng tiếp theo.
5. **Ấn định buổi kiểm tra lại** và người tổng hợp; quyết định mở rộng, điều chỉnh tiếp hoặc dừng dựa trên bằng chứng mới.

Tư duy thực nghiệm không có nghĩa “luôn đổi kế hoạch”. Nó giúp nhóm **thay đổi có lý do**, đồng thời biết khi nào chưa có đủ thông tin để quyết định.

## 7. Kết hợp bằng chứng định lượng và định tính

### 7.1. Dữ liệu định lượng: thấy quy mô và xu hướng

Dữ liệu định lượng có ích khi câu hỏi liên quan tỷ lệ, thời gian, tần suất, phân bố hoặc mức độ thay đổi. Ví dụ: bao nhiêu yêu cầu bị mở lại, thời gian ở trạng thái “chờ xác nhận” bao lâu, luồng tạo yêu cầu có tỷ lệ lỗi ra sao.

Khi đọc số liệu cần xem:

- **Tử số, mẫu số và đơn vị:** 8 lỗi trong 20 yêu cầu khác xa 8 lỗi trong 20.000 yêu cầu.
- **Khoảng thời gian:** dữ liệu trong ngày khác dữ liệu theo tháng, nhất là khi số lượng việc thay đổi.
- **Độ phân tán:** trung bình có thể che khuất một số yêu cầu chờ rất lâu; trung vị và phân vị giúp nhìn rõ hơn.
- **Phân nhóm hợp lý:** người dùng mới/cũ, loại yêu cầu, độ ưu tiên, thiết bị hoặc kênh hỗ trợ.
- **Chất lượng dữ liệu:** sự kiện thiếu, ghi trùng, trạng thái được cập nhật muộn, múi giờ, quyền truy cập và thay đổi định nghĩa.
- **Tác động ngoài phép thử:** ngày nghỉ, chương trình đào tạo, thay đổi nhân sự, sự cố hệ thống, các tính năng khác ra cùng lúc.

Không nên tùy tiện chia dữ liệu thành rất nhiều nhóm đến khi tìm được một con số “đẹp”, rồi trình bày nó như một kết luận đã được xác nhận.

### 7.2. Dữ liệu định tính: hiểu nguyên nhân và ngữ cảnh

Những câu hỏi trung lập khi phỏng vấn người dùng:

- “Lần gần nhất bạn cần kiểm tra tiến độ yêu cầu, bạn đã làm gì?”
- “Bạn hiểu trạng thái ‘đang xử lý’ như thế nào?”
- “Ở bước nào bạn cần thêm thông tin để tiếp tục?”
- “Bạn kỳ vọng điều gì sẽ xảy ra sau khi gửi yêu cầu?”
- “Có tình huống nào màn hình này vẫn không giải quyết được vấn đề của bạn?”

Tránh dẫn dắt bằng câu “Tính năng mới tiện hơn đúng không?”. Hãy quan sát người dùng **làm gì** và hỏi họ **đã hiểu điều gì**. Ghi các trích dẫn, tình huống, lỗi và bước họ dừng lại; tổng hợp thành các mẫu vấn đề cần kiểm tra tiếp, không biến một câu nói đơn lẻ thành kết luận về tất cả người dùng.

### 7.3. Khi hai nguồn bằng chứng mâu thuẫn

Ví dụ dashboard cho thấy lượt mở trang trạng thái tăng nhưng phỏng vấn cho biết người dùng vẫn phải gọi nhân viên. Hai nguồn không nhất thiết sai: người dùng có thể mở trang **nhiều lần vì chưa tìm thấy câu trả lời**.

Nhóm nên đặt câu hỏi mới: “Trang được xem nhiều vì hữu ích hay vì thông tin chưa đủ rõ?”. Sau đó kiểm tra số lần quay lại, quan sát thao tác và đối chiếu câu hỏi hỗ trợ. Bằng chứng mâu thuẫn thường là cơ hội đào sâu vấn đề chứ không phải lý do chọn bỏ nguồn mình không thích.

## 8. Kiểm tra dòng công việc để cải tiến cách phối hợp

Tư duy thực nghiệm không chỉ áp dụng cho sản phẩm. Nhóm cũng cần kiểm tra **cách công việc chảy từ lúc bắt đầu đến khi hoàn thành**, vì thời gian chờ và lỗi phối hợp làm chậm phản hồi khách hàng.

### 8.1. Bốn chỉ số thực hành

| Chỉ số | Định nghĩa cần thống nhất | Hành động có thể rút ra |
| --- | --- | --- |
| **WIP (Work in Progress)** | Số hạng mục đã bắt đầu nhưng chưa hoàn tất trong phạm vi theo dõi | Giảm việc bắt đầu mới, ưu tiên hoàn thành việc đang mắc. |
| **Work item age** | Tuổi của một hạng mục đang làm: thời gian từ lúc bắt đầu đến thời điểm hiện tại | Chú ý các hạng mục sắp vượt mức chờ thông thường, gỡ tắc sớm. |
| **Cycle time** | Thời gian từ lúc bắt đầu xử lý một hạng mục đến khi hoàn tất theo cùng quy ước | Kiểm tra phân bố thời gian, tìm giai đoạn chờ lâu. |
| **Throughput** | Số hạng mục hoàn tất mỗi đơn vị thời gian | Theo dõi tốc độ hoàn tất thực tế, không đánh giá riêng lẻ một tuần. |

**Lead time** cũng hữu ích khi đo từ lúc yêu cầu đi vào điểm ghi nhận đã thỏa thuận đến lúc được đáp ứng. Phải nêu rõ hai mốc, vì các nhóm có thể sử dụng cách định nghĩa khác nhau.

Ví dụ một bảng Kanban:

~~~text
Backlog → Sẵn sàng → Đang làm (WIP 3) → Kiểm tra (WIP 2) → Hoàn tất
                                      ↑
                              Yêu cầu bị chờ review
~~~

Nhóm quan sát thấy bốn hạng mục liên tục phải chờ ở “Kiểm tra”, trong khi mọi người vẫn kéo thêm việc mới vào “Đang làm”. Giả thuyết cải tiến có thể là: “Nếu nhóm ưu tiên review các hạng mục đang chờ và tạm không bắt đầu việc mới khi WIP đầy, cycle time sẽ giảm mà tỷ lệ lỗi không tăng”.

### 8.2. Ví dụ tính cycle time

Giả sử sáu hạng mục hoàn tất trong một tuần có cycle time lần lượt là **2, 3, 4, 5, 8 và 12 ngày**:

- **Throughput** tuần quan sát = **6 hạng mục/tuần**.
- **Trung bình cycle time** = (2 + 3 + 4 + 5 + 8 + 12) / 6 = **34/6 ≈ 5,7 ngày/hạng mục**.
- **Trung vị cycle time** = (4 + 5) / 2 = **4,5 ngày**.
- Hai hạng mục 8 và 12 ngày đáng được phân tích nguyên nhân chờ, nhưng chưa đủ cơ sở nói ai làm việc kém.

Các số là ví dụ học tập. Một tuần không đủ để rút ra xu hướng bền vững, và cycle time của các việc khác loại, kích thước rất khác nhau cần được diễn giải thận trọng. Có thể xem thêm **biểu đồ phân tán cycle time theo ngày hoàn tất**, biểu đồ WIP hoặc một số phân vị để đánh giá tính ổn định.

### 8.3. Cải tiến bằng một thử nghiệm vận hành

Nhóm thống nhất thử trong hai tuần:

1. Giữ giới hạn WIP công khai: tối đa ba hạng mục “Đang làm”, hai hạng mục “Kiểm tra”.
2. Nếu cột “Kiểm tra” đầy, ưu tiên cùng xử lý hạng mục chờ review trước khi nhận việc mới.
3. Ghi lại tuổi các hạng mục đang làm, nguyên nhân tắc nghẽn và cycle time khi hoàn tất.
4. Theo dõi thêm lỗi sau phát hành để bảo đảm việc đẩy nhanh luồng không làm giảm chất lượng.
5. Cuối đợt thử, so sánh với dữ liệu nền có cùng định nghĩa và quyết định giữ, thay đổi hoặc bỏ giới hạn đang thử.

Nếu throughput giảm trong tuần đầu khi nhóm dọn công việc dở dang, chưa thể kết luận chính sách thất bại. Cần nhìn toàn bộ tác động đến WIP, độ tuổi công việc, tính ổn định, chất lượng và nhịp giao giá trị qua đủ thời gian quan sát.

## 9. Áp dụng trong Scrum, Kanban và XP

### 9.1. Scrum: kiểm tra và điều chỉnh ở nhiều nhịp

Các sự kiện Scrum tạo cơ hội chính thức để kiểm tra và thích ứng, nhưng chúng chỉ hữu ích khi dựa trên hiện trạng minh bạch:

| Nhịp làm việc | Điều được kiểm tra | Kiểu điều chỉnh |
| --- | --- | --- |
| **Sprint Planning** | Product Goal, thứ tự backlog, năng lực và điều đã học trước đó | Chọn Sprint Goal và kế hoạch khả thi cho Sprint. |
| **Daily Scrum** | Tiến độ hướng tới Sprint Goal, công việc bị cản trở | Developers điều chỉnh kế hoạch cho ngày tiếp theo. |
| **Sprint Review** | Increment, thay đổi thị trường/nghiệp vụ, phản hồi bên liên quan | Điều chỉnh hướng phát triển và Product Backlog khi cần. |
| **Sprint Retrospective** | Chất lượng, hiệu quả, phối hợp, quy trình và công cụ | Chọn hành động cải tiến cách làm việc cho Sprint tiếp theo. |

Một lỗi thường gặp là biến Sprint Review thành buổi báo cáo tiến độ bằng slide. Để kiểm tra giá trị, cần đưa ra **Increment thực sự sử dụng được**, xem phản hồi từ những người liên quan và thảo luận điều nhóm nên làm tiếp.

Ngược lại, Retrospective tập trung vào **cách nhóm làm việc**. Ví dụ: “Chúng ta mất quá nhiều thời gian đợi môi trường kiểm thử” nên dẫn đến thử nghiệm cải thiện cách tạo môi trường hoặc phối hợp, rồi đo tác động của thử nghiệm.

Scrum không yêu cầu chờ đến sự kiện cuối Sprint mới được xử lý thông tin quan trọng. Khi có lỗi nghiêm trọng hoặc bằng chứng mới, nhóm cần trao đổi và thích ứng phù hợp, đồng thời vẫn tôn trọng mục tiêu Sprint và chất lượng.

### 9.2. Kanban: kiểm tra luồng và điều chỉnh chính sách

Trong cách quản lý dòng công việc theo Kanban, minh bạch bắt đầu bằng bảng việc và **chính sách rõ ràng**: lúc nào được kéo hạng mục, tiêu chuẩn chuyển cột, giới hạn WIP, cách xử lý việc gấp và thế nào là “hoàn tất”.

Nhóm kiểm tra các hạng mục già nhất, thời gian chờ và phân bố cycle time; sau đó thử thay đổi chính sách theo vấn đề quan sát được. Giới hạn WIP không phải công thức cố định: nó là một chính sách có thể điều chỉnh khi bằng chứng cho thấy luồng quá tải hoặc không sử dụng hết khả năng.

### 9.3. XP: kiểm tra bằng phản hồi kỹ thuật nhanh

Các thực hành kỹ thuật như **test-driven development (TDD)**, **pair programming**, **continuous integration** và **refactoring** giúp nhóm nhận phản hồi sớm về tính đúng đắn và khả năng thay đổi của mã.

Ví dụ:

~~~text
Viết kiểm thử cho quy tắc phân quyền → Kiểm thử thất bại như dự kiến
→ Viết mã tối thiểu để đạt kiểm thử → Chạy kiểm thử tự động
→ Cải thiện cấu trúc mã mà giữ nguyên hành vi → Tích hợp thay đổi
~~~

Kiểm thử tự động cung cấp bằng chứng về **những hành vi được kiểm tra trong điều kiện thử**; nó không chứng minh người dùng thích tính năng hay mọi lỗi đã được loại bỏ. Nhóm cần kết hợp phản hồi kỹ thuật với phản hồi sản phẩm và theo dõi vận hành.

## 10. Ra quyết định khi bằng chứng chưa hoàn hảo

Trong thực tế, dữ liệu hiếm khi đầy đủ. Nếu đòi hỏi chắc chắn tuyệt đối, nhóm không thể thích ứng kịp; nếu thay đổi theo mỗi tín hiệu nhỏ, nhóm sẽ liên tục chạy theo nhiễu.

### 10.1. Chọn hành động theo mức rủi ro và khả năng đảo ngược

| Tình huống | Cách xử lý hợp lý |
| --- | --- |
| Lỗi nghiêm trọng đang ảnh hưởng người dùng | Ưu tiên bảo vệ người dùng và ổn định hệ thống; không chờ thêm dữ liệu thử nghiệm để hành động cần thiết. |
| Tín hiệu cải thiện rõ, rủi ro thấp, có thể quay lại | Mở rộng thử từng bước và tiếp tục quan sát. |
| Số liệu tốt hơn nhưng chỉ số chất lượng xấu đi | Điều tra nguyên nhân, khắc phục hoặc giữ pilot giới hạn trước khi mở rộng. |
| Phản hồi mâu thuẫn, mẫu nhỏ | Thu thập thêm bằng chứng có mục tiêu; cân nhắc thử nghiệm nhỏ và an toàn. |
| Không thấy thay đổi đáng kể sau phạm vi thử hợp lý | Xem lại giả thuyết, thiết kế thử nghiệm hoặc dừng giải pháp để ưu tiên việc khác. |

Một quyết định dựa trên bằng chứng không bắt buộc là “có” hoặc “không”. Đôi khi quyết định đúng là **thu hẹp phạm vi**, **thử lại có điều chỉnh**, **duy trì hiện trạng để đo thêm**, hoặc **dừng đầu tư**.

### 10.2. Phân biệt tương quan và nguyên nhân

Nếu thời gian giải quyết yêu cầu giảm sau khi nhóm thêm dashboard, không có nghĩa dashboard đã **gây ra** toàn bộ cải thiện. Cùng thời gian đó, nhóm có thể vừa tuyển thêm người, thay nhà cung cấp hạ tầng hoặc nhận ít yêu cầu phức tạp hơn.

Khi trình bày kết luận, dùng câu có độ chắc chắn phù hợp:

- Có căn cứ: “Trong giai đoạn thử, thời gian giải quyết trung vị giảm từ 24 xuống 18 giờ.”
- Cần điều tra thêm: “Việc bổ sung dashboard **có thể** góp phần làm giảm thời gian chờ.”
- Không có đủ căn cứ: “Dashboard chắc chắn giúp tăng năng suất nhóm 25%.”

Nếu phép thử có phân nhóm đủ tốt và dữ liệu đủ để đánh giá, có thể nói mạnh hơn về tác động của thay đổi. Nhưng thiết kế nghiên cứu và giới hạn kết luận vẫn cần được giải thích rõ.

### 10.3. Ghi lại quyết định để vòng sau kiểm tra được

Một **nhật ký quyết định (decision log)** ngắn giúp tránh việc lần nào nhóm cũng tranh luận lại từ đầu:

~~~text
Ngày kiểm tra: [ngày]
Mục tiêu / giả thuyết: [điều cần kiểm chứng]
Phạm vi đã quan sát: [đối tượng, thời gian, mốc dữ liệu]
Kết quả: [quan sát định lượng + định tính]
Giới hạn bằng chứng: [thiếu dữ liệu, biến số ngoài, mẫu nhỏ...]
Quyết định: [giữ / mở rộng / sửa / thử tiếp / dừng]
Lý do: [liên hệ giá trị, chất lượng và rủi ro]
Hành động tiếp theo: [việc cụ thể, người chịu trách nhiệm]
Ngày xem lại: [mốc hẹn]
Điều kiện đổi quyết định: [bằng chứng cần thấy]
~~~

Nhật ký không cần dài. Mục tiêu là giữ lại **lập luận và điều kiện có thể thay đổi lập luận** để nhóm học từ quyết định thực tế.

## 11. Những sai lầm thường gặp

| Sai lầm | Vì sao gây hại | Cách sửa |
| --- | --- | --- |
| Chỉ đo số story hoàn thành, số giờ làm, số commit | Những số này không nói trực tiếp người dùng được lợi gì | Gắn đầu ra với kết quả người dùng và chất lượng. |
| Lấy một lời khen làm bằng chứng sản phẩm đã phù hợp | Người trả lời có thể không đại diện cho người dùng mục tiêu | Quan sát hành vi, phỏng vấn nhiều vai trò, tìm tình huống trái chiều. |
| Chỉ báo cáo số liệu thuận lợi | Quyết định bỏ qua rủi ro và tác động không mong muốn | Báo cùng lúc chỉ số chính, chỉ số bảo vệ và giới hạn. |
| Không xác định mẫu số và mốc đo | Hai giai đoạn không thể so sánh đáng tin cậy | Ghi định nghĩa, nguồn, thời gian và phạm vi đo. |
| Đổi nhiều yếu tố cùng lúc | Khó biết yếu tố nào liên quan kết quả | Thử thay đổi nhỏ, tách từng giả thuyết khi có thể. |
| Cứ có số liệu là cho rằng đã hiểu nguyên nhân | Tương quan dễ bị nhầm thành nhân quả | Tìm bằng chứng bổ sung và xét yếu tố tác động khác. |
| Đợi đến cuối dự án mới hỏi người dùng | Phát hiện hiểu sai quá muộn | Giao Increment nhỏ và lấy phản hồi sớm, đều đặn. |
| Retrospective chỉ nêu vấn đề mà không theo dõi | Nhóm lặp lại cùng khó khăn | Chọn một cải tiến có chủ sở hữu, thước đo, ngày xem lại. |
| Giảm WIP bằng cách đánh dấu việc chưa xong là “Done” | Chỉ số đẹp lên nhưng hệ thống mất minh bạch | Dùng Definition of Done nhất quán và kiểm tra chất lượng. |
| Cố chứng minh giả thuyết ban đầu đúng | Dữ liệu bị diễn giải thiên lệch | Chủ động tìm dấu hiệu phản bác và chuẩn bị phương án đổi hướng. |

Đặc biệt, đừng dùng số liệu dòng công việc để quy lỗi cá nhân. Cycle time của một story dài có thể bắt nguồn từ phụ thuộc, môi trường kiểm thử, yêu cầu đổi hoặc quyết định ưu tiên. Câu hỏi thực nghiệm là **hệ thống làm việc đang tạo ra khó khăn ở đâu và nhóm có thể cải thiện điều gì**.

## 12. Bài thực hành: kiểm tra một cải tiến trong nhóm hỗ trợ

### 12.1. Bối cảnh

Nhóm hỗ trợ nội bộ vừa thử hiển thị trạng thái yêu cầu rõ ràng hơn. Họ muốn biết người dùng có bớt hỏi lại tiến độ mà chất lượng hỗ trợ không suy giảm hay không.

Dữ liệu **giả định** từ hai đợt quan sát, dùng cùng quy tắc đếm:

| Chỉ số | Đợt A (trước) | Đợt B (sau) |
| --- | ---: | ---: |
| Yêu cầu được theo dõi đủ 7 ngày | 40 | 50 |
| Yêu cầu có ít nhất một lần hỏi lại trạng thái | 12 | 10 |
| Thời gian giải quyết trung vị | 10 giờ | 14 giờ |
| Yêu cầu bị mở lại sau khi đóng | 2 | 5 |
| Người dùng nói “không hiểu bước tiếp theo” trong phỏng vấn | 3 trong 8 người | 2 trong 8 người |

### 12.2. Nhiệm vụ

1. Tính tỷ lệ yêu cầu hỏi lại trạng thái của hai đợt. Giải thích chênh lệch bằng **điểm phần trăm**.
2. Xác định ít nhất hai chỉ số bảo vệ chất lượng có tín hiệu cần chú ý.
3. Viết **hai điều biết được** và **hai điều chưa thể kết luận** từ bảng.
4. Nêu ba câu hỏi cần phỏng vấn để tìm hiểu vì sao người dùng tiếp tục hỏi lại.
5. Đề xuất một thay đổi nhỏ cho vòng tiếp theo; ghi rõ cách kiểm tra và điều kiện giữ/dừng.
6. Chỉ ra kết quả sẽ ảnh hưởng thế nào đến thứ tự Product Backlog hoặc chính sách vận hành của nhóm.

### 12.3. Gợi ý tự kiểm tra

- Tỷ lệ hỏi lại: **A = 12/40 = 30%**, **B = 10/50 = 20%**. Chênh lệch quan sát được là **giảm 10 điểm phần trăm**, không phải khẳng định tất cả người dùng đã hài lòng hơn.
- Thời gian giải quyết trung vị tăng **10 → 14 giờ**; tỷ lệ mở lại tăng **2/40 = 5% → 5/50 = 10%**. Hai dấu hiệu này cần điều tra trước khi mở rộng.
- Có thể nói **trong mẫu quan sát**, tỷ lệ hỏi lại giảm. Chưa thể khẳng định chức năng mới trực tiếp tạo ra sự thay đổi hoặc giải pháp nên triển khai cho toàn bộ tổ chức.
- Một phép thử tiếp theo: làm rõ “người phụ trách – hành động tiếp theo – thời gian cập nhật dự kiến” trên trang trạng thái, giữ nguyên kênh liên hệ hỗ trợ; quan sát một nhóm người dùng tiếp theo và theo dõi lại tỷ lệ hỏi lại, thời gian giải quyết và tỷ lệ mở lại.
- Nếu điều chỉnh giúp người dùng hiểu trạng thái tốt hơn **và** các chỉ số bảo vệ không xấu đi, có thể mở rộng thận trọng. Nếu không, xem lại giả thuyết hoặc giải quyết điểm nghẽn xử lý trước.

Khi đánh giá bài làm, quan trọng nhất không phải chọn cùng một giải pháp với người khác mà là **lập luận rõ từ dữ liệu đến quyết định** và biết thừa nhận giới hạn bằng chứng.

## 13. Mẫu tổ chức một phiên kiểm tra và thích ứng 30 phút

Đây là cấu trúc gợi ý cho một buổi kiểm tra kết quả ngắn. Nhóm có thể tích hợp vào Sprint Review, Retrospective hoặc nhịp xem dòng việc; không cần tạo thêm cuộc họp nếu đã có nơi phù hợp.

| Thời lượng | Hoạt động | Câu hỏi dẫn dắt |
| --- | --- | --- |
| 5 phút | Nhắc lại mục tiêu và giả thuyết | Điều chúng ta định cải thiện là gì? |
| 8 phút | Xem kết quả quan sát | Chỉ số chính, phản hồi và chỉ số bảo vệ cho thấy điều gì? |
| 7 phút | Tìm chênh lệch và giới hạn | Điều gì khác kỳ vọng? Có thể còn nguyên nhân nào? |
| 7 phút | Chọn một điều chỉnh nhỏ | Việc gì đáng thử nhất, ai phụ trách, giảm rủi ro thế nào? |
| 3 phút | Chốt cách đo vòng tiếp theo | Khi nào kiểm tra lại, điều gì khiến ta giữ hoặc đổi quyết định? |

Ví dụ ghi nhận cuối buổi:

> **Quan sát:** số lần hỏi lại tiến độ giảm nhưng thời gian giải quyết tăng. **Giả thuyết mới:** người dùng tự xem trạng thái dễ hơn, trong khi hạng mục bị tắc ở bước phân công. **Thay đổi:** thử quy tắc phân công rõ người chịu trách nhiệm trong vòng 48 giờ đầu và cải thiện thông báo trạng thái. **Kiểm tra tiếp:** xem thời gian chờ phân công, tỷ lệ hỏi lại, tỷ lệ mở lại; xem kết quả sau hai tuần. **Điều kiện dừng:** nếu xuất hiện lỗi phân quyền, mất yêu cầu hoặc chất lượng giảm đáng kể, xử lý ngay thay vì chờ đủ thời hạn.

Thay đổi ở đây chỉ là **giả thuyết cải tiến**, chưa phải kết luận rằng phân công thực sự là nguyên nhân. Nhóm nên kiểm tra dữ liệu thời gian chờ và phản hồi nhân viên trước khi mở rộng chính sách.

## 14. Checklist trước và sau mỗi vòng kiểm chứng

**Trước khi bắt đầu:**

- [ ] Mục tiêu liên hệ đến giá trị người dùng hoặc khả năng giao phần mềm an toàn.
- [ ] Giả định và giả thuyết được phát biểu sao cho có thể kiểm tra, kể cả khả năng giả thuyết sai.
- [ ] Xác định rõ người dùng/nhóm công việc, phạm vi thử và điều kiện an toàn.
- [ ] Có baseline hoặc ghi rõ lý do chưa có baseline.
- [ ] Chỉ số chính, chỉ số bảo vệ, cách đếm và nguồn dữ liệu được thống nhất.
- [ ] Có kế hoạch kết hợp quan sát định lượng và phản hồi định tính khi cần.
- [ ] Người phụ trách thu thập kết quả và thời điểm xem lại đã rõ.

**Khi kiểm tra kết quả:**

- [ ] Tách dữ kiện quan sát với cách giải thích và suy đoán nguyên nhân.
- [ ] Đối chiếu mẫu số, thời gian, thay đổi ngữ cảnh và chất lượng dữ liệu.
- [ ] Xem cả kết quả mong muốn và tác dụng phụ ngoài dự kiến.
- [ ] Ghi nhận bằng chứng trái chiều và những điều chưa thể kết luận.
- [ ] Đưa ra quyết định cụ thể: giữ, mở rộng, điều chỉnh, thử tiếp hoặc dừng.
- [ ] Cập nhật backlog, cách làm hoặc kỹ thuật theo quyết định.
- [ ] Ghi ngày xem lại và tiêu chí đánh giá tác động của chính thay đổi vừa chọn.

Tư duy thực nghiệm được thể hiện qua một chuỗi hành động có thể quan sát: **minh bạch mục tiêu và trạng thái → kiểm tra sản phẩm hoặc dòng việc bằng bằng chứng phù hợp → diễn giải có giới hạn → thích ứng có chủ đích → kiểm tra lại tác động**. Nhờ đó, nhóm Agile liên tục học từ phản hồi sớm, giao những phần sản phẩm có giá trị và cải thiện cách phối hợp theo thực tế, thay vì giữ kế hoạch chỉ vì đó là kế hoạch ban đầu.
