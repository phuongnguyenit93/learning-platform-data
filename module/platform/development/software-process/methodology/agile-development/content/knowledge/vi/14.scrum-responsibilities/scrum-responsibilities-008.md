# Cộng tác với bên liên quan và chuyên gia ngoài Scrum Team

> **Ý tưởng cốt lõi:** Scrum Team chịu trách nhiệm tạo ra Increment có giá trị trong mỗi Sprint, nhưng không thể và không cần sở hữu mọi kiến thức về khách hàng, pháp lý, bảo mật, hạ tầng, dữ liệu hoặc nghiệp vụ. Cộng tác tốt nghĩa là **mời đúng người đóng góp đúng lúc, đưa bằng chứng vào quyết định và giữ rõ trách nhiệm của Scrum Team**. Cộng tác không đồng nghĩa với trao quyền điều hành Sprint cho tất cả người có ý kiến.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **thành viên Scrum Team**, **stakeholder (bên liên quan)** và **chuyên gia bên ngoài Scrum Team**.
2. Giải thích trách nhiệm của **Product Owner**, **Scrum Master** và **Developers** khi tiếp nhận phản hồi hoặc hỗ trợ chuyên môn.
3. Xác định **ai cần được tham vấn, ai ra quyết định, ai cần được thông báo** mà không biến mô hình Scrum thành chuỗi phê duyệt cồng kềnh.
4. Lựa chọn thời điểm phối hợp phù hợp: khám phá vấn đề, làm rõ Product Backlog, Sprint Planning, thực hiện trong Sprint và Sprint Review.
5. Làm việc với chuyên gia về bảo mật, UX, vận hành, dữ liệu, pháp lý hoặc hệ thống tích hợp để giảm rủi ro mà vẫn bảo vệ **Sprint Goal** và **Definition of Done**.
6. Dùng user story, acceptance criteria, ví dụ Gherkin, thỏa thuận giao tiếp và quản lý phụ thuộc để chuyển ý kiến thành hành động có thể kiểm chứng.
7. Nhận diện các sai lầm như stakeholder giao việc trực tiếp cho Developer, chuyên gia trở thành nút phê duyệt duy nhất, hoặc Sprint Review chỉ còn là báo cáo thành tích.

## 2. Vì sao một Scrum Team vẫn cần cộng tác bên ngoài?

Hãy tưởng tượng một nhóm phát triển nền tảng học trực tuyến đang bổ sung đăng nhập dành cho khách hàng doanh nghiệp. Nhóm có thể xây giao diện, backend và kiểm thử, nhưng vẫn cần thông tin từ:

- **Người học và quản trị viên doanh nghiệp:** quy trình đăng nhập thực tế, lỗi họ thường gặp và yêu cầu sử dụng.
- **Đối tác cung cấp hệ thống định danh:** hợp đồng API, giới hạn môi trường thử, cách xử lý phiên đăng nhập.
- **Chuyên gia bảo mật và quyền riêng tư:** những kiểm soát bắt buộc khi nhận hoặc lưu thông tin tài khoản.
- **Chuyên gia UX và khả năng tiếp cận:** hành trình đăng nhập, thông báo lỗi, người dùng sử dụng công nghệ hỗ trợ.
- **Đội vận hành và hỗ trợ:** giám sát lỗi, phương án xử lý sự cố, hướng dẫn khi kết nối bên ngoài bị gián đoạn.
- **Bộ phận kinh doanh hoặc pháp lý:** điều kiện hợp đồng, mốc bàn giao, cam kết với khách hàng và việc tuân thủ liên quan.

Nếu chỉ phát triển theo giả định nội bộ, Scrum Team có thể giao đúng số lượng chức năng nhưng sai nhu cầu hoặc gặp rủi ro khi tích hợp. Ngược lại, nếu từng bên ngoài được quyền thêm việc và đổi ưu tiên bất kỳ lúc nào, nhóm khó duy trì Sprint Goal.

Mục đích của cộng tác là tạo **vòng phản hồi sớm**: làm rõ vấn đề → chọn việc có giá trị → xây một Increment đủ chất lượng → kiểm tra với người có hiểu biết phù hợp → điều chỉnh theo kết quả.

## 3. Ai là ai trong và ngoài Scrum Team?

### 3.1. Cấu trúc chính thức của Scrum Team

Theo *Scrum Guide (2020)*, Scrum Team nhỏ, có tính gắn kết và gồm **một Scrum Master, một Product Owner và Developers**. Scrum Team không có tiểu nhóm hoặc cấp bậc nội bộ; các thành viên cùng tập trung vào **một mục tiêu tại một thời điểm: Product Goal**.

| Trách nhiệm trong Scrum | Trọng tâm | Khi làm việc với người ngoài |
|---|---|---|
| **Product Owner** | Chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog | Thu thập nhu cầu, trao đổi đánh đổi, làm rõ thứ tự ưu tiên và Product Goal |
| **Scrum Master** | Chịu trách nhiệm thiết lập Scrum theo Scrum Guide và giúp Scrum Team nâng cao hiệu quả | Hỗ trợ cách cộng tác, tạo điều kiện cho trao đổi hiệu quả, hỗ trợ loại bỏ trở ngại giữa stakeholders và Scrum Team |
| **Developers** | Chịu trách nhiệm tạo kế hoạch Sprint Backlog, bảo đảm chất lượng theo DoD, thích ứng kế hoạch từng ngày và chịu trách nhiệm nghề nghiệp với nhau | Trao đổi trực tiếp yêu cầu kỹ thuật/nghiệp vụ, kiểm chứng khả thi, đề xuất giải pháp và tích hợp thành Increment |
| **Scrum Team nói chung** | Chịu trách nhiệm với mọi hoạt động liên quan sản phẩm như hợp tác với stakeholders, kiểm chứng, vận hành, nghiên cứu và phát triển | Tổ chức công việc để tạo Increment có giá trị mà không bị chia thành các tuyến trách nhiệm tách rời cứng nhắc |

**Scrum không định nghĩa một vai trò chính thức thứ tư tên là “stakeholder”, “business analyst”, “architect” hoặc “QA approver”.** Những người có kỹ năng phân tích, kiểm thử, thiết kế, kiến trúc có thể là Developers nếu họ là thành viên Scrum Team và cùng chịu trách nhiệm tạo Increment. Tên chức danh trong tổ chức không tự quyết định họ ở trong hay ngoài Scrum Team.

Product Owner là **một người, không phải một ủy ban**. Người này có thể ủy quyền thực hiện một số công việc quản lý Product Backlog nhưng vẫn giữ **trách nhiệm cuối cùng (accountability)**. Những người muốn thay đổi Product Backlog cần thuyết phục Product Owner bằng vấn đề, bằng chứng và giá trị, không tự ý thay thứ tự công việc.

### 3.2. Stakeholder là ai?

**Stakeholder** là cá nhân hoặc nhóm có nhu cầu, chịu tác động bởi sản phẩm, có thông tin hoặc ảnh hưởng đến quyết định về sản phẩm. Ví dụ:

| Nhóm stakeholder | Quan tâm chính | Thông tin hữu ích |
|---|---|---|
| Người dùng cuối | Tác vụ hoàn thành dễ, đúng và an toàn | Hành vi sử dụng, vấn đề, phản hồi về Increment |
| Khách hàng trả tiền/đại diện doanh nghiệp | Kết quả kinh doanh, khả năng sử dụng, điều kiện hợp đồng | Mục tiêu, mức ưu tiên, hạn bắt buộc, quy tắc nghiệm thu |
| Hỗ trợ khách hàng | Sự cố và câu hỏi người dùng thường gặp | Mẫu khiếu nại, điểm khó hiểu, chi phí hỗ trợ |
| Kinh doanh/marketing | Phân khúc khách hàng, cơ hội thị trường, mốc chiến dịch | Bối cảnh và giả thuyết về nhu cầu |
| Quản lý vận hành | Độ ổn định, khả năng quan sát, an toàn khi triển khai | Rủi ro phát hành, nhu cầu giám sát và ứng cứu |
| Tài chính/pháp lý | Chi phí, nghĩa vụ và mức rủi ro chấp nhận | Điều khoản, thời điểm, giới hạn cần tôn trọng |

Một người có thể đồng thời là **stakeholder và chuyên gia**. Chẳng hạn người quản lý vận hành vừa chịu ảnh hưởng bởi các bản phát hành vừa có chuyên môn quan trọng về khôi phục dịch vụ.

### 3.3. Chuyên gia ngoài Scrum Team là ai?

Đây là những người có tri thức hoặc thẩm quyền cần thiết cho một vấn đề, nhưng **không phải thành viên của Scrum Team đang chịu trách nhiệm tạo Increment**.

Ví dụ: chuyên gia bảo mật được mời đánh giá thiết kế đăng nhập; kỹ sư từ đối tác định danh giải thích giao thức tích hợp; nhà nghiên cứu UX hỗ trợ quan sát người dùng; chuyên viên pháp lý xác nhận nghĩa vụ xử lý dữ liệu.

Nhóm có thể nhờ chuyên gia tư vấn, cùng phân tích rủi ro hoặc thực hiện công việc theo thỏa thuận. Tuy nhiên, việc họ tham gia **không tự động chuyển trách nhiệm của Product Owner, Scrum Master hay Developers** sang họ.

### 3.4. Một nguyên tắc phân biệt thực dụng

Hãy hỏi:

> “Người này có thuộc Scrum Team và cùng chịu trách nhiệm liên tục với Increment, hay chỉ cung cấp nhu cầu, bằng chứng, chuyên môn hoặc chấp thuận theo một thẩm quyền bên ngoài?”

Điều này giúp tránh hiểu nhầm:

- Một chuyên gia an ninh thuộc Scrum Team có thể là **Developer** theo nghĩa trách nhiệm Scrum, dù chức danh hành chính là Security Engineer.
- Một chuyên gia an ninh từ bộ phận khác là **người hỗ trợ bên ngoài**, không phải Scrum Master hay Product Owner thứ hai.
- Một giám đốc sản phẩm ở cấp tổ chức không mặc nhiên là Product Owner của Scrum Team, nếu trách nhiệm Product Owner đã thuộc người khác.

## 4. Ranh giới cộng tác và quyền quyết định

Nhóm tự quản lý không có nghĩa tự miễn trừ mọi chính sách của tổ chức. Ngược lại, việc tham vấn chuyên gia hoặc stakeholder không có nghĩa ai tham gia cũng được phân công trực tiếp cho Developers.

| Câu hỏi/quyết định | Trách nhiệm chính | Người cần cung cấp thông tin |
|---|---|---|
| Product Goal và thứ tự Product Backlog | **Product Owner** | Người dùng, khách hàng, Developers, chuyên gia, các stakeholder |
| Sprint Goal và kế hoạch của Sprint | **Scrum Team** hình thành Sprint Goal trong Sprint Planning; **Developers** chọn PBI và lập kế hoạch | Product Owner cung cấp bối cảnh, chuyên gia được mời khi cần lời khuyên |
| Cách xây dựng, chia nhỏ, kiểm thử, tích hợp | **Developers** | Chuyên gia kỹ thuật/nghiệp vụ, Product Owner về hành vi mong muốn |
| Chuẩn chất lượng và xác nhận đạt DoD | **Scrum Team** chịu trách nhiệm tạo Increment đạt DoD; Developers cam kết tuân thủ DoD | Chuyên gia chất lượng, bảo mật, vận hành; chuẩn tổ chức khi áp dụng |
| Cải thiện cách áp dụng Scrum và gỡ trở ngại | **Scrum Master** chịu trách nhiệm hiệu quả Scrum Team, cùng Scrum Team thực hiện thay đổi | Tổ chức, quản lý, chuyên gia hỗ trợ phối hợp |
| Chấp thuận ngoại lệ bảo mật, hợp đồng hoặc pháp lý | **Người có thẩm quyền theo chính sách hiện hành** | Product Owner, Developers, chuyên gia và đơn vị liên quan |
| Điều chỉnh phạm vi trong Sprint | Developers thương lượng với **Product Owner**, bảo vệ Sprint Goal | Stakeholder được thông tin khi phạm vi cam kết bị ảnh hưởng |
| Hủy Sprint khi Sprint Goal trở nên lỗi thời | **Product Owner** | Scrum Team và stakeholder cung cấp thông tin về bối cảnh |

**Lưu ý:** bảng phân công trên là cách diễn giải trách nhiệm để phối hợp, không phải ma trận RACI chính thức bắt buộc của Scrum. Nhiều quyết định sản phẩm đòi hỏi hợp tác; thẩm quyền về an toàn, pháp lý, hợp đồng hoặc phát hành có thể được tổ chức quy định riêng. Scrum không cho phép một cá nhân tự bỏ qua những nghĩa vụ đó.

### Ví dụ về việc vượt ranh giới

Một stakeholder gửi thẳng cho Developer: “Thêm đăng nhập Google vào Sprint hiện tại, việc này phải xong trước thứ Sáu.”

Phản ứng tốt không phải luôn từ chối trao đổi với stakeholder. Developer có thể hỏi về vấn đề người dùng và đánh giá kỹ thuật. Nhưng **quyết định đổi thứ tự Product Backlog và tác động lên Sprint Goal** cần được xử lý cùng Product Owner và Developers theo trách nhiệm của Scrum Team. Không nên tạo một backlog bí mật qua tin nhắn cá nhân.

Ngược lại, Product Owner có thể thống nhất giá trị của tính năng, nhưng không nên tự quyết định mọi chi tiết lập trình và áp đặt giải pháp kỹ thuật mà không trao đổi với Developers.

## 5. Cộng tác dựa trên ba trụ cột Scrum và các giá trị

Scrum dựa trên **minh bạch, kiểm tra và thích ứng**. Làm việc với stakeholder và chuyên gia tạo thêm góc nhìn để ba trụ cột trở nên hữu ích.

~~~mermaid
flowchart TD
    A["Product Goal và nhu cầu người dùng"] --> B["Phản hồi stakeholder / bằng chứng chuyên gia"]
    B --> C["Product Owner và Scrum Team làm rõ quyết định"]
    C --> D["Product Backlog và Sprint Goal"]
    D --> E["Developers tạo Increment đạt DoD"]
    E --> F["Kiểm tra kết quả với người liên quan"]
    F --> G["Học, điều chỉnh backlog hoặc cách làm"]
    G --> B
~~~

### 5.1. Minh bạch: thông tin nào cần được chia sẻ?

- **Mục tiêu:** người dùng sẽ được lợi gì; Product Goal và Sprint Goal liên quan thế nào?
- **Trạng thái:** phần nào đã đạt Definition of Done, phần nào đang thử hoặc bị chặn?
- **Rủi ro và giả định:** điều gì đã được xác nhận, điều gì chưa chắc chắn?
- **Phụ thuộc:** đang chờ ai, cần quyết định gì và hậu quả nếu chậm?
- **Giới hạn chuyên môn:** những trường hợp bắt buộc phải tham vấn hoặc kiểm chứng trước khi phát hành?

Minh bạch không có nghĩa chia sẻ tài liệu nhạy cảm, thông tin nhận dạng cá nhân hoặc bí mật thương mại cho tất cả người tham gia. Cần dùng **quyền truy cập phù hợp và dữ liệu tối thiểu cần thiết**.

### 5.2. Kiểm tra: hỏi gì để cuộc trao đổi có ích?

Ví dụ, khi chuyên gia bảo mật xem luồng đăng nhập, nhóm không chỉ hỏi “Thiết kế này ổn không?”. Câu hỏi tốt hơn:

> “Nếu token hết hạn giữa lúc người học mở bài, trạng thái nào phải được xử lý? Nếu hệ thống đối tác từ chối xác thực, người học nhận thông điệp gì? Điều kiện nào khiến việc phát hành không được chấp nhận?”

Kiểm tra cần có **một đối tượng cụ thể**: Increment, kịch bản sử dụng, thiết kế tích hợp, hợp đồng API, lỗi tái hiện hoặc số liệu. Những nhận định khác nhau cần được đưa về ví dụ hoặc bằng chứng có thể xác nhận.

### 5.3. Thích ứng: phản hồi phải dẫn đến quyết định rõ

Sau buổi trao đổi, nhóm có thể:

- Chỉnh **Product Backlog** vì phát hiện vấn đề người dùng quan trọng hơn.
- Bổ sung **acceptance criteria** cho tình huống lỗi, quyền truy cập hoặc khả năng tiếp cận.
- Thực hiện một **spike** giới hạn thời gian để kiểm tra tính khả thi tích hợp.
- Thương lượng **phạm vi trong Sprint** với Product Owner để bảo vệ Sprint Goal.
- Đổi cách phối hợp để giảm thời gian chờ chuyên gia.

Không phải mọi phản hồi đều phải trở thành PBI ngay. Có thể giữ nguyên quyết định nếu bằng chứng mới chưa đủ, nhưng cần nói rõ lý do và điều kiện xem lại.

### 5.4. Năm giá trị Scrum giúp cộng tác an toàn

| Scrum Value | Biểu hiện khi làm việc với người ngoài |
|---|---|
| **Commitment – Cam kết** | Cùng hướng tới mục tiêu sản phẩm, không chỉ bảo vệ quyền lợi cục bộ |
| **Focus – Tập trung** | Ưu tiên thông tin giúp đạt Sprint Goal và Product Goal; tránh thêm việc không kiểm soát |
| **Openness – Cởi mở** | Nêu vấn đề, trạng thái chưa Done và giả định còn thiếu, kể cả khi không thuận tai |
| **Respect – Tôn trọng** | Tôn trọng chuyên môn, vai trò, dữ liệu và thời gian của người khác |
| **Courage – Can đảm** | Đặt câu hỏi khó, từ chối rủi ro không chấp nhận được, nói rõ khi deadline chưa khả thi |

## 6. Xác định stakeholder cần phối hợp mà không tạo bộ máy quan liêu

Không cần mời mọi stakeholder vào mọi cuộc họp. Hãy lập bản đồ đơn giản theo **điều họ biết**, **quyết định họ có thể tác động** và **thời điểm nhóm cần thông tin**.

### 6.1. Bảng cộng tác mẫu

| Bên liên quan/chuyên gia | Cần họ giúp gì? | Thời điểm phù hợp | Kênh phù hợp |
|---|---|---|---|
| Người dùng thử | Xác nhận vấn đề, thử luồng, phản hồi hành vi | Khám phá và sau Increment phù hợp | Quan sát tác vụ, phỏng vấn, phiên thử |
| Product Owner | Làm rõ giá trị và thứ tự PBI | Liên tục khi có thông tin mới | Trao đổi ngắn, cập nhật backlog |
| Chuyên gia bảo mật | Xác định rủi ro và kiểm soát thiết yếu | Sớm trước thiết kế rủi ro cao, khi kiểm chứng | Review threat model, kịch bản, PR cần thiết |
| Chuyên gia UX/accessibility | Kiểm tra hành trình người dùng và tiếp cận | Trước khi khóa quyết định UX, khi có prototype | Prototype review, thử nghiệm |
| Đối tác API | Xác nhận hợp đồng giao tiếp, lỗi, môi trường thử | Trước và trong tích hợp | API contract, phiên kỹ thuật tập trung |
| Vận hành/SRE | Giám sát, rollback, độ ổn định, cảnh báo | Từ lúc thiết kế đến trước phát hành | Kịch bản sự cố, kế hoạch triển khai |
| Pháp lý/quyền riêng tư | Điều kiện thu thập và xử lý dữ liệu | Trước xử lý dữ liệu có rủi ro | Danh sách câu hỏi cụ thể, bằng chứng kiểm soát |
| Hỗ trợ khách hàng | Tình huống lỗi thực tế và cách hướng dẫn | Khi chọn vấn đề và chuẩn bị ra mắt | Tổng hợp ticket, hướng dẫn xử lý |

Đây là **mẫu minh họa**, cần thay bằng vai trò và chính sách thực tế của tổ chức. Nếu chuyên môn đã có trong Scrum Team, không cần tạo tuyến tham vấn ngoài riêng chỉ để đủ biểu mẫu.

### 6.2. Phân biệt “cần tham vấn” với “cần phê duyệt”

- **Tham vấn (consultation):** chuyên gia góp bằng chứng, chỉ ra rủi ro hoặc đề xuất phương án.
- **Quyết định sản phẩm:** Product Owner quyết định thứ tự và tính hiệu quả của Product Backlog sau khi xem thông tin liên quan.
- **Quyết định triển khai:** Developers quyết định cách thực hiện, kiểm thử và điều chỉnh Sprint Backlog.
- **Phê duyệt bắt buộc:** áp dụng khi có chính sách hoặc nghĩa vụ cụ thể về an toàn, tuân thủ, hợp đồng, phát hành.

Không gọi mọi cuộc trao đổi là “approval” nếu thực tế chỉ cần tư vấn. Cũng không được bỏ một phê duyệt thực sự bắt buộc bằng cách nói “Scrum tự quản lý”.

### 6.3. Câu hỏi lựa chọn người tham gia

Trước một buổi trao đổi, hỏi:

1. **Quyết định** nào cần đưa ra?
2. **Kiến thức** nào nhóm đang thiếu?
3. Ai có **bằng chứng trực tiếp** hoặc chịu tác động quan trọng?
4. Ai có **thẩm quyền ngoài Scrum** cần được xem xét?
5. Những ai chỉ cần đọc **kết luận bất đồng bộ** thay vì tham gia thời gian thực?

Nếu không có quyết định hoặc rủi ro cụ thể cần giải quyết, một tài liệu ngắn hay câu hỏi trên issue có thể hiệu quả hơn một cuộc họp đông người.

## 7. Cộng tác qua các giai đoạn và sự kiện Scrum

### 7.1. Khám phá vấn đề và quản lý Product Backlog

Product Owner có trách nhiệm quản lý Product Backlog hiệu quả, bao gồm phát triển và truyền đạt Product Goal, tạo và làm rõ PBI, sắp thứ tự PBI, bảo đảm backlog minh bạch và dễ hiểu.

Product Owner cần **tìm hiểu người dùng và stakeholder**, nhưng không nhất thiết tự thực hiện mọi cuộc phỏng vấn hoặc viết mọi tiêu chí. Scrum Team có thể cùng nghiên cứu và làm rõ công việc. Khi nhiều stakeholder đề xuất giải pháp, cần đưa các ý kiến về câu hỏi: **“Vấn đề thực tế là gì và ảnh hưởng tới Product Goal ra sao?”**

Ví dụ: doanh nghiệp đề nghị thêm một hệ thống báo cáo mới. Thay vì tạo ngay epic lớn, nhóm hỏi họ đang khó ra quyết định gì, số liệu nào thiếu và liệu một báo cáo đơn giản có đủ kiểm chứng nhu cầu trước không.

### 7.2. Backlog refinement: chuyên gia giúp làm rõ trước khi làm

**Product Backlog refinement** là hoạt động làm rõ và chia nhỏ PBI thường xuyên khi cần, không phải một sự kiện Scrum chính thức với thời lượng bắt buộc.

Một phiên làm rõ với chuyên gia có thể tập trung:

- Ví dụ nghiệp vụ thường gặp và trường hợp biên.
- Rủi ro tích hợp, bảo mật, tính sẵn có hoặc quyền riêng tư.
- Cách nhận biết hành vi đúng qua acceptance criteria.
- Điều gì chưa biết, nên làm spike hay nghiên cứu trước?
- Những phụ thuộc cần giải quyết để PBI đủ rõ cho Sprint gần.

Không biến refinement thành buổi phê duyệt thiết kế chi tiết của toàn bộ sản phẩm nhiều tháng trước. Cần đủ hiểu biết để đưa ra **quyết định tiếp theo**, không phải giả định tương lai sẽ không đổi.

### 7.3. Sprint Planning: mời lời khuyên, không giao quyền lập kế hoạch

Scrum Team xác định vì sao Sprint có giá trị, điều gì có thể được thực hiện và làm như thế nào. **Scrum Guide cho phép mời người khác tham dự Sprint Planning để đưa ra lời khuyên**.

Ví dụ, chuyên gia hệ thống định danh giải thích rằng môi trường thử của đối tác chưa hỗ trợ tình huống hết hạn token. Thông tin này ảnh hưởng tới rủi ro và lựa chọn PBI. Nhưng chuyên gia không tự quyết định Sprint Goal hoặc phân công cho Developers.

### 7.4. Daily Scrum: Developers kiểm tra tiến độ

**Daily Scrum là sự kiện 15 phút cho Developers** kiểm tra tiến độ đối với Sprint Goal và điều chỉnh Sprint Backlog. Nó không phải phiên báo cáo trạng thái bắt buộc cho stakeholder hoặc quản lý.

Nếu Product Owner hoặc Scrum Master trực tiếp làm việc trên các hạng mục Sprint Backlog, họ tham gia Daily Scrum với tư cách Developers cho phần công việc đó. Scrum Team vẫn có thể trao đổi với chuyên gia **ngoài Daily Scrum** khi cần xử lý vấn đề; không phải cứ có câu hỏi cho người ngoài là mời họ dự hằng ngày.

Ví dụ: Developers nhận ra lỗi SSO phải nhờ kỹ sư đối tác xác nhận. Nhóm nêu điểm tắc trong Daily Scrum rồi bố trí **một phiên kỹ thuật riêng** với người đối tác phù hợp.

### 7.5. Sprint Review: không chỉ trình diễn, mà kiểm tra cùng stakeholder

Trong Sprint Review, Scrum Team trình bày kết quả công việc và **các stakeholder quan trọng** cùng kiểm tra Increment, tiến độ Product Goal và bối cảnh thay đổi. Đây là **phiên làm việc** nhằm xem bước tiếp theo phù hợp, không chỉ là buổi trình chiếu slide.

Một Sprint Review tốt:

- Cho thấy **Increment thực sự đạt Definition of Done**.
- Nêu điều đã học từ dữ liệu sử dụng, phản hồi hoặc thử nghiệm.
- Cho stakeholder cơ hội xem **hành vi thật** và nêu vấn đề.
- Đối chiếu kết quả với mục tiêu, thảo luận những thay đổi có thể cần trong Product Backlog.

**Sprint Review không phải cổng phê duyệt phát hành bắt buộc.** Một Increment có thể được bàn giao trước khi Sprint kết thúc; phần chưa đạt DoD không được gọi là Increment đã hoàn thành để đem trình bày như Done.

### 7.6. Sprint Retrospective: trọng tâm là cải tiến của Scrum Team

Scrum Team kiểm tra cách phối hợp, công cụ, chất lượng và hiệu quả để chọn cải tiến. Nếu quá nhiều công việc bị chặn vì chờ chuyên gia, Retrospective có thể đưa ra thử nghiệm về thỏa thuận phản hồi, cách chuẩn bị câu hỏi hoặc cách giảm phụ thuộc.

Retrospective là sự kiện của Scrum Team. **Không phải mặc định mời tất cả stakeholder** vào đây, đặc biệt nếu điều đó khiến thành viên không dám thảo luận vấn đề thực tế. Nhóm có thể thu thập đầu vào từ bên ngoài trước hoặc tổ chức phiên làm việc phù hợp riêng nếu cần.

## 8. Cách đặt câu hỏi để khai thác chuyên môn hiệu quả

Một yêu cầu mơ hồ khiến chuyên gia khó phản hồi, mất nhiều lượt hỏi đáp. Hãy chuẩn bị **bối cảnh, quyết định cần hỗ trợ, phương án và bằng chứng**.

### 8.1. Mẫu câu hỏi cho chuyên gia

~~~text
Bối cảnh:
  Scrum Team phát triển luồng đăng nhập doanh nghiệp qua SSO.

Mục tiêu:
  Người học được xác thực an toàn và vào bài đầu tiên thuận lợi.

Vấn đề cụ thể:
  Hệ thống đối tác trả lỗi khi token hết hạn giữa hai bước.

Điều đã quan sát:
  Mã phản hồi và thời điểm lỗi trong môi trường thử, không chứa token thật.

Điều còn chưa biết:
  Cách xác nhận trạng thái, xử lý thử lại và trải nghiệm người dùng phù hợp.

Phương án đang cân nhắc:
  (A) Yêu cầu đăng nhập lại; (B) làm mới phiên nếu an toàn và được hỗ trợ.

Câu hỏi cần chuyên gia hỗ trợ:
  Điều kiện bảo mật nào loại trừ một phương án?
  Có tài liệu/hợp đồng API nào xác nhận không?

Mốc cần phản hồi:
  Trước thời điểm nhóm chốt kịch bản tích hợp quan trọng trong Sprint.

Người liên hệ và nơi ghi quyết định:
  Liên kết PBI / quyết định kỹ thuật / tài liệu tích hợp được kiểm soát quyền.
~~~

Tránh gửi dữ liệu định danh cá nhân, token, mật khẩu hoặc nội dung bí mật qua kênh không phù hợp. Dùng dữ liệu thử, che thông tin nhạy cảm và tuân thủ chính sách của tổ chức.

### 8.2. Trao đổi đồng bộ hay bất đồng bộ?

| Tình huống | Kênh thường phù hợp | Lý do |
|---|---|---|
| Câu hỏi ngắn về một điều kiện API đã có tài liệu | Issue, bình luận PR hoặc thông điệp có ngữ cảnh | Dễ lưu lại, không cần làm gián đoạn nhiều người |
| Hai bên hiểu khác nhau về quy tắc nghiệp vụ quan trọng | Cuộc trao đổi ngắn theo ví dụ, ghi kết luận sau | Phản hồi hai chiều giúp sửa hiểu nhầm nhanh |
| Cần quan sát người dùng gặp khó | Phiên thử khả dụng hoặc demo có nhiệm vụ rõ | Xem hành vi thay vì chỉ hỏi ý kiến |
| Thay đổi kiến trúc có nhiều đánh đổi | Workshop tập trung, quyết định bằng văn bản | Cần so sánh lựa chọn và lưu lý do |
| Thông báo trạng thái đã có quyết định | Bản cập nhật ngắn tại nguồn chung | Tránh họp chỉ để chuyển tiếp thông tin |
| Sự cố khẩn, rủi ro an toàn cao | Kênh ứng cứu theo chính sách, sau đó ghi hậu kiểm | Cần phản ứng nhanh, không chờ chu kỳ họp thông thường |

Nguyên tắc **“nói để hiểu, viết để nhớ”**: dùng đối thoại khi cần làm rõ nhanh; ghi lại quyết định, tiêu chí và phụ thuộc để người không tham gia vẫn có thông tin đúng.

### 8.3. Một phiên làm rõ 30 phút có cấu trúc

Ví dụ cách điều phối linh hoạt, không phải timebox bắt buộc của Scrum:

1. **5 phút:** nêu Product Goal/Sprint Goal liên quan và trường hợp người dùng.
2. **10 phút:** chuyên gia giải thích ràng buộc, nhóm đặt câu hỏi qua ví dụ.
3. **10 phút:** cùng xem các tình huống chính, lỗi, lựa chọn và rủi ro.
4. **5 phút:** chốt điều đã rõ, người chịu trách nhiệm tìm phần chưa rõ và nơi lưu kết quả.

Nếu vấn đề không được giải quyết trong thời gian này, không ép một quyết định thiếu căn cứ chỉ để đúng lịch. Ghi phần chưa biết và chọn cách giảm bất định tiếp theo.

## 9. User story, acceptance criteria và Three Amigos

### 9.1. Vì sao cần ví dụ cụ thể?

Một stakeholder có thể nói “Đăng nhập phải mượt mà”, còn chuyên gia bảo mật nói “Phải an toàn”. Hai nhận định đều quan trọng nhưng chưa đủ để Developers lập trình và kiểm thử. Scrum Team cần làm rõ **hành vi có thể kiểm chứng**.

**User story minh họa:**

> “Là người học thuộc doanh nghiệp đã được cấp quyền, tôi muốn đăng nhập bằng tài khoản doanh nghiệp để truy cập các khóa học được phép mà không phải tạo mật khẩu mới.”

**Ba góc nhìn thường dùng trong kỹ thuật Three Amigos:**

- **Nghiệp vụ/sản phẩm:** ai được quyền truy cập, giá trị và trường hợp cần hỗ trợ?
- **Phát triển:** thiết kế luồng, trạng thái lỗi, phụ thuộc API có gì cần xác minh?
- **Kiểm thử/chất lượng:** ví dụ nào sẽ chứng minh đúng hoặc phát hiện trường hợp sai?

Three Amigos là **thực hành cộng tác có thể chọn dùng**, không phải một sự kiện hay ba vai trò mới bắt buộc trong Scrum. Người có góc nhìn kiểm thử hoặc nghiệp vụ có thể là Developers trong Scrum Team; chuyên gia bên ngoài có thể được mời khi kiến thức của họ cần thiết.

### 9.2. Acceptance criteria qua ví dụ Gherkin

~~~gherkin
Tính năng: Đăng nhập bằng hệ thống định danh doanh nghiệp

Kịch bản: Người học hợp lệ đăng nhập thành công
  Cho trước người học thuộc doanh nghiệp được phép sử dụng SSO
  Và tài khoản doanh nghiệp đang hợp lệ
  Khi người học hoàn tất xác thực qua nhà cung cấp định danh được cấu hình
  Thì hệ thống chỉ cấp quyền vào tài nguyên học tập phù hợp
  Và người học được chuyển tới trạng thái đăng nhập hợp lệ

Kịch bản: Tài khoản không được cấp quyền
  Cho trước danh tính không có quyền vào sản phẩm
  Khi có yêu cầu đăng nhập bằng hệ thống doanh nghiệp
  Thì hệ thống không cấp quyền truy cập khóa học được bảo vệ
  Và phản hồi lỗi phù hợp, không để lộ thông tin nội bộ nhạy cảm

Kịch bản: Dịch vụ định danh bên ngoài không khả dụng
  Cho trước dịch vụ định danh không thể hoàn tất yêu cầu
  Khi người học thử đăng nhập
  Thì hệ thống không báo đăng nhập thành công khi chưa được xác thực
  Và cung cấp hướng dẫn thử lại hoặc liên hệ hỗ trợ phù hợp

Kịch bản: Phiên đăng nhập hết hiệu lực
  Cho trước phiên của người học đã hết hiệu lực theo chính sách áp dụng
  Khi người học yêu cầu nội dung cần xác thực
  Thì hệ thống không cho phép sử dụng phiên đã hết hiệu lực
  Và hướng người học tới cách xác thực lại phù hợp
~~~

Các kịch bản này minh họa hành vi, **không phải bản đặc tả đầy đủ cho một giao thức định danh cụ thể**. Chuyên gia bảo mật và đối tác cung cấp dịch vụ cần xác nhận yêu cầu về token, giao thức, phiên, quyền và điều kiện kiểm thử theo hệ thống thực tế. Không đưa dữ liệu xác thực thật vào ví dụ hoặc log.

### 9.3. Definition of Done và chuẩn ngoài Scrum Team

Các acceptance criteria mô tả **hành vi riêng của PBI**. **Definition of Done (DoD)** là mô tả chính thức về trạng thái Increment khi đáp ứng các tiêu chuẩn chất lượng sản phẩm.

Ví dụ DoD liên quan:

- Đã tích hợp và kiểm thử hành vi chính, lỗi quan trọng, quyền truy cập và hồi quy.
- Mã và cấu hình đáp ứng quy chuẩn an toàn, quyền riêng tư và quản lý bí mật áp dụng.
- Có cơ chế theo dõi sự cố thích hợp mà không ghi dữ liệu nhạy cảm không cần thiết.
- Các ràng buộc vận hành/phát hành được kiểm tra theo chính sách của tổ chức.
- Những phần đã hoàn thành tạo thành Increment có thể sử dụng được.

Nếu tổ chức có chuẩn Definition of Done áp dụng cho sản phẩm, Scrum Team phải tuân theo **mức tối thiểu đó**; Scrum Team có thể xây DoD phù hợp và nghiêm ngặt hơn. Không được gọi PBI là Done chỉ vì một chuyên gia “đã xem qua” trong khi chất lượng và tích hợp còn thiếu.

## 10. Tình huống xuyên suốt: tích hợp đăng nhập doanh nghiệp

### 10.1. Bối cảnh

Một Scrum Team phát triển nền tảng học trực tuyến cho nhân viên doanh nghiệp. Product Owner đặt **Product Goal** là giúp nhân viên của khách hàng doanh nghiệp bắt đầu học nhanh và truy cập đúng khóa được cấp quyền.

Trong một Sprint hai tuần, **Sprint Goal** được hình thành:

> “Có một luồng đăng nhập doanh nghiệp tích hợp cơ bản cho nhóm người dùng thử, xử lý đúng các trường hợp xác thực thành công và thất bại, đạt DoD và có thể quan sát lỗi.”

Để đạt mục tiêu, nhóm cần hợp tác với ba đối tượng ngoài Scrum Team:

1. **Kỹ sư đối tác định danh:** giải thích hợp đồng API, cung cấp môi trường thử và dữ liệu kiểm thử.
2. **Chuyên gia bảo mật nội bộ:** xác định kiểm soát truy cập, xử lý phiên và yêu cầu log.
3. **Đại diện khách hàng doanh nghiệp:** mô tả quyền học tập, hành vi khi tài khoản bị vô hiệu hóa và cách hỗ trợ người học.

### 10.2. Trước Sprint: làm rõ để tránh phụ thuộc ẩn

Product Owner trao đổi với khách hàng về nhu cầu: doanh nghiệp không muốn nhân viên phải quản lý thêm mật khẩu; nhưng chỉ những người được cấp quyền mới được học.

Developers đề nghị một phiên ngắn với đối tác và chuyên gia bảo mật để hiểu:

- Môi trường thử có hỗ trợ các trường hợp thành công, thất bại và phiên hết hạn không?
- Danh tính và vai trò được ánh xạ vào tài khoản học thế nào?
- Có yêu cầu về thời gian phản hồi, quyền truy cập hoặc dữ liệu nhạy cảm nào không?
- Có phần nào nên thử bằng một **spike kỹ thuật** trước khi cam kết phạm vi lớn?

Nhóm ghi các câu trả lời vào PBI và quyết định tích hợp, không cần sao chép toàn bộ tài liệu của đối tác sang backlog.

### 10.3. Trong Sprint: phụ thuộc ngoài nhóm trở thành điểm tắc

Sau một số ngày, Developers phát hiện API trả lỗi khác tài liệu khi phiên hết hạn. Kỹ sư đối tác chưa trả lời câu hỏi; một stakeholder đề nghị bỏ qua tình huống đó để kịp demo.

**Minh bạch:** nhóm ghi rõ PBI đang bị chặn một phần, điều đã kiểm chứng, điều chưa rõ, người cần phối hợp và ảnh hưởng có thể tới Sprint Goal.

**Kiểm tra:** nhóm xem lại DoD và rủi ro truy cập; hỏi chuyên gia bảo mật liệu có phương án tạm thời an toàn được phép sử dụng trong phạm vi thử hay không.

**Thích ứng:** Developers cùng Product Owner cân nhắc phạm vi. Có thể giảm một thành phần giao diện không thiết yếu, tập trung xử lý trường hợp lỗi và chỉ phát hành luồng đáp ứng chất lượng. Nếu vấn đề an toàn chưa được giải quyết, **không công bố chức năng chưa bảo đảm là đã hoàn thành**.

### 10.4. Một nhật ký quyết định ngắn

~~~markdown
Mã minh họa: DEC-SSO-04
Mục tiêu: Nhóm người dùng thử đăng nhập an toàn và vào đúng khóa học
Tín hiệu: API đối tác trả lỗi chưa thống nhất khi phiên hết hạn
Điều đã biết: Luồng thành công chạy được; một trường hợp lỗi chưa đạt DoD
Lựa chọn:
  A. Bỏ qua tình huống lỗi để demo
  B. Giữ kiểm soát, chờ xác nhận hợp đồng API và hoàn thiện xử lý lỗi
  C. Giảm phạm vi dùng thử nếu điều kiện an toàn và hợp đồng cho phép
Quyết định: Không chọn A; làm rõ B, cân nhắc C theo quyền phê duyệt
Người tham vấn: Chuyên gia bảo mật, kỹ sư đối tác, Product Owner, Developers
Đánh đổi: Hoãn hiệu ứng giao diện phụ và cập nhật dự báo nếu bị chặn
Tiêu chí kiểm chứng: PBI-SSO, các kịch bản lỗi, kiểm thử quyền truy cập, DoD
Theo dõi: Phản hồi đối tác, lỗi thử nghiệm, điều kiện phát hành
Điểm xem lại: Ngay khi có câu trả lời và kiểm thử tích hợp mới
~~~

Đây là ví dụ **ghi quyết định theo rủi ro**, không phải biểu mẫu chính thức của Scrum. Quyết định sản phẩm thuộc trách nhiệm Product Owner; kiểm soát kỹ thuật do Developers thực hiện; ngoại lệ bảo mật hoặc điều khoản đối tác phải được xử lý bởi người có thẩm quyền theo chính sách.

### 10.5. Sprint Review: stakeholder tham gia kiểm tra Increment

Scrum Team trình bày **phần đã đạt DoD**, cho khách hàng thấy tình huống người học truy cập đúng khóa và tình huống từ chối không hợp lệ. Stakeholder có thể phản hồi rằng một số tài khoản của khách hàng có nhiều vai trò, dẫn đến yêu cầu kiểm tra quyền truy cập mới.

Product Owner cùng nhóm xem giá trị và rủi ro của thông tin đó để điều chỉnh Product Backlog. Nhóm không tự biến mọi góp ý cuối Review thành **cam kết chắc chắn cho Sprint kế tiếp** trước khi làm rõ.

### 10.6. Retrospective: cải tiến cách làm việc với chuyên gia

Nhóm nhận thấy câu hỏi cho đối tác thường được gửi quá muộn và thiếu ví dụ. Một cải tiến được đề xuất:

- Với PBI phụ thuộc API bên ngoài, xác định sớm **người liên hệ, hợp đồng API, tình huống lỗi quan trọng và môi trường thử**.
- Gửi câu hỏi có trạng thái tái hiện, ví dụ dữ liệu thử và thời điểm cần phản hồi.
- Công khai tuổi công việc bị chặn; khi cần, Scrum Master hỗ trợ gỡ trở ngại giữa Scrum Team và đơn vị khác.
- Đánh giá thời gian chờ và số lần phải làm lại do hiểu sai ở Sprint kế tiếp.

**Điều học được:** Scrum Team không cần tự làm mọi chuyên môn, nhưng phải **chủ động quản lý luồng thông tin và chịu trách nhiệm với Increment**.

## 11. Quản lý phụ thuộc bên ngoài mà không đánh mất tự quản lý

Phụ thuộc có thể là yêu cầu dữ liệu từ phòng ban khác, một API do đối tác cung cấp, quyết định nghiệp vụ của khách hàng hoặc môi trường triển khai chung.

### 11.1. Bảng phụ thuộc minh bạch

| Phụ thuộc | Tác động nếu chậm | Người phối hợp | Bằng chứng hoàn tất | Cách giảm rủi ro |
|---|---|---|---|---|
| Tài liệu API SSO còn thiếu trường hợp lỗi | Không thể kiểm thử xử lý phiên hết hạn | Kỹ sư tích hợp và đầu mối đối tác | Hợp đồng API hoặc kịch bản đã xác nhận | Thử spike, mock dựa trên hợp đồng được kiểm chứng |
| Quy tắc quyền học tập chưa rõ | Có nguy cơ cho truy cập sai khóa | Product Owner và đại diện khách hàng | Ví dụ nghiệp vụ cùng acceptance criteria | Làm rõ trước khi xây phần phân quyền phức tạp |
| Chính sách log bảo mật | Có thể lộ thông tin nhạy cảm hoặc không điều tra được lỗi | Developers và chuyên gia bảo mật | Chính sách và kiểm thử ghi nhận phù hợp | Thiết kế telemetry tối thiểu, review sớm |
| Môi trường thử chưa sẵn sàng | Tích hợp bị dồn cuối Sprint | Developers và đội vận hành/đối tác | Môi trường dùng được theo kịch bản chính | Kiểm thử hợp đồng sớm, kế hoạch thử thay thế |

Không nên quản lý phụ thuộc bằng cách **mở hàng chục cuộc họp** nhưng không biết ai trả lời câu hỏi nào. Hãy lưu liên kết trong công cụ chung, xác định bước kế tiếp và làm hiển thị blocker.

### 11.2. Khi chuyên gia không có thời gian

Các lựa chọn có thể gồm:

1. **Thu hẹp và làm rõ câu hỏi** để chuyên gia trả lời bất đồng bộ.
2. **Chốt lịch phối hợp ngắn** cho vấn đề rủi ro cao có nhiều cách hiểu.
3. **Thử spike có giới hạn** cho giả định kỹ thuật không cần chờ quyết định ngoài.
4. **Thương lượng phạm vi** với Product Owner nếu điều chưa rõ không trực tiếp cần cho Sprint Goal.
5. **Nâng rủi ro qua kênh phù hợp**, có dữ liệu về tác động và phương án, thay vì đổ lỗi cho người đang bận.

Scrum Master hỗ trợ gỡ trở ngại và nâng cao khả năng phối hợp của Scrum Team; điều đó không đồng nghĩa Scrum Master phải là **người chuyển tiếp mọi câu hỏi** hoặc là người duy nhất được phép liên hệ stakeholder. Developers và Product Owner có thể nói chuyện trực tiếp với người cần thiết trong phạm vi trách nhiệm.

### 11.3. Tránh phụ thuộc “chuyên gia duy nhất”

Nếu mỗi PR hoặc thay đổi nhỏ đều phải chờ một người ngoài duyệt, quy trình dễ tạo điểm tắc và rủi ro kiến thức tập trung. Có thể cải thiện bằng:

- Làm rõ **tiêu chuẩn nào thật sự cần phê duyệt bắt buộc**.
- Đưa các nguyên tắc phổ biến vào checklist, kiểm thử hoặc hướng dẫn dễ dùng.
- Tổ chức chia sẻ kiến thức hoặc cùng làm việc trong những phần rủi ro cao.
- Thiết lập người thay thế hoặc đầu mối phù hợp khi chính sách cho phép.
- Mời chuyên gia tham gia **sớm để phòng lỗi**, thay vì chỉ xem ở cuối khi chi phí sửa cao.

Không loại bỏ review hoặc quyền chấp thuận có tính bắt buộc; mục tiêu là **giảm việc chờ không tạo thêm giá trị**.

## 12. Cộng tác xuyên nhóm, từ xa và khác múi giờ

Nhiều sản phẩm có các Scrum Team hoặc đội hỗ trợ hoạt động tại địa điểm khác nhau. Nhịp trao đổi cần tôn trọng múi giờ, tính bất đồng bộ và sự khác nhau về ngữ cảnh.

### 12.1. Thỏa thuận phối hợp thực dụng

Một thỏa thuận làm việc có thể bao gồm:

- Nơi lưu **mục tiêu, PBI, quyết định và phụ thuộc**, tránh tài liệu rời ở nhiều kênh.
- Kênh dành cho **câu hỏi khẩn** và kênh dành cho việc bình thường.
- Cách mô tả lỗi: hành vi mong đợi/thực tế, bước tái hiện, điều kiện, log đã loại bỏ dữ liệu nhạy cảm.
- Khi nào dùng cuộc gọi ngắn và khi nào chỉ cần nhận xét trên issue.
- Ai thông báo thay đổi hợp đồng API, ai xác nhận người nhận đã hiểu.
- Thời gian phản hồi **được thỏa thuận theo nhu cầu thực**, không mặc định chuyên gia ngoài nhóm luôn trực tuyến.
- Cách xử lý khi người chịu trách nhiệm vắng mặt hoặc một mốc quan trọng có nguy cơ trễ.

Không nên biến thỏa thuận thành KPI “phải trả lời trong năm phút” cho mọi câu hỏi; các SLA/SLO hỗ trợ chỉ nên được thiết lập khi có nhu cầu vận hành hoặc cam kết thực tế.

### 12.2. Quy tắc cuộc họp tập trung

Với những người ngoài Scrum Team có lịch bận:

- Gửi **mục đích, bối cảnh và câu hỏi** trước cuộc họp.
- Chỉ mời người có thông tin hoặc trách nhiệm cần thiết.
- Dùng ví dụ thật/giả lập an toàn, nguyên mẫu hoặc Increment thay cho tranh luận trừu tượng.
- Phân biệt **điều đã thống nhất**, **điều còn bất định** và **quyết định cần người khác**.
- Kết thúc bằng kết luận ngắn và liên kết tới backlog hoặc quyết định liên quan.

### 12.3. Khả năng tiếp cận và sự an toàn khi góp ý

Đừng mặc định mọi người đều có thể tham gia cuộc họp nói liên tục hoặc theo một múi giờ. Cho phép gửi câu hỏi trước, đóng góp bằng văn bản và chia sẻ bản tóm tắt sau giúp nhiều góc nhìn được tiếp nhận hơn.

Đặc biệt trong buổi Review, người dùng hoặc chuyên gia cần có không gian **nêu phản hồi trái chiều**. Nếu mọi góp ý tiêu cực bị coi là làm chậm nhóm, vòng kiểm tra sẽ mất thông tin quan trọng.

## 13. Đo hiệu quả cộng tác bằng kết quả, không bằng số cuộc họp

Nhiều cuộc họp chưa chắc có nghĩa là phối hợp tốt. Nên dùng cả tín hiệu **thời gian, chất lượng, giá trị và độ rõ quyết định**.

| Tín hiệu | Câu hỏi giúp trả lời | Hạn chế cần nhớ |
|---|---|---|
| Thời gian chờ quyết định/chuyên gia | PBI quan trọng có bị chặn lâu vì thiếu thông tin không? | Cần tách thời gian phân tích cần thiết khỏi việc chờ không cần |
| Work item age và WIP | Có nhiều việc mở nhưng không hoàn tất vì phụ thuộc không? | Không kết luận chỉ từ một số trung bình |
| Số lần làm lại do hiểu sai yêu cầu | Các bên có cùng hiểu acceptance criteria trước khi phát triển không? | Phân biệt hiểu sai với thay đổi hợp lý nhờ phản hồi mới |
| Lỗi tích hợp phát hiện muộn | Chuyên gia/đối tác có được tham gia đủ sớm không? | Xem mức độ lỗi, loại việc và thay đổi môi trường |
| Tỷ lệ PBI đạt DoD | Nhóm có giao Increment thực sự hoàn thành không? | Số lượng PBI không tự đo giá trị |
| Phản hồi người dùng và outcome | Increment có giải quyết mục tiêu sản phẩm không? | Cần xem mẫu, phân khúc, thời gian và yếu tố gây nhiễu |
| Khả năng tìm lại quyết định | Người mới có hiểu vì sao chọn phương án và ai chấp thuận không? | Không biến thành yêu cầu ghi hồ sơ quá mức |
| Cảm nhận của các bên về độ rõ | Họ có biết khi nào, vì sao và cách đưa thông tin vào nhóm không? | Kết hợp quan sát hành vi, không chỉ khảo sát hài lòng |

### Thử nghiệm cải tiến minh họa

**Quan sát:** nhiều PBI tích hợp bị chờ chuyên gia tới cuối Sprint.

**Giả thuyết:** nếu nhóm xác định sớm các trường hợp lỗi quan trọng và đặt câu hỏi với đối tác trước khi bắt đầu PBI, thời gian chờ và số lỗi tích hợp phát hiện muộn sẽ giảm.

**Thử nghiệm:** trong hai Sprint, với các PBI có phụ thuộc ngoài nhóm đáng kể, Developers ghi một danh sách câu hỏi/rủi ro ngắn và liên hệ đầu mối thích hợp sớm. Không yêu cầu thủ tục tương tự cho mọi PBI đơn giản.

**Kiểm tra:** xem work item age, thời gian chờ, lỗi phải làm lại, mức công sức trao đổi và khả năng đạt Sprint Goal.

**Quyết định:** giữ, điều chỉnh hoặc dừng cách làm dựa trên quan sát. Thời lượng hai Sprint là ví dụ, không phải quy định chính thức.

## 14. Những sai lầm cộng tác thường gặp

| Sai lầm | Vì sao gây hại | Cách làm phù hợp hơn |
|---|---|---|
| Stakeholder tự thêm task vào Sprint Backlog | Có thể phá Sprint Goal và gây quá tải | Đưa nhu cầu vào trao đổi với Product Owner/Developers, nêu giá trị và đánh đổi |
| Product Owner phải tự trả lời mọi câu hỏi kỹ thuật | Quyết định bị tắc, chuyên môn không được dùng đúng | Developers trao đổi trực tiếp chuyên gia kỹ thuật và giữ PO hiểu tác động lên sản phẩm |
| Scrum Master là thư ký chuyển toàn bộ tin nhắn | Tạo điểm nghẽn và giảm tự quản lý | Scrum Master hỗ trợ cộng tác; các thành viên trao đổi trực tiếp phù hợp |
| Chuyên gia ngoài nhóm quyết định thay toàn bộ thiết kế | Không rõ trách nhiệm tích hợp, giải pháp có thể thiếu bối cảnh | Chuyên gia cung cấp ràng buộc/bằng chứng, Developers chịu trách nhiệm cách thực hiện |
| Coi mọi ý kiến của khách hàng là cam kết phải làm ngay | Backlog mất thứ tự, Sprint Goal bị phân tán | Hỏi vấn đề, giá trị, bằng chứng, hạn thực sự và chi phí cơ hội |
| Chỉ hỏi chuyên gia trước khi release | Phát hiện lỗi muộn, chi phí sửa lớn | Tham vấn sớm ở điểm rủi ro, kiểm thử tích hợp tăng dần |
| Mọi PR đều cần một chuyên gia hiếm thời gian duyệt | Tích tụ chờ và phụ thuộc cá nhân | Phân biệt review thiết yếu với hướng dẫn tự phục vụ; tuân thủ chính sách bắt buộc |
| Sprint Review chỉ trình diễn slide | Stakeholder khó kiểm tra hành vi sản phẩm và góp ý | Dùng Increment thật, câu hỏi về Product Goal và bối cảnh |
| Mời mọi stakeholder vào Daily Scrum | Biến thành báo cáo trạng thái thay vì kế hoạch của Developers | Daily Scrum cho Developers; tổ chức trao đổi riêng khi cần |
| Mời stakeholder vào mọi Retrospective | Có thể làm giảm sự cởi mở, mất trọng tâm cải tiến Scrum Team | Thu thập dữ kiện trước; giữ không gian cho Scrum Team phản tư |
| Tin nhắn riêng là nguồn sự thật duy nhất | Người khác không thấy quyết định và phụ thuộc | Ghi kết luận ở backlog/decision record dùng chung |
| Vì “Agile” nên bỏ phê duyệt bảo mật bắt buộc | Có thể vi phạm ràng buộc và gây rủi ro lớn | Làm rõ quyền quyết định, kết hợp kiểm soát vào DoD/quy trình phù hợp |
| Đếm số buổi họp làm thước đo cộng tác | Khuyến khích nghi thức mà không tăng giá trị | Quan sát thời gian chờ, lỗi, chất lượng quyết định và outcome |

## 15. Checklist cho Scrum Team khi cần người ngoài

Trước khi yêu cầu hỗ trợ:

1. **Mục tiêu:** vấn đề này cản Product Goal hay Sprint Goal như thế nào?
2. **Chuyên môn:** nhóm thiếu kiến thức gì, ai có bằng chứng hoặc thẩm quyền phù hợp?
3. **Phạm vi:** điều nào đang cần làm rõ, điều nào có thể để sau hoặc thử nhỏ?
4. **Định nghĩa câu hỏi:** có ví dụ, dữ kiện, phương án và quyết định cần hỗ trợ chưa?
5. **Rủi ro:** có liên quan bảo mật, dữ liệu, vận hành, hợp đồng hoặc khả năng tiếp cận không?

Trong khi phối hợp:

6. **Vai trò:** ai tư vấn, ai quyết định backlog, ai quyết định cách triển khai và ai phê duyệt điều bắt buộc?
7. **Thông tin:** có chia sẻ vừa đủ, đúng quyền truy cập và không tiết lộ dữ liệu nhạy cảm không?
8. **Tập trung:** trao đổi có đưa nhóm tới hành vi/acceptance criteria hoặc quyết định rõ hơn không?
9. **Phụ thuộc:** ai đang thực hiện bước tiếp theo, khi nào cần xem lại và rủi ro nếu chậm?

Sau khi phối hợp:

10. **Dấu vết:** Product Backlog, tiêu chí chấp nhận hoặc quyết định liên quan đã được cập nhật chưa?
11. **Chất lượng:** kiểm thử và Definition of Done có phản ánh ràng buộc được làm rõ không?
12. **Phản hồi:** khi nào kiểm tra Increment với stakeholder và đo kết quả thực tế?
13. **Cải tiến:** có điểm tắc phối hợp nào cần đưa vào Retrospective không?

Checklist phục vụ **ra quyết định có trách nhiệm**, không phải một biểu mẫu phải ký cho mọi câu hỏi nhỏ.

## 16. Bài tập thực hành

### Bài tập 1 — Phân biệt người trong và ngoài Scrum Team

Một Scrum Team phát triển hệ thống thanh toán gồm Product Owner, Scrum Master, ba lập trình viên, một Tester và một chuyên gia UX làm việc toàn thời gian cùng nhóm. Ngoài nhóm có chuyên gia bảo mật được mời theo vụ việc, đại diện khách hàng và quản lý dự án của đối tác thanh toán.

**Yêu cầu:**

1. Xác định các **accountabilities** trong Scrum Team. Tester và UX có thể nằm trong Developers theo nghĩa trách nhiệm Scrum không?
2. Ai là stakeholder/chuyên gia ngoài Scrum Team trong tình huống?
3. Ai chịu trách nhiệm thứ tự Product Backlog?
4. Ai quyết định giải pháp tích hợp kỹ thuật và bảo đảm DoD?
5. Nếu cần phê duyệt giao dịch theo chính sách, ai cần xác nhận thẩm quyền?

**Gợi ý:** Scrum không định nghĩa các tiểu nhóm QA/UX riêng bên trong Scrum Team. Người có kỹ năng chuyên môn nhưng là thành viên cùng tạo Increment thuộc Developers theo trách nhiệm Scrum.

### Bài tập 2 — Stakeholder yêu cầu thêm việc giữa Sprint

Sprint Goal là **“Người dùng có thể thanh toán bằng thẻ trong một luồng an toàn và đáng tin”**. Giữa Sprint, stakeholder kinh doanh yêu cầu thêm ví điện tử mới; chuyên gia bảo mật phát hiện lỗi xác thực giao dịch nghiêm trọng.

**Yêu cầu:** đề xuất cách Product Owner, Developers, Scrum Master và chuyên gia phối hợp. Nêu:

- Câu hỏi cần hỏi stakeholder kinh doanh.
- Cách ứng phó rủi ro bảo mật.
- Điều kiện xem xét thay đổi Sprint Backlog và phạm vi.
- Việc cần ghi để người khác hiểu quyết định.

**Gợi ý:** lỗi nghiêm trọng có thể phải xử lý theo chính sách ứng cứu; không được giảm DoD để giữ số ticket. Ví điện tử có thể vào Product Backlog để làm rõ giá trị và ưu tiên.

### Bài tập 3 — Chuẩn bị buổi trao đổi với chuyên gia API

Nhóm đang tích hợp API giao hàng, nhưng trạng thái “đã giao” đôi khi xuất hiện trước khi bên vận chuyển xác nhận.

Viết một lời mời hoặc tài liệu chuẩn bị ngắn gồm: **bối cảnh, mục tiêu, dữ kiện đã thấy, điều chưa chắc, ba câu hỏi cụ thể, người tham gia và kết quả mong muốn**.

**Gợi ý:** cần hỏi về ý nghĩa trạng thái, thứ tự sự kiện, khả năng gửi lặp và cách đối soát. Không chỉ hỏi “API có lỗi gì không?”.

### Bài tập 4 — Thiết kế Three Amigos và acceptance criteria

Product Goal là **giảm số đơn hàng bị thanh toán lặp**. Product Owner đề nghị chức năng kiểm tra yêu cầu gửi lại khi người dùng nhấn nút thanh toán nhiều lần.

**Yêu cầu:**

1. Viết user story nêu nhu cầu và lợi ích người dùng.
2. Nêu ba góc nhìn cần có trong cuộc trao đổi nghiệp vụ–phát triển–kiểm thử.
3. Viết ba kịch bản acceptance criteria: thành công, nhấn lặp, lỗi mạng khi chưa biết kết quả giao dịch.
4. Xác định chuyên gia ngoài Scrum Team cần mời khi có ràng buộc của đơn vị thanh toán.
5. Chọn một chỉ số outcome và hai tín hiệu bảo vệ.

**Gợi ý:** không được báo thanh toán thành công nếu chưa có bằng chứng, nhưng cũng phải tránh tạo giao dịch trùng khi thử lại.

### Bài tập 5 — Cải tiến cách làm việc với chuyên gia

Trong ba Sprint gần đây, nhiều PBI bị chặn trung bình vài ngày vì phải chờ review từ cùng một chuyên gia kiến trúc. Một số review là bắt buộc, nhiều trường hợp chỉ là hỏi về quy ước kỹ thuật.

**Yêu cầu:** phân biệt phần bắt buộc với tư vấn, đề xuất một thỏa thuận mới và thiết kế phép thử cải tiến gồm:

~~~text
Vấn đề và bằng chứng:
Giả thuyết:
Thay đổi nhỏ sẽ thử:
Chuyên gia/người có thẩm quyền cần tham gia:
Phạm vi thử:
Tín hiệu: thời gian chờ, work item age, lỗi và làm lại
Tín hiệu bảo vệ: chất lượng, tuân thủ, tải của chuyên gia
Thời điểm xem lại:
Quyết định tiếp theo:
~~~

**Gợi ý:** có thể tạo hướng dẫn tự phục vụ cho trường hợp phổ biến, dành thời gian review cho phần rủi ro cao và thiết lập đầu mối thay thế khi chính sách cho phép.

### Bài tập 6 — Nhận diện cơ hội cộng tác trong sự kiện Scrum

Hãy chọn sự kiện phù hợp cho các tình huống sau:

1. Nhóm muốn cùng khách hàng kiểm tra Increment vừa hoàn thành và điều chỉnh ưu tiên sản phẩm.
2. Developers cần kiểm tra tiến độ Sprint Goal và thống nhất cách phối hợp hôm nay.
3. Scrum Team cần hiểu một yêu cầu nghiệp vụ chưa rõ và muốn mời chuyên gia góp ý trước khi lựa chọn PBI.
4. Scrum Team cần xem vì sao liên tục có blocker với đội vận hành và thử một thay đổi quy trình.
5. Scrum Team cần lời khuyên chuyên gia trước khi lập kế hoạch Sprint.

**Gợi ý:** (1) Sprint Review; (2) Daily Scrum; (3) refinement/trao đổi làm rõ khi cần, không phải sự kiện chính thức bắt buộc; (4) Sprint Retrospective; (5) Sprint Planning có thể mời người ngoài tư vấn.

### Bài tập 7 — Mẫu lập kế hoạch cộng tác cho dự án thật

Chọn một Product Backlog Item có phụ thuộc ngoài nhóm và điền:

~~~text
Product Goal/Sprint Goal liên quan:
Vấn đề người dùng hoặc rủi ro:
PBI/Increment dự kiến:
Người dùng hoặc stakeholder cần kiểm tra:
Chuyên gia còn thiếu và phần kiến thức cần họ:
Ai quyết định backlog / cách thực hiện / ngoại lệ bắt buộc:
Ba câu hỏi cụ thể và bằng chứng hiện có:
Cách và thời điểm liên hệ:
Acceptance criteria hoặc kiểm thử bị ảnh hưởng:
Phụ thuộc, người theo dõi, điểm xem lại:
Thông tin nào cần lưu ở nguồn chung:
Dữ liệu sau phát hành để kiểm chứng giá trị:
~~~

**Tự đánh giá:** nếu người ngoài vắng mặt một tuần, Scrum Team có biết phần nào đang bị chặn, ai cần được liên hệ, quyết định nào chưa có và phần công việc nào vẫn có thể tiến triển một cách an toàn hay không?

## 17. Tổng kết

Scrum Team tự quản lý và chịu trách nhiệm tạo Increment có giá trị, **nhưng không làm việc trong một “ốc đảo” tách khỏi khách hàng, tổ chức và hệ thống kỹ thuật**. Cộng tác với stakeholder và chuyên gia là phần thiết yếu để Agile thích ứng thông qua phản hồi sớm và giao phần mềm tăng dần.

Hãy ghi nhớ:

1. **Rõ trách nhiệm Scrum:** Product Owner tối đa hóa giá trị và quản lý Product Backlog; Developers lập kế hoạch, tạo Increment và giữ DoD; Scrum Master giúp Scrum được hiểu và Scrum Team hiệu quả hơn.
2. **Phân biệt vai trò với chức danh:** chuyên gia có thể ở trong hoặc ngoài Scrum Team; stakeholder không tự trở thành Product Owner hay có quyền đổi Sprint Backlog.
3. **Mời đúng người vào đúng thời điểm:** lấy phản hồi người dùng và chuyên môn cần thiết trước khi rủi ro trở thành lỗi đắt đỏ.
4. **Đưa trao đổi về vấn đề và bằng chứng:** một ví dụ có thể kiểm chứng thường hữu ích hơn nhiều lời nhận xét chung.
5. **Giữ ranh giới quyết định:** Product Owner và Developers làm theo trách nhiệm Scrum; nghĩa vụ bảo mật, hợp đồng và pháp lý vẫn phải tuân thủ đúng thẩm quyền.
6. **Minh bạch phụ thuộc và quyết định:** ghi rõ blocker, người phối hợp, lý do và acceptance criteria tại nguồn dùng chung, không phụ thuộc vào lời nói của một người.
7. **Dùng Scrum events theo mục đích:** Sprint Planning có thể mời lời khuyên; Daily Scrum cho Developers; Sprint Review làm việc với stakeholder; Retrospective tập trung cải tiến Scrum Team.
8. **Khép vòng học hỏi:** xem Increment đạt DoD, phản hồi người dùng, kết quả sản phẩm và mức hiệu quả phối hợp để quyết định bước tiếp theo.

> **Câu hỏi ghi nhớ:** “Chúng ta đã mời đủ góc nhìn cần thiết để ra quyết định tốt hơn, đồng thời vẫn biết rõ ai chịu trách nhiệm về giá trị, cách thực hiện và chất lượng của Increment chưa?”

### Tài liệu tham khảo

- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Scrum Team accountabilities, tự quản lý, Product Backlog, Sprint Goal, Scrum Events, Increment và Definition of Done.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 Principles](https://agilemanifesto.org/principles.html) — cộng tác khách hàng, giao tiếp trực tiếp, giao phần mềm thường xuyên và thích ứng.
- [The Kanban Guide](https://kanbanguides.org/) — minh bạch workflow, Work in Progress, work item age và cycle time để quan sát phụ thuộc và điểm tắc.
- [Agile Alliance — Extreme Programming](https://agilealliance.org/glossary/xp/) — thực hành kỹ thuật và cộng tác giúp tạo phản hồi sớm và đổi hướng an toàn.
