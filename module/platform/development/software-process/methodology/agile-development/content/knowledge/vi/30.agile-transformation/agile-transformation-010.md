# Duy trì học hỏi để tránh biến chuyển đổi thành một chương trình có điểm kết thúc hình thức

Một doanh nghiệp công bố hoàn thành chương trình chuyển đổi Agile sau mười hai tháng. Hơn 90% nhân viên đã dự khóa đào tạo, các nhóm đều có bảng công việc, tổ chức Sprint Planning và Daily Scrum, báo cáo cho thấy “mức độ áp dụng Agile” tăng. Ban chuyển đổi bàn giao tài liệu và tuyên bố dự án thành công.

Sáu tháng sau, Product Backlog lại bị nhiều quản lý giao việc trực tiếp, Sprint Review chủ yếu là trình diễn slide, kiểm thử tích hợp dồn về cuối và lỗi sản xuất tăng. Các nhóm vẫn họp đều nhưng **không còn cơ chế đủ mạnh để nhận phản hồi, thử thay đổi và sửa chính cách tổ chức của mình**.

Vấn đề không phải chương trình chuyển đổi có một ngày kết thúc về mặt ngân sách. Vấn đề là tổ chức đã nhầm **hoàn tất hoạt động triển khai** với **hình thành năng lực học hỏi bền vững**.

Trong chương **Chuyển đổi Agile** thuộc mô-đun **AGILE_DEVELOPMENT**, bài này tập trung vào cách duy trì các giá trị Agile sau giai đoạn thí điểm và mở rộng: **phản hồi sớm, giao sản phẩm tăng dần, cải tiến liên tục**, thực hành user story, Product Backlog, Scrum, Kanban, XP và đo lường dòng công việc theo nhu cầu thực tế. Mục tiêu không phải biến “chuyển đổi” thành một dự án vô hạn, mà là **chuyển trách nhiệm học hỏi từ chương trình tạm thời sang cách điều hành sản phẩm và công việc hằng ngày**.

**Sau bài học, bạn có thể:**

- Phân biệt **đầu ra của chương trình chuyển đổi**, **năng lực tổ chức** và **kết quả người dùng**.
- Giải thích tại sao có thể **kết thúc chương trình chuyển đổi hữu hạn** mà vẫn duy trì **cải tiến liên tục**.
- Thiết kế các vòng học ở cấp **nhóm, sản phẩm, dòng giá trị và tổ chức** với quyền quyết định rõ.
- Đưa cải tiến kỹ thuật, sản phẩm, quy trình và chính sách vào **công việc có chủ sở hữu và được kiểm chứng**.
- Dùng Scrum, Kanban, XP và các nguyên tắc Lean để duy trì phản hồi và thích ứng mà không tạo thêm nghi thức rỗng.
- Chọn thước đo **outcome, chất lượng, flow, độ tin cậy và nhịp bền vững**, tránh xếp hạng nhóm bằng velocity hoặc “điểm trưởng thành Agile”.
- Nhận biết các dấu hiệu thoái lui: **ưu tiên bị áp đặt, làm lại tăng, báo cáo đẹp nhưng thiếu giá trị, phụ thuộc cá nhân và thiếu thời gian cải tiến**.
- Thiết kế cách **bàn giao trách nhiệm, nguồn lực, điều kiện dừng và cơ chế xem lại** khi một bộ phận chuyển đổi tạm thời giải thể.
- Thực hành viết giả thuyết, phân tích case study và lập kế hoạch duy trì học hỏi qua nhiều vòng.

## 1. Chuyển đổi Agile là thay đổi năng lực, không chỉ đổi hình thức

Agile không phải bộ nhãn áp lên những hoạt động cũ. Một nhóm có thể gọi giai đoạn làm việc là Sprint nhưng vẫn nhận một kế hoạch cố định từ cấp trên, không nói chuyện với người dùng và chỉ kiểm thử khi sắp bàn giao. Việc đổi tên **không tự tạo ra khả năng thích ứng**.

### Ba cấp kết quả cần tách bạch

| Cấp | Ví dụ | Nó chứng minh gì? | Chưa chứng minh gì? |
| --- | --- | --- | --- |
| **Hoạt động triển khai** | Đào tạo Agile, mở bảng Kanban, phân công Scrum accountabilities | Một số bước tổ chức đã diễn ra | Sản phẩm hoặc cách làm đã tốt hơn |
| **Năng lực vận hành** | Nhóm có thể chọn lát cắt, tạo Increment đạt DoD, đo flow, phản hồi và cải tiến | Cơ chế học và giao phần mềm bắt đầu tồn tại | Người dùng đã nhận tác động mong đợi |
| **Kết quả sản phẩm/hệ thống** | Thời gian tới phản hồi giảm, lỗi nghiêm trọng giảm, người học tiếp tục học thuận lợi hơn | Có tín hiệu về kết quả cần tạo | Quan hệ nhân quả chắc chắn nếu chỉ so trước/sau |

Một báo cáo trưởng thành nên nói:

> “Chúng ta đã tạo được những cơ chế học hỏi nào, bằng chứng nào cho thấy chúng có ích, rủi ro nào còn tồn tại và ai chịu trách nhiệm duy trì chúng?”

Thay vì chỉ:

> “Bao nhiêu nhóm đã được chuyển đổi sang Scrum?”

### Chuyển đổi không nhất thiết là mục tiêu tự thân

Mục tiêu tổ chức có thể là **tăng khả năng giao giá trị an toàn và thích ứng khi thị trường, công nghệ hoặc người dùng thay đổi**. Scrum, Kanban và XP là những cách tiếp cận hoặc thực hành có thể hỗ trợ mục tiêu này. Tổ chức không cần nhân bản cùng một hình thức làm việc cho mọi dòng công việc.

## 2. Kết thúc chương trình hữu hạn khác dừng cải tiến liên tục

Một chương trình chuyển đổi có thể có **ngân sách, nhóm triển khai, ngày bắt đầu và ngày bàn giao**. Điều đó bình thường. Vấn đề là **ai sở hữu năng lực học và sửa hệ thống sau khi chương trình kết thúc**.

### Hai kiểu “kết thúc” rất khác nhau

| Kết thúc hình thức | Kết thúc chuyển tiếp có trách nhiệm |
| --- | --- |
| Đếm số đội học xong và tuyên bố hoàn tất | Xác nhận cơ chế nào vận hành được khi không còn chương trình hỗ trợ |
| Bàn giao một bộ slide hướng dẫn | Bàn giao quyền, người chịu trách nhiệm, dữ liệu và cách xem lại |
| Dừng coaching, dừng chia sẻ bài học, không có năng lực cải tiến | Chuyển hỗ trợ vào cộng đồng thực hành, quản lý sản phẩm, kỹ thuật và lãnh đạo tuyến |
| KPI duy nhất là số Scrum event được tổ chức | Có chỉ số outcome, flow, chất lượng và guardrail với định nghĩa ổn định |
| Không ai sửa rào cản ngân sách/phê duyệt nữa | Có đường phản hồi để thay đổi chính sách khi nó cản tạo giá trị |
| Coi mô hình đã chọn là bất biến | Có quyền và thời điểm xem mô hình còn phù hợp không |

**Một tổ chức không cần “ban chuyển đổi Agile vĩnh viễn”**. Nó cần những người đang điều hành sản phẩm và phát triển phần mềm có **trách nhiệm và năng lực tiếp tục học hỏi**.

### Tiêu chí bàn giao nên dựa trên năng lực

Một phần việc chuyển đổi có thể được bàn giao khi:

1. **Ai chịu trách nhiệm giá trị sản phẩm** và thứ tự ưu tiên đã rõ.
2. **Ai chịu trách nhiệm chất lượng và Increment** đã rõ.
3. Nhóm có thể **quan sát dòng công việc và xử lý blocker** mà không cần bộ phận chuyển đổi làm thay.
4. Các sự kiện/hình thức phối hợp tạo **quyết định và phản hồi thật**.
5. Có cách đưa **bài học và sự cố** vào lựa chọn công việc kế tiếp.
6. Rào cản ngoài nhóm có **người có quyền giải quyết**.
7. Có thời gian và nguồn lực để tiếp tục **nâng chất lượng kỹ thuật, hỗ trợ, học và cải tiến**.

Không cần mọi vấn đề đều được giải quyết trước bàn giao. Nhưng **vấn đề chưa giải quyết phải có chủ sở hữu, đường xử lý và cách kiểm chứng**, không được biến mất khỏi báo cáo.

## 3. Đơn vị cần duy trì là vòng học hỏi, không phải danh sách nghi thức

Một vòng học hữu ích bắt đầu bằng một vấn đề có ý nghĩa, thử một điều có thể kiểm chứng và dùng kết quả để quyết định tiếp.

~~~mermaid
flowchart TD
    A["Quan sát vấn đề / cơ hội"] --> B["Nêu giả thuyết và rủi ro"]
    B --> C["Chọn lát cắt hoặc thay đổi nhỏ"]
    C --> D["Thực hiện với chất lượng và guardrails"]
    D --> E["Đo kết quả / lấy phản hồi"]
    E --> F["Diễn giải bằng chứng và giới hạn"]
    F --> G{"Quyết định tiếp theo"}
    G -->|"Giữ / mở rộng"| H["Chuẩn hóa điều có ích"]
    G -->|"Sửa / thử tiếp"| B
    G -->|"Dừng"| I["Ghi bài học, giải phóng năng lực"]
    H --> A
    I --> A
~~~

### Vòng học có thể tạo ba loại kết quả

- **Xác nhận:** Bằng chứng phù hợp với giả thuyết, guardrails đạt; có thể giữ hoặc mở rộng có điều kiện.
- **Điều chỉnh:** Một phần cơ chế hoạt động nhưng còn điểm mù, dữ liệu thiếu hoặc tác dụng phụ cần khắc phục.
- **Bác bỏ/dừng:** Giả thuyết chưa được ủng hộ hoặc chi phí/rủi ro vượt giá trị; dừng là một quyết định hữu ích nếu giúp tránh đầu tư sai.

**“Chúng ta đã học” không đủ nếu chẳng có gì thay đổi.** Một vòng học hoàn tất khi có **quyết định dựa trên bằng chứng**: cập nhật Product Backlog, sửa quy trình, cải thiện test, đổi ranh giới nhóm, điều chỉnh chính sách hoặc dừng một giả thuyết.

### Điều kiện để vòng học tiếp diễn

1. **Có tín hiệu được nhìn thấy:** Dữ liệu, sự cố, ý kiến người dùng và phản hồi người làm việc.
2. **Có chỗ thảo luận phù hợp:** Câu hỏi được đưa tới đúng người có trách nhiệm.
3. **Có quyền hành động:** Nhóm có thể đổi cách làm trong ràng buộc chất lượng; Product Owner có thể sắp thứ tự; lãnh đạo xử lý rào cản tổ chức.
4. **Có năng lực và thời gian:** Không bị lấp kín bởi công việc khẩn hoặc mục tiêu ngắn hạn tới mức mọi cải tiến đều bị hoãn.
5. **Có kiểm chứng:** Thay đổi được quan sát qua đủ vòng, không tự công bố thành công.

## 4. Ba dạng học hỏi không nên bị trộn lẫn

Một dashboard có thể cho thấy cycle time giảm, nhưng không trả lời người dùng có hài lòng hơn hay đội có đang làm thêm giờ không. Cần phân biệt các góc nhìn:

| Dạng học hỏi | Câu hỏi | Tín hiệu gợi ý | Ai cần tham gia? |
| --- | --- | --- | --- |
| **Sản phẩm/giá trị** | Chúng ta có đang giải quyết đúng vấn đề? | Outcome người dùng, task success, retention có ngữ cảnh | Product Owner, Scrum Team, stakeholder, người dùng |
| **Kỹ thuật/dòng công việc** | Có giao Increment đúng và an toàn với vòng phản hồi ngắn? | DoD, WIP, cycle time, Work Item Age, CI, lỗi, reliability | Developers, người kiểm thử, vận hành và người liên quan |
| **Hệ thống tổ chức** | Cơ cấu, quyền và chính sách có cản giá trị hoặc sự bền vững? | Thời gian chờ quyết định, phụ thuộc, tải on-call, xung đột ưu tiên | Lãnh đạo, Product Owner, nhóm và các chức năng hỗ trợ |

### Ví dụ về sự nhầm lẫn

Giả sử việc phát triển tính năng tiếp tục học nhanh hơn, nhưng học viên vẫn bỏ bài nhiều:

- Có thể **cách phát triển đã cải thiện**, nhưng **giả thuyết nhu cầu chưa đúng**.
- Có thể tỷ lệ dùng thấp vì **chưa có exposure đủ**, không phải tính năng không có giá trị.
- Có thể outcome cải thiện nhưng **lỗi mất dữ liệu tăng**; đó không phải thành công toàn diện.
- Có thể đội đạt mục tiêu nhờ **làm ngoài giờ liên tục**; cách làm chưa bền vững.

Một văn hóa học hỏi trưởng thành có thể giữ điều tốt ở một cấp và **sửa điều chưa tốt ở cấp khác**, thay vì tuyên bố tất cả thành công hoặc tất cả thất bại theo một con số.

## 5. Giữ Product Goal và phản hồi người dùng làm điểm tựa

Khi bộ phận chuyển đổi tạm thời rút đi, các nhóm rất dễ quay về mô hình **nhận task theo phòng ban**. Vì vậy, cần duy trì một đường nối rõ giữa công việc hằng ngày và giá trị người dùng.

### Chuỗi quyết định cần được nhìn thấy

~~~text
Product Goal
  -> Vấn đề/người dùng mục tiêu
  -> Product Backlog có thứ tự
  -> Lát cắt hoặc giả thuyết ưu tiên
  -> Increment đạt Definition of Done
  -> Phát hành có kiểm soát khi phù hợp
  -> Tiếp xúc và sử dụng thực
  -> Outcome/quality/guardrails
  -> Điều chỉnh Product Backlog
~~~

### Product Owner không chỉ là người viết ticket

Theo Scrum Guide 2020, **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog. Nếu sau chương trình chuyển đổi, một hội đồng hoặc nhiều cấp quản lý lại **phân công song song các ưu tiên đối kháng** mà Product Owner không thể thực hiện trách nhiệm này, Scrum Team dễ trở về trạng thái hoàn thành đầu việc nhưng thiếu hướng sản phẩm.

Product Owner không phải người tự quyết mọi chi tiết kỹ thuật: **Developers chịu trách nhiệm lập kế hoạch và tạo Increment đáp ứng DoD**. Trách nhiệm được phân biệt để quyền thay đổi nằm gần thông tin cần thiết.

### Phản hồi người dùng không chỉ ở Sprint Review

**Sprint Review** là một cơ hội kiểm tra Increment cùng stakeholder và thích ứng Product Backlog. Nhưng Increment đáp ứng DoD **có thể được phát hành trước Sprint Review**, và việc quan sát sản phẩm không bắt buộc đợi cuối Sprint.

Tương tự, một outcome cần **bảy hoặc 28 ngày** quan sát có thể tiếp tục theo dõi qua nhiều Sprint. Không được rút ngắn cửa sổ đo chỉ để “có số kịp buổi báo cáo”.

## 6. Scrum: giữ vòng kiểm tra và thích ứng chứ không giữ cuộc họp cho đủ lịch

Scrum có những **accountabilities, events, artifacts và commitments** nhằm tăng minh bạch, kiểm tra và thích ứng. Trong Scrum Guide 2020, Sprint là container cho Sprint Planning, Daily Scrum, Sprint Review và Sprint Retrospective.

| Scrum event | Điều cần duy trì sau chuyển đổi | Dấu hiệu thoái lui |
| --- | --- | --- |
| **Sprint Planning** | Scrum Team hiểu vì sao Sprint có giá trị, chọn phạm vi và Developers lập kế hoạch | Product Owner/cấp quản lý chỉ giao danh sách task |
| **Daily Scrum** | Developers kiểm tra tiến độ hướng Sprint Goal và điều chỉnh Sprint Backlog | Đọc báo cáo tình trạng cho quản lý |
| **Sprint Review** | Kiểm tra kết quả sản phẩm với stakeholder, dùng phản hồi để thích ứng | Trình diễn slide và xin đóng dấu hoàn tất |
| **Sprint Retrospective** | Lập kế hoạch cải thiện chất lượng/hiệu quả và xem lại kết quả cải tiến | Mỗi Sprint viết danh sách việc tốt/việc xấu nhưng không ai theo |

### Commitments giúp giữ trục đánh giá

- **Product Goal** là commitment của Product Backlog.
- **Sprint Goal** là commitment của Sprint Backlog.
- **Definition of Done** là commitment của Increment.

Các commitment này giúp nhóm nhận diện **mục tiêu, kế hoạch và chất lượng thực**, không thay thế bằng tỷ lệ hoàn tất checklist.

### Retrospective có thể thoái hóa như thế nào?

Sau khi chương trình chuyển đổi kết thúc, Retrospective vẫn diễn ra nhưng các hành động “tự động hóa kiểm thử”, “giảm phụ thuộc một chuyên gia”, “rút ngắn chờ môi trường” liên tục được ghi lại rồi không bao giờ được thực hiện.

Để phục hồi vòng học:

1. Xem lại **một hoặc hai hành động cũ** trước khi tạo hàng loạt đề xuất mới.
2. Phân biệt việc nhóm tự giải quyết được với **rào cản cần lãnh đạo hoặc bộ phận khác hỗ trợ**.
3. Đặt **giả thuyết và tín hiệu kiểm chứng**, không chỉ “cải thiện giao tiếp”.
4. Bảo vệ năng lực thực hiện cải tiến và kiểm tra nó trong Sprint sau.
5. Nếu một thử nghiệm không hiệu quả, **ghi lý do và chọn điều chỉnh/dừng**, không để tồn tại vô hạn.

### Không áp dụng Scrum bằng cưỡng chế cho mọi dòng việc

Nhóm hỗ trợ sự cố liên tục có thể phù hợp với **Kanban** để quản lý Work in Progress và nhu cầu đến ngẫu nhiên, kết hợp các thực hành kỹ thuật/phản hồi có ích. Giữ học hỏi nghĩa là **xem phương pháp còn phục vụ loại công việc hay không**, không coi mọi đội không dùng Sprint là thất bại chuyển đổi.

## 7. Kanban: cải tiến dòng công việc qua dữ liệu thật

Kanban tạo cơ hội kiểm tra hệ thống bằng cách **trực quan hóa workflow, giới hạn WIP, nêu chính sách rõ, quản lý dòng công việc và cải tiến**.

Bốn phép đo dòng công việc quan trọng:

| Thước đo | Ý nghĩa | Cách giúp duy trì học hỏi |
| --- | --- | --- |
| **WIP** | Số hạng mục đã bắt đầu nhưng chưa hoàn thành | Nhìn quá tải và tồn kho công việc |
| **Throughput** | Số hạng mục hoàn thành trong một khoảng theo cùng đơn vị | Nhìn năng lực hoàn tất, không chỉ bắt đầu |
| **Cycle time** | Thời gian từ Started tới Finished theo workflow được định nghĩa | Nhìn phân phối thời gian giao |
| **Work Item Age** | Thời gian một hạng mục đang mở đã tồn tại kể từ Started | Phát hiện việc mắc kẹt trước khi hoàn thành |

### Ví dụ bị che khuất bởi một dashboard đẹp

Nhóm báo cycle time trung bình của các story **đã Done** từ 8 ngày xuống 5 ngày. Nhưng ba story khó nhất đã mở hơn 25 ngày và vẫn nằm ở bước kiểm thử tích hợp. Nếu chỉ nhìn việc đã Done, đội có thể cho rằng mình đang cải tiến.

**Work Item Age, WIP và trạng thái blocked** phải được quan sát cùng cycle time của những việc hoàn thành. Điều này đặc biệt quan trọng khi chương trình chuyển đổi không còn người ngoài đến nhắc nhóm nhìn nút thắt.

### Cải tiến không bằng cách đổi định nghĩa

Nếu một nhóm đổi “Started” từ lúc nhận công việc sang lúc bắt đầu code, cycle time có thể giảm ngay dù thời gian chờ của người dùng không đổi. Nếu ticket được chia nhỏ hơn nhưng vẫn cần nhiều ticket để có một Increment, throughput có thể tăng về số lượng mà **thời gian tới giá trị chưa giảm**.

Khi xem số liệu, hãy ghi **ranh giới, loại hạng mục, thời gian quan sát và mọi thay đổi cách đếm**.

## 8. XP: giữ khả năng thay đổi nhờ chất lượng kỹ thuật

Một tổ chức có nhiều hội thoại Agile nhưng **kiểm thử yếu, tích hợp chậm và thiết kế khó thay đổi** có thể không duy trì được vòng lặp phản hồi nhanh. Những thực hành thuộc Extreme Programming (XP) giúp tạo nền tảng kỹ thuật:

| Thực hành | Năng lực học hỏi được bảo vệ | Kiểm chứng thực tế |
| --- | --- | --- |
| **Test-Driven Development (TDD)** | Phản hồi nhanh về hành vi khi thay đổi mã | Test có ý nghĩa, lỗi hồi quy và khả năng refactor |
| **Behavior-Driven Development / ví dụ nghiệp vụ** | Giảm hiểu sai giữa nghiệp vụ–phát triển–kiểm thử | Ví dụ chấp nhận được kiểm chứng |
| **Continuous Integration (CI)** | Phát hiện lỗi tích hợp khi thay đổi còn nhỏ | Build/test phản hồi nhanh, ít lỗi tích lũy |
| **Refactoring** | Giữ mã dễ thích ứng khi kiến thức thay đổi | Chi phí thay đổi và rủi ro hồi quy phù hợp |
| **Pair programming / chia sẻ hiểu biết** | Bớt phụ thuộc một người, tăng phản biện kỹ thuật | Giảm blocker và kiến thức tập trung |
| **Small releases** | Thu nhận phản hồi sớm, giảm quy mô tác động | Time to feedback, sự cố, khả năng phục hồi |

**Không nên biến kỹ thuật thành checklist mới**: “100% code coverage” không chứng minh mọi hành vi đúng; “CI xanh” chỉ chứng minh các kiểm tra đang chạy đạt; số lần deploy nhiều chưa chứng minh người dùng nhận giá trị.

### Một rủi ro sau chuyển đổi

Trong giai đoạn rollout, tổ chức đầu tư thiết lập CI và bộ test. Sau đó, ngân sách dành cho cải tiến kỹ thuật bị cắt vì “Agile đã xong”. Pipeline ngày càng chậm, test không ổn định, nhiều cảnh báo bị bỏ qua và Developers ngại refactor.

Muốn giữ vòng học, phải duy trì **năng lực và trách nhiệm bảo trì hệ thống phản hồi kỹ thuật**, không xem khoản đầu tư chất lượng là “chi phí thiết lập một lần”.

## 9. Lean: nhìn toàn bộ dòng giá trị, không chỉ tốc độ của một nhóm

Học hỏi ở quy mô tổ chức phải xét **từ nhu cầu người dùng đến giá trị được sử dụng**, không chỉ thời gian Developers viết code. Một vấn đề có thể nằm ở chờ ưu tiên, handoff, môi trường, phê duyệt, tích hợp hoặc chờ phát hành.

### Bản đồ dòng giá trị có ích hơn sơ đồ nghi thức

~~~mermaid
flowchart LR
    A["Nhu cầu / tín hiệu người dùng"] --> B["Quyết định ưu tiên"]
    B --> C["Làm rõ và phát triển lát cắt"]
    C --> D["Tích hợp / đạt DoD"]
    D --> E["Phát hành và tiếp xúc"]
    E --> F["Sử dụng và outcome"]
    F --> G["Điều chỉnh Product Backlog"]
    G --> B
~~~

### Ví dụ thời gian giả định

Một lát cắt có giá trị mất:

| Bước | Thời gian xử lý | Thời gian chờ |
| --- | ---: | ---: |
| Xác định nhu cầu và ví dụ | 2 ngày | 3 ngày |
| Phát triển và kiểm thử gần mã | 4 ngày | 2 ngày |
| Tích hợp end-to-end | 2 ngày | 5 ngày |
| Phát hành có kiểm soát | 1 ngày | 1 ngày |
| **Tổng** | **9 ngày** | **11 ngày** |

Theo giả định các bước đi tuần tự, lead time từ nhu cầu đã xác định tới phát hành là **20 ngày lịch**; **11 ngày là thời gian chờ**. Rút một ngày xử lý có thể ít ảnh hưởng hơn việc giảm năm ngày chờ tích hợp.

**Không mặc định mọi thời gian chờ là lãng phí:** kiểm soát bảo mật, xử lý dữ liệu và cửa sổ quan sát hợp lý có thể cần thiết. Hãy hỏi **nó phục vụ rủi ro nào, có thể làm sớm hoặc tự động hóa điều gì và người dùng nhận được gì**.

### Vì sao cải tiến liên tục cần ranh giới toàn luồng?

Sau chương trình chuyển đổi, mỗi nhóm có thể tối ưu “tỷ lệ Done” cục bộ và đẩy việc chờ sang nhóm khác. Kết quả là các dashboard vẫn xanh trong khi **time to value của người dùng không đổi**.

Các hành động duy trì học hỏi gồm:

- Xác định **điểm bắt đầu/kết thúc đo** nhất quán theo hành trình có giá trị.
- Xem **thời gian chờ và công việc đang già đi** ở ranh giới nhiều nhóm.
- Kiểm chứng **Increment tích hợp**, không cộng task rời rạc thành giá trị.
- Có diễn đàn giải quyết **nút thắt ngoài quyền một nhóm**, với người có thẩm quyền thực.

## 10. Tạo một “learning backlog” đủ nhẹ để cải tiến không biến mất

Khi nhóm phát hiện vấn đề, ý tưởng cải tiến thường nằm trong biên bản Retrospective, tin nhắn riêng hoặc một bảng theo dõi không ai mở. Để duy trì học hỏi, cần biến vấn đề đáng giải quyết thành **thay đổi có quyền sở hữu và được xem lại**.

Có thể gọi đây là **danh sách giả thuyết cải tiến** hoặc *learning backlog*. Đây là **một công cụ tùy chọn**, không phải artifact chính thức của Scrum và **không thay thế Product Backlog**.

### Phân loại đúng nơi cần ra quyết định

| Vấn đề | Nơi theo dõi thường phù hợp | Trách nhiệm |
| --- | --- | --- |
| Người học không hiểu trạng thái lưu | Product Backlog và nghiên cứu sản phẩm | Product Owner cân nhắc giá trị; Developers làm rõ cách thực hiện |
| CI chậm khiến mọi PR chờ | Công việc cải tiến kỹ thuật nhìn thấy trong kế hoạch của nhóm/sản phẩm | Developers và người hỗ trợ hạ tầng |
| Nhiều story mắc ở kiểm thử tích hợp | Chính sách workflow/cải tiến tại nhóm hoặc dòng giá trị | Những người sở hữu quy trình và năng lực tích hợp |
| Hai cấp lãnh đạo giao ưu tiên trái nhau | Rào cản chính sách/quản trị có người chịu trách nhiệm | Lãnh đạo có thẩm quyền, phối hợp với Product Owner |
| Nhóm mới không biết làm refinement | Hỗ trợ coaching/đào tạo theo nhu cầu | Người phụ trách phát triển năng lực, nhóm tự áp dụng |
| Lỗi truy cập dữ liệu nghiêm trọng | Quy trình xử lý sự cố và bảo mật | Vai trò ứng phó theo chính sách; không đợi refinement thường kỳ |

**Không tạo một “backlog cải tiến của ban Agile”** rồi đòi mọi việc đều phải gửi sang đó. Nhóm nên giải quyết việc họ đủ quyền và năng lực xử lý; chỉ nâng cấp **phụ thuộc và rào cản thực sự ngoài phạm vi**.

### Thẻ thử nghiệm cải tiến nên có gì?

~~~text
VẤN ĐỀ:
  Nhiều PBI có Work Item Age cao vì chờ review và tích hợp.

QUAN SÁT / BASELINE:
  Trong nhóm việc tương tự, p85 cycle time dài,
  hàng đợi test có nhiều hạng mục quá ngưỡng kỳ vọng.

GIẢ THUYẾT:
  Giới hạn WIP ở bước phát triển và review sớm
  sẽ giảm thời gian chờ mà không tăng lỗi hồi quy.

THAY ĐỔI NHỎ:
  Áp dụng chính sách kéo việc mới sau khi hỗ trợ
  hạng mục gần Done, trong hai Sprint.

NGƯỜI CHỊU TRÁCH NHIỆM:
  Developers cùng người phụ trách hỗ trợ test/CI.

TÍN HIỆU:
  Work Item Age, phân phối cycle time, throughput,
  lỗi hậu phát hành và tải trực.

GUARDRAILS:
  Không bỏ DoD, không đẩy việc chờ ra khỏi bảng,
  không tăng làm thêm giờ.

XEM LẠI:
  Sau khi có đủ hạng mục đi qua workflow mới.

QUYẾT ĐỊNH:
  Giữ / sửa / dừng với lý do và điều còn bất định.
~~~

### Giới hạn WIP của cả việc cải tiến

Nếu nhóm khởi động **mười lăm thử nghiệm quy trình cùng lúc**, gần như không thể biết điều gì đã có tác dụng, đồng thời mất năng lực phát triển sản phẩm. Chỉ nên chọn **một vài thử nghiệm ưu tiên**, hoàn tất vòng học rồi mới mở thêm theo khả năng.

## 11. Phân biệt việc cần làm, giả thuyết và quyết định đã có bằng chứng

Một vấn đề phổ biến sau chuyển đổi là **mọi cuộc họp đều tạo action items, nhưng hiếm khi kết luận điều đã học**.

### Bốn trạng thái không nên trộn

| Loại | Ví dụ | Điều còn thiếu |
| --- | --- | --- |
| **Quan sát** | Ba PBI bị chặn khi chờ môi trường | Chưa biết nguyên nhân gốc |
| **Giả thuyết** | Môi trường dùng chung khiến các nhóm xếp hàng | Cần kiểm chứng bằng dữ liệu và người làm việc |
| **Thử nghiệm** | Tạo môi trường tích hợp tạm theo mẫu để giảm chờ | Chưa có kết quả |
| **Kết luận có điều kiện** | Với một loại PBI, blocked time giảm và lỗi không tăng | Cần xem tính lặp lại, loại việc và giới hạn |

**“Action completed” không đồng nghĩa “learning completed”.** Việc tạo môi trường mới chỉ chứng minh hạng mục đã triển khai; phải kiểm tra **tốc độ tích hợp và rủi ro** mới biết giải pháp có ích.

### Bản ghi quyết định ngắn

~~~text
MÃ:
  LEARN-07 (minh họa)

VẤN ĐỀ:
  Kiểm thử end-to-end phải chờ một môi trường dùng chung.

LỰA CHỌN:
  A. Cấp môi trường test độc lập theo nhu cầu.
  B. Tăng lịch đặt chỗ môi trường dùng chung.
  C. Giảm phụ thuộc môi trường bằng contract tests.

ĐIỀU ĐÃ THỬ:
  C cho ranh giới API phù hợp, kết hợp cải thiện dữ liệu mẫu.

BẰNG CHỨNG:
  Blocked time theo cùng loại PBI; lỗi hợp đồng và
  chi phí duy trì môi trường qua những chu kỳ đủ quan sát.

QUYẾT ĐỊNH:
  Giữ C trong phạm vi đã thử, tiếp tục đánh giá
  trường hợp bắt buộc kiểm thử trên môi trường chung.

GIỚI HẠN:
  Chưa đủ dữ liệu cho migration dữ liệu lớn.

LẦN XEM LẠI:
  Khi workflow hoặc kiến trúc thay đổi đáng kể.
~~~

Không cần lưu tất cả ý kiến thành một hồ sơ đồ sộ. Giá trị của decision log là **người đến sau hiểu vì sao một lựa chọn được đưa ra và điều kiện khiến nó cần thay đổi**.

## 12. Thiết lập nhịp kiểm tra ở nhiều cấp nhưng không nhân bản báo cáo

Một tổ chức lớn thường có các cấp **team, sản phẩm, dòng giá trị và chiến lược**. Mỗi cấp có một loại câu hỏi khác nhau; không nên cùng xem lại bảng ticket ở bốn cuộc họp.

| Cấp | Cần kiểm tra điều gì? | Phản hồi phù hợp |
| --- | --- | --- |
| **Trong nhóm** | Sprint Goal, blockers, DoD, CI, Work Item Age, cải tiến đang thử | Điều chỉnh kế hoạch hoặc kỹ thuật |
| **Sản phẩm** | Product Goal, Increment, phản hồi người dùng, outcome | Điều chỉnh Product Backlog, giả thuyết và đầu tư |
| **Dòng giá trị nhiều nhóm** | Hàng đợi, tích hợp, phụ thuộc, độ tin cậy xuyên ranh giới | Thay chính sách, hợp đồng hoặc cấu trúc phối hợp |
| **Lãnh đạo/tổ chức** | Phân quyền, ngân sách, rủi ro, năng lực bền vững | Thay điều kiện tổ chức và định hướng đầu tư |

### Không “đẩy lên trên” mọi quyết định

**Quyết định càng gần người có thông tin và có trách nhiệm phù hợp, phản hồi thường càng nhanh.** Nếu một nhóm muốn cải thiện cách code review ít rủi ro mà vẫn phải chờ cuộc họp chương trình hằng tháng, tổ chức chưa chuyển năng lực học hỏi vào nơi thực hiện công việc.

Ngược lại, một thay đổi **phân quyền truy cập, tuân thủ hoặc cấu trúc ngân sách** có thể cần sự tham gia của người được giao quyền cụ thể. Tự quản **không phải bỏ qua ranh giới an toàn**.

### Mẫu nhịp xem lại có thể tùy chỉnh

- **Trong ngày:** CI, sự cố, impediment cần xử lý sớm.
- **Theo Sprint hoặc chu kỳ ngắn:** Cách làm nhóm, chất lượng, Increment, phản hồi stakeholder.
- **Theo cửa sổ outcome:** Cohort đủ thời gian quan sát và quyết định sản phẩm.
- **Theo chu kỳ chiến lược:** Product Goal, năng lực, cấu trúc nhóm, đầu tư và chính sách.

Đây là ví dụ chứ **không phải quy định mọi tổ chức phải tạo thêm bốn loại meeting**. Hãy dùng dữ liệu chia sẻ không đồng bộ khi có thể và dành thảo luận trực tiếp cho **quyết định, bất đồng hoặc rào cản**.

## 13. Tài trợ cải tiến như một năng lực liên tục

Sau chương trình chuyển đổi, tổ chức có thể nói “từ nay đội tự cải tiến”, nhưng đồng thời **xếp toàn bộ năng lực vào các dự án đã cam kết**, không dành chỗ cho CI, giảm nợ kỹ thuật, nghiên cứu người dùng hay xử lý nguyên nhân sự cố. Khi đó cải tiến có thể chỉ tồn tại trên biên bản.

### Cách nhìn năng lực thay vì quỹ “Agile”

Một tổ chức cần tiếp tục đầu tư hợp lý vào:

- **Cải tiến sản phẩm:** nghiên cứu, kiểm chứng giả thuyết và đo outcome.
- **Năng lực kỹ thuật:** test, CI/CD, khả năng phục hồi, bảo mật, giảm phụ thuộc.
- **Cải tiến dòng công việc:** làm rõ yêu cầu, WIP, quyết định và tích hợp.
- **Phát triển con người:** mentoring, coaching theo nhu cầu, chia sẻ kỹ năng và đào tạo đúng thời điểm.
- **Chất lượng vận hành:** quan sát, xử lý sự cố và phòng ngừa lỗi lặp.

### Không có tỷ lệ thời gian cố định cho mọi nhóm

Một số đội có thể chọn một phần năng lực cho cải tiến; đội khác tích hợp refactoring/test ngay trong mỗi PBI. **Không có tỷ lệ phần trăm chuẩn của Agile** áp dụng cho mọi hoàn cảnh.

Điều cần kiểm tra là:

1. Công việc cải tiến quan trọng **có thể được ưu tiên thực sự** không?
2. **Thời gian chờ, lỗi, phụ thuộc và sự cố lặp** có giảm qua nhiều vòng không?
3. Cách phân bổ năng lực có khiến nhóm **làm ngoài giờ liên tục** không?
4. Những lựa chọn đầu tư có được **đánh giá giá trị và chi phí cơ hội** không?

### Vì sao ngân sách chỉ theo dự án có thể tạo vấn đề?

Nếu toàn bộ năng lực của một nhóm bị khóa vào danh sách tính năng cam kết đầu năm, khi người dùng phản hồi một giả thuyết sai, nhóm có thể không có quyền chuyển hướng. Cần xem lại **cách tài trợ sản phẩm/dòng giá trị và cơ chế thay đổi ưu tiên**, nhưng không nên tuyên bố chỉ có một mô hình ngân sách đúng cho mọi tổ chức.

## 14. Vai trò lãnh đạo sau chương trình chuyển đổi

Lãnh đạo không chỉ tài trợ khóa học hay tuyên bố “mọi người được trao quyền”. Họ cần **thay đổi cách ra quyết định và quản trị rủi ro** để việc kiểm tra–thích ứng thực sự khả thi.

### Những điều lãnh đạo cần duy trì

| Hành động | Cơ chế giúp học hỏi | Dấu hiệu thoái lui |
| --- | --- | --- |
| **Định hướng kết quả** | Nhóm có mục tiêu người dùng thay vì danh sách lệnh | Chỉ hỏi bao nhiêu ticket và giờ công |
| **Quyền quyết định rõ** | Product Owner quản lý thứ tự, Developers tự quản thực hiện | Nhiều người giao ưu tiên trực tiếp, không chịu trade-off |
| **Phản hồi về rào cản tổ chức** | Blocker ngoài team có người xử lý | “Đây là vấn đề nhóm phải tự lo” dù nhóm không có quyền |
| **Chất lượng không thỏa hiệp** | Không tăng tốc bằng việc bỏ DoD hoặc kiểm soát dữ liệu | Ép release dù có lỗi nghiêm trọng |
| **Khuyến khích báo sự cố** | Phát hiện và học sớm, không giấu lỗi | Trừng phạt người đưa tin xấu |
| **Đầu tư dài hạn** | Duy trì CI, test, mentoring và khả năng thích ứng | Cắt toàn bộ năng lực cải tiến sau “go-live Agile” |
| **Xem lại chính sách** | Giảm cấp phê duyệt không cần thiết | Đo lead time nhưng giữ nguyên hàng chờ thủ tục |

### Một câu hỏi quản lý nên hỏi

> “Điều gì đang làm đội không thể giao một lát cắt có giá trị và nhận phản hồi an toàn sớm hơn? Trong những điều đó, tôi có quyền thay đổi phần nào?”

Câu hỏi này thường hữu ích hơn:

> “Vì sao Sprint này đội không tăng velocity?”

**Đừng lấy thông tin đội tự báo để xếp hạng “đội Agile nhất”**. Điều đó làm méo số liệu, thúc đẩy giấu blocker và khiến học hỏi trở thành rủi ro nghề nghiệp.

## 15. Cộng đồng thực hành giúp giữ kiến thức mà không tạo cơ quan phê duyệt mới

Khi coach hoặc nhóm chuyển đổi rút đi, nhiều kiến thức có thể tập trung vào một vài cá nhân. **Communities of Practice (CoP)** là một cách tùy chọn để những người có mối quan tâm chuyên môn **trao đổi ví dụ thực, cùng học và chia sẻ giải pháp**.

### CoP có thể làm gì?

- Chia sẻ **bài học về Product Backlog, user story, ví dụ chấp nhận và nghiên cứu người dùng**.
- Trao đổi các **thử nghiệm WIP/SLE và cách đọc flow metrics**.
- Làm việc cùng nhau để cải thiện **CI, TDD, contract tests, release và observability**.
- Tạo thư viện **quyết định, phản mẫu và bài học sự cố** dễ tìm.
- Mentoring thành viên mới hoặc nhóm bắt đầu thử một thực hành.
- Kết nối những người gặp cùng vấn đề nhưng thuộc sản phẩm khác nhau.

### CoP không nên trở thành gì?

| CoP hữu ích | CoP thoái hóa |
| --- | --- |
| Người tham gia mang vấn đề và bằng chứng thật | Chỉ báo cáo hoạt động để hoàn thành lịch |
| Đề xuất lựa chọn và điều kiện áp dụng | Ban hành template bắt buộc cho mọi nhóm |
| Thử và cập nhật kiến thức khi phản hồi thay đổi | Coi tài liệu đã viết một lần là “best practice” bất biến |
| Giúp lan truyền kiến thức, giảm phụ thuộc chuyên gia | Trở thành cấp xét duyệt mọi PR, PBI hoặc event |
| Có tham gia tự nguyện/phù hợp công việc | Ép attendance để tính điểm trưởng thành |

**Một CoP có thể tạm dừng hoặc thay đổi mục tiêu khi không còn tạo giá trị.** Không nên duy trì cộng đồng chỉ vì tổ chức đã đặt tên cho nó.

## 16. Bàn giao trách nhiệm từ ban chuyển đổi vào các cấu trúc thường trực

Nếu chương trình chuyển đổi có một nhóm chuyên trách, cần **bàn giao theo năng lực và quyền**, không chỉ chuyển một thư mục tài liệu.

### Ma trận bàn giao gợi ý

| Năng lực sau chuyển đổi | Chủ thể thường trực cần có | Bằng chứng bàn giao có ích |
| --- | --- | --- |
| **Ưu tiên sản phẩm và đo outcome** | Product Owner/Product Management và người liên quan | Product Goal, backlog, metric contract, nhịp xem lại |
| **Tạo Increment đạt chất lượng** | Developers và năng lực engineering | Definition of Done, CI, test, chính sách release |
| **Cải tiến workflow** | Người làm việc và chủ thể chịu trách nhiệm hệ thống | Bảng flow, chính sách WIP, cơ chế tháo blocker |
| **Phản hồi người dùng** | Product team, UX, support và vận hành | Kênh nghiên cứu, telemetry, cách đưa kết quả vào backlog |
| **Giải quyết rào cản tổ chức** | Lãnh đạo/người có quyền theo chính sách | Danh sách vấn đề còn mở và đường quyết định |
| **Phát triển năng lực** | Mentors, CoP, lãnh đạo kỹ thuật, coach phù hợp | Ví dụ, người hỗ trợ, thời gian học và hỗ trợ |
| **Theo dõi rủi ro hệ thống** | Vai trò vận hành, bảo mật và nhóm sản phẩm | SLI/SLO, incident process và điều kiện dừng |

### Bốn mức trạng thái bàn giao

1. **Chưa rõ quyền/chủ thể:** Chưa nên tuyên bố đã bàn giao.
2. **Đã chỉ định nhưng chưa thực hành:** Cần quan sát trong công việc thật.
3. **Có thể vận hành với hỗ trợ:** Đặt lộ trình giảm phụ thuộc coaching, không rút đột ngột.
4. **Vận hành và tự cải tiến:** Người sở hữu có thể phát hiện vấn đề, ra quyết định phù hợp và xem kết quả mà không cần chương trình làm thay.

### Một thử nghiệm bàn giao thực tế

Cho nhóm thường trực tự:

- Nhận một phản hồi quan trọng từ người dùng.
- Kiểm tra dữ liệu cùng giới hạn.
- Sắp thứ tự một Product Backlog Item hoặc chọn cách thử tiếp.
- Tạo Increment đáp ứng DoD và phát hành an toàn nếu phù hợp.
- Quan sát kết quả và xử lý một rào cản nảy sinh.

Nếu toàn bộ quy trình vẫn phải **xin ban chuyển đổi chỉ cách làm**, trách nhiệm chưa được chuyển thành năng lực bền vững.

## 17. Đo năng lực học hỏi bằng kết quả, không bằng “điểm Agile”

Số nhóm đã được đào tạo, số buổi Scrum hoặc tỷ lệ dùng một phần mềm quản lý có thể giúp theo dõi **hoạt động triển khai**, nhưng không đủ để đánh giá tổ chức **tiếp tục cải tiến sau giai đoạn chuyển đổi**.

### Một bộ tín hiệu cân bằng

| Góc nhìn | Câu hỏi điều hành | Ví dụ phép đo | Giới hạn |
| --- | --- | --- | --- |
| **Giá trị sản phẩm** | Người dùng giải quyết vấn đề tốt hơn? | Task success, outcome theo cohort, phản hồi người dùng | Kết quả còn chịu tác động từ môi trường và hành vi |
| **Dòng công việc** | Giá trị đến sớm và đều hơn? | Lead time end-to-end, phân phối cycle time, WIP, Work Item Age | Đơn vị hạng mục và ranh giới phải nhất quán |
| **Chất lượng** | Increment đúng và dễ sửa hơn? | DoD, lỗi hồi quy, lỗi nghiêm trọng, test theo rủi ro | Số lỗi phụ thuộc cách phát hiện/báo cáo |
| **Độ tin cậy** | Phát hành và vận hành an toàn? | SLI/SLO phù hợp, sự cố, khả năng phục hồi | Một số SLI có thể không phản ánh task success |
| **Khả năng học** | Có thử, kiểm tra, ra quyết định từ bằng chứng? | Giả thuyết có mốc xem lại; điều chỉnh backlog có lý do | Không đếm số thử nghiệm như KPI phải tăng |
| **Năng lực tổ chức** | Rào cản ngoài nhóm có được xử lý? | Tuổi quyết định còn mở, blocked time do chính sách | Không quy lỗi cho người nêu blocker |
| **Bền vững** | Nhịp làm việc có duy trì? | Tải on-call, làm thêm giờ ngoài kế hoạch, phản hồi tự nguyện | Không theo dõi đời tư hoặc xếp hạng cá nhân |

**Không cần mỗi nhóm có tất cả chỉ số**. Chọn vài chỉ số phục vụ những câu hỏi quan trọng hiện tại, bổ sung dữ liệu chẩn đoán khi cần. Không tạo một “Agile score” với trọng số tùy ý để thay thế thảo luận.

### Một định nghĩa về khả năng học có thể quan sát

Thay vì “mỗi Sprint phải có ba cải tiến”, hãy kiểm tra:

1. Nhóm **nhận biết một vấn đề thực** qua dữ liệu hoặc phản hồi.
2. Có **giả thuyết cụ thể** về nguyên nhân/cách thay đổi.
3. Có **quyền và năng lực** để thử với guardrails.
4. Có **thời điểm kiểm tra** kết quả.
5. Có **quyết định rõ**: giữ, sửa, dừng, chia sẻ bài học.
6. Điều hữu ích được **duy trì trong thực tế**, không chỉ lưu trên slide.

Không đếm từng điều thành bảng thành tích cá nhân. Đây là **các câu hỏi kiểm tra cơ chế**, không phải tiêu chí để thưởng/phạt.

## 18. Tránh Goodhart: chỉ số trở thành mục tiêu có thể làm méo hành vi

Khi chuyển đổi ban đầu, tổ chức có thể đặt KPI “mọi team phải tăng velocity” hoặc “không được có bug”. Những chỉ tiêu này làm nhân viên **có động lực tối ưu con số thay vì hệ thống**.

### Những méo mó phổ biến

| Mục tiêu cứng | Hành vi có thể xảy ra | Sự thật bị che |
| --- | --- | --- |
| **Velocity luôn tăng** | Tăng story points hoặc đổi hạng mục tham chiếu | Giá trị và chất lượng không nhất thiết tăng |
| **Throughput task tăng** | Chia cùng công việc thành nhiều ticket nhỏ | Số kết quả người dùng không đổi |
| **Cycle time phải thấp** | Chuyển điểm Started muộn hơn, giấu thời gian chờ | Lead time của người dùng không giảm |
| **Không có blocker** | Không gắn nhãn blocked | Vấn đề biến mất khỏi dashboard, không khỏi hệ thống |
| **Ít lỗi nhất** | Không ghi nhận lỗi hoặc đổi tên thành “improvement” | Chất lượng đo mất tin cậy |
| **Nhiều deploy nhất** | Triển khai thay đổi không có giá trị | Tần suất không đồng nghĩa phản hồi người dùng |
| **100% attendance event** | Có mặt nhưng không tranh luận hoặc thích ứng | Nghi thức thay thế học hỏi |
| **Mọi đội đạt mức maturity X** | Tối ưu hồ sơ tự chấm điểm | Không chứng minh năng lực làm việc thật |

### Phòng ngừa ở cấp tổ chức

- **Tuyên bố mục đích đo:** Câu hỏi nào cần được giải quyết?
- **Giữ nguyên định nghĩa qua các kỳ**, ghi ngày thay đổi cách đo.
- **Xem cùng guardrails:** Flow tốt hơn mà lỗi dữ liệu tăng không phải kết quả tốt.
- **Đón nhận số liệu bất lợi:** Bug và blocker cần được báo trung thực.
- **Tách đo hệ thống khỏi xếp hạng cá nhân:** Tránh dùng số commit, story points, thời gian online để suy ra “năng suất”.
- **Sử dụng dữ liệu định tính:** Người thực hiện và người dùng có thể giải thích điều dashboard chưa thấy.
- **Chấp nhận câu trả lời “chưa đủ bằng chứng”** khi mẫu nhỏ, mốc đo không tương thích hoặc outcome còn chờ.

### Một phép tính cần đọc đúng

Giả sử tỷ lệ người học tiếp tục thành công tăng từ **40% lên 46%**:

- Chênh lệch tuyệt đối: **6 điểm phần trăm**.
- Tăng tương đối: \(\frac{46-40}{40}\times100\%=15\%\).

Không được nói tăng “15 điểm phần trăm”. Cũng **không được kết luận chắc chắn** tổ chức chuyển đổi Agile đã gây ra mức tăng này nếu đồng thời có chiến dịch nhắc học, thay đổi cohort hoặc cách ghi sự kiện.

## 19. Bảo vệ nhịp làm việc bền vững và an toàn tâm lý

Một đội có thể báo throughput cao hơn nhờ **làm ngoài giờ, bỏ kiểm thử, căng thẳng và liên tục xử lý sự cố**. Thành tích đó khó duy trì và có thể gây hại cho cả người dùng lẫn người làm việc.

### Những tín hiệu hệ thống nên xem

| Tín hiệu | Câu hỏi | Cách sử dụng có trách nhiệm |
| --- | --- | --- |
| **Làm ngoài giờ lặp lại** | Nhóm có liên tục vượt năng lực bình thường? | Xem khối lượng và cơ chế ưu tiên, không chấm điểm cá nhân |
| **Incident/on-call ngoài kế hoạch** | Có phải sửa sự cố lặp vì thiếu chất lượng? | Giảm nguyên nhân và phân bổ hỗ trợ công bằng |
| **Nhiều công việc chen ngang** | Có thiếu chính sách xử lý khẩn? | Phân biệt incident thật với yêu cầu có thể xếp backlog |
| **WIP và Work Item Age cao** | Nhóm đang dở quá nhiều việc? | Xem nguồn chờ, không ép từng người phải bận 100% |
| **Phụ thuộc một chuyên gia** | Nếu người ấy nghỉ, dòng việc có dừng? | Pairing, tài liệu, kiểm thử và lan truyền kiến thức |
| **Không có thời gian cải tiến** | Lỗi lặp và nợ kỹ thuật tăng theo thời gian? | Bảo vệ năng lực cải tiến theo giá trị/rủi ro |
| **Phản hồi tự nguyện từ nhóm** | Nhịp hiện tại có thể tiếp tục một cách lành mạnh? | Tôn trọng riêng tư; không thu thập thông tin sức khỏe bắt buộc |

### Phản hồi nhân viên khác đánh giá hiệu suất

Một câu hỏi như:

> “Trong những Sprint gần đây, trở ngại nào khiến nhóm khó hoàn thành một lát cắt mà không phải chuyển ngữ cảnh liên tục?”

có thể giúp tìm **vấn đề quy trình**. Nó không nên biến thành:

> “Ai cảm thấy mệt, khai lý do cá nhân để quản lý chấm điểm.”

Ở nhóm nhỏ, khảo sát “ẩn danh” vẫn có thể khiến người trả lời bị nhận diện. Hãy dùng **phản hồi tự nguyện, tổng hợp đủ an toàn hoặc hội thoại phù hợp** và hạn chế lưu trữ dữ liệu nhạy cảm.

### Sau sự cố nên học gì?

Một cuộc phân tích sự cố tốt đặt câu hỏi:

1. Điều gì đã xảy ra, tác động tới ai và trong bao lâu?
2. Tín hiệu nào xuất hiện trước, cảnh báo có đến kịp không?
3. Những điều kiện kỹ thuật và tổ chức nào góp phần?
4. Làm sao giảm xác suất lặp lại hoặc thời gian phục hồi?
5. Ai triển khai hành động phòng ngừa và khi nào kiểm chứng?

**Không đổ lỗi cá nhân** giúp tăng khả năng phát hiện lỗi. Không có nghĩa bỏ trách nhiệm khắc phục hoặc phớt lờ vi phạm cố ý; các trường hợp đặc biệt cần xử lý theo chính sách phù hợp.

## 20. Học một vòng và học hai vòng: dám sửa cả giả định quản trị

Một đội có thể cải thiện trong những quy tắc hiện tại, hoặc phát hiện **chính quy tắc đang làm công việc kém hiệu quả**.

### Single-loop learning (học trong quy tắc hiện có)

**Câu hỏi:** Làm thế nào làm tốt hơn theo mục tiêu và ràng buộc đang được giả định?

Ví dụ: Pull Request chờ lâu → đặt thời gian review, ghép cặp, chia PR nhỏ hơn.

### Double-loop learning (xem lại giả định và quy tắc)

**Câu hỏi:** Tại sao mọi thay đổi đều phải chờ một người hoặc một cấp phê duyệt? Ràng buộc đó bảo vệ rủi ro thật hay là thói quen tổ chức?

Ví dụ: Nếu mọi PR dù rủi ro thấp đều phải qua một hội đồng họp mỗi tuần, cải tiến lịch review nội bộ **chưa giải quyết nút thắt gốc**. Tổ chức có thể cần phân quyền review dựa trên loại thay đổi, giữ kiểm soát bắt buộc cho rủi ro cao.

### Ví dụ từ nền tảng học

| Hiện tượng | Single-loop learning | Double-loop learning |
| --- | --- | --- |
| Hạng mục chờ môi trường tích hợp | Cải thiện lịch đặt môi trường | Vì sao mọi nhóm phải dùng một môi trường duy nhất? Có thể tự tạo môi trường an toàn không? |
| Nhiều ưu tiên chen ngang | Lập kế hoạch lại Sprint tốt hơn | Ai có quyền thay Product Backlog và vì sao một Product Owner không thể thực hiện trách nhiệm? |
| Kiểm thử cuối đợt nhiều lỗi | Tăng số ca kiểm thử cuối kỳ | Vì sao kiểm thử chưa được xây vào DoD, CI và cách chia lát cắt? |
| Nhiều sự cố ngoài giờ | Lập lịch trực công bằng hơn | Vì sao cùng nguyên nhân lỗi lặp mà không được đầu tư phòng ngừa? |
| Product Review thiếu phản hồi | Mời thêm stakeholder | Vì sao người dùng không thể tiếp xúc và gửi phản hồi sớm hơn? |

### Double-loop không phải “phá mọi quy trình”

Một quy tắc bảo mật, pháp lý hoặc quản lý dữ liệu có thể có lý do bắt buộc. Vấn đề là **làm rõ rủi ro thực và tìm cách thực hiện hiệu quả**, không tự gỡ bỏ kiểm soát cho nhanh. Học hai vòng đòi **người có thẩm quyền cùng tham gia**, và quyết định phải nêu điều kiện an toàn.

## 21. Cơ chế phát hiện Agile đang thoái lui thành nghi thức

Tổ chức nên có khả năng tự nhận biết khi **hình thức vẫn còn nhưng chức năng học hỏi biến mất**.

### Dấu hiệu đáng chú ý

| Quan sát | Điều có thể đang xảy ra | Phản ứng học hỏi |
| --- | --- | --- |
| Review chỉ có slide tổng hợp | Không kiểm tra sản phẩm, người dùng không tham gia | Chuẩn bị Increment thử được và câu hỏi giá trị |
| Daily là từng người báo việc cho quản lý | Developers không điều chỉnh Sprint Backlog | Quay về Sprint Goal, blocked items và kế hoạch |
| Retrospective lặp cùng vấn đề | Cải tiến không có người/capacity hoặc ngoài quyền nhóm | Gắn rào cản với người có quyền, chọn thử nghiệm nhỏ |
| Backlog có nhiều danh sách ưu tiên cạnh tranh | Product Goal và trách nhiệm giá trị bị mờ | Xem quyền ưu tiên, Product Backlog chung khi cùng sản phẩm |
| Velocity là chủ đề chính trong mọi báo cáo | Output thay thế giá trị và chất lượng | Xem outcome, DoD, flow và guardrails |
| Test bị hoãn cuối Sprint | Increment không thường xuyên đạt DoD | CI, TDD/BDD, chia lát cắt và kiểm thử sớm |
| Mọi sự cố làm dừng tất cả kế hoạch | Không có cơ chế điều phối urgent work | Chính sách expedite, WIP và năng lực dự phòng |
| Mỗi đổi kỹ thuật cần hội đồng duyệt | Quyền tự quản bị rút lại | Phân loại quyết định theo rủi ro và quyền |
| Nhiều dashboard nhưng không đổi quyết định | Dữ liệu chỉ dùng báo cáo | Thay buổi xem số bằng câu hỏi và thử nghiệm |
| Cộng đồng Agile chỉ còn đọc bài trình bày | Kiến thức không được kiểm chứng trong công việc | Mang case thật, thử nhỏ và cập nhật bài học |

### Không tự kết luận từ một dấu hiệu

Một Retrospective không tạo ra thay đổi lớn trong Sprint có thể hợp lý nếu đội vừa trải qua sự cố và cần phục hồi. Một giai đoạn có ít release có thể do migration bắt buộc hoặc yêu cầu an toàn. **Hãy hỏi bối cảnh và xu hướng qua nhiều kỳ**, đừng dùng checklist để phán xét.

### Câu hỏi chống nghi thức hóa

> “Nếu bỏ tên ‘Agile’ khỏi tất cả cuộc họp và công cụ, những cơ chế giúp chúng ta kiểm tra thực tế và thay đổi quyết định vẫn còn hoạt động không?”

Nếu câu trả lời là không, tổ chức đang dựa vào hình thức nhiều hơn năng lực thực.

## 22. Giữ kiến thức và khả năng học khi người hoặc điều kiện thay đổi

Một tổ chức có thể cải tiến rất tốt khi có một coach, Product Owner hoặc chuyên gia CI giàu kinh nghiệm. Nhưng nếu mọi hiểu biết nằm trong đầu một người, năng lực tổ chức **có thể biến mất khi người đó chuyển vai trò hoặc nghỉ việc**.

### Những năng lực cần chia sẻ

| Năng lực | Rủi ro khi phụ thuộc một người | Cách tạo khả năng tiếp nối |
| --- | --- | --- |
| **Hiểu Product Goal và người dùng** | Backlog mất hướng khi Product Owner đổi | Ghi giả thuyết, quyết định, dữ liệu outcome và ranh giới sản phẩm |
| **Hiểu workflow và blocked work** | Nhóm chỉ biết xử lý theo kinh nghiệm riêng | Chính sách workflow rõ, ví dụ ngoại lệ, review theo số liệu |
| **Hiểu hợp đồng API/dữ liệu** | Một thay đổi nhỏ bị chặn chờ chuyên gia | Contract tests, pairing, tài liệu quyết định |
| **Năng lực CI/CD** | Pipeline lỗi không ai sửa, test bị vô hiệu hóa | Runbook, ownership, mentoring và thời gian bảo trì |
| **Điều phối phản hồi** | Review/Retrospective mất mục đích khi facilitator vắng | Chia sẻ kỹ năng, Developers tự quản, thử nhiều người hỗ trợ |
| **Ứng phó sự cố** | Chỉ một người trực được dịch vụ quan trọng | Diễn tập hợp lý, runbook, quan sát và phân quyền an toàn |

### Văn bản không thay được thực hành

Một tài liệu dài về “cách làm Agile” không đủ để phát triển năng lực. Cần cơ hội:

- **Làm cùng nhau:** Pairing, shadowing, cùng phân tích một blocker.
- **Tự thực hiện có phản hồi:** Nhóm mới tự dẫn refinement hoặc giải quyết một incident với hỗ trợ khi cần.
- **Kiểm chứng trong tình huống thực:** Có thể tạo Increment và thích ứng dù người hướng dẫn vắng.
- **Cập nhật tài liệu khi sai:** Nếu thực tế khác runbook, sửa nguồn thông tin, không đòi mọi người tuân theo tài liệu đã lỗi thời.

### Onboarding như một phép thử năng lực tổ chức

Khi một thành viên mới gia nhập, họ có thể tìm được **Product Goal, nơi xem backlog, Definition of Done, chính sách workflow, nơi báo vấn đề và cách tìm quyết định** mà không cần ba tuần hỏi khắp công ty không?

Nếu không, tổ chức có thể cần cải thiện **đường tiếp cận tri thức**, nhưng tránh tạo onboarding checklist dài chỉ để chấm điểm. Kết quả cần là **người mới có thể đóng góp an toàn và đặt câu hỏi đúng**.

## 23. Học hỏi ở cấp danh mục đầu tư và chiến lược

Trong tổ chức nhiều sản phẩm, một quyết định đầu tư có thể khiến một đội **không có quyền đổi hướng dù bằng chứng đã thay đổi**. Vì vậy, ngoài Scrum Team và Product Backlog, cần cơ chế xem lại **đầu tư, ưu tiên và ràng buộc tổ chức**.

### Ba loại câu hỏi khác nhau

| Cấp | Câu hỏi | Lựa chọn có thể điều chỉnh |
| --- | --- | --- |
| **Product Backlog** | Nên cải thiện sản phẩm này theo thứ tự nào? | PBI, thử nghiệm, thứ tự và phạm vi |
| **Năng lực/dòng giá trị** | Có đủ người và năng lực tạo Increment chất lượng? | Hỗ trợ kỹ thuật, giảm phụ thuộc, năng lực vận hành |
| **Danh mục/chiến lược** | Nên tiếp tục đầu tư vào sản phẩm hoặc vấn đề nào? | Điều chuyển đầu tư, ngừng sáng kiến, thay mục tiêu có lý do |

### Không cần khóa mọi kế hoạch một năm để “ổn định”

Một số cam kết pháp lý hoặc hợp đồng có mốc bắt buộc. Nhưng các giả thuyết sản phẩm chưa được kiểm chứng có thể cần **đầu tư từng bước**, để mỗi vòng tạo thêm bằng chứng trước quyết định tiếp theo.

**Rolling-wave planning** là một cách tiếp cận hữu ích:

- **Gần:** Chi tiết đủ để thực hiện, kiểm thử và tích hợp.
- **Trung hạn:** Mục tiêu, lựa chọn năng lực và phụ thuộc quan trọng.
- **Xa:** Hướng chiến lược, giả thuyết lớn và điều bất định.

Không có “mức khoảng thời gian” cố định áp dụng cho mọi tổ chức. Câu hỏi là **quyết định nào khó đảo ngược cần chuẩn bị sớm, quyết định nào có thể thử nhỏ để tránh cam kết sai quá sớm**.

### Kết thúc đầu tư là một dạng học hỏi

Nếu một thử nghiệm cho thấy người dùng không cần khả năng X như dự đoán, dừng hoặc giảm đầu tư có thể là **kết quả quản trị tốt**. Đừng ép đội hoàn tất roadmap chỉ vì ngân sách đã ghi tên dự án, đồng thời cần quản lý nghĩa vụ hợp đồng, chi phí chuyển đổi và người dùng đang phụ thuộc chức năng.

### Một phiên xem lại đầu tư có ích

1. Giả thuyết nào có **bằng chứng mới**?
2. Outcome hoặc tác dụng phụ nào **khác dự tính**?
3. Chi phí cơ hội của việc tiếp tục là gì?
4. Rủi ro hoặc điều kiện tổ chức nào cần tháo?
5. Quyết định là **tiếp tục, tăng/giảm đầu tư, thử tiếp, điều chỉnh hoặc dừng**?
6. Ai chịu trách nhiệm và khi nào kiểm tra lại?

Một phiên xem lại kiểu này **không cần nhận báo cáo toàn bộ task của từng đội**. Nó cần thông tin đủ cho những quyết định thuộc cấp đầu tư.

## 24. Khi thử nghiệm thành công không nên biến ngay thành “best practice bắt buộc”

Một chương trình chuyển đổi có thể tổng kết rằng nhóm A giảm cycle time sau khi thử WIP limit và ghép cặp. Nếu tổ chức lập tức ban hành “mọi nhóm phải dùng WIP limit = 5 và pair 4 giờ/ngày”, sự học hỏi có thể dừng ngay tại nơi nó cần tiếp tục.

### Phân biệt ba loại tri thức

| Loại | Ví dụ | Cách chuyển giao |
| --- | --- | --- |
| **Nguyên tắc** | Làm công việc dở nhìn thấy; bảo vệ chất lượng; nhận phản hồi sớm | Có thể áp dụng rộng nhưng giải thích mục đích |
| **Thực hành có điều kiện** | WIP limit phù hợp với loại việc, pair tại đoạn rủi ro cao | Chia sẻ cơ chế, dữ liệu và điều kiện thành công |
| **Quy ước nội bộ của nhóm** | Tên cột board, mẫu ghi chú, giờ pairing | Cho nhóm chủ động nếu không phá tích hợp/guardrails |

### Một “pattern” đáng chia sẻ có cấu trúc

~~~text
TÊN:
  Giảm thời gian chờ kiểm thử tích hợp.

BỐI CẢNH:
  Nhóm phát triển tính năng có CI và API phụ thuộc nhiều nơi.

VẤN ĐỀ:
  PBI Done cục bộ nhưng chưa đạt DoD end-to-end.

THỰC HÀNH THỬ:
  Contract examples, CI tích hợp sớm,
  cùng kiểm tra lát cắt trước khi kéo việc mới.

CƠ CHẾ:
  Phát hiện mâu thuẫn hợp đồng khi thay đổi còn nhỏ.

BẰNG CHỨNG:
  Blocked time theo loại PBI, lỗi tích hợp,
  lead time và quality guardrail qua các kỳ.

GIỚI HẠN:
  Chưa kiểm chứng trong migration dữ liệu lớn.

KHI NÀO KHÔNG NÊN SAO CHÉP:
  Workflow khác hoặc phụ thuộc bắt buộc chưa được giải quyết.

CÂU HỎI THỬ Ở ĐỘI MỚI:
  Nút thắt của đội có thật ở tích hợp không?
~~~

### Đừng chuẩn hóa bằng chứng chưa có

Một nhóm tăng throughput sau khi đổi công cụ có thể do thay cách chia ticket, thành viên tăng hoặc ít incident hơn. **Không nên biến kinh nghiệm một lần thành chính sách toàn công ty** trước khi hiểu cơ chế và bối cảnh.

### Thay đổi tiêu chuẩn chung khi có lý do

Một số quy tắc **nên chung** nếu nhiều nhóm cùng một sản phẩm: Definition of Done thống nhất theo Scrum, hợp đồng API, yêu cầu phân quyền và chính sách bảo vệ dữ liệu. Không nên hiểu “tự chủ” là mỗi nhóm định nghĩa khác nhau về mức an toàn.

**Tự chủ và nhất quán không đối lập:** Chuẩn hóa ở **ranh giới tạo hậu quả cho người khác**; cho phép thử cách làm khác nhau trong phạm vi có thể đảo ngược và kiểm chứng.

## 25. Case study xuyên suốt: chuyển đổi hoàn tất trên giấy, học hỏi ngừng trong thực tế

**Bối cảnh giả định:** Công ty phát triển một nền tảng học trực tuyến. Một năm trước, công ty bắt đầu chương trình chuyển đổi Agile với ba mục tiêu: đưa cải tiến tới người học sớm hơn, giảm lỗi tích hợp và giúp các nhóm phối hợp tốt hơn.

Trong năm đầu, công ty:

- Đào tạo Scrum/Kanban cho nhiều thành viên.
- Thành lập Product Team, có Product Owner và một số Scrum Master.
- Cải thiện pipeline CI và tổ chức Sprint Review với stakeholder.
- Thử chia user story theo hành vi người học, đo cycle time và lỗi sau release.
- Có nhóm coaching hỗ trợ các Retrospective và tháo blocker.

Sau đó, báo cáo kết thúc chương trình: **“100% mục tiêu chuyển đổi về số nhóm và đào tạo đạt”**. Bộ phận triển khai giải thể; không có kế hoạch rõ ai duy trì việc sửa rào cản và đầu tư chất lượng.

### 25.1. Sáu tháng sau: nghi thức vẫn chạy, giá trị bị đứt

Một nhóm đang làm chức năng **lưu và khôi phục tiến độ học**. Họ tổ chức đầy đủ các sự kiện Scrum, nhưng:

1. Quản lý kinh doanh giao yêu cầu trực tiếp cho từng Developer, làm Product Backlog bị chia thành nhiều ưu tiên.
2. Sprint Planning biến thành việc phân công task có ngày cam kết bất biến.
3. Daily Scrum là từng thành viên báo cáo tiến độ cho quản lý.
4. Sprint Review diễn ra khi chưa có Increment tích hợp, chỉ trình chiếu màn hình thử.
5. Retrospective lặp câu “cần cải thiện kiểm thử tích hợp” nhưng không có năng lực hoặc quyền thực hiện.
6. Một môi trường tích hợp dùng chung bị nghẽn, chờ duyệt phát hành qua hội đồng định kỳ.
7. Người học liên tục báo trạng thái “Đã lưu” không khớp dữ liệu thực, nhưng phản hồi không vào thứ tự Product Backlog.

Tổ chức **không đánh mất kiến thức từ vựng Agile**. Nó đánh mất **quyền, năng lực và nhịp giải quyết vấn đề từ phản hồi**.

### 25.2. Bảng hiện trạng giả định

Số liệu dưới đây **hoàn toàn minh họa**, được đặt với giả định ranh giới đo nhất quán giữa hai khoảng quan sát nhưng vẫn cần xem loại công việc và điều kiện tương đương.

| Tín hiệu | Cuối năm chuyển đổi | Sáu tháng sau | Câu hỏi cần đặt |
| --- | ---: | ---: | --- |
| Tỷ lệ người học tiếp tục đúng tiến độ trong cohort đủ điều kiện | 64% | 61% | Có thay đổi cohort, tính năng hoặc cách đo không? |
| Lead time từ nhu cầu được ưu tiên tới Increment dùng được, số mô tả điển hình | 16 ngày | 25 ngày | Chờ ở đâu? Định nghĩa có đổi không? |
| Thời gian blocked vì môi trường, trong một lát cắt mẫu | 3 ngày | 8 ngày | Nút thắt tích hợp có tái xuất hiện? |
| WIP trung bình | 7 hạng mục | 13 hạng mục | Đang mở quá nhiều việc hay loại việc thay đổi? |
| Lỗi sau phát hành mức trung bình trở lên trong kỳ | 5 | 11 | Mức sử dụng và cách phát hiện có tương đương? |
| Sự cố hỗ trợ ngoài giờ trong kỳ | 2 | 6 | Có nguyên nhân lỗi lặp và tải vận hành tăng? |
| Sự kiện Scrum theo lịch | Đủ | Đủ | Vì sao nghi thức không bảo vệ kết quả? |

**Điểm mấu chốt:** Các con số không chứng minh riêng việc giải thể ban chuyển đổi đã gây suy giảm. Chúng giúp tổ chức nhận diện **những giả thuyết cần điều tra**, nhất là thời gian chờ và thay đổi quyền quyết định.

### 25.3. Tìm nguyên nhân bằng ba lớp học hỏi

Nhóm điều tra theo ba câu hỏi:

| Lớp | Quan sát | Giả thuyết |
| --- | --- | --- |
| **Sản phẩm** | Người học báo trạng thái lưu khó hiểu, outcome giảm | Product Backlog đang ưu tiên số màn hình thay vì đúng vấn đề người học |
| **Engineering/flow** | PBI chờ hợp đồng/môi trường, WIP cao | Tích hợp muộn và mở quá nhiều việc làm lead time tăng |
| **Tổ chức** | Nhiều cấp giao trực tiếp; cải tiến Retrospective không có nguồn lực | Quyền ưu tiên và hỗ trợ tổ chức bị rút sau chương trình |

Không nên kết luận “Scrum thất bại” hoặc “Developers không còn cố gắng” trước khi kiểm tra những điều kiện này.

### 25.4. Khôi phục Product Goal và một đường ưu tiên rõ

Product Owner cùng các bên liên quan làm rõ Product Goal:

> “Học viên quay lại đúng tiến độ đã được xác nhận và có thể tiếp tục hành trình mà không phải học lại.”

Họ xem lại Product Backlog để phân biệt:

- **Vấn đề chất lượng cần xử lý sớm:** Trạng thái “Đã lưu” xuất hiện trước xác nhận.
- **Lát cắt giá trị:** Khôi phục đúng vị trí trên cùng tài khoản.
- **Ý tưởng chưa đủ bằng chứng:** Đồng bộ offline mọi thiết bị.
- **Công việc kỹ thuật hỗ trợ:** Contract test và observability cho thao tác lưu/đọc.

Các yêu cầu mới phải được **thảo luận về giá trị và thứ tự** thay vì đưa thẳng vào từng Developer ngoài Product Backlog. Điều này không cấm stakeholder góp ý; nó tạo **một cách xử lý xung đột minh bạch**.

### 25.5. Thử cải thiện dòng công việc nhỏ, có guardrails

Nhóm có giả thuyết:

> “Nếu hạn chế WIP ở các bước trước tích hợp, làm rõ hợp đồng API sớm và kiểm chứng trạng thái lưu bằng test tích hợp trong CI, thời gian blocked và lỗi phát hành sẽ giảm mà không cần làm ngoài giờ liên tục.”

Họ thực hiện:

1. Giữ bảng minh bạch cho **việc đã bắt đầu, đang chờ và đã đạt DoD**.
2. Khi kiểm thử là nút thắt, **giúp hoàn tất lát cắt gần Done** trước khi mở PBI mới.
3. Viết ví dụ Given–When–Then cho trạng thái lưu, bao gồm timeout.
4. Tạo contract tests cho ngữ nghĩa lưu **đã nhận** khác **đã ghi thành công**.
5. Dành năng lực sửa và giữ ổn định pipeline CI.
6. Ghi nguyên nhân blocked và định nghĩa đo thống nhất.
7. Bảo vệ quality guardrails, không ép release khi dữ liệu sai.

### 25.6. Thay đổi ở cấp tổ chức chứ không chỉ cấp nhóm

Lãnh đạo đồng ý:

- Các yêu cầu sản phẩm mới đi qua **cơ chế quản lý Product Backlog phù hợp**, trừ sự cố khẩn theo chính sách.
- Những thay đổi ít rủi ro được **xử lý gần người thực hiện hơn**, không chờ hội đồng chỉ họp theo lịch.
- Một nhóm hỗ trợ nền tảng cung cấp **hợp đồng dịch vụ hoặc khả năng tự phục vụ** cho môi trường test có kiểm soát.
- Cải tiến kỹ thuật quan trọng được **nhìn thấy trong ưu tiên và phân bổ năng lực**, không bị yêu cầu làm ngoài giờ.
- Retrospective được phép **đưa một rào cản tổ chức lên người có thẩm quyền**, kèm thời hạn phản hồi rõ.

Không cắt kiểm soát bảo mật hoặc xử lý dữ liệu. Mục tiêu là **giảm chờ không tạo giá trị**, giữ những kiểm tra có lý do thật.

### 25.7. Dữ liệu sau một số vòng cải tiến

Giả sử sau ba đến bốn Sprint và một cửa sổ quan sát đủ dài phù hợp, nhóm ghi được:

| Tín hiệu | Trước cải tiến | Sau cải tiến | Giới hạn diễn giải |
| --- | ---: | ---: | --- |
| Lead time điển hình của lát cắt tương tự | 25 ngày | 18 ngày | Xem phân phối và hạng mục đang mở |
| Blocked time trong một lát cắt minh họa | 8 ngày | 4 ngày | Có thay loại công việc hoặc môi trường? |
| WIP trung bình | 13 | 8 | Không được ẩn việc chờ để làm đẹp số |
| Tỷ lệ người học tiếp tục đúng tiến độ | 61% | 66% | Cần cohort, exposure, cửa sổ và yếu tố khác |
| Lỗi hậu phát hành mức trung bình trở lên | 11 | 6 | Xem severity và mức tiếp xúc |
| Sự cố ngoài giờ | 6 | 3 | Kiểm tra cả mức độ nghiêm trọng và cách đếm |

Những con số trên **phù hợp với giả thuyết rằng vòng học hỏi được phục hồi**, nhưng chưa chứng minh thay đổi tổ chức là **nguyên nhân duy nhất**. Có thể đồng thời có thay đổi nhân sự, loại bài học, chiến dịch hoặc lưu lượng người dùng.

### 25.8. Một kết luận có trách nhiệm

> “Nhóm đã phục hồi cách ưu tiên theo Product Goal, giảm số việc dở và tích hợp sớm hơn. Dữ liệu giả định qua vài vòng cho thấy lead time và một số tín hiệu chất lượng có hướng tốt hơn; outcome của người học cũng có dấu hiệu cải thiện. Chúng ta sẽ duy trì những cơ chế có ích, tiếp tục xác minh ở các cohort và không tự tuyên bố tác động nhân quả từ trước/sau. Các điểm nghẽn còn lại có chủ thể theo dõi và thời điểm xem lại.”

Một kết luận như vậy **đánh giá năng lực học và hành động**, không chỉ kết quả một kỳ báo cáo.

### 25.9. Ban chuyển đổi có cần tái lập vĩnh viễn?

Không nhất thiết. Nhóm có thể **tạm thời huy động hỗ trợ coaching, engineering hoặc lãnh đạo** để phục hồi các cơ chế. Sau đó, người phụ trách sản phẩm, nhóm kỹ thuật và cấp quản trị sở hữu hoạt động thường xuyên.

Nếu mỗi lần có vấn đề đều phải tái lập **một ban chỉ đạo mới**, tổ chức chưa đưa khả năng điều chỉnh vào cấu trúc hiện tại. Cần xem lại **quyền quyết định và đường phản hồi** thay vì tạo vòng lặp quản lý tạm thời vô tận.

## 26. Khi số liệu “đẹp” nhưng học hỏi thực tế đang yếu đi

Một tổ chức có thể thấy:

- Tổng số story points tăng.
- Tỷ lệ hoàn tất khóa học Agile đạt 100%.
- Mọi đội họp Daily Scrum đúng giờ.
- Số lỗi được báo cáo giảm.

Nhưng:

- Story được chia nhỏ hơn mà người dùng chưa dùng được tính năng.
- Có rất ít phản hồi người dùng đi vào quyết định backlog.
- Những lỗi nghiêm trọng bị ghi thành “technical improvement” thay vì bug.
- Work Item Age của các việc khó tiếp tục tăng.
- Người làm việc ngại báo vấn đề vì sẽ bị trừ điểm năng suất.

**Đây là một hệ đo có thể bị điều khiển bởi mục tiêu**. Để nhận diện, hãy xem **tính toàn vẹn của nguồn dữ liệu và các tín hiệu bảo vệ**.

### Phép kiểm tra tính toàn vẹn tối thiểu

1. **Đơn vị:** Số ticket, số story, số người dùng hay số request?
2. **Ranh giới:** Từ Started tới Done theo định nghĩa nào?
3. **Nguồn:** Dữ liệu được thu khi nào và có thiếu nhóm/người dùng nào?
4. **Động cơ:** Người ghi số có đang chịu chỉ tiêu khiến họ đổi cách đếm?
5. **Guardrails:** Chất lượng, độ tin cậy, quyền riêng tư và nhịp bền vững có được đo?
6. **Bằng chứng định tính:** Người dùng và người làm việc có xác nhận hiện tượng không?
7. **Quyết định:** Sau khi thấy số, tổ chức có thực sự làm điều gì khác?

### Mức giảm bug chưa chắc chất lượng tăng

Nếu nhóm thay công cụ ghi nhận và có ít người dùng hơn, tổng số bug có thể giảm. Ngược lại, khi tổ chức tạo điều kiện báo lỗi trung thực, **số lỗi được phát hiện ban đầu có thể tăng** dù chất lượng kiểm soát về sau tốt hơn.

Đừng dùng số lỗi thô như một thước đo duy nhất. Xem **severity, lỗi ảnh hưởng người dùng, mức tiếp xúc, xu hướng sau nhiều kỳ và khả năng phát hiện/khắc phục**.

## 27. Kế hoạch phục hồi khi chương trình đã kết thúc và cải tiến bị đình trệ

Không phải tổ chức nào cũng có thể tổ chức lại ngay. Có thể bắt đầu bằng **một chuỗi hành động ngắn, có quyền và bằng chứng**, thay vì ra thông báo “Agile 2.0” rồi triển khai thêm toàn bộ nghi thức.

### Bước 1 — Chọn một vấn đề quan trọng, không bắt đầu bằng tái chứng nhận

Ví dụ: “Tính năng lưu tiến độ mất nhiều tuần để sửa nhưng vẫn có lỗi ảnh hưởng người học.” Chọn một hành trình đủ giá trị và rủi ro phù hợp để quan sát.

### Bước 2 — Cùng người làm việc vẽ dòng thực tế

Ghi thời gian chờ, điểm quyết định, WIP, lỗi tích hợp, nguồn dữ liệu và khả năng phát hành. Không vội kết luận “mọi người thiếu Agile mindset”.

### Bước 3 — Làm rõ điều gì nhóm có thể đổi và điều gì cần cấp tổ chức

| Nhóm tự thay đổi được | Cần phối hợp hoặc quyền khác |
| --- | --- |
| Thảo luận Sprint Goal và lát cắt rõ hơn | Quyền quản lý thứ tự Product Backlog bị chia nhỏ |
| Ghép cặp kiểm thử ranh giới API | Hệ môi trường tích hợp bị chặn bởi cơ cấu khác |
| Giới hạn WIP, review Work Item Age | Chính sách ưu tiên hoặc nhân lực luôn bị điều đi |
| Viết test và giữ CI có ý nghĩa | Ngân sách bảo trì pipeline và quyền release |

### Bước 4 — Chọn một thay đổi vừa đủ

Thử **refinement dựa trên ví dụ + contract test + giảm WIP trước điểm nghẽn**, nếu cơ chế này phù hợp quan sát. Có thể chọn cách khác; quan trọng là **giả thuyết có thể kiểm chứng**.

### Bước 5 — Bảo vệ chất lượng và nhịp bền vững

Không tăng tốc bằng cách bỏ Definition of Done, triển khai rủi ro hoặc bắt nhóm làm ngoài giờ vô hạn. Có quyền ứng phó khi xuất hiện sự cố nghiêm trọng.

### Bước 6 — Xem kết quả và điều chỉnh

Xem **end-to-end lead time, Work Item Age, quality guardrails, outcome người dùng và phản hồi đội** sau khoảng thời gian phù hợp. Nêu cả điều chưa biết.

### Bước 7 — Chuyển cơ chế thành trách nhiệm thường trực

Nếu việc thử có ích, ghi **chính sách, người duy trì, đường giải quyết ngoại lệ và lúc xem lại**. Không giữ một chuyên gia chuyển đổi làm người phê duyệt mọi bước.

### Bước 8 — Kiểm tra lại ở bối cảnh mới

Khi đội hoặc loại công việc thay đổi, **đừng coi lựa chọn cũ là bất biến**. Một thực hành tốt cho nhóm phát triển tính năng chưa chắc đúng với dòng incident hoặc hệ thống chịu ràng buộc pháp lý cao.

## 28. Các phản mẫu khiến chuyển đổi Agile có “điểm kết thúc hình thức”

| Phản mẫu | Tại sao làm mất năng lực học? | Hướng điều chỉnh |
| --- | --- | --- |
| **Chuyển đổi = đào tạo xong** | Hiểu khái niệm không chứng minh thay đổi công việc | Thử trong sản phẩm thật, có kết quả và phản hồi |
| **Chuyển đổi = mọi đội đều họp Scrum** | Nghi thức thay thế mục đích kiểm tra/thích ứng | Đánh giá Scrum events theo giá trị và quyết định tạo ra |
| **Báo 100% đội đã “Agile”** | Một nhãn không phản ánh khả năng giao Increment | Đo outcome, flow, chất lượng và năng lực tự điều chỉnh |
| **Ban chuyển đổi là chủ duy nhất của cải tiến** | Khi ban giải thể, hành động cải tiến không còn người sở hữu | Bàn giao quyền/năng lực vào sản phẩm, kỹ thuật và lãnh đạo tuyến |
| **Giữ ban chuyển đổi vĩnh viễn để duyệt mọi việc** | Tạo thêm hàng đợi và phụ thuộc | Trao quyền gần nơi có thông tin, hỗ trợ theo nhu cầu |
| **Retrospective tạo việc nhưng không làm** | Vòng học không khép kín | Chọn ít thử nghiệm, cấp năng lực và xem lại kết quả |
| **Chỉ đo số cuộc họp hoặc attendance** | Có mặt không đồng nghĩa phản hồi và quyết định | Kiểm tra Increment, rủi ro, hành động và học hỏi |
| **Velocity tăng là thành công** | Điểm tương đối dễ bị tối ưu sai | Giữ như công cụ planning nội bộ nếu hữu ích |
| **So velocity giữa các đội** | Không cùng thang ước lượng và loại việc | Dùng chỉ số toàn luồng với đơn vị rõ |
| **Tỷ lệ Done cao nhờ đổi định nghĩa** | Dời việc kiểm thử và tích hợp sang sau | Giữ Definition of Done và ranh giới đo minh bạch |
| **Chỉ đo PBI đã hoàn tất** | Việc đang kẹt biến mất khỏi số liệu | Xem Work Item Age, WIP và blocked items |
| **Giấu lỗi để tránh bị phạt** | Dữ liệu chất lượng mất trung thực | Báo lỗi an toàn, phân tích hệ thống và guardrails |
| **Cắt ngân sách CI/test sau go-live Agile** | Phản hồi kỹ thuật chậm, lỗi tích lũy | Duy trì năng lực kỹ thuật theo nhu cầu sản phẩm |
| **Mọi câu hỏi phải lên cấp quản lý** | Mất tự quản và tốc độ thích ứng | Rõ trách nhiệm, trao quyền dựa trên rủi ro |
| **Nhiều sếp giao backlog song song** | Product Goal và thứ tự mất nhất quán | Làm rõ quyền ưu tiên của Product Owner trong Scrum |
| **Giữ roadmap không đổi dù người dùng phản hồi** | Học được nhưng không hành động | Rolling-wave planning, cập nhật giả thuyết và trade-off |
| **Thấy outcome tăng là bỏ qua lỗi nghiêm trọng** | Hy sinh an toàn lấy một số đẹp | Guardrail là điều kiện dừng/thu hẹp thật |
| **Định nghĩa một best practice cho mọi loại nhóm** | Bỏ qua sự khác biệt dòng công việc | Chia sẻ cơ chế và điều kiện thay vì sao chép nghi thức |
| **CoP chỉ dùng để trình bày slide** | Không có thử nghiệm hay kết quả áp dụng | Mang vấn đề thật, bằng chứng và phản hồi vào cộng đồng |
| **Onboarding chỉ có tài liệu dài** | Tri thức khó thực hành, phụ thuộc người cũ | Pairing, ví dụ thật, làm với phản hồi |
| **Mỗi người bận 100% là tối ưu** | Hàng đợi, gián đoạn và làm ngoài giờ tăng | Giới hạn WIP và tạo năng lực dự phòng hợp lý |
| **Coi báo sự cố là lỗi cá nhân** | Tổ chức giấu tín hiệu quan trọng | Học từ hệ thống, bảo vệ quyền báo cáo |
| **Khảo sát nhịp làm việc rồi công khai từng người** | Rủi ro riêng tư, ngại phản hồi | Tự nguyện, tổng hợp đủ an toàn, mục đích rõ |
| **Tổng kết pilot rồi quên giới hạn suy rộng** | Nhân bản sai mô hình sang dòng việc khác | Ghi cơ chế, điều kiện, guardrails và điều chưa biết |
| **Nhiều dashboard không có quyết định** | Đo lường biến thành hoạt động báo cáo | Mỗi lần xem số phải dẫn tới câu hỏi, hành động hoặc quyết định có lý do |
| **Không chấp nhận kết quả thử nghiệm bất lợi** | Mọi giả thuyết được tuyên bố đúng, học giả | Giữ quyền nói “chưa biết”, “giả thuyết sai” hoặc “cần dừng” |
| **Nghĩ cải tiến là dự án chỉ xuất hiện khi khủng hoảng** | Hệ thống lại xuống cấp giữa các đợt can thiệp | Cải tiến thành phần công việc thường xuyên có người chịu trách nhiệm |
| **Chuẩn hóa cả chi tiết nội bộ từng nhóm** | Giảm khả năng thử nghiệm phù hợp bối cảnh | Chuẩn hóa ranh giới chất lượng/tích hợp; tự quản phần còn lại |

### Phản mẫu nguy hiểm nhất: “đang xanh nên không cần hỏi”

Khi mọi chỉ số báo cáo đều xanh, tổ chức càng cần hỏi:

- Chỉ số đã được định nghĩa nhất quán chưa?
- Những việc khó hoặc chưa Done có bị bỏ khỏi phép đo?
- Có ai ngại báo lỗi hoặc đưa phản biện?
- Người dùng có nhận giá trị và tính năng có an toàn không?
- Tại sao một số giả thuyết **không hề bị bác bỏ** qua nhiều chu kỳ?

**Một tổ chức học hỏi không cần bảng màu đỏ thật nhiều.** Nó cần **khả năng nhìn thấy sự thật, kể cả khi sự thật bất lợi cho kế hoạch cũ**.

## 29. Bài thực hành: chuyển “chuyển đổi xong” thành năng lực học hỏi

Các tình huống và con số dưới đây đều **giả định minh họa**. Hãy nêu **đơn vị đo, ranh giới, nguồn bằng chứng, quyết định và giới hạn suy luận**, không chỉ viết khẩu hiệu.

### Bài 1 — Phân biệt hoạt động triển khai, năng lực và kết quả

Một doanh nghiệp báo cáo:

1. Đã đào tạo 240 nhân viên về Agile.
2. Mọi nhóm có bảng Scrum/Kanban.
3. Product Owner sắp thứ tự Product Backlog bằng phản hồi người dùng.
4. Developers phát hành được Increment đạt DoD với CI và kiểm thử phù hợp.
5. Tỷ lệ người học tiếp tục đúng tiến độ trong bảy ngày cải thiện.
6. Nhóm tự phát hiện một chính sách release gây chờ và đưa ra cách kiểm chứng cải tiến.

**Yêu cầu:** Phân loại từng mục thành **hoạt động triển khai**, **năng lực học hỏi/giao phần mềm**, hoặc **kết quả sản phẩm**. Mục nào chưa đủ để kết luận quan hệ nhân quả?

**Gợi ý:** (1) và (2) là hoạt động; (3), (4), (6) là năng lực/hành vi; (5) là outcome nếu đo đúng. Không có mục nào một mình chứng minh toàn bộ tác động do chuyển đổi.

### Bài 2 — Viết lại một mục tiêu chuyển đổi hình thức

Mục tiêu cũ:

> “Đến cuối quý, 100% nhóm phải chạy Daily Scrum và tăng velocity 20%.”

Hãy viết lại thành:

- Một **vấn đề người dùng hoặc dòng giá trị** cần cải thiện.
- Một **giả thuyết cơ chế** có thể sai.
- Một **outcome** và một **flow metric**.
- Ít nhất **hai guardrails**.
- Một **quyết định có thể đưa ra sau kỳ thử**.

**Định hướng:** Không bắt mọi nhóm dùng cùng framework; cách đo phải giúp học nguyên nhân, không dùng velocity làm KPI chung.

### Bài 3 — Nhìn Retrospective chưa khép vòng học

Ba Sprint liên tiếp, Retrospective đều ghi “Cần tăng test tích hợp”. Không có người làm và các PBI vẫn nằm chờ ở cuối Sprint.

**Nhiệm vụ:**

1. Nêu hai giả thuyết về **nguyên nhân** chứ không chỉ mô tả vấn đề.
2. Đề xuất một thử nghiệm nhỏ liên quan **CI, BDD hoặc WIP**.
3. Chọn hai tín hiệu để quan sát.
4. Xác định ai có thể quyết định trong nhóm, khi nào cần hỗ trợ tổ chức.
5. Viết điều kiện **giữ, sửa hoặc dừng** thử nghiệm.

**Gợi ý:** “Làm nhiều test hơn” không đủ nếu môi trường tích hợp bị khóa bởi một quy trình ngoài quyền nhóm.

### Bài 4 — Phân tích bản đồ dòng giá trị

Một lát cắt theo mô hình tuần tự mất **9 ngày xử lý và 11 ngày chờ** để phát hành.

1. Tổng lead time là bao nhiêu?
2. Tỷ lệ thời gian xử lý trên tổng thời gian?
3. Nếu giảm 3 ngày chờ mà xử lý không đổi, lead time mới?
4. Vì sao không thể kết luận 55% thời gian của Developers “lười” từ phép đo này?
5. Điều kiện nào khiến một bước chờ vẫn cần giữ vì an toàn?

**Đáp án tham khảo:** Lead time ban đầu **20 ngày**; tỷ lệ thời gian xử lý **45%**; nếu giảm ba ngày chờ còn tám, lead time mới **17 ngày**. Thời gian chờ là thời gian của **hạng mục trong hệ thống**, không đo giờ làm của người.

### Bài 5 — Cycle time đẹp nhưng Work Item Age xấu

Nhóm có chuỗi story Done với cycle time **2, 3, 3, 5 và 12 ngày**. Một hạng mục quan trọng khác đã mở **21 ngày** nhưng vẫn blocked.

Hãy tính:

- Mean và median cycle time của những story Done.
- Work Item Age của hạng mục chưa Done.
- Vì sao chỉ công bố mean/median có thể che vấn đề?
- Một hành động thích hợp trước khi mở thêm story.

**Đáp án tham khảo:** Mean **5 ngày**, median **3 ngày**. Hạng mục chưa Done có Work Item Age **21 ngày** và phải được xem trong WIP/blocked work; có thể ưu tiên tháo blocker, giúp hoàn tất và kiểm tra chính sách kéo việc.

### Bài 6 — Tính chênh lệch outcome có trách nhiệm

Tỷ lệ người học tiếp tục đúng tiến độ tăng từ **40% lên 46%** sau một số thay đổi sản phẩm và quy trình.

1. Tăng bao nhiêu **điểm phần trăm**?
2. Tăng bao nhiêu **phần trăm tương đối** so với ban đầu?
3. Vì sao không thể tuyên bố “chuyển đổi Agile tạo ra 15% tăng trưởng” từ trước/sau đơn thuần?
4. Cần kiểm tra cohort, exposure, cửa sổ và những yếu tố đồng thời nào?

**Đáp án tham khảo:** **6 điểm phần trăm**, **15% tương đối**. Giới hạn là khác mẫu, chiến dịch, mùa vụ, tính năng và instrumentation có thể thay đổi cùng lúc.

### Bài 7 — Quyết định có nên giải thể ban chuyển đổi

Một ban hỗ trợ Agile muốn kết thúc dự án vào cuối quý. Các nhóm đã học Scrum nhưng:

- Product Owner vẫn không có quyền giải quyết ưu tiên mâu thuẫn.
- CI chỉ do một chuyên gia ngoài nhóm bảo trì.
- Hành động Retrospective cấp tổ chức không có người tiếp nhận.
- Phản hồi người dùng đã có trong dashboard nhưng không ảnh hưởng Product Backlog.

**Yêu cầu:** Lập bảng **năng lực – hiện trạng – người thường trực cần sở hữu – bằng chứng bàn giao – blocker**. Đề xuất những điều có thể kết thúc và những điều chưa nên tuyên bố bàn giao.

**Định hướng:** Chương trình có thể hoàn tất các hoạt động hữu hạn, nhưng phải **ghi rõ rủi ro và chủ sở hữu**. Không cần giữ ban vô hạn nếu có thể chuyển giao trách nhiệm vào cấu trúc hiện tại.

### Bài 8 — Chọn việc nên đưa vào Product Backlog hay nơi khác

Phân loại:

1. Người học không hiểu trạng thái “Đang đồng bộ”.
2. Pipeline CI mất 50 phút và hay lỗi giả.
3. Quy tắc phân quyền dữ liệu thiếu kiểm chứng.
4. Một cấp phê duyệt mới làm mọi release chờ 10 ngày.
5. Nhóm muốn thử một cách viết bản ghi Retrospective ngắn hơn.
6. Một sự cố lộ dữ liệu đã được xác nhận.

**Yêu cầu:** Phân biệt **giá trị sản phẩm**, **cải tiến kỹ thuật/workflow**, **rào cản tổ chức** và **xử lý sự cố khẩn**; nêu người có trách nhiệm phù hợp.

**Gợi ý:** Không đưa sự cố bảo mật nghiêm trọng vào hàng đợi cải tiến thường kỳ chờ xét ưu tiên. Không tự tạo một backlog thứ hai tranh thứ tự Product Backlog.

### Bài 9 — Phân biệt single-loop và double-loop learning

Tình huống: Hạng mục chờ xét duyệt từ một hội đồng họp mỗi tháng.

1. Đề xuất một cải tiến **single-loop** trong giới hạn hiện tại.
2. Đặt hai câu hỏi **double-loop** về chính quy tắc xét duyệt.
3. Ai có quyền xem lại chính sách?
4. Làm sao giảm chờ mà **không bỏ kiểm soát bảo mật/dữ liệu bắt buộc**?

**Định hướng:** Tự động hóa kiểm tra phù hợp, phân loại rủi ro và trao quyền đúng nơi có thể tốt hơn chỉ họp hội đồng thường xuyên hơn.

### Bài 10 — Xây bản ghi “pattern có điều kiện”

Nhóm A đã giảm chờ tích hợp nhờ contract tests và ghép cặp, nhưng nhóm B là đội xử lý incident liên tục và chưa có pipeline tương tự.

Hãy tạo bản ghi có:

- Bối cảnh, vấn đề, điều đã thử và cơ chế.
- Dữ liệu ủng hộ cùng guardrails.
- Những giới hạn và điều kiện cần khi chuyển sang nhóm B.
- Một thử nghiệm nhỏ phù hợp với dòng incident của B.
- Điều kiện ngừng nếu tác dụng phụ xấu.

**Gợi ý:** Không bắt B dùng cùng Sprint, cùng WIP limit hoặc cùng lịch pairing của A chỉ để “chuẩn hóa Agile”.

### Bài 11 — Bảo vệ nhịp bền vững

Sau chuyển đổi, throughput tăng nhưng số lần trực ngoài giờ, làm thêm giờ và lỗi hồi quy cũng tăng.

Hãy đề xuất:

1. Hai giả thuyết về nguyên nhân hệ thống.
2. Một thay đổi chính sách ưu tiên/gián đoạn.
3. Một thay đổi kỹ thuật phòng ngừa.
4. Một cách thu nhận phản hồi đội **tự nguyện và bảo vệ riêng tư**.
5. Tiêu chí không được gọi đây là thành công dù throughput tăng.

### Bài 12 — Xây một phiên xem lại chiến lược có quyết định

Ban lãnh đạo có 60 phút xem sản phẩm học trực tuyến. Tài liệu hiện tại gồm 40 slide tiến độ task.

Thiết kế agenda mới:

- Bối cảnh Product Goal và những thay đổi của người dùng.
- Outcome, chất lượng và các rủi ro guardrail.
- Hai nút thắt cấp tổ chức cần quyết định.
- Một giả thuyết đầu tư có thể giữ, thử thêm hoặc dừng.
- Người chịu trách nhiệm và thời điểm xem lại.

**Tiêu chí:** Không biến buổi xem lại thành báo cáo Daily ở cấp cao; chỉ trình bày thông tin đủ cho quyết định thuộc thẩm quyền lãnh đạo.

### Bài 13 — Dùng Little's Law đúng điều kiện

Một dòng công việc được giả định đủ ổn định có:

- WIP trung bình: **12 hạng mục cùng định nghĩa**.
- Throughput trung bình: **3 hạng mục/tuần**.

**Nhiệm vụ:**

1. Tính cycle time trung bình tương ứng theo Little's Law.
2. Nếu WIP xuống 9 mà throughput vẫn đúng 3/tuần, cycle time trung bình tương ứng là bao nhiêu?
3. Nêu ít nhất ba điều kiện khiến công thức **không thể dùng đáng tin**.
4. Giải thích vì sao giảm WIP limit xuống 9 **không bảo đảm** mỗi hạng mục xong sau ba tuần.

**Đáp án tham khảo:** Ban đầu **4 tuần**, sau đó **3 tuần** theo giả định ổn định và cùng đơn vị. Không dùng công thức để cam kết từng hạng mục khi throughput biến động, workflow đổi, dữ liệu không cùng ranh giới hoặc nhiều hạng mục bị hủy/chia.

### Bài 14 — Tạo chương trình bàn giao mà không tạo ban cải tiến vĩnh viễn

Một công ty muốn đóng chương trình chuyển đổi sau sáu tháng nữa. Nhóm sản phẩm đã có CI và Product Backlog, nhưng vẫn phụ thuộc coach để tổ chức Review và cần lãnh đạo giải quyết xung đột ưu tiên.

**Viết kế hoạch bàn giao theo ba giai đoạn:**

1. **Có người cùng làm:** Người thường trực thực hành với hỗ trợ; nêu bằng chứng năng lực.
2. **Tự thực hiện có phản hồi:** Coach không làm hộ, chỉ hỗ trợ lúc cần; lãnh đạo xử lý quyền.
3. **Duy trì và xem lại:** Người thường trực có quyền, nguồn lực và mốc kiểm tra.

**Yêu cầu:** Nêu một tình huống cần **hoãn bàn giao cụ thể**, và một tình huống có thể **bàn giao dù còn những điều cần cải tiến**.

### Bài 15 — Dùng kết quả bất lợi làm thông tin hữu ích

Giả sử nhóm thử giới hạn WIP và contract tests trong ba Sprint. Cycle time của story tương tự không giảm, nhưng lỗi tích hợp được phát hiện sớm hơn, số sự cố sau phát hành giảm và một nhóm stakeholder thấy thời gian chờ ưu tiên tăng.

Hãy viết bản kết luận **180–250 từ** gồm:

- Giả thuyết nào chưa được ủng hộ?
- Kết quả chất lượng nào có ích?
- Điều cần kiểm tra trước khi quyết định giữ hay dừng WIP limit?
- Nút thắt ưu tiên có thuộc quyền nhóm hay tổ chức?
- Quyết định giữ/sửa/dừng từng phần, người chịu trách nhiệm và mốc xem lại.

**Tiêu chí:** Không dùng câu “thí điểm thất bại nên bỏ hết” hoặc “chất lượng tăng nên mọi thứ thành công”. Tách cơ chế, tác dụng phụ và giới hạn bằng chứng.

## 30. Checklist duy trì học hỏi sau chương trình chuyển đổi

### A. Hướng sản phẩm và mục đích

- [ ] Tổ chức đã xác định **vấn đề và giá trị người dùng** mà Agile cần hỗ trợ, không chỉ số nhóm đã chuyển đổi.
- [ ] Có **Product Goal hoặc hướng giá trị** đủ rõ để giúp nhóm ưu tiên.
- [ ] Không đồng nhất **hoạt động triển khai, năng lực làm việc và outcome sản phẩm**.
- [ ] Những phản hồi người dùng có **đường vào quyết định Product Backlog**.
- [ ] Increment đạt **Definition of Done** được phân biệt với deploy/release và outcome.
- [ ] Nhóm có thể **điều chỉnh phạm vi, giả thuyết và thứ tự** khi có bằng chứng mới.
- [ ] Những quyết định có tác động dài hạn được ghi **lý do và điều kiện xem lại**.

### B. Vòng học trong công việc thường ngày

- [ ] Mỗi cải tiến có **vấn đề, giả thuyết, thay đổi, tín hiệu, guardrail và mốc kiểm chứng**.
- [ ] Hành động Retrospective được xem lại qua các Sprint, không liên tục ghi rồi quên.
- [ ] Có cơ chế quan sát **cả hạng mục đang dở** qua WIP và Work Item Age.
- [ ] Flow metrics được định nghĩa theo **đơn vị và ranh giới nhất quán**.
- [ ] CI, test, contract và môi trường tích hợp tạo phản hồi đủ sớm.
- [ ] Sản phẩm được kiểm tra **end-to-end**, không chỉ Done theo từng thành phần.
- [ ] Các câu hỏi mới từ người dùng, sản xuất và kỹ thuật được xử lý **trước khi tích lũy thành lô quá lớn** khi khả thi.
- [ ] Số thử nghiệm cải tiến đang mở phù hợp năng lực; có thể **dừng thử nghiệm ít giá trị**.
- [ ] Kết quả bất lợi hoặc chưa đủ dữ liệu được **báo trung thực**.

### C. Scrum, Kanban, XP và cách chọn phù hợp

- [ ] Scrum events được đánh giá theo **mục đích inspect/adapt**, không chỉ attendance.
- [ ] Product Owner có trách nhiệm thực về thứ tự Product Backlog khi dùng Scrum.
- [ ] Developers có quyền tự quản phù hợp để tạo Increment đạt DoD.
- [ ] Scrum Master/coaching hỗ trợ **hiệu quả của Scrum Team**, không làm thư ký/kiểm soát nghi thức.
- [ ] Kanban workflow, chính sách WIP, throughput, cycle time và Work Item Age được **xem theo bối cảnh**.
- [ ] XP practices được duy trì khi chúng bảo vệ chất lượng và khả năng thay đổi.
- [ ] Đội không bị bắt buộc dùng cùng framework khi **loại công việc và ràng buộc khác nhau**.
- [ ] Những thực hành chia sẻ dưới dạng **cơ chế và điều kiện áp dụng**, không chỉ mẫu biểu.

### D. Quyền, nguồn lực và cấu trúc tổ chức

- [ ] Những rào cản ngoài team có **người đủ quyền giải quyết** và mốc phản hồi.
- [ ] Không có nhiều kênh giao ưu tiên mâu thuẫn làm mờ trách nhiệm giá trị.
- [ ] Các quy tắc phê duyệt được **kiểm tra theo rủi ro thật**, không tự thêm tầng vì “Agile governance”.
- [ ] Có nguồn lực thực cho **quality, CI/CD, nghiên cứu người dùng, vận hành và cải tiến workflow**.
- [ ] Những nút thắt lặp có thể dẫn đến **thay đổi chính sách, cấu trúc nhóm hoặc kiến trúc**.
- [ ] Các quyết định kỹ thuật ít rủi ro được xử lý gần người có thông tin và trách nhiệm phù hợp.
- [ ] Những ràng buộc bảo mật, quyền riêng tư, dữ liệu và tuân thủ **không bị cắt để làm đẹp lead time**.
- [ ] Đầu tư sản phẩm có thể được **xem lại có trách nhiệm** khi kết quả khác giả thuyết.

### E. Con người và nhịp bền vững

- [ ] Nhóm có thể báo bug, blocked work hoặc rủi ro **mà không bị hạ điểm thành tích**.
- [ ] Không dùng velocity, số commit, dòng code hoặc phút online để xếp hạng cá nhân.
- [ ] Số liệu về làm ngoài giờ, trực sự cố và áp lực được dùng **ở mức hệ thống**.
- [ ] Phản hồi đội được thu nhận **tự nguyện và bảo vệ riêng tư**.
- [ ] Có kế hoạch **chia sẻ hiểu biết và onboarding** để không lệ thuộc một coach/chuyên gia.
- [ ] Những cộng đồng thực hành có **vấn đề thật và phản hồi áp dụng**, không chỉ bài trình bày.
- [ ] Đội có thể thử và duy trì cải tiến mà không phải **hy sinh thời gian phục hồi liên tục**.

### F. Bàn giao và sau chuyển đổi

- [ ] Phân biệt **ngày kết thúc chương trình hữu hạn** với **khả năng học hỏi thường trực**.
- [ ] Mỗi năng lực cốt lõi có **chủ sở hữu, quyền, dữ liệu và nguồn lực phù hợp** sau bàn giao.
- [ ] Những vấn đề chưa xong có **người tiếp nhận, mức ưu tiên và mốc xem lại**.
- [ ] Product outcome cần cửa sổ dài vẫn có **người theo dõi sau ngày kết thúc chương trình**.
- [ ] Đã thử khả năng team tự tiếp nhận phản hồi, tạo Increment và xử lý blocker khi coach không trực tiếp điều phối.
- [ ] Nhóm kế tiếp được chọn dựa trên **bối cảnh và điều kiện áp dụng**, không sao chép máy móc pilot trước.
- [ ] Có đường để **phản biện chính cả mô hình tổ chức và cơ chế đo hiện tại** khi chúng không còn phù hợp.
- [ ] Có thể giải thể bộ phận chuyển đổi mà vẫn thấy **học hỏi diễn ra trong sản phẩm, kỹ thuật và điều hành**.

## 31. Câu hỏi ôn tập

1. Vì sao số người đã đào tạo Agile không chứng minh chuyển đổi tạo giá trị?
2. Ba cấp hoạt động triển khai, năng lực vận hành và kết quả sản phẩm khác nhau như thế nào?
3. Tại sao chương trình chuyển đổi có thể kết thúc về ngân sách mà cải tiến liên tục vẫn phải tiếp diễn?
4. Điểm khác nhau giữa bàn giao tài liệu và bàn giao năng lực có trách nhiệm là gì?
5. Những điều kiện nào giúp một nhóm tự học và điều chỉnh khi không còn coach?
6. Một vòng học Agile bắt đầu và kết thúc ở đâu?
7. Vì sao action item hoàn thành chưa chắc là vòng học hoàn thành?
8. Nếu một giả thuyết bị bác bỏ nhưng tổ chức tránh được đầu tư sai, đó có phải là học hỏi có giá trị không?
9. Học hỏi về sản phẩm khác học hỏi về engineering/flow và về tổ chức như thế nào?
10. Product Goal giúp đội tránh quay lại tình trạng chỉ nhận task theo phòng ban ra sao?
11. Vì sao Product Owner không chỉ là người viết ticket hoặc thư ký yêu cầu?
12. Sprint Planning, Daily Scrum, Sprint Review và Sprint Retrospective tạo ra loại kiểm tra–thích ứng gì?
13. Product Goal, Sprint Goal và Definition of Done là commitment gắn với artifact nào trong Scrum?
14. Những dấu hiệu nào cho thấy Sprint Review đã biến thành một buổi demo hình thức?
15. Làm thế nào biết Retrospective đang tạo cải tiến thật thay vì lặp cùng danh sách vấn đề?
16. Khi nào Kanban có thể phù hợp hơn một nhịp Scrum cố định?
17. WIP, throughput, cycle time và Work Item Age trả lời các câu hỏi khác nhau thế nào?
18. Vì sao chỉ đo cycle time các story đã hoàn tất có thể che việc đang bị chặn?
19. TDD, BDD, CI, refactoring và pair programming giúp bảo vệ năng lực thích ứng bằng cơ chế nào?
20. CI xanh và code coverage cao chưa chứng minh những điều gì?
21. Value stream map phải bao gồm những loại thời gian và quyết định nào?
22. Vì sao rút ngắn giờ code cục bộ chưa chắc cải thiện time to value?
23. Khi nào việc chờ để kiểm soát rủi ro là hợp lý, và cần kiểm tra điều gì để giảm chờ không tạo giá trị?
24. Một learning backlog khác Product Backlog chính thức ra sao?
25. Vì sao không nên bắt đầu quá nhiều thử nghiệm cải tiến cùng lúc?
26. Một bản ghi quyết định tốt cần có những loại thông tin gì?
27. Vì sao báo cáo cùng dashboard ở bốn cấp tổ chức không đồng nghĩa có bốn vòng học hữu ích?
28. Quyền quyết định cần ở gần thông tin đến mức nào, và ranh giới an toàn nào cần giữ?
29. Vì sao cải tiến kỹ thuật cần được tài trợ sau khi chương trình chuyển đổi kết thúc?
30. Lãnh đạo cần thay đổi hành vi quản trị nào để nhóm không quay lại tình trạng chờ phê duyệt?
31. Communities of Practice giúp gì và khi nào chúng trở thành nghi thức?
32. Làm sao kiểm tra khả năng tiếp nối khi một coach hoặc chuyên gia quan trọng rời đội?
33. Một bộ chỉ số cân bằng nên gồm những góc nhìn nào và tại sao?
34. Goodhart's Law nhắc điều gì khi velocity/throughput trở thành KPI cứng?
35. Mức tăng từ 40% lên 46% là bao nhiêu điểm phần trăm và bao nhiêu phần trăm tương đối?
36. Vì sao không thể quy kết tác động của chuyển đổi chỉ từ dữ liệu trước/sau?
37. Những tín hiệu nào cho thấy nhịp làm việc đang dựa vào làm thêm giờ hoặc xử lý sự cố lặp?
38. Single-loop learning và double-loop learning khác nhau thế nào với một bước phê duyệt gây chờ?
39. Tại sao không nên dỡ bỏ kiểm soát bảo mật chỉ vì muốn rút ngắn cycle time?
40. Những dấu hiệu nào cho thấy tổ chức đang thoái lui thành việc làm Scrum hình thức?
41. Vì sao mở rộng một thực hành có hiệu quả ở nhóm A cần xem bối cảnh nhóm B?
42. Rolling-wave planning giúp giữ hướng chiến lược mà vẫn thử nghiệm có giới hạn thế nào?
43. Trong case study, tại sao dữ liệu xấu đi chưa chứng minh việc giải thể ban chuyển đổi là nguyên nhân duy nhất?
44. Những thay đổi nào cần thực hiện ở cấp nhóm, sản phẩm và lãnh đạo để phục hồi vòng học trong case study?
45. Vì sao số lỗi giảm vẫn cần kiểm tra mức tiếp xúc người dùng và thay đổi cách ghi nhận?
46. Nếu cải tiến làm cycle time giảm nhưng sự cố dữ liệu nghiêm trọng tăng, cần ra quyết định gì?
47. Điều kiện nào giúp kết thúc một chương trình chuyển đổi hữu hạn một cách có trách nhiệm?
48. Những năng lực nào phải còn hoạt động mà không phụ thuộc ban chuyển đổi?
49. Khi một giả thuyết cũ không còn đúng, Product Backlog và chiến lược đầu tư nên được điều chỉnh ra sao?
50. Bằng chứng nào cho thấy một tổ chức đã duy trì **khả năng học hỏi và thích ứng** thay vì chỉ hoàn thành một dự án đổi phương pháp có điểm kết thúc hình thức?

**Ghi nhớ:** **Chuyển đổi Agile có thể có ngày kết thúc về mặt chương trình, nhưng năng lực nhận phản hồi, kiểm tra thực tế và thích ứng phải sống trong công việc thường ngày.** Đừng lấy số người đã học Scrum, số cuộc họp hay một mức “Agile maturity” làm đích cuối. Hãy giữ **Product Goal và người dùng** làm điểm tựa, tạo Increment đạt **Definition of Done**, quan sát **outcome, chất lượng, flow, độ tin cậy và nhịp bền vững**, thử những cải tiến có giả thuyết, guardrail và mốc xem lại. Chuyển **quyền, nguồn lực và trách nhiệm học hỏi** từ ban chuyển đổi tạm thời sang Product Owner, Developers, lãnh đạo và những người vận hành sản phẩm; tạo điều kiện để đặt câu hỏi về cả chính sách tổ chức khi nó cản giá trị. Một tổ chức thực sự Agile **không cần tuyên bố mình đã hoàn tất học hỏi**: họ có khả năng tiếp tục phát hiện điều chưa đúng, sửa cách làm và đưa giá trị đáng tin cậy đến người dùng qua những vòng phản hồi tiếp theo.
