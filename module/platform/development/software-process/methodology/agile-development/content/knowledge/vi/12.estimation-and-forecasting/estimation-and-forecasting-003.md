# Ước lượng tương đối bằng story point và hạng mục tham chiếu

Trong một dự án Agile, nhóm cần quyết định nên lấy công việc nào vào Sprint, cần chia nhỏ hạng mục nào và phạm vi còn lại có thể bàn giao trong khoảng thời gian nào. Nhưng phát triển phần mềm không phải công việc lặp lại với thời gian cố định: yêu cầu có thể chưa rõ, tích hợp có thể phát sinh lỗi, một phương án thiết kế có thể không hiệu quả như kỳ vọng. Nếu cố trả lời mọi câu hỏi bằng một con số giờ công thật chính xác ngay từ đầu, nhóm có nguy cơ tạo ra **cảm giác chắc chắn giả**.

**Ước lượng tương đối (relative estimation)** là cách xem xét một hạng mục lớn hay nhỏ **so với những hạng mục đã hiểu**. Nhiều nhóm sử dụng **story point** làm đơn vị quy ước và chọn các **hạng mục tham chiếu (reference stories)** để duy trì cùng một thang so sánh. Mục đích chính là hỗ trợ thảo luận phạm vi, độ phức tạp, bất định và khả năng bàn giao giá trị.

Bài học thuộc chương **Ước lượng và dự báo** của mô-đun **AGILE_DEVELOPMENT**. Nội dung liên hệ với user story, Product Backlog, Scrum, Kanban, XP, phản hồi sớm và đo lường dòng công việc. Story point là **một công cụ có thể lựa chọn**, không phải quy định bắt buộc của Tuyên ngôn Agile hoặc Scrum Guide.

Sau bài học, người học có thể phân biệt ước lượng và dự báo; tạo thang story point nội bộ; chọn hạng mục tham chiếu; tổ chức Planning Poker; chia nhỏ story quá lớn; sử dụng dữ liệu hoàn thành để dự báo có điều kiện; và tránh dùng điểm để đánh giá năng suất cá nhân.

## 1. Phân biệt ước lượng, dự báo và cam kết

| Khái niệm | Câu hỏi cần trả lời | Minh họa |
| --- | --- | --- |
| **Ước lượng (estimate)** | Hạng mục này lớn hoặc khó tương đối đến đâu? | “Story mới gần với mốc 5 điểm hơn mốc 3 điểm.” |
| **Dự báo (forecast)** | Với dữ liệu thực tế và giả định hiện tại, khoảng kết quả nào có thể xảy ra? | “Phạm vi còn lại có thể cần khoảng hai đến ba Sprint nếu điều kiện không thay đổi lớn.” |
| **Cam kết (commitment)** | Mục tiêu hoặc tiêu chuẩn nào nhóm chịu trách nhiệm theo đuổi? | “Sprint Goal là giúp học viên tiếp tục học từ tiến độ đã lưu.” |

Story point không phải thời hạn bàn giao. Một dự báo cũng không phải cam kết vô điều kiện, vì nó phụ thuộc năng lực, phạm vi, chất lượng và các biến động ngoài dự đoán.

Trong Scrum, những commitment chính thức là **Product Goal** của Product Backlog, **Sprint Goal** của Sprint Backlog và **Definition of Done** của Increment. Scrum không bắt buộc ước lượng bằng story point.

### Vì sao chỉ hỏi “mất bao nhiêu giờ?” thường chưa đủ?

Ví dụ, thay đổi giao diện hiển thị tiến độ học có thể mất ít thời gian viết mã, nhưng nhóm còn cần:

- Làm rõ thế nào là “đã hoàn thành” một bước học.
- Xác định API nào trả dữ liệu tiến độ và cách xử lý dữ liệu cũ.
- Kiểm tra hành vi khi mất mạng, tải lại trang và đăng nhập trên thiết bị khác.
- Hoàn thành kiểm thử, tích hợp và các yêu cầu chất lượng.

Nếu chỉ ước lượng thời gian viết giao diện, nhóm đã bỏ qua phần công việc cần thiết để tạo một **Increment đáp ứng Definition of Done**. Ước lượng tương đối khuyến khích hỏi hạng mục mới **khác hạng mục đã làm ở điểm nào**, giúp phát hiện các giả định đó.

Ước lượng giờ không phải lúc nào cũng sai. Khi công việc đã ổn định hoặc cần lập lịch chi tiết, thời gian vẫn có ích. Vấn đề là **không được coi một ước lượng ban đầu như sự thật chắc chắn**, hoặc bí mật đổi đơn vị story point thành giờ.

## 2. Story point phản ánh điều gì?

**Story point** là đơn vị quy ước, thường được nhóm dùng để thể hiện **kích thước tương đối của một Product Backlog Item**. Khi so sánh, nhóm có thể cân nhắc:

1. **Khối lượng công việc cần làm:** Giao diện, xử lý nghiệp vụ, dữ liệu, tích hợp, kiểm thử và hoàn thiện.
2. **Độ phức tạp:** Số tương tác giữa các thành phần, trường hợp biên, quy tắc khó hoặc thiết kế chưa quen.
3. **Bất định và rủi ro:** Những điều chưa biết có thể khiến cách làm thay đổi hoặc phát sinh kiểm chứng.

Đây là các yếu tố thường được cân nhắc, **không phải công thức tính điểm chuẩn**. Có nhóm thiên về tổng kích thước công việc; có nhóm đưa bất định vào so sánh nhiều hơn. Quan trọng nhất là **cùng hiểu quy ước và duy trì nó đủ ổn định để có dữ liệu hữu ích**.

### Story point không phải những thứ sau

| Nhầm lẫn | Vì sao không đúng? |
| --- | --- |
| **1 điểm = 1 giờ hoặc 1 ngày** | Điểm không có đơn vị thời gian cố định; cùng một hạng mục có thể chịu những điều kiện thực hiện khác nhau |
| **5 điểm nghĩa là khó chính xác gấp 5 lần 1 điểm** | Thang điểm chỉ biểu đạt tương quan, không phải phép đo vật lý có tỉ lệ tuyệt đối |
| **Điểm của một người** | Điểm gắn với kích thước công việc theo góc nhìn nhóm, không đo thành tích cá nhân |
| **Thước đo dùng chung mọi đội** | Mỗi đội chọn mốc và quy ước khác nhau, nên không thể so sánh trực tiếp |
| **Chỉ số giá trị sản phẩm** | Hoàn thành nhiều điểm không chứng minh người dùng có được kết quả mong muốn |
| **Mức độ ưu tiên** | Một sửa lỗi 2 điểm có thể khẩn cấp hơn tính năng 8 điểm; thứ tự còn tùy giá trị và rủi ro |

Chẳng hạn, hai story cùng 5 điểm có thể mất thời gian thực tế khác nhau. Đó không nhất thiết là sai sót: câu hỏi là **trong nhiều hạng mục, cách ước lượng có giúp nhóm lập kế hoạch và thảo luận bất định tốt hơn không?**

## 3. Hạng mục tham chiếu giúp nhóm dùng cùng một thước đo

Một vấn đề lớn của story point là **con số tự nó không có ngữ cảnh**. Với một người, 3 điểm có thể là sửa một màn hình. Với người khác, 3 điểm có thể bao gồm API và kiểm thử tích hợp. Nếu cả hai cùng nói “3”, vẻ ngoài nhất trí có thể che giấu khác biệt về phạm vi.

**Hạng mục tham chiếu** là một công việc mà nhóm đã hiểu rõ **giá trị, ranh giới, điều kiện hoàn thành và kích thước tương đối**, được dùng làm mốc cho các hạng mục mới. Hạng mục đã hoàn thành và có bằng chứng thực tế thường là mốc tốt nhất.

Một tham chiếu tốt cần:

- **Phạm vi rõ:** Bao gồm và không bao gồm những tình huống nào?
- **Giá trị hoặc lý do tồn tại rõ:** Người dùng có khả năng gì sau khi xong, hoặc rủi ro nào được giảm?
- **Kiểm chứng rõ:** Có tiêu chí chấp nhận và tiêu chuẩn chất lượng đã áp dụng.
- **Đại diện cho công việc nhóm thật sự làm:** Không chọn một ví dụ quá xa lạ.
- **Dễ nhớ và dễ đối chiếu:** Thành viên có thể nói “story mới giống mốc A nhưng thêm đồng bộ B”.
- **Tương đối ổn định:** Không thay số điểm của mốc sau mỗi lần ước lượng.

### Khi chưa có lịch sử

Nhóm mới có thể chọn vài story **được tất cả thành viên cùng hiểu** làm mốc tạm thời. Điểm của chúng là quy ước khởi tạo, không phải dữ liệu đã được chứng minh. Khi nhóm có các Increment đã hoàn thành, nên dùng trải nghiệm thực tế để rà soát mốc hoặc thay mốc không còn đại diện.

Không nên áp nguyên bảng điểm của nhóm khác. Một hạng mục 5 điểm ở đội chuyên về giao diện có thể khác rất nhiều với 5 điểm ở đội vận hành một hệ thống nhiều tích hợp.

## 4. Tạo một thang tham chiếu cho nhóm học trực tuyến

Một thang thường gặp là **1, 2, 3, 5, 8, 13, 21**, có khoảng cách lớn hơn khi kích thước tăng. Dãy này tương tự Fibonacci nhưng **không bắt buộc**: nhóm có thể dùng kích thước áo (XS/S/M/L/XL), thang 1–5 hoặc cách khác.

Giả sử một đội làm nền tảng học trực tuyến thống nhất các **ví dụ minh họa**:

| Điểm | Hạng mục tham chiếu | Phạm vi và giả định |
| ---: | --- | --- |
| **1** | Hiển thị thông báo lưu tiến độ thành công/thất bại | Dựa trên API hiện có, thông điệp đã thống nhất; kiểm thử trạng thái đơn giản |
| **2** | Lọc danh sách bài học theo trạng thái | Dữ liệu trạng thái đã có, cần UI và kiểm thử bộ lọc |
| **3** | Hiển thị tiến độ bài học sau mỗi bước | API tiến độ đã ổn định, có tải lại và kiểm thử hiển thị |
| **5** | Tiếp tục bài học tại vị trí đã lưu trên cùng thiết bị | Cần lưu/đọc, xử lý một số lỗi mạng, kiểm thử tích hợp |
| **8** | Xem tiến độ đã đồng bộ trên thiết bị thứ hai | Có thêm quy tắc dữ liệu cũ, xung đột và kiểm thử đa thiết bị |

**Đây không phải bảng điểm chuẩn cho ngành phần mềm.** Một nhóm có API sẵn và bộ kiểm thử tốt có thể đánh giá một thay đổi nhỏ hơn. Một nhóm mới tích hợp hệ thống ngoài có thể đánh giá nó lớn hơn.

### Ghi thông tin mốc như thế nào?

~~~text
Mã: REF-05
Tên: Tiếp tục bài học từ vị trí đã lưu
Điểm quy ước: 5
Người hưởng lợi: Học viên học dở rồi quay lại
Bao gồm:
  - Một tài khoản và một thiết bị
  - Lưu, đọc và hiển thị vị trí đã xác nhận
  - Lỗi mạng phổ biến và kiểm thử tích hợp
Không bao gồm:
  - Đồng bộ giữa nhiều thiết bị
  - Chế độ học offline đầy đủ
Lý do chọn:
  Nhóm đã hoàn thành và hiểu được phạm vi của lát cắt này
~~~

Không nhất thiết cần mốc cho mọi con số. Thường một số mốc **nhỏ, vừa và lớn đã được hiểu rõ** đủ để khởi đầu. Khi có công việc rất khác biệt, có thể thêm mốc cho một dạng tích hợp hoặc nghiên cứu cụ thể.

### Vì sao tham chiếu cần giữ cả phần “không bao gồm”?

“Lưu tiến độ” có thể chỉ lưu một trường vào API sẵn, hoặc bao gồm offline, đồng bộ đa thiết bị và giải quyết xung đột. Nếu không ghi ranh giới, cùng tên story có thể dẫn đến những mức ước lượng rất khác nhau. Một hạng mục tham chiếu tốt giúp nhóm làm rõ **điều gì đang được so sánh**.

## 5. Ước lượng tương đối từng bước

~~~mermaid
flowchart TD
    A["Chọn Product Backlog Item cần thảo luận"] --> B["Làm rõ giá trị, phạm vi và tiêu chí chấp nhận"]
    B --> C["Chọn story tham chiếu gần nhất"]
    C --> D["Thành viên đánh giá độc lập"]
    D --> E{"Có chênh lệch đáng kể?"}
    E -->|Có| F["Thảo luận giả định, phụ thuộc và rủi ro"]
    F --> G{"Cần chia nhỏ hoặc nghiên cứu trước?"}
    G -->|Có| H["Chia lát cắt / spike có giới hạn"]
    H --> B
    G -->|Không| C
    E -->|Không| I["Ghi mức ước lượng và những giả định chính"]
    I --> J["Dùng cho lập kế hoạch, cập nhật từ phản hồi"]
~~~

### Bước 1 — Xác nhận mục đích của story

Ví dụ:

> Là học viên đang học dở, tôi muốn quay lại đúng vị trí đã lưu, để không phải học lại những phần đã hoàn thành.

Nhóm hỏi: “Vị trí” nghĩa là bài, chương hay mốc video? Lưu trên một hay nhiều thiết bị? Lúc mất mạng, có thông báo nào? Có điều kiện nghiệp vụ nào liên quan đến chứng chỉ và điểm bài kiểm tra? Đây là những câu hỏi về **hành vi cần có**, không phải tranh luận về điểm.

### Bước 2 — So sánh với các mốc gần nhất

Với story trên, nhóm nhìn mốc **REF-03** (hiển thị tiến độ) và **REF-05** (tiếp tục từ vị trí đã lưu):

- Nếu chỉ hiển thị dữ liệu có sẵn, hạng mục có thể gần nhóm **3 điểm**.
- Nếu có lưu, đọc lại, xử lý lỗi và kiểm thử tích hợp, nó có thể gần **5 điểm**.
- Nếu có đồng bộ đa thiết bị và quy tắc giải quyết xung đột, nó có thể tiến tới **8 điểm hoặc hơn**.

### Bước 3 — Đưa ra đánh giá độc lập

Thành viên tham gia thực hiện chọn mức tương đối trước khi xem lựa chọn của người khác. Cách này giảm nguy cơ cả nhóm đi theo người nói đầu tiên hoặc người có chức vụ cao hơn.

### Bước 4 — Khai thác chênh lệch

Giả sử ba người chọn **3, 5, 8**. Người chọn 3 có thể nghĩ API đã xử lý mọi logic; người chọn 8 biết API chưa giải quyết trường hợp dữ liệu cũ. Cần trao đổi **phạm vi và rủi ro** trước khi chốt điểm.

Không nên lấy trung bình \( (3+5+8)/3 \) rồi làm tròn chỉ để kết thúc cuộc họp. Trung bình không giải quyết sự khác biệt về yêu cầu.

### Bước 5 — Ghi quyết định đủ ngắn

~~~text
Hạng mục: Tiếp tục từ tiến độ đã lưu
Ước lượng của nhóm: 5 điểm
Tham chiếu: REF-05
Bao gồm: Một thiết bị, đọc/lưu tiến độ, lỗi mạng phổ biến
Không bao gồm: Đồng bộ đa thiết bị, học offline đầy đủ
Cần theo dõi: Độ trễ API khi nhiều học viên truy cập
Quyết định: Kiểm chứng API trước khi mở rộng phạm vi
~~~

**Giá trị chính** của các bước là nhóm đã đạt **cách hiểu chung về story**; số điểm chỉ là kết quả hỗ trợ việc lên kế hoạch.

## 6. Planning Poker: thảo luận thông minh từ những điểm khác nhau

**Planning Poker** là một kỹ thuật ước lượng theo nhóm. Mỗi thành viên chọn thẻ điểm hoặc đưa ra mức so sánh riêng, sau đó công bố cùng lúc. Khi có chênh lệch, nhóm giải thích và có thể chọn lại sau khi làm rõ.

Một vòng gợi ý:

1. Người hiểu nghiệp vụ hoặc Product Owner giới thiệu **người dùng, giá trị và điều kiện chấp nhận**.
2. Developers và người kiểm thử hỏi về phụ thuộc, ràng buộc, dữ liệu và Definition of Done.
3. Nhóm xác định hạng mục tham chiếu phù hợp.
4. Từng người chọn mức điểm **độc lập**.
5. Công bố cùng lúc; người chọn cao và thấp giải thích **điều mình đang giả định**.
6. Nếu còn bất định quan trọng, nhóm quyết định chia story, làm spike hoặc hỏi thêm nghiệp vụ.
7. Khi đủ rõ để lập kế hoạch, nhóm ghi một mức tương đối và lý do.

### Minh họa: ba cách hiểu về cùng một story

| Người | Đánh giá ban đầu | Cách hiểu đằng sau |
| --- | ---: | --- |
| Developer A | **3** | “API đã lưu tiến độ, chỉ cần hiển thị lại.” |
| Developer B | **5** | “Phải xử lý khôi phục vị trí và lỗi khi tải trang.” |
| Người kiểm thử | **13** | “Tôi đang tính cả dữ liệu xung đột giữa nhiều thiết bị và offline.” |

Nhóm xác nhận **phạm vi hiện tại chỉ gồm một thiết bị, online, xử lý lỗi mạng phổ biến**. Đồng bộ offline được đưa vào hạng mục khác. Điểm được xem xét lại theo mốc 5, đồng thời nhóm bổ sung tiêu chí chấp nhận cho trường hợp lưu thất bại.

**Kết quả quan trọng:** Nhóm phát hiện bất đồng về phạm vi **trước khi lập trình**. Đây thường là lợi ích lớn hơn bản thân việc chọn con số cuối cùng.

### Khi nào ngừng tranh luận?

Nếu chênh lệch giữa hai mốc liền nhau **không làm thay đổi quyết định**, nhóm có thể chọn mức quy ước hợp lý và tiếp tục. Nếu chênh lệch đến từ rủi ro dữ liệu, tích hợp chưa kiểm chứng hoặc quy tắc nghiệp vụ có thể thay đổi thiết kế, hãy giải quyết nguyên nhân.

Planning Poker **không cần đạt đồng thuận hình thức bằng mọi giá**. Cuộc họp càng dài không tự khiến dự báo càng chính xác.

## 7. Ví dụ xuyên suốt: ước lượng backlog nền tảng học trực tuyến

Giả sử Product Goal là:

> Học viên mới có thể bắt đầu, hoàn thành bài đầu tiên và quay lại học từ tiến độ đã được lưu một cách đáng tin cậy.

Nhóm đã thống nhất các hạng mục tham chiếu trong mục 4. Các con số dưới đây **chỉ minh họa quy ước của nhóm giả định**.

| ID | Product Backlog Item | Mốc gần nhất | Điểm minh họa | Điều còn cần làm rõ |
| --- | --- | --- | ---: | --- |
| PBI-11 | Học viên lọc danh sách bài theo trạng thái học | REF-02 | **2** | Quy tắc phân loại “đang học” |
| PBI-12 | Học viên xem tiến độ cập nhật sau từng bước | REF-03 | **3** | Cách làm mới khi hoàn thành |
| PBI-13 | Học viên quay lại vị trí đã lưu trên cùng thiết bị | REF-05 | **5** | Lỗi mạng và dữ liệu tiến độ cũ |
| PBI-14 | Học viên mở thiết bị thứ hai và thấy tiến độ đã đồng bộ | REF-08 | **8**, tạm thời | Quy tắc giải quyết xung đột |
| PBI-15 | Học viên học offline nhiều ngày rồi đồng bộ lại | Lớn hơn REF-08 | **Chưa đáng tin** | Bảo vệ dữ liệu, tải nội dung, xung đột, đồng bộ |

### Vì sao PBI-13 lớn hơn PBI-12?

PBI-12 chủ yếu cần đọc dữ liệu, hiển thị và kiểm tra trạng thái. PBI-13 thêm lưu, đọc lại, đồng bộ trạng thái giữa giao diện và API, xử lý trường hợp mạng lỗi và kiểm thử hồi quy. Do đó, trong thang **của nhóm ví dụ**, PBI-13 gần mốc 5 hơn.

Tuy nhiên, nếu một thư viện ổn định đã giải quyết việc khôi phục tiến độ hoàn toàn, ước lượng có thể nhỏ hơn. **Tên tính năng không quyết định số điểm**.

### Vì sao PBI-15 chưa nên gán 21 điểm để “cho xong”?

Không chỉ vì nó lớn, mà vì các lựa chọn nghiệp vụ chưa rõ:

- Khi thiết bị A hoàn thành bước 5, thiết bị B offline ở bước 3, kết quả đồng bộ nên ra sao?
- Học viên có được cố tình học lại bài cũ và lưu mốc thấp hơn không?
- Nội dung học có giới hạn tải về hoặc quyền sử dụng nào?
- Sau nhiều ngày không kết nối, dữ liệu và phiên đăng nhập có còn hợp lệ không?

Những câu trả lời có thể làm thay đổi kiến trúc, trải nghiệm và kiểm thử. Một **phép thử kỹ thuật có giới hạn**, kèm chia nhỏ story, có ích hơn con số lớn che giấu bất định.

### Điểm không quyết định thứ tự ưu tiên

PBI-11 chỉ 2 điểm không có nghĩa luôn phải làm trước PBI-13 là 5 điểm. Nếu nhiều học viên **mất tiến độ đã hoàn thành**, cải thiện độ tin cậy lưu tiến độ có thể mang giá trị lớn hơn tính năng lọc danh sách bài. Trong Scrum, **Product Owner** chịu trách nhiệm sắp thứ tự Product Backlog theo giá trị và bối cảnh; ước lượng là một trong các đầu vào.

## 8. Story lớn, thiếu thông tin và kỹ thuật chia nhỏ

### Khi nào một story đang quá lớn?

Dấu hiệu thường thấy:

- Một story gom nhiều vai trò, luồng và kênh sử dụng.
- Phải hoàn thành nhiều tuần hoặc nhiều nhóm công việc mới có phần sử dụng được.
- Các thành viên cho điểm cách xa nhau vì hiểu phạm vi khác nhau.
- Có phụ thuộc chưa rõ hoặc tích hợp chưa từng được kiểm tra.
- Không thể xác định điều kiện hoàn thành riêng cho một phần nhỏ.

Ví dụ “xây hệ thống đồng bộ tiến độ offline hoàn chỉnh cho mọi thiết bị” là một **phạm vi lớn**. Nhóm có thể tách:

1. Người học thấy tiến độ đã lưu trên thiết bị đang sử dụng.
2. Người học trở lại bài trên cùng thiết bị khi có mạng.
3. Người học thấy tiến độ đã xác nhận trên thiết bị thứ hai khi cả hai online.
4. Người học được thông báo rõ khi thay đổi chưa đồng bộ thành công.
5. Người học đồng bộ một phạm vi nội dung offline giới hạn theo quy tắc đã kiểm chứng.

Lát cắt cần đi qua các phần giao diện, xử lý và dữ liệu **đủ để tạo hành vi có ích**, không chỉ là ba task “database, API, frontend” tách rời. Tuy vậy, không được trì hoãn các yêu cầu **bắt buộc về bảo mật, nhất quán hoặc chống mất dữ liệu** chỉ để phần đầu trông nhỏ hơn.

### Spike giảm bất định trước khi ước lượng tiếp

**Spike** là một hoạt động nghiên cứu hoặc thử nghiệm có mục tiêu và giới hạn, thường dùng khi câu hỏi kỹ thuật quan trọng chưa thể trả lời bằng trao đổi đơn thuần.

~~~text
Mục tiêu:
  Kiểm tra khả năng đồng bộ tiến độ giữa hai thiết bị.
Câu hỏi:
  Bản cập nhật cũ có ghi đè tiến độ mới hơn không?
Phạm vi:
  Môi trường thử nghiệm, dữ liệu mẫu, không phát hành tính năng.
Kết quả:
  Bằng chứng, rủi ro, đề xuất quy tắc, phương án khả thi,
  cập nhật ước lượng cho phần sản phẩm cần bàn giao.
~~~

Đầu ra chính của spike là **kiến thức và quyết định**. Không nên gọi một spike nghiên cứu là Increment cung cấp tính năng hoàn chỉnh nếu nó chưa tạo được phần sản phẩm đáp ứng chất lượng và có thể sử dụng.

### Đừng cộng điểm để thay cho làm rõ

Nếu người ước lượng không biết story cần xử lý một hay nhiều hệ thống, cộng thêm 5 điểm dự phòng chỉ khiến **phạm vi mơ hồ trở thành một con số mơ hồ hơn**. Hãy nêu câu hỏi, tác động của câu trả lời và cách kiểm chứng. Sau khi có bằng chứng, nhóm mới quyết định gộp, chia hoặc ước lượng lại.

## 9. Khi nào nên xem xét lại ước lượng?

Một số thay đổi có thể làm story khác đi đáng kể:

- Product Owner và Developers làm rõ thêm **điều kiện chấp nhận** khiến phạm vi tăng hoặc giảm.
- Xuất hiện **phụ thuộc mới** hay sự cố dữ liệu chưa được biết trước.
- Kết quả spike xác nhận phải đổi hướng triển khai.
- Story được chia thành những lát cắt mới.
- Hệ thống nền tảng thay đổi, khiến các mốc cũ không còn đại diện.

Nên **ghi lý do điều chỉnh** thay vì chỉ đổi số điểm. Ví dụ: “Từ 5 lên 8 vì bổ sung đồng bộ đa thiết bị”. Với story chưa bắt đầu, việc cập nhật theo phạm vi mới có thể hợp lý.

Ngược lại, **đừng sửa điểm của story đã hoàn thành chỉ để khớp thời gian thực tế**. Nếu story 5 điểm mất nhiều ngày vì hệ thống kiểm thử liên tục lỗi, nhóm cần phân tích nút thắt và cải thiện môi trường. Viết lại điểm quá khứ có thể khiến dữ liệu lịch sử không còn dùng được.

Story point là **ước lượng tại thời điểm nhóm có một mức hiểu biết nhất định**, không phải con số cuối cùng phải đúng về thời gian.

## 10. Từ story point đến dự báo có điều kiện

Một số nhóm Scrum dùng **velocity**, thường được hiểu là tổng điểm của các hạng mục **đã hoàn thành theo Definition of Done trong một Sprint**, để hỗ trợ dự báo nội bộ. Velocity **không phải metric bắt buộc** của Scrum.

### Ví dụ với ba Sprint đã kết thúc

Giả sử cùng một nhóm có dữ liệu:

| Sprint | Tổng điểm các hạng mục đã đạt DoD |
| --- | ---: |
| A | 18 |
| B | 21 |
| C | 23 |

Trung bình đơn giản:

\[
\bar v = \frac{18+21+23}{3} = \frac{62}{3} \approx 20{,}7 \text{ điểm/Sprint}
\]

Nếu các hạng mục còn lại sau khi làm rõ có tổng kích thước **34 điểm**, phép chia thô cho kết quả:

\[
\frac{34}{20{,}7} \approx 1{,}64 \text{ Sprint}
\]

Không thể hứa “hoàn thành đúng sau 1,64 Sprint”. Một cách diễn đạt thận trọng có thể là **khoảng hai đến ba Sprint**, với điều kiện phạm vi, cách ước lượng, năng lực và rủi ro không thay đổi đáng kể. Khoảng này chỉ là **nhận định minh họa**, không phải khoảng tin cậy xác suất đã tính từ ba mẫu.

### Các giả định cần nói rõ khi dự báo

| Giả định | Nếu không còn đúng, điều gì xảy ra? |
| --- | --- |
| Nhóm giữ cùng mốc story point | Velocity cũ khó so với điểm hiện tại |
| Số người và thời gian dành cho sản phẩm tương đối ổn định | Năng lực hoàn thành có thể tăng hoặc giảm |
| Có ít công việc sự cố chen ngang | Phần năng lực dành cho backlog có thể bị thu hẹp |
| Story đã chia đủ nhỏ và đủ rõ | Tổng điểm có thể thay đổi sau refinement |
| Definition of Done được duy trì | Bỏ kiểm thử làm chỉ số tăng nhưng chất lượng giảm |
| Phụ thuộc bên ngoài sẵn sàng | Việc đang làm có thể phải chờ lâu hơn dự kiến |

Một dự báo hữu ích nên có **phạm vi, mốc dữ liệu, giả định, mức bất định và thời điểm cập nhật**. Nếu muốn ước lượng xác suất đáng tin hơn, nhóm cần nhiều dữ liệu thực tế hơn và phương pháp phù hợp, không chỉ lấy ba Sprint gần nhất rồi thêm một phần trăm tùy ý.

### Các hạng mục chưa đạt DoD được tính thế nào?

Không nên tính một phần điểm của story chưa hoàn thành như đã có Increment hoàn chỉnh, chỉ vì “đã viết xong 80% mã”. Nếu cần cải thiện khả năng dự báo, hãy chia các hạng mục quá lớn trước khi làm, theo dõi công việc đang tiến triển và đánh giá thời gian bị chặn. Việc đếm điểm hoàn thành cần dùng **một quy ước nhất quán**.

## 11. Khi dữ liệu dòng công việc hữu ích hơn điểm

Story point là **công cụ tùy chọn**, không phải yêu cầu của Agile. Trong một số bối cảnh, nhóm có thể dự báo tốt hơn bằng những phép đo:

| Chỉ số | Diễn giải | Lưu ý |
| --- | --- | --- |
| **Throughput** | Số hạng mục hoàn thành mỗi khoảng thời gian theo quy ước | Hữu ích khi các hạng mục được chia tương đối nhỏ và ổn định |
| **Cycle time** | Thời gian từ khi bắt đầu thực hiện đến khi hoàn thành | Cần thống nhất điểm bắt đầu và kết thúc |
| **Lead time** | Thời gian từ mốc tiếp nhận đến khi bàn giao | Có thể bao gồm thời gian chờ trước khi bắt đầu |
| **WIP** | Số hạng mục đang làm cùng lúc | Quá nhiều WIP có thể khiến mọi việc chậm đi |
| **Thời gian bị chặn** | Khoảng hạng mục không tiến triển vì phụ thuộc hoặc quyết định | Giúp tìm nút thắt mà điểm không phản ánh đầy đủ |

Trong Kanban, một nhóm xử lý nhiều yêu cầu nhỏ, tương đối đồng đều có thể dùng phân phối cycle time và throughput để dự báo. Nếu hệ thống có nhiều hạng mục khác kích thước, việc chia nhỏ hoặc phân loại hạng mục có thể hữu ích hơn một quy trình chấm điểm nặng nề.

**Lựa chọn phương pháp dự báo nên dựa trên việc nó có giúp ra quyết định tốt hơn hay không**, không dựa trên việc công cụ nào được xem là “Agile hơn”.

## 12. Story point trong Scrum, Kanban và XP

### Scrum: hỗ trợ Sprint Planning, không thay Sprint Goal

Trong Scrum, **Product Owner** chịu trách nhiệm quản lý và sắp thứ tự Product Backlog nhằm tối đa hóa giá trị sản phẩm; **Developers** chọn Product Backlog Item cho Sprint thông qua trao đổi với Product Owner và lập kế hoạch công việc. Story point, nếu nhóm dùng, là một nguồn thông tin khi thảo luận năng lực và kích thước.

**Sprint Goal** vẫn là mục đích chung của Sprint, không phải một chỉ tiêu điểm phải đạt. Nếu bất định mới xuất hiện, Developers có thể thương lượng phạm vi với Product Owner để giữ Sprint Goal không bị ảnh hưởng. Không nên ép nhóm nhận thêm điểm vượt khả năng bằng cách hạ tiêu chuẩn Definition of Done.

### Kanban: so sánh kích thước và kiểm soát luồng

Kanban tập trung làm rõ workflow, giới hạn WIP và quản lý dòng công việc. Một đội Kanban có thể dùng story point nếu điều đó hỗ trợ lựa chọn công việc, nhưng cũng có thể không ước lượng điểm mà dự báo bằng lịch sử công việc hoàn thành.

Điều quan trọng là **công việc nhỏ, rõ, có thể kéo qua các bước và tạo phản hồi**, chứ không phải trên bảng bắt buộc có cột điểm.

### XP: tăng độ tin cậy của phản hồi kỹ thuật

Các thực hành của **Extreme Programming (XP)** như TDD, lập trình cặp, tích hợp liên tục và tái cấu trúc có thể giúp nhóm phát hiện vấn đề gần lúc viết mã và giảm rủi ro tích hợp. Nhờ đó, ước lượng các thay đổi tương tự trong tương lai có thể dễ hơn.

Tuy nhiên, việc có thêm kiểm thử hoặc kinh nghiệm **không tự động khiến mọi story còn lại phải giảm một nửa điểm**. Nhóm cần xem thay đổi kỹ thuật đã thực sự ảnh hưởng phạm vi và mức độ khó của hạng mục nào.

## 13. Những phản mẫu khi sử dụng story point

| Phản mẫu | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| “1 điểm = 8 giờ” | Biến điểm thành giờ công trá hình | Dùng điểm để so sánh tương đối; dự báo thời gian bằng dữ liệu thực |
| So điểm giữa các cá nhân | Khuyến khích cạnh tranh và làm đẹp số liệu | Đánh giá sự phối hợp, chất lượng và kết quả chung |
| So velocity giữa các đội | Thang mốc không giống nhau | Không dùng điểm như thước đo chuẩn liên đội |
| Hễ story không rõ thì chấm thêm 8 điểm | Che giấu điều chưa biết | Tách story, xác nhận phạm vi hoặc thực hiện spike |
| Chấm điểm bằng tên tính năng | Bỏ qua quy tắc, phụ thuộc và tiêu chí chấp nhận | Hỏi về hành vi và so sánh với mốc có ranh giới rõ |
| Lấy trung bình các phiếu Planning Poker bất đồng | Không giải quyết khác biệt về giả định | Hỏi người chọn cao và thấp nhất về phạm vi |
| Đổi điểm quá khứ để khớp thời gian thực tế | Dữ liệu lịch sử bị bóp méo | Giữ lịch sử, ghi nguyên nhân sai lệch |
| Ép làm nhiều điểm bằng cách bỏ kiểm thử | Velocity tăng nhưng chất lượng giảm | Duy trì Definition of Done và chỉ số bảo vệ |
| Coi điểm lớn là giá trị lớn | Sản phẩm có thể nhiều đầu ra nhưng không tạo outcome | Ưu tiên theo Product Goal và bằng chứng người dùng |
| Họp ước lượng quá lâu cho khác biệt nhỏ | Tốn chi phí ra quyết định | Dừng khi đã đủ hiểu để chọn bước tiếp theo |
| Dùng điểm để hứa ngày chính xác | Bỏ qua biến động và công việc mới | Dự báo theo khoảng, nêu giả định và cập nhật |

### Nhận biết khi nên bỏ hoặc đơn giản hóa điểm

Nếu nhóm mất nhiều thời gian chấm điểm nhưng dự báo không tốt hơn, backlog vẫn quá lớn hoặc người dùng vẫn nhận phản hồi chậm, hãy xem lại quy trình. Có thể giữ một vài mốc để làm rõ phạm vi, chuyển sang đo throughput/cycle time hoặc chỉ phân loại story nhỏ/vừa/lớn.

**Agile quan tâm khả năng thích ứng và tạo giá trị**, không phải duy trì một nghi thức ước lượng bằng mọi giá.

## 14. Bài thực hành: xây mốc và ước lượng cho nhóm

**Bối cảnh:** Một nền tảng học trực tuyến có chức năng đăng nhập, danh sách bài học và API tiến độ cơ bản. Product Goal là giúp người mới bắt đầu và hoàn thành bài học đầu tiên đáng tin cậy.

### Nhiệm vụ A — Chọn mốc tham chiếu

Nhóm chọn ba mốc:

| Mốc | Hạng mục | Điểm minh họa |
| --- | --- | ---: |
| **R1** | Hiển thị thông báo lưu thành công/thất bại dựa trên API hiện có | 1 |
| **R2** | Hiển thị tiến độ sau mỗi bước, có kiểm thử tải lại trang | 3 |
| **R3** | Khôi phục vị trí đã lưu trên một thiết bị khi quay lại | 5 |

Hãy bổ sung cho từng mốc: **phạm vi bao gồm, loại trừ, tiêu chí chấp nhận, cách kiểm thử và rủi ro đã biết**. Người học có thể chọn mốc khác nếu có ngữ cảnh hợp lý, miễn nhất quán.

### Nhiệm vụ B — Ước lượng bốn story mới

| Story | Câu hỏi nên trao đổi trước khi chọn điểm |
| --- | --- |
| **S1:** Lọc danh sách bài theo trạng thái học | Dữ liệu có sẵn không? “Đang học” có nghĩa gì? |
| **S2:** Thông báo khi tiến độ chưa được lưu do mất mạng | Giao diện có trạng thái chờ chưa? Có retry trong phạm vi không? |
| **S3:** Xem tiến độ đã đồng bộ trên thiết bị thứ hai | Quy tắc dữ liệu cũ/mới và cạnh tranh cập nhật là gì? |
| **S4:** Xem video offline và đồng bộ tiến độ sau nhiều ngày | Có giới hạn bản quyền, dung lượng, quyền truy cập và xung đột không? |

**Gợi ý giải có điều kiện:** S1 có thể gần 2–3 điểm khi dữ liệu sẵn. S2 có thể gần 3–5 nếu gồm xử lý lỗi. S3 có thể gần mốc 8 hoặc cần chia theo quy tắc đồng bộ. S4 chưa đủ rõ để gán số tin cậy; có thể làm spike hoặc tách lát cắt.

Những mức này **không phải đáp án đúng cho mọi đội**. Điều cần đánh giá là lý do so sánh và khả năng làm rõ bất định.

### Nhiệm vụ C — Thử một vòng Planning Poker

Ba thành viên đưa ra cho S3:

~~~text
Người A: 3 điểm — chỉ nghĩ tới việc đọc tiến độ đã lưu.
Người B: 5 điểm — tính cả luồng đồng bộ và kiểm thử tích hợp.
Người C: 13 điểm — tính cả offline và xử lý xung đột phức tạp.
~~~

Hãy đóng vai nhóm, lần lượt:

1. Xác định mỗi người đang hình dung những hành vi nào.
2. Hỏi người hiểu nghiệp vụ quy tắc nào là bắt buộc ở lát cắt đầu.
3. Tách yêu cầu offline nếu chưa cần ngay.
4. Chọn tham chiếu phù hợp và đánh giá lại.
5. Ghi câu hỏi chưa rõ và người chịu trách nhiệm tìm câu trả lời.

**Mục tiêu** không phải mọi người lập tức chọn cùng con số mà là cùng hiểu **phần sản phẩm có thể kiểm chứng và hoàn thành**.

### Nhiệm vụ D — Dự báo có điều kiện

Nhóm có kết quả ba Sprint gần nhất: **18, 21, 23 điểm**, backlog đang xét còn **34 điểm**.

1. Tính mức trung bình điểm hoàn thành một Sprint.
2. Tính số Sprint theo phép chia thô.
3. Nêu ít nhất ba giả định có thể khiến dự báo thay đổi.
4. Đề xuất cách truyền đạt dự báo với stakeholder để không biến nó thành lời hứa ngày cố định.
5. Cho biết dữ liệu cần quan sát sau Sprint tiếp theo để hiệu chỉnh dự báo.

**Gợi ý:** Trung bình khoảng 20,7 điểm/Sprint; phép chia thô khoảng 1,64 Sprint. Có thể trình bày dự báo sơ bộ hai đến ba Sprint kèm rủi ro và điều kiện, rồi xem lại phạm vi và năng lực thực tế. Không được rút ngắn kiểm thử chỉ để đạt con số.

## 15. Checklist dùng story point có trách nhiệm

- [ ] Story có **người hưởng lợi hoặc giá trị giảm rủi ro** rõ ràng.
- [ ] Phạm vi bao gồm, loại trừ và tiêu chí chấp nhận đủ rõ để trao đổi.
- [ ] Nhóm có **hạng mục tham chiếu** phù hợp, đã ghi ranh giới.
- [ ] Các thành viên sử dụng **một thang điểm nhất quán**.
- [ ] Những bất đồng lớn được thảo luận theo **giả định và rủi ro**, không theo chức danh.
- [ ] Story quá lớn được cân nhắc **chia lát cắt** hoặc làm spike trước.
- [ ] Điểm không được quy đổi cứng sang giờ và không dùng làm **KPI cá nhân**.
- [ ] Dự báo sử dụng **dữ liệu hoàn thành theo Definition of Done** và nêu giả định.
- [ ] Nhóm duy trì chất lượng và xem xét **outcome người dùng**, không chỉ velocity.
- [ ] Có kế hoạch xem lại mức độ hữu ích của cách ước lượng sau vài vòng.

Checklist là lời nhắc cho cuộc trao đổi, không phải một cổng phê duyệt cứng. Nếu một hạng mục có giá trị nhưng chưa thể ước lượng, bước hợp lý có thể là **làm rõ và giảm bất định**, không phải bỏ nó khỏi Product Backlog.

## 16. Câu hỏi ôn tập

1. Ước lượng tương đối khác ước lượng giờ công ở điểm nào?
2. Story point thường cân nhắc những loại yếu tố gì và tại sao không tương đương số ngày?
3. Một hạng mục tham chiếu tốt cần những thông tin gì ngoài tên và điểm?
4. Vì sao một story 5 điểm ở nhóm A có thể khác story 5 điểm ở nhóm B?
5. Khi Planning Poker cho kết quả 3, 5, 13, nhóm nên thảo luận điều gì trước khi chốt?
6. Vì sao chia theo database, API, UI chưa chắc tạo ra các user story tốt?
7. Khi chưa biết cách xử lý xung đột offline, nhóm nên chấm điểm dự phòng hay kiểm chứng trước?
8. Story point hỗ trợ sắp thứ tự Product Backlog nhưng vì sao không quyết định thứ tự?
9. Velocity dùng để dự báo có những giả định và giới hạn gì?
10. Một story chưa đạt Definition of Done có nên được tính một phần điểm hoàn thành không?
11. Khi nào dùng throughput hoặc cycle time phù hợp hơn việc chấm story point?
12. Scrum có bắt buộc story point hoặc Planning Poker không?
13. Điều gì cho thấy ước lượng tương đối đã giúp nhóm **nhận phản hồi sớm và bàn giao giá trị tốt hơn**?

**Ghi nhớ:** **Story point** là đơn vị quy ước giúp nhóm so sánh kích thước công việc; **hạng mục tham chiếu** làm cho quy ước ấy trở nên cụ thể bằng những ví dụ đã hiểu rõ phạm vi, rủi ro và chất lượng. Giá trị của ước lượng tương đối nằm ở **việc tạo cách hiểu chung, phát hiện bất định và chia công việc thành phần có thể bàn giao**, không nằm ở việc chấm thật nhiều điểm. Hãy dự báo bằng dữ liệu hoàn thành, công khai các giả định và liên tục đối chiếu với kết quả người dùng để Agile vẫn tập trung vào giá trị thay vì những con số.
