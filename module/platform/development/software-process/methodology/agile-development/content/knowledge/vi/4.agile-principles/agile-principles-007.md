# Sử dụng phần mềm hoạt động được làm thước đo tiến triển chủ yếu

Một nhóm có thể báo cáo “đã hoàn thành 90% công việc”, tổ chức nhiều cuộc họp, tạo hàng trăm ticket và viết rất nhiều dòng mã. Nhưng nếu người dùng vẫn chưa thực hiện được một tác vụ trọn vẹn bằng sản phẩm, nhóm có ít bằng chứng đáng tin cậy rằng sản phẩm thực sự đang tiến gần mục tiêu. Đó là lý do một trong 12 nguyên tắc của Agile Manifesto nhấn mạnh:

> **Working software is the primary measure of progress.**
>
> *Phần mềm hoạt động được là thước đo tiến triển chủ yếu.*

Nguyên tắc này không phủ nhận giá trị của thiết kế, phân tích, tài liệu, kiểm thử, kế hoạch hay sự phối hợp. Nó yêu cầu đặt câu hỏi thực chất hơn những con số về hoạt động: **Phần mềm hiện làm được gì một cách đáng tin cậy, và điều đó giúp chúng ta kiểm chứng điều gì?**

Trong module **AGILE_DEVELOPMENT**, tư duy này kết nối với phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục. User story giúp diễn đạt nhu cầu; Product Backlog giúp lựa chọn việc tiếp theo; Scrum tạo nhịp kiểm tra Increment; Kanban giúp nhìn dòng công việc; XP và các thực hành kỹ thuật giúp tạo phần mềm có thể sử dụng, kiểm thử và thay đổi an toàn. Mỗi công cụ chỉ hữu ích khi đưa nhóm đến gần một phần mềm **thực sự hoạt động** và tạo cơ hội học hỏi.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao phần mềm hoạt động được là thước đo tiến triển *chủ yếu*, và vì sao “chủ yếu” không có nghĩa là “duy nhất”.
2. Phân biệt mức độ bận rộn, tỷ lệ hoàn tất công việc, sản phẩm chạy được, khả năng phát hành và kết quả sử dụng.
3. Xác định các tiêu chí để một Increment được coi là hoạt động được, bao gồm chức năng, tích hợp, kiểm thử, chất lượng và khả năng kiểm chứng.
4. Chia yêu cầu thành lát cắt chức năng có thể chạy xuyên suốt, sử dụng tiêu chí chấp nhận và Definition of Done (DoD) để tránh tiến độ ảo.
5. Kết hợp bằng chứng về sản phẩm chạy được với chỉ số dòng công việc, chất lượng và phản hồi người dùng để điều chỉnh ưu tiên.
6. Nhận diện các ngoại lệ và trường hợp đặc biệt như nghiên cứu kỹ thuật, thay đổi hạ tầng, di chuyển dữ liệu hoặc hệ thống chịu ràng buộc pháp lý.

## 1. “Tiến triển” là gì trong phát triển phần mềm?

Tiến triển là mức độ một nhóm đã biến nhu cầu hoặc giả định thành khả năng sử dụng được và có bằng chứng đủ tin cậy để quyết định bước tiếp theo. Trong công việc phần mềm, các lớp thông tin rất dễ bị đánh đồng:

| Lớp thông tin | Ví dụ | Nó thực sự chứng minh điều gì? | Nó chưa chứng minh điều gì? |
|---|---|---|---|
| **Hoạt động** | Họp planning, phân tích yêu cầu, viết mã, review pull request | Nhóm đang thực hiện công việc | Một chức năng đã hoàn tất hoặc người dùng nhận giá trị |
| **Hiện vật trung gian** | Tài liệu kiến trúc, thiết kế Figma, prototype, mã trên nhánh riêng | Có ý tưởng, giải pháp hoặc hiện vật để trao đổi | Phần mềm đã tích hợp và hoạt động trong điều kiện dự kiến |
| **Công việc được đánh dấu xong** | Ticket ở cột Done, 20 story point đã đóng | Công việc đáp ứng cách nhóm đang ghi nhận trạng thái | Tiêu chí “xong” có bảo đảm khả năng sử dụng hay không |
| **Phần mềm hoạt động được** | Một luồng người dùng được tích hợp, kiểm thử, đạt chuẩn chất lượng và có thể kiểm tra | Một khả năng cụ thể thực sự tồn tại trong sản phẩm | Người dùng chắc chắn yêu thích hoặc tạo ra tác động kinh doanh |
| **Kết quả sử dụng** | Người dùng hoàn tất tác vụ tốt hơn, giảm lỗi hoặc thời gian thao tác | Sản phẩm có tín hiệu tạo giá trị trong thực tế | Tác động có chắc chắn do thay đổi này gây ra hay không, nếu chưa kiểm soát yếu tố nhiễu |

Những lớp này không loại trừ nhau. Thiết kế tốt giúp hiện thực hóa chức năng; tài liệu phù hợp giúp vận hành an toàn; chỉ số dòng công việc giúp phát hiện chờ đợi. Tuy nhiên, các hoạt động và hiện vật trung gian là **tín hiệu gián tiếp**. Phần mềm hoạt động được cho thấy những quyết định thiết kế và giả định kỹ thuật đã thực sự gặp nhau trong một hệ thống chạy được.

### 1.1. Vì sao gọi là “thước đo chủ yếu”, không phải “thước đo duy nhất”?

Từ **primary** đặt phần mềm hoạt động được ở vị trí ưu tiên khi đánh giá tiến triển phát triển. Nó không yêu cầu bỏ toàn bộ thước đo khác. Một chức năng chạy được nhưng không an toàn, không thể duy trì hoặc không giải quyết nhu cầu thì chưa đủ để gọi là thành công sản phẩm.

Cần phối hợp ít nhất ba câu hỏi:

- **Năng lực đã hình thành:** Phần mềm hiện làm được việc gì, với điều kiện và tiêu chuẩn chất lượng nào?
- **Khả năng giao và vận hành:** Năng lực ấy có thể được tích hợp, phát hành, hỗ trợ và thay đổi an toàn đến đâu?
- **Tác động mong muốn:** Người dùng hoặc tổ chức thực sự nhận được ích lợi gì; điều gì cần kiểm chứng tiếp?

Nguyên tắc này nhấn mạnh bằng chứng về sản phẩm chạy được bởi nó thường khó “tô đẹp” hơn báo cáo phần trăm hoàn thành. Dù vậy, ngay cả một bản demo chạy tốt cũng cần được kiểm tra trong điều kiện phù hợp trước khi đưa ra kết luận rộng.

### 1.2. Từ “90% hoàn thành” sang “đã dùng được phần nào?”

Ví dụ, một tính năng đặt lại mật khẩu được chia thành các mục: giao diện 100%, API 95%, gửi email 80%, kiểm thử 20%, cấu hình triển khai 0%. Báo cáo trung bình có thể tạo cảm giác dự án gần xong, nhưng **chưa có luồng đặt lại mật khẩu hoàn chỉnh**. Nếu các thành phần không tích hợp được, mức hoàn thành thực dụng của khả năng người dùng cần vẫn là **chưa đạt**.

Ngược lại, nếu nhóm giao được một luồng nhỏ gồm yêu cầu đặt lại mật khẩu, nhận liên kết hợp lệ, đổi mật khẩu, đăng nhập bằng mật khẩu mới, xử lý liên kết hết hạn và kiểm thử các rủi ro quan trọng, nhóm có một năng lực cụ thể để kiểm chứng. Năng lực này có thể nhỏ hơn kế hoạch dài hạn nhưng có bằng chứng tiến triển mạnh hơn.

Không nên biến ví dụ thành phép tính kiểu “một luồng xong = 20% giá trị”, vì các luồng có giá trị và độ khó khác nhau. Điều đáng quan tâm là **những khả năng nào đã thật sự hoàn tất**, thay vì suy luận từ trung bình tiến độ của từng bộ phận.

## 2. Thế nào là phần mềm “hoạt động được”?

“Chạy trên máy lập trình viên” là điều kiện rất yếu. “Có thể demo” cũng chưa đủ nếu demo dùng dữ liệu giả, bỏ qua kiểm thử hoặc che giấu bước thủ công quan trọng. Mức độ “hoạt động được” cần gắn với ngữ cảnh sản phẩm và những rủi ro cần kiểm soát.

Một khả năng phần mềm đáng tin cậy thường có các thuộc tính sau:

1. **Thực hiện đúng hành vi mong đợi.** Các trường hợp sử dụng quan trọng và tiêu chí chấp nhận đã được đáp ứng; cả đường đi thông thường lẫn trường hợp lỗi phù hợp đều được xử lý.
2. **Tích hợp được với hệ thống liên quan.** Giao diện, dịch vụ, dữ liệu và thành phần phụ thuộc phối hợp theo đường đi thực tế, không chỉ thành công ở từng thành phần cô lập.
3. **Đạt tiêu chuẩn chất lượng đã thỏa thuận.** Kiểm thử cần thiết đã hoàn thành; các yêu cầu phù hợp về bảo mật, hiệu năng, khả năng truy cập, độ tin cậy và quan sát hệ thống được đáp ứng.
4. **Có thể kiểm tra lại.** Thành viên khác có thể quan sát hành vi, chạy kiểm thử hoặc dùng phiên bản triển khai trong môi trường phù hợp để xác nhận kết quả.
5. **Không che giấu phần việc chưa xong.** Các bước thủ công, cấu hình tạm, tính năng chưa hỗ trợ hoặc nợ kỹ thuật quan trọng được làm rõ thay vì gọi toàn bộ là Done.
6. **Có trạng thái phát hành rõ ràng.** Nhóm biết phần mềm đang chạy trong môi trường nào, có thể phát hành hay còn cần thêm điều kiện gì.

Tiêu chuẩn phải **phù hợp rủi ro và mục tiêu**, không đồng nghĩa mọi tính năng nhỏ đều phải trải qua một bộ thủ tục giống nhau. Một bản thử nghiệm nội bộ cho giả thuyết sản phẩm có yêu cầu khác hệ thống thanh toán hoặc xử lý dữ liệu nhạy cảm. Dù trong bối cảnh nào, không nên âm thầm giảm chuẩn chất lượng để tạo cảm giác hoàn thành.

### 2.1. Phân biệt bốn trạng thái dễ nhầm

| Trạng thái | Ý nghĩa | Có nên dùng làm bằng chứng phần mềm hoàn tất? |
|---|---|---|
| **Prototype / proof of concept** | Minh họa ý tưởng hoặc kiểm tra tính khả thi, có thể dùng dữ liệu giả và chưa tích hợp đầy đủ | Có giá trị học tập, nhưng không tự động là Increment sản phẩm hoàn tất |
| **Mã đã được viết / đã merge** | Một phần mã đã được tạo hoặc hợp nhất | Chưa đủ; phải kiểm tra hành vi, tích hợp và tiêu chuẩn chất lượng |
| **Increment đạt Definition of Done** | Phần tăng trưởng của sản phẩm đạt chuẩn chất lượng chung, có thể sử dụng và kiểm tra | Là bằng chứng mạnh về tiến triển phát triển trong Scrum |
| **Đã phát hành cho người dùng** | Phần mềm đã được cung cấp ở một phạm vi sử dụng cụ thể | Cho phép thu thập phản hồi thực tế; vẫn cần quan sát để biết giá trị và rủi ro |

Trong Scrum, **Increment phải đạt Definition of Done để được coi là một phần của Increment**; một Increment có thể được cung cấp cho stakeholders trước khi Sprint kết thúc. Sprint Review là dịp kiểm tra và thích ứng, **không phải cổng phê duyệt bắt buộc** để phát hành. “Có thể phát hành” và “đã phát hành” là hai trạng thái khác nhau.

**Definition of Done (DoD)** là mô tả chính thức về trạng thái của Increment khi đáp ứng các tiêu chuẩn chất lượng áp dụng cho sản phẩm. Khi có chuẩn DoD của tổ chức, Scrum Team tuân thủ mức tối thiểu đó; nếu chưa có, Scrum Team thiết lập DoD phù hợp. Không nên để mỗi người tự định nghĩa Done theo mức thuận tiện của phần việc mình.

### 2.2. Kiểm thử đi cùng hành vi hoạt động

Để nói một luồng hoạt động được, nhóm cần bằng chứng phù hợp:

- **Kiểm thử đơn vị:** Logic cục bộ có hành vi mong đợi.
- **Kiểm thử tích hợp:** Các thành phần giao tiếp đúng khi kết nối.
- **Kiểm thử hành vi đầu-cuối:** Một luồng sử dụng trọng yếu chạy qua các thành phần thực tế.
- **Kiểm tra phi chức năng:** Bảo mật, hiệu năng, khả năng truy cập, xử lý lỗi và khả năng quan sát theo mức rủi ro.
- **Kiểm tra cùng người dùng hoặc bên liên quan:** Chức năng có dễ hiểu, dùng được và giải quyết đúng tình huống không.

Không nhất thiết kiểm thử mọi trường hợp bằng một bộ kiểm thử giao diện tự động rất lớn. Nhóm lựa chọn chiến lược kiểm thử cân đối, đáng tin cậy và bảo trì được. **Số lượng bài test hoặc tỷ lệ bao phủ mã** chỉ là thông tin bổ trợ; bài test vượt qua có thể vẫn bỏ sót một hành vi quan trọng.

## 3. Từ user story đến một Increment kiểm chứng được

Một user story không nên chỉ là nhiệm vụ lập trình được viết theo khuôn “Là một..., tôi muốn...”. Nó diễn đạt nhu cầu để cùng trao đổi, làm rõ giá trị và xác định cách kiểm tra.

Ví dụ:

> **Là** người dùng đã đăng ký, **tôi muốn** tự đặt lại mật khẩu khi quên **để** có thể truy cập lại tài khoản mà không cần liên hệ hỗ trợ.

Từ câu chuyện này, nhóm làm rõ ranh giới: người dùng cần nhận được gì, có tình huống lỗi nào, bảo mật ra sao, và mức nào là đủ để cung cấp khả năng đầu tiên.

### 3.1. Chia theo lát cắt chức năng xuyên suốt

**Lát cắt dọc (vertical slice)** là phần nhỏ đi qua các lớp cần thiết để tạo ra một hành vi sử dụng được. Một lát cắt có thể gồm giao diện, API, xử lý nghiệp vụ, dữ liệu, kiểm thử và triển khai. Nó thường hữu ích hơn việc chia công việc thành các “lát cắt ngang” chỉ theo tầng kỹ thuật.

| Cách chia | Ví dụ | Khả năng kiểm chứng sau khi xong |
|---|---|---|
| Theo tầng kỹ thuật | Tuần 1 làm toàn bộ UI, tuần 2 toàn bộ API, tuần 3 toàn bộ database | Các phần riêng lẻ hoàn thành nhưng luồng sử dụng có thể chưa chạy |
| Theo hành vi người dùng | Đầu tiên hoàn thiện một luồng đặt lại mật khẩu an toàn; sau đó cải thiện thông báo, khả năng hỗ trợ và các kênh khác | Mỗi lát cắt tạo ra một hành vi có thể kiểm tra từ đầu đến cuối |

Không phải yêu cầu nào cũng chia nhỏ mà giữ nguyên toàn bộ giá trị ngay được. Nhóm phải cân nhắc phụ thuộc, dữ liệu và kiến trúc; đôi khi cần một công việc nền tảng trước. Mục đích không phải ép mọi ticket thành một tính năng hiển thị, mà là **giảm thời gian đến bằng chứng hoạt động đáng tin cậy**.

### 3.2. Viết tiêu chí chấp nhận có thể quan sát

Với ví dụ đặt lại mật khẩu, tiêu chí chấp nhận có thể bao gồm:

- Người dùng nhập email đăng ký và nhận hướng dẫn đặt lại mật khẩu mà không làm lộ thông tin tài khoản cho bên không được phép.
- Liên kết đặt lại mật khẩu chỉ có hiệu lực trong thời gian quy định và không thể dùng lại sau khi đổi mật khẩu thành công.
- Mật khẩu mới phải tuân thủ chính sách hiện hành, được lưu và xử lý an toàn.
- Người dùng có thể đăng nhập bằng mật khẩu mới; các trường hợp lỗi có thông báo phù hợp.
- Hoạt động có thể được theo dõi và hỗ trợ vận hành theo quy định bảo mật.

Đội có thể diễn đạt một phần hành vi bằng cú pháp Given–When–Then:

~~~gherkin
Feature: Dat lai mat khau

  Scenario: Doi mat khau bang lien ket hop le
    Given nguoi dung da yeu cau dat lai mat khau
    And lien ket dat lai mat khau con hieu luc
    When nguoi dung dat mat khau moi hop le
    Then he thong xac nhan thay doi thanh cong
    And nguoi dung co the dang nhap bang mat khau moi
    And lien ket cu khong the su dung lai

  Scenario: Lien ket da het han
    Given lien ket dat lai mat khau da het han
    When nguoi dung thu dat mat khau moi
    Then he thong tu choi yeu cau
    And huong dan nguoi dung tao yeu cau moi
~~~

Ví dụ trên là một **đặc tả hành vi**, chưa tự chứng minh chức năng đã chạy. Nhóm vẫn cần triển khai, kiểm thử và kiểm tra các ràng buộc bảo mật phù hợp. Tiêu chí chấp nhận nói *câu chuyện này cần làm gì*; Definition of Done nói *mức chất lượng chung mà mọi Increment phải đạt*.

### 3.3. Xác định DoD trước khi kết luận Done

Ví dụ một DoD ở mức đội phát triển phần mềm web (cần điều chỉnh theo hệ thống):

| Nhóm tiêu chí | Câu hỏi xác nhận |
|---|---|
| Mã nguồn và tích hợp | Mã đã được review phù hợp, tích hợp vào nhánh chính và xây dựng thành công? |
| Hành vi | Các tiêu chí chấp nhận quan trọng đã được kiểm chứng bằng cách thích hợp? |
| Kiểm thử | Các kiểm thử cần thiết đã vượt qua; không còn lỗi nghiêm trọng chưa được xử lý trái với chuẩn chất lượng? |
| Vận hành | Cấu hình, dữ liệu, logging/monitoring, kế hoạch triển khai hoặc quay lui đã sẵn sàng khi cần? |
| Bảo mật và chất lượng | Các yêu cầu bảo mật, quyền riêng tư, khả năng truy cập, hiệu năng liên quan đã được xem xét? |
| Khả năng kiểm tra | Có phiên bản hoặc môi trường giúp các bên liên quan kiểm tra Increment một cách đáng tin cậy? |

Khi không đáp ứng DoD, công việc chưa được tính là Increment hoàn tất, dù nhiều phần code đã viết. Nhóm nên làm minh bạch tình trạng, xử lý phần còn thiếu và học từ nguyên nhân gây chậm, thay vì đổi nhãn để đạt chỉ tiêu.

## 4. Đo tiến triển bằng bằng chứng từ phần mềm hoạt động

Nguyên tắc không đưa ra một công thức tính tiến độ duy nhất. Một sản phẩm có nhiều loại chức năng, rủi ro và giá trị khác nhau; do đó, số lượng màn hình hoặc story point đã đóng khó phản ánh chính xác tiến triển. Hãy chọn cách trình bày trực tiếp **những năng lực đã đạt chuẩn**, cộng với tín hiệu hỗ trợ giải thích bối cảnh.

### 4.1. Bảng theo dõi khả năng đã kiểm chứng

Giả sử đội xây dựng một dịch vụ học trực tuyến và có mục tiêu “học viên tự mua và bắt đầu một khóa học”. Thay vì báo cáo “khoảng 75% backend”, nhóm có thể trình bày:

| Khả năng người dùng | Bằng chứng hiện có | Trạng thái đáng tin cậy | Câu hỏi tiếp theo |
|---|---|---|---|
| Xem thông tin khóa học | Trang thực tế hoạt động với dữ liệu khóa học và kiểm thử liên quan đạt | Đạt DoD | Người dùng có hiểu đủ thông tin để chọn khóa học không? |
| Tạo đơn đăng ký | Luồng từ giao diện đến dữ liệu đơn đã tích hợp, xử lý lỗi quan trọng | Đạt DoD | Các trường hợp hủy hoặc đăng ký trùng đã được kiểm tra? |
| Thanh toán | UI và API riêng lẻ có kết quả, tích hợp đối tác chưa hoàn tất | **Chưa đạt DoD** | Phụ thuộc nào cần tháo chặn để hoàn thiện luồng an toàn? |
| Truy cập nội dung đã mua | Đã thiết kế phân quyền, chưa kiểm thử luồng đầu-cuối | **Chưa đạt DoD** | Cần hoàn thành lát cắt nào để kiểm chứng quyền truy cập? |

Hai khả năng đầu tiên là bằng chứng có thể kiểm tra. Hai khả năng còn lại vẫn đang tiến hành dù nhiều nhiệm vụ con đã xong. Bảng không bắt buộc quy đổi hai trên bốn thành **50% tổng giá trị**, vì các phần không có cùng độ lớn, mức quan trọng hoặc rủi ro.

### 4.2. Tập hợp chỉ số hỗ trợ, không thay thế

| Loại tín hiệu | Ví dụ đo lường | Sử dụng phù hợp | Nguy cơ hiểu sai |
|---|---|---|---|
| **Khả năng phần mềm hoàn tất** | Những luồng nghiệp vụ/tiêu chí chấp nhận đã đạt DoD và có thể minh chứng | Chỉ ra chính xác phần người dùng có thể thực hiện | Đếm chức năng như thể chúng có giá trị ngang nhau |
| **Tiến triển theo mục tiêu** | Các khả năng đã hoàn tất đang phục vụ Product Goal hoặc Sprint Goal như thế nào | Giữ trọng tâm vào mục tiêu thay vì danh sách việc | Gắn nhãn “xong” khi tiêu chí chất lượng chưa đạt |
| **Dòng công việc** | Work in progress, work item age, cycle time, throughput | Nhìn thời gian chờ, tắc nghẽn và khả năng dự báo | Dùng throughput để so năng suất cá nhân hoặc các nhóm có công việc không tương đương |
| **Chất lượng và khả năng vận hành** | Lỗi lọt ra môi trường sử dụng, lỗi hồi quy, sự cố triển khai, thời gian khôi phục | Bảo đảm tiến triển không bị “mua” bằng rủi ro hoặc nợ chất lượng | Chỉ xem số test pass mà bỏ qua mức độ hữu ích của test |
| **Phát hành và phản hồi** | Thời gian từ hoàn tất đến khi nhận phản hồi; phản ánh từ người dùng | Kiểm tra nhóm có học sớm và điều chỉnh được không | Coi nhiều lần triển khai là đồng nghĩa nhiều giá trị |
| **Kết quả sử dụng** | Tỷ lệ hoàn tất tác vụ, số bước thao tác, lỗi người dùng gặp, mức đáp ứng nhu cầu | Xem phần mềm đang tạo giá trị mong muốn không | Tuyên bố nhân quả khi thiếu dữ liệu, mẫu hoặc bối cảnh |

Ví dụ, một đội có throughput ổn định nhưng cycle time tăng có thể đang tích tụ công việc khó, chờ kiểm thử hoặc tăng phụ thuộc. Đội dùng dữ liệu để điều chỉnh dòng công việc, không kết luận vội rằng một cá nhân “làm chậm”. Với Scrum, **velocity/story point (nếu được dùng)** là một cách hỗ trợ dự báo trong đội theo quy ước ước lượng của chính đội, không phải thước đo tuyệt đối về giá trị phần mềm và không thích hợp để xếp hạng đội.

### 4.3. Cập nhật tiến độ bằng minh chứng thay vì phần trăm cảm tính

Một cách cập nhật ngắn gọn nhưng hữu ích:

> **Mục tiêu giai đoạn:** Học viên mua và truy cập được khóa học.
>
> **Đã hoạt động:** Xem khóa học và tạo đơn, đã đạt DoD và có thể kiểm tra trên môi trường tích hợp.
>
> **Chưa hoàn tất:** Thanh toán và cấp quyền truy cập; đang chờ tích hợp phương thức thanh toán.
>
> **Rủi ro:** Phụ thuộc đối tác có thể ảnh hưởng dự báo; luồng lỗi thanh toán cần kiểm thử.
>
> **Lựa chọn tiếp theo:** Ưu tiên tích hợp thanh toán và hoàn tất lát cắt mua–truy cập trước khi bắt đầu tính năng gợi ý khóa học.

Cách này trình bày trực tiếp điều đã chứng minh được và nơi cần quyết định. Một bản demo cũng nên dùng cấu hình, dữ liệu và hành vi đủ đại diện. Nếu dùng mock, cờ giả lập hoặc bước thủ công, phải nói rõ giới hạn: **demo được một kịch bản** khác với **sản phẩm đã hoạt động toàn diện trong điều kiện mục tiêu**.

## 5. Cách Scrum, Kanban và XP hỗ trợ nguyên tắc

Các phương pháp và thực hành không thay thế thước đo chủ yếu, nhưng giúp nhóm tạo và quan sát phần mềm hoạt động được thường xuyên hơn.

### 5.1. Scrum: kiểm tra Increment và mục tiêu, không chỉ số ticket

Scrum sử dụng Increment để làm rõ tiến triển dựa trên sản phẩm. Từng Increment phải **có thể sử dụng** và đáp ứng Definition of Done; các Increment mới cộng dồn với những phần trước đó, đã được kiểm tra phù hợp để hệ thống tiếp tục hoạt động như một tổng thể.

- **Product Backlog:** Thứ tự ưu tiên phục vụ Product Goal và những gì đội đang học. Các hạng mục nên đủ rõ để tạo giá trị có thể kiểm tra.
- **Sprint Planning:** Scrum Team xác định *tại sao* Sprint có giá trị và Developers chọn, lập kế hoạch cho phần có thể làm. Sprint Goal cung cấp điểm tựa để thích ứng.
- **Daily Scrum:** Developers kiểm tra tiến triển hướng tới Sprint Goal và điều chỉnh kế hoạch. Câu hỏi trọng tâm là “cần làm gì để có Increment đạt Done?”, thay vì chỉ báo cáo ai đã làm bao nhiêu giờ.
- **Sprint Review:** Scrum Team và stakeholders kiểm tra kết quả Sprint, diễn biến môi trường sử dụng và các lựa chọn tương lai; Product Backlog có thể thay đổi theo điều học được.
- **Sprint Retrospective:** Đội tìm cách tăng chất lượng và hiệu quả để tạo Increment tốt hơn ở những Sprint tiếp theo.

**Tình huống:** Sprint còn hai ngày, giao diện tính năng mới đã hoàn thành, API gần xong nhưng kiểm thử tích hợp thất bại. Nhóm không nên tự động tuyên bố “90% Done” hoặc hạ DoD để báo đạt. Nhóm cần làm rõ ảnh hưởng đến Sprint Goal, cùng gỡ lỗi, thương lượng lại phạm vi với Product Owner khi cần và công khai những gì thực sự đạt chuẩn. Một Sprint có thể không đạt dự báo ban đầu; che giấu sự thật khiến khả năng học và dự báo còn yếu hơn.

### 5.2. Kanban: giúp công việc chuyển từ “đang làm” sang “đã hoàn tất”

Một bảng Kanban có nhiều thẻ màu không bảo đảm sản phẩm chạy được. Giá trị của cách quản lý dòng công việc đến từ việc hiển thị **trạng thái thật**, kiểm soát việc đang làm (WIP), quản lý luồng chảy và cải tiến chính sách.

Ví dụ các trạng thái:

~~~text
Sẵn sàng -> Đang phát triển -> Tích hợp / kiểm thử -> Đạt DoD
                   |                    |
                   +-- Bị chặn ---------+
~~~

Đội cần thống nhất chính sách chuyển cột:

1. “Đang phát triển” có giới hạn WIP phù hợp; không kéo việc mới khi những việc đang mở cần hỗ trợ hoàn tất.
2. “Tích hợp / kiểm thử” phải thể hiện những việc còn thiếu, không được gọi Done chỉ vì mã đã merge.
3. Công việc bị chặn có lý do và thời điểm cần xử lý; nhóm chủ động hỗ trợ thay vì bỏ quên.
4. Chỉ chuyển “Đạt DoD” khi có minh chứng theo chính sách chất lượng thống nhất.
5. Các số liệu như work item age và cycle time được dùng để tìm điểm nghẽn, không để thưởng/phạt theo số ticket.

Nhờ đó, quản lý luồng công việc hỗ trợ phần mềm hoàn tất ổn định. Thẻ đã tới “Done” chỉ đáng tin nếu **định nghĩa Done thực sự gắn với khả năng hoạt động được**.

### 5.3. XP: thực hành kỹ thuật làm phần mềm hoạt động được sớm và thường xuyên

Trong Extreme Programming (XP), các thực hành như kiểm thử thường xuyên, Test-Driven Development (TDD) khi phù hợp, tích hợp liên tục, refactoring, lập trình cặp và phát hành nhỏ giúp giảm rủi ro “chỉ chạy trên máy tôi”.

Ví dụ:

- Tích hợp thường xuyên làm lộ xung đột giữa các thành phần sớm.
- Bộ kiểm thử hồi quy hỗ trợ sửa đổi mà không phá vỡ chức năng đang chạy.
- Refactoring giữ cấu trúc đủ dễ thay đổi khi yêu cầu được làm rõ.
- Lát cắt chức năng nhỏ làm giảm lượng công việc chưa thể kiểm chứng.
- Triển khai an toàn, quan sát và khả năng quay lui giúp nhận phản hồi mà vẫn kiểm soát rủi ro.

TDD hay kiểm thử tự động không tự đảm bảo sản phẩm đúng nhu cầu. Đội vẫn phải trao đổi với người dùng, kiểm tra tiêu chí chấp nhận và đánh giá kết quả trong ngữ cảnh thực tế. **Kỹ thuật tạo khả năng thích ứng; quyết định về giá trị giúp biết cần thích ứng theo hướng nào.**

## 6. Một tình huống xuyên suốt: xây dựng luồng đăng ký học

> **Các mốc và con số dưới đây chỉ là tình huống giả định để luyện phân tích, không phải dữ liệu khảo sát hoặc chuẩn áp dụng cho mọi đội.**

Một đội có sáu tuần để cải thiện khả năng đăng ký khóa học trên nền tảng học trực tuyến. Yêu cầu ban đầu gồm: xem thông tin khóa học, tạo tài khoản, chọn khóa, thanh toán và vào học. Hai phương án triển khai được đề xuất.

### Phương án A: tối ưu tiến độ của từng bộ phận

Đội chia công việc theo từng tầng: frontend, backend, database, kiểm thử và triển khai. Kết thúc tuần thứ ba, báo cáo ghi:

- Frontend: 100% màn hình.
- Backend: 80% endpoint.
- Database: 100% bảng dữ liệu.
- Kiểm thử tích hợp: 10%.
- Triển khai môi trường kiểm tra: đang chờ.

Các tỷ lệ này có thể hữu ích trong theo dõi nhiệm vụ, nhưng không trả lời được câu “học viên hiện đăng ký khóa được chưa?”. Nếu tính tỷ lệ trung bình, con số càng có nguy cơ che giấu phụ thuộc giữa các phần. Cuối tuần thứ ba, đội chưa tạo được luồng sử dụng xuyên suốt, nên bằng chứng về tiến triển sản phẩm còn yếu.

### Phương án B: giao phần mềm theo lát cắt hoạt động được

Đội chọn thứ tự phát triển theo các khả năng quan sát được:

| Giai đoạn minh họa | Lát cắt hoàn thiện | Minh chứng tiến triển | Điều có thể học |
|---|---|---|---|
| Tuần 1–2 | Xem danh sách và chi tiết khóa học trên môi trường tích hợp, đạt DoD | Luồng xem khóa dùng dữ liệu thực tế phù hợp và chạy ổn định | Người học có hiểu nội dung và điều kiện khóa học? |
| Tuần 3–4 | Chọn khóa và tạo đơn đăng ký với các tình huống lỗi quan trọng, đạt DoD | Có thể đi từ trang khóa học đến đơn đăng ký đầy đủ | Tại bước nào người học còn nhầm lẫn hoặc bỏ dở? |
| Tuần 5–6 | Thanh toán trong phạm vi hỗ trợ và truy cập nội dung đã mua, đáp ứng DoD và kiểm soát rủi ro | Luồng mua–vào học hoạt động từ đầu đến cuối | Phản hồi, lỗi và tỷ lệ hoàn tất có đáp ứng mục tiêu? |

Thứ tự thực tế có thể khác: ví dụ đội phải kiểm chứng sớm rủi ro thanh toán hoặc phân quyền trước khi xây nhiều giao diện. Bài học là **chia nhỏ sao cho giảm rủi ro và sớm có năng lực kiểm chứng**, chứ không buộc mọi hệ thống theo trình tự cố định.

Đến cuối tuần thứ tư, phương án B chưa có toàn bộ sản phẩm. Nhưng đội biết rõ những khả năng nào đã đạt DoD và có thể kiểm tra. Khi phát hiện người học nhầm lẫn với chi phí khóa học, Product Owner có thể sắp xếp lại Product Backlog trước khi xây thêm tính năng phụ.

### 6.1. Vì sao phương án B có bằng chứng tiến triển tốt hơn?

1. Các thành phần đã gặp nhau trong môi trường tích hợp, nên lỗi giao tiếp được phát hiện sớm.
2. Một phần trải nghiệm đã có thể được người khác dùng để kiểm tra thay vì chỉ xem bản thiết kế.
3. Đội nhìn rõ khả năng nào đã hoàn tất và phụ thuộc nào còn mở.
4. Phản hồi có thể dẫn đến thay đổi ưu tiên khi chi phí sửa còn thấp.
5. Tiêu chuẩn chất lượng được kiểm tra xuyên suốt, tránh tích tụ kiểm thử vào cuối dự án.

Điều này **chưa chứng minh phương án B tự động mang lại doanh thu hoặc tỷ lệ đăng ký cao hơn**. Muốn kết luận tác động, đội cần quan sát kết quả sử dụng đủ tin cậy, đối chiếu bối cảnh và xem các điều kiện ràng buộc. Phần mềm hoạt động được là thước đo tiến triển phát triển chủ yếu; **giá trị đạt được vẫn cần được kiểm chứng**.

## 7. Dùng phần mềm hoạt động để ra quyết định

Việc có Increment chạy được không chỉ phục vụ báo cáo. Nó phải giúp nhóm **kiểm tra thực tế rồi quyết định bước tiếp theo**.

~~~mermaid
flowchart LR
    A["Mục tiêu và giả thuyết"] --> B["Chọn lát cắt nhỏ"]
    B --> C["Phát triển, tích hợp và kiểm thử"]
    C --> D{"Đạt Definition of Done?"}
    D -->|Chưa| E["Làm rõ phần thiếu và hoàn thiện"]
    E --> C
    D -->|Đã đạt| F["Kiểm tra Increment chạy được"]
    F --> G["Thu phản hồi và quan sát chất lượng"]
    G --> H{"Chọn bước tiếp theo"}
    H --> I["Tiếp tục / đổi ưu tiên / thử phương án khác"]
    I --> A
~~~

Tại mỗi vòng, nhóm có thể hỏi:

- **Phần nào đang thực sự chạy được?** Bằng chứng là gì và ai đã kiểm tra?
- **Điều gì khiến chúng ta tin đó là khả năng có thể sử dụng?** Có phụ thuộc giả lập hoặc trường hợp lỗi chưa được xử lý không?
- **Điều chưa chắc chắn lớn nhất là gì?** Nhu cầu người dùng, tích hợp, hiệu năng, bảo mật hay khả năng vận hành?
- **Lát cắt tiếp theo nên giảm rủi ro nào?** Ưu tiên một tính năng mới, sửa chức năng hiện có hay xử lý điểm nghẽn chất lượng?
- **Khi nào có thể nhận được phản hồi tiếp theo?** Có cần phát hành, thử nghiệm nội bộ hoặc phối hợp với người dùng thực tế không?

### 7.1. Đừng biến “Done” thành một trò chơi đếm ticket

Nếu đánh giá thành công bằng số ticket Done, nhóm có thể chia việc thành hàng chục nhiệm vụ nhỏ, bỏ qua tích hợp hoặc hạ tiêu chuẩn để đạt số đẹp. Cần gắn trạng thái hoàn tất với DoD đáng tin, đồng thời diễn giải **ý nghĩa của các năng lực đã hoàn thành đối với mục tiêu**.

Một nhóm có thể hoàn thành ba user story nhỏ nhưng kiểm chứng được toàn bộ chức năng trọng yếu. Nhóm khác có thể đóng mười ticket cấu hình mà vẫn không có năng lực sử dụng mới. Không thể xếp hạng hai nhóm chỉ bằng số ticket hoặc điểm ước lượng.

### 7.2. Bằng chứng trước khi phán đoán

Nếu người dùng báo chức năng tìm kiếm trả về kết quả không liên quan, việc giao diện tải nhanh không đủ để gọi tiến triển thành công. Nhóm cần tái hiện hành vi, xem chất lượng kết quả, định nghĩa tác vụ tìm kiếm mà người dùng thực sự cần và quyết định có ưu tiên sửa thuật toán trước chức năng mới hay không.

Nếu Increment hoạt động đúng theo đặc tả nhưng không đạt mục tiêu trải nghiệm, kết quả này vẫn rất có giá trị: đội có bằng chứng để xem lại **giả thuyết sản phẩm**. Agile không đòi hỏi mọi Increment đều chứng minh giả thuyết ban đầu đúng; nó đòi hỏi nhóm học được từ phần mềm có thể kiểm tra.

## 8. Những ngộ nhận thường gặp

### Ngộ nhận 1: “Có nhiều dòng code hơn nghĩa là tiến triển nhiều hơn”

Số dòng code không đo khả năng sử dụng. Một thay đổi nhỏ loại bỏ lỗi quan trọng có thể đem lại giá trị lớn hơn một tính năng dài hàng nghìn dòng. Code nhiều cũng có thể làm tăng chi phí bảo trì.

**Thay thế:** Nêu rõ hành vi nào đã hoạt động, tiêu chí chất lượng đã đạt và phần mềm giúp người dùng làm được gì.

### Ngộ nhận 2: “Đã merge vào nhánh chính tức là Done”

Merge chỉ là một bước kỹ thuật. Nếu luồng đầu-cuối thất bại, di chuyển dữ liệu chưa xong hoặc thiếu kiểm tra bảo mật quan trọng, khả năng sản phẩm chưa đủ điều kiện đạt DoD.

**Thay thế:** Dùng DoD chung, tích hợp và kiểm tra hành vi theo rủi ro; hiển thị chính xác phần còn thiếu.

### Ngộ nhận 3: “Demo chạy một lần là phần mềm hoạt động được”

Demo có thể dùng dữ liệu dựng sẵn, bỏ qua tích hợp hoặc đi đường tắt thủ công. Nó chứng minh được một kịch bản trong một điều kiện nhất định, không tự chứng minh khả năng vận hành.

**Thay thế:** Công khai điều kiện demo, chạy kiểm thử phù hợp, dùng môi trường đại diện và kiểm tra cả tình huống lỗi quan trọng.

### Ngộ nhận 4: “Đã phát hành thì chắc chắn có giá trị”

Một tính năng chạy ổn có thể không giải quyết đúng vấn đề hoặc có thể ít người sử dụng. Phần mềm hoạt động được là bằng chứng tiến triển phát triển; phản hồi và kết quả thực tế giúp xác định giá trị.

**Thay thế:** Nối chức năng đã giao với mục tiêu, quan sát dữ liệu sử dụng và phản hồi định tính.

### Ngộ nhận 5: “Muốn nhanh thì bỏ bớt kiểm thử”

Bỏ kiểm thử có thể làm báo cáo trông đẹp trong ngắn hạn nhưng tăng nguy cơ lỗi, làm lại và mất khả năng thay đổi. Phần mềm lỗi liên tục không tạo nền tảng vững để tăng trưởng.

**Thay thế:** Chọn kiểm thử theo mức rủi ro, tự động hóa phần có ích và duy trì chất lượng trong DoD.

### Ngộ nhận 6: “Mọi công việc đều phải ra ngay tính năng nhìn thấy được”

Nghiên cứu khả thi, xử lý hạ tầng, cải thiện bảo mật, giảm nợ kỹ thuật và di chuyển dữ liệu có thể cần thiết để sản phẩm hoạt động an toàn. Ép mọi công việc thành màn hình mới sẽ khiến đội bỏ qua các rủi ro thật.

**Thay thế:** Liên kết công việc hỗ trợ với khả năng hoặc rủi ro cụ thể, có tiêu chí hoàn thành kiểm chứng được, và quay lại tạo Increment sử dụng được sớm nhất hợp lý.

### Ngộ nhận 7: “Càng phát hành nhiều càng chắc chắn Agile hơn”

Triển khai thường xuyên là năng lực có ích nhưng một lần triển khai không tạo giá trị nếu nó không cải thiện khả năng, chất lượng hoặc khả năng học. Nhiều thay đổi không kiểm soát có thể làm tăng sự cố.

**Thay thế:** Theo dõi cả nhịp giao hàng, chất lượng thay đổi và kết quả nhận phản hồi.

### Ngộ nhận 8: “Đã có DoD thì không cần trao đổi với người dùng”

DoD chủ yếu nói về chất lượng và trạng thái hoàn tất của Increment; nó không chứng minh toàn bộ giả định sản phẩm đúng. Đội vẫn phải kiểm tra mức hữu ích, dễ dùng và nhu cầu thực tế.

**Thay thế:** Kết hợp DoD với mục tiêu sản phẩm, tiêu chí chấp nhận và phản hồi từ người dùng hoặc stakeholders.

## 9. Các tình huống đặc biệt và giới hạn áp dụng

Nguyên tắc cần được áp dụng có phán đoán. Có những công việc không tạo ngay tính năng cho người dùng nhưng vẫn hỗ trợ tiến triển. Quan trọng là không biến chúng thành một khối hoạt động kéo dài mà thiếu bằng chứng.

### 9.1. Nghiên cứu hoặc kiến trúc chưa chắc chắn

Một nhóm chưa biết công nghệ tìm kiếm mới có đáp ứng yêu cầu tải hay không. Nhóm có thể làm **spike** trong thời gian giới hạn, tạo nguyên mẫu đo độ trễ với tập dữ liệu đại diện, ghi lại lựa chọn và rủi ro còn lại. Spike là bằng chứng học tập và giảm bất định; nó **không tự động là Increment sản phẩm đạt DoD**. Sau khi ra quyết định kỹ thuật, nhóm nên hướng tới một lát cắt tích hợp chạy được.

### 9.2. Hạ tầng, bảo mật, refactoring và di chuyển dữ liệu

Một thay đổi hạ tầng có thể không hiện lên giao diện nhưng vẫn làm phần mềm hoạt động đáng tin cậy hơn. Ví dụ: hoàn thiện cơ chế backup–restore và thực hiện một lần kiểm tra khôi phục thành công trong môi trường thích hợp là bằng chứng có ý nghĩa hơn câu “đã cập nhật tài liệu backup”.

Với di chuyển dữ liệu, tiêu chí tiến triển có thể gồm một tập dữ liệu được chuyển đổi đúng, kiểm tra toàn vẹn, ứng dụng đọc/ghi bình thường, kế hoạch quay lui được kiểm chứng và không làm mất quyền truy cập. Đừng suy diễn rằng số bản ghi đã sao chép tự động chứng minh hệ thống đã hoạt động sau chuyển đổi.

### 9.3. Hệ thống chịu ràng buộc cao

Trong tài chính, y tế, hạ tầng quan trọng hoặc xử lý dữ liệu nhạy cảm, bằng chứng “hoạt động được” bao gồm các yêu cầu về an toàn, bảo mật, truy vết và phê duyệt theo quy định áp dụng. Phát hành nhỏ có thể phải đi qua nhiều kiểm soát. Agile vẫn có thể được thực hiện bằng cách tích hợp, thử nghiệm và kiểm chứng từng phần trong môi trường thích hợp, đồng thời tôn trọng giới hạn pháp lý và rủi ro.

### 9.4. Khi chưa thể phát hành cho người dùng cuối

Một hợp đồng hoặc phụ thuộc có thể khiến sản phẩm chưa được công bố. Đội vẫn nên cố gắng tạo các Increment sử dụng được trên môi trường phù hợp, demo trung thực, kiểm thử đầu-cuối và nhận phản hồi từ người dùng đại diện khi có thể. Phải phân biệt rõ **có thể phát hành** với **đã phát hành**, và nói minh bạch những gì chưa thể kiểm chứng trong điều kiện sản xuất.

### 9.5. Không phải mọi việc chỉ được đo bằng phần mềm chạy được

Với công việc khám phá nhu cầu, thiết kế tổ chức hoặc một hoạt động thuần vận hành không tạo sản phẩm phần mềm, cần thước đo phù hợp với mục tiêu thực tế. Nguyên tắc này được phát biểu trong bối cảnh **phát triển phần mềm**; không nên áp một tiêu chí sản phẩm chạy được vào mọi loại công việc một cách máy móc.

## 10. Cách triển khai với một đội đang có “tiến độ ảo”

Một kế hoạch cải tiến nhỏ trong bốn tuần có thể giúp đội chuyển từ báo cáo hoạt động sang kiểm chứng phần mềm:

| Giai đoạn | Việc cần làm | Kết quả mong đợi |
|---|---|---|
| **Tuần 1 — Khảo sát thực trạng** | Chọn một luồng người dùng quan trọng; thử thao tác đầu-cuối trên phiên bản hiện có; xem lại cách đội dùng từ Done | Biết rõ luồng hiện chạy được đến đâu và khoảng cách giữa trạng thái ticket với trạng thái sản phẩm |
| **Tuần 2 — Làm rõ chuẩn hoàn tất** | Thống nhất tiêu chí chấp nhận và DoD phù hợp; chia một backlog item thành lát cắt có thể kiểm tra | Có mục tiêu nhỏ, ranh giới công việc rõ và chuẩn chất lượng minh bạch |
| **Tuần 3 — Hoàn tất lát cắt** | Ưu tiên tích hợp, kiểm thử và xử lý phụ thuộc; dùng bảng Kanban hoặc Sprint Backlog để hạn chế việc mở thêm khi còn tồn | Có một khả năng sản phẩm đạt DoD hoặc lý do chưa đạt được minh bạch |
| **Tuần 4 — Kiểm tra và cải tiến** | Cho stakeholders kiểm tra khả năng thực tế; quan sát phản hồi; xem độ trễ và các lỗi xuất hiện; điều chỉnh backlog hoặc quy trình | Có quyết định tiếp theo dựa trên bằng chứng thay vì chỉ có báo cáo phần trăm |

Hãy ưu tiên một phạm vi đủ nhỏ để kiểm chứng. Nếu đội vừa bắt đầu áp dụng DoD, có thể phải giảm lượng công việc dự kiến để đạt chất lượng ổn định. Đó là cách làm lộ thực tế tiến triển; không phải nguyên nhân để hạ chuẩn.

### 10.1. Mẫu báo cáo tiến triển thực dụng

~~~text
MỤC TIÊU: [Người dùng cần hoàn thành tác vụ gì?]
KHẢ NĂNG ĐÃ HOẠT ĐỘNG: [Luồng hoặc hành vi cụ thể]
MÔI TRƯỜNG / BẰNG CHỨNG: [Nơi kiểm chứng, test và kết quả]
TIÊU CHUẨN: [Đã đạt DoD? Điều kiện quan trọng nào đã kiểm tra?]
CHƯA HOÀN TẤT: [Khả năng hoặc kiểm tra nào còn thiếu?]
RỦI RO / PHỤ THUỘC: [Điểm chặn và ảnh hưởng]
PHẢN HỒI: [Người dùng, stakeholders, chất lượng]
QUYẾT ĐỊNH TIẾP THEO: [Làm tiếp / đổi ưu tiên / thử lại]
THỜI ĐIỂM KIỂM CHỨNG: [Mốc hoặc điều kiện]
~~~

Đội có thể rút gọn mẫu khi báo cáo hằng ngày; nó không phải biểu mẫu bắt buộc của Agile. Mục đích là giúp người đọc hiểu nhanh **sản phẩm đã dùng được phần nào, căn cứ nào chứng minh và còn điều gì phải quyết định**.

## 11. Bài tập thực hành

### Bài tập 1 — Đâu là bằng chứng tiến triển tốt hơn?

Một đội báo cáo bốn sự kiện:

1. Tổ chức 12 cuộc họp trong Sprint.
2. Hoàn thành 40 story point theo kế hoạch.
3. Người dùng có thể đăng ký tài khoản và xác nhận email thành công trên môi trường tích hợp, các tiêu chí chất lượng đã đạt.
4. Sau khi dùng thử, nhóm phát hiện người dùng thường bỏ dở ở bước xác nhận và quyết định đơn giản hóa hướng dẫn.

**Yêu cầu:** Xác định phát biểu nào là bằng chứng trực tiếp nhất về phần mềm hoạt động được. Phát biểu nào cho thấy nhóm đã sử dụng phần mềm đó để học và thích ứng? Vì sao không thể chỉ lấy số story point để kết luận thành công?

<details>
<summary>Gợi ý đáp án</summary>

Phát biểu 3 là bằng chứng trực tiếp nhất về khả năng phần mềm hoạt động được trong điều kiện được nêu. Phát biểu 4 cho thấy nhóm quan sát phản hồi và điều chỉnh quyết định. Phát biểu 1 chủ yếu mô tả hoạt động, phát biểu 2 mô tả cách đội ghi nhận lượng việc hoàn thành; cả hai không bảo đảm Increment đã đạt DoD hoặc tạo giá trị. Cần kiểm tra cách đo chất lượng và điều kiện môi trường trước khi khái quát.

</details>

### Bài tập 2 — Thiết kế lát cắt dọc

Backlog hiện có ba ticket: “Xây toàn bộ frontend thanh toán”, “Xây toàn bộ backend thanh toán”, “Thiết kế database giao dịch”. Nhóm dự kiến làm tuần tự trong ba Sprint.

**Yêu cầu:** Đề xuất một lát cắt đầu tiên có thể kiểm chứng xuyên suốt và tối thiểu ba tiêu chí chấp nhận. Nêu rõ các điều kiện bảo mật hoặc tính đúng đắn cần giữ.

<details>
<summary>Gợi ý đáp án</summary>

Một lát cắt khả thi là “người dùng thực hiện một giao dịch thử nghiệm trong môi trường tích hợp, hệ thống ghi nhận kết quả đúng và hiển thị trạng thái rõ ràng”. Tiêu chí có thể gồm: (1) luồng gửi yêu cầu tới cổng thanh toán thử nghiệm chạy được; (2) kết quả thành công/thất bại được xử lý và lưu nhất quán; (3) người dùng nhận thông báo đúng trạng thái; (4) không lưu thông tin nhạy cảm trái quy định, có cơ chế chống xử lý giao dịch trùng; (5) kiểm thử các lỗi quan trọng và cơ chế đối soát phù hợp. Hãy xác nhận phạm vi thử nghiệm: giao dịch trên môi trường giả lập chưa đồng nghĩa có thể nhận thanh toán thực tế.

</details>

### Bài tập 3 — Đánh giá một Sprint “đạt 100%”

Đội đóng toàn bộ ticket trong Sprint, nhưng tính năng đặt lại mật khẩu chỉ chạy với email hard-code; người dùng chưa nhận email thực và chưa có kiểm thử hết hạn liên kết. Báo cáo nói “Sprint đạt 100%”.

**Yêu cầu:** Giải thích thông tin nào của báo cáo có thể đúng, thông tin nào dễ gây hiểu nhầm và đội nên báo cáo ra sao.

<details>
<summary>Gợi ý đáp án</summary>

Có thể đúng rằng đội đã hoàn thành toàn bộ nhiệm vụ theo cách chia ticket hiện tại. Nhưng nếu các điều kiện trên nằm trong phạm vi DoD và tiêu chí chấp nhận, tính năng chưa phải một Increment hoàn chỉnh. Đội nên nêu rõ các phần đã được thực hiện, những phần giả lập, tiêu chí chưa đạt, rủi ro và kế hoạch tích hợp/kiểm thử. Nếu cách chia ticket khiến trạng thái Done gây hiểu nhầm, nên điều chỉnh chính sách và cách chia backlog item thay vì giữ số 100% như một chứng nhận sản phẩm hoàn tất.

</details>

### Bài tập 4 — Xử lý công việc nền tảng

Một nhóm mất hai tuần refactoring hệ thống phân quyền, không bổ sung màn hình mới. Người quản lý cho rằng nhóm không có tiến triển vì “không có tính năng nào”.

**Yêu cầu:** Đề xuất cách chứng minh giá trị công việc này mà không đánh đồng refactoring với tính năng sản phẩm mới.

<details>
<summary>Gợi ý đáp án</summary>

Nêu rủi ro hoặc khả năng cụ thể mà refactoring giải quyết, ví dụ loại bỏ lỗi cấp quyền trái phép, giảm trùng lặp quy tắc phân quyền, hoặc cho phép mở rộng vai trò người dùng an toàn. Đưa bằng chứng như bộ kiểm thử quyền hạn, kết quả kiểm thử hồi quy, luồng nghiệp vụ cũ vẫn chạy, quan sát lỗi đã được khắc phục và một lát cắt tích hợp tận dụng cấu trúc mới. Đây có thể là tiến triển kỹ thuật cần thiết, dù không đồng nhất với một tính năng người dùng mới.

</details>

## 12. Tự kiểm tra cách đội đang đo tiến triển

Hãy trao đổi những câu sau trong planning, review hoặc retrospective phù hợp:

1. Chúng ta có thể **mở sản phẩm và trình diễn một luồng sử dụng thật** đang hoạt động không?
2. Bằng chứng nào cho thấy chức năng đạt tiêu chí chấp nhận và DoD, ngoài việc ticket được gắn nhãn Done?
3. Những phần chưa tích hợp, chưa kiểm thử hoặc đang dùng mock có được trình bày rõ ràng không?
4. Nhóm có thường xuyên kết hợp các phần nhỏ thành Increment có thể dùng, hay chỉ tích hợp và kiểm thử sát ngày phát hành?
5. Chúng ta có đánh giá tiến triển gắn với Product Goal hoặc Sprint Goal thay vì số công việc mỗi người thực hiện không?
6. Dữ liệu về WIP, cycle time, lỗi và phản hồi có giúp thay đổi ưu tiên hoặc tháo điểm nghẽn không?
7. Khi người dùng cho biết tính năng không giải quyết vấn đề, chúng ta có thay đổi giả thuyết hoặc backlog không?
8. Các công việc nền tảng có tiêu chí kiểm chứng và liên kết rõ đến rủi ro hoặc năng lực sản phẩm không?
9. Một lãnh đạo hoặc stakeholder có thể phân biệt “đã viết xong mã”, “đạt DoD”, “có thể phát hành” và “đã phát hành” từ báo cáo của nhóm không?
10. Nếu không thể kiểm chứng tiến triển trong thời gian dài, điều gì đang ngăn cản nhóm: chia việc, kiến trúc, kiểm thử, phụ thuộc hay cách ra quyết định?

Khi trả lời, nên dùng ví dụ từ sản phẩm thật và nêu hành động kế tiếp. Mục tiêu của bộ câu hỏi là giúp xây dựng khả năng quan sát thực tế, không phải để chấm điểm con người hay so sánh đội không cùng bối cảnh.

## 13. Ghi nhớ

- **Phần mềm hoạt động được là bằng chứng tiến triển phát triển chủ yếu** vì nó kiểm tra trực tiếp xem một khả năng đã tồn tại, tích hợp và đạt chất lượng phù hợp hay chưa.
- **Hoạt động, tài liệu, story point và số ticket không thể thay thế bằng chứng sản phẩm chạy được.** Chúng hữu ích để quản lý công việc nhưng phải được diễn giải đúng giới hạn.
- **“Hoạt động được” cần có nghĩa cụ thể.** Sử dụng tiêu chí chấp nhận, Definition of Done, kiểm thử và điều kiện môi trường đủ đại diện; trình bày minh bạch những gì còn giả lập.
- **Giao tăng dần bằng các lát cắt có thể kiểm chứng** giúp giảm rủi ro tích hợp, nhận phản hồi sớm và có quyền điều chỉnh kế hoạch khi thực tế khác dự đoán.
- **Phần mềm chạy được chưa tự động là sản phẩm có giá trị.** Cần tiếp tục quan sát người dùng, chất lượng và tác động để quyết định bước tiếp theo.
- **Scrum, Kanban và XP hỗ trợ cùng một mục đích bằng những cơ chế khác nhau:** kiểm tra Increment, quản lý dòng công việc và duy trì năng lực kỹ thuật để giao phần mềm đáng tin cậy.

Khi nhận một báo cáo tiến độ, hãy thử hỏi: **“Ngay bây giờ phần mềm làm được điều gì mà trước đây chưa làm được, chúng ta kiểm chứng điều đó bằng cách nào, và kết quả ấy dẫn tới quyết định tiếp theo nào?”** Câu trả lời cụ thể, có thể kiểm tra sẽ cho thấy tiến triển rõ hơn bất kỳ con số “hoàn thành 90%” nào.

## Tài liệu tham khảo

- [Manifesto for Agile Software Development — Principles](https://agilemanifesto.org/principles.html): nguyên tắc “Working software is the primary measure of progress”.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): Increment, Definition of Done, Sprint Goal, Sprint Review và các trách nhiệm trong Scrum.
- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/): dòng công việc, giới hạn WIP và các thước đo luồng công việc.
- [Extreme Programming — Agile Alliance](https://agilealliance.org/glossary/xp/): các thực hành kỹ thuật hỗ trợ phần mềm chất lượng và phản hồi nhanh.
