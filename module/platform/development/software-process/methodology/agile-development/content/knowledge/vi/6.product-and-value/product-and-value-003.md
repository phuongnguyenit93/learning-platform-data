# Liên kết tầm nhìn, mục tiêu sản phẩm và công việc ngắn hạn

Trong một dự án Agile, nhóm thường làm việc theo các chu kỳ ngắn: làm rõ user story, chọn hạng mục trong backlog, xây dựng, kiểm thử và bàn giao phần mềm hoạt động. Tuy nhiên, **hoàn thành nhiều hạng mục chưa chắc đồng nghĩa với tiến gần đến điều sản phẩm cần đạt được**. Nếu không thấy mối liên hệ giữa việc đang làm và giá trị mong muốn, nhóm rất dễ trở thành “nhà máy tính năng”: phát hành đều nhưng khó trả lời vì sao tính năng đó đáng đầu tư.

Để tránh tình trạng này, những người tham gia phát triển cần kết nối các cấp độ quyết định:

1. **Tầm nhìn sản phẩm (product vision):** Sản phẩm tồn tại để tạo ra thay đổi có ý nghĩa gì, cho ai?
2. **Mục tiêu sản phẩm (Product Goal):** Kết quả quan trọng tiếp theo mà nhóm cần hướng tới là gì?
3. **Chiến lược và Product Backlog:** Những vấn đề, giả thuyết và cơ hội nào được ưu tiên để đạt mục tiêu?
4. **Mục tiêu ngắn hạn và công việc:** Trong Sprint hoặc giai đoạn tiếp theo, nhóm sẽ tạo ra năng lực gì để tiến gần mục tiêu?
5. **Increment và phản hồi:** Phần sản phẩm hoàn thành có đáp ứng chất lượng, tạo cơ hội kiểm chứng và làm rõ bước kế tiếp không?

Bài học thuộc chương **Sản phẩm và giá trị** của mô-đun **AGILE_DEVELOPMENT**. Chúng ta sẽ nối các khái niệm Agile, user story, Product Backlog, Scrum, Kanban và đo lường dòng công việc thành một phương pháp lập kế hoạch có thể **kiểm tra và thích ứng**, thay vì chỉ biến mục tiêu dài hạn thành danh sách việc phải làm.

## 1. Vì sao cần liên kết các tầng mục tiêu?

Xét hai tình huống của một ứng dụng đặt lịch khám:

- **Tình huống A:** Nhóm hoàn thành trong tháng ba màn hình mới, một API và tám user story. Báo cáo ghi “đã hoàn thành 100% công việc”. Nhưng khách vẫn thường gọi điện để hỏi lịch còn trống và không tin rằng lịch đã được xác nhận.
- **Tình huống B:** Nhóm bàn giao ít tính năng hơn, nhưng người thử nghiệm có thể tự tìm khung giờ phù hợp, đặt lịch và nhận xác nhận rõ ràng. Nhóm đo được tỷ lệ hoàn thành tác vụ, các bước gây bỏ dở và lỗi đặt lịch trùng; kết quả giúp họ quyết định đầu tư tiếp vào đâu.

Cả hai nhóm đều tạo **đầu ra (outputs)**. Tình huống B còn tạo cơ sở để đánh giá **kết quả (outcomes)**: người dùng làm được điều họ cần và hành vi có tiến triển theo mục tiêu sản phẩm hay không.

| Khái niệm | Câu hỏi | Ví dụ trong ứng dụng đặt lịch |
| --- | --- | --- |
| **Hoạt động (activity)** | Nhóm đã dành công sức làm gì? | Phân tích luồng đặt lịch, lập trình, kiểm thử |
| **Đầu ra (output)** | Đã tạo hoặc bàn giao thứ gì? | Trang chọn giờ, API giữ chỗ, thông báo xác nhận |
| **Kết quả (outcome)** | Điều gì đã thay đổi ở hành vi hoặc khả năng của người dùng? | Nhiều người tự đặt lịch thành công hơn, ít cần gọi điện |
| **Tác động (impact)** | Kết quả đóng góp ra sao cho mục tiêu lớn của tổ chức hoặc cộng đồng? | Giảm tải công việc điều phối, cải thiện khả năng tiếp cận dịch vụ |

Một outcome tốt thường cần **nhiều output hỗ trợ**; đồng thời, một output có thể không tạo outcome như giả định. Vì vậy, liên kết mục tiêu là **mối quan hệ giả thuyết cần kiểm chứng**, không phải lời cam kết rằng cứ hoàn thành danh sách tính năng thì giá trị chắc chắn xuất hiện.

## 2. Tầm nhìn sản phẩm: hướng đi ổn định giữa các thay đổi

**Tầm nhìn sản phẩm** diễn đạt trạng thái tương lai mà sản phẩm muốn góp phần tạo ra. Nó nên đủ rõ để hướng dẫn những lựa chọn khó, đủ ngắn để thành viên có thể nhắc lại bằng lời của mình và đủ bền vững để không đổi chỉ vì một Sprint gặp khó khăn.

Một tầm nhìn hữu ích thường trả lời:

- **Người hưởng lợi:** Nhóm người dùng hoặc khách hàng chính là ai?
- **Vấn đề:** Khó khăn quan trọng nào đang tồn tại?
- **Thay đổi mong muốn:** Điều gì sẽ dễ hơn, an toàn hơn hoặc có giá trị hơn?
- **Khác biệt và ranh giới:** Sản phẩm lựa chọn phục vụ hoàn cảnh nào, những gì hiện chưa phải trọng tâm?

Ví dụ tầm nhìn giả định:

> Giúp người cần khám bệnh tìm và đặt được lịch phù hợp một cách dễ hiểu, đáng tin cậy, không phải mất nhiều cuộc gọi xác nhận.

Tuyên bố này cho biết **đích đến và người được phục vụ**, nhưng chưa yêu cầu phải dùng ứng dụng di động, chatbot hay một kiến trúc cụ thể. Nhóm vẫn có không gian lựa chọn giải pháp phù hợp với bằng chứng.

### Tầm nhìn không phải danh sách tính năng

| Phát biểu | Nhận xét |
| --- | --- |
| “Xây chatbot AI, đặt lịch bằng giọng nói và thêm năm màn hình” | Là danh sách giải pháp; chưa nêu kết quả cho người dùng |
| “Trở thành ứng dụng đặt lịch số một” | Rất rộng; chưa rõ nhóm người dùng và giá trị khác biệt |
| “Người bệnh tự chọn và xác nhận lịch khám tin cậy trong vài bước” | Chỉ ra đối tượng, khả năng và giá trị mà đội có thể định hướng |

Tầm nhìn cần dựa trên sự hiểu biết về nhu cầu và bối cảnh; không nên được xem như điều bất biến. Khi bằng chứng cho thấy nhóm đang giải quyết sai vấn đề, người chịu trách nhiệm chiến lược có thể xem xét điều chỉnh tầm nhìn. Tuy nhiên, **không nên thay tầm nhìn chỉ để hợp thức hóa mỗi yêu cầu mới**.

## 3. Product Goal: biến tầm nhìn thành mục tiêu cụ thể có thể theo đuổi

Trong **Scrum Guide 2020**, **Product Goal** mô tả trạng thái tương lai của sản phẩm, là mục tiêu dài hạn để Scrum Team lập kế hoạch hướng tới. Product Goal là **cam kết (commitment) gắn với Product Backlog**. Scrum Team phải hoàn thành hoặc từ bỏ một Product Goal trước khi nhận Product Goal tiếp theo. Tầm nhìn sản phẩm có thể giúp định hướng nhưng **không phải một artifact bắt buộc được Scrum Guide quy định**.

Product Goal nên tạo được câu trả lời rõ cho câu hỏi: **“Nếu vài tháng tới chúng ta chỉ tiến bộ đáng kể ở một hướng sản phẩm, đó là hướng nào?”**

Một cách diễn đạt thực dụng:

> Đối với **[nhóm người dùng và bối cảnh]**, sản phẩm cần đạt **[trạng thái hoặc năng lực tạo giá trị]** để **[giải quyết vấn đề]**; nhóm sẽ đánh giá tiến triển qua **[tín hiệu phù hợp]**.

**Ví dụ Product Goal** cho hệ thống đặt lịch:

> Người bệnh tại cơ sở thí điểm có thể tự tìm khung giờ còn chỗ, đặt và nhận xác nhận lịch khám đáng tin cậy mà không phải gọi điện cho nhân viên.

Mục tiêu này đủ cụ thể để giúp lựa chọn ưu tiên. Chẳng hạn, tính năng đổi màu giao diện trang chủ có thể chưa cấp thiết bằng khả năng ngăn đặt trùng hoặc giải thích rõ trạng thái xác nhận.

### Phân biệt trạng thái mục tiêu và chỉ số thành công

Product Goal nói về **trạng thái cần đạt**. Các chỉ số có thể giúp đánh giá tiến triển, nhưng không nên nhầm một con số riêng lẻ với toàn bộ mục đích của sản phẩm.

Ví dụ nhóm có thể đề xuất các mục tiêu đo lường **giả định cho chương trình thí điểm**:

| Tín hiệu | Cách diễn giải mẫu |
| --- | --- |
| Tỷ lệ tự đặt lịch thành công | Số phiên đặt lịch khởi tạo bởi người dùng và có xác nhận hợp lệ / số phiên bắt đầu quy trình đặt lịch theo định nghĩa |
| Thời gian tới xác nhận | Thời gian từ lúc người dùng gửi yêu cầu đến khi thấy trạng thái xác nhận có hiệu lực |
| Số liên hệ hỗ trợ về xác nhận lịch | Số lượt liên hệ thuộc nhóm vấn đề đó trên 100 lượt đặt lịch hợp lệ |
| Chỉ số bảo vệ | Tỷ lệ đặt trùng, lỗi giữ chỗ, sự cố dữ liệu lịch, mức khiếu nại |

Nếu nhóm nói “nâng tỷ lệ tự đặt lịch từ 42% lên 55%”, cả **42% và 55% đều chỉ là con số minh họa** cho bài học: trong thực tế phải đo đường cơ sở, định nghĩa mẫu, thời gian quan sát và đánh giá độ tin cậy trước khi chốt. Tăng tỷ lệ đặt lịch bằng cách che giấu lỗi xác nhận hoặc khiến người dùng đặt trùng là **không đạt mục tiêu giá trị**.

### Một Product Goal, nhiều cách để đến đích

Có thể có nhiều giả thuyết hỗ trợ một Product Goal:

- Người dùng bỏ dở vì khó tìm giờ còn trống.
- Người dùng không hiểu họ đã đặt thành công hay chưa.
- Khách phải đăng ký tài khoản quá sớm nên rời đi.
- Thông tin lịch không đồng bộ gây ra nhiều lần xác nhận thất bại.

Đây là các **khả năng cần kiểm chứng**, không phải danh sách tính năng chắc chắn phải xây. Khi một giả thuyết bị bác bỏ, nhóm thay cách tiếp cận mà vẫn có thể giữ Product Goal.

## 4. Từ tầm nhìn đến Sprint: một chuỗi liên kết có thể kiểm chứng

Quan hệ giữa các cấp độ được hình dung như sau:

~~~mermaid
flowchart TD
    A["Tầm nhìn sản phẩm: vì sao và cho ai?"] --> B["Product Goal: trạng thái giá trị tiếp theo"]
    B --> C["Product Backlog: cơ hội, giả thuyết, hạng mục được sắp thứ tự"]
    C --> D["Sprint Goal hoặc mục tiêu ngắn hạn: bước tiến có ý nghĩa"]
    D --> E["Các backlog item được chọn và kế hoạch thực hiện"]
    E --> F["Increment đáp ứng Definition of Done"]
    F --> G["Phản hồi người dùng, phần mềm, vận hành"]
    G --> H["Kiểm tra tiến triển và điều chỉnh"]
    H --> C
    H -. "Bằng chứng lớn làm thay đổi hướng" .-> B
    H -. "Thay đổi bối cảnh chiến lược" .-> A
~~~

Mỗi mũi tên từ trên xuống là câu hỏi **“Vì sao việc này đáng làm?”**. Mũi tên phản hồi đi lên là câu hỏi **“Điều vừa học có làm thay đổi ưu tiên hoặc mục tiêu không?”**.

| Tầng quyết định | Thời hạn thường gặp | Người phối hợp chính | Câu hỏi kiểm tra |
| --- | --- | --- | --- |
| Tầm nhìn | Dài hạn, xem lại khi bối cảnh quan trọng thay đổi | Người chịu trách nhiệm định hướng sản phẩm và stakeholder | Sản phẩm có đang giải quyết đúng vấn đề cho đúng người? |
| Product Goal | Dài hạn hơn một Sprint; cho đến khi đạt hoặc từ bỏ | Product Owner chịu trách nhiệm tối đa hóa giá trị, cả Scrum Team đóng góp | Chúng ta đang cố đạt trạng thái sản phẩm nào? |
| Product Backlog | Cập nhật liên tục | Product Owner chịu trách nhiệm nội dung và thứ tự; Developers cùng làm rõ | Việc nào có giá trị nhất để xem xét tiếp? |
| Sprint Goal | Trong một Sprint | Toàn Scrum Team cùng tạo mục tiêu trong Sprint Planning | Increment hoặc khả năng nào cần đạt để Sprint có ý nghĩa? |
| Kế hoạch và công việc hằng ngày | Giờ, ngày, tuần | Developers tự quản lý cách thực hiện | Hôm nay cần làm gì để đạt Sprint Goal? |
| Kiểm chứng | Liên tục và khi có dữ liệu phù hợp | Nhóm sản phẩm, người dùng, kỹ thuật, vận hành | Bằng chứng mới có xác nhận hướng đi không? |

Thời hạn trong bảng là **tương đối**, không phải quy tắc cứng. Agile không yêu cầu Product Goal phải được hoàn thành trong một số Sprint cố định hoặc mọi Product Backlog Item phải là user story.

## 5. Product Backlog: cầu nối giữa mục tiêu và lựa chọn đầu tư

**Product Backlog** là một danh sách công việc cần thiết để cải thiện sản phẩm, được sắp xếp thứ tự và liên tục làm rõ. Trong Scrum, Product Owner chịu trách nhiệm quản lý Product Backlog hiệu quả; các stakeholder và Developers đóng góp thông tin để ra quyết định.

Backlog có thể chứa tính năng, lỗi, cải thiện khả dụng, công việc bảo mật, ổn định hệ thống, nghiên cứu và các loại việc khác. Điều quan trọng là **biết vì sao một hạng mục cần được thực hiện**, tác động đến mục tiêu nào và mức độ hiểu biết hiện tại ra sao.

### Viết hạng mục theo vấn đề hoặc kết quả mong muốn

Ví dụ nhóm khám phá vấn đề “người bệnh không biết lịch đã xác nhận chưa”. Có thể diễn đạt:

**User story:**

> Là người bệnh vừa gửi yêu cầu đặt lịch, tôi muốn biết yêu cầu đang xử lý, đã xác nhận hay không thể xác nhận, để không phải gọi điện hoặc gửi yêu cầu đặt trùng.

**Tiêu chí chấp nhận minh họa:**

1. Khi yêu cầu còn chờ xử lý, màn hình hiển thị trạng thái *đang xác nhận* và cách kiểm tra lại.
2. Khi hệ thống nhận xác nhận hợp lệ, hiển thị mã lịch, thời gian và nơi khám.
3. Nếu không giữ được khung giờ, màn hình thông báo rõ và cho phép chọn giờ khác.
4. Không hiển thị *đã xác nhận* khi hệ thống chưa có bằng chứng xác nhận.
5. Trường hợp mạng lỗi hoặc dịch vụ phản hồi chậm được xử lý rõ ràng, tránh khuyến khích gửi yêu cầu trùng.

User story mô tả **người dùng và giá trị**; tiêu chí chấp nhận làm rõ **hành vi kỳ vọng của hạng mục**. Cả hai không thay thế cho **Definition of Done**, vốn là tiêu chuẩn chất lượng chung để một Increment được coi là hoàn thành.

### Ưu tiên theo giá trị và điều chưa biết

Product Owner có thể cân nhắc nhiều yếu tố:

| Góc nhìn | Câu hỏi giúp quyết định thứ tự |
| --- | --- |
| Giá trị người dùng | Việc này giải quyết vấn đề lớn nào? Bao nhiêu người bị ảnh hưởng? |
| Đóng góp cho Product Goal | Việc này có giúp đạt trạng thái sản phẩm mong muốn không? |
| Bất định và học hỏi | Giả định nào quan trọng nhưng còn ít bằng chứng? Có phép kiểm chứng rẻ hơn không? |
| Rủi ro kỹ thuật / vận hành | Nếu trì hoãn, hậu quả chất lượng, an toàn hoặc ổn định là gì? |
| Chi phí và độ phức tạp | Ước lượng nỗ lực, phụ thuộc và chi phí vận hành ra sao? |
| Thời điểm | Có ràng buộc thời gian, chính sách hoặc cơ hội kinh doanh nào không? |

Một hạng mục **có thể được ưu tiên vì giảm rủi ro hoặc tạo điều kiện cho việc có giá trị**, ngay cả khi người dùng không nhìn thấy thay đổi trực tiếp. Ví dụ sửa cơ chế khóa lịch để tránh hai khách cùng được xác nhận một chỗ góp phần vào mục tiêu “đặt lịch đáng tin cậy”. Không nên chỉ giữ backlog gồm các tính năng có giao diện.

### Đừng biến roadmap thành lời hứa về danh sách tính năng

**Product roadmap** có thể diễn đạt các hướng giá trị, mục tiêu, giả thuyết và thời điểm dự kiến xem xét. Nó giúp stakeholder hiểu hướng đầu tư mà không cần coi mọi hạng mục là bất biến.

Ví dụ roadmap theo kết quả:

| Giai đoạn dự kiến | Câu hỏi trọng tâm | Hướng thử nghiệm có thể có |
| --- | --- | --- |
| Đầu tiên | Người bệnh có tìm được giờ phù hợp không? | Hiển thị lịch còn chỗ, thử khả dụng |
| Tiếp theo | Yêu cầu đặt lịch có được xác nhận đáng tin cậy không? | Kiểm tra đồng bộ lịch, trạng thái xác nhận |
| Sau khi đã có bằng chứng | Có thể giảm thao tác và hỗ trợ mà vẫn giữ an toàn không? | Rút gọn luồng, thông báo, tự phục vụ |

Roadmap là công cụ trao đổi định hướng; Product Backlog là nguồn công việc liên tục được làm rõ. Khi dữ liệu mới xuất hiện, nhóm nên cập nhật phương án và thứ tự để vẫn theo đuổi giá trị.

## 6. Sprint Goal: bước tiến ngắn hạn có ý nghĩa

Trong Scrum, **Sprint Goal** là **mục tiêu duy nhất của Sprint** và là **cam kết gắn với Sprint Backlog**. Sprint Goal được tạo trong Sprint Planning, cung cấp tính nhất quán và linh hoạt để Developers điều chỉnh kế hoạch trong quá trình làm việc.

Một Sprint Goal tốt diễn đạt **kết quả chung mà đội muốn tạo ra trong Sprint**. Nó không nên đơn thuần sao chép danh sách backlog item, chỉ tiêu story point hoặc nhiệm vụ của từng cá nhân.

| Cách viết | Vấn đề / giá trị |
| --- | --- |
| “Hoàn thành story #21, #22, #23 và #24” | Chỉ liệt kê việc; khó quyết định khi có thay đổi |
| “Hoàn thành 30 story point” | Đo lượng công việc, không chỉ ra giá trị |
| “Cho phép người bệnh lần đầu chọn khung giờ còn chỗ và nhận xác nhận rõ ràng tại cơ sở thí điểm” | Diễn đạt khả năng mang lại giá trị và giữ nhóm tập trung |
| “Cải thiện trải nghiệm người dùng” | Quá rộng, khó nhận biết đạt hay chưa |

### Sprint Backlog gồm những gì?

Theo Scrum Guide, **Sprint Backlog** gồm **Sprint Goal (vì sao)**, tập hợp các Product Backlog Item được chọn (**cái gì**) và kế hoạch hành động để tạo Increment (**làm thế nào**). Developers có thể điều chỉnh công việc và kế hoạch khi học thêm; khi thay đổi phạm vi, cần thương lượng với Product Owner trong khi **giữ Sprint Goal không bị ảnh hưởng**.

Để đạt Sprint Goal trong ví dụ, nhóm có thể chọn:

| Product Backlog Item được chọn | Tại sao cần cho Sprint Goal? | Ví dụ công việc ngắn hạn |
| --- | --- | --- |
| Người bệnh xem các khung giờ còn chỗ | Có khả năng tự chọn giờ phù hợp | Làm rõ quy tắc lịch trống, triển khai API và màn hình, kiểm thử |
| Xác nhận đặt lịch tránh trùng | Lịch đã đặt phải đáng tin cậy | Kiểm tra cạnh tranh đồng thời, xử lý giữ chỗ và xác nhận |
| Hiển thị trạng thái xác nhận | Người dùng hiểu kết quả yêu cầu | Thiết kế thông điệp, tích hợp trạng thái, kiểm thử luồng |
| Đo các bước hoàn thành đặt lịch | Có dữ liệu phản hồi để quyết định bước sau | Định nghĩa sự kiện, kiểm tra đo lường, xem tín hiệu thí điểm |

Nếu phát hiện một công việc chưa cần thiết để đạt Sprint Goal, Developers có thể đề xuất thay đổi kế hoạch. Nếu rủi ro đặt trùng nghiêm trọng hơn dự kiến, có thể cần tập trung xử lý rủi ro trước, đồng thời trao đổi về ảnh hưởng đến mục tiêu.

**Lưu ý:** Sprint không bắt buộc kết thúc bằng việc phát hành cho toàn bộ người dùng. Nhưng nhóm phải hướng tới Increment **có giá trị, có thể sử dụng và đáp ứng Definition of Done**; nếu muốn kiểm chứng giá trị thực tế, cần kế hoạch đưa thay đổi tới môi trường và người dùng phù hợp.

## 7. Giữ liên kết trong công việc hằng ngày

Liên kết mục tiêu không chỉ diễn ra ở buổi lập kế hoạch. Nó hiện ra trong những quyết định nhỏ: nên giải quyết lỗi nào trước, có nên thêm một điều kiện mới, cần mời ai làm rõ nghiệp vụ, khi nào phần việc đủ hoàn chỉnh để xem sản phẩm.

### Ba câu hỏi trước khi bắt đầu một công việc

1. **Vì sao?** Công việc này giúp Sprint Goal hoặc Product Goal thế nào?
2. **Làm gì?** Dấu hiệu nào chứng minh hành vi mong đợi đã được tạo và đạt mức chất lượng cần thiết?
3. **Học gì?** Sau khi hoàn thành, nhóm có thể xác nhận điều gì bằng kiểm thử, trải nghiệm người dùng hoặc số liệu vận hành?

Ví dụ, “viết API trạng thái lịch” là hoạt động; “người bệnh thấy trạng thái đơn đặt lịch đáng tin cậy” là khả năng mong muốn. API nên được kiểm thử theo hành vi đó, không chỉ vì endpoint phản hồi HTTP 200.

### Duy trì bản ghi liên kết tối giản

Một backlog item không cần tài liệu chiến lược dài, nhưng có thể ghi ngắn:

~~~text
Product Goal:
  Người bệnh tại cơ sở thí điểm tự đặt và nhận xác nhận tin cậy.

Sprint Goal:
  Người bệnh lần đầu chọn được giờ và biết chắc kết quả đặt lịch.

Backlog item:
  Hiển thị rõ trạng thái đang xác nhận / đã xác nhận / thất bại.

Giả định:
  Việc thiếu trạng thái rõ ràng làm người dùng gửi trùng yêu cầu.

Bằng chứng cần thu:
  Người dùng xác định đúng trạng thái; số yêu cầu đặt trùng;
  lỗi và độ trễ cập nhật trạng thái.

Quyết định sau kiểm chứng:
  Tiếp tục mở rộng, cải thiện cách diễn đạt hoặc sửa cơ chế xác nhận.
~~~

Đây là cách thể hiện **truy xuất lý do quyết định**, không nhất thiết là cấu trúc trường bắt buộc của mọi công cụ. Dùng liên kết đến Product Goal hoặc Sprint Goal và tiêu chí chấp nhận khi công cụ quản lý backlog hỗ trợ.

### Daily Scrum và phối hợp hằng ngày

Trong Scrum, **Daily Scrum** là sự kiện 15 phút dành cho Developers để kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh Sprint Backlog khi cần. Câu hỏi cốt lõi không phải “ai hôm qua làm được bao nhiêu giờ?” mà là “điều gì cần thay đổi trong kế hoạch để đạt Sprint Goal?”.

Ngoài Daily Scrum, nhóm nên làm rõ bất định nghiệp vụ, phối hợp kiểm thử và thảo luận rủi ro đúng lúc. Việc hỏi sớm và chia sẻ bằng chứng có thể rút ngắn thời gian chờ hơn một cuộc họp tổng hợp kéo dài.

## 8. Từ Increment đến phản hồi: đo tiến triển của sản phẩm

Trong Scrum, **Increment** là một bước cụ thể tiến tới Product Goal. Increment phải **đáp ứng Definition of Done**; mỗi Increment được tạo trong Sprint có thể được chuyển giao cho stakeholder trước Sprint Review nếu phù hợp. **Definition of Done là cam kết gắn với Increment**.

Ba cam kết trong Scrum có quan hệ:

| Artifact | Commitment | Tập trung |
| --- | --- | --- |
| **Product Backlog** | **Product Goal** | Đích sản phẩm dài hạn |
| **Sprint Backlog** | **Sprint Goal** | Mục đích chung của Sprint |
| **Increment** | **Definition of Done** | Chất lượng và mức hoàn thành minh bạch |

**Sprint Review** giúp Scrum Team và stakeholder kiểm tra kết quả Sprint, thảo luận thay đổi trong môi trường và quyết định cách thích ứng tiếp theo. Đây là cơ hội để học hỏi, **không phải cửa duyệt bắt buộc trước khi Increment có thể phát hành**.

### Kiểm chứng outcome khác nghiệm thu output

Đối với một màn hình đặt lịch:

- **Đúng chức năng:** Kiểm thử cho thấy hệ thống hiển thị lịch trống theo quy tắc đã thống nhất.
- **Đạt Definition of Done:** Các tiêu chuẩn chất lượng và tích hợp cần thiết đã được đáp ứng.
- **Có thể sử dụng:** Người dùng thử có thể hoàn tất tác vụ với mức khó khăn chấp nhận được.
- **Tạo outcome:** Dữ liệu thực tế cho thấy nhiều người tự đặt lịch thành công hơn trong nhóm được quan sát.

Bốn nhận định trên **không suy ra nhau một cách tự động**. Một giao diện được kiểm thử đầy đủ vẫn có thể khiến người bệnh khó hiểu. Một thí điểm có tín hiệu tích cực vẫn cần kiểm tra sự khác biệt về nhóm người dùng, lưu lượng và rủi ro vận hành trước khi mở rộng.

### Đo đúng kết quả thay vì chỉ đo khối lượng

| Chỉ số | Dùng để trả lời | Giới hạn |
| --- | --- | --- |
| Số story hoặc tính năng hoàn thành | Nhóm đã tạo ra những output nào? | Không trực tiếp chứng minh giá trị |
| Velocity / story point | Hỗ trợ ước lượng và dự báo nội bộ khi nhóm áp dụng | Không nên dùng để so sánh hiệu suất các nhóm hoặc thay outcome |
| Lead time / cycle time | Công việc mất bao lâu để đi qua dòng chảy? | Nhanh hơn chưa chắc giải quyết đúng vấn đề |
| Tỷ lệ tự đặt lịch thành công | Người dùng có đạt mục tiêu tự phục vụ không? | Cần mẫu và định nghĩa phép đo nhất quán |
| Lỗi xác nhận, đặt trùng | Chất lượng và sự tin cậy có được bảo đảm? | Cần kiểm tra trường hợp hiếm và mức độ ảnh hưởng |
| Số liên hệ hỗ trợ trên mỗi đơn | Việc cần trợ giúp thay đổi ra sao? | Có thể chịu tác động từ kênh hỗ trợ và cơ chế ghi nhận |

Đo **outcome chính** cùng **chỉ số bảo vệ** giúp tránh tối ưu lệch. Ví dụ, tỷ lệ tự đặt lịch có thể tăng nhờ bỏ bước xác nhận thông tin nhưng đổi lại gia tăng sai sót; đó là một đánh đổi cần được nhìn thấy.

## 9. Ví dụ xuyên suốt qua ba Sprint giả định

Các con số và mốc sau **chỉ phục vụ minh họa cách tư duy**, không phải dữ liệu khảo sát thực tế hay kế hoạch bắt buộc cho Scrum.

### Bối cảnh ban đầu

Một cơ sở khám có website nhưng đa số lịch hẹn vẫn được xác nhận qua điện thoại. Trong một đợt quan sát giả định, nhóm ghi nhận **42%** lượt bắt đầu đặt lịch trực tuyến được tự hoàn tất và xác nhận hợp lệ. Product Goal là đưa người bệnh ở cơ sở thí điểm đến trạng thái có thể tự đặt và nhận xác nhận đáng tin cậy.

Nhóm đặt một **ngưỡng phấn đấu minh họa là 55%** cho giai đoạn học hỏi tiếp theo, đồng thời yêu cầu không gia tăng sự cố đặt trùng. Product Goal vẫn nói về trạng thái giá trị; chỉ số giúp định lượng tiến triển và cần được xem xét lại khi có thêm dữ liệu.

| Sprint | Giả thuyết ưu tiên | Sprint Goal minh họa | Increment / phép kiểm chứng |
| --- | --- | --- | --- |
| **1** | Người dùng chưa biết giờ nào còn chỗ nên bỏ dở | Người bệnh có thể xem và chọn khung giờ còn trống phù hợp | Lát cắt chọn giờ, kiểm thử quy tắc lịch trống, quan sát tác vụ trên bản dùng thử |
| **2** | Người dùng không tin yêu cầu đã được xác nhận | Người bệnh có thể gửi yêu cầu và nhận trạng thái xác nhận chính xác | Xử lý xác nhận, chống đặt trùng, giao diện trạng thái, kiểm thử tình huống lỗi |
| **3** | Một số bước nhập thông tin không cần thiết làm tăng bỏ dở | Người bệnh lần đầu có thể hoàn tất đặt lịch với ít thao tác hơn nhưng vẫn đủ dữ liệu cần thiết | Cải thiện luồng đã đo được, thử nghiệm giới hạn, theo dõi tỷ lệ hoàn thành và lỗi |

Sau Sprint 1, nhóm phát hiện người dùng tìm được giờ nhưng một số giờ thực tế không thể đặt vì dữ liệu đồng bộ trễ. Thay vì lập tức làm tất cả tính năng đã dự tính, Product Owner có thể **ưu tiên độ tin cậy của dữ liệu lịch** trong backlog. Điều này phản ánh kết quả học được và phục vụ Product Goal rõ hơn việc cố giữ nguyên roadmap.

Sau Sprint 2, nếu hệ thống có thể xác nhận đúng và người dùng hiểu trạng thái, nhóm mới có căn cứ kiểm tra giả thuyết của Sprint 3. Nếu vẫn có nhiều lỗi xác nhận, nhóm cần cải thiện trước khi mở rộng lưu lượng.

### Diễn giải số liệu thận trọng

Giả sử tỷ lệ tự đặt thành công tăng từ 42% lên 49% trong một nhóm thí điểm. Đây có thể là **tín hiệu tiến triển**, nhưng chưa mặc nhiên chứng minh các thay đổi gây ra mức tăng 7 điểm phần trăm. Nhóm cần kiểm tra quy mô mẫu, cách ghi nhận, sự thay đổi về nguồn truy cập, ngày trong tuần, loại khám và những thay đổi đồng thời.

Nếu có điều kiện, dùng nhóm đối chứng hoặc một thiết kế đo lường phù hợp để tăng khả năng suy luận tác động. Ngay cả khi không thể kết luận nhân quả chắc chắn, nhóm vẫn có thể **ghi mức độ tin cậy và thiết kế phép kiểm chứng tiếp theo**.

### Nhìn lại trục liên kết sau các Sprint

~~~text
TẦM NHÌN
  Đặt lịch khám dễ hiểu, tin cậy, ít phụ thuộc điện thoại
        ↓
PRODUCT GOAL
  Người bệnh tại cơ sở thí điểm tự đặt và được xác nhận đáng tin cậy
        ↓
VẤN ĐỀ ƯU TIÊN TRONG BACKLOG
  Không biết giờ trống → thiếu xác nhận → quá nhiều thao tác
        ↓
SPRINT GOAL
  Mỗi Sprint tạo một bước tiến sản phẩm có thể kiểm chứng
        ↓
BACKLOG ITEMS + KẾ HOẠCH
  Quy tắc nghiệp vụ, giao diện, xử lý đồng thời, kiểm thử, đo lường
        ↓
INCREMENT + BẰNG CHỨNG
  Phần dùng được, đạt DoD, được người dùng và hệ thống kiểm chứng
        ↺
  Điều chỉnh Product Backlog và kế hoạch ngắn hạn
~~~

Mục tiêu cuối không phải “hoàn thành ba Sprint” mà là **giảm bất định về cách sản phẩm tạo giá trị** và có Increment tốt hơn sau mỗi vòng.

## 10. Kết nối mục tiêu khi nhóm dùng Kanban hoặc không tổ chức Sprint

Không phải mọi nhóm Agile đều vận hành bằng Scrum. Một nhóm hỗ trợ sản phẩm có yêu cầu liên tục có thể dùng **Kanban**, không áp dụng Sprint Goal theo khuôn mẫu Scrum. Dù vậy, nhóm vẫn cần một **đích sản phẩm hoặc mục tiêu dịch vụ** để biết việc nào nên xử lý trước.

Ví dụ, nhóm có thể thống nhất **mục tiêu ngắn hạn trong bốn tuần**: giảm các trường hợp người bệnh phải gọi điện vì lịch chưa được xác nhận. Họ quản lý công việc theo luồng:

~~~text
Ý tưởng / Vấn đề → Cần làm rõ → Sẵn sàng → Đang làm → Kiểm thử → Bàn giao → Quan sát
                                          ↑             |
                                          └── Xử lý blocked / phản hồi ──┘
~~~

Trong Kanban, việc **trực quan hóa luồng**, **giới hạn WIP** và **thống nhất chính sách xử lý** giúp phát hiện chờ đợi. Ví dụ, nếu nhiều hạng mục mắc ở “Cần làm rõ” do thiếu người quyết định nghiệp vụ, giảm thời gian chờ có thể đưa giá trị đến người dùng sớm hơn việc yêu cầu lập trình nhanh hơn.

Các câu hỏi định hướng không thay đổi:

1. Hạng mục này phục vụ mục tiêu sản phẩm hoặc mục tiêu dịch vụ nào?
2. Có thể bàn giao từng phần để nhận phản hồi sớm không?
3. Dữ liệu dòng công việc và dữ liệu kết quả nói gì?
4. Mục nào nên được kéo vào làm tiếp, dựa trên giá trị, rủi ro và năng lực hiện có?

Không nên gọi mọi mục tiêu ngắn hạn là “Sprint Goal” nếu nhóm không tổ chức Sprint theo Scrum. Tên gọi rõ ràng giúp tránh hiểu nhầm giữa các phương pháp.

## 11. Quản lý thay đổi mà không đánh mất hướng đi

Agile chấp nhận rằng hiểu biết có thể thay đổi sau mỗi vòng phản hồi. **Giữ định hướng không có nghĩa là giữ nguyên giải pháp**.

### Khi backlog item thay đổi

Nếu một phép thử cho thấy người bệnh không gặp khó ở chỗ nhập thông tin, nhóm có thể bỏ ý định xây lại form đăng ký và chuyển sang cải thiện cơ chế xác nhận lịch. Product Goal không cần đổi vì vấn đề giá trị vẫn là khả năng tự đặt lịch đáng tin cậy.

### Khi Sprint phát sinh công việc khẩn cấp

Giả sử phát hiện lỗi đặt trùng lịch nghiêm trọng. Nhóm phải đánh giá và xử lý phù hợp mức độ rủi ro; trong Scrum, Developers làm việc với Product Owner để thương lượng phạm vi Sprint Backlog, bảo vệ Sprint Goal khi còn khả thi. Nếu Sprint Goal đã trở nên lỗi thời, **chỉ Product Owner có quyền hủy Sprint**.

Không nên giả vờ một vấn đề an toàn hoặc bảo mật không quan trọng chỉ vì “không nằm trong mục tiêu Sprint”. Những rủi ro này có thể trực tiếp làm mất khả năng tạo giá trị của sản phẩm.

### Khi Product Goal không còn phù hợp

Nếu bằng chứng cho thấy nhóm người bệnh mục tiêu hầu như không sử dụng đặt lịch trực tuyến vì rào cản khác nằm ngoài giải pháp, hoặc chiến lược của cơ sở khám thay đổi căn bản, nhóm cần đánh giá **tiếp tục, điều chỉnh hay từ bỏ Product Goal**. Quyết định này cần thảo luận minh bạch với người chịu trách nhiệm sản phẩm và stakeholder, thay vì lặng lẽ đổi danh sách hạng mục.

### Khi có nhiều đội cùng phát triển một sản phẩm

Cần tránh tình trạng mỗi đội tối ưu KPI riêng nhưng làm tổn hại outcome chung. Một Product Goal chung và mục tiêu kết quả minh bạch giúp các đội thống nhất ưu tiên, điều phối phụ thuộc và giữ chất lượng tích hợp. Đối với nhiều Scrum Team làm cùng một sản phẩm, Scrum Guide nêu rằng họ cần chia sẻ **Product Goal, Product Backlog và Product Owner**.

## 12. Những phản mẫu làm đứt mạch giá trị

| Phản mẫu | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| “Tầm nhìn” chỉ là khẩu hiệu truyền thông | Nhóm không biết dùng nó để đưa ra lựa chọn nào | Nêu rõ người dùng, vấn đề và thay đổi mong muốn |
| Product Goal là danh sách tính năng | Khó điều chỉnh cách làm khi có bằng chứng mới | Diễn đạt trạng thái sản phẩm / giá trị cần đạt |
| Tất cả backlog item đều là “ưu tiên cao nhất” | Nhóm đa nhiệm, nhiều việc dở, thời gian nhận phản hồi dài | Sắp thứ tự rõ và giới hạn công việc đang làm |
| Sprint Goal là tổng các ticket | Khi một ticket thay đổi, nhóm mất mục tiêu chung | Viết Sprint Goal theo khả năng hoặc kết quả có ý nghĩa |
| Báo cáo story point như giá trị tạo ra | Tạo động cơ làm nhiều việc thay vì giải quyết vấn đề | Theo dõi outcome và các chỉ số chất lượng |
| Chỉ chấp nhận tính năng khi đã xong toàn bộ dự án | Sai giả định được phát hiện muộn | Bàn giao lát cắt dùng được, kiểm chứng sớm |
| Đổi mục tiêu sau từng phản hồi nhỏ | Nhóm thiếu định hướng và khó học có hệ thống | Xem chất lượng bằng chứng, giữ ổn định mục tiêu đủ để kiểm chứng |
| Bỏ qua nợ kỹ thuật, lỗi dữ liệu, bảo mật | Outcome có vẻ tốt ngắn hạn nhưng sản phẩm thiếu tin cậy | Xem giảm rủi ro là đóng góp vào giá trị và khả năng bàn giao |
| Định hướng tốt nhưng người thực hiện không hiểu “vì sao” | Công việc bị chia nhỏ theo phòng ban và dễ lệch mục tiêu | Liên kết Product Goal, Sprint Goal, backlog item và bằng chứng ở mức vừa đủ |
| Review chỉ là màn hình đã hoàn thành | Không học điều mới, backlog không thay đổi | Xem Increment với stakeholder, hỏi về kết quả và quyết định tiếp theo |

## 13. Thực hành: tự nối một Product Goal với công việc hai tuần

**Tình huống:** Một nền tảng học trực tuyến có nhiều học viên đăng ký khóa học nhưng không hoàn thành bài đầu tiên. Nhóm muốn tăng khả năng người học bắt đầu học thật sự trong tuần đầu.

### Bước 1 — Tạo chuỗi mục tiêu

Viết vào mẫu:

~~~text
Tầm nhìn:
  [Đối tượng nào được giúp đỡ, theo cách nào, để tạo giá trị gì?]

Product Goal:
  [Trạng thái sản phẩm quan trọng tiếp theo cần đạt]

Chỉ số kết quả:
  [Định nghĩa hành vi, mẫu đo, khoảng quan sát]

Chỉ số bảo vệ:
  [Chất lượng, an toàn, sự hài lòng hoặc rủi ro không được tăng]

Giả thuyết ưu tiên:
  [Điều gì được cho là đang ngăn người dùng đạt kết quả?]

Sprint Goal / mục tiêu ngắn hạn:
  [Bước tiến có ý nghĩa có thể kiểm chứng trong giai đoạn kế tiếp]

Backlog items:
  [Những lát cắt có thể sử dụng hoặc phép thử nhỏ]

Bằng chứng và quyết định:
  [Quan sát điều gì? Khi nào? Ai quyết định bước tiếp theo?]
~~~

### Bước 2 — Tham khảo một phương án giải

| Thành phần | Phương án minh họa |
| --- | --- |
| Tầm nhìn | Người mới học có thể bắt đầu hành trình học tập phù hợp mà không bị choáng ngợp |
| Product Goal | Học viên mới đã đăng ký có thể dễ dàng bắt đầu và hoàn tất bài học đầu tiên |
| Outcome chính | Tỷ lệ học viên mới hoàn tất bài đầu tiên trong 7 ngày sau đăng ký |
| Chỉ số bảo vệ | Tỷ lệ lỗi tải nội dung, phản hồi rằng bài học không phù hợp, sự cố lưu tiến độ |
| Giả thuyết | Học viên không rõ nên bắt đầu ở đâu sau khi đăng ký |
| Sprint Goal minh họa | Người học mới có thể truy cập một bài đầu tiên phù hợp và thấy tiến độ sau khi hoàn tất |
| Backlog items | Gợi ý bài khởi đầu, luồng vào bài, lưu trạng thái đã học, kiểm thử trạng thái, đo sự kiện hoàn tất |
| Kiểm chứng | Thử khả dụng, kiểm thử lỗi lưu tiến độ, quan sát tỷ lệ bắt đầu và hoàn tất theo nhóm người học |

Ở vòng tiếp theo, nếu dữ liệu cho thấy học viên tìm được bài nhưng bỏ dở vì thời lượng quá dài, nhóm có thể ưu tiên chia bài hoặc điều chỉnh nội dung thay vì tiếp tục làm giao diện gợi ý. **Đổi giải pháp theo bằng chứng vẫn giữ được Product Goal**.

### Bước 3 — Kiểm tra khả năng truy ngược

Hãy tự trả lời:

1. Một hạng mục “thay toàn bộ biểu tượng trên dashboard” có giúp Product Goal không? Cần bằng chứng gì trước khi ưu tiên?
2. Nếu tỷ lệ bắt đầu bài tăng nhưng tỷ lệ hoàn tất không tăng, nên xem lại giả thuyết nào?
3. Nếu kiểm thử cho thấy việc lưu tiến độ thường thất bại, có nên ưu tiên sửa trước khi phát hành thêm tính năng không?
4. Sprint Goal có còn đúng nếu nhóm thay đổi chi tiết cách gợi ý bài học giữa Sprint?
5. Nếu sau nhiều vòng kiểm chứng, Product Goal có vẻ không phù hợp với nhu cầu thực, ai nên tham gia quyết định thay đổi?

### Danh sách kiểm tra cho một buổi lập kế hoạch

- [ ] Người tham gia diễn đạt được **tầm nhìn và người dùng mục tiêu** bằng ngôn ngữ cụ thể.
- [ ] Product Goal mô tả **trạng thái giá trị** thay vì chỉ liệt kê tính năng.
- [ ] Backlog được **sắp thứ tự** theo giá trị, rủi ro, bất định và khả năng triển khai.
- [ ] Mục tiêu ngắn hạn thể hiện **một bước tiến có ý nghĩa** hướng đến Product Goal.
- [ ] Hạng mục được chọn có đủ thông tin và **tiêu chí chấp nhận phù hợp** để bắt đầu.
- [ ] Nhóm thống nhất **Definition of Done** và cách bảo đảm chất lượng.
- [ ] Có kế hoạch **lấy phản hồi và đo outcome** sau phần bàn giao.
- [ ] Kết quả học được sẽ có **người chịu trách nhiệm đưa trở lại backlog**.

## 14. Câu hỏi ôn tập và gợi mở thảo luận

1. Vì sao hoàn thành toàn bộ kế hoạch tính năng vẫn có thể không đạt mục tiêu sản phẩm?
2. Điểm khác biệt giữa tầm nhìn sản phẩm, Product Goal và Sprint Goal là gì?
3. Theo Scrum, Product Goal gắn với artifact nào? Sprint Goal gắn với artifact nào? Definition of Done gắn với artifact nào?
4. Khi nào một việc kỹ thuật không hiển thị cho người dùng vẫn nên được ưu tiên để tạo giá trị?
5. Vì sao “hoàn thành 30 story point” không phải là Sprint Goal tốt?
6. Nếu một phép thử bác bỏ giả thuyết đang đứng đầu Product Backlog, nhóm nên giữ điều gì và thay đổi điều gì?
7. Một Increment đáp ứng Definition of Done đã đủ chứng minh Product Goal đạt được chưa?
8. Khi cần đưa thêm lỗi khẩn cấp vào Sprint, Scrum Team nên làm rõ đánh đổi và trách nhiệm như thế nào?
9. Nhóm Kanban không dùng Sprint Goal có thể giữ mối liên kết giữa công việc hằng ngày với mục tiêu giá trị bằng cách nào?
10. Những chỉ số nào giúp phân biệt “bàn giao đều” với “người dùng thực sự được lợi”?

**Ghi nhớ:** **Tầm nhìn** xác định *vì sao sản phẩm tồn tại và cho ai*; **Product Goal** xác định *trạng thái giá trị tiếp theo cần hướng tới*; **Product Backlog** giúp lựa chọn *điều đáng làm tiếp*; **Sprint Goal hoặc mục tiêu ngắn hạn** giữ nhóm tập trung vào *bước tiến có ý nghĩa*; **Increment và phản hồi** cho biết *những giả định nào được kiểm chứng và cần thích ứng ra sao*. Liên kết này giúp Agile vừa có hướng đi dài hạn, vừa đủ linh hoạt để học và điều chỉnh sau mỗi phần sản phẩm được bàn giao.
