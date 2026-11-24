# Xác định phần sản phẩm nhỏ nhất để kiểm chứng một giả định

> **Thông điệp chính:** Trong Agile, xây dựng ít hơn chỉ có ý nghĩa khi phần được xây dựng giúp nhóm **học sớm một điều quan trọng về giá trị sản phẩm**. Phạm vi tối thiểu không phải phiên bản thiếu chất lượng của một sản phẩm lớn; đó là phần đủ để quan sát hành vi thật, kiểm tra một giả định cụ thể và quyết định bước tiếp theo.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **vấn đề người dùng, giả định, giả thuyết kiểm chứng được, thử nghiệm, Increment và kết quả sản phẩm**.
2. Chọn giả định rủi ro cao cần kiểm chứng trước khi xây dựng nhiều tính năng.
3. Xác định **phần sản phẩm nhỏ nhất** có đủ luồng sử dụng và khả năng đo lường để tạo ra bằng chứng đáng tin.
4. Viết **user story, acceptance criteria và tiêu chí thành công** cho một phép thử có giới hạn.
5. Chọn cách thử phù hợp như phỏng vấn, nguyên mẫu, thực hiện thủ công có kiểm soát, phát hành cho nhóm nhỏ hoặc thử nghiệm A/B.
6. Diễn giải phản hồi sớm, chỉ số và giới hạn của bằng chứng để **tiếp tục, thay đổi hướng hoặc dừng** một ý tưởng.
7. Kết hợp Scrum, Kanban và các thực hành kỹ thuật XP để giao giá trị tăng dần mà vẫn bảo đảm chất lượng.

## 2. Vì sao cần tìm "phần nhỏ nhất"?

Hãy tưởng tượng một đội phát triển nền tảng đặt lịch tư vấn. Khách hàng thường không đến buổi hẹn, khiến chuyên viên phải để trống nhiều khung giờ. Nhóm đề xuất một hệ thống lớn gồm nhắc lịch qua email, SMS, chatbot, lịch đồng bộ hai chiều, ứng dụng di động và công cụ dự báo tỷ lệ vắng mặt.

Đề xuất nghe hợp lý nhưng chứa nhiều giả định chưa kiểm chứng:

- Người dùng **quên lịch** thực sự là nguyên nhân chính khiến họ vắng mặt.
- Một tin nhắn nhắc trước buổi hẹn sẽ giúp họ có mặt nhiều hơn.
- Email là kênh mà nhóm người dùng mục tiêu thường đọc.
- Người dùng có thể đổi hoặc hủy lịch mà không cần hỗ trợ trực tiếp.
- Hiệu quả giảm vắng mặt đủ lớn để bù chi phí triển khai và vận hành.

Nếu xây cả hệ thống trước rồi mới đo, nhóm có thể tốn hàng tháng giải quyết một vấn đề **chưa hiểu rõ nguyên nhân**. Cách tiếp cận Agile là làm rõ nhu cầu, chọn giả định có tác động lớn và tạo **vòng phản hồi ngắn nhất đủ đáng tin**.

Đôi khi một cuộc phỏng vấn hoặc nguyên mẫu là đủ để bác bỏ giả định về cách sử dụng. Đôi khi phải có **một phần sản phẩm chạy thật** mới biết người dùng có hành động như kỳ vọng hay không. Mục tiêu không phải tìm mọi cách giảm số dòng mã; mục tiêu là **giảm công sức và thời gian đến bằng chứng hữu ích**.

## 3. Những khái niệm không nên nhầm lẫn

| Khái niệm | Câu hỏi nó trả lời | Ví dụ trong sản phẩm đặt lịch |
|---|---|---|
| **Vấn đề (problem)** | Người dùng hoặc tổ chức đang gặp khó khăn gì? | Nhiều buổi hẹn bị bỏ lỡ, chuyên viên khó tận dụng lịch |
| **Giả định (assumption)** | Điều gì chúng ta tin là đúng nhưng chưa chứng minh? | Phần lớn người vắng mặt vì quên lịch |
| **Giả thuyết (hypothesis)** | Dự đoán có thể bị bác bỏ bằng quan sát nào? | Gửi nhắc lịch trước 24 giờ sẽ giảm tỷ lệ không đến trong nhóm thử |
| **Thử nghiệm (experiment)** | Ta làm gì để thu thập bằng chứng? | Gửi thông báo tới nhóm hẹn đủ điều kiện và theo dõi kết quả |
| **Đầu ra (output)** | Ta đã tạo hoặc giao cái gì? | Chức năng gửi email nhắc lịch |
| **Kết quả (outcome)** | Hành vi hay trạng thái nào thay đổi? | Tỷ lệ người đến đúng lịch tăng; tỷ lệ vắng giảm |
| **Tác động/giá trị (impact/value)** | Vì sao kết quả đó quan trọng? | Người dùng được phục vụ đúng giờ, giảm giờ trống và công xử lý lại |
| **Increment** | Phần sản phẩm tích hợp, đạt Definition of Done và sử dụng được là gì? | Luồng email nhắc lịch đáng tin cậy được tích hợp vào hệ thống |

**Giả định** là một niềm tin cần kiểm tra; **giả thuyết** là cách diễn đạt niềm tin ấy để có thể đánh giá đúng/sai trong một bối cảnh cụ thể.

**Minimum Viable Product (MVP)** thường được hiểu là phiên bản giúp nhóm thu được tối đa kiến thức đã được kiểm chứng về khách hàng với công sức ít nhất. Đây là một khái niệm trong tư duy Lean Startup; **MVP không phải một sự kiện, vai trò hoặc tạo tác bắt buộc trong Scrum**. Trong thực tế, có nơi gọi MVP là sản phẩm phát hành đầu tiên, có nơi dùng để chỉ một thử nghiệm rất nhỏ. Vì vậy, khi dùng từ này cần nói rõ **giả định nào sẽ được kiểm chứng và bằng chứng nào được chấp nhận**.

**Minimum Marketable Product (MMP)** hoặc một bản có thể bán/giao rộng rãi trả lời câu hỏi khác: “Phạm vi tối thiểu đủ giá trị để phát hành cho thị trường mục tiêu là gì?”. Bản thử nghiệm đầu tiên có thể **chưa** đáp ứng yêu cầu phát hành rộng rãi.

**Prototype (nguyên mẫu)** giúp kiểm tra cách hiểu, thiết kế hoặc khả năng sử dụng; nó có thể không có dữ liệu thật hay xử lý nghiệp vụ hoàn chỉnh. **Spike** thường là công việc khám phá có giới hạn thời gian nhằm giảm bất định kỹ thuật, chẳng hạn kiểm tra API gửi thông báo có hỗ trợ độ trễ mong muốn không. Prototype và spike tạo bằng chứng hữu ích, nhưng **không tự động là Increment có thể phát hành**.

## 4. "Nhỏ nhất" phải đủ để trả lời một câu hỏi

Một phần sản phẩm quá lớn khiến thời gian học chậm; quá nhỏ thì người dùng không thể hoàn thành hành vi cần đo. Hãy dùng ba tiêu chí đồng thời:

1. **Đủ để xảy ra hành vi quan trọng:** người dùng thực hiện được hành động cốt lõi trong bối cảnh phù hợp.
2. **Đủ để quan sát:** hệ thống hoặc người nghiên cứu có thể nhận biết kết quả thật, không chỉ biết nút bấm đã hiển thị.
3. **Đủ an toàn và đáng tin:** phần đã giao đáp ứng tiêu chuẩn chất lượng, quyền riêng tư, bảo mật và ràng buộc vận hành tương ứng.

### Ví dụ phần quá nhỏ, vừa đủ và quá lớn

| Phạm vi | Học được gì? | Hạn chế |
|---|---|---|
| Chỉ thêm nút “Nhắc tôi” nhưng nút không hoạt động | Có thể thấy người dùng chú ý hoặc muốn tìm hiểu, nếu có đo đúng | **Không** xác nhận được tin nhắn có giúp người dùng đến đúng hẹn |
| Gửi email nhắc lịch thực sự trước 24 giờ cho một nhóm hẹn đủ điều kiện | Có thể quan sát việc email gửi thành công, người dùng phản hồi và tỷ lệ đến hẹn | Chưa kiểm chứng kênh SMS, chatbot hay tối ưu hóa thời điểm |
| Xây cả hệ sinh thái nhắc lịch đa kênh, phân tích dự báo, ứng dụng mới | Có thể kiểm chứng nhiều khả năng sau khi xây xong | Thời gian và chi phí trước phản hồi đầu tiên rất lớn; khó biết yếu tố nào tạo tác động |

**Kết luận quan trọng:** nếu câu hỏi là “Người dùng có hiểu nút nhắc lịch không?”, nguyên mẫu có thể đủ. Nếu câu hỏi là “Nhắc lịch có giảm vắng mặt không?”, cần quan sát hành vi đặt lịch thực tế hoặc một phép thử có khả năng đại diện cho hành vi đó.

## 5. Bắt đầu từ giả định có rủi ro cao nhất

Đừng chọn tính năng dễ làm nhất theo phản xạ. Trước tiên, hãy liệt kê những điều **phải đúng** để ý tưởng tạo giá trị.

### 5.1. Bốn nhóm giả định nên xem xét

| Nhóm | Câu hỏi | Cách kiểm chứng ban đầu |
|---|---|---|
| **Giá trị (value)** | Người dùng có cần giải pháp và sẵn sàng dùng hay trả tiền cho nó không? | Quan sát hành vi, thử luồng thật, trao đổi có ví dụ |
| **Khả dụng (usability)** | Người dùng có hiểu và sử dụng được giải pháp không? | Kiểm thử khả dụng với nguyên mẫu hoặc chức năng đơn giản |
| **Khả thi kỹ thuật (feasibility)** | Hệ thống có thể đáp ứng yêu cầu kỹ thuật, dữ liệu và tích hợp không? | Spike, thử API, kiểm thử tải hoặc thử tích hợp giới hạn |
| **Khả năng duy trì (viability)** | Chi phí, vận hành, quy định và mô hình kinh doanh có chấp nhận được không? | Ước lượng chi phí có kiểm chứng, thử vận hành nhỏ, trao đổi với bộ phận chịu trách nhiệm |

Các nhóm này có quan hệ với nhau. Một tính năng được người dùng yêu thích nhưng vi phạm quyền riêng tư hoặc có chi phí vận hành không bền vững chưa phải giải pháp phù hợp.

### 5.2. Ma trận độ bất định và hậu quả

Chấm điểm đơn giản chỉ để **ưu tiên trao đổi**, không phải phép tính chính xác:

| Giả định | Độ bất định | Hậu quả nếu sai | Nên kiểm chứng |
|---|---|---|---|
| Người dùng vắng mặt chủ yếu vì quên lịch | Cao | Cao | **Đầu tiên** |
| Email đến đúng hộp thư và được đọc kịp thời | Trung bình | Cao | Sớm, trước khi mở rộng |
| Giao diện có cần hình minh họa lớn không | Trung bình | Thấp | Sau hoặc thử nhanh bằng nguyên mẫu |
| API có thể gửi 100.000 tin/ngày | Cao | Trung bình nếu giai đoạn đầu chỉ có 100 lịch/ngày | Khi quy mô thực tế yêu cầu |

Một giả định vừa **khó chắc chắn** vừa **gây hậu quả lớn nếu sai** là ứng viên ưu tiên cho bước kiểm chứng tiếp theo. Không cần xây đầy đủ sản phẩm để kiểm tra mọi giả định cùng lúc.

### 5.3. Phân biệt bằng chứng với ý kiến

Một khách hàng nói “Tôi rất thích tính năng này” là tín hiệu quan tâm, chưa phải bằng chứng họ **sẽ dùng thường xuyên**. Một người nói “Tôi chắc chắn trả tiền” cũng chưa tương đương giao dịch thật.

Có thể xếp các loại bằng chứng theo mức độ liên quan tới câu hỏi:

- **Ý kiến hoặc dự đoán:** người tham gia diễn đạt điều họ nghĩ mình sẽ làm.
- **Quan sát thao tác:** họ có thực hiện được nhiệm vụ trên nguyên mẫu hoặc bản dùng thử không?
- **Hành vi thực tế:** họ có sử dụng, quay lại, hoàn thành tác vụ hoặc thanh toán trong bối cảnh thật không?
- **Kết quả duy trì:** tác động có tồn tại sau lần dùng đầu, trên nhóm phù hợp và trong điều kiện vận hành thông thường không?

Không có thứ bậc tuyệt đối cho mọi câu hỏi. Một kiểm thử tải là bằng chứng phù hợp để trả lời **khả thi kỹ thuật**, nhưng không thể thay thế bằng chứng **người dùng cần tính năng**.

## 6. Viết giả thuyết kiểm chứng được

Một mẫu thực dụng:

> **Chúng tôi tin rằng** [nhóm người dùng cụ thể] gặp [vấn đề], và nếu [thay đổi nhỏ], thì [hành vi/kết quả đo được] sẽ thay đổi theo [hướng kỳ vọng] trong [bối cảnh/khoảng thời gian]. **Chúng tôi sẽ kiểm tra bằng** [phương pháp], đồng thời theo dõi [rủi ro/tín hiệu bảo vệ].

Ví dụ:

> “Đối với người đã đặt lịch tư vấn trước ít nhất hai ngày, nếu gửi email nhắc trước 24 giờ, tỷ lệ không đến hẹn có thể giảm so với những lịch tương đương không nhận email. Nhóm sẽ đo tỷ lệ vắng mặt theo định nghĩa thống nhất, đồng thời theo dõi lỗi gửi, yêu cầu hủy, phản hồi không mong muốn và quyền từ chối nhận thông báo.”

Giả thuyết này tốt hơn câu **“Làm hệ thống nhắc lịch để nâng trải nghiệm”** vì nó chỉ rõ người dùng, can thiệp, outcome và cách quan sát. Tuy nhiên, **mức giảm cụ thể và cỡ mẫu** vẫn cần xác định theo dữ liệu nền, mức tác động có ý nghĩa và năng lực đo lường.

### 6.1. Lập kế hoạch trước khi nhìn số liệu

Trước khi triển khai, nhóm nên thống nhất:

| Thành phần | Câu hỏi cần quyết định |
|---|---|
| **Đối tượng** | Ai đủ điều kiện tham gia? Có loại trừ trường hợp nào không? |
| **Hành vi mục tiêu** | Cần thấy điều gì thay đổi để giả thuyết đáng tiếp tục? |
| **Cách đo** | Sự kiện, nguồn dữ liệu, thời điểm và mẫu số là gì? |
| **Mốc so sánh** | So với hiện trạng, nhóm tương đương hay thử nghiệm có phân nhóm? |
| **Tín hiệu bảo vệ** | Lỗi gửi, phiền nhiễu, bảo mật, chi phí, công sức hỗ trợ có tăng không? |
| **Thời điểm đánh giá** | Khi nào có đủ quan sát để xem lại? |
| **Quyết định có thể đưa ra** | Nếu kết quả tốt, xấu hoặc không rõ ràng thì làm gì? |

Đừng nhìn dữ liệu rồi tùy ý chọn một ngưỡng làm bằng chứng “đã thành công”. Cũng tránh chốt số lượt nhấp hoặc lượt xem làm mục tiêu khi điều thực sự muốn biết là **tỷ lệ có mặt đúng hẹn**.

## 7. Chọn phép thử ít tốn kém nhất nhưng đủ sức trả lời

Không phải mọi giả định đều cần viết code. Hãy chọn thử nghiệm theo **điều chưa biết**, mức rủi ro và mức độ bằng chứng cần thiết.

| Phép thử | Phù hợp để học | Chưa đủ để kết luận |
|---|---|---|
| **Phỏng vấn có tình huống cụ thể** | Vấn đề, bối cảnh, động cơ, quy trình hiện tại | Người dùng chắc chắn sẽ sử dụng hay trả tiền |
| **Phác thảo hoặc nguyên mẫu có thể bấm** | Người dùng hiểu giao diện và tìm được bước cần làm không | Tính ổn định, hiệu năng hoặc kết quả sử dụng lâu dài |
| **Wizard of Oz / concierge có thông báo rõ** | Người dùng có chấp nhận trải nghiệm dịch vụ khi một phần hậu trường làm thủ công không | Khả năng vận hành tự động ở quy mô lớn |
| **Landing page / đăng ký quan tâm trung thực** | Người dùng có thể hiện mối quan tâm đủ để để lại thông tin hoặc đăng ký thử không | Họ chắc chắn sẽ sử dụng đều đặn sau phát hành |
| **Spike kỹ thuật** | API, tích hợp, chi phí xử lý hoặc giới hạn công nghệ có khả thi không | Nhu cầu thực của người dùng |
| **Increment dọc (vertical slice) cho nhóm nhỏ** | Người dùng thực hiện hành vi cốt lõi trên phần mềm hoạt động được không | Các trường hợp hoặc phân khúc chưa được thử |
| **Thử nghiệm có nhóm so sánh/A-B** | Một thay đổi có liên quan đến khác biệt outcome trong điều kiện kiểm soát phù hợp không | Tác động chắc chắn nếu chọn nhóm sai, đo sai hoặc mẫu quá ít |

**Lưu ý đạo đức và tin cậy:** các thử nghiệm như “fake door” (hiển thị lựa chọn trước khi chức năng sẵn sàng) chỉ nên dùng nếu không đánh lừa người dùng về việc đã thực hiện, thu thập dữ liệu đúng thỏa thuận và không gây thiệt hại. Cần thông báo rõ tính năng chưa sẵn sàng hoặc là chương trình đăng ký quan tâm. Không mô phỏng giao dịch, xác nhận lịch hay xử lý dữ liệu nhạy cảm như thể đã hoàn tất nếu hệ thống chưa thực hiện.

### Cây quyết định đơn giản

~~~mermaid
flowchart TD
    A["Ta đang chưa biết điều gì?"] --> B{"Có cần quan sát sản phẩm chạy thật?"}
    B -->|"Không"| C["Chọn phỏng vấn, nguyên mẫu hoặc spike phù hợp"]
    B -->|"Có"| D{"Hành vi có thể xuất hiện trong một luồng nhỏ?"}
    D -->|"Có"| E["Xây vertical slice đạt chuẩn, thử trên phạm vi hẹp"]
    D -->|"Chưa"| F["Tách giả định hoặc tìm phép thử trung gian"]
    C --> G["Thu thập bằng chứng và ghi giới hạn"]
    E --> G
    F --> G
    G --> H{"Đã đủ thông tin cho quyết định kế tiếp?"}
    H -->|"Chưa"| A
    H -->|"Đủ"| I["Tiếp tục / điều chỉnh / dừng"]
~~~

“Nhỏ nhất” là **nhỏ nhất để đưa ra quyết định kế tiếp**, chứ không phải nhỏ nhất có thể đưa lên một slide.

## 8. Thiết kế một vertical slice có thể kiểm chứng

Khi cần phần mềm hoạt động được, hãy **cắt phạm vi theo luồng giá trị từ đầu đến cuối** thay vì chỉ hoàn thiện từng lớp kỹ thuật.

### 8.1. Cắt theo hành vi người dùng

Với hệ thống đặt lịch, một cách chia theo tầng công nghệ có thể là:

1. Làm toàn bộ cấu trúc bảng thông báo.
2. Làm toàn bộ API.
3. Làm mọi màn hình quản trị.
4. Cuối cùng mới gửi được thông báo thật.

Nhóm phải chờ đến bước cuối mới biết người dùng có hưởng lợi. Một lát cắt dọc có giá trị kiểm chứng sớm hơn:

> **Với những lịch hẹn đã xác nhận và có địa chỉ email hợp lệ, hệ thống gửi một email nhắc trước 24 giờ, ghi nhận kết quả gửi và cho phép người dùng xem chi tiết lịch đã đặt.**

Lát cắt này có thể đi qua dữ liệu, logic thời điểm, dịch vụ gửi email và ghi nhận sự kiện, nhưng chỉ phục vụ **một kênh, một thời điểm và một nhóm trường hợp rõ ràng**.

### 8.2. User story và acceptance criteria

**User story:**

> Là người đã đặt lịch tư vấn, tôi muốn nhận một thông báo trước buổi hẹn để không vô tình quên thời gian và địa điểm.

**Các kịch bản minh họa:**

~~~gherkin
Tính năng: Gửi email nhắc lịch hẹn

Kịch bản: Lịch đã xác nhận và đủ điều kiện nhận nhắc
  Cho trước một lịch hẹn đã được xác nhận
  Và người dùng đã đồng ý nhận email nhắc
  Và thời gian hẹn còn 24 giờ theo quy tắc đã thống nhất
  Khi tác vụ gửi thông báo được thực hiện
  Thì hệ thống tạo email với thời gian và địa điểm chính xác
  Và ghi nhận kết quả xử lý gửi

Kịch bản: Lịch đã bị hủy
  Cho trước một lịch hẹn đã bị hủy trước thời điểm gửi
  Khi tác vụ gửi thông báo được thực hiện
  Thì hệ thống không gửi email nhắc cho lịch đó

Kịch bản: Thử lại khi dịch vụ gửi gặp lỗi tạm thời
  Cho trước một lịch hẹn đủ điều kiện gửi
  Và dịch vụ gửi email trả lỗi có thể thử lại
  Khi hệ thống xử lý lại theo chính sách đã thống nhất
  Thì tránh tạo nhiều thông báo trùng không cần thiết
  Và lưu trạng thái để vận hành có thể theo dõi

Kịch bản: Người dùng đã từ chối nhận nhắc
  Cho trước người dùng không cho phép nhận email nhắc
  Khi tác vụ xử lý lịch hẹn chạy
  Thì hệ thống không gửi email nhắc cho người dùng đó
~~~

Các quy tắc về thời điểm, đồng ý nhận thông báo, xử lý lỗi và quyền riêng tư phải được thống nhất theo sản phẩm thực tế. Các kịch bản giúp nhóm biết **phần nhỏ này đã hoạt động đúng hay chưa**; chúng không tự chứng minh giả thuyết **người dùng sẽ bớt vắng mặt**.

### 8.3. Definition of Done không thu nhỏ theo tham vọng thử nghiệm

Có thể thu nhỏ **phạm vi tính năng**, nhưng một Increment vẫn cần đáp ứng Definition of Done phù hợp và tiêu chuẩn chất lượng áp dụng. Ví dụ:

- Trường hợp chính và trường hợp lỗi quan trọng đã được kiểm thử.
- Không gửi thông báo sai lịch, sai người hoặc trái lựa chọn của người dùng.
- Có log/sự kiện cần thiết để biết hệ thống gửi thành công hay thất bại; tránh lưu dữ liệu nhạy cảm không cần thiết.
- Có khả năng tắt tính năng hoặc dừng phát hành thử khi phát hiện tác động xấu.
- Những người vận hành liên quan biết phạm vi, người chịu trách nhiệm và cách phản hồi sự cố.

**Không chấp nhận “MVP nên được phép lỗi nhiều” như một nguyên tắc chung.** Một phép thử phạm vi nhỏ vẫn có thể gây mất dữ liệu, lộ thông tin hoặc làm phiền khách hàng. Giới hạn của trải nghiệm cần được công khai và rủi ro phải được kiểm soát.

## 9. Ví dụ xuyên suốt: từ giả định đến quyết định sản phẩm

### Giai đoạn A — Làm rõ vấn đề

Đội đặt lịch thống kê các lịch đã hoàn thành và các lịch bị bỏ lỡ. Dữ liệu cho thấy một phần lịch không có mặt, nhưng chưa giải thích được nguyên nhân. Nhóm phỏng vấn người dùng từng bỏ lỡ lịch và nhân viên hỗ trợ; một số nói đã quên, số khác gặp việc đột xuất hoặc chưa thấy địa điểm rõ ràng.

**Điều học được:** quên lịch là giả định có cơ sở để thử, nhưng **không phải nguyên nhân duy nhất**. Hệ thống nhắc có thể giúp một nhóm người, còn nhóm khác cần cơ chế đổi/hủy lịch.

### Giai đoạn B — Chọn một giả thuyết

> “Với lịch hẹn tư vấn đã xác nhận trước ít nhất hai ngày, một email nhắc gửi trước 24 giờ có thể làm giảm tỷ lệ không đến mà không làm tăng đáng kể khiếu nại hoặc yêu cầu hỗ trợ.”

Nhóm chọn **email** vì người dùng hiện đã cung cấp email và dịch vụ gửi hiện có. Đây là lựa chọn phụ thuộc bối cảnh, không phải khẳng định email luôn tốt hơn SMS.

### Giai đoạn C — Xây lát cắt tối thiểu

Phạm vi ban đầu:

| Có trong thử nghiệm | Chưa đưa vào |
|---|---|
| Một mẫu email ngắn, rõ thời gian và địa điểm | Nhiều mẫu quảng bá hoặc cá nhân hóa phức tạp |
| Gửi một lần theo quy tắc thời gian | Chuỗi nhắc nhiều lần, đa kênh |
| Kiểm tra lịch chưa hủy và quyền nhận thông báo | Chatbot, tự động gợi ý khung giờ khác |
| Theo dõi lỗi gửi và tình trạng đến hẹn | Hệ thống dự báo không đến bằng AI |
| Giới hạn nhóm hẹn và cơ chế tắt khi cần | Phát hành đồng loạt tới toàn bộ người dùng |

Nhóm vẫn phải giải quyết trường hợp lỗi gửi, lịch bị hủy và độ chính xác thời gian. **Cắt bớt khả năng không cần thiết** khác với **bỏ qua các trường hợp gây hại**.

### Giai đoạn D — Lập phương án đo

Ví dụ minh họa, nhóm phân chia ngẫu nhiên **những lịch đủ điều kiện** thành hai nhóm nếu điều kiện kinh doanh và đạo đức cho phép: nhóm có email nhắc và nhóm vẫn nhận cách hỗ trợ hiện tại. Mỗi lịch chỉ thuộc một nhóm; định nghĩa “không đến” và thời điểm chốt kết quả được thống nhất trước.

**Chỉ số chính:** tỷ lệ lịch đủ điều kiện mà người dùng không đến trong khoảng thời gian theo quy tắc xác nhận có mặt.

**Tín hiệu bảo vệ:** số email gửi lỗi, phản hồi phàn nàn, yêu cầu hủy/đổi lịch và chi phí xử lý.

**Thông tin nền:** loại lịch, thời điểm đặt lịch, người dùng mới/cũ và các thay đổi dịch vụ có thể ảnh hưởng kết quả.

**Điều không nên làm:** so sánh các lịch của tuần có email với một tuần bất kỳ trước đó rồi khẳng định email chắc chắn gây ra thay đổi; khác biệt có thể đến từ mùa vụ, cơ cấu khách hàng hoặc thay đổi vận hành.

### Giai đoạn E — Đọc bằng chứng

Giả sử nhóm thử nghiệm được các số liệu **hoàn toàn giả định** sau:

| Nhóm | Số lịch đủ điều kiện | Số lịch không đến | Tỷ lệ không đến |
|---|---:|---:|---:|
| Không có email nhắc mới | 60 | 18 | 30% |
| Có email nhắc mới | 60 | 13 | Khoảng 21,7% |

Chênh lệch quan sát là khoảng **8,3 điểm phần trăm**, hoặc khoảng **giảm 27,8% theo tỷ lệ tương đối** so với nhóm không có email nhắc. Hai cách diễn đạt này khác nhau; không nên viết “giảm 27,8 điểm phần trăm”.

Đây mới là **tín hiệu ban đầu**, không đủ để tuyên bố tác động chắc chắn cho mọi người dùng. Với 60 lịch mỗi nhóm, sai số ngẫu nhiên có thể đáng kể; còn cần xem tính tương đồng nhóm, cách phân bổ, lịch bị loại, phản hồi tiêu cực và mức tác động tối thiểu có ý nghĩa với sản phẩm.

Nếu chênh lệch chưa đủ rõ, nhóm có thể kéo dài phép thử, cải thiện đo lường hoặc kiểm tra phân khúc phù hợp **theo kế hoạch minh bạch**, thay vì liên tục chọn nhóm con cho ra số đẹp. Nếu xuất hiện rủi ro như gửi sai lịch hoặc làm phiền người dùng, nhóm phải xử lý trước khi mở rộng.

### Giai đoạn F — Quyết định tiếp theo

| Kết quả quan sát | Quyết định hợp lý cần cân nhắc |
|---|---|
| Có tín hiệu giảm vắng mặt, rủi ro chấp nhận được, bằng chứng đủ cho quyết định hiện tại | Tiếp tục thử ở phạm vi rộng hơn hoặc triển khai có kiểm soát |
| Email ít được nhận/đọc hoặc không làm thay đổi hành vi | Xem lại giả định về nguyên nhân, thời điểm, kênh hoặc nội dung |
| Người dùng quan tâm nhưng nhiều trường hợp cần đổi lịch | Ưu tiên kiểm chứng luồng đổi/hủy lịch thay vì tự động thêm nhiều tin nhắc |
| Dữ liệu chưa đủ rõ hoặc nhóm thử khác biệt đáng kể | Cải thiện thiết kế phép thử, thu thập thêm bằng chứng phù hợp |
| Phát sinh lỗi nghiêm trọng, sai người nhận hoặc vi phạm quyền riêng tư | Dừng phạm vi thử ảnh hưởng, khắc phục và đánh giá lại rủi ro |

Mỗi quyết định nên ghi rõ **điều đã học, giới hạn dữ liệu và giả định còn lại**. Đó là cách phản hồi sớm dẫn đến phát triển tăng dần, thay vì chạy theo một danh sách tính năng không thay đổi.

## 10. Kỹ thuật cắt nhỏ phạm vi mà vẫn giữ giá trị học hỏi

Không phải cứ giảm số dòng code hoặc số màn hình là phạm vi thử tốt hơn. Những cách cắt sau giúp duy trì câu hỏi kiểm chứng:

| Kỹ thuật | Cách áp dụng | Điều cần tránh |
|---|---|---|
| **Một phân khúc người dùng** | Thử với lịch tư vấn tại một cơ sở hoặc một nhóm khách hàng đủ điều kiện | Suy rộng kết quả ngay sang mọi cơ sở, mọi phân khúc |
| **Một tình huống chính** | Chỉ nhắc lịch đã xác nhận, chưa hủy, đặt trước đủ thời gian | Không xử lý lỗi có thể gây gửi sai thông tin |
| **Một kênh giao tiếp** | Email trước, chưa tích hợp SMS và chatbot | Kết luận một kênh hiệu quả cho mọi người dùng |
| **Một quy tắc đơn giản** | Nhắc trước 24 giờ theo quy tắc được thống nhất | Xây engine cấu hình lịch phức tạp trước khi biết cần hay không |
| **Một lát cắt dọc** | Lưu điều kiện → gửi email → ghi nhận kết quả → đo outcome | Xây xong nhiều API nhưng người dùng chưa thể trải nghiệm |
| **Thực hiện thủ công có kiểm soát** | Chuyên viên xử lý một phần hậu trường trong thử nghiệm minh bạch | Giả vờ đã tự động hóa hoàn toàn hoặc bỏ kiểm soát dữ liệu |
| **Giới hạn thời gian/thể tích thử** | Giới hạn số lịch hoặc thời gian để sớm xem lại quyết định | Cắt thử quá ngắn khiến không có đủ tín hiệu để phân biệt biến động |

### Cắt theo đầu–cuối, không chỉ theo lớp công nghệ

Một slice theo kiểu **backend xong trước → frontend xong sau → vận hành xong cuối** có thể tạo nhiều output kỹ thuật nhưng chưa có kết quả kiểm chứng. Nếu cần chứng minh khách hàng có thể thực hiện tác vụ, hãy tìm một đường đi **tối thiểu từ hành động người dùng đến phản hồi quan sát được**.

Tuy nhiên, các năng lực nền như kiểm soát truy cập hoặc tích hợp bắt buộc đôi khi phải xây trước. Khi đó nên nói rõ đây là **điều kiện kỹ thuật cần thiết** hoặc spike để giảm bất định, chứ không tự gọi nó là giá trị đã được kiểm chứng với người dùng.

### Đừng đánh đồng "đơn giản" với "cẩu thả"

Độ đơn giản mong muốn nằm ở **số giả định được kiểm tra cùng lúc**, **phạm vi hành vi** và **chi phí học hỏi**. Chất lượng của kết quả và độ tin cậy của phép đo vẫn cần bảo vệ.

## 11. Viết backlog theo câu hỏi cần học

Một Product Backlog có thể lưu cả tính năng, cải tiến, lỗi và công việc giảm rủi ro. Khi chọn bước tiếp theo, thay vì tạo hàng loạt task triển khai hệ thống hoàn chỉnh, hãy liên kết từng mục với giả định:

| Product Backlog Item | Giá trị hoặc câu hỏi học hỏi | Dấu hiệu hoàn thành |
|---|---|---|
| Làm rõ nguyên nhân vắng mặt qua phỏng vấn có cấu trúc | Quên lịch có phải một vấn đề có thật với nhóm mục tiêu? | Có ghi nhận các tình huống thực tế, giả định và khoảng trống hiểu biết |
| Kiểm tra tích hợp dịch vụ gửi email | Có thể gửi đúng lịch và theo dõi lỗi đáng tin cậy không? | Spike tạo bằng chứng kỹ thuật và danh sách rủi ro |
| Gửi email nhắc cho lịch đủ điều kiện | Người dùng có được thông báo và hệ thống có ghi nhận chính xác không? | Slice đáp ứng acceptance criteria và DoD |
| Thiết lập đo tỷ lệ vắng mặt theo nhóm | Có thể xem thay đổi outcome và tác dụng phụ không? | Định nghĩa chỉ số, sự kiện, kiểm tra tính đầy đủ dữ liệu |
| Quyết định mở rộng hoặc điều chỉnh ý tưởng | Bằng chứng hỗ trợ hướng đi nào? | Có kết luận, giới hạn và quyết định được ghi lại |

Không phải tất cả các mục này đều là **Increment**. Phỏng vấn và spike tạo kiến thức, còn Increment là phần sản phẩm tích hợp đáp ứng DoD. Phân biệt rõ giúp nhóm báo cáo thành thực về loại giá trị đã tạo ra.

Trong Scrum, Product Owner chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog; Developers quyết định cách thực hiện công việc trong Sprint. Scrum Team cùng kiểm tra giả định và có thể điều chỉnh Sprint Backlog khi hiểu biết tăng lên, miễn không làm nguy hại Sprint Goal và không hạ chất lượng.

## 12. Tận dụng Scrum, Kanban và XP cho vòng học hỏi ngắn

| Cách tiếp cận | Vai trò trong việc kiểm chứng giả định | Câu hỏi thực hành |
|---|---|---|
| **Scrum** | Tổ chức phát triển tăng dần qua Sprint; Sprint Review giúp trao đổi với bên liên quan về Increment và điều mới học | “Sprint Goal gắn với kết quả hoặc giả định quan trọng nào? Increment này giúp kiểm tra điều gì?” |
| **Kanban** | Hiển thị thời gian chờ, số việc đang làm, điểm tắc giữa ý tưởng và bằng chứng; kiểm soát WIP | “Có bao nhiêu thử nghiệm đang mở? Giả định nào bị chặn vì chúng ta làm quá nhiều việc song song?” |
| **Extreme Programming (XP)** | TDD, CI, refactoring và các thực hành kỹ thuật giúp giao slice nhỏ, kiểm thử được, thay đổi an toàn | “Khi giả định sai, việc đổi hành vi có phá vỡ hệ thống không? Chúng ta phát hiện lỗi nhanh đến đâu?” |

### 12.1. Dùng Sprint Goal để bảo vệ mục đích học

Thay vì mục tiêu “Hoàn thành 10 ticket email, 8 ticket chatbot”, một mục tiêu khả thi hơn trong tình huống minh họa có thể là:

> “Có Increment nhắc lịch qua email vận hành an toàn cho nhóm thử và đủ dữ liệu để bắt đầu kiểm tra tác động lên tỷ lệ vắng mặt.”

Kết quả cuối Sprint có thể là **hạ tầng và dữ liệu để bắt đầu quan sát**, chưa chắc đủ thời gian kết luận tỷ lệ vắng mặt. Hãy phân biệt **đạt mục tiêu giao Increment** với **xác nhận giả thuyết về outcome**.

### 12.2. Quan sát thời gian từ ý tưởng đến bằng chứng

Kanban có thể giúp nhóm theo dõi công việc từ **Cần làm rõ → Sẵn sàng thử → Đang xây/thực hiện → Đang quan sát → Đã quyết định**.

Giới hạn công việc đang thực hiện (**WIP**) giúp tránh việc mở hàng loạt thử nghiệm nhưng không có ai tổng hợp kết quả. Tuy nhiên, không nên coi một bảng có đủ mọi cột là quy định bắt buộc; workflow phải phù hợp loại việc, có chính sách rõ và phản ánh trạng thái thật.

### 12.3. Kỷ luật kỹ thuật giúp thử nhỏ nhiều lần

Một slice nhỏ nhưng thiếu kiểm thử có thể làm nhóm tốn công sửa lỗi hơn là học về nhu cầu. Các thực hành như:

- **Automated testing:** kiểm tra đường đi chính và những điều kiện rủi ro cao.
- **Continuous integration:** tích hợp và nhận phản hồi kỹ thuật sớm.
- **Feature flags và phát hành theo nhóm:** kiểm soát phạm vi thử khi phù hợp.
- **Telemetry phù hợp:** ghi nhận hành vi và lỗi cần thiết, tránh thu thập quá mức.
- **Refactoring:** giữ cấu trúc mã đủ linh hoạt để thay đổi khi giả thuyết bị bác bỏ.

Không phải mọi phép thử cần thêm một nền tảng kỹ thuật lớn. Hãy tái sử dụng cơ chế hiện có, nhưng vẫn bảo đảm an toàn và khả năng quan sát để tin vào kết quả.

## 13. Đánh giá bằng chứng và quyết định sau thử nghiệm

Một báo cáo thử nghiệm tốt không chỉ ghi “tính năng đã làm xong” hoặc “mọi người thích”. Nó phải làm rõ:

1. **Giả thuyết ban đầu** và vì sao quan trọng.
2. **Đối tượng, phạm vi và thay đổi** đã được triển khai.
3. **Dữ liệu thực tế** và chất lượng thu thập: cỡ mẫu, mốc thời gian, định nghĩa chỉ số.
4. **Tín hiệu bảo vệ** và tác dụng phụ.
5. **Giải thích thay thế:** yếu tố nào khác có thể tạo kết quả?
6. **Quyết định tiếp theo:** mở rộng, tiếp tục học, đổi hướng hoặc dừng, kèm lý do.

### Mẫu ghi nhận kết quả

~~~text
Giả định:
  Người vắng mặt chủ yếu vì quên lịch.

Giả thuyết thử:
  Email nhắc trước 24 giờ giúp giảm tỷ lệ không đến ở nhóm đủ điều kiện.

Phạm vi:
  Một nhóm lịch đã xác nhận, gửi qua một kênh và một thời điểm.

Bằng chứng thu được:
  Tỷ lệ đến/vắng theo định nghĩa thống nhất,
  số email lỗi, phản hồi người dùng và tình huống ngoại lệ.

Điều chưa chắc chắn:
  Cỡ mẫu, khác biệt phân khúc, tác động mùa vụ,
  liệu thay đổi có duy trì lâu dài không.

Quyết định:
  Tiếp tục / thay đổi / dừng (ghi lý do và người chịu trách nhiệm).

Bước tiếp:
  Thử mở rộng có kiểm soát hoặc kiểm chứng một giả định mới.
~~~

### Tránh những sai lầm suy luận phổ biến

- **Lượt nhấp không phải giá trị cuối:** người dùng có thể mở email nhưng vẫn bỏ lỡ cuộc hẹn.
- **Tương quan không luôn là nhân quả:** tỷ lệ vắng mặt giảm trong cùng thời gian gửi email không tự chứng minh email là nguyên nhân.
- **Số trung bình che giấu phân khúc:** tác động có thể khác giữa người dùng mới và người dùng cũ.
- **Dữ liệu quá ít tạo cảm giác chắc chắn giả:** vài người khen tính năng không chứng minh nhu cầu toàn thị trường.
- **Đổi tiêu chí sau khi xem kết quả dễ tạo thiên lệch:** cần ghi lại rõ thay đổi kế hoạch đo và phân biệt phát hiện khám phá với kết luận đã định trước.
- **Thử nghiệm thất bại về giả thuyết vẫn có giá trị:** nếu nhóm học được rằng vấn đề không đến từ quên lịch, có thể tránh xây thêm hệ thống nhắc vô ích.

## 14. Các sai lầm khi xác định phần sản phẩm nhỏ nhất

| Sai lầm | Vì sao gây hại | Cách sửa |
|---|---|---|
| “MVP là bản đầy đủ nhưng ít tính năng hơn.” | Vẫn có thể xây nhiều thứ trước khi kiểm tra giả định quan trọng | Viết rõ câu hỏi cần học, chọn phần đủ trả lời |
| “Càng ít code càng tốt.” | Một nút bấm không có luồng thật có thể không tạo bằng chứng về hành vi | Chọn lát cắt đủ end-to-end khi cần |
| “Khách hàng nói thích là ý tưởng đã được chứng minh.” | Ý định tự báo cáo có thể khác hành vi thật | Bổ sung quan sát hành vi hoặc cam kết thực |
| “Phải có A/B test cho mọi ý tưởng.” | Tốn công hoặc bất khả thi với nhóm nhỏ, rủi ro kỹ thuật | Chọn phương pháp hợp với câu hỏi và mức bằng chứng cần thiết |
| “Phát hành thử nghĩa là không cần kiểm thử.” | Lỗi nghiêm trọng có thể phá hủy dữ liệu, niềm tin và kết quả đo | Giữ DoD, bảo mật, khả năng dừng thử và kiểm soát rủi ro |
| “Nhóm nhỏ thấy tốt thì toàn thị trường sẽ tốt.” | Tác động có thể phụ thuộc phân khúc hoặc điều kiện vận hành | Nêu giới hạn, mở rộng từng bước |
| “Không đạt chỉ số thì cố xây thêm tính năng.” | Có thể giải quyết sai vấn đề trong thời gian dài | Xem lại giả định gốc và bằng chứng người dùng |
| “Đã hoàn thành nhiều story thì đã xác thực nhu cầu.” | Story hoàn thành đo output, không chứng minh outcome | Liên kết Product Backlog với mục tiêu học và hành vi |
| “Một con số tốt là đủ.” | Có thể bỏ qua lỗi, chi phí hoặc tác dụng phụ | Dùng tín hiệu chính cùng guardrails |
| “Đã thử rồi thì phải theo ý tưởng đến cùng.” | Chi phí chìm làm nhóm chậm thay đổi | Ghi tiêu chí quyết định trước và sẵn sàng dừng |

## 15. Bài tập vận dụng

### Bài tập 1 — Chọn giả định rủi ro nhất

Một nhóm muốn thêm gợi ý khóa học bằng AI vào nền tảng học trực tuyến. Họ đưa ra bốn giả định:

1. Người học khó chọn khóa phù hợp vì quá nhiều lựa chọn.
2. Gợi ý tự động sẽ khiến người học bắt đầu học thường xuyên hơn.
3. Mô hình có thể xử lý một triệu yêu cầu mỗi phút.
4. Giao diện gợi ý cần có hoạt ảnh phức tạp mới hấp dẫn.

**Yêu cầu:** chọn giả định nên kiểm chứng trước, giải thích theo **độ bất định và hậu quả nếu sai**, rồi đề xuất một phép thử nhỏ.

**Gợi ý:** thường nên làm rõ vấn đề lựa chọn và hành vi học trước khi xây hạ tầng AI quy mô lớn. Có thể thử gợi ý do người phụ trách nội dung tuyển chọn cho một nhóm nhỏ, minh bạch về cách gợi ý, rồi đo tỷ lệ bắt đầu và tiếp tục học; đừng mặc định AI cần thiết.

### Bài tập 2 — Tìm lát cắt dọc tối thiểu

Nhóm muốn làm tính năng **đăng ký nhận bản tin hàng tuần**. Danh sách ban đầu gồm đăng ký, hủy đăng ký, gợi ý chủ đề cá nhân hóa, AI viết nội dung, dashboard phân tích, nhắc qua SMS và thiết kế nhiều mẫu email.

**Yêu cầu:**

1. Viết một giả thuyết có thể kiểm chứng về nhu cầu nhận bản tin.
2. Chọn phạm vi cho bản thử đầu tiên có luồng dùng được.
3. Nêu ít nhất ba acceptance criteria, bao gồm xử lý quyền nhận email và hủy nhận.
4. Chọn tín hiệu hành vi liên quan đến giá trị; đừng chỉ đếm số email đã gửi.

**Gợi ý:** có thể thử đăng ký chủ động, gửi bản tin qua một kênh và hủy đăng ký rõ ràng. Tùy câu hỏi, theo dõi tỷ lệ đăng ký, phản hồi và tỷ lệ quay lại học có thể hữu ích hơn số email phát ra.

### Bài tập 3 — Phân biệt output và outcome

Trong một Sprint, nhóm hoàn thành 12 story point về trang tìm kiếm. Sau phát hành, người dùng vẫn thường không tìm được sản phẩm mong muốn.

**Yêu cầu:** chỉ rõ output, outcome mong muốn, giả định chưa kiểm chứng và hai loại bằng chứng cần thu thập. Đề xuất một thay đổi nhỏ trong Product Backlog.

**Gợi ý:** story point không cho biết người dùng tìm đúng thứ họ cần. Có thể quan sát truy vấn không kết quả, tỷ lệ chọn đúng sản phẩm hoặc thực hiện kiểm thử tìm kiếm trên nhiệm vụ cụ thể.

### Bài tập 4 — Đọc số liệu thử nghiệm đúng mức

Giả sử nhóm nhắc lịch bằng email có 13/60 lịch vắng; nhóm so sánh có 18/60 lịch vắng.

**Yêu cầu:** tính hai tỷ lệ, chênh lệch theo **điểm phần trăm** và mức giảm **tương đối**; rồi nêu ít nhất ba lý do chưa được tuyên bố tác động chắc chắn cho toàn bộ người dùng.

**Gợi ý:** khoảng 21,7% so với 30%; chênh khoảng 8,3 điểm phần trăm và giảm tương đối khoảng 27,8%. Cần xem cỡ mẫu, cách phân nhóm, phân khúc, thời gian đo và tác dụng phụ.

### Bài tập 5 — Viết một thẻ thử nghiệm

Điền mẫu cho tính năng bạn đang xây dựng:

~~~text
Vấn đề người dùng:
Giả định có rủi ro cao:
Giả thuyết có thể kiểm chứng:
Nhóm người dùng đủ điều kiện:
Phần sản phẩm nhỏ nhất cần thiết:
Những gì chủ động chưa xây:
Acceptance criteria và Definition of Done liên quan:
Tín hiệu outcome chính:
Tín hiệu bảo vệ:
Thời điểm xem lại và giới hạn bằng chứng:
Quyết định tiếp theo nếu tốt / chưa rõ / không tốt:
~~~

**Cách tự kiểm tra:** nếu xóa đi tính năng phụ mà vẫn thu được bằng chứng về giả thuyết, nên cân nhắc để tính năng đó sang bước sau. Ngược lại, nếu không thể quan sát điều giả thuyết dự đoán, phạm vi thử có thể còn **quá nhỏ hoặc đo sai đối tượng**.

## 16. Tổng kết

Tìm **phần sản phẩm nhỏ nhất để kiểm chứng một giả định** là kỹ năng cốt lõi của phát triển Agile dựa trên phản hồi sớm và giao giá trị tăng dần.

Hãy nhớ trình tự:

1. **Bắt đầu từ vấn đề và giá trị người dùng**, không bắt đầu từ danh sách công nghệ hoặc tính năng.
2. **Liệt kê giả định** và chọn điều vừa bất định vừa gây hậu quả đáng kể nếu sai.
3. **Viết giả thuyết có thể kiểm chứng**, xác định hành vi mục tiêu và giới hạn bằng chứng.
4. **Chọn phép thử tối thiểu nhưng đủ sức trả lời**; phỏng vấn hoặc prototype khi phù hợp, vertical slice chạy thật khi cần quan sát hành vi thực.
5. **Giữ chất lượng và sự tin cậy**: DoD, quyền riêng tư, tính minh bạch và khả năng xử lý lỗi không bị bỏ qua vì thử nhỏ.
6. **Đọc dữ liệu cùng bối cảnh**, so sánh outcome với output và quan sát tác dụng phụ.
7. **Đưa ra quyết định mới** từ điều vừa học: mở rộng, thử giả định kế tiếp, điều chỉnh hướng hoặc dừng.

Scrum giúp nhóm kiểm tra Increment theo nhịp, Kanban giúp quan sát dòng công việc đến bằng chứng, còn XP hỗ trợ thay đổi phần mềm an toàn. Không phương pháp nào thay thế cho câu hỏi trung tâm:

> **“Điều quan trọng nhất mà ta chưa biết là gì, và phần nhỏ nhất nào đủ giúp ta đưa ra quyết định tiếp theo một cách có trách nhiệm?”**

### Tài liệu tham khảo và đọc thêm

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 Principles](https://agilemanifesto.org/principles.html): giao giá trị sớm, chào đón thay đổi và điều chỉnh qua phản hồi.
- [The Scrum Guide](https://scrumguides.org/scrum-guide.html): Product Goal, Product Backlog, Increment, Definition of Done, kiểm tra và thích ứng.
- [The Lean Startup — Eric Ries](https://theleanstartup.com/): tư duy thử giả thuyết và học hỏi được kiểm chứng, khái niệm MVP.
- [The Kanban Guide](https://kanbanguides.org/): quản lý dòng công việc và các phép đo hỗ trợ khả năng dự báo.
- [Agile Alliance — Extreme Programming](https://agilealliance.org/glossary/xp/): thực hành kỹ thuật giúp tạo thay đổi nhỏ, có phản hồi sớm.
