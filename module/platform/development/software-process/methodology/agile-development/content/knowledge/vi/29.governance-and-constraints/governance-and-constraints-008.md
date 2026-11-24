# Phối hợp với nhà cung cấp có nhịp phát triển khác

## 1. Khi nhóm Agile chạy nhanh hơn nhịp của nhà cung cấp

Một nhóm phát triển nền tảng học trực tuyến có thể lập kế hoạch trong Sprint hai tuần, tích hợp mã mỗi ngày và giao các phần tăng trưởng nhỏ. Tuy nhiên, sản phẩm của họ còn cần sử dụng một dịch vụ xác thực bên ngoài chỉ phát hành tính năng mới theo quý, một dịch vụ gửi thông báo có quy trình thay đổi cấu hình vài ngày, hoặc một đối tác triển khai hệ thống nghiệp vụ chỉ cho kiểm thử tích hợp theo lịch hẹn.

Giả sử Product Goal hiện tại là:

> Học viên tự đăng ký một khóa học miễn phí còn chỗ, biết được trạng thái chính xác và không cần nhờ nhân viên xử lý những trường hợp thông thường.

Nhóm có thể hoàn thành giao diện, xử lý sức chứa, kiểm thử luồng đăng ký và chuẩn bị triển khai. Nhưng nếu nhà cung cấp định danh chưa xác nhận hợp đồng token mới hoặc môi trường thử nghiệm của đối tác chưa sẵn sàng, **kết quả người dùng vẫn có thể bị chặn** dù các hạng mục nội bộ đã tiến triển tốt.

Vấn đề không nhất thiết là nhà cung cấp “không Agile”. Một dịch vụ có nhiều khách hàng, hợp đồng vận hành, yêu cầu pháp lý, lịch kiểm thử hệ thống hoặc chính sách duyệt thay đổi có thể **có lý do hợp lệ để tổ chức nhịp khác**. Ngược lại, không phải mọi rào cản do đối tác nêu đều bất biến; có những hàng đợi do giao tiếp, hợp đồng mơ hồ hoặc lựa chọn kiến trúc tạo ra.

**Phối hợp với nhà cung cấp có nhịp phát triển khác** là năng lực xác định ranh giới trách nhiệm, hợp đồng, điều kiện kiểm chứng, mức bất định và phương án tích hợp để nhóm sản phẩm **vẫn giao giá trị tăng dần và nhận phản hồi sớm** khi một phần năng lực cần thiết đến từ đối tác ngoài quyền điều hành trực tiếp.

Trong module **AGILE_DEVELOPMENT**, chủ đề này nối liền:

- **Giá trị và nguyên tắc Agile:** cộng tác, phần mềm hoạt động được, thích ứng trước thay đổi, phản hồi sớm.
- **User story, backlog và ưu tiên:** chia lát cắt giá trị dựa trên kết quả có thể bàn giao, không dựa hoàn toàn vào lịch vendor.
- **Scrum:** Product Goal, Sprint Goal, Increment và Definition of Done không tự mất ý nghĩa vì có đối tác.
- **Kanban:** hiển thị thời gian chờ, work item age, WIP và chính sách xử lý phụ thuộc.
- **XP/CI:** hợp đồng API, kiểm thử tự động, tích hợp thường xuyên, giảm rủi ro sửa đổi muộn.
- **Quản trị và ràng buộc:** hợp đồng, quyền quyết định, chất lượng, bảo mật, chi phí, hỗ trợ và nghĩa vụ thông báo.

> **Luận điểm chính:** Không cần ép mọi nhà cung cấp chạy cùng Sprint. Cần thiết kế **điểm giao tiếp rõ, tích hợp có kiểm chứng, dự báo có điều kiện và phương án thích ứng** để nhịp bên ngoài không biến mọi thay đổi thành một đợt giao lớn, khó đảo ngược.

### 1.1. Kết quả học tập

Sau bài, người học có thể:

1. Phân loại các kiểu nhịp phát triển, phát hành, hỗ trợ và phê duyệt của nhà cung cấp.
2. Lập bản đồ phụ thuộc và xác định **đầu ra thật sự cần, ai có quyền quyết, khi nào cần biết và kiểm chứng ra sao**.
3. Đặt ranh giới hợp đồng và chất lượng, tránh nhầm **nhà cung cấp đã giao** với **Increment của sản phẩm đã Done**.
4. Chia công việc, thiết kế hợp đồng và môi trường thử để hai bên có thể tiến triển **không đồng bộ nhưng tương thích**.
5. Phối hợp release, thay đổi schema/API, lịch đóng băng, ứng cứu sự cố và bảo mật.
6. Dùng dữ liệu flow và outcome để xem biện pháp phối hợp có cải thiện thật hay không.
7. Nhận ra khi nào nên **điều chỉnh phạm vi, thay đổi cách tích hợp, thương lượng điều kiện hoặc quyết định thay nhà cung cấp**.

## 2. “Nhịp phát triển khác” thực sự gồm những nhịp nào?

### 2.1. Không chỉ là Sprint hai tuần so với release theo quý

| Loại nhịp | Ví dụ minh họa | Tác động có thể có |
| --- | --- | --- |
| **Nhịp khám phá/yêu cầu** | Nhà cung cấp chỉ nhận yêu cầu tính năng mới vào đầu mỗi tháng. | Thời điểm chốt nhu cầu không khớp lúc nhóm học được thông tin mới. |
| **Nhịp lập kế hoạch/công suất** | Đối tác phân bổ kỹ sư theo dự án cố định, thay đổi phải đặt trước. | Một yêu cầu nhỏ vẫn có thể chờ hàng đợi ưu tiên. |
| **Nhịp phát triển** | Vendor dùng chu kỳ giai đoạn phân tích → triển khai → kiểm thử dài. | Khó có bản tích hợp sớm nếu không chia được đầu ra. |
| **Nhịp phát hành** | Provider công bố API mới theo phiên bản định kỳ. | Consumer phải hỗ trợ phiên bản hiện hành lâu hơn. |
| **Nhịp triển khai production** | Có cửa sổ bảo trì hoặc change advisory board. | Deploy của nhóm sản phẩm và deploy vendor có thể không trùng. |
| **Nhịp môi trường thử nghiệm** | Chỉ có sandbox dùng được trong một khoảng thời gian đã đặt lịch. | Kiểm thử liên hệ thống dễ bị dồn tới cuối. |
| **Nhịp đánh giá an toàn/pháp lý** | Thay đổi dữ liệu phải qua đánh giá và phê duyệt riêng. | Không thể coi phê duyệt là một task kỹ thuật có thể bỏ. |
| **Nhịp hỗ trợ và khắc phục lỗi** | Support giờ hành chính; sự cố nghiêm trọng có kênh ứng cứu khác. | Thời gian phát hiện và khôi phục phụ thuộc đúng tuyến. |
| **Nhịp hợp đồng/thương mại** | Phạm vi, ngân sách và thay đổi được xét theo mốc hợp đồng. | Thay đổi Product Backlog không tự sửa điều khoản và chi phí. |

Khi nói **“vendor chậm”**, phải hỏi **chậm ở nhịp nào, so với điều kiện nào, và đó là hàng đợi hay ràng buộc bắt buộc**. Hai nhà cung cấp cùng phát hành theo quý có thể khác biệt lớn: một bên vẫn cung cấp contract, sandbox và bản ứng viên liên tục; bên kia chỉ cho kiểm thử sau khi bản chính thức đã phát hành.

### 2.2. Nhịp đội sản phẩm và nhịp đối tác có thể chồng lấn một phần

~~~mermaid
flowchart LR
    subgraph A["Nhóm sản phẩm — vòng phản hồi ngắn"]
        A1["Làm rõ lát cắt"] --> A2["Code + CI"]
        A2 --> A3["Kiểm chứng tích hợp"]
        A3 --> A4["Increment Done"]
    end
    subgraph B["Nhà cung cấp — nhịp thay đổi riêng"]
        B1["Tiếp nhận yêu cầu"] --> B2["Phân tích / phê duyệt"]
        B2 --> B3["Phiên bản / thay đổi"]
        B3 --> B4["Hỗ trợ vận hành"]
    end
    A1 -. "Hợp đồng / dữ liệu mẫu" .-> B1
    A3 -. "Sandbox / compatibility" .-> B3
    A4 -. "Release policy / support" .-> B4
~~~

Nhóm có thể tăng vòng phản hồi nội bộ **mà không ép nhà cung cấp đổi cơ cấu quản trị**, bằng cách làm rõ hợp đồng sớm, dùng sandbox/contract tests và phát triển các phần không cần chờ. Tuy nhiên, một giả lập chỉ giúp giảm bất định sớm; **nó không thay thế bằng chứng hệ thống thật tích hợp đúng** trước khi coi phần phụ thuộc đạt chuẩn.

### 2.3. Phân biệt lịch có thể thương lượng và điều kiện bắt buộc

Ví dụ:

- **Có thể thương lượng:** kênh trao đổi, định dạng API spec, số lần cung cấp test build, thời điểm đặt lịch sandbox, người đầu mối thay thế.
- **Có thể cải tiến qua công nghệ:** contract tests, môi trường kiểm thử tự phục vụ, backward compatibility, tự động xác nhận phiên bản.
- **Có thể cần quyết định hợp đồng:** thời gian hỗ trợ, quyền nhận thay đổi trước, điều khoản xử lý defect, môi trường test và chi phí.
- **Có thể bắt buộc:** quy định bảo vệ dữ liệu, giới hạn quyền production, xác thực danh tính, kiểm toán, nghĩa vụ an toàn hoặc một điều khoản hợp đồng đang có hiệu lực.

Không gọi việc bỏ một kiểm soát bảo mật là **“giảm phụ thuộc để Agile hơn”**.

## 3. Những mô hình quan hệ nhà cung cấp cần phân biệt

### 3.1. Không phải nhà cung cấp nào cũng có cùng phạm vi trách nhiệm

| Kiểu quan hệ | Ví dụ | Điều nhóm sản phẩm kiểm soát được | Điểm phụ thuộc khó |
| --- | --- | --- | --- |
| **SaaS/API dùng chung** | Dịch vụ định danh, gửi email, bản đồ. | Consumer code, cấu hình trong quyền, cách tích hợp và giám sát. | Lịch API/version, availability, thay đổi nhà cung cấp. |
| **Gia công phát triển theo hợp đồng** | Vendor xây một phân hệ UI/ERP. | Mô tả nhu cầu, tiêu chí chấp nhận, hợp đồng, tích hợp phía mình. | Công suất vendor, thay đổi phạm vi, cách kiểm chứng giữa hai bên. |
| **COTS/phần mềm đóng gói** | Nền tảng thương mại có plugin và lịch nâng phiên bản. | Cấu hình/extension được phép, contract tích hợp. | Giới hạn sản phẩm, lịch patch, thiếu quyền sửa lõi. |
| **Đối tác tích hợp hệ thống** | Tích hợp dữ liệu với hệ thống đào tạo của tổ chức khác. | Hợp đồng trao đổi và điều kiện test trong phạm vi sở hữu. | Quyền dữ liệu, lịch thay đổi, đồng bộ sơ đồ. |
| **Nhà cung cấp hạ tầng/managed service** | Database, cloud, monitoring. | Cách sử dụng dịch vụ, backup/khôi phục trong quyền. | Thay đổi nền tảng, quyền, quota, hỗ trợ sự cố. |
| **Đơn vị kiểm định/đánh giá độc lập** | Kiểm thử an toàn hoặc đánh giá tuân thủ khi cần. | Chuẩn bị bằng chứng và sửa các phát hiện. | Khung thời gian đánh giá và quyền ra kết luận độc lập. |

Một vendor có thể đóng nhiều vai trò cùng lúc: vừa cung cấp SaaS vừa triển khai tùy chỉnh. **Ai sở hữu code, dữ liệu, hoạt động production và quyền quyết định** phải được xác định theo thực tế và hợp đồng, không đoán từ nhãn “outsource”.

### 3.2. Đầu ra hợp đồng khác kết quả sản phẩm

Nhà cung cấp có thể giao:

- API endpoint theo hợp đồng.
- Mã nguồn hoặc binary trong phiên bản xác định.
- Chứng cứ kiểm thử/hồ sơ an toàn cần thiết.
- Cấu hình, tài liệu vận hành hoặc runbook.
- Khả năng truy cập môi trường thử.
- Dịch vụ hoạt động theo điều kiện cam kết.

Nhóm sản phẩm cần **kết quả**: học viên tự đăng ký thành công và dữ liệu đúng. Việc vendor báo “đã giao API” chỉ xác nhận một đầu ra trong phạm vi hợp đồng nếu bằng chứng phù hợp; chưa chứng minh hành trình web–API–database–quyền đã tích hợp, cũng chưa chứng minh outcome người dùng.

### 3.3. Ranh giới trách nhiệm dùng mô hình chia sẻ trách nhiệm

Chẳng hạn với SaaS định danh:

- Provider có thể chịu trách nhiệm vận hành nền tảng định danh và các khả năng được cam kết.
- Nhóm sản phẩm vẫn chịu trách nhiệm **kiểm tra claims/token đúng cách, phân quyền truy cập tài nguyên của mình, lưu secret an toàn và thông báo trạng thái cho người dùng**.
- Nhà cung cấp không tự chịu trách nhiệm cho lỗ hổng do consumer bỏ qua kiểm tra quyền ở API nội bộ.

Đối với cloud/managed service, phạm vi chia sẻ trách nhiệm thay đổi theo sản phẩm và điều khoản. Cần xem **tài liệu/điều khoản thực của đối tác**, không lấy một mô hình khái quát làm cam kết.

## 4. Nhận diện phụ thuộc theo luồng giá trị

### 4.1. Bắt đầu từ hành vi người dùng cần giao

Một Product Backlog Item minh họa:

> Là học viên đủ điều kiện, tôi muốn đăng ký khóa học miễn phí còn chỗ để biết mình có thể tham gia mà không cần gọi nhân viên hỗ trợ.

Hỏi:

1. Để PBI thực sự **Done**, thành phần/hợp đồng nào phải hoạt động?
2. Phần nào hiện tại đã có khả năng và phần nào cần vendor đổi?
3. Khi nào cần biết **sẽ dùng được hay không** để điều chỉnh Sprint Goal hoặc phạm vi?
4. Các kịch bản lỗi/không sẵn sàng nào phải được kiểm chứng?
5. Ai có quyền yêu cầu thay đổi, cung cấp môi trường thử, chấp nhận đầu ra hoặc phê duyệt phát hành?
6. Có thể tách một lát cắt giá trị **không bỏ kiểm soát bắt buộc** để tránh chờ không?

Không chỉ lập danh sách “cần vendor A, vendor B”. Cần biết **điều kiện cụ thể**: phiên bản hợp đồng, claim nào được bảo đảm, sandbox nào, chứng cứ nào, cửa sổ nào và mức rủi ro nếu thiếu.

### 4.2. Bản đồ phụ thuộc minh họa

~~~mermaid
flowchart TD
    Goal["Học viên đăng ký đúng và biết trạng thái"]
    Goal --> Web["Web và hành trình người học"]
    Goal --> Enroll["Đăng ký, sức chứa, dữ liệu"]
    Goal --> Verify["Kiểm thử trên bản tích hợp"]
    Web -. "SSO/token hiện hành" .-> IdP["Nhà cung cấp định danh"]
    Enroll -. "Claims/permission contract" .-> IdP
    Enroll -. "DB runtime/sandbox" .-> Infra["Nhà cung cấp nền tảng"]
    Verify -. "Sandbox và test accounts" .-> IdP
    Verify -. "Môi trường/test data" .-> Infra
    Goal -. "Xác nhận ngoài hệ thống nếu thuộc scope" .-> Notify["Nhà cung cấp thông báo"]
~~~

Các cạnh nét đứt biểu diễn **điều kiện hoặc nhu cầu phối hợp**. Chúng không mặc nhiên là blocker. Ví dụ, nếu IdP đã có hợp đồng ổn định, nhóm có thể tích hợp với khả năng hiện hành trong khi vendor phát triển phiên bản mới theo lịch khác.

### 4.3. Phân biệt “cần phiên bản mới” với “muốn phiên bản mới”

Một nhóm dễ tự tạo phụ thuộc bằng cách gắn Product Goal vào tính năng vendor **chưa cần thiết**:

- **Cần:** xác minh danh tính và quyền đọc trạng thái đăng ký.
- **Muốn:** giao diện đăng nhập hoàn toàn mới trong phiên bản vendor sắp phát hành.

Nếu khả năng hiện tại đáp ứng tiêu chí an toàn, nhóm có thể tách:

1. **Lát cắt giá trị hiện tại:** dùng hợp đồng ổn định đã kiểm chứng.
2. **Lát cắt cải tiến sau:** nâng cấp trải nghiệm khi phiên bản vendor mới sẵn sàng, có kiểm tra tương thích.

Tuy nhiên, nếu phiên bản mới **sửa một lỗ hổng nghiêm trọng hoặc đáp ứng ràng buộc bắt buộc**, việc hoãn chỉ để đạt tiến độ không được tự động chấp nhận. Cần theo chính sách ứng cứu/thay đổi có thẩm quyền.

### 4.4. Dependency register dành cho vendor

| Trường | Câu hỏi cần trả lời |
| --- | --- |
| **ID/liên kết PBI hoặc mục tiêu** | Phụ thuộc nào ảnh hưởng kết quả nào? |
| **Consumer/provider** | Nhóm nào cần điều kiện từ đơn vị nào, đầu mối là ai? |
| **Hợp đồng/phiên bản** | API, schema, tài liệu, release line hay điều khoản nào? |
| **Đầu ra có thể kiểm chứng** | Cần môi trường, build, test, quyết định hoặc bằng chứng nào? |
| **Lịch vendor và mốc cần biết** | Khi nào họ có thể cung cấp, lịch đã xác nhận hay chỉ dự kiến? |
| **Giới hạn quyền/chi phí** | Ai được yêu cầu thay đổi, có phát sinh thay đổi hợp đồng không? |
| **Tác động nếu trễ** | Chặn DoD, Sprint Goal, release, giá trị hoặc an toàn ở mức nào? |
| **Phương án thích ứng** | Dùng hợp đồng cũ, mock có kiểm chứng, thay đổi phạm vi, fallback an toàn? |
| **Owner và escalation** | Ai theo dõi và ai có thể ra quyết định cần thiết? |
| **Trạng thái/bằng chứng** | Chưa làm rõ, đã xác nhận, đang chờ, đã tích hợp kiểm chứng? |

Trạng thái “vendor báo xong” **khác** trạng thái “consumer đã kiểm chứng tương thích” và “Increment đã đạt DoD”.

## 5. Thiết kế hai kế hoạch liên kết: nhịp sản phẩm và nhịp nhà cung cấp

### 5.1. Không gộp hai nhịp thành một lịch đẹp nhưng sai

Kế hoạch nội bộ nên thể hiện **những gì đội có thể làm, học và kiểm chứng trong từng vòng ngắn**. Kế hoạch vendor phản ánh **những điều kiện bên ngoài, thời điểm cần quyết định, cửa sổ test và các mốc hợp đồng**.

| Lớp kế hoạch | Mục đích | Ví dụ |
| --- | --- | --- |
| **Product Goal / roadmap thích ứng** | Hướng giá trị cho người học và những quyết định lớn. | Tự đăng ký đáng tin cậy trước khi mở khả năng mới. |
| **Product Backlog có thứ tự** | Các nhu cầu cải tiến sản phẩm, rủi ro và công việc cần thiết. | Kết nối IdP, trạng thái đăng ký, kiểm thử retry. |
| **Sprint Goal / kế hoạch ngắn hạn** | Mục tiêu tạo Increment có thể dùng khi áp dụng Scrum. | Hoàn tất luồng đăng ký với IdP hiện hành đã hỗ trợ. |
| **Dependency/release calendar** | Mốc bên ngoài và thời điểm cần biết. | Vendor xác nhận contract, sandbox window, API deprecation. |
| **Integration/release readiness** | Điều kiện sản phẩm phải chứng minh trước khi mở tính năng. | Auth tests, contract tests, dữ liệu đúng và runbook. |

**Dependency calendar không phải thứ thay Product Backlog**. Ngược lại, Product Backlog không tự thay hợp đồng, quyền phê duyệt và lịch hỗ trợ thực tế.

### 5.2. “Ngày giao” và “ngày cần biết” là hai khái niệm khác nhau

Nếu một thay đổi API dự kiến có vào cuối tháng, nhóm có thể cần:

- Trước một mốc sớm hơn: **biết contract/schema tối thiểu** để làm UI và test phù hợp.
- Trước một mốc khác: **có sandbox hoặc pre-release** để kiểm chứng bất định.
- Trước ngày mở cho người dùng: **bản provider chính thức tương thích, bảo mật đạt và phương án hỗ trợ**.

Mốc **cần biết** giúp nhóm kịp đổi kế hoạch trước khi bị chặn. Chờ tới đúng ngày vendor dự kiến giao rồi mới phát hiện không thể tích hợp là phát hiện quá muộn.

### 5.3. Ví dụ lịch giả định hai nhịp

| Thời điểm minh họa | Nhóm Agile | Vendor | Câu hỏi kiểm chứng |
| --- | --- | --- | --- |
| **Tuần 1** | Làm rõ PBI, test quyền, dựng adapter hợp đồng hiện hành. | Xác nhận khả năng API và chính sách hỗ trợ. | Có thể đạt phần giá trị đầu với hợp đồng hiện hành không? |
| **Tuần 2** | Tích hợp end-to-end, test lỗi timeout/retry, demo bản thực. | Trả lời các câu hỏi hợp đồng, cấp sandbox phù hợp. | Có bằng chứng tích hợp thật hay còn dùng mock? |
| **Tuần 3–4** | Tiếp tục cải tiến nhỏ độc lập, chuẩn bị rollout có kiểm chứng. | Đánh giá/hoàn tất thay đổi theo lịch riêng nếu cần. | Có phải thay đổi vendor là blocker của lát cắt hiện tại? |
| **Mốc vendor** | Chạy contract/integration regression, xem rủi ro nâng phiên bản. | Công bố build/changelog/deprecation. | Những consumer nào bị ảnh hưởng; có đường khôi phục không? |
| **Sau release** | Quan sát outcome, hỗ trợ người dùng và backlog thích ứng. | Hỗ trợ vận hành, xử lý sự cố theo hợp đồng. | Người dùng có được giá trị và dữ liệu có đúng không? |

Đây **không phải SLA hay lịch hẹn thật**; các mốc chỉ minh họa tư duy. Với yêu cầu có độ bất định cao, cần nói rõ dự báo, giả định, điều kiện quyết định và người chịu trách nhiệm cập nhật.

### 5.4. Quy tắc lập kế hoạch khi vendor trễ

Thay vì chỉ kéo toàn bộ ngày giao:

1. Xác định **hành vi nào thực sự bị chặn**.
2. Giữ những chuẩn chất lượng và an toàn không thể đánh đổi.
3. Tách phần có giá trị dùng được với hợp đồng hiện hành nếu hợp lệ.
4. Làm sớm những việc giúp phát hiện sai hợp đồng: ví dụ, test, adapter, dữ liệu giả.
5. Đánh giá thay đổi Sprint Goal/phạm vi theo trách nhiệm Scrum hoặc quy trình sản phẩm đang dùng.
6. Thông báo dự báo mới và lý do cho stakeholder, không giả vờ mọi thứ vẫn đúng lịch.
7. Xem các rủi ro được chuyển sang support/vận hành hay không.

**Không dùng mock và bản demo để tuyên bố Increment đã Done** nếu điều kiện tích hợp quan trọng chưa đạt.

## 6. Đặt hợp đồng giao tiếp thay vì phụ thuộc vào lời hứa

### 6.1. Hợp đồng có nhiều lớp

| Lớp | Nội dung cần làm rõ | Ai cần tham gia |
| --- | --- | --- |
| **Nghiệp vụ** | Hành vi nào là đúng, trường hợp lỗi và giới hạn. | Product Owner, người dùng/đại diện, vendor và Developers liên quan. |
| **Kỹ thuật** | API/schema/event, phiên bản, lỗi, timeout, retry, auth. | Consumer/provider engineers, kiểm thử, bảo mật. |
| **Chất lượng** | Acceptance criteria, kiểm thử, môi trường và bằng chứng hoàn tất. | Developers, QA, test/engineering vendor theo phạm vi. |
| **Phát hành** | Build/version, lịch deploy, compatibility, rollback/forward fix. | Release/on-call, vendor operations, owner dịch vụ. |
| **Vận hành** | Giám sát, incident, support, SLI/SLO/SLA và escalation. | Service owner, support và vendor support. |
| **Thương mại/pháp lý** | Phạm vi bàn giao, change requests, quyền dữ liệu, giấy phép, trách nhiệm. | Người có thẩm quyền hợp đồng/procurement/legal và bên cung cấp. |

Một tài liệu **OpenAPI** có thể nói đúng endpoint nhưng chưa giải thích **trách nhiệm khi sai dữ liệu, kỳ hỗ trợ phiên bản hoặc quyền sửa production**. Hợp đồng kỹ thuật cần được nối với những ràng buộc còn lại.

### 6.2. Ví dụ hợp đồng tối thiểu cho IdP

Giả sử nhóm Enrollment nhận token từ một nhà cung cấp định danh. Những điều cần làm rõ gồm:

- Issuer, audience, thuật toán/kênh xác minh và vòng đời khóa ký theo chính sách.
- Định danh học viên ổn định nào consumer được phép dùng.
- Các claims nào **được bảo đảm** và claims nào chỉ tùy chọn.
- Token hết hạn, bị thu hồi, đổi khóa và phiên đăng nhập xử lý thế nào.
- Những lỗi nào là tạm thời và điều gì không được tự retry.
- Khi nào provider có thể thêm/đổi claim, hợp đồng deprecation.
- Sandbox/test accounts và cách kiểm tra hành vi tương thích.
- Trách nhiệm bảo vệ dữ liệu, logs, support và ứng cứu.

Không nên tự coi mọi claim do token cung cấp là căn cứ **phân quyền truy cập học viên khác**; consumer phải thực thi quy tắc quyền của sản phẩm.

### 6.3. Thỏa thuận giao tiếp có thể kiểm chứng

Ví dụ thay câu:

> “Vendor sẽ hỗ trợ API mới trong Sprint tới.”

bằng:

> “Hai bên xác nhận contract cho thao tác tra trạng thái đăng ký, bao gồm các mã lỗi và quyền truy cập. Bên cung cấp công bố sandbox/version hỗ trợ theo mốc xác nhận riêng; nhóm consumer có contract tests và sẽ kiểm chứng trên bản cung cấp thật. Nếu chưa có bằng chứng tương thích trước mốc quyết định phát hành, khả năng mới không được đưa vào Increment như đã Done.”

Thỏa thuận như vậy làm rõ **đầu ra**, **bằng chứng** và **phương án khi điều kiện chưa đạt**. Nó không hứa vendor phải chuyển sang Sprint.

### 6.4. Acceptance criteria, DoD và nghiệm thu hợp đồng khác nhau

| Khái niệm | Để làm gì? | Không nên nhầm với |
| --- | --- | --- |
| **Acceptance criteria** | Những hành vi/điều kiện cụ thể cho PBI hoặc kết quả bàn giao. | Toàn bộ Definition of Done. |
| **Definition of Done (Scrum)** | Cam kết về trạng thái chất lượng của Increment; cùng sản phẩm có cùng DoD. | Biên bản vendor nghiệm thu hoặc demo. |
| **Vendor acceptance/contractual acceptance** | Xác định deliverable đã đáp ứng điều kiện thỏa thuận và quyền/nghĩa vụ tương ứng. | Người dùng đã nhận giá trị hoặc hệ thống đã tích hợp an toàn. |
| **Release readiness** | Các điều kiện để mở sử dụng theo rủi ro, quyền và vận hành. | Chỉ cần vendor gửi build. |
| **Outcome** | Thay đổi thực tế trong hành vi/kết quả người dùng. | Số task hoàn thành hoặc số ngày đúng hợp đồng. |

Một deliverable có thể đã được nghiệm thu theo hợp đồng nhưng **chưa đạt DoD của Increment sản phẩm** vì thiếu tích hợp hoặc kiểm thử liên hệ thống. Ngược lại, các điều kiện thanh toán/nghiệm thu thương mại không tự bị thay bằng việc một Scrum Team đánh dấu Done.

## 7. Quản trị phạm vi, thay đổi và cam kết thương mại mà vẫn thích ứng

### 7.1. Agile không có nghĩa hợp đồng không còn hiệu lực

Tư duy Agile ưu tiên **cộng tác với khách hàng hơn thương lượng hợp đồng** và **thích ứng với thay đổi hơn bám theo một kế hoạch bất biến**. Điều đó **không phải chỉ dẫn bỏ hợp đồng, né nghĩa vụ pháp lý hoặc không cần kiểm soát chi phí**.

Khi làm việc với nhà cung cấp, có thể gặp:

- **Fixed scope/fixed price:** điều khoản rõ về deliverables và chi phí; thay đổi có thể cần quy trình bổ sung.
- **Time and materials:** chi phí theo thời gian/năng lực; cần minh bạch ngân sách, ưu tiên và kiểm soát kết quả.
- **Capacity-based engagement:** thuê một năng lực nhất định, ưu tiên thay đổi linh hoạt trong giới hạn thỏa thuận.
- **Managed service/SaaS:** trả tiền cho một dịch vụ với mức hỗ trợ/availability được xác định; consumer ít quyết định roadmap bên cung cấp.
- **Outcome-oriented arrangements:** một số thỏa thuận tập trung mục tiêu kết quả, nhưng cần đo lường và phân định các yếu tố ngoài quyền kiểm soát của vendor.

Không thể khẳng định **một kiểu hợp đồng luôn Agile hơn**. Mỗi kiểu có đánh đổi về phân chia rủi ro, biến động phạm vi, khả năng quan sát chất lượng và quyền thay đổi. Người có thẩm quyền thương mại/pháp lý cần tham gia khi điều khoản thay đổi.

### 7.2. Dùng các lát cắt giá trị nhỏ làm điểm kiểm chứng hợp đồng khi phù hợp

Nếu có quyền đàm phán thỏa thuận, thay vì chỉ mô tả một **bản bàn giao lớn cuối quý**, có thể đề xuất:

1. Hợp đồng nghiệp vụ/technical contract có ví dụ cụ thể.
2. Sandbox hoặc pre-release để consumer kiểm chứng sớm.
3. Những **deliverables nhỏ, tích hợp được** và có tiêu chí chất lượng rõ.
4. Demo trên bản tích hợp, không chỉ slide hoặc môi trường riêng của vendor.
5. Một cơ chế làm rõ thay đổi và rủi ro theo nhịp phù hợp.
6. Quy định quyền sở hữu tri thức, tài liệu, test, dữ liệu, hỗ trợ sau nghiệm thu.

Mức chi tiết và quyền thực thi phụ thuộc hợp đồng thật. Nếu doanh nghiệp đã có hợp đồng cố định, đội sản phẩm **không tự đổi điều khoản bằng một working agreement nội bộ**; cần đi đúng quy trình thay đổi.

### 7.3. Change request khác refinement hằng ngày

| Tình huống | Cách nhận diện | Hướng xử lý |
| --- | --- | --- |
| Vendor hỏi ý nghĩa mã trạng thái đã cam kết | **Làm rõ** cách thực hiện điều đã thuộc phạm vi. | Trả lời bằng ví dụ, kiểm thử và cập nhật tài liệu. |
| Người dùng yêu cầu chức năng SMS chưa thuộc phạm vi | **Mở rộng khả năng** nếu quyết định thực hiện. | Product Owner xem giá trị; hợp đồng vendor có thể cần change request. |
| Provider giao API không đúng hợp đồng đã nghiệm thu | Có thể là **defect hoặc không phù hợp bàn giao**. | Thu bằng chứng, xử lý theo bảo hành/hợp đồng và rủi ro hệ thống. |
| Cần thay đổi API vì quy định bảo mật mới | **Thay đổi bắt buộc** với tác động kỹ thuật/thương mại. | Thẩm định đúng quyền, lập kế hoạch rủi ro và thay đổi hợp đồng nếu cần. |
| Consumer chuyển schema mà không báo vendor | **Thay đổi phụ thuộc do bên mình tạo**. | Cần sửa contract, kiểm chứng và chịu trách nhiệm theo thỏa thuận. |

Không gọi mọi câu hỏi là **scope creep** để né làm rõ, nhưng cũng không hứa mọi yêu cầu phát sinh là “chỉnh nhẹ” khi nghĩa vụ và chi phí thay đổi.

### 7.4. Mô hình quyền quyết định tối thiểu

| Quyết định | Chủ thể phù hợp | Điều cần rõ |
| --- | --- | --- |
| Sắp thứ tự PBI và phạm vi giá trị sản phẩm trong Scrum | **Product Owner** | Hướng tới Product Goal; tham vấn stakeholders và rủi ro. |
| Thiết kế tích hợp và kiểm thử trong phạm vi được giao | **Developers và chuyên gia phù hợp** | Tuân thủ DoD, chính sách dữ liệu/kiến trúc. |
| Thay đổi cam kết giá, thời gian hoặc quyền trong hợp đồng | **Người có thẩm quyền hợp đồng/procurement/legal** | Có quy trình và bằng chứng chấp thuận. |
| Thay đổi môi trường production/vận hành | **Bên có quyền release/on-call hoặc service owner theo quy trình** | Dừng rollout, rollback, dữ liệu và truyền thông. |
| Xử lý sự cố bảo mật/riêng tư | **Đường ứng cứu chuyên biệt có thẩm quyền** | Hạn chế tác động, bảo toàn bằng chứng, nghĩa vụ thông báo. |
| Thay đổi roadmap/version của vendor | **Nhà cung cấp theo quyền sở hữu và hợp đồng** | Consumer nhận thông báo và kiểm chứng ảnh hưởng. |

**Một Product Owner không mặc nhiên có quyền sửa hợp đồng, bỏ kiểm soát bảo mật hoặc buộc vendor thay lịch phát hành.** Ngược lại, người mua hàng không nên tự quyết định thứ tự Product Backlog mà không có ngữ cảnh giá trị sản phẩm.

### 7.5. Khi nào cần một bản ghi quyết định?

Quyết định thay hợp đồng provider, xử lý không tương thích lâu dài hoặc chấp nhận rủi ro vận hành có thể được ghi ngắn:

~~~text
Decision ID: VND-EXAMPLE-04
Vấn đề: API IdP mới chưa thể kiểm chứng trong sandbox hiện có
Lựa chọn A: giữ hợp đồng API cũ còn được hỗ trợ
Lựa chọn B: hoãn mở tính năng tới khi bản mới được kiểm chứng
Lựa chọn C: dùng provider khác nếu đáp ứng pháp lý/kỹ thuật/thương mại
Tiêu chí: giá trị người học, bảo mật, chi phí, thời gian, khả năng khôi phục
Quyết định: [người có thẩm quyền xác nhận]
Giới hạn: [những điều chưa biết / điều kiện phải kiểm chứng]
Ngày xem lại: [mốc sau khi vendor cung cấp bằng chứng]
~~~

Đây là **mẫu minh họa**. Không cần một ban phê duyệt mới cho mọi thay đổi nhỏ; chỉ ghi những quyết định cần truy vết, có tác động tới nhiều bên hoặc khó đảo ngược.

## 8. Giảm phụ thuộc bằng kiến trúc và cấu trúc lát cắt

### 8.1. Cô lập khác biệt nhịp sau một ranh giới hợp đồng

Nếu logic của nhà cung cấp nằm rải khắp UI và backend, mỗi lần vendor đổi schema có thể làm nhiều nhóm phải sửa. Một **adapter/anti-corruption layer** có thể chuyển hợp đồng bên ngoài thành mô hình nội bộ ổn định:

~~~mermaid
flowchart LR
    UI["UI / hành trình học viên"] --> APP["Ứng dụng đăng ký"]
    APP --> PORT["Cổng định danh nội bộ / port"]
    PORT --> ADAPTER["Adapter nhà cung cấp"]
    ADAPTER --> V["API của IdP"]
    APP --> DB["Dữ liệu đăng ký"]
    V -. "Version / contract changes" .-> ADAPTER
~~~

**Lợi ích tiềm năng:** thay nhà cung cấp/phiên bản chủ yếu tác động adapter; ứng dụng có thể kiểm tra logic nghiệp vụ bằng interface ổn định. **Chi phí:** thêm mã và trách nhiệm bảo trì; nếu adapter chỉ chuyển tiếp mọi field/vendor exception không kiểm soát, coupling vẫn còn.

### 8.2. Contract-first và consumer-driven contract

Thay vì chờ vendor bàn giao code hoàn chỉnh:

- Làm rõ request/response, enum, error codes và semantics.
- Kiểm tra hành vi qua ví dụ từ người dùng.
- Tạo **contract tests** cho những kỳ vọng quan trọng.
- Cho provider chạy kiểm chứng phù hợp trên bản thực hoặc pre-release.
- Công bố thay đổi tương thích/vỡ hợp đồng và quản lý version.

**Consumer-driven contract** hữu ích khi nhà cung cấp có thể tham gia và quản lý kỳ vọng nhiều consumer; với SaaS đóng, consumer vẫn có thể tự viết **compatibility checks** và theo dõi changelog, nhưng không mặc nhiên buộc SaaS chạy test do mình cung cấp.

### 8.3. Mock và sandbox giảm chờ, không phải bằng chứng cuối

| Lớp | Mục tiêu | Điều chưa chứng minh |
| --- | --- | --- |
| **Mock/stub từ contract** | Phát triển UI/logic trong lúc chờ dịch vụ thật. | Provider thực xử lý đúng tất cả trường hợp. |
| **Contract test** | Kiểm tra tương thích nghĩa vụ giao tiếp. | Tính đúng đắn toàn luồng, dữ liệu đồng thời, độ trễ thật. |
| **Sandbox integration** | Kiểm tra tích hợp với bản provider thử. | Sandbox có thể khác production về cấu hình, tải và quy mô. |
| **Pre-production E2E** | Kiểm tra hành trình người dùng trên hệ thống tích hợp. | Không chứng minh mọi sự cố production sẽ không xảy ra. |
| **Rollout có quan sát** | Phát hiện khác biệt thực tế và xác minh outcome. | Không thay DoD, kiểm soát an toàn hay nghiệm thu bắt buộc. |

Nếu nhà cung cấp chỉ cung cấp sandbox **cũ hơn production**, nhóm phải biết giới hạn ấy. “Contract tests xanh trên fake” chỉ nên được ghi là **bằng chứng của fake/contract**, không phải xác nhận thay cho tích hợp thật.

### 8.4. Chia lát cắt theo khả năng sẵn có

Giả sử vendor thông báo **phiên bản IdP mới có giao diện đăng nhập tùy chỉnh** chỉ phát hành sau hai tháng, nhưng giao thức chuẩn hiện hành đã đáp ứng xác thực học viên. Có thể tách:

1. **Lát cắt đầu:** dùng giao thức hiện hành, tích hợp đúng authn/authz, bảo vệ dữ liệu và hoàn tất hành vi tự đăng ký.
2. **Lát cắt cải tiến:** thử trải nghiệm đăng nhập mới khi vendor cung cấp version và sandbox phù hợp.

Đó là **giảm phụ thuộc theo giá trị**, không phải lách yêu cầu. Nếu phiên bản mới bắt buộc để đáp ứng an toàn hoặc luật hiện hành thì không tự hoãn.

### 8.5. Những chiến thuật giảm coupling cần đánh giá rủi ro

| Chiến thuật | Phụ thuộc được giảm | Rủi ro cần xét |
| --- | --- | --- |
| **Adapter/port** | Consumer không trực tiếp phụ thuộc mọi chi tiết vendor. | Độ phức tạp adapter, test và bảo trì. |
| **Backward-compatible changes** | Không bắt mọi consumer nâng đồng thời. | Hạn hỗ trợ, enum/schema, client parsing. |
| **Feature flags** | Tách deploy code khỏi thời điểm mở hành vi. | Không thay thế phân quyền; phải quản lý vòng đời flag. |
| **Phased rollout/canary** | Giảm quy mô tác động khi mở thay đổi. | Dữ liệu đã ghi hoặc thông báo gửi đi có thể không đảo ngược. |
| **Queue/event integration** | Giảm phụ thuộc thời điểm dịch vụ phải cùng online. | Idempotency, ordering, eventual consistency, DLQ, privacy. |
| **Circuit breaker/timeout/bulkhead** | Giới hạn việc lỗi provider lan ra các dịch vụ khác. | Fallback không được trả thành công giả hoặc làm sai dữ liệu. |
| **Cache có giới hạn** | Giảm số cuộc gọi đồng bộ khi dữ liệu chấp nhận được độ trễ. | Dữ liệu cũ không an toàn với quyền, số chỗ còn lại hoặc thanh toán. |
| **Self-service setup** | Giảm chờ cấu hình/môi trường từ nhà cung cấp. | Quyền, quota, dữ liệu test, audit. |

Một hệ thống đăng ký **không được xác nhận còn chỗ dựa trên cache có thể đã cũ** nếu quy tắc nghiệp vụ đòi kiểm soát sức chứa chính xác. Fallback phải tương ứng tính chất giao dịch.

## 9. Test strategy khi hai bên không cùng nhịp

### 9.1. Tổ chức các tầng kiểm chứng với mục đích khác nhau

Một chiến lược kiểm thử phù hợp có thể gồm:

1. **Unit tests:** nghiệp vụ nội bộ như không tạo đăng ký trùng.
2. **Contract tests:** request/response và lỗi/phiên bản IdP.
3. **Integration tests:** application + database + provider sandbox thật trong quyền phù hợp.
4. **Security tests:** token, permissions, tenant isolation và lỗi từ chối.
5. **Failure-mode tests:** provider timeout, unavailable, token expired, retry, rate limit.
6. **End-to-end tests:** học viên hoàn tất hành trình được xác định.
7. **Release smoke tests:** kiểm chứng phiên bản/cấu hình và tín hiệu sau triển khai.

Không phải mọi test đều phải chạy mỗi lần ở mọi môi trường; nhưng các kiểm soát **bắt buộc để đạt DoD và bảo vệ người dùng** phải có bằng chứng trước khi công bố hoàn tất hoặc mở sử dụng.

### 9.2. Gherkin minh họa cho tích hợp định danh và đăng ký

~~~gherkin
Feature: Đăng ký khóa miễn phí qua nhà cung cấp định danh

  Scenario: Học viên đã được xác thực hợp lệ đăng ký thành công
    Given học viên A có phiên xác thực hợp lệ theo hợp đồng IdP đang hỗ trợ
    And A đủ điều kiện cho khóa X còn chỗ
    When A gửi yêu cầu đăng ký khóa X
    Then hệ thống ghi đúng một đăng ký hiệu lực của A
    And A nhận kết quả đã xác nhận từ dữ liệu thực

  Scenario: Phiên đăng nhập hết hạn
    Given phiên xác thực của A đã hết hạn
    When A gửi yêu cầu đăng ký khóa X
    Then hệ thống từ chối thao tác cần quyền theo chính sách
    And không tạo đăng ký hiệu lực mới
    And hướng dẫn A xác thực lại an toàn nếu phù hợp

  Scenario: Không có quyền đọc trạng thái của người khác
    Given học viên B không có quyền đọc đăng ký riêng của A
    When B yêu cầu tra cứu trạng thái đăng ký của A
    Then hệ thống từ chối truy cập ở phía server
    And không tiết lộ dữ liệu riêng của A

  Scenario: IdP tạm không phản hồi
    Given khả năng cần xác minh với IdP tạm thời không sẵn sàng
    When A thực hiện thao tác yêu cầu xác thực bổ sung
    Then hệ thống không tự suy rằng A đã được xác thực thành công
    And trả trạng thái lỗi an toàn theo hợp đồng
    And không ghi giao dịch đăng ký không hợp lệ

  Scenario: Client mất phản hồi sau khi đăng ký đã được ghi
    Given yêu cầu đăng ký hợp lệ ban đầu của A đã commit thành công
    And phản hồi tới trình duyệt bị gián đoạn
    When A tra trạng thái hoặc gửi lại theo cơ chế idempotent đã thiết kế
    Then không có đăng ký hiệu lực thứ hai của A cho cùng khóa
    And A có thể xác minh trạng thái cuối đúng
~~~

Đây là **ví dụ nghiệp vụ**, chưa phải test chạy được. Quy tắc token, retry và tình huống phụ thuộc cần được các bên kiểm chứng với hợp đồng thật, đặc biệt khi IdP có thể xử lý bằng token tự chứa mà không cần gọi server cho mọi request.

### 9.3. Mẫu test matrix liên hệ thống

| Điều kiện | Consumer unit/contract | Vendor sandbox | Bản tích hợp | Theo dõi sau release |
| --- | --- | --- | --- | --- |
| Claims hợp lệ | Contract assertions | Token test theo quyền | Hành vi đăng ký đúng | Lỗi authn/authz theo phạm vi an toàn |
| Claim thiếu hoặc ngoài hợp đồng | Kiểm thử từ chối | Dữ liệu thử đặc thù | Không cấp quyền sai | Alert truy cập bất thường |
| Provider timeout/rate limit | Stub failure responses | Fault injection khi được phép | Graceful failure / retry policy | Độ trễ và số lần thất bại |
| Hai đăng ký tranh chỗ cuối | Unit/integration DB | Không phụ thuộc IdP riêng cho phần DB | Concurrency trên hệ thống thật | Bất nhất sức chứa |
| Phiên bản API thay đổi | Compatibility tests | Bản mới/pre-release | Regression trên version mục tiêu | Correlation với rollout |
| Mất phản hồi sau commit | Idempotency tests | Không nhất thiết cần vendor | End-to-end + DB kiểm chứng | Ticket trạng thái mơ hồ |

Hãy giữ test trên **dữ liệu giả hoặc dữ liệu đã được phép dùng**, không tải hồ sơ thực sang sandbox tùy tiện. Các công cụ quan sát cũng không nên ghi token, mật khẩu hoặc thông tin cá nhân ngoài mục đích.

### 9.4. Nếu vendor không cung cấp sandbox giống production

Một số lựa chọn:

- Làm rõ **khác biệt đã biết** giữa sandbox và production.
- Dùng simulator/mock từ hợp đồng để kiểm chứng phần consumer.
- Kết hợp **contract verification** hoặc chứng cứ provider được phép cung cấp.
- Tổ chức một đợt tích hợp có kiểm soát với test accounts và quyền phù hợp.
- Giảm phạm vi rollout, quan sát rủi ro còn lại **chỉ khi đã đáp ứng những chuẩn bắt buộc**.
- Ghi rủi ro chưa được kiểm chứng cho người có quyền quyết thay vì gọi “test đầy đủ”.

Nếu không thể kiểm chứng yêu cầu về dữ liệu hoặc an toàn mà sản phẩm bắt buộc phải đạt, **không tuyên bố phần liên quan Done/ready** chỉ vì vendor không có sandbox.

### 9.5. Luồng phản hồi lỗi liên hệ thống

Khi test thất bại, ticket gửi vendor cần có:

- Môi trường, phiên bản consumer/provider và thời gian có múi giờ.
- Kịch bản, kết quả kỳ vọng theo hợp đồng và kết quả thực.
- Correlation ID hoặc log đã **lược bỏ thông tin nhạy cảm**.
- Phạm vi ảnh hưởng và khả năng tái hiện.
- Những giả thuyết đã kiểm tra, điều chưa chắc chắn.
- Đầu mối xử lý, mức ưu tiên/ảnh hưởng theo quy trình thỏa thuận.

Không chỉ gửi “API không chạy, nhờ kiểm tra” và cũng không gửi token thật qua email để vendor tự giải mã nếu kênh đó không được phép.

## 10. Quản lý phiên bản, deprecation và những đợt phát hành lệch nhịp

### 10.1. Một hệ thống sản phẩm có thể dùng nhiều phiên bản song song

Trong thời gian nâng cấp:

- Một phần backend có thể tiếp tục dùng API phiên bản cũ.
- Một nhóm người dùng thử nghiệm đã dùng đường mới.
- Web/mobile cũ vẫn tồn tại vì người dùng chưa cập nhật.
- Vendor chạy hai thế hệ hợp đồng trong một giai đoạn chuyển tiếp.
- Rollback consumer có thể cần khả năng provider vẫn hỗ trợ phiên bản trước.

Vì vậy, một thay đổi như **thêm giá trị mới vào enum** hoặc đổi ý nghĩa một field có thể phá consumer dù URL endpoint không đổi. Không nên hiểu **“cùng schema JSON nên tương thích”** nếu parser hoặc quy tắc nghiệp vụ không chấp nhận giá trị mới.

### 10.2. Quy trình xử lý thay đổi hợp đồng

~~~mermaid
flowchart TD
    A["Nhận thông báo version / deprecation"] --> B["Xác định consumer, dữ liệu và luồng bị ảnh hưởng"]
    B --> C["Đánh giá breaking/non-breaking theo hành vi thật"]
    C --> D["Lên phương án tương thích / chuyển tiếp"]
    D --> E["Chạy contract + integration + security tests"]
    E --> F{"Kiểm chứng đạt và rủi ro chấp nhận?"}
    F -- "Chưa" --> G["Sửa, thương lượng, hoãn hoặc xử lý khẩn theo policy"]
    G --> D
    F -- "Có" --> H["Rollout có kiểm soát, theo dõi"]
    H --> I["Xác minh consumer đã chuyển và loại bỏ phần cũ đúng hạn"]
~~~

Sơ đồ mô tả **thay đổi thông thường**. Nếu nhà cung cấp phát hiện một lỗ hổng bảo mật đang bị khai thác, có thể phải dùng quy trình ứng cứu/khắc phục khẩn theo thẩm quyền; không chờ vòng cải tiến chậm.

### 10.3. Mẫu bảng quản lý phiên bản

| Thành phần | Hiện tại | Vendor dự kiến | Mốc cần biết | Điều kiện consumer sẵn sàng |
| --- | --- | --- | --- | --- |
| IdP token/claim contract | v1 theo hợp đồng đang hỗ trợ | v2 có thêm claim | Trước khi chốt PBI phụ thuộc v2 | Có hợp đồng, test thiếu/đủ claim, phân quyền đúng. |
| API notification | API hiện hành | Batch thay đổi schema event | Trước tích hợp gửi xác nhận | Consumer tương thích; xử lý event lặp. |
| Sandbox | Bản tương đương v1 | Pre-release v2 | Trước quyết định nâng phiên bản | Test accounts, dữ liệu giả, logging và cửa sổ thử. |
| Chính sách support | Khung giờ và mức sự cố hiện hành | Đề xuất cập nhật | Trước go-live có rủi ro tăng | Có on-call/escalation theo thỏa thuận hợp lệ. |

Đây là ví dụ, **không phải phiên bản hay lịch của một dịch vụ thật**. Cần lấy dữ liệu thực từ hợp đồng/changelog được xác nhận khi áp dụng.

### 10.4. Cửa sổ đóng băng thay đổi và ngoại lệ

Một tổ chức có thể cấm deploy trong kỳ tuyển sinh, kiểm toán hoặc mùa cao điểm. Nhóm Agile cần:

- Biết chính sách và phạm vi áp dụng từ sớm.
- Phân biệt merge/code complete với deploy/release.
- Hoàn tất kiểm chứng và chuẩn bị rollback/forward fix đúng quyền.
- Không tích lũy những nhánh lớn chỉ vì chưa thể release; tiếp tục tích hợp an toàn khi được phép.
- Có cơ chế xử lý sự cố/bảo mật khẩn được định nghĩa trước.
- Tránh cam kết ngày release ngoài cửa sổ cho phép khi chưa có ngoại lệ được duyệt.

**Release freeze không ngăn mọi hình thức học hỏi**. Nhóm vẫn có thể làm rõ PBI, test contract, phân tích dữ liệu, cải thiện runbook hoặc thử prototype không tác động production.

### 10.5. “Go/No-go” cần điều kiện, không phải cảm giác

Một quyết định phát hành liên quan vendor có thể xét:

1. Increment đạt DoD chưa?
2. Các hợp đồng/version đang chạy và sẽ chạy có tương thích?
3. Test đầu–cuối, phân quyền, dữ liệu và failure modes đã đạt?
4. Cửa sổ thay đổi và những phê duyệt bắt buộc có hiệu lực?
5. Có dashboard/alert, on-call của cả bên nào cần tham gia?
6. Có cách dừng rollout và khôi phục **mà không làm dữ liệu sai**?
7. Những giới hạn còn lại có được ghi, có người chịu trách nhiệm và người có quyền quyết biết không?

Không gọi một cuộc họp go/no-go là bằng chứng chất lượng. **Bằng chứng đến từ kiểm chứng thực tế**, cuộc họp (nếu cần) chỉ giúp đúng người ra quyết định trên bằng chứng ấy.

## 11. Bảo mật, quyền riêng tư và tuân thủ tại ranh giới nhà cung cấp

### 11.1. Không được giảm kiểm soát chỉ vì nhịp vendor chậm

Trong hệ thống đăng ký khóa học, dữ liệu có thể gồm định danh học viên, lựa chọn khóa, lịch học và lịch sử tham gia. Khi dùng nhà cung cấp bên ngoài, nhóm phải xét:

- Loại dữ liệu nào thực sự cần gửi tới provider.
- Mục đích xử lý, quyền và cơ sở pháp lý/chính sách áp dụng.
- Địa điểm lưu trữ/xử lý dữ liệu và những nghĩa vụ hợp đồng liên quan.
- Thời gian lưu, xóa, export và khả năng truy vết.
- Ai được truy cập logs, sandbox và dashboard.
- Cơ chế cấp, xoay, thu hồi secret/token.
- Cách phát hiện, ứng cứu và thông báo sự cố theo quy định áp dụng.

Không thể kết luận nghĩa vụ pháp lý cụ thể chỉ từ việc vendor nằm ở một quốc gia hoặc dùng cloud. Khi cần, phải tham vấn **người phụ trách pháp lý, bảo mật hoặc bảo vệ dữ liệu** theo bối cảnh thực.

### 11.2. Đưa kiểm soát vào hợp đồng và kiểm chứng sớm

| Rủi ro | Câu hỏi/kiểm chứng cần có |
| --- | --- |
| **Dữ liệu quá mức** | Trường nào cần cho đăng ký? Có thể dùng pseudonymous ID thay vì hồ sơ đầy đủ? |
| **Quyền truy cập sai** | Server kiểm tra token, quyền đọc/ghi và tenant isolation đúng chưa? |
| **Sandbox lộ dữ liệu** | Có dùng dữ liệu giả/được phép, secrets tách môi trường không? |
| **Chuyển đổi schema** | Có kế hoạch bảo toàn tính nhất quán và khả năng truy vết không? |
| **Thay đổi khóa/phiên bản** | Consumer kiểm chứng rotation, expiry, revocation theo contract không? |
| **Xử lý sự cố** | Ai là đầu mối kỹ thuật/bảo mật, thời gian và nghĩa vụ thông báo thực? |
| **Kết thúc hợp đồng** | Dữ liệu, bí mật, log, tài liệu và quyền truy cập được xử lý thế nào? |
| **Subprocessor/đối tác phụ** | Có quyền biết/kiểm soát theo hợp đồng và quy định liên quan không? |

### 11.3. Không đổi an toàn lấy “tăng velocity”

Các cách làm không phù hợp:

- Bỏ xác minh token khi IdP chậm.
- Cấp quyền admin production cho nhà cung cấp để “test nhanh”.
- Copy database có dữ liệu học viên thật lên sandbox chưa được phê duyệt.
- Dùng feature flag để thay kiểm tra quyền ở server.
- Tắt audit logging để giảm độ trễ rồi không còn khả năng điều tra.
- Công bố nguyên nhân sự cố và thông tin cá nhân trước khi được xác minh/cho phép.

Nếu vendor hiện tại không đáp ứng điều kiện an toàn bắt buộc, lựa chọn có thể là **không phát hành khả năng phụ thuộc, thiết kế thay thế an toàn, yêu cầu khắc phục hoặc đánh giá nhà cung cấp khác**. Không phải mọi mục tiêu Sprint đều hợp thức hóa rủi ro.

### 11.4. Bảo mật theo nhịp khác vẫn có thể cải tiến

Ngay cả khi đợt đánh giá bảo mật chính thức chỉ có theo lịch:

- Có thể làm threat modeling cho lát cắt nhỏ từ sớm.
- Đưa chuyên gia an toàn vào refinement khi có thay đổi quan trọng.
- Chạy static analysis, dependency scanning, unit/contract security tests liên tục.
- Chuẩn bị bằng chứng và mô tả phạm vi rõ để giảm vòng bổ sung hồ sơ.
- Tách những thay đổi an toàn thông thường với những thay đổi cần đánh giá đặc biệt theo chính sách.

Kiểm tra tự động **bổ trợ** các bước duyệt bắt buộc, không thay quyền quyết định của chuyên gia có thẩm quyền.

## 12. SLA, SLO, support và khắc phục sự cố trong quan hệ vendor

### 12.1. Đừng nhầm chỉ số dịch vụ với cam kết hợp đồng

- **SLI (Service Level Indicator):** phép đo chất lượng dịch vụ như availability hoặc độ trễ theo một định nghĩa cụ thể.
- **SLO (Service Level Objective):** mục tiêu của một SLI trong một khoảng thời gian.
- **SLA (Service Level Agreement):** thỏa thuận với các nghĩa vụ/hệ quả được xác định.
- **SLE (Service Level Expectation) trong Kanban:** kỳ vọng có tính xác suất về thời gian hoàn tất item; không tự thay SLA.
- **Support response target:** mốc phản hồi hoặc ghi nhận theo hợp đồng/chính sách; không đồng nghĩa mốc giải quyết cuối.

Một provider công bố **SLA availability** không tự cam kết “mọi yêu cầu mở tính năng mới sẽ hoàn thành trong hai Sprint” hoặc “mọi lỗi sẽ khôi phục trong một giờ”. Phải đọc **phạm vi, điều kiện, ngoại lệ, cách tính và hệ quả** thực.

### 12.2. Những mục hỗ trợ cần làm rõ

| Chủ đề | Câu hỏi quan trọng |
| --- | --- |
| **Service hours** | Có hỗ trợ giờ hành chính, 24/7 hay chỉ sự cố nghiêm trọng 24/7? |
| **Severity** | Tiêu chí phân loại ảnh hưởng chung giữa các bên là gì? |
| **Acknowledgement/response** | Khi nào bên nhận xác nhận và khi nào cung cấp phản hồi đầu có ích? |
| **Restoration/resolution** | Khôi phục dịch vụ và sửa nguyên nhân có được tách mốc không? |
| **Escalation** | Khi người hỗ trợ đầu không giải quyết được, đường tiếp theo là gì? |
| **Observability/evidence** | Consumer được xem trạng thái, correlation ID, changelog, logs tới mức nào? |
| **Incidents/privacy** | Ai điều phối, thông báo, bảo toàn bằng chứng và thực hiện nghĩa vụ? |
| **Known limitations** | Rate limits, maintenance windows, quota và lỗi đã biết được công bố ra sao? |
| **Vendor-to-vendor** | Nếu lỗi liên quan hai vendor, ai giữ việc phối hợp tới lúc khôi phục? |
| **End of support** | Phiên bản cũ và hợp đồng cũ còn hỗ trợ đến mốc nào? |

### 12.3. Công thức availability minh họa

Giả sử một SLI được định nghĩa là tỷ lệ phút đủ điều kiện mà dịch vụ trả trạng thái khỏe mạnh trong một khoảng quan sát. Nếu có **43.200 phút** đủ điều kiện và **43.150 phút** đạt:

\[
\text{Availability SLI}
=\frac{43.150}{43.200}\times100\%
\approx99{,}884\%.
\]

Không thể biết kết quả này **đạt hay vi phạm SLA** nếu chưa biết ngưỡng cam kết, loại trừ bảo trì, phương pháp tính và giới hạn của thỏa thuận. Đồng thời, dịch vụ **có uptime tốt vẫn có thể trả dữ liệu đăng ký sai**; cần tín hiệu nghiệp vụ/tính toàn vẹn dữ liệu ngoài availability.

### 12.4. Mức khẩn cấp của incident khác thứ tự yêu cầu tính năng

Một nhà cung cấp có thể xử lý thay đổi tính năng theo kế hoạch hàng tháng nhưng phải ứng cứu lỗi production nghiêm trọng theo quy trình khác. Nhóm cần phân biệt:

| Loại công việc | Đường xử lý |
| --- | --- |
| Nhu cầu tích hợp khả năng mới | Product Backlog, đề nghị thay đổi, kế hoạch vendor/cam kết hợp đồng. |
| Defect chưa gây sự cố đang diễn ra | Triage rủi ro, tái hiện, lịch sửa và hỗ trợ theo thỏa thuận. |
| Incident đang ảnh hưởng giao dịch | Quy trình ứng cứu/khôi phục theo severity và quyền được giao. |
| Quan ngại bảo mật/riêng tư | Kênh ứng cứu chuyên biệt và nghĩa vụ phù hợp, không chờ refinement thường lệ. |
| Cải tiến sau hậu kiểm | Product Backlog/experiment và đầu mối cam kết của các bên. |

Không lấy câu **“vendor chỉ release cuối tháng”** làm lý do không kích hoạt ứng cứu khi dữ liệu đang bị lộ hoặc nghiệp vụ cốt lõi đang gây hại.

### 12.5. Ai giữ bức tranh sự cố liên hệ thống?

Nếu người dùng không đăng ký được vì IdP không phản hồi:

1. **Support của sản phẩm** tiếp nhận và xác minh tác động người dùng.
2. **On-call/incident coordinator** của sản phẩm phân loại sự cố và giữ bức tranh tổng thể.
3. **Developers** kiểm tra consumer logic, fallback, logs và phiên bản.
4. **Vendor support** kiểm tra phần provider trong quyền và phạm vi dịch vụ.
5. **Người có quyền bảo mật/dữ liệu** tham gia nếu có dấu hiệu sai quyền hoặc dữ liệu.
6. **Product Owner** nắm tác động và ưu tiên việc cải tiến sản phẩm sau khôi phục.

Chức năng **incident coordinator** không phải vai trò Scrum bắt buộc. Một tổ chức có thể gộp một số chức năng ở sự cố nhỏ, nhưng không nên để ticket đi lòng vòng giữa vendor và nội bộ mà **không có đầu mối theo dõi kết quả tới người dùng**.

## 13. Giao tiếp bất đồng bộ, nhịp đồng bộ và escalation

### 13.1. Thiết kế giao tiếp cho sự khác biệt nhịp

Không cần tạo một cuộc họp hằng ngày với vendor chỉ vì nhóm Scrum có Daily Scrum. Có thể chia:

- **Async mặc định** cho changelog, câu hỏi nhỏ, hợp đồng đã rõ, kết quả test và thông báo mốc.
- **Đồng bộ ngắn theo vấn đề** cho quyết định nghiệp vụ khó, xung đột hợp đồng hoặc blocker cần nhiều người cùng chốt.
- **Điểm xem xét định kỳ** cho những mốc hợp đồng, rủi ro, kế hoạch phiên bản và cải tiến liên hệ thống.
- **Kênh ứng cứu riêng** cho incident và sự cố bảo mật có mức nghiêm trọng phù hợp.

Điều quan trọng là **thời gian nhận biết thay đổi và khả năng ra quyết định**, không phải số lượng meeting.

### 13.2. Một working agreement hai bên

| Chủ đề | Thỏa thuận gợi ý |
| --- | --- |
| **Đầu mối** | Named owner sản phẩm, kỹ thuật, hỗ trợ và người dự phòng khi cần. |
| **Định dạng yêu cầu** | Hợp đồng/phiên bản, tình huống, kỳ vọng, tác động, mốc cần biết. |
| **Kênh** | Ticket hỗ trợ có truy vết, nơi lưu contract, kênh incident khẩn. |
| **Nhịp** | Mốc xem roadmap/change, cách báo breaking changes và cửa sổ thử. |
| **Phản hồi** | Phân biệt acknowledgment, câu trả lời có ích, quyết định và deliverable. |
| **Bằng chứng** | Logs an toàn, correlation ID, kết quả contract/integration tests. |
| **Quyền** | Ai được phê duyệt thay đổi, release, xem dữ liệu hoặc truy cập môi trường. |
| **Escalation** | Khi nào và vì điều kiện gì cần nâng cấp kỹ thuật hoặc thẩm quyền. |
| **Điều chỉnh** | Khi dependency age hoặc lỗi lặp tăng, cách xem lại thỏa thuận. |

Một working agreement **không tự sửa SLA hoặc hợp đồng có hiệu lực**; những điều vượt quyền phải chuyển qua người có thẩm quyền.

### 13.3. Một thông điệp yêu cầu vendor có thể hành động

Thay vì:

> “Nhờ vendor hỗ trợ API sớm vì nhóm đang bị trễ Sprint.”

hãy cung cấp:

> “Để hoàn tất kiểm thử hành trình tự đăng ký khóa miễn phí, chúng tôi cần xác nhận contract trả trạng thái của API Identity phiên bản đang hỗ trợ, đặc biệt trường hợp token hết hạn và thiếu claim. Hiện contract tests cho hai tình huống chưa thể chạy trên sandbox. Điều này chặn bằng chứng phân quyền của Increment, không phải chỉ chặn một task UI. Nhờ xác nhận schema/test accounts hoặc lịch cung cấp bằng chứng trước mốc ra quyết định phát hành; nếu chưa đáp ứng, chúng tôi sẽ giữ lát cắt hiện tại trên hợp đồng đã được kiểm chứng và tách phần nâng cấp.”

Yêu cầu này mô tả **đầu ra, tác động, quyền được đề nghị và phương án thay thế**. Nó không giả định vendor phải coi Sprint Goal của nhóm là ưu tiên số một.

### 13.4. Escalation chức năng khác escalation thẩm quyền

| Loại | Khi nào dùng | Ví dụ |
| --- | --- | --- |
| **Chuyên môn** | Cần người hiểu API, security, runtime hoặc dữ liệu. | Kỹ sư provider giải thích lỗi signature validation. |
| **Quyền quyết định** | Cần duyệt thay đổi chi phí, production hoặc rủi ro vượt thẩm quyền. | Hợp đồng cần mua thêm sandbox hoặc change request. |
| **Điều phối ưu tiên** | Hai sản phẩm cùng cần một năng lực vendor hữu hạn. | Sắp thứ tự theo tác động và nghĩa vụ đã xác nhận. |
| **Ứng cứu sự cố** | Dịch vụ đang gây tác động cần khôi phục. | Vendor incident support theo severity và hợp đồng. |

Escalation tốt phải nói rõ: **quyết định cần có, phương án, tác động của trì hoãn, bằng chứng và người có quyền**. Thêm nhiều quản lý vào email nhưng không có câu hỏi quyết định thường chỉ làm chậm thêm.

### 13.5. Bàn giao tri thức giữa các nhịp

Vì vendor có thể chỉ họp vào một số ngày, thông tin cần **tự đủ ngữ cảnh**:

- Hành vi người dùng và lý do yêu cầu.
- Hợp đồng/phiên bản chính xác.
- Dữ liệu thử và các bước tái hiện an toàn.
- Điều đã kiểm tra, kết quả và điều còn chưa biết.
- Rủi ro, mốc cần biết, lựa chọn thay thế.
- Quyết định cuối cùng và nơi lưu bản cập nhật.

Một **Decision Log** hoặc ADR ngắn có ích nếu nhiều consumer sẽ cần hiểu tại sao một contract được giữ lại. Không tạo tài liệu nặng chỉ để chứng minh “đã giao tiếp”.

## 14. Áp dụng Scrum khi phụ thuộc vào nhà cung cấp ngoài Sprint

### 14.1. Scrum Team không điều khiển được Sprint của vendor

Trong Scrum:

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog.
- **Developers** tạo Increment đáp ứng Definition of Done và điều chỉnh Sprint Backlog để đạt Sprint Goal.
- **Scrum Master** hỗ trợ Scrum Team và tổ chức áp dụng Scrum hiệu quả.
- **Sprint Goal** mang lại mục đích thống nhất cho Sprint.
- **Increment** phải có thể sử dụng và đáp ứng DoD; một Sprint có thể tạo nhiều Increment.

Những accountabilities ấy **không tạo quyền tự động** yêu cầu nhà cung cấp đổi lịch hợp đồng, quy trình kỹ thuật hoặc nhân sự. Cần thiết kế **cách làm nội bộ có thể thích ứng** với điều kiện bên ngoài.

### 14.2. Sprint Planning: chọn mục tiêu không phụ thuộc vào một điều kiện mơ hồ

Trước khi chọn PBI phụ thuộc provider:

1. Những phần nào đã có **contract/version sẵn sàng và kiểm chứng được**?
2. Vendor đã xác nhận điều kiện gì, hay mới là dự kiến?
3. Nếu provider trễ, có **lát cắt giá trị an toàn** khác giúp tiến gần Product Goal không?
4. Nhóm cần kiểm chứng tích hợp ở đâu, môi trường nào, ai có quyền cấp?
5. Rủi ro chặn DoD lớn tới đâu; có hợp lý để chọn hạng mục đó trong Sprint không?
6. Có thể dành năng lực **làm rõ hợp đồng** hoặc discovery/spike trước khi cam kết một Increment phụ thuộc?

Một **spike/hoạt động khám phá kỹ thuật** có thể giảm bất định, nhưng không nên gọi nó là **phần giá trị đã phát hành** nếu chỉ tạo thông tin hoặc prototype.

### 14.3. Không nên định nghĩa Sprint Goal là “chờ vendor giao”

Sprint Goal yếu:

> “Hoàn thành tích hợp IdP phiên bản mới ngay khi vendor phát hành.”

Nếu chưa có build, sandbox, hợp đồng hoặc lịch chắc chắn, đội không có đủ quyền kiểm soát để hướng mục tiêu. Một phương án mục tiêu cụ thể hơn, nếu phù hợp Product Goal:

> “Học viên đã đăng nhập qua IdP hiện hành có thể tự đăng ký khóa miễn phí còn chỗ trên bản tích hợp đáp ứng chuẩn chất lượng.”

Phần nâng cấp IdP tương lai có thể được làm rõ/kiểm tra riêng. **Điều này chỉ hợp lệ nếu hợp đồng hiện hành đáp ứng yêu cầu bắt buộc**; không được dùng phiên bản không an toàn chỉ để giữ Sprint Goal.

### 14.4. Daily Scrum và trao đổi vendor

**Daily Scrum** là sự kiện 15 phút dành cho Developers kiểm tra tiến độ hướng Sprint Goal và điều chỉnh Sprint Backlog, không phải cuộc họp báo cáo tình trạng vendor cho quản lý.

Sau Daily Scrum, nhóm có thể:

- Cử người có bối cảnh trao đổi trực tiếp với vendor về contract mismatch.
- Kiểm tra trạng thái một ticket có owner rõ.
- Làm những test không cần chờ hoặc chuyển sang lát cắt khác.
- Gỡ blocker môi trường bằng người có quyền.
- Điều chỉnh kế hoạch trong Sprint khi xuất hiện bằng chứng mới.

**Không cần đợi Sprint Review mới thông báo một lỗi production hay phụ thuộc rủi ro cao.**

### 14.5. Sprint Review và Retrospective xem hai loại kết quả

| Sự kiện | Câu hỏi khi có vendor |
| --- | --- |
| **Sprint Review** | Increment thực sự chạy được tới đâu? Người dùng nhận giá trị gì? Nhà cung cấp thay đổi điều kiện gì? Product Backlog nên được điều chỉnh thế nào? |
| **Sprint Retrospective** | Chờ vendor xuất hiện khi nào? Hợp đồng đã được làm rõ sớm chưa? CI/sandbox/working agreement giúp hay gây tắc? Có thử nghiệm cải tiến nào nên làm? |

Thay đổi **định dạng họp** không tự giảm phụ thuộc. Retrospective có ích khi tạo được một hành động kiểm chứng, ví dụ thêm contract tests, yêu cầu test access từ sớm hoặc chia lát cắt theo version sẵn có.

### 14.6. Một sản phẩm, nhiều Scrum Team và một vendor

Theo Scrum Guide 2020, nếu nhiều Scrum Team cùng làm trên **một sản phẩm**, họ chia sẻ **một Product Goal, một Product Backlog, một Product Owner và cùng Definition of Done**. Đối tác có thể chỉ giao một subsystem trong sản phẩm ấy; không vì thế mà mỗi nhóm tự đặt chuẩn Done riêng rồi cộng các phần cục bộ.

Ngược lại, nếu vendor vận hành **sản phẩm SaaS riêng** phục vụ nhiều khách hàng, họ có thể có mục tiêu và cách quản trị sản phẩm khác. Đội consumer phải phối hợp qua hợp đồng, không mặc nhiên đưa toàn bộ backlog vendor vào Product Backlog của mình.

## 15. Áp dụng Kanban để quản lý hàng đợi và mức bất định

### 15.1. Hiển thị công việc đang chờ vendor ngay trong workflow

Một luồng hỗ trợ tích hợp có thể là:

~~~mermaid
flowchart LR
    A["Làm rõ nhu cầu"] --> B["Contract / ready"]
    B --> C["Phát triển consumer"]
    C --> D["Đợi vendor / kiểm chứng provider"]
    D --> E["Tích hợp và xác minh"]
    E --> F["Done theo policy"]
    D -. "Hợp đồng không phù hợp" .-> B
    E -. "Lỗi tích hợp" .-> C
~~~

Điều quan trọng là **Definition of Workflow (DoW)** và chính sách của nhóm: Started/Finished ở đâu, WIP được đếm thế nào, blocked nghĩa gì, ai cập nhật, có ngoại lệ khẩn ra sao.

Nếu một PBI đã Started nhưng đang chờ vendor, nó **vẫn là WIP** theo workflow ấy; chuyển nó sang bảng khác hoặc ẩn đi để báo cáo “có ít việc dở” chỉ che vấn đề.

### 15.2. Các metrics giúp cải tiến

| Metric | Ý nghĩa trong phụ thuộc vendor |
| --- | --- |
| **WIP** | Số hạng mục đã bắt đầu nhưng chưa hoàn tất; phát hiện quá nhiều việc chờ đồng thời. |
| **Cycle time** | Thời gian từ Started tới Finished của item đã hoàn tất, tính cả những giai đoạn chờ theo policy. |
| **Work item age** | Thời gian item đang dở tới hiện tại; hữu ích khi vendor delay tạo item rất già. |
| **Throughput** | Số item Finished mỗi khoảng thời gian theo loại việc và quy tắc nhất quán. |
| **Blocked time** | Thời gian một item bị chặn theo điều kiện đã được xác nhận. |
| **Dependency age** | Tuổi của một yêu cầu/điều kiện vendor chưa được đáp ứng theo mốc thống nhất. |

Nếu bắt đầu đo cycle time từ lúc vendor đã giao và loại hoàn toàn **thời gian chờ vendor** thì nhóm có thể báo tốc độ coding rất tốt, trong khi **thời gian khách hàng chờ giá trị không giảm**. Cần đo ranh giới đầu–cuối phù hợp mục đích.

### 15.3. Hướng quản lý WIP khi có vendor delay

Khi nhiều thẻ “đợi vendor”:

1. Kiểm tra có bị chặn thật hay chỉ chưa có người làm tiếp.
2. Chọn item nào có rủi ro/hậu quả lớn, cần escalation.
3. Xem việc có thể hoàn tất **một lát cắt độc lập** hoặc test hợp đồng trước không.
4. Giảm mở việc mới nếu WIP đã cao và nhóm còn khả năng giúp gỡ blocker.
5. Không biến giới hạn WIP thành lý do trì hoãn ứng cứu sự cố.
6. Duy trì item đang chờ minh bạch, không reset tuổi khi chuyển nhóm.

Kanban có thể hỗ trợ Scrum như một cách quản lý flow; **Kanban không bắt buộc phải dùng Sprint**, cũng không tự yêu cầu Scrum Master hoặc Product Owner.

### 15.4. SLE khác SLA của vendor

**Service Level Expectation (SLE)** trong Kanban là kỳ vọng thời gian hoàn tất item với xác suất theo dữ liệu workflow. Nó **không tự là SLA nhà cung cấp**.

Ví dụ minh họa: nhóm nhận thấy phần lớn PBI tích hợp với vendor hiện hành xong trong một khoảng ngày nhất định khi sandbox sẵn sàng. SLE này có thể dùng để xem item có nguy cơ chậm, nhưng **không hứa tất cả PBI sẽ đúng một mốc cứng** và không tự buộc provider giao trong khoảng đó.

Nếu vendor đổi lịch hoặc loại công việc tăng độ phức tạp, dữ liệu nền cần được phân loại và xem lại; đừng giữ dự báo lạc quan như một chân lý.

## 16. XP, CI và engineering practices giúp hai nhịp tương thích hơn

### 16.1. Nhóm Agile nên nhận phản hồi nhanh trong phần mình kiểm soát

Một nhà cung cấp có thể không đưa bản mới mỗi ngày, nhưng consumer vẫn có thể:

- Làm thay đổi nhỏ, tích hợp vào mainline thường xuyên khi an toàn.
- Chạy unit tests và contract tests theo mỗi thay đổi.
- Tách logic nghiệp vụ khỏi API vendor qua adapter.
- Giữ test regression cho phiên bản provider đang dùng.
- Kiểm tra code review/security và cấu hình tự động.
- Đánh dấu chính xác những kiểm chứng đang đợi bản provider thật.

Đây là các thực hành liên quan **Extreme Programming (XP)** như CI, TDD, refactoring và thay đổi nhỏ. Chúng giúp giảm chi phí tích hợp muộn nhưng **không thể tự tạo hợp đồng mới mà vendor chưa cung cấp**.

### 16.2. Red–Green–Refactor ở phạm vi hợp đồng

Một vòng TDD tham khảo:

1. Viết một test thể hiện consumer xử lý **token hết hạn** đúng cách.
2. Test thất bại vì thiếu logic từ chối/hướng dẫn lại.
3. Sửa mã đủ đáp ứng hành vi.
4. Refactor adapter trong khi giữ test xanh.

Sau đó vẫn cần test bản tích hợp với IdP thực. Unit test xanh từ stub không chứng minh issuer/audience validation hoặc cách vendor xoay khóa đúng trong môi trường mục tiêu.

### 16.3. Thay đổi nhỏ làm giảm batch size tích hợp

Khi vendor chỉ có cửa sổ test một lần mỗi tuần, đừng đợi đến cửa sổ đó mới ghép **toàn bộ mã đã viết một tháng**. Có thể:

- Chốt contract và build nhỏ thường xuyên.
- Chạy kiểm thử consumer qua mock và provider compatibility checks sớm.
- Chuẩn bị danh sách test case ưu tiên theo rủi ro.
- Giữ thay đổi tương thích với version vendor hiện hành.
- Dùng cửa sổ có hạn để kiểm chứng những giả thuyết **chỉ bản thật mới kiểm tra được**.
- Ghi kết quả và lỗi ngay để vendor có bằng chứng tái hiện.

Như vậy, nhịp kiểm chứng bên ngoài có thể chậm nhưng **lượng vấn đề tích tụ trước mỗi đợt** được giảm.

### 16.4. Không dùng CI xanh để che tích hợp chưa được kiểm chứng

Một pipeline có thể cần tách:

| Kết quả | Ý nghĩa trung thực |
| --- | --- |
| **Consumer unit/contract checks: PASS** | Code nội bộ và kỳ vọng hợp đồng trong môi trường kiểm tra đạt. |
| **Vendor sandbox checks: NOT RUN** | Chưa có bằng chứng từ sandbox; không được coi là PASS. |
| **End-to-end integration: BLOCKED** | Bản tích hợp chưa đáp ứng điều kiện cần cho Done nếu đây là kiểm tra bắt buộc. |
| **Security/access checks: PASS hoặc FAIL** | Đánh giá theo phạm vi thực tế; FAIL phải được xử lý. |
| **Release readiness: PENDING** | Chưa đến thời điểm hoặc chưa đủ điều kiện phát hành. |

Không đổi tên các job chưa chạy thành “success” cho đẹp dashboard. **Minh bạch điều chưa được xác minh** là một phần của chất lượng Agile.

## 17. Tình huống xuyên suốt: nhóm học trực tuyến phối hợp hai nhà cung cấp

### 17.1. Bối cảnh giả định

Một tổ chức phát triển tính năng **đăng ký khóa miễn phí** cho nền tảng học trực tuyến. Có:

- **Scrum Team sản phẩm:** sở hữu hành trình web, dữ liệu đăng ký và điều kiện hoàn tất.
- **Nhà cung cấp Identity (IdP):** cung cấp xác thực/claims, thông báo roadmap theo đợt và sandbox giới hạn.
- **Nhà cung cấp Notifications:** cung cấp dịch vụ email xác nhận với API hiện hành; thay event schema theo lịch định kỳ.
- **Bộ phận hỗ trợ/vận hành:** hỗ trợ người học, giám sát, ứng cứu lỗi tích hợp theo thẩm quyền.

Trong ví dụ này **email chỉ là tiện ích cải tiến**, còn học viên có thể tra trạng thái đăng ký chính xác trên giao diện. Nếu một sản phẩm thật có yêu cầu bắt buộc phải gửi email thì phải điều chỉnh phạm vi và DoD theo sự thật, không tự áp dụng giả định này.

### 17.2. Mục tiêu và điều kiện bất biến

Product Goal được diễn đạt:

> Học viên đủ điều kiện có thể tự đăng ký lớp còn chỗ và xác minh trạng thái thật, ngay cả khi có yêu cầu lặp hoặc lỗi mạng thông thường.

Các kiểm soát cần giữ:

1. Có xác thực hợp lệ và phân quyền phù hợp.
2. Không tạo đăng ký hiệu lực trùng cho một học viên/khóa theo quy tắc.
3. Không xác nhận vượt sức chứa.
4. Người dùng chỉ đọc dữ liệu đăng ký họ có quyền.
5. Trạng thái xác nhận gắn với dữ liệu đã lưu thật.
6. Nếu dịch vụ phụ thuộc không sẵn sàng, không báo thành công giả.
7. Mọi kiểm thử bắt buộc và DoD được đáp ứng trước khi gọi Increment Done.

### 17.3. Ba phụ thuộc khác bản chất

| ID | Phụ thuộc | Nhịp vendor | Đối sách chính |
| --- | --- | --- | --- |
| **V-01** | Xác minh claims từ IdP hiện hành. | API đang hỗ trợ; thay phiên bản mới theo quý. | Dùng hợp đồng ổn định, contract/auth tests và adapter; không đợi giao diện mới nếu không cần. |
| **V-02** | Sandbox thử token invalid/expiry. | Môi trường được cấp theo lịch/giới hạn. | Đặt lịch sớm, dùng fixture/mock cho phần consumer, dành sandbox cho kiểm chứng thật. |
| **V-03** | Email xác nhận qua Notifications mới. | Change request theo đợt. | Nếu email chưa bắt buộc, tách PBI cải tiến; nếu bắt buộc phải có thì quản lý như điều kiện Done. |

Đây là một ví dụ **màu sắc tổ chức**, không phải danh sách nhà cung cấp hay lịch thực có trong dự án nào.

### 17.4. Nhóm tránh tạo phụ thuộc không cần thiết

Thay vì đặt Sprint Goal “đăng ký + IdP phiên bản mới + email schema mới”, Product Owner và Developers cân nhắc:

- Hợp đồng IdP hiện tại có an toàn và đáp ứng định danh/claims cần thiết không?
- Nếu có, một **lát cắt tự đăng ký + xem trạng thái** đã tạo giá trị độc lập chưa?
- Email mang giá trị gì và có bắt buộc trước khi dùng không?
- Những test nào chỉ cần sandbox thật và đã được đặt lịch chưa?
- Có rủi ro thay đổi phiên bản IdP sẽ làm luồng đang hoạt động bị hỏng không?

Cách này giảm scope coupling **theo giá trị**, không phải cố né mọi sự phối hợp.

### 17.5. Sơ đồ chiến lược hai nhịp

~~~mermaid
flowchart TD
    A["Product Goal: đăng ký đáng tin cậy"] --> B{"Hợp đồng IdP hiện hành đủ và an toàn?"}
    B -- "Có" --> C["Tích hợp và kiểm thử lát cắt giá trị hiện tại"]
    B -- "Không" --> D["Phụ thuộc version mới / giải pháp thay thế an toàn"]
    C --> E["Kiểm chứng trên sandbox và bản tích hợp"]
    D --> F["Làm rõ vendor contract, mốc cần, change decision"]
    F --> E
    E --> G{"Đạt DoD, security và data correctness?"}
    G -- "Không" --> H["Sửa, điều chỉnh phạm vi / dừng rollout"]
    H --> E
    G -- "Có" --> I["Có thể release theo chính sách"]
    I --> J["Quan sát người dùng và vận hành"]
    J --> K["Backlog cải tiến / nâng version khi có lợi ích"]
~~~

**Điều kiện “đủ và an toàn” là điều kiện được kiểm chứng**, không phải quyết định theo cảm tính. Nếu hợp đồng hiện tại sắp end-of-support hoặc chứa lỗi an toàn nghiêm trọng, không được tiếp tục sử dụng chỉ vì ít phụ thuộc hơn.

### 17.6. Điểm kiểm chứng trên hành trình học viên

| Bước | Bằng chứng | Ai có thể cần phối hợp |
| --- | --- | --- |
| Học viên xác thực | Token hợp lệ được xác minh theo contract và quyền. | Developers, IdP, bảo mật. |
| Học viên chọn khóa còn chỗ | Dữ liệu khóa và trạng thái đủ mới/đúng theo nghiệp vụ. | Developers/nhóm dữ liệu. |
| Gửi đăng ký | Transaction, unique constraints/idempotency và concurrency tests. | Developers, database/platform. |
| Xem xác nhận | Dữ liệu cuối chính xác, không hiển thị thành công giả. | Web + API/test. |
| Mất phản hồi mạng | Có đường tra trạng thái/retry an toàn. | Web + API + support. |
| Vendor outage | Failure-mode response an toàn, không tự cấp quyền. | Consumer on-call + vendor support. |
| Thông báo email (nếu có) | Event và nội dung đúng người, không gửi trùng bất hợp lý. | Notifications vendor, quyền dữ liệu. |

Một bài kiểm thử của riêng IdP không xác minh transaction enrollment. **Bằng chứng phải phù hợp ranh giới thực của hành vi**.

## 18. Tình huống A: sandbox của nhà cung cấp đến trễ

### 18.1. Timeline giả định

Nhóm đã làm unit/contract tests cho luồng xác thực nhưng cần chạy bộ test trên sandbox IdP. Ban đầu vendor dự kiến cấp môi trường trong tuần thứ hai; sau đó thông báo lịch cấp bị dời.

| Mốc minh họa | Sự kiện | Điều đã biết và chưa biết |
| --- | --- | --- |
| **Ngày 1** | Product Owner làm rõ PBI đăng ký, Developers xác định contract và test auth. | Biết những behavior cần test; chưa có sandbox v2. |
| **Ngày 3** | Vendor xác nhận API v1 vẫn được hỗ trợ, v2 đang chờ phát hành. | Cần kiểm tra v1 có đáp ứng đầy đủ và an toàn không. |
| **Ngày 5** | Consumer unit/contract tests cho v1 đạt. | Có bằng chứng nội bộ, chưa phải chứng cứ tích hợp v2. |
| **Ngày 7** | Vendor thông báo sandbox v2 dời một đợt. | Không có bằng chứng cho phiên bản v2 theo kế hoạch cũ. |
| **Ngày 8** | Developers và PO xem lát cắt đang định giao. | Có thể giao với v1 nếu đáp ứng DoD/điều kiện bắt buộc; nếu không thì phải thích ứng. |
| **Ngày 10** | Nhóm chạy integration tests với hợp đồng đang hỗ trợ; kiểm chứng dữ liệu. | Chỉ những phần đạt thật mới được xem xét Done. |
| **Mốc tiếp theo** | Vendor cung cấp v2/sandbox khi sẵn sàng. | Chạy compatibility/security tests trước khi nâng phiên bản. |

Tất cả dữ liệu thời gian ở bảng là **giả định**. Việc một nhà cung cấp thực tế có hỗ trợ v1 tới ngày nào hoặc có sandbox ra sao phải dựa trên thỏa thuận đã xác nhận.

### 18.2. Bốn lựa chọn, không phải một lựa chọn duy nhất “chờ”

| Lựa chọn | Khi có thể hợp lý | Điều kiện không được bỏ |
| --- | --- | --- |
| **Dùng hợp đồng hiện hành** | v1 đủ chức năng và còn đáp ứng an toàn/chuẩn hỗ trợ. | Test tích hợp, quyền và dữ liệu đúng. |
| **Tách phần phụ thuộc v2** | v2 chỉ bổ sung trải nghiệm mới chưa bắt buộc. | Phạm vi Product Backlog/acceptance criteria minh bạch. |
| **Đổi thứ tự công việc** | v2 thực sự bắt buộc nhưng có PBI giá trị khác không bị chặn. | Product Owner/Developers điều chỉnh theo trách nhiệm Scrum. |
| **Hoãn phát hành phụ thuộc** | Không có cách tích hợp an toàn thay thế hoặc thiếu chứng cứ bắt buộc. | Truyền thông rủi ro, cập nhật dự báo và không khai báo Done giả. |

Không nên “lách sandbox” bằng cách gọi production với tài khoản thật hoặc cấp quyền ngoài quy trình. Đó là **rủi ro riêng**, không phải cách Agile xử lý phụ thuộc.

### 18.3. Bản ghi quyết định minh họa

~~~text
Quyết định: Tiếp tục lát cắt đăng ký với IdP v1 nếu mọi kiểm chứng đạt
Căn cứ: Vendor xác nhận v1 hiện vẫn được hỗ trợ theo phạm vi cần dùng
Chưa được xác minh: Hành vi/claims của v2, vì sandbox chưa sẵn sàng
Phạm vi hiện tại: Xác thực qua v1 và tự đăng ký khóa miễn phí
Phạm vi tách ra: Trải nghiệm đăng nhập mới của v2
Điều kiện bắt buộc: Không giảm authn/authz, DoD, dữ liệu và monitoring
Người quyết sản phẩm: Product Owner
Người quyết release/security: theo thẩm quyền hiện hành
Theo dõi: Khi v2 xuất hiện, mở compatibility tests và quyết định nâng
~~~

Trong hệ thống thật, nếu v1 **không còn đủ an toàn** hoặc là phiên bản đã end-of-support, quyết định phải khác; không được sao chép mẫu một cách máy móc.

### 18.4. Thông điệp tới stakeholder

Một bản cập nhật tốt phân biệt:

- **Đã xác nhận:** contract tests của v1 và trạng thái hợp đồng hiện hành.
- **Chưa xác nhận:** sandbox và behavior v2.
- **Tác động:** lát cắt nào bị chặn, lát cắt nào còn có thể đạt DoD.
- **Quyết định:** có điều chỉnh phạm vi, dự báo release hoặc giữ kế hoạch không.
- **Rủi ro và thời điểm xem lại:** mốc cụ thể khi có thông tin mới.

Không nên báo “đội đã hoàn thành 95%” khi 5% còn lại chứa **khả năng xác thực và phân quyền chưa kiểm chứng**.

## 19. Tình huống B: nhà cung cấp đổi hợp đồng API bất ngờ

### 19.1. Triệu chứng

Một ngày, provider thông báo thay đổi cách thể hiện claim học viên, thêm trạng thái lỗi mới và chuẩn bị loại bỏ một endpoint cũ. Nhóm đã viết consumer theo hợp đồng hiện tại; nhiều phiên bản ứng dụng đang chạy.

Sai lầm phổ biến là:

- Lập tức sửa mọi code và bỏ test cũ.
- Giả định phiên bản mới luôn tương thích vì “chỉ thêm field”.
- Bắt toàn bộ nhóm deploy cùng giờ với vendor.
- Không kiểm tra người dùng chưa cập nhật client.
- Xóa phiên bản cũ trước khi biết mọi consumer đã chuyển.

### 19.2. Phân tích tác động theo consumer

| Câu hỏi | Cần xác minh |
| --- | --- |
| Provider đổi field/enum nào? | Diff hợp đồng, behavior và version có hiệu lực. |
| Consumer nào đang dùng? | Web backend, mobile, batch, support tools, hệ thống khác. |
| Có breaking change thật không? | Parser, validation, business mapping và quyền. |
| Có thể chạy song song version không? | Phạm vi hỗ trợ, routing, endpoint hoặc adapter. |
| Những test nào sẽ phát hiện hỏng? | Contract, integration, authn/authz, E2E. |
| Nếu nâng cấp thất bại, khôi phục thế nào? | Rollback/forward fix, tương thích dữ liệu và phiên làm việc. |
| Có phải thay đổi khẩn để vá an toàn? | Chính sách khẩn, thẩm quyền và nghĩa vụ thông báo. |

### 19.3. Bước chuyển đổi tương thích

Một phương án tùy contract:

1. Giữ parser chấp nhận những giá trị hợp lệ đang được hỗ trợ theo chính sách.
2. Thêm adapter hỗ trợ cách biểu diễn mới mà không phá đường cũ.
3. Bổ sung test cho cả v1/v2 và những lỗi quan trọng.
4. Tích hợp với sandbox/bản provider được phép, kiểm chứng quyền.
5. Mở đường mới có kiểm soát, theo dõi lỗi và phạm vi người dùng.
6. Chỉ gỡ phần cũ khi có bằng chứng consumer đã chuyển và đúng hạn hỗ trợ.

**Không cố giữ một phiên bản lỗi bảo mật nghiêm trọng để tránh thay đổi**. Khi đó phải lập kế hoạch ứng cứu/khắc phục nhanh nhưng vẫn giữ khả năng kiểm chứng và bảo vệ dữ liệu.

### 19.4. Đường dây trách nhiệm khi contract phá

Nếu vendor có thay đổi ngoài cam kết tương thích, nhóm cần **bằng chứng cụ thể** để làm việc theo hợp đồng thay vì chỉ cáo buộc:

- Hợp đồng/phiên bản đã cam kết.
- Request/response thực tế đã loại dữ liệu nhạy cảm.
- Test chứng minh sai khác.
- Phạm vi người dùng bị ảnh hưởng.
- Các thời điểm công bố, test và deploy đã xác nhận.
- Đề xuất mitigation và quyết định cần vendor đưa ra.

Nếu lỗi do consumer hiểu nhầm hợp đồng hoặc tự phụ thuộc field không được bảo đảm, tổ chức cũng cần ghi nhận trách nhiệm phần mình và cải tiến adapter/tests.

## 20. Tình huống C: sự cố production khi cả hai bên cùng vận hành

### 20.1. Đừng bắt người dùng điều tra ranh giới trách nhiệm

Học viên chỉ biết **không đăng ký được**. Họ không cần biết token được ký ở vendor hay quyền được kiểm tra ở ứng dụng. Khi dịch vụ đang gây tác động, mục tiêu đầu tiên là **bảo vệ người dùng và khôi phục trạng thái chấp nhận được**, không phải tranh luận lỗi thuộc nhóm nào.

Luồng ứng cứu minh họa:

~~~mermaid
flowchart TD
    A["Người dùng báo lỗi / alert"] --> B["Phân loại tác động và rủi ro"]
    B --> C{"Có incident cần ứng cứu?"}
    C -- "Không" --> D["Support / defect / backlog theo policy"]
    C -- "Có" --> E["Điều phối và bảo vệ người dùng"]
    E --> F["Kiểm tra consumer, provider và các thay đổi gần đây"]
    F --> G["Vendor escalation với bằng chứng an toàn"]
    F --> H["Consumer mitigation / giảm phạm vi an toàn"]
    G --> I["Kiểm chứng trạng thái thật và dữ liệu"]
    H --> I
    I --> J{"Đã ổn định?"}
    J -- "Chưa" --> F
    J -- "Có" --> K["Thông báo, giám sát và hậu kiểm"]
    K --> L["Sửa nguyên nhân, hợp đồng, test và runbook"]
~~~

Nếu có khả năng lộ dữ liệu hoặc sai quyền, dùng kênh ứng cứu bảo mật/riêng tư theo nghĩa vụ áp dụng; không đợi cuộc họp vendor định kỳ.

### 20.2. Khi provider chậm, fallback phải đúng nghiệp vụ

Ví dụ có thể:

- **Dừng thao tác mới** nếu không thể xác thực quyền an toàn.
- **Chỉ xem trạng thái đã có** khi sản phẩm có dữ liệu và quyền hợp lệ cho phép.
- **Thông báo chưa thể xác minh trạng thái**, không nói “thất bại” nếu một request đã có thể commit.
- **Dùng cached data** chỉ với thông tin chấp nhận được độ trễ và có quy tắc, không dùng cache cũ để vượt kiểm tra sức chứa hay quyền.
- **Tạm dừng rollout** một phiên bản tích hợp gây lỗi, không mặc nhiên rollback dữ liệu.

Không được tự tiếp tục đăng ký như thể người dùng đã được xác thực nếu không có bằng chứng quyền hợp lệ.

### 20.3. Phân biệt ba mốc

| Mốc | Nghĩa | Ví dụ |
| --- | --- | --- |
| **Incident acknowledged** | Có người phụ trách nhận tín hiệu và bắt đầu ứng cứu. | On-call nhận alert và đánh giá mức độ. |
| **Service restored** | Dịch vụ/hành vi quan trọng về mức chấp nhận theo bằng chứng. | Đăng ký và xác minh trạng thái hoạt động đúng. |
| **Root cause/permanent fix** | Đã xử lý nguyên nhân được kiểm chứng để giảm tái phát. | Vendor sửa lỗi token rotation và consumer thêm regression tests. |

Ba mốc có thể ở thời điểm khác nhau. **Không lấy việc vendor báo đã khôi phục API làm bằng chứng duy nhất** rằng người học không còn bản ghi đăng ký sai.

### 20.4. Timeline mẫu để phục vụ hậu kiểm

| Giờ giả định (+07:00) | Sự kiện | Bằng chứng/điều chưa biết |
| --- | --- | --- |
| **09:00** | Tỷ lệ lỗi đăng nhập tăng. | Alert consumer; chưa xác định nguyên nhân. |
| **09:06** | Support báo học viên không thể hoàn tất đăng ký. | Có ảnh hưởng người dùng; số lượng còn cần xác minh. |
| **09:10** | On-call lập kênh incident, liên hệ vendor. | Correlation IDs và version được ghi nhận an toàn. |
| **09:18** | Vendor xác nhận một thay đổi cấu hình vừa triển khai. | Có tương quan thời gian, chưa chứng minh nguyên nhân. |
| **09:26** | Các bên thống nhất giảm tác động theo quyền được giao. | Không tắt phân quyền, không tự sửa dữ liệu tùy ý. |
| **09:47** | Kịch bản đăng nhập và đăng ký quan trọng đạt trên bản thực. | Cần tiếp tục kiểm tra dữ liệu bị ảnh hưởng và theo dõi tái phát. |
| **Sau khôi phục** | Hậu kiểm chung và cập nhật backlog. | Chưa kết luận chỉ một bên chịu mọi nguyên nhân. |

Đây là **dữ liệu giả**. Với sự cố thật cần bảo toàn timeline, evidence, quyền truy cập và nghĩa vụ thông báo theo quy trình.

### 20.5. Hậu kiểm liên bên để giảm sự cố lặp lại

Hậu kiểm hiệu quả không dừng ở “vendor lỗi, đề nghị cam kết không lặp lại”. Cần xem:

- Changelog/version đã được công bố thế nào.
- Contract tests có thể phát hiện sớm không.
- Monitoring có phân biệt lỗi provider và consumer không.
- Hợp đồng support/escalation có phù hợp mức ảnh hưởng không.
- Consumer có dùng fallback hoặc retry sai làm tăng tác động không.
- Ai sở hữu hành động phòng ngừa và bằng chứng hoàn tất.

Một **blameless postmortem** có thể tập trung vào các điều kiện hệ thống mà vẫn giữ trách nhiệm hợp đồng, khắc phục dữ liệu và các nghĩa vụ pháp lý thực tế.

## 21. Theo dõi rủi ro nhà cung cấp và điểm quyết định

### 21.1. Risk register không phải danh sách dự đoán mọi tai nạn

Một bản ghi rủi ro hữu ích cho quản trị có:

- **Sự kiện có thể xảy ra** và nguyên nhân/điều kiện.
- **Ảnh hưởng** lên người dùng, dữ liệu, Product Goal, release, hỗ trợ hoặc chi phí.
- **Dấu hiệu sớm** hoặc sự kiện kích hoạt.
- **Khả năng xảy ra và mức hậu quả** với cơ sở đánh giá, không cần giả số chính xác.
- **Owner và thẩm quyền** quyết định.
- **Phương án phòng ngừa, giảm tác động và phục hồi**.
- **Mốc xem lại** và điều kiện chuyển rủi ro thành hành động/incident.

Không dùng một bảng màu đẹp để thay hiểu biết rủi ro. **Một vấn đề bảo mật ít khả năng nhưng hậu quả rất lớn** có thể cần hành động ngay.

### 21.2. Mẫu risk register cho phụ thuộc vendor

| ID | Rủi ro | Tín hiệu sớm | Hậu quả | Giảm/phòng ngừa | Owner |
| --- | --- | --- | --- | --- | --- |
| **R-01** | Vendor thay token claim ngoài dự kiến. | Changelog, test pre-release, contact báo thay đổi. | Sai xác thực hoặc truy cập dữ liệu. | Adapter, contract/security tests, kế hoạch nâng version. | Technical/service owner và vendor counterpart. |
| **R-02** | Sandbox không sẵn đúng mốc kiểm chứng. | Lịch chưa xác nhận, yêu cầu cấp quyền tồn lâu. | Không đủ bằng chứng DoD. | Đặt lịch sớm, test consumer trước, đổi scope khi an toàn. | Integration lead. |
| **R-03** | API provider vượt rate limit. | Metrics 429/latency tăng trong tải thử. | Người học không xác thực/đăng ký được. | Capacity planning, backoff hợp lệ, giảm tải và monitoring. | On-call/engineers. |
| **R-04** | Email xác nhận gửi lặp. | Event replay/test và báo cáo hỗ trợ. | Nhầm lẫn hoặc ảnh hưởng riêng tư. | Idempotency, deduplication, contract event. | Consumer + Notifications vendor. |
| **R-05** | Provider v1 hết hỗ trợ trước ngày nâng cấp. | Deprecation notice chính thức. | Rủi ro an toàn và vận hành. | Migration plan, compatibility checks, quyết định hợp đồng. | Product + technical/vendor owners. |
| **R-06** | Vendor support không có kênh khẩn đủ dùng. | Điều khoản không rõ, diễn tập escalation thất bại. | Khôi phục incident chậm. | Làm rõ hợp đồng, on-call và kế hoạch mitigation nội bộ. | Service/commercial owners. |

Các mức và owner là **minh họa**, không thay cấu trúc trách nhiệm thật. Một rủi ro có thể có owner theo dõi, nhưng cần nhiều bên thực hiện đối sách.

### 21.3. Phân biệt risk, issue, incident và change request

| Loại | Khi nào dùng | Ví dụ |
| --- | --- | --- |
| **Risk** | Chưa xảy ra, có thể ảnh hưởng tương lai. | Vendor dự kiến đổi hợp đồng token. |
| **Issue/blocker** | Điều kiện đang cản công việc. | Chưa có sandbox nên integration test bị chặn. |
| **Incident** | Dịch vụ đang gián đoạn/gây tác động cần ứng cứu. | Học viên không đăng nhập được diện rộng. |
| **Defect** | Hành vi sai so với điều đúng cần kiểm chứng/sửa. | Consumer parser không chấp nhận trạng thái hợp lệ. |
| **Change request** | Đề nghị thay đổi phạm vi/cam kết hợp đồng khi cần. | Bổ sung tùy chỉnh API chưa nằm trong thỏa thuận. |

Một sự kiện có thể đi qua các loại này. Ví dụ rủi ro mất tương thích trở thành issue trong Sprint, rồi gây incident khi release; sau khôi phục tạo defect và change request. **Tên ticket không thay nhiệm vụ xử lý theo mức ảnh hưởng thật**.

### 21.4. Điểm quyết định giúp giảm bất định sớm

Thay vì chờ mốc release rồi hỏi “vendor đã sẵn sàng chưa?”, lập các điểm kiểm tra:

1. **Contract checkpoint:** hành vi, phiên bản và quyền đã được làm rõ?
2. **Test access checkpoint:** môi trường và tài khoản thử có thật và được phép?
3. **Integration checkpoint:** consumer/provider bản thực đã qua test cần thiết?
4. **Security/release checkpoint:** có đủ điều kiện và người quyết định?
5. **Operational checkpoint:** monitoring, runbook, support/escalation sẵn sàng?
6. **Outcome checkpoint:** người dùng có nhận được giá trị như dự kiến?

Đây là **điểm hỏi và quyết định** theo rủi ro, không bắt buộc dựng sáu hội đồng phê duyệt. Các bước có thể tự động hoặc kết hợp khi phù hợp.

## 22. Đo hiệu quả phối hợp với nhà cung cấp

### 22.1. Đo kết quả toàn luồng, không chỉ đếm cuộc họp và ticket

| Nhóm tín hiệu | Metric gợi ý | Câu hỏi thực sự |
| --- | --- | --- |
| **Flow** | Cycle time của PBI phụ thuộc vendor, work item age, WIP, blocked time. | Nhà cung cấp đang làm dòng giá trị chờ ở đâu và trong bao lâu? |
| **Dependency responsiveness** | Thời gian từ yêu cầu đủ điều kiện tới phản hồi có ích hoặc đầu ra kiểm chứng được. | Có những khâu phản hồi/chốt quyết định chậm không? |
| **Integration quality** | Tỷ lệ lỗi hợp đồng, rework vì schema, lần test lại, thời gian từ contract tới tích hợp thật. | Lệch nhịp có gây lỗi tích hợp muộn không? |
| **Release reliability** | Lỗi sau nâng phiên bản, thời gian khôi phục, khả năng rollback/forward fix. | Phần mềm vẫn vận hành an toàn khi version đổi? |
| **Vendor operations** | SLI/SLO/SLA có định nghĩa, tỷ lệ timeout, severity incident. | Dịch vụ cung cấp có đáp ứng kỳ vọng/cam kết thực tế? |
| **User outcome** | Học viên hoàn tất đăng ký, trạng thái sai, số ticket về xác thực/trạng thái. | Hành trình người dùng có tốt hơn không? |
| **Cost/risk** | Chi phí rework, sandbox, change request, tải on-call, rủi ro dữ liệu. | Phương án phối hợp có bền vững và hợp lý không? |
| **Learning** | Bản kiểm chứng/giả thuyết được cập nhật, phụ thuộc lặp được giảm. | Hệ thống học được điều gì để ít chờ hơn? |

Không nên dùng **số email gửi vendor, số cuộc họp, số yêu cầu đã tạo hoặc phần trăm task vendor báo Done** để khẳng định kết quả người dùng đã cải thiện.

### 22.2. Tính blocked time và tỷ lệ chờ

Một PBI có chu kỳ minh họa không chồng lấn:

| Hoạt động | Thời gian |
| --- | ---: |
| Làm rõ và code phần consumer | 2 ngày |
| Chờ vendor trả hợp đồng API | 3 ngày |
| Cập nhật adapter và kiểm chứng cục bộ | 1 ngày |
| Chờ sandbox có thể kiểm thử | 4 ngày |
| Chạy test tích hợp, sửa sai lệch và đạt DoD | 2 ngày |
| **Tổng cycle time** | **12 ngày** |

Nếu chỉ xét hai khoảng chờ trực tiếp và **giả định chúng không chồng lấn**:

\[
\text{Blocked time}=3+4=7\text{ ngày}.
\]

\[
\text{Tỷ lệ chờ minh họa}
=\frac{7}{12}\times100\%
\approx58{,}3\%.
\]

Số liệu này gợi ý rằng giảm hàng đợi và việc đặt lịch sandbox sớm có thể quan trọng hơn việc ép coding từ hai ngày xuống một ngày. Tuy nhiên, trong thực tế có việc làm song song, bối cảnh khác nhau và những khoảng chờ chưa ghi; **phải định nghĩa thời gian theo mốc, không cộng trùng giờ**.

### 22.3. Đọc trước–sau mà không gán nguyên nhân vội

Giả sử nhóm thử **đặt lịch sandbox trước refinement và tự động contract checks**:

| Metric minh họa | Trước thử (4 tuần) | Sau thử (4 tuần) |
| --- | ---: | ---: |
| PBI cùng loại đã Finished | 10 | 11 |
| Cycle time trung vị | 14 ngày | 9 ngày |
| Blocked time trung vị do vendor | 6 ngày | 3 ngày |
| Lỗi integration vì contract mismatch | 5 | 2 |
| Sự cố dữ liệu nghiêm trọng đã ghi nhận | 0 | 0 |

Có tín hiệu cải thiện cycle time, blocked time và mismatch. Nhưng cần hỏi:

- Tập PBI có tương đồng về loại việc, phạm vi, size và độ rủi ro?
- Thay đổi còn liên quan việc vendor bổ sung kỹ sư hoặc hết kỳ nghỉ?
- Cách đo Started/Finished và blocked time có giữ như cũ không?
- Lượng thay đổi vendor và môi trường thử có khác?
- Bốn tuần có đủ để quan sát lỗi hậu phát hành?
- Vendor có phải tăng giờ làm thêm hoặc đẩy hàng đợi sang customer support?

**Tương quan trước–sau không chứng minh nguyên nhân tuyệt đối.** Nếu guardrail dữ liệu bị vi phạm, phải xử lý ngay theo mức nghiêm trọng, không tiếp tục thử chỉ để có cỡ mẫu đẹp.

### 22.4. Đo ranh giới khác nhau cho những câu hỏi khác nhau

Ví dụ:

- **Vendor response time:** từ lúc gửi yêu cầu đủ dữ liệu đến lúc có phản hồi hữu ích theo cách thỏa thuận.
- **Vendor deliverable lead time:** từ lúc điều kiện/chấp nhận phạm vi tới lúc đầu ra kiểm chứng được bàn giao.
- **Consumer integration cycle time:** từ khi nhóm bắt đầu tích hợp đến khi đáp ứng điều kiện Finished.
- **User value lead time:** từ khi một nhu cầu được chọn để đáp ứng đến khi người dùng có khả năng sử dụng theo ranh giới đã định.

Các khoảng này **có thể chồng lấn hoặc bắt đầu khác nhau**. Không cộng tổng mù quáng để dự báo ngày giao, cũng không so vendor với Developers như thể họ chịu cùng phạm vi.

### 22.5. Phản hồi định tính giúp hiểu số liệu

Một cuộc trao đổi có cấu trúc với người trực tiếp làm có thể tìm được:

- Hợp đồng đã đúng nhưng tài khoản sandbox luôn hết hạn.
- Người vendor có chuyên môn nhưng ticket chuyển qua ba cấp helpdesk.
- Consumer gửi câu hỏi thiếu ngữ cảnh phải hỏi lại nhiều lần.
- Cùng một trường JSON có ý nghĩa khác ở hai hệ thống.
- Một mức hỗ trợ hợp đồng không phù hợp giờ người dùng cao điểm.

Những điều này có thể dẫn tới thử nghiệm **working agreement, template ticket, contract testing hoặc đổi kiến trúc**, thay vì mặc định mua thêm dịch vụ.

## 23. Ra quyết định khi vendor không theo kịp nhịp phát triển mong muốn

### 23.1. Cây câu hỏi thực hành

~~~mermaid
flowchart TD
    A["Vendor không cung cấp điều kiện vào mốc kỳ vọng"] --> B{"Điều kiện đó bắt buộc để giao giá trị an toàn?"}
    B -- "Không" --> C["Tách scope / chuyển PBI / dùng capability hiện hành"]
    B -- "Có" --> D{"Có giải pháp khác đáp ứng cùng điều kiện?"}
    D -- "Có" --> E["Đánh giá quyền, rủi ro, chi phí và test"]
    D -- "Không" --> F["Không tuyên bố Done/ready cho phần bị chặn"]
    E --> G{"Giải pháp thay thế đã kiểm chứng đầy đủ?"}
    G -- "Có" --> H["Làm Increment, release theo policy"]
    G -- "Không" --> F
    F --> I["Escalation, thương lượng hoặc đổi kế hoạch"]
    I --> J["Cập nhật Product Backlog/dự báo, thông tin stakeholder"]
    H --> K["Theo dõi outcome và rủi ro"]
    C --> K
~~~

Sơ đồ hướng dẫn tư duy, **không thay quy trình quyết định bắt buộc** khi liên quan dữ liệu, an toàn, hợp đồng hoặc pháp lý.

### 23.2. Giảm phụ thuộc trước khi tăng tầng quản lý

Các lựa chọn thường nên xem trước khi chỉ xin “vendor làm nhanh hơn”:

1. Có thể làm rõ contract sớm hơn và test qua mock/compatibility checks không?
2. Có thể dùng phiên bản hiện tại **còn được hỗ trợ và đáp ứng đầy đủ** không?
3. Có thể tách khả năng giá trị nhỏ hơn để không chờ phần không bắt buộc không?
4. Có thể tạo adapter, tự phục vụ sandbox hoặc giảm release coupling không?
5. Có thể đặt lịch môi trường/test theo mốc cần biết thay vì ngày cuối?
6. Có thể rút bớt các bước phê duyệt **không bắt buộc** bằng tự động hóa có kiểm soát?
7. Nếu không, cần thương lượng điều gì về công suất, hợp đồng hoặc quyền?

Không nên khuyến khích vendor bỏ kiểm thử hoặc làm ngoài giờ liên tục để đáp ứng một Sprint Goal có thể đã được đặt thiếu căn cứ.

### 23.3. Khi nào cần đánh giá thay thế nhà cung cấp?

Đổi vendor có thể là quyết định chiến lược nếu:

- Khả năng bắt buộc không còn được hỗ trợ với chất lượng/an toàn cần thiết.
- Phụ thuộc gây thiệt hại lặp và vendor không có lộ trình hợp lý.
- Chi phí tích hợp, thay đổi, vận hành và rủi ro vượt lợi ích.
- Điều khoản dữ liệu, hỗ trợ hoặc quyền kiểm soát không đáp ứng nhu cầu.
- Khả năng phục hồi và năng lực ứng cứu không phù hợp với tính quan trọng của dịch vụ.

Tuy nhiên, đánh giá phải gồm **total cost of ownership**, migration, hợp đồng, dữ liệu, license, quyền IP, kỹ năng và hiệu ứng chuyển đổi. Một vendor mới chưa chắc giảm phụ thuộc; có thể chỉ thay **một hàng đợi quen thuộc** bằng nhiều rủi ro chưa biết.

### 23.4. Bảng so sánh lựa chọn minh họa

| Lựa chọn | Giá trị sớm | Rủi ro chính | Khi xem xét |
| --- | --- | --- | --- |
| Giữ version hiện hành còn được hỗ trợ | Có thể giao nhanh phần phù hợp | Nợ nâng cấp và mốc end-of-support | Khi chức năng/an toàn đã đáp ứng. |
| Chờ version mới | Có thể đáp ứng nhu cầu mới đầy đủ | Chậm phản hồi và phụ thuộc lịch vendor | Khi version mới là điều kiện bắt buộc. |
| Adapter + hợp đồng tương thích | Giảm sửa code trải rộng | Chi phí bảo trì abstraction/test | Khi contract thay đổi lặp hoặc nhiều consumer. |
| Thuê thêm capacity/test window | Có thể rút hàng đợi thực | Chi phí, quyền và hiệu quả không chắc | Khi bottleneck đúng là công suất/cửa sổ. |
| Dùng dịch vụ thay thế | Có thể giảm rủi ro provider hiện tại | Migration, dữ liệu và hợp đồng mới | Khi đánh giá tổng thể ủng hộ. |
| Bỏ qua test và mở production | Tưởng là nhanh | Sai dữ liệu, an toàn, vi phạm DoD | **Không phải lựa chọn hợp lệ** để giảm phụ thuộc. |

### 23.5. Khi nào nên dừng hoặc hoãn?

Một quyết định **No-go** có thể là hành động quản trị tốt nếu:

- Không có bằng chứng phân quyền hoặc tính đúng đắn bắt buộc.
- Provider chưa có bản tương thích và không có phương án thay thế an toàn.
- Một phiên bản sắp bị loại bỏ không còn đạt điều kiện vận hành.
- Khả năng khôi phục dữ liệu sau migration chưa được đánh giá đúng mức.
- Không có kênh ứng cứu cần thiết cho sản phẩm có hậu quả cao.

Hoãn một khả năng không phải thất bại Agile nếu đó là **quyết định minh bạch dựa trên rủi ro và giá trị**. Nhưng cũng cần học cách giảm phụ thuộc lần sau, thay vì biến No-go thành thủ tục bị động lặp lại.

## 24. Các phản mẫu thường gặp

| Phản mẫu | Hậu quả | Hướng cải thiện |
| --- | --- | --- |
| **Yêu cầu vendor dự Daily Scrum như một điều kiện bắt buộc** | Tốn thời gian và vẫn không có quyền đổi roadmap. | Thiết kế hợp đồng/nhịp giao tiếp phù hợp, trao đổi theo vấn đề. |
| **Mọi thay đổi đều phải chờ bản vendor kế tiếp** | Batch size lớn, thời gian nhận phản hồi dài. | Tách lát cắt, dùng version hiện hành an toàn, adapter và contract checks. |
| **Tin roadmap vendor như ngày chắc chắn** | Hứa giao khi chưa có đầu ra/điều kiện. | Ghi mức chắc chắn, mốc cần biết và phương án khi trễ. |
| **Đợi ngày cuối mới yêu cầu sandbox** | Không đủ thời gian sửa mismatch. | Đặt lịch và kiểm tra quyền test từ refinement. |
| **Mock xanh = tích hợp Done** | Che thiếu kiểm chứng trên provider thật. | Phân biệt tầng test, yêu cầu bằng chứng phù hợp DoD. |
| **Nghiệm thu vendor = sản phẩm đã giao giá trị** | Người dùng chưa thể hoàn tất tác vụ. | Kiểm thử đầu–cuối và quan sát outcome. |
| **Bỏ kiểm soát quyền vì IdP chậm** | Lộ dữ liệu hoặc hành vi trái quyền. | Failure handling an toàn, không tự cấp quyền. |
| **Coi feature flag là phân quyền** | Endpoint vẫn có thể bị gọi trực tiếp. | Authn/authz ở server và test quyền. |
| **Mọi lỗi đều quy cho vendor** | Không phát hiện consumer bugs, fallback hoặc retry sai. | Điều tra theo bằng chứng và trách nhiệm chia sẻ. |
| **Đổi contract nhưng không báo consumer** | Breaking changes đến production. | Versioning, changelog, contract tests, deprecation policy. |
| **Bắt cả hệ thống cùng deploy một phút** | Coupling phát hành, rollback khó. | Thiết kế tương thích và triển khai từng bước. |
| **Giảm CI bằng cách tắt integration test** | Phát hiện muộn và rủi ro tăng. | Phân tầng, chạy song song và giữ kiểm chứng bắt buộc. |
| **Dùng dữ liệu thật trên sandbox tùy tiện** | Rủi ro riêng tư, hợp đồng và bảo mật. | Test data được phép, quyền và lưu vết. |
| **Giảm WIP bằng cách ẩn thẻ chờ vendor** | Metric đẹp giả, mất khả năng phát hiện item già. | Workflow và work item age trung thực. |
| **Mọi ticket là change request tính phí** | Khó phân biệt làm rõ, lỗi và mở rộng phạm vi. | Đối chiếu hợp đồng và bằng chứng, có quy tắc phân loại. |
| **PO tự đồng ý đổi điều khoản thương mại** | Vượt thẩm quyền, rủi ro hợp đồng. | Làm việc với commercial/legal owners. |
| **Chỉ đo số ngày vendor phản hồi** | Không biết chất lượng đầu ra/tác động người dùng. | Kết hợp flow, integration, severity và outcome. |
| **Không phân biệt SLA và SLE** | Hứa sai quyền/nghĩa vụ. | Ghi đúng định nghĩa, nguồn dữ liệu và điều khoản thật. |
| **Escalation chỉ là CC thêm quản lý** | Chậm quyết định, tăng áp lực mà không có phương án. | Nêu lựa chọn, quyền cần, tác động và mốc kiểm chứng. |
| **Release freeze = không thể làm gì** | Mất cơ hội chuẩn bị test/refinement. | Tiếp tục học và tích hợp an toàn trong phạm vi được phép. |
| **Rollback code được coi rollback mọi dữ liệu** | Side effects vẫn tồn tại, có thể sai trạng thái. | Kế hoạch migration/khôi phục dữ liệu thực. |
| **Chỉ ưu tiên đúng lịch vendor, bỏ Product Goal** | Xây thứ sẵn có thay vì thứ có giá trị. | PO ordering theo giá trị và rủi ro, xem lại khi điều kiện đổi. |
| **Đổ lỗi ở hậu kiểm** | Hai bên giấu vấn đề, lặp lại sự cố. | Hậu kiểm dựa trên bằng chứng, vẫn giữ trách nhiệm và nghĩa vụ. |
| **Không có kế hoạch kết thúc hợp đồng** | Bị lock-in về dữ liệu, quyền và tri thức. | Exit plan, export, revocation, migration và kiểm chứng. |

## 25. Lộ trình áp dụng cho một nhóm Agile đang phụ thuộc nhà cung cấp

### Bước 1 — Chọn một hành trình giá trị cụ thể

Ví dụ: **học viên đăng ký khóa miễn phí**. Ghi phạm vi thực, rủi ro không được đánh đổi và Product Goal liên quan. Không bắt đầu bằng danh sách tất cả vendor trong tổ chức nếu nó chưa giúp ra quyết định.

### Bước 2 — Nhìn workflow và nhịp thật của nhà cung cấp

Thu bằng chứng:

- Vendor nhận yêu cầu ở đâu, ai phản hồi, đâu là hợp đồng được hỗ trợ?
- Lịch phát hành/thay đổi, test window và thời gian hỗ trợ theo điều khoản?
- Có những bước duyệt nào là bắt buộc, bước nào do cách làm hiện tại?
- Những PBI nào từng chờ lâu, mắc lỗi tích hợp hoặc phải làm lại?
- Đã có quyền, tài liệu, changelog, sandbox và đường escalation chưa?

Không giả định vendor có Sprint hoặc SLA cụ thể khi chưa được xác nhận.

### Bước 3 — Lập bản đồ phụ thuộc và quyền quyết

Chọn **các phụ thuộc tác động lớn nhất**; với mỗi phụ thuộc ghi:

1. Consumer/provider, owner và người có quyền.
2. Đầu ra hoặc điều kiện **kiểm chứng được**.
3. Hợp đồng/version, lịch và mốc cần biết.
4. Rủi ro tới DoD, người dùng, dữ liệu và chi phí.
5. Cách giảm/né, test, escalation và phương án khôi phục.

Phân biệt **đã được vendor xác nhận** với **đội mình tự suy đoán**.

### Bước 4 — Chọn chiến lược giảm coupling

Kiểm tra lần lượt:

- Có thể giao lát cắt với capability hiện hành đủ an toàn không?
- Contract-first và adapter có giúp tránh sửa nhiều nơi không?
- Có test/mock/sandbox giúp kiểm tra sớm, không đánh tráo bằng chứng không?
- Có thể tự phục vụ môi trường hoặc yêu cầu lặp theo quyền không?
- Có thể thay đổi tương thích để hai bên không phải deploy cùng lúc?
- Có quy trình thương lượng cho điều kiện vendor không thể tự quyết không?

### Bước 5 — Tạo kế hoạch hai nhịp và checkpoint

Chỉ rõ:

- Nhóm Agile có thể học/giao điều gì trong vòng ngắn.
- Những mốc vendor có hoặc chưa có cam kết.
- Lúc nào cần hợp đồng, sandbox, bản thật và quyết định release.
- Điều gì sẽ thay đổi nếu một mốc không đạt.

Không nhất thiết đồng bộ lịch nhưng phải **đồng bộ điều kiện cần và cách kiểm chứng**.

### Bước 6 — Thử một cải tiến nhỏ

Chọn một vấn đề có thể đo, ví dụ:

> “Hầu hết PBI phụ thuộc IdP phải chờ sandbox quá lâu; đặt lịch từ refinement và xây compatibility tests trước sẽ giảm blocked time mà không tăng lỗi tích hợp.”

Thử trong phạm vi nhỏ, ghi baseline, metric chính, guardrail về dữ liệu/quyền và một mốc đánh giá.

### Bước 7 — Đo end-to-end và điều chỉnh

Theo dõi blocked time, cycle time, work item age, lỗi hợp đồng, sự cố và người dùng hoàn tất tác vụ. Nếu chỉ số consumer cải thiện nhưng tải của vendor/support tăng bất hợp lý, cần xem **toàn hệ thống**, không chỉ dashboard riêng nhóm.

### Bước 8 — Chuẩn hóa điều có hiệu quả

Sau thử, nếu có bằng chứng hữu ích:

- Cập nhật mẫu ticket vendor, working agreement và người đầu mối.
- Bổ sung contract/security/integration tests.
- Cập nhật adapter, chính sách version và migration.
- Đưa release readiness/runbook vào công việc thông thường.
- Thương lượng sửa hợp đồng hoặc capacity theo thẩm quyền nếu cần.
- Đặt mốc xem lại khi vendor đổi phiên bản hoặc Product Goal đổi.

Một thử nghiệm không cải thiện vẫn có giá trị nếu giúp bác bỏ giả thuyết và dừng thủ tục vô ích; **không được biến thử nghiệm gây hại cho người dùng thành chuyện chấp nhận được chỉ vì muốn học nhanh**.

## 26. Bài tập thực hành và gợi ý lời giải

### Bài tập 1 — Phân loại các loại nhịp

Một nhóm làm Sprint hai tuần. Các đối tác có điều kiện:

1. IdP chỉ công bố tính năng mới theo quý nhưng API hiện hành hoạt động 24/7.
2. Nhóm vận hành đối tác chỉ duyệt cấu hình production vào ngày đã đặt lịch.
3. Nhà cung cấp email nhận change request mỗi tháng.
4. Bộ phận an toàn cần duyệt kiểu xử lý dữ liệu mới theo quy định.
5. Vendor hỗ trợ sự cố nghiêm trọng 24/7, còn yêu cầu tính năng thông thường theo giờ làm việc.

**Yêu cầu:** phân biệt **development, release/deploy, contract/change, compliance và support cadence**. Tình huống nào không thể giải quyết bằng cách yêu cầu đối tác “tham gia Daily Scrum”?

**Đáp án gợi ý:** (1) chủ yếu là nhịp phát triển/phiên bản; (2) là lịch vận hành/deploy; (3) là nhịp thay đổi thương mại; (4) là kiểm soát an toàn/pháp lý; (5) là các nhịp hỗ trợ theo mức công việc. Cả năm không tự biến mất khi họp mỗi ngày; cần hợp đồng, chứng cứ, quyền và cách giảm coupling phù hợp.

### Bài tập 2 — Tách điều kiện bắt buộc và mong muốn

Nhóm muốn tự đăng ký khóa miễn phí. IdP hiện hành có xác thực và claims cần thiết, còn phiên bản dự kiến phát hành sau hai tháng thêm giao diện đăng nhập đẹp hơn. Mọi kiểm chứng an toàn hiện hành đạt. Một người đề xuất hoãn tất cả tính năng đăng ký tới khi vendor giao bản mới.

**Yêu cầu:** đề xuất tối thiểu hai lát cắt có giá trị, nói điều gì cần kiểm chứng trước khi chọn.

**Gợi ý:** có thể giao hành trình đăng ký dùng IdP đang được hỗ trợ nếu kiểm chứng quyền, dữ liệu, DoD đạt; sau đó thử trải nghiệm đăng nhập mới như PBI cải tiến. Nếu bản mới sửa một yêu cầu an toàn bắt buộc hoặc v1 sắp hết hỗ trợ, không dùng quyết định trên như lối tắt. Phải xác minh phiên bản, quyền và phạm vi thật.

### Bài tập 3 — Phân biệt vendor acceptance và Increment Done

Vendor giao API xác thực có unit tests xanh và biên bản nghiệm thu. Nhóm Web chưa chạy integration test trên token thật; khi gọi API tra đăng ký, server chưa có kiểm tra người dùng chỉ đọc hồ sơ của mình.

**Câu hỏi:**

1. Deliverable vendor có thể đã đáp ứng hợp đồng không?
2. Increment đăng ký của sản phẩm đã Done chưa?
3. Những bằng chứng bổ sung nào cần có?
4. Ai cần tham gia?

**Gợi ý:** nghiệm thu vendor là một quyết định theo điều khoản được áp dụng, có thể có hiệu lực; nhưng Increment sản phẩm **chưa đáp ứng DoD an toàn** nếu thiếu tích hợp và phân quyền. Cần contract/integration/security tests, hành trình người dùng và xác nhận đúng dữ liệu. Developers, người kiểm thử, bảo mật và vendor counterpart phối hợp tùy phạm vi.

### Bài tập 4 — Viết dependency register có thể hành động

Vendor thông báo sandbox v2 có thể được cấp vào tuần sau, nhưng chưa xác nhận. PBI tra trạng thái đăng ký phụ thuộc test token expiry trên bản v2 nếu nhóm chọn nâng phiên bản.

**Yêu cầu:** viết thẻ có consumer/provider, điều kiện, mốc cần biết, owner, rủi ro, phương án thay thế và điều kiện kiểm chứng.

**Gợi ý bản ghi:**

~~~text
ID: V-TEST-01
Consumer: Nhóm đăng ký khóa học
Provider: Nhà cung cấp IdP
Cần: sandbox v2 và test account kiểm chứng token expiry
Trạng thái: dự kiến, chưa xác nhận lịch/cấp quyền
Mốc cần biết: trước quyết định chọn PBI nâng v2 vào Sprint
Ảnh hưởng: thiếu bằng chứng DoD nếu PBI phụ thuộc v2
Owner: integration lead và vendor technical contact
Giảm phụ thuộc: tiếp tục với v1 an toàn nếu phạm vi cho phép;
                kiểm thử consumer mock trước, không coi mock là E2E
Kết thúc: test expiry/authn/authz đạt với bản provider phù hợp
~~~

### Bài tập 5 — Soạn một thông điệp vendor request tốt

Nhóm chỉ có ticket **“Vendor giúp API nhanh nhé, chúng tôi trễ rồi”**.

**Yêu cầu:** viết lại dưới 150 từ, nêu:

- Mục tiêu nghiệp vụ liên quan.
- Contract và phiên bản.
- Kịch bản bị chặn và bằng chứng.
- Điều kiện cần vendor cung cấp.
- Mốc cần biết và phương án nếu chưa có.
- Không tiết lộ bí mật hoặc dữ liệu cá nhân.

**Gợi ý:** mô tả endpoint/test cần được chạy, correlation ID đã ẩn thông tin, ảnh hưởng tới điều kiện Done và lựa chọn dùng hợp đồng hiện hành nếu hợp lệ. Không dùng từ “urgent” để thay mức tác động và bằng chứng.

### Bài tập 6 — Phân tích change request

Một vendor xây dịch vụ gửi thông báo. Sau khi hai bên chốt mẫu email đã thuộc hợp đồng, Product Owner muốn thêm thông báo qua SMS và lịch sử chọn nhận tin. Vendor yêu cầu chi phí bổ sung.

**Câu hỏi:** phần nào là clarification, phần nào có thể là mở rộng phạm vi? Ai quyết định ordering, ai phê duyệt thay đổi điều khoản?

**Gợi ý:** giải thích ý nghĩa mẫu email trong hợp đồng là làm rõ; thêm kênh SMS/consent management có thể là capability mới. Product Owner quyết định thứ tự Product Backlog theo giá trị trong Scrum; người có thẩm quyền hợp đồng quyết định nghĩa vụ/chi phí. Phải làm rõ bảo mật/riêng tư và sự đồng ý nhận tin nếu phù hợp.

### Bài tập 7 — Chọn chiến lược test khi sandbox hạn chế

Nhóm có:

- Unit tests và contract tests cho IdP đang hỗ trợ.
- Một mock tạo token giả.
- Sandbox IdP mới chỉ được đặt lịch một lần mỗi tuần.
- DoD yêu cầu kiểm chứng trên hệ thống tích hợp và quyền chính xác.

**Yêu cầu:** phân công các loại test nên chạy thường xuyên và các test dành cho cửa sổ sandbox. Có được đánh dấu Done trước khi test bắt buộc trên bản thật không?

**Gợi ý:** chạy unit/contract/security logic tests sớm và thường xuyên; chuẩn bị dữ liệu/kịch bản để dùng sandbox cho kiểm chứng issuer/audience/expiry/permissions trên provider thật; sau đó integration/E2E đủ điều kiện. Không coi mock là bản thật; nếu thiếu bằng chứng DoD bắt buộc thì chưa Done.

### Bài tập 8 — Đọc dữ liệu blocked time

Một PBI mất:

- 2 ngày code.
- 3 ngày chờ contract.
- 1 ngày sửa adapter.
- 4 ngày chờ sandbox.
- 2 ngày tích hợp/kiểm chứng.

Giả sử các khoảng **không chồng lấn**.

**Yêu cầu:** tính cycle time, blocked time do vendor và tỷ lệ blocked. Gợi ý một thử nghiệm cải tiến và guardrail.

**Lời giải:**

\[
\text{Cycle time}=2+3+1+4+2=12\text{ ngày}.
\]

\[
\text{Blocked}=3+4=7\text{ ngày};\quad
\text{Tỷ lệ}=7/12\times100\%\approx58{,}3\%.
\]

Thử đặt lịch sandbox từ refinement, chốt contract bằng ví dụ trước coding. Guardrail là không giảm kiểm thử quyền/integration và không làm tăng lỗi hậu phát hành. Trong thực tế cần xem các khoảng trùng nhau và biến động loại việc.

### Bài tập 9 — Tình huống breaking change và version cũ

IdP chuẩn bị đổi claim và loại endpoint cũ. Nhóm có phiên bản web mới và một số client cũ chưa thể cập nhật đồng thời.

**Yêu cầu:** lập kế hoạch:

1. Thống kê consumer bị ảnh hưởng.
2. Xác định thay đổi breaking theo hành vi thật.
3. Hợp đồng test cho cả phiên bản.
4. Phương án chuyển tiếp và mốc kết thúc version cũ.
5. Điều kiện rollback/forward fix.
6. Đường xử lý nếu version cũ có lỗ hổng nghiêm trọng.

**Gợi ý:** giữ tương thích chuyển tiếp nếu vendor hỗ trợ và an toàn; adapter/versioning, contract tests, theo dõi consumer còn cũ, gỡ khi đủ điều kiện. Không giữ một phiên bản không an toàn chỉ để giảm thay đổi. Quyết định release theo rủi ro, quyền và chính sách.

### Bài tập 10 — Thiết kế đường ứng cứu sự cố liên vendor

Học viên không đăng nhập được. IdP báo API vẫn khỏe; logs consumer có lỗi kiểm tra signature. Hai bên đều cho rằng lỗi phía kia.

**Yêu cầu:** đề xuất quy trình năm bước giải quyết dựa trên bằng chứng thay vì tranh cãi.

**Gợi ý:**

1. Triage impact và kích hoạt incident response nếu phù hợp.
2. Ghi thời điểm, version, correlation ID và tín hiệu lỗi có phân quyền/ẩn dữ liệu.
3. Kiểm tra consumer key rotation, issuer/audience, cache và provider configuration.
4. Liên hệ vendor escalation với yêu cầu đối chiếu cụ thể; giảm tác động an toàn.
5. Kiểm chứng hành vi người dùng và dữ liệu khi khôi phục; hậu kiểm và cập nhật contract/tests/runbook.

Không bỏ xác minh chữ ký hoặc gửi private keys/token thật qua email để thử nhanh.

### Bài tập 11 — Phân biệt SLA, SLO, SLE và response target

Một nhà cung cấp quảng bá “99,9% uptime” và hỗ trợ phản hồi trong giờ hành chính. Scrum Team dự báo “90% PBI tích hợp có thể hoàn tất trong khoảng 15 ngày” từ dữ liệu lịch sử.

**Câu hỏi:** phát biểu nào là SLA, SLO, SLE? Có thể suy được thời gian khôi phục tối đa hoặc thời gian vendor giao tính năng không?

**Gợi ý:** “99,9% uptime” chỉ được gọi **SLA** nếu nằm trong một thỏa thuận với điều kiện/hệ quả tương ứng; có thể chỉ là mục tiêu SLO công bố. Dự báo PBI theo phân bố là một dạng **SLE** nếu được định nghĩa đúng. Response target theo giờ hành chính khác resolution time. Không thể suy cam kết khôi phục hoặc lịch giao tính năng từ uptime.

### Bài tập 12 — Product Owner lựa chọn phạm vi

Product Goal: học viên tự đăng ký khóa miễn phí chính xác. Các hạng mục:

| ID | Hạng mục | Tình trạng |
| --- | --- | --- |
| **A** | Xử lý request lặp không tạo đăng ký trùng | Trong khả năng đội, kiểm thử tích hợp cần làm. |
| **B** | Tra trạng thái đăng ký của chính mình | Có thể dùng IdP hiện hành đã kiểm chứng. |
| **C** | Giao diện đăng nhập mới của vendor | Chưa có sandbox; không bắt buộc cho mục tiêu hiện tại. |
| **D** | Email theo mẫu mới từ Notifications vendor | Đang chờ change request; không phải điều kiện bắt buộc giả định. |

**Yêu cầu:** đề xuất thứ tự ưu tiên có lý do, rủi ro nào không được bỏ và cách phản hồi stakeholder muốn C trước.

**Gợi ý:** A là rủi ro chất lượng rất quan trọng, B gắn trực tiếp Product Goal; có thể tập trung hai phần trước nếu đáp ứng DoD/giá trị. C, D là cải tiến có thể làm rõ và lên kế hoạch theo vendor; nếu người có thẩm quyền xác nhận chúng bắt buộc, cần xem lại quyết định. PO chịu trách nhiệm ordering trong Scrum, không có quyền bỏ kiểm soát bảo mật hoặc sửa hợp đồng trái quyền.

### Bài tập 13 — Đánh giá trước–sau

Nhóm áp dụng contract-first và đặt lịch sandbox sớm. Bốn tuần đầu ghi 10 PBI Done, cycle time trung vị 14 ngày, blocked time trung vị 6 ngày. Bốn tuần sau ghi 11 PBI Done, cycle time 9 ngày, blocked time 3 ngày.

**Yêu cầu:** viết một nhận xét có bằng chứng và hai yếu tố chưa biết. Nêu vì sao không đủ để kết luận cải tiến có thể áp dụng cho mọi vendor.

**Gợi ý:**

> “Dữ liệu minh họa cho thấy cycle time và blocked time trung vị giảm trong khoảng theo dõi, là tín hiệu đáng khích lệ. Tuy nhiên, chưa biết độ tương đương của các PBI và tác động của thay đổi công suất vendor; cần theo dõi thêm chất lượng, lỗi phát hành và lượng rework trước khi chuẩn hóa rộng.”

Không tự suy rằng mọi nhà cung cấp sẽ phản hồi nhanh hơn đúng ba ngày. Những vendor có mức pháp lý/hỗ trợ khác nhau có thể cần cách khác.

### Bài tập 14 — Chọn giữa bốn phương án giảm phụ thuộc

Nhà cung cấp danh tính không hỗ trợ một capability cần cho yêu cầu bảo mật mới. Nhóm có bốn lựa chọn:

- A. Giữ bản cũ và tắt kiểm soát để kịp Sprint.
- B. Chờ vendor cung cấp bản được kiểm chứng và hoãn phần phụ thuộc.
- C. Dùng provider khác đủ điều kiện sau khi đánh giá kỹ thuật/pháp lý/thương mại.
- D. Đề nghị đổi phạm vi sang một hành vi không cần capability ấy, nếu người có thẩm quyền xác nhận vẫn đáp ứng nghĩa vụ.

**Yêu cầu:** lựa chọn nào phải loại, lựa chọn nào có thể cân nhắc, cần ai quyết định?

**Gợi ý:** loại A vì bỏ kiểm soát bắt buộc. B có thể an toàn khi chưa đủ bằng chứng. C và D có thể xét khi thực sự đáp ứng các yêu cầu và thẩm quyền, nhưng cần chi phí migration, dữ liệu, hợp đồng, DoD và outcome. Đây không phải quyết định PO tự làm một mình nếu liên quan bảo mật và hợp đồng.

### Bài tập 15 — Viết một thẻ thử nghiệm cải tiến phối hợp

Chọn một vấn đề: sandbox hay trễ, contract mismatch lặp, quá nhiều ticket hỏi lại hoặc sự cố support chuyển vòng. Viết kế hoạch theo **Plan–Do–Check–Act (PDCA)**:

1. Quan sát và baseline cụ thể.
2. Giả thuyết cơ chế **Nếu… thì… vì…**.
3. Một thay đổi nhỏ và phạm vi thử.
4. Metric chính và ít nhất hai guardrails.
5. Đầu mối consumer/vendor, quyền cần có, lịch review.
6. Hướng xử lý nếu cải thiện, nếu không cải thiện hoặc nếu có tác động nghiêm trọng.

**Ví dụ gợi ý:**

> “Nếu yêu cầu cấp sandbox được ghi từ lúc làm rõ PBI, với mẫu mô tả test account/version/điều kiện và đầu mối vendor, thì blocked time do sandbox sẽ giảm vì cả hai bên có thời gian kiểm tra quyền và chuẩn bị trước cửa sổ test.”

Metric chính: thời gian từ lúc PBI cần sandbox tới lúc có môi trường **thực sự dùng được**. Guardrails: test bắt buộc vẫn chạy; không mở quyền/dữ liệu vượt phạm vi; không tăng tải bất hợp lý của vendor. Nếu kết quả không cải thiện, xem rào cản công suất hoặc hợp đồng thay vì tổ chức thêm họp theo phản xạ.

## 27. Checklist phối hợp với nhà cung cấp có nhịp phát triển khác

### Trước khi chọn PBI hoặc cam kết phạm vi

- [ ] Đã mô tả **kết quả người dùng** thay vì chỉ công việc phải nhận từ vendor.
- [ ] Xác định được nhà cung cấp nào thực sự cần và điều kiện nào là tùy chọn.
- [ ] Phân biệt version hiện hành, version dự kiến và điều kiện end-of-support.
- [ ] Biết nhịp phát triển, tiếp nhận thay đổi, release, test access, support và phê duyệt của đối tác ở mức đã xác minh.
- [ ] Có Product Owner/đầu mối sản phẩm và người có quyền thương mại, kỹ thuật, vận hành phù hợp.
- [ ] Đã nêu những yêu cầu **không được đánh đổi**: dữ liệu, bảo mật, DoD, nghĩa vụ pháp lý và khả năng phục hồi.
- [ ] Đã xem khả năng tách một **lát cắt giá trị an toàn** không cần đợi tất cả nâng cấp vendor.
- [ ] Điều kiện vendor nào chưa có chứng cứ được ghi là **giả định/rủi ro**, không phải cam kết chắc.

### Khi lập bản đồ phụ thuộc và hợp đồng

- [ ] Mỗi phụ thuộc có **consumer, provider, đầu ra, version, owner và điều kiện kiểm chứng**.
- [ ] Có mốc **cần biết** đủ sớm để điều chỉnh phạm vi/kế hoạch.
- [ ] Có contract hoặc ví dụ nghiệp vụ cho thành công, lỗi, quyền và trạng thái chưa rõ.
- [ ] Đã phân biệt hợp đồng kỹ thuật, nghiệm thu thương mại, DoD và release policy.
- [ ] Có thông tin môi trường thử, test accounts và nguồn dữ liệu được phép.
- [ ] Đã thống nhất quy trình thay đổi hợp đồng/schema và thông báo breaking change.
- [ ] Có người có thẩm quyền tiếp nhận change request hoặc thay đổi chi phí.
- [ ] Có phương án khi mốc vendor không đạt, kể cả lựa chọn **No-go**.

### Khi phát triển và tích hợp

- [ ] Consumer unit tests chạy liên tục trong phạm vi tự kiểm soát.
- [ ] Có contract/compatibility tests cho phiên bản provider mục tiêu.
- [ ] Mock/stub được ghi rõ là mô phỏng, không bị tính như tích hợp thật.
- [ ] Test integration/security/E2E cần thiết có thể chạy trên môi trường phù hợp.
- [ ] Không tự copy dữ liệu cá nhân hoặc secret production sang sandbox.
- [ ] Có kiểm thử timeout, invalid token, rate limit, retry và failure modes liên quan.
- [ ] Thay đổi schema/API có chiến lược tương thích và gỡ phiên bản cũ đúng điều kiện.
- [ ] Adapter/feature flag/fallback không thay bảo vệ authn/authz và tính đúng đắn dữ liệu.
- [ ] Nếu provider bản mới chưa sẵn sàng, phần đó vẫn được thể hiện **Not Run/Blocked**, không khai báo PASS.
- [ ] Có khả năng truy vết phiên bản consumer/provider và correlation IDs theo quyền.

### Khi quản lý Scrum và Kanban

- [ ] Product Backlog được sắp thứ tự theo giá trị và rủi ro, không chạy theo lịch vendor một cách máy móc.
- [ ] Sprint Goal có thể điều hướng trong điều kiện phụ thuộc và mức bất định đã biết.
- [ ] Developers xem điều kiện để tạo Increment đạt DoD, không chỉ task code đã xong.
- [ ] Nếu nhiều Scrum Team cùng một sản phẩm, họ chia sẻ Product Goal, Product Backlog, Product Owner và DoD.
- [ ] Các item chờ vendor vẫn hiển thị trong WIP/work item age theo workflow đã định.
- [ ] Theo dõi blocked time và dependency age, không giấu thời gian chờ khỏi cycle time sản phẩm.
- [ ] Có SLE cho loại việc phù hợp nếu có dữ liệu, nhưng không lẫn với SLA vendor.
- [ ] Có điều kiện escalation kỹ thuật/thẩm quyền rõ; không đợi cuộc họp tuần để gỡ việc gấp.
- [ ] Retrospective/flow review xem nguyên nhân phụ thuộc lặp và thử cải tiến có kiểm chứng.

### Trước khi phát hành

- [ ] Increment đã đáp ứng Definition of Done và kiểm chứng bắt buộc.
- [ ] Vendor acceptance (nếu có) không được dùng thay thế bằng chứng tích hợp sản phẩm.
- [ ] Hợp đồng và phiên bản đang vận hành tương thích với consumer trong phạm vi release.
- [ ] Có cửa sổ triển khai, quyền và những phê duyệt cần thiết.
- [ ] Có kế hoạch rollout/dừng/rollback hoặc forward fix xét tới **dữ liệu và side effects**.
- [ ] Có release note, known limitations và các thay đổi ảnh hưởng support.
- [ ] Có SLI/monitoring, cảnh báo và runbook đủ để phát hiện lỗi liên hệ thống.
- [ ] Có kênh on-call và vendor escalation cho các mức tác động cần thiết.
- [ ] Các giới hạn chưa xác minh đã được giải quyết hoặc phần phụ thuộc chưa được mở.

### Khi hỗ trợ và ứng cứu

- [ ] Support có thể nhận và xác minh vấn đề người dùng mà không hỏi mật khẩu/token hoặc dữ liệu thừa.
- [ ] Có đầu mối giữ bức tranh sự cố **xuyên các nhóm và vendor**.
- [ ] Phân biệt đã xác nhận với giả thuyết nguyên nhân.
- [ ] Kiểm tra consumer logic, provider status, cấu hình, phiên bản và tác động dữ liệu.
- [ ] Fallback không cấp quyền hoặc trả thành công giả khi dependency thất bại.
- [ ] Truyền thông trung thực về phạm vi ảnh hưởng, tình trạng và nhịp cập nhật.
- [ ] Khôi phục được xác nhận bằng **hành vi người dùng và dữ liệu**, không chỉ dashboard vendor xanh.
- [ ] Hậu kiểm có hành động phòng ngừa, owner và bằng chứng hiệu quả.

### Khi đánh giá và cải tiến quan hệ vendor

- [ ] Đo blocked time, cycle time, work item age, chất lượng, chi phí và outcome cùng bối cảnh.
- [ ] Không so các workflow khác mốc đo như thể cùng một chỉ số.
- [ ] Không dùng số email, meeting, ticket đã đóng để thay kết quả sản phẩm.
- [ ] Xem dữ liệu trước–sau với yếu tố gây nhiễu và guardrails.
- [ ] Phụ thuộc lặp được thử giảm qua contract, tự phục vụ, versioning hoặc lát cắt khác.
- [ ] Những thay đổi hợp đồng hoặc quyền sở hữu đã được quyết đúng thẩm quyền.
- [ ] Có kế hoạch cập nhật, end-of-support, chuyển đổi và kết thúc hợp đồng khi cần.
- [ ] Người dùng vẫn được phục vụ đáng tin cậy dù nhịp phát triển các bên khác nhau.

Checklist này là **bộ câu hỏi thực hành**, không phải danh sách phê duyệt bắt buộc giống nhau cho mọi vendor. Một hệ thống rủi ro thấp có thể cần luồng nhẹ; sản phẩm liên quan dữ liệu nhạy cảm hoặc nghĩa vụ chuyên ngành cần mức bằng chứng và quyền quyết định tương xứng.

## 28. Tổng kết

Khi làm Agile, nhóm không nhất thiết phải kiểm soát nhịp phát triển của mọi nhà cung cấp để tạo được sản phẩm thích ứng. Điều có thể kiểm soát là **cách làm rõ nhu cầu, phân rã giá trị, thiết kế hợp đồng, tích hợp, quản lý rủi ro và học hỏi từ kết quả**.

Một cách phối hợp hiệu quả cần:

1. **Hiểu nhịp thật của vendor:** phát triển, phát hành, phê duyệt, hỗ trợ, bảo mật và hợp đồng có thể là những nhịp khác nhau.
2. **Đặt giá trị người dùng làm trung tâm:** Product Goal và hành vi có thể sử dụng quyết định thứ tự công việc, không chỉ lịch vendor.
3. **Ghi phụ thuộc theo điều kiện kiểm chứng:** ai cần gì từ ai, phiên bản nào, lúc nào cần biết, tác động ra sao và ai quyết định.
4. **Giảm coupling:** dùng khả năng hiện hành phù hợp, lát cắt dọc, adapter, backward compatibility, contract testing, CI và môi trường test có kiểm soát.
5. **Tích hợp sớm nhưng trung thực:** mock và contract tests giúp giảm chờ, nhưng không thay kiểm chứng provider thật, dữ liệu và quyền bắt buộc để đạt DoD.
6. **Giữ quản trị đúng quyền:** Product Owner sắp thứ tự giá trị; Developers tạo Increment; người có thẩm quyền thương mại/bảo mật/vận hành quyết những việc thuộc phạm vi họ.
7. **Phối hợp sự cố rõ:** có escalation, runbook, monitoring, trách nhiệm khôi phục xuyên nhiều bên và hậu kiểm dựa trên bằng chứng.
8. **Đo toàn luồng:** giảm thời gian chờ mà không tăng lỗi, mất dữ liệu, rủi ro an toàn hay tải hỗ trợ.
9. **Thích ứng khi điều kiện đổi:** sửa scope, version, thứ tự việc hoặc kế hoạch theo bằng chứng; không cố giữ một lịch đã không còn khả thi.

Trong **Scrum**, sự phối hợp với vendor không làm mất Product Goal, Sprint Goal, DoD và trách nhiệm tạo Increment tích hợp. **Kanban** giúp thấy công việc đang chờ, giới hạn WIP và quản lý tuổi item/phụ thuộc. **XP/CI** giúp đưa feedback kỹ thuật tới sớm, còn tư duy **Lean** giúp giảm hàng đợi và tránh tối ưu cục bộ bằng cách chuyển chi phí sang bên khác.

**Mục tiêu không phải bắt nhà cung cấp “Agile giống hệt chúng ta”. Mục tiêu là để các nhịp khác nhau vẫn kết nối qua hợp đồng rõ, kiểm chứng sớm và quyết định minh bạch, tạo giá trị cho người dùng một cách đáng tin cậy.**

### Thuật ngữ chính

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Vendor / supplier / provider** | Nhà cung cấp hoặc đối tác tạo năng lực, sản phẩm, dịch vụ hoặc đầu ra cho consumer. |
| **Consumer** | Hệ thống/nhóm sử dụng hợp đồng hoặc dịch vụ do provider cung cấp. |
| **Cadence** | Nhịp lặp của việc phát triển, ra quyết định, phát hành, hỗ trợ hoặc phê duyệt. |
| **Cross-team/external dependency** | Điều kiện hoặc đầu ra từ bên khác cần để hoàn tất một kết quả. |
| **Dependency register** | Bản ghi đầu ra cần, owner, phiên bản, mốc, trạng thái, tác động và cách xử lý phụ thuộc. |
| **Decision checkpoint** | Điểm cần xem bằng chứng để chọn đi tiếp, điều chỉnh hoặc dừng. |
| **Contract** | Thỏa thuận giao tiếp/kỹ thuật hoặc nghĩa vụ thương mại; cần phân biệt theo ngữ cảnh. |
| **Change request** | Đề nghị thay đổi phạm vi hoặc điều kiện hợp đồng khi áp dụng. |
| **Contractual acceptance** | Nghiệm thu một deliverable theo tiêu chí của thỏa thuận. |
| **Acceptance criteria** | Các điều kiện hành vi cụ thể cần đáp ứng cho hạng mục/sản phẩm đã định. |
| **Definition of Done (DoD)** | Cam kết về trạng thái chất lượng của Increment trong Scrum. |
| **Increment** | Phần sản phẩm tăng thêm đã tích hợp, có thể sử dụng và đáp ứng DoD. |
| **Product Goal / Sprint Goal** | Mục tiêu dài hạn sản phẩm / mục tiêu thống nhất của Sprint trong Scrum. |
| **API contract / schema** | Đặc tả giao tiếp và cấu trúc/ý nghĩa dữ liệu giữa consumer và provider. |
| **Consumer-driven contract testing** | Cách consumer xác định kỳ vọng để kiểm chứng provider tương thích trong phạm vi được thỏa thuận. |
| **Compatibility / breaking change** | Khả năng cùng hoạt động giữa các phiên bản / thay đổi làm hỏng consumer hiện hành. |
| **Deprecation / end-of-support** | Thông báo ngừng dùng một khả năng / thời điểm chấm dứt hỗ trợ theo chính sách. |
| **Adapter / anti-corruption layer** | Ranh giới chuyển hợp đồng bên ngoài thành mô hình nội bộ ổn định. |
| **Mock / stub** | Thành phần mô phỏng hành vi giúp phát triển/test sớm, không thay tích hợp thật. |
| **Sandbox** | Môi trường thử có cấu hình/quyền/giới hạn theo provider, có thể khác production. |
| **Expand–migrate–contract** | Cách đổi hợp đồng hoặc dữ liệu theo giai đoạn tương thích, chuyển tiếp và gỡ phần cũ. |
| **Feature flag** | Cơ chế điều khiển mở khả năng; không thay xác thực/phân quyền. |
| **Canary / phased rollout** | Mở dần thay đổi trong phạm vi giới hạn để kiểm chứng và giảm tác động. |
| **Circuit breaker / fallback** | Cơ chế hạn chế lỗi phụ thuộc lan rộng / cách xử lý khi dịch vụ ngoài không sẵn. |
| **Idempotency** | Tính chất xử lý yêu cầu lặp theo quy tắc mà không tạo tác động nghiệp vụ trùng ngoài ý muốn. |
| **CI / TDD / XP** | Tích hợp liên tục / phát triển dẫn dắt bởi test / thực hành kỹ thuật Extreme Programming. |
| **SLI / SLO / SLA** | Chỉ số chất lượng dịch vụ / mục tiêu chất lượng / thỏa thuận mức dịch vụ. |
| **SLE** | Kỳ vọng có tính xác suất cho thời gian hoàn tất hạng mục trong Kanban. |
| **WIP / cycle time / work item age / throughput** | Chỉ số việc dở, thời gian hoàn tất, tuổi việc dở và số việc hoàn tất theo workflow. |
| **Blocked time / dependency age** | Thời gian bị chặn / thời gian phụ thuộc tồn tại theo mốc đo đã xác định. |
| **Go/No-go** | Quyết định có tiếp tục phát hành/triển khai dựa trên bằng chứng và thẩm quyền. |
| **Rollback / forward fix** | Khôi phục bằng quay phiên bản/cấu hình / sửa tiến lên theo phương án an toàn. |
| **Incident / severity / escalation** | Sự cố cần phản ứng / mức tác động / chuyển đúng tuyến chuyên môn hoặc thẩm quyền. |
| **Blameless postmortem** | Hậu kiểm hướng vào điều kiện hệ thống, không dùng việc đổ lỗi để thay phân tích nguyên nhân. |
| **RACI / ADR** | Mô hình làm rõ trách nhiệm / bản ghi quyết định kiến trúc khi phù hợp. |
| **PDCA** | Plan–Do–Check–Act: cải tiến qua kế hoạch, thử, kiểm tra và điều chỉnh/chuẩn hóa. |
