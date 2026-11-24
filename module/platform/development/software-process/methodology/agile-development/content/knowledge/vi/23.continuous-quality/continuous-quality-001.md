# Chất lượng như trách nhiệm chung trong toàn bộ vòng phát triển

## 1. Chất lượng không phải việc của một người ở cuối quy trình

Hãy hình dung một nhóm xây chức năng đăng ký khóa học trên nền tảng học trực tuyến. Product Owner đã mô tả nhu cầu, Developers viết API và giao diện, người kiểm thử chạy các kịch bản, nhóm vận hành triển khai. Cuối Sprint, giao diện hoạt động tốt trong demo một người dùng. Nhưng khi hai học viên cùng đăng ký chỗ cuối, hệ thống xác nhận cho cả hai; một người khác có thể đọc thông tin đăng ký không thuộc quyền mình.

Nếu nhóm nói **“Developers đã xong; QA chưa tìm ra lỗi”**, họ đang chia trách nhiệm theo phòng ban nhưng chưa giải quyết được vấn đề của sản phẩm. Lỗi có thể bắt nguồn từ nhiều nơi: nghiệp vụ chưa làm rõ tình huống đồng thời, thiết kế giao dịch chưa phù hợp, thiếu kịch bản kiểm thử, môi trường không tương tự thực tế hoặc quyết định phát hành đã bỏ qua rủi ro. Không có một bước kiểm thử cuối cùng nào có thể sửa mọi sai lệch hình thành từ trước.

**Chất lượng liên tục (continuous quality)** là cách tư duy và tổ chức công việc trong đó **chất lượng được xây vào từng quyết định và từng bước tạo giá trị**, được kiểm chứng nhiều lần, tiếp tục được quan sát sau khi phần mềm đi vào sử dụng. Nó bao gồm **phòng ngừa sai sót, phát hiện sớm, sửa có trách nhiệm và học từ phản hồi**, chứ không chỉ gia tăng số lượng test.

Trong module **AGILE_DEVELOPMENT**, chất lượng liên tục gắn trực tiếp với các giá trị Agile:

- **Cá nhân và tương tác:** người hiểu nghiệp vụ, người xây sản phẩm, người kiểm thử và người vận hành cùng trao đổi.
- **Phần mềm hoạt động được:** kết quả phải tích hợp, đáp ứng hành vi và điều kiện chất lượng cần thiết, không chỉ “đã viết xong”.
- **Cộng tác với khách hàng:** xác minh đúng vấn đề người dùng, không chỉ đúng đặc tả thiếu sót.
- **Phản hồi với thay đổi:** dùng bằng chứng mới để bổ sung tình huống, điều chỉnh thiết kế và cải tiến quy trình.

Chủ đề này có thể áp dụng với Scrum, Kanban, XP, Lean hoặc cách làm Agile khác. **Không phải mọi tổ chức phải dùng cùng một bộ test hay cùng một sơ đồ vai trò**, nhưng mỗi nhóm cần minh bạch ai quyết định điều gì, tiêu chuẩn nào phải đạt và bằng chứng nào chứng minh phần mềm có thể sử dụng đáng tin cậy.

> **Luận điểm chính:** Chất lượng là trách nhiệm chung đối với **kết quả sản phẩm và hệ thống làm việc**; chuyên gia kiểm thử không phải người duy nhất chịu trách nhiệm, và trách nhiệm chung không xóa bỏ trách nhiệm cụ thể của từng vai trò.

## 2. Chất lượng phần mềm là gì?

### 2.1. “Chạy được” là cần thiết nhưng chưa đủ

Một chức năng có thể chạy đúng khi thao tác thông thường mà vẫn có chất lượng kém:

- **Đúng chức năng:** học viên đăng ký khóa hợp lệ và nhận đúng kết quả; từ chối đăng ký trùng, hết chỗ hoặc trái quyền.
- **Độ tin cậy:** hệ thống không mất dữ liệu hoặc xác nhận sai khi có lỗi mạng, retry, truy cập đồng thời.
- **An toàn và bảo mật:** thông tin học viên không bị đọc hoặc sửa trái quyền; bí mật, phiên đăng nhập được bảo vệ.
- **Hiệu năng:** người dùng nhận phản hồi trong mức chấp nhận được ở tải dự kiến.
- **Khả năng sử dụng và tiếp cận:** giao diện rõ ràng, có thể vận hành bằng bàn phím hoặc công nghệ hỗ trợ khi thuộc phạm vi yêu cầu.
- **Khả năng vận hành:** có logging, cảnh báo và cách khôi phục khi xảy ra sự cố.
- **Khả năng bảo trì/thay đổi:** cấu trúc mã và các kiểm thử giúp đội tiếp tục sửa an toàn khi yêu cầu thay đổi.
- **Tính tương thích:** API, dữ liệu và các Increment trước đó hoạt động cùng nhau.
- **Nghĩa vụ và quyền riêng tư:** cách xử lý dữ liệu hoặc ngành nghề tuân thủ các yêu cầu áp dụng.

Các khía cạnh trên không đồng trọng số trong mọi tình huống. Một bản thử với dữ liệu giả và một hệ thống thanh toán thật có rủi ro khác nhau. Nhóm cần **làm rõ chất lượng cần đạt cho phạm vi sử dụng cụ thể**, thay vì tuyên bố “đạt chất lượng cao” mà không có tiêu chí.

### 2.2. Chất lượng gồm “xây đúng” và “xây điều đúng”

| Góc nhìn | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Building the product right** — xây sản phẩm đúng | Phần mềm có thực hiện đúng hành vi, an toàn và đáng tin cậy trong phạm vi cam kết không? | Một học viên không có hai đăng ký hiệu lực cho cùng khóa, kể cả khi gửi lại request. |
| **Building the right product** — xây điều người dùng cần | Khả năng này có thực sự giải quyết vấn đề người dùng hoặc tổ chức không? | Học viên có thể đăng ký mà không cần gọi nhân viên hỗ trợ. |

Một hệ thống có hàng nghìn test xanh vẫn có thể **không tạo giá trị** nếu người dùng không cần khả năng đó. Ngược lại, một ý tưởng được người dùng yêu thích vẫn không được gọi là sản phẩm hoàn tất nếu gây mất dữ liệu hoặc vi phạm điều kiện an toàn.

Chất lượng liên tục do đó kết hợp **kiểm chứng cách xây** với **phản hồi về giá trị**. Không được dùng chỉ số hài lòng để che lỗi bảo mật, cũng không dùng số lượng test làm bằng chứng đủ về hiệu quả sản phẩm.

### 2.3. Chất lượng được định nghĩa theo bối cảnh và được kiểm chứng

Thay vì nói “trang phải nhanh”, nhóm có thể thảo luận:

> Trong kịch bản học viên đã đăng nhập xem danh sách khóa, thời gian phản hồi ở tải được dự báo phải đáp ứng ngưỡng đã thống nhất. Kết quả cần được đo trên môi trường và dữ liệu đủ đại diện trước khi mở rộng sử dụng.

**Không tự áp một ngưỡng số mili giây chung** cho mọi hệ thống. Mục tiêu hiệu năng phải phù hợp hành trình người dùng, thiết bị, tải, ràng buộc và phép đo. Với độ tin cậy, quyền riêng tư hay khả năng tiếp cận cũng tương tự: cần có **tiêu chuẩn và điều kiện kiểm chứng**, không chỉ một tính từ.

## 3. Trách nhiệm chung không đồng nghĩa ai cũng làm cùng một việc

### 3.1. Tư duy “whole-team quality”

**Whole-team quality** nghĩa là những người tham gia tạo sản phẩm **cùng sở hữu kết quả chất lượng**, phát hiện và giải quyết vấn đề trong phạm vi chuyên môn, không chờ một nhóm cuối quy trình “chịu mọi trách nhiệm”.

Điều đó không yêu cầu mọi thành viên phải viết automation test, thiết kế UX hoặc thực hiện threat modeling giống nhau. Trách nhiệm chung được thể hiện bằng:

1. **Làm rõ chất lượng từ sớm:** cùng đặt câu hỏi và nhận diện rủi ro.
2. **Không đẩy lỗi xuống bước sau:** kiểm tra thích hợp tại nơi thay đổi được tạo ra.
3. **Phối hợp xuyên chuyên môn:** khi một ràng buộc liên quan nhiều thành phần, các bên cùng hiểu và giải quyết.
4. **Minh bạch tình trạng:** không gọi một phần việc là Done nếu tiêu chuẩn bắt buộc chưa đạt.
5. **Cải tiến hệ thống:** lỗi trở thành dữ liệu học hỏi về sản phẩm, test, kỹ thuật và cách phối hợp.

### 3.2. Ai đóng góp điều gì?

| Bên tham gia | Đóng góp chính cho chất lượng | Điều cần tránh |
| --- | --- | --- |
| **Product Owner / người quyết định sản phẩm** | Làm rõ nhu cầu, giá trị, thứ tự Product Backlog, quy tắc nghiệp vụ và phạm vi chấp nhận. | Quy định cách kỹ thuật chi tiết mà không trao đổi hoặc coi vấn đề chất lượng bắt buộc là tùy chọn. |
| **Developers trong Scrum Team** | Lập kế hoạch thực hiện, thiết kế, code, tích hợp, kiểm thử và tuân thủ Definition of Done khi tạo Increment. | Chỉ chịu trách nhiệm đoạn mã cá nhân rồi chuyển lỗi sang “QA”. |
| **Chuyên gia kiểm thử / quality engineering** | Dẫn dắt tư duy kiểm thử, thiết kế tình huống, khám phá rủi ro, automation và phân tích bằng chứng. | Trở thành nút thắt phê duyệt mọi thay đổi hoặc người duy nhất “sở hữu” lỗi. |
| **Chuyên gia UX/accessibility** | Quan sát người dùng, đánh giá hành trình, khả năng sử dụng và tiếp cận. | Chỉ được mời sau khi giao diện đã xây xong. |
| **Chuyên gia bảo mật, pháp lý, riêng tư** | Làm rõ nghĩa vụ, mô hình đe dọa, kiểm soát và đánh giá rủi ro trong phạm vi thẩm quyền. | Chỉ xuất hiện ở ngày chuẩn bị phát hành hoặc bị bỏ qua khi có rủi ro cao. |
| **Vận hành/SRE/DevOps** | Độ tin cậy, observability, môi trường, triển khai, rollback, ứng cứu sự cố và phản hồi vận hành. | Chỉ nhận sản phẩm như một “gói đã xong” không có hướng dẫn hay cách giám sát. |
| **Scrum Master** | Hỗ trợ áp dụng Scrum và hiệu quả Scrum Team, giúp gỡ trở ngại ảnh hưởng chất lượng và cộng tác. | Bị biến thành người duyệt test hoặc người giao task kiểm thử. |
| **Người dùng, khách hàng, stakeholder** | Xác nhận vấn đề, quy tắc và kết quả sử dụng thực tế. | Bị xem là người phải phát hiện toàn bộ lỗi kỹ thuật trên production. |

**Trong Scrum Guide 2020**, Scrum Team gồm **Product Owner, Scrum Master và Developers**. “Developers” là accountability dành cho những người tạo các khía cạnh của Increment có thể sử dụng; một người chuyên kiểm thử có thể thuộc Developers. Các hàng trong bảng chỉ là **năng lực thực hành**, không tạo thêm vai trò Scrum chính thức.

### 3.3. Phải có người chịu trách nhiệm quyết định cụ thể

Trách nhiệm chung **không được biến thành “mọi người chịu trách nhiệm nên chẳng ai quyết”**. Ví dụ:

- Ai xác nhận **quy tắc đăng ký trùng**? Product Owner phối hợp người có thẩm quyền nghiệp vụ.
- Ai quyết định **cơ chế kiểm soát giao dịch**? Developers với chuyên gia kiến trúc/dữ liệu phù hợp, theo chính sách tổ chức.
- Ai quyết định **có được mở tính năng cho khách hàng**? Người có quyền phát hành theo quy trình sản phẩm/vận hành đã định.
- Ai cập nhật **mức rủi ro sự cố bảo mật**? Chủ sở hữu rủi ro và người có chuyên môn theo chính sách.
- Ai tuân thủ **DoD khi tạo Increment trong Scrum**? Developers; Scrum Team cùng chịu trách nhiệm tạo Increment có giá trị.

Nhóm nên thống nhất **người quyết định, người thực hiện, người cần tham vấn và người cần được thông báo** cho các rủi ro quan trọng. Việc này giúp quyền tự chủ đi cùng accountability mà không cần tầng phê duyệt cho mọi thao tác nhỏ.

## 4. Chất lượng xuyên suốt vòng đời: từ ý tưởng đến vận hành

### 4.1. Nhìn toàn bộ vòng phát triển

~~~mermaid
flowchart LR
    A["Discovery / phản hồi nhu cầu"] --> B["Backlog / làm rõ"]
    B --> C["Thiết kế / phân tích rủi ro"]
    C --> D["Code + kiểm thử sớm"]
    D --> E["Tích hợp + kiểm chứng"]
    E --> F["Bàn giao / phát hành"]
    F --> G["Vận hành / quan sát"]
    G --> H["Phản hồi và cải tiến"]
    H -. "Thông tin mới" .-> A
    H -. "Cập nhật rủi ro, ưu tiên" .-> B
~~~

Đây là **chuỗi hoạt động để tư duy**, không phải các phòng ban phải bàn giao tuần tự. Trong Agile, một nhóm liên chức năng có thể thực hiện nhiều hoạt động song song, quay lại làm rõ khi học thêm và giao những lát cắt nhỏ thường xuyên.

### 4.2. Chất lượng cần được tạo ở từng bước

| Giai đoạn | Câu hỏi chất lượng | Cách phát hiện/phòng ngừa sớm |
| --- | --- | --- |
| **Khám phá vấn đề** | Người dùng thực sự gặp khó khăn gì? | Phỏng vấn, quan sát tác vụ, thử giả thuyết, phân biệt outcome với output. |
| **Backlog / refinement** | Điều kiện đúng/sai, ranh giới và ngoại lệ đã rõ chưa? | Ví dụ chấp nhận, trao đổi nghiệp vụ–phát triển–kiểm thử, phân tích rủi ro. |
| **Thiết kế** | Dữ liệu, quyền, tích hợp và lỗi từng phần có được xử lý? | Review thiết kế, threat modeling phù hợp, thử mô hình, phân tích failure modes. |
| **Phát triển** | Thay đổi có thể kiểm chứng mà không phá hành vi cũ? | Unit tests, TDD khi phù hợp, pairing, code review, static analysis. |
| **Tích hợp** | Các phần có hoạt động cùng nhau ở phiên bản chung? | CI, contract/integration tests, môi trường tái hiện được, dữ liệu test an toàn. |
| **Kiểm chứng trước bàn giao** | Lát cắt có đáp ứng tiêu chí chấp nhận và chuẩn chất lượng? | Exploratory/E2E/nonfunctional tests theo rủi ro, DoD, kiểm tra triển khai. |
| **Phát hành** | Có thể thay đổi hệ thống một cách kiểm soát và khôi phục khi cần? | Release policy, quyền, rollout, smoke test, monitoring, rollback kế hoạch. |
| **Vận hành** | Người dùng có nhận giá trị và hệ thống có hoạt động tin cậy? | Telemetry, incident response, phản hồi hỗ trợ, phân tích outcome và lỗi. |
| **Cải tiến** | Điều kiện nào khiến lỗi xuất hiện/lọt qua và cách làm nào có tác dụng? | Retrospective, post-incident review, thử thay đổi nhỏ có số đo. |

Chất lượng **không thể “kiểm thử thêm” ở cuối để bù cho mọi quyết định thiếu thông tin**. Ví dụ, nếu quy tắc nghiệp vụ chưa xác định ai được quyền hủy khóa đã bắt đầu, test chỉ có thể xác nhận một giả định, chưa biết giả định ấy có đúng hay không.

### 4.3. Không cần tất cả bước dưới hình thức cuộc họp

Một đội nhỏ có thể làm rõ quy tắc bằng cuộc trao đổi 15 phút và ví dụ trong ticket. Một hệ thống thanh toán nghiêm trọng có thể cần review chuyên môn, bằng chứng truy vết và phê duyệt theo chính sách. **Mức hoạt động và tài liệu cần tương xứng với rủi ro**, nhưng tiêu chuẩn bắt buộc không thể bị bỏ qua chỉ để giảm thủ tục.

## 5. Làm rõ yêu cầu bằng ví dụ thay vì đợi lỗi xuất hiện

### 5.1. “Three Amigos” và chất lượng ngay từ refinement

Một kỹ thuật hữu ích là **Three Amigos**: kết hợp các góc nhìn **nghiệp vụ, phát triển và kiểm thử** để làm rõ cách hành vi phải hoạt động. Không bắt buộc đúng ba người hay ba chức danh. Với dữ liệu nhạy cảm, có thể mời thêm người hiểu quyền riêng tư; với tải lớn, thêm chuyên gia hiệu năng.

Ví dụ user story:

> Là học viên đã đăng nhập, tôi muốn đăng ký khóa miễn phí còn chỗ để tham gia học mà không phải nhờ nhân viên hỗ trợ.

Các câu hỏi cần trả lời:

1. Học viên như thế nào là **đủ điều kiện**?
2. “Còn chỗ” được tính tại thời điểm hiển thị hay khi yêu cầu được xác nhận?
3. Nếu gửi hai yêu cầu giống nhau, kết quả phải ra sao?
4. Nếu hai học viên tranh chỗ cuối, hệ thống quyết định và báo kết quả như thế nào?
5. Học viên có thể xem/sửa đăng ký của người khác không?
6. Nếu API timeout sau khi đã lưu thành công, lần thử lại phải xử lý ra sao?
7. Phần nào được làm trong lát cắt đầu; phần nào thuộc roadmap sau?

Những câu hỏi này **tạo chất lượng trước khi có mã** vì chúng ngăn nhóm triển khai các giả định không thống nhất.

### 5.2. Tiêu chí chấp nhận có thể kiểm chứng

Một số ví dụ gần cú pháp Gherkin:

~~~gherkin
Feature: Đăng ký khóa học miễn phí

  Scenario: Đăng ký thành công
    Given học viên A đã đăng nhập và chưa có đăng ký hiệu lực cho khóa X
    And khóa X còn ít nhất một chỗ
    When A xác nhận đăng ký khóa X
    Then hệ thống lưu đúng một đăng ký hiệu lực cho A
    And A thấy trạng thái xác nhận chính xác

  Scenario: Yêu cầu bị lặp
    Given A đã có đăng ký hiệu lực cho khóa X
    When A gửi lại yêu cầu đăng ký khóa X
    Then hệ thống không tạo đăng ký hiệu lực thứ hai
    And A nhận được trạng thái hiện hành

  Scenario: Hai học viên cùng chọn chỗ cuối
    Given khóa X chỉ còn một chỗ
    When A và B đều đủ điều kiện và cùng gửi yêu cầu đăng ký X
    Then tối đa một đăng ký mới được xác nhận
    And tổng số đăng ký hiệu lực không vượt sức chứa của X

  Scenario: Truy cập trái quyền
    Given học viên B không có quyền đọc thông tin đăng ký riêng của A
    When B yêu cầu xem đăng ký của A
    Then hệ thống từ chối truy cập

  Scenario: Gửi lại sau khi kết quả mạng không rõ
    Given yêu cầu đầu tiên của A đã được lưu hợp lệ
    And phản hồi mạng tới A bị gián đoạn
    When A thử gửi lại yêu cầu đăng ký cùng khóa
    Then hệ thống không tạo tác động đăng ký trùng
    And A có thể biết trạng thái đăng ký thực tế
~~~

Gherkin giúp **mô tả ví dụ có thể trao đổi**, nhưng chưa tự trở thành test chạy được nếu chưa có mã kiểm thử, dữ liệu và môi trường đúng. Ngay cả test tự động xanh cũng chưa chứng minh mọi kịch bản đã được nghĩ tới.

### 5.3. Kiểm tra cả ví dụ dương và âm

| Loại ví dụ | Mục đích | Trường hợp đăng ký |
| --- | --- | --- |
| **Happy path** | Hành vi bình thường có giá trị. | Một học viên hợp lệ đăng ký còn chỗ. |
| **Boundary value** | Kiểm tra biên giới hạn. | Còn một chỗ, vừa hết chỗ, sức chứa bằng 0. |
| **Negative case** | Kiểm tra từ chối hợp lệ. | Không đăng nhập, sai quyền, khóa hết chỗ. |
| **Concurrency** | Kiểm tra các hành động gần đồng thời. | Hai người tranh chỗ cuối. |
| **Retry / idempotency** | Ngăn tác động lặp khi mạng lỗi. | Nhấn xác nhận hai lần, timeout rồi gửi lại. |
| **Integration failure** | Giữ dữ liệu đúng khi phụ thuộc lỗi. | Dịch vụ xác nhận hoặc DB trả lỗi từng phần. |
| **Experience / accessibility** | Kiểm tra khả năng dùng thực tế. | Có thông báo rõ và phản hồi cho công nghệ hỗ trợ. |

Không phải PBI nào cũng cần toàn bộ loại kiểm thử. Nhóm dùng **phân tích rủi ro** để chọn mức cần thiết. Với quy tắc không vượt sức chứa, kiểm thử đồng thời là phần quan trọng; với đổi nhãn nút nhỏ, cùng một bộ tải cao có thể không cần chạy lại thủ công nếu hệ thống đã có kiểm soát thích hợp.

## 6. Phân biệt acceptance criteria, Definition of Done và chính sách phát hành

### 6.1. Ba câu hỏi khác nhau

| Khái niệm | Câu hỏi trọng tâm | Ví dụ |
| --- | --- | --- |
| **Acceptance criteria** | Hạng mục cụ thể phải làm gì, trong điều kiện nào? | “Gửi đăng ký lặp không tạo bản ghi hiệu lực thứ hai.” |
| **Definition of Done (DoD)** | Increment cần đạt **chuẩn chất lượng chung** nào để gọi là hoàn tất? | “Mã tích hợp, các test bắt buộc đạt, quyền truy cập được kiểm chứng, có khả năng sử dụng.” |
| **Release policy** | Khi nào và bằng cách nào được đưa khả năng tới người dùng mục tiêu? | “Rollout cho nhóm thử, theo dõi lỗi và có phương án khôi phục.” |

Tiêu chí chấp nhận **không thay thế DoD**; DoD **không tự thay thế quy trình phát hành**; phát hành **không tự chứng minh giá trị người dùng đã đạt**.

### 6.2. DoD theo Scrum Guide 2020

Trong Scrum:

- **Definition of Done** là mô tả chính thức về trạng thái của **Increment** khi đáp ứng các tiêu chuẩn chất lượng cần thiết cho sản phẩm.
- **Developers** có trách nhiệm đưa chất lượng vào phần mềm bằng cách tuân thủ DoD.
- Nếu tổ chức có chuẩn DoD, Scrum Team tuân thủ chuẩn đó tối thiểu; nếu không có, Scrum Team tạo DoD phù hợp.
- Nhiều Scrum Team cùng làm **một sản phẩm** phải cùng định nghĩa và tuân thủ **một DoD chung**.
- Công việc **chưa đáp ứng DoD không được coi là một phần của Increment hoàn tất**; cũng không được trình bày như đã Done ở Sprint Review.
- Một Sprint có thể có nhiều Increment; một Increment đạt chuẩn có thể được phát hành trước Sprint Review. Review không phải cổng bắt buộc cho release.

**DoD là cam kết của Increment**, cùng với Product Goal là cam kết của Product Backlog và Sprint Goal là cam kết của Sprint Backlog. Chất lượng liên tục không làm thay đổi các accountabilities Scrum chính thức.

### 6.3. Ví dụ DoD dùng cho chức năng đăng ký

Nhóm có thể đề xuất một DoD phù hợp với hệ thống:

- [ ] Hành vi nghiệp vụ và trường hợp lỗi bắt buộc đã được kiểm chứng theo tiêu chí chấp nhận.
- [ ] Giao diện, API, dữ liệu và các thành phần phụ thuộc liên quan được tích hợp.
- [ ] Build, unit tests, integration/contract tests và các kiểm tra theo rủi ro đã đạt.
- [ ] Những kiểm soát về phân quyền, dữ liệu cá nhân và truy cập không hợp lệ đã được xác minh.
- [ ] Các trường hợp cạnh tranh, đăng ký lặp, lỗi giao dịch quan trọng được kiểm thử phù hợp.
- [ ] Không còn lỗi nghiêm trọng vi phạm tiêu chuẩn hoàn tất; trạng thái các rủi ro còn lại minh bạch.
- [ ] Review mã/thiết kế và điều kiện bảo mật hoặc tuân thủ cần thiết đã đạt.
- [ ] Tài liệu/hợp đồng API, migration, hướng dẫn vận hành và observability đã được cập nhật khi có ảnh hưởng.
- [ ] Increment có thể sử dụng trong phạm vi đã công bố và có bằng chứng cần thiết.

Đây là **checklist minh họa**, không phải một DoD bắt buộc cho mọi Scrum Team hay cho mọi loại PBI. Nhóm phải chọn mức tiêu chuẩn phù hợp với sản phẩm và chuẩn tổ chức. Với hệ thống dùng tiền thật, một số kiểm soát khác có thể là bắt buộc.

### 6.4. Tránh “đổi nghĩa Done” dưới áp lực thời hạn

Ví dụ:

> “API trả đúng trong demo, nhưng test cạnh tranh thất bại. Chúng ta chuyển sang Done rồi tạo bug sửa Sprint sau.”

Nếu đăng ký không vượt sức chứa là hành vi bắt buộc, cách làm ấy **đánh tráo trạng thái**. Nhóm nên:

1. Công khai điều kiện nào chưa đạt và tác động.
2. Phối hợp xử lý hoặc giảm phạm vi **tùy chọn** sau khi trao đổi đúng thẩm quyền.
3. Không bỏ kiểm tra an toàn/chất lượng bắt buộc để báo tiến độ đẹp.
4. Chỉ coi là Increment Done khi DoD thực sự được đáp ứng.

Ngược lại, nhóm cũng cần tránh DoD vô hạn gồm mọi bài test có thể tưởng tượng. Tiêu chuẩn phải **rõ, cần thiết, kiểm chứng được và duy trì được**.

## 7. Shift-left và shift-right: kiểm tra sớm, tiếp tục học sau bàn giao

### 7.1. Shift-left không phải giao hết kiểm thử cho lập trình viên

**Shift-left testing/quality** là đưa các hoạt động nhận diện rủi ro, làm rõ và kiểm chứng **sớm hơn** vào vòng phát triển. Ví dụ:

- Người kiểm thử cùng dự refinement để phát hiện kịch bản thiếu.
- Chuyên gia bảo mật xem một luồng xử lý dữ liệu nhạy cảm từ thiết kế.
- Developers viết test và chạy CI khi thay đổi còn nhỏ.
- Người làm UX thử một tương tác trước khi xây toàn bộ giao diện.

Ý tưởng là **sửa vấn đề khi chi phí thay đổi còn thấp**, không phải chuyển mọi công việc chuyên sâu của chuyên gia QA sang Developers và giải tán các năng lực cần thiết.

### 7.2. Shift-right không phải dùng production thay môi trường thử

**Shift-right** nhấn mạnh quan sát chất lượng trong **điều kiện sử dụng thực**: telemetry, log, traces, mức lỗi, hiệu năng, hỗ trợ khách hàng, thử nghiệm có kiểm soát và hậu kiểm sự cố.

Nó không có nghĩa:

- Đưa phần mềm chưa qua kiểm tra bắt buộc vào production để “test thật”.
- Dùng dữ liệu cá nhân của khách hàng một cách tùy tiện.
- Cho rằng có thể rollback mã thì mọi tác động dữ liệu đều tự hoàn tác.
- Bỏ nghĩa vụ an toàn, pháp lý hoặc quản lý sự cố.

**Shift-left và shift-right bổ sung nhau**: kiểm tra sớm giảm khả năng lỗi tới người dùng; quan sát sau triển khai phát hiện những điều môi trường thử không tái hiện hoặc những giả định về giá trị chưa đúng.

### 7.3. Vòng học hỏi liên tục

~~~mermaid
flowchart TD
    A["Nhu cầu và rủi ro"] --> B["Ví dụ / tiêu chí kiểm chứng"]
    B --> C["Thiết kế và mã có test"]
    C --> D["CI + kiểm thử tích hợp"]
    D --> E{"Đủ điều kiện Done / release?"}
    E -- "Chưa" --> F["Sửa, làm rõ hoặc điều chỉnh phạm vi"]
    F --> B
    E -- "Có" --> G["Rollout có kiểm soát"]
    G --> H["Quan sát, phản hồi, sự cố"]
    H --> I["Cải tiến sản phẩm và cách làm"]
    I --> A
~~~

Vòng phản hồi này có thể diễn ra nhiều lần trong Sprint hoặc trong luồng Kanban liên tục. Không phải chờ hết một giai đoạn kiểm thử tập trung cuối dự án.

## 8. Kỹ thuật phát triển giúp chất lượng được xây vào sản phẩm

### 8.1. TDD: kiểm tra hành vi theo vòng nhỏ

**Test-Driven Development (TDD)** thường theo nhịp **Red → Green → Refactor**:

1. **Red:** viết test thể hiện hành vi chưa có hoặc lỗi chưa sửa; xác nhận test thất bại vì lý do kỳ vọng.
2. **Green:** viết phần mã tối thiểu để test đạt.
3. **Refactor:** cải thiện cấu trúc, giữ hành vi được bảo vệ bởi test.

Ví dụ, nếu quy tắc nghiệp vụ là “một học viên chỉ có một đăng ký hiệu lực cho một khóa”, Developers có thể bắt đầu từ unit test quy tắc đơn lẻ rồi bổ sung integration test chứng minh ràng buộc trên dữ liệu thật và khi có request đồng thời.

TDD không tự thay thế kiểm chứng người dùng hoặc kiểm thử phân tán. Có những phần như giao diện trực quan, xử lý hiệu năng hoặc tích hợp bên thứ ba cần các kỹ thuật bổ sung.

### 8.2. Code review, pairing và collective ownership

| Thực hành | Tác dụng cho chất lượng | Rủi ro nếu áp dụng hình thức |
| --- | --- | --- |
| **Pair programming** | Phản hồi ngay, chia sẻ hiểu biết, phát hiện vấn đề thiết kế sớm. | Hai người cùng hiểu sai quy tắc thì vẫn sai; phải kiểm chứng nghiệp vụ. |
| **Code review** | Kiểm tra hành vi, tương thích, an toàn và khả năng bảo trì. | PR quá lớn hoặc reviewer thiếu thời gian tạo xác nhận hời hợt. |
| **Refactoring** | Giữ mã dễ hiểu và dễ thay đổi qua nhiều Sprint. | Thiếu test bảo vệ có thể làm thay đổi hành vi ngoài ý muốn. |
| **Continuous Integration** | Phát hiện lỗi tích hợp khi thay đổi còn nhỏ. | Pipeline xanh không chứng minh tất cả rủi ro được bao phủ. |
| **Collective code ownership** | Giảm phụ thuộc một cá nhân, tăng khả năng hỗ trợ nhau. | Vẫn cần quyền truy cập, quy tắc review và trách nhiệm rõ. |
| **Small changes / short-lived branches** | Giảm khối lượng cần hiểu mỗi lần tích hợp, dễ khoanh vùng lỗi. | Merge những phần chưa an toàn hoặc test không đáng tin có thể phá mainline. |

Những thực hành thường gắn với XP là **công cụ hỗ trợ chất lượng liên tục**, không phải những thao tác Scrum bắt buộc.

### 8.3. Ngăn lỗi trước khi nó đi xuống bước tiếp

Trong pipeline, nhóm có thể đặt các kiểm tra như lint, compile, unit tests, integration tests, contract tests, security scanning và thử nghiệm môi trường theo rủi ro. Một quy ước hữu ích:

> “Nếu kiểm tra bắt buộc của bản tích hợp thất bại, không tuyên bố bản ấy đủ điều kiện bàn giao. Cả nhóm chủ động sửa hoặc hoàn tác an toàn, sau đó mới tiếp tục.”

**Giữ mainline khỏe** làm phản hồi kỹ thuật đáng tin. Nếu CI thường xuyên đỏ và mọi người bỏ qua, khả năng bắt lỗi sớm giảm. Tuy nhiên, không phải mọi lỗi ở một công cụ phụ đều cần dừng toàn tổ chức; nhóm phải làm rõ **mức rủi ro và cổng kiểm tra bắt buộc**.

## 9. Thiết kế chiến lược kiểm thử theo rủi ro

### 9.1. Kiểm thử nhiều lớp vì mỗi lớp nhìn thấy điều khác

| Lớp / loại kiểm thử | Điều thường phát hiện tốt | Điều thường không chứng minh |
| --- | --- | --- |
| **Unit tests** | Quy tắc, thuật toán, biến đổi trạng thái phạm vi nhỏ. | Tính đúng đắn khi các dịch vụ và DB thật tương tác. |
| **Component tests** | Hành vi một thành phần với phụ thuộc được kiểm soát. | Toàn bộ hành trình người dùng hoặc cấu hình production. |
| **Contract tests** | Tính tương thích giao diện giữa consumer và provider. | Mọi lỗi nội bộ hoặc dữ liệu bất thường của hệ thống. |
| **Integration tests** | DB, API, transaction, message, dịch vụ phối hợp. | Trải nghiệm thật của người dùng và mọi đặc tính phi chức năng. |
| **End-to-end tests** | Một số hành trình quan trọng từ đầu tới cuối. | Mọi kết hợp, tải đồng thời hoặc lỗ hổng bảo mật. |
| **Exploratory testing** | Vấn đề chưa dự đoán được từ hành vi và phản hồi. | Khả năng chạy hồi quy lặp lại nhất quán nếu không ghi kết quả. |
| **Performance/load tests** | Độ trễ, throughput và điểm nghẽn khi chịu tải mô phỏng. | Khả năng đúng nghiệp vụ hoặc bảo mật trên mọi điều kiện. |
| **Security tests/reviews** | Một số lỗ hổng, quyền, cấu hình hoặc mối đe dọa. | Không có công cụ nào bảo đảm tuyệt đối không còn lỗ hổng. |
| **Accessibility/usability tests** | Khả năng tiếp cận, hiểu và thao tác của người dùng. | Không tự bảo đảm chính xác dữ liệu hoặc độ tin cậy backend. |
| **Resilience/recovery tests** | Khả năng phục hồi dưới lỗi thành phần, mất mạng, restart. | Giá trị sản phẩm hoặc mọi tương tác người dùng. |

**Test pyramid** là một mô hình hữu ích: nhiều kiểm tra nhanh, tập trung ở phạm vi nhỏ, cộng với số lượng có chủ đích các kiểm tra tích hợp và E2E. Nó không phải tỷ lệ bắt buộc như “70/20/10” áp cho mọi sản phẩm.

### 9.2. Bắt đầu từ kịch bản thất bại có hậu quả

Một bảng phân tích đơn giản:

| Rủi ro | Khả năng/tác động cần hiểu | Bằng chứng kiểm chứng phù hợp |
| --- | --- | --- |
| Đăng ký trùng khi retry | Có thể làm sai dữ liệu và tăng hỗ trợ. | Unit test + integration test lặp request, kiểm tra ràng buộc dữ liệu. |
| Vượt sức chứa khi hai người đăng ký | Gây xác nhận sai và tranh chấp. | Integration test cạnh tranh trên DB/transaction phù hợp. |
| Học viên xem dữ liệu người khác | Rủi ro riêng tư nghiêm trọng. | Kiểm thử phân quyền ở API và kiểm tra ranh giới dữ liệu. |
| API đối tác thay đổi | Gây lỗi tích hợp không thấy ở unit test. | Contract test, integration test, thông báo thay đổi. |
| Kết quả trả về khó hiểu | Người dùng thử lại, tạo yêu cầu hỗ trợ. | Quan sát người dùng, exploratory/usability test. |
| Hệ thống chậm khi mở đăng ký | Người học không hoàn tất tác vụ, tải tăng bất thường. | Load/performance test với mức tải có cơ sở. |
| Lỗi sau triển khai không được phát hiện | Kéo dài sự cố và thiệt hại. | Observability, alert, smoke test và thực hành ứng cứu. |

**Không suy ra mức rủi ro chỉ từ số lượng test hiện có.** Một chức năng thu học phí có thể cần kiểm soát tài chính và nghĩa vụ pháp lý ngoài những ví dụ ở đây. Nhóm phải hỏi chuyên gia có thẩm quyền khi vượt năng lực.

### 9.3. Rủi ro được đánh giá lại khi có thông tin mới

Ban đầu nhóm tưởng đăng ký chỉ có một người thao tác mỗi lần. Khi mở lớp giới hạn chỗ, tải cùng lúc tăng mạnh. **Khả năng xảy ra lỗi đồng thời thay đổi**, nên test, kiến trúc và chính sách release có thể cần cập nhật.

Việc bổ sung kiểm thử sau khi thấy rủi ro mới là hành vi Agile đúng. Nhưng nếu điều kiện chất lượng bắt buộc chưa đạt, nhóm phải nói **chưa Done** thay vì cho rằng “yêu cầu mới xuất hiện nên có thể bỏ qua”.

## 10. Chất lượng xuyên hệ thống: bảo mật, hiệu năng, dữ liệu và khả năng tiếp cận

### 10.1. Nhiều rủi ro không nằm trong một user story đơn lẻ

Một user story có thể mô tả đăng ký khóa học, nhưng các chất lượng nền như quyền riêng tư, khả năng quan sát hoặc tính tương thích của API ảnh hưởng **nhiều lát cắt sản phẩm**. Nếu không có người chịu trách nhiệm định nghĩa và kiểm tra chính sách chung, nhóm dễ lặp lỗi.

Các câu hỏi nên được đặt sớm:

| Khía cạnh | Câu hỏi thiết kế | Cách kiểm chứng |
| --- | --- | --- |
| **Bảo mật** | Ai được gọi API; xác thực và phân quyền ở đâu? | Test truy cập trái quyền, review mô hình mối đe dọa khi rủi ro cao. |
| **Riêng tư** | Dữ liệu nào cần lưu, ai đọc, bao lâu được giữ? | Kiểm tra quyền, luồng dữ liệu, chính sách lưu/xóa áp dụng. |
| **Tính nhất quán** | Khi lỗi từng phần hoặc nhiều request cùng đến, dữ liệu có đúng không? | Test transaction, retry, rollback, idempotency. |
| **Khả dụng và phục hồi** | Mất phụ thuộc thì người dùng nhận trạng thái nào? | Simulate failure, test retry có giới hạn, kiểm tra khôi phục. |
| **Hiệu năng** | Độ trễ nào ảnh hưởng người dùng ở tải nào? | Đo trên môi trường/đầu vào đại diện, kiểm tra ngưỡng đã thống nhất. |
| **Tiếp cận** | Người dùng bàn phím, trình đọc màn hình có thực hiện tác vụ được không? | Kiểm thử công cụ phù hợp và đánh giá thủ công bởi người có chuyên môn. |
| **Khả năng bảo trì** | Người sau có hiểu và sửa an toàn không? | Review, static analysis, test, tài liệu ngắn đúng chỗ. |
| **Khả năng vận hành** | Có phát hiện và điều tra được lỗi sớm không? | Traces/metrics/logs, cảnh báo và diễn tập theo rủi ro. |

### 10.2. Đừng coi kiểm tra tự động là bảo đảm tuyệt đối

Một công cụ quét bảo mật có thể bỏ sót sai sót nghiệp vụ; kiểm thử hiệu năng có thể không phản ánh tải ngày mở lớp; công cụ accessibility có thể không hiểu nhãn thông báo người dùng nghe có rõ không. Chất lượng cần **phối hợp bằng chứng từ công cụ, người có chuyên môn và thử nghiệm sử dụng**.

### 10.3. Bảo vệ dữ liệu khi kiểm thử

Nhóm không nên sao chép dữ liệu cá nhân production vào môi trường test hoặc log tùy tiện. Cần cân nhắc:

- Dùng dữ liệu giả, dữ liệu tổng hợp hoặc dữ liệu đã xử lý an toàn khi phù hợp.
- Giới hạn quyền truy cập và thời gian lưu theo quy định.
- Không lộ secrets trong pipeline, ảnh chụp và báo cáo lỗi.
- Kiểm tra việc tẩy dữ liệu, quyền truy cập và chính sách sử dụng dữ liệu thật nếu được phép.
- Khi thử nghiệm với người dùng, có cơ chế đồng ý, giải thích mục đích và bảo vệ quyền riêng tư theo yêu cầu áp dụng.

**Chất lượng của kiểm thử không thể đạt bằng cách tạo một lỗ hổng dữ liệu mới.**

## 11. Chất lượng trong CI/CD: kiểm chứng mỗi thay đổi nhỏ

### 11.1. Continuous Integration hỗ trợ trách nhiệm chung thế nào?

**Continuous Integration (CI)** khuyến khích đưa các thay đổi nhỏ vào dòng phát triển chung thường xuyên và kiểm tra bản tích hợp bằng những phép kiểm chứng tự động thích hợp. Trong một nhóm liên chức năng:

- Developers chịu trách nhiệm viết thay đổi và test phù hợp với hành vi/rủi ro.
- Người có chuyên môn kiểm thử giúp chọn những phép kiểm chứng có khả năng phát hiện sai sót, cải thiện dữ liệu và chiến lược automation.
- Người hiểu kiến trúc, bảo mật hoặc vận hành tham gia xây các kiểm tra cần thiết cho hệ thống.
- Cả nhóm quan sát và sửa lỗi mainline/pipeline, không coi “test của QA” là hệ thống riêng.

Một pipeline chạy liên tục nhưng nhiều nhánh chỉ ghép vào cuối Sprint **không tạo phản hồi tích hợp sớm**. Ngược lại, tích hợp liên tục mà không có phép kiểm chứng thích hợp có thể làm dòng chung thường xuyên hỏng.

### 11.2. Một pipeline minh họa

~~~mermaid
flowchart TD
    A["Thay đổi nhỏ / PR"] --> B["Static checks + build"]
    B --> C["Unit tests"]
    C --> D["Contract / integration tests theo rủi ro"]
    D --> E{"Kiểm tra bắt buộc đạt?"}
    E -- "Không" --> F["Điều tra, sửa hoặc hoàn tác an toàn"]
    F --> A
    E -- "Có" --> G["Review và merge vào mainline"]
    G --> H["Kiểm tra bản tích hợp chung"]
    H --> I{"Đã đủ DoD và điều kiện bàn giao?"}
    I -- "Chưa" --> J["Tiếp tục hoàn thiện / kiểm chứng"]
    J --> D
    I -- "Có" --> K["Release có kiểm soát và quan sát"]
~~~

Sơ đồ chỉ là **ví dụ cách tổ chức cổng kiểm tra**, không bắt buộc thứ tự hoặc công cụ. Một số kiểm tra có thể chạy song song, trên merge queue, theo mốc môi trường hoặc trước phát hành tùy loại rủi ro. Bất kể sắp xếp ra sao, phải phân biệt **kiểm tra đã chạy đạt**, **kiểm tra chưa chạy**, và **kiểm tra đã chạy thất bại**.

### 11.3. Quy tắc khi pipeline đỏ

Một working agreement có thể là:

1. Check bắt buộc trên mainline thất bại phải được hiển thị và xử lý ưu tiên theo tác động.
2. Người nắm bối cảnh thay đổi phối hợp người có năng lực để xác định nguyên nhân; không mặc định quy lỗi cá nhân.
3. Tách **lỗi sản phẩm, lỗi test, lỗi môi trường và test không ổn định** dựa trên bằng chứng.
4. Sửa hoặc revert an toàn nếu cần, giữ dấu vết và kiểm chứng lại bản tích hợp.
5. Không đánh dấu kiểm tra là “đạt” chỉ vì bỏ qua, rerun ngẫu nhiên hoặc không có môi trường để chạy.
6. Sau khôi phục, cải thiện test, pipeline hoặc quá trình review nếu có nguyên nhân lặp lại.

Khi có sự cố lộ dữ liệu hoặc lỗi ảnh hưởng người dùng, phải kích hoạt **quy trình ứng cứu phù hợp** thay vì chờ một nhịp họp định kỳ.

### 11.4. Cổng kiểm tra nên bảo vệ rủi ro, không chỉ chặn tiến độ

Một *quality gate* tốt có:

- **Mục đích rõ:** bảo vệ hành vi, dữ liệu hay nghĩa vụ nào?
- **Tiêu chuẩn minh bạch:** điều kiện kiểm tra và quyền ra quyết định.
- **Phản hồi hữu ích:** lỗi có thông tin đủ để tái hiện và sửa.
- **Chi phí tương xứng:** tối ưu thời gian chạy nhưng không bỏ kiểm soát bắt buộc.
- **Cách cải tiến:** nếu gate hay báo sai hoặc ít phát hiện vấn đề, nhóm đo và sửa.

Ví dụ, PR thay văn bản hướng dẫn có thể không cần chạy thủ công một bài thử tải 30 phút nếu thay đổi không ảnh hưởng đường xử lý. Nhưng PR sửa cơ chế giữ chỗ phải có kiểm chứng tính nhất quán cần thiết trước khi được coi là hoàn tất. **Tối ưu pipeline** là đặt phép kiểm tra vào đúng mốc, không đồng nghĩa bỏ những phép kiểm tra quan trọng.

## 12. Ví dụ xuyên suốt: cùng chịu trách nhiệm xây luồng đăng ký khóa học

### 12.1. Bối cảnh sản phẩm và mục tiêu

Một Scrum Team thuộc nền tảng học trực tuyến có **Product Goal** minh họa:

> Học viên đủ điều kiện có thể tự đăng ký khóa học miễn phí qua web và nhận trạng thái chính xác, không cần nhân viên xử lý những trường hợp thông thường.

Trong Sprint gần, nhóm thống nhất **Sprint Goal**:

> Học viên thử nghiệm có thể đăng ký một khóa miễn phí còn chỗ; hệ thống bảo vệ dữ liệu, không tạo đăng ký trùng và phản hồi rõ kết quả.

Nhóm có các năng lực frontend, backend, kiểm thử, thiết kế giao diện và hỗ trợ triển khai. **Tất cả đóng góp cho Increment**, thay vì tạo một chuỗi bàn giao “nghiệp vụ xong → code xong → QA xong → vận hành tự xử lý”.

### 12.2. Bước A — Làm rõ giá trị và những điều không được sai

Product Owner cùng người hiểu nghiệp vụ xác nhận phạm vi:

- Học viên phải đăng nhập và đủ điều kiện tham gia.
- Chỉ hỗ trợ khóa học **miễn phí**, còn chỗ, trong phạm vi thử nghiệm.
- Một học viên không có hai đăng ký hiệu lực cho cùng khóa.
- Hệ thống không xác nhận nhiều chỗ hơn sức chứa, kể cả khi request gần đồng thời.
- Không truy cập, sửa dữ liệu của học viên khác trái quyền.
- Có kết quả rõ nếu hết chỗ, request lặp hoặc hệ thống không chắc trạng thái sau timeout.

Tính năng thanh toán, danh sách chờ, hủy đăng ký và SMS **chưa thuộc lát cắt đầu** nếu không phải yêu cầu bắt buộc. Thu hẹp phạm vi giúp nhóm có thể tạo Increment có giá trị sớm; **không được thu hẹp bằng cách bỏ những điều kiện đúng đắn đã cam kết**.

### 12.3. Bước B — Đặt rủi ro và kỹ thuật kiểm chứng cạnh nhau

| Rủi ro cụ thể | Người góp góc nhìn | Cách phát hiện sớm | Kiểm chứng trước Done |
| --- | --- | --- | --- |
| Hai người giành chỗ cuối | PO, backend, QA, chuyên gia dữ liệu nếu cần | Ví dụ nghiệp vụ tranh chấp chỗ; thiết kế transaction. | Integration test đồng thời và kiểm tra ràng buộc sức chứa. |
| Gửi lại tạo đăng ký trùng | UX, backend, QA | Ví dụ timeout/nhấn hai lần; thảo luận idempotency. | Test lặp request, dữ liệu không trùng, trạng thái rõ. |
| Đọc dữ liệu người khác | Backend, security, QA | Phân tích quyền và ranh giới tài khoản. | API authorization tests, kiểm tra dữ liệu trả về. |
| API và UI hiểu khác trạng thái | Frontend, backend, QA | Mẫu response và contract chung. | Contract/integration test, thử UI trên dữ liệu thật. |
| Học viên không hiểu thông báo | PO, UX, QA, học viên đại diện | Prototype, kiểm tra nội dung. | Quan sát người dùng thử, điều chỉnh thông báo. |
| Không nhìn thấy lỗi sau rollout | Developers, vận hành | Thiết kế correlation ID và chỉ số nghiệp vụ phù hợp. | Kiểm tra logs/metrics/alert, smoke test trên môi trường đích. |

Bảng này không biến mỗi nguy cơ thành một cuộc họp hoặc tài liệu riêng. Nó giúp **đưa chuyên môn phù hợp vào đúng thời điểm**, sau đó chọn bằng chứng cần có.

### 12.4. Bước C — Chia công việc thành lát cắt sử dụng được

Một kế hoạch yếu:

~~~text
Tuần 1: backend hoàn tất
Tuần 2: frontend hoàn tất
Tuần 3: chuyển sang kiểm thử
Tuần 4: tích hợp và sửa lỗi
~~~

Một cách tổ chức theo Agile là phối hợp sớm để có **một luồng đầu cuối** trong thời gian ngắn:

1. Tạo giao diện chọn khóa còn chỗ và hợp đồng API tối thiểu.
2. Tích hợp API với dữ liệu thật trong môi trường thử phù hợp.
3. Thêm ràng buộc dữ liệu và tình huống cạnh tranh, request lặp trước khi gọi luồng đăng ký Done.
4. Kiểm tra quyền, lỗi và khả năng sử dụng trên bản tích hợp.
5. Đưa Increment đáp ứng DoD tới nhóm học viên thử nghiệm theo chính sách.

Nhiều PR/commit nhỏ có thể hỗ trợ một PBI, nhưng **merge PR không tự là Increment**. Một bộ mã đang ẩn sau feature flag chưa đủ hành vi hoặc chưa đạt DoD vẫn là công việc đang làm, dù đã tích hợp an toàn vào mainline.

### 12.5. Bước D — Lập ma trận test tối thiểu cho lát cắt

| Kịch bản | Ví dụ đầu vào | Kết quả cần chứng minh | Mức kiểm chứng khả dĩ |
| --- | --- | --- | --- |
| Đăng ký hợp lệ | A chưa đăng ký, còn 5 chỗ. | Lưu một đăng ký hiệu lực; phản hồi chính xác. | Unit + integration + E2E đại diện. |
| Đăng ký lặp | A gửi hai request cùng khóa. | Không tăng bản ghi hiệu lực lần thứ hai. | Unit + integration/idempotency. |
| Hết chỗ | Khóa còn 0 chỗ. | Từ chối phù hợp, dữ liệu giữ nguyên. | Unit + API/integration. |
| Tranh chỗ cuối | A và B cùng gửi, còn 1 chỗ. | Tối đa một request được xác nhận; không vượt sức chứa. | Concurrency integration test trên DB phù hợp. |
| Sai quyền | B đọc đăng ký của A. | Từ chối, không lộ dữ liệu. | Authorization API test + review. |
| Timeout sau commit | Server lưu thành công nhưng phản hồi bị mất. | Retry không tạo tác động trùng; người dùng biết trạng thái thực. | Fault/retry integration test. |
| Trạng thái giao diện | Nhận thành công, hết chỗ, lỗi tạm thời. | Nội dung rõ, không gây nhầm trạng thái cuối. | Component/E2E + usability review. |

Đây là bộ **ví dụ học tập**, chưa phải đặc tả đầy đủ cho hệ thống thật. Tùy rủi ro, cần thêm kiểm thử hiệu năng, phục hồi, hành vi đa trình duyệt, hỗ trợ tiếp cận và các chính sách tổ chức.

### 12.6. Bước E — Chất lượng được kiểm tra ngay trong Sprint

Một diễn biến minh họa:

| Thời điểm | Điều nhóm làm | Điều học được |
| --- | --- | --- |
| **Đầu Sprint** | PO, Developers và chuyên gia kiểm thử thảo luận tình huống tranh chỗ cuối. | Phát hiện cần bảo vệ tính nhất quán dữ liệu. |
| **Khi thiết kế** | Backend và người hiểu DB kiểm tra cơ chế transaction. | Có một lựa chọn an toàn hơn so với “đọc rồi ghi” đơn giản. |
| **Khi triển khai** | PR nhỏ, review, CI chạy test tương ứng. | Lỗi API/contract hiện ra khi thay đổi còn hẹp. |
| **Khi tích hợp** | Frontend và backend ghép luồng; QA khám phá các tình huống bị lỗi. | Phát hiện thông báo hết chỗ chưa rõ. |
| **Khi test đồng thời** | Test tranh chỗ cuối thất bại. | Chưa đạt điều kiện chất lượng; nhóm phải sửa trước Done. |
| **Sau khi sửa** | Re-run test, kiểm tra quyền và hồi quy, xem DoD. | Increment có thể được xác nhận nếu mọi điều kiện đạt. |
| **Khi rollout thử** | Theo dõi lỗi và phản hồi học viên. | Có dữ liệu về khả năng dùng và rủi ro còn lại. |

Điểm quan trọng là **không có giai đoạn “đợi QA ở cuối”**. Chuyên gia kiểm thử tham gia từ việc đặt câu hỏi, Developers tự kiểm chứng, PO làm rõ nghiệp vụ và người vận hành giúp nhìn rủi ro thực tế.

### 12.7. Khi phát hiện lỗi bắt buộc ngày cuối

Giả sử kiểm thử đồng thời vẫn thất bại, nhưng một bên liên quan muốn demo đúng lịch. Nhóm cần minh bạch:

> “Luồng một người đã tích hợp, nhưng điều kiện không vượt sức chứa chưa đạt. Chúng tôi chưa thể gọi khả năng đăng ký là Done. Nhóm đang ưu tiên sửa và kiểm chứng, có thể hoãn phần lọc nâng cao để bảo vệ Sprint Goal và tiêu chuẩn chất lượng.”

Có thể **trình bày điều đã học** hoặc demo prototype với nhãn trạng thái rõ nếu thích hợp, nhưng không được giới thiệu một hạng mục chưa đạt DoD như Increment hoàn tất. Scrum Team có thể trao đổi lại dự báo/phạm vi trong khi giữ chất lượng bắt buộc.

### 12.8. Khi thử nghiệm cho người dùng

Ngay cả khi test xanh, học viên có thể không hiểu cách nhận biết đăng ký thành công. Nhóm nên quan sát một số tác vụ thật với sự đồng ý và phạm vi phù hợp, thu dữ liệu định tính/lượng hóa, rồi Product Owner quyết định xem **cải thiện thông báo** có nên được ưu tiên tiếp theo không.

Nếu hành vi mới **không vi phạm** tiêu chí đã thống nhất và DoD, đây có thể là một PBI cải tiến. Nếu một lỗi cho thấy hệ thống **không đáp ứng cam kết cũ**, nhóm phải đánh giá đó là defect cần xử lý, không gắn nhãn “yêu cầu mới” chỉ để tránh trách nhiệm.

## 13. Quản lý defect: sửa vấn đề và học từ điều kiện gây lỗi

### 13.1. Defect khác yêu cầu tính năng mới thế nào?

| Tình huống | Bản chất | Cách xử lý |
| --- | --- | --- |
| API trả dữ liệu người khác trái quyền đã quy định | **Defect / sự cố bảo mật** | Đánh giá mức độ ảnh hưởng, xử lý theo chính sách và kiểm chứng hồi quy. |
| Học viên muốn nhận SMS nhắc học dù trước đó chưa có yêu cầu | **Nhu cầu mới / cải tiến** | PO thảo luận giá trị, rủi ro, phụ thuộc và thứ tự backlog. |
| Test cho thấy đăng ký vượt sức chứa trong item chưa Done | **Không đạt hành vi đã cam kết** | Tiếp tục công việc/rework trong item, không tuyên bố Done. |
| Sau phát hành phát hiện trường hợp mạng mới chưa từng được xử lý đúng | **Defect cần đánh giá** | Ghi nhận, phân loại tác động, ưu tiên sửa và học từ thiếu sót test. |
| Người dùng mong có thêm loại khóa trả phí ngoài phạm vi miễn phí | **Mở rộng phạm vi** | Làm rõ PBI mới thay vì coi tính năng cũ chưa Done vô hạn. |

Mọi trường hợp cần dựa trên **điều đã cam kết, hành vi thực tế, rủi ro và bằng chứng**. Không kết luận “bug” hay “new feature” chỉ dựa vào người gửi ticket.

### 13.2. Phân biệt severity, priority và urgency

- **Severity:** hậu quả hoặc mức ảnh hưởng nếu lỗi xảy ra.
- **Priority:** thứ tự nên xử lý so với công việc khác, xét giá trị, rủi ro và phụ thuộc.
- **Urgency:** mức cấp bách về thời gian, chẳng hạn sự cố đang gây tác động hoặc hạn chót có hậu quả.

Một lỗi giao diện nhỏ có thể được ưu tiên sửa nhanh vì nằm ngay trong lát cắt đang giao; một lỗ hổng dữ liệu có thể cần kích hoạt ứng cứu ngay vì hậu quả nghiêm trọng. Không dùng số lượng lỗi làm đại diện cho severity.

### 13.3. Vòng đời xử lý lỗi minh bạch

~~~mermaid
flowchart TD
    A["Phát hiện / phản hồi lỗi"] --> B["Thu bằng chứng và đánh giá tác động"]
    B --> C{"Sự cố đang gây hại?"}
    C -- "Có" --> D["Ứng cứu và hạn chế ảnh hưởng theo chính sách"]
    C -- "Không" --> E["Xếp thứ tự và lập kế hoạch xử lý"]
    D --> F["Tái hiện và phân tích nguyên nhân"]
    E --> F
    F --> G["Sửa + bổ sung kiểm chứng"]
    G --> H["Review, integration, hồi quy"]
    H --> I{"Hành vi / chuẩn chất lượng đạt?"}
    I -- "Chưa" --> F
    I -- "Có" --> J["Bàn giao, giám sát và rút kinh nghiệm"]
~~~

Phần mềm phức tạp có thể có lỗi không tái hiện được ngay. Khi ấy nhóm vẫn cần mô tả mức bất định, dấu vết quan sát, phạm vi ảnh hưởng và bước điều tra tiếp; **không tự đánh dấu lỗi là “không tồn tại” chỉ vì không tái hiện được trong một môi trường**.

### 13.4. Lỗi trước Done và lỗi sau Done

Khi test phát hiện lỗi **trước mốc Done**, hạng mục có thể quay về bước sửa nhưng vẫn thuộc **cùng công việc chưa hoàn tất**; không tạo ticket mới chỉ để đếm thêm throughput.

Khi phát hiện lỗi **sau một Increment đã đáp ứng DoD và được bàn giao**, có thể tạo defect/incident mới, liên kết với thay đổi gốc và xử lý theo mức độ rủi ro. Điều này không có nghĩa mọi lỗi về sau chứng minh DoD trước kia đã được áp dụng gian dối; chất lượng phần mềm cần học từ tình huống chưa dự đoán được. Nếu thực tế hạng mục đã được đánh dấu Done **nhầm hoặc bỏ kiểm tra bắt buộc**, cần sửa dữ liệu và cải tiến điều kiện kiểm chứng một cách có dấu vết.

### 13.5. Dùng hậu kiểm để sửa hệ thống

Một lỗi lặp lại có thể dẫn đến câu hỏi:

1. Quy tắc nào chưa được làm rõ?
2. Thiết kế nào cho phép trạng thái sai?
3. Tại sao test không phát hiện hoặc không được chạy đúng lúc?
4. Có thay đổi API, dữ liệu hoặc cấu hình nào không được thông báo?
5. Có áp lực WIP, thời hạn hoặc trách nhiệm mơ hồ nào dẫn đến bỏ bước cần thiết?
6. Biện pháp nào ngăn lỗi tái diễn và làm sao kiểm chứng tác dụng?

Hậu kiểm **không tìm một cá nhân để làm vật thay lỗi**, nhưng vẫn có người nhận trách nhiệm sửa, người phê duyệt theo quyền và thời điểm kiểm tra kết quả. An toàn để báo lỗi đi cùng trách nhiệm chuyên nghiệp.

## 14. Chất lượng sau phát hành: vận hành và phản hồi là một phần của phát triển

### 14.1. Release không phải điểm kết thúc của việc học

Sau khi một Increment được mở cho người dùng phù hợp, những điều nhóm học thêm có thể bao gồm:

- Tỷ lệ đăng ký thành công thực tế so với kỳ vọng.
- Tình huống lỗi mạng và cách người dùng retry.
- Thời gian phản hồi ở tải mở lớp thật.
- Tỷ lệ yêu cầu hỗ trợ và những thông báo gây nhầm lẫn.
- Các lỗi dữ liệu, quyền hoặc tích hợp chưa xuất hiện trong môi trường thử.
- Những rủi ro vận hành mới khi lượng người dùng tăng.

Nhóm cần biến dữ liệu ấy thành **quyết định sản phẩm, kỹ thuật và vận hành**; nếu chỉ thu log mà không ai xem hoặc không có ngưỡng hành động, chất lượng vẫn có thể suy giảm âm thầm.

### 14.2. Observability phục vụ người dùng, không chỉ máy chủ

**Logging, metrics và tracing** giúp điều tra trạng thái; chúng không nên chứa thông tin nhạy cảm không cần thiết. Với luồng đăng ký, có thể quan sát:

| Tín hiệu | Điều có thể suy ra | Lưu ý |
| --- | --- | --- |
| Số yêu cầu đăng ký theo kết quả | Tần suất thành công, hết chỗ, lỗi tạm thời. | Cần phân biệt từ chối hợp lệ với sự cố sản phẩm. |
| Tỷ lệ trạng thái lỗi 5xx | Có vấn đề hạ tầng hoặc xử lý server. | Không phát hiện mọi lỗi nghiệp vụ trả 200 sai. |
| Độ trễ các API quan trọng | Người dùng có bị chờ quá lâu? | Cần xem phân bố và bối cảnh tải, không chỉ trung bình. |
| Số phát hiện dữ liệu đăng ký bất nhất | Có vi phạm ràng buộc nghiệp vụ? | Đây có thể là tín hiệu nghiêm trọng dù tỷ lệ nhỏ. |
| Số lần retry và timeout | Người dùng gặp kết quả không chắc chắn? | Xem idempotency và khả năng tra cứu trạng thái thật. |
| Lượng yêu cầu hỗ trợ về đăng ký | Trải nghiệm có gây nhầm lẫn? | Chịu ảnh hưởng quy mô người dùng và kênh hỗ trợ. |

Không thu thập dữ liệu cá nhân vượt mục đích chỉ để tăng mức quan sát; dùng mã tương quan, quyền truy cập và chính sách lưu giữ phù hợp.

### 14.3. Phân biệt SLI, SLO và SLA

Trong thực hành độ tin cậy:

- **SLI (Service Level Indicator):** số đo của một đặc tính dịch vụ, ví dụ tỷ lệ yêu cầu hợp lệ được xử lý thành công.
- **SLO (Service Level Objective):** mục tiêu nội bộ hoặc đã thống nhất cho SLI trong một khoảng đo.
- **SLA (Service Level Agreement):** thỏa thuận dịch vụ với các điều khoản/nghĩa vụ tương ứng; không tự đồng nhất với SLO.

Ví dụ minh họa: trong một kỳ đo, có **995/1.000** tác vụ đăng ký hợp lệ đáp ứng định nghĩa “thành công” đã thống nhất:

\[
\text{Tỷ lệ thành công}=\frac{995}{1000}\times100\%=99{,}5\%.
\]

Con số này **không nói lên tất cả chất lượng**: năm yêu cầu thất bại có thể gây thiệt hại khác nhau; mẫu đo, lỗi bị loại trừ và tải phải được mô tả. Tỷ lệ thành công cao cũng không chứng minh không có lỗ hổng phân quyền hoặc dữ liệu sai. Nếu chưa có dữ liệu nền, không tự đặt một SLO tưởng tượng rồi tuyên bố hệ thống đã đạt.

### 14.4. Triển khai có kiểm soát để giảm tác động

Các lựa chọn như **canary release**, **phát hành theo nhóm người dùng**, **feature flag**, **blue–green deployment** hoặc **rollback** có thể hỗ trợ giảm rủi ro khi áp dụng đúng.

Tuy nhiên:

- Flag ẩn nút không phải kiểm soát phân quyền của API.
- Canary không tự bảo vệ hệ thống khỏi việc sửa dữ liệu sai ở phạm vi nhỏ nhưng không thể hoàn tác.
- Revert code không tự thu hồi email, giao dịch hoặc dữ liệu đã gửi.
- Khi thay đổi schema, cần xét tương thích cũ/mới, kế hoạch migration và phục hồi.
- Hệ thống có yêu cầu an toàn hoặc tuân thủ nghiêm ngặt phải tuân thủ chính sách phát hành tương ứng.

**Triển khai nhỏ** giúp quan sát và hạn chế phạm vi ảnh hưởng; nó không phải giấy phép đưa thay đổi chưa qua kiểm chứng bắt buộc vào môi trường thật.

### 14.5. Post-incident review và việc học bền vững

Sau khi xử lý sự cố, nhóm có thể ghi:

1. Người dùng bị ảnh hưởng và thời gian tác động.
2. Timeline từ tín hiệu đầu tiên tới khôi phục.
3. Những điều kiện kỹ thuật và tổ chức góp phần gây lỗi.
4. Điều gì đã giúp phát hiện/giảm tác động, điều gì còn thiếu.
5. Những hành động có người sở hữu, mốc và bằng chứng hiệu quả.
6. Thay đổi cần làm ở DoD, test, monitoring, quy trình phát hành hoặc backlog.

Đừng đánh giá hậu kiểm bằng số trang hay số người được nêu tên. Giá trị của nó nằm ở **sự cố tương tự có ít khả năng tái diễn hoặc ít gây hại hơn** sau cải tiến.

## 15. Đo lường chất lượng liên tục mà không tạo chỉ số sai

### 15.1. Dùng một bộ tín hiệu cân bằng

| Nhóm số đo | Ví dụ | Câu hỏi cần trả lời |
| --- | --- | --- |
| **Chất lượng sản phẩm** | Mức nghiêm trọng của defect, lỗi sau phát hành, sai lệch dữ liệu, vi phạm quyền. | Sản phẩm có đáng tin trong phạm vi sử dụng? |
| **Khả năng phát hiện sớm** | Lỗi được tìm trong refinement, review, CI hay sau release. | Có thể chuyển việc học sớm hơn không? |
| **Độ tin cậy kiểm chứng** | Tỷ lệ job thất bại do flaky test, thời gian khôi phục pipeline, các check bắt buộc bị chặn. | Khi CI báo xanh/đỏ, nhóm có tin và hành động được không? |
| **Dòng công việc** | WIP, work item age, cycle time, throughput. | Công việc có bị chờ ở review, test hoặc phụ thuộc? |
| **Khả năng đưa thay đổi ra dùng** | Thời gian từ thay đổi tới triển khai, nhịp triển khai, sự cố do thay đổi và khả năng khôi phục. | Nhóm có giao nhanh mà vẫn giữ an toàn? |
| **Giá trị người dùng** | Tỷ lệ hoàn tất đăng ký, thời gian thao tác, phản hồi hỗ trợ. | Phần mềm đúng có giải quyết vấn đề cần thiết? |
| **Sự bền vững của nhóm** | Gián đoạn khẩn cấp, trực sự cố quá tải, công việc tồn đọng khó xử lý. | Hệ thống có đang yêu cầu con người bù đắp lỗi quy trình? |

Các nhóm có thể tham khảo thực hành **DORA** khi đo hiệu quả giao phần mềm và ổn định vận hành, nhưng **không nên coi một bộ metric là công thức đánh giá cá nhân**. Định nghĩa số đo và khung tham chiếu có thể được cập nhật; điều quan trọng là nhóm thống nhất chính xác cách tính, phạm vi và mục đích.

### 15.2. Defect escape rate — dùng được nhưng dễ bị hiểu sai

Giả sử theo **cùng một kỳ quan sát và cùng quy tắc ghi nhận**, nhóm phát hiện **30 lỗi trước bàn giao** và **5 lỗi sau bàn giao**. Một chỉ số mô tả có thể là:

\[
\text{Tỷ lệ lỗi phát hiện sau bàn giao}
=\frac{5}{30+5}\times100\%
\approx14{,}3\%.
\]

Đây là **ví dụ tính toán**, không phải bằng chứng hệ thống tốt hay xấu nếu chưa biết:

- Độ nghiêm trọng của năm lỗi sau bàn giao.
- Phạm vi và mức phơi nhiễm người dùng.
- Mức độ kiểm tra và khả năng phát hiện ở mỗi giai đoạn.
- Quy tắc đếm lỗi trùng, lỗi được báo nhiều lần và khoảng thời gian.
- Việc đội có được khuyến khích báo lỗi trung thực không.

Nếu tổ chức thưởng cho nhóm có “ít lỗi được báo”, người làm có thể ngừng ghi nhận defect và chỉ số trông đẹp hơn trong khi chất lượng tệ đi.

### 15.3. Coverage: có ích nếu hiểu nó không đo điều gì

**Code coverage** có thể cho biết bao nhiêu câu lệnh/nhánh mã được thực thi trong các bài test, theo cách công cụ đo. Coverage **không chứng minh**:

- Các assertion kiểm tra đúng hành vi.
- Những trường hợp nghiệp vụ quan trọng đều được bao phủ.
- Không còn lỗi cạnh tranh, quyền riêng tư hoặc tích hợp.
- Những giá trị biên và điều kiện thất bại được xử lý.

**100% coverage không đồng nghĩa 100% chất lượng.** Một nhóm có thể theo dõi coverage để nhận diện vùng mã thiếu kiểm chứng, đồng thời sử dụng tiêu chí rủi ro, review và test khác để đánh giá chất lượng thật.

### 15.4. Đọc số liệu theo hệ thống, không phán xét cá nhân

Giả sử nhóm tăng tần suất triển khai, cycle time giảm nhưng số sự cố dữ liệu nghiêm trọng tăng. Không thể kết luận “Agile nhanh hơn nên thành công”. Nhóm cần xem liệu DoD có bị áp dụng thiếu, test chưa bao phủ điều kiện mới, thay đổi schema gây tương thích sai hoặc rollout chưa có giám sát phù hợp.

Ngược lại, số lỗi **được phát hiện trước phát hành** tăng có thể là tín hiệu tích cực nếu nhóm bổ sung kiểm chứng sớm. Cần phân biệt **nhiều lỗi được phát hiện** với **nhiều lỗi được tạo ra**, rồi xem tác động thực tế.

### 15.5. Định nghĩa thời gian và đơn vị rõ ràng

Nếu nhóm đo:

- **WIP:** số item đã Started nhưng chưa Finished tại thời điểm chụp.
- **Cycle time:** thời gian từ Started đến Finished của item đã hoàn tất.
- **Work item age:** thời gian từ Started đến hiện tại của item chưa hoàn tất.
- **Throughput:** số item Finished trong khoảng đo.

thì mốc Started/Finished phải được công bố và giữ nhất quán. Nếu trước đây “Done” nghĩa code merged, nay nghĩa đã triển khai và kiểm chứng cho người dùng, **không thể so cycle time hai giai đoạn như cùng một chỉ số** mà không chú thích thay đổi ranh giới.

## 16. Cân bằng tốc độ, chất lượng và chi phí thay đổi

### 16.1. “Làm nhanh” bằng cách bỏ chất lượng có thể làm chậm toàn hệ thống

Giả sử một nhóm muốn rút ngắn Sprint bằng cách bỏ integration tests. Họ có thể ghi nhận nhiều ticket Done trong tuần, nhưng nếu phải sửa lỗi dữ liệu sau triển khai và hỗ trợ khách hàng, **thời gian đưa giá trị đáng tin cậy tới người dùng** có thể còn dài hơn.

Một cách phân tích:

| Lựa chọn | Lợi ích ngắn hạn | Rủi ro/tác động dài hạn |
| --- | --- | --- |
| Bỏ mọi kiểm thử tích hợp | Giảm thời gian chạy test hiện tại. | Lỗi hợp đồng/transaction được phát hiện muộn, có thể gây tác động thực. |
| Tự động hóa kịch bản rủi ro cao | Chi phí xây bộ test ban đầu. | Phản hồi hồi quy nhanh và lặp lại được. |
| Chia lát cắt dọc nhỏ | Cần làm rõ phạm vi và hợp đồng. | Giao sớm, giảm thay đổi chưa tích hợp. |
| Giới hạn WIP | Có thể một thành viên tạm không bắt đầu task mới. | Giảm chờ, tăng khả năng hoàn tất chung. |
| Review thiết kế rủi ro cao | Thêm công sức trao đổi trước khi code. | Có thể tránh sửa lại nhiều thành phần hoặc sự cố nghiêm trọng. |
| Làm rõ acceptance criteria từ sớm | Cần sự tham gia của PO/người hiểu nghiệp vụ. | Giảm hiểu sai và đổi phạm vi ngầm. |

Lựa chọn tốt phải dựa trên **mức rủi ro, dữ liệu và mục tiêu**, không phải giả định rằng tăng quy trình luôn làm tăng chất lượng hoặc cắt quy trình luôn làm tăng tốc độ.

### 16.2. Kỹ thuật phòng ngừa lỗi có chi phí và lợi ích

Chất lượng liên tục bao gồm:

- **Prevention:** làm rõ yêu cầu, thiết kế, đào tạo, test sớm, review.
- **Appraisal/detection:** kiểm thử, rà soát, đo và kiểm chứng.
- **Failure/rework:** sửa lỗi trước hoặc sau bàn giao, khôi phục và hỗ trợ.

Các nhóm hoạt động này giúp tư duy về **chi phí chất lượng**, nhưng không cần lập một mô hình tiền tệ chính xác giả tạo cho mọi lỗi. Một bug khó tái hiện có thể gây thiệt hại uy tín hoặc riêng tư lớn hơn nhiều thời gian sửa mã; đánh giá kinh tế cần cân nhắc mức hậu quả và bất định.

### 16.3. Nợ kỹ thuật ảnh hưởng chất lượng tương lai

**Technical debt** mô tả những đánh đổi trong thiết kế hoặc mã có thể làm thay đổi sau này khó hơn. Không phải mọi đoạn mã chưa tối ưu là nợ nghiêm trọng; không phải mọi refactoring tạo giá trị ngang nhau.

Khi quyết định xử lý, nhóm có thể hỏi:

1. Cấu trúc hiện tại làm tăng lỗi, thời gian sửa hoặc phụ thuộc ở đâu?
2. Rủi ro nào sẽ xuất hiện nếu tiếp tục trì hoãn?
3. Có thể xử lý từng phần cùng thay đổi giá trị nào?
4. Kiểm thử nào giúp refactor an toàn?
5. Product Owner có hiểu lợi ích bảo vệ hoặc khả năng mở khóa tương lai không?

Không nên xem cải tiến kỹ thuật là “việc ngoài sản phẩm” trong mọi trường hợp, nhưng cũng không dùng nhãn “chất lượng” để thực hiện các dự án refactor không gắn với vấn đề hay bằng chứng.

### 16.4. Khi không đủ thời gian để đạt chất lượng cần thiết

Nhóm có thể:

- Thu hẹp **phạm vi tính năng tùy chọn** trong thỏa thuận với người có trách nhiệm giá trị.
- Chia nhỏ thành Increment thực sự có thể sử dụng và kiểm chứng.
- Dời quyết định phát hành hoặc dùng cơ chế triển khai phù hợp khi có rủi ro chưa thể chấp nhận.
- Đề nghị hỗ trợ chuyên môn, môi trường hoặc tháo gỡ phụ thuộc.
- Công khai giới hạn và thông tin chưa biết, cập nhật dự báo.

Không nên tự giảm DoD hoặc bỏ kiểm soát bảo mật/an toàn bắt buộc để giữ hình thức “đúng hạn”. **Thời hạn là một ràng buộc cần quản lý**, không tự biến phần mềm chưa đúng thành Done.

## 17. Phối hợp Scrum, Kanban, XP và Lean để duy trì chất lượng

### 17.1. Scrum: chất lượng được gắn vào Increment và mục tiêu

Trong Scrum:

- **Product Goal** định hướng trạng thái sản phẩm dài hạn.
- **Sprint Goal** tạo mục tiêu chung cho Sprint.
- **Definition of Done** minh bạch khi Increment đạt chuẩn chất lượng.
- **Developers** chọn cách thực hiện, thích ứng kế hoạch và tuân thủ DoD.
- **Product Owner** quản lý giá trị và Product Backlog, làm rõ các đánh đổi sản phẩm.
- **Scrum Master** hỗ trợ Scrum Team cải thiện hiệu quả và xử lý những trở ngại cần phối hợp.

Chất lượng cần được xây trong Sprint, không phải đặt một “Sprint kiểm thử” mặc định sau mỗi Sprint phát triển. Một Sprint có thể tạo nhiều Increment đạt DoD; những hạng mục chưa đạt DoD không được đếm như Increment hoàn tất.

### 17.2. Kanban: chất lượng xuất hiện trong chính sách luồng

Một nhóm dùng Kanban có thể định nghĩa:

- Điều kiện nhận một hạng mục từ backlog.
- Điều kiện chuyển từ Developing sang Review/Verify.
- WIP limit và chính sách pull.
- Cách ghi blocked, rework, lỗi và tuổi công việc.
- **Finished point** cùng bằng chứng cần có để gọi Done.
- Các flow metrics để phát hiện chờ và tắc nghẽn.

Nếu test thất bại trong Verify, **không chuyển thẻ Done để tăng throughput**. Item tiếp tục WIP cho tới khi đạt điều kiện; chất lượng và minh bạch phải được ưu tiên hơn số lượng thẻ đã đóng.

### 17.3. XP: chất lượng là hành vi kỹ thuật mỗi ngày

TDD, pairing, refactoring, CI, collective ownership và thay đổi nhỏ hỗ trợ kiểm chứng sớm. Nhưng kỹ thuật cần được nối với nhu cầu và rủi ro sản phẩm: unit tests nhiều không thay thế xem xét nghiệp vụ; CI xanh không thay thế kiểm tra tương thích dữ liệu và quyền.

### 17.4. Lean: tối ưu cả dòng giá trị, không đổ lỗi

Tư duy Lean nhấn mạnh:

- **Giảm lãng phí** như chờ review, làm lại và mở quá nhiều việc.
- **Tôn trọng con người:** người phát hiện lỗi có thể nói thật và nhận hỗ trợ.
- **Cải tiến liên tục:** thử thay đổi nhỏ, kiểm tra bằng chứng rồi điều chỉnh.
- **Nhìn toàn hệ thống:** không làm đẹp thời gian của nhóm A bằng cách đẩy sự cố hoặc thao tác thủ công sang nhóm B/người dùng.

### 17.5. Một chuỗi thực hành phối hợp

| Giai đoạn | Thực hành có thể dùng | Chất lượng được bảo vệ |
| --- | --- | --- |
| Làm rõ PBI | Three Amigos, ví dụ chấp nhận. | Hiểu đúng hành vi và ngoại lệ. |
| Chọn việc | Product Goal, backlog ordering, Kanban WIP. | Tập trung giá trị và không quá tải. |
| Thiết kế/triển khai | XP TDD, pairing, review, threat modeling. | Đúng logic, cấu trúc và kiểm soát theo rủi ro. |
| Tích hợp | CI, nhánh ngắn, contract/integration tests. | Các thành phần hoạt động cùng nhau. |
| Hoàn tất | DoD của Scrum hoặc chính sách Done minh bạch. | Không đánh tráo “đã code” với “đã dùng được”. |
| Phát hành/vận hành | Rollout, observability, incident response. | Giảm tác động, phát hiện vấn đề thực. |
| Cải tiến | Retrospective, Lean PDCA, postmortem. | Nguyên nhân hệ thống được xử lý, giảm tái diễn. |

Không cần áp toàn bộ nghi thức của các phương pháp cùng lúc. **Chọn thực hành có mục đích**, giữ nguyên các thành phần chính thức của framework mà nhóm tuyên bố áp dụng, và tránh tạo nhiều cổng duyệt không giúp nâng chất lượng.

## 18. Các phản mẫu làm mất trách nhiệm chung về chất lượng

| Phản mẫu | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| **“QA chịu toàn bộ chất lượng”** | Lỗi được đẩy xuống bước cuối, hiểu sai accountability. | Whole-team quality; chuyên gia kiểm thử đóng góp năng lực riêng. |
| **“Code complete” được gọi Done** | Chưa tích hợp, chưa xác minh rủi ro; số liệu sai. | DoD và bằng chứng hoàn tất chung. |
| **Chỉ kiểm thử trong một giai đoạn cuối** | Phát hiện muộn, phải sửa nhiều thành phần. | Làm rõ và test từ refinement tới CI, tiếp tục quan sát sau release. |
| **PO mô tả yêu cầu bằng câu mơ hồ** | Nhóm tự suy đoán hành vi, nhiều rework. | Ví dụ chấp nhận, hỏi tình huống biên và quyền. |
| **Automation xanh = chắc chắn đúng** | Sai nghiệp vụ ngoài coverage hoặc production vẫn lỗi. | Phân tầng bằng chứng, exploratory/usability/production feedback. |
| **Test đạt trên mock = tích hợp thật đạt** | Sai hợp đồng, schema hoặc transaction chỉ lộ sau merge. | Contract/integration tests trên môi trường phù hợp. |
| **Đóng bug cũ và mở bug mới trước Done** | Che giấu cycle time và việc chưa hoàn tất. | Rework trong cùng item; giữ trạng thái và lịch sử đúng. |
| **Bỏ test cạnh tranh để kịp release** | Rủi ro dữ liệu và trách nhiệm với người dùng. | Giữ tiêu chuẩn bắt buộc; thương lượng phạm vi/nhịp bàn giao. |
| **Chỉ đo số bug của từng cá nhân** | Khuyến khích che lỗi và đổ lỗi. | Đo hệ thống, severity, khả năng phát hiện và học hỏi. |
| **Yêu cầu 100% code coverage cho mọi module** | Tạo test hình thức và bỏ qua rủi ro thật. | Chọn kiểm chứng theo hành vi và mức rủi ro. |
| **Mainline đỏ kéo dài, vẫn nhận thêm việc** | Khó xác minh thay đổi, tích lũy rework. | Chính sách phục hồi tích hợp và ưu tiên sửa lỗi bắt buộc. |
| **Bảo mật chỉ xem ở ngày release** | Lỗ hổng kiến trúc và dữ liệu khó sửa muộn. | Đưa security/privacy vào thiết kế và test theo tác động. |
| **Không có quyền dừng một thay đổi nguy hiểm** | Nhân viên biết lỗi nhưng không thể hành động. | Quy tắc cảnh báo, người quyết định và kênh escalation rõ. |
| **Xem production là nơi thay test bắt buộc** | Người dùng gánh rủi ro chưa được kiểm soát. | Shift-right bổ sung, không thay thế kiểm chứng trước release. |
| **Rollback = revert code trong Git** | Dữ liệu, email và tác động ngoài hệ thống vẫn tồn tại. | Thiết kế migration, recovery và rollback theo rủi ro. |
| **Hậu kiểm để tìm một người chịu lỗi** | Mọi người giấu vấn đề, nguyên nhân hệ thống còn nguyên. | Post-incident review tập trung bằng chứng và hành động cải tiến. |
| **Giảm WIP hoặc cycle time bằng cách đổi tên Done** | Báo cáo cải thiện giả tạo, chưa giao giá trị. | Giữ ranh giới đo nhất quán, đối chiếu chất lượng và outcome. |
| **Chất lượng là một checklist dài không ai hiểu** | Tăng thủ tục, che rủi ro quan trọng. | Tiêu chuẩn theo sản phẩm, minh bạch và kiểm chứng được. |

## 19. Bài tập vận dụng và đáp án gợi ý

### Bài tập 1 — Nhận diện trách nhiệm chất lượng

Một Scrum Team đang tạo Increment đăng ký khóa học. Tình huống:

1. Product Owner chưa xác định rõ một học viên có được đăng ký lại cùng khóa không.
2. Developer nói: “Tôi viết API xong; QA tự kiểm thử phần dữ liệu”.
3. Chuyên gia kiểm thử phát hiện lỗi ở tình huống tranh chỗ cuối.
4. Scrum Master thấy môi trường tích hợp chưa được cấp quyền.
5. Người vận hành biết rollout có thể làm hệ thống vượt tải.

**Yêu cầu:** xác định hành động phù hợp của từng bên; ai có quyền quyết định và ai có trách nhiệm tạo Increment đạt DoD?

**Gợi ý:** PO làm rõ quy tắc với người có thẩm quyền; Developers phối hợp thiết kế, test, sửa và tuân thủ DoD; chuyên gia kiểm thử nêu bằng chứng và góp cách kiểm chứng; SM thúc đẩy gỡ trở ngại môi trường; vận hành nêu rủi ro release và đề nghị kiểm soát. Trong Scrum, **Developers** chịu trách nhiệm tuân thủ DoD khi tạo Increment, Scrum Team cùng chịu trách nhiệm giá trị. Không có vai trò nào được dùng làm nơi “đẩy toàn bộ chất lượng”.

### Bài tập 2 — Acceptance criteria và DoD

Hạng mục “Học viên tự đăng ký khóa miễn phí” có acceptance criteria:

> “Khi học viên đủ điều kiện gửi đăng ký khóa còn chỗ, hệ thống trả xác nhận thành công.”

DoD của đội yêu cầu kiểm thử quyền, tích hợp, hồi quy quan trọng và dữ liệu nhất quán. Demo một người thành công, nhưng API vẫn cho xem đăng ký của người khác.

**Câu hỏi:** hạng mục có Done không? Acceptance criteria cần bổ sung gì để tránh hiểu sai?

**Gợi ý:** **chưa Done**, vì vi phạm DoD và an toàn. Cần bổ sung ví dụ quyền truy cập, request lặp, trường hợp hết chỗ và tranh chỗ cuối theo rủi ro, đồng thời kiểm chứng bằng test phù hợp.

### Bài tập 3 — Thiết kế ma trận kiểm thử theo rủi ro

Một hệ thống có ba khả năng:

- A: tìm khóa học theo từ khóa.
- B: đăng ký khóa còn chỗ có giới hạn sức chứa.
- C: thanh toán và hoàn học phí.

Hãy chọn **ít nhất ba loại kiểm chứng** cho từng khả năng và giải thích tại sao không áp dụng cùng mức kiểm tra cho cả ba.

**Gợi ý:**

- **A:** unit test bộ lọc, test kết quả API, đánh giá trải nghiệm/tiếp cận và hiệu năng ở mức phù hợp.
- **B:** unit test quy tắc, integration test DB/concurrency/retry, authorization và E2E cốt lõi.
- **C:** thêm kiểm chứng giao dịch, idempotency, đối soát, quyền/dữ liệu, tích hợp nhà cung cấp, khôi phục và nghĩa vụ tài chính áp dụng. Cần chuyên gia đủ thẩm quyền với rủi ro thanh toán.

Lựa chọn dựa trên **hậu quả nếu sai**, không chỉ độ dài code.

### Bài tập 4 — Tại sao CI xanh chưa đủ?

Một bản build có 300 unit tests đạt và code coverage 95%, nhưng:

- Chưa chạy integration tests trên DB thật phù hợp.
- Test concurrent enrollment chưa được viết.
- Không có kiểm chứng người dùng có hiểu thông báo xác nhận không.
- Pipeline đang bỏ qua bước kiểm tra quyền vì sandbox chưa hoạt động.

**Yêu cầu:** nêu ít nhất bốn rủi ro còn lại và kế hoạch kiểm chứng trước khi gọi Increment Done.

**Gợi ý:** rủi ro nhất quán dữ liệu, cạnh tranh, quyền riêng tư, UX và khả năng tích hợp. Cần làm rõ môi trường, khôi phục phép kiểm tra quyền, chạy test dữ liệu/đồng thời, test luồng thật và thu phản hồi phù hợp; không dùng coverage 95% làm lý do bỏ kiểm chứng.

### Bài tập 5 — Phân biệt defect và phạm vi mới

Sau khi đăng ký khóa miễn phí được phát hành:

1. Học viên bị ghi nhận hai đăng ký hiệu lực sau khi gửi lại request.
2. Người dùng đề nghị có SMS nhắc ngày học.
3. Người dùng thấy thông báo hết chỗ khó hiểu dù thông báo đã đáp ứng tiêu chí cũ.
4. Người dùng có thể xem bản ghi của học viên khác.
5. Đề nghị bổ sung đăng ký khóa học có thanh toán.

**Yêu cầu:** phân loại sơ bộ các mục và nêu cách xử lý.

**Gợi ý:** (1), (4) là defect cần đánh giá mức rủi ro và ưu tiên sửa; (2), (5) thường là cải tiến/tính năng mới; (3) có thể là vấn đề khả năng sử dụng cần điều tra, phân biệt **vi phạm tiêu chí đã cam kết** với cơ hội cải tiến. PO quản lý thứ tự backlog; lỗi an toàn nghiêm trọng phải theo chính sách ứng cứu.

### Bài tập 6 — Đọc số liệu mà không đánh lừa bản thân

Nhóm báo:

| Kỳ minh họa | Defect trước bàn giao | Defect sau bàn giao | Cycle time trung vị |
| --- | ---: | ---: | ---: |
| Tháng A | 20 | 8 | 9 ngày |
| Tháng B | 35 | 5 | 7 ngày |

**Câu hỏi:**

1. Có thể kết luận chất lượng tốt hơn trong tháng B không?
2. Vì sao defect được phát hiện trước bàn giao tăng có thể là điều tốt?
3. Cần xem những dữ liệu bổ sung nào?
4. Những hành vi xấu nào xuất hiện nếu dùng số lỗi làm KPI cá nhân?

**Gợi ý:** chưa thể kết luận chỉ từ bảng. Có thể nhóm bổ sung kiểm thử sớm và phát hiện nhiều lỗi trước release; nhưng cũng có thể chất lượng mã kém hơn hoặc loại công việc đổi. Cần xem severity, phạm vi người dùng, số thay đổi, rủi ro, chuẩn Done, cách ghi nhận lỗi và tác động sản phẩm. Không dùng chỉ số để khuyến khích giấu lỗi.

### Bài tập 7 — Lập kế hoạch phản ứng với lỗi sau rollout

Sau khi mở tính năng cho 10% học viên, monitoring ghi nhận tỷ lệ lỗi tăng. Một số yêu cầu đăng ký nhận timeout, nhưng chưa biết hệ thống đã lưu thành công hay chưa.

Hãy lập kế hoạch gồm:

1. Kiểm tra tác động, mức nghiêm trọng và người có thẩm quyền.
2. Hành động hạn chế ảnh hưởng hoặc tạm dừng rollout.
3. Thu bằng chứng để phân biệt timeout và thất bại lưu dữ liệu.
4. Cách xử lý retry/idempotency để không tạo bản ghi trùng.
5. Kết quả cần kiểm chứng trước khi tiếp tục phát hành.
6. Một hành động cải tiến sau sự cố.

**Gợi ý:** theo incident response, quan sát request ID và transaction state với dữ liệu an toàn; tạm dừng hoặc giảm phạm vi theo quyền và mức rủi ro; kiểm tra bản ghi trước khi cho retry; sửa và chạy test tích hợp hồi quy; thêm telemetry/kịch bản lỗi mạng để ngăn tái diễn. Không cho rằng rollback mã tự sửa dữ liệu đã ghi.

### Bài tập 8 — Cải tiến điểm nghẽn giữa phát triển và kiểm thử

Nhóm có WIP cao. Mỗi Sprint, Developers mở nhiều ticket, kiểm thử dồn vào hai ngày cuối, thường không có Increment hoàn tất. Người quản lý đề nghị tuyển thêm tester.

Hãy xây một thử nghiệm cải tiến theo **Plan–Do–Check–Act (PDCA)**:

- **Plan:** nêu giả thuyết nguyên nhân và tín hiệu ban đầu.
- **Do:** chọn một thay đổi nhỏ về phối hợp hoặc workflow.
- **Check:** chọn số đo để xem chất lượng và thời gian chờ.
- **Act:** quyết định giữ, điều chỉnh hoặc hoàn tác.

**Ví dụ:** giả thuyết nhóm chia việc theo backend–frontend–QA nên test tới muộn. Thử giới hạn WIP, làm rõ ví dụ từ đầu, pairing kiểm thử với Developers và tạo lát cắt dọc; theo dõi cycle time, work item age ở Verify, lỗi sau phát hành và số Increment đạt DoD. Nếu vẫn bị nghẽn vì năng lực môi trường hoặc chuyên môn thật sự, cần đầu tư đúng nút thắt thay vì chỉ thêm người theo cảm tính.

## 20. Checklist thực hành chất lượng liên tục

### Trước khi bắt đầu một PBI

- [ ] PBI có mục đích người dùng/kinh doanh và phạm vi đủ rõ để trao đổi.
- [ ] PO/người có thẩm quyền đã xác nhận các quy tắc nghiệp vụ trọng yếu.
- [ ] Có ví dụ cho hành vi thành công, thất bại, biên và ngoại lệ quan trọng.
- [ ] Những rủi ro về dữ liệu, đồng thời, quyền, bảo mật, hiệu năng và vận hành được xem xét tương xứng.
- [ ] Chuyên môn kiểm thử, UX, security, dữ liệu, vận hành được mời tham gia khi có rủi ro liên quan.
- [ ] Nhóm hiểu acceptance criteria, DoD và release policy khác nhau thế nào.

### Trong thiết kế và phát triển

- [ ] Developers cùng chịu trách nhiệm chất lượng của phần sản phẩm, không đẩy toàn bộ sang QA.
- [ ] Thay đổi đủ nhỏ để review và tích hợp thường xuyên.
- [ ] Có test phù hợp với rủi ro, không chỉ happy path.
- [ ] Các thay đổi hợp đồng API/schema có kế hoạch tương thích khi cần.
- [ ] Phân quyền và dữ liệu cá nhân được kiểm soát đúng thẩm quyền.
- [ ] CI/pipeline có phản hồi đáng tin; thất bại được xử lý chứ không che giấu.
- [ ] Những trở ngại kiểm thử được công khai và xử lý trước khi dồn cuối Sprint.

### Trước khi tuyên bố hoàn tất

- [ ] Hành vi cần thiết và acceptance criteria đã được kiểm chứng.
- [ ] Phần mềm tích hợp, các test bắt buộc đã **thực sự chạy và đạt**.
- [ ] Quyền truy cập, dữ liệu nhất quán và kịch bản lỗi có mức rủi ro phù hợp đã được kiểm tra.
- [ ] Không còn vấn đề nghiêm trọng vi phạm DoD/chuẩn tổ chức.
- [ ] Bằng chứng chất lượng có thể xem lại; trạng thái chưa kiểm chứng được ghi rõ.
- [ ] Phần sản phẩm có thể sử dụng trong phạm vi đã công bố, không chỉ demo với dữ liệu giả.
- [ ] Nếu chưa đạt DoD, công việc **không bị gọi là Increment Done**.

### Khi phát hành và vận hành

- [ ] Quy trình phát hành có người có thẩm quyền và kiểm soát cần thiết.
- [ ] Có cách quan sát lỗi, hiệu năng và kết quả nghiệp vụ sau rollout.
- [ ] Có kế hoạch xử lý/khôi phục và nhận diện tác động dữ liệu/side effects nếu cần.
- [ ] Phản hồi người dùng và nhân viên hỗ trợ có đường quay lại Product Backlog.
- [ ] Defect sau Done được ghi nhận, ưu tiên và xử lý theo mức ảnh hưởng.
- [ ] Sự cố quan trọng có hậu kiểm tập trung nguyên nhân hệ thống và hành động phòng ngừa.

### Khi cải tiến cách làm

- [ ] Nhóm xem WIP, cycle time, work item age, sự cố và outcome trong bối cảnh.
- [ ] Không dùng số bug, coverage, commit hay story point để xếp hạng năng suất cá nhân.
- [ ] Các phát hiện mới khiến nhóm cập nhật test, DoD hoặc cách phối hợp khi cần.
- [ ] Hoạt động kiểm chứng vẫn tương xứng với rủi ro và không biến thành thủ tục vô ích.
- [ ] Nhóm có thể báo lỗi và đặt câu hỏi mà không sợ bị làm nhục hay trả đũa.
- [ ] Mỗi thay đổi cải tiến có giả thuyết, người thực hiện và bằng chứng đánh giá hiệu quả.

Checklist là gợi ý để **thảo luận và lựa chọn thực hành**, không phải biểu mẫu bắt buộc. Nhóm cần duy trì những chính sách chất lượng của tổ chức và chỉ bổ sung điều thật sự giúp sản phẩm đáng tin hơn.

## 21. Tổng kết

**Chất lượng trong Agile là trách nhiệm chung xuyên suốt vòng phát triển**, từ khám phá nhu cầu, làm rõ backlog, thiết kế và mã, tới tích hợp, kiểm chứng, phát hành, vận hành và cải tiến.

- **Product Owner và người hiểu nghiệp vụ** góp phần làm rõ điều đúng và giá trị cần đạt.
- **Developers** tạo Increment sử dụng được, đưa chất lượng vào công việc hằng ngày và tuân thủ Definition of Done trong Scrum.
- **Chuyên gia kiểm thử, UX, bảo mật, dữ liệu và vận hành** mang các góc nhìn cần thiết để phát hiện và giảm rủi ro.
- **Scrum Master hoặc người hỗ trợ nhóm** giúp cải thiện hiệu quả phối hợp và tháo gỡ trở ngại theo trách nhiệm tương ứng.
- **Người dùng và hệ thống đang vận hành** cung cấp bằng chứng để cải thiện sản phẩm và cách làm.

Những thực hành như **Three Amigos, acceptance criteria, test theo rủi ro, TDD, review, CI, DoD, rollout có kiểm soát, observability và hậu kiểm sự cố** bổ sung cho nhau. Không thực hành nào thay thế mọi thực hành khác, và một pipeline xanh không tự chứng minh giá trị hoặc chất lượng toàn diện.

Mục tiêu không phải phát hiện được thật nhiều lỗi để “chuyển cho QA”, cũng không phải chạy ít test nhất để giao nhanh. Mục tiêu là **ngăn vấn đề từ sớm, phát hiện sai lệch khi còn rẻ để sửa, giao Increment đáng tin cậy và học từ việc sử dụng thực tế**. Đó là nền tảng cho phát triển phần mềm Agile thích ứng và bền vững.

### Thuật ngữ chính

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Continuous quality** | Chất lượng được xây, kiểm chứng và cải tiến liên tục trong toàn vòng phát triển. |
| **Whole-team quality** | Tư duy mọi năng lực trong nhóm cùng góp trách nhiệm với chất lượng sản phẩm. |
| **Quality Assurance (QA)** | Các hoạt động và cách làm giúp bảo đảm quy trình/hệ thống tạo sản phẩm có chất lượng; không đồng nghĩa chỉ kiểm thử cuối cùng. |
| **Quality Control (QC)** | Các hoạt động kiểm tra/xác nhận để phát hiện sai lệch ở kết quả sản phẩm. |
| **Acceptance criteria** | Tiêu chí cụ thể làm rõ hành vi/kết quả mong đợi của một hạng mục. |
| **Definition of Done (DoD)** | Cam kết về trạng thái chất lượng của Increment trong Scrum. |
| **Increment** | Phần tăng trưởng sản phẩm đã tích hợp, có thể sử dụng và đáp ứng DoD. |
| **Three Amigos** | Trao đổi đa góc nhìn nghiệp vụ, phát triển và kiểm thử để làm rõ hành vi. |
| **Shift-left** | Đưa hoạt động làm rõ, phòng ngừa và kiểm chứng rủi ro sớm hơn. |
| **Shift-right** | Quan sát chất lượng trong sử dụng/vận hành thực tế để tiếp tục học hỏi. |
| **Risk-based testing** | Lựa chọn loại và độ sâu kiểm chứng dựa trên khả năng và hậu quả rủi ro. |
| **TDD** | Test-Driven Development: vòng Red–Green–Refactor với test dẫn dắt triển khai. |
| **CI** | Continuous Integration: tích hợp thường xuyên, kiểm chứng tự động bản mã chung. |
| **Contract test** | Kiểm tra hợp đồng giữa các thành phần hoặc dịch vụ giao tiếp. |
| **Exploratory testing** | Học, thiết kế và thực hiện kiểm thử theo những quan sát phát hiện trong quá trình thử. |
| **Defect** | Sai lệch giữa hành vi thực và điều đã được xác định là đúng trong bối cảnh. |
| **Observability** | Khả năng suy ra trạng thái hệ thống từ tín hiệu như log, metric và trace. |
| **SLI / SLO / SLA** | Chỉ số mức dịch vụ / mục tiêu mức dịch vụ / thỏa thuận mức dịch vụ. |
| **Canary release** | Triển khai trước cho một phần nhỏ phạm vi sử dụng, theo dõi rồi mở rộng có kiểm soát. |
| **Post-incident review** | Xem lại sự cố để hiểu nguyên nhân và cải tiến hệ thống, không tìm người để đổ lỗi. |
| **WIP** | Work in Progress: các hạng mục đã bắt đầu nhưng chưa hoàn tất. |
| **Cycle time** | Thời gian từ Started tới Finished theo workflow được công bố. |
| **Technical debt** | Những đánh đổi kỹ thuật có thể tăng chi phí và rủi ro thay đổi tương lai. |
| **PDCA** | Plan–Do–Check–Act: lập kế hoạch, thử thay đổi, kiểm chứng kết quả và điều chỉnh. |

