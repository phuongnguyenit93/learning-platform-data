# Xem Product Owner là người ghi yêu cầu và Scrum Master là người giao việc

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **Product Owner (PO) chỉ ghi yêu cầu** và **Scrum Master (SM) chia việc cho từng người** là hai cách hiểu sai có ảnh hưởng đến giá trị sản phẩm, quyền tự quản và chất lượng Increment.
2. Phân biệt ba nhóm **trách nhiệm giải trình (accountabilities)** của Scrum: **Product Owner, Scrum Master và Developers**; hiểu rằng Scrum Team không có các tiểu đội hoặc cấp bậc nội bộ được Scrum định nghĩa.
3. Trình bày những trách nhiệm quản lý Product Backlog của Product Owner: **Product Goal, Product Backlog Items, thứ tự ưu tiên và tính minh bạch**, cùng khả năng ủy quyền thực hiện nhưng không chuyển giao trách nhiệm giải trình.
4. Trình bày cách Scrum Master hỗ trợ thiết lập Scrum, hiệu quả Scrum Team, tự quản, phối hợp và xử lý trở ngại **mà không biến thành người điều hành công việc từng ngày**.
5. Mô tả quyền và trách nhiệm của Developers khi chọn công việc trong Sprint Planning, xây Sprint Backlog, lập kế hoạch để đạt Sprint Goal, bảo đảm Definition of Done và thích nghi mỗi ngày.
6. Xử lý các tình huống **stakeholder áp đặt ưu tiên, quản lý giao việc trực tiếp, phụ thuộc liên nhóm, sự cố khẩn, thay đổi yêu cầu và bất đồng về chất lượng** mà không đẩy mọi quyết định cho PO hoặc SM.
7. Thiết kế cách cải tiến thực tế bằng **nhật ký quyết định, ví dụ user story, vòng phản hồi sản phẩm, dữ liệu flow và chất lượng**, cùng bài tập thực hành và checklist.

## 1. Khi Scrum biến thành bộ máy nhập việc và giao việc

Một tổ chức phát triển nền tảng học trực tuyến tuyên bố đã chuyển sang Scrum. Trên sơ đồ nhân sự có đủ Product Owner, Scrum Master và Developers. Nhưng cách làm hằng ngày là:

- Trưởng bộ phận gửi một danh sách tính năng, yêu cầu Product Owner nhập thành ticket và không thay đổi thứ tự.
- Product Owner viết lại tài liệu chi tiết, giao cho Developers, ít khi được gặp người học hoặc quyết định việc nào có giá trị hơn.
- Scrum Master mở bảng công việc mỗi sáng, hỏi từng người đã làm gì, giao tiếp task và nhắc hoàn thành đủ story point.
- Developers chỉ được làm những task đã được phân sẵn; muốn giúp đồng đội review hoặc xử lý lỗi tích hợp phải xin phép.
- Sprint Review chủ yếu báo phần trăm ticket đóng, trong khi học viên vẫn chưa sử dụng được tính năng **“Tiếp tục học”**.

Nhóm có thể làm đầy đủ **các nghi thức nhìn thấy được**, nhưng:

1. Không ai thực sự chịu trách nhiệm **kết quả sản phẩm**.
2. Người trực tiếp phát triển không được **tự tổ chức cách tạo Increment**.
3. Scrum Master trở thành một tầng điều phối tạo thêm hàng chờ.
4. Phản hồi về người dùng, dữ liệu và chất lượng không làm thay đổi những quyết định quan trọng.

> **Scrum không định nghĩa Product Owner là người nhập yêu cầu, cũng không định nghĩa Scrum Master là người chia task.** Scrum làm rõ trách nhiệm giải trình để Scrum Team tự quản, giao Increment có giá trị và thích nghi dựa trên thực tế.

Trong module **AGILE_DEVELOPMENT**, nội dung này gắn trực tiếp với việc sử dụng user story, Product Backlog, các sự kiện Scrum, thực hành kỹ thuật XP, quan sát luồng công việc kiểu Kanban và cải tiến liên tục. Công cụ quản lý công việc chỉ hỗ trợ các hành vi đó; bản thân nó không trao quyền và cũng không tạo giá trị.

## 2. Vì sao nhầm trách nhiệm gây hại hơn nhầm chức danh?

Nếu gọi người viết ticket là Product Owner nhưng người đó không thể đưa ra quyết định về **giá trị và thứ tự Product Backlog**, trách nhiệm tối đa hóa giá trị bị tách khỏi quyền hành động.

Nếu gọi người phân công là Scrum Master, Developers có thể trở thành **nhóm nhận lệnh** thay vì tự quản để giao Increment. Họ biết rõ nhất giới hạn code, test, phụ thuộc và năng lực nhưng không thể điều chỉnh công việc khi phát hiện điều mới.

### Chuỗi hậu quả thường gặp

~~~mermaid
flowchart TD
    A["Stakeholder giao danh sách tính năng"] --> B["PO chỉ ghi yêu cầu"]
    B --> C["Không có quyết định giá trị và thứ tự minh bạch"]
    C --> D["SM phân task theo năng lực từng người"]
    D --> E["Developers chờ phân công, khó tự phối hợp"]
    E --> F["Nhiều việc bắt đầu, ít lát cắt tích hợp Done"]
    F --> G["Feedback và lỗi đến muộn"]
    G --> H["Thêm kiểm soát status và deadline"]
    H --> B
~~~

Vấn đề này thường bị che bởi biểu đồ có nhiều task hoàn thành. Tỷ lệ ticket đóng **không tự chứng minh** Product Goal tiến triển, phần mềm đạt Definition of Done hay người dùng nhận giá trị.

### Một chuỗi tốt hơn

Product Owner nêu **mục tiêu và thứ tự giá trị**; Developers cùng chọn và điều chỉnh **cách tạo Increment**; Scrum Master giúp Scrum Team vận hành **Scrum hiệu quả, minh bạch và có khả năng tự quản**. Những trách nhiệm khác nhau này hỗ trợ nhau, không biến thành chuỗi cấp trên ra lệnh cho cấp dưới.

## 3. Scrum Team: một đội tự quản với ba trách nhiệm giải trình

Trong Scrum Guide, Scrum Team gồm **một Scrum Master, một Product Owner và Developers**. Scrum Team **cross-functional** (có đủ kỹ năng cần thiết để tạo giá trị mỗi Sprint) và **self-managing** (nội bộ tự quyết ai làm gì, khi nào và làm thế nào trong phạm vi trách nhiệm).

Scrum không quy định các tiểu đội hoặc thứ bậc nội bộ như “đội PO giao việc cho đội SM, đội SM quản lý Developers”. Một người có thể có chức danh công ty khác, nhưng cần phân biệt chức danh đó với **accountability theo Scrum**.

| Accountability | Chịu trách nhiệm giải trình về điều gì? | Không nên biến thành |
| --- | --- | --- |
| **Product Owner** | Tối đa hóa giá trị sản phẩm tạo ra từ công việc Scrum Team; quản lý Product Backlog hiệu quả | Người chép yêu cầu, thư ký stakeholder, người đóng dấu nghiệm thu mọi task |
| **Scrum Master** | Thiết lập Scrum theo Scrum Guide; hiệu quả của Scrum Team | Người phân công hằng ngày, quản lý chấm công, cảnh sát story point |
| **Developers** | Kế hoạch Sprint; chất lượng qua Definition of Done; thích nghi Sprint Backlog theo Sprint Goal; giữ trách nhiệm với nhau như những người chuyên nghiệp | Những người chỉ làm task được cấp, không được tự điều chỉnh |

**Cả Scrum Team** chịu trách nhiệm về hoạt động liên quan tới sản phẩm và việc tạo **Increment có giá trị, hữu ích mỗi Sprint**.

### Trách nhiệm giải trình không đồng nghĩa làm mọi việc một mình

Product Owner không phải tự viết tất cả ticket. Scrum Master không phải tự gỡ mọi blocker. Developers không phải tự quyết mục tiêu kinh doanh hoặc thay chính sách bảo mật. Mỗi accountability có **một phạm vi chịu trách nhiệm**, nhưng kết quả đòi hỏi cộng tác.

### Ba câu hỏi kiểm tra

- **Giá trị và thứ tự:** Ai chịu trách nhiệm Product Goal và việc sắp xếp Product Backlog?
- **Hiệu quả Scrum:** Ai chủ động giúp mọi người hiểu Scrum, cải tiến cách phối hợp và giải quyết trở ngại tổ chức?
- **Kế hoạch và chất lượng Sprint:** Ai lựa chọn cách làm, kiểm tra tiến độ hướng Sprint Goal và bảo đảm Increment đạt DoD?

Nếu cả ba câu trả lời đều là “trưởng nhóm giao việc”, cấu trúc trách nhiệm đã đi chệch khỏi Scrum.

## 4. Product Owner: trách nhiệm với giá trị sản phẩm

Product Owner chịu trách nhiệm tối đa hóa **giá trị của sản phẩm** do Scrum Team tạo ra. Cách thực hiện có thể khác nhau theo tổ chức, sản phẩm và bối cảnh. Điều quan trọng là Product Owner thực sự làm các quyết định và hoạt động cần thiết để **liên kết công việc với giá trị**.

### Trách nhiệm quản lý Product Backlog hiệu quả

Scrum nêu bốn nội dung của Product Backlog management:

1. **Phát triển và truyền đạt rõ Product Goal.**
2. **Tạo và truyền đạt rõ Product Backlog Items.**
3. **Sắp xếp thứ tự Product Backlog Items.**
4. **Bảo đảm Product Backlog minh bạch, dễ thấy và được hiểu rõ.**

Product Owner có thể **ủy quyền thực hiện một phần công việc** liên quan Product Backlog cho người khác, chẳng hạn Developers, analyst hoặc designer, nhưng **vẫn chịu trách nhiệm giải trình**.

### Ví dụ với “Tiếp tục học”

**Người chỉ ghi yêu cầu** nhận: “Thêm nút Continue, màn hình đồng bộ video, API mới và báo cáo học tập”. Người này nhập bốn ticket, đánh số ưu tiên theo email của lãnh đạo.

**Product Owner đúng trách nhiệm** hỏi:

- Học viên đang gặp vấn đề gì khi muốn học tiếp?
- Chúng ta kỳ vọng tác động nào: giảm thời gian tìm bài, tăng khả năng hoàn tất bài học hay giảm lỗi mất tiến độ?
- Việc nào tạo ra **lát cắt giá trị nhỏ nhất nhưng an toàn**?
- Điều chưa biết nào cần kiểm chứng trước khi đầu tư đồng bộ video?
- Những ràng buộc dữ liệu, quyền học và vận hành nào phải được tôn trọng?
- Nếu có phản hồi trái với giả định ban đầu, thứ tự backlog cần thay đổi ra sao?

Product Owner không cần có sẵn mọi câu trả lời về thiết kế hoặc thị trường, nhưng cần **tổ chức việc làm rõ và chịu trách nhiệm về lựa chọn giá trị**.

### Giá trị không chỉ là số tính năng

Giá trị có thể bao gồm:

- **Người dùng:** Mở đúng bài, ít mất thời gian, giảm nhầm lẫn.
- **Chất lượng:** Ít lỗi tiến độ, giảm rủi ro dữ liệu.
- **Vận hành:** Hỗ trợ và phát hiện sự cố tốt hơn.
- **Tổ chức:** Giảm chi phí, tuân thủ nghĩa vụ, có năng lực thay đổi tiếp.

Product Owner nên làm rõ **đánh đổi** giữa các loại giá trị, không chỉ ưu tiên yêu cầu có người gửi cấp cao nhất.

## 5. Product Goal là điểm tựa, không phải danh sách task

**Product Goal** là cam kết của Product Backlog trong Scrum, mô tả trạng thái tương lai của sản phẩm để Scrum Team dùng làm mục tiêu lập kế hoạch. Product Backlog tiến hóa theo quá trình học hỏi về sản phẩm.

### Mẫu hai cách mô tả

**Không đủ định hướng:**

> “Tháng này phải làm nút Tiếp tục học, API thống kê, biểu đồ và trang cài đặt.”

**Có định hướng kết quả hơn:**

> “Học viên có thể tìm lại bài phù hợp và tiếp tục học trên tài khoản của mình mà không mất tiến độ đã xác nhận hoặc xem dữ liệu trái quyền.”

Product Goal thứ hai giúp Scrum Team chọn thứ tự theo rủi ro, giá trị và mức hiểu biết. Nó không quy định kiến trúc hoặc số ticket trước khi nhóm cùng làm rõ.

### Từ Product Goal đến các PBI có thể thảo luận

| Product Backlog Item minh họa | Vấn đề/giá trị | Bất định hoặc rủi ro | Cách làm rõ |
| --- | --- | --- | --- |
| Mở bài hợp lệ gần nhất | Giảm thao tác tìm lại bài | “Gần nhất” và quyền khóa học chưa thống nhất | Ví dụ nghiệp vụ với PO, Developers và tester |
| Hiển thị trạng thái khi chưa có bài | Không gây hiểu lầm | Phân biệt chưa học với API lỗi | AC/contract examples |
| Lưu tiến độ khi mạng gián đoạn | Tránh mất dữ liệu | Retry và xung đột hai thiết bị | Spike/test có giới hạn |
| Đồng bộ vị trí video | Tiếp tục chính xác hơn | Giá trị thực chưa rõ, chi phí kỹ thuật cao | Discovery và phân tích phản hồi |
| Quan sát lỗi mở lại bài | Phát hiện vấn đề vận hành | Thu dữ liệu thế nào không lộ thông tin riêng? | Review telemetry và chính sách dữ liệu |

Product Owner **không phải chuyên gia kỹ thuật quyết định cách cài đặt từng chức năng**. Developers thảo luận khả năng triển khai, nguy cơ và chi phí; các bên có thẩm quyền về bảo mật/dữ liệu tham gia khi cần.

### Product Backlog không phải “hộp thư yêu cầu”

Không phải mọi ý tưởng stakeholder gửi tới đều phải trở thành một PBI được cam kết xây ngay. Product Owner cần:

1. Hiểu vấn đề và kỳ vọng.
2. Kiểm tra quan hệ với Product Goal.
3. Làm rõ giá trị, rủi ro và bất định.
4. Sắp thứ tự và công khai quyết định.
5. Cập nhật khi phản hồi hoặc điều kiện thay đổi.

Điều này đòi hỏi **quyền ra quyết định có ý nghĩa**, không chỉ quyền chỉnh sửa một trường Priority trong công cụ.

## 6. Product Owner là một người chịu trách nhiệm, không phải một hội đồng

Trong Scrum, **Product Owner là một người, không phải một committee**. Product Owner có thể đại diện cho nhu cầu của nhiều stakeholders trong Product Backlog. Những người muốn thay đổi Product Backlog cần **thuyết phục Product Owner**, không bỏ qua accountability đó bằng cách giao riêng cho từng Developer.

### Những nhầm lẫn về quyền

| Nhầm lẫn | Tác động | Cách làm rõ |
| --- | --- | --- |
| “PO nhập ticket theo email của lãnh đạo” | Không ai chịu trách nhiệm quyết định giá trị | Làm rõ quyền sắp thứ tự và quyền phản hồi của PO |
| “Mọi stakeholder là một PO ngang nhau” | Nhóm nhận ưu tiên mâu thuẫn | Một PO chịu accountability; cơ chế trao đổi stakeholder minh bạch |
| “PO phải tự viết từng AC và test” | PO thành bottleneck; Developers không tham gia làm rõ | Làm rõ cùng Developers/tester; PO chịu trách nhiệm Product Backlog |
| “PO được ra lệnh cách code” | Trộn quyết định giá trị với kế hoạch kỹ thuật | PO nêu outcome/ưu tiên; Developers quyết định cách thực hiện |
| “PO có thể bỏ kiểm tra quyền để kịp demo” | Nhầm trách nhiệm giá trị với quyền miễn nghĩa vụ chất lượng | Giữ DoD và chính sách bắt buộc; đổi phạm vi hoặc chưa gọi Done |
| “PO tự mình quyết mọi vấn đề ngân sách, pháp lý” | Vượt thẩm quyền tổ chức thực tế | Phân biệt accountability Scrum và quyền được ủy quyền theo chính sách |

### Khi tổ chức chưa trao đủ quyền

Không nên chỉ yêu cầu người mang tên Product Owner **“hãy chịu trách nhiệm hơn”** nếu mọi quyết định ưu tiên bị hội đồng khác phủ quyết không minh bạch. Scrum Master có thể giúp tổ chức và stakeholders hiểu nhu cầu về accountability, giúp xử lý trở ngại hệ thống. Người có thẩm quyền tổ chức cần làm rõ **quyền quyết định thực tế** và ranh giới nghĩa vụ.

### Ủy quyền không mất accountability

PO có thể nhờ một analyst viết ví dụ nghiệp vụ, developer đề xuất cách chia PBI, designer nghiên cứu hành trình người dùng. Nhưng nếu Product Backlog mất định hướng giá trị, PO không thể nói “do người viết ticket khác chịu trách nhiệm” để bỏ qua accountability của mình.

## 7. Scrum Master không phải người giao task

Theo Scrum, Scrum Master chịu trách nhiệm **thiết lập Scrum như được định nghĩa trong Scrum Guide** và **hiệu quả của Scrum Team**. Scrum Master là người lãnh đạo phục vụ Scrum Team và tổ chức, giúp mọi người hiểu lý thuyết/thực hành Scrum.

### Scrum Master phục vụ Scrum Team bằng cách nào?

- **Huấn luyện tự quản và tính liên chức năng**: hỗ trợ Developers phối hợp, giảm phụ thuộc cá nhân và silo.
- **Giúp Scrum Team tập trung tạo Increment có giá trị cao, đạt DoD.**
- **Hỗ trợ loại bỏ trở ngại** đối với tiến triển của Scrum Team, bằng cách trực tiếp hỗ trợ hoặc giúp những người có quyền xử lý.
- **Bảo đảm các sự kiện Scrum diễn ra, mang tính tích cực, hữu ích và trong timebox**.
- **Hỗ trợ Product Owner** với kỹ thuật Product Goal, quản lý Product Backlog hiệu quả, làm rõ nhu cầu lập kế hoạch thực nghiệm và cộng tác stakeholder.
- **Hỗ trợ tổ chức** tiếp nhận Scrum, học cách làm thực nghiệm và loại bỏ rào cản giữa stakeholders với Scrum Teams.

### Scrum Master không cần làm gì để chứng minh vai trò?

- Không bắt buộc **chủ trì hoặc phát biểu nhiều nhất** ở mọi Daily Scrum.
- Không phải **người giao task, quyết định ai code ticket nào** theo Scrum.
- Không phải **thư ký cập nhật bảng cho mọi người**.
- Không phải **người phê duyệt mọi PR, yêu cầu hoặc quyết định product**.
- Không phải **người sở hữu Sprint Goal một mình**.
- Không phải **quản lý chấm điểm Developers bằng velocity hoặc số ticket**.

Scrum Master có thể giúp điều phối, huấn luyện, hỗ trợ sự kiện và công việc hành chính khi cần. Điều khác nhau là **làm để đội tăng năng lực tự quản** hay **làm thay khiến đội phải chờ người phân việc**.

### Nếu Scrum Master cũng có chức danh quản lý?

Trong thực tế một người có thể đồng thời giữ chức vụ tổ chức khác. Điều đó không tự xóa các trách nhiệm của Scrum, nhưng làm tăng nguy cơ lẫn lộn **quyền quản lý nhân sự** với **vai trò huấn luyện tự quản**.

Nếu có trường hợp này, tổ chức cần làm rõ:

1. Khi nào người ấy đang thực hiện accountability của Scrum Master?
2. Những quyết định nào thuộc quyền quản lý chính thức ngoài Scrum?
3. Developers có thể trao đổi rủi ro, lỗi và bất đồng mà không bị trừng phạt tùy tiện không?
4. Ai bảo đảm không biến Daily Scrum hoặc retrospective thành buổi chấm hiệu suất cá nhân?

Không nên suy diễn rằng Scrum Master **luôn** là cấp trên hoặc **luôn không thể** kiêm nhiệm bất kỳ vai trò nào; vấn đề thực là tính nhất quán giữa trách nhiệm Scrum, quyền tổ chức và khả năng tự quản.

## 8. Developers có quyền và trách nhiệm lập kế hoạch công việc

**Developers** trong Scrum là những người cam kết tạo ra bất kỳ khía cạnh nào của **Increment sử dụng được** mỗi Sprint, không chỉ người viết code. Tùy sản phẩm, họ có thể gồm người làm kiểm thử, thiết kế, phân tích, vận hành hoặc năng lực khác trực tiếp tham gia tạo Increment.

### Developers chịu trách nhiệm về bốn điều

1. **Tạo kế hoạch cho Sprint**: Sprint Backlog.
2. **Đưa chất lượng vào bằng cách tuân thủ Definition of Done**.
3. **Thích nghi kế hoạch mỗi ngày** hướng Sprint Goal.
4. **Chịu trách nhiệm với nhau như những người chuyên nghiệp**.

### Không đồng nghĩa “ai thích làm gì thì làm”

Tự quản cần một **mục tiêu chung, tiêu chuẩn chất lượng và tính minh bạch**. Developers có thể chọn ai làm gì, khi nào và như thế nào trong phạm vi Sprint, nhưng:

- Không bỏ qua Sprint Goal vì sở thích cá nhân.
- Không tự ý phát triển những tính năng trái Product Goal mà không trao đổi.
- Không coi Done khi chưa đạt DoD.
- Không vi phạm quyền truy cập, bảo mật hoặc nghĩa vụ tổ chức.
- Không giấu blocker, thay đổi hoặc rủi ro ảnh hưởng kế hoạch.

**Tự quản không phải không có trách nhiệm; tự quản là sở hữu trách nhiệm đối với quyết định và kết quả.**

### Một tình huống review bị nghẽn

Có ba PBI đang làm, đều chờ review và integration test. Scrum Master có thể hỏi:

> “Điều gì đang cản khả năng hoàn tất lát cắt hướng Sprint Goal? Đội muốn thử cách điều phối nào?”

Developers có thể tự quyết tạm dừng kéo việc mới, ghép cặp review, hỗ trợ kiểm thử hoặc trao đổi với đội API. **Scrum Master không cần chia từng task** để hành động được thực hiện.

## 9. Sprint Planning: ai chọn việc, ai lập kế hoạch?

**Sprint Planning** mở đầu Sprint bằng cách tạo kế hoạch cho công việc sẽ được thực hiện. Trong Scrum, toàn bộ Scrum Team cộng tác để giải quyết ba chủ đề:

1. **Why is this Sprint valuable?** Vì sao Sprint này có giá trị?
2. **What can be Done this Sprint?** Có thể hoàn tất những gì?
3. **How will the chosen work get done?** Sẽ làm những việc đã chọn như thế nào?

### Phân biệt vai trò trong ba chủ đề

| Chủ đề | Trách nhiệm trọng tâm | Ví dụ với nền tảng học tập |
| --- | --- | --- |
| **Why** | Product Owner đề xuất cách sản phẩm có thể tăng giá trị; cả Scrum Team cộng tác xác định Sprint Goal | “Người học mở được đúng bài gần nhất còn quyền” |
| **What** | Qua trao đổi với PO, **Developers chọn PBI** có thể hoàn tất trong Sprint | Chọn lát cắt hiển thị và mở một bài hợp lệ cùng xử lý trạng thái rỗng |
| **How** | **Developers lập kế hoạch thực hiện** cần thiết để tạo Increment đạt DoD | Chia việc theo hợp đồng UI–API, quyền, test và tích hợp |

Product Owner không nên ấn định sẵn **một danh sách công việc phải xong bất kể năng lực và bất định**. Scrum Master cũng không nên chia danh sách đó thành task và giao từng tên người. Developers chịu trách nhiệm dự báo những gì có thể hoàn tất, trên cơ sở thảo luận và hiểu biết thực.

### Ví dụ buổi Sprint Planning có giá trị

**Product Owner:** “Nghiên cứu gần đây cho thấy người học mất thời gian tìm bài sau khi đăng nhập. Tôi đề xuất Sprint tập trung luồng mở lại bài hợp lệ gần nhất.”

**Developer UI:** “Hợp đồng API chưa rõ trường hợp khóa hết quyền. Nếu chưa làm rõ, demo có thể sai dữ liệu.”

**Developer API:** “Có thể hoàn thành lát cắt không có đồng bộ video, nhưng phải có kiểm tra quyền server và integration test.”

**Tester trong nhóm Developers:** “Tôi đề nghị chốt ví dụ A đăng xuất, B đăng nhập và response cũ về muộn từ đầu.”

**Scrum Master:** “Đội có trở ngại nào về quyền trao đổi với nhóm danh tính hoặc môi trường test cần tôi hỗ trợ giải quyết không?”

**Cả Scrum Team:** Thống nhất Sprint Goal; Developers quyết định PBI, cách phối hợp, các phần kiểm chứng và kế hoạch trong Sprint Backlog.

### Sprint Backlog không phải kế hoạch cứng

Sprint Backlog gồm **Sprint Goal, các PBI được chọn và kế hoạch thực hiện**. Nó được Developers cập nhật trong Sprint khi học thêm. Sprint Goal cung cấp sự tập trung; có thể thương lượng **phạm vi** với Product Owner khi xuất hiện thông tin mới, không hy sinh chất lượng hoặc gây nguy hiểm cho mục tiêu.

## 10. Daily Scrum: Developers tự kiểm tra và thích nghi, không báo cáo lên trên

**Daily Scrum** là sự kiện 15 phút dành cho **Developers** của Scrum Team, nhằm kiểm tra tiến triển hướng Sprint Goal và điều chỉnh Sprint Backlog khi cần. Developers có thể chọn bất kỳ cấu trúc hoặc kỹ thuật nào giúp đạt mục đích này.

### Dấu hiệu Daily Scrum bị biến thành cuộc họp phân công

- Mọi người xếp hàng báo “hôm qua/hôm nay” cho Scrum Master hoặc quản lý.
- Sau khi nghe, Scrum Master nói từng người phải làm task nào trong ngày.
- Ai báo vướng mắc bị đánh giá là “không đủ năng suất” nên ngại công khai.
- Không ai kiểm tra Sprint Goal đang gặp rủi ro gì.
- Sau 15 phút không có quyết định về ưu tiên, hợp tác hoặc kế hoạch.

### Daily Scrum hướng mục tiêu

Ví dụ Sprint Goal: **“Người học mở lại được bài hợp lệ gần nhất”**.

Developers có thể cùng nhìn:

1. Lát cắt nào đã đạt DoD và có thể sử dụng?
2. Item nào đã già, blocked hoặc đang đe dọa Sprint Goal?
3. Có nên **ưu tiên hoàn tất review/integration** trước khi bắt đầu việc mới?
4. Kế hoạch hôm nay cần đổi thế nào do phản hồi API hoặc test?
5. Cần một cuộc trao đổi chuyên sâu sau Daily với ai?

**Scrum Master không bắt buộc là người dẫn dắt Daily Scrum**. Nếu SM tham gia, họ nên hỗ trợ mục đích sự kiện và sự tự quản. Daily Scrum cũng không cần giải quyết mọi tranh luận kỹ thuật trong 15 phút; Developers có thể tổ chức trao đổi tiếp ngay sau đó.

### Những câu hỏi “hôm qua/hôm nay/blocker” có sai không?

Không. Đó có thể là cấu trúc hữu ích nếu phục vụ **kiểm tra và thích nghi kế hoạch hướng Sprint Goal**. Sai lầm là biến bộ ba câu hỏi thành **mẫu báo cáo bắt buộc cho cấp trên**, thay mục đích thật của Daily Scrum.

## 11. Sprint Review và Retrospective: hai vòng phản hồi khác mục đích

Nếu Product Owner chỉ chép yêu cầu và Scrum Master chỉ giao việc, hai sự kiện dễ bị biến dạng nhất là **Sprint Review** và **Sprint Retrospective**.

### Sprint Review: kiểm tra kết quả sản phẩm

Trong Sprint Review, Scrum Team và stakeholders kiểm tra **kết quả của Sprint và tiến triển hướng Product Goal**, trao đổi về điều đã thay đổi trong môi trường và cùng xác định bước tiếp theo. Product Backlog có thể được điều chỉnh để phản ánh cơ hội và thông tin mới.

**Không nên:**

> “PO đọc danh sách ticket, SM công bố mỗi người hoàn thành bao nhiêu point, quản lý ký biên bản.”

**Nên hướng tới:**

> “Đội cho thấy Increment đã đạt DoD, học viên thử mở lại bài theo tình huống thật, stakeholders nêu phản hồi, Product Owner và đội kiểm tra tác động tới Product Goal và thứ tự backlog.”

Sprint Review là **working session**, không chỉ là bài trình chiếu một chiều. Nó cũng **không phải cổng phê duyệt bắt buộc để phát hành** trong Scrum. Increment có thể được giao trước Review nếu đạt DoD và đáp ứng các chính sách phát hành thực tế.

### Sprint Retrospective: kiểm tra cách làm và chất lượng

Sprint Retrospective là cơ hội Scrum Team kiểm tra **con người, tương tác, quy trình, công cụ và Definition of Done** nhằm lập kế hoạch tăng chất lượng, hiệu quả.

**Không nên:**

> “SM phê bình ai không hoàn thành task, buổi sau phân việc chặt hơn.”

**Nên hướng tới:**

> “Vì sao ba PBI bị chặn ở API? Có phải hợp đồng chưa rõ, reviewer quá ít hoặc integration test chạy quá muộn? Thay đổi nhỏ nào có thể thử trong Sprint tới?”

Scrum Master có thể giúp **điều phối buổi trao đổi**, tạo điều kiện để mọi góc nhìn được lắng nghe và giúp đội theo dõi hành động cải tiến. Nhưng **những người làm việc thực tế cùng sở hữu hành động và khả năng học hỏi**; SM không phải người tự viết 20 yêu cầu cải tiến rồi chia việc như quản lý.

### Phản hồi về sản phẩm khác phản hồi về cách làm

| Vòng phản hồi | Câu hỏi chính | Ai góp phần? | Kết quả |
| --- | --- | --- | --- |
| **Sprint Review** | Chúng ta đã tạo được giá trị gì, có cần điều chỉnh hướng sản phẩm? | Scrum Team và stakeholders phù hợp | Hiểu biết về Increment, Product Goal, Product Backlog |
| **Sprint Retrospective** | Chúng ta cần nâng chất lượng và hiệu quả hợp tác thế nào? | Scrum Team | Một vài thử nghiệm/cải tiến cách làm có trách nhiệm |

Hai vòng liên quan nhưng không thay nhau. Một đội có thể demo rất đẹp mà cách làm không bền vững; cũng có thể rất hòa thuận nhưng tính năng không giúp người học.

## 12. Cùng một user story, ba accountability phối hợp ra sao?

Xét user story minh họa:

> **Là** học viên đã đăng nhập, **tôi muốn** tiếp tục bài phù hợp gần nhất của mình **để** không phải tìm lại vị trí học.

Đây là cách mô tả để khởi đầu trao đổi, **không phải đặc tả đầy đủ**. Những ví dụ về quyền, dữ liệu và lỗi cần được làm rõ.

### Acceptance Criteria được thảo luận cùng nhau

| Tình huống | Kỳ vọng cần xác nhận |
| --- | --- |
| Có bài hợp lệ đã học | Hệ thống mở đúng bài mà tài khoản còn quyền |
| Không có bài hợp lệ | UI hiển thị trạng thái rõ, không tạo nội dung giả |
| Khóa học bị thu hồi quyền | Không được trả/hiển thị tiến độ riêng trái quyền |
| API tạm thời không đọc được dữ liệu | Không nhầm lỗi thành “chưa từng học” |
| A đăng xuất, B đăng nhập cùng thiết bị | Response cũ của A không được đưa vào phiên của B |
| Hai thiết bị cập nhật gần nhau | Có quy tắc giải quyết xung đột được làm rõ và kiểm chứng |

### Một cuộc đối thoại có trách nhiệm

**Product Owner:** “Mục tiêu quan trọng nhất lúc này là học viên mở được đúng bài còn quyền. Chúng ta chưa có bằng chứng rằng đồng bộ video theo từng giây mang lại giá trị đủ lớn.”

**Developer:** “Với API hiện có, có thể cung cấp bài hợp lệ gần nhất nhưng chưa có cơ chế chắc chắn để giải quyết hai cập nhật đồng thời.”

**Tester trong Developers:** “Tôi đề nghị kiểm tra chéo tài khoản và API timeout từ đầu vì hai trường hợp này có thể gây hại hoặc gây hiểu lầm.”

**Scrum Master:** “Có ai cần hỗ trợ liên hệ nhóm danh tính để xác nhận quyền không? Những điều nào đội có thể tự giải quyết ngay?”

**Product Owner:** “Tôi sẽ làm rõ trường hợp quyền bị thu hồi với người chịu trách nhiệm nghiệp vụ và cập nhật PBI.”

**Developers:** “Chúng tôi sẽ chọn lát cắt nhỏ, chốt contract, chia công việc, phối hợp test và tự điều chỉnh khi có thông tin mới.”

### Điểm cần nhận ra

- Product Owner **không phải người duy nhất được viết acceptance criteria**; PO chịu trách nhiệm Product Backlog minh bạch và hướng giá trị.
- Scrum Master **không quyết định thứ tự kỹ thuật hoặc giao từng task**; SM giúp đội có khả năng phối hợp và xử lý trở ngại.
- Developers **không chỉ đợi yêu cầu hoàn hảo rồi code**; họ chủ động làm rõ, lập kế hoạch, chia sẻ rủi ro và tạo Increment đạt DoD.
- Chính sách dữ liệu, bảo mật hoặc quyền quyết định của tổ chức vẫn áp dụng, không bị thay bằng cuộc đối thoại Scrum.

## 13. Khi stakeholder giao task trực tiếp cho Developers

### Tình huống

Giữa Sprint, một giám đốc gửi tin nhắn trực tiếp cho developer UI:

> “Mai phải có biểu đồ học tập mới. Bỏ việc đang làm, chuyển ngay sang task này. PO chỉ cần nhập bổ sung vào Jira.”

Nếu developer làm ngay mà không trao đổi, Sprint Goal có thể bị đe dọa, các PBI đang làm dở kéo dài và phụ thuộc mới xuất hiện. Nếu Scrum Master lập tức ra lệnh “Không được nghe giám đốc!”, vấn đề quyền quyết định vẫn chưa được xử lý.

### Cách xử lý có trách nhiệm

1. **Làm rõ mục tiêu và mức khẩn:** Biểu đồ giải quyết vấn đề gì, có cam kết bên ngoài hay rủi ro không thể chờ?
2. **Minh bạch thông tin tới Product Owner và Scrum Team:** Tránh có “backlog ẩn” qua tin nhắn cá nhân.
3. **Product Owner đánh giá giá trị và thứ tự:** Điều chỉnh Product Backlog dựa trên thông tin, trade-off và trách nhiệm.
4. **Developers đánh giá tác động tới kế hoạch Sprint:** Việc mới có làm mất khả năng đạt Sprint Goal hoặc chất lượng Increment không?
5. **Thương lượng phạm vi nếu cần:** Trong Sprint, có thể làm rõ và điều chỉnh phạm vi với PO khi học thêm, nhưng không làm nguy hiểm Sprint Goal hoặc giảm DoD.
6. **Scrum Master hỗ trợ xử lý trở ngại tổ chức:** Giúp stakeholders hiểu luồng quyết định và Scrum; không trở thành người ra lệnh thay PO hoặc Developers.

### Nếu đây thật sự là vấn đề nghiêm trọng cần xử lý ngay?

Ví dụ có lỗ hổng bảo mật production làm lộ dữ liệu học viên. Đội cần kích hoạt **quy trình ứng phó sự cố có thẩm quyền** theo chính sách, không viện lý do “Sprint đang khóa” để trì hoãn xử lý. Scrum Team minh bạch tác động, điều chỉnh kế hoạch thích hợp và tôn trọng các ranh giới chất lượng.

**Agile không đồng nghĩa bỏ cam kết hoặc bỏ an toàn**; nó tạo khả năng xử lý thay đổi có lý do, đúng quyền và dữ liệu.

## 14. Khi Product Owner bị vô hiệu hóa bởi một hội đồng ưu tiên

### Dấu hiệu

- Cả ba trưởng bộ phận đều có quyền đánh dấu ticket của mình là “Critical”.
- Product Owner không được phép sắp thứ tự lại Product Backlog.
- Developers nhận các yêu cầu mâu thuẫn từ nhiều đầu mối.
- Mỗi tuần Scrum Master phải hỏi “nên giao người nào cho yêu cầu nào?”.
- Không có một Product Goal đủ rõ để giải thích đánh đổi.

### Tác hại

Nhóm có nhiều **đơn hàng cạnh tranh** nhưng không có quyết định minh bạch về giá trị. Việc đang làm bị ngắt liên tục; WIP, blocked và rework tăng. Người mang chức danh PO bị quy trách nhiệm khi không đạt KPI nhưng lại thiếu quyền giải quyết mâu thuẫn.

### Cách cải tiến

**Trước hết**, xác minh quyền và nghĩa vụ thực của tổ chức: ngân sách, hợp đồng, chính sách, người có thẩm quyền chiến lược. Scrum không tự cấp cho PO mọi quyền pháp lý hoặc tài chính.

**Tiếp theo**, trao đổi rõ: Product Owner cần được tổ chức **tôn trọng quyết định liên quan tới Product Backlog** theo Scrum. Stakeholders có thể đề xuất, cung cấp thông tin, phản biện; không nên dùng những kênh ngầm để ra lệnh cho từng Developer như thể Product Backlog không tồn tại.

**Cuối cùng**, chọn cơ chế:

- Một người PO có accountability và khả năng ra quyết định Product Backlog.
- Product Goal và tiêu chí đánh đổi được truyền đạt minh bạch.
- Kênh tiếp nhận stakeholder có phản hồi, không phải hộp thư một chiều.
- Những ngoại lệ do nghĩa vụ cấp tổ chức có **quyền, điều kiện và cách leo thang rõ**.
- Scrum Master hỗ trợ tổ chức điều chỉnh thói quen giao việc tạo xung đột.

### Điều không nên làm

Không giải quyết bằng cách đổi tên hội đồng thành “Product Owner Committee” rồi tiếp tục giao trực tiếp task. Trong Scrum, PO là **một người** chịu accountability; những đóng góp từ nhiều stakeholders vẫn cần được xử lý qua cơ chế sản phẩm.

## 15. Khi Scrum Master “sở hữu blocker” thay cả nhóm

Một cách hiểu sai phổ biến:

> “Bất cứ ai bị chặn đều báo Scrum Master; Scrum Master có trách nhiệm tự giải quyết toàn bộ.”

Scrum Master có trách nhiệm hỗ trợ **loại bỏ trở ngại** và giúp tổ chức tăng hiệu quả Scrum, nhưng không có nghĩa mọi trở ngại phải được chuyển thành task cá nhân của SM.

### Phân biệt các loại trở ngại

| Trở ngại | Chủ thể có thể trực tiếp xử lý | Scrum Master hỗ trợ thế nào? |
| --- | --- | --- |
| Hai developer chưa thống nhất cách test | Developers cùng trao đổi và thử giải pháp | Huấn luyện cách giải quyết bất đồng và cộng tác |
| API contract chưa rõ | Developers provider/consumer, người có quyền nghiệp vụ | Kết nối đúng người khi phụ thuộc kéo dài |
| Item chờ review do WIP quá cao | Developers tự phối hợp, ưu tiên hoàn tất | Giúp minh bạch flow và thử cải tiến workflow |
| PO không được quyền sắp Product Backlog | Người có thẩm quyền tổ chức và PO | Hỗ trợ làm rõ Scrum accountability với stakeholders |
| Môi trường test luôn không sẵn sàng | Nhóm sở hữu hạ tầng cùng Developers | Giúp giải quyết trở ngại liên tổ chức và phát triển năng lực |
| Kiểm soát bảo mật chưa được đáp ứng | Người thực hiện và chuyên môn bảo mật có thẩm quyền | Hỗ trợ phối hợp, không tự miễn nghĩa vụ |

### Dấu hiệu Scrum Master đang trở thành bottleneck

- Developers chờ SM sắp lịch review dù có thể tự liên hệ đúng người.
- Mọi quyết định kỹ thuật đều phải “được SM duyệt”.
- Sprint Backlog chỉ SM được chỉnh sửa.
- Khi SM nghỉ, Daily Scrum không thể diễn ra hoặc không ai biết ưu tiên hỗ trợ việc đang mở.

### Cách chuyển từ làm thay sang phát triển năng lực

Thay vì “Đưa tôi ticket, tôi sẽ xử lý”, Scrum Master có thể:

1. Hỏi **điều gì thật sự ngăn Developers hoàn tất**.
2. Làm rõ nhóm có thể tự làm gì ngay, ai cần tham gia.
3. Giúp đội tạo **cơ chế tiếp cận người có thẩm quyền**.
4. Hỗ trợ khi rào cản vượt phạm vi nhóm hoặc lặp lại có tính hệ thống.
5. Xem sau lần xử lý, đội có **tự chủ hơn** hay phụ thuộc vào SM hơn.

Mục tiêu là giảm thời gian chờ và tăng năng lực phối hợp, không tăng số việc đi qua tay Scrum Master.

## 16. Khi Developers tự quản nhưng không phối hợp với nhau

Một cực đoan khác là hiểu self-management thành:

> “Mỗi người tự chọn task mình thích, không cần trao đổi với ai.”

Điều này cũng không phù hợp Scrum. Developers cùng chịu trách nhiệm về **Sprint Backlog, Increment đạt DoD, tiến triển hướng Sprint Goal và chất lượng**. Tự quản mang nghĩa **đội tự quyết cách phối hợp**, không phải mỗi cá nhân độc lập tối ưu điểm riêng.

### Ví dụ

Tất cả Developers chọn task xây giao diện mới vì dễ demo; không ai muốn sửa lỗi phân quyền và integration test. Cuối Sprint có nhiều màn hình đẹp nhưng không có Increment sử dụng được.

**Cách làm phù hợp hơn:**

- Nhìn lại Sprint Goal và những PBI cần đạt DoD.
- Chủ động giải quyết vùng ít người muốn làm nhưng ảnh hưởng chất lượng.
- Pairing hoặc swarming ở công việc khó/phụ thuộc để giảm nút thắt.
- Chia sẻ hiểu biết thay vì giữ độc quyền một module.
- Điều chỉnh Sprint Backlog theo diễn biến thật.

### Trách nhiệm với nhau không đồng nghĩa giám sát cá nhân

Developers có thể làm rõ cam kết, hỗ trợ, xem lại kết quả và nêu vấn đề chuyên môn. Không nên dùng việc “chịu trách nhiệm với nhau” để công khai chỉ trích cá nhân hoặc biến Daily Scrum thành báo cáo thưởng phạt.

## 17. Khi yêu cầu thay đổi trong Sprint: ai quyết định điều gì?

Scrum không yêu cầu Sprint Backlog bất biến và cũng không cho phép thay đổi tùy tiện làm mất mục tiêu.

### Phân biệt các loại điều chỉnh

| Tình huống | Cách phản ứng thích hợp | Ranh giới |
| --- | --- | --- |
| Cách triển khai khó hơn dự báo | Developers điều chỉnh kế hoạch, minh bạch tác động | Không hạ DoD |
| Một PBI cần làm rõ ví dụ | PO và Developers trao đổi, refine thông tin | Giữ hướng Sprint Goal |
| Có cơ hội giá trị mới | PO cập nhật Product Backlog; Scrum Team xem tác động Sprint | Không kéo việc vào Sprint qua kênh ngầm |
| Lỗi chất lượng trong Increment | Developers ưu tiên sửa và kiểm chứng theo DoD | Không gọi Done nếu chưa đáp ứng |
| Sự cố production cần ứng phó khẩn | Kích hoạt quyền/chính sách ứng phó, minh bạch ảnh hưởng | Không dùng Sprint để cản an toàn |
| Sprint Goal trở nên lỗi thời | **Product Owner có quyền hủy Sprint** theo Scrum Guide | Chỉ khi Sprint Goal trở nên lỗi thời; xem hậu quả và hướng tiếp |

### Một ví dụ đổi phạm vi có trách nhiệm

Đội phát hiện đồng bộ vị trí video đa thiết bị phức tạp hơn dự báo. Nếu Sprint Goal là **“Học viên có thể mở đúng bài gần nhất còn quyền”**, Developers và PO có thể trao đổi để:

- Giữ lát cắt mở bài an toàn và đạt DoD.
- Đưa đồng bộ từng giây về Product Backlog để làm rõ khi có bằng chứng giá trị.
- Không xóa integration test phân quyền hoặc kiểm tra dữ liệu để gọi Done.
- Minh bạch thay đổi và phản hồi ở Sprint Review.

**Linh hoạt phạm vi** không phải giấy phép để xóa mục tiêu, tiêu chuẩn chất lượng hay trách nhiệm giải trình.

## 18. Definition of Done: trách nhiệm chất lượng không thuộc riêng PO, SM hay tester

**Definition of Done (DoD)** mô tả chính thức trạng thái Increment khi đáp ứng các tiêu chuẩn chất lượng của sản phẩm. Nếu có chuẩn ở cấp tổ chức, Scrum Team tuân thủ ít nhất chuẩn đó; nếu không có, Scrum Team cần tạo DoD phù hợp. Khi nhiều Scrum Team cùng làm **một sản phẩm**, họ phải cùng định nghĩa và tuân thủ một DoD.

### Ai chịu trách nhiệm trong thực tế?

- **Developers** chịu trách nhiệm đưa chất lượng vào bằng cách tuân thủ DoD khi tạo Increment.
- **Product Owner** quan tâm giá trị và tính minh bạch của phần đã hoàn thành, không dùng áp lực deadline để hạ DoD.
- **Scrum Master** hỗ trợ mọi người hiểu và thực hiện Scrum, giúp nhóm vượt trở ngại đối với Increment có giá trị và chất lượng.
- **Những người có thẩm quyền bảo mật, dữ liệu, vận hành, hợp đồng** thực hiện trách nhiệm theo chính sách khi liên quan; Scrum không thay các nghĩa vụ đó.

### Mẫu DoD minh họa cho “Tiếp tục học”

| Chiều chất lượng | Điều cần kiểm chứng | Bằng chứng có thể dùng |
| --- | --- | --- |
| Nghiệp vụ | Mở đúng bài hợp lệ, xử lý trạng thái rỗng và lỗi | Acceptance tests và ví dụ người dùng |
| Tích hợp | UI–API–danh tính hoạt động theo contract | Contract/integration tests |
| Phân quyền | Không đọc tiến độ người khác qua API hay cache | Security integration test |
| Dữ liệu | Retry/concurrency không gây ghi lùi trái quy tắc | Test giao dịch/version theo rủi ro |
| Kỹ thuật | Kiểm tra CI, review theo chính sách đạt | Build/test report, PR |
| Vận hành | Có quan sát và ứng phó phù hợp thay đổi | Telemetry/runbook khi cần |

Đây là **ví dụ minh họa**, không phải một DoD bắt buộc cho mọi sản phẩm. Điều kiện kiểm chứng cần phù hợp rủi ro và tiêu chuẩn thực của tổ chức.

### Ba ngộ nhận cần tránh

1. **“PO chấp nhận là Done.”** Việc PO hài lòng với demo không làm một Increment thiếu test bắt buộc tự đạt DoD.
2. **“SM ký cho chuyển cột Done.”** Scrum Master không phải cổng chất lượng thay Developers.
3. **“Tester phải tự bảo đảm mọi lỗi.”** Quality là trách nhiệm của Scrum Team; Developers có accountability về việc tuân thủ DoD, dù thành viên có chuyên môn khác nhau.

## 19. Nhiều nhóm cùng một sản phẩm: không nhân bản PO và SM theo phòng ban

Khi nhiều Scrum Team cùng làm **một sản phẩm**, họ chia sẻ Product Goal, Product Backlog và Product Owner. Các Scrum Team cùng sản phẩm phải **cùng định nghĩa và tuân thủ Definition of Done**.

### Ví dụ ba nhóm

- **Nhóm Giao diện học viên** phát triển trải nghiệm mở bài.
- **Nhóm Tiến độ** phát triển API và dữ liệu.
- **Nhóm Danh tính** xây và vận hành kiểm soát quyền.

Nếu tất cả là các Scrum Team cùng làm **một sản phẩm theo phạm vi Product**, mỗi nhóm không nên được cấp một “PO giả” chỉ để nhận phần yêu cầu chuyên môn rồi cạnh tranh ưu tiên. Cần một **Product Owner có accountability với Product Backlog chung** theo Scrum, dù có nhiều người hỗ trợ làm rõ và chuyên môn khác nhau.

### Điều phối kỹ thuật vẫn cần người sở hữu chuyên môn

Scrum không bắt Product Owner tự thiết kế API, không bắt Scrum Master tự viết contract test. Các Developers và người có trách nhiệm liên quan phối hợp:

1. Thống nhất lát cắt giá trị và ví dụ nghiệp vụ.
2. Chốt contract và quyền dữ liệu sớm.
3. Tích hợp thường xuyên thay vì bàn giao một lô code cuối Sprint.
4. Kiểm chứng Increment với DoD chung.
5. Dùng Sprint Review và phản hồi người dùng để điều chỉnh Product Backlog.

### Một điều cần phân biệt

Không phải cứ hai nhóm làm việc với cùng khách hàng thì Scrum bắt buộc họ có chung PO; cần xem **đó có thực sự là cùng một sản phẩm hay không**. Ranh giới sản phẩm, trách nhiệm và cấu trúc tổ chức phải được làm rõ, không suy chỉ từ tên bộ phận.

### Scrum of Scrums không phải một tầng phân công

Scrum of Scrums có thể là cơ chế phối hợp tùy chọn, **không phải một sự kiện chính thức bắt buộc của Scrum Guide**. Nếu hoạt động này chỉ để một người phân task cho tất cả các nhóm, nó tái tạo sai lầm ban đầu ở quy mô lớn hơn.

## 20. Liên hệ với Kanban và XP: đừng để trách nhiệm Scrum cản cải tiến kỹ thuật

Scrum mô tả framework để tạo giá trị trong điều kiện phức tạp; nó không chỉ định một công cụ board, một kỹ thuật estimation hoặc một kiểu branching bắt buộc. Các thực hành Kanban và XP có thể hỗ trợ Scrum Team nếu phục vụ mục đích và không phá vỡ những thành phần của Scrum.

### Kanban giúp đội phát hiện điều gì?

| Vấn đề | Thực hành có thể dùng | Giá trị |
| --- | --- | --- |
| SM phân task mới liên tục, WIP tăng | Visualization và WIP limit | Ưu tiên hoàn tất trước khi bắt đầu thêm |
| Review chờ lâu nhưng mỗi cá nhân vẫn “bận” | Work item age và blocked time | Thấy bottleneck của dòng công việc |
| Sprint hay bị bất ngờ bởi phụ thuộc | Explicit policies và flow review | Minh bạch điều kiện chuyển trạng thái |
| Dự báo chỉ dựa trên cảm giác của một người | Cycle time và throughput có định nghĩa | Kiểm tra khả năng hoàn tất trong bối cảnh thực |

Các chỉ số flow không thay **Product Goal, Sprint Goal hoặc DoD**; chúng cung cấp tín hiệu giúp đội quản lý công việc.

### XP giúp Developers thực hiện quyền tự quản có chất lượng

- **TDD** giúp làm rõ hành vi và nhận phản hồi sớm.
- **Pair programming** giúp giảm phụ thuộc vào một chuyên gia và chia sẻ kỹ năng.
- **Continuous Integration** phát hiện lệch hợp đồng, build hoặc test sớm.
- **Refactoring** giữ thiết kế dễ thay đổi sau khi có đủ test.
- **Small releases** có thể giảm kích thước thay đổi và tăng feedback khi đạt chất lượng.

Nếu Developers được tự chọn cách làm nhưng thiếu CI và kiểm thử, quyền tự quản dễ biến thành nhiều nhánh dài và lỗi phát hiện muộn. Scrum Master có thể hỗ trợ đội nhận ra trở ngại và cải thiện khả năng cộng tác; Product Owner có thể giúp cân đối công việc chất lượng với Product Goal; Developers chọn và triển khai kỹ thuật.

### Không gọi Kanban là Scrum rồi bỏ trách nhiệm

Một đội vận hành chuyên xử lý sự cố liên tục có thể chọn cách **flow-first với Kanban** theo bối cảnh, nhưng không phải vì vậy PO/SM nếu đã tuyên bố dùng Scrum được tùy ý đổi thành người ghi ticket/phân việc. Hãy **gọi đúng mô hình đang áp dụng** và đánh giá hiệu quả thực tế.

## 21. Tình huống xuyên suốt: một sản phẩm, một Product Goal, một đội đang bị phân công

### 21.1. Bối cảnh ban đầu

Scrum Team gồm:

- Một Product Owner có chức danh nhưng chủ yếu nhận email từ ba trưởng bộ phận.
- Một Scrum Master hằng sáng phân task dựa trên ước lượng giờ và số story point.
- Developers gồm người hiểu giao diện, API, dữ liệu và kiểm thử.

Product Goal được viết chung chung là “Nâng cấp trải nghiệm học tập”. Trong ba Sprint gần đây, nhiều task được đóng nhưng chức năng **“Tiếp tục học”** vẫn chưa được người dùng thử trên một đường đi tích hợp đạt DoD.

### 21.2. Dữ liệu ban đầu giả định

| Sprint | Ticket kỹ thuật được đóng | PBI đạt DoD | Lỗi tích hợp phát hiện muộn | Phản hồi học viên thực |
| --- | ---: | ---: | ---: | --- |
| 1 | 28 | 0 | 5 | Không có Increment để thử |
| 2 | 34 | 1 | 4 | Chỉ có demo nội bộ, chưa có kiểm chứng với người học |
| 3 | 31 | 1 | 6 | Một góp ý nhưng chưa ảnh hưởng Product Backlog |

**Số liệu đều là giả định để học**, không đại diện một tổ chức thật. Bảng không chứng minh người nào kém năng lực, và bản thân số lỗi tích hợp còn phụ thuộc khả năng phát hiện/định nghĩa lỗi.

### 21.3. Truy nguyên cơ chế

Nhóm xem lại một PBI chưa hoàn thành:

~~~text
Ngày 1: PO nhận yêu cầu từ quản lý, tạo ticket lớn.
Ngày 2: SM phân UI cho A, API cho B, test cho C.
Ngày 3-5: A làm UI theo mock, B còn chờ quy tắc quyền.
Ngày 6: A đóng ticket UI, báo đã "Done".
Ngày 7: Reviewer B bận sửa sự cố, không ai hỗ trợ review.
Ngày 8: API trả trạng thái lỗi khác mock; UI cần sửa.
Ngày 9: Test chéo tài khoản phát hiện sai phiên.
Ngày 10: Sprint Review trình bày slide; không có Increment đạt DoD.
~~~

### 21.4. Phân tích đúng vấn đề

**Không phải:** “SM chia việc chưa khéo” hoặc “PO nhập yêu cầu chưa đủ chi tiết”.

**Đúng hơn:**

1. Product Goal chưa được cụ thể hóa đủ để chọn mục tiêu Sprint có giá trị.
2. PO không có quyền hoặc cơ chế đưa phản hồi người dùng vào thứ tự backlog.
3. Developers bị phân việc theo kỹ năng cá nhân, không cùng sở hữu lát cắt tích hợp.
4. Công việc kéo vào quá nhiều; thiếu ưu tiên hoàn tất và xử lý phụ thuộc.
5. DoD không được dùng làm ranh giới rõ của Increment.
6. Scrum Master đang duy trì một cách phối hợp làm **tăng phụ thuộc vào việc phân công**.

### 21.5. Thay đổi trách nhiệm trước khi đổi công cụ

**Product Owner** cùng stakeholders xác nhận mục tiêu:

> “Trong giai đoạn hiện tại, giúp học viên mở đúng bài gần nhất còn quyền, giảm thao tác tìm lại bài và không gây mất tiến độ.”

**Developers** cùng PO chọn PBI có thể hoàn tất; họ tự thiết kế cách chia việc, phối hợp contract UI–API, test quyền và các bước tích hợp, thay vì chờ một danh sách task đã gắn sẵn tên người.

**Scrum Master** tập trung hỗ trợ:

- Scrum Team hiểu và sử dụng đúng Sprint Goal, DoD và các sự kiện.
- Stakeholders tôn trọng quyết định Product Backlog qua PO.
- Người làm API, giao diện và kiểm thử có cơ chế trao đổi sớm.
- Các trở ngại về môi trường/reviewer được giải quyết theo quyền thực, không dồn vào SM mãi.

### 21.6. Sprint Goal và lát cắt mới

Sprint Goal được Scrum Team xác định:

> “Học viên đã xác thực có thể đi từ trang chủ tới bài học gần nhất còn quyền, với trạng thái lỗi rõ ràng và không lộ tiến độ của tài khoản khác.”

Developers chọn lát cắt nhỏ hơn, **chưa bao gồm đồng bộ video từng giây**. Kế hoạch tích hợp bao gồm:

1. Chốt ví dụ nghiệp vụ “bài gần nhất” và quyền.
2. Thống nhất contract API.
3. Xây unit/contract/integration tests liên quan.
4. Tích hợp UI–API–Identity sớm.
5. Kiểm chứng DoD, bao gồm đổi tài khoản và response cũ.
6. Nhận feedback về khả năng tìm và mở bài.

### 21.7. Quan sát sau thử nghiệm

Thay vì kết luận thành công vì “SM đã ngừng chia việc”, đội xem:

- PBI nào **thực sự đạt DoD**?
- Work item age, cycle time, blocked time có giảm với loại item tương tự không?
- Lỗi phát hiện muộn, rework và sự cố dữ liệu thay đổi thế nào?
- Scrum Team có thể **tự xử lý review/contract** mà không chờ SM không?
- Product Owner có thể giải thích **tại sao** PBI này được ưu tiên hơn PBI khác?
- Có phản hồi học viên nào đã làm thay đổi Product Backlog?

Nếu cùng kỳ tổ chức bổ sung nhân sự hoặc sửa CI, phải ghi những yếu tố đó; không tự quy toàn bộ kết quả cho việc đổi cách điều phối.

## 22. Tình huống khó: PO muốn giá trị sớm, Developers cần chất lượng, SM bị yêu cầu “ép deadline”

### 22.1. Vấn đề

Trước Sprint Review, Product Owner muốn demo chức năng “Tiếp tục học” cho stakeholders. Integration test phát hiện response của tài khoản A có thể hiển thị sau khi B đăng nhập. Một quản lý nói:

> “SM hãy giao thêm người và yêu cầu đội đánh dấu Done. PO đã chấp nhận tính năng rồi, chỉ cần bật feature flag sau buổi demo.”

### 22.2. Vì sao cả hai đề nghị đều chưa đúng?

- **PO đã chấp nhận** không thay Definition of Done nếu kiểm tra quyền là tiêu chuẩn bắt buộc.
- **SM giao thêm người** không tự giải quyết cơ chế lỗi và không phải trách nhiệm phân task được Scrum định nghĩa.
- **Feature flag** có thể giúp tách deploy với mở tính năng, nhưng không khiến một nhánh đã biết có lỗi nghiêm trọng trở nên đạt DoD.
- Một demo trên dữ liệu giả có thể hỗ trợ thảo luận, nhưng **không nên bị trình bày là Increment hoàn thành nếu chưa đạt DoD**.

### 22.3. Phân chia trách nhiệm khi xử lý

**Developers:** Giữ trạng thái chưa Done, tái hiện lỗi bằng dữ liệu an toàn, đánh giá nguyên nhân ở session/cache/API, tự tổ chức kiểm thử và sửa.

**Product Owner:** Hiểu tác động tới Product Goal, trao đổi với stakeholders về phạm vi có thể giao và những điều vẫn chưa hoàn thành; sắp thứ tự tiếp theo.

**Scrum Master:** Hỗ trợ Scrum Team và tổ chức hiểu DoD, bảo vệ vòng minh bạch–kiểm tra–thích nghi; giúp loại bỏ trở ngại về phối hợp nếu có.

**Người có thẩm quyền bảo mật/vận hành:** Tham gia khi chính sách và mức rủi ro yêu cầu.

### 22.4. Kết quả phù hợp

Đội có thể:

1. Sửa lỗi và kiểm chứng, nếu đủ điều kiện trong Sprint.
2. Thu hẹp phạm vi để giao **một lát cắt khác đạt DoD**, nếu có.
3. Trình bày minh bạch tại Sprint Review những gì đã học và chưa Done.
4. Cập nhật kế hoạch/backlog sau phản hồi.

**Không phương án nào cần biến SM thành người cưỡng ép hoàn thành** hoặc PO thành người ký duyệt chất lượng thay Developers.

## 23. Tình huống khó: Scrum Master thực hiện công việc hành chính có phải luôn sai?

Không phải mọi lần Scrum Master **giúp ghi chú, gửi lời mời họp, cập nhật bảng hoặc tạo ticket hỗ trợ** đều sai. Một người có thể chủ động hỗ trợ đội khi việc đó hữu ích và được thỏa thuận.

Sai lầm nằm ở **cơ chế phụ thuộc kéo dài**:

- Developers không thể tự tổ chức Daily Scrum nếu thiếu SM.
- PO chỉ trao đổi được với stakeholders khi SM chuyển lời.
- Mọi task bắt buộc có tên người giao và người nhận do SM điền.
- SM phải duyệt mọi lần đổi Sprint Backlog.
- Việc hành chính chiếm hết năng lực hỗ trợ đội và tổ chức cải tiến Scrum.

### Phép thử “trao quyền hay làm thay?”

| Câu hỏi | Hỗ trợ có ích | Làm thay gây phụ thuộc |
| --- | --- | --- |
| Vì sao SM làm? | Giúp giải quyết trở ngại tạm thời, huấn luyện quy trình tốt | Vì đội không được phép tự làm |
| Ai ra quyết định? | Người có accountability đúng | SM quyết thay PO hoặc Developers |
| Có cơ chế chuyển giao năng lực? | Có hướng dẫn, công cụ, người dự phòng | Không; khi SM vắng thì công việc dừng |
| Kết quả học hỏi? | Đội tự phối hợp tốt hơn theo thời gian | Đội phải chờ SM nhiều hơn |
| Đo tác động thế nào? | Giảm blocked/queue, chất lượng giữ ổn định | Đếm số task SM phân hoặc số họp đã tổ chức |

### Một kế hoạch chuyển tiếp

Nếu lâu nay SM luôn điều hành Daily Scrum, có thể:

1. Minh bạch **mục đích Daily Scrum** và thảo luận với Developers.
2. Cùng chọn một cách kiểm tra Sprint Goal phù hợp.
3. Developers tự điều hành và điều chỉnh Sprint Backlog; SM quan sát/hỗ trợ khi cần.
4. Phản hồi ở Retrospective, kiểm tra khả năng đội tự vận hành.
5. Mở rộng việc tự chủ sang review, xử lý phụ thuộc và cải tiến workflow.

Không cần thay đổi bằng mệnh lệnh “Từ mai SM không được làm gì”. Mục tiêu là phát triển năng lực và trách nhiệm thực, không tạo khoảng trống hỗ trợ.

## 24. Ma trận quyết định: giá trị, kế hoạch, chất lượng và ràng buộc

Một cách giảm nhầm lẫn là làm rõ **loại quyết định**, thay vì lập sơ đồ cấp trên–cấp dưới giữa PO, SM và Developers.

| Quyết định hoặc hoạt động | Trọng tâm accountability | Người cần cộng tác/đóng góp | Điều không nên suy diễn |
| --- | --- | --- | --- |
| Xác định hướng giá trị và truyền đạt Product Goal | **Product Owner** | Scrum Team, stakeholders, người dùng | PO tự quyết mọi luật, ngân sách hoặc chính sách ngoài thẩm quyền |
| Tạo, làm rõ và sắp Product Backlog | **Product Owner** | Developers, chuyên gia, stakeholders; có thể ủy quyền thực hiện | PO phải tự nhập từng ticket |
| Phát triển Sprint Goal | **Cả Scrum Team** qua Sprint Planning | PO đề xuất giá trị, Developers thảo luận tính khả thi | SM hoặc quản lý tự ấn định mục tiêu |
| Chọn PBI có thể Done trong Sprint | **Developers** qua thảo luận với PO | PO làm rõ thứ tự và ngữ nghĩa | PO/SM giao sẵn danh sách bất kể năng lực |
| Lập và thích nghi Sprint Backlog | **Developers** | PO khi cần thương lượng phạm vi, chuyên môn liên quan | SM là người duy nhất được sửa bảng |
| Tạo Increment và tuân thủ DoD | **Developers** trong Scrum Team | Product Owner, chuyên môn kiểm thử/bảo mật/vận hành phù hợp | PO hoặc SM ký là chất lượng tự động đạt |
| Thiết lập Scrum và nâng hiệu quả Scrum Team | **Scrum Master** | Toàn Scrum Team và tổ chức | SM là quản lý phân task hoặc chủ sở hữu mọi blocker |
| Ưu tiên khi có cơ hội giá trị mới | **Product Owner** với Product Backlog | Developers để hiểu tác động, stakeholders liên quan | Stakeholder bỏ qua PO để giao task trực tiếp |
| Hủy Sprint nếu Sprint Goal lỗi thời | **Product Owner** theo Scrum Guide | Scrum Team cần trao đổi hậu quả và hướng tiếp | SM hủy vì dashboard chưa đạt velocity |
| Thực hiện ứng phó sự cố/bảo mật bắt buộc | **Vai trò có quyền theo chính sách tổ chức** | Scrum Team, chủ dịch vụ, bảo mật | Scrum tự thay thế thẩm quyền rủi ro |

### Ma trận là công cụ đối thoại, không phải bản phân việc cứng

Từng hoạt động có thể do nhiều người cùng thực hiện. Ví dụ Developers giúp viết PBI nhưng PO vẫn chịu accountability Product Backlog; SM giúp tổ chức workshop user story nhưng không trở thành Product Owner; PO có thể tham gia xem integration test để hiểu rủi ro nhưng không tự đặt cách test thay chuyên môn.

**Đừng biến ma trận này thành một RACI cơ học yêu cầu chữ ký của tất cả những người được nêu** cho mọi task. Mục tiêu là giảm mơ hồ quyền, không tạo thêm cổng phê duyệt.

## 25. Đo chất lượng của việc trao quyền, không đo số task được giao

Đội không thể chứng minh “Scrum Master đã phục vụ tốt” bằng số ticket giao mỗi ngày, cũng không đánh giá Product Owner chỉ bằng số PBI nhập vào hệ thống.

### Tín hiệu cân bằng

| Mục tiêu | Dữ liệu/quan sát có thể dùng | Câu hỏi quyết định |
| --- | --- | --- |
| **Product Goal rõ và hữu ích** | Những quyết định ưu tiên có liên kết giá trị, phản hồi stakeholder/người dùng | Nhóm có giải thích vì sao làm việc này trước không? |
| **Product Backlog minh bạch** | PBI được hiểu đủ mức, quyết định sắp thứ tự có lý do, ít yêu cầu qua kênh ngầm | Người cần thông tin có biết trạng thái và hướng sản phẩm không? |
| **Developers tự quản** | Khả năng tự điều chỉnh Sprint Backlog, hỗ trợ review và gỡ phụ thuộc | Đội có phải chờ SM phân việc mới tiếp tục không? |
| **Hiệu quả Scrum** | Sprint Goal, Increment đạt DoD, vòng phản hồi và hành động Retrospective | Những sự kiện tạo quyết định và học hỏi thật không? |
| **Dòng công việc** | Work item age, cycle time, throughput, WIP, blocked time theo loại việc | Việc có được hoàn tất sớm và ổn định hơn không? |
| **Chất lượng** | Lỗi dữ liệu/quyền, rework, thất bại tích hợp, độ ổn định CI | Có giao nhanh bằng cách tạo lỗi muộn không? |
| **Kết quả người dùng** | Task success, nghiên cứu định tính, thời gian tìm bài, phản hồi học viên | Người học thật sự được giúp đỡ không? |
| **Bền vững** | Overtime, mức gián đoạn, tình trạng phụ thuộc cá nhân | Hiệu quả có duy trì mà không quá tải? |

### Ví dụ đo work item age đúng

Trong một snapshot, một số PBI đang mở:

| PBI | Tuổi công việc từ lúc start | Trạng thái | Trở ngại hiện biết |
| --- | ---: | --- | --- |
| A | 12 ngày | Chờ tích hợp | Contract API chưa thống nhất |
| B | 8 ngày | Review | Chờ người hiểu phân quyền |
| C | 3 ngày | Đang phát triển | Không có blocker ghi nhận |
| D | 1 ngày | Đang phát triển | Mới bắt đầu |

**Work item age** của item chưa Done vẫn tăng khi chờ; nó khác với **cycle time** chỉ biết đầy đủ sau khi item Done. Nếu item A có hai blocker chồng thời gian, không nên cộng trùng để tuyên bố blocked duration dài hơn thực tế.

Nhóm có thể quyết định **hỗ trợ hoàn tất A/B trước khi kéo thêm việc**, thay vì Scrum Master phân bốn task mới cho bốn người chỉ để mọi người “đều bận”.

### Dữ liệu không tự chứng minh nguyên nhân

Nếu cycle time giảm sau khi SM ngừng phân task, cùng kỳ đội cũng thêm reviewer và cải thiện CI, không được quy toàn bộ cải thiện cho một thay đổi. Nên ghi **giả thuyết, yếu tố cùng thay đổi, kỳ đo và chất lượng**.

### Những metric dễ bị lạm dụng

- Số PBI hoặc user story Product Owner viết mỗi tuần.
- Số task Scrum Master đã phân công.
- Số người phát biểu ở Daily Scrum.
- Story point hoàn thành của từng Developer.
- Số cuộc họp retrospective được tổ chức.
- Tỷ lệ ticket Done được ghi trước khi tích hợp.

Những con số này có thể phản ánh **hoạt động**, không nhất thiết phản ánh giá trị, chất lượng hoặc hiệu quả Scrum Team.

## 26. Một chương trình chuyển đổi hành vi trong bốn tuần

Mục tiêu không phải đổi tên chức danh hoặc thêm biểu mẫu, mà là **làm rõ accountability và xây khả năng tự quản có chất lượng**.

### Tuần 1 — Kiểm tra hiện trạng và quyền

- Quan sát một Sprint Planning và một Daily Scrum với mục đích học hỏi, không chấm điểm cá nhân.
- Xem ba đến năm PBI thật từ khi xuất hiện tới Done hoặc snapshot.
- Hỏi Product Owner có thể **sắp thứ tự Product Backlog và trao đổi với stakeholders** ở mức nào.
- Hỏi Developers có thể **tự chọn cách làm, hỗ trợ review và cập nhật Sprint Backlog** không.
- Hỏi Scrum Master đang dùng thời gian cho **tăng hiệu quả, gỡ trở ngại và huấn luyện** hay chủ yếu chia việc.
- Xác định Product Goal, Sprint Goal, DoD, ràng buộc và các hàng chờ có thật.

**Đầu ra:** Một bản đồ trách nhiệm, một vấn đề quan trọng và dữ liệu nền đủ dùng.

### Tuần 2 — Làm rõ mục tiêu và thay cách lập kế hoạch

- Product Owner trình bày **mục tiêu giá trị**, những giả thuyết và thứ tự backlog.
- Developers cùng PO làm rõ PBI, AC, rủi ro và chọn lát cắt có thể Done.
- Developers tự phát triển kế hoạch Sprint Backlog; SM không phân task.
- Scrum Master hỗ trợ mọi người hiểu trách nhiệm và giải quyết trở ngại quyền quyết định.
- Giữ các tiêu chuẩn chất lượng/DoD và chính sách tổ chức hiện hành.

**Đầu ra:** Một Sprint Goal có nghĩa, kế hoạch do Developers xây và cơ chế phản hồi rõ.

### Tuần 3 — Thực hành tự quản trong công việc hằng ngày

- Developers điều hành Daily Scrum theo tiến triển hướng Sprint Goal.
- Khi item già hoặc blocked, tự cùng quyết định giúp hoàn tất trước khi kéo thêm.
- PO làm rõ trade-off về giá trị và phản hồi kịp thời với stakeholder khi có thay đổi.
- SM quan sát hệ thống, huấn luyện phối hợp và hỗ trợ những trở ngại đội khó tự giải quyết.
- Tăng tích hợp thường xuyên, test và minh bạch trạng thái Done.

**Đầu ra:** Những quyết định thực do đúng người có accountability đưa ra, kèm bằng chứng về dòng công việc.

### Tuần 4 — Kiểm tra, điều chỉnh và lan tỏa

- Trong Sprint Review, xem **Increment đạt DoD**, phản hồi sản phẩm và thay đổi hướng backlog.
- Trong Retrospective, xem chất lượng tự quản, điểm nghẽn, thử nghiệm và tác dụng phụ.
- Đối chiếu flow, quality, outcome, overtime và phụ thuộc vào Scrum Master.
- Ghi những ranh giới vẫn thiếu quyền ở cấp tổ chức để người có thẩm quyền tiếp tục giải quyết.
- Quyết định giữ, sửa, bỏ hoặc thử nhỏ hơn; không tổng kết chỉ bằng số cuộc họp.

**Đầu ra:** Kết luận có giới hạn, một hoặc hai cải tiến tiếp và trách nhiệm rõ ràng.

### Ví dụ giả thuyết có thể kiểm chứng

~~~text
VẤN ĐỀ:
  Developers chờ Scrum Master phân task và chờ reviewer;
  các PBI bị mở lâu, cuối Sprint ít Increment đạt DoD.

GIẢ THUYẾT:
  Nếu PO đưa mục tiêu/ưu tiên minh bạch hơn, Developers tự lập
  Sprint Backlog và chủ động hỗ trợ review, đội có thể giảm thời
  gian chờ và giao Increment ổn định hơn.

THỬ NGHIỆM:
  Một Sprint Goal nhỏ, rõ hành vi.
  Developers tự tổ chức Daily Scrum và quyết định điều phối.
  SM hỗ trợ coaching/gỡ trở ngại chứ không gán task.
  PO phản hồi kịp thời về giá trị và thứ tự backlog.

ĐO:
  Số PBI đạt DoD; age, cycle time, blocked duration;
  lỗi tích hợp, rework, phản hồi người dùng và overtime.

GUARDRAIL:
  Không giảm DoD; không bỏ kiểm tra quyền và dữ liệu;
  không dùng velocity cá nhân để đánh giá.

XEM LẠI:
  Kết quả thật, tác dụng phụ, yếu tố cùng thay đổi,
  quyết định giữ/sửa/bỏ và chủ sở hữu bước tiếp theo.
~~~

## 27. Mẫu hội thoại để thay thói quen giao việc

Các câu nói ngắn thường có tác dụng hơn một biểu đồ cơ cấu tổ chức nếu được dùng đúng lúc.

### Khi PO nhận danh sách yêu cầu từ lãnh đạo

**Thay vì:** “Tôi sẽ nhập nguyên danh sách rồi yêu cầu SM chia cho nhóm.”

**Có thể nói:**

> “Tôi sẽ làm rõ mục tiêu, giá trị và thời điểm cần kết quả của các yêu cầu, cùng ảnh hưởng tới Product Goal. Tôi sẽ cập nhật thứ tự Product Backlog và trao đổi lựa chọn với Developers, minh bạch những đánh đổi và ràng buộc.”

### Khi SM được yêu cầu giao việc trong Sprint Planning

**Thay vì:** “A làm UI, B làm API, C làm test; ai không xong phải báo tôi.”

**Có thể nói:**

> “Developers sẽ cùng xây kế hoạch để đạt Sprint Goal và Definition of Done. Tôi sẽ hỗ trợ khi có trở ngại về phối hợp, quyền hoặc hiểu cách vận hành Scrum. Chúng ta cần làm rõ quyết định nào còn thiếu để đội tự tổ chức công việc.”

### Khi một developer hỏi SM nên làm ticket nào

**Thay vì:** “Làm ticket số 126, tôi vừa gắn tên bạn.”

**Có thể hỏi:**

> “Sprint Goal và những PBI đang làm cần hỗ trợ ở đâu? Đội đã xem item nào sắp Done nhưng còn chờ review hoặc test chưa? Mọi người có thể cùng chọn bước tiếp theo để tối đa hóa khả năng hoàn tất không?”

### Khi stakeholder muốn chen một yêu cầu mới

**Thay vì:** “Nhắn thẳng cho Developer nhanh hơn, đừng qua PO.”

**Có thể nói:**

> “Chúng ta hãy mô tả mức khẩn, giá trị và ràng buộc, trao đổi với Product Owner để đánh giá thứ tự Product Backlog. Developers sẽ cùng xem tác động tới Sprint Goal và kế hoạch hiện tại. Nếu là sự cố khẩn, chúng ta dùng đường ứng phó có thẩm quyền.”

### Khi PO muốn bỏ test để kịp demo

**Có thể nói:**

> “Mục tiêu giá trị cần được giữ, nhưng Increment chưa đạt DoD nếu test bắt buộc thất bại. Chúng ta hãy chọn lát cắt nhỏ hơn hoặc sửa lỗi, đồng thời minh bạch điều chưa hoàn thành. Scrum Master hỗ trợ giải quyết trở ngại, không phê duyệt miễn kiểm tra.”

### Khi SM thấy retrospective chỉ lặp phàn nàn

**Có thể hỏi:**

> “Trong những dữ liệu và ví dụ vừa xem, vấn đề nào gây cản trở lớn nhất tới Increment? Chúng ta thử một thay đổi nhỏ nào, ai phối hợp thực hiện, khi nào kiểm tra lại và bằng chứng thành công là gì?”

## 28. Những ngộ nhận phổ biến và cách điều chỉnh

| Ngộ nhận | Vì sao nguy hiểm hoặc chưa đúng? | Cách hiểu và hành động phù hợp |
| --- | --- | --- |
| **“Product Owner là người ghi yêu cầu.”** | Tách accountability về giá trị khỏi quyền sắp Product Backlog | PO phát triển Product Goal, làm rõ, sắp thứ tự và minh bạch Product Backlog; có thể ủy quyền việc viết |
| **“PO phải tự viết mọi user story.”** | Tạo bottleneck, hạn chế đóng góp của Developers và chuyên môn nghiệp vụ | Cùng refinement và dùng ví dụ; PO vẫn chịu trách nhiệm Product Backlog |
| **“Stakeholder nào cấp cao nhất thì quyết thứ tự.”** | Ưu tiên xung đột, backlog ngầm, không có đánh đổi minh bạch | Stakeholders trao đổi với PO; quyền tổ chức được làm rõ và tôn trọng |
| **“Có nhiều PO ngang quyền cho cùng một Product Backlog.”** | Mâu thuẫn accountability, Developers nhận lệnh từ nhiều nguồn | Trong Scrum, một PO chịu accountability; nhiều người có thể hỗ trợ |
| **“PO là người kiểm duyệt cách code.”** | Trộn giá trị với kỹ thuật, tăng hàng chờ | PO trao đổi outcome, trade-off; Developers sở hữu kế hoạch triển khai |
| **“PO ký là tự động Done.”** | Bỏ qua DoD và chất lượng tích hợp | Increment chỉ Done khi đáp ứng DoD |
| **“Scrum Master là trưởng nhóm giao việc.”** | Tước khả năng Developers tự quản và thích nghi | SM giúp thiết lập Scrum và nâng hiệu quả, không phân task theo Scrum |
| **“SM phải chủ trì Daily Scrum và đọc ticket.”** | Biến sự kiện thành báo cáo thay vì kiểm tra Sprint Goal | Daily Scrum thuộc Developers; SM hỗ trợ mục đích sự kiện khi cần |
| **“SM phải giải quyết mọi blocker một mình.”** | Tạo điểm nghẽn cá nhân; nhóm không phát triển năng lực | Developers chủ động giải quyết trong quyền mình, SM hỗ trợ gỡ trở ngại hệ thống |
| **“SM sở hữu Sprint Backlog.”** | Người lập kế hoạch không phải người thực hiện | Developers tạo và thích nghi Sprint Backlog |
| **“SM chấm điểm năng suất từng Developer.”** | Tạo động cơ giấu việc khó và lỗi; gây mất tin cậy | Dùng dữ liệu giúp cải tiến hệ thống, không xếp hạng cá nhân theo point |
| **“SM chỉ cần nhắc mọi người làm đúng nghi thức.”** | Hình thức có đủ nhưng không có Increment hoặc cải tiến | SM hỗ trợ hiểu Scrum, hiệu quả, tự quản và trở ngại |
| **“Developers phải nhận task cố định từ quản lý.”** | Không thể điều chỉnh theo năng lực, phụ thuộc và phản hồi mới | Developers tự quyết ai làm gì, khi nào, thế nào trong phạm vi Scrum |
| **“Tự quản nghĩa là không cần phối hợp.”** | Mỗi người chọn việc riêng, WIP tăng, không ai giữ DoD chung | Tự quản trong trách nhiệm chung đối với Sprint Goal và Increment |
| **“Sprint Planning là buổi PO/SM giao ticket.”** | Developers không sở hữu dự báo và kế hoạch | Cả Scrum Team hợp tác theo Why–What–How; Developers chọn PBI và lập kế hoạch |
| **“Daily Scrum là cuộc họp báo cáo quản lý.”** | Không phát hiện và gỡ rủi ro hướng Sprint Goal | Developers kiểm tra tiến triển và thích nghi kế hoạch trong 15 phút |
| **“Sprint Review chỉ để PO nghiệm thu.”** | Không có feedback sản phẩm và stakeholders thực | Kiểm tra Increment và tiến triển Product Goal, thích nghi Product Backlog |
| **“Retrospective để SM xử lý người yếu.”** | Lỗi hệ thống bị cá nhân hóa; giảm an toàn trao đổi | Scrum Team điều tra cơ chế, thử cải tiến chất lượng/hiệu quả |
| **“Sprint Backlog phải giữ nguyên bất kể điều mới.”** | Điều chỉnh bị chặn, kế hoạch mất liên hệ thực tế | Developers thích nghi kế hoạch, trao đổi phạm vi với PO, giữ Sprint Goal/DoD |
| **“Velocity cao là SM phân việc tốt.”** | Point không đo giá trị hoặc hiệu quả Scrum Team | Xem flow, DoD, chất lượng, outcome và năng lực phối hợp |
| **“Có Jira và đủ vai trò là đã Scrum.”** | Công cụ/chức danh không tạo accountability | Kiểm tra quyền ra quyết định và hành vi thực |
| **“Không cần TDD/CI vì đã có SM.”** | Framework không tự tạo phản hồi kỹ thuật | Developers chọn thực hành kỹ thuật phù hợp rủi ro |
| **“Có thể bỏ phân quyền cho demo nhỏ.”** | Vi phạm chất lượng và có thể gây hại dữ liệu | Giữ DoD/guardrail, thu hẹp lát cắt an toàn |
| **“Scrum Master phải phê duyệt mọi thay đổi.”** | Tạo lớp kiểm soát không được Scrum định nghĩa | Kiểm tra đúng quyền theo sản phẩm, kỹ thuật và chính sách |
| **“Mỗi nhóm chuyên môn có PO riêng dù cùng một sản phẩm.”** | Đứt Product Goal và Product Backlog chung | Xác định ranh giới Product, áp dụng accountabilities Scrum đúng |
| **“Khi SM nghỉ, Sprint phải ngừng.”** | Tự quản chỉ tồn tại trên giấy | Developers chủ động vận hành công việc, SM giúp tăng năng lực bền vững |

### Ba phép thử cho một thay đổi trách nhiệm

1. **Giá trị:** Quyết định mới có giúp người có accountability đúng kết nối công việc với Product Goal không?
2. **Tự quản:** Developers có thể phối hợp và thích nghi tốt hơn mà không cần thêm tầng giao việc không?
3. **Chất lượng:** Increment có đạt DoD và phản hồi người dùng đến sớm hơn, không đánh đổi dữ liệu hay nhịp làm việc bền vững?

Nếu chỉ đổi tên “Project Manager” thành “Scrum Master” và “Business Analyst” thành “Product Owner” trong sơ đồ tổ chức, ba câu hỏi này có thể vẫn không có đáp án tốt hơn.

## 29. Bài tập thực hành

### Bài tập 1 — Phân loại accountability

Các công việc được nêu:

1. Truyền đạt Product Goal.
2. Quyết định thứ tự Product Backlog.
3. Chọn PBI có thể hoàn tất trong Sprint qua trao đổi với PO.
4. Tạo và thích nghi Sprint Backlog.
5. Huấn luyện tự quản và giúp loại bỏ trở ngại.
6. Bảo đảm Scrum được hiểu và thực hành đúng.
7. Tuân thủ DoD khi tạo Increment.
8. Hỗ trợ stakeholder hợp tác với Scrum Team.

**Yêu cầu:** Phân loại accountability trọng tâm PO/SM/Developers cho từng việc; chỉ ra việc nào cần cộng tác nhưng có một accountability rõ.

### Bài tập 2 — Product Owner có phải chỉ viết ticket?

Một PO được yêu cầu mỗi tuần tạo 40 user story từ email của ba trưởng bộ phận. Họ không được gặp người dùng hoặc đổi thứ tự backlog.

**Yêu cầu:** Xác định ít nhất bốn nguy cơ với giá trị sản phẩm. Đề xuất cách tổ chức trao đổi với stakeholders và làm rõ quyền PO. Không giả định PO có quyền bỏ nghĩa vụ ngân sách/pháp lý.

### Bài tập 3 — Viết Product Goal có giá trị

Một nhóm nhận yêu cầu “Làm nút Tiếp tục học, API mới, đồng bộ video và trang thống kê”.

**Yêu cầu:** Viết Product Goal hướng tới kết quả người học. Nêu ba câu hỏi chưa biết và ít nhất ba PBI có thứ tự dự kiến theo giá trị/rủi ro.

### Bài tập 4 — Từ user story đến ví dụ chấp nhận

User story: “Là học viên, tôi muốn mở lại bài gần nhất để không tìm lại thủ công”.

**Yêu cầu:** Viết acceptance criteria cho bài còn quyền, không có bài, hết quyền và API lỗi. Đánh dấu những điểm chưa biết cần PO hoặc người có quyền nghiệp vụ xác nhận. Nêu hai test kỹ thuật Developers có thể đề xuất.

### Bài tập 5 — Thiết kế Sprint Planning đúng trách nhiệm

Một buổi Planning hiện tại: PO đưa danh sách 50 ticket; SM gắn tên người và hạn từng task; Developers im lặng.

**Yêu cầu:** Thiết kế lại phần Why–What–How. Viết mẫu hội thoại cho PO, Developers và SM; giải thích ai chọn PBI, ai lập kế hoạch và Sprint Goal được hình thành thế nào.

### Bài tập 6 — Daily Scrum không phải cuộc họp status

SM gọi lần lượt từng người, hỏi ba câu báo cáo và giao thêm việc. Một item chờ review sáu ngày nhưng không ai hành động.

**Yêu cầu:** Viết agenda 15 phút dành cho Developers tập trung Sprint Goal và kế hoạch; nêu một cách xử lý item review mà không cần SM ra lệnh.

### Bài tập 7 — Scrum Master giúp gỡ trở ngại

Pipeline integration thường lỗi do dữ liệu test bị các nhóm dùng chung ghi đè. Developers đề nghị SM “hãy tự sửa môi trường vì đó là blocker”.

**Yêu cầu:** Phân biệt phần đội tự giải quyết với trở ngại hệ thống cần SM hỗ trợ. Đề xuất phương án cải thiện môi trường và dấu hiệu đội tự chủ hơn.

### Bài tập 8 — Stakeholder yêu cầu chen việc

Giữa Sprint, một trưởng bộ phận giao trực tiếp cho developer một biểu đồ mới. Sprint Goal hiện tại liên quan phân quyền tiến độ.

**Yêu cầu:** Viết cách Developers phản hồi, Product Owner đánh giá giá trị và Scrum Master hỗ trợ phối hợp. Phân biệt yêu cầu thông thường với sự cố an toàn thật sự khẩn.

### Bài tập 9 — Product Owner không có quyền

Một hội đồng gồm năm người quyết thứ tự backlog, PO chỉ nhập liệu và trả lời những câu hỏi kỹ thuật thay Developers.

**Yêu cầu:** Đề xuất một cấu trúc trao đổi stakeholder minh bạch, một cách phục hồi accountability của PO và hai ràng buộc tổ chức cần xác minh trước.

### Bài tập 10 — Bất đồng về DoD

PO muốn demo “Tiếp tục học” và gọi Done. Test cho phép B thấy dữ liệu của A đang thất bại. SM được yêu cầu “hãy quyết định nhóm có thể bỏ test không”.

**Yêu cầu:** Nêu trách nhiệm của PO, SM, Developers và vai trò bảo mật có thẩm quyền. Đề xuất hai phương án an toàn để tiếp tục nhận phản hồi mà không giả Increment đã Done.

### Bài tập 11 — Tự quản nhưng không phối hợp

Developers nói “ai thích ticket nào cứ tự lấy”. Tất cả chọn task giao diện; code review, API và test bị bỏ lại.

**Yêu cầu:** Đề xuất chính sách phối hợp theo Sprint Goal, hai hành vi hỗ trợ hoàn tất trước khi bắt đầu thêm và một guardrail chất lượng.

### Bài tập 12 — Nhiều Scrum Team cùng sản phẩm

Ba Scrum Team cùng làm chức năng học tập. Mỗi nhóm có một backlog riêng, một PO riêng và một DoD khác nhau, nhưng tất cả được giới thiệu là “cùng phát triển một sản phẩm”.

**Yêu cầu:** Giải thích những điểm cần xem lại theo Scrum về Product Goal, Product Backlog, Product Owner và DoD. Nêu điều kiện cần xác minh trước khi kết luận các nhóm thật sự cùng một Product.

### Bài tập 13 — Sprint Goal lỗi thời

Đội đang làm cải tiến UI thì xuất hiện thông tin khiến hướng sản phẩm không còn giá trị. Một thành viên nói “SM hủy Sprint rồi phân task mới”.

**Yêu cầu:** Nêu đúng thẩm quyền hủy Sprint theo Scrum, điều kiện Sprint Goal lỗi thời và cách Scrum Team minh bạch ảnh hưởng; phân biệt với trường hợp chỉ cần thương lượng phạm vi.

### Bài tập 14 — Story point không đo quyền tự quản

Trước cải tiến, một nhóm hoàn thành 30 point; sau cải tiến họ hoàn thành 24 point nhưng có một Increment đạt DoD, lỗi tích hợp giảm và người dùng thử được.

**Yêu cầu:** Viết nhận định có giới hạn về kết quả. Giải thích vì sao không thể kết luận hiệu suất giảm chỉ từ point; đề xuất dữ liệu flow, chất lượng và outcome nên xem.

### Bài tập 15 — Work item age và blocker

Bốn PBI đang mở có age **12, 8, 3, 1 ngày**. Item A đang chờ contract, B chờ review, C/D đang phát triển. SM muốn giao bốn task mới để “không ai rảnh”.

**Yêu cầu:** Đề xuất hai quyết định Developers có thể tự đưa ra trước khi bắt đầu thêm; giải thích age khác cycle time và dữ liệu blocked cần ghi thế nào.

### Bài tập 16 — Đánh giá một Scrum Master giúp quá nhiều

SM được khen vì mỗi ngày tự cập nhật Sprint Backlog, gửi từng task cho từng developer và tổ chức mọi cuộc họp. Khi SM nghỉ một tuần, nhóm không biết phải làm gì.

**Yêu cầu:** Phân tích đâu là hỗ trợ thực, đâu là tạo phụ thuộc; viết kế hoạch ba bước chuyển giao năng lực cho Developers và cơ chế xem lại tại Retrospective.

### Bài tập 17 — Phản hồi đúng vai trò

Viết lại ba câu:

- “PO, bạn ghi hết yêu cầu của sếp vào tool và đừng tự ý thay đổi.”
- “SM, chia task cho từng bạn để Sprint không bị trễ.”
- “Developer, bạn cứ code xong phần mình, tester và PO sẽ lo chất lượng.”

**Yêu cầu:** Viết thành lời đề nghị tôn trọng accountability, có mục tiêu giá trị/chất lượng và cho phép các bên cộng tác.

### Bài tập 18 — Thiết kế Retrospective về quyền quyết định

Một Scrum Team không dám thông báo blocker vì mọi lỗi đều bị truy trách nhiệm cá nhân. Team có nhiều ticket Done nhưng không tích hợp được.

**Yêu cầu:** Lập agenda 45 phút với timeline từ một item thật, câu hỏi không quy lỗi, giả thuyết cải tiến, một hành động nhỏ, guardrail và cách theo dõi kết quả.

### Bài tập 19 — Thực nghiệm bốn tuần

Một tổ chức muốn giảm tình trạng Scrum Master phân task và Product Owner chỉ nhập ticket.

**Yêu cầu:** Xây một thử nghiệm bốn tuần có baseline, Product Goal, thay đổi accountability, hoạt động Sprint Planning/Daily/Review/Retro, chỉ số flow/quality/outcome, người có quyền giải quyết trở ngại tổ chức và điều kiện dừng.

### Bài tập 20 — Chọn Scrum, Kanban hay thực hành bổ trợ?

Ba đội:

- A xây sản phẩm có mục tiêu và nhu cầu kiểm chứng giá trị theo nhịp.
- B xử lý sự cố production đến liên tục, có ưu tiên khẩn.
- C phát triển API tích hợp nhiều đối tác với rủi ro hợp đồng và dữ liệu.

**Yêu cầu:** Đề xuất cách phối hợp cho từng đội dựa trên bối cảnh, nêu các thực hành Kanban/XP có ích. Giải thích vì sao không cần ép mọi đội gọi người ghi ticket là PO và người phân việc là SM.

## 30. Checklist tránh biến PO thành thư ký và SM thành người giao việc

Khi rà soát một Scrum Team, hãy dùng checklist để **mở đối thoại dựa trên bằng chứng**, không phải xếp hạng cá nhân hay chấm phần trăm “Scrum trưởng thành”.

### Product Goal và Product Owner

- [ ] Product Goal có mô tả trạng thái sản phẩm mong muốn, không chỉ danh sách tính năng?
- [ ] Product Owner có thể giải thích **vì sao** PBI này được ưu tiên hơn PBI khác?
- [ ] Product Backlog minh bạch, thấy được và được hiểu bởi người cần dùng?
- [ ] PO có thể trao đổi với stakeholders/người dùng theo nhu cầu sản phẩm?
- [ ] Những yêu cầu từ lãnh đạo có được đánh giá về giá trị, rủi ro và đánh đổi?
- [ ] Có một PO chịu accountability về Product Backlog, thay vì nhiều nguồn ra lệnh mâu thuẫn?
- [ ] Việc viết user story/AC được cộng tác và có thể ủy quyền, không dồn mọi thao tác cho PO?
- [ ] PO vẫn chịu trách nhiệm giải trình sau khi ủy quyền tạo hoặc làm rõ PBI?
- [ ] Quyền PO và những giới hạn hợp đồng, pháp lý, ngân sách được làm rõ?
- [ ] Phản hồi từ Sprint Review hoặc người dùng thực có thể thay đổi Product Backlog?

### Scrum Master và hiệu quả Scrum

- [ ] Scrum Master hiểu accountability thiết lập Scrum và nâng hiệu quả Scrum Team?
- [ ] SM giúp đội học cách tự quản, thay vì cần SM phân việc từng ngày?
- [ ] Scrum Team có thể vận hành Daily Scrum hữu ích khi SM vắng?
- [ ] Những sự kiện Scrum có mục tiêu rõ và tạo quyết định, không chỉ báo cáo trạng thái?
- [ ] SM hỗ trợ PO quản lý Product Backlog, Product Goal và trao đổi stakeholders khi cần?
- [ ] SM hỗ trợ xử lý rào cản hệ thống, không ôm mọi blocker vào mình?
- [ ] SM giúp tổ chức hiểu Scrum, hạn chế các luồng giao việc trực tiếp trái trách nhiệm?
- [ ] Không dùng SM làm người chấm năng suất cá nhân bằng velocity/story point?
- [ ] Khi SM giúp làm việc hành chính, có lý do và cơ chế không tạo phụ thuộc kéo dài?
- [ ] Những xung đột giữa chức danh quản lý khác với accountability Scrum được minh bạch?

### Developers, Sprint Goal và chất lượng

- [ ] Developers cùng PO chọn những PBI có thể Done trong Sprint?
- [ ] Developers tạo và cập nhật Sprint Backlog, thay vì chỉ nhận task đã được cấp?
- [ ] Sprint Goal là mục tiêu chung có giá trị, không phải tổng danh sách task?
- [ ] Developers tự phối hợp ai làm gì, khi nào và làm thế nào trong ranh giới trách nhiệm?
- [ ] Daily Scrum hướng vào tiến triển tới Sprint Goal và điều chỉnh kế hoạch?
- [ ] Item già hoặc bị blocked được chủ động xử lý, không mở thêm việc chỉ để mọi người bận?
- [ ] Các thành viên có thể hỗ trợ review, test và tích hợp thay vì giữ việc theo silo?
- [ ] Developers chia sẻ trách nhiệm với nhau về **Increment đạt DoD**?
- [ ] Kiểm thử quyền, dữ liệu và bảo mật bắt buộc không bị bỏ để tăng tỷ lệ Done?
- [ ] Sprint Backlog có thể thích nghi khi có thông tin mới, giữ Sprint Goal và DoD?

### Hợp tác, chất lượng và phản hồi

- [ ] Product Owner, Scrum Master và Developers có phân biệt rõ **giá trị, hiệu quả và kế hoạch/chất lượng**?
- [ ] Sprint Review giúp kiểm tra Increment và tiến triển Product Goal với stakeholders?
- [ ] Sprint Retrospective có hành động cải tiến nhỏ và xem lại tác động?
- [ ] Khi sự cố khẩn xảy ra, đội có đường ứng phó đúng quyền thay vì chờ phân task?
- [ ] Nếu nhiều Scrum Team cùng một sản phẩm, họ chia sẻ Product Goal, Product Backlog, PO và DoD chung?
- [ ] Các phụ thuộc liên nhóm về API, dữ liệu và môi trường có người phối hợp/quyền quyết định rõ?
- [ ] Không nhầm merge code, Done, deployment, release và outcome?
- [ ] Có nguồn phản hồi thực từ người nhận giá trị, không chỉ dashboard?
- [ ] Chỉ số flow, chất lượng và outcome được xem cùng nhau với mẫu/kỳ đo rõ?
- [ ] Không xếp hạng người bằng story point, số ticket hoặc thời gian phát biểu ở Daily?
- [ ] Thử nghiệm cải tiến có giả thuyết, guardrail, người phối hợp và mốc xem lại?
- [ ] Các quyết định về cách làm dựa trên **loại công việc và bối cảnh**, không chỉ một template?
- [ ] Tổ chức bảo vệ nhịp làm việc bền vững và điều kiện nêu vấn đề không sợ bị phạt?

Nếu một số câu trả lời là “chưa”, không nhất thiết cần **thêm công cụ hoặc thêm vai trò**. Có thể bắt đầu bằng một cuộc trao đổi để làm rõ ai có accountability, quyền nào còn thiếu và **một quyết định cụ thể** cần cải thiện.

## 31. Tổng kết

- **Product Owner không phải người ghi yêu cầu.** PO chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả: Product Goal, PBI rõ ràng, thứ tự và tính minh bạch. PO có thể ủy quyền thực hiện, nhưng không chuyển trách nhiệm giải trình.
- **Scrum Master không phải người giao việc.** SM giúp thiết lập Scrum và nâng hiệu quả Scrum Team bằng huấn luyện, hỗ trợ tự quản, xử lý trở ngại và giúp tổ chức hiểu Scrum. SM không được Scrum định nghĩa là cấp trên phân task của Developers.
- **Developers không phải nhóm chỉ nhận lệnh.** Họ tạo và thích nghi Sprint Backlog, đưa chất lượng vào bằng Definition of Done, tự phối hợp để hướng tới Sprint Goal và giữ trách nhiệm chuyên nghiệp với nhau.
- **Sprint Planning không phải buổi chia task của PO/SM.** Cả Scrum Team làm rõ Why–What–How; Developers chọn PBI qua thảo luận với PO và lập kế hoạch triển khai.
- **Daily Scrum không phải cuộc họp status cho quản lý.** Nó giúp Developers kiểm tra tiến triển và thích nghi kế hoạch hướng Sprint Goal trong 15 phút.
- **Sprint Review và Retrospective không phải nghi thức hình thức.** Một vòng kiểm tra kết quả sản phẩm và thích nghi Product Backlog; vòng còn lại cải tiến cách làm, chất lượng và hiệu quả.
- **Chất lượng không thể được “ký thay”.** Increment chỉ Done khi đạt Definition of Done; PO, SM hoặc feature flag không cho phép bỏ ràng buộc dữ liệu và bảo mật.
- **Quyền tự quản không đồng nghĩa tùy tiện.** Nó cần mục tiêu, bằng chứng, phối hợp, trách nhiệm và guardrail rõ; Kanban/XP có thể bổ sung để quản lý flow và phản hồi kỹ thuật.
- **Sửa sai bắt đầu từ hành vi và quyền quyết định, không chỉ tên chức danh.** Hãy nhìn cách Product Backlog được sắp thứ tự, cách Developers điều phối, cách SM giảm trở ngại và cách người dùng nhận giá trị.

Khi nghe câu **“Product Owner cứ ghi yêu cầu, Scrum Master sẽ phân việc cho Developers”**, hãy hỏi:

> **“Ai đang chịu trách nhiệm về giá trị và thứ tự sản phẩm? Ai có quyền xây và thích nghi kế hoạch tạo Increment? Và Scrum Master đang làm gì để cả đội tự quản, phản hồi sớm và giao chất lượng tốt hơn?”**
