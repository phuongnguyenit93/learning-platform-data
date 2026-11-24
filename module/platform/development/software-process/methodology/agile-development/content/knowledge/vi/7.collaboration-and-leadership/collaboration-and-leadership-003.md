# Xây dựng mục tiêu chung và trách nhiệm đối với kết quả

Hãy tưởng tượng một nhóm phát triển tính năng đăng ký tài khoản cho nền tảng học trực tuyến. Đội giao diện cố hoàn tất các màn hình; đội backend cố giao đủ API; người kiểm thử cố đóng toàn bộ lỗi; người phụ trách sản phẩm cố hoàn thành kế hoạch phát hành. Mỗi bộ phận có thể báo cáo rằng mình làm tốt, nhưng người học vẫn không đăng ký được vì thông báo xác minh email đến muộn và không ai xem trải nghiệm từ đầu đến cuối là trách nhiệm của mình.

Vấn đề ở đây không nhất thiết là thiếu nỗ lực. Các thành viên đang **tối ưu các phần việc riêng**, trong khi tổ chức chưa xác lập được một **mục tiêu chung có ý nghĩa với người dùng** và một cách rõ ràng để **cùng chịu trách nhiệm về kết quả**.

Trong Agile, cộng tác hiệu quả bắt đầu khi mọi người hiểu **tại sao** cần làm, **kết quả nào** cần hướng tới, **ai có quyền quyết định điều gì**, và **sẽ ứng xử ra sao khi bằng chứng mới cho thấy kế hoạch chưa hiệu quả**. Mục tiêu chung không có nghĩa mọi người làm cùng một việc. Trách nhiệm chung không có nghĩa trách nhiệm cá nhân bị xóa nhòa hoặc một đội phải bảo đảm tuyệt đối hành vi của người dùng.

Bài học thuộc chương **Cộng tác và lãnh đạo** của module **AGILE_DEVELOPMENT**. Nó kết nối các giá trị Agile với phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; đồng thời vận dụng user story, backlog, Scrum, Kanban, XP và phép đo dòng công việc để xây dựng cách phối hợp hướng tới kết quả thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt mục tiêu chung, nhiệm vụ riêng, đầu ra bàn giao và kết quả cần đạt đối với người dùng.
2. Viết một phát biểu mục tiêu có đối tượng, giá trị, thời hạn xem lại và tín hiệu kiểm chứng, cùng những ràng buộc cần bảo vệ.
3. Kết nối mục tiêu sản phẩm với mục tiêu Sprint, backlog và quyết định hằng ngày mà không đánh đồng chúng.
4. Làm rõ trách nhiệm cá nhân, trách nhiệm nhóm, quyền ra quyết định và sự phối hợp với người liên quan.
5. Sử dụng các thực hành Scrum, Kanban và XP để kiểm tra tiến triển chung, xử lý phụ thuộc và điều chỉnh kế hoạch khi có phản hồi.
6. Phân biệt **trách nhiệm đối với kết quả** với **đổ lỗi khi một chỉ số không đạt**, và xây dựng cách học từ kết quả ngoài dự kiến.
7. Thiết kế một buổi thống nhất mục tiêu, một nhịp kiểm tra kết quả và cơ chế giải quyết xung đột ưu tiên cho nhóm phần mềm.

## 1. Vì sao mục tiêu chung là nền tảng của cộng tác?

Một tập hợp người cùng tham gia dự án chưa chắc là một nhóm có mục tiêu chung. Nếu mỗi người chỉ biết nhiệm vụ được giao, việc phối hợp có thể dừng ở mức **bàn giao giữa các bộ phận**. Khi xuất hiện thay đổi, các thành viên dễ hỏi “phần này thuộc ai?” thay vì “làm sao để người dùng đạt được điều cần thiết?”.

Mục tiêu chung đóng vai trò **tiêu chí để ra quyết định**. Khi một API chậm, một user story quá lớn, một lỗi nghiêm trọng xuất hiện hoặc một stakeholder đề nghị thêm tính năng, nhóm có thể đánh giá: phương án nào giúp tiến gần mục tiêu nhất trong những ràng buộc hiện có?

| Khi thiếu mục tiêu chung | Khi có mục tiêu chung được hiểu và sử dụng |
|---|---|
| “Tôi đã hoàn tất ticket, phần còn lại không thuộc tôi.” | “Luồng quan trọng chưa hoạt động; tôi có thể hỗ trợ gỡ điểm chặn nào?” |
| Các bộ phận tranh luận ai chậm hơn | Nhóm xem phụ thuộc nào ngăn người dùng nhận giá trị |
| Ưu tiên theo yêu cầu mới nhất hoặc người có tiếng nói lớn nhất | Ưu tiên theo mục tiêu, bằng chứng, rủi ro và quyền quyết định đã rõ |
| Sprint Review chỉ kiểm tra số tính năng hoàn thành | Review kiểm tra Increment, điều đã học và lựa chọn tiếp theo |
| Kết quả không đạt thì tìm cá nhân để quy trách | Nhóm xem giả định, quyết định, năng lực và điều kiện hệ thống cần cải thiện |

**Mục tiêu chung không đòi hỏi mọi người đồng ý với mọi giải pháp.** Các thành viên có thể bất đồng về cách triển khai, mức rủi ro hoặc thứ tự công việc. Điều quan trọng là cùng hiểu vấn đề cần giải quyết và có cơ chế chọn phương án minh bạch.

### 1.1. Mục tiêu chung là “điểm quy chiếu”, không phải khẩu hiệu

Các câu như “trở thành đội xuất sắc”, “nâng cao trải nghiệm”, “đổi mới sáng tạo” có thể truyền cảm hứng nhưng chưa đủ để lựa chọn giữa hai yêu cầu mâu thuẫn.

Thử đối chiếu:

- **Khẩu hiệu:** “Cải thiện trải nghiệm học viên.”
- **Đầu ra cần giao:** “Xây trang onboarding mới với bốn màn hình.”
- **Mục tiêu chung có thể hành động:** “Giúp học viên mới đã đăng ký khóa tìm và bắt đầu bài học đầu tiên trong vòng bảy ngày dễ dàng hơn, đồng thời không tăng lỗi cấp quyền truy cập.”

Mục tiêu thứ ba làm rõ **ai**, **khả năng nào cần cải thiện** và **điều không được đánh đổi**. Nó vẫn cho nhóm quyền lựa chọn giải pháp: nút bắt đầu rõ hơn, bớt bước, sửa thông báo lỗi, tối ưu tải trang hoặc một cách khác có bằng chứng tốt hơn.

### 1.2. Phân biệt mục tiêu, hoạt động, đầu ra và kết quả

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| **Mục tiêu (goal)** | Chúng ta muốn thay đổi điều gì, vì sao? | Học viên mới tự bắt đầu học thuận lợi hơn |
| **Hoạt động (activity)** | Chúng ta đang làm gì? | Phỏng vấn người dùng, họp planning, viết kiểm thử |
| **Đầu ra (output)** | Chúng ta đã tạo hoặc giao thứ gì? | Increment có nút “Bắt đầu học”, API xác thực, tài liệu hỗ trợ |
| **Kết quả (outcome)** | Điều gì thực sự thay đổi cho người dùng? | Tỷ lệ tự hoàn thành bước bắt đầu học tăng, thời gian thao tác giảm |
| **Tác động dài hạn (impact)** | Giá trị rộng hơn có hình thành không? | Người học duy trì học tập tốt hơn, giảm chi phí hỗ trợ hợp lý |

Mục tiêu có thể mô tả **kết quả mong muốn**, nhưng không nên nhầm chính phát biểu mục tiêu với bằng chứng đã đạt. Một Increment hoàn tất theo Definition of Done (DoD) chứng minh năng lực đã được xây dựng đúng chuẩn; muốn biết người dùng nhận giá trị đến đâu vẫn phải kiểm tra kết quả sử dụng.

## 2. Đặc điểm của một mục tiêu chung hữu ích

Một mục tiêu phát huy tác dụng khi các thành viên có thể sử dụng nó để lựa chọn công việc và kiểm tra tiến triển. Không nhất thiết dùng một khuôn mẫu duy nhất; hãy bảo đảm các thành phần quan trọng sau.

### 2.1. Có đối tượng và vấn đề rõ ràng

“Tăng độ hài lòng” là quá rộng nếu không biết **ai** đang gặp vấn đề gì. Ví dụ: “người dùng mới trên điện thoại gặp khó khi xác minh email trong lần đăng ký đầu tiên” cho phép nhóm tìm bằng chứng và phân biệt khỏi vấn đề của người dùng đã có tài khoản.

Cần tránh giả định tất cả người dùng có trải nghiệm như nhau. Thiết bị, công nghệ hỗ trợ, loại tài khoản, điều kiện mạng và nhu cầu có thể tạo ra các trở ngại khác nhau.

### 2.2. Nói rõ kết quả mong muốn mà không khóa sớm giải pháp

“Xây chatbot” là một phương án; “giúp người dùng tự giải quyết những lỗi đăng nhập thông thường” là một kết quả mong muốn. Khi mục tiêu được viết dưới dạng giải pháp, mọi phản hồi trái chiều dễ bị bỏ qua vì nhóm vẫn tập trung bảo vệ ý tưởng ban đầu.

Một mục tiêu tốt có thể để ngỏ nhiều giải pháp nhưng vẫn đủ cụ thể để định hướng việc ưu tiên. Nếu đã có một đầu ra bắt buộc bởi pháp luật, hợp đồng hoặc an toàn, hãy nêu rõ đó là **ràng buộc**, không giả vờ rằng nhóm được tùy ý bỏ đi.

### 2.3. Có tín hiệu kiểm chứng và mốc xem lại

Đội cần thống nhất điều gì sẽ giúp biết mình tiến triển, ví dụ:

- Tỷ lệ người dùng hoàn tất tác vụ quan trọng.
- Thời gian thực hiện hoặc số lần phải thử lại.
- Tỷ lệ phải liên hệ hỗ trợ để hoàn thành.
- Phản hồi trực tiếp khi quan sát người dùng.
- Độ tin cậy của chức năng và số lỗi gây cản trở.

Mỗi tín hiệu phải có định nghĩa, phạm vi và thời điểm kiểm tra phù hợp. Nếu tỷ lệ kích hoạt đo trong bảy ngày, không nên kết luận từ một cohort mới đăng ký chưa đủ bảy ngày. Một con số còn phải đi kèm bối cảnh và các giới hạn suy luận.

### 2.4. Có các ràng buộc về chất lượng và an toàn

Nhóm không được “đạt mục tiêu” bằng cách đưa ra quyết định gây hại. Ví dụ, giảm thời gian đăng ký bằng cách bỏ kiểm tra quyền truy cập có thể làm chỉ số nhanh hơn nhưng tạo rủi ro bảo mật. Cần làm rõ **guardrail**: chất lượng, bảo mật, quyền riêng tư, khả năng tiếp cận, tính đúng đắn nghiệp vụ và các nghĩa vụ bắt buộc.

### 2.5. Trong vùng ảnh hưởng của nhóm, nhưng không hứa hẹn kết quả tuyệt đối

Một đội có thể trực tiếp chọn phương án phát triển, kiểm thử, cải tiến trải nghiệm và đo phản hồi; đội không điều khiển hoàn toàn hành vi của người dùng hoặc biến động thị trường.

Hãy tách:

1. **Cam kết về hành động và chất lượng:** nhóm kiểm soát tương đối trực tiếp, chẳng hạn tạo Increment đạt DoD, kiểm chứng một giả thuyết, theo dõi lỗi sau triển khai.
2. **Mục tiêu về kết quả người dùng:** nhóm hướng tới và có trách nhiệm theo dõi, học hỏi, điều chỉnh; mức đạt được có thể chịu ảnh hưởng của các yếu tố ngoài nhóm.

Trách nhiệm hướng kết quả đòi hỏi **minh bạch và phản ứng có trách nhiệm khi thực tế khác dự đoán**. Nó không đòi hỏi che giấu dữ liệu để chứng minh lời hứa ban đầu luôn đúng.

### 2.6. Đủ ngắn để mọi thành viên hiểu giống nhau

Mục tiêu quá dài, chứa nhiều đề tài không liên quan sẽ khó định hướng. Có thể dùng cấu trúc:

> **Trong** [bối cảnh và giai đoạn], **giúp** [nhóm người dùng] **đạt được** [hành vi/kết quả mong muốn], **được kiểm chứng qua** [một vài tín hiệu], **trong khi bảo vệ** [ràng buộc quan trọng].

Ví dụ:

> Trong giai đoạn cải thiện đăng ký, giúp học viên mới kích hoạt tài khoản và vào được bài đầu tiên dễ dàng hơn; kiểm tra tỷ lệ tự hoàn tất trong bảy ngày và lỗi xác minh; không làm giảm bảo mật hoặc khả năng truy cập.

Một mục tiêu như vậy nên được mọi người đọc và giải thích bằng từ ngữ của chính mình. Nếu mỗi bộ phận hiểu một ý khác nhau, nhóm cần làm rõ trước khi tạo thêm backlog item.

## 3. Kết nối mục tiêu ở các cấp độ mà không biến thành danh sách việc

Một tổ chức có thể có định hướng kinh doanh, mục tiêu sản phẩm và những mục tiêu ngắn hạn. Cần biết **mối liên hệ giữa chúng**, đồng thời tránh ép mọi cấp độ vào một công thức giống nhau.

### 3.1. Từ nhu cầu sản phẩm đến hành động hằng ngày

~~~mermaid
flowchart TD
    A["Nhu cầu và định hướng sản phẩm"] --> B["Mục tiêu sản phẩm"]
    B --> C["Ưu tiên trong Product Backlog"]
    C --> D["Mục tiêu Sprint hoặc mục tiêu luồng công việc"]
    D --> E["Lát cắt chức năng / backlog item"]
    E --> F["Công việc hằng ngày và kiểm thử"]
    F --> G["Increment / thay đổi đạt chất lượng"]
    G --> H["Phản hồi người dùng và kết quả quan sát"]
    H -. "Điều chỉnh giả định và ưu tiên" .-> B
    H -. "Điều chỉnh kế hoạch" .-> C
~~~

Sơ đồ cho thấy một đường liên kết **có chủ đích**, không phải cơ cấu quản lý bắt buộc. Phản hồi có thể đến từ bất cứ bước nào: nghiên cứu người dùng có thể làm thay đổi giả thuyết ngay trước khi code; lỗi tích hợp có thể làm thay đổi kế hoạch Sprint; sự cố sản xuất có thể làm ưu tiên dịch chuyển tức thời.

### 3.2. Trong Scrum: Product Goal, Sprint Goal và Definition of Done

Scrum cung cấp ba *commitment* gắn với ba artifact:

| Artifact | Commitment | Câu hỏi giúp liên kết mục tiêu |
|---|---|---|
| **Product Backlog** | **Product Goal** | Sản phẩm muốn tiến tới trạng thái tương lai nào có giá trị? |
| **Sprint Backlog** | **Sprint Goal** | Vì sao Sprint hiện tại có giá trị và chúng ta đang hướng tới kết quả chung nào? |
| **Increment** | **Definition of Done** | Phần mềm phải đạt tiêu chuẩn chất lượng nào trước khi được xem là hoàn tất? |

**Product Goal** định hướng dài hơn một Sprint. **Sprint Goal** là một mục tiêu chung của Sprint, giúp Developers linh hoạt điều chỉnh kế hoạch công việc trong khi vẫn giữ ý nghĩa Sprint. **Definition of Done** không phải mục tiêu kinh doanh; nó là cam kết về chất lượng của Increment.

Ví dụ:

| Cấp độ | Ví dụ |
|---|---|
| Mục tiêu sản phẩm | Người dùng mới có thể tự đăng ký và truy cập khóa học đã mua một cách đáng tin cậy |
| Mục tiêu Sprint | Người dùng mới có thể hoàn tất luồng xác minh email và mở khóa đã đăng ký trên môi trường tích hợp |
| Backlog item | Tạo và xác minh liên kết email; xử lý hết hạn; hiển thị trạng thái truy cập |
| Kế hoạch Developers | Hoàn thiện email service, tích hợp API, kiểm thử đầu-cuối, rà soát rủi ro bảo mật |
| DoD | Luồng tích hợp hoạt động, kiểm thử liên quan đạt, tiêu chuẩn bảo mật/chất lượng được đáp ứng |

Ví dụ trên mô tả mối liên kết. Trong Scrum thực tế, **Scrum Team xác định Sprint Goal trong Sprint Planning**, Developers lựa chọn và lập kế hoạch thực hiện công việc, còn Product Owner hỗ trợ làm rõ giá trị và ưu tiên. Không nên thay Sprint Goal bằng câu “hoàn thành 20 story point” hoặc danh sách ticket không có một lý do chung.

### 3.3. Trong Kanban: mục tiêu chung giúp điều chỉnh chính sách dòng công việc

Kanban không yêu cầu có Sprint Goal như Scrum. Đội vẫn cần định hướng về giá trị dịch vụ, kỳ vọng của khách hàng và cách công việc đi từ yêu cầu đến hoàn tất.

Ví dụ một nhóm hỗ trợ lỗi đặt mục tiêu giảm thời gian người dùng phải chờ lỗi nghiêm trọng được khắc phục. Nhóm có thể:

- Hiển thị rõ trạng thái của từng lỗi và những điểm đang bị chặn.
- Giới hạn công việc đang thực hiện (work in progress, WIP) theo khả năng thực tế.
- Ưu tiên hỗ trợ hoàn tất lỗi quan trọng thay vì mở thêm nhiều việc.
- Theo dõi work item age, cycle time và các loại lỗi cần xử lý.
- Kiểm tra việc thay đổi chính sách có thực sự cải thiện thời gian khắc phục và độ tin cậy không.

Giảm cycle time là dấu hiệu cải thiện dòng công việc; nó **chưa tự chứng minh** người dùng gặp ít sự cố hơn. Nhóm phải nối số đo quy trình với kết quả dịch vụ cần đạt.

### 3.4. Trong XP: mục tiêu phải được hỗ trợ bằng năng lực thay đổi phần mềm

Nếu đội muốn phản hồi sớm nhưng tích hợp phải chờ ba tuần, kiểm thử hoàn toàn thủ công hoặc mỗi lần sửa lỗi đều gây hồi quy, khả năng theo đuổi mục tiêu sẽ bị hạn chế. Các thực hành kỹ thuật như tích hợp liên tục, kiểm thử tự động phù hợp, refactoring, phát hành nhỏ và lập trình cặp khi cần giúp đội **tạo bằng chứng sớm và thích ứng an toàn**.

Mục tiêu chung giúp đội lựa chọn đầu tư kỹ thuật theo vấn đề đang cản trở giá trị: ví dụ “cần kiểm thử quyền truy cập đầu-cuối để có thể triển khai an toàn” thay vì “mọi người phải viết thêm thật nhiều test” mà không rõ mục đích.

## 4. Trách nhiệm chung và trách nhiệm riêng cần cùng tồn tại

Hai cực đoan thường gây hại:

- **Chỉ có trách nhiệm cá nhân:** mỗi người xong phần mình rồi dừng, không ai quan tâm luồng sử dụng chung.
- **Chỉ nói trách nhiệm tập thể:** mọi người “cùng chịu trách nhiệm” nhưng không rõ ai quyết định ưu tiên, ai hỗ trợ gỡ điểm chặn hoặc ai theo dõi kết quả.

Đội cần **trách nhiệm chung đối với giá trị và chất lượng của sản phẩm**, đi cùng **trách nhiệm cụ thể về quyết định và thực hiện**.

### 4.1. Phân biệt responsibility và accountability

Trong quản trị, hai từ có thể được dùng khác nhau giữa các tổ chức. Để tránh tranh luận thuật ngữ, bài này dùng:

- **Responsibility (trách nhiệm thực hiện):** ai trực tiếp tổ chức hoặc thực hiện một phần việc; việc gì cần được hoàn thành và theo tiêu chuẩn nào.
- **Accountability (trách nhiệm giải trình về kết quả/quyết định):** ai cần đứng ra làm rõ điều đã xảy ra, chịu trách nhiệm cho quyết định trong phạm vi quyền hạn, trình bày bằng chứng và điều chỉnh khi cần.
- **Shared accountability (trách nhiệm giải trình chung):** mọi người cùng quan tâm kết quả toàn hệ thống, chủ động phối hợp và không đẩy vấn đề qua ranh giới chức năng.

Điều đó **không có nghĩa** mọi người có cùng quyền phê duyệt hoặc phải chịu trách nhiệm như nhau với những điều nằm ngoài quyền kiểm soát. Người chịu trách nhiệm về giá trị và người chịu trách nhiệm về kiến trúc/triển khai có vai trò khác nhau nhưng cần cùng hướng đến mục tiêu chung.

### 4.2. Vai trò và trách nhiệm trong Scrum

Scrum định nghĩa một Scrum Team bao gồm Product Owner, Scrum Master và Developers. Mỗi accountability có ý nghĩa riêng:

| Accountability | Trách nhiệm trọng tâm theo Scrum | Đóng góp vào mục tiêu chung |
|---|---|---|
| **Scrum Team** | Chịu trách nhiệm tạo ra Increment có giá trị, hữu ích ở mỗi Sprint và quản lý các hoạt động liên quan đến sản phẩm | Cùng hướng tới Product Goal, kiểm tra tiến triển và thích ứng |
| **Product Owner** | Chịu trách nhiệm tối đa hóa giá trị sản phẩm tạo ra từ công việc của Scrum Team và quản lý Product Backlog hiệu quả | Làm rõ Product Goal, giao tiếp các quyết định ưu tiên, cân nhắc giá trị và phản hồi |
| **Developers** | Chịu trách nhiệm tạo bất kỳ khía cạnh nào của Increment có thể dùng được mỗi Sprint; lập kế hoạch Sprint, bảo đảm chất lượng và điều chỉnh kế hoạch | Phối hợp liên chức năng để tạo Increment đạt DoD, xử lý phụ thuộc và giữ tiến độ thực tế |
| **Scrum Master** | Chịu trách nhiệm về hiệu quả của Scrum Team; giúp nhóm và tổ chức hiểu, thực hành Scrum | Huấn luyện cách hợp tác, nâng chất lượng thực nghiệm, giúp tháo trở ngại trong phạm vi phù hợp |

Stakeholders, người dùng, chuyên gia bảo mật, pháp lý và vận hành có thể cung cấp thông tin, điều kiện hoặc quyết định thuộc thẩm quyền của họ. **Product Owner không phải người duy nhất làm mọi công việc liên quan giá trị**, và Scrum Master không phải người quản lý giao task cho Developers.

Scrum Team **tự quản lý**: nội bộ đội quyết định ai làm gì, khi nào và bằng cách nào trong giới hạn đã thống nhất. Tự quản lý đi cùng trách nhiệm minh bạch, sự phối hợp và tuân thủ các yêu cầu chất lượng phù hợp; nó không có nghĩa bỏ qua vai trò, quyền quyết định hoặc các ràng buộc của tổ chức.

### 4.3. Một bản đồ quyền quyết định đơn giản

Trong những tổ chức không sử dụng Scrum hoặc có nhiều đội phụ thuộc, hãy ghi rõ quyền quyết định cho những vấn đề lặp lại. Có thể dùng bảng minh họa:

| Quyết định | Ai chịu trách nhiệm ra quyết định? | Ai đóng góp bằng chứng? | Ranh giới |
|---|---|---|---|
| Xác định và sắp thứ tự ưu tiên trong Product Backlog | Product Owner nếu làm theo Scrum | Người dùng, stakeholders, Developers, chuyên gia domain | Product Goal, ngân sách và nghĩa vụ liên quan |
| Chọn cách kỹ thuật để đạt Sprint Goal | Developers | Product Owner, chuyên gia kiến trúc/bảo mật khi cần | DoD, tiêu chuẩn kỹ thuật, ràng buộc an toàn |
| Điều chỉnh kế hoạch trong ngày | Developers | Thành viên đang xử lý công việc, người hỗ trợ | Sprint Goal và chính sách làm việc |
| Thay đổi một chính sách WIP của dịch vụ | Nhóm vận hành dòng công việc theo cơ chế đã thống nhất | Dữ liệu flow, người nhận dịch vụ, người quản lý phụ thuộc | Năng lực, mức ưu tiên khẩn cấp, chất lượng |
| Chấp nhận rủi ro pháp lý vượt thẩm quyền nhóm | Vai trò được tổ chức trao thẩm quyền phù hợp | Chuyên gia pháp lý, bảo mật, Product Owner, kỹ sư | Luật, hợp đồng và kiểm soát bắt buộc |

Bảng trên là **cách thiết kế cơ chế phối hợp minh họa**, không phải quy tắc bắt buộc của Scrum hay một mô hình phân quyền áp dụng mọi tổ chức. Nếu quyền quyết định không đủ rõ, hãy làm rõ cùng người có thẩm quyền trước khi có xung đột.

### 4.4. Trách nhiệm chung không phải “cùng làm hết mọi việc”

Một kỹ sư frontend không nhất thiết phải tự viết hệ thống gửi email; một chuyên gia kiểm thử không nhất thiết quyết định ưu tiên sản phẩm. Nhưng mọi người cùng cần quan tâm **luồng người dùng đã hoạt động xuyên suốt chưa**.

Khi email xác minh bị chặn:

1. Thành viên nhận thấy vấn đề đưa bằng chứng lên bảng công việc hoặc trao đổi trực tiếp.
2. Những người có chuyên môn liên quan phối hợp gỡ chặn, thay đổi kế hoạch nếu phù hợp.
3. Product Owner cùng đội xem ảnh hưởng đến giá trị và ưu tiên.
4. Nếu cần quyết định vượt thẩm quyền, nhóm chỉ rõ người có quyền quyết định và thời hạn phản hồi.
5. Cả đội kiểm tra lại khả năng người dùng hoàn tất luồng, không chỉ đóng ticket của bộ phận email.

Hành vi này thể hiện **ownership chung đối với kết quả**, trong khi phần việc và quyết định cụ thể vẫn có người chịu trách nhiệm.

## 5. Lãnh đạo Agile tạo điều kiện để nhóm sở hữu mục tiêu

Lãnh đạo trong Agile không chỉ là đặt mục tiêu rồi giao cho đội thực hiện. Người lãnh đạo cần tạo điều kiện để **thông tin, quyền ra quyết định, năng lực và trách nhiệm** đi cùng nhau.

### 5.1. Làm rõ “tại sao” và ranh giới, cho đội quyền chọn “bằng cách nào”

Giả sử mục tiêu là giảm số học viên không thể truy cập khóa đã thanh toán. Người quản lý có thể nêu vấn đề, mức độ ưu tiên và ràng buộc, đồng thời để nhóm chuyên môn đánh giá giải pháp: sửa lỗi phân quyền, thay đổi quy trình đồng bộ thanh toán hay cải thiện trạng thái chờ.

Trao quyền hiệu quả cần:

- Mục tiêu có ý nghĩa và bối cảnh nghiệp vụ được chia sẻ.
- Quyền quyết định phù hợp với chuyên môn và trách nhiệm.
- Dữ liệu, người dùng, môi trường kiểm thử và công cụ cần thiết.
- Ranh giới an toàn, pháp lý, ngân sách hoặc kiến trúc được làm rõ.
- Kênh hỗ trợ khi nhóm vướng phụ thuộc vượt khả năng tự giải quyết.

Nếu đội bị yêu cầu chịu trách nhiệm về outcome nhưng không được đổi backlog, không gặp người dùng và không thể quyết định kỹ thuật, quyền hạn không tương xứng với trách nhiệm.

### 5.2. Khuyến khích nêu sự thật, kể cả tin xấu

Một mục tiêu chung vô dụng nếu không ai dám nói rằng giả thuyết đã sai hoặc tiến độ đang chậm. Lãnh đạo cần tạo môi trường mà thành viên có thể báo lỗi, nêu rủi ro và bất đồng trên cơ sở bằng chứng mà không sợ bị làm nhục hoặc trừng phạt tùy tiện.

Ví dụ: khi phát hiện thiết kế mới khiến người dùng dùng trình đọc màn hình gặp khó khăn, thông tin đó nên được xem là **bằng chứng quan trọng để điều chỉnh**, không phải sự thất bại cá nhân cần che giấu.

**An toàn tâm lý không đồng nghĩa thiếu trách nhiệm.** Nhóm vẫn cần kiểm tra chất lượng, giải trình quyết định, sửa lỗi và giữ những cam kết đã thống nhất. Khác biệt nằm ở cách xử lý: tìm nguyên nhân hệ thống và hành động sửa chữa thay vì tạo động lực giấu vấn đề.

### 5.3. Tránh vi quản lý và tránh bỏ mặc

| Vi quản lý | Trao quyền có hỗ trợ | Bỏ mặc |
|---|---|---|
| Lãnh đạo quyết định từng ticket và kỹ thuật | Lãnh đạo làm rõ mục tiêu, ranh giới và hỗ trợ gỡ phụ thuộc | Chỉ giao chỉ số rồi yêu cầu tự xoay xở |
| Chỉ hỏi ai làm chậm | Hỏi phần nào đang cản mục tiêu và cần hỗ trợ gì | Không kiểm tra tiến triển hoặc rủi ro |
| Phạt khi dự báo thay đổi | Đòi hỏi dự báo minh bạch và cập nhật khi có dữ liệu mới | Không có cơ chế ra quyết định khi bất định tăng |

Lãnh đạo phục vụ (servant leadership) thường được nhắc tới trong bối cảnh Agile: tập trung giúp người khác làm việc hiệu quả hơn, tháo cản trở và phát triển năng lực. Tên gọi không quan trọng bằng các hành vi quan sát được. Người lãnh đạo vẫn có thể cần đưa ra các quyết định khó khi lợi ích, nguồn lực hoặc an toàn xung đột.

## 6. Cách xây dựng mục tiêu chung cùng nhóm

Mục tiêu được “công bố” từ trên xuống có thể là định hướng cần thiết, nhưng để trở thành **điểm quy chiếu thực sự**, nhóm cần có cơ hội làm rõ, thách thức giả định và thống nhất cách dùng nó.

### 6.1. Quy trình sáu bước

**Bước 1 — Bắt đầu từ vấn đề và bằng chứng hiện có.**

Thu thập tiếng nói người dùng, sự cố, dữ liệu hành vi, yêu cầu kinh doanh và bối cảnh vận hành. Nêu rõ dữ liệu nào đáng tin, dữ liệu nào mới là giả định. Không cần có mọi đáp án ngay từ đầu.

**Bước 2 — Xác định đối tượng và thay đổi mong muốn.**

Chọn người dùng hoặc luồng dịch vụ cụ thể. Ví dụ: “Học viên mua khóa trên điện thoại có thể vào được bài đầu tiên mà không liên hệ hỗ trợ”.

**Bước 3 — Làm rõ ràng buộc và những điểm được phép thay đổi.**

Ghi ra điều không thể thương lượng: luật, bảo mật, DoD, hợp đồng, ngày cần đáp ứng yêu cầu bắt buộc. Phân biệt với những thứ đội được điều chỉnh: cách làm, mức chi tiết, thứ tự hạng mục, phương án triển khai.

**Bước 4 — Viết phát biểu mục tiêu, chọn tín hiệu và giả thuyết.**

Ghi một mục tiêu ngắn, một hoặc vài chỉ số có định nghĩa, nguồn đo và mốc xem lại. Dùng baseline nếu có; nếu chưa có, nêu kế hoạch đo baseline trước khi đặt ngưỡng.

**Bước 5 — Cùng lập bản đồ phụ thuộc và quyền quyết định.**

Xác định các công việc liên chức năng cần hoàn tất, ai có thể quyết định, ai cần được tham vấn và điểm chặn nào vượt phạm vi đội.

**Bước 6 — Chọn bước nhỏ để kiểm chứng, sau đó kiểm tra lại.**

Đưa một lát cắt tạo giá trị vào backlog hoặc chính sách dòng công việc, xác định chất lượng cần đạt và cách nhận phản hồi. Khi có dữ liệu mới, nhóm thống nhất lựa chọn tiếp theo.

### 6.2. Mẫu mục tiêu và cam kết nhóm

~~~text
NGƯỜI DÙNG / BỐI CẢNH:
  [Ai? Đang cần hoàn thành việc gì?]

MỤC TIÊU CHUNG:
  [Thay đổi có ích nào chúng ta muốn tạo ra?]

VÌ SAO QUAN TRỌNG:
  [Bằng chứng của vấn đề, giá trị với người dùng và tổ chức]

KẾT QUẢ CẦN THEO DÕI:
  [Chỉ số, định nghĩa, nguồn dữ liệu, baseline, thời điểm xem lại]

RÀNG BUỘC / GUARDRAIL:
  [Bảo mật, chất lượng, pháp lý, khả năng tiếp cận, ngân sách...]

PHẠM VI TỰ CHỦ:
  [Quyết định nào đội được tự đưa ra? Điều gì cần tham vấn?]

LÁT CẮT ĐẦU TIÊN:
  [Increment hoặc thử nghiệm nhỏ có thể kiểm chứng]

TRÁCH NHIỆM:
  [Người quyết định giá trị, người tạo Increment,
   người hỗ trợ phụ thuộc và người tổng hợp phản hồi]

MỐC ĐÁNH GIÁ:
  [Khi nào xem dữ liệu và chọn bước tiếp theo?]

NẾU GIẢ THUYẾT SAI:
  [Nhóm sẽ điều chỉnh hoặc kiểm chứng điều gì tiếp?]
~~~

Mẫu này nhằm giúp các bên hiểu giống nhau; không cần biến thành biểu mẫu dài bắt buộc trong mọi cuộc họp. Với một thay đổi nhỏ, một đoạn mô tả trong Product Backlog có thể là đủ.

### 6.3. Kiểm tra xem mục tiêu đã thực sự “chung” chưa

Sau khi thống nhất, hãy hỏi ngẫu nhiên từng vai trò:

1. Người dùng cần đạt điều gì?
2. Thay đổi tiếp theo của chúng ta phục vụ mục tiêu đó như thế nào?
3. Nếu xuất hiện yêu cầu gấp không liên quan mục tiêu, ai quyết định thứ tự ưu tiên?
4. Chất lượng hoặc nghĩa vụ nào không được đánh đổi?
5. Nếu dữ liệu không cải thiện, nhóm sẽ học hoặc thử điều gì?

Nếu các câu trả lời mâu thuẫn, cần làm rõ mục tiêu hoặc quyền quyết định. “Mọi người đã nghe trình bày” không đồng nghĩa “mọi người đã thống nhất cách dùng mục tiêu”.

## 7. Phối hợp hằng ngày theo mục tiêu thay vì theo phần việc riêng

Một mục tiêu chung chỉ có tác dụng khi nó xuất hiện trong **lựa chọn công việc mỗi ngày**. Nếu mục tiêu chỉ nằm trên slide mở đầu quý, nhóm sẽ quay lại cách tối ưu ticket cá nhân.

### 7.1. Trong Sprint Planning

Trước khi hỏi “đội làm được bao nhiêu story point?”, Scrum Team nên làm rõ:

- Vì sao Sprint sắp tới có giá trị?
- Chúng ta muốn đạt Sprint Goal nào có ý nghĩa?
- Backlog item nào góp phần vào mục tiêu và điều nào tạo phụ thuộc?
- Các rủi ro kỹ thuật/chất lượng nào có thể làm mục tiêu thất bại?
- Developers có thể dự báo làm được phần nào và tổ chức công việc ra sao?

Một danh sách việc đầy kín năng lực nhưng không có Sprint Goal có thể tạo nhiều đầu ra rời rạc và ít khả năng điều chỉnh khi thực tế thay đổi.

### 7.2. Trong Daily Scrum

Daily Scrum phục vụ Developers kiểm tra tiến triển tới Sprint Goal và điều chỉnh Sprint Backlog khi cần. Nó không bắt buộc ba câu hỏi cố định hay là buổi báo cáo cá nhân cho quản lý.

Ví dụ, nhóm có Sprint Goal: “Học viên mới có thể xác minh email và truy cập khóa học”. Khi phát hiện email gửi chậm, câu hỏi hữu ích là: “Điều đó ảnh hưởng mục tiêu thế nào? Ai hỗ trợ kiểm tra, chúng ta đổi kế hoạch hôm nay ra sao?”.

Một câu hỏi yếu hơn là: “Hôm qua mỗi người đã hoàn thành mấy task?”. Thông tin task có thể hữu ích, nhưng chỉ khi giúp nhóm quyết định hành động tiếp theo.

### 7.3. Trong Sprint Review

Sprint Review không chỉ trình diễn những gì đã làm. Scrum Team và stakeholders cùng kiểm tra kết quả Sprint, bối cảnh sản phẩm và tiến triển tới Product Goal. Nhóm có thể mang đến:

- Increment thực sự đạt DoD và có thể kiểm tra.
- Phần nào của mục tiêu đã được hỗ trợ bởi phần mềm mới.
- Dữ liệu phản hồi và điều chưa thể kết luận.
- Rủi ro, cơ hội và thay đổi trong môi trường sử dụng.
- Đề xuất điều chỉnh Product Backlog hoặc phương án kiểm chứng tiếp theo.

Không phải Sprint nào cũng đủ thời gian cho một outcome dài hạn xuất hiện. Điều cần thiết là **trình bày bằng chứng đúng mức** thay vì tuyên bố chắc chắn từ một lần demo.

### 7.4. Trong Sprint Retrospective

Retrospective tập trung tăng chất lượng và hiệu quả. Một mục tiêu chung cho phép xem lại không chỉ “ai đã giao tiếp thiếu tốt” mà còn **cơ chế phối hợp nào làm dòng giá trị chậm**.

Ví dụ: hai Sprint liên tiếp luồng đăng ký bị kẹt ở kiểm thử tích hợp. Nhóm thử chính sách “hợp đồng API phải có ví dụ đầu vào/đầu ra được hai phía xác nhận trước khi triển khai”, có người theo dõi và kiểm tra số lần làm lại ở Sprint sau.

### 7.5. Trong hệ thống Kanban

Nhóm có thể dùng một buổi ngắn để nhìn bảng công việc và hỏi: “Việc nào gần hoàn tất nhưng bị chặn? Việc nào đã tồn tại quá lâu? Nếu mở việc mới, mục tiêu dịch vụ có đến người dùng nhanh hơn không?”.

Các quyết định ưu tiên giúp **hoàn tất công việc có giá trị** thay vì chỉ giữ mọi người luôn bận. Giới hạn WIP nên là chính sách được thử và điều chỉnh dựa trên dữ liệu, không phải con số áp cứng cho mọi loại công việc.

## 8. Xử lý phụ thuộc và xung đột ưu tiên

Mục tiêu chung không xóa bỏ phụ thuộc giữa hệ thống hoặc giữa các đội. Nó giúp các bên hiểu vì sao phụ thuộc cần được giải quyết và cái giá của việc chậm trễ.

### 8.1. Bản đồ phụ thuộc theo luồng người dùng

Giả sử tính năng đăng ký cần các hệ thống:

~~~mermaid
flowchart LR
    A["Người dùng đăng ký"] --> B["Dịch vụ tài khoản"]
    B --> C["Dịch vụ gửi email"]
    C --> D["Xác minh tài khoản"]
    D --> E["Cấp quyền khóa học"]
    E --> F["Người dùng bắt đầu học"]
~~~

Nếu dịch vụ email đang tắc, luồng người dùng không hoàn tất dù frontend và backend mỗi bên đã “Done”. Bản đồ phụ thuộc giúp nhóm nêu rõ:

- Khả năng người dùng bị ảnh hưởng.
- Người đang sở hữu phần việc hoặc dịch vụ liên quan.
- Quyết định cần đưa ra và hạn cuối theo tác động thực tế.
- Phương án khác nếu phụ thuộc không được giải quyết đúng dự báo.
- Rủi ro về chất lượng khi chọn phương án thay thế.

### 8.2. Quy tắc xử lý bất đồng

Khi hai yêu cầu cạnh tranh, nhóm có thể dùng trình tự:

1. **Nhắc lại mục tiêu:** yêu cầu nào phục vụ đối tượng và vấn đề đang ưu tiên?
2. **Đặt bằng chứng lên bàn:** tác động người dùng, dữ liệu lỗi, mức độ không chắc chắn, chi phí chậm trễ và phụ thuộc.
3. **Làm rõ ràng buộc:** sự cố nghiêm trọng, nghĩa vụ pháp lý, chất lượng hoặc hợp đồng nào phải xử lý trước?
4. **So sánh các lựa chọn:** làm ngay, hoãn, giảm phạm vi, thử một lát cắt, tách luồng khẩn cấp.
5. **Xác định người có quyền quyết định:** tránh mọi người tranh luận vô hạn nhưng không ai có thẩm quyền kết luận.
6. **Ghi lại lý do và thời điểm xem lại:** nếu giả định thay đổi, có thể điều chỉnh mà không tranh luận lại từ đầu.

Không cần sự đồng thuận tuyệt đối cho mọi quyết định. Cần một quyết định minh bạch, có người chịu trách nhiệm và có khả năng kiểm tra.

### 8.3. Khi có nhiều mục tiêu xung đột

Một sản phẩm vừa muốn tăng tỷ lệ đăng ký, vừa giảm lỗi bảo mật, vừa tiết kiệm chi phí. Các mục tiêu có thể cạnh tranh. Không nên giải quyết bằng khẩu hiệu “tất cả đều ưu tiên số một”.

Hãy xác định **mục tiêu dẫn hướng** trong giai đoạn đang xét, các **guardrail bắt buộc** và điều gì có thể thương lượng. Khi xuất hiện rủi ro nghiêm trọng, thứ tự ưu tiên phải được đánh giá lại bởi đúng người có thẩm quyền. Mục tiêu chung là phương tiện ra quyết định trong bối cảnh thực, không phải lý do bỏ qua nghĩa vụ an toàn.

## 9. Đo trách nhiệm đối với kết quả mà không tạo hành vi đối phó

“Trách nhiệm với kết quả” dễ bị hiểu thành “thưởng hoặc phạt đội chỉ bằng một con số”. Điều đó khiến các thành viên cố tối ưu chỉ số bề mặt, che giấu dữ liệu xấu hoặc tránh nhận công việc rủi ro.

### 9.1. Kết hợp ba lớp tín hiệu

| Lớp | Câu hỏi | Ví dụ đo | Quyết định hỗ trợ |
|---|---|---|---|
| **Kết quả người dùng** | Người dùng có làm tốt hơn việc quan trọng không? | Tỷ lệ hoàn tất tác vụ, thời gian đạt giá trị đầu tiên, số lần cần hỗ trợ | Tiếp tục, thay đổi hoặc dừng giả thuyết sản phẩm |
| **Năng lực giao hàng và dòng công việc** | Nhóm có đưa các Increment đạt chất lượng đến phản hồi đủ nhanh không? | Increment đạt DoD, cycle time, WIP, work item age, throughput | Tháo tắc nghẽn, giảm WIP, chia nhỏ công việc, tăng khả năng dự báo |
| **Chất lượng, an toàn và tính bền vững** | Đội có đang tạo tác dụng phụ hoặc đẩy nợ sang tương lai không? | Sự cố, lỗi hồi quy, khả năng truy cập, thời gian khôi phục, phản hồi về tải công việc | Dừng phát hành, sửa rủi ro, đầu tư vào kỹ thuật hoặc cách phối hợp |

Đo lường không nên biến thành bảng xếp hạng cá nhân. Một kỹ sư không trực tiếp kiểm soát tỷ lệ chuyển đổi; số story point của hai đội không nhất thiết tương đương; cycle time phụ thuộc loại việc và điểm bắt đầu/kết thúc được định nghĩa.

### 9.2. Tách mục tiêu kỳ vọng và kết quả quan sát

Giả sử đội đặt mục tiêu nâng tỷ lệ học viên kích hoạt tài khoản trong bảy ngày từ 40% lên 50%. Sau một bản phát hành, tỷ lệ quan sát là 46%.

- **Mục tiêu:** 50% — mức đội mong muốn hướng tới trong giai đoạn này.
- **Đầu ra:** Increment hướng dẫn xác minh đã được triển khai và đạt DoD.
- **Kết quả quan sát:** 46% trong nhóm đo được.
- **Câu hỏi tiếp theo:** Dữ liệu có đủ tin cậy và các nhóm người dùng có tương đương không? Có vấn đề nào chưa giải quyết? Cần làm gì tiếp?

Các con số trên chỉ là **ví dụ giả định**. Tăng từ 40% lên 46% là **6 điểm phần trăm**, nhưng chưa chứng minh tính năng mới gây ra toàn bộ mức tăng nếu môi trường sử dụng hoặc nhóm người dùng đồng thời thay đổi.

Đội có thể chịu trách nhiệm cho việc đo đúng, công khai bất định và điều chỉnh quyết định, dù kết quả chưa đạt 50%.

### 9.3. Trách nhiệm đối với quy trình ra quyết định

Khi outcome chưa đạt, một câu hỏi hữu ích hơn “ai phải chịu lỗi?” là:

- Giả thuyết ban đầu là gì và dựa vào bằng chứng nào?
- Đội có đủ quyền và dữ liệu để lựa chọn giải pháp không?
- Phần mềm có thực sự đạt chuẩn chất lượng và được dùng đúng nhóm đối tượng không?
- Có yếu tố nào ngoài dự kiến, như hành vi người dùng, mùa vụ hoặc hệ thống phụ thuộc?
- Điều gì đã được phát hiện sớm, điều gì chỉ phát hiện muộn và vì sao?
- Ai sẽ làm rõ lựa chọn tiếp theo và khi nào kiểm tra lại?

Đây là **trách nhiệm giải trình hướng học tập**. Nó vẫn có thể dẫn đến việc điều chỉnh vai trò, sửa quy trình hoặc đánh giá quyết định sai có thể phòng tránh; nhưng không đồng nhất mọi kết quả không đạt với sai phạm của một cá nhân.

### 9.4. Đừng dùng velocity như mục tiêu kết quả

Velocity (nếu nhóm Scrum dùng story point) có thể hỗ trợ dự báo nội bộ theo cách ước lượng riêng của nhóm. Nó **không đo giá trị người dùng**, không phải bằng chứng chất lượng và không phù hợp để so sánh năng suất giữa những đội có cách chia việc khác nhau.

Một nhóm hoàn thành ít story point hơn vì ưu tiên sửa lỗi bảo mật ngăn người dùng mất tài khoản vẫn có thể tạo giá trị rất cao. Hãy xem **mục tiêu chung, chất lượng Increment và kết quả người dùng** trước khi kết luận tiến triển.

## 10. Tình huống xuyên suốt: khi mỗi bộ phận đều “hoàn thành”

> **Tình huống giả định phục vụ học tập.** Các tỷ lệ và thời gian dưới đây dùng để minh họa cách phối hợp và ra quyết định; không phải số liệu thực nghiệm hay tiêu chuẩn ngành.

Một nền tảng bán khóa học ghi nhận trong một giai đoạn có 1.000 người mới đăng ký; 400 người xác minh email và vào được trang khóa học trong bảy ngày, tương ứng **40%**. Bộ phận sản phẩm đề xuất bốn chức năng: màn hình chào mừng, hướng dẫn tương tác, email nhắc lại và chatbot trợ giúp.

### 10.1. Khi không có mục tiêu chung

Các bộ phận nhận KPI riêng:

- Frontend: hoàn tất bốn màn hình.
- Backend: giao đủ API.
- QA: đóng các lỗi thuộc phạm vi kiểm thử đã nhận.
- Product Owner: đạt 100% danh sách backlog được duyệt.
- Vận hành: giữ tỷ lệ triển khai thành công.

Đến cuối giai đoạn, mọi KPI riêng đều “xanh”. Nhưng nhóm phát hiện email xác minh có thể đến trễ, gây hết hạn liên kết; học viên không hoàn thành đăng ký. Khi phản hồi xuất hiện, mỗi bộ phận chỉ ra rằng ticket của mình đã đóng đúng yêu cầu.

**Gốc vấn đề:** Đội chưa có một mục tiêu xuyên suốt luồng người dùng, chưa ai chủ động tập hợp dữ liệu kết quả, và các ranh giới trách nhiệm làm cho điểm chặn chung ít được ưu tiên.

### 10.2. Cùng xây dựng mục tiêu

Scrum Team cùng stakeholders làm rõ:

> **Mục tiêu sản phẩm cho giai đoạn cải thiện:** giúp học viên mới xác minh tài khoản và truy cập khóa học đã đăng ký thuận lợi hơn; hướng tới tăng tỷ lệ hoàn tất luồng trong bảy ngày từ mức quan sát 40% lên khoảng 50%, không làm giảm bảo mật và khả năng truy cập.

Đội thống nhất:

| Nội dung | Thỏa thuận minh họa |
|---|---|
| Đối tượng | Học viên mới có đăng ký hợp lệ |
| Luồng quan trọng | Đăng ký → nhận email → xác minh → vào đúng khóa học |
| Baseline | 400/1.000 = 40% trong cohort đủ thời gian quan sát |
| Mục tiêu kết quả | Hướng tới khoảng 50% trong giai đoạn thử nghiệm |
| Guardrail | Không lộ thông tin tài khoản; không tăng lỗi cấp quyền; khả năng truy cập không bị suy giảm |
| Phạm vi linh hoạt | Có thể thay đổi thứ tự giải pháp, loại bỏ tính năng chưa cần thiết |
| Quyền quyết định | Product Owner quản lý ưu tiên; Developers quyết định cách triển khai; chuyên gia bảo mật quyết định/cho ý kiến theo cơ chế thẩm quyền của tổ chức |
| Mốc xem lại | Kiểm tra Increment và phản hồi trong Sprint Review; theo dõi cohort đủ bảy ngày khi có dữ liệu |

Không phải ai cũng có quyền đổi Product Backlog một cách độc lập. Nhưng mọi người có thể chủ động cung cấp bằng chứng, phát hiện rủi ro và đề xuất điều chỉnh.

### 10.3. Chọn một lát cắt để kiểm chứng

Qua quan sát, đội nhận thấy nhiều người bấm lại liên kết đã hết hạn mà không biết cách yêu cầu email mới. Thay vì bắt đầu cả chatbot và màn hình chào mừng, nhóm đưa một lát cắt nhỏ vào Sprint:

**Sprint Goal minh họa:** “Người học có thể khôi phục quá trình xác minh tài khoản khi liên kết cũ hết hạn mà không cần liên hệ hỗ trợ”.

Developers chia việc theo luồng:

1. Làm rõ trạng thái liên kết hết hạn.
2. Cho phép yêu cầu liên kết mới với giới hạn bảo mật phù hợp.
3. Gửi email, cập nhật trạng thái và tích hợp quyền truy cập.
4. Kiểm thử trường hợp thành công, lỗi, liên kết đã dùng và yêu cầu lặp lại.
5. Tạo Increment đạt DoD và có thể kiểm tra.

Khi dịch vụ gửi email chậm, người phụ trách giao diện chủ động hỗ trợ tái hiện lỗi và kiểm tra end-to-end, thay vì mở ngay màn hình mới không liên quan. Cách làm đó giúp nhóm hoàn tất **luồng có giá trị**, ngay cả khi có thành viên làm ít ticket mang tên chuyên môn của mình hơn dự kiến.

### 10.4. Sử dụng dữ liệu để ra quyết định

Giả sử cohort đủ điều kiện ở giai đoạn sau có 1.100 học viên, trong đó 506 người hoàn tất luồng trong bảy ngày:

\[
\text{Tỷ lệ hoàn tất} = \frac{506}{1.100}\times 100\% = 46\%
\]

So với baseline 40%, tỷ lệ **quan sát** tăng 6 điểm phần trăm. Đội **chưa đạt** mục tiêu minh họa 50%, nhưng có tín hiệu đáng quan tâm.

Trong Sprint Review, Product Owner và stakeholders:

- Kiểm tra chất lượng và điều kiện phát hành của Increment đã hoàn tất.
- Xem dữ liệu theo nhóm sử dụng điện thoại/máy tính và thời gian gửi email.
- Kiểm tra có chiến dịch truyền thông hoặc thay đổi dữ liệu nào trùng giai đoạn hay không.
- Nghe phản hồi của người dùng vẫn mắc ở bước xác minh.
- Ưu tiên sửa thời gian gửi email và cách thông báo trạng thái trước khi xây chatbot.

Không ai cần báo cáo “thất bại” chỉ vì outcome chưa đạt mục tiêu ngay lần đầu. Nhưng cả đội phải làm rõ **đã học được gì, lựa chọn nào thay đổi và ai sẽ thực hiện bước tiếp theo**.

### 10.5. So sánh hai cách quản trị

| Câu hỏi | Tối ưu theo bộ phận | Cùng sở hữu mục tiêu |
|---|---|---|
| Thành công là gì? | Mỗi nhóm đóng hết ticket của mình | Người học hoàn tất luồng dễ hơn, phần mềm đạt chất lượng |
| Khi email chậm | “Đó là việc của backend/nhà cung cấp.” | Xác định ảnh hưởng lên mục tiêu, cùng tháo chặn và điều chỉnh ưu tiên |
| Khi phát hiện giả thuyết sai | Vẫn làm hết danh sách ban đầu | Xem lại giải pháp và Product Backlog |
| Khi chỉ số chưa đạt | Tìm bộ phận gây chậm | Kiểm tra bằng chứng, quyền quyết định, giả định và hướng khắc phục |
| Công việc kỹ thuật | Cố tối đa hóa ticket từng chuyên môn | Tạo Increment chạy được xuyên suốt với DoD đáng tin |
| Vai trò lãnh đạo | Theo dõi số việc từng người hoàn thành | Làm rõ mục tiêu, giới hạn và giúp đội đủ điều kiện phối hợp |

## 11. Một buổi thống nhất mục tiêu chung có thể tổ chức như thế nào?

Đây là **kịch bản minh họa khoảng 75 phút** cho một nhóm phát triển sản phẩm. Có thể rút ngắn hoặc kéo dài theo phạm vi và mức độ bất định; không phải một sự kiện bắt buộc của Scrum.

| Khoảng thời gian | Hoạt động | Sản phẩm của phần trao đổi |
|---|---|---|
| 0–10 phút | Nêu vấn đề người dùng, tác động và những bằng chứng đang có | Một vấn đề chung được hiểu |
| 10–25 phút | Lắng nghe các góc nhìn: sản phẩm, phát triển, kiểm thử, vận hành, khách hàng | Giả định và trở ngại quan trọng |
| 25–40 phút | Soạn phát biểu mục tiêu; xác định đối tượng và phạm vi | Một mục tiêu ngắn, dễ giải thích |
| 40–50 phút | Chọn chỉ số kết quả, nguồn dữ liệu, baseline dự kiến và guardrail | Cách biết khi nào tiến triển hoặc gặp rủi ro |
| 50–60 phút | Làm rõ quyền quyết định, phụ thuộc và lựa chọn cần tham vấn | Bản đồ trách nhiệm có thể hành động |
| 60–70 phút | Chọn một lát cắt nhỏ hoặc thử nghiệm để kiểm chứng | Bước tiếp theo gắn với mục tiêu |
| 70–75 phút | Nhắc lại quyết định và mốc xem lại | Người phụ trách, thời điểm và cách cập nhật |

Trong buổi làm việc:

- Bắt đầu bằng dữ liệu và tiếng nói người dùng, không bằng danh sách giải pháp yêu thích.
- Mời người có chuyên môn hoặc góc nhìn khác nhau phát biểu trước khi người có quyền quyết định kết luận.
- Ghi rõ đâu là giả định, đâu là ràng buộc bắt buộc và đâu là thông tin chưa có.
- Tìm dấu hiệu hiểu khác nhau về từ “thành công”.
- Tránh nhồi nhiều mục tiêu ngang hàng; nếu có xung đột, làm rõ ưu tiên và guardrail.

Sau buổi họp, mục tiêu cần xuất hiện ở nơi nhóm thực sự xem mỗi ngày: bảng công việc, Product Goal/Sprint Goal khi dùng Scrum, tài liệu sản phẩm hoặc báo cáo ngắn. Chỉ lưu mục tiêu trong biên bản cuộc họp không bảo đảm nó được sử dụng.

## 12. Những ngộ nhận thường gặp

### Ngộ nhận 1: “Mục tiêu chung là hoàn thành toàn bộ backlog”

Backlog là tập các hạng mục có thể thay đổi theo điều nhóm học được. Hoàn thành hết một danh sách có thể không tạo ra kết quả người dùng nếu giả định ban đầu sai.

**Cách điều chỉnh:** Nêu rõ giá trị mục tiêu, cho phép Product Backlog được cập nhật có trách nhiệm khi xuất hiện thông tin mới.

### Ngộ nhận 2: “Chỉ cần OKR hoặc KPI là mọi người sẽ cùng hướng”

Một mục tiêu số được viết đẹp vẫn có thể không ai hiểu, không có quyền hành động hoặc khuyến khích tối ưu sai. OKR là công cụ có thể dùng trong tổ chức nhưng **không phải yêu cầu của Agile hay Scrum**.

**Cách điều chỉnh:** Kiểm tra người dùng, ràng buộc, quyền quyết định và hành động phát sinh từ dữ liệu. Không coi việc điền đủ biểu mẫu là thành công.

### Ngộ nhận 3: “Chịu trách nhiệm kết quả nghĩa là bảo đảm KPI luôn đạt”

Outcome chịu ảnh hưởng của nhiều biến số. Một đội không thể hứa chắc hành vi của tất cả khách hàng nhưng có thể chịu trách nhiệm về chất lượng thực thi, bằng chứng, tốc độ học và việc điều chỉnh giải pháp.

**Cách điều chỉnh:** Phân biệt mục tiêu hướng tới với cam kết trong vùng kiểm soát; đánh giá quyết định dựa trên bằng chứng có sẵn tại thời điểm đưa ra.

### Ngộ nhận 4: “Trách nhiệm chung thì không cần người sở hữu quyết định”

Nếu mọi người đều “có trách nhiệm”, nhưng không ai quyết ưu tiên hoặc giải quyết xung đột, công việc có thể đình trệ.

**Cách điều chỉnh:** Nói rõ ai chịu trách nhiệm quyết định giá trị, ai quyết định kỹ thuật, ai cung cấp bằng chứng, ai xử lý việc vượt thẩm quyền.

### Ngộ nhận 5: “Tự quản lý nghĩa là không cần lãnh đạo”

Nhóm tự quản lý vẫn cần định hướng, nguồn lực, ranh giới và phối hợp với hệ thống tổ chức rộng hơn. Người lãnh đạo không phải giải quyết mọi ticket nhưng cần xử lý các trở ngại mà đội không thể tự tháo gỡ.

**Cách điều chỉnh:** Trao quyền cùng điều kiện thực hiện, hỗ trợ và trách nhiệm giải trình.

### Ngộ nhận 6: “Mọi người phải làm việc giống nhau để có mục tiêu chung”

Chuyên môn khác nhau là nguồn sức mạnh. Trách nhiệm chung là **cùng sở hữu khả năng người dùng đạt mục tiêu**, không bắt buộc mọi người viết cùng loại code hoặc họp trong mọi quyết định.

**Cách điều chỉnh:** Phân chia phần việc theo năng lực nhưng thường xuyên kiểm tra luồng xuyên suốt.

### Ngộ nhận 7: “Một khi đã thống nhất mục tiêu thì không được thay đổi”

Agile coi trọng phản hồi và thích ứng, nhưng đổi mục tiêu liên tục không có lý do cũng làm mất sự tập trung. Cần phân biệt điều chỉnh phương án với thay đổi mục tiêu nền tảng.

**Cách điều chỉnh:** Có mốc và thẩm quyền xem lại, giải thích bằng chứng khiến mục tiêu cần sửa; giữ sự ổn định phù hợp để nhóm học từ một hướng đi.

### Ngộ nhận 8: “Trách nhiệm với outcome là trách nhiệm của Product Owner”

Product Owner có trách nhiệm tối đa hóa giá trị và quản lý Product Backlog trong Scrum. Nhưng Developers, Scrum Master và những người liên quan đều góp phần tạo Increment có ích, thu thập phản hồi và tháo cản trở. Để đội phát triển chỉ quan tâm code là cách tách rời trách nhiệm giá trị khỏi năng lực thực thi.

**Cách điều chỉnh:** Giữ vai trò rõ ràng đồng thời duy trì sự hợp tác hướng tới Product Goal.

### Ngộ nhận 9: “Mục tiêu tăng doanh thu luôn có ưu tiên cao hơn mọi thứ”

Doanh thu có thể là mục tiêu kinh doanh hợp lệ, nhưng giải pháp không được vi phạm an toàn, bảo mật, quyền riêng tư hoặc nghĩa vụ khác. Tối ưu ngắn hạn cũng có thể làm mất niềm tin dài hạn.

**Cách điều chỉnh:** Đặt guardrail rõ và quản lý đánh đổi bởi đúng người có thẩm quyền.

### Ngộ nhận 10: “Mọi Sprint đều phải làm chỉ số outcome tăng”

Một số outcome có độ trễ dài hoặc chịu nhiễu; có Sprint tập trung vào an toàn, hạ tầng hay giảm rủi ro để tạo khả năng phát hành sau này.

**Cách điều chỉnh:** Theo dõi cả Increment đạt DoD, giả thuyết được kiểm chứng, năng lực dòng công việc, chất lượng và outcome khi đủ dữ liệu; tránh ép kết luận từ mẫu chưa trưởng thành.

## 13. Kế hoạch cải tiến thử nghiệm trong bốn tuần

Nhóm đang có nhiều cuộc họp nhưng chưa gắn quyết định với kết quả có thể thử cách làm sau.

| Tuần | Trọng tâm | Việc làm cụ thể | Bằng chứng cần có |
|---|---|---|---|
| **1 — Nhìn rõ thực tế** | Quan sát luồng người dùng và quyết định hiện tại | Chọn một luồng quan trọng, xem ba lần bàn giao hoặc thay đổi gần đây; ghi nơi phát sinh chờ đợi và lý do ưu tiên | Một vấn đề thật, baseline sơ bộ, điểm nghẽn trách nhiệm |
| **2 — Thống nhất mục tiêu** | Cùng viết mục tiêu, guardrail và quyền quyết định | Tổ chức buổi ngắn với những vai trò liên quan; chọn một giả thuyết và một lát cắt kiểm chứng | Mục tiêu mà thành viên giải thích thống nhất, người quyết định và mốc xem lại |
| **3 — Cùng hoàn tất** | Ưu tiên tạo Increment hoặc sửa dòng công việc | Chia công việc theo luồng, hỗ trợ chỗ bị chặn, dùng DoD và kiểm thử phù hợp | Một phần mềm chạy được hoặc một thử nghiệm dòng công việc có dữ liệu rõ |
| **4 — Học và điều chỉnh** | Kiểm tra phản hồi và cách cộng tác | Xem người dùng, chỉ số, chất lượng, dự báo; chọn tiếp tục/đổi/dừng; phản tư về cơ chế phối hợp | Quyết định mới có bằng chứng, thay đổi backlog/chính sách và người chịu trách nhiệm |

Một cải tiến nhỏ được thực hiện và kiểm chứng có thể hữu ích hơn một đợt thay đổi toàn bộ cơ cấu không có phản hồi. Nếu phát hiện rào cản do quyền hạn hoặc phụ thuộc giữa nhiều đội, cần người lãnh đạo có khả năng giải quyết ở cấp phù hợp.

## 14. Bài tập vận dụng

### Bài tập A — Từ KPI bộ phận sang mục tiêu chung

Một nhóm có các chỉ tiêu:

1. Frontend hoàn thành 12 màn hình.
2. Backend hoàn thành 20 endpoint.
3. QA đóng 50 ticket kiểm thử.
4. Học viên vẫn không thể đăng ký và vào học theo luồng xuyên suốt.

**Yêu cầu:** Viết lại một mục tiêu chung cho nhóm. Nêu hai kết quả người dùng có thể quan sát, hai guardrail và ba hành động phối hợp giúp nhóm tiến gần mục tiêu.

<details>
<summary>Gợi ý đáp án</summary>

Mục tiêu có thể là “giúp học viên mới hoàn thành đăng ký và vào bài học đầu tiên thuận lợi trên thiết bị được hỗ trợ”. Kết quả: tỷ lệ người học tự hoàn tất luồng và thời gian từ đăng ký đến khi bắt đầu bài đầu. Guardrail: không tăng lỗi phân quyền, không suy giảm khả năng truy cập. Hành động phối hợp: tạo một lát cắt đầu-cuối trước khi mở thêm giao diện; kiểm thử tích hợp sớm; cùng hỗ trợ gỡ lỗi ở bước email hoặc thanh toán đang chặn luồng. Không cần dùng số màn hình hoặc endpoint như mục tiêu giá trị.

</details>

### Bài tập B — Quyền quyết định khi có yêu cầu chen ngang

Trong Sprint, một stakeholder đề nghị thêm báo cáo quản trị không liên quan trực tiếp Sprint Goal. Cùng lúc, Developers phát hiện lỗi xác minh email có thể khiến Sprint Goal không đạt. Stakeholder cho rằng báo cáo phải được làm ngay vì “lãnh đạo vừa yêu cầu”.

**Yêu cầu:** Ai cần tham gia quyết định? Nhóm nên kiểm tra những thông tin nào? Có những lựa chọn hợp lý nào?

<details>
<summary>Gợi ý đáp án</summary>

Developers đánh giá tiến triển Sprint Goal, phần việc và rủi ro chất lượng; Product Owner cùng Scrum Team xem giá trị và trao đổi ưu tiên với stakeholder. Nếu có nghĩa vụ hoặc rủi ro vượt thẩm quyền, tham vấn người có quyền quyết định. Các lựa chọn gồm hoãn báo cáo vào Product Backlog, giảm phạm vi không thiết yếu của Sprint để giữ Sprint Goal, hoặc xử lý yêu cầu khẩn thật sự thông qua cơ chế đã thống nhất. Không âm thầm hạ DoD hay bỏ Sprint Goal chỉ để đáp ứng yêu cầu mới nhất.

</details>

### Bài tập C — Outcome chưa đạt thì đội phải làm gì?

Nhóm đặt mục tiêu tăng tỷ lệ kích hoạt tài khoản từ 40% lên 50%. Sau hai Sprint, Increment đã đạt DoD, dữ liệu đo đủ kỳ cho thấy tỷ lệ khoảng 43%. Người quản lý yêu cầu chỉ ra cá nhân chịu trách nhiệm vì không đạt 50%.

**Yêu cầu:** Phân biệt trách nhiệm giao hàng và trách nhiệm hướng kết quả. Nêu ít nhất bốn câu hỏi giúp đội chọn hành động tiếp theo mà vẫn giải trình rõ ràng.

<details>
<summary>Gợi ý đáp án</summary>

Đội có thể đã hoàn tất trách nhiệm tạo Increment đạt chất lượng, trong khi outcome chưa đạt kỳ vọng. Cần kiểm tra định nghĩa kích hoạt và chất lượng dữ liệu; tỉ lệ người dùng được tiếp xúc tính năng; các yếu tố cùng thay đổi; hành vi người dùng đang bị chặn; giả thuyết sản phẩm; chất lượng luồng đầu-cuối; và quyền điều chỉnh backlog của nhóm. Product Owner chịu trách nhiệm quản lý ưu tiên và giá trị trong Scrum; Developers chịu trách nhiệm chất lượng và cách tạo Increment; Scrum Master hỗ trợ hiệu quả Scrum. Không có cơ sở quy lỗi cá nhân chỉ từ một KPI tổng hợp.

</details>

### Bài tập D — Thiết kế buổi thống nhất mục tiêu

Bạn tiếp nhận một nhóm có frontend, backend, QA, vận hành và Product Owner. Họ đều bận nhưng liên tục phải làm lại do hiểu khác nhau về từ “hoàn tất”.

**Yêu cầu:** Soạn chương trình 45–60 phút nhằm tạo mục tiêu chung; nêu bốn đầu ra tối thiểu của buổi làm việc và một cách kiểm tra sau hai tuần.

<details>
<summary>Gợi ý đáp án</summary>

Có thể dành thời gian xem một luồng người dùng thực tế và các điểm bị chặn; thảo luận đối tượng/vấn đề; thống nhất mục tiêu có tín hiệu đo; làm rõ DoD và quyền quyết định; chọn lát cắt kiểm chứng. Bốn đầu ra: phát biểu mục tiêu, tiêu chí kiểm tra/guardrail, bản đồ phụ thuộc và người chịu trách nhiệm quyết định, mốc xem lại. Sau hai tuần, kiểm tra Increment hoặc thay đổi dòng công việc có làm giảm điểm chặn và cải thiện khả năng người dùng hoàn tất tác vụ không.

</details>

### Bài tập E — Phản biện một “mục tiêu chung” không có guardrail

Một đội được giao mục tiêu “giảm thời gian hoàn tất thanh toán bằng mọi giá”. Một đề xuất là bỏ bước xác nhận thông tin cuối cùng. Khảo sát nhanh cho thấy một số người dùng thanh toán nhanh hơn, nhưng xuất hiện đơn đặt nhầm và yêu cầu hoàn tiền.

**Yêu cầu:** Viết lại mục tiêu, bổ sung hai guardrail, nêu quyết định về thử nghiệm tiếp theo.

<details>
<summary>Gợi ý đáp án</summary>

Mục tiêu có thể là “giúp khách hoàn tất giao dịch mong muốn dễ hơn và nhanh hơn mà vẫn hiểu rõ số tiền, nội dung đơn và điều kiện thanh toán”. Guardrail: tỷ lệ đặt nhầm/hoàn tiền do lỗi trải nghiệm không tăng và không suy giảm các kiểm soát bảo mật. Đội nên xem dữ liệu phân nhóm và nguyên nhân thao tác nhầm; thử giải pháp xác nhận gọn, rõ đúng ngữ cảnh hoặc giảm các bước không quan trọng thay vì mặc định bỏ bước xác nhận. Với rủi ro cao, cần đánh giá bởi các vai trò có thẩm quyền phù hợp.

</details>

## 15. Bộ câu hỏi tự đánh giá nhóm

Với mỗi câu, hãy đưa ra **một ví dụ có thật trong công việc gần đây**, thay vì trả lời đơn giản “có/không”.

1. Tất cả thành viên có thể diễn đạt mục tiêu hiện tại bằng ngôn ngữ của người dùng không?
2. Mọi người có biết mục tiêu khác gì với danh sách ticket cần hoàn tất không?
3. Nếu hai yêu cầu xung đột, nhóm có biết tiêu chí ưu tiên và ai có quyền quyết định không?
4. Thành viên có thể nêu rủi ro đối với mục tiêu mà không cần đợi cuộc họp báo cáo cấp quản lý không?
5. Khi một phần việc bị chặn, nhóm có cùng tập trung hoàn tất luồng giá trị hay mỗi người mở thêm việc riêng?
6. Đội có Definition of Done đủ đáng tin để biết khả năng nào thực sự hoạt động không?
7. Sprint Review hoặc nhịp xem lại sản phẩm có giúp thay đổi quyết định theo bằng chứng không?
8. Dữ liệu về người dùng, dòng công việc và chất lượng có được đọc trong cùng một bối cảnh không?
9. Các ràng buộc về bảo mật, khả năng truy cập, tuân thủ và vận hành đã rõ chưa?
10. Khi một outcome không đạt, nhóm có tìm nguyên nhân và điều chỉnh giả thuyết thay vì giấu kết quả hay đổ lỗi ngay không?
11. Người lãnh đạo có giúp tháo phụ thuộc và cung cấp quyền quyết định tương xứng trách nhiệm không?
12. Nhóm có thể nêu một cải tiến cụ thể đã được thử, đo và giữ lại hoặc bỏ đi sau phản hồi không?

Nếu nhiều câu thiếu minh chứng, hãy chọn **một luồng người dùng** và **một quyết định lặp lại** để cải thiện trước. Tránh tổ chức thêm hàng loạt cuộc họp chỉ để chứng minh đang áp dụng Agile.

## 16. Ghi nhớ

- **Mục tiêu chung giúp đội phối hợp và lựa chọn phương án.** Nó cần gắn với nhu cầu người dùng, kết quả mong muốn, bằng chứng và ràng buộc rõ ràng.
- **Các thành viên không cần làm cùng một việc nhưng cần cùng quan tâm kết quả xuyên suốt.** Trách nhiệm chung đi cùng người chịu trách nhiệm cụ thể về quyết định, chuyên môn và chất lượng.
- **Scrum phân biệt rõ các accountability.** Product Owner tối đa hóa giá trị và quản lý Product Backlog; Developers tạo Increment có thể sử dụng; Scrum Master nâng cao hiệu quả Scrum; Scrum Team cùng hướng tới Product Goal.
- **Trách nhiệm đối với outcome là trách nhiệm học, quyết định và điều chỉnh dựa trên bằng chứng.** Kết quả người dùng không hoàn toàn nằm dưới quyền kiểm soát của một cá nhân.
- **Lãnh đạo tạo điều kiện cho quyền tự chủ có trách nhiệm.** Mục tiêu, thông tin, quyền quyết định, nguồn lực, phản hồi và giới hạn an toàn phải đi cùng nhau.
- **Scrum, Kanban và XP hỗ trợ những khía cạnh khác nhau của cùng hành trình:** tập trung mục tiêu và kiểm tra Increment, quản lý dòng công việc, duy trì năng lực kỹ thuật để học từ thay đổi sớm.

Khi nhóm đang tranh luận nên làm gì tiếp, hãy trở lại ba câu hỏi: **“Chúng ta cùng muốn người dùng đạt điều gì? Ai có trách nhiệm và quyền đưa ra quyết định này? Bằng chứng nào sẽ khiến chúng ta giữ hoặc đổi hướng?”** Một nhóm trả lời được cả ba bằng những ví dụ thực tế đã có nền tảng để cộng tác hiệu quả và cùng chịu trách nhiệm về kết quả.

## Tài liệu tham khảo định hướng

- [Manifesto for Agile Software Development](https://agilemanifesto.org/): các giá trị cộng tác, phản hồi thay đổi, phần mềm hoạt động được.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html): cộng tác thường xuyên, nhóm tự tổ chức, nhịp phát triển bền vững và cải tiến liên tục.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): Product Goal, Sprint Goal, Definition of Done, các accountability và các sự kiện Scrum.
- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/): cách nhìn luồng giá trị, quản lý WIP và các chỉ số dòng công việc.
