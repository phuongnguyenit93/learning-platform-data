# Chia nhỏ đầu việc nhưng không tạo phần giá trị có thể kiểm chứng

Một nhóm phát triển nền tảng đăng ký workshop bắt đầu Sprint với yêu cầu: **“Học viên đủ điều kiện có thể đăng ký một workshop còn chỗ và biết mình đã được xác nhận hay chưa.”** Nhóm tách yêu cầu thành tám thẻ: thiết kế bảng dữ liệu, viết entity, tạo API, thêm nút đăng ký, viết email, cấu hình pipeline, kiểm thử tích hợp và cập nhật tài liệu. Đến cuối Sprint, sáu trong tám thẻ có trạng thái **Done**. Dashboard báo hoàn thành 75% số đầu việc. Nhưng khi Product Owner thử luồng đăng ký, API chưa kết nối với giao diện, thao tác đồng thời có thể giữ quá số chỗ, người dùng không biết đăng ký thành công hay chưa. **Không có một hành trình đăng ký hoàn chỉnh nào đủ tin cậy để xác nhận với người dùng.**

Nhóm đã **chia nhỏ công việc**, nhưng chưa **chia nhỏ giá trị**. Đây là một sai lầm phổ biến trong phát triển Agile: tối ưu việc tạo nhiều đơn vị công việc nhỏ và dễ đánh dấu hoàn tất, trong khi các đơn vị ấy vẫn phụ thuộc lẫn nhau để tạo nên một kết quả có thể sử dụng, kiểm chứng hoặc học hỏi.

Bài thuộc chương **Sai lầm thường gặp** của module **AGILE_DEVELOPMENT**. Nội dung vận dụng giá trị, nguyên tắc Agile, **user story, Product Backlog, Scrum, Kanban, XP, kiểm thử liên tục, phản hồi sớm và giao sản phẩm tăng dần** để phân biệt **tách task theo tầng kỹ thuật** với **tạo lát cắt giá trị theo chiều dọc**. Mục tiêu không phải biến mọi đầu việc kỹ thuật thành tính năng độc lập, mà là xây dựng cách tổ chức công việc giúp nhóm **hoàn tất được kết quả có ý nghĩa, chứng minh bằng bằng chứng phù hợp và ra quyết định dựa trên phản hồi thật**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **ý tưởng lớn, Product Backlog Item (PBI), user story, task kỹ thuật, lát cắt dọc và Increment**.
2. Phát hiện dấu hiệu nhóm đang **chia nhỏ đầu việc nhưng chưa giao được giá trị có thể kiểm chứng**.
3. Giải thích vì sao chia theo **database → backend → frontend → QA** có thể làm tăng phụ thuộc, thời gian chờ và tích hợp muộn.
4. Viết user story có **đối tượng, mục đích và hành vi có thể kiểm tra**, không chỉ gắn nhãn “user story” cho task kỹ thuật.
5. Áp dụng các cách chia theo **luồng hành vi, kịch bản, quy tắc, nhóm dữ liệu, phân đoạn người dùng, mức độ phức tạp và giả thuyết**.
6. Giữ **Definition of Done, tiêu chí chấp nhận, bảo mật, dữ liệu và chất lượng** khi giảm phạm vi.
7. Nhận ra trường hợp cần **spike, enabler hoặc work item kỹ thuật**, cùng cách kiểm chứng kết quả của chúng mà không gọi nhầm là giá trị người dùng đã giao.
8. Tổ chức phản hồi sớm với Product Owner, Developers, kiểm thử, vận hành và người dùng liên quan.
9. Sử dụng **WIP, work item age, cycle time, throughput, outcome và guardrail** mà không bị đánh lừa bởi số thẻ Done.
10. Luyện chia một yêu cầu lớn thành các lát cắt có thứ tự, có thể thử và đủ an toàn để bổ sung dần.

## 2. Tách công việc nhỏ chưa chắc tạo được giá trị nhỏ

Hãy nhìn hai kiểu chia cho cùng một yêu cầu đăng ký workshop:

| Kiểu chia | Các phần được tạo ra | Điều có thể chứng minh khi một phần xong |
| --- | --- | --- |
| **Theo tầng hoặc chuyên môn** | Thiết kế database, tạo API, xây UI, viết test, cấu hình email | Một phần kỹ thuật đã hoàn tất; người dùng thường chưa thực hiện được hành trình |
| **Theo hành vi đầu cuối** | Xem workshop còn chỗ; đăng ký hợp lệ và nhận trạng thái; xem đăng ký của mình; hủy theo chính sách | Mỗi lát cắt hướng tới một hành vi/điều kiện kinh doanh có thể kiểm chứng xuyên qua các tầng cần thiết |

Tách theo tầng **không sai trong mọi trường hợp**. Developers vẫn cần task database, API, frontend và test để phối hợp. Sai lầm xuất hiện khi **coi việc hoàn tất các task thành bằng chứng giao giá trị** mà chưa tích hợp và xác nhận được hành vi tổng thể.

### 2.1. “Nhỏ” có ít nhất ba nghĩa khác nhau

- **Ít khối lượng:** Chỉ cần vài giờ để sửa một file.
- **Hẹp phạm vi:** Xử lý một trường hợp nghiệp vụ cụ thể thay vì mọi trường hợp.
- **Nhỏ về giá trị có thể kiểm chứng:** Hoàn tất được một hành vi, rủi ro hoặc giả thuyết đủ rõ để nhận phản hồi.

Một task đổi tên biến có thể rất nhỏ về khối lượng nhưng không tạo một kết quả sản phẩm riêng để người dùng kiểm chứng. Một lát cắt “học viên đăng ký một workshop còn chỗ theo chính sách cơ bản” có thể cần nhiều tầng kỹ thuật nhưng **đủ hẹp và có ý nghĩa**.

### 2.2. Giá trị không đồng nghĩa doanh thu ngay lập tức

Giá trị có thể là:

- Người dùng hoàn thành tác vụ nhanh và đúng hơn.
- Người học biết rõ trạng thái của mình.
- Giảm lỗi dữ liệu và rủi ro bảo mật.
- Xác minh một giả thuyết sản phẩm trước khi đầu tư lớn.
- Giảm thời gian chờ hoặc làm lại có bằng chứng.
- Tạo một năng lực kỹ thuật cần thiết để giao giá trị tiếp theo.

Tuy nhiên, cần **gọi đúng loại kết quả**: một spike xác minh công nghệ có thể tạo **giá trị học hỏi**, nhưng không có nghĩa một khả năng dành cho người dùng đã sẵn sàng phát hành.

## 3. Phân biệt user story, PBI, task và Increment

Các khái niệm này liên quan nhưng không thay thế nhau.

| Khái niệm | Vai trò | Ví dụ workshop | Sai lầm cần tránh |
| --- | --- | --- | --- |
| **Mục tiêu sản phẩm / Product Goal** | Hướng giá trị lâu dài | Học viên chủ động đăng ký workshop an toàn | Nhầm với danh sách task |
| **Ý tưởng lớn / epic (từ dùng tùy công cụ)** | Gom một nhu cầu rộng cần chia | Quản lý toàn bộ vòng đời đăng ký | Coi epic là việc hoàn tất trong một Sprint dù chưa rõ phạm vi |
| **Product Backlog Item** | Một hạng mục công việc để cải thiện sản phẩm | Đăng ký một workshop còn chỗ, có xác nhận | Mặc định PBI luôn phải có cùng định dạng |
| **User story** | Cách mô tả nhu cầu từ góc nhìn người hưởng lợi | Là học viên, tôi muốn biết mình đã có chỗ... | Chỉ gắn tiền tố “Là người dùng...” cho task kỹ thuật |
| **Task kỹ thuật** | Bước thực hiện, có thể thuộc một PBI | Thêm ràng buộc dữ liệu, tạo endpoint, viết test | Tính một task Done như một Increment |
| **Acceptance criteria** | Điều kiện để xác nhận hành vi/nhu cầu của PBI | Nếu workshop còn chỗ và đủ điều kiện, đăng ký có trạng thái xác nhận | Viết mơ hồ “API hoạt động tốt” |
| **Definition of Done (DoD)** | Cam kết chất lượng chung cho Increment trong Scrum | Đã tích hợp, được kiểm chứng, bảo mật/đặc tính cần thiết đạt | Hạ DoD để tăng số lượng Done |
| **Increment** | Phần bổ sung sản phẩm đáp ứng DoD và hoạt động cùng các phần trước | Luồng đăng ký mới tương thích với hành trình hiện có | Demo UI giả rồi gọi đã giao chức năng |

**User story không phải artifact bắt buộc riêng của Scrum**, và Scrum cũng không bắt buộc một kiểu chia task nhất định. Scrum hướng tới Increment có giá trị, đáp ứng Definition of Done và hỗ trợ Product Goal; nhóm có thể dùng user story khi cách diễn đạt ấy giúp hiểu nhu cầu.

### 3.1. Một PBI có thể có nhiều task

Ví dụ PBI **“Học viên đủ điều kiện đăng ký workshop còn chỗ và biết kết quả”** có thể chứa task:

1. Làm rõ quy tắc còn chỗ/đủ điều kiện.
2. Chọn cách kiểm soát tranh chỗ cuối.
3. Viết test giao dịch và phân quyền.
4. Xây endpoint phù hợp.
5. Kết nối giao diện và trạng thái.
6. Kiểm tra lỗi, quan sát và hỗ trợ.

Từng task hữu ích để **thực hiện và phối hợp**. Nhưng **PBI chưa Done** chỉ vì năm trong sáu task xong nếu hành vi trọng yếu chưa đạt DoD.

### 3.2. Không có công thức “mỗi story = đúng một tính năng lớn”

Một story tốt có thể rất nhỏ: “Học viên xem được danh sách workshop còn mở đăng ký theo bộ lọc mặc định”. Nó không nhất thiết có email, dashboard hay các tùy chọn nâng cao. Quan trọng là **phạm vi đủ rõ để kiểm chứng, giá trị có nghĩa và sự phụ thuộc được hiểu**.

## 4. Bốn phép thử cho một lát cắt có thể kiểm chứng

Trước khi đưa một hạng mục vào Sprint hoặc bắt đầu làm, nhóm có thể hỏi bốn nhóm câu:

### 4.1. Phép thử giá trị

- **Ai** nhận lợi ích? Học viên, nhân viên hỗ trợ, người vận hành hay một nhóm tích hợp?
- **Họ làm được gì hoặc biết thêm điều gì** sau khi hạng mục hoàn tất?
- Điều đó giúp **Product Goal hoặc giảm rủi ro** nào?
- Nếu bỏ hạng mục, hậu quả hoặc cơ hội bị mất là gì?

Nếu câu trả lời chỉ là **“backend có thêm class”**, có thể đây là task hoặc enabler chứ chưa phải lát cắt hành vi sản phẩm.

### 4.2. Phép thử kiểm chứng

- Có thể đưa ra **đầu vào, hành động, kết quả mong đợi** không?
- Có bằng chứng từ test, demo thật, log/metric hoặc nghiên cứu người dùng?
- Bằng chứng có kiểm tra **đường đi đầu cuối cần thiết** hay chỉ một mock?
- Những trường hợp thất bại và quyền truy cập đã được xét?

### 4.3. Phép thử hoàn tất và chất lượng

- Lát cắt có đạt **DoD/chính sách hoàn tất phù hợp**?
- Đã tích hợp với các phần liên quan, không làm hỏng hành vi cũ?
- Có cần dữ liệu thử, test đồng thời, phân quyền, khả năng vận hành?
- Nếu có lỗi, người dùng hoặc người vận hành biết trạng thái và cách xử lý?

### 4.4. Phép thử phản hồi và quyết định

- Sau khi xong, **ai có thể xem và phản hồi**?
- Học được điều gì khiến nhóm **giữ, sửa, bổ sung hoặc dừng**?
- Có thể phát hành an toàn cho đối tượng phù hợp, hoặc ít nhất **được kiểm chứng trong môi trường đáng tin**?
- Hạng mục có bị phụ thuộc vào năm PBI chưa Done mới kiểm tra được không?

Lát cắt chưa cần mở cho toàn bộ người dùng ngay, nhưng phải rõ **đã kiểm chứng gì**, **chưa kiểm chứng gì** và **điều kiện phát hành nào còn thiếu**. Tránh gọi một mock/demo hình ảnh là bằng chứng mọi hành vi production đã an toàn.

## 5. Chia ngang và chia dọc: hình dung bằng luồng công việc

**Chia ngang (*horizontal slicing*)** tập trung vào một tầng hoặc chuyên môn; **chia dọc (*vertical slicing*)** tập trung vào một hành vi có ý nghĩa đi qua các tầng cần thiết.

~~~mermaid
flowchart TB
    subgraph H["Chia ngang: nhiều tầng xong rời rạc"]
        direction TB
        H1["Task A: Database"] --> H2["Task B: Backend"]
        H2 --> H3["Task C: Frontend"]
        H3 --> H4["Task D: Tích hợp và kiểm thử"]
        H4 --> H5["Người dùng chỉ nhận giá trị ở cuối"]
    end
    subgraph V["Chia dọc: từng lát cắt có thể kiểm chứng"]
        direction TB
        V1["Lát cắt 1: Xem workshop còn mở"]
        V2["Lát cắt 2: Đăng ký đúng một chỗ"]
        V3["Lát cắt 3: Xem lại trạng thái"]
        V1 --> V2 --> V3
    end
    H5 -.-> C["So sánh: thời điểm có bằng chứng về giá trị"]
    V3 -.-> C
~~~

Sơ đồ **minh họa cách tổ chức công việc**, không có nghĩa một lát cắt dọc tự động không có phụ thuộc. Lát cắt 2 có thể cần dùng dữ liệu/khả năng từ lát cắt 1, nhưng **từng bước phải có tiêu chí hoàn tất và có thể được kiểm chứng ở thời điểm thích hợp**.

### 5.1. Vì sao chia theo phòng ban dễ dẫn tới tích hợp muộn?

Khi mỗi chuyên môn nhận một “gói việc” lớn:

- Database được thiết kế theo giả định chưa kiểm tra từ hành vi thật.
- Backend cung cấp API rồi phải chờ frontend thử.
- Frontend dùng mock và báo Done dù contract chưa khớp.
- QA nhận tất cả phần việc gần cuối Sprint.
- Lỗi yêu cầu và giao dịch phát hiện khi **không còn nhiều thời gian điều chỉnh**.
- Mọi người tối ưu phần đã bàn giao, ít ai chịu trách nhiệm cho **luồng người dùng đầy đủ**.

### 5.2. Chia dọc không bắt buộc từng người tự làm mọi tầng

Một nhóm cross-functional có thể phối hợp để cùng hoàn tất lát cắt: có người chuyên dữ liệu, người chuyên giao diện và người chuyên test. Điều cần thay là **cách cùng chịu trách nhiệm hoàn tất hành vi**, không phải ép mọi Developer thành chuyên gia ở tất cả lĩnh vực.

## 6. Vì sao nhiều thẻ Done có thể làm ảo giác tiến độ?

Xem một Sprint với mười task thuộc cùng hành trình đăng ký:

| Hạng mục | Trạng thái cuối Sprint | Người dùng nhận được gì? |
| --- | --- | --- |
| Tạo bảng đăng ký | Done | Chưa thấy hành vi |
| Tạo entity | Done | Chưa thấy hành vi |
| Tạo repository | Done | Chưa thấy hành vi |
| Tạo endpoint đăng ký | Done theo task | Chưa nối luồng và test quyền |
| Giao diện form | Done với mock | Chưa xác nhận thật |
| CSS/hiển thị nút | Done | Chưa xác nhận thật |
| Tài liệu endpoint | Done | Người dùng chưa đăng ký được |
| Tạo email template | Done | Chưa có trạng thái gửi |
| Integration test đồng thời | Chưa Done | Chưa có bằng chứng không vượt sức chứa |
| Luồng giao diện–API–dữ liệu | Chưa Done | Chưa có hành trình end-to-end |

Nếu chỉ đếm task, nhóm báo **8/10 = 80% hoàn thành**. Nhưng mục tiêu người học đăng ký an toàn có thể vẫn **0% được chứng minh ở mức hành vi trọn vẹn**.

### 6.1. Tỷ lệ task Done không tương đương tỷ lệ giá trị

Tám task đầu không nhất thiết tương đương về khối lượng, rủi ro hoặc giá trị với hai task còn lại. Không có lý do để suy ra **80% số task = 80% giá trị**. Đặc biệt, hai task cuối có thể chứa rủi ro quyết định khả năng phát hành.

### 6.2. “90% xong” kéo dài nhiều tuần

Khi nhiều công việc kỹ thuật được xem như gần xong nhưng không có tiêu chuẩn Done đầu cuối, tiến độ dễ treo ở trạng thái “chỉ còn tích hợp và test”. Tích hợp và kiểm chứng **không phải phần việc nhỏ mặc định**; chúng có thể bộc lộ giả định sai cần thiết kế lại.

### 6.3. Ngược lại, nhiều lát cắt nhỏ không tự động là tốt

Chia một story thành mười thẻ “đổi label”, “đổi màu”, “đổi vị trí nút” có thể tăng throughput nhưng **không tăng giá trị** nếu không gắn với một thay đổi hành vi hoặc giả thuyết có thể quan sát. Quy mô nhỏ là **phương tiện**, không phải mục tiêu tự thân.

## 7. Dấu hiệu nhận biết backlog bị chia thành đầu việc thuần kỹ thuật

Một backlog có nguy cơ chia sai khi xuất hiện nhiều dấu hiệu:

1. Tên PBI đều bắt đầu bằng **“Tạo DB”, “Làm API”, “Làm UI”, “Viết test”** và thiếu nhu cầu sử dụng.
2. Người dùng hoặc Product Owner không thể hiểu **điều gì sẽ thay đổi** khi thẻ Done.
3. Một story chỉ kiểm chứng được sau khi **năm story khác Done**.
4. Mỗi nhóm chuyên môn đánh dấu phần mình Done nhưng không ai kiểm tra **hành trình tổng thể**.
5. Acceptance criteria nói “code compile”, “endpoint trả 200” nhưng không nêu hành vi/ngoại lệ cần bảo vệ.
6. QA hoặc security luôn nhận việc **sát cuối** sau khi phần khác báo hoàn tất.
7. Dashboard đếm nhiều thẻ Done nhưng Sprint Review không có **Increment đáp ứng DoD**.
8. Công việc bị chuyển trạng thái để làm đẹp cycle time dù vẫn chưa tích hợp.
9. Story points được chia theo người hoặc tầng rồi dùng để đánh giá **năng suất cá nhân**.
10. Khi hỏi “nếu dừng dự án hôm nay, người dùng có thêm khả năng gì?”, câu trả lời chỉ là **“đã có khung hệ thống”**.

### 7.1. Không kết luận chỉ từ tên thẻ

Một PBI **“Nâng cấp pipeline tích hợp dữ liệu”** có thể là enabler cần thiết và có giá trị giảm rủi ro. Vấn đề là **tổ chức mô tả, ưu tiên và kiểm chứng kết quả ra sao**, không chỉ tiêu đề có chữ API hay không.

### 7.2. Một câu hỏi mạnh trong refinement

> **“Nếu chỉ PBI này hoàn tất đúng chất lượng, chúng ta có thể kiểm chứng được điều gì mới mà trước đó chưa thể kiểm chứng?”**

Nếu câu trả lời phụ thuộc toàn bộ vào những phần còn chưa xây, nhóm nên **xem lại ranh giới PBI** hoặc **chủ động nhận đây là enabler** với kết quả học hỏi/kỹ thuật rõ, không gọi nhầm tính năng đã giao.

## 8. User story cần mô tả hành vi và giá trị, không phải câu thần chú

Một cách diễn đạt thông dụng:

> **Là [đối tượng], tôi muốn [khả năng/hành vi], để [lợi ích hoặc kết quả].**

Ví dụ:

> **“Là học viên đủ điều kiện, tôi muốn đăng ký một workshop còn chỗ và nhận trạng thái xác nhận, để biết mình có thể tham gia hay không.”**

Nhưng định dạng này chỉ là **điểm bắt đầu cuộc trao đổi**. Một câu có đủ ba ô nhưng vẫn không có tiêu chí chấp nhận, quy tắc và rủi ro thì chưa đủ để nhóm làm đúng.

### 8.1. Ví dụ story giả tạo

> “Là backend Developer, tôi muốn tạo repository cho bảng đăng ký, để backend có repository.”

Câu này **có thể mô tả task kỹ thuật**, nhưng không đưa ra hành vi người dùng hoặc kết quả học hỏi rõ. Nếu nó thuộc một PBI đăng ký hoàn chỉnh, nên giữ như task dưới PBI. Nếu cần công việc nền độc lập, mô tả **rủi ro được giảm hoặc khả năng kỹ thuật cần chứng minh**.

### 8.2. Ba thành phần thực hành của một story

- **Card:** Một tên ngắn để nhớ nhu cầu.
- **Conversation:** Trao đổi với Product Owner, người hiểu nghiệp vụ, Developers, kiểm thử và bên chịu tác động.
- **Confirmation:** Những ví dụ/điều kiện xác nhận được hành vi mong đợi.

Không cần xem ba chữ C là luật bắt buộc của Scrum; đây là **cách thực hành giúp user story không biến thành một dòng giao việc**.

### 8.3. Khi user story chưa phải cách diễn đạt tốt nhất

Một spike “đánh giá khả năng tái hiện lỗi tranh chỗ cuối trên database đang dùng” không có người dùng trực tiếp thực hiện hành vi mới. Thay vì gượng ép thành user story, nên nêu **câu hỏi kỹ thuật, giới hạn thời gian, đầu ra và cách dùng kết quả**.

## 9. Tình huống xuyên suốt: đăng ký workshop và ranh giới giá trị

**Bối cảnh học tập:** Nền tảng tổ chức workshop có số chỗ giới hạn. Học viên đăng nhập, xem buổi học, đăng ký và biết trạng thái của mình. Product Goal là **giúp người học chủ động đặt chỗ đáng tin và giảm xử lý thủ công**.

### 9.1. Yêu cầu lớn ban đầu

> “Xây module quản lý đăng ký workshop, gồm danh sách, bộ lọc, đăng ký, giữ chỗ cuối, email, hủy, lịch tháng, dashboard, báo cáo, phân quyền và tích hợp vận hành.”

Yêu cầu này có nhiều loại giá trị và rủi ro. Nếu giữ nguyên một PBI lớn rồi chia task theo tầng, nhóm khó chứng minh tiến độ theo giá trị.

### 9.2. Phân biệt lõi và tiện ích

| Khả năng | Giá trị/rủi ro | Có thể xem là lát cắt riêng? |
| --- | --- | --- |
| Xem workshop đang mở đăng ký | Người học tìm được buổi phù hợp | Có, nếu dữ liệu đúng và hành vi có thể thử |
| Đăng ký workshop còn chỗ | Người học giữ vị trí hợp lệ | Có, nhưng phải bảo vệ đồng thời/trạng thái theo rủi ro |
| Xem đăng ký của chính mình | Người học kiểm chứng kết quả | Có, nếu quyền và dữ liệu đúng |
| Hủy theo chính sách | Người học thay đổi quyết định hợp lệ | Có, nếu chính sách hủy/hoàn chỗ được làm rõ |
| Email xác nhận | Bổ sung kênh thông tin | Có thể tách nếu không là điều kiện bắt buộc của đăng ký |
| Bộ lọc nâng cao | Tìm nhanh trong danh sách lớn | Có thể làm sau luồng tìm kiếm tối thiểu |
| Lịch tháng | Trải nghiệm thay thế | Có thể hoãn nếu không bắt buộc |
| Báo cáo vận hành | Giám sát và đối soát | Phải xác định phần nào bắt buộc ngay |

**Lưu ý:** Nhãn “có thể tách” chưa quyết định thứ tự hay tính bắt buộc. Nếu có nghĩa vụ hợp đồng, chính sách nghiệp vụ hoặc an toàn yêu cầu hủy/email/báo cáo ngay khi mở đăng ký, nhóm **không được tự ý hoãn**.

### 9.3. Định nghĩa người nhận giá trị

Không chỉ có học viên. Nhân viên Support cần thấy trạng thái đối soát để xử lý lỗi; người vận hành cần alert; Product Owner cần hiểu số người đăng ký thành công. Một lát cắt có thể mang **giá trị cho vai trò nội bộ**, nhưng phải nêu **kết quả kiểm chứng được**, không chỉ tên chức năng kỹ thuật.

## 10. So sánh hai cách chia cùng yêu cầu

### 10.1. Phân rã theo tầng — nguy cơ tích hợp muộn

| Thẻ | Kết quả kỹ thuật dự kiến | Có thể demo hành vi người dùng? |
| --- | --- | --- |
| T1. Tạo bảng và entity | Dữ liệu lưu được | Chưa |
| T2. Thêm endpoint đăng ký | API có đường gọi | Chưa chắc đúng giao dịch/điều kiện |
| T3. Tạo form đăng ký | UI nhận input, có thể dùng mock | Chưa chắc kết nối thật |
| T4. Thêm queue gửi email | Hệ thống có thể phát sự kiện | Chưa chắc nhận trạng thái đúng |
| T5. Viết integration tests | Kiểm tra liên tầng | Chỉ lúc này mới biết giả định đã khớp |
| T6. Kết nối UI/API | Hành trình đầu cuối | Rủi ro tập trung cuối luồng |

Cách chia này có thể dùng **làm task nội bộ**, nhưng nếu xem T1–T4 là **bốn Increment độc lập**, dashboard sẽ tạo nhận thức sai.

### 10.2. Phân rã theo lát cắt dọc — ưu tiên kiểm chứng sớm

| PBI/lát cắt | Điều người dùng làm được | Kiểm chứng tối thiểu |
| --- | --- | --- |
| S1. Xem workshop mở đăng ký | Nhìn được buổi, thời điểm, trạng thái còn chỗ đáng tin | API và UI dùng cùng nguồn dữ liệu, test điều kiện mở |
| S2. Đăng ký một workshop còn chỗ | Đặt chỗ hợp lệ, nhận kết quả rõ | Trạng thái, phân quyền, giao dịch và test concurrent |
| S3. Xem đăng ký của mình | Xác minh trạng thái đã lưu | Kiểm tra chủ thể và truy cập tài khoản khác |
| S4. Hủy theo chính sách đã xác minh | Hủy đúng điều kiện, không làm sai sức chứa | Quy tắc hủy, quyền, trạng thái và test cạnh tranh |
| S5. Nhận thông báo sau xác nhận | Có kênh cập nhật bổ sung | Contract, retry/idempotency, không báo sai |
| S6. Tìm kiếm/lọc nâng cao | Tìm workshop nhanh hơn | Acceptance examples và quan sát thực |

### 10.3. Không phải mỗi lát cắt đều phải độc lập với tất cả phần trước

S2 sử dụng dữ liệu workshop mà S1 đã giới thiệu; S3 dùng đăng ký từ S2. **Tính tăng dần** nghĩa là mỗi bước **bổ sung khả năng có thể kiểm chứng trên nền sản phẩm hiện tại**, không bắt buộc “mỗi story không có dependency nào”.

### 10.4. Không chia phạm vi an toàn thành giai đoạn gây hại

Không được tách thành:

- “Đăng ký hoạt động nhưng chưa kiểm soát vượt sức chứa” rồi **mở cho người dùng thật**.
- “Xem trạng thái nhưng chưa kiểm tra chủ sở hữu dữ liệu” rồi phát hành.
- “Gửi email xác nhận dù giao dịch chưa được xác nhận” rồi gọi là hoàn tất.

Nếu kiểm soát đồng thời, phân quyền hoặc chính xác trạng thái là điều kiện bắt buộc, chúng **thuộc ranh giới an toàn của lát cắt tương ứng**, không phải tùy chọn trang trí.

## 11. Phép thử đầu cuối cho lát cắt đăng ký tối thiểu

Lát cắt **“Học viên đủ điều kiện đăng ký workshop còn chỗ và nhận xác nhận”** có thể phải vượt qua các trường hợp:

1. Workshop tồn tại, đang mở đăng ký, còn chỗ và học viên đủ điều kiện.
2. Không đăng ký được nếu workshop hết chỗ hoặc đã đóng.
3. Không được xem/sửa dữ liệu đăng ký của học viên khác.
4. Khi hai yêu cầu tranh chỗ cuối, trạng thái cuối cùng không vượt sức chứa.
5. Không sinh xác nhận trùng hoặc kết quả mơ hồ khi client gửi lại sau timeout theo chính sách đã thống nhất.
6. Giao diện biểu thị kết quả dựa trên **nguồn dữ liệu đáng tin**, không chỉ nhờ một thông báo thành công giả.
7. Hệ thống có log/quan sát và đường hỗ trợ phù hợp mức rủi ro.

### 11.1. Một số acceptance examples bằng Gherkin

~~~gherkin
Feature: Đăng ký workshop còn chỗ

  Scenario: Học viên hợp lệ đăng ký thành công
    Given học viên đã đăng nhập và đủ điều kiện
    And workshop đang mở đăng ký và còn 2 chỗ
    When học viên xác nhận đăng ký
    Then hệ thống lưu đúng một đăng ký được xác nhận
    And học viên thấy trạng thái "Đã xác nhận"
    And số chỗ còn lại phản ánh trạng thái đã lưu

  Scenario: Workshop đã hết chỗ
    Given workshop đang mở đăng ký nhưng không còn chỗ
    When học viên yêu cầu đăng ký
    Then hệ thống không tạo đăng ký được xác nhận
    And học viên nhận thông báo phù hợp

  Scenario: Không cho xem đăng ký của người khác
    Given học viên A đã đăng ký workshop
    And học viên B đã đăng nhập
    When học viên B yêu cầu xem đăng ký của A
    Then yêu cầu bị từ chối theo chính sách phân quyền
    And dữ liệu riêng của A không bị tiết lộ
~~~

Các bước là **mô tả hành vi**, không phải bộ mã test thực thi sẵn. Mỗi kịch bản phải được nối với cách kiểm chứng phù hợp và dữ liệu có kiểm soát.

### 11.2. Kiểm thử đồng thời không chỉ là hai lệnh nối tiếp

Khi chỉ còn một chỗ và hai yêu cầu tới gần như cùng lúc, cần thẩm định **nguồn sự thật, transaction/constraint, isolation hoặc cơ chế phù hợp của kiến trúc thực tế**. Một unit test với repository giả có thể xác minh một phần logic, nhưng **chưa chứng minh database thật xử lý tranh chỗ đúng**.

### 11.3. Test và phản hồi cần có thể tái hiện

Với một lỗi cạnh tranh, nhóm nên lưu **điều kiện bắt đầu, dữ liệu, cách phát đồng thời, kết quả thực tế, kết quả mong đợi và phiên bản code/môi trường**. Nếu chỉ nói “QA thấy lỗi đôi khi xảy ra”, nhóm khó biết đã sửa và có thể giảm nguy cơ quay lại không.

## 12. Definition of Done và acceptance criteria: hai lớp kiểm chứng khác nhau

**Acceptance criteria** mô tả những ví dụ/điều kiện cụ thể của PBI. **Definition of Done** là chuẩn chất lượng chung cho Increment trong Scrum.

| Điều kiện | Chủ yếu thuộc phạm vi nào? | Ví dụ |
| --- | --- | --- |
| Workshop hết chỗ không được xác nhận thêm | Acceptance criteria | Quy tắc nghiệp vụ của lát cắt đăng ký |
| Người dùng chỉ thấy dữ liệu đăng ký của mình | Acceptance criteria, đồng thời có thể liên hệ chuẩn bảo mật chung | Kiểm chứng phân quyền |
| Increment được tích hợp và kiểm thử theo tiêu chuẩn nhóm | Definition of Done | Build/test bắt buộc đạt |
| Không đưa secret vào mã hoặc log không an toàn | Chuẩn chất lượng/bảo mật chung | Review, kiểm tra phù hợp |
| UI phản ánh đúng trạng thái lưu | Acceptance criteria và kiểm chứng tích hợp | Hành trình người dùng end-to-end |
| Có cách chẩn đoán lỗi quan trọng | Chuẩn vận hành tùy mức rủi ro | Log/metric/runbook tương ứng |

### 12.1. DoD không tự động đồng nhất với “đã release”

Một Increment đạt DoD trong Scrum **có thể sẵn sàng sử dụng** và có thể được giao cho stakeholder trước Sprint Review, nhưng quyết định mở cho người dùng thật còn tùy **quyền phát hành, chính sách sản phẩm, nghĩa vụ bảo mật/vận hành và điều kiện release phù hợp**.

Nếu một PBI chưa đạt DoD, **không được xem là Increment Done** chỉ vì demo trên mock trông đẹp. Nhưng cũng không nên mặc định mọi PBI đã Done phải lập tức mở rộng tới tất cả người dùng nếu rollout cần kiểm soát.

### 12.2. Thu hẹp phạm vi khác hạ chuẩn chất lượng

Đúng:

> “Lần đầu chỉ hỗ trợ đăng ký workshop mở, không có tính năng lịch tháng nâng cao; kiểm soát dữ liệu và phân quyền vẫn đầy đủ.”

Sai:

> “Lần đầu cho phép đăng ký nhưng chưa xử lý tranh chỗ cuối; Sprint sau mới sửa vì lần này cần demo số lượng chức năng.”

**Phạm vi có thể thương lượng trong giới hạn nghĩa vụ; tính đúng và an toàn cần giữ theo rủi ro thực.**

## 13. Các kỹ thuật chia lát cắt theo hành vi

Không có một công thức chung cho mọi user story. Khi một story quá lớn, hãy hỏi **có những khác biệt hành vi nào có thể đưa ra phản hồi độc lập**, thay vì chỉ tìm cách giao bớt file cho từng người.

| Kỹ thuật | Câu hỏi chia | Ví dụ workshop | Điều cần giữ |
| --- | --- | --- | --- |
| **Các bước của luồng** | Bước nào tạo một kết quả hoàn chỉnh? | Xem workshop → đăng ký → xem trạng thái → hủy | Không tạo bước vô dụng hoặc gây hiểu nhầm |
| **Kịch bản nghiệp vụ** | Happy path và trường hợp nào có thể tách? | Đăng ký thường; đăng ký theo danh sách chờ | Happy path vẫn phải an toàn và đúng |
| **Quy tắc nghiệp vụ** | Có nhóm quy tắc nào có thể bổ sung sau? | Buổi miễn phí trước; chính sách ưu đãi phức tạp sau | Không bỏ quy tắc bắt buộc của lần dùng đầu |
| **Phân đoạn người dùng** | Có nhóm người dùng có phạm vi nhu cầu khác? | Học viên nội bộ trước, đối tác sau | Quyền và cam kết cho từng nhóm vẫn đúng |
| **Dữ liệu đầu vào** | Tập dữ liệu đơn giản nào đủ làm tác vụ thật? | Workshop một lịch cố định trước lịch nhiều ca | Không giả dữ liệu production thành công |
| **Thao tác theo trường hợp sử dụng** | Read-only và write path có thể tách? | Xem workshop trước đăng ký | Không coi chỉ có DB/API là giá trị đọc được |
| **Phức tạp trải nghiệm** | Giao diện đơn giản giải quyết nhu cầu chưa? | Danh sách trước lịch tháng | Kết quả nghiệp vụ không bị giảm chất lượng |
| **Tích hợp** | Có giá trị nào trước khi thêm kênh phụ? | Trạng thái trong ứng dụng trước email nhắc | Nếu email bắt buộc theo cam kết thì không thể hoãn |
| **Mức hỗ trợ/khả năng mở rộng** | Có thể bắt đầu với lưu lượng đã định nghĩa? | Nhóm người dùng thử được phép trước khi mở rộng | Guardrail và thẩm quyền release rõ |
| **Khám phá/giảm rủi ro** | Có một câu hỏi cần kiểm chứng trước khi chọn giải pháp? | Spike về concurrency trên database thật | Ghi đúng là học hỏi, không giả giao tính năng |

### 13.1. “Dễ nhất trước” không phải nguyên tắc duy nhất

Một lát cắt nhỏ nhưng ít giá trị có thể làm nhóm bận mà không giúp giảm bất định. Có lúc nên ưu tiên **rủi ro lớn trước**: ví dụ thẩm định tranh chỗ cuối và phân quyền trước khi xây email hay lịch tháng.

### 13.2. Chọn hướng chia theo điều cần học

- Nếu chưa biết người dùng hiểu trạng thái không → chia theo **giao diện/thông tin phản hồi** có thể thử.
- Nếu rủi ro nằm ở giao dịch → làm **lát cắt đăng ký tối thiểu và test đồng thời**.
- Nếu sợ dependency đối tác → thử **contract/integration path tối thiểu** để giảm rủi ro.
- Nếu PBI chờ QA lâu → giảm kích thước lô, cùng viết examples và **test sớm**.

## 14. Chia theo kịch bản: happy path và ngoại lệ đúng cách

Một kỹ thuật phổ biến là làm rõ **kịch bản thông thường** trước, sau đó xem ngoại lệ nào có thể đưa vào phần tiếp theo. Nhưng có hai loại ngoại lệ rất khác nhau.

### 14.1. Ngoại lệ có thể hoãn nếu không bắt buộc

Ví dụ **đăng ký workshop cơ bản** có thể chưa hỗ trợ:

- Mã giảm giá nhiều tầng.
- Danh sách chờ tự động.
- Đổi từ một workshop sang workshop khác.
- Gợi ý khóa học dựa trên sở thích.
- Gửi SMS nhắc lịch.

Nhóm vẫn có thể tạo một luồng đăng ký **đúng cho phạm vi cho phép**, với điều kiện không có nghĩa vụ hoặc quy tắc hiện hành yêu cầu các khả năng trên.

### 14.2. Ngoại lệ không thể bỏ để “nhỏ”

Những trường hợp như **workshop đã hết chỗ, người không có quyền, request gửi lại, dữ liệu không hợp lệ, giao dịch bị tranh chấp** có thể trực tiếp quyết định tính đúng và an toàn của hành vi cốt lõi.

Nếu sản phẩm cho phép nhiều người đăng ký cùng lúc, không nên xem cạnh tranh chỗ cuối là một “edge case optional” có thể mở sau khi phát hành dù đã biết nó có thể gây dữ liệu sai.

### 14.3. Quy tắc thực dụng

> **“Bỏ một trường hợp chỉ khi phạm vi được phép sử dụng đã được giới hạn rõ và phần đang mở vẫn đúng, an toàn, đáng tin.”**

Nếu chưa thể giới hạn phạm vi để bỏ ngoại lệ, hạng mục cần đủ kiểm chứng hoặc chưa nên phát hành.

## 15. Chia theo luồng hoạt động mà không tạo mảnh vụn

Yêu cầu rộng **“Quản lý đăng ký workshop”** chứa nhiều hành trình có thể xem là những giá trị tăng dần:

1. Học viên **tìm** buổi đang mở.
2. Học viên **chọn và đăng ký** đúng một chỗ.
3. Học viên **xem lại trạng thái**.
4. Học viên **hủy hợp lệ** khi có nhu cầu.
5. Học viên **nhận thông báo** theo chính sách.
6. Support **đối soát** khi gặp sự cố.

### 15.1. Chọn một đường đi từ đầu tới cuối

Thay vì xây toàn bộ tính năng cho tất cả hành trình trước khi tích hợp, chọn một hành trình nhỏ nhưng **khép kín**. Ví dụ:

> “Học viên đã đăng nhập, đủ điều kiện, chọn một workshop còn chỗ trong danh sách và nhận kết quả xác nhận đúng từ hệ thống.”

Nó có thể cần cả UI/API/database/test, nhưng **bề rộng nghiệp vụ nhỏ hơn** nhiều so với toàn bộ module.

### 15.2. Đặt điều kiện rõ cho phần chưa hỗ trợ

Nếu chưa có danh sách chờ:

- Người dùng không thấy nút “Tham gia danh sách chờ”.
- Hệ thống không tạo một trạng thái chờ không được hỗ trợ.
- Trường hợp hết chỗ được thông báo rõ.
- Backlog ghi rằng danh sách chờ là khả năng tương lai, không phải phần đã hoàn tất.

Đó là **giới hạn sản phẩm minh bạch**, không phải “ẩn một nửa chức năng lỗi”.

### 15.3. Đừng chia thành “một click” nếu không có kết quả

Một PBI “nút đăng ký bấm được” mà không lưu trạng thái thật thường **không có giá trị đăng ký**. Nó có thể là task hoặc prototype phục vụ thử thiết kế, nhưng cần nói rõ **đang kiểm chứng thao tác UI hay đã giao được đăng ký thật**.

## 16. Chia theo quy tắc nghiệp vụ: từ đơn giản tới phức tạp

Quy tắc đăng ký có thể gồm:

- Workshop có số chỗ giới hạn.
- Học viên phải có tài khoản và đủ điều kiện.
- Một người có thể hoặc không thể đăng ký cùng buổi nhiều lần.
- Có chính sách hủy trước giờ học.
- Có danh sách chờ, ưu tiên hoặc mã giảm giá.
- Có mức quyền khác nhau cho nhân viên hỗ trợ.

### 16.1. Thứ tự ví dụ

| Lát cắt | Phạm vi quy tắc | Vì sao có thể kiểm chứng |
| --- | --- | --- |
| R1. Workshop chỉ có một loại chỗ | Hiển thị đúng sức chứa và tình trạng mở | Kiểm tra danh sách và dữ liệu nguồn |
| R2. Đăng ký với quy tắc đủ điều kiện cơ bản | Xác nhận không vượt sức chứa, không trùng theo chính sách | Test nghiệp vụ, đồng thời và trạng thái |
| R3. Hủy theo một chính sách thống nhất | Giải phóng chỗ nếu đúng điều kiện | Test hủy, quyền, đối soát dữ liệu |
| R4. Quy tắc đặc biệt theo loại workshop | Một số workshop có điều kiện hoặc ưu tiên riêng | Test từng nhóm quy tắc |
| R5. Danh sách chờ | Người chưa có chỗ có thể chờ hợp lệ | Test thứ tự, chuyển trạng thái, thông báo |

**Điểm quan trọng:** Phần R2 vẫn phải kiểm soát chỗ và quyền trong phạm vi đang hoạt động. “Quy tắc đơn giản” không có nghĩa cho phép sai dữ liệu vì chưa làm R4/R5.

### 16.2. Khi nào không tách được một quy tắc?

Nếu quy định bắt buộc nói **mọi đăng ký phải kiểm tra học viên đủ 18 tuổi hoặc có sự đồng ý hợp lệ**, không được mở đăng ký cho nhóm thuộc phạm vi ấy mà bỏ kiểm tra. Khi đó quy tắc **thuộc ranh giới chất lượng/tuân thủ của lát cắt**.

### 16.3. Quy tắc phụ thuộc nhau phải được biểu diễn thật

Hủy chỗ có thể ảnh hưởng danh sách chờ và số chỗ trống. Nếu phần hủy chưa xử lý đúng sức chứa, **đừng đánh dấu phần hủy Done** chỉ vì UI xóa dòng khỏi danh sách.

## 17. Chia theo dữ liệu và đối tượng sử dụng

Một yêu cầu có thể quá lớn do phải hỗ trợ nhiều loại dữ liệu hoặc người dùng. Có thể chọn **một tập đại diện, hợp lệ và đủ tạo kết quả hữu ích** trước.

### 17.1. Chia theo nhóm workshop

Ví dụ:

- Giai đoạn đầu hỗ trợ workshop **một ca, một địa điểm**, có số chỗ hữu hạn.
- Sau đó thêm workshop **nhiều ca, có điều kiện đổi lịch**.
- Cuối cùng thêm workshop **kết hợp online/offline, danh sách chờ, nhiều loại chỗ**.

Nhưng nếu một workshop nhiều ca thuộc cam kết mở bán ngày D, không thể tùy ý bỏ nó chỉ vì nó khó hơn; cần **làm rõ phạm vi và quyền quyết định**.

### 17.2. Chia theo nhóm người dùng

Một release có thể được thử trên **nhân viên nội bộ được phép** để xác nhận trải nghiệm hoặc vận hành, rồi mở rộng cho người học bên ngoài theo điều kiện kiểm soát.

**Nhóm thử nghiệm không tự tạo giá trị production cho mọi người dùng.** Nêu rõ tính chất pilot, khả năng đã kiểm chứng và nghĩa vụ vẫn phải đáp ứng khi mở thực tế.

### 17.3. Tránh dữ liệu giả dẫn tới quyết định sai

Một demo dùng ba workshop hard-code có thể giúp kiểm tra cách trình bày UI. Nhưng nó không chứng minh luồng thật hoạt động khi số chỗ thay đổi theo đăng ký đồng thời.

Nên tách câu hỏi:

- **Prototype:** Người dùng có hiểu cách chọn workshop không?
- **Increment tích hợp:** Hệ thống thật có đưa ra trạng thái đúng và giữ dữ liệu nhất quán không?

Cả hai có thể tạo học hỏi, nhưng **không nên đánh đồng mức bằng chứng**.

## 18. Chia theo giao diện và trải nghiệm: bỏ tiện ích, không bỏ ý nghĩa

Nhiều yêu cầu UI được gộp trong một PBI lớn. Có thể chia theo **mức tiện dụng tăng dần**:

| Phiên bản | Hành vi có ích | Phần có thể để sau |
| --- | --- | --- |
| V1. Danh sách workshop rõ | Xem tên, lịch, điều kiện, trạng thái còn chỗ | Lịch tháng, animation |
| V2. Tìm kiếm cơ bản | Tìm theo tên/địa điểm | Bộ lọc nhiều điều kiện và lưu truy vấn |
| V3. Lọc nâng cao | Lọc theo thời gian, loại workshop | Cá nhân hóa tự động |
| V4. Gợi ý thông minh | Đề xuất buổi phù hợp có bằng chứng giá trị | Tùy biến ít được dùng |

### 18.1. Đừng mặc định accessibility là polish

Khả năng sử dụng bàn phím, tên nhãn rõ ràng, trạng thái lỗi có thể hiểu và yêu cầu tiếp cận theo chính sách **không nên bị cắt như animation trang trí**. Mức bắt buộc phụ thuộc đối tượng, cam kết và tiêu chuẩn áp dụng.

### 18.2. Tránh “bản tối giản” làm người dùng hiểu sai

Nếu giao diện ban đầu hiển thị **“Còn 1 chỗ”** trong khi backend cho phép hai xác nhận đồng thời, thiếu sót không nằm ở giao diện đẹp/xấu mà ở **tính đúng của trải nghiệm**. Cần nguồn trạng thái đáng tin và cách thông báo kết quả thích hợp.

## 19. Lát cắt theo giả thuyết: kiểm chứng nhu cầu trước khi xây quá nhiều

Không phải mọi yêu cầu cần bắt đầu bằng code production. Đôi khi bất định lớn nhất là **người dùng có thật sự cần tính năng**.

### 19.1. Ví dụ giả thuyết sản phẩm

> “Học viên thường bỏ dở đăng ký vì không hiểu trạng thái còn chỗ và điều kiện tham gia, chứ không phải vì thiếu lịch tháng.”

Cách thử:

1. Phỏng vấn/quan sát một số học viên phù hợp.
2. Kiểm tra cách họ tìm buổi và xác minh trạng thái.
3. Dùng prototype hoặc lát cắt nhỏ để hỏi về thông tin cần thiết.
4. Xác định hành vi nào thay đổi, điều gì chưa rõ.
5. Đưa kết quả vào Product Backlog trước khi đầu tư lịch tháng phức tạp.

### 19.2. Không gọi prototype là tính năng đã hoàn tất

Một prototype Figma hoặc UI với dữ liệu giả có thể là **bằng chứng về khả năng hiểu giao diện**, nhưng chưa xác nhận bảo mật, dữ liệu, hiệu năng hay vận hành production. Cần ghi **mục tiêu thử và giới hạn**.

### 19.3. Lát cắt tạo giá trị học hỏi

Nếu kết quả thử cho thấy người dùng chỉ cần một nhãn trạng thái rõ, nhóm có thể **bỏ hoặc hoãn** một hạng mục lịch tháng lớn. Giá trị ở đây là **tránh làm một thứ ít hữu ích**, không phải đếm số màn hình đã thiết kế.

## 20. Spike và enabler: công việc kỹ thuật cần thiết nhưng phải gọi đúng

Không phải mọi PBI đều là tính năng người dùng. Một nhóm Agile vẫn cần:

- Điều tra giới hạn công nghệ.
- Nâng cấp CI/test để giao sản phẩm an toàn.
- Tạo công cụ đối soát dữ liệu.
- Cải thiện môi trường để phát hiện lỗi nhanh.
- Refactor ranh giới một module nhằm giảm nguy cơ thay đổi.
- Chuẩn bị đường migration có kiểm chứng.

### 20.1. Spike cần một câu hỏi và timebox

Ví dụ:

> **Spike:** “Trong một khoảng thời gian đã thỏa thuận, kiểm chứng hai cơ chế xử lý tranh chỗ cuối trên database hiện tại; so sánh tính đúng khi request đồng thời, chi phí triển khai, mức khóa và cách kiểm thử; ghi kết luận, rủi ro còn lại và quyết định đề xuất.”

Đầu ra có thể gồm **test proof-of-concept, kết quả chạy, ADR ngắn và PBI tiếp theo được làm rõ**.

### 20.2. Spike không phải cách trì hoãn vô hạn

Nếu một spike chỉ ghi “nghiên cứu concurrency” mà không có câu hỏi kết thúc, nhóm khó biết đã học đủ chưa. Nên nêu:

- Điều cần quyết định sau spike.
- Các phương án cần so sánh.
- Bằng chứng cần thu.
- Giới hạn thử và thời điểm xem lại.
- Rủi ro nếu không thể kết luận.

### 20.3. Enabler nên liên hệ với giá trị kế tiếp

Ví dụ enabler **“Tăng độ tin cậy integration tests của đăng ký”** có thể giúp nhóm giao nhiều lát cắt an toàn hơn. Nên mô tả **nó gỡ blocker nào, cách xác nhận pipeline ổn và nhóm nào sẽ hưởng lợi**, không đơn giản đếm số test viết thêm.

### 20.4. Không biến mọi refactor thành user story giả

Một refactor không làm thay đổi hành vi người dùng nhưng giúp giảm phức tạp và tăng testability vẫn có thể cần thiết. Hãy quản lý nó **minh bạch như công việc kỹ thuật có tiêu chí kiểm chứng**, không viết một câu “Là học viên, tôi muốn code sạch hơn” cho có định dạng.

## 21. Walking skeleton: dựng đường đầu cuối mỏng để phát hiện tích hợp sớm

**Walking skeleton** là một đường đi tối thiểu xuyên qua những phần chính của kiến trúc nhằm chứng minh **các thành phần có thể kết nối và vận hành cùng nhau**, trước khi bổ sung toàn bộ quy tắc nghiệp vụ.

Ví dụ đường kỹ thuật:

~~~text
Browser/UI
  -> API gateway / ứng dụng
  -> Service đăng ký
  -> Database thử nghiệm
  -> Response hiển thị ở UI
  -> Test trong CI
~~~

### 21.1. Nó giúp học gì?

- Có thể chạy pipeline build/deploy/test với các thành phần tương ứng?
- Contract UI–API có khớp?
- Quyền truy cập môi trường và dữ liệu thử có sẵn?
- Có quan sát log/trace để chẩn đoán lỗi?
- Các tầng có thể tích hợp trong một thay đổi nhỏ?

### 21.2. Nó chưa chứng minh điều gì?

Một skeleton có thể chỉ lưu một bản ghi đơn giản, chưa bảo đảm:

- Đúng chính sách đăng ký.
- Không vượt sức chứa khi đồng thời.
- Quyền của từng học viên.
- Retry/idempotency.
- Dữ liệu production hoặc tải thực.

Do đó nó là **bằng chứng giảm rủi ro tích hợp/hạ tầng**, chưa phải mặc định một **Increment giá trị người dùng hoàn chỉnh**.

### 21.3. Từ skeleton tới lát cắt có giá trị

Bổ sung một hành vi nghiệp vụ cụ thể cùng điều kiện chất lượng vào đường đã kết nối. Khi có thể xác minh **“một học viên hợp lệ được xác nhận đúng và trạng thái được đọc lại”** trong môi trường phù hợp, nhóm đã tiến gần một lát cắt thực hơn việc xây toàn bộ tầng backend mà không đi qua UI.

## 22. Kiểm thử theo rủi ro trong từng lát cắt

Để một PBI có thể kiểm chứng sớm, kiểm thử không nên chỉ xuất hiện **sau khi tất cả task kỹ thuật báo hoàn tất**.

### 22.1. Các tầng kiểm chứng có vai trò khác nhau

| Tầng hoặc loại kiểm chứng | Câu hỏi | Ví dụ workshop |
| --- | --- | --- |
| **Unit test** | Logic nhỏ có đúng trong các tình huống đại diện? | Hàm xác định đủ điều kiện, tính thời hạn hủy |
| **Integration test** | Thành phần thật tương tác đúng? | Database transaction và truy cập đồng thời |
| **Contract test** | Hai hệ thống thống nhất input/output và ý nghĩa? | API dịch vụ email/đối tác |
| **End-to-end test** | Người dùng hoàn tất hành trình qua các tầng? | Chọn workshop, đăng ký, đọc lại trạng thái |
| **Security/authorization test** | Vai trò và dữ liệu được bảo vệ? | Tài khoản B không đọc đăng ký của A |
| **Performance/operational check** | Hành vi đáng tin dưới tải/môi trường đã định? | Timeout và tranh chấp khi nhiều yêu cầu |
| **User/stakeholder feedback** | Kết quả có dễ hiểu và hữu ích? | Người học hiểu mình đã có chỗ hay chưa |

### 22.2. Không phải mọi lát cắt đều cần cùng số lượng test

Một thay đổi hiển thị nhãn có rủi ro khác với thay đổi giao dịch dữ liệu. Chọn kiểm chứng theo **rủi ro của hành vi và chuẩn chất lượng áp dụng**; không dùng việc “lát cắt nhỏ” làm lý do bỏ test trọng yếu.

### 22.3. Ví dụ test cạnh tranh chỗ cuối ở mức mô tả

~~~text
GIVEN: Workshop còn đúng 1 chỗ; hai học viên hợp lệ khác nhau
WHEN: Hai yêu cầu đăng ký đến gần như đồng thời
THEN: Không có hơn 1 đăng ký được xác nhận
AND: Dữ liệu sức chứa và danh sách đăng ký nhất quán
AND: Học viên không được xác nhận nhận trạng thái phù hợp
AND: Các thao tác retry không tạo xác nhận trùng trái chính sách
~~~

Một test như vậy cần triển khai với **database và cơ chế thực tế**, không chỉ giả lập hàm trừ số chỗ đơn luồng.

## 23. TDD, CI và refactoring giúp lát cắt thật sự Done

Các thực hành kỹ thuật từ XP hỗ trợ **giao những thay đổi nhỏ mà vẫn giữ chất lượng**.

### 23.1. TDD theo một hành vi nhỏ

Vòng **Red → Green → Refactor**:

1. **Red:** Viết một test cho hành vi/rủi ro cụ thể trước khi triển khai.
2. **Green:** Viết lượng code nhỏ đủ làm test đạt.
3. **Refactor:** Cải thiện cấu trúc, giữ test xanh.
4. Lặp với ví dụ tiếp theo.

Ví dụ đầu tiên có thể là “học viên không đủ điều kiện không được đăng ký”, tiếp theo “workshop hết chỗ phải từ chối”. Các rủi ro giao dịch đồng thời cần **integration tests thích hợp**, không thể chỉ dùng unit tests.

### 23.2. CI giảm kích thước lô tích hợp

Khi một PR nhỏ được merge và chạy test tự động, nhóm có thể phát hiện **API contract, migration, lỗi cấu hình hoặc test regression** sớm hơn so với chờ tất cả tầng hoàn tất cuối kỳ.

~~~mermaid
flowchart LR
    A["Ví dụ chấp nhận / rủi ro"] --> B["Code + test lát cắt nhỏ"]
    B --> C["Review và tích hợp"]
    C --> D{"CI/test đạt?"}
    D -->|"Không"| E["Sửa khi thay đổi còn nhỏ"]
    E --> C
    D -->|"Có"| F["Kiểm chứng DoD + demo/feedback"]
    F --> G["Quyết định lát cắt tiếp theo"]
    G --> A
~~~

### 23.3. Refactoring không phải “làm thêm cho đẹp”

Một module đăng ký có code lặp khiến mỗi thay đổi dễ phá phân quyền. Refactor với test phù hợp có thể **giảm chi phí giao những lát cắt tiếp theo**. Khi cần đầu tư đáng kể, nên làm rõ **lợi ích, rủi ro, phạm vi và cách kiểm chứng**, thay vì che dưới một story người dùng không liên quan.

### 23.4. Pair programming để hoàn tất thay vì song song hóa giả

Hai Developers cùng xử lý rủi ro dữ liệu hoặc một reviewer hỗ trợ sớm có thể làm **số task cá nhân ít hơn** nhưng giúp PBI đạt DoD sớm. Đo “ai làm nhiều task” có thể khuyến khích họ tách ra và để hàng đợi tích hợp lớn hơn.

## 24. Feature flag, deploy và release: giúp phản hồi an toàn, không che thiếu sót

Một lát cắt được tích hợp có thể chưa được mở cho toàn bộ người dùng. Có thể dùng **feature flag, pilot nội bộ, rollout theo pha hoặc canary** khi thích hợp để kiểm soát phạm vi tiếp cận.

### 24.1. Ba khái niệm cần tách

- **Deploy:** Đưa mã/cấu hình vào một môi trường.
- **Release:** Cho phép một khả năng được sử dụng theo quyết định sản phẩm/vận hành.
- **Exposure:** Người dùng hoặc nhóm người dùng thật sự gặp khả năng đó.

### 24.2. Lợi ích khi chia lát cắt đúng

Nhóm có thể deploy phần tích hợp có kiểm chứng, giữ cờ tắt cho người dùng bên ngoài, thử với nhóm được ủy quyền và mở rộng sau khi **quality gate và outcome phù hợp**.

### 24.3. Giới hạn quan trọng

Feature flag **không làm biến mất lỗi bảo mật hoặc dữ liệu đã biết**. Một thay đổi ghi sai đăng ký không trở nên an toàn chỉ vì mở cho 1% người dùng. Rollback code có thể không khôi phục giao dịch đã ghi hoặc email đã gửi. Phải bảo vệ người dùng, kiểm soát dữ liệu và có quy trình khôi phục được phê duyệt.

## 25. Xử lý phụ thuộc giữa các tầng và các nhóm

Một lát cắt dọc có thể cần frontend, backend, database, bảo mật và vận hành. Khi các nhóm chuyên môn khác nhau giữ quyền, khó khăn là **cách phối hợp theo dòng giá trị**.

### 25.1. Mô hình phối hợp tránh bàn giao mù

| Bước | Vai trò/cách làm | Kết quả mong muốn |
| --- | --- | --- |
| Làm rõ nhu cầu | Product Owner, Developers, kiểm thử, người hiểu nghiệp vụ | Ví dụ chấp nhận và rủi ro chung |
| Chọn lát cắt | Nhóm phát triển cùng PO | Đầu ra có giá trị và ranh giới Done |
| Thiết kế hợp đồng | Người tạo/tiêu thụ API | Contract và cách kiểm chứng |
| Thực hiện | Developers phối hợp, pairing khi phù hợp | Thay đổi nhỏ xuyên các tầng |
| Kiểm chứng | Tự động + thẩm định rủi ro | Bằng chứng thật, lỗi phát hiện sớm |
| Hoàn tất | Đánh giá DoD và quy tắc phát hành | Increment không chỉ là task merge |
| Nhận phản hồi | PO, người dùng, Support/Operations | Quyết định giữ/sửa/đưa gì vào backlog |

### 25.2. Nếu hai nhóm cần làm một lát cắt thì sao?

Có thể dùng **working agreement, API contract, integration test, trách nhiệm release và kế hoạch phụ thuộc**. Nhưng không nên kết luận “nhóm A Done vì đã chuyển yêu cầu cho nhóm B” nếu hành vi tổng thể chưa thể kiểm chứng.

### 25.3. Cần phân biệt ownership và khả năng phối hợp

Một nhóm có thể sở hữu API và một nhóm khác sở hữu UI, nhưng **cả dòng giao giá trị** vẫn cần người điều phối quyết định và kiểm chứng. Nếu bottleneck ở phê duyệt ngoài nhóm, chuyển sang Scrum hoặc Kanban **không tự làm mất hàng đợi ấy**.

### 25.4. Khi phụ thuộc quá lớn cần thay hệ thống

Nếu mọi lát cắt phải chờ chuyên gia duy nhất hoặc staging chung, vấn đề có thể không giải quyết chỉ bằng chia story nhỏ. Cần xem **kiến trúc, quyền tự phục vụ môi trường, review policy, đào tạo người dự phòng và thứ tự Product Backlog**.

## 26. Scrum: Sprint Goal và Increment quan trọng hơn số task Done

Trong Scrum, Product Owner chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog; Developers lập kế hoạch và tạo Increment đáp ứng DoD; Scrum Master giúp Scrum Team và tổ chức cải thiện hiệu quả áp dụng Scrum.

### 26.1. Sprint Goal nên gắn kết quả

Ví dụ Sprint Goal:

> **“Học viên đủ điều kiện có thể đăng ký một workshop còn chỗ và nhận trạng thái chính xác.”**

Nó khác với:

> **“Hoàn thành 12 task backend và 8 task frontend.”**

Câu thứ hai chỉ mô tả hoạt động, không nói khi nào mục tiêu người dùng đạt.

### 26.2. Sprint Backlog là kế hoạch, không phải hợp đồng đóng băng task

Developers có thể cập nhật kế hoạch trong Sprint khi hiểu thêm về công việc. Phạm vi có thể được làm rõ và thương lượng với Product Owner khi cần, **không làm nguy hại Sprint Goal hoặc giảm chất lượng**.

Nếu phát hiện rủi ro tranh chỗ cuối, việc ưu tiên integration test và điều chỉnh task có thể là **thích ứng đúng**, dù số task “giao diện nâng cao” ít đi.

### 26.3. Sprint Review cần kiểm tra kết quả thật

Nếu chỉ demo API dùng mock rồi nói “80% xong”, stakeholder không biết **người dùng có đăng ký được hay không**. Sprint Review là cơ hội **kiểm tra Increment và tiến độ tới Product Goal**, nhận phản hồi và điều chỉnh Product Backlog.

### 26.4. PBI chưa Done thì không trở thành Increment

Trong Scrum, PBI không đạt Definition of Done **không được xem là phần của Increment Done**; phần chưa hoàn tất cần được xem xét lại trong Product Backlog. Không tự cộng một task đã code xong vào sản lượng Increment hay kéo dài Sprint theo mặc định.

### 26.5. Không biến “mỗi Sprint phải có mười story” thành KPI

Nếu nhóm bị thưởng theo số story Done, họ có thể chia giả một lát cắt thành nhiều thẻ rồi tính nhiều lần. **Sprint Goal, DoD và phản hồi sản phẩm** có ích hơn số lượng story đơn lẻ.

## 27. Kanban: quản lý dòng của lát cắt thay vì các mảnh rời

Kanban giúp hình dung **công việc đang làm**, giới hạn WIP, quản lý luồng và dùng dữ liệu để cải tiến. Nếu board chỉ có các thẻ “Create class”, “Write endpoint”, “Style form” không liên hệ PBI, nhóm có thể thấy mọi người bận nhưng không biết **hành vi người dùng nào đang chờ hoàn tất**.

### 27.1. Hiển thị lớp giá trị và lớp task

Một cách thực hành:

- **Tầng PBI/lát cắt:** Từ Ready → In Progress → Review/Test → Done theo chính sách đã định.
- **Các task thực hiện:** Database, API, UI, test, docs thuộc PBI.
- **Blocker:** Ai/điều kiện nào làm lát cắt chưa đạt DoD?
- **WIP policy:** Hạn chế mở nhiều PBI cùng lúc; ưu tiên đưa PBI cũ tới Done.

Không cần bắt mọi nhóm dùng đúng cấu trúc hai tầng; điều quan trọng là board **không che mất kết quả đầu cuối**.

### 27.2. Bốn flow metrics cơ bản

| Chỉ số | Định nghĩa thực dụng | Cách dùng đúng |
| --- | --- | --- |
| **WIP** | Số work item đã bắt đầu và chưa Done trong luồng đã định | Giảm mở việc khi nhiều lát cắt đang bị chặn |
| **Throughput** | Số item đạt Done theo chính sách trong một khoảng | Dự báo có điều kiện, không chấm cá nhân |
| **Work item age** | Tuổi của item đang làm chưa hoàn tất | Phát hiện PBI mắc kẹt trước khi quá muộn |
| **Cycle time** | Thời gian từ điểm bắt đầu tới kết thúc của item đã Done | Nhìn phân phối và thời gian chờ |

### 27.3. Một board “nhiều Done” vẫn có thể là tín hiệu xấu

Nếu throughput task tăng nhưng cycle time của **lát cắt có giá trị** kéo dài, cần hỏi:

- WIP của PBI có tăng không?
- Review/test có bị dồn về cuối?
- Các task có được đóng trước khi tích hợp không?
- Chính sách Done có đổi?
- Người dùng có nhận một khả năng mới an toàn không?

**Đơn vị đếm phải nhất quán với câu hỏi quản trị**, không phải “thẻ nào đóng được cũng quy thành năng suất”.

## 28. Đo lường: tránh dùng số thẻ nhỏ để chứng minh tiến độ lớn

Khi một nhóm chủ động chia PBI nhỏ hơn, **số item tăng** không tự chứng minh nhóm tạo nhiều giá trị hơn. Số lượng là chỉ báo phụ thuộc vào **cách định nghĩa đơn vị**.

### 28.1. Phân biệt activity, output, flow và outcome

| Nhóm đo | Ví dụ | Câu hỏi hữu ích | Không suy ra được |
| --- | --- | --- | --- |
| **Activity** | Commit, PR, task đóng, giờ họp | Có những hoạt động nào diễn ra? | Người dùng đã nhận giá trị |
| **Output** | PBI đáp ứng DoD, Increment được tạo | Có gì thực sự hoàn tất? | Người dùng chắc chắn đạt mục tiêu |
| **Flow** | WIP, throughput, work item age, cycle time | Giá trị chảy qua hệ thống ra sao? | Một item có giá trị ngang item khác |
| **Quality** | Lỗi nghiêm trọng, dữ liệu đúng, kiểm thử, DoD | Có giữ tính đáng tin? | Sản phẩm đã đúng nhu cầu |
| **Outcome** | Tỷ lệ đăng ký hợp lệ thành công, giảm ticket hỗ trợ | Hành vi và kết quả người dùng thay đổi thế nào? | Mọi thay đổi đều do một thực hành gây ra |
| **Sustainability** | Quá tải, chuyển ngữ cảnh, thời gian chờ người review | Nhóm có duy trì được nhịp? | Hiệu suất từng cá nhân qua một con số |

### 28.2. Ví dụ vì sao số task tăng có thể là dấu hiệu xấu

Nhóm A đóng 45 task kỹ thuật trong một Sprint nhưng **không có PBI đăng ký nào đạt DoD**. Nhóm B đóng 28 task, nhưng hoàn tất **ba lát cắt**: xem workshop đúng dữ liệu, đăng ký hợp lệ và xem lại trạng thái.

Nếu chỉ đếm task, A có vẻ “nhiều output”. Nếu xem **Increment và hành vi người dùng có thể kiểm chứng**, B có bằng chứng mạnh hơn. Tuy vậy không nên xếp hạng hai team chỉ từ ba con số: cần biết **bối cảnh, loại việc, rủi ro và kết quả thật**.

### 28.3. Goodhart và tác dụng phụ của KPI “nhiều story hơn”

Khi thưởng theo số user story Done, nhóm có thể:

- Chia một hành vi thành nhiều story không có giá trị độc lập.
- Đổi cách ước lượng hoặc định nghĩa Done để đóng thẻ nhanh.
- Né hạng mục phức tạp nhưng bắt buộc về dữ liệu/bảo mật.
- Đẩy integration test sang nhóm khác hoặc Sprint sau.
- Chọn demo đẹp thay vì kết quả chính xác.
- Giảm pairing/review vì các hoạt động này không tạo thẻ cá nhân.

**Chỉ số nên giúp phát hiện vấn đề và ra quyết định, không là mục tiêu làm đẹp bằng mọi giá.**

### 28.4. Không đánh giá người theo số thẻ hoàn tất

Một người cùng hỗ trợ sửa lỗi concurrency có thể tạo ít PR hơn người làm nhiều chỉnh sửa UI nhỏ. So năng suất bằng **story points, số commit, số task, dòng code** thiếu ngữ cảnh và có thể làm hợp tác xấu đi.

Trong Agile, nên xem **khả năng hoàn tất giá trị của luồng**, chất lượng, phối hợp và bằng chứng thực tế; phản hồi nghề nghiệp cá nhân cần **ví dụ cụ thể, vai trò và bối cảnh**, không dùng bảng xếp hạng thô.

## 29. Một ví dụ dữ liệu trước/sau khi thay cách chia PBI

**Tình huống giả định:** Trong hai khoảng bốn tuần của cùng một nhóm workshop, nhóm điều chỉnh từ chia theo tầng sang chia theo lát cắt dọc và tích hợp sớm.

| Tín hiệu trong mỗi giai đoạn bốn tuần | Trước cải tiến | Sau cải tiến |
| --- | ---: | ---: |
| Task kỹ thuật được đánh dấu Done | 42 | 31 |
| PBI giá trị đạt DoD | 2 | 5 |
| Cycle time trung vị của PBI đạt DoD | 16 ngày | 9 ngày |
| PBI đang mở cuối kỳ | 12 | 6 |
| Lỗi nghiêm trọng lọt production | 3 | 1 |
| Hành trình đăng ký bắt đầu hợp lệ | 400 | 500 |
| Hành trình đăng ký xác nhận thành công | 200 | 360 |
| Ticket “không biết đã có chỗ chưa” | 30 | 18 |
| Ngày nhóm phải làm thêm giờ kéo dài | 6 | 3 |

Các con số chỉ là **ví dụ học tập**, không phải nghiên cứu hay mức benchmark ngành.

### 29.1. Task giảm có nghĩa năng suất giảm?

Số task Done giảm từ 42 xuống 31:

\[
\frac{31-42}{42}\times100\%\approx-26{,}2\%.
\]

Nếu quản lý chỉ thưởng theo task, nhóm sẽ bị chê dù **PBI đạt DoD tăng từ 2 lên 5** và thời gian hoàn tất trung vị giảm. Điều này minh họa tác hại của việc lấy **đơn vị công việc do chính cách chia quyết định** làm thước đo giá trị.

### 29.2. PBI Done tăng có chắc giá trị tăng 150%?

Số PBI Done tăng:

\[
\frac{5-2}{2}\times100\%=150\%.
\]

**Không được kết luận giá trị hay năng suất tăng 150%**: độ lớn và cách chia PBI thay đổi, mẫu ít, loại công việc có thể khác. Số này chỉ mô tả lượng item theo quy tắc đếm.

### 29.3. Tỷ lệ hoàn tất đăng ký

Trước:

\[
\frac{200}{400}\times100\%=50\%.
\]

Sau:

\[
\frac{360}{500}\times100\%=72\%.
\]

Mức chênh mô tả là **22 điểm phần trăm**. Có thể là tín hiệu tích cực về hành trình, nhưng còn ảnh hưởng bởi **số workshop còn chỗ, kênh người dùng, tính ổn định dịch vụ, cách ghi event và thay đổi khác**. Cần kiểm chứng trước khi gán toàn bộ cho kỹ thuật chia story.

### 29.4. Ticket hỗ trợ cần chuẩn hóa theo sử dụng

Số ticket giảm từ 30 xuống 18. Nếu tính tỷ lệ thô:

\[
\frac{30}{400}\times100=7{,}5\text{ ticket/100 hành trình}
\]

so với:

\[
\frac{18}{500}\times100=3{,}6\text{ ticket/100 hành trình}.
\]

Đây là dấu hiệu cần xem tiếp, không khẳng định nhân quả. Một người dùng có thể gửi nhiều ticket, cách phân loại vấn đề cũng có thể đổi.

### 29.5. Đọc các chỉ số cùng nhau

Nhóm nên hỏi:

1. PBI có cùng ranh giới Done không?
2. Phần tăng output có đến từ chia giả item?
3. Cycle time ngắn hơn do ít hàng đợi hay do bỏ test?
4. Lỗi nghiêm trọng giảm có phải do ít traffic không?
5. Người dùng có hoàn tất hành trình và hiểu trạng thái hơn không?
6. Nhóm có phải làm thêm giờ để đạt kết quả?

**Dữ liệu giúp mở cuộc điều tra, không tự trả lời mọi câu hỏi.**

## 30. Khép kín vòng phản hồi sau từng lát cắt

Một lát cắt nhỏ chỉ thật sự phát huy giá trị Agile khi nó giúp nhóm **học sớm và điều chỉnh**.

### 30.1. Vòng học hỏi hoàn chỉnh

~~~mermaid
flowchart TD
    A["Mục tiêu người dùng / giả thuyết"] --> B["Chọn lát cắt nhỏ + điều kiện chấp nhận"]
    B --> C["Triển khai xuyên các tầng cần thiết"]
    C --> D["Kiểm chứng DoD và rủi ro"]
    D --> E{"Đã đủ điều kiện?"}
    E -->|"Chưa"| F["Sửa lỗi hoặc làm rõ phạm vi"]
    F --> C
    E -->|"Có"| G["Demo/release có kiểm soát và thu phản hồi"]
    G --> H["Outcome, support, vận hành, quan sát"]
    H --> I["Giữ / sửa / hoãn / chọn lát cắt tiếp"]
    I --> A
~~~

### 30.2. Demo không đồng nghĩa nhận phản hồi hữu ích

Một buổi demo màn hình đẹp có thể tạo sự hài lòng nhưng chưa trả lời:

- Người học hiểu trạng thái “đã nhận yêu cầu” và “đã xác nhận” khác nhau thế nào?
- Khi hết chỗ, thông điệp có giúp họ quyết định bước tiếp?
- Khi có timeout, trạng thái cuối cùng có đúng không?
- Người dùng có thể tự xem lại đăng ký để không gọi Support?

Cần đưa **những câu hỏi cụ thể** vào Sprint Review, user testing hoặc quan sát sau release.

### 30.3. Phản hồi định lượng và định tính hỗ trợ nhau

**Định lượng** cho biết có bao nhiêu hành trình thành công, thời gian chờ và số lỗi. **Định tính** giúp hiểu vì sao người dùng bỏ dở, thông điệp khó hiểu hay điều kiện nghiệp vụ không phù hợp. Một lát cắt nhỏ giúp dễ **nối nguyên nhân với thay đổi vừa thực hiện**, dù vẫn phải thận trọng với yếu tố đồng thời.

## 31. Lập kế hoạch dưới deadline: ít khả năng hoàn chỉnh tốt hơn nhiều khả năng dở

Khi ngày mở workshop đã được xác minh là bắt buộc, nhóm dễ muốn chia thành hàng chục task để mọi người đều có việc. Nhưng **mục tiêu là đạt điều kiện mở đăng ký an toàn**, không phải có bảng đầy thẻ Done.

### 31.1. Chọn mức tối thiểu có giá trị

Ví dụ các điều cần xác nhận:

- Workshop hiển thị đúng thông tin và trạng thái còn chỗ.
- Học viên đủ điều kiện đăng ký hợp lệ.
- Không vượt sức chứa, không xác nhận trùng trái chính sách.
- Trạng thái có thể kiểm tra và được bảo vệ quyền truy cập.
- Có khả năng hỗ trợ/khôi phục phù hợp khi lỗi quan trọng.
- Những nghĩa vụ về hủy, thông báo hay báo cáo đã được xác minh.

Những tiện ích như lịch tháng, phân tích nâng cao hoặc cá nhân hóa có thể hoãn **nếu người có thẩm quyền xác nhận không phải điều kiện bắt buộc của mốc**.

### 31.2. Dự báo theo lát cắt Done thay vì task “có thể code”

Nếu lịch sử cho thấy nhóm thường hoàn tất bốn lát cắt tương đối tương đồng mỗi tuần, dữ liệu có thể giúp **thảo luận năng lực**. Nhưng không hứa chắc bốn lát cắt bất kỳ sẽ hoàn tất nếu một phần có rủi ro giao dịch hoặc phụ thuộc mới.

Phải xem **WIP, work item age, thời gian chờ kiểm thử, dữ liệu lịch sử và điều kiện phát hành**. Không biến phép chia throughput thành chỉ tiêu “mỗi người phải đóng bốn thẻ”.

### 31.3. Chọn “hoãn một tính năng” thay vì “hoãn test của tính năng phải có”

Nếu chỉ còn hai ngày và luồng đăng ký chưa qua test đồng thời, không nên giải quyết bằng:

> “Bỏ test transaction, đổi trạng thái PBI thành Done và đưa vào production. Có lỗi thì Sprint sau sửa.”

Các lựa chọn có trách nhiệm hơn:

- Hoãn một tiện ích không bắt buộc để tập trung sửa rủi ro lõi.
- Giới hạn phạm vi release nếu hợp lệ và vẫn bảo đảm an toàn.
- Thương lượng mốc/phạm vi với người có quyền dựa trên bằng chứng.
- Quyết định **no-go** nếu chưa có phương án đáp ứng điều kiện tối thiểu.

**Một deadline không làm chất lượng trở thành phần có thể cắt tùy tiện.**

## 32. Hợp tác trong refinement: để người hiểu giá trị và người biết rủi ro cùng chia

Chia story không chỉ là việc Product Owner “viết lại câu”. Những lát cắt tốt thường xuất hiện khi **người hiểu nghiệp vụ, Developers, người kiểm thử và người có chuyên môn vận hành/bảo mật** cùng xem một hành trình.

### 32.1. Các góc nhìn bổ sung nhau

| Góc nhìn | Câu hỏi cần mang tới |
| --- | --- |
| **Product Owner/nghiệp vụ** | Ai cần gì, vì sao, trường hợp nào phải hỗ trợ trước? |
| **Developers** | Ranh giới kỹ thuật nào làm thay đổi khả thi, phụ thuộc gì? |
| **Kiểm thử** | Ví dụ chấp nhận nào phân biệt đúng/sai, nguy cơ nào cần test? |
| **Bảo mật/dữ liệu** | Quyền, tính nhất quán, dữ liệu cá nhân và điều kiện bắt buộc nào? |
| **Vận hành/Support** | Khi lỗi, ai biết gì và có thể phục hồi/hỗ trợ thế nào? |
| **Người dùng/stakeholder phù hợp** | Hành vi và thông điệp có đúng nhu cầu không? |

### 32.2. Cách trao đổi tránh tranh luận theo tầng

Thay vì:

> “Backend cần xong hết entity trước, frontend tuần sau, QA cuối cùng.”

Nhóm có thể hỏi:

> “Hành trình nhỏ nhất giúp một học viên xác nhận đúng một chỗ là gì? Nó cần những thay đổi database, API, UI và test nào để đạt Done? Chúng ta cần kiểm tra lỗi đồng thời ngay từ lát cắt đầu hay không?”

Vẫn có task chuyên môn, nhưng chúng **phục vụ một mục tiêu tích hợp chung**.

### 32.3. Người vắng mặt cần nhìn thấy ranh giới giá trị

Trong nhóm phân tán, nên ghi lại:

- PBI và mục tiêu.
- Acceptance examples và điều kiện không được bỏ.
- Quyết định phạm vi đã chọn/hoãn, lý do.
- Contract, dependency và trạng thái kiểm chứng.
- Người có quyền làm rõ hoặc quyết release.

Một người mới đọc backlog cần biết **mình đang giúp hành vi nào hoàn tất**, không chỉ nhận task “thêm field vào DTO”.

## 33. Workshop thực hành “story slicing clinic” trong 45–60 phút

Một phiên làm rõ đủ gọn có thể giúp nhóm chuyển từ danh sách đầu việc sang lát cắt giá trị. Khoảng thời lượng chỉ là **gợi ý**, có thể điều chỉnh theo độ phức tạp và mức rủi ro.

| Giai đoạn | Mục tiêu | Câu hỏi hoặc hoạt động |
| --- | --- | --- |
| **0–10 phút: xác định outcome** | Hiểu vấn đề và người hưởng lợi | “Học viên phải làm được gì?” |
| **10–20 phút: vẽ hành trình** | Thấy chuỗi hành vi và ngoại lệ | Xem → chọn → đăng ký → xác nhận → xem lại |
| **20–35 phút: đề xuất lát cắt** | Chia theo hành vi, rủi ro, đối tượng | Chọn luồng tối thiểu, liệt kê phần có thể hoãn |
| **35–45 phút: kiểm chứng** | Gắn acceptance examples và DoD | Người không có quyền? Hết chỗ? Đồng thời? |
| **45–55 phút: ưu tiên** | Chọn lát cắt giảm bất định và có giá trị | Phần nào nên làm đầu tiên và vì sao? |
| **55–60 phút: chốt hành động** | Có PBI đủ rõ và người cần tham gia | Owner quyết định, blocker, thử nghiệm đầu |

### 33.1. Đầu ra mong muốn

Không phải một backlog có thật nhiều thẻ. Đầu ra tốt gồm:

1. **Một mục tiêu có thể diễn giải bằng hành vi người dùng.**
2. Một số lát cắt nhỏ **có lý do ưu tiên**.
3. Acceptance examples cho lát cắt sắp làm.
4. Rủi ro và phụ thuộc cần giải quyết sớm.
5. Quyết định về phần chưa làm, không để thành “ngầm hiểu”.
6. Người sẽ kiểm chứng và nguồn phản hồi phù hợp.

### 33.2. Nếu nhóm chưa thống nhất được?

Có thể cần **spike, prototype, làm rõ chính sách hoặc gặp người có thẩm quyền**. Đừng ép nhóm ước lượng chính xác một vấn đề chưa biết rồi báo là đủ sẵn sàng chỉ vì đã có tên thẻ.

## 34. Sơ đồ lựa chọn: đây là task, lát cắt giá trị hay enabler?

~~~mermaid
flowchart TD
    A["Một hạng mục nhỏ trong backlog"] --> B{"Có đối tượng, hành vi hoặc kết quả cần kiểm chứng?"}
    B -->|"Có"| C{"Có thể kiểm chứng trong phạm vi rõ + chất lượng phù hợp?"}
    C -->|"Có"| D["Ứng viên lát cắt giá trị / PBI"]
    C -->|"Chưa"| E["Làm rõ, giảm phạm vi hoặc xử lý dependency"]
    B -->|"Chưa rõ"| F{"Có câu hỏi kỹ thuật hoặc rủi ro cần giảm?"}
    F -->|"Có"| G["Spike / enabler với đầu ra kiểm chứng"]
    F -->|"Không"| H["Task kỹ thuật hoặc hoạt động cần xem lại lý do"]
    E --> I["Gắn acceptance examples, DoD, guardrail"]
    G --> J["Ghi giới hạn, kết quả học hỏi, quyết định tiếp"]
    H --> K["Liên kết tới PBI/kết quả cấp cao hơn"]
    D --> I
~~~

### 34.1. Dùng sơ đồ như công cụ hỏi, không là máy phân loại tự động

Một hạng mục có thể vừa giảm rủi ro kỹ thuật vừa tạo khả năng người dùng. Người viết backlog cần **phân tích bối cảnh**, không chỉ nhìn vào tên hoặc một từ khóa.

### 34.2. Câu hỏi “độc lập” có giới hạn

Theo kinh nghiệm thiết kế user story, một lát cắt nên **giảm phụ thuộc không cần thiết và có thể ưu tiên/kiểm chứng rõ**. Nhưng không phải lúc nào cũng có thể làm mỗi lát cắt độc lập hoàn toàn về dữ liệu, hợp đồng hoặc thứ tự hành vi.

Điều quan trọng hơn là **phụ thuộc được minh bạch, không che khoảng trống giá trị và không đẩy mọi kiểm chứng sang cuối dự án**.

## 35. Những sai lầm phổ biến và cách sửa

| Sai lầm | Hậu quả có thể xảy ra | Cách sửa |
| --- | --- | --- |
| Chia một story thành DB/API/UI rồi gọi từng phần là giá trị | Tích hợp muộn, demo rời rạc | Task dưới PBI có hành vi end-to-end |
| Đánh dấu Done khi code merge | Người dùng chưa thực hiện được tác vụ | Dùng DoD và acceptance examples |
| Coi frontend dùng mock là tính năng đã giao | Không kiểm chứng backend/dữ liệu | Ghi rõ prototype; tích hợp trước khi gọi Increment |
| Đếm số task như phần trăm giá trị | Báo cáo tiến độ sai | Xem lát cắt đạt DoD và outcome |
| Mỗi story là một commit | Chia theo thao tác lập trình | Chia theo hành vi có thể kiểm tra |
| Chia quá nhỏ đến mức không còn mục đích | Tăng số thẻ và overhead | Gắn mỗi PBI với mục tiêu/rủi ro |
| Chỉ chia happy path và bỏ an toàn | Dữ liệu sai/không đủ quyền | Giữ các điều kiện bắt buộc của lát cắt |
| “Story nhỏ” nghĩa là không cần test | Lỗi lọt, làm lại | Test theo rủi ro trong từng lát cắt |
| Để QA test sau mọi task | Dồn lỗi cuối Sprint | Cùng viết ví dụ chấp nhận, kiểm chứng sớm |
| Không xử lý dependency giữa nhóm | Chờ dù task nội bộ đã Done | Contract, người quyết, lịch tích hợp, swarming |
| Phát hành một phần chưa được phép | Không đáp ứng cam kết hoặc gây hại | Xác minh phạm vi, quyền và quality gate |
| Lát cắt chỉ có hiệu quả trên demo hard-code | Thực tế không dùng được | Phân biệt prototype với Increment |
| Làm mọi CRUD endpoint trước khi thử một hành trình | Xây nhiều mà chưa biết đúng nhu cầu | Bắt đầu một đường đi tối thiểu |
| Chia theo developer thay vì người dùng | Khó cùng chịu trách nhiệm | Cross-functional phối hợp hoàn tất |
| Gọi mọi task kỹ thuật là user story | Backlog mất ngữ nghĩa | Gọi đúng task, enabler, spike hoặc PBI |
| Không timebox spike | Nghiên cứu kéo dài không ra quyết định | Câu hỏi, bằng chứng, hạn, kết quả |
| Bỏ refactor/CI vì không “user-facing” | Không giữ chất lượng khi giao nhỏ | Ưu tiên kỹ thuật theo rủi ro và khả năng giao |
| Mỗi Sprint đổi DoD để tăng velocity | Số liệu không so được, rủi ro tăng | Giữ chuẩn chất lượng có kiểm soát |
| Story points thành KPI cá nhân | Chia giả việc, né việc khó | Dùng để trao đổi ước lượng nếu phù hợp |
| Bảo mọi PBI phải độc lập tuyệt đối | Thực tế không thể đáp ứng, tạo thiết kế kỳ lạ | Giảm dependency và nêu thứ tự minh bạch |
| Lát cắt quá hẹp không có feedback | Học hỏi chậm dù nhiều thẻ | Chọn kết quả có người kiểm chứng |
| Lát cắt quá rộng vì “người dùng cần đủ hết” | Không có Increment sớm | Tách workflow, quy tắc, phân đoạn khi hợp lệ |
| Bỏ ngoại lệ hết chỗ như tiện ích phụ | Xác nhận vượt sức chứa | Phân loại rủi ro bắt buộc của hành vi |
| Đo throughput mọi loại task như nhau | Dự báo méo vì đơn vị khác nhau | Định nghĩa item và loại việc |
| Dùng feature flag để che bug đã biết | Gây hại cho nhóm người dùng thử | Chỉ mở khi đạt điều kiện an toàn |
| Có dashboard nhiều số nhưng không quyết định | Tốn chi phí đo lường | Bắt đầu từ câu hỏi và hành động |
| Review chỉ trình chiếu tiến độ task | Stakeholder không biết sản phẩm đạt gì | Demo Increment và phản hồi thật |
| Coi mọi phản hồi sau release là bằng chứng nhân quả | Quyết định sai | Xem mẫu, confounding và độ tin cậy |
| Cắt phạm vi không ghi điều chưa hỗ trợ | Người dùng hiểu lầm hoặc Support bị động | Ghi giới hạn, thông báo, backlog rõ |
| Tối đa 100% người bận | WIP và chờ tăng | Ưu tiên hoàn tất lát cắt cũ |

## 36. Checklist trước khi đưa một lát cắt vào thực hiện

Checklist này là **công cụ học tập và refinement**, không phải artifact bắt buộc của Scrum/Kanban/XP.

~~~text
GIA TRI
[ ] Co doi tuong huong loi va hanh vi/ket qua ro?
[ ] Hanh vi co lien he Product Goal hoac rui ro can giam?
[ ] Neu lat cat Done, chung minh duoc dieu gi moi?
[ ] Co phan biet value slice voi task ky thuat / spike?

RANH GIOI
[ ] Pham vi du nho de nhan feedback som?
[ ] Co neu kieu nguoi dung, luong hoac quy tac duoc ho tro?
[ ] Phan hoan lai duoc ghi minh bach, khong phai nghia vu bat buoc?
[ ] Dependency voi cac PBI/nhom khac co ro?
[ ] Khong chi tach theo DB/API/UI/QA roi goi la Increment?

KIEM CHUNG
[ ] Acceptance examples co input, hanh dong, ket qua?
[ ] Test nguon su that, phan quyen, dong thoi neu lien quan?
[ ] Co cach chay end-to-end tren moi truong phu hop?
[ ] Co xac minh failure path va trang thai nguoi dung?
[ ] Co nguoi du dieu kien demo/review/phan hoi?

CHAT LUONG VA VAN HANH
[ ] Definition of Done va chinh sach chat luong duoc giu?
[ ] Khong giam test de dat so story Done?
[ ] CI/integration/review can thiet da duoc len ke hoach?
[ ] Khong mo user that khi biet rui ro bao mat/du lieu nghiem trong?
[ ] Co cach theo doi va ho tro loi quan trong?

HOC HOI VA DO LUONG
[ ] Co cau hoi can quyet dinh sau feedback?
[ ] Metric phan biet task activity voi PBI Done va outcome?
[ ] Khong xep hang ca nhan bang story points, task hoac commit?
[ ] Co guardrail ve quality, user impact va nhom?
[ ] Neu gia thuyet sai, co the sua/hoan/bo backlog?
~~~

Không cần đọc 25 ô trong mỗi cuộc họp. Với một PBI nhỏ, nhóm có thể chọn **những câu hỏi quan trọng nhất theo rủi ro**. Điều cốt lõi là có khả năng chứng minh **Done theo hành vi và chất lượng**, thay vì chỉ có nhiều task được gạch bỏ.

## 37. Bài tập 1 — Biến backlog chia theo tầng thành lát cắt dọc

**Bối cảnh:** Product Owner muốn học viên đăng ký workshop. Developers nhận các thẻ:

| Thẻ ban đầu | Ước lượng khối lượng tương đối | Điều được báo là xong |
| --- | --- | --- |
| A. Tạo bảng WorkshopRegistration | Nhỏ | Migration chạy được ở môi trường dev |
| B. Tạo repository và entity | Nhỏ | Unit test repository giả đạt |
| C. Tạo REST API đăng ký | Vừa | Endpoint trả kết quả mẫu |
| D. Tạo form đăng ký | Vừa | UI dùng mock hoạt động |
| E. Thêm email template | Nhỏ | Template render được |
| F. Tạo integration tests | Vừa/khó | Chưa bắt đầu |
| G. Kiểm tra phân quyền và xử lý chỗ cuối | Khó | Chưa bắt đầu |
| H. Nối API thật vào UI | Vừa | Chưa bắt đầu |

### Yêu cầu

1. Phân loại các thẻ ban đầu là **task**, ứng viên **enabler** hay **lát cắt hành vi**.
2. Viết **một câu user story** diễn đạt nhu cầu người học.
3. Chọn **hai hoặc ba lát cắt có ý nghĩa** phù hợp với Product Goal.
4. Với mỗi lát cắt, nêu **ai nhận giá trị, hành vi, acceptance examples và cách kiểm chứng**.
5. Chỉ rõ task A–H được gom/di chuyển dưới PBI nào; task nào nên thực hiện sớm để giảm rủi ro.
6. Khi nào email template là Should và khi nào nó là một phần Must?
7. Vì sao F/G/H không thể bị xem như “việc phụ cuối Sprint” nếu đang kiểm soát tính đúng của đăng ký?
8. Nếu còn ba ngày mà chưa có integration test đồng thời, bạn sẽ quyết định gì?

### Gợi ý hướng giải

**User story:** “Là học viên đủ điều kiện, tôi muốn đăng ký workshop còn chỗ và nhận xác nhận đáng tin, để biết mình có vị trí tham dự.”

Các lát cắt có thể gồm:

| Lát cắt | Kết quả và kiểm chứng | Các task có thể nằm bên trong |
| --- | --- | --- |
| **S1. Xem workshop mở đăng ký** | Người học thấy thông tin và trạng thái đúng từ dữ liệu; test danh sách và điều kiện mở | Phần schema, API danh sách, UI, test |
| **S2. Đăng ký một workshop hợp lệ** | Người học được xác nhận tối đa theo sức chứa; kết quả đúng khi đồng thời, quyền hợp lệ, UI đọc trạng thái thật | A, B, C, D, F, G, H theo phạm vi thực |
| **S3. Xem lại đăng ký của mình** | Học viên đọc trạng thái đã lưu; tài khoản khác không xem được | API/UI/test phân quyền |

**E — email template** có thể là task thuộc PBI thông báo riêng nếu email không bắt buộc cho luồng đầu. Nhưng nếu cam kết/điều kiện chấp nhận yêu cầu email xác nhận ngay, nó thuộc phạm vi cần hoàn tất hoặc cần phương án được chấp thuận. **F/G/H** không thể bỏ chỉ để gọi S2 Done.

**Không cần nhất thiết triển khai S1 riêng trước S2** nếu hành trình đăng ký đã được thiết kế sẵn hoặc điều kiện sản phẩm khác. Quan trọng là chọn **lát cắt có ý nghĩa, phụ thuộc minh bạch, kiểm chứng đủ rủi ro**.

## 38. Bài tập 2 — Acceptance examples và trường hợp không thể hoãn

**Đề bài:** Nhóm muốn tách “Đăng ký workshop” thành:

- Story 1: Học viên bấm nút Đăng ký, UI báo thành công bằng mock.
- Story 2: Backend tạo đăng ký, nhưng chưa kiểm soát tranh chỗ cuối.
- Story 3: Test phân quyền.
- Story 4: Test concurrent, dự kiến Sprint sau.
- Story 5: Email xác nhận.

Product Owner được thông báo “Story 1 và 2 đã Done, có thể demo với người dùng thật”.

### Câu hỏi

1. Story nào hiện chỉ là **prototype hoặc task kỹ thuật**, chưa tạo hành vi đăng ký có thể tin cậy?
2. Nếu còn một chỗ và hai yêu cầu đồng thời, điều kiện dữ liệu tối thiểu phải bảo đảm là gì?
3. Vì sao không nên xem kiểm tra phân quyền là tiện ích trang trí có thể hoãn?
4. Viết **ba acceptance examples**: thành công, hết chỗ và truy cập trái phép.
5. Một test với mock repository chưa chứng minh điều gì về giao dịch database?
6. Trong điều kiện nào email có thể hoãn?
7. Có thể phát hành qua feature flag cho nhóm nhỏ khi biết lỗi dữ liệu nghiêm trọng không? Vì sao?
8. Bạn sẽ viết lại PBI đầu tiên thế nào để **nhỏ hơn nhưng không sai**?

### Gợi ý hướng giải

Story 1 là **prototype UI**, Story 2 là **thành phần backend** nếu chưa đáp ứng các rủi ro bắt buộc. Trước khi mở luồng đăng ký thật, nhóm cần có **hành vi end-to-end đúng, giao dịch không xác nhận vượt sức chứa, phân quyền phù hợp và trạng thái phản ánh nguồn dữ liệu**.

Ba examples có thể theo dạng:

~~~gherkin
Scenario: Còn chỗ và học viên đủ điều kiện
  Given workshop còn một chỗ và học viên A đủ điều kiện
  When A đăng ký
  Then hệ thống tạo một xác nhận hợp lệ cho A
  And trạng thái hiển thị nhất quán với dữ liệu đã lưu

Scenario: Không còn chỗ
  Given workshop đã hết chỗ
  When học viên B yêu cầu đăng ký
  Then hệ thống không tạo xác nhận mới
  And B nhận trạng thái không thành công phù hợp

Scenario: Người khác yêu cầu xem đăng ký
  Given A có đăng ký đã lưu
  When B yêu cầu xem đăng ký của A
  Then hệ thống từ chối theo chính sách phân quyền
  And không tiết lộ thông tin riêng của A
~~~

Đối với tranh chỗ cuối, cần **bài test đồng thời riêng có cơ chế lưu trữ thực**, chứ ba kịch bản tuần tự trên chưa chứng minh được cạnh tranh được xử lý đúng. Email có thể hoãn nếu **không nằm trong nghĩa vụ và trạng thái tối thiểu vẫn được thông báo rõ**.

## 39. Bài tập 3 — Đọc số liệu mà không bị số thẻ Done đánh lừa

**Dữ liệu giả định:** Hai khoảng quan sát bốn tuần:

| Tín hiệu | Trước | Sau |
| --- | ---: | ---: |
| Task kỹ thuật Done | 42 | 31 |
| PBI đạt DoD | 2 | 5 |
| Cycle time trung vị của PBI | 16 ngày | 9 ngày |
| Lượt đăng ký bắt đầu hợp lệ | 400 | 500 |
| Lượt đăng ký xác nhận thành công | 200 | 360 |
| Lỗi nghiêm trọng sau phát hành | 3 | 1 |

### Câu hỏi

1. Tính tỷ lệ phần trăm biến động **task Done**.
2. Tính tỷ lệ phần trăm biến động **PBI đạt DoD**.
3. Tính tỷ lệ hoàn tất đăng ký của mỗi kỳ và chênh lệch **điểm phần trăm**.
4. Có thể nói nhóm “năng suất tăng 150%” vì PBI Done tăng từ 2 lên 5 không?
5. Vì sao giảm cycle time có thể là cải thiện thật hoặc là do **đổi ranh giới đo**?
6. Những guardrail nào cần đọc cùng outcome?
7. Nếu nhóm cố chia thêm 20 PBI từ cùng một hành vi để báo cáo throughput, bạn sẽ phản biện thế nào?
8. Chọn một thử nghiệm cải tiến tiếp theo và nêu bằng chứng muốn thấy.

### Gợi ý đáp án

- Task Done giảm khoảng **26,2%** theo số lượng đơn vị được đếm.
- PBI Done tăng **150%** theo số lượng đơn vị được đếm.
- Tỷ lệ hoàn tất tăng từ **50%** lên **72%**, chênh **22 điểm phần trăm**.
- Không có đủ cơ sở kết luận tăng năng suất hay nhân quả tương ứng vì **kích thước/loại item, cách đếm và điều kiện sử dụng** có thể đổi.
- Nên xem **DoD, lỗi nghiêm trọng, dữ liệu đúng, quá tải, WIP và thời gian chờ** để hiểu cải tiến có bền vững không.

## 40. Bài tập 4 — Tách story dưới deadline mà vẫn giữ chất lượng

**Bối cảnh:** Một công ty đã xác minh ngày mở đăng ký workshop với đối tác. Còn bốn ngày. Luồng xem workshop đã Done. Luồng đăng ký vẫn có lỗi tranh chỗ cuối. Phần email nhắc và bộ lọc nâng cao đã gần hoàn tất. Lãnh đạo đề xuất “đánh dấu đăng ký Done, cho người dùng thử trước, sửa concurrency sau”.

### Nhiệm vụ

1. Viết outcome **bắt buộc phải có ở ngày mở**.
2. Xác định hai hạng mục **có thể cân nhắc hoãn** và điều kiện để hoãn hợp lệ.
3. Rủi ro dữ liệu nào khiến không thể gọi luồng đăng ký Done?
4. Nếu có feature flag, nó giúp điều gì và không giúp điều gì?
5. Những kiểm chứng nào phải có trước quyết định release?
6. Ai cần được tham gia khi phạm vi cam kết phải đổi?
7. Nếu thực sự không kịp làm luồng đăng ký an toàn, có những phương án quản trị nào?
8. Viết thông báo ngắn cho stakeholder nêu **điều đã Done, điều chưa đủ điều kiện, phương án và thời điểm cần quyết định**.

### Gợi ý hướng giải

Giữ **tính đúng của giao dịch, phân quyền, trạng thái xác nhận và hỗ trợ phù hợp**. Bộ lọc nâng cao hoặc email nhắc có thể hoãn **nếu không là nghĩa vụ đã xác minh**. Không mở đăng ký có lỗi tranh chỗ cuối đã biết chỉ vì phạm vi thử nhỏ.

Thông báo mẫu:

> “Luồng xem workshop đã đạt DoD. Luồng đăng ký chưa đạt điều kiện phát hành do integration test đồng thời phát hiện khả năng xác nhận vượt sức chứa. Nhóm đang ưu tiên sửa và kiểm chứng, đề nghị hoãn bộ lọc nâng cao và xác nhận lại nghĩa vụ email. Nếu không có phương án an toàn trước mốc quyết định, cần chủ cam kết và bên vận hành đánh giá điều chỉnh phạm vi/ngày hoặc no-go. Chúng tôi sẽ cập nhật dựa trên kết quả test, không đánh dấu Done trước khi đạt chuẩn.”

## 41. Bài tập 5 — Thử thiết kế một chuỗi Increment có thể phản hồi

**Bài toán:** Product Goal là giảm số học viên phải nhờ nhân viên hỗ trợ đăng ký workshop. Hiện người dùng phải gửi email thủ công để hỏi còn chỗ. Nhóm có Product Backlog với các ý tưởng: danh sách workshop, đăng ký, hủy, thông báo, tìm kiếm nâng cao, báo cáo, đồng bộ lịch và giao diện mobile.

### Yêu cầu

1. Đề xuất một **chuỗi ba đến năm lát cắt** theo thứ tự học hỏi hợp lý.
2. Giải thích vì sao lát cắt đầu tiên có thể tạo bằng chứng về nhu cầu hoặc giảm rủi ro.
3. Với mỗi lát cắt, ghi một **bài test hành vi** và một người sẽ phản hồi.
4. Đánh dấu những yếu tố **bắt buộc trong phạm vi mở thật** và những thứ cần xác minh nghĩa vụ.
5. Chỉ ra **hai task kỹ thuật** thuộc một lát cắt, không phải PBI giá trị độc lập.
6. Thiết kế một spike nếu rủi ro quan trọng chưa đủ thông tin.
7. Nêu một chỉ số flow, một outcome và hai guardrail để quan sát.
8. Khi phản hồi cho thấy người dùng không cần lịch tháng, quyết định Product Backlog có thể thay đổi thế nào?

### Một hướng giải minh họa

| Thứ tự | Lát cắt / hoạt động | Bằng chứng chính |
| --- | --- | --- |
| 1 | **Xem workshop có thông tin và chỗ đáng tin** | Người học tự tìm buổi phù hợp, dữ liệu không sai |
| 2 | **Đăng ký hợp lệ với trạng thái xác nhận đúng** | End-to-end, đồng thời, phân quyền, lỗi và retry theo chính sách |
| 3 | **Xem lại đăng ký và nhận trợ giúp khi trạng thái bất thường** | Người học biết mình có chỗ; Support có nguồn đối soát |
| 4 | **Hủy theo chính sách hợp lệ** | Không sai sức chứa/trạng thái, người học kiểm tra kết quả |
| 5 | **Tìm/lọc nâng cao hoặc thông báo** theo phản hồi/những nghĩa vụ đã xác nhận | Thay đổi được đánh giá bằng nhu cầu và dữ liệu |

Đường đi này chỉ là **một phương án học tập**. Nếu chính sách hủy/email là điều kiện bắt buộc ngay khi mở đăng ký, cần **đưa vào ranh giới Must**; không hoãn máy móc.

Một spike có thể xác minh **cơ chế chống xác nhận vượt sức chứa**. Hai task của lát cắt 2 có thể là **viết migration/ràng buộc và kết nối UI với API**; chỉ hoàn tất chúng chưa chứng minh kết quả người dùng.

## 42. Câu hỏi tự kiểm tra

1. Vì sao một hạng mục kỹ thuật nhỏ không tự động là một lát cắt giá trị?
2. Tách theo database, backend, frontend và QA thường tạo rủi ro tích hợp nào?
3. User story, PBI, task và Increment khác nhau như thế nào?
4. User story có phải một định dạng bắt buộc của Scrum không?
5. Bốn phép thử của lát cắt có thể kiểm chứng gồm những gì?
6. Vì sao 8/10 task Done không tương đương 80% giá trị đã giao?
7. Thế nào là một hành vi có thể demo **trên hệ thống thật hoặc môi trường phù hợp**?
8. Acceptance criteria khác Definition of Done ở điểm nào?
9. Scrum có cho phép gọi PBI chưa đạt DoD là Increment không?
10. Khi nào có thể chia theo kịch bản happy path và hoãn ngoại lệ?
11. Vì sao lỗi vượt sức chứa hoặc lộ dữ liệu thường không được hoãn nếu lát cắt đã mở thật?
12. Chia theo workflow, quy tắc, dữ liệu và nhóm người dùng khác nhau thế nào?
13. Vì sao một prototype với mock có thể hữu ích nhưng chưa chứng minh tích hợp production?
14. Spike nên có câu hỏi, timebox và bằng chứng gì?
15. Walking skeleton giúp giảm rủi ro nào? Chưa chứng minh điều gì?
16. Unit test, integration test và end-to-end test có vai trò khác nhau ra sao?
17. TDD và CI giúp chia nhỏ thay đổi nhưng vẫn giữ chất lượng như thế nào?
18. Có thể sử dụng feature flag để chấp nhận lỗi dữ liệu đã biết không?
19. Vì sao Scrum Sprint Goal nên nêu outcome thay vì số task phải đóng?
20. Có thể thay đổi phạm vi Sprint khi học thêm những gì? Giới hạn nào phải giữ?
21. Khi nào task kỹ thuật nên nằm dưới một PBI, khi nào enabler cần được theo dõi riêng?
22. Kanban flow metrics giúp thấy các lát cắt bị chặn thế nào?
23. Vì sao không nên đếm số task như throughput giá trị người dùng?
24. Story points và số PR có phù hợp để xếp hạng đóng góp cá nhân không?
25. Khi cycle time giảm, cần xem điều gì để biết không phải do đổi cách đo hoặc hạ DoD?
26. Vì sao outcome có thể tăng cùng thời điểm nhưng chưa chứng minh kỹ thuật chia PBI là nguyên nhân?
27. Nếu hai nhóm cùng tham gia một lát cắt, cần kiểm soát phụ thuộc thế nào?
28. Một phiên story slicing clinic nên tạo những đầu ra nào ngoài danh sách thẻ?
29. Khi deadline không còn đủ cho tất cả tính năng, phần nào nên cân nhắc giảm trước?
30. Câu hỏi gì giúp bạn quyết định PBI nào nên làm tiếp theo sau khi có feedback từ người dùng?

## 43. Ghi nhớ: chia nhỏ để giao và học, không chia nhỏ để đóng thêm thẻ

**Chia nhỏ đầu việc nhưng không tạo phần giá trị có thể kiểm chứng** là sai lầm khi nhóm lấy **đơn vị tổ chức công việc** làm **đơn vị chứng minh tiến độ sản phẩm**. Những task như tạo database, viết API, dựng giao diện hay viết test vẫn cần thiết, nhưng **nhiều task Done không thay thế một hành vi người dùng được tích hợp và kiểm chứng đúng**.

Khi chia một yêu cầu lớn, hãy giữ mười nguyên tắc:

1. **Bắt đầu từ người hưởng lợi và hành vi cần thay đổi**, không bắt đầu từ danh sách file phải sửa.
2. **Chia theo chiều dọc khi phù hợp:** Mỗi lát cắt nên bổ sung khả năng hoặc bằng chứng có ý nghĩa qua các tầng cần thiết.
3. **Nhỏ về phạm vi, không nhỏ về chất lượng:** Giữ rủi ro dữ liệu, phân quyền, giao dịch và DoD trong phần đang làm thật.
4. **Phân biệt PBI với task:** Dùng task cho thực hiện, dùng PBI/lát cắt để theo dõi giá trị và Increment.
5. **Gọi đúng spike/enabler:** Học hỏi hoặc giảm rủi ro kỹ thuật là kết quả cần thiết, nhưng không giả gọi chức năng người dùng đã giao.
6. **Viết acceptance examples rõ:** Có người dùng, điều kiện, hành động, kết quả và tình huống lỗi quan trọng.
7. **Tích hợp và kiểm thử sớm:** CI, TDD, review, pairing và test theo rủi ro giúp phát hiện sai giả định khi thay đổi còn nhỏ.
8. **Giảm WIP để ưu tiên hoàn tất:** Tránh mở thêm nhiều task khi lát cắt cũ vẫn chờ review/test.
9. **Đo bằng chứng cân bằng:** Increment Done, flow, outcome, chất lượng và nhịp làm việc bền vững; không dùng số thẻ/commit làm bảng xếp hạng.
10. **Nhận phản hồi rồi thay quyết định:** Sự khác biệt của Agile nằm ở khả năng học sớm và thích ứng, không chỉ ở kích thước backlog.

Trước khi nói một story đã được chia đủ nhỏ, hãy tự hỏi: **“Nếu chỉ phần này được làm xong đúng Definition of Done, người dùng hoặc người ra quyết định có thể kiểm chứng được kết quả mới nào, bằng bằng chứng gì, và những rủi ro nào vẫn không được phép để sang phần sau?”**

Trả lời được câu hỏi đó giúp nhóm **giao Increment có giá trị, phản hồi sớm, giảm lãng phí và cải tiến liên tục**, thay vì chỉ làm đầy dashboard bằng những đầu việc nhỏ nhưng chưa tạo được hành vi có thể tin cậy.
