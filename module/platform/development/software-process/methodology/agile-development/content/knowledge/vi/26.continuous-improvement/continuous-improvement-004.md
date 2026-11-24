# Chọn vấn đề có tác động rõ và phạm vi thử nghiệm phù hợp

> **Chương:** Cải tiến liên tục  
> **Học phần:** **AGILE_DEVELOPMENT** — hiểu giá trị và nguyên tắc Agile trong phát triển phần mềm thích ứng nhờ phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để chọn cách phối hợp phù hợp.

Một nhóm phát triển phần mềm đặt lịch tư vấn kết thúc Sprint Retrospective với 18 ý tưởng: thay công cụ quản lý công việc, giảm số cuộc họp, chuyển toàn bộ hệ thống sang microservices, bổ sung kiểm thử tự động, tăng thời lượng review và đổi cấu trúc backlog. Mọi đề xuất đều nghe có vẻ hữu ích. Nhưng tháng sau, người dùng vẫn không biết lịch đã được xác nhận hay chưa, một số yêu cầu bị gửi lặp, còn các feature thường mắc ở hàng đợi kiểm thử.

Vấn đề không nhất thiết là nhóm thiếu ý tưởng. Nhóm có thể thiếu **cách chọn vấn đề quan trọng dựa trên bằng chứng**, thiếu một **giả thuyết cải tiến có thể bị bác bỏ** và thiếu **phạm vi thử nghiệm vừa đủ nhỏ để kiểm soát rủi ro nhưng đủ lớn để quan sát tác động**.

Trong Agile, **cải tiến liên tục (continuous improvement)** không có nghĩa làm càng nhiều thay đổi quy trình càng tốt. Đó là chuỗi hành động có chủ đích: nhìn thấy vấn đề, hiểu hệ thống, chọn điều đáng cải thiện, thiết kế thử nghiệm, xem kết quả và điều chỉnh. Mỗi lần thử cần giúp nhóm trả lời một câu hỏi có ích, không phải tạo thêm một quy định cố định khi chưa biết nó có hiệu quả không.

**Thông điệp trung tâm:** Hãy chọn **vấn đề có ảnh hưởng rõ tới người dùng, dòng công việc hoặc chất lượng**, rồi chọn **thử nghiệm nhỏ nhất có thể cung cấp bằng chứng đáng tin mà vẫn an toàn**. Thử nghiệm nhỏ không đồng nghĩa thử tùy tiện; vấn đề nghiêm trọng về dữ liệu, bảo mật hoặc an toàn cần được xử lý ngay theo trách nhiệm hiện hành.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt **triệu chứng, vấn đề, giả thuyết nguyên nhân và đề xuất giải pháp**.
2. Tìm vấn đề có tác động rõ qua dữ liệu người dùng, luồng công việc, chất lượng, rủi ro và phản hồi nhóm.
3. Đặt **ranh giới đo**, thu thập baseline, phân biệt dữ liệu mô tả với bằng chứng về nguyên nhân.
4. Chọn vấn đề ưu tiên bằng cách kết hợp **mức tác động, tần suất, chi phí trì hoãn, độ tin cậy bằng chứng, khả năng kiểm soát và công sức**, không chạy theo điểm số giả chính xác.
5. Viết một **giả thuyết cải tiến có thể bác bỏ**, kèm chỉ số kết quả, guardrails và tiêu chí dừng.
6. Thu hẹp **phạm vi thử nghiệm** theo số loại việc, công đoạn, nhóm tham gia, thời gian và mức độ phơi nhiễm của người dùng.
7. Vận dụng chu kỳ **Plan–Do–Study–Act (PDSA)**, 5 Whys, phân tích dòng giá trị và thực hành Scrum/Kanban/XP mà không lẫn công cụ với mục tiêu.
8. Đọc kết quả thử nghiệm thận trọng, quyết định **tiếp tục, điều chỉnh, mở rộng hoặc dừng** và đưa bài học vào cách làm hằng ngày.

## 2. Phân biệt bốn thứ dễ bị trộn lẫn

### 2.1. Triệu chứng không phải nguyên nhân

Nhóm thấy: **“Cycle time của user story tăng.”** Đây là **triệu chứng** có thể đo. Nó chưa chỉ rõ vấn đề bắt nguồn từ đâu. Nguyên nhân khả dĩ gồm WIP quá lớn, thiếu môi trường test, phụ thuộc API đối tác, review dồn cuối Sprint hoặc sự cố production kéo nhiều người ra khỏi luồng.

Người khác kết luận ngay: **“Phải họp Daily Scrum lâu hơn để phối hợp.”** Đó là **đề xuất giải pháp**, chưa phải kết luận từ bằng chứng. Nếu nút thắt thực là quyền truy cập môi trường kiểm thử, tăng thời gian họp có thể làm chậm thêm.

| Thành phần | Câu hỏi | Ví dụ trong hệ thống đặt lịch |
| --- | --- | --- |
| **Triệu chứng** | Điều gì đang được nhìn thấy? | Nhiều user story có work item age lớn và nằm ở cột Test. |
| **Vấn đề có tác động** | Ai chịu hệ quả gì, ở ranh giới nào? | Các lát cắt đặt lịch ra mắt chậm, khách tiếp tục phải gọi tổng đài. |
| **Giả thuyết nguyên nhân** | Điều gì có thể tạo ra vấn đề? | Môi trường test phải thiết lập thủ công, khiến story chờ nhiều ngày. |
| **Giải pháp/thử nghiệm** | Thay đổi nào sẽ kiểm tra giả thuyết? | Thử tạo dữ liệu test tự phục vụ cho một luồng đặt lịch. |

**Điều cần tránh:** Gọi “chúng ta cần microservices” là vấn đề. Đó là một phương án kiến trúc cần chứng minh liên hệ tới vấn đề, rủi ro và chi phí thay đổi hiện tại.

### 2.2. Một phát biểu vấn đề đủ tốt

Một cấu trúc thực dụng:

> **Đối tượng/luồng** + **điều đang xảy ra** + **hệ quả** + **bằng chứng và phạm vi đo**.

Ví dụ:

> “Trong bốn tuần gần đây, các thay đổi nhỏ ở luồng đặt lịch thường chờ tích hợp/kiểm thử lâu hơn thời gian phát triển, khiến phản hồi từ khách được xử lý muộn. Bảng flow và lịch sử hạng mục chỉ ra phần lớn thời gian chờ tập trung ở việc chuẩn bị môi trường test; chúng tôi cần xác minh đây có phải giới hạn chính trước khi đổi quy trình.”

Phát biểu này đủ cụ thể để tìm dữ liệu, nhưng **không tự khẳng định nguyên nhân đã được chứng minh**.

### 2.3. Ranh giới vấn đề quan trọng hơn tên công cụ

“Tăng năng suất Dev” có thể che việc QA đang quá tải. “Đóng nhiều ticket” có thể che lỗi chưa được người dùng xác nhận. Vấn đề cải tiến nên gắn với **toàn luồng giao giá trị** và **điều kiện chất lượng**, không chỉ hiệu suất cục bộ.

Hỏi:

1. Người dùng hoặc đồng nghiệp nào đang phải chờ hay chịu rủi ro?
2. Ranh giới bắt đầu/kết thúc đang đo là gì?
3. Kết quả mong muốn liên hệ thế nào với Product Goal hoặc nghĩa vụ vận hành?
4. Nếu bộ phận này nhanh hơn, bước tiếp theo có tiếp nhận được không?

### 2.4. Không phải vấn đề nào cũng cần thử nghiệm trước khi sửa

Nếu hệ thống đang tạo **hai lịch trùng giờ** hoặc làm lộ dữ liệu cá nhân, đó là vấn đề phải **triage và giảm thiệt hại ngay theo thẩm quyền**, không trì hoãn để thử “liệu có nên sửa hay không”.

Vòng cải tiến vẫn có chỗ đứng sau ứng cứu: tìm nguyên nhân hệ thống, kiểm tra hiệu lực biện pháp phòng ngừa và rút ngắn thời gian phát hiện/phục hồi. **Thử nghiệm cải tiến quy trình không được hợp thức hóa việc cố ý để lỗi nghiêm trọng tồn tại trên người dùng thật**.

## 3. Nhìn vấn đề từ các nguồn bằng chứng khác nhau

Một nhóm cải tiến hiệu quả không chỉ hỏi “mọi người thấy chỗ nào bất tiện?”; họ đối chiếu **trải nghiệm người dùng, số liệu vận hành, dữ liệu flow và phản hồi từ người làm công việc**.

### 3.1. Năm nguồn gợi ý

| Nguồn | Ví dụ | Giá trị | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| **Phản hồi người dùng** | Khách không hiểu Pending khác Confirmed. | Cho thấy nhu cầu và trải nghiệm thật. | Người nói nhiều nhất không tự đại diện toàn tập. |
| **Kết quả sản phẩm** | Tỷ lệ đặt lịch thành công, số lần phải gọi hỗ trợ. | Gắn vấn đề với outcome. | Có thể chịu tác động từ nhiều yếu tố. |
| **Flow metrics** | WIP, throughput, cycle time, work item age. | Hiện thời gian chờ và biến động công việc. | Phụ thuộc định nghĩa workflow, kích thước và loại việc. |
| **Chất lượng/vận hành** | Lỗi tạo trùng, sự cố, thời gian khôi phục, rollback. | Chỉ ra thiệt hại và rủi ro hệ thống. | Lỗi hiếm nhưng nặng có thể không hiện trong trung bình. |
| **Kinh nghiệm nhóm** | Reviewer thiếu quyền, test data khó tạo, quá nhiều ngắt việc. | Gợi ý cơ chế gây ma sát. | Là dữ liệu định tính cần làm rõ, không tự chứng minh nguyên nhân. |

Phản hồi và số liệu **không cần cùng nói một điều**. Một số liệu cho thấy chậm, cuộc phỏng vấn giúp giải thích cơ chế; mâu thuẫn giữa hai nguồn là cơ hội điều tra.

### 3.2. Quan sát từ công việc đã hoàn tất và còn đang mở

Nếu chỉ phân tích story đã Done, những story đang chờ lâu có thể bị che. Cần xem:

- Các hạng mục **còn mở** đang ở đâu và bao nhiêu ngày kể từ khi bắt đầu.
- Số việc bị chặn, nguyên nhân chặn và thời gian chờ.
- Những vòng lặp làm lại: review trả về, test fail, reopen bug.
- Phân bố cycle time của việc hoàn tất, không chỉ trung bình.
- Mức độ khẩn cấp, kích thước và loại việc có khác nhau giữa các kỳ không.

**Work item age** đặc biệt hữu ích để thấy vấn đề **trước khi** một mục được đóng và đi vào báo cáo cycle time lịch sử.

### 3.3. Quan sát cả chất lượng và khả năng phục hồi

Không nên chọn ưu tiên chỉ theo vấn đề có số lần xuất hiện cao nhất. **Một lỗi hiếm làm sai dữ liệu thanh toán** có thể quan trọng hơn một lỗi hiển thị xuất hiện nhiều lần nhưng ít ảnh hưởng. Xem:

- Mức nghiêm trọng và khả năng phát hiện sớm.
- Khả năng phục hồi và hậu quả không thể đảo ngược.
- Số người/tác vụ bị ảnh hưởng.
- Rủi ro an toàn, bảo mật, pháp lý và nghĩa vụ hợp đồng.
- Tần suất, xu hướng và khả năng tái diễn.

Các nghĩa vụ bắt buộc phải được giải quyết đúng thẩm quyền; không dùng công thức ưu tiên điểm số để hợp thức hóa việc trì hoãn khắc phục rủi ro không thể chấp nhận.

## 4. Baseline: biết hiện trạng trước khi hứa cải thiện

### 4.1. Bắt đầu bằng định nghĩa nhất quán

Giả sử nhóm báo **“cycle time trung bình là sáu ngày”**. Cần hỏi:

- Khi nào tính **started**: lúc Product Owner chọn story, lúc Developer kéo vào In Progress hay lúc viết code?
- Khi nào tính **finished**: merge code, đạt DoD, deploy hay người dùng sử dụng được?
- “Ngày” là ngày lịch hay ngày làm việc?
- Có tính blocked và việc bị trả về không?
- Có trộn feature lớn với bug nhỏ, các nhóm khác nhau hoặc việc khẩn không?

Không có ranh giới chung, so sánh trước/sau dễ trở thành **so hai chỉ số khác nhau**.

### 4.2. Một bảng baseline minh họa

Giả sử một nhóm xem các user story nhỏ thuộc luồng đặt lịch trong bốn tuần; số dưới đây là **dữ liệu giả định để học**, không phải quan sát thực tế:

| Tín hiệu | Baseline minh họa | Câu hỏi tiếp |
| --- | ---: | --- |
| Throughput | 4 story/tuần | Các story có kích thước/loại tương tự không? |
| WIP trung bình | 12 story | Tồn đọng tập trung ở đâu? |
| Cycle time trung vị | 13 ngày | Phân bố và các trường hợp đuôi dài ra sao? |
| Work item age lớn nhất còn mở | 22 ngày | Hạng mục này đang bị chặn vì điều gì? |
| Thời gian chờ review trung vị | 3 ngày | Chờ năng lực, quyền, hay thiếu ngữ cảnh? |
| Thời gian chờ môi trường test trung vị | 4 ngày | Có tạo dữ liệu test tự phục vụ được không? |
| Lỗi hồi quy nghiêm trọng sau phát hành | 2 sự cố | Phân loại, mức độ và gốc rễ? |

Đừng tối đa hóa throughput rồi gọi mọi cải tiến là thành công. Nếu cycle time giảm nhưng lỗi hồi quy tăng mạnh, nhóm có thể đã **dịch chi phí từ phát triển sang người dùng**.

### 4.3. Quan hệ giữa WIP, throughput và thời gian

Trong hệ thống dòng **đủ ổn định**, định luật Little cho quan hệ trung bình:

\[
\text{WIP trung bình}=\text{Throughput trung bình}\times\text{Thời gian trung bình trong hệ thống}
\]

Nếu WIP trung bình là **12 story**, throughput trung bình **4 story/tuần**, mô hình cho thời gian trung bình xấp xỉ **3 tuần/story**. Đây là **trung bình** trong ranh giới nhất quán, **không phải** lời hứa mọi story đều xong trong ba tuần.

Nếu nhóm giảm WIP bằng cách chuyển nhiều story sang cột “đã kết thúc đo nhưng vẫn chờ release”, chỉ số đẹp lên nhưng **người dùng không nhận giá trị sớm hơn**. Ranh giới đo cần bao gồm các điểm chờ có ý nghĩa, hoặc công khai chỉ số nào dừng trước phát hành.

### 4.4. Chọn baseline đủ đại diện

Một ngày duy nhất có sự cố lớn chưa chắc phản ánh giới hạn thường xuyên. Nhưng cũng không được xóa sự cố khỏi dữ liệu chỉ vì “ngoại lệ không đẹp”. Ghi:

- Khoảng thời gian và số hạng mục được quan sát.
- Khác biệt loại việc, nghỉ phép, chiến dịch hoặc phát hành lớn.
- Dữ liệu thiếu hay thay đổi cách tracking.
- Những trường hợp đặc biệt cần xem riêng.

**Baseline không cần hoàn hảo** mới bắt đầu một thử nghiệm ít rủi ro, nhưng phải **đủ rõ để không tạo kết luận sai** khi xem kết quả.

## 5. Tìm nguyên nhân: quan sát cơ chế, tránh đổ lỗi cá nhân

### 5.1. Value Stream Mapping ở mức vừa đủ

Một bản đồ dòng giá trị giúp thấy thời gian **xử lý** và **chờ đợi** từ yêu cầu tới giao giá trị.

~~~mermaid
flowchart LR
    A["Nhu cầu / story được ưu tiên"] --> B["Làm rõ"]
    B --> C["Phát triển và test sớm"]
    C --> D["Chờ review"]
    D --> E["Kiểm thử tích hợp"]
    E --> F["Chờ phát hành"]
    F --> G["Người dùng nhận giá trị"]
    G -. "Phản hồi" .-> A
~~~

Nếu test tích hợp là nút thắt, tăng số story bắt đầu ở Development thường chỉ tăng hàng đợi. **Tối ưu cục bộ** không đảm bảo luồng tốt. Trước khi chọn thử nghiệm, hãy hỏi **bước nào đang giới hạn khả năng hoàn tất** và **có bằng chứng gì**.

### 5.2. Five Whys là công cụ hỏi, không phải máy xác định nguyên nhân

Một chuỗi **5 Whys** minh họa:

1. **Vì sao** story thường chờ test? → Môi trường chưa sẵn.
2. **Vì sao** môi trường chưa sẵn? → Cần tạo thủ công dữ liệu lịch hẹn.
3. **Vì sao** phải tạo thủ công? → Không có fixture an toàn và tự phục vụ.
4. **Vì sao** chưa có fixture? → Công việc cải thiện môi trường không được làm rõ tác động.
5. **Vì sao** chưa làm rõ? → Nhóm chỉ đo thời gian coding, không đo chờ end-to-end.

Chuỗi trên **là giả thuyết cần kiểm chứng**, không phải kết luận rằng “gốc rễ chắc chắn nằm ở bước số 5”. Một vấn đề có thể có nhiều nguyên nhân đồng thời; số lần hỏi **không nhất thiết đúng năm**. Cần đối chiếu log, dữ liệu công việc, quan sát và thử thay đổi nhỏ.

### 5.3. Phân tích nguyên nhân mang tính hệ thống

| Cách nói quy lỗi | Câu hỏi mang tính hệ thống |
| --- | --- |
| “QA làm chậm nhóm.” | QA đang chờ dữ liệu/môi trường/quyền gì, WIP tới bước này có vượt năng lực không? |
| “Reviewer thiếu trách nhiệm.” | Quy tắc review có rõ, PR có quá lớn, có người dự phòng, thời gian bị ngắt việc ra sao? |
| “Developer viết lỗi quá nhiều.” | Có tiêu chí chấp nhận, test sớm, CI và phản hồi chất lượng ở vị trí nào? |
| “Product Owner đổi ý liên tục.” | Có giả định nào chưa xác minh, stakeholder có được xem Increment sớm và ưu tiên có rõ không? |

Tôn trọng con người không đồng nghĩa bỏ qua trách nhiệm. Nó có nghĩa **đánh giá nguyên nhân và thiết kế điều kiện làm việc**, không dùng một điểm dữ liệu làm cơ sở quy chụp cá nhân.

### 5.4. Phân biệt nguyên nhân gốc với điểm đòn bẩy

Nhóm không nhất thiết phải giải quyết **toàn bộ gốc rễ lịch sử** để cải tiến hữu ích. Có thể có nhiều nguyên nhân tạo hàng đợi; thay chính sách WIP hoặc tạo dữ liệu test tự phục vụ có thể **giảm ảnh hưởng rõ** trước khi mọi hệ thống cũ được sửa xong.

**Điểm đòn bẩy** là thay đổi nhỏ có khả năng tác động lên dòng/giá trị đủ lớn. Để chọn điểm ấy, vẫn cần giữ an toàn, đo hệ quả và biết giới hạn của giả thuyết.

## 6. Đặt tác động rõ hơn “ý tưởng nghe hay”

### 6.1. Ba lớp tác động

| Lớp | Câu hỏi | Tín hiệu |
| --- | --- | --- |
| **Người dùng / sản phẩm** | Khách có hoàn thành tác vụ hữu ích, ít lỗi hoặc ít phải nhờ hỗ trợ hơn? | Completion rate, khiếu nại, trải nghiệm sử dụng, tác động đến Product Goal. |
| **Dòng công việc** | Nhóm đưa thay đổi có ích từ ưu tiên tới sử dụng nhanh và dự báo tốt hơn không? | WIP, cycle time, throughput, blocked, lead time, work item age. |
| **Chất lượng và bền vững** | Nhóm có duy trì chuẩn chất lượng, độ tin cậy và năng lực thay đổi tiếp không? | Sự cố, lỗi hồi quy, thời gian phục hồi, công việc khẩn, mệt mỏi. |

Một vấn đề đáng chọn thường có **tác động quan trọng ở ít nhất một lớp** và không được tạo tác động xấu khó chấp nhận ở các lớp khác.

### 6.2. Tác động không đồng nghĩa số lần lặp

Một lỗi hiển thị nhỏ xảy ra mỗi ngày có thể ít nghiêm trọng hơn một lỗi dữ liệu xuất hiện mỗi tháng. Ngược lại, hàng nghìn lần người dùng không hiểu trạng thái Pending có thể tích lũy thành rất nhiều thời gian và hỗ trợ.

Để đánh giá cần xem:

1. **Mức độ nghiêm trọng** nếu vấn đề xảy ra.
2. **Tần suất/xác suất** và xu hướng.
3. **Số người, tác vụ hoặc nhóm** bị ảnh hưởng.
4. **Khả năng phát hiện và phục hồi**.
5. **Chi phí trì hoãn** nếu không hành động.
6. **Mức tin cậy của bằng chứng** hiện có.

Với rủi ro an toàn và nghĩa vụ bắt buộc, thực hiện triage phù hợp trước khi dùng điểm ưu tiên tương đối.

## 7. Chọn vấn đề ưu tiên khi nguồn lực cải tiến có hạn

### 7.1. Bộ câu hỏi trước khi xếp hạng

Nhóm thường có nhiều vấn đề cùng lúc. Thay vì bình chọn “vấn đề được yêu thích nhất”, hãy hỏi:

1. **Tác động nào đã được thấy?** Liên hệ tới người dùng, Product Goal, dòng hoặc rủi ro.
2. **Quy mô ảnh hưởng?** Một trường hợp cá biệt, một phân đoạn hay nhiều nhóm?
3. **Độ cấp bách/chi phí trì hoãn?** Vấn đề đang gây thiệt hại hoặc khóa công việc quan trọng không?
4. **Bằng chứng có đáng tin?** Có dữ liệu, quan sát và giới hạn rõ không?
5. **Nhóm có thể tác động?** Có quyền đổi workflow, hệ thống test hoặc cần quyết định liên đội?
6. **Có thể học bằng thử nhỏ?** Có giải pháp ít rủi ro, đảo ngược được, đo được không?
7. **Công sức và chi phí cơ hội?** Nếu dành một Sprint cải tiến, feature nào phải chờ?

Các câu hỏi này phục vụ thảo luận. **Không phải mọi vấn đề đều cần một bảng điểm phức tạp**, và mức tác động của sự cố nghiêm trọng không nên bị hạ vì khó thử hoặc thiếu điểm “ease”.

### 7.2. Một ma trận ưu tiên minh họa

Giả sử nhóm có bốn vấn đề; đánh giá dưới đây là **giả định**:

| Vấn đề ứng viên | Tác động hiện tại | Độ tin cậy bằng chứng | Khả năng thử nhỏ/an toàn | Hướng quyết định |
| --- | --- | --- | --- | --- |
| Story chờ môi trường test nhiều ngày | Cao với dòng phát hành; backlog chậm | Có timestamps và nhiều trường hợp | Khá cao: thử fixture ở một luồng | **Ưu tiên thử trước** nếu không có sự cố cấp bách hơn. |
| Quá nhiều cuộc họp dài | Chưa rõ tác động lên flow | Chủ yếu là ý kiến | Cao: thử thay format họp | Đo ma sát thật, tránh bỏ cuộc họp đang giải quyết phụ thuộc. |
| Muốn chuyển toàn bộ sang microservices | Lợi ích chưa chứng minh; rủi ro lớn | Thấp: chưa có dependency analysis | Thấp nếu chuyển cả hệ thống | Chưa cam kết; xác định vấn đề kiến trúc cụ thể rồi thử tách một ranh giới. |
| Retry gây lịch trùng ở production | Tác động dữ liệu cao, nguy cơ thiệt hại | Đã xác minh lỗi | Không được thử bằng cách để bug tiếp diễn | **Ứng cứu và sửa theo mức nghiêm trọng**, kiểm chứng an toàn. |

Không thể so sự cố dữ liệu với cải tiến tiện ích bằng cùng một phép cộng điểm đơn giản. Triage cấp bách và cải tiến thường xuyên nên có **chính sách riêng nhưng cùng nhìn tổng năng lực và giá trị**.

### 7.3. Impact–Confidence–Effort: công cụ hỗ trợ, không phải chân lý

Một bảng đơn giản có thể dùng ba trục:

- **Impact:** Nếu vấn đề giảm, kết quả nào có khả năng tốt lên và mức đáng kể ra sao?
- **Confidence:** Bằng chứng hiện tại củng cố nhận định tới đâu?
- **Effort:** Công sức để thử và triển khai, kể cả test, hỗ trợ và phối hợp.

Có thể phân loại **Cao / Vừa / Thấp** thay vì gán số chính xác. Nếu cần điểm số, phải công khai đây là **heuristic để sắp thứ tự thảo luận**, không phải ước lượng ROI thực hoặc chứng minh lợi ích.

Một vấn đề có tác động tiềm năng cao nhưng confidence thấp có thể đáng làm **discovery/spike ngắn trước**, thay vì bỏ qua vĩnh viễn. Một việc nhỏ dễ làm không nên được ưu tiên chỉ vì điểm effort thấp.

### 7.4. RICE, WSJF và những gì điểm số bỏ sót

Nhóm có thể gặp **RICE** (Reach, Impact, Confidence, Effort) hoặc **WSJF** (Weighted Shortest Job First, thường liên hệ chi phí trì hoãn và kích thước công việc) trong lập thứ tự ưu tiên. Chúng có thể giúp trao đổi khi **định nghĩa đầu vào nhất quán**, nhưng dễ tạo **độ chính xác giả** nếu mọi con số chỉ là cảm tính.

Ví dụ, “Reach = 10.000” không có nghĩa đã xác minh 10.000 người sẽ hưởng lợi. “Tác động = 3” không có đơn vị khoa học nếu nhóm không nêu cách chấm. Các yếu tố an toàn, pháp lý, phụ thuộc và độ bất định phải được xét riêng khi cần.

**Quy tắc thực dụng:** Dùng điểm số để **nêu những giả định đang tranh luận** chứ không che chúng. Nếu thiếu dữ liệu quan trọng, một thử nghiệm nhỏ để giảm bất định có thể có giá trị hơn tính điểm ngày càng tinh vi.

### 7.5. Khi nào không cần thêm thang điểm?

Nếu ba người cùng thấy **một bước review chờ bốn ngày vì chỉ có một người được quyền duyệt**, dữ liệu lặp nhiều kỳ và có một cách thử ít rủi ro (reviewer dự phòng cho một loại PR), nhóm có thể thực hiện thử ngay với guardrail rõ. Tạo thêm buổi chấm điểm có thể chỉ tăng thời gian chờ.

## 8. Thu hẹp phạm vi thử nghiệm: đủ nhỏ để an toàn, đủ lớn để học

**Thử nghiệm cải tiến** là một thay đổi có giới hạn nhằm kiểm tra giả thuyết. Phạm vi hợp lý là **mức nhỏ nhất vẫn có thể tạo bằng chứng về quyết định cần đưa ra**, không phải lúc nào cũng là một người trong một ngày.

### 8.1. Năm chiều để giới hạn

| Chiều giới hạn | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Loại công việc** | Chỉ thử trên hạng mục nào? | Story nhỏ thuộc luồng đặt lịch, không áp cho incident bảo mật. |
| **Bước workflow** | Đổi một chính sách ở đâu? | Chỉ thử chuẩn bị dữ liệu test trước bước kiểm thử tích hợp. |
| **Nhóm/người tham gia** | Ai cần phối hợp và ai có quyền quyết định? | Một nhóm sản phẩm và người sở hữu test environment. |
| **Thời gian** | Bắt đầu, thời điểm xem lại, timebox? | Hai tuần theo lịch, không tự kéo dài vô hạn. |
| **Mức phơi nhiễm người dùng/hệ thống** | Dùng sandbox, nội bộ, pilot hay production? | Bắt đầu với môi trường test, không đụng dữ liệu thật. |

Có thể giới hạn thêm **khung giờ, thiết bị, quy mô dữ liệu, quyền truy cập hoặc vùng chức năng** nếu điều đó giúp an toàn và đánh giá đúng vấn đề.

### 8.2. “Nhỏ” không phải lúc nào cũng đo được

Một nhóm thử WIP limit trong **một giờ** rồi kết luận không có tác dụng có thể đã chọn cửa sổ quá ngắn để hạng mục di chuyển qua workflow. Ngược lại, thay toàn bộ quy trình công ty trong sáu tháng khiến khó biết cải tiến nào có hiệu lực.

Chọn thời lượng và số trường hợp theo:

- **Tốc độ xuất hiện dữ liệu:** Trong hai tuần, có đủ loại việc đi qua bước cần quan sát không?
- **Độ trễ tác động:** Một thay đổi test automation có thể cần nhiều lần tích hợp để thấy lợi ích.
- **Rủi ro của thay đổi:** Thay chính sách review khác thay giao dịch tiền.
- **Mức biến động:** Nghỉ lễ, outage, thay người hoặc chiến dịch lớn có làm dữ liệu nhiễu?
- **Khả năng đảo ngược:** Nếu không tốt, có thể trở về chính sách cũ mà không gây lỗi dữ liệu không?

**Không dùng một số ngày cố định cho mọi thử nghiệm.** Timebox có ý nghĩa khi giúp nhóm **xem lại quyết định**, chứ không phải đợi hết hạn dù đã có sự cố.

### 8.3. Chọn một biến thay đổi chính khi có thể

Nếu đồng thời thay công cụ review, WIP limit, cách ước lượng, cơ cấu nhân sự và lịch release, thấy cycle time thay đổi vẫn khó quy kết **điều gì tạo ra kết quả**.

Trong điều kiện thực tế, không phải lúc nào cũng cô lập một biến. Tuy vậy, có thể:

1. Thử **một chính sách chính** trong một phạm vi hẹp.
2. Ghi rõ những thay đổi khác diễn ra cùng kỳ.
3. Giữ nhất quán ranh giới và cách đo.
4. Nếu có thể, so với luồng/nhóm tương đương mà không gây bất công hoặc rủi ro.
5. Báo cáo **mức chắc chắn và yếu tố nhiễu**, không tự tuyên bố nhân quả.

### 8.4. Không thử trên người dùng thật khi chưa bảo vệ an toàn

Với lỗi tạo lịch trùng, không được mở beta cố tình để lỗi xảy ra nhằm “đủ mẫu”. Có thể thử fix bằng:

- Unit test cho quy tắc và trạng thái.
- Integration test với nhiều yêu cầu đồng thời.
- Môi trường sandbox kiểm tra retry/timeout.
- Đối soát dữ liệu sau sửa trong điều kiện an toàn.
- Phát hành có kiểm soát sau khi đã qua các điều kiện chất lượng.

**Thử nghiệm nhỏ** trong cải tiến quy trình và **thử nghiệm ngẫu nhiên với hành vi rủi ro cao** là hai khái niệm khác nhau. Không đánh đổi quyền lợi người dùng để lấy nhanh dữ liệu.

## 9. Giả thuyết cải tiến và điều kiện để nó bị bác bỏ

### 9.1. Từ mong muốn thành giả thuyết

**Mong muốn:** “Review phải nhanh hơn.”

**Giả thuyết tốt hơn:**

> “Trong hai tuần, nếu hai người đủ năng lực luân phiên review các PR nhỏ thuộc luồng đặt lịch và giới hạn số PR chờ, thời gian chờ review của loại PR này sẽ giảm, trong khi lỗi hồi quy và thời gian hoàn tất toàn dòng không xấu đi.”

Giả thuyết này chỉ ra:

1. **Đối tượng:** PR nhỏ thuộc một luồng.
2. **Can thiệp:** reviewer dự phòng và chính sách giới hạn việc đang chờ.
3. **Kết quả kỳ vọng:** giảm thời gian chờ review.
4. **Thước đo đối trọng:** lỗi hồi quy và cycle time end-to-end.
5. **Phạm vi/timebox:** hai tuần, không áp toàn hệ thống.

### 9.2. Mẫu phiếu thử nghiệm

~~~yaml
improvement_id: "IMP-04"
problem: "Story đặt lịch chờ môi trường test quá lâu"
evidence: "Nhiều hạng mục cùng loại bị blocked tại Integration Test"
assumed_cause: "Dữ liệu test phải chuẩn bị thủ công"
hypothesis: "Dữ liệu test tự phục vụ giảm thời gian chờ"
intervention: "Thử fixture an toàn cho một loại story"
scope:
  work_item: "Story nhỏ thuộc luồng đặt lịch"
  environment: "Test sandbox, không dùng dữ liệu production"
  team: "Một team và người phụ trách môi trường"
  timebox: "Hai tuần làm việc, xem lại theo số hạng mục"
baseline: "Thời gian chờ test và cycle time cùng ranh giới"
primary_signal: "Phân bố thời gian chờ trước khi test bắt đầu"
guardrails:
  - "Không giảm độ tin cậy của bộ kiểm thử"
  - "Không tăng lỗi do dữ liệu giả không đại diện"
  - "Không lộ dữ liệu cá nhân vào test"
stop_condition: "Có sự cố dữ liệu/bảo mật hoặc fixture sai nghiêm trọng"
review_decision: "Giữ, sửa, mở rộng, hoặc dừng dựa trên bằng chứng"
~~~

Đây là **mẫu minh họa**. Trước khi thực hiện phải xác nhận người có quyền thay đổi môi trường, chuẩn chất lượng và cách xử lý khi test data sai. Không tự ý tạo tài nguyên hoặc thay chính sách cấp tổ chức nếu chưa có thẩm quyền.

### 9.3. Ba loại tín hiệu cần có

| Loại | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Chỉ số chính (primary outcome)** | Cái gì phải thay đổi nếu giả thuyết đúng? | Thời gian chờ tạo dữ liệu test giảm. |
| **Chỉ số toàn hệ thống** | Người dùng/flow có tốt hơn không? | Cycle time từ story started tới đạt Done hoặc release. |
| **Guardrails** | Điều gì không được xấu đi? | Lỗi dữ liệu, hồi quy, bảo mật, nhịp bền vững. |

Không cố tối đa hóa một chỉ số chính bằng cách chuyển chi phí sang bước sau. Nếu review nhanh hơn nhưng PR thiếu kiểm thử và production lỗi nhiều hơn, thử nghiệm **không thành công theo mục tiêu hệ thống**.

### 9.4. Tiêu chí dừng và điều chỉnh phải có trước

Một thử nghiệm quy trình ít rủi ro có thể dừng khi **quá nhiều việc bị chặn** hoặc mức công sức tăng nhưng không có tín hiệu ích lợi. Thử nghiệm liên quan dữ liệu người dùng phải có tiêu chí dừng rõ theo **lỗi, quyền riêng tư, tính đúng đắn và khả năng khôi phục**.

**Không cần đợi hết timebox nếu đã có bằng chứng về thiệt hại.** Timebox là khung ra quyết định, không phải giấy phép duy trì rủi ro tới ngày kết thúc.

## 10. Đánh giá độ an toàn và khả năng đảo ngược trước khi thử

### 10.1. Phân nhóm theo khả năng đảo ngược

| Loại thử | Ví dụ | Khả năng quay lại | Cần chú ý |
| --- | --- | --- | --- |
| **Thay đổi cách phối hợp** | Reviewer dự phòng cho một loại PR. | Thường có thể trở về chính sách cũ. | Không bỏ review bắt buộc, đo tải và chất lượng. |
| **Thay đổi công cụ nội bộ** | Tạo fixture test tự phục vụ ở sandbox. | Thường tương đối dễ, nếu cô lập. | Dữ liệu giả phải đúng và không chứa thông tin thật. |
| **Thay đổi cách nhìn dashboard** | Hiển thị work item age ở cột Blocked. | Dễ đảo ngược về giao diện. | Không giấu vấn đề bằng cách đổi định nghĩa đo. |
| **Thay đổi giao diện người dùng** | Làm rõ trạng thái Pending. | Có thể tắt hiển thị, nhưng chưa chắc khôi phục trải nghiệm đã xảy ra. | Test khả năng dùng và tránh thông tin sai. |
| **Thay đổi dữ liệu/giao dịch** | Sửa cơ chế giữ chỗ hoặc migration. | Có thể không đảo ngược hoàn toàn. | Transaction, rollback/compensation, kiểm tra nhất quán. |
| **Thay đổi tổ chức quy mô lớn** | Chia lại team, đổi toàn bộ quy trình. | Chi phí đảo ngược cao. | Nên thử giới hạn, có đối thoại và thẩm quyền rõ. |

Một **feature flag** có thể tắt một chức năng, nhưng không thu hồi được email đã gửi, giao dịch đã lưu hoặc quyết định người dùng đã đưa ra. Đánh giá **hậu quả thực tế**, không chỉ khả năng hoàn tác commit.

### 10.2. Xác định blast radius

**Blast radius** là phạm vi có thể chịu ảnh hưởng nếu thay đổi sai. Trong cải tiến nhóm, nó có thể là:

- Một loại công việc hay toàn backlog?
- Một team hay hàng chục đội phụ thuộc?
- Một môi trường sandbox hay toàn production?
- Một số người dùng tình nguyện hay toàn bộ khách?
- Một cơ chế phục vụ ít rủi ro hay luồng tài chính/dữ liệu quan trọng?

**Phạm vi phù hợp** là phạm vi đủ bộc lộ cơ chế cần học nhưng không mở rộng rủi ro ngoài khả năng kiểm soát. Một thử nghiệm chỉ trên một cá nhân chưa chắc cho thấy thay đổi quy tắc WIP của cả team; một pilot toàn tổ chức lại quá lớn để học an toàn.

### 10.3. Phân biệt safe-to-fail với fail-safe

**Safe-to-fail probe** là thử nghiệm được thiết kế để **nếu giả thuyết sai vẫn giới hạn được thiệt hại**; không có nghĩa thử nghiệm không thể thất bại.

**Fail-safe design** là hệ thống được thiết kế để khi có lỗi vẫn chuyển về trạng thái an toàn theo điều kiện nghiệp vụ. Ví dụ, khi không rõ đối tác đã nhận lệnh đặt lịch hay chưa, không tự động xác nhận thất bại rồi cho gửi thêm một lệnh tạo lịch khác không được bảo vệ.

Hai tư tưởng bổ sung nhau: thử nghiệm cải tiến nên ở phạm vi safe-to-fail, còn hệ thống được thử vẫn cần các cơ chế fail-safe và kiểm tra chất lượng cần thiết.

### 10.4. Dừng thử không phải thất bại của người đề xuất

Nếu một giải pháp không đạt giả thuyết, **nhóm có thêm hiểu biết về hệ thống**. Điều cần đánh giá là:

- Có câu hỏi rõ và phép đo phù hợp không?
- Có bảo vệ người dùng, dữ liệu và chất lượng không?
- Có ghi nhận bằng chứng trái dự đoán không?
- Có chuyển bài học thành quyết định tiếp theo không?

Một thử nghiệm bị dừng sớm vì guardrail quan trọng có thể là **thực hành quản trị rủi ro tốt**. Ngược lại, kéo dài giải pháp không hiệu quả để bảo vệ ý kiến ban đầu là một phản mẫu.

## 11. Vòng Plan–Do–Study–Act (PDSA) và nhịp Kaizen

**PDSA** là một khung cải tiến theo vòng học: **Plan (lập kế hoạch) → Do (thử) → Study (nghiên cứu kết quả) → Act (điều chỉnh/chuẩn hóa)**. Nhiều tài liệu cũng dùng tên PDCA (Plan–Do–Check–Act); cả hai nhấn mạnh vòng cải tiến, nhưng từ **Study** đặc biệt gợi ý **học từ dữ liệu và các dự đoán**, không chỉ kiểm tra đã tuân thủ kế hoạch.

### 11.1. Plan — một câu hỏi đáng học

Ghi rõ:

1. Vấn đề và baseline.
2. Giả thuyết nguyên nhân và thay đổi đề xuất.
3. Đối tượng, phạm vi/timebox và người có quyền quyết định.
4. Dự đoán có thể kiểm tra.
5. Chỉ số kết quả, guardrails, cách ghi nhận dữ liệu.
6. Tiêu chí dừng hoặc quay lại.

**Không cần tài liệu vài chục trang** cho thử nghiệm workflow nhỏ. Một trang minh bạch là đủ khi rủi ro thấp, câu hỏi rõ và mọi người thống nhất.

### 11.2. Do — thử nhỏ và ghi điều thực sự xảy ra

Trong khi thực hiện:

- Ghi thời điểm bắt đầu, loại việc áp dụng và ngoại lệ.
- Không tự mở rộng sang mọi nhóm giữa chừng rồi vẫn gọi đó là một thử nghiệm nhỏ.
- Ghi sự cố, nghỉ phép, thay đổi thành phần team hoặc bất cứ biến số đáng kể nào.
- Theo dõi công việc chưa hoàn tất, không chỉ ticket đã Done.
- Dừng và xử lý nếu có điều kiện an toàn bị vi phạm.

Một thay đổi quy trình có thể cần mọi người hiểu **chính sách mới**. Nếu nửa team áp dụng WIP limit, nửa team không biết, kết quả phản ánh cả vấn đề truyền đạt, không chỉ tác dụng của WIP.

### 11.3. Study — so dữ liệu với dự đoán, không chỉ với mong muốn

Sau thử:

- Dự đoán nào đúng, sai hoặc chưa đủ bằng chứng?
- Điều gì thay đổi ở **chỉ số chính**, **toàn dòng** và **guardrails**?
- Số hạng mục đủ để nhận xét ở mức nào?
- Có biến số nhiễu, nhóm đối tượng khác, dữ liệu thiếu?
- Có phát sinh chi phí phối hợp mà chưa tính?
- Những trường hợp ngoại lệ dạy điều gì?

**Đừng kết luận nhân quả từ tương quan yếu.** Một cải thiện sau khi thay chính sách có thể do loại việc dễ hơn hoặc số người tham gia khác. Báo kết quả đúng mức tin cậy, rồi thử tiếp khi cần.

### 11.4. Act — giữ, thích ứng, mở rộng hoặc dừng

| Kết quả | Quyết định có thể phù hợp |
| --- | --- |
| Tín hiệu cải thiện ổn, guardrails được giữ | Duy trì trong phạm vi thử, xem cần chuẩn hóa/mở rộng có kiểm soát. |
| Có lợi ích nhưng chi phí mới tăng | Điều chỉnh chính sách, thử lại theo giả thuyết mới. |
| Dữ liệu chưa đủ/định nghĩa sai | Sửa cách đo, kéo thêm một vòng khi đáng đầu tư. |
| Không có lợi ích và đã kiểm chứng phù hợp | Dừng, ghi bài học và chuyển sang phương án khác. |
| Phát sinh rủi ro nghiêm trọng | Dừng mở rộng, giảm thiệt hại/ứng cứu theo thẩm quyền. |

**Act không nhất thiết là “mở rộng”.** Dừng một biện pháp không hiệu quả là một kết quả hữu ích, bởi nhóm giải phóng năng lực cho vấn đề có tác động lớn hơn.

### 11.5. Kaizen: cải tiến là năng lực của cả nhóm

Tinh thần **Kaizen** khuyến khích mọi người tham gia phát hiện lãng phí, thử cải tiến có trách nhiệm và học thường xuyên. Nó không có nghĩa mỗi thành viên phải đề xuất một ý tưởng mỗi ngày.

Một nhóm có thể cải tiến một chính sách nhỏ mỗi vài tuần, bảo đảm đã đo/hiểu kết quả trước khi tạo thêm nhiều thay đổi chồng chéo. **Nhịp cải tiến bền vững** quan trọng hơn số lượng “action item” sau retrospective.

## 12. Ví dụ xuyên suốt: chọn một nút thắt và thử cải tiến vừa đủ

Toàn bộ dữ liệu trong tình huống sau là **giả định để luyện tập**, không phải kết quả khảo sát hay dự báo cho một nhóm thật.

### 12.1. Bối cảnh

Một Scrum Team xây ứng dụng đặt lịch tư vấn. Product Goal của họ là **khách có thể đặt và quản lý lịch đáng tin, ít cần gọi tổng đài**. Nhóm có Developers, Product Owner, Scrum Master và người có chuyên môn kiểm thử/vận hành cùng cộng tác.

Trong Retrospective, nhóm ghi nhận:

1. Story thường chờ nhiều ngày trước kiểm thử tích hợp.
2. Một số pull request quá lớn nên review chậm.
3. Các cuộc họp kéo dài và nhiều người thấy khó tập trung.
4. Nhiều stakeholder yêu cầu chuyển sang microservices.
5. Một lỗi gửi lặp vừa được phát hiện trong môi trường test, nhưng chưa thấy lỗi production.

Nếu chọn ngay ý tưởng “dễ thống nhất nhất”, nhóm có thể đổi công cụ họp mà **không cải thiện việc giao tính năng đặt lịch**. Nhưng nếu vội chuyển toàn bộ kiến trúc sang microservices, nhóm có thể tạo chương trình thay đổi rủi ro lớn khi chưa biết điểm nghẽn thật.

### 12.2. Triage rủi ro trước khi chọn cải tiến

Nhóm tách **lỗi gửi lặp có nguy cơ sai dữ liệu** khỏi danh sách cải tiến workflow:

- Kiểm tra có ảnh hưởng production hay không.
- Viết kiểm thử tái hiện, bảo vệ bất biến idempotency và xử lý theo mức nghiêm trọng.
- Không dùng khách thật để “xác minh xem lỗi có xảy ra nhiều không”.
- Sau khi lỗi được quản lý an toàn, xem nguyên nhân kỹ thuật và năng lực phát hiện trong vòng cải tiến thích hợp.

**Không trộn công việc ứng cứu bắt buộc với phiếu bầu ý tưởng Retrospective.** Sau triage, nhóm mới chọn một thử nghiệm workflow có thể thực hiện an toàn.

### 12.3. Thu thập baseline cho một loại hạng mục

Nhóm chọn **user story nhỏ đi qua kiểm thử tích hợp của luồng đặt lịch** và xem bốn tuần gần đây:

| Tín hiệu | Trước cải tiến, giả định |
| --- | ---: |
| Số story đủ điều kiện đã hoàn tất | 12 |
| Thời gian chờ trước test trung vị | 4 ngày làm việc |
| Cycle time trung vị từ In Progress đến Done | 14 ngày làm việc |
| Số story thuộc luồng này bị blocked vì dữ liệu test | 8/12 |
| Lỗi hồi quy nghiêm trọng ghi nhận | 1 |
| Số người được giao quyền chuẩn bị môi trường | 1 |

Nhóm nhìn các hạng mục đang mở và xác minh nguyên nhân blocked. Họ biết số liệu **trung vị** chỉ là một góc nhìn, nên xem thêm phân bố và danh sách trường hợp phải chờ lâu nhất. Nhóm ghi rõ “Done” là đã kiểm tra/tích hợp theo chuẩn, **không tự thay thế chỉ số thời gian tới người dùng sau phát hành**.

### 12.4. Hình thành giả thuyết nguyên nhân

Quan sát công việc và trao đổi với người phụ trách môi trường cho thấy:

- Nhiều story chờ một người tạo dữ liệu giả lập lịch.
- Khi người đó vắng, story bị chặn.
- Dữ liệu test cũ đôi khi không đúng quy tắc mới, gây kiểm thử lại.
- Không phải mọi story đều bị ảnh hưởng: một số bug nhỏ chỉ cần unit test.

**Giả thuyết:** Nếu nhóm có **bộ fixture dữ liệu test an toàn và tự phục vụ cho luồng đặt lịch**, các story cần kiểm thử tích hợp sẽ đỡ chờ, và cycle time end-to-end có thể giảm **mà không giảm chất lượng**.

Đây là giả thuyết hợp lý vì gắn với hàng đợi có bằng chứng, **không phải kết luận chắc chắn**. Nút thắt khác như review có thể lộ ra sau khi thời gian chờ test giảm.

### 12.5. Chọn phạm vi thử nghiệm

Nhóm không xây hệ thống quản lý dữ liệu test cho toàn công ty. Họ chọn:

| Chiều | Phạm vi thử |
| --- | --- |
| **Loại việc** | Story nhỏ của luồng đặt lịch cần kiểm thử tích hợp. |
| **Kỹ thuật** | Fixture tạo dữ liệu Consultant, Slot và Appointment với các trạng thái hợp lệ. |
| **Môi trường** | Chỉ sandbox/test tách biệt; không chạm dữ liệu khách thật. |
| **Nhóm** | Một nhóm sản phẩm, phối hợp người sở hữu môi trường. |
| **Thời gian** | Bốn tuần quan sát, có điểm xem sớm nếu gặp rủi ro. |
| **Không thuộc phạm vi** | Chuyển database, đổi toàn bộ pipeline CI, tổ chức lại QA và chuyển microservices. |
| **Dấu hiệu chính** | Thời gian chờ trước test của các hạng mục đủ điều kiện. |
| **Guardrails** | Độ tin cậy test, lỗi hồi quy, quyền truy cập và dữ liệu nhạy cảm. |

**Vì sao đây là phạm vi hợp lý?** Nó cô lập một cơ chế được nghi ngờ, đủ gần nút thắt, có thể đo trên nhiều hạng mục và ít rủi ro hơn thay toàn bộ kiến trúc. Nếu trong bốn tuần số hạng mục đủ điều kiện quá ít, nhóm **không tuyên bố thành công chỉ vì timebox hết**.

### 12.6. Thực hiện và ghi nhận

Trong **Do**:

1. Developers và người phụ trách test thống nhất dữ liệu đại diện, quy tắc quyền và cách tái tạo.
2. Bộ fixture được dùng trong một luồng, không đưa thông tin cá nhân production vào test.
3. Nhóm ghi thời điểm story sẵn sàng test, bắt đầu test và đạt Done.
4. Những story vẫn dùng cách cũ hoặc gặp ngoại lệ được ghi rõ.
5. Nếu fixture tạo trạng thái sai hoặc tăng false positive/false negative, nhóm dừng mở rộng để sửa.

Nhóm cũng tiếp tục ghi story còn đang chờ test, không chỉ tính các story hoàn tất. **Một cải tiến gây dồn nhiều việc khó vào trạng thái đang mở** không được coi thành công chỉ vì nhóm đóng nhanh vài story dễ.

### 12.7. Số liệu sau thử và cách tính

Giả sử sau bốn tuần, trong cùng ranh giới đo và điều kiện đã ghi nhận:

| Tín hiệu | Trước | Sau thử |
| --- | ---: | ---: |
| Story đủ điều kiện hoàn tất | 12 | 13 |
| Thời gian chờ test trung vị | 4 ngày | 1,5 ngày |
| Cycle time trung vị | 14 ngày | 10,5 ngày |
| Story đã hoàn tất từng bị blocked vì dữ liệu test | 8/12 | 3/13 |
| Lỗi hồi quy nghiêm trọng ghi nhận | 1 | 1 |
| Sự cố dữ liệu nhạy cảm trong môi trường test | 0 | 0 |

Mức giảm **thời gian chờ test trung vị**:

\[
\frac{4-1{,}5}{4}\times100\% = 62{,}5\%
\]

Mức giảm **cycle time trung vị**:

\[
\frac{14-10{,}5}{14}\times100\% =25\%
\]

**Không suy ra:** “Fixture chắc chắn gây giảm 25% cycle time cho mọi story.” Các tập chỉ có 12 và 13 hạng mục, có thể khác độ phức tạp, kỳ nghỉ và thành viên; cùng kỳ có thể có thay đổi review hoặc phụ thuộc API. Số lỗi hồi quy bằng 1 ở hai kỳ **không chứng minh** độ tin cậy tương đương vì mẫu nhỏ và mức độ nghiêm trọng có thể khác. Trung vị cycle time cũng **không bằng tổng các trung vị thời gian từng bước**.

### 12.8. Study: xem cả kết quả không đúng dự đoán

Nhóm thấy:

- Thời gian chờ test giảm rõ trong mẫu quan sát.
- Cycle time cũng giảm, nhưng có hạng mục vẫn chờ review lâu.
- Một số fixture không mô phỏng được trạng thái timeout của API đối tác.
- Người phụ trách môi trường đỡ bị ngắt việc, song cần thêm tài liệu vận hành.

Những quan sát mới không phủ nhận lợi ích ban đầu; chúng cho thấy **hướng cải tiến tiếp theo** và **giới hạn phạm vi hiện tại**.

### 12.9. Act: quyết định sau thử

Nhóm quyết định:

1. Giữ fixture cho loại story đã thử và bổ sung test bảo vệ dữ liệu/trạng thái.
2. Chưa mở rộng ngay sang mọi hệ thống; đánh giá tính phù hợp và nhu cầu ở từng luồng.
3. Đưa rủi ro API timeout vào backlog discovery/kiểm thử tích hợp riêng.
4. Quan sát thêm thời gian chờ review để biết nút thắt đã dịch chuyển chưa.
5. Chia sẻ kết quả và giới hạn với Product Owner, stakeholder và người dùng khi phù hợp.

**Bài học:** Một thử nghiệm được xem là hữu ích vì **tạo thay đổi và hiểu biết có thể hành động**, không phải vì nhóm đạt một phần trăm đẹp.

## 13. So sánh phạm vi quá nhỏ, phù hợp và quá lớn

### 13.1. Ví dụ chính sách review

| Phạm vi | Rủi ro/khoảng trống | Nhận xét |
| --- | --- | --- |
| **Một PR duy nhất, trong một buổi sáng** | Kết quả phụ thuộc cá nhân và độ khó PR, chưa phản ánh dòng. | Có thể dùng để kiểm tra cơ chế, **chưa đủ** kết luận hiệu quả quy trình. |
| **Các PR nhỏ của một luồng trong vài tuần, có review chuẩn** | Còn biến động nhưng có cơ hội quan sát hàng đợi và chất lượng. | **Phù hợp hơn** để học về chính sách review. |
| **Tất cả PR của mọi nhóm, bỏ vai trò review hiện có ngay** | Phạm vi lớn, quyền sở hữu và rủi ro thay đổi cùng lúc. | Khó quy nguyên nhân và không an toàn nếu mất kiểm soát bắt buộc. |

### 13.2. Ví dụ giao diện trạng thái Pending

| Phạm vi | Điều học được | Điều chưa chứng minh |
| --- | --- | --- |
| **Prototype với vài người dùng phù hợp** | Họ có hiểu thông điệp và biết việc tiếp theo không? | Hiệu quả production, tỷ lệ lỗi hiếm. |
| **Phiên usability test có mạng chậm mô phỏng** | Cách người dùng phản ứng khi không thấy xác nhận ngay. | Khả năng backend chống trùng và hành vi mọi phân đoạn. |
| **Pilot an toàn với giám sát** | Cách dùng và độ tin cậy ở môi trường thật trong một phạm vi. | Tự động suy ra kết quả toàn bộ người dùng hoặc nhân quả chắc chắn. |
| **Phát hành toàn bộ ngay để xem dữ liệu** | Có thể có nhiều dữ liệu nhanh. | Có thể chuyển rủi ro sang khách khi chưa đủ điều kiện. |

Thử nghiệm ở một mức không loại bỏ nhu cầu kiểm chứng ở mức khác. **Prototype hữu ích nhưng không thay thế integration test**, còn pilot production không thể tự chứng minh vì sao người dùng nhấn lại nếu không có bối cảnh.

### 13.3. Quy mô nhỏ và đại diện là hai tiêu chí khác nhau

Nhóm thử chỉ với Developer nội bộ có thể phát hiện crash sớm nhưng không phản ánh cách khách lần đầu hiểu giao diện. Ngược lại, mời quá nhiều người dùng ngay khi có lỗi dữ liệu chưa sửa là rủi ro.

Để vừa nhỏ vừa hữu ích:

- Chọn **đúng nhóm người/loại việc** liên quan giả thuyết.
- Bao gồm những trường hợp **biên quan trọng**, không chỉ happy path.
- Xác định mẫu có thể trả lời câu hỏi gì, **không thể trả lời gì**.
- Nếu cần ước lượng tỷ lệ ở quy mô lớn, xây thiết kế đo và thời gian phù hợp.
- Với rủi ro cao, ưu tiên kiểm chứng kỹ thuật/an toàn trước khi mở rộng phơi nhiễm.

### 13.4. Đừng mở rộng thử nghiệm khi vấn đề đã đổi

Nếu sau hai tuần nhóm nhận ra **thời gian chờ test không còn là giới hạn**, còn review đang nghẽn, đừng tiếp tục xây thêm nhiều fixture chỉ vì kế hoạch ban đầu ghi “tự động hóa toàn bộ môi trường test”. Hãy dùng kết quả Study để **đổi quyết định**.

Đây là tinh thần lập kế hoạch thích ứng: giữ Product Goal và chuẩn chất lượng, nhưng cho phép phương tiện cải tiến thay đổi theo bằng chứng mới.

## 14. Phân tích kết quả khi dữ liệu ít, nhiễu hoặc trái chiều

### 14.1. Đừng chỉ so một con số trước–sau

Một thử nghiệm đổi quy trình review diễn ra đúng lúc đội có ít feature phức tạp hơn. Cycle time có thể giảm mà chính sách mới chỉ đóng góp ít. Một kỳ có một sự cố lớn khiến mọi người phải ứng cứu có thể làm cycle time tăng dù thử nghiệm có lợi.

Nên ghi đồng thời:

- Số hạng mục và loại việc.
- Khoảng quan sát và độ trễ giữa can thiệp/kết quả.
- Thay đổi năng lực, nhân sự, lịch nghỉ, sự cố và công cụ.
- Phân bố, nhóm ngoại lệ và work item age.
- Chỉ số toàn hệ thống và guardrails.
- Ý kiến người trực tiếp làm việc nhưng không biến ý kiến thành kết luận nhân quả.

### 14.2. Phân biệt tín hiệu và nguyên nhân

**Tín hiệu:** Sau khi thêm reviewer dự phòng, thời gian chờ review giảm.

**Giả thuyết nguyên nhân:** Reviewer dự phòng làm hàng đợi giảm.

**Các nguyên nhân khác có thể có:** PR nhỏ hơn, ít vắng mặt, upstream bắt đầu ít việc hơn hoặc CI ổn định hơn.

Khi không thể kiểm soát mọi biến, báo cáo trung thực:

> “Trong phạm vi thử, thời gian chờ giảm so với baseline; đây là tín hiệu tích cực. Chúng ta chưa thể tách riêng đóng góp của chính sách reviewer dự phòng khỏi thay đổi kích thước PR và lượng việc.”

Đây là cách làm **đáng tin cậy hơn** câu “đã chứng minh năng suất tăng 50%”.

### 14.3. Thiết kế so sánh phù hợp khi cần

Tùy mục tiêu, nhóm có thể:

1. So **trước–sau** với định nghĩa đo nhất quán, ghi các yếu tố gây nhiễu.
2. Chọn **hai luồng tương đồng** để xem xu hướng khác biệt, nhưng phải thận trọng vì chúng hiếm khi giống hoàn toàn.
3. Thử **luân phiên có kiểm soát** một chính sách ít rủi ro, khi không tạo đối xử bất công hay vi phạm yêu cầu vận hành.
4. Dùng thí nghiệm có nhóm đối chứng khi thật sự phù hợp, có đủ năng lực đo lường và các biện pháp bảo vệ.

Không nên ép mọi vấn đề cải tiến thành A/B test. Các biện pháp **bảo vệ an toàn hoặc khắc phục lỗi đã xác minh** không cần cố tình giữ một nhóm người dùng ở trạng thái nguy hiểm làm đối chứng.

### 14.4. “Không thấy khác biệt” chưa chắc nghĩa là “không hiệu quả”

Nếu chỉ có ba hạng mục hoàn tất trong hai tuần, dữ liệu throughput và cycle time có thể quá ít để thấy khác biệt đáng tin. Ngược lại, nếu có đủ trường hợp và không thấy tác động có ích, nhóm cần cân nhắc **dừng hoặc đổi giả thuyết**, không kéo dài vô hạn.

Nên tách:

- **Không có lợi ích quan sát được trong phạm vi đủ phù hợp.**
- **Chưa đủ dữ liệu để đánh giá.**
- **Có lợi ích cục bộ nhưng guardrail xấu đi.**
- **Có tín hiệu tích cực, cần kiểm tra độ bền và khả năng mở rộng.**

Bốn kết quả này dẫn tới **bốn loại quyết định khác nhau**.

### 14.5. Trung vị, trung bình và chuyện một vài hạng mục rất chậm

Giả sử cycle time của năm story là **3, 4, 4, 5 và 24 ngày**:

- **Trung vị:** 4 ngày.
- **Trung bình:** \((3+4+4+5+24)/5=8\) ngày.

Chỉ báo trung vị 4 ngày có thể che một story đang gây thiệt hại lớn ở đuôi phân bố. Chỉ báo trung bình 8 ngày có thể không mô tả trải nghiệm điển hình. Cần xem **cả phân bố, trường hợp ngoại lệ, work item age và mức tác động**, thay vì tranh luận một thước đo duy nhất.

## 15. Kết nối cải tiến với Scrum, Kanban và XP

### 15.1. Scrum: Retrospective chọn cách cải tiến, không thay Product Goal

Trong Scrum, **Sprint Retrospective** là cơ hội Scrum Team kiểm tra con người, tương tác, quy trình, công cụ và Definition of Done, rồi lập kế hoạch cải thiện chất lượng/hiệu quả. Đây là nơi phù hợp để nêu vấn đề, đánh giá bằng chứng và chọn thử nghiệm.

Tuy nhiên:

- **Sprint Goal** là commitment của Sprint Backlog, không nên bị thay bằng một danh sách action item cải tiến dài.
- **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog.
- **Developers** chịu trách nhiệm lập kế hoạch công việc trong Sprint, giữ chất lượng và tạo Increment đạt DoD.
- **Scrum Master** giúp nhóm nâng hiệu quả Scrum, có thể hỗ trợ tháo điểm nghẽn và điều phối cải tiến.

Scrum Team có thể đưa một cải tiến có tác động vào Sprint Backlog hoặc điều chỉnh cách làm trong Sprint khi phù hợp; **không cần chờ đúng Sprint Retrospective tiếp theo** mới xử lý vấn đề đã thấy. Nhưng phải tôn trọng quyền quyết định, các ràng buộc và cam kết hiện có.

### 15.2. Từ Sprint Review tới vấn đề cải tiến

**Sprint Review** giúp Scrum Team và stakeholder kiểm tra kết quả Sprint, tiến độ hướng Product Goal và những thay đổi của môi trường. Một phản hồi như “khách chưa hiểu Pending” có thể tạo:

- Một yêu cầu sản phẩm mới.
- Một lỗi cần xử lý.
- Một giả thuyết UX cần sử dụng thử.
- Một vấn đề về cách nhóm thu thập phản hồi sớm.

Đừng biến mọi phản hồi ở Review thành kết luận “Scrum Team cần chạy nhanh hơn”. Có khi vấn đề **hiểu sai nhu cầu** chứ không phải **thiếu tốc độ**.

### 15.3. Kanban: cải tiến dựa trên dòng thực và WIP

Kanban nhấn mạnh việc **định nghĩa và nhìn thấy workflow**, quản lý số việc đang làm, chính sách kéo việc, các vòng phản hồi và cải tiến flow. Với một thử nghiệm WIP limit:

1. Công khai start/finish của workflow.
2. Xác định giới hạn WIP và ngoại lệ/việc khẩn theo chính sách.
3. Đo WIP, throughput, cycle time, work item age.
4. Quan sát blocked và chất lượng khi nhóm ưu tiên hoàn tất.
5. Xem lại chính sách dựa trên số liệu và trải nghiệm làm việc.

**WIP limit không phải mục tiêu tự thân**: Nếu đặt quá thấp khiến mọi người bị chặn hoặc trì hoãn sự cố quan trọng, cần điều chỉnh chính sách, không ép số liệu cho khớp mục tiêu.

### 15.4. XP: cải tiến khả năng thay đổi an toàn

Một số vấn đề có tác động lớn là **phản hồi kỹ thuật đến quá muộn**: lỗi hồi quy chỉ phát hiện ở cuối Sprint, PR lớn khó review, việc thay đổi một module gây hỏng nhiều phần.

Các thực hành XP có thể là ứng viên thử:

- **TDD:** thử viết test trước cho một quy tắc nhiều lỗi.
- **Continuous Integration:** tích hợp thường xuyên hơn để thấy lỗi sớm.
- **Pair programming:** hỗ trợ một loại việc phức tạp và chia sẻ tri thức.
- **Refactoring:** giảm phụ thuộc ở khu vực thực sự đang làm chậm thay đổi.
- **Small releases:** học từ phần mềm đã giao khi điều kiện an toàn cho phép.

Thử **một thay đổi kỹ thuật đủ rõ** với tiêu chí chất lượng, không áp nguyên một danh sách nghi thức và xem việc tuân thủ tất cả là mục tiêu cuối.

### 15.5. Lean: tối ưu toàn hệ thống, không ép mọi người bận 100%

Nếu phát triển hoàn tất mười story/tuần, nhưng kiểm thử chỉ xử lý bốn story, tăng công suất coding tiếp có thể làm WIP và thời gian chờ tăng. Tư duy Lean tìm **rào cản toàn dòng** và giảm lãng phí chuyển giao, chờ, làm lại thay vì tối đa hóa hiệu suất từng bộ phận.

**Khả năng hấp thụ biến động**, thời gian học, review và ứng cứu hợp lý không tự động là lãng phí. Ép utilization mọi người lên 100% có thể phá sự linh hoạt của hệ thống trong môi trường công việc tri thức nhiều bất định.

## 16. Những phản mẫu làm cải tiến liên tục mất tác dụng

| Phản mẫu | Dấu hiệu | Hậu quả | Điều chỉnh |
| --- | --- | --- | --- |
| **Chọn giải pháp trước khi hiểu vấn đề** | Retrospective bắt đầu bằng “chúng ta phải chuyển công cụ”. | Đầu tư lớn nhưng điểm chờ thật không đổi. | Viết phát biểu vấn đề và bằng chứng trước giải pháp. |
| **Thích vấn đề dễ thấy hơn vấn đề quan trọng** | Ưu tiên đổi giao diện dashboard, bỏ qua lỗi dữ liệu hiếm nhưng nặng. | Cải tiến không liên hệ mục tiêu/rủi ro. | Triage nghiêm trọng và đánh giá tác động nhiều chiều. |
| **Đếm phiếu thay đánh giá tác động** | Ý tưởng được nhiều người thích nhất mặc định đứng đầu. | Người chịu ảnh hưởng ít tiếng nói bị bỏ qua. | Kết hợp thông tin người dùng, dữ liệu flow, chất lượng và quyền quyết định. |
| **Chỉ có ý kiến, không có baseline** | “Review rất chậm” nhưng không biết chờ bao lâu. | Không thể biết sau thử có cải thiện không. | Thu timestamps, phân bố và nguyên nhân blocked vừa đủ. |
| **Phân tích số liệu mà không biết ranh giới** | Bên A tính Done khi merge, bên B khi release. | So sánh sai và tối ưu cục bộ. | Đặt metric contract, start/finish và loại việc rõ. |
| **Giải pháp không thể bác bỏ** | “Thay quy trình này chắc chắn giúp tinh thần tốt hơn.” | Không có cách đánh giá hay quyết định dừng. | Viết giả thuyết, dự đoán, dấu hiệu trái dự đoán. |
| **Thay mọi thứ cùng lúc** | Đổi CI, tổ chức, WIP, backlog trong một kỳ. | Khó phân biệt cơ chế và gây quá tải. | Thử một thay đổi chính, ghi biến số đi kèm. |
| **Thử quá nhỏ để học** | Áp dụng chính sách WIP một buổi với một ticket. | Không đủ trường hợp hoặc thời gian dòng. | Chọn mẫu/phạm vi có khả năng quan sát hiệu ứng. |
| **Thử quá lớn và khó đảo ngược** | Triển khai lại tổ chức toàn công ty để xem có nhanh hơn. | Blast radius cao, rủi ro và khó học. | Cắt lát theo loại việc/team/timebox, bảo vệ quyền lợi. |
| **Không có guardrails** | Review nhanh hơn nhờ bỏ kiểm tra thiết yếu. | Lỗi hồi quy và mất niềm tin. | Đo flow cùng chất lượng, an toàn và người dùng. |
| **Dùng người dùng làm nơi thử lỗi nghiêm trọng** | Mở beta khi biết có nguy cơ đặt lịch trùng. | Chuyển thiệt hại sang khách. | Ứng cứu, test trong sandbox, phát hành an toàn sau sửa. |
| **Chỉ xem ticket đã hoàn tất** | Việc khó nằm chờ nhiều tuần nhưng không vào cycle time. | Che WIP và rủi ro chậm. | Theo dõi work item age và blocked song song. |
| **Mục tiêu là “mọi người bận”** | Giao thêm việc khi ai đó chờ phản hồi. | Tăng chuyển ngữ cảnh và hàng đợi. | Quản lý WIP, ưu tiên hoàn tất, dự phòng hợp lý. |
| **Dùng cải tiến để đổ lỗi** | “Phải sửa QA vì QA yếu.” | Nhóm giấu lỗi, mất cộng tác. | Phân tích điều kiện hệ thống, quyền và quy trình. |
| **Tính điểm độ tin cậy giả chính xác** | Confidence 91,7% chỉ vì một người chấm. | Che bất định và tranh luận dữ liệu. | Ghi nguồn bằng chứng, giới hạn và mức tin cậy hợp lý. |
| **Thấy tăng chỉ số là tuyên bố nhân quả** | Cycle time giảm sau kỳ ít story lớn. | Quyết định mở rộng dựa trên kết luận sai. | Xem loại việc, phân bố, các biến số đồng thời. |
| **Không quyết định sau thử** | Mọi action item kéo qua nhiều retrospective. | Không có học hỏi, năng lực bị khóa. | Đặt review date, người phụ trách, lựa chọn giữ/sửa/dừng. |
| **Chuẩn hóa trước khi kiểm tra** | Một nhóm vừa thử đã áp dụng chính sách cho mọi đội. | Phản ứng ở bối cảnh khác có thể xấu hơn. | Mở rộng từng bước, tôn trọng khác biệt workflow. |
| **Đóng backlog theo số lượng ý tưởng cải tiến** | Mỗi Sprint phải hoàn thành ít nhất 10 action items. | Chọn việc nhỏ vô nghĩa. | Đánh giá outcome, flow, chất lượng và bài học. |
| **Đồng nhất thất bại giả thuyết với thất bại con người** | Người đề xuất bị phê bình khi thử không đạt. | Không ai dám thừa nhận bằng chứng trái dự đoán. | Đánh giá tính trách nhiệm trong thiết kế thử và học từ kết quả. |

### 16.1. Cải tiến “có vẻ nhanh” nhưng giảm chất lượng

Một nhóm bỏ review với các thay đổi nhạy cảm để rút thời gian chờ. Báo cáo tuần đầu cho thấy số PR merge tăng. Tháng sau xuất hiện lỗi quyền truy cập, phát sinh ứng cứu và mất thời gian sửa dữ liệu.

Đây là **tối ưu một bước**, không phải cải tiến toàn hệ thống. Nếu review là nút thắt, cần xem kích thước PR, người dự phòng, chuẩn review, tự động hóa kiểm tra và khả năng kiểm chứng sớm, **không hạ chuẩn bắt buộc**.

### 16.2. Đổi quy trình trước khi thống nhất mục tiêu

Hai nhóm báo “muốn bớt họp”. Một nhóm bị họp trùng giờ gây ngắt việc, nhóm khác lại thiếu trao đổi nên thường xây sai yêu cầu. Cùng chính sách “giảm họp 50%” có thể cải thiện nhóm thứ nhất và làm nhóm thứ hai tệ hơn.

Vì vậy, chọn cải tiến phải dựa trên **vấn đề của workflow thật**, không áp một công thức cho mọi nhóm. Có thể thử bỏ một cuộc họp ít giá trị ở nhóm thứ nhất, nhưng bổ sung cơ chế làm rõ ví dụ nghiệp vụ sớm ở nhóm thứ hai.

### 16.3. Bảng vấn đề có thể trở thành “nghĩa trang ý tưởng”

Nếu nhóm ghi nhiều vấn đề mà không ai quyết định, các cuộc họp sau sẽ tiếp tục nói lại cùng điều. Một danh sách hiệu quả cần có:

- Vấn đề được diễn đạt theo tác động.
- Bằng chứng hoặc mức bất định.
- Tình trạng: đang điều tra, được chọn thử, đã học, tạm hoãn, dừng.
- Người phối hợp và thời điểm xem lại.
- Quyết định cuối cùng kèm lý do.

Không cần một công cụ mới chỉ để làm được những việc trên; một trang chia sẻ đơn giản có thể đủ.

## 17. Bài tập tình huống có đáp án định hướng

### Tình huống A — Chọn vấn đề từ Retrospective

Nhóm có ba ứng viên:

- **A:** Môi trường test thường chờ ba ngày, ảnh hưởng nhiều story và đã được ghi nhận sáu tuần.
- **B:** Một số thành viên không thích màu giao diện công cụ backlog.
- **C:** Một lỗi timeout có khả năng tạo hai lịch, đã tái hiện bằng kiểm thử tích hợp.

**Câu hỏi:**

1. Vấn đề nào cần xử lý theo luồng sự cố/rủi ro, không chờ bình chọn?
2. Sau khi rủi ro được kiểm soát, ứng viên nào đáng thử cải tiến workflow trước? Vì sao?
3. Đề xuất một phạm vi nhỏ và ba chỉ số để thử ứng viên đó.

**Hướng giải:** **C** cần triage và sửa theo mức nghiêm trọng vì liên quan bất biến dữ liệu. Với cải tiến thông thường, **A** có tác động dòng và bằng chứng rõ hơn B. Có thể thử fixture tự phục vụ cho một nhóm user story trong sandbox, đo thời gian chờ test, cycle time toàn luồng và lỗi/độ tin cậy test làm guardrail.

### Tình huống B — Thử nghiệm quá nhỏ

Một Scrum Team áp dụng giới hạn hai story đang phát triển trong đúng **nửa ngày**, chỉ có một story được kéo qua test. Họ kết luận “WIP limit không giúp cải thiện cycle time”.

**Câu hỏi:**

1. Phạm vi này có đủ để đánh giá chưa?
2. Một cách thử phù hợp hơn là gì?
3. Cần quan sát cả công việc đã hoàn tất và chưa hoàn tất như thế nào?

**Hướng giải:** Chưa đủ hạng mục và thời gian để quan sát ảnh hưởng lên dòng. Có thể thử trên một loại việc và một nhóm trong vài tuần hoặc cho tới khi có số trường hợp hợp lý, định nghĩa start/finish, WIP và blocked. Theo dõi throughput/cycle time đã Done cùng work item age của việc còn mở; xét mức độ biến động và chất lượng.

### Tình huống C — Thử nghiệm quá lớn

Một quản lý muốn thay đồng thời công cụ backlog, cơ cấu team, CI pipeline, quy trình code review và nhịp release trên toàn công ty trong hai tháng để “tăng tốc Agile”.

**Câu hỏi:**

1. Vì sao khó biết cải tiến nào hiệu quả?
2. Rủi ro vận hành và con người nào có thể xuất hiện?
3. Có thể thu hẹp thành một thử nghiệm đầu tiên ra sao?

**Hướng giải:** Thay nhiều biến cùng lúc khiến khó quy cơ chế và tạo tải phối hợp. Có thể chọn một vấn đề đã đo như thời gian chờ review, thử reviewer dự phòng cho một loại PR trong một team, giữ chính sách an toàn và so flow/quality. Từ bằng chứng đó mới xem có nên thay công cụ hay tổ chức.

### Tình huống D — Bảng số liệu đã đẹp hơn, nhưng lỗi tăng

Một đội giảm thời gian review trung vị từ 3 ngày xuống 1 ngày nhờ bỏ bước kiểm tra thay đổi quyền truy cập. Sau đó số sự cố quyền truy cập sai tăng từ 0 lên 3.

**Câu hỏi:**

1. Có thể tuyên bố cải tiến thành công không?
2. Guardrail nào bị bỏ sót?
3. Đề xuất thử nghiệm thay thế ít rủi ro.

**Hướng giải:** Không; chất lượng và bảo mật đã bị ảnh hưởng. Khôi phục/điều chỉnh kiểm soát theo thẩm quyền, xem kích thước PR, thiết lập rule kiểm tra tự động, reviewer dự phòng được đào tạo và test quyền ở tầng phù hợp. Đo thời gian chờ cùng lỗi/khả năng phục hồi.

### Tình huống E — Tính phần trăm thay đổi

Baseline của một loại story có **thời gian chờ test trung vị 5 ngày**. Sau một thử nghiệm có ranh giới đo tương đương, chỉ số là **3 ngày**.

1. Mức giảm tuyệt đối là bao nhiêu ngày?
2. Mức giảm tương đối là bao nhiêu phần trăm?
3. Có thể khẳng định biện pháp thử tạo ra toàn bộ cải thiện không?

**Đáp án:** (1) **2 ngày**; (2) \((5-3)/5\times100\%=40\%\); (3) **chưa**, cần xem số mẫu, đặc điểm hạng mục, biến số nhiễu, phân bố, guardrails và cả việc chưa Done.

### Tình huống F — Little’s Law và giới hạn suy luận

Một workflow tương đối ổn định có **WIP trung bình 15 mục** và **throughput trung bình 5 mục/tuần**. Nhóm muốn giảm WIP còn 10, kỳ vọng throughput được giữ ổn định.

1. Thời gian trung bình trong hệ thống theo mô hình hiện tại là bao nhiêu?
2. Với WIP 10 và throughput không đổi, mô hình cho bao nhiêu?
3. Có được cam kết mỗi mục sẽ hoàn tất trong hai tuần không?
4. Nếu việc đang mở liên tục tăng, việc áp dụng phép tính có nguy cơ gì?

**Đáp án:** (1) \(15/5=3\) tuần; (2) \(10/5=2\) tuần; (3) không, đây là quan hệ **trung bình trong điều kiện ổn định**; (4) dữ liệu chưa ở trạng thái dòng ổn định, cần xem nguồn vào/ra, WIP, phân bố thời gian và ranh giới đo.

### Tình huống G — Kết quả không khớp giả thuyết

Nhóm thử chuẩn hóa mẫu PR trong ba tuần. Số comment review giảm nhưng cycle time toàn dòng không đổi và thời gian chờ kiểm thử tăng. Người đề xuất muốn kéo dài thêm ba tháng vì “mẫu PR đẹp hơn”.

**Câu hỏi:**

1. Điều gì có thể đã được cải thiện cục bộ?
2. Có khả năng nút thắt đã dịch chuyển không?
3. Quyết định Study/Act có trách nhiệm là gì?

**Hướng giải:** Mẫu PR có thể giúp review dễ hơn, nhưng giá trị end-to-end chưa được chứng minh. Xem WIP, hàng đợi kiểm thử và chất lượng. Có thể giữ phần mẫu thực sự hữu ích, dừng các thủ tục tốn kém, rồi chọn vấn đề mới ở nút thắt; không mở rộng chỉ để bảo vệ giải pháp.

### Tình huống H — Mẫu thử không đại diện

Nhóm thay màn hình đặt lịch và sử dụng thử với sáu Developers có điện thoại mới, mạng mạnh. Tất cả hoàn tất nhanh. Sau khi phát hành, khách hàng dùng máy cũ và mạng chậm tiếp tục gặp lỗi.

**Câu hỏi:**

1. Đây là giới hạn về phạm vi hay cách chọn mẫu?
2. Nên thử lại bằng phương pháp nào?
3. Điều gì phải được kiểm chứng ở backend?

**Hướng giải:** Cả phạm vi lẫn mẫu chưa tương ứng tình huống khách cần cải thiện. Thử tác vụ với thiết bị/mạng phù hợp và người dùng đại diện; quan sát cách hiểu trạng thái. Backend vẫn phải bảo vệ chống trùng, retry, timeout và quyền dữ liệu bằng kiểm thử thích hợp trước khi phát hành mở rộng.

### Tình huống I — Cải tiến tạo kết quả tốt nhưng tốn nhiều công sức duy trì

Nhóm viết một script tự động tạo dữ liệu test; thời gian chờ giảm nhưng script cần hai Developers sửa hằng ngày vì cấu trúc schema thay đổi. Một số lần script tạo dữ liệu sai làm test thất bại giả.

**Câu hỏi:**

1. Vì sao không thể chỉ dùng thời gian chờ để quyết định mở rộng?
2. Những chi phí nào cần đo?
3. Có thể làm gì ở vòng PDSA tiếp theo?

**Hướng giải:** Cần đo false failures, giờ bảo trì, lỗi test data, chi phí onboarding và độ tin cậy. Có thể thử hợp đồng fixture/seed data ổn định cho một mô đun hoặc cải thiện cơ chế cập nhật schema, giữ phạm vi giới hạn cho đến khi chi phí toàn hệ thống chấp nhận được.

### Tình huống J — Mọi người đều đưa ra giải pháp, không ai mô tả vấn đề

Trong Retrospective, các action items là “thêm Jira plugin”, “bỏ Daily Scrum”, “làm microservice”, “tăng họp refinement”. Nhóm không thống nhất chúng liên hệ tới khó khăn nào.

**Câu hỏi:**

1. Viết lại ít nhất hai mục thành **vấn đề có tác động**.
2. Mỗi vấn đề cần bằng chứng gì?
3. Một thử nghiệm nhỏ nào sẽ cung cấp thông tin ra quyết định?

**Hướng giải:** Có thể viết “story thường chờ xác nhận tiêu chí chấp nhận hai ngày trước khi Developers tiếp tục” rồi đo blocked/rework và thử làm rõ ví dụ với Product Owner trước khi kéo story. Hoặc “thay quy tắc kiểm tra trạng thái lịch thường buộc sửa ba module và phá test” rồi lập bản đồ phụ thuộc, thử tách chính sách trong một use case với test bảo vệ. Không coi tên công cụ hay mô hình kiến trúc là vấn đề tự thân.

## 18. Workshop 60–75 phút: chọn vấn đề và thiết kế thử nghiệm

### 18.1. Đề bài cho nhóm

Một nhóm Agile phát triển tính năng đặt lịch. Trong tháng qua:

- Khách phản ánh đôi khi không biết lịch đã được xác nhận hay chưa.
- Story thường chờ kiểm thử tích hợp.
- Một số Developer thấy Daily Scrum không giúp tháo chặn.
- Một lỗi retry có nguy cơ gây lịch trùng vừa được phát hiện.
- Quản lý đề nghị chuyển sang microservices.

Nhiệm vụ là **chọn một vấn đề cải tiến thường xuyên có tác động rõ sau khi triage rủi ro cấp bách**, rồi thiết kế một thử nghiệm **an toàn và có thể học**.

### 18.2. Cách tổ chức buổi thực hành

| Thời gian | Hoạt động | Đầu ra |
| --- | --- | --- |
| 0–10 phút | Xác định Product Goal, rủi ro bắt buộc xử lý và người bị ảnh hưởng. | Ranh giới quyết định, vấn đề cấp bách tách riêng. |
| 10–20 phút | Phân loại triệu chứng, vấn đề, nguyên nhân giả định và giải pháp. | 2–3 phát biểu vấn đề có tác động. |
| 20–35 phút | Xem bằng chứng hiện có, số đo và khoảng trống; chọn một vấn đề ưu tiên. | Baseline/nguồn dữ liệu, lý do lựa chọn. |
| 35–50 phút | Thiết kế giả thuyết và phạm vi thử theo năm chiều. | Một phiếu thử nghiệm có timebox/guardrails. |
| 50–60 phút | Mô phỏng kết quả trái dự đoán hoặc sự cố; xác định điều kiện dừng. | Kịch bản bảo vệ và quyết định có thể xảy ra. |
| 60–75 phút | Phản biện chéo và chốt người phụ trách, thời điểm xem lại. | Kế hoạch PDSA có thể dùng ngay. |

Khung này có thể rút gọn nếu vấn đề nhỏ, hoặc mở rộng khi cần phân tích dữ liệu. **Không để workshop trì hoãn việc xử lý sự cố an toàn đang diễn ra**.

### 18.3. Mẫu A3 rút gọn cho cải tiến

~~~text
1. CONTEXT / PRODUCT GOAL
   Kết quả người dùng hoặc giá trị nào đang bị ảnh hưởng?

2. PROBLEM STATEMENT
   Triệu chứng:
   Vấn đề và hệ quả:
   Ranh giới start/finish:

3. CURRENT CONDITION
   Bằng chứng đã có:
   Baseline và phân bố:
   Hạng mục còn mở/blocked:
   Độ tin cậy và dữ liệu thiếu:

4. CAUSE HYPOTHESIS
   Nguyên nhân có thể:
   Bằng chứng hỗ trợ / trái chiều:
   Điều cần kiểm chứng tiếp:

5. PRIORITY RATIONALE
   Impact / severity / cost of delay:
   Confidence / control / effort:
   Vấn đề cạnh tranh và chi phí cơ hội:

6. EXPERIMENT
   Can thiệp chính:
   Loại việc / bước workflow / team:
   Môi trường / mức phơi nhiễm:
   Timebox / người chịu trách nhiệm:

7. MEASURE AND SAFETY
   Primary signal:
   End-to-end signal:
   Guardrails:
   Stop/rollback/incident response:

8. STUDY AND ACT
   Dự đoán ban đầu:
   Kết quả quan sát / ngoại lệ:
   Điều học được:
   Giữ / sửa / mở rộng / dừng:
   Người quyết định và ngày xem lại:
~~~

**A3** ở đây là cách trình bày vấn đề và lập luận gọn, không yêu cầu đúng kích thước giấy hoặc bắt buộc theo một biểu mẫu của mọi tổ chức. Quan trọng là **một người khác có thể kiểm tra được lý do và bằng chứng của quyết định**.

### 18.4. Một kế hoạch mẫu

**Vấn đề chọn:** Story đặt lịch chờ môi trường kiểm thử nhiều ngày, làm chậm cập nhật những yêu cầu khách phản ánh.

**Bằng chứng ban đầu:** Dữ liệu blocked của bốn tuần cho thấy chờ tạo dữ liệu test thường xuyên; một số lần test lại do fixture sai.

**Giả thuyết:** Fixture tự phục vụ cho một luồng sẽ giảm thời gian chờ và cycle time mà không tăng lỗi.

**Phạm vi:** Một team, một loại story, sandbox, bốn tuần; không dùng dữ liệu production.

**Chỉ số chính:** Phân bố thời gian chờ chuẩn bị test.

**Chỉ số toàn dòng:** Cycle time từ start tới Done và work item age của việc đang mở.

**Guardrails:** Độ tin cậy test, lỗi hồi quy, quyền và dữ liệu nhạy cảm.

**Tiêu chí xem lại:** Đối chiếu dữ liệu với kỳ trước, xem số hạng mục, tính khác biệt loại việc; nếu lợi ích xuất hiện và guardrails giữ, tiếp tục trong phạm vi đó rồi đánh giá mở rộng. Nếu fixture tạo dữ liệu sai nghiêm trọng, dừng và sửa.

**Không thuộc phạm vi:** Chuyển kiến trúc toàn hệ thống, đổi mọi công cụ, tăng số story bắt đầu.

### 18.5. Tiêu chí đánh giá bài thực hành

Một bản kế hoạch tốt cho phép trả lời:

1. Vấn đề có **tác động rõ và bằng chứng** hay chỉ là lời đề xuất công cụ?
2. Có phân biệt triệu chứng với nguyên nhân giả định không?
3. Phạm vi đủ nhỏ để bảo vệ người dùng nhưng đủ trường hợp để học không?
4. Có chỉ số **toàn hệ thống** và guardrails, không chỉ chỉ số cục bộ không?
5. Có thời điểm xem lại, tiêu chí dừng và người chịu trách nhiệm không?
6. Khi kết quả bác bỏ giả thuyết, nhóm sẽ làm gì?
7. Có khả năng chuyển bài học thành thay đổi backlog/quy trình thật không?

## 19. Checklist chọn vấn đề và thiết kế thử nghiệm

### Trước khi chọn

- [ ] Đã nêu rõ người dùng, sản phẩm hoặc dòng công việc chịu ảnh hưởng.
- [ ] Đã phân biệt **triệu chứng, vấn đề, giả thuyết nguyên nhân và giải pháp**.
- [ ] Có bằng chứng từ số liệu, quan sát hoặc phản hồi phù hợp; biết giới hạn của nguồn.
- [ ] Đã xem hạng mục còn mở, blocked và công việc làm lại, không chỉ ticket Done.
- [ ] Baseline có ranh giới start/finish, đơn vị và khoảng thời gian rõ.
- [ ] Có đánh giá mức nghiêm trọng và nghĩa vụ an toàn trước khi xếp hạng cải tiến.
- [ ] Đã so tác động, cấp bách, độ tin cậy, công sức và chi phí cơ hội.
- [ ] Nếu đề xuất là một kiến trúc/công cụ, đã hỏi **vấn đề nào nó giải quyết**.

### Khi giới hạn thử nghiệm

- [ ] Có **giả thuyết có thể bác bỏ** và dự đoán về tín hiệu chính.
- [ ] Chọn đúng loại việc và bước workflow cần học.
- [ ] Quy định rõ team/người phối hợp, môi trường và thời gian.
- [ ] Phạm vi đủ sinh bằng chứng, không chỉ “một ticket trong một giờ”.
- [ ] Không thay nhiều biến lớn cùng lúc nếu có cách tránh.
- [ ] Có chỉ số end-to-end và chất lượng đối trọng.
- [ ] Có điều kiện dừng, người có quyền ứng cứu và kế hoạch phục hồi phù hợp.
- [ ] Không thử bằng cách để lỗi dữ liệu/bảo mật nghiêm trọng gây hại người dùng.
- [ ] Có chính sách bảo vệ dữ liệu và giới hạn truy cập khi cần.

### Khi thực hiện và đánh giá

- [ ] Ghi nhận can thiệp đã thực sự được áp dụng tới mức nào.
- [ ] Theo dõi việc chưa hoàn tất và sự cố ngoại lệ, không chỉ các mục nhanh được đóng.
- [ ] Giữ định nghĩa số đo nhất quán và ghi biến số nhiễu.
- [ ] So kết quả với **dự đoán ban đầu**, không chỉ với điều nhóm muốn thấy.
- [ ] Không suy nhân quả chắc chắn từ mẫu nhỏ hoặc dữ liệu trước–sau chưa kiểm soát.
- [ ] Không chấp nhận cải thiện cục bộ khi guardrails xấu đi.
- [ ] Đã quyết định **giữ, sửa, mở rộng hoặc dừng** kèm lý do và người phụ trách.
- [ ] Bài học đã được phản ánh vào chính sách làm việc, backlog hoặc kế hoạch thử kế tiếp.
- [ ] Thử nghiệm không hiệu quả được ghi nhận như kiến thức, không bị che để tránh mất mặt.

## 20. Ghi nhớ cốt lõi

**Cải tiến liên tục không bắt đầu từ một danh sách giải pháp.** Nó bắt đầu từ **vấn đề có tác động thực**, được diễn đạt đủ rõ để một nhóm hiểu ai đang chịu hệ quả và bằng chứng ở đâu. Sau đó nhóm hình thành giả thuyết nguyên nhân, chọn điểm đòn bẩy và thiết kế thử nghiệm có phạm vi, phép đo và điều kiện an toàn phù hợp.

Năm câu hỏi đáng nhớ:

1. **Tại sao cần cải tiến điều này ngay bây giờ?** Người dùng, dòng công việc hoặc chất lượng đang chịu tác động gì?
2. **Ta thật sự biết gì và đang giả định gì?** Triệu chứng và nguyên nhân có được phân biệt không?
3. **Phạm vi nhỏ nhất đủ để học là gì?** Loại việc, bước, team, timebox và phơi nhiễm tới đâu?
4. **Ta sẽ đo kết quả mà không gây hại như thế nào?** Có baseline, tín hiệu toàn dòng và guardrails không?
5. **Sau thử sẽ quyết định gì?** Giữ, điều chỉnh, mở rộng hay dừng và ai chịu trách nhiệm?

**PDSA** giúp tổ chức vòng học; **Retrospective và Sprint Review** trong Scrum giúp kiểm tra hiệu quả làm việc và giá trị sản phẩm; **Kanban** cho thấy WIP, hàng đợi và độ trễ; **XP** giúp thử những cải tiến kỹ thuật và refactor an toàn. Các cách tiếp cận này bổ sung cho nhau khi nhóm **đo đúng vấn đề, chọn thay đổi có chủ đích và học từ phần mềm hoạt động thật**.

**Cải tiến đáng giá không nhất thiết là dự án lớn nhất hay ý tưởng được khen nhiều nhất; đó là thay đổi giúp hệ thống tốt lên với bằng chứng đủ tin, rủi ro được kiểm soát và khả năng tiếp tục thích ứng ở vòng sau.**

### Tài liệu tham khảo nền tảng

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — các giá trị Agile, đặc biệt cộng tác, phần mềm hoạt động và thích ứng trước thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — giao phần mềm thường xuyên, kỹ thuật tốt, nhịp bền vững và tự xem xét hiệu quả để điều chỉnh.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Sprint Retrospective, Sprint Review, Increment, Definition of Done và trách nhiệm Scrum Team.
- [The Kanban Guide](https://kanbanguides.org/) — Definition of Workflow, WIP, cycle time, throughput, work item age và cải tiến dòng.
- [Lean Enterprise Institute](https://www.lean.org/) — tư duy dòng giá trị, giải quyết vấn đề, Kaizen và học bằng cải tiến.
- [The W. Edwards Deming Institute](https://deming.org/) — tư duy hệ thống, PDSA và học từ biến động.
- [DORA](https://dora.dev/) — tham khảo về năng lực giao thay đổi phần mềm, độ tin cậy và cải tiến kỹ thuật.
