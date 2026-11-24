# Xử lý bất đồng kỹ thuật, ưu tiên và cách làm

Hai lập trình viên có thể cùng muốn sản phẩm ổn định nhưng đề xuất kiến trúc khác nhau. Product Owner muốn giao chức năng đúng thời điểm thị trường cần, trong khi nhóm phát triển lo ngại rủi ro kỹ thuật. Một số thành viên thích lập trình cặp để chia sẻ kiến thức; người khác muốn giữ thời gian tập trung cá nhân. Những khác biệt ấy rất thường gặp trong phát triển phần mềm.

**Bất đồng không tự động là dấu hiệu một nhóm hoạt động kém.** Một ý kiến trái chiều được trình bày kịp thời có thể giúp phát hiện rủi ro, giả định sai hoặc cơ hội tạo giá trị chưa được nhìn thấy. Vấn đề xuất hiện khi nhóm biến khác biệt quan điểm thành công kích cá nhân, né tránh trao đổi, kéo dài tranh luận không có tiêu chí kết thúc hoặc ra quyết định mà không rõ ai chịu trách nhiệm.

Bài học thuộc chương **Cộng tác và lãnh đạo** của module **AGILE_DEVELOPMENT**. Agile hướng tới việc thích ứng với thay đổi qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục. Muốn làm được điều đó, nhóm phải biết xử lý **bất đồng về giải pháp kỹ thuật, thứ tự ưu tiên và phương pháp làm việc** mà vẫn bảo vệ mục tiêu sản phẩm, sự tôn trọng lẫn nhau và chất lượng phần mềm.

Sau bài này, bạn có thể:

- Phân loại bất đồng kỹ thuật, bất đồng ưu tiên và bất đồng về cách làm; xác định vấn đề, lợi ích và ràng buộc đằng sau các ý kiến.
- Dùng một quy trình ra quyết định rõ ràng: làm rõ, thu thập bằng chứng, so sánh phương án, quyết định, ghi nhận và kiểm chứng.
- Phân biệt vai trò của Product Owner, Developers, Scrum Master và các bên liên quan khi có bất đồng trong Scrum.
- Chọn cách ra quyết định phù hợp: trao đổi chuyên môn, đồng thuận, ủy quyền, thử nghiệm ngắn hoặc chuyển cấp theo rủi ro.
- Dùng backlog, user story, Definition of Done, Sprint Goal, bảng Kanban và dữ liệu luồng công việc để giảm tranh luận cảm tính.
- Thực hành phản hồi tôn trọng, ghi lại quyết định kỹ thuật và cải tiến cách phối hợp sau xung đột.

## 1. Hiểu bản chất của một bất đồng trong nhóm Agile

**Bất đồng (disagreement)** là tình huống các bên có nhận định, ưu tiên, giả định, mục tiêu gần hoặc đề xuất hành động khác nhau. Bất đồng có thể xảy ra mà không có mâu thuẫn cá nhân. **Xung đột (conflict)** là khi những khác biệt đó gây căng thẳng, cản trở phối hợp hoặc khiến một bên cảm thấy lợi ích của mình bị đe dọa.

Ví dụ, hai người tranh luận nên dùng truy vấn cơ sở dữ liệu trực tiếp hay thêm cache chưa chắc đang xung đột. Họ có thể chỉ đang tối ưu hai điều khác nhau: **độ đơn giản hiện tại** và **khả năng chịu tải trong tương lai**.

### 1.1. Ba tầng cần tách bạch

| Tầng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Dữ kiện** | Điều gì đã được quan sát hoặc xác nhận? | Truy vấn hiện tại mất 250 ms ở tải được đo; 95% yêu cầu dưới giới hạn đã thỏa thuận. |
| **Giả định/diễn giải** | Chúng ta đang suy luận điều gì từ dữ kiện? | “Số người dùng quý sau sẽ tăng gấp mười.” |
| **Lựa chọn/ưu tiên** | Chúng ta muốn làm gì và đánh đổi điều gì? | Thêm cache ngay hay đo tải thêm và tối ưu truy vấn trước. |

Nếu không phân biệt ba tầng này, nhóm dễ nói “phương án của tôi đúng” khi thực tế mỗi người đang dựa trên một giả định khác nhau.

### 1.2. Bất đồng về công việc và bất đồng về quan hệ

**Bất đồng về công việc** tập trung vào vấn đề, phương án và bằng chứng. Ví dụ: “Đọc dữ liệu bằng sự kiện có thể gây độ trễ đồng bộ; cần xác định yêu cầu nhất quán.”

**Bất đồng về quan hệ** liên quan đến cách đánh giá hoặc đối xử với cá nhân. Ví dụ: “Bạn luôn thiết kế quá phức tạp và chẳng hiểu sản phẩm.”

Bất đồng về công việc có thể hữu ích nếu nhóm giữ an toàn tâm lý, biết lắng nghe và ra quyết định minh bạch. Khi chuyển sang quy chụp về con người, nhóm nên dừng cách trao đổi đó và quay về mục tiêu, dữ liệu cùng hành vi có thể quan sát.

### 1.3. Xử lý bất đồng không có nghĩa mọi người phải nghĩ giống nhau

Một quyết định có chất lượng không bắt buộc nhận được sự yêu thích tuyệt đối. Điều quan trọng là các ý kiến liên quan đã được nghe, rủi ro quan trọng được kiểm tra, quyền quyết định rõ ràng và mọi người hiểu vì sao nhóm chọn hướng thực hiện.

Có thể thống nhất theo tinh thần:

> “Tôi vẫn có lo ngại về phương án A. Tôi đã ghi lại điều kiện cần theo dõi và đồng ý hỗ trợ quyết định chung trong giai đoạn thử, trừ khi có bằng chứng mới hoặc rủi ro nghiêm trọng xuất hiện.”

Đây là **cam kết thực hiện sau quyết định**, không phải yêu cầu thành viên che giấu phản đối về bảo mật, pháp lý hay nguy cơ gây hại.

## 2. Nhận diện đúng loại bất đồng

Ba nhóm bất đồng thường chồng lấp nhau. Việc phân loại giúp chọn tiêu chí và người tham gia phù hợp.

| Loại | Ví dụ điển hình | Câu hỏi quan trọng | Bằng chứng hữu ích |
| --- | --- | --- | --- |
| **Kỹ thuật** | Chọn cơ sở dữ liệu, API đồng bộ hay sự kiện, cấu trúc module, mức độ tự động hóa kiểm thử. | Phương án nào đáp ứng yêu cầu chức năng và phi chức năng với rủi ro, chi phí hợp lý? | Benchmark, đặc tả giao tiếp, lỗi thực tế, tải, khả năng bảo trì, PoC. |
| **Ưu tiên sản phẩm** | Sửa lỗi quan trọng hay giao tính năng mới; làm báo cáo hay cải thiện chuyển đổi. | Điều gì mang lại giá trị hoặc giảm rủi ro lớn nhất vào thời điểm này? | Product Goal, tác động khách hàng, mức nghiêm trọng, dữ liệu sử dụng, hạn bắt buộc, chi phí trì hoãn. |
| **Cách làm việc** | Họp hay cập nhật bất đồng bộ, review code theo cặp hay qua pull request, quy tắc WIP. | Cách phối hợp nào làm tăng chất lượng, tốc độ phản hồi và tính bền vững? | Cycle time, thời gian chờ, lỗi, mức tải, phản hồi nhóm, kết quả thử quy trình. |

Có những tình huống cần giải quyết hai loại cùng lúc. Ví dụ, Product Owner muốn giao tính năng thanh toán mới trước hội nghị, Developers cảnh báo rủi ro bảo mật, và nhóm bất đồng về việc có nên làm thêm một vòng kiểm thử. **Ưu tiên và giải pháp kỹ thuật phải được thảo luận cùng nhau**, nhưng trách nhiệm quyết định và các ràng buộc bắt buộc vẫn cần rõ.

### Dấu hiệu bất đồng đang trở thành vấn đề

- Cùng một chủ đề xuất hiện nhiều lần nhưng không có quyết định hay tiêu chí kết thúc.
- Quyết định được thay đổi qua tin nhắn riêng mà những người bị ảnh hưởng không được biết.
- Công việc chờ phê duyệt lâu, backlog liên tục đảo thứ tự nhưng không có lý do được ghi nhận.
- Người tham gia không dám nêu rủi ro, hoặc phản biện bị coi là không hợp tác.
- Một người tự triển khai giải pháp dù biết các bên chưa thống nhất tiêu chí quan trọng.
- Tranh luận xoay quanh chức danh, thâm niên, cảm xúc thay vì nhu cầu và bằng chứng.

Khi thấy những dấu hiệu này, nhóm nên xử lý **cơ chế ra quyết định** cùng với vấn đề cụ thể.

## 3. Nguyên tắc nền tảng: mục tiêu chung, tôn trọng và minh bạch

### 3.1. Bắt đầu từ kết quả cần đạt

Trong Agile, mục tiêu chung có thể là **Product Goal**, **Sprint Goal**, kết quả người dùng cần đạt hoặc một ràng buộc chất lượng. Nếu các bên chỉ nói về giải pháp yêu thích, họ dễ bỏ qua điều đang tối ưu.

Ví dụ:

- Đề xuất A: “Chúng ta phải viết lại service đăng ký.”
- Đề xuất B: “Không cần viết lại, chỉ tối ưu query.”

Hãy hỏi: **“Trong hai tuần tới, chúng ta cần cải thiện điều gì? Giảm lỗi đăng ký, giảm độ trễ hay tăng tốc độ thêm tính năng?”** Khi mục tiêu rõ, phương án dễ được đánh giá công bằng hơn.

### 3.2. Phản biện giả thuyết, không công kích người nói

Nên nói: “Ở mức 500 yêu cầu mỗi giây, thử nghiệm này vượt ngưỡng độ trễ; chúng ta kiểm tra kết quả với mẫu tải khác nhé.”

Tránh nói: “Thiết kế này dở vì bạn thiếu kinh nghiệm.”

Phát biểu thứ nhất mô tả quan sát, rủi ro và đề nghị kiểm tra; phát biểu thứ hai đánh giá phẩm chất con người và không giúp sửa thiết kế.

### 3.3. Thể hiện sự không chắc chắn

Có thể dùng các mức độ:

- **Đã xác nhận:** điều được đo, kiểm chứng hoặc có quy định rõ.
- **Giả định có cơ sở:** có dữ liệu gợi ý nhưng cần kiểm tra thêm.
- **Chưa biết:** chưa có bằng chứng đáng tin; cần điều tra.
- **Sở thích hoặc nguyên tắc nhóm:** quan điểm về cách làm, có thể hợp lý trong bối cảnh riêng.

Việc nói “tôi chưa biết” giúp giảm tranh luận tự vệ và mở ra thử nghiệm hữu ích.

### 3.4. Đưa ý kiến của người bị ảnh hưởng vào quyết định

Không phải quyết định nào cũng cần họp toàn công ty. Tuy nhiên, khi thay đổi ảnh hưởng nhóm vận hành, bảo mật, trải nghiệm người dùng hay một đội dùng chung API, những bên đó cần cơ hội nêu rủi ro đúng lúc.

**Được tham vấn** không nhất thiết đồng nghĩa với **có quyền phủ quyết**. Quyền quyết định cần được xác định theo trách nhiệm, mức độ rủi ro và cách tổ chức.

### 3.5. Bảo vệ việc nêu cảnh báo nghiêm trọng

Bất đồng về sở thích thư viện có thể giải quyết bằng thử nghiệm ngắn. Cảnh báo có căn cứ về mất dữ liệu, lộ thông tin, tính hợp pháp hoặc sự cố người dùng nghiêm trọng phải được đánh giá theo cơ chế kiểm soát và trách nhiệm liên quan. Không dùng bỏ phiếu đa số để bỏ qua yêu cầu bắt buộc.

## 4. Quy trình bảy bước xử lý bất đồng

Đây là một quy trình thực hành gợi ý, có thể rút gọn khi vấn đề nhỏ. Mục tiêu là đi từ **ý kiến khác nhau** tới **quyết định có thể kiểm chứng và thực hiện được**.

~~~mermaid
flowchart TD
    A["Nhận diện bất đồng"] --> B["1. Nêu vấn đề và mục tiêu chung"]
    B --> C["2. Tách dữ kiện, giả định và sở thích"]
    C --> D["3. Xác định người chịu trách nhiệm và các bên ảnh hưởng"]
    D --> E["4. Đề xuất phương án, tiêu chí và bằng chứng"]
    E --> F{"Đủ cơ sở quyết định?"}
    F -->|Chưa| G["Thử nghiệm hoặc thu thập thông tin có giới hạn"]
    G --> E
    F -->|Đủ| H["5. Quyết định và ghi nhận đánh đổi"]
    H --> I["6. Thực hiện, theo dõi tín hiệu"]
    I --> J["7. Xem lại khi đủ dữ liệu hoặc điều kiện đổi"]
    J --> K{"Cần điều chỉnh?"}
    K -->|Có| B
    K -->|Không| L["Giữ quyết định, chia sẻ điều đã học"]
~~~

### Bước 1 — Phát biểu vấn đề không cài sẵn giải pháp

Thay vì “Có nên chuyển toàn bộ hệ thống sang microservices không?”, hãy thử:

> “Chúng ta đang gặp khó khăn khi triển khai thay đổi ở phần nào, mức độ ảnh hưởng thế nào và cần cải thiện kết quả gì?”

Mô tả được vấn đề giúp xem liệu kiến trúc lớn có cần thiết hay một thay đổi nhỏ hơn đã đủ.

### Bước 2 — Phân tách điều biết và điều chưa biết

Ghi riêng:

- **Dữ kiện:** ví dụ, thời gian triển khai trung bình, tỷ lệ lỗi, độ trễ đo được.
- **Giả định:** ví dụ, tải sẽ tăng gấp bốn, việc chia service sẽ giảm phụ thuộc.
- **Giá trị ưu tiên:** ví dụ, giảm thời gian giao hàng, bảo đảm tính toàn vẹn dữ liệu.
- **Ràng buộc:** ví dụ, hạn tuân thủ, ngân sách, nhân sự vận hành, khả năng quay lại phương án cũ.

Đừng làm nhiều phân tích hơn giá trị của quyết định. Những việc dễ đảo ngược, ít rủi ro có thể chọn thử nhanh.

### Bước 3 — Làm rõ quyền quyết định

Ai chịu trách nhiệm cuối cùng cho thứ tự ưu tiên? Ai chịu trách nhiệm về cách xây dựng? Ai cần phê duyệt bảo mật hoặc thay đổi vận hành? Nếu chưa rõ, hãy làm rõ trước khi tiếp tục tranh luận, vì nhóm có thể đã đồng ý về nội dung nhưng không đồng ý về quyền ra quyết định.

### Bước 4 — So sánh các phương án khả thi

Tìm tối thiểu một phương án khác, kể cả **chưa thay đổi ngay và đo thêm**. Đối chiếu với cùng tiêu chí, cùng điều kiện thử. Hạn chế thiên vị phương án do người có vị trí cao đưa ra.

### Bước 5 — Đưa ra quyết định với thời điểm kết thúc rõ

Khi đủ thông tin, người hoặc nhóm có trách nhiệm quyết định cần nêu:

- Phương án được chọn và vì sao.
- Phương án bị loại và lý do chính.
- Rủi ro còn lại; cách phát hiện và xử lý.
- Người chịu trách nhiệm thực hiện.
- Thời điểm hoặc điều kiện cần xem lại.

Quyết định không cần dài, nhưng đủ để người vắng mặt hiểu bối cảnh.

### Bước 6 — Hành động thống nhất, vẫn giữ kênh phản hồi

Các thành viên thực hiện theo quyết định trong phạm vi đã thống nhất, đồng thời ghi nhận bằng chứng mới. Nếu thấy tình huống vượt ranh giới an toàn, cần kích hoạt cơ chế xử lý tương ứng thay vì chờ kỳ họp tiếp theo.

### Bước 7 — Kiểm chứng và cải tiến cách ra quyết định

Xem kết quả thực tế có đạt mục tiêu không. Phân biệt **quyết định tốt trong điều kiện thông tin cũ** với **kết quả không như kỳ vọng vì hoàn cảnh thay đổi**. Mục tiêu là học để quyết định tốt hơn, không tìm người đổ lỗi.

## 5. Chọn phương pháp ra quyết định phù hợp

Không có một cách duy nhất thích hợp cho mọi bất đồng.

| Cách quyết định | Khi nào nên dùng | Lưu ý |
| --- | --- | --- |
| **Chuyên gia/người chịu trách nhiệm quyết định sau tham vấn** | Phạm vi trách nhiệm rõ, cần quyết nhanh, đã nghe rủi ro liên quan. | Phải giải thích tiêu chí, tránh dùng chức danh để chặn phản biện có căn cứ. |
| **Đồng thuận (consensus)** | Ảnh hưởng lớn đến cách cả nhóm phối hợp và cần cam kết chung lâu dài. | Tốn thời gian; không biến yêu cầu đồng thuận thành quyền trì hoãn vô hạn. |
| **Đồng ý đủ để thử (consent)** | Phương án đảo ngược được, rủi ro được kiểm soát, không có phản đối có căn cứ chưa xử lý. | “Không phản đối hợp lý” không có nghĩa mọi người đều yêu thích phương án. |
| **Thử nghiệm có thời hạn (timebox/experiment)** | Hai giải pháp đều có lý; thiếu bằng chứng nhưng có thể thử an toàn. | Đặt giả thuyết, chỉ số và thời điểm kết thúc trước khi thử. |
| **Quyết định theo chính sách/quyền kiểm soát bắt buộc** | Bảo mật, pháp lý, vận hành nghiêm trọng, hợp đồng hay tiêu chuẩn an toàn. | Không lấy tốc độ hay phiếu bầu để vượt rào yêu cầu bắt buộc. |
| **Chuyển cấp (escalation)** | Vượt quyền hạn, tranh chấp liên nhóm, cần phân bổ ngân sách hoặc rủi ro không tự xử lý được. | Chuyển với bối cảnh và lựa chọn đã phân tích, tránh chỉ chuyển cảm xúc. |

**Đồng thuận**, **đồng ý đủ để thử** và **bỏ phiếu đa số** không phải một khái niệm. Bỏ phiếu có thể giúp nhóm khảo sát mức ưa thích nhưng không tự bảo đảm lựa chọn đúng kỹ thuật hoặc hợp quy định.

### Khi nào cần thí nghiệm thay vì tranh luận tiếp?

Giả sử hai phương án đều đáp ứng yêu cầu nhưng chưa rõ chi phí vận hành. Có thể so sánh bằng một proof of concept (PoC) có giới hạn, chạy benchmark trong điều kiện tương đương và ghi lại điều kiện lựa chọn.

Một thử nghiệm tốt nên có:

1. Giả thuyết và câu hỏi cần trả lời.
2. Phạm vi đủ nhỏ; không gây rủi ro không kiểm soát.
3. Phương pháp đo được thống nhất trước.
4. Giới hạn thời gian hoặc mức nỗ lực.
5. Tiêu chí dừng và người quyết định sau khi có kết quả.

Nếu thiếu tiêu chí dừng, “thử thêm” có thể chỉ là cách kéo dài bất đồng.

## 6. Bất đồng kỹ thuật: từ sở thích kiến trúc tới tiêu chí kiểm chứng

### Tình huống: có nên thêm hàng đợi sự kiện?

Một hệ thống đăng ký khóa học đang cập nhật trạng thái đăng ký và gửi email xác nhận. Hai lập trình viên bất đồng:

- **Phương án A:** xử lý đăng ký và yêu cầu gửi email qua luồng đồng bộ hiện tại.
- **Phương án B:** sau khi lưu đăng ký, phát sự kiện và xử lý email bất đồng bộ bằng hàng đợi.

Người ủng hộ B lo email chậm khiến toàn bộ yêu cầu đăng ký kéo dài; người ủng hộ A lo hàng đợi làm tăng độ phức tạp vận hành và nguy cơ xử lý lặp. Cả hai nêu rủi ro có thật.

### 6.1. Đặt mục tiêu và điều kiện thành công

Nhóm có thể thống nhất:

> “Học viên chỉ được báo đăng ký thành công khi dữ liệu đăng ký đã được lưu đúng. Email có thể tới chậm trong giới hạn được chấp nhận. Việc gửi email lỗi không được gây mất đăng ký hoặc gửi trùng không kiểm soát.”

Đây là mục tiêu nghiệp vụ/kỹ thuật giúp định hướng thảo luận. Nhóm cần làm rõ ngưỡng thời gian, tần suất thất bại và điều kiện vận hành theo sản phẩm cụ thể.

### 6.2. So sánh phương án

| Tiêu chí | Luồng đồng bộ | Hàng đợi sự kiện |
| --- | --- | --- |
| Độ đơn giản triển khai ban đầu | Thường ít thành phần hơn. | Cần broker/queue, worker và cơ chế quan sát. |
| Tác động khi dịch vụ email chậm | Có thể ảnh hưởng thời gian phản hồi nếu chờ đồng bộ. | Có thể tách khỏi phản hồi đăng ký nếu thiết kế đúng. |
| Nhất quán kết quả đăng ký | Có thể dễ theo dõi trong một luồng; vẫn cần xác định điểm commit. | Cần bảo đảm sự kiện gắn với thay đổi dữ liệu, tránh mất sự kiện. |
| Xử lý lỗi và lặp | Có thể dùng retry trong phạm vi thích hợp. | Cần idempotency, retry và chính sách xử lý sự kiện lỗi. |
| Chi phí vận hành | Ít thành phần hơn nhưng có thể gắn chặt các phụ thuộc. | Tăng vận hành, theo dõi hàng đợi và khả năng xử lý lại. |

Bảng chỉ thể hiện **đánh đổi phổ biến**, chưa đủ để kết luận phương án nào phù hợp. Nhóm cần đo độ trễ hiện tại, tần suất lỗi email, giới hạn hạ tầng, nguồn lực bảo trì và yêu cầu nghiệp vụ thật.

### 6.3. Thiết kế thử nghiệm nhỏ

Ví dụ, nhóm kiểm tra độ trễ ở tải đại diện, mô phỏng dịch vụ email chậm và đo tác động tới xác nhận đăng ký. Nếu hướng hàng đợi được chọn, cần thử điều kiện worker nhận trùng sự kiện và kiểm soát việc gửi email lặp.

Khi chưa có bằng chứng tải thật và hệ thống hiện tại đủ ổn, nhóm cũng có thể quyết định **giữ thiết kế đơn giản, bổ sung cơ chế timeout/giám sát trước và đặt điều kiện xem lại**.

### 6.4. Ghi lại quyết định

Một **Architecture Decision Record (ADR)** ngắn có thể dùng cấu trúc:

~~~text
Tiêu đề: Xử lý gửi email sau đăng ký khóa học
Trạng thái: Đã quyết định / Đang thử / Được thay thế
Bối cảnh: Vấn đề, dữ liệu, ràng buộc và tác động
Các phương án: Đồng bộ; hàng đợi; cải tiến tối thiểu trước
Tiêu chí: Tính đúng dữ liệu, độ trễ, xử lý lỗi, vận hành
Quyết định: Phương án chọn và người chịu trách nhiệm
Lý do: Bằng chứng và đánh đổi quan trọng
Rủi ro còn lại: Giả định chưa kiểm chứng, kế hoạch xử lý
Xem lại khi: Một chỉ số vượt ngưỡng hoặc bối cảnh thay đổi
~~~

ADR không nhất thiết cần hệ thống phức tạp. Một tệp ngắn, dễ tìm và được liên kết từ công việc liên quan đã có thể giúp những người khác hiểu **vì sao một thiết kế tồn tại**.

### Kết luận của tình huống

Kết quả tốt không phải “người ủng hộ A/B thắng”. Kết quả tốt là nhóm lựa chọn được thiết kế đáp ứng ràng buộc với mức độ rủi ro và chi phí phù hợp, biết **khi nào cần xem lại** khi xuất hiện dữ liệu mới.

## 7. Bất đồng về ưu tiên: giá trị, rủi ro và quyền quyết định

### Tình huống: tính năng mới đối đầu với lỗi sản xuất

Product Owner muốn hoàn tất chức năng xuất chứng chỉ trước buổi giới thiệu sản phẩm. Developers phát hiện một số học viên nhận sai trạng thái hoàn thành khóa học. Đội hỗ trợ nhận nhiều phản ánh; sửa lỗi có thể ảnh hưởng kế hoạch tính năng.

Tranh luận dễ bế tắc:

- “Khách hàng đang chờ tính năng, không thể trễ.”
- “Không thể thêm tính năng trên một hệ thống còn lỗi.”
- “Lỗi chỉ xảy ra ở một số người, để Sprint sau.”

Thay vì so khối lượng tiếng nói, nhóm nên phân tích:

| Khía cạnh | Câu hỏi cần làm rõ |
| --- | --- |
| **Mức độ nghiêm trọng** | Lỗi có làm sai dữ liệu, ảnh hưởng quyền lợi người học, gây rủi ro pháp lý hoặc mất niềm tin không? |
| **Phạm vi ảnh hưởng** | Bao nhiêu người dùng bị ảnh hưởng, có cách xác định và hỗ trợ họ không? |
| **Giá trị của tính năng** | Hạn ra mắt có phải cam kết thực tế? Trì hoãn gây hậu quả nào? |
| **Giải pháp giảm rủi ro** | Có thể khắc phục lỗi nhỏ trước, hạn chế phát hành hoặc tạm dừng chứng chỉ không? |
| **Chi phí và phụ thuộc** | Cần bao lâu, ai có năng lực xử lý, thử nghiệm hồi quy nào phải chạy? |
| **Mục tiêu hiện tại** | Điều gì phù hợp Product Goal và Sprint Goal; cần điều chỉnh phạm vi nào? |

**Lỗi ảnh hưởng nghiêm trọng đến dữ liệu hoặc an toàn** có thể buộc nhóm xử lý theo quy trình sự cố/kiểm soát tương ứng. Với các yêu cầu cạnh tranh thông thường, Product Owner chịu trách nhiệm sắp thứ tự **Product Backlog**, đồng thời trao đổi với Developers và các bên liên quan về giá trị, rủi ro và tính khả thi.

### 7.1. Phân biệt quyền ưu tiên với quyền ép giải pháp

Trong Scrum:

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả, bao gồm thứ tự các mục backlog.
- **Developers** chịu trách nhiệm lập kế hoạch thực hiện, chất lượng và tạo Increment có thể sử dụng, đáp ứng Definition of Done.
- **Scrum Master** hỗ trợ Scrum Team nâng cao hiệu quả, giúp loại bỏ trở ngại và hướng dẫn thực hành Scrum; không mặc định là người áp đặt lựa chọn kỹ thuật hay thứ tự backlog.

Product Owner có thể yêu cầu thảo luận về giá trị và ưu tiên, nhưng không thể biến một thay đổi chưa đủ điều kiện chất lượng thành “Done” bằng quyết định đơn phương. Developers cũng không nên tự thay đổi thứ tự ưu tiên của sản phẩm mà không trao đổi về tác động với Product Owner.

### 7.2. Nếu bất đồng xảy ra giữa Sprint

Nhóm cần làm rõ mức độ ảnh hưởng tới **Sprint Goal**. Phạm vi công việc có thể được làm rõ và trao đổi lại với Product Owner khi học thêm thông tin, trong khi Sprint Goal giữ vai trò định hướng. Khi Sprint Goal trở nên lỗi thời, Scrum có cơ chế hủy Sprint do Product Owner quyết định; đây là tình huống đặc biệt, không phải giải pháp mặc định cho mỗi yêu cầu mới.

Đặt câu hỏi:

> “Nếu chúng ta xử lý sự cố trước, còn phần tối thiểu nào vẫn đạt mục tiêu Sprint? Nếu tiếp tục kế hoạch cũ, rủi ro đối với người dùng và sản phẩm là gì?”

Câu hỏi này giúp tạo **lựa chọn về phạm vi**, thay vì chỉ tranh luận phải chọn toàn bộ bên A hay toàn bộ bên B.

### 7.3. Không lạm dụng một công thức chấm điểm

Một số nhóm dùng giá trị kinh doanh, mức khẩn cấp, giảm rủi ro và nỗ lực để so sánh các backlog item. Điểm số có thể hỗ trợ trao đổi, nhưng không thay thế phán đoán và không tự giải quyết các nghĩa vụ bắt buộc. Đặc biệt, “độ lớn story point” không phải đơn vị tiền tệ và không đo giá trị kinh doanh trực tiếp.

## 8. Bất đồng về cách làm: biến đề xuất quy trình thành thử nghiệm

### Tình huống: review code đang chậm

Một nhóm có nhiều pull request chờ review hơn hai ngày. Hai đề xuất xuất hiện:

- **A:** yêu cầu mọi lập trình viên review code vào một khung giờ cố định hằng ngày.
- **B:** áp dụng lập trình cặp cho các thay đổi phức tạp để giảm thời gian chờ và phát hiện lỗi sớm.

Thay vì chọn ngay theo sở thích, nhóm có thể đặt giả thuyết: **“Giảm thời gian chờ review sẽ rút ngắn cycle time mà không tăng lỗi sau phát hành.”**

### 8.1. Xác định chính xác nút thắt

Cần quan sát:

- Tỷ lệ thời gian code chờ review so với thời gian thực hiện.
- Số mục đang làm dở và số reviewer sẵn có.
- Kích thước pull request; PR có quá lớn để review hiệu quả không?
- Lỗi phát sinh sau khi review; có bị yêu cầu sửa lại nhiều lần không?
- Cách trao đổi khi có bất đồng thiết kế trong PR.

Có thể nguyên nhân không nằm ở lịch review mà ở việc yêu cầu không rõ, nhiệm vụ quá lớn hoặc nhóm phụ thuộc một chuyên gia duy nhất.

### 8.2. Thử nhỏ với điều kiện đánh giá trước

Nhóm có thể thống nhất thử trong hai tuần:

1. Chia pull request theo phần hành vi nhỏ khi hợp lý.
2. Với PR bị chặn vì bất đồng thiết kế, hai bên trao đổi đồng bộ ngắn rồi ghi kết luận.
3. Mỗi ngày ưu tiên xử lý một số PR đang chờ trước khi mở thêm việc, theo chính sách WIP đã thống nhất.
4. Với việc rủi ro cao hoặc khó truyền đạt qua review, thử lập trình cặp khi phù hợp.
5. So sánh phân bố thời gian chờ, cycle time, lỗi và phản hồi nhóm.

**Một thử nghiệm quy trình không nhất thiết phải chính xác hai tuần.** Khoảng thời gian cần đủ để quan sát với khối lượng việc có ý nghĩa, đồng thời không kéo dài quá mức.

### 8.3. Bất đồng về quy trình thường cần đồng ý cùng thử

Nếu nhóm sẽ phải thực hiện một quy tắc chung mỗi ngày, người chịu tác động nên tham gia định nghĩa thử nghiệm và tiêu chí thành công. Không bắt buộc mọi người có sở thích giống nhau, nhưng cần biết quy tắc, lý do, thời điểm đánh giá và đường phản hồi.

Trong **Sprint Retrospective**, Scrum Team có thể nhìn lại kết quả thử và chọn cải tiến kế tiếp. Trong **Kanban**, các chính sách luồng rõ ràng và dữ liệu flow giúp đánh giá nên giữ, điều chỉnh hay bỏ quy tắc.

## 9. Lãnh đạo và điều phối khi bất đồng

Lãnh đạo trong môi trường Agile không chỉ là ra lệnh chọn phương án. Người điều phối tốt tạo điều kiện để nhóm làm rõ vấn đề, sử dụng chuyên môn phù hợp và ra quyết định với trách nhiệm minh bạch.

### 9.1. Vai trò của người điều phối

Người điều phối có thể là Scrum Master, thành viên nhóm, kỹ sư dẫn dắt hoặc người được cả nhóm thống nhất cho cuộc trao đổi. Vai trò chính:

- Làm rõ mục tiêu cuộc thảo luận và phạm vi cần quyết định.
- Mời các góc nhìn liên quan, nhất là người thường ít phát biểu.
- Ngắt hành vi công kích hoặc độc thoại kéo dài; yêu cầu quay về dữ kiện và vấn đề.
- Phân biệt phương án với ràng buộc bắt buộc.
- Nhắc người có thẩm quyền quyết định nêu kết luận rõ.
- Xác nhận hành động, người phụ trách và thời điểm đánh giá.

Người điều phối không nhất thiết là người **quyết định cuối cùng**. Việc nhầm hai vai trò có thể làm nhóm ít dám nêu ý kiến trái chiều.

### 9.2. Kỹ năng lắng nghe và diễn đạt lại

Một kỹ thuật đơn giản là **diễn đạt lại điều người khác đang lo ngại** trước khi phản biện:

> “Mình hiểu bạn ưu tiên tính nhất quán dữ liệu vì giao dịch đã ghi sai sẽ rất khó sửa. Mình đang lo về thời gian đáp ứng. Ta có thể xác định cả hai điều kiện rồi kiểm tra hai phương án không?”

Câu này không đồng ý vô điều kiện; nó xác nhận mối quan tâm chính để giảm hiểu nhầm.

### 9.3. Sử dụng phát biểu về quan sát và tác động

Thay vì:

> “Bạn luôn đẩy việc sang kiểm thử phút cuối.”

Có thể nói:

> “Hai story gần đây được chuyển sang kiểm thử vào cuối ngày cuối Sprint. Nhóm chưa đủ thời gian xác minh các trường hợp lỗi. Ta có thể làm rõ tiêu chí sẵn sàng kiểm thử và chia nhỏ story sớm hơn không?”

Cách thứ hai dựa trên hành vi quan sát, tác động cụ thể và đề nghị giải pháp. Điều này giúp giữ cuộc trao đổi trong phạm vi công việc.

### 9.4. Đưa tiếng nói thiểu số vào sổ rủi ro

Một quyết định đã được đưa ra không có nghĩa phản biện hợp lý cần bị xóa khỏi lịch sử. Nhóm có thể ghi:

- Lo ngại chưa được kiểm chứng.
- Dấu hiệu cho thấy phương án đang gặp vấn đề.
- Biện pháp hạn chế rủi ro.
- Điều kiện để xem xét lại quyết định.

Như vậy, những người bất đồng biết ý kiến được xem xét, còn nhóm có tín hiệu để thích ứng khi bối cảnh thay đổi.

## 10. Đưa bất đồng trở lại user story, backlog và Definition of Done

Một cách giảm tranh luận dai dẳng là chuyển ý kiến chung chung thành **hành vi có thể kiểm chứng**.

### 10.1. Ví dụ bất đồng về yêu cầu

Product Owner muốn luồng đặt lịch cho phép người dùng bấm xác nhận nhanh. Developers muốn kiểm tra trạng thái khung giờ ngay trước khi ghi nhận lịch. Đó không nhất thiết là hai mục tiêu loại trừ: cả hai cùng muốn đặt lịch nhanh **và** không bị trùng lịch.

Có thể viết user story:

> Là khách hàng đặt lịch tư vấn, tôi muốn nhận xác nhận rõ ràng rằng khung giờ đã được giữ thành công, để không đến nơi khi lịch chưa thực sự được đặt.

Ví dụ tiêu chí chấp nhận:

~~~gherkin
Feature: Xác nhận lịch hẹn

Scenario: Khung giờ vẫn còn trống
  Given khách hàng đang chọn một khung giờ hợp lệ
  And khung giờ vẫn còn chỗ tại thời điểm xác nhận
  When khách hàng xác nhận đặt lịch
  Then hệ thống ghi nhận đúng một lịch hẹn
  And hiển thị mã xác nhận cho khách hàng

Scenario: Khung giờ vừa được người khác đặt
  Given khách hàng đang chọn một khung giờ
  And khung giờ không còn chỗ tại thời điểm xác nhận
  When khách hàng xác nhận đặt lịch
  Then hệ thống không tạo lịch trùng
  And thông báo rõ để khách hàng chọn khung giờ khác
~~~

Từ đây, nhóm có thể cùng đánh giá thiết kế kỹ thuật bảo đảm điều kiện đúng, thay vì tranh cãi mơ hồ giữa “nhanh” và “an toàn”.

### 10.2. Story không thay thế tiêu chuẩn chất lượng

**Acceptance criteria** mô tả hành vi cụ thể cần đạt của user story. **Definition of Done** mô tả mức chất lượng và trạng thái hoàn tất áp dụng cho Increment, chẳng hạn tích hợp, kiểm thử và các điều kiện kỹ thuật được thống nhất. Không thể giải quyết tranh luận bằng cách bỏ bước chất lượng cần thiết chỉ vì story đã có vẻ chạy được.

### 10.3. Backlog ghi nhận đánh đổi và quyết định

Các mục backlog nên thể hiện đủ **vấn đề, người hưởng lợi, kết quả mong đợi và ràng buộc quan trọng**. Khi có phản hồi mới, Product Owner có thể sắp thứ tự lại Product Backlog theo giá trị và rủi ro. Developers giúp làm rõ độ phức tạp, phụ thuộc và khả năng thực hiện; người dùng/bên liên quan cung cấp bằng chứng về nhu cầu.

Backlog có chức năng hỗ trợ **đối thoại và ra quyết định**, không phải một danh sách mà mọi ý tưởng đều được cam kết xây.

## 11. Ghi nhận quyết định mà không tạo thêm quan liêu

Một số nhóm xử lý xong bất đồng bằng lời rồi gặp lại đúng tranh luận đó vài tuần sau vì không ai nhớ lý do ban đầu. Ghi lại quyết định ngắn gọn giúp duy trì hiểu biết chung, đặc biệt ở nhóm làm việc từ xa.

### Mẫu ghi nhận quyết định áp dụng chung

~~~text
Vấn đề cần quyết định:
Mục tiêu và kết quả mong đợi:
Người chịu trách nhiệm quyết định:
Người đã tham vấn:
Dữ kiện đã xác minh:
Giả định còn thiếu:
Các lựa chọn và đánh đổi:
Quyết định cùng lý do:
Rủi ro còn lại và biện pháp kiểm soát:
Người thực hiện, bước kế tiếp:
Chỉ số / điều kiện cần xem lại:
Ngày xem lại hoặc sự kiện kích hoạt:
~~~

Có thể dùng ADR cho quyết định kiến trúc, một ghi chú ngắn trên Product Backlog Item cho ưu tiên hoặc mục hành động của Retrospective cho quy trình. Chỉ ghi những gì người khác **cần để hiểu và thực hiện**; tránh tạo thủ tục ký duyệt mới nếu không có lý do thực tế.

### Phân biệt ba loại kết thúc

- **Đã quyết định:** chọn phương án và có người chịu trách nhiệm thực hiện.
- **Đang thử:** chưa cam kết dài hạn; có giả thuyết, phạm vi thử, tiêu chí đo và thời điểm xem lại.
- **Chưa đủ điều kiện quyết định:** biết cần thêm dữ kiện gì, ai thu thập và mốc đưa chủ đề trở lại.

“Để sau” mà không có người phụ trách và điều kiện xem lại thường khiến vấn đề tồn đọng.

## 12. Xử lý bất đồng trong nhóm từ xa và nhiều múi giờ

Trong nhóm phân tán, phản hồi chậm và thiếu ngữ cảnh có thể làm bất đồng căng thẳng hơn. Một dòng bình luận ngắn có thể được hiểu là bác bỏ cá nhân dù người viết chỉ đang chỉ ra lỗi kỹ thuật.

Một cách làm phù hợp:

1. **Viết rõ vấn đề trước:** mô tả bối cảnh, ảnh hưởng, mục tiêu, giả định và câu hỏi cần quyết.
2. **Đánh dấu mức khẩn:** phân biệt cảnh báo sự cố nghiêm trọng với thảo luận thiết kế có thể đợi.
3. **Cho người khác thời gian chuẩn bị:** chia sẻ đường dẫn, số liệu và phương án trước cuộc trao đổi khi khả thi.
4. **Trao đổi đồng bộ khi bất đồng khó giải quyết bằng văn bản:** cùng xem code, sơ đồ luồng hoặc prototype.
5. **Ghi lại kết quả bất đồng bộ:** người không dự họp vẫn thấy quyết định, lý do, người phụ trách.
6. **Giữ cơ chế đặt câu hỏi sau quyết định:** có nơi báo bằng chứng mới, không phụ thuộc hoàn toàn vào cuộc gọi kế tiếp.

Tương tác trực tiếp theo thời gian thực có lợi khi cần xử lý vấn đề nhiều bất định, nhưng **không bắt buộc mọi quyết định phải họp trực tiếp**. Lựa chọn hình thức giao tiếp dựa trên độ phức tạp, rủi ro và tính sẵn có của những người cần tham gia.

### Ví dụ: bình luận pull request đang nóng lên

Thay vì tiếp tục trao đổi 40 bình luận khó theo dõi, người tham gia có thể đề nghị:

> “Chúng ta đang lặp lại hai lo ngại: tính dễ kiểm thử và độ phức tạp cấu hình. Mình đề xuất cùng xem hai phương án 15 phút, xác định tiêu chí rồi ghi kết luận trong PR. Bạn có khung giờ phù hợp không?”

Cách này chuyển cuộc trao đổi từ **phản ứng qua lại** sang **cùng giải quyết bài toán**.

## 13. Đo xem cách xử lý bất đồng có tiến bộ không

Không nên đo số lượng bất đồng về 0. Một nhóm không có ý kiến trái chiều có thể đang thiếu cơ hội phản biện hoặc mọi người không dám nói ra vấn đề.

Nên đo xem quyết định có trở nên **rõ hơn, nhanh đủ mức cần thiết và tạo kết quả tốt hơn** hay không.

| Chỉ báo | Cách quan sát | Cảnh báo khi diễn giải |
| --- | --- | --- |
| **Thời gian chờ quyết định** | Thời gian từ khi phát hiện câu hỏi chặn công việc đến lúc có kết luận đủ để tiếp tục. | Quyết định quá nhanh nhưng thiếu kiểm soát có thể gây lỗi. |
| **Cycle time** | Thời gian công việc từ lúc bắt đầu tới lúc hoàn tất theo quy ước nhóm. | Bị ảnh hưởng bởi kích thước việc, WIP và các yếu tố khác. |
| **WIP và tuổi công việc** | Số việc đang làm dở, số ngày các mục bị chặn. | Không dùng con số đơn lẻ để đánh giá người làm. |
| **Công việc làm lại** | Số lỗi hoặc thay đổi do cách hiểu yêu cầu/thiết kế khác nhau. | Cần tách thay đổi hợp lý theo phản hồi mới khỏi lỗi do thiếu làm rõ. |
| **Chất lượng phát hành** | Lỗi lọt ra production, thời gian khắc phục và tác động người dùng. | Cần xem mức nghiêm trọng và phạm vi, không chỉ số lượng. |
| **Hiệu quả cải tiến quy trình** | Thử nghiệm có được đánh giá và đưa ra quyết định giữ/sửa/dừng không? | Số cuộc Retrospective không tự chứng minh cải tiến. |
| **Khả năng lên tiếng** | Thành viên biết cách nêu lo ngại và tin rằng cảnh báo được xem xét. | Khảo sát theo cách bảo vệ người tham gia; tránh xếp hạng cá nhân. |

**Ví dụ:** Trước khi thử quy tắc gỡ bất đồng qua trao đổi ngắn, các PR bị chặn vì thiết kế thường chờ ba ngày. Sau ba tuần, thời gian chờ trung vị còn một ngày và lỗi sau phát hành không tăng. Đây là tín hiệu tích cực, nhưng nhóm vẫn nên xem loại PR, lượng người review và biến động công việc trước khi kết luận cải tiến là nguyên nhân duy nhất.

### Liên hệ với Scrum và Kanban

Trong **Scrum**, Sprint Retrospective là dịp xem nhóm đã xử lý bất đồng ra sao, có cần đổi cách phối hợp hoặc làm rõ quyền quyết định không. Trong **Kanban**, bảng trực quan, chính sách WIP và số đo luồng giúp thấy nơi công việc bị chặn bởi quyết định chậm. Trong **XP**, thử nghiệm kỹ thuật nhỏ, kiểm thử tự động và trao đổi thường xuyên giúp giảm tranh luận thuần suy đoán.

Chỉ số nhằm **hỗ trợ học hỏi**, không làm công cụ gây áp lực để mọi người ngừng nêu cảnh báo.

## 14. Khi nào cần chuyển cấp hoặc xử lý khẩn cấp?

Không phải bất đồng nào cũng nên kéo dài để tìm đồng thuận. Những trường hợp sau cần phản ứng phù hợp với mức rủi ro:

### 14.1. Nguy cơ mất dữ liệu, lộ thông tin hoặc ảnh hưởng an toàn

Nếu có bằng chứng đáng tin về rủi ro nghiêm trọng, nhóm cần kích hoạt cơ chế ứng phó sự cố hoặc các đầu mối chuyên trách. Người nêu cảnh báo phải có cách trình bày bằng chứng và mức tác động; không nên bị ép “đồng ý theo đa số” khi vấn đề chưa được xử lý.

### 14.2. Vượt thẩm quyền hoặc vượt phạm vi một nhóm

Quyết định liên quan ngân sách lớn, hợp đồng, thay đổi chính sách dữ liệu hoặc gây phụ thuộc lên nhiều nhóm có thể cần cấp quản lý hoặc người có quyền chính thức. Chuẩn bị bối cảnh, các phương án, tác động và đề xuất để người quyết định có cơ sở.

### 14.3. Tranh luận bị cá nhân hóa hoặc có hành vi gây hại

Nếu xuất hiện công kích, đe dọa, phân biệt đối xử hoặc gây áp lực không phù hợp, cần xử lý theo cơ chế tổ chức, bảo vệ người bị ảnh hưởng và tách phần hành vi khỏi tranh luận kỹ thuật. Không yêu cầu người chịu ảnh hưởng tự thương lượng trực tiếp nếu không an toàn.

### 14.4. Công việc bị chặn quá thời hạn có thể chấp nhận

Khi bất đồng kéo dài làm đe dọa Sprint Goal, cam kết khách hàng hoặc vận hành sản phẩm, cần báo rõ tình trạng, tác động, quyền quyết định và lựa chọn khả thi. Chuyển cấp đúng lúc giúp tránh “để mọi người tự giải quyết” nhưng thực tế không ai có thẩm quyền kết thúc.

**Chuyển cấp không phải thất bại của tự quản.** Đó là cách xử lý vấn đề vượt thẩm quyền hoặc rủi ro của nhóm, miễn là sử dụng minh bạch và không thay thế mọi cuộc trao đổi chuyên môn thông thường.

## 15. Tình huống tổng hợp: một Sprint có ba bất đồng

Một nhóm Agile xây sản phẩm quản lý đăng ký khóa học. Sprint Goal được thống nhất là: **“Người học có thể đăng ký khóa học và nhận trạng thái đăng ký đáng tin cậy.”**

Giữa Sprint, phát sinh ba bất đồng:

1. **Kỹ thuật:** một người muốn dùng hàng đợi để gửi email; người khác muốn giữ đồng bộ vì thời gian triển khai ngắn.
2. **Ưu tiên:** Product Owner nhận yêu cầu thêm mã giảm giá trước sự kiện giới thiệu; Developers lo ảnh hưởng Sprint Goal.
3. **Cách làm:** các PR lớn đang chờ review; người thích lập trình cặp, người muốn review bất đồng bộ.

### 15.1. Cách xử lý tuần tự

**Bước 1 — giữ mục tiêu chung:** Cả nhóm nhắc lại phần quan trọng là lưu đăng ký đúng, phản hồi rõ trạng thái và có khả năng xác nhận tới người học. Mã giảm giá có thể có giá trị, nhưng cần xem có phục vụ Sprint Goal và hạn thực tế không.

**Bước 2 — tách vấn đề:** Kiến trúc email là lựa chọn kỹ thuật; mã giảm giá là lựa chọn ưu tiên và phạm vi; review PR là cách phối hợp. Mỗi vấn đề có tiêu chí và những người quyết định liên quan khác nhau.

**Bước 3 — thu thông tin tối thiểu:** Developers đo độ trễ gửi email và kiểm tra tình huống dịch vụ email lỗi. Product Owner hỏi bên liên quan về giá trị và cam kết của mã giảm giá. Nhóm xem thời gian chờ PR và mức độ sửa lại.

**Bước 4 — quyết định theo trách nhiệm:** Developers chọn thiết kế đáp ứng điều kiện chất lượng đã thống nhất. Product Owner cân nhắc thứ tự ưu tiên của backlog và thương lượng phạm vi Sprint với Developers. Scrum Master có thể giúp cuộc trao đổi rõ mục tiêu và tháo gỡ trở ngại, nhưng không tự áp đặt quyết định sản phẩm hay kiến trúc.

**Bước 5 — thử cải tiến quy trình:** Trong tuần còn lại, nhóm cố gắng chia PR nhỏ hơn và phối hợp review các mục chặn công việc. Các PR có bất đồng thiết kế kéo dài được đưa vào trao đổi ngắn, sau đó kết luận được ghi lại.

**Bước 6 — nhìn lại:** Ở Sprint Review, nhóm kiểm tra trải nghiệm đăng ký và phản hồi liên quan. Ở Retrospective, nhóm xem việc chọn phương án kỹ thuật, thương lượng phạm vi và thay đổi review đã ảnh hưởng tới luồng công việc ra sao.

### 15.2. Bảng quyết định minh họa

| Bất đồng | Mục tiêu cần bảo vệ | Quyết định có thể phù hợp nếu bằng chứng ủng hộ | Điểm xem lại |
| --- | --- | --- | --- |
| Đồng bộ hay hàng đợi | Đăng ký đúng, không bị phụ thuộc không cần thiết vào email. | Chọn phương án ít phức tạp nhất đáp ứng ngưỡng độ trễ và độ tin cậy thực tế. | Khi độ trễ hoặc lỗi vượt ngưỡng đã thống nhất. |
| Mã giảm giá hay Sprint Goal | Giao luồng đăng ký đáng tin cậy và đáp ứng giá trị kinh doanh. | Giữ Sprint Goal; ghi yêu cầu mới, đánh giá tính khẩn và thương lượng phạm vi khi cần. | Khi có thông tin chính thức về cam kết hoặc tác động. |
| Review bất đồng bộ hay lập trình cặp | Giao phần tăng trưởng đạt DoD với thời gian chờ hợp lý. | Thử phối hợp linh hoạt theo mức phức tạp của PR. | Sau khi có dữ liệu cycle time, review wait và lỗi. |

Không có phương án cố định phù hợp với mọi đội. Giá trị của tình huống là **cùng một Sprint có thể chứa ba loại bất đồng khác nhau; mỗi loại cần cách đưa ra quyết định tương ứng**.

## 16. Bài tập áp dụng

Bạn tham gia một nhóm phát triển ứng dụng đặt lịch khám. Trong Sprint hiện tại:

- Product Owner muốn ưu tiên xuất phiếu xác nhận đẹp để phục vụ buổi giới thiệu.
- Một lập trình viên phát hiện khả năng đặt trùng lịch khi nhiều người chọn cùng khung giờ.
- Hai thành viên tranh luận nên khóa giao dịch ở cơ sở dữ liệu hay xử lý qua hàng đợi.
- Việc review code thường chờ lâu; có đề nghị bắt buộc tất cả PR phải được duyệt bởi một trưởng nhóm kỹ thuật.
- Sprint Goal là cho phép người dùng đặt một lịch hợp lệ và nhận xác nhận rõ ràng.

### Nhiệm vụ

1. **Phân loại:** Chỉ ra vấn đề nào là bất đồng ưu tiên, kỹ thuật hoặc cách làm; trường hợp nào chồng lấp nhiều loại?
2. **Làm rõ sự thật:** Nêu ba dữ kiện còn thiếu trước khi chọn giải pháp chống đặt trùng.
3. **Đặt tiêu chí:** Viết ba điều kiện phải đáp ứng của tính năng đặt lịch, bao gồm trường hợp hai người xác nhận cùng một khung giờ.
4. **Quyền quyết định:** Ai nên tham gia quyết định thứ tự Product Backlog, ai quyết định cách xây phần mềm, ai giúp nhóm cải thiện phối hợp?
5. **Thử nghiệm:** Đề xuất một cách thử kỹ thuật và một cách thử giảm thời gian chờ review mà vẫn giữ chất lượng.
6. **Ghi nhận:** Viết ghi chú quyết định tối đa một trang, nêu mục tiêu, phương án, rủi ro và điều kiện xem lại.
7. **Phản hồi:** Chọn một chỉ số sản phẩm và hai chỉ số luồng công việc để biết các thay đổi có tạo cải thiện không.

### Gợi ý hướng giải

**Phân loại:** Đặt trùng lịch là vấn đề đúng đắn/khả năng sử dụng có thể ưu tiên rất cao; tranh luận khóa giao dịch và hàng đợi là kỹ thuật; phiếu xác nhận đẹp liên quan ưu tiên; quy tắc một người duyệt mọi PR liên quan quy trình và nút thắt.

**Dữ kiện cần có:** Tỷ lệ hoặc cách tái hiện đặt trùng; yêu cầu nghiệp vụ khi hai người cùng đặt; đặc điểm lưu trữ hiện tại và khả năng thực thi thao tác nguyên tử; giới hạn tải. Dữ kiện đo và phân tích phải đi trước việc mặc định một kiến trúc.

**Tiêu chí cần bảo vệ:** Không tạo hai lịch chiếm cùng tài nguyên/khung giờ khi nghiệp vụ cấm; người đặt thành công nhận xác nhận nhất quán với dữ liệu đã lưu; người không thể đặt nhận thông báo rõ và có thể chọn giờ khác. Ngoài ra cần kiểm soát quyền truy cập và dữ liệu cá nhân.

**Quyết định:** Product Owner chịu trách nhiệm thứ tự Product Backlog; Developers chịu trách nhiệm kế hoạch triển khai, lựa chọn kỹ thuật và chất lượng Increment; Scrum Master hỗ trợ hiệu quả Scrum và tháo gỡ trở ngại. Cần tham vấn người phụ trách nghiệp vụ, kiểm thử, bảo mật/vận hành theo rủi ro.

**Thử nghiệm:** Tái hiện hai yêu cầu đặt cùng lúc, kiểm tra tính nhất quán ở tải phù hợp và so sánh chi phí phương án. Với review, thử giới hạn WIP, chia PR nhỏ và tạo cơ chế review bởi người đủ năng lực thay vì phụ thuộc tuyệt đối vào một người, trong phạm vi tiêu chuẩn kiểm soát của tổ chức.

**Đo lường:** Theo dõi tỷ lệ đặt lịch hợp lệ thành công; thời gian chờ review và cycle time. Đọc kết quả cùng số lỗi sau phát hành và mức nghiêm trọng của lỗi.

## 17. Tự kiểm tra kiến thức

**Câu 1.** Hai lập trình viên phản đối giải pháp của nhau. Có nên lập tức yêu cầu Scrum Master chọn một phương án không?

**Đáp án:** Không mặc định. Nên làm rõ mục tiêu, tiêu chí kỹ thuật, dữ liệu và quyền quyết định. Scrum Master có thể hỗ trợ quá trình trao đổi; Developers chịu trách nhiệm cách xây phần mềm trong Scrum.

**Câu 2.** Bỏ phiếu 5–2 để bỏ qua một lỗi có nguy cơ mất dữ liệu có phải là giải quyết bất đồng phù hợp không?

**Đáp án:** Không. Rủi ro nghiêm trọng và yêu cầu bắt buộc cần được kiểm soát theo trách nhiệm tương ứng, không thể vô hiệu bằng đa số.

**Câu 3.** Khi hai phương án kỹ thuật đều có lý nhưng chưa đủ dữ liệu, nhóm nên làm gì?

**Đáp án:** Xác định giả thuyết và tiêu chí chọn, thử nghiệm nhỏ có thời hạn nếu an toàn và khả thi, rồi quyết định dựa trên bằng chứng. Nếu chi phí thử lớn hoặc vấn đề ít rủi ro, có thể chọn phương án đơn giản đáp ứng yêu cầu hiện tại và ghi điều kiện xem lại.

**Câu 4.** Product Owner đề nghị thêm tính năng giữa Sprint. Developers phải làm ngay vì Product Owner quyết định ưu tiên sản phẩm?

**Đáp án:** Không tự động. Cần trao đổi tác động tới Sprint Goal, phạm vi công việc, chất lượng và rủi ro. Product Owner chịu trách nhiệm Product Backlog; Developers lập kế hoạch và tạo Increment đáp ứng DoD.

**Câu 5.** Một cuộc họp kết thúc với câu “mọi người tự xử lý tiếp”. Quy trình giải quyết bất đồng đã hoàn tất chưa?

**Đáp án:** Chưa rõ. Cần xác định quyết định hoặc dữ liệu còn thiếu, người phụ trách và thời điểm xem lại. Không nên coi kết thúc cuộc họp là kết thúc vấn đề.

**Câu 6.** Vì sao số lần bất đồng ít đi chưa chắc là dấu hiệu tốt?

**Đáp án:** Có thể nhóm đang phối hợp tốt hơn, nhưng cũng có thể thành viên ngại lên tiếng. Cần nhìn chất lượng quyết định, rủi ro được phát hiện, kết quả sản phẩm và khả năng phản biện an toàn.

**Câu 7.** Khi một quyết định đã thực hiện nhưng xuất hiện bằng chứng mới làm thay đổi bối cảnh, nhóm có được xem lại không?

**Đáp án:** Có. Thích ứng dựa trên phản hồi là trọng tâm Agile. Việc xem lại phải minh bạch, dùng bằng chứng và cân nhắc chi phí thay đổi; không nên đảo quyết định chỉ vì sở thích mới xuất hiện.

## 18. Ghi nhớ trọng tâm

- **Bất đồng là thông tin cần khai thác, không mặc định là lỗi của đội ngũ.** Hãy giữ tranh luận ở mức công việc, mục tiêu và bằng chứng.
- **Tách dữ kiện, giả định, giá trị và lựa chọn.** Phần lớn tranh luận kéo dài vì các bên đang tối ưu những điều khác nhau mà chưa nói rõ.
- **Nhận diện loại bất đồng để chọn cách xử lý.** Kỹ thuật cần tiêu chí và kiểm chứng; ưu tiên cần mục tiêu, giá trị, rủi ro và quyền quyết định; cách làm cần thỏa thuận và thử cải tiến.
- **Ra quyết định có trách nhiệm:** xác định ai quyết, ai cần tham vấn, tiêu chí kết thúc, người triển khai và điều kiện xem lại.
- **Dùng bằng chứng thay cho khẩu hiệu.** Prototype/PoC, user story, acceptance criteria, DoD, backlog, Sprint Goal và số đo Kanban giúp biến ý kiến thành vấn đề có thể kiểm tra.
- **Tương tác tôn trọng làm cho phản hồi đến sớm.** Nói rõ rủi ro, lắng nghe góc nhìn khác và ghi lại những điều quan trọng cho người không tham dự.
- **Đo kết quả thay vì đo số cuộc họp hay số người “thắng” tranh luận.** Giá trị người dùng, chất lượng và thời gian luồng công việc mới cho biết quyết định có hữu ích không.
- **Thích ứng sau quyết định.** Khi có bằng chứng mới, nhóm xem lại phương án theo điều kiện đã thống nhất và tiếp tục cải tiến.

Xử lý bất đồng tốt không xóa bỏ mọi khác biệt quan điểm. Nó biến khác biệt thành **quyết định minh bạch, phần mềm được giao với chất lượng phù hợp và cơ hội học hỏi tiếp theo**. Đó là năng lực cộng tác và lãnh đạo giúp đội ngũ Agile phản hồi sớm, phát triển sản phẩm tăng dần và giữ khả năng thích ứng khi điều kiện thay đổi.
