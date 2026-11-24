# Xử lý giả định chưa được kiểm chứng bằng công việc khảo sát có giới hạn

> **Chương:** Yêu cầu thích ứng  
> **Học phần:** AGILE_DEVELOPMENT — phát triển phần mềm thích ứng nhờ phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; kết hợp user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để chọn cách phối hợp thích hợp.

Khi làm rõ yêu cầu, nhóm thường nghe những phát biểu có vẻ chắc chắn: “Người dùng sẽ thích đăng nhập bằng số điện thoại”, “API đối tác chịu được một nghìn yêu cầu đồng thời”, “Chuyển sang cơ sở dữ liệu mới sẽ giải quyết vấn đề hiệu năng”, “Có thể hoàn tất chức năng này trong một Sprint”. Một số phát biểu là sự thật đã có bằng chứng; số khác mới là **giả định**. Nếu biến giả định quan trọng thành cam kết phạm vi, kiến trúc hay ngày giao mà không kiểm tra, nhóm có thể phát hiện sai lầm khi chi phí sửa đã rất lớn.

Agile khuyến khích **học sớm để giảm rủi ro cho quyết định tiếp theo**. Một cách thực tế là tạo **công việc khảo sát có giới hạn** (*timeboxed exploration*, thường gọi là *spike* trong phát triển phần mềm): dành một khoảng thời gian và nguồn lực đã xác định để trả lời **một câu hỏi cụ thể**, thu thập bằng chứng vừa đủ, rồi đưa ra quyết định tiếp tục, thay đổi, thử thêm hoặc dừng.

Mục đích của spike không phải “cứ nghiên cứu cho đến khi biết hết”. Giá trị của nó nằm ở việc **giảm bất định có tác động đáng kể đối với một quyết định**, trong giới hạn chi phí hợp lý. Kết quả có thể là lựa chọn kỹ thuật, giả thuyết bị bác bỏ, một prototype, tiêu chí chấp nhận rõ hơn hoặc quyết định chưa nên đầu tư vào tính năng.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **sự thật, giả định, giả thuyết, rủi ro, bằng chứng và quyết định** trong yêu cầu phần mềm.
2. Nhận diện giả định nào nên khảo sát trước dựa trên mức độ bất định và hậu quả nếu sai.
3. Viết một công việc khảo sát có giới hạn với câu hỏi, phạm vi, thời hạn, phương pháp, người phối hợp, tiêu chí dừng và đầu ra có thể kiểm chứng.
4. Chọn phương pháp phù hợp: phỏng vấn, quan sát, thử bản mẫu, spike kỹ thuật, thử nghiệm tích hợp, đo hiệu năng hoặc kiểm tra dữ liệu.
5. Chuyển kết quả khảo sát thành quyết định về user story, Product Backlog, thiết kế và kế hoạch giao sản phẩm tăng dần.
6. Tránh dùng spike để trì hoãn lựa chọn, né kiểm thử, hoặc che một khối công việc xây tính năng chưa rõ phạm vi.

## 2. Vì sao yêu cầu thích ứng cần quản lý giả định?

Một yêu cầu thường chứa đồng thời:

- **Nhu cầu:** Người dùng muốn hoàn tất tác vụ nào hoặc tránh vấn đề gì?
- **Giải pháp đề xuất:** Chức năng hoặc thiết kế người liên quan đang hình dung.
- **Giả định:** Điều nhóm tin là đúng nhưng chưa đủ bằng chứng để dựa vào.
- **Ràng buộc:** Điều bắt buộc phải tôn trọng, như bảo mật, pháp lý, hợp đồng, chi phí hoặc khả năng vận hành.
- **Tiêu chí thành công:** Dấu hiệu cho biết giải pháp thật sự cải thiện kết quả.

Ví dụ, một yêu cầu viết “Thêm chatbot để giảm số yêu cầu hỗ trợ” bao gồm:

| Thành phần | Cách diễn đạt |
| --- | --- |
| Nhu cầu | Người dùng cần nhận câu trả lời chính xác nhanh hơn. |
| Giải pháp đề xuất | Chatbot tự động. |
| Giả định về giá trị | Phần lớn câu hỏi có thể giải đáp qua hội thoại tự động. |
| Giả định kỹ thuật | Hệ thống tra cứu trả kết quả đủ chính xác, có thể vận hành an toàn. |
| Ràng buộc | Không tiết lộ thông tin cá nhân; biết khi nào phải chuyển tới nhân viên hỗ trợ. |
| Tín hiệu thành công | Người dùng giải quyết được vấn đề, thời gian hỗ trợ giảm mà chất lượng không giảm. |

Nếu bắt đầu bằng “xây chatbot trong bốn tuần”, nhóm đã biến **một giải pháp chưa được xác minh** thành kế hoạch. Khảo sát có giới hạn có thể chỉ ra rằng phần lớn câu hỏi là tra cứu trạng thái đơn hàng, và một trang tự phục vụ có thể đem lại giá trị nhanh hơn. Đây là **giảm công việc không cần làm** bằng bằng chứng, phù hợp tinh thần Agile.

### 2.1. Phân biệt năm khái niệm quan trọng

| Khái niệm | Đặc điểm | Ví dụ trong sản phẩm đặt lịch |
| --- | --- | --- |
| **Sự thật được ghi nhận** | Quan sát hoặc dữ liệu có nguồn và phạm vi cụ thể; vẫn cần xem chất lượng đo. | Trong mẫu phiên sử dụng đã ghi nhận, 38/100 lượt thử bỏ dở tại bước chọn giờ. |
| **Giả định** | Một điều đang được coi là đúng để lập kế hoạch nhưng chưa kiểm chứng đủ. | Người dùng bỏ dở vì giao diện chọn giờ quá khó hiểu. |
| **Giả thuyết kiểm chứng** | Phát biểu có điều kiện, dự kiến quan sát và có khả năng bị bác bỏ. | Nếu hiển thị giờ trống sớm hơn, tỷ lệ hoàn tất đặt lịch sẽ tăng trong nhóm người dùng mục tiêu. |
| **Rủi ro** | Khả năng một sự kiện hoặc giả định sai gây hậu quả bất lợi. | Nếu hiển thị sai giờ trống, khách có thể tạo lịch trùng và mất niềm tin. |
| **Quyết định** | Lựa chọn cần đưa ra với bằng chứng và giới hạn hiện tại. | Thử giao diện mới với nhóm nhỏ, giữ cơ chế chống trùng ở phía server. |

Ví dụ “38/100” ở đây **chỉ minh họa cách ghi dữ liệu**, không phải thống kê từ nghiên cứu thực tế. Mẫu có thể nhỏ hoặc bị thiên lệch; từ số lượt bỏ dở không thể suy ra ngay **nguyên nhân**. Câu hỏi khảo sát cần nhắm đúng khoảng trống giữa điều đã thấy và điều chưa biết.

### 2.2. Bốn nhóm giả định thường gặp

| Nhóm giả định | Câu hỏi | Cách thu thập bằng chứng điển hình |
| --- | --- | --- |
| **Giá trị / nhu cầu (value, desirability)** | Người dùng có gặp vấn đề và có muốn giải quyết đến mức thay đổi hành vi không? | Quan sát, phỏng vấn theo trải nghiệm thật, dữ liệu hành vi, thử nghiệm đề xuất giá trị. |
| **Khả năng sử dụng (usability)** | Người dùng mục tiêu có hiểu và hoàn tất tác vụ không? | Bài thử tác vụ với bản mẫu, quan sát điểm vấp, kiểm tra khả năng tiếp cận. |
| **Khả thi kỹ thuật (feasibility)** | Hệ thống, API và đội ngũ có thực hiện được trong giới hạn không? | Spike tích hợp, proof of concept, benchmark có kiểm soát, kiểm tra hợp đồng API. |
| **Khả thi kinh doanh/vận hành (viability)** | Giải pháp có phù hợp chi phí, nghĩa vụ, vận hành và mô hình kinh doanh không? | Phân tích chi phí, tham vấn pháp lý/bảo mật, thử quy trình hỗ trợ, kiểm tra SLA. |

Bốn loại này liên quan nhau. Một tính năng có thể hấp dẫn người dùng nhưng quá đắt hoặc không đáp ứng quyền riêng tư. Ngược lại, demo kỹ thuật chạy thành công **không chứng minh người dùng cần tính năng**.

## 3. Không phải giả định nào cũng cần một spike

Khảo sát cũng tiêu tốn năng lực, nên chỉ dùng khi **giá trị của thông tin mới đủ lớn** so với chi phí thu thập. Một cách sàng lọc thực tế là đặt giả định vào hai chiều:

1. **Mức bất định:** Hiện nhóm chắc tới đâu? Bằng chứng có mạnh, mới, đại diện và liên quan đến ngữ cảnh thật không?
2. **Hậu quả nếu sai:** Mất bao nhiêu giá trị, thời gian, dữ liệu hoặc khả năng vận hành? Việc sửa lại có khó và tốn kém không?

|  | Hậu quả nếu sai thấp | Hậu quả nếu sai cao |
| --- | --- | --- |
| **Bất định thấp** | Thường có thể tiến hành, giám sát kết quả. | Xác minh các giới hạn quan trọng và chuẩn chất lượng; không mặc nhiên cần nghiên cứu lớn. |
| **Bất định cao** | Có thể thử nhanh trong phạm vi nhỏ hoặc chấp nhận học sau phát hành an toàn. | **Ứng viên tốt cho spike/timebox sớm** trước khi cam kết giải pháp lớn. |

**Ví dụ:** Chọn tên cho một nút phụ dễ đổi và ít rủi ro có thể kiểm tra nhanh bằng bản mẫu hoặc A/B test khi có điều kiện. Nhưng thay công nghệ lưu trữ dữ liệu giao dịch có thể khó đảo ngược và ảnh hưởng tính toàn vẹn; nếu chưa hiểu khả năng di chuyển và khôi phục, một khảo sát kỹ thuật có giới hạn thường đáng đầu tư.

### 3.1. Những câu hỏi trước khi tạo việc khảo sát

- Nếu giả định sai, **quyết định nào** phải thay đổi?
- Việc đó gây thiệt hại lớn đến đâu và **có thể đảo ngược** không?
- Có bằng chứng nào đã sẵn có trong log, dữ liệu khách hàng, tài liệu API hoặc người có kinh nghiệm?
- Có thể **xử lý bằng một lát cắt có giá trị** thay vì tạo hạng mục khảo sát riêng?
- Có phương pháp ngắn, ít tốn kém hơn: hỏi chuyên gia, chạy một bài test, đọc hợp đồng API?
- Ai có quyền quyết định dựa trên kết quả; khi nào cần câu trả lời?

**Không tạo spike chỉ vì story chưa được ước lượng.** Nếu nhóm thiếu hiểu biết về một yêu cầu, trước hết nên refinement: làm rõ nghiệp vụ, chia nhỏ, tìm ví dụ chấp nhận. Spike phù hợp khi vẫn còn **một bất định cụ thể ảnh hưởng đến phương án hoặc độ rủi ro** mà việc trao đổi thông thường chưa giải quyết được.

### 3.2. Tập trung vào “giảm bất định có giá trị”

Không thể chắc chắn tuyệt đối trước khi xây phần mềm. Một spike được coi là hữu ích ngay cả khi kết luận là “hiện chưa đủ bằng chứng để chọn phương án A”, miễn là nó chỉ ra:

- Điều gì đã biết chắc hơn trước.
- Điều gì vẫn chưa biết và vì sao.
- Phương án nào bị loại hoặc trở nên đáng cân nhắc.
- Bước nhỏ nhất tiếp theo để quyết định hoặc kiểm chứng.

Nếu câu hỏi không ảnh hưởng bất kỳ quyết định nào, nhóm nên xem lại **lý do làm khảo sát** trước khi cấp thêm thời gian.

## 4. Spike/timebox là gì và không phải là gì?

**Spike** là một hạng mục tìm hiểu, thử nghiệm hoặc điều tra có phạm vi rõ nhằm giảm bất định. Trong XP, khái niệm *spike solution* thường gắn với việc thử một giải pháp kỹ thuật để học trước khi thiết kế và xây chính thức. Trong thực hành Agile rộng hơn, các nhóm còn gọi công việc khám phá nhu cầu hoặc khảo sát rủi ro bằng các tên khác như *discovery task*, *experiment*, *research task*. Tên không quan trọng bằng câu hỏi và cách kết thúc.

**Timebox** là giới hạn thời gian (và có thể cả công sức, chi phí) được thống nhất **trước khi bắt đầu**. Đến mốc đó, nhóm dừng để trình bày điều đã học và quyết định: dùng kết quả hiện có, đổi phương pháp, mở thêm một khảo sát **được phê duyệt rõ ràng**, hoặc chấp nhận rủi ro còn lại.

| Công việc | Mục tiêu trực tiếp | Đầu ra tối thiểu | Tiêu chí hoàn tất |
| --- | --- | --- | --- |
| **User story tạo giá trị** | Đưa một hành vi có ích tới người dùng | Increment đáp ứng tiêu chí chấp nhận và chuẩn chất lượng | Hành vi đã tích hợp và kiểm chứng theo DoD |
| **Spike kỹ thuật** | Trả lời một câu hỏi khả thi hoặc giảm rủi ro triển khai | Bằng chứng thử nghiệm, lựa chọn và hạn chế | Câu hỏi được trả lời tới mức ra quyết định hoặc hết timebox và nêu rõ kết quả/việc tiếp |
| **Khảo sát nhu cầu** | Kiểm tra giả định về vấn đề, giá trị, cách dùng | Ghi nhận quan sát, mức tin cậy và kết luận | Có bằng chứng đủ cho quyết định tiếp theo hoặc báo rõ chưa đủ |
| **Sửa lỗi đã rõ nguyên nhân** | Khôi phục hành vi đúng | Thay đổi code, kiểm thử, triển khai/khôi phục | Tiêu chí lỗi được giải quyết; không cần gắn nhãn spike |
| **Nghiên cứu tự do** | Mở rộng hiểu biết nói chung | Có thể là tài liệu hoặc kỹ năng | Không tự động phù hợp để đưa vào backlog delivery nếu không có quyết định cần hỗ trợ |

**Lưu ý về Scrum:** Scrum Guide không quy định một sự kiện hay loại artifact bắt buộc tên “Spike”. Một Scrum Team có thể đưa công việc giảm bất định vào Product Backlog và kế hoạch Sprint nếu việc đó giúp đạt mục tiêu. Tuy nhiên, **một bản báo cáo khảo sát không tự biến thành Increment sản phẩm**; Increment cần đáp ứng Definition of Done và là phần của sản phẩm sử dụng được.

### 4.1. Timebox không phải lời hứa chắc chắn sẽ tìm ra câu trả lời

Đặt timebox hai ngày nghĩa là nhóm dành tối đa hai ngày để **thu thập bằng chứng phù hợp**, không bảo đảm thế giới sẽ cung cấp câu trả lời đầy đủ sau đúng hai ngày. Nếu cần dữ liệu do đối tác cung cấp, nhóm nên ghi phụ thuộc và phương án dự phòng. Hết timebox mà còn chưa chắc chắn, hãy **báo trạng thái bất định trung thực**, không bịa ra một câu trả lời cho đủ thủ tục.

### 4.2. Spike không có nghĩa xây gần xong rồi mới gọi là khảo sát

Nếu một hạng mục “nghiên cứu cách viết chức năng đăng ký” kéo dài ba Sprint, sinh ra gần toàn bộ giao diện và backend, nhưng không có câu hỏi, tiêu chí dừng hoặc kết luận, đó có thể là **công việc triển khai bị đặt tên sai**.

Một prototype/spike code có thể **cố ý bỏ bớt tính năng để kiểm chứng khả thi**, nên không mặc nhiên đủ bảo mật, kiểm thử, vận hành và khả năng bảo trì để đưa vào production. Nếu muốn dùng lại mã, cần đánh giá và nâng cấp theo tiêu chuẩn chất lượng của sản phẩm trước khi tích hợp.

## 5. Viết một spike có giới hạn đủ rõ để thực hiện

Spike tốt có thể được mô tả trên một trang ngắn. Trước khi bắt đầu, cần điền:

| Trường | Câu hỏi cần trả lời |
| --- | --- |
| **Bối cảnh quyết định** | Hạng mục hoặc lựa chọn nào đang bị chặn bởi bất định? |
| **Giả định cần kiểm tra** | Nhóm đang tin điều gì? Nguồn của niềm tin đó? |
| **Câu hỏi trọng tâm** | Câu hỏi nào nếu trả lời được sẽ thay đổi quyết định? |
| **Phạm vi và không thuộc phạm vi** | Sẽ khảo sát đúng đối tượng, luồng, API, dữ liệu nào? Điều gì không làm? |
| **Timebox và năng lực** | Dành bao lâu, bao nhiêu người, khi nào xem kết quả? |
| **Phương pháp và bằng chứng** | Chạy thử gì, quan sát ai, dùng dữ liệu nào, cách ghi nhận? |
| **Tiêu chí dừng / tiêu chí kết luận** | Khi nào đủ để ra quyết định? Khi nào dừng vì không còn hữu ích hoặc vượt rủi ro? |
| **Phương án đang cân nhắc** | Chọn A, B, tiếp tục thử, đổi phạm vi hay dừng? |
| **Chỉ số và ràng buộc bảo vệ** | Chất lượng, quyền riêng tư, chi phí, vận hành, độ tin cậy nào phải giữ? |
| **Người chịu trách nhiệm** | Ai làm khảo sát, ai hỗ trợ, ai quyết định theo kết quả? |
| **Hình thức bàn giao** | Bản tóm tắt bằng chứng, demo, quyết định, backlog update hoặc thí nghiệm tiếp theo. |

### 5.1. Ví dụ một “spike brief” cho tích hợp API

Giả sử nhóm chuẩn bị tích hợp một API đặt lịch của đối tác nhưng chưa biết cơ chế **chống tạo lịch trùng** khi người dùng gửi yêu cầu nhiều lần.

~~~yaml
title: "Spike: API đối tác có hỗ trợ chống tạo lịch trùng khi gửi lại?"
decision_blocked: "Chọn thiết kế đảm bảo mỗi yêu cầu đặt lịch hợp lệ chỉ tạo một lịch"
assumption: "API đối tác hỗ trợ idempotency key hoặc cơ chế tương đương"
question: "Khi gửi cùng yêu cầu hai lần và khi mạng timeout, API trả kết quả nào?"
timebox: "Tối đa 1 ngày làm việc của 2 người; xem kết quả cuối ngày"
in_scope:
  - "Đọc hợp đồng API và xác nhận với đối tác nếu cần"
  - "Thử 3 tình huống: lặp tuần tự, lặp đồng thời, timeout rồi gửi lại"
out_of_scope:
  - "Xây toàn bộ luồng booking production"
  - "Kiểm thử tải quy mô lớn"
evidence:
  - "Request/response đã ẩn thông tin nhạy cảm"
  - "Kết quả các tình huống, bản API và điều kiện môi trường thử"
stop_when: "Có đủ bằng chứng chọn cơ chế chống trùng hoặc hết timebox"
options: ["Tận dụng khóa idempotency", "Tự kiểm soát tại hệ thống trung gian", "Đổi cách tích hợp"]
decision_owner: "Nhóm kỹ thuật theo phân quyền, tham vấn Product Owner khi ảnh hưởng phạm vi"
deliverable: "Bảng so sánh phương án, rủi ro còn lại và story/kiểm thử cần bổ sung"
~~~

Các giới hạn “1 ngày”, “2 người” và số tình huống trong mẫu **chỉ để minh họa**, không phải chuẩn chung. Timebox thực tế phải tương xứng với giá trị quyết định, thời hạn và phụ thuộc. Có thể kết thúc sớm nếu đã đủ bằng chứng.

### 5.2. Viết câu hỏi đủ hẹp

| Quá rộng, khó kết thúc | Cụ thể, có thể khảo sát trong timebox |
| --- | --- |
| “Tìm hiểu toàn bộ công nghệ sự kiện.” | “Trong môi trường thử, giải pháp A có giữ đúng thứ tự xử lý cho một đơn hàng khi retry không?” |
| “Nghiên cứu người dùng của ứng dụng.” | “Trong 5–8 buổi quan sát được tuyển phù hợp, những bước nào khiến người dùng mục tiêu không hoàn tất đặt lịch?” |
| “Nghiên cứu hiệu năng hệ thống.” | “Với luồng truy vấn X và bộ dữ liệu thử có đặc điểm Y, p95 độ trễ và tài nguyên của hai phương án ra sao?” |
| “Thiết kế hệ thống phân quyền mới.” | “Hai mô hình phân quyền đề xuất có đáp ứng ba tình huống nghiệp vụ khó nhất theo yêu cầu hiện tại không?” |
| “Khảo sát dùng AI.” | “Dịch vụ tìm kiếm có trả được thông tin đặt lịch đúng quyền truy cập với tập kiểm tra đã xác định không?” |

Một spike tốt tìm câu trả lời **đủ để chọn bước kế tiếp**. Từ ngữ như “nghiên cứu toàn diện”, “tìm giải pháp tốt nhất cho mọi trường hợp” hoặc “hết nghi ngờ” thường báo hiệu phạm vi chưa rõ.

## 6. Quy trình từ giả định tới quyết định

~~~mermaid
flowchart LR
    A["Yêu cầu / tín hiệu mới"] --> B["Tách sự thật và giả định"]
    B --> C{"Giả định có ảnh hưởng lớn và chưa rõ?"}
    C -->|Không| D["Refine / làm lát cắt nhỏ và đo"]
    C -->|Có| E["Viết câu hỏi, timebox, phương pháp"]
    E --> F["Thu thập bằng chứng an toàn"]
    F --> G["Đánh giá mức tin cậy và giới hạn"]
    G --> H{"Đủ cơ sở ra quyết định?"}
    H -->|Có| I["Chọn phương án, cập nhật backlog"]
    H -->|Chưa| J["Ghi phần chưa biết, cân nhắc dừng / khảo sát tiếp"]
    J --> I
    D --> K["Giao giá trị tăng dần"]
    I --> K
    K --> L["Đo kết quả và học tiếp"]
    L --> B
~~~

### Bước 1 — Ghi vấn đề và điều chưa biết

Phân tách lời yêu cầu, kết quả mong muốn, ràng buộc và giả định. Hỏi: **Quyết định nào đang bị chặn?** Nếu nhóm đã có đủ thông tin để chọn một lát cắt an toàn và kiểm tra trực tiếp, có thể không cần spike.

### Bước 2 — Ưu tiên giả định có ảnh hưởng lớn

Đánh giá mức bất định và hậu quả nếu sai. Tránh làm nghiên cứu chỉ vì tò mò hoặc vì đề tài hấp dẫn. Nếu giả định liên quan đến an toàn dữ liệu hoặc nghĩa vụ pháp lý, phải xác minh với người có thẩm quyền thích hợp.

### Bước 3 — Chọn phương pháp và giới hạn

Xác định rõ câu hỏi, dữ liệu, phương án thử, timebox, người tham gia và điểm dừng. Nếu cần phỏng vấn người dùng, mô tả nhóm người dùng mục tiêu và nguyên tắc xử lý dữ liệu cá nhân. Nếu cần spike kỹ thuật, mô tả môi trường, phiên bản, kích thước dữ liệu và cách tái hiện.

### Bước 4 — Thực hiện khảo sát và ghi bằng chứng

Ghi **quan sát thực tế** tách khỏi **diễn giải**. Một bản demo chạy đúng một lần là bằng chứng hẹp; một lần gặp lỗi không luôn chứng minh phương án bất khả thi. Cần ghi điều kiện thử, mẫu, giới hạn và yếu tố có thể làm sai lệch kết luận.

### Bước 5 — Dừng tại timebox và phân tích

Đến mốc đã thống nhất, nhóm trình bày:

- Những giả định nào được ủng hộ, bị bác bỏ hoặc vẫn chưa rõ.
- Bằng chứng nào dẫn tới nhận định, mạnh/yếu ở đâu.
- Phương án phù hợp và đánh đổi chính.
- Rủi ro còn lại và điều kiện cần kiểm tra khi delivery.
- Có nên khảo sát tiếp không; nếu có, **câu hỏi mới và chi phí bổ sung** là gì.

Không tự động kéo dài đến khi có câu trả lời “đẹp”. Việc mở thêm timebox là một **quyết định đầu tư mới**.

### Bước 6 — Dùng kết quả để đổi backlog và hành động

Kết luận khảo sát phải tác động tới điều thực tế: sắp lại backlog, viết tiêu chí chấp nhận, tách user story, chọn thiết kế, cập nhật dự báo, bỏ hướng ít giá trị hoặc mở một thí nghiệm mới. Đừng để báo cáo nghiên cứu nằm yên mà đội delivery vẫn làm theo giả định cũ.

## 7. Chọn phương pháp thu thập bằng chứng phù hợp

| Câu hỏi cần học | Phương pháp thường hữu ích | Bằng chứng mang lại | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| Người dùng đang gặp khó khăn gì? | Phỏng vấn theo tình huống đã xảy ra, quan sát hành vi, phân tích hỗ trợ. | Mô tả trở ngại, ngữ cảnh và động cơ. | Người được hỏi có thể nhớ không chính xác; mẫu phỏng vấn nhỏ không đại diện thống kê. |
| Người dùng có hoàn tất luồng được không? | Usability test với bản mẫu hoặc lát cắt. | Các bước thất bại, nhầm lẫn, thao tác cần cải thiện. | Chỉ đo hành vi trong điều kiện thử; không tự chứng minh tác động lâu dài. |
| Thay đổi có cải thiện kết quả không? | Phát hành giới hạn, theo dõi trước/sau, thử nghiệm đối chứng khi khả thi. | Tín hiệu kết quả và độ ổn định. | So sánh trước/sau dễ nhiễu; A/B test cần thiết kế mẫu, tiêu chí và điều kiện phù hợp. |
| API có hỗ trợ yêu cầu nghiệp vụ không? | Đọc hợp đồng, hỏi nhà cung cấp, prototype tích hợp. | Request/response, giới hạn, lỗi, phương án thay thế. | Sandbox có thể khác production về tải và cấu hình. |
| Thiết kế có đạt độ trễ mục tiêu không? | Benchmark/đo tải có kiểm soát. | Độ trễ, mức dùng tài nguyên, điểm nghẽn ở điều kiện thử. | Kết quả phụ thuộc dữ liệu, cấu hình, kịch bản và kích thước mẫu. |
| Phương án có đáp ứng bảo mật/tuân thủ không? | Threat modeling, rà soát chính sách, tham vấn chuyên gia, kiểm thử phù hợp. | Danh sách rủi ro, yêu cầu và biện pháp kiểm soát. | Bản mẫu chạy được không đủ chứng minh an toàn hoặc hợp pháp. |
| Quy trình làm việc gây chờ ở đâu? | Vẽ workflow, xem WIP/cycle time, phỏng vấn nhóm. | Điểm nghẽn và giả thuyết cải tiến dòng. | Thay đổi số liệu có thể do kích thước việc và nguồn yêu cầu. |

### 7.1. Không dùng một loại bằng chứng để trả lời câu hỏi khác

- “Người dùng **nói** sẽ dùng” chưa chắc họ sẽ sử dụng khi sản phẩm thật có chi phí và ràng buộc.
- “Prototype **chạy được**” chưa chứng minh hệ thống hoạt động ổn định ở tải thực tế.
- “Hai ngày sau phát hành tỷ lệ chuyển đổi tăng” chưa chứng minh nguyên nhân là thay đổi vừa làm.
- “Không tìm thấy lỗi trong mười ca thử” chưa chứng minh tính năng không có lỗi.
- “Chuyên gia dự đoán sẽ ổn” là đầu vào có giá trị, nhưng cần đối chiếu bối cảnh sử dụng.

Phương pháp và mức bằng chứng phải phù hợp **quyết định dự kiến đưa ra**. Nếu quyết định khó đảo ngược và hậu quả lớn, một demo vui mắt không đủ.

### 7.2. Thực hiện an toàn, có đạo đức

Để kiểm chứng giả định, không được tùy tiện đưa dữ liệu cá nhân thật vào prototype, log hoặc dịch vụ thứ ba. Khi quan sát người dùng, cần có sự đồng ý phù hợp, chỉ thu thập dữ liệu cần thiết và hạn chế định danh. Nếu câu hỏi liên quan tới lỗ hổng bảo mật, sử dụng môi trường và quyền thử nghiệm đã được cho phép. Mức độ khảo sát nhanh không làm giảm nghĩa vụ bảo vệ người dùng.

## 8. Hai ví dụ spike với tiêu chí dừng rõ ràng

### 8.1. Spike kỹ thuật: bảo đảm không tạo lịch trùng khi mạng chập chờn

**Bối cảnh:** Một hệ thống đặt lịch gọi API đối tác để ghi lịch. API có thể timeout sau khi đã lưu dữ liệu. Nếu người dùng bấm lại, hệ thống có nguy cơ tạo hai lịch.

**Giả định chưa kiểm chứng:** API hỗ trợ khóa idempotency hoặc cách truy vấn trạng thái để nhận biết yêu cầu trước đã thành công.

**Quyết định bị chặn:** Cách thiết kế retry và phục hồi khi mất kết nối.

**Timebox minh họa:** Một ngày làm việc, gồm đọc hợp đồng và chạy thử các tình huống quan trọng trong sandbox với dữ liệu thử.

| Phép thử | Dữ liệu cần ghi | Cách diễn giải |
| --- | --- | --- |
| Gửi cùng yêu cầu hai lần tuần tự. | Response, mã lịch, trạng thái dữ liệu sau hai lần. | Có tạo hai lịch hay không trong kịch bản đơn giản. |
| Gửi hai yêu cầu gần như đồng thời. | Thời điểm gửi, mã yêu cầu, số lịch tạo, lỗi. | Cơ chế chống trùng có bảo vệ khỏi cạnh tranh đồng thời không. |
| Giả lập timeout rồi retry. | Trạng thái của lần đầu, response lần retry, số lịch cuối cùng. | Có cần cơ chế truy vấn trạng thái sau timeout không. |
| Gửi cùng khóa nhưng nội dung khác. | Mã lỗi hoặc hành vi API. | Điều kiện hợp lệ của khóa idempotency và lỗi cần xử lý. |

**Tiêu chí dừng:** Khi đã chứng minh đủ để chọn cơ chế và viết yêu cầu kiểm thử cho các trường hợp trọng yếu, hoặc hết timebox và ghi rõ phần chưa biết. Nếu sandbox không phản ánh production, kết luận phải nói rõ giới hạn và điều kiện kiểm tra lại trước phát hành.

**Đầu ra mẫu (giả định):**

> “API chấp nhận khóa idempotency và thử nghiệm trong sandbox không tạo trùng khi retry tuần tự. Chưa đủ bằng chứng cho tải đồng thời và timeout đặc biệt. Đề nghị dùng khóa cho mỗi hành động người dùng, lưu trạng thái yêu cầu ở hệ thống trung gian, bổ sung kiểm thử cạnh tranh và quan sát kết quả khi rollout giới hạn.”

Đây là một kết luận hữu ích **dù còn bất định**: nhóm xác định được cách triển khai khả dĩ, kiểm thử bổ sung và rủi ro còn lại. Không nên khẳng định “API đã được chứng minh luôn an toàn” từ vài phép thử.

**Backlog sau khảo sát:** User story “đặt một lịch hợp lệ, không sinh trùng khi gửi lại”; các tiêu chí chấp nhận cho retry/timeout; công việc quan sát lỗi; nếu cần thêm thử nghiệm tải, tạo hạng mục có câu hỏi và timebox riêng.

### 8.2. Khảo sát nhu cầu: vì sao người dùng bỏ dở luồng đặt lịch?

**Bối cảnh:** Dữ liệu ghi nhận một tỷ lệ bỏ dở cao ở bước chọn giờ trên điện thoại.

**Giả định:** Người dùng bỏ dở vì danh sách giờ quá dài; nhóm tính xây bộ lọc phức tạp theo địa điểm.

**Quyết định bị chặn:** Có nên xây bộ lọc, đơn giản hóa màn hình hay thay đổi thứ tự các bước?

**Timebox minh họa:** Hai ngày để chuẩn bị kịch bản, quan sát một nhóm người dùng mục tiêu có tiêu chí tuyển chọn rõ và tổng hợp kết quả. Số người tham gia tùy loại câu hỏi, tính đa dạng của người dùng và nguồn lực; **không coi một con số mẫu nhỏ là đại diện thống kê**.

**Cách khảo sát:**

1. Chọn người có bối cảnh sử dụng gần với người dùng sản phẩm; xin phép phù hợp.
2. Giao tác vụ thực tế: “Hãy đặt một lịch tư vấn phù hợp với thời gian của bạn”.
3. Quan sát thao tác và câu hỏi người dùng nêu ra, hạn chế gợi ý đáp án.
4. Ghi lại điểm dừng, nhầm lẫn và lý do người dùng nói ra; đối chiếu với dữ liệu sản phẩm.
5. Phác thảo hai phương án nhỏ và cho thử lại, tránh kết luận từ ý kiến thích/không thích đơn thuần.

**Kết quả minh họa:** Người dùng không khó chọn quá nhiều giờ; họ lo không biết giờ còn trống thật hay không và không thấy rõ nút xác nhận. Nhóm quyết định **hoãn bộ lọc** để thử hiển thị tình trạng chỗ và trạng thái xác nhận rõ hơn.

**Điểm dừng:** Khi có đủ bằng chứng định tính để xác định vấn đề ưu tiên và phương án thử tiếp theo, hoặc hết timebox. Kết luận chỉ nên nói “trong các phiên quan sát, chúng tôi thấy…” chứ không gán tỷ lệ ảnh hưởng cho toàn bộ khách hàng nếu chưa có phép đo đại diện.

**Backlog sau khảo sát:** Một hoặc hai user story về trạng thái giờ trống và xác nhận; kế hoạch đo tỷ lệ hoàn tất, số yêu cầu lỗi và tỷ lệ lịch trùng sau phát hành giới hạn.

### 8.3. Vì sao không cần nghiên cứu mọi thứ trước khi giao?

Nhóm có thể vẫn chưa biết người dùng có cần hủy lịch qua ứng dụng hay không. Nếu luồng đặt lịch cơ bản an toàn và có thể giao, họ có thể phát hành lát cắt này trước, quan sát nhu cầu rồi quyết định story tiếp theo. **Khảo sát và delivery diễn ra song song**, tập trung vào rủi ro quan trọng nhất tại thời điểm ra quyết định.

## 9. Chuyển bằng chứng thành yêu cầu và Product Backlog

Kết quả khảo sát có giá trị khi thay đổi được một hoặc nhiều yếu tố sau:

- **Product Goal / kết quả:** Có cần điều chỉnh vấn đề ưu tiên hoặc giả thuyết giá trị?
- **Thứ tự Product Backlog:** Nên làm gì trước, bỏ gì, thử gì tiếp?
- **User story:** Vai trò, nhu cầu, lợi ích có thay đổi? Có chia lát cắt nhỏ hơn không?
- **Tiêu chí chấp nhận:** Có trường hợp biên, lỗi, quyền truy cập hay giới hạn cần ghi rõ?
- **Thiết kế và rủi ro:** Chọn phương án kiến trúc, thêm kiểm thử, giám sát hoặc phương án phục hồi nào?
- **Kế hoạch và dự báo:** Giả định ước lượng nào sai, phụ thuộc nào phải được xử lý, cần trao đổi với ai?

### 9.1. Ví dụ từ spike đến user story

**Trước khảo sát:**

> “Là khách hàng, tôi muốn đặt lịch qua điện thoại để không cần gọi tổng đài.”

Story này chưa làm rõ các trường hợp retry và tình trạng giờ trống.

**Sau khảo sát kỹ thuật và nhu cầu:**

> “Là khách đang đặt lịch trên điện thoại, tôi muốn thấy khung giờ còn trống và nhận xác nhận rõ ràng sau một lần gửi, để biết lịch đã được ghi nhận mà không phải gửi lại nhiều lần.”

**Ví dụ tiêu chí chấp nhận:**

~~~gherkin
Feature: Đặt lịch và phản hồi kết quả

  Scenario: Khung giờ hợp lệ và còn trống
    Given khách đang xem một khung giờ còn trống
    When khách gửi yêu cầu đặt lịch hợp lệ
    Then hệ thống tạo một lịch hẹn
    And khách thấy xác nhận cùng mã lịch hẹn

  Scenario: Khách gửi lại cùng một yêu cầu sau khi mạng timeout
    Given yêu cầu đầu đã được hệ thống ghi nhận
    When khách gửi lại cùng yêu cầu theo cơ chế đã thiết kế
    Then hệ thống không tạo lịch hẹn thứ hai
    And khách nhận kết quả cuối cùng có thể hiểu được

  Scenario: Khung giờ không còn trống
    Given khung giờ đã được khách khác đặt
    When khách cố xác nhận khung giờ đó
    Then hệ thống không tạo lịch trùng
    And khách được hướng dẫn chọn khung giờ khác
~~~

Các tiêu chí trên là ví dụ; nhóm còn phải làm rõ timeout thực tế, quyền xem mã lịch, cạnh tranh đồng thời, múi giờ, bảo vệ dữ liệu và trường hợp kết quả chưa xác định. Spike giúp nhóm **biết cần hỏi và kiểm thử điều gì**, không thay thế thiết kế chi tiết và kiểm thử production.

### 9.2. Kết quả khảo sát có thể là “không làm”

Nếu thử nghiệm cho thấy tính năng đề xuất không giải quyết nhu cầu đáng kể hoặc có chi phí vận hành vượt lợi ích, Product Owner có thể quyết định không ưu tiên. Đây cũng là một kết quả có giá trị: nhóm tránh làm, triển khai và bảo trì phần mềm ít ích lợi. Cần ghi lý do và điều kiện có thể khiến quyết định thay đổi trong tương lai.

### 9.3. Ghi kết quả ngắn, dễ truy vết

Mẫu báo cáo spike sau khi kết thúc:

~~~text
ID / chủ đề           : SPIKE-17 — Kiểm chứng khả năng chống lịch trùng
Quyết định cần hỗ trợ : Chọn cơ chế retry khi API đối tác timeout
Timebox đã dùng       : 1 ngày
Giả định ban đầu      : API có idempotency key
Phương pháp           : Hợp đồng API + 4 kịch bản thử trong sandbox
Quan sát có bằng chứng: ...
Giới hạn thử nghiệm   : Sandbox, tải nhỏ, chưa phản ánh toàn bộ production
Kết luận              : Ủng hộ / bác bỏ / chưa đủ bằng chứng cho từng giả định
Phương án đề xuất     : ...
Rủi ro còn lại        : ...
Người quyết định      : ...
Thay đổi backlog      : Story A, kiểm thử B, loại bỏ phương án C
Điều kiện xem lại     : Khi nhận được xác nhận từ đối tác hoặc kết quả rollout
~~~

Lưu nguồn và cách tái hiện đủ để người khác có thể kiểm tra lập luận. Không cần biến mỗi spike thành tài liệu dài hàng chục trang nếu một bảng quyết định và demo ngắn đã đủ.

## 10. Tổ chức công việc khảo sát trong Scrum, Kanban và XP

### 10.1. Scrum: khảo sát phục vụ mục tiêu và Increment

Trong Scrum, Product Backlog là một danh sách công việc có thứ tự và được làm rõ khi có thêm hiểu biết. Product Owner chịu trách nhiệm tối đa hóa giá trị và quản lý hiệu quả backlog; Developers lập kế hoạch thực hiện để đạt Sprint Goal. Một công việc khảo sát có thể được cân nhắc trong Product Backlog hoặc Sprint Backlog khi nó **giảm bất định cần thiết để đạt mục tiêu**.

Ví dụ:

- Trong **refinement**, nhóm nhận ra chưa rõ API có hỗ trợ giữ chỗ. Họ định nghĩa một spike ngắn để đưa ra quyết định triển khai.
- Ở **Sprint Planning**, Scrum Team xem công việc khảo sát có phục vụ Sprint Goal không; nếu cần, Developers đưa nó vào kế hoạch.
- Trong Sprint, nhóm thực hiện spike, trao đổi phát hiện với Product Owner và điều chỉnh phương án khi có bằng chứng mới mà không làm giảm chất lượng.
- Ở **Sprint Review**, nhóm thảo luận với bên liên quan về Increment, thay đổi thị trường và kết quả học được để thích ứng backlog.
- Ở **Retrospective**, nhóm xem cách khảo sát có đang kéo dài, phụ thuộc nhiều người hoặc tạo điểm chờ không và thử cải tiến.

**Điểm phân biệt:** Scrum không có một artifact chính thức tên “spike” và không yêu cầu mỗi spike tạo một Increment. Nếu chưa có một phần sản phẩm đạt Definition of Done, báo cáo nghiên cứu không nên được trình bày như tính năng Done. Tùy mục tiêu, khảo sát có thể được thực hiện ngoài Sprint hoặc song song với delivery; phải quản lý minh bạch năng lực đã dùng.

### 10.2. Kanban: làm hiện rõ công việc khám phá và giới hạn WIP

Nhóm vận hành theo dòng công việc có thể trực quan hóa các mục khảo sát giống những hạng mục khác, đồng thời dùng chính sách phù hợp:

~~~text
Ý tưởng / giả định -> Cần khảo sát -> Khảo sát [WIP: 1] -> Quyết định -> Sẵn sàng delivery
                                                    |               |
                                                 Bị chặn?       Bằng chứng / rủi ro?
~~~

Giới hạn WIP “1” là ví dụ, không phải quy tắc. Nếu mọi người bắt đầu nhiều spike mà không kết thúc, nhóm có thể tích lũy hàng đợi nghiên cứu giống như hàng đợi code. Kanban giúp:

- Xác định chính sách khi nào đưa một giả định vào khảo sát.
- Giới hạn số khảo sát đang xử lý để bảo vệ khả năng hoàn tất.
- Làm rõ điểm chặn như “đang chờ đối tác xác nhận” thay vì kéo dài im lặng.
- Đo **cycle time** từ bắt đầu đến khi kết thúc khảo sát theo định nghĩa thống nhất.
- Xem bao nhiêu kết quả khảo sát dẫn tới quyết định, thay vì chỉ đếm số trang báo cáo.

Một spike có thể kết thúc với quyết định **không triển khai**; đó là thành công về giảm rủi ro, không nhất thiết là thất bại về throughput.

### 10.3. XP: spike kỹ thuật nhỏ để học và giữ chất lượng

Trong Extreme Programming, spike solution giúp thử một rủi ro kỹ thuật theo cách nhỏ nhất. Các thực hành XP khác hỗ trợ chuyển kiến thức thành delivery:

- **Test-driven development (TDD):** Biến trường hợp hành vi mới học được thành kiểm thử trước khi triển khai chính thức.
- **Continuous integration:** Tích hợp thường xuyên, phát hiện bất tương thích và lỗi hồi quy sớm.
- **Pair programming:** Cùng quan sát kết quả thí nghiệm và chia sẻ hiểu biết về thiết kế.
- **Refactoring:** Giữ cấu trúc có thể thay đổi khi giả định mới được kiểm chứng.
- **Thiết kế đơn giản:** Không xây kiến trúc bao quát nhu cầu tưởng tượng chỉ vì spike chưa thể loại bỏ mọi bất định.

**Mã trong spike có thể là mã bỏ đi.** Nếu nó chưa đáp ứng yêu cầu kiểm thử, bảo mật, chất lượng, giấy phép thư viện và vận hành, không nên sao chép thẳng vào production chỉ vì “đã chạy được”.

## 11. Ước lượng, timebox và các chỉ số cần theo dõi

Một timebox nên đủ ngắn để nhóm có thể ra quyết định lại khi chưa chắc chắn, nhưng đủ để tiến hành phép thử có ý nghĩa. Không có “spike chuẩn luôn hai ngày” hoặc “tối đa tám story point”. Các giới hạn phụ thuộc mức rủi ro, phương pháp, khả năng tiếp cận dữ liệu và giá trị của câu trả lời.

### 11.1. Phân biệt chỉ số khảo sát và chỉ số delivery

| Cần hiểu | Chỉ số hoặc tín hiệu | Cách sử dụng |
| --- | --- | --- |
| Khảo sát có giúp quyết định không? | Tỷ lệ hạng mục có kết luận/đề xuất hành động rõ; quyết định được cập nhật vào backlog. | Xem đầu ra có được sử dụng, không chỉ được tạo ra. |
| Đang tắc ở đâu? | Thời gian chờ chuyên gia/đối tác, WIP, cycle time của spike. | Thấy phụ thuộc và cải tiến đường thu thập bằng chứng. |
| Dự báo có tốt hơn? | Những bất định lớn được phát hiện trước khi cam kết; số lần phải làm lại vì giả định sai. | Xem xu hướng qua nhiều trường hợp, tránh quy hết nguyên nhân cho một spike. |
| Sản phẩm có đem lại giá trị? | Tỷ lệ hoàn tất tác vụ, sử dụng tính năng, phản hồi khách hàng. | Cần kiểm chứng sau delivery, không suy ra từ báo cáo spike. |
| Chất lượng có được bảo vệ? | Lỗi hồi quy, tỷ lệ lỗi, độ trễ, sự cố, thời gian phục hồi. | Làm chỉ số bảo vệ khi thử giải pháp mới. |

**Không tối ưu số spike hoàn tất.** Nếu nhóm được thưởng vì số lượng báo cáo nghiên cứu, họ có thể tạo những câu hỏi vụn vặt không ảnh hưởng quyết định. Nếu bị phạt vì một giả thuyết bị bác bỏ, họ sẽ có động cơ che bằng chứng xấu.

### 11.2. Khi nào dừng hoặc gia hạn?

Một spike có thể kết thúc trước timebox khi đã có đủ bằng chứng. Đến cuối timebox, nhóm nên chọn một trong các kết quả:

1. **Ra quyết định với bằng chứng hiện có:** Chọn phương án, triển khai có kiểm soát.
2. **Bác bỏ giả định và đổi hướng:** Loại hoặc thay thứ tự backlog, tránh tiếp tục đầu tư sai.
3. **Chưa đủ bằng chứng nhưng rủi ro chấp nhận được:** Thử lát cắt nhỏ hơn, giám sát chặt và điều chỉnh khi có tín hiệu.
4. **Chưa đủ bằng chứng và rủi ro cao:** Không cam kết phương án lớn; trình bày phụ thuộc, đề xuất khảo sát tiếp có câu hỏi và timebox mới.
5. **Không còn giá trị khảo sát:** Dừng hạng mục, ghi lý do và điều kiện mở lại.

Gia hạn không phải mặc định; người chịu trách nhiệm ưu tiên cần cân nhắc chi phí cơ hội của việc chậm giao giá trị khác.

## 12. Các sai lầm thường gặp và cách sửa

| Sai lầm | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| “Nghiên cứu thêm công nghệ X” mà không có câu hỏi quyết định. | Không biết khi nào hoàn tất. | Viết quyết định bị chặn, giả định và câu hỏi có thể kiểm chứng. |
| Đặt timebox nhưng cứ kéo dài khi hết thời gian. | Chi phí khảo sát mất kiểm soát, backlog không tiến. | Dừng, tổng hợp bằng chứng, quyết định có cấp một timebox mới hay không. |
| Coi một demo chạy được là chứng minh phương án an toàn ở production. | Lỗi bảo mật, tải, dữ liệu hoặc khả năng vận hành bị phát hiện muộn. | Nêu điều kiện môi trường, giới hạn bằng chứng, kiểm thử và rollout phù hợp. |
| Dùng mẫu phỏng vấn ít người để tuyên bố tỷ lệ chính xác của cả thị trường. | Quyết định dựa trên suy luận vượt quá dữ liệu. | Dùng quan sát định tính để tìm vấn đề, dùng phép đo phù hợp để ước lượng quy mô. |
| Nghiên cứu mọi rủi ro trước khi giao phần nhỏ. | Chậm học từ thực tế và trì hoãn giá trị. | Ưu tiên giả định ảnh hưởng lớn; giao lát cắt an toàn để học liên tục. |
| Ghi kết quả nhưng backlog vẫn không đổi. | Khảo sát không tạo tác động quyết định. | Kết thúc bằng quyết định, hạng mục hành động và người chịu trách nhiệm. |
| Đẩy mọi việc khó ước lượng thành spike. | Che vấn đề refinement và thiếu năng lực chia nhỏ story. | Làm rõ yêu cầu, dùng spike khi có bất định cụ thể không giải quyết bằng trao đổi thường. |
| Đưa mã prototype vào production ngay. | Mang theo thiếu sót về kiểm thử, an toàn và bảo trì. | Đánh giá lại, tái triển khai hoặc hoàn thiện mã theo DoD và tiêu chuẩn hệ thống. |
| Không phân biệt sự thật với giả thuyết. | Nhóm “chứng minh” điều vốn đã tin bằng dữ liệu chọn lọc. | Ghi nguồn, điều kiện thử, giả thuyết thay thế và bằng chứng bất lợi. |
| Dùng số story point của spike để coi đó là giá trị người dùng đã giao. | Báo cáo tiến độ bị đánh đồng với Increment. | Tách kết quả học hỏi và Increment sản phẩm, nêu rõ rủi ro còn lại. |

## 13. Tình huống thực hành

### Tình huống A — Chọn cơ sở dữ liệu mới

Nhóm muốn chuyển toàn bộ dữ liệu đơn hàng sang một hệ quản trị khác vì có nhận định “nó sẽ nhanh hơn”. Hiện chưa có benchmark trên truy vấn và dữ liệu điển hình; việc chuyển đổi khó đảo ngược.

**Câu hỏi:**

1. Giả định nào cần tách khỏi dữ kiện đã biết?
2. Quyết định nào đang bị chặn và hậu quả nếu sai là gì?
3. Thiết kế một spike có giới hạn gồm những phép thử nào?
4. Kết luận nào đủ để quyết định thử chuyển một thành phần nhỏ thay vì toàn bộ hệ thống?

**Hướng xử lý:** Xác định truy vấn nghẽn thực tế, đo baseline và chỉ số mục tiêu; thử trên dữ liệu đại diện đã xử lý an toàn, cùng cấu hình có thể so sánh; xem chi phí vận hành, di chuyển, tương thích và khả năng rollback. Kết luận nên có độ trễ, tài nguyên, phạm vi thử, điểm chưa rõ và phương án thử giới hạn trước khi đổi toàn bộ.

### Tình huống B — Nhóm được yêu cầu “thêm AI vào sản phẩm”

Một bên liên quan muốn đưa AI vào hệ thống hỗ trợ để giảm nhân công, nhưng chưa biết câu hỏi nào lặp lại nhiều nhất và độ chính xác chấp nhận được.

**Câu hỏi:**

1. Đâu là giả định giá trị, kỹ thuật và vận hành?
2. Khảo sát nào nên làm trước khi tích hợp mô hình?
3. Dữ liệu và quyền riêng tư cần bảo vệ thế nào?
4. Kết quả “một trang tra cứu có ích hơn chatbot” có phải thất bại không?

**Hướng xử lý:** Xem chủ đề hỗ trợ lặp lại và nhu cầu người dùng, sau đó thử một phương án đơn giản cùng một phương án AI với bộ tình huống kiểm tra có dữ liệu được phép dùng. Đánh giá chất lượng câu trả lời, chuyển tuyến khi không chắc chắn, chi phí và rủi ro riêng tư. Quyết định không dùng AI nếu không tạo giá trị tốt hơn là kết quả có ích.

### Tình huống C — Spike hết hạn nhưng đối tác chưa phản hồi

Nhóm đã dành hai ngày để xác minh giới hạn API, nhưng đối tác chưa cung cấp thông tin về quota. Một thành viên đề xuất kéo dài spike vô thời hạn, người khác đề nghị tự xây giả lập rồi coi như quota không giới hạn.

**Câu hỏi:**

1. Việc nào đã có bằng chứng và việc nào chưa?
2. Những lựa chọn nào hợp lệ khi đến cuối timebox?
3. Khi nào có thể tiếp tục bằng thiết kế dự phòng, khi nào phải dừng cam kết?

**Hướng xử lý:** Kết thúc timebox, ghi rõ phụ thuộc chưa được giải quyết. Có thể thử thiết kế giảm tải, giới hạn yêu cầu hoặc lập phương án dự phòng, nhưng không suy ra quota thật từ giả lập. Cập nhật rủi ro vào backlog, phân công liên hệ đối tác và quyết định có khảo sát tiếp dựa trên tác động nếu sai.

### Bài tập nhóm — Viết một spike brief

Chọn một yêu cầu còn mơ hồ trong dự án của bạn và điền:

| Câu hỏi | Câu trả lời |
| --- | --- |
| Quyết định đang bị chặn là gì? | ... |
| Giả định nào chưa đủ bằng chứng? | ... |
| Nếu giả định sai, hậu quả và khả năng đảo ngược thế nào? | ... |
| Câu hỏi nhỏ nhất có thể kiểm chứng? | ... |
| Phương pháp, nguồn dữ liệu, người cần tham gia? | ... |
| Timebox và giới hạn phạm vi? | ... |
| Tiêu chí dừng và điều kiện cần thử tiếp? | ... |
| Các kết quả có thể dẫn tới quyết định nào? | ... |
| Cần thay đổi user story, backlog hoặc kiểm thử ra sao? | ... |

Trao đổi brief với Product Owner, Developers, người hiểu nghiệp vụ hoặc chuyên gia phù hợp. Nếu người khác không thể nói được **spike này giúp quyết định việc gì**, cần viết lại trước khi bắt đầu.

## 14. Checklist trước và sau khảo sát

### Trước khi bắt đầu

- [ ] Giả định được ghi riêng với sự thật đã có bằng chứng.
- [ ] Có một quyết định cụ thể chịu ảnh hưởng của giả định.
- [ ] Bất định và hậu quả nếu sai đủ lớn để đáng đầu tư khảo sát.
- [ ] Có câu hỏi hẹp, phạm vi rõ, người thực hiện và timebox.
- [ ] Đã chọn phương pháp khớp với loại giả định cần kiểm chứng.
- [ ] Có tiêu chí dừng, cách báo cáo khi chưa đủ bằng chứng và ràng buộc an toàn.
- [ ] Biết ai có quyền ra quyết định sau khi nhận kết quả.

### Khi kết thúc

- [ ] Đã dừng và trình bày kết quả ở mốc timebox, kể cả khi chưa có câu trả lời hoàn chỉnh.
- [ ] Quan sát, cách diễn giải, điều kiện thử và giới hạn bằng chứng được tách rõ.
- [ ] Đã so sánh các phương án với giá trị, chi phí, rủi ro và khả năng đảo ngược.
- [ ] Có quyết định hoặc bước học tiếp theo được cấp phạm vi rõ.
- [ ] User story, backlog, tiêu chí chấp nhận, kiểm thử hoặc kế hoạch đã được cập nhật.
- [ ] Không coi prototype chưa đạt DoD là Increment production.
- [ ] Có tín hiệu theo dõi sau delivery để xác nhận lựa chọn trong thực tế.

## 15. Ghi nhớ cốt lõi

Yêu cầu thích ứng bắt đầu bằng việc **thừa nhận điều nhóm chưa biết**. Spike/timebox là một phương tiện nhỏ để đưa giả định quan trọng ra kiểm chứng trước khi cam kết lớn. Một spike tốt có **quyết định cần hỗ trợ, một câu hỏi hẹp, phương pháp phù hợp, giới hạn rõ, bằng chứng có nguồn và kết luận có thể hành động**.

Trong Scrum, khảo sát giúp làm rõ Product Backlog và kế hoạch tạo Increment; trong Kanban, nó cần được nhìn thấy trong luồng và giới hạn WIP; trong XP, spike kỹ thuật giúp kiểm chứng một rủi ro trước khi triển khai bền vững. Dù dùng cách phối hợp nào, **giá trị cuối cùng của khảo sát nằm ở quyết định tốt hơn và phần mềm có ích được giao an toàn**, chứ không nằm ở số giờ nghiên cứu hoặc số báo cáo hoàn thành.

### Tài liệu nên đọc tiếp

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — ưu tiên phản hồi, phần mềm hoạt động được và đáp ứng thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — giao thường xuyên, chào đón thay đổi, cải tiến kỹ thuật và đơn giản.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Product Backlog, Sprint Goal, Increment, Definition of Done và kiểm tra/thích ứng.
- [The Kanban Guide](https://kanbanguides.org/) — quản lý dòng công việc, WIP và các chỉ số dòng.
- [Agile Alliance: Spike](https://agilealliance.org/glossary/spike/) — tham khảo thuật ngữ spike trong thực hành Agile.
