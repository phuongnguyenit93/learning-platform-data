# Kiểm soát công việc đang thực hiện bằng giới hạn WIP

> **Thông điệp chính:** Trong Kanban, giới hạn **Work in Progress (WIP)** giúp nhóm ngừng bắt đầu quá nhiều việc và tập trung **hoàn tất những gì đã bắt đầu**. WIP limit không phải chỉ tiêu khiến mọi người bận 100%, cũng không phải con số thần kỳ làm năng suất tăng ngay. Đó là một **chính sách quản lý dòng công việc**: công việc mới chỉ được kéo vào khi có năng lực thực tế, các điểm tắc được bộc lộ và nhóm cùng tìm cách cải thiện thời gian đưa giá trị tới người dùng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **WIP**, **WIP limit**, **backlog**, **throughput**, **cycle time**, **work item age** và **lead time**.
2. Giải thích vì sao quá nhiều công việc đang thực hiện có thể làm tăng chuyển ngữ cảnh, thời gian chờ và nguy cơ giao hàng muộn.
3. Thiết lập giới hạn WIP cho **toàn workflow**, một hoặc nhiều trạng thái, và viết chính sách **kéo việc (pull)** rõ ràng.
4. Xử lý tình huống cột đã đầy, công việc bị chặn, lỗi khẩn cấp hoặc nhu cầu phối hợp với chuyên gia mà không tùy tiện vượt giới hạn.
5. Dùng bốn phép đo dòng công việc của Kanban để quan sát tác động, không biến số liệu thành công cụ đánh giá năng suất cá nhân.
6. Hiểu trực giác của **Little's Law** và giới hạn áp dụng khi dòng công việc biến động.
7. Kết hợp giới hạn WIP với Scrum, kỹ thuật XP và phản hồi sản phẩm để giao phần mềm tăng dần, có chất lượng.
8. Thực hành cải tiến một workflow thật bằng thử nghiệm nhỏ, có giả thuyết, cách đo và điểm đánh giá lại.

## 2. Câu chuyện mở đầu: ai cũng bận, ít việc thật sự xong

Một đội phát triển nền tảng học trực tuyến có năm Developers. Đầu mỗi tuần, đội thường mở thêm nhiều PBI: đăng ký tài khoản, gửi email kích hoạt, lưu tiến độ, trang tìm khóa học, tối ưu hình ảnh và sửa lỗi thanh toán.

Tình hình giữa tuần:

- Có **12 PBI đang thực hiện** nhưng chỉ hai PBI thực sự hoàn thành từ đầu đến cuối.
- Công việc chờ review mã lâu vì người review cũng đang viết tính năng khác.
- Tester chỉ nhận một loạt thay đổi vào gần cuối tuần.
- Một lỗi lưu tiến độ nghiêm trọng vẫn nằm trong trạng thái “Đang làm”, dù chưa có ai xử lý tiếp.
- Dashboard cho thấy nhiều ticket có người được giao, nhưng Product Owner khó dự báo khi nào người học được dùng phần mềm đã tích hợp.

Vấn đề không nhất thiết là các thành viên thiếu năng lực. **Hệ thống làm việc có thể đang khuyến khích bắt đầu việc mới thay vì hoàn tất việc cũ.**

Nếu đội cứ giao thêm việc khi một người “rảnh ở bước của mình”, số hạng mục dở dang tăng. Chúng nằm chờ ở những chỗ khác nhau: thiết kế, review, kiểm thử, môi trường thử hoặc quyết định nghiệp vụ. Người dùng chỉ hưởng lợi khi một phần sản phẩm đạt chất lượng và có thể sử dụng.

Kanban giúp nhóm nhìn rõ vấn đề đó qua workflow và giới hạn WIP. Khi cột tiếp theo không nhận thêm được, câu hỏi không phải “Làm gì để vẫn trông bận?”, mà là:

> **“Chúng ta có thể giúp hoàn tất việc đang mở, tháo điểm nghẽn hoặc giảm công việc chờ ở đâu trước khi kéo thêm việc mới?”**

## 3. Khái niệm cốt lõi: WIP là gì?

**Work in Progress (WIP)** là số hạng mục **đã bắt đầu nhưng chưa hoàn thành**, theo điểm bắt đầu và kết thúc được quy định trong **Definition of Workflow (DoW)** của nhóm.

Ví dụ, nếu nhóm quy ước:

- **Bắt đầu:** khi PBI được kéo từ “Sẵn sàng” sang “Đang thực hiện”.
- **Hoàn thành:** khi PBI đã qua kiểm thử, tích hợp và đáp ứng Definition of Done (DoD) áp dụng.

Thì một PBI đang chờ review, một PBI bị chặn bởi API bên ngoài và một PBI đang kiểm thử **đều là WIP**, vì đã bắt đầu nhưng chưa Done.

### 3.1. Phân biệt các khái niệm dễ nhầm

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Backlog** | Các công việc đang được cân nhắc hoặc chuẩn bị, chưa nhất thiết được bắt đầu | 15 ý tưởng tính năng đang chờ ưu tiên |
| **WIP** | Các hạng mục đã bắt đầu nhưng chưa hoàn thành trong workflow được định nghĩa | 2 việc đang phát triển, 2 việc chờ review, 1 việc đang test |
| **WIP limit** | Chính sách giới hạn số hạng mục được phép đồng thời ở một phạm vi workflow | Toàn workflow tối đa 5 việc đang thực hiện |
| **Blocked item** | Hạng mục đang dở nhưng không thể tiến tiếp vì thiếu điều kiện | Chờ API đối tác; vẫn tính WIP nếu đã bắt đầu |
| **Throughput** | Số hạng mục hoàn thành trong một khoảng thời gian | 8 PBI đạt Done trong tuần |
| **Cycle time** | Thời gian từ lúc hạng mục bắt đầu đến lúc hoàn thành | PBI mất 6 ngày từ In Progress tới Done |
| **Work item age** | Thời gian đã trôi qua của hạng mục đang dở tính từ lúc bắt đầu | PBI đang mở 11 ngày, chưa Done |
| **Lead time** | Thời gian chờ từ một mốc yêu cầu/tiếp nhận được định nghĩa tới hoàn thành | Người yêu cầu chờ 14 ngày từ khi yêu cầu được nhận |

**Lưu ý về lead time:** tổ chức có thể dùng các mốc bắt đầu khác nhau. Khi so sánh dữ liệu, phải nêu rõ cách định nghĩa. Trong bốn phép đo nền tảng được **Kanban Guide** nêu, trọng tâm là **WIP, throughput, work item age và cycle time**.

### 3.2. Giới hạn WIP áp vào đâu?

Không có quy định mọi nhóm đều phải dùng “WIP = số người” hoặc mỗi cột đều phải có giới hạn hai việc.

Nhóm có thể đặt giới hạn cho:

- **Toàn hệ thống:** tối đa năm hạng mục đã bắt đầu nhưng chưa hoàn thành.
- **Một trạng thái:** ví dụ cột “Review” có tối đa hai hạng mục.
- **Một nhóm trạng thái:** ví dụ tổng “Đang phát triển + Chờ review” không quá bốn.
- **Một loại công việc hoặc chính sách luồng:** nếu thật sự có lý do để tách, như công việc vận hành khẩn cấp.

Điều quan trọng là chính sách **rõ, dễ quan sát, được thực thi và có thể điều chỉnh dựa trên dữ liệu**.

### 3.3. WIP limit khác giới hạn backlog

Nếu Product Backlog có 80 PBI còn workflow đang thực hiện có WIP limit = 5, điều đó **không có nghĩa backlog chỉ được có năm việc**. Nó nghĩa là chỉ tối đa năm hạng mục nằm trong phạm vi đã bắt đầu tới chưa hoàn thành theo quy tắc nhóm.

Tương tự, hạng mục đang “Sẵn sàng” thường chưa tính WIP nếu nhóm định nghĩa điểm bắt đầu sau trạng thái đó. Cách vẽ cột trên bảng phải khớp với **định nghĩa bắt đầu/kết thúc thật**, không dựa vào màu sắc hoặc tên cột tùy ý.

## 4. Vì sao hạn chế công việc dở dang có thể giúp dòng công việc tốt hơn?

### 4.1. Chi phí chuyển ngữ cảnh

Khi một Developer phải luân phiên sửa lỗi thanh toán, tích hợp API, trả lời review và viết tính năng mới, mỗi lần chuyển việc có thể cần thời gian nhớ lại bối cảnh, khôi phục môi trường và tái kiểm tra giả định.

Giảm WIP giúp đội có điều kiện hoàn tất một lát cắt trước khi mở thêm lát cắt khác. Điều này không loại bỏ mọi sự gián đoạn, nhưng làm **chi phí việc dở dang** dễ nhìn hơn.

### 4.2. Công việc chờ không tạo giá trị sử dụng

Một tính năng đã viết code nhưng chưa review và kiểm thử có thể chưa tạo thành Increment đạt DoD. Nó tiêu tốn vốn thời gian và sự chú ý, đồng thời có nguy cơ lỗi thời nếu yêu cầu thay đổi.

WIP limit khuyến khích nhóm hỏi: “Có ai hỗ trợ review/test để đưa hạng mục tới Done không?” thay vì tự động mở thêm một PBI.

### 4.3. Phát hiện điểm nghẽn thay vì che giấu

Nếu “Kiểm thử” thường đầy trong khi “Phát triển” liên tục có việc mới, vấn đề có thể là:

- PBI được chuyển sang kiểm thử quá muộn hoặc quá lớn.
- Tester phụ thuộc môi trường chưa sẵn sàng.
- Các tiêu chí chấp nhận thiếu rõ, gây hỏi lại và làm lại.
- Tự động hóa kiểm thử chưa phù hợp, lỗi hồi quy xuất hiện muộn.

Một giới hạn WIP không **tự sửa** những vấn đề này; nó khiến sự tắc nghẽn rõ đến mức nhóm cần phối hợp giải quyết.

### 4.4. Rút ngắn vòng phản hồi

Người dùng nhận giá trị từ tính năng **đã hoàn thành và có thể dùng**, không phải từ số ticket đang hoạt động. Bằng cách hỗ trợ hoàn tất nhanh hơn, giới hạn WIP có thể giúp đưa Increment tới kiểm chứng sớm hơn, rút ngắn thời gian giữa ý tưởng và phản hồi.

**Không nên khẳng định:** cứ giảm WIP một nửa thì tốc độ giao sản phẩm sẽ tăng gấp đôi. Nếu giới hạn quá thấp trong khi phụ thuộc không thay đổi, throughput thậm chí có thể giảm. Chính sách cần được thử và đánh giá trong bối cảnh cụ thể.

## 5. Từ bảng trực quan tới hệ thống kéo công việc

Một bảng có cột “To do – Doing – Done” **chưa đủ để gọi là quản lý WIP hiệu quả**. Nhóm cần thỏa thuận cách công việc di chuyển và điều kiện được bắt đầu.

### 5.1. Ví dụ workflow có giới hạn

~~~text
Product Backlog
      |
      v
Sẵn sàng (chưa bắt đầu, không tính WIP)
      |
      | KÉO KHI CÓ CHỖ TRỐNG
      v
Đang phát triển (limit 3) --> Review (limit 2) --> Kiểm thử (limit 2)
        \____________________  Tổng WIP <= 5  _________________/
                                               |
                                               v
                                      Done (đã đạt DoD)
~~~

Trong ví dụ này:

- **Giới hạn toàn workflow = 5:** tổng hạng mục trong ba trạng thái hoạt động không vượt năm.
- **Giới hạn từng trạng thái:** “Phát triển” tối đa ba, “Review” hai, “Kiểm thử” hai.
- **Sẵn sàng và Done** nằm ngoài phạm vi WIP, theo quy ước điểm bắt đầu/kết thúc đã nêu.
- Các mức giới hạn chỉ là **giả định minh họa**, không phải chuẩn áp cho mọi Scrum Team hoặc đội Kanban.

Giả sử hiện tại có **2 việc Đang phát triển + 2 việc Review + 1 việc Kiểm thử = 5 WIP**. Dù “Phát triển” còn một chỗ theo giới hạn cột, giới hạn tổng đã đầy. Nhóm **không kéo thêm PBI mới** cho đến khi có việc đạt Done hoặc có thay đổi chính sách hợp lệ.

Nếu một việc Review chuyển sang Kiểm thử, tổng WIP vẫn là năm: đó là **dịch chuyển việc đang làm**, chưa tạo chỗ để bắt đầu việc mới. Nếu một việc Kiểm thử đạt Done, tổng WIP giảm còn bốn; lúc đó có thể cân nhắc kéo thêm một việc phù hợp.

### 5.2. “Pull” và “push” khác nhau ở đâu?

**Push:** khi một cá nhân hoặc bộ phận xong bước của mình, họ tự đưa thêm việc sang bộ phận sau, bất kể nơi nhận còn năng lực hay không. Hệ quả thường là hàng đợi và WIP tăng.

**Pull:** nơi thực hiện bước tiếp theo chỉ nhận việc khi có năng lực trong giới hạn và thỏa mãn chính sách chuyển trạng thái. Khi chưa có chỗ, nhóm ưu tiên phối hợp để hoàn tất việc hiện có.

Ví dụ:

| Tình huống | Cách push không kiểm soát | Cách pull có chính sách |
|---|---|---|
| Cột Review đã đầy | Developer đẩy thêm PR vào hàng chờ không giới hạn | Developer hỗ trợ xử lý review tồn đọng hoặc công việc đã bắt đầu khác |
| Tester chưa có môi trường | Mọi story cứ chuyển sang “Testing” | Làm rõ blocker, phối hợp chuẩn bị môi trường, không giả vờ việc đang tiến triển |
| Một Developer hoàn tất bước của mình | Bắt đầu ngay story mới dù hệ thống đủ WIP | Hỏi chỗ nào trong workflow đang cần giúp để hoàn thành việc cũ |
| Có lỗi nghiêm trọng đang gây tác động | Chen ngang không ghi dấu vết | Kích hoạt chính sách khẩn cấp, làm rõ việc bị thay thế và hậu kiểm |

Pull không phải quy tắc “không ai được giúp nhau nếu không thuộc chuyên môn của mình”. Ngược lại, nó khuyến khích phối hợp vượt ranh giới chức danh để **hoàn tất công việc**.

### 5.3. Định nghĩa trạng thái thật rõ

Mỗi trạng thái cần mô tả:

- Khi nào một hạng mục **được vào** trạng thái đó.
- Điều kiện nào khiến nó **được ra** trạng thái đó.
- Ai hoặc nhóm nào có thể thực hiện bước tiếp theo.
- Trường hợp bị chặn được hiển thị và xử lý như thế nào.
- Hạng mục được tính WIP trong trạng thái ấy hay không.

Không nhất thiết phải có các cột “Phát triển, Review, Test”. Workflow của nhóm hỗ trợ vận hành, nghiên cứu UX hay phát triển phần cứng sẽ khác. Điểm quan trọng là **bảng thể hiện dòng công việc thật**, không chỉ sơ đồ lý tưởng trên slide.

## 6. Definition of Workflow và giới hạn WIP

Theo **Kanban Guide**, cần định nghĩa rõ **Definition of Workflow (DoW)** để quản lý và cải thiện dòng công việc. Một DoW tối thiểu mô tả:

1. **Các loại công việc** cần theo dõi.
2. **Điểm bắt đầu và điểm kết thúc** của workflow.
3. **Những trạng thái** một hạng mục đi qua từ bắt đầu tới kết thúc.
4. **Cách kiểm soát WIP** từ bắt đầu tới kết thúc.
5. **Các chính sách rõ ràng** để công việc được chuyển qua các trạng thái.
6. **Service Level Expectation (SLE)**: kỳ vọng thời gian hoàn thành theo một mức xác suất/khả năng, khi có căn cứ phù hợp.

Những mục này hỗ trợ nhau. Nếu nhóm chỉ viết “WIP limit = 5” nhưng không thống nhất khi nào công việc bắt đầu, kết thúc hoặc bị xem là Done, số đếm WIP sẽ không đáng tin.

### 6.1. Mẫu Definition of Workflow gọn

~~~yaml
workflow: "Phát triển một lát cắt sản phẩm"
work_items:
  - "Product Backlog Item đủ rõ để thực hiện"
started_at: "Kéo từ Sẵn sàng sang Đang phát triển"
finished_at: "Đạt Done theo chính sách chất lượng áp dụng"
states:
  - "Đang phát triển"
  - "Review"
  - "Kiểm thử"
control_wip:
  total_active: 5
  development: 3
  review: 2
  testing: 2
explicit_policies:
  - "Chỉ kéo PBI mới khi tổng WIP còn chỗ"
  - "Không bỏ qua tiêu chí chuyển cột để làm đẹp số liệu"
  - "Việc blocked vẫn tính WIP và phải có hướng tháo gỡ"
  - "Xử lý việc khẩn theo chính sách ngoại lệ đã thỏa thuận"
sle:
  statement: "Dùng dữ liệu cycle time quan sát để thống nhất kỳ vọng"
  note: "Chưa áp một con số SLE trước khi có dữ liệu phù hợp"
~~~

Đây là **mẫu minh họa**, không phải cấu trúc YAML mà Kanban bắt buộc. Đừng tạo thêm một file cấu hình nếu nhóm chỉ cần các chính sách ngắn ngay trên bảng.

### 6.2. WIP limit không chỉ là một số trên tiêu đề cột

Giới hạn có ý nghĩa nếu mọi người biết **phải làm gì khi chạm giới hạn**. Một chính sách rõ có thể nêu:

> “Khi tổng WIP đạt năm, nhóm không kéo PBI mới. Ưu tiên hoàn tất việc gần Done, xử lý blocker và hỗ trợ các trạng thái đang tắc. Trường hợp khẩn cấp cần được chỉ ra công khai cùng việc nào phải tạm dừng; nhóm xem lại ngoại lệ sau đó.”

Nếu mọi người thường xuyên vượt limit nhưng không ghi nhận và không điều chỉnh cách làm, con số chỉ là **trang trí trên dashboard**.

## 7. Chọn giới hạn WIP ban đầu như thế nào?

Không có công thức chung phù hợp mọi đội. Cách thực dụng là **quan sát dòng công việc hiện có, đặt một giới hạn đủ tạo sự tập trung nhưng vẫn khả thi, rồi cải tiến bằng dữ liệu**.

### 7.1. Khảo sát trước khi đặt số

Nhóm nên biết:

- Hiện có bao nhiêu hạng mục đã bắt đầu nhưng chưa hoàn thành?
- Công việc thường chờ ở trạng thái nào lâu nhất?
- Có hạng mục quá lớn khiến nhóm không thể thấy tiến triển trong nhiều ngày không?
- Các kỹ năng có bị tập trung ở một người review, QA hoặc vận hành không?
- Đâu là công việc khẩn cấp thực sự, và tần suất chen ngang hiện tại?
- Định nghĩa Done và nguồn dữ liệu lịch sử có nhất quán không?

Ví dụ, nếu đội năm Developers đang mở 12 việc và nhiều việc chờ review, giảm ngay xuống WIP = 1 có thể làm workflow tê liệt. Nhóm có thể thử giới hạn tổng ở mức thấp hơn hiện tại nhưng vẫn đủ để vận hành, rồi theo dõi **throughput và cycle time** sau vài vòng.

### 7.2. Cách thiết kế một thử nghiệm có trách nhiệm

| Bước | Câu hỏi | Ví dụ |
|---|---|---|
| **Quan sát nền** | WIP, thời gian chờ và loại công việc đang như thế nào? | 12 việc mở; review chờ lâu; nhiều việc dồn test cuối tuần |
| **Đặt giả thuyết** | Giảm WIP sẽ giúp cải thiện điều gì? | Ít chuyển ngữ cảnh hơn, review sớm hơn, giảm work item age |
| **Chọn phạm vi thử** | Giới hạn nào có thể áp dụng mà không tạo rủi ro không cần? | Thử total WIP = 6 trong một giai đoạn; chỉnh theo quan sát |
| **Viết chính sách** | Khi đầy thì kéo việc/giải quyết blocker thế nào? | Không kéo việc mới, hỗ trợ công việc gần Done |
| **Chọn phép đo** | Điều gì chứng minh cải thiện, điều gì báo tác dụng phụ? | Cycle time, throughput, tuổi việc mở, lỗi sau phát hành |
| **Đánh giá** | Giới hạn có giúp hoàn thành việc hơn không? | Giữ, tăng, giảm hoặc sửa chính sách theo bằng chứng |

Con số **6** ở đây chỉ là giả định minh họa. Không nên sao chép thành “quy tắc Kanban cho đội năm người”.

### 7.3. Phân biệt giới hạn trạng thái và giới hạn hệ thống

Nếu giới hạn mỗi cột là ba nhưng toàn hệ thống có năm cột, tổng WIP có thể vẫn cao. Ngược lại, giới hạn tổng quá thấp có thể khiến một khâu không có việc để làm khi hạng mục khác chờ một phụ thuộc không thể hỗ trợ.

Vì vậy:

1. Nhìn **toàn dòng**, không chỉ năng suất từng cột.
2. Dùng giới hạn trạng thái để làm lộ điểm tắc.
3. Dùng giới hạn tổng để ngăn số việc dở dang tăng âm thầm.
4. Kiểm tra lại khi loại việc, năng lực hoặc phụ thuộc thay đổi.

### 7.4. Giảm WIP bằng cách hoàn tất, không bằng giấu việc

Không nên giảm số WIP bằng cách chuyển ticket bị chặn sang một cột “Chờ” nằm ngoài phạm vi tính WIP dù công việc đã bắt đầu và chưa hoàn tất. Cách đó chỉ làm con số đẹp hơn.

Nếu nhóm có **chính sách hủy hoặc dừng hẳn** công việc, cần ghi rõ điều kiện và ảnh hưởng. Một việc được quyết định **không tiếp tục** khác với việc **đã hoàn thành và tạo giá trị**; không gộp hai loại để tăng throughput giả.

## 8. Vận hành hằng ngày khi có giới hạn WIP

### 8.1. Xem bảng từ phải sang trái

Trong nhiều workflow, ưu tiên nhìn từ gần **Done** ngược về đầu dòng giúp nhóm tập trung hoàn tất:

1. Có việc ở **Kiểm thử/Review** đang chờ trợ giúp hoặc thông tin?
2. Có **blocked item** có thể tháo gỡ ngay không?
3. Một hạng mục **đang già đi** có nguy cơ trễ bất thường không?
4. Có điều kiện cần làm rõ để hạng mục đang mở đi tới Done?
5. Chỉ sau đó mới hỏi **có được kéo việc mới không**.

“Đi từ phải sang trái” là **heuristic vận hành hữu ích**, không phải một quy tắc máy móc phải áp dụng trong mọi tình huống. Sự cố đang gây mất dữ liệu hoặc nghĩa vụ khẩn cấp có thể cần cơ chế xử lý ưu tiên đã thỏa thuận.

### 8.2. Ví dụ buổi trao đổi về dòng công việc

~~~text
Tình trạng:
  Development: 2 / limit 3
  Review:      2 / limit 2
  Testing:     1 / limit 2
  Total WIP:   5 / limit 5

Nhận định:
  Review đầy, một PBI chờ hai ngày.
  Testing còn chỗ nhưng không thể nhận thêm nếu review chưa hoàn tất.

Hành động:
  - Developers phối hợp review PBI cũ nhất trước.
  - Làm rõ câu hỏi chưa trả lời ở một PR.
  - Không bắt đầu PBI mới dù Development chưa đầy.

Điều kiện kéo việc mới:
  Một hạng mục đạt Done, làm tổng WIP giảm xuống dưới 5,
  và công việc mới đáp ứng chính sách đầu vào đã thống nhất.
~~~

Lưu ý: WIP toàn hệ thống là **tổng số hạng mục đang mở**, không phải tổng giới hạn cột. Trong tình huống trên, hai việc Dev + hai việc Review + một việc Test = năm.

### 8.3. Quy tắc cho việc bị chặn

Một PBI bị chặn cần được **nhìn thấy**, không tự biến mất khỏi WIP. Với mỗi blocker, nhóm có thể ghi:

| Thuộc tính | Câu hỏi |
|---|---|
| **Nguyên nhân** | Chờ thông tin nghiệp vụ, API, quyền, môi trường hay lỗi kỹ thuật? |
| **Người/nhóm phối hợp** | Ai có thể giúp tháo, ai đang liên hệ? |
| **Mốc bắt đầu bị chặn** | Đã chờ bao lâu? |
| **Tác động** | Cản việc nào khác, tác động người dùng hoặc Sprint Goal ra sao? |
| **Bước tiếp theo** | Làm gì, ai làm và khi nào cần xem lại? |

Nếu blocker không thể tháo ngay, nhóm có thể thay đổi kế hoạch hoặc dùng thời gian cho việc đang mở khác **trong giới hạn**. Không nhất thiết mọi thành viên phải ngồi chờ không làm gì, nhưng cũng không nên dùng blocker làm lý do mở công việc vô hạn.

### 8.4. Chính sách ngoại lệ với việc khẩn

Có thể có lỗi sản xuất nghiêm trọng, sự cố bảo mật hoặc nghĩa vụ phải đáp ứng ngay. Một chính sách ngoại lệ tốt cần:

- Nêu tiêu chí để một việc được xem là **khẩn cấp thật**.
- Làm rõ ai có quyền kích hoạt theo trách nhiệm sản phẩm/vận hành.
- Chỉ ra **việc nào bị tạm dừng hoặc thay thế**, thay vì cộng việc mới vô hình.
- Thể hiện việc khẩn trên bảng và vẫn theo dõi WIP, blockers.
- Xem lại tần suất ngoại lệ; nếu ngày nào cũng “khẩn”, chính sách cần sửa.

Ví dụ nhóm có thể dành **một vị trí được kiểm soát** cho sự cố hoặc chọn chính sách nâng ưu tiên khi cần. Không có một số slot khẩn cố định do Kanban Guide bắt buộc.

### 8.5. Kiểm soát WIP không đồng nghĩa tối đa hóa thời gian bận

Khi test hoặc review bị nghẽn, một Developer có thể:

- Hỗ trợ tái hiện và sửa lỗi từ việc đang mở.
- Tham gia review hoặc ghép đôi với người có kỹ năng phù hợp.
- Cải thiện kiểm thử tích hợp cho những PBI đang thực hiện.
- Làm rõ một phụ thuộc để việc khác được hoàn tất.
- Trao đổi kỹ năng để giảm nút cổ chai trong dài hạn.

Không ai bắt buộc phải thực hiện công việc vượt quá khả năng hoặc quyền hạn chuyên môn, đặc biệt trong an toàn thông tin. **Mục tiêu là tối ưu khả năng hoàn thành của toàn hệ thống, không tận dụng 100% từng cá nhân bằng mọi giá.**

## 9. Đo tác động của giới hạn WIP

### 9.1. Bốn phép đo dòng công việc căn bản

| Phép đo | Cách hiểu | Việc nhóm có thể làm |
|---|---|---|
| **WIP** | Có bao nhiêu việc đã bắt đầu mà chưa Done? | Phát hiện quá tải, kiểm tra chính sách kéo việc |
| **Throughput** | Hoàn thành bao nhiêu việc trong một khoảng thời gian? | Quan sát năng lực giao việc, hỗ trợ dự báo phạm vi |
| **Work item age** | Việc đang mở đã “già” bao lâu? | Ưu tiên kiểm tra hạng mục có nguy cơ tắc |
| **Cycle time** | Một việc đã Done mất bao lâu từ bắt đầu tới hoàn thành? | Hiểu thời gian dòng công việc và biến động |

Không dùng những phép đo này để kết luận **giá trị sản phẩm** hay **hiệu suất cá nhân**. Một nhóm đóng nhiều ticket nhỏ không nhất thiết giải quyết vấn đề quan trọng của người dùng.

### 9.2. Ví dụ tính WIP và throughput

Giả sử cuối ngày nhóm có:

| Trạng thái | Số hạng mục |
|---|---:|
| Sẵn sàng (chưa bắt đầu) | 9 |
| Đang phát triển | 2 |
| Review | 2 |
| Kiểm thử | 1 |
| Done | 18 |

Nếu Definition of Workflow xác định phạm vi WIP từ **Đang phát triển** đến **trước Done**, thì:

\[
\text{WIP} = 2 + 2 + 1 = 5.
\]

Không cộng chín việc “Sẵn sàng” hoặc 18 việc “Done”. Nếu trong tuần có **7 hạng mục mới đạt Done** theo quy tắc hoàn tất, throughput của tuần đó là **7 hạng mục/tuần**.

**Cẩn trọng:** ảnh chụp WIP tại một thời điểm không phải **WIP trung bình theo thời gian**; throughput một tuần có thể biến động mạnh. Không nên lấy một lần chụp để suy ra quy luật dài hạn.

### 9.3. Ví dụ cycle time và work item age

Giả sử ba PBI hoàn thành trong tuần có cycle time lần lượt **3, 6 và 9 ngày**. Trung bình mẫu:

\[
\overline{CT} = \frac{3 + 6 + 9}{3} = 6\ \text{ngày}.
\]

Nếu một PBI khác vẫn đang mở tới **ngày thứ 11**, work item age của nó là **11 ngày**, không có cycle time hoàn thành vì nó **chưa Done**.

PBI đang mở 11 ngày nên được kiểm tra xem có blocker hoặc phạm vi quá lớn không, đặc biệt khi đa số PBI cùng loại trước đây hoàn thành sớm hơn. Tuy nhiên, không được suy ra chắc chắn người phụ trách đã làm sai chỉ từ tuổi công việc.

### 9.4. Service Level Expectation (SLE)

**SLE** là kỳ vọng về thời gian hoàn thành một hạng mục **với mức xác suất hoặc khả năng cụ thể**, dựa trên dữ liệu hoặc giả định được nêu rõ.

Giả sử trong **20 hạng mục cùng loại** đã hoàn thành, **17 hạng mục mất không quá 8 ngày** từ bắt đầu đến Done. Nhóm có thể mô tả mức quan sát:

> “Trong mẫu này, 85% hạng mục hoàn tất trong tối đa 8 ngày.”

Đây có thể là đầu vào cho SLE, **không phải lời hứa mọi PBI đều xong trong tám ngày**. Mẫu 20 việc có giới hạn; nếu nhóm đổi loại công việc, Definition of Workflow hoặc cách tính thời gian, kỳ vọng phải được xem lại.

SLE cũng không thay thế việc kiểm tra work item age: một việc đang mở chín ngày đòi hỏi trao đổi về rủi ro và bước tiếp theo, chứ không chỉ tô màu đỏ trên bảng.

### 9.5. Giảm WIP thành công phải nhìn nhiều tín hiệu

Khi thử giới hạn mới, nên cùng xem:

- **Cycle time và phân bố cycle time:** việc hoàn tất nhanh hơn hay biến động ít hơn?
- **Throughput:** lượng việc đạt Done có giữ được hoặc cải thiện không?
- **Work item age:** có giảm số việc tồn đọng quá lâu không?
- **WIP và số lần vượt giới hạn:** chính sách có được áp dụng nhất quán không?
- **Lỗi sau phát hành và DoD:** có giảm chất lượng để đóng việc nhanh hơn không?
- **Outcome người dùng:** việc giao nhanh hơn có tạo giá trị sản phẩm thực không?
- **Sức khỏe phối hợp:** có tăng áp lực, chuyển ngữ cảnh hoặc tạo nút cổ chai mới không?

Không thể khẳng định giới hạn mới có lợi nếu chỉ thấy biểu đồ WIP giảm nhưng throughput sụt mạnh, số lỗi tăng hoặc người dùng vẫn không nhận được Increment có giá trị.

## 10. Little's Law: nhìn quan hệ giữa WIP, throughput và cycle time

### 10.1. Ý tưởng

Trong một hệ thống có điều kiện ổn định thích hợp, **Little's Law** liên hệ số việc trung bình trong hệ thống, tốc độ hoàn thành trung bình và thời gian tồn tại trung bình:

\[
\overline{WIP} \approx \lambda \times \overline{CT},
\]

trong đó:

- \(\overline{WIP}\) là **WIP trung bình theo thời gian** của cùng một workflow.
- \(\lambda\) là **tốc độ hoàn thành trung bình**, ví dụ hạng mục/tuần, trong điều kiện ổn định.
- \(\overline{CT}\) là **cycle time trung bình** theo tuần cho cùng loại công việc, cùng mốc bắt đầu/kết thúc.

Viết lại:

\[
\overline{CT} \approx \frac{\overline{WIP}}{\lambda}.
\]

Đây là mối quan hệ về dòng công việc ở **trạng thái ổn định với điều kiện phù hợp**, không phải công thức khiến việc giảm WIP tự động tăng throughput.

### 10.2. Ví dụ trực giác

Giả sử một workflow tương đối ổn định:

- Trung bình có **12 hạng mục đang thực hiện**.
- Trung bình hoàn thành **3 hạng mục/tuần**.

Khi điều kiện của Little's Law đủ phù hợp:

\[
\overline{CT} \approx \frac{12}{3} = 4\ \text{tuần}.
\]

Nếu nhóm giảm WIP trung bình xuống **6**, và **giả sử throughput thực tế vẫn là 3/tuần**, quan hệ tương ứng là:

\[
\overline{CT} \approx \frac{6}{3} = 2\ \text{tuần}.
\]

**Điều kiện “throughput không đổi” là giả định quan trọng**, không phải kết quả tất yếu khi giảm WIP. Nếu giới hạn quá thấp làm nhóm thường xuyên không có việc sẵn sàng hoặc cản tích hợp, throughput có thể giảm; cycle time lúc đó không tuân theo kịch bản mong muốn.

### 10.3. Khi nào không nên áp dụng máy móc?

Hãy thận trọng nếu:

- WIP được chụp vào một ngày còn throughput lấy trung bình cả quý.
- Cycle time đo từ khi code bắt đầu, nhưng WIP lại bao gồm hàng đợi trước code.
- Số hạng mục mới bắt đầu tăng nhanh và hệ thống chưa ổn định.
- Các PBI có độ lớn quá khác nhau, bị thay đổi cách chia liên tục.
- Nhiều hạng mục bị hủy hoặc loại khỏi thống kê không nhất quán.
- Tuần vừa qua có sự cố lớn, thay đổi nhân sự hoặc phụ thuộc chưa từng xuất hiện.

**Little's Law hữu ích để đặt câu hỏi về dòng công việc**, không bảo đảm dự báo cho một PBI riêng lẻ và không thay thế hiểu biết về biến động, chất lượng hay ưu tiên sản phẩm.

## 11. Tình huống xuyên suốt: đội phát triển chức năng lưu tiến độ học

### 11.1. Bối cảnh ban đầu

Một nhóm làm nền tảng học trực tuyến muốn cải thiện khả năng người dùng bắt đầu bài đầu và tiếp tục học mà không mất tiến độ. Product Owner ưu tiên các PBI: đăng ký, mở bài, lưu tiến độ, xử lý lỗi mạng và báo cáo trạng thái học.

Nhóm có năm Developers, phối hợp với Tester và đội vận hành; thành viên có thể đảm nhận nhiều loại công việc. Workflow ban đầu có các trạng thái “Sẵn sàng → Phát triển → Review → Kiểm thử → Done”.

Dữ liệu minh họa từ các tuần gần đây cho thấy:

| Quan sát | Tình trạng |
|---|---|
| WIP đang mở | Khoảng 12 PBI tại nhiều thời điểm |
| Throughput | Thường 3–5 PBI/tuần, biến động |
| Điểm chờ | Review và kiểm thử cuối kỳ |
| Work item age | Một số PBI mở hơn 14 ngày |
| Chất lượng | Lỗi lưu tiến độ phát hiện muộn |
| Kết quả sản phẩm | Người học phản ánh mất trạng thái sau khi đổi thiết bị |

**Giả thuyết của nhóm:** nhiều việc bắt đầu cùng lúc khiến review và kiểm thử bị dồn, làm chậm thời gian tạo Increment đáng tin.

### 11.2. Định nghĩa workflow và chính sách thử

Nhóm thống nhất:

- **Bắt đầu:** PBI được kéo từ Sẵn sàng vào Phát triển.
- **Hoàn thành:** tích hợp và đạt DoD, đưa vào Done.
- **Blocked item:** vẫn thuộc WIP, có nhãn, nguyên nhân và bước xử lý.
- **Giới hạn thử:** tổng WIP tối đa **6**, đồng thời giới hạn Review = **2**; các mức là giả định thực hành.
- **Pull policy:** chỉ kéo PBI mới khi tổng WIP còn chỗ và hạng mục được chọn đã đủ rõ.
- **Quy tắc khẩn:** lỗi đang gây mất dữ liệu được xử lý theo mức ảnh hưởng thực tế; thay đổi ưu tiên được minh bạch và có hậu kiểm.

Mục tiêu thử không phải bắt tất cả thành viên luôn có việc riêng, mà là **hoàn tất luồng người dùng và phát hiện lỗi sớm hơn**.

### 11.3. Ngày đầu áp dụng: cột Review đã đầy

Giả sử:

| Cột | Số hạng mục | Giới hạn |
|---|---:|---:|
| Phát triển | 3 | 3 |
| Review | 2 | 2 |
| Kiểm thử | 1 | 2 |
| **Tổng WIP** | **6** | **6** |

Một Developer hoàn tất bước code của PBI “Thông báo lưu thành công” và muốn nhận PBI mới. Nhưng Review đang đầy.

Nhóm quyết định:

1. Không kéo PBI mới chỉ vì một người đã xong phần code.
2. Phối hợp review PR cũ, giải quyết câu hỏi nghiệp vụ còn mở.
3. Nếu PR cũ đạt điều kiện review, kéo nó sang kiểm thử khi nơi nhận có chỗ.
4. Kiểm thử tích hợp và đưa một PBI đạt DoD sang Done trước khi nhận thêm công việc.

Điều này tránh tạo hàng đợi PR ngày càng dài. Nếu không thể chuyển việc vì cần chuyên môn còn thiếu, nhóm ghi rõ blocker và liên hệ người phù hợp.

### 11.4. Xuất hiện lỗi khẩn cấp

Trong khi thử, nhóm phát hiện có trường hợp giao diện báo “Đã lưu” dù backend chưa ghi tiến độ, khiến người học mất công sức. Đây có thể là **rủi ro chất lượng nghiêm trọng**, không nên để chờ chỉ vì hạn WIP đã đầy.

Nhóm có thể kích hoạt chính sách ưu tiên khẩn:

- Công khai ảnh hưởng người dùng và phạm vi lỗi.
- Product Owner và Developers phối hợp quyết định thứ tự công việc theo trách nhiệm; người có thẩm quyền về ứng cứu/bảo mật tham gia khi cần.
- Tạm dừng hoặc giảm ưu tiên một PBI ít cấp thiết thay vì cộng thêm công việc vô hạn.
- Kiểm thử sửa lỗi, theo dõi tác động và giữ DoD.
- Sau xử lý, xem vì sao lỗi bị phát hiện muộn và chính sách WIP có cần điều chỉnh không.

**WIP limit không phải lý do trì hoãn ứng cứu sự cố.** Cũng không nên để mọi yêu cầu nhỏ được gắn nhãn khẩn để vượt limit theo sở thích.

### 11.5. Đo kết quả sau thử nghiệm

Giả sử nhóm áp dụng trong ba tuần; số liệu sau **chỉ là ví dụ minh họa**, không phải kết quả được bảo đảm:

| Tín hiệu | Trước thử | Trong giai đoạn thử | Cần giải thích thêm |
|---|---:|---:|---|
| WIP trung bình | Khoảng 12 | Khoảng 6 | Cách tính và loại việc có giữ nhất quán? |
| Throughput trung bình/tuần | 4 | 4 | Chưa thấy tăng lượng Done, nhưng cũng chưa giảm |
| Cycle time trung bình | Khoảng 3 tuần | Khoảng 1,5 tuần | Phù hợp trực giác dòng ổn định; mẫu nhỏ cần kiểm tra thêm |
| Số việc mở quá 14 ngày | 4 | 1 | Có hạng mục bị ẩn, hủy hoặc đổi loại không? |
| Lỗi nghiêm trọng sau triển khai | Cần theo dõi | Cần theo dõi | Không được suy rằng giảm WIP chắc chắn giảm lỗi |

Các con số **12/4 = 3 tuần** và **6/4 = 1,5 tuần** được chọn để minh họa quan hệ Little's Law ở điều kiện ổn định. Với **ba tuần thử**, không thể khẳng định chúng đại diện cho phân phối dài hạn hoặc tác động nhân quả. Nhóm cần xem cách chọn giai đoạn, mức thay đổi phạm vi, số hạng mục đang mở từ trước và các yếu tố gây nhiễu.

### 11.6. Quyết định tiếp theo

Nếu work item age và cycle time giảm, throughput được giữ, chất lượng không xấu đi và nhóm phối hợp tốt hơn, có cơ sở **tiếp tục thử WIP = 6** rồi thu thập dữ liệu dài hơn.

Nếu tổng WIP giảm nhưng throughput cũng giảm mạnh vì thiếu kỹ năng review hoặc một môi trường test độc quyền, nhóm cần xử lý **điểm nghẽn thực**, không chỉ hạ limit thêm.

Nếu việc khẩn liên tục vượt chính sách, cần kiểm tra nguyên nhân sự cố và cách phân bổ năng lực vận hành. Mục tiêu cuối là **giá trị người dùng và dòng công việc đáng tin**, không phải giữ số 6 bằng mọi giá.

## 12. Giới hạn WIP khi kết hợp Scrum và XP

### 12.1. Kanban không đòi thay Scrum

Scrum tạo khung **Product Goal, Sprint Goal, Increment và các vòng kiểm tra–thích ứng**. Kanban giúp định nghĩa dòng công việc và kiểm soát WIP trong việc tạo Increment.

Một Scrum Team có thể dùng WIP limit cho Sprint Backlog để:

- Tránh chọn quá nhiều việc đang thực hiện cùng lúc.
- Nhìn blocker tác động tới Sprint Goal.
- Đưa PBI đạt Definition of Done sớm hơn.
- Hỗ trợ dự báo bằng throughput, cycle time và work item age.
- Thảo luận cải tiến trong Sprint Retrospective.

**Lưu ý:** Scrum Guide không bắt buộc mọi Scrum Team dùng Kanban board, WIP limit hay story point. Hạn WIP là **thực hành bổ trợ**, còn Sprint Goal và DoD vẫn phải được bảo vệ.

### 12.2. Sprint Backlog không bị đóng băng

Nếu giới hạn WIP khiến nhóm nhận ra PBI đang mở quá lớn hoặc một bước kiểm thử bị nghẽn, Developers có thể điều chỉnh cách làm, lập kế hoạch lại và thương lượng phạm vi với Product Owner khi cần.

Không dùng WIP limit để tuyên bố: “Đã vượt hạn rồi nên mặc kệ Sprint Goal.” Mục tiêu của chính sách là tăng khả năng thực hiện mục tiêu có chất lượng, không thay thế quyết định sản phẩm.

### 12.3. Các thực hành XP hỗ trợ hoàn tất công việc

**Extreme Programming (XP)** cung cấp các thực hành kỹ thuật giúp giảm thời gian chờ và làm lại:

| Khó khăn khi WIP cao | Thực hành có thể hỗ trợ | Lợi ích kỳ vọng |
|---|---|---|
| PR chờ review lâu | Pair programming, review sớm theo thay đổi nhỏ | Phát hiện hiểu nhầm và lỗi sớm |
| Tích hợp dồn cuối kỳ | Continuous Integration | Giảm xung đột mã và phản hồi kỹ thuật muộn |
| Kiểm thử hồi quy trở thành nút thắt | Automated testing/TDD khi phù hợp | Kiểm chứng hành vi lặp lại nhanh hơn |
| PBI khó chia vì code phụ thuộc chéo | Refactoring có kiểm soát | Giảm chi phí thay đổi và chia lát cắt |
| Chỉ một người hiểu module quan trọng | Pairing, chia sẻ kiến thức | Giảm phụ thuộc kỹ năng vào một cá nhân |

Không nên xem kỹ thuật XP là cách “lách” chất lượng để tăng throughput. Các thực hành này giúp **tạo Increment đáng tin cậy**, nhờ đó việc được chuyển sang Done phản ánh phần mềm thật.

## 13. Những sai lầm phổ biến khi áp WIP limit

| Sai lầm | Hệ quả | Cách điều chỉnh |
|---|---|---|
| “Mỗi người chỉ được làm đúng một ticket nên WIP toàn hệ thống bằng số người.” | Chưa tính chờ review/test, blocker và phụ thuộc | Định nghĩa workflow và số việc đã bắt đầu chưa Done |
| “Đã có giới hạn cột thì tổng WIP chắc chắn thấp.” | Nhiều cột cộng lại vẫn có quá nhiều việc dở | Xem cả giới hạn toàn luồng |
| “Khi cột của mình đầy, cứ mở việc ở cột trước.” | Hàng đợi và chuyển ngữ cảnh tăng | Ưu tiên giúp hoàn tất việc đang mở |
| “Việc blocked không tính WIP.” | Che công việc dở dang, báo trạng thái đẹp giả | Giữ blocked trong WIP và có chính sách tháo gỡ |
| “Nếu muốn giảm WIP chỉ cần chuyển ticket sang On Hold ngoài bảng.” | Dữ liệu không còn phản ánh thực tế | Nêu rõ chính sách hủy/tạm dừng thực sự và hệ quả |
| “WIP limit càng nhỏ càng tốt.” | Nghẽn kỹ năng, thiếu việc ở một số khâu, throughput có thể giảm | Thử giới hạn theo dữ liệu và ràng buộc thực |
| “Đạt limit nghĩa là mọi người phải ngồi chờ.” | Lãng phí cơ hội phối hợp và tháo blocker | Swarming, review, test, làm rõ phụ thuộc |
| “Việc khẩn không cần chính sách.” | Mọi việc dễ bị gắn khẩn, WIP liên tục vượt | Xác định tiêu chí, người quyết định, việc bị thay thế và hậu kiểm |
| “Cứ hoàn thành nhiều ticket là tạo nhiều giá trị.” | Đếm output thay vì outcome | Liên kết PBI với mục tiêu sản phẩm và phản hồi |
| “Giảm WIP là bảo đảm giảm cycle time đúng tỷ lệ.” | Áp Little's Law sai khi throughput hoặc loại việc đổi | Ghi giả định ổn định, đo throughput thực và biến động |
| “Số WIP thấp là KPI đánh giá năng suất cá nhân.” | Người làm việc có động cơ giấu việc hoặc tránh hỗ trợ | Dùng WIP để cải thiện hệ thống và chất lượng |
| “Tất cả trạng thái phải có cùng giới hạn.” | Bỏ qua đặc tính workflow và điểm tắc | Chọn chính sách theo luồng thực tế |
| “Kanban chỉ là bảng ba cột.” | Không có chính sách pull hoặc đo luồng, khó cải tiến | Định nghĩa workflow, kiểm soát WIP, quản lý và cải thiện luồng |
| “Để kịp hạn có thể gọi Done khi mới code xong.” | Throughput giả, lỗi chuyển về người dùng | Giữ DoD và chuẩn chuyển trạng thái |

## 14. Checklist áp dụng giới hạn WIP

### Trước khi bắt đầu

1. **Mục tiêu:** vấn đề nào của dòng công việc hoặc giá trị sản phẩm cần cải thiện?
2. **Phạm vi:** đâu là điểm bắt đầu và kết thúc của workflow?
3. **Loại việc:** những hạng mục được tính có đặc tính đủ tương đồng không?
4. **Trạng thái:** mỗi cột có chính sách vào/ra rõ ràng không?
5. **Done:** trạng thái hoàn thành có tuân thủ Definition of Done áp dụng không?
6. **Số nền:** đã biết WIP, throughput, cycle time và điểm tắc hiện tại chưa?

### Khi vận hành

7. **Giới hạn:** nhóm có biết tổng WIP và các trạng thái bị giới hạn không?
8. **Pull:** khi WIP đầy, có ưu tiên hoàn tất việc cũ trước khi kéo việc mới không?
9. **Blocked:** hạng mục bị chặn có vẫn hiển thị và có bước tiếp theo không?
10. **Chất lượng:** nhóm có tránh đẩy việc chưa sẵn sàng sang trạng thái tiếp theo không?
11. **Ngoại lệ:** việc khẩn có tiêu chí, trách nhiệm, đánh đổi và ghi nhận rõ không?
12. **Phối hợp:** mọi người có thể hỗ trợ đúng nơi tắc mà không xâm phạm quyền hạn/chuyên môn không?

### Khi đánh giá

13. **Dòng công việc:** WIP trung bình, phân bố cycle time và work item age thay đổi thế nào?
14. **Năng lực hoàn tất:** throughput có giữ được hoặc cải thiện không?
15. **Kết quả người dùng:** Increment có giao được sớm hơn và hữu ích hơn không?
16. **Rủi ro:** lỗi, chuyển ngữ cảnh, quá tải hoặc sự phụ thuộc mới có tăng không?
17. **Quyết định tiếp:** giữ, điều chỉnh giới hạn, đổi chính sách pull hay xử lý điểm tắc gốc?

Đừng dùng checklist như bộ hồ sơ kiểm toán bắt buộc cho mọi PBI; hãy xem đó là những câu hỏi giúp **kiểm tra và thích ứng có mục đích**.

## 15. Bài tập vận dụng

### Bài tập 1 — Tính WIP và quyết định kéo việc

Một đội có workflow: **Sẵn sàng → Dev → Review → Test → Done**. Chính sách: Dev tối đa 3, Review tối đa 2, Test tối đa 2, **tổng WIP tối đa 5**. Hiện có:

| Trạng thái | Số việc |
|---|---:|
| Sẵn sàng | 8 |
| Dev | 2 |
| Review | 2 |
| Test | 1 |
| Done | 14 |

**Yêu cầu:**

1. Tính WIP hiện tại.
2. Đội có được bắt đầu thêm một PBI từ Sẵn sàng không? Vì sao?
3. Nếu một PBI chuyển từ Review sang Test, đội đã có chỗ kéo việc mới chưa?
4. Nếu một PBI ở Test đạt Done, khi đó WIP thay đổi thế nào?

**Gợi ý:** WIP = **2 + 2 + 1 = 5**, bằng giới hạn tổng. Chuyển giữa các trạng thái WIP không làm giảm tổng; chỉ khi một việc kết thúc hoặc có chính sách khác được thực thi hợp lệ thì mới có chỗ.

### Bài tập 2 — Xử lý việc blocked

PBI “Đồng bộ tiến độ học” đã bắt đầu 12 ngày nhưng chờ môi trường thử của đối tác. Developer đề nghị chuyển nó sang một cột “Tạm dừng” ngoài phạm vi WIP để được mở thêm ba tính năng.

**Yêu cầu:** giải thích tại sao cách xử lý đó có thể làm sai dữ liệu, đề xuất thông tin cần ghi cho blocker và hai hành động giảm rủi ro phù hợp.

**Gợi ý:** nếu việc chưa hoàn tất và vẫn được giữ trong workflow, nó vẫn là WIP. Có thể làm rõ đầu mối đối tác, thử nghiệm hợp đồng bằng môi trường giả lập có kiểm chứng, điều chỉnh ưu tiên cùng Product Owner hoặc quyết định dừng hẳn công việc với lý do minh bạch.

### Bài tập 3 — Little's Law

Một workflow ổn định giả định có **WIP trung bình = 10 PBI**, **throughput trung bình = 2 PBI/tuần**.

1. Tính cycle time trung bình theo Little's Law.
2. Nếu WIP trung bình giảm xuống 6 nhưng throughput vẫn là 2/tuần, cycle time tương ứng là bao nhiêu?
3. Nêu ba lý do không thể coi kết quả này là lời hứa giao một PBI cụ thể.
4. Giải thích vì sao việc giảm WIP có thể không giữ được throughput.

**Gợi ý:** 10/2 = **5 tuần**; 6/2 = **3 tuần** nếu điều kiện ổn định và throughput giữ nguyên. Công việc không đồng nhất, phụ thuộc, thay đổi năng lực và biến động là những yếu tố quan trọng.

### Bài tập 4 — Thiết kế WIP limit theo điểm tắc

Nhóm có sáu người, phần lớn công việc chờ review mã. Qua quan sát, backlog có 30 hạng mục, **9 việc đang mở**, trong đó **5 việc chờ review**. Người quản lý đề xuất “mọi Developer được bắt đầu tối đa ba việc cùng lúc”.

**Yêu cầu:** giải thích vì sao đề xuất có thể làm tăng WIP, đề xuất một thử nghiệm giới hạn cho toàn luồng và cho Review, cùng ba phép đo đánh giá.

**Gợi ý:** nếu mỗi người có ba việc thì tổng công việc dở có thể tăng đáng kể. Nên thảo luận giới hạn hệ thống thấp hơn mức đang có và cách giúp review hoàn tất; đo cycle time, work item age và throughput.

### Bài tập 5 — Ngoại lệ khẩn cấp

Trong khi WIP đang đầy, nhóm phát hiện lỗi thanh toán có thể tạo giao dịch trùng. Đồng thời, bộ phận kinh doanh yêu cầu thêm biểu tượng mới “trước chiều nay”.

**Yêu cầu:** phân loại hai yêu cầu theo rủi ro, mô tả cách kích hoạt chính sách khẩn, cho biết việc nào có thể cần tạm dừng và cách tránh hạ DoD.

**Gợi ý:** rủi ro giao dịch trùng thường cần phản ứng theo chính sách sự cố; yêu cầu biểu tượng không tự trở thành khẩn chỉ vì có mốc do người đề xuất mong muốn.

### Bài tập 6 — Đọc số liệu sau thử nghiệm

Nhóm thử giảm WIP tổng từ 10 xuống 6. Sau hai tuần, throughput giảm từ 5 xuống 3 PBI/tuần, trong khi cycle time trung bình của một số PBI hoàn thành có vẻ giảm.

**Yêu cầu:** có đủ căn cứ để tuyên bố chính sách mới thành công không? Cần kiểm tra những gì về loại việc, blocker, phụ thuộc, số mẫu, Definition of Done và lỗi?

**Gợi ý:** chưa đủ. Có thể các PBI hoàn thành là việc nhỏ, việc khó còn mở; throughput giảm có thể do giới hạn quá thấp hoặc rủi ro ngoài ý muốn. Cần nhìn phân bố cycle time, work item age và chất lượng cùng nhau.

### Bài tập 7 — Viết Definition of Workflow cho nhóm mình

Điền mẫu:

~~~text
Loại công việc cần quản lý:
Product Goal hoặc vấn đề dòng công việc muốn cải thiện:
Điểm bắt đầu:
Điểm kết thúc / tiêu chuẩn Done:
Các trạng thái:
WIP hiện tại và nơi chờ lâu nhất:
WIP limit tổng và giới hạn trạng thái (nếu có):
Quy tắc kéo việc mới:
Chính sách khi cột đầy:
Chính sách blocked item:
Chính sách việc khẩn:
Throughput / cycle time / work item age cần đo:
SLE nếu đã đủ dữ liệu:
Tín hiệu chất lượng và outcome người dùng:
Thời điểm xem lại chính sách:
Điều kiện giữ / thay đổi giới hạn:
~~~

**Tự đánh giá:** nếu một người mới tham gia nhóm, họ có thể biết **khi nào được bắt đầu PBI, làm gì lúc không có chỗ và thế nào mới thật sự Done** mà không cần hỏi nhiều người hay không?

## 16. Tổng kết

Kiểm soát công việc đang thực hiện bằng giới hạn WIP là cách Kanban giúp nhóm **tối ưu dòng giá trị thay vì tối đa số việc mỗi người đang giữ**.

Những ý chính cần nhớ:

1. **WIP là việc đã bắt đầu nhưng chưa hoàn thành**, được xác định bằng điểm bắt đầu/kết thúc minh bạch của workflow.
2. **WIP limit là chính sách kéo việc**, không chỉ số in trên tiêu đề cột. Cần biết phải làm gì khi đầy, khi blocked và khi xuất hiện việc khẩn.
3. **Hoàn tất trước khi bắt đầu thêm** giúp giảm chuyển ngữ cảnh và làm lộ điểm tắc; tuy nhiên giới hạn phải được thiết kế phù hợp thay vì càng thấp càng tốt.
4. **Definition of Workflow** làm rõ loại việc, trạng thái, cách kiểm soát WIP, chính sách và SLE. Thiếu định nghĩa chung sẽ khiến số đếm không đáng tin.
5. **Bốn phép đo nền tảng** — WIP, throughput, work item age, cycle time — hỗ trợ kiểm tra và cải tiến; chúng không tự đo giá trị người dùng hoặc năng suất cá nhân.
6. **Little's Law** giúp hiểu quan hệ WIP–throughput–cycle time trong điều kiện ổn định; giảm WIP không tự bảo đảm throughput giữ nguyên.
7. **Scrum và XP có thể bổ trợ**: Scrum giữ mục tiêu và vòng phản hồi, Kanban quản lý dòng công việc, XP giúp phần mềm tích hợp và kiểm thử sớm để đạt DoD.
8. **Thử, đo và điều chỉnh** chính sách dựa trên chất lượng và outcome sản phẩm. Một WIP limit tốt là giới hạn giúp nhóm đưa những phần nhỏ, đáng tin đến người dùng sớm hơn.

> **Câu hỏi ghi nhớ:** “Khi một việc mới xuất hiện, đội đang cần thêm người **bắt đầu**, hay cần cùng nhau **hoàn tất** điều đã mở để người dùng sớm nhận giá trị?”

### Tài liệu tham khảo

- [The Kanban Guide](https://kanbanguides.org/) — Definition of Workflow, kiểm soát WIP, pull, SLE và bốn phép đo dòng công việc.
- [The Scrum Guide](https://scrumguides.org/scrum-guide.html) — Product Goal, Sprint Goal, Sprint Backlog, Increment, Definition of Done và kiểm tra/thích ứng.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 Principles](https://agilemanifesto.org/principles.html) — giao phần mềm có giá trị sớm, cộng tác, thích ứng và nhịp làm việc bền vững.
- [Agile Alliance — Extreme Programming](https://agilealliance.org/glossary/xp/) — tích hợp liên tục, kiểm thử, refactoring và cộng tác kỹ thuật để giao phần mềm chất lượng.
