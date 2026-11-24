# Khảo sát kỹ thuật bằng spike và nguyên mẫu có mục đích

## 1. Khi chưa biết đủ để thiết kế, nhóm nên làm gì?

Một nhóm phát triển nền tảng học trực tuyến muốn cho phép người học xem video trên điện thoại, tiếp tục trên máy tính và không mất tiến độ khi mạng chập chờn. Ý tưởng mang lại giá trị rõ ràng, nhưng Developers chưa biết:

- Có thể đồng bộ tiến độ giữa nhiều thiết bị mà không ghi đè dữ liệu mới bằng dữ liệu cũ không?
- Nếu người học xem ngoại tuyến, điều gì xảy ra khi thiết bị kết nối trở lại?
- API hiện tại chịu được tần suất cập nhật tiến độ tới mức nào?
- Có cần cơ chế xử lý sự kiện phức tạp, hay cập nhật có điều kiện trong cơ sở dữ liệu hiện tại là đủ?
- Dữ liệu tiến độ có được phép gửi tới một dịch vụ bên ngoài hay phải giữ trong hệ thống?

Nếu nhóm chọn ngay một kiến trúc lớn, họ có thể đầu tư nhiều tuần trước khi phát hiện giả định sai. Nếu nhóm chỉ tranh luận trong các cuộc họp, họ cũng không nhận được bằng chứng mới để quyết định.

**Spike kỹ thuật** và **nguyên mẫu (prototype) có mục đích** là hai cách chủ động giảm bất định bằng việc học trong phạm vi nhỏ. Chúng giúp nhóm đặt câu hỏi rõ, thực hiện thử nghiệm có giới hạn, thu thập bằng chứng và lựa chọn bước tiếp theo trước khi đầu tư lớn.

Trong chương **Thiết kế tiến hóa** của module **AGILE_DEVELOPMENT**, điều này kết nối trực tiếp với việc:

- Ưu tiên giá trị trong **Product Backlog**.
- Giao phần mềm **tăng dần** thay vì dự đoán mọi chi tiết ngay từ đầu.
- Nhận phản hồi sớm để **thích ứng** thiết kế và kế hoạch.
- Dùng các thực hành **Scrum, Kanban, XP** và đo lường dòng công việc để tổ chức học hỏi.
- Cải thiện kỹ thuật liên tục mà không bỏ qua **chất lượng và an toàn**.

**Ý chính:** Mục đích của spike hoặc prototype không phải chứng minh nhóm đã viết được bao nhiêu mã, mà là **biến một điều chưa biết quan trọng thành hiểu biết có thể hành động**.

## 2. Từ thiết kế định trước đến thiết kế tiến hóa

**Thiết kế tiến hóa (evolutionary design)** là cách phát triển cấu trúc phần mềm theo hiểu biết tích lũy qua những lát cắt nhỏ, kiểm thử, tích hợp và phản hồi thực tế. Nhóm vẫn thiết kế có chủ đích, nhưng không giả định rằng tất cả nhu cầu và ràng buộc đều được hiểu đầy đủ ngay lúc đầu.

Ví dụ, thay vì ngay lập tức thiết kế một nền tảng xử lý sự kiện để đồng bộ tiến độ học cho mọi tương lai có thể tưởng tượng, nhóm có thể:

1. Làm rõ quy tắc nghiệp vụ của phiên bản đầu: lưu vị trí xem gần nhất, không làm mất tiến độ đã xác nhận.
2. Kiểm tra xem API và cơ sở dữ liệu hiện tại có đáp ứng khả năng cập nhật đồng thời không.
3. Tạo một lát cắt nhỏ để người học lưu và xem lại tiến độ.
4. Nhận phản hồi sử dụng, quan sát lỗi và tải thực tế.
5. Chỉ mở rộng thiết kế khi có rủi ro hoặc nhu cầu có bằng chứng.

| Thiết kế cố định quá sớm | Thiết kế tiến hóa có kỷ luật |
| --- | --- |
| Chốt công nghệ dựa trên dự đoán xa | Khảo sát rủi ro quan trọng, chọn phương án vừa đủ |
| Xây cả hệ thống trước khi tích hợp | Kiểm chứng lát cắt xuyên hệ thống sớm |
| Phát hiện yêu cầu sai sau nhiều tuần | Dùng phản hồi để cập nhật thiết kế theo từng bước |
| Đổi hướng bằng một lần viết lại lớn | Refactor có kiểm thử và thay đổi nhỏ |
| Coi mọi thay đổi là thất bại kế hoạch | Xem thay đổi có căn cứ là cơ hội cải thiện kết quả |

Thiết kế tiến hóa **không phải** “cứ viết mã trước rồi nghĩ sau”. Những quyết định khó đảo ngược liên quan dữ liệu, bảo mật, pháp lý và kiến trúc lõi vẫn cần khảo sát, phê duyệt hoặc thiết kế sớm ở mức phù hợp.

### 2.1. Học hỏi và thực hiện là hai loại kết quả khác nhau

Một spike có thể kết thúc với kết luận: “Giải pháp A không an toàn khi hai thiết bị ghi đồng thời; đề xuất B”. Đây là **kết quả học hỏi có ích**, dù chưa có tính năng sẵn sàng cho người dùng.

Một Increment hoàn tất lại cần đáp ứng **Definition of Done** và có thể sử dụng được trong bối cảnh sản phẩm. Không được đánh dấu một đoạn mã thử nghiệm thiếu kiểm chứng là Increment chỉ để tăng số hạng mục Done.

### 2.2. Khi nào chưa cần spike?

Không phải mọi nhiệm vụ đều mơ hồ tới mức cần khảo sát riêng. Nếu nhóm đã hiểu cách sửa lỗi hiển thị một nhãn, tác động nhỏ, dễ đảo ngược và có kiểm thử bảo vệ, **thực hiện trực tiếp** thường nhanh hơn mở một công việc “nghiên cứu” hình thức.

Nên dùng spike khi **bất định có khả năng làm thay đổi lựa chọn thiết kế, phạm vi hoặc mức rủi ro** và thử nghiệm giới hạn có thể mang lại bằng chứng đáng giá.

## 3. Spike, prototype, PoC, walking skeleton và MVP khác nhau thế nào?

Các thuật ngữ thường bị dùng lẫn nhau. Phân biệt theo **câu hỏi cần trả lời** và **đối tượng được kiểm chứng** sẽ hữu ích hơn tranh luận tên gọi.

| Hình thức | Mục đích nổi bật | Ví dụ nền tảng học | Kết quả chính |
| --- | --- | --- | --- |
| **Spike kỹ thuật** | Giảm bất định về khả thi, giải pháp hoặc rủi ro kỹ thuật trong thời gian giới hạn | Thử hai cách xử lý tiến độ cập nhật đồng thời | Bằng chứng, giới hạn, quyết định/khuyến nghị |
| **Prototype** | Biểu diễn một ý tưởng đủ cụ thể để kiểm tra giả thuyết | Giao diện mô phỏng “tiếp tục học” trên điện thoại | Phản hồi về hành vi, tương tác hoặc kỹ thuật |
| **Proof of Concept (PoC)** | Kiểm tra một ý tưởng có thực hiện được về nguyên lý không | Kết nối sandbox với dịch vụ chuyển mã video | Bằng chứng khả thi tối thiểu, chưa đủ production |
| **Walking skeleton** | Khung mỏng đi xuyên các thành phần hệ thống | UI → API → lưu dữ liệu → đọc lại tiến độ cơ bản | Kiểm chứng khả năng kết nối và đường triển khai |
| **MVP — Minimum Viable Product** | Phiên bản sản phẩm đủ giá trị để kiểm tra giả định thị trường/sử dụng | Người học thực sự tiếp tục khóa đang học với phạm vi giới hạn | Sản phẩm có thể dùng và phản hồi thực tế |
| **Increment** | Phần sản phẩm có thể sử dụng, đáp ứng DoD của sản phẩm | Chức năng lưu/khôi phục tiến độ đã kiểm thử và tích hợp | Giá trị sản phẩm hoàn tất theo chuẩn chất lượng |

Một PoC có thể được thực hiện **trong một spike**, và prototype có thể là công cụ để thực hiện spike. Đây **không phải các loại công việc loại trừ lẫn nhau**.

### 3.1. Spike là câu hỏi và phương pháp học, không phải một loại mã

Ví dụ:

> “Trong điều kiện hai thiết bị cùng cập nhật tiến độ, giải pháp dùng phiên bản bản ghi có thể ngăn việc cập nhật cũ ghi đè cập nhật mới không?”

Spike có thể tạo một ứng dụng thử, bộ kiểm thử đồng thời, bản ghi kết quả và quyết định. Mã chỉ là **phương tiện kiểm tra giả thuyết**.

### 3.2. Prototype là mô hình kiểm chứng ý tưởng

Prototype có thể là bản phác giấy, màn hình tương tác, một API giả lập hoặc một triển khai kỹ thuật giới hạn. Nó có thể giúp hỏi:

- Người học có hiểu trạng thái “Đã đồng bộ” không?
- Người dùng sẽ làm gì khi hai thiết bị có tiến độ khác nhau?
- Cách hiển thị xung đột có gây hoang mang không?
- Luồng kỹ thuật có hoạt động trong một môi trường thử được kiểm soát?

Một bản prototype không nhất thiết phải có chức năng đầy đủ. **Đừng dùng phản hồi từ một giao diện giả lập để khẳng định API thật đã an toàn hoặc có thể chịu tải.**

### 3.3. Tránh gọi mọi bản mẫu là MVP

MVP cần đủ giá trị và điều kiện sử dụng để học từ một giả thuyết sản phẩm. Một mockup không lưu dữ liệu vẫn có thể là prototype hữu ích, nhưng chưa phải sản phẩm cho người học sử dụng thật. Ngược lại, một lát cắt có ít tính năng nhưng đã đạt DoD và phục vụ nhu cầu thực có thể phù hợp để thử MVP.

## 4. Tìm đúng bất định trước khi thiết kế khảo sát

Một câu hỏi như “Nên chọn Kafka hay database hiện tại?” đã **định khung quá sớm theo công nghệ**. Trước hết cần hỏi hệ thống phải đạt điều gì, điều gì chưa biết và sai lầm sẽ gây hậu quả nào.

| Nhóm bất định | Câu hỏi quan trọng | Bằng chứng có thể thu thập |
| --- | --- | --- |
| **Nghiệp vụ và giá trị** | Người học mong hệ thống khôi phục tiến độ nào? | User interview, ví dụ chấp nhận, usability test |
| **Tính đúng đắn** | Hai yêu cầu cập nhật cùng lúc có làm mất dữ liệu không? | Kiểm thử đồng thời, bất biến dữ liệu |
| **Hiệu năng** | Độ trễ ở mức tải cần thiết có chấp nhận được không? | Benchmark trên môi trường và dữ liệu đại diện |
| **Tính sẵn sàng** | Khi mất mạng hoặc dịch vụ lỗi, có thể phục hồi thế nào? | Thử lỗi có kiểm soát, quan sát và phương án khôi phục |
| **Khả năng tích hợp** | API hiện có có phù hợp cách đọc/ghi mới? | Contract test, walking skeleton |
| **Khả năng vận hành** | Nhóm có chẩn đoán sự cố dễ dàng không? | Thử log/metrics/tracing và quy trình xử lý |
| **Bảo mật và quyền dữ liệu** | Dữ liệu học tập có được chuyển cho nhà cung cấp ngoài không? | Rà soát với người có thẩm quyền |
| **Chi phí thay đổi** | Nếu phương án sai, thay thế có khó không? | Phân tích phụ thuộc, spike kiến trúc giới hạn |

### 4.1. Ưu tiên khảo sát theo rủi ro, không theo độ hấp dẫn công nghệ

Một bảng thảo luận đơn giản:

| Bất định | Khả năng giả định sai | Hậu quả nếu sai | Khả năng học nhanh | Ưu tiên |
| --- | --- | --- | --- | --- |
| Cập nhật tiến độ đồng thời | Chưa rõ | Có thể mất dữ liệu người học | Có thể tạo test mô phỏng | **Cao** |
| Thư viện hiệu ứng nút mới | Thấp | Có thể đổi dễ dàng | Thử giao diện nhỏ | Thấp |
| Quyền dùng dữ liệu trong dịch vụ ngoài | Chưa rõ | Rủi ro pháp lý/bảo mật lớn | Có thể rà soát sớm | **Rất cao** |
| Độ trễ ở tải dự kiến | Chưa rõ | Trải nghiệm học kém | Có thể đo benchmark | Cao |

Đây là **đánh giá định tính minh họa**, không phải điểm số chuẩn hóa của Lean hay Scrum. Nếu một ràng buộc bắt buộc bị vi phạm, phương án có thể phải loại bỏ ngay chứ không chờ xếp hạng.

### 4.2. Chọn câu hỏi đủ hẹp

**Quá rộng:** “Nghiên cứu kiến trúc đồng bộ.”

**Cụ thể hơn:** “Với hai thiết bị cập nhật cùng một bản ghi tiến độ trong vòng một giây, cách kiểm tra phiên bản có phát hiện và ngăn ghi đè dữ liệu mới bằng bản ghi cũ không?”

**Cụ thể hơn nữa:** “Trên cơ sở dữ liệu mục tiêu, cập nhật có điều kiện theo version có được thực thi nguyên tử khi có hai yêu cầu cạnh tranh không?”

Câu hỏi hẹp giúp thiết kế thử nghiệm nhanh, biết dữ liệu nào cần thu và biết khi nào đủ để dừng.

## 5. Viết một Spike Charter trước khi thử

**Spike Charter** là thỏa thuận ngắn về mục đích, giới hạn và đầu ra của một khảo sát kỹ thuật. Đây là **mẫu quản lý tự chọn**, không phải artifact hoặc quy tắc bắt buộc trong Scrum Guide.

### 5.1. Mẫu đầy đủ nhưng gọn

| Trường | Nội dung cần ghi |
| --- | --- |
| **Quyết định cần hỗ trợ** | Nhóm sắp phải chọn hoặc loại phương án nào? |
| **Giả định/bất định** | Điều gì chưa biết và có thể làm quyết định đổi? |
| **Câu hỏi kiểm chứng** | Câu hỏi có thể trả lời bằng bằng chứng nào? |
| **Các phương án** | Những lựa chọn nào sẽ được so sánh? |
| **Môi trường và dữ liệu** | Thử ở đâu, dùng dữ liệu nào, ranh giới tin cậy? |
| **Phương pháp** | Prototype, benchmark, test tích hợp, tài liệu kỹ thuật, phỏng vấn? |
| **Timebox** | Giới hạn thời gian/công sức và thời điểm xem lại |
| **Tiêu chí kết luận** | Dấu hiệu chấp nhận, loại bỏ hoặc cần kiểm tra tiếp |
| **Guardrails** | An toàn, riêng tư, bảo mật, hiệu năng hoặc ràng buộc không thể đánh đổi |
| **Đầu ra** | Bản ghi bằng chứng, quyết định và việc tiếp theo |
| **Người liên quan** | Ai thực hiện, ai xác nhận nghiệp vụ và ai phê duyệt ràng buộc? |

### 5.2. Ví dụ Spike Charter cho đồng bộ tiến độ

> **Câu hỏi:** Bản ghi có trường version và phép cập nhật có điều kiện có ngăn mất dữ liệu khi hai thiết bị ghi đồng thời không?  
> **Giả thuyết:** Với thao tác compare-and-set được cơ sở dữ liệu hỗ trợ nguyên tử, một yêu cầu dùng version cũ sẽ bị từ chối thay vì ghi đè im lặng.  
> **Thử nghiệm:** Tạo dịch vụ nhỏ và kiểm thử nhiều yêu cầu ghi cạnh tranh trên môi trường thử được cấu hình giống cơ sở dữ liệu mục tiêu.  
> **Timebox:** Hai ngày làm việc, trong đó có thời gian ghi kết quả và trao đổi quyết định.  
> **Bằng chứng:** Không có cập nhật im lặng ghi đè dữ liệu mới trong những tình huống đã kiểm tra; lỗi xung đột được trả về rõ; đo thời gian phản hồi ở tải thử đã định nghĩa.  
> **Giới hạn:** Chỉ thử một loại dữ liệu, một cấu hình và một số mức tải. Chưa chứng minh khả năng hoạt động của toàn hệ thống production.  
> **Kết thúc:** Đề xuất chọn, loại hoặc cần khảo sát thêm, cùng rủi ro và bước tiếp theo.

**Không nên** đặt tiêu chí “làm được demo thì chọn ngay kiến trúc” vì một demo thành công chưa đủ kiểm chứng tình huống biên, an toàn dữ liệu và vận hành.

### 5.3. Timebox là giới hạn học hỏi, không phải lý do bỏ qua bằng chứng

Hết timebox, nhóm có thể:

1. **Kết luận đủ:** Có bằng chứng để chọn hoặc loại phương án.
2. **Kết luận chưa đủ:** Biết rõ điều nào vẫn chưa được chứng minh, cần khảo sát nào tiếp theo.
3. **Thay đổi câu hỏi:** Giả thuyết ban đầu không còn đúng hoặc không còn quan trọng.
4. **Dừng:** Chi phí khảo sát tiếp lớn hơn giá trị thông tin có thể nhận.

Nếu chưa đủ bằng chứng mà rủi ro nghiêm trọng vẫn tồn tại, **không được gọi phương án là an toàn chỉ vì đã hết hai ngày**. Cần báo cáo khoảng trống, điều chỉnh quyết định hoặc nâng mức kiểm chứng phù hợp.

## 6. Đặt giả thuyết có thể bác bỏ và đo đúng thứ cần biết

Một giả thuyết kỹ thuật hữu ích cần có **bối cảnh, kết quả mong đợi, điều kiện thử và dấu hiệu có thể làm nó sai**.

### 6.1. Từ khẩu hiệu sang giả thuyết

| Câu mơ hồ | Giả thuyết có thể kiểm tra |
| --- | --- |
| “Cơ sở dữ liệu này nhanh.” | “Với 100 yêu cầu ghi/giây trên dữ liệu thử X, p95 độ trễ cập nhật của cấu hình Y nằm dưới ngưỡng mục tiêu Z do nhóm xác định.” |
| “Cơ chế version chống mất dữ liệu.” | “Hai yêu cầu cập nhật cùng version không thể cùng ghi thành công vào một bản ghi theo thao tác nguyên tử đã chọn.” |
| “Prototype này dễ dùng.” | “Người học mục tiêu có thể nhận ra tiến độ nào đang được giữ khi hai thiết bị có thông tin khác nhau trong nhiệm vụ thử đã định nghĩa.” |
| “Dịch vụ ngoài ổn định.” | “Trong các kiểu lỗi mô phỏng đã xác định, hệ thống xử lý timeout/reties theo chính sách, không báo thành công giả và có thể quan sát sự cố.” |

Không nên tự đặt mức “p95 dưới 200 ms” như tiêu chuẩn chung cho mọi sản phẩm. **Ngưỡng phải xuất phát từ nhu cầu và bối cảnh**, gồm môi trường triển khai, tải, yêu cầu người dùng, mức độ an toàn và chi phí.

### 6.2. Thiết lập ba loại tiêu chí

- **Success criteria — Tiêu chí đạt:** Điều quan sát nào đủ để hỗ trợ phương án, ví dụ “không có hai giao dịch cùng ghi thành công trên version cũ trong test cạnh tranh”.
- **Failure/stop criteria — Tiêu chí loại hoặc dừng:** Điều gì khiến phương án không phù hợp, ví dụ thiếu cơ chế khôi phục sau ghi lỗi hoặc không đạt nghĩa vụ quyền dữ liệu.
- **Guardrails — Rào chắn:** Những điều không được vi phạm để lấy dữ liệu thử, chẳng hạn không dùng dữ liệu cá nhân thật ở môi trường chưa được phê duyệt.

Không xác định các tiêu chí trước sẽ dễ dẫn tới **đổi mục tiêu sau khi thấy kết quả**, chỉ giữ những số liệu có lợi cho phương án được ưa thích.

### 6.3. Chọn phép đo hợp lệ

**Latency:** ghi rõ điểm bắt đầu/kết thúc phép đo, đơn vị, cách tính p95 và tải.

**Correctness:** xác định bất biến cần giữ, ví dụ không có hai bản ghi tiến độ hợp lệ xung đột bị ghi đè âm thầm.

**Reliability:** nêu loại lỗi được tạo trong thử nghiệm và cách xác minh phục hồi.

**Usability:** định nghĩa nhiệm vụ, đối tượng thử, điều quan sát và hạn chế mẫu; đừng suy từ một vài lượt dùng rằng toàn bộ người học sẽ có cùng kết quả.

**Operational complexity:** đo thời gian khôi phục, các bước triển khai hoặc số phụ thuộc thật thay vì chỉ cảm giác “giải pháp A đơn giản hơn”.

## 7. Timebox, điểm quyết định và chi phí giữ lựa chọn

Spike hữu ích khi nó **có tác động tới một quyết định sẽ đến**. Nếu chưa biết tới khi nào phải chốt, khảo sát có thể kéo dài không giới hạn.

### 7.1. Đi ngược từ mốc giá trị

Giả sử một chương trình học bắt đầu sau **sáu tuần**. Với một phương án đồng bộ tiến độ cụ thể, sau khi chọn kiến trúc cần:

| Hoạt động sau khi chốt phương án | Thời lượng giả định |
| --- | ---: |
| Thực hiện lát cắt sản phẩm và tích hợp | 2 tuần |
| Kiểm thử đồng thời, quyền dữ liệu và lỗi mạng | 1 tuần |
| Kiểm tra vận hành và phát hành theo quy trình | 1 tuần |
| **Tổng thời gian cần bảo vệ theo giả định** | **4 tuần** |

Nếu các khoảng này cần nối tiếp và không thể rút ngắn, thời điểm chốt **muộn nhất theo phép tính giản lược** là:

\[
6\ \text{tuần}-4\ \text{tuần}=2\ \text{tuần từ khi bắt đầu}
\]

Điều này không có nghĩa nhóm **nên** đợi hết hai tuần mới quyết định. Nếu có bằng chứng đủ sau ba ngày, hoặc cần dự phòng thêm vì rủi ro cao, nhóm nên quyết định sớm hơn. Nếu chờ thêm khiến bỏ lỡ nghĩa vụ bắt buộc, không còn là “trì hoãn có trách nhiệm”.

### 7.2. Giá trị thông tin và chi phí trì hoãn

Một spike có giá trị khi bằng chứng mới **có khả năng thay đổi quyết định** và tránh chi phí sai lầm đáng kể. Nhưng thử nghiệm cũng tiêu tốn năng lực, môi trường và thời gian.

Giả sử **số liệu minh họa**:

- Nếu chọn ngay một giải pháp khó đảo ngược, chi phí làm lại khi sai là **15 người-ngày**.
- Nhóm tạm giả định xác suất chọn sai là **25%**.
- Một spike hai ngày có thể kiểm tra rủi ro quan trọng, nhưng chưa chắc loại bỏ hết bất định.

Tổn thất làm lại kỳ vọng theo mô hình giản lược:

\[
0{,}25\times15=3{,}75\ \text{người-ngày}
\]

So với hai người-ngày khảo sát, việc thử **có thể đáng cân nhắc**. Tuy nhiên, **25% là giả định để tập suy nghĩ**, không phải xác suất đã đo; cần đánh giá spike có thật sự giảm rủi ro đó, thêm chi phí trì hoãn và hậu quả không thể định lượng đơn giản.

**Không được áp dụng phép tính này như công thức tự động cho quyết định liên quan an toàn dữ liệu hoặc nghĩa vụ pháp lý.** Những ràng buộc bắt buộc không thể bị bỏ qua chỉ vì “xác suất kỳ vọng có vẻ thấp”.

## 8. Chọn giữa spike, prototype và lát cắt thực sự

Không phải câu hỏi nào cũng cần cùng một công cụ. Một luồng chọn:

~~~mermaid
flowchart TD
    A["Có vấn đề hoặc quyết định mới"] --> B{"Bất định nào có thể đổi lựa chọn?"}
    B -->|"Tính đúng, tích hợp, tải, vận hành"| C["Spike kỹ thuật / PoC giới hạn"]
    B -->|"Người dùng hiểu, thao tác, trải nghiệm"| D["Prototype và thử nghiệm sử dụng"]
    B -->|"Đã hiểu đủ, thay đổi nhỏ, dễ đảo ngược"| E["Lát cắt sản phẩm có thể dùng"]
    C --> F["Đọc bằng chứng, rủi ro và giới hạn"]
    D --> F
    E --> G["Kiểm chứng DoD và phản hồi thực tế"]
    F --> H{"Đủ để quyết định?"}
    H -->|"Chưa"| I["Sửa câu hỏi hoặc khảo sát bổ sung có giới hạn"]
    I --> B
    H -->|"Có"| E
    G --> J["Học thêm và điều chỉnh thiết kế"]
    J --> A
~~~

### 8.1. Một ví dụ lựa chọn

| Câu hỏi | Cách làm phù hợp | Điều không đủ |
| --- | --- | --- |
| “Người học có hiểu nút ‘Tiếp tục từ đây’ không?” | Prototype giao diện + usability test | Benchmark backend |
| “Có chống được cập nhật đồng thời vào bản ghi tiến độ không?” | Spike với test cạnh tranh và dữ liệu thử | Demo UI chạy trơn tru |
| “API hiện tại có trả được tiến độ đã lưu?” | Walking skeleton và integration test | Chỉ đọc tài liệu thiết kế |
| “Nhóm đã biết cách lưu tiến độ đơn thiết bị, cần triển khai phần đầu.” | Lát cắt giá trị nhỏ đáp ứng DoD | Mở spike chỉ vì muốn ghi có nghiên cứu |
| “Có được dùng dịch vụ ngoài để xử lý tiến độ học không?” | Rà soát quyền dữ liệu, chính sách và phương án kỹ thuật | Một PoC chạy thành công với dữ liệu nhạy cảm |

### 8.2. Nhiều loại bằng chứng có thể cần phối hợp

Một prototype trải nghiệm giúp làm rõ người học muốn thấy gì khi mạng mất. Một spike kỹ thuật giúp biết có thể giữ tính nhất quán ra sao. Chỉ khi kết hợp cả hai, nhóm mới có cơ sở thiết kế lát cắt phù hợp.

Đừng bắt một thí nghiệm duy nhất trả lời **mọi** câu hỏi. Hãy chọn thử nghiệm nhỏ cho **bất định có tác động lớn nhất**, rồi cập nhật câu hỏi tiếp theo.

## 9. Mã spike: bỏ đi hay phát triển tiếp?

Có hai chiến lược thường gặp, và lựa chọn phải có chủ đích:

| Chiến lược | Bản chất | Khi phù hợp | Rủi ro |
| --- | --- | --- | --- |
| **Throwaway spike/prototype** | Mã chỉ để học, dự kiến không đưa vào production | Thử nhiều thư viện, cách đồng bộ, đường lỗi hoặc cấu trúc chưa rõ | Áp lực thời hạn khiến mã thử bị dùng thật mà không nâng chất lượng |
| **Evolutionary prototype** | Bắt đầu bằng lát cắt nhỏ có chủ đích phát triển tới sản phẩm | Khi môi trường/kiến trúc được hiểu đủ và có chiến lược chất lượng từ đầu | Dễ tích lũy lối tắt nếu “để sau sửa” không được thực hiện |

**Spike không bắt buộc phải luôn bỏ toàn bộ mã**, nhưng cần phân biệt **kết quả học hỏi** với **mức sẵn sàng sử dụng** của bất kỳ đoạn mã nào.

### 9.1. Khi nào nên bỏ mã thử?

Nên cân nhắc bỏ mã khi:

- Được viết trong sandbox với dữ liệu giả và cố tình bỏ qua kiểm soát chất lượng sản phẩm.
- Dùng thư viện hoặc phiên bản chưa được phê duyệt.
- Chứa cấu hình tạm thời, secret thử hoặc xử lý lỗi giả lập.
- Kiến trúc chỉ phục vụ quan sát một giả thuyết và không đại diện nhu cầu thật.
- Không có bộ kiểm thử, khả năng vận hành và xem xét bảo mật phù hợp.

**Giữ lại kết quả học hỏi**: tập dữ liệu hợp lệ, test tái hiện, biểu đồ, giả định, quyết định và lý do loại phương án. Bỏ mã không đồng nghĩa bỏ tri thức.

### 9.2. Khi có ý định dùng tiếp mã prototype

Đừng tự động đổi nhãn “prototype hoàn tất” thành “feature Done”. Cần:

1. Xem lại yêu cầu nghiệp vụ và tiêu chí chấp nhận.
2. Bổ sung thiết kế lỗi, giao dịch, phân quyền và vận hành phù hợp.
3. Làm sạch cấu hình tạm, mã mô phỏng, dữ liệu thử và phụ thuộc chưa được phê duyệt.
4. Thực hiện code review, kiểm thử đơn vị/tích hợp/hành vi theo rủi ro.
5. Đáp ứng **Definition of Done** và các nghĩa vụ tổ chức.
6. Phát hành theo chính sách, quan sát và có kế hoạch khôi phục khi cần.

**Mã đã chứng minh ý tưởng có thể làm được** chưa chắc là mã có thể chịu tải, phục hồi, bảo vệ dữ liệu hoặc vận hành bền vững.

### 9.3. Prototype mỏng, bài toán lớn

Một prototype UI có thể được làm trong vài giờ, nhưng hệ thống thật cần xử lý quyền tài khoản, dữ liệu học tập, trạng thái offline, đồng bộ và lỗi mạng. Không nên suy số giờ làm prototype thành ước lượng sản xuất bằng một hệ số tùy tiện.

Prototype cho biết **điều gì có thể cần thiết** hoặc **có thể xảy ra**; ước lượng triển khai vẫn cần phạm vi thật, DoD, phụ thuộc, khả năng vận hành và mức bất định còn lại.

## 10. Ví dụ xuyên suốt: khảo sát đồng bộ tiến độ học

### 10.1. Bối cảnh sản phẩm

Người học đang xem khóa “Java nhập môn” trên điện thoại ở phút 18, sau đó mở trên laptop. Họ muốn tiếp tục gần vị trí đã xem. Khi điện thoại ngoại tuyến, nó có thể gửi cập nhật muộn; nếu hệ thống ghi đè không có kiểm tra, tiến độ mới trên laptop có thể bị thay bằng tiến độ cũ.

**Giá trị người dùng cần bảo vệ:**

- Vị trí xem được lưu và khôi phục có ý nghĩa.
- Dữ liệu của người học khác không bị truy cập hoặc ghi nhầm.
- Lỗi đồng bộ được thông báo hoặc xử lý theo quy tắc đã thống nhất, không báo thành công giả.
- Nếu hệ thống xử lý đồng thời, không im lặng làm mất cập nhật mới hợp lệ.

**Chưa quyết định:** Cách xử lý xung đột khi cập nhật tiến độ ở nhiều thiết bị.

### 10.2. Các phương án ban đầu

| Phương án | Ý tưởng | Lợi ích có thể có | Rủi ro cần khảo sát |
| --- | --- | --- | --- |
| **A — Cập nhật vị trí cuối cùng nhận được** | Ghi đè trường vị trí theo thứ tự tới server | Đơn giản | Có thể ghi đè tiến độ mới bằng cập nhật đến muộn |
| **B — Cập nhật có điều kiện theo version** | Chỉ ghi khi version hiện tại khớp version client đã đọc | Có thể phát hiện xung đột | Client cần xử lý từ chối và hợp nhất theo nghiệp vụ |
| **C — Lưu sự kiện xem và tính tiến độ** | Ghi sự kiện theo dòng, tính trạng thái từ các sự kiện hợp lệ | Có thể giữ lịch sử và xử lý phức tạp | Chi phí vận hành, thứ tự sự kiện, quyền dữ liệu và độ phức tạp |

**Lưu ý quan trọng:** “Vị trí lớn nhất” không phải lúc nào là kết quả đúng. Người học có thể chủ động xem lại phần trước; hệ thống có thể cần lưu **vị trí tiếp tục gần nhất** và **mức hoàn thành đã xác nhận** như hai khái niệm riêng. Quy tắc giải quyết xung đột phải được làm rõ với Product Owner và người hiểu trải nghiệm học, không do thuật toán tự quyết thay nghiệp vụ.

### 10.3. Spike được chọn

Nhóm quyết định bắt đầu với **B**, vì có thể thử rẻ trong cơ sở dữ liệu đang sử dụng. Spike không nhằm chứng minh B là lựa chọn tốt nhất vĩnh viễn, mà nhằm kiểm tra **cập nhật có điều kiện có ngăn ghi đè im lặng trong một tình huống cạnh tranh quan trọng không**.

**Giả thuyết:** Nếu hai yêu cầu cùng mang version 7, thao tác cập nhật nguyên tử theo version chỉ cho phép một yêu cầu thành công và tăng version thành 8; yêu cầu còn lại nhận trạng thái xung đột, không ghi đè.

**Điều chưa giải quyết trong spike này:** Client sẽ chọn trạng thái nào sau khi nhận xung đột, quy tắc offline kéo dài, quyền dữ liệu và trải nghiệm thông báo. Chúng cần các giả thuyết hoặc PBI tiếp theo.

### 10.4. Mô hình dữ liệu tối thiểu

Một bản ghi tiến độ thử có thể chứa:

~~~json
{
  "learnerId": "learner-42",
  "courseId": "java-basic",
  "lessonId": "intro-01",
  "positionSeconds": 1080,
  "version": 7
}
~~~

Đây là **dữ liệu giả**, không phải API có thể dùng trực tiếp hoặc schema production. Không lưu định danh/tiến độ cá nhân thật vào một sandbox chưa được kiểm soát.

### 10.5. Pseudocode cập nhật có điều kiện

**Giả mã SQL** dưới đây minh họa nguyên lý. Cú pháp, kiểu trường, giao dịch, cách xác định hàng bị ảnh hưởng và tính nguyên tử phải được kiểm tra trên **cơ sở dữ liệu mục tiêu**:

~~~sql
-- Ví dụ ý tưởng optimistic concurrency control.
UPDATE learning_progress
SET position_seconds = :new_position,
    version = version + 1
WHERE learner_id = :learner_id
  AND course_id = :course_id
  AND lesson_id = :lesson_id
  AND version = :expected_version;

-- 1 hàng được cập nhật: thành công trong điều kiện đã kiểm tra.
-- 0 hàng được cập nhật: có thể là xung đột version,
-- không tìm thấy bản ghi hoặc không phù hợp điều kiện.
-- Cần phân biệt và xử lý theo nghiệp vụ + phân quyền.
~~~

**Không dùng số hàng bị cập nhật để thay thế kiểm tra quyền truy cập.** Hệ thống thật cần xác thực người học, bảo vệ phạm vi dữ liệu, phân biệt không có bản ghi với version sai và xử lý lỗi giao dịch.

### 10.6. Kịch bản kiểm tra xung đột

~~~text
Trạng thái đầu:
  server.version = 7
  server.position = 1080 giây

Thiết bị A đọc version 7.
Thiết bị B cũng đọc version 7.

A gửi cập nhật vị trí 1200 giây, expectedVersion=7.
B gửi cập nhật vị trí 1100 giây, expectedVersion=7.

Kỳ vọng của spike:
  Chỉ một cập nhật được ghi thành công từ version 7 lên 8.
  Cập nhật còn lại không âm thầm ghi đè dữ liệu.
  API trả dấu hiệu xung đột rõ để client xử lý.

Chưa được kết luận:
  Vị trí cuối cùng nào là đúng với trải nghiệm người dùng?
  Làm thế nào đồng bộ ngoại tuyến kéo dài?
  Độ trễ và độ tin cậy ở quy mô production thế nào?
~~~

Nếu kiểm thử chỉ chạy A trước rồi B sau một cách tuần tự, chưa chắc tái hiện được **cạnh tranh thực**. Cần thiết kế yêu cầu đồng thời hoặc cơ chế điều khiển lịch trình đủ để kiểm tra bất biến.

## 11. Thiết kế thí nghiệm công bằng và tái lập được

Một spike có kết quả “chạy được trên laptop tôi” rất khó dùng cho quyết định kiến trúc. Nhóm nên ghi rõ:

- **Revision mã** và cấu hình thư viện.
- **Phiên bản cơ sở dữ liệu** và chính sách cô lập giao dịch.
- **Số lượng và loại yêu cầu**: tuần tự, cạnh tranh, có retry, mạng mất.
- **Dữ liệu thử**: khởi tạo ra sao và có dọn sạch giữa các lượt không.
- **Môi trường**: cấu hình máy, kết nối, giới hạn tài nguyên.
- **Cách đo**: công cụ, thời điểm bắt đầu/kết thúc, cách tính phân vị.
- **Số lượt lặp**: điều gì được quan sát, điều gì chưa được thử.
- **Hành vi lỗi**: timeout, dữ liệu không hợp lệ, từ chối quyền truy cập.

### 11.1. Bộ kịch bản tham khảo

| Kịch bản | Mục đích | Bằng chứng cần ghi |
| --- | --- | --- |
| Ghi đơn từ một thiết bị | Baseline đúng hành vi | Giá trị và version sau ghi |
| Hai yêu cầu cùng expectedVersion | Kiểm tra lost update | Có đúng một cập nhật thành công không? |
| Retry cùng yêu cầu | Quan sát xử lý lặp | Có tạo kết quả sai hoặc trạng thái khó giải thích? |
| Một yêu cầu tới trễ | Quan sát cập nhật version cũ | Có phát hiện xung đột không? |
| Client mất mạng giữa chừng | Xác định cách phát hiện kết quả chưa chắc chắn | Có báo thành công giả không? |
| Truy cập progress của người khác | Kiểm tra ranh giới phân quyền | Yêu cầu có bị từ chối đúng không? |
| Tăng tải có kiểm soát | Xác định điểm nghẽn ban đầu | Độ trễ, lỗi, tài nguyên trong môi trường thử |
| Cơ sở dữ liệu mất kết nối | Thử khả năng phục hồi | Lỗi có quan sát và xử lý phù hợp? |

Đối với spike có timebox, **không nhất thiết thực hiện toàn bộ kịch bản**; chọn những kịch bản quyết định phương án. Những rủi ro còn lại phải được ghi rõ và xử lý ở bước phù hợp trước khi sản phẩm được coi là Done.

### 11.2. Tránh kết luận từ benchmark không tương đồng

Một phương án chạy nhanh trên dữ liệu 100 bản ghi không thể tự chứng minh nó đáp ứng hệ thống có hàng triệu bản ghi. Tương tự, thử trên cơ sở dữ liệu ở máy phát triển không cho biết độ trễ mạng hoặc tình huống cụm máy production.

Nếu một kết quả chỉ đúng trong sandbox, hãy viết **“đã quan sát trong sandbox”**, không viết **“sẵn sàng chịu tải production”**.

### 11.3. Mẫu báo cáo thử nghiệm

~~~text
Mã spike: SPIKE-PROGRESS-01
Câu hỏi: Cập nhật theo version có chặn lost update?
Môi trường: Database thử, dữ liệu giả, revision được ghi rõ
Kịch bản: Hai yêu cầu cạnh tranh cùng expectedVersion
Kết quả: Mô tả lần chạy, trạng thái, số hàng cập nhật và lỗi
Giới hạn: Chưa kiểm chứng toàn bộ tương tác offline hoặc tải thật
Phương án: Giữ thử B / loại A / cần thêm bằng chứng về C
Việc tiếp theo: Xác nhận quy tắc xử lý xung đột với Product Owner
Người xem lại: Developers, người hiểu nghiệp vụ, chuyên gia dữ liệu
~~~

Báo cáo không cần dài, nhưng phải đủ để người khác **hiểu phương pháp, lặp lại kiểm tra và không diễn giải quá mức kết quả**.

## 12. Đọc kết quả thử nghiệm mà không tự tạo sự chắc chắn giả

Giả sử nhóm chạy thử ba phương án trong **một sandbox** và thu được dữ liệu **giả định phục vụ bài học**:

| Tiêu chí quan sát | A — Ghi cuối | B — Có version | C — Sự kiện |
| --- | --- | --- | --- |
| Có ngăn ghi đè im lặng khi hai yêu cầu dùng trạng thái cũ? | **Không** trong kịch bản đã thử | **Có** trong kịch bản đã thử | Phụ thuộc cách tái dựng/xử lý sự kiện |
| p95 độ trễ ghi ở tải thử đã chọn | 24 ms | 31 ms | 47 ms |
| Công sức thử nghiệm ban đầu | Thấp | Trung bình | Cao |
| Rủi ro còn lại | Mất cập nhật | Cần quy tắc giải quyết xung đột | Thứ tự sự kiện, vận hành phức tạp |
| Kết luận trong phạm vi spike | Loại cho yêu cầu không mất cập nhật | Đề nghị khảo sát bước tiếp theo | Chưa có lý do đủ để triển khai sâu |

Các số **24, 31, 47 ms chỉ là dữ liệu minh họa**, không phải benchmark đã được thực thi hoặc cam kết hiệu năng thực. Nếu báo cáo thực tế muốn dùng p95, cần nêu định nghĩa phép đo, cỡ mẫu, phân bố tải, cách chọn phân vị và độ biến động.

### 12.1. Quyết định phù hợp với bằng chứng

Nhóm có thể kết luận:

> “Ở kịch bản ghi cạnh tranh đã kiểm chứng, phương án A cho phép ghi đè im lặng nên không phù hợp với yêu cầu giữ dữ liệu. Phương án B phát hiện được xung đột trên cơ sở dữ liệu đã thử, với chi phí triển khai có vẻ phù hợp hơn C. Đề nghị dùng B cho lát cắt tiếp theo, đồng thời làm rõ quy tắc xử lý xung đột ở phía client và thử khả năng phục hồi, tải thực tế trước khi phát hành.”

Đây là quyết định **có điều kiện và có giới hạn**, tốt hơn hai cách cực đoan:

- “B chạy nhanh nên chắc chắn là kiến trúc tốt nhất mãi mãi.”
- “Chưa biết mọi tình huống tương lai nên không thể bắt đầu xây gì cả.”

### 12.2. Một thử nghiệm thất bại có thể thành công về học hỏi

Nếu B không thể bảo đảm cập nhật nguyên tử trong điều kiện hạ tầng hiện có, đó không phải “spike thất bại vô ích”. Nhóm vừa loại một giả định sai trước khi đưa vào sản phẩm và có thể khảo sát C hoặc điều chỉnh phạm vi.

Tuy nhiên, nếu spike không có câu hỏi, không ghi kết quả, không đưa ra quyết định và vẫn kéo dài, **việc đó khó được coi là học hỏi có giá trị**.

## 13. Từ spike tới quyết định thiết kế và backlog

Kết thúc spike không đồng nghĩa bắt đầu viết lại tất cả thiết kế. Hãy chuyển kết quả thành một quyết định nhỏ, có lý do và một hoặc vài lát cắt tiếp theo.

### 13.1. Architecture Decision Record (ADR) ngắn

**ADR** là một cách ghi lại quyết định kiến trúc và bối cảnh. Nó hữu ích nhưng **không phải tạo tác bắt buộc của Scrum**.

~~~text
ADR: Xử lý cập nhật tiến độ từ nhiều thiết bị
Trạng thái: Chọn thử cho lát cắt đầu, có điều kiện xem lại
Bối cảnh:
  Người học có thể ghi tiến độ từ nhiều thiết bị.
  Không được để cập nhật cũ ghi đè im lặng thông tin mới.
Các lựa chọn:
  A. Ghi cuối
  B. Kiểm tra version
  C. Lưu sự kiện
Quyết định:
  Ưu tiên B cho lát cắt đầu vì phát hiện xung đột trong thử nghiệm.
Lý do:
  Phù hợp cơ sở dữ liệu đang có; độ phức tạp ban đầu thấp hơn C.
Điều kiện:
  Phải kiểm thử tích hợp, dữ liệu, bảo mật và quy tắc client khi xung đột.
Hệ quả:
  Client cần xử lý phản hồi conflict và yêu cầu tải lại/đồng bộ.
Điểm xem lại:
  Khi nhu cầu offline hoặc tải vận hành vượt giả định ban đầu.
~~~

Không cần một tài liệu thiết kế dài hàng trăm trang để ra quyết định có căn cứ. Nhưng một ghi chú đủ rõ giúp thành viên mới hiểu **vì sao** phương án được chọn và điều kiện nào có thể khiến quyết định thay đổi.

### 13.2. Những Product Backlog Item tiếp theo

| PBI hoặc hoạt động | Giá trị / mục tiêu | Điều kiện hoàn tất được xem xét |
| --- | --- | --- |
| Lưu và đọc tiến độ từ một thiết bị | Người học tiếp tục tại vị trí hợp lệ | Behavior test, phân quyền, dữ liệu đúng, DoD |
| Phát hiện cập nhật version cũ | Không ghi đè dữ liệu mới một cách im lặng | Integration/concurrency test theo giả định đã xác nhận |
| Hiển thị trạng thái đồng bộ | Người học hiểu tiến độ đã lưu hay chưa | Acceptance criteria và thử nghiệm khả năng sử dụng |
| Xử lý mất mạng/đồng bộ trở lại | Trải nghiệm phù hợp khi offline | Quy tắc nghiệp vụ, kiểm thử lỗi, DoD |
| Quan sát lỗi đồng bộ | Nhóm phát hiện vấn đề sau phát hành | Logs/metrics phù hợp và bảo vệ quyền dữ liệu |
| Cập nhật ADR sau kết quả thực tế | Giữ thiết kế có thể tiến hóa | Quyết định và điều kiện xem lại được cập nhật |

Các hạng mục có thể được chia nhỏ thêm theo **lát cắt giá trị**. Đừng biến backlog thành danh sách mọi tầng kỹ thuật được xây riêng mà chưa tạo được Increment dùng được.

## 14. Prototype giao diện cho tình huống xung đột

Một spike backend có thể chỉ ra rằng xung đột được phát hiện, nhưng **người học cần thấy điều gì khi xung đột xảy ra** vẫn là câu hỏi thiết kế trải nghiệm.

Nhóm có thể tạo hai prototype nhỏ:

- **P1 — Tự chọn vị trí mới nhất từ server**, kèm thông báo ngắn rằng tiến độ thiết bị này chưa được đồng bộ.
- **P2 — Hiển thị hai lựa chọn “Tiếp tục từ vị trí trên thiết bị này” và “Tiếp tục từ vị trí đã đồng bộ”**, có thông tin giải thích.

Không nên dùng nội dung chính xác trên như quy tắc sản phẩm bắt buộc; đó là **hai giả thuyết trải nghiệm cần kiểm chứng**.

### 14.1. Mẫu bài thử khả năng sử dụng

**Nhiệm vụ:** Người học xem tới phút 18 trên điện thoại rồi tiếp tục tới phút 25 trên laptop. Điện thoại kết nối mạng lại và giao diện thông báo về tiến độ.

**Câu hỏi cần quan sát:**

1. Người học có hiểu rằng hai thiết bị có trạng thái khác nhau không?
2. Người học có dự đoán chính xác điều gì sẽ xảy ra khi chọn một phương án?
3. Người học có thể tiếp tục học mà không sợ mất kết quả không?
4. Có từ ngữ hoặc biểu tượng nào gây hiểu nhầm?
5. Phương án có đáp ứng yêu cầu khả năng tiếp cận cần thiết không?

**Tín hiệu thu thập:** Tỷ lệ hoàn thành nhiệm vụ theo tiêu chí đã định, số lần nhầm, thời gian thao tác, phản hồi định tính, những lỗi có hệ quả lớn.

### 14.2. Không được lạm dụng kết quả mẫu nhỏ

Giả sử năm người dùng thử P1, ba người hiểu đúng; năm người khác thử P2, bốn người hiểu đúng. **3/5 và 4/5 chỉ là tỷ lệ quan sát trong nhóm thử nhỏ**, chưa đủ để kết luận P2 tốt hơn cho toàn bộ người học hoặc có ý nghĩa thống kê.

Hơn nữa, nếu hai nhóm khác kinh nghiệm và không được phân bổ ngẫu nhiên, không thể khẳng định chính prototype gây ra khác biệt. Bằng chứng này có thể giúp nhận diện vấn đề và **quyết định nên thử tiếp điều gì**, không phải lời bảo đảm về outcome dài hạn.

### 14.3. Mã prototype không mặc định đạt chất lượng sản phẩm

Bản mẫu có thể mô phỏng thành công/thất bại mà không thực sự ghi dữ liệu. Khi chuyển sang Increment thật, phải kiểm tra:

- Giao diện không báo thành công nếu server chưa xác nhận phù hợp.
- Hành vi khi gửi lại yêu cầu, mất mạng và xung đột.
- Quyền truy cập dữ liệu tiến độ theo tài khoản.
- Khả năng tiếp cận và các điều kiện chất lượng khác.
- Dữ liệu và trạng thái được phục hồi đúng sau các lỗi đã xác định.

**Khả năng sử dụng tốt trong prototype** và **tính đúng kỹ thuật trong spike** đều cần thiết ở những rủi ro tương ứng, nhưng không thay thế lẫn nhau.

## 15. Kiểm thử và tích hợp cho thiết kế tiến hóa

Spike giảm bất định ban đầu. Sau khi chọn phương án, **kiểm thử và tích hợp liên tục** giúp nhóm tiếp tục thay đổi mà không mất những hành vi đã được xác nhận.

### 15.1. Lưới kiểm thử theo rủi ro

| Tầng | Điều cần bảo vệ | Ví dụ |
| --- | --- | --- |
| **Unit test** | Quy tắc lựa chọn trạng thái hoặc xác định conflict | Dùng version cũ trả kết quả không được ghi đè |
| **Component test** | Logic dịch vụ với các phụ thuộc được kiểm soát | Phân biệt record không tồn tại và conflict |
| **Contract test** | Hợp đồng client–API | Trạng thái xung đột được biểu diễn nhất quán |
| **Integration/concurrency test** | Giao dịch và cơ sở dữ liệu thật trong môi trường thử | Hai request cạnh tranh không cùng ghi thành công trên version cũ |
| **End-to-end test** | Luồng người học quan trọng | Mất mạng, tải lại, khôi phục vị trí |
| **Security/privacy review** | Ranh giới dữ liệu và quyền truy cập | Người dùng A không xem/sửa tiến độ B |
| **Operational test** | Khả năng quan sát và phục hồi | Khi DB không sẵn, có lỗi rõ và không báo lưu giả |

Không bắt buộc mọi PBI phải có đúng số lượng kiểm thử mỗi loại. **Chọn kiểm thử theo rủi ro cần kiểm chứng** và tiêu chuẩn DoD áp dụng, không theo chỉ tiêu làm đẹp coverage.

### 15.2. Gherkin cho lát cắt đã được chốt quy tắc

~~~gherkin
Tính năng: Đồng bộ tiến độ học

  Tình huống: Lưu tiến độ khi không có xung đột
    Cho trước người học đã đăng nhập
    Và đã đọc bản ghi tiến độ với version hiện tại
    Khi người học gửi vị trí mới kèm version tương ứng
    Thì hệ thống ghi tiến độ theo quy tắc đã thống nhất
    Và trả về version mới sau khi lưu thành công

  Tình huống: Cập nhật từ dữ liệu đã cũ
    Cho trước người học đã đọc tiến độ ở version 7
    Và một thiết bị khác đã cập nhật bản ghi lên version 8
    Khi thiết bị đầu tiên gửi cập nhật dựa trên version 7
    Thì hệ thống không âm thầm ghi đè dữ liệu version 8
    Và phản hồi xung đột để client xử lý theo chính sách sản phẩm

  Tình huống: Không được sửa tiến độ của tài khoản khác
    Cho trước người học A đã đăng nhập
    Và bản ghi tiến độ thuộc tài khoản B
    Khi A cố gửi yêu cầu sửa tiến độ thuộc B
    Thì hệ thống từ chối thao tác theo chính sách phân quyền
    Và không thay đổi tiến độ của B

  Tình huống: Lưu thất bại
    Cho trước dịch vụ không thể xác nhận đã ghi tiến độ
    Khi người học gửi cập nhật
    Thì hệ thống không báo chắc chắn lưu thành công
    Và giao diện thể hiện trạng thái chưa xác nhận phù hợp
~~~

Đây là **kịch bản hành vi minh họa**, muốn tự động thực thi cần mã bước, dữ liệu và môi trường kiểm thử. Nhóm phải làm rõ thêm quy tắc vị trí khi người học chủ động xem lại và hành vi retry trước khi dùng trong sản phẩm thật.

### 15.3. Refactoring sau spike

Giả sử nhóm phát hiện nhiều dịch vụ đang cùng tự quản lý version theo cách khác nhau. Một refactor có kiểm thử có thể đưa quy tắc về ranh giới rõ, giảm việc sửa lặp và nguy cơ lệch hợp đồng.

**Refactoring** là cải thiện cấu trúc bên trong mà không chủ định đổi hành vi đã được xác định. Nếu nhóm đồng thời thay cả quy tắc xung đột, đó còn là **thay đổi hành vi** cần acceptance criteria và kiểm thử riêng.

### 15.4. CI giúp phát hiện thay đổi mới phá kết quả cũ

Trong thiết kế tiến hóa, mỗi quyết định và lát cắt có thể thay đổi tiếp. CI đáng tin giúp biết:

- API có còn tương thích với client?
- Migration có còn chạy với dữ liệu đại diện?
- Bất biến chống ghi đè có còn được bảo vệ?
- Một tối ưu hiệu năng có phá tính đúng đắn?

Không nên giữ nhánh thử nghiệm nhiều tuần rồi hợp nhất một lần ở cuối Sprint. Tích hợp nhỏ và thường xuyên giúp phản hồi đến trước khi vấn đề lan rộng.

## 16. An toàn, bảo mật và quyền dữ liệu trong thí nghiệm

“Chỉ là prototype” **không phải lý do miễn tuân thủ**. Một khảo sát có thể gây rủi ro thật nếu dùng tài khoản production, secret, dữ liệu người học hoặc dịch vụ bên ngoài.

### 16.1. Guardrails tối thiểu

- Ưu tiên **dữ liệu giả/tổng hợp** hoặc dữ liệu đã được cho phép và xử lý đúng chính sách.
- Không đưa secret hay token thật vào repository, ảnh chụp, report hoặc log.
- Tách môi trường thử khỏi dữ liệu production khi rủi ro đòi hỏi.
- Chỉ cấp quyền tối thiểu cho runner, dịch vụ và người thực hiện.
- Không thử tác động hủy dữ liệu thật nếu chưa có phê duyệt và phương án phục hồi.
- Kiểm tra yêu cầu về quyền riêng tư, lưu giữ và chuyển dữ liệu trước khi gọi nhà cung cấp ngoài.
- Nêu rõ phạm vi thí nghiệm và cách dừng hoặc khôi phục nếu có lỗi.

### 16.2. Hai trường hợp không thể “thử rồi tính”

**Trường hợp A — Dữ liệu cá nhân:** Một dịch vụ gợi ý bên ngoài muốn nhận lịch sử học. Dù API hoạt động tốt, nhóm không thể xem đó là phương án hợp lệ trước khi xử lý quyền dữ liệu và phê duyệt phù hợp.

**Trường hợp B — Thanh toán:** Một prototype cập nhật thanh toán không được dùng tiền thật trên người dùng nếu thiếu kiểm soát giao dịch, phân quyền, kiểm tra và cơ chế khôi phục cần thiết.

Spike có thể chứng minh tính khả thi **trong điều kiện an toàn được cho phép**. Một quyết định phát hành đòi hỏi chuẩn cao hơn.

### 16.3. Ranh giới kỹ thuật và ranh giới quyết định

Developers có thể tự đề xuất cách đo, môi trường test và phương án triển khai trong phạm vi chuyên môn. Nhưng quyết định **phạm vi giá trị sản phẩm** cần cộng tác với Product Owner; yêu cầu **pháp lý, bảo mật, hợp đồng hoặc dữ liệu** phải được người có thẩm quyền tương ứng xem xét.

Tự quản không đồng nghĩa tự quyết bỏ các ràng buộc bắt buộc.

## 17. Tổ chức spike và prototype trong Scrum

Scrum xác định accountabilities, events, artifacts và commitments; **không bắt buộc một artifact có tên “spike”**, không yêu cầu mọi PBI là user story và không ấn định timebox riêng cho nghiên cứu kỹ thuật.

Tuy vậy, một Scrum Team có thể đưa **công việc học hỏi có giá trị** vào Product Backlog nếu nó cần thiết để tiến tới Product Goal hoặc giảm rủi ro của một Increment sắp tới.

### 17.1. Product Owner và Developers cộng tác ra sao?

| Câu hỏi | Trách nhiệm phù hợp |
| --- | --- |
| Tại sao cần khảo sát? Nó hỗ trợ giá trị hoặc mục tiêu nào? | Product Owner và Developers làm rõ cùng nhau |
| Điều gì chưa biết về kỹ thuật? | Developers chỉ ra giả định và rủi ro |
| Phương pháp spike nên làm như thế nào? | Developers tự chọn cách thực hiện phù hợp |
| Bao nhiêu năng lực nên dành cho khảo sát? | Scrum Team trao đổi theo mục tiêu, ưu tiên và năng lực thực |
| Phát hiện mới có làm thay đổi phạm vi không? | Developers trao đổi với Product Owner để làm rõ/thương lượng |
| Mã thử nghiệm đã trở thành Increment chưa? | Đối chiếu Definition of Done và điều kiện có thể sử dụng |

### 17.2. Spike có thể thuộc một Sprint không?

Có, nếu được lựa chọn và tổ chức hợp lý để hỗ trợ mục tiêu Sprint. Ví dụ, một Sprint Goal có thể tập trung **giảm rủi ro một cách kiểm chứng được** cho luồng đồng bộ tiến độ, thay vì bắt buộc giao toàn bộ tính năng cuối cùng.

Tuy nhiên:

- **Sprint Goal** vẫn là commitment giúp Scrum Team tập trung.
- **Developers** lập và cập nhật Sprint Backlog.
- **Definition of Done** áp dụng khi khẳng định có một Increment hoàn tất.
- Kết quả spike như báo cáo hoặc prototype nội bộ **không tự động trở thành Increment**.
- Trong Sprint, không được giảm chất lượng hoặc thay đổi gây nguy hiểm cho Sprint Goal; phạm vi được làm rõ hoặc thương lượng với Product Owner khi học thêm.

Một bản ghi nghiên cứu có thể đạt **tiêu chí hoàn tất riêng cho hoạt động học hỏi**; điều đó **khác** với tuyên bố chức năng sản phẩm đã Done.

### 17.3. Sử dụng các Scrum Events

| Sự kiện | Vai trò đối với khảo sát |
| --- | --- |
| **Sprint Planning** | Xác định rủi ro cần giải quyết, mục tiêu, năng lực và kế hoạch học hỏi |
| **Daily Scrum** | Developers kiểm tra tiến độ hướng Sprint Goal, trở ngại và điều chỉnh kế hoạch spike |
| **Sprint Review** | Kiểm tra kết quả và thông tin đã học cùng stakeholder, điều chỉnh Product Backlog |
| **Sprint Retrospective** | Xem cách spike được timebox, chất lượng bằng chứng và việc chuyển thành quyết định |

**Daily Scrum không phải buổi trình bày báo cáo nghiên cứu cho quản lý**; nó giúp Developers điều chỉnh kế hoạch nhằm đạt Sprint Goal.

## 18. Kanban, XP và Lean giúp khảo sát có dòng chảy tốt hơn

### 18.1. Kanban: làm rõ việc đang học và giới hạn WIP

Nếu cả nhóm mở mười spike nhưng không có quyết định nào, công việc nghiên cứu cũng có thể trở thành **WIP bị tồn đọng**.

Một bảng công việc nhỏ:

~~~text
Chờ chọn         Đang khảo sát          Chờ kết luận          Đã quyết định
--------------- ---------------------- --------------------- -----------------
Tải khi offline  Version/concurrency    API bên thứ ba         Quy tắc login
UI xung đột      Migration dữ liệu
~~~

Nhóm có thể đặt chính sách:

1. Mỗi spike có câu hỏi và timebox rõ.
2. Chưa hoàn tất kết luận hoặc chưa biết bước tiếp theo thì không coi là Done.
3. Không mở thêm quá nhiều spike khi người có quyền quyết định chưa thể xem kết quả cũ.
4. Theo dõi **work item age** của việc khảo sát, đặc biệt khi chờ môi trường hoặc phê duyệt.
5. Ghi **throughput** của công việc đã tạo quyết định nếu nó thật sự giúp cải thiện luồng, nhưng đừng tối ưu số spike đóng bằng cách chia giả tạo.

Một spike tồn 15 ngày chỉ để chờ người phê duyệt dữ liệu có thể cho thấy **nút nghẽn quyết định**, không phải thiếu nỗ lực của người lập trình.

### 18.2. XP: dùng spike để học, sau đó thiết kế đơn giản và refactor

Trong Extreme Programming, spike là kỹ thuật hữu ích khi nhóm gặp điều chưa biết đáng kể. Sau khi học:

- Chọn thiết kế **đơn giản vừa đủ** theo bằng chứng.
- Viết kiểm thử cho hành vi cần giữ.
- Tích hợp các thay đổi nhỏ bằng **Continuous Integration**.
- Dùng **refactoring** để cải thiện cấu trúc khi hiểu biết tăng.
- Phát hành phần tăng dần nhỏ khi đạt chất lượng.
- Có thể dùng pair programming để cùng làm rõ rủi ro và chia sẻ hiểu biết.

Spike không thay thế kỷ luật kỹ thuật. Nếu mã khảo sát làm lộ lựa chọn hợp lý nhưng sau đó nhóm phát triển không có kiểm thử, CI hoặc thiết kế dễ đổi, khả năng thích ứng vẫn có thể giảm.

### 18.3. Lean: tối ưu học hỏi trên mỗi đơn vị chi phí

Lean khuyến khích **amplify learning** và **defer commitment responsibly**: thu thập thông tin có ý nghĩa trước những quyết định đắt đỏ, giữ phương án mở khi giá trị còn lớn, rồi chốt đúng lúc.

Một prototype được xây chỉ để gây ấn tượng trong buổi demo, không dẫn tới quyết định, có thể là **lãng phí**. Một thử nghiệm nhỏ giúp loại một kiến trúc sai có thể tạo giá trị lớn dù không tạo thêm màn hình sản phẩm.

| Cách tiếp cận | Đóng góp thực tế | Giới hạn cần nhớ |
| --- | --- | --- |
| **Thiết kế tiến hóa** | Phát triển thiết kế theo bằng chứng mới | Không được tránh mọi quyết định kiến trúc |
| **Scrum** | Mục tiêu, trách nhiệm, kiểm tra/thích ứng theo nhịp | Không định nghĩa spike như một event bắt buộc |
| **Kanban** | Nhìn WIP, tuổi việc và nút nghẽn khảo sát | Nhiều ticket Done không chứng minh học hỏi có ích |
| **XP** | Spike, TDD, CI, refactor, simple design | Mã spike chưa tự đạt tiêu chuẩn sản phẩm |
| **Lean** | Chọn bất định đáng học, tránh cam kết sai | Trì hoãn có chi phí và phải có điểm dừng |

## 19. Đo kết quả spike bằng khả năng ra quyết định

**Không nên dùng số dòng mã prototype làm thước đo thành công.** Cũng không nên thưởng cho số lượng spike vì dễ dẫn tới nghiên cứu hình thức.

### 19.1. Những tín hiệu đáng theo dõi

| Tín hiệu | Câu hỏi | Điểm cần cảnh giác |
| --- | --- | --- |
| **Từ câu hỏi đến quyết định** | Mất bao lâu để có bằng chứng đủ hành động? | Nhanh nhưng kết luận thiếu căn cứ không tốt |
| **Rủi ro được loại bỏ/làm rõ** | Bất định quan trọng nào đã giảm? | “Đã tìm hiểu” không đồng nghĩa có kết quả kiểm chứng |
| **Tỷ lệ spike có quyết định tiếp theo** | Khảo sát có dẫn tới chọn, loại hoặc thử tiếp có lý do? | Đừng ép mọi spike phải chọn một giải pháp ngay |
| **Work item age của spike** | Khảo sát bị chặn hoặc tồn lâu ở đâu? | Tuổi cao có thể do chờ phê duyệt |
| **Chi phí khảo sát** | Nhóm dùng bao nhiêu năng lực và môi trường? | Rẻ nhưng không trả lời đúng câu hỏi có thể lãng phí |
| **Làm lại tránh được** | Có bằng chứng rằng khảo sát giúp tránh thiết kế sai? | Không dễ xác định phản thực tế; tránh bịa số tiết kiệm |
| **Lỗi về sau tại ranh giới đã khảo sát** | Có rủi ro nào spike bỏ sót? | Một lỗi không tự chứng minh mọi khảo sát trước vô ích |
| **Outcome người dùng** | Giải pháp đã chọn có tạo kết quả mong muốn? | Cần quan sát sau khi giao thực tế |

### 19.2. Đánh giá quyết định bằng giả định và khả năng xem lại

Một quyết định tốt không nhất thiết cho kết quả hoàn hảo trong mọi hoàn cảnh tương lai. Nó cần:

- Được đưa ra với **bằng chứng tốt nhất hợp lý tại thời điểm đó**.
- Nêu rõ **giả định và giới hạn**.
- Không vi phạm điều kiện bắt buộc.
- Chỉ ra **tín hiệu nào sẽ kích hoạt xem lại**.
- Cho phép thực hiện bước tiếp theo mà không làm hệ thống phức tạp vô ích.

Đừng đánh giá spike chỉ theo việc “sau đó chẳng bao giờ phải sửa thiết kế”. Sản phẩm và bối cảnh thay đổi; mục tiêu của thiết kế tiến hóa là **đổi hướng có kiểm soát**, không phải đoán đúng mọi tương lai.

## 20. Những sai lầm thường gặp

**1. “Spike” chỉ là đổi tên một task chưa ước lượng được.** Nếu không có câu hỏi, timebox, bằng chứng và kết luận, nó dễ trở thành công việc mơ hồ.

**2. Nghiên cứu mọi công nghệ trước khi chọn bất kỳ hướng nào.** Không phải mọi bất định có tác động lớn; cần ưu tiên quyết định quan trọng và điểm cam kết.

**3. Chỉ hỏi “có chạy được không?”.** Một PoC thành công chưa trả lời độ an toàn, chi phí vận hành, hiệu năng hoặc tính đúng đắn khi tải thực.

**4. Không đặt điều kiện dừng.** Nhóm có thể mở rộng spike mãi, không chuyển thành quyết định.

**5. Hết timebox là tuyên bố phương án an toàn.** Timebox giới hạn chi phí khảo sát, không làm biến mất rủi ro chưa được chứng minh.

**6. Viết prototype như production nhưng không có kế hoạch dùng tiếp.** Chi phí xây và bảo trì vượt giá trị học hỏi.

**7. Đẩy mã throwaway vào production vì “đã demo thành công”.** Mã thử thiếu kiểm thử, review, bảo mật và vận hành có thể gây hậu quả thật.

**8. Xóa mọi kết quả sau khi bỏ mã thử.** Nên giữ bằng chứng, kịch bản tái hiện và lý do quyết định.

**9. Chỉ thử happy path.** Rủi ro thường nằm ở đồng thời, dữ liệu cũ, quyền truy cập, timeout hoặc điều kiện biên.

**10. Benchmark thiếu mô tả môi trường rồi suy ra khả năng production.** Số đo chỉ có nghĩa theo cấu hình, dữ liệu và tải đã thử.

**11. Dùng dữ liệu người dùng thật trong sandbox không được phê duyệt.** Thử nghiệm kỹ thuật không miễn nghĩa vụ bảo mật và quyền riêng tư.

**12. Bảo “người dùng thích prototype” là chứng minh kiến trúc tốt.** Trải nghiệm và khả thi kỹ thuật cần bằng chứng phù hợp khác nhau.

**13. Coi mỗi ý tưởng là một MVP.** Prototype, PoC, sản phẩm dùng được và Increment có chuẩn chất lượng khác nhau.

**14. Không ghi kết luận và lý do loại phương án.** Sau vài Sprint, nhóm lặp lại cùng tranh luận hoặc tái tạo thử nghiệm.

**15. Giữ mọi phương án sống vô hạn.** Phương án mở tiêu tốn thời gian và độ phức tạp; cần thu hẹp khi có bằng chứng.

**16. Chọn kiến trúc khó đảo ngược bằng ý kiến người có chức vụ cao nhất.** Cần xem rủi ro, dữ liệu, chuyên môn và thẩm quyền phù hợp.

**17. Ép spike phải tạo Increment ngay.** Kết quả học hỏi có ích khác với chức năng sản phẩm đạt DoD; không được làm mờ hai khái niệm.

**18. Dùng spike để né Sprint Goal hoặc lén thêm phạm vi.** Công việc nghiên cứu trong Scrum cần hỗ trợ mục tiêu và trao đổi với Product Owner khi phạm vi ảnh hưởng.

**19. Chỉ đo số spike hoàn tất.** Mục đích là nâng chất lượng quyết định và khả năng giao giá trị, không phải tăng số ticket.

**20. Không có bước kiểm thử/tích hợp sau quyết định.** Spike giúp chọn hướng, còn CI, test, refactor và DoD mới giúp biến hướng thành phần mềm đáng tin.

**21. Coi thiết kế tiến hóa là không cần kiến trúc.** Những ràng buộc an toàn, dữ liệu và quyết định khó đảo ngược cần được thiết kế có trách nhiệm.

**22. Tự ý xử lý quy tắc sản phẩm khi thử kỹ thuật.** Developers cần làm rõ nhu cầu và cách giải quyết xung đột với Product Owner hoặc người có thẩm quyền, không biến giả định thử thành nghiệp vụ thật.

## 21. Bài tập tình huống: chọn cách đồng bộ khi có hạn giao

Một nhóm phát triển nền tảng học trực tuyến có **sáu tuần** trước khi mở khóa học mới. Product Owner muốn người học tiếp tục bài học trên hai thiết bị. Developers đưa ra ba phương án:

| Phương án | Tính chất | Điều cần kiểm chứng |
| --- | --- | --- |
| **A — Ghi vị trí cuối nhận được** | Đơn giản, triển khai nhanh | Có làm mất tiến độ khi cập nhật cũ tới muộn? |
| **B — Kiểm tra version** | Phát hiện cập nhật dựa trên trạng thái cũ | Có nguyên tử trong DB hiện tại; UX xử lý conflict ra sao? |
| **C — Lưu sự kiện** | Hỗ trợ lịch sử phong phú hơn nhưng phức tạp | Thứ tự, lưu trữ, vận hành và chi phí có chấp nhận được? |

Một thử nghiệm bước đầu **giả định** cho thấy A có ghi đè im lặng khi hai yêu cầu cùng tới; B không ghi đè nhưng client chưa biết xử lý xung đột; C chưa được thử vì chi phí khảo sát cao. Sau khi chốt một phương án, nhóm cần ít nhất **bốn tuần** để triển khai, kiểm thử và phát hành theo các điều kiện hiện có.

### Câu hỏi

1. Vì sao việc A hoạt động với một thiết bị **không đủ** để chọn cho bài toán hai thiết bị?
2. Hãy viết câu hỏi và giả thuyết cụ thể của một spike cho phương án B.
3. Chọn **ba kịch bản kiểm thử** quan trọng, gồm ít nhất một trường hợp lỗi.
4. Với hạn sáu tuần và bốn tuần thực hiện sau quyết định, điểm quyết định muộn nhất theo phép tính đơn giản là khi nào? Cần lưu ý gì?
5. Prototype nào giúp kiểm tra **trải nghiệm xử lý xung đột**, không chỉ thuật toán?
6. Nếu spike B dùng dữ liệu giả và bỏ qua phân quyền, có thể merge nguyên mã đó thành feature Done không?
7. Nếu B pass kiểm tra cạnh tranh trong sandbox, được phép kết luận những gì và chưa được kết luận gì?
8. Hãy viết một ADR tối giản và hai PBI tiếp theo từ kết quả spike.
9. Khi môi trường thử nghiệm không sẵn sàng, nhóm nên xử lý tình trạng blocked của spike ra sao?
10. Tại Sprint Review, nên trình bày kết quả khảo sát thế nào để không gây nhầm với Increment đã hoàn tất?

### Gợi ý lời giải

**Câu 1:** A chỉ chứng minh chức năng ghi tuần tự; tình huống cập nhật đồng thời hoặc đến muộn có thể khiến trạng thái mới bị ghi đè. Đây là bất định về **tính đúng đắn**, có hậu quả trực tiếp tới người học.

**Câu 2:**

> “Với hai yêu cầu cùng expectedVersion trên cơ sở dữ liệu mục tiêu, thao tác cập nhật nguyên tử theo version có bảo đảm chỉ một yêu cầu thành công và yêu cầu còn lại báo conflict mà không ghi đè không?”

Giả thuyết có thể bị bác bỏ nếu hai yêu cầu cùng ghi thành công hoặc dữ liệu sai sau cạnh tranh.

**Câu 3:** (1) Ghi bình thường đúng version; (2) hai request cùng version, chỉ một thành công; (3) client gửi version cũ sau khi mất mạng hoặc yêu cầu không có quyền, hệ thống từ chối phù hợp và không thay đổi dữ liệu của người khác.

**Câu 4:** \(6-4=2\) tuần từ đầu kế hoạch. Đây chỉ là **mốc chốt muộn nhất theo các giả định thời gian đơn giản**, không phải mốc phải đợi. Rủi ro, sự phụ thuộc, tính song song và yêu cầu dự phòng có thể khiến phải chốt sớm hơn.

**Câu 5:** Thử hai màn hình/luồng thông báo khi điện thoại và laptop khác tiến độ: tự dùng vị trí server với giải thích hoặc cho người học chọn có hướng dẫn. Quan sát người dùng có hiểu lựa chọn và hậu quả không; không suy từ UI prototype rằng API đã an toàn.

**Câu 6:** Không. Cần kiểm tra quyền tài khoản, hành vi lỗi, kiểm thử tích hợp, review, tiêu chuẩn DoD và các điều kiện vận hành. Mã thử có thể được dùng làm điểm tham khảo hoặc phát triển tiếp sau khi nâng chất lượng, nhưng **không tự là Increment**.

**Câu 7:** Có thể nói B **đã ngăn ghi đè im lặng trong những kịch bản và môi trường đã thử**. Chưa được khẳng định mọi trường hợp offline, tải production, quyền dữ liệu, khả năng phục hồi hoặc trải nghiệm đã đạt.

**Câu 8:** ADR ngắn ghi bối cảnh, A/B/C, bằng chứng, quyết định chọn thử B, hệ quả client phải xử lý conflict và điều kiện xem lại. Hai PBI ví dụ: (i) lưu/đọc tiến độ với version và bảo vệ phân quyền theo DoD; (ii) hiển thị/giải quyết trạng thái xung đột sau khi có quy tắc nghiệp vụ được xác nhận.

**Câu 9:** Minh bạch lý do blocked, người có quyền hỗ trợ, thời điểm kiểm tra lại và tác động tới điểm quyết định. Đừng tự ghi “spike Done” khi chưa có bằng chứng; có thể đổi phương pháp thử hoặc xem lại ưu tiên với Product Owner.

**Câu 10:** Trình bày **câu hỏi, kết quả thử, giới hạn, phương án đề xuất và quyết định cần nhận**. Nếu mới có báo cáo khảo sát hoặc prototype nội bộ, nói rõ **chưa phải Increment có thể dùng và đạt DoD**. Nếu có phần Increment thật, trình bày riêng phần đó.

### Bài tập mở rộng: tự thiết kế spike cho lựa chọn công nghệ

Đề bài: Hệ thống muốn gửi thông báo khi người học hoàn tất một bài kiểm tra. Nhóm chưa biết nên dùng hàng đợi sự kiện hay gọi dịch vụ đồng bộ.

Hãy viết Spike Charter không quá một trang, gồm:

1. Quyết định cần hỗ trợ, yêu cầu độ tin cậy và điều kiện không được mất thông báo.
2. Hai phương án cần so sánh; chi phí/vận hành có thể khác nhau thế nào.
3. Ít nhất hai kịch bản lỗi như timeout, yêu cầu lặp hoặc dịch vụ đích không sẵn.
4. Môi trường và dữ liệu an toàn để thử, cùng cách đo.
5. Timebox và điểm buộc phải chốt.
6. Tiêu chí chọn, loại hoặc khảo sát tiếp và dạng báo cáo kết quả.

**Một hướng tham khảo:** Nếu hệ thống có yêu cầu không được mất thông báo nhưng dịch vụ đích thường gián đoạn, kiểm thử queue/retry có thể rất quan trọng. Tuy vậy, “dùng queue” **không tự bảo đảm đúng một lần**; có thể cần idempotency, giám sát và cơ chế xử lý lặp ở bên nhận. Không nên chọn công nghệ chỉ dựa trên tên gọi mà không kiểm chứng yêu cầu và cơ chế thực tế.

## 22. Checklist thực hành trước, trong và sau spike

### Trước khi bắt đầu

1. **Vấn đề:** Có quyết định cụ thể cần hỗ trợ hay chỉ là mong muốn nghiên cứu chung chung?
2. **Bất định:** Điều chưa biết nào có thể làm nhóm chọn khác?
3. **Giá trị:** Kết quả khảo sát giúp ích gì cho người dùng, Product Goal hoặc Sprint Goal?
4. **Mức rủi ro:** Sai lầm có tác động lớn hay khó đảo ngược không?
5. **Phương án:** Có lựa chọn đơn giản hơn cần kiểm tra trước không?
6. **Giả thuyết:** Có kết quả nào có thể bác bỏ giả thuyết?
7. **Phương pháp:** Spike, prototype, PoC hay lát cắt thật trả lời đúng câu hỏi nhất?
8. **Guardrails:** Có yêu cầu an toàn, quyền dữ liệu và phê duyệt bắt buộc nào?
9. **Timebox:** Đã có giới hạn công sức và mốc xem lại?
10. **Điểm quyết định:** Đến khi nào nhóm không còn khả năng chờ thêm?

### Trong khi thử

11. **Môi trường:** Cấu hình và revision có được ghi đủ để lặp lại?
12. **Dữ liệu:** Test data có hợp lệ và không làm lộ thông tin thật?
13. **Kịch bản:** Có kiểm tra tình huống rủi ro, không chỉ happy path?
14. **Phép đo:** Có ghi đơn vị, số lượt, điều kiện và giới hạn thống kê?
15. **Phụ thuộc:** Nếu blocked, có người xử lý, bước tiếp theo và tác động mốc chốt?
16. **Phạm vi:** Có tránh mở rộng prototype ngoài câu hỏi ban đầu?
17. **Trách nhiệm:** Có phân biệt quyết định kỹ thuật với quyết định nghiệp vụ/tuân thủ?

### Sau khi thử

18. **Kết luận:** Đã trả lời được câu hỏi hay phải báo “chưa đủ bằng chứng”?
19. **Giới hạn:** Có nêu chính xác điều gì chưa chứng minh?
20. **So sánh:** Có loại/giữ phương án vì bằng chứng và rủi ro, không vì sở thích?
21. **Lưu tri thức:** Test, kết quả, ADR và quyết định có được ghi vừa đủ?
22. **Mã thử:** Có quyết định bỏ đi hoặc nâng cấp chất lượng trước khi dùng tiếp?
23. **Backlog:** Có PBI/lát cắt giá trị và công việc giảm rủi ro tiếp theo?
24. **DoD:** Không nhầm prototype thành Increment đã hoàn tất?
25. **Phản hồi:** Có kế hoạch quan sát người dùng và vận hành sau khi giao thật?
26. **Cải tiến:** Nhóm có học được cách thiết kế spike ngắn và đúng câu hỏi hơn?

## 23. Tổng kết: khảo sát để quyết định, không khảo sát để trì hoãn

Spike và prototype giúp nhóm Agile thiết kế tiến hóa khi chưa có đủ thông tin, nhưng mỗi công cụ phục vụ một loại câu hỏi:

| Nếu câu hỏi là… | Cách tiếp cận nên cân nhắc | Kết quả cần có |
| --- | --- | --- |
| “Công nghệ có giải quyết được rủi ro quan trọng không?” | **Spike/PoC kỹ thuật có giới hạn** | Bằng chứng, rủi ro còn lại, quyết định |
| “Người dùng có hiểu và sử dụng được cách tương tác này không?” | **Prototype trải nghiệm** | Quan sát, tín hiệu, điều cần điều chỉnh |
| “Các thành phần có kết nối được xuyên hệ thống không?” | **Walking skeleton** | Rủi ro tích hợp được phát hiện sớm |
| “Người dùng có nhận được giá trị đủ để kiểm tra giả định sản phẩm không?” | **MVP/lát cắt sử dụng thật phù hợp** | Sản phẩm đủ chất lượng và phản hồi thực tế |
| “Làm thế nào tiếp tục thay đổi an toàn sau khi chốt?” | **TDD, CI, refactoring, DoD, observability** | Increment đáng tin cậy, chi phí thay đổi có thể kiểm soát |

**Ghi nhớ:** **Spike bắt đầu bằng một quyết định chưa chắc chắn**, **prototype bắt đầu bằng một giả thuyết cần kiểm chứng**, và cả hai phải kết thúc bằng **bằng chứng, giới hạn cùng bước hành động rõ ràng**. Timebox giúp kiểm soát chi phí, không biến một kết quả chưa đủ thành sự thật. Mã thử nghiệm không tự đáp ứng Definition of Done. Khi kết hợp các khảo sát có mục đích với user story, Product Backlog, Scrum, Kanban và các thực hành kỹ thuật XP, nhóm có thể **học nhanh, chọn thiết kế có trách nhiệm, giao phần tăng dần an toàn và tiếp tục tiến hóa theo phản hồi thực tế**.
