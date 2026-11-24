# Sprint Planning: mục tiêu, lựa chọn công việc và cách thực hiện

Trong Scrum, một Sprint không nên bắt đầu bằng câu hỏi đơn thuần: “Ai sẽ làm ticket nào?”. Nếu chỉ chia danh sách việc cho từng cá nhân, nhóm có thể hoàn thành nhiều đầu việc rời rạc nhưng chưa tạo ra một kết quả có ý nghĩa đối với sản phẩm. **Sprint Planning** giúp toàn bộ Scrum Team cùng thống nhất **vì sao Sprint này có giá trị, những công việc nào có thể hoàn thành và nhóm dự định thực hiện chúng như thế nào**.

Ví dụ, một nhóm phát triển nền tảng học trực tuyến muốn giảm tình trạng học viên phải tìm lại bài đang học. Product Owner có một Product Backlog gồm các đề xuất về nút “Học tiếp”, đồng bộ giữa thiết bị, lời nhắc qua email và phân tích hành vi. Sprint Planning tốt không phải là cố lấy càng nhiều mục càng tốt; nó chọn một **Sprint Goal** có giá trị, cân đối năng lực và rủi ro để tạo **Increment đáp ứng Definition of Done**, rồi chuẩn bị một kế hoạch đủ dùng để Developers bắt đầu và thích ứng trong Sprint.

Bài học thuộc chương **Sự kiện Scrum** trong module **AGILE_DEVELOPMENT**, kết nối giá trị Agile với phản hồi sớm, giao sản phẩm tăng dần, user story, Product Backlog, Scrum, Kanban, XP và đo lường dòng công việc. Trọng tâm là thực hành Sprint Planning đúng tinh thần Scrum: có định hướng chung, thực tế về khả năng hoàn thành và có quyền điều chỉnh theo điều học được.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích mục đích, thành phần tham gia, timebox và đầu ra của Sprint Planning theo Scrum Guide.
2. Phân biệt ba chủ đề **Why — What — How** và diễn đạt chúng thành một **Sprint Backlog** có thể dùng trong công việc hằng ngày.
3. Viết Sprint Goal kết nối Product Goal với giá trị của Sprint mà không đồng nhất mục tiêu với danh sách ticket.
4. Giải thích trách nhiệm của Product Owner, Developers và Scrum Master khi chọn Product Backlog Items (PBIs), lập kế hoạch và xử lý phụ thuộc.
5. Dùng năng lực thực tế, Definition of Done, dữ liệu công việc, rủi ro và độ bất định để lựa chọn phạm vi hợp lý.
6. Tổ chức một phiên Sprint Planning thực hành, có các câu hỏi, bảng minh họa, kế hoạch hành động và cách kiểm tra mức sẵn sàng.
7. Tránh các phản mẫu như áp chỉ tiêu story point, phân việc từ trên xuống, biến Sprint Goal thành bảng kiểm, hoặc giảm chất lượng khi hết thời gian.

## 2. Sprint Planning nằm ở đâu trong Scrum?

Scrum là một framework nhẹ giúp con người giải quyết những vấn đề phức tạp theo hướng thích ứng và tạo giá trị. Scrum dựa trên **empiricism** — đưa quyết định từ những gì quan sát được — cùng ba trụ cột **minh bạch, kiểm tra, thích ứng**.

Một Sprint có thời lượng cố định **không quá một tháng**. Sprint mới bắt đầu ngay khi Sprint trước kết thúc. Trong Sprint, Scrum Team hướng đến một Sprint Goal và tạo ra những Increment đáp ứng Definition of Done. Các sự kiện Scrum tạo nhịp để nhóm kiểm tra và điều chỉnh:

~~~mermaid
flowchart LR
    A["Product Goal<br/>và Product Backlog"] --> B["Sprint Planning<br/>Why · What · How"]
    B --> C["Sprint Goal<br/>và Sprint Backlog"]
    C --> D["Developers tạo Increment<br/>kiểm tra/thích ứng mỗi ngày"]
    D --> E["Sprint Review<br/>kiểm tra sản phẩm cùng bên liên quan"]
    E --> F["Sprint Retrospective<br/>cải tiến cách làm"]
    F --> G["Sprint tiếp theo"]
    G --> B
    D -. "Increment đạt Done<br/>có thể phát hành sớm" .-> H["Người dùng và phản hồi"]
    H -. "Thông tin mới" .-> A
~~~

Đây là sơ đồ quan hệ, không phải yêu cầu cứng rằng phản hồi chỉ được thu vào cuối Sprint. Một Increment đạt Definition of Done có thể được phát hành trước Sprint Review; việc trao đổi, kiểm tra và thích ứng diễn ra liên tục.

**Sprint Planning khởi động Sprint** bằng việc đặt nền tảng cho công việc sắp tới. Nó không nhằm chốt mọi chi tiết cho đến ngày cuối, cũng không phải thời điểm người quản lý giao việc cho từng thành viên.

### Sự kiện này có giới hạn thời gian bao lâu?

Theo *Scrum Guide 2020*, Sprint Planning có timebox **tối đa 8 giờ với Sprint một tháng**. Sprint ngắn hơn thường có Sprint Planning ngắn hơn. Đây là **giới hạn trên**, không phải yêu cầu phải dùng hết tám giờ hay công thức bắt buộc để chia thời lượng theo tỷ lệ.

Ví dụ, một nhóm có Sprint hai tuần có thể tổ chức phiên khoảng 2–3 giờ nếu thông tin đã được chuẩn bị đầy đủ. Nhóm khác cần lâu hơn để xử lý nhiều bất định, miễn việc tổ chức thực sự có ích và nằm trong giới hạn phù hợp. Không có quy tắc Scrum chính thức “Sprint hai tuần phải họp đúng 4 giờ”.

## 3. Ba câu hỏi bắt buộc của Sprint Planning: Why, What, How

Scrum Guide tổ chức Sprint Planning xoay quanh ba chủ đề. Chúng **có liên hệ, không phải ba cuộc họp độc lập bắt buộc**.

| Chủ đề | Câu hỏi | Người đóng góp chính | Kết quả cần làm rõ |
| --- | --- | --- | --- |
| **Why — Vì sao Sprint này có giá trị?** | Sprint tới có thể giúp sản phẩm tiến gần Product Goal như thế nào? | Product Owner đề xuất giá trị; toàn Scrum Team cùng xây Sprint Goal | **Sprint Goal** rõ, có thể dùng định hướng khi xuất hiện thay đổi |
| **What — Có thể hoàn tất những gì?** | Những PBI nào có thể đạt Done trong Sprint với năng lực và thông tin hiện có? | **Developers lựa chọn PBIs** thông qua trao đổi với Product Owner | Tập PBI được chọn, phản ánh dự báo thực tế và giá trị |
| **How — Công việc đã chọn sẽ được thực hiện thế nào?** | Cách tạo một Increment đáp ứng Definition of Done là gì? | **Developers lập kế hoạch thực hiện** và tổ chức công việc | Kế hoạch đủ hành động, có phụ thuộc, kiểm thử, tích hợp, rủi ro |

Đầu ra tổng hợp là **Sprint Backlog**, gồm:

1. **Sprint Goal — Why:** mục đích chung, lời cam kết định hướng cho Sprint.
2. **Những Product Backlog Items được chọn — What:** phạm vi mà Developers dự báo có thể hoàn thành.
3. **Kế hoạch thực hiện — How:** cách Developers dự định tạo Increment đạt Definition of Done.

Sprint Backlog là **kế hoạch bởi và dành cho Developers**, có thể nhìn thấy theo thời gian thực. Nó được cập nhật trong suốt Sprint khi nhóm học được điều mới; không phải hợp đồng bất biến được ký tại Sprint Planning.

## 4. Chuẩn bị trước khi bắt đầu Sprint Planning

Không nhất thiết phải có một buổi “pre-planning” hay biểu mẫu cố định. Tuy nhiên, phiên Sprint Planning sẽ hiệu quả hơn nếu Scrum Team đã làm rõ những thông tin quan trọng.

| Cần chuẩn bị | Mục đích | Cách kiểm tra |
| --- | --- | --- |
| **Product Goal hiện tại** | Giữ định hướng giá trị dài hơn một Sprint | Scrum Team hiểu sản phẩm đang muốn đạt trạng thái nào |
| **Product Backlog được sắp xếp thứ tự** | Thấy được các lựa chọn giá trị nhất cần cân nhắc | Product Owner giải thích được vì sao các mục được ưu tiên |
| **Thông tin từ Sprint Review và người dùng** | Tránh lập kế hoạch theo giả định đã lỗi thời | Có số liệu, phản hồi và giới hạn bằng chứng cần thiết |
| **Các PBI quan trọng được refinement đủ dùng** | Có thể trao đổi phạm vi, ví dụ và rủi ro | Developers hiểu hành vi mong muốn, các quy tắc quan trọng và câu hỏi còn mở |
| **Definition of Done** | Đánh giá phạm vi có thể giao với chất lượng phù hợp | Những tiêu chuẩn tổ chức/Scrum Team áp dụng được biết rõ |
| **Năng lực Sprint tới** | Tránh nhận việc như thể mọi người có 100% thời gian cho tính năng | Biết lịch nghỉ, việc vận hành, phụ thuộc, hỗ trợ và năng lực thực tế |
| **Lịch sử và trạng thái flow** | Cải thiện dự báo dựa trên thực tế | Có thể tham khảo PBI Done ở Sprint trước, throughput, cycle time, việc bị chặn |
| **Rủi ro và phụ thuộc lớn** | Không chọn phạm vi dựa trên giả định vô căn cứ | Biết hệ thống, bên liên quan hoặc quyết định nào có thể gây chậm |

### Refinement không phải một sự kiện Scrum bắt buộc có timebox riêng

**Product Backlog refinement** là hoạt động liên tục làm các PBI nhỏ hơn, rõ hơn, bổ sung thông tin và ước lượng nếu nhóm thấy hữu ích. Scrum Guide không quy định một cuộc họp refinement bắt buộc kéo dài chính xác bao nhiêu giờ, cũng không yêu cầu mọi PBI phải có tài liệu đặc tả đầy đủ trước Sprint Planning.

**Definition of Ready (DoR)** có thể là chính sách làm việc do nhóm lựa chọn, nhưng **không phải artifact hoặc commitment chính thức trong Scrum Guide**. Một checklist “ready” không nên trở thành cánh cổng hành chính cứng khiến nhóm không thể học từ những việc còn bất định. Với những PBI quá mơ hồ, hãy làm rõ hoặc thu hẹp phạm vi, không giả vờ rằng đã hiểu.

## 5. Who: Ai tham gia và ai có quyền quyết định?

**Toàn bộ Scrum Team tham gia Sprint Planning:** Product Owner, Scrum Master và Developers. Scrum Team có thể mời người khác tham dự để cung cấp lời khuyên hoặc bối cảnh cần thiết.

| Trách nhiệm | Đóng góp trong Sprint Planning | Không nên làm |
| --- | --- | --- |
| **Product Owner** | Đảm bảo người tham gia sẵn sàng trao đổi những PBI quan trọng nhất và mối liên hệ với Product Goal; đề xuất cách Sprint tăng giá trị sản phẩm; giải thích ưu tiên, điều kiện nghiệp vụ và trao đổi phạm vi | Quyết thay Developers về số PBI có thể hoàn thành hoặc tự phân việc kỹ thuật |
| **Developers** | Cùng xây Sprint Goal; **chọn PBI** qua trao đổi với Product Owner; đánh giá năng lực, rủi ro, Definition of Done; **thiết kế kế hoạch thực hiện** | Nhận quá nhiều việc để đạt chỉ tiêu; coi PBI chưa Done là đã hoàn thành |
| **Scrum Master** | Hỗ trợ mọi người hiểu và thực hành Scrum, bảo đảm sự kiện diễn ra tích cực, hiệu quả và trong timebox; giúp xử lý những trở ngại trong cách phối hợp | Biến mình thành người giao việc hoặc bắt buộc tất cả các nhóm dùng một mẫu lập kế hoạch |
| **Người được mời tư vấn** | Cung cấp thông tin về người dùng, thiết kế, bảo mật, phụ thuộc, vận hành hoặc sản phẩm | Thay thế trách nhiệm lựa chọn và lập kế hoạch của Scrum Team |

**Product Owner tối đa hóa giá trị và quản lý Product Backlog; Developers dự báo phạm vi và tự tổ chức cách tạo Increment.** Hai loại trách nhiệm này bổ sung cho nhau. Một bên không nên dùng quyền chức danh để che khuất bằng chứng hoặc chuyên môn của bên còn lại.

Nếu tổ chức có engineering manager, trưởng dự án hoặc người quản lý nhân sự, họ vẫn có vai trò về nguồn lực, chính sách và tháo gỡ trở ngại. Nhưng các vai trò đó không mặc nhiên trở thành accountabilities mới trong Scrum Team, và không nên biến Sprint Planning thành cuộc họp quản lý giao task.

## 6. WHY — Tạo Sprint Goal giúp Sprint có giá trị

**Sprint Goal** là mục tiêu duy nhất của Sprint; nó là commitment gắn với Sprint Backlog. Mục tiêu giúp Scrum Team hiểu vì sao những việc đã chọn lại quan trọng và cho phép linh hoạt về cách thực hiện khi có thông tin mới.

Trong Sprint Planning, Product Owner **đề xuất** cách sản phẩm có thể tăng giá trị và mức hữu ích trong Sprint tới. Sau đó, **toàn bộ Scrum Team cộng tác xác định Sprint Goal**, và Sprint Goal phải được chốt trước khi Sprint Planning kết thúc.

### Ví dụ phân biệt Sprint Goal tốt và chưa tốt

| Cách viết | Đánh giá | Vì sao? |
| --- | --- | --- |
| “Hoàn thành 20 story point” | Chưa tốt | Đo khối lượng ước lượng, không nói về người dùng hoặc kết quả |
| “Làm PBI-12, PBI-18, PBI-23” | Chưa tốt | Chỉ sao chép danh sách hạng mục; khó chọn phương án khi phạm vi đổi |
| “Triển khai API, UI và database” | Chưa tốt | Mô tả các lớp kỹ thuật, chưa nói hành vi hay giá trị tạo ra |
| “Cho phép học viên đã đăng nhập tiếp tục đúng bài đang dở từ trang khóa học trên cùng thiết bị, bảo vệ tiến độ cá nhân” | Tốt trong bối cảnh minh họa | Có đối tượng, hành vi có ích, ranh giới và chất lượng quan trọng |
| “Giảm trở ngại để học viên mới tiếp tục bài thứ hai; xác minh bằng quan sát hành vi của nhóm dùng thử” | Có triển vọng khi khả năng đo phù hợp | Gắn nhu cầu sản phẩm với việc học; cần làm rõ Increment sẽ cung cấp điều gì |

Không có một cú pháp bắt buộc cho Sprint Goal. Mục tiêu nên **ngắn, hiểu được, có giá trị và đủ linh hoạt** để Developers có thể thương lượng lại chi tiết phạm vi mà vẫn giữ ý nghĩa chung.

### Sprint Goal khác Product Goal và Definition of Done ra sao?

| Commitment | Gắn với artifact | Mục đích |
| --- | --- | --- |
| **Product Goal** | Product Backlog | Mô tả trạng thái tương lai của sản phẩm mà Scrum Team hướng tới |
| **Sprint Goal** | Sprint Backlog | Mục tiêu chung tạo sự tập trung và gắn kết trong một Sprint |
| **Definition of Done** | Increment | Mô tả chính thức trạng thái Increment khi đạt các tiêu chuẩn chất lượng cần có |

Ví dụ: Product Goal là “Giúp học viên mới tiếp tục lộ trình học thuận tiện”; Sprint Goal là “Cho phép học viên mở lại bài đang dở trên cùng thiết bị”; Definition of Done yêu cầu các Increment có kiểm thử và chất lượng cần thiết. Đó là ba cấp độ khác nhau, không thay thế nhau.

### Sprint Goal không phải bảo đảm rằng outcome sẽ tăng ngay

Nếu Sprint Goal liên quan giảm khó khăn của người học, nhóm vẫn phải tạo Increment sử dụng được và thu thập bằng chứng. Tỷ lệ quay lại sau bảy ngày có thể chưa đủ cửa sổ quan sát ở cuối Sprint. Hãy phân biệt **mục tiêu giá trị**, **phần mềm giao được trong Sprint** và **bằng chứng outcome cần tiếp tục theo dõi**; không dùng một số liệu đo chưa đầy đủ để tuyên bố thành công.

## 7. WHAT — Developers lựa chọn những Product Backlog Items có thể Done

Sau khi hiểu Sprint có giá trị ở đâu, Developers trao đổi với Product Owner để chọn **các PBI có thể hoàn tất trong Sprint**. Đây là **dự báo phạm vi**, không phải Product Owner tự ấn định số lượng hay cấp trên giao việc cho từng người.

### Các yếu tố phải cân nhắc

1. **Mối liên hệ với Sprint Goal:** PBI được chọn có giúp đạt kết quả chung không? Nếu không, vì sao nó cần ở Sprint này?
2. **Thứ tự Product Backlog:** Product Owner đã sắp xếp theo giá trị, rủi ro và định hướng sản phẩm; mọi thay đổi cần có trao đổi.
3. **Năng lực thực tế:** thành viên nghỉ phép, trực sự cố, hỗ trợ nhóm khác, onboarding và những nhiệm vụ bắt buộc.
4. **Kích thước và độ rõ:** các PBI đã được chia đủ nhỏ để tạo lát cắt giá trị, có tiêu chí chấp nhận và rủi ro quan trọng chưa?
5. **Definition of Done:** dự báo phải tính cả phân quyền, kiểm thử, tích hợp, triển khai cần thiết và chất lượng, không chỉ giờ viết mã.
6. **Phụ thuộc:** API ngoài, môi trường, thiết kế, quyền truy cập và quyết định của đơn vị khác đã có kế hoạch xử lý chưa?
7. **Dữ liệu lịch sử:** số lượng PBIs Done, thời gian hoàn thành, các việc kéo dài, sự thay đổi về loại công việc và năng lực.

### Ví dụ ước lượng khả năng lựa chọn

Giả sử Scrum Team có bốn Developers trong Sprint hai tuần, nhưng hai người phải luân phiên xử lý sự cố và một người nghỉ hai ngày. Không thể tính máy móc “4 người × 10 ngày = 40 ngày công cho tính năng”. Cần trừ những trách nhiệm đã biết, xem công việc tích hợp, thời gian kiểm thử và sự biến thiên thực tế.

| Thông tin | Ví dụ minh họa | Diễn giải |
| --- | --- | --- |
| Hai Sprint trước Done lần lượt 5 và 4 story tương đối đồng dạng | Có lịch sử tham khảo | Không có nghĩa Sprint này chắc chắn Done 4–5 story |
| Sprint tới thiếu người một phần thời gian | Năng lực thấp hơn một số Sprint trước | Nên thận trọng với dự báo giữ nguyên |
| Một PBI tích hợp API mới có phụ thuộc bên ngoài | Độ bất định cao | Cân nhắc giảm phạm vi, xác minh phụ thuộc sớm |
| Sprint Goal chỉ cần một luồng học tiếp hoàn chỉnh | Có thể ưu tiên lát cắt dọc | Không bắt buộc lấp đầy Sprint bằng mọi item sẵn có |

**Velocity hoặc story points không phải thước đo bắt buộc của Scrum.** Nếu nhóm dùng story points để dự báo nội bộ, hãy dùng cùng ngữ cảnh nhóm và tránh coi điểm số là cam kết năng suất. Cũng có thể dựa trên throughput, cycle time và hiểu biết thực tế của Developers.

### Chọn ít hơn nhưng có thể dùng được

Một backlog item dạng “Tạo bảng lưu tiến độ” chưa chắc mang giá trị độc lập. Thay vì nhận ba ticket tầng kỹ thuật như ba story riêng, Developers có thể chọn một PBI dọc: “Học viên đã đăng nhập mở lại đúng bài dở từ trang khóa học”. Trong kế hoạch thực hiện, nhóm chia thành task UI, API, dữ liệu, test và giám sát — tất cả phục vụ một hành vi có thể kiểm tra.

Chọn phạm vi hẹp **không có nghĩa bỏ yêu cầu an toàn**. Phân quyền, bảo vệ dữ liệu tiến độ, kiểm thử bắt buộc và Definition of Done vẫn áp dụng với phần được giao.

## 8. HOW — Developers xác định kế hoạch tạo Increment

Scrum Guide quy định Developers **lập kế hoạch công việc cần thiết để tạo Increment đáp ứng Definition of Done**. Họ có thể phân rã PBI thành các việc nhỏ, thường khoảng một ngày hoặc ít hơn để tiện phối hợp, nhưng đó là **gợi ý thực hành chứ không phải giới hạn cứng bắt buộc**. Cách chuyển PBI thành Increment thuộc quyền quyết định của Developers.

Một kế hoạch thực hành nên đủ rõ để nhóm **bắt đầu được và biết cách cập nhật khi có thông tin mới**.

### Các câu hỏi thiết yếu của phần How

| Câu hỏi | Ví dụ với tính năng “Học tiếp” |
| --- | --- |
| Hành vi đầu-cuối là gì? | Học viên mở trang khóa học → thấy nút → chọn → mở đúng bài tại điểm dừng |
| Cần phối hợp những thành phần nào? | Giao diện, API tiến độ, dữ liệu, xác thực, kiểm thử, monitoring |
| Quy tắc bắt buộc? | Chỉ xem/sửa tiến độ tài khoản hiện tại; không mở nội dung hết quyền |
| Kiểm thử thế nào? | Trường hợp có tiến độ, chưa có tiến độ, hết quyền, dữ liệu lỗi, chuyển trang |
| Tích hợp và kiểm tra khi nào? | Tích hợp thường xuyên; kiểm thử tự động từ những lát cắt sớm |
| Phụ thuộc nào cần xử lý đầu tiên? | API định nghĩa tiến độ hoặc quyền cấp môi trường thử |
| Điểm cần học sớm? | Người học có tìm thấy nút không; khôi phục vị trí có đủ tin cậy không |
| Phần nào có thể phát hành khi Done? | Luồng trên cùng thiết bị cho nhóm người dùng phù hợp, có cơ chế quan sát |

Một cách lập kế hoạch tốt là **dựng luồng đi xuyên hệ thống sớm** rồi mở rộng quy tắc, kiểm thử và hoàn thiện. Điều này giảm nguy cơ đến ngày cuối mới phát hiện UI và API không tích hợp được.

### Ví dụ phân rã một PBI dọc

~~~text
PBI: Học viên tiếp tục đúng bài đang dở
  ├─ Thống nhất ví dụ nghiệp vụ, giới hạn hành vi và phân quyền
  ├─ Làm rõ hợp đồng đọc/ghi tiến độ và dữ liệu kiểm thử
  ├─ Hoàn thiện một luồng API + giao diện nhỏ nhất có thể chạy
  ├─ Kiểm thử truy cập đúng tài khoản, dữ liệu lỗi và trạng thái bài
  ├─ Chạy CI, kiểm thử tích hợp và review theo Definition of Done
  ├─ Ghi nhận sự kiện học tiếp và lỗi quan trọng theo chính sách dữ liệu
  └─ Xác nhận hành vi end-to-end và chuẩn bị phản hồi người dùng
~~~

Các dòng dưới PBI là **công việc Developers phối hợp thực hiện**, không tự động là những user story độc lập. Nhóm có thể thay đổi thứ tự, tách nhỏ hoặc ghép task trong Sprint.

### Kế hoạch không được biến thành “vẽ tương lai tuyệt đối”

Với các thành phần còn bất định, nhóm nên chỉ rõ **phép kiểm chứng sớm** và điểm quyết định. Ví dụ: “Trong ngày đầu kiểm tra API có trả về vị trí học hợp lệ dưới điều kiện mất kết nối không. Nếu không, trao đổi với Product Owner để điều chỉnh phạm vi phục hồi và rủi ro”. Không cần giả vờ biết chắc thời lượng của mọi task từ đầu Sprint.

## 9. Sprint Backlog: bản kết quả cụ thể của Sprint Planning

Sprint Backlog gồm **Sprint Goal, các PBI được chọn và kế hoạch để thực hiện**. Nó được hình thành trong Sprint Planning và được cập nhật suốt Sprint theo cách Developers cần để đạt Sprint Goal.

~~~mermaid
flowchart TD
    A["Product Goal và Product Backlog"] --> B["Sprint Planning"]
    B --> C["Sprint Goal<br/>WHY — vì sao"]
    B --> D["Các PBI được chọn<br/>WHAT — làm gì"]
    B --> E["Kế hoạch Developers<br/>HOW — như thế nào"]
    C --> F["Sprint Backlog<br/>kế hoạch bởi và dành cho Developers"]
    D --> F
    E --> F
    F --> G["Kiểm tra và cập nhật<br/>trong Sprint"]
    G -. "Thông tin mới" .-> F
~~~

| Thành phần Sprint Backlog | Ví dụ | Khi được phép điều chỉnh? |
| --- | --- | --- |
| **Sprint Goal** | “Học viên hợp lệ tiếp tục bài đang dở trên cùng thiết bị” | Là commitment định hướng; không tùy tiện đổi mục tiêu để hợp thức hóa việc đã làm |
| **PBI được chọn** | Luồng tiếp tục bài; trường hợp bắt đầu lần đầu; phần đo tín hiệu liên quan nếu phù hợp | Phạm vi có thể được làm rõ và thương lượng với Product Owner nếu có thêm hiểu biết |
| **Kế hoạch thực hiện** | Thứ tự thử hợp đồng API, kiểm thử phân quyền, tích hợp, phát hành an toàn | Developers có thể cập nhật hằng ngày khi công việc tiến triển |

Trong Sprint, **không thực hiện những thay đổi gây nguy hại cho Sprint Goal**, **không làm giảm chất lượng**, và **có thể làm rõ, thương lượng lại phạm vi với Product Owner** khi biết thêm thông tin. Nếu Sprint Goal thật sự trở nên lỗi thời, Scrum Guide cho phép **chỉ Product Owner có thẩm quyền hủy Sprint**; đó là tình huống ngoại lệ, không phải phản ứng với mọi khó khăn nhỏ.

## 10. Kịch bản chi tiết: Sprint Planning cho tính năng “Học tiếp”

Tất cả tên PBI và con số ở phần này là **ví dụ giả định để học**, không phải số liệu của một dự án thực.

### 10.1. Bối cảnh sản phẩm

**Product Goal:** Học viên mới có thể tiếp tục lộ trình học thuận tiện và tin cậy hơn.

**Phản hồi trước Sprint:** Trong một số phiên quan sát, học viên mất nhiều bước để tìm lại bài đang học; nhóm chưa có bằng chứng chắc chắn về hiệu quả của email nhắc học. Đồng thời, lỗi đọc sai tiến độ giữa phiên đăng nhập là rủi ro cần phòng tránh.

**Sprint:** Hai tuần làm việc; Scrum Team có Product Owner, Scrum Master và bốn Developers. Lịch nghỉ, trực vận hành, phụ thuộc môi trường được trao đổi ngay khi chọn phạm vi.

### 10.2. Product Backlog được sắp xếp thứ tự

| PBI | Nhu cầu/kết quả | Tình trạng/rủi ro | Gợi ý cân nhắc |
| --- | --- | --- | --- |
| **PBI-101** | Học viên có bài dở mở lại đúng bài từ trang khóa học | Có đủ mô tả luồng; cần bảo đảm phân quyền và dữ liệu hợp lệ | Trọng tâm của Sprint Goal |
| **PBI-102** | Học viên chưa có tiến độ được hướng dẫn bắt đầu bài đầu tiên | Quy tắc tương đối rõ, có thể triển khai độc lập khi đạt chất lượng | Có thể chọn nếu còn năng lực |
| **PBI-103** | Ghi nhận hành vi học tiếp và tín hiệu lỗi theo quy tắc dữ liệu | Cần thiết để quan sát kết quả; phải tránh dữ liệu nhạy cảm | Kết hợp với PBI chính hoặc hạng mục riêng theo cách tổ chức |
| **PBI-104** | Học viên tiếp tục trên thiết bị khác | Có rủi ro đồng bộ và cập nhật cạnh tranh | Nên làm rõ/kiểm chứng trước khi cam kết mở rộng |
| **PBI-105** | Khôi phục tiến độ khi mất mạng | Bất định kỹ thuật và vận hành cao | Chưa phải lát cắt đầu nếu chưa có cách xử lý an toàn |
| **PBI-106** | Gửi email nhắc học tự động | Giá trị chưa được xác nhận | Cần nghiên cứu nhu cầu, chưa nhất thiết ưu tiên xây |

### 10.3. WHY — Chọn mục tiêu Sprint

Product Owner đề xuất: “Sprint này chúng ta nên giúp người học quay lại đúng vị trí mà họ đã dừng, thay vì xây thêm kênh nhắc học chưa được xác nhận”.

Sau thảo luận, toàn Scrum Team thống nhất:

> **Sprint Goal:** “Học viên đã đăng nhập và còn quyền học có thể từ trang khóa học mở lại đúng bài đang dở trên cùng thiết bị, với tiến độ cá nhân được bảo vệ”.

Sprint Goal tập trung vào một kết quả người dùng thực sự nhận được. Nó cho phép nhóm thay đổi thiết kế nút, cách lưu dữ liệu hoặc cách chia task khi có bằng chứng mới, miễn vẫn bảo vệ mục tiêu và chất lượng.

### 10.4. WHAT — Developers chọn phạm vi

Developers xem năng lực thực tế, các rủi ro đã biết và Definition of Done rồi trao đổi với Product Owner để **chọn PBI-101**, kết hợp phần đo lường và kiểm soát cần thiết từ PBI-103. PBI-102 có thể là lựa chọn tiếp theo nếu hoàn tất phần chính và vẫn còn năng lực; PBI-104/105/106 chưa được hứa sẽ Done trong Sprint này.

Lý do chọn như vậy:

- PBI-101 trực tiếp phục vụ Sprint Goal.
- Bắt đầu từ luồng một thiết bị làm giảm phạm vi đồng bộ nhưng không được bỏ qua phân quyền và bảo vệ tiến độ.
- Cách đo cơ bản giúp quan sát người dùng sau phát hành.
- Công việc nhiều thiết bị hoặc offline cần giảm bất định kỹ thuật trước khi nhận vào Sprint.

**Không coi việc chưa chọn một PBI là thất bại**. Product Backlog vẫn là danh sách được ưu tiên và có thể thay đổi theo phản hồi.

### 10.5. HOW — Phác thảo kế hoạch

| Giai đoạn minh họa | Công việc Developers dự định thực hiện | Tín hiệu/tiêu chí kiểm tra |
| --- | --- | --- |
| **Đầu Sprint** | Xác nhận ví dụ nghiệp vụ; kiểm tra cơ chế lưu tiến độ, phân quyền và môi trường | Có luồng end-to-end nhỏ; rủi ro lớn được nhìn thấy |
| **Trong quá trình xây** | Làm UI và API theo lát cắt dọc, chạy CI và kiểm thử từng thay đổi | Tích hợp được thường xuyên; lỗi được phát hiện sớm |
| **Khi mở rộng hành vi** | Kiểm thử trạng thái bài đang dở, không có tiến độ và hết quyền trong phạm vi áp dụng | Các trường hợp bắt buộc được xử lý đúng |
| **Trước khi gọi Done** | Kiểm tra acceptance criteria, Definition of Done, log và khả năng quan sát | Increment sử dụng được, không lộ tiến độ giữa tài khoản |
| **Khi an toàn để thử** | Cùng Product Owner đưa bản phù hợp tới nhóm học viên được chọn | Có dữ liệu và quan sát về hành vi “Học tiếp” |

Đây là **kế hoạch ban đầu**, không phải lịch cứng buộc phải hoàn tất mỗi hàng vào một ngày cố định. Nếu API không đáp ứng điều kiện tính đúng đắn, nhóm phải điều chỉnh cách thực hiện và trao đổi phạm vi, không bỏ kiểm thử để giữ biểu đồ tiến độ đẹp.

### 10.6. Sprint Backlog tóm tắt

~~~text
SPRINT GOAL (Why)
  Học viên hợp lệ có thể mở đúng bài đang dở từ trang khóa học
  trên cùng thiết bị mà không lộ tiến độ cá nhân.

SELECTED PRODUCT BACKLOG ITEMS (What)
  PBI-101: Luồng "Học tiếp" end-to-end đạt Done
  Phần đo lường/kiểm tra đi kèm cần thiết của PBI-103
  PBI-102: tùy năng lực và quyết định tại Planning; không tự thêm vào cam kết

ACTIONABLE PLAN (How)
  Làm rõ quy tắc và ví dụ → kiểm chứng hợp đồng dữ liệu
  → triển khai lát cắt UI/API → tích hợp và kiểm thử liên tục
  → kiểm tra phân quyền/điều kiện biên → xác nhận Done
  → quan sát người dùng, cập nhật thông tin cho Product Owner

RISKS / FOLLOW-UP
  Đồng bộ hai thiết bị và offline nằm ngoài phạm vi đang giao,
  nhưng không được để phát sinh mất dữ liệu trong luồng đã hỗ trợ.
~~~

Nếu PBI-102 được chọn tại Sprint Planning, nó phải xuất hiện trong Sprint Backlog; nếu chỉ là khả năng cân nhắc khi còn thời gian, nên thể hiện là một lựa chọn của Product Backlog thay vì viết mập mờ thành phạm vi đã nhận.

## 11. Làm rõ acceptance criteria và Definition of Done

Sprint Planning không cần biến thành buổi viết toàn bộ đặc tả, nhưng nhóm phải hiểu đủ điều kiện để dự báo và bắt đầu công việc. Với PBI-101, dùng ví dụ cụ thể giúp tránh tranh cãi về “đúng tiến độ”:

~~~gherkin
Feature: Tiếp tục bài đang học

  Scenario: Mở lại bài đang dở
    Given học viên đã đăng nhập và còn quyền vào khóa học K
      And học viên đang học dở bài B trong khóa học K
      And hệ thống đã lưu một vị trí học hợp lệ
    When học viên mở trang khóa học K và chọn "Học tiếp"
    Then hệ thống mở bài B tại vị trí đã lưu
      And không hiển thị tiến độ của tài khoản khác

  Scenario: Người dùng không còn quyền học
    Given học viên không còn quyền truy cập khóa học K
    When học viên yêu cầu mở lại bài B trong khóa học K
    Then hệ thống không trả về nội dung được bảo vệ của bài B
      And hiển thị phản hồi từ chối truy cập phù hợp
~~~

| Thành phần | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Acceptance criteria** | Hành vi của PBI này cần đúng thế nào? | Nút mở đúng bài; từ chối truy cập khi hết quyền |
| **Definition of Done** | Điều kiện chất lượng chung để Increment là Done? | Kiểm thử tự động phù hợp, review, tích hợp, bảo mật, tài liệu/giám sát theo chuẩn áp dụng |
| **Outcome cần theo dõi** | Hành vi người học có cải thiện sau giao hàng? | Thời gian tìm lại bài, tỷ lệ mở đúng bài, lỗi tiến độ |

Một PBI đáp ứng acceptance criteria và Definition of Done không tự động chứng minh giá trị kinh doanh lâu dài. Nhóm cần phản hồi sản phẩm sau phát hành để điều chỉnh tiếp.

**Không bao giờ đưa bảo mật hoặc bảo toàn dữ liệu sang “Sprint sau” nếu phần giao hiện tại đã có thể gây hại.** Những quy tắc bắt buộc phải có ở Increment được xem là Done.

## 12. Cân đối năng lực, dự báo và rủi ro trong Sprint Planning

Lập kế hoạch thích ứng cần **ước lượng có điều kiện**, không biến dự báo thành sự chắc chắn giả.

### Một số nguồn bất định

| Nguồn | Dấu hiệu | Cách xử lý phù hợp |
| --- | --- | --- |
| **Nhu cầu chưa rõ** | Hai bên hiểu “Học tiếp” theo hai hành vi khác nhau | Dùng ví dụ, quan sát người dùng hoặc thu hẹp câu chuyện |
| **Rủi ro kỹ thuật** | Đồng bộ tiến độ có thể ghi đè khi retry | Kiểm thử kịch bản rủi ro sớm; cân nhắc spike có timebox |
| **Phụ thuộc tổ chức** | Cần quyền vào môi trường kiểm thử hoặc API của nhóm khác | Làm rõ người chịu trách nhiệm, thời điểm, phương án thay thế |
| **Năng lực biến động** | Có trực sự cố hoặc thành viên nghỉ | Giảm phạm vi dự báo, không “mượn” thời gian chưa chắc có |
| **Chất lượng chưa đủ** | Pipeline đỏ, bộ kiểm thử không đáng tin | Dành công sức sửa điều kiện chất lượng trước khi tuyên bố Done |
| **Phạm vi tăng** | Trong Sprint phát hiện quy tắc nghiệp vụ bắt buộc | Trao đổi Product Owner để sắp xếp lại phạm vi, giữ Sprint Goal |

### Dữ liệu giúp đặt câu hỏi, không thay quyết định của Developers

Nếu hai Sprint vừa qua hoàn tất 4 và 5 PBI, đó là thông tin tham khảo. Cần hiểu kích thước, loại việc, những tuần thiếu người, nợ kỹ thuật và Definition of Done trước khi áp dụng cho Sprint mới. Khi bối cảnh thay đổi, dùng một trung bình đơn giản để ép nhóm nhận đúng năm PBI có thể gây quá tải.

Trong hệ thống Kanban, các chỉ số như **WIP, throughput, cycle time và work item age** giúp Developers phát hiện việc đang bị chặn và mức biến thiên của dòng công việc. Scrum Team có thể dùng các số đo này **bên trong Scrum** để cải thiện khả năng dự báo; Scrum Guide không cấm và cũng không bắt buộc một công thức đo cụ thể.

Nếu cần đưa dự báo dài hơn cho Product Owner, nhóm có thể mô tả **một khoảng hoặc xác suất đạt mốc thời gian** dựa trên dữ liệu phù hợp; đừng ép Sprint Planning thành buổi hứa một ngày chắc chắn cho mọi epic chưa rõ.

## 13. Tổ chức Sprint Planning thực tế: một phiên minh họa

Với Sprint hai tuần, dưới đây là mẫu phiên khoảng **150 phút** (2 giờ 30 phút). Đây là ví dụ để thực hành, **không phải timebox con bắt buộc của Scrum Guide**.

| Phần | Thời gian gợi ý | Hoạt động | Kết quả |
| --- | ---: | --- | --- |
| **Bối cảnh sản phẩm và phản hồi mới** | 15 phút | Product Owner nhắc Product Goal, những thay đổi từ Sprint Review, dữ liệu người dùng | Cùng hiểu cơ hội giá trị |
| **Why: chốt Sprint Goal** | 25 phút | Thảo luận mục tiêu khả thi, giá trị và ranh giới; toàn Scrum Team thống nhất | Một Sprint Goal dùng để định hướng |
| **What: chọn PBI** | 45 phút | Developers trao đổi với Product Owner về ưu tiên, năng lực, giá trị, Done và phụ thuộc | Các PBI được chọn hợp lý |
| **Nghỉ ngắn** | 10 phút | Duy trì tập trung, xử lý nhu cầu cá nhân | Phiên tiếp tục hiệu quả |
| **How: kế hoạch thực hiện** | 45 phút | Developers phác thảo luồng dọc, thứ tự tích hợp, kiểm thử, rủi ro và phối hợp | Kế hoạch ban đầu đủ hành động |
| **Kiểm tra toàn bộ Sprint Backlog** | 10 phút | Rà mục tiêu, danh sách PBI, kế hoạch và câu hỏi chưa rõ; chốt trách nhiệm theo dõi | Minh bạch về điều đã biết, chưa biết và bước tiếp |
| **Tổng** | **150 phút** |  |  |

Không phải lúc nào cuộc họp cũng chạy tuần tự một lần qua Why, What, How. Có thể khi xem What, nhóm phát hiện mục tiêu quá rộng và phải quay lại Why; khi làm How, nhóm thấy phụ thuộc lớn và cần bớt PBI. **Một số vòng trao đổi ngắn ngay trong phiên là bình thường**.

### Một chu trình điều phối đơn giản

~~~mermaid
flowchart TD
    A["Giá trị và phản hồi mới"] --> B["Dự thảo Sprint Goal"]
    B --> C["Developers xem năng lực<br/>và lựa chọn PBI"]
    C --> D["Developers phác thảo<br/>cách đạt Done"]
    D --> E{"Sprint Goal và phạm vi<br/>có hợp lý, rõ ràng?"}
    E -->|Chưa| F["Trao đổi lại mục tiêu,<br/>phạm vi hoặc rủi ro"]
    F --> B
    E -->|Có| G["Hoàn tất Sprint Backlog<br/>bắt đầu Sprint"]
~~~

### Các câu hỏi hữu ích trước khi kết thúc phiên

- Nếu phải giải thích Sprint này bằng một câu cho người dùng, nhóm sẽ nói gì?
- Những PBI đã chọn có kết hợp tạo ra Increment mang ý nghĩa, hay chỉ là các task rời rạc?
- Điều gì có thể khiến dự báo quá lạc quan, và ta biết được dấu hiệu sớm bằng cách nào?
- Có ai cần ra quyết định ở ngoài nhóm? Ai theo dõi phụ thuộc đó?
- Nếu kết quả khác dự kiến, còn phương án nào giữ được Sprint Goal và Definition of Done?
- Developers có đủ thông tin để bắt đầu ngày mai và điều chỉnh kế hoạch trong Sprint không?

## 14. Đoạn hội thoại mẫu: thương lượng phạm vi thay vì áp đặt

**Product Owner:** “Phản hồi người học cho thấy nhiều người không tìm lại đúng bài. Tôi muốn Sprint này làm được một luồng ‘Học tiếp’ sử dụng được. Mục tiêu nào khả thi?”

**Developer A:** “Chúng tôi có thể hoàn thiện luồng đang trực tuyến trên cùng thiết bị. Đồng bộ hai thiết bị còn rủi ro ghi đè dữ liệu, nên nếu làm cả hai cùng lúc, khả năng đạt Done thấp.”

**Product Owner:** “Vậy ưu tiên luồng cùng thiết bị, nhưng cần bảo đảm không lộ tiến độ của tài khoản khác.”

**Developer B:** “Kiểm soát phân quyền là điều kiện bắt buộc từ đầu. Tôi muốn thử hợp đồng dữ liệu ngay ngày đầu và tích hợp giao diện sớm để tránh lỗi muộn.”

**Scrum Master:** “Vậy Sprint Goal sẽ diễn đạt giá trị người học như thế nào? Chúng ta có phụ thuộc nào cần xử lý ngay sau Planning?”

**Developer C:** “Chúng ta có một môi trường kiểm thử đang chờ quyền truy cập; tôi sẽ phối hợp với bộ phận hạ tầng. Chúng tôi chọn một PBI dọc và làm rõ phần đo tín hiệu đi kèm.”

**Product Owner:** “Tôi đồng ý với thứ tự ấy. Nếu còn năng lực sau khi đạt Done, chúng ta có thể trao đổi thêm chuyện gợi ý bài đầu cho người mới, nhưng không hứa trước.”

**Scrum Team:** “Sprint Goal: học viên hợp lệ có thể mở lại đúng bài đang dở từ trang khóa học trên cùng thiết bị, với tiến độ cá nhân được bảo vệ.”

Cuộc trao đổi tốt **không cần một người đọc “bản kế hoạch đúng” cho mọi người**. Nó đưa giá trị, bằng chứng, năng lực, rủi ro và chất lượng vào cùng một quyết định.

## 15. Điều gì xảy ra sau Sprint Planning?

Sprint Planning hoàn tất không có nghĩa nhóm dừng lập kế hoạch cho đến Sprint tiếp theo. Sprint Backlog **nổi lên dần và thay đổi trong suốt Sprint**.

### Daily Scrum giúp kiểm tra và điều chỉnh kế hoạch

Daily Scrum có timebox **15 phút**, dành cho **Developers** kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh Sprint Backlog khi cần. Developers có thể trao đổi sâu hơn ngay sau Daily Scrum để giải quyết vấn đề kỹ thuật. Nó không phải buổi báo cáo tiến độ riêng cho quản lý.

### Khi phát hiện việc khó hơn dự kiến

Giả sử ngày thứ ba nhóm phát hiện dữ liệu tiến độ cũ có trường hợp không hợp lệ. Developers trao đổi với Product Owner:

1. Đây có phải quy tắc bắt buộc để Increment an toàn không?
2. Có thể giảm phạm vi nâng cao khác mà vẫn đạt Sprint Goal không?
3. Cần phối hợp thêm nguồn lực hay giải quyết phụ thuộc nào?
4. Tiêu chí Done và bằng chứng kiểm thử phải được cập nhật ra sao?

Nhóm có thể thay đổi task, làm rõ phạm vi hoặc thương lượng lại PBI với Product Owner. **Không giảm chất lượng và không thay đổi điều gì gây nguy hại cho Sprint Goal**.

### Khi có yêu cầu khẩn giữa Sprint

Product Owner và Developers cùng đánh giá giá trị, mức khẩn, tác động lên Sprint Goal, nghĩa vụ vận hành hoặc bảo mật. Không mặc định đưa mọi yêu cầu “khẩn” vào Sprint mà vẫn giữ nguyên toàn bộ kế hoạch cũ. Nếu một sự cố nghiêm trọng đòi phản ứng ngay, nhóm cần chính sách xử lý phù hợp; minh bạch tác động tới dự báo là trách nhiệm quan trọng.

### Khi đã có Increment đạt Done trước cuối Sprint

Scrum không yêu cầu đợi Sprint Review mới được phát hành. Nếu đáp ứng điều kiện an toàn, sản phẩm có thể được phát hành và nhận phản hồi sớm. Sprint Review vẫn là dịp quan trọng để Scrum Team và các bên liên quan kiểm tra sản phẩm và quyết định thích ứng Product Backlog.

## 16. Những phản mẫu phổ biến trong Sprint Planning

### 16.1. Không có Sprint Goal, chỉ có danh sách ticket

Nếu ticket A không liên quan ticket B, nhóm khó biết nên ưu tiên điều gì khi có biến động. Hãy làm rõ một mục tiêu chung có giá trị, rồi chọn các PBI để hỗ trợ nó.

### 16.2. Product Owner hoặc quản lý chỉ định từng người làm từng task

Developers chịu trách nhiệm tổ chức công việc và lên kế hoạch tạo Increment. Việc giao từ trên xuống có thể giảm tự quản, che giấu rủi ro và khiến nhóm khó thích ứng khi phát hiện điều mới.

### 16.3. Dùng story points làm chỉ tiêu phải đạt

“Sprint nào cũng phải nhận ít nhất 40 điểm” tạo áp lực điều chỉnh điểm số hoặc bỏ kiểm thử. Story points không phải đơn vị năng suất chuẩn và Scrum không yêu cầu sử dụng chúng.

### 16.4. Dành gần hết buổi họp cho ước lượng mà không bàn Why hoặc How

Ước lượng giúp giao tiếp về độ phức tạp, nhưng không thay Sprint Goal hay kế hoạch tạo Increment. Nếu PBI quá mơ hồ, hãy làm rõ câu hỏi thiết yếu hoặc thu hẹp lát cắt.

### 16.5. Xem Sprint Planning là cuộc họp “chốt hợp đồng phạm vi”

Trong công việc phức tạp, nhóm sẽ học thêm trong Sprint. Sprint Goal là commitment; kế hoạch và phạm vi có thể được cập nhật theo đúng ranh giới Scrum. Cứng nhắc giữ mọi ticket bất chấp dữ liệu mới thường gây hại.

### 16.6. Chỉ chọn việc dễ làm để báo cáo nhiều ticket Done

Đếm số lượng PBI không phản ánh đầy đủ giá trị. Một lát cắt dọc cho phép người học tiếp tục bài đang dở có thể có ích hơn nhiều đầu việc kỹ thuật “gần như hoàn tất” nhưng chưa sử dụng được.

### 16.7. Không tính Definition of Done và công việc chất lượng

Nếu chọn phạm vi dựa trên giờ coding nhưng bỏ kiểm thử, bảo mật, tích hợp và khả năng vận hành, dự báo sẽ quá lạc quan. Không gọi việc chưa đạt Done là Increment chỉ vì đã hết Sprint.

### 16.8. Tổ chức “planning cho đủ nghi thức” khi Product Backlog chưa được làm rõ

Sprint Planning dễ biến thành một buổi thảo luận lan man, nhưng cũng không nên lập hàng rào hồ sơ quá mức. Hãy thực hiện refinement liên tục, mời người có hiểu biết phù hợp và xác định mức thông tin **đủ để lựa chọn có trách nhiệm**.

### 16.9. Chọn hết công suất lý thuyết

Mọi người không có toàn bộ ngày làm việc cho coding: còn sự cố, review, cộng tác và thay đổi không dự báo được. Hãy dự báo theo năng lực và lịch sử thực tế, dành chỗ cho chất lượng và bất định.

### 16.10. Quên lập kế hoạch nhận phản hồi sau Increment

Một chức năng đạt Done có thể vẫn không giải quyết nhu cầu. Xác định cách quan sát sản phẩm và lấy phản hồi để Scrum Team điều chỉnh Product Backlog, thay vì chỉ đo số task đã đóng.

## 17. Tình huống đặc biệt và cách xử lý

| Tình huống | Vấn đề cần thấy rõ | Cách phản ứng phù hợp |
| --- | --- | --- |
| **Product Owner không có mặt hoặc không thể làm rõ ưu tiên** | Khó cùng xác định giá trị và lựa chọn PBI hợp lý | Chủ động sắp xếp để Product Owner thực hiện trách nhiệm; không tự mặc định mọi yêu cầu đều có cùng ưu tiên |
| **Một PBI có rủi ro kỹ thuật lớn** | Developers không thể dự báo đáng tin khi thiếu kiểm chứng | Tách lát cắt nhỏ, làm spike có giới hạn hoặc thử tích hợp sớm trước khi mở rộng |
| **Các PBI phụ thuộc nhau** | Không thể tạo Increment dọc nếu chọn sai thứ tự | Tách lại theo hành vi người dùng và giải quyết phụ thuộc quan trọng |
| **Nhóm luôn nhận quá nhiều rồi kéo việc sang Sprint sau** | Có thể do mục tiêu không rõ, phạm vi quá lớn hoặc công việc bị chặn | Rà năng lực, cách chia PBI, WIP và Definition of Done; không chỉ yêu cầu làm nhanh |
| **Có một deadline bên ngoài không đổi** | Mục tiêu kinh doanh/hợp đồng khác với dự báo khả năng hoàn thành | Thảo luận phương án phạm vi tạo giá trị, dự phòng và rủi ro; truyền đạt mức chắc chắn trung thực |
| **Sprint Goal trở nên lỗi thời** | Mục tiêu không còn có ý nghĩa trong môi trường mới | Product Owner có thẩm quyền hủy Sprint khi cần; minh bạch lý do và lập kế hoạch lại |
| **Nhiều công việc hỗ trợ vận hành bất ngờ** | Sprint Goal dễ bị gián đoạn thường xuyên | Cân đối năng lực, chính sách xử lý khẩn; nếu loại công việc phù hợp hơn, cân nhắc thêm thực hành quản lý flow của Kanban |

Không có một cơ chế duy nhất cho mọi tình huống. Nguyên tắc chung là **minh bạch về rủi ro, giữ chất lượng và trao đổi theo đúng trách nhiệm của Scrum Team**.

## 18. Kết nối Sprint Planning với Kanban, XP và tư duy Agile

Sprint Planning là một **sự kiện của Scrum**; không phải nhóm Kanban nào cũng tổ chức Sprint Planning, và XP không yêu cầu một cuộc họp giống hệt. Tuy vậy, nhóm Scrum có thể học và kết hợp những thực hành bổ trợ.

### Kanban giúp hiểu dòng chảy để lựa chọn phạm vi

Nếu Scrum Team theo dõi **WIP, throughput, cycle time và work item age**, Developers có thể nhìn rõ hạng mục bị chặn, biến thiên năng lực và xu hướng hoàn tất. Những tín hiệu này giúp hỏi: “Sprint tới có thể chọn bao nhiêu lát cắt mà vẫn đạt Done?”, “Điểm nghẽn review có làm kế hoạch quá lạc quan không?”. Giới hạn WIP phù hợp có thể hỗ trợ hoàn thành những gì đã bắt đầu trước khi mở thêm việc.

### XP giúp kế hoạch How có khả năng thích ứng

Một Sprint Goal có giá trị sẽ khó đạt nếu mã thường xuyên hỏng khi sửa. Những thực hành **TDD, refactoring, pair programming, continuous integration và phát hành nhỏ** giúp rút ngắn vòng phản hồi kỹ thuật. Developers có thể chủ động đưa kiểm thử tích hợp, xây luồng dọc sớm và refactoring vào kế hoạch thực hiện — không xem chúng là việc chỉ làm “nếu còn thời gian”.

### Agile giúp chọn mục tiêu theo giá trị, không theo nghi thức

Sprint Planning tạo ra nhịp để **đặt mục tiêu có ích và lập kế hoạch có thể thích ứng**. Giá trị Agile thể hiện khi Scrum Team hợp tác thực sự, giao Increment dùng được, nhận phản hồi sớm và thay đổi cách làm theo bằng chứng. Một cuộc họp hoàn tất đúng giờ chưa có nghĩa Sprint thành công nếu sau đó sản phẩm không tạo giá trị.

## 19. Bài tập thực hành

### Bài tập A — Phân loại Why, What, How

Hãy phân loại những phát biểu sau theo **Why**, **What** hoặc **How**:

1. “Học viên đang học dở có thể tìm lại đúng bài mà không cần duyệt danh sách thủ công.”
2. “Chọn PBI-101 về luồng học tiếp và phần đo hành vi cần thiết.”
3. “Kiểm thử truy cập sai tài khoản trước khi cho nhóm thử dùng.”
4. “Chưa chọn đồng bộ offline vì rủi ro làm mất dữ liệu còn cao.”
5. “Tạo hợp đồng API tiến độ và tích hợp giao diện ngay khi có lát cắt đầu.”

**Gợi ý:** (1) diễn đạt Why dưới dạng kết quả có giá trị; (2) thuộc What; (3) và (5) thuộc How (đồng thời là điều kiện chất lượng cần có); (4) hỗ trợ quyết định What dựa trên rủi ro.

### Bài tập B — Viết lại Sprint Goal

Một Scrum Team viết: “Hoàn tất 32 story point; tạo ba endpoint, hai màn hình và một bảng dữ liệu”.

Hãy viết lại thành Sprint Goal thể hiện một kết quả người dùng/khách hàng có thể nhận được. Sau đó trả lời:

- Những PBI nào có thể cùng phục vụ mục tiêu đó?
- Nếu một endpoint nâng cao không cần cho luồng đầu tiên, có thể thay đổi phạm vi ra sao?
- Tiêu chuẩn chất lượng nào tuyệt đối không được bỏ qua?
- Nhóm sẽ quan sát phản hồi gì để quyết định phần tiếp theo?

**Gợi ý:** Một Sprint Goal tốt tập trung vào **hành vi có ích và ranh giới rõ**, ví dụ “Người học đã đăng nhập mở lại đúng bài dở một cách an toàn”, thay vì mô tả khối lượng công việc.

### Bài tập C — Chọn PBI khi năng lực giảm

Giả sử Developers thường hoàn tất 4–5 PBI tương đối đồng dạng trong Sprint hai tuần, nhưng Sprint tới có hai ngày nghỉ của một thành viên và một nhiệm vụ trực sự cố chưa xác định rõ thời lượng. Product Backlog có:

| PBI | Mô tả | Rủi ro |
| --- | --- | --- |
| A | Luồng học tiếp trên cùng thiết bị, đã làm rõ | Thấp đến trung bình nếu bảo đảm phân quyền |
| B | Đề xuất bài đầu khi chưa có tiến độ | Thấp |
| C | Đồng bộ offline | Cao, chưa kiểm chứng |
| D | Cá nhân hóa nội dung email nhắc học | Giá trị chưa có bằng chứng |
| E | Hoàn thiện đo lường hành vi học tiếp | Cần phối hợp dữ liệu và quyền riêng tư |

Hãy đề xuất **Sprint Goal**, PBIs nên chọn, rủi ro phải xử lý đầu tiên và phần nào cần để ở Product Backlog. Không bắt buộc chọn đủ một số lượng ticket theo lịch sử; cần có lý do dựa trên giá trị, năng lực, phụ thuộc và Done.

### Bài tập D — Thay đổi trong Sprint

Ngày thứ tư, Developers phát hiện dữ liệu tiến độ có trường hợp một tài khoản đọc được bản ghi của tài khoản khác nếu dùng ID không được kiểm soát. Đồng thời, một bên liên quan muốn thêm email nhắc học.

1. Điều gì bắt buộc phải xử lý trước khi gọi Increment là Done?
2. Developers và Product Owner nên trao đổi gì về phạm vi?
3. Sprint Goal có còn ý nghĩa không?
4. Khi nào mới cân nhắc hủy Sprint?
5. Nhóm cần thay đổi kiểm thử, monitoring hoặc cách refinement thế nào để phòng ngừa?

**Gợi ý:** Lỗ hổng phân quyền là vấn đề bắt buộc cần xử lý trong luồng đã hỗ trợ; không thể bỏ qua vì hết thời gian. Email nhắc học cần đánh giá ưu tiên so với Sprint Goal, không tự động thêm vào phạm vi.

### Bài tập E — Diễn tập Sprint Planning

Chia thành ba nhóm đại diện Product Owner, Developers và Scrum Master. Trong **45–60 phút timebox mô phỏng**, hãy làm rõ:

1. Product Goal và cơ hội sản phẩm mà Sprint nên theo đuổi.
2. Một Sprint Goal có thể diễn đạt trong một hoặc hai câu.
3. Các PBI Developers lựa chọn và lý do loại bớt những mục rủi ro.
4. Bản kế hoạch How với một lát cắt end-to-end, kiểm thử, tích hợp, phụ thuộc và câu hỏi còn mở.
5. Nội dung Sprint Backlog hoàn chỉnh; điều kiện nào sẽ khiến nhóm cần điều chỉnh trong Sprint.

Đánh giá kết quả bằng **khả năng giải thích và dùng kế hoạch**, không bằng số lượng sticky note hay số story point.

## 20. Checklist trước khi kết thúc Sprint Planning

- [ ] Toàn bộ Scrum Team có mặt và hiểu mục tiêu của sự kiện.
- [ ] Product Owner đã cung cấp bối cảnh Product Goal, ưu tiên và phản hồi quan trọng.
- [ ] Scrum Team đã cộng tác xác định **Sprint Goal có giá trị**, không chỉ ghép tên ticket.
- [ ] Developers đã trao đổi với Product Owner để **chọn các PBI** có khả năng Done.
- [ ] Đã xem năng lực thực tế, lịch nghỉ, sự cố, phụ thuộc và biến thiên từ lịch sử.
- [ ] Các PBI quan trọng đủ rõ về hành vi, quy tắc và tiêu chí chấp nhận.
- [ ] Mọi người biết **Definition of Done** và những điều kiện chất lượng bắt buộc.
- [ ] Developers đã tạo kế hoạch How đủ hành động, bao gồm tích hợp, kiểm thử và phản hồi sớm.
- [ ] Các rủi ro kỹ thuật, giá trị và phụ thuộc lớn có người theo dõi và cách kiểm chứng.
- [ ] Sprint Backlog thể hiện đủ **Why, What, How**, minh bạch với Scrum Team.
- [ ] Không biến dự báo phạm vi hoặc story points thành lời hứa chắc chắn.
- [ ] Không phân task từ trên xuống thay cho sự tự quản của Developers.
- [ ] Có kế hoạch tiếp nhận phản hồi người dùng và điều chỉnh backlog khi sản phẩm tạo ra Increment.
- [ ] Sprint Goal được chốt trước khi Sprint Planning kết thúc, trong timebox phù hợp.
- [ ] Nhóm hiểu rằng kế hoạch **có thể thay đổi trong Sprint**, nhưng không được giảm chất lượng hoặc gây nguy hại Sprint Goal.

## 21. Tài liệu đọc tiếp và điểm ghi nhớ

- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): nguồn nền tảng về Sprint Planning, ba chủ đề Why–What–How, Sprint Goal, Sprint Backlog, quyền tự quản của Developers và Definition of Done.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/): các giá trị cốt lõi về cộng tác, phần mềm hoạt động được, phản hồi và khả năng thích ứng.
- [The Kanban Guide](https://kanbanguides.org/): các chỉ số WIP, throughput, cycle time và work item age có thể hỗ trợ khả năng dự báo và quản lý dòng công việc.
- Kent Beck và Cynthia Andres, *Extreme Programming Explained: Embrace Change*, ấn bản 2 (2004): thực hành kỹ thuật nhằm giữ vòng phản hồi ngắn và khả năng thay đổi phần mềm.

**Điểm cốt lõi:** Sprint Planning không phải buổi giao việc hay ký cam kết hoàn thành một lượng ticket cố định. Nó giúp Scrum Team thống nhất **Why: Sprint có giá trị vì điều gì; What: Developers dự báo có thể hoàn tất những PBI nào; How: Developers sẽ tạo Increment đáp ứng Definition of Done ra sao**. Kết quả là một Sprint Backlog vừa có định hướng, vừa có thể điều chỉnh theo thông tin mới, giúp nhóm giao giá trị sớm và cải tiến liên tục.
