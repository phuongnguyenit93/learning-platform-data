# Phân biệt hoạt động, đầu ra, kết quả và tác động

## 1. Làm rất nhiều việc có đồng nghĩa tạo nhiều giá trị?

Một nhóm phát triển nền tảng học trực tuyến báo cáo sau một tháng:

- Đã tổ chức 18 cuộc trao đổi với các bên liên quan.
- Đã hoàn tất 34 task và 12 user story.
- Đã triển khai 9 lần lên production.
- Đã phát hành tính năng **“Tiếp tục học”**, hiển thị bài học gần nhất và nút mở lại.
- Nhưng số học viên thực sự quay lại học sau khi gián đoạn gần như không thay đổi.

Nhóm đã làm việc và bàn giao sản phẩm. Tuy nhiên, báo cáo trên **chưa chứng minh** rằng họ đã cải thiện thói quen học hoặc giúp người học tiến bộ. Nếu mục tiêu ban đầu là giúp học viên duy trì việc học, thì điều cần kiểm tra không chỉ là **có bao nhiêu việc được thực hiện**, mà còn là **hành vi nào đã thay đổi và sự thay đổi ấy có tạo ra lợi ích bền vững hay không**.

Đây là vấn đề cốt lõi của **đo lường Agile**. Khi Agile nhấn mạnh phản hồi sớm, bàn giao tăng dần và cải tiến liên tục, nhóm cần những tín hiệu cho biết **công việc có đang dẫn đến giá trị thực**. Chỉ theo dõi số cuộc họp, điểm story hoặc số lần triển khai dễ tạo cảm giác tiến bộ nhưng bỏ qua mục tiêu sản phẩm.

Một cách hữu ích là phân biệt bốn tầng:

1. **Hoạt động (activity):** nhóm thực hiện những việc gì?
2. **Đầu ra (output):** nhóm tạo và bàn giao những gì?
3. **Kết quả (outcome):** điều gì thay đổi đối với người dùng, khách hàng hoặc tổ chức nhờ giải pháp?
4. **Tác động (impact):** lợi ích hoặc chuyển biến rộng hơn, dài hạn hơn mà những kết quả đó góp phần tạo ra là gì?

Bốn tầng có liên hệ nhưng **không tự động kéo theo nhau**. Một hoạt động có thể không tạo ra đầu ra hữu ích; một tính năng được phát hành có thể không đổi hành vi; một kết quả ngắn hạn có thể không mang lại tác động mong muốn trong dài hạn.

Bài học thuộc chương **Đo lường Agile** của module **AGILE_DEVELOPMENT**, gắn với giá trị và nguyên tắc Agile, user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc. Mục tiêu là biết **chọn đúng câu hỏi đo lường** thay vì tối ưu một con số tách rời giá trị sản phẩm.

### Kết quả học tập

Sau bài này, người học có thể:

- Phân loại và giải thích rõ **activity, output, outcome, impact** trong phát triển phần mềm.
- Phân biệt các chỉ số hoạt động và dòng công việc với bằng chứng về giá trị người dùng.
- Xây dựng **chuỗi giả thuyết giá trị (logic model / theory of change)** từ công việc kỹ thuật đến mục tiêu dài hạn.
- Định nghĩa các phép đo outcome bằng **tử số, mẫu số, nhóm người dùng, thời gian, nguồn dữ liệu và điều kiện loại trừ**.
- Sử dụng baseline, cohort, chỉ số bảo vệ (**guardrails**) và thử nghiệm để diễn giải thay đổi có trách nhiệm.
- Nhận diện rủi ro của metric gaming, Goodhart's law, nhầm tương quan với nhân quả và mục tiêu chỉ có vẻ đẹp trên dashboard.
- Đưa đo lường vào Product Backlog, Sprint Review, Kanban và vòng phản hồi sản phẩm mà không biến số liệu thành công cụ xếp hạng con người.

## 2. Bốn tầng đo lường: định nghĩa và câu hỏi trọng tâm

| Tầng | Ý nghĩa | Câu hỏi điển hình | Ví dụ trên nền tảng học |
|---|---|---|---|
| **Hoạt động — Activity** | Công việc và hành động được thực hiện để tiến về mục tiêu. | Chúng ta đã làm gì, dùng năng lực ra sao? | Phỏng vấn học viên, refinement, thiết kế luồng, viết mã, kiểm thử, triển khai. |
| **Đầu ra — Output** | Sản phẩm bàn giao, khả năng hoặc hiện vật được tạo ra từ hoạt động. | Cụ thể đã tạo ra hoặc đưa đến người nhận cái gì? | Tính năng “Tiếp tục học” đã tích hợp và phát hành; API lưu tiến độ; hướng dẫn mới. |
| **Kết quả — Outcome** | Thay đổi có ý nghĩa về hành vi, khả năng, trải nghiệm hoặc trạng thái của đối tượng mục tiêu. | Sau khi dùng giải pháp, điều gì thực sự khác đi? | Tỷ lệ học viên quay lại bài đang học tăng; thời gian tìm bài cũ giảm. |
| **Tác động — Impact** | Chuyển biến lớn hơn, thường dài hạn và liên quan mục tiêu chiến lược hoặc xã hội/kinh doanh. | Thay đổi đó góp phần tạo lợi ích bền vững nào? | Người học hoàn thành lộ trình có chất lượng hơn, cải thiện năng lực, tăng khả năng tiếp cận học tập bền vững. |

Đây là một **khung phân tích hữu ích**, không phải hệ phân loại duy nhất được tất cả tổ chức sử dụng với cùng thuật ngữ. Một số mô hình logic bổ sung tầng **input (nguồn lực)**, một số gọi kết quả gần là **short-term outcome** và kết quả xa là **long-term outcome/impact**. Khi sử dụng, nhóm nên **định nghĩa thuật ngữ rõ trong bối cảnh của mình**.

### 2.1. Input khác Activity

Nếu cần đầy đủ chuỗi nhân quả, có thể thêm:

- **Input — nguồn lực:** thời gian, ngân sách, con người, công cụ, hạ tầng, dữ liệu.
- **Activity — hoạt động:** các việc sử dụng nguồn lực đó để khám phá, xây, kiểm thử và phối hợp.

Ví dụ, “nhóm có 5 kỹ sư và một môi trường thử” là nguồn lực. “Chạy kiểm thử tích hợp cho luồng tiếp tục học” là hoạt động. Hai điều đó không phải đầu ra hoặc kết quả với người học.

### 2.2. Output chưa chắc đã được sử dụng

“Tính năng đã release” là bằng chứng quan trọng về **khả năng đã được cung cấp**, nhưng không đồng nghĩa người dùng biết đến, tiếp cận hoặc sử dụng nó.

Một nhóm có thể giao đúng 10 tính năng trong kế hoạch nhưng chỉ 2 tính năng mang lại hành vi mong muốn. Đó không nhất thiết là bằng chứng mọi hoạt động khác vô ích: các hạng mục khám phá hoặc hạ tầng có thể giảm rủi ro. Tuy nhiên, nhóm cần **phân biệt đầu ra có chủ đích với giá trị đã được chứng minh**.

### 2.3. Outcome không nhất thiết là doanh thu

Outcome có thể là:

- Người học tìm được nội dung mong muốn dễ hơn.
- Người dùng hoàn tất một tác vụ với ít bước và ít lỗi hơn.
- Đội hỗ trợ giảm thời gian xử lý yêu cầu nhờ dữ liệu chính xác.
- Khách hàng duy trì sử dụng vì dịch vụ đáng tin hơn.
- Một nhóm người dùng trước đây gặp rào cản nay có thể dùng sản phẩm.
- Nhân viên vận hành phục hồi sự cố nhanh và an toàn hơn.

Điểm chung là **trạng thái hoặc hành vi thực tế thay đổi**, không chỉ xuất hiện một artifact mới.

### 2.4. Impact thường rộng và khó quy về một tính năng

“Nâng cao năng lực lập trình của người học” là mục tiêu dài hạn. Tỷ lệ quay lại học có thể đóng góp, nhưng còn nhiều yếu tố: chất lượng nội dung, thời gian rảnh, động lực, hỗ trợ giảng viên, năng lực đầu vào và điều kiện thiết bị.

Vì vậy, khi đánh giá impact, nhóm nên nói **“góp phần vào”** thay vì mặc định **“tính năng X gây ra toàn bộ tác động Y”**.

## 3. Chuỗi nhân quả: công việc là giả thuyết, không phải bảo chứng

Một **logic model** nối các tầng để biểu diễn giả thuyết tại sao những việc đang làm có thể dẫn đến giá trị:

~~~mermaid
flowchart LR
    A["Input: người, thời gian, dữ liệu"] --> B["Activity: nghiên cứu, xây, kiểm thử"]
    B --> C["Output: khả năng được bàn giao"]
    C --> D["Outcome: hành vi/trải nghiệm thay đổi"]
    D --> E["Impact: lợi ích dài hạn"]
    F["Giả định: người dùng biết và dùng tính năng"] -.-> D
    G["Điều kiện ngoài: nội dung, thiết bị, thời gian học"] -.-> E
    D --> H["Phản hồi, điều chỉnh Product Backlog"]
    H --> B
~~~

Những mũi tên là **giả thuyết cần kiểm tra**, không phải quan hệ nhân quả chắc chắn.

Ví dụ:

> Nếu chúng ta bổ sung nút “Tiếp tục học” dễ tìm (output), học viên sẽ bớt mất công tìm bài đang học và quay lại buổi học thường xuyên hơn (outcome), qua đó góp phần tăng tiến độ và chất lượng hoàn thành lộ trình trong dài hạn (impact).

Giả thuyết này chỉ đúng nếu nhiều điều kiện cùng được đáp ứng:

1. Học viên thực sự gặp trở ngại khi tìm lại bài.
2. Nút mới được nhìn thấy và hiểu đúng.
3. Tiến độ được lưu chính xác, không đưa tới bài sai.
4. Tính năng đủ nhanh, có khả năng truy cập và an toàn.
5. Việc quay lại bài đóng góp vào khả năng học tiếp, không chỉ tạo thêm lượt click.
6. Những yếu tố khác không triệt tiêu lợi ích, chẳng hạn nội dung kém phù hợp.

### 3.1. Thất bại ở một mũi tên cần quyết định khác nhau

| Điểm thất bại | Dấu hiệu | Câu hỏi nên hỏi |
|---|---|---|
| **Activity → Output** | Nhiều cuộc họp/PR nhưng tính năng không dùng được. | Nút thắt ở hiểu yêu cầu, WIP, tích hợp, chất lượng hay phụ thuộc? |
| **Output → Outcome** | Đã release nhưng ít người thấy/dùng, hành vi không đổi. | Người dùng có đúng vấn đề đó không? Giải pháp có dễ tìm và dễ hiểu? |
| **Outcome → Impact** | Lượt quay lại tăng nhưng năng lực học hoặc giữ chân không cải thiện. | Outcome đang đo có đúng là đòn bẩy cho mục tiêu dài hạn? |
| **Đo lường → Kết luận** | Dashboard tăng nhưng dữ liệu không đáng tin. | Có lỗi instrument, đổi mẫu số, thay đổi định nghĩa, seasonality hoặc selection bias? |

Tư duy này giúp đội **chọn thí nghiệm tiếp theo** thay vì phản ứng tự động bằng cách bổ sung thêm nhiều ticket tính năng.

## 4. Cách nhận diện một chỉ số thuộc tầng nào

Đừng phân loại chỉ dựa trên tên chỉ số. Hãy hỏi **đối tượng, hiện tượng và quyết định** mà chỉ số thể hiện.

### 4.1. Bốn câu hỏi kiểm tra nhanh

1. **Hoạt động:** “Con số này cho biết chúng ta đã thực hiện bao nhiêu việc hay dành bao nhiêu nỗ lực?”
2. **Đầu ra:** “Con số này đếm những thứ hoặc khả năng cụ thể đã được tạo, bàn giao hay cung cấp?”
3. **Kết quả:** “Con số này cho thấy ai đó đang làm được điều gì khác trước hoặc nhận lợi ích trực tiếp nào?”
4. **Tác động:** “Con số này phản ánh lợi ích rộng hơn, bền vững hơn đối với mục tiêu chiến lược hoặc cộng đồng?”

Ví dụ “số bài học đã viết” là output; “người học hiểu được kiến thức và áp dụng đúng” là outcome; “năng lực nghề nghiệp được cải thiện bền vững” có thể là impact.

### 4.2. Cùng một phép đo có thể đổi vai trò theo mục tiêu

**Số lượt sử dụng tính năng** thường là một tín hiệu adoption, đôi khi được dùng làm **outcome gần** nếu mục tiêu là thúc đẩy người dùng thực hiện một hành vi cụ thể. Nhưng nếu mục tiêu thật là giúp học viên hoàn thành bài nhanh hơn, lượt click chỉ là **proxy (chỉ số đại diện)** và có thể tăng vì giao diện rối.

**Thời gian xử lý yêu cầu của đội hỗ trợ** có thể là outcome của một cải tiến công cụ nội bộ, nhưng chỉ là một chỉ số vận hành đối với mục tiêu rộng hơn như trải nghiệm khách hàng.

Vì vậy, khi phân loại, cần nêu **mục tiêu và ranh giới hệ thống**, không cố đưa mọi metric vào đúng một ô bất biến.

## 5. Ví dụ xuyên suốt: tính năng “Tiếp tục học”

### 5.1. Vấn đề sản phẩm

Một nền tảng học nhận phản hồi rằng học viên hay bỏ dở lộ trình vì sau vài ngày họ không nhớ bài đang học. Nhóm muốn giảm ma sát khi quay lại, nhưng chưa chắc đây là nguyên nhân chính gây bỏ học.

**Product Goal minh họa:**

> Giúp người học duy trì tiến độ theo lộ trình phù hợp, thông qua việc quay lại nội dung dang dở dễ dàng và đáng tin cậy.

Một giả thuyết:

> Nếu hệ thống hiển thị đúng bài gần nhất và cho phép tiếp tục trong một thao tác rõ ràng, tỷ lệ học viên quay lại học trong tuần sau khi gián đoạn sẽ tăng.

### 5.2. Bảng phân biệt bốn tầng

| Tầng | Ví dụ | Đơn vị đo minh họa |
|---|---|---|
| **Input** | Hai kỹ sư, một nhà thiết kế, dữ liệu tiến độ hợp lệ, môi trường thử. | Năng lực và nguồn lực khả dụng, không phải điểm thành công. |
| **Activity** | Phỏng vấn 12 học viên, thử nguyên mẫu, viết API, kiểm thử truy cập, chạy CI. | Số cuộc phỏng vấn, số hoạt động nghiên cứu/kiểm tra. |
| **Output** | Thành phần “Tiếp tục học” đã đạt DoD, được mở cho nhóm thử. | Tính năng sẵn sàng, % người được cung cấp khả năng. |
| **Outcome gần** | Người học tìm được bài cũ nhanh hơn, ít phải tìm lại nội dung. | Trung vị thời gian tới bài cũ, tỷ lệ hoàn thành tác vụ. |
| **Outcome sản phẩm** | Nhiều học viên đủ điều kiện thực sự quay lại học trong 7 ngày. | Tỷ lệ quay lại học có ý nghĩa theo cohort. |
| **Impact** | Người học duy trì quá trình học, tăng mức hoàn thành/chất lượng học và giá trị lâu dài. | Thay đổi kết quả học tập, duy trì bền vững, chỉ số chiến lược phù hợp. |

Ví dụ này tách **outcome gần và outcome xa hơn** để làm rõ rằng ngay trong tầng kết quả có nhiều mức. Impact thường là đích dài hạn, không phải thứ có thể tuyên bố sau một tuần phát hành.

### 5.3. Điều gì chưa được chứng minh?

Dù tính năng đã xuất hiện và tỷ lệ click cao:

- Click có thể tăng vì nút nằm nổi bật hơn, nhưng học viên vẫn thoát ngay.
- Học viên có thể quay lại vì đang có kỳ thi hoặc thông báo mới, không chỉ nhờ tính năng.
- Những người đã có động lực cao có thể là nhóm duy nhất sử dụng nút.
- Số phiên tăng nhưng thời lượng học có ý nghĩa hoặc kết quả bài kiểm tra không tăng.
- Người dùng dùng bàn phím hoặc thiết bị cũ có thể không truy cập được tính năng.

**Output hoàn thành là một bước quan trọng, nhưng chưa phải bằng chứng đủ cho outcome hoặc impact.**

## 6. Cách viết mục tiêu theo outcome thay vì danh sách việc làm

So sánh hai cách diễn đạt:

**Cách A — tập trung hoạt động/đầu ra:**

> Trong tháng này tổ chức 10 buổi phỏng vấn, hoàn tất 15 story và phát hành nút “Tiếp tục học”.

**Cách B — tập trung kết quả:**

> Trong hai nhóm học viên đủ điều kiện, tăng tỷ lệ quay lại một bài đang học trong vòng 7 ngày từ baseline đã xác nhận lên mức mục tiêu, đồng thời không làm tăng lỗi khôi phục tiến độ hoặc rào cản khả năng truy cập.

Cách B gần với giá trị hơn, nhưng cần được **lượng hóa từ dữ liệu đáng tin và được điều chỉnh phù hợp với thực tế**. Không nên tự đặt một mục tiêu cao tùy ý rồi ép nhóm “đạt bằng mọi cách”.

### 6.1. Outcome tốt cần có ba lớp thông tin

1. **Ai?** Nhóm người dùng hoặc đối tượng nào?
2. **Thay đổi gì?** Hành vi, trải nghiệm hay trạng thái nào cần cải thiện?
3. **Trong điều kiện nào?** Khoảng thời gian, baseline, mức mục tiêu và ràng buộc chất lượng.

Ví dụ:

> Với học viên đang có một khóa học dang dở và có quyền tiếp cận khóa đó, tăng tỷ lệ hoàn thành ít nhất một hoạt động học có ý nghĩa trong bảy ngày sau khi quay lại, so với cohort baseline phù hợp, mà không tăng lỗi mất tiến độ.

Ở đây **hoạt động học có ý nghĩa** phải được định nghĩa, chẳng hạn học viên hoàn thành một đơn vị nội dung hoặc một bài luyện tập có xác minh. Nếu chỉ đếm việc mở trang, hành vi có thể chưa phản ánh học tập.

### 6.2. Tách giả thuyết giải pháp khỏi mục tiêu

Mục tiêu: *giúp học viên quay lại học có ý nghĩa*.

Giả thuyết giải pháp A: nút “Tiếp tục học”.

Giả thuyết giải pháp B: email nhắc học tùy chọn, đúng thời điểm.

Giả thuyết giải pháp C: sửa lỗi khôi phục tiến độ.

Nếu dữ liệu cho thấy B hoặc C giải quyết vấn đề tốt hơn A, đội có thể đổi Product Backlog mà không đánh mất **mục tiêu outcome**. Đây là khác biệt quan trọng giữa **cam kết vào vấn đề và kết quả** với **cứng nhắc cam kết vào một tính năng đã chọn từ trước**.

## 7. Chỉ số Agile thường gặp nằm ở tầng nào?

Scrum, Kanban, XP và DevOps cung cấp nhiều phép đo hữu ích cho **khả năng giao việc, chất lượng và độ tin cậy**. Phần lớn chúng **không tự động là outcome người dùng**.

| Chỉ số | Thường mô tả | Dùng để hỏi | Không chứng minh |
|---|---|---|---|
| **Số cuộc họp/phỏng vấn** | Hoạt động khám phá hoặc phối hợp. | Đã thực hiện những hoạt động học hỏi nào? | Hiểu đúng vấn đề hoặc có tác động. |
| **Số commit/PR** | Dấu vết hoạt động phát triển. | Dòng thay đổi mã và nhu cầu rà soát ra sao? | Năng suất hoặc chất lượng của con người. |
| **Số PBI/story Done** | Đầu ra công việc đạt điều kiện hoàn thành. | Có bao nhiêu hạng mục đã hoàn tất theo chính sách? | Giá trị thực hoặc hành vi người dùng thay đổi. |
| **Velocity/story points** | Tín hiệu hỗ trợ lập kế hoạch trong một nhóm dùng ước lượng. | Có thể dự báo năng lực tương đối của chính nhóm trong bối cảnh ổn định không? | So sánh hiệu suất giữa đội hoặc outcome. |
| **Throughput** | Số work item hoàn thành trong một khoảng thời gian. | Dòng hoàn tất việc có ổn định không? | Những work item đó có tạo đúng giá trị không. |
| **Cycle time** | Thời gian từ lúc công việc bắt đầu xử lý đến Done theo định nghĩa. | Nút thắt hoặc chờ đợi nằm ở đâu? | Tác động dài hạn của sản phẩm. |
| **Work in Progress (WIP)** | Số hạng mục đang ở trạng thái dở dang. | Đội có mở quá nhiều việc không? | Người dùng đã đạt mục tiêu hay chưa. |
| **Work item age** | Tuổi của hạng mục chưa Done. | Việc nào đang có nguy cơ chậm bất thường? | Một tính năng hoàn thành sẽ thành công. |
| **Deployment frequency** | Tần suất triển khai theo định nghĩa đo. | Dòng đưa thay đổi vào môi trường sử dụng có linh hoạt không? | Người dùng có dùng và nhận giá trị không. |
| **Lead time for changes** | Thời gian từ thay đổi mã đến production theo phạm vi DORA thường dùng. | Chờ ở khâu build/kiểm thử/triển khai ra sao? | Tổng thời gian từ nhu cầu đến outcome. |
| **Change failure / recovery** | Độ ổn định của thay đổi và khả năng phục hồi. | Việc triển khai có an toàn và đáng tin không? | Tính năng tạo đúng lợi ích mong muốn. |
| **Tỷ lệ quay lại học có ý nghĩa** | Outcome hành vi trong phạm vi đo. | Học viên đã quay lại học nhiều hơn chưa? | Chính tính năng đang xét chắc chắn gây ra thay đổi. |
| **Năng lực học duy trì sau một thời gian** | Có thể phản ánh impact trong phạm vi nghiên cứu đủ tin cậy. | Người học có tiến bộ bền vững không? | Không thể khẳng định nguyên nhân nếu thiếu thiết kế đánh giá. |

### 7.1. Flow metrics là năng lực hỗ trợ giá trị

Kanban quan tâm đến việc **hiển thị công việc, quản lý WIP và dòng hoàn thành**. Nếu cycle time giảm, team có thể nhận phản hồi nhanh hơn hoặc sửa lỗi sớm hơn; đây là năng lực quan trọng giúp tạo outcome. Nhưng **cycle time giảm không đồng nghĩa outcome tăng**.

Ví dụ, nhóm hoàn thành các story nhỏ nhanh hơn 30% nhưng chỉ làm những thay đổi ít ai cần. Dòng công việc đã hiệu quả hơn theo một phép đo, còn **hiệu lực của lựa chọn sản phẩm** vẫn cần cải tiến.

### 7.2. Velocity không phải thước đo giá trị

**Story point** thường mô tả một ước lượng tương đối mang tính địa phương của một nhóm; các nhóm có cách ước lượng và chia PBI khác nhau.

Tăng velocity từ 30 lên 45 có thể do:

- Nhóm học cách chia story nhỏ hơn.
- Thay đổi quy tắc ước lượng.
- Hạng mục giai đoạn mới ít phức tạp hơn.
- Đội thực sự giảm blocker.
- Chất lượng bị hạ để đánh dấu Done nhiều hơn.

Không thể kết luận “giá trị tăng 50%” từ con số đó. **Không nên dùng velocity để xếp hạng các đội hoặc áp chỉ tiêu năng suất cá nhân**.

### 7.3. Chất lượng và độ tin cậy thường là guardrails

Một chỉ số như tỷ lệ lỗi dữ liệu, số sự cố nghiêm trọng hoặc thời gian khôi phục có thể là **outcome của một chương trình cải tiến độ tin cậy**. Trong tính năng “Tiếp tục học”, các chỉ số đó thường đóng vai trò **guardrail**: bảo đảm việc tăng tương tác không đi kèm giảm an toàn và chất lượng.

Phân loại phụ thuộc **câu hỏi quản trị cụ thể**, không chỉ tên metric.

## 8. Tách chỉ số dẫn dắt và chỉ số kết quả khỏi bốn tầng

Hai cặp khái niệm thường bị trộn lẫn:

- **Activity–Output–Outcome–Impact:** mô tả **vị trí trong chuỗi tạo giá trị**.
- **Leading–Lagging indicators:** mô tả **tín hiệu giúp dự báo hoặc phản ánh kết quả**, tùy quan hệ và khoảng thời gian được xét.

Chúng không phải hai cách đặt tên cho cùng một thứ.

| Ví dụ | Tầng thường gặp | Có thể là tín hiệu dẫn dắt hoặc trễ đối với mục tiêu nào? |
|---|---|---|
| Thời gian phản hồi phỏng vấn người dùng | Hoạt động/quá trình. | Có thể dẫn dắt thời gian hoàn tất khám phá, nhưng chưa chứng minh nhu cầu đúng. |
| Tỷ lệ học viên thấy nút “Tiếp tục học” | Mức tiếp cận đầu ra/đầu vào của hành vi. | Dẫn dắt khả năng dùng nút, không chắc dẫn dắt học tập. |
| Tỷ lệ hoàn thành một hoạt động học sau khi quay lại | Outcome. | Kết quả của trải nghiệm hiện tại; có thể là chỉ báo sớm cho hoàn thành lộ trình. |
| Tỷ lệ hoàn thành lộ trình sau vài tháng | Outcome dài hạn hoặc impact tùy mô hình. | Lagging so với thay đổi giao diện tuần này. |
| Tỷ lệ lỗi mất tiến độ | Chất lượng/guardrail. | Phản ánh lỗi đã xảy ra; cũng cảnh báo sớm cho nguy cơ bỏ học. |

Một chỉ số chỉ nên gọi là **leading indicator** khi có giả thuyết hoặc bằng chứng hợp lý về việc nó giúp dự báo điều mong muốn. Nếu không, “leading” chỉ là nhãn gây cảm giác chắc chắn.

### 8.1. Tín hiệu sớm không được thay đích đến

Ví dụ, số người click “Tiếp tục học” tăng ngay trong ngày đầu. Nó là tín hiệu hữu ích để biết tính năng có được phát hiện. Nhưng nếu sau đó người học không bắt đầu hoặc hoàn thành bài nào, nhóm cần thay đổi cách hiểu: **click không phải mục tiêu cuối**.

## 9. Định nghĩa phép đo outcome đủ rõ để hai người tính giống nhau

Một câu như “tăng tỷ lệ quay lại học” chưa đủ để thiết kế đo lường. Cần xác định:

1. **Đối tượng:** học viên nào đủ điều kiện được tính?
2. **Sự kiện:** thế nào là “quay lại”, “học” và “hoàn thành”?
3. **Mẫu số:** tất cả người đăng ký, người có bài dang dở, người đủ điều kiện nhìn thấy tính năng hay người đã click?
4. **Tử số:** ai thực sự đạt điều kiện kết quả?
5. **Khoảng thời gian:** 1 ngày, 7 ngày, 28 ngày hay sau một đợt học?
6. **Cohort:** nhóm người dùng được xác định theo thời điểm hoặc đặc điểm nào?
7. **Ngoại lệ:** tài khoản thử, bot, người học đã hoàn tất khóa, lỗi mất tracking?
8. **Phân khúc:** thiết bị, nhóm học, trải nghiệm có công nghệ hỗ trợ, trình độ hoặc kênh truy cập liên quan?
9. **Nguồn và độ tin cậy:** sự kiện được ghi ở client hay server, có mất/trùng dữ liệu không?
10. **Quyết định:** kết quả này sẽ dẫn tới hành động gì?

### 9.1. Ví dụ một định nghĩa vận hành

**Tên chỉ số:** Tỷ lệ học viên quay lại học có ý nghĩa trong 7 ngày.

**Đối tượng:** học viên đã xác thực, có ít nhất một bài đang học nhưng chưa hoàn thành, có quyền tiếp cận nội dung và thuộc cohort được đo.

**Tử số:** số học viên thuộc cohort hoàn thành ít nhất một hoạt động học được xác minh trong vòng 7 ngày kể từ mốc kích hoạt được định nghĩa.

**Mẫu số:** tổng số học viên đủ điều kiện trong cohort tại mốc kích hoạt; mỗi người chỉ tính một lần.

**Không tính:** tài khoản kiểm thử, robot, người không còn quyền với nội dung hoặc trường hợp không có dữ liệu đáng tin theo chính sách.

**Phân khúc cần xét:** thiết bị, phiên bản giao diện, loại khóa, thời gian đã ngừng học, nhóm có/không có khả năng dùng tính năng.

**Cảnh báo đo lường:** sự kiện chỉ được gửi từ frontend có thể bị thiếu vì mạng gián đoạn; sự kiện “đã mở trang” không đủ chứng minh có học.

### 9.2. Tử số–mẫu số phải thuộc cùng một quần thể

Nếu tử số đếm học viên **đã click** rồi quay lại, còn mẫu số đếm **toàn bộ học viên đăng ký**, tỷ lệ có thể bị hiểu sai. Nếu mẫu số chỉ gồm những người click, nó đo **conversion sau click**, không đo outcome của toàn bộ nhóm người dùng đủ điều kiện.

Không thể đổi mẫu số giữa hai kỳ rồi diễn giải sự tăng giảm như thay đổi hành vi thật.

### 9.3. Mốc thời gian phải phù hợp hành vi

Một tính năng mở hôm qua không thể được đánh giá ngay bằng “tỷ lệ hoàn thành khóa trong 90 ngày”. Chỉ những cohort đã có **đủ thời gian quan sát** mới đủ điều kiện tính chỉ số 90 ngày.

Với cohort mới chưa đủ cửa sổ, nên công bố trạng thái **chưa trưởng thành (immature cohort)** hoặc chờ đủ dữ liệu, không trộn vào mẫu số rồi xem như thất bại.

## 10. Bài toán số liệu: cải thiện 8 điểm phần trăm nghĩa là gì?

Giả sử hai cohort tương đối tương đồng được theo dõi đủ 7 ngày:

| Số liệu minh họa | Cohort trước | Cohort sau |
|---|---:|---:|
| Học viên đủ điều kiện | 1.000 | 1.000 |
| Học viên quay lại học có ý nghĩa trong 7 ngày | 240 | 320 |
| Tỷ lệ quay lại học | 24% | 32% |

Tính toán:

~~~text
Tỷ lệ trước = 240 / 1.000 × 100% = 24%
Tỷ lệ sau  = 320 / 1.000 × 100% = 32%

Thay đổi tuyệt đối = 32% - 24% = 8 điểm phần trăm
Thay đổi tương đối  = (32% - 24%) / 24% × 100%
                   ≈ 33,3%
~~~

Nói “tăng 8%” là **mơ hồ** và có thể không chính xác: tăng **8 điểm phần trăm** khác tăng **8 phần trăm tương đối**.

### 10.1. Số liệu này chưa chứng minh nguyên nhân

Dù tỷ lệ tăng từ 24% lên 32%, vẫn chưa thể tuyên bố tính năng “Tiếp tục học” **đã gây ra** toàn bộ sự tăng đó. Giữa hai cohort có thể khác nhau về:

- Tỷ lệ học viên mới và học viên đã có thói quen học.
- Độ khó của khóa học, chất lượng nội dung, lịch kiểm tra.
- Hoạt động truyền thông hoặc nhắc học khác diễn ra đồng thời.
- Thiết bị, kết nối mạng và mùa vụ.
- Thay đổi cách ghi sự kiện hoặc điều kiện tính “hoạt động học”.

Tín hiệu đủ để **điều tra tiếp và cân nhắc mở rộng có kiểm soát**, nhưng quan hệ nhân quả cần thiết kế đo lường thích hợp hơn.

### 10.2. Đếm người và đếm sự kiện khác nhau

Nếu một học viên mở bài 15 lần, số lượt mở (**events**) tăng nhiều nhưng chỉ có **một học viên** được tính vào chỉ số tỷ lệ người quay lại. Cần nêu rõ đơn vị là **users, sessions, events hay orders**.

Với mục tiêu “người học được hỗ trợ”, chỉ đếm event có thể thiên về người hoạt động thường xuyên và che khuất nhóm học viên đang gặp trở ngại.

### 10.3. Phân biệt mức tăng và mức mục tiêu

Baseline 24% là dữ liệu ban đầu. Mục tiêu 32% nếu được chọn có thể là một **target giả định**. Kết quả quan sát 32% là **actual**. Không nên trộn lẫn:

- **Baseline:** trạng thái trước để so sánh.
- **Target:** điều mong muốn hoặc giả thuyết thành công.
- **Actual:** giá trị quan sát được.
- **Uncertainty:** mức không chắc chắn do mẫu, đo lường và yếu tố khác.

Đạt target vẫn cần kiểm tra guardrails và ý nghĩa kinh doanh; không đạt target có thể vẫn tạo ra học hỏi có giá trị.

## 11. Đo hành trình thay vì chỉ một tỷ lệ cuối

Outcome có thể bị ảnh hưởng ở nhiều bước. **Funnel (phễu hành trình)** giúp xác định hạng mục nào đang tạo ma sát.

Ví dụ hành trình “Tiếp tục học”:

~~~mermaid
flowchart TD
    A["Học viên đủ điều kiện"] --> B["Đã nhìn thấy lựa chọn Tiếp tục học"]
    B --> C["Đã kích hoạt lựa chọn"]
    C --> D["Bài đúng tiến độ được mở thành công"]
    D --> E["Hoàn thành hoạt động học có ý nghĩa"]
    E --> F["Tiếp tục duy trì học ở những tuần sau"]
~~~

### 11.1. Ví dụ funnel giả định

| Bước | Số học viên duy nhất |
|---|---:|
| Đủ điều kiện trong cohort | 1.000 |
| Thực sự được hiển thị nút | 800 |
| Kích hoạt nút | 500 |
| Mở đúng bài đã lưu tiến độ | 470 |
| Hoàn thành ít nhất một hoạt động học trong cửa sổ | 320 |

Các tỷ lệ có thể tính:

- **Tỷ lệ được tiếp cận:** 800 / 1.000 = **80%**.
- **Tỷ lệ kích hoạt trên số đã thấy:** 500 / 800 = **62,5%**.
- **Tỷ lệ mở bài đúng trên số đã kích hoạt:** 470 / 500 = **94%**.
- **Tỷ lệ hoàn thành hoạt động trên số mở bài đúng:** 320 / 470 ≈ **68,1%**.
- **Tỷ lệ kết quả trên toàn cohort đủ điều kiện:** 320 / 1.000 = **32%**.

**Tất cả số liệu trên đều giả định.** Trong hệ thống thật, cần bảo đảm các bước dùng cùng một cohort/cửa sổ đo và mỗi người được đếm đúng, nếu không funnel có thể vô nghĩa.

### 11.2. Funnel cho biết cần học tiếp ở đâu

Nếu chỉ 80% học viên đủ điều kiện được hiển thị nút, vấn đề có thể nằm ở phân phối tính năng, thiết bị hoặc điều kiện hiển thị. Nếu nhiều người thấy nhưng ít kích hoạt, có thể do nhãn hoặc mức phù hợp. Nếu click cao nhưng mở bài sai, vấn đề là **chất lượng tiến độ/tích hợp**. Nếu mở bài đúng nhưng người học vẫn rời đi, cần hiểu **trải nghiệm nội dung và động lực học**, không đơn giản làm nút to hơn.

Không nên tối ưu từng tỷ lệ cục bộ mà bỏ mục tiêu cuối. Một nhãn gây tò mò có thể tăng click nhưng giảm sự tin cậy và chất lượng học.

## 12. Đo outcome đa chiều và dùng guardrails

Một outcome gần mục tiêu thường cần được nhìn cùng các chỉ số khác để tránh **tối ưu cục bộ**.

| Vai trò | Ví dụ đo lường | Vì sao cần |
|---|---|---|
| **Primary outcome** | Tỷ lệ học viên đủ điều kiện thực sự quay lại học có ý nghĩa trong 7 ngày. | Trả lời giả thuyết giá trị chính. |
| **Supporting outcome** | Thời gian từ đăng nhập đến khi mở đúng bài dang dở. | Cho biết ma sát trải nghiệm có giảm không. |
| **Adoption signal** | Tỷ lệ đủ điều kiện nhìn thấy/dùng nút. | Xem tính năng có được tiếp cận và sử dụng. |
| **Quality guardrail** | Lỗi khôi phục sai vị trí, dữ liệu tiến độ bị ghi nhầm hoặc mất. | Không đánh đổi tính đúng để lấy tỷ lệ quay lại. |
| **Performance guardrail** | p95 thời gian mở bài và tỷ lệ lỗi. | Không làm người học chờ lâu hơn. |
| **Accessibility guardrail** | Hành trình dùng bàn phím/screen reader đạt tiêu chuẩn áp dụng. | Không làm tăng giá trị cho nhóm này bằng cách loại trừ nhóm khác. |
| **Privacy/security guardrail** | Không có truy cập sai quyền hoặc thu thập dữ liệu vượt mục đích cho phép. | Phản hồi sản phẩm không được gây hại. |
| **Long-term indicator** | Tỷ lệ hoàn thành lộ trình có chất lượng sau nhiều tuần/tháng. | Kiểm tra giả thuyết đóng góp vào impact. |

### 12.1. Guardrail không phải chỉ số phụ có thể bỏ qua

Ví dụ, tỷ lệ quay lại tăng từ 24% lên 32% nhưng lỗi mất tiến độ cũng tăng mạnh, khiến học viên hoàn thành ít bài hơn. Khi đó nhóm **không thể xem mục tiêu thành công toàn diện** chỉ vì primary outcome tăng.

Guardrails giúp trả lời: **chúng ta có tạo ra lợi ích trong một hệ thống an toàn, công bằng và đáng tin không?**

### 12.2. Không đặt mục tiêu tăng mọi chỉ số

Một số chỉ số nên **giảm** (lỗi dữ liệu, thời gian chờ), một số nên **tăng** (khả năng hoàn thành tác vụ), một số cần **nằm trong giới hạn** (tải vận hành, tỷ lệ thông báo).

Ví dụ, tăng thời lượng người dùng ở lại ứng dụng **không luôn tốt**: người học có thể phải mất nhiều thời gian để tìm nội dung hoặc mắc kẹt trong giao diện.

Mỗi chỉ số cần nêu **hướng cải thiện mong muốn và cơ sở của hướng đó**.

## 13. Cohort, phân khúc và thời gian quan sát

**Cohort** là một nhóm đối tượng được xác định theo một điều kiện chung, thường là thời điểm tham gia hoặc đạt một trạng thái. Khi so sánh outcome, cohort giúp tránh trộn những người có cơ hội và thời gian quan sát khác nhau.

### 13.1. Ví dụ thiết kế cohort

- **Cohort A:** học viên có bài dang dở và đủ điều kiện trong tuần trước khi mở tính năng.
- **Cohort B:** học viên tương tự trong tuần sau khi mở tính năng.
- **Cửa sổ theo dõi:** 7 ngày sau mốc đủ điều kiện.
- **Điều kiện loại trừ:** tài khoản thử, không còn quyền nội dung hoặc tracking không đáng tin.
- **Phân khúc kiểm tra:** loại thiết bị, nhóm khóa học, độ mới của người học, thời gian gián đoạn.

Hai cohort không tự đồng nhất chỉ vì có cùng 1.000 người. Cần xem sự khác biệt nền và những thay đổi ngoài sản phẩm.

### 13.2. “Lịch” và “tuổi cohort” khác nhau

Nếu người dùng mới chỉ đăng ký hôm qua, họ chưa có 7 ngày để thể hiện hành vi. Tính họ là “chưa quay lại trong 7 ngày” sẽ làm giảm tỷ lệ một cách sai lệch.

Nên chỉ đưa những người có **đủ cửa sổ quan sát** vào báo cáo đã chốt, hoặc báo rõ kết quả tạm thời. Đối với outcome dài hạn, việc chờ cohort trưởng thành đặc biệt quan trọng.

### 13.3. Phân khúc để nhìn thấy nhóm bị bỏ lại

Tỷ lệ chung có thể tăng trong khi:

- Người dùng thiết bị cũ có trải nghiệm tệ hơn.
- Người dùng bàn phím không thấy/không kích hoạt được tính năng.
- Một loại khóa học có tiến độ được lưu sai.
- Học viên mới chưa hiểu ngôn ngữ trên nút.

Vì vậy, sau khi xem tổng thể, nhóm nên phân tích **những phân khúc liên quan đến giả thuyết hoặc rủi ro**, tuân thủ quyền riêng tư và không suy diễn từ nhóm quá nhỏ.

### 13.4. Một ví dụ Simpson's paradox ở mức trực giác

Giả sử tỷ lệ quay lại **trong từng loại khóa học** đều gần như giữ nguyên, nhưng kỳ sau có nhiều học viên ở loại khóa vốn có tỷ lệ quay lại cao. Tỷ lệ trung bình toàn hệ thống vẫn có thể tăng.

Điều đó **không chứng minh** tính năng mới đã cải thiện hành vi; nó có thể chỉ phản ánh thay đổi tỷ trọng người dùng. Hãy xem kết quả trong các nhóm tương đồng và tỷ trọng của chúng, không chỉ một con số tổng hợp.

## 14. Tương quan không phải quan hệ nhân quả

Một dashboard cho thấy người dùng có nhấp “Tiếp tục học” thường hoàn thành nhiều bài hơn. Nhưng những người vốn có động lực học cao **có thể vừa nhấp nút nhiều vừa hoàn thành nhiều bài**, bất kể nút có tác dụng mạnh hay không.

Đây là vấn đề **selection bias (thiên lệch lựa chọn)**. Nếu chỉ so sánh “người đã click” với “người không click”, kết quả khó tách tác động của tính năng khỏi đặc điểm ban đầu của người dùng.

### 14.1. Các mức bằng chứng khác nhau

| Cách đánh giá | Có thể học gì? | Giới hạn |
|---|---|---|
| **Phản hồi định tính** | Hiểu người dùng gặp khó ở đâu và vì sao. | Không đại diện tự động cho toàn bộ người dùng. |
| **Before–after** | Quan sát thay đổi trước và sau một thời điểm. | Có thể bị mùa vụ, truyền thông, thay đổi cohort và tác động ngoài ảnh hưởng. |
| **So sánh cohort/phân khúc có kiểm soát** | Hiểu khác biệt trong những nhóm tương đồng hơn. | Có thể còn biến nhiễu chưa quan sát. |
| **A/B test ngẫu nhiên khi phù hợp** | Ước lượng tác động của thay đổi trong điều kiện thí nghiệm được kiểm soát tốt. | Cần tính hợp lệ phân nhóm, kích thước mẫu, điều kiện đạo đức/an toàn, thời gian và rủi ro. |
| **Nghiên cứu dài hạn/thiết kế đánh giá sâu** | Hiểu đóng góp của giải pháp tới tác động xa hơn. | Tốn thời gian; kết quả chịu nhiều yếu tố ngoài sản phẩm. |

Không phải mọi thay đổi đều phù hợp A/B test. Một bản sửa lỗ hổng bảo mật nghiêm trọng hoặc lỗi mất dữ liệu **không nên bị giữ lại cho một nhóm người dùng chỉ để có đối chứng**, nếu điều đó gây rủi ro không chấp nhận được.

### 14.2. Ví dụ A/B test về “Tiếp tục học”

Giả sử tổ chức được phép thử nghiệm một cải tiến giao diện có rủi ro thấp:

1. Xác định rõ đối tượng đủ điều kiện và chỉ số primary outcome trước khi bắt đầu.
2. Phân bổ ngẫu nhiên nhất quán đối tượng vào hai nhóm, tránh người cùng tài khoản thấy hai phiên bản tùy lúc.
3. Kiểm tra tính tương đương ban đầu và cách ghi dữ liệu.
4. Giữ nguyên các tiêu chuẩn bảo mật, chất lượng, accessibility của cả hai phiên bản.
5. Theo dõi kết quả sau đủ cửa sổ; công bố mức thay đổi và độ không chắc chắn.
6. Xem cả guardrails, phân khúc liên quan và ảnh hưởng vận hành.
7. Ra quyết định mở rộng, sửa đổi hoặc dừng dựa trên bằng chứng tổng hợp.

**Một kết quả có chênh lệch không đồng nghĩa đã có bằng chứng đủ mạnh.** Phải quan tâm tới cỡ mẫu, độ biến thiên, độ tin cậy của đo lường, nhiều lần nhìn dữ liệu và ý nghĩa thực tế của chênh lệch.

### 14.3. Đừng kết luận chỉ từ một giá trị p

Nếu dùng kiểm định thống kê, nhóm nên xem **hiệu ứng thực tế, khoảng tin cậy, thiết kế và chất lượng dữ liệu**; không chỉ áp một ngưỡng p-value rồi gắn nhãn “thắng/thua”.

Một thay đổi nhỏ nhưng ước lượng khá chắc có thể không đáng đầu tư; một thay đổi có lợi ích tiềm năng lớn nhưng dữ liệu còn chưa chắc cần kiểm tra tiếp. **Mục tiêu là quyết định sản phẩm tốt**, không phải giành thắng lợi trong báo cáo thí nghiệm.

## 15. Đo impact dài hạn và trách nhiệm về tác động

Outcome “học viên quay lại học thường xuyên hơn” có thể dẫn tới impact “năng lực học tốt hơn”, nhưng mối liên hệ cần được xem xét riêng.

### 15.1. Phân biệt hoàn thành hoạt động và thực sự học được

“Hoàn thành 10 video” là một **đầu ra hành vi/tiến độ sử dụng**, có thể dùng như proxy cho quá trình học. Nhưng nó chưa chứng minh học viên có thể áp dụng kiến thức.

Những phép đo gần tác động hơn có thể bao gồm:

- Mức độ làm đúng bài thực hành có độ khó tương đương.
- Khả năng giải quyết bài toán mới sau một khoảng thời gian.
- Khả năng duy trì kiến thức ở mốc đánh giá tiếp theo.
- Khả năng hoàn tất một mục tiêu học tập quan trọng, không chỉ số phút xem.
- Phản hồi từ hoạt động thực tế của người học, với phương pháp thu thập phù hợp.

Không có một phép đo đơn lẻ nào hoàn toàn thay thế đánh giá năng lực. Nhóm cần lựa chọn thước đo tương ứng **sứ mệnh sản phẩm và phạm vi bằng chứng có thể thu thập hợp lệ**.

### 15.2. Tác động thường chịu ảnh hưởng bên ngoài

Ví dụ, một người học hoàn tất lộ trình nhưng việc họ có đạt kết quả nghề nghiệp mong muốn còn phụ thuộc thị trường lao động, kinh nghiệm, điều kiện cá nhân và nhiều yếu tố khác.

Nếu sản phẩm được thiết kế để hỗ trợ năng lực nghề nghiệp, đội có thể đặt mục tiêu góp phần vào kết quả đó, nhưng khi báo cáo cần phân biệt **đóng góp có căn cứ** với **khẳng định nhân quả vượt quá dữ liệu**.

### 15.3. Cân nhắc các tác động không mong muốn

Một thiết kế liên tục nhắc học có thể làm tỷ lệ quay lại tăng nhưng gây phiền nhiễu, giảm cảm giác kiểm soát hoặc khuyến khích học đối phó. Một cơ chế chỉ thưởng số lần hoàn thành có thể khiến người học lướt nhanh nội dung mà không hiểu.

Đánh giá impact nên hỏi:

- Người dùng có được lợi theo cách họ thực sự mong muốn không?
- Có nhóm nào chịu bất lợi không?
- Kết quả có bền vững và phù hợp quyền riêng tư, an toàn không?
- Có xuất hiện hành vi “lách” chỉ số hoặc chi phí vận hành lớn bất thường không?

## 16. Metric design canvas: thiết kế phép đo trước khi xây dashboard

Để tránh có nhiều biểu đồ nhưng ít quyết định, nhóm có thể sử dụng bảng thiết kế chỉ số sau:

| Trường | Câu hỏi cần trả lời |
|---|---|
| **Quyết định cần hỗ trợ** | Kết quả sẽ giúp ưu tiên, tiếp tục, sửa hoặc dừng điều gì? |
| **Mục tiêu giá trị** | Người dùng/tổ chức mong đợi sự thay đổi nào? |
| **Giả thuyết nhân quả** | Vì sao đầu ra này được kỳ vọng tạo outcome? Giả định nào có thể sai? |
| **Loại chỉ số** | Activity, output, outcome, impact, hoặc guardrail/đặc tính hỗ trợ? |
| **Định nghĩa đo** | Tử số, mẫu số, đơn vị, sự kiện và cửa sổ thời gian là gì? |
| **Nguồn dữ liệu** | Ghi từ đâu, có đáng tin và hợp lệ về quyền riêng tư không? |
| **Baseline** | Trạng thái ban đầu theo định nghĩa giống nhau là bao nhiêu? |
| **Target hoặc ngưỡng** | Mức cải thiện/giới hạn nào có ý nghĩa, vì sao? |
| **Phân khúc/cohort** | Ai nằm trong phạm vi, ai dễ bị bỏ sót? |
| **Guardrails** | Điều gì không được xấu đi khi chỉ số chính cải thiện? |
| **Độ không chắc chắn** | Sai số, thiếu tracking, yếu tố ngoài và hạn chế thiết kế? |
| **Nhịp xem lại** | Khi nào dữ liệu đủ trưởng thành và ai thảo luận? |
| **Hành động khi không đạt** | Điều tra điều gì trước khi thêm tính năng hoặc đổi mục tiêu? |

### 16.1. Ví dụ canvas thu gọn

~~~text
Mục tiêu: người học quay lại hoạt động học có ý nghĩa thường xuyên hơn
Giả thuyết: nút Tiếp tục học giảm thời gian tìm lại bài

Output:
  Tính năng đã tích hợp, đạt DoD và mở cho nhóm được phép

Primary outcome:
  Tỷ lệ học viên đủ điều kiện hoàn thành >= 1 hoạt động học
  trong vòng 7 ngày sau mốc kích hoạt được định nghĩa

Supporting measures:
  Tỷ lệ nhìn thấy nút, tỷ lệ mở đúng bài, thời gian tới bài cũ

Guardrails:
  Lỗi mất tiến độ, p95 mở bài, phân quyền, truy cập bàn phím,
  dữ liệu cá nhân và phản hồi người dùng

Baseline:
  Tính theo cohort đã đủ cửa sổ 7 ngày, với định nghĩa cố định

Quyết định:
  Tiếp tục, điều chỉnh hoặc thay giải pháp sau khi đánh giá
  dữ liệu có đủ tin cậy; không đánh đồng click với học tập
~~~

Mục tiêu số cần được đặt từ dữ liệu và đánh giá giá trị thực; ví dụ trên không tự gán một target tùy ý.

## 17. OKR: mục tiêu nên mô tả kết quả, còn công việc là sáng kiến

**Objectives and Key Results (OKR)** là một cách diễn đạt mục tiêu và kết quả then chốt có thể sử dụng trong một số tổ chức. Nó **không phải yêu cầu bắt buộc của Scrum, Kanban hay Agile**.

### 17.1. Phân biệt Objective, Key Result và Initiative

| Thành phần | Nội dung minh họa |
|---|---|
| **Objective** | Giúp học viên tiếp tục lộ trình dễ dàng và có động lực hơn. |
| **Key Result 1** | Tăng tỷ lệ học viên đủ điều kiện quay lại học có ý nghĩa trong 7 ngày từ baseline được xác nhận đến mức mục tiêu hợp lý. |
| **Key Result 2** | Giảm thời gian trung vị từ lúc đăng nhập đến khi mở đúng bài dang dở theo phạm vi đo. |
| **Key Result/guardrail chất lượng** | Giữ lỗi mất tiến độ và những rào cản truy cập cốt lõi trong giới hạn chấp nhận được. |
| **Initiative** | Nghiên cứu hành trình, cải tiến lưu tiến độ, thiết kế nút “Tiếp tục học”, thử với người dùng. |

**“Phát hành nút Tiếp tục học”** thường là một initiative hoặc output, không phải outcome Key Result tốt khi mục tiêu là thay đổi hành vi học.

### 17.2. Một mục tiêu có thể cần cả delivery và outcome

Nhóm vẫn có thể theo dõi **mốc đầu ra** để quản lý phụ thuộc và năng lực giao hàng. Điều quan trọng là không ghi “release đúng ngày” rồi tuyên bố mục tiêu giá trị đã đạt nếu người dùng không nhận được lợi ích.

Ở giai đoạn khám phá có rủi ro cao, **mục tiêu học hỏi** cũng có giá trị: xác minh liệu học viên bỏ học vì khó tìm lại bài hay vì nội dung không phù hợp. Khi đó cần nêu bằng chứng học hỏi mong muốn, không chỉ đếm số người được phỏng vấn.

## 18. Dùng chỉ số trong Scrum, Kanban và XP

### 18.1. Scrum: Product Goal, Sprint Goal và Sprint Review

Trong Scrum:

- **Product Goal** định hướng kết quả dài hơn mà nhóm muốn tạo cho sản phẩm.
- **Sprint Goal** cho biết kết quả quan trọng mà Sprint hướng tới.
- **Product Backlog** chứa công việc được sắp thứ tự để cải thiện sản phẩm.
- **Increment** là bước tiến dùng được, tích hợp và đáp ứng Definition of Done.
- **Sprint Review** là dịp Scrum Team và stakeholder kiểm tra kết quả, học từ bằng chứng và thích ứng hướng tiếp theo.

**Ví dụ:** Sprint Goal có thể là “giúp học viên tìm lại đúng bài đang học với ít ma sát hơn trong một phạm vi thử”. Developers tạo Increment đạt DoD, nhóm đo thời gian tìm lại bài và nhận phản hồi. Nếu còn quá ít thời gian để thấy outcome 7 ngày, Review có thể thảo luận **tín hiệu sớm và kế hoạch quan sát tiếp**, không bịa ra kết quả chưa đủ thời gian.

### 18.2. Kanban: cải thiện dòng công việc để học sớm

Kanban dùng WIP, throughput, cycle time và work item age để nhìn thấy khả năng hoàn thành công việc. Những chỉ số này giúp giảm thời gian chờ và tăng cơ hội phản hồi.

Nhưng cần nối chúng với câu hỏi **“Đang hoàn thành công việc nào và nó có tạo giá trị không?”**. Khi WIP giảm và cycle time ngắn lại, team có thể phát hành lát giá trị nhỏ hơn, đo outcome sớm hơn. Nếu backlog ưu tiên sai vấn đề, dòng công việc nhanh hơn vẫn chưa đủ.

### 18.3. XP: chất lượng kỹ thuật bảo vệ giả thuyết giá trị

Các thực hành XP như TDD, pair programming, continuous integration, refactoring và small releases giúp giảm lỗi và tăng khả năng thay đổi. Đây thường là **năng lực hỗ trợ outcome**.

Ví dụ, một bộ kiểm thử khôi phục tiến độ đáng tin giúp giảm khả năng nút “Tiếp tục học” mở sai bài. Tuy nhiên, số lượng unit test không tự chứng minh người học thực sự quay lại và tiến bộ.

### 18.4. DevOps: từ triển khai sang sử dụng thực

Deployment frequency, lead time for changes, change failure và recovery time giúp đội hiểu khả năng đưa thay đổi vào production an toàn. Chúng bổ sung cho các chỉ số sản phẩm, **không thay thế việc quan sát hành vi và tác động của người dùng**.

**Tốc độ cung cấp khả năng** và **mức giá trị được tạo ra** là hai câu hỏi liên quan nhưng khác nhau.

## 19. Ra quyết định khi chỉ số kể những câu chuyện trái nhau

Một dashboard hữu ích phải cho phép thảo luận khi các tín hiệu **không cùng tăng hoặc cùng giảm**.

| Tình huống | Điều quan sát | Quyết định nên cân nhắc |
|---|---|---|
| **Hoạt động cao, đầu ra thấp** | Họp nhiều, nhiều task đang làm, ít PBI Done. | Xem WIP, blocker, chất lượng đầu vào, phụ thuộc và tích hợp. |
| **Đầu ra cao, adoption thấp** | Nhiều tính năng release nhưng ít người tìm thấy. | Kiểm tra khám phá nhu cầu, khả năng tiếp cận, nội dung và đường phân phối. |
| **Adoption cao, outcome thấp** | Nút được click nhiều, người học vẫn bỏ dở. | Xem chất lượng trải nghiệm sau click, bài học, tính đúng tiến độ và giả thuyết gốc. |
| **Outcome tăng, guardrail xấu đi** | Quay lại tăng nhưng lỗi mất tiến độ và phàn nàn tăng. | Điều tra và sửa chất lượng, có thể dừng mở rộng theo rủi ro. |
| **Outcome gần tăng, impact chưa rõ** | Quay lại tốt hơn, chưa có dữ liệu năng lực học dài hạn. | Tiếp tục theo dõi đủ cửa sổ và đánh giá đúng mức bằng chứng. |
| **Impact kỳ vọng không xuất hiện** | Người học hoạt động nhiều hơn nhưng kết quả học không cải thiện. | Xem lại lý thuyết thay đổi, proxy và giải pháp, thay vì chỉ tăng tương tác. |
| **Số liệu đẹp nhưng tracking đổi** | Tỷ lệ tăng đúng ngày thay công cụ ghi sự kiện. | Kiểm tra tính liên tục của định nghĩa và dữ liệu trước khi kết luận. |

### 19.1. Không nên lập tức xây thêm tính năng

Một outcome không tăng có thể do:

- Giả thuyết sai.
- Output chưa được dùng hoặc dùng sai.
- Lỗi kỹ thuật, rào cản accessibility hoặc hiệu năng.
- Hệ thống đo sai.
- Chưa đủ thời gian quan sát.
- Tác động ngoài làm thay đổi hành vi.

Vì thế, trước khi bổ sung backlog, hãy **xác định mắt xích nào đang thiếu bằng chứng**.

## 20. Goodhart's law và nguy cơ biến chỉ số thành mục tiêu

Một ý tưởng thường được tóm tắt là **khi thước đo trở thành mục tiêu cần tối đa hóa bằng mọi giá, nó dễ mất đi khả năng phản ánh đúng điều ban đầu muốn đo**.

Trong phần mềm, các phản ứng có thể xuất hiện:

- Chia một story thành rất nhiều story cực nhỏ để tăng số lượng Done.
- Tạo commit hoặc deploy không mang ý nghĩa để tăng chỉ số hoạt động.
- Chỉ chọn việc dễ để giảm cycle time trung bình.
- Gửi quá nhiều thông báo để tăng số phiên quay lại.
- Thiết kế nút gây hiểu nhầm để tăng click.
- Giảm kiểm thử hoặc bỏ qua bug để đạt target velocity.
- Không ghi nhận sự cố nhằm làm change failure rate đẹp hơn.

### 20.1. Metric gaming không phải lúc nào cũng do cá nhân cố tình xấu

Nếu tổ chức đánh giá đội chỉ theo số ticket hoàn thành, một nhóm chịu áp lực có thể tối ưu quy trình để đáp ứng tiêu chí đó, ngay cả khi làm giảm giá trị. Đây là **vấn đề thiết kế hệ thống khuyến khích**, không chỉ là chuyện đạo đức của một người.

### 20.2. Các cách giảm rủi ro

1. Đo **outcome cùng guardrails**, không chỉ một mục tiêu duy nhất.
2. Dùng **metric để đặt câu hỏi**, không quy kết năng lực cá nhân.
3. Giữ định nghĩa đo rõ ràng, kiểm tra thay đổi tracking và ngữ cảnh.
4. Kết hợp số liệu với quan sát định tính, phản hồi người dùng và chất lượng sản phẩm.
5. Tránh so sánh đội khác nhau bằng story point, velocity hoặc số commit.
6. Cho phép nêu rủi ro và kết quả không mong muốn mà không bị trừng phạt vô lý.
7. Định kỳ hỏi: **“Nếu chỉ số này tăng, có trường hợp nào người dùng thực sự tệ hơn không?”**

## 21. Chất lượng dữ liệu và quyền riêng tư của phép đo

Không thể ra quyết định tốt từ dữ liệu không đáng tin hoặc được thu thập thiếu trách nhiệm.

### 21.1. Một event tracking cần được đặc tả

Ví dụ sự kiện:

~~~json
{
  "event_name": "learning_activity_completed",
  "event_version": 1,
  "occurred_at": "2026-11-23T10:00:00Z",
  "activity_type": "practice",
  "course_category": "programming",
  "completion_state": "verified",
  "anonymous_subject_id": "opaque-example-id"
}
~~~

**Dữ liệu chỉ là ví dụ giả định**, không phải cấu trúc bắt buộc. Trong sản phẩm thật, cần lựa chọn trường dữ liệu tối thiểu, quyền hạn hợp lệ, cách định danh, tính chính xác của đồng hồ và điều kiện xử lý sự kiện theo chính sách tổ chức.

### 21.2. Những lỗi đo lường phổ biến

| Lỗi | Ảnh hưởng | Cách giảm |
|---|---|---|
| Gửi event hai lần vì retry. | Tăng giả số lượt sử dụng/hoàn thành. | Thiết kế khóa định danh/idempotency hoặc quy tắc khử trùng phù hợp. |
| Chỉ ghi event phía client. | Mất sự kiện khi mạng lỗi hoặc trang đóng. | Xem nguồn server đáng tin và đối soát khi thích hợp. |
| Đổi tên/ý nghĩa event không version. | Hai giai đoạn không còn so sánh được. | Quản lý schema và thông báo thay đổi định nghĩa. |
| Đếm phiên thay vì người duy nhất. | Người dùng hoạt động nhiều bị tính nặng hơn. | Chọn đơn vị phù hợp mục tiêu. |
| Mẫu số gồm người chưa đủ thời gian quan sát. | Tỷ lệ kết quả thấp giả tạo. | Chỉ tính cohort trưởng thành hoặc ghi rõ kết quả tạm. |
| Chỉ quan sát người đã click. | Thiên lệch lựa chọn, bỏ qua người không tiếp cận được. | Đo từ quần thể đủ điều kiện và funnel đầy đủ. |
| Thu thập dữ liệu vượt nhu cầu. | Rủi ro quyền riêng tư và tuân thủ. | Giảm trường, hạn chế truy cập và thời gian lưu. |

### 21.3. Không thu dữ liệu nhạy cảm chỉ để có dashboard đẹp

Phân tích sản phẩm cần tuân thủ yêu cầu về quyền riêng tư, quyền truy cập và mục đích thu thập. Không nên ghi nội dung bài làm riêng tư, token đăng nhập hoặc thông tin cá nhân không cần thiết vào log phân tích.

Khi báo cáo theo phân khúc, các nhóm quá nhỏ có thể dẫn đến **rò rỉ thông tin gián tiếp**; cần chọn cách tổng hợp và quyền xem phù hợp.

## 22. Một vòng vận hành đo lường Agile thực dụng

Đo lường hữu ích phải được nối với **nhịp ra quyết định và hành động**.

### Bước 1 — Bắt đầu từ vấn đề người dùng

Hỏi “người học đang gặp khó gì và vì sao việc đó quan trọng?”, không bắt đầu bằng “dashboard có sẵn những số nào?”.

### Bước 2 — Viết giả thuyết thay đổi

Mô tả đầu ra dự kiến, outcome mong muốn và mối liên hệ được giả định giữa chúng. Ghi những điều chưa chắc.

### Bước 3 — Chọn số ít phép đo có thể quyết định

Một primary outcome, vài supporting measures và các guardrails thiết yếu thường hữu ích hơn một bảng hàng trăm chỉ số không ai biết dùng làm gì.

### Bước 4 — Kiểm tra khả năng đo trước khi phát hành

Xác nhận event, đơn vị, cohort, baseline, cửa sổ, nguồn dữ liệu, quyền riêng tư và cách đối soát. Không để tới sau phát hành mới phát hiện thiếu dữ liệu gốc.

### Bước 5 — Giao phần giá trị nhỏ và quan sát

Sử dụng Increment đã đáp ứng chất lượng, mở trong phạm vi được phép, rồi thu phản hồi định tính/định lượng phù hợp.

### Bước 6 — Xem kết quả với cả nhóm

Đặt cạnh nhau:

- Hoạt động và đầu ra đã hoàn tất.
- Outcome quan sát được và độ không chắc chắn.
- Guardrails về chất lượng, hiệu năng, bảo mật, accessibility.
- Nút thắt flow và chi phí vận hành.
- Bằng chứng nào hỗ trợ hoặc bác bỏ giả thuyết.

### Bước 7 — Quyết định và ghi lại lý do

Có thể tiếp tục, mở rộng, sửa, dừng, thử giả thuyết khác hoặc thu thêm dữ liệu. Quyết định phải cân nhắc **giá trị người dùng**, không chỉ đạt chỉ tiêu của kỳ.

### Bước 8 — Kiểm tra kết quả sau thay đổi

Lập một nhịp xem lại phù hợp để biết hành động có thực sự mang lại cải thiện. **Phản hồi chỉ có ích khi tạo ra khả năng thích ứng**.

## 23. Bài thực hành: phân loại và đọc dashboard

Một nhóm phát triển tính năng “Tiếp tục học” công bố báo cáo giả định:

| Mã | Phát biểu |
|---|---|
| A | Nhóm đã tổ chức 8 buổi phỏng vấn và 3 buổi xem nguyên mẫu. |
| B | Nhóm đã phát hành tính năng “Tiếp tục học” và hoàn tất 14 PBI. |
| C | 76% học viên đủ điều kiện đã nhìn thấy nút mới. |
| D | Tỷ lệ học viên quay lại hoàn thành ít nhất một hoạt động học trong 7 ngày tăng từ 24% lên 32%. |
| E | Tỷ lệ hoàn thành lộ trình có chất lượng trong 90 ngày chưa đủ dữ liệu để kết luận. |
| F | p95 mở bài giảm nhưng một nhóm dùng thiết bị cũ gặp lỗi nhiều hơn. |

### Bài tập 1 — Phân loại theo bốn tầng

**Hướng phân tích:**

- **A:** activity.
- **B:** output; số PBI Done là đầu ra của dòng thực hiện công việc, chưa tự chứng minh giá trị.
- **C:** tín hiệu tiếp cận output / adoption, có thể làm chỉ báo hỗ trợ outcome.
- **D:** outcome hành vi trong phạm vi định nghĩa, nhưng chưa chứng minh nhân quả.
- **E:** chỉ số outcome dài hạn hoặc impact tùy khung mục tiêu; hiện chưa có đủ cửa sổ quan sát.
- **F:** performance/quality guardrails; có rủi ro phân khúc dù một chỉ số chung tốt lên.

### Bài tập 2 — Tính mức thay đổi

**Câu hỏi:** từ 24% lên 32% thay đổi bao nhiêu?

**Đáp án:** tăng **8 điểm phần trăm**, tương đương khoảng **33,3% tương đối** so với mức 24% ban đầu. Không nên chỉ nói “tăng 8%” vì thiếu đơn vị diễn giải.

### Bài tập 3 — D đã đủ để tuyên bố tác động dài hạn?

**Hướng phân tích:** chưa. D chỉ đo một outcome trong 7 ngày. E chưa trưởng thành để đánh giá 90 ngày; còn nhiều yếu tố ngoài có thể ảnh hưởng. Cần ghi rõ giới hạn và tiếp tục kiểm tra.

### Bài tập 4 — Phản ứng thế nào với F?

**Hướng phân tích:** xem phạm vi và mức ảnh hưởng nhóm thiết bị cũ, chất lượng dữ liệu, tiêu chuẩn đã cam kết, các rủi ro quan trọng. Nếu rào cản có tác động đáng kể, cần khắc phục hoặc điều chỉnh kế hoạch mở rộng; không bỏ qua vì p95 tổng thể giảm.

### Bài tập 5 — Lựa chọn nghiên cứu tiếp theo

**Câu hỏi:** nếu adoption tăng nhưng tỷ lệ hoàn tất hoạt động học không tăng, đội nên làm gì?

**Gợi ý:** kiểm tra tính đúng của tiến độ, thời gian mở bài, trải nghiệm sau click, nhóm người dùng không được tiếp cận và tính phù hợp của nội dung. Có thể cần phỏng vấn hoặc thí nghiệm phù hợp, thay vì chỉ làm nút nổi bật hơn.

### Bài tập 6 — Phát hiện thiên lệch mẫu

**Câu hỏi:** đội chỉ tính những người đã nhấn nút để báo tỷ lệ “quay lại học”. Điều đó phản ánh gì?

**Gợi ý:** đó là tỷ lệ kết quả **có điều kiện trên việc đã click**, không phải tỷ lệ toàn cohort đủ điều kiện; còn chịu selection bias. Muốn đo hiệu quả tới nhóm mục tiêu, phải định nghĩa mẫu số phù hợp và xem cả người không thấy/không click.

## 24. Checklist trước khi sử dụng một metric

### Về mục tiêu và phân loại

- [ ] Chỉ số này hỗ trợ **quyết định nào**, cho ai?
- [ ] Nó đang đo **hoạt động, đầu ra, kết quả hay tác động**?
- [ ] Nếu chỉ số tăng, có chắc người dùng tốt hơn không? Nếu không, nó có phải proxy?
- [ ] Có mô tả được **chuỗi giả thuyết** từ công việc tới giá trị không?
- [ ] Mục tiêu có tách khỏi một giải pháp cụ thể để còn khả năng đổi hướng không?

### Về thiết kế dữ liệu

- [ ] Tử số, mẫu số, đơn vị và sự kiện được định nghĩa rõ?
- [ ] Cohort và cửa sổ thời gian có phù hợp hành vi không?
- [ ] Có so sánh cùng định nghĩa đo giữa baseline và kết quả không?
- [ ] Có xem người dùng chưa đủ cửa sổ quan sát không?
- [ ] Đã xác định sai số, sự kiện trùng/thiếu và cách kiểm tra nguồn dữ liệu chưa?
- [ ] Có xét phân khúc quan trọng mà không vi phạm quyền riêng tư không?
- [ ] Có phân biệt điểm phần trăm với phần trăm thay đổi tương đối không?

### Về diễn giải và hành động

- [ ] Có kiểm tra yếu tố ngoài, sự khác biệt cohort và thiên lệch lựa chọn?
- [ ] Khi nói về nhân quả, thiết kế đánh giá có cho phép kết luận tương ứng không?
- [ ] Có xem guardrails về chất lượng, bảo mật, khả năng truy cập, vận hành?
- [ ] Có thông tin định tính giúp hiểu **vì sao** thay đổi xuất hiện không?
- [ ] Có nêu giới hạn và độ không chắc chắn thay vì chỉ kết luận thắng/thua?
- [ ] Team có hành động rõ sau khi xem số liệu và kiểm tra lại tác động?
- [ ] Chỉ số có được dùng để **học hỏi**, không ép đánh đổi chất lượng hoặc xếp hạng cá nhân?

## 25. Những ngộ nhận cần tránh

| Ngộ nhận | Hệ quả | Cách nhìn đúng hơn |
|---|---|---|
| “Đã làm nhiều là đã tạo nhiều giá trị.” | Tăng công việc và họp nhưng bỏ qua người dùng. | Activity cần được nối với output, outcome và impact. |
| “Story Done = outcome.” | Nhầm tính năng đã giao với hành vi đã thay đổi. | Increment có giá trị tiềm năng; outcome cần bằng chứng sử dụng thực. |
| “Deploy nhiều là sản phẩm thành công.” | Tối ưu delivery mà không xem nhu cầu. | Deployment là năng lực hỗ trợ học hỏi, không thay thế outcome. |
| “Velocity là năng suất của các kỹ sư.” | So sánh sai, gây áp lực đổi ước lượng và bỏ chất lượng. | Dùng có chừng mực cho dự báo nội bộ, không xếp hạng người/đội. |
| “Mọi lượt click đều là giá trị.” | Khuyến khích thiết kế gây click nhưng không giải quyết nhu cầu. | Đo hành vi có ý nghĩa và tác động tới tác vụ. |
| “Outcome phải là doanh thu.” | Bỏ qua giá trị về trải nghiệm, khả năng tiếp cận và độ tin cậy. | Chọn kết quả phù hợp sứ mệnh sản phẩm. |
| “Impact xuất hiện ngay sau release.” | Đánh giá quá sớm, gán nguyên nhân vô căn cứ. | Tách thời gian và mức độ bằng chứng cho từng tầng. |
| “Tỷ lệ tăng 8%” khi từ 24% lên 32%. | Mơ hồ phần trăm và điểm phần trăm. | Báo tăng 8 điểm phần trăm, khoảng 33,3% tương đối. |
| “Mẫu số nào cũng được miễn biểu đồ đẹp.” | Quyết định sai do định nghĩa không nhất quán. | Định nghĩa cohort, sự kiện, đơn vị và cửa sổ trước. |
| “Sau release chỉ cần so trước–sau là kết luận nhân quả.” | Bỏ qua mùa vụ, thay đổi mẫu và yếu tố khác. | Đánh giá phù hợp, nói rõ giới hạn; thử nghiệm khi hợp lệ. |
| “Guardrail tốt là có cũng được.” | Outcome tăng nhưng chất lượng/an toàn xấu đi. | Bảo vệ các ràng buộc không thể đánh đổi. |
| “Metric càng nhiều càng tốt.” | Nhiều dashboard, không có quyết định. | Chọn ít phép đo hữu ích theo câu hỏi. |
| “Chỉ số thấp là lỗi cá nhân.” | Che giấu vấn đề hệ thống và giảm học hỏi. | Phân tích điều kiện làm việc, sản phẩm và dữ liệu. |
| “Chỉ báo sớm chắc chắn tạo tác động.” | Bị proxy dẫn dắt thay vì kiểm tra đích đến. | Kiểm tra và cập nhật quan hệ giữa leading signal với impact. |
| “Tối ưu từng bước funnel là tối ưu giá trị.” | Tạo click và thời gian sử dụng không cần thiết. | Xem primary outcome, guardrails và mục tiêu lâu dài. |
| “Một mẫu nhỏ không thấy lỗi nghĩa là an toàn.” | Bỏ qua độ không chắc chắn và nhóm ít được quan sát. | Xem phạm vi mẫu, kỹ thuật kiểm chứng và mức rủi ro. |

## 26. Kết luận

**Hoạt động (activity)** cho biết nhóm đang làm gì. **Đầu ra (output)** cho biết những khả năng hoặc hiện vật đã được tạo và bàn giao. **Kết quả (outcome)** cho biết hành vi, khả năng hoặc trải nghiệm của người dùng và tổ chức đã thay đổi như thế nào. **Tác động (impact)** cho biết những chuyển biến rộng và dài hạn mà kết quả ấy có thể đóng góp.

Bốn tầng liên kết trong một **giả thuyết tạo giá trị**, không phải một đường thẳng bảo đảm thành công. Muốn hiểu đúng, cần kết hợp **flow metrics, chất lượng Increment, adoption, outcome và guardrails**, đồng thời làm rõ cohort, tử số–mẫu số, cửa sổ thời gian, độ tin cậy và giới hạn của suy luận nhân quả.

Trong **AGILE_DEVELOPMENT**, Scrum giúp nhóm kiểm tra Product Goal và kết quả Increment, Kanban giúp cải thiện dòng công việc, XP và DevOps hỗ trợ chất lượng và khả năng bàn giao. Nhưng **điều quan trọng không phải có bao nhiêu ticket, điểm story, commit hay bản triển khai — mà là nhóm có học được điều gì, người dùng nhận được giá trị nào và sản phẩm góp phần tạo ra tác động có ích, bền vững hay không**.
