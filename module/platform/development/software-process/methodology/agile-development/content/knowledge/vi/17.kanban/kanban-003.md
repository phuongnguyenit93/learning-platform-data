# Trực quan hóa trạng thái, hàng đợi và công việc bị chặn

Trong phát triển phần mềm Agile, rất dễ nhầm **mọi người đều đang bận** với **giá trị đang được bàn giao đều đặn**. Một nhóm có thể viết nhiều mã, mở hàng chục yêu cầu, báo cáo từng người hoàn thành 80% công việc, nhưng người dùng vẫn phải đợi lâu để nhận được một cải tiến nhỏ. Nguyên nhân thường không nằm ở tốc độ gõ mã: công việc đang **xếp hàng chờ kiểm thử, chờ người quyết định quy tắc nghiệp vụ, chờ môi trường triển khai hoặc bị chặn bởi một phụ thuộc không ai nhìn thấy**.

**Kanban** hỗ trợ giải quyết vấn đề bằng cách **trực quan hóa quy trình làm việc và dòng chảy của các hạng mục**. Thay vì chỉ liệt kê task cần làm, một bảng Kanban hữu ích trả lời:

- Hạng mục nào đang ở **trạng thái** nào của quy trình thực tế?
- Việc nào đang được **xử lý**, việc nào chỉ **xếp hàng chờ**?
- Việc nào **bị chặn**, từ khi nào, bởi điều gì và ai có thể giúp tháo gỡ?
- Có bao nhiêu việc đang làm dở (**WIP**) so với năng lực hoàn tất của nhóm?
- Nút thắt nào khiến người dùng phải chờ lâu hơn thời gian thực sự làm việc?
- Nhóm nên **hoàn tất việc nào trước khi bắt đầu việc mới**?

Chủ đề này thuộc chương **Kanban** của mô-đun **AGILE_DEVELOPMENT**: phát triển thích ứng bằng phản hồi sớm, bàn giao tăng dần, phối hợp dựa trên user story/backlog, thực hành Scrum, Kanban, XP và cải tiến liên tục nhờ đo lường dòng công việc.

**Mục tiêu học tập:** Sau bài này, bạn có thể thiết kế bảng thể hiện trung thực luồng làm việc, phân biệt trạng thái với hàng đợi và tình trạng blocked, định nghĩa chính sách chuyển cột, sử dụng giới hạn WIP, đọc các tín hiệu nghẽn, và thực hành điều chỉnh bảng Kanban dựa trên bằng chứng.

## 1. Kanban là cách quản lý dòng công việc, không chỉ là bảng ba cột

Một bảng “To do – Doing – Done” có thể là điểm khởi đầu, nhưng không đủ nếu công việc thực tế đi qua nhiều thời điểm chờ. Ví dụ, một tính năng đã viết mã nhưng cần đợi bốn ngày mới được review, hai ngày mới được kiểm thử và thêm ba ngày mới được triển khai. Gắn mọi khoảng chờ vào cột **Doing** khiến nhóm chỉ thấy “đang làm lâu” mà không hiểu **đang làm gì hay đang chờ ai**.

Kanban hữu ích khi nhóm chủ động:

1. **Xác định và trực quan hóa workflow:** Công việc đi từ đâu, qua những bước nào và kết thúc ở đâu?
2. **Kiểm soát WIP:** Không mở quá nhiều hạng mục cùng lúc so với khả năng hoàn thành.
3. **Quản lý dòng công việc:** Quan sát thời gian chờ, công việc già đi, nút thắt và cách hoàn tất.
4. **Minh bạch chính sách:** Mọi người hiểu điều kiện nhận việc, chuyển trạng thái và xử lý ngoại lệ.
5. **Thiết lập vòng phản hồi:** Kiểm tra công việc và dữ liệu thường xuyên để quyết định.
6. **Cải tiến từ trải nghiệm:** Thử những thay đổi nhỏ, đo tác động rồi điều chỉnh.

Những nguyên tắc này không yêu cầu đội phải dùng một công cụ hay sơ đồ cố định. **Bảng là mô hình của quy trình thật**, không phải vật trang trí hay chỉ là công cụ báo cáo cấp trên.

### Luồng công việc khác danh sách công việc như thế nào?

| Danh sách đơn thuần | Bảng Kanban thể hiện dòng chảy |
| --- | --- |
| “Có 40 ticket cần làm.” | “Có 12 đề xuất chưa chọn, 3 việc sẵn sàng, 2 đang phát triển và 5 việc đang chờ review.” |
| “Story X được giao cho A.” | “Story X đang chờ kiểm thử tích hợp từ thứ Ba; chưa có năng lực kiểm thử.” |
| “Đã đóng 10 ticket.” | “Đã bàn giao 10 hạng mục; thời gian chờ review đang tăng, lỗi sau bàn giao có xu hướng giảm.” |
| “Mọi người đã bắt đầu việc mới.” | “Có thể kéo việc mới chỉ khi workflow còn năng lực WIP và các việc đang chờ không cần được hỗ trợ trước.” |

**Trực quan hóa đúng** làm nổi bật điều cần quyết định, không chỉ trình bày trạng thái đẹp mắt.

## 2. Bắt đầu từ ranh giới của workflow

Trước khi tạo cột, nhóm cần thống nhất **một hạng mục công việc đi từ đâu đến đâu**. Ví dụ:

> Với một nhóm phát triển nền tảng học trực tuyến, luồng đang quản lý bắt đầu khi một Product Backlog Item **được chọn để thực hiện**, và kết thúc khi thay đổi **được bàn giao theo chính sách chất lượng và phát hành đã thống nhất**.

Đây chỉ là **một quy ước minh họa**. Nhóm khác có thể tính từ khi yêu cầu được tiếp nhận hoặc đến lúc người dùng bắt đầu sử dụng, miễn thống nhất mốc để dữ liệu không bị hiểu sai.

### Phân biệt ba khu vực công việc

| Khu vực | Ví dụ | Điều cần hiểu |
| --- | --- | --- |
| **Ý tưởng / đầu vào chưa cam kết** | Phản hồi người dùng, ticket hỗ trợ, đề xuất cải tiến | Không phải tất cả đều sẽ được làm |
| **Nguồn công việc được ưu tiên** | Product Backlog hoặc hàng chờ đã đánh giá, sắp thứ tự | Thể hiện công việc có thể chọn; ưu tiên có thể thay đổi |
| **Workflow thực hiện** | Sẵn sàng → Phát triển → Review → Kiểm thử → Bàn giao | Cho thấy việc thực sự đã được nhận vào hệ thống và dòng chảy của nó |

Nếu gộp mọi ý tưởng chưa được xem xét với công việc đang làm, chỉ số WIP và tuổi hạng mục sẽ trở nên khó diễn giải. **Điểm cam kết bắt đầu xử lý (commitment point)** cần rõ: đó là mốc nhóm chấp nhận một hạng mục vào workflow, không tự động có nghĩa cam kết ngày bàn giao tuyệt đối.

### Định nghĩa đơn vị công việc

Nhóm có thể hiển thị **user story, lỗi cần sửa, yêu cầu vận hành hoặc Product Backlog Item kỹ thuật**. Điều quan trọng là thống nhất:

- Hạng mục đủ độc lập và nhỏ để thấy tiến triển có ý nghĩa.
- Không dùng một thẻ “xây toàn bộ sản phẩm” kéo dài nhiều tháng để che những lát cắt chưa hoàn tất.
- Nếu một story chứa nhiều task, phân biệt **thẻ công việc tạo giá trị** với **task nội bộ**; không đếm cả story và task con như những hạng mục độc lập trong cùng một chỉ số throughput.
- Có tiêu chí hoàn thành phù hợp; với Scrum, Increment phải đáp ứng **Definition of Done**.

## 3. Thiết kế cột: hoạt động và hàng đợi phải có ý nghĩa

Một mô hình workflow tham khảo:

~~~text
ĐẦU VÀO (chưa nhận vào WIP)
    Ý tưởng / phản hồi -> Product Backlog được ưu tiên
                                  |
                                  v
WORKFLOW (đã nhận để thực hiện)
    Sẵn sàng -> Đang phát triển -> Chờ review -> Đang review
                                                       |
                                                       v
                    Đang kiểm thử <- Chờ kiểm thử <-----+
                          |
                          v
                    Chờ phát hành -> Đã bàn giao
~~~

Sơ đồ trên là ví dụ, **không phải các cột bắt buộc cho mọi đội**. Với nhóm tích hợp và phát hành liên tục, có thể không cần hàng đợi “Chờ phát hành”. Với nhóm dịch vụ vận hành, workflow có thể gồm “Phân loại – Điều tra – Chờ khách hàng – Xử lý – Xác minh – Hoàn tất”.

### Cột đang xử lý khác cột hàng đợi

| Loại trạng thái | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Active / Doing** | Có hoạt động đang được thực hiện trên hạng mục | Đang phát triển, đang review, đang kiểm thử |
| **Queue / Waiting** | Hạng mục đã sẵn sàng cho bước kế tiếp nhưng chưa được ai xử lý tại bước đó | Chờ review, chờ kiểm thử, chờ triển khai |
| **Done / Finished** | Hạng mục đạt điều kiện kết thúc của workflow đã định nghĩa | Đã phát hành theo chính sách nhóm, hoặc đã đạt mốc kết thúc đã thống nhất |
| **Blocked** | **Tình trạng cản trở tiến triển**, có thể xảy ra trong một trạng thái khác | Đang phát triển nhưng bị chặn do thiếu quyền truy cập |

**Blocked thường nên là tín hiệu đặt trên thẻ**, không mặc nhiên là một trạng thái workflow độc lập. Một thẻ ở “Chờ kiểm thử” có thể bị chặn vì môi trường kiểm thử không hoạt động; nếu chỉ chuyển sang cột “Blocked” mà xóa trạng thái “Chờ kiểm thử”, nhóm mất dấu nghẽn nằm ở đâu.

Tổ chức có thể chọn một cột bị chặn nếu nó phản ánh **một hoạt động xử lý trở ngại thực sự có chính sách riêng**, nhưng vẫn cần giữ thông tin bước trước đó để đo luồng và tính WIP chính xác.

### Cột có quá nhiều chi tiết cũng có thể gây hại

Một bảng 20 cột cho từng hành động nhỏ thường rất khó đọc. Nếu cột “Code review lần 1”, “Chờ phản hồi review”, “Sửa review”, “Review lại” chỉ phản ánh các lần trao đổi khác nhau trong **cùng một dịch vụ review**, có thể biểu diễn bằng trạng thái phụ, cờ hoặc checklist mà không cần thêm nhiều cột.

Ngược lại, nếu nhóm thường xuyên chờ nhiều ngày ở một bước, **tách cột chờ khỏi cột xử lý** có thể giúp nhìn nút thắt. Số cột phải phục vụ **quan sát và quyết định**, không phục vụ việc tạo ra quy trình có vẻ phức tạp.

## 4. Dùng một tấm thẻ để làm rõ trạng thái thực tế

Một thẻ Kanban tốt đủ ngắn để nhìn nhanh nhưng chứa những thông tin cần thiết cho luồng công việc:

~~~text
PBI-214  |  Học viên quay lại đúng tiến độ đã lưu
Giá trị: Tránh học lại phần đã hoàn thành
Trạng thái: Chờ kiểm thử tích hợp
Loại công việc: Sửa lỗi / cải thiện trải nghiệm
Bắt đầu: 09/11  |  Vào hàng đợi kiểm thử: 12/11
Tuổi công việc: 5 ngày làm việc (theo quy ước nhóm)
BLOCKED: Có, từ 13/11
Lý do: Môi trường thử nghiệm không truy cập được API tiến độ
Đầu mối hỗ trợ: Nhóm môi trường
Bước tiếp theo: Kiểm tra quyền truy cập lúc 10:00, 14/11
Tiêu chí kết thúc: Kiểm thử đạt, tích hợp và đạt DoD
~~~

Những ngày trong thẻ là **dữ liệu giả định minh họa**, không phải dữ liệu của dự án có thật. Nếu ngày đầu vào hạng mục, ngày bắt đầu và ngày vào hàng đợi được ghi nhất quán, nhóm mới đo được **thời gian chờ**, không chỉ tổng thời gian.

### Thông tin nào nên hiển thị trực tiếp?

| Thông tin | Vì sao cần? | Cách hiển thị gợi ý |
| --- | --- | --- |
| **ID và tên ngắn** | Nhận biết thẻ, tránh tạo trùng | Một dòng tiêu đề |
| **Trạng thái** | Biết hạng mục ở bước nào | Vị trí cột |
| **Mức ưu tiên / loại dịch vụ** | Hiểu quy tắc chọn việc tiếp theo | Nhãn hoặc lane nếu thực sự cần |
| **Tuổi hạng mục** | Phát hiện việc đang già đi | Ngày vào WIP và số ngày theo quy ước |
| **Blocked** | Lộ tình trạng bị cản trở | Biểu tượng/nền dễ thấy, kèm thời gian bắt đầu |
| **Lý do và bước xử lý** | Cho biết phải hành động gì | Nội dung ngắn trên thẻ hoặc liên kết |
| **Người/nhóm đang hỗ trợ** | Biết nơi hỏi và phối hợp | Đầu mối, không dùng như danh sách đổ lỗi |
| **Giá trị / tiêu chí Done** | Giữ sự tập trung vào kết quả | Liên kết đến PBI và tiêu chí |

Không nên đưa mật khẩu, thông tin bệnh nhân, dữ liệu thanh toán hoặc thông tin học viên nhạy cảm lên bảng có quyền truy cập rộng. Có thể để **mã tham chiếu và liên kết** tới hệ thống được bảo vệ.

## 5. Hàng đợi không phải tiến độ đã hoàn thành

Một hiểu lầm phổ biến là “đã chuyển khỏi cột phát triển” đồng nghĩa “gần xong”. Thực tế, việc nằm trong hàng đợi có thể **không tiến thêm chút nào tới trạng thái bàn giao** dù tổng thời gian vẫn tăng.

### Ví dụ hàng đợi kiểm thử

Giả sử một nhóm có:

| Trạng thái | Số hạng mục tại thời điểm quan sát |
| --- | ---: |
| Đang phát triển | 2 |
| Chờ review | 3 |
| Đang review | 1 |
| Chờ kiểm thử | 5 |
| Đang kiểm thử | 1 |
| Chờ phát hành | 2 |

Nhóm có **14 hạng mục đang trong workflow** nếu tất cả các cột trên đều nằm sau điểm bắt đầu WIP và trước điểm Done. Chỉ **4 hạng mục** ở các cột chủ động xử lý (2 phát triển + 1 review + 1 kiểm thử), còn **10 hạng mục ở các hàng đợi**.

Nhận định quan trọng không phải “Developers chậm” hay “kiểm thử làm không đủ việc”, mà là **dòng công việc đang tích tụ tại các bước chờ**. Nhóm cần điều tra: hạng mục chuyển sang “chờ” đã đủ điều kiện chưa, năng lực review/kiểm thử có bị chia sẻ với dự án khác không, có nhiều công việc bị mở sớm không, và có thể giúp hoàn tất phần đang chờ trước khi bắt đầu mới không.

### Nhìn tuổi của hàng đợi

Nếu có năm hạng mục chờ kiểm thử, một hạng mục mới vừa tới có thể ít đáng lo hơn một hạng mục đã chờ tám ngày và sắp vượt kỳ vọng giao hàng. Bởi vậy, nên xem cả:

- **Queue length:** Có bao nhiêu thẻ đang chờ?
- **Queue age:** Mỗi thẻ đã chờ bước này bao lâu?
- **Arrival vs departure:** Thẻ vào hàng chờ nhanh hơn số thẻ được xử lý xong không?
- **Độ biến động:** Có lúc hàng chờ rất dài, lúc gần như trống, hay thường xuyên tích tụ?

Đếm số thẻ chỉ cho biết **ảnh chụp tại một thời điểm**. Theo dõi xu hướng và tuổi mới giúp đánh giá mức độ tồn đọng.

## 6. Công việc bị chặn: lộ rõ nguyên nhân, thời gian và hành động

**Blocked work** là hạng mục không thể tiến triển theo quy trình như dự kiến vì một trở ngại cụ thể, ví dụ:

- Chưa có quyết định nghiệp vụ quan trọng.
- API phụ thuộc không hoạt động hoặc quyền truy cập chưa được cấp.
- Môi trường thử nghiệm không sẵn sàng.
- Thiếu dữ liệu kiểm chứng hoặc thông tin từ đối tác.
- Một điều kiện an toàn hoặc chất lượng cần được giải quyết trước khi tiếp tục.

Nên phân biệt **blocked** với **đang chờ bình thường theo chính sách**. Một thẻ chờ review khi nhóm review đang làm những thẻ khác là hàng đợi; một thẻ không thể review do thiếu quyền xem mã là blocked. Ranh giới cần được **định nghĩa rõ** để dữ liệu không phụ thuộc cảm tính từng người.

### Bốn thông tin tối thiểu cho nhãn blocked

1. **Nguyên nhân quan sát được:** “Không truy cập được môi trường test”, thay vì “team khác chậm”.
2. **Bắt đầu từ khi nào:** Ghi thời điểm blocked để theo dõi tuổi cản trở.
3. **Ai có thể giúp tháo gỡ:** Đầu mối kỹ thuật, nghiệp vụ, vận hành hoặc người có thẩm quyền.
4. **Hành động kế tiếp và thời điểm xem lại:** Ví dụ “liên hệ quản trị môi trường; xem lại sau buổi phối hợp chiều nay”.

~~~text
PBI-214  [BLOCKED]
Vị trí: Chờ kiểm thử tích hợp
Từ: 13/11, 09:30
Nguyên nhân: Môi trường thử nghiệm không thể kết nối dịch vụ tiến độ
Ảnh hưởng: Chưa kiểm chứng được việc khôi phục bài học
Đầu mối: Hạ tầng + Developers
Hành động kế tiếp: Kiểm tra kết nối và thông tin phân quyền
Xem lại: 14/11, 10:00
~~~

Không cần biến thông tin blocked thành một báo cáo dài. Điều cần là người nhìn bảng biết **phải giúp việc gì để thẻ tiếp tục di chuyển**.

### Thẻ bị chặn vẫn thường được tính vào WIP

Nếu hạng mục đã bắt đầu và chưa Done, nó vẫn chiếm năng lực, thời gian chờ và sự chú ý. **Ẩn thẻ blocked ra khỏi WIP** rồi tự động kéo hạng mục mới vào có thể khiến nhóm mở ngày càng nhiều việc, trong khi các hạng mục cũ không hoàn tất.

Một nhóm có thể đặt chính sách ngoại lệ cho công việc bị chặn kéo dài, nhưng cần minh bạch:

- Hạng mục có còn thuộc workflow được đo không?
- Chính sách WIP xử lý blocked ra sao?
- Ai theo dõi và khi nào quyết định thay thế hạng mục?
- Có làm méo số liệu cycle time, throughput hoặc việc đang dở không?

**Nguyên tắc thực dụng:** Đừng dùng nhãn blocked như một cách “giải phóng ô WIP miễn phí”. Nếu tạm gác một hạng mục, phải thể hiện sự thay đổi theo chính sách rõ ràng và giữ dấu vết lịch sử.

## 7. Chính sách chuyển trạng thái: giảm tranh cãi và tạo dữ liệu đáng tin

Một bảng chỉ có cột nhưng không có **chính sách (explicit policies)** sẽ dẫn đến tình trạng mỗi người tự hiểu “sẵn sàng”, “đang làm”, “chờ” và “hoàn thành” khác nhau.

Ví dụ chính sách cho workflow phát triển:

| Bước chuyển | Điều kiện rõ ràng được thống nhất | Điều cần tránh |
| --- | --- | --- |
| **Backlog → Sẵn sàng** | Có mục tiêu, phạm vi đủ rõ, điều kiện chấp nhận chính và phụ thuộc lớn đã biết | Chuyển vì “ticket vừa được tạo” |
| **Sẵn sàng → Đang phát triển** | Nhóm có năng lực WIP, chọn việc theo chính sách ưu tiên | Mỗi người kéo việc mới dù các việc cũ còn bị chặn |
| **Đang phát triển → Chờ review** | Thay đổi đã sẵn sàng review theo tiêu chuẩn nhóm; có ngữ cảnh kiểm tra | Gửi review khi chưa thể chạy hoặc thiếu thông tin |
| **Chờ review → Đang review** | Có người/nhóm nhận xử lý, thời điểm bắt đầu được ghi | Coi “đã có người được gán” là đang review thật |
| **Đang review → Chờ kiểm thử** | Vấn đề phát hiện đã xử lý hoặc có quyết định cụ thể | Đẩy lỗi chưa giải quyết sang bước sau để làm đẹp cột |
| **Chờ kiểm thử → Đang kiểm thử** | Có môi trường, dữ liệu và người xử lý phù hợp | Chuyển cột chỉ vì đã đặt lịch test |
| **Đang kiểm thử → Chờ phát hành** | Đạt các kiểm tra/điều kiện chất lượng cần thiết | Coi kiểm thử bị bỏ qua là kiểm thử đạt |
| **Chờ phát hành → Đã bàn giao** | Đạt chính sách kết thúc workflow; thời điểm kết thúc được ghi | Đóng thẻ trước khi đạt điều kiện đã định nghĩa |

Đây là **chính sách mẫu để học tập**, không phải khuôn mẫu áp dụng cho mọi dự án. Nếu có một bước sửa lỗi quay lại phát triển, nhóm cần thể hiện **chuyển động ngược** trung thực thay vì giả vờ công việc chỉ luôn đi tiến.

### Một trạng thái nên trả lời ba câu hỏi

- **Ai/nhóm nào hoặc hoạt động nào có khả năng tiến hành bước này?**
- **Điều kiện nào để hạng mục vào và rời bước?**
- **Làm sao biết thẻ đang được xử lý thực sự hay chỉ chờ?**

Nếu không trả lời được ba câu hỏi, tên cột có thể quá mơ hồ để giúp quản lý dòng công việc.

## 8. Giới hạn WIP và cơ chế kéo việc: hoàn tất trước khi bắt đầu thêm

**WIP (work in progress)** là số hạng mục đã bắt đầu nhưng chưa hoàn thành trong ranh giới workflow đã định. **Giới hạn WIP** giúp nhóm ngăn mở quá nhiều việc, phát hiện nghẽn và tập trung đưa những hạng mục đang làm đến Done.

Ví dụ một nhóm đặt các giới hạn:

| Vị trí | WIP limit minh họa |
| --- | ---: |
| Đang phát triển | 3 |
| Đang review | 2 |
| Đang kiểm thử | 2 |
| **Toàn bộ phần đang thực hiện từ phát triển tới kiểm thử** | **6** |

Các số là **giả định thử nghiệm**, phải được hiệu chỉnh bằng năng lực và dữ liệu thực tế. Nếu chỉ giới hạn cột đang xử lý nhưng không giới hạn tổng lượng việc gồm hàng đợi, nhóm có thể tiếp tục tích tụ hàng chờ vô hạn.

### Pull thay vì push

**Push:** Một hạng mục vừa viết mã xong lập tức được đẩy sang “Chờ kiểm thử”, trong khi kiểm thử đang quá tải; đồng thời Developers lại bắt đầu thêm ba story.

**Pull:** Khi còn năng lực tại bước tiếp theo, nhóm nhận một hạng mục sẵn sàng theo chính sách đã thống nhất. Khi không còn năng lực, cả nhóm xem cách giúp **hoàn tất việc đang chờ** thay vì chỉ đẩy thêm việc tới nút thắt.

~~~mermaid
flowchart LR
    A["Sẵn sàng"] --> B["Phát triển"]
    B --> C["Hàng đợi review"]
    C --> D["Review"]
    D --> E["Hàng đợi kiểm thử"]
    E --> F["Kiểm thử"]
    F --> G["Done"]
    H["Khi bước sau có năng lực, kéo việc phù hợp"] -.-> C
    H -.-> E
~~~

Điều cần tối ưu là **dòng giá trị toàn hệ thống**, không phải giữ tất cả cá nhân bận 100%. Một Developer hỗ trợ tái hiện lỗi kiểm thử có thể giúp một story hoàn thành sớm hơn so với việc bắt đầu story mới của riêng mình.

### Vượt WIP limit cần được nhìn thấy

Giới hạn WIP không phải công cụ để trừng phạt. Nếu phát sinh sự cố nghiêm trọng buộc nhóm vượt giới hạn, hãy ghi rõ **lý do, ảnh hưởng và chính sách ngoại lệ**, rồi xem lại. Khi vượt giới hạn lặp đi lặp lại mà không được thảo luận, con số WIP limit chỉ còn là trang trí.

### Giới hạn WIP không tự giải quyết phụ thuộc

Nếu toàn bộ công việc bị chặn vì chưa có quyền sử dụng API, chỉ giảm WIP sẽ không làm hệ thống vận hành. Nhóm phải **tháo gỡ nguyên nhân thực**: phối hợp với đầu mối, thử tích hợp sớm, thay đổi chính sách cấp quyền hoặc chia lát cắt phù hợp.

## 9. Trực quan hóa thời gian chờ, tuổi công việc và xu hướng nghẽn

Bảng cho biết **việc đang ở đâu**; số liệu thời gian giúp biết **đã ở đó bao lâu** và **xu hướng có trở nên xấu hơn không**.

### Bốn phép đo dòng công việc cơ bản

| Thước đo | Định nghĩa thực dụng | Câu hỏi giúp trả lời |
| --- | --- | --- |
| **WIP** | Số hạng mục đã bắt đầu nhưng chưa kết thúc workflow ở một thời điểm | Nhóm đang mở bao nhiêu việc? |
| **Throughput** | Số hạng mục hoàn thành trong một khoảng thời gian theo quy ước | Dòng công việc thực tế hoàn tất được bao nhiêu? |
| **Work Item Age** | Thời gian đã trôi qua của một hạng mục đang WIP, tính từ mốc bắt đầu đã định | Việc đang làm có già hơn mức thường thấy không? |
| **Cycle Time** | Thời gian trôi qua từ mốc bắt đầu đến khi hạng mục hoàn thành | Việc đã hoàn tất thường mất bao lâu? |

**Lead time** cũng được dùng rộng rãi, thường tính từ mốc yêu cầu được tiếp nhận tới khi bàn giao. Cần ghi rõ mốc nào được áp dụng; nếu một tổ chức định nghĩa lead time từ thời điểm cam kết bắt đầu, không nên so sánh trực tiếp với đội đo từ ngày khách hàng gửi yêu cầu.

Thời gian blocked, thời gian chờ riêng từng cột và thời gian xử lý thực có thể giúp giải thích **vì sao cycle time cao**, chứ không chỉ biết tổng số ngày.

### Ví dụ tính thời gian của một story

Giả sử một story trải qua các khoảng **ngày làm việc không chồng lấn** sau khi được nhận vào workflow:

| Hoạt động | Thời gian minh họa |
| --- | ---: |
| Phát triển trực tiếp | 2 ngày |
| Chờ review | 3 ngày |
| Review trực tiếp | 0,5 ngày |
| Chờ kiểm thử, trong đó có 2 ngày blocked vì môi trường | 3 ngày |
| Kiểm thử trực tiếp | 0,5 ngày |
| Chờ phát hành | 1 ngày |
| **Tổng cycle time** | **10 ngày** |

Tổng thời gian xử lý trực tiếp trong ví dụ là **3 ngày** (2 + 0,5 + 0,5); thời gian chờ là **7 ngày** (3 + 3 + 1). Nếu nhóm dùng cách tính **flow efficiency** đơn giản:

\[
\text{Flow efficiency}=\frac{\text{thời gian xử lý trực tiếp}}{\text{cycle time}}\times100\%=\frac{3}{10}\times100\%=30\%.
\]

Chỉ số 30% không có nghĩa “nhân viên chỉ làm việc 30% thời gian”. Nó nói rằng **trong hành trình của story này**, phần thời gian được nhóm phân loại là xử lý chủ động chiếm 30%. Thành viên vẫn có thể làm những hạng mục khác trong lúc story xếp hàng.

Hai ngày blocked **nằm trong ba ngày chờ kiểm thử**; không được cộng thêm lần nữa vào tổng cycle time. Nếu đo thời gian theo giờ lịch thay vì ngày làm việc, cần thay đổi cách tính nhất quán. Những số liệu này chỉ minh họa, không đại diện cho một dự án thực tế.

### Work Item Age giúp can thiệp trước khi quá muộn

Cycle time chỉ có sau khi việc hoàn thành. **Work Item Age** cho biết một hạng mục **chưa hoàn tất** đã nằm trong workflow bao lâu, nên hữu ích khi nhóm xem bảng mỗi ngày.

Ví dụ:

- Story A: đang phát triển, tuổi 1 ngày.
- Story B: chờ review, tuổi 7 ngày.
- Story C: blocked ở kiểm thử, tuổi 11 ngày.

Ngay cả khi WIP chưa vượt giới hạn, story C vẫn cần được điều tra vì có thể **đang già hơn phần lớn hạng mục tương tự**. Nên dựa vào phân phối cycle time của nhóm để đặt tín hiệu cảnh báo, tránh tự đặt ngưỡng toàn ngành không có căn cứ.

## 10. Cumulative Flow Diagram: xem hàng đợi lớn dần ở đâu

**Cumulative Flow Diagram (CFD)** là biểu đồ thể hiện số lượng tích lũy các hạng mục theo trạng thái trong thời gian. Độ dày của một dải trạng thái có thể cho thấy lượng hạng mục đang nằm tại trạng thái đó.

### Diễn giải đơn giản

- Nếu dải **chờ kiểm thử** ngày càng dày, hạng mục vào hàng chờ có thể nhiều hơn hạng mục được lấy ra xử lý.
- Nếu nhiều dải WIP cùng dày lên, tổng lượng việc đang làm dở có thể đang tăng.
- Nếu đường hạng mục hoàn thành tăng đều trong khi WIP tương đối ổn định, dòng công việc có thể ổn định hơn.
- Nếu đường hoàn thành gần như phẳng trong khi WIP tăng, cần điều tra nút thắt hoặc công việc bị chặn.

CFD **không tự xác định nguyên nhân**. Để hiểu vì sao hàng đợi tăng, cần kiểm tra chính sách, loại công việc, thời gian bị chặn, phụ thuộc và năng lực thực tế.

### Khi nào biểu đồ dễ gây hiểu sai?

Nếu nhóm:

- Đổi tên hoặc thêm cột giữa kỳ nhưng không lưu lịch sử trạng thái;
- Chuyển thẻ blocked sang cột riêng khiến chúng “biến mất” khỏi hàng đợi ban đầu;
- Đóng và mở lại thẻ theo một quy ước khác nhau;
- Đếm task con cùng với story cha;

thì biểu đồ có thể thay đổi do **cách ghi dữ liệu**, không phải do dòng công việc tốt hơn hay xấu đi. Vì vậy cần **giữ chính sách và cách đo ổn định hoặc ghi rõ thời điểm thay đổi**.

### Không suy diễn quá nhiều từ một ảnh chụp

Một bảng có 5 thẻ chờ kiểm thử chưa đủ để kết luận kiểm thử là nút thắt dài hạn. Cần xem **thời gian tồn đọng, tốc độ đến/rời hàng chờ, loại hạng mục và giai đoạn sản phẩm**. Một đợt tích hợp lớn có thể tạo hàng chờ tạm thời; nếu xu hướng kéo dài nhiều tuần, nguyên nhân đáng điều tra hơn.

## 11. Tín hiệu trực quan hỗ trợ quyết định mà không gây nhiễu

Một bảng Kanban có thể dùng màu sắc, nhãn, biểu tượng, swimlane hoặc đường viền để làm nổi thông tin. Nhưng **quá nhiều màu và nhãn khiến mọi việc trở nên “đặc biệt” như nhau**.

Các tín hiệu nên có quy tắc:

| Tín hiệu | Mục đích | Chính sách ví dụ |
| --- | --- | --- |
| **BLOCKED** | Nhận biết hạng mục không thể tiến triển | Luôn ghi lý do, thời điểm bắt đầu và hành động tiếp theo |
| **Aging** | Nhìn hạng mục già hơn thông thường | So với phân phối lịch sử hoặc mục tiêu thời gian đã thống nhất |
| **Loại dịch vụ / class of service** | Phân biệt nhóm công việc cần chính sách xử lý khác nhau | Ví dụ sự cố khẩn cấp, công việc tiêu chuẩn, hạng mục có ngày hạn bắt buộc |
| **Swimlane** | Gom nhóm thẻ theo một chiều có ích | Có thể theo loại công việc hoặc khách hàng, tránh tạo quá nhiều luồng ưu tiên riêng |
| **Phụ thuộc** | Biết hạng mục đang đợi kết quả từ nơi khác | Liên kết tới hạng mục hoặc đầu mối xử lý |
| **WIP limit** | Làm lộ nơi nhóm đã mở quá nhiều việc | Hiển thị số thẻ hiện tại và giới hạn trên cột/vùng phù hợp |

### “Expedite” không phải nhãn để ai cũng chọn

Một số workflow có lớp dịch vụ **expedite** cho sự cố thật sự khẩn cấp. Nhóm nên định nghĩa điều kiện vào, quyền quyết định, giới hạn sử dụng và cách minh bạch công việc bị trì hoãn. Nếu mọi ticket đều có nhãn **Urgent**, nhãn ấy không giúp chọn việc nữa.

Một lỗi làm lộ dữ liệu người dùng có thể đòi hỏi ứng phó theo quy trình sự cố của tổ chức. **Không cần bỏ qua các kiểm soát an toàn bắt buộc** chỉ vì hạng mục được xếp expedite.

### Chú ý khả năng tiếp cận

Đừng dùng **chỉ màu đỏ/xanh** để thể hiện blocked/unblocked, vì có người khó phân biệt màu. Kết hợp màu với **từ “BLOCKED”, biểu tượng, trạng thái văn bản và cấu trúc rõ ràng** để bảng dễ đọc hơn trên nhiều thiết bị.

## 12. Case study: giải phóng hàng đợi kiểm thử trong một đội Agile

**Bối cảnh giả định:** Nhóm phát triển nền tảng học trực tuyến có mục tiêu giúp học viên tiếp tục bài từ tiến độ đã lưu. Họ sử dụng Kanban để quản lý việc cải thiện sản phẩm và sửa lỗi.

### 12.1. Ảnh chụp bảng trước khi thay đổi

| Thẻ | Vị trí | Tuổi minh họa | Ghi chú |
| --- | --- | ---: | --- |
| PBI-201: Hiển thị danh sách bài đang học | Đang phát triển | 2 ngày | Gần xong UI |
| PBI-202: Khôi phục tiến độ sau tải lại | Chờ review | 6 ngày | Đợi người hiểu API |
| PBI-203: Thông báo khi chưa lưu thành công | Chờ review | 5 ngày | Thiếu ví dụ về lỗi mạng |
| PBI-204: Ngăn ghi đè tiến độ mới bằng dữ liệu cũ | Chờ kiểm thử | 9 ngày | **Blocked:** môi trường test lỗi |
| PBI-205: Đồng bộ tiến độ giữa thiết bị | Chờ kiểm thử | 8 ngày | Đợi quy tắc xử lý xung đột |
| PBI-206: Lọc khóa học theo chủ đề | Đang phát triển | 1 ngày | Vừa được kéo vào |
| PBI-207: Sửa lỗi đăng xuất sai | Đang kiểm thử | 4 ngày | Có test còn lỗi |

Từ bảng, nhóm có thể thấy **nhiều việc cũ đang chờ** và vẫn kéo thêm việc mới vào phát triển. Nhưng chỉ đếm số thẻ chưa đủ: cần xem nguyên nhân của PBI-204/205 và khả năng hỗ trợ review PBI-202/203.

### 12.2. Kiểm tra nguyên nhân, không chỉ đổi nhãn

Nhóm trao đổi và phát hiện:

1. **PBI-202:** Không có thời gian review được dành rõ khi chuyên gia API vừa làm dự án khác. Cần chia sẻ kiến thức và phối hợp review sớm.
2. **PBI-203:** Tiêu chí chấp nhận không nói rõ thông báo nào hiển thị khi API chưa xác nhận lưu thành công. Cần trao đổi nghiệp vụ và kiểm thử.
3. **PBI-204:** Môi trường kiểm thử không truy cập được dịch vụ tiến độ. Cần đầu mối hạ tầng, tái hiện và xử lý quyền kết nối.
4. **PBI-205:** Quy tắc xung đột chưa được quyết định. Cần làm rõ với Product Owner và người có quyền quyết định nghiệp vụ trước khi kiểm thử hành vi.

Các nguyên nhân **khác nhau** nên hành động cũng khác nhau. Một cột chung “Blocked” không thể thay thế phần phân tích này.

### 12.3. Một cải tiến quy trình nhỏ

Nhóm thỏa thuận thử trong hai tuần:

- Khi một hạng mục chờ review quá khoảng thời gian nội bộ đã thống nhất, Developers ưu tiên giúp hoàn tất trước khi mở story mới.
- Trước khi chuyển sang chờ kiểm thử, người thực hiện và kiểm thử cùng kiểm tra **các ví dụ chấp nhận quan trọng**.
- Thẻ blocked giữ nguyên cột hiện tại nhưng có **nhãn, thời điểm, nguyên nhân, đầu mối và lần xem lại**.
- WIP toàn bộ phần đang thực hiện được quản lý để không tạo thêm hàng chờ vô hạn.
- Mỗi lần họp ngắn, nhóm xem **thẻ già nhất và thẻ bị chặn**, thay vì lần lượt đọc báo cáo của từng người.

### 12.4. Cách đo xem thử nghiệm có hiệu quả

| Chỉ số | Điều nhóm quan sát | Cần kiểm tra thêm |
| --- | --- | --- |
| **Số thẻ chờ review/kiểm thử** | Hàng đợi có bớt tích tụ không? | Có phải thẻ bị chuyển sang cột khác để che tồn đọng? |
| **Tuổi của hạng mục đang WIP** | Thẻ cũ có được hoàn tất không? | Có ưu tiên hạng mục thật sự quan trọng không? |
| **Thời gian blocked** | Trở ngại có được tháo gỡ sớm hơn không? | Có ngừng ghi blocked dù vấn đề chưa hết không? |
| **Throughput và cycle time** | Dòng công việc có ổn định hơn không? | Hạng mục có bị chia khác đi làm dữ liệu khó so không? |
| **Lỗi sau bàn giao** | Tốc độ tốt hơn có đi kèm chất lượng không? | Không bỏ kiểm thử hoặc áp lực đóng thẻ sớm |
| **Phản hồi người học** | Khả năng lưu/khôi phục tiến độ có đáng tin hơn không? | Cần đủ dữ liệu và bối cảnh quan sát |

Nếu hai tuần đầu bảng trông “thưa thẻ” hơn nhưng người dùng vẫn mất tiến độ, nhóm chưa thể kết luận đã cải thiện sản phẩm. **Mục tiêu cuối cùng là tạo giá trị và giảm thời gian nhận phản hồi đáng tin cậy**, không phải chỉ làm cho bảng gọn.

## 13. Nhịp phản hồi: dùng bảng để phối hợp, không chỉ cập nhật trạng thái

Bảng Kanban cần được sử dụng trong những cuộc trao đổi tạo quyết định. Một nhịp vận hành thực tế có thể gồm:

### 13.1. Xem dòng công việc hằng ngày

Một cuộc trao đổi ngắn có thể tập trung:

1. **Hạng mục nào gần hoàn thành nhất?** Có thể giúp nó tới Done không?
2. **Thẻ nào già bất thường hoặc đang blocked?** Nguyên nhân và hành động kế tiếp?
3. **Hàng đợi nào đang tích tụ?** Có cần đổi cách phối hợp hoặc giới hạn kéo việc mới?
4. **Khi nào thực sự có năng lực để kéo hạng mục tiếp theo?**
5. **Có rủi ro nào ảnh hưởng việc giao giá trị hoặc chất lượng?**

Một số nhóm chọn xem bảng **từ phải sang trái** để ưu tiên hoàn tất công việc. Đây là **kỹ thuật gợi ý**, không phải luật bắt buộc.

### 13.2. Replenishment: chọn việc mới khi có năng lực

Nhóm cần chính sách đưa hạng mục mới từ nguồn được ưu tiên vào workflow. Các câu hỏi hữu ích:

- Công việc có liên quan mục tiêu sản phẩm hoặc rủi ro cần xử lý?
- Có đủ thông tin để bắt đầu an toàn?
- Có năng lực WIP thực sự không?
- Có phải tạm dừng hoặc bỏ việc nào để nhận việc khẩn cấp?

Không nhất thiết biến mỗi lần chọn việc thành cuộc họp dài. Nhưng cần rõ **ai được quyết định thứ tự, ai chọn việc và điều kiện nào cho phép kéo việc**.

### 13.3. Xem kết quả bàn giao

Khi một hạng mục tới Done, nhóm có thể xem phản hồi người dùng, số liệu lỗi hoặc giới hạn vừa phát hiện. Những thông tin đó quay lại Product Backlog hoặc nguồn ưu tiên để nhóm thích ứng.

### 13.4. Review mức dịch vụ và rủi ro dòng công việc

Theo chu kỳ phù hợp, nhóm xem phân phối cycle time, throughput, hàng đợi, tuổi hạng mục và những blocker lặp lại. Nếu phần lớn thẻ bị chặn vì cấp quyền môi trường, cải tiến có thể cần **người có thẩm quyền ngoài nhóm**, không thể giải quyết chỉ bằng đổi cột.

**Điều kiện thành công:** Phản hồi từ bảng dẫn tới thay đổi có thể kiểm chứng, không chỉ thêm một cuộc họp báo cáo.

## 14. Kanban và Scrum: trực quan hóa có thể bổ trợ Sprint Goal

**Kanban không bắt buộc dùng Sprint**, còn **Scrum** có các accountability, event, artifact và commitment được định nghĩa riêng. Một Scrum Team có thể áp dụng các thực hành Kanban để **tăng tính minh bạch của Sprint Backlog và quản lý dòng công việc** mà không bỏ Sprint Goal.

Ví dụ trong Daily Scrum, Developers nhìn bảng:

- Một hạng mục đang blocked vì API chưa xác nhận lưu.
- Hai hạng mục đang chờ kiểm thử, một hạng mục cần đạt DoD để hoàn thành Sprint Goal.
- WIP đã đạt giới hạn nội bộ.

Developers có thể **điều chỉnh kế hoạch phối hợp để hoàn tất lát cắt đang làm**, thay vì chỉ báo cáo mỗi người đã làm gì hôm qua. Scrum Master có thể huấn luyện việc dùng bảng, nhưng không mặc nhiên trở thành người giao việc.

Trong Scrum:

- **Product Owner** chịu trách nhiệm quản lý Product Backlog và thứ tự ưu tiên.
- **Developers** chịu trách nhiệm kế hoạch trong Sprint Backlog và chất lượng Increment.
- **Sprint Goal** là commitment của Sprint Backlog, **Definition of Done** là commitment của Increment.
- Thực hành Kanban giúp nhìn luồng, **không thay đổi các accountability hoặc biến mọi sự kiện Scrum thành buổi báo cáo bảng**.

### XP có thể giảm hàng chờ kỹ thuật

Các thực hành của **Extreme Programming (XP)** như TDD, lập trình cặp, tích hợp liên tục và tái cấu trúc có thể giảm thời gian chờ phát hiện lỗi:

- **Pair programming** giúp một số vấn đề review hoặc chia sẻ kiến thức được xử lý ngay khi lập trình.
- **Continuous Integration** giúp nhóm không đợi cuối Sprint mới biết thay đổi không tích hợp được.
- **TDD và kiểm thử tự động** hỗ trợ kiểm tra thường xuyên và giảm số vòng sửa lỗi.

Những kỹ thuật này không loại bỏ mọi hàng đợi, nhưng giúp nhóm thử cách **giảm thời gian chờ có nguyên nhân kỹ thuật** mà vẫn giữ chất lượng.

## 15. Khi làm việc phân tán hoặc có nhiều đội cùng tham gia

Ở đội làm việc từ xa, bảng số nên đủ minh bạch để người không tham gia cuộc gọi vẫn biết thẻ nào cần hỗ trợ. Nhưng **công cụ số không tự bảo đảm thông tin đúng** nếu thẻ chỉ được cập nhật mỗi tuần.

### Một số quy ước hữu ích

- Người tham gia cập nhật **trạng thái tại thời điểm chuyển bước**, không đợi cuối tuần để nhớ lại.
- Khi blocked, ghi **nguyên nhân và lần xem lại**; không chỉ gắn một nhãn đỏ.
- Người phụ trách bước tiếp theo nhận được ngữ cảnh cần thiết mà không phải tìm qua nhiều đoạn chat.
- Các công việc từ nhiều đội được **liên kết bằng phụ thuộc có thể tra cứu**, không tạo danh sách ưu tiên mâu thuẫn.
- Dashboard cho các bên liên quan cần phân biệt **công việc đang xử lý, hàng đợi, blocked và Done**.
- Những thông tin hạn chế quyền truy cập được lưu tại hệ thống phù hợp, không đặt công khai trên thẻ.

### Nếu nhiều đội cùng làm một sản phẩm

Một sản phẩm có thể có nhiều bảng vận hành ở các cấp độ kỹ thuật khác nhau, nhưng cần tránh mỗi bảng tuyên bố một thứ tự ưu tiên không tương thích. Với nhiều Scrum Team cùng phát triển một sản phẩm, Scrum Guide yêu cầu họ cùng chia sẻ **Product Goal, Product Backlog và Product Owner**.

**“Một nguồn ưu tiên có thẩm quyền” không có nghĩa mọi chi tiết kỹ thuật phải nằm trong cùng một bảng khổng lồ.** Có thể liên kết bảng của các đội với Product Backlog chung, giữ ranh giới và quyền quyết định rõ.

## 16. Những phản mẫu dễ gặp khi trực quan hóa Kanban

| Phản mẫu | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| **Chỉ dùng To do – Doing – Done dù có nhiều bước chờ** | Không thấy nút thắt cụ thể | Tách những hàng đợi có ý nghĩa và đo thời gian chờ |
| **Chia quá nhiều cột cho hành động nhỏ** | Bảng khó đọc, cập nhật tốn công | Dùng cột cho các trạng thái quyết định được; việc nhỏ là checklist hoặc trạng thái phụ |
| **Chuyển mọi thẻ bị chặn vào cột Blocked** | Mất thông tin công việc bị chặn tại bước nào | Dùng tín hiệu blocked trên thẻ và giữ trạng thái gốc; có chính sách nếu dùng cột riêng |
| **Thẻ blocked không có nguyên nhân hay hành động** | Không ai biết tháo gỡ thế nào | Ghi lý do, thời điểm, đầu mối và lần xem lại |
| **Blocked tự động không tính WIP** | Việc dở phình to, người dùng vẫn chờ | Tính nhất quán theo ranh giới WIP và chính sách ngoại lệ minh bạch |
| **Mỗi người luôn phải có việc mới để bắt đầu** | Dồn việc tới review và test, cycle time tăng | Ưu tiên hoàn tất công việc và giúp nút thắt |
| **Mọi thẻ đều khẩn cấp** | Không có cách chọn thứ tự thật | Định nghĩa class of service và quyền sử dụng nhãn |
| **Không có chính sách chuyển cột** | Dữ liệu trạng thái không đáng tin | Công bố điều kiện vào/ra và cách xử lý ngoại lệ |
| **Đóng thẻ khi code xong dù chưa kiểm thử** | Throughput tăng giả, lỗi sau bàn giao tăng | Định nghĩa Done phù hợp với chất lượng và bàn giao |
| **Đếm cả story và task con trong throughput** | Sai lệch số lượng công việc hoàn thành | Thống nhất đơn vị đo và tránh đếm hai lần |
| **Tập trung số ticket, không nhìn tuổi** | Hạng mục lâu ngày bị lãng quên | Xem Work Item Age và các thẻ già nhất |
| **Dùng bảng để giám sát cá nhân** | Mọi người che giấu khó khăn hoặc làm đẹp trạng thái | Dùng bảng để phối hợp và cải tiến hệ thống công việc |
| **Chỉ nhìn bảng mà không trò chuyện với người dùng** | Luồng nhanh nhưng giá trị sản phẩm không rõ | Kết nối kết quả bàn giao với phản hồi và Product Goal |
| **Đổi định nghĩa trạng thái liên tục** | CFD, cycle time khó so sánh theo thời gian | Ghi thời điểm thay đổi quy ước và điều chỉnh cách phân tích |

## 17. Bài thực hành: thiết kế và vận hành một bảng Kanban

### Bối cảnh

Một nhóm phát triển nền tảng học trực tuyến nhận các yêu cầu:

- Người học thấy tiến độ đã lưu khi mở lại bài.
- Người học nhận biết việc lưu thất bại do mất mạng.
- Người quản trị có thể lọc những bài chưa hoàn thành.
- API tiến độ phải chống ghi đè dữ liệu mới bằng dữ liệu cũ.
- Nhóm hỗ trợ muốn giảm số ticket hỏi “tôi đã học tới đâu?”.

Nhóm có Developers, người kiểm thử và sự phụ thuộc vào môi trường tích hợp; họ thường bị ùn việc ở bước review và kiểm thử. Dữ liệu, thời gian và chính sách trong bài tập là **giả định để thực hành**.

### Nhiệm vụ A — Vẽ ranh giới và các cột

Thiết kế bảng từ lúc PBI được chọn để thực hiện đến lúc được bàn giao theo chính sách chất lượng. Một phương án:

~~~text
Backlog đã sắp thứ tự (chưa tính WIP)
                 |
                 v
Sẵn sàng -> Phát triển -> Chờ review -> Review -> Chờ test -> Test -> Done
~~~

Hãy giải thích:

1. Những cột nào là **hàng đợi**, những cột nào là **đang xử lý**?
2. Mốc nào dùng để bắt đầu đo **cycle time**, mốc nào kết thúc?
3. “Done” có nghĩa **đạt DoD**, **đã phát hành** hay **đã được sử dụng**? Vì sao chọn?
4. Nếu một story cần quay lại phát triển sau kiểm thử, biểu diễn ra sao?
5. Những hạng mục chưa được chọn từ backlog có được tính vào WIP không?

**Gợi ý:** Không có một sơ đồ bắt buộc. Nhóm phải làm rõ **định nghĩa cột và ranh giới**, tránh trộn hạng mục chưa cam kết với công việc đã bắt đầu.

### Nhiệm vụ B — Đánh dấu blocked mà không mất trạng thái

Thẻ **PBI-308** đang ở **Chờ kiểm thử** thì môi trường tích hợp ngừng hoạt động. Hãy bổ sung:

~~~text
ID: PBI-308
Trạng thái hiện tại: Chờ kiểm thử
Blocked: Có
Lý do: Môi trường tích hợp không truy cập được dịch vụ tiến độ
Bắt đầu blocked: (ghi thời điểm thực tế)
Đầu mối hỗ trợ: (nhóm/người phù hợp)
Hành động kế tiếp: (một bước có thể thực hiện)
Xem lại: (thời điểm cụ thể)
~~~

**Câu hỏi:** Nếu nhóm chuyển thẻ sang “Blocked” rồi không ghi nó đã ở hàng chờ nào, việc phân tích nút thắt sẽ sai lệch ra sao? Nếu thẻ vẫn chưa Done, có nên âm thầm loại khỏi WIP không?

### Nhiệm vụ C — Đếm WIP và tìm hàng đợi

Giả sử bảng có:

| Trạng thái | Số thẻ |
| --- | ---: |
| Đang phát triển | 3 |
| Chờ review | 4 |
| Đang review | 1 |
| Chờ kiểm thử | 5 |
| Đang kiểm thử | 2 |

1. **Tính tổng WIP** nếu tất cả đều nằm trong workflow đang thực hiện.
2. Có bao nhiêu thẻ **đang xử lý** và bao nhiêu thẻ **đang xếp hàng**?
3. Nếu một trong năm thẻ chờ kiểm thử bị blocked, WIP có tự giảm không?
4. Nhóm có nên bắt đầu thêm một story trong khi hàng chờ kiểm thử đang dài không? Nêu điều kiện để quyết định.

**Gợi ý:** Tổng WIP là **15**; **6 thẻ đang xử lý** (3 + 1 + 2) và **9 thẻ chờ** (4 + 5). Một thẻ blocked vẫn thuộc WIP theo ranh giới của bài tập. Cần điều tra năng lực và tuổi thẻ trước khi quyết định kéo việc mới.

### Nhiệm vụ D — Tính thời gian chờ

Một thẻ mất **2 ngày phát triển, 3 ngày chờ review, 0,5 ngày review, 3 ngày chờ kiểm thử, 0,5 ngày kiểm thử và 1 ngày chờ phát hành**, theo các khoảng ngày làm việc không chồng lấn.

1. Tính **cycle time** từ lúc bắt đầu phát triển tới Done.
2. Tính **thời gian xử lý trực tiếp** và **thời gian chờ**.
3. Tính flow efficiency theo công thức thời gian xử lý/cycle time.
4. Giả sử 2 ngày trong khoảng chờ kiểm thử được ghi blocked. Có cộng thêm 2 ngày vào cycle time không?
5. Đề xuất một cải tiến để giảm chờ mà không bỏ kiểm thử hoặc hạ chất lượng.

**Đáp án tham khảo:** Cycle time **10 ngày**, xử lý trực tiếp **3 ngày**, chờ **7 ngày**, flow efficiency **30%**. Hai ngày blocked là **một phần của ba ngày chờ kiểm thử**, không được cộng thêm lần nữa.

### Nhiệm vụ E — Chọn một thử nghiệm cải tiến trong hai tuần

Nhóm thấy hàng chờ review và kiểm thử ngày càng dài. Đề xuất một thử nghiệm, chẳng hạn:

> “Giới hạn số story mới được bắt đầu; mỗi ngày ưu tiên giúp thẻ gần Done và những thẻ bị chặn lâu nhất; làm rõ tiêu chí kiểm thử trước khi chuyển sang hàng đợi.”

Hãy ghi:

- **Giả thuyết:** Vì sao thay đổi này sẽ giảm thời gian chờ?
- **Chính sách cụ thể:** Khi nào được kéo việc, ai điều phối trở ngại?
- **Tín hiệu:** Work Item Age, queue length, cycle time, throughput, lỗi sau bàn giao.
- **Thời điểm xem lại:** Sau hai tuần với dữ liệu đủ bối cảnh.
- **Điều kiện dừng hoặc sửa:** Nếu chất lượng giảm hoặc hạng mục quan trọng bị bỏ quên, phải điều chỉnh.

### Nhiệm vụ F — Thảo luận trường hợp khẩn cấp

Giả sử nhóm nhận tin một lỗ hổng đã được xác nhận có thể làm lộ dữ liệu học viên. Workflow đang đạt WIP limit.

Hãy mô tả cách:

1. Kích hoạt xử lý sự cố theo chính sách bảo mật và thẩm quyền phù hợp.
2. Thể hiện hạng mục khẩn cấp trên bảng và giải thích **việc nào sẽ bị trì hoãn**.
3. Duy trì việc kiểm chứng chất lượng và bảo vệ dữ liệu.
4. Ghi nhận tác động tới cycle time, WIP và công việc thường lệ.
5. Sau sự cố, cập nhật những cải tiến phòng ngừa vào backlog.

Không nên dùng “expedite” để bỏ qua kiểm soát an toàn hoặc làm mọi hạng mục khác biến mất khỏi số liệu.

## 18. Checklist vận hành bảng Kanban

- [ ] **Ranh giới workflow** từ bắt đầu đến kết thúc đã được công bố.
- [ ] **Đơn vị công việc** dùng để đo WIP/throughput đã thống nhất, tránh đếm story và task hai lần.
- [ ] Các trạng thái phản ánh **quy trình thực**, không chỉ tên phòng ban hoặc cảm giác “đang làm”.
- [ ] Những hàng đợi có ảnh hưởng lớn được **nhìn thấy riêng** khỏi hoạt động đang xử lý.
- [ ] Nhóm phân biệt **waiting bình thường** với **blocked** theo chính sách rõ.
- [ ] Thẻ blocked có **lý do, thời điểm, đầu mối, hành động và lúc xem lại**.
- [ ] Không che blocked bằng cách **loại thẻ khỏi WIP** khi nó vẫn chưa kết thúc.
- [ ] Các bước chuyển có **điều kiện vào/ra** để dữ liệu đáng tin cậy.
- [ ] **WIP limit** áp dụng cho vùng có ý nghĩa và được xem xét khi vượt.
- [ ] Nhóm ưu tiên **hoàn tất hạng mục đang làm** trước khi kéo thêm việc không cần thiết.
- [ ] **Tuổi hạng mục và thời gian chờ** được theo dõi, không chỉ đếm số thẻ.
- [ ] Cycle time, throughput và các chỉ số khác có **mốc đo nhất quán**.
- [ ] Khi xem bảng, nhóm chọn **hành động tháo gỡ nút thắt**, không chỉ báo cáo từng người.
- [ ] Trạng thái **Done** gắn với điều kiện chất lượng và bàn giao đã thống nhất.
- [ ] Có vòng nhận **phản hồi người dùng và vận hành** để cải tiến backlog và workflow.

## 19. Câu hỏi tự kiểm tra

1. Vì sao bảng To do – Doing – Done có thể che thời gian chờ thực tế?
2. Một workflow Kanban cần xác định những ranh giới nào trước khi đo WIP và cycle time?
3. Phân biệt cột **đang xử lý**, cột **hàng đợi** và **tín hiệu blocked**.
4. Khi nào nên tách cột “Chờ review” khỏi “Đang review”? Khi nào chia quá nhiều cột gây hại?
5. Vì sao một thẻ bị chặn nên giữ thông tin trạng thái gốc?
6. Thẻ bị chặn chưa Done có thường còn được tính vào WIP không? Vì sao?
7. Bốn thông tin tối thiểu của một thẻ blocked là gì?
8. Chính sách rõ về điều kiện chuyển cột giúp nhóm tránh những vấn đề nào?
9. Cơ chế pull khác push ở điểm nào, và vì sao có thể cải thiện dòng công việc?
10. WIP cao nhưng throughput không tăng có thể cho biết điều gì cần điều tra?
11. Work Item Age khác cycle time ra sao và hữu ích khi nào?
12. Tại sao không được cộng thời gian blocked thêm lần nữa nếu nó đã nằm trong thời gian chờ?
13. Một CFD có dải chờ kiểm thử ngày càng dày gợi ý điều gì, và vì sao chưa đủ kết luận nguyên nhân?
14. Nhóm nên làm gì khi phát sinh sự cố thật sự khẩn cấp trong lúc WIP đã đạt giới hạn?
15. Cách dùng Kanban nào hỗ trợ Daily Scrum mà không thay Sprint Goal?
16. Vì sao một bảng gọn, ít thẻ không tự động chứng minh sản phẩm có giá trị hơn?

**Ghi nhớ:** Trực quan hóa trong Kanban không dừng ở việc chuyển thẻ qua các cột. Một bảng có ích phải làm rõ **công việc đang thực sự được xử lý, những hàng đợi đang kéo dài thời gian bàn giao và các trở ngại ngăn tiến triển**. Hãy giữ trạng thái blocked minh bạch, áp dụng chính sách và giới hạn WIP có ý nghĩa, đo tuổi cùng thời gian chờ, rồi ưu tiên **hoàn tất và học từ phản hồi** thay vì liên tục bắt đầu việc mới. Giá trị của bảng Kanban nằm ở **những quyết định tốt hơn về dòng công việc và sản phẩm**, không ở số thẻ được kéo hay màu sắc của dashboard.
