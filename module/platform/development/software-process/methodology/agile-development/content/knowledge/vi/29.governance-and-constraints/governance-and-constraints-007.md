# Tích hợp yêu cầu tuân thủ và bằng chứng kiểm chứng vào dòng công việc Agile

> **Tư tưởng chính:** Tuân thủ không nên là một “cửa kiểm tra giấy tờ” chỉ xuất hiện sau khi code đã xong. Một đội Agile cần biến **ràng buộc được xác nhận** thành **hành vi, kiểm soát và điều kiện hoàn thành có thể kiểm chứng**, đồng thời tạo và lưu **bằng chứng đáng tin cậy ngay tại bước công việc phát sinh**. Mục tiêu là giao phần mềm thích ứng, có giá trị và có thể chứng minh đã đáp ứng những nghĩa vụ liên quan — không phải biến Sprint thành quy trình xin chữ ký cho mọi thao tác nhỏ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **nghĩa vụ tuân thủ, chính sách nội bộ, rủi ro, kiểm soát, tiêu chí chấp nhận, bằng chứng và quyết định phê duyệt**.
2. Chuyển một yêu cầu bảo vệ dữ liệu, quyền truy cập hoặc khả năng tiếp cận thành **Product Backlog Items**, acceptance criteria, test cases và bằng chứng có thể đối chiếu.
3. Thiết lập **truy vết hai chiều** từ nguồn yêu cầu đến thay đổi code, kiểm tra, kết quả, phiên bản và người/chức năng có thẩm quyền xác nhận.
4. Chọn mức kiểm tra thích hợp giữa **static checks, unit/component, contract/integration, E2E, kiểm tra thủ công và đánh giá chuyên môn**, không coi test tự động là bằng chứng cho mọi nghĩa vụ.
5. Gắn kiểm soát vào **Definition of Done, CI/CD, review và chính sách phát hành** một cách tương xứng rủi ro.
6. Nhận biết bằng chứng **thiếu ngữ cảnh, hết hạn, gắn sai phiên bản, không đủ tin cậy hoặc chứa dữ liệu nhạy cảm**.
7. Xử lý **ngoại lệ, nợ tuân thủ, blocker và sự cố** minh bạch, với đúng quyền quyết định và biện pháp giảm thiểu.
8. Vận dụng Scrum, Kanban, XP và các phép đo dòng công việc để giảm **thời gian chờ kiểm soát** mà vẫn bảo vệ chất lượng.
9. Thiết kế kế hoạch kiểm chứng theo rủi ro cho một chức năng lưu tiến độ người học, kèm ma trận yêu cầu–bằng chứng và hành động cải tiến.

## 2. Tình huống mở đầu: “Code xong” nhưng chưa thể giao

Một Scrum Team xây nền tảng học trực tuyến muốn bổ sung khả năng **lưu tiến độ và tiếp tục bài học**.

Đầu Sprint, nhóm chọn user story:

> “Là người học đang học dở, tôi muốn lưu và mở lại tiến độ để không phải học lại từ đầu.”

Developers hoàn tất code, unit tests xanh, giao diện chạy được. Nhưng sát ngày phát hành, nhóm mới nhận các câu hỏi:

- **Ai được đọc tiến độ?** Một người học có xem dữ liệu người khác bằng cách đổi tham số API không?
- **Dữ liệu nào thực sự cần lưu?** Có chứa chi tiết cá nhân không cần thiết không?
- **Thông báo “Đã lưu” nghĩa gì?** Có thể báo thành công trước khi nơi lưu xác nhận không?
- **Có dấu vết thay đổi không?** Quyết định về quyền truy cập và những kiểm tra bắt buộc được ghi ở đâu?
- **Ai có thẩm quyền chấp nhận rủi ro còn lại?** Chính sách có đòi hỏi đánh giá riêng trước khi mở cho người dùng không?
- **Bằng chứng nào gắn với bản phát hành?** Một ảnh CI xanh của nhánh khác có đủ không?

Nhóm có thể đã xây đúng một phần chức năng nhưng **chưa chứng minh được các ràng buộc quan trọng**. Khi kiểm soát bị khám phá quá muộn, code phải làm lại, release bị chặn và người dùng chờ lâu.

Một đội có năng lực Agile không phản ứng bằng cách tuyên bố “bỏ kiểm soát cho nhanh”. Họ **làm rõ yêu cầu với người có thẩm quyền, đưa chúng vào backlog và tiêu chí Done, kiểm chứng sớm, lưu bằng chứng đúng nơi** rồi thay đổi kế hoạch khi có thông tin mới.

> **Câu hỏi thiết kế dòng công việc:** “Yêu cầu nào bắt buộc với thay đổi này, bằng chứng gì chứng minh đã đạt, ai đánh giá nó và **ở bước nào** đội có thể nhận phản hồi sớm nhất mà vẫn đáng tin?”

## 3. Thuật ngữ nền tảng: từ nghĩa vụ tới bằng chứng

### 3.1. Không đồng nhất các khái niệm

| Khái niệm | Câu hỏi trả lời | Ví dụ giả định trong nền tảng học |
|---|---|---|
| **Nguồn nghĩa vụ** | Điều này bắt buộc vì đâu? | Hợp đồng, chính sách bảo vệ dữ liệu, quy định hoặc yêu cầu kiểm soát nội bộ có hiệu lực |
| **Yêu cầu tuân thủ** | Điều kiện cụ thể nào phải đáp ứng? | Chỉ tài khoản có quyền được truy cập tiến độ của người học tương ứng |
| **Rủi ro** | Điều gì có thể xảy ra nếu không đáp ứng? | Một người học đọc/sửa tiến độ của người khác |
| **Kiểm soát (control)** | Cơ chế phòng ngừa, phát hiện hoặc giảm tác động nào? | Kiểm tra quyền ở server trước thao tác đọc/ghi |
| **Acceptance criteria** | Hành vi của PBI được chấp nhận thế nào? | Request trái quyền bị từ chối và không trả dữ liệu |
| **Definition of Done (DoD)** | Chuẩn chất lượng chung để Increment được coi là hoàn thành? | Thay đổi tích hợp, kiểm thử theo rủi ro đạt, bằng chứng kiểm soát bắt buộc có thể truy tìm |
| **Bằng chứng (evidence)** | Dựa vào gì để xác minh kiểm soát có hiệu lực cho phạm vi/version? | Kết quả integration test gắn commit/build cùng log test đã làm sạch dữ liệu |
| **Đánh giá/phê duyệt** | Ai có quyền kết luận hoặc chấp nhận rủi ro còn lại? | Người/chức năng được quy định trong chính sách tổ chức |
| **Ngoại lệ** | Có điều kiện nào chưa đạt và cần xử lý theo thẩm quyền? | Một kiểm tra bắt buộc chưa chạy do môi trường thử lỗi |
| **Dấu vết (traceability)** | Có thể đi từ nghĩa vụ tới kiểm soát, PBI, code, test, bằng chứng và quyết định không? | Liên kết CTL-ACCESS-01 → PBI-42 → PR-42 → test → build |

**Lưu ý:** Đường dẫn tới một kết quả test **không tự chứng minh** kiểm soát tuân thủ đã đủ. Kết quả còn phải đúng phạm vi, phiên bản, môi trường, tiêu chí và mức bảo đảm mà nghĩa vụ yêu cầu.

### 3.2. Không phải mọi yêu cầu “compliance” đều giống nhau

Trong thực tế, nguồn ràng buộc có thể là:

1. **Luật hoặc quy định áp dụng:** phụ thuộc khu vực pháp lý, loại dữ liệu, chủ thể và hoạt động của tổ chức.
2. **Hợp đồng khách hàng/đối tác:** thỏa thuận về quyền truy cập, bảo mật, xử lý dữ liệu, báo cáo hoặc bằng chứng.
3. **Chính sách và tiêu chuẩn nội bộ:** ví dụ quy trình quản lý quyền, bảo vệ bí mật, lưu vết thay đổi, review.
4. **Tiêu chuẩn ngành hoặc yêu cầu chứng nhận:** phạm vi và cách chứng minh phụ thuộc chương trình cụ thể.
5. **Ràng buộc kỹ thuật/vận hành:** độ tin cậy, khôi phục, kiểm soát phát hành và giới hạn hệ thống hiện có.

Không tự tuyên bố một tiêu chuẩn nào đó **bắt buộc với mọi phần mềm**. Trước khi đưa việc vào backlog, cần xác nhận **nguồn, phiên bản, phạm vi áp dụng, người có thẩm quyền diễn giải và cách kiểm chứng được chấp nhận**.

Ví dụ bài này sử dụng **những chính sách giả định để học cách tổ chức công việc**; chúng không phải tư vấn pháp lý hay kết luận rằng một bộ luật/tiêu chuẩn cụ thể luôn áp dụng với nền tảng học.

### 3.3. Tuân thủ không có nghĩa sản phẩm có giá trị

Một chức năng có thể:

- **Đáp ứng một số kiểm soát** nhưng người học không cần.
- Tạo **outcome người dùng tốt** nhưng vi phạm kiểm soát quyền truy cập.
- Đạt **unit tests** nhưng chưa qua kiểm chứng kết nối với database thật.
- Đã được **phê duyệt một bản release** nhưng không còn đáp ứng kiểm soát sau khi cấu hình thay đổi.

Đội phải nhìn đồng thời **Product Goal, chất lượng Increment, ràng buộc bắt buộc và phản hồi sử dụng**. “Đã tuân thủ” không được dùng như bằng chứng rằng mọi rủi ro biến mất.

### 3.4. Ba lớp bảo đảm nên được mô tả rõ

| Lớp | Điều muốn biết | Cách xem |
|---|---|---|
| **Thiết kế kiểm soát** | Cơ chế dự định có phù hợp rủi ro và nghĩa vụ không? | Threat/risk review, kiến trúc, chính sách, chuyên gia |
| **Hiện thực kiểm soát** | Code/cấu hình có triển khai cơ chế đó? | Review, static/unit/component/contract/integration tests |
| **Hiệu lực vận hành** | Cơ chế có tiếp tục hoạt động trong hệ thống thực? | Quan sát, kiểm tra quyền, kiểm toán theo phạm vi, theo dõi sự cố |

Một screenshot thiết kế không chứng minh code đã triển khai. Một CI run xanh không chứng minh cấu hình production chưa bị đổi. Nên mô tả **bằng chứng đang hỗ trợ lớp nào**.

## 4. Biến yêu cầu trừu tượng thành điều kiện có thể kiểm chứng

### 4.1. Bắt đầu từ mục đích kiểm soát

Yêu cầu quá chung:

> “Hệ thống phải bảo vệ dữ liệu người học.”

Nó khó kiểm thử vì không nói **dữ liệu nào, ai được làm gì, điều kiện truy cập nào, hậu quả gì**. Cần làm rõ bằng câu hỏi:

- Dữ liệu nào cần bảo vệ: tiến độ, hồ sơ, nội dung bài, lịch sử hoạt động?
- Ai là chủ thể: người học, người hướng dẫn, bộ phận hỗ trợ, quản trị?
- Hoạt động nào: đọc, ghi, xóa, xuất, sửa?
- Trong ngữ cảnh nào được phép: cùng tài khoản, vai trò, tổ chức, phiên?
- Trường hợp bị từ chối phải thể hiện thế nào?
- Có hành vi ghi log nào bắt buộc? Log được phép chứa những trường gì?
- Có ràng buộc cụ thể về lưu giữ/xóa/định vị dữ liệu không? Ai xác nhận?

**Điều quan trọng:** Developers không nên tự diễn giải nghĩa vụ pháp lý chưa rõ thành một giá trị số hoặc chính sách bắt buộc chỉ vì cần viết test.

### 4.2. Mẫu yêu cầu có thể truy vết

~~~yaml
# Ví dụ học tập, không phải schema compliance chính thức.
requirement_id: REQ-ACCESS-01
source_type: "Chính sách nội bộ giả định"
source_reference: "POL-DATA-04, phiên bản được xác nhận"
applicability: "API đọc và cập nhật tiến độ người học"
purpose: "Ngăn đọc/sửa dữ liệu của người học khác trái quyền"
risk: "Lộ hoặc sửa dữ liệu học tập không được phép"
control_id: CTL-ACCESS-01
control: "Server kiểm tra quyền trên tài nguyên trước đọc/ghi"
acceptance_examples:
  - "Chủ thể có quyền đọc đúng tiến độ được phép"
  - "Chủ thể không có quyền bị từ chối, không lộ dữ liệu"
verification:
  - "Unit/component test quy tắc phân quyền"
  - "API/integration test kiểm tra quyền với dữ liệu khác chủ"
evidence_required:
  - "Kết quả kiểm tra gắn với build/commit"
  - "Review kiểm soát và kết luận theo chính sách"
accountability: "Vai trò được chính sách tổ chức xác định"
review_trigger: "Thay đổi chính sách, API, role model hoặc kiến trúc"
~~~

Thông tin **source_reference và accountability** phải lấy từ nguồn có thẩm quyền của sản phẩm thật. Ở ví dụ này chúng chỉ là nhãn minh họa.

### 4.3. Dùng acceptance examples để tránh hai cách hiểu

Giả sử chính sách giả định là **người học chỉ được xem tiến độ của chính mình**, ngoại trừ những quyền đã được quy định rõ cho vai trò khác.

~~~gherkin
Feature: Kiểm soát quyền truy cập tiến độ học
  Để ngăn tiết lộ dữ liệu học tập trái quyền

  Scenario: Người học xem tiến độ của mình
    Given tài khoản A đã xác thực hợp lệ
    And tiến độ bài học thuộc về tài khoản A
    When A yêu cầu đọc tiến độ đó
    Then hệ thống trả dữ liệu được phép theo hợp đồng

  Scenario: Người học không được xem tiến độ của người khác
    Given tài khoản A đã xác thực hợp lệ
    And tiến độ bài học thuộc về tài khoản B
    And A không có quyền truy cập dữ liệu của B
    When A yêu cầu đọc tiến độ của B
    Then hệ thống từ chối yêu cầu theo chính sách
    And không tiết lộ dữ liệu tiến độ của B
~~~

Gherkin giúp diễn đạt hành vi nhưng **không tự tạo kiểm thử đã chạy**. Cần step definitions, môi trường, dữ liệu thử được kiểm soát và xác minh rằng các trường hợp đã bao phủ đúng rủi ro.

### 4.4. Làm rõ trường hợp biên và ngoại lệ

Các điều cần hỏi thêm:

| Câu hỏi | Tác động nếu không rõ |
|---|---|
| Người hướng dẫn có được xem tiến độ của học viên trong lớp mình không? | Quyền bị cấp quá rộng hoặc từ chối sai |
| Hỗ trợ khách hàng có cần quyền đọc tạm thời không? | Chưa có quy trình phê duyệt/ghi nhận phù hợp |
| Tài khoản đã khóa còn truy cập được dữ liệu cũ không? | Lỗi vòng đời quyền |
| API trả lỗi nào khi thiếu quyền, thông tin nào được tiết lộ? | Rò rỉ tồn tại tài nguyên |
| Quyền cache tại UI có thể cũ không? | Kiểm tra client không đủ bảo đảm server |
| Một phiên xác thực hết hạn giữa thao tác thì sao? | Quy tắc xử lý biên chưa có |
| Xóa tài khoản hoặc yêu cầu dữ liệu phải làm gì? | Nghĩa vụ lưu giữ/xóa chưa được diễn giải |

Không nên tự thêm một role “support có toàn quyền” chỉ để đơn giản hóa kiểm tra. **Quyền và ngoại lệ phải được người có thẩm quyền xác nhận**.

### 4.5. Tách tiêu chí hành vi và nghĩa vụ bằng chứng

| Đầu ra cần có | Ý nghĩa | Ví dụ |
|---|---|---|
| **Acceptance criteria** | Tính năng phải cư xử thế nào | Chủ thể trái quyền bị từ chối |
| **Test** | Kiểm chứng một ví dụ cụ thể | API test với hai tài khoản thử và ID khác nhau |
| **Evidence artifact** | Ghi lại kết quả, phạm vi và phiên bản đã kiểm tra | Kết quả test gắn commit, môi trường, thời điểm |
| **Control review** | Xác nhận thiết kế/độ bao phủ theo chính sách | Kết luận của reviewer có thẩm quyền |
| **DoD** | Chuẩn chất lượng của Increment | Thay đổi tích hợp, kiểm thử và kiểm soát bắt buộc đạt |
| **Release decision** | Có được phép mở cho người dùng trong điều kiện hiện tại? | Bằng chứng gate và rủi ro tồn dư được xử lý đúng thẩm quyền |

**Một bài test có thể phục vụ nhiều mục tiêu**, nhưng cần nói rõ nó chứng minh phần nào, thay vì tạo thêm bản sao chỉ vì hai nhóm dùng hai thuật ngữ khác nhau.

## 5. Truy vết từ nghĩa vụ tới Increment và ngược lại

### 5.1. Vì sao truy vết hai chiều?

**Đi từ yêu cầu xuống thực thi:** Với REQ-ACCESS-01, các PBI, thay đổi code, test và kết quả nào cho thấy kiểm soát được thực hiện?

**Đi từ thay đổi đi lên yêu cầu:** Với PR sửa API tiến độ, có yêu cầu/kiểm soát liên quan nào phải kiểm tra lại không? Có thay đổi nào làm bằng chứng cũ không còn phù hợp?

Truy vết chỉ có ích nếu giúp **phát hiện khoảng trống và đánh giá tác động thay đổi**, không phải chỉ để đếm số dòng trong bảng.

### 5.2. Ma trận truy vết minh họa

| ID nguồn | Ràng buộc/kiểm soát | PBI hoặc việc | Kiểm chứng | Bằng chứng dự kiến | Trạng thái |
|---|---|---|---|---|---|
| REQ-ACCESS-01 | Đọc/ghi tiến độ đúng quyền | PBI-42 | Unit phân quyền; API integration trái quyền | Test run gắn build + review quyền | Đang thực hiện |
| REQ-STATE-02 | Không báo “Đã lưu” khi thiếu xác nhận | PBI-43 | Component UI + contract + E2E chọn lọc | Test run và contract version | Chưa hoàn tất |
| REQ-LOG-03 | Không ghi dữ liệu cá nhân quá mức trong log | PBI-44 | Review schema log + kiểm tra mẫu log test | Tài liệu kiểm soát và kết quả review | Cần xác nhận phạm vi |
| REQ-A11Y-04 | Điều khiển và trạng thái hỗ trợ khả năng tiếp cận theo tiêu chí được chọn | PBI-45 | Static check + thao tác bàn phím + đánh giá cần thiết | Kết quả theo tiêu chí/phiên bản | Chưa thực hiện |
| REQ-REL-05 | Có thể phát hiện và phục hồi lỗi lưu theo mục tiêu dịch vụ | PBI-46 | Integration/resilience + kiểm tra vận hành | Kịch bản, log, kết luận thử | Dự kiến |

Các ID, ràng buộc và trạng thái trong bảng **hoàn toàn minh họa**. Trên sản phẩm thật, **REQ-A11Y-04** cần nêu rõ phiên bản tiêu chuẩn và tiêu chí áp dụng; **REQ-REL-05** cần ngưỡng do tổ chức xác nhận, không dùng số giả.

### 5.3. Sơ đồ chuỗi bằng chứng

~~~mermaid
flowchart TD
    N["Nguồn nghĩa vụ có hiệu lực"] --> R["Yêu cầu trong phạm vi áp dụng"]
    R --> C["Kiểm soát và rủi ro cần giảm"]
    C --> P["PBI / tiêu chí chấp nhận / DoD"]
    P --> I["Code, cấu hình, tài liệu được version"]
    I --> T["Kiểm chứng: tự động + chuyên môn"]
    T --> E["Bằng chứng: kết quả, thời gian, build, phạm vi"]
    E --> D{"Đạt các điều kiện cần thiết?"}
    D -->|"Chưa"| B["Blocker / sửa / đánh giá ngoại lệ đúng thẩm quyền"]
    D -->|"Có"| A["Increment và quyết định phát hành phù hợp"]
    A --> O["Quan sát hiệu lực vận hành, thay đổi và sự cố"]
    O --> R
~~~

Sơ đồ là mô hình học tập, **không phải sơ đồ phê duyệt bắt buộc cho mọi tổ chức**. Sản phẩm khác nhau có thể cần thêm bước đánh giá hoặc cho phép những kiểm tra độc lập diễn ra song song.

### 5.4. Truy vết phải có trạng thái cập nhật

Một ma trận ghi “test đạt” tháng trước **không tự hợp lệ** sau khi:

- API đổi hợp đồng.
- Cấu hình quyền trong production thay đổi.
- Nguồn nghĩa vụ được sửa phiên bản.
- Service được chuyển nhà cung cấp hoặc vùng triển khai.
- Một test không còn được chạy trong pipeline.
- Cơ chế phân quyền bị refactor.

Khi có thay đổi, nhóm cần **đánh giá phạm vi bằng chứng cũ còn hiệu lực**, không chỉ sửa trạng thái trên spreadsheet.

### 5.5. Truy vết không cần đòi nhập tay mọi liên kết

Có thể giảm chi phí bằng:

- ID yêu cầu/kiểm soát ổn định trong ticket và PR.
- Test case đặt tên mô tả hành vi và liên kết tới PBI/requirement.
- CI tự gắn commit SHA, build ID, môi trường, thời điểm và test suite.
- Tài liệu chính sách được version, có trạng thái hiệu lực.
- Quy tắc review tập trung vào thay đổi kiểm soát quan trọng.

Nhưng **tự động tạo link** chưa đồng nghĩa đã xác minh được mối liên hệ. Cần người phù hợp đánh giá xem test đúng **mục đích kiểm soát** hay chỉ có tên giống yêu cầu.

## 6. Bằng chứng kiểm chứng có chất lượng là gì?

### 6.1. Bằng chứng không chỉ là ảnh màn hình màu xanh

Một kết quả test có thể đúng nhưng **không đủ để kết luận cho release** nếu thiếu:

| Thuộc tính | Câu hỏi kiểm tra | Dấu hiệu thiếu sót |
|---|---|---|
| **Tính liên quan** | Có kiểm chứng đúng yêu cầu và rủi ro cần chứng minh? | Test chỉ gọi API thành công, trong khi nghĩa vụ là từ chối người trái quyền |
| **Tính xác thực/nguồn gốc** | Ai/công cụ nào tạo bằng chứng, có thể kiểm tra nguồn? | Screenshot không có link build hoặc dữ liệu đầu vào |
| **Đúng phiên bản** | Kết quả gắn với commit, artifact, cấu hình và contract nào? | Kết quả cũ từ nhánh khác được dùng để release |
| **Đúng phạm vi/môi trường** | Môi trường test có đại diện cho rủi ro kiểm soát cần đánh giá? | Mock trả quyền đúng nhưng DB thật bỏ qua kiểm tra |
| **Tính đầy đủ** | Có bao phủ các trường hợp chính, thất bại và ngoại lệ quan trọng? | Chỉ có happy path; không thử truy cập trái quyền |
| **Có thể tái hiện/đối chiếu** | Có tiêu chí, bước thực hiện, dữ liệu thử hoặc phương pháp rõ? | Chỉ ghi “đã kiểm tra thủ công, OK” |
| **Tính toàn vẹn** | Bằng chứng có được lưu và bảo vệ trước sửa/xóa trái phép? | File kết quả có thể bị thay mà không có dấu vết |
| **Tính kịp thời/hiệu lực** | Có cần kiểm chứng lại sau thay đổi hay khoảng thời gian nào? | Cấu hình đổi nhưng bản review cũ vẫn được tính đạt |
| **Bảo mật và tối thiểu dữ liệu** | Bằng chứng có lộ bí mật/dữ liệu nhạy cảm không? | Log chứa token hoặc nội dung cá nhân không cần thiết |
| **Khả năng truy xuất** | Người được phép đánh giá có tìm được trong thời gian cần thiết? | Chỉ lưu ở máy cá nhân hoặc một đường link tạm |

Không phải mọi test đều cần thủ tục chứng thực như nhau. **Mức bảo đảm và thời gian lưu giữ phải phù hợp yêu cầu thực tế**, tránh tạo quá nhiều bước thủ công không đóng góp giá trị.

### 6.2. Ví dụ bản ghi bằng chứng có cấu trúc

~~~yaml
# Manifest mẫu minh họa, không phải artifact chuẩn của một hệ CI.
evidence_id: EVD-ACCESS-2026-0042
requirement_id: REQ-ACCESS-01
control_id: CTL-ACCESS-01
verification_type: "API integration test và review kiểm soát"
test_suite: "progress-access-integration"
commit_sha: "<commit-sha-được-CI-ghi-thật>"
build_id: "<build-id-được-CI-ghi-thật>"
artifact_version: "<phiên-bản-artifact>"
environment: "Môi trường integration được kiểm soát"
execution_time: "<thời-điểm-UTC-thực>"
result: "PASS nếu tất cả điều kiện bắt buộc thực sự đạt"
test_summary:
  allowed_access: "Đạt theo tiêu chí đã định"
  denied_cross_account_access: "Đạt theo tiêu chí đã định"
open_questions:
  - "Phạm vi quyền của nhân sự hỗ trợ cần review riêng"
review_reference: "<link tới kết luận và người có thẩm quyền>"
storage_reference: "<vị-trí-lưu-được-phép>"
retention_policy: "<chính-sách-được-xác-nhận>"
~~~

Đây là **mẫu trường thông tin**, không phải bằng chứng đã tồn tại. Các giá trị nằm trong ngoặc nhọn phải được **hệ thống hoặc người có thẩm quyền ghi thật**, không được điền ngẫu nhiên cho đẹp báo cáo.

### 6.3. Một kết quả test phải đi kèm kết quả âm tính khi phù hợp

Với quyền truy cập, kiểm tra “A đọc được dữ liệu của A” là cần nhưng chưa đủ. Còn phải kiểm tra:

- A không có quyền đọc dữ liệu B.
- A không có quyền ghi vào dữ liệu B.
- Vai trò hoặc phiên không hợp lệ bị xử lý đúng.
- Không lộ thông tin nhạy cảm trong response/log theo chính sách.

Trong một số sản phẩm, còn cần test cho quyền hỗ trợ, tổ chức nhiều tenant hoặc thay đổi quyền trong khi phiên hoạt động. **Phạm vi được xác nhận bởi mô hình quyền thật**, không sao chép một bộ trường hợp chung mà bỏ yêu cầu cụ thể.

### 6.4. Bằng chứng thủ công có giá trị khi được mô tả đúng

Một đánh giá khả năng tiếp cận hoặc tình huống vận hành khó tự động hóa có thể cần người kiểm tra. Bản ghi nên nêu:

- Tiêu chí hoặc requirement cụ thể.
- Phạm vi trang/luồng/thiết bị/phiên bản được đánh giá.
- Phương pháp và công cụ hỗ trợ.
- Người thực hiện hoặc chức năng kiểm tra theo chính sách.
- Các phát hiện, giới hạn, mức ảnh hưởng và kết luận.
- Liên kết khắc phục nếu còn vấn đề.

Không tự gọi một bài review thủ công là “tự động chứng minh tuân thủ”. Ngược lại, **không coi kiểm tra thủ công luôn kém giá trị**; có rủi ro mà test tự động hiện tại khó đánh giá đầy đủ.

### 6.5. Tính toàn vẹn và vòng đời bằng chứng

Một luồng quản lý bằng chứng hợp lý:

~~~mermaid
flowchart LR
    A["Kiểm chứng tạo kết quả"] --> B["Gắn source, build, thời điểm, phạm vi"]
    B --> C["Lưu tại nơi được phép và phân quyền"]
    C --> D["Review/đối chiếu theo chính sách"]
    D --> E["Dùng cho quyết định chất lượng/phát hành"]
    E --> F["Theo dõi thay đổi và thời hạn hiệu lực"]
    F --> G{"Còn hợp lệ?"}
    G -->|"Không"| H["Kiểm chứng lại hoặc thay thế"]
    G -->|"Có"| I["Giữ và truy xuất khi cần"]
~~~

**Không đặt thời hạn lưu giữ tùy ý.** Nguồn nghĩa vụ có thể yêu cầu khoảng thời gian, hình thức, phạm vi truy cập hoặc xóa khác nhau; đội cần được người có thẩm quyền xác nhận và đưa yêu cầu đó vào thiết kế.

### 6.6. Khi test xanh nhưng bằng chứng vẫn không đạt

| Hiện tượng | Vì sao chưa đủ? | Bước tiếp |
|---|---|---|
| Unit tests xanh cho hàm quyền | Chưa kiểm tra cách API lấy danh tính và tài nguyên thật | Bổ sung kiểm chứng qua ranh giới phù hợp |
| Test pass trong local branch, release từ commit khác | Không gắn đúng version | Chạy lại/gắn bằng chứng cho artifact được phát hành |
| Log đủ kỹ thuật nhưng lộ token | Vi phạm nguyên tắc bảo vệ bằng chứng | Loại dữ liệu nhạy cảm và xử lý sự cố nếu cần |
| Review phê duyệt nhưng chưa rõ phạm vi | Không xác định nghĩa vụ nào đã được đánh giá | Ghi lại phạm vi và xác nhận đúng thẩm quyền |
| Dashboard báo compliance 100% | Có thể chỉ là tỷ lệ ô được tick | Xem chất lượng nguồn và mức bao phủ rủi ro |
| CI bỏ qua test do môi trường không sẵn sàng | Không có bằng chứng PASS | Block, khôi phục môi trường hoặc xử lý ngoại lệ hợp lệ |

## 7. Đưa kiểm tra vào CI/CD và dòng phát triển

### 7.1. Dịch chuyển phản hồi sớm, không dồn kiểm tra vào release

Một chiến lược có thể gồm:

| Thời điểm | Kiểm soát/phản hồi nên cân nhắc | Bằng chứng tạo ra |
|---|---|---|
| **Discovery/refinement** | Xác định nguồn nghĩa vụ, phạm vi, nguy cơ và ví dụ chấp nhận | Requirement record, risk/control mapping, câu hỏi chưa rõ |
| **Thiết kế** | Threat modeling, data-flow review, chính sách quyền và dữ liệu | Kết luận thiết kế, quyết định, rủi ro còn lại |
| **Khi code** | Compile, lint, unit/component tests, TDD, review code nhỏ | Test run local và thay đổi được version |
| **Pull request** | Static/security checks theo rủi ro, contract/integration thiết yếu, peer review | Kết quả CI gắn commit/PR |
| **Tích hợp** | API–DB, permission, schema/migration, logging, lỗi dependency | Kết quả tích hợp theo build/môi trường |
| **Trước release** | Quality gates bắt buộc, đánh giá chuyên môn nếu chính sách yêu cầu, readiness | Kết luận release và bằng chứng liên kết |
| **Sau release** | Monitoring, quyền thực tế, cấu hình, sự cố, kiểm tra lại khi thay đổi | Dấu vết vận hành và quyết định khắc phục |

Đây là **cách tổ chức linh hoạt**, không áp một chuỗi phê duyệt duy nhất cho mọi dự án. Mỗi điều kiện quan trọng phải có **thời điểm nhận bằng chứng đủ sớm** để không gây tác hại khi phát hành.

### 7.2. Ví dụ pipeline mô tả bằng YAML

~~~yaml
# Pseudocode: ý tưởng tổ chức, KHÔNG phải cấu hình sẵn chạy
# trên một nhà cung cấp CI cụ thể.
on_pull_request:
  - compile_and_type_check
  - unit_and_component_tests
  - targeted_static_security_checks
  - required_api_contract_tests
  - access_control_integration_tests
  - peer_review_for_sensitive_changes

on_mainline:
  - integration_tests_with_isolated_data
  - database_migration_compatibility_checks
  - verify_required_test_reports_are_present
  - attach_commit_build_and_environment_metadata

before_release:
  - confirm_definition_of_done
  - check_release_artifact_matches_verified_build
  - verify_required_controls_for_release_scope
  - obtain_authorized_assessment_if_policy_requires
  - record_remaining_risks_and_decisions

after_release:
  - deployment_smoke_checks
  - monitor_authorization_failures_and_errors
  - review_configuration_drift_and_incidents
  - reassess_evidence_after_material_changes
~~~

**Điểm quan trọng:** kết quả từ một bước **không được giả lập hoặc coi là PASS khi không chạy**. Nếu một kiểm tra bắt buộc chưa thể thực hiện, cần biểu diễn **Not Run/Blocked/Unknown** theo chính sách, không tự đổi thành xanh.

### 7.3. Không phải tất cả kiểm soát đều là CI check

Ví dụ:

- **Secret scanning:** có thể tự động hỗ trợ tìm một số bí mật trong repository; không chứng minh mọi secret đã được quản lý an toàn.
- **Dependency scanning:** cảnh báo phụ thuộc có vấn đề; phải đánh giá điều kiện khai thác, phạm vi và cách xử lý.
- **SAST:** giúp tìm một số mẫu lỗi; vẫn có false positive/false negative.
- **Contract tests:** bảo vệ kỳ vọng giữa consumer/provider; không chứng minh toàn bộ nghiệp vụ hoặc quyền thật.
- **Accessibility static checks:** hỗ trợ phát hiện một số lỗi; còn cần đánh giá tương tác và trải nghiệm phù hợp.
- **Threat-model review:** xem rủi ro thiết kế; không được thay bằng một badge công cụ.
- **Production monitoring:** phát hiện một số vi phạm sau release; không phải giấy phép bỏ kiểm soát trước release.

**Tự động hóa bằng chứng có giới hạn**, nhưng nó giúp phản hồi sớm và giảm khối lượng sao chép giấy tờ nếu được thiết kế đúng.

### 7.4. Dùng test ở mức thấp nhất nhưng đủ bảo đảm

| Rủi ro | Mức kiểm tra có ích | Vì sao không dừng ở một mức? |
|---|---|---|
| Quy tắc truy cập dữ liệu | Unit/component + API integration + security review theo rủi ro | Unit test với mock không chứng minh API gắn đúng tài khoản |
| Dữ liệu nhạy cảm bị ghi log | Code review + kiểm tra log/integration + vận hành | Static pattern không phát hiện mọi đường ghi log |
| API đổi hợp đồng làm lộ trường mới | Contract + integration | Schema đúng vẫn có thể tiết lộ dữ liệu ngoài quyền |
| Dữ liệu tiến độ không nhất quán sau migration | Integration/migration + kế hoạch khôi phục | Unit tests không bao phủ DB thật |
| Trạng thái thông báo không hỗ trợ bàn phím/screen reader | Component UI + manual accessibility check khi cần | Test DOM tự động không phản ánh mọi trải nghiệm |
| Một role có quyền rộng sau thay đổi cấu hình | Configuration review + integration/production control | Test trên môi trường staging có thể khác production |

Không có **tỷ lệ unit/integration/E2E phổ quát**. Chọn danh mục dựa trên tác động, độ tin cậy và chi phí; vẫn bảo vệ các kiểm soát bắt buộc.

### 7.5. Phản hồi nhanh phải đáng tin

Một pipeline trả kết quả trong ba phút nhưng thường **xanh giả** vì thiếu kiểm tra quyền không có nhiều giá trị. Một bộ đầy đủ chạy ba giờ mỗi commit cũng khiến đội dễ bỏ qua kết quả.

Đội cần cân bằng:

1. **Phát hiện:** kiểm soát quan trọng nào được đánh giá?
2. **Độ trễ:** kết quả tới người có thể sửa khi nào?
3. **Độ ổn định:** test có thường fail do môi trường/dữ liệu không liên quan không?
4. **Khả năng chẩn đoán:** lỗi có chỉ đúng requirement/control và nguyên nhân?
5. **Chi phí bảo trì:** test có dễ vỡ khi thay đổi chi tiết không ảnh hưởng hành vi?
6. **Độ tin cậy của bằng chứng:** kết quả có gắn đúng phiên bản và phạm vi?

Nếu công việc dồn ở cuối Sprint vì một kiểm tra tích hợp chưa từng chạy trước đó, đây là vấn đề **dòng phản hồi và thiết kế hệ thống làm việc**, không chỉ “QA làm chậm”.

## 8. Definition of Done, acceptance criteria và điều kiện release

### 8.1. Phân biệt ba lớp tiêu chí

| Lớp | Phạm vi | Ví dụ |
|---|---|---|
| **Acceptance criteria** | Điều kiện cụ thể cho một PBI/khả năng | API không trả tiến độ B khi A không có quyền |
| **Definition of Done** | Chuẩn chất lượng chung của Increment | Đã tích hợp, kiểm tra bắt buộc đạt, không còn yêu cầu chất lượng chưa thỏa |
| **Release criteria/approval** | Điều kiện để đưa phiên bản cụ thể tới người dùng theo quy định thực tế | Artifact đúng build, kiểm soát bắt buộc được xác nhận, kế hoạch rollout/khôi phục sẵn sàng |

Một acceptance test xanh **không tự làm PBI Done** nếu các yêu cầu DoD liên quan chưa đáp ứng. Một Increment đạt DoD cũng **không nhất thiết đã phát hành**, vì quyết định release có thể có điều kiện riêng theo sản phẩm/tổ chức.

### 8.2. Scrum và Definition of Done

Theo Scrum Guide 2020:

- **Increment** là phần sản phẩm có thể sử dụng, được tích hợp với Increment trước.
- **Definition of Done** là mô tả chính thức về trạng thái Increment khi đáp ứng các chuẩn chất lượng cần thiết.
- Nếu một Product Backlog Item không đáp ứng DoD, nó **không thể được phát hành hay trình bày như Increment đã hoàn thành** tại Sprint Review; công việc đó quay lại Product Backlog để xem xét.
- Tổ chức có thể đặt **DoD như tiêu chuẩn tối thiểu**. Scrum Team phải tuân thủ; nếu không có chuẩn tổ chức thì Scrum Team tạo một DoD phù hợp với sản phẩm.

Trong môi trường có ràng buộc cụ thể, Scrum Team cần đưa **những điều kiện chất lượng bắt buộc liên quan** vào DoD và cách làm. Không có lý do Agile hợp lệ để tùy tiện hạ chất lượng khi Sprint sắp hết.

### 8.3. Mẫu DoD cho thay đổi liên quan quyền dữ liệu

**Ví dụ tham khảo cần tổ chức xác nhận**, không phải một DoD chuẩn áp chung:

- Code đã tích hợp vào trạng thái xây dựng có thể sử dụng.
- Acceptance criteria, gồm trường hợp trái quyền và lỗi, đã được kiểm chứng.
- Unit/component/contract/integration checks bắt buộc **đạt theo phạm vi**.
- Những cảnh báo bảo mật quan trọng được xử lý hoặc có kết luận đúng thẩm quyền.
- Không lộ dữ liệu nhạy cảm trong log/test artifacts theo chính sách.
- Yêu cầu kiểm soát liên quan được liên kết tới bằng chứng đúng build.
- Tài liệu hợp đồng API/decision log được cập nhật khi hành vi đổi.
- Kiểm tra vận hành cần thiết và kế hoạch khôi phục phù hợp rủi ro đã được xem.

Không nên thêm vào DoD những điều kiện **quá đặc thù của mọi PBI** khiến nhóm phải ký hồ sơ giống nhau bất kể thay đổi. Có thể có **chính sách áp dụng theo loại thay đổi/rủi ro** cùng với chuẩn chất lượng chung và release controls rõ.

### 8.4. “Đã phê duyệt” không được đánh đồng với “đã kiểm chứng”

Một người có thể phê duyệt release dựa trên **bằng chứng do hệ thống và chuyên gia cung cấp**; lời phê duyệt là quyết định có thẩm quyền, không thay các test chưa chạy.

Ngược lại, một bộ test xanh không có nghĩa hệ thống đã đáp ứng **quy trình phê duyệt độc lập** nếu nghĩa vụ thực sự yêu cầu. Scrum không tự quy định mọi loại approval này; cần phân biệt **accountability trong Scrum** và **thẩm quyền quản trị tổ chức**.

### 8.5. Khi thay đổi quá lớn để đạt DoD trong một Sprint

Đội có thể:

- Chia PBI thành **lát dọc nhỏ có giá trị, có thể tích hợp và kiểm chứng**.
- Giữ những phần chưa đạt chuẩn là **chưa Done**, không đếm vào Increment hoàn thành.
- Phân bổ năng lực cho test, tài liệu và review cần thiết ngay từ Planning.
- Dùng feature flags/rollout được kiểm soát nếu phù hợp; vẫn phải kiểm tra trạng thái bật/tắt và rủi ro dữ liệu.
- Thương lượng phạm vi với Product Owner khi học thêm, không tự bỏ kiểm soát bắt buộc.

Không nên “chuyển nợ compliance sang Sprint sau” mà vẫn trình bày chức năng có rủi ro như đã hoàn thành đầy đủ.

## 9. Gắn bằng chứng với quyết định phát hành

### 9.1. Release không chỉ là nhấn nút Deploy

Một release cần câu trả lời:

- Artifact nào sẽ phát hành? Có khớp build đã được kiểm tra?
- Những thay đổi nào nằm trong phạm vi?
- Các kiểm soát bắt buộc với thay đổi đó đã được xác minh?
- Có kiểm tra/approval nào chưa hoàn tất? Tình trạng được ghi thế nào?
- Rủi ro tồn dư, phụ thuộc, migration dữ liệu hoặc rollback có được đánh giá?
- Ai có trách nhiệm đưa ra quyết định theo chính sách?
- Nếu có vấn đề sau rollout, ai nhận tín hiệu và hành động thế nào?

Không cần một cuộc họp phê duyệt lớn cho mọi thay đổi ít rủi ro. **Mức kiểm soát phải tương xứng rủi ro, nghĩa vụ và khả năng đảo ngược**, không chỉ theo số dòng code.

### 9.2. Manifest phát hành và bằng chứng liên quan

~~~json
{
  "releaseId": "learn-progress-release-example",
  "artifactVersion": "<phiên-bản-thật>",
  "commitSha": "<commit-thật>",
  "buildId": "<build-thật>",
  "controlScope": [
    "REQ-ACCESS-01",
    "REQ-STATE-02"
  ],
  "evidenceLinks": [
    "<kết-quả-integration-thật>",
    "<kết-luận-review-hợp-lệ>"
  ],
  "verificationStatus": "PENDING_UNTIL_EVIDENCE_IS_CHECKED",
  "residualRisks": [],
  "releaseDecision": "NOT_YET_APPROVED"
}
~~~

Đây là **biểu mẫu dữ liệu minh họa**, cố ý để trạng thái chờ xác minh. **Không được đổi thành APPROVED khi chưa có bằng chứng và thẩm quyền thực**.

### 9.3. Kiểm tra liên kết build–test–release

Một lỗi phổ biến:

1. Test chạy trên commit **A**.
2. Developer sửa quyền ở commit **B**.
3. Pipeline tạo artifact từ commit **B** nhưng ảnh test xanh là của **A**.
4. Hồ sơ release gắn ảnh test cũ và kết luận kiểm soát đạt.

Vấn đề không phải “test đã đỏ hay chưa”, mà là **bằng chứng không đại diện cho artifact được phát hành**. Cần gắn định danh build/commit/cấu hình và quy định cách xác minh tính tương ứng.

Một pipeline có thể tự động hóa **linkage** này. Nếu công cụ chưa hỗ trợ, quy trình review phải đủ tin cậy nhưng cũng nên có kế hoạch giảm thao tác sao chép dễ sai.

### 9.4. Rollout có kiểm soát và trách nhiệm vận hành

Tùy mức rủi ro, nhóm có thể:

- Phát hành lát cắt nhỏ.
- Dùng feature flags với quyền và trạng thái được kiểm soát.
- Rollout theo giai đoạn, theo dõi lỗi/guardrails.
- Chuẩn bị cách giới hạn tác động hoặc khôi phục.
- Ghi lại ai có thẩm quyền dừng rollout khi xuất hiện rủi ro.

**Rollback không tự phục hồi dữ liệu đã mất hoặc đảo ngược mọi migration.** Với thay đổi có tác động dữ liệu, cần đánh giá tính đảo ngược, sao lưu/khôi phục và các ràng buộc liên quan.

### 9.5. Sau phát hành vẫn có nghĩa vụ kiểm tra

Kiểm soát có thể mất hiệu lực do:

- Thay đổi role/permission trong production.
- Drift cấu hình hoặc quyền cloud.
- Key/secret hết hạn hoặc bị xử lý sai.
- Dependency thay đổi hành vi.
- Dịch vụ mới đọc dữ liệu theo hợp đồng khác.
- Chính sách hoặc nghĩa vụ thay đổi.

Vì thế, cần xác định **điểm kích hoạt kiểm chứng lại** và monitoring/hậu kiểm phù hợp. “Passed một lần” không luôn đồng nghĩa “vẫn đạt mãi”.

## 10. Quản lý thay đổi phạm vi tuân thủ trong Product Backlog

### 10.1. Không coi tất cả yêu cầu kiểm soát là một loại ticket

Các hạng mục có thể xuất hiện trong Product Backlog:

| Loại công việc | Ví dụ | Cách mô tả giá trị hoặc rủi ro |
|---|---|---|
| **Feature/PBI hành vi** | Người học tự lưu tiến độ | Tạo khả năng có giá trị, kèm acceptance criteria |
| **Lát cắt bảo vệ quyền** | Ngăn tài khoản khác đọc tiến độ | Giảm rủi ro lộ dữ liệu, hỗ trợ mục tiêu sản phẩm |
| **Enabler kỹ thuật** | Chuẩn hóa cơ chế kiểm tra quyền server | Làm các thay đổi tương lai ít lỗi và dễ kiểm chứng |
| **Kiểm chứng hoặc nghiên cứu** | Xác định lưu giữ dữ liệu theo nguồn nghĩa vụ | Giảm bất định trước khi cam kết xây |
| **Khắc phục phát hiện** | Sửa lỗi log chứa thông tin nhạy cảm | Xử lý rủi ro đã được xác minh |
| **Bổ sung bằng chứng** | Kết nối test run với build release | Giảm sai lệch hồ sơ và thời gian kiểm tra |
| **Thay đổi quy trình** | Chính sách cảnh báo PBI thiếu evidence | Phát hiện blocker trước thời điểm phát hành |

Không bắt buộc viết mọi việc thành user story “Là người dùng…”. Enabler và kiểm soát có thể được mô tả bằng **mục tiêu, tác động, điều kiện xác minh**, không cần giả một nhu cầu UI.

### 10.2. Các chiều để sắp thứ tự

Product Owner cùng Scrum Team và chuyên gia liên quan cân nhắc:

1. **Bắt buộc hay tùy chọn?** Nguồn và thẩm quyền của yêu cầu?
2. **Mức ảnh hưởng nếu không thực hiện:** người dùng, dữ liệu, hoạt động, hợp đồng?
3. **Thời điểm bắt buộc:** hạn thật, điều kiện release, phụ thuộc?
4. **Mức chắc chắn về yêu cầu:** đã được diễn giải rõ hay cần nghiên cứu?
5. **Khả năng giảm rủi ro bằng lát cắt nhỏ:** có cách làm sớm không?
6. **Năng lực và phụ thuộc:** test, môi trường, chuyên gia, đối tác?
7. **Chi phí cơ hội:** việc được làm trước sẽ đẩy việc gì lùi lại?
8. **Tín hiệu kiểm chứng:** khi nào biết kiểm soát thực sự hiệu quả?

Không nên dùng **một điểm ưu tiên chung** để bỏ qua nghĩa vụ bắt buộc hoặc rủi ro nghiêm trọng. Những hạn chế có thẩm quyền có thể là **ràng buộc của lựa chọn**, không chỉ một ứng viên để chấm điểm ngang với tính năng trang trí.

### 10.3. Không tự tạo cam kết thời hạn chắc chắn

Một hạng mục compliance có hạn pháp lý/hợp đồng thật cần được nhận diện và quản lý; còn ngày hoàn thành kỹ thuật **vẫn là dự báo chịu bất định**.

Nhóm nên minh bạch:

- Nghĩa vụ và **ngày có hiệu lực/hạn phải đáp ứng** nếu được xác nhận.
- Phạm vi cần xong để đáp ứng.
- Năng lực, phụ thuộc, kiểm chứng/approval cần thiết.
- Dự báo và mức tin cậy hiện tại.
- Các lựa chọn giảm phạm vi hoặc triển khai từng bước không vi phạm nghĩa vụ.
- Quyết định nào cần người có thẩm quyền, trước thời điểm nào.

Không nên chấp nhận một “deadline” do ai đó nói trong chat thành luật; cũng không nên xem hạn đã xác minh như việc có thể tự trì hoãn bằng đổi thứ tự backlog.

### 10.4. Chia lát cắt tuân thủ thay vì làm một Epic vô tận

Epic giả định: “Bảo vệ mọi dữ liệu người học, đáp ứng toàn bộ yêu cầu”.

Cách chia khả thi hơn:

1. **Kiểm tra quyền đọc tiến độ trên API chính**, có ví dụ được phép/trái quyền.
2. **Kiểm tra quyền ghi và xử lý phiên hết hạn**, gắn bằng chứng đúng build.
3. **Giảm thông tin nhạy cảm trong log**, có kiểm tra và chính sách truy cập.
4. **Bảo vệ luồng xuất dữ liệu**, nếu đã được xác nhận nằm trong phạm vi.
5. **Vận hành/giám sát quyền thực tế**, kích hoạt kiểm tra lại theo thay đổi.

Mỗi lát cắt nên **có kết quả kiểm chứng riêng** và tích hợp đủ để không tạo cảm giác “đã đạt toàn bộ compliance” khi chỉ hoàn thành bước đầu.

### 10.5. Discovery với người am hiểu nghĩa vụ

Một cuộc trao đổi sớm có thể gồm:

- Product Owner: giá trị, Product Goal, phạm vi và ưu tiên.
- Developers: kiến trúc, dữ liệu, dependency và phương án kiểm soát.
- Tester/chuyên gia chất lượng: ví dụ kiểm chứng, trường hợp lỗi và bằng chứng.
- Người có chuyên môn bảo mật/riêng tư/pháp chế/kiểm toán: cách hiểu nghĩa vụ, kiểm soát và approval trong phạm vi được trao quyền.

Đây là **hình thức cộng tác có thể lựa chọn**, không phải Scrum Event chính thức mới. Nếu nghĩa vụ chưa rõ, ghi câu hỏi và cần quyết định; **không suy đoán rồi biến giả định thành chính sách**.

## 11. Tích hợp quản trị vào Scrum mà không phá vỡ tính thực nghiệm

### 11.1. Scrum không “miễn trừ” nghĩa vụ tuân thủ

Scrum định nghĩa trách nhiệm, sự kiện, artifacts và commitments để tạo giá trị trong môi trường phức tạp. Nó **không quy định bộ luật, mẫu hồ sơ hay framework compliance bắt buộc**, và cũng không cho phép bỏ nghĩa vụ đã được xác nhận.

Trong một tổ chức có ràng buộc:

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog, gồm thứ tự hạng mục.
- **Developers** chịu trách nhiệm tạo Increment có thể sử dụng, lập/điều chỉnh Sprint Backlog, bảo đảm chất lượng bằng DoD và chịu trách nhiệm nghề nghiệp với kế hoạch.
- **Scrum Master** chịu trách nhiệm về hiệu quả Scrum Team, hỗ trợ Scrum, phối hợp gỡ trở ngại tổ chức.
- **Chuyên gia/đơn vị kiểm soát** có thể có quyền xác nhận nghĩa vụ, yêu cầu đánh giá độc lập hoặc quyền phê duyệt theo quy định tổ chức. Họ không tự trở thành một Scrum accountability mới.

**Phân quyền tổ chức và Scrum accountabilities phải được làm rõ cùng nhau**, không để một bên dùng tên Scrum hoặc compliance để lấn sang quyết định ngoài thẩm quyền.

### 11.2. Product Backlog refinement: nơi tốt để phát hiện nghĩa vụ sớm

Khi làm rõ một PBI liên quan dữ liệu người học:

1. Product Owner nêu **người dùng, Product Goal và giá trị**.
2. Developers xác định **dữ liệu, service, giao diện và các ranh giới thay đổi**.
3. Nhóm mời chuyên môn phù hợp để xác nhận **nguồn ràng buộc và phạm vi áp dụng**.
4. Viết **acceptance examples** cho happy path, trái quyền, lỗi và ngoại lệ.
5. Xác định **bằng chứng cần tạo** và điều kiện DoD/release liên quan.
6. Chia PBI thành lát cắt đủ nhỏ để kiểm chứng sớm.

Refinement là **hoạt động liên tục**, không phải Scrum Event chính thức. Không nên đợi buổi Sprint Planning mới bắt đầu hỏi về quyền và dữ liệu khi biết PBI có rủi ro cao từ trước.

### 11.3. Sprint Planning: tính cả công việc kiểm chứng

Để có Sprint Goal khả thi, Developers cần tính:

- Thời gian xây và tích hợp chức năng.
- Viết/chạy test theo rủi ro.
- Review kiểm soát hoặc quyết định chuyên môn cần thiết.
- Phụ thuộc môi trường, quyền truy cập và người phê duyệt theo chính sách.
- Công việc khắc phục và bất định còn mở.

Nếu chỉ ước lượng code rồi xem kiểm chứng là “việc của QA sau Sprint”, nhóm dễ lập kế hoạch sai và dồn lỗi tới cuối.

### 11.4. Daily Scrum: phát hiện blocker ảnh hưởng Sprint Goal

Daily Scrum là sự kiện **15 phút dành cho Developers** để kiểm tra tiến độ hướng Sprint Goal và thích ứng Sprint Backlog.

Ví dụ:

- Contract test của API tiến độ chưa có môi trường.
- Người xác nhận chính sách quyền đang không sẵn sàng.
- Một lỗi quyền truy cập trái phép mới được phát hiện.
- Evidence gắn sai build và cần chạy lại kiểm tra.

Developers cần **làm rõ kế hoạch**, phối hợp hỗ trợ và đưa trở ngại lên đúng người; không biến Daily Scrum thành cuộc họp phê duyệt tuân thủ hoặc bảng báo cáo cho quản lý.

### 11.5. Sprint Review: kiểm tra Increment và rủi ro sản phẩm

Sprint Review giúp Scrum Team và stakeholders kiểm tra kết quả Sprint, bối cảnh thay đổi và những việc cần làm tiếp. Tại đây có thể:

- Trình bày **Increment thực sự đáp ứng DoD**.
- Minh bạch điều gì đã được kiểm chứng về quyền/trạng thái dữ liệu.
- Chia sẻ giới hạn bằng chứng và rủi ro cần xử lý.
- Nhận phản hồi về trải nghiệm thông báo lỗi hoặc luồng học.
- Điều chỉnh Product Backlog theo thông tin mới.

**Sprint Review không phải một cổng nghiệm thu duy nhất** để kiểm tra control; các hoạt động kiểm chứng phải diễn ra đủ sớm trong Sprint. Một PBI chưa đạt DoD không nên được giới thiệu như Increment đã Done.

### 11.6. Sprint Retrospective: cải tiến hệ thống kiểm chứng

Retrospective có thể đặt câu hỏi:

- Kiểm soát nào thường bị phát hiện quá muộn?
- Bằng chứng nào bị thiếu trường version/owner?
- Approval nào liên tục chờ người không có giờ làm chung?
- Test nào flaky khiến nhóm không tin CI?
- Có bước sao chép hồ sơ bằng tay nào dễ lỗi mà có thể tự động hóa?
- Chất lượng có bị đẩy thành việc ngoài giờ khi Sprint sắp kết thúc?

Kết quả nên là **một vài thử nghiệm cải tiến với người phối hợp và tín hiệu kiểm chứng**, không phải khẩu hiệu “làm compliance sớm hơn”.

### 11.7. Sprint Goal, phạm vi và quyền hủy Sprint

Trong Sprint, Sprint Goal tạo trọng tâm. Khi học thêm về một ràng buộc:

- Developers có thể điều chỉnh Sprint Backlog và thương lượng phạm vi với Product Owner.
- **Chất lượng không được giảm** chỉ vì xuất hiện kiểm soát chưa dự kiến.
- Nếu Sprint Goal thực sự **trở nên lỗi thời**, chỉ Product Owner có thẩm quyền hủy Sprint theo Scrum Guide.
- Một sự cố nghiêm trọng có thể cần ứng cứu ngay theo chính sách, **không nhất thiết đồng nghĩa hủy mọi Sprint**.

Khi có nghĩa vụ mới phát sinh, đội phải minh bạch tác động, năng lực và quyết định đúng thẩm quyền; không âm thầm “bỏ qua để kịp deadline”.

## 12. Kanban: làm hiển thị kiểm chứng và thời gian chờ

### 12.1. Kiểm soát cũng có thể tạo hàng chờ

Nếu nhóm code xong sáu PBI rồi cùng chuyển sang “Awaiting Security Review”, tất cả có thể bị chặn đến cuối Sprint. Khi đó vấn đề không nhất thiết là chuyên gia an toàn “quá chậm”; có thể vì:

- PBI lớn, nhiều việc tới kiểm chứng cùng lúc.
- Mỗi PBI yêu cầu review thủ công giống nhau dù rủi ro khác nhau.
- Chưa có tiêu chí gửi review rõ ràng, phải hỏi đi hỏi lại.
- Chuyên gia chỉ được mời khi mọi thứ đã hoàn thiện.
- Bằng chứng không gắn build, phải làm lại.
- Workflow không hiển thị thời điểm bắt đầu chờ hoặc người hỗ trợ.

Kanban giúp mô tả **dòng công việc thực tế**, không chỉ dòng code.

### 12.2. Definition of Workflow có thể bao gồm kiểm soát

Một workflow minh họa:

~~~mermaid
flowchart LR
    A["Ready: yêu cầu / rủi ro rõ"] --> B["Implement + verify"]
    B --> C["Review theo mức rủi ro"]
    C --> D["Integrate + required checks"]
    D --> E["Done theo DoD"]
    B -. "Blocked" .-> F["Chờ nghĩa vụ / môi trường / thẩm quyền"]
    C -. "Blocked" .-> F
    D -. "Blocked" .-> F
    F -. "Đã giải quyết" .-> B
~~~

Không nhất thiết mọi PBI đều qua **cùng một cột review thủ công**. Có thể đưa kiểm tra phù hợp vào hoạt động xây dựng, nhưng phải giữ **Definition of Done và yêu cầu bắt buộc**.

### 12.3. Các phép đo flow

| Phép đo | Định nghĩa cơ bản | Tín hiệu tuân thủ có thể thấy |
|---|---|---|
| **WIP** | Số hạng mục đã bắt đầu nhưng chưa hoàn thành | Có quá nhiều PBI mở đang chờ evidence/review? |
| **Work item age** | Tuổi của hạng mục đang mở tính từ lúc bắt đầu | PBI nào đang chờ kiểm soát quá lâu? |
| **Cycle time** | Thời gian từ bắt đầu tới Done của hạng mục đã xong | Tích hợp kiểm chứng sớm có rút thời gian đạt Done? |
| **Throughput** | Số hạng mục Done trong một khoảng | Việc hoàn thành có đều, bền vững không? |

Các phép đo cần **định nghĩa thời điểm bắt đầu/Done nhất quán**. Không dùng throughput hoặc cycle time để xếp hạng cá nhân, và không chuyển PBI còn thiếu DoD sang Done để làm số đẹp.

### 12.4. Ví dụ work item age của kiểm soát

| PBI | Trạng thái | Tuổi công việc minh họa | Rủi ro cần nhìn |
|---|---|---:|---|
| PBI-42 | Chờ API integration test | 6 ngày | Kiểm soát quyền chưa có bằng chứng qua ranh giới thật |
| PBI-43 | Chờ định nghĩa retention | 4 ngày | Yêu cầu nguồn chưa được người có thẩm quyền làm rõ |
| PBI-44 | Đang khắc phục log | 2 ngày | Có phát hiện dữ liệu nhạy cảm, cần xử lý phù hợp |
| PBI-45 | Đã đạt DoD | Không tính age đang mở | Dùng cycle time khi phân tích công việc đã xong |

Số liệu **hoàn toàn minh họa**. Cần phân biệt chờ bình thường, chờ phụ thuộc không hợp lý và xử lý sự cố khẩn theo chính sách.

### 12.5. WIP limit và chính sách ngoại lệ

Khi nhiều PBI chờ kiểm tra:

- Tạm hạn chế kéo việc mới để giúp hoàn tất việc đang mở.
- Chia PBI thành lát cắt nhỏ, có review và evidence sớm.
- Tăng khả năng **tự kiểm tra** bằng checklists/tests đủ tin cậy.
- Làm rõ đầu vào review để giảm vòng hỏi lại.
- Thiết lập chính sách cho **hạng mục khẩn/sự cố**, tránh lạm dụng nhãn “compliance” để chen ngang mọi việc.

Không có một con số WIP chuẩn cho mọi đội. Mục tiêu là **luồng hoàn thành đáng tin**, không làm giảm tiêu chuẩn kiểm soát.

## 13. XP và Lean: xây chất lượng tại nguồn

### 13.1. Thực hành kỹ thuật giúp giảm “compliance làm sau”

| Thực hành | Tác động có ích |
|---|---|
| **TDD** | Viết kiểm tra cho quy tắc quyền/trạng thái trước khi code, nhận phản hồi nhanh |
| **BDD/ATDD** | Các bên làm rõ nghĩa vụ nghiệp vụ thành ví dụ chấp nhận trước implementation |
| **Pair programming** | Phát hiện giả định sớm, chia tri thức và review khi xử lý kiểm soát khó |
| **Refactoring** | Giữ kiến trúc dễ thay đổi khi chính sách hoặc cách hiểu yêu cầu đổi |
| **Continuous Integration** | Kiểm tra thường xuyên và gắn bằng chứng với thay đổi |
| **Small releases** | Khoanh vùng thay đổi, dễ đánh giá phạm vi rủi ro và nhận phản hồi |
| **Collective code ownership** | Giảm phụ thuộc một người khi sửa kiểm soát thiết yếu |
| **Sustainable pace** | Tránh cắt bỏ test/review khi áp lực giao hàng tích tụ |

Không phải mọi tổ chức phải dùng toàn bộ XP, nhưng các thực hành có thể hỗ trợ **kiểm chứng sớm, code dễ thay đổi và kết quả dễ truy xuất**.

### 13.2. TDD khác việc “có unit tests”

TDD dùng vòng **Red → Green → Refactor**:

1. Viết test thất bại cho hành vi nhỏ đã rõ.
2. Viết code đủ làm test qua.
3. Cải thiện thiết kế và chạy lại test.

Với quy tắc phân quyền, một unit test có thể kiểm tra “chủ thể không đủ quyền bị từ chối”. Nhưng **unit test với fake repository không chứng minh API thực không rò dữ liệu**; vẫn cần integration/security tests theo rủi ro.

### 13.3. BDD/ATDD là công cụ khám phá ràng buộc

Một buổi trao đổi theo các góc nhìn sản phẩm, phát triển và kiểm thử có thể hỏi:

- “Thế nào là được phép truy cập tiến độ?”
- “Tài khoản hỗ trợ có quyền gì trong trường hợp khẩn?”
- “Nếu session hết hạn, API trả thông tin nào?”
- “Người học biết kết quả lưu **chưa xác định** thế nào?”
- “Những ví dụ nào chứng minh kiểm soát đạt điều kiện chấp nhận?”

BDD nhấn mạnh **Discovery và ngôn ngữ nghiệp vụ chung**. ATDD nhấn mạnh **các ví dụ chấp nhận được thống nhất trước code**. Chúng giao nhau nhưng **không nhất thiết là hai bộ test riêng**.

### 13.4. Lean: giảm lãng phí mà không giảm kiểm soát

Một số lãng phí có thể giảm:

- Chụp cùng một ảnh test xanh nhiều lần cho nhiều báo cáo.
- Gửi email xin phê duyệt mỗi PBI nhưng không kèm bối cảnh, phải hỏi đi hỏi lại.
- Chạy thử quyền chỉ ở cuối Sprint và sửa lại cả UI–API.
- Lưu evidence thủ công không gắn commit, tới release phải đối chiếu lại.
- Bắt mọi PBI ít rủi ro qua cùng một review sâu như thay đổi phân quyền.

**Một kiểm soát bắt buộc không phải “lãng phí” chỉ vì tốn công.** Lean hướng tới loại bỏ hoạt động không tạo giá trị, đồng thời xây chất lượng tại nguồn và giảm sai lệch, không tùy tiện bỏ biện pháp phòng rủi ro.

### 13.5. Kết hợp vòng phản hồi kỹ thuật và sản phẩm

~~~mermaid
flowchart TD
    P["Product Goal + nghĩa vụ đã xác nhận"] --> D["BDD/ATDD: ví dụ và rủi ro"]
    D --> T["TDD + engineering practices"]
    T --> C["CI: kiểm chứng và tạo evidence"]
    C --> I["Increment đạt DoD"]
    I --> R["Release theo rủi ro và thẩm quyền"]
    R --> F["Feedback sản phẩm + quan sát kiểm soát"]
    F --> P
~~~

Một CI build xanh là **phản hồi kỹ thuật**; một quyết định release hợp lệ là **phản hồi quản trị**; outcome người dùng là **phản hồi giá trị**. Cần cả ba nếu sản phẩm có nghĩa vụ kiểm soát quan trọng.

## 14. Ngoại lệ, kiểm tra chưa đạt và rủi ro tồn dư

### 14.1. Không có bằng chứng không đồng nghĩa đã đạt

Các trạng thái nên được phân biệt:

| Trạng thái | Ý nghĩa |
|---|---|
| **PASS** | Đã chạy/đánh giá đúng tiêu chí trong phạm vi và kết quả đạt |
| **FAIL** | Đã xác minh điều kiện không đạt |
| **NOT RUN** | Kiểm tra chưa chạy; không có kết quả |
| **BLOCKED** | Không thể kiểm tra vì dependency/môi trường/quyết định |
| **NOT APPLICABLE** | Đã được người phù hợp xác nhận không nằm trong phạm vi áp dụng |
| **EXCEPTION REQUESTED** | Có đề nghị ngoại lệ; chưa có quyết định hợp lệ |
| **EXCEPTION APPROVED** | Ngoại lệ được chấp nhận **trong phạm vi và thời hạn** theo đúng thẩm quyền |
| **EXPIRED/REVOKED** | Ngoại lệ không còn hiệu lực hoặc đã bị thu hồi |

**NOT APPLICABLE phải có lý do**, không phải nhãn tiện để bỏ qua test khó. **APPROVED EXCEPTION không biến một FAIL thành PASS**; nó là quyết định quản lý rủi ro riêng, với điều kiện và trách nhiệm tương ứng.

### 14.2. Phân biệt waiver, risk acceptance và remediation

- **Remediation:** sửa nguyên nhân để kiểm soát đáp ứng yêu cầu.
- **Compensating control:** một biện pháp khác được đánh giá đủ phù hợp khi kiểm soát gốc chưa thể thực hiện, **nếu chính sách cho phép**.
- **Risk acceptance/waiver:** người có thẩm quyền chấp nhận rủi ro trong phạm vi, điều kiện và thời gian nhất định; **không phải lúc nào cũng hợp lệ**, nhất là nghĩa vụ pháp lý không cho miễn trừ.
- **Temporary restriction:** giới hạn chức năng/rollout để tránh rủi ro trong khi chờ sửa.
- **Defer feature:** hoãn một khả năng chưa đáp ứng kiểm soát, bảo vệ phần sản phẩm đang hoạt động.

Không dùng từ “waiver” như chiếc vé bỏ qua luật hoặc yêu cầu không thể miễn trừ. Nếu nghĩa vụ không cho phép ngoại lệ, phải **đáp ứng, thay đổi phạm vi hoạt động hoặc dừng chức năng liên quan theo thẩm quyền**.

### 14.3. Bản ghi ngoại lệ minh họa

~~~yaml
# Mẫu quản trị ngoại lệ; KHÔNG phải một ngoại lệ đã được phê duyệt.
exception_id: EXC-ACCESS-02
requirement_id: REQ-ACCESS-01
requested_state: "EXCEPTION_REQUESTED"
gap: "Một kiểm chứng tích hợp cần thiết chưa chạy được"
reason: "Môi trường kiểm thử dùng chung không khả dụng"
affected_scope: "Chức năng tiến độ chưa được mở cho người dùng"
impact_assessment: "Chờ chuyên gia có thẩm quyền xác minh"
proposed_mitigation:
  - "Không bật chức năng cho tới khi kiểm tra đạt"
  - "Khôi phục môi trường và chạy kiểm tra liên quan"
requested_by: "Người đề nghị có định danh thật trong công cụ"
authorized_decision_maker: "Theo chính sách được xác nhận"
valid_until: "Chỉ ghi nếu được phê duyệt hợp lệ"
reassessment_trigger: "Môi trường khôi phục hoặc phạm vi thay đổi"
decision: "PENDING"
evidence_links: []
~~~

Trong ví dụ, **đề nghị chưa phê duyệt và chưa có test**, vì vậy không được dùng làm căn cứ tuyên bố đáp ứng kiểm soát.

### 14.4. Chính sách ứng phó khi phát hiện vi phạm

Nếu một API đang sản xuất cho phép đọc dữ liệu người học khác trái quyền:

1. **Bảo vệ người dùng và giảm tác động** theo quy trình sự cố.
2. Xác minh phạm vi, phiên bản và hành vi mà không mở rộng truy cập trái phép.
3. Thu thập bằng chứng kỹ thuật bằng kênh được phép, tránh lan truyền dữ liệu nhạy cảm.
4. Phối hợp với người có thẩm quyền về bảo mật, riêng tư, pháp lý và vận hành tùy bối cảnh.
5. Sửa và kiểm chứng lại, không chỉ đổi trạng thái ticket.
6. Đánh giá yêu cầu thông báo/báo cáo nếu có theo nghĩa vụ thật.
7. Hậu kiểm cơ chế đã cho phép lỗi xuất hiện, lan và phát hiện muộn.

Không đợi Sprint Retrospective để xử lý một sự cố nghiêm trọng đang xảy ra. **Retrospective** có thể giúp cải tiến hệ thống sau khi ứng cứu.

### 14.5. Trách nhiệm về khoảng trống kiểm soát

Một khoảng trống có thể bắt nguồn từ:

- Nghĩa vụ diễn giải chưa rõ.
- Môi trường test/nhà cung cấp chưa sẵn sàng.
- Kiến trúc cũ thiếu cơ chế kiểm soát.
- Năng lực review chuyên môn bị giới hạn.
- Một thay đổi policy mới.

Vì vậy, cần xác định **người chịu trách nhiệm phối hợp và người có thẩm quyền quyết định**, không tự đổ lỗi cho Developer hoặc Tester cuối chuỗi. Nhưng cũng không dùng cách nói “lỗi hệ thống” để che hành vi cố ý bỏ qua kiểm soát; các trường hợp nghiêm trọng phải xử lý qua kênh thích hợp.

## 15. Cộng tác với chức năng kiểm soát và đối tác ngoài đội

### 15.1. Tránh mô hình “compliance làm kiểm toán cuối kỳ” nếu có thể

Một số đánh giá độc lập phải có thời điểm và thẩm quyền riêng. Tuy nhiên, nhiều câu hỏi kiểm soát có thể được **làm rõ trước code** để giảm công việc phải làm lại:

- API nào xử lý dữ liệu nhạy cảm?
- Role model hiện tại đã được chấp nhận chưa?
- Bằng chứng cho phép truy cập đúng quyền cần có gì?
- Môi trường test có được dùng dữ liệu thật không?
- Release có gate chuyên môn nào không thể bỏ?

**Trao đổi sớm không làm mất tính độc lập** nếu nhiệm vụ của người đánh giá độc lập được bảo đảm theo chính sách.

### 15.2. RACI/RAPID và trách nhiệm Scrum: dùng để làm rõ, không áp máy móc

Tổ chức có thể dùng ma trận trách nhiệm như RACI để biết ai thực hiện, ai tham vấn, ai được thông báo. Nhưng cần tránh:

- Dùng RACI để làm mờ accountability của Product Owner với Product Backlog.
- Cho rằng Scrum Master có quyền ký mọi rủi ro tuân thủ.
- Giao “security owner” cho Developer rồi bỏ qua thẩm quyền phê duyệt theo chính sách.
- Xem mọi phê duyệt là quyền của người quản lý trực tiếp dù nghĩa vụ yêu cầu đánh giá độc lập.

Một bảng minh họa:

| Hoạt động | Product Owner | Developers | Scrum Master | Chuyên gia/đơn vị kiểm soát |
|---|---|---|---|---|
| Ưu tiên PBI đáp ứng giá trị và ràng buộc | Chịu accountability Product Backlog | Cung cấp khả năng/rủi ro/chi phí | Hỗ trợ gỡ trở ngại | Cung cấp nghĩa vụ và rủi ro liên quan |
| Thiết kế/hiện thực kiểm soát trong code | Làm rõ hành vi sản phẩm | Thực hiện và giữ chất lượng Increment | Hỗ trợ hiệu quả phối hợp | Tham vấn/review theo trách nhiệm được giao |
| Đánh giá nghĩa vụ/approval đặc thù | Phối hợp theo phạm vi sản phẩm | Cung cấp bằng chứng | Hỗ trợ tháo gỡ nghẽn | Thực hiện theo thẩm quyền của tổ chức |
| Xử lý trở ngại khiến kiểm chứng bị chờ | Sắp lại phạm vi/giá trị nếu cần | Làm rõ trạng thái và phương án | Giúp tháo gỡ trở ngại | Hỗ trợ trong giới hạn thẩm quyền |

Bảng này **không thay chính sách chính thức**; mỗi tổ chức cần xác nhận tên vai trò và quyền thực tế.

### 15.3. Handoff kiểm soát có cấu trúc

Một yêu cầu review yếu:

> “@security kiểm tra giúp trước release, gấp.”

Một yêu cầu hữu ích nên có:

~~~text
PBI / RELEASE: LEARN-42 — API lưu tiến độ
MỤC ĐÍCH KIỂM SOÁT: Ngăn đọc/ghi dữ liệu tiến độ trái quyền
NGUỒN NGHĨA VỤ: REQ-ACCESS-01, chính sách phiên bản đã xác nhận
PHẠM VI THAY ĐỔI: Endpoint đọc/ghi, role mapping và schema liên quan
ĐÃ KIỂM CHỨNG: Unit, contract, integration test với link build
CHƯA KIỂM CHỨNG: Kịch bản quyền của vai trò hỗ trợ (chờ làm rõ)
RỦI RO / QUYẾT ĐỊNH CẦN: Xác nhận phạm vi role hỗ trợ
MỐC PHẢN HỒI MONG MUỐN: Ngày/giờ cụ thể với múi giờ và lý do
LIÊN KẾT: PBI, PR, contract, test report, decision log
NGƯỜI PHỐI HỢP: Đầu mối kỹ thuật/PO theo mục đích
~~~

Handoff rõ giúp chuyên gia đánh giá **đúng câu hỏi**, giảm vòng hỏi lại và không bị áp lực phê duyệt một phạm vi chưa minh bạch.

### 15.4. Phụ thuộc nhà cung cấp

Nếu nền tảng học dùng dịch vụ ngoài cho định danh, lưu trữ hoặc gửi email, cần phân biệt:

- Điều tổ chức **có thể kiểm soát trực tiếp**.
- Điều nhà cung cấp **cam kết theo hợp đồng**.
- Điều phải được **đối chiếu bằng bằng chứng hoặc đánh giá phù hợp**.
- Điều kiểm chứng trong môi trường thử **không thể thay bằng một giấy chứng nhận chung** của nhà cung cấp.
- Cách xử lý khi nhà cung cấp đổi hợp đồng, phạm vi hoặc trạng thái dịch vụ.

Không giả định nhà cung cấp “đã có chứng nhận” nghĩa là sản phẩm của mình **tự động tuân thủ mọi nghĩa vụ**. Cần xác định **phạm vi trách nhiệm chia sẻ**, nguồn bằng chứng và thời điểm đánh giá lại.

### 15.5. Tài liệu nhiều nhưng không tìm được cũng là trở ngại

Một hệ thống có hàng trăm file PDF và screenshot nhưng không truy vết được tới build/requirement sẽ khiến review chậm. Có thể cải thiện:

- ID thống nhất cho control/requirement.
- Link trực tiếp tới kết quả CI và build.
- Quy tắc đặt tên, quyền truy cập và phiên bản.
- Danh mục bằng chứng theo phạm vi/phiên bản.
- Chủ sở hữu nội dung và kích hoạt review khi thay đổi.
- Tránh bản sao rải rác nếu đã có nguồn chính.

**Truy xuất được đúng bằng chứng** có giá trị hơn “lưu càng nhiều file càng tốt”.

## 16. Case study xuyên suốt: phát hành chức năng lưu tiến độ có thể kiểm chứng

### 16.1. Bối cảnh và giả định

Một Scrum Team xây dịch vụ học trực tuyến có **Product Goal**:

> “Người học có thể bắt đầu, lưu và tiếp tục bài học đáng tin, từng bước tăng tỷ lệ hoàn thành bài đầu.”

Đội chuẩn bị một Increment cho chức năng **lưu tiến độ và xem lại vị trí học**. Các thành phần gồm:

- Frontend web/mobile.
- API đọc/ghi tiến độ.
- Database lưu trạng thái.
- Dịch vụ định danh.
- Hệ thống log, metrics và CI/CD.

Để minh họa quy trình, giả định tổ chức đã xác nhận **ba yêu cầu nội bộ** sau:

1. **REQ-ACCESS-01:** chỉ chủ thể có quyền mới được đọc/ghi dữ liệu tiến độ.
2. **REQ-STATE-02:** ứng dụng không được thông báo “Đã lưu” nếu chưa có xác nhận đáng tin theo hợp đồng.
3. **REQ-LOG-03:** log vận hành phải tránh chứa trường dữ liệu nhạy cảm không cần thiết và chỉ được người có quyền truy cập.

Đây là **yêu cầu giả định phục vụ học tập**. Không thể suy ra luật hoặc thời hạn lưu dữ liệu thật của sản phẩm từ ba mã này.

### 16.2. Phân tích rủi ro cùng các bên

| Ràng buộc | Điều có thể sai | Người cần tham gia làm rõ | Mức kiểm tra dự kiến |
|---|---|---|---|
| REQ-ACCESS-01 | Người học A đọc/sửa tiến độ của B | PO, Developers, chuyên môn quyền dữ liệu | Quy tắc quyền, API/integration, review |
| REQ-STATE-02 | UI báo lưu thành công giả khi timeout | PO, UI/API Developers, Tester | BDD/ATDD, TDD, contract và E2E chọn lọc |
| REQ-LOG-03 | Log/CI artifact lộ dữ liệu người học | Developers, chuyên môn bảo mật/riêng tư, vận hành | Review schema log, kiểm tra mẫu và quyền |

Nhóm ghi những câu chưa rõ, ví dụ **vai trò hỗ trợ khách hàng có được đọc tiến độ không**. Đây là đầu vào cho discovery có thẩm quyền; không tự bổ sung quyền rộng để “giảm thời gian code”.

### 16.3. Chọn Sprint Goal và lát cắt đầu

**Sprint Goal minh họa:**

> “Người học có thể lưu và tiếp tục bài hợp lệ, nhận trạng thái lưu đúng; thao tác dữ liệu được kiểm soát quyền ở ranh giới API.”

Product Owner sắp backlog theo giá trị và rủi ro; Developers cân nhắc năng lực tích hợp, test và đánh giá bắt buộc. Nhóm chia:

| PBI | Kết quả có thể giao | Kiểm soát liên quan |
|---|---|---|
| **LEARN-201** | Chủ tài khoản lưu và đọc lại tiến độ ở phiên có kết nối | REQ-ACCESS-01, REQ-STATE-02 |
| **LEARN-202** | Từ chối đọc/ghi trái quyền trên API tiến độ | REQ-ACCESS-01 |
| **LEARN-203** | UI phân biệt CONFIRMED/FAILED/UNKNOWN | REQ-STATE-02 |
| **LEARN-204** | Log an toàn và bằng chứng kiểm chứng được truy xuất | REQ-LOG-03 |
| **LEARN-205** | Kiểm tra vận hành và rollout có kiểm soát | Những nghĩa vụ đã xác nhận có liên quan |

Các lát cắt có thể được ghép khác nhau tùy kiến trúc, nhưng **không nên giao tính năng có thể làm lộ dữ liệu khi quyền chưa đạt chuẩn bắt buộc**.

### 16.4. Acceptance examples và kiểm thử

Nhóm làm rõ hành vi:

~~~gherkin
Feature: Bảo vệ dữ liệu và trạng thái lưu tiến độ

  Scenario: Chủ tài khoản đọc lại tiến độ đã xác nhận
    Given người học A đã xác thực hợp lệ
    And tiến độ của bài học thuộc A
    When A yêu cầu lưu tiến độ
    And hệ thống xác nhận đã lưu thành công
    Then A có thể đọc lại tiến độ được phép
    And giao diện thể hiện trạng thái "Đã lưu"

  Scenario: Từ chối tài khoản khác đọc tiến độ
    Given người học A và B là hai tài khoản khác nhau
    And A không có quyền đọc dữ liệu của B
    When A yêu cầu đọc tiến độ thuộc B
    Then API từ chối yêu cầu theo chính sách
    And không trả dữ liệu tiến độ của B

  Scenario: Không khẳng định thành công khi kết quả chưa rõ
    Given người học A đã gửi yêu cầu lưu hợp lệ
    When kết nối ngắt trước khi có xác nhận đáng tin
    Then giao diện không thể hiện "Đã lưu"
    And hiển thị trạng thái chưa xác định theo quy tắc sản phẩm
~~~

**Không tự động suy ra** timeout đồng nghĩa thất bại hoặc thành công. Nếu cơ chế thử lại/đối soát còn chưa rõ, nhóm phải làm rõ trước khi viết test khẳng định một chính sách tùy tiện.

### 16.5. Truy vết từ yêu cầu tới bằng chứng

| Kiểm soát | Evidence cần tạo | Tầng kiểm tra | Link gắn vào đâu? |
|---|---|---|---|
| Chỉ chủ tài khoản đọc tiến độ | Test cho phép đọc của A; test từ chối A đọc B | Unit + API/integration | PBI-201/202, CI build và control record |
| Không báo lưu thành công giả | Test kết quả CONFIRMED/FAILED/UNKNOWN; kịch bản UI | Component/contract + E2E chọn lọc | PBI-203, API contract, CI |
| Không ghi dữ liệu nhạy cảm quá mức | Review fields được log; kiểm tra mẫu log sau thao tác | Review + integration/operational check | PBI-204, kết quả review theo chính sách |
| Đảm bảo trạng thái phát hành | Kiểm tra artifact, các gates và rollout decision | Pipeline + assessment cần thiết | Release manifest |

Nhóm không ghi “100% tuân thủ” chỉ vì có bốn hàng trong bảng. **Độ bao phủ được đánh giá theo nguồn nghĩa vụ, trường hợp rủi ro và phạm vi áp dụng thật**.

### 16.6. CI phát hiện kiểm soát chưa đạt trước merge

Giả sử test cho thấy:

~~~text
Build: learn-progress-ci-0042
Commit: <sha-thực-được-CI-ghi>

unit/save-status-mapper ........ PASS
contract/progress-api-v2 ....... PASS
integration/owner-can-read ..... PASS
integration/other-cannot-read .. FAIL
log-sensitive-field-check ..... NOT RUN (môi trường thiếu)

Kết luận:
  KHÔNG đủ điều kiện coi các kiểm soát bắt buộc đã đạt.
  Không dùng report này làm bằng chứng RELEASE APPROVED.
~~~

Đây là **kết quả minh họa** để phân biệt các trạng thái. Một thất bại quyền truy cập nghiêm trọng cần được **khắc phục, kiểm tra lại và xem xét rủi ro**. Bước NOT RUN không được đổi thành PASS; nếu bắt buộc với Increment/release thì vẫn là khoảng trống.

### 16.7. Xử lý sai lệch theo cách thực nghiệm

Nhóm kiểm tra:

1. **Mô tả lỗi:** A nhận được dữ liệu B qua một nhánh truy vấn API.
2. **Phạm vi:** endpoint, role model, loại dữ liệu và môi trường nào bị ảnh hưởng?
3. **Nguyên nhân có thể:** server dựa vào ID do client gửi thay vì xác minh quyền trên tài nguyên.
4. **Biện pháp:** sửa kiểm tra quyền server, bổ sung test cho nhánh đó.
5. **Kiểm chứng:** chạy lại unit/integration, đánh giá các endpoint cùng cơ chế.
6. **Bằng chứng:** gắn đúng test run sau sửa vào commit/build được phát hành.
7. **Rủi ro vận hành:** nếu có khả năng lỗi đã ở production, kích hoạt đánh giá sự cố theo chính sách.

Không dừng ở việc “đổi response code thành 403”; cần xác minh **thực sự không lộ dữ liệu**, bao gồm những đường truy cập liên quan có rủi ro.

### 16.8. Đánh giá bằng chứng sau khi sửa

Giả sử bản sửa tạo build mới:

| Điều kiện | Build 0042 | Build 0043 |
|---|---|---|
| Unit mapping trạng thái | PASS | PASS |
| API contract | PASS | PASS |
| Đọc đúng chủ thể | PASS | PASS |
| Từ chối truy cập trái quyền | **FAIL** | PASS sau khắc phục |
| Kiểm tra schema log | **NOT RUN** | PASS sau khôi phục môi trường |
| Review rủi ro quyền | Chưa đủ | Đã có kết luận theo giả định bài học |
| Evidence gắn commit/artifact | Thiếu điều kiện | Có link tương ứng |

Những giá trị đều là **ví dụ giả định**, không phải bằng chứng thực. Trong sản phẩm thật cần đối chiếu logs, kết quả và người có thẩm quyền; một bảng tự điền PASS không thay hồ sơ xác minh.

### 16.9. Điều kiện Done và quyết định release

Với giả định các kiểm soát bắt buộc đã được kiểm chứng hợp lệ trên build 0043:

- Các PBI đạt acceptance criteria, được tích hợp và đáp ứng DoD.
- Những evidence links có thể truy xuất theo quyền và đúng phiên bản.
- Các phát hiện chưa giải quyết đã được đánh giá theo thẩm quyền.
- Phạm vi rollout, khả năng giảm tác động và giám sát được xem.
- Quyết định phát hành được ghi **nếu chính sách yêu cầu**, không tự gán một nút CI xanh thành approval.

Nếu một review bắt buộc còn chờ, phải **giữ trạng thái minh bạch và xử lý theo chính sách**. “Chúng ta gần xong” không phải điều kiện tuân thủ.

### 16.10. Quan sát sau release

Các tín hiệu minh họa:

- API denied-access rate theo mẫu phù hợp, không ghi nội dung dữ liệu nhạy cảm.
- Lỗi đọc/ghi tiến độ và timeout.
- Số phát hiện quyền truy cập trái phép đã xác minh.
- Lỗi hồi quy liên quan thay đổi role/permission.
- Số người học bị mất tiến độ và khả năng tiếp tục bài.
- Trạng thái bằng chứng khi dependency hoặc cấu hình production đổi.

**Không lấy tỷ lệ request bị từ chối cao làm bằng chứng chắc chắn có tấn công**; cần phân biệt request không hợp lệ bình thường, cấu hình sai, hành vi người dùng và hoạt động độc hại theo phương pháp an toàn.

### 16.11. Phản hồi trái giả định ban đầu

Giả sử unit và integration tests đều đạt, nhưng người học vẫn báo **“Đã lưu” rồi quay lại không thấy vị trí cũ** trên một thiết bị đặc thù.

Nhóm không nên tuyên bố “đã compliant nên phản hồi người dùng sai”. Họ cần:

1. Thu thập tình huống và dữ liệu an toàn.
2. Kiểm tra hiệu lực của bằng chứng trước đây: test đã bao phủ điều kiện thiết bị/mạng đó chưa?
3. Xác định nghĩa vụ/acceptance criteria nào bị ảnh hưởng.
4. Bổ sung kiểm tra ở tầng phù hợp (component, integration, E2E hoặc đánh giá môi trường).
5. Điều chỉnh Product Backlog và kế hoạch, giữ DoD.
6. Theo dõi sau khi sửa và cập nhật truy vết.

**Bằng chứng có giới hạn** phải được nhìn trong bối cảnh sản phẩm thật; nó không thay cho cải tiến liên tục.

### 16.12. Những bài học của case study

1. Làm rõ nghĩa vụ và tiêu chí **trước implementation**, không phải ngày phát hành.
2. Kiểm chứng quyền **cả đường được phép và trái quyền**.
3. Dùng test ở nhiều mức cho đúng rủi ro, không dồn mọi thứ vào E2E.
4. **NOT RUN và FAIL không phải PASS**, dù có áp lực thời gian.
5. Bằng chứng cần gắn đúng **build, môi trường và phạm vi**.
6. DoD bảo vệ Increment; điều kiện release/approval phụ thuộc chính sách thật.
7. Các phát hiện sau release là đầu vào cho **kiểm chứng lại và Product Backlog**, không phải lý do đổ lỗi cá nhân.

## 17. Đo hiệu quả quản trị và kiểm chứng mà không chơi trò điểm số

### 17.1. Các tín hiệu nên nhìn cùng nhau

| Nhóm | Tín hiệu | Câu hỏi | Bẫy khi dùng làm KPI |
|---|---|---|---|
| **Phát hiện sớm** | Tỷ lệ lỗi kiểm soát được phát hiện trước merge/release theo rủi ro | Có giảm lỗi phát hiện muộn không? | Đếm nhiều test FAIL là “đội kém” dù phát hiện sớm |
| **Dòng công việc** | Work item age ở bước review, WIP, cycle time, throughput | Bằng chứng/phê duyệt tắc ở đâu? | Tối ưu số lượng ticket bằng cách chia giả |
| **Độ tin cậy evidence** | Kết quả thiếu build ID, sai version, artifact không truy xuất | Bằng chứng có dùng được lúc cần không? | Tăng số file/report mà không cải thiện khả năng chứng minh |
| **Chất lượng kiểm thử** | Test flaky, test bị bỏ qua, thời gian phản hồi CI | Phản hồi kỹ thuật có đủ tin cậy không? | Xóa tests để pipeline luôn xanh |
| **Rủi ro tồn dư** | Phát hiện chưa giải quyết, ngoại lệ hết hạn, phạm vi chưa đánh giá | Có nguy cơ đang bị che không? | Đặt mục tiêu số ngoại lệ bằng 0 bằng cách không ghi |
| **Vận hành** | Sự cố quyền/dữ liệu đã xác minh, thời gian phát hiện/khôi phục | Kiểm soát tiếp tục hiệu quả sau release không? | Dùng log thô để suy kết quả pháp lý |
| **Outcome sản phẩm** | Lỗi mất tiến độ, tỷ lệ học tiếp, hoàn thành bài | Đội vẫn tạo giá trị cho người học không? | Coi compliance check là thước đo duy nhất |
| **Nhịp bền vững** | Thời gian chờ chuyên môn, quá tải review, làm thêm giờ | Cách tích hợp kiểm soát có duy trì được không? | Ép người duyệt ngoài giờ |

Một hệ thống có thể **tạo nhiều evidence hơn nhưng chất lượng thấp hơn**. Vì vậy, nên nhìn **tính phù hợp và khả năng đối chiếu**, không chỉ số lượng.

### 17.2. Ví dụ số liệu trước–sau

Tất cả số liệu sau **hoàn toàn minh họa**, với điều kiện loại việc và mẫu số được ghi nhất quán:

| Chỉ báo | Giai đoạn A | Giai đoạn B | Diễn giải thận trọng |
|---|---:|---:|---|
| PBI có kiểm soát được làm rõ trước khi code | 8/20 | 16/20 | Có dấu hiệu discovery sớm hơn |
| Phát hiện kiểm soát đến cuối giai đoạn mới được chú ý | 6 | 2 | Cần xem mức độ nghiêm trọng và cách ghi |
| Kết quả kiểm tra không gắn build ID | 12 | 1 | Khả năng truy xuất có thể tốt hơn |
| Trung vị thời gian chờ review kiểm soát | 4 ngày | 2 ngày | Không được rút ngắn bằng bỏ review bắt buộc |
| PBI hoàn thành đạt DoD | 13 | 15 | Cần xem loại PBI, độ phức tạp và lượng việc |
| Sự cố dữ liệu người học đã xác minh | Chưa đủ dữ liệu | Chưa đủ dữ liệu | Không kết luận tác động tới production |

Không thể khẳng định một điều chỉnh pipeline **gây ra** mọi thay đổi chỉ từ hai giai đoạn. Cần xem cỡ mẫu, scope, mùa vụ, chính sách và thay đổi đồng thời.

### 17.3. Từ sự kiện tới thử nghiệm cải tiến

~~~yaml
# Ví dụ thử nghiệm cải tiến trong Retrospective.
experiment_id: IMPROVE-EVIDENCE-01
problem: "Đến cuối Sprint mới phát hiện thiếu evidence gắn build"
observations:
  - "Nhiều test reports được chụp ảnh mà không ghi build ID"
  - "Security reviewer phải hỏi lại phạm vi/version"
hypothesis: >
  Nếu CI tự gắn commit/build vào test report và PBI liên kết control,
  thì thời gian chờ đối chiếu và tỷ lệ evidence không dùng được sẽ giảm.
scope: "Các PBI thay đổi API tiến độ trong hai Sprint"
actions:
  - "Dùng ID requirement/control trong PBI"
  - "CI ghi build metadata vào kết quả test liên quan"
  - "Handoff review liệt kê phạm vi và điều chưa đạt"
signals:
  - "Số báo cáo thiếu metadata cần thiết"
  - "Work item age khi chờ review"
  - "Số lần làm lại evidence vì sai version"
guardrails:
  - "Không bỏ kiểm tra chất lượng bắt buộc"
  - "Không đưa dữ liệu nhạy cảm vào reports"
  - "Không làm tăng tải review ngoài giờ bất hợp lý"
review_point: "Retrospective sau hai Sprint thử nghiệm"
decision_options: ["Giữ", "Sửa", "Dừng"]
~~~

### 17.4. Những chỉ số không nên coi là đích tự thân

Không nên đặt mục tiêu kiểu:

- “Mỗi Developer phải tạo 20 bằng chứng/ngày.”
- “Mọi PBI có ít nhất năm screenshot kiểm tra.”
- “Số phát hiện compliance phải bằng 0 kể cả khi phát hiện lỗi sớm.”
- “Không được ghi ngoại lệ để dashboard luôn xanh.”
- “Thời gian phê duyệt phải bằng 0, dù thiếu reviewer chuyên môn.”

Những con số này có thể khuyến khích **hành vi làm đẹp hồ sơ**, làm giảm khả năng minh bạch. Mục tiêu thật là **kiểm soát hiệu quả, bằng chứng đáng tin, flow hợp lý và giá trị người dùng**.

## 18. Những ngộ nhận và phản mẫu cần tránh

| Ngộ nhận / phản mẫu | Vì sao nguy hiểm? | Cách tiếp cận phù hợp |
|---|---|---|
| “Agile thì không cần tuân thủ.” | Nhầm thích ứng với miễn trừ nghĩa vụ | Làm rõ ràng buộc và tích hợp vào cách giao Increment |
| “Compliance chỉ cần xem trước ngày release.” | Phát hiện muộn, tạo hàng chờ và làm lại nhiều phần | Khám phá và kiểm chứng sớm theo rủi ro |
| “Một người ghi ‘approved’ trong chat là đủ.” | Không rõ thẩm quyền, phạm vi và bằng chứng | Quyết định theo chính sách, có nguồn và dấu vết |
| “Có quy định thì Developer tự diễn giải cho nhanh.” | Có thể áp sai phạm vi hoặc đưa chính sách giả vào code | Hỏi người có chuyên môn/thẩm quyền khi yêu cầu chưa rõ |
| “Mọi control đều bắt buộc với mọi PBI.” | Tạo quá tải, đánh đồng thay đổi ít và nhiều rủi ro | Xác minh applicability và chính sách theo loại thay đổi |
| “Đã pass unit tests nên kiểm soát quyền đạt.” | Mock không chứng minh ranh giới API/DB thật | Kiểm tra ở mức đủ bảo đảm, bổ sung integration/security |
| “CI xanh nghĩa là tuân thủ toàn bộ.” | Có thể không chạy kiểm tra bắt buộc hoặc không bao phủ phạm vi | Kiểm chứng evidence, DoD và điều kiện release |
| “Screenshot màu xanh là bằng chứng đầy đủ.” | Thiếu build/version, phạm vi, nguồn gốc | Gắn artifact, commit, tiêu chí, môi trường và kết quả |
| “PASS ở build cũ dùng cho release mới cũng được.” | Sai đối tượng kiểm chứng | Đối chiếu artifact được phát hành với bằng chứng |
| “NOT RUN nghĩa là không có lỗi.” | Không biết kết quả nên không thể kết luận | Phân biệt NOT RUN/BLOCKED/FAIL/PASS |
| “Không có bug được báo nghĩa là bảo mật tốt.” | Thiếu tín hiệu không chứng minh không có lỗ hổng | Kiểm tra theo threat/risk, quan sát và review |
| “Dùng tool quét là không cần chuyên gia.” | Tự động hóa có blind spots và false positives | Kết hợp kỹ thuật, ngữ cảnh và đánh giá chuyên môn |
| “Dùng chuyên gia review là khỏi cần test.” | Một lần review không thay kiểm tra hành vi code | Có bằng chứng kỹ thuật đúng rủi ro |
| “Bằng chứng càng nhiều file càng đáng tin.” | Nhiều bản sao, sai version, khó truy xuất | Chọn bằng chứng liên quan, đúng nguồn và có vòng đời |
| “Evidence nên chứa toàn bộ dữ liệu thật để dễ đối chiếu.” | Lộ dữ liệu cá nhân, bí mật, quyền truy cập | Dùng dữ liệu thử và tối thiểu hóa thông tin nhạy cảm |
| “Có ngoại lệ thì xem như đã PASS.” | Che rủi ro còn tồn tại | Ghi rủi ro/điều kiện/thời hạn; không sửa trạng thái kiểm tra |
| “Mọi nghĩa vụ đều có thể xin miễn trừ.” | Có nghĩa vụ không cho waiver | Xác minh quyền miễn trừ; nếu không hợp lệ phải đáp ứng hoặc dừng phạm vi |
| “Product Owner có thể ký bỏ kiểm soát bảo mật.” | Nhầm PO accountability với phê duyệt chuyên môn/tổ chức | Theo thẩm quyền thật, giữ Scrum accountability |
| “Scrum Master là người phê duyệt compliance.” | Không đúng bản chất accountability Scrum | Scrum Master hỗ trợ hiệu quả và tháo gỡ trở ngại |
| “Sửa lỗi gấp nên không cần DoD.” | Đẩy lỗi nguy hiểm tới người dùng | Ứng cứu đúng quy trình, bảo vệ chất lượng bắt buộc |
| “Bước review chậm vì reviewer không chăm.” | Bỏ qua đầu vào thiếu, WIP, phụ thuộc, múi giờ | Xem flow và nguyên nhân hệ thống |
| “Càng nhiều approval thì càng an toàn.” | Dễ tạo phê duyệt hình thức không có bằng chứng | Review theo rủi ro và thẩm quyền cần thiết |
| “Risk score cao nhất luôn làm trước, không cần xem ràng buộc.” | Có thể lùi nghĩa vụ bắt buộc | Kết hợp ưu tiên giá trị với phạm vi và nghĩa vụ không thể bỏ |
| “Đã có chứng nhận của vendor nên mình tự động compliant.” | Chứng nhận có phạm vi và trách nhiệm chia sẻ | Xác minh dịch vụ, cấu hình và nghĩa vụ của chính mình |
| “Release đã được duyệt nên mãi mãi đạt.” | Cấu hình, dependency, luật/chính sách thay đổi | Xác định trigger kiểm tra lại và hiệu lực evidence |
| “Đạt compliance đồng nghĩa Product Goal đạt.” | Có kiểm soát nhưng người dùng vẫn có thể không đạt giá trị | Theo dõi outcome và phản hồi sau release |
| “Mỗi Sprint phải tăng số kiểm tra và screenshot.” | Metric gaming, chi phí duy trì cao | Đo mức bao phủ rủi ro và tính tin cậy, không chỉ số lượng |
| “Việc compliance là của một phòng ban, không liên quan Developers.” | Kiểm soát đến sau implementation, khó sửa | Cộng tác sớm, nhưng giữ thẩm quyền đánh giá cần thiết |
| “Log lỗi càng chi tiết càng tốt.” | Có thể lộ dữ liệu nhạy cảm trong CI/monitoring | Thiết kế log theo mục đích, quyền và tối thiểu dữ liệu |
| “Bằng chứng lưu trên máy tôi là đủ.” | Không có truy xuất, backup, quyền và dấu vết phù hợp | Lưu theo chính sách, liên kết và quản lý vòng đời |

## 19. Checklist tích hợp tuân thủ vào dòng công việc

### 19.1. Trước khi chọn PBI

1. **Nguồn:** yêu cầu xuất phát từ luật, hợp đồng, chính sách hay quyết định kỹ thuật nào?
2. **Hiệu lực:** nguồn có đúng phiên bản và thời điểm áp dụng không?
3. **Phạm vi:** dữ liệu, chức năng, role và môi trường nào chịu ảnh hưởng?
4. **Thẩm quyền:** ai có quyền diễn giải và xác nhận điều chưa rõ?
5. **Rủi ro:** điều gì có thể gây hại nếu kiểm soát thiếu hoặc sai?
6. **Mục tiêu:** hạng mục liên hệ Product Goal và giá trị như thế nào?
7. **Truy vết:** có ID requirement/control và nguồn tham chiếu rõ không?
8. **Tính khẩn:** có thời hạn hay nghĩa vụ không thể trì hoãn được xác nhận không?

### 19.2. Khi làm rõ và thiết kế

9. **Ví dụ:** có trường hợp được phép, bị từ chối và lỗi quan trọng không?
10. **Trường hợp biên:** role đặc biệt, timeout, trạng thái chưa rõ có được quyết định?
11. **Thiết kế kiểm soát:** cơ chế phòng ngừa/phát hiện/giảm tác động phù hợp rủi ro chưa?
12. **Dữ liệu:** có giảm tối thiểu dữ liệu sử dụng và trong test/log không?
13. **Đầu ra kiểm chứng:** bằng chứng gì cần có, ở mức test nào?
14. **Review:** cần chuyên gia/đánh giá độc lập hay gate nào theo chính sách?
15. **DoD:** tiêu chí chất lượng chung có bao gồm ràng buộc liên quan không?
16. **Cắt nhỏ:** có thể giao Increment nhỏ có kiểm chứng thay vì một epic mơ hồ không?

### 19.3. Khi hiện thực và tích hợp

17. **Code/review:** thay đổi nhạy cảm có được xem xét với ngữ cảnh và quyền phù hợp?
18. **Test:** unit/component/contract/integration/E2E có bảo vệ đúng rủi ro?
19. **CI:** kiểm tra bắt buộc chạy sớm, kết quả có đáng tin và gắn commit?
20. **Bằng chứng:** có build, version, môi trường, phạm vi, thời gian và nguồn tạo?
21. **Thất bại:** có phân biệt PASS/FAIL/NOT RUN/BLOCKED không?
22. **Dữ liệu thử:** môi trường, tài khoản và log có được kiểm soát quyền?
23. **Blocker:** việc chờ quyết định/review có hiển thị tuổi công việc và người hỗ trợ?
24. **Truy vết ngược:** thay đổi code có đánh giá tác động tới control liên quan không?

### 19.4. Trước và sau phát hành

25. **Increment:** PBI đã đáp ứng Definition of Done hay chỉ xong code?
26. **Artifact:** evidence có đại diện cho build/cấu hình sẽ phát hành không?
27. **Phê duyệt:** nếu có gate theo quy định, người có thẩm quyền đã đánh giá phạm vi rõ chưa?
28. **Ngoại lệ:** có được xử lý theo thẩm quyền, thời hạn và phạm vi? Có nghĩa vụ không cho miễn trừ?
29. **Rollback/khôi phục:** dữ liệu và triển khai có kế hoạch giảm tác động phù hợp?
30. **Quan sát:** kiểm soát và lỗi quan trọng được theo dõi thế nào sau release?
31. **Đổi trạng thái:** chính sách, role, API hoặc vendor thay đổi có kích hoạt review lại?
32. **Lưu trữ:** bằng chứng được giữ, truy cập và loại bỏ theo chính sách thật?
33. **Outcome:** người dùng có thực sự nhận được giá trị và tránh rủi ro mong muốn?
34. **Cải tiến:** Retro có xem thời gian chờ, evidence lỗi và cơ chế gây phát hiện muộn?

Checklist phục vụ **đánh giá theo rủi ro**, không phải giấy phép biến mỗi PBI thành 34 thủ tục ký duyệt. Các tiêu chí áp dụng cụ thể phải được đội và người có thẩm quyền xác nhận.

## 20. Bài tập vận dụng

### Bài tập 1 — Phân loại các khái niệm

Hãy xác định mỗi phát biểu thuộc **nghĩa vụ, rủi ro, kiểm soát, acceptance criterion, bằng chứng, DoD hay release decision**:

1. “Người không có quyền không được đọc tiến độ người khác.”
2. “API xác minh danh tính và quyền trên tài nguyên trước khi trả dữ liệu.”
3. “Lộ tiến độ của người học do truy cập trái quyền.”
4. “Test integration trên build 2043 chứng minh request A đọc B bị từ chối.”
5. “Increment đã tích hợp và đạt những tiêu chuẩn chất lượng chung.”
6. “Người có thẩm quyền quyết định bật tính năng sau khi xem hồ sơ kiểm soát.”

**Gợi ý:** câu (1) có thể là yêu cầu/tiêu chí tùy cách ghi và nguồn; (2) là kiểm soát; (3) là rủi ro; (4) là mô tả bằng chứng; (5) là tiêu chuẩn DoD khi được áp dụng; (6) là quyết định release. Hãy nêu **điều kiện còn thiếu** để mô tả đủ chặt.

### Bài tập 2 — Từ chính sách đến acceptance examples

Chính sách giả định: “Một người học chỉ được cập nhật tiến độ của tài khoản mình, trừ trường hợp quyền khác được xác nhận.”

**Yêu cầu:**

1. Viết requirement ID và nêu nguồn cần xác minh.
2. Nêu rủi ro chính và kiểm soát ở server.
3. Viết ba acceptance examples: được phép, trái quyền và phiên không hợp lệ.
4. Chọn một unit test và một API integration test.
5. Mô tả bằng chứng phải lưu cho build được phát hành.
6. Nêu câu hỏi về vai trò hỗ trợ chưa thể tự quyết.

### Bài tập 3 — Đọc ma trận truy vết

Một PBI có:

~~~text
REQ-ACCESS-01 -> PBI-42 -> PR-42 -> unit test: PASS
API integration test: NOT RUN
Release build: B-005, commit khác PR-42
Security review: "looks good" trong chat
~~~

**Yêu cầu:**

1. Chỉ ra ít nhất bốn khoảng trống.
2. Nêu vì sao unit test PASS chưa chứng minh kiểm soát.
3. Viết cách cập nhật trạng thái theo đúng tính chất evidence.
4. Đề xuất bước kiểm chứng tiếp theo và ai cần xác nhận.
5. Giải thích vì sao không nên chụp lại screenshot cũ để “điền đủ ô”.

### Bài tập 4 — Kiểm tra thuộc tính của bằng chứng

Nhóm có ba artifact:

- A: Screenshot CI xanh, không có commit hoặc đường link.
- B: Kết quả test API gắn build/commit, có môi trường và ca trái quyền, nhưng log chứa token thật.
- C: Báo cáo review quyền có phạm vi và kết luận, nhưng API đã đổi role mapping sau đó.

Hãy đánh giá theo **tính liên quan, nguồn gốc, phiên bản, toàn vẹn, bảo mật và hiệu lực**, rồi đề xuất hành động sửa. Không gọi artifact nào “đủ” chỉ vì nhìn chuyên nghiệp.

### Bài tập 5 — Thiết kế pipeline kiểm chứng có rủi ro

Một đội chuẩn bị thay đổi:

- Sửa văn bản hướng dẫn trên trang.
- Đổi API đọc dữ liệu tiến độ.
- Sửa cấu hình quyền của dịch vụ.

**Yêu cầu:** thiết kế các checks tại local, PR, mainline, trước release và sau release. Giải thích vì sao ba thay đổi không cần **cùng độ sâu kiểm tra**, nhưng vẫn phải giữ DoD và các nghĩa vụ bắt buộc. Chỉ ra kiểm tra nào không thể thay bằng một static analyzer.

### Bài tập 6 — Scrum và một nghĩa vụ xuất hiện giữa Sprint

Sprint Goal là “Người học lưu và tiếp tục bài đáng tin”. Giữa Sprint, chuyên gia kiểm soát xác nhận rằng API đang thiếu kiểm tra quyền bắt buộc.

**Yêu cầu:**

1. Product Owner, Developers và Scrum Master nên phối hợp ra sao?
2. Nhóm cần làm gì với Sprint Backlog và phạm vi?
3. Vì sao không được đánh dấu PBI Done khi kiểm soát bắt buộc chưa đạt?
4. Khi nào chỉ Product Owner có thể hủy Sprint?
5. Nêu một cách chia lát cắt để vẫn giữ giá trị và chất lượng.

### Bài tập 7 — Quản lý ngoại lệ đúng thẩm quyền

Một bài kiểm tra log bắt buộc không chạy do môi trường thử ngừng hoạt động. Người quản lý dự án nói “đánh dấu PASS để không trễ release”.

**Yêu cầu:**

- Ghi trạng thái thực của test.
- Nêu mức rủi ro và điều chưa biết.
- Phân biệt remediation, compensating control và waiver.
- Đề xuất cách hạn chế tác động trong khi chờ kiểm chứng.
- Chỉ ra ai cần xác nhận nếu tổ chức có quy trình ngoại lệ, và khi nào ngoại lệ không hợp lệ.

**Gợi ý:** không đổi **NOT RUN → PASS**. Một ngoại lệ hợp lệ, nếu cho phép, vẫn không biến kiểm tra chưa chạy thành kết quả đạt.

### Bài tập 8 — Thiết kế Definition of Workflow cho kiểm chứng

Một nhóm Kanban có nhiều PBI đợi review kiểm soát ở cuối Sprint. Hãy thiết kế workflow:

~~~text
Các trạng thái chính:
Điều kiện kéo việc:
Mốc tính WIP:
Mốc tính cycle time:
Khi nào cần báo Blocked:
Thông tin cần gửi người review:
Chính sách kiểm tra theo mức rủi ro:
Ngoại lệ/sự cố khẩn:
Tiêu chuẩn chuyển sang Done:
Tín hiệu work item age và throughput:
Điểm cải tiến trong Retrospective:
~~~

Đề xuất một WIP limit để thử, nhưng phải **giải thích cách xem lại** thay vì gọi nó là số chuẩn phổ quát.

### Bài tập 9 — Nhà cung cấp có chứng nhận

Nền tảng học dùng dịch vụ định danh bên ngoài. Nhà cung cấp quảng bá một chứng nhận bảo mật. Đội định xem như chức năng đăng nhập của mình đã đáp ứng mọi nghĩa vụ.

**Yêu cầu:**

1. Nêu ít nhất bốn câu hỏi về **phạm vi và trách nhiệm chia sẻ**.
2. Chỉ ra kiểm soát mà đội vẫn có thể phải tự thực hiện, như mapping quyền với tiến độ.
3. Đề xuất evidence cho cấu hình tích hợp.
4. Nêu trigger kiểm chứng lại khi nhà cung cấp hoặc hợp đồng đổi.
5. Giải thích tại sao chứng nhận của vendor không đồng nghĩa compliance end-to-end.

### Bài tập 10 — Ghi release manifest đúng

Tạo manifest phát hành mô tả:

~~~text
Release ID:
Artifact và commit:
Những PBI/controls liên quan:
Acceptance tests và kết quả:
Integration/security reviews và kết quả:
Evidence links với nguồn/phiên bản:
Các kiểm tra NOT RUN/FAIL:
Rủi ro tồn dư và ngoại lệ (nếu hợp lệ):
Người/phạm vi có thẩm quyền quyết định:
Điều kiện rollout/rollback:
Monitoring sau release:
Tình trạng quyết định hiện tại:
~~~

**Yêu cầu quan trọng:** nếu một kiểm tra bắt buộc còn thiếu, giữ trạng thái thích hợp và **không tự viết APPROVED**.

### Bài tập 11 — Phân tích số liệu và metric gaming

Hai Sprint có dữ liệu giả định:

| Tín hiệu | Sprint A | Sprint B |
|---|---:|---:|
| PBI bắt đầu | 20 | 20 |
| PBI có control được làm rõ trước code | 8 | 16 |
| Kết quả test thiếu build ID | 12 | 1 |
| Thời gian chờ security review trung vị | 4 ngày | 2 ngày |
| Lỗi sản phẩm sau release | Chưa đủ dữ liệu | Chưa đủ dữ liệu |

**Yêu cầu:** nêu hai tín hiệu cải thiện, ba yếu tố có thể gây nhiễu, một guardrail để không bỏ kiểm tra chỉ vì muốn review nhanh, và lý do chưa thể kết luận sản phẩm an toàn hơn.

### Bài tập 12 — Lập thử nghiệm cải tiến cho đội của bạn

Chọn một dòng công việc thật hoặc giả định nơi bằng chứng tuân thủ hay bị làm lại ở cuối Sprint.

~~~text
Product Goal và phạm vi kiểm soát:
Yêu cầu / nguồn nghĩa vụ đã xác nhận:
Tình trạng hiện tại và bằng chứng:
Rủi ro nếu không hành động:
Điểm nghẽn trong workflow:
Giả thuyết nguyên nhân:
Thử nghiệm cải tiến nhỏ:
Người thực hiện và chức năng cần tham vấn:
Thay đổi trong backlog/DoD/CI:
Thông tin evidence cần tự động ghi:
Chính sách bảo mật và quyền truy cập artifact:
Tín hiệu flow và độ tin cậy:
Guardrails về chất lượng và outcome:
Mốc xem lại:
Điều kiện giữ, sửa hoặc dừng:
~~~

**Tự đánh giá:** bạn có thể chọn một requirement, chỉ ra **kiểm soát cụ thể nào giảm rủi ro đó**, bằng chứng đúng **build và phạm vi** nào chứng minh điều kiện đã đạt, và **còn giới hạn gì** cần báo trước release hay không?

## 21. Tổng kết

Tích hợp tuân thủ và bằng chứng vào dòng công việc giúp Agile **thích ứng mà không đánh đổi trách nhiệm**. Những nguyên tắc quan trọng:

1. **Xác nhận nguồn và phạm vi nghĩa vụ trước khi thiết kế:** luật, hợp đồng, chính sách và tiêu chuẩn không mặc định áp dụng như nhau với mọi sản phẩm.
2. **Chuyển nghĩa vụ thành hành vi/kiểm soát có thể kiểm chứng:** có requirement ID, rủi ro, acceptance examples, kiểm soát và kết quả mong đợi.
3. **Truy vết hai chiều:** từ nguồn tới Product Backlog, code, test, evidence, release — và từ thay đổi trở lại những nghĩa vụ bị ảnh hưởng.
4. **Tạo bằng chứng khi kiểm tra diễn ra:** gắn commit, build, môi trường, thời điểm, phương pháp, kết quả, phạm vi và review cần thiết; bảo vệ toàn vẹn, quyền truy cập và vòng đời.
5. **Bằng chứng phải đủ đúng rủi ro:** unit tests, contract/integration, E2E, đánh giá chuyên môn và monitoring bổ trợ; không có một badge tự động chứng minh mọi nghĩa vụ.
6. **Giữ Definition of Done và điều kiện release rõ:** test xanh không đồng nghĩa DoD hoặc approval; release phải dựa trên bằng chứng phù hợp với artifact và thẩm quyền thật.
7. **Phân biệt PASS, FAIL, NOT RUN, BLOCKED và ngoại lệ:** waiver không biến FAIL thành PASS và có nghĩa vụ không thể miễn trừ.
8. **Dùng Scrum/Kanban/XP để nhận phản hồi sớm:** refinement làm rõ yêu cầu, CI tạo evidence, WIP/work item age phơi bày hàng chờ, engineering practices giữ thay đổi an toàn.
9. **Không để quản trị thành nghi thức hình thức:** tự động hóa phần lặp phù hợp, review theo rủi ro, giảm copy giấy tờ, không lấy số screenshot làm KPI.
10. **Tiếp tục kiểm tra sau phát hành:** cấu hình, role, dependency, chính sách và hành vi người dùng có thể làm bằng chứng cũ không còn hiệu lực; cần cập nhật kiểm soát và backlog theo phản hồi.

> **Câu hỏi ghi nhớ:** “Đối với một thay đổi cụ thể, chúng ta có chỉ ra được **yêu cầu nào thật sự áp dụng, kiểm soát gì đã được triển khai, bằng chứng nào đúng phiên bản chứng minh nó đạt, ai có quyền kết luận, và điều kiện nào buộc kiểm chứng lại** không?”

### Tài liệu tham khảo

- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Product Goal, Product Backlog, Sprint Goal, Increment, Definition of Done và trách nhiệm Scrum Team.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 Principles](https://agilemanifesto.org/principles.html) — hợp tác với khách hàng, giao phần mềm giá trị và chú trọng sự xuất sắc kỹ thuật.
- [The Kanban Guide](https://kanbanguides.org/) — Definition of Workflow, WIP, work item age, throughput và cycle time.
- [NIST Secure Software Development Framework (SSDF)](https://csrc.nist.gov/projects/ssdf) — tham khảo về tổ chức các thực hành phát triển phần mềm an toàn và bảo đảm kiểm chứng.
- [OWASP Application Security Verification Standard (ASVS)](https://owasp.org/www-project-application-security-verification-standard/) — nguồn tham khảo về yêu cầu kiểm chứng an toàn ứng dụng, cần chọn phạm vi và phiên bản phù hợp.
- [OWASP Software Assurance Maturity Model (SAMM)](https://owaspsamm.org/) — tham khảo cách cải thiện thực hành bảo đảm phần mềm ở cấp tổ chức.
- [W3C Web Content Accessibility Guidelines (WCAG)](https://www.w3.org/WAI/standards-guidelines/wcag/) — nguồn tham khảo khả năng tiếp cận; yêu cầu áp dụng và phiên bản cần được xác nhận.
- [Martin Fowler — Continuous Integration](https://martinfowler.com/articles/continuousIntegration.html) — phản hồi tích hợp sớm và khả năng khôi phục build đáng tin.
- [Agile Alliance — Extreme Programming](https://agilealliance.org/glossary/xp/) — TDD, CI, refactoring và phát hành nhỏ giúp phản hồi sớm.
