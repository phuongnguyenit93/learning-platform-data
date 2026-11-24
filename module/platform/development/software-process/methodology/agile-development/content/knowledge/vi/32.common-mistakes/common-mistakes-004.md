# Biến Daily Scrum thành báo cáo cho người quản lý

## 1. Một Daily Scrum tưởng như đúng quy trình nhưng không giúp nhóm tiến lên

08:45 sáng, Scrum Team phát triển nền tảng học trực tuyến bắt đầu cuộc họp 15 phút. Mười người đứng trước bảng công việc. Scrum Master lần lượt gọi tên:

> “Hôm qua em làm gì? Hôm nay làm gì? Có khó khăn gì không?”

Một Developer đáp: “Hôm qua em sửa API, hôm nay tiếp tục sửa”. Một tester đáp: “Em viết test, không có blocker”. Product Owner nghe, người quản lý ghi số lượng task hoàn thành. Khi đến lượt cuối, mọi người đã hết thời gian. Không ai nhắc đến **Sprint Goal**, dù lỗi cấp quyền trong API đang khiến tính năng “Tiếp tục học” không thể đạt Definition of Done. Hai pull request chờ review từ hôm trước vẫn chưa có người nhận. Cuộc họp kết thúc với câu: “Cảm ơn, cố gắng hoàn thành đúng hạn”.

Đến cuối Sprint, nhóm không tạo được Increment có thể dùng, nhưng Daily Scrum nào cũng diễn ra đúng giờ và có đủ ba câu trả lời.

Đây là sai lầm phổ biến: **biến Daily Scrum thành phiên báo cáo tiến độ cá nhân cho Scrum Master, Product Owner hoặc người quản lý**, thay vì dùng nó để **Developers tự kiểm tra tiến triển tới Sprint Goal và điều chỉnh Sprint Backlog**. Vấn đề không phải mọi câu hỏi cập nhật trạng thái đều sai; vấn đề là **mục đích cuộc họp đã bị thay thế**.

Trong module **AGILE_DEVELOPMENT**, Daily Scrum hỗ trợ tính minh bạch, kiểm tra–thích ứng và giao sản phẩm tăng dần qua phản hồi sớm. Nếu chỉ tạo báo cáo, nhóm có thể có nhiều dữ liệu về hoạt động cá nhân nhưng thiếu **quyết định chung để đưa một Increment đạt DoD tới người dùng**.

> **Thông điệp chính:** Daily Scrum thành công không phải khi ai cũng đã “báo cáo xong”, mà khi Developers hiểu rõ **Sprint Goal đang ở đâu, điều gì cản trở và kế hoạch hành động nào cần thay đổi ngay**.

## 2. Daily Scrum theo Scrum Guide có mục đích gì?

Theo Scrum Guide 2020, **Daily Scrum** là sự kiện dành cho **Developers của Scrum Team**, được tổ chức mỗi ngày làm việc của Sprint, **timebox 15 phút**, ở cùng một thời điểm và địa điểm nhằm giảm độ phức tạp trong điều phối.

Mục đích của nó là:

- **Kiểm tra tiến triển hướng tới Sprint Goal**.
- **Thích ứng Sprint Backlog khi cần**, điều chỉnh công việc dự kiến tiếp theo.
- Tạo ra một **kế hoạch hành động có thể thực hiện cho ngày làm việc tiếp theo**.

Developers có thể chọn **cấu trúc và kỹ thuật bất kỳ** cho Daily Scrum, miễn tập trung vào tiến triển tới Sprint Goal và tạo ra kế hoạch có thể hành động. Scrum Guide không yêu cầu mọi người phải đứng, nói ba câu cố định, lần lượt điểm danh hay báo cáo cho một người điều phối.

### Bốn điểm dễ bị hiểu sai

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “Daily Scrum là cuộc họp báo cáo hằng ngày cho Scrum Master” | **Sai** | Developers dùng sự kiện để kiểm tra và thích ứng kế hoạch, không phải để gửi báo cáo lên Scrum Master |
| “Ba câu hỏi hôm qua–hôm nay–blocker là bắt buộc” | **Sai** | Đó là một kỹ thuật có thể dùng, không phải cấu trúc bắt buộc của Scrum Guide 2020 |
| “Daily Scrum phải kéo dài đúng 15 phút” | **Không chính xác** | 15 phút là **timebox tối đa**, không phải thời lượng tối thiểu |
| “Trong Daily Scrum phải giải quyết xong mọi vấn đề kỹ thuật” | **Sai** | Có thể xác định vấn đề và người phối hợp, rồi trao đổi chuyên sâu ngay sau đó |
| “Sprint Backlog không được thay đổi trong Sprint” | **Sai** | Developers thích ứng Sprint Backlog khi học được điều mới, cùng bảo vệ Sprint Goal và trao đổi với PO nếu phạm vi cần thương lượng |
| “Daily Scrum là thời điểm duy nhất Developers được điều chỉnh kế hoạch” | **Sai** | Developers có thể gặp và điều chỉnh kế hoạch bất cứ lúc nào trong Sprint |
| “Có quản lý ngồi nghe thì tự động không còn là Daily Scrum” | **Quá đơn giản** | Cần xem người tham gia có làm lệch mục đích, áp đặt báo cáo hoặc cản quyền tự quản hay không |

### Ai thực sự tham gia?

Daily Scrum là sự kiện cho **Developers**. Nếu Product Owner hoặc Scrum Master đang tích cực làm các công việc trong Sprint Backlog thì họ **tham gia như Developers**. Nếu họ không làm công việc ấy, họ không phải người nhận báo cáo mặc định, cũng không có lý do dùng Daily Scrum để giao task hoặc đánh giá từng người.

Tổ chức có thể có quy định hợp lý về người quan sát, phối hợp hoặc cập nhật tình hình, nhưng những quy định đó **không nên biến sự kiện thành cuộc họp kiểm soát công việc cá nhân**. Scrum Master hỗ trợ hiểu và thực hành Scrum đúng; trách nhiệm tiến hành Daily Scrum thuộc Developers.

### Kết quả thực chất cần thấy

Sau 15 phút hoặc ít hơn, Developers nên nắm được:

1. **Sprint Goal còn đạt được không và bằng chứng là gì?**
2. **Việc nào quan trọng nhất để tiến tới mục tiêu**, không chỉ việc của từng người?
3. **Điều gì cần đổi ngay trong kế hoạch**: thứ tự, phối hợp, review, test, giúp tháo blocker?
4. **Ai sẽ làm gì tiếp theo cùng ai**, đặc biệt với những việc không thể hoàn thành bằng một người?

Không cần một biên bản dài nếu kế hoạch và bảng công việc đã minh bạch.

## 3. Phân biệt Daily Scrum với cuộc họp trạng thái

Một cuộc họp trạng thái có thể hợp lệ cho một mục đích quản trị riêng. Sai lầm xảy ra khi nó **chiếm chỗ của Daily Scrum**, khiến Developers không còn không gian kiểm tra–thích ứng.

| Tiêu chí | Daily Scrum phục vụ Developers | Cuộc họp status/reporting |
| --- | --- | --- |
| **Câu hỏi trung tâm** | Cần điều chỉnh gì để đạt Sprint Goal? | Ai đã làm gì, tiến độ cá nhân ra sao? |
| **Người hưởng lợi chính** | Developers đang tạo Increment | Người quản lý/người yêu cầu báo cáo |
| **Đối tượng kiểm tra** | Mục tiêu chung, Sprint Backlog, chất lượng, phụ thuộc | Danh sách hoạt động và mức hoàn thành của từng cá nhân |
| **Cách nói** | “PR quyền học đang chặn hai PBI; ai giúp review/test?” | “Em đã hoàn thành ba task; đang làm task thứ tư” |
| **Quyền ra quyết định** | Developers tự phối hợp và thích ứng kế hoạch | Người nghe có thể phân công, phê duyệt, chấm tiến độ |
| **Dữ liệu cần nhìn** | Sprint Goal, board, work item age, DoD, blockers | Báo cáo nhân sự, deadline, số task |
| **Đầu ra** | Kế hoạch có thể hành động cho ngày tới | Bản cập nhật tình hình |
| **Rủi ro khi dùng sai** | Nếu không tập trung thì mất tính thực nghiệm | Nếu chiếm Daily Scrum thì tạo micromanagement |

### Ví dụ cùng một sự kiện, hai cách diễn đạt

**Cách báo cáo cá nhân:**

> “Hôm qua em viết hai unit tests. Hôm nay em sửa controller. Em không có blocker”.

**Cách hướng tới Sprint Goal:**

> “Mục tiêu Sprint yêu cầu học viên PENDING không mở được bài. API authorization chưa có test tích hợp, nên story chưa thể Done. Hôm nay em và một bạn tester sẽ tái hiện request trực tiếp; cần một Developer review policy trước khi merge”.

Phiên bản thứ hai **kết nối công việc với kết quả và nhu cầu phối hợp**. Nó không đòi hỏi mọi người phải nói nhiều hơn; nó cho thấy **hệ quả với kế hoạch chung**.

### Báo cáo không phải xấu, nhưng phải đúng nơi

Người quản lý có thể cần thông tin về ngân sách, ngày phát hành, phụ thuộc và rủi ro. Những thông tin đó nên đến từ **Sprint Backlog minh bạch, Increment, Sprint Review, báo cáo rủi ro và các cuộc trao đổi phù hợp**. Không nên buộc mỗi Developer **đọc lại lịch sử task** trước toàn nhóm để một người bên ngoài cập nhật spreadsheet.

## 4. Vì sao “ba câu hỏi” dễ biến thành điểm danh?

Cách hỏi:

1. Hôm qua tôi làm gì?
2. Hôm nay tôi làm gì?
3. Tôi có trở ngại gì?

có thể hữu ích nếu được dùng để **kết nối công việc với Sprint Goal và điều chỉnh kế hoạch**. Nhưng trong nhiều nhóm, nó trở thành **bộ câu hỏi hành chính**: từng người kể việc, các thành viên khác chờ đến lượt, không có quyết định chung.

### Bốn tín hiệu câu hỏi đã lệch mục đích

- Mọi người **nhìn người quản lý** khi trả lời, thay vì trao đổi với đồng đội.
- Sau mỗi lượt, người điều phối chỉ nói “OK, người tiếp theo”, dù vừa xuất hiện một blocker quan trọng.
- Những nhiệm vụ đang chờ review hoặc test **không có người tiếp sức**, vì ai cũng chỉ nói về task mình sở hữu.
- Cuộc họp kết thúc khi **đã điểm danh đủ người**, không phải khi đã thống nhất việc cần đổi để đạt Sprint Goal.

### Ba câu hỏi là công cụ, không phải tội lỗi

Không cần cấm hẳn cách hỏi này. Một nhóm mới có thể dùng nó để làm quen với việc nói rõ blocker. Điều cần bổ sung là:

> “Những thông tin vừa nghe **có ảnh hưởng gì tới Sprint Goal**? Chúng ta có cần **đổi kế hoạch hôm nay** không?”

Nếu câu hỏi sau cùng không được hỏi, Daily Scrum có thể chỉ còn là **những bài độc thoại nối tiếp**.

### Khi “không có blocker” không có nghĩa là dòng công việc trôi chảy

Một Developer có thể không bị chặn trên phần việc của mình, nhưng PBI chung đang chờ review của họ. Người ấy nói “không có blocker” vẫn có thể đúng ở cấp cá nhân, trong khi **Sprint Goal đang bị chặn ở cấp luồng**.

Hãy xem việc đang chờ, việc gần Done và phụ thuộc liên nhóm, không chỉ cảm nhận chủ quan của từng người.

## 5. Những nguyên nhân tổ chức khiến Daily Scrum thành họp báo cáo

Sai lệch hiếm khi chỉ đến từ “Scrum Master hỏi sai câu”. Nhiều khi nó phản ánh **cơ chế quản lý, văn hóa và thiếu minh bạch của hệ thống**.

| Nguyên nhân có thể | Biểu hiện | Cách xác minh |
| --- | --- | --- |
| **Không có Sprint Goal thực chất** | Buổi họp chỉ còn danh sách task riêng | Xem Sprint Goal có mô tả giá trị và được dùng để ra quyết định không |
| **Lãnh đạo cần báo cáo theo người** | Từng thành viên phải đọc task để được đánh giá | Kiểm tra chính sách đánh giá, biểu mẫu và quyền quản lý |
| **Board không phản ánh thực tế** | Người quản lý phải hỏi miệng vì trạng thái cũ | Đối chiếu ticket với PR, CI, blocker và DoD |
| **Scrum Master bị hiểu là project manager** | SM giao việc và hỏi “đã xong chưa?” | Xem accountability và cách phân quyền trong Scrum Team |
| **Không có an toàn tâm lý** | Người làm ngại báo sai sót, luôn nói “đang đúng kế hoạch” | Phỏng vấn, quan sát phản ứng khi có cảnh báo |
| **Nhiều WIP và việc cá nhân hóa** | Ai cũng bận nhưng PBI không về Done | Xem WIP, aging, review/test queues |
| **Thiếu quyền tự quản** | Developers không được đổi thứ tự hoặc phân công | Xác định ai thực sự quyết định cách đạt Sprint Goal |
| **Phụ thuộc ngoài nhóm** | Người làm chỉ báo “đang chờ” mỗi ngày | Xem owner, thời gian chờ và kênh escalation |
| **Lịch họp phục vụ sếp hơn nhóm** | Daily Scrum dời giờ theo lịch quản lý | Hỏi ai sử dụng đầu ra và ai có quyền thay đổi lịch |

### Chẩn đoán trước khi sửa nghi thức

Nếu quản lý yêu cầu báo cáo vì dashboard hiện tại không đáng tin, việc chỉ tuyên bố “quản lý không được dự” có thể khiến **thiếu minh bạch và mất niềm tin**. Giải pháp có thể gồm:

- Cập nhật board ngay khi trạng thái công việc thay đổi.
- Định nghĩa rõ trạng thái Review, Test, Done và availability.
- Có kênh trao đổi về rủi ro phù hợp với nhu cầu quản trị.
- Huấn luyện phân biệt trách nhiệm của Product Owner, Developers và Scrum Master.
- Trao quyền để Developers **thực sự điều chỉnh kế hoạch**, không chỉ trao quyền nói.

### Không đổ lỗi cho người ít phát biểu

Nếu một tester từ xa không dám nhắc lỗi quyền khi quản lý đang nghe, không nên kết luận họ “không chịu phát biểu”. Cần xem **điều gì xảy ra sau lần trước họ báo lỗi** và họ có con đường nêu vấn đề an toàn hay không.

## 6. Hậu quả đối với dòng giá trị và khả năng thích ứng

Một Daily Scrum biến thành báo cáo có thể tạo ra **cảm giác kiểm soát** mà không cải thiện việc giao Increment.

### 6.1. Chậm nhận biết lệch Sprint Goal

Mọi người báo “task của tôi đúng tiến độ”, trong khi một điều kiện chấp nhận quan trọng chưa có cách kiểm thử. Lệch mục tiêu được phát hiện quá muộn, khiến Sprint Review mới là lúc cả nhóm biết Increment chưa dùng được.

### 6.2. Tối ưu công việc cá nhân, không tối ưu kết quả chung

Một Developer mở thêm PBI vì “xong task của mình” dù hàng đợi review đầy. WIP tăng, thời gian chờ kéo dài, nhưng báo cáo hoạt động cá nhân vẫn đẹp.

### 6.3. Blocker biến thành thông tin thụ động

“Em đang chờ đội Identity” được lặp lại năm ngày liên tiếp. Nếu không ai quyết định **người liên hệ, thời điểm escalation, phương án tạm thời an toàn**, Daily Scrum chỉ ghi nhận việc chờ.

### 6.4. Giảm an toàn tâm lý

Khi người quản lý dùng lời báo cáo để phê bình công khai hoặc đánh giá năng suất, thành viên có thể tránh nói:

- “Tôi không hiểu quy tắc PENDING/ACTIVE”.
- “Tôi tạo ra lỗi rồi, cần người giúp xác minh”.
- “Sprint Goal đang có rủi ro”.
- “Kế hoạch ban đầu không còn phù hợp”.

Thiếu tín hiệu thật khiến Scrum mất khả năng **inspection và adaptation**.

### 6.5. Chất lượng bị đẩy về cuối

Nhóm kể nhiều task “code complete” nhưng không ưu tiên integration tests, DoD và review. Báo cáo phần trăm hoàn thành **che đi** khoảng cách từ code tới Increment có thể dùng.

### 6.6. Phản hồi đến muộn, rework tăng

Sai giả định nghiệp vụ hoặc contract API không được đưa ra để phối hợp sớm. Nhóm phát hiện ở cuối Sprint hoặc sau release, phải quay lại sửa những phần đã tưởng hoàn thành.

**Lưu ý:** Daily Scrum tốt không đảm bảo tự nó sẽ giảm lead time hay lỗi. Nó là **một cơ chế điều phối** cần kết hợp Product Backlog rõ, kỹ thuật chất lượng, quyền quyết định và phản hồi người dùng.

## 7. Tín hiệu quan sát trong một Daily Scrum thật

Đừng chỉ hỏi “nhóm có đang dùng ba câu hỏi không?”. Hãy quan sát **người nào đang nhận thông tin và cuộc họp tạo ra quyết định gì**.

| Tín hiệu | Daily Scrum bị kéo thành báo cáo | Daily Scrum đang phục vụ tự quản |
| --- | --- | --- |
| **Hướng nhìn** | Mọi người nhìn một người điều hành | Trao đổi với các Developers cần phối hợp |
| **Điểm bắt đầu** | “Đến lượt bạn A báo cáo” | “Sprint Goal đang ở trạng thái nào?” |
| **Đối tượng chú ý** | Task cá nhân và thời gian đã dùng | PBI, blocker, review/test, rủi ro đối với Done |
| **Cách nói về khó khăn** | “Em bị chặn, chờ chỉ đạo” | “Cần ai giúp và khi nào quyết định?” |
| **Kết thúc** | “Đã đủ người báo cáo” | “Kế hoạch hôm nay đã được điều chỉnh” |
| **Board** | Chỉ là ảnh nền hoặc công cụ quản lý người | Thể hiện công việc thực, WIP, age và phụ thuộc |
| **DoD** | Không xuất hiện trong thảo luận | Cản trở chất lượng được nhận diện và xử lý |
| **Hành vi của SM/PO** | Chấm điểm, giao task, đòi báo cáo | Hỗ trợ minh bạch, tháo trở ngại trong đúng phạm vi |

### Một câu kiểm tra ngắn sau cuộc họp

Hỏi một Developer:

> “Sau Daily Scrum, điều gì trong kế hoạch tiến tới Sprint Goal đã thay đổi so với trước buổi họp?”

Không bắt buộc mọi ngày phải đổi thứ tự task lớn. Đôi khi kế hoạch vẫn phù hợp. Nhưng nếu nhiều ngày liên tiếp **không ai biết kế hoạch chung là gì**, cần xem lại chất lượng cuộc họp.

### Không dùng checklist để xếp hạng người

Những tín hiệu này là căn cứ để cải tiến **cơ chế cộng tác**, không phải cơ sở chấm “Developer A đạt 8/10 điểm Daily Scrum”.

## 8. Phân biệt minh bạch hợp lệ với quản lý vi mô

Người quản lý không sai khi cần biết sản phẩm có đang đúng cam kết, có rủi ro hay chi phí đang vượt mức. Tình huống trở thành sai lầm khi **lấy Daily Scrum làm kênh thu báo cáo nhân sự**, khiến Developers không còn không gian ra quyết định.

### Những thông tin stakeholder có thể cần

- Sprint Goal và rủi ro có đạt được không.
- Increment nào đã thực sự đạt DoD và có thể dùng.
- Product Backlog thay đổi vì phản hồi nào.
- Có phụ thuộc, quyết định vượt quyền hoặc rủi ro phát hành nào cần hỗ trợ.
- Có guardrail bảo mật, dữ liệu, ngân sách hoặc chất lượng đang bị đe dọa không.
- Dự báo có điều kiện về thời điểm giao giá trị.

### Nên lấy thông tin từ đâu?

| Nhu cầu | Kênh có thể phù hợp | Vì sao |
| --- | --- | --- |
| Theo dõi Sprint Goal | Sprint Backlog/board, trao đổi với Scrum Team | Thấy kế hoạch và tiến triển chung |
| Xem Increment và điều chỉnh hướng sản phẩm | Sprint Review, Product Backlog | Kiểm tra kết quả và nhận phản hồi |
| Rủi ro cần quyết định ngay | Kênh escalation/incident và người có thẩm quyền | Không chờ đến Daily Scrum hay Sprint Review |
| Phụ thuộc liên nhóm kéo dài | Dependency/decision log, trao đổi giữa người có quyền xử lý | Có owner và mốc chốt |
| Năng lực, chi phí và thời hạn | Dự báo và báo cáo quản trị có ngữ cảnh | Không nhầm số task cá nhân với giá trị |
| Hiệu quả cách làm | Sprint Retrospective, flow/quality metrics | Tập trung cải tiến hệ thống |

### Có thể báo cáo riêng mà không tạo thêm gánh nặng lớn

Một dashboard đủ tin cậy hoặc bản tóm tắt rủi ro ngắn đôi khi thay được nhiều cuộc họp điểm danh. Nhưng **không nên tạo bộ giấy tờ song song** bắt Developers cập nhật cùng một dữ liệu ở ba nơi.

### Nếu có yêu cầu quản trị bắt buộc

Một số tổ chức cần báo cáo theo hợp đồng, bảo mật hoặc nghĩa vụ pháp lý. Nhóm nên **đáp ứng qua quy trình thích hợp**, phân định rõ đầu mối, dữ liệu cần thiết và quyền xem. Điều đó **không có nghĩa phải biến Daily Scrum thành buổi giao nộp báo cáo**.

## 9. Ai có trách nhiệm gì khi Daily Scrum lệch mục đích?

### Developers

Developers **chịu trách nhiệm tiến hành Daily Scrum**, kiểm tra tiến triển tới Sprint Goal và điều chỉnh Sprint Backlog. Họ cũng cần:

- Minh bạch về khó khăn, chất lượng và điều chưa chắc chắn.
- Đề nghị giúp nhau để đưa PBI về Done, không chỉ bảo vệ task cá nhân.
- Đưa ra kế hoạch có thể thực hiện cho thời gian làm việc tiếp theo.
- Điều chỉnh công việc khi xuất hiện thông tin mới và trao đổi phạm vi với Product Owner khi cần.

### Scrum Master

Scrum Master có accountability giúp Scrum Team và tổ chức hiểu, áp dụng Scrum hiệu quả. Khi Daily Scrum thành báo cáo, Scrum Master có thể:

- Giúp nhóm phân biệt mục đích sự kiện với cập nhật status.
- Huấn luyện Developers tự điều phối.
- Giúp lãnh đạo nhận báo cáo minh bạch qua kênh phù hợp.
- Hỗ trợ loại bỏ trở ngại vượt khả năng của Developers.
- Quan sát xu hướng WIP, chất lượng phản hồi và Retrospective để hỗ trợ cải tiến.

**Scrum Master không phải chủ tọa bắt buộc** và không có quyền tự biến Daily Scrum thành cuộc họp giao task. Scrum Master cũng không cần đọc “status của từng người” để có thể hỗ trợ nhóm.

### Product Owner

Product Owner chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog hiệu quả. PO có thể giúp Developers:

- Làm rõ Sprint Goal và mục tiêu giá trị.
- Xác nhận quy tắc nghiệp vụ, thứ tự backlog, trade-off phạm vi.
- Phản hồi nhanh nếu nhu cầu hoặc rủi ro thay đổi.

PO không cần dùng Daily Scrum để **phân việc hằng ngày** hoặc yêu cầu tất cả Developers báo từng hoạt động.

### Người quản lý và stakeholder

Người quản lý có thể:

- Làm rõ mục tiêu tổ chức, ngân sách và ràng buộc.
- Cung cấp năng lực và giúp xử lý phụ thuộc vượt quyền của team.
- Nhận thông tin rủi ro qua kênh phù hợp.
- Tránh dùng phát biểu tại Daily Scrum làm cơ sở công kích/xếp hạng cá nhân.

Nếu người quản lý muốn tăng khả năng dự đoán, cần làm rõ **mục tiêu, định nghĩa Done, flow và phụ thuộc**, không mặc định tăng tần suất truy vấn từng người sẽ làm delivery nhanh hơn.

### Một tình huống tinh tế

PO hoặc Scrum Master có thể đồng thời là Developer trong một Scrum Team nhỏ, khi họ **thực sự làm những PBI của Sprint Backlog**. Khi đó, họ có thể tham gia Daily Scrum **theo trách nhiệm Developers**, nhưng không nên dùng vai trò khác để đảo mục đích thành báo cáo.

## 10. Chuẩn bị trước Daily Scrum: dữ liệu phải giúp ra quyết định

Daily Scrum không cần 15 phút để **ngồi nhớ lại từng task** nếu Sprint Backlog không được cập nhật. Minh bạch công việc phải là hoạt động liên tục, không chỉ diễn ra vào giờ họp.

### Những gì nên có sẵn

| Dữ liệu | Câu hỏi nó hỗ trợ |
| --- | --- |
| **Sprint Goal ở nơi dễ thấy** | Tại sao các PBI này quan trọng? |
| **Sprint Backlog hiện hành** | Developers đã chọn kế hoạch nào, điều gì thay đổi? |
| **Trạng thái PBI và DoD** | Cái gì thật sự Done, cái gì mới code complete? |
| **Blocked flag + lý do** | Công việc nào đang chờ quyết định hay môi trường? |
| **PR/review/test/CI** | Công việc nào chưa thể tích hợp hoặc chưa đủ chất lượng? |
| **Work Item Age và WIP** | Có việc nào đang già, quá nhiều việc mở đồng thời? |
| **Phụ thuộc và owner** | Ai cần hỗ trợ, điều kiện nào nằm ngoài quyền team? |
| **Rủi ro cần xác minh** | Có chuyện gì có thể làm Sprint Goal không đạt? |

### Board không phải bảng thành tích cá nhân

Thẻ công việc nên phản ánh **trạng thái thật** của giá trị và chất lượng. Nếu story chưa đạt DoD vì thiếu API authorization test, không đánh Done chỉ vì người viết controller đã commit.

### Trạng thái phải có định nghĩa

Ví dụ:

~~~text
To Do: Chưa bắt đầu theo chính sách nhóm
In Progress: Đang thực hiện và còn trách nhiệm tạo Increment
Review: Thay đổi đủ điều kiện để người khác xem xét
Test/Integration: Đang kiểm chứng theo DoD
Blocked: Không tiến triển vì điều kiện cụ thể, có owner theo dõi
Done: Đã đạt Definition of Done hiện hành
~~~

Nếu board dùng trạng thái khác, không sao; điều quan trọng là **chính sách rõ và nhất quán**, không phải đủ năm cột.

### Dữ liệu tự động hóa nên hỗ trợ, không thay cuộc trao đổi

CI có thể tự báo pipeline đỏ, pull request có thể hiện thời gian chờ, nhưng Developers vẫn cần xác định **điều gì quan trọng nhất để giúp Sprint Goal**, không chỉ đọc từng dòng log.

## 11. Một cấu trúc Daily Scrum 15 phút tập trung vào Sprint Goal

Scrum Guide cho Developers **tự chọn cấu trúc**. Dưới đây là một phương án tham khảo khi nhóm đang bị kéo về status reporting.

| Khoảng minh họa | Câu hỏi | Kết quả cần có |
| --- | --- | --- |
| **Phút 0–2** | Sprint Goal là gì, còn cơ sở để đạt không? | Nhận biết hướng và rủi ro chung |
| **Phút 2–7** | PBI nào gần Done nhất; điều gì cản trở review/test/tích hợp? | Ưu tiên hoàn tất, tránh thêm WIP |
| **Phút 7–11** | Có blocker, phụ thuộc hoặc phát hiện mới nào ảnh hưởng kế hoạch? | Người theo dõi và bước xử lý cụ thể |
| **Phút 11–14** | Hôm nay cần điều chỉnh gì: phối hợp, kéo việc, thứ tự, kiểm chứng? | Kế hoạch hành động cho thời gian tới |
| **Phút 14–15** | Chủ đề sâu nào chuyển sang trao đổi ngay sau họp? | Người tham gia và mục tiêu follow-up |

Đây là **phân bổ thời gian tham khảo**, không phải cấu trúc bắt buộc. Nhóm có ba Developers có thể chỉ cần năm phút; nhóm nhiều phụ thuộc có thể dùng cấu trúc board-first khác mà vẫn ở trong 15 phút.

### Tránh biến thành buổi giải pháp kỹ thuật

Nếu một API cần 20 phút phân tích race condition, không bắt toàn nhóm ngồi nghe ngay trong timebox. Hãy:

1. Xác định **rủi ro với Sprint Goal**.
2. Chọn **người phối hợp** và thời điểm trao đổi tiếp.
3. Cập nhật **Sprint Backlog hoặc blocker** cho rõ.
4. Mời đúng người ở lại sau Daily Scrum để xử lý sâu.

### Không buộc cuộc họp phải có “nghi thức kết”

Không cần mọi người hô “Scrum!” hoặc nói một câu cam kết cá nhân. Kết thúc tốt khi cả nhóm **cùng hiểu kế hoạch và trách nhiệm hỗ trợ**, rồi quay lại delivery.

## 12. Đi theo công việc thay vì điểm danh từng người

Một cách thường hữu ích là **walk the board**: quan sát công việc từ phía gần hoàn tất trở ngược về phía mới bắt đầu, ưu tiên những hạng mục đang cản Sprint Goal.

### Ví dụ board Sprint

~~~text
SPRINT GOAL:
Học viên ACTIVE khóa tuyến tính có thể "Tiếp tục học" đúng bài,
đúng quyền và đạt DoD để thử trong cohort đã thống nhất.

DONE:
  ST-01: Quy tắc chọn bài tiếp theo (đã tích hợp và test)

TEST / INTEGRATION:
  ST-02: API quyền mở bài — thiếu kiểm thử PENDING gọi trực tiếp

REVIEW:
  ST-03: UI trạng thái hoàn tất — PR chờ review 2 ngày

IN PROGRESS:
  ST-04: Đồng bộ tiến độ phiên web — đang chờ quyết định conflict

TO DO:
  ST-05: Đo tỷ lệ học viên mở đúng bài theo cohort
~~~

Thay vì hỏi tuần tự “Hôm qua ai làm gì?”, Developers có thể bắt đầu:

> “ST-02 đang chặn một điều kiện DoD và liên quan quyền truy cập. Hôm nay ai có thể cùng tester xác minh request trực tiếp? ST-03 chờ review đã hai ngày; ai có thể nhận trước khi mở thêm ST-05?”

### Một vòng quan sát công việc hiệu quả

- **Done:** chỉ ghi nhận khi đạt chuẩn; không lặp báo cáo về việc đã xong.
- **Test/Review:** hỏi việc gì cần để hoàn tất và ai có thể hỗ trợ.
- **In Progress:** xem phụ thuộc, rủi ro và khả năng hoàn thành.
- **To Do:** chỉ kéo thêm nếu phục vụ Sprint Goal và **năng lực thực tế cho phép**.

Đây là một kỹ thuật có thể mượn từ tư duy flow/Kanban. Không có yêu cầu Scrum bắt buộc phải đi bảng từ phải sang trái.

### Khi board có nhiều thẻ

Không cần đọc hết mọi PBI. Ưu tiên **việc đe dọa Sprint Goal, lâu chưa tiến triển, đang gần Done hoặc có phụ thuộc cần xử lý ngay**.

## 13. Tập trung vào Sprint Goal thay vì hoàn thành càng nhiều task càng tốt

Một Sprint có thể có nhiều PBI nhưng cần một **Sprint Goal thống nhất**. Nếu mỗi người chỉ bảo vệ việc của mình, Daily Scrum không giúp lựa chọn khi năng lực có hạn.

### Ví dụ đánh đổi thực

Trong Sprint phát triển “Tiếp tục học”, Developers có ba lựa chọn cho ngày hôm nay:

1. Mở thêm story làm màu sắc nút mới vì dễ hoàn thành.
2. Cùng review và kiểm thử API phân quyền đang chặn Done.
3. Thử nghiên cứu hệ thống gợi ý AI cho quý sau.

Nếu **Sprint Goal phụ thuộc API phân quyền**, lựa chọn 2 có thể có giá trị cao nhất cho hôm nay, dù **số task cá nhân hoàn tất** ít hơn.

### Một Sprint Goal có thể làm rõ thứ tự quyết định

**Sprint Goal yếu:** “Hoàn thành 10 user stories”.

**Sprint Goal có hướng giá trị:** “Học viên đủ điều kiện có thể tiếp tục khóa tuyến tính từ bài tiếp theo một cách an toàn và kiểm chứng được”.

Với mục tiêu thứ hai, nhóm dễ hỏi **story nào cần hoàn tất để đạt giá trị**, chứ không chỉ ai còn task chưa tích.

### Sprint Goal không phải giấy phép bỏ DoD

Nếu “Tiếp tục học” mở được bài tiếp theo nhưng người PENDING cũng truy cập bài hạn chế, Increment chưa đáp ứng điều kiện an toàn. Developers không nên báo “đã đạt mục tiêu” dựa trên UI happy path. Cần **kiểm tra quyền ở backend, dữ liệu và acceptance criteria**.

### Nếu Sprint Goal không còn đạt được?

Daily Scrum là nơi phát hiện và minh bạch nguy cơ sớm. Developers trao đổi với Product Owner để **thương lượng phạm vi trong Sprint** mà không tự ý đổi giá trị chung. Nếu Sprint Goal trở nên lỗi thời, **Product Owner có quyền hủy Sprint** theo Scrum, nhưng đó không phải quyết định cá nhân của một Developer hoặc quản lý đứng nghe Daily Scrum.

## 14. Blocker cần hành động, không chỉ một dòng “đang chờ”

Blocker được ghi lại nhưng không có người xử lý sẽ trở thành **nợ điều phối**.

### Một mẫu blocker hữu ích

~~~text
PBI: ST-04 – Đồng bộ tiến độ đa phiên
Tác động: Không thể chứng minh điều kiện Done liên quan tiến độ nhất quán
Đang chờ: Team Learning xác nhận semantics khi hai thiết bị ghi xung đột
Người theo dõi: Developer A
Cần ai: Đại diện Learning và Product Owner nếu ảnh hưởng quy tắc nghiệp vụ
Việc tiếp theo: Gửi ví dụ request/response + câu hỏi cụ thể
Mốc cần trả lời: Trước lúc test tích hợp bắt đầu theo kế hoạch
Phương án trong quyền nhóm: Có thể hoàn tất lát online-only đã được xác nhận?
Escalation: Theo kênh phụ thuộc đã thống nhất nếu chờ vượt mốc
~~~

### Câu hỏi tốt khi gặp blocker

Không chỉ: “Em còn blocker không?”.

Hãy hỏi:

- **Điều gì đang bị chặn?** PBI, DoD, Sprint Goal hay một task phụ?
- **Nguyên nhân đã xác nhận hay chỉ là phỏng đoán?**
- **Chúng ta tự giải quyết được gì?**
- **Ai có quyền quyết định hoặc hỗ trợ?**
- **Nếu chưa có câu trả lời hôm nay, kế hoạch cần đổi thế nào?**

### Blocker ngoài nhóm không phải lỗi cá nhân

Một Developer không thể tự quyết định hợp đồng API của team khác. Đầu mối theo dõi cần **làm rõ yêu cầu, người quyết định và mốc hỗ trợ**, không phải hứa chắc mình sẽ sửa tất cả.

### Rủi ro khẩn không chờ Daily Scrum

Phát hiện API cho phép xem dữ liệu học viên khác? Dùng **quy trình bảo mật/incident ngay**, giảm tác động theo thẩm quyền, thông báo đúng người và kiểm chứng cách khắc phục. Không chờ tới 08:45 hôm sau để “báo blocker”.

## 15. Bảo vệ thời gian: 15 phút để điều phối, trao đổi sâu sau đó

Daily Scrum bị kéo dài đôi khi do mọi người giải quyết từng chi tiết kỹ thuật trước toàn nhóm. Cách xử lý không phải **cắt lời rủi ro quan trọng**, mà là phân định **quyết định điều phối** và **phân tích chuyên sâu**.

### Ví dụ

Developer A: “API từ chối PENDING nhưng khi hai request đến cùng lúc có thể tạo trạng thái ACTIVE sai”.

Đây là vấn đề nghiêm trọng. Daily Scrum cần nhanh chóng làm rõ:

- PBI nào chịu ảnh hưởng và có thể đạt DoD không?
- Ai sẽ tái hiện và xem thiết kế transaction?
- Có cần dừng merge/rollout hay kích hoạt xử lý rủi ro ngay?
- Điều gì cần cập nhật trên Sprint Backlog?

Sau đó, đúng những người liên quan trao đổi chi tiết concurrency và kiểm thử tích hợp. Không biến 15 phút thành buổi debug cho tất cả.

### “Parking lot” là công cụ giúp không bỏ quên

~~~text
FOLLOW-UP SAU DAILY SCRUM

09:05 – A + tester: tái hiện API PENDING/concurrency
09:20 – B + C: review PR ST-03
Trước 11:00 – D liên hệ Learning về contract tiến độ
Sau khi có kết quả – cập nhật Sprint Backlog và cảnh báo PO nếu phạm vi đổi
~~~

Thời điểm chỉ là **ví dụ**. Follow-up cần có **người và hành động**, không phải danh sách “để sau” rồi mất dấu.

### Không ép mọi vấn đề chỉ có thể bàn sau họp

Nếu một nguy cơ cần dừng release ngay, nhóm xử lý theo kênh khẩn. Timebox Daily Scrum **không có quyền ưu tiên cao hơn an toàn người dùng**.

## 16. Minh họa một Daily Scrum trước và sau khi chỉnh cách làm

### 16.1. Trước: 15 phút báo cáo cho trưởng nhóm

~~~text
Manager: Lần lượt mọi người báo hôm qua làm gì.
A: Em code controller, hôm nay code tiếp.
B: Em review một PR, chiều nay làm task mới.
Tester: Em chạy test, hiện không có gì thêm.
Manager: Còn lỗi quyền hôm qua thì ai chịu trách nhiệm?
A: Em đang xử lý ạ.
Manager: Nhớ xong trước thứ Sáu. Người tiếp theo.
...
Manager: Cảm ơn, đã đủ status.
~~~

Những điều cuộc họp này **không trả lời**:

- Lỗi quyền có làm Sprint Goal không thể đạt không?
- Cần dừng/giới hạn việc merge hay release gì?
- Tester cần ai giúp tái hiện?
- Nếu review đang chờ, có cần bớt WIP và hỗ trợ hoàn tất?
- Developers đã điều chỉnh Sprint Backlog hay chưa?

### 16.2. Sau: Developers kiểm tra tiến triển và tự phối hợp

~~~text
Developer A: Sprint Goal là "Tiếp tục học đúng quyền".
             ST-02 chưa Done vì test PENDING còn đỏ.

Tester: Tôi có request trực tiếp tái hiện được đường cấp nội dung.
        Hôm nay cần A cùng xác minh ở service và B xem policy.

Developer B: ST-03 đang chờ tôi review. Tôi sẽ hoàn thành review
             trước khi kéo PBI mới để không tăng WIP.

Developer C: ST-04 chờ Learning xác nhận contract.
             Tôi gửi hai ví dụ conflict và đề nghị trao đổi ngắn.

Developer A: Vậy kế hoạch hôm nay ưu tiên bảo vệ quyền,
             review ST-03 và theo dõi contract ST-04.
             Chúng ta cập nhật blocker, ai cần làm sâu ở lại sau họp.
~~~

Đây **không phải một kịch bản bắt buộc phải diễn**. Nó minh họa thay đổi về **trung tâm cuộc nói chuyện: từ báo cáo cá nhân sang kế hoạch chung**.

### 16.3. Đầu ra khác nhau thế nào?

| Trước | Sau |
| --- | --- |
| Ai cũng đã trả lời câu hỏi | Nhóm có ưu tiên hành động cùng nhau |
| Quản lý biết một vài task đang làm | Developers thấy rủi ro đối với Sprint Goal |
| Blocker được nhắc nhưng không xử lý | Blocker có owner, bước tiếp và mốc phản hồi |
| Chưa rõ ai hỗ trợ test/review | Có người phối hợp ngay sau sự kiện |
| DoD nằm ngoài cuộc họp | Chất lượng quyết định khả năng Done |

## 17. Tình huống thực tế: Daily Scrum phát hiện kế hoạch Sprint cần thay đổi

### 17.1. Bối cảnh

Scrum Team phát triển nền tảng học có Sprint Goal:

> “Đối với học viên có đăng ký ACTIVE của khóa tuyến tính, tính năng ‘Tiếp tục học’ mở đúng bài tiếp theo, kiểm tra quyền ở API và đạt DoD để dùng trong cohort thử”.

Sprint có bảy ngày làm việc còn lại. Các PBI:

| PBI | Giá trị | Trạng thái | Rủi ro |
| --- | --- | --- | --- |
| **ST-01** | Chọn bài tiếp theo từ tiến độ | Done | Không có rủi ro đã biết lớn |
| **ST-02** | API kiểm tra quyền trước khi cấp nội dung | Test/Integration | PENDING gọi trực tiếp vẫn lấy được nội dung |
| **ST-03** | UI hiển thị hoàn tất và điều hướng | Review | PR chờ hai ngày, có thể cần sửa theo API |
| **ST-04** | Đồng bộ tiến độ đa thiết bị | In Progress | Chờ hợp đồng conflict từ Learning |
| **ST-05** | Instrumentation đo outcome của cohort | To Do | Cần bảo vệ dữ liệu và định nghĩa event |

### 17.2. Daily Scrum kiểu báo cáo che điều gì?

A nói đã code gần xong. B nói PR “trên 80%”. Tester nói đã test UI. C nói đang chờ đội khác. Nếu không ai **liên kết các mảnh ấy với Sprint Goal**, nhóm có thể lầm rằng Sprint đang tiến rất tốt.

Trong thực tế:

- ST-02 **không thể Done** khi kiểm soát quyền còn sai.
- ST-03 có thể phát sinh rework nếu UI giả định quyền không đúng.
- ST-04 đang tiêu tốn WIP nhưng chưa có câu trả lời nghiệp vụ/contract.
- ST-05 chưa được làm, nhưng điều kiện đo outcome có thể cần chuẩn bị sớm để đánh giá pilot.

### 17.3. Cuộc kiểm tra theo Sprint Goal

Nhóm thảo luận ba câu hỏi:

1. **Điều gì đang cản Increment an toàn?** ST-02 là rủi ro ưu tiên.
2. **Điều gì cần thay đổi hôm nay?** Hai Developers hỗ trợ test/review ST-02, một Developer review ST-03, người còn lại liên hệ contract cho ST-04.
3. **Có cần PO xác nhận trade-off phạm vi không?** Nếu đồng bộ đa thiết bị chưa thể đạt DoD đúng thời điểm, PO và Developers cần trao đổi về lát giá trị khả thi mà vẫn giữ Sprint Goal và guardrails; không tự bỏ kiểm thử.

### 17.4. Sprint Backlog được thích ứng

~~~mermaid
flowchart TD
    A["Daily Scrum: xem Sprint Goal và DoD"] --> B{"Rủi ro quan trọng nhất?"}
    B -->|"API quyền chưa đúng"| C["Ưu tiên tái hiện, sửa và kiểm thử ST-02"]
    B -->|"PR bị chờ"| D["Ghép reviewer để hoàn tất ST-03"]
    B -->|"Contract chưa rõ"| E["Chốt owner, gửi ví dụ và mốc phản hồi ST-04"]
    C --> F["Cập nhật Sprint Backlog"]
    D --> F
    E --> F
    F --> G["Theo dõi DoD và tiến triển tới Sprint Goal"]
    G --> H{"Phạm vi cần thương lượng?"}
    H -->|"Có"| I["Trao đổi Product Owner, giữ guardrails"]
    H -->|"Không"| J["Tiếp tục kế hoạch điều chỉnh"]
~~~

### 17.5. Không được dùng Daily Scrum để hợp thức hóa lỗi quyền

Nếu nhóm đề xuất tắt kiểm tra quyền để có demo đẹp, quyết định ấy **vi phạm điều kiện an toàn** trong bối cảnh bài học. Không phải “vì Sprint Goal nên bỏ DoD”. Hãy thu hẹp phạm vi được phép, hoãn phần chưa an toàn hoặc sử dụng quy trình rủi ro phù hợp.

### 17.6. Hai ngày sau nên kiểm tra điều gì?

Không chỉ “A đã code thêm bao nhiêu”. Hãy xem:

- API từ chối PENDING ở tầng máy chủ qua test thực thi chưa?
- ST-03 có được review/tích hợp và đạt DoD chưa?
- Contract ST-04 có người xác nhận, hay vẫn bị treo?
- WIP có giảm, hay nhóm mở thêm story để tạo cảm giác bận rộn?
- Với những thay đổi đã được tích hợp, còn điều gì cản đạt Sprint Goal?

Daily Scrum **lặp lại mỗi ngày làm việc của Sprint** chính để phát hiện sự thay đổi và điều chỉnh kế hoạch sớm, không chỉ ghi nhận số task vừa đóng.

## 18. Work Item Age, WIP và Kanban bổ trợ Daily Scrum như thế nào?

Không cần biến Scrum thành Kanban thuần túy để sử dụng tư duy **flow**. Một Scrum Team có thể đưa các tín hiệu dòng công việc vào cách quan sát Sprint Backlog.

### Những tín hiệu nên hỏi

| Tín hiệu | Câu hỏi trong Daily Scrum | Hành động ứng viên |
| --- | --- | --- |
| **WIP cao** | Vì sao nhiều PBI đang mở mà ít PBI tới Done? | Giảm kéo việc mới, hỗ trợ hoàn tất |
| **Work Item Age tăng** | Item nào lâu không có thay đổi quan trọng? | Làm rõ blocker, giảm phụ thuộc |
| **Review queue lớn** | Ai có thể review trước khi mở task mới? | Swarm hoặc ưu tiên review |
| **Test queue lớn** | Có thiếu dữ liệu/môi trường/test năng lực? | Pairing, tự động hóa hoặc điều chỉnh cách kéo việc |
| **Blocked time cao** | Quyết định nào cần người ngoài team? | Escalation có owner và mốc |
| **CI đỏ liên tục** | Chất lượng đang chặn Increment nào? | Tập trung khôi phục phản hồi kỹ thuật |

### WIP limit không phải công thức tự động

Một nhóm có thể thử giới hạn hai PBI ở Review/Test, nhưng con số phải phù hợp với dòng công việc thực tế. Không có “WIP tối ưu cho mọi Scrum Team”. Mục tiêu là **giảm chia nhỏ chú ý và hoàn tất đúng chất lượng**, không biến WIP thành công cụ trách phạt.

### Work Item Age khác cycle time

- **Work Item Age:** thời gian một hạng mục **chưa hoàn tất** đã ở trong luồng theo điểm bắt đầu được định nghĩa.
- **Cycle time:** thời gian của hạng mục đã hoàn tất từ điểm bắt đầu tới điểm kết thúc theo chính sách.

Nếu chỉ nhìn cycle time của các story đã Done, item bị kẹt 12 ngày ở Review có thể **biến mất khỏi dashboard**. Daily Scrum cần thấy cả những thứ đang già.

### Không phải Daily Scrum phải tính phân vị hằng ngày

Median/P85 cycle time và SLE hữu ích để cải tiến xu hướng, nhưng không cần dùng 15 phút để đọc nhiều biểu đồ. Chỉ mang **tín hiệu liên quan tới kế hoạch hôm nay** vào Daily Scrum; phân tích sâu làm ở thời điểm phù hợp như Retrospective hoặc workshop flow.

## 19. DoD, XP và phản hồi kỹ thuật trong cuộc họp ngắn

Một dấu hiệu Daily Scrum thành báo cáo là nhóm nói nhiều về phần trăm code hoàn thành nhưng bỏ qua **Definition of Done**.

### Kết nối kỹ thuật với Increment

Với story phân quyền học:

- **Unit tests** xác minh quy tắc thuần của trạng thái và điều kiện.
- **API/security integration tests** xác minh người PENDING không xem được nội dung qua đường trực tiếp.
- **Contract tests** kiểm tra tương thích với các dịch vụ liên quan.
- **CI** cho tín hiệu sớm khi thay đổi làm sai hành vi.
- **Refactoring/TDD/pairing** giúp cải thiện an toàn thay đổi khi rủi ro và chi phí phù hợp.

Những thực hành này gắn với XP và continuous quality. Daily Scrum không phải nơi tranh luận hết chi tiết test, nhưng phải giúp Developers **nhận diện khi phản hồi kỹ thuật cho thấy kế hoạch không còn hợp lệ**.

### “Unit test xanh” chưa phải “Done”

Một API có unit tests xanh vẫn có thể cấp dữ liệu sai quyền vì thiếu kiểm tra ở tầng request hoặc transaction. Nếu DoD yêu cầu integration/security tests liên quan, PBI chưa Done khi thiếu chúng.

### Một mẫu báo rủi ro kỹ thuật hữu ích

~~~text
Mục tiêu ảnh hưởng:
  Đạt Increment "Tiếp tục học" đúng quyền.

Bằng chứng mới:
  API test cho request trực tiếp PENDING đang đỏ.

Tác động:
  ST-02 chưa đáp ứng DoD; release cohort không an toàn.

Kế hoạch cần điều chỉnh:
  Ưu tiên hai người cùng tái hiện/sửa/test;
  hoãn bắt đầu PBI ít liên quan tới Sprint Goal.

Phụ thuộc:
  Cần người nghiệp vụ xác nhận ngoại lệ nếu quy tắc mơ hồ.
~~~

Đây không phải báo cáo chi tiết mọi lần chạy test. Nó là **thông tin đủ để tự quản và bảo vệ giá trị**.

## 20. Daily Scrum với nhóm phân tán và nhiều múi giờ

Nhóm phân tán có thể gặp khó vì giờ làm ít chồng lấn và chat bất đồng bộ. Chỉ chuyển ba câu hỏi thành một bot điểm danh **không tự đảm bảo mục đích Daily Scrum**.

### Những điều cần bảo vệ

- Các Developers có **cách kiểm tra Sprint Goal và thích ứng kế hoạch cùng nhau**.
- Sprint Backlog, blocker và quyết định được cập nhật ở nơi cả nhóm truy cập.
- Người ở xa có kênh nêu rủi ro **trước khi quyết định khó đảo ngược được chốt**.
- Lịch đồng bộ không mặc định khiến một khu vực phải làm ngoài giờ liên tục.
- Các vấn đề khẩn có đường xử lý riêng, không phụ thuộc thời điểm Daily Scrum.

### Async có thể bổ trợ nhưng không nên tráo mục đích

Một cập nhật ngắn bất đồng bộ trước giờ đồng bộ giúp mọi người đọc ngữ cảnh, giảm thời gian kể task. Tuy nhiên, **chỉ gửi ba câu trả lời vào chat rồi không ai cùng kiểm tra hay điều chỉnh kế hoạch** là hoạt động cập nhật trạng thái, chưa tự chứng minh đã đạt mục đích Daily Scrum theo Scrum.

Nếu nhóm dùng Scrum, cần **bảo đảm Daily Scrum 15 phút theo nhịp và mục đích được Scrum Guide mô tả**, hoặc minh bạch rằng họ đang sử dụng một cách làm khác thay vì tuyên bố đúng Scrum vì có bot.

### Ví dụ phối hợp thực tế

~~~text
Trước Daily Scrum:
  Developers cập nhật board khi công việc thực sự thay đổi.
  Người khác múi giờ để lại blocker rõ tác động, owner và câu hỏi.

Trong Daily Scrum:
  Developers trong nhịp làm việc cùng kiểm tra Sprint Goal,
  chọn ưu tiên, người hỗ trợ và quyết định cần follow-up.

Sau Daily Scrum:
  Kết luận được ghi lên Sprint Backlog/decision log.
  Người không có mặt vì điều kiện hợp lệ theo kịp và phản hồi.
  Chủ đề cần chuyên gia được giải quyết trong cuộc trao đổi riêng.
~~~

### Đừng dùng camera làm bằng chứng đóng góp

Người không bật camera có thể đóng góp bằng test, bình luận PR và giải quyết blocker. Không nên xem thời gian online hay số tin nhắn là KPI đóng góp Daily Scrum. Điều quan trọng là **sự minh bạch, khả năng phối hợp và tiến triển tới mục tiêu**.

## 21. Khi một người quản lý yêu cầu mọi người báo cáo trong Daily Scrum

Đây là tình huống rất thực tế. Phản ứng “quản lý bị cấm dự” thường không giải quyết lý do họ cần thông tin. Cần **thương lượng mục đích và kênh minh bạch**.

### Cách trao đổi hướng giải pháp

~~~text
Chúng tôi hiểu anh/chị cần thấy tiến độ và rủi ro Sprint để
đưa quyết định đúng lúc.

Daily Scrum là 15 phút Developers kiểm tra Sprint Goal và
điều chỉnh Sprint Backlog, nên nếu dùng để từng người báo cáo,
chúng tôi sẽ mất cơ hội phối hợp và xử lý blocker ngay.

Đề xuất:
  - Sprint Goal, board, DoD và blocker luôn được cập nhật.
  - Những rủi ro vượt quyền được báo qua kênh escalation ngay.
  - Chúng tôi có thể cung cấp bản tóm tắt theo nhịp đã thống nhất,
    tập trung Increment, điều chưa chắc và quyết định cần hỗ trợ.
  - Sau một hoặc hai Sprint, cùng xem dữ liệu có đủ minh bạch không.
~~~

### Từ yêu cầu “ai làm gì” sang “công việc có tiến triển không”

| Câu hỏi quản lý thường đặt | Phiên bản giúp quyết định |
| --- | --- |
| “Hôm qua A làm mấy task?” | “PBI quan trọng nào đã tiến tới Done và còn chờ gì?” |
| “B có rảnh không?” | “Có chỗ nào cần tăng năng lực để giảm hàng đợi?” |
| “Tại sao C chưa xong?” | “Điều gì làm work item age tăng và ai có thể hỗ trợ?” |
| “Bao nhiêu phần trăm Sprint đã hoàn thành?” | “Sprint Goal đang được chứng minh bằng Increment và DoD ở mức nào?” |
| “Có chắc thứ Sáu xong không?” | “Có những giả định, phụ thuộc và rủi ro nào trong forecast?” |

### Khi quản lý là người giải quyết blocker thực

Nếu team cần quyền truy cập môi trường hoặc quyết định ngân sách nằm ở người quản lý, họ **có vai trò hỗ trợ thật**. Nhóm nên làm rõ blocker và yêu cầu cụ thể, có thể trao đổi ngay sau Daily Scrum hoặc qua kênh phù hợp. **Giúp tháo cản trở khác với bắt mọi Developer báo cáo cho người đó**.

## 22. Huấn luyện nhóm chuyển từ status meeting sang Daily Scrum có giá trị

Đổi câu hỏi trong một ngày có thể chưa đủ nếu văn hóa và quyền quyết định không thay đổi. Nên thử **một cải tiến nhỏ có mốc xem lại**.

### Một kế hoạch thử trong hai Sprint

| Bước | Hành động | Bằng chứng hoặc tín hiệu |
| --- | --- | --- |
| **Quan sát hiện trạng** | Xem vài Daily Scrum với mục đích kiểm tra cách làm, không đánh giá cá nhân | Cuộc họp có bao nhiêu quyết định điều chỉnh kế hoạch? |
| **Làm rõ Sprint Goal** | Hiển thị Goal và DoD trên board | Developers có thể diễn đạt mục tiêu và rủi ro |
| **Cập nhật Sprint Backlog liên tục** | Ghi blocked item, trạng thái review/test thật | Giảm việc đọc lại tình hình đã có trên bảng |
| **Thử walk the board** | Đi theo PBI gần Done và rủi ro lớn | Có sự phân công hỗ trợ và giảm việc chờ |
| **Tách follow-up** | Các chủ đề kỹ thuật sâu chuyển sau 15 phút | Không mất thông tin, timebox vẫn hữu ích |
| **Trao đổi với quản lý** | Tạo kênh báo cáo rủi ro/Increment phù hợp | Minh bạch tăng mà không chiếm Daily Scrum |
| **Retrospective kiểm tra** | Hỏi liệu Developers có tự chủ và giúp nhau tốt hơn | Quyết định giữ/điều chỉnh/dừng thử nghiệm |

### Đừng đặt KPI “mỗi Daily Scrum phải có ba quyết định”

Có ngày Sprint đang đi đúng kế hoạch và không cần điều chỉnh đáng kể. Ép mỗi buổi phải tạo một số lượng action cố định sẽ dẫn tới **hành động giả**. Chỉ cần **có khả năng kiểm tra và thích ứng khi thông tin đòi hỏi**.

### Một câu hỏi Retrospective hữu ích

> “Trong hai Sprint vừa rồi, có trở ngại nào Daily Scrum đã giúp chúng ta phát hiện và xử lý sớm? Có vấn đề nào được lặp lại trong báo cáo nhưng không hề dẫn tới quyết định?”

Đây là cách học dựa trên thực tế hơn khảo sát “mọi người có thích kiểu họp mới không?”.

### Ghi nhận hành vi lãnh đạo tích cực

Nếu quản lý giúp bỏ một cổng phê duyệt thừa, cấp môi trường test hoặc hỗ trợ người phụ trách API liên nhóm, hãy ghi rõ kết quả. Một thay đổi thành công không chỉ là **Developers nói với nhau**, mà còn là tổ chức giảm ma sát thật.

## 23. Đo Daily Scrum có giúp delivery không?

Không thể kết luận hiệu quả chỉ từ số phút họp hoặc độ hài lòng sau một tuần. Chọn **vài tín hiệu phản ánh mục tiêu và hậu quả**, tránh biến quan sát thành giám sát cá nhân.

### Ba loại bằng chứng

| Loại | Gợi ý theo dõi | Giới hạn |
| --- | --- | --- |
| **Thực hành cuộc họp** | Developers có bắt đầu từ Sprint Goal? Có kế hoạch hành động và owner cho blocker? | Không nên chấm điểm cứng hay đếm số câu phát biểu |
| **Flow và phối hợp** | Work Item Age, WIP, thời gian chờ review/test, số blocker kéo dài | Nhiều yếu tố khác Daily Scrum cũng ảnh hưởng |
| **Kết quả và chất lượng** | PBI đạt DoD, Increment, Sprint Goal, lỗi hồi quy, quyền và dữ liệu | Có thể chịu ảnh hưởng phạm vi, sự cố và nhu cầu biến động |

### Một ví dụ số liệu minh họa

Giả sử trước khi cải tiến, nhóm đo thời gian chờ review từ khi PR **Ready for Review** tới feedback đầu tiên có thể hành động trên **20 PR tiêu chuẩn**:

~~~text
Trước thử:
  Trung vị chờ review = 2,0 ngày lịch
  Số PR trong mẫu = 20

Sau thử walk-the-board + hỗ trợ review:
  Trung vị chờ review = 1,2 ngày lịch
  Số PR trong mẫu = 18

Chênh lệch trung vị = 2,0 - 1,2 = 0,8 ngày
Giảm tương đối = 0,8 / 2,0 × 100% = 40%
~~~

Đây là dữ liệu **hoàn toàn giả định**. Nó gợi ý hàng đợi có thể giảm, nhưng **không chứng minh** thay đổi Daily Scrum gây ra toàn bộ mức giảm: kích thước PR, lượng sự cố, số reviewer và độ khó có thể thay đổi.

### Không chỉ đo PR đã xong

Cần nhìn những PR chưa có feedback và **tuổi của chúng**. Nếu sau thử chỉ các PR dễ được review nhanh, còn PR khó chờ lâu hơn, trung vị các PR đã hoàn tất có thể tạo ấn tượng sai.

### Guardrails quan trọng

- Không tăng lỗi security/authorization.
- Không giảm DoD hoặc bỏ integration tests để tăng số Done.
- Không chuyển chờ từ Review sang Test/Release.
- Không ép mọi người online ngoài giờ để số liệu đẹp.
- Không dùng dữ liệu Daily Scrum để chấm năng suất từng người.

### Điều gì có thể kết luận?

Một câu phù hợp là: **“Sau khi làm rõ Sprint Goal và ưu tiên review ở Daily Scrum, thời gian chờ review của tập quan sát giảm; chúng tôi cần tiếp tục theo dõi tác dụng phụ và điều kiện tương đồng trước khi quy toàn bộ thay đổi cho một nguyên nhân”**.

## 24. Daily Scrum phối hợp với các Scrum events khác, không thay thế chúng

Một hiểu lầm dẫn tới status reporting là cố dùng Daily Scrum để xử lý **mọi thông tin quản trị và sản phẩm**.

### Sprint Planning

Scrum Team cùng xác định **tại sao Sprint có giá trị**, những PBI phù hợp và kế hoạch ban đầu. Nếu Sprint Goal mơ hồ, Daily Scrum khó có điểm tựa; việc chữa chỉ ở giờ họp hằng ngày là chưa đủ.

### Daily Scrum

Developers kiểm tra tiến triển tới Sprint Goal và điều chỉnh Sprint Backlog, tạo kế hoạch hành động phù hợp cho ngày tới.

### Sprint Review

Scrum Team và stakeholder kiểm tra **kết quả Sprint**, tình hình môi trường, thay đổi quan trọng và cùng xác định hướng điều chỉnh tiếp theo. Đây không phải cổng phê duyệt để hợp thức hóa Increment không đạt DoD.

### Sprint Retrospective

Scrum Team kiểm tra cách làm, con người, phối hợp, quy trình, công cụ và chất lượng để **đề xuất cải tiến hiệu quả**. Nếu Daily Scrum chỉ là điểm danh, Retrospective nên khám phá cơ chế tạo ra điều ấy và chọn một thay đổi nhỏ có owner.

### Product Backlog và Product Goal

Product Owner giữ trọng tâm giá trị. Khi Developers phát hiện Sprint Backlog cần thay đổi vì thông tin mới, **trao đổi với Product Owner khi ảnh hưởng phạm vi hoặc ưu tiên sản phẩm**; không biến Daily Scrum thành buổi tái ưu tiên toàn bộ Product Backlog theo một người bên ngoài.

### Sự kiện không thay thế công việc hằng ngày

Developers có thể phối hợp, ghép cặp, debug, code review và điều chỉnh kế hoạch ngoài Daily Scrum. **Scrum không cho phép chỉ giúp nhau trong 15 phút mỗi ngày**.

## 25. Những phản mẫu thường gặp và cách xử lý

| Phản mẫu | Tác hại | Thay đổi có thể thử |
| --- | --- | --- |
| **Scrum Master gọi tên và ghi task của từng người** | Cuộc họp lệ thuộc một người, không tự quản | Developers tự nhìn Sprint Goal và board |
| **Manager đòi báo cáo từng ngày** | Hướng chú ý lên cấp trên, tạo áp lực | Cung cấp minh bạch qua Sprint Backlog, risk reporting |
| **Đọc ba câu hỏi như một kịch bản bắt buộc** | Nhiều độc thoại, ít quyết định | Thêm câu hỏi về Sprint Goal và kế hoạch chung |
| **Không có Sprint Goal rõ** | Mỗi người tối ưu task của mình | Làm rõ Goal trong Sprint Planning và giữ dễ nhìn |
| **Mọi người chỉ nói “không blocker”** | Blocker cấp luồng bị che | Xem PBI già, review/test queue, phụ thuộc |
| **Daily Scrum kéo dài 45 phút để debug** | Tốn thời gian cả đội, mất timebox | Chọn người theo follow-up, trao đổi sâu riêng |
| **Không xử lý blocker lặp lại** | Cuộc họp ghi nhận mà không thích ứng | Gắn owner, mốc và escalation |
| **Story Done ngay khi code xong** | Che chất lượng, Increment chưa dùng được | Nhìn DoD và các tầng test bắt buộc |
| **Báo “80% hoàn thành” theo cảm giác** | Không thấy phần rủi ro còn lại | Xem acceptance criteria và Done thật |
| **Mở thêm việc để ai cũng bận** | WIP tăng, lead time dài | Ưu tiên hoàn tất trước khi bắt đầu |
| **PO giao task trong Daily Scrum** | Sai trọng tâm accountability, giảm tự quản | PO làm rõ mục tiêu/ưu tiên, Developers tự chọn cách |
| **Stakeholder đổi scope trực tiếp trong giờ họp** | Phá Sprint Goal và kế hoạch | Trao đổi theo Product Backlog/PO và Sprint Goal |
| **SM phải có mặt để cuộc họp được diễn ra** | Team phụ thuộc facilitator | Developers sở hữu sự kiện, SM hỗ trợ khi cần |
| **Cấm mọi người ngoài Developers nói trong mọi hoàn cảnh** | Có thể bỏ lỡ thông tin quan trọng | Giữ sự kiện phục vụ Developers, phối hợp theo bối cảnh |
| **Chỉ đo thời lượng cuộc họp** | Có thể họp ngắn nhưng vô ích | Xem kế hoạch, blocker, flow và chất lượng |
| **Chỉ đo số action sau cuộc họp** | Tạo hành động hình thức | Quan sát vấn đề thực được xử lý |
| **Biến Daily Scrum thành đánh giá nhân sự** | Mọi người giấu vấn đề và báo số đẹp | Tách báo cáo/đánh giá khỏi inspection–adaptation |
| **Bot ba câu hỏi được gọi là Scrum đầy đủ** | Không chắc có kiểm tra và điều chỉnh chung | Dùng async bổ trợ, bảo đảm mục đích Scrum |
| **Chờ Daily Scrum để báo lỗi nghiêm trọng** | Chậm giảm tác động người dùng | Kích hoạt incident/security workflow ngay |
| **Không ghi quyết định sau cuộc họp** | Người vắng mặt không theo kịp, blocker lặp lại | Cập nhật Sprint Backlog/decision log gọn |
| **Bỏ quality guardrails để kịp Sprint Goal** | Sai quyền, lỗi dữ liệu, tăng rework | Giữ DoD, thương lượng scope an toàn |
| **Họp đều nhưng backlog thiếu ưu tiên** | Daily Scrum không thể chữa vấn đề sản phẩm | PO làm rõ Product Goal và thứ tự backlog |

## 26. Bài thực hành: biến một Daily Scrum status thành phiên kiểm tra–thích ứng

### 26.1. Bối cảnh

Scrum Team có bảy Developers, một Product Owner và một Scrum Master. Sprint Goal là:

> “Học viên đã có quyền trong khóa tuyến tính có thể dùng ‘Tiếp tục học’ mở đúng bài, kể cả các trường hợp hoàn tất khóa, và không được mở bài khi đang chờ duyệt”.

Trong Daily Scrum hôm nay:

1. Developer A nói “controller xong 90%”, nhưng test quyền truy cập trực tiếp chưa được viết.
2. Developer B có pull request ở Review ba ngày, nhưng vẫn muốn mở story mới.
3. Tester C phát hiện người PENDING có thể lấy nội dung bài qua API.
4. Developer D đang chờ team Learning xác nhận cơ chế cập nhật tiến độ.
5. Product Owner muốn đưa chức năng AI gợi ý khóa vào Sprint ngay lập tức.
6. Người quản lý tham gia yêu cầu mỗi người báo số task hoàn thành và cam kết ngày xong.
7. Scrum Master dự định dùng toàn bộ 15 phút lần lượt gọi tên từng người.

### 26.2. Nhiệm vụ

1. Chỉ ra **ít nhất năm dấu hiệu** cuộc họp có nguy cơ lệch mục đích.
2. Giải thích **ai là người sử dụng Daily Scrum** và trách nhiệm điều phối thuộc về ai.
3. Viết **hai câu mở đầu** tập trung Sprint Goal thay vì điểm danh.
4. Sắp xếp thứ tự ba vấn đề cần làm rõ trong 15 phút, nêu lý do.
5. Đề xuất một **kế hoạch hành động cho ngày tiếp theo** với người phối hợp và việc follow-up.
6. Với lỗi PENDING, chỉ ra **cơ chế xử lý khẩn** và điều kiện không được đánh đổi.
7. Cho biết B có nên mở story mới khi PR chờ ba ngày hay không; cần thêm thông tin gì?
8. Khi PO đề nghị AI giữa Sprint, Developers nên phản hồi và phối hợp thế nào?
9. Đề xuất cách đáp ứng nhu cầu minh bạch của người quản lý **mà không biến Daily Scrum thành báo cáo**.
10. Viết một mẫu trao đổi ngắn trong Daily Scrum **không vượt mục đích 15 phút**.
11. Chọn **hai chỉ số flow/quality** để xem thử nghiệm cải tiến có ích.
12. Nếu sau hai Sprint cuộc họp ngắn hơn nhưng vẫn không có hành động nào giúp tháo blocker, bạn sẽ điều chỉnh gì?

### 26.3. Đáp án tham khảo – chẩn đoán

**Dấu hiệu nguy cơ:** báo phần trăm controller mà thiếu DoD; PR chờ lâu không được ưu tiên; test quyền phát hiện rủi ro nhưng không được nêu như vấn đề Sprint Goal; phụ thuộc không có bước escalation; PO có thể làm lệch trọng tâm Sprint; quản lý đòi status cá nhân; Scrum Master định dùng toàn thời gian để điểm danh.

**Mục đích và sở hữu:** Developers kiểm tra tiến triển tới Sprint Goal và điều chỉnh Sprint Backlog. Scrum Master hỗ trợ Scrum được hiểu và vận hành hiệu quả, không phải chủ tọa bắt buộc hoặc người nhận status. PO tham gia làm rõ giá trị và phạm vi khi cần, không giao việc chi tiết trong Daily Scrum.

**Hai câu mở đầu:**

> “Mục tiêu Sprint là tiếp tục học đúng quyền. Những PBI nào hiện ngăn chúng ta tạo Increment đáp ứng DoD?”
>
> “Có thông tin nào mới từ test, review hoặc phụ thuộc khiến kế hoạch hôm nay cần thay đổi?”

### 26.4. Đáp án tham khảo – ưu tiên

1. **Lỗi API cấp nội dung cho PENDING:** rủi ro quyền truy cập, cần ứng phó theo chính sách ngay khi phát hiện và bảo vệ DoD.
2. **PR Review ba ngày:** có thể là chỗ nghẽn làm PBI không tới Done; hỏi người hỗ trợ và nguyên nhân.
3. **Phụ thuộc contract của Learning:** ghi câu hỏi rõ, đầu mối và thời điểm cần quyết định; kiểm tra tác động lên Sprint Goal.

Đây là thứ tự tham khảo. Nếu tình huống quyền trái phép đang ảnh hưởng production, **việc giảm tác động có ưu tiên ngay** và không cần đợi đủ 15 phút để quyết định.

**Không tự động kéo thêm story mới** khi Review đang nghẽn. B cần xem PR thuộc PBI quan trọng nào, khả năng giúp review/test, WIP thực và nhu cầu của Sprint Goal. Nếu có lý do hợp lý để mở việc mới, nhóm có thể quyết định minh bạch; WIP limit không phải luật mù quáng.

### 26.5. Đáp án tham khảo – kế hoạch

~~~text
Mục tiêu: "Tiếp tục học" đúng quyền, đáp ứng DoD

Ngay khi phát hiện vấn đề:
  - Tester C và Developer A phối hợp tái hiện API PENDING.
  - Dùng quy trình sự cố/bảo mật nếu có nguy cơ ảnh hưởng thực.
  - Không gọi story Done hoặc release khi điều kiện quyền chưa đạt.

Trong ngày:
  - Developer B ưu tiên review PR đang chờ với một đồng đội phù hợp.
  - Developer D gửi ví dụ contract cho Learning, có mốc phản hồi.
  - Team cập nhật Sprint Backlog, blocked flag và kế hoạch.

Sau Daily Scrum:
  - A + C phân tích nguyên nhân kỹ thuật và bổ sung integration tests.
  - PO và Developers trao đổi riêng về đề nghị AI,
    ảnh hưởng tới Sprint Goal và Product Backlog.
  - Người cần hỗ trợ ngoài nhóm được thông báo theo kênh escalation.
~~~

### 26.6. Đáp án tham khảo – minh bạch và đo lường

**Người quản lý:** nhận Sprint Goal, Increment đã đạt DoD, board có trạng thái thật, blocker vượt quyền, forecast có điều kiện và rủi ro phát hành. Nếu cần báo cáo riêng theo yêu cầu tổ chức, tạo kênh phù hợp, **không buộc từng Developer đọc task trong Daily Scrum**.

**Chỉ số ứng viên:** trung vị/P85 thời gian chờ Review (có định nghĩa mốc), Work Item Age của các PBI chưa xong, số lỗi quyền ở các môi trường phù hợp, tỷ lệ PBI đạt DoD. Không suy nhân quả chỉ từ một con số; xem cả WIP và guardrails.

**Nếu họp ngắn mà không giúp tháo blocker:** xem lại Sprint Goal có rõ không, board có đúng trạng thái không, Developers có quyền điều chỉnh không, ai quyết phụ thuộc ngoài nhóm, người quản lý có còn kiểm soát chi tiết không. Có thể thử **walk the board và owner cho blocker**, rồi kiểm tra lại trong Retrospective. Rút ngắn họp **không phải mục tiêu cuối cùng**.

### 26.7. Ví dụ hội thoại cải tiến

~~~text
Developer A: Sprint Goal đang bị đe dọa vì API PENDING chưa đạt DoD.
Tester C: Tôi có test tái hiện request trực tiếp. A cùng tôi xử lý ngay.
Developer B: Tôi ưu tiên PR đang Review, không mở thêm story trước.
Developer D: Tôi liên hệ Learning về contract, có mốc cần trả lời.
Developer A: Cập nhật Sprint Backlog theo các việc này.
             Ai cần phân tích sâu sẽ ở lại sau Daily Scrum.
~~~

Cuộc nói chuyện ngắn có tác dụng vì **dẫn tới thay đổi trong kế hoạch**, không phải vì câu chữ đẹp hoặc đúng đủ ba câu hỏi.

## 27. Mẫu hướng dẫn dùng ngay cho Developers

Một nhóm đang có thói quen báo cáo có thể đặt mẫu sau cạnh Sprint Backlog, tự điều chỉnh sau vài Sprint.

~~~text
DAILY SCRUM – GỢI Ý KHỞI ĐẦU (15 phút tối đa)

1. Sprint Goal là gì? Chúng ta đang tiến gần hay rời xa mục tiêu?
2. PBI nào gần Done nhất? Chúng ta cần hỗ trợ gì để hoàn tất đúng DoD?
3. Có rủi ro mới từ test, review, CI, dữ liệu hoặc người dùng không?
4. Work item nào bị chặn hoặc già nhất? Ai có thể giúp ngay?
5. Hôm nay nên dừng, bắt đầu, phối hợp hoặc đổi thứ tự việc gì?
6. Chủ đề sâu nào cần follow-up với đúng người sau cuộc họp?

KẾT THÚC KHI:
  - Developers hiểu kế hoạch hành động cho ngày làm việc tiếp theo.
  - Sprint Backlog và blocker được cập nhật theo thực tế.
  - Những vấn đề khẩn được chuyển đúng kênh ngay.
  - Không có task nào bị coi Done khi chưa đạt DoD.

KHÔNG DÙNG ĐỂ:
  - Chấm năng suất của từng cá nhân.
  - Xin quản lý giao việc từng giờ.
  - Debug mọi chi tiết trước toàn nhóm.
  - Thay Sprint Planning, Review, Retrospective hoặc incident process.
~~~

### Có thể bắt đầu theo nhiều cách

Một ngày nhóm có thể hỏi **“Sprint Goal đang có rủi ro gì?”**. Ngày khác có thể mở board và xem những PBI đang chờ review. Một nhóm nhỏ có thể dùng ba câu hỏi nếu kết quả vẫn là kế hoạch chung. **Cấu trúc cần phục vụ mục đích, không phải trở thành nghi lễ mới**.

## 28. Checklist: Daily Scrum còn là kiểm tra–thích ứng hay đã thành báo cáo?

- [ ] Sprint Goal có được nhắc tới khi **cần ra quyết định**, không chỉ treo làm khẩu hiệu?
- [ ] Developers có thực sự **sở hữu Daily Scrum** và cách tiến hành?
- [ ] Mọi người nói với nhau về công việc chung, không chỉ trả lời một người quản lý?
- [ ] Câu hỏi chính là **kế hoạch cần điều chỉnh gì** để đạt Sprint Goal?
- [ ] Daily Scrum được giữ trong **timebox 15 phút**, không yêu cầu phải đủ 15 phút?
- [ ] Ba câu hỏi truyền thống chỉ được dùng như **một tùy chọn**, không là nghĩa vụ máy móc?
- [ ] Có nhìn thấy PBI gần Done, review/test, CI và phụ thuộc thật?
- [ ] Một story chưa đạt DoD **không bị báo Done** vì phần coding đã xong?
- [ ] Blocker có tác động, owner, bước tiếp và mốc phản hồi rõ?
- [ ] Vấn đề kỹ thuật cần phân tích sâu được **theo dõi sau sự kiện** với đúng người?
- [ ] Rủi ro bảo mật/dữ liệu nghiêm trọng được **báo ngay**, không chờ giờ Daily Scrum?
- [ ] Developers có quyền tự phối hợp, đổi thứ tự và điều chỉnh Sprint Backlog trong phạm vi?
- [ ] Khi phạm vi ảnh hưởng mục tiêu hoặc Product Backlog, có trao đổi với Product Owner đúng trách nhiệm?
- [ ] Scrum Master hỗ trợ hiệu quả Scrum, không biến Daily Scrum thành điểm danh?
- [ ] Người quản lý có **kênh minh bạch phù hợp** mà không làm lệch mục đích sự kiện?
- [ ] Có tránh dùng lời báo cáo hoặc số task để **đánh giá năng suất cá nhân**?
- [ ] Những người ở xa có quyền truy cập thông tin và kênh phản hồi có tác dụng?
- [ ] Không mặc định camera, số tin nhắn hay thời gian online phản ánh đóng góp?
- [ ] Work Item Age và WIP có được xem khi có việc chờ lâu hoặc quá nhiều việc mở?
- [ ] Có ưu tiên **hoàn tất giá trị** trước khi mở thêm việc để ai cũng bận?
- [ ] Khi CI/test báo lỗi, kế hoạch có điều chỉnh để **bảo vệ chất lượng và quyền**?
- [ ] Daily Scrum có giúp phát hiện lệch Sprint Goal **sớm hơn cuối Sprint**?
- [ ] Sprint Review kiểm tra Increment và phản hồi, không biến thành cuộc báo cáo cá nhân khác?
- [ ] Retrospective xem hành động cải tiến **có được thực hiện và tạo tác dụng** hay chưa?
- [ ] Có theo dõi flow/outcome/quality mà không dùng chỉ số để gây áp lực làm số đẹp?
- [ ] Nếu Daily Scrum chưa có ích, nhóm có thể **thử cách khác và đánh giá bằng bằng chứng**?

**Ghi nhớ:** Daily Scrum **không phải cuộc họp báo cáo cá nhân cho người quản lý**. Đây là sự kiện ngắn để **Developers kiểm tra tiến triển tới Sprint Goal và thích ứng Sprint Backlog**, từ đó có kế hoạch hành động cho ngày làm việc tiếp theo. Ba câu hỏi, bảng Kanban, báo cáo status hay công cụ họp từ xa chỉ là phương tiện. Khi nhóm tập trung vào **Increment đạt DoD, phối hợp tháo blocker, giảm WIP, phản hồi kỹ thuật sớm và mục tiêu chung**, Daily Scrum mới hỗ trợ các giá trị Agile: minh bạch, học hỏi, giao giá trị tăng dần và cải tiến liên tục.
