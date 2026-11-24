# Phân tích một tình huống phát triển và xác định nhu cầu thích ứng

## 1. Bài thực hành tổng hợp: từ dấu hiệu bất ổn đến quyết định thích ứng có căn cứ

Hãy hình dung một nhóm phát triển phần mềm đang làm một tính năng tưởng chừng đơn giản: **học viên tự đăng ký khóa học miễn phí còn chỗ**. Ở cuộc họp đầu tiên, yêu cầu được mô tả ngắn: “Thêm nút Đăng ký và lưu thông tin học viên”. Sau một số vòng phát triển, nhóm gặp những vấn đề:

- Người học không biết yêu cầu đã thành công hay chưa khi mạng bị gián đoạn.
- Hai học viên đồng thời đăng ký chỗ cuối khiến hệ thống đôi lúc vượt sức chứa.
- Product Owner nhận đề xuất thêm email, danh sách chờ và thanh toán trong khi chức năng chính chưa ổn định.
- Frontend, API, dữ liệu và kiểm thử hoàn thành nhiều task riêng, nhưng phần mềm tích hợp chưa đáp ứng Definition of Done.
- Một nhà cung cấp định danh thông báo sắp đổi hợp đồng token; lịch thay đổi không trùng Sprint.
- Nhóm bắt đầu thêm việc mới để “giữ năng suất”, trong khi các item dở ngày càng già.

Câu trả lời phù hợp không phải lập tức tuyên bố **“chuyển sang Scrum”**, **“dùng Kanban”** hoặc **“viết thêm unit test”**. Trước tiên cần hiểu **điều gì thật sự đang xảy ra, ai chịu ảnh hưởng, giả định nào chưa được kiểm chứng, rủi ro nào bắt buộc xử lý và cơ chế nào khiến nhóm chưa thể giao giá trị**.

Đây là bài **thực hành tổng hợp** của module **AGILE_DEVELOPMENT**, kết nối tư duy giá trị và nguyên tắc Agile với user story, Product Backlog, Scrum, Kanban, XP, Lean và đo lường flow. Tâm điểm không phải kể lại các framework, mà là **phân tích một tình huống phát triển để quyết định khi nào, vì sao và bằng cách nào cần thích ứng**.

Toàn bộ tổ chức, nhân vật, con số và diễn biến dưới đây là **tình huống giả định để học tập**, không phản ánh hệ thống sản xuất hay doanh nghiệp cụ thể. Mọi tính toán đều dùng dữ liệu minh họa và phải được xác minh lại khi áp dụng thực tế.

### 1.1. Năng lực cần đạt

Sau bài này, người học có thể:

1. Tái dựng tình huống phát triển từ **bằng chứng, diễn biến và giới hạn dữ liệu**.
2. Phân biệt **sự kiện đã quan sát**, **diễn giải**, **giả thuyết nguyên nhân**, **rủi ro** và **quyết định**.
3. Nhận diện nhu cầu thích ứng về **giá trị, yêu cầu, phạm vi, thứ tự ưu tiên, luồng công việc, kỹ thuật, phối hợp và vận hành**.
4. Đặt câu hỏi để bảo vệ **Product Goal, Sprint Goal, Definition of Done**, dữ liệu và quyền người dùng.
5. Chọn hành động thích hợp với bối cảnh, kể cả **làm rõ yêu cầu, chia lát cắt dọc, giới hạn WIP, tích hợp sớm, thử nghiệm sản phẩm và điều chỉnh kế hoạch**.
6. Chỉ ra **thước đo thành công, guardrails, người ra quyết định và dấu hiệu cần xem lại**.
7. Thảo luận được nhiều phương án hợp lý, thay vì tìm một “đáp án Agile duy nhất”.

### 1.2. Sản phẩm cuối của bài thực hành

Người học sẽ tạo một **phiếu phân tích và kế hoạch thích ứng** ngắn nhưng đủ kiểm chứng:

- Bản mô tả vấn đề và kết quả người dùng cần đạt.
- Danh sách bằng chứng, khoảng trống dữ liệu và giả thuyết.
- Bản đồ phụ thuộc/luồng giá trị và những rủi ro chính.
- Các lựa chọn thích ứng, lý do sắp thứ tự và điều không được đánh đổi.
- Một hoặc vài lát cắt giá trị có acceptance criteria rõ.
- Kế hoạch thử trong vòng ngắn, metric chính và guardrails.
- Quy tắc điều chỉnh nếu xuất hiện bằng chứng mới.

> **Nguyên tắc phân tích:** Chỉ nói “cần thích ứng” khi đã xác định **thay đổi nào trong thực tế làm giả định/kế hoạch hiện hành không còn phù hợp**, và biết điều gì cần được giữ ổn định để bảo vệ giá trị.

## 2. Hồ sơ ca: nền tảng học trực tuyến Học Mở

### 2.1. Sản phẩm, người dùng và mục tiêu

Một sản phẩm học trực tuyến giả định mang tên **Học Mở** có danh mục khóa học miễn phí và có phí. Người học hiện xem được thông tin nhưng phải nhờ nhân viên hỗ trợ khi muốn đăng ký. Tổ chức mong muốn giảm việc xử lý thủ công bằng một luồng tự phục vụ.

**Product Goal minh họa:**

> Học viên đủ điều kiện có thể tự chọn và đăng ký khóa học phù hợp, nhìn thấy trạng thái đáng tin cậy và nhận hướng dẫn tiếp theo mà không cần nhân viên xử lý các trường hợp thông thường.

**Lát cắt đang được xem xét:** chỉ gồm **khóa miễn phí với số chỗ giới hạn**. Thanh toán, hoàn phí và thông báo qua nhiều kênh chưa mặc nhiên là một phần của lát cắt này. Nếu hệ thống thật có quy định bắt buộc về thông báo, phải kiểm tra và đưa vào điều kiện hoàn tất; không tự loại bỏ.

### 2.2. Những bên liên quan

| Bên liên quan | Nhu cầu/góc nhìn chính | Điều có thể quyết hoặc cung cấp |
| --- | --- | --- |
| **Học viên** | Đăng ký được, thấy trạng thái thật, không lộ thông tin. | Phản hồi trải nghiệm và hành vi sử dụng khi được phép thu thập. |
| **Nhân viên hỗ trợ** | Giảm câu hỏi không cần thiết; tra cứu an toàn khi có sự cố. | Dữ liệu hỗ trợ đã được cấp quyền, mô tả lỗi thường gặp. |
| **Product Owner (PO)** | Tối đa hóa giá trị và sắp thứ tự Product Backlog. | Quyết định ordering/phạm vi sản phẩm trong quyền Scrum. |
| **Developers** | Tạo Increment sử dụng được, đáp ứng DoD. | Thiết kế kỹ thuật, Sprint Backlog và kế hoạch thực hiện. |
| **Scrum Master** | Hỗ trợ Scrum hiệu quả, gỡ trở ngại ở cấp hệ thống. | Facilitate cải tiến, không làm người phân việc cho Developers. |
| **Chuyên gia chất lượng và bảo mật** | Chứng minh quyền, dữ liệu và hành vi lỗi đúng. | Kiểm chứng/khuyến nghị theo năng lực, chính sách và quyền thực tế. |
| **Nhóm nền tảng** | CI, môi trường thử, khả năng vận hành. | Cung cấp công cụ và self-service có kiểm soát. |
| **Nhà cung cấp định danh (IdP)** | Vận hành xác thực và quản lý API/version theo thỏa thuận. | Contract, hỗ trợ, sandbox và thay đổi trong phạm vi quyền. |
| **Quản lý/đơn vị kinh doanh** | Kết quả người dùng, chi phí, mốc quan trọng, rủi ro. | Nguồn lực và quyết định thuộc thẩm quyền, không tự thay PO. |

Các tên vai trò mô tả **khả năng cần thiết**, không buộc tổ chức thật phải có từng phòng ban riêng. Trong Scrum, **Developers, Product Owner và Scrum Master** là ba accountabilities; chuyên môn kiểm thử/bảo mật có thể nằm trong Developers hoặc là năng lực hỗ trợ bên ngoài tùy tổ chức.

### 2.3. Tình trạng kỹ thuật và quy trình ban đầu

Sản phẩm có:

- Ứng dụng web hiển thị danh mục khóa và trạng thái sơ bộ.
- API đăng ký do nhóm phát triển sở hữu.
- Cơ sở dữ liệu lưu học viên, khóa và đăng ký.
- Dịch vụ định danh bên ngoài cung cấp token đăng nhập.
- CI chạy unit tests; integration tests trên DB và IdP chưa ổn định.
- Lịch phát hành bị giới hạn bởi một số điều kiện vận hành.

Nhóm dùng **Sprint hai tuần** và có Daily Scrum, Sprint Review, Sprint Retrospective. Tuy nhiên, công việc đang bị tách thành ticket theo lớp như **“UI xong”**, **“API xong”**, **“DB xong”** và **“QA sau”**. Vì vậy danh sách task đã đóng **không tự chứng minh** Increment đăng ký của người học đã đạt DoD.

### 2.4. Kết quả nghiệp vụ được kỳ vọng

Không chỉ “có nút đăng ký”, mà là:

1. Học viên đã xác thực và đủ điều kiện thấy khóa miễn phí còn chỗ.
2. Khi đăng ký, hệ thống kiểm tra quyền và tính đúng đắn **tại server**.
3. Đối với một học viên–khóa, không tạo hai đăng ký hiệu lực trái quy tắc.
4. Không thể xác nhận vượt sức chứa khi nhiều yêu cầu đồng thời.
5. Nếu timeout sau khi dữ liệu đã lưu, người học có cách biết **trạng thái cuối đúng**.
6. Người học không thể xem đăng ký riêng của người khác.
7. Hệ thống có bằng chứng kiểm thử/tích hợp và vận hành cần thiết theo DoD.

**Chú ý:** không được coi các kiểm tra dữ liệu và phân quyền là “phần nâng cao sẽ làm Sprint khác” nếu tính năng thực tế đã mở cho người dùng. Có thể chia thành những bước kỹ thuật nhỏ được tích hợp an toàn, nhưng khả năng được tuyên bố **Done/usable** phải đáp ứng những điều kiện bắt buộc.

## 3. Dữ liệu ca: phân biệt đo được với chưa biết

### 3.1. Thống kê hỗ trợ và hành vi người học giả định

Trong một đợt thử giới hạn, nhóm ghi dữ liệu tổng hợp sau (hoàn toàn **giả định**):

| Chỉ báo | Quan sát trong 4 tuần | Giới hạn diễn giải |
| --- | ---: | --- |
| Lượt bắt đầu yêu cầu đăng ký | 200 | Không đồng nghĩa 200 người khác nhau. |
| Lượt có trạng thái đăng ký được xác nhận thành công | 148 | Chưa có phân tích đầy đủ các yêu cầu còn lại. |
| Ticket hỗ trợ có liên quan tới đăng ký | 27 | Một người có thể gửi nhiều ticket; có thể trùng với lượt thành công. |
| Ticket hỏi “đã đăng ký thành công chưa?” | 12 | Là tập con của 27 ticket, không cộng như loại độc lập. |
| Lần phát hiện bản ghi đăng ký trùng cần điều tra | 3 | Chưa kết luận nguyên nhân; cần kiểm chứng mức ảnh hưởng. |
| Lỗi kiểm thử tranh chỗ cuối ở môi trường tích hợp | 2 lần | Cần biết version, test data và khả năng tái hiện. |
| Tỷ lệ hoàn tất theo lượt bắt đầu (định nghĩa minh họa) | 148/200 = 74% | Không đồng nghĩa tỷ lệ chuyển đổi người dùng duy nhất. |

Hai con số đáng chú ý là **có nguy cơ sai tính toàn vẹn dữ liệu** và **người dùng thiếu khả năng xác minh trạng thái**. Tuy vậy, **một lỗi test chưa chứng minh lỗi đã xảy ra ở production**, còn một bản ghi “có vẻ trùng” chưa đủ để quy kết nguyên nhân cho race condition.

**Ưu tiên an toàn:** nếu xác minh có bản ghi trùng/sai sức chứa hay lộ dữ liệu đang ảnh hưởng người dùng, phải xử lý theo quy trình sự cố và bảo vệ dữ liệu ngay, không chờ tới Retrospective hoặc một thử nghiệm cải tiến thông thường.

### 3.2. Thống kê phát triển giả định

Từ 24 PBI đã được xem xét trong bốn tuần:

| Trạng thái theo bản chụp cuối kỳ | Số PBI | Cách hiểu |
| --- | ---: | --- |
| Đạt Done theo chuẩn đang công bố | 9 | Chỉ những item thực sự thỏa DoD mới được tính, cần xem chất lượng chuẩn. |
| Đã Started nhưng chưa Finished | 5 | WIP tại cuối kỳ theo ranh giới đã chọn. |
| Chưa Started | 10 | Không được tính vào WIP; vẫn có thể thuộc backlog. |
| **Tổng** | **24** | **9 + 5 + 10 = 24**. |

Những số đo khác trong ví dụ:

- **Cycle time trung vị** của 9 PBI Finished: 9 ngày làm việc, theo một cách đếm đã thống nhất.
- **Work item age** của 5 PBI đang dở: 3, 7, 10, 11 và 15 ngày làm việc.
- Có **3 item** ghi chờ môi trường tích hợp; **2 item** chờ quyết định hợp đồng API. Hai tập có thể chồng lấn, không tự cộng thành năm item khác nhau.
- Một số PR có thời gian chờ review dài, nhưng chưa có dữ liệu phân bố đủ để kết luận reviewer là nút thắt chính.

Vì cycle time chỉ được tính trên **item đã Finished**, một PBI già 15 ngày chưa Done **không xuất hiện trong median 9 ngày**. Chỉ dùng median của item Done có thể che hàng đợi đang tích tụ.

### 3.3. Bằng chứng phải kèm định nghĩa

Một bảng số liệu có ích cần xác định:

- **Khoảng thời gian** đo (lịch, ngày làm việc, múi giờ khi cần).
- **Đơn vị** (lượt yêu cầu, học viên, ticket, PBI, PR hay Increment).
- **Mốc bắt đầu/kết thúc** của flow metric.
- **Nguồn dữ liệu** và điều kiện được phép truy cập.
- **Trùng lặp/thiếu dữ liệu** và giới hạn suy luận.
- **Điều đã được xác minh** khác **điều đang nghi ngờ**.

Không so “200 lượt đăng ký” với “27 ticket” rồi nói **13,5% người học gặp lỗi**, vì hai tập không cùng đơn vị và có thể không ánh xạ một-một. Có thể tính 27/200 như **tỷ số ticket trên lượt bắt đầu** để tham khảo nếu đã công bố định nghĩa, nhưng không được diễn giải thành tỷ lệ người dùng bị ảnh hưởng.

## 4. Dòng thời gian của ca và những tín hiệu cần thích ứng

### 4.1. Timeline giả định qua các vòng phát triển

| Thời điểm | Diễn biến | Tín hiệu thay đổi |
| --- | --- | --- |
| **Trước Sprint 1** | Business yêu cầu “thêm nút đăng ký và lưu vào DB”. | Chưa đủ hành vi lỗi, phân quyền và tranh chỗ cuối. |
| **Sprint 1, ngày 3** | Web và API triển khai song song nhưng chưa thống nhất trạng thái khi hết chỗ. | Rủi ro lệch hợp đồng; có thể làm rõ bằng ví dụ sớm. |
| **Sprint 1, ngày 8** | Ba task kỹ thuật báo Done cục bộ; test tích hợp chưa chạy. | Không có bằng chứng Increment sử dụng được. |
| **Sprint Review 1** | Stakeholder muốn thêm email xác nhận và danh sách chờ. | Nhu cầu mới cần phân loại, không tự đưa hết vào Sprint kế. |
| **Sprint 2, ngày 2** | Test concurrency cho thấy có thể vượt sức chứa trong điều kiện thử. | Rủi ro dữ liệu cần kiểm chứng và sửa sớm. |
| **Sprint 2, ngày 4** | Support ghi nhận câu hỏi sau timeout. | Có tín hiệu giá trị chưa đạt; cần điều tra đường trạng thái. |
| **Sprint 2, ngày 6** | Nhà cung cấp IdP thông báo sắp thay cấu trúc claims. | Rủi ro phụ thuộc/khả năng tương thích chưa chắc thành blocker ngay. |
| **Sprint 2, ngày 8** | Môi trường thử dùng chung không sẵn; item dở tăng. | Nhu cầu thích ứng cách tích hợp và quản lý WIP. |
| **Sprint Review 2** | Quản lý muốn giữ ngày mở rộng cho tất cả học viên. | Cần trình bày sự thật về DoD, rủi ro và lựa chọn phát hành. |

Các ngày và Sprint là **nhãn thời gian minh họa**. Chúng không chứng minh một công việc phải mất đúng một thời lượng nhất định.

### 4.2. Sơ đồ các đường tác động

~~~mermaid
flowchart TD
    A["Product Goal: học viên tự đăng ký đáng tin"] --> B["User story / acceptance criteria"]
    B --> C["UI + API + DB + quyền"]
    C --> D["Test tích hợp / concurrency"]
    D --> E{"Đạt DoD?"}
    E -- "Chưa" --> F["Làm rõ, sửa, giảm WIP, kiểm chứng"]
    F --> D
    E -- "Có" --> G["Increment sử dụng được"]
    G --> H["Release theo policy"]
    H --> I["Hành vi người học / support / outcome"]
    I --> J["Học từ bằng chứng, cập nhật backlog"]
    J --> B
    K["Thay đổi IdP / môi trường"] -. "Phụ thuộc và bất định" .-> D
    L["Yêu cầu email / danh sách chờ"] -. "Cần quyết định phạm vi" .-> J
~~~

Trong sơ đồ, các sự kiện mới **không có cùng mức khẩn cấp**. Một nguy cơ mất toàn vẹn dữ liệu đang xảy ra cần xử lý khác với đề xuất thêm email cho trải nghiệm sau này.

### 4.3. Câu hỏi người học cần trả lời trước khi đề xuất giải pháp

1. Có sự kiện nào là **sự cố thực sự** cần ứng cứu ngay?
2. Có vấn đề nào chỉ do **yêu cầu chưa rõ** nhưng có thể làm rõ trong phạm vi hiện tại?
3. Những thay đổi nào tạo ra **khả năng sản phẩm mới**?
4. Phần nào bị chặn bởi **phụ thuộc bên ngoài**, phần nào có thể làm độc lập?
5. Nhóm đang thiếu **bằng chứng tích hợp** hay thực sự thiếu code?
6. Product Goal có thay đổi, hay chỉ **kế hoạch đạt mục tiêu** cần thay?
7. Có cách nào giao **một phần giá trị an toàn** mà không đợi tất cả ý tưởng mới?
8. Những gì **không được đánh đổi** dù stakeholder muốn phát hành nhanh?

## 5. Kỹ thuật quan trọng nhất: sự kiện, diễn giải, giả thuyết, quyết định

### 5.1. Bốn lớp thông tin

| Lớp | Ví dụ trong ca | Cách kiểm tra |
| --- | --- | --- |
| **Quan sát/sự kiện** | Trong một test tích hợp, hai request đồng thời được xác nhận dù chỉ còn một chỗ. | Lưu version/test data/các bước và tái hiện. |
| **Diễn giải** | “Hệ thống đăng ký có thể đang không bảo vệ sức chứa.” | Hợp lý như cảnh báo, chưa đủ là kết luận nguyên nhân. |
| **Giả thuyết nguyên nhân** | “Hai request cùng đọc số chỗ trước khi ghi, không có cơ chế đồng bộ transaction.” | Kiểm tra transaction, constraints, isolation, logs và test concurrency. |
| **Quyết định/hành động** | Tạm không mở rộng chức năng; xác minh lỗi, sửa cơ chế đúng và kiểm thử hồi quy. | Đúng người có quyền quyết, bằng chứng DoD và mức rủi ro. |

Phân biệt bốn lớp giúp tránh **chữa nhầm nguyên nhân**. Một test bị lỗi không tự chứng minh bug ở DB; có thể test data không được reset, mock trả sai, hoặc một logic thực đã sai.

### 5.2. Mẫu câu phân tích có căn cứ

> “Trong môi trường kiểm thử **phiên bản X**, kịch bản hai học viên tranh chỗ cuối **đã thất bại hai lần**. Chúng tôi chưa xác minh root cause hay mức tác động production. Giả thuyết ưu tiên là điều kiện giao dịch/ghi sức chứa chưa bảo đảm đồng thời. Nhóm sẽ tái hiện bằng test có dữ liệu cách ly, kiểm tra transaction và xem dữ liệu thực theo thẩm quyền; chưa coi hành vi đăng ký này đạt DoD.”

Câu này tốt hơn:

> “Database team làm lỗi, cần viết lại toàn bộ API ngay.”

Vế thứ hai vừa **quy lỗi khi chưa có bằng chứng**, vừa chọn giải pháp lớn khi chưa biết cơ chế.

### 5.3. Không dùng “Agile thích ứng” làm lý do thay đổi tùy tiện

Thích ứng có trách nhiệm cần:

1. **Một tín hiệu mới** hoặc bằng chứng làm thay đổi hiểu biết trước đây.
2. **Tác động** tới giá trị, rủi ro, khả năng đạt mục tiêu hoặc điều kiện Done.
3. **Những lựa chọn thực tế** cùng chi phí/đánh đổi.
4. **Người có thẩm quyền** và giới hạn phải giữ.
5. **Cách kiểm chứng** hành động mới có hữu ích không.

Không phải mọi yêu cầu mới đều cần đưa vào ngay; không phải mọi kế hoạch cũ đều phải giữ vì “đã cam kết”.

## 6. Phân loại tín hiệu thay đổi để biết cần thích ứng ở đâu

### 6.1. Không đánh đồng mọi thay đổi thành mở rộng phạm vi

Trong ca Học Mở, mỗi sự kiện đòi hỏi kiểu quyết định khác nhau:

| Tín hiệu | Loại chính | Nhu cầu thích ứng | Ranh giới không được bỏ |
| --- | --- | --- | --- |
| “Đăng ký thành công” chưa rõ nghĩa khi timeout | **Làm rõ hành vi đã cần có** và cải thiện trải nghiệm | Thống nhất trạng thái cuối, cơ chế tra kết quả và xử lý retry. | Dữ liệu thực phải đúng; không trả xác nhận giả. |
| Test tranh chỗ cuối thất bại | **Defect/rủi ro chất lượng** | Điều tra, sửa cơ chế đồng thời, test hồi quy trên DB phù hợp. | Không vượt sức chứa, DoD phải đạt. |
| PO đề nghị thêm email | **Nhu cầu khả năng mới hoặc điều kiện chưa làm rõ** | Xác minh email có bắt buộc không; nếu không, đánh giá giá trị và xếp backlog. | Nếu email là nghĩa vụ thật thì không được tự bỏ. |
| Stakeholder muốn danh sách chờ | **Mở rộng sản phẩm** | Khám phá quy tắc thứ tự, thông báo, thời hạn và quyền hủy; tách PBI. | Không lẫn trạng thái “đang chờ” với “đã đăng ký”. |
| IdP sắp đổi claims | **Rủi ro phụ thuộc/versioning** | Xác minh hợp đồng hiện hành, ảnh hưởng consumer, contract/security tests. | Không hạ kiểm tra token hoặc quyền. |
| Staging không sẵn | **Trở ngại luồng/khả năng kiểm chứng** | Làm rõ owner, môi trường thay thế hợp lệ, self-service và dự báo Done. | Không gọi mock xanh là integration PASS. |
| WIP cao và PR chờ | **Vấn đề flow/cách phối hợp** | Giảm batch, kéo việc theo năng lực, giúp hoàn tất, xem nút thắt. | Không tạo metric đẹp bằng cách ẩn item. |
| Quản lý yêu cầu mở toàn bộ người dùng đúng ngày | **Áp lực phát hành/ra quyết định** | Công khai rủi ro, giới hạn bằng chứng, các phương án release/no-go. | Người có quyền quyết và kiểm soát bắt buộc. |

Một sự kiện có thể thuộc **nhiều loại**. Ví dụ timeout vừa là khoảng trống acceptance criteria vừa là cơ hội giảm ticket support. Phân loại để **chọn câu hỏi và hành động**, không để tranh luận nhãn.

### 6.2. Thay đổi hiểu biết khác thay đổi Product Goal

**Product Goal** vẫn có thể là tự đăng ký đáng tin cậy, trong khi nhóm thay:

- Cách phản hồi sau timeout.
- Thứ tự các PBI.
- Cách phân chia lát cắt.
- Kế hoạch tích hợp với IdP.
- Chính sách WIP và cách kiểm thử.
- Mốc release nếu chưa đạt chuẩn.

Không nên kết luận “Product Goal phải đổi” mỗi khi một test thất bại. Ngược lại, nếu bằng chứng cho thấy người học **không cần tự đăng ký** hoặc rào cản thật là tính đủ điều kiện pháp lý, có thể cần Product Owner và stakeholders xem lại hướng sản phẩm.

### 6.3. Nhu cầu thích ứng có nhiều tầng

~~~mermaid
flowchart TD
    A["Tín hiệu / bằng chứng mới"] --> B{"Tác động chính ở đâu?"}
    B --> C["Giá trị / giả định người dùng"]
    B --> D["Yêu cầu / phạm vi / thứ tự"]
    B --> E["Kỹ thuật / chất lượng / vận hành"]
    B --> F["Flow / phụ thuộc / phối hợp"]
    C --> G["Khám phá, đo outcome, điều chỉnh mục tiêu khi cần"]
    D --> H["Refine, chia lát cắt, re-order backlog"]
    E --> I["Điều tra lỗi, test, CI, kiến trúc, safety gate"]
    F --> J["VSM, WIP, contract, owner, escalation"]
    G --> K["Kiểm chứng kết quả và guardrails"]
    H --> K
    I --> K
    J --> K
~~~

Sơ đồ dùng để **chọn điểm bắt đầu**. Trong thực tế, một kế hoạch thích ứng tốt thường phối hợp nhiều tầng; ví dụ xử lý lỗi concurrency cần kỹ thuật, nhưng cũng cần đổi thứ tự backlog và thông tin minh bạch về release.

### 6.4. Khi nào chỉ cần làm rõ, khi nào cần quyết định phạm vi?

Một tiêu chí có ích:

- Nếu câu trả lời giúp xác định **hành vi cần thiết để đáp ứng mục tiêu đã chọn** mà không tạo capability mới, đó thường là **refinement/làm rõ**.
- Nếu câu trả lời thêm hành vi, kênh, nhóm người dùng, nghĩa vụ hoặc chi phí khác đáng kể, có thể là **thay đổi phạm vi**.
- Nếu hành vi triển khai **sai so với tiêu chí đã được xác nhận**, cần xem như **defect**, không tự xếp vào “yêu cầu mới để làm Sprint sau”.
- Nếu luật/quy định hoặc nguy cơ nghiêm trọng xuất hiện, phải xử lý theo **thẩm quyền và yêu cầu bắt buộc**.

Ví dụ, làm rõ việc hai yêu cầu đồng thời không được vượt sức chứa là **điều kiện tính đúng đắn** khi hệ thống đang bán/giữ chỗ hữu hạn; không nên biến nó thành “nice-to-have”. Còn danh sách chờ khi hết chỗ là **khả năng sản phẩm khác**, cần hiểu quy tắc và giá trị.

## 7. Phân tích người dùng và xác định outcome thích ứng

### 7.1. Hành trình người học theo thời gian

Một user journey có thể chia:

1. **Tìm hiểu:** học viên xem khóa, lịch học và điều kiện.
2. **Xác thực:** hệ thống biết ai đang thực hiện.
3. **Quyết định:** học viên thấy khóa còn chỗ và thông tin cần thiết.
4. **Yêu cầu đăng ký:** gửi hành động cần được xử lý đúng.
5. **Nhận phản hồi:** thành công, hết chỗ, đã đăng ký hoặc đang chưa biết trạng thái.
6. **Tự xác minh:** xem danh sách khóa của mình hoặc tra trạng thái sau lỗi mạng.
7. **Tham gia:** nhận hướng dẫn tiếp theo khi đã được xác nhận.

Nếu bước 4 đã ghi dữ liệu nhưng bước 5 mất phản hồi, từ góc nhìn người học **nhiệm vụ chưa được giải thích rõ**. Đây là một thất bại trải nghiệm đáng phân tích dù server đã commit thành công.

### 7.2. Thói quen hỏi “điều gì xảy ra tiếp theo?”

Đặt các câu hỏi cho mỗi bước:

- Người học nhìn thấy gì?
- Hệ thống biết điều gì và **chưa thể biết điều gì**?
- Điều gì được ghi thành dữ liệu thật?
- Quyền của người học giới hạn những gì được xem/thay đổi?
- Nếu lỗi xảy ra ở đây, người học có đường phục hồi không?
- Support có biết cách kiểm tra và giải thích an toàn không?
- Điều gì chứng minh hành vi ấy **hữu ích**, thay vì chỉ có code chạy?

Đây là cách nối **user story** với **outcome**, không biến nó thành danh sách màn hình cần xây.

### 7.3. Phân biệt output và outcome

| Mức | Ví dụ | Cách kiểm chứng |
| --- | --- | --- |
| **Activity** | Họp refinement, viết test concurrency. | Công việc đã thực hiện, artifact tạo ra. |
| **Output** | Endpoint đăng ký, trang tra trạng thái, pipeline integration. | Chạy/kiểm tra bản tích hợp, đạt DoD. |
| **Outcome** | Học viên tự hoàn tất và biết trạng thái đúng, ít phải hỏi support. | Phân tích hành vi đã được phép đo và phản hồi thực. |
| **Impact dài hạn** | Giảm xử lý thủ công và tăng mức tin cậy học viên. | Theo dõi bền vững với bối cảnh và yếu tố khác. |

Không suy rằng **tỷ lệ tự đăng ký tăng** chỉ từ số PR đã merge. Ngược lại, một outcome tốt đôi khi đạt bằng **thay đổi thông báo và tự tra trạng thái** nhỏ, thay vì xây một phân hệ mới lớn.

### 7.4. Xác định một outcome đủ cụ thể

Một outcome để thử cải tiến có thể là:

> “Trong đợt thử với người dùng đủ điều kiện và định nghĩa đo nhất quán, tăng tỷ lệ lượt bắt đầu đăng ký có **trạng thái cuối được xác minh rõ** mà không làm tăng trường hợp sai dữ liệu/vi phạm quyền; đồng thời giảm ticket hỏi kết quả mơ hồ tính theo cách đo đã công bố.”

**Không tự đặt ngưỡng cam kết** từ ví dụ ít dữ liệu. Có thể đưa ra target để học, ví dụ mục tiêu thử từ 74% lên **ít nhất 85%** lượt hoàn tất theo định nghĩa, nhưng target phải được ghi là **giả thuyết/đích mong muốn** và cần quan sát độ tin cậy, biến động loại người dùng, tác động support.

### 7.5. Đâu là nguy cơ “xây thứ không ai cần”?

Stakeholder muốn email và danh sách chờ. Cần kiểm chứng:

- Người học thực sự cần email hay chỉ cần trạng thái có thể tra sau timeout?
- Có yêu cầu thông báo bắt buộc theo hợp đồng/chính sách không?
- Khi hết chỗ, người học muốn biết khóa tương tự hay thật sự muốn xếp hàng?
- Danh sách chờ có cần quy tắc giữ chỗ, hết hạn, thứ tự ưu tiên và quyền hủy không?
- Dịch vụ email thêm rủi ro trùng/tiết lộ thông tin hay không?

Không được từ chối ý tưởng chỉ vì “không nằm Sprint hiện tại”; cũng không nên đưa tất cả ý tưởng vào ngay khi chưa biết **giá trị, chi phí, rủi ro và phụ thuộc**.

## 8. Phân tích dòng giá trị: tại sao nhiệm vụ chưa hoàn tất?

### 8.1. Value Stream Mapping của lát cắt đăng ký

Theo một giả định cụ thể, dòng từ PBI được chọn tới Increment có thể phát hành gồm:

~~~mermaid
flowchart LR
    A["Refinement / ví dụ nghiệp vụ"] --> B["Hợp đồng UI–API"]
    B --> C["Phát triển dọc lát cắt"]
    C --> D["Review / CI"]
    D --> E["Kiểm thử tích hợp"]
    E --> F["Đạt DoD"]
    F --> G["Release / quan sát"]
    E -. "Rework" .-> B
    G -. "Phản hồi người học" .-> A
~~~

Cần gắn dữ liệu **chờ, active, blocker và vòng rework** lên sơ đồ. Không tự coi một bước “QA” là lãng phí chỉ vì nó ở cuối; vấn đề là **kiểm chứng đến muộn do thiết kế công việc**, thiếu môi trường hoặc lệch hợp đồng.

### 8.2. Ví dụ thời gian của một item — không phải trung vị toàn nhóm

Để luyện phân tích, xét **một PBI đã hoàn tất** đi qua các khoảng **không chồng lấn**, cùng đơn vị là ngày làm việc:

| Giai đoạn | Active time | Waiting time | Tín hiệu |
| --- | ---: | ---: | --- |
| Làm rõ hành vi | 0,5 | 1,5 | Chờ người quyết khi hết chỗ. |
| Contract UI–API | 0,5 | 1 | Hai nhóm hiểu khác mã lỗi. |
| Phát triển | 2 | 1 | Chuyển ngữ cảnh sang item khác. |
| Review và CI | 0,5 | 1,5 | PR chờ review và CI queue. |
| Tích hợp/kiểm chứng | 1 | 2 | Staging thiếu dữ liệu và test cạnh tranh. |
| **Tổng** | **4,5** | **7** | **11,5 ngày** theo mô hình tuần tự. |

Trong mẫu minh họa:

\[
\text{Elapsed time}=4,5+7=11,5\text{ ngày}.
\]

\[
\text{Flow efficiency}
=\frac{4,5}{11,5}\times100\%
\approx39,1\%.
\]

Chỉ số này **không phải điểm năng suất của cá nhân**. Nếu các khoảng thời gian thực chồng lấn, không thể cộng person-days vào elapsed time. Và việc giảm active time bằng cách bỏ phép kiểm chứng bắt buộc có thể làm tỷ số đẹp hơn nhưng tăng rủi ro.

### 8.3. Nhận diện Muda, Mura, Muri

| Dấu hiệu | Nhóm nguyên nhân cần kiểm chứng | Dạng Lean liên quan |
| --- | --- | --- |
| Nhiều ticket qua UI → API → QA → DB | Chia việc theo lớp tạo handoff; thông tin truyền thiếu. | **Muda: transportation**, có thể thêm defects/rework. |
| WIP có item 15 ngày chưa Done | Mở nhiều việc và thiếu điều kiện kiểm chứng. | **Muda: inventory/waiting**, cần xem mức chờ thật. |
| Dồn PR vào ngày cuối Sprint | Batch lớn, kiểm thử không được đưa sớm. | **Mura** và waiting. |
| Một reviewer nhận mọi thay đổi DB | Quyền/kiến thức tập trung, công suất hữu hạn. | **Muri** tại reviewer, waiting ở upstream. |
| CI chạy lại do flaky | Môi trường/test không ổn định. | **Muda: defects/overprocessing/waiting**. |
| Danh sách chờ được xây trước khi cần | Chưa có bằng chứng outcome, scope phình. | Có nguy cơ **overproduction**. |

Không mặc định một hoạt động là waste nếu nó bảo vệ dữ liệu hoặc pháp lý. Lean nhấn mạnh **loại bỏ chờ và làm lại không cần thiết**, không phải bỏ chất lượng.

### 8.4. Điểm nghẽn là hệ thống, không nhất thiết là người

Nếu cả ba item cùng chờ DB test, cần hỏi:

- Môi trường có thiếu công suất hay thiếu quyền cấp?
- Dữ liệu thử được tạo theo cách thủ công hay tự phục vụ an toàn?
- Test có phụ thuộc một phiên bản API chưa thống nhất?
- Có thể tích hợp sớm hơn với data fixtures và contract tests?
- Những item đó đã cần DB test từ đầu nhưng bị phát hiện quá muộn?

Giải pháp “thêm một tester” **chưa chắc có ích** nếu tester vẫn không có môi trường chạy.

## 9. Phân tích chất lượng và chọn rủi ro phải xử lý trước

### 9.1. Ba loại rủi ro trong ca

**Rủi ro tính đúng đắn dữ liệu:**

- Đăng ký trùng.
- Vượt sức chứa.
- Trả thành công khi transaction chưa commit.
- Tình trạng mơ hồ khi retry sau timeout.

**Rủi ro bảo mật và riêng tư:**

- Người dùng đọc dữ liệu đăng ký của người khác.
- Tin vào claim không được bảo đảm.
- Token hết hạn hoặc sai audience vẫn được chấp nhận.
- Gửi thông tin cá nhân lên sandbox sai quyền.

**Rủi ro luồng và phát hành:**

- Integration tests không thể chạy đúng hạn.
- Một dependency vendor biến thành blocker.
- Thay schema không tương thích consumer cũ.
- Không có monitoring/runbook khi mở cho nhiều người.

Rủi ro có thể **đan xen**. Một lỗi token khiến hệ thống tin nhầm danh tính là vấn đề bảo mật, có thể dẫn tới đăng ký sai chủ thể và dữ liệu sai.

### 9.2. Ví dụ bảng rủi ro theo hành động

| Rủi ro | Bằng chứng hiện tại | Điều cần xác minh | Hành động ưu tiên |
| --- | --- | --- | --- |
| Vượt sức chứa khi đồng thời | Hai lần test không đạt. | DB schema/transaction, kịch bản tái hiện; tác động production nếu có. | Triage, ngăn mở rộng tác động; sửa và kiểm thử hồi quy. |
| Dữ liệu đăng ký trùng | Ba dấu hiệu cần điều tra. | Có thật là trùng hiệu lực, nguyên nhân và phạm vi ảnh hưởng? | Đối soát theo quyền, sửa/khôi phục dữ liệu an toàn. |
| Trạng thái mơ hồ sau timeout | 12 ticket cùng chủ đề. | Server có thể đã commit? UI có đường tra lại? | Làm rõ nghiệp vụ, thiết kế idempotency/tra trạng thái, test. |
| Claims IdP thay đổi | Có thông báo dự kiến. | Hợp đồng mới có breaking change? v1 còn hỗ trợ? | Inventory consumer, contract/security tests và kế hoạch version. |
| Staging không dùng được | Có item bị blocked. | Công suất, quyền, phiên bản, dữ liệu test? | Owner rõ, sửa nút thắt và công khai ảnh hưởng tới DoD. |

**Thứ tự xử lý** không chỉ dựa số lượng ticket: một lỗi quyền hoặc sai sức chứa nghiêm trọng có thể đáng xử lý trước một cải tiến UI được nhiều người yêu thích.

### 9.3. Không biến rủi ro thành cớ trì hoãn mọi thứ

Cần phân biệt:

- **Điều kiện bắt buộc** để phần chức năng được coi Done/usable.
- **Hạn chế đã biết** chưa ảnh hưởng phần scope đang giao, có thể đưa backlog với owner.
- **Giả thuyết chưa kiểm chứng**, cần một spike/test ngắn.
- **Sự cố đang diễn ra**, cần ứng cứu ngay, không chờ quy trình backlog thông thường.

Nếu phần ghi đăng ký hiện có nguy cơ vượt sức chứa, có thể tạm **không mở chức năng ghi mới** và vẫn tạo những thay đổi an toàn không kích hoạt tính năng. Nhưng không được tuyên bố khả năng **tự đăng ký** đã hoàn tất nếu điều kiện này chưa đạt.

### 9.4. Phản ứng phù hợp với phát hiện concurrency

Một cách tiếp cận:

1. **Tái hiện** với DB và logic transaction phù hợp, test data cách ly.
2. Xem DB constraints, isolation, locking, idempotency và cơ chế giữ chỗ theo thiết kế.
3. Xác định giải pháp đúng với quy tắc nghiệp vụ, không chỉ thêm retry vô điều kiện.
4. Chạy test đồng thời đủ để kiểm chứng không xác nhận vượt chỗ trong các điều kiện quan trọng.
5. Bổ sung test hồi quy và khả năng quan sát.
6. Nếu có dữ liệu sai đã tồn tại, đối soát/khôi phục theo thẩm quyền và kế hoạch bảo vệ người dùng.
7. Chỉ mở khả năng ghi khi các điều kiện chất lượng cần thiết đã đạt.

Không có một dòng SQL hoặc một kiểu khóa nào **luôn giải quyết được mọi dạng tranh chỗ**. Thiết kế cần tương thích DB, transaction, hành vi retry, phân tán dịch vụ và định nghĩa “đăng ký hiệu lực” thực tế.

## 10. Làm rõ yêu cầu bằng ví dụ, user story và acceptance criteria

### 10.1. Tách những câu hỏi nghiệp vụ chưa được trả lời

Trước khi chọn phương án kỹ thuật, cần làm rõ:

- “Đăng ký thành công” là **khi request được nhận** hay **khi dữ liệu được commit**?
- Nếu học viên đã đăng ký trước đó, UI cần hiển thị điều gì?
- Nếu hết chỗ ngay khi người dùng bấm, kết quả là gì?
- Nếu mạng mất sau commit, người học có thể **tra lại trạng thái thật** bằng cách nào?
- Nếu cùng một request được gửi lại, điều gì xác định đó là yêu cầu lặp?
- Nếu cần giữ chỗ tạm, giữ bao lâu và có giới hạn nào?
- Quyền truy cập của học viên, support và quản trị khác nhau thế nào?
- Email là **kênh bổ sung**, điều kiện bắt buộc, hay một dự đoán chưa được xác nhận?

Những câu hỏi này nên được thảo luận giữa PO, Developers, chuyên môn kiểm thử, vận hành và người có quyền quyết nếu liên quan hợp đồng/bảo mật.

### 10.2. Một user story tập trung giá trị

> **Là** học viên đã đăng nhập và đủ điều kiện, **tôi muốn** tự đăng ký khóa học miễn phí còn chỗ và kiểm tra trạng thái cuối, **để** biết chắc mình có thể tham gia mà không cần nhờ nhân viên hỗ trợ.

User story là **lời mời đối thoại**, không thay toàn bộ đặc tả. Các ví dụ quan trọng nên được chuyển thành acceptance criteria/kiểm thử có thể kiểm chứng.

### 10.3. Ví dụ Gherkin cho đường thành công và thất bại

~~~gherkin
Feature: Tự đăng ký khóa học miễn phí an toàn

  Scenario: Đăng ký khóa còn chỗ
    Given học viên A đã được xác thực và đủ điều kiện
    And khóa X là khóa miễn phí còn ít nhất một chỗ
    When A gửi yêu cầu đăng ký khóa X
    Then hệ thống lưu đúng một đăng ký hiệu lực của A cho X
    And A nhận trạng thái xác nhận tương ứng với dữ liệu đã commit

  Scenario: Học viên gửi lại khi đã đăng ký
    Given học viên A đã có một đăng ký hiệu lực cho khóa X
    When A gửi lại yêu cầu đăng ký X theo cơ chế đã định
    Then hệ thống không tạo bản ghi đăng ký hiệu lực thứ hai
    And A có thể xem trạng thái đã đăng ký

  Scenario: Hết chỗ trước khi xác nhận
    Given khóa X không còn chỗ được phép xác nhận
    When học viên đủ điều kiện gửi yêu cầu đăng ký X
    Then hệ thống không xác nhận thêm đăng ký vượt sức chứa
    And trả thông tin hết chỗ rõ ràng

  Scenario: Hai học viên tranh chỗ cuối
    Given khóa X còn đúng một chỗ
    When hai học viên đủ điều kiện gửi yêu cầu đồng thời
    Then tối đa một đăng ký mới được xác nhận
    And số đăng ký hiệu lực không vượt sức chứa

  Scenario: Mất phản hồi sau khi dữ liệu đã commit
    Given yêu cầu hợp lệ của A đã được xử lý và commit thành công
    And phản hồi bị gián đoạn trước khi tới trình duyệt
    When A tra trạng thái hoặc gửi lại theo cơ chế idempotent đã thiết kế
    Then không có đăng ký hiệu lực trùng của A cho X
    And A có thể biết trạng thái thật của mình

  Scenario: Truy cập trạng thái của người khác trái quyền
    Given B không có quyền xem đăng ký riêng của A
    When B yêu cầu đọc trạng thái đăng ký của A qua API
    Then hệ thống từ chối truy cập ở phía server
    And không tiết lộ dữ liệu riêng của A
~~~

Các kịch bản **minh họa hành vi**. Chúng cần được hiện thực và chạy ở tầng phù hợp; Gherkin viết đẹp chưa tự là **test PASS** trên DB, IdP hoặc production.

### 10.4. Acceptance criteria khác Definition of Done

**Acceptance criteria** làm rõ điều một hạng mục cụ thể phải đáp ứng, như “không tạo đăng ký trùng”. **Definition of Done** là cam kết về chất lượng của Increment, có thể gồm kiểm thử, tích hợp, bảo mật, tài liệu hỗ trợ hoặc các điều kiện liên quan theo sản phẩm.

Không được cộng một tập story có acceptance criteria xanh nhưng **chưa tích hợp** rồi gọi toàn bộ Increment Done. Ngược lại, có thể có một thay đổi kỹ thuật đạt test cục bộ và merge an toàn mà **chức năng người dùng chưa được coi hoàn tất** nếu còn điều kiện nghiệp vụ bắt buộc chưa đạt.

## 11. Những thông tin còn thiếu: lập kế hoạch học trước khi lập kế hoạch làm

### 11.1. Dữ liệu hiện tại chưa đủ để quyết định mọi thứ

Một đội vội vàng có thể nói “lỗi concurrency chắc là do DB” hoặc “chỉ cần thêm email là ticket support sẽ giảm”. Cả hai đều là **giả thuyết chưa được kiểm chứng**. Trước khi cam kết thay đổi lớn, cần thu thêm thông tin theo mức tác động.

| Câu hỏi chưa có câu trả lời | Vì sao quan trọng? | Cách lấy bằng chứng hợp lệ |
| --- | --- | --- |
| Ba trường hợp nghi đăng ký trùng có thật sự là hai bản ghi **hiệu lực**? | Xác định mức sai dữ liệu và tác động học viên. | Đối soát log/DB theo quyền, phân biệt trạng thái hủy/nháp/hiệu lực. |
| Test tranh chỗ cuối có tái hiện ổn định không? | Tách lỗi nghiệp vụ khỏi test data/setup. | Chạy lại có điều kiện, phiên bản và dữ liệu cách ly. |
| Người học đang hiểu thông báo timeout thế nào? | Biết vấn đề UI, mạng hay trạng thái server. | Quan sát tác vụ có đồng ý, phân loại ticket ẩn danh. |
| Contract token nào IdP bảo đảm ở phiên bản hiện tại? | Đánh giá có thể tiếp tục tích hợp an toàn không. | Đọc hợp đồng đã xác nhận và contract/security tests. |
| Email có phải điều kiện bắt buộc? | Quyết định phạm vi, thời gian và rủi ro notification. | PO trao đổi người có quyền, kiểm tra chính sách/hợp đồng. |
| Staging bị chặn do công suất, quyền hay cấu hình? | Chọn self-service, tăng công suất hay sửa pipeline. | Log cấp môi trường, sự cố, kiểm tra quyền và lịch chờ. |
| PR chờ lâu do kích thước, reviewer hay CI? | Tránh chọn sai giải pháp. | Lịch sử PR với mốc ready/review/CI. |
| 148/200 lượt hoàn tất còn thiếu do đâu? | Xác định outcome và đối tượng cần cải tiến. | Phân loại lỗi, chưa hoàn tất có chủ đích, dữ liệu đo thiếu. |

### 11.2. Phân biệt câu hỏi cần trả lời ngay và có thể trả lời dần

Nhóm có thể dùng ba nhóm:

- **Cần biết ngay để bảo vệ người dùng:** có dữ liệu sai hay lộ dữ liệu đang xảy ra? Tính năng có nên ngừng mở rộng? Ai có quyền ứng cứu?
- **Cần biết trước khi chọn PBI/đạt Done:** hành vi cần thiết, hợp đồng IdP, môi trường test, điều kiện DoD.
- **Có thể học qua các vòng nhỏ:** người dùng có thực sự cần danh sách chờ không, cách thông báo nào dễ hiểu nhất, giá trị email so với trang tra trạng thái.

Không dùng thử nghiệm sản phẩm thông thường để **học bằng cách cố tình đưa dữ liệu người dùng vào rủi ro không thể chấp nhận**. Những kiểm soát bắt buộc phải đi trước hoặc song song trong môi trường an toàn.

### 11.3. Timebox hoạt động khám phá

Một hoạt động điều tra ngắn (spike/discovery) có thể có mục tiêu:

> “Xác minh điều kiện xảy ra đăng ký trùng, phác họa cơ chế bảo đảm sức chứa và chứng minh một hướng sửa có thể kiểm thử trên DB phù hợp.”

Đầu ra **không nhất thiết là Increment dùng được**. Có thể là test tái hiện, kết luận về giả thuyết, ADR kỹ thuật và thay đổi dự báo. Cần ghi rõ **điều đã học**, không gọi “đã nghiên cứu 3 ngày” là giá trị người dùng được giao.

### 11.4. Một giả định tốt phải có cách bác bỏ

Giả thuyết: “Nhiều ticket hỏi trạng thái do frontend mặc định báo thất bại sau timeout”.

Để kiểm chứng:

1. Xác minh request server có thể đã commit dù client mất phản hồi.
2. Xem UI thực trả thông báo gì và test các tình huống mất mạng.
3. Kiểm tra ticket support có trùng trạng thái không rõ không.
4. Thử cách tra trạng thái an toàn trên bản tích hợp.
5. Nếu UI không báo sai nhưng ticket vẫn cao, xem nguyên nhân khác như truy cập tài khoản, quyền hoặc cách đặt tên trạng thái.

Giả thuyết phải **có thể sai**. “Chúng ta chắc chắn cần thiết kế lại toàn bộ màn hình” không phải giả thuyết đủ cụ thể.

## 12. Xác định nhu cầu thích ứng bằng ma trận tác động và tính khẩn cấp

### 12.1. Không gán điểm bằng trực giác rồi coi là sự thật

Để thảo luận ưu tiên, có thể xét:

- **Giá trị hoặc thiệt hại tới người dùng** nếu chưa hành động.
- **Mức độ rủi ro về dữ liệu, bảo mật và tính đúng đắn**.
- **Mức chắc chắn của bằng chứng**.
- **Tính cấp thiết theo thời điểm** và phụ thuộc bên ngoài.
- **Chi phí/công sức và khả năng chia lát cắt**.
- **Khả năng học thêm với một thử nghiệm nhỏ**.
- **Tác động tới Product Goal hoặc Sprint Goal**.

Đánh giá định tính **cao/vừa/thấp** có thể hữu ích trước khi có đủ dữ liệu. Không đặt trọng số tùy ý rồi tuyên bố kết quả là “khách quan”, nhất là với nguy cơ dữ liệu nghiêm trọng.

### 12.2. Bảng quyết định minh họa

| Vấn đề/đề nghị | Giá trị/hậu quả | Chắc chắn hiện tại | Hướng ưu tiên |
| --- | --- | --- | --- |
| Nguy cơ ghi vượt sức chứa | Hậu quả chất lượng cao; có thể đang ảnh hưởng. | Có test thất bại, nguyên nhân chưa rõ. | **Triage và bảo vệ an toàn ngay**, kiểm chứng/sửa trước mở rộng. |
| Nguy cơ bản ghi trùng | Sai dữ liệu và trải nghiệm; cần đánh giá phạm vi. | Có dấu hiệu cần điều tra. | **Điều tra ưu tiên**, sửa dữ liệu khi có quyền và test hồi quy. |
| Người học không biết kết quả sau timeout | Giá trị người dùng trực tiếp, tăng hỗ trợ. | Ticket có tín hiệu; cơ chế chưa đủ rõ. | Làm rõ/kiểm chứng sớm, đưa vào lát cắt đáng tin. |
| IdP thay claims trong tương lai | Có thể phá tích hợp và quyền. | Có thông báo, chưa biết breaking change. | Phân tích hợp đồng, tạo test/owner, không hoảng loạn đổi toàn bộ ngay. |
| Staging chờ lâu | Chặn bằng chứng DoD và tăng cycle time. | Có item blocked, chưa biết nguyên nhân. | Điều tra điểm nghẽn, giảm phụ thuộc và công khai dự báo. |
| Email xác nhận | Có thể tăng trải nghiệm, thêm phụ thuộc. | Chưa rõ bắt buộc và giá trị tương đối. | Làm rõ phạm vi; cân nhắc backlog sau phần cốt lõi. |
| Danh sách chờ | Giá trị tiềm năng nhưng nghiệp vụ mới. | Chưa có nghiên cứu nhu cầu/quy tắc. | Discovery/refinement rồi mới cam kết triển khai. |
| Giữ mốc mở rộng cho mọi người | Có giá trị kinh doanh nhưng tăng rủi ro. | Chưa đạt bằng chứng tích hợp. | Quyết định release dựa trên DoD và an toàn; có thể No-go. |

**Thứ tự này là gợi ý cho ca**, không phải một thuật toán ưu tiên chuẩn cho mọi tổ chức. Khi nguy cơ dữ liệu thực sự đang xảy ra, **đường ứng cứu** có thể vượt ngoài thứ tự PBI thông thường.

### 12.3. Đừng đếm “bao nhiêu người yêu cầu” làm thước đo duy nhất

Một lãnh đạo muốn email, trong khi ba ticket báo trùng dữ liệu. **Một lỗi toàn vẹn dữ liệu** có thể phải ưu tiên hơn số lần đề nghị thay đổi giao diện. Ngược lại, nếu dữ liệu đã an toàn và người học rất cần thông báo theo nghĩa vụ đã xác minh, email có thể trở thành quan trọng.

Trọng tâm là **hậu quả, giá trị và điều kiện bắt buộc**, không chỉ số phiếu bầu hoặc vị trí người đưa ra ý tưởng.

### 12.4. Dùng Cost of Delay/WSJF khi dữ liệu đủ phù hợp

Một nhóm có thể dùng tư duy **Cost of Delay (CoD)**: việc trì hoãn kết quả gây thiệt hại/đánh mất cơ hội gì theo thời gian? **WSJF** thường được mô tả ở dạng tỷ số tương đối:

\[
\text{WSJF}\approx
\frac{\text{Relative Cost of Delay}}{\text{Relative Job Size}}.
\]

Trong đó CoD có thể được ước lượng theo các thành phần như giá trị kinh doanh, mức cấp thiết theo thời điểm và giảm rủi ro/tạo cơ hội, tùy cách tổ chức dùng. Đây là **công cụ hỗ trợ đối thoại**, không tự đo chính xác số tiền hay thay kiểm soát chất lượng.

**Ví dụ hoàn toàn giả định**, sau khi đã xử lý nguy cơ dữ liệu bắt buộc:

| PBI | CoD tương đối | Size tương đối | Tỷ số WSJF minh họa |
| --- | ---: | ---: | ---: |
| Bổ sung đường tra trạng thái an toàn | 12 | 3 | 4,0 |
| Cải thiện dashboard nội bộ | 5 | 5 | 1,0 |
| Email thông báo tùy chọn | 6 | 3 | 2,0 |

Theo **số giả định** này, đường tra trạng thái có tỷ số cao nhất. Nhưng không dùng bảng này để kết luận **phải bỏ sửa lỗi concurrency** vì lỗi đó không phải một feature tùy chọn được so bằng điểm CoD tùy tiện. Bảo đảm dữ liệu là guardrail trước khi giao khả năng ghi.

### 12.5. Khi dữ liệu chưa đủ, dùng thử nghiệm nhỏ

Nếu không rõ email có giảm ticket support hay không:

1. Xác minh email có bắt buộc hay không.
2. Quan sát nguyên nhân câu hỏi “đã đăng ký chưa?”.
3. Thử cải thiện UI và đường tra trạng thái nếu đó là nguyên nhân phù hợp.
4. Đo outcome và ticket theo cùng định nghĩa.
5. Sau đó cân nhắc email theo giá trị còn thiếu và rủi ro notification.

Điều đó có thể **tránh overproduction**, giảm phụ thuộc vendor và tập trung vào Product Goal.

## 13. Chia việc theo lát cắt giá trị và giữ điều kiện Done

### 13.1. Vì sao chia theo tầng kỹ thuật gây lệch kế hoạch?

Một kế hoạch kiểu:

~~~text
Story A: Hoàn tất UI đăng ký
Story B: Hoàn tất toàn bộ REST API
Story C: Hoàn tất schema và stored procedures
Story D: QA kiểm tra tất cả vào cuối Sprint
Story E: Integrate và deploy khi mọi nhóm xong
~~~

có thể tạo “Done” cục bộ nhưng không có **phần tăng trưởng sản phẩm** nào sử dụng được. Khi hai tầng hiểu khác “hết chỗ”, lỗi chỉ lộ ở D/E. Hệ thống có nhiều **handoff và rework**.

### 13.2. Lát cắt dọc — kỹ thuật và giá trị phải gặp nhau

Có thể tổ chức các PBI như sau, tùy yêu cầu thực:

| Lát cắt | Giá trị / khả năng quan sát | Điều kiện an toàn không được bỏ |
| --- | --- | --- |
| **A. Xem thông tin và số chỗ theo quy tắc** | Người học chọn được khóa phù hợp. | Quyền hiển thị và tính đúng đắn dữ liệu ở mức đã xác định. |
| **B. Đăng ký khóa miễn phí** | Người học đủ điều kiện tự đăng ký. | Xác thực, phân quyền, không trùng, không vượt sức chứa, test tích hợp. |
| **C. Xác minh trạng thái sau timeout** | Người học không phải đoán thành công/thất bại. | Trạng thái lấy từ dữ liệu thật, idempotency và quyền truy cập. |
| **D. Thông báo email bổ sung** | Thêm kênh xác nhận nếu có giá trị. | Đúng người, xử lý trùng/không gửi, riêng tư và nghĩa vụ. |
| **E. Danh sách chờ** | Hỗ trợ nhu cầu khi khóa hết chỗ, nếu đã kiểm chứng. | Quy tắc ưu tiên, giữ chỗ, hủy, thông báo và trạng thái không gây hiểu lầm. |

**Lưu ý quan trọng:** Lát cắt B không được phát hành như **đăng ký hoàn tất** nếu lỗi concurrency và dữ liệu chưa được bảo vệ. Bảng thể hiện **kết quả có thể độc lập khi đạt chuẩn**, không phải chỉ dẫn giao một chức năng thiếu các điều kiện cơ bản.

### 13.3. Có thể chia các bước kỹ thuật an toàn trước khi mở tính năng

~~~mermaid
flowchart LR
    A["Hợp đồng + test hành vi"] --> B["Thay schema tương thích"]
    B --> C["API ghi + kiểm soát transaction"]
    C --> D["UI và tra trạng thái"]
    D --> E["Integration, security, concurrency"]
    E --> F{"Đạt DoD?"}
    F -- "Chưa" --> G["Sửa / kiểm chứng lại"]
    G --> E
    F -- "Có" --> H["Increment dùng được"]
~~~

Nhóm có thể merge các thay đổi nhỏ lên mainline **nếu chúng không phá behavior đang hoạt động và được kiểm soát an toàn**. Điều đó giúp nhận feedback kỹ thuật sớm. Nhưng **một feature flag tắt không tự biến tính năng chưa được kiểm chứng thành Increment dùng được**, và cờ tính năng không thay authn/authz tại server.

### 13.4. Phân chia theo hành vi, không phải chia giả để tăng điểm

Một lát cắt có thể nhỏ về chức năng nhưng phải có:

- Người dùng và mục đích rõ.
- Kết quả kiểm chứng được.
- Kiểm soát cần thiết tương xứng với rủi ro.
- Cách tích hợp và quan sát.
- Không phụ thuộc việc một phần lỗi dữ liệu được hứa “sẽ sửa sau” nếu phần đó đang sử dụng thực.

Chia một yêu cầu thành 20 ticket “đổi tên biến” để tăng throughput không làm **giá trị hoặc khả năng dự báo** tốt hơn.

## 14. So sánh ba hướng thích ứng sai–đúng trong cùng tình huống

### 14.1. Lựa chọn 1: cứ giữ kế hoạch ban đầu

Một cách phản ứng là:

> “Tất cả task đã được giao từ đầu Sprint, cứ làm xong UI, API, email rồi test cuối; ngày phát hành không đổi.”

**Rủi ro:**

- Phát hiện concurrency/rights muộn.
- WIP tiếp tục tăng.
- Không ai xử lý phụ thuộc staging.
- Phần email làm phân tán nguồn lực khỏi giá trị cốt lõi.
- Việc giữ ngày dự báo bằng mọi giá dễ dẫn đến báo Done sai hoặc chuyển rủi ro tới người dùng.

Phương án này chỉ hợp lý nếu kế hoạch **vẫn phù hợp với bằng chứng và DoD**, điều hiện tại chưa được xác lập. “Kiên định” không có nghĩa bỏ qua bằng chứng mới.

### 14.2. Lựa chọn 2: thay toàn bộ framework ngay

Một phản ứng khác:

> “Scrum không hiệu quả, từ mai bỏ Sprint, dựng Kanban board 12 cột, mua tool mới và yêu cầu mọi người cập nhật 4 lần/ngày.”

**Rủi ro:**

- Đổi nhãn nhưng không sửa lỗi dữ liệu.
- Thêm thao tác/báo cáo và chuyển ngữ cảnh.
- Không làm rõ Product Goal, API contract hay điều kiện test.
- Không có baseline để biết công cụ/quy trình mới giúp gì.

Đổi framework **có thể có lý do trong bối cảnh phù hợp**, nhưng không phải đối sách tự động cho một vấn đề kỹ thuật hoặc hàng đợi chưa được phân tích.

### 14.3. Lựa chọn 3: thích ứng theo bằng chứng ở đúng tầng

Một hướng hành động tốt hơn cho ca:

1. **Triage lỗi dữ liệu và quyền**; ngừng mở rộng ảnh hưởng nếu cần.
2. **Làm rõ user story và Gherkin** cho đăng ký, hết chỗ, retry, trạng thái.
3. **Chọn lát cắt giá trị an toàn**, tách những khả năng mới chưa bắt buộc.
4. **Rà soát Sprint Goal/Product Backlog** theo mục tiêu giá trị và quyền Scrum.
5. **Giảm WIP và tích hợp sớm**, gỡ blocker môi trường/contract.
6. **Chạy test thực** qua DB, IdP và hành trình người dùng trước khi tuyên bố Done.
7. **Đo flow và outcome**, cập nhật dự báo/decision log cho stakeholders.
8. **Thử cải tiến nhỏ** ở vấn đề lặp lại, xem kết quả và điều chỉnh.

Đây không phải một danh sách phải thực hiện **tất cả** trong một ngày; cần ưu tiên an toàn và khả năng hiện có, đồng thời giao tiếp minh bạch.

### 14.4. Ma trận phương án và đánh đổi

| Phương án | Lợi ích có thể đạt | Chi phí/rủi ro | Điều kiện chọn |
| --- | --- | --- | --- |
| **Làm rõ contract + acceptance examples** | Giảm hiểu sai, test sớm. | Cần đúng người quyết; thời gian trao đổi. | Mismatch UI–API đang là nguồn rework. |
| **Giảm WIP, ưu tiên finish** | Giảm đổi ngữ cảnh, phơi lộ bottleneck. | Phải thay cách kéo việc, có thể làm “độ bận” giảm. | Có nhiều item dở/blocked và hàng đợi. |
| **Tăng unit tests đơn thuần** | Bảo vệ một số logic cục bộ. | Không chứng minh concurrency/DB/IdP thật. | Bổ trợ chiến lược test theo rủi ro, không thay integration. |
| **Sửa transaction + kiểm chứng concurrency** | Bảo vệ dữ liệu cốt lõi. | Cần kỹ thuật, DB và test phù hợp. | Có bằng chứng/triệu chứng rủi ro dữ liệu. |
| **Tách email/danh sách chờ** | Tập trung mục tiêu, giảm phụ thuộc. | Phải làm rõ nghĩa vụ và truyền thông. | Chúng không bắt buộc cho lát cắt cốt lõi. |
| **Self-service staging có guardrails** | Giảm chờ môi trường lặp. | Chi phí platform, quyền và vận hành. | Chờ môi trường là bottleneck lặp, không thể giải quyết đơn giản. |
| **Mở cho toàn bộ học viên ngay** | Nhận nhiều phản hồi/giá trị nếu thật sự sẵn. | Tác động dữ liệu và người dùng lớn. | **Chỉ hợp lệ khi các kiểm soát/điều kiện release đã đạt**. |

Quyết định tốt là quyết định giải quyết **vấn đề đã xác minh**, có thể đo tác động và giữ guardrails.

## 15. Nếu đang dùng Scrum: điều chỉnh Sprint Goal và Sprint Backlog như thế nào?

### 15.1. Đúng vai trò, đúng quyền

Theo Scrum Guide 2020:

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm và Product Backlog.
- **Developers** lập và thích ứng Sprint Backlog, tạo Increment đáp ứng DoD và giữ trách nhiệm chất lượng chuyên môn.
- **Scrum Master** hỗ trợ hiệu quả Scrum, giúp tháo gỡ trở ngại và cải tiến.

Đội không được chuyển mọi quyết định về kỹ thuật, phạm vi và hợp đồng cho một quản lý “Scrum Project Manager” không phải accountability của Scrum.

### 15.2. Ví dụ Sprint Goal trước và sau khi làm rõ

**Cách đặt yếu:**

> “Hoàn thành tất cả ticket Web, API, DB, email và báo cáo trước thứ Sáu.”

**Cách đặt hướng giá trị:**

> “Học viên đủ điều kiện có thể tự đăng ký khóa học miễn phí còn chỗ, nhận và tự kiểm tra trạng thái chính xác trên Increment đã tích hợp.”

Sau khi test concurrency thất bại, Sprint Goal **không cần đổi chỉ vì có trở ngại** nếu nhóm vẫn có phương án đạt goal an toàn. Developers có thể **điều chỉnh Sprint Backlog**: tập trung sửa lỗi transaction, gỡ blocker môi trường, giảm scope tùy chọn theo trao đổi với PO và bảo đảm DoD.

Nếu mục tiêu đã trở nên **không thể đạt** vì bằng chứng/ràng buộc mới, phải **minh bạch**. Trong Scrum, chỉ **Product Owner có quyền hủy Sprint** nếu Sprint Goal trở nên lỗi thời; không nên dùng “hủy Sprint” như phản ứng mặc định cho một blocker có thể giải quyết.

### 15.3. Khi nào thương lượng phạm vi trong Sprint?

Ví dụ email được đề xuất giữa Sprint:

1. Xác định đó là **yêu cầu mới** hay điều kiện bắt buộc trước đây bị bỏ sót.
2. Đánh giá ảnh hưởng Sprint Goal và DoD.
3. **Developers và Product Owner phối hợp làm rõ/đàm phán phạm vi Sprint Backlog** khi học thêm.
4. Nếu email tùy chọn và khiến mục tiêu cốt lõi rủi ro, để ở Product Backlog, không tự lén thêm.
5. Nếu email bắt buộc vì quy định/contract, điều chỉnh kế hoạch và dự báo theo thẩm quyền; không hạ chuẩn.

Điều chỉnh Sprint Backlog **không có nghĩa đổi Sprint Goal mỗi ngày để hợp thức hóa mọi việc đã làm**. Sprint Goal là cam kết mục đích; cách đạt có thể thích ứng trong giới hạn chất lượng và ngữ cảnh.

### 15.4. Daily Scrum tập trung kiểm tra–thích ứng

Thay vì mỗi người báo “hôm qua tôi code bao nhiêu” cho cấp trên, Developers có thể hỏi:

- Mức tiến tới Sprint Goal còn thực tế không?
- PBI nào đang chờ kiểm chứng bắt buộc?
- Ai có thể hỗ trợ gỡ blocker DB/staging ngay?
- Có cần dừng kéo việc mới để cùng sửa lỗi dữ liệu?
- Có giả định nào thay đổi làm cách làm hiện tại không phù hợp?

Daily Scrum là sự kiện **15 phút của Developers** nhằm kiểm tra tiến độ hướng Sprint Goal và điều chỉnh Sprint Backlog; các trao đổi chi tiết liên nhóm có thể tiếp tục **sau** cuộc họp, không cần buộc mọi vendor vào Daily Scrum.

### 15.5. Sprint Review và Sprint Retrospective hỏi khác nhau

| Sự kiện | Bài học từ ca |
| --- | --- |
| **Sprint Review** | Có Increment nào đã tích hợp, dùng được, đạt DoD? Người học/stakeholder phản hồi gì? Product Backlog cần điều chỉnh ra sao? |
| **Sprint Retrospective** | Tại sao tích hợp muộn? Có WIP/handoff/CI/flaky test tạo chờ? Thử cải tiến nhỏ nào có owner và số đo? |

Review không phải chỉ là buổi báo cáo task, Retro không phải nơi đổ lỗi cho “QA chậm”. Cả hai cần bám **bằng chứng** và hướng tới khả năng tạo giá trị tốt hơn.

## 16. Nếu dùng Kanban: quản lý việc đang dở và các điểm nghẽn

### 16.1. Minh bạch Definition of Workflow

Để biết phải điều chỉnh gì, nhóm có thể định nghĩa:

- **Loại item:** PBI phát triển, defect, yêu cầu vận hành hay incident.
- **Started:** khi công việc thực sự được kéo vào vùng xử lý.
- **Finished:** khi đạt điều kiện Finished/Done đã công bố.
- **Các trạng thái:** Ready, Developing, Review, Integrated Verify, Done.
- **Chính sách blocked:** khi nào đánh dấu, ai cập nhật, cách gỡ, khi nào escalation.
- **WIP limits:** giới hạn thích hợp cho từng vùng, có quy tắc ngoại lệ.
- **Service Level Expectation (SLE):** kỳ vọng thời gian hoàn tất có tính xác suất dựa trên dữ liệu phù hợp.

Không nên dùng “Done = đã viết code” khi mục tiêu là **Increment có thể dùng**. Nếu cần theo dõi coding riêng, hãy đặt trạng thái phụ **Code Complete**, vẫn để item chính ở vùng đang dở cho tới khi đủ điều kiện.

### 16.2. Ví dụ bảng luồng

~~~mermaid
flowchart LR
    A["Ready"] --> B["Developing"]
    B --> C["Review / CI"]
    C --> D["Integrated Verify"]
    D --> E["Done / usable"]
    D -. "Rework" .-> B
    C -. "Contract mismatch" .-> B
    D -. "Blocked: staging / IdP" .-> D
~~~

Một item đang **chờ staging** vẫn là WIP theo workflow nếu đã Started nhưng chưa Finished. Không chuyển nó sang bảng “bên ngoài” để che thời gian chờ hoặc làm median cycle time đẹp giả.

### 16.3. Giới hạn WIP để ưu tiên hoàn tất

Giả sử nhóm thử chính sách **WIP toàn vùng Development + Verify không quá 4 PBI thường**. Đây là **con số thử nghiệm**, không phải giới hạn Kanban chuẩn.

Khi vùng đã đầy:

1. Xem các item lâu chưa Done, nhất là item có rủi ro Sprint Goal.
2. Giúp review, test, pairing, sửa lỗi tích hợp hoặc gỡ blocker.
3. Tránh mở thêm PBI chỉ để mọi người “bận”.
4. Có quy tắc công việc khẩn/incident rõ và không để WIP limit ngăn ứng cứu an toàn.
5. Xem liệu điểm nghẽn có chuyển từ Verify sang API/Platform không.
6. Đánh giá hiệu quả bằng cycle time, work item age, throughput và chất lượng.

WIP limit được dùng để **thay đổi cách hợp tác và nhìn rõ bottleneck**, không làm KPI kỷ luật cá nhân.

### 16.4. Đọc công việc đang dở, không chỉ công việc đã xong

Từ dữ liệu ca:

- 9 PBI đã Finished có median cycle time 9 ngày.
- 5 PBI vẫn dở có tuổi 3, 7, 10, 11 và 15 ngày.

**Nhận định an toàn:** ít nhất một item đang rất già so với các item Finished gần đây, cần hỏi nguyên nhân, tác động và khả năng gỡ. Không thể kết luận ngay **mọi PBI sẽ trễ 15 ngày** hay WIP quá cao nếu chưa biết phân bố lịch sử, loại item và chính sách Started/Finished.

### 16.5. Một cuộc flow review có thể hỏi gì?

| Câu hỏi | Bằng chứng cần |
| --- | --- |
| Item 15 ngày dở vì điều kiện nào? | Lịch sử trạng thái, blocker owner, version và mốc cần. |
| Bước nào tích tụ nhiều item? | WIP/cumulative flow, queue time theo bước. |
| Có phải team đang đẩy thêm việc vào chỗ đã nghẽn? | Policy pull, số item vào/ra, thời gian đợi. |
| Giới hạn WIP có giúp hoàn tất nhanh hơn không? | Cycle time và work item age nhiều kỳ cùng định nghĩa. |
| Chất lượng có bị đẩy xuống support không? | Defect sau release, incident, rework, outcome. |

SLE hỗ trợ xem rủi ro item vượt kỳ vọng, **không phải SLA cứng** và không cho phép bỏ test khi item gần quá tuổi.

## 17. Áp dụng XP/CI để biến rủi ro kỹ thuật thành phản hồi sớm

### 17.1. Chọn test dựa trên cơ chế sai, không chỉ tăng số test

Trong ca, các kỹ thuật có thể gồm:

| Rủi ro | Kiểm chứng phù hợp | Giới hạn của test |
| --- | --- | --- |
| Quy tắc không đăng ký trùng | Unit/service test + ràng buộc dữ liệu + integration test. | Unit test không đảm bảo tranh chỗ đồng thời. |
| Hai học viên tranh chỗ cuối | Concurrency/integration tests trên DB phù hợp. | Một lần test xanh không chứng minh mọi lịch thực thi đều an toàn. |
| Token hoặc claim không đúng | Authn/authz tests + contract tests với IdP. | Mock có thể khác provider thật. |
| Timeout sau commit | Test failure mode, idempotency và tra trạng thái thật. | Không tự giả định client nhận được phản hồi. |
| API thay đổi field/mã lỗi | Consumer/provider contract tests. | Contract đúng vẫn có thể sai nghiệp vụ. |
| Triển khai version mới | Smoke/integration tests, logs/metrics và rollback plan. | Rollback code không tự hoàn tác dữ liệu đã ghi. |

**Test strategy** phải phục vụ chất lượng của hành vi cần giao, không phải một cuộc đua số lượng test case.

### 17.2. TDD và refactoring theo hành vi nhỏ

Một chu trình TDD tham khảo:

1. **Red:** viết test cho trường hợp một học viên gửi lại đăng ký khi đã có bản ghi hiệu lực.
2. **Green:** triển khai đủ logic nghiệp vụ để test đạt.
3. **Refactor:** làm rõ code/khả năng kiểm soát idempotency, giữ test xanh.
4. **Integrate:** chạy với DB và các điều kiện cần thiết thực; thêm test cạnh tranh.

Không được suy rằng **chỉ cần TDD là concurrency tự an toàn**. Lỗi đồng thời có thể cần database constraints, transaction isolation, locking, conditional updates hoặc thiết kế khác tùy hệ thống.

### 17.3. Tích hợp thường xuyên, thay đổi nhỏ

Nhóm có thể:

- Merge những thay đổi nhỏ tương thích và an toàn.
- Viết contract tests trước khi UI và API tách xa nhau.
- Tạo dữ liệu thử được phép và môi trường tái lập.
- Chạy unit, static analysis, contract và integration checks với nhịp phù hợp.
- Theo dõi tình trạng pipeline, không để nhánh chính đỏ kéo dài.
- Đánh dấu rõ test chưa chạy vì thiếu provider/staging, không gọi là PASS.

**Một pipeline xanh** chỉ xác nhận những gì nó **thực sự chạy và kiểm chứng**. Nếu test concurrency trên DB thật bị skip, nó không có bằng chứng cho rủi ro ấy.

### 17.4. Feature flags và tích hợp trước khi mở cho người dùng

Có thể cần merge code mới mà chưa mở giao diện. Feature flag giúp tách **deploy** khỏi **release**, nhưng cần:

- Flag owner, phạm vi và kế hoạch gỡ.
- Authn/authz độc lập với flag.
- Test cho trạng thái bật/tắt quan trọng.
- Xử lý thay đổi schema và dữ liệu tương thích.
- Phương án khôi phục khi side effects đã xảy ra.

Không cho rằng “flag đang tắt” đồng nghĩa toàn tính năng **đã là Increment Done** nếu chưa đạt tiêu chuẩn chất lượng/khả năng sử dụng theo phạm vi.

### 17.5. Quan sát hệ thống sau release không thay pre-release quality

Metrics sau release có thể gồm:

- Tỷ lệ request thất bại theo mã nguyên nhân đã phân loại.
- Số request không rõ trạng thái sau timeout.
- Bất nhất sức chứa hoặc bản ghi trùng đã xác minh.
- Lỗi token và từ chối quyền bất thường.
- Độ trễ API ảnh hưởng người học.
- Tỷ lệ hành trình tự hoàn tất và ticket support.

Observability giúp thấy vấn đề không lộ trong test, nhưng **không hợp thức hóa việc đưa lỗi dữ liệu nghiêm trọng ra người dùng để “thu feedback”**.

## 18. Phân tích phụ thuộc và phối hợp nhiều nhóm hoặc nhà cung cấp

### 18.1. Bản đồ phụ thuộc cho lát cắt hiện tại

~~~mermaid
flowchart TD
    Goal["Tự đăng ký khóa miễn phí chính xác"] --> Web["Web + hành trình"]
    Goal --> Enroll["Enrollment API / DB"]
    Goal --> Verify["Kiểm chứng liên thành phần"]
    Web -. "Contract response / lỗi" .-> Enroll
    Enroll -. "Xác thực và claims" .-> IdP["Nhà cung cấp định danh"]
    Verify -. "Test DB / môi trường" .-> Platform["Platform"]
    Verify -. "Bản contract hợp lệ" .-> IdP
~~~

Các cạnh thể hiện **điều kiện cần hoặc điểm giao tiếp**, chưa đủ kết luận tất cả đang là blocker. Cần hỏi rõ **ai cần gì, ai có thể cung cấp, khi nào cần biết, điều kiện kiểm chứng và phương án giảm chờ**.

### 18.2. Dependency register ngắn

| ID | Phụ thuộc | Trạng thái/bằng chứng hiện tại | Hành động thích ứng |
| --- | --- | --- | --- |
| **D-01** | Web cần trạng thái và lỗi từ Enrollment. | Có mismatch trong kiểm thử. | Hai bên chốt ví dụ, contract tests và owner thay đổi. |
| **D-02** | Enrollment cần claims/quyền từ IdP. | Contract hiện tại đang dùng; vendor thông báo thay đổi dự kiến. | Kiểm tra version được hỗ trợ, inventory consumer và compatibility/security tests. |
| **D-03** | Verify cần môi trường DB/staging dùng được. | Ba item có ghi blocker; nguyên nhân chưa xác minh. | Platform/Developers cùng điều tra, template tự phục vụ hoặc lịch cấp hợp lệ. |
| **D-04** | Release cần chứng cứ DoD và runbook phù hợp. | Chưa có bằng chứng concurrency pass. | Không mở rộng hành vi ghi trước khi đạt chuẩn. |

Mỗi bản ghi nên có **owner theo dõi, mốc cần biết và điều kiện kết thúc**, không chỉ tên một team để đổ trách nhiệm.

### 18.3. Nhịp nhà cung cấp khác nhịp Scrum Team

IdP thay claims theo lịch riêng. Nhóm không cần ép IdP vào Sprint hai tuần. Thay vào đó:

- Xác minh **API/claims đang được hỗ trợ** và ngày hết hỗ trợ thực nếu có.
- Cùng chốt ví dụ hợp đồng/tình huống permission.
- Làm **contract tests** và test tích hợp ở phiên bản provider thật.
- Dùng adapter/compatibility khi có lý do kỹ thuật.
- Thông báo sớm thay đổi có thể phá consumer.
- Chuẩn bị rollback/forward fix và support theo hợp đồng.
- Nếu phiên bản mới chưa cần cho goal hiện tại và version cũ còn an toàn, có thể tách việc nâng version thành hạng mục sau theo sự thật.

Không dùng một phiên bản không được hỗ trợ hoặc bỏ xác minh token chỉ vì nó giúp giảm blocked time.

### 18.4. Khi nhiều Scrum Team cùng một sản phẩm

Theo Scrum Guide 2020, nhiều Scrum Team cùng làm **một sản phẩm** cần cùng **một Product Goal, một Product Backlog, một Product Owner và một Definition of Done**. Điều này khác với việc IdP là một **sản phẩm SaaS độc lập** phục vụ nhiều khách hàng với backlog và mục tiêu riêng.

Nếu Web, Enrollment và một nhóm Platform cùng đóng góp một sản phẩm, không tự suy rằng mỗi nhóm có thể tuyên bố Done riêng rồi ghép các báo cáo. Cần tập trung **Increment tích hợp**, những tiêu chuẩn chung và trách nhiệm chuyên môn.

### 18.5. Nâng cấp trở ngại đúng người có quyền

Một thông điệp escalation có thể là:

> “Lát cắt tự đăng ký chưa thể đạt DoD vì kịch bản hai học viên tranh chỗ cuối chưa được kiểm chứng ổn định trên DB tích hợp. Test hiện có đã thất bại hai lần, root cause còn cần điều tra. Chúng tôi cần môi trường test cách ly và đầu mối hỗ trợ có quyền cấu hình trước lần kiểm chứng tiếp theo. Phương án là dùng template staging đã được phê duyệt và dữ liệu giả, không mở chức năng cho người dùng khi chưa đạt kiểm thử bắt buộc.”

Thông điệp này rõ **bằng chứng, điều kiện, tác động, lựa chọn và quyền** hơn câu “team Platform làm chúng tôi trễ”.

## 19. Quyết định phát hành: thích ứng không đồng nghĩa hạ tiêu chuẩn

### 19.1. Ba khả năng cần phân biệt

| Trạng thái | Có thể làm gì? | Không được tự tuyên bố |
| --- | --- | --- |
| **Code cục bộ đã viết** | Review, refactor, test, merge an toàn trong phạm vi phù hợp. | “Người dùng đã có giá trị” khi chưa tích hợp. |
| **Increment đạt Definition of Done** | Sẵn sàng theo nghĩa chất lượng sản phẩm đã định, có thể xem tại Sprint Review. | “Đã phát hành cho mọi người” nếu chưa release. |
| **Released/đã mở sử dụng** | Người dùng thực hiện được hành vi, cần quan sát và hỗ trợ. | “Outcome đã cải thiện” khi chưa có dữ liệu thực. |

Trong Scrum, Increment được tạo ra khi một Product Backlog Item đáp ứng DoD; **Increment có thể được giao cho stakeholders trước khi kết thúc Sprint**, Sprint Review không phải cổng release bắt buộc. Tuy nhiên, việc phát hành thực vẫn phải tuân thủ các điều kiện vận hành, quyền và an toàn áp dụng.

### 19.2. Ví dụ câu hỏi Go/No-go

Trước khi mở rộng cho mọi học viên, người có quyền cần biết:

1. Có tình huống sai sức chứa hoặc trùng dữ liệu chưa xử lý không?
2. Test concurrency, idempotency, phân quyền và end-to-end đạt chưa?
3. Cấu hình IdP/claims được xác minh trên phiên bản mục tiêu chưa?
4. Staging và production có khác biệt nào ảnh hưởng kiểm chứng?
5. Có giám sát, cảnh báo, runbook và đường ứng cứu?
6. Nếu rollout sai, có cách dừng/khôi phục mà không phá dữ liệu không?
7. Scope nào thực sự được mở, giới hạn nào được nói rõ cho người dùng/support?
8. Ai có thẩm quyền release và chấp nhận rủi ro còn lại theo policy?

Một cuộc họp “go/no-go” không tự thay **bằng chứng test**. Người có quyền quyết trên bằng chứng; không tuyên bố thành công vì các team đã ký vào một slide.

### 19.3. Không nhầm rollback code với sửa dữ liệu

Nếu đăng ký sai đã ghi:

- Quay code về version cũ không tự xóa bản ghi sai.
- Email gửi ra không tự thu hồi.
- Khóa học đã đầy sai có thể gây ảnh hưởng cho học viên khác.
- Hành động sửa dữ liệu phải có **quyền, kiểm toán, đối soát và kế hoạch thông báo** tương xứng.

Kế hoạch release/khôi phục cần xét cả **dữ liệu và side effects**, không chỉ việc đổi nhãn image trong CI/CD.

### 19.4. Khi chưa đạt chuẩn, có thể làm gì tích cực?

Một quyết định **No-go** cho hành vi đăng ký chưa an toàn không đồng nghĩa nhóm ngừng làm việc:

- Hoàn tất điều tra và sửa lỗi.
- Tạo test hồi quy và môi trường kiểm chứng.
- Làm rõ Product Backlog và lát cắt tiếp.
- Cải thiện tài liệu hỗ trợ, giám sát và contract.
- Giao phần giá trị khác **thật sự độc lập và đáp ứng DoD**, nếu có.
- Cập nhật dự báo và điều kiện xem lại với stakeholders.

Không “lách” bằng cách mở tính năng ghi cho nhóm người dùng thử nếu kiểm soát bắt buộc vẫn chưa đạt; một nhóm nhỏ người dùng thật vẫn có thể chịu ảnh hưởng sai dữ liệu/riêng tư.

## 20. Chọn thước đo để biết thích ứng có hiệu quả hay không

### 20.1. Ba lớp câu hỏi

**Giá trị và outcome:**

- Người học có tự hoàn tất đăng ký và biết trạng thái đúng hơn không?
- Ticket hỗ trợ mơ hồ có giảm theo một mẫu số phù hợp không?
- Có tăng các sự cố dữ liệu hoặc quyền hay không?

**Flow và năng lực giao hàng:**

- PBI từ Started tới Done mất bao lâu?
- Item đang dở đã già tới mức nào?
- Hạng mục chờ staging/contract/review bao lâu?
- WIP và throughput có thay đổi bền vững không?

**Độ tin cậy và bảo vệ hệ thống:**

- Test quan trọng đã thực sự chạy trên hệ thống tích hợp chưa?
- Có rework vì lệch contract hay lỗi sau release không?
- CI/mainline và môi trường test có ổn định hơn không?
- Tải support/on-call hoặc giờ làm thêm có tăng không?

Nếu chỉ đo **tốc độ coding**, nhóm có thể giao nhanh các thay đổi còn sai dữ liệu. Nếu chỉ đo **outcome người dùng**, có thể bỏ qua quá tải Developers đang gây chi phí lâu dài. Cần đủ chỉ số để thấy **cả giá trị, flow và guardrails**.

### 20.2. Bộ đo lường gọn cho ca

| Metric | Định nghĩa minh họa | Vai trò |
| --- | --- | --- |
| **Tỷ lệ hoàn tất lượt đăng ký** | Lượt bắt đầu dẫn tới trạng thái cuối xác minh được / lượt bắt đầu hợp lệ theo event definition. | Outcome người dùng, cần tách đã xác nhận/hết chỗ. |
| **Ticket hỏi trạng thái** | Số ticket phân loại “không rõ đăng ký đã xong?” trên tập/chu kỳ được xác định. | Tín hiệu trải nghiệm và support, không tự là tỷ lệ người dùng bị lỗi. |
| **Data-integrity incidents** | Sự cố bản ghi trùng hiệu lực/vượt sức chứa đã xác minh theo severity. | **Guardrail nghiêm trọng**. |
| **Unauthorized access incidents** | Trường hợp truy cập trái quyền đã xác minh. | **Guardrail bảo mật**. |
| **Cycle time** | Thời gian Started → Finished của PBI đã Done theo cùng DoW. | Đo hoàn tất flow. |
| **Work item age** | Thời gian từ Started đến hiện tại của PBI chưa Finished. | Phát hiện item mắc kẹt. |
| **WIP** | Số PBI Started nhưng chưa Finished tại mốc đo. | Phản ánh lượng việc đang dở. |
| **Throughput** | Số PBI Finished mỗi khoảng thời gian theo loại việc. | Nhịp hoàn tất, không thay giá trị. |
| **Blocked time** | Khoảng không thể tiến triển theo quy tắc ghi blocker. | Tìm hàng đợi và phụ thuộc. |
| **Integration feedback time** | Thời gian từ thay đổi/merge tới kết quả kiểm chứng tích hợp cần thiết. | Xem phản hồi kỹ thuật đến sớm hơn không. |
| **Rework vì contract mismatch** | Những vòng sửa lại có nguyên nhân được xác minh do hợp đồng lệch. | Đánh giá hiệu quả contract-first. |
| **Team sustainability** | Dấu hiệu quá tải, giờ trực, bối cảnh đổi ngữ cảnh và phản hồi người làm. | Không tối ưu tốc độ bằng chuyển chi phí sang con người. |

**Không dùng một metric làm KPI cá nhân.** Story points/velocity, nếu nhóm dùng, là công cụ lập kế hoạch mang ngữ cảnh riêng; không phải thước đo để xếp hạng Developers hay nhóm khác loại công việc.

### 20.3. Kết hợp cycle time và work item age

Một vấn đề thường gặp là chỉ xem **9 PBI Finished, median cycle time 9 ngày** rồi tuyên bố flow ổn định. Nhưng còn một item WIP **15 ngày** chưa Finished.

Phân tích có ích:

1. Item 15 ngày thuộc loại gì? Có lớn hơn những PBI Finished không?
2. Tại sao nó chưa Done? Blocker, kỹ thuật, thay đổi yêu cầu hay bị bỏ quên?
3. Nó có ảnh hưởng Product Goal/Sprint Goal hoặc nghĩa vụ hiện tại không?
4. Có thể giúp hoàn tất với WIP hiện có thay vì mở item mới không?
5. Nếu DoW/DoD thay đổi, dữ liệu lịch sử còn so được không?

Thông thường cần **phân bố cycle time**, không chỉ trung vị, và xem trạng thái/tuổi item dở để tránh thiên lệch “chỉ những gì đã hoàn tất”.

### 20.4. Một mẫu tính flow và điều kiện Little's Law

Nếu workflow tương đối ổn định có:

- WIP trung bình: **6 PBI**.
- Throughput trung bình: **3 PBI/tuần**.
- Mốc Started/Finished và loại item nhất quán.

Theo quan hệ của Little's Law trong điều kiện thích hợp:

\[
\overline{\text{WIP}}\approx
\text{Throughput rate}\times\overline{\text{Cycle time}}.
\]

Thời gian trung bình trong hệ thống có thể xấp xỉ:

\[
\overline{\text{Cycle time}}\approx
\frac{6\text{ PBI}}{3\text{ PBI/tuần}}=2\text{ tuần}.
\]

Đây **không phải cam kết** mọi PBI sẽ xong sau hai tuần và không nhất thiết áp được cho mẫu bốn tuần với nhiều blocker/incident. Cần điều kiện về ổn định, luồng vào–ra, cùng phạm vi và dữ liệu phù hợp.

### 20.5. Không nhầm chỉ báo lỗi thấp với chứng minh an toàn

Nếu một kỳ quan sát không ghi nhận lỗi trái quyền, có ít nhất ba khả năng:

- Hệ thống thực sự đang bảo vệ quyền tốt.
- Test/monitoring còn thiếu, lỗi chưa được phát hiện.
- Số lượt sử dụng/mẫu quan sát chưa đủ để phát hiện.

Vì thế **guardrail không chỉ là số incident thấp**, mà còn là **bằng chứng kiểm thử và kiểm soát bắt buộc**. Không cho phép thử tính năng chưa an toàn chỉ để có dữ liệu production nhiều hơn.

## 21. Kế hoạch thích ứng theo PDCA/PDSA

### 21.1. Quan sát vấn đề → giả thuyết → thử → học

~~~mermaid
flowchart LR
    A["Quan sát / bằng chứng"] --> B["Định nghĩa vấn đề"]
    B --> C["Giả thuyết cơ chế"]
    C --> D["Thử cải tiến nhỏ, có guardrails"]
    D --> E["Đo outcome + flow + quality"]
    E --> F{"Kết quả ủng hộ?"}
    F -- "Có, đủ bằng chứng" --> G["Chuẩn hóa và tiếp tục theo dõi"]
    F -- "Chưa rõ / không" --> H["Điều chỉnh hoặc bác giả thuyết"]
    H --> B
    G --> A
~~~

**PDCA** là Plan–Do–Check–Act; **PDSA** là Plan–Do–Study–Act. Cả hai nhấn mạnh cải tiến dựa trên việc **quan sát thực tế và điều chỉnh**, không yêu cầu mọi thử nghiệm phải thành công.

### 21.2. Thử nghiệm thứ nhất: giảm sai lệch hợp đồng UI–API

**Problem statement minh họa:**

> Trong một số PBI đăng ký, trạng thái lỗi/hết chỗ được thống nhất sau khi hai bên đã code, tạo vòng làm lại và kéo thời gian Verify. Chưa biết tỷ lệ thực trên toàn nhóm vì chưa đo đầy đủ.

**Giả thuyết:**

> Nếu PO, Developers và người kiểm thử cùng thống nhất ví dụ acceptance/contract trước khi bắt đầu một số PBI đăng ký, rồi chạy contract tests từ sớm, thì số vòng rework vì mismatch sẽ giảm, vì hai bên phát hiện kỳ vọng khác nhau trước khi code hoàn chỉnh.

**Phạm vi thử:** hai đến bốn PBI cùng loại khi có đủ điều kiện, không tùy tiện áp vào mọi hạng mục.

**Metric chính:** số vòng rework do contract mismatch trên mỗi PBI cùng loại, hoặc thời gian blocked của bước Verify do lỗi hợp đồng.

**Guardrails:** DoD không đổi; không tăng lỗi sau tích hợp; không tạo một cuộc họp kéo dài làm quá tải người tham gia.

**Yếu tố gây nhiễu:** khác độ phức tạp, người làm, môi trường, vendor version và mức sẵn của dữ liệu test.

### 21.3. Thử nghiệm thứ hai: giảm WIP để ưu tiên hoàn tất

**Vấn đề:** có năm PBI đang dở và một item 15 ngày, nhóm thường mở thêm việc khi Verify bị chặn.

**Giả thuyết:**

> Nếu nhóm dùng WIP limit phù hợp và dành năng lực giúp item ở Verify, thì work item age của những item cũ và thời gian chờ review/integration sẽ giảm vì bớt việc mở đồng thời và tăng hỗ trợ tại điểm nghẽn.

**Phạm vi thử:** một chu kỳ quan sát đủ để có dữ liệu, có policy ngoại lệ cho incident.

**Metric:** work item age theo thời gian, WIP và cycle time phân bố cho PBI tương đồng.

**Guardrails:** chất lượng không giảm, Developers không tăng giờ làm thêm, số incident không tăng, không xóa item blocked khỏi bảng.

**Không bảo đảm:** WIP limit **không tự tạo môi trường staging**. Nếu bottleneck là quyền và công suất hạ tầng, phải xử lý nguyên nhân ấy song song.

### 21.4. Thử nghiệm thứ ba: kiểm chứng cải tiến trạng thái sau timeout

**Giả thuyết sản phẩm:**

> Nếu học viên có một đường tra lại trạng thái đăng ký thật và thông báo phân biệt “chưa xác định kết quả” với “đã thất bại”, thì số lượt phải hỏi support về kết quả mơ hồ sẽ giảm, vì người dùng có cách xác minh không cần nhân viên.

**Điều kiện bắt buộc:** server phải xử lý idempotency, bảo vệ quyền và giữ dữ liệu chính xác; không chỉ thay câu chữ khi backend vẫn trả kết quả sai.

**Outcome:** tỷ lệ lượt đăng ký có trạng thái cuối được xác minh, ticket theo cùng mẫu số/định nghĩa, phản hồi người dùng.

**Guardrails:** không tăng đăng ký trùng/vượt chỗ, không lộ thông tin, không thông báo thành công giả.

**Cách thử:** kiểm chứng kỹ thuật trên bản tích hợp trước; nếu đạt, thử trong phạm vi sử dụng được phép và quan sát tương xứng. Không dùng người dùng thật để thử một đường ghi chưa an toàn.

### 21.5. Quyết định sau thử

| Quan sát | Hành động phù hợp |
| --- | --- |
| Metric chính cải thiện, guardrails đạt, dữ liệu đủ tin | Chuẩn hóa thay đổi phù hợp và tiếp tục theo dõi. |
| Metric cải thiện nhưng lỗi dữ liệu/riêng tư tăng | Ưu tiên xử lý rủi ro, dừng hoặc điều chỉnh thử nghiệm theo quyền. |
| Không cải thiện, dữ liệu chỉ ra bottleneck khác | Sửa giả thuyết; ví dụ từ review sang staging capacity. |
| Dữ liệu quá ít hoặc mốc đo thay đổi | Không khẳng định thành công; kéo dài/điều chỉnh cách quan sát. |
| Kết quả tốt cục bộ nhưng support quá tải | Xem lại whole-system impact, không tối ưu một bước. |

Tư duy cải tiến là **liên tục học**, không phải đảm bảo mọi thử nghiệm đều giảm đúng một tỷ lệ đã được chọn trước.

## 22. Sáu diễn biến mới: luyện khả năng thích ứng trong khi đang làm

### 22.1. Diễn biến A — Một stakeholder đề nghị bật tính năng ngay ngày mai

**Thông tin mới:** phòng kinh doanh muốn mở đăng ký cho toàn bộ học viên để phục vụ chiến dịch. Nhưng test tranh chỗ cuối vẫn chưa đạt ổn định.

**Câu hỏi ra quyết định:**

1. Có bằng chứng DoD và dữ liệu an toàn chưa?
2. Người có quyền phát hành/rủi ro đã được cung cấp tình trạng thật chưa?
3. Có phần giá trị khác đã Done có thể giao độc lập không?
4. Cần giữ/đổi mốc, phạm vi hoặc cách truyền thông thế nào?

**Hướng xử lý gợi ý:** không mở tính năng ghi chưa đạt điều kiện bắt buộc. Triage lỗi, xác minh khả năng khôi phục dữ liệu, làm rõ dự báo và nêu phương án: phát hành phần độc lập đã Done nếu có; giữ mốc cho hoạt động không có rủi ro; hoặc điều chỉnh kế hoạch chiến dịch.

**Không hợp lệ:** đổi trạng thái test fail thành “known issue” rồi báo Increment Done chỉ để giữ ngày.

### 22.2. Diễn biến B — Vendor IdP thông báo breaking change trong vòng hai tuần

**Thông tin mới:** claim học viên mà API đang dùng sẽ đổi tên ở version mới. Không rõ version cũ còn hỗ trợ trong bao lâu.

**Câu hỏi:**

1. Có contract/notice chính thức và thời điểm hiệu lực không?
2. Những consumer/version nào bị ảnh hưởng?
3. Có thể hỗ trợ hai hợp đồng tạm thời một cách an toàn không?
4. Có rủi ro bảo mật bắt buộc cần đổi khẩn không?
5. Lát cắt hiện tại có thật sự phụ thuộc khả năng mới không?

**Hướng xử lý gợi ý:** phân tích hợp đồng, lập compatibility/security tests, làm việc với vendor và người có quyền; không tự động hoãn mọi PBI nếu version hiện hành vẫn đủ an toàn. Ngược lại, nếu version cũ hết hỗ trợ hoặc có lỗ hổng nghiêm trọng, không giữ lại chỉ để đạt Sprint Goal.

### 22.3. Diễn biến C — Bộ phận hỗ trợ cho biết ticket giảm nhưng người dùng bỏ cuộc tăng

**Thông tin mới:** sau thay đổi UI, ticket hỏi trạng thái giảm, nhưng dữ liệu phân tích cho thấy số lượt bỏ giữa chừng tăng. Không rõ nguyên nhân.

**Câu hỏi:**

- Ticket ít hơn có phải vì vấn đề được giải quyết hay vì người dùng **không thấy cách liên hệ**?
- Lượt bỏ có được đo với cùng ranh giới và nhóm người dùng?
- Có thay đổi mùa vụ, tốc độ mạng, chính sách khóa học hoặc tính năng khác?
- Có thể quan sát một phiên người dùng với sự đồng ý không?

**Hướng xử lý gợi ý:** không tuyên bố thành công chỉ vì ticket giảm. Xem funnel, completion/verified status, lỗi nghiệp vụ và phản hồi; thử cải thiện có giả thuyết, bảo vệ quyền và riêng tư.

### 22.4. Diễn biến D — Staging ổn định lại nhưng PR vẫn dồn cuối Sprint

**Thông tin mới:** môi trường test không còn lỗi, nhưng PBI vẫn chờ nhiều ngày vì mọi nhóm gửi code vào ngày cuối.

**Câu hỏi:**

1. Giả thuyết “staging là nguyên nhân chính duy nhất” còn đúng không?
2. Batch size, WIP và cách chia ticket có gây tích lũy?
3. Contract/CI có thể chạy sớm hơn không?
4. Có cần đổi ranh giới quyền sở hữu hoặc working agreement?

**Hướng xử lý gợi ý:** xem VSM mới, thử vertical slicing, PR nhỏ, pull policies, swarming cho item dở, không mua thêm staging theo phản xạ khi nút thắt đã chuyển nơi khác.

### 22.5. Diễn biến E — PO phát hiện email xác nhận là nghĩa vụ bắt buộc

**Thông tin mới:** một điều khoản đã được xác nhận yêu cầu học viên phải nhận thông báo qua kênh cụ thể khi đăng ký được chấp nhận.

**Hệ quả:** giả định “email là tùy chọn và có thể để sau” **không còn đúng**. Nhóm cần:

- Xác minh phạm vi điều khoản, loại thông báo, thời điểm, bằng chứng và quyền.
- Làm rõ hành vi lỗi của nhà cung cấp email và trường hợp retry.
- Điều chỉnh acceptance criteria, kế hoạch và điều kiện release/DoD tương ứng.
- Đánh giá contract, riêng tư, idempotent delivery và support.
- Thông tin minh bạch về thay đổi phạm vi/rủi ro thay vì giấu phát hiện.

**Bài học:** thích ứng không phải luôn giảm scope; đôi khi phát hiện mới buộc nhóm **bổ sung một điều kiện bắt buộc** trước khi gọi hành vi Done.

### 22.6. Diễn biến F — Lỗi dữ liệu được xác nhận đang ảnh hưởng production

**Thông tin mới:** điều tra chứng minh có đăng ký vượt sức chứa đang có hiệu lực, khiến một số học viên nhận xác nhận sai.

**Hướng hành động:** kích hoạt ứng cứu theo severity; ngăn tăng ảnh hưởng theo quyền; xác định phạm vi, bảo toàn bằng chứng, đối soát/khôi phục dữ liệu theo phê duyệt, thông báo người liên quan theo nghĩa vụ, sửa và kiểm thử hồi quy trước khi mở lại. Product Backlog/roadmap cần cập nhật, nhưng **không thay thế incident response bằng một PBI bình thường**.

**Bài học:** mô hình Agile hỗ trợ học và thích ứng, nhưng không làm mất trách nhiệm **bảo vệ người dùng và sửa tác động thực**.

## 23. Phiếu phân tích tình huống và nhật ký quyết định

### 23.1. Mẫu phiếu phân tích có thể tái sử dụng

~~~text
CASE ID:
Sản phẩm / lát cắt giá trị:
Người nhận giá trị:
Product Goal hoặc mục tiêu liên quan:
Ranh giới tình huống:

1. QUAN SÁT / BẰNG CHỨNG
   - Sự kiện:
   - Nguồn, thời gian, phiên bản:
   - Những điều chưa được xác minh:

2. VẤN ĐỀ VÀ ẢNH HƯỞNG
   - Hành vi người dùng không đạt:
   - Dữ liệu / quyền / vận hành bị tác động:
   - Công việc đang chờ, chờ ở đâu:

3. GIẢ THUYẾT NGUYÊN NHÂN
   - Giả thuyết ưu tiên:
   - Bằng chứng phản bác sẽ là gì?
   - Cách kiểm tra an toàn:

4. NHU CẦU THÍCH ỨNG
   - Giá trị/nhu cầu:
   - Yêu cầu/phạm vi:
   - Kỹ thuật/chất lượng:
   - Flow/phụ thuộc:
   - Release/vận hành:

5. LỰA CHỌN VÀ QUYỀN
   - Phương án A/B/C:
   - Giá trị, chi phí và rủi ro:
   - Điều bắt buộc phải giữ:
   - Người có quyền quyết:

6. KẾ HOẠCH NGẮN HẠN
   - Lát cắt / PBI:
   - Điều kiện Done và bằng chứng:
   - Mốc cần biết/điểm xem lại:
   - Owner và dependency:

7. ĐO LƯỜNG VÀ HỌC
   - Baseline, định nghĩa mẫu số:
   - Metric chính:
   - Guardrails:
   - Confounders / giới hạn dữ liệu:
   - Kết quả, quyết định giữ/điều chỉnh/hoàn tác:
~~~

Mẫu này **không bắt buộc thành một biểu mẫu mới**. Nhóm có thể ghi trong ticket, wiki hoặc một trang thảo luận hiện có. Mục tiêu là giữ **ngữ cảnh ra quyết định có thể truy vết**, không tạo thêm bước bàn giao không cần thiết.

### 23.2. RACI/decision rights chỉ nên dùng khi cần

| Loại quyết định | Người/bên nên tham gia | Điều cần giữ |
| --- | --- | --- |
| Thứ tự Product Backlog | Product Owner và các bên cung cấp thông tin | Giá trị, rủi ro và Product Goal. |
| Cách làm, kiểm chứng trong Sprint | Developers và chuyên môn phù hợp | Sprint Goal, DoD, chất lượng chuyên môn. |
| Thay đổi hợp đồng bên ngoài | Người có thẩm quyền thương mại/pháp lý | Điều khoản, chi phí và quyền ký. |
| Release/triển khai production | Bên có quyền theo policy | Dữ liệu, bảo mật, monitoring, khả năng khôi phục. |
| Ứng cứu sự cố nghiêm trọng | Incident/security/service owners có thẩm quyền | Bảo vệ người dùng, bằng chứng, nghĩa vụ thông báo. |
| Cải tiến quy trình hằng ngày | Nhóm và người bị ảnh hưởng | Khả năng thử nhỏ, hiệu quả và tải bền vững. |

**RACI hoặc DACI** có thể giúp làm rõ người quyết khi có nhiều nhóm, nhưng không thay ba accountabilities chính thức của Scrum và không nên trở thành “hội đồng duyệt mọi PR”.

### 23.3. Ví dụ Decision Record

~~~text
DECISION: CAPSTONE-ENROLL-01
Vấn đề: Đăng ký miễn phí chưa chứng minh bảo vệ tranh chỗ cuối
Thông tin đã có: test tích hợp thất bại 2 lần; đang điều tra DB transaction
Chưa rõ: root cause và ảnh hưởng production
Hệ quả: hành vi ghi mới chưa thể được coi Done/ready
Lựa chọn:
  A. Mở toàn bộ ngay và sửa sau -> loại vì rủi ro dữ liệu
  B. Điều tra, sửa, test trước khi mở -> được chọn
  C. Giao riêng lát cắt đọc thông tin đã Done -> xem nếu có giá trị độc lập
Quyền:
  - Developers quyết giải pháp/test kỹ thuật trong policy
  - Product Owner điều chỉnh thứ tự Product Backlog
  - Release/incident owner quyết theo quyền ứng cứu và vận hành
Kế tiếp: tái hiện lỗi với DB phù hợp; làm rõ điều kiện sức chứa
Điều kiện xem lại: test concurrency/idempotency/auth đạt và DoD đầy đủ
Guardrails: dữ liệu, quyền, monitoring, không báo thành công giả
~~~

**Đây là một bản ghi giả định về hướng xử lý**, không phải tuyên bố rằng một giải pháp kỹ thuật cụ thể đã được kiểm chứng.

### 23.4. Truy xuất từ tín hiệu tới quyết định

Một quyết định thích ứng nên có đường kiểm tra:

~~~mermaid
flowchart LR
    A["Evidence / tín hiệu"] --> B["Vấn đề và hậu quả"]
    B --> C["Giả thuyết cần kiểm chứng"]
    C --> D["Các lựa chọn và guardrails"]
    D --> E["Quyết định theo quyền"]
    E --> F["Hành động nhỏ + test"]
    F --> G["Metric / feedback"]
    G -. "Học lại nếu sai" .-> C
~~~

Nếu nhóm chỉ có bước **“quản lý bảo làm” → “task được giao”**, người học khó hiểu vì sao kế hoạch đổi và không có cách biết biện pháp có giải quyết vấn đề không.

## 24. Bài giải mẫu: một kế hoạch thích ứng có thể thực hiện

### 24.1. Bước 1 — Xác định vấn đề ưu tiên

**Vấn đề cấp thiết:** hành vi ghi đăng ký chưa chứng minh tính đúng đắn khi yêu cầu đồng thời; có dấu hiệu dữ liệu trùng cần điều tra.

**Vấn đề giá trị:** người học không luôn biết trạng thái cuối sau lỗi mạng, nên vẫn cần hỗ trợ thủ công.

**Vấn đề flow:** nhiều PBI dở, tích hợp cuối Sprint, phụ thuộc staging chưa rõ owner.

**Bất định bên ngoài:** IdP có khả năng thay contract; chưa xác nhận mức ảnh hưởng, ngày và version.

**Yêu cầu phạm vi mới:** email và danh sách chờ; chưa mặc nhiên cần cho lát cắt hiện tại.

### 24.2. Bước 2 — Đặt thứ tự hành động theo mức rủi ro

Một trình tự minh họa:

1. Triage bất nhất dữ liệu/khả năng vượt sức chứa; bảo vệ người dùng nếu có tác động.
2. Làm rõ quy tắc nghiệp vụ và kịch bản Gherkin quan trọng.
3. Sửa và chứng minh transaction/idempotency/authn/authz trên bản tích hợp.
4. Gỡ blocker staging/contract để không chờ tới cuối Sprint.
5. Hoàn tất lát cắt tự đăng ký + xác minh trạng thái.
6. Xem lại Product Backlog với PO về email/danh sách chờ.
7. Theo dõi flow, chất lượng và outcome; quyết định cải tiến vòng tiếp.

Trình tự thực tế có thể có **các bước song song an toàn**. Không dùng nó như một waterfall thu nhỏ: làm rõ contract, chuẩn bị test và điều tra môi trường có thể diễn ra đồng thời khi đúng người có năng lực.

### 24.3. Bước 3 — Kế hoạch PBI và bằng chứng

| Hạng mục | Kết quả cụ thể | Bằng chứng bắt buộc/tùy rủi ro |
| --- | --- | --- |
| **PBI-1: Học viên xem được khóa còn chỗ** | Thông tin được hiển thị đúng theo quy tắc đã làm rõ. | Integration test dữ liệu đọc, quyền và tình huống cập nhật. |
| **PBI-2: Đăng ký miễn phí** | Lưu một đăng ký hợp lệ, không vượt chỗ. | DB transaction/concurrency/idempotency/security/E2E theo rủi ro và DoD. |
| **PBI-3: Tra trạng thái sau timeout** | Người học tự xác minh kết quả đã commit. | Test mất phản hồi, retry, quyền, trạng thái cuối và UI thông báo. |
| **ENABLER: test environment** | Môi trường DB tích hợp tái lập, quyền và test data an toàn. | Pipeline test thật và thông tin version; không thay DoD của PBI. |
| **DISCOVERY: nhu cầu email** | Xác nhận giá trị hoặc nghĩa vụ; phác họa contract nếu có. | Quyết định phạm vi, nguồn bằng chứng và backlog tiếp. |
| **RISK: IdP change** | Biết version nào được hỗ trợ và điều gì có thể phá consumer. | Contract/security tests, migration/compatibility plan. |

Một enabler hoặc hoạt động discovery **có giá trị kỹ thuật/học tập** nhưng không tự tương đương một Increment người dùng hoàn tất.

### 24.4. Bước 4 — Một Sprint Goal mẫu có điều kiện

> “Học viên đủ điều kiện có thể tự đăng ký khóa miễn phí còn chỗ và kiểm tra trạng thái cuối trên phần sản phẩm tích hợp đáp ứng DoD.”

**Cần làm rõ trước Sprint Planning** liệu khả năng test/điều kiện kỹ thuật đã đủ để mục tiêu này là một dự báo có trách nhiệm. Nếu còn bất định lớn không thể giải quyết trong Sprint, có thể chọn một **Sprint Goal khác có giá trị và khả thi hơn** mà vẫn hướng tới Product Goal, cùng một hoạt động khám phá rủi ro rõ ràng.

Không đặt Sprint Goal theo giả định vendor chắc chắn giao API hoặc staging chắc chắn hoạt động nếu chưa có bằng chứng.

### 24.5. Bước 5 — Phối hợp hằng ngày theo flow

Một cách làm:

- Giữ số PBI đang dở ở mức đội có thể kiểm soát.
- Khi test tích hợp thiếu môi trường, chỉ rõ dependency owner và mốc cần.
- Pair/swarms để gỡ lỗi cốt lõi thay vì mở thêm email/dashboard.
- Có hợp đồng UI–API và test chung từ refinement.
- Điều chỉnh Sprint Backlog dựa trên tiến độ hướng Sprint Goal.
- Thông báo sớm cho PO khi mục tiêu có nguy cơ không đạt.

### 24.6. Bước 6 — Điểm kiểm chứng cuối trước release

| Điều kiện | Trạng thái cần chứng minh |
| --- | --- |
| Không vượt sức chứa | Test tích hợp đồng thời trên DB phù hợp **đạt**. |
| Không đăng ký trùng | Quy tắc, constraint/idempotency và test **đạt**. |
| Đúng quyền | Authn/authz trên API **đạt**, không tiết lộ dữ liệu. |
| Sau timeout | Có đường xác minh trạng thái thật **được kiểm thử**. |
| Hợp đồng IdP | Version đang dùng được hỗ trợ và kiểm chứng phù hợp. |
| Hành trình UI–API–DB | End-to-end trên bản tích hợp **đạt** theo DoD. |
| Vận hành | Monitoring, runbook, rollback/forward fix và quyền release phù hợp. |
| Giá trị | Có cách đo hoàn tất/hỗ trợ và thu phản hồi được phép. |

Nếu bất kỳ **điều kiện bắt buộc** nào chưa đạt, không điền “PASS giả” chỉ vì ngày release cận kề. Có thể cần No-go cho phạm vi liên quan.

### 24.7. Bước 7 — Báo cáo stakeholder bằng bằng chứng

Một thông điệp mẫu:

> “Mục tiêu đang hướng tới là học viên tự đăng ký khóa miễn phí và xác minh trạng thái cuối. Trong đợt kiểm chứng, test cạnh tranh chỗ cuối chưa đạt; chúng tôi đang tái hiện nguyên nhân và chưa coi chức năng ghi đăng ký sẵn sàng mở rộng. Những phần có thể kiểm chứng độc lập vẫn tiếp tục. Yêu cầu email và danh sách chờ đã được ghi để PO làm rõ giá trị/nghĩa vụ. Điểm quyết định tiếp theo là khi test dữ liệu, quyền và tích hợp đạt DoD; khi đó nhóm sẽ cập nhật phương án release dựa trên bằng chứng thay vì một tỷ lệ task đã đóng.”

Thông điệp có **thực tế, giới hạn, bước kế tiếp và điều kiện quyết định**, không đổ lỗi hoặc hứa chắc một ngày khi còn phụ thuộc chưa được xác nhận.

### 24.8. Một vòng xem lại sau khi có kết quả

Nếu test dữ liệu đạt, staging ổn định và người học xác minh trạng thái dễ hơn:

- Kiểm tra **outcome**, không chỉ “số test pass”.
- Xem work item age và cycle time có cải thiện thực sự không.
- Theo dõi lỗi hậu phát hành và ticket đúng loại.
- Quyết định có nên chuẩn hóa contract-first/WIP policy.
- Tiếp tục discovery email/danh sách chờ theo giá trị mới được biết.

Nếu không có cải thiện, **bác bỏ hoặc sửa giả thuyết**. Một kế hoạch thích ứng tốt chấp nhận việc học được “nguyên nhân không phải như ta nghĩ”.

## 25. Bài tập tự phân tích và gợi ý lời giải

Các bài tập này có thể thực hiện cá nhân hoặc theo nhóm. Lời giải là **một hướng tham khảo dựa trên dữ liệu giả định**, không có nghĩa mọi tổ chức phải chọn đúng một kỹ thuật hoặc một lịch giống nhau.

### Bài tập 1 — Phân biệt sự kiện với suy đoán

Cho sáu phát biểu:

1. “Hai lần test tranh chỗ cuối không đạt.”
2. “DBA làm chậm cả Sprint.”
3. “Có 12 ticket hỏi trạng thái cuối.”
4. “Người học chắc chắn muốn nhận email.”
5. “Vendor đã thông báo thay cấu trúc claim ở bản tới.”
6. “Dùng Kanban sẽ sửa lỗi đăng ký trùng.”

**Yêu cầu:** phân loại phát biểu theo **sự kiện có thể xác minh** hoặc **diễn giải/giả thuyết/giải pháp chưa chứng minh**. Viết lại hai phát biểu thiếu bằng chứng thành câu phù hợp hơn.

**Gợi ý:** (1), (3) và (5) có thể là sự kiện **nếu có test/ticket/notice thực**; vẫn cần phiên bản, định nghĩa và nguồn. (2), (4), (6) là suy đoán. Ví dụ viết lại (2): “PBI đang chờ môi trường DB; chưa xác minh nguyên nhân và quyền cấp môi trường. Cần đối chiếu lịch yêu cầu và đầu mối Platform.”

### Bài tập 2 — Nhận diện nhu cầu thích ứng

Phân loại mỗi tình huống:

| Tình huống | Nhóm cần xét |
| --- | --- |
| Test quyền cho API tra đăng ký chưa có. | ? |
| Stakeholder muốn thêm danh sách chờ. | ? |
| CI bị flaky và kết quả tích hợp xuất hiện quá muộn. | ? |
| Người học sau timeout không biết server đã commit. | ? |
| Vendor IdP đổi schema claims. | ? |
| Nhóm có nhiều item WIP 15 ngày chưa Done. | ? |

**Gợi ý:** lần lượt là chất lượng/bảo mật; phạm vi/giá trị; kỹ thuật/flow; làm rõ yêu cầu, giá trị và dữ liệu; phụ thuộc/versioning; flow/WIP. Các nhóm có thể chồng lấn, nhưng mỗi vấn đề cần **một điều kiện kiểm chứng và owner**, không chỉ tên framework.

### Bài tập 3 — Tính toán đúng mẫu số

Dữ liệu minh họa: 200 lượt bắt đầu, 148 lượt có kết quả hoàn tất, 27 ticket hỗ trợ, trong đó 12 ticket hỏi trạng thái mơ hồ.

**Câu hỏi:**

1. Tỷ lệ lượt bắt đầu có trạng thái hoàn tất theo định nghĩa là bao nhiêu?
2. Có thể nói “13,5% học viên gặp lỗi” từ 27 ticket không?
3. Có thể cộng 27 và 12 thành 39 ticket không?
4. Cần bổ sung dữ liệu gì để biết người học thực sự gặp khó?

**Gợi ý:** \(148/200=74\%\). Không thể gọi 27/200 là tỷ lệ **người học lỗi**, vì 27 là ticket, 200 là lượt và có thể có người trùng. Không cộng 27+12 vì 12 thuộc 27. Cần mapping được phép giữa lượt–người–ticket, nguyên nhân không hoàn tất, lỗi nghiệp vụ, nguồn đo và độ trễ dữ liệu.

### Bài tập 4 — Có thể tuyên bố Done không?

Frontend, backend và database có unit tests xanh. Test tích hợp hai học viên tranh chỗ cuối thất bại, chưa xác định nguyên nhân. Một người nói **“chỉ còn QA, cứ đánh dấu Done để giữ tiến độ”**.

**Yêu cầu:** trả lời có/không và nêu lý do theo Increment/DoD. Đề xuất ba hành động tiếp.

**Gợi ý:** **Không** đối với hành vi đăng ký cần bảo vệ sức chứa; còn thiếu bằng chứng chất lượng bắt buộc. Hành động: tái hiện, điều tra DB/transaction/fixture; sửa và thêm test hồi quy; giải quyết môi trường và cập nhật dự báo. Nếu production đã bị ảnh hưởng, kích hoạt ứng cứu phù hợp.

### Bài tập 5 — Làm rõ hay mở rộng phạm vi?

Có các yêu cầu:

- A. Khi gửi trùng, không tạo thêm đăng ký hiệu lực.
- B. Khi hết chỗ, báo chính xác trạng thái.
- C. Gửi SMS mỗi khi học viên đăng ký.
- D. Xếp hàng chờ tự động cho khóa hết chỗ.
- E. Học viên tự tra trạng thái sau timeout.
- F. Cho phép thanh toán qua một nhà cung cấp mới.

**Yêu cầu:** phân biệt điều kiện có thể **bắt buộc để đáp ứng hành vi đã chọn**, điều kiện **cần làm rõ với PO**, và **capability mới**.

**Gợi ý:** A/B/E rất gần tính đúng đắn của tự đăng ký đáng tin, phải làm rõ acceptance criteria và DoD; C/D/F thường là capability mới với nghiệp vụ/phụ thuộc riêng. Tuy nhiên một kênh thông báo có thể là nghĩa vụ bắt buộc; phải xác minh thay vì suy từ tên chức năng.

### Bài tập 6 — Viết user story và Gherkin

**Yêu cầu:** từ mục tiêu “học viên không cần nhờ support để biết kết quả đăng ký”, viết:

1. Một user story.
2. Một kịch bản khi commit thành công nhưng client timeout.
3. Một kịch bản trái quyền.
4. Một điều kiện không được bỏ khi chia lát cắt.

**Gợi ý:** user story tương tự mục 10. Gherkin dùng **Given commit thành công và mất phản hồi → When tra/gửi lại hợp lệ → Then không có bản ghi trùng và xem trạng thái thật**. Trái quyền phải bị từ chối phía server. Không bỏ ràng buộc dữ liệu và authn/authz để báo Done.

### Bài tập 7 — Chọn thứ tự PBI

Có bốn ý tưởng:

1. Sửa rủi ro đăng ký vượt sức chứa.
2. Thêm thông báo email tùy chọn chưa được nghiên cứu.
3. Thêm khả năng tra trạng thái sau timeout.
4. Xây dashboard thống kê ít người dùng đã được quan sát.

**Yêu cầu:** đề xuất thứ tự theo **hậu quả, giá trị, bất định và điều kiện kỹ thuật**. Vì sao không nên dùng một điểm WSJF tùy ý để đẩy việc số 1 xuống cuối?

**Gợi ý:** (1) là nguy cơ tính đúng đắn bắt buộc, có thể cần ứng cứu ngay; (3) gần Product Goal và có bằng chứng trải nghiệm; (2) cần xác minh giá trị/nghĩa vụ; (4) có thể cần xem lại. Một phép tính điểm tùy ý không thay nghĩa vụ bảo vệ dữ liệu hoặc giải quyết incident.

### Bài tập 8 — Phân tích flow của item minh họa

Một PBI có active time **4,5 ngày** và waiting time **7 ngày**, các khoảng **không chồng lấn**.

**Yêu cầu:**

1. Tính elapsed time và flow efficiency.
2. Nếu giảm waiting từ 7 xuống 4 ngày, active giữ nguyên, flow efficiency mô hình mới là bao nhiêu?
3. Vì sao không nên gọi hai con số này là năng suất Developers?

**Đáp án:**

\[
\text{Elapsed}=4,5+7=11,5\text{ ngày};
\quad
\text{Flow efficiency}=\frac{4,5}{11,5}\times100\%\approx39,1\%.
\]

Nếu chờ còn 4 ngày:

\[
\frac{4,5}{4,5+4}\times100\%
=\frac{4,5}{8,5}\times100\%
\approx52,9\%.
\]

Đây là **mô hình tính**, chưa chứng minh cải tiến thật. Các điều kiện test và chất lượng cần giữ; tỷ lệ không đo phẩm chất người làm.

### Bài tập 9 — Tại sao median cycle time chưa đủ?

Nhóm báo cycle time trung vị **9 ngày** cho 9 PBI Finished. Còn 5 item chưa Done với work item age **3, 7, 10, 11, 15 ngày**.

**Yêu cầu:** nêu ít nhất ba câu hỏi quan trọng trước khi kết luận nhóm có flow tốt và một hành động thực tế cho item già nhất.

**Gợi ý:** xem loại việc/size, blocker và tác động goal, điều kiện Finished/DoD, phân bố cycle time và dữ liệu còn thiếu. Với item 15 ngày, tìm owner/điều kiện blocked, có thể swarming hoặc điều chỉnh scope an toàn; không chuyển Done giả hay reset tuổi item.

### Bài tập 10 — Scrum: điều chỉnh Sprint khi phát hiện rủi ro

Đang giữa Sprint, Developers phát hiện test tranh chỗ cuối thất bại. PO muốn thêm email nhưng Sprint Goal là **đăng ký miễn phí đáng tin**.

**Yêu cầu:** mô tả Developers và PO nên phối hợp điều chỉnh gì; có cần hủy Sprint ngay không?

**Gợi ý:** Developers điều chỉnh Sprint Backlog và kỹ thuật, PO cùng làm rõ phạm vi/ưu tiên, Scrum Master hỗ trợ gỡ trở ngại và cách Scrum vận hành. Tập trung goal và chất lượng, không tự thêm email tùy chọn. Không hủy Sprint theo phản xạ; chỉ PO có quyền hủy nếu Sprint Goal trở nên lỗi thời theo Scrum.

### Bài tập 11 — Kanban: nhóm kéo thêm việc khi Verify bị nghẽn

Verify có bốn item chờ môi trường; Developing có hai người sẵn sàng. Nhóm muốn mở sáu story mới để “không lãng phí công suất”.

**Yêu cầu:** đề xuất quy tắc kéo việc, cách giúp hoàn tất và metric đo tác động.

**Gợi ý:** xem WIP/age, gỡ blocker môi trường với owner, chuẩn bị test/data, hỗ trợ review hoặc cải tiến CI theo năng lực, tránh mở hàng loạt việc mới. Dùng WIP limit thử nghiệm, có ngoại lệ khẩn rõ. Đo blocked time, item age, throughput, cycle time và chất lượng.

### Bài tập 12 — XP: contract tests xanh, dữ liệu vẫn sai

Web và Enrollment có contract tests xanh. Khi hai request đồng thời, DB vẫn lưu vượt sức chứa.

**Yêu cầu:** giải thích vì sao và đề xuất các tầng test cần bổ sung.

**Gợi ý:** contract tests kiểm tra giao tiếp giữa consumer/provider, không chứng minh transaction/concurrency. Cần integration tests với DB và transaction phù hợp, authn/authz, idempotency, failure modes, E2E theo hành vi; giữ CI và test dữ liệu tương ứng trong DoD.

### Bài tập 13 — Phân tích phụ thuộc IdP

Vendor thông báo đổi claims trong một tháng, nhưng chưa rõ có breaking change. Có một phiên bản hiện hành vẫn dùng được.

**Yêu cầu:** phân loại **risk** hay **blocker**, viết ba hành động trước khi yêu cầu chuyển toàn bộ code.

**Gợi ý:** trước hết là **rủi ro phụ thuộc**; có thể thành blocker nếu hợp đồng hiện hành không đáp ứng, hết hỗ trợ hoặc bản mới bắt buộc. Xác nhận notice/version và consumer, chạy compatibility/security tests, thống nhất timeline/hỗ trợ và phương án adapter/migration. Không bỏ kiểm tra quyền hoặc giữ version không an toàn.

### Bài tập 14 — PDCA: thử nghiệm giảm thời gian chờ Verify

Một đội giả định đo được trung vị waiting tại Verify **3 ngày** trong các PBI cùng loại. Nhóm muốn giảm bằng cách chuẩn bị test data/contract từ refinement.

**Yêu cầu:** soạn:

1. Giả thuyết **Nếu… thì… vì…**.
2. Phạm vi thử nhỏ.
3. Metric chính và hai guardrails.
4. Hai yếu tố gây nhiễu.
5. Điều kiện quyết định giữ/đổi/hoàn tác.

**Gợi ý:**

> “Nếu chuẩn bị contract examples và test data trước khi code các PBI đăng ký, thời gian chờ Verify sẽ giảm vì ít mismatch và ít thiếu môi trường lúc kết thúc.”

Metric: blocked/waiting time Verify theo cách đếm giữ nguyên. Guardrails: DoD/test bắt buộc và lỗi dữ liệu; thêm tải test/support nếu liên quan. Confounders: PBI kỳ sau nhỏ hơn, staging vừa sửa; không tuyên bố nhân quả chắc chỉ bằng một kỳ ngắn.

### Bài tập 15 — Vai trò trong cuộc họp quyết định release

Chia nhóm học thành bốn vai: PO, Developers, người có quyền release/security, đại diện hỗ trợ. Có áp lực mở cho toàn bộ học viên vào ngày mai; kiểm thử concurrent requests chưa đạt.

**Yêu cầu đóng vai:**

- PO trình bày Product Goal, giá trị và lựa chọn phạm vi.
- Developers nêu bằng chứng, rủi ro và điều kiện kiểm chứng.
- Release/security owner nêu chính sách và quyết định trong quyền.
- Support nêu tác động và khả năng phục hồi/thông tin người học.

**Gợi ý:** một kết quả tốt là **No-go cho hành vi ghi chưa an toàn**, kế hoạch sửa/test có owner và mốc xem lại, truyền thông rõ; có thể giao một phần độc lập đã Done nếu phù hợp. Không phải người nói to nhất sẽ quyết định tất cả.

### Bài tập 16 — Diễn biến đảo chiều: email hóa ra bắt buộc

Nhóm đã ưu tiên đường tra trạng thái và để email sau. Một tài liệu hợp đồng được xác minh cho thấy email thông báo sau khi đăng ký được xác nhận là **điều kiện bắt buộc**.

**Yêu cầu:** cập nhật phiếu phân tích theo sáu mục: bằng chứng mới, tác động, phạm vi, phụ thuộc, test/DoD và mốc release.

**Gợi ý:** ghi rõ nghĩa vụ và nguồn, đưa email trở lại phạm vi bắt buộc, làm rõ điều kiện delivery/failed send, contract Notification, idempotency/riêng tư, test tích hợp và decision rights. Không lén giữ giả định cũ chỉ vì đã lên kế hoạch.

### Bài tập 17 — Bài phân tích tổng hợp không có một đáp án duy nhất

Một nhóm khác báo:

- 70% PBI hoàn tất được ước tính theo kế hoạch ban đầu.
- Hai PBI quan trọng có test dữ liệu chưa đạt.
- Nhiều story đã hoàn thành nhưng chưa release.
- Support báo người dùng chưa thể tự giải quyết lỗi.
- Vendor API sắp ngừng hỗ trợ phiên bản cũ.

**Yêu cầu:** viết **phiếu quyết định 1–2 trang**: kết quả người dùng, sự kiện–giả thuyết, phân loại rủi ro, stakeholder, một Value Stream Map ngắn, 3 lựa chọn thích ứng, PBI ưu tiên, điều kiện Done/release và kế hoạch đo.

**Gợi ý đánh giá:**

- Không lấy “70% task” làm bằng chứng Increment Done.
- Xử lý an toàn dữ liệu và ngừng hỗ trợ phiên bản theo thẩm quyền.
- Thấy phụ thuộc, chờ release và giá trị support thực.
- Có lựa chọn cải tiến nhỏ, không chỉ “đổi framework”.
- Ghi giả định và điều kiện kiểm chứng, không hứa ngày chắc chắn.

### Bài tập 18 — Xây bản phản biện cho quyết định của chính mình

Sau khi viết kế hoạch thích ứng, giả sử bạn là reviewer không tham gia quyết định. Hãy tìm **ít nhất năm điểm có thể làm kế hoạch sai**:

- Dữ liệu nào mới là giả định?
- Một người dùng/nhóm nào chưa được hỏi?
- Test nào chưa chạy với hệ thống thật?
- Có bước kiểm soát bắt buộc nào bị gọi nhầm là waste?
- Có phụ thuộc ẩn hoặc tải support sau release?
- Nếu kết quả không như dự đoán, nhóm có dám đổi kế hoạch?

**Gợi ý:** kế hoạch tốt không chỉ có lý do **ủng hộ**, mà còn có điều kiện **có thể khiến nó bị bác bỏ**. Đây là nền tảng của kiểm tra–thích ứng và trách nhiệm chuyên môn.

## 26. Checklist phân tích tình huống và xác định nhu cầu thích ứng

### A. Hiểu bối cảnh và giá trị

- [ ] Đã xác định **người dùng/người nhận giá trị** và hành vi họ cần thực hiện.
- [ ] Có **Product Goal** hoặc mục tiêu nghiệp vụ liên quan; không chỉ danh sách task.
- [ ] Mô tả được ranh giới sản phẩm, phần đã có và phần đang làm.
- [ ] Biết những bên liên quan và quyền quyết định theo ngữ cảnh thực.
- [ ] Phân biệt output kỹ thuật với outcome người dùng.
- [ ] Không suy nhu cầu người dùng chỉ từ đề nghị của một stakeholder.
- [ ] Có danh sách những điều kiện **bắt buộc** về dữ liệu, quyền, chất lượng, vận hành/hợp đồng.

### B. Thu và đánh giá bằng chứng

- [ ] Tách **sự kiện quan sát** khỏi diễn giải, giả thuyết và hành động.
- [ ] Nêu nguồn, thời gian, môi trường, version và mức tin cậy khi cần.
- [ ] Phân biệt số lượt, người dùng, ticket, PBI, PR và Increment.
- [ ] Không cộng các tập dữ liệu chồng lấn hoặc dùng mẫu số sai.
- [ ] Có dữ liệu về **những item chưa Done**, không chỉ item Finished.
- [ ] Những lỗ hổng dữ liệu và giả định được ghi rõ.
- [ ] Không quy lỗi cá nhân/nhóm khi root cause chưa có bằng chứng.
- [ ] Có một kế hoạch lấy thêm thông tin an toàn, tương xứng rủi ro.

### C. Phân loại nhu cầu thích ứng

- [ ] Phân biệt **làm rõ yêu cầu**, **thay đổi phạm vi**, **defect**, **rủi ro**, **blocker** và **incident**.
- [ ] Đã hỏi Product Goal có đổi hay chỉ cách đạt mục tiêu cần thay.
- [ ] Xác định tác động tới user story/acceptance criteria/DoD.
- [ ] Xác định những thay đổi về ưu tiên backlog, flow, kỹ thuật và phối hợp.
- [ ] Có đánh giá IdP/vendor, schema/version, môi trường, quyền và ràng buộc.
- [ ] Sự cố nghiêm trọng không bị chờ qua lịch Sprint/backlog thông thường.
- [ ] Không gọi hoạt động chất lượng bắt buộc là lãng phí để loại bỏ.
- [ ] Những yêu cầu mới chưa được kiểm chứng giá trị không tự nhảy lên đầu backlog.

### D. Phân tích rủi ro và phụ thuộc

- [ ] Có bảng rủi ro với hậu quả, bằng chứng, điều chưa biết, owner và bước tiếp.
- [ ] Nguy cơ dữ liệu sai/truy cập trái quyền được ưu tiên theo mức hậu quả.
- [ ] Phụ thuộc ghi rõ **bên cần, bên cung cấp, đầu ra và điều kiện kiểm chứng**.
- [ ] Có mốc **cần biết** cho phụ thuộc rủi ro cao, không chỉ ngày giao dự kiến.
- [ ] Phân biệt vendor risk chưa xảy ra với blocker hiện tại.
- [ ] Có phương án compatibility hoặc fallback **không bỏ an toàn** khi phụ thuộc chậm.
- [ ] Có đường escalation với đúng người có quyền, không chỉ thêm người nhận báo cáo.
- [ ] Có kế hoạch vận hành/khôi phục xét tới **dữ liệu và side effects**, không chỉ code.

### E. Tổ chức lại giá trị và cách làm

- [ ] PBI ưu tiên được viết theo **lát cắt dọc có hành vi dùng được**.
- [ ] Những bước kỹ thuật có thể merge nhỏ và an toàn, nhưng không bị tính như Done giả.
- [ ] User story có ví dụ thành công, lỗi, rủi ro và quyền quan trọng.
- [ ] Sprint Goal (nếu dùng Scrum) diễn đạt giá trị, không phải KPI số task.
- [ ] Developers có thể điều chỉnh Sprint Backlog khi học thêm; PO quản lý Product Backlog.
- [ ] Kanban DoW và WIP/blocked policies đủ rõ nếu áp dụng.
- [ ] Có hành động giúp **item dở hoàn tất**, không liên tục mở việc mới.
- [ ] CI/contract/integration/security tests tương xứng rủi ro.
- [ ] Mock, stub, prototype và spike được mô tả đúng giới hạn.
- [ ] Team biết **bằng chứng nào còn thiếu** để gọi Increment Done.

### F. Quyết định phát hành và giao tiếp

- [ ] Phân biệt code complete, Increment Done và release/outcome.
- [ ] Những kiểm thử bắt buộc đã chạy trên môi trường phù hợp và đạt.
- [ ] Nếu chưa đạt, có quyết định No-go/đổi phạm vi minh bạch theo quyền.
- [ ] Không đưa lỗi dữ liệu/quyền nghiêm trọng ra người dùng chỉ để lấy feedback.
- [ ] Có monitoring, runbook, người hỗ trợ và khả năng khôi phục theo rủi ro.
- [ ] Stakeholders biết điều đã xác nhận, điều còn bất định, rủi ro và điểm xem lại.
- [ ] Không báo “x% task Done” như bằng chứng giá trị hoặc chất lượng.
- [ ] Nếu scope bắt buộc thay đổi, cập nhật backlog/acceptance/DoD và dự báo phù hợp.

### G. Đo lường và học sau thích ứng

- [ ] Có một outcome/flow problem cụ thể, không chỉ mục tiêu “làm Agile tốt hơn”.
- [ ] Viết được giả thuyết **Nếu… thì… vì…**, có thể bị bác bỏ.
- [ ] Có baseline và định nghĩa metrics nhất quán.
- [ ] Có **metric chính, guardrails và mốc xem lại**.
- [ ] Xem WIP, cycle time, work item age, blocked time/throughput khi phù hợp.
- [ ] Không dùng một chỉ số để xếp hạng cá nhân hoặc đổi DoD cho đẹp.
- [ ] Có xem yếu tố gây nhiễu, thay đổi loại việc, kỳ nghỉ và môi trường.
- [ ] Đánh giá tác động tới support/on-call, dữ liệu và tải làm việc.
- [ ] Có quyết định duy trì, điều chỉnh, hoàn tác hoặc tiếp tục thử dựa trên bằng chứng.
- [ ] Những điều đã học được ghi thành policy/test/working agreement hoặc backlog cần thiết, không chỉ là một cuộc họp.

Checklist dùng để **kiểm tra tính đầy đủ của lập luận**, không phải quy trình duyệt cứng cho mọi PBI. Một trường hợp rủi ro thấp có thể ghi ngắn; một lỗi nghiêm trọng về dữ liệu cần ưu tiên ứng cứu và thẩm quyền phù hợp.

## 27. Tổng kết: thích ứng là một năng lực ra quyết định dựa trên bằng chứng

Khi phân tích ca Học Mở, ta không bắt đầu bằng câu “chọn Scrum hay Kanban” mà bắt đầu từ **người dùng và bằng chứng**. Người học cần tự đăng ký khóa miễn phí đáng tin cậy. Nhưng task cục bộ Done, test tích hợp lỗi, nhiều item đang dở và thay đổi từ nhà cung cấp khiến kế hoạch ban đầu **cần được kiểm tra lại**.

Những bài học cốt lõi:

1. **Hiểu tình huống thật:** kết quả người dùng, giới hạn sản phẩm, stakeholders, timeline, rủi ro và bằng chứng đo.
2. **Phân biệt điều biết và điều đoán:** test thất bại là sự kiện; “DB chắc chắn là nguyên nhân” mới là giả thuyết cần kiểm chứng.
3. **Phân loại thay đổi:** làm rõ yêu cầu, mở rộng scope, defect, dependency, blocker và incident có cách xử lý khác nhau.
4. **Ưu tiên an toàn và giá trị:** không vì muốn giữ ngày release mà bỏ kiểm tra dữ liệu, quyền hoặc điều kiện Done.
5. **Chia lát cắt dọc:** tập trung vào hành vi người dùng có thể sử dụng, không đếm UI/API/DB đã hoàn tất riêng lẻ như các Increment.
6. **Thích ứng đúng vai trò và công cụ:** Scrum bảo vệ mục tiêu và trách nhiệm tạo Increment; Kanban làm rõ flow/WIP; XP/CI giúp phát hiện lỗi sớm; Lean giúp nhìn lãng phí và tối ưu hệ thống.
7. **Quản lý phụ thuộc có điều kiện:** contract, provider, version, môi trường, owner, thời điểm cần biết và kiểm chứng thật.
8. **Đo toàn hệ thống:** outcome người dùng, flow, chất lượng và tải bền vững; không chỉ số task, velocity hay một median đẹp.
9. **Thử nhỏ và học liên tục:** có baseline, giả thuyết, guardrails, yếu tố gây nhiễu và quyết định điều chỉnh.
10. **Truyền thông minh bạch:** nói rõ điều đã đạt, điều còn chưa xác minh và quyết định tiếp theo, thay vì hứa một kết quả khi chưa đủ bằng chứng.

**Thông điệp cuối:** Một nhóm Agile không thành công vì thay kế hoạch thường xuyên hay vì luôn giữ kế hoạch. Họ thành công khi biết **điều gì cần giữ ổn định (giá trị, an toàn, chất lượng, cam kết đúng nghĩa)** và **điều gì cần thay đổi (giả định, thứ tự, cách làm, kiến trúc, phối hợp, phạm vi)** khi bằng chứng mới xuất hiện.

### Thuật ngữ chính

| Thuật ngữ | Ý nghĩa trong bài |
| --- | --- |
| **Adaptation / thích ứng** | Điều chỉnh quyết định, kế hoạch hoặc cách làm dựa trên kiểm tra thực tế và điều kiện mới. |
| **Empiricism / thực nghiệm** | Minh bạch, kiểm tra và thích ứng dựa trên bằng chứng, không chỉ giả định. |
| **Signal / evidence** | Tín hiệu / dữ liệu hoặc sự kiện giúp kiểm chứng điều đang xảy ra. |
| **Observation / interpretation / hypothesis** | Sự kiện quan sát / cách diễn giải / lời giải thích cần kiểm chứng. |
| **Problem statement** | Mô tả khoảng cách giữa trạng thái quan sát và kết quả mong muốn, có bối cảnh. |
| **User outcome** | Thay đổi thực tế trong khả năng/hành vi người dùng. |
| **Output** | Đầu ra đã tạo: tính năng, code, API, test, tài liệu. |
| **Product Goal** | Mục tiêu dài hạn của sản phẩm trong Scrum. |
| **Sprint Goal** | Cam kết về mục đích thống nhất của Sprint. |
| **Product Backlog / Sprint Backlog** | Danh sách có thứ tự công việc cần thiết cho sản phẩm / mục tiêu, việc chọn và kế hoạch của Developers trong Sprint. |
| **User story** | Mô tả ngắn nhu cầu người dùng làm cơ sở đối thoại và làm rõ giá trị. |
| **Acceptance criteria** | Những điều kiện hành vi cụ thể để chấp nhận kết quả hạng mục. |
| **Definition of Done (DoD)** | Cam kết chuẩn chất lượng của Increment. |
| **Increment** | Phần sản phẩm tăng thêm đã tích hợp, có thể sử dụng và đáp ứng DoD. |
| **Vertical slice** | Lát cắt xuyên các tầng cần thiết để tạo hành vi có giá trị và kiểm chứng được. |
| **Scope clarification / scope change** | Làm rõ nghĩa của phạm vi đang có / thay đổi nghĩa vụ hoặc khả năng đã chọn. |
| **Defect / blocker / risk / incident** | Sai hành vi / điều kiện đang chặn / nguy cơ tương lai / sự cố cần ứng cứu. |
| **Backlog refinement** | Làm nhỏ và rõ các Product Backlog Items khi học thêm về giá trị và cách thực hiện. |
| **Kanban / Definition of Workflow (DoW)** | Phương pháp quản lý luồng công việc / các ranh giới và chính sách vận hành flow. |
| **WIP / throughput** | Công việc đang dở / lượng item hoàn tất theo kỳ. |
| **Cycle time / work item age** | Thời gian Started–Finished của item đã xong / tuổi của item chưa xong. |
| **Blocked time / flow efficiency** | Thời gian bị chặn / tỷ lệ thời gian trực tiếp xử lý trên tổng thời gian theo cách đo. |
| **Little's Law** | Quan hệ WIP–throughput–cycle time trung bình trong điều kiện áp dụng. |
| **Lean / Value Stream Mapping** | Tư duy giá trị, dòng chảy và cải tiến / trực quan hóa toàn dòng giá trị. |
| **Muda / Mura / Muri** | Lãng phí / không đều / quá tải. |
| **XP / TDD / CI** | Extreme Programming / phát triển dẫn dắt bởi test / tích hợp liên tục. |
| **Contract test / integration test** | Kiểm tra kỳ vọng giao tiếp giữa các thành phần / kiểm tra thành phần phối hợp thật. |
| **Idempotency** | Khả năng xử lý yêu cầu lặp mà không tạo tác động nghiệp vụ trùng ngoài ý muốn. |
| **Concurrency / data integrity** | Yêu cầu đồng thời / tính đúng đắn và nhất quán dữ liệu. |
| **Provider / consumer dependency** | Phụ thuộc giữa bên cung cấp điều kiện/hợp đồng và bên cần dùng. |
| **Guardrail metric** | Thước đo/điều kiện bảo vệ an toàn, chất lượng và tác động phụ khi thử cải tiến. |
| **Confounder** | Yếu tố gây nhiễu làm việc diễn giải trước–sau có thể sai. |
| **PDCA/PDSA** | Plan–Do–Check/Study–Act: lập kế hoạch, thực hiện thử, kiểm tra/học và điều chỉnh. |
| **No-go / release readiness** | Quyết định chưa cho phát hành / mức sẵn sàng dựa trên điều kiện thực tế. |
| **Decision record** | Bản ghi ngắn về bằng chứng, lựa chọn, người quyết và điều kiện xem lại. |






