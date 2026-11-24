# Những giới hạn Scrum cần được hỗ trợ bằng kỹ thuật và bối cảnh tổ chức

Một nhóm phát triển phần mềm tổ chức Sprint Planning, Daily Scrum, Sprint Review và Sprint Retrospective đều đặn. Product Backlog được sắp thứ tự, Sprint Goal được công bố và bảng công việc luôn có nhiều ticket chuyển sang Done. Nhưng mỗi đợt tích hợp lại gây lỗi, kiểm thử hồi quy mất hai tuần, nhóm vận hành không nhận triển khai thường xuyên, còn Product Owner phải chờ nhiều cấp phê duyệt cho một thay đổi nhỏ. Sau ba Sprint, người dùng vẫn chưa có khả năng mới đáng tin cậy để sử dụng.

Nhóm đó có thể đang thực hiện nhiều hoạt động của Scrum, nhưng **các sự kiện Scrum không tự động biến hệ thống kỹ thuật và tổ chức thành một môi trường giao sản phẩm hiệu quả**. Scrum tạo ra cấu trúc để nhìn thấy thực tế, kiểm tra và thích ứng. Nó không quy định đầy đủ cách viết mã, thiết kế kiến trúc, kiểm thử, triển khai, nghiên cứu người dùng, quản lý ngân sách hay thay đổi chính sách giữa các phòng ban.

Chính vì vậy, khi bàn về giới hạn của Scrum, điều quan trọng không phải kết luận “Scrum thiếu nên không dùng được”, cũng không phải đổ mọi thất bại cho “đội chưa làm đúng Scrum”. Cần phân biệt **điều khung Scrum thực sự cung cấp**, **những năng lực phải được bổ sung** và **những trở ngại nằm ngoài quyền kiểm soát trực tiếp của Scrum Team**. Khi kết hợp các yếu tố này phù hợp, Scrum mới giúp tổ chức giao phần mềm hoạt động được, nhận phản hồi sớm và điều chỉnh sản phẩm một cách có trách nhiệm.

Bài thuộc chương **Nền tảng Scrum** trong module **AGILE_DEVELOPMENT**. Bên cạnh Scrum, nội dung liên hệ các thực hành kỹ thuật thường gặp trong Extreme Programming (XP), cách quản lý dòng công việc của Kanban, user story, Product Backlog, đo lường và năng lực vận hành để minh họa Agile là một cách tạo và học từ giá trị, không chỉ là một lịch họp.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả đúng phạm vi của Scrum và lý do khung này được thiết kế **có chủ đích chưa hoàn chỉnh** thay vì là quy trình kỹ thuật toàn diện.
2. Phân biệt một trở ngại do cách thực hành Scrum với trở ngại kỹ thuật, sản phẩm, vận hành hoặc tổ chức.
3. Giải thích vai trò của **Definition of Done**, kiểm thử tự động, tích hợp liên tục, thiết kế có thể thay đổi và triển khai an toàn trong việc tạo Increment hữu ích.
4. Nhận diện những hạn chế khi Product Owner thiếu quyền quyết định, Developers thiếu năng lực liên chức năng hoặc Scrum Master không thể hỗ trợ thay đổi hệ thống.
5. Kết nối Scrum với khám phá nhu cầu người dùng, bảo mật, tuân thủ, DevOps, Kanban và XP mà không coi các thực hành bổ sung là quy định bắt buộc của Scrum.
6. Thiết kế các cải tiến dựa trên bằng chứng cho một Scrum Team đang họp đủ nhưng giao phần mềm chậm hoặc ít giá trị.
7. Trình bày ranh giới trách nhiệm và những điều kiện cần ở cấp tổ chức khi Scrum không thể giải quyết vấn đề chỉ bằng nghi thức trong đội.

## 1. Scrum cung cấp điều gì và không hứa điều gì?

Theo **Scrum Guide 2020**, Scrum là một khung làm việc nhẹ giúp con người, đội nhóm và tổ chức tạo ra giá trị qua giải pháp thích ứng cho các vấn đề phức tạp. Scrum sử dụng chủ nghĩa thực nghiệm (**empiricism**) và tư duy tinh gọn (**lean thinking**). Ba trụ cột của tính thực nghiệm là **minh bạch, kiểm tra và thích ứng**; năm giá trị là **cam kết, tập trung, cởi mở, tôn trọng và can đảm**.

Scrum xác định một cấu trúc tối thiểu để kiểm tra tiến triển của sản phẩm và cách cộng tác. **Scrum không phải bộ hướng dẫn hoàn chỉnh về software engineering, UX research, quản lý hạ tầng hay điều hành toàn tổ chức.** Việc không quy định chi tiết các thực hành ấy là lựa chọn thiết kế của một khung áp dụng được trong nhiều bối cảnh.

### 1.1. Những thành phần cốt lõi

| Thành phần Scrum | Nó giúp giải quyết điều gì? | Nó **không** tự giải quyết điều gì? |
|---|---|---|
| **Scrum Team** gồm Product Owner, Scrum Master, Developers | Tạo đơn vị làm việc hướng một Product Goal với các accountability rõ | Không tự cung cấp đủ kỹ năng kiểm thử, bảo mật, UX, vận hành hay quyền hành tổ chức |
| **Product Goal** gắn với Product Backlog | Định hướng mục tiêu dài hạn để sắp xếp sản phẩm | Không tự chứng minh mục tiêu phản ánh nhu cầu người dùng thực |
| **Sprint Goal** gắn với Sprint Backlog | Tạo sự tập trung và khả năng linh hoạt của kế hoạch trong Sprint | Không tự bảo đảm công việc đã chia đủ nhỏ hoặc ít phụ thuộc |
| **Definition of Done (DoD)** gắn với Increment | Làm minh bạch mức chất lượng cần có để Increment được xem là hoàn tất | Không cung cấp sẵn một chiến lược kiểm thử, kiến trúc hoặc công cụ CI |
| **Sprint** và các sự kiện Scrum | Tạo nhịp kiểm tra, thích ứng và phối hợp thường xuyên | Không biến chức năng chưa tích hợp thành sản phẩm hoạt động được |
| **Product Backlog refinement** | Làm rõ, chia nhỏ và bổ sung thông tin về backlog items | Không tự thay thế nghiên cứu người dùng hoặc giải quyết phụ thuộc với nhà cung cấp |
| **Scrum values và self-management** | Giúp nhóm làm việc dựa trên niềm tin và trách nhiệm | Không tự xóa bỏ chính sách tổ chức ngăn đội ra quyết định |

Scrum Guide xác định khung là **purposefully incomplete**: nó chỉ nêu các phần cần thiết để triển khai lý thuyết Scrum, còn những kỹ thuật và phương pháp khác có thể được sử dụng trong khung. Điều này **không có nghĩa được tự ý bỏ vai trò, sự kiện, artifact hoặc commitment mà vẫn gọi kết quả đó là Scrum đầy đủ**. Cần phân biệt tính tối giản của Scrum với cách triển khai bỏ qua các phần cốt lõi.

### 1.2. Ba trụ cột chỉ có giá trị khi có điều kiện thực hiện

**Minh bạch:** Nếu ticket “Done” nhưng chưa tích hợp, báo cáo đang thiếu minh bạch. Nếu lỗi triển khai bị ẩn để giữ biểu đồ tiến độ đẹp, đội khó ra quyết định đúng.

**Kiểm tra:** Sprint Review có thể diễn ra đều, nhưng nếu Increment không chạy hoặc stakeholders không thấy luồng sử dụng thực, chất lượng kiểm tra thấp. Dashboard chi tiết cũng vô ích nếu dữ liệu sai hoặc không liên quan đến mục tiêu.

**Thích ứng:** Sau khi biết một giả thuyết sai, Product Owner và Scrum Team cần khả năng điều chỉnh backlog, phạm vi hoặc cách làm. Nếu phải chờ ba tháng phê duyệt mọi thay đổi, tổ chức đã hạn chế trụ cột thích ứng.

Ba trụ cột không phải ba cuộc họp. Chúng là **các điều kiện để đưa ra quyết định dựa trên thực tế**. Kỹ thuật, dữ liệu, quyền quyết định và văn hóa làm việc đều ảnh hưởng đến khả năng thực hiện.

### 1.3. Scrum không hứa loại bỏ bất định

Trong sản phẩm phức tạp, người dùng có thể thay đổi nhu cầu; việc tích hợp với hệ thống cũ có thể khó hơn dự đoán; kết quả thử nghiệm có thể trái giả thuyết. Scrum không biến những điều đó thành chắc chắn chỉ nhờ Sprint hai tuần.

Điều Scrum tạo ra là **cơ hội học thường xuyên và thích ứng**. Nếu một Sprint không giao được Increment đạt DoD, đó là thông tin quan trọng để kiểm tra năng lực và trở ngại; không phải lý do hợp thức hóa một Increment chưa hoàn tất.

## 2. Nhận diện giới hạn của khung và vấn đề do cách triển khai

Một đội thường gắn nhãn “Scrum không hiệu quả” cho mọi vấn đề. Cách chẩn đoán đó quá rộng. Hãy phân biệt ba loại:

| Loại vấn đề | Ví dụ | Câu hỏi cần đặt |
|---|---|---|
| **Cách dùng Scrum chưa đúng** | Không có Product Goal, Sprint Review chỉ là báo cáo cá nhân, DoD bị bỏ qua | Thành phần Scrum hiện có được hiểu và thực hiện đúng mục đích chưa? |
| **Năng lực bổ trợ còn thiếu** | Không có kiểm thử hồi quy, tích hợp mỗi tháng, thiếu khả năng quan sát production | Kỹ thuật hoặc kỹ năng nào cần phát triển để tạo Increment hữu ích? |
| **Rào cản của hệ thống tổ chức** | Product Owner không được quyền ưu tiên, QA là hàng đợi tập trung, phê duyệt triển khai cố định mỗi quý | Chính sách, phân quyền hoặc phụ thuộc nào vượt khả năng tự xử lý của đội? |

Ba loại có thể xuất hiện đồng thời. Ví dụ, một đội không có DoD đáng tin (**cách áp dụng Scrum**) vì tổ chức không đầu tư môi trường kiểm thử (**năng lực và tổ chức**). Chỉ sửa tên cột trên bảng Scrum không giải quyết được gốc vấn đề.

### 2.1. Khi tổ chức “đủ sự kiện” nhưng thiếu khả năng giao hàng

Những tín hiệu đáng chú ý:

- Sprint Planning kết thúc bằng danh sách task nhưng không có mục tiêu chung có ý nghĩa.
- Daily Scrum trở thành buổi báo cáo “hôm qua tôi làm gì” cho quản lý, không giúp Developers điều chỉnh kế hoạch.
- Sprint Review chỉ chiếu slide hoặc demo bằng dữ liệu giả, không kiểm tra Increment thực tế.
- Nhiều Product Backlog Items được ghi Done nhưng chưa đáp ứng DoD.
- Các hạng mục không hoàn tất bị chuyển từ Sprint này sang Sprint khác vì phụ thuộc chưa giải quyết.
- Thời gian chờ QA, kiểm thử bảo mật hoặc triển khai dài hơn thời gian viết mã.
- Người dùng chỉ được tiếp cận sản phẩm sau nhiều tháng và phản hồi đến quá muộn.

Không phải mỗi tín hiệu đều chứng minh Scrum bị dùng sai. Chúng là **đầu mối điều tra**, cần xác minh bằng dòng công việc, tình trạng chất lượng và trải nghiệm người dùng.

## 3. Giới hạn kỹ thuật số một: Scrum không viết mã và kiểm thử thay đội

Scrum Guide yêu cầu Increment đáp ứng **Definition of Done**, nhưng không yêu cầu mọi đội dùng TDD, một ngôn ngữ cụ thể, một mô hình kiến trúc hoặc một công cụ CI/CD. Đó là điểm mạnh về khả năng thích ứng, đồng thời tạo nhu cầu lựa chọn **thực hành kỹ thuật phù hợp với sản phẩm**.

Nếu code của các thành viên không thể tích hợp, bài kiểm thử không đáng tin hoặc thay đổi nhỏ thường gây hồi quy, Sprint ngắn chỉ khiến vấn đề xuất hiện thường xuyên hơn. Không có nghi thức Scrum nào tự sửa được một hệ thống mã nguồn thiếu khả năng thay đổi.

### 3.1. Definition of Done là tiêu chuẩn chất lượng, không phải nhãn trạng thái

**DoD** mô tả chính thức trạng thái của Increment khi nó đáp ứng các tiêu chuẩn chất lượng áp dụng cho sản phẩm. Trong Scrum:

- Khi một Product Backlog Item không đáp ứng DoD, nó **không thể được coi là một phần của Increment**.
- Increment phải **có thể sử dụng được**; một Sprint có thể tạo nhiều Increment.
- Không cần đợi Sprint Review để phát hành Increment; Review không phải cổng phê duyệt phát hành.
- Nếu tổ chức có DoD tiêu chuẩn, Scrum Team phải áp dụng như mức tối thiểu; nếu không, Scrum Team tạo DoD phù hợp với sản phẩm.
- Khi nhiều Scrum Team cùng làm trên một sản phẩm, các Increment phải được tích hợp và các đội phải cùng tuân theo một DoD chung.

Ví dụ **DoD minh họa** cho một nền tảng học trực tuyến:

| Điều kiện chất lượng | Bằng chứng thường cần |
|---|---|
| Mã và cấu hình đã được tích hợp vào phiên bản sản phẩm cần kiểm tra | Build/tích hợp thành công; thay đổi nằm đúng nhánh hoặc artifact |
| Các tiêu chí chấp nhận quan trọng đã được kiểm chứng | Kết quả kiểm thử thích hợp, gồm trường hợp thành công và lỗi |
| Không còn vi phạm yêu cầu bảo mật áp dụng cho lát cắt | Kiểm tra phân quyền, dữ liệu nhạy cảm và các kiểm soát theo rủi ro |
| Hành vi không gây hồi quy không chấp nhận được | Bộ kiểm thử hồi quy phù hợp, theo dõi vấn đề còn mở |
| Khả năng truy cập và hiệu năng liên quan đã được kiểm tra | Kiểm tra với tiêu chuẩn và điều kiện hỗ trợ đã công bố |
| Có khả năng vận hành và xác định lỗi ở mức cần thiết | Logging, monitoring, cấu hình và khả năng khôi phục phù hợp |
| Increment có thể kiểm tra/sử dụng theo phạm vi công bố | Luồng UI–API–dữ liệu chạy với quyền và trạng thái đúng |

Đây **không phải DoD bắt buộc cho mọi Scrum Team**. Sản phẩm y tế, ngân hàng, trò chơi hay hệ thống nội bộ có tiêu chuẩn khác nhau. Nếu một mục trong bảng không áp dụng, đội cần nói rõ lý do; nếu có một yêu cầu tuân thủ bổ sung, đội phải đưa vào chất lượng cần thiết.

**DoD không đồng nghĩa:** “Đã code xong”, “đã giao cho QA”, “đã tạo pull request” hoặc “đã chạy demo được một đường vui vẻ”. Một item chỉ Done khi đạt mức chất lượng đã công bố.

### 3.2. Chiến lược kiểm thử là phần Scrum không tự chỉ định

Scrum cho biết cần một Increment chất lượng; đội phải quyết định **kiểm chứng bằng gì**. Một chiến lược kiểm thử có thể kết hợp:

| Lớp kiểm chứng | Đóng góp | Giới hạn |
|---|---|---|
| Unit tests | Bắt lỗi logic và trường hợp biên ở phạm vi nhỏ | Không chứng minh tích hợp toàn hệ thống |
| Contract/API tests | Kiểm tra giao tiếp và quy tắc giữa các thành phần | Không thay thế trải nghiệm UI hoặc quyền truy cập xuyên suốt |
| Integration tests | Phát hiện lỗi khi dữ liệu, dịch vụ hoặc thành phần hoạt động cùng nhau | Môi trường thử cần đại diện cho rủi ro thực |
| End-to-end tests | Xác nhận luồng quan trọng qua nhiều thành phần | Có thể chậm và dễ không ổn định nếu lạm dụng |
| Kiểm thử khám phá | Phát hiện cách dùng ngoài giả định hoặc những trải nghiệm khó chịu | Cần kỹ năng, bối cảnh và ghi nhận kết quả phù hợp |
| Kiểm tra bảo mật, hiệu năng, khả năng truy cập | Bảo vệ các thuộc tính chất lượng không thể suy ra từ luồng happy path | Phải được định nghĩa theo hệ thống, loại rủi ro và tiêu chuẩn áp dụng |

**Không có tỷ lệ unit/integration/E2E cố định được Scrum quy định.** Một kim tự tháp kiểm thử có thể là heuristic hữu ích, nhưng chất lượng chiến lược phụ thuộc vào rủi ro thực, kiến trúc và năng lực đội.

### 3.3. TDD và BDD giúp thu hẹp vòng phản hồi

Trong **Test-Driven Development (TDD)**, nhóm thường theo vòng *Red → Green → Refactor*: viết một kiểm thử nhỏ thất bại, bổ sung mã để đáp ứng, rồi cải thiện cấu trúc trong khi các kiểm thử vẫn đạt. Nó có thể làm rõ hành vi và giảm rủi ro khi thay đổi code.

Trong **Behavior-Driven Development (BDD)** hoặc *Specification by Example*, các bên trao đổi ví dụ hành vi nghiệp vụ theo ngôn ngữ chung, chẳng hạn Given–When–Then:

~~~gherkin
Feature: Dang ky khoa hoc mien phi

  Scenario: Hoc vien du dieu kien ghi danh
    Given hoc vien A da dang nhap
    And khoa hoc X la khoa mien phi dang mo ghi danh
    When A yeu cau ghi danh vao X
    Then he thong tao ghi danh hop le cho A va X
    And A co the truy cap noi dung duoc phep cua X

  Scenario: Khong duoc ghi danh trung
    Given hoc vien A da ghi danh khoa X
    When A gui lai yeu cau ghi danh X
    Then he thong khong tao ghi danh trung
    And quyen truy cap cua A van dung
~~~

Ví dụ trên là **đặc tả hành vi**, chưa phải bằng chứng test đã thực thi. BDD giúp ba góc nhìn nghiệp vụ, kỹ thuật và kiểm thử hiểu cùng một điều; TDD hỗ trợ xây phần logic đáng tin. Chúng **không phải sự kiện hoặc quy tắc bắt buộc của Scrum**, nhưng có thể tăng chất lượng của Increment được tạo trong Sprint.

### 3.4. Refactoring và thiết kế có khả năng thay đổi

Nếu mỗi yêu cầu mới buộc sửa hàng chục thành phần không liên quan, thời gian hoàn tất dần tăng. Sprint Review có thể phát hiện nhu cầu cần thay đổi, nhưng đội không thể thích ứng an toàn nếu cấu trúc hệ thống khó sửa.

**Refactoring** cải thiện cấu trúc nội bộ mà không chủ đích đổi hành vi bên ngoài; cần bộ kiểm thử đủ tin để phát hiện hồi quy. Một số thực hành hỗ trợ:

- Chia ranh giới trách nhiệm giữa các thành phần theo hành vi và dữ liệu thực.
- Loại bỏ phụ thuộc không cần thiết, mã trùng lặp và các thiết kế gây khó kiểm thử.
- Lập trình cặp hoặc cùng xem mã khi quyết định có rủi ro cao.
- Giữ thông tin kiến trúc và những quyết định quan trọng có thể tra cứu.
- Đưa cải tiến kỹ thuật vào dòng công việc thường xuyên, tránh luôn trì hoãn tới “Sprint dọn nợ” không bao giờ đến.

Không nên tách “phát triển tính năng” khỏi “duy trì chất lượng mã” như hai nghĩa vụ đối lập. Khả năng thay đổi của hệ thống ảnh hưởng trực tiếp đến tốc độ giao giá trị trong các Sprint sau.

## 4. Giới hạn kỹ thuật số hai: Scrum không tự tạo khả năng tích hợp và phát hành

**Sprint ngắn không đồng nghĩa có thể phát hành thường xuyên.** Nếu mỗi Sprint nhóm viết mã nhưng chỉ tích hợp một lần mỗi tháng, mức kiểm tra thực tế vẫn chậm. Nếu pipeline triển khai thiếu kiểm soát hoặc phải đợi hàng tuần để đặt lịch môi trường, Increment khó đến được người dùng đúng lúc.

### 4.1. Tích hợp liên tục giúp phát hiện lỗi sớm

**Continuous Integration (CI)** thường kết hợp những thay đổi nhỏ vào phiên bản chung thường xuyên và kiểm tra tự động phù hợp. Những dấu hiệu tốt:

- Build có thể lặp lại, không phụ thuộc thủ công vào một máy cá nhân.
- Những thay đổi thường xuyên được tích hợp; xung đột được phát hiện khi còn nhỏ.
- Kiểm thử tự động liên quan chạy sớm và kết quả được xem xét.
- Test thất bại hoặc bị bỏ qua được ghi nhận minh bạch; pipeline “xanh” không che lỗi quan trọng.
- Đội có khả năng quay về phiên bản ổn định khi cần.

CI không bảo đảm sản phẩm đúng hoàn toàn, nhưng làm giảm độ trễ giữa **đưa thay đổi vào hệ thống** và **biết thay đổi đó có làm hỏng điều gì không**.

### 4.2. Phân biệt tích hợp, triển khai và phát hành

| Trạng thái | Ý nghĩa | Có tự đồng nghĩa tạo giá trị người dùng không? |
|---|---|---|
| **Mã đã tích hợp** | Thay đổi kết hợp với mã sản phẩm và được kiểm tra theo điều kiện xác định | Chưa; có thể chưa hoàn tất Increment |
| **Increment đạt DoD** | Phần mềm đạt chuẩn chất lượng, có thể sử dụng theo phạm vi | Có khả năng cung cấp giá trị, nhưng chưa chắc người dùng đã tiếp cận |
| **Triển khai (deployment)** | Phiên bản được đưa lên môi trường vận hành/kiểm tra | Không nhất thiết; tính năng có thể chưa được bật |
| **Phát hành (release)** | Khả năng được cung cấp cho đối tượng sử dụng phù hợp | Có cơ hội tạo giá trị và nhận phản hồi thực |
| **Outcome được quan sát** | Người dùng thực sự đạt được điều hữu ích | Cần dữ liệu và bối cảnh sử dụng để kết luận |

Một đội có thể **deploy** thường xuyên nhưng chỉ **release** một số khả năng theo lịch, ví dụ dùng *feature flag*. Ngược lại, một Increment đã đạt DoD có thể chưa triển khai ra production do điều kiện vận hành hoặc quy định, nhưng việc trì hoãn đó phải được hiểu và quản lý, không được dùng để gọi phần mềm chưa tích hợp là hoàn tất.

### 4.3. Continuous Delivery và kiểm soát phát hành

**Continuous Delivery** hướng tới khả năng giữ phần mềm ở trạng thái có thể phát hành an toàn sau những thay đổi nhỏ; **Continuous Deployment** thường mô tả việc tự động đưa thay đổi đạt điều kiện vào production. Tổ chức không bắt buộc phải tự động phát hành mọi commit mới có thể làm Scrum tốt.

Tùy rủi ro, cơ chế hỗ trợ có thể gồm:

- Pipeline triển khai chuẩn hóa và quyền truy cập phù hợp.
- Kiểm thử hồi quy và các cổng bảo mật có ý nghĩa.
- Phát hành theo giai đoạn (*canary*, nhóm thử nghiệm, feature flag).
- Quan sát tỷ lệ lỗi, thời gian phản hồi, tác động người dùng.
- Khả năng rollback hoặc roll-forward an toàn; với dữ liệu có trạng thái, cần kế hoạch khôi phục tương ứng.
- Nhật ký thay đổi và chứng cứ phê duyệt khi sản phẩm phải tuân thủ.

Không bỏ kiểm soát bắt buộc chỉ để tăng tần suất release. Mục tiêu là **giảm rủi ro và thời gian chờ bằng tự động hóa, chuẩn hóa và bằng chứng phù hợp**, không thay sự kiểm soát có ý nghĩa bằng tốc độ bề mặt.

### 4.4. Quan sát sản phẩm sau khi phát hành

Scrum Review có thể kiểm tra Increment trước mặt stakeholders. Nhưng nếu không có dữ liệu hoạt động và phản hồi thực tế, nhóm khó biết:

- Người dùng có tìm thấy khả năng mới không?
- Luồng quan trọng có hoàn tất với tỉ lệ mong muốn không?
- Có lỗi hoặc độ trễ tăng sau phát hành không?
- Có nhóm người dùng bị ảnh hưởng xấu hơn những nhóm khác không?
- Cần điều chỉnh Product Backlog hay thiết kế kỹ thuật ở đâu?

Các thực hành **observability** như logging có cấu trúc, metrics, traces, cảnh báo và điều tra sự cố hỗ trợ vòng phản hồi ấy. Đội cần bảo vệ thông tin cá nhân, bí mật và dữ liệu nhạy cảm khi ghi log. **Một dashboard nhiều số liệu nhưng không dẫn tới quyết định cũng chưa phải phản hồi hiệu quả.**

## 5. Giới hạn sản phẩm: Scrum không tự biết người dùng cần gì

Một Product Backlog minh bạch chưa chắc là backlog có giá trị. Nếu Product Owner chỉ nhận danh sách yêu cầu từ lãnh đạo, không gặp người dùng, không kiểm tra giả thuyết và không thể đổi ưu tiên, Scrum Team có thể xây đúng kế hoạch nhưng sai vấn đề.

### 5.1. Discovery và delivery phải liên hệ với nhau

**Product discovery** bao gồm các cách tìm hiểu vấn đề, nhu cầu và rủi ro giải pháp: phỏng vấn, quan sát tác vụ, phân tích hành vi, prototype, thử nghiệm có giới hạn hoặc kiểm tra khả năng sử dụng.

**Product delivery** tập trung biến những lựa chọn phù hợp thành phần mềm đạt chất lượng và có thể dùng. Hai loại hoạt động nên trao đổi thường xuyên:

~~~mermaid
flowchart TD
    A["Nhu cầu và mục tiêu người dùng"] --> B["Giả thuyết giá trị / giải pháp"]
    B --> C["Làm rõ và ưu tiên Product Backlog"]
    C --> D["Tạo Increment đạt Definition of Done"]
    D --> E["Tiếp cận người dùng và nhận phản hồi"]
    E --> F{"Giả thuyết còn phù hợp?"}
    F -->|Có| G["Điều chỉnh hoặc mở rộng có kiểm soát"]
    F -->|Không / chưa đủ bằng chứng| H["Nghiên cứu, thử phương án khác"]
    H --> B
    G --> C
~~~

Không phải mọi nghiên cứu phải diễn ra trong một Sprint tách biệt, cũng không phải mọi hoạt động discovery phải tạo một Increment dùng được. Nhưng Product Owner và Scrum Team cần **bằng chứng để quyết định giá trị**, thay vì giả định số ticket hoàn tất chính là outcome.

### 5.2. Phân biệt output với outcome

Ví dụ:

| Đầu ra (output) | Kết quả mong muốn (outcome) | Câu hỏi thực tế |
|---|---|---|
| Màn hình onboarding mới | Học viên mới bắt đầu bài học đầu tiên dễ hơn | Tỉ lệ tự hoàn tất bước đầu có cải thiện không? |
| Chatbot hỗ trợ | Người dùng tự xử lý vấn đề thông thường nhanh hơn | Vấn đề có thật sự được giải quyết, hay chỉ tăng số lượt chat? |
| Bộ lọc khóa học | Học viên tìm khóa phù hợp ít phải thử lại | Thời gian tìm và tỉ lệ chọn đúng có thay đổi không? |
| Pipeline tự động hóa | Đội giao thay đổi nhỏ an toàn và thường xuyên hơn | Lỗi sau triển khai, thời gian sửa và khả năng phát hành thay đổi thế nào? |

Đầu ra đạt DoD là điều quan trọng về giao hàng; outcome cần được quan sát riêng. Đừng buộc một outcome dài hạn trở thành điều kiện DoD của một item đơn lẻ, vì nhóm có thể không kiểm soát được thời gian quan sát. Đồng thời không gọi một sản phẩm thành công chỉ vì tính năng được bàn giao.

### 5.3. Scrum không thay thế chuyên môn UX và tiếp cận người dùng

User story “là học viên, tôi muốn xem tiến độ học” không bảo đảm thiết kế dễ hiểu. Đội có thể cần:

- Khảo sát mô hình tư duy người dùng.
- Thử luồng với người dùng phù hợp, kể cả người sử dụng công nghệ hỗ trợ.
- Thiết kế phản hồi khi thao tác lỗi, tải chậm, hoặc dữ liệu không có.
- Kiểm tra ngôn ngữ, biểu tượng và những hành vi gây hiểu nhầm.
- Phân tích phản hồi của người dùng bị bỏ dở giữa hành trình.

Scrum giúp đội có cơ hội kiểm tra và thích ứng. **Phương pháp khám phá và thiết kế cần được lựa chọn có chủ đích**, không tự xuất hiện chỉ vì đã có Sprint Review.

## 6. Giới hạn tổ chức: Scrum Team cần quyền hạn tương xứng trách nhiệm

Scrum Team được thiết kế **cross-functional** và **self-managing**: có các kỹ năng cần thiết để tạo giá trị mỗi Sprint, tự quyết ai làm gì, khi nào và bằng cách nào trong phạm vi nhóm. Nhưng một cơ cấu tổ chức chia người theo chức năng, phê duyệt tập trung và ưu tiên cạnh tranh có thể làm hai đặc điểm ấy khó thực hiện.

### 6.1. Một bảng so sánh trách nhiệm và điều kiện thực thi

| Accountability trong Scrum | Vai trò trọng tâm | Điều kiện tổ chức thường cần hỗ trợ |
|---|---|---|
| **Product Owner** | Tối đa hóa giá trị sản phẩm, phát triển/truyền đạt Product Goal và quản lý Product Backlog hiệu quả | Quyền ưu tiên đủ rõ, tiếp cận người dùng/dữ liệu, kênh quyết định với stakeholders, tránh nhiều “Product Owner” cùng áp thứ tự khác nhau |
| **Developers** | Tạo Increment có thể sử dụng mỗi Sprint; lập kế hoạch Sprint, duy trì chất lượng, thích ứng kế hoạch và phối hợp chuyên môn | Kỹ năng liên chức năng, quyền tiếp cận môi trường, công cụ kiểm thử, điều kiện tích hợp và khả năng xử lý phụ thuộc |
| **Scrum Master** | Chịu trách nhiệm về hiệu quả của Scrum Team; giúp Scrum được hiểu và thực hiện, hỗ trợ đội và tổ chức tháo trở ngại | Quyền kết nối người ra quyết định, sự hợp tác của lãnh đạo, thời gian để cải tiến hệ thống thay vì chỉ điều phối cuộc họp |
| **Scrum Team** | Tập trung Product Goal, tạo Increment có giá trị, hữu ích mỗi Sprint | Mục tiêu thống nhất, khả năng tự quản lý và chính sách tổ chức không liên tục phá vỡ sự tập trung |

**Product Owner không phải người duy nhất “chịu trách nhiệm về giá trị” theo nghĩa tự thực hiện mọi thứ; Scrum Master không phải người quản lý giao task; Developers không chỉ là người viết mã.** Mỗi accountability khác nhau nhưng phục vụ cùng Product Goal.

### 6.2. Product Owner có danh nghĩa nhưng không có thực quyền

Một dấu hiệu là Product Owner luôn nói “tôi sẽ hỏi cấp trên” cho mọi thay đổi nhỏ, trong khi năm phòng ban khác nhau có quyền đưa yêu cầu trực tiếp cho Developers.

Hệ quả:

- Product Backlog không thể duy trì một thứ tự có ý nghĩa.
- Sprint Goal bị chen ngang bởi nhiều yêu cầu “khẩn”.
- Nhóm thiếu tiêu chí ra quyết định về giá trị và phạm vi.
- Những bài học từ Sprint Review không dẫn đến điều chỉnh thực tế.

Giải pháp không chỉ là huấn luyện Product Owner viết user story hay tổ chức thêm refinement. **Tổ chức cần làm rõ quyền quyết định, giới hạn ủy quyền và cơ chế xử lý xung đột ưu tiên.** Những trường hợp liên quan pháp lý, ngân sách hay an toàn có thể vẫn cần thẩm quyền khác, nhưng cách đưa quyết định phải minh bạch và kịp thời.

### 6.3. Nhóm mang tên liên chức năng nhưng còn hàng đợi phòng ban

Ví dụ một Scrum Team có frontend, backend và QA, nhưng toàn bộ kiểm thử bảo mật phải qua một đơn vị được đặt lịch trước bốn tuần; việc triển khai phải chờ nhóm vận hành theo chu kỳ hàng tháng.

Không thể giải quyết chỉ bằng Daily Scrum. Các lựa chọn có thể gồm:

- Đầu tư kỹ năng và công cụ để đội tự xử lý nhiều kiểm tra thông thường trong phạm vi được phép.
- Đưa chuyên gia vào hoạt động refinement và thiết kế sớm để tránh chờ đến cuối.
- Tạo cơ chế cung cấp dịch vụ rõ cho những kiểm tra bắt buộc của bộ phận chuyên trách.
- Dùng kiểm soát tự động hoặc mẫu chuẩn đã được phê duyệt để giảm việc phê duyệt lặp không cần thiết.
- Thống nhất lịch và điều kiện với đơn vị phụ thuộc ngay khi lập kế hoạch.
- Đưa trở ngại kéo dài lên cấp tổ chức có quyền sửa chính sách thay vì chỉ chuyển item qua Sprint kế tiếp.

**Không nhất thiết mọi Scrum Team phải có chuyên gia toàn thời gian của mọi lĩnh vực.** Điều quan trọng là có đủ kỹ năng để tạo Increment hữu ích và cách phối hợp với những chuyên môn không thể đặt trọn trong đội.

### 6.4. Lãnh đạo và cơ chế khuyến khích có thể chống lại Scrum

Nếu mỗi phòng ban được thưởng theo mức sử dụng nhân sự hoặc số ticket hoàn tất, các thành viên dễ ưu tiên “ai cũng bận” hơn “luồng người dùng được hoàn tất”. Nếu cá nhân bị phạt mỗi khi báo cáo rủi ro, minh bạch sẽ giảm. Nếu quản lý yêu cầu kế hoạch chi tiết bất biến trước cả khi khám phá nhu cầu, thích ứng trở nên rất khó.

Lãnh đạo có thể hỗ trợ bằng cách:

1. Thống nhất mục tiêu sản phẩm và quyền ưu tiên rõ ràng.
2. Đánh giá **giá trị và chất lượng**, không chỉ sự bận rộn của từng bộ phận.
3. Cho phép đội công khai dự báo, rủi ro, lỗi và dữ liệu chưa chắc chắn.
4. Đầu tư vào công cụ, môi trường kiểm thử, kiến trúc và năng lực vận hành.
5. Giải quyết phụ thuộc liên đội ở cấp có thẩm quyền.
6. Tôn trọng tính tự quản lý trong cách Developers đạt Sprint Goal.

Tự quản lý không phải bỏ mặc. Cần **mục tiêu, giới hạn, thông tin và quyền hành** đi cùng trách nhiệm.

## 7. Giới hạn về phụ thuộc, kiến trúc và nhiều đội làm một sản phẩm

Scrum Team nên có kỹ năng đủ để tạo giá trị mỗi Sprint, nhưng sản phẩm lớn có thể liên quan nhiều nhóm, hệ thống dùng chung, cơ sở dữ liệu cũ hoặc nhà cung cấp ngoài. Scrum không tự cung cấp một kiến trúc cho phép từng đội giao Increment độc lập.

### 7.1. Phụ thuộc dài làm lộ giới hạn của Sprint ngắn

Một luồng đăng ký khóa học có thể đi qua:

~~~mermaid
flowchart LR
    A["Người học ghi danh"] --> B["Dịch vụ tài khoản"]
    B --> C["Dịch vụ thanh toán"]
    C --> D["Sự kiện xác nhận"]
    D --> E["Cấp quyền khóa học"]
    E --> F["Truy cập bài học"]
~~~

Nếu mỗi hệ thống do một đội khác nhau sở hữu, chỉ đặt Sprint Goal trong một đội không đủ để bảo đảm luồng hoạt động. Cần thống nhất **hợp đồng giao tiếp, dữ liệu, kiểm thử tích hợp, môi trường và quy tắc xử lý lỗi** giữa các bên.

Một số cách giảm phụ thuộc:

- Chia backlog theo **khả năng người dùng đầu-cuối** thay vì chỉ theo tầng hệ thống.
- Thống nhất API contract và kiểm thử tương thích sớm.
- Làm rõ nguồn dữ liệu đáng tin và trách nhiệm khi trạng thái không nhất quán.
- Ưu tiên tích hợp thường xuyên, tránh “tích hợp tất cả” ở cuối chương trình.
- Ghi rõ quyết định cần đưa ra và người có thẩm quyền ở các hệ thống chung.
- Đánh giá ranh giới kiến trúc khi nhiều thay đổi nhỏ liên tục phải chờ cùng một đội.

### 7.2. Khi nhiều Scrum Team cùng phát triển một sản phẩm

Theo Scrum Guide, nhiều Scrum Team làm trên cùng một sản phẩm cần **chia sẻ cùng Product Goal, Product Backlog và Product Owner**. Công việc của họ phải tạo được **Increment tích hợp**, đáp ứng cùng một DoD áp dụng cho sản phẩm.

Điều này đặt ra những yêu cầu kỹ thuật và tổ chức cụ thể: khả năng tích hợp giữa các đội, làm rõ phụ thuộc, chiến lược kiểm thử, trách nhiệm sở hữu chung và kênh ưu tiên thống nhất. Một cuộc họp “Scrum of Scrums” có thể giúp phối hợp trong một số tổ chức nhưng **không phải sự kiện bắt buộc của Scrum** và không thay thế tính tích hợp thực tế.

Thêm tầng quản trị, chức danh hoặc nghi thức không tự giải quyết thiết kế hệ thống quá phụ thuộc. Quy mô càng lớn càng cần kiểm tra xem việc bổ sung phối hợp **giảm hay chỉ chuyển chỗ thời gian chờ**.

### 7.3. Kiến trúc và hạ tầng không được biến thành “việc vô hình”

Cải thiện khả năng backup, phân quyền, quan sát hệ thống hoặc quy trình build có thể không tạo nút mới trên UI nhưng giảm rủi ro và tạo năng lực giao hàng. Product Owner và Developers cần nhìn thấy những hạng mục này trong lựa chọn sản phẩm/kỹ thuật ở mức phù hợp.

Ví dụ, nếu mọi thay đổi của luồng đăng ký đều cần sửa một module dùng chung dễ gây lỗi, việc refactoring và bổ sung kiểm thử có thể là đầu tư cần thiết để tạo Increment an toàn. Tránh coi toàn bộ công việc kỹ thuật là “không tạo giá trị”, nhưng cũng cần nêu **rủi ro hoặc năng lực** mà khoản đầu tư nhằm cải thiện và cách kiểm chứng.

## 8. Giới hạn về an toàn, bảo mật và quy định

Trong các hệ thống tài chính, giáo dục có dữ liệu cá nhân, y tế, công nghiệp hoặc sản phẩm có nghĩa vụ đặc biệt, đội không thể chỉ dựa trên ý tưởng “cứ release nhanh rồi sửa sau”. Scrum cũng không cho phép bỏ qua luật, hợp đồng hoặc chuẩn an toàn.

### 8.1. Scrum không tự tạo bằng chứng tuân thủ

Scrum xác định sự minh bạch và DoD, nhưng quy trình thực tế có thể cần:

| Lĩnh vực | Bằng chứng hoặc hoạt động hỗ trợ |
|---|---|
| Quyền truy cập và bảo mật | Mô hình đe dọa, kiểm tra phân quyền, bí mật được quản lý phù hợp |
| Dữ liệu cá nhân | Phân loại dữ liệu, giới hạn thu thập, kiểm soát truy cập và lưu trữ theo chính sách |
| Khả năng truy cập | Kiểm tra tiêu chuẩn áp dụng, thử thao tác bàn phím và công nghệ hỗ trợ |
| Thay đổi quan trọng | Truy vết yêu cầu–test–kết quả, phê duyệt có thẩm quyền, kiểm soát phiên bản |
| Khả năng khôi phục | Kế hoạch rollback/roll-forward, sao lưu và diễn tập khi phù hợp |
| Vận hành | Giám sát, quản lý sự cố, đánh giá rủi ro khi triển khai |

Những bằng chứng này có thể được xây **liên tục trong Sprint**. Việc dồn toàn bộ kiểm định đến cuối dự án vừa gây thời gian chờ vừa làm phát hiện lỗi muộn.

### 8.2. Kết hợp kiểm soát với luồng phát triển

Một cách tiếp cận thực dụng:

1. Làm rõ điều kiện bắt buộc ngay khi refinement, không chờ đến lúc chuẩn bị phát hành.
2. Cùng chuyên gia phân loại rủi ro và lựa chọn phép kiểm chứng.
3. Tự động hóa các kiểm tra lặp có thể tự động hóa một cách đáng tin.
4. Ghi lại bằng chứng theo phiên bản, môi trường và tiêu chí liên quan.
5. Giữ các phê duyệt bắt buộc bởi vai trò đúng thẩm quyền.
6. Đưa thời gian chờ hoặc rủi ro tuân thủ vào dự báo thay vì giả định nó bằng không.

**Không nên gán tất cả sự chậm trễ cho “quan liêu”.** Một số kiểm soát bảo vệ người dùng và tổ chức là cần thiết. Cần cải tiến **cách thực hiện kiểm soát**, phân biệt yêu cầu bắt buộc với bước lặp không tạo thêm an toàn.

### 8.3. Một ngoại lệ không được giải quyết bằng cách đổi nhãn Done

Giả sử kiểm thử phân quyền phát hiện tài khoản A có thể xem dữ liệu học tập của B. Nhóm muốn phát hành đúng lịch và đánh dấu ticket Done với lý do “sẽ sửa Sprint sau”.

Nếu lỗi vi phạm DoD hoặc điều kiện chất lượng bắt buộc, hạng mục **chưa được xem là Done trong Scrum**. Người có quyền quản trị rủi ro có thể cần quyết định về việc dừng, thu hẹp phạm vi hoặc phương án dự phòng, nhưng không nên biến việc đổi trạng thái trên bảng thành bằng chứng phần mềm đã an toàn.

## 9. Giới hạn đo lường: Scrum không tự xác định chỉ số thành công

Scrum không bắt buộc dùng story point, velocity, burn-down chart hoặc một số lượng ticket chuẩn cho mỗi Sprint. Các công cụ này có thể có ích trong bối cảnh phù hợp, nhưng không thay thế bằng chứng về Increment và kết quả người dùng.

### 9.1. Ba lớp tín hiệu cần xem cùng nhau

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| **Giá trị / outcome** | Người dùng có thực sự hoàn thành việc quan trọng tốt hơn không? | Tỉ lệ học viên tự đăng ký và vào bài đầu, số yêu cầu hỗ trợ |
| **Năng lực dòng công việc** | Đội có biến thay đổi thành Increment đạt chất lượng đều và có thể dự báo không? | WIP, work item age, throughput, cycle time |
| **Chất lượng và vận hành** | Những thay đổi có an toàn, đáng tin và bền vững không? | Lỗi sau phát hành, thời gian khôi phục, hồi quy, sự cố truy cập |

**Velocity** có thể hỗ trợ dự báo nội bộ nếu đội tự ước lượng bằng story point; nó không đo giá trị và không phù hợp để xếp hạng giữa những đội có cách chia việc khác nhau. **Throughput** tăng cũng có thể chỉ vì chia ticket nhỏ hơn, không phải vì người dùng nhận thêm giá trị.

### 9.2. Thước đo dòng công việc của Kanban

Trong Kanban, có thể sử dụng:

- **WIP (Work in Progress):** số hạng mục đã bắt đầu nhưng chưa hoàn tất.
- **Work item age:** thời gian một hạng mục đang mở đã nằm trong workflow.
- **Cycle time:** thời gian từ lúc bắt đầu đến khi hoàn tất theo định nghĩa luồng.
- **Throughput:** số hạng mục hoàn tất trong một khoảng thời gian.

Ví dụ, nếu QA đang có 12 mục chờ kiểm tra và số mục hoàn tất mỗi Sprint ngày càng ít, việc mở thêm 8 mục mới có thể làm vòng phản hồi dài hơn. Nhóm nên phân tích hàng đợi, hỗ trợ kiểm thử sớm và cải thiện khả năng tích hợp, thay vì chỉ yêu cầu Developers “code nhanh hơn”.

Kanban có thể được dùng cùng Scrum để tăng khả năng quan sát dòng công việc; **không cần bỏ Sprint mới được sử dụng WIP hoặc cycle time**. Tuy nhiên, việc áp dụng Kanban không tự xóa được phụ thuộc tổ chức hay kỹ thuật.

### 9.3. Chỉ số giao hàng và vận hành

Những phép đo thường gắn với năng lực DevOps/DORA có thể giúp nhận diện vấn đề về tần suất và độ tin cậy khi thay đổi, ví dụ tần suất triển khai, thời gian đưa thay đổi qua hệ thống, mức lỗi liên quan thay đổi và khả năng khôi phục. Định nghĩa cụ thể của hệ đo có thể tiến hóa theo thời gian và bối cảnh.

Không nên:

- Đòi hỏi mọi đội có cùng tần suất deploy dù rủi ro và mô hình phát hành khác nhau.
- Đánh giá cá nhân qua số commit, số pull request hoặc số story point.
- Khuyến khích deploy nhiều chỉ để làm đẹp dashboard.
- Bỏ qua mức độ nghiêm trọng của sự cố và tác động lên người dùng.

Số đo hữu ích khi giúp đội **thay đổi quyết định**, không phải chỉ để có một bảng xếp hạng.

## 10. Khi nào Scrum cần được bổ sung, khi nào cần xem lại cách tổ chức công việc?

Scrum phù hợp với việc tạo giá trị từ các vấn đề phức tạp, nơi nhóm có thể xây Increment thường xuyên, kiểm tra thực tế và thích ứng. Tuy nhiên, không phải mọi dòng công việc đều cần cùng nhịp và cách tổ chức.

### 10.1. Phân biệt lựa chọn khung với năng lực thực thi

| Tình huống | Điều nên xem xét | Điều cần tránh |
|---|---|---|
| Nhóm sản phẩm đang học từ nhu cầu thay đổi, tạo Increment theo Sprint | Sử dụng Scrum, đầu tư DoD, discovery và năng lực kỹ thuật | Nghĩ rằng chỉ họp đủ là tạo giá trị |
| Dòng yêu cầu nhỏ, liên tục, khó dự đoán thời điểm đến | Chính sách luồng, Kanban, xử lý loại việc và WIP; có thể kết hợp Scrum nếu vẫn có Sprint Goal hữu ích | Ép mọi sự cố phải chờ Sprint kế tiếp hoặc ngụy tạo Sprint Goal |
| Hệ thống cũ phụ thuộc nhiều bên, không thể tích hợp nhanh | Cải tiến kiến trúc, pipeline, phân quyền và phối hợp cấp tổ chức | Đổi từ hai tuần sang một tuần rồi kỳ vọng rủi ro tự biến mất |
| Sản phẩm có yêu cầu kiểm định và an toàn cao | DoD/kiểm chứng phù hợp, chuyên gia tuân thủ tham gia sớm, chứng cứ truy vết | Bỏ kiểm soát hoặc đổi nhãn Done để kịp Sprint |
| Nhiều đội cùng một sản phẩm | Product Goal, backlog, Product Owner và DoD thống nhất; tích hợp liên đội | Chỉ tổ chức thêm cuộc họp mà không giải quyết phụ thuộc |
| Đội chưa có quyền quyết định về mục tiêu hoặc ưu tiên | Sửa cơ chế governance và quyền hạn ở cấp phù hợp | Đổ lỗi cho Developers vì không tự chủ trong điều họ không được phép quyết |

**Scrum với Kanban**, XP và DevOps không phải các mảnh ghép có thể lắp một cách máy móc. Cần chọn thực hành bổ sung dựa trên trở ngại đã xác nhận và đánh giá kết quả sau khi áp dụng.

### 10.2. Tránh lập luận “Scrum có thể giải quyết mọi thứ”

Scrum có thể giúp **phát hiện** rằng kiểm thử tích hợp quá chậm. Nó không tự động tạo máy chủ kiểm thử, ngân sách hay quy trình phê duyệt. Scrum có thể giúp Product Owner **thấy** rằng người dùng không cần một tính năng; nếu Product Owner không có quyền đổi ưu tiên, tổ chức vẫn phải giải quyết vấn đề quyền quyết định.

Ngược lại, không nên kết luận Scrum vô ích khi nhóm gặp trở ngại kỹ thuật. Nhịp kiểm tra của Scrum có thể giúp đánh giá rủi ro sớm và ưu tiên cải tiến, miễn các bên sẵn sàng hành động dựa trên bằng chứng.

## 11. Tình huống xuyên suốt: Scrum đủ nghi thức nhưng luồng đăng ký vẫn trễ

> **Tình huống giả định để học tập.** Mọi khoảng thời gian và số liệu dưới đây chỉ minh họa cách chẩn đoán và cải tiến; không phải dữ liệu thực nghiệm hay chuẩn ngành.

Một nhóm 8 người phát triển nền tảng học trực tuyến dùng Sprint hai tuần. Mục tiêu sản phẩm là giúp học viên tự đăng ký và vào khóa học mà không cần gọi hỗ trợ.

Nhóm có Product Owner, Scrum Master và Developers với các kỹ năng giao diện, backend và kiểm thử. Scrum events diễn ra đều đặn. Tuy nhiên:

- 12 backlog items đã được đánh dấu Done trong hai Sprint, nhưng chỉ có 2 luồng đầu-cuối đạt DoD.
- Kiểm thử tích hợp phải chờ môi trường dùng chung khoảng 10 ngày.
- Nhà cung cấp thanh toán chưa cung cấp sandbox đầy đủ.
- Product Owner muốn ưu tiên sửa trạng thái thanh toán nhưng phải chờ hội đồng ra quyết định mỗi tháng.
- Sprint Review chủ yếu trình diễn giao diện bằng dữ liệu giả; người dùng thực không được mời hoặc quan sát.
- Lỗi cấp quyền sau thanh toán được phát hiện khi gần đến lịch triển khai.

Những con số và điều kiện này không chứng minh Scrum là nguyên nhân. Chúng cho thấy **các vòng kiểm tra và khả năng tạo Increment có giá trị chưa ăn khớp**.

### 11.1. Đội chẩn đoán theo từng tầng

| Hiện tượng | Giới hạn liên quan | Cần kiểm tra | Can thiệp có thể thử |
|---|---|---|---|
| Done nhiều nhưng Increment ít | DoD không được áp dụng nhất quán; chia việc theo tầng kỹ thuật | “Done” nghĩa là gì? Luồng nào thực sự chạy được? | Làm rõ DoD, chia lát cắt dọc, kiểm tra tích hợp trước khi đóng |
| Chờ môi trường 10 ngày | Hạ tầng và chính sách chia sẻ tài nguyên | Ai quản lý? Có thể tự phục vụ hoặc dựng môi trường riêng không? | Tự động tạo môi trường thử phù hợp, thống nhất lịch và quyền truy cập |
| Thiếu sandbox đối tác | Phụ thuộc bên ngoài | Yêu cầu API, điều kiện hợp đồng, mức tin cậy của mock | Spike/kiểm chứng tích hợp sớm, công khai rủi ro và kế hoạch thay thế |
| Product Owner chờ phê duyệt | Quyền ưu tiên không tương xứng trách nhiệm | Những quyết định nào cần phê duyệt thật? | Rõ ngưỡng ủy quyền và mốc phản hồi cho quyết định |
| Demo dữ liệu giả | Kiểm tra chưa đủ thực chất | Increment đã đạt DoD? Dữ liệu nào đại diện? | Trình diễn luồng tích hợp thực; ghi rõ prototype nếu chưa hoàn tất |
| Thiếu phản hồi người dùng | Discovery/validation còn yếu | Người học gặp khó ở bước nào? | Quan sát tác vụ, xem dữ liệu hỗ trợ và đo outcome |

Chẩn đoán nhiều tầng giúp tránh giải pháp hời hợt như “tăng Daily Scrum lên 30 phút”, “đổi Scrum Master” hoặc “mua thêm công cụ quản lý ticket” trong khi hàng đợi QA và quyền ra quyết định vẫn không thay đổi.

### 11.2. Cải tiến kỹ thuật đầu tiên

Nhóm chọn một Sprint Goal có ý nghĩa: **“Học viên đã thanh toán hợp lệ xem được trạng thái chính xác và mở được bài đầu tiên”**.

Để phục vụ mục tiêu, nhóm:

1. Chia một lát cắt UI–API–dữ liệu–quyền truy cập thay vì các ticket giao diện/backend tách rời.
2. Viết AC cho giao dịch đã xác nhận, đang xử lý, thất bại và callback lặp.
3. Bổ sung integration tests cho nguồn trạng thái, quyền truy cập và idempotency.
4. Tạo pipeline chạy sớm những phép kiểm tra phù hợp trên build tích hợp.
5. Làm rõ các kiểm tra bắt buộc trong DoD và đưa chuyên gia vận hành/bảo mật tham gia sớm.
6. Xử lý phụ thuộc sandbox bằng hoạt động khám phá có thời hạn, ghi rõ những điều chưa thể kết luận.

Lưu ý: nếu thanh toán sandbox chưa chứng minh được khả năng nhận giao dịch thật, nhóm **không được gọi toàn bộ luồng thanh toán production là hoàn tất**. Sprint Goal và phạm vi phải được chọn phù hợp với những khả năng thực sự có thể kiểm chứng.

### 11.3. Cải tiến tổ chức song song

Trong cùng thời gian, Scrum Master hỗ trợ đội và lãnh đạo làm rõ:

- Product Owner được tự quyết thứ tự các mục backlog trong phạm vi Product Goal và những ràng buộc nào?
- Khi cần thay đổi chính sách cấp quyền hoặc thanh toán, ai có thẩm quyền phản hồi và trong thời hạn nào?
- Những kiểm tra có thể tự động hóa hoặc đưa vào Scrum Team để không chờ hàng tuần?
- Vận hành có thể hỗ trợ môi trường và quy trình triển khai thường xuyên hơn thế nào?
- Làm sao để người dùng/hỗ trợ cung cấp phản hồi ngay sau một Increment?

Đây là **trở ngại ở cấp hệ thống**, không chỉ là công việc của một Scrum Master đi “nhắc người khác” cho đủ lịch.

### 11.4. Review dựa trên Increment và điều học được

Thay vì báo “12/12 ticket Done”, Sprint Review có thể trình bày:

> **Khả năng đã đạt DoD:** học viên xem trạng thái đăng ký sau giao dịch hợp lệ và truy cập đúng khóa trong môi trường được kiểm chứng.  
> **Bằng chứng:** kết quả kiểm thử tích hợp cho các trạng thái quan trọng; kiểm tra phân quyền và callback lặp; giới hạn hiện tại được nêu rõ.  
> **Điều còn mở:** xác nhận tích hợp production với nhà cung cấp và một số trường hợp cần phê duyệt bổ sung.  
> **Điều mới học:** người học khó phân biệt “đang xử lý” với “đã thanh toán”; đội đề xuất điều chỉnh thông báo trước tính năng gợi ý khóa học.  
> **Quyết định:** Product Owner xem lại thứ tự backlog; người có thẩm quyền phối hợp giải quyết phụ thuộc đối tác.

**Sprint Review là cơ hội kiểm tra và thích ứng, không phải nơi làm lễ công nhận Done**. Increment phải đáp ứng DoD theo tiêu chuẩn áp dụng trước khi được tính là hoàn tất.

### 11.5. Đánh giá cải tiến bằng kết quả, không bằng số cuộc họp

Sau một số chu kỳ, đội có thể theo dõi:

- Số lượng **Increment tích hợp và đạt DoD**, không chỉ số ticket được đóng.
- Thời gian chờ môi trường kiểm thử và số hạng mục đang bị chặn.
- Cycle time của các item tương đối so sánh được.
- Số lỗi phát hiện muộn hoặc lọt ra môi trường sử dụng.
- Khả năng phát hành an toàn và thời gian xử lý sự cố.
- Tỷ lệ học viên tự hoàn thành luồng đăng ký, phản hồi về trạng thái thanh toán.

Nếu môi trường kiểm thử nhanh hơn nhưng tỷ lệ đăng ký không cải thiện, đội cần xem lại giả thuyết sản phẩm. Nếu outcome tăng nhưng lỗi bảo mật tăng, không được coi cải tiến là thành công vô điều kiện. **Năng lực kỹ thuật và giá trị người dùng cần được đọc cùng nhau.**

## 12. Kế hoạch cải tiến theo ba chân trời

Thay vì cố triển khai ngay một “chương trình chuyển đổi Agile toàn diện”, đội có thể bắt đầu từ một trở ngại được đo và mở rộng từng bước.

### 12.1. Trong một hoặc hai Sprint: nhìn rõ và giảm một điểm nghẽn

| Việc làm | Bằng chứng cần thu |
|---|---|
| Kiểm tra lại DoD và định nghĩa Done trên bảng công việc | Một Increment thật có đạt chuẩn không, hay chỉ là một phần việc? |
| Chọn một lát cắt dọc quan trọng và hoàn tất end-to-end | Luồng có thể sử dụng và kiểm chứng, không dựa vào dữ liệu giả chưa công bố |
| Quan sát điểm chờ lớn nhất: QA, môi trường, tích hợp hay quyết định ưu tiên | Work item age, thời gian chờ, tác động đến Sprint Goal |
| Đưa người hiểu nghiệp vụ và kỹ thuật liên quan vào làm rõ AC sớm | Các giả định và trường hợp lỗi được phát hiện trước khi triển khai |
| Dùng Retrospective để chọn một thử nghiệm cải tiến nhỏ | Người thực hiện, điều thay đổi và thời điểm kiểm tra kết quả |

### 12.2. Trong vài Sprint: xây năng lực giao hàng

- Tự động hóa kiểm thử hồi quy quan trọng và quy trình build lặp lại được.
- Rút ngắn thời gian tích hợp, giảm những thay đổi tích lũy quá lớn.
- Cải thiện độ ổn định môi trường thử và quyền truy cập cần thiết.
- Tạo khả năng phát hành an toàn và quan sát sản phẩm sau release.
- Phát triển kỹ năng liên chức năng, thiết kế có thể sửa và quyền sở hữu chất lượng chung.
- Thiết lập nhịp phản hồi người dùng và đánh giá outcome với Product Owner.
- Thống nhất với lãnh đạo những phụ thuộc phải xử lý ở cấp tổ chức.

Đừng đặt một chỉ tiêu chung như “mọi đội phải có 90% code coverage” mà không xác định rủi ro và chất lượng test. Chỉ số cần phục vụ quyết định chứ không phải tạo mục tiêu dễ đối phó.

### 12.3. Trung hạn: điều chỉnh cơ chế tổ chức

Nếu những phụ thuộc liên tục xuất hiện, có thể cần:

- Rà soát cấu trúc đội và ranh giới sở hữu sản phẩm.
- Làm rõ Product Goal, quyền Product Owner và cách stakeholders tham gia.
- Tạo dịch vụ nội bộ dễ sử dụng cho môi trường, bảo mật, kiểm thử, triển khai.
- Thay cơ chế dự báo chỉ dựa vào số người bận bằng dữ liệu Increment và dòng công việc.
- Điều chỉnh chính sách phê duyệt, ngân sách hoặc hợp tác với nhà cung cấp.
- Thiết kế cách quản lý đa đội giúp tích hợp thật, không chỉ họp phối hợp.

Đây là những quyết định cần vai trò có thẩm quyền. Scrum Team có thể **đưa ra bằng chứng và đề xuất**, nhưng không thể tự mình thay đổi mọi chính sách hoặc hợp đồng.

## 13. Những tình huống biên cần phán đoán cẩn trọng

### 13.1. Sản phẩm legacy có độ trễ kiểm thử rất lớn

Một hệ thống cũ không có test, triển khai thủ công và phụ thuộc database chung có thể khó tạo Increment đáng tin mỗi Sprint. Không có nghĩa cứ thêm Sprint dài hơn là giải pháp.

Đội cần xác định các **đường kiểm chứng nhỏ nhưng có ý nghĩa**, xây kiểm thử xung quanh hành vi cốt lõi, cải thiện build/tích hợp, giảm phụ thuộc và đặt lộ trình đầu tư kỹ thuật. DoD phải minh bạch và không thể bị giả vờ đạt. Nếu phát hiện không thể hoàn tất mục tiêu đã chọn, phải điều chỉnh kế hoạch và làm rõ khả năng thực tế.

### 13.2. Dòng sự cố vận hành đến bất ngờ

Một nhóm trực sự cố 24/7 có thể khó bảo vệ Sprint Goal khi công việc khẩn đến liên tục. Các chính sách **Kanban**, phân loại mức độ khẩn, giới hạn WIP và đội trực luân phiên có thể giúp quản lý luồng. Một số nhóm vẫn dùng Scrum với chính sách năng lực dự phòng; một số chọn luồng liên tục là chính.

Điều quan trọng là không ép sự cố nghiêm trọng đợi Sprint kế tiếp hoặc ước lượng giả để tạo cảm giác kế hoạch ổn định. Cần đánh giá **mô hình công việc** trước khi chọn cách phối hợp.

### 13.3. Sản phẩm phần cứng hoặc hệ thống phụ thuộc chu kỳ chứng nhận

Không phải mọi Increment đều có thể đưa ngay tới người dùng cuối nếu việc thử nghiệm vật lý hoặc chứng nhận mất nhiều thời gian. Scrum vẫn có thể hỗ trợ nhịp học tập với mô phỏng, nguyên mẫu và bằng chứng theo giai đoạn, nhưng phải mô tả rõ **mức độ hoàn thiện và giới hạn của mỗi Increment**.

Không nhầm một mô hình chạy mô phỏng với sản phẩm đã đạt điều kiện an toàn ngoài thực tế. Các nghĩa vụ chứng nhận phải được lập kế hoạch từ sớm.

### 13.4. Đội phân tán, nhà cung cấp và người dùng ở nhiều múi giờ

Daily Scrum không tự giải quyết độ trễ phản hồi 24 giờ hoặc hợp đồng nhà cung cấp chỉ cho phép trao đổi qua một đầu mối. Nhóm có thể cần:

- Tài liệu quyết định ngắn, rõ và cập nhật.
- Ví dụ API/AC có thể kiểm chứng không đồng bộ.
- Khoảng giờ chồng lấn để giải quyết phụ thuộc khó.
- Quy tắc thời hạn phản hồi và kênh khẩn cấp.
- Môi trường tích hợp và kết quả kiểm thử có thể chia sẻ.

Số cuộc họp không phản ánh chất lượng cộng tác; **độ trễ từ câu hỏi tới quyết định và từ mã tới bằng chứng** mới giúp hiểu vấn đề.

### 13.5. Hợp đồng phạm vi và ngày cố định

Nếu cả ngày giao, ngân sách và toàn bộ phạm vi đều bị khóa trong khi còn bất định lớn, một Scrum Team khó tạo lời hứa đáng tin chỉ bằng cách chia Sprint. Cần công khai các giả định, xác định phần tối thiểu có ích và an toàn, đánh giá rủi ro hợp đồng, thương lượng điều kiện thay đổi và báo cáo sớm phương án nếu không khả thi.

Scrum hỗ trợ kiểm tra và dự báo; **không thay thế trách nhiệm quản trị hợp đồng hoặc quyền ra quyết định về đánh đổi**.

## 14. Những ngộ nhận phổ biến

### Ngộ nhận 1: “Scrum có đủ nghi thức thì sản phẩm tự tốt”

Các sự kiện Scrum tạo cơ hội kiểm tra; chất lượng thực tế cần DoD đáng tin, năng lực kỹ thuật và phản hồi người dùng.

**Thay thế:** Đánh giá Increment có thể sử dụng và những quyết định thay đổi sau kiểm tra.

### Ngộ nhận 2: “Scrum Guide không nhắc TDD nên đội không cần kiểm thử”

Scrum không quy định TDD, nhưng vẫn yêu cầu Increment đáp ứng DoD. Nếu không có chiến lược kiểm thử phù hợp, đội khó chứng minh chất lượng.

**Thay thế:** Chọn phép kiểm chứng theo rủi ro; dùng TDD, BDD, integration tests hoặc thực hành phù hợp như những công cụ, không phải huy hiệu.

### Ngộ nhận 3: “Chỉ Product Owner chịu trách nhiệm về giá trị”

Product Owner chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog, nhưng Scrum Team cùng tạo Increment hữu ích; Developers và Scrum Master có những accountability khác nhau, cần phối hợp.

**Thay thế:** Rõ vai trò mà không tách đội phát triển khỏi nhu cầu người dùng.

### Ngộ nhận 4: “Scrum Master chỉ cần xếp lịch và dẫn họp”

Hiệu quả Scrum còn liên quan đến việc huấn luyện đội và tổ chức, giúp tháo trở ngại và cải thiện khả năng thực nghiệm.

**Thay thế:** Xem Scrum Master là người chịu trách nhiệm về hiệu quả Scrum Team, không phải thư ký cuộc họp hoặc người quản lý task.

### Ngộ nhận 5: “Sprint Review là ngày được phép release”

Increment có thể được phát hành trước Sprint Review khi đáp ứng điều kiện phù hợp. Review dùng để kiểm tra kết quả và thích ứng Product Backlog.

**Thay thế:** Phân biệt Increment Done, deployment, release và outcome.

### Ngộ nhận 6: “Done nghĩa là code xong, QA sẽ làm Sprint sau”

Nếu tiêu chuẩn chất lượng và kiểm thử cần thiết chưa đạt, item chưa là một phần của Increment. Một “hardening Sprint” mặc định sau nhiều Sprint có thể che giấu dòng công việc chưa hoàn tất.

**Thay thế:** Tích hợp và kiểm chứng xuyên suốt, cải thiện DoD và năng lực kỹ thuật.

### Ngộ nhận 7: “Cứ tăng velocity là Scrum thành công”

Story point không đo giá trị. Đội có thể tăng điểm bằng cách đổi cách ước lượng và chia ticket mà không giúp người dùng.

**Thay thế:** Xem outcome, chất lượng và năng lực giao hàng dựa trên bằng chứng.

### Ngộ nhận 8: “Nếu đội không tự quản lý được thì chỉ cần đào tạo mindset”

Khi ưu tiên, nhân sự, môi trường và mọi quyết định kỹ thuật bị kiểm soát từ bên ngoài, đội không có đủ điều kiện tự quản lý.

**Thay thế:** Giải quyết ranh giới quyền hạn, phụ thuộc, hạ tầng và cơ chế lãnh đạo.

### Ngộ nhận 9: “Thêm công cụ hoặc quy mô Scrum là tự giải quyết tích hợp”

Công cụ quản lý backlog và các cuộc họp liên đội không tự tạo API contract, test tích hợp hoặc kiến trúc ít phụ thuộc.

**Thay thế:** Giảm phụ thuộc kỹ thuật và tổ chức, tạo một Increment sản phẩm tích hợp thực.

### Ngộ nhận 10: “Nếu Scrum chưa hiệu quả, cứ bỏ Scrum là giải pháp”

Có những bối cảnh Kanban hoặc mô hình khác phù hợp hơn, nhưng đổi tên phương pháp không tự sửa kiểm thử, kiến trúc, quyền quyết định hay bất định về sản phẩm.

**Thay thế:** Chẩn đoán rõ trở ngại rồi mới quyết định thay thực hành, chính sách hoặc khung.

### Ngộ nhận 11: “Tuân thủ và bảo mật chỉ làm Agile chậm”

Một số kiểm soát là bắt buộc để bảo vệ người dùng. Vấn đề thường nằm ở cách tổ chức kiểm chứng muộn, lặp thủ công hoặc không có điều kiện kiểm tra.

**Thay thế:** Đưa yêu cầu chất lượng vào sớm, tự động hóa phần phù hợp và giữ thẩm quyền phê duyệt cần thiết.

### Ngộ nhận 12: “Scrum thất bại là lỗi của một cá nhân”

Kết quả hệ thống chịu ảnh hưởng bởi nhiều yếu tố: kỹ năng, kiến trúc, dữ liệu, quyền hạn, hợp đồng và năng lực vận hành. Một thành viên có thể cần cải tiến hành vi, nhưng không thể kết luận nguyên nhân từ một biểu đồ tiến độ.

**Thay thế:** Dùng Retrospective và dữ liệu thực để điều tra nguyên nhân, gán trách nhiệm hành động phù hợp và kiểm tra cải tiến.

## 15. Quy trình chẩn đoán một Scrum Team đang bị kẹt

Một quy trình thực dụng theo sáu bước:

1. **Chọn một luồng giá trị cụ thể.** Ví dụ từ học viên nhấn đăng ký đến khi họ vào được bài học đầu tiên.
2. **Xác nhận định nghĩa Done.** Kiểm tra những ticket gần đây: cái gì đã được tích hợp, kiểm thử và có thể sử dụng? Điều gì mới chỉ “xong một phần”?
3. **Vẽ thời gian và điểm chặn.** Ghi thời gian phát triển, chờ kiểm thử, chờ môi trường, phê duyệt, triển khai và phản hồi người dùng.
4. **Phân loại trở ngại.** Do cách áp dụng Scrum, năng lực kỹ thuật, hiểu biết sản phẩm hay điều kiện tổ chức? Ai có quyền thay đổi?
5. **Chọn một hoặc hai cải tiến có thể đo.** Ví dụ tăng mức tích hợp hằng ngày, giảm WIP, đưa kiểm thử phân quyền vào pipeline, hoặc trao quyền ưu tiên cho Product Owner trong phạm vi xác định.
6. **Kiểm tra sau vài chu kỳ.** Đo thời gian đến Increment đạt DoD, lỗi, độ trễ quyết định và outcome. Giữ, sửa hoặc dừng thực hành theo bằng chứng.

~~~mermaid
flowchart TD
    A["Luồng người dùng đang bị chặn"] --> B["Đo thực tế: Done, chờ đợi, lỗi, phản hồi"]
    B --> C{"Trở ngại chính ở đâu?"}
    C -->|Scrum| D["Làm rõ Goal, events, artifact, accountability"]
    C -->|Kỹ thuật| E["CI, kiểm thử, kiến trúc, vận hành"]
    C -->|Sản phẩm| F["Discovery, outcome, Product Backlog"]
    C -->|Tổ chức| G["Quyền quyết định, phụ thuộc, chính sách"]
    D --> H["Một cải tiến có người phụ trách và phép đo"]
    E --> H
    F --> H
    G --> H
    H --> I["Kiểm tra kết quả qua các chu kỳ"]
    I -. "Điều chỉnh theo bằng chứng" .-> B
~~~

Không cần chọn ngay công cụ hoặc phương pháp mới. Đầu tiên phải **biết điểm nào đang ngăn nhóm tạo và học từ Increment hữu ích**.

### 15.1. Mẫu ghi nhận một thử nghiệm cải tiến

~~~text
VAN DE DUOC QUAN SAT:
  [Vi du: item cho QA trung binh qua nhieu ngay]

BANG CHUNG HIEN TAI:
  [So item, thoi gian cho, cac su co, pham vi do]

GIA THUYET NGUYEN NHAN:
  [Vi du: kiem thu chi bat dau sau khi code cua Sprint ket thuc]

THAY DOI SE THU:
  [Vi du: kiem tra integration som cho lat cat quan trong]

NGUOI / NHOM CO THE QUYET DINH:
  [Ai co quyen va du dieu kien thuc hien?]

GUARDRAIL:
  [Khong ha DoD, bao mat, chat luong, workload ben vung]

BANG CHUNG KY VONG:
  [Thoi gian cho, Increment dat DoD, loi hoi quy, phan hoi]

MOC XEM LAI:
  [Sau bao nhieu lan chay / Sprint hoac dieu kien nao]

QUYET DINH TIEP:
  [Giu, sua, bo, mo rong, can thay doi chinh sach cap to chuc]
~~~

## 16. Bài tập vận dụng

### Bài tập A — Phân loại trở ngại

Một Scrum Team gặp bốn vấn đề:

1. Không có Sprint Goal; Sprint Planning chỉ chia task cho từng người.
2. Kiểm thử hồi quy mất 12 ngày vì mọi bước chạy thủ công.
3. Product Owner phải chờ hai cấp phê duyệt để điều chỉnh thứ tự backlog.
4. User story hoàn tất nhưng người dùng không hiểu cách vào bài học đầu tiên.

**Yêu cầu:** Với từng vấn đề, phân loại **cách thực hành Scrum**, **năng lực kỹ thuật**, **điều kiện tổ chức** hoặc **khám phá/kiểm chứng giá trị**. Đề xuất hành động có thể thử.

<details>
<summary>Gợi ý đáp án</summary>

1 là vấn đề cách dùng Scrum: Scrum Team cần một Sprint Goal có ý nghĩa và Developers lập kế hoạch hướng tới đó. 2 là năng lực kỹ thuật: phân loại kiểm thử theo rủi ro, đưa kiểm tra hồi quy quan trọng vào pipeline và cải thiện môi trường. 3 là rào cản tổ chức: làm rõ quyền Product Owner, ngưỡng ủy quyền và đường xử lý ngoại lệ. 4 liên quan discovery/validation: quan sát luồng thật, kiểm tra mức tiếp cận tính năng và điều chỉnh Product Backlog. Mỗi vấn đề có thể có nguyên nhân liên quan khác nên cần kiểm chứng bằng dữ liệu.

</details>

### Bài tập B — Xác định Increment Done

Nhóm làm chức năng lưu khóa học yêu thích. Frontend hoạt động trong demo, API trả HTTP 200 trên môi trường mock; kiểm thử phân quyền chưa chạy và dữ liệu không tồn tại sau đăng nhập lại. Người quản lý yêu cầu đánh dấu Done vì “đã hoàn thành 90%”.

**Yêu cầu:** Hạng mục có thể được coi là Done không? Scrum cung cấp quy tắc nào? Các năng lực kỹ thuật bổ trợ nào cần có?

<details>
<summary>Gợi ý đáp án</summary>

Không, nếu hành vi tồn tại qua phiên và phân quyền là tiêu chí/điều kiện chất lượng áp dụng thì công việc chưa đáp ứng DoD. Scrum yêu cầu Increment đáp ứng DoD để được xem là hoàn tất. Đội cần kiểm thử tích hợp với lưu trữ thực của môi trường phù hợp, kịch bản đăng nhập lại, kiểm tra tài khoản khác, bằng chứng theo build và khả năng chạy lại sau sửa lỗi. Không cần tuyên bố “90% Done” thay cho trạng thái thật.

</details>

### Bài tập C — Review có tạo học tập không?

Trong ba Sprint, đội đã demo tổng cộng 18 màn hình bằng tài khoản thử, nhưng không có dữ liệu sử dụng, không gặp người dùng và Product Backlog giữ nguyên dù hỗ trợ báo nhiều lỗi đăng ký.

**Yêu cầu:** Sprint Review đang thiếu điều gì? Các thực hành ngoài Scrum nào có thể bổ sung, và Product Owner nên quyết định tiếp theo thế nào?

<details>
<summary>Gợi ý đáp án</summary>

Review chưa kiểm tra được mức độ sản phẩm phục vụ mục tiêu và phản hồi thực. Đội nên trình diễn Increment đạt DoD, xem dữ liệu hỗ trợ, quan sát học viên thực hiện tác vụ, phân tích sự kiện quan trọng và rủi ro vận hành. Product Owner nên cân nhắc ưu tiên xử lý trở ngại của người học thay vì tiếp tục toàn bộ màn hình trong kế hoạch ban đầu. Product discovery và product analytics là năng lực bổ trợ, không phải các sự kiện Scrum bắt buộc.

</details>

### Bài tập D — Scrum hay Kanban cho đội xử lý sự cố?

Một nhóm nhận khoảng 30 yêu cầu vận hành mỗi tuần, nhiều yêu cầu không dự báo trước; đôi lúc có sự cố mức khẩn rất cao. Nhóm cố đưa mọi yêu cầu vào Sprint Goal hai tuần, liên tục đổi scope và hầu như không có thời gian Review sản phẩm.

**Yêu cầu:** Bạn sẽ đặt câu hỏi gì trước khi đề xuất đổi cách làm? Chính sách nào của Kanban có thể hữu ích?

<details>
<summary>Gợi ý đáp án</summary>

Cần hỏi loại công việc, mục tiêu dịch vụ, mức biến động đầu vào, thời gian chờ, nghĩa vụ xử lý sự cố và cơ hội tạo Increment có giá trị theo Sprint. Kanban có thể hỗ trợ hiển thị workflow, chính sách xử lý việc khẩn, WIP, work item age, throughput, cycle time và SLE phù hợp. Có thể kết hợp Kanban với Scrum khi vẫn có Sprint Goal có ý nghĩa; không nên quyết định chỉ theo khẩu hiệu “Scrum không hợp vận hành” trước khi xem dữ liệu.

</details>

### Bài tập E — Rào cản quyền Product Owner

Scrum Team có Product Goal rõ, nhiều phản hồi chỉ ra vấn đề cấp quyền khóa học, nhưng hội đồng quản lý buộc ưu tiên các báo cáo không liên quan trong bốn Sprint tới. Product Owner không được đổi thứ tự dù có bằng chứng sản phẩm.

**Yêu cầu:** Việc này ảnh hưởng trụ cột Scrum nào và giải pháp phải đến từ cấp nào?

<details>
<summary>Gợi ý đáp án</summary>

Trụ cột thích ứng bị hạn chế vì dữ liệu kiểm tra không dẫn đến thay đổi quyết định. Product Owner cần quyền quản lý Product Backlog hiệu quả; nếu quyền này bị giới hạn, cần làm rõ cơ chế phân quyền và yêu cầu hội đồng/lãnh đạo có thẩm quyền điều chỉnh. Scrum Master có thể giúp làm minh bạch tác động và hỗ trợ tháo trở ngại. Developers không thể tự vượt qua các ràng buộc quản trị bằng việc họp Daily Scrum nhiều hơn.

</details>

### Bài tập F — Thiết kế một cải tiến kiểm chứng được

Nhóm nói: “Scrum chậm vì mỗi Sprint đều phải chờ QA tập trung khoảng 8 ngày”. Đội muốn bắt đầu “triển khai DevOps” nhưng chưa biết hành động cụ thể.

**Yêu cầu:** Viết một giả thuyết cải tiến nhỏ, cách đo và guardrail. Chỉ rõ điều gì cần sự hỗ trợ của tổ chức.

<details>
<summary>Gợi ý đáp án</summary>

Giả thuyết: nếu đưa kiểm thử tích hợp cho luồng đăng ký quan trọng vào pipeline và có QA tham gia làm rõ AC trước khi code, thời gian chờ kiểm chứng và số lỗi phát hiện muộn sẽ giảm. Đo thời gian chờ từ item sẵn kiểm tra đến có kết quả, số Increment đạt DoD, lỗi hồi quy và test bị skip. Guardrail: không bỏ kiểm tra bảo mật hoặc accessibility cần thiết; không biến pipeline “xanh” thành mục tiêu đối phó. Cần tổ chức hỗ trợ môi trường, quyền truy cập, thời gian chuyên gia và quyền thay đổi quy trình kiểm thử.

</details>

### Bài tập G — Tính đúng đắn của lời hứa phát hành

Một Scrum Team tạo Increment đạt DoD vào ngày thứ sáu của Sprint hai tuần. Vận hành đã sẵn sàng và Product Owner muốn đưa cho một nhóm học viên thử sớm. Người quản lý nói: “Scrum bắt buộc chờ Sprint Review rồi mới được release”.

**Yêu cầu:** Nhận định đó có đúng Scrum Guide không? Cần kiểm tra điều kiện nào trước khi phát hành?

<details>
<summary>Gợi ý đáp án</summary>

Không. Scrum cho phép phát hành Increment trước khi Sprint kết thúc; Sprint Review không phải cổng phê duyệt release. Tuy nhiên, phải bảo đảm Increment đạt DoD và các điều kiện phát hành thực tế như bảo mật, quyền hạn, vận hành, dữ liệu, khả năng quan sát, phương án khôi phục và nghĩa vụ tuân thủ phù hợp. “Có thể release theo Scrum” không có nghĩa được bỏ qua kiểm soát bắt buộc của tổ chức.

</details>

## 17. Checklist đánh giá giới hạn và điều kiện hỗ trợ Scrum

Hãy tìm **bằng chứng thực tế** cho từng câu hỏi thay vì trả lời “có” vì đội đã đặt tên một hoạt động:

1. Scrum Team có Product Goal được hiểu chung và đủ liên hệ với nhu cầu người dùng không?
2. Sprint Goal giúp Developers lựa chọn, điều chỉnh kế hoạch hay chỉ là danh sách ticket?
3. Đã có Definition of Done rõ và được áp dụng nhất quán cho Increment chưa?
4. Một item đánh dấu Done có thực sự tích hợp và có thể sử dụng trong phạm vi công bố không?
5. Đội có thể phát hiện lỗi tích hợp và hồi quy trước khi chúng dồn về cuối Sprint không?
6. Kiểm thử, bảo mật, khả năng truy cập và vận hành có được xem là trách nhiệm chất lượng chung không?
7. Môi trường build, kiểm thử và triển khai có đáng tin; những điểm chờ có được đo không?
8. Kiến trúc và phụ thuộc có cho phép giao lát cắt dọc thay vì chỉ hoàn tất từng tầng?
9. Product Owner có khả năng thực sự sắp xếp backlog theo giá trị và phản hồi không?
10. Developers có quyền tự quyết cách làm trong giới hạn chất lượng, và có đủ kỹ năng/nguồn lực cần thiết không?
11. Scrum Master có hỗ trợ hiệu quả Scrum Team và phối hợp với tổ chức để tháo trở ngại không?
12. Sprint Review có kiểm tra Increment và tác động của thông tin mới đối với Product Backlog không?
13. Retrospective có dẫn đến thử nghiệm cải tiến được đo và xem lại không?
14. Người dùng, bộ phận hỗ trợ và dữ liệu sử dụng có tham gia vào vòng khám phá/xác nhận giá trị không?
15. Có người có thẩm quyền giải quyết các phụ thuộc ngoài đội, đặc biệt là môi trường, bảo mật và phê duyệt không?
16. Các đội cùng sản phẩm có Product Goal, backlog, Product Owner và DoD thống nhất theo Scrum không?
17. Dữ liệu flow và vận hành có được dùng để cải tiến hệ thống, không để chấm điểm cá nhân không?
18. Khi một mục không đạt DoD, đội có trung thực công bố trạng thái thay vì đổi nhãn Done không?
19. Tổ chức có tạo môi trường để nhân sự nêu rủi ro và đề xuất thay đổi dựa trên bằng chứng không?
20. Nếu Scrum không phù hợp với loại công việc hiện tại, đội có đánh giá cách tổ chức khác bằng dữ liệu thay vì chạy theo xu hướng không?

Nếu nhiều câu trả lời chưa có bằng chứng, hãy chọn **một luồng giá trị** và tìm **một điểm nghẽn rõ nhất** để xử lý. Không cần đồng thời cài mọi công cụ Agile, DevOps hay XP; cải tiến có ích là thay đổi giúp đội giao sản phẩm đúng chất lượng và học nhanh hơn.

## 18. Tổng kết

- **Scrum là một khung thực nghiệm tối giản, không phải hệ điều hành đầy đủ của tổ chức hay quy trình engineering toàn diện.** Nó cung cấp accountability, sự kiện, artifact, commitment và nguyên tắc minh bạch–kiểm tra–thích ứng.
- **Scrum không tự tạo phần mềm chất lượng.** Cần DoD rõ và các năng lực bổ trợ phù hợp: kiểm thử, tích hợp, thiết kế có thể thay đổi, triển khai, vận hành, bảo mật và khả năng tiếp cận.
- **Scrum không tự xác nhận người dùng cần giải pháp.** Product discovery, nghiên cứu hành vi và dữ liệu outcome giúp Product Owner và Scrum Team quyết định nên xây hoặc thay đổi điều gì.
- **Scrum Team không thể tự vượt mọi ràng buộc tổ chức.** Quyền Product Owner, năng lực liên chức năng, hạ tầng, phụ thuộc, cơ chế phê duyệt và sự hỗ trợ của lãnh đạo ảnh hưởng trực tiếp đến khả năng tạo Increment.
- **Kanban, XP, DevOps và các phương pháp chất lượng là những nguồn thực hành có thể bổ sung.** Chọn theo vấn đề được quan sát, không xem mọi thực hành đó là quy định chính thức của Scrum.
- **Đánh giá bằng chứng thay vì nghi thức:** Increment đạt DoD, chất lượng hệ thống, thời gian đến phản hồi, mức phụ thuộc, khả năng phát hành và giá trị người dùng.
- **Giới hạn của Scrum không phải lý do che giấu thất bại hoặc làm thay phần việc của tổ chức.** Hãy chẩn đoán nguyên nhân, gắn trách nhiệm với đúng cấp quyết định, thực hiện cải tiến và kiểm tra tác dụng của nó.

Khi một Scrum Team đã họp đầy đủ nhưng vẫn giao sản phẩm chậm, câu hỏi hữu ích không phải chỉ là **“Chúng ta còn thiếu nghi thức Scrum nào?”** mà là: **“Nhóm đã có đủ chất lượng kỹ thuật, dữ liệu sản phẩm, quyền quyết định và điều kiện tổ chức để tạo Increment có giá trị mỗi Sprint chưa? Nếu chưa, trở ngại nào phải được tháo gỡ trước và bằng chứng nào sẽ chứng minh cải tiến có tác dụng?”**

## Tài liệu tham khảo định hướng

- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): phạm vi khung Scrum, Scrum Team, empiricism, các commitment, Sprint Review và Definition of Done.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/): giá trị Agile và tầm quan trọng của phần mềm hoạt động được, hợp tác và phản hồi thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html): giao sản phẩm thường xuyên, đội có động lực, chất lượng kỹ thuật và cải tiến liên tục.
- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/): định nghĩa và quản lý dòng công việc, WIP, cycle time, work item age, throughput.
- [DORA — Software delivery performance and capabilities](https://dora.dev/): nghiên cứu và hướng dẫn về năng lực giao phần mềm, chất lượng và vận hành.
- [OWASP Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/): các nhóm yêu cầu kiểm chứng an toàn ứng dụng theo rủi ro.
- [W3C Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/): tiêu chuẩn tham khảo cho khả năng truy cập nội dung web.
