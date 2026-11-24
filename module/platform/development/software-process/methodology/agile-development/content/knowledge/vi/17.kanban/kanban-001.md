# Kanban và mục tiêu tối ưu dòng giá trị

> **Chương:** Kanban  
> **Học phần:** **AGILE_DEVELOPMENT** — hiểu các giá trị và nguyên tắc Agile để phát triển phần mềm thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc nhằm lựa chọn cách phối hợp phù hợp.

Một nhóm có thể có bảng Kanban rất đẹp với ba cột **To do – Doing – Done**, nhưng khách hàng vẫn phải đợi ba tuần để nhận một thay đổi nhỏ. Vấn đề không nằm ở việc nhóm thiếu bảng: năm hạng mục cùng chờ review, môi trường kiểm thử liên tục bị chặn, nhiều việc được bắt đầu nhưng rất ít việc được hoàn tất. Mỗi người có vẻ luôn bận, còn **giá trị chưa đến tay người dùng**.

**Kanban** giúp nhóm nhìn và cải tiến **dòng chảy của các hạng mục công việc qua một quy trình xác định**. Thay vì tối đa hóa số việc mọi người đang làm, nhóm tìm cách **giao giá trị liên tục, có thể dự báo và bền vững**, giảm chờ đợi và phát hiện trở ngại sớm. Bảng trực quan chỉ là một công cụ; Kanban phát huy tác dụng khi nhóm cùng định nghĩa luồng làm việc, kiểm soát công việc đang làm (*work in progress — WIP*), quản lý các hạng mục trong luồng và điều chỉnh quy trình bằng bằng chứng.

Bài viết diễn giải các khái niệm từ **The Kanban Guide**, liên hệ một số thực hành quen thuộc trong **Kanban Method** và đưa ra ví dụ phát triển phần mềm. Những giá trị số, giới hạn WIP, quy tắc và lịch trao đổi dùng trong ví dụ chỉ có tính minh họa; chúng không phải cấu hình bắt buộc cho mọi nhóm.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích **dòng giá trị (value flow)** và phân biệt tối ưu dòng công việc với giữ từng người luôn bận.
2. Xây dựng một **Definition of Workflow** rõ ràng: hạng mục, điểm bắt đầu/kết thúc, trạng thái, chính sách, cách kiểm soát WIP và kỳ vọng mức dịch vụ.
3. Mô tả cơ chế **pull** và giới hạn WIP, đồng thời xử lý các hạng mục bị chặn hoặc cần ưu tiên khẩn cấp một cách minh bạch.
4. Tính và diễn giải **WIP, throughput, cycle time, work item age**, phân biệt chúng với lead time, thời gian chờ và kết quả sản phẩm.
5. Dùng bảng trực quan và dữ liệu để nhận ra nút thắt, thiết kế thử nghiệm cải tiến và kiểm tra kết quả.
6. Liên hệ Kanban với backlog, user story, Scrum, XP và các cách nhận phản hồi, giao phần mềm tăng dần.

## 2. Tối ưu dòng giá trị thực chất là tối ưu điều gì?

### 2.1. Giá trị chỉ hình thành khi nhu cầu được giải quyết

Hãy xét một yêu cầu trong hệ thống đặt lịch: “Khách cần đổi giờ hẹn mà không phải gọi tổng đài”.

- Người dùng nêu nhu cầu.
- Người làm sản phẩm xác định quy tắc và thứ tự ưu tiên.
- Developers triển khai, review và kiểm thử.
- Phần mềm được phát hành cho đối tượng sử dụng.
- Người dùng đổi được giờ hẹn thành công; nhóm quan sát tác động và độ tin cậy.

**Value stream (chuỗi hoạt động tạo và chuyển giao giá trị)** bao gồm cả những bước có ích và thời gian chờ giữa các bước. Nếu chỉ nhìn giờ lập trình, nhóm có thể không thấy một user story viết mã trong hai ngày nhưng chờ phê duyệt, review và phát hành thêm mười ngày.

Trong ngữ cảnh Kanban, **flow** mô tả cách các hạng mục đi qua một workflow cụ thể. Nhóm cần chọn ranh giới workflow phản ánh điều mình muốn cải thiện. Nếu điểm “Done” chỉ có nghĩa là “code đã merge”, nhóm phải thừa nhận chỉ số đo **flow đến merge**, chưa phải thời gian khách hàng nhận giá trị. Muốn tối ưu thời gian đến tay người dùng, phải đo cả đường từ yêu cầu tới phát hành hoặc sử dụng thực tế.

### 2.2. Bốn góc nhìn bổ sung nhau

| Góc nhìn | Câu hỏi | Tín hiệu thực tế |
| --- | --- | --- |
| **Hiệu quả tạo giá trị (effectiveness)** | Đang làm đúng vấn đề và có đáp ứng nhu cầu không? | Tỷ lệ hoàn tất tác vụ, mức dùng tính năng, phản hồi khách hàng. |
| **Hiệu quả dòng (flow efficiency)** | Công việc nằm chờ bao lâu so với thời gian thực sự được xử lý? | Thời gian chờ review, chờ kiểm thử, chờ quyền truy cập. |
| **Khả năng dự báo (predictability)** | Có thể nói hợp lý khi nào hạng mục sẽ hoàn tất không? | Phân bố cycle time, tuổi của việc đang làm, Service Level Expectation (SLE). |
| **Tính bền vững/chất lượng** | Có đang giao nhanh bằng cách chuyển rủi ro sang tương lai không? | Lỗi hồi quy, sự cố, làm thêm giờ, độ ổn định vận hành. |

**Không đánh đồng “flow nhanh” với “giá trị cao”.** Một nhóm có thể đóng các ticket vô ích rất nhanh. Ngược lại, một nhóm chọn đúng vấn đề nhưng để công việc mắc ở các hàng đợi lâu sẽ khiến giá trị đến chậm. Kanban cần được dùng cùng hoạt động khám phá nhu cầu, định hướng sản phẩm và chuẩn chất lượng.

### 2.3. Tối ưu hệ thống khác tối ưu mức bận rộn cá nhân

Giả sử nhóm có năm người, mỗi người nhận ba việc để chứng minh mình luôn bận. Khi cần review, ai cũng đang viết code; kết quả là hàng đợi review tăng, mọi việc có nhiều thời gian chờ. Một chính sách “giúp hoàn tất công việc gần Done trước khi kéo việc mới” có thể giảm WIP và cycle time, dù một số người không luôn có ticket riêng ở trạng thái Doing.

Kanban ưu tiên **dòng hạng mục qua toàn bộ hệ thống** hơn tối đa hóa công suất cục bộ. Một cột đầy, một người luôn bận hoặc nhiều thẻ được mở **không phải mục tiêu cuối cùng**.

## 3. Phân biệt bảng Kanban, hệ thống Kanban và Kanban Method

| Khái niệm | Giải thích | Điều dễ nhầm |
| --- | --- | --- |
| **Bảng Kanban** | Cách hiển thị trạng thái công việc, giới hạn và điểm chặn. | Có bảng chưa có nghĩa đã quản lý flow tốt. |
| **Hệ thống Kanban** | Workflow được định nghĩa, hạng mục đi qua các trạng thái theo chính sách, WIP được kiểm soát, các số đo giúp cải tiến. | Không chỉ có thao tác kéo thẻ từ trái sang phải. |
| **Kanban Method** | Cách tiếp cận cải tiến dịch vụ và quản lý thay đổi dần dần dựa trên thực trạng, luồng giá trị, chính sách và phản hồi. | Không phải yêu cầu thay toàn bộ cơ cấu tổ chức ngay. |
| **Scrum có dùng Kanban** | Scrum Team dùng trực quan hóa, WIP, pull và flow metrics để nâng hiệu quả trong khung Scrum. | Không thay thế Sprint Goal, trách nhiệm và các sự kiện Scrum bằng một bảng. |

Các hướng dẫn Kanban khác nhau có thể sắp xếp thực hành bằng thuật ngữ không hoàn toàn giống nhau. **The Kanban Guide** nhấn mạnh việc **định nghĩa và trực quan hóa workflow, chủ động quản lý các hạng mục trong workflow, cải tiến workflow**. Kanban Method thường được mô tả qua các thực hành như **trực quan hóa, giới hạn WIP, quản lý flow, làm rõ chính sách, dùng vòng phản hồi và cải tiến hợp tác**. Hai cách diễn đạt đều nhằm biến luồng công việc thành thứ quan sát và cải thiện được.

## 4. Bắt đầu bằng cách nhìn thấy workflow thực tế

Một nhóm thường có luồng thực tế phức tạp hơn ba cột: yêu cầu đi vào, được làm rõ, chờ ưu tiên, phát triển, code review, kiểm thử, đợi môi trường phát hành và cuối cùng tới người dùng.

**Ví dụ workflow của một dịch vụ đặt lịch:**

~~~text
Yêu cầu -> Làm rõ -> Sẵn sàng | Đang phát triển -> Review -> Kiểm thử -> Đã giao
                               ^                                ^
                       Điểm bắt đầu WIP                   Điểm kết thúc WIP
~~~

Trong ví dụ này, thời điểm nhóm **kéo hạng mục vào Đang phát triển** là điểm bắt đầu để đo cycle time; **Đã giao** là điểm kết thúc. Trạng thái trước điểm bắt đầu có thể được dùng để đo lead time rộng hơn. Quy tắc này cần được cả nhóm hiểu giống nhau.

Không cần sao chép nguyên sơ đồ vào mọi đội. Nhóm hỗ trợ production, phát triển sản phẩm mới hoặc xử lý công việc pháp lý có trạng thái khác nhau. Nếu bảng chỉ dùng “Doing” nhưng không cho thấy thời gian chờ review, nó khó giúp xác định nút thắt.

### 4.1. Definition of Workflow (DoW): không chỉ đặt tên cột

Một **Definition of Workflow** nên làm rõ:

1. **Loại hạng mục công việc** được theo dõi: user story, lỗi, thay đổi hạ tầng, discovery có giới hạn…
2. **Điểm bắt đầu và điểm kết thúc** của workflow: khi nào hạng mục được xem là bắt đầu/hoàn tất?
3. **Các trạng thái bên trong** và cách hạng mục chuyển trạng thái.
4. **Cách kiểm soát WIP**, chẳng hạn giới hạn theo cột, theo nhóm trạng thái hoặc toàn bộ workflow.
5. **Chính sách minh bạch (explicit policies)** về kéo việc, hoàn tất, blocked, ưu tiên và các trường hợp ngoại lệ.
6. **Service Level Expectation (SLE)** để thể hiện kỳ vọng thời gian hoàn tất; nếu chưa có đủ dữ liệu lịch sử, nhóm ghi rõ kỳ vọng ban đầu là giả định cần được hiệu chỉnh.

Các yếu tố phải **quan sát và sử dụng được**, không chỉ được ghi trong trang tài liệu ít người mở. Có thể bắt đầu đơn giản, rồi thay đổi khi thấy workflow không phản ánh công việc thật.

### 4.2. Ví dụ Definition of Workflow cho một nhóm nhỏ

| Thành phần | Định nghĩa minh họa |
| --- | --- |
| **Hạng mục** | Một lát cắt user story, bug hoặc thay đổi kỹ thuật có kết quả xác định. |
| **Bắt đầu** | Hạng mục được kéo từ Sẵn sàng vào Đang phát triển. |
| **Kết thúc** | Hành vi đã đáp ứng chuẩn chất lượng và được giao theo chính sách sản phẩm. |
| **Trạng thái** | Đang phát triển → Review → Kiểm thử/triển khai → Đã giao. |
| **WIP** | Tối đa ba mục trong Đang phát triển, hai mục trong Review, hai mục trong Kiểm thử; xem lại giới hạn toàn hệ thống khi cần. |
| **Chính sách kéo** | Chỉ kéo khi có chỗ theo WIP limit và hạng mục đủ rõ; ưu tiên hoàn tất mục già nhất nếu có rủi ro. |
| **Blocked** | Hiển thị lý do và người phối hợp; vẫn tính vào WIP khi chưa hoàn tất, trừ khi chính sách workflow xác định và quản lý riêng minh bạch. |
| **Tiêu chí hoàn tất** | Có kết quả được kiểm chứng, kiểm thử liên quan đạt, không vi phạm bảo mật và được giao theo ranh giới Done đã định. |
| **SLE** | Ví dụ mục tiêu kỳ vọng “85% hạng mục hoàn tất trong không quá tám ngày” khi dữ liệu lịch sử đủ phù hợp; kiểm tra lại bằng dữ liệu. |

Các giới hạn **3, 2, 2** không phải giá trị chuẩn của Kanban. WIP limit là **chính sách để tạo tín hiệu về quá tải**; cần cân nhắc kỹ năng, cách chia hạng mục, phụ thuộc và loại dịch vụ. Không nên thay số liên tục chỉ để bảng không bao giờ báo quá tải.

### 4.3. Làm hiện rõ “chờ” và “bị chặn”

Một hạng mục có thể đang ở Review suốt bốn ngày vì người đủ quyền phê duyệt đi nghỉ. Nếu thẻ vẫn để “Đang phát triển”, nhóm dễ tưởng lập trình đang chậm.

Có thể dùng:

- Cột hoặc hàng con **Đang chờ review**, **Chờ môi trường**, **Chờ đối tác** khi chúng là trạng thái có ý nghĩa.
- **Dấu blocked** với lý do, ngày bắt đầu bị chặn và hành động gỡ chặn.
- Quy định **ai hỗ trợ khi bị chặn**, khi nào cần làm việc với nhóm khác và ai quyết định chuyển ưu tiên.
- Cảnh báo theo **work item age** để thấy việc đang kéo dài, không chờ tới khi đã quá hạn mới phản ứng.

**Không che việc bị chặn bằng cách chuyển thẻ sang Done hoặc khỏi bảng.** Việc còn tồn tại vẫn tiêu tốn năng lực dự báo và làm mất khả năng giao đúng kỳ vọng. Nếu một việc thực sự được hủy, cần ghi nhận lý do và tách khỏi số liệu hoàn tất theo quy tắc đo nhất quán.

## 5. Pull và giới hạn WIP: hoàn tất trước khi bắt đầu thêm

### 5.1. Push khác pull ở điểm nào?

**Push (đẩy việc):** Ai có yêu cầu mới hoặc ai có thời gian trống liền giao thêm, dù các trạng thái tiếp theo đang đầy.

**Pull (kéo việc):** Người/nhóm đang có năng lực và thỏa điều kiện của workflow **chủ động kéo** hạng mục ưu tiên phù hợp từ hàng đợi; trước khi kéo, xem trạng thái các việc hiện tại, WIP limit và chính sách.

Ví dụ, cột Review có giới hạn hai mục. Nếu đã đủ hai mục, Developers không nên mặc nhiên bắt đầu thêm một feature để “giữ người bận”. Họ có thể hỗ trợ review, ghép đôi với người đang xử lý, giảm phụ thuộc hoặc tháo điểm chặn để đưa một hạng mục tới Done.

### 5.2. Vì sao WIP cao kéo dài thời gian đến giá trị?

Khi quá nhiều hạng mục được bắt đầu:

- Mỗi hạng mục có ít thời gian được xử lý liên tục hơn.
- Chuyển ngữ cảnh và hàng đợi tăng.
- Lỗi tích hợp có thể chỉ lộ khi nhiều nhánh code tồn tại lâu.
- Người ngoài khó biết hạng mục nào sẽ xong trước.
- Một sự cố mới càng dễ làm toàn bộ các hạng mục trễ thêm.

**Giới hạn WIP** không khiến mọi vấn đề tự biến mất. Nó làm việc quá tải **trở nên nhìn thấy được**, buộc nhóm đặt câu hỏi về ưu tiên, điểm chờ và năng lực. Nếu WIP cao vì một đối tác chậm phê duyệt, nhóm phải xử lý phụ thuộc đó chứ không chỉ di chuyển thẻ.

### 5.3. Ví dụ thay đổi thói quen

Trước khi dùng pull:

~~~text
Ngày 1: Bắt đầu A, B, C.
Ngày 2: A chờ review; mở D, E.
Ngày 3: B chờ test; mở F.
Ngày 4: Sáu việc đang làm, chưa việc nào thực sự Done.
~~~

Sau khi thống nhất giới hạn và chính sách:

~~~text
Ngày 1: Kéo A, B.
Ngày 2: A sẵn sàng review; Developers giúp hoàn tất review của A.
Ngày 3: A đạt chuẩn và kết thúc; khi có chỗ mới kéo C.
Ngày 4: B được kiểm thử; cả nhóm xử lý điểm chặn trước khi kéo D.
~~~

Không nên hiểu ví dụ này là “Kanban chỉ cho phép làm tuần tự một việc”. Nhóm có thể làm song song trong phạm vi hợp lý. Mục tiêu là **giữ lượng công việc đang thực hiện vừa đủ để flow tốt**, không phải làm mọi người chờ không cần thiết.

### 5.4. Khi nào phá giới hạn WIP?

Một sự cố ảnh hưởng an toàn dữ liệu có thể cần ứng cứu ngay. Nhưng nếu cứ tăng WIP limit mỗi khi có người yêu cầu thêm feature, limit không còn tác dụng.

Hãy có **chính sách ngoại lệ**:

1. Tiêu chí khẩn cấp có thể kiểm tra được: mức tác động, nghĩa vụ và thời hạn.
2. Ai có quyền kích hoạt, ai điều phối?
3. Công việc nào tạm dừng, tác động tới dự báo?
4. Khi nào kết thúc trạng thái ngoại lệ và khôi phục flow?
5. Có xem lại nguyên nhân khiến việc khẩn cấp xuất hiện không?

Mỗi ngoại lệ thực sự nên có **lý do và thời điểm xem lại**. Một quy trình khẩn cấp có thể chạy ngoài workflow chuẩn, nhưng chi phí năng lực và tác động tới việc khác phải được nhìn thấy.

## 6. Tối ưu dòng không phải ép mọi công việc có cùng mức ưu tiên

Một hệ thống phần mềm thường có tính năng mới, bug, nợ kỹ thuật và khám phá. Các loại này khác nhau về hậu quả nếu trì hoãn, nhưng vẫn cần tranh luận trên **cùng năng lực thực tế**.

### 6.1. Làm rõ thứ tự và tiêu chí kéo hạng mục

Khi có chỗ để kéo việc mới, nhóm cần biết:

- Hạng mục nào tạo giá trị và phục vụ mục tiêu sản phẩm?
- Hạng mục nào có **chi phí trì hoãn** cao, ngày bắt buộc hoặc rủi ro lớn?
- Hạng mục nào đã đủ rõ, đủ điều kiện kiểm thử và không bị chặn đầu vào?
- Có thể chia nhỏ hạng mục để nhận phản hồi sớm hơn không?
- Nếu chọn việc này, **việc nào sẽ chờ**?

Kanban không tự quyết định chiến lược sản phẩm. Product Owner hoặc người chịu trách nhiệm sản phẩm vẫn cần làm rõ giá trị và thứ tự backlog; nhóm kỹ thuật cung cấp kích thước, rủi ro, phụ thuộc và chất lượng.

### 6.2. Classes of service: khi cần chính sách riêng

Một số nhóm dùng **lớp dịch vụ (classes of service)** để thiết kế cách xử lý:

| Lớp minh họa | Khi áp dụng | Cách quản lý |
| --- | --- | --- |
| **Tiêu chuẩn (standard)** | Phần lớn feature, lỗi thường và cải tiến kỹ thuật. | Kéo theo thứ tự đã thống nhất và WIP limit. |
| **Khẩn cấp (expedite)** | Sự cố nghiêm trọng có hậu quả hiện tại. | Quy trình ưu tiên đặc biệt theo thẩm quyền, công khai tác động và thời điểm kết thúc. |
| **Có hạn cố định (fixed date)** | API ngừng hỗ trợ, nghĩa vụ phải đáp ứng trước ngày cụ thể. | Quản lý hạn và rủi ro từ sớm, không chờ đến phút cuối mới gắn khẩn cấp. |
| **Khám phá có giới hạn** | Giả định lớn chưa rõ trước khi cam kết giải pháp. | Hạng mục timebox với câu hỏi, tiêu chí dừng và quyết định cần hỗ trợ. |

Đây là **chính sách có thể chọn**, không phải bốn trạng thái bắt buộc hay bốn loại người trong Kanban. Nếu 80% hạng mục đều thành expedite, nhóm cần xem lại tiêu chí và nguyên nhân nhu cầu khẩn; một làn khẩn cấp luôn đầy sẽ không còn nhanh.

### 6.3. Nợ kỹ thuật cũng ảnh hưởng dòng giá trị

Ví dụ cứ mỗi lần sửa luồng đặt lịch, nhóm phải sửa cùng quy tắc ở ba service và mất hai ngày kiểm thử thủ công. Refactor kết hợp kiểm thử tự động có thể giảm độ trễ và lỗi hồi quy cho nhiều thay đổi tiếp theo. Nếu đề xuất này được diễn đạt bằng **chi phí chờ, rủi ro, khả năng thay đổi và kết quả kiểm chứng**, người chịu trách nhiệm ưu tiên dễ so sánh hơn với một feature mới.

Ngược lại, “viết lại cho sạch” mà không nêu tác động hiện tại hoặc tương lai gần chưa có cơ sở vượt lên một yêu cầu khách hàng cấp bách.

## 7. Bốn chỉ số flow cốt lõi

Đo lường giúp nhóm **ra quyết định cải tiến workflow**, không dùng để xếp hạng người viết code. Các chỉ số sau cần thống nhất điểm bắt đầu/kết thúc và cách chia hạng mục trước khi so sánh.

| Chỉ số | Định nghĩa thực hành | Câu hỏi nó trả lời |
| --- | --- | --- |
| **WIP — Work in Progress** | Số hạng mục đã bắt đầu nhưng chưa đạt điểm kết thúc workflow ở thời điểm quan sát. | Hệ thống đang giữ bao nhiêu việc chưa hoàn tất? |
| **Throughput** | Số hạng mục hoàn tất trong một khoảng thời gian, theo cùng định nghĩa Done. | Trong một tuần/tháng, hệ thống hoàn tất được bao nhiêu việc? |
| **Cycle time** | Thời gian thực tế từ điểm bắt đầu đến điểm kết thúc workflow của một hạng mục **đã hoàn tất**. | Các hạng mục thường mất bao lâu để đi qua luồng? |
| **Work item age** | Thời gian trôi qua từ điểm bắt đầu đến **hiện tại** của hạng mục **chưa hoàn tất**. | Việc nào đang già đi và có nguy cơ vượt kỳ vọng? |

Trong hệ thống thực, **cycle time và work item age là hai phía của cùng một định nghĩa luồng**: một chỉ số dành cho việc đã xong, một chỉ số dành cho việc còn đang làm. Không thể lấy số trung bình của những việc đã hoàn tất để khẳng định việc đang bị chặn sẽ tự xong đúng ngày.

### 7.1. Phân biệt lead time với cycle time

Thuật ngữ **lead time** có thể được dùng khác nhau tùy tổ chức. Một định nghĩa hữu ích:

- **Request lead time:** Từ khi khách hàng gửi yêu cầu tới khi khách nhận kết quả.
- **Cycle time của workflow nhóm:** Từ lúc hạng mục được kéo vào Đang phát triển đến khi qua điểm Done được định nghĩa.

Ví dụ:

~~~text
Ngày 1: Khách nêu yêu cầu
Ngày 4: Yêu cầu đủ rõ, vào Sẵn sàng
Ngày 7: Developers kéo vào Đang phát triển   <- bắt đầu cycle time
Ngày 9: Hoàn tất lập trình
Ngày 13: Hoàn tất review và kiểm thử
Ngày 14: Phát hành                            <- kết thúc cycle time
~~~

Theo quy ước tính thời gian trôi qua giữa hai mốc ngày, **cycle time là 7 ngày** (từ ngày 7 tới 14), còn **request lead time là 13 ngày** (từ ngày 1 tới 14). Nếu đếm số ngày lịch bao gồm cả ngày đầu/cuối, kết quả số đếm khác; nhóm phải thống nhất cách tính, múi giờ và các loại ngày trước khi công bố số liệu.

**Quan trọng:** Nếu nhóm định nghĩa điểm Done tại “code merge” thay vì “phát hành”, cycle time sẽ khác. Không thể so sánh hai nhóm dùng ranh giới khác nhau rồi kết luận nhóm nào làm việc tốt hơn.

### 7.2. Work item age là tín hiệu hành động sớm

Một hạng mục đang ở Review sáu ngày có tuổi sáu ngày kể từ điểm bắt đầu; nếu chính sách SLE của nhóm thường kỳ vọng phần lớn việc kết thúc trước tám ngày, đây là lúc phải xem hạng mục có bị chặn hoặc bị bỏ quên không.

**Câu hỏi cho cuộc họp xem flow:**

- Hạng mục nào già nhất và vì sao chưa kết thúc?
- Có đang chờ quyền truy cập, quyết định nghiệp vụ hoặc reviewer?
- Việc chia nhỏ có cần thiết và có còn giữ giá trị của hạng mục không?
- Nên ưu tiên hoàn tất, hỗ trợ giải quyết điểm chặn hay cân nhắc dừng việc không còn giá trị?

Tuổi của việc tăng theo thời gian cho tới khi hạng mục hoàn tất hoặc được xử lý theo chính sách hủy minh bạch. Không tự “làm mới ngày bắt đầu” để số liệu trông đẹp.

### 7.3. Throughput không đo giá trị hay năng suất cá nhân

Nếu một tuần hoàn tất tám ticket rất nhỏ, tuần sau hoàn tất hai hạng mục phức tạp tạo tác động lớn, **không thể chỉ nhìn 8 và 2 để kết luận tuần đầu tốt hơn**. Cần xem cách chia hạng mục, chất lượng, outcome và các phụ thuộc. Throughput đặc biệt hữu ích cho dự báo khi hạng mục cùng loại có kích thước tương đối nhất quán.

### 7.4. Dữ liệu minh họa cho một tuần

| Mã | Bắt đầu | Hoàn tất | Cycle time tính theo ngày trôi qua |
| --- | --- | --- | ---: |
| A — Sửa xác nhận lịch | Thứ Hai tuần trước | Thứ Năm tuần trước | 3 |
| B — Thêm kiểm thử retry | Thứ Ba tuần trước | Thứ Sáu tuần trước | 3 |
| C — Đổi nội dung xác nhận | Thứ Tư tuần trước | Thứ Hai tuần này | 5 |
| D — Sửa lỗi hiển thị | Thứ Sáu tuần trước | Thứ Ba tuần này | 4 |

Tất cả mốc và kết quả trong bảng **chỉ mang tính giả định**. Nếu C và D kết thúc trong tuần này, **throughput tuần này là hai hạng mục** theo bảng. Muốn xem chu kỳ phân bố đầy đủ, nhóm cần nhiều hạng mục đã hoàn tất hơn và một định nghĩa hạng mục nhất quán.

Đối với hạng mục **E vẫn đang làm**, không có cycle time hoàn tất; nhóm theo dõi **work item age** của E để nhận biết rủi ro trễ. Không nên bỏ E khỏi cuộc thảo luận chỉ vì nó chưa góp vào throughput.

## 8. Service Level Expectation (SLE): dự báo có mức bất định

SLE là **kỳ vọng về thời gian hạng mục đi qua workflow**, thường được diễn đạt bằng **khoảng thời gian và tỷ lệ phần trăm**. Ví dụ:

> “Dựa trên dữ liệu phù hợp, chúng tôi kỳ vọng **85% hạng mục tiêu chuẩn** hoàn tất trong **8 ngày lịch hoặc ít hơn**, tính từ lúc bắt đầu xử lý tới điểm Done đã định.”

SLE khác với lời hứa “mọi việc chắc chắn xong trong tám ngày”. Nếu được xây từ lịch sử đáng tin, SLE giúp nhóm **trao đổi mức tin cậy** và **nhận biết hạng mục đang già đi**. Nếu chưa có dữ liệu, nhóm có thể bắt đầu bằng một giả định SLE để học, nhưng phải đánh dấu là **giả định ban đầu** và điều chỉnh khi có quan sát.

### 8.1. Ví dụ cách hình thành SLE từ dữ liệu

Giả sử 20 hạng mục tương đối cùng loại vừa hoàn tất, trong đó **17 hạng mục có cycle time không quá 8 ngày**.

Tỷ lệ quan sát được là:

\[
\frac{17}{20}\times100\%=85\%
\]

Từ dữ liệu này, nhóm có thể **thử** một SLE “85% trong 8 ngày” và xem lại ở những tuần tiếp theo. **20 mẫu là ít**, có thể không đại diện khi nhân sự, loại việc hoặc phụ thuộc thay đổi. Một tỷ lệ quan sát 85% không chứng minh xác suất thực tế luôn đúng 85%, cũng không thay thế các nghĩa vụ hợp đồng có mức dịch vụ chính thức.

### 8.2. SLE khác SLA

| Khái niệm | Ý nghĩa |
| --- | --- |
| **SLE — Service Level Expectation** | Kỳ vọng dự báo flow của một loại hạng mục theo định nghĩa workflow, dùng để quản lý và giao tiếp. |
| **SLA — Service Level Agreement** | Cam kết mức dịch vụ được thỏa thuận, có thể bao gồm nghĩa vụ hợp đồng hoặc hậu quả nếu không đạt. |
| **SLO — Service Level Objective** | Mục tiêu mức dịch vụ, thường dùng trong vận hành độ tin cậy; không mặc nhiên là cam kết hợp đồng. |

Không nên đưa một SLE nội bộ vào hợp đồng rồi gọi là SLA mà không xác định lại định nghĩa, tác động pháp lý, loại việc, ngoại lệ và cách đo. Ngược lại, khi có SLA bắt buộc, nhóm cần thiết kế workflow để chủ động quản lý rủi ro vi phạm.

### 8.3. Dùng SLE để ưu tiên việc đang làm

Nếu SLE dự kiến phần lớn hạng mục tiêu chuẩn hoàn tất trong tám ngày mà một mục đã đạt tuổi bảy ngày, nhóm cần hỏi tại sao. Một chính sách thực dụng là xem các hạng mục **già nhất** trước khi kéo việc mới, nhưng không có nghĩa phải bỏ qua một sự cố bảo mật nghiêm trọng để bảo vệ con số SLE. Ưu tiên vẫn dựa vào giá trị, rủi ro, chính sách và mức độ khẩn cấp.

## 9. Từ dữ liệu tới hiểu biết về dòng công việc

Chỉ số flow có giá trị khi giải thích được **điều đang xảy ra trong workflow** và giúp nhóm chọn hành động. Một chỉ số đơn lẻ thường không đủ.

### 9.1. Mối quan hệ theo Little's Law và điều kiện sử dụng

Trong một hệ thống dòng **đủ ổn định**, cùng ranh giới đo và các giả định phù hợp, định luật Little cho mối quan hệ giữa lượng công việc trung bình, tốc độ hoàn tất trung bình và thời gian trung bình trong hệ thống:

\[
\text{WIP trung bình} = \text{Throughput trung bình} \times \text{Cycle time trung bình}
\]

Suy ra:

\[
\text{Cycle time trung bình} \approx
\frac{\text{WIP trung bình}}{\text{Throughput trung bình}}
\]

**Ví dụ minh họa:** Một workflow ổn định có WIP trung bình **8 hạng mục**, throughput trung bình **4 hạng mục/tuần**. Khi ranh giới đo và các điều kiện áp dụng nhất quán, thời gian trung bình trong workflow xấp xỉ **2 tuần/hạng mục**.

Nếu throughput vẫn khoảng 4 hạng mục/tuần và WIP trung bình giảm xuống **5 hạng mục** trong điều kiện tương tự, phép tính cho thời gian trung bình khoảng **1,25 tuần**. Điều này cho thấy vì sao giảm lượng việc đồng thời có thể cải thiện thời gian tới giá trị mà không nhất thiết tăng số giờ làm việc.

**Không diễn giải quá mức:**

- Đây là quan hệ giữa **các đại lượng trung bình ở trạng thái đủ ổn định**, không phải công thức hứa ngày hoàn tất của một ticket riêng lẻ.
- Nếu lượng việc liên tục tăng, tồn đọng biến đổi mạnh, loại việc thay đổi hoặc các mục được đo ở những ranh giới khác nhau, suy luận đơn giản có thể sai.
- Giảm WIP bằng cách giấu hoặc hủy việc mà không ghi nhận đúng **không phải cải tiến flow**.
- Để đánh giá độ tin cậy của thời gian hoàn tất, phải xem **phân bố cycle time**, không chỉ số trung bình.

### 9.2. Khi WIP tăng nhưng throughput không tăng

Hãy giả định trong bốn tuần, nhóm quan sát:

| Tuần | WIP cuối tuần | Throughput tuần | Điều nhóm ghi nhận |
| --- | ---: | ---: | --- |
| 1 | 7 | 4 | Review tương đối ổn. |
| 2 | 9 | 4 | Ba mục bắt đầu chờ review. |
| 3 | 11 | 3 | Reviewer chủ chốt bận hỗ trợ production. |
| 4 | 13 | 4 | Nhiều việc bị mở mới, hàng đợi review tăng. |

Các số liệu **giả định** nhưng minh họa một dấu hiệu đáng xem: **công việc trong hệ thống phình ra mà đầu ra hoàn tất không cải thiện**. Nhóm nên kiểm tra thời gian chờ theo trạng thái, công việc già nhất, khả năng review, cách chia hạng mục và chính sách kéo.

Không vội kết luận “Developers cần viết code nhanh hơn”. Nếu điểm nghẽn nằm ở review hoặc môi trường kiểm thử, tăng tốc phát triển có thể chỉ tạo thêm hàng đợi.

### 9.3. Cumulative Flow Diagram (CFD) để xem dòng tích tụ

Một **Cumulative Flow Diagram** biểu diễn số lượng tích lũy của hạng mục theo các trạng thái workflow qua thời gian. Bằng cách nhìn vùng biểu thị WIP, chỗ phình to và độ dốc các đường hoàn tất, nhóm có thể đặt câu hỏi:

- WIP đang tăng hay ổn định?
- Một trạng thái có ngày càng tích tụ nhiều hạng mục không?
- Tốc độ công việc vào hệ thống có vượt tốc độ hoàn tất trong một giai đoạn không?
- Một thay đổi chính sách kéo có giúp giảm hàng đợi về sau không?

CFD không tự giải thích nguyên nhân; nó chỉ cho thấy **mẫu hình cần điều tra**. Nếu thay cách phân loại hoặc cách đo mà không ghi nhận, biểu đồ có thể tạo cảm giác xuất hiện nút thắt dù đó chỉ là thay đổi định nghĩa.

### 9.4. Scatterplot và biểu đồ tuổi công việc

- **Cycle time scatterplot:** Mỗi điểm là một hạng mục đã hoàn tất, đặt theo ngày hoàn tất và thời gian từ start tới finish. Nhìn được độ phân tán, ngoại lệ và xu hướng.
- **Work item aging chart:** Cho thấy tuổi của các hạng mục chưa hoàn tất, thường theo trạng thái hiện tại. Hữu ích để chọn việc cần hỗ trợ **hôm nay**, thay vì chờ phân tích kết quả sau khi ticket đã đóng.
- **Biểu đồ thời gian chờ theo trạng thái:** Giúp nhận ra review, kiểm thử, chờ phê duyệt hay chờ phát hành chiếm phần lớn thời gian.

Một hạng mục có cycle time dài có thể là dấu hiệu của phụ thuộc, công việc quá lớn hoặc mức rủi ro cao. Không nên mặc định đó là “người làm chậm” nếu chưa xét ngữ cảnh.

### 9.5. Flow efficiency và giới hạn của nó

Một cách biểu diễn **flow efficiency** là:

\[
\text{Flow efficiency} =
\frac{\text{Thời gian thực sự xử lý hạng mục}}
{\text{Tổng thời gian hạng mục ở trong luồng}}
\times 100\%
\]

Nếu một hạng mục cần 12 giờ xử lý thực tế nhưng nằm trong workflow 60 giờ làm việc theo cùng đơn vị đo, flow efficiency tính theo mô hình đó là **20%**. Điều này gợi ý thời gian chờ đáng xem xét.

Tuy nhiên, việc tách thời gian “xử lý” với “chờ” không luôn đơn giản: một số hoạt động như kiểm thử tự động, chờ dữ liệu có chủ đích hoặc kiểm soát rủi ro là cần thiết. **Flow efficiency không phải tỷ lệ làm việc hiệu quả của một cá nhân**. Không dùng nó để thúc mọi người báo cáo số giờ “bận rộn” hay loại bỏ bước kiểm soát chất lượng quan trọng.

## 10. Vòng phản hồi: quản lý flow là hoạt động liên tục

Một workflow chỉ cải thiện khi các bên **xem dữ liệu, trao đổi trở ngại và thay đổi chính sách**. Kanban không đòi mọi nhóm tổ chức cùng một bộ cuộc họp cố định, nhưng nhịp kiểm tra phù hợp giúp công việc không bị quên.

### 10.1. Các loại trao đổi nhóm có thể thiết kế

| Mục đích | Câu hỏi thường hữu ích | Tần suất minh họa |
| --- | --- | --- |
| **Xem flow hằng ngày** | Hạng mục nào già nhất? Review hoặc test có bị chặn? Có thể giúp hoàn tất trước khi kéo việc mới? | 10–15 phút mỗi ngày làm việc nếu hữu ích. |
| **Bổ sung công việc (replenishment)** | Năng lực sắp trống nên kéo mục nào tiếp? Hạng mục có đủ rõ, đủ giá trị và đáp ứng chính sách không? | Khi hàng đợi cần bổ sung; có thể định kỳ hoặc theo tín hiệu. |
| **Xem mức dịch vụ** | SLE có còn phù hợp? Những loại việc nào thường vượt kỳ vọng và vì sao? | Hằng tuần hoặc định kỳ có đủ dữ liệu. |
| **Xem delivery / khách hàng** | Người dùng đã nhận giá trị gì, rủi ro và phản hồi nào đòi thay đổi ưu tiên? | Theo nhịp phát hành và phản hồi sản phẩm. |
| **Cải tiến workflow** | Chính sách nào đang gây chờ? Thử nghiệm nào giảm chi phí dòng công việc mà vẫn giữ chất lượng? | Sau khi đủ bằng chứng hoặc tại vòng cải tiến định kỳ. |

Tần suất trong bảng là **ví dụ**, không phải nghi thức bắt buộc. Mỗi cuộc trao đổi cần có mục đích và kết quả. Nếu chỉ đọc tên thẻ trên bảng nhưng không giúp ra quyết định, nhóm nên cải tiến cách xem bảng.

### 10.2. Đi bảng từ phía gần Done về phía bắt đầu

Một cách dùng bảng Kanban trong cuộc xem flow là **đi từ phải sang trái**:

1. Có hạng mục nào đang chờ kiểm thử hoặc phát hành để thành Done?
2. Review có đầy không? Ai có thể hỗ trợ hoàn tất?
3. Việc nào bị chặn, đã chờ bao lâu, ai có thể gỡ?
4. Hạng mục nào đang già hơn kỳ vọng?
5. Chỉ khi còn năng lực và chính sách cho phép, nên kéo việc nào mới?

Không có quy tắc mọi nhóm **bắt buộc** đi theo thứ tự này, nhưng nó giúp chống phản xạ mở việc mới trước khi hoàn tất giá trị đã đầu tư.

### 10.3. Policies phải rõ ràng và được xem lại

Ví dụ một chính sách kéo hạng mục:

~~~text
KHI CÓ CHỖ TRONG "ĐANG PHÁT TRIỂN":
  1. Kiểm tra việc gần Done và việc bị chặn đang cần hỗ trợ.
  2. Nếu có thể giúp hoàn tất mục đang làm, ưu tiên việc đó.
  3. Nếu không, chọn mục ưu tiên cao nhất ở "Sẵn sàng".
  4. Kiểm tra mục có tiêu chí chấp nhận, phụ thuộc và người phối hợp rõ.
  5. Kéo mục vào workflow, ghi thời điểm bắt đầu.
~~~

Ví dụ một chính sách blocked:

~~~text
KHI BỊ CHẶN:
  - Gắn dấu blocked, nêu nguyên nhân và mốc phát hiện.
  - Xác định người có thể hỗ trợ hoặc quyết định tiếp theo.
  - Giữ tuổi công việc phản ánh đúng thời gian thực tế.
  - Xem lại trong cuộc kiểm tra flow tiếp theo.
  - Không mở vô hạn việc mới để che khoảng chờ.
~~~

Chính sách nên **đủ rõ để các thành viên hành động nhất quán**, nhưng cũng đủ đơn giản để cải tiến khi có dữ liệu. Không cần một bộ quy trình phê duyệt cồng kềnh chỉ để chuyển một thẻ qua cột.

## 11. Cải tiến workflow: từ nút thắt tới thí nghiệm

Một vòng cải tiến có thể gồm sáu bước:

1. **Quan sát tín hiệu:** WIP tăng, cycle time dài, hạng mục già hoặc throughput biến động.
2. **Xác định vùng cần xem:** Review, test, môi trường, phụ thuộc hay chia việc quá lớn?
3. **Đề xuất giả thuyết:** “Nếu chúng ta hỗ trợ review trước khi kéo việc mới, thời gian chờ review sẽ giảm.”
4. **Thiết kế thử nghiệm nhỏ:** Chính sách cụ thể, thời gian thử, người tham gia và chỉ số bảo vệ.
5. **Thực hiện và đo:** Giữ dữ liệu trước/sau cùng định nghĩa, lưu thay đổi về loại việc và năng lực.
6. **Xem lại và quyết định:** Giữ, điều chỉnh hoặc bỏ chính sách; ghi rủi ro còn tồn tại.

~~~mermaid
flowchart LR
    A["Nhìn flow: WIP, age, cycle time, throughput"] --> B["Chọn điểm nghẽn đáng xử lý"]
    B --> C["Giả thuyết cải tiến và chính sách thử"]
    C --> D["Thử nhỏ, giữ chất lượng"]
    D --> E["Đo dữ liệu và phản hồi"]
    E --> F{"Có cải thiện có ý nghĩa?"}
    F -->|Có| G["Giữ và chuẩn hóa chính sách"]
    F -->|Chưa rõ hoặc không| H["Điều chỉnh / thử cách khác"]
    G --> A
    H --> A
~~~

### 11.1. Ví dụ thử nghiệm giảm tắc review

**Quan sát:** Trong bốn tuần, cột Review thường chứa 5–7 việc, cycle time của nhiều mục kéo dài trong khi Developers vẫn bắt đầu story mới.

**Giả thuyết:** Đa nhiệm và thiếu người ưu tiên review làm hàng đợi tăng.

**Thử nghiệm hai tuần minh họa:**

- Giới hạn Review ở **hai mục**, làm rõ trường hợp ngoại lệ.
- Trước khi bắt đầu việc mới, Developers kiểm tra có hạng mục đang chờ review cần giúp không.
- Chia user story quá lớn thành lát cắt dọc có tiêu chí chấp nhận rõ.
- Theo dõi WIP, tuổi việc, thời gian chờ review và lỗi sau merge.

**Điều kiện bảo vệ:** Không bỏ review, không hợp thức hóa thay đổi chưa kiểm thử để rút ngắn số liệu.

**Đánh giá:** Nếu thời gian chờ giảm mà lỗi không tăng, chính sách có cơ sở để tiếp tục thử. Nếu review vẫn chậm vì chỉ một người có quyền duyệt, nhóm cần tháo điểm phụ thuộc và chia sẻ năng lực; chỉ đổi con số giới hạn sẽ không đủ.

### 11.2. Cẩn thận với kết luận nhân quả

Nếu cycle time sau hai tuần giảm, có thể do:

- Chính sách mới thực sự giúp bớt chờ.
- Các hạng mục tuần sau nhỏ hơn tuần trước.
- Không có sự cố production hoặc ngày nghỉ.
- Một số hạng mục khó vẫn còn WIP và chưa xuất hiện trong số cycle time đã hoàn tất.

Nên xem **work item age của việc đang mở**, loại hạng mục, lỗi và phản hồi định tính. Không tuyên bố cải tiến đã “tăng năng suất 40%” chỉ từ so sánh hai trung bình không tương đương.

## 12. Ví dụ xuyên suốt: cải tiến dòng giá trị cho ứng dụng đặt lịch

Giả sử một nhóm sáu người phụ trách ứng dụng đặt lịch tư vấn. Nhóm tiếp nhận user story, bug và cải tiến hạ tầng. Họ giao được tính năng nhưng khách thường phải đợi nhiều tuần sau khi yêu cầu đã được ưu tiên. Toàn bộ chi tiết và số liệu dưới đây là **tình huống giả định để học**.

### 12.1. Trạng thái ban đầu

Workflow ban đầu chỉ có:

~~~text
Backlog -> Doing -> Done
~~~

Trong cuộc họp, Developers cho biết “đã code xong”, nhưng nhiều thẻ vẫn ở Doing do chờ review, kiểm thử hoặc phát hành. Một số thẻ bị đưa sang Done ngay khi merge code, dù khách chưa sử dụng được.

**Vấn đề chính:** Ranh giới “Done” thiếu thống nhất, các hàng đợi bị che và không có dữ liệu tin cậy về thời gian đến giá trị.

### 12.2. Nhóm vẽ lại workflow

Sau một buổi quan sát công việc thật, nhóm thống nhất:

~~~text
Ý tưởng -> Làm rõ -> Sẵn sàng
                          |
                          v
                 Phát triển [WIP 3]
                          |
                          v
                   Review [WIP 2]
                          |
                          v
               Kiểm thử / Giao [WIP 2]
                          |
                          v
                        Đã giao
~~~

Nhóm chọn điểm bắt đầu khi kéo từ Sẵn sàng vào Phát triển; điểm kết thúc khi việc được giao theo chính sách phát hành. Họ ghi cả thời gian yêu cầu ở backlog để có thể xem một **lead time rộng hơn** bên cạnh cycle time nội bộ.

Nhóm cũng định nghĩa:

- **Ready:** mục có kết quả mong muốn, tiêu chí chấp nhận đủ để bắt đầu, phụ thuộc được ghi.
- **Review:** thay đổi sẵn sàng được xem xét bằng tiêu chí chung, người liên quan có quyền truy cập.
- **Test/Giao:** kiểm thử liên quan đạt; phát hành theo chính sách an toàn.
- **Blocked:** nêu lý do, người hỗ trợ và tuổi của hạng mục.
- **Ưu tiên:** Product Owner sắp thứ tự hạng mục sản phẩm cùng nhóm; sự cố nghiêm trọng theo playbook riêng.

Giới hạn WIP **3–2–2** là điểm khởi đầu để học, không được tuyên bố là cấu hình tối ưu.

### 12.3. Tuần đầu: phát hiện nút thắt

Nhóm nhận thấy:

| Dấu hiệu | Quan sát minh họa | Giải thích cần kiểm tra |
| --- | --- | --- |
| Cột Review thường đầy | Hai việc trong Review, ba việc khác đang chờ được kéo sang. | Năng lực review hoặc cách chia việc có thể chưa phù hợp. |
| Một story đã bắt đầu 12 ngày | Chờ quyết định từ đối tác về hành vi API. | Có phụ thuộc chưa được làm rõ trước khi kéo. |
| Nhiều bug xen vào công việc feature | Mỗi người ngắt việc để xử lý yêu cầu “gấp”. | Chính sách khẩn cấp và dự báo năng lực chưa rõ. |
| Khách nhận giá trị muộn | Code merge nhưng phải chờ lịch triển khai. | Ranh giới Done cần tính tới phát hành, không chỉ kết thúc code. |

**Quyết định:** Nhóm ưu tiên làm rõ phụ thuộc API, tăng khả năng review và đồng bộ chính sách Done. Chưa tìm cách bắt đầu nhiều feature hơn.

### 12.4. Tuần thứ hai: thử giảm WIP và kéo việc

Trong hai tuần tiếp theo, nhóm:

1. Ưu tiên **hoàn tất các mục gần Done** trong cuộc xem flow hằng ngày.
2. Giảm việc đang làm, không để mỗi thành viên mặc nhiên mở nhiều ticket.
3. Làm rõ tiêu chí chuyển trạng thái và kỳ vọng reviewer phản hồi.
4. Dùng **pair programming** cho phần tích hợp khó để giảm phụ thuộc vào một cá nhân.
5. Phân biệt lỗi production nghiêm trọng với yêu cầu đổi giao diện bình thường.
6. Tiếp tục ghi cycle time, throughput và tuổi hạng mục chưa hoàn tất.

### 12.5. Đánh giá dựa trên dữ liệu minh họa

| Chỉ số | Bốn tuần trước thử | Bốn tuần sau thử |
| --- | ---: | ---: |
| WIP trung bình | 12 hạng mục | 7 hạng mục |
| Throughput trung bình | 4 hạng mục/tuần | 4 hạng mục/tuần |
| Cycle time trung vị | 13 ngày | 9 ngày |
| Tỷ lệ mục vượt kỳ vọng 14 ngày | 45% | 30% |
| Lỗi hồi quy nghiêm trọng phát hiện sau giao | 2 | 1 |

Các số liệu chỉ **giả định và nhằm minh họa cách đọc**. Chúng có vẻ gợi ý WIP và cycle time được cải thiện mà throughput không giảm, nhưng nhóm vẫn phải xem loại việc, thời gian chờ, các mục đang mở và cách đo. Không kết luận tất cả thay đổi đến từ WIP limit nếu bối cảnh trước/sau khác nhau.

### 12.6. Kết nối flow với kết quả người dùng

Giả sử nhóm giao nhanh tính năng xác nhận đặt lịch. Điều tiếp theo không chỉ là đếm ticket: người dùng có **hiểu trạng thái xác nhận**, có hoàn tất đặt lịch và có ít yêu cầu hỗ trợ hơn không? Có tăng lỗi tạo trùng hay rủi ro riêng tư không?

Một **dòng giá trị tối ưu** phải chuyển công việc thành kết quả hữu ích **mà không phá chất lượng**. Nếu nhóm rút cycle time nhờ bỏ kiểm thử cạnh tranh, chỉ số flow tốt lên nhưng khả năng tạo giá trị bền vững đi xuống.

### 12.7. Điều gì xảy ra khi giả định thay đổi?

Sau khi phát hành một lát cắt, người dùng phản hồi họ quan tâm trạng thái xác nhận hơn bộ lọc nâng cao. Product Owner cập nhật thứ tự backlog. Nhóm Kanban kéo mục mới khi có năng lực, không cần giữ hàng đợi cũ chỉ để “đúng kế hoạch”, nhưng vẫn làm rõ lý do, chi phí trì hoãn và công việc nào phải hoãn.

Đây là kết nối trực tiếp với Agile: **phản hồi sớm → thay đổi quyết định → giao phần nhỏ tiếp theo → đo và học**.

## 13. Kanban, Scrum và XP: lựa chọn hoặc kết hợp

Kanban không bắt buộc Sprint, vai trò Product Owner hay một bộ sự kiện cố định. Scrum lại xác định Sprint, Scrum Team, các sự kiện, artifact và commitment. **Có thể kết hợp thực hành flow của Kanban vào Scrum**, miễn là không làm mất các phần thiết yếu của Scrum khi nhóm tuyên bố đang dùng Scrum.

| Nhu cầu | Kanban hỗ trợ | Scrum hỗ trợ | XP hỗ trợ |
| --- | --- | --- | --- |
| Cần thấy công việc đang bị chặn ở đâu | Workflow rõ, thẻ blocked, work item age, WIP. | Sprint Backlog minh bạch và Daily Scrum xem tiến độ Sprint Goal. | Kiểm thử và tích hợp thường xuyên giúp lộ vấn đề kỹ thuật. |
| Cần tập trung kết quả ưu tiên | Pull, giới hạn WIP, chính sách bổ sung công việc. | Product Goal, Sprint Goal và Product Backlog có thứ tự. | Chia thay đổi nhỏ, thiết kế đơn giản. |
| Cần giảm rủi ro khi thay đổi | Chu kỳ phản hồi và quan sát thời gian tới Done. | Sprint Review và Retrospective để kiểm tra, thích ứng. | TDD, CI, refactoring và pair programming. |
| Có nhiều bug/hỗ trợ ngoài kế hoạch | Trực quan hóa, chính sách expedite và ngày hạn cố định. | Làm rõ ảnh hưởng tới Sprint Goal và thương lượng phạm vi. | Tự động kiểm thử để ngăn lỗi tái phát. |
| Cần dự báo giao hạng mục | Cycle time, throughput, SLE và aging. | Lập kế hoạch theo mục tiêu Sprint và năng lực thực tế. | Tăng khả năng delivery ổn định qua chất lượng kỹ thuật. |

### 13.1. Khi nào workflow liên tục là lựa chọn phù hợp?

Một đội phụ trách lỗi, hỗ trợ và cải tiến nhỏ nhận việc không đều có thể phù hợp với **pull liên tục** và các vòng phản hồi Kanban. Một nhóm sản phẩm cần mục tiêu kết quả theo từng Sprint có thể dùng Scrum, nhưng vẫn dùng Kanban để giảm WIP và quan sát flow.

Không nên quyết định chỉ dựa vào khẩu hiệu “Kanban linh hoạt hơn Scrum” hoặc “Scrum kỷ luật hơn Kanban”. Cần xem loại nhu cầu, phụ thuộc, quyền quyết định, mức bất định, khả năng kiểm tra kết quả và những vấn đề đang thực sự xảy ra.

### 13.2. Kanban không loại bỏ kế hoạch hay backlog

Một workflow pull vẫn cần **quyết định ưu tiên đầu vào**, xác định đủ điều kiện sẵn sàng, chính sách hạng mục có hạn và khả năng đáp ứng mức dịch vụ. Nếu luôn kéo việc mới nhất mà không quan tâm Product Goal và chi phí trì hoãn, bảng Kanban chỉ che một backlog thiếu định hướng.

### 13.3. Phản hồi kỹ thuật phải đủ nhanh để flow có ý nghĩa

Nếu các hạng mục thường không thể rời cột Review vì CI liên tục hỏng hoặc mã quá khó sửa, quản lý bảng không thay thế đầu tư kỹ thuật. Các thực hành XP như **TDD, CI, refactoring, pair programming** giúp giảm chi phí thay đổi và tăng khả năng hoàn tất an toàn.

Thực hành kỹ thuật và quản lý dòng **bổ sung nhau**. Kanban giúp thấy vấn đề hệ thống; XP có thể cung cấp kỹ thuật để xử lý một phần vấn đề; Scrum có thể cung cấp mục tiêu và nhịp kiểm tra sản phẩm phù hợp.

## 14. Những ngộ nhận thường làm Kanban mất tác dụng

| Ngộ nhận | Hệ quả | Cách nhìn và hành động đúng |
| --- | --- | --- |
| “Có bảng To do–Doing–Done là đang thực hành Kanban.” | Không biết ranh giới, điểm chặn, WIP hay độ tin cậy giao hàng. | Định nghĩa workflow và chính sách, quản lý hạng mục, đo và cải tiến. |
| “Kanban nghĩa là không cần kế hoạch.” | Việc được kéo tùy hứng, thiếu giá trị và người chịu trách nhiệm. | Làm rõ ưu tiên, chính sách bổ sung việc và kỳ vọng dịch vụ. |
| “Càng nhiều việc đang làm càng năng suất.” | Hàng đợi và chuyển ngữ cảnh tăng, thời gian tới Done dài. | Giới hạn WIP, ưu tiên hoàn tất và xử lý điểm chặn. |
| “WIP limit là chỉ tiêu để phạt người làm.” | Người dùng giấu hoặc chia thẻ hình thức để không vượt giới hạn. | Dùng giới hạn làm tín hiệu cải tiến hệ thống, không đo phẩm chất cá nhân. |
| “Bị chặn thì bỏ thẻ khỏi bảng.” | WIP, tuổi việc và rủi ro bị che. | Hiển thị blocked, người xử lý và cập nhật dự báo minh bạch. |
| “Một hạng mục ở Done khi đã xong code.” | Báo cáo flow tốt nhưng người dùng chưa nhận giá trị. | Định nghĩa Done rõ, đo thêm đến phát hành/kết quả khi cần. |
| “Throughput càng cao chứng minh sản phẩm càng có giá trị.” | Nhóm tối ưu ticket nhỏ, tránh hạng mục có tác động. | Kết hợp outcome, chất lượng, loại việc và dữ liệu flow. |
| “Cycle time trung bình = ngày chắc chắn hoàn tất.” | Hứa hẹn không phản ánh biến động, rủi ro cao. | Xem phân bố, SLE, work item age và bất định. |
| “Giới hạn WIP cố định mãi, không được thay.” | Chính sách không thích ứng khi workflow/năng lực đổi. | Đặt giả thuyết, thử giới hạn mới và so bằng chứng. |
| “Mọi việc gấp đều được vào expedite.” | Làn khẩn cấp quá tải, việc chuẩn thường xuyên bị dừng. | Làm rõ tiêu chí khẩn, quyền quyết định và hậu quả. |
| “Giảm cycle time bằng cách bỏ review và kiểm thử.” | Lỗi và nợ kỹ thuật tăng; khách chịu rủi ro. | Bảo vệ chất lượng; giảm chờ và lãng phí thực sự. |
| “Kanban chỉ dành cho nhóm sửa bug.” | Bỏ lỡ cách cải tiến flow của feature và discovery. | Dùng cho workflow có hạng mục và ranh giới rõ, tùy bối cảnh. |
| “Dùng Kanban thì không được dùng Scrum hoặc XP.” | Tranh luận phương pháp thay vì xử lý điểm nghẽn. | Có thể bổ trợ nếu giữ rõ trách nhiệm và mục đích của từng cách. |

## 15. Bài tập tình huống

### Tình huống A — Review nghẽn, nhưng mọi người vẫn mở việc mới

Một nhóm có workflow Phát triển → Review → Kiểm thử → Done. Đầu tuần có **4 mục Review**, hai người viết code đang mở thêm **3 story**. Thời gian chờ review của những mục cũ đã đạt năm ngày.

**Câu hỏi:**

1. Dấu hiệu nào cho thấy nút thắt không đơn thuần ở tốc độ viết mã?
2. Chính sách WIP hoặc pull nào có thể thử mà không làm giảm chất lượng?
3. Trong cuộc xem flow, nên hỏi điều gì về hạng mục già nhất?
4. Nên đo những gì sau hai tuần?

**Gợi ý giải:** Xem tuổi các mục đang chờ review, số người có thể review và quy tắc chuyển cột. Thử giới hạn WIP Review, ưu tiên hỗ trợ hoàn tất trước kéo việc mới, chia nhỏ các story quá lớn, kiểm tra review có phụ thuộc một cá nhân không. Đo WIP, thời gian chờ, phân bố cycle time, throughput và lỗi hồi quy; không coi thay đổi của một tuần là bằng chứng nhân quả chắc chắn.

### Tình huống B — Product Owner muốn tăng tốc một hạng mục “nhỏ”

Nhóm đang có ba mục gần Done. Product Owner yêu cầu thêm một bộ lọc nâng cao và nói “chỉ mất một ngày code”, nhưng cần thay đổi API và kiểm thử quyền truy cập.

**Câu hỏi:**

1. Cần biết gì trước khi kéo hạng mục vào workflow?
2. Nếu vượt WIP limit, nhóm có những phương án nào?
3. Giá trị và chi phí trì hoãn có thể được làm rõ thế nào?

**Gợi ý giải:** Xác định kết quả người dùng, phụ thuộc, phạm vi và chuẩn chất lượng. Nếu không cấp bách, để trong hàng đợi có thứ tự; kéo khi có năng lực. Có thể chia lát cắt nhỏ hơn hoặc thay ưu tiên các mục khác nhưng phải công khai phần bị hoãn. Không dùng ước lượng “một ngày code” thay cho thời gian qua review, test và phát hành.

### Tình huống C — Lỗi production cần xử lý ngay

Hệ thống đặt lịch bắt đầu tạo lịch trùng khi mạng không ổn định, ảnh hưởng khách thật. Tất cả cột đang đầy WIP limit.

**Câu hỏi:**

1. Có nên giữ WIP limit bằng mọi giá rồi đợi đến tuần sau?
2. Chính sách expedite cần quy định điều gì?
3. Sau sự cố, nên cải tiến dòng công việc như thế nào?

**Gợi ý giải:** Kích hoạt ứng cứu theo quyền hạn để giảm thiệt hại, công khai năng lực và công việc bị gián đoạn, không che WIP. Chính sách phải nêu tiêu chí, người quyết định, mức thông báo và điều kiện kết thúc ngoại lệ. Sau sự cố, phân tích vì sao lỗi lọt, bổ sung kiểm thử và quan sát hệ thống; đánh giá tác động tới flow và backlog.

### Tình huống D — SLE và việc già đi

Một nhóm có SLE nội bộ **85% hạng mục tiêu chuẩn hoàn tất trong 8 ngày**. Hôm nay một hạng mục đã bắt đầu **10 ngày** nhưng chưa xong vì đang chờ đối tác trả lời.

**Câu hỏi:**

1. Hạng mục này có cycle time hoàn tất chưa? Chỉ số nào đúng lúc này?
2. SLE có nghĩa là tổ chức đã tự động vi phạm hợp đồng không?
3. Nhóm nên làm gì tiếp?

**Gợi ý giải:** Hạng mục chưa hoàn tất nên theo dõi **work item age = 10 ngày**, không gán cycle time kết thúc. SLE là kỳ vọng dự báo, không mặc nhiên là SLA. Làm rõ điểm chặn, phối hợp với đối tác, xem phương án xử lý tạm và cập nhật dự báo với người quan tâm. Không đặt lại ngày bắt đầu để “xóa quá hạn”.

### Tình huống E — Đo flow tốt nhưng khách hàng vẫn không hài lòng

Nhóm giảm cycle time trung vị từ 12 xuống 7 ngày, throughput tăng, nhưng số yêu cầu hỗ trợ và tỷ lệ người dùng bỏ dở đặt lịch không cải thiện.

**Câu hỏi:**

1. Vì sao chỉ số flow tốt hơn chưa đủ chứng minh đã tối ưu dòng giá trị?
2. Cần thêm bằng chứng nào về người dùng và chất lượng?
3. Product Owner và nhóm kỹ thuật nên hợp tác ra sao?

**Gợi ý giải:** Xem loại hạng mục đã giao, nhu cầu thực, phản hồi về khả năng sử dụng, lỗi và dữ liệu outcome. Có thể nhóm đang hoàn tất nhanh các mục ít giá trị. Làm rõ lại giả định, thử user story có tác động hơn và tiếp tục giữ chất lượng/độ ổn định. Kanban làm rõ flow, còn việc chọn giá trị cần quyết định sản phẩm tốt.

### Bài tập tính nhanh

**Dữ kiện giả định:** Một workflow tương đối ổn định có **WIP trung bình = 9 mục** và **throughput trung bình = 3 mục/tuần**.

1. Theo quan hệ Little's Law ở điều kiện phù hợp, cycle time trung bình ước khoảng bao nhiêu tuần?
2. Nếu nhóm giảm WIP trung bình xuống **6 mục** mà throughput vẫn giữ 3 mục/tuần, mô hình cho khoảng thời gian trung bình bao nhiêu?
3. Tại sao **không** được hứa mọi hạng mục chắc chắn hoàn tất trong khoảng thời gian vừa tính?
4. Nếu có một việc đang mở đã 20 ngày, chỉ số nào phải được quan sát và thảo luận ngay?

**Đáp án tham khảo:** (1) \(9/3 = 3\) tuần; (2) \(6/3 = 2\) tuần; (3) đây là quan hệ trung bình ở hệ ổn định, còn phân bố, rủi ro và loại việc có thể rất khác; (4) **work item age** và lý do bị chặn, kết hợp SLE nếu có.

## 16. Bài thực hành nhóm: thiết kế một hệ thống Kanban đầu tiên

Một nhóm phát triển nền tảng đặt lịch đang gặp tình trạng story kéo dài vì chờ review và môi trường. Hãy tổ chức workshop 45–60 phút với người nắm nghiệp vụ, Developers, người kiểm thử, vận hành và người quản lý ưu tiên khi phù hợp.

### Yêu cầu thực hiện

1. Chọn **một loại dịch vụ công việc rõ** để tối ưu, ví dụ “thay đổi ứng dụng từ khi bắt đầu triển khai tới khi phát hành”.
2. Vẽ workflow thực tế từ việc đã hoàn tất gần đây; phân biệt làm việc và chờ đợi.
3. Thống nhất **điểm bắt đầu và kết thúc**, các trạng thái, loại hạng mục và chính sách chuyển cột.
4. Đặt WIP limit **giả định để thử**, nêu lý do và điều kiện điều chỉnh, không sao chép số của nhóm khác.
5. Xác định chính sách khi blocked, khi có sự cố khẩn cấp và khi bổ sung việc từ backlog.
6. Chọn bốn chỉ số cốt lõi để thu thập theo định nghĩa nhất quán.
7. Viết một kỳ vọng SLE sơ bộ dựa trên dữ liệu nếu có; nếu thiếu dữ liệu, ghi rõ đây là **giả định cần hiệu chỉnh**.
8. Chọn một thí nghiệm cải tiến trong hai tuần, kèm tín hiệu outcome và chất lượng để tránh tối ưu cục bộ.

### Mẫu bàn giao của workshop

| Câu hỏi | Câu trả lời của nhóm |
| --- | --- |
| Giá trị/dịch vụ chúng ta đang giao cho ai? | ... |
| Workflow bắt đầu và kết thúc ở đâu? | ... |
| Các trạng thái thể hiện công việc thật? | ... |
| Loại hạng mục nào đi qua workflow? | ... |
| WIP limit và lý do chọn? | ... |
| Chính sách pull/replenishment? | ... |
| Điều kiện chuyển sang Review, Test và Done? | ... |
| Cách báo blocked, ai hỗ trợ, khi nào xem lại? | ... |
| Điều kiện kích hoạt expedite? | ... |
| Định nghĩa WIP, throughput, cycle time, work item age? | ... |
| SLE, nguồn dữ liệu và mức tin cậy? | ... |
| Thử nghiệm cải tiến, thời điểm kiểm tra? | ... |
| Outcome và chuẩn chất lượng cần bảo vệ? | ... |

**Tiêu chí hoàn thành workshop:** Một người mới vào nhóm có thể nhìn bảng và biết hạng mục đang ở đâu, khi nào được kéo tiếp, khi nào coi là Done và cần hỗ trợ việc nào trước. Các thành viên biết **vì sao** giới hạn WIP tồn tại và sẽ xem lại nó bằng bằng chứng, chứ không chỉ nhớ con số.

## 17. Checklist vận hành Kanban hướng tới giá trị

### Khi thiết kế workflow

- [ ] Đã xác định ai nhận giá trị và kết quả nào là quan trọng, không chỉ có cột trạng thái.
- [ ] Có Definition of Workflow rõ: hạng mục, điểm start/finish, trạng thái, chính sách và kiểm soát WIP.
- [ ] Ranh giới Done phản ánh kết quả muốn tối ưu; nếu chỉ tới code merge, đã đo riêng thời gian tới người dùng.
- [ ] Chính sách về Ready, Review, Test/Done, blocked và việc khẩn cấp được công khai.
- [ ] Hạng mục được chia đủ nhỏ để có thể hoàn tất và nhận phản hồi, không làm mất chuẩn chất lượng.

### Khi quản lý dòng hằng ngày

- [ ] WIP đang thực hiện nhìn thấy được, không che việc bị chặn hoặc quá hạn.
- [ ] Nhóm ưu tiên giúp hoàn tất việc gần Done trước khi mở quá nhiều việc mới.
- [ ] Mục có tuổi lớn được xem xét và có kế hoạch tháo điểm chặn.
- [ ] Hạng mục mới được kéo theo ưu tiên giá trị, năng lực và chính sách.
- [ ] Expedite được dùng cho trường hợp đủ tiêu chí, có người chịu trách nhiệm và tác động minh bạch.
- [ ] Không chuyển công việc chưa đủ chất lượng sang Done chỉ để đẹp chỉ số.

### Khi đo và cải tiến

- [ ] Bốn chỉ số cốt lõi được định nghĩa và thu thập nhất quán: WIP, throughput, cycle time, work item age.
- [ ] SLE được giải thích bằng phạm vi, lịch sử và giới hạn độ tin cậy, không bị hiểu như bảo đảm tuyệt đối.
- [ ] Nhóm xem phân bố và việc chưa hoàn tất, không chỉ tốc độ trung bình của ticket đã đóng.
- [ ] Đã đối chiếu flow với outcome khách hàng, lỗi và độ ổn định vận hành.
- [ ] Có thí nghiệm nhỏ, thời điểm xem lại, dữ liệu trước/sau và khả năng điều chỉnh chính sách.
- [ ] Các chỉ số được dùng để cải thiện hệ thống, không để xếp hạng năng suất từng cá nhân.

## 18. Ghi nhớ cốt lõi

**Kanban hướng tới tối ưu dòng chảy của giá trị**, không phải tối đa hóa số thẻ trên bảng hoặc mức bận rộn của từng người. Muốn đạt điều đó, nhóm cần nhìn thấy workflow thật, xác định điểm bắt đầu–kết thúc, giới hạn WIP, kéo việc theo năng lực, làm rõ chính sách và xử lý điểm chặn trước khi chúng tích tụ.

**WIP và throughput** cho biết lượng việc trong hệ thống và nhịp hoàn tất; **cycle time** cho biết các hạng mục đã xong mất bao lâu; **work item age** giúp phát hiện rủi ro ngay khi công việc còn đang xử lý; **SLE** làm kỳ vọng giao hàng minh bạch hơn. Những chỉ số này cần được hiểu theo bối cảnh, phân bố và ranh giới đo, không phải mục tiêu để thao túng.

Quan trọng nhất, Kanban phải kết nối với **việc chọn đúng nhu cầu và giao phần mềm đáng tin cậy**. Scrum có thể cung cấp nhịp mục tiêu và kiểm tra khi phù hợp; XP cung cấp thực hành kỹ thuật giảm lỗi và chi phí thay đổi; Kanban giúp toàn bộ hệ thống nhìn thấy và cải tiến thời gian từ lúc bắt đầu tới lúc giá trị được giao. Đó là nền tảng cho **phản hồi sớm, phát triển tăng dần và cải tiến liên tục** trong Agile.

### Tài liệu tham khảo nền tảng

- [The Kanban Guide](https://kanbanguides.org/) — Definition of Workflow, kiểm soát WIP, quản lý các hạng mục và các chỉ số flow.
- [Kanban University](https://kanban.university/) — tài liệu và thực hành của Kanban Method, các chính sách, vòng phản hồi và cải tiến dịch vụ.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Sprint, Product Goal, Definition of Done và trách nhiệm Scrum Team khi kết hợp thực hành Kanban.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — các giá trị Agile về cộng tác, phần mềm hoạt động và thích ứng.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — giao thường xuyên, nhịp bền vững, kỹ thuật tốt và cải tiến định kỳ.
- [DORA](https://dora.dev/) — nghiên cứu về năng lực giao thay đổi và độ ổn định của hệ thống phần mềm.
