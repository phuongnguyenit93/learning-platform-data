# Phân biệt mục tiêu dài hạn với kế hoạch chi tiết ngắn hạn

## 1. Vì sao Agile cần cả định hướng dài hạn lẫn kế hoạch gần?

Một nhóm phát triển phần mềm phải biết **mình đang hướng đến kết quả nào** để lựa chọn công việc có ý nghĩa. Đồng thời, nhóm phải biết **sẽ làm gì trong những ngày hoặc tuần sắp tới** để phối hợp, kiểm thử và bàn giao phần mềm. Vấn đề xuất hiện khi tổ chức biến danh sách công việc dự kiến cho nhiều tháng thành một kế hoạch chi tiết bất biến, trong khi nhu cầu người dùng và hiểu biết kỹ thuật còn thay đổi.

Giả sử một nền tảng học trực tuyến đặt mục tiêu: “Trong hai quý tới, giúp nhiều học viên mới học tiếp đến bài thứ ba thay vì bỏ dở sau bài đầu”. Đó là **định hướng dài hạn gắn với giá trị**. Để tiến gần mục tiêu, nhóm có thể bắt đầu bằng việc quan sát hành trình học, kiểm tra khó khăn tìm bài tiếp theo và triển khai một lát cải thiện điều hướng trong đợt gần nhất. Đó là **kế hoạch chi tiết ngắn hạn**, được lập bằng những điều hiện đã đủ hiểu.

Nếu nhóm cam kết ngay từ đầu rằng “tháng thứ nhất làm hệ thống huy hiệu, tháng thứ hai làm nhắc học, tháng thứ ba làm bảng xếp hạng” mà chưa kiểm chứng nguyên nhân bỏ dở, kế hoạch có vẻ chắc chắn nhưng có thể không giúp đạt mục tiêu. Ngược lại, nếu chỉ phản ứng với từng ticket phát sinh mà không có hướng đi dài hạn, nhóm dễ hoàn tất nhiều việc rời rạc nhưng không tạo ra tác động đáng kể.

**Lập kế hoạch thích ứng (adaptive planning)** kết hợp hai nhu cầu:

- **Giữ rõ mục tiêu và ràng buộc quan trọng:** biết người hưởng lợi, kết quả cần tạo, tiêu chuẩn chất lượng và các giới hạn về ngân sách, thời gian hoặc pháp lý.
- **Chi tiết hóa công việc khi đã gần thời điểm thực hiện:** chỉ cam kết mức thông tin có thể kiểm chứng; dùng phản hồi từ phần mềm hoạt động thật để điều chỉnh các bước tiếp theo.

Đây là một cách đưa các giá trị Agile vào thực tế: **bàn giao tăng dần, học từ phản hồi sớm và cải tiến liên tục**. Agile không khuyến khích bỏ kế hoạch; Agile khuyến khích lập kế hoạch nhiều lần với **độ chi tiết tương xứng mức hiểu biết**.

> **Câu hỏi trung tâm:** “Mục tiêu nào cần giữ để định hướng quyết định, và phần kế hoạch nào cần được xem lại khi thực tế cung cấp bằng chứng mới?”

## 2. Mục tiêu, chiến lược, dự báo và kế hoạch khác nhau thế nào?

Các từ “mục tiêu”, “roadmap”, “cam kết” và “kế hoạch” đôi khi bị dùng thay thế cho nhau. Cần phân biệt để các bên hiểu đúng điều nhóm có thể bảo đảm và điều vẫn là giả thuyết.

| Khái niệm | Trả lời câu hỏi | Ví dụ trong nền tảng học |
| --- | --- | --- |
| **Mục tiêu (goal/outcome)** | Muốn cải thiện điều gì, cho ai, vì sao? | Tăng tỷ lệ học viên mở bài thứ ba trong 30 ngày kể từ khi bắt đầu khóa |
| **Chiến lược/giả thuyết** | Cơ hội hoặc hướng tiếp cận nào được tin là có ích? | Giảm khó khăn khi quay lại học có thể cải thiện khả năng tiếp tục |
| **Roadmap/định hướng triển khai** | Những vấn đề hoặc khả năng nào có thể được ưu tiên theo giai đoạn? | Trước mắt làm rõ hành trình quay lại; tiếp theo xem vấn đề độ dài bài; về sau cân nhắc nhắc học |
| **Dự báo (forecast)** | Dựa trên dữ liệu hiện tại, khả năng đạt mốc/thời hạn ra sao? | Với luồng công việc đang quan sát, khoảng thời gian hoàn tất các lát dự kiến có thể dao động |
| **Kế hoạch ngắn hạn (plan)** | Ai sẽ phối hợp làm bước nào, kiểm tra ra sao, điều kiện Done là gì? | Trong chu kỳ gần nhất, làm rõ story, sửa nút “Tiếp tục học”, kiểm thử quyền và phát hành giới hạn |
| **Cam kết (commitment)** | Nhóm nhận trách nhiệm đối với mục tiêu, quy tắc hoặc nghĩa vụ nào? | Cùng hướng tới Sprint Goal, tuân thủ Definition of Done và báo rủi ro sớm |

**Mục tiêu** thường ổn định hơn kế hoạch triển khai, nhưng không phải không bao giờ thay đổi. Nếu dữ liệu cho thấy mục tiêu sai, hoàn cảnh pháp lý thay đổi hoặc chiến lược kinh doanh chuyển hướng, người có trách nhiệm phải xem lại mục tiêu một cách minh bạch.

**Dự báo** khác **lời hứa chắc chắn**. Dự báo có điều kiện: nó dựa vào những giả định về năng lực, độ lớn công việc, mức độ gián đoạn và chất lượng dữ liệu. Cần nói rõ những giả định đó, nhất là khi giao tiếp với người ra quyết định đầu tư.

**Cam kết** trong Scrum có nghĩa cụ thể ở từng artifact: Product Goal cho Product Backlog, Sprint Goal cho Sprint Backlog và Definition of Done cho Increment. Không nên đồng nhất cam kết với “mọi ticket đã ước lượng bắt buộc phải hoàn thành bất kể điều kiện thay đổi”.

## 3. Các chân trời kế hoạch: càng xa càng cần linh hoạt

Lập kế hoạch theo nhiều chân trời thường được gọi là **rolling-wave planning** hoặc **progressive elaboration**: phạm vi gần có thể mô tả rõ, phạm vi xa thường chỉ có hướng đi, lựa chọn và giả thuyết. Độ dài mỗi chân trời thay đổi tùy sản phẩm, rủi ro và cách tổ chức; không có lịch chung bắt buộc cho mọi đội Agile.

| Chân trời | Mức chi tiết hữu ích | Người/cơ chế thường tham gia | Nhịp xem lại gợi ý |
| --- | --- | --- | --- |
| **Tầm nhìn sản phẩm** | Người dùng được phục vụ, vấn đề nền tảng, tác động mong muốn | Lãnh đạo sản phẩm, stakeholder và nhóm xây dựng | Khi có thay đổi lớn hoặc bằng chứng chiến lược |
| **Mục tiêu sản phẩm/giai đoạn** | Outcome có cách đo, ràng buộc và điều kiện thành công | Product Owner/người phụ trách sản phẩm cùng nhóm | Mỗi khi có đủ bằng chứng giá trị; có thể theo tháng/quý |
| **Roadmap/đợt ưu tiên** | Chủ đề, vấn đề, thứ tự tương đối, phụ thuộc quan trọng | Người làm sản phẩm, thiết kế, kỹ thuật, vận hành | Thường xuyên theo biến động và kết quả |
| **Backlog gần** | User story đủ hiểu, tiêu chí chấp nhận, rủi ro và thứ tự | Product Owner, Developers, người hiểu nghiệp vụ | Refinement liên tục |
| **Sprint hoặc luồng thực hiện ngắn** | Mục tiêu gần, lát công việc được chọn, kế hoạch kiểm thử và tích hợp | Scrum Team hoặc nhóm quản lý flow | Theo Sprint hoặc nhịp replenishment của Kanban |
| **Ngày làm việc hiện tại** | Bước phối hợp cụ thể, trở ngại, ai cần hỗ trợ | Những người trực tiếp thực hiện | Khi công việc/bằng chứng thay đổi |

Đây là **một mô hình giúp suy nghĩ**, không phải sáu tầng tài liệu bắt buộc. Nhóm nhỏ có thể duy trì một trang mục tiêu, một Product Backlog và một bảng làm việc. Điều quan trọng là luôn biết ở cấp nào mình **đang nói về kết quả**, ở cấp nào mình **đang nói về phương án hoặc bước thực hiện**.

### Hình dung mối liên hệ giữa các cấp

~~~mermaid
flowchart TD
    A["Tầm nhìn: Giúp người học duy trì tiến bộ"] --> B["Mục tiêu dài hạn: Nhiều học viên học tiếp đến bài 3"]
    B --> C["Roadmap: Cơ hội và các giả thuyết ưu tiên"]
    C --> D["Backlog: Lát giá trị cần làm rõ"]
    D --> E["Kế hoạch ngắn hạn: Chọn mục tiêu gần và việc có thể hoàn tất"]
    E --> F["Increment đạt chuẩn, phát hành phù hợp"]
    F --> G["Phản hồi người dùng + chất lượng + dòng công việc"]
    G -->|Điều chỉnh ưu tiên| C
    G -->|Làm rõ story| D
    G -->|Bằng chứng chiến lược quan trọng| B
~~~

Mô hình này giải thích vì sao kế hoạch gần cần cụ thể để làm việc, còn kế hoạch xa nên thể hiện **khả năng thích ứng**, không chỉ là danh sách tính năng được phân tháng.

## 4. Xây dựng mục tiêu dài hạn có ích cho quyết định

Một mục tiêu dài hạn giúp nhóm **ưu tiên giữa nhiều việc đều có vẻ tốt**. Nếu mục tiêu chỉ là “phát triển sản phẩm tốt hơn” hoặc “làm 20 tính năng”, nhóm khó quyết định nên làm gì khi có phản hồi mới.

Một mục tiêu đủ rõ thường có các yếu tố:

1. **Đối tượng:** ai nhận lợi ích hoặc ai đang gặp vấn đề?
2. **Outcome mong muốn:** hành vi, khả năng hoặc kết quả nào cần thay đổi?
3. **Bằng chứng/đo lường:** làm sao biết đang tiến gần mục tiêu?
4. **Chân trời thời gian:** khi nào nên xem kết quả và quyết định lại?
5. **Ràng buộc bảo vệ:** tiêu chuẩn chất lượng, dữ liệu, ngân sách, an toàn, pháp lý nào phải giữ?

**Ví dụ minh họa (số liệu giả định):** Trong 2 quý tới, nhóm muốn nâng tỷ lệ học viên mới mở bài thứ ba trong vòng 30 ngày từ khoảng **28% lên 40%**, với điều kiện tỷ lệ lỗi truy cập không tăng và quyền học vẫn được kiểm soát đúng. Những tỷ lệ này chỉ là số để minh họa cách viết mục tiêu; trong sản phẩm thật cần xác nhận nền dữ liệu, định nghĩa người học, tập đủ điều kiện và mức cải thiện khả thi.

Mục tiêu trên **không chỉ định** phải làm hệ thống huy hiệu, thông báo hay thuật toán gợi ý. Nó mở đường cho nhiều phương án và cho phép nhóm đổi thứ tự sau khi có bằng chứng.

### Outcome khác output

| Output có thể hoàn tất | Outcome cần kiểm chứng |
| --- | --- |
| Đã thêm nút “Tiếp tục học” | Nhiều học viên quay lại đúng bài và tiếp tục học |
| Đã phát hành chức năng nhắc học | Học viên có chọn nhận nhắc và thực sự học tiếp không? |
| Đã đóng 15 user story | Người dùng có hoàn thành hành trình quan trọng nhanh, đúng và an toàn hơn không? |
| Đã triển khai 20 lần | Chất lượng và giá trị sản phẩm có được cải thiện bền vững không? |

Output phản ánh công việc sản xuất; outcome phản ánh điều **thay đổi đối với người sử dụng**. Đôi khi kết quả có độ trễ hoặc bị ảnh hưởng bởi nhiều yếu tố bên ngoài. Nhóm nên phối hợp dữ liệu định lượng với quan sát định tính để tránh gán mọi thay đổi cho một tính năng đơn lẻ.

### Để mục tiêu hướng dẫn mà không trói buộc

Một mục tiêu dài hạn hữu ích cần được nhắc lại khi:

- Chọn giữa các epic và user story cạnh tranh nhau.
- Xử lý yêu cầu phát sinh từ stakeholder.
- Đánh giá có nên đầu tư làm tiếp giải pháp hiện tại.
- Cân nhắc khoản nợ kỹ thuật ảnh hưởng đến tốc độ thử nghiệm và chất lượng dài hạn.
- Thảo luận có nên đổi hướng do bối cảnh thay đổi.

Mục tiêu có thể đi kèm **guardrail**: ví dụ “tăng khả năng quay lại học nhưng không gửi thông báo khi người dùng chưa đồng ý nhận”, hoặc “giảm thời gian đăng ký nhưng không bỏ kiểm soát bảo mật”. Một quyết định đạt chỉ số tăng trưởng mà vi phạm ràng buộc quan trọng không phải thành công.

## 5. Lập kế hoạch chi tiết ngắn hạn: biến định hướng thành increment

Trong chân trời gần, nhóm cần đủ chi tiết để **cùng thực hiện, phát hiện phụ thuộc, kiểm thử và hoàn tất một lát sản phẩm có giá trị**. Những câu hỏi hữu ích là:

- Kết quả gần nhất giúp kiểm chứng mục tiêu dài hạn là gì?
- Story/lát giá trị nào có thể hoàn thành trọn vẹn trong nhịp thực hiện hiện tại?
- Các tiêu chí chấp nhận, Definition of Done và ràng buộc nào áp dụng?
- Có điều chưa biết nào cần nghiên cứu/spike trước hoặc trong khi làm?
- Nhóm có năng lực thực tế bao nhiêu sau khi tính việc hỗ trợ, nghỉ phép và sự cố?
- Cần phối hợp với ai, phụ thuộc nào có nguy cơ chặn bàn giao?
- Khi nào và bằng cách nào sẽ lấy phản hồi sau khi hoàn tất?

Ví dụ, thay vì ghi “tuần này làm giao diện học, API, database”, nhóm xác định một lát:

> “Học viên đã hoàn tất bài đầu có thể mở đúng bài tiếp theo từ trang khóa học, bao gồm kiểm tra quyền truy cập và xử lý trường hợp không có bài tiếp.”

Đây là một kết quả có thể trình diễn và kiểm thử từ đầu đến cuối. Nhóm vẫn có thể chia thành task thiết kế, API, dữ liệu, kiểm thử tích hợp; nhưng **hoàn tất task riêng lẻ chưa đồng nghĩa increment đã sẵn sàng**.

### Tiêu chí chấp nhận minh họa

~~~gherkin
Feature: Tiếp tục học từ bài tiếp theo

  Scenario: Học viên có bài tiếp theo hợp lệ
    Given học viên đã đăng nhập và có quyền học khóa
    And bài đầu đã được ghi nhận hoàn tất theo quy tắc
    When học viên mở trang chi tiết khóa
    Then hệ thống hiển thị hành động "Tiếp tục học"
    And khi chọn, học viên được mở đúng bài tiếp theo

  Scenario: Học viên không có quyền học
    Given người dùng không có quyền truy cập khóa
    When người dùng gửi liên kết trực tiếp đến bài tiếp theo
    Then hệ thống từ chối truy cập nội dung bị hạn chế

  Scenario: Không còn bài tiếp theo
    Given học viên đã hoàn tất bài cuối theo quy tắc khóa
    When học viên mở trang chi tiết khóa
    Then hệ thống không điều hướng đến một bài không tồn tại
    And hiển thị trạng thái hoàn tất phù hợp
~~~

Những điều kiện trên phải được xác nhận theo chính sách của sản phẩm thật. Tiêu chí chấp nhận mô tả **hành vi**; Definition of Done còn bao gồm mức chất lượng chung như kiểm thử, review, tích hợp, bảo vệ dữ liệu và khả năng triển khai/vận hành.

### Chi tiết đúng lúc (just-in-time elaboration)

Một Product Backlog có thể gồm những ý tưởng xa chưa biết chính xác cách làm. Khi một hạng mục gần được thực hiện, nhóm tinh chỉnh: chia nhỏ epic, trao đổi user story, bổ sung ví dụ nghiệp vụ, nhận diện phụ thuộc và ước lượng hoặc dự báo hợp lý.

Việc làm rõ không bắt buộc phải đợi một cuộc họp cố định. Nhóm có thể trao đổi trong refinement, trước Sprint Planning hoặc trong lúc thực hiện khi phát hiện tình huống mới. **Chi tiết đúng lúc** không phải bỏ qua phân tích cần thiết; nó là cách dành công sức làm rõ cho hạng mục có khả năng sắp được thực hiện.

## 6. Ví dụ xuyên suốt: mục tiêu hai quý, các kế hoạch gần liên tiếp

### 6.1. Bối cảnh và mục tiêu

Giả sử một nền tảng học lập trình muốn cải thiện tình trạng bỏ dở ở giai đoạn đầu khóa. Nhóm có dữ liệu ban đầu cho thấy nhiều người học xong bài thứ nhất nhưng ít người quay lại trong tuần tiếp theo. Product Owner và nhóm đặt mục tiêu hướng tới **tăng tỷ lệ học đến bài thứ ba trong 30 ngày** trong hai quý, trong khi vẫn bảo đảm phân quyền và trải nghiệm học ổn định.

Nhóm chưa biết chính xác nguyên nhân bỏ dở. Có thể do khó tìm bài, bài quá dài, thời gian học không phù hợp hoặc thiếu giá trị cảm nhận. Vì vậy, roadmap ban đầu mô tả **vấn đề cần giải quyết và giả thuyết để kiểm chứng**.

| Chân trời | Nội dung minh họa | Mức độ chắc chắn |
| --- | --- | --- |
| **Hai quý** | Cải thiện tỷ lệ người học tiếp đến bài thứ ba, dựa trên định nghĩa đã thống nhất | Mục tiêu định hướng và ngưỡng kỳ vọng, không bảo đảm đạt |
| **Giai đoạn gần** | Hiểu rào cản quay lại học, thử cải thiện điều hướng | Có tín hiệu ban đầu nhưng cần kiểm chứng |
| **Các giai đoạn sau** | Cân nhắc chia bài thành phần ngắn, nhắc học tự chọn hoặc cá nhân hóa | Phương án ứng viên, thứ tự sẽ thay đổi theo bằng chứng |
| **Một chu kỳ ngắn** | Hoàn thành lát “Tiếp tục học”, kiểm thử và cho nhóm người dùng phù hợp thử | Đủ rõ để lập kế hoạch thực hiện |
| **Hằng ngày** | Phối hợp UI–API–kiểm thử, xử lý blocker và giữ increment tích hợp | Cụ thể nhưng vẫn điều chỉnh nếu có trở ngại |

### 6.2. Vòng thứ nhất: kiểm chứng giả thuyết “khó tìm bài tiếp theo”

Nhóm quan sát một số phiên học, kiểm tra funnel và phỏng vấn những người bỏ dở. Họ thấy vài học viên mất thời gian tìm bài kế tiếp. Đây là **tín hiệu để thử**; mẫu nhỏ chưa chứng minh đó là nguyên nhân chính của toàn bộ người học.

Nhóm chọn lát nhỏ “Tiếp tục học” trên trang khóa. Trong chu kỳ thực hiện gần, Developers thống nhất công việc cần để có một increment hoàn chỉnh: lấy trạng thái tiến độ thật, kiểm tra quyền, điều hướng, kiểm thử trường hợp biên và theo dõi lỗi.

Sau khi đạt DoD, nhóm phát hành giới hạn theo cơ chế phù hợp, thu thập dữ liệu người dùng được phép tham gia. Nhóm đo **tỷ lệ mở bài tiếp theo** và theo dõi lỗi phân quyền, thay vì chỉ kiểm tra nút có được nhấn hay không.

### 6.3. Vòng thứ hai: điều chỉnh khi phát hiện vấn đề mới

Giả sử người dùng thử dễ tìm bài tiếp theo hơn, nhưng nhiều người vẫn không tiếp tục vì **bài thứ hai quá dài**. Thông tin này khiến nhóm thay đổi thứ tự ưu tiên: thay vì xây ngay hệ thống huy hiệu, nhóm thảo luận thử chia một bài dài thành các phần có thể hoàn tất trong thời gian ngắn hơn.

Việc đổi giải pháp **không đồng nghĩa mục tiêu hai quý đã thất bại**. Mục tiêu vẫn là giúp học viên tiếp tục học; điều cần thích ứng là giả thuyết về cách đạt mục tiêu.

Nếu sau nhiều lần thử có bằng chứng rõ rằng chỉ số “mở bài ba” không phản ánh học tập có ý nghĩa, nhóm còn phải xem lại **cách đo mục tiêu**, ví dụ kết hợp mức hiểu bài, tỷ lệ hoàn thành hay phản hồi định tính. Thay đổi mục tiêu/định nghĩa phải được thống nhất công khai, không sửa số sau khi đã thấy kết quả chỉ để báo cáo đẹp hơn.

### 6.4. Một quyết định ưu tiên có thể được trình bày minh bạch

~~~text
Mục tiêu: Giúp học viên mới tiến xa hơn trong khóa nhập môn
Bằng chứng mới: Nhiều người tìm được bài 2 nhưng chưa bắt đầu học
Giả thuyết cần thử: Bài 2 quá dài so với quỹ thời gian phổ biến
Lựa chọn:
  A. Xây hệ thống huy hiệu toàn khóa
  B. Chia một bài dài thành các phần ngắn và đo kết quả
  C. Giữ nguyên, nghiên cứu thêm hành vi bỏ dở
Quyết định hiện tại: Thử B ở phạm vi nhỏ nếu đã xác nhận nguyên tắc sư phạm
Tiêu chí: Người học hoàn tất phần đầu dễ hơn, không giảm chất lượng học
Guardrail: Không mất tiến độ, không cấp quyền sai, không làm sai đánh giá
Mốc xem lại: Sau một đợt dùng thử đủ dữ liệu theo thiết kế đo đã thống nhất
~~~

Cách ghi ngắn này giúp stakeholder hiểu **vì sao roadmap được đổi**, nhóm sẽ biết gì sau bước tiếp theo và điều gì vẫn chưa chắc chắn.

## 7. Thích ứng kế hoạch trong Scrum

Scrum là một framework thực nghiệm với các artifact, sự kiện và cam kết rõ ràng. Việc phân biệt chân trời dài và ngắn trong Scrum đặc biệt dễ thấy qua ba tầng:

| Tầng | Vai trò trong Scrum | Điều cần thích ứng |
| --- | --- | --- |
| **Product Goal** | Mục tiêu dài hạn cho Scrum Team, được mô tả trong Product Backlog | Phản ánh trạng thái tương lai có giá trị; mục tiêu mới được chọn theo chiến lược và bằng chứng |
| **Product Backlog** | Danh sách công việc cần thiết để cải thiện sản phẩm, được sắp thứ tự và có tính phát sinh | Hạng mục được thêm, bớt, làm rõ, chia nhỏ và ưu tiên lại |
| **Sprint Goal** | Mục tiêu duy nhất của Sprint, tạo sự tập trung và linh hoạt về công việc cần làm | Hướng dẫn thay đổi kế hoạch khi nhóm học thêm hoặc gặp trở ngại |
| **Sprint Backlog** | Sprint Goal, các PBI được chọn và kế hoạch hành động của Developers | Developers cập nhật trong Sprint khi hiểu thêm về công việc |

Một Sprint có độ dài cố định **không quá một tháng** theo Scrum Guide. Nhóm chọn độ dài phù hợp để kiểm tra và thích ứng thường xuyên. Sprint Goal tạo hướng đi cho Sprint, còn **phạm vi chi tiết được làm rõ và thương lượng** khi nhóm học thêm. Trong Sprint, thay đổi không được làm phương hại Sprint Goal; chất lượng không bị giảm; phạm vi có thể được làm rõ và trao đổi lại với Product Owner khi biết thêm thông tin.

**Sprint Planning** giúp Scrum Team xác định vì sao Sprint có giá trị, điều gì có thể hoàn thành và cách Developers dự kiến thực hiện. **Daily Scrum** để Developers kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh kế hoạch. **Sprint Review** để cùng stakeholder xem kết quả, những thay đổi trong môi trường và hướng thích ứng Product Backlog. **Sprint Retrospective** để cải tiến chất lượng và hiệu quả cách làm.

### Tình huống thay đổi trong Sprint

Giả sử Sprint Goal là “giúp học viên trở lại đúng bài tiếp theo từ trang khóa”. Trong khi làm, nhóm phát hiện dữ liệu tiến độ từ thiết bị di động không đồng bộ như dự kiến. Developers có thể:

1. Đánh giá rủi ro mất tiến độ và phân quyền.
2. Trao đổi với Product Owner về một lát giải pháp vẫn giúp đạt Sprint Goal, nếu có.
3. Bỏ bớt một tiện ích phụ chưa cần trong Sprint, hoặc điều chỉnh các task và cách tích hợp.
4. Thông báo sớm nếu mục tiêu có nguy cơ không đạt; không che giấu bằng cách hạ DoD.

Đây là thích ứng có trách nhiệm. Ngược lại, tự ý đổi Sprint Goal sang một mục tiêu hoàn toàn khác chỉ vì stakeholder gửi ticket mới sẽ làm mất tính tập trung. Nếu Sprint Goal thực sự trở nên lỗi thời, Scrum có cơ chế xem xét hủy Sprint; trong Scrum, **chỉ Product Owner có thẩm quyền hủy Sprint**. Đây là trường hợp đặc biệt, không phải cách xử lý mỗi khi một task trễ.

## 8. Thích ứng kế hoạch trong Kanban và XP

Agile không yêu cầu mọi nhóm dùng Sprint để phân biệt kế hoạch dài và ngắn.

### Kanban: mục tiêu ổn định, dòng công việc được điều chỉnh liên tục

Nhóm dùng Kanban có thể giữ **mục tiêu sản phẩm hoặc outcome dài hạn**, duy trì danh sách hạng mục ưu tiên và kéo công việc theo năng lực thực tế. Thay vì lên kế hoạch chi tiết cố định cho cả tháng, nhóm có thể dùng nhịp **replenishment** để chọn việc mới và nhịp xem lại dịch vụ/dòng công việc để điều chỉnh chính sách.

Chẳng hạn:

- Mục tiêu giai đoạn: giảm thời gian xử lý yêu cầu hỗ trợ về học tập.
- Chính sách luồng: chỉ kéo story mới khi còn WIP cho phép; ưu tiên xử lý việc bị chặn lâu.
- Quyết định gần: xử lý trước một lát tra cứu trạng thái yêu cầu; điều chỉnh sau khi quan sát người dùng.

Các chỉ số như **Work in Progress (WIP)**, **throughput**, **cycle time** và **work item age** giúp nhìn ra công việc đang tắc và hỗ trợ dự báo. Khi phân tích, cần giữ định nghĩa điểm bắt đầu/kết thúc nhất quán, phân biệt loại việc nếu kích thước quá khác nhau và tránh dùng số ticket để xếp hạng cá nhân.

### XP: kỹ thuật tốt giúp kế hoạch có thể đổi an toàn

Các thực hành Extreme Programming (XP) như kiểm thử tự động, tích hợp liên tục, refactoring, làm việc cùng nhau và thiết kế đơn giản giúp nhóm **thay đổi phần mềm ít rủi ro hơn** khi phản hồi thay đổi. Nếu mỗi lần sửa chức năng đều phải chờ tích hợp nhiều tuần và kiểm thử thủ công một khối lớn, kế hoạch dù được gọi là Agile vẫn khó thích ứng.

Ví dụ, khi nhóm phát hiện cần thay cách xác định “bài tiếp theo”, bộ kiểm thử hồi quy và khả năng triển khai nhỏ giúp cập nhật quy tắc mà không làm hỏng việc học của người dùng hiện tại. Kế hoạch thích ứng vì vậy cần cả **cách ưu tiên linh hoạt** lẫn **năng lực kỹ thuật để thực thi thay đổi**.

## 9. Dự báo tiến độ mà không tạo cảm giác chắc chắn giả

Một trong những khó khăn thực tế là stakeholder cần biết **khi nào có kết quả**, trong khi nhóm chưa hiểu hết phạm vi. Phương án tốt là nêu rõ mốc chắc chắn, phần dự báo và giả định của dự báo.

### 9.1. Dùng dữ liệu thật thay cho ước lượng chính xác giả tạo

Giả sử một nhóm có throughput **4 hạng mục có kích thước tương tự mỗi tuần** trong một giai đoạn quan sát. Nếu backlog gần có **12 hạng mục tương tự**, phép chia sơ bộ cho kết quả **khoảng 3 tuần**.

~~~text
Thời lượng ước tính sơ bộ = 12 hạng mục / 4 hạng mục mỗi tuần
                         = khoảng 3 tuần
~~~

**Đây không phải lời hứa sẽ hoàn thành sau đúng ba tuần.** Thực tế có dao động: hạng mục khó hơn, sự cố phát sinh, người nghỉ phép, phụ thuộc và thời gian kiểm thử. Chỉ có giá trị khi định nghĩa “hạng mục hoàn tất” nhất quán, phạm vi tương đối ổn định và dữ liệu đủ đại diện. Nếu độ lớn hạng mục khác nhau nhiều, phép chia đơn giản rất dễ đánh lừa.

Với dữ liệu lịch sử đủ tốt, nhóm có thể dự báo theo **phân phối throughput/cycle time** (chẳng hạn mô phỏng Monte Carlo hoặc dùng các phân vị) để trình bày khoảng và mức tin cậy phù hợp. Không nên tự tạo phần trăm xác suất khi không có dữ liệu hoặc mô hình hỗ trợ.

### 9.2. Nói rõ loại thông tin khi công bố mốc

| Cách diễn đạt | Người nghe nên hiểu |
| --- | --- |
| “Mục tiêu quý này là tăng tỷ lệ hoàn thành bài học” | **Đích kết quả** để hướng tới và kiểm tra, không phải một tính năng cố định |
| “Đợt gần nhất nhóm sẽ thử lát Tiếp tục học” | **Kế hoạch thực hiện gần**, có phạm vi kiểm soát tốt hơn |
| “Dự báo hoàn tất từ khoảng ba đến năm tuần nếu không có thay đổi lớn” | **Ước lượng có điều kiện**, cần xem lại khi dữ liệu thay đổi |
| “Ngày 15 phải bảo đảm tuân thủ quy định bắt buộc” | **Ràng buộc thời hạn**, cần chủ động quản lý phạm vi, phụ thuộc và rủi ro |
| “Các khả năng B, C, D nằm ở cột Later của roadmap” | **Ứng viên tương lai**, chưa là cam kết ngày phát hành |

Ngày và tỷ lệ ở ví dụ trên chỉ để minh họa cách giao tiếp. Khi làm việc thật, cần ghi cụ thể **mốc nào bất biến vì nghĩa vụ**, mốc nào mới là kỳ vọng hiện thời, ai có quyền chốt và điều kiện nào khiến dự báo phải cập nhật.

### 9.3. Khi có ngày phát hành bắt buộc

Agile không loại bỏ các thời hạn bên ngoài: quy định pháp luật, hợp đồng, chương trình học theo kỳ hoặc sự kiện thị trường có thể tạo ngày phải đáp ứng. Khi ngày cố định, nhóm cần thảo luận sớm về **phạm vi tối thiểu an toàn và hữu ích**, năng lực, phụ thuộc và phương án dự phòng.

Ví dụ, hệ thống phải hỗ trợ tra cứu trạng thái đăng ký trước ngày khai giảng. Nhóm có thể ưu tiên:

1. Luồng tra cứu trạng thái cơ bản có xác thực và dữ liệu đúng.
2. Kiểm thử quyền, tình huống lỗi, giám sát và khả năng vận hành.
3. Các tiện ích không bắt buộc như lọc nâng cao, cá nhân hóa giao diện hoặc nhiều kênh thông báo để ưu tiên sau.

Nếu phạm vi, chất lượng và ngày đều bị cố định, nhóm phải báo **đánh đổi và rủi ro** sớm để người có thẩm quyền quyết định: tăng năng lực thực sự, thay đổi phạm vi/thoả thuận, hoặc điều chỉnh mốc theo quy trình phù hợp. Không nên hạ tiêu chuẩn bảo mật, dữ liệu hay kiểm thử bắt buộc chỉ để trông như đạt deadline.

## 10. Những tín hiệu cho thấy kế hoạch cần được xem lại

Lập kế hoạch thích ứng cần có **điều kiện kích hoạt xem lại**, không chỉ một lịch họp định kỳ. Ví dụ:

| Tín hiệu | Câu hỏi cần đặt | Phản ứng khả dĩ |
| --- | --- | --- |
| Người dùng không sử dụng tính năng mới | Vấn đề có thật? Có sai giả thuyết hoặc sai cách triển khai? | Phỏng vấn/quan sát, đổi thứ tự backlog, dừng mở rộng |
| Chỉ số outcome không cải thiện | Đã đo đúng? Thời gian đủ chưa? Có yếu tố bên ngoài? | Kiểm tra dữ liệu, giả định và phương án khác |
| Story thường kéo qua nhiều chu kỳ | Phạm vi quá lớn hay phụ thuộc nhiều? | Chia lát dọc nhỏ hơn, xử lý bottleneck, nâng chất lượng refinement |
| Số việc đang làm dở tăng liên tục | Đang bắt đầu quá nhiều và ít hoàn tất? | Giới hạn WIP, ưu tiên giúp việc hiện tại đạt Done |
| Tỷ lệ lỗi sau phát hành tăng | Có đánh đổi chất lượng để chạy theo tiến độ? | Cải thiện kiểm thử, CI, DoD, quy trình phát hành |
| Một tích hợp quan trọng bị trì hoãn | Còn lựa chọn thay thế? Ảnh hưởng goal/mốc bắt buộc? | Thử phương án ít phụ thuộc, đàm phán lại phạm vi/mốc |
| Quy định hoặc điều kiện kinh doanh thay đổi | Mục tiêu hiện tại còn hợp lệ? | Điều chỉnh ưu tiên, có thể xem lại cả mục tiêu dài hạn |

**Không phải mọi biến động nhỏ đều đòi đổi kế hoạch.** Nhóm cần đánh giá mức độ đáng tin của bằng chứng, độ lớn tác động, chi phí thay đổi và các rủi ro đối với người sử dụng. Thích ứng liên tục không đồng nghĩa đổi mục tiêu theo từng thông báo mới.

### Chuỗi ra quyết định minh họa

~~~mermaid
flowchart TD
    A["Nhận bằng chứng mới"] --> B{"Có ảnh hưởng đáng kể đến mục tiêu hoặc an toàn?"}
    B -->|"Không rõ"| C["Xác minh thêm, giữ kế hoạch có giám sát"]
    B -->|"Có"| D["Kiểm tra giả định và lựa chọn"]
    D --> E{"Chỉ cần đổi cách làm/phạm vi gần?"}
    E -->|"Có"| F["Điều chỉnh Sprint Backlog hoặc chính sách luồng phù hợp"]
    E -->|"Không"| G["Thảo luận đổi ưu tiên, roadmap hoặc mục tiêu với người chịu trách nhiệm"]
    C --> H["Tiếp tục quan sát"]
    F --> H
    G --> H
~~~

Một quyết định thay đổi kế hoạch nên có **ai quyết định, vì sao, điều gì thay đổi, tác động đến người liên quan và khi nào xem lại**. Việc ghi ngắn gọn này tránh để các nhóm hiểu một roadmap cũ là lời hứa vẫn còn nguyên hiệu lực.

## 11. Truyền đạt kế hoạch với stakeholder và giữ niềm tin

Thay đổi kế hoạch dễ bị hiểu thành “nhóm không giữ cam kết” nếu tổ chức chỉ thấy ngày và danh sách tính năng. Cách truyền đạt hữu ích là **nêu mục tiêu ổn định, bằng chứng thay đổi và lựa chọn thay thế**.

Ví dụ:

> “Mục tiêu của giai đoạn vẫn là giúp học viên quay lại và học tiếp. Kết quả thử cho thấy nút điều hướng giúp họ tìm bài nhanh hơn, nhưng nhiều người vẫn dừng vì bài thứ hai quá dài. Nhóm đề xuất ưu tiên thử chia nội dung bài trước khi đầu tư huy hiệu; dự báo cho nhóm tính năng huy hiệu vì vậy được xem lại. Chúng tôi sẽ đo tỷ lệ bắt đầu và hoàn tất phần học trong đợt thử sắp tới, đồng thời giữ các yêu cầu chất lượng hiện có.”

Thông báo như vậy làm rõ **điều đã học, điều sẽ làm và hệ quả với roadmap**. Nó tránh dùng “Agile nên đổi kế hoạch” như lý do chung chung mà không chứng minh quyết định dựa trên bằng chứng.

Một buổi cập nhật ngắn có thể trình bày:

- **Mục tiêu dài hạn và tiến triển outcome:** điều gì đang cải thiện, điều gì chưa và độ tin cậy của dữ liệu.
- **Increment gần nhất:** phần mềm nào đã đạt DoD, đang được thử với ai và có phản hồi gì.
- **Kế hoạch gần:** nhóm sẽ kiểm chứng giả thuyết hoặc bàn giao lát nào tiếp theo.
- **Rủi ro và phụ thuộc:** điều gì có thể ảnh hưởng mốc, cần ai quyết định.
- **Điều chỉnh so với dự báo cũ:** những lựa chọn bị trì hoãn, bỏ bớt hoặc ưu tiên cao hơn cùng lý do.

Khi trao đổi, hãy phân biệt quyết định đã được chốt với đề xuất còn đang xin ý kiến. Không dùng từ “chắc chắn giao” cho phần nhiều bất định hoặc chưa được tổ chức chấp nhận về phạm vi.

## 12. Những phản mẫu thường gặp

| Phản mẫu | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| **Kế hoạch năm liệt kê chi tiết từng ticket** | Nhiều giả định xa được xem như sự thật; tốn công duy trì | Giữ tầm nhìn/outcome dài hạn, chi tiết hóa backlog khi gần làm |
| **Chỉ có task tuần này, không biết mục tiêu sản phẩm** | Nhiều output rời rạc, khó lựa chọn ưu tiên | Liên kết story với outcome, Product Goal hoặc mục tiêu giai đoạn |
| **Roadmap là lịch phát hành cố định của mọi ý tưởng** | Stakeholder kỳ vọng sai; khó thích ứng khi phản hồi đổi | Gắn mức chắc chắn và điều kiện của mốc; định hướng theo vấn đề |
| **Chỉ đo velocity hoặc số ticket** | Có thể tăng sản lượng nhưng giá trị không tăng | Kết hợp outcome, chất lượng và số liệu luồng |
| **Đổi Sprint Goal mỗi khi có yêu cầu mới** | Mất tập trung và khó đánh giá Sprint | Dùng Sprint Goal để định hướng, đánh giá tác động và trao đổi phạm vi đúng trách nhiệm |
| **Không thay đổi kế hoạch dù giả thuyết đã bị bác bỏ** | Tiếp tục đầu tư vào hướng không còn hiệu quả | Xem lại backlog/roadmap khi bằng chứng có ý nghĩa |
| **Lấy lý do “linh hoạt” để bỏ qua ràng buộc** | Tăng rủi ro bảo mật, pháp lý hoặc dữ liệu | Giữ guardrail, DoD và minh bạch đánh đổi |
| **Lập nhiều kế hoạch nhưng không bàn giao gì** | Phản hồi thực tế đến muộn; kế hoạch ngày càng dựa vào suy đoán | Ưu tiên increment nhỏ, tích hợp và kiểm tra thường xuyên |
| **Dùng ước lượng một con số làm cam kết chắc chắn** | Dự báo sai bị quy thành thất hứa hoặc nhóm che giấu rủi ro | Công bố giả định, khoảng bất định và nhịp cập nhật |
| **Chia việc thành task kỹ thuật rồi coi là bàn giao giá trị** | Các tầng chưa chạy thành hành trình người dùng | Ưu tiên story/lát dọc có hành vi kiểm chứng được |

## 13. Bài thực hành: đổi từ roadmap tính năng sang kế hoạch thích ứng

### Đề bài

Một nhóm phát triển hệ thống học trực tuyến được giao bảng kế hoạch sáu tháng:

1. Tháng 1: tạo 12 màn hình.
2. Tháng 2: thêm huy hiệu và điểm thưởng.
3. Tháng 3: gửi email nhắc học hàng ngày.
4. Tháng 4: xây dashboard tiến độ.
5. Tháng 5: tích hợp gợi ý khóa bằng AI.
6. Tháng 6: kiểm thử tổng thể và phát hành toàn bộ.

Trong khi đó, dữ liệu bước đầu cho thấy nhiều học viên rời khóa sau bài đầu; nhóm **chưa biết nguyên nhân chính**. Ngày khai giảng khóa tiếp theo sau tám tuần là mốc bên ngoài quan trọng. Hệ thống hiện có lỗi khi ghi tiến độ trên hai thiết bị.

**Yêu cầu thực hiện:**

1. Viết lại **một mục tiêu giai đoạn** bằng outcome, nêu nhóm người dùng và cách đo.
2. Tách những gì là **ràng buộc bắt buộc** với những gì chỉ là **phương án/ý tưởng**.
3. Phác thảo roadmap theo **Now – Next – Later** dựa trên vấn đề cần kiểm chứng, không cố định danh sách tính năng vào từng tháng.
4. Lập kế hoạch **một nhịp thực hiện gần** với lát giá trị có thể hoàn tất, tiêu chí chấp nhận và DoD.
5. Nêu điều kiện khiến nhóm **xem lại dự báo hoặc đổi thứ tự backlog**.
6. Đề xuất cách thông báo với stakeholder về mốc khai giảng và độ bất định.

### Lời giải tham khảo

**Mục tiêu giai đoạn:** Tăng tỷ lệ học viên mới quay lại và mở bài hai trong bảy ngày sau bài đầu, với định nghĩa đo nhất quán; duy trì việc ghi tiến độ chính xác và bảo vệ quyền truy cập.

**Ràng buộc:** ngày khai giảng là mốc cần phối hợp; quy tắc quyền học, tính toàn vẹn tiến độ và tiêu chuẩn vận hành không được bỏ qua. Các tính năng huy hiệu, email nhắc và AI là **lựa chọn**, cần bằng chứng trước khi trở thành cam kết.

**Roadmap theo cơ hội:**

| Chân trời | Nội dung | Bằng chứng/điều kiện chuyển tiếp |
| --- | --- | --- |
| **Now** | Sửa lỗi mất tiến độ đa thiết bị; quan sát người học bỏ dở; cải thiện một luồng quay lại học nếu có bằng chứng | Kiểm thử hồi quy, dữ liệu sự kiện, quan sát tình huống thật |
| **Next** | Xem xét vấn đề độ dài/độ khó bài học và thử một cải tiến nhỏ | Kết quả đo và phản hồi từ lát Now |
| **Later** | Cân nhắc nhắc học tự chọn, huy hiệu, đề xuất cá nhân hóa | Chỉ ưu tiên khi giải quyết vấn đề đã xác nhận và có tính khả thi |

**Kế hoạch gần:** Trong nhịp thực hiện đầu, tập trung sửa lỗi mất tiến độ vì nó có thể làm hỏng mọi phép đo về việc quay lại học; đồng thời quan sát người dùng và làm rõ story “Tiếp tục học” nếu đủ chứng cứ. Nhóm cần tránh cam kết quá nhiều lát một lúc. Acceptance criteria cho sửa lỗi bao gồm: tiến độ cập nhật nhất quán theo quy tắc trên hai thiết bị, không hiển thị tiến độ của người khác, và có kiểm thử cho đồng bộ lại sau lỗi mạng. DoD cần kiểm thử tích hợp/hồi quy và khả năng theo dõi lỗi sau triển khai.

**Điều kiện thay đổi:** Nếu phỏng vấn cho thấy trở ngại chính là nội dung bài, chuyển ưu tiên sang thử phân chia bài. Nếu lỗi đồng bộ chưa được khắc phục an toàn gần mốc khai giảng, thông báo rủi ro sớm, xem lại phạm vi đủ ổn định cho người học và phương án vận hành phù hợp. Không đợi sát ngày mới báo “kế hoạch không khả thi”.

**Trao đổi với stakeholder:** “Mốc khai giảng vẫn được quản lý như ràng buộc quan trọng. Nhóm đang ưu tiên độ chính xác tiến độ và một luồng học tiếp có thể kiểm chứng. Các tính năng thưởng điểm, email và AI được giữ là ứng viên cho các đợt sau; chúng tôi sẽ cập nhật dự báo khi có kết quả kiểm thử, phản hồi và năng lực thực tế.”

Lời giải tham khảo **không khẳng định** một nhóm bất kỳ có thể hoàn thành mọi phần trước tám tuần. Phạm vi cam kết thực tế phải dựa trên năng lực, độ lớn hạng mục, phụ thuộc, mức rủi ro và quyết định của người có thẩm quyền.

## 14. Checklist phân biệt dài hạn và ngắn hạn

- [ ] Mục tiêu dài hạn mô tả **người hưởng lợi và outcome**, thay vì chỉ một danh sách tính năng?
- [ ] Đã xác định **cách đo**, mốc xem lại và các guardrail quan trọng?
- [ ] Roadmap thể hiện **giả thuyết và lựa chọn tương lai** ở mức chi tiết phù hợp?
- [ ] Các ràng buộc về **ngày, ngân sách, chất lượng và pháp lý** đã được nêu rõ?
- [ ] Backlog gần được làm rõ bằng **user story, tiêu chí chấp nhận và mức rủi ro thực tế**?
- [ ] Kế hoạch ngắn hạn chọn **lát có thể tích hợp và kiểm chứng**, tránh chỉ liệt kê task theo tầng?
- [ ] Nhóm đã xem **năng lực thực tế, phụ thuộc, WIP và công việc đột xuất**?
- [ ] Đã phân biệt rõ **mục tiêu, dự báo, kế hoạch và cam kết** trong giao tiếp?
- [ ] Có cách lấy **phản hồi sau increment** để điều chỉnh backlog và roadmap?
- [ ] Khi có bằng chứng mới, đã xác định **ai quyết định và điều gì được phép đổi**?
- [ ] Nhóm có xem lại **chất lượng kỹ thuật và dòng công việc**, không chỉ lượng ticket hoàn tất?
- [ ] Các thay đổi kế hoạch được giải thích bằng **bằng chứng và tác động**, không chỉ khẩu hiệu “Agile linh hoạt”?

**Ghi nhớ:** Trong Agile, mục tiêu dài hạn giúp cả nhóm biết **vì sao và hướng đến kết quả nào**, còn kế hoạch chi tiết ngắn hạn cho biết **bước nào có thể thực hiện và kiểm chứng ngay với thông tin hiện có**. Giữ mục tiêu đủ rõ để tập trung, lập kế hoạch gần đủ cụ thể để bàn giao, rồi cập nhật dự báo và ưu tiên bằng phản hồi thực tế là cách biến **Scrum, Kanban, XP, user story, backlog và số liệu dòng công việc** thành năng lực phát triển thích ứng thay vì chỉ bám theo lịch cố định.
