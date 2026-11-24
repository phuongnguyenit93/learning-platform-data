# Phân biệt bảng Kanban với một hệ thống quản lý dòng công việc

Một nhóm phần mềm tạo ba cột **To do – Doing – Done**, đưa mọi công việc lên thẻ, kéo thẻ qua các cột mỗi ngày và gọi đó là “đã áp dụng Kanban”. Sau vài tuần, nhóm vẫn bắt đầu quá nhiều việc, các thẻ bị chặn chờ kiểm thử, những yêu cầu khẩn chen ngang liên tục và không ai biết khi nào một yêu cầu sẽ hoàn thành. Bảng có thể rất đẹp, nhưng cách công việc đi từ nhu cầu đến giá trị chưa thay đổi.

**Bảng Kanban là công cụ trực quan hóa; hệ thống quản lý dòng công việc theo Kanban là tập hợp các quy tắc, cách điều hành và vòng phản hồi để công việc chảy qua một quy trình được định nghĩa, đo lường và cải tiến.** Bảng là một phần quan trọng của hệ thống, nhưng không thay thế giới hạn công việc đang thực hiện (WIP), chính sách kéo việc, tiêu chí hoàn tất, kỳ vọng thời gian phục vụ, các số đo và quyết định cải tiến.

Bài thuộc chương **Kanban** của module **AGILE_DEVELOPMENT**. Hiểu sự khác biệt này giúp nhóm thực hành đúng tinh thần Agile: hợp tác theo nhu cầu thực tế, nhận phản hồi sớm, giao phần mềm tăng dần và liên tục điều chỉnh cách làm. Những nguyên tắc cũng có thể hỗ trợ nhóm đang dùng **Scrum, user story, Product Backlog và kỹ thuật của Extreme Programming (XP)**, miễn giữ rõ mục tiêu và trách nhiệm của từng cách tiếp cận.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **một bảng có thẻ và cột chưa đủ để tạo thành hệ thống Kanban hiệu quả**.
2. Phân biệt các khái niệm **Kanban board, workflow, Definition of Workflow (DoW), WIP, pull, chính sách rõ ràng và Service Level Expectation (SLE)**.
3. Mô tả và trực quan hóa các trạng thái, hàng đợi, điểm bắt đầu/kết thúc và đường đi của một work item.
4. Thiết kế giới hạn WIP và quy tắc kéo việc thay vì liên tục giao thêm công việc cho người đang bận.
5. Đọc **WIP, throughput, cycle time, work item age** để nhận diện điểm nghẽn và đánh giá cải tiến.
6. Lựa chọn vòng phản hồi để quản lý luồng công việc, xử lý ngoại lệ và nâng chất lượng giao hàng.
7. Áp dụng một lộ trình thực hành từ “chỉ có bảng” đến **hệ thống điều hành dựa trên dòng chảy**, có ví dụ và bài tập tự kiểm tra.

## 2. Hai thứ thường bị gọi chung là “Kanban”

Từ “Kanban” xuất hiện trong nhiều bối cảnh, dễ gây nhầm giữa **tấm bảng** và **phương pháp quản lý**.

| Góc nhìn | Bảng Kanban | Hệ thống quản lý dòng công việc theo Kanban |
| --- | --- | --- |
| **Bản chất** | Một cách **hiển thị** công việc và trạng thái | Một cơ chế **định nghĩa, kiểm soát, đo lường và cải tiến** cách công việc tạo ra giá trị |
| **Thành phần** | Cột, thẻ, nhãn, swimlane, chỉ báo blocked | Workflow và ranh giới đo, chính sách di chuyển, kiểm soát WIP, SLE, số liệu flow, các vòng phản hồi và quyết định |
| **Câu hỏi chính** | “Việc nào đang ở đâu?” | “Việc đi đến Done nhanh, ổn định, an toàn và phù hợp nhu cầu đến mức nào?” |
| **Khi phát sinh tắc nghẽn** | Nhìn thấy nhiều thẻ ở cột Review | Xác định tuổi việc, nguyên nhân chờ, WIP, quy tắc hỗ trợ và thử thay đổi hệ thống |
| **Khi có việc mới** | Tạo thẻ và đẩy ngay vào Doing | Áp chính sách ưu tiên/bổ sung; chỉ kéo việc khi có năng lực và điều kiện phù hợp |
| **Đánh giá hiệu quả** | Số thẻ hoặc hình dạng bảng | Kết quả thực tế, thời gian hoàn tất, khả năng dự báo, chất lượng, công việc đang dở |
| **Thay đổi cách làm** | Thêm hoặc đổi tên cột | Thử chính sách dòng chảy, năng lực, WIP hoặc cách xử lý phụ thuộc; đo trước/sau |

Một bảng có thể hỗ trợ nhiều cách quản lý công việc khác nhau. Một tổ chức sử dụng bảng Trello, Jira hay bảng giấy **không tự động áp dụng Kanban đầy đủ**. Ngược lại, một hệ thống Kanban không nhất thiết phải dùng công cụ số phức tạp: bảng vật lý với quy tắc và số liệu rõ ràng vẫn có thể hữu ích.

### “Kanban” có một cách diễn đạt duy nhất không?

Có những tài liệu phổ biến về **Kanban Method** mô tả sáu thực hành như trực quan hóa, giới hạn WIP, quản lý flow, làm chính sách rõ ràng, thiết lập vòng phản hồi và cùng cải tiến theo thực nghiệm. **The Kanban Guide** diễn đạt Kanban dưới ba nhóm thực hành: **định nghĩa và trực quan hóa workflow, chủ động quản lý các item trong workflow, cải tiến workflow**. Hai cách tổ chức kiến thức có nhiều điểm tương thích, nhưng không nên lẫn danh sách từ các nguồn rồi trình bày như một bộ quy tắc duy nhất bắt buộc.

Bài này sử dụng **Definition of Workflow (DoW)** theo The Kanban Guide làm khung thực hành, đồng thời nhắc tới các kỹ thuật quản lý luồng thường thấy trong Kanban Method.

## 3. Bảng Kanban làm được gì — và không tự làm được gì?

Một bảng trực quan tốt giúp mọi người cùng nhìn thấy hệ thống công việc ở một thời điểm:

~~~text
                       BẢNG HIỂN THỊ CÔNG VIỆC
┌────────────┬──────────────┬──────────────┬─────────────┐
│   Ready    │  Developing  │ Review/Test  │    Done     │
├────────────┼──────────────┼──────────────┼─────────────┤
│ Story C    │ Story A      │ Story B      │ Story X     │
│ Bug D      │ Bug E ⚠     │ Story F      │ Bug Y       │
│ Story G    │ Story H      │              │             │
└────────────┴──────────────┴──────────────┴─────────────┘

⚠ = công việc bị chặn, cần ghi lý do và người hỗ trợ
~~~

Từ bảng trên, nhóm biết có ba item trong Developing và hai item trong Review/Test. Nhưng bảng **chưa tự trả lời**:

- Có được nhận thêm item vào Developing khi cột này đang có ba item không?
- Điều kiện nào cho phép chuyển từ Developing sang Review/Test?
- Review/Test đang có sức chứa bao nhiêu; nếu đầy, Developers nên làm gì?
- Work item nào đang chờ quá lâu so với kỳ vọng?
- Từ khi bắt đầu đến Done, nhóm mất bao nhiêu ngày, và có thể dự báo thế nào?
- Một lỗi nghiêm trọng có được đi theo luồng riêng không? Ai quyết định?
- Nếu một item bị chặn, nó có còn tính vào WIP không?
- “Done” nghĩa là đã viết mã, đã kiểm thử hay đã triển khai tới người dùng?

Những câu hỏi đó cần **quy ước vận hành**. Bảng chỉ cho phép nhìn thấy vấn đề; thay đổi hệ thống đòi hỏi chính sách, trách nhiệm, thông tin đo lường và hành động có kiểm chứng.

### Một bảng đơn giản có thể vẫn là bước khởi đầu tốt

Không cần đợi có dashboard hoàn hảo mới bắt đầu. Nhóm có thể vẽ bảng để **nhìn thấy công việc hiện tại như nó thực sự diễn ra**, rồi dần làm rõ ranh giới, chính sách và dòng chảy. Sai lầm không nằm ở bảng đơn giản, mà ở kết luận **“đã có bảng nên không cần thay đổi cách quản lý nữa”**.

## 4. Hệ thống Kanban cần một Definition of Workflow (DoW)

The Kanban Guide mô tả **Definition of Workflow** như hiểu biết được các thành viên Kanban system tạo ra về cách công việc chảy qua hệ thống. Có sáu nội dung quan trọng:

| Thành phần DoW | Câu hỏi phải làm rõ | Ví dụ với nền tảng học trực tuyến |
| --- | --- | --- |
| **1. Đơn vị giá trị / work item** | Chúng ta đang theo dõi loại công việc nào? | User story tạo trải nghiệm học viên, lỗi production, thay đổi vận hành đủ nhỏ |
| **2. Điểm bắt đầu và kết thúc** | Khi nào một item được tính đã bắt đầu? Khi nào tính đã hoàn tất? | Bắt đầu khi Developers kéo việc vào Doing; kết thúc khi đạt tiêu chuẩn Done và sẵn sàng bàn giao/đã phát hành theo phạm vi đo |
| **3. Các trạng thái trong workflow** | Từ bắt đầu đến hoàn tất, item đi qua những bước nào? | Developing → Review/Test → Ready to Release → Done |
| **4. Cách kiểm soát WIP** | Làm sao giới hạn hoặc quản lý số item đã bắt đầu nhưng chưa hoàn tất? | Giới hạn 3 item ở Developing và 2 ở Review/Test; ngoại lệ phải theo chính sách rõ |
| **5. Chính sách rõ cho luồng di chuyển** | Khi nào item được kéo, chuyển trạng thái, đánh dấu blocked hoặc được ưu tiên? | Chỉ chuyển sang Review khi đã tích hợp và kiểm thử mức tối thiểu; blocked có lý do |
| **6. Service Level Expectation (SLE)** | Với loại việc này, kỳ vọng mất bao lâu từ bắt đầu đến hoàn tất, với mức xác suất/kỳ vọng phù hợp? | Dựa trên lịch sử: khoảng 85% item loại chuẩn hoàn tất trong không quá 10 ngày làm việc |

**DoW không đơn giản là sơ đồ cột.** Cần định nghĩa đủ để các thành viên có cùng cách hiểu và có thể **đo, quản lý, cải tiến** luồng công việc thực.

Không có quy tắc rằng mọi tổ chức phải dùng đúng tên cột, một WIP limit chuẩn hoặc một SLE mặc định. DoW được xác định theo loại dịch vụ, rủi ro, chính sách chất lượng và bối cảnh nhóm, sau đó điều chỉnh theo bằng chứng.

## 5. Thành phần thứ nhất: xác định work item có ý nghĩa

Một tấm thẻ cần đại diện cho **đơn vị công việc mà hệ thống đang quản lý**, không nhất thiết luôn là user story. Có thể là yêu cầu khách hàng, lỗi nghiêm trọng, thay đổi kỹ thuật có kết quả độc lập hoặc một đơn vị công việc vận hành.

### Ví dụ chọn đơn vị giá trị

| Loại thẻ | Khi hữu ích | Cạm bẫy |
| --- | --- | --- |
| **User story dọc** | Theo dõi luồng hành vi như “Học viên mở lại đúng bài đang dở” từ bắt đầu đến Done | Chia một user story thành API/UI/database rồi đếm như ba kết quả người dùng độc lập |
| **Bug cần khắc phục** | Theo dõi lỗi với tác động, điều kiện tái hiện và tiêu chí xác nhận | Chỉ “đóng ticket” khi có sửa mã, chưa kiểm thử lỗi tái xuất |
| **Thay đổi hạ tầng/vận hành** | Theo dõi cấp môi trường, giảm sự cố, cải thiện pipeline có kết quả rõ | Không định nghĩa lúc nào dịch vụ/đầu ra thực sự hoàn tất |
| **Yêu cầu hỗ trợ** | Dùng trong hệ thống phục vụ người dùng có luồng yêu cầu liên tục | Trộn các yêu cầu vài phút với các thay đổi kéo dài nhiều tuần mà không phân loại |

Nếu kích thước item khác nhau quá nhiều, throughput theo **số thẻ** có thể dễ hiểu sai. Ví dụ, chia cùng một tính năng từ 2 story thành 12 ticket kỹ thuật có thể khiến throughput tăng, dù thời gian đưa giá trị tới người dùng không thay đổi.

**Đơn vị giá trị phải thống nhất với mục tiêu đo.** Khi cần dự báo một yêu cầu khách hàng, hãy theo dõi đơn vị mà khách hàng nhận kết quả; khi cần cải thiện vận hành, có thể dùng loại item riêng và nhìn rõ mối liên hệ với kết quả dịch vụ.

### Chính sách cho kích thước item

Nhóm có thể thống nhất:

- Item quá lớn nên được chia theo **luồng người dùng, quy tắc nghiệp vụ hoặc rủi ro**.
- Một item đưa vào Doing phải có kết quả và điều kiện Done có thể kiểm tra.
- Việc kỹ thuật bên trong một story có thể theo task phụ, nhưng cần phân biệt với work item dùng để đo throughput của dịch vụ.
- Khi thay đổi cách chia item, chú thích dữ liệu cũ và mới để tránh so sánh không đồng dạng.

## 6. Thành phần thứ hai: làm rõ điểm bắt đầu, điểm kết thúc và các trạng thái

Giả sử workflow được mô tả:

~~~mermaid
flowchart LR
    A["Ideas / Requests<br/>chưa bắt đầu"] --> B["Ready<br/>hàng đợi đầu vào"]
    B --> C["Developing<br/>đã bắt đầu"]
    C --> D["Review / Test"]
    D --> E["Release / Validate"]
    E --> F["Done<br/>điểm kết thúc"]
    D -. "Cần sửa" .-> C
    F -. "Phản hồi thực tế<br/>cập nhật backlog" .-> A
~~~

Trong ví dụ này, nhóm có thể chọn **start** khi item được kéo từ Ready vào Developing và **finish** khi vượt qua Release/Validate để vào Done. Các trạng thái trước start là **hàng đợi đầu vào**, chưa thuộc WIP được đo; những việc giữa start và finish thuộc WIP kể cả đang chờ.

Một nhóm khác có thể chọn Done là **đã đạt Definition of Done và sẵn sàng phát hành**, còn phát hành đo riêng. Điều đó không tự sai. Điều bắt buộc là **định nghĩa nhất quán với dịch vụ và câu hỏi cần trả lời**, chẳng hạn:

- Nếu hỏi “Mất bao lâu để Developers hoàn thành một Increment?”, Done có thể là đạt chuẩn sản phẩm sẵn sàng dùng.
- Nếu hỏi “Người yêu cầu mất bao lâu để nhận kết quả?”, cần tính cả thời gian chờ phát hành/bàn giao trong lead time của dịch vụ.
- Nếu dùng Scrum, hạng mục chưa đạt **Definition of Done** không thể gọi là Increment hoàn tất, dù đã chuyển sang cột báo cáo đẹp mắt.

### Trạng thái phải phản ánh công việc thực tế

Cột **Review/Test** nếu thực tế gồm “chờ review” và “đang được review” có thể được tách thành hai trạng thái/hàng đợi để nhìn rõ thời gian chờ. Nhưng **không phải càng nhiều cột càng tốt**. Chỉ thêm cột khi nó giúp phát hiện, điều hành hoặc kiểm chứng một chính sách có ý nghĩa.

### “Blocked” là cột hay nhãn?

Có thể thiết kế theo một trong hai cách:

- **Nhãn blocked trên trạng thái hiện tại:** thẻ vẫn ở Developing/Review, màu hoặc biểu tượng giúp nhìn thấy vấn đề. Dễ tránh che khuất nút thắt thực.
- **Trạng thái/hàng đợi blocked riêng:** có thể hữu ích nếu cách xử lý bị chặn thật sự khác; phải bảo đảm **không vô tình loại item khỏi WIP và phép đo tuổi việc**.

Không có lựa chọn duy nhất. Điều quan trọng là chính sách blocked ghi **lý do, thời điểm, cách tháo gỡ, người cần hỗ trợ và cách tính WIP**.

## 7. Thành phần thứ ba: kiểm soát WIP, không chỉ đếm thẻ

**Work in Progress (WIP)** là số item đã bắt đầu nhưng chưa hoàn tất trong ranh giới workflow đã định nghĩa. WIP cao khiến nhiều việc bị dở dang, tăng chuyển đổi ngữ cảnh, hàng đợi và rủi ro giao hàng kéo dài.

### Ví dụ giới hạn WIP

~~~text
Ready (hàng đợi)   Developing [WIP ≤ 3]    Review/Test [WIP ≤ 2]    Done
┌─────────────┐    ┌──────────────────┐    ┌──────────────────┐   ┌──────┐
│ Story C     │    │ Story A          │    │ Story B          │   │  X   │
│ Bug D       │    │ Story H          │    │ Story F          │   │  Y   │
│ Story G     │    │ Bug E (blocked)  │    │ [đầy: 2/2]      │   │      │
└─────────────┘    └──────────────────┘    └──────────────────┘   └──────┘
                      [đầy: 3/3]
~~~

Nếu Review/Test đã đầy và một item ở Developing sẵn sàng chuyển sang, nhóm không nên âm thầm đẩy sang rồi bắt đầu thêm việc mới để “ai cũng bận”. Họ có thể **cùng hoàn tất review**, xử lý item già nhất, tháo blocker hoặc điều chỉnh nguồn lực/đầu vào theo chính sách đã thống nhất.

### “Pull” khác “push” thế nào?

| **Push — đẩy việc** | **Pull — kéo việc** |
| --- | --- |
| Quản lý hoặc hệ thống đẩy thêm task vào người đang bận vì có yêu cầu mới | Người/nhóm nhận việc khi luồng tiếp theo có năng lực theo chính sách |
| Ưu tiên cục bộ: mọi cá nhân phải bận | Ưu tiên hệ thống: giúp item đang làm đạt Done |
| Hàng đợi và công việc chưa hoàn tất có thể phình to | WIP được kiểm soát để vấn đề tắc nghẽn lộ ra |
| Người phụ trách có thể đổi ngữ cảnh liên tục | Hạn chế chuyển đổi ngữ cảnh không cần thiết |

**WIP control không phải lúc nào cũng là một con số cột cứng.** Có thể dùng giới hạn toàn hệ thống, từng trạng thái, chính sách lớp công việc hoặc các cách kiểm soát rõ khác. Tuy nhiên, chỉ ghi “hãy làm ít việc” mà không có cơ chế quan sát/ứng xử cụ thể thì khó tạo thay đổi.

### Điều gì làm khi chạm giới hạn?

1. Kiểm tra item nào gần Done nhất, item nào đang bị chặn hoặc quá tuổi.
2. Hỗ trợ hoàn thành item hiện có trước khi khởi động item mới.
3. Điều phối người có khả năng xử lý review, test hoặc phụ thuộc.
4. Nếu có trường hợp khẩn, áp **chính sách ngoại lệ đã công bố** và ghi nhận tác động lên WIP/dự báo.
5. Xem lại giới hạn sau một khoảng quan sát để tránh đặt mức tùy tiện làm công việc tắc không cần thiết.

**WIP limit không phải quota năng suất** và không phải lý do để bỏ qua sự cố nghiêm trọng. Nó là cách buộc hệ thống đưa ra lựa chọn về luồng công việc.

## 8. Thành phần thứ tư: chính sách rõ ràng cho việc di chuyển

Một bảng trông ổn vẫn có thể hỗn loạn nếu mỗi người hiểu “Ready”, “Review” và “Done” khác nhau. Chính sách rõ làm các quy tắc **có thể nhìn thấy, thảo luận và sửa đổi**.

### Bộ chính sách minh họa

| Điểm trong workflow | Chính sách nhập/chuyển trạng thái | Vì sao cần |
| --- | --- | --- |
| **Ready** | Work item có người nhận giá trị, mục tiêu, điều kiện chấp nhận đủ để bắt đầu, phụ thuộc lớn đã nêu | Giảm “bắt đầu rồi mới phát hiện không hiểu” |
| **Ready → Developing** | Kéo item theo thứ tự ưu tiên/kịch bản dịch vụ; trạng thái đang làm còn năng lực theo WIP | Tránh khởi động vô hạn |
| **Developing → Review/Test** | Có thay đổi tích hợp được, mô tả kết quả cần kiểm tra, kiểm thử cấp phù hợp và môi trường sẵn sàng | Không đẩy công việc chưa đủ rõ qua bước tiếp theo |
| **Review/Test → Done** | Thỏa acceptance criteria, Definition of Done/chính sách dịch vụ, các kiểm tra bắt buộc và bàn giao theo ranh giới | Done phản ánh đầu ra đáng tin cậy |
| **Khi blocked** | Đánh dấu nguyên nhân, người phối hợp, thời điểm bắt đầu chờ; vẫn tính WIP trừ khi DoW định nghĩa xử lý khác có căn cứ | Không che giấu điểm nghẽn |
| **Khi phát sinh lỗi** | Phân loại mức ảnh hưởng, xác định có cần quay lại Developing và các kiểm thử hồi quy | Tránh đóng thẻ khi lỗi chưa xử lý |
| **Khi có yêu cầu khẩn** | Xác minh tiêu chí khẩn, người quyết định, tác động lên WIP và công việc khác | Ngăn mọi yêu cầu đều bị gắn “khẩn nhất” |

Các quy tắc trên chỉ là **ví dụ thực hành**. Mỗi nhóm phải căn cứ vào ràng buộc pháp lý, bảo mật, chất lượng, sản phẩm và quyền quyết định thực tế. Đừng tạo điều kiện “Ready” quá nặng làm nhóm mất khả năng thử nghiệm trong bối cảnh bất định.

### Minh bạch và dễ thay đổi

Để chính sách có tác dụng, mọi người cần biết:

- Nó áp dụng từ **điểm nào đến điểm nào**.
- Ai có quyền đề xuất và quyết định ngoại lệ, ví dụ production incident.
- Khi có xung đột ưu tiên, ai giải quyết và theo tiêu chí nào.
- Dữ liệu nào giúp biết chính sách đang hữu ích hoặc gây tắc.
- Khi nào nhóm kiểm tra và thay đổi chính sách.

**Chính sách tốt không phải chính sách không bao giờ đổi; nó là giả thuyết vận hành có thể được kiểm chứng và cải tiến.**

## 9. Thành phần thứ năm: SLE — kỳ vọng dịch vụ dựa trên bằng chứng

**Service Level Expectation (SLE)** diễn đạt kỳ vọng về thời gian một item chảy từ start đến finish, thường có **mốc thời gian và mức xác suất/độ tin cậy** dựa trên dữ liệu lịch sử.

Ví dụ:

> “Với loại work item chuẩn, bắt đầu khi kéo vào Developing và kết thúc tại Done, dữ liệu trước đây cho thấy khoảng **85% item hoàn tất không quá 10 ngày làm việc**.”

Đây là phát biểu **theo dữ liệu và ranh giới cụ thể**, không phải lời bảo đảm mọi item sẽ hoàn tất trong 10 ngày.

### SLE khác deadline và SLA thế nào?

| Thuật ngữ | Cách hiểu phù hợp |
| --- | --- |
| **SLE** | Kỳ vọng thời gian hoàn thành dùng để quản lý flow và phản hồi, thường có phân vị/mức xác suất |
| **Deadline** | Mốc cần đáp ứng do kinh doanh hoặc một nghĩa vụ xác định |
| **SLA (Service Level Agreement)** | Thỏa thuận mức dịch vụ có thể mang tính hợp đồng/quản trị với quyền lợi và hậu quả khi không đáp ứng |

SLE không tự trở thành SLA pháp lý và cũng không phải giấy phép bỏ qua các deadline thực. Nếu cần cam kết với khách hàng, tổ chức phải làm rõ **mức nghĩa vụ, điều kiện, phạm vi, ngoại lệ và quản trị rủi ro**.

### Ví dụ số liệu SLE đơn giản

Giả sử trong **40 work items tương đối đồng dạng** đã hoàn tất, có **34 item** có cycle time **không quá 10 ngày làm việc**, tính từ start đến Done như DoW đã định nghĩa.

\[
\frac{34}{40}=0{,}85=85\%
\]

Nhóm có thể ghi: “Dữ liệu mẫu cho thấy 85% item hoàn thành trong 10 ngày làm việc hoặc ít hơn”. Nhưng **mẫu 40 item không bảo đảm chính xác 85% item tương lai cũng đạt mốc**; cần xem biến động, tính đại diện, loại công việc và mọi thay đổi quy trình.

### SLE là tín hiệu chủ động

Nếu một item hiện có **work item age = 9 ngày**, đang gần mốc SLE 10 ngày, nhóm nên kiểm tra nguyên nhân chờ và hành động. Không nhất thiết chờ đến ngày 11 mới coi có vấn đề.

**Không được suy rằng một item đã 9 ngày thì “chắc chắn 85% sẽ xong vào ngày thứ 10”.** Phân bố cycle time từ lúc bắt đầu và dự báo thời gian còn lại **có điều kiện theo tuổi hiện tại** là những câu hỏi khác nhau.

## 10. Bốn số đo flow cơ bản và cách đọc đúng

Theo The Kanban Guide, bốn thước đo tối thiểu cần quan sát là **WIP, throughput, work item age và cycle time**.

| Chỉ số | Đo gì? | Câu hỏi điều hành | Sai lầm thường gặp |
| --- | --- | --- | --- |
| **WIP** | Số item đã bắt đầu nhưng chưa hoàn tất | Có bao nhiêu việc đang cùng tiêu tốn năng lực và chờ đợi? | Không tính các item bị blocked; chỉ đếm task coding đang hoạt động |
| **Throughput** | Số item được hoàn tất trong một khoảng thời gian | Hệ thống đang hoàn thành bao nhiêu đơn vị giá trị? | Xem số thẻ tăng là giá trị tăng dù cách chia item đã đổi |
| **Work item age** | Thời gian một item hiện chưa Done đã ở trong workflow từ điểm start | Item nào có nguy cơ kéo dài và cần can thiệp trước? | Chỉ xem các item đã Done, bỏ qua việc “già” đang kẹt |
| **Cycle time** | Khoảng thời gian thực tế từ start đến finish của một item đã Done | Phân bố thời gian hoàn tất ra sao, biến thiên thế nào? | Xem một giá trị trung bình là cam kết chắc chắn cho mọi item |

### Một ví dụ tuần làm việc

Giả sử từ thứ Hai đến thứ Sáu, một hệ thống Kanban có:

| Ngày | WIP cuối ngày | Item đạt Done trong ngày | Item lâu nhất chưa Done |
| --- | ---: | ---: | --- |
| Thứ Hai | 8 | 1 | 7 ngày |
| Thứ Ba | 9 | 0 | 8 ngày |
| Thứ Tư | 9 | 1 | 9 ngày |
| Thứ Năm | 8 | 0 | 10 ngày |
| Thứ Sáu | 7 | 2 | 11 ngày |

Tổng **throughput tuần = 1 + 0 + 1 + 0 + 2 = 4 items**. Nếu WIP gần như giữ ở mức 8–9 nhưng item lâu nhất vẫn già lên, nhóm có thể đang có một số item bị chặn khó xử lý; không thể kết luận “mọi thứ ổn vì tuần này vẫn đóng được bốn thẻ”.

WIP cuối ngày chỉ là **ảnh chụp**, chưa phải trung bình WIP đủ chính xác cho mọi mô hình. Cycle time cần lấy từ **từng item đã Done** với timestamp phù hợp, không thể tính trực tiếp từ cột WIP cuối ngày.

### Đọc phân bố, không chỉ nhìn một số trung bình

Giả sử cycle time của 12 item hoàn tất là:

~~~text
2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 9, 14 (ngày làm việc)
~~~

**Trung vị** là trung bình của giá trị thứ 6 và thứ 7, tức **5 ngày**. Có item hoàn tất sau 14 ngày, cho thấy đuôi phân bố dài hơn nhiều so với trung vị. Nếu chỉ báo “trung vị 5 ngày”, người nhận có thể đánh giá thấp rủi ro của các item chậm.

Với mẫu nhỏ, các phân vị cao (ví dụ P85) không ổn định và phụ thuộc cách tính; nếu dùng làm SLE cần **nêu phương pháp, số lượng quan sát và giới hạn của mẫu**, không xem đó là giá trị chính xác đến nhiều chữ số.

## 11. Dòng công việc là hệ thống có hàng đợi và nút thắt

Một trong những lợi ích lớn nhất của Kanban là chuyển sự chú ý từ “ai đang bận” sang **công việc mất thời gian ở đâu**.

~~~mermaid
flowchart LR
    A["Yêu cầu được chấp nhận"] --> B["Ready<br/>hàng đợi"]
    B --> C["Developing"]
    C --> D["Chờ review"]
    D --> E["Review / Test"]
    E --> F["Chờ triển khai"]
    F --> G["Done / nhận giá trị"]
    D -. "WIP tích tụ" .-> H["Cần nhìn điểm nghẽn,<br/>thay vì chỉ tăng coding"]
~~~

Giả sử một thay đổi phần mềm cần 2 giờ làm mã nhưng chờ 3 ngày review và 4 ngày phê duyệt triển khai. **Tăng tốc viết mã** không làm thời gian từ start đến Done giảm tương ứng. Ngược lại, việc có chính sách review sớm, cùng xử lý công việc bị chặn hoặc cải thiện triển khai an toàn có thể giúp dòng chảy tốt hơn.

### Tốc độ hoàn tất và mức sử dụng nhân sự

**Tối đa hóa mức bận của từng cá nhân** dễ làm mọi người bắt đầu thêm việc để tránh thời gian rảnh, khiến nhiều item chờ lâu hơn. **Tối ưu flow** hướng vào việc hoàn tất và giao giá trị, chấp nhận rằng đôi khi Developers hỗ trợ review, kiểm thử hoặc tháo blocker thay vì tiếp tục tạo task coding mới.

### Liên hệ định luật Little

Trong một hệ thống ổn định, với ranh giới, đơn vị và điều kiện đo nhất quán, có một quan hệ trung bình thường được nêu:

\[
\text{Average WIP} \approx \text{Average Throughput Rate} \times \text{Average Cycle Time}
\]

Nếu WIP trung bình khoảng **9 item** và throughput trung bình khoảng **3 item/tuần**, phép tính sơ bộ cho cycle time trung bình vào khoảng:

\[
\frac{9\ \text{item}}{3\ \text{item/tuần}} \approx 3\ \text{tuần}
\]

**Cảnh báo:** Đây là quan hệ trung bình dưới các giả định cần thiết của hệ thống tương đối ổn định, không phải công thức xác định thời gian hoàn tất của một ticket và cũng không suy ra rằng cứ đặt WIP bằng 3 là mọi ticket xong trong 1 tuần. Nếu lượng việc đến/ra thay đổi mạnh, đo WIP theo vài ảnh chụp thiếu đại diện hoặc ranh giới không nhất quán, phép xấp xỉ có thể gây hiểu nhầm.

## 12. Chủ động quản lý flow: từ quan sát tới hành động

Một hệ thống Kanban hoạt động khi đội ngũ thường xuyên hỏi **item nào cần được hoàn tất tiếp theo và điều gì đang ngăn nó chảy**.

### Một vòng quản lý công việc hằng ngày

1. **Nhìn gần Done trước:** Những item ở Review/Test hoặc đang chờ phát hành có thể hoàn thành sớm với hỗ trợ nhỏ không?
2. **Xem item già và bị chặn:** Work item age tăng ở đâu, rủi ro vượt SLE nào cần phản ứng sớm?
3. **Kiểm tra WIP và khả năng kéo:** Có được bắt đầu việc mới không, hay nên cùng hoàn tất công việc hiện tại?
4. **Làm rõ ưu tiên và ngoại lệ:** Yêu cầu khẩn có thực sự đáp ứng chính sách xử lý khẩn không?
5. **Cập nhật trạng thái, chính sách và người cần hỗ trợ:** Việc nào được chuyển, ai giúp giải quyết phụ thuộc?
6. **Kiểm tra lại hiệu quả:** Tác động của thay đổi có phản ánh ở cycle time, aging, throughput và chất lượng không?

### Ví dụ đối thoại

**Cách hỏi chỉ nhìn bảng:**

> “Tại sao thẻ của em vẫn ở Review? Em phải chuyển sang Done hôm nay.”

**Cách hỏi theo flow:**

> “Review đang đầy và hai item đã chờ bốn ngày. Quy tắc vào/ra cột này có rõ không? Ai có thể giúp hoàn tất kiểm thử trước khi ta kéo thêm việc? Có phụ thuộc nào cần được tháo ở cấp nhóm khác?”

Câu hỏi thứ hai không phủ nhận trách nhiệm; nó hướng đến **khả năng hoàn thành công việc trong hệ thống thực**, thay vì yêu cầu thay màu cột cho đẹp.

## 13. Thiết lập các vòng phản hồi của hệ thống

Kanban không chỉ có Daily Stand-up. Một hệ thống hữu ích cần những cơ hội phù hợp để **quan sát, đưa ra quyết định và cải tiến**. Nhịp có thể theo sự kiện hoặc lịch định kỳ tùy loại dịch vụ.

| Vòng phản hồi | Câu hỏi trung tâm | Ví dụ nhịp có thể dùng |
| --- | --- | --- |
| **Flow review hằng ngày** | Item nào đang tắc, già lên hoặc có nguy cơ trễ kỳ vọng? | Hằng ngày hoặc ngay khi bảng phát tín hiệu |
| **Replenishment / bổ sung đầu vào** | Khi có năng lực, nên kéo công việc nào vào workflow? | Khi thỏa điều kiện pull, hoặc một phiên ngắn định kỳ |
| **Service delivery review** | Thời gian và chất lượng dịch vụ có phù hợp kỳ vọng không? | Theo tuần/tháng tùy lưu lượng và rủi ro |
| **Risk review** | Loại công việc, phụ thuộc hoặc ngoại lệ nào gây biến thiên lớn? | Khi có rủi ro mới hoặc theo nhịp đã chọn |
| **Operations/strategy review** | Luồng ở nhiều nhóm và năng lực tổ chức có phù hợp mục tiêu giá trị không? | Theo mốc quyết định quản lý sản phẩm/dịch vụ |
| **Cải tiến hệ thống** | Chính sách nào nên thử thay đổi, lấy bằng chứng bằng gì? | Theo chu kỳ thử nghiệm có chủ đích |

**Các cuộc họp và tần suất trong bảng là minh họa, không phải các sự kiện bắt buộc giống Sprint Planning/Daily Scrum trong Scrum.** Nhóm có thể tổ chức trao đổi bất đồng bộ nếu vẫn giúp đưa ra quyết định kịp thời.

### Vòng phản hồi cần một kết quả

Không chỉ hỏi “có bao nhiêu thẻ đang ở đâu?”; hãy kết thúc bằng:

- Quyết định gì vừa được đưa ra?
- Chính sách hoặc thứ tự công việc có thay đổi không?
- Ai đang gỡ blocker và bằng cách nào?
- Chỉ số nào sẽ cho biết thay đổi có ích?
- Khi nào sẽ xem lại?

Một cuộc họp đúng giờ nhưng không tạo ra sự điều chỉnh cần thiết **chưa tạo vòng phản hồi có ý nghĩa**.

## 14. Xử lý công việc khẩn và các lớp dịch vụ

Một hệ thống làm việc thật thường có lỗi sản xuất nghiêm trọng, yêu cầu có hạn chót và công việc cải tiến dài hạn. Nếu tất cả theo đúng một hàng đợi, đôi khi cần chờ không phù hợp; nếu mọi người đều được gắn nhãn “khẩn”, WIP sẽ mất kiểm soát.

Một số cách triển khai **Kanban Method** sử dụng *classes of service* (lớp dịch vụ), chẳng hạn:

| Lớp minh họa | Đặc điểm | Chính sách nên làm rõ |
| --- | --- | --- |
| **Standard** | Yêu cầu bình thường, sắp xếp theo giá trị và thứ tự | Kéo theo ưu tiên khi có năng lực |
| **Expedite** | Sự cố có hậu quả cao cần xử lý ngay | Tiêu chí thế nào mới đủ khẩn; ai quyết; giới hạn ngoại lệ; điều gì bị gián đoạn |
| **Fixed date** | Có mốc thực sự quan trọng | Xác minh deadline, chuẩn bị trước, quản lý rủi ro chờ |
| **Intangible** | Công việc giảm nợ kỹ thuật/cải thiện năng lực có lợi ích dài hạn | Quyết định năng lực dành cho công việc phòng ngừa, tránh bị đẩy lùi mãi |

**Các lớp dịch vụ này là kỹ thuật tùy chọn**, không phải danh sách bắt buộc trong mọi Definition of Workflow. Nếu dùng, nhóm phải định nghĩa ý nghĩa rõ, tránh đổi nhãn tùy ý.

### Ví dụ lỗi mất tiến độ học viên

Nếu lỗi sản xuất có thể làm mất dữ liệu học tập, nhóm cần ưu tiên xử lý theo cơ chế sự cố đã thống nhất, kể cả tạm thời vượt chính sách WIP thông thường nếu điều đó phù hợp an toàn. Nhưng ngoại lệ phải **được nhìn thấy**, ghi nhận tác động lên các công việc khác và được đánh giá sau sự cố. Nếu cứ mỗi ngày có vài “expedite” do người có quyền yêu cầu, vấn đề là chính sách ưu tiên và năng lực, không thể sửa chỉ bằng tô đỏ thêm thẻ.

## 15. Tình huống xuyên suốt: từ bảng ba cột sang hệ thống flow

Giả sử một nhóm sáu người phát triển nền tảng học trực tuyến xử lý user story, bug và việc triển khai. Nhóm đã có bảng **To do – Doing – Done** ba tháng.

### 15.1. Tình trạng ban đầu

- 20–25 item thường xuyên ở Doing; nhiều item mở cùng lúc.
- Developers viết xong phần kỹ thuật nhưng chờ review hoặc kiểm thử.
- Một số item được chuyển Done ngay khi merge mã dù chưa đủ tiêu chuẩn triển khai.
- Hằng ngày có yêu cầu “ưu tiên ngay” từ nhiều bên.
- Không lưu thời điểm start/finish nhất quán, nên không thể nói item hoàn tất trong bao lâu.
- Nhóm báo số ticket Done hằng tuần nhưng người học vẫn chờ nhiều tuần mới nhận tính năng.

**Nhận định:** Có bảng trực quan nhưng thiếu định nghĩa flow, điều kiện Done, cơ chế kiểm soát WIP, chính sách ưu tiên và các số đo tin cậy. Việc áp thêm màu cho cột sẽ không đủ.

### 15.2. Bước 1 — vẽ lại workflow thực

Nhóm đi theo một user story vừa hoàn tất và một bug bị chặn để xác định đường đi:

~~~text
Requested → Ready → Developing → Waiting for Review
          → Reviewing/Testing → Ready for Release → Released
~~~

Nhóm quyết định **start = lúc kéo từ Ready sang Developing**, **finish = lúc Released** cho dịch vụ giao thay đổi đến production. Họ vẫn ghi rõ **Definition of Done** của Increment và không đánh đồng “đã merge” với “đã phát hành”. Với nhu cầu báo cáo hoàn tất phát triển trước production, họ có thể đo thêm một khoảng riêng, không thay nghĩa chỉ số đang dùng.

### 15.3. Bước 2 — làm rõ chính sách

| Quyết định | Chính sách thử trong bốn tuần |
| --- | --- |
| **Đơn vị theo dõi** | Story dọc và bug với tiêu chí hoàn tất rõ; task phụ không làm tăng throughput item |
| **WIP** | Giới hạn tổng item đã bắt đầu ở mức phù hợp với năng lực nhóm; thử giới hạn cụ thể theo các bước đang tắc |
| **Pull** | Chỉ kéo thêm item khi có năng lực; trước tiên giúp hoàn tất item ở review/test |
| **Review/Test** | Quy tắc vào rõ; ưu tiên item cũ, đưa lý do blocked và người hỗ trợ lên bảng |
| **Done** | Chỉ khi đạt tiêu chuẩn chất lượng và điểm kết thúc Release theo DoW đã chọn |
| **Việc khẩn** | Có tiêu chí production incident và người quyết định ngoại lệ |
| **SLE** | Ban đầu công bố kỳ vọng thận trọng, ghi rõ lịch sử còn thiếu và cập nhật khi có đủ dữ liệu |

Không cần áp giới hạn 3 hoặc 5 item theo một “chuẩn Kanban” nào. Nhóm chọn mức đầu tiên từ năng lực, WIP hiện tại và khả năng hoàn tất; sau đó đo tác động thay vì coi số đó bất biến.

### 15.4. Bước 3 — vận hành và học từ dữ liệu

Tuần đầu, nhóm bắt đầu nhìn **work item age**. Hai story đã chờ review hơn 12 ngày; nhóm ưu tiên review và sửa bài kiểm thử, thay vì mở thêm ba story mới.

Tuần hai, nhóm ghi nhận phần lớn thời gian chờ nằm ở cấp môi trường kiểm thử. Họ phối hợp hạ tầng tạo cơ chế cấp môi trường đơn giản hơn, đồng thời đặt chính sách đánh dấu blocker sớm.

Tuần ba, phản hồi người dùng cho thấy story “Học tiếp” còn thiếu điều kiện khi khóa học hết quyền truy cập. Nhóm bổ sung tiêu chí an toàn, tách phần mở rộng không cần thiết sang backlog phù hợp. **Giảm thời gian tới Done không được đánh đổi bằng việc phát hành tính năng sai quyền**.

Tuần bốn, nhóm kiểm tra lại throughput, cycle time, item bị chặn, lỗi production và mức độ ổn định của công việc. Nếu thời gian chờ giảm mà lỗi tăng, cải tiến chưa thật sự tốt. Nếu flow nhanh hơn nhưng sản phẩm không giúp học viên tiếp tục học, cần xem lại cách ưu tiên giá trị, không chỉ tối ưu workflow.

### 15.5. Bảng so sánh trước/sau theo các chiều

| Khía cạnh | Trước — chỉ có bảng | Sau — hệ thống được định nghĩa |
| --- | --- | --- |
| **Trạng thái** | To do / Doing / Done chung chung | Các bước và hàng đợi thực, có start/finish rõ |
| **Kéo việc** | Người có yêu cầu mới giao ngay | Có chính sách pull, năng lực và WIP |
| **Blocked** | Một nhãn đỏ đôi khi bị bỏ qua | Có lý do, người phối hợp, tuổi công việc và cơ chế gỡ |
| **Done** | Merge mã là xong | Đạt chuẩn chất lượng và mốc hoàn tất đã định nghĩa |
| **Dự báo** | Hỏi ý kiến từng người, nêu một ngày | Sử dụng dữ liệu flow/SLE có điều kiện và mức bất định |
| **Phản hồi** | Họp cập nhật trạng thái | Xem dữ liệu, ra quyết định và kiểm chứng cải tiến |
| **Giá trị** | Đếm số ticket đóng | Quan sát thời gian đến kết quả và phản hồi người nhận giá trị |

**Lưu ý:** Đây là kịch bản thực hành, không phải số liệu chứng minh rằng một chính sách WIP cụ thể sẽ tự động cải thiện mọi nhóm. Để khẳng định tác động thực, cần dữ liệu trước/sau và xem xét các thay đổi khác trong cùng thời gian.

## 16. Scrum, Kanban và XP có thể kết hợp thế nào?

**Scrum** và **Kanban** không phải hai loại bảng khác nhau. Scrum là framework với accountabilities, events, artifacts và commitments; Kanban tập trung vào việc định nghĩa, quản lý và cải tiến luồng công việc. XP cung cấp các thực hành kỹ thuật giúp thay đổi phần mềm an toàn.

| Trọng tâm | Scrum | Kanban | XP |
| --- | --- | --- | --- |
| **Câu hỏi chính** | Sprint này tạo giá trị gì và kiểm tra/thích ứng thế nào? | Công việc chảy đến Done ra sao và có thể cải thiện ở đâu? | Làm sao giữ mã, kiểm thử và tích hợp dễ thay đổi? |
| **Cơ chế trọng tâm** | Sprint Goal, Sprint Backlog, Increment, các sự kiện và trách nhiệm Scrum | Definition of Workflow, WIP, flow metrics, SLE, policies và phản hồi | TDD, pair programming, CI, refactoring, phát hành nhỏ |
| **Nhịp** | Sprint có timebox không quá một tháng | Có thể kéo việc liên tục; phản hồi theo nhịp hoặc sự kiện phù hợp | Phản hồi kỹ thuật trong các thay đổi nhỏ, thường xuyên |
| **Vai trò bảng** | Có thể dùng để thấy Sprint Backlog và kế hoạch Developers | Là hình ảnh trực quan của DoW, không thay thế hệ thống | Có thể hỗ trợ, nhưng không phải nội dung cốt lõi của XP |

### Scrum Team có thể dùng Kanban không?

Có. Ví dụ trong Sprint hai tuần, Developers vẫn hướng đến **Sprint Goal**, dựa trên **Sprint Backlog** được cập nhật hằng ngày và tạo **Increment đạt Definition of Done**. Đồng thời, nhóm có thể sử dụng bảng có WIP limit, đo **cycle time, throughput, work item age** và cải tiến chính sách review.

Việc dùng Kanban **không xóa bỏ** Sprint Goal, quyền quyết định của Product Owner hay Daily Scrum nếu nhóm vẫn đang sử dụng Scrum. Tương tự, nhóm làm việc theo Kanban không có nghĩa bắt buộc phải thêm Sprint Planning hoặc Sprint Review theo tên gọi Scrum.

### XP làm flow ổn định hơn ra sao?

Nếu kiểm thử thất bại liên tục hoặc tích hợp vào cuối chu kỳ, item có thể mắc kẹt ở Review/Test. Các thực hành **TDD, CI, refactoring, pair programming và small releases** giúp phát hiện vấn đề kỹ thuật sớm, giảm việc làm lại và hỗ trợ các lát cắt nhỏ đi đến Done. Bảng Kanban không thể thay thế những năng lực kỹ thuật này.

## 17. Lộ trình xây hệ thống Kanban từ một bảng sẵn có

Một lộ trình thực dụng là **bắt đầu từ công việc hiện tại, làm rõ luồng, đo và cải tiến từng bước**. Không cần tổ chức lại toàn bộ công ty trước khi thử.

### Giai đoạn 1 — nhìn thấy đúng thực tế

1. Chọn dịch vụ hoặc luồng giá trị cụ thể cần cải thiện.
2. Quan sát một số item thật từ lúc nhận nhu cầu tới khi giao kết quả.
3. Vẽ trạng thái và hàng đợi đang tồn tại, kể cả bước chờ không hiển thị.
4. Làm rõ người nhận giá trị, đơn vị work item và start/finish.
5. Đặt các item đang hoạt động lên bảng theo trạng thái thật; **không tô xanh giả**.

**Đầu ra:** Bản workflow ban đầu và những điểm chưa rõ cần thảo luận.

### Giai đoạn 2 — làm chính sách hiển thị và có thể hành động

1. Thống nhất điều kiện Ready, chuyển trạng thái, Done và blocked.
2. Chọn cơ chế kiểm soát WIP ban đầu.
3. Xác định cách pull, ưu tiên và xử lý trường hợp khẩn.
4. Ghi người cần phối hợp khi có blocker hoặc phụ thuộc.
5. Chọn nhịp xem flow và bổ sung công việc.

**Đầu ra:** Definition of Workflow được mọi người trong hệ thống hiểu và có thể áp dụng.

### Giai đoạn 3 — đo đúng và chủ động điều hành

1. Lưu timestamp start/finish và trạng thái work item khi cần.
2. Đo WIP, throughput, cycle time, work item age với ranh giới nhất quán.
3. Sử dụng dữ liệu đủ phù hợp để đề xuất SLE có điều kiện.
4. Theo dõi việc già đi và các nút thắt **khi chúng còn có thể được xử lý**, không đợi cuối tháng.
5. Minh bạch thay đổi về loại việc, nhân sự, chính sách và độ phức tạp.

**Đầu ra:** Hệ thống có tín hiệu giúp ra quyết định, không chỉ trang báo cáo.

### Giai đoạn 4 — thử nghiệm cải tiến

1. Chọn một vấn đề có bằng chứng, ví dụ Review/Test chờ quá lâu.
2. Nêu giả thuyết: “Nếu nhóm cùng hoàn tất review trước khi kéo việc mới, thời gian chờ sẽ giảm”.
3. Thử thay đổi có giới hạn trong một khoảng phù hợp.
4. Quan sát cycle time, work item age, throughput **và chất lượng**.
5. Đánh giá kết quả, giữ/đổi/bỏ chính sách và cập nhật DoW.

**Đầu ra:** Các quyết định cải tiến dựa trên thực tế. Một hệ thống Kanban không bao giờ chỉ “cấu hình xong bảng là hoàn tất”.

## 18. Bài thực hành: từ bảng ba cột tới DoW tối thiểu

Giả sử một nhóm đang có bảng:

~~~text
To do: 12 thẻ
Doing: 9 thẻ
Done: 5 thẻ
~~~

Không có thêm thông tin nào. Bảng trên **không đủ** để dự báo công việc có thể hoàn tất trong tuần tới.

### Bước A — đặt câu hỏi trước khi thay đổi

1. Thẻ đại diện cho user story, bug, task kỹ thuật hay hỗn hợp?
2. Item vào Doing lúc nào; “Done” nghĩa là gì?
3. Trong chín thẻ Doing, bao nhiêu việc đang chờ review, chờ dữ liệu hoặc chờ người?
4. Ai được quyết định kéo việc từ To do vào Doing?
5. Có thể dừng bắt đầu việc mới để hoàn thành chín item đang làm không?
6. Trong bốn tuần gần đây có bao nhiêu item thật sự đạt Done và mất bao lâu?
7. Có loại việc khẩn nào cần chính sách riêng?

### Bước B — viết DoW

~~~text
DỊCH VỤ ĐƯỢC QUẢN LÝ:
  [Ví dụ: giao thay đổi sản phẩm cho học viên]

WORK ITEM:
  [Đơn vị giá trị được theo dõi]

START:
  [Sự kiện bắt đầu WIP]

FINISH:
  [Sự kiện kết thúc, tiêu chuẩn Done/Release]

CÁC TRẠNG THÁI:
  [Các bước thật từ start tới finish]

KIỂM SOÁT WIP:
  [Giới hạn/chính sách trong các bước và toàn workflow]

CHÍNH SÁCH:
  [Pull, nhập/ra cột, blocked, ưu tiên, ngoại lệ]

SLE:
  [Mốc thời gian + mức kỳ vọng + nguồn dữ liệu/giới hạn]

PHẢN HỒI VÀ CẢI TIẾN:
  [Nhịp kiểm tra, người quyết định, thước đo]
~~~

Nếu chưa có dữ liệu tin cậy cho SLE, hãy **nêu rõ đây là giả thuyết kỳ vọng ban đầu** và kế hoạch thu thập/hiệu chỉnh, không gán “85% trong 5 ngày” như một sự thật thống kê.

### Bước C — chọn một thử nghiệm

Ví dụ: “Trong ba tuần tới, giới hạn Developing ở một mức đã thỏa thuận, ưu tiên hỗ trợ Review/Test khi đầy. Mỗi ngày xem work item age của những item lâu nhất. So sánh thời gian chờ review và lỗi lọt production với trước, có chú thích thay đổi loại việc”.

Kết quả tốt không chỉ là “Doing còn ít thẻ”; nó phải giúp công việc **đạt Done đúng chất lượng** và cải thiện thời gian phục vụ hoặc mức tin cậy.

## 19. Những phản mẫu phổ biến

### 19.1. “Có Jira/Trello tức là đã có Kanban”

Công cụ làm cho bảng dễ cập nhật, nhưng không xác định thay nhóm chính sách pull, điểm bắt đầu/kết thúc, WIP và SLE. Hãy quan sát các quyết định thật trong nhóm, không chỉ danh sách tính năng của phần mềm.

### 19.2. “Càng nhiều cột càng minh bạch”

Thêm cột không tự giúp giao hàng. Nếu trạng thái không có điều kiện vào/ra hoặc không được dùng để điều hành, bảng phức tạp sẽ tăng chi phí mà không tăng hiểu biết.

### 19.3. “Mỗi người một thẻ Doing là tối ưu”

Giới hạn một người một task chưa chắc giải quyết việc đang chờ review, tích hợp hay triển khai. WIP cần được xem theo **luồng công việc chung**, không chỉ mức bận của cá nhân.

### 19.4. “Item blocked thì chuyển ra ngoài WIP để có chỗ nhận việc khác”

Nếu chỉ đổi trạng thái để WIP giảm trên bảng trong khi công việc vẫn chưa hoàn tất, hệ thống đang che giấu hàng đợi. Blocked cần được quản lý theo chính sách rõ, không phải cách hợp thức hóa khởi động thêm nhiều việc.

### 19.5. “WIP limit càng thấp càng tốt”

Giới hạn quá thấp so với phụ thuộc và loại việc có thể gây tắc không cần thiết. Giới hạn là **giả thuyết vận hành**; điều chỉnh dựa trên đo lường, năng lực và chất lượng, không dựa trên một con số thần kỳ.

### 19.6. “Dùng throughput để xếp hạng năng suất cá nhân”

Việc kiểm thử, giúp đồng đội, giảm lỗi và tháo blocker có giá trị lớn nhưng có thể không tạo thêm ticket cá nhân. Đếm thẻ để thưởng/phạt khuyến khích chia vụn việc và né việc khó.

### 19.7. “SLE là lời hứa mọi item phải xong trước hạn”

SLE là kỳ vọng dịch vụ có điều kiện, thường dựa trên phân bố lịch sử. Cần phân biệt xác suất, đối tượng và ranh giới đo với nghĩa vụ hợp đồng.

### 19.8. “Tăng tốc một cột sẽ tăng tốc toàn hệ thống”

Nếu Developers hoàn thành mã nhanh hơn nhưng Review/Test vẫn tắc, tồn đọng sẽ chỉ chuyển chỗ. Cần nhìn **end-to-end** và đưa năng lực tới điểm nghẽn.

### 19.9. “Kanban không có kế hoạch hay ưu tiên”

Kanban cần chính sách chọn việc, quyết định năng lực, kỳ vọng phục vụ và vòng phản hồi. Không bắt buộc Sprint hai tuần không có nghĩa công việc diễn ra không có mục tiêu.

### 19.10. “Đã có bảng nên không cần cải tiến kỹ thuật”

Các kỹ thuật XP, kiểm thử tự động, CI, refactoring, phát hành tăng dần và giám sát ảnh hưởng trực tiếp đến khả năng đưa item về Done an toàn. Bảng chỉ cho thấy chỗ nghẽn; cải thiện kỹ thuật mới có thể xử lý nguyên nhân.

### 19.11. “Càng nhanh càng tốt, kể cả bỏ qua chất lượng”

Cycle time giảm do bỏ kiểm thử, phân quyền hoặc chuyển Done sớm có thể làm trải nghiệm và độ tin cậy tệ hơn. Đo flow phải đi cùng chuẩn hoàn tất và chất lượng thực tế.

### 19.12. “Ngày nào cũng họp bảng là đã có vòng phản hồi”

Nếu mọi người chỉ đọc lần lượt trạng thái mà không quyết định kéo việc, gỡ blocker hay thay chính sách, cuộc họp chưa giúp quản lý flow. Cần kết thúc bằng hành động và bằng chứng cần kiểm tra.

## 20. Bài tập tự kiểm tra

### Bài tập A — Board hay system?

Đánh giá từng phát biểu là **chỉ mô tả bảng**, **một thành phần hệ thống**, hoặc **dấu hiệu vận hành hệ thống**:

1. “Nhóm có bốn cột màu sắc rõ ràng và thẻ cho mọi task.”
2. “Item từ Developing sang Review phải qua kiểm thử tự động đã thống nhất.”
3. “Chỉ kéo việc mới khi WIP cho phép; nếu Review đầy thì cùng xử lý item ở đó.”
4. “Mỗi tuần nhóm xem cycle time, tuổi việc và lỗi rồi đổi chính sách khi cần.”
5. “Một item được gọi Done khi code merge, dù bên nhận vẫn phải chờ triển khai; nhóm nêu rõ đó là mốc kết thúc đang đo.”
6. “Bảng có nhãn đỏ cho tất cả công việc khẩn, nhưng không ai biết tiêu chí khẩn.”

**Gợi ý:** (1) là công cụ trực quan; (2) là chính sách DoW; (3) và (4) cho thấy vận hành flow; (5) cần xét ranh giới dịch vụ — có thể minh bạch nhưng chưa đủ nếu muốn đo đến lúc người dùng nhận giá trị; (6) mới có nhãn chứ chưa có chính sách ưu tiên hữu ích.

### Bài tập B — Tính throughput và nhận diện rủi ro

Trong năm ngày làm việc, số item Done là **[2, 0, 1, 0, 3]**, còn WIP cuối ngày là **[7, 8, 9, 9, 8]**.

1. Throughput cả tuần là bao nhiêu?
2. Vì sao chưa thể tính chính xác cycle time của các item từ dữ liệu trên?
3. Nếu một item đã ở Doing 15 ngày, bạn sẽ hỏi gì?
4. Bạn có thể kết luận nhóm đang sử dụng WIP tối ưu không? Vì sao?

**Gợi ý:** Throughput = **6 item/tuần**. Muốn biết cycle time cần timestamp start/finish của từng item đạt Done; WIP cuối ngày không cho phép suy trực tiếp. Cần phân tích item bị chặn, loại việc và điều kiện Done trước khi đánh giá hiệu quả WIP.

### Bài tập C — Xây chính sách blocked

Một nhóm có nhiều item bị chặn vì môi trường staging hay hết dung lượng. Hãy đề xuất:

- Khi nào thẻ được gắn blocked và ghi lý do thế nào?
- Blocked vẫn tính WIP ra sao?
- Ai giải quyết phụ thuộc với bộ phận hạ tầng?
- Khi nào cần chuyển cấp xử lý nếu ảnh hưởng tới kỳ vọng dịch vụ?
- Cách biết thay đổi môi trường có thực sự làm giảm thời gian chờ?

**Gợi ý:** Chính sách cần tạo hành động, đo được work item age/thời gian chờ và có người hỗ trợ rõ. Không dùng một cột blocked để bỏ quên việc.

### Bài tập D — Thiết kế SLE

Một nhóm có 40 item hoàn tất, trong đó 34 item không quá 10 ngày làm việc. Hãy viết một câu SLE có bối cảnh đúng, giải thích:

1. 85% có nghĩa gì trong **mẫu lịch sử**?
2. Vì sao không bảo đảm 85% tương lai?
3. Nếu item đang làm đã 9 ngày, hành động nào hợp lý?
4. Những trường hợp nào khiến dữ liệu không còn đại diện?

**Gợi ý:** Viết rõ loại công việc, mốc start/finish, dữ liệu mẫu và kỳ vọng có điều kiện; không dùng phân vị của item đã Done như một lời hứa chính xác cho item đang làm.

### Bài tập E — Chọn can thiệp thay vì thêm cột

Đội có bảng To do → Coding → Review/Test → Done. Coding trung bình hoàn tất mã nhanh, nhưng 60% thời gian của các work item là chờ Review/Test. Product Owner muốn tăng số Developers.

Hãy đề xuất **hai thí nghiệm hệ thống** có thể thực hiện trong vài tuần và **cặp chỉ số** dùng để đánh giá hiệu quả, ví dụ:

- Developers hỗ trợ review/test trước khi kéo thêm việc mới, so thời gian chờ và tỷ lệ lỗi.
- Tự động hóa bước kiểm thử tích hợp bị nghẽn, so cycle time và độ tin cậy pipeline.

Đáp án cần giải thích vì sao tăng năng lực coding có thể chưa giải quyết nút thắt Review/Test.

### Bài tập F — Kết hợp Scrum

Scrum Team có Sprint Goal “Học viên mở lại đúng bài đang học một cách an toàn”, nhưng có tám PBIs ở trạng thái Doing, ba item chờ kiểm thử và một lỗi phân quyền chưa sửa.

Hãy trình bày một kế hoạch Daily Scrum 15 phút sử dụng tư duy flow mà vẫn giữ:

- Sprint Goal, Sprint Backlog và quyền tự quản của Developers.
- Definition of Done và kiểm thử quyền truy cập.
- Cách phối hợp với Product Owner khi cần thương lượng phạm vi.
- Một hoặc hai thay đổi WIP/chính sách có thể quan sát trong Sprint.

**Gợi ý:** Tập trung đưa item quan trọng về Done, xử lý lỗi bắt buộc, giảm bắt đầu việc mới; không thay Sprint Goal bằng mục tiêu “đóng nhiều thẻ nhất”.

## 21. Checklist: nhóm đang có bảng hay đã quản lý hệ thống?

- [ ] Nhóm biết **dịch vụ/người nhận giá trị** mà workflow đang phục vụ.
- [ ] Thẻ đại diện cho **work item có định nghĩa rõ**, không lẫn nhiệm vụ kỹ thuật với giá trị đã giao.
- [ ] **Start và finish** của luồng được thống nhất; các số đo dùng cùng ranh giới.
- [ ] Bảng phản ánh **các trạng thái và hàng đợi thực tế**, không che bước chờ quan trọng.
- [ ] Có **cơ chế kiểm soát WIP** mà mọi người hiểu và sử dụng.
- [ ] Khi một trạng thái đầy, nhóm biết **nên cùng hoàn tất việc gì** trước khi khởi động thêm.
- [ ] Chính sách **pull, ưu tiên, chuyển trạng thái, blocked, Done và ngoại lệ** được làm rõ.
- [ ] Blocked work không bị giấu khỏi WIP và việc theo dõi tuổi việc nếu vẫn thuộc ranh giới.
- [ ] **Definition of Workflow** bao gồm cả **SLE**, có điều kiện và giới hạn thông tin.
- [ ] Nhóm theo dõi **WIP, throughput, cycle time, work item age** một cách nhất quán.
- [ ] Khi item gần/vượt SLE, có cơ chế **phản ứng chủ động**.
- [ ] Số liệu không bị dùng để xếp hạng cá nhân thiếu bối cảnh.
- [ ] Có những **vòng phản hồi tạo ra quyết định**, không chỉ các buổi đọc trạng thái.
- [ ] Nhóm có thể nêu **một thay đổi workflow gần đây**, lý do và bằng chứng tác động.
- [ ] Cách phân loại việc khẩn có tiêu chí, người quyết định và cách theo dõi hậu quả.
- [ ] Các thay đổi giảm thời gian hoàn tất không bỏ qua **Definition of Done, kiểm thử, bảo mật và chất lượng**.
- [ ] Nếu dùng Scrum, nhóm vẫn bảo vệ **Sprint Goal, Sprint Backlog, Increment** và trách nhiệm Scrum Team.
- [ ] Những điều học từ khách hàng dẫn đến cải tiến ưu tiên/giải pháp, không chỉ tăng số thẻ trên bảng.

## 22. Tài liệu đọc tiếp và tổng kết

- [The Kanban Guide](https://kanbanguides.org/): Definition of Workflow, WIP, bốn thước đo flow, Service Level Expectation và ba nhóm thực hành quản lý Kanban.
- [Kanban University](https://kanban.university/): kiến thức về Kanban Method, chính sách rõ, các lớp dịch vụ, vòng phản hồi và cải tiến tiến hóa.
- [The Scrum Guide](https://scrumguides.org/): các tạo tác, trách nhiệm và sự kiện của Scrum; hữu ích khi kết hợp thực hành Kanban trong Sprint.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/): các giá trị về cộng tác, phần mềm hoạt động, phản hồi sớm và thích ứng.
- Daniel S. Vacanti, *Actionable Agile Metrics for Predictability* (2015): ứng dụng phân bố cycle time, WIP, throughput để cải thiện khả năng dự báo.
- David J. Anderson, *Kanban: Successful Evolutionary Change for Your Technology Business* (2010): cách tiếp cận thay đổi tiến hóa và quản lý dòng công việc trong tổ chức tri thức.

**Điểm cần nhớ:** **Bảng Kanban trả lời công việc đang ở đâu; hệ thống Kanban giúp quyết định công việc nên chảy thế nào để tạo ra giá trị đúng chất lượng, có thể dự báo và liên tục cải tiến.** Một hệ thống thực sự cần *workflow được định nghĩa, WIP được kiểm soát, chính sách rõ, SLE có căn cứ, số đo flow và các vòng phản hồi dẫn tới hành động*. Bảng làm vấn đề hiện ra; **cách nhóm sử dụng thông tin đó để hoàn tất việc và thay đổi hệ thống mới tạo nên năng lực Kanban**.
