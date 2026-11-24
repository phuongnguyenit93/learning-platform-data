# Chuẩn bị sự hỗ trợ của lãnh đạo và quyền ra quyết định phù hợp

> **Chương:** Chuyển đổi Agile  
> **Học phần:** **AGILE_DEVELOPMENT** — hiểu giá trị và nguyên tắc Agile trong phát triển phần mềm thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để lựa chọn cách phối hợp phù hợp.

Một công ty công bố chương trình “chuyển đổi Agile” và yêu cầu mọi nhóm tổ chức Sprint Planning, Daily Scrum, Sprint Review, Sprint Retrospective. Nhóm sản phẩm đặt lịch nhanh chóng tạo Product Backlog và giao được một vài Increment nhỏ. Tuy nhiên, mỗi khi Product Owner muốn đổi thứ tự công việc theo phản hồi khách hàng, đề xuất phải chờ ba cấp quản lý ký duyệt. Developers phát hiện hệ thống có nguy cơ tạo lịch trùng nhưng không có quyền dành năng lực sửa lỗi nếu kế hoạch quý chưa ghi. Người quản lý yêu cầu vừa “tự tổ chức” vừa “cam kết không thay đổi ngày và phạm vi”. Sprint diễn ra đều đặn, **cơ chế ra quyết định vẫn ngăn nhóm thích ứng**.

Đây là một vấn đề của **hệ thống lãnh đạo và quản trị**, không thể sửa chỉ bằng cách huấn luyện nhóm về các sự kiện Scrum. Chuyển đổi Agile đòi hỏi tổ chức biết **mình muốn cải thiện kết quả gì, lãnh đạo cam kết thay đổi điều kiện nào, ai được quyết định việc gì, và khi nào phải phối hợp hoặc báo cáo rủi ro**.

**Thông điệp cốt lõi:** *Trao quyền* không phải để mọi người tự quyết mọi thứ; *hỗ trợ lãnh đạo* không phải để một nhà quản lý tham dự mọi cuộc họp. Một tổ chức thích ứng tốt khi **quyết định được đưa ra gần nơi có thông tin và năng lực phù hợp nhất, trong các ranh giới chiến lược, an toàn và trách nhiệm minh bạch**.

Bài học trình bày cách chuẩn bị **sự bảo trợ thực chất của lãnh đạo**, định nghĩa **quyền quyết định sản phẩm, kỹ thuật, con người và rủi ro**, thiết kế đường **ủy quyền và leo thang** không tạo nút thắt, rồi kiểm tra hiệu quả bằng các kết quả có thể quan sát. Ví dụ xuyên suốt là nền tảng đặt lịch tư vấn có ba nhóm cùng phát triển một sản phẩm.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **Agile transformation là thay đổi hệ thống làm việc**, không đồng nghĩa lắp đặt công cụ hoặc tổ chức các buổi họp mới.
2. Phân biệt **sự đồng ý trên lời nói, sự bảo trợ chủ động và hỗ trợ vận hành thường xuyên** của lãnh đạo.
3. Xác định những **điểm nghẽn quyền quyết định** khiến phản hồi người dùng hoặc rủi ro kỹ thuật không được xử lý đúng lúc.
4. Phân biệt quyết định **chiến lược/đầu tư, giá trị và thứ tự Product Backlog, thực thi kỹ thuật, nhân sự, bảo mật, phát hành, vận hành và ứng cứu sự cố**.
5. Hiểu trách nhiệm chính thức của **Product Owner, Developers và Scrum Master** trong Scrum, đồng thời thiết kế cơ chế tổ chức bổ sung mà không tự tạo “Scrum role” sai.
6. Viết **decision charter** và ma trận quyền quyết định, gồm phạm vi tự chủ, giới hạn ngân sách/rủi ro, người tham vấn và cơ chế giải quyết xung đột.
7. Đề xuất cách lãnh đạo hỗ trợ bằng **mục tiêu rõ, nhóm đủ năng lực, ngân sách, thời gian học, điều kiện kỹ thuật, phản hồi và xử lý trở ngại cơ cấu**.
8. Thiết kế **thử nghiệm chuyển đổi có giới hạn**, đo kết quả người dùng, flow, chất lượng, thời gian chờ quyết định và sự phát triển năng lực ra quyết định.
9. Xử lý tình huống quyền hạn chồng chéo, quản lý trung gian thiếu vai trò rõ hoặc yêu cầu khẩn xung đột với kế hoạch đã chọn.

## 2. Chuyển đổi Agile là thay đổi điều kiện để học và giao giá trị

### 2.1. Đổi tên chức danh chưa thay được cơ chế ra quyết định

| Thay đổi bề mặt | Thay đổi hệ thống có ý nghĩa hơn |
| --- | --- |
| Đổi “Project Manager” thành “Scrum Master”. | Làm rõ trách nhiệm, năng lực hỗ trợ và những trở ngại tổ chức có thể được xử lý. |
| Tất cả nhóm chạy Sprint hai tuần. | Giao Increment đủ chất lượng, nhận phản hồi và thích ứng Product Backlog theo Product Goal. |
| Có bảng Kanban mới. | Công khai workflow, kiểm soát WIP, cải thiện thời gian chờ và khả năng hoàn tất. |
| Mọi người tham gia khóa Agile. | Lãnh đạo thay đổi mục tiêu, cách phân bổ năng lực, quyền quyết định và phản hồi khi có bằng chứng mới. |
| Mỗi quý báo “Agile maturity tăng”. | Người dùng nhận giá trị sớm hơn, chất lượng được bảo vệ và nhóm có thể thay đổi hướng khi cần. |
| Quản lý tuyên bố “hãy tự chủ”. | Nhóm biết **những quyết định nào thuộc quyền mình**, guardrails nào áp dụng, có nguồn lực và đường leo thang rõ. |

Một tổ chức có thể thực hiện Scrum đúng các sự kiện mà vẫn khó thích ứng nếu cơ chế ngân sách, hợp đồng, kiến trúc, đánh giá hiệu suất hay quyền phê duyệt đi ngược với nhu cầu giao tăng dần.

### 2.2. Kết quả cần thay đổi là gì?

Mục tiêu chuyển đổi không nên chỉ là:

> “Đến cuối năm có 100% nhóm sử dụng Scrum.”

Một mục tiêu có thể kiểm tra tốt hơn:

> “Rút ngắn thời gian từ phát hiện vấn đề đặt lịch tới khi khách nhận thay đổi an toàn, tăng khả năng hoàn tất tác vụ tự phục vụ, giảm lỗi nghiêm trọng và giữ nhịp làm việc bền vững.”

Các chỉ báo có thể gồm **outcome người dùng**, **cycle time/blocked time**, **lỗi hồi quy**, **thời gian ra quyết định**, **khả năng thay đổi ưu tiên theo bằng chứng** và **sức khỏe hệ thống làm việc**. Không có chỉ báo đơn lẻ chứng minh chuyển đổi thành công.

### 2.3. Lãnh đạo phải thay đổi cách hành xử, không chỉ yêu cầu người khác đổi

Khi nhóm đưa ra dữ liệu cho thấy giả thuyết thị trường sai, lãnh đạo có thể:

- **Cách cũ:** “Đã cam kết roadmap thì làm cho đủ; báo cáo phần trăm hoàn thành.”
- **Cách thích ứng:** “Mục tiêu người dùng vẫn quan trọng. Có phương án nào làm lát cắt khác để kiểm chứng nhanh hơn và an toàn hơn? Phạm vi hoặc đầu tư nào cần điều chỉnh?”

Khi một lỗi nghiêm trọng xuất hiện:

- **Cách cũ:** “Đừng ảnh hưởng deadline; đưa bug vào quý sau.”
- **Cách có trách nhiệm:** “Bảo vệ người dùng theo mức nghiêm trọng trước, sau đó nêu ảnh hưởng đến năng lực và cập nhật dự báo.”

**Trao quyền không có nghĩa mặc kệ.** Lãnh đạo vẫn phải đặt định hướng, bảo vệ các ranh giới pháp lý/an toàn và chịu trách nhiệm đối với quyết định thuộc thẩm quyền của mình.

### 2.4. Sơ đồ vòng hỗ trợ lãnh đạo

~~~mermaid
flowchart TD
    G["Mục tiêu và kết quả tổ chức cần đạt"] --> P["Product Goal và các ranh giới quyết định"]
    P --> T["Nhóm có năng lực và quyền thực thi phù hợp"]
    T --> I["Increment nhỏ đạt chất lượng"]
    I --> F["Phản hồi người dùng, flow và chất lượng"]
    F --> D["Quyết định thích ứng dựa trên bằng chứng"]
    D --> P
    F --> L["Lãnh đạo xem trở ngại hệ thống"]
    L --> R["Điều chỉnh cấu trúc, đầu tư, chính sách, năng lực"]
    R --> T
~~~

Nếu vòng **lãnh đạo xem trở ngại → thay đổi điều kiện** không hoạt động, phản hồi thu được trong Sprint Review có thể chỉ tạo thêm ticket nhưng không làm sản phẩm tiến lên.

## 3. Sự hỗ trợ của lãnh đạo có ba mức

### 3.1. Đồng ý, bảo trợ và duy trì hỗ trợ không giống nhau

| Mức | Biểu hiện | Giá trị và giới hạn |
| --- | --- | --- |
| **Đồng ý về chủ trương** | Cho phép thử Scrum/Kanban, tham dự buổi khởi động. | Cần thiết nhưng **chưa giải quyết** ngân sách, quyền và phụ thuộc. |
| **Bảo trợ chủ động (sponsorship)** | Nêu mục đích chuyển đổi, nhận trách nhiệm điều chỉnh chính sách, dành năng lực và xử lý xung đột vượt nhóm. | Tạo điều kiện cho thay đổi **thực chất**. |
| **Hỗ trợ liên tục** | Xem bằng chứng, bỏ rào cản, giữ cam kết, sửa cơ chế đánh giá/đầu tư khi cần. | Ngăn tổ chức quay lại lối cũ khi áp lực tiến độ tăng. |

Một tuyên bố trong cuộc họp toàn công ty không phải bằng chứng đủ của sponsorship. Cần xem **quyết định và nguồn lực đã thực sự thay đổi**.

### 3.2. Nhà bảo trợ chuyển đổi (executive sponsor) làm gì?

Vai trò bảo trợ là **cách tổ chức phân công**, không phải một accountability bắt buộc của Scrum Guide. Người bảo trợ có thể:

1. Nói rõ **vì sao** chuyển đổi và kết quả cần đạt.
2. Bảo đảm mục tiêu chuyển đổi phù hợp chiến lược, người dùng và nghĩa vụ hiện hành.
3. Tài trợ thử nghiệm, huấn luyện, chất lượng kỹ thuật và thời gian cải tiến.
4. Bảo vệ quyền quyết định đã ủy quyền khi xảy ra áp lực kéo mọi thứ trở lại cơ chế duyệt cũ.
5. Tháo các trở ngại **vượt khả năng xử lý của Scrum Team**: phân bổ ngân sách, cấu trúc nhóm, quy trình mua sắm, quyền truy cập môi trường.
6. Hỗ trợ cơ chế leo thang nhanh với rủi ro, bảo mật, tuân thủ và các quyết định liên phòng ban.
7. Nhìn **kết quả thực và tác động phụ** thay vì chỉ số số lượng sự kiện Agile.
8. Chấp nhận học từ thử nghiệm không đạt giả thuyết nhưng **không cho phép bỏ qua an toàn hoặc gian lận số liệu**.

Người bảo trợ không nên quyết định mọi Product Backlog Item hoặc tự chỉ định task cho Developers. Làm vậy có thể vừa tăng thời gian chờ vừa khiến trách nhiệm sản phẩm không rõ.

### 3.3. Người quản lý trung gian không phải “chướng ngại phải loại bỏ”

Trong một chuyển đổi, trưởng bộ phận, engineering manager, quản lý QA, vận hành và chuyên gia an toàn thường đang nắm **trách nhiệm con người, năng lực, tiêu chuẩn và quản trị**. Nếu chỉ nói “từ nay nhóm tự tổ chức nên không cần quản lý”, người ta có thể lo mất quyền, còn công việc quản trị quan trọng bị bỏ trống.

Thay vì bỏ qua họ, cần làm rõ cách hỗ trợ mới:

- Xây **năng lực và con đường phát triển** của nhân viên.
- Bảo đảm nhóm có đủ kỹ năng, môi trường, quyền truy cập và sự ổn định.
- Tháo trở ngại liên phòng ban, giảm lệ thuộc một chuyên gia.
- Hỗ trợ tiêu chuẩn kỹ thuật, bảo mật và việc vận hành lâu dài.
- Cải tiến hệ thống đánh giá để không khuyến khích che lỗi, làm việc quá tải hoặc tối đa hóa số ticket.
- Tôn trọng quyền quyết định giá trị của Product Owner và quyền lập kế hoạch của Developers.

**Quyền quản lý nhân sự không tự đồng nghĩa quyền sắp thứ tự Product Backlog**. Ngược lại, Product Owner **không tự động** có thẩm quyền quyết định lương, kỷ luật nhân sự hoặc vượt chuẩn bảo mật chỉ vì chịu trách nhiệm giá trị sản phẩm.

### 3.4. Hỗ trợ phải hiển thị qua hành động cụ thể

Một *sponsorship backlog* nội bộ có thể ghi những trở ngại cơ cấu cần người có thẩm quyền tháo, chẳng hạn:

| Trở ngại | Tác động | Việc lãnh đạo có thể quyết định | Cách kiểm chứng |
| --- | --- | --- | --- |
| Cấp môi trường test cần ba cấp duyệt. | Story chờ nhiều ngày trước tích hợp. | Phê duyệt cơ chế cấp quyền có kiểm soát và self-service. | Thời gian chờ giảm, không tăng sự cố quyền truy cập. |
| Mỗi thay đổi nhỏ phải qua hội đồng phát hành cố định mỗi tháng. | Increment đạt DoD nhưng khách chờ lâu. | Phân loại rủi ro phát hành, tự động hóa kiểm tra và điều kiện release phù hợp. | Tần suất giao an toàn, lỗi và thời gian khôi phục. |
| Một chuyên gia kỹ thuật là điểm duyệt duy nhất. | Các nhóm chờ review và kiến thức không lan tỏa. | Dành năng lực huấn luyện và reviewer dự phòng có đủ chuyên môn. | Blocked time và chất lượng review. |
| PO phải xin phép ba quản lý để đổi thứ tự PBI. | Phản hồi người dùng không vào kế hoạch kịp. | Xác định rõ ủy quyền về thứ tự và giới hạn đầu tư. | Độ trễ quyết định, số lần leo thang vô ích. |

Danh sách trở ngại không phải một Product Backlog thứ hai để tranh quyền ưu tiên sản phẩm; nó là **công cụ minh bạch việc hệ thống quản trị cần thay đổi**, với thẩm quyền và trách nhiệm rõ.

## 4. Chẩn đoán hiện trạng quyền ra quyết định

Trước khi viết ma trận RACI mới, nhóm cần quan sát **cách quyết định thực sự đi qua tổ chức**, bao gồm sự chờ đợi, vòng lặp duyệt lại, ngoại lệ và những quyết định không ai dám đưa ra.

### 4.1. Đi theo một quyết định thật, không chỉ nhìn sơ đồ chức danh

Ví dụ người dùng báo **không nhận được trạng thái đặt lịch**. Hãy lần theo:

1. Ai nhận phản hồi và kiểm chứng vấn đề?
2. Ai có thể yêu cầu sửa lỗi, khám phá hoặc cập nhật Product Backlog?
3. Ai quyết định thứ tự công việc này so với SMS hoặc đổi giao diện?
4. Developers có quyền chọn phương án giải quyết và test cần thiết không?
5. Ai phải chấp thuận sử dụng dữ liệu test, môi trường, API đối tác?
6. Ai quyết định có thể phát hành trong phạm vi kiểm soát?
7. Nếu rủi ro dữ liệu được xác minh, ai có quyền dừng rollout và ứng cứu?
8. Khi thông tin mới mâu thuẫn kế hoạch quý, ai cập nhật ngân sách/phạm vi?

Tìm **đường chờ thực tế**: “chờ ai?”, “để biết điều gì?”, “quy định nào yêu cầu?”, “có thể giảm số cấp duyệt mà vẫn bảo vệ rủi ro không?”.

### 4.2. Những dấu hiệu quyền hạn không rõ

| Dấu hiệu | Giả thuyết về cơ chế | Cách kiểm tra |
| --- | --- | --- |
| PO được gọi “owner” nhưng thứ tự PBI luôn bị quản lý đổi. | Quyền quyết định sản phẩm chỉ trên danh nghĩa. | So log thay đổi ưu tiên với quyết định cuối và thẩm quyền. |
| Developers phải chờ người ngoài duyệt mọi thay đổi test. | Chính sách kỹ thuật không phân loại mức rủi ro. | Kiểm tra thời gian chờ, tỷ lệ trường hợp phải duyệt và lỗi. |
| Mỗi team có “PO riêng” quyết định độc lập cho một sản phẩm. | Không có trách nhiệm giá trị thống nhất. | Xác định ranh giới sản phẩm, Product Goal, nguồn PBI chuẩn. |
| Manager bị yêu cầu bảo đảm deadline nhưng không được tham gia điều chỉnh năng lực. | Trách nhiệm không khớp quyền quyết định. | Xem thỏa thuận đầu tư, nhân sự, forecast và cách xử lý thay đổi. |
| Một lỗi nghiêm trọng phải chờ phiên lập kế hoạch mới. | Đường incident/triage không rõ hoặc bị lẫn backlog. | Quan sát một tình huống giả lập an toàn, không cố tạo lỗi production. |
| Cuộc họp “đồng thuận” kéo dài nhưng không ai có quyền chốt. | Thiếu người quyết định cuối hoặc tiêu chí/giới hạn rõ. | Ghi thời gian từ nêu vấn đề tới quyết định thực thi. |

Một dấu hiệu có thể có nhiều nguyên nhân. Chẳng hạn, thời gian duyệt lâu có thể do **rủi ro pháp lý thật**, chứ không nhất thiết do quản lý thích kiểm soát. Cần làm rõ rủi ro và cách giảm bằng chứng/kiểm tra, **không tự ý bỏ kiểm soát bắt buộc**.

### 4.3. Bản đồ dòng quyết định

~~~mermaid
flowchart LR
    A["Tín hiệu / vấn đề từ khách"] --> B["Phân loại và xác minh"]
    B --> C["Quyết định giá trị / ưu tiên"]
    C --> D["Thiết kế và triển khai"]
    D --> E["Kiểm chứng chất lượng / rủi ro"]
    E --> F["Quyết định phát hành"]
    F --> G["Quan sát kết quả"]
    G -. "Bằng chứng mới" .-> B
    B -. "Sự cố khẩn" .-> H["Incident response theo chính sách"]
    H -. "Khắc phục / học" .-> C
~~~

Trong sơ đồ trên, **mỗi nút có thể thuộc thẩm quyền khác nhau**. Vấn đề xuất hiện khi tất cả buộc phải đi qua cùng một người, hoặc không ai biết ai quyết định khi có rủi ro.

### 4.4. Đo thời gian quyết định, không chỉ thời gian viết code

Một nhóm có thể xử lý thay đổi trong hai ngày nhưng mất mười ngày chờ duyệt ưu tiên/môi trường. Nếu chỉ đo thời gian coding thì chương trình chuyển đổi không nhìn thấy giới hạn thực.

Một chỉ số hữu ích là **decision latency**: khoảng thời gian từ lúc vấn đề có đủ dữ liệu và được đưa vào đường quyết định phù hợp đến lúc có quyết định có thể hành động. Phải định nghĩa:

- Mốc bắt đầu/kết thúc của từng loại quyết định.
- Mức độ quan trọng và rủi ro; quyết định phức tạp không nên so thô với việc nhỏ.
- Bao nhiêu lần yêu cầu bổ sung dữ liệu vì **thật sự cần** và vì **quyền hạn mơ hồ**.
- Mất bao lâu để thực thi quyết định sau khi đã chốt?
- Kết quả có tốt và an toàn không, hay quyết định quá nhanh dẫn tới làm lại?

**Không cố rút mọi quyết định về “trong một giờ”.** Quyết định quan trọng cần kiểm tra đủ; mục tiêu là bỏ **thời gian chờ và lặp duyệt không tạo thông tin**, không bỏ chất lượng.

## 5. Phân loại quyền quyết định trước khi ủy quyền

### 5.1. Một quyết định có nhiều loại ảnh hưởng

| Loại quyết định | Ví dụ | Vì sao cần ranh giới |
| --- | --- | --- |
| **Chiến lược/đầu tư** | Đầu tư cho nền tảng đặt lịch hay một sản phẩm khác. | Liên quan ngân sách, mục tiêu nhiều sản phẩm và trách nhiệm tổ chức. |
| **Mục tiêu và thứ tự sản phẩm** | Ưu tiên trạng thái Pending hơn SMS; điều chỉnh Product Backlog. | Cần người chịu trách nhiệm tối đa hóa giá trị một sản phẩm. |
| **Thực thi và thiết kế** | Chọn API, test, cách cắt lát, thiết kế chống trùng. | Cần kiến thức kỹ thuật và khả năng kiểm chứng gần công việc. |
| **Nhân sự và năng lực** | Tuyển thêm kỹ năng bảo mật, đào tạo, phân bổ người. | Liên quan trách nhiệm quản lý con người và dài hạn. |
| **Chính sách rủi ro/tuân thủ** | Quyền truy cập dữ liệu, ngưỡng bảo mật, nghĩa vụ báo cáo. | Cần đúng tiêu chuẩn và người chịu trách nhiệm pháp lý/chuyên môn. |
| **Phát hành/vận hành** | Rollout theo nhóm, rollback, giám sát và ứng cứu. | Có tác động thật tới dữ liệu và người dùng. |
| **Khám phá/đo lường** | Thử usability với dữ liệu giả, gắn event không nhạy cảm. | Có thể làm nhanh nếu trong chính sách bảo vệ, nhưng vẫn có giới hạn riêng tư. |
| **Xử lý xung đột liên nhóm** | Hai nhóm cùng cần một chuyên gia để giải quyết sự cố hoặc feature. | Cần nhìn tác động tới mục tiêu toàn sản phẩm và quyền phân bổ năng lực. |

Không nhất thiết giao mỗi loại cho một chức danh riêng. Một người có thể kiêm nhiều trách nhiệm trong tổ chức nhỏ. Tuy nhiên, **cùng một người không xóa nhu cầu minh bạch về cơ chế và rủi ro**.

### 5.2. Trao quyền theo mức rủi ro và tính đảo ngược

| Loại quyết định | Tình huống | Cách ủy quyền phù hợp |
| --- | --- | --- |
| **Nhỏ, dễ đảo ngược** | Thay thứ tự thử hai cách diễn đạt thông báo với dữ liệu giả. | Nhóm chuyên môn tự quyết trong mục tiêu và quy tắc thử đã thống nhất; chia sẻ kết quả. |
| **Giới hạn, cần phối hợp** | Thay hợp đồng API dùng bởi hai team. | Developers/chủ hợp đồng phối hợp với consumer, test tương thích và thông báo. |
| **Có tác động tài chính/nguồn lực** | Thuê thêm dịch vụ cloud vượt ngân sách được phân bổ. | Người được ủy quyền ngân sách xem xét chi phí và giới hạn. |
| **Rủi ro dữ liệu/bảo mật cao** | Thay transaction đặt lịch, quyền tra cứu thông tin khách. | Bắt buộc tuân thủ chuẩn kiểm thử, bảo mật và phê duyệt theo phân loại rủi ro. |
| **Khó đảo ngược hoặc chiến lược** | Đóng một dòng sản phẩm, tái cơ cấu lớn. | Thẩm quyền chiến lược tham vấn các nhóm và người bị ảnh hưởng. |
| **Sự cố đang gây hại** | Lịch tạo trùng và email gửi sai trạng thái. | Kích hoạt quyền ứng cứu/dừng rollout theo chính sách ngay, không chờ biểu quyết backlog. |

**Thấp rủi ro không có nghĩa muốn làm gì cũng được:** vẫn phải giữ mục tiêu, chất lượng và nghĩa vụ bảo vệ dữ liệu. **Cao rủi ro cũng không mặc định cần ba cấp duyệt nối tiếp:** có thể dùng kiểm tra tự động, chuẩn hóa bằng chứng và người có thẩm quyền chuyên môn để rút thời gian chờ mà không giảm an toàn.

### 5.3. Quyền quyết định gồm cả quyền nói “chưa đủ dữ liệu”

Nếu Product Owner muốn đưa một chức năng đổi lịch vào Sprint nhưng Developers biết hợp đồng đối tác chưa rõ và việc tạo lịch trùng có thể xảy ra, phản hồi chuyên môn phải được lắng nghe. **Quyền ưu tiên giá trị không tự động quyết định phương án kỹ thuật an toàn.**

Ngược lại, nếu Developers thích viết lại kiến trúc vì thẩm mỹ, họ cần chỉ ra **vấn đề và chi phí cơ hội** khi dùng năng lực sản phẩm. **Quyền thiết kế kỹ thuật không tự động cho phép bỏ qua Product Goal và quyết định đầu tư.**

## 6. Viết ma trận quyền quyết định không làm biến mất trách nhiệm Scrum

Ma trận ra quyết định có thể giúp một tổ chức thấy **ai quyết định, ai tham vấn, ai thực thi và khi nào leo thang**. Nó là **công cụ tổ chức tùy chọn**, không thay thế định nghĩa chính thức về Scrum accountabilities.

### 6.1. Ma trận minh họa cho một sản phẩm đặt lịch

| Câu hỏi / loại quyết định | Quyền quyết định chính / trách nhiệm | Cần tham vấn | Ranh giới/điều kiện |
| --- | --- | --- | --- |
| Định hướng đầu tư và hạn mức ngân sách sản phẩm | Lãnh đạo/cấp có thẩm quyền đầu tư. | Product Owner, tài chính, nhóm phát triển, stakeholder. | Mục tiêu tổ chức, ngân sách, nghĩa vụ và rủi ro. |
| Mục tiêu và thứ tự Product Backlog trong Scrum | **Product Owner** chịu trách nhiệm, quyết định thứ tự. | Developers, người dùng, stakeholder, chuyên gia miền. | Chiến lược/mục tiêu sản phẩm, chính sách và nghĩa vụ áp dụng. |
| Sprint Goal và cách lập Sprint Backlog | **Scrum Team** tạo Sprint Goal; **Developers** chịu trách nhiệm lập và thích ứng kế hoạch Sprint Backlog. | Product Owner làm rõ giá trị, Scrum Master hỗ trợ khi cần. | Definition of Done, năng lực, Sprint Goal, chất lượng. |
| Thiết kế kỹ thuật, cách kiểm thử và tích hợp | **Developers/người có thẩm quyền kỹ thuật theo tổ chức**, cộng tác và tự quản trong Scrum. | Consumer, bảo mật, vận hành, chuyên gia nghiệp vụ. | Tiêu chuẩn kỹ thuật, quyền, dữ liệu và DoD. |
| Đổi chính sách truy cập dữ liệu nhạy cảm | Người có thẩm quyền bảo mật/pháp lý theo quy trình tổ chức. | Developers, Product Owner, vận hành. | Quy định và đánh giá rủi ro áp dụng. |
| Mở rộng rollout cho khách thật | Người được giao quyền release/vận hành theo chính sách. | Product Owner, Developers, support, an toàn khi cần. | Bằng chứng chất lượng, guardrails và năng lực khôi phục. |
| Dừng rollout/ứng cứu sự cố | Người trực ứng cứu hoặc vai trò được ủy quyền. | Các bên bị ảnh hưởng và lãnh đạo khi cần. | Mức sự cố, hậu quả dữ liệu, quyền thông báo. |
| Bổ sung kỹ năng, tuyển dụng, thay cơ cấu | Người có thẩm quyền quản lý nhân sự/đầu tư. | Developers, Scrum Master, Product Owner và người bị ảnh hưởng. | Năng lực dài hạn, pháp lý lao động và kế hoạch sản phẩm. |
| Tháo trở ngại liên phòng ban về ngân sách/quy định | Nhà bảo trợ hoặc người có quyền về vấn đề đó. | Những nhóm phụ thuộc và người chịu trách nhiệm kiểm soát. | Không tự bỏ kiểm soát bắt buộc khi đơn giản hóa. |

**Cảnh báo:** “Người ra quyết định chính” trong bảng không có nghĩa mọi tổ chức dùng Scrum phải có đúng những chức danh quản lý ngoài Scrum. Tên vai trò ngoài **Product Owner, Developers, Scrum Master** tùy thực tế. Đừng áp bảng khi nó mâu thuẫn với quyền pháp lý hoặc hợp đồng.

### 6.2. RACI, DACI, RAPID là hỗ trợ, không phải mục tiêu

Các công cụ phân quyền có thể hữu ích:

- **RACI:** Responsible (thực hiện), Accountable (chịu trách nhiệm cuối), Consulted (được tham vấn), Informed (được thông báo).
- **DACI:** Driver (thúc đẩy), Approver (người chốt), Contributors (đóng góp), Informed (được biết).
- **RAPID:** Một khung phân vai trong quyết định gồm các nhiệm vụ đề xuất, đồng ý theo phạm vi, thực hiện, cung cấp dữ liệu và chốt quyết định.

Chúng có **những định nghĩa/biến thể khác nhau tùy tổ chức**. Không nên trộn ba khung rồi kết luận “mỗi quyết định phải có đúng một chữ A là Product Owner”. Với Scrum, **accountabilities chính thức của Scrum Guide không biến mất** vì một bảng quản trị được vẽ.

Một công cụ đủ tốt giúp trả lời:

1. **Ai có quyền chốt?**
2. **Ai phải cung cấp bằng chứng hoặc được tham vấn vì ảnh hưởng?**
3. **Ai thực thi trong phạm vi quyền nào?**
4. **Nếu vượt ranh giới thì leo thang đến ai và trong điều kiện nào?**
5. **Quyết định được lưu/chia sẻ ra sao để không phải xin lại?**

### 6.3. “Tham vấn” không nhất thiết là “phê duyệt”

Với thay đổi nhỏ của giao diện, nhóm có thể **tham vấn** chuyên gia accessibility và người dùng, nhưng không phải mọi người được hỏi đều có **quyền phủ quyết vô hạn**. Ngược lại, với dữ liệu nhạy cảm, một ý kiến bảo mật có thể đi kèm **quyền phê duyệt hoặc chặn thực sự do nghĩa vụ áp dụng**.

Cần công khai sự khác biệt để tránh hai cực đoan: **duyệt mọi thứ ở mọi cấp** hoặc **bỏ mọi kiểm soát vì gọi đó là Agile**.

### 6.4. Ví dụ decision charter một trang

~~~yaml
product: "Nền tảng đặt lịch tư vấn"
product_goal: "Khách đặt và tra cứu lịch hợp lệ, rõ trạng thái"
investment_boundaries:
  - "Trong ngân sách và mục tiêu sản phẩm được phê duyệt"
  - "Các chi phí vượt hạn mức phải chuyển cấp có thẩm quyền"
decision_rights:
  backlog_order: "Product Owner"
  sprint_plan: "Developers cùng Scrum Team theo Scrum Guide"
  technical_implementation: "Developers trong tiêu chuẩn kỹ thuật"
  sensitive_data_controls: "Vai trò có thẩm quyền bảo mật/pháp lý"
  production_release: "Vai trò release/operations được tổ chức ủy quyền"
guardrails:
  - "Không bỏ Definition of Done để giữ deadline"
  - "Không tạo lịch trùng hoặc sai trạng thái dữ liệu"
  - "Không dùng dữ liệu cá nhân production cho demo tùy tiện"
escalation:
  - "Rủi ro đang gây hại: đường ứng cứu sự cố"
  - "Xung đột ưu tiên sản phẩm: Product Owner làm rõ đánh đổi"
  - "Vượt ngân sách/chiến lược: cấp đầu tư có thẩm quyền"
  - "Xung đột quyền kiểm soát: người phụ trách chính sách thích hợp"
review_trigger: "Sau một vòng thử hoặc khi có thay đổi rủi ro lớn"
~~~

Đây là **mẫu minh họa**, không phải chính sách được cấp thẩm quyền của một công ty thật. Một decision charter nên **ngắn, dễ tìm, được những người liên quan hiểu, có điểm xem lại**, thay vì chỉ được ký rồi cất trong kho tài liệu.

## 7. Hiểu đúng trách nhiệm và quyền tự quản trong Scrum

### 7.1. Một Scrum Team tự quản không phải tổ chức không có lãnh đạo

Theo *Scrum Guide 2020*, Scrum Team gồm **Product Owner, Scrum Master và Developers**. Scrum Team **self-managing**: họ quyết định nội bộ *ai làm gì, khi nào và như thế nào* trong khuôn khổ trách nhiệm, Product Goal, Sprint Goal, tiêu chuẩn chất lượng và điều kiện tổ chức.

Điều này không xóa các quyền về **ngân sách, tuyển dụng, pháp lý, bảo mật hoặc quản trị vận hành**. Chuyển đổi cần phân biệt **quyền nhóm tự quản đối với công việc** với **thẩm quyền tổ chức đối với điều kiện và giới hạn**.

Một nhà quản lý hỗ trợ hiệu quả có thể đặt câu hỏi: “Các bạn cần tôi tháo điều gì để làm được điều nhóm đã chọn?” thay vì “Tôi phân công từng story và duyệt từng ước lượng.”

### 7.2. Product Owner chịu trách nhiệm giá trị nhưng không phải người duyệt mọi thay đổi

Product Owner chịu trách nhiệm tối đa hóa **giá trị sản phẩm do Scrum Team tạo ra** và quản lý hiệu quả Product Backlog. Những trách nhiệm gắn với Product Backlog gồm:

- Phát triển và truyền đạt Product Goal một cách rõ ràng.
- Tạo và truyền đạt Product Backlog Items.
- Sắp thứ tự Product Backlog Items.
- Bảo đảm Product Backlog minh bạch, có thể thấy và được hiểu.

Product Owner **có thể ủy quyền việc thực hiện** các hoạt động nhưng **vẫn chịu trách nhiệm cuối**. Họ là **một người**, không phải hội đồng; có thể đại diện nhu cầu nhiều stakeholder, song quyết định giá trị cần đủ nhất quán.

**Ví dụ đúng:** Sau Sprint Review cho thấy khách không hiểu trạng thái Pending, Product Owner đưa một PBI làm rõ trạng thái lên trên SMS và giải thích đánh đổi. Lãnh đạo đã ủy quyền trong giới hạn ngân sách/chiến lược nên không buộc phải xin lại ba cấp duyệt cho thay đổi trong Product Backlog.

**Giới hạn đúng:** Product Owner không thể chỉ vì muốn ra tính năng nhanh mà yêu cầu bỏ kiểm tra bảo mật bắt buộc hoặc ghi lịch Confirmed khi chưa có trạng thái có thẩm quyền.

### 7.3. Developers chịu trách nhiệm tạo Increment đủ chất lượng

Developers chịu trách nhiệm:

- Tạo kế hoạch của Sprint, tức **Sprint Backlog**.
- Đảm bảo chất lượng bằng cách tuân thủ **Definition of Done**.
- Thích ứng kế hoạch mỗi ngày để hướng tới **Sprint Goal**.
- Có trách nhiệm lẫn nhau trong tư cách người làm nghề.

Lãnh đạo cần tạo điều kiện để Developers **chọn giải pháp kỹ thuật phù hợp, phối hợp kiểm thử và điều chỉnh cách làm**. Đồng thời, Developers cần giữ minh bạch về năng lực, rủi ro, dữ liệu và tiến độ; **tự quản không phải quyền tự ý tạo thiệt hại hoặc bỏ cam kết chất lượng**.

### 7.4. Scrum Master giúp hiệu quả Scrum, không phải “sếp của nhóm”

Scrum Master chịu trách nhiệm giúp Scrum được thiết lập đúng như Scrum Guide và giúp **Scrum Team tăng hiệu quả**. Trong chuyển đổi, họ có thể hỗ trợ:

- Dạy và giúp các bên hiểu Scrum và empiricism.
- Giúp nhóm cải thiện tự quản, đa chức năng và khả năng tập trung tạo Increment.
- Hỗ trợ tháo trở ngại ảnh hưởng tiến độ Scrum Team.
- Hỗ trợ Product Owner làm rõ Product Goal và kỹ thuật quản lý Product Backlog.
- Giúp tổ chức hiểu, chấp nhận và áp dụng Scrum phù hợp; hỗ trợ tương tác giữa stakeholder và Scrum Team.

Scrum Master **không tự động có quyền ưu tiên Product Backlog, chỉ định task, duyệt thiết kế hoặc thay đổi chính sách công ty**. Nếu trở ngại vượt quyền nhóm, họ có thể giúp đưa vấn đề tới người có thẩm quyền và theo dõi cách giải quyết.

### 7.5. Sprint Goal giúp thích ứng mà không rơi vào tùy tiện

**Sprint Goal** là mục tiêu duy nhất của Sprint, cam kết của Sprint Backlog. Trong Sprint, **không được thay đổi gây nguy hiểm cho Sprint Goal; chất lượng không giảm; Product Backlog được làm rõ khi cần; phạm vi có thể được làm rõ và thương lượng với Product Owner khi học thêm**.

Giả sử Sprint Goal là “Khách thấy trạng thái đặt lịch rõ ràng và an toàn khi mạng chậm”. Developers phát hiện API đối tác không hỗ trợ retry như giả định. Họ không nên cố hoàn thành mọi ticket ban đầu bằng cách hiển thị kết quả giả. Thay vào đó, **trao đổi về phạm vi an toàn** có thể đạt Sprint Goal, làm rõ phần chưa xong và cập nhật dự báo.

Quản lý hỗ trợ đúng sẽ ưu tiên **mục tiêu và khả năng thích ứng** thay vì ép nhóm giữ tất cả tasks ban đầu bất chấp sự thật mới.

### 7.6. Nhiều Scrum Team cùng làm một sản phẩm

Khi nhiều Scrum Team cùng làm **một sản phẩm**, theo Scrum Guide họ nên **chia sẻ cùng Product Goal, Product Backlog và Product Owner**; những Scrum Team này cũng phải **cùng định nghĩa và tuân thủ một Definition of Done**. Có thể có Sprint Backlog và Sprint Goal của từng Scrum Team, nhưng Increment cần **tích hợp**.

Lãnh đạo tạo điều kiện:

- Ranh giới sản phẩm và trách nhiệm giá trị rõ.
- Các nhóm đủ năng lực liên chức năng, không chia cắt công việc khiến ai cũng chờ.
- Tiêu chuẩn chất lượng và môi trường tích hợp dùng chung phù hợp.
- Quyền tham vấn và xử lý phụ thuộc giữa các nhóm.
- Cơ chế quản lý đầu tư không biến mỗi nhóm thành một sản phẩm giả với ưu tiên đối nghịch.

**Không phải tổ chức nhiều nhóm là phải lập thêm một “chief Product Owner” hoặc hội đồng thay PO.** Những mô hình điều phối mở rộng có thể là lựa chọn, nhưng phải minh bạch và không nhầm với các vai trò chính thức của Scrum cơ bản.

## 8. Trao quyền trong giới hạn rõ: autonomy with guardrails

### 8.1. Hai thái cực đều có hại

**Kiểm soát quá mức:** Mọi thay đổi nhỏ phải xin duyệt qua nhiều cấp. Hậu quả là decision latency cao, chờ đợi, ngại nêu vấn đề và ít thích ứng theo phản hồi.

**Buông kiểm soát:** “Đã Agile thì tự quyết hết.” Nhóm không biết quyền truy cập dữ liệu, hạn mức ngân sách, chuẩn bảo mật hay ai chịu trách nhiệm khi có incident. Hậu quả có thể là rủi ro pháp lý, bảo mật và trách nhiệm chồng chéo.

**Mô hình hữu ích:** Lãnh đạo công khai **mục tiêu, nguồn lực, tiêu chuẩn và ngưỡng**, sau đó để người có thông tin và chuyên môn phù hợp tự quyết trong ranh giới. Khi vượt ranh giới, họ biết **đường leo thang ngắn và người có quyền chốt**.

### 8.2. Những guardrails thường cần

| Guardrail | Ví dụ | Ai cần hiểu rõ? |
| --- | --- | --- |
| **Product Goal / ranh giới giá trị** | Thay đổi phục vụ đặt lịch tự phục vụ và tin cậy, không tự chuyển toàn bộ đầu tư sang sản phẩm khác. | Product Owner, Developers, lãnh đạo, stakeholder. |
| **Ngân sách và mua sắm** | Team có thể dùng dịch vụ nội bộ đã duyệt trong hạn mức; vượt ngưỡng cần người có quyền đầu tư. | PO, engineering, tài chính/mua sắm. |
| **An toàn dữ liệu và quyền riêng tư** | Không dùng dữ liệu khách thật trong demo nếu không có cơ sở và kiểm soát thích hợp. | Tất cả người thu thập, xử lý hoặc kiểm thử dữ liệu. |
| **Bảo mật kỹ thuật** | Các thay đổi quyền truy cập phải đạt kiểm tra thích hợp; không bỏ vì deadline. | Developers, bảo mật, vận hành. |
| **Chất lượng/DoD** | Không gọi Increment Done khi kiểm thử quan trọng còn thiếu. | Scrum Team và những người nhận kết quả. |
| **Phát hành** | Mở rộng rollout khi đáp ứng tiêu chí chất lượng, có giám sát và phương án xử lý sự cố. | Vai trò release/vận hành, PO, Developers. |
| **Con người** | Không dùng “tăng velocity” để ép làm thêm giờ liên tục; có quy tắc hỗ trợ và bảo vệ nhân viên. | Lãnh đạo, quản lý, Scrum Team. |
| **Hợp đồng đối tác** | Không tự thay API hoặc điều khoản vượt quyền của nhóm. | Nhóm tích hợp, người chịu trách nhiệm đối tác. |

Guardrails cần **diễn đạt có thể thực hiện**: “dữ liệu test phải được tạo từ fixture an toàn” rõ hơn “hãy cẩn thận với dữ liệu”. Một quy tắc quá mơ hồ sẽ khiến Developers phải hỏi lại mỗi lần.

### 8.3. Từ quyền xin phép sang quyền tự thực hiện có kiểm chứng

Ví dụ hiện trạng: mỗi thay đổi cấu hình test cần một quản lý duyệt bằng email vì “tránh rủi ro”. Nhóm đề xuất:

1. Phân loại rõ **cấu hình sandbox ít rủi ro** và **thay đổi production quan trọng**.
2. Chuẩn hóa quyền, ghi log, kiểm tra tự động và phạm vi tài nguyên.
3. Cho nhóm tự tạo dữ liệu/test environment trong **hạn mức và mẫu đã duyệt**.
4. Giữ đường kiểm soát chuyên môn cho trường hợp **vượt ngưỡng**.
5. Đo blocked time, lỗi cấu hình và chi phí trước/sau.

Đây là **thay đổi hệ thống quản trị**, không chỉ một yêu cầu Developers “làm nhanh hơn”.

### 8.4. “Quyền từ chối” là một phần của trách nhiệm chuyên môn

Một Developer nhận thấy cách triển khai sẽ tạo lịch trùng trong trường hợp gửi lặp. Họ cần có đường để nói:

> “Phương án hiện tại vi phạm bất biến đặt lịch; chúng tôi cần kiểm chứng retry trong môi trường an toàn trước khi đưa vào production.”

Điều đó không có nghĩa bất kỳ cá nhân nào cũng có quyền **veto vô hạn vì sở thích**. Tổ chức cần tiêu chuẩn kỹ thuật, người đánh giá có chuyên môn và cách giải quyết bất đồng dựa trên bằng chứng. Khi liên quan rủi ro dữ liệu/bảo mật thực, **không dùng quyền ưu tiên kinh doanh để phủ quyết cảnh báo an toàn một cách tùy tiện**.

### 8.5. Một ví dụ điều chỉnh thẩm quyền theo cấp độ

~~~text
Thay copy UI với dữ liệu giả, trong Product Goal và chuẩn accessibility?
  -> Nhóm có thể thử theo quyền được ủy quyền, đo khả năng hiểu.

Thay hợp đồng trạng thái API giữa hai nhóm?
  -> Chủ sở hữu/consumer cùng làm rõ, contract tests, tích hợp.

Mua dịch vụ cloud vượt hạn mức đã duyệt?
  -> Người có thẩm quyền đầu tư/mua sắm quyết định sau khi có bằng chứng.

Thay xử lý transaction với dữ liệu khách thật?
  -> Phải tuân thủ kiểm thử, tiêu chuẩn an toàn và quy trình release áp dụng.

Phát hiện lỗi tạo lịch trùng đang gây thiệt hại?
  -> Kích hoạt incident response ngay theo quyền ứng cứu, không đợi backlog.
~~~

## 9. Lãnh đạo hỗ trợ bằng cơ cấu, năng lực và thời gian

### 9.1. Nhóm được “trao quyền” nhưng không có năng lực là trao trách nhiệm rỗng

Một Product Owner có quyền sắp thứ tự backlog nhưng không có ai đủ khả năng sửa API đối tác có thể **không tạo ra kết quả**. Developers được tự chọn giải pháp nhưng môi trường test chỉ người ngoài cấp quyền cũng vẫn bị chặn.

Lãnh đạo cần đánh giá **quyền quyết định có đi cùng năng lực và nguồn lực không**:

- Đủ kỹ năng để tạo Increment: phát triển, kiểm thử, hiểu miền, bảo mật, vận hành khi cần.
- Cách chia sẻ tri thức để tránh một chuyên gia thành nút thắt.
- Quyền truy cập công cụ/môi trường phù hợp, có kiểm soát.
- Thời gian cho refinement, kiểm thử, refactoring và cải tiến liên tục.
- Khả năng tiếp cận stakeholder và người dùng thật theo chính sách.
- Ngân sách hạ tầng, giám sát và trả nợ kỹ thuật có chứng cứ.
- Cơ chế giải quyết các phụ thuộc liên nhóm.

### 9.2. Ưu tiên nhóm đủ ổn định để học về cùng một sản phẩm

Nếu một Developer phải tham gia bốn dự án, đổi ngữ cảnh liên tục và không biết Product Goal nào quan trọng hơn, việc yêu cầu họ “tăng velocity” hiếm khi giải quyết được nút thắt.

Một nhóm đủ ổn định có thể:

1. Hiểu miền và người dùng sâu hơn.
2. Giữ trách nhiệm với chất lượng sau phát hành.
3. Nhận phản hồi và cải tiến cách làm dựa trên dữ liệu của **cùng workflow**.
4. Xây quan hệ tin cậy và chia sẻ tri thức.
5. Giảm thời gian chuyển giao và chờ người ngoài nhóm.

Điều đó **không có nghĩa cấm mọi thay đổi nhân sự**. Tổ chức vẫn cần điều chỉnh năng lực; quan trọng là tính tới chi phí chuyển ngữ cảnh, rủi ro tri thức và thời gian học khi lên kế hoạch.

### 9.3. Gỡ phụ thuộc tổ chức thay vì buộc nhóm chịu đựng

| Cơ chế hiện tại | Tác động lên Agile | Cải tiến có thể thử |
| --- | --- | --- |
| Mỗi team phụ thuộc một QA tập trung vào cuối Sprint. | Test dồn cuối, feedback trễ. | Chia sẻ kỹ năng test sớm, CI, tiêu chuẩn kiểm thử và năng lực hỗ trợ phù hợp. |
| Mọi database migration phải đợi một người duyệt. | PBI nhỏ thường chờ nhiều ngày. | Tạo tiêu chuẩn migration, review theo rủi ro và người dự phòng. |
| Một nhóm giao diện có nhiều Product Owners cạnh tranh. | Mọi yêu cầu được coi là khẩn. | Xác định Product Goal, quyền quyết định thứ tự và cơ chế intake. |
| Công cụ release cố định mỗi tháng, bất kể rủi ro. | Increment Done vẫn chờ tới khách. | Đánh giá đường phát hành ít rủi ro với kiểm tra tự động, giám sát và rollback phù hợp. |
| Ngân sách chỉ cấp theo dự án có phạm vi khóa. | Phản hồi mới khó thay đổi đầu tư. | Xem khả năng phân bổ theo mục tiêu sản phẩm và các điểm review định kỳ. |

Những cải tiến phải phù hợp bối cảnh. Một hệ thống chịu yêu cầu quản lý nghiêm ngặt có thể cần bằng chứng và người phê duyệt chuyên môn khác hệ thống nội bộ ít rủi ro; **không sao chép đường release liên tục của nơi khác mà bỏ nghĩa vụ áp dụng**.

### 9.4. Dành năng lực cho việc cần thiết nhưng không trực tiếp là feature

Chuyển đổi Agile thường thất bại khi kế hoạch chỉ ghi **feature người dùng nhìn thấy**, còn hạ tầng test, chất lượng, bảo mật, giám sát, nợ kỹ thuật và học cách làm mới phải tranh thời gian “ngoài giờ”.

Một số hạng mục có thể được ưu tiên vì **giúp sản phẩm giao giá trị bền vững**:

- Test chống tạo lịch trùng trong tình huống concurrent requests.
- Bộ fixture dữ liệu giả cho integration tests.
- Kiểm thử hợp đồng API đối tác.
- Cải thiện observability cho Pending/Unknown.
- Refactor điểm coupling đang làm mọi thay đổi lan sang nhiều mô đun.
- Huấn luyện chung một quy tắc nghiệp vụ phức tạp.

Người chịu trách nhiệm giá trị và Developers cần **minh bạch chi phí cơ hội**. Không nên gọi mọi đề nghị công nghệ là “nợ kỹ thuật bắt buộc”; cũng không nên bác bỏ mọi việc không tạo UI ngay hôm nay là “không có giá trị”.

### 9.5. Hạn mức năng lực là giả định, không phải luật 20%

Một đội có thể tạm dự trù năng lực cho incident/support và cải tiến kỹ thuật dựa trên dữ liệu lịch sử. Nhưng không có quy tắc Scrum bắt buộc “mỗi Sprint 20% nợ kỹ thuật, 10% discovery, 70% feature”.

Nếu có sự cố nghiêm trọng, tỷ trọng khắc phục có thể tăng; nếu đang thử Product Goal mới cần discovery, tỷ trọng học có thể tăng. **Lãnh đạo hỗ trợ khi cho phép điều chỉnh phân bổ theo bằng chứng**, không xem mọi thay đổi tỷ lệ là thất bại kỷ luật.

## 10. Hành vi lãnh đạo giúp xây năng lực ra quyết định

### 10.1. Hỏi về kết quả và rủi ro, không hỏi ai đang bận nhất

| Câu hỏi tạo kiểm soát vi mô | Câu hỏi thúc đẩy tự chủ có trách nhiệm |
| --- | --- |
| “Vì sao hôm nay bạn chỉ đóng hai ticket?” | “Điều gì đang ngăn một lát cắt có giá trị đi tới Done?” |
| “Ai là người gây trễ?” | “Chúng ta đang chờ quyết định hoặc thông tin ở đâu?” |
| “Có giữ đúng mọi hạng mục đã hứa không?” | “Sprint Goal và chất lượng có được bảo vệ khi học thêm không?” |
| “Bao giờ mọi người bận 100%?” | “WIP và hàng đợi đang ảnh hưởng cycle time toàn hệ thống thế nào?” |
| “Hãy chuyển sang Scrum ngay tháng sau.” | “Vấn đề hiện tại nào Scrum/Kanban/XP có thể giúp chúng ta giải quyết?” |
| “Thử không thành công thì ai chịu trách nhiệm?” | “Giả thuyết nào bị bác bỏ và quyết định tiếp theo đã rõ chưa?” |
| “Tại sao PO không xin duyệt?” | “Quyết định này có nằm trong ranh giới đã ủy quyền không?” |

Lãnh đạo vẫn cần **kỳ vọng, trách nhiệm và năng lực đánh giá**. Câu hỏi tốt giúp họ thấy kết quả và hệ thống thay vì tạo áp lực làm đẹp dữ liệu.

### 10.2. Psychological safety không đồng nghĩa thiếu tiêu chuẩn

Một môi trường có **an toàn tâm lý** giúp người tham gia nêu rủi ro, nhận mình chưa biết, báo lỗi hoặc đề xuất thay đổi mà không sợ bị sỉ nhục hay trừng phạt tùy tiện. Điều này đặc biệt quan trọng khi chuyển từ “làm đúng kế hoạch” sang “học từ thực tế”.

Nhưng an toàn tâm lý **không thay thế trách nhiệm nghề nghiệp**. Người làm vẫn cần:

- Tuân thủ quy tắc bảo mật và chất lượng.
- Báo lỗi/cảnh báo dựa trên thông tin có thật.
- Giải thích quyết định, giữ bằng chứng và tham gia khắc phục.
- Nhận phản hồi chuyên môn và cải tiến kỹ năng.
- Chịu trách nhiệm theo chính sách phù hợp khi cố ý vi phạm hoặc bỏ qua rủi ro nghiêm trọng.

Mục tiêu là **phân biệt sai lầm do giả thuyết được kiểm thử có trách nhiệm** với **hành vi liều lĩnh hoặc che giấu**.

### 10.3. Lãnh đạo làm gương khi giả thuyết của chính mình sai

Giả sử lãnh đạo từng tin rằng tăng họp cập nhật trạng thái sẽ rút ngắn cycle time. Một thử nghiệm hai tuần cho thấy không có lợi ích và Developers mất thời gian tập trung.

Cách làm mẫu:

1. Công nhận giả thuyết ban đầu chưa được hỗ trợ.
2. Cùng nhóm kiểm tra thời gian chờ thật và loại việc.
3. Dừng cuộc họp không tạo giá trị, giữ phương thức chia sẻ thông tin cần thiết.
4. Thử cách tháo phụ thuộc đúng nơi.
5. Công khai bài học, không tìm người để đổ lỗi.

Nếu lãnh đạo có thể **thay đổi quyết định dựa trên bằng chứng** mà không mất uy tín, Developers và Product Owner cũng dễ hành xử tương tự.

### 10.4. Giữ cam kết ở cấp mục tiêu, chấp nhận thích ứng phương tiện

Lãnh đạo có thể kiên định với **mục tiêu kết quả** như giảm lỗi xác nhận lịch và tăng tự phục vụ, đồng thời cho phép thay giải pháp từ SMS sang tra cứu trạng thái nếu bằng chứng cho thấy SMS không giải quyết vấn đề.

Giữ cam kết khác với **khóa mọi tính năng và ngày từ lúc chưa hiểu API đối tác**. Khi thông tin mới xuất hiện, nhóm cần thảo luận phạm vi, đầu tư, rủi ro và dự báo thay vì giấu bất định để giữ vẻ “đúng kế hoạch”.

### 10.5. Không giao KPI cá nhân trái mục tiêu sản phẩm

Nếu Product Owner được thưởng theo **số tính năng hoàn thành**, còn Developers bị đánh giá theo **story points**, còn vận hành bị phạt theo **số lần triển khai**, các bên có thể làm đúng KPI của mình nhưng sản phẩm **ít được giao, ít phản hồi và nhiều rủi ro**.

Cần xem hệ thống đánh giá có vô tình khuyến khích:

- Đẩy việc chưa Done sang nhóm khác.
- Chia ticket thành mảnh nhỏ để tăng số lượng.
- Trì hoãn phát hành dù đã đủ an toàn.
- Che sự cố, né phản hồi tiêu cực.
- Làm thêm giờ liên tục để giữ cam kết bất khả thi.
- Tranh quyền ưu tiên thay vì hợp tác giải quyết Product Goal.

**Không nên dùng một metric đơn lẻ để thưởng/phạt người**. Đo outcome, flow và chất lượng ở cấp phù hợp rồi dùng nó để học và cải thiện hệ thống.

## 11. Ngân sách, portfolio và cách đầu tư phải cho phép học

### 11.1. Ngân sách dự án cố định có thể xung đột với việc thích ứng

Một mô hình đầu tư truyền thống có thể chỉ cho phép chi nếu đúng **danh sách hạng mục đã chốt một năm trước**. Khi khách cần tra cứu trạng thái thay vì SMS, Product Owner phải viết hồ sơ thay đổi dự án mất vài tháng. Tổ chức nói “ưu tiên phản hồi khách hàng” nhưng ngân sách lại **trừng phạt việc đổi hướng sau khi học**.

Lãnh đạo có thể xem lại:

- Đầu tư theo **mục tiêu sản phẩm/vấn đề** thay vì chỉ theo dự án với phạm vi khóa.
- Các **điểm kiểm tra giá trị và rủi ro** để quyết định tiếp tục/điều chỉnh đầu tư.
- Hạn mức ủy quyền cho Product Owner và nhóm trong phạm vi đã được duyệt.
- Quy tắc kiểm soát thay đổi lớn có ảnh hưởng tài chính/chiến lược.
- Cách lập dự báo theo **mức bất định** thay vì bắt mọi chi tiết có ngày chắc chắn.

Không phải mọi công ty có thể đổi ngay ngân sách sang mô hình khác. Có thể bắt đầu bằng **một sản phẩm và một khoảng đầu tư giới hạn**, trong khi vẫn tuân thủ cam kết tài chính hiện hành.

### 11.2. Phân biệt quyết định giữa các sản phẩm và trong một sản phẩm

**Cấp portfolio/chiến lược** có thể quyết định:

- Có nên tăng đầu tư cho nền tảng đặt lịch so với sản phẩm khác?
- Mục tiêu kinh doanh/khách hàng ưu tiên trong kỳ?
- Giới hạn ngân sách và rủi ro doanh nghiệp?
- Khi nào dừng một khoản đầu tư không tạo giá trị?

**Cấp sản phẩm**, Product Owner trong Scrum chịu trách nhiệm Product Backlog:

- Giải quyết Pending trước hay SMS?
- Thử nghiệm giả thuyết khách dùng app hay cần tổng đài?
- Làm lát cắt đổi lịch cơ bản hay thêm khả năng khác?

**Cấp kỹ thuật và thực thi**, Developers:

- Thiết kế hợp đồng/API/test thế nào để giữ bất biến?
- Cắt nhỏ công việc, tích hợp và xử lý dependency ra sao?
- Điều chỉnh Sprint Backlog để hướng tới Sprint Goal thế nào?

Không nên để cuộc họp portfolio **trở thành nơi phê duyệt từng thay đổi PBI**, cũng không để Product Owner **quyết định đầu tư cho sản phẩm khác** vượt thẩm quyền.

### 11.3. “Đã chi tiền” không phải lý do tiếp tục không có giá trị

Giả sử đã đầu tư một phần vào SMS nhắc lịch, nhưng sử dụng thử và dữ liệu hỗ trợ cho thấy khách cần **biết lịch đã Confirmed**, không phải nhận thêm kênh. Lãnh đạo có thể muốn tiếp tục SMS vì “đã bắt đầu”.

Đây là bẫy **sunk cost**: chi phí đã bỏ ra không tự làm tăng giá trị của phần còn lại. Quyết định hợp lý xem:

- Giá trị/rủi ro dự kiến **từ thời điểm này**.
- Chi phí còn phải chi và các lựa chọn thay thế.
- Các nghĩa vụ hợp đồng/chuyển đổi còn hiệu lực.
- Khả năng tái sử dụng, dừng hoặc giảm phạm vi an toàn.

Một chương trình chuyển đổi Agile tốt cho phép **dừng hoặc xoay hướng khi bằng chứng đủ**, không ép nhóm hoàn tất feature ít giá trị để làm đẹp kế hoạch.

### 11.4. Bảo trợ có thể cấp “ngân sách cho học” có điều kiện

Thay vì cấp kinh phí lớn để viết lại toàn hệ thống, lãnh đạo có thể phê duyệt **một discovery/spike có timebox** nhằm trả lời:

> “API đối tác có hỗ trợ retry/idempotency an toàn để tự động đổi lịch không?”

Đầu ra của khoản đầu tư nhỏ là **bằng chứng cho quyết định tiếp theo**, không phải lượng code. Nếu kết quả cho thấy API không phù hợp, nhóm có thể **đổi thiết kế, chọn đối tác khác hoặc giảm phạm vi** trước khi đầu tư lớn.

### 11.5. Dự báo là thông tin ra quyết định, không phải hợp đồng giả chắc

Một báo cáo tốt phân biệt:

- **Đã giao:** Increment nào đạt DoD và đã được sử dụng?
- **Dự kiến với dữ liệu:** Dựa trên throughput/cycle time/khả năng hiện tại, lựa chọn nào có thể hoàn tất trong phạm vi thời gian?
- **Phụ thuộc/bất định:** Thông tin API, chính sách, dữ liệu hay năng lực nào chưa rõ?
- **Tín hiệu đổi hướng:** Nếu giả thuyết sai hoặc rủi ro tăng, quyết định sẽ thay thế ra sao?

**Không biến mọi dự báo thành lời hứa tuyệt đối** khi thông tin còn thiếu; cũng không dùng “Agile linh hoạt” làm lý do né việc báo mức rủi ro và cập nhật dự báo thường xuyên.

## 12. Quản trị rủi ro, tuân thủ và phát hành không đối lập với Agile

### 12.1. Agile không có nghĩa bỏ governance

Một hệ thống đặt lịch có thể xử lý dữ liệu cá nhân, thông tin nhạy cảm và các nghĩa vụ với nhà cung cấp. Tổ chức phải hiểu **những ràng buộc thực** và ai có quyền xác nhận chúng.

Một chương trình chuyển đổi đúng hướng **làm governance rõ và theo rủi ro hơn**:

- Mục tiêu và quyền quyết định được công khai.
- Các kiểm tra bắt buộc có bằng chứng, tiêu chí rõ.
- Kiểm soát lặp lại có thể tự động hóa khi phù hợp.
- Những thay đổi rủi ro thấp được xử lý nhanh trong giới hạn.
- Những thay đổi rủi ro cao có đánh giá chuyên môn và quyền chặn cần thiết.
- Sau phát hành có giám sát, phản hồi và cải tiến.

**Không có một “ngoại lệ Agile” cho nghĩa vụ pháp lý hoặc bảo mật.** Thay đổi cấu trúc phê duyệt phải do cấp có thẩm quyền thực hiện.

### 12.2. Thiết kế đường quyết định phát hành theo rủi ro

| Tình huống | Điều cần kiểm tra | Quyền quyết định |
| --- | --- | --- |
| Sửa lỗi chính tả trong nội dung công khai, ít rủi ro. | Đúng nội dung, accessibility, kiểm tra phù hợp. | Theo quyền release đã ủy quyền cho loại thay đổi thấp rủi ro. |
| Bổ sung trạng thái Pending. | Semantics, contract tests, quyền, test tích hợp, monitoring. | Theo quy trình release và năng lực vận hành đã duyệt. |
| Thay transaction chống trùng. | Bất biến dữ liệu, test cạnh tranh, migration, rollback/đối soát. | Người có thẩm quyền release/kỹ thuật và đánh giá rủi ro áp dụng. |
| Thu dữ liệu hành vi người dùng. | Mục đích, tối thiểu hóa, đồng ý/cơ sở phù hợp, lưu trữ, truy cập. | Vai trò sản phẩm/nghiên cứu/bảo mật/pháp lý theo chính sách. |
| Ứng cứu lỗi production nghiêm trọng. | Giảm thiệt hại, dữ liệu bị ảnh hưởng, khôi phục, thông báo cần thiết. | Người có quyền ứng cứu theo mức sự cố; không chờ họp Scrum. |

Trong Scrum, **Sprint Review không phải cổng phê duyệt phát hành bắt buộc**. Increment có thể được giao trước Review nếu đạt Definition of Done và các điều kiện vận hành/pháp lý áp dụng. Một demo đẹp không làm tính năng chưa đạt DoD trở thành Done.

### 12.3. Điều kiện dừng và quyền ứng cứu phải cụ thể

Nếu một pilot tạo lịch trùng hoặc gửi thông báo sai trạng thái, cần biết:

1. Ai **có quyền dừng rollout ngay**?
2. Ai điều tra và đối soát dữ liệu?
3. Ai quyết định thông báo/hỗ trợ khách theo nghĩa vụ?
4. Có thể rollback hành vi phần mềm đến đâu, hậu quả nào cần bù trừ?
5. Ai xác nhận điều kiện mở lại?
6. Hạng mục phòng ngừa và bài học đưa vào Product Backlog/cách làm thế nào?

**Tắt feature flag không tự thu hồi email đã gửi, giao dịch đã ghi hoặc dữ liệu đã lộ.** Vì vậy quyết định chuyển đổi về tốc độ release phải đi cùng khả năng vận hành và xử lý sự cố thật.

### 12.4. Chính sách rõ giảm thời gian chờ tốt hơn quyền “ngoại lệ”

Nếu mọi lần phát hành cần quản lý cấp cao cấp phép ngoại lệ, đội sẽ phụ thuộc vào quan hệ cá nhân và không mở rộng được năng lực.

Thay bằng:

- Chính sách phân loại thay đổi theo rủi ro.
- Tiêu chuẩn test/monitoring/rollback hoặc compensation cụ thể.
- Quyền tự thực hiện nếu đã đáp ứng ranh giới.
- Đường phê duyệt chuyên môn khi vượt ngưỡng.
- Dữ liệu về kết quả phát hành, lỗi và thời gian chờ để cải tiến.

**Không tự đổi chính sách khi chưa được phép**. Việc soạn phương án chỉ là bước đầu; sponsor và người chịu trách nhiệm kiểm soát phải quyết định việc ủy quyền mới.

## 13. Chuẩn bị phối hợp nhiều nhóm và các chức năng liên quan

### 13.1. Đa nhóm cần trách nhiệm sản phẩm thống nhất, không chỉ có nhiều Scrum Masters

Một tổ chức phát triển ứng dụng đặt lịch bằng ba nhóm: **A (trải nghiệm), B (Booking domain), C (tích hợp đối tác)**. Nếu mỗi nhóm có một danh sách ưu tiên độc lập, Product Goal “khách tự đặt lịch an toàn” có thể bị phá vỡ khi:

- A hoàn tất màn hình hiển thị “Thành công” nhưng B chưa xác nhận transaction.
- B xử lý đặt trùng nhưng C không biết quy tắc retry của đối tác.
- C làm SMS theo yêu cầu kinh doanh trong khi khách không thể tra cứu Pending.
- Mọi nhóm báo tỷ lệ Done cao, Increment end-to-end vẫn chưa dùng được.

**Lãnh đạo cần tháo xung đột cấu trúc**: cùng sản phẩm thì làm rõ Product Goal, Product Backlog, trách nhiệm Product Owner và Definition of Done chung (khi sử dụng Scrum). Có thể có board nội bộ theo nhóm nhưng không tạo ba nguồn ưu tiên sản phẩm cạnh tranh.

### 13.2. Tách thẩm quyền theo vấn đề, không theo ai đang chủ trì họp

| Tình huống liên nhóm | Quyền quyết định cốt lõi | Hình thức phối hợp |
| --- | --- | --- |
| A muốn thêm UI trước B/C. | Product Owner về thứ tự sản phẩm; Developers về khả năng tích hợp an toàn. | Làm rõ một lát cắt có giá trị, hợp đồng API và test. |
| B muốn refactor transaction. | Developers đánh giá thiết kế và tính đúng; Product Owner tham gia đánh đổi năng lực/giá trị. | Nêu bằng chứng coupling/rủi ro, PBI hoặc cải tiến kỹ thuật trong kế hoạch phù hợp. |
| C cần nâng hạn mức dịch vụ đối tác. | Vai trò có thẩm quyền hợp đồng/chi phí. | Nêu tính cần thiết, dự báo chi phí, rủi ro và lựa chọn thay thế. |
| Hai nhóm tranh một chuyên gia bảo mật. | Người có quyền phân bổ năng lực và kiểm soát rủi ro; PO nêu thứ tự giá trị sản phẩm. | Cân nhắc mức nghiêm trọng, điểm chặn và người dự phòng. |
| Một lỗi production tạo lịch trùng. | Đường ứng cứu theo mức sự cố. | Phối hợp nhóm kỹ thuật, vận hành, sản phẩm và bảo mật khi cần. |

**Quyền quyết định không tự xuất hiện từ chức danh “coordinator”.** Người điều phối có thể giúp mọi bên thấy phụ thuộc nhưng phải biết quyết định nào do ai chốt.

### 13.3. Tổ chức một cuộc xem phụ thuộc ngắn, đúng người

Một phiên phối hợp liên nhóm có thể chỉ hỏi:

1. **PBI kết quả** nào đang bị chặn và người dùng chịu ảnh hưởng gì?
2. **Điều kiện chặn cụ thể** là gì: hợp đồng API, dữ liệu test, chính sách hay năng lực?
3. **Ai có thông tin/quyền giải quyết**?
4. Bước nhỏ nhất để giảm bất định và thử tích hợp là gì?
5. Khi nào kiểm tra lại, và có phải cập nhật thứ tự/dự báo không?

Nếu không có phụ thuộc mới, không cần bắt mọi người dự cuộc họp dài. **Một bảng minh bạch và liên hệ trực tiếp đúng người** có thể hiệu quả hơn nhiều tầng báo cáo.

### 13.4. Chính sách chung không đồng nghĩa mọi nhóm dùng y hệt công cụ

Team A có thể sử dụng prototype và usability test, Team B dùng TDD và contract tests, Team C dùng sandbox và kiểm thử lỗi mạng. Không nhất thiết ép tất cả dùng cùng board chi tiết hay cùng số story points.

Điều cần thống nhất ở cấp sản phẩm là:

- Product Goal và thứ tự PBI.
- Nghĩa của các trạng thái nghiệp vụ và hợp đồng.
- Chuẩn Definition of Done/tiêu chí tích hợp.
- Cách phân loại, ứng cứu rủi ro và phát hành.
- Điểm đo outcome và flow end-to-end.
- Đường leo thang khi quyết định vượt giới hạn.

### 13.5. Không dùng phối hợp liên nhóm để thay quyền Product Owner

Một “hội đồng ba trưởng nhóm” có thể giúp nêu phụ thuộc. Nhưng nếu hội đồng này bỏ phiếu quyết định thứ tự Product Backlog cho cùng một sản phẩm và vô hiệu trách nhiệm PO, quyền quản lý giá trị trở nên không rõ trong Scrum.

Các stakeholder có quyền **đóng góp và tác động tới nhu cầu**. Product Owner cần lắng nghe và minh bạch đánh đổi, song **trách nhiệm thứ tự Product Backlog phải rõ**. Nếu cấp điều hành thật sự muốn đổi định hướng đầu tư, hãy công khai đó là quyết định chiến lược rồi điều chỉnh Product Goal/đường ưu tiên phù hợp, không lén sửa ticket.

## 14. Xây liên minh bảo trợ và truyền thông thay đổi

### 14.1. Một sponsor đơn lẻ thường không đủ tháo trở ngại liên chức năng

Nhiều rào cản Agile nằm ở giao điểm:

- Tài chính quyết định ngân sách/mua sắm.
- HR/quản lý quyết định lộ trình nghề nghiệp và tuyển dụng.
- An ninh thông tin quản lý tiêu chuẩn truy cập/dữ liệu.
- Vận hành kiểm soát release và ứng cứu.
- Product Owner xác định thứ tự giá trị sản phẩm.
- Developers chịu trách nhiệm chất lượng và thực thi kỹ thuật.

Nhà bảo trợ cần làm rõ **ai cùng cam kết thay đổi chính sách nào**. Nếu tài chính, bảo mật và vận hành chưa tham gia, một lời hứa “team sẽ deploy hằng ngày” có thể bất khả thi hoặc nguy hiểm.

### 14.2. Stakeholder map cho chương trình chuyển đổi

| Nhóm liên quan | Mối quan tâm điển hình | Điều cần làm rõ | Cách tham gia hữu ích |
| --- | --- | --- | --- |
| **Lãnh đạo cấp đầu tư** | Kết quả kinh doanh, rủi ro, chi phí. | Mục tiêu và giới hạn đầu tư; quyết định nào được ủy quyền. | Bảo trợ, điều chỉnh chính sách và xem bằng chứng giá trị. |
| **Product Owner / người làm sản phẩm** | Giá trị, người dùng, roadmap, Product Goal. | Quyền thực chất sắp thứ tự PBI và tương tác stakeholder. | Định hướng outcome, thu thập phản hồi, thay đổi backlog. |
| **Developers và chuyên gia kỹ thuật** | Kỹ năng, chất lượng, quyền thiết kế, công cụ. | Phạm vi tự quản, tiêu chuẩn và môi trường hỗ trợ. | Thiết kế thử nghiệm, Increment, kiểm thử và cải tiến. |
| **Engineering/people managers** | Năng lực, nghề nghiệp, duy trì nhân sự. | Trách nhiệm mới đối với hệ thống phát triển con người. | Huấn luyện, gỡ nút thắt, giảm chuyển ngữ cảnh. |
| **Bảo mật/pháp lý/compliance** | Nghĩa vụ và khả năng chứng minh kiểm soát. | Ngưỡng rủi ro, chứng cứ cần, quyết định nào được tự động hóa. | Thiết kế guardrails phù hợp và đường xử lý ngoại lệ. |
| **Vận hành/SRE/support** | Độ tin cậy, khách hàng, incident. | Quyền dừng/rollback, giám sát, hỗ trợ sau release. | Cùng thiết kế phát hành có kiểm soát và phản hồi. |
| **Khách hàng/đại diện người dùng** | Nhu cầu, khả năng sử dụng và sự tin cậy. | Cách tham gia nghiên cứu và bảo vệ thông tin. | Phản hồi qua demo, thử tác vụ và quan sát được phép. |

**Không phải mọi người cần ngồi trong mọi cuộc họp.** Tham vấn đúng lúc, với mục đích và quyền quyết định rõ, tốt hơn họp đông rồi chờ đồng thuận tuyệt đối.

### 14.3. Cách truyền đạt “vì sao” chuyển đổi

Một thông điệp khởi đầu có thể nói:

> “Chúng ta muốn người dùng đặt lịch nhanh hơn và an toàn hơn. Hiện một thay đổi nhỏ phải chờ nhiều lần duyệt, còn kiểm thử tích hợp phát hiện lỗi quá muộn. Trong phạm vi một sản phẩm, chúng ta sẽ thử làm rõ quyền ưu tiên của Product Owner, quyền quyết định kỹ thuật trong chuẩn chất lượng và đường phê duyệt theo mức rủi ro. Chúng ta sẽ đo outcome, thời gian chờ, lỗi và mức tải trước–sau; nếu phương án không giúp ích, chúng ta sẽ điều chỉnh. Không ai được bỏ qua các yêu cầu bảo mật hoặc làm thêm giờ vô hạn để đạt chỉ số.”

Thông điệp này chứa **mục đích, ranh giới, hành động, bằng chứng và trách nhiệm**. Nó khác câu “từ tháng sau tất cả phải Agile” chỉ nêu nhãn.

### 14.4. Nói rõ điều gì sẽ không thay đổi

Khi chuyển đổi, nhiều người lo rằng “trao quyền” nghĩa là:

- Không còn con đường nghề nghiệp/đánh giá minh bạch.
- Không còn ai chịu trách nhiệm về kiến trúc hoặc an toàn.
- Team phải tự lo toàn bộ hợp đồng, ngân sách và sự cố.
- Bị buộc nhận thêm công việc vì giờ có quyền tự chủ.
- Những người không thích nghi ngay sẽ bị quy là chống đối.

Lãnh đạo nên khẳng định cụ thể: **những nghĩa vụ bảo vệ người dùng và nhân viên vẫn áp dụng**, các quyết định nhân sự/đầu tư có thẩm quyền rõ, và mục tiêu chuyển đổi là **cải thiện hệ thống giao giá trị** chứ không giảm hỗ trợ.

### 14.5. Cần có kênh phản hồi cả về chính chương trình chuyển đổi

Một chương trình thay đổi chỉ dựa vào báo cáo của sponsor có thể không nhìn thấy rủi ro ở cấp nhóm. Nên có cách:

- Người làm công việc nêu trở ngại không sợ bị phạt vì báo tin xấu.
- Quản lý nêu trách nhiệm đang bị bỏ trống.
- Product Owner nêu xung đột ưu tiên và ngân sách.
- Người chịu trách nhiệm bảo mật nêu các phần chưa đủ bằng chứng.
- Nhóm phản hồi về cuộc họp/quy định mới có tạo giá trị hay không.

Quan trọng là **đóng vòng phản hồi**: ai xem, ai có quyền thay đổi, khi nào thông báo kết quả. Thu khảo sát rồi không đổi gì thường làm mất niềm tin.

## 15. Leo thang và giải quyết xung đột mà không quay lại kiểm soát vi mô

### 15.1. Khi nào cần leo thang?

Một quyết định nên được xử lý **gần nơi có đủ thông tin và quyền**. Leo thang khi:

- Vượt hạn mức ngân sách/đầu tư đã ủy quyền.
- Có tác động pháp lý, bảo mật, an toàn hoặc dữ liệu ngoài ranh giới nhóm.
- Hai mục tiêu sản phẩm/đơn vị cạnh tranh năng lực mà không có cơ chế cân bằng.
- Có xung đột trách nhiệm chưa được định nghĩa.
- Một phụ thuộc liên phòng ban bị chặn và người chịu trách nhiệm hiện tại không thể giải quyết.
- Rủi ro cần thay đổi chiến lược, cấu trúc hoặc cam kết hợp đồng.

**Không leo thang mọi bất đồng nhỏ về tên class, giao diện thử nghiệm hoặc chi tiết task** nếu Developers có thể giải quyết theo chuẩn nghề nghiệp.

### 15.2. Bốn trạng thái cho một quyết định bị chặn

~~~text
1. CẦN THÔNG TIN
   -> Thiếu bằng chứng nghiệp vụ/kỹ thuật; làm spike hoặc hỏi đúng chuyên gia.

2. CẦN PHỐI HỢP
   -> Có phụ thuộc giữa nhóm; cùng xác định hợp đồng, owner, thời điểm thử.

3. CẦN THẨM QUYỀN
   -> Vượt ngân sách, chính sách hoặc rủi ro; đưa đến người có quyền chốt.

4. CẦN ỨNG CỨU
   -> Có thiệt hại hiện tại; kích hoạt incident response theo mức nghiêm trọng.
~~~

Đặt đúng loại giúp tránh biến mọi blocked thành “cần cấp trên quyết” hoặc ngược lại coi sự cố thật là một câu hỏi có thể chờ Sprint Review.

### 15.3. Mẫu yêu cầu quyết định có thể hành động

~~~text
Decision ID: DEC-17
Vấn đề: Xác nhận trạng thái lịch sau API đối tác timeout.
Ảnh hưởng: Khách không biết lịch đã Confirmed; gửi lại có nguy cơ trùng.
Điều đã biết: Backend nhận request; API đối tác có thể timeout sau xử lý.
Điều chưa biết: Có API truy vấn/đối soát được không?
Lựa chọn:
  A. Tạm dùng trạng thái Unknown và đối soát thủ công/được kiểm soát.
  B. Đợi đối tác có khả năng truy vấn trước khi mở tự động đổi lịch.
  C. Đổi thiết kế/đối tác nếu có căn cứ và nguồn lực.
Đề xuất: Thử sandbox và làm rõ hợp đồng trước khi mở rộng.
Quyền quyết định:
  - Ưu tiên sản phẩm: Product Owner.
  - Thiết kế và kiểm thử: Developers theo chuẩn kỹ thuật.
  - Rủi ro/đối tác vượt quyền: người có thẩm quyền tương ứng.
Cần trả lời trước: Mốc ra quyết định có thể hành động.
Guardrail: Không tạo lịch trùng, không hiển thị Confirmed giả.
Hệ quả nếu trì hoãn: Lát cắt tự đổi lịch chưa thể phát hành an toàn.
~~~

Mẫu minh họa giúp **người có quyền quyết định nhận đủ bối cảnh**, thay vì nhận email “xin phê duyệt sớm giúp” không có lựa chọn hoặc rủi ro.

### 15.4. Quy tắc “ai có quyền phản đối?”

Trong một quyết định:

- **Người cung cấp ý kiến** có thể đưa bằng chứng và nêu rủi ro.
- **Người chịu trách nhiệm chuyên môn/kiểm soát** có thể có quyền chặn nếu điều kiện bắt buộc chưa đạt.
- **Người chốt** cần cân nhắc các ý kiến trong phạm vi được ủy quyền.
- **Người thực thi** cần đủ thông tin để làm và phản hồi khi giả định không đúng.

Không thể đặt quy tắc “mọi người phải đồng ý 100%” cho mọi việc. Cũng không thể nói “chỉ PO muốn là được” với giao dịch nguy hiểm. **Quyền phản đối phải gắn loại rủi ro và thẩm quyền rõ**, tránh veto vô hạn vì sở thích.

### 15.5. Decision log để tránh xin lại cùng một việc

Một decision log ngắn có thể lưu:

| Trường | Nội dung |
| --- | --- |
| **Ngày/căn cứ** | Khi nào, vì sao cần quyết định. |
| **Quyết định** | Chọn phương án nào, trong ranh giới nào. |
| **Người có quyền** | Vai trò/đầu mối chốt theo chính sách. |
| **Người được tham vấn** | Chuyên gia và stakeholder bị ảnh hưởng. |
| **Giả định còn mở** | Điều gì chưa chắc, cần kiểm chứng. |
| **Guardrails** | Điều kiện chất lượng, bảo mật, chi phí, an toàn. |
| **Mốc xem lại** | Điều kiện hoặc thời điểm làm mới quyết định. |
| **Tác động backlog/forecast** | PBI nào đổi thứ tự/phạm vi. |

**Không ghi dữ liệu cá nhân hoặc bí mật vào log quyết định công khai** chỉ để đầy đủ. Thông tin nhạy cảm cần đường lưu trữ và truy cập phù hợp.

### 15.6. Đừng dùng “escalation” để phạt người nêu vấn đề

Nếu Developers báo rủi ro tạo lịch trùng, mà người quản lý coi đó là “không cam kết”, nhóm có thể học cách che lỗi. Leo thang nên là **cách huy động thẩm quyền để giải quyết giới hạn**, không phải bằng chứng một cá nhân thất bại.

Ngược lại, người đề nghị leo thang cần **làm rõ vấn đề, đưa bằng chứng và lựa chọn**, không dùng cấp trên để né mọi trách nhiệm chuyên môn. Cần cân bằng tự chủ với trách nhiệm có thể kiểm tra.

## 16. Thử chuyển đổi từng phần thay vì tái tổ chức “big bang”

### 16.1. Chọn một vấn đề hệ thống có bằng chứng

Ví dụ “Product Owner mất quá lâu xin duyệt thay đổi thứ tự trong cùng ngân sách”. Một giả thuyết:

> “Nếu lãnh đạo ủy quyền rõ Product Owner sắp thứ tự Product Backlog trong giới hạn Product Goal và đầu tư đã duyệt, đồng thời giữ đường escalations cho rủi ro/ngân sách, thời gian quyết định ưu tiên sẽ giảm mà không làm tăng quyết định sai hoặc vi phạm chính sách.”

Giả thuyết này **không đòi thay toàn bộ cơ cấu công ty ngay**. Nó xác định **thay đổi chính sách có phạm vi và guardrail**.

### 16.2. Chọn phạm vi thử nghiệm

| Chiều | Phạm vi minh họa |
| --- | --- |
| **Sản phẩm** | Nền tảng đặt lịch, không mặc định áp toàn doanh nghiệp. |
| **Loại quyết định** | Đổi thứ tự PBI **trong** Product Goal và ngân sách đã duyệt. |
| **Không thuộc thử nghiệm** | Phê duyệt chi phí vượt hạn mức, dữ liệu nhạy cảm, hợp đồng đối tác, incident. |
| **Nhóm tham gia** | Product Owner, Scrum Teams, lãnh đạo bảo trợ và đầu mối tuân thủ liên quan. |
| **Thời gian** | Một vài vòng làm việc đủ quan sát quyết định, có điểm xem sớm. |
| **Baseline** | Thời gian chờ ưu tiên, số lần xin lại, PBI blocked, ảnh hưởng flow. |
| **Guardrails** | Chất lượng, chi phí, quyền truy cập và rủi ro phù hợp. |
| **Quyết định sau thử** | Giữ, sửa giới hạn ủy quyền, mở rộng có kiểm soát hoặc dừng. |

Không chọn timebox quá ngắn khiến không có quyết định thực nào phát sinh; cũng không thay toàn tổ chức rồi tuyên bố hiệu quả nếu chưa phân biệt các yếu tố tác động.

### 16.3. Một chu kỳ PDSA cho lãnh đạo

~~~mermaid
flowchart LR
    P["PLAN: Vấn đề, quyền, guardrails, dự đoán"] --> D["DO: Thử ở một sản phẩm"]
    D --> S["STUDY: Decision latency, flow, outcome, rủi ro"]
    S --> A{"ACT"}
    A -->|Có ích và an toàn| E["Giữ/mở rộng từng bước"]
    A -->|Có vấn đề| R["Điều chỉnh ranh giới"]
    A -->|Không hiệu quả| X["Dừng và ghi bài học"]
    E -. "Vòng tiếp" .-> P
    R -. "Thử lại" .-> P
~~~

**Plan–Do–Study–Act** là cách tổ chức học hỏi, không phải một “Scrum event” mới. Nó nhấn mạnh mỗi thử nghiệm cần **dự đoán, kết quả và quyết định tiếp theo**.

### 16.4. Bảo vệ những việc không thể thử ngẫu nhiên

Không dùng khách thật làm nhóm đối chứng **thiếu kiểm soát quyền truy cập** để xem bảo mật có làm chậm không. Không để một nửa hệ thống dùng transaction có thể tạo trùng chỉ để đo “tốc độ”.

Có thể thử trong **sandbox**, với **thay đổi quy trình ít rủi ro**, hoặc so hai đường kiểm tra **đều đáp ứng nghĩa vụ**. Với lỗi nghiêm trọng đã xác minh, cần khắc phục theo mức độ và sau đó kiểm tra hiệu lực cải tiến.

### 16.5. Bản đồ năng lực chuyển đổi

Một chương trình thử nên dành nguồn lực cho:

- **Hiểu giá trị:** Product Goal, feedback người dùng, discovery.
- **Kỹ thuật:** CI, TDD, integration tests, refactoring và release an toàn.
- **Quản trị:** quyền quyết định, ngân sách, bảo mật, chính sách rủi ro.
- **Con người:** quản lý phát triển năng lực, huấn luyện, ổn định nhóm.
- **Đo lường:** outcome, flow, chất lượng, decision latency, trải nghiệm làm việc.

Không nên chỉ mua khóa Scrum rồi kỳ vọng giải quyết mọi thứ. **Chuyển đổi là năng lực phối hợp của cả hệ thống**.

### 16.6. Thời điểm mở rộng không dựa vào “có vẻ ổn”

Khi một sản phẩm có tín hiệu tích cực, trước khi mở rộng tới sản phẩm khác cần hỏi:

1. **Vấn đề của sản phẩm khác có tương tự không?**
2. **Ranh giới pháp lý, ngân sách, dữ liệu và kỹ thuật có khác không?**
3. **Cơ chế nào tạo lợi ích**, có bằng chứng ngoài việc nhóm thích cách mới?
4. **Có người hỗ trợ đủ năng lực** để tránh chuyển gánh nặng sang nhóm khác?
5. **Guardrails giữ được** khi quy mô lớn hơn không?
6. **Có kế hoạch dừng/sửa** nếu kết quả khác dự đoán không?

**Mở rộng thực hành có ích không đồng nghĩa nhân bản tất cả nghi thức.** Có thể giữ nguyên tắc phân quyền/đo lường, nhưng thích ứng workflow cho từng sản phẩm.

## 17. Tình huống xuyên suốt: bảo trợ và phân quyền cho ba nhóm đặt lịch

Toàn bộ số liệu, tên nhóm và diễn biến dưới đây là **giả định để học**, không phải mô tả công ty thực tế.

### 17.1. Tổ chức trước chuyển đổi

Một doanh nghiệp có:

- **Team A — Web/Mobile:** Giao diện cho khách.
- **Team B — Booking:** Quy tắc đặt lịch, bảo vệ transaction và trạng thái.
- **Team C — Integration:** API đối tác, thông báo và đồng bộ.
- Một **Product Owner** chịu trách nhiệm mục tiêu sản phẩm nhưng thường bị ba trưởng bộ phận đổi thứ tự công việc.
- Một **nhà bảo trợ** cấp điều hành tuyên bố chuyển đổi Agile.
- Các bộ phận **bảo mật, vận hành, tài chính và hỗ trợ khách hàng**.

Product Goal dự kiến:

> “Khách có thể tự đặt, tra cứu và đổi lịch hợp lệ, tin tưởng vào trạng thái xác nhận mà ít phải gọi tổng đài.”

Nhưng mỗi nhóm báo cáo riêng. A ưu tiên thêm UI đổi lịch, B phải sửa retry có nguy cơ tạo lịch trùng, C tập trung SMS do một trưởng bộ phận đặt hàng. Thay đổi ưu tiên PBI phải chờ lịch ký duyệt hàng tuần.

### 17.2. Hiện trạng bằng dữ liệu giả định

Nhóm xem bốn tuần và ghi:

| Tín hiệu | Hiện trạng giả định | Vấn đề cần kiểm tra |
| --- | ---: | --- |
| Thời gian chờ quyết định đổi thứ tự PBI trung vị | 8 ngày làm việc | Ai cần ký, có thật sự thêm bằng chứng không? |
| Số cấp duyệt theo quy trình hiện tại | 3 | Quyết định nào bắt buộc phải duyệt? |
| Cycle time PBI tích hợp trung vị | 18 ngày làm việc | Phần nào đang chờ giữa các team? |
| Số PBI đang làm trung bình | 15 | WIP có cao so với năng lực hoàn tất không? |
| Sự cố nghiêm trọng đã xác minh | 1 | Quy trình ứng cứu và phòng ngừa có đủ không? |
| Tỷ lệ khách hoàn tất đặt lịch (cửa sổ định nghĩa) | 68% | Phân đoạn nào gặp khó, tracking có đủ không? |
| Số lần xin duyệt lại vì người chốt khác nhau | 9 trong bốn tuần | Ranh giới thẩm quyền có mơ hồ không? |

Các số này dùng để hỏi **có vấn đề hệ thống hay không**, chưa tự chứng minh nguyên nhân. Chẳng hạn cycle time 18 ngày có thể do thiếu môi trường test hoặc API đối tác, không chỉ do quyền ưu tiên.

### 17.3. Sponsor không cho phép “tự do tuyệt đối”, mà sửa ranh giới

Sau khi nghe nhóm, sponsor cùng người có thẩm quyền thống nhất **một thử nghiệm**:

1. Trong **ngân sách và Product Goal đã phê duyệt**, Product Owner chịu trách nhiệm và có quyền thực chất sắp thứ tự Product Backlog.
2. Developers lập Sprint Backlog và chọn phương án thực thi/kiểm thử trong tiêu chuẩn kỹ thuật.
3. Các thay đổi **vượt ngân sách, dữ liệu nhạy cảm, bảo mật và hợp đồng đối tác** vẫn theo đường chuyên môn/phê duyệt thích hợp.
4. Người quản lý không tự chèn ticket vào Sprint; nếu có nhu cầu mới, đưa qua cơ chế intake và làm rõ đánh đổi với PO.
5. **Incident response** có đường riêng, kích hoạt theo mức độ, không phải chờ Sprint Planning.
6. Cấp điều hành bảo trợ giải quyết những xung đột nguồn lực hoặc quyền mà nhóm không thể tự tháo.
7. Thử trong một sản phẩm đủ các vòng để có dữ liệu, sau đó cùng người tham gia xem lại chính sách.

**Điểm mấu chốt:** Những người có quyền bảo mật/tài chính đã tham gia xác định ranh giới, nên nhóm **không cần xin phép tùy tiện** nhưng cũng **không bỏ nghĩa vụ**.

### 17.4. Một quyết định ưu tiên được làm khác đi

Trong Sprint Review, nhóm phát hiện nhiều khách bấm gửi lại khi UI hiển thị trạng thái không rõ. Developers cũng tìm thấy điều kiện cạnh tranh có thể gây lịch trùng.

Trước đây:

~~~text
Phản hồi khách -> Team A -> trưởng bộ phận A
                    -> trưởng bộ phận B -> hội đồng dự án
                    -> Product Owner nhận thứ tự được duyệt
                    -> Developers chờ điều chỉnh và kiểm thử
~~~

Trong phạm vi thử:

~~~text
Phản hồi khách / kiểm thử lỗi
    -> Product Owner + Developers làm rõ tác động/rủi ro
    -> Nếu sự cố: incident response theo mức độ
    -> PO sắp thứ tự PBI trong ranh giới đã ủy quyền
    -> Developers phối hợp thiết kế/test trong DoD
    -> Nếu vượt ranh giới: chuyển đúng người có thẩm quyền
    -> Increment tích hợp -> quan sát outcome
~~~

Product Owner đưa công việc chống trùng và trạng thái có thẩm quyền lên trước SMS. Nhóm C kiểm tra API đối tác, B bảo vệ bất biến, A thử giao diện trạng thái với dữ liệu giả; họ chia thành **lát cắt có thể tích hợp và kiểm tra**.

### 17.5. Vai trò của từng bên trong thử nghiệm

| Bên | Hành động hữu hình |
| --- | --- |
| **Sponsor** | Chốt ranh giới ủy quyền; bảo đảm cấp quản lý khác không âm thầm vô hiệu; tháo chi phí môi trường test. |
| **Product Owner** | Công khai Product Goal, thứ tự và lý do thay SMS bằng sửa trạng thái/an toàn. |
| **Developers A/B/C** | Làm rõ contract, test chống trùng, tích hợp và tạo Increment đủ chất lượng. |
| **Scrum Master** | Giúp nhóm dùng Scrum hiệu quả, nhìn điểm chờ, hỗ trợ gỡ trở ngại và cải tiến phối hợp. |
| **Engineering/people managers** | Giúp chia sẻ kiến thức về transaction, tạo reviewer dự phòng, bảo vệ năng lực cho kiểm thử. |
| **Bảo mật/tuân thủ** | Làm rõ tiêu chuẩn truy cập, dữ liệu và loại thay đổi được tự thực hiện. |
| **Vận hành/support** | Thiết kế giám sát, rollback/đối soát phù hợp và cung cấp phản hồi khách hàng. |

Không nhất thiết mọi vai trò này là một người hoặc một team độc lập; điều quan trọng là **các trách nhiệm không bị bỏ trống** và người cần quyết định có đủ thông tin.

### 17.6. Số liệu sau thử và phép tính minh bạch

Giả sử sau một số vòng công việc, cùng định nghĩa và ranh giới đo, nhóm thu dữ liệu **giả định**:

| Tín hiệu | Trước | Sau thử |
| --- | ---: | ---: |
| Thời gian chờ quyết định ưu tiên trung vị | 8 ngày | 2 ngày |
| Số lần phải xin duyệt lại vì quyền mơ hồ | 9 | 2 |
| Cycle time PBI tích hợp trung vị | 18 ngày | 13 ngày |
| WIP trung bình | 15 | 11 |
| Sự cố nghiêm trọng được phát hiện trong kỳ | 1 | 1 |
| Tỷ lệ đặt lịch thành công theo phiên | 68% | 73% |

Mức giảm thời gian chờ quyết định:

\[
\frac{8-2}{8}\times100\% = 75\%
\]

Mức giảm cycle time trung vị:

\[
\frac{18-13}{18}\times100\%\approx27{,}8\%
\]

Số lần xin lại giảm từ 9 xuống 2, nhưng đây là **số tuyệt đối trong hai giai đoạn**: nếu tổng số quyết định khác nhau, cần dùng tỷ lệ hoặc mẫu số tương ứng để so phù hợp. Tỷ lệ đặt lịch tăng từ 68% lên 73% là **5 điểm phần trăm**, không phải “tăng 5% tương đối”.

### 17.7. Diễn giải đúng mức chắc chắn

**Có thể nói:** “Trong phạm vi thử, thời gian chờ ưu tiên và cycle time PBI tích hợp giảm; nhóm báo ít trường hợp phải xin lại vì quyền quyết định mơ hồ.”

**Chưa thể nói:** “Việc ủy quyền PO chắc chắn tạo toàn bộ mức giảm 27,8% cycle time hoặc cải thiện 5 điểm phần trăm completion.”

Vì sao?

- Có thể đồng thời cải thiện CI, test data hoặc hợp đồng API.
- Loại PBI, độ phức tạp và năng lực nhóm giữa hai kỳ có thể khác.
- Sự cố production và kỳ nghỉ có thể tác động.
- Mẫu số của các phép đo chưa được nêu đủ để suy luận thống kê.
- Số sự cố nghiêm trọng bằng 1 trong hai kỳ **không chứng minh rủi ro bằng nhau**.

Cần xem **phân bố, work item age, số trường hợp, chất lượng và tác động dài hơn**, không chỉ hai số trung vị.

### 17.8. Nút thắt tiếp theo xuất hiện

Sau khi PO không còn chờ duyệt thứ tự nhiều ngày, một số PBI vẫn bị chặn tại **integration testing** vì phải tạo dữ liệu test thủ công. Đây là một phát hiện tốt: rào cản về quyền ra quyết định có thể đã giảm, còn **rào cản kỹ thuật** nay rõ hơn.

Sponsor có thể hỗ trợ một thử nghiệm tiếp:

- Tạo fixture test an toàn cho một luồng.
- Phân quyền môi trường sandbox có kiểm soát.
- Đo blocked time và độ tin cậy test.
- Giữ người có thẩm quyền quản lý môi trường/rủi ro tham gia.
- Chưa mở rộng sang mọi hệ thống cho tới khi có bằng chứng.

**Chuyển đổi Agile là chuỗi thích ứng**, không phải một dự án một lần ký sơ đồ quyền rồi kết thúc.

## 18. Đo sự hỗ trợ của lãnh đạo bằng hành vi và kết quả

### 18.1. Không dùng số cuộc họp Scrum làm thước đo chuyển đổi duy nhất

Một dashboard cho thấy **100% nhóm chạy Daily Scrum** không tự chứng minh rằng:

- Product Owner thật sự quyết định được thứ tự trong phạm vi trách nhiệm.
- Developers có khả năng giao Increment tích hợp và an toàn.
- Quyết định có ít thời gian chờ hơn.
- Người dùng nhận phần mềm có ích sớm hơn.
- Sự cố được phát hiện và xử lý đúng.
- Nhóm có năng lực giữ nhịp bền vững.

Các chỉ số về **đào tạo, sự kiện hoặc công cụ** có thể hữu ích để biết hoạt động triển khai, nhưng phải đặt cạnh **kết quả người dùng, dòng công việc và chất lượng**.

### 18.2. Bốn lớp đo lường bổ trợ

| Lớp | Tín hiệu khả dĩ | Câu hỏi lãnh đạo nên hỏi | Giới hạn |
| --- | --- | --- | --- |
| **Kết quả sản phẩm** | Tỷ lệ khách hoàn thành tác vụ, giảm thời gian nhận giá trị, phản hồi hỗ trợ. | Quyền tự chủ giúp giải quyết vấn đề người dùng nào? | Nhiều yếu tố khác cũng ảnh hưởng outcome. |
| **Flow** | Cycle time, WIP, throughput, work item age, blocked duration. | Quyết định/cơ cấu mới có giảm thời gian chờ toàn luồng không? | Ranh giới, loại việc và cơ cấu mẫu phải thống nhất. |
| **Chất lượng và vận hành** | Lỗi hồi quy, incident, độ tin cậy, thời gian phục hồi, bảo mật. | Cải tiến tốc độ có chuyển rủi ro sang người dùng không? | Sự cố hiếm cần xem mức nghiêm trọng, không chỉ tần suất. |
| **Năng lực quyết định** | Decision latency, vòng xin lại, phạm vi quyền hiểu đúng, chất lượng quyết định. | Nhóm biết quyền và có điều kiện đưa quyết định đúng lúc không? | Ra quyết định nhanh không có nghĩa quyết định đúng. |

Một chương trình lành mạnh theo dõi **nhiều tín hiệu cân bằng**, không ép tất cả thành một con số “Agility Score” khó diễn giải.

### 18.3. Metric contract cho decision latency

Ví dụ cần đo thời gian chờ đổi thứ tự Product Backlog:

~~~yaml
metric: "Product backlog reprioritization decision latency"
unit: "Ngày làm việc / quyết định"
start_event: "Đã có vấn đề, bằng chứng tối thiểu và đề xuất quyết định"
end_event: "Người có thẩm quyền chốt lựa chọn có thể hành động"
scope: "Quyết định trong Product Goal/ngân sách đã ủy quyền"
exclusions:
  - "Incident khẩn: đo bằng quy trình sự cố riêng"
  - "Đầu tư vượt hạn mức: phân tích ở lớp chiến lược riêng"
breakdowns:
  - "Chờ thông tin thật sự cần"
  - "Chờ phê duyệt vì quyền mơ hồ"
  - "Chờ người có thẩm quyền sẵn sàng"
guardrails:
  - "Số quyết định phải làm lại vì bỏ thiếu kiểm soát"
  - "Vi phạm chất lượng, quyền truy cập hoặc ngân sách"
  - "Ảnh hưởng tới mục tiêu và flow sản phẩm"
~~~

**Điểm quan trọng:** Nếu đổi mốc bắt đầu từ “khi yêu cầu xuất hiện” sang “khi mọi người đã ký hồ sơ”, chỉ số latency có thể giảm trên báo cáo mà **thời gian thực không thay đổi**. Phải công khai định nghĩa và giữ nhất quán khi so sánh.

### 18.4. Thử đếm những vòng xin lại vô nghĩa

Giả sử một tháng có **25 quyết định đổi thứ tự PBI**. Trong đó:

- 10 quyết định đi qua một vòng ký duyệt bổ sung vì người chịu trách nhiệm chưa rõ.
- 5 quyết định cần bổ sung bằng chứng về giá trị thật.
- 3 quyết định phải xem xét bảo mật/nghĩa vụ.
- 7 quyết định được chốt trong ranh giới đã ủy quyền.

Đây là **bốn loại nguyên nhân giả định**, không nên gộp toàn bộ **18 quyết định chưa chốt ngay** thành “bureaucracy”. Vòng bổ sung bằng chứng hoặc kiểm tra rủi ro có thể tạo giá trị; vòng duyệt trùng chỉ xác nhận quyền đã rõ có thể là ứng viên cải tiến.

Tỷ lệ quyết định phải qua duyệt lại **do quyền mơ hồ** trong ví dụ:

\[
\frac{10}{25}\times100\%=40\%
\]

Đo lại chỉ số này **không nhằm tăng tốc bằng mọi giá**, mà giúp sponsor xem việc định nghĩa lại thẩm quyền có giảm những vòng chờ không tạo thông tin hay không.

### 18.5. Decision quality không được xem chỉ bằng tốc độ

Giả sử thời gian quyết định rút từ tám ngày xuống một ngày, nhưng số lần phải rollback quyết định do thiếu tham vấn chuyên gia tăng mạnh. Nhóm có thể đã **dịch chi phí từ lúc cân nhắc sang lúc sửa hậu quả**.

Nên kiểm tra:

1. Quyết định có bám Product Goal và bằng chứng không?
2. Những bên có thẩm quyền rủi ro đã tham gia đúng lúc?
3. Có phải quyết định phải đảo ngược vì bỏ sót thông tin cần thiết?
4. Đầu ra có tạo Increment/giá trị hoặc giảm bất định?
5. Chi phí phối hợp sau quyết định có giảm không?
6. Khi sai, tổ chức có học và sửa mà không che kết quả?

**Một quyết định đúng có thể cần nhiều thời gian hơn quyết định sai được đưa ra nhanh**, nhất là với giao dịch dữ liệu hoặc nghĩa vụ pháp lý.

### 18.6. Chỉ số sự hỗ trợ có thể quan sát

Một số tín hiệu quản trị bổ sung:

- Tỷ lệ **trở ngại vượt nhóm được xử lý hoặc có bước tiếp rõ** trong thời gian phù hợp.
- Thời gian cấp **quyền môi trường/test** theo các mức rủi ro.
- Số lần **quyết định đã ủy quyền bị vô hiệu âm thầm**.
- Năng lực thực dành cho **chất lượng, discovery và học** thay vì chỉ khóa feature.
- Mức độ rõ của **Product Goal, thẩm quyền, guardrails và incident path** qua phỏng vấn thực tế.
- Việc sponsor **sửa chính sách hoặc phân bổ nguồn lực** khi có bằng chứng.
- Tính nhất quán giữa **thông điệp Agile** và **cơ chế KPI/đánh giá/đầu tư**.

Các tín hiệu định tính cần được thu từ nhiều góc nhìn và xử lý an toàn; không nên dùng chúng làm công cụ xếp hạng cá nhân hoặc thưởng/phạt những người nêu trở ngại.

### 18.7. Không nhầm đo dòng với giám sát con người

**Cycle time** mô tả hạng mục đi qua một workflow; nó không phải thước đo đạo đức hay năng lực một Developer. **WIP** giúp thấy tải và hàng đợi; nó không phải lý do ép mọi người luôn có nhiều task. **Decision latency** giúp nhận diện quy trình chờ; nó không phải KPI khiến người chịu trách nhiệm ký bừa.

Một hệ thống đánh giá dựa duy nhất vào số liệu dễ khuyến khích:

- Đóng ticket sớm trước khi tích hợp.
- Chuyển work item ra ngoài ranh giới đo.
- Bỏ qua bug khó hoặc che incident.
- Giảm chất lượng thẩm định để ra quyết định nhanh.
- Tránh hỏi người có chuyên môn vì sợ mất thời gian.

**Dùng số liệu làm công cụ học và quyết định cải tiến**, cân bằng với thông tin định tính và outcome thực.

### 18.8. Minh họa quan hệ WIP, throughput và thời gian

Trong workflow **đủ ổn định và cùng ranh giới đo**, Little's Law cho:

\[
\text{WIP trung bình}=\text{Throughput trung bình}\times\text{Thời gian trung bình trong hệ thống}
\]

Nếu WIP trung bình là **18 PBI** và throughput trung bình là **6 PBI/tuần**, thời gian trung bình theo mô hình là:

\[
\frac{18}{6}=3\text{ tuần/PBI}
\]

Nếu nhóm tuyên bố cắt một nửa WIP bằng cách **đưa nhiều PBI đang chờ phê duyệt ra ngoài cột In Progress**, con số có thể đẹp nhưng thời gian khách chờ không đổi. **Thay quyền quyết định phải được kiểm tra ở đường giao giá trị thật**, không chỉ đổi nơi đặt card.

## 19. Dẫn dắt thay đổi về con người và vai trò quản lý

### 19.1. Kháng cự có thể là thông tin về rủi ro hoặc quyền hạn chưa rõ

Một quản lý nói “tôi không muốn PO tự đổi backlog”. Có thể do:

- Họ đang chịu trách nhiệm với hợp đồng ngân sách không cho thay phạm vi.
- Product Goal và giới hạn ưu tiên chưa được phê duyệt.
- Họ lo các nhóm bỏ qua kiểm soát an toàn.
- Họ chưa thấy con đường nghề nghiệp mới sau khi bỏ vai trò giao task.
- Họ quen với cơ chế quyền lực cũ và chưa muốn từ bỏ.

**Không nên mặc định mọi ý kiến phản đối là xấu hoặc chỉ do thiếu hiểu Agile.** Cần tìm cơ chế thật, nêu ranh giới, xử lý rủi ro chính đáng và yêu cầu thay đổi hành vi khi kiểm soát cũ không còn phù hợp.

### 19.2. Từ “quản lý task” sang “xây hệ thống tạo giá trị”

| Trách nhiệm theo cách cũ | Điều có thể cần chuyển đổi | Kết quả tốt cần thấy |
| --- | --- | --- |
| Giao ticket hằng ngày cho từng người. | Trao Developers trách nhiệm lập kế hoạch trong ranh giới. | Sprint Goal/flow rõ, ít chờ điều phối. |
| Kiểm tra số giờ bận và story points. | Xem outcome, flow, chất lượng và năng lực học. | Hành vi không bị tối ưu lệch KPI. |
| Tự duyệt mọi thay đổi kỹ thuật. | Định nghĩa tiêu chuẩn, reviewer đủ năng lực và ranh giới rủi ro. | Chất lượng giữ, số vòng chờ không cần thiết giảm. |
| Đổi ưu tiên theo khách hàng có quyền lực. | Làm rõ nhu cầu qua Product Owner và Product Goal. | Backlog có thứ tự minh bạch. |
| Che tin xấu để bảo vệ deadline. | Báo sớm bất định, đề xuất phạm vi/đường giải quyết. | Forecast đáng tin và thiệt hại được giảm sớm. |
| Xem nhân sự là nguồn lực có thể đổi liên tục. | Phát triển đội đủ ổn định và năng lực liên chức năng. | Ít chuyển ngữ cảnh, chia sẻ tri thức tốt hơn. |

Không phải mọi chức năng cũ đều biến mất: trách nhiệm pháp lý, tuyển dụng, chuyên môn kỹ thuật, quản trị ngân sách và bảo vệ nhân viên vẫn cần người nắm. Chuyển đổi thực tế là **tái phân định công việc cần thiết**, không đổi tên rồi bỏ trống.

### 19.3. Huấn luyện theo tình huống quyết định thật

Một buổi đào tạo lý thuyết Scrum có thể chưa giúp nhà quản lý xử lý câu hỏi:

> “Nếu Product Owner đẩy việc sửa lỗi lên trước feature hợp đồng đã cam kết, nhưng finance nói ngân sách chỉ dành cho feature, ai có quyền quyết?”

Một hoạt động thực hành tốt hơn:

1. Dùng tình huống thật đã loại thông tin nhạy cảm.
2. Phân loại: **incident, ưu tiên sản phẩm, phạm vi đầu tư hay rủi ro kỹ thuật**?
3. Xác định **quyền quyết định và giới hạn**.
4. Lập các lựa chọn, căn cứ giá trị/chi phí/rủi ro.
5. Thử một đường quyết định ngắn hơn nếu chính sách cho phép.
6. Theo dõi thời gian chờ và kết quả thay vì chỉ điểm danh đào tạo.

### 19.4. Những người không có chức danh Agile vẫn cần được hỗ trợ

Support, vận hành, bảo mật, kiến trúc, tài chính và HR thường gắn với **điều kiện để nhóm tạo giá trị**. Chuyển đổi Agile chỉ tập trung Developers/PO/SM dễ tạo xung đột khi các phòng ban còn lại không hiểu mục tiêu mới.

Hỗ trợ phù hợp có thể là:

- Cùng thiết kế quy trình release theo mức rủi ro với vận hành/bảo mật.
- Mở kênh phản hồi khách hàng được bảo vệ từ support tới Product Owner.
- Thay đổi lập ngân sách theo những mốc học có thể kiểm chứng.
- Xây chương trình phát triển năng lực và hướng dẫn quản lý trung gian.
- Giảm khoảng cách giữa thiết kế kiến trúc và việc tích hợp Increment nhỏ.

**Lãnh đạo cần làm công việc kết nối hệ thống**, không coi bộ phận khác là “không Agile” rồi yêu cầu họ tự thích nghi không hỗ trợ.

### 19.5. Công bằng trong chuyển đổi

Chuyển đổi có thể thay đổi cách đánh giá và quyền quyết định. Cần lưu ý:

- Nói rõ mục tiêu, giới hạn và điều **không phải** mục tiêu (ví dụ không dùng Agile để tăng giờ làm).
- Có cơ hội học và phản hồi cho những người chịu thay đổi.
- Không chỉ mời người có chức vụ cao vào nơi quyết định; lắng nghe người trực tiếp làm việc.
- Quy định rõ về quyền nhân sự và việc xử lý vi phạm.
- Không công khai dữ liệu khảo sát nhạy cảm hoặc lời phản hồi có thể gây trả đũa.
- Đánh giá tác động tới người có năng lực khác nhau, nhu cầu trợ năng, nhóm ở múi giờ khác và nhân viên hỗ trợ ngoài giờ.

Sự tham gia có trách nhiệm khác việc đòi **mọi người hoàn toàn đồng ý trước mọi thay đổi**. Sponsor vẫn có thể phải ra quyết định khó và giải thích bằng chứng/đánh đổi minh bạch.

### 19.6. Nhận biết dấu hiệu “Agile fatigue”

Nhóm có thể mệt mỏi khi:

- Mỗi tháng lại dùng một framework mới.
- Có nhiều biểu mẫu và cuộc họp tăng thêm, không giảm quy trình cũ.
- Vẫn bị đánh giá theo KPI cũ nhưng phải báo thêm “Agile metrics”.
- Liên tục tham gia workshop mà trở ngại về quyền, ngân sách không được giải quyết.
- Chương trình thay đổi đánh giá người ta bằng mức độ tuân thủ thuật ngữ.

Một quyết định lãnh đạo có ích có thể là **dừng một nghi thức không tạo giá trị**, giữ một thí nghiệm nhỏ và dành thời gian tháo một điểm chặn có bằng chứng. **Đơn giản hóa có mục đích** quan trọng hơn thu thập thêm nghi thức.

## 20. Những phản mẫu khi bảo trợ và phân quyền chuyển đổi Agile

| Phản mẫu | Dấu hiệu | Hệ quả | Điều chỉnh |
| --- | --- | --- | --- |
| **Sponsor chỉ phát biểu khai mạc** | Sau kickoff, không ai xử lý ngân sách/phụ thuộc. | Quyền trên giấy, rào cản giữ nguyên. | Cam kết hành động cụ thể, owner và thời điểm xem lại. |
| **Agile là dự án đổi tên vai trò** | Project Manager đổi thành Scrum Master nhưng vẫn giao task/duyệt mọi việc. | Không đổi cơ chế quyết định. | Kiểm tra trách nhiệm Scrum và quyền tổ chức thật. |
| **Ủy quyền không có ranh giới** | Nhóm được nói “tự quyết” nhưng không rõ ngân sách, dữ liệu. | Thiếu trách nhiệm, rủi ro cao. | Decision charter và guardrails cụ thể. |
| **Trao trách nhiệm mà không cấp quyền** | PO chịu outcome nhưng phải xin ba cấp duyệt thứ tự. | Chậm phản hồi, mơ hồ accountability. | Sponsor thống nhất quyền PO trong phạm vi được duyệt. |
| **PO được gọi là CEO của sản phẩm** | PO tự phê duyệt chi phí vượt ngân sách, bỏ qua bảo mật. | Vượt quyền và rủi ro tổ chức. | Phân biệt quyền sản phẩm với đầu tư/rủi ro/pháp lý. |
| **Lãnh đạo duyệt mọi PBI** | Quyết định nhỏ chờ cuộc họp quản lý hằng tuần. | Decision latency, WIP tăng. | Phân loại rủi ro và ủy quyền trong giới hạn. |
| **Hội đồng PO** | Nhiều người bỏ phiếu thứ tự cho cùng một sản phẩm. | Không rõ trách nhiệm tối đa hóa giá trị. | Một PO theo Scrum, tham vấn đủ stakeholder. |
| **Scrum Master làm “mini-manager”** | SM phân task, ép commitment, báo cáo cá nhân. | Mất tự quản, Scrum sai mục đích. | SM giúp Scrum và hiệu quả, không thay PO/Developers. |
| **Quản lý trung gian bị gạt ra** | Không có ai chịu trách nhiệm đào tạo, nghề nghiệp, nguồn lực. | Kháng cự và trách nhiệm bỏ trống. | Làm rõ vai trò quản lý phát triển năng lực và rủi ro. |
| **Nhóm tự quyết mọi thứ** | Team thay chuẩn quyền truy cập production tùy ý. | Rủi ro pháp lý và an toàn. | Guardrails, kiểm tra chuyên môn, thẩm quyền rõ. |
| **Tăng tốc bằng bỏ kiểm thử** | “Agile không cần gate” nên bỏ test transaction. | Sự cố, mất niềm tin và rework. | Tối ưu kiểm soát theo rủi ro, giữ DoD và nghĩa vụ. |
| **Sprint Review là cổng duyệt bắt buộc** | Increment Done vẫn chờ Review cuối Sprint mới phát hành. | Chậm feedback không có lý do kỹ thuật. | Review để kiểm tra/thích ứng; release theo điều kiện thực. |
| **Mỗi team có backlog ưu tiên riêng cho một sản phẩm** | Ba team cùng làm tính năng khác nhau, không tích hợp. | Tối ưu cục bộ, giá trị đứt đoạn. | Product Goal, Product Backlog và PO chung khi dùng Scrum cùng sản phẩm. |
| **Đổi toàn tổ chức một lần** | Tái cơ cấu, thay công cụ và ngân sách cùng một kỳ. | Rủi ro lớn, khó biết điều gì hiệu quả. | Chọn vấn đề và thử từng phạm vi có thể kiểm chứng. |
| **Đào tạo thay đổi thay việc tháo chặn** | Nhân viên học Scrum nhiều lần, vẫn chờ môi trường test. | Mất niềm tin, lãng phí. | Kết hợp học với điều chỉnh quyền, công cụ và năng lực thật. |
| **Agile maturity trở thành KPI cá nhân** | Mọi người chạy đủ họp để có điểm đẹp. | Game hóa số liệu, che vấn đề. | Đo outcome, flow, chất lượng và cải tiến hệ thống. |
| **Suy nguyên nhân từ trước–sau** | Cycle time giảm rồi quy toàn bộ công lao cho coach/sponsor. | Mở rộng sai thực hành. | Nêu biến số nhiễu, số mẫu và kiểm chứng tiếp. |
| **Bỏ qua incident vì đã khóa Sprint** | Lỗi dữ liệu chờ backlog refinement. | Thiệt hại cho khách. | Đường ứng cứu riêng, cập nhật năng lực/dự báo. |
| **Chỉ sửa quy trình Developers** | Finance/HR/security/ops vẫn hoạt động với quyền mơ hồ. | Phụ thuộc liên chức năng không đổi. | Liên minh bảo trợ và thiết kế guardrails cùng các bên. |
| **Nhiều cuộc họp để bù quyền không rõ** | Ai cũng tham dự để “cùng chịu trách nhiệm”, không ai chốt. | Chờ đồng thuận, giảm tập trung. | Người quyết định chính, tham vấn đúng người và decision log. |
| **Giao quyền rồi rút khi có tin xấu** | PO tự ưu tiên được tới lúc một stakeholder phàn nàn. | Nhóm không còn tin vào ủy quyền. | Sponsor bảo vệ quyết định trong ranh giới, sửa chính sách minh bạch nếu cần. |
| **Thưởng tốc độ, phạt nêu rủi ro** | Nhóm ngại báo lỗi vì sợ mất velocity. | Sự cố bị giấu và học chậm. | An toàn tâm lý đi cùng tiêu chuẩn nghề nghiệp. |

### 20.1. Chỉ làm Scrum ở cấp nhóm là chưa đủ

Ba nhóm có thể tuân thủ từng sự kiện Scrum và tạo Sprint Backlog tốt nhưng **đường xin ngân sách để tạo môi trường test vẫn mất ba tháng**. Đó là trở ngại hệ thống cần người có thẩm quyền cấp tổ chức tháo.

**Câu hỏi đúng:** “Điều kiện nào bên ngoài Scrum Team đang làm họ không thể tạo Increment?” thay vì “Có thể yêu cầu các nhóm cam kết nhiều story points hơn không?”.

### 20.2. Chuyển sang microservices không tự trao quyền

Một lãnh đạo muốn “độc lập hóa team” bằng việc chuyển tất cả thành microservices. Nhưng nếu hợp đồng dữ liệu, môi trường và quyền đầu tư vẫn tập trung một người, sự phụ thuộc còn nguyên, thậm chí tăng vì mạng, triển khai và transaction phân tán.

Cần xác định **cơ chế gây chờ** trước. Có thể thử modular monolith với ranh giới và ownership rõ, contract tests, khả năng triển khai từng lát cắt; chỉ chọn service riêng khi **nhu cầu độc lập và năng lực vận hành** đủ căn cứ.

### 20.3. Sự im lặng trong cuộc họp không chứng minh mọi người đã được trao quyền

Trong một cuộc họp có nhiều lãnh đạo, Developers không phản đối đề xuất “bỏ test retry để kịp demo”. Họ có thể không hiểu, hoặc sợ phản ứng khi nêu rủi ro.

Một cơ chế tốt cần **kênh nêu cảnh báo chất lượng có trách nhiệm**, hỏi ví dụ thật và tiêu chí an toàn. Không kết luận “mọi người đã đồng thuận” từ việc không ai phát biểu.

### 20.4. Chương trình chuyển đổi có thể cần dừng hoặc đổi hướng

Nếu sau một thời gian thử, chỉ số họp/đào tạo tăng nhưng outcome không cải thiện và nhân viên kiệt sức, **đó là bằng chứng phải kiểm tra lại chương trình**. Có thể giảm số sáng kiến, giữ những thay đổi giúp flow và chất lượng, dừng những việc chỉ tạo báo cáo.

**Bản thân kế hoạch chuyển đổi cũng phải thích ứng**. Không dùng nhãn Agile để bảo vệ một kế hoạch chuyển đổi đã mất giá trị.

## 21. Bài tập tình huống: phân định quyền và hành động có trách nhiệm

### Tình huống A — Product Owner phải xin ba chữ ký để đổi PBI

Một Product Owner phụ trách nền tảng đặt lịch. Trong Sprint Review, nhóm có bằng chứng khách không hiểu trạng thái Pending. PO muốn ưu tiên sửa trạng thái lên trước tính năng SMS trong phạm vi Product Goal và ngân sách đã được duyệt. Nhưng quy trình yêu cầu trưởng nhóm UI, trưởng nhóm backend và giám đốc dự án ký duyệt mỗi lần đổi thứ tự Product Backlog.

**Câu hỏi:**

1. Quyết định nào đang bị chậm? Nó thuộc trách nhiệm nào trong Scrum?
2. Lãnh đạo cần hỗ trợ bằng hành động gì ngoài lời tuyên bố “trao quyền”?
3. Guardrails và loại quyết định nào vẫn cần leo thang?
4. Nên đo thử thay đổi chính sách bằng tín hiệu nào?

**Hướng giải:** Trong Scrum, PO chịu trách nhiệm thứ tự Product Backlog. Sponsor cần cùng các bên có thẩm quyền xác định ranh giới ủy quyền thật để PO không xin lại quyết định trong hạn mức. Vượt ngân sách, nghĩa vụ bảo mật/hợp đồng và rủi ro đặc biệt vẫn có đường quyết định riêng. Theo dõi decision latency, các lần xin lại vì mơ hồ, tác động flow/outcome và chất lượng, không chỉ tốc độ chốt.

### Tình huống B — PO yêu cầu bỏ test chống trùng để đúng deadline

Developers nhận thấy request gửi lại có thể tạo hai lịch Confirmed. Product Owner muốn ra mắt trước hội nghị khách hàng và yêu cầu bỏ một số kiểm thử tích hợp để kịp.

**Câu hỏi:**

1. PO có quyền quyết định tiêu chuẩn chất lượng như một lựa chọn ưu tiên không?
2. Developers cần phản hồi và làm rõ điều gì?
3. Có phương án giảm phạm vi hoặc thử nghiệm an toàn nào?

**Hướng giải:** Product Owner quyết định giá trị và thứ tự, không có quyền yêu cầu Increment chưa đạt Definition of Done được tính Done. Developers phải giữ chất lượng, báo rủi ro có bằng chứng, cùng PO điều chỉnh phạm vi/forecast. Có thể trình bày prototype hoặc demo với dữ liệu giả và nói rõ chưa đủ điều kiện production; sửa bất biến, test cạnh tranh và chỉ phát hành khi điều kiện an toàn phù hợp được đáp ứng.

### Tình huống C — Scrum Master bị giao vai trò quản lý tiến độ cá nhân

Một giám đốc yêu cầu Scrum Master gửi bảng “ai đóng bao nhiêu ticket mỗi ngày” và nhắc từng Developer hoàn thành task, vì cho rằng Scrum Master là người quản lý nhóm trong Scrum.

**Câu hỏi:**

1. Vai trò Scrum Master đang bị hiểu sai như thế nào?
2. Có thể giúp lãnh đạo có thông tin dự báo mà không vi mô hóa không?
3. Ai điều chỉnh Sprint Backlog hằng ngày?

**Hướng giải:** Scrum Master giúp thiết lập Scrum và tăng hiệu quả, không thay người giao task. Developers chịu trách nhiệm Sprint Backlog và điều chỉnh kế hoạch để đạt Sprint Goal. Có thể công khai Increment, Sprint Goal, impediments, WIP/flow, chất lượng và mức bất định cho stakeholder; không dùng số ticket mỗi người làm KPI đơn giản.

### Tình huống D — Quản lý trung gian phản đối vì sợ bỏ trống trách nhiệm

Một engineering manager nói: “Nếu Developers tự quyết định cách làm và PO quyết định Product Backlog thì tôi còn chịu trách nhiệm gì? Ai đào tạo người mới và xử lý thiếu năng lực kiến trúc?”

**Câu hỏi:**

1. Đây có thể là lo lắng hợp lý nào?
2. Những việc cần tiếp tục có người chịu trách nhiệm?
3. Một hành động cụ thể của sponsor là gì?

**Hướng giải:** Cần phân định quyền nhân sự, năng lực, tiêu chuẩn, nguồn lực, coaching, môi trường và phụ thuộc liên đội. Manager có thể tập trung phát triển con người, chuẩn kiến trúc/đào tạo phù hợp và gỡ trở ngại hệ thống. Sponsor công khai vai trò mới và bảo đảm các trách nhiệm quan trọng không bị bỏ trống; không chỉ đổi tên/loại bỏ chức danh.

### Tình huống E — Incident xuất hiện giữa Sprint

Giữa Sprint, production ghi nhận lịch Confirmed bị trùng. Kế hoạch ban đầu tập trung SMS và đổi giao diện. Quản lý dự án cấm bất kỳ ai đổi thứ tự vì “đã chốt commitment từ đầu Sprint”.

**Câu hỏi:**

1. Đường xử lý khẩn cần được kích hoạt ra sao?
2. Sprint Goal, Product Backlog và năng lực nên được xem lại thế nào?
3. Vì sao việc xử lý incident không phải bằng chứng nhóm “không Agile”?

**Hướng giải:** Kích hoạt ứng cứu theo mức độ, giảm thiệt hại, đối soát và bảo vệ dữ liệu; không đợi refinement. PO và Developers trao đổi ảnh hưởng tới Product Goal/Sprint Goal và phạm vi có thể thương lượng; không hạ chất lượng. Thích ứng vì bằng chứng rủi ro mới **là trách nhiệm**, không phải thiếu kỷ luật.

### Tình huống F — Ba Product Owners cho một sản phẩm

Ba team A/B/C cùng làm một ứng dụng đặt lịch. Mỗi team có “PO” độc lập tự quyết PBI quan trọng nhất. A chọn UI đổi lịch, B chọn refactor, C chọn SMS. Không có một Product Goal rõ.

**Câu hỏi:**

1. Đây có phải dấu hiệu vấn đề Scrum ở phạm vi sản phẩm không?
2. Nếu đúng là một sản phẩm, cần chia sẻ điều gì?
3. Nếu thực ra là ba sản phẩm khác nhau thì sao?

**Hướng giải:** Nếu cùng một sản phẩm sử dụng Scrum, các team nên có cùng Product Goal, Product Backlog và Product Owner, cùng định nghĩa/tuân thủ một DoD. Cần làm rõ ranh giới sản phẩm theo người dùng/giá trị, không theo team. Nếu là ba sản phẩm thực sự khác nhau, có thể có Product Goals/Backlogs/PO riêng và một cơ chế đầu tư liên sản phẩm.

### Tình huống G — Lãnh đạo muốn bỏ mọi bước phê duyệt release

Một CEO đọc về Continuous Delivery và yêu cầu “từ nay mọi thay đổi được deploy tự động không qua kiểm soát”, kể cả migration dữ liệu nhạy cảm và quyền truy cập.

**Câu hỏi:**

1. Phần nào của mục tiêu release nhanh là hợp lý?
2. Phần nào cần guardrail hoặc thẩm quyền chuyên môn?
3. Một thử nghiệm nhỏ ít rủi ro có thể là gì?

**Hướng giải:** Mong muốn rút feedback cycle có giá trị, nhưng không thể bỏ nghĩa vụ an toàn. Phân loại thay đổi, tự động hóa bằng chứng kiểm tra, thí điểm luồng ít rủi ro trong chính sách đã duyệt; giữ review chuyên môn khi thay quyền, dữ liệu, transaction. Đo time-to-release, lỗi và khả năng phục hồi, không chỉ số lần deploy.

### Tình huống H — Sponsor vắng mặt sau kickoff

Lãnh đạo công bố “chuyển đổi Agile”, thuê huấn luyện Scrum và lập bảng maturity. Sau ba tháng, nhóm vẫn chờ quyền môi trường test, PO vẫn phải xin phê duyệt thứ tự, còn ngân sách CI bị từ chối.

**Câu hỏi:**

1. Có thể nói đây là sponsorship thực chất không?
2. Hai việc sponsor có thể làm ngay theo thẩm quyền?
3. Nên cập nhật cách đo chương trình thế nào?

**Hướng giải:** Chưa có bằng chứng sponsorship thực chất. Sponsor cần xử lý điểm chặn có tác động rõ: ví dụ ủy quyền có giới hạn cho PO, điều chỉnh quyền test environment phù hợp và cấp nguồn lực cho CI/đào tạo. Xem outcome, blocked time, decision latency và chất lượng; không chỉ số khóa học/sự kiện đã tổ chức.

### Tình huống I — Số liệu cải thiện nhưng phạm vi đo bị thay

Nhóm báo decision latency giảm từ 10 ngày còn 2 ngày. Khi kiểm tra, chỉ số cũ bắt đầu từ lúc yêu cầu xuất hiện, còn chỉ số mới bắt đầu **sau khi tất cả quản lý ký hồ sơ**.

**Câu hỏi:**

1. Hai con số có so sánh trực tiếp được không?
2. Đề xuất metric contract mới?
3. Làm sao biết quá trình ủy quyền có giúp khách nhận giá trị sớm hơn?

**Hướng giải:** Không, vì điểm bắt đầu đã thay. Cần đo cùng ranh giới, phân loại quyết định, vòng duyệt cần/không cần, thời gian tới tác động thực thi. Đối chiếu cycle time end-to-end, Increment, chất lượng và outcome theo mục tiêu; không kết luận chỉ từ latency.

### Tình huống J — Người có quyền kỹ thuật và PO bất đồng

Product Owner muốn thiết kế một nút “Đã xác nhận” ngay sau client gửi request để tăng tỷ lệ hoàn tất tác vụ. Developers và vận hành chỉ ra API đối tác có thể timeout sau khi tiếp nhận nhưng chưa xác nhận kết quả.

**Câu hỏi:**

1. Đây là xung đột giá trị hay tính đúng đắn nghiệp vụ?
2. Ai cần cung cấp bằng chứng và quyết định phần nào?
3. Làm sao tránh cuộc họp đồng thuận kéo dài vô hạn?

**Hướng giải:** Giá trị sản phẩm cần trải nghiệm rõ, nhưng trạng thái không được sai. PO làm rõ outcome và ưu tiên; Developers/chuyên gia miền/đối tác làm rõ semantics, thiết kế, test và rủi ro. Chốt cách biểu diễn Pending/Unknown và tra cứu có thẩm quyền; khi vượt ranh giới cần người có quyền chuyên môn, decision log và mốc kiểm tra.

### Tình huống K — Một nút thắt nhân sự kéo dài

Một chuyên gia duy nhất được duyệt mọi schema changes, thường mất bốn ngày mỗi yêu cầu. CEO đề xuất bỏ review schema để đạt mục tiêu “deploy hằng ngày”.

**Câu hỏi:**

1. Cần phân biệt hai loại chờ đợi nào?
2. Có thể giảm nút thắt mà không bỏ tính đúng đắn không?
3. Cần nhà bảo trợ hỗ trợ điều gì?

**Hướng giải:** Một phần review có thể quan trọng để bảo vệ dữ liệu; phần chờ người độc quyền không tạo thêm bằng chứng có thể cải tiến. Chuẩn migration, contract tests, kiểm tra tự động, reviewer dự phòng có chuyên môn và quyền được ủy quyền theo mức rủi ro. Sponsor bảo đảm năng lực/tiêu chuẩn/ủy quyền, đo thời gian chờ cùng lỗi schema.

### Tình huống L — Chuyển đổi khiến quản lý ép làm thêm giờ

Sau khi chuyển sang Sprint hai tuần, các nhóm phải vừa thực hiện feature cũ, vừa tham gia thêm workshop và chuẩn hóa công cụ. Chỉ số bận rộn tăng, nghỉ phép giảm và chất lượng bắt đầu xấu đi.

**Câu hỏi:**

1. Đây có phải bằng chứng tổ chức “chưa đủ kỷ luật Agile” không?
2. Lãnh đạo có thể thay đổi điều kiện nào?
3. Tín hiệu nào giúp kiểm tra cải tiến mà không biến thành theo dõi cá nhân?

**Hướng giải:** Có thể là overload do chương trình thay đổi không dự trù năng lực. Sponsor cần ưu tiên bớt sáng kiến, gỡ cuộc họp trùng, dành thời gian học, xem WIP và sự cố. Theo dõi cycle time, lỗi, blocked và phản hồi về nhịp bền vững ở mức phù hợp, không ép velocity cá nhân.

### Tình huống M — Một quyết định ngân sách bị ngụy trang thành quyết định backlog

PO muốn mua một dịch vụ đối soát mới vượt hạn mức ngân sách. Họ nói: “Theo Scrum, PO tối đa hóa giá trị nên tôi có quyền ký mọi hợp đồng phục vụ sản phẩm.”

**Câu hỏi:**

1. Quyền PO và quyền đầu tư khác nhau ở đâu?
2. PO cần chuẩn bị thông tin gì cho người có thẩm quyền?
3. Có thể thử giảm bất định trước khi ký hợp đồng lớn không?

**Hướng giải:** Trách nhiệm Product Backlog không mặc định cấp quyền mua sắm vượt hạn mức. PO đưa giá trị/rủi ro, chi phí trì hoãn, lựa chọn, giới hạn và kết quả dự kiến tới người có quyền đầu tư. Có thể thử sandbox, proof-of-concept hoặc khảo sát có timebox trong phạm vi cho phép, rồi quyết định sau.

### Tình huống N — Tính toán và diễn giải tỷ lệ cải thiện

Trong một pilot giả định, thời gian chờ ưu tiên trung vị giảm từ **6 ngày** xuống **1,5 ngày**; cycle time của các PBI hoàn tất giảm từ **12 ngày** xuống **9 ngày**. Số PBI đủ điều kiện đo là 10 trước và 11 sau.

**Câu hỏi:**

1. Thời gian chờ ưu tiên giảm bao nhiêu phần trăm?
2. Cycle time giảm bao nhiêu phần trăm?
3. Vì sao không thể nói “ủy quyền làm năng suất tăng 75%”?

**Đáp án:** (1) \((6-1{,}5)/6\times100\%=75\%\); (2) \((12-9)/12\times100\%=25\%\); (3) đó là mức giảm **trung vị hai chỉ số thời gian**, không phải đo năng suất; mẫu nhỏ, loại việc và biến số khác có thể thay đổi, không chứng minh nhân quả hoặc outcome. Cần xem bảo vệ chất lượng, khối lượng công việc, phân bố và phản hồi.

### Tình huống O — Quyền chốt rõ nhưng thiếu tham vấn

Để rút thời gian, tổ chức đặt người duyệt duy nhất cho các thay đổi liên quan dữ liệu khách nhưng không yêu cầu lấy ý kiến nhóm vận hành hay pháp lý. Quyết định nhanh hơn nhưng nhiều lần phải sửa lại vì nghĩa vụ bị bỏ sót.

**Câu hỏi:**

1. Thiếu điều gì ngoài một người có quyền chốt?
2. Tham vấn và phê duyệt khác nhau thế nào?
3. Có thể cải tiến gì trước khi rút thêm thời gian?

**Hướng giải:** Cần quy định thông tin/bằng chứng bắt buộc và chuyên gia phải tham gia **đúng loại quyết định**. Tham vấn cung cấp căn cứ, phê duyệt gắn quyền chốt/chặn theo chính sách. Dùng tiêu chuẩn, checklist rủi ro và liên hệ sớm, đo cả quyết định phải sửa lại, không chỉ latency.

### Tình huống P — Kháng cự sau thay đổi quyền hạn

Một quản lý trước đây duyệt từng backlog item. Sau khi PO được ủy quyền, họ âm thầm yêu cầu Developers báo riêng kế hoạch để điều chỉnh qua kênh khác. PO không biết vì sao thứ tự thay đổi.

**Câu hỏi:**

1. Đây là vấn đề cơ chế nào?
2. Sponsor cần hành động thế nào mà không biến thành phê bình cá nhân công khai?
3. Làm sao kiểm tra ranh giới mới đã được tuân thủ?

**Hướng giải:** Quyền trên giấy chưa đi vào thực tế, tạo “shadow approval”. Sponsor làm rõ thẩm quyền và phản ánh mối quan ngại về ngân sách/rủi ro của manager; nếu có thiếu sót trong charter thì sửa công khai. Dùng decision log, trao đổi trực tiếp, theo dõi những lần ưu tiên bị đổi ngoài đường quyết định và tác động tới flow; không tạo môi trường trừng phạt người nêu vấn đề.

## 22. Lộ trình chuẩn bị sự hỗ trợ và quyền quyết định theo từng giai đoạn

Một chương trình chuyển đổi không cần bắt đầu bằng **tái cơ cấu toàn công ty**. Có thể đi từ **thống nhất vấn đề → thử thay đổi chính sách trong phạm vi nhỏ → học và mở rộng có điều kiện**. Những khoảng thời gian dưới đây là **gợi ý nhịp làm việc**, không phải mẫu 30–60–90 ngày bắt buộc.

### 22.1. Giai đoạn A — Hiểu mục tiêu và quyền hiện có

**Mục đích:** Không thay đổi một quyền nào khi chưa hiểu quyết định nào đang thật sự bị chặn và những kiểm soát nào là cần thiết.

Hoạt động:

1. Ghi rõ **vấn đề sản phẩm/flow**: ví dụ phản hồi khách phải chờ phê duyệt nhiều ngày.
2. Xác định **Product Goal, ranh giới sản phẩm và nhóm liên quan**.
3. Lần theo hai hoặc ba **quyết định thật** từ đề xuất tới người chốt/thi hành.
4. Phân loại các điểm chờ: thiếu dữ liệu, phụ thuộc kỹ thuật, quyền mơ hồ, kiểm soát bắt buộc hoặc chờ năng lực.
5. Xác định **nhà bảo trợ, PO, Developers, quản lý trung gian, tài chính, bảo mật, vận hành** cần tham gia.
6. Thu baseline về **decision latency, blocked, cycle time, chất lượng và outcome** với ranh giới rõ.
7. Kiểm tra chính sách hiện hành: điều gì **không thể đổi** nếu chưa có thẩm quyền hoặc nghĩa vụ pháp lý?

**Đầu ra nên có:** Một phát biểu vấn đề, bản đồ quyết định, vài bằng chứng, danh sách rủi ro và người có thể sửa điều kiện hệ thống.

**Chưa nên làm:** Công bố “từ nay team được làm mọi thứ” hoặc bắt tất cả team đổi công cụ khi chưa biết vấn đề.

### 22.2. Giai đoạn B — Thiết kế quyền và thử trong phạm vi rõ

**Mục đích:** Kiểm tra một giả thuyết thay đổi có thể giúp cải thiện kết quả.

Hoạt động:

1. Chọn **loại quyết định** cụ thể để ủy quyền, chẳng hạn thay thứ tự PBI trong ngân sách/Product Goal đã duyệt.
2. Viết **decision charter**: người chốt, người thực thi, người tham vấn, giới hạn, điều kiện vượt quyền.
3. Đồng thiết kế **guardrails** với người chịu trách nhiệm rủi ro.
4. Xác định **điểm dừng, đường ứng cứu, cách giải quyết bất đồng**.
5. Chuẩn bị **năng lực kỹ thuật và con người** để quyền không chỉ nằm trên giấy.
6. Chọn một sản phẩm hoặc một loại quyết định có **đủ tình huống phát sinh để học**, không thử quá hẹp đến mức không có dữ liệu.
7. Công bố mục tiêu, điều **đã và chưa được ủy quyền**, nơi ghi phản hồi.
8. Đo theo metric contract, ghi cả trường hợp không đạt hoặc phải quay lại chính sách cũ.

**Đầu ra nên có:** Một charter được người có thẩm quyền thực sự chấp thuận, kế hoạch thử nhỏ, nguồn lực và điều kiện đo.

**Chưa nên làm:** Gộp việc đổi cơ cấu, HR, ngân sách, công cụ, Sprint length, CI và toàn bộ release policy vào một thử nghiệm duy nhất rồi tìm một nguyên nhân cho kết quả.

### 22.3. Giai đoạn C — Học, điều chỉnh và quyết định mở rộng

**Mục đích:** Kiểm tra xem quyết định nhanh hơn có tạo **giá trị và chất lượng bền vững** không.

Hoạt động:

1. So kết quả với **dự đoán ban đầu**, không chỉ với cảm giác tích cực.
2. Xem decision latency, các lần xin lại, blocked time và **cycle time end-to-end**.
3. Xem **guardrails**: bảo mật, dữ liệu, độ tin cậy, chi phí, tải công việc.
4. Hỏi PO, Developers, managers và những người có quyền kiểm soát về những quyết định **vẫn mơ hồ**.
5. Chỉnh charter khi xuất hiện trường hợp mới, công khai người chốt và lý do.
6. Quyết định **giữ, sửa, mở rộng từng bước hoặc dừng**.
7. Nếu mở rộng, kiểm tra **sản phẩm mới có ranh giới/rủi ro khác** không.
8. Đưa bài học vào cách cấp năng lực, huấn luyện, workflow và đánh giá kết quả.

**Đầu ra nên có:** Quyết định có căn cứ về lần thử, phiên bản charter mới nếu cần và vấn đề tiếp theo đáng cải tiến.

### 22.4. Bảng tổng hợp giai đoạn

| Giai đoạn | Câu hỏi then chốt | Sponsor đóng góp | Nhóm và PO đóng góp | Bằng chứng hoàn tất |
| --- | --- | --- | --- | --- |
| **Hiểu** | Điều gì đang ngăn giao giá trị? | Cho phép nhìn thẳng vấn đề, mở quyền tiếp cận dữ liệu/chính sách. | Vẽ dòng thực, nêu rủi ro và ranh giới Product Goal. | Phát biểu vấn đề, baseline và bản đồ thẩm quyền. |
| **Thử** | Quyền nào có thể chuyển gần công việc hơn? | Phê duyệt ranh giới, cấp năng lực, bảo vệ sự ủy quyền. | Thực thi trong guardrails, ghi kết quả và điều còn thiếu. | Charter, thử nghiệm và dữ liệu hợp lệ. |
| **Học** | Kết quả/thiệt hại thay đổi ra sao? | Chọn giữ/sửa/dừng/mở rộng, xử lý trở ngại mới. | Đánh giá flow, quality, outcome và feedback. | Quyết định sau thử, bài học và kế hoạch tiếp. |

### 22.5. Năm điều kiện trước khi gọi là “sẵn sàng thử”

- **Có mục tiêu rõ:** Tại sao phải thay quyền quyết định này?
- **Có thẩm quyền thật:** Ai có quyền cấp ủy quyền và ai chấp nhận thay đổi?
- **Có năng lực:** Nhóm có kỹ năng, thời gian, môi trường và hỗ trợ cần thiết?
- **Có guardrails:** Ngân sách, chất lượng, dữ liệu, bảo mật, ứng cứu và dừng thử?
- **Có phép đo và điểm xem lại:** Biết điều gì tạo giá trị và điều gì khiến phải sửa?

Nếu thiếu một điều kiện quan trọng, thay vì hủy cả chương trình, có thể chọn **bước chuẩn bị nhỏ** để làm rõ hoặc tạo điều kiện đó.

## 23. Workshop 90–120 phút: chuẩn bị quyết định và bảo trợ chuyển đổi

### 23.1. Bối cảnh workshop

Một công ty xây nền tảng đặt lịch tư vấn. Sponsor nói cần chuyển đổi Agile để phát hành thường xuyên hơn. Hiện có ba Scrum Teams A/B/C:

- Product Owner muốn ưu tiên sửa lỗi trạng thái Pending sau phản hồi người dùng.
- Ba trưởng bộ phận có quyền ký duyệt thứ tự Product Backlog.
- Developers không tự cấp được môi trường test dù có thể thiết kế kiểm soát phù hợp.
- Bộ phận bảo mật lo thay transaction và dữ liệu cá nhân bị triển khai thiếu kiểm tra.
- Vận hành đang chịu trách nhiệm incident, release và các rủi ro sau giao.
- Một engineering manager sợ trách nhiệm phát triển nhân sự bị bỏ trống.
- CEO muốn “mọi team self-organize từ đầu tháng sau”.

**Nhiệm vụ:** Xây một kế hoạch **sponsor action + decision charter + thử nghiệm có guardrails** để hệ thống học và giao giá trị tốt hơn, không chỉ đổi khẩu hiệu.

### 23.2. Các vòng làm việc

| Thời gian | Hoạt động | Đầu ra |
| --- | --- | --- |
| **0–10 phút** | Thống nhất Product Goal và vấn đề hiện tại; nêu những rủi ro cần xử lý ngay. | Vấn đề, outcome và đường ứng cứu tách riêng. |
| **10–25 phút** | Vẽ dòng một quyết định thật: từ phản hồi khách tới quyết định sửa/phát hành. | Decision flow và điểm chờ. |
| **25–40 phút** | Phân loại loại quyết định và người có quyền hiện tại. | Ma trận hiện trạng, chỗ chồng chéo/bỏ trống. |
| **40–55 phút** | Thiết kế decision charter trong một phạm vi nhỏ. | Người chốt, tham vấn, thực thi, guardrails, escalation. |
| **55–70 phút** | Chọn hành động bảo trợ: ngân sách, môi trường, kỹ năng, ranh giới backlog. | Ba việc sponsor thực sự có thể làm. |
| **70–85 phút** | Viết giả thuyết thử và metric contract. | Baseline, chỉ số chính, chất lượng, điều kiện dừng. |
| **85–100 phút** | Mô phỏng một thay đổi/rủi ro bất ngờ. | Quyết định điều chỉnh, cách thông báo đánh đổi. |
| **100–120 phút (nếu có)** | Phản biện chéo và chốt điểm xem lại. | Kế hoạch khả thi, trách nhiệm và ngày/điều kiện đánh giá. |

Đây là **khung thực hành minh họa**. Nếu đang có sự cố production gây hại, đường ứng cứu **không được chờ workshop kết thúc**.

### 23.3. Mẫu bảng decision charter trong workshop

| Quyết định cần thực hiện | Người chốt trong phạm vi thử | Người tham vấn | Giới hạn/điểm leo thang | Bằng chứng và trạng thái |
| --- | --- | --- | --- | --- |
| Đổi thứ tự PBI Pending so với SMS | Product Owner | Developers, support, stakeholder | Trong Product Goal và ngân sách đã duyệt; nếu vượt thì cấp đầu tư. | Phản hồi khách, tác động và decision log. |
| Chọn giải pháp chống retry tạo trùng | Developers và người có trách nhiệm kỹ thuật theo chuẩn | Chuyên gia miền, bảo mật, vận hành | Không vi phạm DoD, quyền dữ liệu, transaction. | Test và kiểm chứng bất biến. |
| Cho phép tạo dữ liệu test trong sandbox | Người có quyền môi trường chấp thuận chính sách tự phục vụ; nhóm áp dụng sau đó | QA, security, ops | Không dùng dữ liệu production, giữ log và hạn mức. | Chính sách mới, blocked time và sự cố test. |
| Điều chỉnh ngân sách vượt ngưỡng | Người có thẩm quyền đầu tư | PO, tài chính, engineering | Giới hạn tài chính/hợp đồng. | Hồ sơ lựa chọn và chi phí. |
| Dừng rollout khi tạo trùng | Người được ủy quyền incident/release | Developers, support, security khi cần | Mức sự cố kích hoạt hành động ngay. | Incident log và khắc phục. |

**Điểm cần kiểm tra:** Với một quyết định nhỏ đã nằm trong hạn mức, có còn **nhiều người cùng bắt buộc ký lại** mà không bổ sung bằng chứng hay không? Với quyết định rủi ro cao, các chuyên gia và người có quyền chặn **có được tham gia đúng lúc** hay không?

### 23.4. Mẫu “Sponsor Action Plan” một trang

~~~text
PROGRAM PURPOSE
  Vì sao thay đổi hệ thống ra quyết định:
  Outcome sản phẩm / flow cần cải thiện:

SPONSOR
  Người có quyền bảo trợ:
  Những chính sách hoặc nguồn lực thực sự có thể điều chỉnh:
  Những quyền vẫn thuộc cấp khác:

CURRENT PROBLEM
  Quyết định nào thường bị chặn:
  Ai chịu hệ quả:
  Bằng chứng / baseline:
  Nguyên nhân giả định:

DECISION CHARTER - PILOT
  Loại quyết định được ủy quyền:
  Người chịu trách nhiệm cuối:
  Người thực thi và người tham vấn:
  Những giới hạn ngân sách/chiến lược/kỹ thuật:
  Quyền bảo mật / release / incident:
  Khi vượt phạm vi thì liên hệ ai:

ENABLEMENT
  Kỹ năng/đào tạo cần hỗ trợ:
  Công cụ/môi trường/CI cần tạo:
  Năng lực/tải công việc cần bảo vệ:
  Quản lý trung gian sẽ hỗ trợ theo vai trò nào:

EXPERIMENT
  Giả thuyết có thể bác bỏ:
  Sản phẩm / nhóm / loại quyết định / timebox:
  Primary signal:
  Flow/outcome signal:
  Guardrails:
  Điều kiện dừng/đường ứng cứu:

REVIEW AND ADAPT
  Người xem lại kết quả:
  Khi nào hoặc khi điều kiện nào:
  Những lựa chọn: giữ / điều chỉnh / mở rộng / dừng:
  Cách công khai quyết định và bài học:
~~~

### 23.5. Một phương án tham khảo

**Vấn đề:** Việc đổi thứ tự PBI trong cùng Product Goal mất tám ngày vì ba lần duyệt lại, trong khi khách cần sửa trạng thái Pending.

**Giả thuyết:** Nếu PO có quyền thật sắp thứ tự PBI trong phạm vi đầu tư đã chấp thuận, thời gian quyết định sẽ giảm và các hạng mục giá trị được xử lý sớm hơn, **mà không tăng vi phạm chất lượng hoặc ngân sách**.

**Sponsor:** Cấp có quyền điều chỉnh quy trình phê duyệt xác định rằng **thứ tự Product Backlog trong phạm vi đã duyệt do PO quyết định**, còn thay đổi đầu tư, hợp đồng, dữ liệu nhạy cảm đi qua thẩm quyền chuyên môn.

**Developers:** Đưa ra giải pháp kỹ thuật, test và khả năng triển khai trong DoD; không để UI báo Confirmed khi backend chưa biết kết quả.

**Manager:** Bảo đảm reviewer dự phòng, môi trường test, kỹ năng và đường hỗ trợ, không tiếp tục phê duyệt PBI qua kênh riêng.

**Pilot:** Một sản phẩm, các quyết định đổi thứ tự PBI thường xuyên trong một số vòng làm việc đủ quan sát; đo decision latency, lần xin lại, cycle time toàn luồng và rủi ro.

**Guardrails:** Không bỏ test, bảo mật, quyền dữ liệu, ngân sách hay incident path; quyết định vượt phạm vi được chuyển đúng cấp.

**Act:** Nếu tín hiệu tích cực và chất lượng giữ, duy trì rồi xem xét mở rộng có điều kiện; nếu xuất hiện quyết định sai vì thiếu tham vấn, sửa charter và yêu cầu bằng chứng, không quay về việc mọi cấp ký mọi thứ theo thói quen.

### 23.6. Phản biện bằng ba thẻ biến cố

**Thẻ 1 — Sự cố production:** Đang thử phân quyền thì xuất hiện lỗi tạo lịch trùng. Nhóm phải giải thích **đường ứng cứu, quyền dừng rollout, ảnh hưởng Sprint Goal và cách cập nhật backlog**, không tranh luận “ai chịu lỗi Scrum”.

**Thẻ 2 — Vượt ngân sách:** Product Owner muốn mua một công cụ mới vượt hạn mức để giảm thời gian chờ. Nhóm phải mô tả **thẩm quyền đầu tư, bằng chứng CoD/chi phí, phương án thử nhỏ** và lý do không tự ký hợp đồng.

**Thẻ 3 — Shadow approval:** Một manager tiếp tục đổi thứ tự PBI bằng tin nhắn riêng với Developers. Nhóm phải nêu **tín hiệu phát hiện, cách sponsor xử lý, mối lo hợp lý của manager và cách công khai quyền**, không tạo cơ chế giám sát trả đũa.

### 23.7. Tiêu chí đánh giá kế hoạch workshop

Một kế hoạch tốt cần trả lời rõ:

1. **Vấn đề thực** nào đang cần sửa, có bằng chứng không?
2. Sponsor có **thẩm quyền và cam kết hành động** nào?
3. Những loại quyết định nào được chuyển gần nhóm, loại nào giữ ở cấp khác?
4. Quyền và trách nhiệm **PO/Developers/SM** có đúng Scrum khi áp dụng không?
5. Người quản lý trung gian và các chức năng hỗ trợ có công việc rõ không?
6. Có tiêu chuẩn chất lượng, quyền dữ liệu, ngân sách và **incident path** không?
7. Người dùng có thể nhận giá trị nhỏ tăng dần thay vì chỉ thấy biểu mẫu mới không?
8. Thử nghiệm có **phạm vi, thời gian, baseline, guardrails và quyền dừng** không?
9. Kết quả được đo **cân bằng** giữa decision latency, flow, outcome và rủi ro không?
10. Nếu kết quả khác dự đoán, sponsor và nhóm có **quyết định tiếp theo** không?

## 24. Checklist chuẩn bị sự hỗ trợ của lãnh đạo và quyền ra quyết định

### 24.1. Mục tiêu và bảo trợ

- [ ] Có vấn đề cụ thể về giá trị, flow hoặc chất lượng mà chuyển đổi cần giúp giải quyết.
- [ ] Mục tiêu diễn đạt thành **outcome**, không chỉ tần suất Scrum events hay phần trăm nhóm được đào tạo.
- [ ] Lãnh đạo bảo trợ hiểu và cam kết thay đổi **điều kiện/cơ chế** trong thẩm quyền của mình.
- [ ] Có người chịu trách nhiệm xử lý trở ngại vượt nhóm và mốc xem lại.
- [ ] Mục tiêu và đầu tư chuyển đổi không mâu thuẫn với chuẩn an toàn/đạo đức hoặc nghĩa vụ thật.
- [ ] Người bị ảnh hưởng hiểu điều gì thay đổi, điều gì không thay đổi và vì sao.
- [ ] Có đường nhận phản hồi về chính chương trình chuyển đổi và cách đóng vòng.

### 24.2. Quyền quyết định và trách nhiệm

- [ ] Đã xác định đúng **ranh giới sản phẩm** và Product Goal.
- [ ] Quyền đầu tư/chiến lược khác quyền sắp thứ tự Product Backlog.
- [ ] Product Owner trong Scrum có trách nhiệm thật đối với Product Backlog; không phải hội đồng cùng ký mọi PBI.
- [ ] Developers có quyền lập Sprint Backlog và lựa chọn thực thi phù hợp với DoD, kỹ năng và tiêu chuẩn.
- [ ] Scrum Master không bị biến thành người giao task hoặc quản lý tiến độ cá nhân.
- [ ] Quyền quản lý nhân sự, ngân sách, pháp lý và an toàn không bị bỏ trống.
- [ ] Ma trận hoặc charter chỉ rõ **người chốt, người thực thi, người tham vấn, giới hạn và đường leo thang**.
- [ ] Không có vòng phê duyệt trùng lặp cho những quyết định ít rủi ro đã được ủy quyền.
- [ ] Quyền tham vấn và quyền chặn/phê duyệt chuyên môn được phân biệt.
- [ ] Có decision log/nguồn thông tin phù hợp để người khác không phải xin lại cùng quyết định.

### 24.3. Điều kiện trao quyền

- [ ] Nhóm có đủ năng lực liên chức năng hoặc đường phối hợp để tạo Increment tích hợp.
- [ ] Môi trường test, dữ liệu thử, CI, hợp đồng API và công cụ được hỗ trợ phù hợp.
- [ ] Có kế hoạch chia sẻ tri thức và reviewer dự phòng cho điểm nghẽn chuyên môn.
- [ ] Có năng lực để xử lý discovery, nợ kỹ thuật có tác động, kiểm thử và cải tiến liên tục.
- [ ] Không ép utilization mọi người đạt 100% hoặc làm thêm giờ liên tục để bù chương trình thay đổi.
- [ ] Vai trò của engineering/people managers trong phát triển con người và gỡ trở ngại được diễn đạt rõ.
- [ ] Sponsor có quyền điều chỉnh chính sách liên phòng ban hoặc biết cách đưa vấn đề tới người có quyền.
- [ ] Các bên tài chính, bảo mật, vận hành, HR và stakeholder cần thiết được tham gia đúng quyết định.

### 24.4. Rủi ro và quản trị

- [ ] Ranh giới ngân sách/chiến lược và điều kiện vượt quyền được công khai.
- [ ] Quy định bảo mật, dữ liệu cá nhân, kiểm thử và Definition of Done áp dụng vẫn được tuân thủ.
- [ ] Release có quyền thực hiện, giám sát và khả năng khắc phục theo mức rủi ro.
- [ ] Có đường incident response **không phụ thuộc vào lịch Sprint Review**.
- [ ] Người có quyền dừng rollout/ứng cứu được xác định rõ.
- [ ] Feature flag không bị coi là cách hoàn tác mọi dữ liệu/giao dịch đã xảy ra.
- [ ] Không thực hiện thử nghiệm để người dùng chịu rủi ro đã biết chỉ nhằm thu thêm dữ liệu.
- [ ] Các quyết định khó đảo ngược được kiểm tra và tham vấn đúng thẩm quyền.
- [ ] Không tự ý bỏ một kiểm soát bắt buộc chỉ để báo “ra quyết định nhanh”.

### 24.5. Thử, đo và thích ứng

- [ ] Có baseline cho một hoặc vài quyết định/workflow thật.
- [ ] Metric contract nêu rõ loại quyết định, start/finish, đơn vị và cách phân nhóm.
- [ ] Thử nghiệm có phạm vi đủ nhỏ để bảo vệ rủi ro nhưng đủ trường hợp để quan sát.
- [ ] Có giả thuyết và cả kết quả có thể **bác bỏ** giả thuyết.
- [ ] Chỉ số decision latency được xem với **chất lượng quyết định, flow và outcome**.
- [ ] Các trường hợp bị chặn và việc chưa hoàn tất vẫn xuất hiện trong phân tích.
- [ ] Có ghi biến số nhiễu, thay đổi mẫu và giới hạn suy luận trước–sau.
- [ ] Không dùng số story points, ticket hoặc sự kiện Agile để xếp hạng/đánh giá cá nhân.
- [ ] Có thời điểm xem lại và khả năng **giữ, sửa, mở rộng hoặc dừng**.
- [ ] Những điều sai dự đoán được ghi như bài học, không bị che để giữ chương trình chuyển đổi “thành công”.
- [ ] Sau mỗi vòng, sponsor thực sự điều chỉnh nguồn lực, quyền hoặc chính sách khi bằng chứng đòi hỏi.

## 25. Ghi nhớ cốt lõi

**Chuyển đổi Agile không thể thành công chỉ nhờ các nhóm học Scrum nếu hệ thống lãnh đạo vẫn ngăn họ ra quyết định đúng lúc.** Sự hỗ trợ thực chất cần được nhìn thấy qua **mục tiêu có ý nghĩa, quyền đã ủy quyền rõ ràng, năng lực đủ để thực hiện, guardrails phù hợp, đường leo thang và thói quen học từ bằng chứng**.

Nhớ sáu câu hỏi trước khi thay cơ chế quản trị:

1. **Vì sao chúng ta cần thay đổi?** Khách hàng, flow hoặc chất lượng đang gặp vấn đề nào?
2. **Lãnh đạo sẽ làm gì khác?** Chính sách, đầu tư, cơ cấu hoặc trở ngại nào sẽ được xử lý?
3. **Ai quyết định điều gì?** Phân biệt mục tiêu/đầu tư, Product Backlog, kế hoạch thực thi, kỹ thuật, nhân sự, release và rủi ro.
4. **Quyền đi kèm năng lực và ranh giới nào?** Nhóm có kỹ năng, môi trường, ngân sách và tiêu chuẩn không?
5. **Khi vượt quyền hoặc có sự cố, đi đâu?** Có người chốt, quyền ứng cứu và đường xử lý ngắn phù hợp không?
6. **Làm sao biết đang tốt lên?** Có outcome, flow, chất lượng, decision latency và khả năng sửa quyết định khi học thêm không?

Với **Scrum**, Product Owner chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog; Developers tạo Sprint Backlog và Increment đủ chất lượng; Scrum Master hỗ trợ Scrum và hiệu quả. **Lãnh đạo tổ chức** không bị xóa khỏi bức tranh: họ tạo điều kiện về đầu tư, nhân sự, rủi ro, quyền và năng lực. **Kanban** giúp thấy dòng quyết định/công việc và những điểm chờ; **XP** giúp CI, TDD và refactoring giảm rủi ro khi thay đổi; **PDSA** giúp thử và điều chỉnh chính sách một cách có bằng chứng.

**Trao quyền thực chất là đưa quyết định tới nơi có thông tin và chuyên môn phù hợp, trong giới hạn minh bạch; bảo trợ thực chất là bảo vệ điều kiện ấy và cùng chịu trách nhiệm sửa hệ thống khi nó không hoạt động.**

### Tài liệu tham khảo để tìm hiểu sâu

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — ưu tiên cộng tác, phần mềm hoạt động và thích ứng trước thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — giao giá trị thường xuyên, kết hợp kinh doanh và kỹ thuật, nhóm tự tổ chức, nhịp bền vững và tự cải tiến.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — ba accountabilities, Product Goal, Product Backlog, Sprint Goal, Sprint Backlog, Definition of Done và cách nhiều Scrum Team cùng một sản phẩm.
- [The Kanban Guide](https://kanbanguides.org/) — Definition of Workflow, WIP, cycle time, throughput, work item age và cải tiến dòng công việc.
- [Scrum.org — Evidence-Based Management Guide](https://www.scrum.org/resources/evidence-based-management-guide) — khung nhìn giá trị, khả năng tạo giá trị và quyết định dựa trên bằng chứng.
- [DORA](https://dora.dev/) — tham khảo năng lực giao thay đổi phần mềm và độ tin cậy vận hành.
- [Lean Enterprise Institute](https://www.lean.org/) — tư duy dòng giá trị, giải quyết vấn đề và cải tiến hệ thống.
- [The W. Edwards Deming Institute](https://deming.org/) — tư duy hệ thống, hiểu biến động và phương pháp Plan–Do–Study–Act.
- Amy C. Edmondson (1999), *Psychological Safety and Learning Behavior in Work Teams* — nền tảng nghiên cứu về việc nêu vấn đề và học hỏi trong nhóm.
- Nicole Forsgren, Jez Humble và Gene Kim (2018), *Accelerate* — nghiên cứu năng lực giao phần mềm và hiệu quả tổ chức.
- Mik Kersten (2018), *Project to Product* — tư duy dịch chuyển đầu tư và quản trị theo dòng giá trị sản phẩm.
