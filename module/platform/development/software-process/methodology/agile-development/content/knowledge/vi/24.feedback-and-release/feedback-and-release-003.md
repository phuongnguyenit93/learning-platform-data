# Thu thập phản hồi qua trình diễn, sử dụng thử và quan sát thực tế

> **Chương:** Phản hồi và phát hành  
> **Học phần:** **AGILE_DEVELOPMENT** — hiểu giá trị và nguyên tắc Agile trong phát triển phần mềm thích ứng thông qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để lựa chọn cách phối hợp phù hợp.

Một nhóm vừa hoàn tất chức năng **đặt lịch tư vấn trực tuyến**. Trong buổi trình diễn, các stakeholder đều gật đầu khi thấy dòng chữ “Đặt lịch thành công”. Tuy nhiên, khi khách hàng trực tiếp thử thao tác trên điện thoại, một số người nhấn nút Đặt lịch nhiều lần vì màn hình phản hồi chậm. Sau khi phát hành cho một nhóm nhỏ, hệ thống ghi nhận nhiều yêu cầu gửi lại và có khách liên hệ tổng đài để hỏi liệu lịch đã được xác nhận hay chưa.

Ba nguồn thông tin có vẻ mâu thuẫn, nhưng thực ra chúng đang nói về **ba góc nhìn khác nhau**:

- **Trình diễn (demonstration):** Người xem đánh giá một kết quả được trình bày trong bối cảnh có hướng dẫn.
- **Sử dụng thử (trial use):** Người dùng thực hiện tác vụ, bộc lộ điểm vướng khi trực tiếp tương tác với sản phẩm.
- **Quan sát thực tế (real-world observation):** Nhóm xem hành vi và kết quả trong môi trường sử dụng thật, nơi có thiết bị, mạng, động lực và tình huống không hoàn toàn kiểm soát được.

Agile không coi một buổi demo được khen hoặc một dashboard có nhiều lượt nhấp là bằng chứng đủ để kết luận sản phẩm tạo giá trị. **Phản hồi hữu ích cần được thu thập có chủ đích, diễn giải trong bối cảnh, kiểm tra chất lượng nguồn dữ liệu và chuyển thành quyết định có thể theo dõi.**

Bài học này xây dựng vòng phản hồi từ **giả thuyết → chọn phương pháp → thu thập bằng chứng → diễn giải → điều chỉnh backlog → thử hoặc phát hành tiếp → đánh giá lại**. Mục tiêu cuối cùng không phải thu càng nhiều ý kiến càng tốt, mà là **giảm bất định và giao đúng phần mềm đáng tin cậy**.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt mục đích, thế mạnh và giới hạn của **trình diễn, sử dụng thử và quan sát thực tế**.
2. Đặt câu hỏi phản hồi gắn với **giả thuyết và kết quả người dùng**, không chỉ hỏi “có thích tính năng này không?”.
3. Thiết kế một buổi demo có trao đổi, một phiên thử tác vụ có quan sát và kế hoạch thu thập bằng chứng sau phát hành.
4. Thu thập, phân loại và kết hợp **dữ liệu định tính** với **dữ liệu định lượng**, nhận diện các thiên lệch và giới hạn suy luận.
5. Sử dụng tín hiệu như **task success, time on task, error/retry, funnel, adoption, phản hồi hỗ trợ và độ tin cậy** đúng ngữ cảnh.
6. Lập chính sách thu thập phản hồi **tôn trọng sự đồng ý, quyền riêng tư, bảo mật, khả năng tiếp cận và công bằng**.
7. Chuyển insight thành **Product Backlog Item, giả thuyết thử nghiệm, lỗi hoặc cải tiến kỹ thuật** có tiêu chí kiểm chứng.
8. Kết nối vòng phản hồi với **Sprint Review, Increment, phát hành tăng dần, Kanban flow và các thực hành XP**.

## 2. Phản hồi trong Agile là bằng chứng để ra quyết định

### 2.1. “Ý kiến” khác “quan sát” và “kết quả”

| Loại thông tin | Ví dụ về chức năng đặt lịch | Có thể kết luận gì? |
| --- | --- | --- |
| **Ý kiến/nhận xét** | “Nút xác nhận trông hơi nhỏ.” | Có một nhận xét cần làm rõ trong bối cảnh sử dụng. |
| **Hành vi quan sát** | Người dùng nhấn Đặt lịch ba lần vì chưa thấy phản hồi. | Trong phiên đó, trạng thái phản hồi chưa đủ rõ hoặc có vấn đề liên quan. |
| **Dữ liệu sự kiện** | Tỷ lệ gửi lại tăng ở phân đoạn mạng yếu. | Có dấu hiệu định lượng cần kiểm tra nguyên nhân và chất lượng tracking. |
| **Kết quả tác vụ** | Khách không biết liệu lịch có được đặt thành công. | Tác vụ chưa cung cấp sự chắc chắn cần thiết. |
| **Kết quả dài hạn** | Cuộc gọi hỏi xác nhận giảm sau cải tiến. | Có tín hiệu lợi ích; cần xét các biến số khác trước khi quy nguyên nhân. |

**Mục đích của phản hồi là giúp ra quyết định tốt hơn**, không phải tạo kho bình luận chưa phân loại. Một phát biểu của stakeholder có thẩm quyền có thể quan trọng, nhưng vẫn cần phân biệt **quyết định chiến lược** với **bằng chứng hành vi người dùng**.

### 2.2. Ba câu hỏi trước khi thu thập

1. **Điều chưa biết là gì?** Ví dụ: “Khách có nhận biết khi yêu cầu đang Pending không?”.
2. **Bằng chứng nào có thể làm thay đổi quyết định?** Quan sát khách tự thao tác, tỷ lệ gửi lặp, log backend hay phản hồi tổng đài?
3. **Nếu kết quả khác dự đoán, nhóm sẽ làm gì?** Sửa nội dung trạng thái, thay cơ chế retry, dừng mở rộng phát hành hay cần khảo sát thêm?

Nếu không trả lời được câu 3, có thể nhóm đang thu thập thông tin theo thói quen chứ chưa có một **quyết định cần hỗ trợ**.

### 2.3. Phân biệt output, outcome và impact

- **Output:** Đã triển khai màn hình xác nhận, đã hoàn thành bao nhiêu story.
- **Outcome:** Người dùng hiểu tình trạng yêu cầu và hoàn tất đặt lịch hợp lệ dễ hơn.
- **Impact:** Số cuộc gọi tổng đài, chi phí hỗ trợ hoặc tỷ lệ bỏ lỡ lịch thay đổi theo thời gian.

Output cần thiết nhưng **không tự chứng minh outcome**. Outcome thường có thể đo gần trải nghiệm người dùng hơn; impact có thể cần thời gian và chịu ảnh hưởng của nhiều biến số.

**Ví dụ:** Một story “thêm spinner khi gửi yêu cầu” hoàn tất kỹ thuật chưa đủ. Nếu người dùng vẫn nhấn lại hoặc không phân biệt “đang xử lý” với “đã xác nhận”, vấn đề có thể chưa được giải quyết.

### 2.4. Vòng phản hồi khép kín

~~~mermaid
flowchart TD
    A["Product Goal / vấn đề người dùng"] --> B["Giả thuyết và câu hỏi cần biết"]
    B --> C{"Chọn bằng chứng phù hợp"}
    C --> D["Trình diễn và đối thoại"]
    C --> E["Sử dụng thử / làm tác vụ"]
    C --> F["Quan sát hành vi thực"]
    D --> G["Tổng hợp định tính + định lượng"]
    E --> G
    F --> G
    G --> H["Kiểm tra thiên lệch và độ tin cậy"]
    H --> I["Quyết định: sửa, thử tiếp, phát hành, dừng"]
    I --> J["Backlog / phát hành / cải tiến kỹ thuật"]
    J --> K["Increment và quan sát sau thay đổi"]
    K -. "Bằng chứng mới" .-> B
~~~

**Vòng phản hồi không phải quy trình phê duyệt cứng.** Với lỗi nghiêm trọng ảnh hưởng người dùng, nhóm có thể phải ứng cứu trước rồi phân tích đầy đủ sau. Với quyết định sản phẩm chưa chắc chắn, một phiên thử ngắn hoặc phát hành giới hạn có thể giảm bất định trước khi đầu tư lớn.

## 3. Chọn phương pháp theo loại câu hỏi

Không có nguồn phản hồi nào tốt nhất cho mọi câu hỏi. Demo giúp chia sẻ ý tưởng và thảo luận quy tắc; usability test cho thấy người dùng có làm được tác vụ; quan sát thực tế cho thấy hệ thống vận hành ra sao khi không có người hướng dẫn.

| Câu hỏi cần trả lời | Trình diễn | Sử dụng thử | Quan sát thực tế |
| --- | --- | --- | --- |
| Quy tắc nghiệp vụ mới có đúng mong đợi? | **Hữu ích** với chuyên gia miền. | Hữu ích khi có tình huống thật. | Bổ sung trường hợp chưa lường trước. |
| Người mới có tự hoàn tất một tác vụ? | **Yếu** nếu người trình diễn thao tác thay. | **Mạnh** với kịch bản và người dùng phù hợp. | Hữu ích với tín hiệu hành vi và quyền quan sát phù hợp. |
| Tính năng có được sử dụng thường xuyên? | Không kết luận được. | Chỉ cung cấp tín hiệu sớm. | Cần đo theo khoảng thời gian, phân đoạn. |
| Lỗi mạng yếu/retry có làm sai dữ liệu? | Có thể nêu giả định và thử mô phỏng. | Có thể thử thiết bị/mạng kiểm soát. | Kết hợp telemetry, log và kiểm chứng backend. |
| Vì sao người dùng bỏ dở? | Nêu giả thuyết. | Quan sát và hỏi sau tác vụ. | Funnel chỉ ra nơi bỏ dở, không tự nói “vì sao”. |
| Có nên mở rộng phát hành? | Góc nhìn stakeholder. | Mức sẵn sàng sử dụng trong một mẫu. | Kết quả thực, guardrail và độ tin cậy. |

### 3.1. Quy tắc chọn phương pháp

**Cần biết “người dùng nói họ muốn gì”:** Phỏng vấn có câu hỏi trung tính và trao đổi trong demo có thể cung cấp giả thuyết.

**Cần biết “người dùng có làm được việc không”:** Quan sát họ **tự thực hiện tác vụ** thường phù hợp hơn hỏi ý kiến về một màn hình.

**Cần biết “điều gì xảy ra thường xuyên trong môi trường thực”:** Telemetry, dữ liệu hỗ trợ và quan sát bối cảnh phù hợp có ích, nhưng phải xác định đúng sự kiện và mẫu.

**Cần biết “thay đổi X có gây cải thiện Y không”:** Cần thiết kế so sánh đủ chặt (đôi khi thử nghiệm có đối chứng), cân nhắc an toàn, mẫu và yếu tố nhiễu.

### 3.2. Không dùng nhiều phương pháp chỉ để đủ ba nhãn

Với lỗi **không thể hoàn tất thanh toán** đang ảnh hưởng production, cần xử lý an toàn theo quy trình; không chờ demo, beta và phỏng vấn mới sửa. Với ý tưởng **đổi tên nút** ít rủi ro, vài phiên thử có thể giúp chọn bước tiếp. Với thay đổi **giao dịch tiền hoặc dữ liệu nhạy cảm**, cần thêm bảo vệ kỹ thuật, thẩm quyền và giám sát.

## 4. Bắt đầu từ giả thuyết có thể kiểm chứng

### 4.1. Chuyển ý tưởng mơ hồ thành câu hỏi cụ thể

**Ý tưởng mơ hồ:** “Giao diện đặt lịch nên thân thiện hơn.”

**Giả thuyết:**

> “Khách lần đầu sử dụng điện thoại thường gửi lặp vì không phân biệt được *Đang xử lý* và *Đã xác nhận*. Nếu hiển thị trạng thái rõ và có cách xem lại yêu cầu đang chờ, tỷ lệ gửi lặp và số yêu cầu hỗ trợ về trạng thái có thể giảm, mà không làm thời gian hoàn tất tác vụ tăng quá mức.”

Từ đó nhóm có thể:

- **Trình diễn** để hỏi chuyên gia miền về những trạng thái cần phân biệt.
- **Sử dụng thử** để quan sát khách tự thao tác khi mạng chậm.
- **Quan sát thực tế** để đo gửi lặp, Pending kéo dài, lỗi và yêu cầu hỗ trợ.

**Giả thuyết không phải sự thật.** Nếu người dùng gửi lại chủ yếu vì lỗi API, chỉ thay nội dung UI có thể không giải quyết gốc rễ.

### 4.2. Mẫu giả thuyết và kế hoạch bằng chứng

~~~yaml
problem: "Khách không biết yêu cầu đặt lịch đã được xử lý hay chưa"
audience: "Khách đặt lịch lần đầu bằng điện thoại"
assumption: "Trạng thái chờ chưa rõ làm khách gửi lại yêu cầu"
proposed_change: "Hiển thị Pending và tra cứu bằng mã yêu cầu"
qualitative_question: "Khi mạng chậm, khách nghĩ điều gì đang xảy ra?"
quantitative_signals:
  - "Tỷ lệ gửi lặp theo cùng tác vụ"
  - "Tỷ lệ hoàn tất đặt lịch hợp lệ"
  - "Tỷ lệ liên hệ hỗ trợ về trạng thái"
guardrails:
  - "Không tăng số lịch tạo trùng"
  - "Không báo Confirmed cho lịch còn Pending"
  - "Không tăng lỗi backend nghiêm trọng"
decision: "Thử một lát cắt nhỏ trước khi mở rộng"
~~~

Đây là mẫu học tập, **không phải dữ liệu đã xác minh**. Trước khi đo phải định nghĩa **đơn vị phân tích, mẫu số, khoảng thời gian, tiêu chí loại bot/test và cách xử lý yêu cầu gửi lặp**.

### 4.3. Dự kiến cả kết quả bác bỏ giả thuyết

Trước khi thử nên trả lời:

- Nếu người dùng vẫn gửi lặp khi trạng thái rõ, sẽ xem log/độ trễ hoặc cơ chế retry nào?
- Nếu gửi lặp giảm nhưng tỷ lệ hoàn tất giảm, có phải chỉ vì nút trở nên khó nhấn hơn?
- Nếu mẫu nhỏ không cho tín hiệu rõ, sẽ tiếp tục quan sát hay dừng đầu tư?
- Nếu phát hiện lỗi dữ liệu, ngưỡng nào khiến phải **dừng thử và ứng cứu**?

Cách làm này giảm **confirmation bias**: chỉ chú ý phản hồi ủng hộ phương án đã thích.

## 5. Trình diễn: biến buổi xem sản phẩm thành đối thoại về giá trị

### 5.1. Trình diễn có thể giúp gì?

**Trình diễn sản phẩm (demo)** cho phép:

- Xem một lát cắt chức năng hoạt động.
- Phát hiện thuật ngữ, quy tắc và giả định khác nhau.
- Kiểm tra những tình huống nghiệp vụ biên.
- Thảo luận tác động của Increment tới Product Goal.
- Đặt câu hỏi về giá trị, khả năng sử dụng và việc tiếp theo.

Demo có thể dùng dữ liệu minh họa, nhưng phải **nói rõ đâu là tính năng đã đạt chuẩn, đâu là prototype hoặc mô phỏng**. Không trình bày mock chưa tích hợp như Increment đã hoàn tất.

### 5.2. Sprint Review có thể chứa demo nhưng không chỉ là demo

Theo **Scrum Guide 2020**, **Sprint Review** là sự kiện gần cuối Sprint để **kiểm tra kết quả và xác định thích ứng tiếp theo** giữa Scrum Team với stakeholder. Nó có thể bao gồm demo nhưng **không phải thuyết trình một chiều, ký duyệt hay cổng phát hành**.

Increment có thể được phát hành trước Sprint Review nếu đáp ứng Definition of Done và điều kiện phát hành phù hợp. Review có ý nghĩa hơn khi nhóm có **bằng chứng hành vi, chất lượng và sử dụng** để ra quyết định.

| Demo đơn thuần | Sprint Review hiệu quả |
| --- | --- |
| Người trình bày thao tác theo kịch bản đẹp. | Scrum Team và stakeholder kiểm tra Increment, bối cảnh, tiến độ Product Goal. |
| Hỏi “mọi người thấy ổn không?”. | Hỏi điều gì đã giải quyết, điều gì chưa biết, trường hợp nào bị bỏ sót. |
| Kết thúc khi xem hết slide. | Kết thúc với hiểu biết và thích ứng sản phẩm khi cần. |
| Có thể là một buổi trao đổi bất kỳ. | Là sự kiện Scrum có mục đích, timebox riêng. |

### 5.3. Chuẩn bị demo có giá trị

**Trước demo:**

1. Nêu **quyết định cần hỗ trợ**, ví dụ “luồng xác nhận có xử lý đúng các trạng thái không?”.
2. Mời người có thông tin: Product Owner, chuyên gia miền, đại diện hỗ trợ/vận hành, người dùng phù hợp khi có thể.
3. Chuẩn bị **dữ liệu thử**, không lộ dữ liệu cá nhân, và môi trường đáng tin.
4. Nói rõ phần nào **Done**, phần nào chưa triển khai hoặc còn giả định.
5. Chuẩn bị kịch bản **bình thường và bất thường**: mạng yếu, lịch bị chiếm, gửi lại.

**Trong demo:** Mở đầu bằng vấn đề người dùng; thể hiện lát cắt end-to-end khi có thể; nói rõ thành phần giả lập; hỏi về **quy tắc, kết quả, rủi ro**; phân biệt lỗi, yêu cầu và giả định.

**Sau demo:** Ghi bằng chứng và người có thể xác nhận; phân loại việc cần sửa ngay, việc vào backlog và điều cần thử với người dùng; chia sẻ quyết định cho nhóm.

### 5.4. Kịch bản demo đặt lịch

~~~text
Mục tiêu: Kiểm tra hiểu biết chung về xác nhận đặt lịch.

Tình huống 1: Giờ còn trống -> tạo lịch -> Confirmed.
Tình huống 2: Hai người chọn cùng giờ -> chỉ một lịch hợp lệ.
Tình huống 3: Mạng timeout -> Pending/Unknown theo hợp đồng.
Tình huống 4: Khách quay lại -> tra cứu trạng thái yêu cầu.

Câu hỏi cần quyết định:
- Khi nào được dùng chữ "Đã xác nhận"?
- Pending có giữ chỗ không, giữ bao lâu?
- Nếu đối tác không phản hồi, khách nên làm gì?
- Khi nào gửi thông báo và nội dung thế nào?
~~~

Demo không tự chứng minh ứng dụng chịu tải hay chống trùng đồng thời ở production. Những điều đó còn cần kiểm thử tích hợp, bảo vệ dữ liệu và quan sát vận hành.

### 5.5. Hỏi câu mở thay vì dẫn dắt

| Câu hỏi dễ dẫn dắt | Câu hỏi có ích hơn |
| --- | --- |
| “Nút mới đẹp và dễ dùng hơn rồi nhỉ?” | “Nếu là khách lần đầu, bạn nghĩ bước tiếp theo là gì?” |
| “Tính năng này đúng ý kinh doanh chứ?” | “Quy tắc nào chưa khớp thực tế trong tình huống vừa xem?” |
| “Có ai phản đối không?” | “Điều gì có thể xảy ra ngoài kịch bản mà chúng ta chưa thử?” |
| “Release được rồi phải không?” | “Bằng chứng và điều kiện an toàn nào còn thiếu trước khi mở rộng?” |
| “Bạn thích màu nào?” | “Thông tin nào giúp khách biết lịch đã được xác nhận?” |

Tránh **đưa sẵn câu trả lời mong muốn** hoặc khiến người tham dự ngại nêu vấn đề.

## 6. Sử dụng thử: để người dùng tự thực hiện tác vụ

**Sử dụng thử** bao gồm nhiều hình thức cần phân biệt:

- **Usability testing:** Quan sát người dùng đại diện tự thực hiện tác vụ trong một phiên có mục đích.
- **Prototype testing:** Kiểm tra ý tưởng/luồng trước khi triển khai hoàn chỉnh; kết quả không chứng minh hệ thống production hoạt động.
- **Dogfooding/internal trial:** Thành viên nội bộ dùng thử, tìm lỗi sớm nhưng không thay thế người dùng đại diện.
- **Pilot/beta:** Cho một nhóm dùng phần mềm thật trong phạm vi giới hạn với hỗ trợ, giám sát và quyết định mở rộng.
- **Accessibility testing:** Kiểm tra khả năng sử dụng với công nghệ hỗ trợ và nhu cầu tiếp cận đa dạng; không chỉ chạy công cụ tự động.

Các hình thức có chi phí, mức tin cậy và rủi ro khác nhau. Một usability test trên prototype giúp hiểu **cách người dùng nhìn và thao tác**; pilot với phần mềm thật cung cấp thêm bằng chứng về **độ tin cậy và công việc thực tế**.

### 6.1. Thiết kế tác vụ, không chỉ dẫn từng cú nhấp

**Tác vụ không tốt:**

> “Hãy nhấn nút Chọn giờ màu xanh ở góc phải rồi bấm Xác nhận.”

Nó kiểm tra khả năng làm theo hướng dẫn, không kiểm tra khả năng tự tìm đường.

**Tác vụ tốt hơn:**

> “Bạn cần tư vấn chiều thứ Sáu. Hãy tìm một giờ phù hợp và thực hiện việc đặt lịch. Sau đó cho biết liệu bạn tin rằng lịch đã được xác nhận hay chưa.”

Người điều phối nêu bối cảnh vừa đủ để người tham gia **tự quyết định bước đi**, ghi lúc ngập ngừng, tìm lại thông tin, mắc lỗi hoặc nhờ trợ giúp.

### 6.2. Mẫu kế hoạch phiên thử

| Thành phần | Nội dung minh họa |
| --- | --- |
| **Câu hỏi** | Khách lần đầu có nhận ra Pending khác Confirmed khi mạng chậm? |
| **Đối tượng** | Người có nhu cầu tương tự khách thật, gồm trường hợp thiết bị/mạng phù hợp. |
| **Môi trường** | Điện thoại thật hoặc tương đương; mạng bình thường và chậm giả lập có kiểm soát. |
| **Tác vụ 1** | Tìm giờ và đặt lịch không có hướng dẫn từng bước. |
| **Tác vụ 2** | Xác định kết quả khi trạng thái còn đang xử lý. |
| **Tác vụ 3** | Quay lại tra cứu trạng thái yêu cầu đã gửi. |
| **Quan sát** | Đường đi, nhấn lặp, điểm dừng, diễn giải trạng thái, phản ứng với lỗi. |
| **Số đo bổ sung** | Tác vụ hoàn thành độc lập, thời gian, hỗ trợ cần thiết, lỗi quan trọng. |
| **An toàn** | Tài khoản và dữ liệu thử, không tạo lịch thật chiếm chỗ của khách khác. |
| **Đầu ra** | Sửa UI/luồng, điều tra kỹ thuật, hoặc chuẩn bị pilot an toàn. |

Không có số người thử **bắt buộc** cho mọi câu hỏi. Một vài phiên có thể phát hiện lỗi khả dụng rõ, nhưng không đủ để ước lượng chính xác tỷ lệ lỗi của toàn bộ người dùng hoặc chứng minh tác động thống kê.

### 6.3. Lời mở đầu trung tính

> “Chúng tôi đang kiểm tra cách sản phẩm hỗ trợ tác vụ, không đánh giá khả năng của bạn. Bạn có thể thao tác như bình thường, nói điều khiến bạn phân vân nếu thấy thoải mái và có thể dừng bất cứ lúc nào. Nếu một bước khó hiểu, thông tin đó giúp nhóm cải thiện sản phẩm.”

Tùy bối cảnh, cần thông báo **mục đích, cách sử dụng dữ liệu, quyền đồng ý hoặc từ chối và điều kiện ghi âm/ghi hình**. Không ghi màn hình, giọng nói hay dữ liệu nhạy cảm một cách bí mật.

### 6.4. Quan sát mà không dẫn dắt

Người điều phối có thể hỏi:

- “Bạn đang tìm điều gì ở màn hình này?”
- “Thông báo vừa xuất hiện có nghĩa gì với bạn?”
- “Lúc này bạn kỳ vọng hệ thống sẽ làm gì?”
- “Điều gì khiến bạn quyết định thử lại?”

Tránh:

- “Bạn thấy nút ở đây không?”
- “Có phải bạn không hiểu vì chữ nhỏ?”
- “Bạn nên nhấn nút này.”

Nếu phải hỗ trợ để phiên tiếp tục, **ghi rõ đã hỗ trợ**, không đánh dấu là hoàn thành độc lập. Nếu sản phẩm lỗi kỹ thuật khiến không thể tiếp tục, phân loại nguyên nhân đúng thay vì quy lỗi cho người dùng.

### 6.5. Một phiếu quan sát mẫu

~~~text
Session: U-03 (mã giả danh, không chứa tên thật)
Segment: Khách lần đầu, điện thoại, mạng chậm giả lập
Task: Đặt lịch và xác định trạng thái
Observation 1: Dừng 8 giây sau khi nhấn Đặt lịch.
Observation 2: Nhấn lại lần thứ hai vì không thấy thay đổi rõ.
User quote: "Chắc hệ thống chưa nhận."
Outcome: Không xác định được trạng thái dù request đã được tiếp nhận.
Facilitator help: Không
Technical evidence: Kiểm tra request ID trên môi trường thử.
Interpretation (giả thuyết): Trạng thái xử lý không đủ rõ.
Follow-up: Đối chiếu log và thử thông báo Pending.
~~~

Phân biệt **điều quan sát được**, **điều người tham gia nói** và **điều nhóm suy luận**. Câu “người dùng không biết đọc” là nhãn áp đặt; “người dùng dừng tám giây và tìm trạng thái ở vị trí X” là quan sát có thể kiểm tra.

### 6.6. Tín hiệu sử dụng thử

| Tín hiệu | Cách hiểu | Cẩn trọng |
| --- | --- | --- |
| **Task completion** | Hoàn tất tác vụ theo tiêu chí xác định trước. | Phân biệt tự làm, có trợ giúp và sai kết quả. |
| **Time on task** | Thời gian từ lúc bắt đầu đến tiêu chí kết thúc. | Nhanh chưa chắc tốt nếu bỏ qua kiểm tra an toàn. |
| **Error count** | Hành vi sai, lỗi sản phẩm hoặc kết quả sai; cần phân loại. | Không coi mọi cú nhấp lại là “lỗi người dùng”. |
| **Assistance rate** | Bao nhiêu phiên cần người điều phối giúp. | Kịch bản, độ khó và tiêu chuẩn trợ giúp phải nhất quán. |
| **Comprehension** | Người dùng hiểu trạng thái và diễn giải đúng kết quả. | Không chỉ hỏi “đã hiểu chưa?”; yêu cầu diễn giải theo ngôn ngữ riêng. |
| **Satisfaction** | Thái độ/cảm nhận tự báo cáo. | Có thể cao dù không hoàn tất đúng tác vụ. |

Nếu người dùng dùng công nghệ hỗ trợ cần thêm thời gian, mục tiêu nên là **khả năng tiếp cận và hoàn tất chính xác**, không ép mọi người vào một ngưỡng tốc độ chung.

## 7. Sử dụng thử giới hạn: pilot, beta và phát hành theo nhóm

**Pilot/beta** đưa việc sử dụng gần môi trường thật hơn. Nó hữu ích để đánh giá giá trị và mức sẵn sàng mở rộng, nhưng **không biến tính năng chưa đạt chuẩn chất lượng thành an toàn chỉ vì gắn nhãn beta**.

### 7.1. Một kế hoạch pilot có trách nhiệm

1. **Mục tiêu:** Kiểm tra điều gì trước khi mở rộng, ví dụ tỷ lệ gửi lặp và cách xử lý Pending.
2. **Đối tượng:** Ai đại diện cho bối cảnh cần đo? Ai không nên đưa vào thử vì rủi ro?
3. **Điều kiện tham gia:** Thông tin rõ phạm vi beta, kênh hỗ trợ và khả năng dừng tham gia.
4. **Phạm vi chức năng:** Feature được mở; điều gì vẫn ẩn/chưa hỗ trợ?
5. **Guardrails:** Lỗi dữ liệu, độ trễ, tỷ lệ thất bại, bảo mật, ngưỡng tạm dừng.
6. **Hỗ trợ:** Ai trực, ai có quyền tắt feature hoặc chuyển sang quy trình an toàn?
7. **Kế hoạch đo:** Dữ liệu nền, phản hồi chủ động và tín hiệu bất thường.
8. **Quyết định:** Mở rộng, giữ phạm vi, sửa rồi thử lại hoặc dừng theo tiêu chí rõ.

**Feature flag** có thể giúp bật/tắt một khả năng cho một nhóm nhưng **không tự bảo đảm rollback an toàn**. Thay schema, gửi thông báo và đặt lịch thật có thể không đảo ngược đơn giản chỉ bằng tắt flag.

### 7.2. Beta khác usability test

Trong usability test, nhóm có thể biết **vì sao người thử bấm sai** vì quan sát trực tiếp. Trong beta, nhóm có thể thấy **tần suất vấn đề trong bối cảnh thật** và theo dõi dài hơn, nhưng khó biết chính xác vì sao nếu không phỏng vấn hoặc có thông tin bối cảnh.

Người đăng ký beta sớm thường có **thiên lệch tự chọn**: họ có thể thành thạo công nghệ hơn phần đông. Vì vậy, kết quả pilot không tự đại diện cho mọi tập khách, nhất là người ít kinh nghiệm, dùng thiết bị cũ hoặc có nhu cầu trợ năng.

### 7.3. Lộ trình phát hành tăng dần

~~~text
Increment đạt chuẩn kỹ thuật và điều kiện an toàn
        |
        v
Thử nội bộ / sandbox phù hợp
        |
        v
Pilot nhỏ có giám sát và hỗ trợ
        |
        v
Kiểm tra outcome, độ tin cậy, sự cố, phản hồi
        |
        +-- Guardrail vi phạm --> Dừng mở rộng, giảm ảnh hưởng/ứng cứu
        |
        +-- Bằng chứng chưa rõ --> Giữ phạm vi và tìm hiểu tiếp
        |
        +-- Điều kiện đáp ứng --> Mở rộng có kiểm soát
~~~

Không phải sản phẩm nào cũng cần đúng các bước trên. Với chỉnh sửa nội dung ít rủi ro, đường đi có thể đơn giản hơn. Với hệ thống tài chính, y tế hoặc dữ liệu nhạy cảm, điều kiện phát hành có thể phức tạp hơn và phải theo nghĩa vụ thực tế.

### 7.4. Sự cố trong pilot là sự cố thật

Nếu tạo lịch trùng trong pilot với khách thật, không nên coi đó chỉ là “phản hồi hay” rồi tiếp tục thêm người dùng. Cần **ngăn thiệt hại, đối soát dữ liệu, hỗ trợ theo thẩm quyền và điều tra nguyên nhân**. Học nhanh không biện minh việc chuyển rủi ro không chấp nhận được sang người tham gia.

## 8. Quan sát thực tế: thấy điều người dùng làm trong bối cảnh của họ

Quan sát thực tế có hai dạng bổ trợ:

1. **Quan sát có bối cảnh (contextual observation / field research):** Người nghiên cứu xem tác vụ trong môi trường phù hợp với sự cho phép và bảo vệ cần thiết.
2. **Quan sát qua dữ liệu vận hành (analytics, telemetry, support):** Dùng tín hiệu hành vi, chất lượng và hỗ trợ mà hệ thống được phép ghi nhận/phân tích.

**Analytics cho thấy điều gì xảy ra nhưng không tự giải thích động cơ.** Quan sát trực tiếp cho thấy bối cảnh nhưng mẫu nhỏ hoặc có người quan sát cũng có thể khác hành vi tự nhiên.

### 8.1. Contextual observation: người dùng không làm việc như demo

Khách đặt lịch trên đường đi làm có thể:

- Chỉ dùng một tay trên điện thoại.
- Chuyển giữa Wi-Fi và dữ liệu di động.
- Bị cuộc gọi đến khiến ứng dụng xuống nền.
- Không nhớ đã gửi thành công khi quay lại.
- Cần biết giờ theo múi giờ của bản thân.

Trong demo với Wi-Fi mạnh và người trình bày biết đường đi, những vấn đề này có thể không hiện ra. Quan sát bối cảnh giúp nhóm thấy **điều kiện sử dụng**, không chỉ giao diện.

**Giới hạn:** Không quan sát bí mật, không xem dữ liệu cá nhân không liên quan hoặc ghi hình nhạy cảm thiếu cơ sở/đồng ý thích hợp. Có thể dùng phiên thử mô phỏng nếu quan sát đời thực không an toàn.

### 8.2. Thiết kế sự kiện theo hành trình người dùng

Thay vì chỉ ghi chung **button_clicked**, có thể xem các sự kiện có nghĩa:

| Sự kiện minh họa | Khi nào ghi? | Câu hỏi trả lời |
| --- | --- | --- |
| **booking_flow_started** | Bắt đầu phiên đặt lịch theo định nghĩa. | Có bao nhiêu phiên bắt đầu? |
| **availability_viewed** | Danh sách giờ khả dụng được hiển thị hợp lệ. | Người dùng có tới bước chọn giờ? |
| **booking_submit_attempted** | Một lần gửi yêu cầu phát sinh. | Có bao nhiêu attempt, có gửi lặp? |
| **booking_request_accepted** | Backend tiếp nhận yêu cầu theo hợp đồng. | Yêu cầu có được nhận chưa? |
| **booking_confirmed** | Hệ thống có thẩm quyền xác nhận lịch hợp lệ. | Bao nhiêu lịch thật sự được xác nhận? |
| **booking_pending_observed** | Người dùng được hiển thị Pending. | Khách có nhìn thấy trạng thái chờ? |
| **booking_status_checked** | Khách tra cứu lại trạng thái. | Luồng tra cứu có được dùng? |
| **booking_failed** | Thất bại được phân loại bằng mã an toàn. | Lỗi tập trung ở bước nào? |

Một cú nhấp frontend **không chứng minh** backend đã xác nhận. Cần phân biệt **attempt**, **accepted**, **confirmed** và **failed/unknown** theo ngữ nghĩa miền. Một sự kiện **booking_success** dùng chung cho toast, nhận request và tạo giao dịch sẽ gây đo lường không đáng tin.

### 8.3. Payload sự kiện không chứa dữ liệu nhạy cảm

~~~json
{
  "event_name": "booking_status_checked",
  "event_version": 1,
  "occurred_at": "2026-11-20T09:10:00Z",
  "flow_id": "flow-pseudonymous-001",
  "status": "PENDING",
  "surface": "mobile_web",
  "network_class": "slow",
  "environment": "pilot"
}
~~~

Payload là **ví dụ tổng hợp**. **Mã giả danh vẫn có thể là dữ liệu cá nhân nếu còn khả năng liên kết một người**; flow_id phải tuân thủ chính sách bảo mật, giới hạn truy cập và thời hạn lưu phù hợp. Không đưa tên, số điện thoại, email, token, nội dung tư vấn hoặc dữ liệu thanh toán vào event chỉ để dễ debug.

**Độ chính xác cần kiểm tra:** Client có thể mất mạng, gửi event lặp hoặc bị chặn tracking; backend có thể gửi sự kiện muộn. Dashboard phải minh bạch quy tắc deduplication và dữ liệu thiếu/trễ.

### 8.4. Funnel không phải bản đồ toàn bộ trải nghiệm

~~~text
Bắt đầu đặt lịch
   -> Xem giờ khả dụng
      -> Gửi yêu cầu
         -> Nhận trạng thái rõ
            -> Lịch được xác nhận
~~~

Trước khi tính tỷ lệ chuyển đổi, cần định nghĩa:

- **Mẫu số:** Người dùng, phiên, yêu cầu hay từng attempt?
- **Cửa sổ:** Một phiên, 24 giờ hay một tuần?
- **Thành công:** Backend confirmed hay chỉ có toast?
- **Phân đoạn:** Khách mới/quay lại, thiết bị, kênh, khu vực?
- **Ngoại lệ:** Hủy có chủ đích, hết chỗ, sự kiện thử, bot, lỗi tracking.

**Ví dụ giả định:** 200 phiên bắt đầu, 150 phiên gửi yêu cầu, 120 phiên có lịch xác nhận trong cửa sổ thống nhất. Tỷ lệ từ bắt đầu tới confirmed là **120/200 = 60%**; không được đổi mẫu số sang 150 rồi gọi cùng một chỉ số. Không thể kết luận 80 phiên còn lại đều thất bại vì UI: có thể khách đổi ý, không có giờ hoặc event thiếu.

### 8.5. Quan sát lỗi và độ tin cậy

Ngoài analytics cần xem:

- Số/mức nghiêm trọng của **lịch tạo trùng**.
- Tỷ lệ timeout, retry, Unknown/Pending kéo dài.
- Thời gian từ gửi yêu cầu tới kết quả có thẩm quyền.
- Lỗi nhà cung cấp và khả năng đối soát.
- Sự cố dữ liệu, bảo mật, quyền truy cập.
- Thời gian khôi phục khi có vấn đề.

Đây là **tín hiệu chất lượng**, không thay thế outcome. Nếu lượt nhấn Đặt lịch tăng nhưng lịch trùng cũng tăng, thay đổi đang vi phạm điều kiện bảo vệ.

## 9. Kết hợp định tính và định lượng

### 9.1. Định tính tìm cơ chế, định lượng xem mức độ

**Định tính:** lời nói, quan sát hành vi, nhật ký, hỗ trợ và ghi nhận từ phiên thử. Giúp hiểu **người dùng nghĩ gì, bối cảnh nào tạo vấn đề và giả thuyết nào cần thử**.

**Định lượng:** tỷ lệ hoàn thành, tần suất lỗi, số gửi lặp, phân bố thời gian, phân đoạn thiết bị, số sự cố. Giúp thấy **mẫu hình lớn tới đâu, biến đổi ra sao và nơi cần điều tra**.

Chúng bổ trợ, không thay thế nhau. Sáu người thử đều hiểu màn hình không chứng minh toàn bộ khách sẽ hiểu. Ngược lại, 30% bỏ dở chưa nói được vì sao.

### 9.2. Triangulation — đối chiếu nguồn

Nhận định cần kiểm tra: **“Khách gửi lại vì không biết hệ thống đã nhận yêu cầu.”**

| Nguồn | Tín hiệu | Ý nghĩa |
| --- | --- | --- |
| **Demo** | Stakeholder nói Pending cần khác Confirmed. | Quy tắc và kỳ vọng nghiệp vụ. |
| **Usability** | Một số người nhấn lại khi UI chờ lâu. | Cơ chế có thể gây gửi lặp trong phiên thử. |
| **Telemetry** | Tỷ lệ gửi lặp cao ở nhóm mạng chậm. | Mẫu hình cần kiểm tra ở quy mô rộng. |
| **Support** | Nhiều câu hỏi “Tôi đã đặt được chưa?”. | Bằng chứng vấn đề hiểu trạng thái. |
| **Backend** | Nhiều yêu cầu gửi lặp có cùng mã idempotency. | Phân biệt hành vi với lỗi hệ thống, kiểm tra an toàn. |

Nếu nguồn mâu thuẫn, có thể tập khách khác nhau, tracking thiếu hoặc demo đã hướng dẫn quá rõ. Hãy ghi **điều chưa biết** thay vì ép bằng chứng khớp nhau.

### 9.3. Correlation khác causation

Giả sử sau thay UI, số lượt gọi tổng đài giảm từ 100 xuống 70 trong hai tuần. **Chưa thể khẳng định** UI mới gây giảm 30% nhu cầu hỗ trợ vì:

- Tổng lượng khách có thể thay đổi.
- API có thể đồng thời được nâng cấp.
- Hỗ trợ có thể đổi cách phân loại ticket.
- Pilot có thể gồm khách am hiểu công nghệ hơn.
- Số liệu có thể quá ít hoặc thời gian quá ngắn.

Thiết kế so sánh, dữ liệu nền và đánh giá yếu tố nhiễu giúp tăng độ tin cậy. Với rủi ro cao cần kết hợp chuyên môn kỹ thuật và nghiệp vụ.

### 9.4. Phân nhóm insight theo bằng chứng

| Insight | Bằng chứng | Chưa biết | Hành động hợp lý |
| --- | --- | --- | --- |
| Khách không hiểu Pending | Quan sát phiên thử, ticket hỗ trợ. | Mức phổ biến trên toàn tập. | Thử nội dung mới, kiểm tra hiểu đúng. |
| Retry có thể tạo trùng | Test cạnh tranh phát hiện lỗi backend. | Các đường gọi bị ảnh hưởng khác. | Sửa lỗi an toàn, test hồi quy. |
| Khách muốn SMS | Một stakeholder đề nghị. | Nhu cầu thực và giá trị so với chi phí. | Khảo sát mục tiêu, chưa đầu tư lớn. |
| Xác nhận chậm | Traces backend và phản hồi hỗ trợ. | Nút thắt API, hàng đợi hay client. | Điều tra độ trễ theo môi trường. |

Không cần tạo điểm tin cậy giả chính xác **87,3%** nếu không có phương pháp. Dùng **cao/trung bình/thấp kèm căn cứ** hoặc mô tả rõ giới hạn.

## 10. Những thiên lệch khiến nhóm học sai

### 10.1. Trong trình diễn

- **Demo effect:** Người trình diễn biết đường đi, dữ liệu và môi trường được chọn đẹp.
- **Authority bias:** Người tham dự đồng ý với người có chức vụ cao.
- **Courtesy bias:** Người dùng ngại phê bình trước nhóm làm sản phẩm.
- **Groupthink:** Một vài ý kiến đầu khiến người khác ít phản biện.

Giảm thiểu bằng câu hỏi cụ thể, mời quan điểm khác nhau, cho phép phản hồi riêng và không coi im lặng là bằng chứng đồng thuận.

### 10.2. Trong sử dụng thử

- **Selection bias:** Chỉ mời đồng nghiệp, người quen hoặc khách thạo công nghệ.
- **Observer effect:** Có người quan sát khiến thao tác khác thường.
- **Facilitator bias:** Người điều phối vô tình chỉ đường.
- **Learning effect:** Người thử nhiều lần khác người lần đầu.
- **Survivorship bias:** Chỉ hỏi người hoàn thành, bỏ qua người bỏ dở.

Giảm thiểu bằng chọn đối tượng phù hợp, ghi trợ giúp, chuẩn hóa tác vụ, thêm người có nhu cầu tiếp cận khác nhau và xem cả phiên thất bại.

### 10.3. Trong dữ liệu thực tế

- **Tracking bias:** Event thiếu trên mạng yếu hoặc một số trình duyệt.
- **Denominator bias:** Trộn số người với phiên hoặc attempt.
- **Cohort bias:** Beta users không đại diện cho toàn bộ khách.
- **Seasonality:** Ngày lễ/chiến dịch thay đổi nhu cầu.
- **Instrumentation change:** Đổi định nghĩa event làm so sánh trước/sau sai.
- **Simpson's paradox:** Xu hướng tổng có thể khác xu hướng trong từng phân đoạn khi cơ cấu người dùng thay đổi.

Giảm thiểu bằng công bố định nghĩa, ghi version, xem phân đoạn, điều tra sự kiện thiếu và không tuyên bố nguyên nhân chỉ từ tương quan.

### 10.4. Không lạm dụng phép thử thống kê

A/B testing có thể giúp đánh giá tác động nếu cách phân nhóm và số đo phù hợp, nhưng không bắt buộc cho mọi quyết định. Với thay đổi an toàn/bảo mật, **không để một nhóm người dùng nhận cơ chế không an toàn để làm nhóm đối chứng**.

Với mẫu nhỏ hoặc sự kiện hiếm, bất định lớn. Không tự tạo ngưỡng “95% chắc chắn” từ vài người, cũng không nhầm **không thấy khác biệt** với **chứng minh hai phương án tương đương**. Khi cần suy luận nhân quả nghiêm ngặt, phải có thiết kế và chuyên môn phân tích phù hợp.

## 11. Quyền riêng tư, an toàn và đạo đức trong thu thập phản hồi

Thu thập dữ liệu không phải hoạt động vô hại chỉ vì mục tiêu là cải tiến sản phẩm. Ghi âm, quay màn hình, thu sự kiện, phân tích logs và quan sát ngoài thực địa có thể tiết lộ dữ liệu cá nhân, thông tin nhạy cảm, bí mật kinh doanh hoặc hành vi không liên quan đến mục tiêu nghiên cứu.

### 11.1. Những nguyên tắc thực hành

1. **Mục đích rõ ràng:** Chỉ thu thông tin cần thiết để trả lời câu hỏi nghiên cứu hoặc duy trì an toàn vận hành.
2. **Minh bạch và cơ sở xử lý phù hợp:** Thông báo cách dùng dữ liệu và thực hiện yêu cầu đồng ý khi áp dụng; quyền từ chối/thu hồi phải được xử lý đúng phạm vi.
3. **Tối thiểu hóa dữ liệu:** Không lấy tên, email, nội dung tư vấn hoặc video toàn màn hình nếu một số đo tổng hợp là đủ.
4. **Giới hạn truy cập và lưu trữ:** Xác định ai xem được, lưu bao lâu, nơi lưu và quy trình xóa/ẩn dữ liệu thích hợp.
5. **Bảo mật trong thiết kế:** Không đưa token, thông tin xác thực hoặc chi tiết nhạy cảm vào analytics; bảo vệ log và môi trường nghiên cứu.
6. **Không gây thiệt hại:** Không cố tạo lỗi thanh toán, giữ lịch giả chiếm chỗ khách khác hoặc thử nghiệm nguy hiểm với người thật.
7. **Tôn trọng người tham gia:** Họ có thể dừng phiên hoặc không trả lời câu hỏi phù hợp quy trình; không gán năng lực của họ từ một phiên thử.
8. **Tiếp cận công bằng:** Không chỉ chọn khách hàng có thiết bị mới, mạng mạnh và trình độ kỹ thuật cao.

**Đây là nguyên tắc sản phẩm và nghiên cứu**, không phải tư vấn pháp lý. Quy định cụ thể phụ thuộc quốc gia, ngành, tổ chức và loại dữ liệu; cần tuân theo chính sách/đánh giá chuyên môn áp dụng.

### 11.2. Ghi session replay: lợi ích và nguy cơ

Session replay có thể giúp điều tra lỗi giao diện, nhưng nếu ghi các trường nhập liệu, lịch sử duyệt hoặc thông tin cá nhân, rủi ro cao. Trước khi bật cần xem:

- Có thực sự cần ghi hình hay chỉ cần sự kiện tổng hợp?
- Những vùng nào phải che hoặc không thu ngay từ đầu?
- Ai có quyền xem, trích xuất và chia sẻ?
- Có chính sách thông báo, đồng ý, thời hạn lưu phù hợp không?
- Có kiểm tra khả năng dữ liệu nhạy cảm lọt qua cấu hình che không?

**Mặc định an toàn:** Thiết kế instrumentation theo **sự kiện có ngữ nghĩa và dữ liệu tối thiểu** thay vì lưu toàn bộ hành vi và mọi trường nội dung, trừ khi có nhu cầu rõ được đánh giá và bảo vệ.

### 11.3. Phỏng vấn và quan sát người dễ bị tổn thương

Nếu nghiên cứu với trẻ em, người có tình trạng sức khỏe nhạy cảm hoặc bối cảnh bất cân xứng quyền lực, cần thêm biện pháp bảo vệ, quy trình đồng ý phù hợp và người phụ trách chuyên môn. Tránh yêu cầu người tham gia tiết lộ dữ liệu mà sản phẩm không cần.

Với một hệ thống đặt lịch y tế, nhóm có thể kiểm tra **khả năng xác định trạng thái lịch** trên dữ liệu giả, không cần xem nội dung điều trị hoặc chẩn đoán để đánh giá một nút xác nhận.

### 11.4. Tách dữ liệu nghiên cứu khỏi quyết định đánh giá nhân viên

Phản hồi khách hàng không nên biến thành công cụ xếp hạng Developer, nhân viên tổng đài hoặc người điều phối cá nhân. Một khách bực mình có thể do mạng, chính sách, bug hoặc kỳ vọng sản phẩm không rõ. Hãy dùng dữ liệu để **sửa hệ thống làm việc và trải nghiệm**, tránh gán trách nhiệm khi chưa tìm hiểu.

## 12. Định nghĩa số đo để phản hồi có thể so sánh

Nhiều dashboard trông đẹp nhưng người làm sản phẩm không biết **mẫu số** hoặc **đơn vị đo**. Trước khi chạy pilot cần một thỏa thuận tối thiểu về số đo.

### 12.1. Một bảng metric contract minh họa

| Tên chỉ số | Cách tính minh họa | Đơn vị và cửa sổ | Điều kiện cần kiểm tra |
| --- | --- | --- | --- |
| **Booking completion rate** | Số phiên có lịch Confirmed / số phiên bắt đầu theo định nghĩa. | Phiên, trong 24 giờ. | Loại test/bot; trạng thái backend có thẩm quyền; thời gian xác nhận chậm. |
| **Duplicate submit rate** | Số phiên có từ hai lần submit cùng tác vụ / số phiên có ít nhất một submit. | Phiên, trong một phiên logic. | Phân biệt retry tự động với người dùng nhấn lại, dedup event. |
| **Pending confusion in study** | Phiên người thử diễn giải sai Pending / tổng phiên có tác vụ Pending hợp lệ. | Phiên usability test. | Đánh dấu có được điều phối trợ giúp không; mẫu nhỏ. |
| **Support contact rate** | Lượt liên hệ về trạng thái / số lịch yêu cầu trong cùng giai đoạn. | Lượt liên hệ trên 100 yêu cầu. | Một khách liên hệ nhiều lần; mã phân loại hỗ trợ. |
| **Time to authoritative status** | Thời gian từ request tiếp nhận tới trạng thái kết quả có thẩm quyền. | Giây/phút, phân bố. | Timeout, trường hợp Unknown, clock và mốc đo. |
| **Duplicate booking incidents** | Số sự cố tạo lịch xung đột đã xác minh. | Sự cố theo mức nghiêm trọng. | Dữ liệu thật, đối soát và không che lỗi hiếm nghiêm trọng. |

Khi so sánh trước/sau, phải giữ **cùng định nghĩa** hoặc chú thích lúc instrumentation đổi. Không lấy tỷ lệ theo phiên của tuần trước so với tỷ lệ theo lượt nhấn của tuần sau.

### 12.2. Một phép tính có mẫu số minh bạch

Giả sử số liệu hoàn toàn **minh họa** trong một tuần:

- Có **500 phiên** đặt lịch được theo dõi hợp lệ.
- **350 phiên** gửi ít nhất một yêu cầu.
- **310 phiên** có lịch Confirmed trong cửa sổ 24 giờ.
- **70 trong số 350 phiên đã submit** có từ hai lần submit trở lên.

Khi đó:

\[
\text{Completion rate} = \frac{310}{500}\times100\% = 62\%
\]

\[
\text{Duplicate submit rate} = \frac{70}{350}\times100\% = 20\%
\]

**Không thể kết luận** 20% người dùng tạo hai lịch: đó là tỷ lệ **phiên gửi lặp**, không phải lịch trùng do backend. Một hệ thống có idempotency đúng có thể nhận nhiều attempts nhưng vẫn tạo đúng một lịch; ngược lại, một lỗi hiếm vẫn có thể gây thiệt hại lớn dù tỷ lệ trung bình thấp.

### 12.3. Đo phân bố, không chỉ trung bình

Với thời gian xác nhận, báo một số trung bình có thể che một nhóm nhỏ khách chờ rất lâu. Nên xem:

- Trung vị và các phân vị thích hợp (ví dụ **p90/p95** nếu đủ dữ liệu).
- Những trường hợp Pending/Unknown quá lâu.
- Khác biệt giữa mạng mạnh/yếu, thiết bị, đối tác và thời điểm.
- Lỗi được ghi nhận, số lượng mẫu, dữ liệu mất/trễ.

**Không đặt ngưỡng p95 tùy tiện** chỉ để có badge xanh. Ngưỡng nên gắn với tác vụ, nghĩa vụ vận hành và rủi ro; nhóm cần biết điều gì xảy ra với khách ở phần đuôi của phân bố.

### 12.4. Kết quả của thử nghiệm khác kết quả quan sát

**Quan sát sau phát hành:** Nếu completion tăng từ 62% lên 66%, có tín hiệu cải thiện nhưng chưa chứng minh nguyên nhân là UI mới.

**Thử nghiệm có nhóm đối chứng:** Nếu thiết kế phù hợp, nhóm có thể so sánh hai biến thể đồng thời với phân nhóm và ngưỡng an toàn; cần kiểm tra kích thước mẫu, dữ liệu mất, tác động giữa các nhóm và tính phù hợp của phương pháp phân tích.

**Nghiên cứu định tính:** Nếu một người nói “tôi nghĩ Pending nghĩa là thất bại”, đó là tín hiệu rất hữu ích để xây giả thuyết, nhưng không thể suy ra tỷ lệ toàn tập chỉ từ một người.

## 13. Từ phản hồi thô đến backlog và quyết định sản phẩm

Một nhóm có thể thu cả trăm bình luận mỗi Sprint nhưng không cải thiện sản phẩm nếu không có cơ chế **tổng hợp → phân tích → quyết định → thực hiện → kiểm tra lại**.

### 13.1. Không chuyển nguyên mọi bình luận thành user story

Người dùng nói: **“Thêm nút Gửi lại thật to.”**

Đó là **đề xuất giải pháp**. Vấn đề bên dưới có thể là **không biết yêu cầu đã được nhận**, **mạng lỗi**, **thời gian xác nhận dài** hoặc **thiếu khả năng tra cứu**.

Trước khi mở một Product Backlog Item “tăng kích thước nút gửi lại”, nhóm nên hỏi:

- Người dùng đã gặp tình huống gì?
- Khi đó trạng thái hệ thống thực sự ra sao?
- Người dùng muốn đạt điều gì: gửi thêm request hay biết kết quả?
- Có rủi ro tạo trùng nếu cho phép gửi lại không?
- Giải pháp nhỏ nào có thể kiểm chứng điều cần cải thiện?

**Phản hồi thô là đầu vào cho khám phá và ưu tiên**, không tự động là backlog đã sẵn sàng triển khai.

### 13.2. Một quy trình triage phản hồi

~~~mermaid
flowchart TD
    A["Phản hồi mới từ demo / thử / quan sát"] --> B["Ghi nguồn, bối cảnh và bằng chứng"]
    B --> C{"Loại thông tin?"}
    C -->|Lỗi và rủi ro đang ảnh hưởng| D["Triage theo mức tác động; ứng cứu nếu cần"]
    C -->|Nhu cầu / vướng mắc sản phẩm| E["Làm rõ vấn đề, đối tượng và outcome"]
    C -->|Giả định chưa kiểm chứng| F["Khảo sát / thử có timebox"]
    C -->|Đề xuất không có căn cứ| G["Ghi nhận và xin thêm bối cảnh"]
    D --> H["Quyết định trách nhiệm và ưu tiên"]
    E --> H
    F --> H
    G --> H
    H --> I["Cập nhật backlog hoặc chính sách khi phù hợp"]
    I --> J["Thực hiện lát cắt / cải tiến / quyết định dừng"]
    J --> K["Đo và chia sẻ lại kết quả"]
~~~

Không phải mọi phản hồi đều trở thành công việc mới. Một số chỉ cần trả lời thông tin; một số bác bỏ một ý tưởng; một số cho thấy **không cần thay đổi sản phẩm**. Điều quan trọng là có **lý do quyết định** chứ không phải tạo số ticket.

### 13.3. Phân loại phản hồi theo hành động

| Loại | Ví dụ | Đường xử lý |
| --- | --- | --- |
| **Lỗi nghiêm trọng** | Lịch tạo trùng gây khách tới cùng giờ. | Ứng cứu/triage ngay, kiểm tra ảnh hưởng, bổ sung test và xử lý gốc rễ. |
| **Khó sử dụng** | Khách không hiểu Pending. | Tạo giả thuyết cải tiến và thử tác vụ. |
| **Nhu cầu mới** | Khách muốn tự đổi lịch. | Làm rõ giá trị, quy tắc, rủi ro và thứ tự Product Backlog. |
| **Nợ kỹ thuật** | Mỗi sửa đổi trạng thái phá nhiều integration tests. | Đánh giá chi phí thay đổi, phạm vi refactor và ưu tiên với công việc khác. |
| **Giả định chưa rõ** | API đối tác hỗ trợ retry tới mức nào? | Spike có câu hỏi, timebox và kết quả quyết định. |
| **Phản hồi không đại diện** | Một người thích màn hình tối hơn. | Ghi bối cảnh, xem phân đoạn và nhu cầu trước khi ưu tiên. |
| **Khả năng tiếp cận** | Không đọc được trạng thái qua screen reader. | Đánh giá mức cản trở, tiêu chuẩn/ nghĩa vụ áp dụng và sửa có trách nhiệm. |

### 13.4. Cách diễn đạt insight đủ dùng

~~~text
Insight ID: IN-14
Problem: Khách không phân biệt yêu cầu đang chờ và đã được xác nhận.
Segment: Khách lần đầu trên mobile web.
Evidence:
  - 3/6 phiên thử không diễn giải đúng Pending (mẫu nhỏ, minh họa).
  - Có hỗ trợ hỏi tình trạng sau timeout.
  - Telemetry cho thấy một số phiên gửi lặp khi độ trễ cao.
Confidence: Trung bình; chưa biết mức phổ biến ở toàn tập.
Risk: Gửi lại có thể gây sai dữ liệu nếu backend xử lý không an toàn.
Next decision: Sửa bảo vệ idempotency, sau đó thử UI rõ trạng thái.
Owner/coordination: Product Owner cùng Developers và người hỗ trợ.
Review date: Sau vòng thử được thống nhất.
~~~

Ghi **nguồn, phạm vi và giới hạn** ngay bên cạnh kết luận. Đừng tách một câu nói khỏi bối cảnh rồi trình bày như kết quả nghiên cứu lớn.

### 13.5. Xếp thứ tự dựa trên giá trị, rủi ro và chi phí trì hoãn

Khi backlog có lỗi, feature, khám phá và nợ kỹ thuật, những câu hỏi cần thảo luận:

1. **Tác động người dùng:** Ai bị chặn, mất dữ liệu hoặc chịu thiệt hại?
2. **Mức rủi ro:** Nếu trì hoãn, có khả năng xảy ra lỗi nghiêm trọng không?
3. **Giá trị dự kiến:** Thay đổi có giải quyết vấn đề quan trọng cho đúng nhóm không?
4. **Bằng chứng:** Phản hồi nào đã xác minh, đâu là giả định?
5. **Công sức và phụ thuộc:** Có thể thử một lát cắt ít rủi ro hơn không?
6. **Chi phí cơ hội:** Nếu làm việc này, việc nào phải chờ?
7. **Điều kiện bắt buộc:** Có nghĩa vụ an toàn, pháp lý hoặc thời hạn cần xử lý riêng không?

Một lỗi dữ liệu nghiêm trọng không nên bị đẩy xuống chỉ vì feature trang trí “có điểm ROI dễ tính”. Đồng thời một lời đề nghị của một stakeholder lớn tiếng **không tự động** có tác động tới người dùng cao hơn mọi yêu cầu khác.

### 13.6. Phản hồi phải quay lại người đã cung cấp khi phù hợp

Một hành động hữu ích là **đóng vòng phản hồi**:

> “Chúng tôi đã kiểm tra vấn đề trạng thái đặt lịch chưa rõ. Nhóm sửa xử lý gửi lặp để không tạo lịch trùng, đồng thời thử màn hình phân biệt Đang xử lý và Đã xác nhận. Chúng tôi sẽ tiếp tục xem kết quả sử dụng trước khi mở rộng.”

Không hứa giải quyết mọi đề xuất. Nếu không ưu tiên, có thể nói rõ lý do và điều kiện xem lại, đặc biệt khi phản hồi đến từ người dùng hoặc đối tác đã dành thời gian tham gia nghiên cứu.

## 14. Phát hành dựa trên bằng chứng: không nhầm feedback với điều kiện an toàn

Phản hồi từ demo, thử nghiệm và quan sát giúp đánh giá **giá trị và khả năng sử dụng**, nhưng **không thay thế kiểm thử, Definition of Done hoặc quy trình an toàn vận hành**.

### 14.1. Ba cổng câu hỏi trước khi mở rộng

**Cổng 1 — Tính đúng và an toàn:** Increment đã đáp ứng tiêu chuẩn chất lượng, bảo mật, dữ liệu và quyền truy cập liên quan chưa? Có lỗi nghiêm trọng chưa xử lý không?

**Cổng 2 — Khả năng dùng và giá trị:** Người dùng có hoàn tất tác vụ thiết yếu không? Những điểm vướng có được hiểu ở mức đủ ra quyết định không?

**Cổng 3 — Khả năng vận hành và phục hồi:** Có giám sát, hỗ trợ, giới hạn rollout và khả năng xử lý khi sự cố xuất hiện không?

Đây là **khung hỏi minh họa**, không phải ba bước phê duyệt chính thức của Scrum. Với sản phẩm chịu quy định, có thể còn nhiều điều kiện bắt buộc; với sản phẩm ít rủi ro, quy trình có thể nhẹ hơn.

### 14.2. Decision matrix khi pilot

| Bằng chứng | Chất lượng/guardrail | Quyết định hợp lý |
| --- | --- | --- |
| Người dùng hoàn tất tốt, dữ liệu ổn. | Trong giới hạn chấp nhận được. | Xem xét mở rộng theo khả năng hỗ trợ. |
| Người dùng thích nhưng lỗi tạo trùng xuất hiện. | **Vi phạm nghiêm trọng.** | Dừng mở rộng, giảm ảnh hưởng và sửa lỗi trước. |
| Chất lượng ổn nhưng ít người hiểu Pending. | Đủ an toàn, giá trị chưa đạt. | Giữ phạm vi, cải tiến UI rồi thử lại. |
| Kết quả quan sát không rõ do event thiếu. | Chưa thấy lỗi nghiêm trọng. | Sửa instrumentation, bổ sung bằng chứng trước khi tuyên bố thành công. |
| Kết quả tiêu cực với tập khách mục tiêu. | Đủ an toàn. | Xem lại giả thuyết, cân nhắc thay hướng hoặc dừng ý tưởng. |
| Chỉ có lời khen tại demo. | Chưa có kiểm chứng tích hợp. | Không coi là căn cứ đủ để mở rộng tính năng rủi ro cao. |

**Lưu ý:** Không được dùng điều kiện “chưa thấy lỗi” như bằng chứng “không có lỗi” khi dữ liệu quá ít hoặc không có giám sát đầy đủ.

### 14.3. Tắt feature khác rollback mọi tác động

Giả sử một pilot gửi email nhầm “Đã xác nhận” cho lịch còn Pending. Tắt feature không thu hồi được email đã gửi. Cần:

- Xác định những người bị ảnh hưởng theo quyền truy cập được phép.
- Chỉnh trạng thái và đối soát dữ liệu nếu cần.
- Thông báo/hỗ trợ theo quy trình đã thỏa thuận.
- Sửa điều kiện phát thông báo, bổ sung kiểm thử.
- Kiểm tra hậu quả trước khi mở trở lại.

Tương tự, khi một thao tác gây giao dịch hoặc ghi dữ liệu thật, phải có phương án **bù trừ và khắc phục**, không chỉ tưởng tượng feature flag là nút “undo”.

### 14.4. Sprint Review không phải điều kiện duy nhất cho release

Trong Scrum, Increment có thể được giao cho stakeholder **trước khi Sprint kết thúc** nếu đã đáp ứng DoD và điều kiện liên quan. **Sprint Review không phải cổng phê duyệt phát hành.** Nhóm có thể mang dữ liệu từ pilot/release đã diễn ra vào Review để thảo luận Product Goal và cập nhật Product Backlog.

Ngược lại, một demo đẹp ở Sprint Review **không biến phần chưa đạt DoD thành Done**. Cần minh bạch hạng mục chưa hoàn tất và lý do.

## 15. Tình huống xuyên suốt: từ demo thành một vòng học thật

Toàn bộ số liệu và tình huống trong phần này đều là **giả định dùng để thực hành**, không đại diện một sản phẩm thực tế.

### 15.1. Bối cảnh sản phẩm và vấn đề ban đầu

Một Scrum Team xây web đặt lịch tư vấn. Product Goal:

> “Khách tự đặt lịch tư vấn hợp lệ và biết chắc trạng thái yêu cầu, không phải gọi tổng đài để hỏi xác nhận.”

Trong một Sprint, nhóm triển khai luồng chọn giờ, gửi yêu cầu và xem kết quả. **Sprint Goal** tập trung vào việc khách tạo được một lịch hợp lệ với kết quả rõ.

Tại demo, một số stakeholder nói màn hình rất đơn giản. Người hỗ trợ khách hàng hỏi: “Nếu mạng timeout sau khi backend đã nhận request thì sao?” Nhóm nhận ra **kịch bản trình diễn bình thường không kiểm chứng điều kiện quan trọng này**.

### 15.2. Quyết định nghiên cứu trước khi mở rộng

Nhóm tách hai vấn đề:

1. **An toàn dữ liệu:** Request lặp không tạo hai lịch; Pending/Unknown được đối soát.
2. **Khả năng hiểu của người dùng:** Trạng thái hiển thị rõ để khách không nhấn lại vô ý.

**Không nên chỉ chọn một:** Sửa UI không thay thế xử lý idempotency ở backend. Sửa backend giúp chống lỗi nhưng có thể khách vẫn phải gọi tổng đài vì không hiểu trạng thái.

### 15.3. Sử dụng thử sáu phiên minh họa

Nhóm mời **sáu người có nhu cầu đặt lịch tương tự**, gồm người lần đầu và người quay lại. Họ dùng dữ liệu thử và kịch bản mạng chậm. Kết quả giả định:

| Mã phiên | Hoàn thành tự lực? | Có nhấn lại? | Diễn giải Pending đúng? | Quan sát chính |
| --- | --- | --- | --- | --- |
| U01 | Có | Không | Có | Đọc trạng thái và chờ. |
| U02 | Có | Có | Không | Cho rằng request chưa được gửi. |
| U03 | Không | Có | Không | Không tìm thấy cách xem trạng thái. |
| U04 | Có | Không | Có | Quay lại xem yêu cầu. |
| U05 | Có | Có | Không | Tưởng Pending nghĩa là thất bại. |
| U06 | Có | Không | Có | Hiểu kết quả sau vài giây. |

Trong **mẫu thử minh họa**: 5/6 hoàn thành tự lực; 3/6 nhấn lại; 3/6 hiểu đúng Pending. Đây là **mô tả sáu phiên**, tuyệt đối không suy ra rằng đúng 50% toàn bộ khách hàng sẽ nhấn lại hoặc hiểu trạng thái.

**Insight:** Có một vấn đề đáng thử về cách giải thích Pending và đường tra cứu; nguyên nhân kỹ thuật gửi lặp vẫn cần kiểm tra riêng.

### 15.4. Điều chỉnh Increment và kiểm thử chất lượng

Nhóm chọn hai thay đổi:

- **Backend:** Idempotency/transaction bảo vệ bất biến, test cạnh tranh đồng thời và timeout; trạng thái Unknown không được tự coi là Rejected.
- **Giao diện:** Hiển thị “Yêu cầu đang được xử lý, chưa xác nhận lịch”, kèm cách xem trạng thái mà không tạo request mới.

**Definition of Done/chuẩn chất lượng:** Không gọi hạng mục Done chỉ vì demo trông đúng; các trường hợp gửi lặp, quyền truy cập, tích hợp và trạng thái quan trọng phải được kiểm chứng ở các tầng phù hợp.

### 15.5. Pilot có giám sát

Khi các điều kiện kỹ thuật và an toàn cho phép, nhóm mở cho **một tập khách có giới hạn** và theo dõi:

- Tỷ lệ phiên gửi lại nhiều lần.
- Tỷ lệ hoàn tất có trạng thái có thẩm quyền.
- Số ticket hỏi tình trạng.
- Lỗi tạo lịch trùng, độ trễ đuôi phân bố và số Pending/Unknown kéo dài.
- Phản hồi từ người dùng về khả năng hiểu và kênh hỗ trợ.

Nếu lỗi tạo lịch trùng xuất hiện, **ứng cứu và dừng mở rộng**, dù completion rate có vẻ tăng.

### 15.6. Ví dụ kết quả quan sát sau thay đổi

Giả sử một giai đoạn trước và một giai đoạn sau có cùng định nghĩa số đo, nhưng không phải thí nghiệm đối chứng:

| Tín hiệu giả định | Trước | Sau |
| --- | ---: | ---: |
| Phiên đủ điều kiện quan sát | 500 | 550 |
| Phiên có lịch Confirmed trong 24h | 300 | 363 |
| **Completion rate** | **60%** | **66%** |
| Phiên có ít nhất một submit | 360 | 400 |
| Phiên có submit lặp | 90 | 60 |
| **Duplicate submit rate** | **25%** | **15%** |
| Lượt liên hệ hỏi trạng thái | 45 | 33 |
| Lịch trùng đã xác minh | 0 | 0 |

Các tỷ lệ được tính từ dữ liệu giả định:

\[
\frac{300}{500}=60\%,\quad \frac{363}{550}=66\%
\]

\[
\frac{90}{360}=25\%,\quad \frac{60}{400}=15\%
\]

**Diễn giải thận trọng:** Các tín hiệu gợi ý sản phẩm có thể cải thiện nhưng **không chứng minh** riêng phần sửa UI tạo ra thay đổi vì backend cũng đổi, cơ cấu người dùng có thể khác và số liệu còn biến động. Số lịch trùng bằng 0 trong hai giai đoạn không chứng minh không còn rủi ro cho mọi trường hợp hiếm; test, giám sát và khả năng khôi phục vẫn cần thiết.

### 15.7. Phản hồi quay vào backlog như thế nào?

Sau demo, thử và pilot, nhóm thống nhất:

| Bằng chứng | Quyết định | Mục backlog/hoạt động |
| --- | --- | --- |
| UI Pending khó hiểu | Sửa cách diễn đạt và đường xem trạng thái | User story/lát cắt về trạng thái và khả năng tra cứu. |
| Retry nguy cơ tạo trùng | Ưu tiên an toàn trước mở rộng | Lỗi/technical improvement với test chống trùng. |
| Người dùng vẫn cần biết khi xác nhận mất lâu | Nghiên cứu thêm kỳ vọng thời gian và kênh thông báo | Discovery timebox, có câu hỏi và tiêu chí dừng. |
| Có stakeholder muốn SMS | Chưa đủ bằng chứng giá trị ưu tiên | Giữ ý tưởng trong backlog, không đưa thẳng vào Sprint. |
| Nhiều người dùng cần trợ năng | Kiểm chứng luồng thông báo với screen reader | Kiểm thử tiếp cận và sửa các điểm cản trở. |

Tại **Sprint Review**, Scrum Team cùng stakeholder xem Increment, phản hồi và tiến độ Product Goal; Product Backlog được điều chỉnh khi phù hợp. Trong **Sprint Retrospective**, nhóm nhìn lại cách phối hợp và nhận ra cần thử trạng thái mạng chậm **sớm hơn trong phát triển**, không chỉ cuối Sprint.

### 15.8. Vòng tiếp theo

Nhóm không mặc định “sửa xong, vấn đề hết”. Ở vòng kế:

1. Bổ sung instrumentation về thời gian nhận trạng thái có thẩm quyền.
2. Thử khả năng hiểu sau khi thay copy/flow với những người phù hợp, gồm nhu cầu trợ năng.
3. Theo dõi phân đoạn mạng chậm và tỷ lệ Unknown kéo dài.
4. Đánh giá liệu kênh thông báo khác có thật sự cần thiết và giá trị so với chi phí.
5. Chia sẻ điều học được, kể cả giả thuyết bị bác bỏ.

**Đó là phản hồi Agile có ích:** Mỗi vòng giúp nhóm **hiểu người dùng và hệ thống tốt hơn**, giao một thay đổi có kiểm chứng và điều chỉnh kế hoạch dựa trên bằng chứng thay vì cảm giác demo thành công.

## 16. Kết nối phản hồi với Scrum, Kanban, XP và mục tiêu Agile

### 16.1. Scrum: Sprint là cơ hội tạo Increment và học từ stakeholder

Trong Scrum, vòng phản hồi gắn với:

| Phần Scrum | Vai trò đối với phản hồi | Điều cần tránh |
| --- | --- | --- |
| **Product Goal / Product Backlog** | Làm rõ kết quả giá trị và những hạng mục cần thử hoặc giao tiếp. | Biến mọi ý kiến thành ticket ưu tiên cao. |
| **Sprint Goal / Sprint Planning** | Chọn một kết quả ngắn hạn có thể kiểm tra, làm rõ rủi ro và cách đo. | Chỉ lên kế hoạch theo số story point. |
| **Daily Scrum** | Developers kiểm tra tiến độ tới Sprint Goal và điều chỉnh kế hoạch; vấn đề kỹ thuật từ phản hồi có thể được xử lý sớm. | Biến thành họp báo cáo cho quản lý hoặc phỏng vấn stakeholder. |
| **Increment / Definition of Done** | Chứng minh phần mềm đủ điều kiện chất lượng để sử dụng; có thể tạo nhiều Increment trong Sprint. | Gọi mock chưa tích hợp là Done. |
| **Sprint Review** | Scrum Team và stakeholder kiểm tra kết quả, bối cảnh và thích ứng Product Backlog khi cần. | Chỉ trình diễn đường đi đẹp rồi xin ký duyệt. |
| **Sprint Retrospective** | Cải tiến cách thu thập, kiểm thử và dùng phản hồi trong workflow. | Chỉ nhận xét về UI mà quên vấn đề phối hợp và chất lượng. |

**Product Owner** chịu trách nhiệm tối đa hóa giá trị và quản lý hiệu quả Product Backlog; **Developers** xây Increment và giữ chất lượng; **Scrum Master** giúp Scrum Team nâng hiệu quả. Người làm nghiên cứu, hỗ trợ, vận hành và chuyên gia miền có thể cộng tác theo bối cảnh nhưng **không tự biến thành accountability chính thức thứ tư của Scrum**.

Một Sprint Review có giá trị khi nhóm có thể nói:

> “Chúng ta đã giao lát cắt nào đạt DoD? Người dùng đã làm được gì? Bằng chứng nào củng cố hoặc bác bỏ giả định? Điều này thay đổi cách nhìn Product Goal và thứ tự backlog như thế nào?”

### 16.2. Kanban: đừng để phản hồi mắc kẹt trong hàng đợi

Kanban giúp nhìn **dòng của công việc phát sinh từ phản hồi**:

~~~text
Tín hiệu mới
   -> Cần làm rõ
      -> Đã triage/ưu tiên
         -> Discovery hoặc phát triển
            -> Kiểm chứng
               -> Giao và theo dõi kết quả
~~~

Các trạng thái chỉ minh họa. Nhóm cần định nghĩa workflow thật, chính sách kéo việc, WIP và cách xử lý blocked. **Một insight chưa được xử lý không tự đồng nghĩa story cần phát triển**; nó có thể là câu hỏi nghiên cứu hoặc một quyết định không thực hiện.

Những tín hiệu flow hữu ích:

- **Work item age:** Một phản hồi nghiêm trọng hoặc hạng mục sửa lỗi đang chờ bao lâu?
- **Cycle time:** Từ lúc bắt đầu xử lý đến khi quyết định/giao kết quả theo ranh giới định nghĩa mất bao lâu?
- **WIP:** Bao nhiêu giả thuyết hoặc feature đang được mở mà chưa kiểm chứng?
- **Throughput:** Bao nhiêu hạng mục có kết quả rõ trong một khoảng thời gian?

**Không đánh đồng throughput của ticket phản hồi với số insight đúng hoặc giá trị sản phẩm.** Một nhóm trả lời 100 bình luận không nhất thiết học nhiều hơn nhóm tập trung kiểm chứng một giả định có ảnh hưởng lớn.

### 16.3. XP: phản hồi kỹ thuật giúp phản hồi sản phẩm đáng tin

**Extreme Programming** có những thực hành giúp rút ngắn vòng phản hồi:

- **TDD:** Giữ hành vi quan trọng được kiểm chứng khi nhóm sửa tính năng theo phản hồi.
- **Continuous Integration:** Phát hiện lỗi tích hợp sớm thay vì đợi tới demo cuối Sprint.
- **Refactoring:** Giữ cấu trúc có thể thay đổi khi hiểu biết miền phát triển.
- **Pair programming:** Chia sẻ ngữ cảnh và cải thiện chất lượng quyết định kỹ thuật.
- **Small releases:** Cung cấp phần nhỏ có ích để học sớm khi điều kiện phát hành cho phép.

Nếu muốn thử UI mới nhưng không có cách phân biệt trạng thái backend chính xác, kết quả nghiên cứu dễ bị nhiễu bởi lỗi kỹ thuật. **Phản hồi sản phẩm và phản hồi kỹ thuật cần cùng hoạt động**, không thể chỉ tổ chức nhiều buổi phỏng vấn rồi bỏ qua chất lượng.

### 16.4. Những vòng phản hồi có thời gian khác nhau

| Vòng | Thời gian phản hồi điển hình | Bằng chứng |
| --- | --- | --- |
| **Test/CI** | Phút tới giờ khi được tổ chức phù hợp. | Build, unit/integration tests, linter, contract tests. |
| **Trao đổi nhanh về yêu cầu** | Trong ngày hoặc theo nhịp cộng tác. | Ví dụ nghiệp vụ, kịch bản chấp nhận, giả định còn mở. |
| **Demo/Review** | Theo lịch sản phẩm hoặc nhịp Sprint. | Increment và phản hồi stakeholder. |
| **Usability test** | Theo kế hoạch thử có mục tiêu. | Hành vi tự thao tác, khó khăn và lời nói. |
| **Pilot/production telemetry** | Liên tục nhưng cần đủ thời gian và dữ liệu hợp lệ để diễn giải. | Hành vi, chất lượng, adoption và outcome. |
| **Đo impact dài hạn** | Có thể kéo dài nhiều tuần/tháng. | Chi phí hỗ trợ, duy trì sử dụng, kết quả kinh doanh hoặc xã hội. |

Không phải vòng nào cũng cần đợi vòng trước kết thúc. Nhóm có thể demo Increment trong khi vẫn theo dõi phiên pilot đã phát hành, và dùng kiểm thử tự động liên tục để bảo vệ hành vi.

## 17. Một nhịp phối hợp phản hồi khả thi cho nhóm sản phẩm

Một nhóm không nhất thiết cần một “hội đồng phản hồi” lớn. Điều cần là **cách đưa bằng chứng tới đúng người quyết định** và không để thông tin biến mất trong tài liệu.

### 17.1. Chính sách minh họa

| Khi nào? | Ai thường phối hợp? | Quyết định/đầu ra |
| --- | --- | --- |
| Khi có lỗi nghiêm trọng | Người trực ứng cứu, Developers, vận hành và người có thẩm quyền. | Giảm thiệt hại, điều tra và xử lý theo mức nghiêm trọng. |
| Khi có phản hồi mới | Người nhận phản hồi, Product Owner hoặc người quản lý sản phẩm, nhóm có chuyên môn. | Ghi nguồn và bối cảnh, phân loại sơ bộ. |
| Khi cần thử giả thuyết | Product Owner, nghiên cứu/thiết kế nếu có, Developers, người dùng phù hợp. | Câu hỏi, phương pháp, phạm vi, điều kiện an toàn và tiêu chí dừng. |
| Khi cần chọn backlog | Product Owner cùng Scrum Team/người liên quan. | Thứ tự dựa trên giá trị, rủi ro, năng lực và bằng chứng. |
| Khi xem Increment | Scrum Team và stakeholder phù hợp. | Review kết quả, phản hồi và thích ứng hướng sản phẩm. |
| Khi xem cách làm | Scrum Team. | Cải tiến khả năng nhận phản hồi, kiểm thử và phát hành. |

**Quyền quyết định phải theo cơ cấu thật của tổ chức**, không tự tạo một vai trò “Feedback Owner” có quyền bỏ qua Product Owner hoặc người chịu trách nhiệm an toàn.

### 17.2. Một cuộc xem insight ngắn

Thay vì đọc tất cả bình luận theo thứ tự đến, hãy đi từ câu hỏi:

1. Có **rủi ro hoặc thiệt hại hiện tại** phải xử lý ngay không?
2. **Giả thuyết quan trọng nhất** đang có bằng chứng mới gì?
3. Những điều nào **đã xác minh, đang suy đoán hoặc thiếu dữ liệu**?
4. Quyết định hiện tại là **thực hiện, thử nhỏ, cần thêm bằng chứng hay không làm**?
5. Nếu quyết định làm, **ai chịu trách nhiệm** và khi nào xem kết quả?

Cần ngắn, đủ người và tạo hành động. Nếu nhóm tổ chức thêm một buổi họp nhưng phản hồi vẫn nằm trong một bảng không ai xem, đó là lãng phí.

### 17.3. Không làm đứt vòng phản hồi khi nhiều đội tham gia

Ví dụ, bộ phận hỗ trợ nhận phản ánh khách bị đặt trùng. Nếu support chỉ đóng ticket với câu “đã chuyển cho kỹ thuật”, Product Owner chưa biết mức ảnh hưởng và Developers chưa thấy bằng chứng, vấn đề có thể kéo dài.

Một luồng phối hợp tốt cần:

- Nguồn phản hồi có **mã tham chiếu và bối cảnh** phù hợp, không kèm dữ liệu cá nhân tùy tiện.
- Có đường **triage mức nghiêm trọng** và người chịu trách nhiệm xử lý.
- Liên kết vấn đề sản phẩm với lỗi kỹ thuật và test xác nhận.
- Theo dõi kết quả sau sửa, chia sẻ lại với support/người dùng khi thích hợp.
- Đánh giá vì sao lỗi lọt qua và cách rút ngắn phản hồi ở vòng sau.

### 17.4. Các quyết định “không làm” cũng có giá trị

Phản hồi “tôi muốn mọi lịch đều gửi SMS” có thể không đủ giá trị nếu phần lớn khách đã nhận xác nhận tốt qua kênh khác và SMS tạo chi phí/độ trễ mới. Nhóm có thể **chưa triển khai**, ghi căn cứ và điều kiện xem lại.

**Không làm một ý tưởng ít giá trị** có thể là kết quả tốt của một vòng phản hồi. Agile khuyến khích thích ứng dựa trên hiểu biết, không yêu cầu biến mọi đề xuất thành code.

## 18. Các phản mẫu khiến thu thập phản hồi không tạo giá trị

| Phản mẫu | Vì sao gây hại | Cách cải tiến |
| --- | --- | --- |
| **Demo chỉ trình diễn happy path** | Che lỗi, trạng thái bất thường và giả định nghiệp vụ. | Thêm tình huống biên, nói rõ Done/chưa Done, thảo luận kết quả. |
| **Lấy lời khen demo làm bằng chứng usability** | Người xem không trực tiếp làm tác vụ. | Quan sát người dùng tự thao tác trong phiên phù hợp. |
| **Gọi Sprint Review là buổi nghiệm thu phát hành** | Làm chậm release và giảm đối thoại về Product Goal. | Dùng Review để kiểm tra/thích ứng, không làm cổng bắt buộc. |
| **Thử nghiệm với toàn đồng nghiệp nội bộ** | Mẫu không phản ánh trải nghiệm khách mới. | Tuyển đúng đối tượng và nhu cầu sử dụng. |
| **Người điều phối chỉ từng nút** | Che khó khăn thực và làm completion sai. | Đưa tác vụ có ngữ cảnh, ghi thời điểm cần trợ giúp. |
| **Chỉ hỏi “có thích không?”** | Nhận ý kiến lịch sự, ít hành vi. | Hỏi về tác vụ, kỳ vọng, điểm chưa hiểu, quan sát trực tiếp. |
| **Xem request gửi lại là đặt lịch trùng** | Trộn hành vi với kết quả dữ liệu. | Phân biệt attempt, accepted, confirmed và duplicate thực. |
| **Funnel không có mẫu số rõ** | So sánh sai khi đơn vị là click, phiên hoặc người. | Định nghĩa metric contract và phiên bản sự kiện. |
| **Chỉ xem trung bình** | Che nhóm đợi lâu hoặc lỗi hiếm nghiêm trọng. | Xem phân bố, phân đoạn, tail và guardrails. |
| **Chỉ đọc ý kiến tích cực** | Confirmation bias làm nhóm không sửa giả định. | Lưu cả bằng chứng trái chiều và kết quả bác bỏ. |
| **Suy nguyên nhân từ hai tuần trước/sau** | Biến số môi trường và mẫu có thể khác. | Thiết kế so sánh phù hợp, nêu giới hạn. |
| **Mở beta để thử chức năng không an toàn** | Chuyển rủi ro sang người dùng thật. | Giữ chuẩn chất lượng và điều kiện dừng/ứng cứu. |
| **Thu dữ liệu cá nhân quá mức** | Tăng rủi ro riêng tư, bảo mật và niềm tin. | Tối thiểu hóa, kiểm soát truy cập, chính sách lưu trữ. |
| **Biến mọi bình luận thành story** | Backlog phình to, ưu tiên bị nhiễu. | Triage theo vấn đề, bằng chứng, giá trị, rủi ro. |
| **Không theo dõi sau sửa** | Không biết thay đổi có tạo giá trị hoặc lỗi mới. | Đo lại outcome, flow, chất lượng và phản hồi người dùng. |
| **Dùng feedback để chấm cá nhân** | Khuyến khích che lỗi, phòng thủ và chọn bằng chứng đẹp. | Dùng để cải tiến hệ thống và trách nhiệm nhóm. |
| **Kết luận không có lỗi vì chưa thấy lỗi** | Mẫu nhỏ, telemetry thiếu và sự kiện hiếm dễ bị bỏ sót. | Giữ test/guardrails, đo đầy đủ, quản lý bất định. |
| **Sản phẩm có dashboard nhưng không ai quyết định** | Thu thập tốn kém mà backlog và hướng đi không đổi. | Gắn mỗi tín hiệu với quyết định, người phụ trách và thời điểm xem lại. |

### 18.1. “Người dùng nói muốn X” không có nghĩa phải xây X

Người dùng nêu **giải pháp họ hình dung**, nhưng nhóm cần hiểu **vấn đề thực, hoàn cảnh và kết quả họ muốn**. Ví dụ người dùng yêu cầu nút Gửi lại to hơn vì không biết lịch đang Pending. Tăng kích thước nút có thể làm **tình trạng gửi lặp nặng hơn**; một màn hình trạng thái rõ và tra cứu an toàn có thể phù hợp hơn.

### 18.2. “Dữ liệu nhiều” không có nghĩa “dữ liệu tốt”

Một triệu click events thiếu định nghĩa hoặc chứa dữ liệu trùng có thể ít hữu ích hơn **vài chục phiên có đủ bối cảnh, kiểm chứng backend và thống nhất mẫu số**. Chất lượng sự kiện, mẫu và câu hỏi nghiên cứu quyết định giá trị của phân tích.

### 18.3. “Feedback nhanh” không đồng nghĩa “thay đổi không kiểm soát”

Agile đón nhận thay đổi nhưng vẫn bảo vệ chất lượng, quyền riêng tư và mục tiêu sản phẩm. Nhóm có thể sửa thứ tự backlog khi học thêm; nhưng không nên tự ý bật feature nguy hiểm cho hàng nghìn người chỉ để xem conversion có tăng không.

## 19. Bài tập tình huống và hướng giải

### Tình huống A — Một demo được khen nhưng người dùng thử thất bại

Sprint Review có một demo đặt lịch rất đẹp; stakeholder khen giao diện. Sau đó, bốn trên tám người thử không tự tìm được cách xác định lịch đã Confirmed. Product Owner nói: “Stakeholder đã duyệt rồi, cứ phát hành.”

**Câu hỏi:**

1. Hai loại bằng chứng có mâu thuẫn trực tiếp không?
2. Đâu là vấn đề cần khám phá hoặc sửa trước?
3. Vì sao Sprint Review không thay thế usability test?
4. Một lát cắt cải tiến nhỏ có thể là gì?

**Hướng giải:** Demo có hướng dẫn và tác vụ không hướng dẫn đánh giá những điều khác nhau. Cần điều tra cách người dùng hiểu trạng thái, có thể thử copy rõ hơn và đường tra cứu; kiểm tra backend chống gửi lặp trước mở rộng. Review giúp thảo luận hướng sản phẩm, không chứng minh mọi người tự dùng được. Tám người là mẫu nhỏ, không nên suy tỷ lệ cho toàn tập.

### Tình huống B — Dashboard báo completion 90%

Nhóm có 900 lượt hiển thị toast “Thành công” trên 1.000 lần nhấn nút. Backend cho thấy chỉ 770 lịch đã Confirmed. Marketing báo “tỷ lệ đặt lịch thành công 90%”.

**Câu hỏi:**

1. Vì sao chỉ số 90% có thể sai về ngữ nghĩa?
2. Mẫu số đúng cần định nghĩa thế nào?
3. Cần những event hoặc kiểm chứng nào?

**Hướng giải:** Toast hoặc click không phải lịch Confirmed; có retry và nhiều attempt mỗi phiên. Nên thống nhất tiêu chí thành công có thẩm quyền ở backend, chọn đơn vị phiên/yêu cầu và cửa sổ thời gian, đối soát event, phân biệt accepted/pending/confirmed/failed. Số 770 không tự tạo completion rate cho người dùng nếu chưa xác định số phiên/người bắt đầu.

### Tình huống C — Beta có bug nghiêm trọng

Trong pilot với một số khách thật, tỷ lệ hoàn tất tác vụ cải thiện nhưng xuất hiện lỗi đặt trùng và phải hủy lịch của khách khác.

**Câu hỏi:**

1. Có nên tiếp tục tăng người dùng để có mẫu lớn hơn?
2. Cần hành động theo hướng an toàn nào?
3. Có thể tiếp tục học điều gì mà không tăng rủi ro?

**Hướng giải:** Không mở rộng khi guardrail quan trọng đã vi phạm. Kích hoạt quy trình ứng cứu, giảm thiệt hại, đối soát và hỗ trợ khách theo thẩm quyền; sửa bất biến với kiểm thử cạnh tranh. Có thể tiếp tục nghiên cứu UI trong môi trường thử an toàn trong khi giữ production được bảo vệ.

### Tình huống D — Định tính và định lượng khác nhau

Năm người thử nói màn hình “dễ dùng”; telemetry production cho thấy tỷ lệ bỏ dở cao ở khách dùng điện thoại cũ.

**Câu hỏi:**

1. Có thể có nguyên nhân nào không phải giả dối hay đo lường sai?
2. Phân đoạn và dữ liệu nào cần xem?
3. Phiên thử tiếp theo nên thay đổi gì?

**Hướng giải:** Mẫu thử có thể chỉ gồm thiết bị mới; performance trên máy cũ khác; mạng, font và trợ năng có thể ảnh hưởng. Xem thiết bị, phiên bản trình duyệt, độ trễ, lỗi client, funnel theo cohort; tuyển thêm người có bối cảnh liên quan và quan sát tác vụ trên thiết bị phù hợp.

### Tình huống E — Stakeholder đề nghị SMS

Một lãnh đạo đề nghị gửi SMS sau mọi lịch vì “khách thích được nhắc”. Nhóm chưa đo tỷ lệ khách không nhận được email hoặc lợi ích SMS. Nhà cung cấp SMS tính phí theo lượt.

**Câu hỏi:**

1. Đây là dữ liệu về nhu cầu hay một đề xuất giải pháp?
2. Có thể kiểm tra nhu cầu mà không xây hệ thống SMS toàn diện không?
3. Thước đo nào cân bằng giá trị và chi phí?

**Hướng giải:** Đây chủ yếu là đề xuất giải pháp. Hỏi khách cần xác nhận lúc nào, vì sao email không đủ; phân đoạn người thực sự cần, thử nội dung/kênh trong phạm vi an toàn, đánh giá tỷ lệ lịch được nhận biết, hỗ trợ, chi phí gửi và rủi ro bảo mật/riêng tư. Không ưu tiên chỉ vì chức vụ hoặc cảm giác.

### Tình huống F — Sau phát hành, lượt liên hệ hỗ trợ giảm

Tuần trước có 100 cuộc gọi về trạng thái và 2.000 lịch yêu cầu. Tuần sau có 70 cuộc gọi và 1.000 lịch yêu cầu. Một người nói “hỗ trợ giảm 30%, UI thành công”.

**Câu hỏi:**

1. Số cuộc gọi tuyệt đối nói lên điều gì?
2. Tính **tỷ lệ cuộc gọi trên 100 yêu cầu** cho mỗi tuần.
3. Kết luận “UI thành công” có đúng không?

**Đáp án:** Tuần trước \(100/2000\times100=5\) cuộc gọi/100 yêu cầu; tuần sau \(70/1000\times100=7\) cuộc gọi/100 yêu cầu. Số tuyệt đối giảm nhưng tỷ lệ **tăng**, trong ví dụ giả định. Cần kiểm tra mẫu, cách phân loại, kênh hỗ trợ và các yếu tố khác trước khi quy nguyên nhân.

### Tình huống G — Ghi session replay chứa dữ liệu cá nhân

Nhóm muốn xem vì sao khách không hoàn tất đặt lịch, liền bật ghi hình toàn bộ màn hình, gồm số điện thoại, thông tin tư vấn và các trường nhập nhạy cảm, cho mọi nhân viên có quyền xem.

**Câu hỏi:**

1. Những rủi ro nào xuất hiện?
2. Có phương án thu thập ít dữ liệu hơn không?
3. Cần xem những quyền và chính sách nào?

**Hướng giải:** Rủi ro quyền riêng tư, bảo mật, lộ dữ liệu nhạy cảm, lưu vượt mục đích và truy cập quá rộng. Thử event có ngữ nghĩa, số đo tổng hợp, quan sát tình nguyện với dữ liệu giả; chỉ thu session replay nếu được đánh giá và bảo vệ thích hợp, có quyền truy cập/hạn lưu/che dữ liệu và cơ sở xử lý phù hợp.

### Tình huống H — Hai tính năng cùng thay đổi khi pilot

Nhóm đồng thời sửa UI trạng thái và nâng cấp API đối tác. Sau đó tỷ lệ gửi lại giảm từ 25% xuống 15%. Product Owner nói: “Chứng minh UI mới làm giảm 10 điểm phần trăm.”

**Câu hỏi:**

1. Có thể kết luận riêng UI là nguyên nhân không?
2. Có thể thiết kế phép thử phù hợp thế nào khi đảm bảo an toàn?
3. Nếu không thể làm A/B test, cần báo cáo ra sao?

**Hướng giải:** Không thể quy riêng UI vì backend cũng đổi và còn biến số khác. Có thể thử khả năng hiểu của UI qua tác vụ độc lập, so sánh các phiên bản an toàn với phân nhóm thích hợp nếu được phép; bảo vệ backend như nhau ở mọi nhóm. Nếu chỉ có dữ liệu quan sát, báo “tỷ lệ giảm sau các thay đổi” kèm giới hạn, không nói “UI chắc chắn gây giảm”.

## 20. Workshop 60–75 phút: thiết kế một vòng phản hồi hoàn chỉnh

### 20.1. Đề bài

Một Scrum Team xây hệ thống đặt lịch tư vấn. Stakeholder thích giao diện hiện tại, nhưng có một số khách phản ánh “nhấn Đặt lịch mà không biết đã được nhận chưa”; telemetry cũng có dấu hiệu gửi lại khi mạng chậm. Nhóm dự định phát hành rộng trong kỳ tới.

**Nhiệm vụ:** Thiết kế một kế hoạch thu thập phản hồi vừa giúp chọn đúng thay đổi vừa không chuyển rủi ro dữ liệu sang khách.

### 20.2. Gợi ý tổ chức workshop

| Thời gian | Hoạt động | Đầu ra |
| --- | --- | --- |
| **0–10 phút** | Thống nhất người dùng, tác vụ và điều chưa biết. | Một câu vấn đề và một giả thuyết có thể bác bỏ. |
| **10–20 phút** | Phân loại nguồn phản hồi đã có: demo, trial, telemetry. | Bản đồ bằng chứng và khoảng trống. |
| **20–35 phút** | Thiết kế một phiên sử dụng thử không dẫn dắt. | Tác vụ, người thử, cách quan sát, bảo vệ dữ liệu. |
| **35–45 phút** | Chọn metric contract và guardrails. | Tên event, mẫu số, cửa sổ, điều kiện dừng. |
| **45–55 phút** | Quy định cách triage và ưu tiên backlog. | Loại công việc, người quyết định, giả định còn mở. |
| **55–65 phút** | Thiết kế pilot/phát hành giới hạn phù hợp. | Phạm vi, hỗ trợ, giám sát, rollback/đối soát. |
| **65–75 phút** | Trình bày, phản biện và chốt cách học tiếp. | Một kế hoạch, ngày xem lại, tiêu chí quyết định. |

Đây là khung minh họa. Với một vấn đề nhỏ, nhóm có thể rút gọn; với hệ thống chịu nghĩa vụ nghiêm ngặt, cần thêm đánh giá chuyên môn và quyền phê duyệt phù hợp.

### 20.3. Mẫu kế hoạch một trang

~~~text
Product Goal / outcome người dùng:
Vấn đề cần giải quyết:
Đối tượng/phân đoạn:
Giả thuyết:
Bằng chứng đã có:
Điều chưa biết:

DEMONSTRATION
  - Kịch bản bình thường và biên:
  - Người cần tham gia:
  - Câu hỏi về quy tắc và giá trị:

TRIAL USE
  - Tác vụ không hướng dẫn từng bước:
  - Tiêu chí hoàn tất:
  - Mẫu người thử và giới hạn:
  - Quan sát và câu hỏi trung tính:
  - Đồng ý, riêng tư, dữ liệu thử:

REAL-WORLD OBSERVATION
  - Event và ý nghĩa:
  - Mẫu số và cửa sổ:
  - Phân đoạn và rủi ro dữ liệu thiếu:
  - Support/operational signals:
  - Guardrails:

DECISION
  - Khi nào sửa ngay / thử thêm / mở rộng / dừng:
  - Ai có thẩm quyền:
  - Product Backlog Item hoặc spike:
  - Ngày và cách kiểm chứng lại:
  - Cách chia sẻ kết quả cho người tham gia:
~~~

### 20.4. Ví dụ một phương án đạt yêu cầu

**Giả thuyết:** Khách gửi lặp vì không thấy trạng thái rõ trong mạng yếu.

**Demo:** Xem trạng thái Confirmed/Pending/Unknown với chuyên gia miền và người hỗ trợ; kiểm tra nghĩa khi đối tác timeout.

**Sử dụng thử:** Mời khách lần đầu ở thiết bị phù hợp; yêu cầu đặt lịch rồi xác định trạng thái, quan sát nhấn lại mà không hướng dẫn đường đi; dùng dữ liệu thử.

**Quan sát:** Đo theo phiên, phân biệt attempt và lịch Confirmed; xem tỷ lệ gửi lặp, hoàn tất, phân bố độ trễ và liên hệ hỗ trợ; theo dõi lỗi tạo trùng.

**Hành động:** Sửa lỗi idempotency nếu có trước pilot; thử UI trạng thái; không triển khai SMS lớn chỉ từ một ý kiến.

**Quyết định phát hành:** Chỉ mở rộng khi guardrail chất lượng không bị vi phạm và khả năng sử dụng đủ phù hợp; nếu bằng chứng còn thiếu, giữ phạm vi quan sát.

**Điểm xem lại:** Sau vòng thử, trao đổi bằng chứng với Product Owner, Developers và stakeholder; cập nhật backlog và điều kiện kiểm tra của vòng kế.

### 20.5. Tiêu chí đánh giá kế hoạch

Một kế hoạch đủ tốt cần cho người khác trả lời được:

1. **Bằng chứng nào sẽ khiến chúng ta đổi quyết định?**
2. **Người dùng nào và tác vụ nào thực sự được kiểm tra?**
3. **Chỉ số có mẫu số và nguồn dữ liệu rõ không?**
4. **Khi có lỗi nghiêm trọng, ai có quyền dừng và xử lý?**
5. **Dữ liệu cá nhân được bảo vệ như thế nào?**
6. **Insight sẽ thay đổi backlog hoặc kế hoạch phát hành bằng cách nào?**
7. **Có quay lại xem kết quả sau khi thay đổi không?**

Nếu chỉ có biểu mẫu khảo sát dài hoặc dashboard nhiều biểu đồ mà không có câu trả lời cho những câu hỏi này, kế hoạch thu thập phản hồi chưa đủ tính hành động.

## 21. Checklist áp dụng trước, trong và sau vòng phản hồi

### Trước khi thu thập

- [ ] Có vấn đề người dùng, outcome và giả thuyết rõ; không chỉ có giải pháp muốn xác nhận.
- [ ] Chọn phương pháp theo câu hỏi: demo, thử tác vụ, quan sát thực tế hoặc phối hợp.
- [ ] Người tham gia phù hợp với đối tượng cần nghiên cứu; nhận diện thiên lệch mẫu.
- [ ] Demo nói rõ đâu là Increment Done, prototype hay thành phần mô phỏng.
- [ ] Tác vụ thử không hướng dẫn từng bước; có tiêu chí hoàn tất độc lập.
- [ ] Có phương án đồng ý/thông báo, quyền riêng tư, quyền truy cập và bảo vệ dữ liệu phù hợp.
- [ ] Analytics có định nghĩa event, mẫu số, cửa sổ và cách xử lý dữ liệu thiếu.
- [ ] Những guardrails chất lượng, bảo mật và điều kiện dừng đã rõ.

### Trong khi thu thập

- [ ] Phân biệt điều người dùng nói, điều quan sát được và điều nhóm suy luận.
- [ ] Không dẫn dắt câu trả lời hoặc ép người dùng hoàn tất tác vụ.
- [ ] Ghi cả trường hợp thất bại, bị chặn và phản hồi trái ý kiến ban đầu.
- [ ] Không cho người tham gia tạo dữ liệu hoặc giao dịch thật nguy hiểm chỉ để thử.
- [ ] Ghi số lần hỗ trợ, sự cố môi trường, giới hạn mẫu và thay đổi instrumentation.
- [ ] Sự kiện kỹ thuật phân biệt attempt, accepted, confirmed, pending và failure.
- [ ] Nếu guardrail bị vi phạm, ứng cứu theo thẩm quyền thay vì tiếp tục để lấy thêm mẫu.

### Sau khi thu thập

- [ ] Insight có nguồn, bối cảnh, phạm vi, mức độ chắc chắn và giới hạn.
- [ ] Dữ liệu định tính được đối chiếu với định lượng khi có ích; mâu thuẫn không bị giấu.
- [ ] Không quy nguyên nhân từ tương quan hoặc từ vài người thử.
- [ ] Phản hồi đã được triage thành lỗi, nhu cầu, discovery, cải tiến kỹ thuật hoặc chưa hành động.
- [ ] Backlog được ưu tiên theo giá trị, rủi ro, bằng chứng và năng lực, không theo người nói lớn nhất.
- [ ] Quyết định phát hành giữ Definition of Done và các tiêu chuẩn an toàn áp dụng.
- [ ] Có người theo dõi, thời điểm kiểm tra lại và cách chia sẻ kết quả.
- [ ] Những giả thuyết bị bác bỏ cũng được ghi như kiến thức có giá trị.
- [ ] Nhóm xem cách cải tiến vòng phản hồi tiếp theo, không chỉ thay màn hình.

## 22. Ghi nhớ cốt lõi

**Trình diễn, sử dụng thử và quan sát thực tế trả lời những câu hỏi khác nhau.** Demo tạo cơ hội thảo luận về kết quả và quy tắc; sử dụng thử cho thấy người dùng có thực sự làm được việc khi tự thao tác; quan sát thực tế cho thấy hành vi, độ tin cậy và tác động trong môi trường nhiều biến động.

Nhớ năm nguyên tắc:

1. **Bắt đầu bằng quyết định cần hỗ trợ**, rồi mới chọn nguồn phản hồi.
2. **Phân biệt ý kiến, hành vi, số đo và suy luận**; không coi lời khen demo là bằng chứng mọi người dùng được.
3. **Đo đúng ngữ nghĩa và mẫu số**; cú nhấp không phải giao dịch thành công, số lượt không phải số người và tương quan chưa phải nguyên nhân.
4. **Bảo vệ người dùng và dữ liệu** trong mọi thử nghiệm; pilot không phải lý do hạ chuẩn chất lượng.
5. **Đóng vòng học hỏi:** Tổng hợp, triage, quyết định, đưa vào backlog hoặc dừng, giao lát cắt có kiểm chứng và quan sát lại.

Trong **Scrum**, Sprint Review giúp kiểm tra kết quả và thích ứng Product Backlog, còn Increment phải đáp ứng Definition of Done; Review không phải cổng phát hành. **Kanban** giúp nhìn dòng xử lý feedback và điểm chờ. **XP** giúp kiểm thử, tích hợp và refactor an toàn để phản hồi sản phẩm có thể chuyển thành phần mềm hoạt động đáng tin.

**Phản hồi có giá trị không được đo bằng số cuộc họp, số survey hay số event thu được, mà bằng khả năng nhóm ra quyết định tốt hơn, sửa đúng vấn đề và giao giá trị sớm mà vẫn bảo vệ người dùng.**

### Tài liệu tham khảo nền tảng

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — cộng tác với khách hàng, phần mềm hoạt động và đáp ứng thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — giao thường xuyên, phối hợp, kỹ thuật tốt và cải tiến liên tục.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Sprint Review, Increment, Definition of Done, Product Goal và trách nhiệm Scrum Team.
- [The Kanban Guide](https://kanbanguides.org/) — workflow, kiểm soát WIP, work item age, cycle time và cải tiến dòng công việc.
- [Nielsen Norman Group — Articles](https://www.nngroup.com/articles/) — tham khảo phương pháp usability testing, nghiên cứu người dùng và thiết kế dựa trên bằng chứng.
- [GOV.UK Service Manual](https://www.gov.uk/service-manual) — tham khảo cách nghiên cứu nhu cầu và cải tiến dịch vụ dựa trên trải nghiệm thực tế.
- [DORA](https://dora.dev/) — tham khảo năng lực giao thay đổi phần mềm và độ ổn định vận hành.
