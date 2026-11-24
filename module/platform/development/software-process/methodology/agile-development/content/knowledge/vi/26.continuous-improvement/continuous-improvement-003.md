# Phân tích nguyên nhân của chậm trễ, lỗi và trở ngại lặp lại

## 1. Vì sao nhóm liên tục gặp lại cùng một vấn đề?

Một nhóm phát triển nền tảng học trực tuyến liên tiếp trải qua bốn Sprint có cùng câu chuyện:

- Nửa đầu Sprint, Developers bắt đầu nhiều user story; mọi người đều có việc làm.
- Những ngày cuối Sprint, nhiều pull request chờ review hoặc môi trường kiểm thử tích hợp.
- Một số bài kiểm thử thất bại không ổn định; nhóm chạy lại nhiều lần cho đến khi thấy xanh.
- Chức năng đăng ký khóa học có lúc tạo bản ghi trùng khi người học bấm liên tiếp.
- Sprint Retrospective lại kết luận: “Lần sau phải kiểm thử sớm hơn và phối hợp tốt hơn.”

Nhóm có tổ chức Retrospective, ghi nhiều ý kiến và gửi báo cáo đầy đủ, nhưng các vấn đề vẫn lặp lại. Vì sao?

Vì **nhìn thấy triệu chứng chưa đồng nghĩa hiểu cơ chế tạo ra triệu chứng**. Nếu chỉ đề nghị mọi người “cẩn thận hơn”, “làm nhanh hơn” hoặc “đừng để dồn cuối Sprint”, nhóm có thể không thay đổi được chính sách kéo việc, hàng chờ review, dữ liệu kiểm thử và cách thiết kế luồng đăng ký—những điều kiện đang tạo lại vấn đề.

Trong chương **Cải tiến liên tục** thuộc module **AGILE_DEVELOPMENT**, chúng ta học cách **phân tích nguyên nhân của chậm trễ, lỗi và trở ngại lặp lại** để đưa ra những thay đổi hệ thống có thể kiểm chứng. Nội dung kết nối giá trị Agile (phản hồi sớm, giao tăng dần, thích ứng và cải tiến) với **user story, Product Backlog, Scrum, Kanban, XP** và đo lường dòng công việc.

**Câu hỏi trung tâm:** *Điều gì trong cách thiết kế sản phẩm, kỹ thuật, dòng công việc hoặc phối hợp khiến kết quả không mong muốn tiếp tục xảy ra; có bằng chứng nào hỗ trợ giả thuyết ấy; và thay đổi nhỏ nào sẽ kiểm tra được nguyên nhân?*

## 2. Phân biệt triệu chứng, sự kiện, nguyên nhân và tác động

Một cuộc điều tra tốt bắt đầu bằng cách gọi tên đúng loại thông tin.

| Khái niệm | Ý nghĩa | Ví dụ trong nhóm nền tảng học |
| --- | --- | --- |
| **Sự kiện quan sát** | Điều đã xảy ra có thời điểm và bằng chứng | PR-42 được tạo thứ Hai, tới thứ Năm mới có review đầu tiên |
| **Triệu chứng** | Dấu hiệu vấn đề có thể nhìn thấy | Công việc Done muộn và nhiều story chờ kiểm thử |
| **Tác động** | Hậu quả lên người dùng, giá trị, chất lượng hoặc dòng công việc | Chậm cơ hội kiểm thử luồng đăng ký trước đợt khai giảng |
| **Nguyên nhân trực tiếp** | Cơ chế gần nhất tạo ra sự kiện | PR chưa được review nên chưa thể tích hợp |
| **Điều kiện góp phần** | Chính sách, cấu trúc, ràng buộc làm vấn đề dễ xảy ra hoặc nghiêm trọng hơn | Chỉ một người có quyền review, WIP cao, reviewer thường xuyên bị ngắt việc |
| **Nguyên nhân hệ thống có thể cải tiến** | Điều kiện lặp lại có thể tác động để giảm xác suất/tác hại | Không có chính sách hỗ trợ review khi người phụ trách quá tải |
| **Giả thuyết** | Cách giải thích chưa được xác nhận | “Nút nghẽn review là lý do chính khiến cycle time kéo dài” |
| **Hành động khắc phục** | Thay đổi nhằm giảm tác động hiện tại hoặc ngăn lặp | Cùng review trước khi kéo thêm việc; đào tạo người review dự phòng |

**Triệu chứng không nhất thiết chỉ có một nguyên nhân.** Một PBI có thể chậm vì chờ review, dữ liệu thử thiếu, phụ thuộc nhà cung cấp và phạm vi được làm rõ muộn. Ngược lại, một nguyên nhân như **WIP quá cao** có thể góp phần tạo nhiều triệu chứng: review chậm, kiểm thử muộn, nhiều lỗi tích hợp và cảm giác “mọi người đều bận”.

### 2.1. Một ví dụ về mô tả vấn đề đúng

**Mơ hồ và dễ đổ lỗi:** “Nhóm QA chậm nên chúng tôi không kịp Sprint.”

**Cụ thể và có thể kiểm chứng hơn:**

> “Trong ba Sprint gần đây, nhiều PBI hoàn tất code nhưng chờ kiểm thử tích hợp từ hai đến năm ngày làm việc. Chỉ có một môi trường kiểm thử dùng chung; khi hai nhánh cùng thay dữ liệu, các bộ test ảnh hưởng lẫn nhau. Điều này làm cycle time tăng và khiến khả năng đạt Sprint Goal khó dự báo.”

Mô tả thứ hai nêu **bối cảnh, dấu hiệu và cơ chế cần điều tra** mà không quy kết rằng một cá nhân “làm việc kém”.

### 2.2. Chậm trễ, lỗi và trở ngại không phải cùng một loại vấn đề

- **Chậm trễ:** Thời gian tới kết quả dài hơn kỳ vọng. Có thể do thời gian xử lý thật, hàng chờ, phụ thuộc hoặc thay đổi phạm vi.
- **Lỗi (defect):** Hành vi thực tế không đáp ứng yêu cầu/chất lượng kỳ vọng đã xác định. Có thể phát hiện trước hoặc sau phát hành.
- **Trở ngại (impediment/blocker):** Điều ngăn hoặc làm chậm khả năng tiến hành công việc, ví dụ thiếu quyền truy cập hoặc môi trường không sẵn.
- **Sự cố (incident):** Một sự kiện ảnh hưởng đáng kể tới dịch vụ hoặc người dùng, cần ứng phó theo mức nghiêm trọng.

Ba loại có thể liên hệ: môi trường tích hợp thiếu ổn định gây trở ngại, làm phát hiện lỗi muộn, rồi kéo dài thời gian Done.

## 3. Tư duy hệ thống: thay câu “ai gây lỗi?” bằng “điều kiện nào cho phép lỗi xảy ra?”

**Tư duy hệ thống (systems thinking)** nhìn kết quả như sản phẩm của các tương tác giữa con người, quy trình, chính sách, công cụ, kiến trúc, dữ liệu và môi trường.

Một người review có thể làm việc rất có trách nhiệm nhưng vẫn thành nút nghẽn nếu:

1. Chỉ họ có quyền phê duyệt tất cả thay đổi.
2. Nhiều PR lớn được gửi tới cùng lúc vào cuối Sprint.
3. Họ còn trực hỗ trợ production và thường bị ngắt việc.
4. Không có thỏa thuận về thời điểm review hoặc cơ chế người hỗ trợ.

Trong điều kiện ấy, khẩu hiệu “review nhanh lên” không thay đổi nguyên nhân tạo hàng chờ.

### 3.1. Nhiều tầng nguyên nhân

| Tầng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Kích hoạt gần nhất** | Điều gì trực tiếp dẫn tới thất bại? | Hai request ghi tiến độ cùng lúc |
| **Cơ chế kỹ thuật** | Vì sao kích hoạt tạo ra kết quả sai? | Ghi đè trạng thái không kiểm tra version |
| **Điều kiện tiềm ẩn** | Vì sao cơ chế sai tồn tại? | Không có kiểm thử đồng thời ở ranh giới DB |
| **Điều kiện tổ chức** | Vì sao lỗ hổng không được phát hiện sớm? | Kiểm thử tích hợp dồn cuối Sprint, môi trường chung hay lỗi |
| **Điều kiện phát hiện/giảm tác động** | Vì sao sự cố không được ngăn hoặc phát hiện kịp? | Thiếu log/alert và quy trình phản hồi phù hợp |

Không phải cuộc điều tra nào cũng cần đi qua đủ năm tầng. **Mục đích là hiểu các yếu tố có thể hành động**, không đi tìm một câu trả lời sâu tới vô tận.

### 3.2. “Nguyên nhân gốc” thường không phải một điểm duy nhất

Thuật ngữ *root cause* hữu ích để nhấn mạnh việc đi qua triệu chứng, nhưng trong hệ thống phức tạp thường tồn tại **nhiều điều kiện cần hoặc góp phần**, không có một nguyên nhân duy nhất.

Ví dụ lỗi đăng ký trùng có thể cần đồng thời:

- Hai yêu cầu gần đồng thời.
- Logic kiểm tra tồn tại rồi mới ghi không nguyên tử.
- Không có ràng buộc dữ liệu thích hợp.
- Không có kiểm thử cạnh tranh đủ đại diện.
- Cơ chế retry không được xác định rõ.

Khắc phục một yếu tố có thể giảm rủi ro, nhưng **không nên kết luận mọi vấn đề đã được loại bỏ** nếu các đường gây lỗi khác vẫn tồn tại.

### 3.3. Sơ đồ quan hệ giúp thấy vòng lặp

~~~mermaid
flowchart TD
    A["Nhiều PBI được bắt đầu cùng lúc"] --> B["WIP và PR chờ review tăng"]
    B --> C["Tích hợp và kiểm thử đến muộn"]
    C --> D["Phát hiện lỗi khi gần hết Sprint"]
    D --> E["Áp lực hoàn tất và sửa gấp"]
    E --> F["Ít năng lực cải tiến pipeline và thiết kế"]
    F --> G["Nút nghẽn/lỗi dễ tái diễn"]
    G --> E
    H["Giới hạn WIP, cùng hoàn tất, sửa CI"] --> B
~~~

Mũi tên chỉ **giả thuyết quan hệ cần kiểm chứng**, không phải chứng minh nhân quả chỉ từ sơ đồ. Một can thiệp vào WIP có thể tác động hàng chờ; nhóm vẫn cần đo và xem chất lượng để biết nó có hiệu quả thật không.

## 4. Khi nào cần phân tích sâu, khi nào cần xử lý ngay?

Không phải mọi lỗi nhỏ đều cần một cuộc họp phân tích kéo dài. Ngược lại, vấn đề lặp lại hoặc hậu quả lớn không nên được đóng chỉ bằng lời “đã sửa”.

| Trường hợp | Ưu tiên hành động | Phân tích phù hợp |
| --- | --- | --- |
| Sự cố production ảnh hưởng dữ liệu người học | Ngăn tác động, ứng cứu theo chính sách | Sau khi an toàn, điều tra cơ chế, phát hiện và yếu tố góp phần |
| Lỗi hồi quy nhỏ, dễ tái hiện | Sửa, kiểm chứng, tích hợp | Ghi nguyên nhân nếu loại lỗi lặp lại; không nhất thiết tổ chức điều tra lớn |
| PR thường xuyên chờ nhiều ngày | Quan sát luồng và giảm nguy cơ trễ hiện tại | Phân tích hàng chờ, WIP, quyền review và chính sách |
| Kiểm thử CI flaky lặp lại | Khôi phục tín hiệu kiểm thử đáng tin | Tách mã, dữ liệu, thứ tự chạy, môi trường và phụ thuộc |
| Công việc Blocked vì phê duyệt ngoài nhóm | Liên hệ đúng người có quyền, minh bạch rủi ro | Xem thời gian chờ, thời điểm yêu cầu phê duyệt và khả năng chuẩn bị sớm |
| Một ngoại lệ đơn lẻ nhưng ít tác động | Ghi nhận và theo dõi phù hợp | Không cần suy ra nguyên nhân hệ thống từ một quan sát |
| Near miss có nguy cơ lớn | Giữ bằng chứng và giảm rủi ro | Điều tra trước khi có sự cố thật, phù hợp yêu cầu an toàn |

### 4.1. Tách ứng cứu khỏi cải tiến phòng ngừa

Với sự cố ảnh hưởng đang diễn ra:

1. **Bảo vệ người dùng và dữ liệu trước:** Khoanh vùng tác động, tắt đường gây hại hoặc dùng biện pháp được phê duyệt.
2. **Khôi phục dịch vụ an toàn:** Sửa, hoàn nguyên hoặc kích hoạt phương án dự phòng theo quyền hạn.
3. **Ghi nhận dữ kiện:** Timeline, logs đã xử lý bảo mật, revision mã, trạng thái môi trường và kết quả.
4. **Phân tích sau sự cố:** Những điều kiện nào tạo ra và khiến sự cố không được phát hiện sớm?
5. **Cải tiến và kiểm chứng:** Có hành động, người theo dõi và bằng chứng hiệu quả.

**Không chờ phân tích nguyên nhân đầy đủ mới ngăn thiệt hại đang xảy ra.** Nhưng cũng không dừng ở khắc phục tạm nếu rủi ro có thể lặp lại.

### 4.2. Mức độ đầu tư điều tra cần tương xứng

Một vấn đề nghiêm trọng về quyền dữ liệu có thể cần đánh giá liên chức năng và quy trình pháp lý/bảo mật. Một lỗi định dạng nhỏ có thể chỉ cần kiểm thử hồi quy và cải tiến review. **Độ nghiêm trọng, khả năng lặp và chi phí sai** nên quyết định mức phân tích.

## 5. Quy trình điều tra nguyên nhân từ dữ kiện đến cải tiến

Một quy trình thực hành có thể gồm tám bước:

~~~mermaid
flowchart TD
    A["1. Định nghĩa vấn đề và tác động"] --> B["2. Bảo vệ dịch vụ nếu đang có nguy cơ"]
    B --> C["3. Thu thập timeline và bằng chứng"]
    C --> D["4. Phác họa luồng / cơ chế xảy ra"]
    D --> E["5. Lập các giả thuyết nguyên nhân"]
    E --> F["6. Kiểm chứng bằng dữ liệu và thử nghiệm phù hợp"]
    F --> G{"Đủ cơ sở để chọn can thiệp?"}
    G -->|"Chưa"| C
    G -->|"Có"| H["7. Thử hành động cải tiến có chủ đích"]
    H --> I["8. Theo dõi kết quả, guardrail và điều chỉnh"]
    I --> A
~~~

### 5.1. Bước 1: Viết phát biểu vấn đề

Nên có:

- **Đối tượng/phạm vi:** Loại PBI, dịch vụ, người dùng hoặc luồng cụ thể.
- **Khoảng thời gian:** Sprint, tuần, đợt phát hành hoặc thời điểm sự cố.
- **Mức ảnh hưởng:** Chậm bao lâu, lỗi gì, có nguy cơ dữ liệu nào?
- **Bằng chứng hiện có:** Bản ghi workflow, logs, test, ticket, phản hồi.
- **Điều còn chưa biết:** Không cố viết sẵn nguyên nhân trước khi điều tra.

Ví dụ:

> “Trong bốn tuần, 5 trong 12 PBI đã Done có thời gian chờ review từ ba ngày làm việc trở lên; hai PBI còn dở đã vượt 10 ngày và đang ở cột Review. Chúng tôi muốn biết chính sách review, lượng PR đến cùng lúc hay chất lượng PR đang góp phần gây trễ.”

Những số này thuộc **ví dụ giả định**, không phải dữ liệu thực của nền tảng.

### 5.2. Bước 2: Xác định ranh giới và rủi ro

Nếu điều tra đăng ký trùng, cần biết người học nào có thể bị ảnh hưởng, giao dịch nào cần giữ, ai được quyền truy cập dữ liệu, và hành động khắc phục nào có thể làm hại thêm. **Không tự xóa dữ liệu production** chỉ vì phát hiện bản ghi trùng.

### 5.3. Bước 3: Thu thập dữ kiện không chỉnh sửa cho khớp giả thuyết

Ưu tiên log có timestamp, báo cáo kiểm thử, revision mã, lịch sử trạng thái PBI, tài liệu quyết định và phỏng vấn người trực tiếp tham gia. Khi có mâu thuẫn, **ghi nhận mâu thuẫn**, không chọn ngay nguồn thuận tiện.

### 5.4. Bước 4: Mô hình hóa luồng hoặc cơ chế

Với chậm trễ, vẽ workflow và thời gian ở mỗi hàng chờ. Với lỗi dữ liệu, vẽ đường yêu cầu–dịch vụ–database và những bước đọc/ghi. Với blocker, vẽ chuỗi phụ thuộc và người có quyền quyết định.

### 5.5. Bước 5–6: Tạo và kiểm tra nhiều giả thuyết

Mỗi giả thuyết cần dự đoán **dấu hiệu có thể kiểm tra**. Ví dụ “thiếu reviewer” dự đoán thời gian chờ tăng khi người có quyền nghỉ hoặc khi số PR đến cao; “PR quá lớn” dự đoán thời gian review tăng theo kích thước hoặc mức thay đổi có liên hệ, sau khi xét độ phức tạp.

### 5.6. Bước 7–8: Thử cải tiến và đánh giá

Một hành động chỉ thành “cải tiến” khi có cách xem liệu nó **giảm vấn đề mà không tạo tác dụng phụ lớn**. Ghi tiêu chí thành công, guardrail, người phối hợp và điểm xem lại.

## 6. Thu thập bằng chứng: timeline, workflow, log và lời kể

Phân tích nguyên nhân không phải cuộc thi kể câu chuyện thuyết phục. Bằng chứng cần được **truy vết và diễn giải trong ngữ cảnh**.

### 6.1. Timeline một vấn đề chậm review

| Mốc minh họa | Sự kiện quan sát | Cần kiểm tra thêm |
| --- | --- | --- |
| Thứ Hai 09:00 | PR tạo, tự kiểm tra cơ bản đạt | Có đủ mô tả và điều kiện review chưa? |
| Thứ Hai 10:00 | Pipeline xanh | Pipeline đã kiểm tra hợp đồng quan trọng nào? |
| Thứ Ba 16:00 | Không có review; PR vẫn chờ | Reviewer có được thông báo? Có quyền hỗ trợ? |
| Thứ Tư 14:00 | Reviewer chính xử lý incident production | Có phương án reviewer dự phòng? |
| Thứ Năm 11:00 | Có review đầu tiên, phát hiện hợp đồng API chưa rõ | Có thể làm rõ sớm từ refinement không? |
| Thứ Sáu 15:00 | PR sửa xong và hợp nhất | Kiểm tra sau merge có đạt không? |

Timeline giúp tách **thời gian chờ** khỏi **thời gian xử lý**, đồng thời chỉ ra các mốc có thể thử thay đổi. Nó chưa tự chứng minh “reviewer thiếu trách nhiệm”.

### 6.2. Bốn nguồn bằng chứng bổ sung nhau

| Nguồn | Mạnh ở đâu? | Hạn chế cần biết |
| --- | --- | --- |
| **Hệ thống quản lý công việc** | Trạng thái, người phối hợp, mốc bị chặn | Có thể cập nhật trễ hoặc thiếu chính xác |
| **Repository / CI** | Revision, thời gian review, build/test | Không mô tả hết bối cảnh nghiệp vụ |
| **Logs/metrics/traces** | Hành vi hệ thống, lỗi, độ trễ | Có thể thiếu sự kiện, sai múi giờ hoặc không đủ dữ liệu |
| **Phỏng vấn/người chứng kiến** | Ngữ cảnh, quyết định và việc không được ghi tự động | Ký ức có thể thiếu, thiên lệch hồi tưởng |

Nên đối chiếu các nguồn, đồng thời tôn trọng quyền riêng tư và phạm vi truy cập được phép.

### 6.3. Dữ kiện, suy diễn và điều chưa biết

Mẫu ghi:

~~~text
Quan sát:
  PR-42 chờ ba ngày làm việc trước review đầu tiên.
  Reviewer chính xử lý sự cố production trong hai ngày.

Giả thuyết:
  Thiếu phương án review dự phòng làm thời gian chờ kéo dài.

Bằng chứng cần thêm:
  Dữ liệu các PR tương tự khi reviewer chính có mặt/vắng mặt.
  Chính sách phân quyền review và lịch trực hỗ trợ.

Không được kết luận ngay:
  "Reviewer chính quản lý thời gian kém."
~~~

**Việc phân biệt dữ kiện và giả thuyết là bước nền để điều tra không đổ lỗi.**

## 7. Phân tích chậm trễ bằng dòng công việc thay vì phần trăm task

Với một PBI, thời gian từ bắt đầu tới Done thường chứa cả **thời gian thực hiện, thời gian chờ, làm lại và chuyển giao**.

Ví dụ một PBI có **Cycle Time 9 ngày làm việc** theo ranh giới nhóm đã thống nhất, gồm các khoảng **không chồng lắp**:

| Khoảng trong luồng | Thời lượng | Đặc tính |
| --- | ---: | --- |
| Thiết kế và viết mã ban đầu | 2 ngày | Thực hiện |
| Chờ review đầu tiên | 4 ngày | Hàng chờ |
| Sửa phản hồi và kiểm thử tích hợp | 2 ngày | Thực hiện / kiểm chứng |
| Chờ môi trường sau lỗi cấu hình | 1 ngày | Blocked |
| **Tổng** | **9 ngày** | **2 + 4 + 2 + 1** |

Trong ví dụ này, **5/9 ngày** ở trạng thái chờ hoặc blocked. Con số **5/9 ≈ 55,6%** không chứng minh rằng “55,6% năng lực bị lãng phí”, vì thời gian chờ tính trên item không bằng thời gian nhàn rỗi của con người; nhưng nó giúp nhóm hỏi **liệu giảm review queue hoặc môi trường chờ có làm item Done sớm hơn không**.

### 7.1. Vẽ Value Stream Map đơn giản

~~~mermaid
flowchart LR
    A["Bắt đầu PBI"] --> B["Phát triển: 2 ngày"]
    B --> C["Chờ review: 4 ngày"]
    C --> D["Sửa và kiểm thử: 2 ngày"]
    D --> E["Chờ môi trường: 1 ngày"]
    E --> F["Done: đạt tiêu chuẩn hoàn tất"]
~~~

Sơ đồ trên là **một trường hợp**, chưa thể đại diện mọi PBI. Cần xem nhiều item tương đồng và độ biến động của các bước để quyết định ưu tiên cải tiến.

### 7.2. Phân biệt hàng chờ với xử lý thật

Nếu một PR chờ review ba ngày trong khi review thực tế mất 30 phút, tăng tốc thao tác đọc mã thêm 10% có thể ít tác động hơn **giảm số PR chờ và khả năng sẵn sàng của reviewer**.

Ngược lại, nếu review mất ba ngày vì PR có hàng ngàn dòng thay đổi phức tạp, giải pháp không đơn thuần là “review sớm hơn”; có thể cần **chia lát cắt nhỏ, làm rõ hợp đồng và thêm kiểm thử**.

### 7.3. Cách tránh đếm trùng thời gian

Nếu item vừa ở cột Review vừa được gắn nhãn Blocked do môi trường, cộng “3 ngày review + 3 ngày blocked” có thể **đếm cùng ba ngày hai lần**. Trước khi tính:

- Quy định trạng thái chính, nhãn phụ và cách cộng thời lượng.
- Nêu ngày lịch hay ngày làm việc.
- Chỉ cộng các khoảng không chồng lắp nếu muốn đối chiếu với tổng Cycle Time.
- Có thể báo blocked time **như chiều phân tích riêng**, không ép nó cộng thành tổng nếu có chồng lắp.

## 8. Dùng WIP, Work Item Age, Cycle Time và Throughput để đặt câu hỏi

Trong Kanban, bốn flow metrics hỗ trợ nhìn nhiều mặt của vấn đề:

| Metric | Định nghĩa | Câu hỏi nguyên nhân có thể hỗ trợ |
| --- | --- | --- |
| **WIP** | Số item đã bắt đầu nhưng chưa Done tại thời điểm đo | Có quá nhiều việc cùng mở làm hàng chờ tăng không? |
| **Work Item Age** | Thời gian đã trôi qua từ lúc bắt đầu của item còn dở | Item nào đang già và bị chặn ở công đoạn nào? |
| **Cycle Time** | Thời gian từ bắt đầu đến Done của item hoàn tất | Phân bố thời gian hoàn tất có thay đổi không? |
| **Throughput** | Số item Done trong một khoảng thời gian | Nhóm thực sự hoàn tất được bao nhiêu item? |

**Các metric chỉ hữu ích khi ranh giới đo thống nhất.** Trong Scrum, một PBI chỉ được coi là Done khi đạt Definition of Done. Thay nhãn “code xong” thành Done để tăng throughput là làm sai dữ liệu, không phải cải tiến.

### 8.1. Một tập Cycle Time minh họa

Giả sử có 12 user story tương đồng đã Done trong một giai đoạn, Cycle Time tính bằng **ngày làm việc**, xếp tăng dần:

~~~text
2, 3, 4, 4, 5, 6, 7, 8, 9, 11, 13, 18
~~~

Ta có:

- **Tổng:** \(2+3+4+4+5+6+7+8+9+11+13+18=90\) ngày-item.
- **Trung bình:** \(90/12=7{,}5\) ngày làm việc/item.
- **Trung vị:** \((6+7)/2=6{,}5\) ngày.
- **P85 theo nearest-rank:** Vị trí \(\lceil0{,}85\times12\rceil=11\), tương ứng **13 ngày**.
- **P95 theo nearest-rank:** Vị trí \(\lceil0{,}95\times12\rceil=12\), tương ứng **18 ngày**.

Tập có **đuôi dài**: đa số item nhanh hơn 9 ngày nhưng có item mất 18 ngày. Nếu chỉ báo “trung bình 7,5”, nhóm có thể bỏ qua những item tồn lâu đáng điều tra.

Đây là **mẫu nhỏ để học phương pháp**, không đủ chứng minh phân bố ổn định hoặc áp ngưỡng P85 chính xác cho mọi công việc tương lai. Các thư viện thống kê có thể dùng phương pháp phân vị nội suy khác; cần công bố phương pháp nếu so sánh kết quả.

### 8.2. Work Item Age nhìn thấy vấn đề trước khi Done

Hiện có 9 item WIP. Một vài item:

| Item chưa Done | Age hiện tại | Bước đang ở | Hành động xem xét |
| --- | ---: | --- | --- |
| A — Đăng ký khóa miễn phí | 12 ngày | Blocked môi trường tích hợp | Xác minh phụ thuộc và cách gỡ chặn |
| B — Lưu khóa yêu thích | 10 ngày | Chờ review | Xem hàng chờ, người review dự phòng |
| C — Sửa nhãn trình độ | 3 ngày | Kiểm thử | Theo dõi bình thường theo bối cảnh |
| D — Báo cáo nội bộ | 7 ngày | Đang phát triển | Làm rõ phạm vi và các phụ thuộc |

**Không suy ra tuổi 10 ngày nghĩa là “90% hoàn thành”** nếu SLE tham khảo là 11 ngày. Tuổi công việc là thời gian đã trôi qua, không đo trực tiếp lượng mã còn lại hoặc xác suất trễ của một item riêng lẻ.

### 8.3. Service Level Expectation không phải bằng chứng tuyệt đối

Nhóm có thể dùng phân bố lịch sử để đưa ra **Service Level Expectation (SLE)** cho loại item tương đồng, chẳng hạn “kỳ vọng khoảng 85% story hoàn tất không quá 13 ngày làm việc kể từ khi bắt đầu”. Với chỉ 12 quan sát, mức này cần được xem **rất thận trọng và tiếp tục kiểm chứng**.

SLE khác **SLA** hợp đồng và không phải lời hứa mọi item sẽ xong trong 13 ngày. Item đã vượt mốc cần được xem trạng thái và rủi ro, **không áp phép trừ 13 − Age để đo thời gian còn lại**.

### 8.4. Little's Law giúp đặt giả thuyết hệ thống

Trong hệ thống đủ ổn định và đo nhất quán:

\[
\overline{\text{WIP}}\approx
\overline{\text{Throughput}}\times
\overline{\text{Cycle Time}}
\]

Ví dụ độc lập: WIP trung bình 8 item, throughput trung bình 4 item/tuần có thể liên hệ với Cycle Time trung bình khoảng **2 tuần** theo giả định và điều kiện áp dụng. Công thức **không đưa ra P85 hoặc thời hạn chắc chắn**. Nó giúp đặt câu hỏi liệu quá nhiều WIP và hàng chờ có làm luồng chậm.

### 8.5. Biểu đồ nào giúp điều tra?

- **Aging WIP Chart:** Item nào đã tồn lâu và nằm ở bước nào?
- **Cycle Time Scatterplot:** Đuôi dài có tập trung vào loại item hoặc giai đoạn nào?
- **Cumulative Flow Diagram:** Hàng chờ của công đoạn nào đang phình ra?
- **Run Chart theo thời gian:** Sau thay đổi chính sách, xu hướng có đổi không?
- **Blocked Time theo nguyên nhân:** Môi trường, dữ liệu, review, quyền truy cập hay bên ngoài?

Biểu đồ là **cửa sổ điều tra**, không tự chỉ ra nguyên nhân. Cần xác minh cách cập nhật ticket, phân loại công việc và hành vi thật.

## 9. Phương pháp 5 Whys: hỏi “vì sao?” nhưng phải kiểm chứng

**5 Whys** là kỹ thuật đặt nhiều câu hỏi “Vì sao?” để đi từ triệu chứng tới cơ chế sâu hơn. Con số năm là **gợi ý**, không phải luật; có thể đủ sau ba câu hoặc cần nhiều nhánh. Nó hiệu quả khi câu trả lời dựa trên dữ kiện, nhưng dễ gây hại nếu biến thành cách hỏi “ai làm sai?”.

### 9.1. Ví dụ với PR chờ review

**Vấn đề:** Các PR liên quan đăng ký khóa thường chờ ba đến bốn ngày mới có review đầu tiên.

| Lần hỏi | Giả thuyết/câu trả lời cần kiểm tra | Bằng chứng cần xác minh |
| --- | --- | --- |
| **Vì sao 1?** | Vì PR nằm trong hàng chờ review | Timestamp tạo PR và review đầu |
| **Vì sao 2?** | Vì reviewer có quyền phê duyệt chưa thể xử lý kịp | Quyền review, lịch trực, lượng PR đến |
| **Vì sao 3?** | Vì nhiều PR đến cùng lúc và chỉ một reviewer cho mô-đun | Phân bố PR theo ngày, ma trận chuyên môn |
| **Vì sao 4?** | Vì nhóm thường tích hợp dồn cuối Sprint và không có người review dự phòng | Lịch sử merge, chính sách phân quyền, việc chuyển giao |
| **Vì sao 5?** | Vì thỏa thuận làm việc chưa quy định cách giảm WIP, chia PR và xử lý khi reviewer vắng | Working agreement, Retrospective, quy trình thực tế |

Những câu trả lời trên là **giả thuyết minh họa**, không được coi là sự thật nếu chưa kiểm tra nguồn dữ liệu.

### 9.2. Đổi câu hỏi từ cá nhân sang điều kiện

**Cách hỏi gây phòng vệ:** “Vì sao An không review nhanh hơn?”

**Cách hỏi hữu ích hơn:** “Trong điều kiện nào PR phải chờ An, có thể giảm phụ thuộc và làm thay đổi nhỏ hơn bằng cách nào?”

Điều này không loại bỏ trách nhiệm nghề nghiệp; nó giúp nhóm nhìn thấy **cơ chế có thể thay đổi** thay vì dừng ở một phán xét về tính cách.

### 9.3. Khi nào nên dừng chuỗi Whys?

Có thể dừng hoặc chuyển sang phương pháp khác khi:

1. Đã thấy **một hoặc vài điều kiện kiểm soát được** có bằng chứng hỗ trợ.
2. Câu trả lời tiếp theo bắt đầu **suy đoán thiếu dữ liệu**.
3. Chuỗi đi tới điều quá chung như “con người luôn sai” mà không gợi ra hành động.
4. Nguyên nhân rẽ nhánh: cần xem nhiều đường gây lỗi cùng lúc.
5. Một ràng buộc ngoài nhóm cần được chuyển tới người có thẩm quyền.

### 9.4. Không ép chỉ một chuỗi tuyến tính

Nếu một lỗi đăng ký trùng do cả **giao dịch không nguyên tử** và **retry thiếu kiểm soát**, một chuỗi duy nhất có thể bỏ sót vấn đề. Hãy tạo hai nhánh giả thuyết và kiểm tra từng nhánh, hoặc dùng causal map/fishbone bên dưới.

## 10. Fishbone/Ishikawa: mở rộng những nhánh nguyên nhân có thể có

Sơ đồ **xương cá (Ishikawa/Fishbone)** giúp nhóm phân loại những điều kiện có thể góp phần gây ra vấn đề. Nó là **công cụ brainstorming có cấu trúc**, không tự chứng minh các nguyên nhân đã nêu.

Ví dụ: **“Kiểm thử tích hợp liên tục đến muộn trong Sprint”**.

| Nhánh | Các yếu tố cần kiểm tra | Bằng chứng phù hợp |
| --- | --- | --- |
| **Quy trình / chính sách** | Test chỉ được mở sau khi “code xong”, không giới hạn WIP | Workflow thực tế, lịch sử ticket |
| **Công cụ / tự động hóa** | Pipeline quá chậm, kết quả flaky, runner thiếu | CI logs, queue time, test report |
| **Môi trường / dữ liệu** | Test data chung bị sửa, môi trường bị tranh chấp | Lịch sử reset dữ liệu, lỗi môi trường |
| **Thiết kế / kiến trúc** | Thành phần kết nối chặt, hợp đồng API không được kiểm tra | Contract tests, phụ thuộc mô-đun |
| **Thông tin / yêu cầu** | Acceptance criteria chưa rõ, tình huống lỗi bị bỏ sót | Lịch sử refinement, ví dụ nghiệp vụ |
| **Năng lực / phối hợp** | Ít người biết tạo dữ liệu thử, thiếu reviewer dự phòng | Ma trận kỹ năng, lịch phụ thuộc |
| **Ràng buộc / quản trị** | Phải chờ quyền truy cập hoặc phê duyệt ngoài nhóm | Thời gian phê duyệt, chính sách |

### 10.1. Một bản đồ xương cá dạng văn bản

~~~text
                        [Công cụ / CI]
                  runner thiếu, test flaky
                               \
   [Quy trình] ------------------\ 
   test dồn cuối, WIP cao         \
                                  > Kiểm thử tích hợp đến muộn
   [Dữ liệu / môi trường] --------/
   dữ liệu test dùng chung       /
                              /
                     [Yêu cầu / phối hợp]
                     hợp đồng chưa rõ
~~~

Sau khi liệt kê, nhóm nên **chọn vài giả thuyết có tác động và có thể kiểm chứng**, không lập ngay một danh sách 30 hành động cải tiến thiếu nguồn lực.

### 10.2. Fishbone không phải danh sách lỗi con người

Không nên để nhánh “People” chỉ chứa “thiếu cẩn thận”, “lười review” hoặc “không có ý thức”. Nếu vấn đề liên quan kỹ năng, hãy tìm điều kiện cụ thể: **thiếu thời gian hướng dẫn, thiếu tài liệu hệ thống, quyền review quá tập trung hoặc lịch trực không có người dự phòng**.

## 11. Causal map: kiểm tra giả thuyết về quan hệ nhân quả

**Causal map** thể hiện các điều kiện và mối quan hệ giả định, đặc biệt hữu ích khi nhiều yếu tố cùng ảnh hưởng.

~~~mermaid
flowchart LR
    A["PBI quá lớn"] --> C["PR tới review muộn"]
    B["Không giới hạn WIP"] --> D["Hàng chờ review dài"]
    C --> D
    E["Quyền review tập trung"] --> D
    F["Runner/test không ổn định"] --> G["Tích hợp bị lặp và chờ"]
    D --> H["Cycle Time tăng"]
    G --> H
    H --> I["Phản hồi sản phẩm đến muộn"]
    J["Cùng chia nhỏ PBI và hỗ trợ review"] --> C
    J --> D
~~~

Mỗi mũi tên nên được diễn đạt như **giả thuyết có thể kiểm tra**:

- Nếu PR đến muộn vì PBI quá lớn, dữ liệu có thể cho thấy PR lớn hơn có thời gian từ bắt đầu PBI đến tạo PR dài hơn.
- Nếu hàng chờ vì quyền review tập trung, thời gian chờ có thể tăng khi người có quyền vắng hoặc số PR đồng thời tăng.
- Nếu CI flaky gây tích hợp lặp, cần thấy thất bại không ổn định và thời gian điều tra/nhắc chạy lại.

**Tương quan không chứng minh nguyên nhân.** PR lớn có thể đi kèm độ phức tạp cao, nên kích thước PR có thể chỉ là một biểu hiện của loại công việc khó hơn. Cần so sánh trường hợp tương đồng, tìm bằng chứng bổ sung hoặc thử thay đổi có kiểm soát khi phù hợp.

### 11.1. Phân biệt yếu tố kích hoạt và điều kiện tiềm ẩn

Nếu reviewer nghỉ ốm một ngày và hàng chờ tăng, **việc nghỉ ốm không phải vấn đề cần “sửa”**. Điều kiện hệ thống đáng quan tâm là không có phương án phân quyền hoặc chia sẻ kiến thức khi người phụ trách vắng mặt.

### 11.2. Tránh kể câu chuyện hợp lý nhưng không kiểm chứng

“Do văn hóa nhóm kém nên CI đỏ” là cách giải thích khó kiểm chứng và khó hành động. Có thể chuyển thành những giả thuyết cụ thể hơn:

- Test flaky có bị rerun mà không ghi ticket xử lý?
- Quy trình ứng cứu build chung đỏ có được thống nhất?
- Có thời gian dành cho sửa môi trường test?
- Một PR fail CI bao lâu trước khi được xử lý?

## 12. Pareto giúp chọn nơi điều tra, không tự chỉ ra nguyên nhân

**Pareto chart** xếp các loại vấn đề theo một đại lượng như **tần suất, thời gian bị chặn hoặc tác động**. Nó giúp chọn nơi tập trung, nhưng cần phân loại dữ liệu nhất quán.

Giả sử trong tháng có **30 lượt trở ngại** được ghi nhận, phân loại theo nguyên nhân gần nhất:

| Nhóm trở ngại | Số lượt | Tỷ lệ | Lũy kế |
| --- | ---: | ---: | ---: |
| Kiểm thử CI flaky | 12 | 40,0% | 40,0% |
| Chờ review | 8 | 26,7% | 66,7% |
| Môi trường tích hợp không sẵn | 6 | 20,0% | 86,7% |
| Yêu cầu/tiêu chí chấp nhận chưa rõ | 4 | 13,3% | 100,0% |
| **Tổng** | **30** | **100,0%** | — |

Nếu mục tiêu là **giảm số lần gián đoạn**, xem CI flaky và review có thể đáng ưu tiên điều tra vì chúng chiếm **20/30 ≈ 66,7%** lượt trong mẫu.

Nhưng nếu **một sự cố bảo mật** ít xảy ra gây tác động nghiêm trọng, nó vẫn có thể có ưu tiên cao hơn 12 lần flaky nhỏ. **Tần suất không phải mức độ nghiêm trọng**.

### 12.1. Đếm số lượt, số giờ và tác động là ba cách xếp khác nhau

Ví dụ:

- 12 lần flaky test, mỗi lần mất khoảng 5 phút điều tra.
- 2 lần thiếu quyền dữ liệu, mỗi lần chặn cả nhóm hai ngày.

Nếu chỉ xếp **số lượt**, flaky sẽ đứng đầu. Nếu xếp **thời gian chặn** hoặc **rủi ro**, thiếu quyền có thể quan trọng hơn. Nên chọn đại lượng dựa vào **quyết định đang cần hỗ trợ**.

### 12.2. Không mặc định quy tắc 80/20 là luật

Không phải mọi dữ liệu đều tuân “20% nguyên nhân tạo 80% vấn đề”. Pareto là cách **nhìn sự tập trung trong dữ liệu**, không chứng minh một định luật cứng hoặc một nguyên nhân gốc duy nhất.

### 12.3. Chú ý điều kiện ghi nhận

Nếu Developers chỉ ghi lại trở ngại CI vì tool tự có ticket, còn chậm phê duyệt không ai ghi, bảng Pareto sẽ **thiên lệch về loại dễ thu thập**. Cần kiểm tra mức bao phủ dữ liệu trước khi dựa vào đó phân bổ nguồn lực.

## 13. Phân tích lỗi lặp lại khác với đếm bug

Một nhóm có thể ghi “tháng này 24 bug” nhưng chưa biết **loại lỗi nào, mức nghiêm trọng, ở bước nào có thể phát hiện sớm, và vì sao lỗi cùng loại lặp lại**.

### 13.1. Tách lỗi đã phát hiện và lỗi thoát ra môi trường sử dụng

| Loại tín hiệu | Câu hỏi | Điều cần cẩn trọng |
| --- | --- | --- |
| **Defect phát hiện trong kiểm thử** | Kiểm tra nào đang bắt được vấn đề? | Nhiều lỗi được phát hiện sớm không tự chứng minh chất lượng kém hơn |
| **Defect sau phát hành** | Người dùng gặp lỗi nào mà kiểm chứng trước đó chưa phát hiện? | Thiếu quan sát có thể khiến số lỗi thấp giả |
| **Defect tái mở** | Sửa trước đó chưa giải quyết đúng điều kiện nào? | Có thể là lỗi tương tự nhưng cơ chế khác |
| **Regression** | Thay đổi mới phá hành vi đã đúng trước đây? | Cần xác minh phiên bản và hành vi nền |
| **Incident/near miss** | Hậu quả hoặc nguy cơ có nghiêm trọng không? | Số lượng thấp không loại bỏ rủi ro cao |
| **Flaky test** | Bằng chứng kiểm thử có đáng tin không? | Rerun tới khi xanh có thể che lỗi thật |

Nên phân nhóm lỗi theo **hành vi và cơ chế** hơn là chỉ theo tên màn hình. Ví dụ “đăng ký trùng”, “ghi đè tiến độ”, “API trả thành công giả” đều có thể liên quan tính đúng đắn khi có cạnh tranh hoặc trạng thái không chắc chắn, nhưng chưa chắc cùng nguyên nhân.

### 13.2. Ba câu hỏi về lỗi đã xuất hiện nhiều lần

1. **Vì sao lỗi có thể được tạo ra?** Ví dụ logic read-then-write không nguyên tử, hợp đồng API không tương thích.
2. **Vì sao lỗi không được phát hiện trước khi ảnh hưởng?** Ví dụ test chỉ có happy path, không có concurrency/contract test, logs thiếu.
3. **Vì sao lỗi tiếp tục tái diễn sau lần sửa trước?** Ví dụ chỉ sửa giao diện, không xử lý ràng buộc ở tầng dữ liệu hoặc không bổ sung kiểm thử hồi quy.

Ba câu hỏi này thường tạo ra **nhiều lớp hành động bổ sung nhau**: sửa logic, thêm lưới kiểm thử và cải thiện phát hiện/ứng cứu.

### 13.3. Kỷ luật XP hỗ trợ ngăn lỗi tái diễn

- **TDD/kiểm thử tự động:** Viết ví dụ tái hiện và bảo vệ hành vi quan trọng.
- **Continuous Integration:** Tích hợp thay đổi nhỏ để phát hiện xung đột gần thời điểm tạo.
- **Refactoring:** Làm rõ trách nhiệm và giảm logic trùng khiến sửa một nơi mà quên nơi khác.
- **Pair programming/review:** Chia sẻ hiểu biết về rủi ro và thiết kế.
- **Simple design:** Tránh cấu trúc thừa làm khó sửa lỗi.

Không có một kỹ thuật nào tự bảo đảm hết lỗi. **Cần chọn kiểm tra đúng ranh giới có rủi ro**, ví dụ unit test không thay thế kiểm thử tính đồng thời ở database.

## 14. Trở ngại lặp lại: nhìn cả phụ thuộc ngoài quyền của Developers

Nhiều blocker không xuất phát từ code:

- Chờ quyền truy cập môi trường.
- Chờ dữ liệu kiểm thử được phê duyệt.
- Chờ nhà cung cấp sửa API.
- Chờ người có thẩm quyền quyết định yêu cầu nghiệp vụ.
- Chờ nhóm liên quan hoàn tất một thay đổi giao diện/hợp đồng.
- Chờ môi trường tích hợp được khôi phục.

### 14.1. Ghi blocker ở mức có thể hành động

Một bản ghi nên có:

| Trường | Ví dụ |
| --- | --- |
| Item | STORY-18 — Đồng bộ tiến độ học |
| Bắt đầu bị chặn | Thứ Ba, 09:30 |
| Trở ngại | Chưa có môi trường kiểm thử tích hợp phiên bản database mới |
| Tác động | Không xác minh được cập nhật đồng thời |
| Người phối hợp | Developers, người phụ trách môi trường |
| Hành động tiếp | Chuẩn bị dữ liệu giả và cấu hình môi trường theo quy trình |
| Điểm xem lại | Khi môi trường có thể chạy test / cuộc phối hợp gần nhất |
| Phương án thay thế | Spike cục bộ giảm bớt bất định, nhưng chưa tuyên bố tích hợp đã đạt |

**Người phối hợp không nhất thiết là người gây blocker.** Chỉ định giúp hành động có người theo dõi; không biến việc chia trách nhiệm thành đổ lỗi.

### 14.2. Cần xử lý cả trước và sau điểm chặn

Nếu nhiều story chờ quyền dữ liệu vào cuối Sprint, cải tiến có thể không nằm ở “thúc người phê duyệt nhanh hơn” mà ở:

- Nhận diện loại dữ liệu cần dùng ngay trong refinement.
- Nộp yêu cầu phê duyệt sớm với thông tin đầy đủ.
- Dùng dữ liệu giả ở những thử nghiệm không cần dữ liệu thật.
- Ghi thời gian chờ và điều kiện khiến yêu cầu thường bị trả lại.
- Điều chỉnh phụ thuộc hoặc thứ tự PBI theo rủi ro.

Nếu ràng buộc ngoài nhóm là bắt buộc, **không lách quy trình** để đạt tốc độ. Chọn thay đổi trong phần nhóm kiểm soát được và đưa rủi ro tới đúng thẩm quyền.

## 15. Tình huống sâu: lỗi đăng ký khóa học trùng liên tục tái xuất

### 15.1. Phát biểu vấn đề

Trong ví dụ giả định, ba lần trong bốn tuần, người học đăng ký khóa miễn phí gặp trạng thái **hai bản ghi đăng ký đang có hiệu lực** cho cùng một tài khoản và khóa. Nhóm từng sửa giao diện để vô hiệu hóa nút sau khi bấm, nhưng lỗi lại xuất hiện khi một client gửi lại yêu cầu sau timeout.

Không nên kết luận ngay “người dùng bấm quá nhanh”. Người dùng có thể thao tác lặp, mạng có thể gửi lại hoặc một dịch vụ có thể retry. **Hệ thống phải xử lý những điều kiện nằm trong phạm vi yêu cầu tin cậy**, không coi hành vi mạng bình thường là lỗi đạo đức của người dùng.

### 15.2. Timeline sự kiện minh họa

| Thời điểm | Điều xảy ra | Bằng chứng có thể cần |
| --- | --- | --- |
| 10:00:00 | Người học gửi yêu cầu đăng ký khóa Java nhập môn | Request ID, tài khoản và khóa được truy vết an toàn |
| 10:00:01 | Backend kiểm tra “chưa có đăng ký Active” | Log/tracing phù hợp, mã xử lý phiên bản đang chạy |
| 10:00:02 | Client timeout trước khi nhận phản hồi | Log lỗi client và dịch vụ |
| 10:00:03 | Client gửi lại yêu cầu đăng ký | Cùng khóa/tài khoản; có idempotency key không? |
| 10:00:04 | Hai xử lý gần đồng thời đều vượt kiểm tra tồn tại | Kiểm thử tái hiện trên DB mục tiêu |
| 10:00:05 | Hai bản ghi Active được tạo | Dữ liệu kiểm chứng, không tự thay đổi bản ghi thật |
| 10:05:00 | Người học thấy kết quả không nhất quán và gửi yêu cầu hỗ trợ | Phản hồi và phạm vi ảnh hưởng |

**Timeline chỉ là một kịch bản cần kiểm chứng**, không phải kết luận mọi lỗi trùng đều xảy ra đúng thứ tự này. Trong hệ thống phân tán, đồng hồ và thứ tự log có thể không hoàn toàn chính xác; cần xét correlation ID và dữ liệu giao dịch.

### 15.3. Phân tách các đường gây lỗi

Nhóm có thể lập các giả thuyết:

| Giả thuyết | Dấu hiệu có thể xác minh | Không được kết luận trước |
| --- | --- | --- |
| Logic “đọc rồi ghi” không nguyên tử | Hai request đồng thời cùng đọc chưa tồn tại rồi cùng ghi | “Chắc do Developer viết sai có chủ ý” |
| DB không có ràng buộc phù hợp | Có thể tạo hai bản ghi Active giống cặp tài khoản–khóa | “Cứ thêm unique index là xong mọi nghiệp vụ” |
| Retry không có quy tắc idempotency | Một yêu cầu logic có thể tạo nhiều tác động khi gửi lại | “Cần cấm người học bấm lại” |
| UI báo trạng thái sai khi timeout | Người dùng không biết lưu đã thành công hay chưa | “Đã sửa UI là hết nguy cơ dữ liệu” |
| Kiểm thử chỉ có đường thành công | Test suite không bao phủ concurrent write/timeout | “Coverage cao thì không thể có lỗi này” |
| Không có giám sát dữ liệu bất thường | Bản ghi trùng tồn tại lâu trước khi phát hiện | “Chưa nhận ticket thì không có vấn đề” |

Các giả thuyết **không loại trừ nhau**. Hệ thống có thể cần kiểm soát nhiều tầng.

### 15.4. Kiểm thử tái hiện trước khi sửa

Một kiểm thử có ích phải tái hiện được tình huống rủi ro trên môi trường phù hợp. Ví dụ:

~~~gherkin
Tính năng: Không tạo đăng ký đang có hiệu lực trùng nhau

  Tình huống: Gửi hai yêu cầu đăng ký gần đồng thời
    Cho trước người học đã đăng nhập hợp lệ
    Và khóa "Java nhập môn" đang cho phép đăng ký miễn phí
    Và người học chưa có đăng ký đang có hiệu lực
    Khi hai yêu cầu đăng ký cùng khóa được gửi gần đồng thời
    Thì hệ thống không tạo hai đăng ký đang có hiệu lực trùng nhau
    Và mỗi yêu cầu nhận phản hồi tuân theo hợp đồng đã thống nhất

  Tình huống: Retry khi chưa chắc phản hồi đã tới client
    Cho trước một yêu cầu đăng ký đã được server xử lý
    Và phản hồi của yêu cầu đó không tới client
    Khi client gửi lại cùng một thao tác theo chính sách retry
    Thì hệ thống không tạo tác động đăng ký trùng
    Và người học có cách xác định trạng thái cuối cùng phù hợp

  Tình huống: Dữ liệu của tài khoản khác không bị lộ
    Cho trước tài khoản A đã đăng nhập
    Và một đăng ký thuộc tài khoản B
    Khi A cố xem hoặc sửa đăng ký của B
    Thì hệ thống từ chối theo chính sách phân quyền
    Và không tiết lộ dữ liệu của B
~~~

Các bước Gherkin chỉ mô tả hành vi mong muốn. Muốn chạy cần bước kiểm thử, dữ liệu giả, môi trường và cách tạo yêu cầu gần đồng thời. **Hai yêu cầu chạy tuần tự hoàn toàn chưa chắc kiểm tra được race condition.**

### 15.5. Biện pháp ngăn lặp có thể kết hợp

1. **Quy tắc nghiệp vụ:** Thống nhất thế nào là “đăng ký đang có hiệu lực”, đăng ký lại sau khi hủy có hợp lệ không.
2. **Tính nhất quán dữ liệu:** Dùng cơ chế giao dịch hoặc ràng buộc thích hợp ở tầng dữ liệu để bảo vệ bất biến; kiểm tra trên DB mục tiêu.
3. **Idempotency/retry:** Xác định cách một thao tác logic lặp lại được xử lý, phân biệt retry thật và thao tác nghiệp vụ mới.
4. **Hợp đồng API:** Trạng thái đã đăng ký, trùng, timeout và lỗi được diễn đạt nhất quán cho client.
5. **Kiểm thử:** Bổ sung test đồng thời, integration và hồi quy; không chỉ unit test với mock.
6. **Giám sát:** Phát hiện dữ liệu bất thường và tỷ lệ yêu cầu lỗi với quyền truy cập phù hợp.
7. **Quy trình:** Sửa lỗi ở ranh giới hệ thống, không chỉ vô hiệu nút trong UI rồi đánh dấu vấn đề đã hết.

**Không tự thêm ràng buộc unique hoặc xóa bản ghi production** khi chưa hiểu dữ liệu lịch sử, giao dịch đang diễn ra, cách hủy/đăng ký lại và chiến lược migration/khôi phục. Cần phối hợp người có thẩm quyền dữ liệu.

### 15.6. Khi nào xem hành động đã hiệu quả?

Chưa đủ để nói “đã merge PR”. Cần bằng chứng:

- Kiểm thử cạnh tranh và retry theo giả thuyết trước đó **không tái hiện hành vi sai** trên môi trường đủ đại diện.
- Những luồng hợp lệ khác vẫn hoạt động và đạt **Definition of Done**.
- Migration hoặc làm sạch dữ liệu được thực hiện đúng quyền và có kiểm chứng.
- Sau rollout, giám sát không ghi nhận lỗi trùng cùng cơ chế trong phạm vi quan sát phù hợp.
- Có kế hoạch tiếp tục theo dõi vì **không xuất hiện lỗi trong vài ngày không chứng minh rủi ro đã bằng 0**.

## 16. Phân biệt khắc phục tức thời, phòng ngừa và cải tiến cách phát hiện

Trong điều tra chất lượng, ba loại hành động thường bị gộp thành “đã sửa”.

| Loại hành động | Mục đích | Ví dụ đăng ký trùng |
| --- | --- | --- |
| **Containment/mitigation — Khoanh vùng, giảm tác động** | Bảo vệ người dùng và dừng tác động đang diễn ra | Tạm hạn chế luồng có lỗi theo quyền hạn, hỗ trợ người dùng bị ảnh hưởng |
| **Corrective action — Khắc phục cơ chế gây lỗi** | Xử lý nguyên nhân tạo hành vi sai | Thêm tính nhất quán giao dịch và kiểm tra quy tắc Active phù hợp |
| **Preventive action — Giảm khả năng tạo lại loại lỗi** | Cải thiện hệ thống phát triển, phát hiện hoặc chính sách | Test concurrent ở CI, checklist review cho thao tác ghi nhạy cảm |
| **Detection/recovery improvement — Phát hiện, khôi phục** | Giảm thời gian lỗi tồn tại và tác hại khi lỗi xảy ra | Alert dữ liệu bất thường, truy vết request và runbook khôi phục |

Không có một “hành động gốc” duy nhất phù hợp mọi sự cố. Một lỗi quyền dữ liệu có thể cần nhiều lớp kiểm soát độc lập.

### 16.1. Hành động yếu và hành động mạnh hơn

**Yếu:** “Nhắc mọi người cẩn thận hơn khi sửa phần đăng ký.”

**Cụ thể hơn:** “Bổ sung integration test tái hiện hai request concurrent, xác nhận bất biến dữ liệu ở DB và yêu cầu kiểm tra đó trong CI trước khi tích hợp thay đổi liên quan đăng ký.”

**Chưa đủ nếu chỉ làm vậy:** Test có thể bỏ sót điều kiện chưa nghĩ tới; cần xem cả thiết kế giao dịch, observability, quyền dữ liệu và chính sách vận hành.

### 16.2. Khôi phục build xanh không đồng nghĩa sửa nguyên nhân

Nếu CI đỏ vì flaky test, một lần rerun xanh có thể giúp biết lần chạy tiếp theo đã đạt, nhưng **không giải quyết vì sao kiểm thử không ổn định**. Nhóm cần điều tra dữ liệu dùng chung, phụ thuộc thời gian, thứ tự chạy, môi trường hoặc race condition.

Ngược lại, việc vội “quarantine” mọi test đang lỗi có thể che một rủi ro thực. Nếu phải cách ly kiểm thử theo chính sách để phục hồi dòng tích hợp, cần **ghi rõ phần bằng chứng thiếu, người theo dõi và điều kiện khôi phục kiểm tra**, không tuyên bố DoD đã đạt nếu kiểm tra bắt buộc còn chưa thỏa.

## 17. Chọn biện pháp cải tiến có thể kiểm chứng

Một hành động cải tiến tốt có:

- **Vấn đề rõ:** Điều không mong muốn đang lặp lại ở đâu?
- **Cơ chế giả định:** Vì sao hành động có khả năng ảnh hưởng vấn đề?
- **Phạm vi nhỏ và an toàn:** Có thể thử trước khi áp dụng rộng?
- **Bằng chứng thành công:** Metric hoặc quan sát nào sẽ thay đổi?
- **Guardrail:** Không được làm xấu chất lượng, an toàn hay outcome nào?
- **Người phối hợp:** Ai có khả năng thực hiện và đúng quyền hạn?
- **Điểm xem lại:** Khi nào quyết định giữ, điều chỉnh hoặc bỏ thử nghiệm?

### 17.1. Một ma trận ưu tiên hành động

| Biện pháp | Vấn đề nhắm tới | Tác động kỳ vọng | Chi phí/rủi ro cần xem |
| --- | --- | --- | --- |
| Giới hạn WIP tại phát triển | Hàng chờ review phình ra | Ít PR đồng thời, hoàn tất đều hơn | Cần chính sách kéo và hợp tác của nhóm |
| Tạo reviewer dự phòng có hướng dẫn | Phụ thuộc một người | Giảm thời gian chờ khi có gián đoạn | Cần đào tạo, quyền review phù hợp |
| Chia PR nhỏ hơn | Review khó hiểu, tích hợp muộn | Phản hồi nhanh hơn | Phải giữ lát cắt có nghĩa và kiểm thử |
| Ổn định test data của CI | Flaky, rerun và chờ | Kết quả kiểm tra đáng tin hơn | Cần thay fixture/môi trường |
| Thêm test hợp đồng API | Lỗi semantic khi frontend/backend ghép | Phát hiện sai khác sớm | Không thay thế mọi end-to-end test |
| Xử lý ràng buộc đăng ký tại DB | Dữ liệu Active trùng | Bảo vệ bất biến quan trọng | Cần migration có kiểm chứng, khả năng khôi phục |

Nếu rủi ro là **mất dữ liệu hoặc truy cập trái phép**, mức độ nghiêm trọng có thể đòi xử lý ngay dù biện pháp tốn công hơn. Không ưu tiên chỉ bằng “dễ triển khai nhất”.

### 17.2. Đừng chọn quá nhiều hành động cùng lúc

Một Retrospective đưa ra 18 action items chưa chắc hữu ích bằng **một thay đổi có người thực hiện và đo được tác động**. Nhiều hành động đồng thời còn khiến nhóm khó biết yếu tố nào tạo khác biệt.

Khi rủi ro bắt buộc đòi nhiều biện pháp cùng lúc, vẫn phải thực hiện đầy đủ; nhưng có thể phân biệt **biện pháp bảo vệ bắt buộc** với **thử nghiệm cải tiến quy trình** để đánh giá rõ.

## 18. PDSA/PDCA: từ giả thuyết nguyên nhân tới cải tiến có bằng chứng

Vòng **Plan–Do–Study–Act (PDSA)** hoặc cách gọi gần **Plan–Do–Check–Act (PDCA)** là khung học hỏi cải tiến hữu ích, không phải nghi lễ bắt buộc của Scrum.

~~~mermaid
flowchart LR
    A["Plan: vấn đề, giả thuyết, phép đo, guardrail"] --> B["Do: thử thay đổi có giới hạn"]
    B --> C["Study: đối chiếu dữ liệu, bối cảnh, tác dụng phụ"]
    C --> D{"Kết quả có đủ hữu ích?"}
    D -->|"Có"| E["Act: giữ/chia sẻ, rồi theo dõi"]
    D -->|"Chưa"| F["Act: sửa giả thuyết hoặc cách thử"]
    E --> A
    F --> A
~~~

### 18.1. Plan — Lập kế hoạch kiểm chứng

**Vấn đề:** Review trở thành hàng chờ lớn, khiến user story hoàn tất muộn.

**Giả thuyết:** Nếu nhóm giới hạn WIP ở phát triển và ưu tiên review những item gần Done, thời gian chờ review và Cycle Time sẽ giảm, không làm tăng lỗi bỏ sót.

**Thử nghiệm:** Trong hai Sprint, thử chính sách:

1. Không kéo thêm một PBI nếu đang có item review cũ cần hỗ trợ và nhóm có khả năng giúp.
2. Chia thay đổi thành PR nhỏ có mô tả mục đích, ví dụ hành vi và kiểm thử.
3. Có reviewer dự phòng khi người phụ trách đang xử lý incident.
4. Ghi timestamp review, WIP và blocker theo cùng định nghĩa trước/sau.

**Metric chính:** Phân bố Cycle Time và thời gian chờ review của những PBI tương đồng.

**Guardrails:** Defect sau phát hành, review chất lượng thấp, DoD, mức quá tải và nhiệm vụ vận hành không được xấu đi.

### 18.2. Do — Thử trong phạm vi rõ

Nhóm thực hiện chính sách tại một luồng PBI tương đồng, đảm bảo người tham gia hiểu cách ghi trạng thái. Nếu giữa chừng có sự cố khẩn, cần ghi biến cố ấy thay vì ép dữ liệu “đẹp như dự kiến”.

### 18.3. Study — Đọc kết quả và giới hạn

Giả sử trước thử có 12 Cycle Time như ở mục 8:

~~~text
Trước:
2, 3, 4, 4, 5, 6, 7, 8, 9, 11, 13, 18
~~~

Sau thử có 12 PBI khác, giả định cùng định nghĩa workflow và loại công việc tương tự:

~~~text
Sau:
2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 9, 12
~~~

| Thước đo | Trước | Sau | Mức thay đổi quan sát |
| --- | ---: | ---: | --- |
| Số PBI Done | 12 | 12 | Không đổi trong mẫu |
| Tổng ngày-item | 90 | 66 | Giảm 24 ngày-item |
| Cycle Time trung bình | 7,5 ngày | 5,5 ngày | Giảm 2 ngày |
| Cycle Time trung vị | 6,5 ngày | 5 ngày | Giảm 1,5 ngày |
| P85 nearest-rank | 13 ngày | 9 ngày | Giảm 4 ngày |
| P95 nearest-rank | 18 ngày | 12 ngày | Giảm 6 ngày |

**Kiểm tra phép tính sau thử:**

\[
2+3+3+4+4+5+5+6+6+7+9+12=66
\]

\[
\text{Trung bình sau}=\frac{66}{12}=5{,}5
\quad;\quad
\text{Trung vị sau}=\frac{5+5}{2}=5
\]

P85 nearest-rank sau thử ở vị trí \(\lceil0{,}85\times12\rceil=11\), giá trị **9**. P95 ở vị trí 12, giá trị **12**.

**Đây là dữ liệu minh họa, không phải kết quả triển khai thực tế**. Dù các con số cải thiện, chưa đủ khẳng định chính sách WIP/review **gây ra** mức giảm: hai giai đoạn có thể khác độ khó PBI, nhân sự, sự cố vận hành hoặc cách chia việc. Cỡ mẫu 12 cũng nhỏ để suy ra phân vị tương lai ổn định.

### 18.4. Nhìn Work Item Age để tránh bỏ sót việc khó

Chỉ dùng Cycle Time của item Done có thể **bỏ quên PBI còn dở rất lâu**. Sau thử, nhóm phải xem có item 20 ngày vẫn ở Review hay không; nếu có, thống kê của những item đã hoàn tất chưa phản ánh hết vấn đề.

### 18.5. Guardrails quyết định có nên duy trì

Nếu Cycle Time giảm nhưng sự cố dữ liệu sau phát hành tăng, nhóm **không được tuyên bố cải tiến toàn diện**. Cần xem cách review, test và áp lực công việc đã thay đổi ra sao.

Nếu các kiểm tra chất lượng vẫn đạt và các item ít bị chặn hơn trong nhiều kỳ, nhóm có cơ sở mạnh hơn để giữ chính sách.

### 18.6. Act — Chuẩn hóa có điều kiện hoặc chỉnh lại giả thuyết

Kết quả tốt có thể dẫn tới việc đưa working agreement về review vào cách làm chung; đặt lịch xem lại sau vài Sprint. Kết quả chưa tốt có thể chỉ ra nút nghẽn chính là **test data và runner**, không phải review—khi đó điều chỉnh hướng cải tiến.

**PDSA là vòng học, không phải con dấu chứng nhận thành công.**

## 19. Dùng dữ liệu theo thời gian mà không suy diễn quá mức

Nhóm thường so một tuần “trước” với một tuần “sau” rồi gọi là tác động chắc chắn. Trong dòng công việc, biến động tự nhiên có thể lớn.

### 19.1. Run chart và sự thay đổi

Một **run chart** cho thấy metric theo thời gian với cùng cách đo. Ví dụ median review wait của các tuần giả định:

~~~text
Tuần:                  1    2    3    4   |  5    6    7    8
Chờ review (ngày):    2,5  3,0  2,0  3,5 | 1,8  1,5  1,2  1,4
                                           ^ thử chính sách mới
~~~

Đường số gợi ý một thay đổi sau tuần thứ tư, nhưng có thể có nguyên nhân khác: ít incident, thay reviewer, PBI nhỏ hơn. Cần xem bối cảnh và thêm số kỳ.

Nếu dùng **control chart**, phải hiểu cách xác lập giới hạn kiểm soát và tính chất dữ liệu; không tự vẽ một ngưỡng tùy ý rồi gọi đó là chứng minh thống kê.

### 19.2. Điều gì làm hai giai đoạn không so sánh được?

- Trước là PBI lớn, sau chia rất nhỏ.
- Trước có lỗi khẩn và migration, sau chủ yếu thay câu chữ.
- Trước tính Done khi kiểm thử tích hợp xong, sau tính khi merge.
- Trước đo ngày lịch, sau đo ngày làm việc.
- Trước thiếu người review, sau có một nhóm khác hỗ trợ.
- Trước ghi cả item Blocked vào WIP, sau chuyển chúng sang cột “Tạm dừng” nằm ngoài phạm vi đo.

Không nhất thiết các giai đoạn phải hoàn toàn giống nhau, nhưng **phải nêu thay đổi** trước khi suy luận.

### 19.3. Cái gì là bằng chứng mạnh hơn?

Tùy vấn đề, bằng chứng có thể được củng cố bằng:

1. Có **cơ chế hợp lý và kiểm chứng trực tiếp**, ví dụ ràng buộc DB ngăn bản ghi Active trùng.
2. Có **nhiều quan sát theo thời gian**, không chỉ một tuần.
3. Loại item, định nghĩa đo và dữ liệu ổn định.
4. Guardrail chất lượng không xấu đi.
5. Có kiểm tra độc lập hoặc thử nghiệm có phân bổ phù hợp khi cần kết luận nhân quả.
6. Có khả năng giải thích những trường hợp ngoại lệ và nguyên nhân còn lại.

Không phải mọi cải tiến quy trình đều có thể A/B test ngẫu nhiên; khi đó **thừa nhận giới hạn kết luận** là một phần của tư duy khoa học, không phải lý do bỏ việc cải tiến.

## 20. Sau sự cố: postmortem không đổ lỗi và trách nhiệm công bằng

Một cuộc **blameless postmortem** nhằm hiểu hệ thống và điều kiện quyết định của người tham gia trong bối cảnh thực, thay vì tìm ai để chỉ trích. Tinh thần không đổ lỗi giúp mọi người chia sẻ dữ kiện sớm và đầy đủ.

### 20.1. Những câu hỏi giúp tạo môi trường học hỏi

- Khi sự cố diễn ra, người xử lý **đã nhìn thấy thông tin gì**?
- Quyết định lúc đó có vẻ hợp lý theo điều kiện và hướng dẫn nào?
- Hệ thống có những cảnh báo nào? Cảnh báo nào thiếu hoặc gây nhiễu?
- Những giả định nào không được kiểm chứng?
- Điều kiện nào khiến sai lệch tồn tại lâu mà không ai nhận ra?
- Nếu đặt một người có năng lực khác vào cùng điều kiện, lỗi có còn khả năng xảy ra?
- Có biện pháp phòng ngừa/phát hiện nào thực tế và bền vững?

### 20.2. Không đổ lỗi không đồng nghĩa không có trách nhiệm

**Blameless** không có nghĩa làm ngơ hành vi cố ý gây hại, vi phạm nghiêm trọng hoặc che giấu thông tin. Những trường hợp ấy cần được xử lý theo quy định và quy trình phù hợp, tách khỏi mục tiêu học hỏi hệ thống.

Với sai sót nghề nghiệp thông thường, mục tiêu là **cải thiện điều kiện làm việc, công cụ và chính sách** để giảm khả năng tái diễn, thay vì dừng ở “người đó phải tập trung hơn”.

### 20.3. Bảo vệ thông tin nhạy cảm

Postmortem có thể chứa request ID, thông tin tài khoản, sự cố dữ liệu hoặc cấu hình. Hãy dùng phạm vi truy cập thích hợp, loại bỏ định danh cá nhân khi không cần thiết và tránh đưa secret, mật khẩu hoặc dữ liệu người dùng vào báo cáo phổ biến rộng.

### 20.4. Không biến postmortem thành danh sách việc vô hạn

Một postmortem có thể ghi nhiều yếu tố góp phần nhưng nên chọn **một tập hành động có ưu tiên, người thực hiện, mốc đánh giá và cách xác minh**. Hành động cần theo dõi đến khi có bằng chứng, không đóng chỉ vì đã tạo ticket.

## 21. Scrum: dùng Retrospective để cải tiến, không đợi tới cuối Sprint mới phản ứng

**Sprint Retrospective** là sự kiện Scrum nhằm lập kế hoạch nâng cao chất lượng và hiệu quả. Scrum Team kiểm tra cách Sprint đã diễn ra xét về cá nhân, tương tác, quy trình, công cụ và Definition of Done. Những giả định gây sai lệch được nhận diện và tìm nguồn gốc; nhóm thảo luận các thay đổi hữu ích nhất để cải thiện hiệu quả.

### 21.1. Một nhịp cải tiến phù hợp Scrum

| Thời điểm | Hành động có ích | Tránh hiểu sai |
| --- | --- | --- |
| **Sprint Planning** | Xem rủi ro tích hợp, năng lực và cách đạt DoD | Không ước lượng chỉ phần code rồi đẩy test sang cuối |
| **Trong Sprint** | Xử lý build đỏ, gỡ blocker, điều chỉnh Sprint Backlog | Không chờ Retrospective nếu người dùng đang bị ảnh hưởng |
| **Daily Scrum** | Developers kiểm tra tiến độ hướng Sprint Goal và phối hợp hành động | Không biến thành báo cáo tiến độ cho quản lý |
| **Sprint Review** | Kiểm tra Increment và phản hồi stakeholder, điều chỉnh Product Backlog | Không giới thiệu PBI chưa đạt DoD như Increment |
| **Sprint Retrospective** | Phân tích các điều kiện lặp lại và chọn cải tiến có tác động | Không chỉ ghi “phối hợp tốt hơn” rồi dừng |

Scrum **không bắt buộc 5 Whys, fishbone, một template postmortem hay một số lượng action item cố định**. Scrum Team có thể chọn kỹ thuật thích hợp để phục vụ mục đích kiểm tra và thích ứng.

### 21.2. Những trách nhiệm cần rõ

- **Developers:** Tạo Increment đáp ứng DoD, chủ động điều chỉnh kế hoạch và xử lý các trở ngại kỹ thuật trong khả năng.
- **Product Owner:** Tối đa hóa giá trị và quản lý hiệu quả Product Backlog; cộng tác làm rõ tác động sản phẩm và ưu tiên những cải tiến cần thiết.
- **Scrum Master:** Hỗ trợ Scrum Team áp dụng Scrum, cải thiện hiệu quả và thúc đẩy loại bỏ trở ngại; không phải “người truy tìm cá nhân gây lỗi”.
- **Scrum Team:** Cùng kiểm tra cách làm và chọn cải tiến để nâng chất lượng, hiệu quả.
- **Bên liên quan có thẩm quyền:** Tham gia khi hành động liên quan pháp lý, quyền dữ liệu, hợp đồng, bảo mật hoặc quyền vận hành.

### 21.3. Cải tiến kỹ thuật có thể vào backlog thế nào?

Thay vì “refactor vì code xấu”, mô tả:

> “Mỗi lần đổi hợp đồng API đăng ký, nhóm mất nhiều ngày kiểm tra lại giao diện vì không có contract test. Chúng ta muốn bổ sung kiểm tra hợp đồng tại ranh giới UI–API để phát hiện sai khác trong CI trước khi merge; sẽ theo dõi lỗi tích hợp thoát sang staging và thời gian chờ review.”

Product Owner cần hiểu **tác động tới khả năng giao giá trị và rủi ro** để ưu tiên phù hợp. Developers giữ trách nhiệm lựa chọn cách thực hiện kỹ thuật.

### 21.4. Sprint Goal và DoD vẫn quan trọng khi cải tiến

Cải tiến không phải giấy phép bỏ Sprint Goal hoặc hạ DoD. Trong Sprint, chất lượng không được giảm. Khi việc điều tra phát hiện phạm vi phải thay đổi, Developers cần trao đổi với Product Owner. Nếu một PBI chưa đạt DoD, nó **không trở thành Increment Done** chỉ vì đã “sửa gần hết”.

## 22. Kanban: cải tiến luồng bằng chính sách rõ và dữ liệu age/WIP

Kanban giúp nhóm thấy **công việc đang ở đâu, chờ bao lâu và bị chặn vì điều gì**. Nó hỗ trợ phân tích nguyên nhân về dòng công việc ngay cả khi nhóm đang dùng Scrum hoặc XP.

### 22.1. Trực quan hóa workflow

Một workflow minh họa:

~~~text
Ready -> Development -> Code Review -> Integration Test -> Done
             |                |                |
          WIP limit       WIP limit        WIP limit

Blocked là trạng thái/nhãn rõ theo chính sách khi một item
không thể tiến tiếp; item vẫn được tính là WIP nếu đã bắt đầu.
~~~

**Không bắt buộc mọi nhóm phải có các cột này.** Nên chọn các bước thực sự có chính sách và hàng chờ có thể điều tra.

### 22.2. Chính sách xử lý item già đi

Nhóm có thể thống nhất:

- Khi item tiến gần hoặc vượt **SLE** tham khảo, kiểm tra tuổi, bước hiện tại và lý do.
- Ưu tiên gỡ blocker và cùng hoàn tất thay vì chỉ kéo item mới.
- Xác định ai có thể giúp review, kiểm thử, dữ liệu hoặc ra quyết định.
- Thông báo rủi ro cho bên cần biết, không tự hứa item sẽ Done sau một ngày.
- Cập nhật nguyên nhân và bài học nếu vấn đề lặp lại.

**SLE không phải lời hứa mọi item phải xong trước mốc**. Nó là công cụ dự báo/quan sát rủi ro theo một kỳ vọng xác định.

### 22.3. Một thử nghiệm giảm WIP

Giả sử Review liên tục có 5–6 item đang chờ. Nhóm có thể thử chính sách **giới hạn 2 item trong Review** theo khả năng phục vụ, đồng thời ưu tiên hoàn tất công việc đã bắt đầu trước khi nhận thêm.

Lưu ý:

1. WIP limit chỉ có tác dụng khi mọi người **tôn trọng chính sách thực**, không chuyển nhãn để né con số.
2. Nếu bottleneck nằm ở **môi trường tích hợp**, giảm WIP Review có thể ít tác dụng.
3. Người review dự phòng cần hiểu mã và có quyền phù hợp.
4. Đo kết quả theo thời gian cùng quality guardrails, không tuyên bố cải tiến sau một ngày.

### 22.4. Vì sao flow metrics không phải KPI cá nhân?

Cycle Time dài có thể do yêu cầu bị đổi, môi trường chưa sẵn, dữ liệu cần phê duyệt hoặc hàng chờ review—những điều không nằm trong quyền một Developer. Dùng dữ liệu để **điều chỉnh dòng công việc cấp hệ thống**, không xếp hạng người làm.

## 23. XP: dùng kỹ thuật để loại bỏ điều kiện gây lỗi tái diễn

**Extreme Programming** đặc biệt có ích khi nguyên nhân liên quan **chất lượng mã, kiểm thử, tích hợp và khả năng thay đổi**.

| Thực hành XP | Vấn đề thường hỗ trợ xử lý | Bằng chứng nên theo dõi |
| --- | --- | --- |
| **Test-Driven Development** | Quy tắc nghiệp vụ không được diễn đạt thành ví dụ kiểm tra | Test phản ánh yêu cầu và lỗi hồi quy |
| **Continuous Integration** | Merge muộn, hợp đồng sai, build chung đỏ kéo dài | Thời gian phản hồi CI, trạng thái nhánh chung, lỗi tích hợp |
| **Refactoring** | Logic trùng và phụ thuộc chặt khiến sửa một nơi phá nơi khác | Phạm vi tác động, kiểm thử, khả năng review |
| **Pair programming** | Một người nắm giữ kiến thức trọng yếu, khó phát hiện giả định | Chia sẻ hiểu biết, giảm thời gian gỡ lỗi |
| **Small releases** | Phản hồi người dùng đến muộn | Lát cắt đạt DoD, kết quả sử dụng và lỗi |
| **Simple design** | Cấu trúc quá phức tạp làm việc đổi hướng tốn công | Thời gian thay đổi, số phụ thuộc không cần thiết |

### 23.1. Kiểm thử không chỉ để “đèn xanh”

Một lỗi đăng ký trùng không thể được bảo vệ đầy đủ bằng unit test kiểm tra một yêu cầu đơn. Cần xem **ranh giới có nguy cơ**:

- Test đồng thời tại DB hoặc dịch vụ.
- Contract test giữa API và client khi đổi trạng thái.
- Kiểm thử quyền truy cập tài khoản.
- Kiểm thử retry/timeout.
- Kiểm thử migration trên dữ liệu đại diện.

Tuy nhiên, không nhất thiết mọi PBI phải chạy mọi loại test. **Chọn kiểm tra theo rủi ro và tiêu chuẩn chất lượng áp dụng**.

### 23.2. Refactor để lỗi khó tái diễn hơn

Nếu quy tắc đăng ký tồn tại ở UI, API A, API B và batch job với bốn cách khác nhau, sửa một nơi có thể còn lỗi ở nơi khác. Refactoring có kiểm thử giúp ranh giới nghiệp vụ rõ và giảm logic lặp.

**Refactoring** nghĩa là cải thiện cấu trúc mà không chủ định đổi hành vi đã xác định. Nếu thay quy tắc “đăng ký lại sau hủy”, đó còn là **thay đổi hành vi** cần tiêu chí chấp nhận riêng.

### 23.3. Build chung đỏ là tín hiệu cần xử lý sớm

Khi build sau merge thất bại, nhóm nên điều tra, ưu tiên sửa hoặc hoàn nguyên theo chính sách và xác nhận trạng thái chung trước khi đẩy thêm nhiều thay đổi không liên quan. **Không giải quyết bằng cách xóa test khó hoặc hạ DoD để tạo biểu đồ xanh**.

## 24. Lean và A3: giải quyết vấn đề để tối ưu toàn dòng giá trị

Lean khuyến khích học hỏi, giảm chờ đợi, tránh làm lại và cải tiến liên tục. **A3 problem-solving** là một hình thức tổ chức thông tin vấn đề trên một trang/bản trình bày ngắn, không phải khuôn mẫu bắt buộc.

### 24.1. Một A3 rút gọn cho vấn đề review kéo dài

| Thành phần A3 | Nội dung minh họa |
| --- | --- |
| **Bối cảnh** | Nền tảng học cần giao cải tiến đăng ký theo các Sprint ngắn |
| **Vấn đề** | Nhiều PBI chờ review ba đến bốn ngày trước khi tích hợp |
| **Điều kiện hiện tại** | PR thường dồn cuối Sprint; reviewer có quyền bị phân tán |
| **Mục tiêu** | Giảm thời gian chờ review mà không tăng lỗi hoặc hạ DoD |
| **Phân tích nguyên nhân** | 5 Whys, timeline, WIP và phân bố review wait; giả thuyết về policy |
| **Biện pháp thử** | Giới hạn WIP, PR nhỏ, reviewer dự phòng |
| **Theo dõi** | Age, cycle time, throughput, lỗi sau phát hành, trạng thái review |
| **Học hỏi** | Giữ, điều chỉnh hoặc bỏ biện pháp theo dữ liệu và phản hồi |

### 24.2. Tránh tối ưu cục bộ

Giảm thời gian review bằng cách **không review nữa** có thể làm số liệu đẹp nhưng lỗi production tăng. Tương tự, một Developer “năng suất cao” mở nhiều PBI làm tăng WIP nhưng không giúp Increment Done nhanh hơn.

Lean hướng tới **kết quả của toàn dòng tạo giá trị**, không chỉ tốc độ từng công đoạn.

### 24.3. Cải tiến liên tục khác dự án cải tổ một lần

Một nhóm không cần chờ tái cấu trúc toàn bộ tổ chức mới có thể cải tiến. Có thể bắt đầu bằng một vấn đề có bằng chứng, một thử nghiệm nhỏ, một điểm xem lại và tiếp tục điều chỉnh. Nhưng nếu nguyên nhân nằm ở chính sách quyền hạn hoặc phụ thuộc liên nhóm, **cải tiến nhỏ cần được phối hợp với người có thẩm quyền**, không chỉ nhắc Developers “tự chủ”.

## 25. Tổ chức một buổi phân tích nguyên nhân hiệu quả

Một buổi Retrospective hoặc workshop ngắn có thể theo cấu trúc **gợi ý 50 phút**. Đây không phải thời lượng bắt buộc của Scrum; thực tế cần điều chỉnh theo rủi ro, người tham gia và lượng bằng chứng.

| Phần | Thời gian minh họa | Mục đích |
| --- | ---: | --- |
| Mở đầu và nhắc mục đích không đổ lỗi | 5 phút | Thống nhất học để cải tiến |
| Nhìn vấn đề, tác động và dữ liệu | 10 phút | Cùng hiểu điều gì đã xảy ra |
| Lập timeline và giả thuyết | 10 phút | Tách quan sát khỏi suy đoán |
| 5 Whys/fishbone/causal map | 10 phút | Xác định điều kiện đáng kiểm chứng |
| Chọn biện pháp nhỏ và guardrail | 10 phút | Có quyết định thực tế |
| Ghi người theo dõi và điểm xem lại | 5 phút | Không để action item bị quên |

### 25.1. Ai nên tham gia?

Người hiểu vấn đề từ những góc nhìn cần thiết: Developers, kiểm thử, vận hành, Product Owner, người hiểu nghiệp vụ, người quản lý dữ liệu hoặc bên ngoài nhóm khi phù hợp. Không mời quá nhiều người chỉ để bảo đảm “có đủ cấp quản lý”; nhiều người có quyền lực có thể khiến thành viên ngại nêu vấn đề.

### 25.2. Người điều phối nên làm gì?

- Đề nghị người tham gia mô tả **sự kiện và bằng chứng** trước khi diễn giải.
- Đảm bảo nhiều góc nhìn được lắng nghe, kể cả người trực tiếp xử lý sự cố.
- Chuyển câu “ai làm sai?” thành “điều kiện nào gây rủi ro?”.
- Dừng tranh luận khi thiếu dữ liệu và ghi hành động kiểm chứng.
- Không ép cả nhóm đồng thuận giả nếu có các giả thuyết cạnh tranh.
- Chọn ít hành động nhưng có tác động và người theo dõi.
- Chuyển vấn đề vượt quyền tới đúng thẩm quyền.

### 25.3. Thảo luận sâu không cần đợi họp chính thức

Nếu build đang đỏ hoặc người dùng đang gặp lỗi dữ liệu, nhóm cần phối hợp xử lý ngay theo mức ưu tiên. Retrospective giúp học hỏi định kỳ, nhưng **không phải cổng duy nhất để cải tiến**.

## 26. Các lỗi thường gặp khi điều tra và cải tiến

**1. Dừng ở “người X làm sai”.** Cách kết luận này bỏ qua điều kiện hệ thống và làm người khác sợ báo lỗi.

**2. Coi mọi sự cố có đúng một nguyên nhân gốc.** Hệ thống có thể có nhiều điều kiện góp phần và nhiều lớp bảo vệ.

**3. Mở 5 Whys nhưng không có dữ liệu.** Năm câu trả lời suy đoán vẫn không trở thành sự thật.

**4. Hỏi “vì sao?” cho tới lúc câu trả lời là “thiếu trách nhiệm”.** Cần chuyển sang cơ chế kiểm chứng và điều có thể cải tiến.

**5. Fishbone liệt kê nhiều ý tưởng rồi gọi tất cả là nguyên nhân.** Đây mới là giả thuyết, chưa có bằng chứng.

**6. Lấy biểu đồ Pareto làm bằng chứng nhân quả.** Tần suất phân loại chỉ cho biết loại nào được ghi nhiều.

**7. Ưu tiên vấn đề có tần suất cao mà bỏ rủi ro nghiêm trọng nhưng hiếm.** Mức tác động và ràng buộc an toàn rất quan trọng.

**8. Tính thời gian blocked chồng lắp rồi cộng vào Cycle Time hai lần.** Cần xác định ranh giới đo.

**9. Chỉ xem Cycle Time của item Done.** Work Item Age cho thấy item khó vẫn đang nằm trong WIP.

**10. Coi Work Item Age gần SLE là phần trăm hoàn thành.** Age không đo lượng việc còn lại.

**11. Dùng Little's Law để hứa ngày Done của một item.** Quan hệ trung bình không cho deadline cụ thể hoặc phân vị.

**12. So trước/sau khi định nghĩa Done đã thay đổi.** Kết quả không thể so sánh nguyên vẹn.

**13. Chỉ nhìn trung bình và bỏ đuôi dài.** Một vài item cực chậm có thể chứa vấn đề quan trọng.

**14. Rerun CI đến khi xanh và gọi test flaky đã giải quyết.** Độ tin cậy tín hiệu vẫn bị tổn hại.

**15. Sửa UI để tránh thao tác lặp nhưng không bảo vệ bất biến DB.** Lỗi có thể trở lại qua retry hoặc client khác.

**16. Viết thêm unit test nhưng bỏ test tích hợp tại ranh giới gây lỗi.** Kiểm thử phải phản ánh cơ chế thật.

**17. Phát hiện một lỗi dữ liệu rồi tự xóa production records.** Cần hiểu ý nghĩa dữ liệu, quyền quyết định và phương án khôi phục.

**18. Hạ DoD để số item Done tăng.** Đó là thay đổi cách báo cáo, không phải cải tiến chất lượng.

**19. Đặt quá nhiều action items sau Retrospective.** Không đủ năng lực theo dõi và học hỏi hiệu quả.

**20. Đóng action item khi tạo ticket hoặc merge PR.** Cần kiểm chứng vấn đề có giảm không.

**21. Chọn biện pháp mà không có guardrail.** Cycle Time có thể giảm bằng cách bỏ kiểm thử, nhưng lỗi tăng.

**22. Coi một mẫu nhỏ chứng minh quan hệ nhân quả.** Cần xem biến động, thay đổi loại công việc và bối cảnh.

**23. Chờ Sprint Retrospective mới xử lý sự cố đang gây hại.** Ưu tiên ứng cứu và bảo vệ người dùng ngay.

**24. Dùng biểu đồ lỗi để xếp hạng Developers.** Chỉ số hệ thống dễ méo và làm giảm sự minh bạch.

**25. Nhầm việc thiếu phê duyệt bắt buộc với “quan liêu nên bỏ qua”.** Ràng buộc pháp lý/bảo mật cần được xử lý đúng quyền; có thể cải tiến cách chuẩn bị và phối hợp.

**26. Chỉ cải tiến công đoạn dễ nhìn mà không xem toàn dòng.** Review nhanh hơn nhưng test dữ liệu vẫn nghẽn thì Increment chưa đến sớm hơn.

**27. Không ghi giả định và quyết định.** Sprint sau lặp lại cùng tranh luận và thí nghiệm.

**28. Coi không có bug trong một tuần là không còn rủi ro.** Cần xét mức độ bao phủ kiểm chứng, thời gian quan sát và cơ chế phát hiện.

**29. Tuyên bố Scrum bắt buộc 5 Whys, Pareto hay một dashboard.** Scrum không quy định các kỹ thuật ấy; dùng khi phù hợp mục đích.

**30. Đồng nhất bận rộn cá nhân với cải tiến hiệu quả.** Nhiều việc bắt đầu có thể làm WIP và hàng chờ tăng; kết quả cần xem phần giá trị Done và outcome.

## 27. Bài tập tình huống A: Phân tích hàng chờ review và kiểm thử

Một Scrum Team đang phát triển nền tảng học trực tuyến ghi nhận:

- Cycle Time của 12 user story tương đồng trước cải tiến:

~~~text
2, 3, 4, 4, 5, 6, 7, 8, 9, 11, 13, 18 (ngày làm việc)
~~~

- WIP hiện tại **9 item**, trong đó hai item chờ Review có Age **10 ngày** và **12 ngày**.
- Một PBI từng mất 9 ngày, gồm **2 ngày phát triển + 4 ngày chờ review + 2 ngày sửa/test + 1 ngày chờ môi trường**, không chồng lắp.
- Tháng trước có 30 lượt trở ngại: **12 CI flaky, 8 chờ review, 6 môi trường, 4 yêu cầu chưa rõ**.
- Nhóm đề xuất “yêu cầu tất cả Developers tăng số giờ làm việc” để xử lý chậm trễ.

### Câu hỏi

1. Hãy viết phát biểu vấn đề **không đổ lỗi**, có phạm vi và bằng chứng.
2. Cần phân biệt những **triệu chứng**, **điều kiện góp phần** và **giả thuyết nguyên nhân** nào?
3. Tính Cycle Time **trung bình, trung vị, P85 và P95 nearest-rank** của 12 item.
4. Với item 9 ngày, tỷ lệ **thời gian chờ hoặc blocked** là bao nhiêu? Vì sao không được gọi trực tiếp đó là tỷ lệ “năng lực nhân sự lãng phí”?
5. Những trường hợp nào không được nhìn thấy nếu chỉ đo Cycle Time của item Done?
6. Từ bảng Pareto, CI flaky và chờ review chiếm bao nhiêu phần trăm lượt? Có thể khẳng định đây là hai nguyên nhân có tác động lớn nhất không?
7. Viết ít nhất **ba câu hỏi 5 Whys** và một cách kiểm chứng từng câu.
8. Đề xuất **một thử nghiệm hai Sprint** có metric chính, guardrail và điểm xem lại.
9. Vì sao phương án “tăng giờ làm việc” chưa giải quyết đủ vấn đề?
10. Nếu kết quả sau cải tiến tốt hơn nhưng loại PBI đã thay đổi, nhóm nên nói kết luận như thế nào?

### Gợi ý lời giải

**Câu 1:** 

> “Trong giai đoạn quan sát, một số PBI của luồng đăng ký có Cycle Time dài, gồm các khoảng chờ review và môi trường. Hiện có hai item còn dở 10–12 ngày ở Review, trong khi nhiều trở ngại CI và review được ghi lặp lại. Nhóm cần xác minh chính sách WIP, review, dữ liệu test và phụ thuộc đang làm chậm khả năng đạt DoD.”

**Câu 2:** Triệu chứng: item Done muộn, Age cao, test flaky. Điều kiện có thể góp phần: WIP 9, quyền review tập trung, môi trường không ổn định. Giả thuyết: chính sách kéo nhiều việc và thiếu reviewer dự phòng làm hàng chờ tăng. Các điều kiện cần **kiểm chứng**, không kết luận chỉ từ mô tả.

**Câu 3:** Tổng 90 ngày-item; trung bình **7,5 ngày**, trung vị **6,5 ngày**, P85 nearest-rank vị trí 11 là **13 ngày**, P95 vị trí 12 là **18 ngày**. Kết quả dựa trên mẫu nhỏ và phương pháp phân vị đã nêu.

**Câu 4:** Chờ review 4 ngày + chờ môi trường 1 ngày = **5/9 ≈ 55,6%** Cycle Time của item đó. Thời gian chờ của item **khác** thời gian con người nhàn rỗi; Developers có thể đang làm việc khác nhưng tạo thêm WIP. Không được quy đổi thẳng thành chi phí nhân sự.

**Câu 5:** Những item còn ở WIP, có thể đang già hoặc Blocked, không xuất hiện trong mẫu Cycle Time của item Done. Cần xem Work Item Age và trạng thái thật.

**Câu 6:** \(12+8=20\) trong tổng 30, tức **66,7% lượt**. Không khẳng định tác động lớn nhất vì chưa biết số giờ chặn, mức nghiêm trọng, ảnh hưởng người dùng hoặc thiên lệch ghi nhận.

**Câu 7:** Ví dụ:

- Vì sao PR chờ? → Kiểm tra timestamp tạo và review.
- Vì sao review không bắt đầu sớm? → Xem lượng PR, quyền reviewer và lịch gián đoạn.
- Vì sao nhiều PR tới cùng lúc? → Kiểm tra WIP, cách chia PBI và mốc đẩy PR.
- Vì sao CI phải rerun? → So test data, thời gian, thứ tự chạy và log môi trường.

Không dừng ở “Developer thiếu cố gắng”.

**Câu 8:** Thử giới hạn WIP, chia PR nhỏ và có reviewer dự phòng khi cần. Đo thời gian chờ review, Cycle Time và Age; theo dõi **lỗi hồi quy/DoD** làm guardrail; xem lại sau hai Sprint với định nghĩa đo nhất quán.

**Câu 9:** Nếu phần lớn thời gian nằm ở hàng chờ, kéo dài giờ làm có thể tăng mã mới chờ kiểm tra chứ không tăng năng lực review/test. Ngoài ra, nhịp quá tải kéo dài có thể tăng lỗi và giảm tính bền vững.

**Câu 10:** Nêu số liệu trước/sau là **quan sát có giới hạn**, loại PBI thay đổi khiến khó quy kết nhân quả. Cần phân nhóm tương đồng, xem WIP còn dở và chất lượng, rồi tiếp tục theo dõi hoặc thử cải tiến ở phạm vi rõ hơn.

## 28. Bài tập tình huống B: Lỗi đăng ký trùng đã “sửa” ba lần

Một nhóm ba lần ghi nhận lỗi cùng tài khoản và khóa có hai đăng ký Active. Lần đầu sửa UI vô hiệu nút, lần hai thêm kiểm tra tồn tại trước khi lưu, lần ba lỗi lại xuất hiện khi client retry sau timeout.

### Câu hỏi

1. Vì sao sửa giao diện chưa đủ chứng minh nguyên nhân đã được loại bỏ?
2. Kiểm tra tồn tại rồi mới ghi có rủi ro gì khi có hai request đồng thời?
3. Nêu ba loại bằng chứng cần thu để xác minh race condition và retry.
4. Viết một kịch bản kiểm thử hành vi có thể tái hiện lỗi.
5. Chọn ít nhất một biện pháp ở tầng **dữ liệu**, **hợp đồng/API** và **kiểm thử/CI**.
6. Nếu dữ liệu cũ đã có bản ghi trùng, việc tạo unique constraint ngay có rủi ro nào?
7. Phân biệt containment, corrective và preventive action cho tình huống.
8. Nếu test mới pass nhưng không có lỗi trong một tuần, có thể khẳng định lỗi không bao giờ tái diễn không?
9. Làm sao tổ chức postmortem không đổ lỗi mà vẫn có trách nhiệm rõ?
10. Metric/guardrail nào giúp theo dõi mức rủi ro sau khắc phục?

### Gợi ý lời giải

**Câu 1:** Client khác, request retry hoặc lỗi mạng vẫn có thể gửi lặp. UI là một lớp trải nghiệm, không bảo vệ hoàn toàn tính nhất quán dữ liệu.

**Câu 2:** Hai request có thể cùng đọc trạng thái “chưa tồn tại”, rồi cùng tạo bản ghi. Nếu không có cơ chế nguyên tử/ràng buộc phù hợp, kiểm tra đơn thuần không ngăn race condition.

**Câu 3:** Revision mã và cấu hình DB, timeline/request IDs an toàn, log thao tác ghi, thử nghiệm concurrent với dữ liệu giả, dấu hiệu retry/timeout từ client và kết quả dữ liệu sau giao dịch.

**Câu 4:** Có thể dùng tình huống Gherkin ở mục 15: hai request gần đồng thời cùng khóa, cuối cùng không có hai bản ghi Active trùng và phản hồi đúng hợp đồng.

**Câu 5:** Tầng dữ liệu: ràng buộc/giao dịch phù hợp bất biến. API: xác định idempotency/retry và trạng thái khi kết quả chưa chắc chắn. CI: chạy integration/concurrency test đủ đại diện cho đường ghi.

**Câu 6:** Migration có thể thất bại hoặc phá dữ liệu lịch sử hợp lệ; cần xác minh nghiệp vụ, làm sạch có kiểm soát, backup/khôi phục theo chính sách và người có thẩm quyền.

**Câu 7:** Containment là giảm tác động ngay; corrective là xử lý đường tạo dữ liệu trùng; preventive là test hồi quy, review và giám sát để loại lỗi tương tự hoặc phát hiện sớm.

**Câu 8:** Không. Test pass chứng minh các điều kiện đã kiểm tra đạt; một tuần không có báo cáo còn phụ thuộc lưu lượng và cơ chế quan sát. Theo dõi lâu hơn theo rủi ro.

**Câu 9:** Tập trung timeline và điều kiện kỹ thuật/tổ chức, hỏi thông tin người tham gia thấy khi quyết định, gán người theo dõi hành động và điểm kiểm chứng; xử lý hành vi cố ý/vi phạm nghiêm trọng bằng quy trình phù hợp riêng.

**Câu 10:** Tỷ lệ/tần suất dữ liệu trùng được xác minh, lỗi đăng ký, lỗi retry/timeout, kết quả concurrency test, số incident và thời gian phát hiện/khôi phục. Không lấy “số bug được báo giảm” làm bằng chứng duy nhất.

## 29. Mẫu báo cáo phân tích nguyên nhân gọn trong một trang

Mẫu dưới đây có thể dùng cho Retrospective hoặc postmortem. **Đây không phải artifact Scrum bắt buộc.**

~~~text
Tên vấn đề:
  ...

Phạm vi và khoảng thời gian:
  ...

Ảnh hưởng tới người dùng, chất lượng, Sprint Goal hoặc dòng công việc:
  ...

Điều đã xảy ra (timeline + nguồn bằng chứng):
  ...

Điều quan sát được (facts):
  ...

Giả thuyết nguyên nhân và điều kiện góp phần:
  - H1: ...
    Bằng chứng ủng hộ: ...
    Bằng chứng phản biện / còn thiếu: ...
  - H2: ...
    Bằng chứng ủng hộ: ...
    Bằng chứng phản biện / còn thiếu: ...

Nguyên nhân/cơ chế đã xác minh và giới hạn kết luận:
  ...

Ứng cứu/giảm tác động đã thực hiện:
  ...

Hành động khắc phục hoặc phòng ngừa:
  - Hành động: ...
  - Người phối hợp / quyền quyết định: ...
  - Mốc xem lại: ...
  - Bằng chứng thành công: ...
  - Guardrail chất lượng/an toàn: ...

Điều chưa được giải quyết:
  ...

Tác động tới Product Backlog / Sprint Backlog / DoD:
  ...

Quyết định tiếp theo và điều kiện xem lại:
  ...
~~~

### 29.1. Ví dụ điền ngắn

> **Vấn đề:** PR của luồng đăng ký thường chờ review ba ngày.  
> **Bằng chứng:** Timestamp PR trong ba Sprint; hàng chờ Review tăng khi có incident.  
> **Giả thuyết:** PR đến dồn cuối Sprint và chỉ có một reviewer có quyền ở mô-đun.  
> **Chưa chắc:** Kích thước PR và chất lượng acceptance criteria có thể là yếu tố khác.  
> **Thử nghiệm:** Trong hai Sprint, giới hạn WIP và dùng reviewer dự phòng có hướng dẫn.  
> **Bằng chứng cần quan sát:** Phân bố thời gian chờ Review, Cycle Time, Work Item Age, lỗi review bỏ sót.  
> **Quyết định:** Giữ hoặc điều chỉnh chính sách theo kết quả và guardrail.

### 29.2. Báo cáo tốt phải phân biệt “đã làm” và “đã hiệu quả”

Hai trường quan trọng khác nhau:

- **Hành động đã thực hiện:** “Đã thêm contract test vào pipeline.”
- **Hiệu quả được quan sát:** “Trong các đợt kiểm tra có thể so sánh, test phát hiện sai hợp đồng trước merge; thời gian điều tra giảm theo dữ liệu và không làm xấu chất lượng.”

Nếu chưa có dữ liệu sau can thiệp, hãy báo **“đã triển khai, đang theo dõi”**, không tuyên bố vấn đề đã được loại bỏ vĩnh viễn.

## 30. Checklist phân tích nguyên nhân và cải tiến liên tục

### Trước khi điều tra

1. **Vấn đề:** Đã mô tả điều quan sát và tác động, không vội kết luận nguyên nhân?
2. **Mức nghiêm trọng:** Có nguy cơ người dùng/dữ liệu cần ứng cứu ngay?
3. **Phạm vi:** Luồng, loại PBI, dịch vụ và khoảng thời gian đã rõ?
4. **Bằng chứng:** Có logs, timeline, test, dữ liệu workflow và người biết bối cảnh?
5. **Quyền dữ liệu:** Việc thu thập/phân tích có đúng phạm vi được phép?
6. **Lặp lại:** Có chứng cứ vấn đề tái diễn hoặc là một near miss nghiêm trọng?

### Khi phân tích

7. **Phân loại:** Triệu chứng, tác động, điều kiện góp phần và giả thuyết được tách rõ?
8. **Tư duy hệ thống:** Có xem chính sách, dữ liệu, công cụ, kiến trúc và phụ thuộc?
9. **Không đổ lỗi:** Câu hỏi tập trung vào điều kiện và cơ chế, không quy kết tính cách?
10. **Timeline:** Có kiểm tra thứ tự sự kiện và nguồn dữ liệu mâu thuẫn?
11. **Flow boundary:** Start, Done, ngày làm việc/ngày lịch và blocked time có thống nhất?
12. **WIP:** Có xem những item đang dở, không chỉ thống kê item Done?
13. **Metric:** SLE, Cycle Time, Throughput được diễn giải đúng nghĩa?
14. **Nhiều giả thuyết:** Có tránh ép một chuỗi nguyên nhân duy nhất?
15. **Kiểm chứng:** Mỗi giả thuyết quan trọng có dấu hiệu xác nhận hoặc bác bỏ?
16. **Mức tác động:** Có xét severity và thời gian chặn, không chỉ số lần?
17. **Ranh giới nhân quả:** Có phân biệt tương quan, diễn giải và kết luận có kiểm chứng?

### Khi chọn hành động

18. **Nguyên nhân có thể tác động:** Biện pháp nhắm đúng cơ chế hay chỉ nhắc “cẩn thận hơn”?
19. **Ứng cứu và phòng ngừa:** Có phân biệt giảm tác động với sửa điều kiện lặp lại?
20. **Ưu tiên:** Đã xét rủi ro an toàn, giá trị người dùng và chi phí cơ hội?
21. **Thử nghiệm nhỏ:** Có phạm vi, thời gian và điều kiện dừng?
22. **Guardrail:** Có bảo vệ DoD, chất lượng, quyền dữ liệu và nhịp bền vững?
23. **Quyền quyết định:** Người liên quan và người có thẩm quyền đã rõ?
24. **Product Backlog:** Công việc cải tiến có được diễn đạt bằng tác động và ưu tiên phù hợp?

### Khi đánh giá kết quả

25. **Theo dõi:** Có người chủ động nhìn số liệu sau thay đổi?
26. **So sánh:** Loại công việc và định nghĩa đo trước/sau có tương đồng?
27. **Mẫu và biến động:** Có tránh kết luận lớn từ vài item hoặc một tuần?
28. **Công việc còn dở:** Work Item Age và Blocked Time có được xem cùng Cycle Time?
29. **Chất lượng:** Tốc độ có cải thiện mà không tạo lỗi nghiêm trọng hơn?
30. **Đã học gì:** Có ghi điều kiện khiến phải giữ, chỉnh hoặc bỏ biện pháp?
31. **Chia sẻ:** Bài học cần thiết có tới người tham gia hoặc nhóm phụ thuộc?
32. **Tính liên tục:** Có lịch xem lại để tránh vấn đề âm thầm tái xuất?

## 31. Tổng kết: phân tích nguyên nhân để thay đổi hệ thống, không chỉ sửa triệu chứng

Chậm trễ, lỗi và trở ngại lặp lại là **tín hiệu để học về hệ thống làm việc**. Một nhóm Agile không cần một báo cáo dài cho mọi sự cố, nhưng cần khả năng biến các vấn đề quan trọng thành **bằng chứng, giả thuyết, can thiệp và phản hồi mới**.

| Phản ứng theo triệu chứng | Cải tiến theo nguyên nhân có bằng chứng |
| --- | --- |
| “Mọi người phải làm nhanh hơn.” | Xem hàng chờ, WIP, phụ thuộc, quyền review và luồng tới Done |
| “QA cần kiểm thử kỹ hơn.” | Kiểm tra cách làm rõ yêu cầu, test data, CI, tích hợp và DoD |
| “Lỗi do người dùng bấm nhiều lần.” | Kiểm tra retry, idempotency, giao dịch và ràng buộc dữ liệu |
| “Đã sửa UI nên xong.” | Xác minh cơ chế gây lỗi ở API/DB và kiểm thử ngăn lặp |
| “Chạy lại test tới khi xanh.” | Điều tra flaky test, môi trường và độ tin cậy của phản hồi |
| “P85 của item Done đã giảm, vậy ổn.” | Xem cả Work Item Age của item còn dở và guardrail chất lượng |
| “Retrospective ghi nhiều action là hiệu quả.” | Chọn biện pháp có người làm, metric và điểm xem lại |
| “Không có incident mới nên rủi ro hết.” | Theo dõi mức bao phủ kiểm chứng, tải thực tế và tín hiệu vận hành |
| “Chỉ có một nguyên nhân gốc.” | Cân nhắc nhiều điều kiện góp phần và các lớp bảo vệ |
| “Đo để xếp hạng cá nhân.” | Đo để cải thiện dòng giá trị và quyết định cấp hệ thống |

**Ghi nhớ:** Quy trình hữu ích là **Quan sát vấn đề → Bảo vệ người dùng → Thu thập bằng chứng → Phân tích nhiều nguyên nhân có thể có → Kiểm chứng giả thuyết → Thử cải tiến → Theo dõi tác động và guardrails → Học tiếp**. Scrum cung cấp nhịp kiểm tra, thích ứng và trách nhiệm; Kanban giúp thấy WIP, tuổi công việc và hàng chờ; XP tạo vòng phản hồi kỹ thuật qua kiểm thử, CI và refactoring; Lean giúp loại lãng phí và tập trung vào giá trị toàn dòng. Khi nhóm phân tích nguyên nhân có căn cứ và không đổ lỗi, việc cải tiến liên tục sẽ chuyển từ khẩu hiệu trong Retrospective thành **khả năng giao phần mềm tăng dần an toàn, đáng tin và thích ứng tốt hơn qua mỗi vòng phản hồi**.

