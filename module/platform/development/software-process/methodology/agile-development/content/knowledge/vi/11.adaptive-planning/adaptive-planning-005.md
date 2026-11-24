# Lập kế hoạch theo năng lực thực tế và dữ liệu đã có

Một nhóm phát triển phần mềm có thể lập kế hoạch rất chi tiết mà vẫn thường xuyên trễ hạn. Lý do không nhất thiết vì thành viên làm việc thiếu cố gắng: nhóm có thể đã tính **mọi ngày làm việc là ngày dành cho tính năng mới**, đánh giá thấp công việc hỗ trợ và sửa lỗi, dùng một ước lượng duy nhất cho công việc còn nhiều bất định hoặc xem tốc độ của một Sprint thuận lợi là mức có thể duy trì mãi mãi.

Trong **Agile**, lập kế hoạch là hoạt động liên tục nhằm chọn bước tiếp theo có giá trị, phối hợp người liên quan và phản ứng trước điều vừa học được. Một kế hoạch tốt cần dựa trên **mục tiêu rõ ràng, năng lực thực sự có thể sử dụng, dữ liệu đã quan sát, rủi ro và những giả định còn mở**. Kế hoạch có thể điều chỉnh khi bằng chứng thay đổi, nhưng các điều kiện về chất lượng, an toàn và những cam kết bắt buộc vẫn phải được tôn trọng.

Bài học thuộc chương **Kế hoạch thích ứng** của module **AGILE_DEVELOPMENT**, nơi người học thực hành tư duy phản hồi sớm, giao giá trị tăng dần và cải tiến liên tục. Cách lập kế hoạch này gắn trực tiếp với user story, Product Backlog, Scrum, Kanban, XP và các chỉ số dòng công việc. Trọng tâm không phải tìm một công thức dự báo đúng tuyệt đối; đó là **đưa ra quyết định hữu ích với mức chắc chắn phù hợp**.

## 1. Kế hoạch thích ứng cần trả lời những câu hỏi nào?

Một kế hoạch hữu ích cần làm rõ:

1. **Vì sao làm?** Kết quả nào của người dùng hoặc nghiệp vụ đang được ưu tiên?
2. **Làm điều gì tiếp theo?** Những hạng mục nào trong backlog mang lại giá trị hoặc giảm rủi ro lớn nhất?
3. **Ai có thể làm và có bao nhiêu năng lực?** Thành viên có mặt, kỹ năng, công việc hỗ trợ, phụ thuộc và thời gian làm việc thực tế ra sao?
4. **Bằng chứng nào hỗ trợ dự báo?** Nhóm đã từng hoàn tất bao nhiêu việc tương đương, mất bao lâu và thường vướng ở đâu?
5. **Điều gì chưa biết?** Hạng mục nào còn lớn, công nghệ nào chưa được kiểm chứng và cam kết nào nằm ngoài quyền quyết định của nhóm?
6. **Khi nào xem lại?** Những sự kiện, số đo hoặc phản hồi nào sẽ khiến nhóm điều chỉnh thứ tự, phạm vi hoặc thời điểm?

Những câu hỏi này giúp tránh hai cực đoan: kế hoạch cứng nhắc không đổi dù thực tế khác đi, và cách làm thiếu định hướng chỉ chọn việc theo yêu cầu mới nhất.

### Kế hoạch có nhiều mức độ chi tiết

| Mức kế hoạch | Mục đích | Thông tin cần đáng tin | Khả năng điều chỉnh |
| --- | --- | --- | --- |
| **Định hướng sản phẩm** | Chọn kết quả dài hạn, ưu tiên lớn và các ràng buộc | Product Goal, nhu cầu, ngân sách và thời điểm bắt buộc | Xem lại khi chiến lược hoặc bằng chứng thị trường thay đổi |
| **Roadmap / kế hoạch phát hành** | Phối hợp các mốc giá trị, phụ thuộc và người liên quan | Phạm vi tối thiểu, năng lực gần đây, rủi ro và mức bất định | Điều chỉnh trình tự hoặc phương án để giữ kết quả quan trọng |
| **Kế hoạch Sprint** nếu dùng Scrum | Xác định Sprint Goal, những Product Backlog Item được chọn và kế hoạch thực hiện | Công việc đủ hiểu, khả năng thực hiện trong Sprint, Definition of Done | Developers thích ứng kế hoạch khi học thêm, không làm nguy hại Sprint Goal |
| **Kế hoạch theo dòng công việc** nếu dùng Kanban | Chọn việc khi có khả năng xử lý, giữ WIP trong giới hạn | Chính sách kéo việc, tuổi hạng mục, throughput và điểm tắc | Điều chỉnh thường xuyên dựa trên dòng chảy |
| **Phối hợp hằng ngày** | Phát hiện trở ngại, giúp nhau hoàn tất và điều chỉnh công việc | Trạng thái thật, phụ thuộc đang chờ và rủi ro mới | Thường xuyên; không phải lập lại cam kết ngày hoàn tất cho từng người |

**Mức càng xa, độ chi tiết thường càng ít**, bởi nhiều nhu cầu và giải pháp vẫn là giả thuyết. Một mốc thời gian bắt buộc có thể không đổi, nhưng nhóm vẫn cần lựa chọn phạm vi khả thi và công khai hệ quả.

## 2. Phân biệt năng lực, khối lượng công việc và tốc độ hoàn tất

Các khái niệm dưới đây liên quan nhưng không thể thay thế cho nhau:

| Thuật ngữ | Định nghĩa thực dụng | Ví dụ | Không nên hiểu thành |
| --- | --- | --- | --- |
| **Năng lực khả dụng** (*available capacity*) | Phần thời gian và khả năng thực sự có thể dành cho công việc trong một giai đoạn | Số ngày công còn lại sau nghỉ phép, hỗ trợ và các nghĩa vụ khác | Tổng số ngày trên lịch của cả nhóm |
| **Nhu cầu công việc** (*demand*) | Những hạng mục cần xử lý, kèm độ lớn, độ khẩn và yêu cầu kỹ năng | Story mới, lỗi sản phẩm, hỗ trợ, bảo mật, bảo trì | Chỉ các tính năng mà Product Owner muốn thêm |
| **Velocity** | Tổng đơn vị ước lượng tương đối của công việc hoàn thành trong một Sprint theo quy ước của cùng nhóm | Nhóm hoàn tất 18 điểm trong một Sprint | Số giờ làm việc hoặc năng suất dùng so sánh các nhóm |
| **Throughput** | Số hạng mục công việc hoàn tất trong một đơn vị thời gian theo định nghĩa nhất quán | 5 hạng mục đạt điều kiện hoàn tất trong một tuần | Giá trị kinh doanh hoặc số tính năng lớn đã tạo ra |
| **Cycle time** | Thời gian một hạng mục đi từ lúc bắt đầu xử lý tới khi hoàn tất theo chính sách đo | Một story mất 6 ngày từ lúc vào trạng thái đang làm tới Done | Số giờ một người trực tiếp gõ mã |
| **Lead time** | Thời gian từ một mốc yêu cầu/đặt hàng được xác định tới mốc hoàn tất/giao giá trị đã thống nhất | 14 ngày từ khi yêu cầu được chấp nhận tới khi bàn giao | Một đại lượng có chung điểm đầu ở mọi nhóm |
| **Work item age** | Thời gian một hạng mục đã bắt đầu nhưng chưa hoàn tất tồn tại tới thời điểm hiện tại | Story đang làm được 9 ngày và vẫn chờ kiểm thử | Cycle time của hạng mục đã hoàn thành |
| **WIP** (*work in progress*) | Số hạng mục đã bắt đầu nhưng chưa hoàn tất | Có 7 việc trong các trạng thái đang làm/đang kiểm tra | Mức độ bận rộn càng cao càng tốt |

Ví dụ, bốn người có thể cùng làm đủ giờ nhưng **throughput thấp** nếu nhiều việc chờ phê duyệt và tích hợp. Ngược lại, tuần có nhiều việc nhỏ hoàn tất chưa chắc giá trị lớn hơn tuần xử lý được một sự cố dữ liệu nghiêm trọng.

Một kế hoạch cần kết hợp **năng lực đầu vào** với **bằng chứng về công việc thực sự hoàn tất**, đồng thời hiểu kết quả sử dụng chứ không chỉ đếm hoạt động.

## 3. Dữ liệu nào nên lấy trước khi lập kế hoạch?

Nhóm không cần có hệ thống phân tích phức tạp để bắt đầu. Cần nhất là **dữ liệu đủ gần bối cảnh hiện tại, có định nghĩa nhất quán và được dùng với mức tin cậy phù hợp**.

### 3.1. Bốn nhóm dữ liệu nền

| Nhóm dữ liệu | Cần thu thập | Giá trị khi lập kế hoạch |
| --- | --- | --- |
| **Năng lực** | Thành viên và kỹ năng sẵn có, nghỉ phép, công việc vận hành, hỗ trợ, đào tạo, nghĩa vụ phối hợp | Biết nhóm có thể nhận bao nhiêu việc mà vẫn giữ chất lượng |
| **Lịch sử hoàn tất** | Số PBI hoàn thành theo Sprint; throughput theo tuần; cycle time và tuổi công việc | Có cơ sở dự báo hơn là đoán từ cảm giác |
| **Chất lượng và gián đoạn** | Lỗi khẩn, làm lại, sự cố, thời gian chờ review, kiểm thử, triển khai hoặc phía đối tác | Nhìn thấy phần công sức thường bị bỏ quên |
| **Nhu cầu và rủi ro** | Product Goal, backlog có thứ tự, kích thước hạng mục, phụ thuộc, hạn bắt buộc, giả định chưa xác minh | Biết việc nào cần làm trước và mức bất định của dự báo |

Không được tự suy rằng một thành viên hiện diện tám giờ nghĩa là có tám giờ viết tính năng mới. Trao đổi với người dùng, review, kiểm thử, hỗ trợ đồng nghiệp và xử lý sự cố đều có giá trị nhưng sử dụng năng lực thật.

### 3.2. Kiểm tra chất lượng dữ liệu trước khi dùng

Hãy đặt câu hỏi:

- **Điểm đầu và điểm kết thúc có nhất quán không?** Nếu Sprint trước tính Done khi hoàn thành code còn Sprint này yêu cầu tích hợp và kiểm thử, hai số throughput chưa trực tiếp so sánh được.
- **Các hạng mục có tương đồng không?** Việc sửa nhãn nút và thay luồng phân quyền có độ lớn/rủi ro khác nhau; đếm như nhau cần thận trọng.
- **Bối cảnh có đổi không?** Đổi đội hình, công nghệ, yêu cầu chất lượng, quy trình review hoặc loại sản phẩm có thể làm dữ liệu cũ ít đại diện.
- **Có bỏ sót công việc ngắt quãng không?** Nếu support không được ghi nhận, dự báo chỉ dựa vào story mới sẽ thường quá lạc quan.
- **Dữ liệu có bị thao túng bởi chỉ tiêu không?** Khi thành công được đo bằng số story đóng, nhóm có thể chia việc giả tạo hoặc đóng trước kiểm thử.
- **Lượng quan sát có đủ không?** Một Sprint hoặc một tuần thuận lợi không thể đại diện cho toàn bộ khả năng trong tương lai.

Nếu câu trả lời chưa rõ, **ghi đó là giới hạn của dự báo** và cải thiện cách thu số liệu. Không biến dữ liệu thô thành “bằng chứng chắc chắn” chỉ vì được trình bày trong bảng.

## 4. Tính năng lực thực tế cho một giai đoạn

Hãy tưởng tượng một nhóm có **4 người** và Sprint dài **10 ngày làm việc**. Tổng ngày công lý thuyết là:

\[
4\ \text{người} \times 10\ \text{ngày làm việc} = 40\ \text{ngày-người}.
\]

Nhưng nhóm biết trước trong Sprint này có nghỉ phép, trực hỗ trợ và các hoạt động phối hợp. Bảng sau là **số liệu minh họa, không phải tỷ lệ chuẩn cho các nhóm Agile**.

| Khoản mục | Ngày-người | Giải thích |
| --- | ---: | --- |
| Tổng số ngày công theo lịch | 40 | 4 người × 10 ngày |
| Nghỉ phép và vắng mặt đã biết | −5 | Chỉ trừ phần thực sự nằm trong Sprint |
| Trực hỗ trợ, vận hành và xử lý việc cố định | −7 | Phần thời gian đã biết không thể dùng cho kế hoạch tính năng |
| Hoạt động phối hợp, họp và đào tạo dự kiến | −6 | Không tính trùng với các khoản đã trừ |
| **Năng lực có thể phân bổ ban đầu** | **22** | 40 − 5 − 7 − 6 |

Con số **22 ngày-người** là ước lượng thời gian khả dụng cho công việc đã chọn, **không có nghĩa nhóm sẽ hoàn thành đúng 22 story point hay 22 PBI**. Công việc xây dựng, review, kiểm thử và sửa lỗi của các hạng mục đã chọn vẫn phải nằm trong phần năng lực ấy.

Nếu lịch sử cho thấy vẫn thường có sự cố chưa báo trước, nhóm nên tính tới **khả năng biến động**: ví dụ minh họa, dự kiến giữ một phần năng lực chưa phân bổ ngay cho những việc phát sinh. Không có phần trăm “buffer” cố định áp dụng cho mọi đội; mức dự phòng phụ thuộc dữ liệu và hậu quả trễ hạn.

### 4.1. Những lỗi thường xảy ra khi tính capacity

1. **Đếm trùng hoặc bỏ quên công việc:** Họp review đã tính trong hoạt động phối hợp nhưng lại bị trừ lần nữa trong support; hoặc công việc trực hệ thống không được tính ở đâu.
2. **Cho rằng mọi người thay thế nhau hoàn toàn:** Ba người còn rảnh không tự động thay được chuyên gia duy nhất đang nghỉ nếu công việc yêu cầu quyền hoặc kỹ năng riêng.
3. **Bỏ qua việc chờ phụ thuộc:** Nhóm có thể có ngày công nhưng không thể tích hợp khi API đối tác chưa sẵn sàng.
4. **Xếp đầy toàn bộ thời gian:** Việc đã bắt đầu có thể gặp lỗi, cần học công nghệ hoặc kiểm thử phát hiện vấn đề. Kế hoạch kín không còn chỗ phản ứng.
5. **Dùng capacity để ép tăng velocity:** Capacity là thông tin về khả năng hiện diện; velocity là kết quả lịch sử của công việc theo cách đo của nhóm. Chúng không chuyển đổi tuyến tính.

Capacity hữu ích nhất như **kiểm tra tính khả thi của kế hoạch gần**. Lịch sử hoàn tất và rủi ro của từng hạng mục vẫn là cơ sở để xem số việc dự định có hợp lý.

## 5. Dùng velocity khi nhóm làm việc theo Sprint

Một nhóm Scrum có thể ước lượng Product Backlog Item bằng **story point** và nhìn vào lượng điểm hoàn tất mỗi Sprint. Story point thể hiện quy ước ước lượng tương đối của **chính nhóm đó**, thường phản ánh độ lớn, phức tạp hoặc bất định; nó không phải đơn vị thời gian phổ quát và cũng không phải thành phần bắt buộc của Scrum.

Giả sử bốn Sprint gần nhất, cùng độ dài, cùng quy tắc Done và bối cảnh tương đối ổn định, có kết quả **minh họa**:

| Sprint | Điểm đã hoàn tất và đạt DoD |
| --- | ---: |
| 1 | 17 |
| 2 | 22 |
| 3 | 19 |
| 4 | 20 |
| **Trung bình** | **19,5** |

Trong ví dụ:

\[
\text{Velocity trung bình} = (17+22+19+20)/4 = 19{,}5.
\]

**19,5 điểm không phải cam kết Sprint sau sẽ giao 19,5 điểm.** Nó chỉ là thông tin tham khảo để lập kế hoạch, với mức dao động lịch sử từ 17 đến 22 điểm. Nếu Sprint tới có nhiều người vắng, công việc nghiên cứu mới hoặc nợ kỹ thuật lớn, kỳ vọng cần được giảm hoặc công khai rủi ro.

### Cách dùng velocity có trách nhiệm

- Ưu tiên **Sprint Goal** và những Product Backlog Item thực sự cần để đạt mục tiêu, thay vì “lấp đủ điểm”.
- Developers xem xét năng lực Sprint tới, công việc đang dở, độ hiểu biết về PBI và kết quả Sprint trước khi chọn việc.
- Chỉ tính công việc **đạt Definition of Done** theo thỏa thuận; không cộng điểm cho phần mới hoàn thành một tầng kỹ thuật nếu chưa có Increment hoàn chỉnh.
- Dùng biến động qua nhiều Sprint để trao đổi về khả năng thực hiện; không dùng một mức cao nhất làm chỉ tiêu phải vượt.
- Nếu đội hình, cách ước lượng hoặc tiêu chuẩn hoàn thành đổi đáng kể, cần **thiết lập lại cách diễn giải dữ liệu**, tránh ghép hai thước đo không tương thích.
- Không dùng velocity hoặc story point để xếp hạng cá nhân hay so sánh năng suất các đội.

### Không chuyển story point thành giờ một cách máy móc

Nếu nhóm đã làm được 20 điểm với 40 ngày-người theo lịch, không thể kết luận “một điểm = hai ngày-người” rồi tính mọi hạng mục tương lai bằng công thức ấy. Điểm là đơn vị tương đối, thành phần kỹ năng và rủi ro khác nhau; ngày theo lịch cũng không bằng năng lực thực hiện. Việc ép quy đổi có thể làm **cả hai thước đo mất ý nghĩa**.

## 6. Dự báo bằng throughput và cycle time trong dòng công việc

Một nhóm khác không dùng story point mà theo dõi số hạng mục hoàn tất mỗi tuần. Trong sáu tuần gần đây, số liệu **minh họa** như sau:

| Tuần | Hạng mục hoàn tất theo cùng định nghĩa Done |
| --- | ---: |
| 1 | 4 |
| 2 | 6 |
| 3 | 5 |
| 4 | 3 |
| 5 | 7 |
| 6 | 5 |
| **Tổng** | **30** |
| **Trung bình/tuần** | **5** |

Nếu backlog có **12 hạng mục tương đối tương đồng** đã đủ rõ và chưa bắt đầu, phép chia đơn giản:

\[
12/5 = 2{,}4\ \text{tuần}
\]

chỉ là **mốc tham khảo để kiểm tra quy mô công việc**, không phải lời hứa sẽ hoàn tất trong 2,4 tuần. Dữ liệu vừa cho thấy throughput dao động từ **3 đến 7 hạng mục/tuần**; việc mới có thể lớn hơn, phát sinh lỗi, phụ thuộc và hàng đợi. Nếu hạng mục còn quá lớn hoặc lẫn nhiều loại việc, phải làm rõ/chia nhỏ trước khi sử dụng đếm số hạng mục như dữ liệu dự báo.

### 6.1. Vì sao chỉ nhìn giá trị trung bình thường thiếu?

Hai nhóm có trung bình 5 hạng mục/tuần nhưng biến động rất khác nhau:

- Nhóm A hoàn tất gần như 5 việc mỗi tuần.
- Nhóm B có tuần hoàn tất 1 việc, tuần khác 9 việc.

Cùng trung bình nhưng khả năng hứa một mốc ngắn hạn và rủi ro với các bên liên quan khác nhau. Nên xem **phân bố lịch sử, tuần bất thường, loại việc và điểm nghẽn**, không chỉ một con số trung bình.

### 6.2. Cycle time giúp trả lời câu hỏi khác

Throughput phản ánh tốc độ hoàn tất nhiều hạng mục; **cycle time** phản ánh một hạng mục đã bắt đầu phải chờ bao lâu tới Done. Ví dụ:

| Hạng mục hoàn tất | Cycle time minh họa |
| --- | ---: |
| Sửa trạng thái xác nhận | 3 ngày |
| Xem lịch đăng ký | 5 ngày |
| Xử lý yêu cầu hủy | 6 ngày |
| Thay đổi API tích hợp | 12 ngày |
| Sửa lỗi dữ liệu sau phát hành | 4 ngày |

Nhìn riêng năm số đo này, nhóm có thể nói “việc tích hợp API mất lâu hơn nhiều việc khác trong mẫu”. Chưa đủ căn cứ kết luận rằng mọi API tương lai đều mất 12 ngày hoặc rằng đội có xác suất hoàn tất 85% trong một ngưỡng nào đó. Muốn tạo **Service Level Expectation (SLE)** từ cycle time, cần số quan sát có định nghĩa và bối cảnh phù hợp, rồi công khai ngưỡng và tỷ lệ lịch sử đã quan sát thay vì suy đoán.

### 6.3. Work item age cảnh báo trước khi việc hoàn thành

Cycle time của hạng mục chỉ được biết khi hạng mục đã Done. Trong lúc đang làm, **work item age** cho biết một việc đã tồn tại bao lâu từ lúc bắt đầu. Nếu phần lớn công việc tương tự trước đây hoàn tất trong khoảng 4–7 ngày, còn một story hiện đã 11 ngày vẫn chờ review, nhóm có lý do kiểm tra ngay điểm nghẽn hoặc phụ thuộc.

Đừng chỉ tăng người hoặc mở thêm việc mới; trước hết hỏi **vì sao hạng mục đang chờ**, liệu có thể hỗ trợ hoàn tất, giảm WIP hoặc điều chỉnh chính sách.

## 7. Lập dự báo có khoảng bất định thay vì một con số chắc chắn

Kế hoạch dựa trên dữ liệu cần phân biệt **một ước lượng**, **một kịch bản** và **một cam kết**.

| Cách diễn đạt | Ý nghĩa | Điểm cần nói rõ |
| --- | --- | --- |
| “Nếu throughput trung bình giữ nguyên, 12 PBI tương đương khoảng 2–3 tuần xử lý” | Ước lượng kiểm tra quy mô | Các PBI tương đồng? Có chờ phụ thuộc hay đã có việc dở? |
| “Với các điều kiện thuận lợi, mốc gần nhất có thể sớm hơn; nếu phát sinh tích hợp hoặc lỗi có thể muộn hơn” | Kịch bản | Điều kiện nào tạo ra từng kịch bản? |
| “Mục tiêu phát hành phiên bản tối thiểu trước sự kiện X; các tính năng bổ sung có thể dời” | Cam kết có ranh giới | Phạm vi tối thiểu và yêu cầu chất lượng không thể bỏ là gì? |
| “Mốc P85 được tính từ mô phỏng dữ liệu lịch sử phù hợp” | Dự báo xác suất khi có phương pháp hỗ trợ | Dữ liệu nào, giả định nào, cách tính và phạm vi hiệu lực? |

**Không được tùy tiện gắn nhãn “80% chắc chắn” hay “P85” cho một ngày được đoán.** Xác suất có ý nghĩa khi xuất phát từ dữ liệu và phương pháp rõ ràng, với những giả định về sự tương đồng của tương lai.

### 7.1. Dự báo bằng kịch bản

Từ thông tin hiện có, nhóm có thể dựng ba kịch bản định tính:

| Kịch bản | Điều kiện minh họa | Cách ra quyết định |
| --- | --- | --- |
| **Thuận lợi** | Phụ thuộc sẵn sàng; PBI đủ nhỏ; ít việc khẩn | Có thể kéo thêm hạng mục giá trị tiếp theo sau khi đạt DoD |
| **Cơ sở** | Năng lực và lưu lượng công việc gần với lịch sử đại diện | Chọn một tập hạng mục ưu tiên theo mục tiêu, giữ khả năng đổi phạm vi |
| **Bất lợi** | Vắng chuyên gia, lỗi dữ liệu, thay đổi hợp đồng tích hợp | Bảo vệ phạm vi tối thiểu và chất lượng; xem lại thứ tự, mốc và phụ thuộc |

Các kịch bản nên kèm **tín hiệu quan sát**: nếu API đối tác không sẵn vào ngày đã thống nhất, nhóm kích hoạt phương án thử bằng stub trong môi trường phù hợp hoặc chuyển sang hạng mục không phụ thuộc; nếu lỗi bảo mật được phát hiện, ưu tiên khắc phục trước khi mở rộng phát hành.

### 7.2. Khi nào có thể mô phỏng Monte Carlo?

Với nhiều tuần dữ liệu throughput tương đối đại diện, nhóm có thể lấy mẫu từ phân bố lịch sử để mô phỏng nhiều đường hoàn tất backlog và ước lượng những khoảng thời gian theo xác suất. Tuy nhiên, cần thận trọng:

- Mô hình chỉ hữu ích nếu **đơn vị công việc, quy tắc Done và bối cảnh gần tương đương**.
- Những thay đổi lớn về đội hình, cấu trúc sản phẩm, phụ thuộc hoặc kích cỡ hạng mục làm giả định lấy mẫu lịch sử kém đáng tin.
- Một vài tuần dữ liệu như bảng trên **chưa đủ để khẳng định** một phân bố rủi ro chính xác.
- Kết quả mô phỏng nên được cập nhật khi có dữ liệu mới và diễn giải cùng những rủi ro nằm ngoài lịch sử.

Không cần áp dụng Monte Carlo cho mọi dự án. Khi dữ liệu còn ít, **dự báo theo khoảng, làm rõ điều kiện và kiểm tra lại thường xuyên** vẫn tốt hơn một ngày hoàn tất được trình bày như sự thật.

## 8. Chọn việc dựa trên năng lực và kết quả, không chỉ nhét đủ hạng mục

Một Product Backlog có thứ tự giúp nhóm biết **điều gì đáng làm**, còn năng lực và dữ liệu dòng công việc giúp biết **điều gì có thể làm tốt trong giai đoạn tới**. Hai câu hỏi này phải được xử lý cùng nhau.

### Ví dụ backlog đăng ký workshop

| Hạng mục được xem xét | Giá trị hoặc rủi ro | Ghi chú về kế hoạch |
| --- | --- | --- |
| Học viên đăng ký chỗ còn trống và nhận trạng thái đáng tin | Luồng giá trị cốt lõi | Lát cắt đầu phải bao gồm quyền truy cập, chống vượt sức chứa và kiểm thử cần thiết |
| Học viên xem các đăng ký của mình | Tăng minh bạch, giảm hỗ trợ thủ công | Có thể là lát cắt tương đối nhỏ sau luồng đăng ký |
| Học viên tự hủy trong điều kiện hợp lệ | Giảm thao tác hỗ trợ và sai lệch chỗ trống | Cần làm rõ chính sách và xử lý đồng thời |
| Gửi email xác nhận hoặc nhắc lịch | Cải thiện thông tin và giảm bỏ lỡ | Cần trạng thái đăng ký chính xác, kế hoạch khi dịch vụ email lỗi |
| Bộ lọc nâng cao và lịch tháng | Có thể tăng tiện ích | Cần thêm bằng chứng người dùng thực sự cần |
| Theo dõi lỗi, cảnh báo và xử lý sự cố đăng ký | Duy trì độ tin cậy | Một phần quan sát thiết yếu nằm ngay trong DoD/lát cắt; năng lực giám sát chung có thể là hạng mục riêng |

Nhóm không nên chọn “đăng ký cơ bản” vào Sprint rồi nói sẽ thêm **kiểm tra quyền và tính nhất quán dữ liệu ở Sprint sau** nếu đã định phát hành chức năng cho người dùng thật. Chia nhỏ phải giữ **một dòng giá trị hoàn chỉnh và an toàn**, không phải dồn nợ chất lượng sang tương lai.

### 8.1. Một mục tiêu, nhiều cách đạt

Giả sử nhóm đặt mục tiêu: **“Học viên tự đăng ký được workshop và biết chắc trạng thái chỗ đã xác nhận”**.

Có thể đạt mục tiêu bằng một lát cắt đầu hỗ trợ danh sách khung giờ đơn giản và kiểm soát số chỗ đúng; **không nhất thiết** phải kèm lịch tháng, mã ưu đãi, dashboard quản trị và mọi kênh thông báo. Nhóm ưu tiên một giải pháp đủ dùng rồi nhận phản hồi.

Đây là cách giải bài toán năng lực bằng **thay đổi phạm vi tùy chọn**, thay vì ép người thực hiện tăng giờ hoặc bỏ kiểm thử.

### 8.2. Lập kế hoạch theo mức tự tin của từng hạng mục

| Trạng thái hiểu biết | Cách xử lý hợp lý |
| --- | --- |
| **Rõ mục tiêu, nhỏ và ít phụ thuộc** | Có thể chọn triển khai nếu phù hợp năng lực và thứ tự backlog |
| **Đã hiểu giá trị nhưng hạng mục quá lớn** | Chia thành lát cắt dọc có tiêu chí chấp nhận và DoD |
| **Chưa rõ nhu cầu người dùng** | Làm bản mẫu hoặc phỏng vấn có mục đích; xác định quyết định cần học |
| **Chưa rõ kỹ thuật hoặc rủi ro tích hợp** | Spike giới hạn thời gian và kết quả cần kiểm chứng |
| **Phụ thuộc bên ngoài chưa có thời điểm đáng tin** | Xác minh điều kiện, lộ trình hỗ trợ và phương án thay thế; thể hiện mức bất định |
| **Việc khẩn về bảo mật hoặc dữ liệu** | Đánh giá hậu quả, xử lý theo chính sách ưu tiên/sự cố, cập nhật kế hoạch công khai |

Khi hạng mục có bất định cao, “chốt ước lượng thật chi tiết” chưa chắc là cách tốt nhất. Một phép thử nhỏ có thể tạo ra **thông tin giúp ước lượng thực tế hơn** trước khi nhóm cam kết nguồn lực lớn.

## 9. Tình huống xuyên suốt: lập kế hoạch hai Sprint cho chức năng workshop

Nhóm giả định gồm bốn thành viên đa kỹ năng, làm việc theo Scrum với Sprint hai tuần. Trong bốn Sprint gần nhất, họ hoàn tất lần lượt **4, 5, 3 và 4 Product Backlog Item**, theo cùng một Definition of Done. Dữ liệu này chỉ dùng làm **tham khảo thô**, vì các PBI không hoàn toàn đồng kích thước.

Trong Sprint tới, nhóm có **22 ngày-người khả dụng ban đầu** như ví dụ ở phần 4, ít hơn một Sprint bình thường do nghỉ phép và trực hỗ trợ. Product Owner đã làm rõ Product Goal; Developers kiểm tra các hạng mục sắp chọn, rủi ro bảo mật và khả năng tích hợp.

### 9.1. Chọn mục tiêu cho Sprint đầu

**Sprint Goal minh họa:** Học viên đủ điều kiện đăng ký được một workshop còn chỗ và nhận trạng thái nhất quán.

Để tiến tới mục tiêu, nhóm có thể chọn một tập PBI nhỏ và liên quan chặt chẽ:

1. Hiển thị một danh sách workshop hợp lệ, có chỗ còn trống theo dữ liệu thật.
2. Đăng ký chỗ với kiểm tra quyền, giới hạn sức chứa, phản hồi thành công/thất bại rõ.
3. Thiết lập khả năng quan sát lỗi tối thiểu cần thiết và kiểm thử cho luồng đã mở.

Không nên hiểu đây là **ba việc có thể làm độc lập rồi ghép ở cuối**. Các thành phần cần được tích hợp thành một lát cắt đầu cuối đạt DoD; nhóm có thể chia PBI thêm nếu điều đó giúp kiểm tra giá trị sớm. Phạm vi chính xác phải được Developers quyết định qua Sprint Planning dựa trên năng lực và mức hiểu biết thực tế.

### 9.2. Các lựa chọn cho Sprint tiếp theo

Sau Sprint đầu, nhóm mới có dữ liệu về lỗi, cách người học thao tác và lượng công việc còn lại. Nếu kết quả tích cực, có thể cân nhắc Sprint Goal tiếp theo: **“Học viên xem và tự hủy đăng ký đúng chính sách”**. Nếu phát hiện nguy cơ mất dữ liệu, kế hoạch phải ưu tiên xử lý nguyên nhân trước khi mở thêm tính năng.

Việc dự tính hai Sprint ngay từ đầu có ích để **nhìn phụ thuộc và phối hợp kỳ vọng**, nhưng không biến danh sách của Sprint thứ hai thành cam kết bất biến. Khi Sprint đầu kết thúc, nhóm cập nhật dữ liệu, backlog và rủi ro rồi lập kế hoạch mới.

### 9.3. Một bản tin kế hoạch minh bạch

> **Mục tiêu gần:** Giao luồng đăng ký có thể kiểm chứng và đáng tin. **Năng lực:** Sprint tới có 22 ngày-người khả dụng sau các nghĩa vụ đã biết; còn rủi ro hỗ trợ đột xuất. **Dữ liệu:** Bốn Sprint trước hoàn tất 3–5 PBI mỗi Sprint, nhưng kích thước có khác nhau. **Điều chưa chắc:** Xử lý hai yêu cầu đồng thời và tích hợp trạng thái chỗ. **Quyết định:** Ưu tiên lát cắt đăng ký an toàn; bộ lọc nâng cao để sau. **Mốc xem lại:** Khi kiểm thử cạnh tranh và phản hồi từ bản đầu có kết quả.

Thông điệp như vậy giúp người liên quan hiểu **vì sao phạm vi được chọn**, điều gì có thể thay đổi và bằng chứng nào đang chờ, thay vì chỉ thấy một bảng ngày giao màu xanh.

## 10. Lập kế hoạch khi thời hạn, phạm vi hoặc ngân sách bị ràng buộc

Không phải nhóm nào cũng có quyền thay đổi tất cả yếu tố. Có dự án phải ra mắt trước ngày khai giảng, tuân thủ một ngày hiệu lực pháp lý hoặc không được vượt ngân sách. Agile vẫn có ích nếu nhóm **nói rõ điều gì cố định và điều gì có thể điều chỉnh**.

| Ràng buộc chính | Cách xây kế hoạch thực tế | Điều không nên đánh đổi |
| --- | --- | --- |
| **Ngày phát hành cố định** | Làm rõ phạm vi tối thiểu có giá trị, phân nhóm bắt buộc/tùy chọn; tạo Increment nhỏ sớm; theo dõi tín hiệu trễ | Quyền truy cập, tính đúng đắn dữ liệu, kiểm tra an toàn thiết yếu |
| **Phạm vi bắt buộc** | Dùng năng lực và tốc độ lịch sử để đưa ra khoảng thời gian/chi phí có điều kiện; xử lý phụ thuộc và rủi ro | Che giấu độ bất định để công bố một ngày không có căn cứ |
| **Ngân sách hoặc số người cố định** | Ưu tiên giá trị, giới hạn WIP, giảm làm lại; thử phương án nhỏ trước khi đầu tư lớn | Giả định tăng làm thêm giờ liên tục là kế hoạch bền vững |
| **Nhiều phụ thuộc hoặc phê duyệt** | Công khai mốc chờ, người phụ trách, điều kiện đầu vào/đầu ra và lựa chọn thay thế | Ghi phụ thuộc thành “đã xong” khi bên liên quan chưa xác nhận |
| **Yêu cầu chất lượng đặc biệt** | Đưa kiểm thử, bảo mật, vận hành và bằng chứng tuân thủ vào hạng mục/DoD và kế hoạch phát hành | Trì hoãn toàn bộ kiểm chứng tới một giai đoạn cuối |

### Cách nói chuyện khi cả ba yếu tố đều bị cố định

Nếu bên liên quan muốn **ngày, phạm vi và ngân sách đều chắc chắn**, nhưng công việc có nhiều bất định, nhóm cần nêu rõ các đánh đổi và giới hạn. Có thể đề xuất:

- **Phương án A:** Giữ mốc, giao phần cốt lõi an toàn, dời tính năng tùy chọn.
- **Phương án B:** Giữ phạm vi, dự báo lại thời điểm dựa trên năng lực và phụ thuộc hiện có.
- **Phương án C:** Kiểm chứng rủi ro trọng yếu trước, rồi quyết định lại phạm vi hoặc nguồn lực với thông tin tốt hơn.

Việc bổ sung người không bảo đảm tiến độ giảm tương ứng: thành viên mới cần thời gian làm quen, có thể làm tăng nhu cầu phối hợp, và không giải quyết được mọi phụ thuộc. Nếu một cam kết không còn khả thi với năng lực hiện có, nhóm nên **báo sớm bằng bằng chứng và lựa chọn cụ thể**, không chờ tới ngày cuối mới thừa nhận.

## 11. Scrum, Kanban và XP hỗ trợ lập kế hoạch theo dữ liệu ra sao?

### 11.1. Scrum: mục tiêu Sprint và kiểm tra định kỳ

Trong Scrum:

- Product Owner chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog có thứ tự.
- Scrum Team cùng xác định Sprint Goal trong Sprint Planning; Developers chọn khối lượng công việc cho Sprint qua trao đổi với Product Owner và lập kế hoạch thực hiện.
- Developers thường xuyên kiểm tra tiến độ tới Sprint Goal và thích ứng Sprint Backlog.
- Sprint Review giúp kiểm tra Increment cùng bên liên quan và điều chỉnh Product Backlog; Sprint Retrospective giúp cải tiến cách làm.
- Sprint Goal định hướng sự tập trung, còn Definition of Done bảo vệ chất lượng Increment.

Velocity và dự báo năng lực **có thể** hỗ trợ Sprint Planning, nhưng Scrum không bắt buộc story point hoặc một công thức velocity. Sprint là nhịp kiểm tra và thích ứng, không phải lời hứa rằng tất cả PBI đã chọn chắc chắn hoàn tất bất kể dữ liệu mới.

### 11.2. Kanban: quản lý dòng công việc đang thực sự xảy ra

Kanban giúp nhóm:

1. Trực quan hóa các bước và hàng đợi công việc.
2. Đặt **giới hạn WIP** phù hợp để giảm mở việc mới khi việc cũ chưa xong.
3. Theo dõi throughput, cycle time, work item age và những trạng thái bị chờ.
4. Nêu chính sách kéo công việc và xử lý hạng mục khẩn cấp.
5. Dựa vào dữ liệu dòng chảy để dự báo và cải tiến.

Ví dụ, nếu hầu hết công việc chờ kiểm thử nhiều ngày, việc tăng số story bắt đầu không giải quyết nguyên nhân. Nhóm có thể điều chỉnh năng lực kiểm thử, cách tích hợp và kích thước công việc, rồi quan sát liệu cycle time và độ ổn định được cải thiện.

### 11.3. XP: giữ cho dự báo không bị phá vỡ bởi làm lại

Extreme Programming (XP) đề cao kiểm thử, tích hợp liên tục, refactoring, thiết kế đơn giản và phản hồi nhanh. Những thực hành kỹ thuật này làm giảm rủi ro lỗi tích tụ, khiến nhóm có thể tạo Increment nhỏ và điều chỉnh kế hoạch dựa trên phần mềm thật.

**Một kế hoạch chạy nhanh bằng cách hoãn kiểm thử có thể làm tăng công việc làm lại ở những Sprint tiếp theo.** Vì vậy, khi đo năng lực hoàn tất, cần tính đúng **Definition of Done** và chất lượng, không chỉ đếm phần mã vừa được viết.

### Có thể kết hợp các thực hành

Một nhóm dùng Scrum để xác định mục tiêu và phản hồi theo Sprint, dùng các chỉ số dòng công việc của Kanban để phát hiện hàng đợi, và thực hành kỹ thuật XP để giữ khả năng thay đổi an toàn. Việc phối hợp phải giải quyết một vấn đề thực tế của nhóm, thay vì áp thêm nghi thức không đem lại bằng chứng hoặc giá trị.

## 12. Các nguồn khiến kế hoạch sai lệch và cách phản ứng

| Nguồn sai lệch | Dấu hiệu | Cách phản ứng |
| --- | --- | --- |
| **Lấy Sprint tốt nhất làm chuẩn** | Kế hoạch luôn bằng hoặc cao hơn mức lịch sử cao nhất | Xem nhiều chu kỳ và độ biến động; điều chỉnh theo năng lực thật |
| **Không tính hỗ trợ và sự cố** | Người làm thường bị kéo khỏi story, rồi phải tăng giờ | Ghi nhận loại việc, dành khả năng ứng phó và xem lại chính sách hỗ trợ |
| **Ước lượng một hạng mục quá lớn** | Công việc gần hết Sprint vẫn không thể giao phần chạy được | Chia lát cắt dọc, thử rủi ro sớm, giới hạn WIP |
| **Gộp dữ liệu không tương đồng** | Velocity tăng đột ngột sau khi đổi quy tắc Done | Tách giai đoạn dữ liệu; nêu rõ cách đo mới |
| **Thiếu kỹ năng ở một vị trí** | Mọi hạng mục chờ cùng một chuyên gia | Chia sẻ kiến thức, phối hợp trước, xem lại kế hoạch theo năng lực kỹ năng |
| **Đổi ưu tiên liên tục** | Nhiều việc bắt đầu rồi bỏ dở, work item age tăng | Nêu chính sách việc khẩn, bảo vệ mục tiêu và giới hạn việc đang làm |
| **Phụ thuộc bên ngoài** | Công việc kẹt dù nhóm còn người | Xác nhận người chịu trách nhiệm, mốc phối hợp và phương án dự phòng |
| **Bỏ chất lượng để giữ lịch** | Lỗi tăng, làm lại nhiều, phát hành rủi ro | Giữ DoD; giảm phạm vi tùy chọn hoặc thương lượng thời điểm |
| **Chỉ đo điểm/nhiệm vụ, không đo kết quả** | Báo cáo đẹp nhưng người dùng vẫn gặp vấn đề | Thêm dữ liệu hành vi, lỗi và chất lượng của phần mềm đã giao |
| **Dự báo như lời hứa chắc chắn** | Một con số được lặp lại không kèm giả định | Công khai khoảng, điều kiện và thời điểm cập nhật dự báo |
| **Dự phòng quá lớn nhưng không giải thích** | Nguồn lực bị giữ mơ hồ, khó ưu tiên | Dùng lịch sử biến động và rủi ro cụ thể để thống nhất mức dự phòng |
| **Bỏ qua việc đang làm dở** | Dự báo chỉ đếm hạng mục mới, không xử lý nợ công việc | Xem work item age/WIP, hoàn tất việc đang làm trước khi mở nhiều việc mới |

Lập kế hoạch thích ứng không được đánh giá bằng việc **mọi dự báo luôn đúng từng ngày**. Một nhóm minh bạch có thể cập nhật dự báo thường xuyên vì đã phát hiện thông tin mới; điều quan trọng là họ **dự báo có căn cứ, báo thay đổi kịp thời và cải thiện khả năng giao giá trị**.

## 13. Cách đọc kết quả khi kế hoạch và thực tế khác nhau

Khi nhóm giao ít việc hơn dự kiến, việc đầu tiên không phải tìm ai “làm chậm”. Hãy phân tích:

1. **Đầu vào có sai không?** Năng lực đã trừ đúng nghỉ phép, hỗ trợ, họp và trách nhiệm khác chưa?
2. **Khối lượng việc có thay đổi không?** Tiêu chí chấp nhận mới, lỗi dữ liệu, yêu cầu bảo mật hoặc phụ thuộc mới xuất hiện?
3. **Dòng công việc bị chờ ở đâu?** Review, kiểm thử, tích hợp, phê duyệt hay hỗ trợ người dùng?
4. **Chất lượng có làm lại nhiều không?** Lỗi được phát hiện muộn khiến một phần việc phải sửa lặp lại?
5. **Đơn vị đo có còn tương thích không?** Nhóm vừa thay đổi DoD, chia lại PBI hoặc đổi vai trò?
6. **Giả thuyết giá trị đã thay đổi chưa?** Một hạng mục được dừng do phản hồi cho thấy ít giá trị, điều đó có thể là quyết định đúng.

### Phân biệt ba kết quả khác nhau

| Kết quả | Cách đánh giá |
| --- | --- |
| **Không đạt kế hoạch nhưng học được điều quan trọng** | Có thể là kết quả hữu ích nếu nhóm công khai rủi ro và điều chỉnh hướng đi |
| **Đạt số PBI dự kiến nhưng chất lượng suy giảm** | Không được xem là thành công chỉ vì đạt số lượng |
| **Giao ít tính năng hơn nhưng người dùng đạt kết quả tốt hơn** | Cần xem đó có thể là ưu tiên tốt, đặc biệt nếu giảm lỗi và làm lại |

Những kết luận này phải dựa trên bằng chứng thực tế, không dùng như lý do tùy tiện để bỏ cam kết. Khi có người dùng hoặc bộ phận phụ thuộc vào mốc giao, nhóm cần thông báo rõ **tác động và phương án tiếp theo**.

## 14. Quy trình lập kế hoạch dựa trên năng lực và dữ liệu

### Bước 1. Viết kết quả cần đạt và các ràng buộc

Làm rõ Product Goal hoặc kết quả của giai đoạn, người dùng hưởng lợi và những điều bắt buộc giữ: chính sách, chất lượng, bảo mật, ngân sách, hợp đồng, ngày quan trọng. Kế hoạch của nhóm cần phục vụ mục tiêu chung.

### Bước 2. Chuẩn bị backlog có thứ tự và làm rõ phần gần

Phân biệt công việc cốt lõi, tùy chọn, công việc rủi ro, việc hỗ trợ và lỗi. Chia PBI lớn thành các lát cắt dọc; ghi giả định và phụ thuộc chưa rõ. Chỉ đầu tư chi tiết tương xứng với khả năng sắp thực hiện.

### Bước 3. Xác nhận năng lực thực sự

Tính số ngày làm việc thực tế, nghỉ, công việc vận hành, hỗ trợ, hoạt động phối hợp và năng lực kỹ năng. Tránh tính trùng; ghi rõ công việc đã dự kiến và vùng bất định.

### Bước 4. Xem dữ liệu hoàn tất và chất lượng gần đây

Chọn các Sprint/tuần đại diện, thống nhất tiêu chí Done; xem velocity nếu nhóm dùng ước lượng điểm, throughput/cycle time/WIP nếu theo dòng công việc. Ghi nhận sự cố, làm lại và bối cảnh thay đổi.

### Bước 5. Chọn hạng mục phù hợp với mục tiêu và năng lực

Không chọn chỉ để “đạt chỉ tiêu số lượng”. Ưu tiên phần tạo giá trị, giảm rủi ro và có thể hoàn thành đạt DoD. Nếu quá nhiều bất định, thử nghiệm nhỏ trước khi chốt phạm vi lớn.

### Bước 6. Công bố dự báo và các điều kiện

Trình bày mục tiêu, tập phạm vi ưu tiên, mức năng lực, dữ liệu lịch sử, rủi ro và kịch bản. Phân biệt việc nào **đã cam kết**, việc nào **dự kiến nếu điều kiện thuận lợi**.

### Bước 7. Thực hiện và quan sát dòng công việc

Giảm WIP, hỗ trợ hoàn tất, kiểm tra lỗi và phụ thuộc; báo sớm khi thay đổi làm kế hoạch không còn khả thi. Giữ chất lượng bằng kiểm thử và tích hợp liên tục.

### Bước 8. Nhận phản hồi, xem lại dự báo và cải tiến

Đánh giá Increment hoặc kết quả thử nghiệm, xem các chỉ số dòng công việc và kết quả người dùng. Cập nhật backlog, giả định, phạm vi và các dự báo tiếp theo. Retrospective hoặc buổi xem xét dòng chảy là cơ hội tìm một thay đổi thực hành có thể kiểm chứng.

### Vòng lập kế hoạch thích ứng

~~~mermaid
flowchart TD
    A["Mục tiêu và ràng buộc"] --> B["Backlog có thứ tự, phần gần đủ rõ"]
    B --> C["Năng lực thực tế + dữ liệu hoàn tất"]
    C --> D["Chọn lát cắt và dự báo có điều kiện"]
    D --> E["Xây, kiểm thử và hoàn tất đạt DoD"]
    E --> F["Quan sát dòng công việc và kết quả người dùng"]
    F --> G{"Giả định hoặc bối cảnh có thay đổi?"}
    G -->|"Có"| H["Điều chỉnh ưu tiên, phạm vi hoặc dự báo"]
    G -->|"Không"| I["Tiếp tục mục tiêu với dữ liệu mới"]
    H --> B
    I --> C
~~~

Đầu ra của mỗi vòng không chỉ là một bản kế hoạch mới, mà là **hiểu biết tốt hơn về năng lực, công việc, giới hạn và giá trị thực sự**.

## 15. Mẫu kế hoạch ngắn cho một Sprint hoặc chu kỳ làm việc

Mẫu này phù hợp khi nhóm cần ghi lại lập luận để người liên quan có thể xem xét. Không cần điền mọi trường chi tiết nếu rủi ro và phạm vi nhỏ.

~~~text
GIAI ĐOẠN / SPRINT:
MỤC TIÊU CẦN ĐẠT:
NGƯỜI DÙNG / GIÁ TRỊ KỲ VỌNG:
RÀNG BUỘC KHÔNG ĐƯỢC BỎ:

NĂNG LỰC KHẢ DỤNG:
- Thành viên / kỹ năng sẵn sàng:
- Ngày nghỉ / trực vận hành / công việc cố định:
- Phần dự phòng / nguồn bất định:
- Các phụ thuộc có thể làm giảm năng lực:

DỮ LIỆU LỊCH SỬ ĐƯỢC DÙNG:
- Giai đoạn và cách đo:
- Velocity hoặc throughput / cycle time:
- Biến động và điểm nghẽn:
- Khác biệt giữa lịch sử và giai đoạn tới:

BACKLOG ƯU TIÊN:
- Những lát cắt cần để đạt mục tiêu:
- Những hạng mục có thể dời:
- Công việc chất lượng / bảo mật / vận hành:
- Giả định cần thử trước:

DỰ BÁO:
- Phạm vi / thời điểm có điều kiện:
- Kịch bản cơ sở và tình huống bất lợi:
- Điều gì là cam kết; điều gì vẫn là dự báo:

KIỂM CHỨNG:
- Tiêu chí chấp nhận / Definition of Done:
- Bằng chứng và người đánh giá:
- Chỉ số dòng công việc / kết quả người dùng:

XEM LẠI:
- Tín hiệu buộc phải cập nhật kế hoạch:
- Thời điểm và người chịu trách nhiệm truyền đạt:
- Quyết định sau khi có dữ liệu mới:
~~~

Hãy giữ mẫu này như **công cụ hỗ trợ hội thoại và quyết định**. Việc điền đầy đủ trường không thay thế được thảo luận và phản hồi từ phần mềm hoạt động được.

## 16. Bài tập ứng dụng: lập kế hoạch mà không tăng giờ làm

**Tình huống:** Một nhóm 5 người chuẩn bị Sprint hai tuần để phát triển tính năng theo dõi tiến độ học. Nhóm có dữ liệu **minh họa**:

- Sprint gần đây hoàn thành lần lượt **5, 4, 6, 3** PBI đạt DoD, với kích thước tương đối tương đồng nhưng vẫn có biến động.
- Một thành viên nghỉ 4 ngày, một thành viên trực hỗ trợ nửa thời gian trong Sprint.
- Có lỗi **mất tiến độ học khi đổi thiết bị** cần xử lý trước khi mở rộng tính năng.
- Product Backlog còn các đề xuất: sửa lỗi tiến độ, nút “Học tiếp”, dashboard biểu đồ, bảng xếp hạng, gửi thông báo nhắc học, bổ sung dữ liệu đo hành vi học tiếp.
- Bên liên quan yêu cầu giao dashboard trong Sprint, nhưng nhóm chưa biết nó có giúp người học quay lại hay không.

Hãy lập kế hoạch theo các câu hỏi:

1. **Năng lực:** Bạn cần hỏi thêm những dữ kiện gì trước khi biết sức chứa Sprint? Vì sao 5 người × 10 ngày không phải năng lực cho tính năng mới?
2. **Dữ liệu:** Trung bình bốn Sprint là bao nhiêu PBI? Có nên chọn đúng số ấy vào Sprint mới khi đã biết có người nghỉ và trực hỗ trợ không?
3. **Mục tiêu:** Sprint Goal nào giúp người học tiến bộ thực tế và vẫn tập trung xử lý rủi ro mất dữ liệu?
4. **Ưu tiên:** Lỗi mất tiến độ nên được đánh giá thế nào so với dashboard? Có hạng mục nào cần thử trước khi xây đầy đủ?
5. **Phạm vi:** Hãy chia một lát cắt đủ nhỏ để học viên tìm được bài tiếp theo và vẫn đáp ứng các điều kiện dữ liệu, phân quyền và kiểm thử cần thiết.
6. **Dự báo:** Bạn sẽ nói thế nào với bên liên quan về phạm vi có khả năng giao, phần chưa chắc chắn và mốc xem lại?
7. **Phản hồi:** Sau Sprint, nếu nút “Học tiếp” được nhấn nhiều nhưng tỷ lệ hoàn thành bài tiếp theo không tăng, backlog nên thay đổi ra sao?

### Gợi ý hướng giải

Trung bình lịch sử là:

\[
(5+4+6+3)/4=4{,}5\ \text{PBI/Sprint}.
\]

Đây **không phải mục tiêu bắt buộc** cho Sprint mới: vắng mặt, trực hỗ trợ, tính phức tạp và lỗi đang cần xử lý làm bối cảnh khác lịch sử. Cần tính năng lực cụ thể theo lịch, khả năng kỹ năng, những công việc cố định và rủi ro còn lại.

Nhóm có thể chọn mục tiêu như **“Tiến độ của người học được ghi nhận đáng tin và người học biết bài phù hợp cần học tiếp”**. Lỗi mất tiến độ là rủi ro trực tiếp đối với giá trị và niềm tin, cần ưu tiên dựa trên tác động. Có thể triển khai lát cắt nhỏ cho nút “Học tiếp” sau khi bảo đảm dữ liệu tiến độ chính xác, kèm đo lường hành vi cần thiết; dashboard nhiều biểu đồ và bảng xếp hạng nên chờ bằng chứng về giá trị. Tập công việc cụ thể do Developers lựa chọn qua Sprint Planning cùng Product Owner, theo năng lực và Sprint Goal.

Nếu bằng chứng cho thấy người học vẫn dừng vì bài tiếp theo quá khó, nhóm cần **cập nhật giả thuyết và Product Backlog** thay vì chỉ tối ưu màu sắc nút. Một dự báo có trách nhiệm sẽ ghi rõ điều kiện, rủi ro, phần có thể dời và thời điểm xem lại.

## 17. Ghi nhớ và tự kiểm tra

**Lập kế hoạch theo năng lực thực tế và dữ liệu đã có** nghĩa là nối mục tiêu sản phẩm, backlog có thứ tự, sức chứa thực tế của nhóm, bằng chứng về công việc đã hoàn tất và độ bất định thành **một quyết định có thể điều chỉnh**. Capacity cho biết phần nguồn lực sẵn có; velocity hoặc throughput và cycle time giúp hiểu khả năng hoàn tất đã quan sát; nhưng không chỉ số nào tự bảo đảm kết quả tương lai.

Tự kiểm tra:

1. Vì sao tổng ngày-người theo lịch không bằng năng lực có thể dành cho backlog trong một Sprint?
2. Velocity khác throughput, cycle time và lead time ở đơn vị và mục đích sử dụng như thế nào?
3. Vì sao story point không thể quy đổi cố định ra giờ hoặc dùng để so sánh các nhóm?
4. Một nhóm có throughput tăng nhưng lỗi sau phát hành tăng thì kế hoạch có thật sự hiệu quả không?
5. Khi chỉ có dữ liệu của một Sprint thuận lợi, có nên công bố một ngày hoàn thành với xác suất 85% không? Vì sao?
6. Tại sao cần xem work item age và WIP của những hạng mục đang làm, không chỉ đếm việc đã hoàn thành?
7. Khi mốc phát hành cố định nhưng năng lực giảm, nhóm nên thương lượng điều gì trước khi nghĩ tới bỏ kiểm thử?
8. Product Backlog, Sprint Goal và Definition of Done giúp cân bằng ưu tiên, tập trung và chất lượng ra sao?
9. Khi nhu cầu hoặc dữ liệu mới khiến nhóm đổi dự báo, phải truyền đạt những điều kiện và quyết định gì?
10. Hãy nêu một ví dụ mà **giảm phạm vi tính năng tùy chọn** giúp giao giá trị sớm hơn mà vẫn giữ trách nhiệm với người dùng.

Trước mỗi lần chốt kế hoạch, hãy hỏi: **“Chúng ta đang cam kết kết quả nào, năng lực và dữ liệu nào thực sự hỗ trợ lựa chọn này, và tín hiệu nào sẽ khiến chúng ta điều chỉnh?”** Kế hoạch tốt trong Agile không né tránh sự bất định; nó làm sự bất định **nhìn thấy được, có thể quản lý và giảm dần qua mỗi lần giao sản phẩm và nhận phản hồi**.
