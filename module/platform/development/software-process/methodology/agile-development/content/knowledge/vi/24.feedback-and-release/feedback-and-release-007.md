# Phối hợp hỗ trợ người dùng và vận hành sau bàn giao

## 1. Bàn giao phần mềm không phải là kết thúc việc tạo giá trị

Một nhóm phát triển có thể hoàn thành chức năng đăng ký khóa học, vượt qua kiểm thử tích hợp và mở tính năng cho học viên. Tuy nhiên, câu chuyện chưa dừng lại ở nút **Deploy** hoặc trạng thái **Done** trên bảng công việc:

- Một học viên gửi đăng ký, trình duyệt báo lỗi mạng nhưng hệ thống đã ghi nhận thành công. Người học không biết có nên thử lại.
- Một số lớp học vừa hết chỗ, người dùng tiếp tục gửi yêu cầu và gọi bộ phận hỗ trợ vì thông báo khó hiểu.
- Dịch vụ đăng ký hoạt động nhưng dashboard không hiển thị tỷ lệ lỗi; nhóm vận hành chỉ biết có vấn đề sau khi nhân viên hỗ trợ nhận nhiều cuộc gọi.
- Một phiên bản mới thay đổi cấu trúc dữ liệu; rollback mã không tự khôi phục được những bản ghi đã chuyển.
- Khách hàng đề xuất quy trình đăng ký hộ, trong khi Product Goal hiện tại tập trung vào đăng ký cá nhân.

Nếu Developers cho rằng **“đã bàn giao rồi, phần còn lại là của support”**, nhân viên hỗ trợ có thể thiếu thông tin để giúp người dùng, nhóm vận hành không thể xác định nguyên nhân và Product Owner không nhận được tín hiệu về giá trị thực tế. Phần mềm đã được đưa ra sử dụng nhưng **vòng phản hồi Agile bị đứt đoạn**.

**Phối hợp hỗ trợ người dùng và vận hành sau bàn giao** là việc tổ chức rõ trách nhiệm, luồng thông tin, bằng chứng và cách ứng phó để sản phẩm tiếp tục **đáng tin cậy, hữu ích và có khả năng cải tiến** khi được sử dụng thực tế.

Trong module **AGILE_DEVELOPMENT**, đây là bước nối giữa:

- **Giao sản phẩm tăng dần:** Increment có thể sử dụng và đáp ứng chuẩn chất lượng.
- **Phản hồi sớm:** hiểu hành vi người dùng và những hạn chế mới phát hiện.
- **Backlog thích ứng:** Product Owner cân nhắc sửa lỗi, giảm rủi ro hoặc tạo khả năng mới.
- **Scrum, Kanban và XP:** mục tiêu sản phẩm, quản lý dòng công việc, thực hành kiểm thử/tích hợp và cải tiến liên tục.

> **Thông điệp chính:** Giá trị sản phẩm được kiểm nghiệm khi người dùng thực sự sử dụng. Hỗ trợ và vận hành không phải công đoạn phụ sau phát triển, mà là một phần của hệ thống học hỏi và cung cấp giá trị liên tục.

## 2. Phân biệt Increment, Done, bàn giao, triển khai, phát hành và kết quả

Các từ “xong”, “bàn giao”, “release” và “người dùng đã nhận” dễ bị dùng thay thế nhau. Trong thực tế, chúng có thể là những mốc hoàn toàn khác:

| Khái niệm | Ý nghĩa | Điều chưa được tự động bảo đảm |
| --- | --- | --- |
| **Increment** | Phần sản phẩm tăng thêm đã tích hợp, có thể sử dụng và đáp ứng Definition of Done của Scrum Team khi áp dụng Scrum. | Không đồng nghĩa người dùng đã được mở quyền truy cập. |
| **Definition of Done (DoD)** | Cam kết về trạng thái chất lượng của Increment trong Scrum. | Không tự thay thế toàn bộ quyết định phát hành hoặc nghĩa vụ vận hành. |
| **Deployment** | Đưa phiên bản/cấu hình lên một môi trường đích. | Chưa chắc tính năng đã được kích hoạt hoặc chấp nhận bởi người dùng. |
| **Release** | Đưa phiên bản hoặc khả năng đến một nhóm người sử dụng được xác định theo chính sách. | Không chứng minh người dùng đã nhận được giá trị kỳ vọng. |
| **Bàn giao vận hành** | Chuyển giao hoặc xác nhận trách nhiệm, thông tin và khả năng hỗ trợ/vận hành giữa các bên. | Không làm biến mất trách nhiệm cộng tác của đội phát triển. |
| **Go-live** | Mốc bắt đầu sử dụng trong môi trường thực tế đã định. | Không bảo đảm mọi tình huống thực đã được dự đoán. |
| **Outcome** | Thay đổi thực tế trong kết quả hoặc hành vi của người dùng. | Không thể suy chỉ từ số ticket Done hoặc số lần deploy. |

### 2.1. Ví dụ về các mốc khác nhau

Một chức năng xem lịch sử đăng ký có thể trải qua các mốc:

1. Mã backend/frontend đã merge nhưng còn thiếu kiểm tra phân quyền: **chưa đạt DoD**, không phải Increment hoàn tất.
2. Kiểm thử cần thiết, tích hợp và quyền truy cập đã đạt: có thể được xác nhận **Increment Done**.
3. Phiên bản được triển khai lên production nhưng feature flag còn tắt: **đã deploy**, chưa mở tính năng.
4. Feature flag bật cho 5% học viên đủ điều kiện: **đã release có giới hạn**.
5. Người dùng trải nghiệm và xác nhận có thể tự tra cứu đăng ký: bắt đầu có **bằng chứng sử dụng**.
6. Lượng cuộc gọi hỗ trợ về “đã đăng ký thành công chưa?” giảm: có thể là **tín hiệu outcome**, cần kiểm tra dữ liệu nền và các yếu tố khác.

Điều này không có nghĩa đội cần sáu trạng thái ticket cho mọi việc. Cần phân biệt **bằng ngôn ngữ và phép đo** để người quản lý, vận hành, support và Developers hiểu cùng một tình trạng.

### 2.2. Scrum không yêu cầu chờ Sprint Review mới release

Theo Scrum Guide 2020, một Sprint có thể có nhiều Increment; khi Increment đáp ứng DoD, nó có thể được phát hành trước Sprint Review. **Sprint Review không phải cổng phê duyệt bắt buộc để phát hành**. Tuy nhiên, tổ chức vẫn có thể có những điều kiện phát hành, bảo mật, pháp lý hoặc vận hành phù hợp với sản phẩm.

Nếu một PBI chưa đạt DoD, không nên gọi nó là Done chỉ vì đã qua buổi demo hay đã chuyển cho nhóm vận hành. Phải **minh bạch giới hạn**, tiếp tục xử lý hoặc thay đổi phạm vi tùy chọn theo thẩm quyền thích hợp mà không làm suy giảm chất lượng bắt buộc.

### 2.3. “Bàn giao” không nên biến thành bức tường giữa các nhóm

Một số tổ chức có đội phát triển và đội vận hành riêng; một số khác vận hành theo DevOps hoặc mô hình sản phẩm với trách nhiệm chạy dịch vụ nằm trong nhóm. Cả hai có thể làm việc hiệu quả nếu:

- Trách nhiệm sau phát hành được chỉ định rõ.
- Người ứng cứu tiếp cận được chuyên môn của người xây hệ thống.
- Những thay đổi phát hành có bằng chứng và thông tin liên lạc đủ dùng.
- Support có thể chuyển tình huống không tự xử lý được tới đúng đầu mối.
- Phản hồi sản phẩm quay về backlog và quyết định của Product Owner.

**DevOps là định hướng cộng tác, tự động hóa và chia sẻ trách nhiệm**, không phải yêu cầu mọi đội phải dùng một sơ đồ tổ chức hoặc một chức danh mới. Điều quan trọng là tránh tình trạng **“build xong ném qua tường”**.

## 3. Ai chịu trách nhiệm sau khi tính năng được mở cho người dùng?

### 3.1. Trách nhiệm chung và quyền ra quyết định cụ thể

Hỗ trợ và vận hành là công việc nhiều chuyên môn. “Mọi người cùng chịu trách nhiệm” chỉ hữu ích khi các bên biết **ai tiếp nhận thông tin, ai quyết định, ai hành động và khi nào cần escalation**.

| Bên tham gia | Trách nhiệm đóng góp | Câu hỏi cần xác định rõ |
| --- | --- | --- |
| **Product Owner / người quyết định sản phẩm** | Đánh giá phản hồi, ưu tiên Product Backlog và tối đa hóa giá trị sản phẩm trong Scrum. | Bug/cải tiến nào cần làm trước? Product Goal còn phù hợp? |
| **Developers / nhóm tạo sản phẩm** | Hiểu logic, thiết kế và sửa lỗi; xây kiểm thử, quan sát, khả năng khôi phục; cung cấp thông tin vận hành. | Ai hiểu phiên bản phát hành, API, dữ liệu và cách tái hiện vấn đề? |
| **Hỗ trợ người dùng (service desk/customer support)** | Tiếp nhận, xác minh tác động, hướng dẫn an toàn, thông báo và chuyển tuyến. | Cần hỏi người dùng thông tin gì mà không thu thập dữ liệu nhạy cảm quá mức? |
| **Vận hành/SRE/on-call** | Giám sát dịch vụ, ứng cứu sự cố, điều phối triển khai/rollback, khôi phục và cải thiện độ tin cậy. | Ai được quyền tác động môi trường đang chạy? Khi nào gọi người có chuyên môn? |
| **QA/quality engineering** | Tái hiện lỗi, xác định mức kiểm thử, hỗ trợ hồi quy và chất lượng bản sửa. | Kịch bản nào chưa được bao phủ? Bằng chứng nào cần để đóng lỗi? |
| **Chuyên gia bảo mật/riêng tư** | Đánh giá và xử lý vấn đề liên quan truy cập, dữ liệu, nghĩa vụ an toàn. | Trường hợp nào phải dùng kênh ứng cứu bảo mật và thông báo theo quy định? |
| **Scrum Master nếu dùng Scrum** | Hỗ trợ hiệu quả Scrum Team, phối hợp tháo gỡ trở ngại hệ thống. | Sự cố/phụ thuộc đang làm nhóm mất khả năng tạo giá trị ở đâu? |
| **Chủ sở hữu đối tác/phụ thuộc** | Phối hợp sự cố hoặc thay đổi hợp đồng của dịch vụ liên quan. | Có đầu mối, thời gian phản hồi và bằng chứng giao tiếp không? |
| **Người dùng/khách hàng** | Mô tả vấn đề và giá trị nhận được, xác minh tác vụ sau khi được hỗ trợ. | Trải nghiệm thực có đáp ứng kỳ vọng trong phạm vi đã công bố? |

**Lưu ý:** trong Scrum Guide chỉ có các accountabilities chính thức **Product Owner, Scrum Master và Developers**; bảng mô tả các năng lực vận hành/hỗ trợ, không tự tạo thêm vai trò Scrum bắt buộc. Người thực hiện kiểm thử hoặc vận hành có thể thuộc nhóm Developers tùy cách tổ chức.

### 3.2. Phân biệt service owner, incident commander và Product Owner

Trong một số tổ chức:

- **Service owner** chịu trách nhiệm tổng thể về một dịch vụ ở góc độ vận hành/độ tin cậy.
- **Incident commander/incident coordinator** điều phối một sự cố cụ thể, phân luồng thông tin và các hành động.
- **Product Owner** quyết định thứ tự Product Backlog trong Scrum, hướng tới giá trị sản phẩm.

Đây là những **chức năng khác nhau**, không phải chức danh bắt buộc mọi đội phải có. Một người có thể đảm nhận nhiều chức năng nếu năng lực và thẩm quyền cho phép; khi sự cố lớn, tách người điều phối và người trực tiếp sửa có thể giúp giảm quá tải nhận thức.

### 3.3. Một ma trận quyết định gọn

| Quyết định | Người/nhóm đóng vai trò chính | Ranh giới |
| --- | --- | --- |
| Tiếp nhận phản ánh và xác minh ảnh hưởng người dùng | Support hoặc kênh tiếp nhận được giao | Bảo vệ dữ liệu và không yêu cầu người dùng tự thử thao tác nguy hiểm. |
| Xác nhận mức nghiêm trọng của sự cố | Incident lead/on-call theo quy trình, tham vấn chuyên gia | Dùng tiêu chí mức ảnh hưởng, không tự hạ severity để báo cáo đẹp. |
| Tạm dừng rollout hoặc rollback | Người có quyền vận hành/phát hành, theo quy trình sự cố | Phải xét tác động dữ liệu, side effects và nghĩa vụ thông báo. |
| Chọn giải pháp kỹ thuật để sửa | Developers với người sở hữu chuyên môn và hệ thống | Tuân thủ an ninh, dữ liệu, test, DoD và quyền thay đổi. |
| Sắp thứ tự sửa lỗi và cải tiến sản phẩm | Product Owner trong Scrum | Sự cố đang gây hại vẫn cần ứng cứu ngay theo quy trình, không đợi backlog grooming. |
| Thông báo công khai hoặc cho đối tác | Người được giao trách nhiệm truyền thông | Tránh chia sẻ dữ liệu cá nhân hoặc thông tin chưa xác minh. |
| Kết luận khôi phục dịch vụ | Incident lead/on-call với người có thẩm quyền | Cần bằng chứng dịch vụ trở lại trạng thái chấp nhận được. |
| Hậu kiểm và đưa việc phòng ngừa vào backlog | Người điều phối cải tiến, Developers, PO và bên liên quan | Có owner cho hành động và điều kiện kiểm chứng hiệu quả. |

Một ticket có thể có **một đầu mối theo dõi** nhưng nhiều người cùng thực hiện. Đầu mối không phải người chịu lỗi; họ giúp bảo đảm vấn đề không bị bỏ quên giữa các bộ phận.

## 4. Thiết kế vòng phản hồi sau bàn giao

### 4.1. Từ người dùng tới quyết định sản phẩm

~~~mermaid
flowchart TD
    U["Người dùng / khách hàng"] --> CS["Kênh hỗ trợ và phản hồi"]
    M["Telemetry / cảnh báo / vận hành"] --> T["Tiếp nhận, xác minh và phân loại"]
    CS --> T
    T --> I{"Đang gây hại hoặc có sự cố?"}
    I -- "Có" --> IR["Ứng cứu, bảo vệ người dùng, khôi phục"]
    I -- "Không" --> B["Defect / cải tiến / yêu cầu / câu hỏi"]
    IR --> R["Hậu kiểm và hành động phòng ngừa"]
    B --> PO["Product Owner / backlog có thứ tự"]
    R --> PO
    PO --> DEV["Làm rõ, phát triển, kiểm chứng Increment"]
    DEV --> REL["Bàn giao, triển khai, quan sát"]
    REL --> M
    REL --> U
~~~

Luồng này cho thấy hai đường quan trọng:

1. **Vòng phản ứng nhanh khi dịch vụ đang gây hại:** ưu tiên hạn chế ảnh hưởng và khôi phục theo thẩm quyền.
2. **Vòng học hỏi và ưu tiên sản phẩm:** đánh giá thông tin, làm rõ PBI, triển khai cải tiến và quan sát kết quả.

Không nên bắt người dùng chờ Product Owner sắp lại backlog trước khi nhóm xử lý một sự cố dữ liệu nghiêm trọng. Ngược lại, **một đề nghị tính năng mới** không tự động chen ngang mọi công việc chỉ vì được gửi qua đường hỗ trợ.

### 4.2. Kênh phản hồi khác nhau cho các mục đích khác nhau

| Nguồn | Loại thông tin thường có | Rủi ro diễn giải |
| --- | --- | --- |
| **Ticket hỗ trợ / chat / hotline** | Vấn đề cụ thể người dùng đang gặp. | Người liên hệ nhiều nhất chưa chắc đại diện toàn bộ người dùng. |
| **Theo dõi dịch vụ (logs, metrics, traces)** | Lỗi, độ trễ, tần suất và hành vi hệ thống. | Một chỉ số máy chủ xanh không bảo đảm nghiệp vụ đúng. |
| **Phỏng vấn và quan sát người dùng** | Hiểu nguyên nhân nhầm lẫn, nhu cầu chưa được đáp ứng. | Mẫu nhỏ, cần tránh đặt câu hỏi dẫn dắt. |
| **Phân tích hành trình người dùng** | Tỷ lệ và nơi người dùng bỏ dở thao tác. | Cần định nghĩa sự kiện, bảo vệ riêng tư, xét yếu tố bên ngoài. |
| **Incident và hậu kiểm** | Các điều kiện kỹ thuật/tổ chức gây gián đoạn. | Không suy mọi lỗi có một nguyên nhân hoặc một cá nhân. |
| **Đối tác tích hợp** | Lỗi hợp đồng API, thời gian chờ, thay đổi ngoài hệ thống. | Dữ liệu và mức cam kết có thể khác giữa các bên. |
| **Đề xuất từ nhân viên hỗ trợ** | Các lỗi lặp, câu hỏi thường gặp, chi phí xử lý thủ công. | Chưa chắc việc nào cũng cần tính năng mới; có thể sửa thông báo/tài liệu. |

Nhóm nên kết hợp **bằng chứng định lượng và định tính**. Một lỗi hiếm nhưng có thể lộ dữ liệu cá nhân không thể bị bỏ qua chỉ vì ít ticket; một tính năng ít người phản hồi cũng chưa đủ để kết luận không có giá trị.

### 4.3. Đóng vòng phản hồi

Một vòng phản hồi chưa hoàn thành khi support chỉ tạo ticket rồi chờ. Nó cần có:

- **Biên nhận:** người dùng biết vấn đề đã được tiếp nhận và có mã tham chiếu nếu phù hợp.
- **Trạng thái:** đang xác minh, cần thêm thông tin, đã khôi phục, đang phân tích lâu dài hoặc không nằm trong phạm vi hỗ trợ.
- **Thông báo có căn cứ:** không hứa thời gian/giải pháp chưa được xác nhận.
- **Kết quả kiểm chứng:** người dùng hoặc tín hiệu hệ thống cho biết tình huống có được giải quyết chưa.
- **Tri thức lưu lại:** một lỗi lặp không buộc người dùng và nhân viên hỗ trợ bắt đầu từ số không.
- **Phản hồi về quyết định:** với đề nghị cải tiến, biết rằng ý tưởng đã được ghi nhận, xem xét hoặc chưa được ưu tiên, không coi mọi yêu cầu là cam kết.

Khả năng **đóng vòng** vừa giúp người dùng tin cậy dịch vụ, vừa giảm mất thông tin khi chuyển tuyến.

## 5. Chuẩn bị hỗ trợ và vận hành trước khi phát hành

### 5.1. Release readiness là năng lực vận hành, không chỉ danh sách tài liệu

Một Increment đạt DoD cần được phát hành theo quy định phù hợp, nhưng nhóm vận hành cũng phải có khả năng **phát hiện, giải thích và xử lý** những điều xảy ra sau đó. Trước rollout, những bên liên quan có thể cùng xác nhận:

1. **Phạm vi:** thay đổi nào được phát hành, đối tượng nào được truy cập, điều gì ngoài phạm vi?
2. **Người chịu trách nhiệm:** ai theo dõi rollout, ai xử lý kỹ thuật, ai liên hệ người dùng?
3. **Điều kiện kiểm chứng:** smoke test, health checks, kiểm tra dữ liệu, quyền và khả năng sử dụng cần đạt.
4. **Observability:** theo dõi tín hiệu nào, ngưỡng cảnh báo và người nhận cảnh báo?
5. **Ứng cứu và khôi phục:** có cách tạm dừng, giảm phạm vi, rollback hoặc sửa dữ liệu an toàn không?
6. **Thông tin hỗ trợ:** hướng dẫn thao tác, lỗi thường gặp, câu hỏi xác minh, kênh escalation.
7. **Dữ liệu và quyền:** migration, backup, chính sách truy cập, thông tin nhạy cảm và quy định áp dụng.
8. **Phụ thuộc:** đối tác, API, môi trường, thời điểm bảo trì hoặc nhóm khác cần được biết.
9. **Bằng chứng:** những kiểm tra bắt buộc đã thực sự chạy và đạt.
10. **Phương án theo dõi sau phát hành:** ai đánh giá tín hiệu, khi nào quyết định mở rộng hoặc dừng rollout?

Không phải mọi thay đổi văn bản nhỏ đều cần họp phê duyệt đầy đủ. **Mức chuẩn bị cần tương xứng với rủi ro và hậu quả khi thất bại**; các kiểm soát bắt buộc vẫn phải tuân thủ.

### 5.2. Một bản bàn giao tối thiểu có thể tra cứu

| Thành phần | Nội dung nên có | Vì sao cần |
| --- | --- | --- |
| **Release note** | Khả năng thay đổi, phạm vi, hạn chế, tác động người dùng. | Support biết giải thích đúng. |
| **Runbook** | Cách quan sát, xác minh, ứng cứu và escalation trong phạm vi cho phép. | Người trực hỗ trợ không phải đoán trong sự cố. |
| **Sơ đồ phụ thuộc** | API, DB, queue, nhà cung cấp hoặc dịch vụ quan trọng. | Khoanh vùng nguyên nhân và tác động. |
| **Dashboard/alert** | Đường dẫn/kênh tới tín hiệu đã được phân quyền phù hợp. | Phát hiện bất thường sớm. |
| **Kịch bản smoke test** | Thao tác kiểm chứng quan trọng sau triển khai. | Phân biệt deploy thành công với luồng dùng được. |
| **Kế hoạch khôi phục** | Điều kiện stop/rollback, người có quyền, giới hạn dữ liệu. | Giảm tác động khi rollout không như kỳ vọng. |
| **Thông tin support** | Cách xác minh, vấn đề đã biết, workaround an toàn, đầu mối. | Giải quyết vấn đề thông thường nhanh. |
| **Phiên bản và bằng chứng test** | Build ID, commit/version, kết quả kiểm chứng liên quan. | Truy vết thay đổi và tái hiện vấn đề. |

Tài liệu **ngắn, đúng và dễ tìm** thường có giá trị hơn một bộ hồ sơ rất dài nhưng không được cập nhật. Với hệ thống rủi ro cao, mức truy vết và phê duyệt có thể cần sâu hơn.

### 5.3. Không bàn giao những thứ chưa có khả năng sử dụng thật

Nếu endpoint đăng ký chỉ chạy trên máy một developer, chưa tích hợp dữ liệu thật hoặc chưa kiểm tra phân quyền thì việc tạo release note không biến nó thành chức năng sẵn sàng. Nhóm cần minh bạch rằng phần nào là **prototype/spike**, phần nào là **Increment đạt chuẩn** và phần nào thực sự được bật cho người dùng.

Nếu có hạn chế đã được chấp nhận trong một bản phát hành, phải mô tả **phạm vi sử dụng an toàn**, mức rủi ro, người có thẩm quyền và cơ chế theo dõi; không thể “chấp nhận rủi ro” bằng cách lặng lẽ bỏ qua nghĩa vụ bảo mật hoặc pháp lý.

## 6. Runbook: biến kiến thức phát triển thành khả năng hỗ trợ

### 6.1. Runbook khác tài liệu kiến trúc và FAQ

- **FAQ/hướng dẫn người dùng** giải thích thao tác hoặc vấn đề thông thường theo ngôn ngữ người dùng.
- **Runbook** hướng dẫn người hỗ trợ/vận hành quan sát và ứng phó với tình huống có quy trình rõ.
- **Tài liệu kiến trúc** mô tả cấu trúc, hợp đồng và những quyết định kỹ thuật quan trọng.
- **Hậu kiểm sự cố** ghi điều đã xảy ra và cải tiến về sau.

Một runbook không nên là một chuỗi lệnh nguy hiểm để bất kỳ ai cũng thực thi. Nó cần nêu **điều kiện, quyền thực hiện, cách kiểm tra tác động và khi nào phải dừng để gọi chuyên gia**.

### 6.2. Mẫu runbook ngắn cho đăng ký khóa học

~~~text
Tên: Luồng đăng ký khóa miễn phí — tỷ lệ thất bại tăng

Mục đích:
  Kiểm tra nhanh xem học viên có thể đăng ký hay không,
  hạn chế tác động và chuyển tuyến đúng người.

Phạm vi:
  API đăng ký khóa miễn phí, giao diện web, DB đăng ký,
  dịch vụ danh mục khóa học.

Dấu hiệu kích hoạt:
  Cảnh báo tỷ lệ lỗi vượt ngưỡng đã được cấu hình,
  phát hiện dữ liệu sai, hoặc phản ánh lặp có bằng chứng.

Kiểm tra an toàn:
  1. Xác định thời điểm, phạm vi người dùng và phiên bản đang chạy.
  2. Xem dashboard API, độ trễ và trạng thái phụ thuộc.
  3. Kiểm tra log có correlation ID phù hợp, không yêu cầu
     người dùng gửi mật khẩu hoặc dữ liệu cá nhân thừa.
  4. Dùng tài khoản/dữ liệu test được phép cho smoke test.
  5. Phân biệt từ chối hợp lệ do hết chỗ với lỗi 5xx hoặc dữ liệu sai.

Không thực hiện:
  - Không sửa trực tiếp bản ghi học viên nếu không có quyền và quy trình.
  - Không vô hiệu hóa kiểm tra phân quyền hay ràng buộc sức chứa.
  - Không liên tục yêu cầu người dùng thử lại nếu có nguy cơ ghi trùng.

Escalation:
  - Sự cố dữ liệu/riêng tư: kênh ứng cứu có thẩm quyền.
  - Lỗi API/DB: người trực kỹ thuật và chủ sở hữu dịch vụ.
  - Phụ thuộc danh mục: đầu mối tích hợp được chỉ định.

Khôi phục:
  Thực hiện theo runbook triển khai/rollback riêng;
  yêu cầu xác minh dữ liệu trước khi đóng sự cố.

Điều kiện kết thúc:
  Tín hiệu dịch vụ và kịch bản người dùng chính trở lại mức chấp nhận;
  phạm vi bị ảnh hưởng được xác định và thông báo theo chính sách.
~~~

Đây là **mẫu minh họa**, không phải runbook production đã được kiểm chứng. Runbook thật phải liên kết tới các dashboard, quyền và công cụ đúng của hệ thống, được thử trong môi trường phù hợp và giữ cập nhật.

### 6.3. Runbook tốt giúp người mới hỗ trợ đúng giới hạn

Một runbook nên trả lời:

- **Tình huống nào áp dụng?** Dấu hiệu phải quan sát được.
- **Người thực hiện cần quyền gì?** Nếu thiếu quyền, ai có thể giúp?
- **Bước đầu nào an toàn?** Ưu tiên kiểm tra chỉ đọc, không tác động dữ liệu.
- **Khi nào phải dừng?** Ví dụ nghi lộ dữ liệu, mất tính nhất quán hoặc thay đổi vượt quyền.
- **Chứng cứ nào cần giữ?** Thời gian, version, correlation ID, tác động, kết quả test.
- **Thế nào là khôi phục?** Không chỉ trang trạng thái xanh mà cả hành vi nghiệp vụ cần thiết.
- **Khi nào cập nhật tài liệu?** Sau release lớn, sự cố hoặc phát hiện mới.

Nếu một runbook thường xuyên thất bại vì lỗi thời, nó chính là một **vấn đề chất lượng vận hành**. Nhóm cần có người sở hữu và kiểm chứng định kỳ thay vì đổ lỗi cho người trực.

## 7. Quan sát chất lượng dịch vụ sau bàn giao

### 7.1. Cần nhìn cả kỹ thuật lẫn hành vi người dùng

Một API trả HTTP 200 chưa chắc đăng ký được ghi đúng; một hệ thống không có lỗi 5xx vẫn có thể xác nhận vượt sức chứa. Chất lượng vận hành cần quan sát:

| Nhóm tín hiệu | Ví dụ | Cách dùng cẩn trọng |
| --- | --- | --- |
| **Kỹ thuật** | Tỷ lệ lỗi server, độ trễ, bão hòa tài nguyên, độ ổn định DB, hàng đợi. | Không kết luận nghiệp vụ đúng chỉ từ CPU hoặc HTTP status. |
| **Nghiệp vụ** | Yêu cầu đăng ký thành công, từ chối hợp lệ, dữ liệu trùng, vượt sức chứa. | Định nghĩa “thành công” phải phù hợp trạng thái dữ liệu cuối. |
| **Trải nghiệm** | Học viên hoàn tất hành trình, hiểu xác nhận, số lần retry. | Cần phân biệt lỗi ứng dụng với người dùng tự hủy thao tác. |
| **Hỗ trợ** | Số ticket cùng chủ đề, thời gian chờ, trường hợp phải chuyển tuyến. | Ticket nhiều có thể do nhu cầu tăng hoặc kênh báo lỗi dễ dùng hơn. |
| **An toàn/riêng tư** | Sự kiện truy cập trái quyền, dấu hiệu lộ dữ liệu, hành vi bất thường. | Tuân thủ chính sách bảo mật và giới hạn người được xem dữ liệu. |
| **Phát hành** | Thời điểm deploy, version, feature flag, tỷ lệ rollout. | Phải gắn lỗi với phạm vi người dùng và thay đổi thực tế. |

### 7.2. SLI, SLO và SLA

- **Service Level Indicator (SLI)** là cách đo một đặc tính dịch vụ, chẳng hạn tỷ lệ yêu cầu đăng ký hợp lệ có kết quả đúng trong thời gian được định nghĩa.
- **Service Level Objective (SLO)** là mục tiêu cho SLI trong một cửa sổ thời gian được thống nhất.
- **Service Level Agreement (SLA)** là thỏa thuận với nghĩa vụ hoặc hệ quả tương ứng; không phải mọi SLO nội bộ đều là SLA.

Ví dụ minh họa: trong một cửa sổ quan sát, có **985** trong **1.000** lần đăng ký hợp lệ đạt định nghĩa thành công đã thống nhất:

\[
\text{Tỷ lệ thành công}=\frac{985}{1000}\times100\%=98{,}5\%.
\]

Con số này không cho biết mức **98,5%** có được chấp nhận hay không nếu chưa có SLO, mẫu đo, đối tượng, mức lỗi dữ liệu và rủi ro. Một lỗi lộ thông tin cá nhân hiếm gặp vẫn có thể nghiêm trọng hơn nhiều lỗi giao diện thông thường.

### 7.3. Error budget và đánh đổi thay đổi

Một số đội SRE dùng **error budget** để thảo luận mức sai lệch cho phép so với một SLO trong một cửa sổ đo.

Ví dụ **thuần minh họa**: nếu SLO là **99,9%** số yêu cầu hợp lệ trong một tháng được xử lý đúng, phần chưa đạt mục tiêu tương ứng là **0,1%** theo chính định nghĩa SLI ấy. Với **100.000** yêu cầu thuộc tập tính toán:

\[
100.000\times(1-0{,}999)=100\ \text{yêu cầu}.
\]

Đó **không phải giấy phép cố ý làm sai 100 đăng ký** hoặc bỏ quy định về dữ liệu/riêng tư. Error budget chỉ hữu ích khi SLI/SLO được định nghĩa cẩn thận, có chính sách sử dụng và không che giấu hậu quả mất dữ liệu hoặc vi phạm an toàn.

### 7.4. Log, metric, trace phải phục vụ điều tra mà vẫn bảo vệ người dùng

Một log hữu ích có thể chứa:

~~~json
{
  "timestamp": "2026-11-01T08:12:30Z",
  "service": "course-enrollment",
  "environment": "production",
  "releaseVersion": "example-v2",
  "correlationId": "example-request-42",
  "event": "enrollment_attempt_failed",
  "category": "dependency_timeout",
  "durationMs": 850
}
~~~

Đây là **dữ liệu giả để minh họa**, không phải bản ghi người dùng thật. Log không nên chứa mật khẩu, token, chi tiết thanh toán hoặc thông tin cá nhân vượt mục đích. Cần phân quyền truy cập, giới hạn thời gian lưu, và quản lý correlation ID/định danh sao cho hỗ trợ điều tra mà không tạo rủi ro mới.

### 7.5. Alert phải dẫn đến hành động rõ

Một cảnh báo tốt nên trả lời:

1. Điều kiện nào bị vi phạm và mức độ ảnh hưởng là gì?
2. Người trực có thể kiểm tra/tác động an toàn những gì?
3. Runbook và đầu mối escalation ở đâu?
4. Mức khẩn cấp và cách thông báo ra sao?
5. Khi nào cảnh báo được xem là đã khôi phục?

Nếu mọi sự kiện nhỏ đều gọi người trực, **alert fatigue** khiến tín hiệu nghiêm trọng dễ bị bỏ sót. Nhóm nên đánh giá khả năng hành động và hậu quả thực tế của cảnh báo, không chỉ tăng số lượng dashboard.

## 8. Tiếp nhận và phân loại yêu cầu hỗ trợ một cách nhất quán

### 8.1. Đường tiếp nhận nên đơn giản cho người dùng

Người dùng không cần biết nội bộ có bao nhiêu nhóm hay phân biệt bug/incident/change trước khi được giúp. Họ cần kênh rõ để gửi vấn đề, biết điều gì được yêu cầu và khi nào có thông tin tiếp theo.

Trong nội bộ, nhóm có thể phân loại:

| Nhóm tình huống | Ví dụ | Phương án điều phối |
| --- | --- | --- |
| **Câu hỏi/hướng dẫn** | “Làm sao xem khóa đã đăng ký?” | Hướng dẫn an toàn, cập nhật FAQ nếu câu hỏi lặp. |
| **Service request** | Yêu cầu hỗ trợ thao tác nằm trong chính sách. | Theo quy trình hỗ trợ và quyền được giao. |
| **Defect** | Trạng thái đã ghi nhận khác hành vi kỳ vọng. | Tái hiện, đánh giá rủi ro, lập kế hoạch sửa và test. |
| **Incident** | Dịch vụ đang bị gián đoạn hoặc có dấu hiệu gây tác động cần ứng cứu. | Kích hoạt quy trình sự cố theo mức độ. |
| **Security/privacy concern** | Có thể đọc hồ sơ của người khác. | Chuyển kênh bảo mật phù hợp, hạn chế việc phổ biến chi tiết. |
| **Product feedback/feature request** | “Muốn có danh sách chờ cho lớp đầy.” | Làm rõ giá trị, đưa vào quá trình quyết định Product Backlog. |
| **Problem / nguyên nhân lặp** | Nhiều incident cùng liên quan retry của API. | Phân tích nguyên nhân hệ thống và đối sách lâu dài. |

Các tên gọi tham khảo những cách làm quản lý dịch vụ phổ biến, **không phải nhãn bắt buộc của Scrum hay Kanban**. Một sự kiện có thể vừa là incident đang cần ứng cứu, vừa tạo defect và hành động phòng ngừa sau đó.

### 8.2. Mẫu ticket hỗ trợ đủ thông tin nhưng không xâm phạm riêng tư

~~~text
Mã yêu cầu: SUP-EXAMPLE-017
Kênh nhận: Hệ thống hỗ trợ
Tác vụ: Học viên tự đăng ký khóa miễn phí
Thời gian (kèm múi giờ): 2026-11-01 15:12 +07:00
Triệu chứng: Sau khi xác nhận, trình duyệt báo lỗi mạng,
             người học không rõ đã đăng ký thành công chưa
Phạm vi: Một phản ánh đã xác minh; chưa biết có nhiều người bị ảnh hưởng
Môi trường/phiên bản: Theo metadata hệ thống
Correlation ID: example-request-42
Tác động: Có nguy cơ người học gửi lại và gây nhầm lẫn
Đã kiểm tra: Hướng dẫn tra trạng thái an toàn; chưa kết luận dữ liệu
Mức độ ban đầu: Cần triage theo chính sách
Đầu mối tiếp theo: Nhóm đăng ký / on-call theo lịch
Thời điểm cập nhật tiếp: Theo thỏa thuận kênh hỗ trợ
~~~

Đây là dữ liệu giả. Trong hệ thống thật **không yêu cầu người dùng gửi mật khẩu, mã OTP, token, thông tin thẻ hoặc toàn bộ hồ sơ** qua ticket thông thường. Dùng mã tham chiếu, quyền tra cứu và cơ chế xác minh danh tính được thiết kế phù hợp.

### 8.3. Ba câu hỏi trước khi chuyển tuyến

1. **Người dùng đang muốn hoàn tất việc gì?** Không chỉ “nút bị lỗi”.
2. **Có nguy cơ gây thêm hại khi họ thử lại không?** Ví dụ đăng ký trùng hoặc thanh toán lặp.
3. **Đã có bằng chứng gì và còn điều nào chưa biết?** Thời gian, thông báo, trạng thái chính xác, dữ liệu và phạm vi ảnh hưởng.

Nếu có dấu hiệu sự cố an toàn hoặc dữ liệu, support cần **nâng cấp sớm**, không tiếp tục yêu cầu người dùng lặp thao tác cho đến khi biết an toàn.

## 9. Triage và escalation: chuyển đúng vấn đề tới đúng người

### 9.1. Severity khác priority

- **Severity:** mức hậu quả đang xảy ra hoặc có khả năng xảy ra cho người dùng/dịch vụ.
- **Urgency:** mức cấp bách theo thời gian; trì hoãn có thể làm ảnh hưởng lan rộng hay bỏ lỡ thời điểm quan trọng.
- **Priority:** thứ tự hành động so với công việc khác, xét hậu quả, độ khẩn, phụ thuộc và giá trị.

Một lỗi giao diện nhỏ được báo trước buổi demo có thể cấp bách với việc trình diễn, nhưng không tự tương đương lỗi lộ dữ liệu. Một trường hợp ảnh hưởng ít người vẫn có severity cao nếu hậu quả an toàn nghiêm trọng.

### 9.2. Ma trận mức độ minh họa, không phải chuẩn phổ quát

| Mức minh họa | Tín hiệu gợi ý | Phản ứng |
| --- | --- | --- |
| **Nghiêm trọng** | Rò rỉ dữ liệu, mất toàn vẹn dữ liệu, dịch vụ cốt lõi ngừng hoạt động diện rộng hoặc có nguy cơ gây hại đáng kể. | Kích hoạt ngay quy trình ứng cứu tương ứng; có điều phối, hạn chế tác động và truyền thông theo thẩm quyền. |
| **Cao** | Chức năng quan trọng không dùng được đối với nhóm người dùng đáng kể, workaround khó hoặc nhiều giao dịch không chắc trạng thái. | Chuyển tuyến kỹ thuật sớm, giám sát ảnh hưởng, quyết định giảm tác động. |
| **Trung bình** | Một chức năng phụ bị lỗi nhưng có workaround an toàn, phạm vi hạn chế. | Ghi nhận và xử lý theo chính sách hỗ trợ/ưu tiên, cập nhật người dùng. |
| **Thấp** | Vấn đề hiển thị nhỏ hoặc câu hỏi sử dụng ít tác động. | Hỗ trợ/ghi nhận để cải tiến; không mặc định gọi incident. |

Không có mốc số phút khôi phục, mức P1/P2 hoặc cam kết SLA **mặc định** từ bảng này. Tổ chức phải định nghĩa mức độ, quyền kích hoạt, nhịp cập nhật và thời gian đáp ứng dựa trên dịch vụ, hợp đồng, chính sách và nghĩa vụ thực.

### 9.3. Escalation chức năng và escalation thẩm quyền

**Escalation chức năng:** chuyển cho người/nhóm có chuyên môn cần thiết, chẳng hạn DB, API, IAM, nhà cung cấp.

**Escalation thẩm quyền:** xin quyết định vượt quyền xử lý, chẳng hạn cho phép dừng release, thay đổi cấu hình production, thông báo sự cố bảo mật hoặc tạm ngưng dịch vụ.

Hai đường này có thể xảy ra đồng thời. Không nên liên tục chuyển ticket theo cấp quản lý khi vấn đề cần chuyên gia kỹ thuật; cũng không được tự vượt quyền bảo mật chỉ vì biết cách thay đổi hệ thống.

### 9.4. Chuyển tuyến không được làm mất ngữ cảnh

Một bản handoff hỗ trợ nên chứa:

- Tóm tắt **tình trạng và tác động**, phân biệt sự kiện đã xác minh với giả thuyết.
- Khoảng thời gian và phiên bản/môi trường liên quan.
- Các bước tái hiện an toàn hoặc correlation ID.
- Những hành động đã thử và kết quả, tránh làm lặp thao tác nguy hiểm.
- Người đầu mối và thời điểm cập nhật tiếp theo.
- Các rủi ro về dữ liệu, quyền và người dùng đang bị ảnh hưởng.

“Đã chuyển cho backend” mà không có bằng chứng và người theo dõi chỉ tạo thêm hàng đợi. Mục tiêu là **chuyển thông tin cần thiết để giải quyết**, không chỉ chuyển quyền sở hữu ticket.

## 10. Ứng cứu sự cố khi phần mềm đang gây tác động

### 10.1. Ưu tiên hạn chế ảnh hưởng, không phải tìm người viết lỗi

Khi dịch vụ đang gây hại, mục tiêu đầu tiên là **bảo vệ người dùng và khôi phục trạng thái chấp nhận được**. Phân tích nguyên nhân sâu có thể diễn ra song song nếu đủ năng lực, nhưng không được để việc tranh luận ai chịu lỗi trì hoãn biện pháp an toàn.

Một vòng ứng cứu tham khảo:

~~~mermaid
flowchart TD
    A["Alert / phản ánh có bằng chứng"] --> B["Đánh giá tác động và mức nghiêm trọng"]
    B --> C{"Có incident cần ứng cứu?"}
    C -- "Không" --> D["Theo luồng hỗ trợ / backlog"]
    C -- "Có" --> E["Kích hoạt điều phối, người trực, kênh liên lạc"]
    E --> F["Hạn chế ảnh hưởng: tạm dừng, giảm phạm vi, khôi phục an toàn"]
    F --> G["Kiểm tra hành vi nghiệp vụ, dữ liệu và tín hiệu dịch vụ"]
    G --> H{"Đã ổn định?"}
    H -- "Chưa" --> F
    H -- "Có" --> I["Cập nhật người dùng, kết thúc ứng cứu theo chính sách"]
    I --> J["Hậu kiểm: nguyên nhân, phòng ngừa, backlog"]
    J --> K["Kiểm chứng cải tiến trong các vòng sau"]
~~~

Sơ đồ là định hướng chung. Khi sự cố liên quan dữ liệu cá nhân, tài chính hoặc hệ thống an toàn tính mạng, phải tuân thủ **quy trình ứng cứu chuyên biệt và thẩm quyền pháp lý/kỹ thuật áp dụng**.

### 10.2. Những vai trò có thể tách ra trong sự cố lớn

| Chức năng | Trách nhiệm trong lúc ứng cứu |
| --- | --- |
| **Điều phối sự cố** | Giữ tổng quan trạng thái, mức ảnh hưởng, người tham gia, quyết định và nhịp cập nhật. |
| **Người xử lý kỹ thuật** | Kiểm chứng nguyên nhân, giảm tác động và triển khai giải pháp theo quyền được giao. |
| **Người truyền thông** | Thông báo có căn cứ tới support, stakeholder và người dùng/đối tác cần biết. |
| **Người ghi nhận sự kiện** | Timeline, thay đổi, dấu vết cần bảo toàn và việc còn mở. |
| **Người phụ trách dữ liệu/bảo mật khi cần** | Đánh giá rủi ro, nghĩa vụ thông báo, bảo toàn bằng chứng và giảm thiểu tác hại. |

Ở sự cố nhỏ, một số chức năng có thể do cùng một người đảm nhận; ở sự cố nghiêm trọng, việc tách giúp tránh người đang sửa hệ thống phải đồng thời trả lời tất cả cuộc gọi. **Không biến ma trận trên thành bộ role Agile chính thức.**

### 10.3. Quy trình giao tiếp trong sự cố

Một bản cập nhật tốt trả lời:

1. **Điều gì đã được xác nhận?** Tránh khẳng định nguyên nhân khi chỉ có giả thuyết.
2. **Ai/khả năng nào bị ảnh hưởng?** Nêu phạm vi có bằng chứng.
3. **Đang làm gì để hạn chế tác động?** Không công bố chi tiết nhạy cảm.
4. **Người dùng nên làm gì?** Đưa hướng dẫn an toàn, tránh yêu cầu retry có thể ghi trùng.
5. **Khi nào cập nhật tiếp?** Chỉ cam kết thời điểm hoặc nhịp đã được đội điều phối thống nhất.

Không nên hứa “sẽ sửa hoàn toàn trước 15:00” khi chưa có căn cứ. Tốt hơn là nêu sự thật, công việc đang tiến hành và mốc **cập nhật thông tin** có thể giữ được.

### 10.4. Workaround, khôi phục tạm và sửa nguyên nhân

Ba việc khác nhau:

- **Workaround:** cách giúp người dùng tiếp tục công việc trong phạm vi an toàn, không nhất thiết sửa nguyên nhân.
- **Mitigation/khôi phục tạm:** giảm hoặc ngăn tác động đang xảy ra, như tắt tính năng gây lỗi nếu có cơ chế hợp lệ.
- **Permanent fix:** xử lý nguyên nhân đã được kiểm chứng và ngăn vấn đề lặp lại.

Ví dụ, tạm dừng tạo đăng ký mới để tránh vượt sức chứa có thể là một **biện pháp bảo vệ dữ liệu**, nhưng cũng khiến người dùng không đăng ký được. Người có thẩm quyền phải cân nhắc và truyền thông tác động. Sau khi khôi phục, nhóm vẫn cần sửa, kiểm thử, đánh giá dữ liệu bị ảnh hưởng và giải quyết những trường hợp người dùng cần hỗ trợ.

### 10.5. Không kết thúc sự cố chỉ vì dashboard chuyển xanh

Điều kiện khôi phục có thể bao gồm:

- Tín hiệu lỗi/độ trễ về mức được chấp nhận.
- Hành vi nghiệp vụ quan trọng hoạt động trên bản thực theo cách kiểm tra an toàn.
- Dữ liệu đã ghi trong sự cố được đánh giá và có kế hoạch xử lý sai lệch.
- Người dùng bị ảnh hưởng được hướng dẫn phù hợp.
- Những thành phần phụ thuộc ổn định và không có dấu hiệu tái phát.
- Các hành động theo dõi còn lại có người chịu trách nhiệm.

**Service restoration** và **problem resolution** có thể tách thời điểm. Nhóm có thể kết thúc giai đoạn ứng cứu khi dịch vụ đã ổn định theo chính sách, trong khi defect và hành động phòng ngừa tiếp tục được quản lý minh bạch.

## 11. Hậu kiểm sự cố: học từ hệ thống thay vì tìm một người để đổ lỗi

### 11.1. Vì sao cần post-incident review?

Sau khi dịch vụ đã ổn định, câu hỏi không chỉ là **“ai đã sửa lỗi?”** mà còn:

- Điều kiện nào khiến lỗi có thể xảy ra?
- Vì sao chúng ta không phát hiện được từ thiết kế, kiểm thử hoặc CI?
- Những tín hiệu nào đã có nhưng chưa ai thấy, hoặc đã thấy nhưng không thể hành động?
- Vì sao quá trình ứng cứu mất nhiều thời gian?
- Khâu nào khiến support hoặc người dùng không biết trạng thái thật?
- Đối sách nào ngăn lỗi tái diễn, và làm sao biết đối sách có tác dụng?

**Blameless postmortem/hậu kiểm không đổ lỗi** giúp nhóm nhìn vào hệ thống, công cụ, giao tiếp, áp lực công việc và điều kiện thực tế. Nó **không xóa accountability**: vẫn phải có người chịu trách nhiệm hành động, quyết định đúng thẩm quyền, khôi phục dữ liệu khi cần và thông báo theo nghĩa vụ.

### 11.2. Kết cấu một buổi hậu kiểm thực dụng

| Nội dung | Câu hỏi |
| --- | --- |
| **Tác động** | Ai bị ảnh hưởng, trong bao lâu, dữ liệu nào cần kiểm tra? |
| **Timeline** | Tín hiệu bắt đầu khi nào, ai phát hiện, lúc nào phản ứng/khôi phục? |
| **Hiện tượng quan sát** | Những log, metric, test hoặc phản hồi nào đáng tin? |
| **Các yếu tố góp phần** | Code, API, dữ liệu, CI, runbook, chính sách, phụ thuộc, giao tiếp? |
| **Điều đã làm tốt** | Cảnh báo nào hữu ích, biện pháp nào nhanh và an toàn? |
| **Điều có thể cải thiện** | Tại sao phản hồi/khôi phục chậm hoặc thông tin chưa đầy đủ? |
| **Hành động** | Làm gì, ai chịu trách nhiệm, cần quyền/phụ thuộc nào và kiểm chứng thế nào? |
| **Theo dõi** | Khi nào xem kết quả, điều kiện để đóng hành động phòng ngừa? |

Với sự cố nhỏ, ghi vài mục có ý nghĩa là đủ; với sự cố nghiêm trọng, tổ chức có thể yêu cầu hồ sơ chi tiết hoặc bằng chứng pháp lý/bảo mật. Không dùng quy mô tài liệu như thước đo chất lượng học hỏi.

### 11.3. “Five Whys” chỉ là công cụ đặt câu hỏi

Ví dụ về một chuỗi **giả thuyết chưa được kiểm chứng**:

1. Vì sao học viên gửi lại nhiều lần? Vì họ thấy timeout và không biết kết quả thật.
2. Vì sao không biết kết quả? Vì giao diện không có cách tra cứu trạng thái yêu cầu trước.
3. Vì sao trường hợp này chưa được xử lý? Vì ví dụ acceptance criteria chủ yếu xét phản hồi thành công thông thường.
4. Vì sao refinement thiếu ví dụ timeout sau commit? Vì người hiểu nghiệp vụ và chuyên gia kiểm thử chưa trao đổi về giao dịch lặp.
5. Vì sao điều đó không được phát hiện trước release? Vì CI thiếu test mô phỏng phản hồi bị mất sau khi DB đã lưu.

Đây **không phải kết luận root cause** cho hệ thống thực tế. Nhóm phải xác minh qua log, mã, hợp đồng API, test và các bằng chứng khác. Nguyên nhân có thể **đa yếu tố**: idempotency, transaction, trạng thái giao diện, thời điểm rollout và cả dữ liệu test. Đừng dừng ở câu “người dùng nhấn hai lần” hoặc “developer bất cẩn”.

### 11.4. Hành động phòng ngừa cần kiểm chứng được

Một hành động như **“nâng cao ý thức kiểm thử”** khó biết khi nào hoàn tất. Những hành động có thể kiểm chứng hơn:

| Đối sách | Bằng chứng hoàn tất | Tín hiệu sau áp dụng |
| --- | --- | --- |
| Bổ sung tình huống retry sau timeout vào ví dụ đăng ký. | Acceptance criteria được làm rõ và nhất quán với nghiệp vụ. | Những PBI tương tự có kiểm tra tình huống lỗi mạng. |
| Thêm integration test cho request lặp và trạng thái DB. | Test chạy trên bản tích hợp, chứng minh không tạo đăng ký trùng. | Ít lỗi dữ liệu tương tự xuất hiện sau phát hành. |
| Thêm cách tra cứu trạng thái an toàn trên giao diện. | Học viên thử xác minh trạng thái thật mà không tạo request mới. | Ít yêu cầu hỗ trợ “đã đăng ký hay chưa?”. |
| Bổ sung alert về bất nhất dữ liệu. | Cảnh báo được kiểm tra thử, người trực có runbook. | Thời gian từ phát hiện tới xử lý giảm. |
| Cập nhật hướng dẫn support và đường escalation. | Support thử xử lý tình huống giả lập đúng giới hạn. | Giảm số lần chuyển tuyến thiếu thông tin. |

Những tín hiệu trên cần được đo với **bối cảnh và dữ liệu tương đương**. Nếu số yêu cầu hỗ trợ giảm khi lượng học viên giảm, không thể quy toàn bộ tác dụng cho hướng dẫn mới.

## 12. Hỗ trợ người dùng hiệu quả: kiến thức, hướng dẫn và trải nghiệm

### 12.1. Support giúp người dùng đạt kết quả, không chỉ đóng ticket

Một ticket có thể được đóng vì người dùng không phản hồi hoặc vì nhân viên gửi hướng dẫn, trong khi học viên vẫn không biết mình đã đăng ký thành công chưa. Do đó, chất lượng hỗ trợ cần xem:

1. **Tác vụ người dùng có được giải quyết hoặc có workaround an toàn không?**
2. **Họ có nhận được thông tin đúng và dễ hiểu không?**
3. **Thông tin nhạy cảm có được bảo vệ không?**
4. **Vấn đề có lặp lại hoặc phải chuyển tuyến quá nhiều lần không?**
5. **Nguyên nhân sản phẩm có được phản ánh cho nhóm cải tiến không?**

Hỗ trợ xuất sắc không chỉ là khả năng trả lời nhanh; đôi khi support cần chủ động nói “xin đừng gửi lại thao tác” nếu có nguy cơ ghi dữ liệu trùng, sau đó hướng dẫn cách tra trạng thái thật.

### 12.2. Tổ chức tri thức theo hai lớp

| Lớp tri thức | Đối tượng | Nội dung phù hợp |
| --- | --- | --- |
| **Hướng dẫn người dùng** | Học viên, giảng viên, người quản trị được phép. | Cách đăng ký, xem trạng thái, giải thích thông báo, các giới hạn rõ ràng. |
| **Knowledge base nội bộ** | Support, kỹ thuật, vận hành theo quyền. | Cách xác minh, mã lỗi, runbook, escalation, hạn chế đã biết và cách kiểm chứng khôi phục. |

Những lỗi phổ biến đáng đưa vào FAQ nếu:

- Có thể giải thích bằng ngôn ngữ người dùng.
- Hướng dẫn **không yêu cầu bỏ kiểm soát an toàn**.
- Vấn đề đủ lặp để tài liệu tạo giá trị.
- Có người giữ tài liệu đúng khi sản phẩm thay đổi.

Không biến FAQ thành cách né sửa một lỗi thật nghiêm trọng. Nếu người dùng phải thực hiện mười bước thủ công để bù một hành vi sản phẩm sai, nhóm nên xem đó là tín hiệu cải tiến sản phẩm.

### 12.3. Kịch bản hỗ trợ an toàn cho “không biết đã đăng ký thành công”

Một luồng trao đổi tham khảo:

1. Xác minh danh tính người liên hệ theo cơ chế hợp lệ, không hỏi mật khẩu/OTP.
2. Hỏi **khóa học và khoảng thời gian thao tác**, tránh yêu cầu gửi toàn bộ hồ sơ cá nhân qua chat không bảo vệ.
3. Dùng công cụ được phân quyền để **tra trạng thái đăng ký thực** trước khi đề nghị thử lại.
4. Nếu đã có đăng ký hiệu lực, xác nhận trạng thái và chỉ dẫn cách người dùng tự xem trong sản phẩm.
5. Nếu chưa có và dịch vụ đang ổn định, hướng dẫn thao tác lại theo quy trình được kiểm chứng.
6. Nếu không thể xác định hoặc có nghi vấn dữ liệu sai, **dừng hướng dẫn retry**, chuyển người có chuyên môn cùng correlation ID an toàn.
7. Cập nhật ticket, kết quả và phản hồi nếu phát hiện lỗi thông báo hoặc lỗi sản phẩm.

Lưu ý: quy trình tra dữ liệu phải có **kiểm soát quyền và lưu dấu truy cập phù hợp**. Không lấy lý do “support cần hỗ trợ nhanh” để cấp quyền sửa mọi bản ghi cho mọi nhân viên.

### 12.4. Giao tiếp không làm tăng lo lắng hoặc tạo cam kết giả

Một câu trả lời hữu ích nên:

- Thừa nhận **triệu chứng cụ thể** và vấn đề người dùng đang cố giải quyết.
- Phân biệt **đã xác minh** với **đang điều tra**.
- Nêu **bước an toàn tiếp theo**; không bắt người dùng lặp hành vi rủi ro.
- Cho biết kênh và nhịp cập nhật đã được xác nhận.
- Không hứa hoàn tiền, dữ liệu đã sửa hoặc thời hạn khắc phục nếu chưa có quyết định hợp lệ.

Ví dụ minh họa:

> “Chúng tôi đã tiếp nhận trường hợp bạn không thấy kết quả sau khi xác nhận đăng ký. Trước khi thử lại, vui lòng kiểm tra mục Đăng ký của tôi; nếu trạng thái vẫn chưa rõ, hãy phản hồi theo mã yêu cầu hỗ trợ để nhóm xác minh. Không cần cung cấp mật khẩu hay mã xác thực.”

Nếu giao diện chưa có mục “Đăng ký của tôi” thì **không được hướng dẫn như thể tính năng đã tồn tại**; thay bằng đường xác minh được hỗ trợ thật. Nội dung mẫu cần được kiểm tra với sản phẩm đang chạy.

### 12.5. Giảm gánh nặng support bằng cải tiến sản phẩm

Những phản ánh giống nhau có thể chỉ ra:

- Thông báo quá chung chung.
- Không có trang tra trạng thái sau lỗi mạng.
- Hướng dẫn thiếu ví dụ trực quan.
- Cơ chế retry không idempotent.
- Trạng thái dữ liệu bị lệch giữa các dịch vụ.
- Khả năng tiếp cận kém khiến một nhóm người dùng không hoàn tất tác vụ.

Support và Product Owner nên cùng xem **chủ đề lặp, tác động và chi phí thao tác thủ công**. Sửa nguyên nhân trong sản phẩm có thể giúp người dùng hơn việc liên tục đào tạo nhân viên hỗ trợ về cùng một workaround.

## 13. Đưa phản hồi vận hành trở lại Product Backlog

### 13.1. Mọi phản ánh đều đáng lắng nghe, không phải mọi phản ánh đều là cam kết

Product Backlog trong Scrum là **danh sách nổi lên, có thứ tự** của những điều cần thiết để cải thiện sản phẩm; Product Owner chịu trách nhiệm quản lý và ordering. Sau bàn giao, backlog nên phản ánh những điều nhóm học được:

- Defect làm sai hành vi đã cam kết.
- Các lỗi về độ tin cậy, bảo mật hoặc vận hành.
- Nhu cầu cải thiện thông báo/hành trình người dùng.
- Khả năng mới được đề xuất.
- Công việc kỹ thuật làm giảm rủi ro hoặc mở khóa giá trị.
- Thử nghiệm để kiểm chứng một giả định chưa chắc chắn.

Tuy nhiên, **tạo ticket không phải hứa thực hiện**. Product Owner có thể đề nghị làm rõ, đưa vào backlog ở thứ tự thích hợp, hoãn hoặc từ chối khi không phù hợp mục tiêu. Những nghĩa vụ ứng cứu đang gây hại vẫn đi theo cơ chế tương ứng, không đợi phiên refinement tiếp theo.

### 13.2. Phân biệt sửa lỗi, làm rõ và mở rộng phạm vi

| Phản hồi | Cách hiểu ban đầu | Hướng xử lý |
| --- | --- | --- |
| Đăng ký có thể trùng dù quy tắc cấm | **Defect** về hành vi/nhất quán dữ liệu. | Đánh giá mức ảnh hưởng, sửa với test hồi quy, xem có cần incident response. |
| Người dùng không hiểu “đăng ký đã ghi nhận” nghĩa là gì | Có thể là **vấn đề usability/thiếu làm rõ**; cần kiểm tra cam kết cũ. | Quan sát người dùng, xác định sửa lỗi hay PBI cải tiến. |
| Muốn nhận SMS trước buổi học | **Đề nghị khả năng mới** nếu không thuộc phạm vi cũ. | Làm rõ giá trị, đồng ý nhận tin, chi phí, phụ thuộc; PO ordering. |
| Cần khôi phục cảnh báo hỏng vì thay đổi cấu hình | **Cải tiến/defect vận hành**, có thể cấp bách. | Xử lý đúng rủi ro và bổ sung kiểm soát phát hành. |
| Muốn tự xem trạng thái của bản ghi đã lưu sau timeout | Có thể là **cơ hội cải tiến và giảm rủi ro**. | Phân tích tần suất, tác động, lát cắt giá trị và bằng chứng. |
| Muốn nhân viên sửa đăng ký của mọi học viên qua một nút | Nhu cầu nghiệp vụ **kèm rủi ro phân quyền**. | Không chấp nhận ngay; làm rõ thẩm quyền, audit và trường hợp sử dụng. |

Không nên định nghĩa defect chỉ dựa vào cảm giác của người gửi, cũng không nên gọi mọi yêu cầu khó là “scope creep”. Cần đối chiếu hành vi đã cam kết, ranh giới hiện tại, DoD, bằng chứng thực và tác động.

### 13.3. Từ ticket hỗ trợ sang PBI có giá trị

Một phản ánh ban đầu:

> “Đăng ký bị treo, tôi phải gửi lại ba lần.”

Sau khi làm rõ, có thể hình thành PBI:

**Tên:** Học viên xem được trạng thái đăng ký sau khi mất phản hồi mạng.

**Vấn đề:** người học không biết request trước đã được lưu hay chưa, dễ lặp thao tác và phải nhờ hỗ trợ.

**Giá trị kỳ vọng:** giúp học viên tự phục vụ, giảm tác động retry và giảm số ticket về trạng thái mơ hồ.

**Một số điều kiện chấp nhận:**

~~~gherkin
Feature: Kiểm tra trạng thái đăng ký sau lỗi kết nối

  Scenario: Yêu cầu ban đầu đã được lưu nhưng mất phản hồi
    Given học viên A đã có một đăng ký hiệu lực cho khóa X
    And phản hồi của yêu cầu đăng ký bị gián đoạn
    When A mở lại trang đăng ký của chính mình
    Then A thấy trạng thái đăng ký đã ghi nhận đúng
    And việc tải lại trang không tạo đăng ký hiệu lực thứ hai

  Scenario: Chưa có đăng ký hiệu lực
    Given A chưa có đăng ký hiệu lực cho khóa X
    When A kiểm tra trạng thái đăng ký của mình
    Then hệ thống hiển thị trạng thái thật
    And không tự báo thành công nếu chưa có dữ liệu xác nhận

  Scenario: Người dùng khác cố xem trạng thái
    Given B không có quyền xem đăng ký của A
    When B yêu cầu trạng thái đăng ký của A
    Then hệ thống từ chối truy cập
~~~

Đây là **ví dụ học tập**, chưa phải test chạy được. Developers và người có thẩm quyền cần xác nhận quy tắc dữ liệu, retry và quyền truy cập trong hệ thống thật.

### 13.4. Product Owner sắp thứ tự dựa trên giá trị và rủi ro

Một đề nghị cải tiến có thể được đánh giá theo:

1. **Tác động người dùng:** ai bị ảnh hưởng, họ không hoàn tất được tác vụ gì?
2. **Mức nguy hiểm:** có mất dữ liệu, lộ thông tin hoặc giao dịch sai?
3. **Chi phí trì hoãn:** mỗi kỳ chờ gây thêm công sức hỗ trợ, thiệt hại hoặc mất cơ hội gì?
4. **Sự phù hợp Product Goal:** có tiến gần trạng thái sản phẩm đang hướng tới?
5. **Năng lực và phụ thuộc:** làm trong một lát cắt có giá trị được không? Có rủi ro kỹ thuật chưa rõ?
6. **Bằng chứng:** phản hồi định tính, dữ liệu sử dụng, tín hiệu sự cố có đủ tin cậy không?

Khi cần, Product Owner có thể dùng Cost of Delay, WSJF, RICE hoặc cách ưu tiên khác như **công cụ hỗ trợ quyết định**, không phải công thức Scrum bắt buộc. Không biến mỗi chỉ số thành lý do trì hoãn ứng cứu sự cố đang gây hại.

### 13.5. Theo dõi người dùng sau khi làm thay đổi

Giả sử nhóm đã triển khai trang tra cứu trạng thái. Không chỉ đóng PBI vì mã đã merge:

- Đã đáp ứng DoD và phát hành tới nhóm người dùng phù hợp chưa?
- Có thể quan sát được số tình huống trạng thái mơ hồ giảm không?
- Người dùng hiểu nội dung và có thao tác lại an toàn không?
- Support có biết hướng dẫn mới và có runbook cập nhật chưa?
- Có phát sinh lỗ hổng phân quyền hoặc tác động dữ liệu ngoài dự kiến không?

Đây là **vòng học hỏi**, không phải cam kết rằng một thay đổi chắc chắn làm giảm số ticket. Cần so sánh theo lượng người dùng, mùa vụ và kênh hỗ trợ tương đương.

## 14. Release và vận hành an toàn: mở rộng từng bước và có đường khôi phục

### 14.1. Một thay đổi có thể được triển khai trước khi mở sử dụng

Để giảm rủi ro, nhóm có thể:

- Merge code tương thích với phiên bản hiện tại.
- Dùng **feature flag** để tạm ẩn khả năng chưa hoàn tất.
- Triển khai lên môi trường phù hợp và xác minh bản tích hợp.
- Mở cho một nhóm nhỏ người dùng có thể quan sát.
- Theo dõi tín hiệu chất lượng, dữ liệu và trải nghiệm.
- Mở rộng khi các điều kiện đã thống nhất đạt; dừng nếu rủi ro tăng.

Feature flag **không phải ranh giới bảo mật**: nếu người dùng không được phép truy cập API, phải có kiểm tra phân quyền ở server. Một tính năng chưa đáp ứng DoD vẫn **không được gọi Increment Done** chỉ vì mã đã ẩn sau flag.

### 14.2. Các chiến lược triển khai và giới hạn

| Chiến lược | Tác dụng | Điều cần cẩn trọng |
| --- | --- | --- |
| **Canary** | Thử trên một phần nhỏ lưu lượng/người dùng. | Lỗi dữ liệu có thể không đảo ngược dù nhóm thử nhỏ. |
| **Rolling deployment** | Thay phiên bản dần qua nhiều instance. | Các phiên bản cũ/mới có thể cùng hoạt động, cần tương thích. |
| **Blue–green** | Chuyển giữa hai môi trường chạy phiên bản khác nhau. | Dữ liệu chung, session, message và migrations vẫn cần xử lý. |
| **Feature flag** | Tách deploy khỏi thời điểm bật hành vi. | Cần chủ sở hữu, chính sách phân quyền và kế hoạch gỡ flag. |
| **Rollback/revert** | Quay lại một phiên bản hoặc cấu hình an toàn theo quy trình. | Không tự hoàn tác dữ liệu, email, thanh toán hoặc side effects. |
| **Forward fix** | Đưa thay đổi sửa nhỏ vào khi rollback không an toàn. | Cần đánh giá tác động, quyền và kiểm thử; không chọn chỉ vì nhanh. |

Không chiến lược nào phù hợp mọi hệ thống. Quyết định rollback hay forward fix cần dựa trên trạng thái dữ liệu, rủi ro, khả năng phục hồi và người có thẩm quyền.

### 14.3. Thay đổi dữ liệu cần kế hoạch riêng

Với schema hoặc hợp đồng API, có thể dùng cách **expand–migrate–contract**:

1. Thêm khả năng/hợp đồng mới tương thích với phần đang chạy.
2. Chuyển mã và dữ liệu từng bước, có quan sát và kiểm chứng.
3. Chỉ bỏ cấu trúc cũ khi biết các thành phần phụ thuộc không còn sử dụng.

Ví dụ, nếu nhóm đổi cấu trúc lưu trạng thái đăng ký, rollback code về phiên bản cũ sẽ có rủi ro nếu những bản ghi đã ghi theo schema mới không còn tương thích. Đội cần **kiểm tra migration/khôi phục bằng dữ liệu thử an toàn**, không coi “git revert” là phương án dữ liệu.

### 14.4. Release readiness và exit criteria

Một cuộc trao đổi trước rollout có thể xét:

| Câu hỏi | Bằng chứng / quyết định |
| --- | --- |
| Increment đáp ứng DoD chưa? | Kiểm thử, review và chuẩn chất lượng đã thực sự đạt. |
| Kịch bản nghiệp vụ quan trọng dùng được trên bản tích hợp chưa? | Smoke/E2E/contract/integration tests phù hợp. |
| Những rủi ro nào còn tồn tại? | Danh sách rủi ro, phạm vi và người chịu trách nhiệm. |
| Có ngưỡng dừng rollout không? | SLI/alert, điều kiện dữ liệu sai, quyền dừng được giao. |
| Support đã nắm thay đổi chưa? | Release note, FAQ, runbook và đầu mối xác nhận. |
| Có biết ai trực hỗ trợ khi triển khai? | Lịch trực, escalation, kênh liên lạc được xác nhận. |
| Có khả năng khôi phục không? | Phương án rollback/forward fix, đánh giá migration/side effects. |
| Sau khi release ai kiểm tra giá trị? | Product Owner, người dùng đại diện và phương pháp thu phản hồi. |

**Kiểm tra sẵn sàng không nhất thiết là hội đồng duyệt lớn**. Có thể tự động hóa các phép kiểm chứng và dùng người có thẩm quyền cho những quyết định rủi ro thực sự. Tổ chức phải giữ các yêu cầu bắt buộc theo chính sách/ngành.

### 14.5. “Hypercare” có thể hữu ích nhưng không nên là chế độ chữa cháy mãi mãi

Một số nhóm tăng cường theo dõi/hỗ trợ trong thời gian ngay sau một thay đổi lớn, đôi khi gọi là **hypercare**. Cách làm này có thể gồm:

- Kênh phối hợp nhanh giữa support–Developers–on-call.
- Dashboard và ngưỡng cảnh báo theo thay đổi.
- Lịch theo dõi có người chịu trách nhiệm.
- Tổng hợp câu hỏi người dùng để sửa tài liệu hoặc sản phẩm.
- Tiêu chí chuyển về vận hành thông thường.

Hypercare không phải sự kiện Scrum bắt buộc và **không thay thế chuẩn DoD**. Nếu mỗi lần release đều cần toàn bộ đội làm ngoài giờ trong thời gian dài, đó là tín hiệu cần cải thiện kỹ thuật, khả năng triển khai hoặc kiến trúc, không phải một trạng thái bình thường của Agile.

## 15. Tình huống xuyên suốt: lỗi mạng sau đăng ký trong ngày mở lớp

### 15.1. Bối cảnh minh họa

Nền tảng học trực tuyến đã mở luồng đăng ký khóa miễn phí cho học viên. Đội vừa phát hành bản có cải thiện thông báo và cơ chế gọi API.

Trong thời gian mở đăng ký một lớp còn ít chỗ, một số học viên gửi yêu cầu nhưng thấy **“Không thể hoàn tất yêu cầu”**. Vài người thử lại, có người hỏi support có bị ghi hai lần hay không. Dashboard cho thấy độ trễ API tăng, nhưng chưa có bằng chứng rằng DB đã ghi trùng.

**Dữ liệu và timeline sau đây hoàn toàn giả định để học tập.** Không được suy ra đây là sự cố đã xảy ra hoặc các con số là chuẩn cho một dịch vụ thực.

### 15.2. Timeline quan sát ban đầu

| Giờ địa phương minh họa (+07:00) | Sự kiện | Thông tin đã biết |
| --- | --- | --- |
| **09:00** | Bắt đầu mở khả năng đăng ký cho nhóm học viên thử nghiệm. | Bản phát hành và phạm vi flag đã ghi nhận. |
| **09:08** | Dashboard thấy độ trễ API tăng. | Chưa biết có sai dữ liệu. |
| **09:11** | Support nhận ba ticket về thông báo lỗi sau khi bấm đăng ký. | Có phản ánh từ người dùng, chưa đại diện toàn bộ lưu lượng. |
| **09:14** | On-call cùng Developers kiểm tra tín hiệu và phân loại sự cố. | Có request timeout; trạng thái DB của một số request chưa xác minh. |
| **09:19** | Điều phối quyết định tạm dừng mở rộng rollout. | Hạn chế phạm vi bị ảnh hưởng theo quyền. |
| **09:27** | Nhóm tìm được cách truy vết request bằng correlation ID. | Có trường hợp DB đã ghi thành công nhưng phản hồi HTTP không tới client. |
| **09:35** | Support được cung cấp hướng dẫn tra trạng thái an toàn. | Không yêu cầu người dùng retry khi chưa xác minh. |
| **09:47** | Nhóm xử lý nguyên nhân độ trễ theo quy trình kỹ thuật. | Cần kiểm chứng lại các kịch bản dữ liệu và retry. |
| **10:10** | Các tín hiệu về mức chấp nhận; smoke test và kiểm tra dữ liệu đạt theo phạm vi đã xem. | Ứng cứu có thể chuyển sang giai đoạn theo dõi, chưa có kết luận toàn bộ hậu quả. |
| **Ngày sau đó** | Nhóm tổ chức hậu kiểm và lập kế hoạch cải tiến. | Cần kiểm chứng nguyên nhân gốc và hành động phòng ngừa. |

Timeline tạo ra **ngôn ngữ chung về sự kiện**. Không nên điền kết luận nguyên nhân vào những thời điểm chỉ mới có triệu chứng.

### 15.3. Support xử lý như thế nào?

Khi tiếp nhận trường hợp, nhân viên hỗ trợ:

1. Xác minh người yêu cầu theo cơ chế của sản phẩm.
2. Ghi thời điểm, khóa học và mã correlation an toàn nếu có.
3. Kiểm tra xem người học đã có đăng ký hiệu lực hay chưa qua công cụ **chỉ đọc theo quyền**.
4. Nếu đã có bản ghi, xác nhận trạng thái; không tạo đăng ký mới.
5. Nếu chưa có và hệ thống vẫn bất ổn, hướng dẫn người học **không thử lại** cho tới khi có thông báo an toàn.
6. Nếu thấy hai bản ghi hoặc dấu hiệu sai dữ liệu, chuyển ngay theo chính sách sự cố dữ liệu.
7. Cập nhật ticket và thời điểm có thông tin tiếp theo.

Support **không tự sửa dữ liệu trực tiếp** để hoàn thành ticket nhanh. Với trường hợp cần sửa dữ liệu, phải có người có thẩm quyền, dấu vết và kế hoạch kiểm chứng.

### 15.4. On-call và Developers xử lý như thế nào?

Nhóm kỹ thuật:

- Kiểm tra độ trễ, timeouts, phiên bản và phạm vi rollout.
- Dùng correlation ID để đối chiếu yêu cầu với trạng thái cuối ở DB và thành phần phụ thuộc.
- Xem liệu request lặp có tạo tác động trùng hay không; không chỉ nhìn status code.
- Đánh giá có nên tạm dừng rollout/giảm lưu lượng hoặc khôi phục phiên bản.
- Xác định cách sửa theo quyền được giao và kiểm tra rủi ro side effects.
- Chạy lại những test bắt buộc về retry, concurrency và dữ liệu sau xử lý.
- Cung cấp thông tin đã kiểm chứng cho support và người điều phối.

Khi nguyên nhân còn chưa rõ, nhóm phải **gọi đó là giả thuyết**. Không tự kết luận rằng timeout do “mạng học viên” chỉ vì máy chủ hiện vẫn hoạt động.

### 15.5. Product Owner và người điều phối xử lý như thế nào?

**Người điều phối sự cố** bảo đảm tác động được đánh giá, có quyết định/nguồn thông tin nhất quán và việc ứng cứu không bị phân tán. **Product Owner** nắm ảnh hưởng tới giá trị sản phẩm, hỗ trợ làm rõ quy tắc nghiệp vụ và chuẩn bị quyết định thứ tự backlog cho những việc sửa/phòng ngừa.

Nếu sự cố đang gây hại, on-call phải ứng cứu theo **quy trình đã định**, không chờ Product Owner tổ chức một buổi refinement. Đồng thời, Product Owner không cần quyết định cấu hình DB cấp thấp nếu Developers/người vận hành có thẩm quyền và chuyên môn xử lý.

### 15.6. Sơ đồ xử lý lỗi mạng nhưng trạng thái ghi dữ liệu chưa rõ

~~~mermaid
flowchart TD
    A["Học viên gửi yêu cầu đăng ký"] --> B{"Có kết quả xác nhận rõ?"}
    B -- "Có" --> C["Hiển thị đúng trạng thái thật"]
    B -- "Không / timeout" --> D["Không tự suy rằng ghi dữ liệu thất bại"]
    D --> E["Tra trạng thái bằng cơ chế an toàn / correlation ID"]
    E --> F{"Trạng thái dữ liệu đã xác minh?"}
    F -- "Đã đăng ký" --> G["Hiển thị đăng ký hiện có; không ghi thêm"]
    F -- "Chưa đăng ký" --> H["Chỉ cho thử lại khi dịch vụ và chính sách an toàn cho phép"]
    F -- "Không xác minh được" --> I["Chuyển tuyến hỗ trợ; không lặp thao tác rủi ro"]
    H --> J["Kiểm tra idempotency và quyền ở server"]
~~~

Đây là **luồng tư duy**, không phải thuật toán production hoàn chỉnh. Để thực thi đúng, cần thiết kế giao dịch, idempotency, khả năng quan sát và quyền truy cập cụ thể.

### 15.7. Những kết quả phải xác minh trước khi khép lại

| Khía cạnh | Bằng chứng cần có |
| --- | --- |
| **Khôi phục dịch vụ** | Tỷ lệ lỗi/độ trễ và kịch bản đăng ký cốt lõi ở mức chấp nhận đã định. |
| **Toàn vẹn dữ liệu** | Không có đăng ký trùng/vượt sức chứa trong phạm vi cần kiểm tra; trường hợp sai được xử lý đúng quy trình. |
| **Quyền riêng tư** | Việc tra trạng thái không lộ bản ghi của người khác. |
| **Truyền thông** | Người dùng bị ảnh hưởng có chỉ dẫn phù hợp; support biết trạng thái. |
| **Dự phòng** | Test retry/concurrency được bổ sung và chạy đạt; alert/runbook được sửa nếu cần. |
| **Giá trị sản phẩm** | Product Owner xem liệu người học có còn gặp khó trong việc tự xác nhận đăng ký hay không. |

Nếu dữ liệu không thể xác minh đầy đủ ngay, nhóm phải ghi **phạm vi chưa chắc chắn và người theo dõi**, không tuyên bố “mọi thứ đã được giải quyết” chỉ vì tốc độ API trở lại bình thường.

### 15.8. Từ sự cố thành cơ hội cải tiến

Một hậu kiểm có thể tạo các công việc:

- **Defect/kiểm soát dữ liệu:** bảo đảm retry không ghi trùng trong mọi tình huống yêu cầu.
- **Quality improvement:** thêm integration test mất phản hồi sau commit.
- **Observability:** dashboard phân biệt timeout với trạng thái ghi dữ liệu thật.
- **Runbook/support:** bổ sung bước tra cứu an toàn, thông báo người dùng khi trạng thái chưa rõ.
- **Product improvement:** khả năng học viên tự xem trạng thái đăng ký không cần gọi nhân viên.
- **Process improvement:** mời support và vận hành vào buổi làm rõ những thay đổi ảnh hưởng retry/rollout.

Không nên lập sáu ticket chỉ để có vẻ “đã hậu kiểm”. Mỗi hành động cần **lý do, chủ sở hữu, thứ tự/rủi ro, bằng chứng hoàn tất và cách kiểm tra tác dụng**.

## 16. Thiết kế nhịp phối hợp hằng ngày và sau mỗi đợt phát hành

### 16.1. Cộng tác theo sự kiện và rủi ro, không chỉ theo phòng ban

Một hệ thống học hỏi hiệu quả cần các **đường trao đổi có chủ đích**:

- **Khi đang có incident:** dùng kênh điều phối sự cố, người trực, đầu mối truyền thông và nhịp cập nhật phù hợp; ưu tiên khôi phục.
- **Khi support gặp một vấn đề chưa rõ:** có cơ chế chuyển tuyến với dữ liệu tối thiểu, đúng quyền và thời điểm phản hồi.
- **Khi chuẩn bị release:** Developers, support và vận hành xem thay đổi ảnh hưởng và khả năng giám sát/khôi phục.
- **Khi nhiều phản ánh giống nhau:** Product Owner và nhóm liên quan đánh giá nguyên nhân, giá trị cải tiến và thứ tự backlog.
- **Khi có thông tin mới về sản phẩm:** trao đổi với người dùng/stakeholder, cập nhật giả thuyết và điều kiện chấp nhận.
- **Khi kết thúc sự cố hoặc đợt cải tiến:** kiểm tra bằng chứng để chọn đối sách có tác dụng.

Không cần tạo sáu cuộc họp cố định nếu có thể xử lý bằng dashboard, ticket rõ bối cảnh hoặc trao đổi trực tiếp. Nhưng **việc không họp** không thể là lý do để thiếu người chịu trách nhiệm hay bỏ qua rủi ro.

### 16.2. Một bảng Kanban cho luồng hỗ trợ và khắc phục

~~~mermaid
flowchart LR
    A["Tiếp nhận"] --> B["Xác minh / triage"]
    B --> C["Sẵn sàng xử lý"]
    C --> D["Đang xử lý"]
    D --> E["Kiểm chứng với hệ thống / người dùng"]
    E --> F["Đã giải quyết / đóng vòng"]
    E -. "Chưa đạt" .-> D
    B -. "Sự cố khẩn" .-> G["Luồng incident riêng"]
    G --> H["Khôi phục + hậu kiểm"]
    H --> C
~~~

Đây chỉ là một thiết kế tham khảo. Nếu dùng Kanban, nhóm cần định nghĩa:

- **Started point:** ví dụ lúc một yêu cầu được nhận xử lý, không tính từ khi khách hàng tạo lần đầu nếu đang đo cycle time xử lý nội bộ.
- **Finished point:** khi yêu cầu đã được xử lý và đóng vòng đúng chính sách, không chỉ khi người thực hiện trả lời “đã xong”.
- **Explicit policies:** điều kiện vào/ra trạng thái, rework, blocked, chờ phản hồi và việc khẩn cấp.
- **WIP control:** giới hạn lượng việc đang làm dở, ưu tiên hoàn tất hoặc xử lý blocker.
- **Service Level Expectation (SLE):** kỳ vọng thời gian hoàn thành item với xác suất theo loại việc và dữ liệu phù hợp; không tự đồng nhất với SLA hợp đồng.

Sự cố sản xuất nghiêm trọng có thể cần **luồng ứng cứu riêng** để không bị giữ trong hàng đợi công việc thông thường. Đồng thời cần minh bạch ảnh hưởng của việc ưu tiên khẩn đến những hạng mục khác.

### 16.3. Phân tách hàng đợi mà không mất cái nhìn toàn hệ thống

Một tổ chức có thể có các bảng riêng:

| Luồng | Chủ yếu theo dõi | Liên kết cần giữ |
| --- | --- | --- |
| **Support requests** | Câu hỏi, xác minh, hướng dẫn, kết quả hỗ trợ. | Liên kết defect, incident, phản hồi sản phẩm khi cần. |
| **Incidents** | Tác động, khôi phục, truyền thông và hậu kiểm. | Liên kết release/version, defect, problem và hành động phòng ngừa. |
| **Product Backlog** | Cơ hội cải thiện sản phẩm có thứ tự. | Liên kết nguồn phản hồi, bằng chứng, rủi ro và Product Goal. |
| **Engineering improvements** | Kiểm thử, observability, debt và khả năng bảo trì. | Thể hiện tác động đến sản phẩm, rủi ro và luồng công việc. |

Không nhất thiết đưa mọi ticket support vào Product Backlog; không phải mọi lỗi triển khai đều cần tạo một PBI mới nếu đang có sự cố chưa được khôi phục. Nhưng các hệ thống phải có **khả năng truy ngược từ ảnh hưởng người dùng tới quyết định và thay đổi khắc phục** khi cần.

### 16.4. Nhịp xem xét minh họa

| Nhịp | Nội dung gợi ý | Kết quả mong muốn |
| --- | --- | --- |
| **Trong incident** | Tác động, điều đang làm, blockers, quyết định, nhịp cập nhật. | Một thông tin sự thật nhất quán, phản ứng an toàn. |
| **Hằng ngày hoặc theo nhu cầu** | Ticket bị chặn, item già, lỗi lặp, tình trạng rollout. | Gỡ điểm nghẽn, không bỏ quên người dùng. |
| **Sau release quan trọng** | Lỗi/độ trễ, dữ liệu, câu hỏi support, tín hiệu outcome. | Quyết định mở rộng, tạm dừng hoặc cải tiến. |
| **Refinement/backlog review** | Các đề nghị mới và bằng chứng từ vận hành. | PBI rõ hơn, ordering có căn cứ. |
| **Retrospective/kaizen** | Điều gì gây chờ, rework hoặc khó phối hợp? | Một vài thử nghiệm cải tiến có người theo dõi. |
| **Hậu kiểm sự cố đáng kể** | Timeline, yếu tố góp phần, đối sách và bằng chứng. | Giảm khả năng tái diễn hoặc mức tác động. |

Những nhịp này có thể đi cùng các sự kiện Scrum hoặc được tổ chức độc lập khi đội dùng Kanban. **Không chờ Sprint Review** mới thông báo sự cố đang ảnh hưởng người dùng.

## 17. Đo hiệu quả hỗ trợ và vận hành sau bàn giao

### 17.1. Nhóm cần chỉ số cân bằng, không chỉ thời gian đóng ticket

| Khía cạnh | Số đo/tín hiệu | Câu hỏi quyết định |
| --- | --- | --- |
| **Kết quả người dùng** | Tỷ lệ hoàn tất tác vụ, mức tự phục vụ, trường hợp cần hỗ trợ. | Người dùng có nhận được giá trị dễ dàng hơn không? |
| **Tiếp nhận hỗ trợ** | Thời gian tới phản hồi đầu tiên có ích, tỷ lệ yêu cầu thiếu thông tin. | Người dùng có được tiếp nhận rõ ràng, kịp thời không? |
| **Giải quyết hỗ trợ** | Thời gian tới giải quyết, reopen, số lần chuyển tuyến, kết quả xác minh. | Có xử lý đúng vấn đề hay chỉ gửi câu trả lời nhanh? |
| **Sự cố** | Thời gian phát hiện, thời gian khôi phục, phạm vi ảnh hưởng, tái phát, hậu quả dữ liệu. | Dịch vụ có được bảo vệ và khôi phục đáng tin cậy? |
| **Độ tin cậy** | SLI/SLO thích hợp, tỷ lệ lỗi, độ trễ, dữ liệu bất nhất. | Sản phẩm hoạt động như đã cam kết trong điều kiện thực? |
| **Dòng công việc** | WIP, throughput, work item age, cycle time của luồng đã định. | Hàng đợi hay phụ thuộc nào đang tạo thời gian chờ? |
| **Chất lượng thay đổi** | Lỗi sau release, thời gian phát hiện regressions, khả năng rollback/khôi phục. | Có cải tiến nhanh mà vẫn giữ chất lượng không? |
| **Học hỏi** | Hành động hậu kiểm hoàn tất và hiệu quả, các chủ đề lặp đã được xử lý. | Nguyên nhân hệ thống có thực sự thay đổi? |
| **Sự bền vững** | Tần suất báo động đêm, quá tải trực, lượng việc khẩn chen ngang. | Đội có đang duy trì dịch vụ bằng cách hy sinh sức khỏe con người? |

Số lượng ticket càng ít **không tự chứng minh** sản phẩm tốt hơn: có thể lượng người dùng giảm, kênh hỗ trợ khó tìm hoặc người dùng bỏ cuộc mà không gửi yêu cầu. Thời gian đóng ticket càng nhanh cũng có thể vì nhân viên chuyển “resolved” trước khi người dùng kiểm chứng.

### 17.2. Phân biệt response time và resolution time

**First response time** có thể đo thời gian từ lúc người dùng mở yêu cầu tới khi nhận phản hồi đầu tiên **có ích** theo định nghĩa. **Resolution time** đo tới mốc vấn đề được xử lý/đóng vòng theo chính sách.

Ví dụ giả định:

~~~text
09:00  Học viên tạo ticket.
09:08  Support xác nhận đã tiếp nhận, yêu cầu không gửi lại đăng ký.
09:20  Support chuyển kỹ thuật với correlation ID.
11:00  Nhóm kỹ thuật xác nhận đã sửa lỗi và kiểm chứng.
11:15  Học viên được thông báo trạng thái thực.
~~~

Tùy quy ước:

- Phản hồi đầu tiên sau **8 phút**.
- Giải quyết/đóng vòng sau **2 giờ 15 phút**, nếu chính sách coi 11:15 là mốc hoàn tất.
- Nếu tổ chức coi mốc 11:00 là khôi phục dịch vụ, **thời gian khôi phục kỹ thuật** có thể khác thời gian đóng yêu cầu người dùng.

Mỗi chỉ số cần nói rõ **mốc, lịch tính, múi giờ, loại yêu cầu và điều kiện tạm dừng tính thời gian nếu có**. Không tự lấy một con số rồi gọi đó là cam kết SLA cho mọi sự cố.

### 17.3. Một tỷ lệ hỗ trợ tự phục vụ giả định

Giả sử trong một đợt mở lớp có **500 học viên** gặp nhu cầu tra cứu trạng thái đăng ký. Trong số đó, **420 người** hoàn thành qua giao diện mà không phải mở yêu cầu hỗ trợ (được xác định bằng sự kiện đo phù hợp và tôn trọng riêng tư):

\[
\text{Tỷ lệ tự phục vụ minh họa}
=\frac{420}{500}\times100\%
=84\%.
\]

Đây là **bài toán số học**, không phải kết luận chất lượng của sản phẩm thật. Cần biết 500 là tập nào, sự kiện “tự phục vụ thành công” có chính xác hay không, người dùng có bỏ cuộc âm thầm không, và liệu giao diện có tạo hành vi không an toàn.

### 17.4. Time to Detect và Time to Restore cần định nghĩa cụ thể

Hai mốc thường hữu ích:

- **Time to Detect/Acknowledge:** khoảng từ khi điều kiện sự cố bắt đầu hoặc từ tín hiệu đầu tiên tới khi có người/hệ thống phát hiện hoặc xác nhận, theo định nghĩa của đội.
- **Time to Restore:** khoảng từ mốc sự cố đã chọn tới lúc dịch vụ trở về mức chấp nhận được, theo định nghĩa và bằng chứng kiểm chứng.

Không nên trộn “thời gian từ khi alert gửi” với “thời gian từ khi người dùng bắt đầu bị ảnh hưởng” trong cùng một biểu đồ. Nếu không biết thời điểm lỗi thực sự bắt đầu, phải nói rõ mức bất định.

Một điểm trung bình có thể che các sự cố rất dài; nên xem **phân bố, độ nghiêm trọng và hậu quả**, không chỉ trung bình. Không dùng thời gian khôi phục để xếp hạng cá nhân trực sự cố, vì mức khó và phạm vi phụ thuộc khác nhau.

### 17.5. Metrics không nên làm người dùng và người trực chịu rủi ro

Những mục tiêu dễ gây hành vi sai:

- Yêu cầu đóng mọi ticket trong 30 phút nên nhân viên đóng yêu cầu khi chưa xác minh.
- Thưởng cho đội ít incident nên người làm ngại khai báo.
- Đếm mọi alert như “sự cố” để chứng minh đội vận hành hoạt động tích cực.
- Đếm số PBI tạo từ feedback mà không xét giá trị giải quyết.
- Chỉ tối ưu uptime, bỏ qua lỗi dữ liệu trả HTTP 200.
- Gây áp lực cho người trực phải rollback mọi thứ thật nhanh dù dữ liệu không tương thích.

**Mục tiêu là giúp hệ thống an toàn và người dùng đạt kết quả**, không phải tạo bảng chỉ số đẹp mà che giấu vấn đề.

## 18. Liên hệ với Scrum, Kanban, XP, Lean và DevOps

### 18.1. Scrum: Product Goal không dừng lại khi Increment được phát hành

Trong Scrum, Product Owner chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog; Developers tạo Increment đạt DoD; Scrum Master hỗ trợ hiệu quả Scrum Team.

Sau release:

- **Product Owner** dùng phản hồi support/vận hành để xem Product Goal và sắp thứ tự PBI.
- **Developers** hỗ trợ hiểu hành vi, sửa defect, bổ sung test, monitoring và thiết kế khả năng khôi phục.
- **Scrum Master** giúp tháo gỡ trở ngại giữa nhóm/đơn vị để công việc có chất lượng và minh bạch.
- **Sprint Review** kiểm tra sản phẩm và bối cảnh để thích ứng backlog.
- **Sprint Retrospective** cải thiện chất lượng và hiệu quả cách làm.

Không được hiểu rằng Developers chỉ có trách nhiệm trong một Sprint, hoặc rằng sự cố chỉ được xử lý sau Sprint Review. **Ứng cứu vẫn phải theo chính sách vận hành phù hợp tại thời điểm xảy ra.**

### 18.2. Kanban: tối ưu dòng hỗ trợ và khắc phục

Kanban giúp nhìn thấy **từ yêu cầu tới kết quả**, giới hạn WIP và nhận diện blocker trong review, kiểm chứng, hỗ trợ hoặc phối hợp liên nhóm. Một service desk có thể dùng Kanban ngay cả khi đội phát triển dùng Scrum.

Điều quan trọng là:

- Định nghĩa workflow và mốc Started/Finished rõ.
- Không làm biến mất item blocked khỏi số lượng việc dở dang.
- Đặt policy cho yêu cầu khẩn và chuyển tuyến.
- Phân biệt thời gian giải quyết support với cycle time phát triển PBI.
- Sử dụng work item age và SLE để chú ý yêu cầu lâu bất thường.

Kanban **không bắt buộc Sprint hoặc Scrum Master**. Nó có thể bổ trợ Scrum mà không thay thế các accountabilities và commitments của Scrum.

### 18.3. XP và kỹ thuật liên tục giúp vận hành dễ dàng hơn

Các thực hành **Extreme Programming** như TDD, CI, refactoring, pairing và thay đổi nhỏ giúp:

| Thực hành | Giá trị sau bàn giao |
| --- | --- |
| **CI / kiểm thử hồi quy** | Phát hiện nhanh bản sửa sự cố có phá hành vi khác không. |
| **TDD / test theo rủi ro** | Đưa lỗi đã gặp vào bộ kiểm chứng có thể chạy lại. |
| **Pair programming / code review** | Chia sẻ hiểu biết về đường xử lý phức tạp; giảm phụ thuộc một người. |
| **Refactoring có test bảo vệ** | Giảm chi phí sửa lỗi tương lai mà không đổi hành vi ngoài ý muốn. |
| **Thay đổi nhỏ / nhánh ngắn** | Khoanh vùng ảnh hưởng và giảm xung đột khi sửa nhanh. |

Không dùng lý do “cần sửa incident nhanh” để bỏ tất cả kiểm tra rồi tạo lỗi nghiêm trọng hơn. Khi cần quy trình thay đổi khẩn cấp, phải có **điều kiện, thẩm quyền và kiểm chứng** tương xứng.

### 18.4. Lean và DevOps: giảm thời gian chờ giữa các bộ phận

Tư duy Lean nhìn toàn bộ dòng giá trị:

- Nếu backend báo Done nhưng support phải sửa dữ liệu thủ công, giá trị chưa được giao trọn vẹn.
- Nếu alert gửi cho một hộp thư không ai trực, tổ chức chưa có khả năng phản ứng.
- Nếu mỗi lần lỗi lại phải họp tìm người chịu trách nhiệm, thời gian khôi phục tăng.
- Nếu một workaround kéo dài cả năm, sản phẩm đang chuyển chi phí sang người dùng.

DevOps nhấn mạnh cộng tác giữa phát triển/vận hành cùng các cơ chế tự động hóa, đo lường và trách nhiệm rõ. Nhóm có thể dùng **PDCA** để thử cải tiến luồng: giảm handoff, bổ sung runbook, tự động kiểm chứng deployment, thực hành incident drills hoặc cải thiện observability.

### 18.5. Không đánh đồng phản hồi giá trị với phản hồi vận hành

Hai loại phản hồi bổ sung:

| Phản hồi | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Product feedback** | Tính năng có giải quyết đúng nhu cầu không? | Học viên vẫn phải gọi nhân viên vì không hiểu trạng thái đăng ký. |
| **Operational feedback** | Sản phẩm có vận hành đáng tin, có khả năng khôi phục không? | API timeout, ghi dữ liệu đúng nhưng không có cách tra cứu trạng thái sau khi mất phản hồi. |

Một sản phẩm có thể rất ổn định nhưng ít người dùng; hoặc rất hữu ích nhưng dữ liệu thiếu tin cậy. **Phản hồi sau bàn giao cần phục vụ cả chất lượng vận hành lẫn kết quả sản phẩm**.

## 19. Các phản mẫu thường gặp

| Phản mẫu | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| **“Dev xong rồi, việc còn lại của support”** | Mất ngữ cảnh kỹ thuật, lỗi kéo dài. | Xác định đường phối hợp và trách nhiệm chất lượng sau release. |
| **Không có người trực hoặc escalation rõ** | Ticket và alert bị bỏ quên. | Công bố owner, lịch trực, điều kiện chuyển tuyến và người dự phòng. |
| **Runbook chỉ có vài lệnh không giải thích** | Người mới thực hiện nguy hiểm hoặc không biết khi nào dừng. | Bổ sung phạm vi, kiểm tra an toàn, quyền và điều kiện khôi phục. |
| **Chỉ quan sát CPU và HTTP 200** | Lỗi nghiệp vụ/dữ liệu không được phát hiện. | Bổ sung tín hiệu hành trình người dùng và bất nhất dữ liệu. |
| **Tất cả phản hồi đều chuyển cho Developers** | Tắc nghẽn kỹ thuật, câu hỏi đơn giản vẫn chờ. | Tạo kiến thức tự phục vụ, chính sách hỗ trợ và triage đúng. |
| **Tất cả lỗi được đưa vào backlog chờ ưu tiên** | Incident đang gây hại không được xử lý kịp. | Phân luồng ứng cứu sự cố riêng với quản lý cải tiến. |
| **Support tự sửa DB production để đóng ticket** | Mất audit, có thể phá dữ liệu và quyền. | Quy trình thay đổi dữ liệu theo thẩm quyền, có kiểm chứng và truy vết. |
| **Cứ timeout thì khuyên người dùng thử lại liên tục** | Có thể tạo tác động trùng hoặc quá tải thêm. | Tra trạng thái thật, bảo vệ idempotency và đưa hướng dẫn an toàn. |
| **Đóng incident khi alert xanh trở lại** | Dữ liệu sai hoặc người dùng bị ảnh hưởng chưa được giải quyết. | Kiểm chứng nghiệp vụ, dữ liệu và phạm vi tác động. |
| **Thông báo phỏng đoán như sự thật** | Mất niềm tin, người dùng có thể làm sai theo hướng dẫn. | Phân biệt đã xác nhận với đang điều tra, cập nhật có căn cứ. |
| **Đánh giá cá nhân theo số ticket/incident** | Che giấu lỗi, làm số liệu đẹp nhưng kết quả xấu. | Dùng metric cho cải tiến hệ thống và chất lượng thực. |
| **Không cập nhật FAQ/runbook sau thay đổi** | Support hướng dẫn sai hoặc không hỗ trợ được. | Gắn cập nhật tài liệu vào release readiness và cải tiến. |
| **Feature flag được coi là phân quyền** | Người dùng có thể gọi API trực tiếp, lộ dữ liệu. | Kiểm tra xác thực/phân quyền phía server. |
| **Rollback Git được coi là phục hồi toàn bộ** | Side effects và dữ liệu đã ghi vẫn sai. | Đánh giá migration, idempotency, dữ liệu và kế hoạch khôi phục. |
| **Mọi đề nghị tính năng mới đều được hứa ngay** | Product Goal mất trọng tâm, WIP tăng. | PO sắp thứ tự theo giá trị, rủi ro, phụ thuộc và bằng chứng. |
| **Hậu kiểm để tìm người chịu tội** | Thành viên ngại báo rủi ro, nguyên nhân không được sửa. | Hậu kiểm hướng hệ thống, có owner và xác minh đối sách. |
| **Hypercare mãi mãi** | Quá tải và phụ thuộc con người để giữ hệ thống chạy. | Cải thiện độ tin cậy, tri thức, tự động hóa và tiêu chí kết thúc. |
| **Chỉ đo thời gian phản hồi đầu tiên** | Trả lời nhanh nhưng vấn đề người dùng chưa được giải quyết. | Theo dõi cả resolution, chất lượng hỗ trợ, outcome và tái mở ticket. |
| **Dùng số cuộc gọi giảm để khẳng định thành công** | Có thể người dùng bỏ cuộc hoặc nhu cầu giảm. | Xem tỷ lệ tự phục vụ, tác vụ hoàn tất và dữ liệu nền. |
| **Không phân biệt version/nhóm rollout** | Khó xác định tính năng nào gây lỗi. | Gắn tín hiệu với release version, cohort/flag và quyền truy cập phù hợp. |

## 20. Bài tập thực hành và hướng dẫn giải

### Bài tập 1 — Phân biệt các mốc của một bản phát hành

Cho tình huống:

1. PR đã merge vào mainline.
2. Unit test và integration test đã đạt; Increment đáp ứng DoD.
3. Mã mới đã deploy lên production nhưng feature flag đang tắt.
4. Nhóm bật flag cho 10% học viên.
5. Sau hai tuần, số học viên phải gọi hỗ trợ về trạng thái đăng ký giảm so với dữ liệu nền.

**Yêu cầu:** xác định đâu là **merge**, **Done/Increment**, **deployment**, **release** và **outcome**. Tại mốc nào support và on-call phải có thông tin thích hợp?

**Gợi ý:** năm mốc lần lượt gần tương ứng năm khái niệm trên. Support và on-call nên được chuẩn bị **trước khi khả năng được mở cho người dùng**, đồng thời cần có thông tin thay đổi khi deployment có thể tác động hệ thống. Outcome đòi hỏi đo và kiểm tra yếu tố ngoài sản phẩm; không suy từ việc bật flag.

### Bài tập 2 — Phân loại phản ánh

Một ngày, support nhận:

- A. “Tôi không tìm thấy danh sách khóa đã đăng ký.”
- B. “Một học viên có thể xem hồ sơ người khác.”
- C. “Tôi muốn nhận SMS nhắc lịch.”
- D. “Đăng ký trả thành công nhưng DB không có bản ghi.”
- E. “Dịch vụ đăng ký đang trả lỗi cho phần lớn học viên.”
- F. “Sau bản nâng cấp, nhân viên không biết xử lý lỗi mới như thế nào.”

**Yêu cầu:** phân loại sơ bộ và nêu đường xử lý. Trường hợp nào cần xem xét ứng cứu ngay thay vì chỉ tạo PBI?

**Gợi ý:** A có thể là câu hỏi hướng dẫn hoặc UX cần làm rõ; B là quan ngại bảo mật có thể nghiêm trọng; C là feature request; D là defect về toàn vẹn dữ liệu, cần đánh giá tác động; E là incident đang xảy ra; F là khoảng trống release readiness/knowledge transfer và có thể kéo theo cải tiến. B, D, E cần triage nghiêm trọng sớm theo chính sách.

### Bài tập 3 — Thiết kế runbook ngắn

Nhóm sắp release chức năng đăng ký khóa miễn phí. Viết một runbook tối đa một trang cho triệu chứng **“Tỷ lệ timeout đăng ký tăng”**.

Runbook phải có:

1. Dấu hiệu kích hoạt và phạm vi.
2. Ba phép kiểm tra ban đầu **chỉ đọc**.
3. Người có quyền quyết định giảm phạm vi/rollback.
4. Điều không được làm để tránh ghi dữ liệu trùng hoặc lộ riêng tư.
5. Kênh escalation.
6. Bằng chứng khôi phục và hướng dẫn support.

**Gợi ý:** xem dashboard API, release version và trạng thái phụ thuộc; kiểm tra correlation ID theo quyền; không hướng dẫn retry vô hạn hay sửa DB thủ công; nếu mất nhất quán dữ liệu hoặc rủi ro riêng tư, chuyển kênh ứng cứu. Điều kiện khôi phục phải có hành vi đăng ký và dữ liệu đúng, không chỉ HTTP 200.

### Bài tập 4 — Phản ứng với sự cố mất phản hồi sau commit

Học viên A báo bấm “Đăng ký” thấy timeout, không rõ đã lưu chưa; sau đó bấm lại. Support nhìn thấy hai request cùng correlation context nhưng chưa xác nhận DB.

**Yêu cầu:**

- Nêu điều support **không nên khuyên người dùng**.
- Liệt kê bằng chứng cần lấy mà không yêu cầu mật khẩu/OTP.
- Giải thích vì sao status code không đủ.
- Đề xuất hai phép kiểm chứng kỹ thuật.
- Nêu khi nào cần escalation sự cố dữ liệu.

**Gợi ý:** không bảo thử lại liên tục. Cần thời điểm, khóa, correlation ID và trạng thái DB qua công cụ có quyền. Test retry/idempotency và transaction/constraint đồng thời. Nếu phát hiện đăng ký trùng, vượt sức chứa hoặc không xác minh được trạng thái có nguy cơ gây hại, chuyển tuyến phù hợp.

### Bài tập 5 — Soạn bản cập nhật sự cố trung thực

Tình huống: một số học viên không đăng ký được; nguyên nhân chưa rõ. Nhóm đã tạm dừng rollout và đang kiểm tra dữ liệu. Không có thời gian khôi phục đáng tin.

Hãy viết **bốn câu** để thông báo tới bộ phận hỗ trợ/người dùng với các phần: tình trạng đã biết, phạm vi và mức bất định, việc đang làm, hành động an toàn người dùng nên thực hiện cùng nhịp cập nhật.

**Ví dụ tham khảo:**

> “Chúng tôi đang kiểm tra một số trường hợp đăng ký không nhận được kết quả rõ ràng sau khi gửi. Phạm vi ảnh hưởng vẫn đang được xác minh, vì vậy chưa thể xác nhận nguyên nhân hoặc thời gian khôi phục. Nhóm đã tạm dừng mở rộng tính năng và đang kiểm tra trạng thái dữ liệu để tránh đăng ký lặp. Nếu bạn gặp tình huống này, vui lòng không gửi liên tiếp nhiều yêu cầu và liên hệ kênh hỗ trợ chính thức để được hướng dẫn xác minh an toàn; thông tin tiếp theo sẽ được cập nhật theo nhịp do kênh hỗ trợ công bố.”

Với sản phẩm thật, phải thay câu chữ và nhịp cập nhật theo bằng chứng, chính sách và người có thẩm quyền truyền thông.

### Bài tập 6 — Đọc chỉ số hỗ trợ

Một đợt phát hành có dữ liệu **minh họa**:

| Chỉ số | Trước cải tiến | Sau cải tiến |
| --- | ---: | ---: |
| Số học viên hoạt động | 2.000 | 3.000 |
| Ticket về trạng thái đăng ký | 80 | 75 |
| Ticket phải chuyển tuyến kỹ thuật | 32 | 15 |
| Thời gian tới phản hồi đầu hữu ích (trung vị) | 18 phút | 8 phút |
| Sự cố sai dữ liệu đã xác nhận | 1 | 2 |

**Câu hỏi:**

1. Có thể kết luận chất lượng toàn diện tăng chỉ vì ticket giảm 80 xuống 75 không?
2. Tính tỷ lệ ticket về trạng thái đăng ký trên một học viên hoạt động ở mỗi kỳ.
3. Chỉ số nào gợi ý hỗ trợ hiệu quả hơn, chỉ số nào cần điều tra rủi ro?
4. Cần thông tin gì trước khi so sánh?

**Đáp án tham khảo:** tỷ lệ trước là **80/2.000 = 4%**, sau là **75/3.000 = 2,5%** theo định nghĩa đơn giản. Chuyển tuyến và phản hồi trung vị có vẻ cải thiện, nhưng **sự cố dữ liệu đã xác nhận tăng từ 1 lên 2** cần xem severity, cách ghi nhận, người dùng bị ảnh hưởng và trạng thái khắc phục. Không dùng tỷ lệ ticket thấp hơn để che một rủi ro dữ liệu nghiêm trọng.

### Bài tập 7 — Đưa phản hồi support vào backlog có thứ tự

Product Goal hiện tại là giúp học viên tự đăng ký khóa miễn phí đáng tin cậy. Có bốn đề nghị:

- A. Học viên tra được trạng thái sau timeout.
- B. SMS quảng bá khóa học mới.
- C. Sửa lỗi có thể ghi đăng ký trùng khi retry.
- D. Thêm cảnh báo khi số đăng ký hiệu lực vượt sức chứa.

Hãy đề xuất thứ tự hoặc **cách nhóm ra quyết định** có giải thích:

- Việc nào thuộc phản ứng khẩn cấp nếu đang gây tác động?
- Việc nào bảo vệ Product Goal rõ nhất?
- Có phụ thuộc giữa sửa nguyên nhân và khả năng quan sát không?
- Đề nghị nào có thể hoãn để kiểm chứng giá trị?
- Ai chịu trách nhiệm ordering trong Scrum?

**Gợi ý:** nếu C đang gây sai dữ liệu, cần ứng cứu và sửa theo rủi ro; D có thể hỗ trợ phát hiện nhưng không thay thế sửa nguyên nhân; A giúp người học tự xác minh, đóng góp trực tiếp Product Goal; B có thể hoãn/khám phá vì ít liên quan mục tiêu hiện hành. **Product Owner** chịu trách nhiệm ordering, với dữ liệu từ Developers, support và vận hành.

### Bài tập 8 — Thiết kế một vòng cải tiến phối hợp

Tình huống: support thường chuyển ticket thiếu log và thời gian; Developers mất nhiều giờ hỏi lại; người dùng không nhận được cập nhật đều đặn. Nhóm muốn cải thiện trong hai tuần.

Hãy lập thử nghiệm **Plan–Do–Check–Act (PDCA)**:

1. Giả thuyết nguyên nhân.
2. Một thay đổi nhỏ về mẫu ticket, runbook hoặc đường escalation.
3. Người phối hợp và giới hạn dữ liệu được phép thu thập.
4. Hai chỉ số flow và một tín hiệu chất lượng.
5. Điều kiện để giữ, sửa hoặc hoàn tác thử nghiệm.

**Gợi ý:** thử mẫu ticket có timestamp, correlation ID và tác động; support được hướng dẫn bằng ví dụ có thể tái hiện; kỹ thuật cung cấp bảng mã lỗi an toàn. Theo dõi work item age, thời gian chờ phản hồi bổ sung, tỷ lệ ticket phải hỏi lại và chất lượng giải quyết. Không thu mật khẩu hoặc dữ liệu nhạy cảm chỉ để tăng tỷ lệ ticket “đủ thông tin”.

### Bài tập 9 — Rollback có giải quyết mọi hậu quả không?

Một bản release thay đổi schema và đã gửi email thông báo cho một số học viên. Sau khi lỗi được phát hiện, nhóm muốn revert mã về bản cũ.

**Yêu cầu:** nêu những điều có thể **không quay lại trạng thái cũ**; xác định kiểm tra trước và sau rollback; giải thích khi nào cần forward fix hoặc xử lý dữ liệu chuyên biệt.

**Gợi ý:** dữ liệu đã ghi theo schema mới, email đã gửi, message trong queue, token hoặc trạng thái hệ thống khác có thể tồn tại sau revert. Cần kiểm tra tương thích, tính nhất quán và quyền, thực hiện qua quy trình được phê duyệt, có kế hoạch theo dõi người dùng bị ảnh hưởng. Rollback code không phải công cụ xóa mọi side effects.

### Bài tập 10 — Trách nhiệm và ranh giới sau bàn giao

Nhóm gồm Product Owner, Developers, Scrum Master, QA, support và on-call. Hãy thảo luận:

| Câu hỏi | Trách nhiệm chính cần làm rõ |
| --- | --- |
| Ai quyết định thay đổi thứ tự Product Backlog? | Product Owner trong Scrum. |
| Ai chịu trách nhiệm tạo Increment đáp ứng DoD? | Developers, trong trách nhiệm chung của Scrum Team. |
| Ai tiếp nhận và hướng dẫn người dùng theo chính sách? | Bộ phận/kênh support được giao. |
| Ai điều phối ứng cứu sự cố đang xảy ra? | Người/đội được chỉ định trong chính sách incident response. |
| Ai quyết định thay đổi production và xử lý dữ liệu nhạy cảm? | Người có thẩm quyền theo quyền hệ thống, quy trình và chuyên môn. |
| Ai giúp Scrum Team tháo impediment và cải thiện cách làm? | Scrum Master hỗ trợ trong phạm vi Scrum. |
| Ai có thể đề xuất test, cảnh báo hoặc FAQ tốt hơn? | Mọi người có thông tin liên quan; cần chủ sở hữu thực hiện và kiểm chứng. |

**Câu hỏi mở:** nếu support giải quyết vấn đề người dùng tốt nhưng bản thân sản phẩm tạo cùng một lỗi mỗi tuần, nhóm nên đánh giá thành công thế nào? Trả lời cần xét **kết quả người dùng, khả năng phòng ngừa và chi phí toàn hệ thống**, không chỉ số ticket đã đóng.

## 21. Checklist trước và sau bàn giao

### Trước khi release

- [ ] Phạm vi thay đổi, đối tượng nhận tính năng, hạn chế và rủi ro được làm rõ.
- [ ] Increment đáp ứng DoD/chuẩn hoàn tất bắt buộc; kiểm chứng đã thực sự chạy và đạt.
- [ ] Có người chịu trách nhiệm phát hành, theo dõi, hỗ trợ và đường escalation.
- [ ] Các thay đổi API/schema, dữ liệu và phụ thuộc quan trọng được kiểm tra tương thích.
- [ ] Có kế hoạch smoke test và bằng chứng bản tích hợp dùng được.
- [ ] Có dashboard/alert đủ thông tin về sức khỏe dịch vụ và hành vi nghiệp vụ.
- [ ] Những rủi ro dữ liệu, bảo mật, quyền và khả năng khôi phục đã được đánh giá phù hợp.
- [ ] Support có release note, FAQ, thông tin lỗi thường gặp và hướng dẫn an toàn.
- [ ] On-call có runbook, quyền được giao và người dự phòng cần thiết.
- [ ] Có ngưỡng dừng/mở rộng rollout và người có quyền quyết định.
- [ ] Có phương án rollback/forward fix/migration phù hợp với dữ liệu và side effects.

### Khi người dùng bắt đầu sử dụng

- [ ] Hệ thống và hành vi nghiệp vụ quan trọng được quan sát, không chỉ HTTP status.
- [ ] Ticket hỗ trợ được tiếp nhận và có đầu mối theo dõi.
- [ ] Những phản ánh về quyền riêng tư, mất dữ liệu hoặc gián đoạn được triage kịp thời.
- [ ] Support không yêu cầu retry rủi ro hoặc dữ liệu nhạy cảm vượt cần thiết.
- [ ] Những vấn đề không chắc trạng thái thật được chuyển tuyến với bằng chứng thích hợp.
- [ ] Khi có incident, điều phối, giảm tác động và thông báo theo chính sách.
- [ ] Không kết thúc incident khi còn chưa xác minh dữ liệu hoặc hành vi cốt lõi.
- [ ] Đối tượng bị ảnh hưởng được hướng dẫn hoặc cập nhật có căn cứ.

### Sau khi dịch vụ ổn định

- [ ] Các trường hợp cần sửa dữ liệu hoặc hỗ trợ riêng có owner và đường giải quyết.
- [ ] Incident đáng kể có hậu kiểm, nguyên nhân được xem xét và hành động phòng ngừa.
- [ ] Runbook/FAQ/alert/test được cập nhật nếu có bài học mới.
- [ ] Defect, vấn đề vận hành và nhu cầu sản phẩm được phân loại nhất quán.
- [ ] Product Owner được cung cấp bằng chứng để sắp thứ tự Product Backlog.
- [ ] Có cách kiểm tra cải tiến làm giảm lỗi/chờ đợi mà không gây tác động phụ.
- [ ] Các metric được đọc theo severity, bối cảnh, phạm vi người dùng và cách đo.
- [ ] Người trực và đội hỗ trợ không phải bù đắp mãi cho lỗi hệ thống bằng quá tải.
- [ ] Người dùng được phản hồi kết quả hoặc trạng thái khi phù hợp.
- [ ] Product Goal và những giả thuyết giá trị được xem lại theo dữ liệu sử dụng thực.

Checklist là **công cụ hướng dẫn đối thoại**, không phải biểu mẫu cố định cho mọi phiên bản. Những thay đổi rủi ro thấp có thể dùng luồng nhẹ hơn; những hệ thống có nghĩa vụ an toàn/tài chính/riêng tư phải giữ kiểm soát phù hợp.

## 22. Tổng kết

Trong phát triển phần mềm Agile, **bàn giao không phải điểm kết thúc trách nhiệm tạo giá trị**. Một Increment có thể đã Done về mặt chất lượng, nhưng sản phẩm còn cần được **mở sử dụng, theo dõi, hỗ trợ, khôi phục khi gặp vấn đề và cải tiến từ phản hồi thực tế**.

Hỗ trợ và vận hành hiệu quả đòi hỏi:

1. **Minh bạch mốc và trách nhiệm:** phân biệt Increment, deploy, release, bàn giao, incident, defect và outcome; biết ai tiếp nhận, ai quyết định, ai hành động.
2. **Chuẩn bị trước release:** release note, runbook, dashboard/alert, smoke test, quyền, kế hoạch khôi phục và thông tin cho support.
3. **Phản ứng đúng khi có sự cố:** ưu tiên bảo vệ người dùng, dùng bằng chứng xác minh trạng thái dữ liệu, escalation theo thẩm quyền và truyền thông trung thực.
4. **Giữ luồng phản hồi mở:** câu hỏi, lỗi, nhu cầu mới và bài học vận hành quay lại quá trình quyết định Product Backlog.
5. **Cải tiến hệ thống:** xem xét nguyên nhân lặp, bổ sung test/quan sát, tối ưu flow và đo kết quả thực tế thay vì chỉ đếm ticket.

Scrum tạo cơ chế mục tiêu, Increment và kiểm tra–thích ứng; Kanban giúp quản lý luồng hỗ trợ, WIP và thời gian chờ; XP cung cấp thực hành kỹ thuật để sửa và tích hợp an toàn; Lean và DevOps giúp các bên **giảm khoảng cách giữa người xây, người vận hành và người nhận giá trị**.

**Sản phẩm chỉ thật sự tiến bộ khi nhóm tiếp tục học sau mỗi lần bàn giao:** người dùng gặp gì, hệ thống vận hành ra sao, những giả định nào đã sai và nên cải thiện điều gì tiếp theo.

### Thuật ngữ chính

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Increment** | Phần sản phẩm tăng thêm đã tích hợp, có thể sử dụng và đáp ứng DoD khi áp dụng Scrum. |
| **Definition of Done (DoD)** | Cam kết về chuẩn chất lượng của Increment trong Scrum. |
| **Deployment** | Đưa phiên bản/cấu hình vào môi trường đích. |
| **Release** | Mở phiên bản hoặc khả năng cho đối tượng sử dụng được xác định. |
| **Operational handover** | Bàn giao thông tin, trách nhiệm và khả năng hỗ trợ/vận hành phù hợp giữa các bên. |
| **Go-live** | Mốc bắt đầu đưa khả năng vào sử dụng thực tế trong phạm vi đã định. |
| **Outcome** | Thay đổi trong kết quả/hành vi người dùng, cần bằng chứng sử dụng. |
| **Support ticket** | Ghi nhận một yêu cầu hoặc phản ánh cần theo dõi và đóng vòng. |
| **Triage** | Xác minh, phân loại tác động và xác định đường xử lý phù hợp. |
| **Severity / urgency / priority** | Mức hậu quả / mức cấp bách / thứ tự nên xử lý trong bối cảnh. |
| **Escalation** | Chuyển vấn đề tới chuyên môn hoặc thẩm quyền cần thiết. |
| **Incident** | Sự kiện gây hoặc có nguy cơ gây gián đoạn/tác động cần ứng cứu theo chính sách. |
| **Incident commander / coordinator** | Chức năng điều phối phản ứng, thông tin và quyết định trong một sự cố. |
| **Service owner** | Đầu mối chịu trách nhiệm về dịch vụ theo mô hình tổ chức vận hành. |
| **On-call** | Người/nhóm được phân công phản ứng với tín hiệu hoặc sự cố theo lịch và quyền đã định. |
| **Runbook** | Hướng dẫn vận hành/ứng cứu có điều kiện, quyền thực hiện và bước kiểm chứng rõ. |
| **Knowledge base** | Nơi lưu hướng dẫn và tri thức phục vụ người dùng/nhân viên hỗ trợ theo quyền. |
| **Workaround** | Giải pháp tạm giúp tiếp tục công việc an toàn khi nguyên nhân chưa được sửa hoàn toàn. |
| **Mitigation** | Biện pháp giảm tác động của sự cố đang xảy ra. |
| **Restoration / recovery** | Khôi phục trạng thái dịch vụ/dữ liệu chấp nhận được theo điều kiện đã định. |
| **Problem management** | Điều tra và xử lý các nguyên nhân hệ thống gây sự cố hoặc lỗi lặp. |
| **Defect** | Sai lệch giữa hành vi thực và điều được xác định là đúng trong bối cảnh. |
| **Post-incident review** | Xem lại sự cố dựa trên bằng chứng để học và giảm khả năng/mức tác động tái diễn. |
| **Observability** | Khả năng suy ra trạng thái hệ thống từ log, metric, trace và tín hiệu phù hợp. |
| **SLI / SLO / SLA** | Chỉ số mức dịch vụ / mục tiêu mức dịch vụ / thỏa thuận mức dịch vụ. |
| **Error budget** | Phần sai lệch cho phép theo một SLO và khung thời gian cụ thể, không phải miễn trừ an toàn. |
| **Feature flag** | Cơ chế điều khiển việc bật/mở tính năng, không thay thế phân quyền. |
| **Canary rollout** | Mở thay đổi có kiểm soát cho một phần nhỏ phạm vi để theo dõi trước khi mở rộng. |
| **Rollback / forward fix** | Quay về phiên bản phù hợp / sửa tiến lên theo quyết định khôi phục an toàn. |
| **Hypercare** | Giai đoạn hỗ trợ và giám sát tăng cường ngay sau thay đổi lớn khi phù hợp. |
| **WIP / cycle time / work item age** | Các chỉ số công việc dở dang và thời gian theo workflow được định nghĩa. |
| **Service Level Expectation (SLE)** | Kỳ vọng thời gian hoàn tất item với xác suất, dùng trong Kanban khi có dữ liệu/phương pháp phù hợp. |
| **Product Backlog** | Danh sách nổi lên và được sắp thứ tự của điều cần thiết để cải thiện sản phẩm trong Scrum. |
| **PDCA** | Plan–Do–Check–Act: lập kế hoạch, thử thay đổi, kiểm tra và điều chỉnh/chuẩn hóa. |


