# Scrumban và sự kết hợp thực hành theo nhu cầu dòng công việc

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **Scrumban** là gì, vì sao không có một bộ quy tắc Scrumban duy nhất và cách phân biệt nó với **Scrum**, **Kanban** hoặc **Scrum sử dụng thực hành Kanban**.
2. Nhận diện loại công việc, mức biến động nhu cầu, phụ thuộc, khả năng giao giá trị và rủi ro để quyết định nên giữ **nhịp Sprint**, quản lý **dòng việc liên tục** hay kết hợp hai cách tiếp cận.
3. Thiết kế một workflow minh bạch với **điểm bắt đầu/kết thúc, chính sách kéo việc, giới hạn Work in Progress (WIP), chính sách ưu tiên và cơ chế xử lý việc khẩn**.
4. Kết hợp nhịp lập kế hoạch, refinement, review và cải tiến với các dữ liệu **throughput, cycle time, work item age, WIP** và các mục tiêu sản phẩm.
5. Vận dụng thực hành kỹ thuật của **Extreme Programming (XP)** để tăng khả năng tích hợp, kiểm thử và phát hành an toàn trong môi trường có thay đổi thường xuyên.
6. Xây dựng, kiểm chứng và điều chỉnh một mô hình làm việc kết hợp qua **thử nghiệm có thời hạn và tiêu chí đánh giá rõ**, không biến việc pha trộn phương pháp thành các nghi thức rời rạc.

## 1. Vì sao cần kết hợp thực hành?

Nhóm phát triển phần mềm hiếm khi chỉ có một loại công việc. Cùng một đội có thể phải phát triển tính năng mới, sửa lỗi production, trả lời yêu cầu từ đối tác, xử lý phụ thuộc API và bảo trì nền tảng. Những việc này **không có cùng độ khẩn, khả năng dự báo hoặc nhịp xuất hiện**.

Ví dụ một đội phát triển nền tảng học trực tuyến đang theo đuổi mục tiêu “Giúp học viên tiếp tục học trên các thiết bị mà không mất tiến độ”. Trong hai tuần, họ vừa cần triển khai lát cắt **“Tiếp tục học”**, vừa nhận lỗi mất tiến độ, yêu cầu báo cáo học viên và một thông báo thay đổi hợp đồng API từ đối tác.

Nếu chỉ lập một danh sách việc bất biến từ đầu kỳ, đội khó phản ứng với lỗi nghiêm trọng. Nếu cứ thay thứ tự việc mỗi giờ, đội lại không đủ tập trung để hoàn thành khả năng sản phẩm có giá trị. Vấn đề không phải **Scrum hay Kanban tốt hơn về bản chất**, mà là:

> **Nhóm cần những cơ chế gì để vừa giữ định hướng giá trị, vừa nhìn rõ công việc đang chảy, xử lý bất định và giao phần mềm đạt chất lượng?**

**Scrumban** là một tên gọi phổ biến cho cách làm kết hợp tư duy và một số thực hành của **Scrum** và **Kanban**. Các đội có thể khác nhau về mức độ sử dụng Sprint, backlog, sự kiện kiểm tra, chính sách kéo việc và đo lường dòng việc.

**Điểm cần thận trọng:** Scrumban **không phải một khuôn khổ chuẩn hóa duy nhất** có bộ vai trò/sự kiện/tạo tác bắt buộc như Scrum. Vì thế, khi một đội nói “chúng tôi làm Scrumban”, cần hỏi **thực tế đội làm gì, giữ cam kết nào và cải tiến dòng công việc ra sao**.

## 2. Scrum, Kanban và Scrumban: phần nào giống và khác?

| Tiêu chí | Scrum | Kanban áp dụng cho công việc tri thức | Scrumban theo nghĩa thực hành |
| --- | --- | --- | --- |
| **Trọng tâm** | Tạo giá trị qua Sprint, Scrum Team tự quản và cơ chế thực nghiệm | Quản lý và cải tiến **dòng giá trị** bằng quan sát, chính sách và điều tiết WIP | Kết hợp tập trung vào mục tiêu và các cơ chế quản lý flow cho bối cảnh của đội |
| **Đơn vị tổ chức** | Sprint có độ dài cố định, tối đa một tháng | Luồng công việc; không bắt buộc chia Sprint | Có thể giữ Sprint hoặc dùng nhịp bổ sung việc và review độc lập |
| **Trách nhiệm** | Product Owner, Scrum Master và Developers theo Scrum Guide | Bắt đầu từ cấu trúc hiện tại; cần trách nhiệm và quyền quyết định minh bạch | Tùy lựa chọn; nếu tuyên bố dùng Scrum thì phải giữ đúng các trách nhiệm Scrum |
| **Lập kế hoạch** | Sprint Planning, Product Backlog, Sprint Goal, Sprint Backlog | Replenishment/pull theo năng lực và chính sách, dự báo bằng dữ liệu flow | Có thể duy trì Sprint Planning, bổ sung việc theo nhu cầu hoặc kết hợp ở các chân trời khác nhau |
| **Kiểm tra và cải tiến** | Daily Scrum, Sprint Review, Sprint Retrospective | Những vòng phản hồi phù hợp để xem workflow, chất lượng dịch vụ và cải tiến | Chọn nhịp có ích, tránh họp trùng mà không ra quyết định |
| **Giới hạn WIP** | Không quy định một con số WIP chuẩn | Một cơ chế quan trọng để kiểm soát công việc đã bắt đầu | Thường dùng giới hạn WIP với bảng công việc đang thực hiện |
| **Chỉ số** | Có thể dùng các chỉ số hỗ trợ mục tiêu và dự báo | WIP, throughput, cycle time, work item age, SLE và các tín hiệu liên quan | Chọn dữ liệu dòng việc để hỗ trợ quyết định và dự báo, không dùng số liệu để xếp hạng cá nhân |
| **Chất lượng** | Increment phải đáp ứng Definition of Done | Cần chính sách hoàn tất và chất lượng minh bạch phù hợp sản phẩm | Bảo vệ DoD nếu dùng Scrum; dù dùng mô hình nào cũng không hạ yêu cầu an toàn |

### Hai cách nói không đồng nhất

**“Scrum với Kanban”** thường có nghĩa một Scrum Team **giữ nguyên khung Scrum** rồi sử dụng quan sát flow, chính sách WIP và các thực hành Kanban để cải thiện khả năng giao giá trị trong Sprint.

**“Scrumban”** có thể được một đội dùng để mô tả cách làm rộng hơn: vẫn có mục tiêu và những cuộc review định kỳ, nhưng việc chọn và kéo vào hệ thống diễn ra liên tục, không nhất thiết có đầy đủ sự kiện hoặc các trách nhiệm giải trình của Scrum.

**Không nên nói một đội đang thực hiện Scrum đầy đủ nếu đội chủ động bỏ Sprint Goal, Product Owner hoặc các sự kiện bắt buộc của Scrum.** Đội có quyền chọn phương pháp khác phù hợp hơn; điều quan trọng là gọi đúng cách làm và hiểu các đánh đổi.

## 3. Bắt đầu từ nhu cầu dòng công việc, không từ tên phương pháp

Trước khi chọn mô hình, hãy tìm hiểu **nhu cầu thật**:

- Công việc đến **theo đợt có thể chuẩn bị** hay **liên tục, khó dự đoán**?
- Đội đang cần **mục tiêu sản phẩm chung theo giai đoạn** hay chủ yếu phục vụ **dòng yêu cầu độc lập**?
- Những hạng mục có thể được chia thành **lát cắt nhỏ, tích hợp và kiểm chứng** không?
- Có bao nhiêu việc phải **phản ứng ngay** vì lỗi production, an toàn dữ liệu hoặc nghĩa vụ bên ngoài?
- Thời gian chờ nằm ở **review, test, đối tác, phê duyệt, thiết kế** hay bước khác?
- Ai có quyền quyết định **giá trị, mức ưu tiên và rủi ro**?
- Đội có dữ liệu đủ nhất quán để đưa ra **dự báo có điều kiện** không?

### Một ma trận lựa chọn sơ bộ

| Bối cảnh | Hướng cân nhắc | Điểm phải làm rõ |
| --- | --- | --- |
| Đội phát triển khả năng sản phẩm theo mục tiêu ngắn hạn, có thể tạo Increment thường xuyên | **Scrum**, có thể bổ sung giới hạn WIP, quan sát work item age và throughput | Giữ Sprint Goal, DoD và các trách nhiệm/sự kiện Scrum |
| Đội vận hành nhận lỗi và yêu cầu hỗ trợ liên tục, ưu tiên biến động mạnh | **Kanban theo luồng liên tục**, với chính sách kéo việc và xử lý khẩn | Mốc start/finish, trách nhiệm ưu tiên, cách quản lý việc quá tuổi/SLE |
| Một đội vừa phát triển theo mục tiêu, vừa xử lý việc vận hành có rủi ro | Kết hợp có chủ đích: **giữ mục tiêu/nhịp review**, đồng thời có chính sách flow cho việc phát sinh | Năng lực dành cho việc khẩn, quyền đổi ưu tiên, bảo vệ chất lượng |
| Nhiều phụ thuộc bên ngoài gây chờ hơn là thiếu lập trình viên | Tập trung **Kanban metrics, quản lý blocked và hợp đồng tích hợp**, bất kể khung tổ chức | Không chỉ thêm họp hoặc thay tên cột |
| Đội đang thiếu kiểm thử tích hợp và thường giao code lỗi | Bổ sung **XP: CI, TDD, refactoring, pairing và kiểm thử** | Thay đổi kỹ thuật cần đo tác dụng và đáp ứng tiêu chuẩn sản phẩm |

Không có **ngưỡng số người, tỷ lệ bug hay WIP** phổ quát quyết định phương pháp. Những tỷ lệ có thể được dùng để đặt giả thuyết và thử nghiệm, không nên biến thành luật cho mọi đội.

## 4. Hai mô hình kết hợp điển hình

### 4.1. Mô hình A — Scrum giữ nguyên, thêm Kanban để cải tiến flow

Đội giữ:

1. **Product Owner, Scrum Master và Developers** theo trách nhiệm của Scrum.
2. **Product Goal, Sprint Goal và Definition of Done** gắn với ba tạo tác Scrum.
3. Các sự kiện **Sprint Planning, Daily Scrum, Sprint Review, Sprint Retrospective** trong Sprint.
4. Một Sprint có thể tạo **nhiều Increment**, mỗi Increment dùng được và đạt DoD.

Đội bổ sung:

- Bảng thể hiện các bước thật của luồng công việc, bao gồm review/test/blocked.
- **Giới hạn WIP** thích hợp ở các trạng thái có nguy cơ nghẽn.
- Chính sách “**ưu tiên hoàn tất trước khi bắt đầu thêm**”.
- Quan sát **work item age, cycle time, throughput** cùng Sprint Goal.
- Chính sách phản ứng với việc khẩn và phụ thuộc mà không che tác động lên Sprint.

**Ví dụ:** Trong Daily Scrum, Developers thấy ba story đang chờ review và hai story gần chạm SLE nội bộ. Thay vì kéo thêm backlog, họ điều chỉnh Sprint Backlog để hỗ trợ hoàn tất các lát cắt đang hướng Sprint Goal.

Ở mô hình này, **việc áp dụng Kanban không thay thế Sprint Goal** hoặc biến Daily Scrum thành buổi chỉ đọc số WIP. Dữ liệu flow là thông tin hỗ trợ kiểm tra và thích nghi của Scrum.

### 4.2. Mô hình B — Luồng liên tục là chính, thêm nhịp mục tiêu và phản hồi

Đội quyết định **không tổ chức Sprint như Scrum** vì công việc hỗ trợ và cải tiến nhỏ đến liên tục. Họ có thể:

- Duy trì một **mục tiêu dịch vụ/sản phẩm rõ ràng** theo một khoảng thời gian.
- Có buổi **replenishment** để đưa việc đủ rõ vào hàng đợi Sẵn sàng theo năng lực.
- Kéo việc theo chính sách và WIP; ưu tiên khắc phục item già, blocked.
- Xem kết quả với người dùng và các bên liên quan theo nhịp phù hợp.
- Có hoạt động cải tiến định kỳ, gần với tinh thần retrospective.

Đội có thể gọi cách làm này là **Scrumban** hoặc **Kanban kết hợp các thực hành Scrum**, nhưng cần minh bạch rằng đó **không nhất thiết là Scrum theo Scrum Guide**.

**Ví dụ:** Đội hỗ trợ nền tảng học nhận yêu cầu mỗi ngày. Mỗi tuần họ kiểm tra mục tiêu giảm lỗi lưu tiến độ, bổ sung việc theo năng lực đang rảnh và xử lý lỗi khẩn theo chính sách công khai. Họ không buộc mọi yêu cầu phải chờ Sprint mới để bắt đầu.

### 4.3. Mô hình kết hợp không phải lựa chọn “mỗi thứ lấy một ít”

Khi thiết kế hệ thống làm việc, hãy xác định:

> **Giữ cơ chế nào? Vì nhu cầu gì? Bỏ cơ chế nào? Rủi ro khi bỏ là gì? Dữ liệu nào giúp biết lựa chọn đang có tác dụng?**

Lấy tên Scrum cho kế hoạch hai tuần, tên Kanban cho bảng kéo thả nhưng không có mục tiêu, chính sách WIP hoặc cải tiến dựa trên bằng chứng chỉ là **đổi từ vựng**, chưa tạo khả năng thích ứng.

## 5. Thiết kế workflow thể hiện công việc thật

Một workflow hữu ích cần cho đội thấy **hạng mục ở đâu, bị chờ vì sao, ai có thể giúp và khi nào việc thật sự hoàn thành**.

Ví dụ cho một đội nền tảng học trực tuyến:

~~~text
Ý tưởng/Backlog  ->  Sẵn sàng  ->  Phát triển  ->  Review  ->  Kiểm thử/tích hợp  ->  Done
                         |           |             |               |
                     Hàng chờ       WIP 3         WIP 2           WIP 2

                    [Blocked được đánh dấu trên hạng mục đang bị chặn]
~~~

Các cột và giới hạn WIP chỉ là **minh họa**, không phải quy tắc bắt buộc. Một hệ thống có thể thêm “Chờ đối tác”, “Triển khai” hoặc “Xác nhận”; hệ thống khác có thể đơn giản hơn. Nếu có quá nhiều cột mà không ai sử dụng để ra quyết định, bảng trở thành gánh nặng.

### Quy ước đo lường cần có

| Nội dung | Quy ước ví dụ | Điều cần tránh |
| --- | --- | --- |
| **Work item** | Một story/bug có tiêu chí Done rõ, không đếm từng subtask như hạng mục giao hàng | Chia ticket hình thức để làm đẹp throughput |
| **Start point** | Thời điểm việc được kéo vào “Phát triển” | Gọi ngày tạo ticket là ngày bắt đầu mà không nhất quán |
| **Finish point** | Khi đáp ứng DoD/chính sách Done, đã tích hợp và được xác minh | Đóng khi code vừa merge dù chưa test |
| **Blocked** | Không thể tiến vì phụ thuộc, quyết định, môi trường hoặc rủi ro | Che tình trạng chờ bằng trạng thái “Đang làm” chung chung |
| **Reopened** | Việc bị trả lại do chưa đáp ứng điều kiện Done; ghi theo chính sách nhất quán | Xóa lịch sử lỗi/làm lại cho dashboard đẹp |
| **Expedite** | Việc thực sự khẩn, có điều kiện và người có quyền xác nhận | Mọi yêu cầu từ người có chức danh cao đều thành khẩn |

### Nhìn thấy luồng, không chỉ nhìn thấy người

Trên bảng nên ưu tiên các câu hỏi:

- Hạng mục nào đang chờ nhiều nhất?
- Có cột nào đã đầy đến mức cần **swarm/pair** giúp nhau hoàn tất?
- Có item nào già hơn mức thông thường?
- Những hạng mục nào liên quan trực tiếp mục tiêu sản phẩm/Sprint Goal?
- Việc khẩn nào đang làm thay đổi khả năng giao các việc khác?

Đừng dùng bảng như một công cụ chấm điểm “ai bận hơn”. **Bận rộn cục bộ không đồng nghĩa có luồng giao giá trị tốt**.

## 6. Giới hạn WIP và nguyên tắc kéo việc

**Work in Progress (WIP)** là lượng công việc đã bắt đầu nhưng chưa hoàn thành theo ranh giới workflow. Giới hạn WIP giúp tạo tín hiệu để đội **ngừng bắt đầu thêm khi chưa đủ khả năng hoàn tất công việc đang mở**.

### Vì sao không nên để mọi người mở nhiều ticket?

Giả sử có bốn người phát triển nhưng cùng lúc mở mười hai story:

- Ba story chờ môi trường tích hợp.
- Bốn story chờ review.
- Hai story chưa có tiêu chí chấp nhận đủ rõ.
- Ba story đang được code song song.

Nếu tiếp tục bắt đầu thêm, đội có thể tăng **chuyển ngữ cảnh và thời gian chờ**, khiến người dùng nhận phản hồi chậm. Giới hạn WIP không đảm bảo throughput tự động tăng, nhưng tạo điều kiện để đội nhìn thấy điểm nghẽn và phối hợp.

### Thiết lập một giới hạn có chủ đích

1. Quan sát WIP hiện tại và **khả năng xử lý ở mỗi trạng thái**.
2. Chọn mức giới hạn **mang tính thử nghiệm**, không lấy số của đội khác làm chuẩn.
3. Định nghĩa rõ khi cột đầy thì **không kéo thêm** hay xử lý ngoại lệ ra sao.
4. Khi bị đầy, giúp review, test, làm rõ phụ thuộc hoặc chia nhỏ việc đang làm.
5. Quan sát cycle time, throughput, tuổi item và chất lượng trong một khoảng đủ có dữ liệu.
6. Điều chỉnh giới hạn dựa trên kết quả và khả năng phục vụ công việc khẩn.

**Ví dụ:** Khi cột Review đang có hai item (WIP limit = 2), developer vừa xong code không nên đổi tên item thành “Sẵn sàng chuyển review” để che rằng công việc vẫn chưa được giải quyết. Đội cần quyết định phối hợp review, giữ item trong hệ thống có thể nhìn thấy và xử lý chính sách pull cho nhất quán.

### Pull không có nghĩa “không ai được yêu cầu việc”

Product Owner hoặc người chịu trách nhiệm ưu tiên vẫn có thể giải thích giá trị và thứ tự; người thực hiện kéo việc khi có **năng lực và điều kiện sẵn sàng**. Với Scrum, Developers chịu trách nhiệm lập và điều chỉnh Sprint Backlog để hướng tới Sprint Goal. Không nên dùng từ “pull” như lý do để che sự thiếu trách nhiệm trong quyết định ưu tiên.

## 7. Xử lý công việc khẩn mà không phá dòng thường xuyên

Điều khó nhất của đội kết hợp thường là giữ công việc phát triển tiến triển trong khi vẫn có thể xử lý **sự cố thực sự**.

### Phân loại công việc minh họa

| Loại | Ví dụ | Chính sách có thể thử |
| --- | --- | --- |
| **Tiêu chuẩn** | User story cải thiện nút “Tiếp tục học” | Kéo theo thứ tự ưu tiên, năng lực và WIP |
| **Khẩn / expedite** | Lỗi lộ dữ liệu tiến độ hoặc mất bài nộp | Xử lý ngay theo mức nghiêm trọng; có người xác nhận; làm rõ việc bị gián đoạn |
| **Ngày cố định** | Mốc chứng nhận bảo mật, lịch sự kiện hoặc yêu cầu hợp đồng | Chuẩn bị phụ thuộc và kiểm định từ sớm; không đợi đến sát mốc |
| **Khám phá rủi ro** | Spike xác minh API đồng bộ | Giới hạn thời gian; đầu ra là bằng chứng và quyết định, không tự gọi là Increment |

Các lớp dịch vụ (*classes of service*) là lựa chọn chính sách, **không phải danh mục Scrumban bắt buộc**.

### Chính sách expedite cần rõ điều kiện

Ví dụ đội thống nhất:

1. Chỉ những sự cố đạt mức ảnh hưởng nghiêm trọng đã định nghĩa mới được đánh dấu expedite.
2. Người có quyền quyết định mức độ khẩn được nêu rõ (ví dụ trực sự cố và đầu mối sản phẩm).
3. Khi expedite được kích hoạt, đội minh bạch **item nào tạm dừng** và tác động dự báo.
4. Dành khả năng xử lý sự cố, kiểm thử và khôi phục; không bỏ qua an toàn vì “gấp”.
5. Sau sự cố, xem lại nguyên nhân, chất lượng và điều chỉnh chính sách ưu tiên nếu lặp lại.

**Không có quy tắc phổ quát “luôn chỉ một expedite”**; giới hạn cần tùy bối cảnh và mức rủi ro. Tuy nhiên, nếu hầu hết item đều được gắn “khẩn”, ưu tiên không còn có ý nghĩa và dự báo thường sẽ kém tin cậy.

### Khi dùng Scrum và có expedite giữa Sprint

Trong Scrum, **không thực hiện thay đổi làm nguy hiểm Sprint Goal** và **không giảm chất lượng**. Developers có thể làm rõ/thương lượng phạm vi với Product Owner khi biết điều mới. Sự cố nghiêm trọng có thể buộc đội điều chỉnh dự báo và công việc; đội cần minh bạch tác động thay vì giả vờ Sprint Backlog không đổi.

Nếu Sprint Goal **thực sự lỗi thời**, **chỉ Product Owner có quyền hủy Sprint**. Việc một story khó hơn ước lượng hoặc có một yêu cầu mới không tự nó là lý do hủy Sprint.

## 8. Lập kế hoạch theo các chân trời khác nhau

Scrumban thường hữu ích khi đội tách **định hướng xa** khỏi **lựa chọn việc gần** và **điều chỉnh hằng ngày**.

| Chân trời | Quyết định | Công cụ/thực hành có thể dùng |
| --- | --- | --- |
| **Dài hạn** | Product Goal, kết quả người dùng, ranh giới ngân sách và chất lượng | Roadmap theo outcome, Product Backlog, nghiên cứu người dùng |
| **Trung hạn** | Nhóm hạng mục ưu tiên, phụ thuộc, rủi ro, dự báo có điều kiện | Refinement, thử nghiệm, phân tích throughput/cycle time |
| **Gần hạn theo Sprint** | Sprint Goal, các item được chọn và kế hoạch thực hiện | Sprint Planning và Sprint Backlog nếu đội dùng Scrum |
| **Gần hạn theo luồng liên tục** | Việc nào được replenishment và kéo tiếp theo | Chính sách sẵn sàng, pull, WIP limit và nguồn năng lực |
| **Hằng ngày** | Item nào cần hỗ trợ gỡ chặn, kiểm tra, review hoặc hoàn tất trước | Bảng flow, work item age, Daily Scrum hoặc flow meeting phù hợp |
| **Sau khi giao** | Giá trị đạt chưa, chất lượng có ổn không, đổi hướng nào | Review với bên liên quan, dữ liệu người dùng, Retrospective/cải tiến |

### Phân biệt cadence với batch

**Có một nhịp họp hai tuần** không có nghĩa công việc phải chờ hai tuần mới được tích hợp, kiểm thử hoặc phát hành. Đội có thể:

- Giữ Sprint hai tuần nhưng tạo nhiều Increment đạt DoD trong Sprint.
- Nhận phản hồi sản phẩm sớm khi một Increment đã sẵn sàng.
- Replenish dòng việc liên tục nếu mô hình vận hành cho phép.
- Review chất lượng, SLE và rủi ro vào thời điểm phù hợp.

Nhịp kiểm tra giúp mọi người phối hợp; **không nên biến nó thành lý do dồn giao hàng thành lô lớn**.

## 9. Dùng dữ liệu dòng công việc để ra quyết định

Để cải tiến, đội cần dữ liệu **đủ tin cậy và được hiểu đúng**, không chỉ một dashboard nhiều màu.

### Bốn flow metrics cốt lõi

| Chỉ số | Định nghĩa theo workflow | Quyết định hỗ trợ |
| --- | --- | --- |
| **WIP** | Số item đã bắt đầu, chưa hoàn tất tại thời điểm đo | Có đang bắt đầu quá nhiều? Cột nào cần hỗ trợ? |
| **Throughput** | Số item đi qua điểm Done trong một khoảng thời gian | Nhịp giao thực tế là bao nhiêu? |
| **Cycle time** | Thời gian từ start point đến finish point của **item đã hoàn thành** | Công việc thường mất bao lâu, đuôi dài ở đâu? |
| **Work item age** | Thời gian từ start point đến hiện tại của **item đang mở** | Item nào có nguy cơ kéo dài cần hỗ trợ ngay? |

**Lead time** có thể dùng khi cần đo từ lúc yêu cầu được ghi nhận đến lúc giao xong. Phải nêu rõ điểm bắt đầu và điểm kết thúc vì nhiều đội dùng các mốc khác nhau.

### Ví dụ tính throughput

Một đội có throughput trong sáu tuần:

| Tuần | Item hoàn tất |
| --- | ---: |
| 1 | 4 |
| 2 | 5 |
| 3 | 3 |
| 4 | 4 |
| 5 | 4 |
| 6 | 4 |
| **Tổng** | **24** |

Throughput trung bình là **24 / 6 = 4 item/tuần**. Nếu còn 12 item có kích thước và loại tương tự, một **kịch bản số học thô** theo nhịp trung bình là **3 tuần**; với nhịp 3 item/tuần là **4 tuần**, còn nhịp 5 item/tuần là **2,4 tuần**.

Đây **không phải khoảng tin cậy thống kê**, cũng không phải lời hứa giao đủ 12 item sau ba tuần. Thay đổi phạm vi, nhân sự, phụ thuộc, độ lớn item và chính sách Done có thể làm dự báo sai.

### Phân bố cycle time và SLE

Một **Service Level Expectation (SLE)** diễn đạt kỳ vọng về thời gian một item đi qua workflow, thường theo **một khoảng thời gian và tỷ lệ kỳ vọng** dựa trên dữ liệu lịch sử.

Ví dụ:

> “Theo lịch sử loại story tương đương, khoảng 85% item đã hoàn thành trong 10 ngày lịch kể từ khi bắt đầu.”

Khi một item đang mở đến ngày thứ 8–9, đội có thể chủ động hỏi về blocker. Nhưng kết quả lịch sử **không đảm bảo 85% công việc tương lai** sẽ giống hệt, đặc biệt khi mẫu ít, phân loại item thay đổi hoặc quá trình chưa ổn định.

**SLE không phải SLA.** Service Level Agreement có thể là thỏa thuận dịch vụ với nghĩa vụ được xác định; SLE là một kỳ vọng quản lý flow có điều kiện.

### Không dùng số liệu để thưởng phạt cá nhân

Một story 12 ngày bị chặn bởi đối tác không chứng minh người thực hiện kém năng lực. Thay vì ép “mỗi developer phải hoàn tất N ticket”, hãy tìm **thời gian chờ, nguyên nhân làm lại và quyết định hệ thống** có thể cải thiện.

## 10. Little’s Law và giới hạn của suy luận

Trong hệ thống dòng việc **ổn định tương đối**, có ranh giới đo nhất quán và lượng tồn đọng không tăng/giảm kéo dài, quan hệ trung bình thường được diễn đạt:

\[
\text{WIP trung bình} = \text{Throughput trung bình} \times \text{Cycle time trung bình}
\]

Ví dụ một hệ thống duy trì **WIP trung bình 10 item** và throughput trung bình **5 item/tuần**. Trong những điều kiện giả định phù hợp, cycle time trung bình tương ứng khoảng:

\[
\frac{10\ \text{item}}{5\ \text{item/tuần}}=2\ \text{tuần}
\]

### Ý nghĩa thực tế

Nếu throughput không tăng mà WIP cứ phình lên, **cycle time có nguy cơ dài hơn**. Khi đó, thay vì tự động mở thêm việc để mọi người “có việc làm”, nhóm có thể thử **giúp hoàn tất các item đã bắt đầu**.

Tuy nhiên:

- Little’s Law là quan hệ trung bình với **điều kiện áp dụng**, không phải công thức dự đoán thời gian của từng story.
- Một đội có throughput biến động lớn, backlog thay đổi liên tục hoặc dữ liệu chưa nhất quán cần thận trọng.
- **Giảm WIP không đảm bảo throughput giữ nguyên**; có thể phát sinh nhàn rỗi, chờ hoặc thiếu item sẵn sàng nếu thiết kế chính sách sai.
- Không nên suy ra tỷ lệ “x item/người/tuần” để quản lý cá nhân.

Kanban hữu ích khi **quan sát kết quả của việc điều chỉnh**, thay vì dùng một công thức như lý do áp đặt chính sách bất biến.

## 11. Dùng dữ liệu trong những buổi kiểm tra nào?

Không cần nhân đôi lịch họp của Scrum và Kanban. Mỗi vòng phản hồi cần **mục đích và quyền quyết định riêng**.

| Nhịp kiểm tra | Câu hỏi trọng tâm | Quyết định có thể tạo ra |
| --- | --- | --- |
| **Daily Scrum / flow meeting** | Item nào đang già? Sprint Goal hoặc dịch vụ nào bị rủi ro? | Swarm gỡ chặn, đổi thứ tự hỗ trợ, điều chỉnh Sprint Backlog nếu có |
| **Replenishment** | Việc nào đủ điều kiện kéo tiếp? Có năng lực/WIP còn trống? | Bổ sung hàng Sẵn sàng, chia nhỏ hoặc cần khám phá thêm |
| **Refinement** | Hạng mục sắp làm đã rõ giá trị, ngoại lệ và phụ thuộc chưa? | Bổ sung tiêu chí, rủi ro, lát cắt và người xác nhận |
| **Review sản phẩm / Sprint Review** | Increment đã tạo kết quả gì, người dùng phản hồi ra sao? | Điều chỉnh ưu tiên Product Backlog hoặc hướng đi |
| **Service/flow review** | Cycle time, throughput, SLE và lỗi đang thay đổi thế nào? | Thay chính sách flow và dự báo có điều kiện |
| **Retrospective / improvement review** | Cách làm nào đang cản đội? Thử nghiệm trước có hiệu quả không? | Chọn, giữ, sửa hoặc bỏ thử nghiệm |

Trong **Scrum**, Sprint Planning, Daily Scrum, Sprint Review và Sprint Retrospective **vẫn là các sự kiện Scrum**. Đội có thể tích hợp dữ liệu Kanban vào chúng để tránh sinh cuộc họp dư thừa. Hoạt động refinement không phải một sự kiện bắt buộc với timebox cố định theo Scrum Guide.

Trong mô hình **flow-first**, các nhịp không cần gọi giống Scrum; chỉ cần bảo đảm thông tin dẫn đến **quyết định rõ, người có quyền và điểm kiểm tra lại**.

## 12. Mô hình trách nhiệm và quyền ra quyết định

Hệ thống kết hợp dễ thất bại khi ai cũng tưởng **người khác** sẽ quyết định ưu tiên hoặc chất lượng. Bảng Kanban minh bạch không tự giải quyết vấn đề quyền sở hữu.

### Nếu là Scrum Team sử dụng Kanban

- **Product Owner** tối đa hóa giá trị sản phẩm và chịu trách nhiệm quản lý Product Backlog, gồm thứ tự item.
- **Developers** tạo kế hoạch Sprint, điều chỉnh Sprint Backlog và chịu trách nhiệm tuân thủ Definition of Done để tạo Increment dùng được.
- **Scrum Master** chịu trách nhiệm thiết lập Scrum và hiệu quả Scrum Team; giúp đội hiểu thực nghiệm, tháo trở ngại và cải tiến.
- **Cả Scrum Team** cộng tác xác định Sprint Goal trong Sprint Planning và cùng chịu trách nhiệm tạo Increment có giá trị mỗi Sprint.

Các chính sách Kanban hỗ trợ **minh bạch, cộng tác và năng lực giao hàng**, không chuyển trách nhiệm Product Owner cho một “board manager” hay biến Scrum Master thành người phân công task.

### Nếu vận hành flow-first không đầy đủ Scrum

Đội vẫn cần trả lời:

1. **Ai quyết định thứ tự và mức độ khẩn** của yêu cầu?
2. **Ai quyết định công việc đủ điều kiện kéo vào và khi nào Done?**
3. **Ai giải quyết xung đột giữa mục tiêu sản phẩm, sự cố và phụ thuộc?**
4. **Ai có quyền chấp nhận rủi ro hoặc phê duyệt release theo chính sách?**
5. **Ai chủ trì xem lại dữ liệu và thử nghiệm cải tiến?**

Tên vai trò có thể tùy tổ chức, nhưng **trách nhiệm và quyền quyết định phải rõ**, nhất là với dữ liệu cá nhân, an toàn và nghĩa vụ hợp đồng.

## 13. Kết hợp XP để giảm chi phí thay đổi

Một đội có bảng đẹp và WIP limit hợp lý vẫn có thể giao chậm nếu phần mềm khó thay đổi, pipeline lỗi hoặc API liên tục làm hỏng phần đang hoạt động.

Một số thực hành XP hỗ trợ dòng công việc:

| Thực hành | Tác động có thể có lên flow | Điều cần kiểm chứng |
| --- | --- | --- |
| **TDD / kiểm thử tự động** | Phát hiện sai logic sớm; giảm vòng làm lại và chờ test thủ công | Test có phản ánh rủi ro, độ ổn định và chất lượng thực tế không? |
| **Continuous Integration (CI)** | Giảm lỗi tích hợp xuất hiện muộn; phản hồi nhanh khi merge | Pipeline có đủ test, chạy đủ nhanh và đáng tin không? |
| **Refactoring** | Giảm chi phí thêm yêu cầu khi cấu trúc code không còn phù hợp | Có test giữ hành vi, thay đổi nhỏ và không tạo lỗi mới không? |
| **Pair programming / swarming** | Chia sẻ kiến thức, hỗ trợ item đang blocked, giảm handoff | Có giảm cycle time hoặc lỗi mà không gây quá tải không? |
| **Simple Design / YAGNI** | Tránh xây khả năng tương lai chưa có nhu cầu, tạo lát cắt nhỏ | Có bỏ sót nghĩa vụ bảo mật hay kiến trúc khó đảo ngược không? |
| **Small releases** | Tạo cơ hội nhận phản hồi thường xuyên hơn | Increment có usable và đáp ứng DoD, release có an toàn không? |

### Ví dụ một điểm nghẽn kỹ thuật

Đội nhận ra **cycle time của story tích hợp API thường kéo dài** vì lỗi hợp đồng chỉ xuất hiện lúc kiểm thử cuối kỳ. Họ thử:

1. Trao đổi ví dụ giữa Product Owner, Developer và Tester trước khi bắt đầu story.
2. Viết **contract test** cho trường hợp thành công và lỗi.
3. Tích hợp nhánh nhỏ thường xuyên qua CI.
4. Giữ chính sách không kéo thêm nhiều item khi bài test tích hợp đang đỏ.
5. So sánh tuổi item, lỗi phải làm lại, độ ổn định pipeline và phản hồi người dùng sau vài chu kỳ.

**Không thể chỉ thêm CI rồi kết luận flow tốt hơn.** CI phải cung cấp tín hiệu đúng, và đội cần quan sát xem thời gian chờ cùng chất lượng có thay đổi hay không.

## 14. Dùng Sprint Goal, DoD và flow để chống “đóng ticket cho đẹp”

Khi kết hợp phương pháp, cần tránh việc tối ưu một chỉ số cục bộ làm mất giá trị chung.

### Ba tầng cần đồng thời có

1. **Mục tiêu sản phẩm/Sprint Goal:** Kết quả nào thực sự quan trọng?
2. **Dòng công việc:** Các item tiến đến kết quả với WIP, thời gian chờ và trở ngại ra sao?
3. **Chất lượng hoàn thành:** Increment có thực sự dùng được, tích hợp và đáp ứng DoD/chính sách Done không?

Ví dụ đội đóng 20 ticket “Done” trong Sprint, nhưng luồng “Tiếp tục học” chưa chạy được vì API và UI chưa tích hợp. **Throughput ticket cao** không chứng minh đội đã có Increment đạt DoD hoặc đã đạt Sprint Goal.

### Giữ chất lượng trong mọi mô hình

Với Scrum, một Product Backlog Item chưa đạt **Definition of Done** không được xem là một phần của Increment hoàn thành. Khi dùng Kanban thuần hoặc Scrumban flow-first, đội cũng cần chính sách **Done** có nghĩa rõ, gồm kiểm thử, phân quyền, dữ liệu và vận hành phù hợp.

Khi phát hiện lỗi lộ dữ liệu, không có phương pháp nào cho phép **bỏ test phân quyền** để tăng throughput. Cần xem lại phạm vi, dự báo và năng lực, thay vì hạ tiêu chuẩn sản phẩm.

### Phân biệt release và nhịp lập kế hoạch

Một Increment đáp ứng DoD và các điều kiện phát hành có thể được giao trước Sprint Review. Đội flow-first cũng có thể release theo nhu cầu. **Nhịp release không buộc trùng nhịp họp, replenishment hoặc Sprint**, miễn kiểm soát an toàn và quyền quyết định phù hợp.

## 15. Tình huống hoàn chỉnh: đội học trực tuyến từ Scrum sang cách kết hợp

### 15.1. Bối cảnh giả định

Một Scrum Team gồm Product Owner, Scrum Master và Developers phụ trách:

- Xây các tính năng học trực tuyến.
- Sửa lỗi ảnh hưởng tiến độ học.
- Tích hợp API với hệ thống doanh nghiệp.
- Hỗ trợ sự cố production và yêu cầu báo cáo.

Đội đang dùng Sprint hai tuần. Sprint Goal thường hướng vào một tính năng, nhưng giữa Sprint xuất hiện nhiều yêu cầu khẩn và việc review dồn lại. Có những Sprint kết thúc với nhiều task “code done” nhưng ít Increment đạt Definition of Done.

**Product Goal** hiện tại:

> “Học viên có thể tiếp tục học trên thiết bị thường dùng và không mất tiến độ đã ghi nhận.”

### 15.2. Quan sát trước khi thay đổi

Đội thu thập dữ liệu trong bốn tuần đầu (số liệu hoàn toàn minh họa):

| Tuần | Throughput: PBI/bug Done | WIP trung bình | Vấn đề nổi bật |
| --- | ---: | ---: | --- |
| 1 | 4 | 12 | Nhiều story chờ review |
| 2 | 5 | 11 | Lỗi API phát hiện muộn |
| 3 | 3 | 13 | Có sự cố production |
| 4 | 4 | 12 | Kiểm thử tích hợp dồn cuối Sprint |
| **Tổng/trung bình** | **16 item / 4 item/tuần** | **12 item** | Có nhiều giả thuyết cần điều tra |

Đội chưa đủ căn cứ kết luận “Scrum gây chậm”. Các nguyên nhân có thể là WIP quá cao, phụ thuộc API, chất lượng tích hợp hoặc chính sách ưu tiên khẩn chưa rõ.

### 15.3. Chọn mô hình: giữ Scrum, bổ sung Kanban và XP

Vì đội vẫn tạo được một mục tiêu sản phẩm cụ thể theo Sprint, họ quyết định **giữ khung Scrum** và thử trong bốn tuần:

- Product Owner tiếp tục sắp thứ tự Product Backlog.
- Scrum Team xác định **một Sprint Goal có giá trị** trong Sprint Planning.
- Developers giữ Sprint Backlog là kế hoạch có thể điều chỉnh.
- Bảng phản ánh các trạng thái **Đang làm – Review – Kiểm thử/tích hợp – Done**.
- Đặt **WIP limit thử nghiệm** ở Đang làm và Review; dừng kéo việc mới khi đang nghẽn.
- Có chính sách **expedite cho sự cố nghiêm trọng**, ghi tác động lên Sprint Goal và dự báo.
- Dùng **contract test và CI** cho luồng lưu/đọc tiến độ.
- Daily Scrum xem item đang già, blocker và khả năng đạt Sprint Goal; Sprint Review kiểm tra Increment thật; Retrospective đánh giá thử nghiệm.

**Lưu ý:** Đây là **Scrum sử dụng Kanban**, không phải “đã bỏ Scrum vì dùng bảng”.

### 15.4. Minh họa chính sách đơn giản

~~~text
MỤC TIÊU:
  Học viên mở lại bài gần nhất đúng quyền, dữ liệu tiến độ đáng tin.

ĐIỂM BẮT ĐẦU:
  PBI/bug được Developers kéo vào Đang làm.

ĐIỂM HOÀN TẤT:
  Đạt Definition of Done, đã tích hợp và kiểm chứng.

WIP THỬ NGHIỆM:
  Đang làm <= 3 PBI/bug.
  Review <= 2 PBI/bug.
  Các giới hạn này không phải chuẩn dùng cho đội khác.

KHI REVIEW ĐẦY:
  Ưu tiên review/pair/swarm và giải quyết blocker.
  Không chuyển nhãn để che WIP hoặc tự kéo thêm việc.

VIỆC KHẨN:
  Sự cố dữ liệu/quyền truy cập nghiêm trọng theo tiêu chí đã thống nhất.
  Người trực sự cố phối hợp PO và Developers, ghi ảnh hưởng kế hoạch.

CHẤT LƯỢNG:
  Không hạ DoD; kiểm tra quyền, dữ liệu, tích hợp và hồi quy.

KIỂM TRA:
  Daily Scrum: Sprint Goal, item già, blocked.
  Sprint Review: Increment và phản hồi.
  Retrospective: WIP, cycle time, throughput, chất lượng.
~~~

### 15.5. Một tình huống giữa Sprint

Ngày thứ tư, đội phát hiện request lưu tiến độ bị gửi lặp có thể ghi sai thứ tự học. Cùng lúc, bên kinh doanh đề nghị tạo dashboard huy hiệu.

**Cách xử lý có chủ đích:**

1. Lỗi tiến độ được đánh giá mức nghiêm trọng theo chính sách, không chờ tới Sprint Review.
2. Developers minh bạch blocker và ưu tiên khôi phục tính toàn vẹn dữ liệu, chạy lại test tích hợp.
3. Product Owner trao đổi tác động lên Sprint Goal, thứ tự backlog và phạm vi nếu cần.
4. Yêu cầu dashboard được làm rõ và xếp thứ tự trong Product Backlog, không tự chen vào Sprint chỉ vì một bên đề nghị.
5. Sau khi khắc phục, đội kiểm tra liệu Increment có thực sự đạt DoD và sản phẩm có sử dụng được không.

**Sprint Goal** giúp đội biết mục tiêu nào phải bảo vệ; **Kanban** giúp thấy công việc nào bị chặn; **XP** cung cấp cách kiểm thử và tích hợp an toàn.

### 15.6. Kết quả thử nghiệm giả định

Trong bốn tuần tiếp theo, đội ghi:

| Chỉ số | Bốn tuần trước | Bốn tuần sau | Diễn giải thận trọng |
| --- | --- | --- | --- |
| Throughput | 16 item | 20 item | Tăng từ 4 lên 5 item/tuần trong mẫu ngắn |
| WIP trung bình | 12 item | 8 item | Lượng công việc đang mở giảm |
| Cycle time trung vị | 11 ngày | 8 ngày | Có tín hiệu tích cực; cần xem đuôi dài |
| Item chờ review quá mức nội bộ | 6 | 3 | Cần xác nhận loại item và cách đo vẫn như cũ |
| Lỗi nghiêm trọng thoát ra production | 1 | 1 | Chưa có bằng chứng chất lượng cải thiện rõ từ mẫu rất nhỏ |

Tất cả dữ liệu là **minh họa**. Không thể kết luận chỉ vì giới hạn WIP mà cycle time giảm: cùng kỳ có thể đã hết một phụ thuộc API, có ít sự cố hoặc story được chia nhỏ hơn.

### 15.7. Quyết định sau hai Sprint

Một kết luận có trách nhiệm:

> “WIP và cycle time giảm trong giai đoạn thử, throughput tăng vừa phải, chưa thấy tín hiệu chất lượng xấu đi. Chúng ta sẽ tiếp tục chính sách WIP thêm một chu kỳ, xem phân bố cycle time và tuổi item chưa xong, đồng thời kiểm tra tác động của contract test. Chính sách sự cố khẩn và DoD vẫn giữ nguyên.”

Đây là **cải tiến dựa trên dữ liệu**, không phải khẳng định đã tìm ra một mô hình hoàn hảo vĩnh viễn.

## 16. Một tình huống khác: khi nên chuyển sang flow-first

Một nhóm chuyên hỗ trợ API và xử lý lỗi nhận hầu hết yêu cầu **không thể dự báo từ đầu kỳ**. Họ thử dùng Sprint hai tuần nhưng liên tục điều chỉnh toàn bộ danh sách vì sự cố và thay đổi đối tác. Sprint Goal thường trở thành “Xử lý các ticket đến trong Sprint”.

Nhóm cần đánh giá:

1. Có **mục tiêu chung có giá trị** nào đủ ổn định để tổ chức theo Sprint không?
2. Việc phải phản ứng trong ngày chiếm tỷ lệ bao nhiêu, tính cả thời gian hỗ trợ?
3. Có thể quản lý ưu tiên, năng lực và chất lượng bằng **dòng liên tục** tốt hơn không?
4. Nếu bỏ Scrum đầy đủ, **trách nhiệm giá trị và việc cải tiến** được bảo đảm ra sao?

Họ có thể chọn Kanban làm cách tổ chức chính:

- Replenishment ngắn khi hàng Sẵn sàng cần được bổ sung.
- Chính sách expedite rõ và WIP phù hợp.
- Mốc start/finish, SLE và phân loại hạng mục minh bạch.
- Review dịch vụ với các bên liên quan theo tuần hoặc tháng tùy nhu cầu.
- Thử nghiệm cải tiến về review, test và phụ thuộc bên ngoài.

Điều đó không làm đội “kém Agile”. **Agile là khả năng thích ứng qua giá trị và phản hồi, không phải số lượng buổi Sprint Planning**.

Nhưng khi không còn đầy đủ ba trách nhiệm, các sự kiện và tạo tác Scrum, hãy gọi đúng tên cách làm, tránh tuyên bố đội vẫn tuân thủ Scrum Guide.

## 17. Thiết kế thử nghiệm chuyển đổi có kiểm soát

Không nên đổi toàn bộ hệ thống một lần vì thấy tên “Scrumban” hấp dẫn. Hãy chuyển đổi như một **thử nghiệm**.

### Mẫu thử nghiệm

| Trường | Nội dung cần ghi |
| --- | --- |
| **Vấn đề** | Ví dụ: story chờ review và kiểm thử quá lâu; lỗi khẩn liên tục phá kế hoạch |
| **Dữ liệu nền** | WIP, phân bố cycle time, throughput, tỷ lệ blocked, lỗi và phản hồi người dùng |
| **Giả thuyết** | Nếu giới hạn WIP và giúp hoàn tất item già trước khi kéo thêm, cycle time có thể giảm |
| **Thay đổi** | Chính sách WIP ở cột nào, ai áp dụng, cách xử lý ngoại lệ khẩn |
| **Thời hạn quan sát** | Ví dụ 2–4 tuần hoặc đủ chu kỳ item phù hợp; nêu vì sao |
| **Chỉ số chính** | Cycle time, tuổi item bị chặn, tỷ lệ Done, thời gian chờ review |
| **Guardrail** | DoD, lỗi nghiêm trọng, mất dữ liệu, quá tải nhân sự, phản hồi người dùng |
| **Quyết định** | Giữ, điều chỉnh, bỏ hoặc điều tra thêm sau khi xem bối cảnh |

### Bảy bước chuyển đổi

1. **Quan sát hệ thống hiện tại:** Tên phương pháp không quan trọng bằng thực trạng chờ, lỗi và giá trị.
2. **Làm rõ mục tiêu cải tiến:** Ví dụ “giao thay đổi học viên nhanh và an toàn hơn” thay vì “chuyển sang Scrumban”.
3. **Giữ những gì đang tạo giá trị:** Sprint Goal, review khách hàng hoặc CI không cần bỏ chỉ vì đổi phương pháp.
4. **Bổ sung ít chính sách có tác dụng:** Bắt đầu bằng workflow thật, WIP, blocked và quyền ưu tiên.
5. **Thu thập dữ liệu nhất quán:** Đừng đổi định nghĩa Done giữa chừng rồi so sánh throughput.
6. **Xem tác dụng cùng chất lượng và outcome:** Một chỉ số tốt lên có thể đi kèm lỗi hoặc tăng làm thêm giờ.
7. **Quyết định và truyền đạt:** Minh bạch mô hình hiện tại, trách nhiệm, thay đổi và thời điểm kiểm tra lại.

Một thử nghiệm thất bại **vẫn có giá trị học hỏi** nếu đội hiểu được điều kiện vì sao không phù hợp. Không cần đổ lỗi cho người đề xuất hoặc tiếp tục duy trì một chính sách không có bằng chứng chỉ để “giữ thể diện”.

## 18. Các phản ví dụ cần tránh

| Hiểu sai hoặc phản ví dụ | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| **“Scrumban chỉ là Scrum có bảng Trello.”** | Có tên mới nhưng không có chính sách flow | Định nghĩa start/finish, WIP, pull, blocked và nhịp kiểm tra |
| **“Có WIP limit thì không cần mục tiêu sản phẩm.”** | Tối ưu số ticket nhưng không biết điều gì có giá trị | Duy trì Product Goal/outcome hoặc mục tiêu dịch vụ có chủ sở hữu |
| **“Làm Scrumban thì được bỏ tùy ý các sự kiện Scrum nhưng vẫn gọi là Scrum.”** | Mọi người hiểu nhầm trách nhiệm và cam kết | Nêu rõ đội dùng Scrum với Kanban hay mô hình flow-first |
| **“Product Owner phải giao việc từng người vì có việc khẩn.”** | Giảm tự quản, tăng bottleneck quyết định | PO quản lý giá trị và backlog; Developers tổ chức thực hiện |
| **“Giảm WIP là phải để mọi người ít việc hơn.”** | Nhầm mục tiêu với sự nhàn rỗi; phản ứng tiêu cực | Giải thích ưu tiên hoàn tất, hỗ trợ review/test và giảm chờ |
| **“Mọi item đều là expedite.”** | Dòng thường xuyên bị gián đoạn, không thể dự báo | Có tiêu chí khẩn thực chất, xem xét lại tần suất và nguyên nhân |
| **“Throughput cao thì nhóm đã thành công.”** | Có thể tăng ticket nhỏ hoặc bỏ test | Kiểm tra chất lượng, Increment, outcome và độ nhất quán cách đếm |
| **“Daily Scrum cần đọc hết mọi ticket.”** | Mất thời gian mà không điều chỉnh kế hoạch | Tập trung Sprint Goal, item già/blocked và hành động |
| **“Dùng Kanban thì không cần TDD hoặc CI.”** | Lỗi tích hợp tiếp tục gây chờ và làm lại | Bổ sung thực hành kỹ thuật theo rủi ro và đo tác dụng |
| **“Cycle time là thời gian lập trình.”** | Bỏ qua thời gian chờ và phụ thuộc | Đo thời gian trôi qua từ start đến finish với mốc rõ |
| **“Một tuần sau thử nghiệm đã đủ chứng minh.”** | Biến động tự nhiên dễ bị hiểu là tác động | Xem nhiều kỳ, phân bố và yếu tố đồng thời |
| **“Không được thay kế hoạch Sprint trong bất cứ tình huống nào.”** | Bỏ qua thông tin mới hoặc lỗi nghiêm trọng | Giữ Sprint Goal và DoD, thích nghi Sprint Backlog khi cần |
| **“Đã tích hợp code thì Increment Done.”** | Lộ rủi ro bảo mật và chất lượng | Chỉ gọi Done khi đạt DoD và dùng được |
| **“Chuyển phương pháp là giải quyết vấn đề nhân sự/quyền ưu tiên.”** | Trách nhiệm vẫn mơ hồ | Làm rõ quyền quyết định, tương tác và rủi ro hệ thống |

## 19. Khung tự đánh giá mô hình kết hợp

Khi một đội tuyên bố đã chọn Scrumban, hãy dùng các câu hỏi thay vì hỏi “đã làm đúng từng bước chưa”:

| Góc nhìn | Câu hỏi quan trọng | Bằng chứng nên có |
| --- | --- | --- |
| **Giá trị** | Đội đang cải thiện kết quả người dùng nào? | Product Goal hoặc mục tiêu dịch vụ, feedback, outcome |
| **Trách nhiệm** | Ai sắp thứ tự backlog, ai lập kế hoạch và bảo đảm chất lượng? | Quyền quyết định rõ, ít tranh chấp hoặc handoff mơ hồ |
| **Flow** | Item đi qua những trạng thái nào, nghẽn ở đâu? | Bảng phản ánh thực tế, blocked, WIP và work item age |
| **Dự báo** | Dữ liệu lịch sử và điều kiện được dùng ra sao? | Throughput/cycle time với ranh giới rõ, dự báo có điều kiện |
| **Chất lượng** | Làm sao biết một Increment/item thực sự Done? | DoD/chính sách chất lượng, kiểm thử và tích hợp |
| **Khẩn cấp** | Trường hợp nào được phép phá thứ tự thông thường? | Tiêu chí expedite, người quyết định, tác động được ghi |
| **Học hỏi** | Thử nghiệm trước thay đổi gì, kết quả thế nào? | Giả thuyết, dữ liệu trước/sau, guardrail và quyết định |
| **Bền vững** | Đội có đang cần overtime liên tục để giữ số liệu? | Tín hiệu quá tải, lỗi, nghỉ việc, phản hồi của thành viên |

Nếu thiếu **mục tiêu, trách nhiệm, chính sách luồng hoặc chất lượng**, việc thay tên phương pháp hiếm khi giải quyết được vấn đề.

## 20. Bài tập thực hành

### Bài tập 1 — Chọn mô hình theo bối cảnh

Ba đội có đặc điểm:

1. **Đội A:** Xây tính năng sản phẩm theo mục tiêu quý, có thể giao Increment mỗi Sprint, chỉ thỉnh thoảng nhận lỗi khẩn.
2. **Đội B:** Xử lý sự cố và yêu cầu API liên tục; đa số ticket đến sau khi kỳ làm việc đã bắt đầu.
3. **Đội C:** Có một mục tiêu sản phẩm rõ, nhưng 30–40% năng lực thường bị chi phối bởi hỗ trợ production và kiểm thử tích hợp.

**Yêu cầu:** Chọn cho mỗi đội một hướng ban đầu: Scrum với Kanban, flow-first hoặc tiếp tục cách làm hiện tại nhưng thêm một thực hành. Nêu **ít nhất hai điều kiện cần xác minh** trước khi quyết định.

**Gợi ý:** Không dựa vào một tỷ lệ % như quy tắc tuyệt đối. Xem giá trị của Sprint Goal, năng lực, mức khẩn và khả năng kiểm chứng Increment.

### Bài tập 2 — Thiết kế workflow và WIP

Một đội có các bước: “Chưa rõ – Sẵn sàng – Đang làm – Review – Test – Done”, thường có sáu story chờ review và hai người có thể review.

**Yêu cầu:** Đề xuất:

- Start point và finish point.
- Điều kiện kéo việc vào “Đang làm”.
- Một mức WIP thử nghiệm cho “Đang làm” và “Review”, giải thích lý do.
- Hành động khi Review đầy và quy tắc blocked.
- Hai chỉ số để kiểm tra tác dụng sau vài tuần.

**Gợi ý:** Không có giới hạn WIP đúng sẵn. Hãy giải thích vì sao giới hạn thử phù hợp với thực trạng, và điều gì khiến cần điều chỉnh.

### Bài tập 3 — Xử lý yêu cầu khẩn trong Sprint

Sprint Goal: “Học viên mở lại được bài học hợp lệ gần nhất”. Giữa Sprint, đội nhận:

- Lỗi khiến tài khoản khác đọc được tiến độ học.
- Đề nghị thêm huy hiệu thành tích.
- Cần nâng thư viện nội bộ không ảnh hưởng an toàn ngay lập tức.

**Yêu cầu:** Áp dụng chính sách expedite và trách nhiệm Scrum để phân loại ba việc. Viết nội dung Daily Scrum ngắn nêu điều cần ưu tiên, tác động Sprint Backlog và việc phải trao đổi với Product Owner.

**Gợi ý:** Lỗi quyền truy cập cần được đánh giá và xử lý theo mức nghiêm trọng; yêu cầu huy hiệu không tự động chen vào Sprint; chất lượng bắt buộc không được hạ.

### Bài tập 4 — Đọc dữ liệu flow có điều kiện

Một đội hoàn tất **4, 5, 3, 4, 4, 4** item trong sáu tuần; backlog còn **12 item tương đối tương đồng**. WIP trung bình là 10 item.

**Yêu cầu:** Tính throughput trung bình, hai kịch bản thời gian giao theo nhịp 3 và 5 item/tuần; giải thích vì sao không thể kết luận chắc chắn ngày hoàn thành. Nếu giả định hệ thống ổn định ở throughput trung bình, dùng Little’s Law ước lượng cycle time trung bình tương ứng và nêu giới hạn.

**Gợi ý đáp án:** Throughput **4 item/tuần**; kịch bản **4 tuần** ở nhịp 3 và **2,4 tuần** ở nhịp 5. Little’s Law trong điều kiện giả định cho cycle time **10/4 = 2,5 tuần**. Đây không phải thời gian chắc chắn cho từng item.

### Bài tập 5 — Cải tiến pipeline hay thay đổi quy trình?

Nhóm có WIP không cao nhưng story tích hợp API thường chờ 7–10 ngày vì pipeline không ổn định, thiếu contract test và nhà cung cấp trả lời chậm.

**Yêu cầu:** So sánh ba hướng: giảm WIP, thêm cuộc họp trạng thái, đầu tư kiểm thử hợp đồng và cải tiến pipeline. Chọn một thử nghiệm ưu tiên, mô tả cách đo, guardrail và điều gì sẽ khiến đổi giả thuyết.

**Gợi ý:** WIP thấp không đồng nghĩa thiếu vấn đề flow. Cần nhắm vào nguyên nhân chờ đã quan sát.

### Bài tập 6 — Nhận diện cách dùng tên phương pháp thiếu chính xác

Một đội tuyên bố “Chúng tôi dùng Scrum với Kanban” nhưng không có Product Owner, không có Sprint Goal, bỏ Sprint Review và Sprint Retrospective. Đội vẫn có bảng Kanban và WIP limit.

**Yêu cầu:** Giải thích vì sao tuyên bố này gây hiểu nhầm. Đề xuất **hai lựa chọn rõ ràng**:

1. Khôi phục đầy đủ những phần Scrum cần thiết và bổ sung Kanban.
2. Gọi cách làm là mô hình Kanban/flow-first kết hợp thực hành phù hợp, xác định rõ trách nhiệm và nhịp phản hồi.

**Gợi ý:** Không có cách chọn nào là “thua cuộc”; vấn đề là sự minh bạch giữa cách gọi và cách vận hành thật.

### Bài tập 7 — Thiết kế thử nghiệm chuyển đổi Scrumban

Trước thử nghiệm, đội có throughput 16 item/bốn tuần, WIP trung bình 12, cycle time trung vị 11 ngày và nhiều lỗi tích hợp. Đội muốn áp dụng WIP limit, contract test và có chính sách xử lý khẩn.

**Yêu cầu:** Lập kế hoạch thử nghiệm bốn tuần: mục tiêu, can thiệp, dữ liệu cần thu, guardrail, vai trò quyết định, cách kiểm tra tác động và thời điểm xem lại. Nêu khó khăn khi thay **nhiều biến số cùng lúc**.

**Gợi ý:** Chọn trọng tâm có thể quan sát; ghi rõ các yếu tố cùng thay đổi, không khẳng định nhân quả chỉ từ dữ liệu trước/sau.

### Bài tập 8 — Vẽ mô hình kết hợp của chính bạn

Chọn một sản phẩm giả định có cả xây tính năng, vận hành và phụ thuộc đối tác. Vẽ:

- Nguồn nhu cầu và quyền quyết định ưu tiên.
- Workflow, điểm start/finish và WIP limit thử nghiệm.
- Cách xử lý expedite, ngày cố định và việc khám phá.
- Nhịp xem Product Goal/outcome, flow và cải tiến.
- Các cổng chất lượng kỹ thuật cần có trước khi gọi Done.

**Tiêu chí đánh giá:** Mô hình giải thích được **vì sao** từng thực hành tồn tại, người ra quyết định, dữ liệu kiểm chứng và rủi ro khi bỏ một cơ chế.

## 21. Checklist áp dụng Scrumban có chủ đích

- [ ] Nhóm đã mô tả **vấn đề dòng công việc thật** cần cải thiện, không chỉ chọn một tên mới?
- [ ] Đã phân biệt **Scrum với Kanban** và **mô hình Scrumban flow-first** trong cách truyền thông?
- [ ] Nếu nói đang dùng Scrum, các trách nhiệm, sự kiện, tạo tác và cam kết Scrum còn nguyên vẹn?
- [ ] Có mục tiêu sản phẩm/dịch vụ và tiêu chí giá trị rõ?
- [ ] Người có quyền **ưu tiên, kéo việc, xác nhận chất lượng và quyết định phát hành** đã được xác định?
- [ ] Bảng Kanban phản ánh các trạng thái thật, gồm chờ review, kiểm thử và blocked?
- [ ] Start point, finish point và quy tắc đếm item được định nghĩa nhất quán?
- [ ] Các giới hạn WIP dựa trên thử nghiệm, không sao chép vô căn cứ?
- [ ] Có chính sách **hoàn tất trước khi bắt đầu thêm** khi phù hợp?
- [ ] Chính sách expedite và ngày cố định có tiêu chí, người quyết định và cơ chế minh bạch tác động?
- [ ] Đã chọn vòng feedback phù hợp, không tạo hai buổi họp cùng mục đích chỉ để “kết hợp”?
- [ ] Đội quan sát WIP, throughput, cycle time và work item age khi cần?
- [ ] SLE/dự báo có điều kiện, không được trình bày như bảo đảm thống kê hoặc SLA?
- [ ] CI, kiểm thử, refactoring và các thực hành XP được xem xét theo điểm nghẽn thực?
- [ ] Definition of Done hoặc tiêu chuẩn chất lượng được giữ nhất quán, không dùng số ticket thay giá trị?
- [ ] Các Increment có thể sử dụng, tích hợp và bảo vệ quyền truy cập/dữ liệu?
- [ ] Thử nghiệm có giả thuyết, thời hạn quan sát, chỉ số, guardrail và quyết định sau thử?
- [ ] Việc so sánh trước/sau có xét loại item, năng lực, phụ thuộc và biến động tự nhiên?
- [ ] Các chỉ số hỗ trợ cải tiến hệ thống thay vì xếp hạng hay gây áp lực cá nhân?
- [ ] Có kế hoạch điều chỉnh mô hình khi bối cảnh thay đổi, không coi cách làm hiện tại là vĩnh viễn?

Checklist giúp đội **tự kiểm tra sự nhất quán của cơ chế phối hợp**, không phải công cụ chấm điểm mức “thuần Scrum” hay “thuần Kanban”.

## 22. Tổng kết

- **Scrumban là tên gọi cho những cách kết hợp Scrum và Kanban, không có một bộ quy tắc chuẩn duy nhất.** Hãy mô tả rõ đội giữ nhịp nào, chính sách pull/WIP nào và trách nhiệm quyết định ra sao.
- **Scrum với Kanban vẫn là Scrum:** Không bỏ Sprint Goal, Product Backlog, Sprint Backlog, Definition of Done, trách nhiệm và các sự kiện Scrum chỉ vì đưa Kanban vào.
- **Flow-first phù hợp với những dòng yêu cầu liên tục** nếu đội vẫn minh bạch ưu tiên, chất lượng, phản hồi và cơ chế cải tiến. Không nhất thiết phải tổ chức Sprint giả tạo.
- **Giới hạn WIP, pull và tuổi item** giúp thấy điểm nghẽn; throughput và cycle time hỗ trợ dự báo có điều kiện. Không dùng các con số làm thước đo giá trị hoặc năng suất cá nhân.
- **Chính sách khẩn phải có ranh giới.** Xử lý sự cố nghiêm trọng nhanh nhưng minh bạch tác động lên kế hoạch, không đánh đổi bảo mật và dữ liệu.
- **XP cung cấp năng lực giao kỹ thuật**: TDD, CI, refactoring, pairing và phát hành nhỏ có thể giảm làm lại và tăng phản hồi, khi được áp dụng đúng nguyên nhân.
- **Kết hợp phải được thử nghiệm và kiểm chứng.** Dữ liệu về flow, chất lượng và outcome quan trọng hơn việc đội đang gọi bảng hoặc lịch họp bằng tên gì.

Khi cân nhắc Scrumban, câu hỏi nên là: **“Đội cần giữ cơ chế nào để tạo giá trị và giữ chất lượng, cần thêm cơ chế nào để công việc chảy tốt hơn, và sẽ dùng bằng chứng nào để kiểm tra rằng sự kết hợp ấy thật sự hữu ích?”**
