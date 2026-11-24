# Phát triển kỹ năng cộng tác, sản phẩm và kỹ thuật song song

Một công ty xây dựng nền tảng học trực tuyến quyết định chuyển đổi Agile. Ban đầu, công ty cử mọi người học khóa Scrum hai ngày, bổ nhiệm Product Owner và Scrum Master, chia công việc thành Sprint hai tuần và tổ chức Daily Scrum. Sau ba tháng, các cuộc họp diễn ra đều đặn nhưng nhiều hạng mục vẫn trễ; yêu cầu thay đổi vào cuối Sprint gây tranh cãi; một luồng đăng ký khóa học cần bốn nhóm phối hợp và đến tuần cuối mới phát hiện lỗi tích hợp.

Đội phát triển cho rằng Product Owner thường đưa yêu cầu chưa rõ. Product Owner cho rằng Developers không hiểu giá trị người dùng. Người phụ trách kiểm thử nhận các hạng mục quá muộn, trong khi lãnh đạo nhìn biểu đồ velocity mà không hiểu vì sao học viên vẫn không vào được bài đầu sau thanh toán.

Vấn đề không nhất thiết là mọi người thiếu thiện chí hoặc không hiểu một Scrum event. **Năng lực cần thiết để làm việc thích ứng chưa được phát triển đồng bộ**:

- **Cộng tác:** biết làm rõ bất đồng, đưa ra quyết định, phối hợp giữa chuyên môn, phản hồi và giải quyết trở ngại.
- **Sản phẩm:** hiểu người dùng, phân biệt output với outcome, xác định mục tiêu, kiểm chứng giả thuyết và ưu tiên đúng giá trị.
- **Kỹ thuật:** thiết kế phần mềm thay đổi được, kiểm thử, tích hợp liên tục, bảo vệ chất lượng và triển khai một Increment có thể sử dụng.

Nếu chỉ tăng năng lực lập kế hoạch nhưng không có kiểm thử tin cậy, đội khó giao phần mềm nhỏ và thường xuyên. Nếu CI rất nhanh nhưng không hiểu người học cần gì, đội có thể giao nhanh nhiều tính năng không hữu ích. Nếu khám phá sản phẩm tốt nhưng mỗi thay đổi phải chờ nhiều nhóm, phản hồi sẽ đến quá chậm. Chuyển đổi Agile hiệu quả đòi hỏi **phát triển ba năng lực này song song và kết nối chúng vào công việc thật**.

Bài thuộc chương **Chuyển đổi Agile** của module **AGILE_DEVELOPMENT**: hiểu giá trị và nguyên tắc Agile, giao phần mềm tăng dần, nhận phản hồi sớm, cải tiến liên tục, thực hành user story, Product Backlog, Scrum, Kanban, XP và đo dòng công việc để chọn cách phối hợp phù hợp. Chủ đề ở đây không phải biến mọi người thành chuyên gia của cả ba lĩnh vực; đó là **xây năng lực tập thể đủ để nhận biết nhu cầu, ra quyết định và tạo kết quả có chất lượng một cách bền vững**.

> **Thông điệp cốt lõi:** Đừng chuyển đổi theo chuỗi “đào tạo Scrum trước, học sản phẩm sau, còn chất lượng kỹ thuật để cuối”. Hãy chọn **một vấn đề sản phẩm thực**, đồng thời luyện cách cộng tác, cách quyết định giá trị và cách tạo Increment đáng tin ngay trên vấn đề đó; quan sát bằng chứng rồi điều chỉnh.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **năng lực cộng tác, sản phẩm và kỹ thuật** phụ thuộc lẫn nhau trong chuyển đổi Agile và vì sao tối ưu một chiều có thể không cải thiện kết quả.
2. Phân biệt **đã tham gia đào tạo**, **biết khái niệm**, **thực hiện được trong công việc** và **tạo được kết quả bền vững**.
3. Nhận diện kỹ năng cốt lõi ở ba trụ cột, bao gồm **phản hồi, xử lý xung đột, discovery, user story/acceptance criteria, ưu tiên, TDD, CI, refactoring và quan sát vận hành**.
4. Xây **bản đồ năng lực ở cấp đội**, thấy các phụ thuộc chuyên môn mà không dùng bảng điểm để gắn nhãn hoặc xếp hạng cá nhân.
5. Thiết kế **hoạt động học trong luồng giao sản phẩm**: làm việc cặp, refinement theo ví dụ, khám phá cùng người dùng, luyện kiểm thử trên lát cắt nhỏ và retrospective có thử nghiệm.
6. Xác định vai trò hỗ trợ của lãnh đạo, Product Owner, Scrum Master, Developers, tester, UX, vận hành và chuyên gia khác mà không làm sai accountabilities của Scrum.
7. Lựa chọn các tín hiệu **outcome, chất lượng, flow và năng lực học** thay vì chỉ đếm giờ học, chứng chỉ, story points hay số test.
8. Xây lộ trình cải tiến nhiều tuần, nhận diện rủi ro năng lực và áp dụng vào tình huống một nền tảng học trực tuyến gặp lỗi ghi danh.

## 1. Chuyển đổi Agile là thay đổi năng lực tổ chức, không chỉ thay tên vai trò

Một tổ chức có thể đổi tên phòng “Project Management” thành “Agile Delivery”, thay báo cáo Gantt bằng bảng Sprint và bổ sung Daily Scrum mà vẫn giữ cách làm cũ: yêu cầu được chuyển qua nhiều tầng phê duyệt, phần mềm tích hợp cuối dự án, người dùng chỉ thấy kết quả khi đã quá muộn.

Các thay đổi đó có thể giúp minh bạch một phần, nhưng **không tự tạo khả năng thích ứng**.

### 1.1. Bốn mức thay đổi cần phân biệt

| Mức | Dấu hiệu | Ví dụ | Chưa đủ để kết luận |
|---|---|---|---|
| **Học khái niệm** | Có thể giải thích thuật ngữ | Biết Sprint Goal, Definition of Done, WIP | Đội áp dụng được dưới áp lực chưa? |
| **Thực hiện thực hành** | Thử được hành vi mới trong công việc | Refinement bằng ví dụ, chạy CI mỗi thay đổi | Thực hành có tạo tác dụng không? |
| **Năng lực bền vững** | Thực hiện lặp lại, phản hồi sớm, ít phụ thuộc cá nhân | Đội giao lát cắt nhỏ đạt DoD trong nhiều Sprint | Đội có giao đúng giá trị người dùng không? |
| **Kết quả sản phẩm/tổ chức** | Người dùng, chất lượng và khả năng thích ứng cải thiện | Học viên tự ghi danh và vào bài đầu với ít lỗi hơn | Mức thay đổi do yếu tố nào và bền vững tới đâu? |

**Hoàn thành một khóa học không đồng nghĩa có năng lực.** Nhưng đào tạo cũng không vô ích: nó giúp xây ngôn ngữ chung, nhận biết rủi ro và chuẩn bị thực hành. Giá trị được kiểm chứng khi người học **áp dụng và thích ứng trong hoàn cảnh thật**.

### 1.2. Mục tiêu Agile không phải tốc độ code tối đa

Bốn giá trị của Agile Manifesto nhấn mạnh con người và tương tác, phần mềm hoạt động, hợp tác với khách hàng và đáp ứng thay đổi. Các nguyên tắc chú trọng giao phần mềm thường xuyên, cộng tác kinh doanh–kỹ thuật, chất lượng kỹ thuật, nhịp làm việc bền vững và cải tiến liên tục.

**Không nên suy diễn** rằng Agile yêu cầu:

- Mỗi nhóm phải tăng velocity qua mọi Sprint.
- Mọi người phải có chức danh “Agile” mới làm việc tốt.
- Luôn thay đổi kế hoạch dù chưa có bằng chứng mới.
- Rút ngắn thời gian giao bằng cách bỏ kiểm thử hoặc kiểm soát cần thiết.
- Mọi công ty phải dùng Scrum, Kanban và XP cùng một cách.

Một đội có thể chủ động dành năng lực để củng cố CI hoặc làm rõ vấn đề người dùng, khiến throughput gần hạn giảm nhưng giảm rủi ro và thời gian làm lại về sau. Điều cần kiểm tra là **giá trị và tính bền vững của hệ thống**, không chỉ output tức thời.

### 1.3. Chuyển đổi là một hệ thống các vòng phản hồi

~~~mermaid
flowchart LR
    U["Nhu cầu và kết quả người dùng"] --> P["Năng lực sản phẩm:<br/>Hiểu vấn đề, ưu tiên và giả thuyết"]
    P --> C["Năng lực cộng tác:<br/>Cùng ra quyết định, chia lát cắt"]
    C --> E["Năng lực kỹ thuật:<br/>Tạo Increment đạt chất lượng"]
    E --> D["Phần mềm dùng được<br/>và được quan sát"]
    D --> F["Bằng chứng, phản hồi,<br/>sự cố, outcome"]
    F -. "Học và thích ứng" .-> U
    F -. "Cải thiện năng lực" .-> P
    F -. "Cải thiện phối hợp" .-> C
    F -. "Cải thiện engineering" .-> E
~~~

Sơ đồ diễn tả **các năng lực liên hệ lặp lại**, không phải quy trình tuần tự cứng: chỉ khi sản phẩm hoàn hảo mới được cộng tác, rồi mới được code. Trên thực tế, đội cần làm việc **đồng thời** ở ba chiều trong một lát cắt nhỏ.

### 1.4. Thực hành theo hướng thực nghiệm

Đội có thể dùng câu hỏi:

1. **Mục tiêu cần đạt:** người dùng đang gặp vấn đề gì?
2. **Bằng chứng hiện tại:** lỗi, phản hồi, flow, dữ liệu nào đáng tin?
3. **Khả năng còn thiếu:** hiểu khách hàng, phối hợp quyết định hay kỹ thuật?
4. **Thử nghiệm nhỏ:** thay đổi gì đủ an toàn và có thể kiểm tra?
5. **Kết quả sau thử:** có giao phần mềm có ích và đạt chất lượng tốt hơn không?
6. **Quyết định:** giữ, điều chỉnh, mở rộng hay dừng thực hành?

Các câu hỏi này thể hiện tinh thần **empiricism** của Scrum và cải tiến tiến hóa theo Kanban nhưng không thay thế đầy đủ định nghĩa của từng cách tiếp cận.

## 2. Ba trụ cột năng lực và sự phụ thuộc lẫn nhau

Thay vì một danh sách đào tạo rời rạc, hãy nhìn **năng lực tập thể tạo giá trị đầu-cuối**.

### 2.1. Ba trụ cột

| Trụ cột | Điều đội cần làm được | Bằng chứng quan sát được |
|---|---|---|
| **Cộng tác (collaboration)** | Nói rõ vấn đề, xử lý bất đồng, phối hợp vượt chuyên môn, ra quyết định minh bạch, nhận/gửi phản hồi | Một PBI được làm rõ và hoàn tất không phải đi qua nhiều vòng bàn giao mơ hồ; blocker được giải quyết có owner |
| **Sản phẩm (product)** | Hiểu người dùng, tạo giả thuyết, ưu tiên giá trị, làm rõ AC và đánh giá outcome | Product Goal rõ, backlog có thứ tự, thử nghiệm với người dùng, thay ưu tiên theo bằng chứng |
| **Kỹ thuật (engineering)** | Chia phần mềm thành Increment, test, tích hợp, refactor, vận hành và bảo vệ dữ liệu/chất lượng | Build tích hợp ổn định, thay đổi nhỏ đạt DoD, ít lỗi hồi quy nghiêm trọng, có khả năng phục hồi |

Nói **“kỹ thuật”** ở đây không chỉ là khả năng code nhanh. Nó gồm thiết kế thay đổi được, tính đúng đắn, hiệu năng, bảo mật, accessibility, quan sát vận hành và khả năng giao sản phẩm trong giới hạn phù hợp.

### 2.2. Điều gì xảy ra nếu phát triển lệch?

| Kết hợp lệch | Dấu hiệu | Rủi ro |
|---|---|---|
| **Cộng tác tốt + sản phẩm tốt, kỹ thuật yếu** | Mọi người thống nhất mục tiêu nhưng thay đổi nhỏ vẫn làm hỏng release | Feedback chậm, không thể giao tăng dần an toàn |
| **Sản phẩm tốt + kỹ thuật tốt, cộng tác yếu** | Tìm ra giải pháp có giá trị nhưng các nhóm giữ backlog/phạm vi riêng | Hàng chờ, xung đột, quyết định chậm |
| **Cộng tác tốt + kỹ thuật tốt, sản phẩm yếu** | CI xanh và đội làm việc thân thiện nhưng sản phẩm ít người dùng | Giao nhiều output không giải quyết vấn đề |
| **Chỉ mạnh về nghi thức Scrum** | Sprint Planning, Daily, Review đầy đủ nhưng demo chỉ là slide | Agile ở hình thức, chưa có Increment/feedback thật |
| **Chỉ mạnh ở coaching kỹ năng mềm** | Họp dễ chịu hơn nhưng test và deploy vẫn cuối kỳ | Trở ngại cấu trúc không biến mất |
| **Chỉ mạnh ở công cụ/CI** | Deploy nhanh các giả định sai | Tăng tốc giao thứ không có giá trị hoặc tăng tốc tạo lỗi |

Không cần phân bổ **đúng một phần ba ngân sách** cho từng trụ cột. Phát triển song song nghĩa là **không bỏ quên năng lực tối thiểu và quan hệ phụ thuộc** của trụ cột nào; mức đầu tư cụ thể phụ thuộc dữ liệu và rủi ro.

### 2.3. Tình huống minh họa: học viên không vào được bài

Một user story:

> **“Là học viên đã ghi danh hợp lệ, tôi muốn vào bài đầu từ trang trạng thái đơn để có thể bắt đầu học mà không cần nhờ hỗ trợ.”**

Để giao một lát cắt dùng được, đội cần:

- **Sản phẩm:** hiểu “hợp lệ”, các trường hợp thanh toán chờ/thất bại, hành trình người học, tiêu chí chấp nhận và kết quả cần đo.
- **Cộng tác:** Product Owner, Developers, người có chuyên môn kiểm thử, thiết kế và vận hành thảo luận ví dụ; thống nhất ownership API quyền và xử lý phụ thuộc.
- **Kỹ thuật:** viết test cho trạng thái/quyền, tích hợp API–DB–UI, bảo vệ callback lặp, triển khai an toàn, theo dõi lỗi sau release.

Ba loại công việc cần diễn ra **trong cùng chu kỳ học và giao giá trị**, không giao lần lượt cho ba nhóm đào tạo cách nhau nhiều tháng.

### 2.4. Năng lực riêng và năng lực hệ thống

Một Developer giỏi TDD không giúp mọi PBI có regression tests nếu pipeline chung không cho chạy. Một Product Owner giỏi discovery không giúp công ty biết outcome nếu không được tiếp cận học viên hoặc không có dữ liệu. Một Scrum Master giỏi facilitation không thể tự thay quyền ưu tiên mâu thuẫn từ quản lý nhiều tầng.

Vì thế đánh giá năng lực cần xem cả:

1. **Kỹ năng của người và nhóm.**
2. **Điều kiện để sử dụng kỹ năng:** thời gian, quyền quyết định, môi trường, dữ liệu, cấu trúc nhóm.
3. **Bằng chứng kỹ năng tạo hiệu quả** trong dòng công việc.

Nếu thiếu điều kiện thứ hai, đẩy thêm trách nhiệm cá nhân hoặc lớp học có thể không giải quyết được vấn đề.

## 3. Năng lực cộng tác cần luyện cùng công việc sản phẩm

“Giao tiếp tốt” không có nghĩa ai cũng nói nhiều trong Daily Scrum. Cộng tác có chất lượng là khả năng **chia sẻ hiểu biết quan trọng, ra quyết định kịp thời, phản hồi an toàn và cùng hoàn tất phần giá trị**, kể cả khi có bất đồng.

### 3.1. Những kỹ năng cần thiết

| Kỹ năng | Hành vi cụ thể | Dấu hiệu thực hành |
|---|---|---|
| **Lắng nghe và làm rõ** | Hỏi điều người khác quan sát, giả định, muốn đạt; diễn giải lại | Ít hiểu nhầm yêu cầu sau refinement |
| **Phản hồi có bằng chứng** | Nêu sự kiện, tác động và đề xuất; tránh gắn nhãn cá nhân | Lỗi được thảo luận mà không đổ lỗi |
| **Facilitation** | Giúp nhiều góc nhìn xuất hiện rồi chốt quyết định | Cuộc họp có câu hỏi và hành động rõ |
| **Giải quyết xung đột** | Phân biệt bất đồng mục tiêu, dữ liệu, giải pháp và quyền | Nhóm không trì hoãn quyết định khó |
| **Làm rõ quyền quyết định** | Ai quyết định giá trị, kỹ thuật, an toàn và release? | Giảm lệnh ưu tiên mâu thuẫn |
| **Phối hợp vượt chuyên môn** | Developers, QA, UX, vận hành cùng xét hành vi | Ít hạng mục bị chuyển đi chuyển lại |
| **Tâm lý an toàn** | Mọi người dám nêu rủi ro, lỗi, nghi ngờ và phản biện | Các vấn đề được phát hiện sớm thay vì che giấu |
| **Phối hợp không đồng bộ** | Viết context, quyết định, contract để người khác dùng được | Hạn chế lặp lại câu hỏi và chờ người cụ thể |
| **Học qua retrospective** | Xem dữ liệu, chọn một cải tiến nhỏ và kiểm tra lại | Retrospective không chỉ ghi “cần giao tiếp tốt hơn” |

### 3.2. Thực hành nghe đúng vấn đề

Người phụ trách hỗ trợ nói: “Học viên cứ gửi ticket vì không vào được khóa.” Một cách phản hồi nhanh nhưng kém là: “Đội backend lại có lỗi.”

Cách hỏi có ích hơn:

- Học viên nào, loại khóa nào và điều kiện nào?
- Có đơn đã xác nhận nhưng chưa cấp quyền, hay người dùng không hiểu trạng thái?
- Đây là lỗi mới, lỗi dữ liệu cũ hay người dùng dùng thiết bị cụ thể?
- Những trường hợp nào có thể tái hiện?
- Nếu sửa được, người học sẽ đạt điều gì và dấu hiệu xác nhận là gì?

Nhờ đó, nhóm chuyển từ **phán xét người** sang **hiểu vấn đề và cùng kiểm chứng**.

### 3.3. Phản hồi dựa trên sự kiện

**Phản hồi gây phòng thủ:**

> “Bạn viết yêu cầu lúc nào cũng mơ hồ, QA phải đoán.”

**Phản hồi hữu ích:**

> “Trong PBI ENR-17, chúng ta chưa thống nhất hành vi khi thanh toán đang chờ; hai trường hợp kiểm thử có kết quả mong đợi khác nhau. Điều này làm integration test fail muộn. Tôi đề xuất trước khi triển khai lát cắt tiếp theo, Product Owner và Developers cùng chốt ba ví dụ trạng thái và nguồn xác thực.”

Câu thứ hai có:

1. Sự kiện quan sát được.
2. Hậu quả cho công việc/kết quả.
3. Nhu cầu làm rõ.
4. Đề xuất hành động có thể kiểm chứng.

Đây là kỹ năng nên luyện **ngay khi đang xử lý PBI thật**, không chỉ qua trò chơi đóng vai trong khóa đào tạo.

### 3.4. Bất đồng là dữ liệu, không phải cản trở phải loại bỏ

Giả sử Product Owner muốn phát hành nhanh thông báo “Thanh toán thành công”, Developers phát hiện callback chưa xác thực. Hai góc nhìn **giá trị sớm và an toàn** không được giải quyết bằng bỏ một bên.

Quy trình ngắn:

1. **Cùng phát biểu mục tiêu:** học viên biết trạng thái và vào bài đúng quyền.
2. **Liệt kê ràng buộc:** không báo thành công giả, không cấp quyền trái phép.
3. **Phân biệt bằng chứng với giả định:** đối tác đã có xác nhận hợp lệ hay chưa?
4. **Đưa ra phương án:** hiển thị trạng thái chờ, phát hành giới hạn, hoặc hoàn tất xác thực trước.
5. **Quyết định theo thẩm quyền:** Product Owner về thứ tự/giá trị, Developers về cách triển khai, người có thẩm quyền về guardrails.
6. **Ghi cách kiểm chứng:** test, quan sát người dùng, tình huống lỗi.

Nếu đội không thể tranh luận an toàn về rủi ro, chất lượng dễ bị hy sinh để giữ bầu không khí “đồng thuận”.

### 3.5. Tâm lý an toàn không phải né trách nhiệm

Mọi người được khuyến khích nêu lỗi và bất định không có nghĩa bỏ Definition of Done hoặc không ai chịu trách nhiệm sửa. **An toàn tâm lý giúp minh bạch nhanh**; trách nhiệm chuyên môn giúp nhóm xử lý bằng chứng và cải tiến.

Ví dụ khi production có sự cố:

- Trước hết giảm ảnh hưởng và hỗ trợ người dùng.
- Thu thập bằng chứng và dòng thời gian sự kiện.
- Xem cơ chế hệ thống cho phép lỗi lọt qua: AC, API contract, CI, dữ liệu, phản hồi.
- Đưa ra hành động phòng ngừa có owner và mốc xem lại.
- Không biến retrospective thành cuộc tìm người để quy lỗi theo cảm tính.

### 3.6. Kỹ năng cộng tác cần xem ở cấp luồng công việc

Một workshop facilitation được đánh giá tốt chưa đủ chứng minh đội phối hợp tốt hơn. Hãy quan sát:

- Có PBI nào bị blocked do quyết định mơ hồ?
- Người có liên quan có được trao đổi trước khi phát triển/đổi contract?
- Thời gian từ khi phát hiện blocker đến khi có quyết định phù hợp ra sao?
- Có tăng WIP chỉ vì mọi người né giúp hoàn tất công việc của nhau?
- Team retrospective có tạo một thay đổi được thử và xem lại?

Những tín hiệu ấy cần được diễn giải theo loại công việc và chất lượng, không dùng để xếp hạng ai phát biểu nhiều hơn.

## 4. Năng lực sản phẩm: hiểu vấn đề và kiểm chứng giá trị trước khi mở rộng giải pháp

Nếu đội chỉ quen nhận yêu cầu rồi phát triển theo thứ tự người khác giao, việc chuyển sang Sprint không tự làm Product Backlog có giá trị hơn. **Năng lực sản phẩm** cho phép đội chuyển từ “xây tính năng gì?” sang “người dùng cần đạt kết quả nào, chúng ta tin điều gì và cần kiểm tra ra sao?”.

### 4.1. Những kỹ năng sản phẩm cần phát triển

| Kỹ năng | Câu hỏi đội cần trả lời | Bằng chứng hành vi |
|---|---|---|
| **Tìm hiểu người dùng** | Ai gặp vấn đề, trong bối cảnh nào, hậu quả ra sao? | Quan sát/hội thoại phù hợp, phân đoạn và giả định được công bố |
| **Phân biệt output–outcome–impact** | Xây gì, người dùng thay đổi hành vi gì, vì sao quan trọng? | Mục tiêu không chỉ là số màn hình/API đã giao |
| **Xây giả thuyết và xác thực** | Giải pháp này vì sao có thể giúp, cần học điều gì trước? | Thử nghiệm nhỏ, phản hồi và quyết định giữ/sửa/dừng |
| **Product Goal và chiến lược** | Trạng thái tương lai có giá trị mà sản phẩm hướng tới là gì? | Product Goal dẫn dắt việc chọn PBI |
| **Product Backlog ordering** | Chọn làm gì trước theo giá trị, rủi ro, phụ thuộc và điều kiện? | Backlog có thứ tự có nghĩa, được cập nhật theo bằng chứng |
| **User story và slicing** | Lát cắt nào đem lại khả năng nhỏ nhưng dùng được? | PBI không chỉ chia thành task UI/API/test rời rạc |
| **Acceptance criteria và ví dụ** | Khi nào hành vi được xem là đúng? | Trạng thái thành công, lỗi, biên, quyền có ví dụ thống nhất |
| **Outcome measurement** | Sau khi cung cấp, người dùng có đạt mục tiêu không? | Metric có tử/mẫu số, cohort, cửa sổ, guardrails |
| **Stakeholder collaboration** | Ai có nhu cầu và có quyền nào? | Quyết định ưu tiên có căn cứ, không bởi người nói lớn nhất |

Không nên kỳ vọng chỉ Product Owner phải biết mọi kỹ năng trên. **Product Owner chịu trách nhiệm tối đa hóa giá trị và Product Backlog trong Scrum**, nhưng Developers, UX, analytics, chuyên gia nghiệp vụ và stakeholders đóng góp hiểu biết, bằng chứng và phương án. Năng lực sản phẩm là một **năng lực cộng tác của đội quanh một accountability rõ**.

### 4.2. Phân biệt điều được giao và kết quả cần tạo

Giả sử người quản lý nói: “Thêm nút Thanh toán lại.”

Trước khi biến thành user story, nhóm hỏi:

1. Vấn đề quan sát được là người học không hiểu trạng thái, giao dịch bị lỗi hay phương thức thanh toán không phù hợp?
2. Nút thanh toán lại có thể tạo **giao dịch trùng** khi giao dịch đầu tiên đang PENDING không?
3. Có cần hướng dẫn chờ, kiểm tra trạng thái hoặc liên hệ hỗ trợ thay vì tạo giao dịch mới?
4. Outcome mong muốn là giảm bỏ dở, giảm yêu cầu hỗ trợ hay tăng tỷ lệ hoàn tất hợp lệ?
5. Rủi ro bảo mật và tính đúng đắn nào không được đánh đổi?

Nếu câu trả lời chỉ có thể là “vì lãnh đạo muốn”, đội chưa đủ thông tin để chọn giải pháp an toàn. Cần làm rõ **vấn đề và ràng buộc**, không mặc định thực hiện yêu cầu dưới dạng UI cụ thể.

### 4.3. Một hypothesis statement thực dụng

~~~text
CHUNG TOI TIN RANG:
  Hoc vien bi mac ket do thong diep PENDING khong ro
  va khong biet khi nao duoc vao bai.

NEU CHUNG TA:
  Hien thi trang thai, buoc tiep theo va duong tro giup ro rang,
  dong thoi giu dung quy tac cap quyen.

THI:
  Nhieu hoc vien hop le se tu hoan tat hanh trinh,
  it yeu cau ho tro do nham lan hon.

BANG CHUNG CAN:
  Ket qua usability observation phu hop,
  ty le vao bai dau theo cohort, nhom ticket ho tro,
  khong tang loi giao dich/cap quyen.

BAT DINH:
  Co the van la loi cap quyen that, khong phai loi thong diep.
~~~

Đây là **giả thuyết**, không phải kết luận chắc chắn. Nếu dữ liệu cho thấy lỗi thuộc nghiệp vụ cấp quyền, đội cần đổi trọng tâm thay vì cứ tối ưu câu chữ.

### 4.4. Product discovery và product delivery nên liên hệ liên tục

**Discovery** là tìm hiểu nhu cầu, cơ hội, giả định và các giải pháp có triển vọng. **Delivery** là tạo và cung cấp phần mềm có thể sử dụng, đáp ứng các điều kiện kỹ thuật/nghiệp vụ phù hợp.

Hai luồng này không cần thành hai phòng ban cách biệt với hàng chờ bàn giao:

~~~mermaid
flowchart TD
    N["Phản hồi người dùng và vấn đề"] --> H["Giả thuyết về nhu cầu/giải pháp"]
    H --> X["Thử nghiệm / quan sát sớm"]
    X --> D["Chọn lát cắt Product Backlog"]
    D --> B["Build, test, tích hợp, đạt DoD"]
    B --> O["Quan sát outcome và chất lượng"]
    O -. "Học thêm" .-> N
    O -. "Điều chỉnh giả thuyết" .-> H
~~~

Đội có thể:

- Quan sát người dùng một số lần trong tuần rồi đổi ví dụ acceptance.
- Làm rõ một nguy cơ nghiệp vụ trong refinement.
- Dùng nguyên mẫu để thử cách diễn đạt, nhưng không gọi nguyên mẫu chưa kiểm chứng là Increment an toàn.
- Giao lát cắt nhỏ đã đạt DoD và nhận dữ liệu sử dụng để tiếp tục học.

**Không ép mọi thay đổi phải chạy A/B test.** Với tính đúng đắn thanh toán, phân quyền hoặc ràng buộc pháp lý, cần bảo vệ điều kiện trước khi phát hành; không thử nghiệm sự nguy hiểm trên người dùng để lấy dữ liệu.

### 4.5. Viết user story theo giá trị, rồi làm rõ điều kiện

Ví dụ:

> **Là học viên có đơn đang được xử lý, tôi muốn biết trạng thái và bước tiếp theo rõ ràng, để không tạo thêm giao dịch hoặc bỏ dở khóa học vì nhầm lẫn.**

Các acceptance examples:

| Tình huống | Kết quả nghiệp vụ mong đợi |
|---|---|
| Đơn đang PENDING, chưa có xác nhận hợp lệ | Không báo thanh toán thành công và không cấp quyền sai |
| Đơn được CONFIRMED từ nguồn đáng tin | Hiển thị trạng thái đúng, quyền học được cấp theo quy tắc |
| Dịch vụ đối tác timeout | Không tự chuyển thành SUCCESS, hướng dẫn xử lý theo chính sách |
| Callback được gửi lại | Không tạo quyền học/giao dịch trùng sai |
| Học viên khác xem đơn | Không được đọc dữ liệu riêng trái quyền |
| Học viên dùng bàn phím hoặc công nghệ hỗ trợ | Trạng thái và hành động tiếp theo có thể tiếp cận theo yêu cầu phù hợp |

Product Owner không cần tự viết mọi test; Developers, tester, UX và những bên liên quan có thể cùng **Specification by Example**, rồi tạo bằng chứng kiểm chứng trên build phù hợp.

### 4.6. Ưu tiên không phải chỉ sắp thứ tự theo doanh thu

Trong chuyển đổi Agile, một Product Owner có thể bị áp lực giao tính năng dễ nhìn thấy hơn công việc về độ tin cậy hoặc nợ kỹ thuật.

Cần cân nhắc:

- Giá trị người dùng và mục tiêu sản phẩm.
- Rủi ro cấp quyền, bảo mật và tính toàn vẹn.
- Chi phí chậm trễ, deadline thật và phụ thuộc.
- Khả năng học sớm, đảo ngược quyết định.
- Năng lực giao/khả năng kiểm chứng của đội.
- Điều kiện chất lượng không thể hy sinh.

Các cách tính WSJF, RICE hay cost-of-delay có thể hỗ trợ **cuộc trao đổi**, nhưng không phải công thức bắt buộc của Scrum; khi số đầu vào không chắc, đừng để điểm số tạo ra cảm giác chính xác giả.

### 4.7. Đo khả năng sản phẩm bằng hành vi và bằng chứng

**Đừng chỉ đếm** số buổi phỏng vấn người dùng, số hypotheses hoặc số PBI được chỉnh. Hãy xem:

1. Có quyết định sản phẩm nào thay đổi theo bằng chứng không?
2. Có ngăn được một tính năng không hữu ích hoặc nguy hiểm trước khi phát triển lớn không?
3. Product Goal có giúp nói “chưa làm” với yêu cầu ít giá trị hơn không?
4. Hành vi quan trọng có AC rõ và dữ liệu kiểm chứng phù hợp không?
5. Người dùng có thực sự hoàn thành tác vụ, trong khi guardrails vẫn giữ?

Số buổi discovery là **hoạt động**, còn học được gì và đổi quyết định nào mới là bằng chứng năng lực sản phẩm có tác dụng.

## 5. Năng lực kỹ thuật: khả năng thay đổi phần mềm an toàn và thường xuyên

Agile cần phản hồi sớm. Nhưng nếu một thay đổi nhỏ phải đợi ba tuần để tích hợp, kiểm thử và triển khai, tốc độ học của sản phẩm bị giới hạn. Bởi vậy năng lực kỹ thuật không phải “việc hậu trường” để làm sau chuyển đổi; nó là **điều kiện giúp thích ứng**.

### 5.1. Những kỹ năng kỹ thuật quan trọng

| Kỹ năng | Tác dụng đối với Agile | Dấu hiệu áp dụng |
|---|---|---|
| **Thiết kế thay đổi được** | Giảm chi phí sửa khi học thêm | Module/contract rõ, refactor an toàn |
| **Test design** | Kiểm chứng hành vi và rủi ro, không chỉ đếm test | Test có assertion, dữ liệu biên và điều kiện lỗi |
| **Test-Driven Development (TDD)** | Phản hồi nhanh về hành vi và thiết kế ở lớp phù hợp | Vòng Red–Green–Refactor được thực hành có chủ đích |
| **Continuous Integration** | Phát hiện xung đột sớm từ thay đổi nhỏ | Tích hợp và kiểm tra thường xuyên, lỗi được xử lý |
| **Contract/integration tests** | Bảo vệ giao tiếp giữa thành phần/nhóm | API/data versions không âm thầm phá consumer |
| **Refactoring** | Duy trì khả năng thay đổi mà không đổi hành vi mong đợi | Có test bảo vệ, nợ kỹ thuật được kiểm soát |
| **Continuous Delivery practices** | Phần mềm sẵn sàng cung cấp an toàn khi phù hợp | Pipeline, cấu hình và rollout/rollback có bằng chứng |
| **Security/privacy/accessibility** | Không tạo giá trị bằng cách gây hại/loại trừ người dùng | Các guardrails được thiết kế và kiểm chứng sớm |
| **Observability và incident response** | Biết điều gì xảy ra trong sử dụng thật | Logs, metrics, traces và phản hồi sự cố phù hợp |
| **Migrations và tương thích** | Cho phép thay dữ liệu/API từng bước | Không phá phiên bản đang dùng, có kế hoạch khôi phục |

Không phải mọi nhóm cần độ sâu ngang nhau ở mọi kỹ năng. Một dịch vụ xử lý tiền có trọng tâm tính toàn vẹn, idempotency và audit; một ứng dụng hỗ trợ học viên có thể cần đầu tư đặc biệt vào accessibility và UX. **Tối thiểu chung là nhóm có thể tạo thay đổi đúng, an toàn, kiểm chứng được theo sản phẩm họ chịu trách nhiệm**.

### 5.2. TDD không phải “viết càng nhiều test càng tốt”

Một vòng TDD điển hình:

1. **Red:** viết một test nhỏ mô tả hành vi cần có và thấy nó thất bại vì chức năng chưa được triển khai.
2. **Green:** thay đổi code vừa đủ để test đạt.
3. **Refactor:** cải thiện cấu trúc, giữ hành vi đã được test bảo vệ.

Ví dụ quy tắc đơn giản cho đơn ghi danh:

~~~java
@Test
void pendingPaymentMustNotGrantCourseAccess() {
    PaymentDecision decision = policy.evaluate(
        PaymentStatus.PENDING,
        AccountStatus.ACTIVE
    );
    assertFalse(decision.grantAccess());
}
~~~

Đây chỉ là **ví dụ unit test**. Nó không tự xác nhận nguồn callback tin cậy, phân quyền API, database concurrency hoặc logic production. Để bảo vệ hệ thống thật, đội cần phối hợp **integration, contract, security và exploratory testing** theo rủi ro.

**Không nên biến TDD thành cuộc thi số lượng test**, hoặc cho rằng một chức năng chỉ cần unit tests là đủ chất lượng.

### 5.3. CI là một cơ chế phản hồi, không chỉ là nút chạy build

Một pipeline có thể kiểm tra:

~~~mermaid
flowchart LR
    A["Thay đổi nhỏ"] --> B["Build + static checks"]
    B --> C["Unit/API tests"]
    C --> D["Contract/integration checks"]
    D --> E["Increment đạt điều kiện chất lượng"]
    E --> F["Cung cấp an toàn khi phù hợp"]
    F --> G["Quan sát và học"]
    G -. "Hồi quy hoặc phản hồi" .-> A
~~~

Các bước cụ thể phải theo sản phẩm, độ phức tạp và rủi ro. Có thể có kiểm tra chuyên biệt ngoài đường chạy nhanh, nhưng phải công bố **gate nào bắt buộc** và xử lý test thất bại trung thực.

Một CI có 1.000 tests pass không bảo đảm hành vi thanh toán đúng nếu chưa kiểm tra callback lặp hay quyền truy cập. Chất lượng pipeline cần xét **mức rủi ro được bảo vệ, độ tin cậy và tốc độ nhận tín hiệu**, không chỉ số lượt chạy.

### 5.4. Kỹ thuật và chất lượng gắn với Definition of Done

Trong Scrum, **Definition of Done (DoD)** là commitment của Increment. PBI chưa đạt DoD không thể được xem là một phần Increment Done.

Một DoD minh họa có thể yêu cầu:

- Thay đổi được tích hợp vào bản build phù hợp.
- Các acceptance criteria liên quan có bằng chứng kiểm chứng.
- Các kiểm tra rủi ro chất lượng/bảo mật áp dụng được đáp ứng.
- Không có lỗi nghiêm trọng chưa kiểm soát theo chính sách.
- API và dữ liệu tương thích với consumer liên quan.
- Khả năng quan sát, vận hành và khôi phục phù hợp phạm vi cung cấp.

**Đừng dùng DoD như một danh sách tài liệu vô hạn** để giữ mọi PBI trong trạng thái chờ; đồng thời không hạ DoD chỉ để tăng số PBI Done. DoD phải tạo **minh bạch về chất lượng chung** cho Increment.

### 5.5. Refactoring và evolutionary design giảm chi phí đổi hướng

Khi Product Owner học được người dùng cần hành vi khác, Developers phải thay code. Nếu thiết kế có phụ thuộc chặt, thiếu test và data contracts mơ hồ, thay một trạng thái có thể phá nhiều nơi.

Một vòng cải tiến:

1. Xác định hành vi đã được yêu cầu và rủi ro thay đổi.
2. Thêm/kiểm tra tests để bảo vệ hành vi hiện có và trường hợp lỗi quan trọng.
3. Refactor từng bước nhỏ để làm ranh giới rõ.
4. Tích hợp thường xuyên; kiểm tra contract và các thành phần liên quan.
5. Triển khai theo cách kiểm soát được và theo dõi kết quả.

Đây là **đầu tư khả năng thay đổi**, không phải lý do xây kiến trúc tổng quát cho mọi khả năng tương lai. Nguyên tắc **YAGNI** nhắc tránh thiết kế khả năng chưa cần mà không có lý do rủi ro cụ thể; đồng thời phải giữ những thuộc tính thiết yếu như bảo mật và khả năng khôi phục.

### 5.6. Không dùng production như nơi phát hiện đầu tiên các lỗi không chấp nhận được

Quan sát production, canary hoặc feature flags giúp học hành vi thật, nhưng không thay thế:

- Kiểm tra phân quyền và riêng tư trước khi cung cấp.
- Xác minh nguồn giao dịch và tính nhất quán.
- Kiểm thử hành vi lỗi ảnh hưởng nhiều người.
- Những điều kiện pháp lý/an toàn của phạm vi.

Luyện kỹ thuật song song với sản phẩm nghĩa là **có thể thử sớm những giả thuyết phù hợp** trong khi giữ rủi ro không chấp nhận được ngoài phạm vi thử nghiệm.

### 5.7. Khi kỹ thuật không đủ, đội bị buộc phải lập kế hoạch quá chi tiết

Nếu kiểm thử thủ công kéo dài hai tuần và deploy cần sự tham gia của nhiều phòng, đổi một yêu cầu ở giữa Sprint có chi phí cao. Các bên có thể cố **đóng băng mọi chi tiết trước** để tránh chi phí đó.

Cải thiện CI, test, hợp đồng và thiết kế cho phép đội **trì hoãn quyết định có thể đảo ngược**, nhận feedback sớm và giữ chất lượng khi thay đổi. Đây là kết nối quan trọng giữa **engineering excellence** và **adaptive planning**, chứ không phải một hoạt động kỹ thuật tách rời chiến lược sản phẩm.

## 6. Kết nối ba trụ cột thành một vòng làm việc trên lát cắt nhỏ

Sai lầm dễ mắc là mở ba “chương trình chuyển đổi” song song nhưng độc lập:

- HR tổ chức khóa kỹ năng giao tiếp.
- Product đưa Product Owners đi học discovery.
- Engineering tổ chức đào tạo TDD.

Mọi người đều học, nhưng khi quay lại họ vẫn nhận công việc cũ, quyền cũ, CI cũ và cách ưu tiên cũ. **Lịch học song song chưa đủ; năng lực phải gặp nhau trong một vòng công việc thật.**

### 6.1. Một lát cắt có thể tạo ba cơ hội học cùng lúc

Chọn một PBI nhỏ:

> “Học viên có đơn đang xử lý thấy trạng thái đáng tin và hướng dẫn phù hợp, không nhận quyền học sai.”

| Thời điểm | Cộng tác | Sản phẩm | Kỹ thuật |
|---|---|---|---|
| **Làm rõ vấn đề** | Lắng nghe hỗ trợ/học viên, xác định bất đồng | Phân biệt lỗi hiển thị với lỗi entitlement | Điều tra log và trạng thái dữ liệu |
| **Chọn lát cắt** | PO–Developers–QA thống nhất quyết định | Viết user story, AC, guardrails | Xác định API/DB/UI và test cần thiết |
| **Triển khai** | Pairing, review, giải quyết contract | Kiểm tra ví dụ nghiệp vụ khi phát hiện trường hợp mới | TDD phù hợp, CI, integration tests |
| **Xác nhận Done** | Chia sẻ evidence, minh bạch rủi ro | AC được kiểm chứng, mục tiêu lát cắt rõ | Increment đạt DoD |
| **Phản hồi** | Cùng đọc kết quả, tránh đổ lỗi | Quan sát tác vụ người học, hỗ trợ và phân đoạn | Theo dõi lỗi, latency, khả năng khôi phục |
| **Retrospective** | Phản hồi về cách làm và quyết định | Sửa giả thuyết/ưu tiên | Cải tiến test/data/CI |

Đây là **cách xây kỹ năng có tác dụng chuyển giao**: những người khác chuyên môn học cách dùng kiến thức của nhau ngay trong hoàn cảnh sản phẩm.

### 6.2. Three Amigos là kỹ thuật, không phải một vai trò Scrum bắt buộc

Một thực hành có ích là để góc nhìn **nghiệp vụ/sản phẩm**, **phát triển** và **kiểm thử** cùng thảo luận ví dụ trước khi triển khai (thường gọi là Three Amigos).

Ba góc nhìn có thể được đại diện bởi Product Owner, Developer và tester, nhưng số lượng/role **không cố định theo luật Scrum**; đôi lúc cần thêm UX, bảo mật, vận hành hoặc đối tác.

Ví dụ:

~~~gherkin
Feature: Trang thai don ghi danh

  Scenario: Giao dich dang cho
    Given don hang cua hoc vien A dang cho xac nhan
    And chua co xac nhan thanh cong hop le
    When A xem trang thai don
    Then trang hien thi dang xu ly
    And khong mo quyen hoc do don hang nay

  Scenario: Callback hop le duoc gui lai
    Given don da duoc xac nhan hop le
    And quyen hoc da duoc cap
    When dich vu doi tac gui lai su kien thanh cong
    Then he thong khong tao quyen hoc trung sai

  Scenario: Tai khoan khac
    Given don hang thuoc hoc vien A
    When hoc vien B yeu cau xem don
    Then API tu choi theo chinh sach quyen
~~~

Ví dụ Gherkin giúp mọi người **đồng bộ nghĩa nghiệp vụ**. Nó không tự thành bằng chứng thực thi; phải có test implementation, dữ liệu, build, môi trường và assertions đúng.

### 6.3. Luyện một kỹ năng trong hai vòng liên tiếp

Nếu muốn cải thiện **đặt câu hỏi làm rõ**, đừng chỉ giao mục tiêu “cộng tác tốt hơn”. Một thử nghiệm:

**Vòng thứ nhất:**

- Mỗi PBI rủi ro vừa/cao cần nêu **ít nhất một trường hợp lỗi hoặc bất định chính**.
- Product Owner, Developers và người có góc nhìn test cùng xem ví dụ trước khi triển khai.
- Ghi loại câu hỏi phải quay lại giải thích sau khi bắt đầu.

**Vòng thứ hai:**

- Giữ cách làm nếu nó giúp giảm hiểu nhầm.
- Điều chỉnh cách tổ chức để không kéo cả team vào mọi PBI đơn giản.
- Quan sát những lỗi/hàng chờ phát hiện muộn, không chỉ số cuộc họp refinement.

Nếu thiếu CI và integration tests, thêm câu hỏi sớm chưa đủ. **Đồng thời** chọn một cải tiến kỹ thuật để giảm thời gian kiểm chứng những ví dụ đã làm rõ.

### 6.4. Luyện “làm xong” thay vì “bắt đầu thật nhiều”

Một nhóm có thể đầu tư vào cộng tác bằng cách **cùng hoàn tất một item gần Done**, không chỉ tổ chức team-building:

1. Hiển thị WIP và work item age.
2. Xác định item có giá trị đang chờ kiểm thử, contract hoặc quyết định.
3. Tập trung pairing/swarming có mục đích để tháo chặn.
4. Tích hợp và kiểm chứng cho tới khi đạt DoD.
5. Quan sát tổng cycle time và chất lượng.

**Kanban** cung cấp cách nhìn dòng công việc, **XP** cung cấp thực hành kỹ thuật, **Scrum** cung cấp cơ chế mục tiêu và inspection/adaptation khi dùng phù hợp. Không cần xem ba tên gọi này là những hệ thống cạnh tranh phải chọn một và bỏ phần còn lại; nhưng cũng không tự thêm sự kiện hoặc trách nhiệm rồi gọi đó là yêu cầu chính thức của Scrum.

### 6.5. Kết quả học phải thể hiện trong hành vi của cả nhóm

Ví dụ tín hiệu:

- Trước: PBI ghi danh phải chuyển qua bốn nhóm, chờ tích hợp và chỉ nhận feedback sau vài tuần.
- Sau thử: một lát cắt nhỏ có AC rõ, tích hợp trong vài ngày và được review trên Increment đạt DoD.

Không nên khẳng định tất cả cải thiện là do khóa đào tạo. Có thể nhờ thay CI, giảm phụ thuộc, Product Owner thực quyền hoặc loại công việc dễ hơn. Hãy mô tả **những điều đã thay đổi, chất lượng dữ liệu và giới hạn của kết luận**.

## 7. Bản đồ năng lực đội: nhìn khả năng giao giá trị, không chấm điểm con người

Để đầu tư đúng nơi, đội cần biết **những năng lực nào đang thiếu ở cấp tập thể**. Một bảng tên kỹ năng có thể giúp đối thoại, nhưng nếu biến thành công cụ xếp hạng cá nhân, mọi người sẽ có động lực tự khai cao, che giới hạn hoặc né việc khó.

### 7.1. Bắt đầu từ năng lực cần cho Product Goal

Giả sử Product Goal là giúp học viên ghi danh và vào bài đầu an toàn. Đội cần một số năng lực:

| Nhu cầu năng lực | Vì sao cần | Vùng liên quan |
|---|---|---|
| Hiểu hành trình ghi danh | Phân biệt lỗi trạng thái với nhu cầu người học | Sản phẩm, cộng tác |
| Product Backlog và AC | Chọn lát cắt có giá trị, thống nhất hành vi đúng | Sản phẩm, cộng tác |
| Xử lý xung đột ưu tiên | Khi marketing, hỗ trợ và bảo mật có yêu cầu khác | Cộng tác, sản phẩm |
| API/data contract | Ghi danh, thanh toán và học tập có cùng ngữ nghĩa | Kỹ thuật, cộng tác |
| Automated test/CI | Kiểm chứng nhanh các thay đổi trong luồng | Kỹ thuật |
| Quy tắc entitlement | Không cấp quyền sai hoặc trái phép | Sản phẩm, kỹ thuật |
| Quan sát outcome | Biết học viên đã vào bài và gặp trở ngại gì | Sản phẩm, kỹ thuật |
| Phân tích sự cố và phản hồi | Học từ lỗi production không đổ lỗi | Cộng tác, kỹ thuật |

**Bảng nên xuất phát từ nhu cầu công việc**, không phải lấy một thư viện 200 kỹ năng chung rồi yêu cầu mọi thành viên đạt điểm tối đa.

### 7.2. Các mức năng lực dựa trên hành vi

Có thể dùng bốn mức mô tả **khả năng thực hiện trong bối cảnh nhất định**:

| Mức | Mô tả quan sát được | Ví dụ với kiểm thử tích hợp |
|---|---|---|
| **L1 — Hiểu và nhận biết** | Giải thích mục tiêu, nhận diện rủi ro; cần hướng dẫn khi thực hành | Biết khi nào unit test không đủ kiểm chứng API–DB |
| **L2 — Thực hành với hỗ trợ** | Làm được nhiệm vụ nhỏ khi có pairing, mẫu hoặc review | Bổ sung integration test theo fixture và review |
| **L3 — Thực hiện độc lập phù hợp phạm vi** | Chọn phương pháp hợp lý, giải thích trade-off, xử lý lỗi thông thường | Thiết kế test theo rủi ro và điều tra fail có chứng cứ |
| **L4 — Hỗ trợ người khác và cải thiện hệ thống** | Mentoring, tạo hướng dẫn/tự động hóa, giảm điểm nghẽn lặp | Hỗ trợ đội nâng chất lượng integration test pipeline |

Đây là **thang mô tả gợi ý**, không phải chứng chỉ chung được Agile Manifesto, Scrum Guide hay Kanban Guide quy định. Mức có thể khác theo kỹ năng và phạm vi; người L4 về CI không tự là L4 về product discovery.

### 7.3. Bản đồ năng lực cấp nhóm

Thay vì công bố ma trận tên người, đội có thể tổng hợp năng lực cần để giao một Product Goal:

| Năng lực | Hiện trạng quan sát | Rủi ro nếu thiếu | Cách phát triển |
|---|---|---|---|
| Làm rõ acceptance examples | Có người hướng dẫn, phần lớn PBI vẫn thiếu trường hợp lỗi | Sai yêu cầu bị phát hiện muộn | Three Amigos trên PBI có rủi ro |
| Discovery với học viên | Product Owner có kết quả hỗ trợ nhưng ít quan sát trực tiếp | Ưu tiên theo phỏng đoán | Phỏng vấn/quan sát có mục tiêu, chia sẻ bằng chứng |
| API contract + authz | Hai chuyên gia là nút thắt | Chờ review, lỗi phân quyền | Pairing, test templates và ownership rõ |
| CI/integration tests | Unit tests nhiều, các test môi trường thiếu ổn định | Hồi quy chỉ thấy cuối Sprint | Chọn một pipeline và test fixture đáng tin |
| Retrospective có thử nghiệm | Có họp nhưng hành động không được kiểm tra lại | Cải tiến không thành năng lực | Một thử nghiệm nhỏ, owner và mốc xem lại |
| Incident learning | Sau sự cố chỉ tập trung vá lỗi cục bộ | Cùng nguyên nhân lặp lại | Review không đổ lỗi, học từ contract/DoD/observability |

Điểm yếu quan trọng không phải “chỉ có hai người giỏi API” tự thân, mà là **một Product Goal hoặc dòng công việc bị chặn khi hai người đó không sẵn sàng**. Một nhóm nhỏ vẫn có thể dùng chuyên gia nếu có cách hỗ trợ và chính sách phục vụ phù hợp.

### 7.4. T-shaped skills không nghĩa mọi người phải full-stack

Một người có thể có **chiều sâu** ở kiểm thử bảo mật, dữ liệu hoặc frontend, đồng thời có **chiều rộng đủ** để cộng tác về mục tiêu, rủi ro và hoạt động liền kề. T-shaped skills là hình ảnh hữu ích, nhưng không nên biến nó thành yêu cầu mọi người phải giỏi mọi công nghệ.

Ví dụ:

- Developer frontend hiểu ý nghĩa entitlement và biết chạy contract test.
- Chuyên gia QA hiểu mục tiêu người học, có thể trao đổi với Product Owner về acceptance.
- Product Owner hiểu rủi ro kỹ thuật cơ bản để không hứa cấp quyền khi callback chưa xác thực.
- Chuyên gia platform hiểu hành trình phát hành của product teams để tạo self-service hợp lý.

**Chiều sâu vẫn cần được tôn trọng.** Mục tiêu của chiều rộng là giảm hiểu nhầm/handoff và nâng khả năng phối hợp, không xóa vai trò chuyên môn.

### 7.5. Bus factor và điểm phụ thuộc kiến thức

Một dấu hiệu cần ưu tiên học là mọi thay đổi dữ liệu quyền học phải chờ đúng một cá nhân, kể cả khi người đó chỉ được hỏi trong năm phút.

Điều đội có thể thử:

1. Ghi contract và các quy tắc nghiệp vụ có tác động.
2. Pair hoặc review luân phiên trên một thay đổi nhỏ.
3. Tạo test thể hiện quy tắc và trường hợp lỗi.
4. Để người thứ hai thực hiện một thay đổi có hỗ trợ và kiểm chứng.
5. Xem còn chờ chuyên gia cho mọi việc phổ biến hay không.

Không cần cố tình làm người chuyên môn sâu bị thay thế. **Khả năng chia sẻ kiến thức là tài sản của hệ thống**, giúp chuyên gia tập trung vào các vấn đề phức tạp thay vì giải đáp lặp đi lặp lại.

### 7.6. Kiểm tra năng lực bằng một tình huống, không qua tự chấm suông

Giả sử nhóm muốn biết đã có thể thiết kế một acceptance test cho trạng thái PENDING chưa:

- Cho một PBI thật với trạng thái và tác động.
- Yêu cầu nhóm nêu ví dụ thành công, lỗi, phân quyền.
- Chọn lớp kiểm chứng phù hợp, nêu dữ liệu cần tạo.
- Chạy thử hoặc review một test.
- Ghi điều gì làm được độc lập và điều gì cần hỗ trợ.

Hành vi và bằng chứng tốt hơn câu hỏi “bạn tự chấm mấy điểm kỹ năng kiểm thử?”. Kết quả nên dùng để **lập kế hoạch học**, không làm căn cứ xử phạt hay gắn nhãn cá nhân thiếu năng lực.

## 8. Các phương pháp phát triển kỹ năng ngay trong delivery

Học trong Agile có thể kết hợp lớp học, coaching và thực hành. **Không có một tỷ lệ phần trăm chuẩn** bắt buộc về học trực tiếp so với học từ công việc. Cách chọn phụ thuộc rủi ro, trình độ hiện tại và sự sẵn sàng của môi trường.

### 8.1. Pair programming, pairing nghiệp vụ và mobbing có mục đích

| Cách thực hành | Khi hữu ích | Rủi ro nếu áp dụng máy móc |
|---|---|---|
| **Pair programming** | Chia sẻ kỹ năng, thiết kế test, xử lý code khó hoặc chuyển giao kiến thức | Nếu không luân phiên, một người làm hộ và người còn lại thụ động |
| **Pairing Product Owner–Developer** | Làm rõ hành vi/giá trị và giới hạn kỹ thuật | Không để PO quyết định từng class hoặc Developer tự quyết ưu tiên |
| **Developer–tester pairing** | Chọn rủi ro, test data, kiểm chứng lỗi sớm | Không biến tester thành người chỉ chạy test sau khi code xong |
| **Mob/ensemble programming** | Gỡ vấn đề liên quan nhiều góc nhìn, onboarding hoặc tích hợp khó | Quá đông/thường xuyên gây chi phí họp không đáng |
| **Peer review có phản hồi** | Cải thiện thiết kế, an toàn và hiểu ngữ nghĩa | Review hình thức hoặc chỉ kiểm tra format |

Đội nên đặt mục đích rõ: ví dụ **“sau hai PBI, thêm ít nhất một người có thể tự chẩn đoán lỗi contract thường gặp”**. Không đặt mục tiêu “100% thời gian đều phải pair”.

### 8.2. Deliberate practice: chọn bài tập vừa vượt ngưỡng hiện tại

**Deliberate practice** là luyện tập có mục tiêu và phản hồi, không chỉ lặp thao tác quen thuộc. Một vòng:

1. Chọn **một kỹ năng cụ thể** đang ảnh hưởng dòng công việc.
2. Chọn tình huống có độ khó vừa đủ, rủi ro kiểm soát được.
3. Nhận phản hồi sớm từ người có chuyên môn hoặc test.
4. Sửa cách làm, thử lại.
5. Chuyển sang tình huống thật phù hợp và quan sát tác dụng.

Ví dụ luyện **refactoring có test**:

- Bắt đầu với hàm trạng thái đơn nhỏ có test.
- Refactor giữ hành vi đã xác nhận.
- Chạy unit/integration tests.
- Review thiết kế và ảnh hưởng API.
- Sau đó thử với một phần code có nợ kỹ thuật thật trong sản phẩm.

Không bắt đầu đào tạo kỹ năng bảo mật bằng cách để người học thử trên dữ liệu production thật mà chưa có cơ chế an toàn.

### 8.3. Learning dojo và workshop ngắn

Một **coding dojo** có thể luyện TDD/refactoring; một **product dojo** có thể luyện phỏng vấn người dùng, phân biệt outcome/output; một **collaboration dojo** có thể luyện phản hồi và xử lý bất đồng.

Để tránh thành hoạt động rời rạc, mỗi buổi nên kết thúc bằng:

> “Trong hai Sprint tới, chúng ta sẽ áp dụng phần nào của kỹ năng này cho một PBI cụ thể, ai hỗ trợ và bằng chứng nào cho thấy nó hữu ích?”

Không cần biến mọi workshop thành cam kết cải tiến có số liệu phức tạp, nhưng phải có **đường đi từ học tới thực hành**.

### 8.4. Coaching, mentoring và training khác nhau

| Hình thức | Đóng góp điển hình | Giới hạn |
|---|---|---|
| **Training** | Tạo kiến thức/thuật ngữ chung, kỹ thuật mẫu | Không tự thay đổi hệ thống công việc |
| **Mentoring** | Người có kinh nghiệm hướng dẫn lựa chọn và chuyên môn | Dễ phụ thuộc cá nhân nếu không chia sẻ năng lực |
| **Coaching** | Giúp đội quan sát, phản tư, tự giải quyết và thử cải tiến | Không thay Product Owner/Developers hoặc làm hộ quyết định |
| **Facilitation** | Tạo cuộc trao đổi và quyết định hiệu quả | Không tự giải quyết mọi rủi ro công nghệ |
| **Hands-on pairing** | Học qua thực hiện trên code/PBI có hỗ trợ | Cần thời gian và cách luân phiên vai trò |
| **Communities of Practice** | Chia sẻ giải pháp giữa nhóm, tạo chuẩn tự nguyện | Có thể thành diễn đàn nói nhiều nhưng không thay delivery |

Nên phối hợp những hình thức trên theo điểm nghẽn quan sát được. Nếu vấn đề chính là công cụ CI thiếu quyền truy cập, coaching kỹ năng nghe sẽ không thay được việc **sửa điều kiện kỹ thuật và phân quyền phù hợp**.

### 8.5. Chia sẻ kiến thức qua artifact làm việc

Một số artifact hữu ích:

- **Acceptance examples** thể hiện quy tắc nghiệp vụ.
- **Definition of Done** nêu tiêu chuẩn chung.
- **API/data contracts** và các test tương thích.
- **Decision record** ghi bối cảnh, lựa chọn, trade-off và mốc xem lại.
- **Runbook/incident learning** giúp người khác vận hành và phục hồi.
- **Metric contract** giúp mọi người đọc cùng nghĩa của throughput/cycle time/outcome.

Tài liệu có ích khi nó **được dùng và cập nhật trong luồng thay đổi**, không phải chỉ viết để hoàn thành một KPI “số trang tài liệu”.

### 8.6. Dành năng lực học mà không tách khỏi trách nhiệm giao sản phẩm

Đội cần **không gian thực hành**, đặc biệt khi kỹ năng mới làm công việc chậm hơn ban đầu. Một lựa chọn minh họa:

- Chọn ít PBI hơn trong một Sprint để có thời gian pairing/CI.
- Dùng một PBI thật làm nơi thực hành, thay vì một dự án hoàn toàn khác.
- Giữ DoD và guardrails; tránh coi người học phải tạo sản lượng y hệt chuyên gia ngay ngày đầu.
- Xem lại sau một số Sprint: kỹ năng có giảm bottleneck và lỗi không?

Không có quy tắc phổ quát “dành đúng 20% thời gian” cho mọi đội. Đội và tổ chức cần thương lượng **đầu tư học tập có mục đích** theo Product Goal và khả năng đáp ứng cam kết.

### 8.7. Kiến thức chuyên sâu phải có đường hỗ trợ khi cần

Các lĩnh vực như bảo mật, phân tích dữ liệu, truy cập số, hiệu năng hoặc dữ liệu tài chính có thể cần chuyên gia. Giải pháp không phải buộc mọi người làm chuyên gia trong ba tháng.

Đội có thể:

1. Phát triển nhận biết rủi ro chung để gọi đúng người sớm.
2. Có **service interface hoặc người hỗ trợ** rõ cho tình huống chuyên sâu.
3. Chuẩn hóa những trường hợp thường gặp thành policy, test hoặc công cụ self-service.
4. Có review cần thiết trước thay đổi rủi ro cao.
5. Dùng pairing để mở rộng hiểu biết nhưng không bỏ kiểm soát chuyên môn.

Đây cũng là nơi thiết kế team boundaries và nền tảng kỹ thuật liên quan trực tiếp tới **chiến lược phát triển kỹ năng**.

## 9. Vai trò trong Scrum và trách nhiệm của lãnh đạo khi phát triển ba trụ cột

Một kế hoạch đào tạo dễ thất bại nếu gán mọi cải tiến cộng tác cho Scrum Master, mọi cải tiến sản phẩm cho Product Owner và mọi cải tiến kỹ thuật cho Developers theo nghĩa “mỗi bên chỉ làm phần mình”.

### 9.1. Scrum Guide: accountabilities cần giữ đúng

Theo Scrum Guide 2020:

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm từ công việc của Scrum Team và quản lý Product Backlog hiệu quả; có thể ủy quyền tác vụ nhưng vẫn chịu trách nhiệm.
- **Developers** chịu trách nhiệm tạo mọi khía cạnh của Increment có thể sử dụng mỗi Sprint, lập kế hoạch Sprint Backlog, duy trì chất lượng qua DoD, thích ứng kế hoạch hằng ngày và giữ trách nhiệm chuyên môn với nhau.
- **Scrum Master** chịu trách nhiệm về hiệu quả của Scrum Team, giúp thiết lập Scrum đúng định nghĩa và hỗ trợ đội, Product Owner và tổ chức.
- Scrum Team **cross-functional** và **self-managing**; không có các sub-team hoặc phân cấp bên trong Scrum Team theo Scrum Guide.

Những accountabilities này **không cấm người có chuyên môn khác tham gia**. Nhưng việc thêm tên “Agile Coach”, “Tech Lead”, “UX Lead” hoặc “Delivery Manager” không tự tạo accountabilities chính thức mới trong Scrum.

### 9.2. Bảng trách nhiệm phát triển năng lực

| Vai trò/góc nhìn | Đóng góp điển hình | Không nên biến thành |
|---|---|---|
| **Product Owner** | Làm rõ Product Goal, giá trị, thứ tự backlog; tạo điều kiện nghe người dùng | Người duyệt mọi dòng code hoặc chỉ viết ticket |
| **Developers** | Thiết kế, kiểm chứng, tích hợp và tạo Increment đạt DoD; hợp tác để hiểu nghiệp vụ | Nhóm chỉ nhận task và bàn giao cho QA |
| **Scrum Master** | Hỗ trợ empiricism, hiệu quả Scrum, cải tiến cộng tác và tháo trở ngại trong phạm vi | Người điều khiển Daily Scrum để thu báo cáo từng cá nhân |
| **Tester/quality specialist** | Tư duy rủi ro, chiến lược kiểm chứng, phát hiện khoảng trống evidence | Người duy nhất chịu trách nhiệm chất lượng cuối Sprint |
| **UX/research/analytics** | Giúp hiểu bối cảnh, trải nghiệm, dữ liệu outcome | Bộ phận chỉ trang trí sau khi yêu cầu đã cố định |
| **Platform/operations/security** | Điều kiện kỹ thuật, service contracts, vận hành và guardrails | Điểm nghẽn phê duyệt mọi việc thường ngày |
| **Lãnh đạo tổ chức** | Mục tiêu, quyền ra quyết định, môi trường, tài nguyên, giới hạn rủi ro và cách đánh giá | Người áp KPI velocity/test count để “buộc Agile” |
| **Coach/mentor** | Hỗ trợ thực hành, phản tư, chuyển giao năng lực và giảm phụ thuộc | Người quyết định thay Product Owner hoặc làm công việc thay đội |

Vai trò bên ngoài Scrum Team có thể hỗ trợ theo bối cảnh. Nếu sử dụng Scrum, sự tham gia của họ phải **tăng khả năng tự quản và phối hợp**, không biến Scrum thành cấu trúc phê duyệt theo cấp bậc mới.

### 9.3. Điều kiện lãnh đạo phải tạo

Đào tạo thường không có tác dụng nếu đội:

- Không được tiếp cận người dùng hoặc phản hồi hỗ trợ.
- Không có quyền thay đổi test pipeline và cách tích hợp trong phạm vi hợp lý.
- Được thưởng theo số story points, số ticket, số test hoặc phần trăm sử dụng hết thời gian.
- Bị yêu cầu giữ nguyên mọi chi tiết kế hoạch bất kể bằng chứng mới.
- Có một nhóm chuyên môn dùng chung nhưng không có thỏa thuận hỗ trợ.
- Không thể báo lỗi production hoặc rủi ro bảo mật mà không lo bị trừng phạt.
- Không có thời gian củng cố code/data contract sau các thay đổi gấp.

Lãnh đạo cần tháo **trở ngại cấu trúc** để kỹ năng được dùng. Không thể chỉ yêu cầu đội “chủ động hơn” khi mọi quyết định quan trọng vẫn phải xin nhiều cấp.

### 9.4. Quyền hạn rõ giúp người học dám thực hành

Ví dụ một Developer học refactoring nhưng không rõ có được sửa module dùng chung hay không. Cần:

- Code ownership/review policy.
- Phạm vi thay đổi và tiêu chuẩn test.
- Hợp đồng API/DB và người tham gia khi thay.
- Cách xử lý khi thay đổi vượt quá quyền của đội.

Khi có guardrails và decision rights rõ, người học có thể thử **một thay đổi nhỏ có kiểm chứng**, thay vì hoặc không dám sửa gì hoặc sửa quá phạm vi gây sự cố.

### 9.5. Không áp Scrum cứng lên mọi tổ chức như điều kiện duy nhất

Một nhóm xử lý incident hoặc dịch vụ có công việc đến liên tục có thể ưu tiên trực quan hóa và kiểm soát WIP bằng Kanban. Một nhóm phát triển sản phẩm có thể dùng Scrum với Sprint Goal/Product Goal rõ. Các thực hành kỹ thuật XP như TDD/CI có thể hỗ trợ cả hai.

Chọn cách phối hợp cần xem:

- Bản chất nhu cầu và độ biến động của công việc.
- Rủi ro chất lượng và tốc độ feedback cần có.
- Khả năng sở hữu sản phẩm và quyền ưu tiên.
- Phụ thuộc, năng lực đội và môi trường kỹ thuật.
- Cơ chế nhìn kết quả và cải tiến.

Phát triển kỹ năng song song **không đồng nghĩa áp đồng loạt mọi framework lên mọi đội**.

## 10. Đo tiến triển phát triển kỹ năng mà không tạo KPI sai

Khi tổ chức đầu tư đào tạo, người quản lý thường muốn biết “khóa học có hiệu quả không?”. Một câu trả lời chỉ dựa trên **số giờ học, số chứng chỉ hoặc điểm bài kiểm tra** dễ nhầm năng lực với hoạt động.

Cần tách:

1. **Đầu vào/hoạt động:** có bao nhiêu thời gian và cơ hội học.
2. **Thay đổi hành vi:** người học có làm việc khác đi không.
3. **Năng lực hệ thống:** nhóm có thể lặp lại cách làm tốt, ít điểm nghẽn hơn không.
4. **Kết quả sản phẩm:** người dùng nhận giá trị và chất lượng tốt hơn trong điều kiện đo được không.

### 10.1. Một quality-and-capability scorecard cân bằng

| Góc nhìn | Tín hiệu ví dụ | Dùng để làm gì | Nguy cơ nếu dùng sai |
|---|---|---|---|
| **Cộng tác** | Thời gian chờ quyết định, số blocker lâu ngày có owner, PBI bị chuyển lại nhiều lần | Tìm điểm nghẽn thông tin/quyền | Ép mọi người đóng blocker trên công cụ dù chưa xử lý thật |
| **Sản phẩm** | Số giả thuyết có bằng chứng, tỷ lệ hành trình người học hoàn tất, phản hồi hỗ trợ | Xem có đang học về giá trị không | Đếm số buổi phỏng vấn thay vì chất lượng insight |
| **Kỹ thuật** | CI feedback time, độ tin cậy test, lỗi hồi quy nghiêm trọng, khả năng release có kiểm soát | Xem thay đổi có được bảo vệ sớm không | Xóa test để pipeline nhanh hoặc che sự cố để số đẹp |
| **Dòng công việc** | WIP, throughput, work item age, cycle time, SLE | Xem luồng tới Done và công việc bị kẹt | Đếm task thay PBI hoặc bỏ item blocked |
| **Năng lực học** | Người thứ hai thực hiện được việc sau pairing, số quyết định sửa theo retrospective | Biết kiến thức có lan tỏa không | Biến skill matrix thành bảng xếp hạng cá nhân |
| **Outcome người dùng** | Tỷ lệ vào bài đầu, độ rõ trạng thái, lỗi phân quyền theo ảnh hưởng | Kiểm tra giá trị cuối cùng | Chọn mẫu/denominator làm đẹp conversion |

Không cần theo dõi mọi chỉ số. **Chọn một số tín hiệu chính theo vấn đề** và giữ guardrails về dữ liệu, chất lượng, an toàn, sức khỏe đội.

### 10.2. Metric contract trước khi so sánh

Ví dụ đội đo tỷ lệ học viên vào bài đầu:

\[
\text{Tỷ lệ vào bài đầu}
=\frac{\text{Số lượt đủ điều kiện vào bài trong cửa sổ T}}
{\text{Số lượt đăng ký đủ điều kiện trong cùng cohort}}
\times 100\%
\]

Phải định nghĩa:

- Đơn vị là **học viên**, **đơn hàng** hay **lượt ghi danh**?
- “Đủ điều kiện” theo chính sách nào?
- Cửa sổ T tính từ lúc ghi danh, xác nhận hay cấp quyền?
- Có tính người dùng chưa đủ thời gian quan sát không?
- Các khóa miễn phí/trả phí có cùng loại hành trình?
- Sự kiện có bị đếm lặp hoặc thiếu khi chuyển thiết bị không?
- Có thay đổi định nghĩa giữa các giai đoạn không?

Nếu định nghĩa/nguồn đổi, **đừng so tỷ lệ như cùng một phép đo**. Bài học về chất lượng dữ liệu đặc biệt quan trọng với chuyển đổi Agile, vì tổ chức thường vừa đổi công cụ, workflow và cách ghi nhận item.

### 10.3. Flow metrics không đo trực tiếp con người làm việc chăm chỉ thế nào

The Kanban Guide dùng bốn flow metrics tối thiểu:

- **WIP:** số work items đã bắt đầu nhưng chưa hoàn tất.
- **Throughput:** số work items đã hoàn tất trong một khoảng thời gian.
- **Work Item Age:** thời gian trôi qua từ khi bắt đầu đối với item chưa Done.
- **Cycle Time:** thời gian từ khi bắt đầu tới lúc hoàn tất của item đã Done.

**Service Level Expectation (SLE)** là kỳ vọng về thời gian flow, có **thời lượng và xác suất**. Dữ liệu cần cùng ranh giới workflow, loại item và chính sách Done.

Một tình huống minh họa:

~~~text
Sprint A:
  15 tasks theo UI/API/QA moi tasks duoc tinh Done
  3 PBI thuc su dat Definition of Done
  5 PBI con cho tich hop

Sprint B:
  11 tasks hoan tat
  5 PBI thuc su dat Definition of Done
  2 PBI con cho tich hop
~~~

Nếu chỉ đếm task, Sprint A “đẹp” hơn. Nếu mục tiêu là tạo Increment có thể dùng, Sprint B có thể đáng chú ý hơn; vẫn cần xem **loại/độ phức tạp PBI, chất lượng và outcome** trước khi kết luận.

### 10.4. Tránh metric gaming

| KPI đặt sai | Hành vi bị khuyến khích | Lựa chọn tốt hơn |
|---|---|---|
| Mỗi Developer phải viết 50 tests/Sprint | Tạo test trùng hoặc assertion yếu | Kiểm chứng những rủi ro quan trọng, test suite tin cậy |
| Velocity mỗi Sprint phải tăng | Ước lượng inflated, chia item không có giá trị | Sử dụng velocity nội bộ để dự báo khi hợp lý; xem DoD/outcome |
| Không được có bug production | Che hoặc phân loại lại bug | Báo trung thực severity, tác động, thời gian phát hiện và cải tiến |
| 100% thời gian nhân viên phải gán ticket | Không còn thời gian học, xử lý phụ thuộc, refactor | Xem flow bền vững, WIP và kết quả |
| Số buổi phỏng vấn người dùng tăng liên tục | Phỏng vấn cho đủ chỉ tiêu | Insight nào thay quyết định, cohort và outcome |
| Số chứng chỉ Agile tăng | Học để thi, không có điều kiện ứng dụng | Quan sát năng lực được dùng trên PBI thật |

Đừng dùng **một điểm Agile maturity tổng hợp** để tuyên bố “chuyển đổi đã đạt 82%” nếu không có mô hình đáng tin. Một lỗ hổng bảo mật nghiêm trọng không thể được bù bởi điểm cao về số cuộc họp.

### 10.5. DORA và ranh giới suy luận

Các nghiên cứu/thực hành DORA về **năng lực giao phần mềm** cung cấp góc nhìn bổ sung với flow và reliability, nhưng số đo kỹ thuật không tự chứng minh sản phẩm có giá trị.

Nếu theo dõi những chỉ số về thời gian đưa thay đổi vào vận hành, tần suất triển khai, tỷ lệ lỗi thay đổi hoặc khả năng phục hồi, đội cần dùng **định nghĩa chính xác cho từng phiên bản chỉ số**, không so số từ hai công cụ với mẫu số khác nhau. Không thể suy từ một chỉ số rằng một Developer hoặc team “giỏi hơn”.

**Mục đích là quyết định đầu tư:** liệu điều kiện kỹ thuật có giúp nhận phản hồi sản phẩm sớm hơn mà vẫn giữ độ tin cậy?

### 10.6. Đo hiệu ứng đào tạo theo giả thuyết, không ép quan hệ nhân quả

Giả sử sau khi nhóm học pairing và CI, median cycle time giảm. Cùng kỳ đó, họ nhận ít PBI tích hợp đối tác hơn và một chuyên gia platform giải quyết môi trường test.

**Kết luận hỗ trợ được:**

> “Trong giai đoạn thử nghiệm, nhóm thực hành pairing/CI và quan sát một số chỉ số flow cải thiện; các thay đổi về loại công việc và môi trường có thể cũng đóng góp. Cần theo dõi thêm và phân nhóm để hiểu tác dụng.”

**Kết luận vượt bằng chứng:**

> “Khóa học pairing đã làm năng suất tăng đúng 35%.”

Không phải mọi cải tiến cần thử nghiệm ngẫu nhiên, nhưng **diễn giải trung thực về biến động và yếu tố thay đổi đồng thời** giúp tổ chức không nhân rộng sai.

## 11. Lộ trình 12 tuần phát triển ba năng lực song song

Một lộ trình minh họa cho một đội sản phẩm nhỏ hoặc một cụm nhóm phụ thuộc. **12 tuần không phải thời hạn chuẩn** để “chuyển đổi Agile thành công”. Đây là khoảng thử nghiệm đủ để lập đường cơ sở, thực hành trên PBI và xem nhiều vòng phản hồi. Kết quả tùy trạng thái kỹ thuật, product boundary, nhân lực, pháp lý và mức bất định.

### 11.1. Các nguyên tắc thiết kế lộ trình

1. **Chọn một vấn đề sản phẩm thật** có phản hồi và rủi ro có thể quan sát.
2. **Bắt đầu nhỏ** để không thay toàn bộ tổ chức trước khi biết điều kiện.
3. **Mỗi tuần chạm cả ba trụ cột**, dù mức đầu tư không cân bằng.
4. **Giữ DoD và guardrails** khi kỹ năng còn chưa ổn định.
5. **Làm trên Increment thật** thay vì chỉ học lý thuyết.
6. **Giữ mục tiêu và quyền quyết định rõ**, đặc biệt Product Owner/Developers khi dùng Scrum.
7. **Ghi bằng chứng và các giả định**, không bắt buộc một dashboard lớn.
8. **Cập nhật kế hoạch theo phản hồi**, không cố thực hiện mọi bài tập nếu sản phẩm thay đổi.

### 11.2. Kế hoạch theo ba giai đoạn và một đợt tổng kết

| Giai đoạn | Cộng tác | Sản phẩm | Kỹ thuật | Bằng chứng kỳ vọng |
|---|---|---|---|---|
| **Tuần 1–2: Hiểu hiện trạng** | Quan sát blocker, quyền quyết định, retro; làm rõ nguyên tắc phản hồi | Phỏng vấn/quan sát chọn lọc, Product Goal và hành trình | Kiểm tra DoD, CI, môi trường, vùng thiếu test | Baseline có định nghĩa, một vấn đề ưu tiên và guardrails |
| **Tuần 3–5: Thực hành lát cắt nhỏ** | Three Amigos, pairing, feedback ngắn | Viết AC, chia PBI dọc, thử giả thuyết | TDD phù hợp, integration/contract tests, CI | Ít nhất một lát cắt đạt DoD với evidence |
| **Tuần 6–9: Lan tỏa và xử lý nút thắt** | Luân phiên pairing, giải quyết quyền/phụ thuộc | Cập nhật backlog theo feedback; đo outcome | Ổn định test data, refactor, observability | Một người/nhóm khác làm được kỹ năng quan trọng; giảm blocker nếu có bằng chứng |
| **Tuần 10–12: Đánh giá và thích ứng** | Retrospective xuyên chuyên môn, đưa ra quyết định kế tiếp | Xem Product Goal, dữ liệu người dùng và giả thuyết | Đánh giá rủi ro còn mở, chất lượng Increment và khả năng giao | Báo cáo điều đã học, giới hạn, kế hoạch tiếp theo |

Đây là **mẫu nhịp học**. Nếu đội đang có sự cố bảo mật chưa được kiểm soát, ưu tiên xử lý sự cố và guardrails trước; không chạy workshop chỉ để giữ lịch. Nếu đội chưa có Product Owner thực quyền, phải làm rõ điều kiện tổ chức sớm thay vì kỳ vọng các kỹ thuật test tự giải quyết ưu tiên.

### 11.3. Tuần 1–2: xây đường cơ sở đáng tin

Chọn **một dòng giá trị**, ví dụ ghi danh khóa trả phí:

- **Cộng tác:** vẽ ai quyết định thứ tự, ai cung cấp contract, PBI thường chờ ai.
- **Sản phẩm:** xem ticket hỗ trợ, phỏng vấn người học phù hợp, xác định một outcome và hai guardrails.
- **Kỹ thuật:** chạy build CI hiện tại, điều tra test đỏ, vẽ các điểm tích hợp và cách Done.
- **Flow:** định nghĩa Started/Done, ghi những item blocked và tuổi item; không nối dữ liệu khác nghĩa.

**Deliverables có ích:** Product Goal hoặc mục tiêu giá trị, một bản đồ phụ thuộc, bảng rủi ro, đường cơ sở kỹ thuật có thể tin. Không cần tạo một báo cáo chuyển đổi hàng trăm trang.

### 11.4. Tuần 3–5: luyện trên một lát cắt có giá trị

Ví dụ PBI “hiển thị trạng thái PENDING đáng tin”.

1. Product Owner và Developers cùng kiểm tra điều người dùng thực sự cần biết.
2. Người có chuyên môn test cùng làm rõ trường hợp PENDING, CONFIRMED, FAILED, timeout.
3. Developers chia phần việc thành một lát cắt có thể tích hợp.
4. Pairing làm một integration test cho trạng thái.
5. CI phát hiện thay đổi phá consumer; team sửa.
6. Increment đáp ứng DoD được review với stakeholders phù hợp.
7. Dữ liệu và phản hồi giúp Product Owner chọn bước tiếp.

Với người mới học TDD hoặc contract test, cần thời gian mentoring. **Không tuyên bố thất bại chuyển đổi** nếu lần đầu một PBI nhỏ mất nhiều công sức hơn trước; hãy xem liệu khả năng lặp lại và chất lượng có dần cải thiện.

### 11.5. Tuần 6–9: lan tỏa thay vì tạo một chuyên gia đơn độc

Giả sử sau vài tuần chỉ một Developer viết được integration tests. Đội có thể:

- Ghép cặp người có kinh nghiệm với người mới trên một test đang có tác dụng thật.
- Chọn test fixture và ví dụ chuẩn được review.
- Để người mới thực hiện lần tiếp theo với hỗ trợ.
- Ghi điều gì khó và cải thiện môi trường.
- Đánh giá không chỉ “đã học xong”, mà **có giảm chờ một người hoặc test fail muộn không**.

Song song, Product Owner có thể phối hợp người hỗ trợ học viên để cải thiện hiểu vấn đề; Scrum Master/facilitator giúp đội thực hành phản hồi trong retrospective. Ba hướng học **gắn với cùng dòng giá trị**.

### 11.6. Tuần 10–12: đánh giá đúng điều đã thay đổi

Một báo cáo có thể trả lời:

| Câu hỏi | Bằng chứng cần xem |
|---|---|
| Đội có hiểu người học tốt hơn? | Insight dẫn tới đổi lựa chọn Product Backlog; quan sát task |
| Đội có quyết định và phối hợp nhanh hơn? | Blocker thật, thời gian chờ quyết định, ít vòng bàn giao không cần |
| Đội có tạo Increment an toàn thường xuyên hơn? | DoD, CI reliability, test integration, lỗi hồi quy |
| Flow có cải thiện? | WIP/throughput/age/cycle time cùng định nghĩa, phân nhóm work mix |
| Người học có đạt kết quả hơn không? | Completion, độ rõ trạng thái, sự cố theo cửa sổ và cohort |
| Có hình thành năng lực tập thể? | Người khác áp dụng được kỹ năng, phụ thuộc kiến thức giảm |
| Rủi ro nào còn mở? | Security, dữ liệu, đối tác, quan hệ nhóm, điều kiện tổ chức |

Nếu outcome chưa có tín hiệu vì người dùng chưa đủ thời gian sử dụng, ghi **“chưa đủ dữ liệu”**, không biến số giờ học hoặc số PBI thành bằng chứng giả.

### 11.7. Một kế hoạch tuần minh họa chi tiết

| Tuần | Thực hành chung trên công việc thật | Một kết quả học mong đợi |
|---|---|---|
| 1 | Quan sát một hành trình và các hàng chờ | Biết vấn đề người dùng và flow hiện tại |
| 2 | Thống nhất mục tiêu, DoD, quyền và baseline | Biết mục tiêu/guardrails và dữ liệu có thể tin |
| 3 | Three Amigos trên PBI đầu | Làm rõ trạng thái lỗi trước khi code |
| 4 | Pairing TDD/API test, tích hợp sớm | Test có thể phát hiện sai lệch quy tắc |
| 5 | Review Increment thật với người liên quan | Nhận phản hồi và ưu tiên bước tiếp |
| 6 | Xử lý một test flaky và test data | CI bớt nhiễu, evidence đáng tin hơn |
| 7 | Gỡ một dependency xuyên nhóm | Hiểu quyết định/contract cần thiết |
| 8 | Product discovery trên giả thuyết tiếp | Biết yêu cầu mới có thực sự cần không |
| 9 | Refactoring và migration nhỏ có test | Tăng khả năng thay đổi không phá consumer |
| 10 | Retrospective có phân tích flow/quality | Một cải tiến dựa trên bằng chứng |
| 11 | Chia sẻ lại kỹ năng qua pairing luân phiên | Bớt phụ thuộc một người |
| 12 | Đánh giá outcome và quyết định vòng tới | Có kế hoạch thực nghiệm tiếp theo |

Không biến bảng thành **lịch cứng bất kể sự cố và feedback**. Điểm cốt lõi là mỗi chu kỳ có cơ hội luyện cả cộng tác, sản phẩm và kỹ thuật.

## 12. Tình huống xuyên suốt: chuyển đổi Agile trên luồng ghi danh khóa học

> **Toàn bộ con số và diễn biến trong phần này là giả định để học phương pháp**, không phải dữ liệu từ một công ty cụ thể hoặc tiêu chuẩn hiệu quả Agile.

Một tổ chức có ba nhóm phát triển:

- **Team Enrollment UI:** chịu trách nhiệm giao diện đăng ký và trạng thái đơn.
- **Team Core Services:** chịu trách nhiệm thanh toán, entitlement và dữ liệu.
- **Team QA/Release:** nhận phần tích hợp cuối, chạy bộ kiểm thử và deploy.

Tổ chức dùng Sprint hai tuần nhưng mỗi nhóm có backlog riêng. Một Product Owner được bổ nhiệm nhưng không có quyền thứ tự chung; nhiều bộ phận giao task trực tiếp vào Sprint. Các Developers chủ yếu viết unit tests trên mock, trong khi integration tests chỉ chạy khi QA nhận đủ code.

### 12.1. Mục tiêu tưởng như đã rõ

Lãnh đạo yêu cầu “tăng tốc giao tính năng đăng ký khóa học trong quý tới” và đo:

~~~text
So buoi Daily Scrum: 100% theo lich
So nguoi co chung chi Agile: 18
So story points: tang 25%
So test tu dong: tang 500
~~~

Những số này có thể đúng, nhưng chúng chưa trả lời: **học viên có thể ghi danh hợp lệ và vào bài đầu đáng tin hơn không?** Nếu không có mục tiêu kết quả và cách kiểm chứng, tổ chức có thể khen một chuyển đổi chỉ tồn tại ở nghi thức.

### 12.2. Đường cơ sở giả định và những câu hỏi cần làm rõ

| Tín hiệu giả định | Hiện trạng sơ bộ | Cần kiểm tra trước khi kết luận |
|---|---|---|
| PBI mất nhiều thời gian chờ QA | 8–15 ngày lịch với một số item | Start/Done, loại việc, item chưa hoàn tất và độ trễ thực |
| Tỷ lệ học viên đủ điều kiện vào bài đầu trong 24 giờ | 82% | Cohort và mẫu số, event tracking, đơn miễn phí/trả phí |
| Sự cố cấp quyền trong hai đợt phát hành | 3 sự cố được ghi nhận | Severity, người dùng ảnh hưởng, khả năng phát hiện và cửa sổ |
| Integration tests thường bị tắt khi fail | Một số test quarantine | Test nào, rủi ro nào không được kiểm chứng |
| Cuộc họp refinement ít trường hợp lỗi | Thảo luận chủ yếu happy path | Sai yêu cầu và vòng hỏi lại đã gây chi phí ra sao |
| Quyền ưu tiên của PO | Có chức danh, nhưng marketing và quản lý chức năng có thể chèn việc | Cần làm rõ decision rights và Product Backlog |

Nhóm không coi những con số là bản án cho cá nhân hoặc cho toàn bộ tổ chức; chúng là **đầu mối điều tra nguyên nhân hệ thống**.

### 12.3. Phân tích ba trụ cột

**Cộng tác**

- Team UI và Core Services chỉ trao đổi qua ticket.
- Khi có lỗi trạng thái, hai bên hiểu khác nhau về PENDING.
- Tester không tham gia thảo luận điều kiện chấp nhận ban đầu.
- Những người có quyền ưu tiên đưa chỉ đạo mâu thuẫn.

**Sản phẩm**

- Không có Product Goal rõ cho hành trình ghi danh.
- User story thường là “thêm nút”, “thêm API”, không nêu kết quả.
- Không có dữ liệu đủ tin để phân biệt người dùng bỏ dở vì UX hay quyền.
- Product Owner không thể sắp thứ tự backlog hiệu quả.

**Kỹ thuật**

- CI chạy unit tests nhưng không kiểm tra API contract và dữ liệu thật phù hợp.
- Callback đối tác có thể lặp; test thiếu điều kiện đồng thời.
- Hành trình đầu-cuối được kiểm tra cuối kỳ.
- Test environment dùng chung gây chờ và dữ liệu test không ổn định.

**Kết luận chẩn đoán:** thiếu năng lực phối hợp, hiểu sản phẩm và kỹ thuật cùng lúc. Không thể sửa bằng một khóa coaching giao tiếp duy nhất, cũng không thể sửa chỉ bằng thêm E2E tests.

### 12.4. Một mục tiêu và một lát cắt để học

Nhóm làm rõ Product Goal minh họa:

> **“Học viên đủ điều kiện tự hoàn tất ghi danh, nhận đúng quyền và vào bài đầu trong những trường hợp được hỗ trợ, với thông tin trạng thái rõ ràng và không cần can thiệp thủ công thường xuyên.”**

Để tránh làm quá nhiều, họ chọn PBI đầu tiên:

> **“Học viên thấy trạng thái đơn đang xử lý đáng tin và bước tiếp theo, không bị cấp quyền trước xác nhận giao dịch hợp lệ.”**

Đây là **một lát cắt cần được kiểm chứng đầy đủ**. Team không hứa rằng một màn hình trạng thái sẽ giải quyết mọi sự cố thanh toán.

### 12.5. Một vòng phát triển đồng thời

<table>
<tr><th>Giai đoạn</th><th>Cộng tác</th><th>Sản phẩm</th><th>Kỹ thuật</th></tr>
<tr><td>Làm rõ</td><td>PO, Developers, tester, UX trao đổi ví dụ và quyền quyết định</td><td>Kiểm tra nhu cầu của học viên đang chờ</td><td>Phân tích trạng thái từ nguồn tin cậy và API</td></tr>
<tr><td>Chọn lát cắt</td><td>Thống nhất owner và phụ thuộc</td><td>AC cho PENDING, FAILED, CONFIRMED, timeout</td><td>Chọn unit/API/integration checks theo rủi ro</td></tr>
<tr><td>Thực hiện</td><td>Pair Developers hai vùng và test specialist</td><td>Xác nhận lại ngữ nghĩa nghiệp vụ khi phát hiện ngoại lệ</td><td>CI, contract tests, xử lý idempotency nếu liên quan</td></tr>
<tr><td>Kiểm chứng</td><td>Chia sẻ evidence và rủi ro còn mở</td><td>Đối chiếu AC, quyết định phạm vi</td><td>Increment tích hợp đáp ứng DoD</td></tr>
<tr><td>Học</td><td>Retrospective không đổ lỗi, chọn cải tiến</td><td>Quan sát học viên và thay ưu tiên</td><td>Điều tra sự cố, flaky tests, telemetry</td></tr>
</table>

Không có chuỗi “QA nhận việc chỉ khi Developers Done”. Người có chuyên môn test có thể tham gia làm rõ sớm; Developers vẫn chịu trách nhiệm tạo Increment có chất lượng theo DoD khi đội dùng Scrum.

### 12.6. Luyện kỹ năng ở một blocker thật

Đến giữa Sprint, contract quyền học thay đổi: API mới trả trạng thái PENDING_AUTHORIZATION nhưng UI chưa hiểu. Trước đây team UI mở ticket cho backend rồi đợi.

Đội thử:

1. **Cộng tác:** một cuộc trao đổi ngắn với đúng người có quyền/ngữ nghĩa, không họp toàn tổ chức.
2. **Sản phẩm:** Product Owner cùng Developers xác nhận người học phải thấy gì khi quyền chưa sẵn sàng.
3. **Kỹ thuật:** dùng contract test tái hiện, cập nhật mapping an toàn, tích hợp sớm.
4. **Quan sát:** ghi item blocked bao lâu, test fail ở đâu, người dùng nhận được hành vi nào.

Sau hai PBI, một Developer UI có thể tự phát hiện loại lỗi contract cơ bản trước khi gửi code, trong khi chuyên gia backend vẫn hỗ trợ thay đổi thiết kế phức tạp. Đây là **bằng chứng nhỏ về lan tỏa năng lực**, tốt hơn chỉ ghi “đã học API integration”.

### 12.7. Retrospective chuyển từ đổ lỗi sang thử nghiệm

**Cách cũ:**

> “Frontend cần giao tiếp tốt hơn, backend cần test nhiều hơn, QA cần nhanh hơn.”

**Cách mới:**

> “Ba PBI liên tiếp bị chặn ở cùng trạng thái quyền. Chúng ta giả thuyết API contract không rõ và thiếu test chung là nguyên nhân quan trọng. Trong hai Sprint tới, trên các PBI entitlement, chúng ta làm rõ ví dụ PENDING/CONFIRMED trong refinement và kiểm tra provider–consumer contract trong CI. Quan sát thời điểm phát hiện mismatch, work item age và lỗi người dùng; nếu vấn đề không giảm, xem lại giả thuyết.”

Thử nghiệm này đồng thời luyện:

- Diễn đạt bất đồng dựa trên bằng chứng.
- Làm rõ quy tắc và người dùng.
- Xây test/CI có tác dụng thật.
- Đánh giá kết quả và điều chỉnh.

### 12.8. Tình huống số liệu sau hai tháng

Giả sử bảng kiểm tra sau thời gian thử có:

| Tín hiệu giả định | Trước | Sau | Diễn giải cần thận trọng |
|---|---:|---:|---|
| Tỷ lệ vào bài đầu trong cohort đủ điều kiện | 82% | 89% | Chỉ so nếu cùng định nghĩa và cửa sổ |
| Lỗi cấp quyền nghiêm trọng ghi nhận trong các release được xét | 3 | 1 | Khối lượng sử dụng, severity, khả năng phát hiện có thể khác |
| Median cycle time của PBI thuộc luồng này | 10 ngày | 7 ngày | Work mix/DoD và item đang mở phải so được |
| PBI bị chuyển qua lại do AC mơ hồ trong mẫu đã xét | 7 | 3 | Định nghĩa “chuyển lại” có nhất quán? |
| Số người có thể chạy/chẩn đoán contract test cơ bản với hỗ trợ phù hợp | 1 | 3 | Là năng lực nhóm ở phạm vi xác định, không phải “chứng chỉ” |
| Số test tự động | 800 | 840 | Số lượng không chứng minh mức bảo vệ rủi ro |

Không được tuyên bố **“chuyển đổi làm tỷ lệ người học tăng chính xác 7 điểm phần trăm”** chỉ từ bảng. Tổ chức có thể đồng thời thay UX, đối tác thanh toán, marketing và cơ chế tracking. Cách nói chính xác hơn:

> “Nhóm đã thử phối hợp product–engineering trên một luồng quan trọng; một số tín hiệu sản phẩm, chất lượng và flow có chiều hướng tốt hơn, đồng thời năng lực contract test bớt phụ thuộc một người. Cần xác minh điều kiện so sánh và theo dõi đủ thời gian trước khi nhân rộng.”

### 12.9. Phát hành từng phần và học từ dữ liệu thực

Sau khi lát cắt đạt DoD và đáp ứng điều kiện phát hành, Product Owner và các bên có thẩm quyền có thể quyết định **phạm vi cung cấp** phù hợp, ví dụ giới hạn nhóm người dùng có kiểm soát và đủ quan sát.

Đội cần:

- Theo dõi tỷ lệ thành công đúng định nghĩa, lỗi và latency liên quan.
- Giữ cách giảm ảnh hưởng nếu xảy ra sự cố.
- Không dùng người dùng thật để thử lỗi phân quyền chưa kiểm soát.
- Nhận phản hồi từ hỗ trợ và người học bị lỗi, không chỉ những người hoàn tất thành công.
- Cập nhật Product Backlog theo giá trị, rủi ro và bằng chứng.

Như vậy chuyển đổi có **vòng học thật**, thay vì chỉ một báo cáo “đã tổ chức 24 Daily Scrum”.

### 12.10. Quyết định mở rộng hay chưa

Đội có thể mở rộng thực hành nếu:

1. Có thể giải thích **cơ chế cụ thể** làm tốt hơn, không chỉ con số.
2. Những điều kiện tổ chức khác có thể hỗ trợ, đặc biệt quyền Product Owner và CI.
3. Các nhóm mới có người hỗ trợ học trên công việc thật.
4. Không chuyển nguyên một quy trình thành thủ tục cứng nếu nhóm có loại việc khác.
5. Có chỉ số outcome, chất lượng, flow và giới hạn đánh giá sau mở rộng.

Nếu nhóm thí điểm thành công vì có một chuyên gia đặc biệt được dành riêng toàn thời gian, cần xem **liệu nguồn lực đó có thể nhân rộng** hay phải thiết kế phương án mentoring/platform khác.

## 13. Những trở ngại hệ thống và cách tránh biến đào tạo thành hình thức

Không thể chỉ hỏi “ai cần đi học gì?”. Đội cần xem **những điều kiện nào khiến kỹ năng không được dùng**.

### 13.1. Bảng trở ngại và can thiệp

| Trở ngại | Biểu hiện | Can thiệp cân bằng ba trụ cột |
|---|---|---|
| **Product Owner thiếu quyền** | Stakeholders giao trực tiếp task, ưu tiên thay liên tục | Làm rõ accountability và quyền ưu tiên, xây Product Goal, tạo không gian quyết định |
| **Lãnh đạo chỉ thưởng output** | Velocity/test count tăng dù lỗi và outcome không tốt | Dùng metric contract, outcome và quality guardrails; đánh giá hệ thống |
| **Các nhóm chia theo tầng** | UI–API–DB–QA bàn giao tuần tự | Thử vertical slicing, pairing, contract tests và trách nhiệm end-to-end |
| **CI chậm hoặc flaky** | Developers không tin kết quả, chờ QA cuối Sprint | Đầu tư test data/fixtures, CI reliability và phản hồi nhanh |
| **Không được tiếp cận người dùng** | Ưu tiên theo giả định và stakeholder nội bộ | Tạo kênh feedback, nghiên cứu phù hợp và analytics có bảo vệ dữ liệu |
| **Specialist là nút thắt** | Mọi thay đổi phải chờ một người | Pairing, tài liệu hợp đồng, chuyển giao kỹ năng, self-service khi an toàn |
| **Nợ kỹ thuật tăng** | Sửa một trạng thái phá nhiều phần | Refactoring có test, ranh giới module, làm thay đổi nhỏ |
| **Sợ báo lỗi** | Rủi ro bị giấu, retrospective đổ lỗi | Tâm lý an toàn, incident learning, trách nhiệm rõ và guardrails |
| **Không có thời gian thực hành** | Khóa học xong nhưng backlog luôn quá đầy | WIP hợp lý, ưu tiên một thử nghiệm nhỏ và đưa học vào PBI thật |
| **Quá nhiều sáng kiến đồng thời** | Mọi tuần đổi quy trình, không đo được tác dụng | Chọn dòng giá trị và giả thuyết, giới hạn WIP cải tiến |

### 13.2. Đừng nhầm sức cản với “con người không chịu Agile”

Một người có thể dè dặt với pairing vì mọi thay đổi ở môi trường đang rất rủi ro; một Product Owner có thể khó tham gia discovery vì không được phép nói chuyện với người học; một tester có thể muốn giữ gate kiểm thử vì hệ thống chưa có automated evidence đáng tin.

Thay vì dán nhãn “chống thay đổi”, cần hỏi:

- Người đó đang bảo vệ rủi ro hoặc trách nhiệm gì?
- Điều kiện nào khiến thực hành mới không an toàn hoặc không khả thi?
- Có cách thử phạm vi nhỏ với guardrails nào?
- Ai có quyền tháo trở ngại?

Điều này không có nghĩa mọi phản đối đều đúng. Nó nghĩa là **phản đối là thông tin cần kiểm tra**, không phải lý do mặc định để đào tạo lại hoặc gây áp lực.

### 13.3. Đừng bắt người mới lập tức đạt sản lượng của người có kinh nghiệm

Pairing hoặc viết test kỹ lưỡng ban đầu có thể giảm số PBI hoàn tất trong Sprint đầu. Nếu tổ chức vẫn thưởng cho throughput tức thời, người mới khó có cơ hội thực hành, còn chuyên gia sẽ làm hết để “cứu tiến độ”.

Một cơ chế hợp lý:

1. Chọn một phạm vi học an toàn và có giá trị.
2. Ghi kỳ vọng năng lực ban đầu thực tế.
3. Cho người mới thực hiện dần với hỗ trợ.
4. Giữ các tiêu chuẩn chất lượng bắt buộc.
5. Xem bằng chứng sau nhiều vòng, không một ngày.

Chấp nhận **chi phí học có kiểm soát** khác với chấp nhận lỗi an toàn hoặc sản phẩm chưa Done.

### 13.4. Khi chuyên gia dạy nhưng không chuyển giao quyền

Ví dụ platform team dạy các Product Teams cách tự chạy CI, nhưng hệ thống vẫn không cấp quyền cho họ và mọi cấu hình phải chờ một người platform approve thủ công.

Đội có thể hiểu rất rõ công cụ nhưng **không thể thực hành**. Cần:

- Ranh giới quyền và quy tắc self-service.
- Template/cấu hình an toàn.
- Chuyển giao thao tác thường gặp có test/audit phù hợp.
- Đường escalation cho ngoại lệ.

Việc này là **thay đổi thiết kế hệ thống công việc**, không chỉ chuyển giao kiến thức.

### 13.5. Không có sản phẩm chung, không có cách đánh giá chung

Nếu mỗi nhóm chỉ đo thành tích phòng ban, nỗ lực cải tiến sản phẩm dễ bị chia cắt:

- Nhóm UI đo số màn hình.
- Nhóm API đo endpoint.
- Nhóm test đo test count.
- Nhóm sản phẩm đo số yêu cầu bàn giao.

Để phối hợp, cần làm rõ **Product Goal, ranh giới sản phẩm, người ưu tiên và DoD**, rồi đo Increment và outcome. Với nhiều Scrum Teams cùng một sản phẩm, theo Scrum Guide cần cùng Product Goal, Product Backlog, Product Owner và DoD; không được dùng bốn backlog cạnh tranh cho cùng product rồi mong một khóa cộng tác giải quyết.

### 13.6. Thay đổi hệ thống không có nghĩa tái tổ chức ngay lập tức

Trước khi chuyển toàn bộ Developers giữa các phòng ban, thử:

- Một PBI lát cắt dọc với cộng tác trực tiếp.
- Contract và integration tests ở ranh giới hiện tại.
- Chính sách WIP giúp giảm hàng chờ.
- Quyền Product Owner rõ hơn và Product Backlog có thứ tự.
- Nâng CI/test environment.
- Sharing qua pairing/enabling team.

Nếu những can thiệp nhỏ cải thiện flow và chất lượng, không nhất thiết cần đổi sơ đồ tổ chức. Nếu phụ thuộc vẫn lặp ở hầu hết PBI, có thể cần **xem lại team boundaries**, cùng kế hoạch chuyển giao tri thức và vận hành.

### 13.7. Một chuyển đổi bền vững cần quyền được học từ dữ liệu trái ý

Khi experiment cho kết quả không như mong đợi, đội cần được phép nói:

> “Pairing trên mọi task đã làm tăng chi phí phối hợp mà không cải thiện chất lượng trong nhóm công việc này. Chúng ta giữ pairing cho test/contract rủi ro cao và thử review nhẹ với việc nhỏ.”

Đó không phải thất bại đạo đức của chuyển đổi. Đó là **empiricism**: quan sát, kiểm tra giả thuyết và thích ứng.

Chỉ có vấn đề khi tổ chức gọi tất cả phản hồi trái ý là “kháng cự Agile”, vì khi đó vòng học bị cắt đứt.

## 14. Scrum, Kanban và XP đóng góp gì cho việc phát triển năng lực?

Không có công thức “Scrum = sản phẩm, Kanban = cộng tác, XP = kỹ thuật”. Mỗi cách tiếp cận có phạm vi và thực hành riêng; ba trụ cột đều cần có mặt khi áp dụng vào sản phẩm.

### 14.1. So sánh theo chức năng

| Góc nhìn | Scrum | Kanban | XP |
|---|---|---|---|
| **Tập trung chính** | Scrum Team hướng tới Product Goal, giao Increment, empiricism | Định nghĩa và cải thiện dòng công việc bằng minh bạch/WIP/feedback | Kỷ luật kỹ thuật và cộng tác giúp thay đổi phần mềm an toàn |
| **Cơ chế cộng tác** | Roles/accountabilities, Scrum events, self-managing team | Policies rõ, quản lý flow, trao đổi theo rủi ro/age | Pairing, collective ownership, liên hệ khách hàng và phản hồi nhanh |
| **Góc nhìn sản phẩm** | Product Owner, Product Backlog, Product Goal, Sprint Goal | Dòng giá trị/loại việc, service outcomes, ưu tiên theo chính sách | Small releases, khách hàng, acceptance examples |
| **Chất lượng kỹ thuật** | Increment phải đạt DoD, không bắt buộc một bộ kỹ thuật chi tiết | Done policy và cải thiện chất lượng flow, không thay test strategy | TDD, CI, refactoring, simple design, collective code ownership |
| **Dữ liệu phản hồi** | Inspection/adaptation tại events và Increment | WIP, throughput, work item age, cycle time, SLE | Test feedback, CI, thay đổi nhỏ và phản hồi sản phẩm |
| **Nguy cơ khi hiểu sai** | Chỉ làm nghi thức và velocity | Chỉ vẽ bảng, giấu blocker hoặc thiếu DoD | Chỉ viết unit tests mà bỏ nghiệp vụ/tích hợp |

### 14.2. Scrum không quy định mọi kỹ thuật triển khai

Scrum Guide **không bắt buộc TDD, một ngôn ngữ lập trình, story points hay một công cụ CI cụ thể**. Nhưng Scrum yêu cầu Increment có thể sử dụng và đáp ứng DoD; đội phải chọn kỹ thuật đủ để đáp ứng điều đó.

Vì vậy một chuyển đổi Scrum thường cần **đầu tư năng lực kỹ thuật ngoài việc học Scrum Guide**. Nếu một nhóm khó đáp ứng DoD, giải pháp không chỉ là “Scrum Master tổ chức Daily đúng 15 phút”.

### 14.3. Kanban không thay Product Goal hoặc giá trị người dùng

WIP limits và flow metrics giúp thấy công việc nào đang dở, nhưng một bảng chảy nhanh vẫn có thể chuyển nhiều việc ít giá trị. Tổ chức phải kết nối **dịch vụ và work items** với người dùng, product decisions và chất lượng đầu ra.

Kanban có thể được áp dụng cùng Scrum theo hoàn cảnh; không tự xem đây là lựa chọn “Scrum hoặc Kanban” trong mọi trường hợp.

### 14.4. XP không thay nghiên cứu nhu cầu hoặc quyền quyết định

Một team giỏi TDD, pairing và CI có thể giao tính năng sai rất nhanh nếu thiếu Product Goal và đối thoại người dùng. XP khuyến khích phản hồi khách hàng, nhưng việc xây năng lực sản phẩm vẫn cần **phân tích vấn đề, quyền ưu tiên và đo outcome**.

### 14.5. Dùng ba cách tiếp cận có chủ đích

Một ví dụ hợp lý:

- **Scrum:** Product Goal, Product Backlog, Sprint Goal, Increment và DoD.
- **Kanban practices:** nhìn WIP/age, giới hạn việc bắt đầu, tháo blocked items.
- **XP practices:** pair trên logic quan trọng, TDD, CI, refactoring và small releases.

Tất cả phục vụ **một dòng giá trị**, không phải ba bộ chỉ số cạnh tranh hoặc ba lớp họp riêng.

## 15. Hai mươi phản mẫu chuyển đổi Agile khi phát triển kỹ năng lệch nhau

### 15.1. “Có chứng chỉ Scrum là đã chuyển đổi”

**Dấu hiệu:** đánh giá thành công theo phần trăm nhân sự đạt chứng chỉ nhưng Increment vẫn chưa đáp ứng DoD.

**Cơ chế sai:** nhầm kiến thức lý thuyết với năng lực dùng trong hệ thống.

**Thay thế:** tạo cơ hội thực hành trên Product Goal thật, quan sát phối hợp, Increment, quality và outcome.

### 15.2. “Cứ tổ chức mọi Scrum event là đủ”

**Dấu hiệu:** Sprint Review chỉ trình bày slide, không có phần mềm có thể sử dụng.

**Cơ chế sai:** nghi thức không tự giải quyết chất lượng tích hợp hay mục tiêu sản phẩm.

**Thay thế:** giữ đúng mục đích Scrum events, đầu tư CI/DoD và khả năng kiểm tra Increment thực.

### 15.3. “Đào tạo Product Owner nhưng không trao quyền”

**Dấu hiệu:** PO học ordering nhưng quản lý nhiều phòng vẫn có thể giao việc trực tiếp theo ưu tiên trái nhau.

**Cơ chế sai:** kỹ năng không thể dùng vì decision rights mâu thuẫn.

**Thay thế:** làm rõ quyền Product Backlog, ranh giới guardrails và đường escalation.

### 15.4. “Học giao tiếp để bù cho API contract hỏng”

**Dấu hiệu:** nhiều workshop mềm nhưng lỗi tích hợp vẫn xuất hiện cuối Sprint.

**Cơ chế sai:** vấn đề kỹ thuật/cấu trúc bị quy về thái độ.

**Thay thế:** luyện trao đổi contract trực tiếp đồng thời với test tương thích, CI và ownership.

### 15.5. “Chỉ đầu tư CI, sản phẩm sẽ tự tốt lên”

**Dấu hiệu:** pipeline nhanh nhưng người dùng vẫn bỏ dở vì tính năng không giải quyết nhu cầu.

**Cơ chế sai:** giao output nhanh hơn mà không có discovery/validation.

**Thay thế:** Product Goal, giả thuyết và outcome measurement đi cùng engineering.

### 15.6. “Mỗi người phải giỏi mọi công nghệ”

**Dấu hiệu:** bắt mọi tester, PO, Developer làm đủ frontend, database, bảo mật, vận hành ở mức chuyên sâu.

**Cơ chế sai:** đánh mất chuyên môn, cognitive load tăng và không thực tế.

**Thay thế:** cross-functional ở cấp nhóm, T-shaped learning và hỗ trợ chuyên gia.

### 15.7. “Skill matrix dùng để công bố ai yếu”

**Dấu hiệu:** tự chấm điểm cao để tránh bị phạt, không ai muốn nêu giới hạn.

**Cơ chế sai:** phá tâm lý an toàn và chất lượng dữ liệu năng lực.

**Thay thế:** đánh giá khoảng trống tập thể gắn nhu cầu Product Goal, tạo kế hoạch học có hỗ trợ.

### 15.8. “Pair programming 100% thời gian là mục tiêu”

**Dấu hiệu:** hai người phải ngồi cùng ở mọi ticket dù không có rủi ro hoặc mục tiêu học rõ.

**Cơ chế sai:** đo sự hiện diện của thực hành thay vì tác dụng của nó.

**Thay thế:** pair nơi tăng chất lượng/chuyển tri thức, review và điều chỉnh theo evidence.

### 15.9. “TDD nghĩa là tăng số test”

**Dấu hiệu:** unit tests trùng lặp tăng nhanh nhưng callback trùng và phân quyền không được kiểm chứng.

**Cơ chế sai:** tối ưu hoạt động thay vì bảo vệ rủi ro.

**Thay thế:** chọn test có assertion mạnh và tầng kiểm chứng phù hợp, kèm DoD/quality.

### 15.10. “Có nhiều buổi phỏng vấn là đã làm sản phẩm tốt”

**Dấu hiệu:** team đếm số cuộc phỏng vấn nhưng không có quyết định Product Backlog nào thay đổi.

**Cơ chế sai:** discovery bị biến thành output.

**Thay thế:** ghi insight, độ tin cậy, giả thuyết và lựa chọn sản phẩm được cập nhật.

### 15.11. “QA chịu chất lượng, Developers chỉ code”

**Dấu hiệu:** mọi PBI chuyển đến hàng chờ kiểm thử cuối Sprint, Developers báo Code Complete.

**Cơ chế sai:** chất lượng bị trì hoãn và trách nhiệm bị phân mảnh.

**Thay thế:** Developers tạo Increment đạt DoD, chuyên gia kiểm thử cộng tác sớm và thiết kế test theo rủi ro.

### 15.12. “Velocity càng tăng thì Agile càng trưởng thành”

**Dấu hiệu:** story points bị tăng ước lượng hoặc chia ticket để đạt mục tiêu quản lý.

**Cơ chế sai:** story points không đo năng suất phổ quát hay outcome.

**Thay thế:** dự báo nội bộ có bối cảnh; quan sát flow, Increment, quality và giá trị.

### 15.13. “Chỉ nhìn cycle time của item đã Done”

**Dấu hiệu:** các item dễ hoàn tất nhanh nhưng hạng mục khó blocked ngày càng lâu.

**Cơ chế sai:** survivorship bias, bỏ qua work item age/WIP.

**Thay thế:** xem cả item đang mở, blocked, định nghĩa Done và loại công việc.

### 15.14. “Học xong kỹ thuật, không cần thời gian áp dụng”

**Dấu hiệu:** coding dojo kết thúc, tuần sau mọi PBI vẫn bị giao đầy tải và không có cơ hội pair.

**Cơ chế sai:** kiến thức không chuyển vào hành vi.

**Thay thế:** chọn lát cắt thật với thời gian mentoring và bằng chứng chuyển giao.

### 15.15. “Không phản biện để giữ không khí tích cực”

**Dấu hiệu:** ai cũng gật đầu dù callback chưa xác thực hoặc metric không có mẫu số.

**Cơ chế sai:** thiếu an toàn tâm lý để nêu bất định, dẫn tới đồng thuận giả.

**Thay thế:** phản hồi dựa trên sự kiện, quyết định rõ và quyền nêu rủi ro.

### 15.16. “Retrospective chỉ ghi cần giao tiếp tốt hơn”

**Dấu hiệu:** cùng một câu xuất hiện nhiều Sprint, không có ai thử thay đổi.

**Cơ chế sai:** không chuyển phản tư thành hành động có kiểm chứng.

**Thay thế:** một giả thuyết cụ thể, phạm vi, owner, guardrail và mốc đánh giá.

### 15.17. “Đổi sơ đồ tổ chức là đủ”

**Dấu hiệu:** đổi tên Team Frontend thành Stream Team nhưng code ownership, CI và quyền ưu tiên không đổi.

**Cơ chế sai:** trách nhiệm chỉ đổi trên giấy.

**Thay thế:** điều chỉnh năng lực, ranh giới hợp đồng, DoD, Product Goal và quyền để đội giao lát cắt.

### 15.18. “Bỏ kiểm soát là thích ứng nhanh”

**Dấu hiệu:** bỏ security tests hoặc kiểm tra dữ liệu để giảm cycle time.

**Cơ chế sai:** tạo tốc độ giả bằng cách chuyển rủi ro sang người dùng.

**Thay thế:** đưa kiểm chứng bắt buộc vào công việc sớm, giảm phạm vi hoặc cải thiện tự động hóa an toàn.

### 15.19. “Mọi đội phải dùng cùng một quy trình và lịch học”

**Dấu hiệu:** đội incident response và đội xây tính năng mới bị ép một nhịp/ngưỡng velocity giống nhau.

**Cơ chế sai:** bỏ bối cảnh dịch vụ và mức bất định.

**Thay thế:** nguyên tắc/mục tiêu chung nhưng thử Scrum/Kanban/XP và lộ trình năng lực theo nhu cầu thực, có guardrails.

### 15.20. “Một kết quả tốt sau thay đổi chứng minh nguyên nhân”

**Dấu hiệu:** conversion tăng sau khóa training dù đồng thời thay UX, chiến dịch và tracking.

**Cơ chế sai:** nhầm tương quan thời gian với quan hệ nhân quả, bỏ confounding.

**Thay thế:** ghi thay đổi đồng thời, kiểm tra dữ liệu/cohort, mô tả mức chắc chắn và xem qua nhiều vòng.

## 16. Workshop 100 phút: một user story, ba loại năng lực

Workshop dành cho người học thực hành phối hợp Product Owner, Developers, người có chuyên môn QA/UX/operations và facilitator. Không phải Scrum event bắt buộc; thời lượng có thể điều chỉnh.

### 16.1. Đề bài

Một nền tảng học trực tuyến có 200 báo cáo hỗ trợ liên quan tới trạng thái đăng ký trong một tháng (con số giả định, chưa chuẩn hóa theo lượng giao dịch). Product Owner muốn thêm nút “Thanh toán lại”. Developers lo callback trùng; QA cho rằng test integration chưa đủ; UX nhận thấy thông điệp “Đang xử lý” mơ hồ.

Hãy tạo **một lát cắt có thể kiểm chứng** và một kế hoạch thực hành **cả ba trụ cột**, không chọn đào tạo giao tiếp, học sản phẩm hay CI tách rời.

### 16.2. Các vai trò

**Product Owner:** làm rõ giá trị và lựa chọn Product Backlog, không chỉ giao ngay nút do stakeholder yêu cầu.

**Developer A (API):** giải thích trạng thái đáng tin, callback và rủi ro idempotency.

**Developer B (UI):** giải thích thông điệp, đường thao tác, hành vi khi lỗi và phụ thuộc API.

**Tester/quality specialist:** yêu cầu ví dụ lỗi/quyền và cách tạo bằng chứng trên build thực.

**UX/research:** nêu người học thực sự hiểu gì và cách kiểm chứng câu chữ/trải nghiệm.

**Facilitator/Scrum Master khi dùng Scrum:** giúp nhóm nghe đủ góc nhìn, làm rõ quyền quyết định và kiểm tra cách cộng tác.

**Người vận hành/bảo mật khi phù hợp:** đánh giá tác động sự cố, riêng tư và khả năng phục hồi.

### 16.3. Lịch workshop minh họa

| Phút | Hoạt động | Đầu ra |
|---|---|---|
| **0–10** | Chọn câu hỏi sản phẩm và guardrails | Outcome và rủi ro cần giữ |
| **10–25** | Phân tích evidence/ticket hỗ trợ và giả định | Bản đồ vấn đề và bất định |
| **25–40** | Three Amigos: viết ví dụ PENDING/CONFIRMED/FAILED | AC và những trường hợp sai cần kiểm |
| **40–55** | Xác định lát cắt dọc và cách phối hợp | PBI nhỏ, ownership, hợp đồng |
| **55–70** | Lập test strategy/CI plan, mô phỏng Red–Green–Refactor | Một cách kiểm chứng hành vi |
| **70–80** | Thảo luận điểm bất đồng/điều kiện quyết định | Decision record, nguy cơ còn mở |
| **80–90** | Chọn outcome/flow/quality signals | Metric contract tối thiểu |
| **90–100** | Chọn thử nghiệm năng lực hai Sprint và retro | Owner, mentor, mốc xem lại |

### 16.4. Thẻ sự kiện phát sinh

Khi nhóm đã chọn “thêm nút thanh toán lại”, người hướng dẫn đưa thêm thông tin:

> **Thẻ A:** Hầu hết giao dịch bị hỏi lại đang ở trạng thái PENDING, đối tác có thể xác nhận muộn.

Đội có tiếp tục thêm nút không? Nếu nút tạo giao dịch trùng, cần **xem lại giả thuyết và ràng buộc**, không chỉ sửa UI.

> **Thẻ B:** Một integration test ở môi trường staging thỉnh thoảng fail vì callback xử lý đồng thời.

Đội có tắt test để làm demo không? Cần **phân biệt flaky test với race condition thật**, điều tra và giữ quality gate phù hợp.

> **Thẻ C:** Marketing yêu cầu release cùng banner mới, dù API quyền chưa có bằng chứng.

Ai quyết định thứ tự và điều kiện phát hành? Phải nêu **Product Owner/Developers và thẩm quyền guardrail**, không dùng “đội tự quản” để né trách nhiệm.

> **Thẻ D:** Một Developer là người duy nhất hiểu contract với đối tác và tuần tới vắng mặt.

Nhóm sẽ luyện năng lực bằng pairing, ghi contract và làm test nào để tránh phụ thuộc một người?

### 16.5. Đáp án workshop không phải một giao diện cố định

Một phương án tốt có thể chọn:

- Không cho phép thanh toán lại khi giao dịch chưa được xác nhận thất bại theo chính sách.
- Hiển thị PENDING rõ ràng, hướng dẫn kiểm tra lại và đường hỗ trợ.
- Bảo vệ quyền học không được cấp từ trạng thái chưa xác nhận.
- Tạo integration test cho callback lặp và API test phân quyền.
- Thử với học viên phù hợp để xem thông điệp có dễ hiểu không.
- Theo dõi tỷ lệ vào bài, ticket hỗ trợ theo mẫu số, sự cố và WIP/age.
- Thực hành Three Amigos, pairing và CI trên PBI thật.

Một phương án khác cũng có thể hợp lý nếu dữ liệu cho thấy vấn đề chính là kết nối hoặc đối tác. **Tiêu chí là chất lượng lập luận, guardrails và bằng chứng**, không phải chọn cùng UI mà người hướng dẫn nghĩ ra.

### 16.6. Rubric đánh giá

| Tiêu chí | Chưa đạt | Đạt | Tốt |
|---|---|---|---|
| **Cộng tác** | Đổ lỗi hoặc làm việc riêng | Có trao đổi và owner | Giải quyết bất đồng bằng sự kiện, quyền và quyết định rõ |
| **Sản phẩm** | Lặp lại yêu cầu nút thanh toán | Nêu người dùng, outcome, AC | Thay giả thuyết khi có evidence; guardrails rõ |
| **Kỹ thuật** | Chỉ nói “QA sẽ kiểm tra sau” | Có test/integration plan | Chọn lớp test theo rủi ro, CI và bằng chứng DoD |
| **Học tập** | Chỉ nêu khóa học nên tham gia | Có pairing/mentoring | Một kỹ năng cụ thể được áp vào PBI và kiểm chứng lại |
| **Đo lường** | Đếm task, test, giờ học | Có outcome và quality | Định nghĩa mẫu số, flow, bất định và guardrails |
| **Quyết định** | Khẳng định chắc chắn dù thiếu dữ liệu | Ghi rủi ro còn mở | Biết điều kiện nào cần kiểm tra trước khi mở rộng |

## 17. Bộ mẫu thực hành để gắn kỹ năng với kết quả sản phẩm

Các mẫu sau là **công cụ hỗ trợ**, không phải artifacts chính thức của Scrum hoặc chứng chỉ Agile. Đội có thể rút gọn theo quy mô và rủi ro. Mục đích chung là làm rõ **năng lực cần để tạo giá trị và bằng chứng cho thấy việc học đã đi vào công việc**.

### 17.1. Capability Improvement Card

~~~text
PRODUCT GOAL / VAN DE:
  [Hoc vien can hoan tat tac vu nao?]

TIN HIEU HIEN TAI:
  [Su co, feedback, item age, loi tich hop, du lieu theo cohort]

KY NANG CONG TAC CAN PHAT TRIEN:
  [Vi du: xu ly bat dong ve API contract]

KY NANG SAN PHAM CAN PHAT TRIEN:
  [Vi du: phan biet PENDING va CONFIRMED trong AC]

KY NANG KY THUAT CAN PHAT TRIEN:
  [Vi du: integration tests va CI cho callback lap]

DIEU KIEN TO CHUC CAN:
  [Quyen PO, moi truong, thoi gian pairing, access feedback]

LAT CAT THUC HANH:
  [Mot PBI co gia tri va rui ro kiem soat duoc]

AI HO TRO:
  [Mentor, expert, stakeholder; thoi diem can]

BANG CHUNG HOC:
  [Nang luc thuc hien; khong chi so gio hoc]

QUALITY GUARDRAILS:
  [DoD, bao mat, du lieu, kha nang van hanh]

MOC KIEM TRA:
  [Sau PBI / Sprint / su kien feedback]

QUYET DINH SAU THU:
  [Giu, sua, mo rong, dung]
~~~

### 17.2. Mẫu kỹ năng cấp đội có hành vi thực

| Năng lực | Mức đội cần trong công việc sắp tới | Bằng chứng hiện tại | Cách học | Khi nào xem lại |
|---|---|---|---|---|
| Làm rõ AC lỗi/biên | Có thể làm trước PBI có rủi ro | Thường bị hỏi lại sau code | Three Amigos trên hai PBI | Sau hai lượt refinement |
| Thử nghiệm nhu cầu | Biết phỏng vấn và ghi insight không dẫn dắt | Chủ yếu lấy yêu cầu từ quản lý | Coaching + quan sát học viên | Khi có dữ liệu từ nhóm thử |
| Pairing cho API contract | Có ít nhất hai người hỗ trợ được lỗi phổ biến | Một người là nút thắt | Pair luân phiên và review test | Sau hai thay đổi contract |
| CI/integration test | Có test ổn định cho trạng thái quyền | Quarantine test quan trọng | Test dojo + sửa fixture thật | Sau một số lần CI trên build |
| Feedback và retrospective | Nêu hành vi, bằng chứng, hành động | Chỉ ghi “cần giao tiếp tốt hơn” | Facilitation và thử nghiệm | Retrospective tiếp theo |

Không cần điền tên người hoặc mức điểm chi tiết vào bảng công khai. Nếu cần mentoring cá nhân, trao đổi riêng tôn trọng nguyện vọng và dữ liệu của người học; bảng cấp đội tập trung vào **rủi ro năng lực của hệ thống**.

### 17.3. Mẫu thử nghiệm hai Sprint

~~~text
TEN THU NGHIEM:
  [Vi du: Giam loi contract entitlement]

GIA THUYET:
  Neu PO, Developers va tester chot acceptance examples som
  va contract tests chay trong CI,
  thi mismatches se duoc phat hien som hon va it item bi blocked.

PHAM VI:
  [Hai PBI tiep theo thuoc luong ghi danh]

HOAT DONG CONG TAC:
  [Mot phien Three Amigos ngan, direct feedback khi fail]

HOAT DONG SAN PHAM:
  [AC, rui ro PENDING/CONFIRMED, muc tieu nguoi dung]

HOAT DONG KY THUAT:
  [Provider/consumer checks, integration fixture, CI]

RANH GIOI AN TOAN:
  [Khong ha DoD, khong cap quyen sai, khong bo test quan trong]

DU LIEU BAN DAU:
  [Loai PBI, work item age, thoi diem phat hien mismatch]

DU LIEU SAU THU:
  [Cung dinh nghia, su co, confidence va gioi han]

RUI RO THAY DOI DONG THOI:
  [Moi truong, nguoi, workload, doi tac...]

QUYET DINH XEM LAI:
  [Giu/sua/dung va vi sao]
~~~

### 17.4. Mẫu phản hồi xây dựng

~~~text
SU KIEN CU THE:
  [PBI, buoi hop, test, tai lieu va su kien quan sat]

TAC DONG:
  [Tren nguoi dung, chất lượng, flow hoac bat dinh]

GIA DINH CUA TOI:
  [Dieu dang nghi nhung chua du bang chung]

CAU HOI CAN LAM RO:
  [Goc nhin nguoi khac va dieu kien thuc te]

HANH DONG DE XUAT:
  [Mot thay doi nho co the thu]

BANG CHUNG XEM LAI:
  [Ket qua ra sao, rui ro co giam khong]
~~~

Ví dụ phản hồi không nên là “bạn luôn thiếu trách nhiệm”. Nó nên là **“PBI ENR-14 bị reopen sau khi phát hiện trạng thái thanh toán thiếu điều kiện; chúng ta có thể chốt ví dụ lỗi và chạy integration test trước khi chuyển Done trong lần tới không?”**

### 17.5. Mẫu Learning Review sau một Increment

| Câu hỏi | Ví dụ câu trả lời tốt |
|---|---|
| Người dùng đã nhận được gì? | Luồng trạng thái PENDING trên build B đạt DoD, phát hành giới hạn theo chính sách |
| Chúng ta học gì về sản phẩm? | Người học không hiểu khi nào nên thử lại, cần nội dung hướng dẫn khác |
| Chúng ta học gì về cộng tác? | Khi PO–Developer–QA chốt ví dụ từ đầu, ít mismatch hơn trong hai PBI đã xét |
| Chúng ta học gì về kỹ thuật? | Contract test phát hiện consumer mapping sai sớm; DB concurrency còn là rủi ro mở |
| Điều gì không thể kết luận? | Chưa đủ dữ liệu để nói conversion toàn sản phẩm tăng |
| Kỹ năng nào đã lan tỏa? | Một người mới có thể sửa test fixture với review |
| Điều gì cần tiếp tục? | Kiểm tra callback lặp, usability và theo dõi lỗi production |

Đây là một cách kết nối **Sprint Review, Retrospective hoặc service review** với học tập; nó không thay mục đích chính thức của bất kỳ event nào.

### 17.6. Mẫu bản ghi quyết định kỹ thuật–sản phẩm

~~~text
QUYET DINH:
  [VD: Khong cho thanh toan lai khi don con PENDING]

BOI CANH:
  [Nguoi dung, du lieu, loi va rang buoc]

CAC PHUONG AN DA XEM:
  A:
  B:
  C:

LY DO CHON:
  [Evidence, gia tri, rui ro, kha nang dao nguoc]

AC / TEST / DOD LIEN QUAN:
  [Lop test va dieu kien bat buoc]

QUYEN QUYET DINH:
  [PO ve uu tien, Developers ve implementation,
   vai tro bat buoc ve security/compliance]

BAT DINH CON MO:
  [Dieu chua biet va pham vi anh huong]

TRIGGER XEM LAI:
  [Loi, feedback, thay contract, xu huong outcome]
~~~

Không cần tạo một decision record cho mọi thay đổi nhỏ. Nó hữu ích khi quyết định **ảnh hưởng nhiều chuyên môn, khó đảo ngược hoặc có rủi ro dữ liệu/quyền**.

### 17.7. Mẫu báo cáo tiến triển chuyển đổi cho lãnh đạo

~~~text
VAN DE SAN PHAM:
  [Hanh trinh nguoi dung va gia tri]

NHUNG NANG LUC DANG PHAT TRIEN:
  Cong tac:
  San pham:
  Ky thuat:

CONG VIEC THAT DA THU:
  [PBI/lát cắt, pham vi va evidence]

THAY DOI HANH VI:
  [Vi du: contract được lam ro truoc code, pairing]

KET QUA CO THE KIEM CHUNG:
  [DoD, product feedback, quality, flow, outcome]

DO TIN CAY DU LIEU:
  [Metric contract, cua so, cohort, work mix, missing]

RUI RO / DIEU CHUA BIET:
  [Chua du sample, thay doi dong thoi, phu thuoc]

DIEU KIEN CAN TU LANH DAO:
  [Quyen, thoi gian, moi truong, chuyen gia]

QUYET DINH TIEP:
  [Nhan rong, thu tiep, sua hoac dung]
~~~

**Một báo cáo chuyển đổi có ích cho lãnh đạo là báo cáo tạo được quyết định hỗ trợ đúng**, không phải bảng hạng người học nhiều giờ nhất.

## 18. Bài tập vận dụng

### Bài tập A — Chứng chỉ và năng lực khác nhau thế nào?

Một tổ chức báo 95% nhân viên đã học Scrum, nhưng vẫn cần một tháng để tích hợp một user story quan trọng và người dùng chưa thấy chức năng chạy được.

**Yêu cầu:** Giải thích vì sao không thể kết luận chuyển đổi đã thành công; nêu mỗi trụ cột một vấn đề có thể cần kiểm tra.

<details>
<summary>Gợi ý đáp án</summary>

Số người học chứng minh đã tham gia đào tạo, không chứng minh năng lực sử dụng thực hành và kết quả sản phẩm. Cộng tác: quyền quyết định/handoff và cách làm rõ phụ thuộc có thể yếu. Sản phẩm: PBI có chia theo giá trị và có Product Goal/outcome rõ không? Kỹ thuật: CI, test/integration và DoD có cho phép Increment nhỏ, an toàn không? Cần kiểm tra bằng chứng chứ không tự gán lỗi cá nhân; chọn một lát cắt thật để thử cải tiến ba chiều.

</details>

### Bài tập B — Nhận diện ba trụ cột trong một user story

User story: “Là học viên có đơn đang chờ, tôi muốn biết trạng thái đúng và bước tiếp theo để không thanh toán trùng hoặc bỏ dở khóa.”

**Yêu cầu:** Liệt kê hai hoạt động cộng tác, hai hoạt động sản phẩm và hai hoạt động kỹ thuật để hoàn tất một lát cắt theo DoD.

<details>
<summary>Gợi ý đáp án</summary>

Cộng tác: PO, Developers và tester cùng xem ví dụ PENDING/CONFIRMED/FAILED; thống nhất ai xử lý contract entitlement và cách giải quyết blocker. Sản phẩm: xác minh người học không hiểu điều gì; làm rõ AC và outcome/guardrails. Kỹ thuật: test trạng thái/quyền trên API/integration theo rủi ro; chạy CI, kiểm chứng dữ liệu và không báo thành công giả. Có thể bổ sung usability observation và monitoring sau release phù hợp.

</details>

### Bài tập C — Skill matrix có hại khi nào?

Quản lý công bố bảng điểm kỹ năng từ 1–5 của từng cá nhân, yêu cầu ai dưới 4 phải giải trình. Kết quả tháng sau mọi người tự chấm 5, nhưng một chuyên gia vẫn là nút thắt CI.

**Yêu cầu:** Nêu cơ chế tạo số liệu sai và thiết kế lại cách đánh giá.

<details>
<summary>Gợi ý đáp án</summary>

Khi dùng điểm để phạt/xếp hạng, mọi người có động lực tự khai cao và tránh nói năng lực thiếu, dẫn tới dữ liệu không đáng tin. Nên bắt đầu từ năng lực cần cho Product Goal, đánh giá bằng hành vi ở một PBI thật, tổng hợp khoảng trống cấp đội và thiết kế pairing/mentoring. Điểm chặn CI cần kế hoạch chia sẻ tri thức, quyền và test fixture, không chỉ đổi điểm số của cá nhân.

</details>

### Bài tập D — TDD có đủ để bảo vệ thanh toán không?

Một Developer viết 100 unit tests cho logic mapping trạng thái. Chưa có kiểm tra callback lặp, phân quyền tài khoản khác hoặc dữ liệu DB đồng thời.

**Yêu cầu:** Đánh giá giới hạn bằng chứng và đề xuất chiến lược kỹ thuật theo rủi ro.

<details>
<summary>Gợi ý đáp án</summary>

100 unit tests có thể hữu ích nhưng không bảo vệ các rủi ro tích hợp/bảo mật nếu không kiểm tra chúng. Cần làm rõ AC/trạng thái nguồn với PO, kiểm tra callback lặp và dữ liệu bền vững qua integration/concurrency tests, API authz tests với nhiều identity, contract tests và monitoring phù hợp. TDD hỗ trợ logic nhỏ; không thay phương pháp kiểm chứng ở lớp khác. Không nên chỉ tăng test count.

</details>

### Bài tập E — Phản hồi có bằng chứng

Sau một lỗi quyền học, một thành viên nói: “Backend luôn làm hỏng việc, lần nào cũng vậy.”

**Yêu cầu:** Viết lại thành phản hồi gồm sự kiện, tác động, câu hỏi và hành động đề xuất.

<details>
<summary>Gợi ý đáp án</summary>

Ví dụ: “Trong release B, khi API trả PENDING_AUTHORIZATION, giao diện hiển thị như CONFIRMED và một số học viên bị chặn vào bài. Tôi chưa rõ do hợp đồng trạng thái hay test thiếu. Chúng ta có thể cùng xem event/log và AC, rồi bổ sung contract/integration test cho trạng thái này trước lần tích hợp tới không?” Cách nói không kết luận nguyên nhân khi thiếu bằng chứng và đề xuất một hành động kiểm chứng được.

</details>

### Bài tập F — Một khóa đào tạo không giải quyết thiếu quyền

Product Owner đã học discovery và backlog ordering, nhưng không được trao đổi với học viên; marketing có thể thay thứ tự Sprint Backlog trực tiếp.

**Yêu cầu:** Chọn hai điều kiện tổ chức cần sửa và một thực hành sản phẩm có thể thử.

<details>
<summary>Gợi ý đáp án</summary>

Cần làm rõ quyền Product Owner đối với Product Backlog và cơ chế nhận yêu cầu từ stakeholders; cung cấp kênh tiếp cận học viên/feedback có chính sách dữ liệu phù hợp. Thử một phiên quan sát người học đang PENDING và dùng insight để điều chỉnh một PBI, rồi theo dõi acceptance/outcome. Nếu dùng Scrum, Developers lập và thích ứng Sprint Backlog hướng Sprint Goal; không để nhiều bên chèn lệnh trái quyền. Đào tạo thêm PO không thay điều kiện hệ thống.

</details>

### Bài tập G — Chia năng lực kỹ thuật mà không bắt mọi người full-stack

Nhóm có hai Developers UI, hai backend Developers và một tester. Chỉ một backend Developer hiểu cơ chế callback từ đối tác, mọi PBI thanh toán chờ người đó.

**Yêu cầu:** Thiết kế cách lan tỏa kỹ năng thực tế qua hai Sprint và nêu guardrail.

<details>
<summary>Gợi ý đáp án</summary>

Sprint đầu: hai người pair trên một PBI callback có test và review, ghi contract/trạng thái, tạo integration fixture. Sprint sau: người mới tự xử lý một thay đổi nhỏ với review của chuyên gia; tester/PO tham gia làm rõ AC và trường hợp lỗi. Guardrails: không bỏ xác thực callback, không thay schema production khi chưa kiểm chứng, giữ DoD và ràng buộc dữ liệu. Mục tiêu là giảm phụ thuộc kiến thức, không yêu cầu mọi người trở thành chuyên gia thanh toán toàn diện.

</details>

### Bài tập H — Một retrospective không có hành động

Ba Retrospectives liên tiếp đều ghi “cần giao tiếp tốt hơn”, nhưng cùng một loại API mismatch vẫn xảy ra cuối Sprint.

**Yêu cầu:** Viết một thử nghiệm hai Sprint có giả thuyết, hoạt động và chỉ số xem lại.

<details>
<summary>Gợi ý đáp án</summary>

Ví dụ: “Nếu PO, Developers và tester chốt ví dụ trạng thái trước coding, đồng thời CI chạy consumer/provider contract tests, mismatch sẽ được phát hiện sớm hơn”. Phạm vi: hai PBI entitlement tiếp theo. Hoạt động: Three Amigos 20 phút khi refinement, pairing viết một test chung, điều tra fail. Xem lại thời điểm phát hiện mismatch, blocked age và chất lượng Increment. Không hạ DoD; ghi nếu workload/môi trường thay đổi để tránh quy nguyên nhân quá mức.

</details>

### Bài tập I — Chọn ba tín hiệu chuyển đổi có ý nghĩa

Tổ chức chỉ báo story points, số chứng chỉ và số giờ họp; người học vẫn gặp lỗi ghi danh.

**Yêu cầu:** Đề xuất ba tín hiệu cân bằng theo outcome, chất lượng và khả năng làm việc, kèm giới hạn.

<details>
<summary>Gợi ý đáp án</summary>

Outcome: tỷ lệ học viên đủ điều kiện vào bài đầu trong cửa sổ được định nghĩa; phải làm rõ mẫu số/cohort. Chất lượng: sự cố cấp quyền/giao dịch theo severity và người dùng ảnh hưởng; không dùng “ít bug hơn” khi monitoring thay đổi. Flow: work item age của PBI ghi danh đang blocked hoặc cycle time tới DoD với định nghĩa rõ; không so task UI với PBI đã tích hợp. Có thể xem CI reliability như tín hiệu bổ sung. Kết quả cần được đọc cùng bối cảnh, không cộng thành một “điểm Agile”.

</details>

### Bài tập J — Tính tỷ lệ outcome nhưng thay mẫu số

Tháng đầu có 800 lượt đăng ký đủ điều kiện, 640 lượt vào bài đầu theo quy tắc thống nhất. Tháng sau ghi nhận 900 lượt bắt đầu, nhưng báo cáo loại 100 lượt thất bại khỏi mẫu số và vẫn có 700 lượt vào bài.

**Yêu cầu:** Tính hai cách nhìn tháng sau và nêu điều phải xác minh.

<details>
<summary>Gợi ý đáp án</summary>

Tháng đầu \(640/800=80\%\). Nếu 900 lượt tháng sau đều đủ điều kiện theo cùng định nghĩa, tỷ lệ so sánh nhất quán là \(700/900\approx77{,}78\%\). Nếu loại 100 lượt rồi tính \(700/800=87{,}5\%\), tỷ lệ tăng giả khi 100 lượt thất bại vẫn thuộc population mục tiêu. Cần kiểm tra điều kiện loại trừ, trùng event, cửa sổ theo dõi, cohort miễn phí/trả phí và thời điểm chốt dữ liệu. Không tự loại thất bại để chứng minh chuyển đổi tốt hơn.

</details>

### Bài tập K — Nhiều thay đổi cùng lúc

Sau ba tháng chuyển đổi, cycle time của PBI giảm, nhưng cùng lúc tổ chức nâng CI, tuyển thêm hai Developers và chuyển sang làm nhiều thay đổi nội dung nhỏ hơn.

**Yêu cầu:** Đưa ra kết luận đúng mức chứng cứ và đề xuất bước tiếp.

<details>
<summary>Gợi ý đáp án</summary>

Không khẳng định training hoặc Scrum riêng lẻ gây ra toàn bộ mức giảm. Có thể nói “chúng ta quan sát cycle time của nhóm item đã Done giảm trong giai đoạn có nhiều thay đổi; cần kiểm tra work mix, Definition of Done, WIP age và dữ liệu chất lượng trước khi suy ra hiệu quả”. Tiếp tục theo dõi các PBI tương đồng qua nhiều kỳ, nêu guardrails/outcome và đánh giá những can thiệp có cơ chế rõ.

</details>

### Bài tập L — Scrum, Kanban hay XP cho một đội dịch vụ?

Một đội phải xử lý sự cố sản xuất bất ngờ, yêu cầu hỗ trợ liên tục và thỉnh thoảng phát triển khả năng mới. Lãnh đạo bắt buộc đội tăng story points mỗi Sprint.

**Yêu cầu:** Đề xuất cách phối hợp và kỹ năng cần phát triển, không giả định một phương pháp duy nhất.

<details>
<summary>Gợi ý đáp án</summary>

Có thể ưu tiên Kanban để nhìn WIP, aging, phân loại và chính sách expedite; dùng retrospective/service review để học từ flow và sự cố. Nếu có Scrum trong phạm vi phát triển sản phẩm, cần giữ accountabilities/events đúng và không so velocity với đội khác. Kỹ thuật: test/reliability, CI, rollback và observability. Sản phẩm: hiểu tác động người dùng và ưu tiên mức độ nghiêm trọng. Cộng tác: incident communication và decision rights. Không lấy story points làm thước đánh giá cá nhân hoặc mục tiêu phải tăng.

</details>

### Bài tập M — Kế hoạch 12 tuần có nhất thiết tuần nào cũng như nhau?

Đội dự định tuần 4 học TDD nhưng tuần đó có sự cố lộ thông tin cá nhân cần xử lý khẩn theo quy trình. Người quản lý muốn vẫn tổ chức workshop cho đủ lộ trình.

**Yêu cầu:** Ra quyết định phù hợp với Agile và guardrails.

<details>
<summary>Gợi ý đáp án</summary>

Ưu tiên xử lý và giảm ảnh hưởng sự cố theo thẩm quyền và chính sách bắt buộc. Tạm điều chỉnh workshop, không hạ kiểm soát an toàn hoặc bỏ incident response để giữ lịch đào tạo. Khi ổn định, dùng sự cố (với dữ liệu được bảo vệ) để học về phân quyền, test/API contracts, communication và product impact; cập nhật lộ trình dựa trên bằng chứng. Lịch 12 tuần chỉ là kế hoạch thích ứng, không phải cam kết cố định mọi hoạt động.

</details>

### Bài tập N — Platform đã dạy nhưng nhóm vẫn bị chặn

Platform team tổ chức ba buổi training về deploy, nhưng quyền triển khai mọi môi trường vẫn phải xin một chuyên gia qua ticket, thời gian chờ thường là một tuần.

**Yêu cầu:** Vì sao training không đủ và đề xuất can thiệp tạo năng lực.

<details>
<summary>Gợi ý đáp án</summary>

Kỹ năng không thể dùng nếu không có quyền và công cụ. Cần phân loại thao tác phổ biến đủ an toàn để tự phục vụ qua template/pipeline đã kiểm chứng, phân quyền theo chính sách và audit phù hợp; giữ review có thẩm quyền cho ngoại lệ. Pair người học thực hiện một deploy trong môi trường phù hợp, đo thời gian chờ và sự cố; không chỉ đếm số buổi đào tạo.

</details>

### Bài tập O — Chọn một ưu tiên năng lực khi cả ba đều yếu

Một đội thiếu CI, Product Owner chưa có Product Goal và có xung đột về quyền ưu tiên. Nguồn lực thử nghiệm trong hai tuần đầu rất hạn chế.

**Yêu cầu:** Có cần phát triển cả ba cùng một lượng công sức không? Hãy đề xuất một hành động nhỏ cho mỗi chiều trong cùng một PBI.

<details>
<summary>Gợi ý đáp án</summary>

Không cần chia đều công sức, nhưng không nên bỏ trụ cột nào. Cộng tác: làm rõ ai quyết định thứ tự và một cuộc trao đổi xử lý rủi ro PBI. Sản phẩm: phát biểu một mục tiêu kết quả và AC cho một lát cắt nhỏ. Kỹ thuật: chọn một kiểm tra tích hợp quan trọng hoặc sửa một phần pipeline đủ để thấy feedback. Giữ DoD và guardrails; đánh giá tác động sau PBI để chọn đầu tư tiếp theo. Nếu quyền PO hoàn toàn không có, lãnh đạo phải tham gia tháo điều kiện ấy.

</details>

### Bài tập P — Nhân rộng mô hình học

Đội thí điểm có một chuyên gia TDD và Product Coach tham gia gần như toàn thời gian; kết quả thử nghiệm tích cực. Lãnh đạo muốn yêu cầu 20 đội áp dụng giống hệt ngay tuần sau.

**Yêu cầu:** Đề xuất điều kiện cần xem trước khi nhân rộng.

<details>
<summary>Gợi ý đáp án</summary>

Cần biết cơ chế cải thiện nào thực sự có bằng chứng, nguồn hỗ trợ chuyên gia có đủ, các đội khác có product boundaries/quyền/CI và loại công việc tương đồng không. Có thể nhân rộng theo từng cụm với mentoring, communities of practice, tài liệu/test templates và cách học từ đội mới; không chuyển một checklist cứng cho cả tổ chức. Theo dõi outcome, quality, flow và giới hạn đánh giá. Cần giữ khả năng dừng hoặc điều chỉnh khi kết quả khác đội thí điểm.

</details>

## 19. Checklist tự đánh giá phát triển kỹ năng Agile song song

Hãy chọn **một sản phẩm hoặc một dòng giá trị có vấn đề thật**, rồi trả lời bằng hành vi và bằng chứng. Đây không phải bảng chấm điểm trưởng thành bắt buộc; các câu hỏi giúp phát hiện **đầu tư nào tạo năng lực sử dụng được**.

### 19.1. Mục tiêu và điều kiện chuyển đổi

1. Có biết **người dùng nào và kết quả nào** cần cải thiện không?
2. Có phân biệt **chuyển đổi Agile** với chỉ đổi tên vai trò, Sprint và công cụ không?
3. Tổ chức có một mục tiêu đủ rõ để các nhóm cân nhắc trade-off không?
4. Có bảo vệ những guardrails không thể hạ: an toàn, bảo mật, dữ liệu, chất lượng bắt buộc không?
5. Có Product Goal/định hướng sản phẩm rõ nếu đội đang dùng Scrum không?
6. Product Owner có thực quyền quản lý Product Backlog hay liên tục bị giao ưu tiên trái nhau?
7. Developers có quyền tự quản cách thực hiện trong ranh giới kỹ thuật và DoD không?
8. Những điều kiện để thực hành kỹ năng (thời gian, dữ liệu, môi trường, quyền) có sẵn không?

### 19.2. Kỹ năng cộng tác

9. Đội có trao đổi về **vấn đề người dùng và rủi ro** thay vì chỉ danh sách task không?
10. Khi bất đồng, mọi người có thể phân biệt sự kiện, giả định, mục tiêu và quyền quyết định không?
11. Người có chuyên môn test, UX, vận hành có tham gia sớm khi rủi ro liên quan không?
12. Những người liên quan có thể phản hồi dựa trên hành vi và tác động, không gắn nhãn cá nhân không?
13. Có thể nêu một ví dụ nhóm giải quyết blocker sớm nhờ cộng tác không?
14. Có kỹ năng facilitation giúp buổi trao đổi kết thúc bằng quyết định/hành động rõ không?
15. Mọi người có dám báo test fail, sự cố và bất định mà không lo bị đổ lỗi vô lý không?
16. Retrospective có chọn một thử nghiệm cụ thể và xem lại tác dụng không?
17. Có giảm được phụ thuộc vào một người để giải quyết các câu hỏi thường gặp không?

### 19.3. Kỹ năng sản phẩm

18. Đội có nguồn hiểu biết người dùng đáng tin, không chỉ yêu cầu từ lãnh đạo nội bộ không?
19. Có phân biệt output của feature với outcome người dùng không?
20. Mỗi giả thuyết quan trọng có cách kiểm tra trong bối cảnh an toàn phù hợp không?
21. Product Backlog có được ưu tiên theo giá trị, rủi ro, phụ thuộc và bằng chứng mới không?
22. PBI có được chia thành lát cắt giá trị thay vì chỉ UI/API/DB/test task không?
23. Acceptance criteria có trường hợp lỗi, biên và quyền phù hợp không?
24. Người phụ trách sản phẩm có trao đổi với Developers để hiểu ràng buộc kỹ thuật thực không?
25. Dữ liệu outcome có metric contract về cohort, mẫu số và cửa sổ quan sát không?
26. Có ít nhất một ví dụ Product Backlog đã thay đổi thứ tự vì phản hồi người dùng không?

### 19.4. Kỹ năng kỹ thuật và chất lượng

27. Nhóm có thể tích hợp thay đổi nhỏ thường xuyên thay vì chờ cuối kỳ không?
28. CI có đáng tin và phản hồi kịp thời về những rủi ro phù hợp không?
29. Test suite có kiểm tra hành vi quan trọng, không chỉ đếm test count/coverage không?
30. TDD hoặc cách test-first khác có được luyện đúng phạm vi và mục đích không?
31. Có contract/integration checks cho những giao diện xuyên thành phần quan trọng không?
32. Những thay đổi dữ liệu/quyền có được kiểm chứng trước khi phát hành phạm vi liên quan không?
33. Team có thực hành refactoring có test bảo vệ và không tạo overengineering vô cớ không?
34. Increment có đáp ứng DoD chung phù hợp khi đội dùng Scrum không?
35. Đội có thể theo dõi sự cố, lỗi vận hành và phản hồi người dùng sau khi cung cấp không?
36. Có cách khôi phục hoặc giảm ảnh hưởng phù hợp khi thay đổi tạo sự cố không?

### 19.5. Học tập có tác dụng

37. Bảng kỹ năng có dựa trên năng lực cần cho Product Goal hơn là danh sách chứng chỉ không?
38. Các mức kỹ năng có ví dụ hành vi quan sát được không?
39. Skill matrix có được dùng cho hỗ trợ/mentoring thay vì xếp hạng cá nhân công khai không?
40. Đội có cơ hội pairing hoặc thực hành có feedback trên PBI thật không?
41. Người học có thể làm một phần công việc tự chủ hơn sau mentoring không?
42. Có một ví dụ một kiến thức quan trọng được chia sẻ cho người thứ hai không?
43. Lãnh đạo có dành khả năng/điều kiện thực hành mà không hạ quality guardrails không?
44. Các cộng đồng thực hành có chuyển được giải pháp vào workflow, CI hoặc backlog thật không?
45. Đội có đánh giá kỹ năng ở cấp hệ thống và thừa nhận những chỗ chuyên gia vẫn cần thiết không?

### 19.6. Dữ liệu và quyết định mở rộng

46. Có xem WIP, throughput, work item age, cycle time theo cùng ranh giới workflow không?
47. Có tránh bỏ item blocked khi khoe cycle time của những item đã Done không?
48. Có phân biệt story points, test counts, chứng chỉ và cuộc họp với kết quả người dùng không?
49. Có xem sự cố và chất lượng theo mức ảnh hưởng, không chỉ một tỷ lệ tổng không?
50. Nếu so trước–sau, có kiểm tra đổi DoD, work mix, đội ngũ, môi trường và tracking không?
51. Có tránh kết luận nguyên nhân chắc chắn chỉ từ việc chỉ số tăng sau đào tạo không?
52. Có nói rõ điều chưa biết, dữ liệu thiếu và rủi ro khi nhân rộng thực hành không?
53. Một thử nghiệm cải tiến có giả thuyết, owner, chất lượng tối thiểu và mốc xem lại không?
54. Đội có được phép **sửa hoặc dừng** một thực hành không có tác dụng dù nó mang nhãn Agile không?
55. Kết quả chuyển đổi có giúp người dùng nhận phần mềm hữu ích, đúng và an toàn thường xuyên hơn không?

**Hành động khởi đầu phù hợp khi còn nhiều khoảng trống:** chọn một PBI đang bị chặn vì yêu cầu mơ hồ hoặc lỗi tích hợp; gắn một hành động về cộng tác, một hành động về sản phẩm và một hành động về kỹ thuật vào PBI đó. Quan sát điều thay đổi ở **Increment, chất lượng, phản hồi và khả năng đội làm được việc tiếp theo**, không mở ngay một chương trình đào tạo rộng rồi chờ kết quả tự xuất hiện.

## 20. Tổng kết

- **Chuyển đổi Agile là xây năng lực thích ứng**, không chỉ mở Sprint, họp Daily hay cấp chứng chỉ. Năng lực phải được kiểm chứng qua hành vi và kết quả trên công việc thật.
- **Ba trụ cột phụ thuộc lẫn nhau:** cộng tác để chia sẻ hiểu biết/quyền quyết định; sản phẩm để chọn đúng giá trị; kỹ thuật để tạo thay đổi có chất lượng. Thiếu một chiều có thể làm nghẽn cả dòng giá trị.
- **Phát triển song song không nghĩa chia đều ngân sách**. Mỗi chu kỳ cần chú ý năng lực tối thiểu của cả ba trụ cột, ưu tiên rủi ro và nút thắt có bằng chứng.
- **Học sản phẩm** gồm khám phá nhu cầu, Product Goal, ưu tiên backlog, user story/AC, kiểm chứng giả thuyết và outcome, không chỉ viết thêm yêu cầu.
- **Học cộng tác** gồm lắng nghe, phản hồi theo sự kiện, xử lý xung đột, facilitation, tâm lý an toàn và làm rõ quyền, không phải chỉ nhiều cuộc họp hơn.
- **Học kỹ thuật** gồm TDD khi phù hợp, CI, integration/contract tests, refactoring, thiết kế tiến hóa, quan sát vận hành và bảo vệ DoD, không phải chỉ test count.
- **Một lát cắt dọc là môi trường học tốt:** làm rõ hành vi với PO/Developers/tester, triển khai và tích hợp sớm, kiểm tra Increment, quan sát feedback rồi cải tiến.
- **Cross-functional là năng lực cấp nhóm.** T-shaped learning giúp hiểu nhau mà vẫn giữ chuyên môn sâu; không đòi mọi cá nhân biết mọi thứ.
- **Leadership phải tạo điều kiện:** Product Owner có quyền, Developers có môi trường và quyền phù hợp, nhóm có thời gian học, bảo mật/tuân thủ có guardrails, không thưởng/phạt theo KPI dễ bị thao túng.
- **Scrum, Kanban và XP có thể bổ sung nhau** khi dùng đúng phạm vi: mục tiêu và Increment, quản lý dòng công việc, thực hành kỹ thuật cho phản hồi sớm; không đồng nhất chúng hoặc biến thực hành tùy chọn thành quy tắc Scrum bắt buộc.
- **Đo chuyển đổi bằng outcome, chất lượng, flow và năng lực tập thể**, kèm metric contracts và giới hạn suy luận. Chứng chỉ, giờ học, story points và số test chỉ là những tín hiệu hoạt động có phạm vi sử dụng riêng.
- **Thử nghiệm nhỏ, có kiểm chứng và có quyền điều chỉnh** giúp tổ chức học tốt hơn nhân rộng cơ học một quy trình thành công trong một bối cảnh.

Trước khi lên kế hoạch khóa đào tạo Agile tiếp theo, hãy hỏi:

> **“Trên một kết quả người dùng thật, đội đang thiếu hiểu biết sản phẩm nào, kỹ năng cộng tác nào và năng lực kỹ thuật nào? Chúng ta có thể luyện cả ba trên một lát cắt nhỏ với chất lượng không đổi, rồi nhìn bằng chứng gì để quyết định tiếp?”**

Câu hỏi đó chuyển trọng tâm từ **“bao nhiêu người đã học Agile”** sang **“đội đã có thể tạo, kiểm chứng và cải tiến giá trị cho người dùng tốt hơn đến đâu”**.

## Tài liệu tham khảo định hướng

- [Manifesto for Agile Software Development](https://agilemanifesto.org/): giá trị về tương tác con người, phần mềm hoạt động, hợp tác khách hàng và phản hồi thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html): giao phần mềm thường xuyên, chất lượng kỹ thuật, nhịp bền vững, các nhóm tự tổ chức và cải tiến liên tục.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): Scrum accountabilities, Product Goal, Sprint Goal, Definition of Done, Increment và cơ chế empiricism.
- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/): Definition of Workflow, quản lý WIP, throughput, work item age, cycle time và Service Level Expectation.
- [Scrum.org — Evidence-Based Management](https://www.scrum.org/resources/evidence-based-management): góc nhìn thực nghiệm về giá trị sản phẩm và năng lực giao giá trị khi đo hiệu quả.
- [DORA](https://dora.dev/): nghiên cứu về năng lực giao phần mềm, chất lượng thay đổi và vận hành; cần dùng định nghĩa từng metric trong bối cảnh.
- **Kent Beck & Cynthia Andres — _Extreme Programming Explained: Embrace Change_** (ấn bản thứ hai): các thực hành kỹ thuật và hợp tác trong XP.
- **Kent Beck — _Test-Driven Development: By Example_**: Red–Green–Refactor và cách xây vòng phản hồi nhanh cho thay đổi kỹ thuật.
- **Lisa Crispin & Janet Gregory — _Agile Testing: A Practical Guide for Testers and Agile Teams_**: kiểm thử cộng tác, điều kiện chấp nhận và xây chất lượng xuyên vai trò.
- **Teresa Torres — _Continuous Discovery Habits_**: khám phá vấn đề và cơ hội liên tục qua nghiên cứu/kiểm chứng giả thuyết sản phẩm.
- **Marty Cagan — _Inspired: How to Create Tech Products Customers Love_**: góc nhìn phát triển năng lực sản phẩm và đội tạo giá trị.
- **Matthew Skelton & Manuel Pais — _Team Topologies: Organizing Business and Technology Teams for Fast Flow_**: ranh giới nhóm, cognitive load, platform/enabling teams và tương tác nhằm giảm phụ thuộc.
- **Amy C. Edmondson — _The Fearless Organization_**: tâm lý an toàn trong tổ chức và điều kiện để mọi người chia sẻ rủi ro và học từ lỗi.
- **Gene Kim, Jez Humble, Patrick Debois & John Willis — _The DevOps Handbook_**: dòng thay đổi, feedback, tích hợp/triển khai, năng lực vận hành và cải tiến.
- [Cucumber — Gherkin Reference](https://cucumber.io/docs/gherkin/reference/): cách dùng ví dụ hành vi để làm rõ yêu cầu; đặc tả khác với bằng chứng test đã chạy.
- [W3C Web Accessibility Initiative](https://www.w3.org/WAI/): hiểu và kiểm chứng khả năng truy cập của trải nghiệm web trong thiết kế và phát triển.








