# Liên kết tự chủ của nhóm với mục tiêu và trách nhiệm giải trình

## 1. Tự chủ để giao giá trị, không phải tự quyết mọi thứ

Một Scrum Team xây dựng nền tảng học trực tuyến được giao mục tiêu **giúp học viên quay lại học dễ dàng hơn**. Product Owner tin tưởng Developers tự thiết kế giải pháp. Một nhóm đề xuất làm hệ thống gợi ý bài học dựa trên trí tuệ nhân tạo, nhóm khác muốn sửa nút “Tiếp tục học”, còn người phụ trách bảo mật cảnh báo việc sử dụng dữ liệu tiến độ có thể vượt phạm vi cho phép.

Mọi người đều nói mình đang thực hiện Agile, nhưng ba câu hỏi chưa được trả lời:

1. **Kết quả nào thật sự quan trọng đối với học viên?** Là tìm được bài tiếp theo, mở bài đúng quyền hay sử dụng gợi ý thông minh?
2. **Nhóm được tự quyết trong những giới hạn nào?** Có được thay đổi cách dùng dữ liệu cá nhân, ngân sách và hợp đồng API?
3. **Ai giải trình về kết quả và rủi ro?** Ai xác nhận mục tiêu sản phẩm, ai bảo vệ Definition of Done, ai xử lý khi thử nghiệm gây lỗi?

Nếu thiếu các câu trả lời, “tự chủ” có thể biến thành mỗi người tự chọn việc mình thích; “quản trị” có thể biến thành mọi thay đổi đều chờ phê duyệt. Cả hai cực đoan đều làm phản hồi chậm, giảm chất lượng và khiến việc phát triển tăng dần khó thực hiện.

Trong phạm vi **AGILE_DEVELOPMENT**, tự chủ có ý nghĩa khi nhóm **hiểu mục tiêu, được quyền chọn cách đạt mục tiêu trong ranh giới rõ ràng và chịu trách nhiệm minh bạch về chất lượng, kết quả và điều học được**. Đây là cách kết nối các giá trị Agile với user story, Product Backlog, Scrum, Kanban, XP, đo lường luồng và cải tiến liên tục.

> **Nguyên tắc cốt lõi:** Trao cho nhóm **quyền quyết định gần nơi có thông tin nhất**, đồng thời giữ **mục tiêu chung, giới hạn không thể vượt và cơ chế kiểm tra kết quả** rõ ràng.

Một nhóm có tự chủ thực chất không phải nhóm được phép bỏ qua bảo mật, luật hoặc thỏa thuận với người dùng. Đó là nhóm **không cần xin phép cho từng quyết định kỹ thuật nhỏ**, nhưng **biết khi nào phải tham vấn, cung cấp bằng chứng hoặc dừng để xử lý rủi ro**.

## 2. Phân biệt tự chủ, quyền hạn, trách nhiệm và trách nhiệm giải trình

Những từ này thường được dùng lẫn nhau, đặc biệt khi công việc trải qua nhiều nhóm.

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Autonomy – tự chủ** | Trong phạm vi nào nhóm có thể lựa chọn cách làm? | Developers tự chọn chia lát, thiết kế code và chiến lược test để đạt Sprint Goal |
| **Authority – thẩm quyền** | Ai được phép ra quyết định cụ thể? | Product Owner quyết định thứ tự Product Backlog; người có thẩm quyền bảo mật chấp thuận ngoại lệ chính sách |
| **Responsibility – trách nhiệm thực hiện** | Ai sẽ làm việc hoặc phối hợp thực hiện? | Developers triển khai, kiểm thử và tích hợp tính năng |
| **Accountability – trách nhiệm giải trình** | Ai phải làm rõ kết quả, quyết định và cách xử lý khi không đạt? | Product Owner giải trình về việc quản lý Product Backlog hiệu quả; Developers chịu trách nhiệm về Increment đạt DoD |
| **Transparency – minh bạch** | Người liên quan nhìn thấy mục tiêu, quyết định và bằng chứng không? | Có Sprint Goal, bản ghi quyết định, tiêu chí chấp nhận và tín hiệu kết quả |
| **Governance – quản trị** | Cơ chế nào định hướng, đặt ranh giới và giám sát rủi ro? | Chính sách dữ liệu, ngân sách, DoD, quyền quyết định và quy trình xử lý ngoại lệ |

### Một người có thể thực hiện công việc nhưng không có quyền đổi chính sách

Developer được giao xây API ghi danh có thể **tự chọn cấu trúc service**, nhưng không thể tự đổi quy tắc “khóa cần duyệt chỉ cấp quyền sau khi ACTIVE” thành “gửi yêu cầu là được học ngay”. Đó là **quyết định nghiệp vụ và quyền truy cập** cần xác nhận bởi người có thẩm quyền.

Ngược lại, Product Owner có trách nhiệm làm rõ giá trị, không nên vì vậy yêu cầu Developers dùng một design pattern hay một thư viện cụ thể khi quyết định kỹ thuật nằm trong phạm vi tự quản của họ.

### Accountability không phải tìm người để đổ lỗi

Một lỗi production có thể liên quan yêu cầu mơ hồ, mã sai, test thiếu và quy trình release. **Trách nhiệm giải trình** là khả năng giải thích **điều gì đã được quyết định, bằng chứng nào đã có, tác động ra sao và nhóm sẽ làm gì tiếp theo**. Việc tìm nguyên nhân hệ thống và sửa lỗi không loại bỏ trách nhiệm của từng vai trò, nhưng khác với công kích cá nhân.

### Tự chủ cũng không đồng nghĩa làm việc một mình

Nhóm tự quản vẫn cần phối hợp với người dùng, Product Owner, các nhóm API, vận hành và người có chuyên môn. Tự chủ tốt thường **tăng chất lượng trao đổi ngang hàng**, không biến từng người thành một “ốc đảo” không ai hiểu lựa chọn của nhau.

## 3. Mô hình ba yếu tố: mục tiêu – ranh giới – quyền quyết định

Một cách thiết kế tự chủ là làm rõ ba thành phần trước khi giao một bài toán:

1. **Mục tiêu (direction):** người dùng cần đạt điều gì và vì sao điều đó có giá trị?
2. **Ranh giới (guardrails):** chất lượng tối thiểu, an toàn, dữ liệu, ngân sách, thời gian và cam kết nào phải được bảo vệ?
3. **Quyền quyết định (decision rights):** trong ranh giới ấy, nhóm tự quyết gì, khi nào cần tham vấn và khi nào cần người khác chấp thuận?

~~~mermaid
flowchart TD
    A["Mục tiêu sản phẩm và giá trị người dùng"] --> B["Nhóm hiểu vấn đề + kết quả mong muốn"]
    C["Guardrails: DoD, bảo mật, dữ liệu, ngân sách, chất lượng"] --> B
    D["Quyền quyết định, quyền tham vấn và escalation"] --> B
    B --> E["Nhóm tự chọn lát giá trị, thiết kế và cách làm"]
    E --> F["Increment có thể dùng + dữ liệu thực nghiệm"]
    F --> G["Minh bạch: outcome, flow, chất lượng, rủi ro"]
    G --> H["Kiểm tra với PO / stakeholder và thích ứng"]
    H --> A
    H -. "Cập nhật giới hạn khi có căn cứ" .-> C
~~~

Nếu chỉ có mục tiêu mà không có guardrail, nhóm có thể **giao nhanh nhưng cấp quyền sai**. Nếu chỉ có guardrail mà không trao quyền, nhóm phải xin duyệt từng thay đổi nhỏ. Nếu có quyền nhưng không có mục tiêu, nhóm có thể **tối ưu những chỉ số kỹ thuật không tạo giá trị**.

### Ví dụ một thỏa thuận ngắn

> **Mục tiêu:** học viên đủ điều kiện tìm và mở đúng bài tiếp theo nhanh hơn.
>
> **Không được đánh đổi:** phân quyền nội dung, tính toàn vẹn tiến độ, dữ liệu cá nhân, Definition of Done và khả năng khôi phục khi release.
>
> **Nhóm tự quyết:** chia user story, cách tổ chức mã, kiểm thử, trình tự làm việc, đề xuất thử nghiệm giao diện trong phạm vi được đồng ý.
>
> **Cần tham vấn hoặc phê duyệt:** thay đổi quy tắc ghi danh, dùng dữ liệu cho mục đích mới, hợp đồng API tác động tới bên ngoài, vượt ngân sách hoặc thay đổi chính sách an toàn.
>
> **Bằng chứng:** acceptance tests, dữ liệu mở bài thành công, phản hồi học viên, lỗi và khả năng khôi phục.

Đây là ví dụ **thiết kế ranh giới**, không phải một mô hình thẩm quyền bắt buộc cho mọi tổ chức. Phân quyền thực tế phải theo cơ cấu, hợp đồng và nghĩa vụ của đơn vị.

## 4. Liên kết mục tiêu tổ chức, Product Goal và Sprint Goal

Tự chủ không thể vận hành nếu công việc hằng ngày mất kết nối với vấn đề cần giải quyết. Cần làm rõ **vì sao** một Sprint hoặc user story xứng đáng được thực hiện.

### Các lớp mục tiêu hỗ trợ nhau

| Cấp/thành phần | Câu hỏi | Ví dụ nền tảng học |
| --- | --- | --- |
| **Định hướng chiến lược** | Tổ chức đang cố tạo giá trị bền vững gì? | Giúp người học hoàn thành khóa với trải nghiệm đáng tin |
| **Product Goal** | Trạng thái tương lai nào của sản phẩm cần đạt? | Người học có thể tiếp tục khóa xuyên thiết bị với tiến độ nhất quán |
| **Outcome/KPI có ngữ cảnh** | Có dấu hiệu nào cho thấy người dùng đạt lợi ích? | Tỷ lệ học viên quay lại và mở đúng bài tiếp theo |
| **Sprint Goal** | Vì sao Sprint hiện tại có giá trị thống nhất? | Học viên khóa tuyến tính đủ điều kiện có thể dùng “Tiếp tục học” an toàn |
| **Product Backlog Items** | Những lát giá trị nào giúp tiến về mục tiêu? | Xác định bài tiếp theo, điều hướng, kiểm tra quyền, đồng bộ |
| **Definition of Done** | Chất lượng chung để Increment được coi là hoàn tất? | Đã tích hợp, test phù hợp, không có lỗi chặn theo chính sách |
| **Phản hồi thực tế** | Giả thuyết sản phẩm có đúng không? | Quan sát hành trình, lỗi, hỗ trợ và tỷ lệ sử dụng |

Trong Scrum, **Product Goal là commitment của Product Backlog; Sprint Goal là commitment của Sprint Backlog; Definition of Done là commitment của Increment**. Chúng giúp duy trì minh bạch và tập trung vào kết quả thay vì chỉ đếm task.

### Đây không phải chuỗi mệnh lệnh cứng

Không nhất thiết mọi tổ chức phải dùng OKR hoặc phân rã một mục tiêu cấp công ty thành hàng chục KPI cá nhân. **Mục tiêu nên kết nối được bằng lý do**, nhưng nhóm vẫn có quyền phản hồi rằng một hướng đi không khả thi, thiếu bằng chứng hoặc có rủi ro.

Ví dụ, Product Goal muốn học viên quay lại thường xuyên hơn. Developers có thể chỉ ra vấn đề không nằm ở thiếu thông báo, mà ở việc **đường dẫn tiếp tục học đôi khi sai tiến độ**. Bằng chứng đó có thể khiến Product Owner ưu tiên chất lượng và đồng bộ trước một chiến dịch nhắc học.

### Mục tiêu tốt mô tả kết quả, không ép giải pháp

- Thiên về giải pháp: “Trong Sprint này phải viết hệ thống gợi ý AI”.
- Thiên về outcome: “Học viên đủ điều kiện tìm đúng bài tiếp theo mà không cần hỗ trợ”.
- Thiên về Sprint Goal có phạm vi: “Trong Sprint này, giao được hành trình tiếp tục học đúng quyền cho khóa tuyến tính và đủ bằng chứng để thử với cohort nhỏ”.

Mức outcome cho phép nhóm **tự khám phá giải pháp** và thay đổi hướng khi phản hồi cho thấy một phương án đơn giản hơn hiệu quả hơn.

## 5. Tự quản trong Scrum và những accountability không thể bỏ qua

Scrum Team là **self-managing**: các thành viên cùng quyết định nội bộ **ai làm gì, khi nào và như thế nào** để tạo giá trị. Điều đó không làm các accountability của Scrum biến mất.

| Accountability | Trách nhiệm cốt lõi | Liên quan tới tự chủ và giải trình |
| --- | --- | --- |
| **Product Owner** | Tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả | Làm rõ Product Goal, Product Backlog Items, thứ tự và quyết định sản phẩm trong phạm vi thẩm quyền |
| **Developers** | Tạo kế hoạch cho Sprint, thích ứng hằng ngày, tuân thủ DoD và chịu trách nhiệm chuyên môn với nhau | Tự chọn cách xây Increment, làm rõ phụ thuộc, bảo vệ chất lượng và chủ động nêu rủi ro |
| **Scrum Master** | Thiết lập Scrum như được định nghĩa và giúp Scrum Team/đơn vị tăng hiệu quả | Huấn luyện self-management, hỗ trợ loại bỏ trở ngại, giúp các bên hiểu nhịp kiểm tra và thích ứng |
| **Scrum Team nói chung** | Cộng tác để tạo Increment có giá trị, sử dụng được | Minh bạch về tiến độ, điều đã học và thay đổi cần thiết |

### Những điều không phải Scrum

- Product Owner phân task chi tiết và yêu cầu Developers phải viết mã theo từng bước.
- Scrum Master là “sếp Sprint” có quyền chấm điểm từng người dựa trên velocity.
- Developers tự ý thay Product Goal hoặc phạm vi quyền dữ liệu của người dùng mà không trao đổi.
- Stakeholder dùng Sprint Review như cổng phê duyệt một Increment chưa đáp ứng DoD.
- Mọi quyết định kỹ thuật đều phải được một hội đồng bên ngoài chấp thuận trước khi thử.

### Một điểm tinh tế: ai quyết định Sprint Goal?

Product Owner đề xuất hướng giá trị và bối cảnh; **cả Scrum Team cùng làm rõ Sprint Goal trong Sprint Planning**. Developers lựa chọn các Product Backlog Items phù hợp và lập kế hoạch thực hiện. Khi xuất hiện điều mới trong Sprint, Developers thích ứng Sprint Backlog; nếu phạm vi cần thay đổi, họ trao đổi với Product Owner để **không làm mất Sprint Goal và giá trị đã thống nhất**.

### DoD không phải quyền tùy nghi bỏ qua

Một nhóm có thể tự chọn công cụ và cách kiểm thử, nhưng **không được gọi Increment Done nếu chưa đáp ứng Definition of Done hiện hành**. Nếu tổ chức có tiêu chuẩn chất lượng bắt buộc, DoD của Scrum Team không được thấp hơn tiêu chuẩn ấy. Đây là **ranh giới chất lượng** giúp tự chủ không gây hại cho người dùng.

## 6. Dùng “quyền quyết định” thay vì bảng phê duyệt mọi hành động

Để nhóm tự chủ thực chất, cần trả lời câu hỏi **quyết định nào ở gần người làm, quyết định nào cần người có thẩm quyền khác**. Một ma trận có thể giúp.

### Ví dụ ma trận quyền quyết định cho nền tảng học

| Quyết định | Người/nhóm chủ động | Cần trao đổi với ai? | Trường hợp phải nâng cấp |
| --- | --- | --- | --- |
| **Cách chia user story và phân công nội bộ** | Developers cùng Scrum Team trong Sprint | Product Owner khi ảnh hưởng giá trị/phạm vi | Không thể đáp ứng Sprint Goal hoặc vượt năng lực/ràng buộc |
| **Thiết kế cấu trúc nội bộ, refactor nhỏ** | Developers | Người chịu trách nhiệm thành phần liên quan | Phá hợp đồng công khai hoặc ảnh hưởng kiến trúc chung |
| **Thứ tự Product Backlog** | Product Owner | Stakeholder, Developers, người dùng | Xung đột chiến lược/ngân sách vượt thẩm quyền PO |
| **Tiêu chí hành vi của PBI** | Product Owner xác nhận giá trị; Developers cùng làm rõ tính kiểm chứng | Nghiệp vụ, tester, hỗ trợ | Quy tắc liên quan hợp đồng/pháp lý chưa được chốt |
| **Phân quyền truy cập học viên** | Người phụ trách chính sách nghiệp vụ và kỹ thuật theo quy định | PO, security/privacy, Developers | Nguy cơ lộ dữ liệu hoặc thay đổi chính sách bắt buộc |
| **Thay đổi API liên nhóm** | Developers bên cung cấp/tiêu thụ phối hợp | Những bên đang phụ thuộc | Phá tương thích hoặc làm sai cam kết dịch vụ |
| **Bật feature flag trong cohort đã được phê duyệt** | Nhóm được giao quyền vận hành | PO, vận hành, người theo dõi chất lượng | Tín hiệu guardrail xấu hoặc mở rộng ngoài phạm vi cho phép |
| **Vượt ngân sách/hợp đồng với bên thứ ba** | Người có thẩm quyền tài chính/hợp đồng | PO, nhóm kỹ thuật đề xuất | Không có quyền tự phê duyệt từ nhóm delivery |
| **Ứng phó incident nghiêm trọng** | Người/nhóm trực theo quy trình sự cố | Bảo mật, vận hành, chủ sản phẩm tùy mức độ | Khi vượt ngưỡng ứng phó hoặc có nghĩa vụ báo cáo |
| **Thay đổi tiêu chuẩn DoD bắt buộc** | Các bên có thẩm quyền chất lượng và Scrum Team theo cơ chế tổ chức | Security, compliance, Developers | Không được hạ dưới chuẩn tổ chức bắt buộc |

**Ma trận trên là minh họa**, không phải mẫu quyền quyết định pháp lý hay cấu trúc tổ chức bắt buộc. Tại mỗi đơn vị cần biết **ai thật sự có quyền ký, chấp thuận ngoại lệ và chịu trách nhiệm về dữ liệu/chi phí**.

### Tránh dùng RACI như cách thay thế Scrum accountability

RACI hoặc DACI có thể giúp làm rõ người quyết định/tham vấn ở công việc liên nhóm, nhưng chúng **không tự thay đổi** các accountability của Scrum. Ví dụ, gọi một kiến trúc sư là “Accountable” cho một task trong RACI không có nghĩa Product Owner mất accountability về Product Backlog hoặc Developers không còn chịu trách nhiệm tạo Increment chất lượng.

### Không chỉ định hai người “quyết cuối” cho cùng một vấn đề

Nếu Product Owner nói chỉ PO được chọn cấu trúc database còn một architect nói chỉ architect được chọn mọi tiêu chí sản phẩm, cơ chế đang chồng chéo. Hãy tách **quy tắc nghiệp vụ, tiêu chuẩn kỹ thuật bắt buộc và giải pháp triển khai**; xác định rõ người có thẩm quyền ở từng phạm vi.

## 7. Mức trao quyền thay đổi theo rủi ro và khả năng đảo ngược

Không phải quyết định nào cũng cần cùng mức giám sát. Một thay đổi nội bộ dễ đảo ngược khác xa migration xóa dữ liệu hoặc công bố thông tin học viên cho bên thứ ba.

### Năm mức trao quyền minh họa

1. **Làm theo chính sách đã định:** nhóm thực hiện một quy tắc bắt buộc, không tự đổi phạm vi; phản hồi nếu chính sách cản trở.
2. **Đề xuất để được chốt:** nhóm đưa phương án và bằng chứng, người có thẩm quyền phê duyệt.
3. **Quyết định sau tham vấn:** nhóm chịu trách nhiệm quyết định nhưng phải lấy ý kiến của các bên liên quan trước.
4. **Quyết định rồi thông báo:** nhóm tự quyết trong ranh giới, ghi lại điều có tác động để người khác theo kịp.
5. **Tự quyết trong phạm vi nhỏ:** nhóm thực hiện thay đổi có rủi ro thấp, không tạo phê duyệt thừa; vẫn kiểm tra chất lượng.

Các mức này chỉ là **khung hội thoại**, không phải một tiêu chuẩn chính thức của Scrum hoặc Kanban. Với mỗi loại quyết định, tổ chức cần gắn mức trao quyền với **rủi ro, độ khó đảo ngược, tác động và năng lực nhóm**.

### Ví dụ phân loại theo tính đảo ngược

| Loại thay đổi | Tính đảo ngược | Gợi ý cơ chế |
| --- | --- | --- |
| Đổi tên biến private, refactor có test | Cao, ảnh hưởng hẹp | Developers tự quyết, CI/review phù hợp |
| Thử hai cách sắp xếp nút trên cohort hợp lệ | Tương đối cao nếu feature flag an toàn | Nhóm đề xuất, PO xác nhận mục tiêu; theo dõi outcome/guardrail |
| Chuyển giao diện API đang có client dùng | Trung bình, cần tương thích | Tham vấn bên tiêu thụ, contract test, migration plan |
| Đổi mục đích xử lý dữ liệu tiến độ cá nhân | Có thể bị ràng buộc pháp lý/hợp đồng | Cần người có thẩm quyền privacy/legal đánh giá |
| Xóa dữ liệu lịch sử bằng migration phá hủy | Khó đảo ngược, tác động lớn | Quy trình thay đổi và phục hồi theo chính sách, không tự quyết tùy hứng |

### “Xin phê duyệt cho an toàn” cũng có chi phí

Nếu mọi lựa chọn kỹ thuật đều qua một quản lý duyệt, người duyệt trở thành hàng đợi. Nhóm mất khả năng phản hồi nhanh, còn quản lý phải xử lý quyết định thiếu ngữ cảnh. Với thay đổi rủi ro thấp, **chính sách và kiểm thử tự động** có thể hữu ích hơn nhiều cấp chữ ký.

## 8. Tạo guardrail rõ: điều không được đánh đổi

Guardrail là **điều kiện bảo vệ** để nhóm có thể thử nghiệm mà không vượt quá rủi ro chấp nhận được. Nó khác với một bản hướng dẫn kỹ thuật quá chi tiết.

### Các nhóm guardrail thường gặp

| Lĩnh vực | Ràng buộc minh họa | Bằng chứng kiểm chứng |
| --- | --- | --- |
| **Giá trị người dùng** | Không làm giảm khả năng hoàn tất hành trình học cốt lõi | Outcome, phản hồi, kiểm thử chấp nhận |
| **Phân quyền/bảo mật** | Người chưa ACTIVE không được truy cập bài hạn chế | API/security integration tests và giám sát |
| **Dữ liệu/quyền riêng tư** | Không dùng tiến độ cho mục đích mới khi chưa có cơ sở và thẩm quyền | Quyết định có dấu vết, kiểm tra yêu cầu dữ liệu |
| **Chất lượng** | Increment phải đạt DoD đã thống nhất | CI, review, kiểm thử hồi quy phù hợp |
| **Độ tin cậy** | Thay đổi không làm vượt ngưỡng vận hành được chấp thuận | SLI/SLO hoặc guardrail có định nghĩa |
| **Hợp đồng hệ thống** | Không phá client/API hiện hữu khi chưa có kế hoạch chuyển đổi | Contract tests, versioning, rollout |
| **Chi phí** | Thử nghiệm trong hạn mức đã được trao quyền | Số liệu sử dụng hạ tầng/ngân sách |
| **Thời hạn bắt buộc** | Có mốc giao theo nghĩa vụ đã được xác nhận | Kế hoạch, phụ thuộc, trao đổi rủi ro sớm |
| **Làm việc bền vững** | Không mặc định giải pháp luôn là làm thêm giờ | WIP, năng lực, phản hồi và chính sách nhân sự |

### Phân biệt guardrail với sở thích

“Không được cấp quyền sai cho học viên” là ranh giới chất lượng. “Phải dùng đúng framework web mà một quản lý thích” **không tự động** là ranh giới bắt buộc; cần bằng chứng về bảo trì, bảo mật, khả năng vận hành hoặc tương thích nếu muốn áp dụng như một chính sách chung.

### Guardrail phải có cách phát hiện vi phạm

“Bảo vệ dữ liệu” là ý định tốt nhưng chưa đủ. Cần hỏi: dữ liệu nào, ai có quyền, thay đổi nào cần phê duyệt, kiểm thử hoặc giám sát nào sẽ phát hiện sai lệch, ai có thể dừng rollout và phản ứng khi có vi phạm?

### Đừng dùng con số tùy ý làm tiêu chuẩn chung

Ví dụ đặt một SLO “99,9% yêu cầu hợp lệ thành công trong 28 ngày” chỉ có ý nghĩa khi **mẫu số, chức năng và mục tiêu phục vụ** đã được xác nhận. Đây không phải ngưỡng mặc định cho mọi dịch vụ học trực tuyến.

## 9. Mục tiêu outcome, output và guardrail không thay thế nhau

Một nhóm có thể hoàn tất nhiều story nhưng không giúp người học. Ngược lại, một chỉ số người dùng tốt có thể xuất hiện trong lúc nhóm **âm thầm tạo rủi ro về dữ liệu**. Vì vậy, một cơ chế accountability trưởng thành xem **kết quả, chất lượng và cách làm** cùng nhau.

### Ví dụ minh họa có mẫu số

Giả sử trong một đợt quan sát ban đầu có **200 học viên đủ điều kiện quay lại học**, trong đó **80 người mở đúng bài tiếp theo thành công**. Tỷ lệ theo định nghĩa là:

~~~text
Tỷ lệ mở đúng bài tiếp theo
  = Số học viên đủ điều kiện quay lại và mở đúng bài
    / Tổng số học viên đủ điều kiện quay lại trong cửa sổ đo
    × 100%

Baseline minh họa = 80 / 200 × 100% = 40%
~~~

Nhóm cân nhắc mục tiêu thử **nâng tỷ lệ lên 50%** trong cohort phù hợp mà không thay đổi quy tắc cấp quyền. Nếu một đợt thử khác có 220 học viên đủ điều kiện và 110 người mở đúng bài, kết quả quan sát là **110/220 = 50%**.

| Loại thông tin | Ví dụ | Điều không thể kết luận |
| --- | --- | --- |
| **Outcome** | Tỷ lệ mở đúng bài tăng từ 40% lên 50% trong hai tập quan sát | Không tự chứng minh một thay đổi gây ra mức tăng |
| **Output** | Giao một nút “Tiếp tục học” và hai API liên quan | Không chứng minh người học sử dụng thành công |
| **Quality guardrail** | Không có trường hợp cấp quyền trái phép được phát hiện; kiểm thử quyền đạt | Không chứng minh mọi rủi ro bảo mật đều đã bị loại |
| **Flow** | Lead time của story cùng loại giảm | Không tự chứng minh giá trị hoặc chất lượng tốt |
| **Học hỏi** | Người dùng báo giảm khó hiểu và nhóm xác nhận một giả thuyết hành vi | Vẫn cần biết cách chọn mẫu và giới hạn quan sát |

**Mức tăng từ 40% lên 50% là 10 điểm phần trăm, tương đương 25% tăng tương đối** so với mức ban đầu. Hai cách diễn đạt khác nhau; báo cáo cần ghi rõ để không làm người đọc hiểu sai.

### Không biến outcome thành KPI cưỡng ép cá nhân

Outcome chịu ảnh hưởng bởi chất lượng sản phẩm, nhu cầu người dùng, mùa học, nguồn nội dung, chiến dịch truyền thông và các thay đổi khác. Một Scrum Team có thể **có accountability về việc chọn thử nghiệm, đo và thích ứng** mà không thể bảo đảm một tỷ lệ chuyển đổi tuyệt đối trong mọi điều kiện.

### OKR có thể hỗ trợ nhưng không phải yêu cầu Agile

Nếu tổ chức dùng Objectives and Key Results, một Objective như “Học viên quay lại học dễ dàng và đáng tin” có thể gắn với Key Results về tỷ lệ mở đúng bài, số trường hợp cần hỗ trợ và lỗi quyền. Nhưng phải tránh dùng **số ticket, story point hoặc velocity** làm đại diện duy nhất cho giá trị.

## 10. Từ mục tiêu tới user story và Increment có thể kiểm chứng

Muốn tự chủ tạo giá trị, nhóm cần **chuyển mục tiêu thành lát công việc nhỏ có thể kiểm tra**, không chỉ nhận một danh sách yêu cầu cố định.

### Ví dụ chia lát tính năng “Tiếp tục học”

| Lát giá trị | User story/khả năng | Ranh giới phạm vi |
| --- | --- | --- |
| **A** | Học viên có quyền mở bài tiếp theo trong khóa tuyến tính | Chưa gồm khóa tự chọn hoặc đồng bộ nhiều thiết bị |
| **B** | Khi hoàn thành bài cuối, hiển thị trạng thái hoàn tất | Chưa gồm chứng chỉ hoặc bài kiểm tra phức tạp |
| **C** | Đồng bộ tiến độ giữa hai phiên theo chính sách đã chốt | Chưa gồm mọi loại thiết bị offline |
| **D** | Người không có quyền không thể mở bài qua đường dẫn/API trực tiếp | Bảo vệ xuyên các lát theo DoD, không để lại lỗ hổng chờ story riêng |
| **E** | Thu phản hồi và quan sát tỷ lệ học viên mở đúng bài | Có bảo vệ dữ liệu và định nghĩa metric |

**Điểm quan trọng:** các kiểm soát quyền bắt buộc không thể bị đẩy hết sang một story sau này nếu lát trước đã cung cấp nội dung bị hạn chế cho người dùng. **Từng Increment phải đáp ứng DoD và điều kiện an toàn tương ứng**.

### Ví dụ user story

> Là học viên đã đăng nhập và có quyền học khóa tuyến tính, tôi muốn chọn “Tiếp tục học” để mở đúng bài chưa hoàn thành tiếp theo mà không phải tự tìm trong danh sách.

Một bộ ví dụ chấp nhận có thể được thống nhất trước khi lập trình:

~~~gherkin
Feature: Tiếp tục học đúng quyền và đúng tiến độ

  Scenario: Học viên mở bài tiếp theo
    Given học viên đã đăng nhập và có quyền học khóa tuyến tính
    And khóa có ba bài theo thứ tự
    And học viên đã hoàn thành bài thứ nhất
    When học viên chọn "Tiếp tục học"
    Then hệ thống mở bài thứ hai

  Scenario: Học viên đã hoàn thành toàn bộ khóa
    Given học viên có quyền học và đã hoàn thành ba bài
    When học viên mở trang khóa
    Then hệ thống hiển thị trạng thái hoàn thành
    And không điều hướng đến bài thứ tư

  Scenario: Người không có quyền thử mở bài trực tiếp
    Given người dùng không có quyền truy cập nội dung khóa
    When người dùng gửi yêu cầu API mở bài bị hạn chế
    Then hệ thống từ chối cấp nội dung bị hạn chế
    And không tiết lộ tiến độ riêng của học viên khác
~~~

### Tại sao ví dụ chấp nhận hỗ trợ tự chủ?

Product Owner xác nhận **hành vi cần đạt**, Developers tự chọn **thiết kế và kiểm thử** phù hợp. Tester/người có tư duy chất lượng cùng hỏi về trường hợp biên. Khi mọi người có chung cách nhận biết thành công, nhóm **không phải xin phép cho từng dòng mã**, nhưng vẫn biết khi nào một thay đổi làm lệch mục tiêu.

### Khi giả thuyết sai, được phép điều chỉnh

Nếu quan sát cho thấy học viên không cần gợi ý AI, chỉ cần nút rõ và dữ liệu tiến độ đúng, nhóm có thể đề nghị đổi thứ tự backlog. **Được phép đề xuất và học** không có nghĩa Developers tự ý đảo Product Backlog mà không trao đổi với Product Owner.

## 11. Quyết định minh bạch: ghi vừa đủ, không biến thành hồ sơ phê duyệt

Tự chủ cần khả năng **giải thích quyết định** cho người không có mặt trong cuộc họp, người trực vận hành hoặc thành viên mới. Không phải mọi rename biến đều cần tài liệu, nhưng quyết định ảnh hưởng hợp đồng, dữ liệu, sản phẩm hoặc bảo mật nên có dấu vết.

### Mẫu Decision Record tối giản

~~~text
ID: DEC-014
Bối cảnh: Học viên có thể mở bài cũ khi đổi thiết bị
Mục tiêu: Đồng bộ tiến độ phù hợp, giữ đúng quyền học
Ràng buộc: DoD, bảo mật, không mất dữ liệu tiến độ, client cũ còn dùng API
Lựa chọn xem xét:
  A. Giữ cache nhưng version hóa và kiểm tra dữ liệu mới
  B. Đọc từ nguồn có thẩm quyền cho yêu cầu nhạy cảm
  C. Thay kiến trúc lưu tiến độ dài hạn
Bằng chứng hiện có: Test đa phiên, trace, dữ liệu hỗ trợ đã xử lý an toàn
Quyết định: <phương án được chọn sau đánh giá>
Người có quyền chốt: <theo ma trận quyền quyết định>
Người được tham vấn: <các đội phụ thuộc + an toàn dữ liệu nếu cần>
Hệ quả/trade-off: <độ trễ, chi phí, dữ liệu, tương thích>
Kiểm chứng: <acceptance, integration, guardrails, rollout>
Điều kiện xem lại: <tín hiệu hoặc thời điểm>
~~~

Mẫu trên là **tài liệu phục vụ hiểu biết chung**, không phải biểu mẫu bắt buộc cho mọi commit.

### Ghi rõ điều chưa biết

Nếu chưa xác nhận số người dùng bị ảnh hưởng hoặc độ trễ cache, hãy ghi **“chưa biết; cách kiểm tra là...”**. Trách nhiệm giải trình không yêu cầu giả vờ mọi quyết định đều chắc chắn; nó yêu cầu **minh bạch về mức độ tin cậy và kế hoạch học thêm**.

### Bản ghi quyết định khác biên bản cuộc họp

Biên bản có thể ghi “A nói, B nói, C nói”. Decision Record cần giúp người đọc biết **vì sao chọn phương án, rủi ro nào được chấp nhận, ai có quyền quyết định và khi nào cần xem lại**. Những câu hỏi chưa chốt cần có owner để không mất trong chat.

## 12. Escalation: khi nào nhóm nên dừng để xin hỗ trợ?

**Escalation** không phải dấu hiệu nhóm thiếu tự chủ. Đó là cơ chế **đưa quyết định tới đúng quyền hạn khi rủi ro, phụ thuộc hoặc xung đột vượt ranh giới đã giao**.

### Các tín hiệu cần nâng cấp

- Nguy cơ **truy cập dữ liệu trái phép, lộ thông tin hoặc mất dữ liệu**.
- Thay đổi phạm vi **chính sách nghiệp vụ, hợp đồng hoặc nghĩa vụ pháp lý** không thuộc thẩm quyền nhóm.
- Cần **ngân sách, nhân lực hoặc hợp đồng bên ngoài** vượt giới hạn được trao.
- Phụ thuộc liên nhóm không có owner hoặc quyết định bị treo quá lâu.
- Sprint Goal có nguy cơ không đạt vì bối cảnh thay đổi lớn và cần Product Owner thảo luận.
- Hai chính sách bắt buộc mâu thuẫn nhau, chưa rõ ai được quyền giải quyết.
- Một release có guardrail báo động nhưng có người yêu cầu “vẫn phát hành cho kịp”.

### Mẫu yêu cầu nâng cấp ngắn

~~~text
Vấn đề: Dữ liệu tiến độ có thể mất khi migration phiên bản mới
Phạm vi ảnh hưởng: <cohort/dịch vụ đã xác minh>
Quyết định cần có: Có tiếp tục rollout không? Có cần khôi phục dữ liệu?
Những gì nhóm đã thử/xác minh: <test, backup, canary, giới hạn>
Lựa chọn: Tạm dừng / rollback an toàn / forward fix theo điều kiện
Rủi ro mỗi lựa chọn: <tác động, đảo ngược, thời gian>
Người cần quyết định: <theo quy trình vận hành và dữ liệu>
Thời điểm cần chốt: <mốc phụ thuộc/rủi ro>
Đầu mối: <người cập nhật tình trạng>
~~~

### Escalation khác chuyển trách nhiệm lên cấp trên

Nhóm vẫn cần cung cấp **bằng chứng, lựa chọn và tác động**, thay vì chỉ nói “cấp trên quyết đi”. Người có thẩm quyền cần ra quyết định **trong phạm vi của mình**, tránh thay nhóm chọn toàn bộ phương án kỹ thuật chi tiết khi không cần.

### Sự cố khẩn không chờ Sprint Review

Với vấn đề đang gây hại cho dữ liệu hoặc quyền truy cập, áp dụng **quy trình incident và bảo mật ngay**, không chờ cuộc họp định kỳ hoặc lịch phê duyệt thông thường. Sau khi ổn định mới dùng Sprint Review/Retrospective hoặc postmortem để kiểm tra hướng sản phẩm và cải tiến hệ thống.

## 13. Minh bạch tiến độ và rủi ro mà không biến thành giám sát vi mô

Một hệ thống có trách nhiệm giải trình không cần quản lý hỏi từng thành viên **“Hôm nay viết mấy dòng code?”**. Minh bạch tốt giúp người liên quan nhìn thấy **mục tiêu, Increment, trở ngại, chất lượng và dữ liệu kết quả**.

### Một bảng trạng thái có ích

| Thành phần | Ví dụ hiển thị | Câu hỏi hỗ trợ |
| --- | --- | --- |
| **Product Goal/Sprint Goal** | Đường đi tới hành trình tiếp tục học tin cậy | Chúng ta đang làm đúng việc quan trọng? |
| **Product/Sprint Backlog** | Các PBI và tiêu chí chấp nhận đã làm rõ | Phạm vi nào gần được giao? |
| **WIP và blocker** | Story đang làm, chờ quyết định hay chờ review | Điểm nghẽn ở đâu, ai có thể giúp? |
| **Increment/DoD** | Những lát đã đạt chất lượng chung | Sản phẩm thực sự có gì dùng được? |
| **Release/availability** | Cohort nào đã dùng được, feature flag ở trạng thái nào | Người dùng đã tiếp cận kết quả chưa? |
| **Outcome** | Tỷ lệ mở đúng bài, phản hồi người học | Giả thuyết giá trị có được hỗ trợ? |
| **Guardrails** | Lỗi quyền, tính toàn vẹn tiến độ, độ tin cậy | Có đang đánh đổi an toàn hoặc chất lượng? |
| **Decision/risks** | Câu hỏi chưa chốt, chủ thể quyết định, thời hạn | Điều gì cần phối hợp hoặc escalation? |

### Không nhầm “đã làm nhiều” với “đang tiến tới mục tiêu”

Một Sprint có thể hoàn thành 30 task kỹ thuật nhưng chưa tạo được Increment mở bài đúng quyền. Báo cáo **“95% task Done”** không chứng minh Sprint Goal gần hoàn thành nếu 5% còn lại là kiểm thử tích hợp và quyền truy cập bắt buộc.

### Trách nhiệm đi cùng quyền nhìn thấy thông tin

Nếu Product Owner yêu cầu giải trình về tiến độ nhưng không có quyền truy cập dữ liệu release, hoặc Developers phải cam kết thời gian mà không biết phụ thuộc vận hành, cơ chế đang thiếu minh bạch. Cần làm rõ **những dữ liệu nào được phép chia sẻ, ai cập nhật và nhịp xem lại**.

### Bảo vệ quyền riêng tư trong dashboard

Không đưa thông tin tiến độ học cá nhân, token, dữ liệu thanh toán hoặc hồ sơ nhạy cảm vào bảng công khai chỉ để theo dõi outcome. Dùng **tổng hợp, phân quyền và dữ liệu tối thiểu** theo yêu cầu hợp lệ.

## 14. Accountability bằng outcome, flow và chất lượng: không thưởng cho số đẹp

Chỉ số có thể tạo ra hành vi tốt hoặc **đẩy nhóm tối ưu lệch**. Nếu chỉ thưởng vì giao nhiều story point, một nhóm có thể chia ticket hình thức hoặc né việc khó. Nếu chỉ thưởng vì không có bug, mọi người có thể ngại báo lỗi.

### Bộ ba thấu kính đo lường

| Thấu kính | Ví dụ chỉ số | Cần hiểu giới hạn |
| --- | --- | --- |
| **Value/outcome** | Học viên mở bài thành công; tỷ lệ hoàn tất hành trình; phản hồi có ý nghĩa | Có yếu tố bên ngoài; cần định nghĩa mẫu số và cohort |
| **Flow** | Lead time, cycle time, throughput, work item age, WIP | Nhanh không đồng nghĩa đúng; phải thống nhất ranh giới đo |
| **Quality/risk** | Lỗi lọt production, sai quyền, thời gian khôi phục, kết quả DoD | Đếm bug không đủ; xem mức độ ảnh hưởng và khả năng phát hiện |

Một chỉ số thứ tư có thể là **sức khỏe cộng tác**: thời gian chờ quyết định, phản hồi của nhóm, mức ổn định của WIP và khả năng nêu rủi ro sớm. Không nên biến số tin nhắn, thời gian online hoặc số lần phát biểu thành thước đo năng suất cá nhân.

### Ví dụ báo cáo có giải trình

~~~text
Mục tiêu: Người học khóa tuyến tính tiếp tục đúng bài nhanh hơn
Đã giao: Điều hướng bài tiếp theo, trạng thái hoàn thành và kiểm tra quyền
Đã đạt DoD: <các PBI cụ thể, bằng chứng CI/integration>
Đã sẵn có: <cohort, phiên bản, thời điểm>
Outcome quan sát: <số học viên, tỷ lệ, cửa sổ và giới hạn mẫu>
Guardrails: <các lỗi quyền/dữ liệu/độ tin cậy đã kiểm tra>
Rủi ro còn mở: <một số loại khóa chưa hỗ trợ hoặc dữ liệu chưa đủ>
Quyết định tiếp theo: <tiếp tục, đổi backlog, thu hẹp hay dừng>
~~~

### Vì sao không nên dùng velocity để đánh giá “tự chủ”?

Velocity và story points (nếu nhóm có dùng) chủ yếu hỗ trợ **lập kế hoạch trong ngữ cảnh nhóm**, không có đơn vị tiêu chuẩn so sánh giữa các nhóm. Tăng velocity bằng cách nâng điểm ước lượng không tạo thêm giá trị. Accountability cần **giữ câu chuyện kết quả và bằng chứng**, không biến chỉ số hỗ trợ thành mục tiêu tự thân.

## 15. Dự báo, deadline và năng lực: tự chủ không phải hứa điều chưa biết

Khi stakeholder yêu cầu một mốc phát hành, nhóm cần thể hiện **độ bất định** thay vì nhận một ngày chắc chắn rồi giải quyết bằng làm thêm giờ.

### Tách ba câu hỏi

1. **Điều gì bắt buộc tại mốc thời gian?** Có nghĩa vụ đã chốt hay chỉ mong muốn?
2. **Giá trị tối thiểu an toàn là gì?** Có thể chia sản phẩm thành lát có thể dùng và phù hợp DoD?
3. **Xác suất hoàn thành đến đâu?** Dựa trên throughput, cycle time, phụ thuộc và rủi ro hiện tại, điều gì còn bất định?

### Ví dụ giới hạn thời gian và phạm vi

Giả sử một đợt khai giảng bắt đầu sau ba tuần. Nền tảng muốn hỗ trợ “Tiếp tục học” cho **khóa tuyến tính**, còn phiên bản dành cho khóa tự chọn chưa đủ rõ.

| Lựa chọn | Tác động giá trị | Rủi ro |
| --- | --- | --- |
| Giao lát tuyến tính đạt DoD trước đợt khai giảng | Học viên có hành trình cơ bản, có thể nhận phản hồi sớm | Chưa hỗ trợ mọi loại khóa |
| Cố triển khai cả tuyến tính lẫn tự chọn, giảm test để kịp | Phạm vi rộng trên giấy | Có thể cấp sai quyền, sai tiến độ, khó rollback |
| Dời toàn bộ release đến khi mọi loại khóa hoàn hảo | Ít phải phân biệt cohort ở thời điểm đầu | Chậm học hỏi và bỏ lỡ giá trị khả dụng sớm |

Quyết định sản phẩm có thể chọn **lát tuyến tính có guardrail**, nếu phù hợp nhu cầu và ràng buộc thực tế. Developers tự quyết cách triển khai trong phạm vi ấy nhưng không được tự bỏ test bảo mật để “đúng deadline”.

### Tính đến phụ thuộc và hàng đợi

Nếu PBI cần API của nhóm khác hoặc phê duyệt dữ liệu, thời gian chờ **thuộc lead time thực tế**. Không được loại nó ra khi báo thời gian từ yêu cầu tới giao. Nhóm có thể đo riêng blocked time để tìm cách giảm chờ và nâng cấp phụ thuộc sớm.

### Dự báo có điều kiện tốt hơn cam kết giả

“Với 10 story tiêu chuẩn cùng loại, chúng tôi có mức thời gian lịch sử ...; nếu không có thay đổi lớn ở API và kiểm thử, mục tiêu khả thi là lát A/B, còn lát C cần đánh giá thêm”. Đó là cách giải trình trung thực hơn câu **“Toàn bộ tính năng chắc chắn xong vào thứ Sáu”** khi chưa có bằng chứng.

## 16. Quản trị dựa trên rủi ro thay vì phê duyệt theo cấp bậc

Một quyết định nhỏ, dễ đảo ngược không nên mất ba ngày xin chữ ký; một migration dữ liệu quan trọng không nên được triển khai vì “nhóm có quyền tự chủ”.

### Phân loại thay đổi theo tác động

| Nhóm rủi ro | Ví dụ | Cơ chế phù hợp |
| --- | --- | --- |
| **Thấp, phạm vi hẹp** | Refactor private method có kiểm thử | Developers tự làm, review/CI theo chính sách |
| **Trung bình, có phụ thuộc** | Đổi hợp đồng API nội bộ có client liên quan | Contract tests, tham vấn bên tiêu thụ, cách chuyển tiếp |
| **Cao, ảnh hưởng dữ liệu/quyền** | Thay quy tắc ghi danh, schema lưu tiến độ, quyền xem nội dung | Đánh giá liên chức năng, kiểm thử tích hợp/bảo mật, rollout kiểm soát |
| **Nghiêm trọng hoặc nghĩa vụ bên ngoài** | Dữ liệu cá nhân, sự cố lộ thông tin, vượt ngân sách lớn | Người có thẩm quyền hợp lệ và quy trình bắt buộc |

### Ba cách giảm gánh quản trị mà không giảm an toàn

- **Chuẩn hóa tiêu chuẩn đã lặp lại:** CI, kiểm thử hợp đồng, DoD, chính sách code review rõ ràng.
- **Trao quyền theo giới hạn:** thỏa thuận budget, cohort, loại quyết định và ngưỡng rủi ro trước khi làm.
- **Kiểm tra theo tín hiệu:** chỉ nâng cấp khi vượt ranh giới hoặc guardrail, thay vì duyệt mọi task.

### Governance có thể tạo giá trị khi giảm chờ

Một quy trình phê duyệt khiến đội chờ nhiều ngày có thể là rủi ro delivery. Hãy hỏi **“Quyết định này thật sự cần chuyên môn hoặc thẩm quyền gì?”** Nếu câu trả lời chỉ là “vì từ trước tới giờ phải có chữ ký”, cần xem lại chính sách với người có quyền thay đổi.

### Đừng làm mờ tính bắt buộc của chuẩn pháp lý/hợp đồng

Một team không thể dùng lý do “Agile linh hoạt” để bỏ kiểm soát dữ liệu, nghĩa vụ hợp đồng hoặc chính sách an toàn đã được tổ chức áp dụng hợp lệ. Khi chưa rõ yêu cầu, cần **xác minh với chuyên gia có thẩm quyền**, không tự tuyên bố điều gì là đủ tuân thủ.

## 17. Cộng tác liên nhóm mà không làm mất quyền tự quyết

Nhiều mục tiêu sản phẩm vượt ranh giới một Scrum Team. Nền tảng học có thể cần phối hợp **Identity (xác thực)**, **Learning (tiến độ)** và **Experience (giao diện)**.

### Mục tiêu chung, quyền quyết định tách rõ

| Vấn đề | Cần thống nhất liên nhóm | Vẫn có thể để nhóm tự quyết |
| --- | --- | --- |
| **Người học được cấp quyền khi nào?** | Quy tắc nghiệp vụ, API authorization và hợp đồng trạng thái | Thiết kế nội bộ của mỗi service |
| **Tiến độ giữa thiết bị có nhất quán?** | Semantics cập nhật, conflict, thời gian đồng bộ chấp nhận | Cách tối ưu cache/adapter trong giới hạn |
| **Khi API thay đổi** | Versioning, contract, compatibility và lịch chuyển | Cấu trúc lớp/hàm và chiến lược unit testing |
| **Incident liên thành phần** | Người trực, severity, kênh phản hồi, quyền rollback | Khắc phục kỹ thuật cục bộ trong quyền được giao |
| **Khả năng quan sát** | ID tương quan, định nghĩa một số business metrics và guardrail | Cách triển khai telemetry phù hợp từng môi trường |

### Một API contract có thể là “ranh giới tự chủ”

Nếu Experience cần trường trạng thái **PENDING/ACTIVE/REJECTED**, Learning có thể refactor nội bộ nhưng **không tự đổi nghĩa trạng thái** mà không điều phối với bên tiêu thụ. Contract tests và versioning tạo điều kiện để các đội **phát triển độc lập nhưng không gây bất ngờ**.

### Điều phối không đồng nghĩa phải có thêm một cấp quản lý

Một cuộc trao đổi ngắn giữa người có đủ kiến thức và quyền quyết định đôi khi hiệu quả hơn một hội đồng lớn. Có thể dùng **RFC ngắn, decision log, integration test và thời hạn phản hồi**, rồi chỉ nâng cấp khi quyền, rủi ro hoặc xung đột vượt phạm vi.

### Đo phụ thuộc như vấn đề của hệ thống

Nếu story thường xuyên chờ nhóm khác, theo dõi **work item age, blocked time, cycle time và rủi ro Sprint Goal**. Đừng đổ lỗi cho một cá nhân chỉ vì người ấy không thể thay đổi lịch ưu tiên của đội khác.

## 18. Lãnh đạo và stakeholder tạo điều kiện tự chủ như thế nào?

Trao quyền không có nghĩa **người quản lý bỏ mặc nhóm**. Vai trò hỗ trợ có thể bao gồm làm rõ chiến lược, ngân sách, nghĩa vụ, ranh giới ra quyết định và loại bỏ trở ngại ngoài quyền hạn nhóm.

### Hành vi hỗ trợ hữu ích

| Thay vì... | Hãy thử... |
| --- | --- |
| “Dùng công cụ này vì tôi đã quyết” | “Mục tiêu, rủi ro và yêu cầu tương thích là gì? Nhóm đề xuất phương án và bằng chứng ra sao?” |
| “Báo cáo từng người làm gì mỗi ngày” | “Sprint Goal, Increment, blocker, outcome và chất lượng đang như thế nào?” |
| “Mọi việc đều xin phép tôi” | “Những quyết định nào nhóm tự chốt, những ngưỡng nào phải trao đổi?” |
| “Đã cam kết thì không được đổi” | “Thông tin mới có làm thay đổi cách đạt mục tiêu không? Đánh đổi nào cần PO quyết định?” |
| “Lỗi này do ai?” | “Hệ thống đã bỏ sót kiểm tra nào, tác động ra sao, phòng ngừa bằng gì?” |
| “Tăng velocity thêm 30%” | “Điểm nghẽn nào làm lead time dài và chất lượng xấu? Có cải tiến nào đo được?” |

### Lãnh đạo có thể giữ giới hạn mà không kiểm soát giải pháp

Ví dụ một quản lý có thể thông báo **“Dự án không được vượt hạn mức ngân sách đã duyệt và phải tuân thủ chính sách dữ liệu”**. Trong phạm vi ấy, Scrum Team nên có quyền đề xuất cách chia lát, lựa chọn kỹ thuật và kế hoạch thử nghiệm. Nếu giới hạn làm mục tiêu bất khả thi, **nhóm có trách nhiệm nêu bằng chứng và trade-off** thay vì âm thầm giảm chất lượng.

### Trách nhiệm hai chiều

Nhóm có trách nhiệm **minh bạch kết quả, nêu rủi ro sớm và đề xuất phương án**. Người trao quyền có trách nhiệm **giữ ranh giới ổn định, phản hồi đúng lúc và không đòi quyết định vượt quyền đã giao**. Nếu quyền hạn luôn bị rút lại sau mỗi lần thất bại, nhóm sẽ học cách xin phép tất cả để tự bảo vệ.

## 19. An toàn tâm lý và accountability hỗ trợ nhau

Một nhóm không thể giải trình trung thực nếu mọi người sợ báo lỗi hoặc phản biện người có quyền lực. Nhưng cũng không thể tạo niềm tin lâu dài nếu ai cũng có thể nói mà **không ai chịu trách nhiệm thực hiện quyết định**.

### Ví dụ cách ứng xử khi phát hiện lỗi

Trong lúc review, tester chỉ ra rằng khóa cần duyệt đã cho học viên PENDING mở bài hạn chế. Phản ứng tốt:

1. **Dừng hoặc giới hạn đường phát hành rủi ro** theo quy trình.
2. **Xác minh bằng test/API** và làm rõ phạm vi ảnh hưởng.
3. **Cảm ơn thông tin được nêu sớm**, không coi việc báo lỗi là phá tiến độ.
4. **Chỉ định người theo dõi khắc phục**, phân quyền rõ những quyết định phải chốt.
5. **Bổ sung lớp phòng ngừa**, ví dụ acceptance criteria và security integration tests.
6. **Kiểm tra hiệu quả**, không chỉ đóng ticket.

### Blameless không có nghĩa không có tiêu chuẩn

Nếu mã không đạt DoD, nhóm cần sửa trước khi gọi Increment Done. Nếu có hành vi cố tình che giấu sự cố, vấn đề phải được xử lý qua quy trình có thẩm quyền. **Cách điều tra dựa trên hệ thống** khác với bỏ qua trách nhiệm bảo mật hoặc nghĩa vụ nghề nghiệp.

### Người ít có quyền lực cần kênh góp ý thực chất

Trong nhóm phân tán, quyết định có thể bị chốt trong cuộc họp của một văn phòng. Hãy cho người liên quan **ngữ cảnh trước, cửa sổ phản hồi, decision log và đường escalation**. Được mời vào chat sau khi mọi thứ đã quyết xong không phải cơ hội đóng góp công bằng.

## 20. Tình huống xuyên suốt: cân bằng tốc độ ra mắt và quyền học viên

### 20.1. Bối cảnh

Một nền tảng học chuẩn bị mở đợt khai giảng sau ba tuần. Product Owner muốn tăng khả năng người học quay lại, còn nhóm vận hành yêu cầu không ảnh hưởng dữ liệu tiến độ. Bộ phận kinh doanh đề nghị thêm chức năng gợi ý bài học cho mọi loại khóa, trong khi Developers cho biết **luồng “Tiếp tục học” của khóa tuyến tính** là lát có thể kiểm chứng sớm.

Những ràng buộc đã xác nhận trong ví dụ:

- Học viên chưa có quyền không được xem nội dung hạn chế.
- Tiến độ học không được bị ghi lùi hoặc mất khi đổi thiết bị ngoài quy tắc đã công bố.
- Increment phải đáp ứng DoD của sản phẩm.
- Đợt thử chỉ dùng cohort và ngân sách đã được chấp thuận.
- Việc dùng dữ liệu cho mục đích mới phải qua thẩm quyền tương ứng.
- Deadline đợt khai giảng là mốc mong muốn có tầm quan trọng cao, **không phải lý do bỏ kiểm soát bắt buộc**.

### 20.2. Thỏa thuận quyền tự chủ

| Quyết định | Ví dụ áp dụng |
| --- | --- |
| **Product Owner quyết định hướng giá trị và thứ tự backlog** | Ưu tiên lát khóa tuyến tính có khả năng đến người học sớm |
| **Developers quyết định thiết kế và cách triển khai** | Chọn thuật toán tìm bài tiếp theo, API, refactoring, test |
| **Scrum Team thống nhất Sprint Goal** | Giao hành trình tuyến tính đúng quyền cho cohort thử |
| **Người phụ trách bảo mật/dữ liệu theo thẩm quyền** | Đánh giá thay đổi xử lý dữ liệu nếu phát sinh mục đích mới |
| **Người được trao quyền vận hành** | Bật/tắt rollout trong cohort đã chốt, kích hoạt quy trình incident khi cần |
| **Stakeholder hỗ trợ bằng dữ liệu và phản hồi** | Chia sẻ vấn đề người học, nhưng không tự chèn task vào Sprint Backlog mà không trao đổi |

### 20.3. Sprint Goal ứng viên

> “Học viên đủ điều kiện trong khóa tuyến tính có thể tiếp tục đúng bài, với kiểm soát quyền và dữ liệu tiến độ được xác minh, đủ an toàn để thử trên cohort đã thống nhất”.

Đây là mục tiêu có hướng giá trị; nó không khóa Developers vào một thiết kế duy nhất. Những user story có thể chọn là xác định bài tiếp theo, trạng thái hoàn tất, API kiểm tra quyền và tích hợp thử nghiệm theo DoD.

### 20.4. Quyết định khó xảy ra giữa Sprint

Đến giữa Sprint, nhóm phát hiện:

- Test đơn vị thuật toán đã xanh.
- Kiểm thử tích hợp cho hai thiết bị phát hiện cache có thể trả tiến độ cũ.
- Thiết kế lại toàn bộ cache sẽ khó kịp đợt khai giảng.
- Một phần stakeholder yêu cầu vẫn bật rollout toàn bộ vì đã truyền thông.

Nhóm **không nên** chỉ nhìn tỷ lệ task Done rồi tuyên bố hoàn tất. Họ cần đối chiếu:

1. **Sprint Goal:** lát nào đủ giá trị khi chỉ có dữ liệu một thiết bị hoặc khi chưa bật tính năng đồng bộ?
2. **DoD:** Increment có đáp ứng tiêu chuẩn chất lượng bắt buộc chưa?
3. **Guardrail:** có nguy cơ cấp sai quyền, ghi lùi tiến độ hoặc làm mất dữ liệu không?
4. **Khả năng phát hành:** có thể giới hạn cohort và đường đi chức năng để tránh tác động ngoài phạm vi không?
5. **Quyền quyết định:** quyết định đổi phạm vi thuộc Product Owner, còn cách triển khai và kiểm chứng thuộc Developers trong ranh giới.

Một lựa chọn khả thi có thể là **giữ chức năng tuyến tính trên luồng dữ liệu đã được kiểm chứng**, chưa bật tính năng đồng bộ mới, ghi rõ phần chưa phục vụ và bổ sung PBI tiếp theo. Nhưng nếu ngay cả lát tối thiểu cũng **không đạt DoD hoặc gây sai quyền**, không được gọi Done và phát hành chỉ để đáp ứng mốc.

### 20.5. Mẫu báo cáo giải trình sau Sprint

~~~text
Mục tiêu Sprint: Tiếp tục học đúng quyền cho khóa tuyến tính
Increment đạt DoD: <phạm vi đã xác minh>
Phạm vi chưa giao: <đồng bộ đa thiết bị hoặc loại khóa chưa đạt>
Quyết định scope/release: <PO + các bên có thẩm quyền, lý do>
Chất lượng: <acceptance, security, integration tests, lỗi còn mở>
Availability: <cohort thực sự dùng được>
Outcome: <số học viên, tỷ lệ mở đúng bài, khung đo>
Guardrail: <quyền, tiến độ, sự cố, dữ liệu>
Phụ thuộc: <điều cần đội khác xác nhận>
Điều học được: <giả thuyết nào đúng/sai/chưa đủ dữ liệu>
Bước tiếp theo: <Product Backlog và cải tiến cách làm>
~~~

**Mức độ giải trình** ở đây là kể được câu chuyện **mục tiêu → quyết định → Increment → bằng chứng → điều chỉnh**, không phải cố khẳng định tất cả mục tiêu đã đạt khi dữ liệu chưa đủ.

## 21. Khi áp dụng Kanban, XP và Lean thì tự chủ được vận hành ra sao?

### Kanban: chính sách luồng và quyền kéo việc

Kanban giúp hiển thị WIP, blocked items, cycle time, throughput và work item age. Nhóm có thể tự điều chỉnh cách kéo việc, giới hạn WIP hoặc chính sách review **trong những mục tiêu, chất lượng và thẩm quyền đã thống nhất**.

Ví dụ:

- **Mục tiêu:** giảm thời gian từ bắt đầu tới Increment đạt DoD.
- **Quyền tự chủ:** nhóm thử giới hạn WIP ở Review/Test và hỗ trợ hoàn tất trước khi mở việc mới.
- **Ranh giới:** không bỏ test bảo mật, không ép làm thêm giờ, không đổi định nghĩa Done để làm số đẹp.
- **Bằng chứng:** phân phối cycle time, số story bị blocker, lỗi hồi quy và chất lượng review.

**Một chính sách WIP không phải hình thức giám sát cá nhân**. Nó điều phối dòng công việc của cả hệ thống và có thể được cải tiến khi dữ liệu cho thấy hạn mức không còn phù hợp.

### XP: tự chủ kỹ thuật phải đi với phản hồi sớm

XP nhấn mạnh **TDD, refactoring, continuous integration, pair programming và thiết kế đơn giản**. Developers có quyền lựa chọn cách thiết kế và cải thiện mã, nhưng test và CI tạo bằng chứng để lựa chọn ấy **không phá hành vi đã cam kết**.

Ví dụ, nhóm có thể tự quyết dùng refactoring để gom quy tắc phân quyền, nhưng không tự đổi **ý nghĩa của trạng thái ACTIVE**, và phải giữ các kiểm thử quyền ở tầng API/tích hợp phù hợp.

### Lean: tự chủ để tối ưu toàn dòng giá trị

Lean thúc đẩy giảm thời gian chờ, làm lại và quyết định muộn. Một nhóm chỉ tối ưu tốc độ viết code nhưng khiến QA hoặc vận hành thành hàng đợi thì **không cải thiện lead time người dùng**.

Tự chủ hữu ích khi có **mục tiêu end-to-end**, nhiều nhóm chia sẻ tín hiệu và quyền điều chỉnh được đưa tới nơi có thông tin. Điều đó cũng đòi hỏi lãnh đạo phối hợp tháo những phụ thuộc **vượt phạm vi một Scrum Team**.

### Không một framework nào tự giải quyết xung đột thẩm quyền

Scrum, Kanban, XP và Lean cung cấp khái niệm/thực hành có ích, nhưng tổ chức vẫn phải làm rõ **ai chịu trách nhiệm về dữ liệu, ngân sách, tuân thủ, cam kết bên ngoài và ngoại lệ**. Đổi tên chức danh hoặc thay board không tự tạo ra quyền tự chủ có trách nhiệm.

## 22. Những phản mẫu làm tự chủ và trách nhiệm giải trình lệch nhau

| Phản mẫu | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| **Giao mục tiêu mơ hồ “làm sản phẩm tốt hơn”** | Nhóm tự tối ưu những thứ không có ưu tiên chung | Nêu Product Goal, outcome, người dùng và ràng buộc |
| **Đưa nguyên solution và gọi là tự chủ** | Developers không có quyền tìm cách phù hợp | Giao vấn đề/kết quả, giữ chuẩn bắt buộc |
| **Mọi quyết định đều phải xin ký duyệt** | Hàng đợi tăng, nhóm mất trách nhiệm thực chất | Phân quyền theo rủi ro và khả năng đảo ngược |
| **Tự chủ nghĩa được bỏ DoD** | Increment rủi ro và chất lượng kém | Giữ DoD như commitment và guardrail |
| **Stakeholder đổi thứ tự việc trực tiếp trong Sprint** | Sprint Goal mất tập trung | Trao đổi qua PO và Scrum Team theo accountability |
| **PO chỉ đạo cấu trúc mã chi tiết** | Giảm tự quản kỹ thuật và chất lượng tranh luận | PO làm rõ giá trị; Developers quyết định kỹ thuật trong ranh giới |
| **Developers tự đổi quy tắc nghiệp vụ** | Có thể giao đúng code nhưng sai quyền hoặc giá trị | Làm rõ acceptance criteria với người có thẩm quyền |
| **Scrum Master thành người phê duyệt mọi task** | Sai accountability và tạo hàng đợi | Hỗ trợ Scrum Team tự quản và tháo trở ngại |
| **Chỉ đo story points hoặc số ticket Done** | Tối ưu output giả, che rủi ro | Xem outcome, flow và quality guardrails |
| **Che rủi ro để giữ báo cáo xanh** | Phản hồi đến muộn, gây hại người dùng | Tạo an toàn tâm lý và kênh escalation sớm |
| **Lấy velocity so đội để thưởng/phạt** | Ước lượng méo, né việc khó | Dùng dữ liệu nội bộ để lập kế hoạch, không chấm con người |
| **Phê duyệt compliance theo thủ tục nhưng không kiểm chứng** | Có chữ ký mà rủi ro còn nguyên | Kết hợp thẩm quyền, test, giám sát và bằng chứng |
| **Ranh giới không rõ khiến nhóm tự kiểm duyệt** | Mọi quyết định nhỏ cũng phải hỏi quản lý | Viết decision rights và giới hạn được trao |
| **Quyền quyết định không đi cùng thông tin** | Người có quyền chốt thiếu bằng chứng | Chia sẻ telemetry, phương án và tác động theo quyền hợp lệ |
| **Một người chịu trách nhiệm nhưng không có quyền xử lý** | Blocker kéo dài, đổ lỗi sai đối tượng | Ghi owner, thẩm quyền và đường escalation |
| **Không có nguồn sự thật cho quyết định** | Nhóm phân tán làm sai khác biệt | Decision log ngắn, kết luận dễ tìm |
| **Deadline được dùng để bỏ kiểm thử** | Có thể phát hành sai quyền/mất dữ liệu | Chia phạm vi hoặc thương lượng mốc, giữ guardrail |
| **Thấy rủi ro nhưng vẫn release vì đã hứa** | Thiệt hại có thể lớn hơn việc lùi chức năng | Chính sách dừng rollout và phản ứng theo severity |
| **Không xem lại guardrail khi bối cảnh đổi** | Chính sách cản trở hoặc không còn bảo vệ đủ | Review định kỳ dựa trên rủi ro và bằng chứng |
| **Đồng nhất accountability với truy lỗi cá nhân** | Giấu lỗi, không dám nói sự thật | Tách giải trình kết quả khỏi công kích con người |
| **Phê duyệt mọi ngoại lệ bằng chat riêng** | Thiếu dấu vết và người liên quan không biết | Ghi quyết định, phạm vi, thời hạn và kiểm soát |
| **Chỉ báo cáo outcome đẹp** | Bỏ qua lỗi, dữ liệu thiếu và người dùng bị ảnh hưởng | Báo đầy đủ mẫu số, guardrail, rủi ro và giới hạn |

## 23. Bài thực hành: thiết kế tự chủ có trách nhiệm cho một Scrum Team

### 23.1. Bối cảnh

Scrum Team xây nền tảng học có **10 ngày làm việc** trước một đợt giới thiệu chức năng. Stakeholder muốn ba khả năng:

1. Học viên đã ghi danh xem bài tiếp theo.
2. Học viên đang PENDING cũng được mở bài để “trải nghiệm nhanh”.
3. Hệ thống gợi ý bài theo dữ liệu lịch sử, chưa rõ cơ sở sử dụng dữ liệu.

Product Owner cho biết mục tiêu quan trọng là **học viên có quyền mở đúng bài tiếp theo**. Developers ước tính lát thứ nhất có thể hoàn thành đạt DoD trong nhịp hiện tại; lát thứ hai có nguy cơ vi phạm quy tắc quyền học, lát thứ ba cần xác minh dữ liệu và thêm nghiên cứu.

Những sự kiện khác:

- Một người quản lý muốn duyệt **mọi PR** vì gần đây có một sự cố.
- Một Developer đề xuất bỏ kiểm thử tích hợp để kịp hạn.
- Nhóm vận hành muốn có khả năng dừng rollout khi lỗi tăng.
- Người kiểm thử từ xa phát hiện trường hợp gọi API trực tiếp vượt qua kiểm tra UI.
- Hai nhóm khác nhau phụ trách Identity và Learning.
- Sprint Goal dự thảo là “Hoàn thành cả ba tính năng”, chưa được Scrum Team cùng xác nhận.

### 23.2. Nhiệm vụ

1. Viết lại **mục tiêu theo giá trị người dùng**, không theo danh sách giải pháp.
2. Đề xuất **Sprint Goal ứng viên** có thể tập trung trong thời gian còn lại.
3. Phân biệt **ít nhất năm quyết định nhóm tự chủ** với **năm quyết định cần tham vấn/nâng cấp**.
4. Xây một bảng **guardrail** về quyền, dữ liệu, DoD, release và ngân sách.
5. Giải thích vì sao “PENDING được mở bài hạn chế” **không phải chỉ là thay đổi UI**.
6. Đề xuất **ba acceptance examples** có thể tự động hóa ở tầng phù hợp.
7. Đề xuất **hai outcome/guardrail metrics**, nêu tử số, mẫu số và cửa sổ quan sát khi thích hợp.
8. Nêu cách xử lý đề xuất “mọi PR phải có chữ ký quản lý” sao cho vẫn bảo vệ chất lượng.
9. Nếu phát hiện API cho người PENDING đọc dữ liệu khi sắp release, ai cần biết và xử lý ra sao?
10. Mô tả **một bản giải trình sau Sprint** không dùng story points làm thành tích cá nhân.
11. Nếu Product Owner muốn mở rộng sang gợi ý AI ngay trong Sprint, nhóm nên thảo luận quyền quyết định và rủi ro thế nào?
12. Chọn một hành động cải tiến cho Retrospective, có owner, mốc xem lại và bằng chứng.

### 23.3. Đáp án tham khảo: mục tiêu và Sprint Goal

**Mục tiêu sản phẩm:** “Học viên có quyền có thể quay lại đúng vị trí học mà không phải tìm thủ công và không bị cấp sai quyền truy cập”.

**Sprint Goal ứng viên:** “Cung cấp hành trình tiếp tục học đáng tin cho khóa tuyến tính của học viên đủ điều kiện, đạt DoD và có bằng chứng kiểm soát quyền để thử với cohort được chấp thuận”.

Điểm mạnh là **mô tả kết quả**, để nhóm tự quyết thiết kế nội bộ, cách kiểm thử và chi tiết giao diện. Mục tiêu không hứa làm ba giải pháp chưa được làm rõ; Product Owner và Scrum Team cần xác nhận dựa trên năng lực và Product Goal.

### 23.4. Đáp án tham khảo: quyền quyết định

| Quyết định nhóm tự chủ trong phạm vi | Quyết định phải tham vấn hoặc có thẩm quyền chốt |
| --- | --- |
| Chia lát story tuyến tính nhỏ đủ kiểm chứng | Đổi quy tắc nghiệp vụ PENDING/ACTIVE |
| Chọn thiết kế service, interface nội bộ | Đổi hợp đồng API với nhóm Identity/Learning |
| Chọn unit, integration và security tests phù hợp DoD | Dùng dữ liệu lịch sử học cho mục đích mới |
| Phân công, pairing, refactoring và cách review nội bộ | Vượt ngân sách, hợp đồng hoặc mốc bắt buộc đã cam kết |
| Điều chỉnh Sprint Backlog để tiến tới Sprint Goal | Quyết định mở rộng rollout ngoài cohort đã chốt |
| Đề xuất test tự động và cải tiến CI | Phê duyệt ngoại lệ chính sách bắt buộc |

Những quyết định trong cột trái **không vô điều kiện**; nếu xuất hiện rủi ro dữ liệu, bảo mật hoặc vượt chuẩn tổ chức, cần nâng cấp theo chính sách. Cột phải không phải tất cả do một quản lý duy nhất quyết định.

### 23.5. Đáp án tham khảo: guardrails

| Lĩnh vực | Điều không được đánh đổi | Bằng chứng |
| --- | --- | --- |
| **Quyền học** | PENDING không được mở nội dung hạn chế theo quy tắc đã xác nhận | API/security integration tests |
| **Tiến độ** | Học viên đủ điều kiện không bị mở sai bài hoặc ghi lùi dữ liệu | Acceptance examples, integration tests |
| **DoD** | Increment phải đạt tiêu chuẩn chất lượng chung | CI, review, kiểm tra bắt buộc |
| **Dữ liệu cá nhân** | Không tự dùng dữ liệu cho mục đích gợi ý khi chưa được đánh giá hợp lệ | Bản ghi quyết định với người có thẩm quyền |
| **Rollout** | Không mở rộng khi guardrail xấu hoặc thiếu khả năng kiểm soát | Feature flag/cohort, telemetry, phương án ứng phó |
| **Chi phí/thời gian** | Không tự vượt giới hạn hoặc bù bằng làm thêm giờ kéo dài | Dự báo, phạm vi chia lát, escalation sớm |

### 23.6. Đáp án tham khảo: Gherkin và tầng kiểm thử

~~~gherkin
Feature: Tiếp tục học trong phạm vi được phép

  Scenario: Học viên ACTIVE mở đúng bài tiếp theo
    Given học viên có đăng ký ACTIVE và đủ điều kiện
    And khóa tuyến tính có ba bài
    And học viên đã hoàn tất bài một
    When học viên yêu cầu tiếp tục học
    Then hệ thống cho phép mở bài hai

  Scenario: Người PENDING không được cấp quyền nội dung hạn chế
    Given học viên đã gửi yêu cầu ghi danh và đang PENDING
    When học viên gửi yêu cầu API trực tiếp mở bài hạn chế
    Then hệ thống từ chối cấp nội dung
    And không tiết lộ dữ liệu tiến độ riêng của người khác

  Scenario: Không có bài sau khi đã hoàn tất khóa
    Given học viên ACTIVE và đã hoàn thành cả ba bài
    When học viên mở trang khóa
    Then hệ thống hiển thị trạng thái hoàn thành
    And không tạo liên kết đến bài thứ tư
~~~

Quy tắc chọn bài thuần có thể dùng **unit tests**. Quyền mở bài cần có **API/security integration tests** vì chỉ ẩn nút UI không chặn request trực tiếp. Hành trình giao diện cần một số **end-to-end tests** trọng yếu. Nếu dữ liệu cập nhật giữa hai thiết bị, cần thêm kiểm thử tích hợp cho sự nhất quán theo hợp đồng.

### 23.7. Đáp án tham khảo: đo lường và giải trình

Một **outcome metric** có thể là:

~~~text
Tỷ lệ tiếp tục học thành công
  = Số học viên đủ điều kiện mở đúng bài tiếp theo trong cửa sổ
    / Tổng số học viên đủ điều kiện quay lại cần tiếp tục học
    × 100%
~~~

Một **guardrail** là số trường hợp **cấp quyền trái quy tắc được xác nhận** và tín hiệu rủi ro quyền. Với rủi ro nghiêm trọng, phải xử lý theo quy trình ngay, không chỉ chờ báo cáo cuối kỳ. Có thể theo dõi thêm **lead time từ PBI được nhận đến availability** hoặc **lỗi tiến độ**, nhưng cần mô tả ranh giới và cách đo.

**Báo cáo sau Sprint:** nêu Sprint Goal, Increment đạt DoD, phạm vi đã/ chưa cung cấp, cohort dùng được, dữ liệu người học, lỗi/guardrail, quyết định thay đổi scope và việc tiếp theo. Đừng chỉ trình bày số story point hoặc phần trăm task hoàn thành.

### 23.8. Đáp án tham khảo: xử lý áp lực và cải tiến

**Mọi PR có chữ ký quản lý:** thay vì mặc định bắt buộc, phân tích sự cố trước đó và xem yêu cầu thực tế là bảo vệ rủi ro nào. Có thể đặt **review theo chuyên môn, contract/security tests và điều kiện escalated cho thay đổi rủi ro cao**; người quản lý chỉ chốt những điều vượt ranh giới đã trao. Nếu tổ chức đã có chính sách bắt buộc, nhóm phải thực hiện và đề xuất sửa qua thẩm quyền đúng.

**Cảnh báo từ tester:** xác minh lập tức, giới hạn rollout nếu cần, áp dụng kiểm thử API và quyền, báo người trực sự cố hoặc người có thẩm quyền an toàn; không đợi Retrospective. Người nêu rủi ro không bị coi là cản tiến độ.

**Gợi ý AI giữa Sprint:** xem nó giúp Product Goal thế nào, dữ liệu có quyền sử dụng chưa, mức bất định và tác động tới Sprint Goal. Product Owner làm rõ thứ tự backlog; Developers đánh giá phương án và khả năng triển khai; không âm thầm đổi Sprint Goal hoặc bỏ DoD.

**Action Retrospective:** “Trong hai Sprint tới, với story liên quan quyền và trạng thái đăng ký, thử Three Amigos ngắn trước khi vào In Progress; một Developer đầu mối theo dõi cùng PO và tester. Xem lại số câu hỏi nghiệp vụ đến muộn, lỗi quyền và thời gian chuẩn bị; chỉ giữ nếu cải thiện mà không tăng ma sát quá mức”. Đây là **thử nghiệm có thể kiểm chứng**, không chỉ khẩu hiệu “giao tiếp tốt hơn”.

## 24. Mẫu thỏa thuận tự chủ và giải trình cho nhóm

Nhóm có thể dùng một bản **Team Charter hoặc Working Agreement** ngắn để kết nối giá trị với quyền quyết định. Không nhất thiết tạo thêm một tài liệu dài nếu những thông tin này đã nằm ở nơi khác và dễ truy cập.

~~~text
Tên nhóm / sản phẩm:
Product Goal và người dùng mục tiêu:
Sprint Goal hoặc mục tiêu luồng hiện tại:

Kết quả cần tạo và bằng chứng:
  - Outcome / mẫu số / cohort / cửa sổ đo:
  - Increment / acceptance criteria:
  - Rủi ro chưa biết và giả thuyết cần kiểm tra:

Quyền tự chủ:
  - Những quyết định Developers / nhóm được tự chọn:
  - Những việc phải tham vấn Product Owner / stakeholder:
  - Những quyết định cần security/privacy/finance/ops phê duyệt:

Guardrails:
  - Definition of Done:
  - Quyền học và bảo vệ dữ liệu:
  - Hợp đồng API / chất lượng / vận hành:
  - Ngân sách / thời hạn / nghĩa vụ:

Minh bạch và phối hợp:
  - Product/Sprint Backlog và board:
  - Decision log, owner, thời điểm phản hồi:
  - Escalation khi có blocker hoặc nguy cơ:
  - Phương án rollout, phát hiện lỗi và khôi phục:

Nhịp kiểm tra và thích ứng:
  - Khi nào xem outcome, flow và guardrail:
  - Ai có thẩm quyền quyết định thay đổi phạm vi:
  - Khi nào xem lại ranh giới tự chủ:
~~~

### Cách sử dụng bản thỏa thuận

1. **Cùng soạn và cùng hiểu:** Product Owner, Developers, Scrum Master và các bên có thẩm quyền cần đóng góp đúng phạm vi.
2. **Bắt đầu tối giản:** chỉ ghi những quyền/rủi ro thường gây chờ hoặc hiểu nhầm.
3. **Dùng trong quyết định thật:** khi một PBI cần đổi scope, tham chiếu ma trận quyền và guardrail.
4. **Xem lại bằng bằng chứng:** nếu thỏa thuận tạo hàng đợi thừa hoặc bỏ sót rủi ro, đề xuất điều chỉnh.
5. **Giữ trách nhiệm pháp lý/tổ chức:** bản Team Charter không tự thay thế hợp đồng hoặc chính sách bắt buộc.

## 25. Checklist liên kết tự chủ với mục tiêu và trách nhiệm giải trình

- [ ] Nhóm hiểu **người dùng, vấn đề, Product Goal** và giá trị cần tạo?
- [ ] Sprint Goal hoặc mục tiêu luồng được mô tả bằng **kết quả**, không chỉ danh sách task?
- [ ] Có phân biệt **autonomy, authority, responsibility và accountability**?
- [ ] Scrum Team tự quản cách làm trong phạm vi, nhưng các **accountability của PO/Developers/SM** vẫn rõ?
- [ ] Những quyết định **nhóm tự làm, phải tham vấn và cần phê duyệt** đã được giải thích?
- [ ] Ranh giới quyền quyết định dựa trên **rủi ro, tác động, tính đảo ngược và thẩm quyền**?
- [ ] Có guardrail cụ thể về **DoD, quyền truy cập, dữ liệu, API, vận hành và ngân sách**?
- [ ] Guardrail có **bằng chứng kiểm tra và đường hành động** khi bị vi phạm?
- [ ] Những quy tắc nghiệp vụ mơ hồ được người có thẩm quyền làm rõ trước khi code?
- [ ] User stories được chia thành **lát có giá trị, sử dụng được và đạt DoD**, không chỉ task kỹ thuật?
- [ ] Acceptance criteria phản ánh **hành vi có thể quan sát**, gồm cả trường hợp rủi ro?
- [ ] Người ngoài nhóm có thể hiểu **quyết định, lý do, rủi ro và điều chưa chắc chắn** qua bản ghi thích hợp?
- [ ] Có cơ chế **escalation** khi thay đổi vượt quyền hoặc có rủi ro khẩn?
- [ ] Không chờ sự kiện Scrum định kỳ mới phản ứng với **sự cố bảo mật, mất dữ liệu hoặc gián đoạn lớn**?
- [ ] Các phụ thuộc liên nhóm có **owner, hợp đồng và thời hạn phản hồi** minh bạch?
- [ ] Báo cáo kết quả xem **outcome + flow + quality/guardrails**, không chỉ velocity/story points?
- [ ] Lead time/cycle time có **ranh giới đo** nhất quán để không làm số đẹp giả?
- [ ] Forecast nêu **độ bất định, phụ thuộc và trade-off**, không hứa chắc khi thiếu dữ liệu?
- [ ] Deadline được xử lý bằng **chia phạm vi và phối hợp**, không bằng bỏ DoD hoặc làm thêm giờ vô hạn?
- [ ] Stakeholder có cơ hội cung cấp bằng chứng và phản hồi đúng lúc nhưng không **điều khiển task tùy hứng**?
- [ ] Lãnh đạo trao quyền đi cùng **thông tin, hỗ trợ và khả năng tháo blocker**?
- [ ] Khi có lỗi, nhóm giải trình bằng **sự kiện, tác động, quyết định và hành động phòng ngừa**, không công kích cá nhân?
- [ ] Scrum, Kanban, XP và Lean được dùng để **học hỏi và cải tiến dòng giá trị**, không chỉ đổi nghi thức?
- [ ] Ranh giới tự chủ và các chính sách có được **xem lại khi dữ liệu hoặc bối cảnh thay đổi**?
- [ ] Sau khi giao Increment, nhóm vẫn theo dõi **người dùng thực sự nhận giá trị và rủi ro có nằm trong giới hạn**?

**Ghi nhớ:** **Tự chủ của nhóm chỉ tạo giá trị khi đi cùng định hướng, giới hạn rõ ràng và trách nhiệm giải trình có bằng chứng.** Product Goal và Sprint Goal giúp nhóm hiểu *vì sao* cần hành động; quyền quyết định và guardrail giúp nhóm biết *được tự lựa chọn đến đâu*; Definition of Done, phản hồi người dùng và các chỉ số outcome–flow–quality giúp kiểm tra *kết quả có thực sự tốt hay không*. Khi các yếu tố ấy hoạt động cùng nhau, Scrum Team có thể chọn cách xây sản phẩm linh hoạt, phối hợp ngang hàng, xử lý rủi ro sớm và cải tiến liên tục **mà không cần đánh đổi sự an toàn, chất lượng hoặc niềm tin của người dùng**.
