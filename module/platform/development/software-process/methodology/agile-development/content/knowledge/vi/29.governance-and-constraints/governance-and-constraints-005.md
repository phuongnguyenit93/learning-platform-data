# Cộng tác với khách hàng khi hợp đồng hoặc cơ chế mua sắm còn cứng nhắc

## 1. Tình huống mở đầu: khách hàng muốn đổi, nhưng hợp đồng đã chốt

Một đơn vị đào tạo thuê nhà cung cấp phát triển nền tảng học trực tuyến theo gói thầu có **ngân sách, thời hạn và danh sách đầu ra cố định**. Hợp đồng nêu các chức năng như đăng ký khóa học, học theo bài, báo cáo tiến độ, quản trị tài khoản và kiểm thử nghiệm thu. Sau hai Sprint, khách hàng quan sát bản dùng thử và phát hiện:

- Người học mới không hiểu thông báo “đăng ký đã xử lý” có nghĩa gì.
- Một số người đăng ký xong nhưng không tìm được nút mở bài đầu tiên.
- Bộ phận vận hành muốn ưu tiên sửa trải nghiệm này trước khi xây báo cáo thống kê.
- Nhà cung cấp lo rằng đổi thứ tự hay thay nội dung sẽ bị coi là **không giao đúng hồ sơ mua sắm**.
- Người làm nghiệp vụ ở phía khách hàng có thể phản hồi hàng ngày, nhưng **không có thẩm quyền sửa hợp đồng**.

Hai phản ứng cực đoan đều có hại:

> “Agile là thích ứng nên cứ đổi theo yêu cầu người dùng, giấy tờ tính sau.”

và

> “Hợp đồng đã ký thì không được trao đổi về giải pháp mới; đến cuối dự án mới nghiệm thu.”

Phản ứng thứ nhất có thể gây **vi phạm nghĩa vụ, tranh chấp thanh toán, sai quyền phê duyệt hoặc thiếu dấu vết kiểm toán**. Phản ứng thứ hai có thể khiến sản phẩm giao đủ danh mục nhưng **không giải quyết vấn đề sử dụng thực tế**, đồng thời phát hiện sai lệch quá muộn để sửa.

Trong chương **Quản trị và ràng buộc** của module **AGILE_DEVELOPMENT**, bài học này bàn về cách duy trì **cộng tác với khách hàng, phản hồi sớm, giao tăng dần và cải tiến liên tục** khi vẫn phải tuân theo hợp đồng, hồ sơ thầu, ngân sách, các chuẩn bắt buộc và người có thẩm quyền. User story, Product Backlog, Scrum, Kanban, XP và đo lường dòng công việc là những công cụ giúp làm rõ giá trị **trong phạm vi cho phép**, không phải lý do bỏ nghĩa vụ.

**Nguyên tắc dẫn đường:** *Học sớm để quyết định tốt hơn; thực hiện mọi thay đổi trong ranh giới trách nhiệm và thẩm quyền đã được xác định.*

## 2. “Cộng tác với khách hàng hơn là thương lượng hợp đồng” thực sự có nghĩa gì?

Tuyên ngôn Agile nêu một trong bốn giá trị là:

> **Cộng tác với khách hàng hơn là thương lượng hợp đồng** (*Customer collaboration over contract negotiation*).

Giá trị này **không nói hợp đồng vô ích**. Nghĩa là khi đã có hợp đồng hoặc thỏa thuận, các bên vẫn cần trao đổi, cùng làm rõ vấn đề, xem phần mềm hoạt động và điều chỉnh hiểu biết; không dùng một văn bản ban đầu làm vật thay thế cho cộng tác.

Để đọc đúng, cần nhớ cách diễn đạt của Tuyên ngôn: **những điều ở phía sau vẫn có giá trị, nhưng các điều ở phía trước được coi trọng hơn**. Vì vậy:

1. **Hợp đồng tạo ranh giới và trách nhiệm**, đặc biệt trong mua sắm công, tổ chức lớn hoặc sản phẩm có yêu cầu pháp lý.
2. **Cộng tác giúp các bên hiểu nhu cầu thật** và hạn chế sai lệch trước khi quá muộn.
3. **Thay đổi cần được phân loại và phê duyệt đúng thẩm quyền**, không đồng nhất phản hồi nghiệp vụ với quyền sửa nghĩa vụ đã ký.
4. **Giá trị sản phẩm là mục tiêu**, nhưng giá trị không được đạt bằng cách che giấu sai phạm, hạ chất lượng hay tự ý tăng chi phí.

Ví dụ, khách hàng bảo “nút xác nhận khó hiểu” là **thông tin quan trọng**. Nhóm nên tìm hiểu hành vi, xem tiêu chí hiện có, đề xuất sửa phù hợp. Nhưng yêu cầu “thêm hệ thống chứng chỉ mới ngoài phạm vi đã ký” có thể cần thủ tục bổ sung trước khi triển khai, dù người dùng rất muốn.

### 2.1. Phân biệt ba tầng quan hệ

| Tầng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Học hỏi sản phẩm** | Người dùng cần gì, điều nào chưa đúng? | Người học hiểu sai thông báo đăng ký |
| **Thực hiện kỹ thuật** | Nhóm có thể thay thiết kế và kế hoạch nào trong phạm vi? | Sửa cách hiển thị trạng thái, bổ sung test theo chuẩn |
| **Quản trị nghĩa vụ** | Điều chỉnh có làm đổi chi phí, thời hạn, phạm vi, tiêu chí nghiệm thu hay quyền dữ liệu? | Đề nghị đổi một hạng mục hợp đồng lấy hạng mục khác |

Ba tầng có liên hệ nhưng **không cùng một quy trình ra quyết định**. Một phát hiện ở tầng sản phẩm phải được chuyển thành lựa chọn kỹ thuật hoặc đề xuất thay đổi được phê duyệt ở tầng quản trị tương ứng.

### 2.2. Agile không là cơ chế miễn trách nhiệm

Không nên nói:

- “Product Owner đã đồng ý miệng, vậy hợp đồng mặc nhiên đổi.”
- “Sprint Review đã vỗ tay nên nghiệm thu pháp lý xong.”
- “Cứ phát hành trước để chứng minh Agile, kiểm tra quyền dữ liệu sau.”
- “Story points tăng nên nhà cung cấp mặc nhiên được trả thêm.”

Quyền phê duyệt, thay đổi giá, thời hạn, thanh toán, nghiệm thu và xử lý tranh chấp **phụ thuộc điều khoản và quy tắc áp dụng**, không được suy từ một thuật ngữ Agile.

## 3. Hiểu cơ chế mua sắm và chuỗi tài liệu ràng buộc

Để cộng tác hiệu quả, trước hết phải biết **văn bản nào tạo nghĩa vụ và ai được sửa nghĩa vụ đó**. Tùy tổ chức, hợp đồng có thể liên quan nhiều tài liệu:

| Tài liệu hoặc cơ chế có thể gặp | Mục đích thường thấy | Câu hỏi cần làm rõ |
| --- | --- | --- |
| **Hồ sơ mời thầu / RFP / yêu cầu mua sắm** | Mô tả nhu cầu và điều kiện lựa chọn nhà cung cấp | Điều gì là bắt buộc, điều gì là mong muốn? |
| **Hồ sơ chào thầu / đề xuất nhà cung cấp** | Mô tả giải pháp, phạm vi và cam kết | Phần nào được dẫn chiếu thành nghĩa vụ? |
| **Hợp đồng chính / Master Agreement** | Quan hệ pháp lý và điều khoản chung | Thứ tự ưu tiên tài liệu, thay đổi, trách nhiệm? |
| **Statement of Work (SOW) / phụ lục công việc** | Phạm vi, đầu ra, mốc, trách nhiệm | Đầu ra bắt buộc được mô tả ở cấp nào? |
| **Tiêu chí nghiệm thu / acceptance plan** | Bằng chứng cần để chấp nhận đầu ra | Ai ký, mốc nào, cách xử lý sai lệch? |
| **Điều kiện thanh toán / mốc nghiệm thu** | Quan hệ giữa giao hàng, chứng từ và chi trả | Sprint demo có liên quan hay không? |
| **SLA / cam kết dịch vụ** | Mức phục vụ và cách xử lý vi phạm nếu có | Chỉ áp dụng sau vận hành hay từ giai đoạn nào? |
| **Yêu cầu bảo mật, dữ liệu, accessibility** | Kiểm soát rủi ro và nghĩa vụ chuyên ngành | Tiêu chuẩn nào áp dụng, ai kiểm chứng? |
| **Quy trình change control** | Đề xuất, đánh giá và phê duyệt điều chỉnh | Thay đổi nào cần văn bản, ai có quyền? |
| **Chính sách mua sắm/kiểm toán nội bộ** | Kiểm soát chi và khả năng truy vết | Hồ sơ, phê duyệt, lưu trữ cần ra sao? |

**Không phải hợp đồng nào cũng có đủ các tài liệu này**, và thứ tự ưu tiên pháp lý giữa chúng không giống nhau ở mọi nơi. Nhóm cần hỏi người có thẩm quyền về **bộ tài liệu thực sự đang áp dụng**, thay vì tự giả định.

### 3.1. Ràng buộc không chỉ là “phạm vi đã ký”

Một dự án có thể cố định:

- **Ngân sách hoặc giá hợp đồng**.
- **Thời hạn/mốc giao**.
- **Danh mục chức năng hoặc đầu ra**.
- **Tiêu chuẩn chất lượng và điều kiện nghiệm thu**.
- **Loại công nghệ, nơi lưu trữ dữ liệu hoặc khả năng tích hợp**.
- **Quy trình bảo mật, phê duyệt, lưu hồ sơ và kiểm toán**.
- **Nhân sự/chuyên môn, quyền truy cập hoặc nhà thầu phụ**.

Không có phép đánh đổi phổ quát rằng “đã cố định thời gian và giá thì tự do đổi phạm vi”. Nếu **phạm vi cũng ràng buộc**, nhóm không được đơn phương bỏ một hạng mục dù nghĩ hạng mục khác tạo giá trị hơn.

### 3.2. Trách nhiệm xác định ranh giới

Developers và Product Owner có thể nhận diện sự không rõ ràng, nhưng **không nên tự đưa ra kết luận pháp lý** như “điều khoản này chắc không có hiệu lực” hoặc “khách hàng đã dùng bản demo nên xem là nghiệm thu”.

Khi hợp đồng mơ hồ hoặc ảnh hưởng lớn, cần làm việc với **người phụ trách hợp đồng, mua sắm, pháp chế và chủ thể được ủy quyền** theo tổ chức. Bài học cung cấp phương pháp phối hợp Agile, **không thay thế việc diễn giải hợp đồng của người có thẩm quyền**.

## 4. Lập bản đồ người liên quan và quyền quyết định trước khi nhận thay đổi

Một điểm gây tranh chấp phổ biến là **người góp ý sản phẩm không phải người có quyền sửa hợp đồng**.

### 4.1. Những vai trò thường gặp

| Vai trò | Điều họ thường biết hoặc chịu trách nhiệm | Điều không nên mặc định |
| --- | --- | --- |
| **Người dùng cuối** | Trải nghiệm thực và nhu cầu chưa được đáp ứng | Có quyền thay đổi nghĩa vụ hợp đồng |
| **Đại diện nghiệp vụ khách hàng** | Quy trình vận hành, ưu tiên và tiêu chí sử dụng | Có quyền ký bổ sung ngân sách |
| **Product Owner** | Tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog nếu dùng Scrum | Mặc nhiên có quyền sửa SOW hoặc cam kết pháp lý |
| **Developers / nhóm thực hiện** | Thiết kế, ước lượng rủi ro, tạo Increment đạt DoD | Được tự ý hạ tiêu chí nghiệm thu theo hợp đồng |
| **Scrum Master** | Hỗ trợ áp dụng Scrum, minh bạch và cải tiến hiệu quả | Là người ký nghiệm thu hoặc xử lý pháp lý mặc định |
| **Bên mua / procurement** | Quy trình mua sắm, hồ sơ và quyền phê duyệt áp dụng | Luôn hiểu chi tiết mọi tương tác người dùng |
| **Contract manager / pháp chế** | Nghĩa vụ, thủ tục và giới hạn thay đổi | Có thể tự quyết định giá trị sản phẩm thay PO |
| **Sponsor / người duyệt ngân sách** | Mục tiêu đầu tư và quyền tài chính theo phân cấp | Có thể bỏ qua kiểm soát chuyên ngành |
| **Security, privacy, vận hành** | Điều kiện an toàn, dữ liệu, môi trường và triển khai | Mọi góp ý đều là “thay đổi phạm vi” phải trì hoãn |
| **Nhà cung cấp / vendor lead** | Khả năng giao hàng, chi phí, phụ thuộc, hợp đồng phía bán | Được quyết định thay chủ thể phê duyệt của khách hàng |

Một người có thể đảm nhiệm nhiều vai trò, nhưng **vai trò Agile và quyền ký kết pháp lý là hai khái niệm riêng**.

### 4.2. Ma trận thẩm quyền cho một thay đổi

| Loại quyết định | Ai nên chuẩn bị thông tin? | Ai cần chấp thuận theo quyền thực tế? |
| --- | --- | --- |
| Làm rõ ví dụ acceptance criteria trong phạm vi đã ký | PO/đại diện nghiệp vụ + Developers | Người được giao quyền làm rõ nội dung; kiểm tra nếu ảnh hưởng nghiệm thu |
| Thay đổi thứ tự PBI trong kế hoạch thực hiện | PO và nhóm, xem phụ thuộc | Quyền Product Backlog của PO, không làm mất mốc/đầu ra ràng buộc |
| Chọn cấu trúc mã hoặc framework kỹ thuật trong chuẩn cho phép | Developers + chuyên gia liên quan | Trách nhiệm kỹ thuật và phê duyệt kiến trúc nếu có |
| Bỏ hoặc thêm đầu ra đã ký | PO, bên mua, nhà cung cấp đánh giá tác động | Người có thẩm quyền thay đổi hợp đồng và quy trình mua sắm |
| Dời hạn, đổi giá, thay mốc thanh toán | Contract manager, PM/procurement, nhà cung cấp | Chủ thể phê duyệt ngân sách/hợp đồng theo quy định |
| Thay điều kiện bảo mật hoặc xử lý dữ liệu | Security/privacy, legal, nhóm kỹ thuật | Cơ quan/người có quyền theo chính sách và pháp luật áp dụng |
| Ký nghiệm thu/mở thanh toán | Nhóm cung cấp bằng chứng | Người được ủy quyền ký và quy trình nghiệm thu hợp đồng |

Đây là **mẫu tư duy**, không phải ma trận phân quyền có hiệu lực cho tổ chức nào. Khi dùng thực tế, phải ghi **chức danh/người được ủy quyền, căn cứ và kênh phê duyệt**.

### 4.3. Vì sao một cuộc họp có PO vẫn có thể chưa đủ?

Product Owner có thể được giao trách nhiệm tối đa hóa giá trị nhưng **chưa được phép chi thêm hoặc thay đổi phạm vi của hợp đồng mua sắm**. Nhóm nên tìm cách để PO cộng tác thường xuyên và các quyết định vượt quyền được đưa tới bên mua/sponsor đúng thời điểm.

**Không dùng việc PO “đã đồng ý” để che thiếu phê duyệt bắt buộc.** Ngược lại, không bắt PO đợi hội đồng cho những điều chỉnh hoàn toàn nằm trong quyền đã được trao.

## 5. Phân loại phản hồi: làm rõ, điều chỉnh cách thực hiện hay thay đổi hợp đồng?

Để phản hồi không biến thành tranh cãi, hãy phân loại trước khi triển khai.

| Loại phản hồi | Dấu hiệu | Hành động có thể phù hợp |
| --- | --- | --- |
| **Phát hiện lỗi so với nghĩa vụ hiện có** | Hành vi sai so với tiêu chí đã ký/được chấp nhận | Sửa để đáp ứng nghĩa vụ và DoD theo trách nhiệm áp dụng |
| **Làm rõ yêu cầu còn mơ hồ** | Các bên hiểu khác nhau về thuật ngữ/điều kiện | Ghi ví dụ, xác nhận cách diễn giải với người có quyền |
| **Cải tiến thiết kế trong phạm vi** | Thay cách trình bày mà không làm sai chức năng/chuẩn/ràng buộc | PO và Developers cân nhắc, lưu quyết định phù hợp |
| **Đổi thứ tự triển khai** | Hoãn một PBI chưa cần ngay nhưng vẫn bảo đảm nghĩa vụ cuối | Cập nhật kế hoạch và truyền thông mốc/phụ thuộc |
| **Thay thế một đầu ra đã cam kết** | Bỏ báo cáo A để làm dashboard B | Đánh giá thay đổi hợp đồng nếu điều khoản không cho phép hoán đổi |
| **Bổ sung chức năng** | Thêm chứng chỉ, tích hợp mới không có trong phạm vi | Đề xuất, phân tích tác động, xin phê duyệt trước |
| **Đổi mốc/giá/điều kiện nghiệm thu** | Dời thời hạn, đổi tiêu chí ký nhận hoặc thanh toán | Change control và quyền hợp đồng áp dụng |
| **Yêu cầu an toàn bắt buộc** | Phát hiện lỗ hổng quyền dữ liệu, thiếu kiểm soát | Bảo vệ người dùng, thực hiện kiểm soát bắt buộc; đánh giá tác động hợp đồng nếu cần |

**Tên gọi không quyết định bản chất pháp lý.** Một nhóm có thể đặt nhãn “refinement” cho một yêu cầu tăng gấp đôi phạm vi; điều đó không biến nó thành việc trong hợp đồng. Ngược lại, sửa bug để đáp ứng tiêu chí đã ký không mặc nhiên là change request tính phí.

### 5.1. Câu hỏi phân loại nhanh

1. Hành vi mới có **thay đổi đầu ra đã cam kết** không?
2. Có tăng hoặc giảm yêu cầu chất lượng, bảo mật, quyền dữ liệu không?
3. Có đổi **mốc, giá, điều kiện thanh toán, trách nhiệm** không?
4. Có ảnh hưởng tiêu chí nghiệm thu hoặc tài liệu đã được dẫn chiếu không?
5. Có thể điều chỉnh **cách thực hiện/thứ tự** mà vẫn đáp ứng mọi nghĩa vụ không?
6. Người đang phản hồi có quyền **làm rõ**, **ưu tiên** hay **sửa hợp đồng**?
7. Hợp đồng có quy định ngưỡng, thủ tục hoặc quyền phê duyệt thay đổi nào?

Nếu chưa biết, nên ghi **“đang cần xác nhận phạm vi/thẩm quyền”** thay vì tự kết luận.

### 5.2. Không để tranh luận phạm vi chặn việc học hỏi

Nhóm vẫn có thể **lắng nghe, phân tích và làm thử prototype không xâm phạm ràng buộc** để hiểu yêu cầu, nếu hoạt động được cho phép và có ngân sách/năng lực phù hợp. Nhưng **triển khai sản xuất, phát hành hoặc nhận nghĩa vụ mới** cần tuân thủ quyết định và giấy tờ cần thiết.

## 6. Giữ Product Goal là la bàn, không biến nó thành giấy phép thay hợp đồng

Một Product Goal có thể là:

> “Người học mới có thể tự đăng ký khóa miễn phí và bắt đầu học một cách đáng tin cậy.”

Mục tiêu này hỗ trợ sắp thứ tự ưu tiên các PBI và lựa chọn lát cắt có giá trị. Trong khi đó, hợp đồng có thể còn quy định một **bộ chức năng quản trị, báo cáo, tích hợp và các tiêu chí nghiệm thu khác**.

**Product Goal giúp định hướng quyết định sản phẩm; nó không tự hủy những đầu ra bắt buộc đã ký.**

### 6.1. Phân biệt outcome với deliverable

| Mục tiêu kết quả | Đầu ra hoặc khả năng có thể hỗ trợ | Bằng chứng |
| --- | --- | --- |
| Người học biết mình đã đăng ký thành công | Trạng thái xác nhận rõ ràng, API nhất quán | Usability test + acceptance/integration tests |
| Người học mở bài đầu không bị cản | Quyền học hợp lệ, đường dẫn tới bài đầu | Hành trình dùng thật, test phân quyền |
| Quản trị viên báo cáo đúng tiến độ | Giao diện báo cáo, dữ liệu tiến độ chính xác | Acceptance tests + đối soát dữ liệu |
| Dữ liệu người học được bảo vệ | Xác thực, phân quyền, logging phù hợp | Kiểm thử và đánh giá an toàn áp dụng |

Một deliverable có thể cần thiết để đạt outcome; nhiều deliverable trong hợp đồng có thể không được thay tùy ý chỉ vì outcome ban đầu đã đạt.

### 6.2. Mẫu trao đổi ưu tiên trong phạm vi

> “Từ thử nghiệm với người học, xác nhận đăng ký chưa đủ rõ, nên rủi ro người học không mở bài đầu còn cao. Trong phạm vi chức năng đăng ký đã ký, chúng ta đề xuất làm rõ trạng thái thành công/lỗi và ưu tiên kiểm chứng luồng này ở Sprint tiếp theo. Báo cáo quản trị vẫn nằm trong danh mục bắt buộc; chúng tôi sẽ kiểm tra mốc cuối và chỉ đề xuất thay đổi văn bản nếu các mốc/đầu ra không thể giữ.”

Thông điệp giữ cả **học hỏi về giá trị** lẫn **trách nhiệm với cam kết**.

## 7. User story và backlog giúp tạo đối thoại trong giới hạn

User story hữu ích vì nó khơi gợi **đối thoại và ví dụ chấp nhận**, không phải vì nó có quyền thay thế SOW.

### 7.1. Từ yêu cầu hợp đồng đến user story

Giả sử hợp đồng nói: “Hệ thống phải cho phép người học đăng ký khóa miễn phí và xem kết quả đăng ký.”

Một user story:

> “Là người học đã đăng nhập, tôi muốn đăng ký khóa miễn phí và nhận xác nhận chính xác, để có thể bắt đầu học mà không phải đoán trạng thái.”

Trong refinement, PO, Developers và đại diện nghiệp vụ đặt câu hỏi:

- Nếu gửi hai yêu cầu gần đồng thời, có được tạo hai đăng ký đang có hiệu lực?
- Nếu client timeout nhưng server đã ghi, phản hồi và truy vấn trạng thái phải thế nào?
- Nếu tài khoản không có quyền, dữ liệu của người khác có được bảo vệ?
- Người học phải thấy đường dẫn tới bài đầu ở đâu?

Những câu hỏi này có thể **làm rõ và hoàn thiện nghĩa vụ đang có** hoặc có thể **tạo đề xuất bổ sung**. Trước khi phân loại, đừng mặc định mọi ví dụ là “scope creep” hay mọi ví dụ đều “đã bao gồm”.

### 7.2. Lát cắt dọc để có phản hồi sớm

Thay vì giao “toàn bộ UI”, rồi “toàn bộ backend”, rồi “toàn bộ database”, chia những lát cắt có hành vi sử dụng được:

1. Đăng ký khóa miễn phí theo tài khoản hợp lệ, lưu chính xác và hiển thị trạng thái.
2. Xem danh sách khóa đã đăng ký theo quyền phù hợp.
3. Mở bài đầu theo trạng thái đăng ký.
4. Các báo cáo hoặc kênh thông báo bổ sung theo phạm vi và thứ tự được chấp thuận.

Mỗi phần **được gọi Done** phải đáp ứng DoD. Các lát cắt phục vụ kiểm tra, tích hợp và nhận phản hồi sớm; **không mặc nhiên chia lại điều kiện nghiệm thu hoặc nghĩa vụ thanh toán của hợp đồng**.

### 7.3. Product Backlog có thể thay đổi mà baseline hợp đồng vẫn được bảo vệ

Product Backlog trong Scrum là danh sách có thứ tự, liên tục được làm rõ về những gì cần để cải thiện sản phẩm. Thỏa thuận pháp lý có thể yêu cầu **theo dõi một baseline phạm vi** và chứng minh đầu ra.

Một cách tổ chức thông tin có thể là:

| Mã nghĩa vụ | PBI liên quan | Hành vi cần kiểm chứng | Trạng thái | Nhận xét |
| --- | --- | --- | --- | --- |
| C-REG-01 | STORY-12, STORY-14 | Đăng ký hợp lệ, xác nhận đúng | Đang thực hiện | Chưa đạt kiểm thử timeout |
| C-LEARN-02 | STORY-17 | Mở bài đầu theo quyền học | Chưa bắt đầu | Phụ thuộc hợp đồng API |
| C-REPORT-03 | STORY-22, STORY-26 | Báo cáo tiến độ theo tiêu chí hợp đồng | Đã làm rõ | Mốc nghiệm thu sau |

Mã ở bảng chỉ là **minh họa**, không phải cấu trúc chuẩn Scrum. Không cần biến mỗi PBI thành một điều khoản; điều quan trọng là **có thể truy vết nghĩa vụ mà vẫn duy trì backlog theo giá trị**.

## 8. Những việc có thể thích ứng mà chưa cần sửa điều khoản, nếu được phép

Hợp đồng có thể cứng về một số yếu tố nhưng vẫn cho nhóm khoảng linh hoạt.

| Phạm vi linh hoạt có thể có | Ví dụ | Ranh giới cần kiểm tra |
| --- | --- | --- |
| **Thứ tự thực hiện** | Ưu tiên đăng ký trước báo cáo | Mốc giao và phụ thuộc bắt buộc |
| **Thiết kế giao diện** | Đổi câu chữ xác nhận để người học hiểu hơn | Yêu cầu accessibility, brand, thiết kế đã phê duyệt |
| **Cách triển khai kỹ thuật** | Dùng contract tests và CI để tích hợp sớm | Quy định công nghệ, bảo mật, kiến trúc |
| **Mức chi tiết backlog** | Chia một hạng mục lớn thành các lát cắt dọc | Vẫn truy vết được đầu ra đã ký |
| **Nhịp demo/thu phản hồi** | Xem Increment mỗi Sprint | Quy tắc bảo mật, truy cập và lịch nghiệm thu |
| **Chất lượng kỹ thuật** | Thêm kiểm thử rủi ro, refactor có kiểm chứng | DoD, ngân sách và thủ tục liên quan |
| **Trao đổi nhu cầu** | Phỏng vấn người dùng, xem prototype | Quyền dữ liệu, phê duyệt nghiên cứu nếu áp dụng |

**Tất cả ví dụ đều cần đọc trong điều khoản cụ thể.** Một hợp đồng quy định cứng công nghệ, mẫu giao diện hoặc quy trình phê duyệt có thể giới hạn những việc vốn dễ linh hoạt ở dự án khác.

### 8.1. Không coi “thay đổi nhỏ” là miễn giấy tờ

Một thay đổi vài dòng code có thể làm đổi ý nghĩa nghiệp vụ hoặc điều kiện an toàn, trong khi refactor lớn có thể không đổi đầu ra hợp đồng. **Phân loại theo tác động đến nghĩa vụ**, không chỉ theo story points, số dòng mã hay cảm giác “đơn giản”.

### 8.2. Tách nghiên cứu khỏi phát hành

Một prototype cho khách hàng xem có thể là cách học nhanh, nhưng cần ghi rõ **đây là nguyên mẫu, chưa phải Increment Done hoặc đầu ra đã được nghiệm thu** nếu chưa thỏa điều kiện tương ứng.

## 9. Khi mọi biến thời gian, giá và phạm vi đều cố định

Có dự án được mua theo kiểu “giá cố định, ngày cố định, danh mục đầu ra cố định”. Agile **không thể biến một ràng buộc không khả thi thành khả thi bằng thuật ngữ**.

Nếu năng lực thực tế và phát hiện mới khiến kế hoạch có rủi ro, cần đưa **bằng chứng và phương án** tới người có quyền thay vì âm thầm:

- Bỏ kiểm thử bắt buộc.
- Đánh dấu PBI chưa đạt DoD là Done.
- Giao ít hơn mà không thông báo.
- Dùng nhân sự hoặc chi phí ngoài quyền đã duyệt.
- Thay điều kiện nghiệm thu sau khi phát hiện không đạt.

### 9.1. Ba nhóm phương án cần phân biệt

**Nhóm A — Cải thiện cách giao trong baseline:** Chia PBI nhỏ, giảm WIP, tích hợp thường xuyên, ưu tiên những rủi ro phụ thuộc, bổ sung CI, làm rõ sớm. Không thay nghĩa vụ nếu có thể thực hiện trong phạm vi được phép.

**Nhóm B — Điều chỉnh kế hoạch có phê duyệt trong phạm vi hiện có:** Đổi thứ tự, sắp lại mốc trung gian, huy động năng lực được phép hoặc thống nhất cách giao bằng chứng khác nếu hợp đồng và thẩm quyền cho phép.

**Nhóm C — Đề xuất thay đổi nghĩa vụ:** Khi không thể đáp ứng toàn bộ cùng các ràng buộc, chuẩn bị change request/biện pháp theo hợp đồng về phạm vi, thời gian, giá hoặc nghiệm thu. **Chỉ có hiệu lực sau khi được phê duyệt theo thủ tục tương ứng**.

Không có quy tắc mặc định “cắt scope để giữ deadline”. Nếu scope là nghĩa vụ cứng và không có quyền cắt, cần giải quyết **bằng quản trị hợp đồng**, không bằng backlog âm thầm.

### 9.2. Lập dự báo có điều kiện, không báo chắc chắn giả

Nếu còn 18 PBI và throughput trung bình theo các tuần gần đây là 4–5 item/tuần, phép chia chỉ là **tham khảo thô**, không tự chứng minh giao đúng hạn vì item khác kích thước, có phụ thuộc, nghiệm thu và rủi ro.

Khi có dữ liệu đủ đại diện, nhóm có thể dùng **phân bố throughput/cycle time** để dự báo nhiều kịch bản. Với mẫu nhỏ hoặc điều kiện không ổn định, hãy trình bày **giả định, khoảng bất định và rào cản cần tháo gỡ** thay vì bịa một xác suất chính xác.

### 9.3. Đàm phán minh bạch không đối lập với Agile

Một cuộc đàm phán chính thức để xử lý ràng buộc không còn khả thi có thể là **bước cần thiết để bảo vệ quan hệ hợp tác**. Giá trị Agile khuyến khích không để toàn bộ quan hệ chỉ xoay quanh điều khoản, **không cấm thương lượng khi cần**.

## 10. Change control: biến phản hồi thành đề xuất rõ và có thể quyết định

Khi phản hồi ảnh hưởng nghĩa vụ hợp đồng, nhóm cần một **đường thay đổi rõ ràng**. Một change request tốt giúp người quyết định hiểu giá trị, chi phí, rủi ro và các lựa chọn, thay vì chỉ hỏi “có được sửa hay không?”.

~~~mermaid
flowchart TD
    A["Nhận phản hồi hoặc phát hiện mới"] --> B["Ghi hành vi, tác động và bằng chứng"]
    B --> C{"Có khả năng đổi nghĩa vụ hợp đồng?"}
    C -->|"Chưa rõ"| D["Hỏi contract/procurement/legal đúng quyền"]
    D --> C
    C -->|"Không; trong quyền hiện tại"| E["PO/Developers xử lý qua backlog, kiểm chứng"]
    C -->|"Có"| F["Lập đề xuất thay đổi và các phương án"]
    F --> G["Phân tích scope, giá, mốc, chất lượng, rủi ro"]
    G --> H["Trình chủ thể có quyền phê duyệt"]
    H --> I{"Kết quả theo quy trình?"}
    I -->|"Được duyệt"| J["Cập nhật baseline/tài liệu, backlog và kế hoạch"]
    I -->|"Không duyệt"| K["Giữ nghĩa vụ hiện hành, lựa chọn phương án hợp lệ"]
    I -->|"Cần làm rõ"| F
    E --> L["Kiểm tra DoD, nghiệm thu và phản hồi"]
    J --> L
    K --> L
~~~

Sơ đồ là **mô hình nghiệp vụ tham khảo**, không quy định hình thức văn bản, thời hạn trả lời hay hiệu lực pháp lý của bất cứ nơi nào.

### 10.1. Một change request nên có gì?

| Trường | Nội dung hữu ích |
| --- | --- |
| **Mã và ngày** | Tham chiếu thay đổi và lịch sử |
| **Nguồn yêu cầu** | Ai nêu, dựa trên phản hồi/bằng chứng gì |
| **Vấn đề người dùng** | Hành vi hiện tại gây ảnh hưởng gì |
| **Baseline liên quan** | Điều khoản/hạng mục/tiêu chí đang bị tác động |
| **Thay đổi đề xuất** | Thêm, sửa, thay thế hay bỏ điều gì |
| **Các lựa chọn** | Giữ nguyên, thay cách thực hiện, hoặc sửa phạm vi |
| **Phân tích tác động** | Giá, ngày, phụ thuộc, test, vận hành, bảo mật, chất lượng |
| **Giả định và rủi ro** | Điều gì chưa biết, điều kiện hiệu lực |
| **Người có quyền duyệt** | Thẩm quyền theo hợp đồng/quy trình |
| **Quyết định và ngày hiệu lực** | Chấp thuận, từ chối hoặc yêu cầu bổ sung |
| **Cập nhật theo sau** | Baseline, backlog, kế hoạch, hợp đồng, test, nghiệm thu |

Không nên biến change request thành **bộ hồ sơ quá nặng cho mọi lỗi chính tả**. Xác định ngưỡng theo quyền và tài liệu thật. Nhưng khi thay nghĩa vụ quan trọng, quy trình nhẹ quá mức có thể gây tranh chấp lớn.

### 10.2. Không triển khai trước rồi xin ký sau nếu chưa được phép

Nếu nhà cung cấp làm một chức năng mới theo yêu cầu miệng và hy vọng nhận thanh toán về sau, cả hai bên có rủi ro: bên mua có thể không có quyền chi, còn nhà cung cấp không có căn cứ được trả.

**Nguyên tắc an toàn:** Trước khi cam kết chi phí/phạm vi hoặc triển khai thay đổi có tác động hợp đồng, xác minh và đi đúng thủ tục phê duyệt. Trường hợp ứng cứu khẩn cấp cần tuân theo **cơ chế khẩn đã được ủy quyền**, không tự tạo ngoại lệ.

## 11. Tận dụng phản hồi sớm mà không biến Sprint Review thành ký nghiệm thu

**Sprint Review** trong Scrum là dịp Scrum Team và stakeholders **kiểm tra kết quả Sprint và trao đổi điều chỉnh tiếp theo**. Đây không phải chỉ là buổi trình diễn; mục đích là cộng tác và thích ứng Product Backlog.

**Nghiệm thu theo hợp đồng** có thể đòi hồ sơ, bài kiểm thử, người ký, mẫu biên bản hoặc thủ tục khác. **Không mặc định Sprint Review = nghiệm thu pháp lý**, dù cả hai có thể dùng chung một phần bằng chứng.

### 11.1. Hai vòng phản hồi chạy song song

~~~mermaid
flowchart LR
    A["Nhu cầu và Product Backlog"] --> B["Sprint / lát cắt Done"]
    B --> C["Review người dùng và stakeholder"]
    C --> D["Học hỏi, làm rõ, ưu tiên"]
    D --> A
    B --> E["Bằng chứng theo baseline hợp đồng"]
    E --> F["Kiểm tra điều kiện nghiệm thu"]
    F --> G["Quyết định của người có thẩm quyền"]
    G --> H["Lưu hồ sơ/điều chỉnh theo quy trình"]
    H -.-> A
~~~

Vòng trái **học về giá trị**, vòng phải **xác minh nghĩa vụ và quyền chấp thuận**. Chúng nên chia sẻ thông tin để tránh làm lại, nhưng không bị đánh đồng.

### 11.2. Thực hiện Review có ích khi ràng buộc cứng

Trước buổi Review:

- Xác định mục tiêu cần học, người cần phản hồi và quyền truy cập.
- Chỉ rõ Increment nào **đã đạt DoD**, điều gì là prototype hoặc chưa Done.
- Chuẩn bị ví dụ nghiệp vụ, trường hợp lỗi và dữ liệu thử an toàn.
- Nêu những mục hợp đồng/tiêu chí có liên quan khi cần.

Trong Review:

- Cho khách hàng thử hành trình thực: đăng ký, xác nhận, mở bài.
- Ghi quan sát và câu hỏi, không vội biến mọi góp ý thành cam kết.
- Phân loại **lỗi, làm rõ, cải tiến trong phạm vi và thay đổi cần duyệt**.
- Thảo luận giá trị và bước tiếp theo với Product Owner.

Sau Review:

- Ghi quyết định và việc cần xác minh.
- Liên kết PBI hoặc đề xuất change request phù hợp.
- Không ghi “đã nghiệm thu” nếu chưa qua thủ tục nghiệm thu áp dụng.

### 11.3. Demo liên tục giảm rủi ro nghiệm thu cuối kỳ

Nếu hợp đồng chỉ có mốc nghiệm thu chính thức cuối giai đoạn, các buổi demo và kiểm tra trung gian vẫn có thể phát hiện **hiểu sai quy tắc nghiệp vụ** sớm. Tuy vậy, cần thống nhất **ý nghĩa pháp lý của nhận xét, xác nhận trung gian và phạm vi thử** trước khi sử dụng chúng làm căn cứ thanh toán.

## 12. Phân biệt acceptance criteria, Definition of Done và nghiệm thu hợp đồng

Ba lớp kiểm tra có thể giao nhau nhưng **không thay thế nhau**.

| Lớp | Câu hỏi | Vai trò thực tế |
| --- | --- | --- |
| **Acceptance criteria của PBI** | Hành vi cụ thể của hạng mục có đáp ứng mong đợi đã làm rõ? | Giúp đối thoại, kiểm thử nghiệp vụ |
| **Definition of Done (DoD)** | Increment có đáp ứng các thước đo chất lượng cần thiết của sản phẩm? | Commitment chính thức của Increment trong Scrum |
| **Contractual acceptance** | Đầu ra đã đạt điều khoản/tiêu chí và thủ tục nghiệm thu hợp đồng? | Căn cứ chấp nhận nghĩa vụ theo quyền và tài liệu áp dụng |

Điều kiện **release** còn có thể khác: một Increment Done chưa chắc đã được triển khai production nếu còn yêu cầu phát hành, phê duyệt hoặc lịch vận hành.

### 12.1. Bốn tình trạng dễ nhầm

| Tình trạng | Có thể nói gì? | Không nên tuyên bố |
| --- | --- | --- |
| Story đáp ứng một số acceptance tests, chưa đạt DoD | Đã có hành vi được kiểm chứng một phần | Increment Done |
| Increment đạt DoD, chưa qua nghiệm thu hợp đồng | Có phần sản phẩm Done theo Scrum | Hợp đồng đã được nghiệm thu |
| Đã có biên bản nhận đầu ra nhưng có vấn đề chất lượng thực tế | Có quyết định theo hồ sơ nghiệm thu; cần xem nghĩa vụ bảo hành/xử lý | Phần mềm không thể còn lỗi |
| Increment Done và được cho phép phát hành, nhưng chưa đưa tới người dùng | Sẵn sàng theo điều kiện đã kiểm tra | Người dùng đã nhận giá trị hoặc outcome đã cải thiện |

### 12.2. Đừng hạ DoD để đạt mốc

Trong Sprint, **chất lượng không được giảm** theo Scrum. Nếu PBI chưa đạt DoD, nó không là phần Increment Done. Nếu hợp đồng có yêu cầu an toàn hay chất lượng cao hơn DoD hiện tại, nhóm phải đáp ứng **các yêu cầu áp dụng**, không lấy DoD thấp hơn làm lý do miễn nghĩa vụ.

Ngược lại, việc Product Owner hoặc khách hàng nói “chấp nhận rủi ro này” không tự cho phép thay tiêu chuẩn tổ chức, quy định dữ liệu hoặc điều khoản mà họ không có quyền sửa.

### 12.3. Ví dụ acceptance criteria của đăng ký

~~~gherkin
Tính năng: Đăng ký khóa học miễn phí

  Tình huống: Đăng ký và xác nhận đúng
    Cho trước người học đã đăng nhập
    Và khóa "Java nhập môn" đang cho phép đăng ký miễn phí
    Và người học chưa có đăng ký đang có hiệu lực
    Khi người học gửi yêu cầu đăng ký khóa
    Thì hệ thống lưu đăng ký hợp lệ
    Và người học thấy trạng thái đã đăng ký rõ ràng

  Tình huống: Không tạo đăng ký trùng do yêu cầu đồng thời
    Cho trước người học đã đăng nhập
    Và người học chưa có đăng ký đang có hiệu lực
    Khi hai yêu cầu đăng ký cùng khóa được gửi gần đồng thời
    Thì hệ thống không tạo hai đăng ký đang có hiệu lực trùng nhau
    Và phản hồi tuân theo hợp đồng API đã thống nhất

  Tình huống: Chưa chắc trạng thái lưu sau timeout
    Cho trước dịch vụ chưa thể xác nhận kết quả lưu
    Khi người học đăng ký khóa
    Thì giao diện không thông báo chắc chắn đã đăng ký thành công
    Và người học có cách kiểm tra lại trạng thái phù hợp

  Tình huống: Người học không truy cập được dữ liệu của người khác
    Cho trước tài khoản A đã đăng nhập
    Và một đăng ký thuộc tài khoản B
    Khi A cố truy cập dữ liệu đăng ký của B
    Thì hệ thống từ chối theo quy tắc phân quyền
    Và không tiết lộ thông tin riêng của B
~~~

Gherkin là **mô tả hành vi**, không tự là bộ kiểm thử đã chạy; cần môi trường, dữ liệu, mã kiểm tra và kết quả thực tế. Các kịch bản phải được đối chiếu phạm vi, điều kiện chất lượng và quyền dữ liệu.

## 13. Truy vết nghĩa vụ thành bằng chứng mà không biến backlog thành thủ tục giấy tờ

Trong dự án có kiểm toán, khả năng **traceability** giúp chứng minh đã đáp ứng những điều đã hứa. Nhưng nếu mỗi sửa đổi nhỏ phải viết mười tài liệu rời, nhóm mất khả năng phản hồi sớm.

### 13.1. Một ma trận truy vết tối thiểu

| Nghĩa vụ/tiêu chí | PBI hoặc công việc | Bằng chứng kỹ thuật | Phản hồi người dùng | Tình trạng nghiệm thu |
| --- | --- | --- | --- | --- |
| C-01 Đăng ký khóa hợp lệ | STORY-12 | Integration tests, kết quả DoD | Hiểu trạng thái đăng ký? | Chờ thủ tục áp dụng |
| C-02 Chống ghi trùng dữ liệu | STORY-14 | Concurrency test, kiểm tra ràng buộc | Không gặp trạng thái lặp | Chưa kết luận |
| C-03 Quyền học theo đăng ký | STORY-17 | Authorization tests | Mở bài đúng tài khoản | Chờ kiểm tra |
| C-04 Báo cáo tiến độ | STORY-22 | Kiểm thử báo cáo/đối soát | Người quản trị dùng được? | Chưa tới mốc |

Mã và tình trạng trong bảng **chỉ minh họa**. Nếu không có yêu cầu truy vết chính thức, nhóm có thể dùng bảng nhẹ; nếu tổ chức có chuẩn kiểm toán bắt buộc, cần đáp ứng đúng chuẩn đó.

### 13.2. Chọn chứng cứ được tạo trong quá trình làm

Nhiều bằng chứng có thể lấy từ công việc thường ngày:

- Pull request và lịch sử review.
- Kết quả CI và kiểm thử.
- Các ví dụ acceptance criteria và báo cáo test.
- Biên bản quyết định nghiệp vụ hoặc contract.
- Kết quả kiểm tra bảo mật/migration theo quyền.
- Phiên bản tài liệu triển khai và release notes.
- Phản hồi người dùng được ghi và xử lý đúng quyền dữ liệu.

Đừng mặc định những bằng chứng kỹ thuật này **tự đáp ứng yêu cầu chữ ký/hình thức pháp lý**. Cần kiểm tra điều kiện chấp nhận cụ thể.

### 13.3. Tránh hai dạng sai lệch

- **Không truy vết:** Đến mốc nghiệm thu không biết PBI nào chứng minh điều khoản nào.
- **Truy vết quá mức:** Mỗi task nhỏ cần quy trình riêng, làm chậm cả dòng mà không tăng khả năng kiểm chứng.

Thiết kế truy vết theo **quyết định, rủi ro và nghĩa vụ cần chứng minh**.

## 14. Mốc giao hàng, mốc thanh toán và nhịp Sprint không nhất thiết trùng nhau

Trong Scrum, một Sprint là khoảng thời gian cố định không quá một tháng để tạo ra **Increment có giá trị, hữu ích**. Các Sprint nối tiếp nhau giúp kiểm tra và thích ứng thường xuyên.

Trong hợp đồng mua sắm, bên mua có thể thanh toán hoặc nghiệm thu theo **mốc tài liệu, mốc hệ thống, mốc kiểm thử, bàn giao hoặc điều kiện pháp lý**. Một mốc thanh toán không mặc định đến vào cuối từng Sprint.

### 14.1. Ba dòng lịch khác nhau

| Dòng lịch | Mục đích | Ví dụ |
| --- | --- | --- |
| **Sprint / nhịp phát triển** | Giao Increment và học thường xuyên | Hai tuần kiểm tra một kết quả tích hợp |
| **Mốc hợp đồng** | Chứng minh nghĩa vụ/đầu ra theo tài liệu ký | Bàn giao chức năng đăng ký và báo cáo test vào một ngày đã định |
| **Mốc thanh toán/kiểm toán** | Hồ sơ và điều kiện giải ngân | Chứng từ chấp thuận đầu ra, phê duyệt chi theo chính sách |

Một Increment có thể **Done trước mốc hợp đồng**, hoặc đến mốc hợp đồng chỉ một phần Increment đã đạt DoD. Điều cần là **báo cáo đúng trạng thái và xử lý rủi ro**, không sửa nhãn để khớp lịch.

### 14.2. Tận dụng Sprint để giảm bất định cho nghiệm thu

Một cách thực hành:

1. Với từng mốc hợp đồng, liệt kê **hành vi và bằng chứng cần có**.
2. Chia thành những PBI nhỏ có thể đạt DoD sớm.
3. Thử hành vi và nhận phản hồi ở mỗi Sprint.
4. Ghi lại khoảng cách còn lại tới điều kiện nghiệm thu.
5. Đưa rủi ro mốc/giá/phạm vi lên đúng thẩm quyền **khi còn phương án**, không chờ tới ngày cuối.

### 14.3. Không tự hứa “Sprint nào cũng được thanh toán”

Nếu điều khoản không quy định thanh toán theo Increment, việc Scrum Team giao phần nhỏ thành công **không tự phát sinh quyền thanh toán**. Ngược lại, nếu hợp đồng cho phép nghiệm thu và thanh toán từng phần, nhóm có thể thiết kế bằng chứng và nhịp giao hàng để hỗ trợ, theo sự xác nhận của bộ phận hợp đồng.

### 14.4. Khi chất lượng chưa đạt vào ngày mốc

Không được tự đổi DoD, bỏ kiểm thử hoặc trình bày prototype như đầu ra đã đủ điều kiện chỉ để đủ hồ sơ. Cần:

- Xác minh phần nào thật sự Done.
- Ghi rõ những điều kiện còn thiếu và tác động.
- Xem các phương án kỹ thuật/nguồn lực còn được phép.
- Đề xuất điều chỉnh mốc hoặc cách xử lý theo **hợp đồng và thẩm quyền thực tế**.
- Không tuyên bố được nghiệm thu hoặc được thanh toán trước khi có quyết định hợp lệ.

## 15. Cộng tác ngay từ giai đoạn chuẩn bị mua sắm

Sự cứng nhắc thường bắt đầu **trước khi phát triển**: một bộ yêu cầu được mô tả như thể mọi nhu cầu, rủi ro và thiết kế đã biết chắc. Khi các bên ký xong mới phát hiện hiểu sai, mỗi điều chỉnh có thể trở thành thủ tục nặng.

### 15.1. Phân biệt nhu cầu, ràng buộc và giải pháp giả định trong RFP

| Loại nội dung | Ví dụ | Cách làm rõ có ích |
| --- | --- | --- |
| **Nhu cầu thực** | Người học phải đăng ký và mở bài thuận lợi | Mô tả hành trình, trường hợp thành công/thất bại |
| **Ràng buộc bắt buộc** | Quyền dữ liệu, tích hợp với hệ thống tài khoản hiện hữu | Ghi điều kiện kiểm chứng và người có quyền |
| **Tiêu chí chọn nhà cung cấp** | Năng lực bảo mật, vận hành, hỗ trợ | Làm rõ bằng chứng cần nộp |
| **Giải pháp đang giả định** | Bắt buộc có ba màn hình và một mẫu thông báo cụ thể | Hỏi liệu đây là yêu cầu cứng hay thiết kế có thể thay đổi |
| **Điều chưa chắc** | Người học cần email hay chỉ xác nhận trong ứng dụng? | Đề xuất cách khảo sát sớm nếu cơ chế mua sắm cho phép |

Hồ sơ mua sắm đôi khi phải mô tả chi tiết vì quy định hoặc kiểm toán. Mục tiêu không phải yêu cầu bên mua **bỏ hết tiêu chí**, mà là làm rõ **cái gì phải được bảo đảm** và **cái gì cần được kiểm chứng khi sử dụng**.

### 15.2. Những hoạt động có thể đề xuất trước khi ký

- Buổi làm rõ hành trình người dùng và tình huống biên.
- Hỏi đáp nhà thầu qua kênh **chính thức** để các bên được đối xử phù hợp quy tắc mua sắm.
- Prototype hoặc mẫu thử nếu quy trình cho phép và trách nhiệm dữ liệu rõ.
- Xác định baseline đầu ra cùng quyền làm rõ yêu cầu.
- Dự kiến các mốc kiểm tra trung gian không bị nhầm với nghiệm thu.
- Làm rõ thủ tục đề xuất thay đổi và đầu mối phê duyệt.
- Thống nhất cách lưu bằng chứng, truy vết và quyền truy cập.

**Trong mua sắm có cạnh tranh, trao đổi với riêng một nhà thầu có thể bị hạn chế.** Không tự mở kênh đặc quyền; dùng quy trình hỏi đáp, công bố hoặc tiếp xúc thị trường được phép.

### 15.3. Đừng cam kết khả năng chưa thể xác minh

Một đề xuất của nhà cung cấp có thể nói “mọi tích hợp đều hoàn tất trong hai tuần” khi chưa được tiếp cận API thật. Cách trình bày có trách nhiệm hơn là ghi **giả định, phụ thuộc và điều kiện tiếp cận** trong phạm vi quy trình cho phép, tránh tạo cam kết giả chắc chắn.

Nếu quy trình đòi báo giá cố định trong điều kiện nhiều bất định, nhà cung cấp cần đánh giá rủi ro và lựa chọn tham gia của mình; **Agile không xóa rủi ro hợp đồng chỉ vì sau này có thể làm spike**.

## 16. Sau khi đã trao thầu: cộng tác trong giới hạn thay đổi hợp lệ

Sau khi hợp đồng có hiệu lực, cơ chế mua sắm có thể không cho phép đàm phán lại nhiều điều khoản, đặc biệt nếu việc sửa làm thay đổi đáng kể cơ sở cạnh tranh hoặc thẩm quyền mua sắm.

**Không có một danh sách thay đổi “luôn được phép” áp dụng mọi hợp đồng hay nơi quản lý.** Cần xác minh quy trình cụ thể.

### 16.1. Những việc vẫn có thể làm một cách có trách nhiệm

1. Duy trì đối thoại thường xuyên về **hành vi người dùng và rủi ro chất lượng**.
2. Làm rõ yêu cầu mơ hồ thông qua người có thẩm quyền diễn giải/đối thoại.
3. Thử giải pháp kỹ thuật trong **quyền triển khai đã được trao**.
4. Chia PBI và đổi thứ tự nội bộ **nếu không làm hại các nghĩa vụ**.
5. Giao Increment theo DoD và thu bằng chứng sớm.
6. Nhận diện thay đổi ngoài phạm vi và **đưa vào change control**, không làm ngầm.
7. Nếu một ràng buộc tạo bế tắc, trình bày sự thật và các phương án theo quy định.

### 16.2. “Không được sửa hợp đồng” không có nghĩa “không được phản hồi”

Ví dụ, hợp đồng đã quy định phải có màn hình đăng ký. Người học thử thấy câu chữ khó hiểu. Nếu chỉnh câu chữ, màu sắc, trạng thái hoặc thứ tự hiển thị **nằm trong quyền thay thiết kế và không vi phạm baseline/tiêu chí** thì nhóm có thể cải tiến theo quy trình đã thống nhất.

Nếu người học đề nghị một luồng **đăng ký trả góp** vốn không có trong nghĩa vụ, đó là nhu cầu mới có thể ghi Product Backlog để cân nhắc tương lai, nhưng **chưa phải cam kết triển khai**.

### 16.3. Kiểm soát thay đổi không nên chỉ là câu trả lời “không”

Người phụ trách hợp đồng có thể hỗ trợ Product Owner và Developers bằng cách:

- Chỉ ra ranh giới nào đang ràng buộc.
- Làm rõ bằng chứng cần để phân loại đề xuất.
- Giải thích người ký và bước phê duyệt.
- Nêu những lựa chọn hợp lệ thay vì yêu cầu “đừng thay gì”.

Tương tự, nhóm Agile nên mang đến **vấn đề, tác động và các phương án có chi phí/rủi ro**, không chỉ yêu cầu bộ phận mua sắm “linh hoạt hơn”.

## 17. Thiết kế nhịp giao tiếp để giảm bất ngờ hợp đồng

Cộng tác không đồng nghĩa phải tăng số cuộc họp đến mức Developers không còn thời gian hoàn tất Increment. Cần một nhịp **rõ mục đích, đúng người, đúng quyền và có đầu ra**.

### 17.1. Mẫu nhịp phối hợp

| Hoạt động | Người liên quan | Mục đích | Đầu ra hữu ích |
| --- | --- | --- | --- |
| **Refinement** | PO, Developers, nghiệp vụ cần thiết | Làm rõ PBI và rủi ro | Ví dụ hành vi, phụ thuộc, câu hỏi cần quyết định |
| **Sprint Review** | Scrum Team, stakeholder được mời | Kiểm tra Increment và phản hồi | Tín hiệu giá trị, câu hỏi, backlog thay đổi |
| **Kiểm tra hợp đồng định kỳ** | Contract/procurement, phía mua/bán theo quyền | Nhìn các thay đổi và mốc ràng buộc | Quyết định, trạng thái CR, tác động và người duyệt |
| **Kiểm tra chất lượng/vận hành** | Developers, test, security/operations | Xem DoD, lỗi, dữ liệu, rủi ro | Bằng chứng và việc cần khắc phục |
| **Escalation theo sự kiện** | Người có quyền cho vấn đề cụ thể | Giải quyết blocker, sự cố hoặc mốc nguy hiểm | Chỉ đạo hợp lệ, ngày hiệu lực và người thực hiện |

Các hoạt động ngoài Scrum là **mẫu phối hợp bổ sung**, không tự trở thành Scrum events. Nếu cùng một thông tin được báo ở ba cuộc họp, cần thiết kế lại cách chia sẻ.

### 17.2. Một cuộc trao đổi nên đóng bằng bốn câu

1. **Đã quan sát điều gì?** Có bằng chứng nào?
2. **Điều đó thay đổi dự báo hoặc rủi ro gì?**
3. **Quyết định nào nằm trong quyền hiện tại, quyết định nào cần đưa lên?**
4. **Ai làm bước tiếp theo, khi nào kiểm tra lại?**

### 17.3. Lưu “ai đã nói gì” chưa đủ, cần lưu trạng thái quyết định

Một ghi chú như “khách hàng muốn thêm email” còn thiếu:

- Đây là góp ý hay yêu cầu chính thức?
- Email có trong baseline đã ký không?
- Người đưa yêu cầu có quyền nào?
- Có tác động chi phí/mốc hoặc chất lượng không?
- Nhóm đang khảo sát, chờ phê duyệt hay đã được duyệt?

**Nhận phản hồi khác với nhận cam kết.** Sổ quyết định rõ giúp bảo vệ cả khách hàng lẫn nhà cung cấp khỏi hiểu lầm.

## 18. Quản lý bất đồng giữa giá trị người dùng và phạm vi đã ký

Một bất đồng điển hình:

> Đại diện nghiệp vụ: “Người học không dùng được báo cáo hiện tại; phải đổi thiết kế.”
>
> Nhà cung cấp: “Đây là ngoài phạm vi, chúng tôi không làm.”
>
> Bộ phận mua sắm: “Không thể sửa hợp đồng ngay.”

Tranh luận chỉ quanh chữ “scope” có thể khiến mọi người **không còn nhìn vấn đề người dùng**.

### 18.1. Hướng tiếp cận ba bước

**Bước 1 — Cùng xác minh vấn đề:** Người học hoặc quản trị viên không làm được nhiệm vụ nào? Có bao nhiêu trường hợp, điều kiện thử và tác động gì? Sản phẩm đang đáp ứng đúng tiêu chí đã cam kết chưa?

**Bước 2 — Tách các loại giải pháp:** Có sửa bug/phần mơ hồ đã có, cải tiến thiết kế trong phạm vi, hay phải bổ sung đầu ra? Có giải pháp an toàn ít thay đổi hơn không?

**Bước 3 — Ra quyết định theo quyền:** Việc trong phạm vi được đưa vào Product Backlog theo ưu tiên phù hợp; thay đổi nghĩa vụ cần đề xuất chính thức, có thể bị từ chối hoặc yêu cầu phương án khác.

### 18.2. Tranh luận dựa trên bằng chứng

| Cách nói dễ tạo đối đầu | Cách nói mở đường cộng tác |
| --- | --- |
| “Khách hàng đổi ý liên tục.” | “Qua thử nghiệm, giả định ban đầu về hành trình chưa đúng ở bước nào?” |
| “Nhà cung cấp viện hợp đồng để trốn việc.” | “Đầu ra hiện tại đã đáp ứng điều khoản nào; phần chênh cần phân loại ra sao?” |
| “Procurement chỉ cản trở Agile.” | “Quyền nào có thể trao để làm rõ hàng ngày; điểm nào bắt buộc cần duyệt?” |
| “Người dùng cứ đòi tính năng mới.” | “Nhu cầu phía sau là gì; có thể đáp ứng bằng phần đã có không?” |
| “Cứ làm trước, ký sau.” | “Có phương án thử không phát sinh nghĩa vụ trước khi quyết định?” |

### 18.3. Quan hệ đối tác không loại bỏ bất đối xứng quyền lực

Khách hàng có thể kiểm soát thanh toán, nhà cung cấp có thể kiểm soát thông tin kỹ thuật, còn người dùng ít tiếng nói. Khi có xung đột, cần **minh bạch thông tin, trách nhiệm và rủi ro**, không gây áp lực để một người ký vượt quyền hoặc một nhóm che lỗi nhằm giữ quan hệ.

### 18.4. Không hứa điều chưa được duyệt

Một câu trả lời hữu ích:

> “Chúng tôi ghi nhận việc người học cần email xác nhận. Hiện chưa xác định yêu cầu này thuộc phạm vi đã ký hay thay đổi bổ sung. Nhóm sẽ kiểm tra tiêu chí liên quan, dự báo tác động rồi trình đúng người quyết định; trước khi có kết luận, chúng tôi chưa cam kết ngày giao email.”

Từ chối hứa tùy tiện **không đồng nghĩa từ chối lắng nghe**.

## 19. Rủi ro và giả định phải được nhìn trước khi thành tranh chấp

Một dự án hợp đồng cứng cần **nhìn thấy bất định sớm**, đặc biệt các phụ thuộc không do Scrum Team tự kiểm soát.

### 19.1. Risk/assumption log tối giản

| Rủi ro hoặc giả định | Dấu hiệu | Tác động có thể | Hành động và người phối hợp |
| --- | --- | --- | --- |
| API tài khoản khách hàng chưa sẵn | Không có môi trường test hoặc hợp đồng tích hợp | Chậm luồng đăng ký, lỗi phân quyền | Xin điều kiện tiếp cận, xây contract mock có kiểm chứng |
| Mẫu báo cáo chưa phản ánh công việc thật | Người quản trị thử thấy phải xuất tay | Đầu ra có thể bị phản đối nghiệm thu | Làm rõ ví dụ, kiểm tra baseline và đề xuất thay đổi nếu cần |
| Dữ liệu thử chứa dữ liệu nhạy cảm | Môi trường chung chưa có kiểm soát | Rủi ro privacy/security | Dùng dữ liệu giả, xin quyền đúng quy định |
| Mốc hợp đồng sớm hơn khả năng tích hợp | WIP và blocked time tăng, CI đỏ | Trễ nghiệm thu hoặc giảm chất lượng nếu xử lý sai | Dự báo, điều chỉnh kế hoạch, escalation sớm |
| Người phản hồi không có quyền ký | Yêu cầu đổi phạm vi qua chat cá nhân | Tranh chấp trách nhiệm/chi phí | Làm rõ thẩm quyền, chuẩn hóa kênh quyết định |
| Một yêu cầu được diễn giải khác nhau | Các nhóm test hai kỳ vọng trái nhau | Làm lại và tranh cãi nghiệm thu | Ví dụ chung, ghi xác nhận theo quyền |

Rủi ro nên có **người theo dõi, tác động và cách giảm**, không chỉ nhãn đỏ/vàng/xanh.

### 19.2. Phân biệt sự thật, giả định và dự báo

**Sự thật:** “Môi trường tích hợp chưa cấp quyền truy cập tới ngày được ghi nhận.”

**Giả định:** “Chúng ta kỳ vọng sẽ có môi trường trước Sprint tiếp theo.”

**Dự báo:** “Nếu quyền tiếp cận không có trước mốc X, phần kiểm thử tích hợp khó đạt DoD theo kế hoạch.”

**Quyết định:** “Cần người có quyền xác nhận lịch cấp, hoặc chọn phương án được phê duyệt.”

Không nên trình bày dự báo như một sự kiện chắc chắn hoặc đổi một giả định thành lời hứa hợp đồng.

### 19.3. Đưa rủi ro lên sớm không phải “báo cáo thất bại”

Một nhóm Agile đáng tin phải có khả năng nói “mốc này có rủi ro” khi còn đủ thời gian trao đổi phạm vi và phương án. Nếu tổ chức trừng phạt mọi cảnh báo, người làm sẽ có động cơ giấu blocker đến ngày cuối.

Đây là vấn đề **văn hóa hợp tác và quản trị**, không chỉ khả năng ước lượng.

## 20. Dữ liệu, bảo mật và quyền truy cập trong hoạt động cùng khách hàng

Khách hàng muốn thử phần mềm với dữ liệu thật để nhận phản hồi, nhưng nhiều chương trình mua sắm có ràng buộc về tài khoản, quyền sử dụng dữ liệu, lưu trữ, an ninh mạng và bên thứ ba.

### 20.1. Những câu hỏi trước khi mở buổi dùng thử

- Ai có quyền tham gia, dùng môi trường và xem dữ liệu?
- Dữ liệu thử có chứa thông tin cá nhân không?
- Có thể tạo dữ liệu giả hoặc đã loại định danh phù hợp chưa?
- Ai có quyền cấp tài khoản, thay đổi quyền, trích xuất log?
- Buổi thử có cần thông báo, chấp thuận hoặc đánh giá bảo mật?
- Tài liệu/chụp màn hình được phép lưu, chia sẻ và bao lâu?
- Có cơ chế phản hồi an toàn mà không lộ dữ liệu của người học khác?

**Không được coi việc khách hàng mời một người dùng tham gia là bằng chứng tự động rằng mọi cách thu thập, ghi hình và xử lý dữ liệu đều được phép.**

### 20.2. Sprint Review không phải lý do đưa dữ liệu production vào môi trường thử

Nếu nhóm chưa có quyền sử dụng dữ liệu thật, hãy ưu tiên dữ liệu giả có tính đại diện để kiểm chứng hành vi. Những trường hợp cần dữ liệu thực phải theo chính sách và quyền phù hợp.

### 20.3. Công cụ cộng tác cũng là hệ thống cần kiểm soát

Hợp đồng, thông tin tài chính, bản ghi người học hoặc cấu hình nhạy cảm không nên được sao chép tùy tiện vào chat công khai, hệ thống quản lý công việc không được cấp phép hoặc dịch vụ AI ngoài chính sách.

Khả năng cộng tác tốt dựa trên **đường truy cập được phê duyệt**, không dựa trên việc bỏ kiểm soát để chia sẻ nhanh.

### 20.4. Thực hiện biện pháp an toàn không phải “scope creep tùy chọn”

Nếu phát hiện một lỗ hổng phân quyền nghiêm trọng, nhóm phải xử lý theo yêu cầu an toàn áp dụng và quyền có liên quan; đồng thời xem trách nhiệm/ảnh hưởng hợp đồng nếu có. Không dùng nhãn “phát sinh ngoài scope” để trì hoãn biện pháp bảo vệ bắt buộc khi đang có rủi ro gây hại.

## 21. Scrum trong quan hệ khách hàng–nhà cung cấp

Scrum giúp làm rõ **accountabilities, artifacts và commitments**, nhưng **không tự xác định ai được ký hợp đồng**.

### 21.1. Product Owner cần quyền sản phẩm thực, không chỉ làm người ghi yêu cầu

Product Owner chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog. Quyết định về thứ tự, Product Goal và trao đổi giá trị cần được tổ chức công nhận trong phạm vi Scrum.

Nếu mỗi đề xuất ưu tiên nhỏ phải qua nhiều người quản lý không có cơ chế phân quyền, một người mang danh PO nhưng không có quyền sẽ khó thực hiện trách nhiệm. Tổ chức nên:

1. Làm rõ quyền **quản lý Product Backlog**.
2. Làm rõ quyền **phân loại phản hồi và yêu cầu làm rõ**.
3. Làm rõ ranh giới với **quyền sửa hợp đồng/chi ngân sách**.
4. Tạo đường escalation nhanh cho quyết định vượt quyền.

### 21.2. Khi nhà cung cấp và khách hàng cùng tham gia Scrum

Có thể có thành viên Developers từ nhà cung cấp và Product Owner ở phía khách hàng, nếu tổ chức phù hợp và trách nhiệm thực được xác lập. Nhưng **đừng tự cho rằng cơ cấu nhân sự của hợp đồng luôn trùng Scrum Team**.

Điểm cần giữ:

- Scrum Team có kỹ năng cần thiết để tạo Increment theo DoD.
- Developers tự quản cách thực hiện và kế hoạch trong Sprint.
- Product Owner giữ hướng giá trị và thứ tự Product Backlog.
- Scrum Master hỗ trợ Scrum hiệu quả và tháo gỡ trở ngại.
- Điều khoản hợp đồng/mua sắm được quản trị bởi người có thẩm quyền.

### 21.3. Sprint Goal và Product Goal không thay baseline hợp đồng

**Product Goal** là commitment của Product Backlog; **Sprint Goal** là commitment của Sprint Backlog; **DoD** là commitment của Increment. Những commitments này giúp Scrum Team minh bạch kết quả và hướng tới giá trị.

Nhưng nếu một điều khoản bắt buộc quy định đầu ra khác, việc Scrum Team đã đạt Sprint Goal không tự chứng minh đã hoàn thành mốc hợp đồng.

### 21.4. Những thay đổi trong Sprint

Scrum cho phép **làm rõ và thương lượng lại phạm vi với Product Owner khi học thêm**, nhưng **chất lượng không được giảm** và không thực hiện thay đổi gây nguy hiểm cho Sprint Goal.

Nếu điều chỉnh phạm vi có tác động nghĩa vụ hợp đồng, **còn cần phê duyệt hợp đồng theo quyền tương ứng**. Thương lượng backlog và sửa hợp đồng là hai hoạt động có thể liên quan nhưng không đồng nhất.

### 21.5. Product Owner không “ký cho qua” DoD

Nếu lỗi đăng ký trùng chưa được xử lý theo DoD, không thể gọi PBI là Increment Done chỉ vì khách hàng đang cần demo. Nếu Product Owner hoặc sponsor muốn chấp nhận một ngoại lệ chất lượng, cần xem các chuẩn bắt buộc và quyền áp dụng; **không được tạo báo cáo Done giả**.

## 22. Kanban, XP và Lean giúp cộng tác ít phụ thuộc hơn

Ngay cả khi hợp đồng không thể thay đổi, **cách thực hiện bên trong** có thể được cải tiến trong giới hạn cho phép.

### 22.1. Kanban — làm rõ luồng và hàng chờ quyết định

Một workflow có thể theo:

~~~text
Product Backlog
   -> Làm rõ trong phạm vi
   -> Đang phát triển
   -> Review / CI
   -> Kiểm thử tích hợp
   -> Done theo DoD

Song song:
   Đề xuất cần thay đổi hợp đồng
   -> Chờ đánh giá quyền/tác động
   -> Được duyệt hoặc không duyệt
   -> Nếu được duyệt, cập nhật baseline và backlog
~~~

Đừng để “Chờ phê duyệt thay đổi hợp đồng” lẫn với “Đang phát triển” rồi báo WIP thấp giả. Cần định nghĩa ranh giới khi đo, đồng thời tránh biến mọi ý tưởng chưa duyệt thành PBI đã cam kết.

Những chỉ số hữu ích:

- **WIP:** Có bao nhiêu công việc đã bắt đầu mà chưa Done?
- **Work Item Age:** Những item nào tồn lâu, ở bước nào?
- **Cycle Time:** Các item đã Done mất bao lâu?
- **Throughput:** Bao nhiêu item thật sự Done trong một kỳ?
- **Decision latency:** Đề xuất thay đổi mất bao lâu để nhận quyết định có thẩm quyền?
- **Blocked time:** Bao lâu vì hợp đồng, dữ liệu, review, môi trường?

Nếu một quyết định nằm ở bộ phận mua sắm, Developers không thể “code nhanh hơn” để xóa hàng chờ ấy. Cần **minh bạch và gỡ đúng điểm nghẽn**.

### 22.2. XP — tăng khả năng sửa đúng trong giới hạn

| Thực hành | Giá trị khi yêu cầu bị ràng buộc | Lưu ý |
| --- | --- | --- |
| **Test-Driven Development** | Làm rõ ví dụ và phát hiện sai lệch sớm | Không thay hợp đồng hay mọi test tích hợp |
| **Continuous Integration** | Giảm xung đột khi nhiều thay đổi | Pipeline xanh chỉ chứng minh test đã cấu hình |
| **Pair programming/review** | Cùng hiểu quy tắc hợp đồng/miền nghiệp vụ | Vẫn giữ quyền phê duyệt chuyên môn cần thiết |
| **Refactoring** | Giảm chi phí sửa khi nhận phản hồi | Không tự đổi hành vi đã cam kết |
| **Small releases** | Giao phần giá trị và học sớm | Phải đáp ứng DoD và chính sách phát hành |
| **Simple design** | Tránh đầu tư vào giải pháp chưa cần | Không bỏ chuẩn dữ liệu/an toàn |

### 22.3. Lean — nhìn giá trị toàn dòng

Nếu hợp đồng đòi ba lần phê duyệt hợp lệ, không thể đơn phương xóa chúng. Nhưng nhóm có thể:

- Gửi đúng tài liệu từ lần đầu.
- Chuẩn bị bằng chứng trong khi phát triển.
- Nhận diện sớm phụ thuộc dữ liệu/kiểm toán.
- Cải tiến việc phê duyệt tự động ở bước **được phép**.
- Tránh làm lại do diễn giải yêu cầu khác nhau.
- Giảm WIP để không dồn quá nhiều việc cần quyết định vào một lúc.

Tối ưu Lean không phải “bỏ mọi kiểm soát”, mà là **giảm chờ và công việc không tạo giá trị mà vẫn bảo vệ nghĩa vụ thật**.

## 23. Một phương pháp “hai đường” cho dự án có ràng buộc

Với hợp đồng cứng, nhóm có thể cần **hai đường phối hợp song song**:

1. **Đường học hỏi và giao sản phẩm:** Product Goal, nghiên cứu người dùng, Product Backlog, Sprint, DoD, phản hồi.
2. **Đường quản trị nghĩa vụ:** Baseline hợp đồng, change control, phê duyệt, bằng chứng nghiệm thu, mốc và thanh toán.

### 23.1. Hai đường không được tách thành hai thế giới

~~~mermaid
flowchart TD
    A["Người dùng và khách hàng"] --> B["Vấn đề/outcome cần học"]
    B --> C["Product Backlog và Increment Done"]
    C --> D["Phản hồi về hành vi và chất lượng"]
    D --> B
    D --> E{"Có ảnh hưởng baseline?"}
    E -->|"Không"| F["Quyết định trong quyền sản phẩm"]
    F --> C
    E -->|"Có/chưa rõ"| G["Đánh giá và phê duyệt thay đổi"]
    G --> H{"Được chấp thuận theo quy trình?"}
    H -->|"Có"| I["Cập nhật nghĩa vụ, kế hoạch, backlog"]
    I --> C
    H -->|"Không"| J["Giữ cam kết hiện hành; tìm phương án hợp lệ"]
    J --> C
    C --> K["Bằng chứng DoD/nghiệm thu theo phạm vi"]
    K --> L["Chủ thể nghiệm thu có thẩm quyền"]
~~~

**Một buổi Review có thể tạo dữ liệu cho cả hai đường**, nhưng không mặc định có hiệu lực thay đổi baseline hoặc ký nghiệm thu.

### 23.2. Tránh làm “discovery” vô hạn

Nghiên cứu hành vi rất hữu ích, nhưng hợp đồng cũng có ngân sách và mốc. Một hoạt động discovery nên có:

- Câu hỏi rủi ro cụ thể.
- Thời lượng/phạm vi được phép.
- Dữ liệu có thể thu thập hợp pháp.
- Bằng chứng kỳ vọng.
- Quyết định có thể thay đổi sau khi học.

Một prototype không có mục đích ra quyết định dễ trở thành việc ngoài phạm vi, tiêu thụ thời gian mà không giúp nghĩa vụ được hoàn tất.

### 23.3. Phản hồi không tự cập nhật kế hoạch

Sau nghiên cứu, cần chọn **giữ nguyên, làm rõ, điều chỉnh trong quyền hoặc gửi thay đổi chính thức**. Nếu mọi phát hiện đều nằm trong danh sách “xem sau” mà không ai quyết định, Agile bị biến thành nghi thức thu thập ý kiến.

## 24. Tình huống xuyên suốt: hợp đồng 12 tuần cho nền tảng học trực tuyến

### 24.1. Dữ kiện giả định

Một đơn vị đào tạo ký hợp đồng **12 tuần**, ngân sách cố định, gồm những đầu ra chính:

| Mã tham khảo | Đầu ra được mô tả trong baseline giả định | Điều cần kiểm chứng |
| --- | --- | --- |
| H-01 | Đăng ký khóa miễn phí và xác nhận trạng thái | Không ghi trùng, trạng thái rõ, quyền đúng |
| H-02 | Mở bài đầu và theo dõi tiến độ | Người học truy cập theo quyền, không mất tiến độ |
| H-03 | Quản lý danh sách khóa | Danh mục, tình trạng hiển thị đúng |
| H-04 | Báo cáo tiến độ cho quản trị viên | Dữ liệu nhất quán theo tiêu chí đã ký |
| H-05 | Quản trị tài khoản và phân quyền | Không lộ dữ liệu người dùng khác |
| H-06 | Kiểm thử, tài liệu và bàn giao | Bằng chứng theo điều kiện nghiệm thu |

Mốc cuối và điều kiện nghiệm thu được hợp đồng quy định. Nhóm thực hiện dùng các Sprint hai tuần để phát triển tăng dần. **Mọi mã và mốc trong tình huống là dữ liệu giả định phục vụ học**, không phải hợp đồng thực.

### 24.2. Phản hồi sau hai Sprint

Khách hàng đã dùng thử Increment đăng ký:

- Luồng đăng ký bình thường hoạt động.
- Người học chưa thấy rõ đường dẫn tới bài đầu.
- Thử tình huống timeout cho thấy thông báo thành công chưa chính xác.
- Một đại diện nghiệp vụ muốn thay H-04 bằng dashboard cá nhân hóa.
- Người mua sắm cho biết **chưa có quyết định nào thay đổi H-04**.

Nhóm cần xử lý **bốn loại thông tin khác nhau**:

| Phát hiện | Phân loại sơ bộ | Bước hợp lý |
| --- | --- | --- |
| Timeout khiến UI báo thành công sai | Có thể là **lỗi** đối với hành vi xác nhận đáng tin cậy/DoD | Tái hiện, sửa, test và xác minh nghĩa vụ |
| Người học khó tìm đường mở bài | Cần kiểm tra trong H-02/H-01 hay yêu cầu thiết kế mới | Làm rõ với PO và người có quyền về phạm vi |
| Dashboard cá nhân hóa thay báo cáo H-04 | Có khả năng **thay đổi đầu ra đã ký** | Phân tích tác động, change control; chưa bỏ H-04 |
| Nghiệm thu chưa tới mốc | Không cản việc nhận phản hồi sớm | Demo theo Sprint; không ghi đã nghiệm thu pháp lý |

### 24.3. Điều chỉnh backlog mà không giấu nghĩa vụ

Product Owner có thể ưu tiên những PBI trong phạm vi giúp **đăng ký và mở bài đáng tin**. Developers chia lát cắt:

1. Xử lý chính xác timeout và trạng thái đăng ký.
2. Kiểm thử hai yêu cầu gần đồng thời và phân quyền.
3. Cải thiện đường dẫn tới bài đầu theo phạm vi được xác nhận.
4. Ghi lại yêu cầu dashboard mới dưới trạng thái **đang chờ quyết định phạm vi**.
5. Giữ H-04 trên bảng nghĩa vụ cho đến khi có phê duyệt hợp lệ.

Nếu quá tải hoặc mốc cuối có nguy cơ, cần đưa **dự báo và các phương án** tới người có quyền, không tự xóa H-04 khỏi kế hoạch.

### 24.4. Thông báo trạng thái có trách nhiệm

> “Sau hai Sprint, luồng đăng ký đã có Increment dùng thử, nhưng xử lý timeout chưa đạt chuẩn chất lượng nên phần đó chưa được coi Done. Phản hồi người học cho thấy cần làm rõ đường dẫn mở bài; nhóm đang đối chiếu với phạm vi H-01/H-02. Đề nghị thay báo cáo H-04 bằng dashboard mới có thể ảnh hưởng baseline và đang chờ đánh giá thay đổi; trước khi được duyệt, H-04 vẫn là cam kết hiện hành. Nhóm sẽ cung cấp kết quả kiểm thử và các phương án tác động mốc để người có thẩm quyền quyết định.”

Thông báo không đổ lỗi, không giả rằng “gần xong” là Done và không đặt khách hàng trước việc đã rồi.

### 24.5. Ba nhánh quyết định cho dashboard cá nhân hóa

**Nhánh A — Không phê duyệt thay đổi:** Nhà cung cấp tiếp tục H-04 theo baseline; ý tưởng dashboard mới có thể giữ làm nhu cầu tương lai nếu được phép.

**Nhánh B — Phê duyệt thay thế hợp lệ:** Cập nhật tài liệu có hiệu lực, tiêu chí nghiệm thu, giá/mốc khi có thay đổi và liên kết PBI tương ứng. Nhóm chỉ thực hiện sau khi điều kiện có hiệu lực được xác nhận.

**Nhánh C — Cần thêm dữ liệu:** Làm prototype hoặc nghiên cứu có mục đích **trong quyền và năng lực được chấp thuận**, ước lượng tác động rồi trình lại. Không coi việc khảo sát là cam kết chắc chắn sẽ triển khai.

## 25. Tình huống thứ hai: một đề nghị tưởng nhỏ gây thay đổi lớn

Khách hàng gửi yêu cầu:

> “Chỉ thêm nút ‘Hoàn thành khóa’ để quản trị viên đánh dấu một người đã tốt nghiệp. Chắc một ngày là xong?”

Về giao diện, nút bấm có thể nhỏ. Nhưng phía dưới có thể phát sinh:

- Ai được quyền đánh dấu hoàn thành?
- Hoàn thành có là một **trạng thái pháp lý/nghiệp vụ** liên quan chứng chỉ không?
- Người học có thể phản đối hoặc sửa trạng thái?
- Hệ thống có cần lưu dấu vết ai sửa và lúc nào?
- Có ảnh hưởng kết quả học hoặc báo cáo đã ký?
- Dữ liệu trước đây có cần migration?
- Quy tắc đó thuộc đầu ra H-02/H-04 hay là chức năng mới?

**Không định nghĩa phạm vi thay đổi bằng kích thước nút bấm.**

### 25.1. Một chuỗi xử lý đúng

1. Ghi hành vi và quyết định nghiệp vụ mà nút đại diện.
2. Hỏi phạm vi đã ký và tiêu chí nghiệm thu liên quan.
3. Phân tích dữ liệu, phân quyền, audit và tác động UI/API/report.
4. Chọn phương án: trong phạm vi, làm rõ hợp lệ, hoặc change request.
5. Nếu ngoài phạm vi, chờ phê duyệt theo quyền trước khi cam kết.
6. Khi được thực hiện, bổ sung kiểm thử và chứng cứ DoD/nghiệm thu.

### 25.2. Chống “ước lượng để vừa lòng”

Một Developer bị hỏi giữa cuộc họp có thể nói “mất một ngày” khi chưa biết ràng buộc chứng chỉ. Nên phản hồi:

> “Phần giao diện có thể nhỏ, nhưng cần xác minh quyền, dữ liệu và quy tắc hoàn thành trước khi đưa ra dự báo đáng tin. Chúng tôi sẽ trả lại phân loại phạm vi, các phụ thuộc và phương án thực hiện theo quyền.”

Đó là cộng tác chuyên nghiệp, không phải trì hoãn vô cớ.

## 26. Đo việc cộng tác và quản trị để biết có thực sự cải tiến

Không nên chỉ đo số cuộc họp với khách hàng, số change request hoặc số story points. **Đo để hỗ trợ câu hỏi và quyết định**.

| Câu hỏi quản trị | Metric/tín hiệu có thể dùng | Cách diễn giải có trách nhiệm |
| --- | --- | --- |
| Phản hồi có tới đủ sớm? | Thời gian từ Increment Done tới buổi quan sát/nhận phản hồi | Nhanh hơn chưa đủ, phải xem chất lượng phản hồi |
| Quyết định phạm vi có nghẽn? | Tuổi CR đang chờ, thời gian ra quyết định | Phân loại theo quyền và độ phức tạp |
| Có ít làm lại do hiểu sai? | Số/chi phí rework liên quan thay đổi diễn giải | Cần ghi nhận trung thực, không phạt người báo lỗi |
| Nghĩa vụ có đang được đáp ứng? | Đầu ra/bằng chứng đạt theo baseline, rủi ro mốc | Không cộng task nội bộ như đã nghiệm thu |
| Chất lượng tích hợp có tốt? | Lỗi nghiệm thu, lỗi sau phát hành, kết quả CI/DoD | Ít bug được báo không tự chứng minh chất lượng |
| Người dùng có nhận giá trị? | Task success, activation, kết quả sử dụng theo định nghĩa | Đo theo cohort/ngữ cảnh, không đánh đồng click với value |
| Dòng công việc có đang chờ? | WIP, Work Item Age, Cycle Time, blocked time | Không dùng để xếp hạng nhân sự |
| Có minh bạch chi phí/rủi ro? | Chênh kế hoạch–thực tế có giải thích, quyết định đúng hạn | Không biến dự báo thành lời hứa giả |

### 26.1. Ví dụ thời gian ra quyết định thay đổi

Giả sử năm CR có thời gian từ **hồ sơ hợp lệ được nộp** đến **quyết định có thẩm quyền** là:

~~~text
2, 3, 5, 8, 12 ngày làm việc
~~~

Trung vị là **5 ngày làm việc**; giá trị lâu nhất **12 ngày**. Điều đó có thể gợi câu hỏi: loại CR nào chờ lâu, có phụ thuộc phê duyệt, hồ sơ thiếu hay cần đánh giá bảo mật? **Không tự suy ra người duyệt làm việc chậm**.

Nếu một CR bắt buộc có đánh giá chuyên môn phức tạp, không nên so ngang với thay đổi câu chữ đơn giản. Phân khúc số liệu theo **loại thay đổi và quyền quyết định**.

### 26.2. Khi tối ưu metric có thể gây hại

- Ép **số CR giảm** có thể khiến người ta giấu nhu cầu mới hoặc xử lý miệng.
- Ép **thời gian phê duyệt bằng không** có thể bỏ kiểm tra bắt buộc.
- Ép **mọi Sprint nghiệm thu chính thức** khi hợp đồng không cho phép có thể tạo hồ sơ sai.
- Ép **story points tăng** có thể khuyến khích hạ DoD hoặc thổi ước lượng.
- Ép **số lỗi được báo giảm** có thể khiến lỗi không còn được ghi.

Guardrail nên gồm **tuân thủ nghĩa vụ, chất lượng, an toàn, quyền dữ liệu và kết quả người dùng**.

### 26.3. Dùng dữ liệu để thay đổi chính sách có căn cứ

Nếu nhiều CR bị trả lại vì thiếu mẫu phân tích tác động, có thể cải tiến **checklist hồ sơ** và trao đổi sớm. Nếu việc chờ nằm ở một bước ký bắt buộc theo quyền, cần lập kế hoạch có tính tới thời gian ấy; không tự xóa bước ký.

### 26.4. Không khẳng định nhân quả chỉ từ trước/sau

Giả sử thời gian phê duyệt trung vị giảm từ 8 xuống 4 ngày sau khi tổ chức workshop liên nhóm. Điều này **chưa chứng minh workshop gây ra toàn bộ thay đổi**: loại CR, lịch họp hoặc nhân sự phê duyệt có thể khác. Cần xem phân bố, mức độ phức tạp và nhiều kỳ.

## 27. Những hiểu lầm thường gặp khi Agile gặp hợp đồng cứng

**1. “Agile coi trọng cộng tác nên có thể bỏ hợp đồng.”** Sai: giá trị Agile không xóa nghĩa vụ đã ký hoặc thủ tục có thẩm quyền.

**2. “Có hợp đồng cố định nghĩa là không được nhận phản hồi.”** Sai: có thể quan sát, làm rõ và cải tiến trong phạm vi, đồng thời đưa thay đổi vượt quyền qua quy trình.

**3. “Cứ Product Owner đồng ý thì đã sửa được SOW.”** PO có trách nhiệm sản phẩm; quyền sửa SOW/hợp đồng phụ thuộc ủy quyền và quy định.

**4. “Người dùng thử thấy tốt tức đã nghiệm thu pháp lý.”** Sprint Review/usability test không tự thay thế hồ sơ và người ký nghiệm thu.

**5. “Increment Done nghĩa nhà cung cấp được thanh toán ngay.”** Quyền thanh toán và chứng từ theo điều khoản, không theo nhãn Scrum.

**6. “Hợp đồng yêu cầu chức năng nên nhóm không cần định nghĩa acceptance criteria.”** Những ví dụ cụ thể giúp phát hiện hiểu sai và kiểm chứng, miễn giữ ranh giới nghĩa vụ.

**7. “Mọi phản hồi đều là scope creep.”** Có phản hồi phát hiện lỗi hoặc diễn giải mơ hồ đã nằm trong cam kết.

**8. “Mọi phản hồi đều nằm trong hợp đồng vì đang làm cùng sản phẩm.”** Một tích hợp hoặc khả năng mới có thể đòi thay đổi hợp đồng.

**9. “Đổi scope ít hơn nhưng cùng story points là hợp lệ.”** Điểm ước lượng không đại diện quyền thay đổi đầu ra đã ký.

**10. “Hợp đồng cố định giá/thời gian cho phép tự do đổi phạm vi.”** Có thể phạm vi cũng ràng buộc; cần kiểm tra quy định thực.

**11. “Hợp đồng cố định scope thì nên bỏ Sprint Review.”** Phản hồi sớm giúp tránh giao sai; Review không nhất thiết là nghiệm thu hợp đồng.

**12. “Nếu có CR thì Agile đã thất bại.”** Quản lý thay đổi minh bạch có thể là cách cộng tác có trách nhiệm trong bối cảnh ràng buộc.

**13. “Change request chỉ cần ghi trong chat nhóm.”** Thay đổi có hiệu lực cần hình thức và người duyệt theo quyền đã xác định.

**14. “Cứ xây trước và xin thanh toán sau.”** Có thể tạo công việc không được thanh toán hoặc vi phạm quy trình mua sắm.

**15. “Một nút nhỏ chắc không ảnh hưởng hợp đồng.”** Kích thước giao diện không phản ánh quy tắc nghiệp vụ, dữ liệu, an toàn hoặc nghiệm thu.

**16. “Nếu chưa biết điều khoản, cứ giả định là được.”** Phải xác minh với người có thẩm quyền khi tác động thực sự quan trọng.

**17. “Bộ phận procurement là người quyết định ưu tiên mọi PBI.”** Vai trò mua sắm và trách nhiệm Product Owner cần được phân biệt.

**18. “Product Owner không có quyền sửa hợp đồng nên không thể điều hành Product Backlog.”** Có thể phân quyền quản lý backlog trong phạm vi và có đường escalation cho quyết định vượt quyền.

**19. “Trong Scrum, Sprint Goal đạt thì mọi điều khoản hợp đồng đã đạt.”** Sprint Goal là commitment của Sprint Backlog, không phải thủ tục nghiệm thu.

**20. “Có thể gọi PBI chưa đủ test là Done để giữ mốc.”** Definition of Done bảo vệ chất lượng Increment; trong Sprint, chất lượng không được giảm.

**21. “Kiểm thử phân quyền là việc phụ có thể để sau khi người dùng bắt đầu dùng.”** Bảo vệ dữ liệu phải tuân chuẩn áp dụng; không thể tự ý bỏ.

**22. “Đã demo trên production thì phải dùng dữ liệu thật.”** Demo và nghiên cứu cần đúng quyền; dữ liệu giả có thể phù hợp hơn.

**23. “Một Product Backlog cần sao chép y nguyên từng dòng SOW.”** Nên truy vết nghĩa vụ mà vẫn tổ chức công việc theo giá trị và tính thích ứng.

**24. “Traceability cần tách khỏi mọi công cụ phát triển, viết lại thủ công hết.”** Có thể tận dụng bằng chứng CI/test/PR, kiểm tra thêm hình thức pháp lý cần thiết.

**25. “Một thay đổi không làm tăng giá thì không cần phê duyệt.”** Nó vẫn có thể đổi nghĩa vụ, mốc, quyền dữ liệu hoặc điều kiện nghiệm thu.

**26. “Nếu procurement nói không, không còn cách tạo giá trị.”** Có thể tìm lựa chọn trong baseline, cải tiến chất lượng và ghi nhu cầu mới cho đợt sau.

**27. “Mốc thanh toán là lúc duy nhất phải tích hợp.”** Tích hợp sớm có thể giảm rủi ro, bất kể hợp đồng thanh toán theo mốc nào.

**28. “Khách hàng nên được xem mọi thông tin và dữ liệu vì họ là người mua.”** Quyền truy cập thông tin cá nhân/secret vẫn bị giới hạn bởi chính sách và quy định.

**29. “Càng nhiều cuộc họp với khách hàng càng chứng minh cộng tác.”** Chất lượng quyết định và khả năng gỡ vướng quan trọng hơn tần suất họp.

**30. “Thời gian duyệt CR dài là bằng chứng người duyệt kém.”** Có thể do mức rủi ro, tài liệu thiếu, thẩm quyền nhiều cấp hoặc quy định bắt buộc.

**31. “Dự báo throughput là ngày giao chắc chắn.”** Dữ liệu lịch sử có bất định và không thay nghĩa vụ hợp đồng.

**32. “Đưa rủi ro trễ mốc lên sớm là yếu kém.”** Cảnh báo sớm giúp các bên còn phương án hợp lệ và giảm bất ngờ.

**33. “Nhà cung cấp phải đáp ứng mọi góp ý để giữ quan hệ.”** Cộng tác đúng nghĩa gồm nói rõ rủi ro, giá trị, phạm vi và quyền, không nhận cam kết không có căn cứ.

**34. “Người mua sắm có thể bỏ qua quy tắc cạnh tranh để nhận ý kiến chuyên gia quen biết.”** Giai đoạn mua sắm phải tuân thủ kênh trao đổi và công bằng áp dụng, không tự mở ngoại lệ.

**35. “Hợp đồng bảo hành là giấy phép để trì hoãn mọi lỗi tới sau nghiệm thu.”** Phân loại defect, chất lượng bắt buộc, bảo hành và xử lý sự cố phải dựa trên nghĩa vụ và mức rủi ro thực, không giấu lỗi.

**36. “Nếu một buổi Review vui vẻ, khách hàng sẽ không tranh chấp về sau.”** Cần lưu quyết định có thẩm quyền và bằng chứng đạt tiêu chí, không thay bằng cảm giác đồng thuận.

## 28. Bài tập tình huống A: đổi đầu ra khi hợp đồng sắp tới hạn

Một doanh nghiệp mua nền tảng học trực tuyến với **thời hạn 12 tuần, giá cố định và sáu đầu ra H-01 đến H-06** như mục 24. Cuối tuần thứ tư, một buổi quan sát người học cho thấy thông báo đăng ký khó hiểu. Đại diện nghiệp vụ khách hàng muốn:

1. Sửa thông báo và đường dẫn mở bài ngay.
2. Bỏ báo cáo quản trị H-04 để làm dashboard gợi ý khóa học.
3. Bổ sung email xác nhận gửi tới người học.
4. Gọi mọi chức năng là “đã nghiệm thu từng phần” sau mỗi Sprint Review.

Thông tin hiện tại:

- Contract manager chưa xác nhận quyền hoán đổi H-04.
- Có lỗi timeout khiến giao diện báo thành công giả.
- Nhóm có thể tạo prototype không dùng dữ liệu thật trong môi trường được phép.
- Hợp đồng có thủ tục thay đổi chính thức nhưng **chưa cung cấp thời hạn phê duyệt cố định**.
- DoD sản phẩm bao gồm kiểm thử tích hợp và những kiểm tra quyền dữ liệu áp dụng.

### Câu hỏi

1. Phân loại bốn đề nghị và lỗi timeout thành **làm rõ/lỗi/cải tiến trong phạm vi/thay đổi cần duyệt**; nêu điều còn cần xác minh.
2. Những việc nào Scrum Team có thể ưu tiên **ngay** mà không tự sửa baseline?
3. Vì sao không được tự bỏ H-04 chỉ vì PO và người dùng thích dashboard gợi ý hơn?
4. Sprint Review có ý nghĩa gì nếu khách hàng chỉ nghiệm thu chính thức theo mốc?
5. Ai cần tham gia quyết định thay thế H-04 và tác động có thể gồm những gì?
6. Nếu chỉ có hai tuần tới mốc trung gian, cần báo rủi ro thế nào để không tạo sự chắc chắn giả?
7. Nêu ví dụ **Gherkin** hoặc kiểm thử cần cho lỗi timeout.
8. Nếu dashboard mới được duyệt, những thông tin/tài liệu nào cần cập nhật?
9. Nếu dashboard bị từ chối, nhóm có còn cách học về nhu cầu người dùng không?
10. Viết thông báo ngắn cho phía khách hàng, tách phản hồi, trạng thái Done và quyết định phạm vi.

### Gợi ý lời giải

**Câu 1:** Lỗi timeout có thể là defect đối với hành vi xác nhận đáng tin và DoD; phải sửa/kiểm chứng theo trách nhiệm. Sửa thông báo/đường dẫn có thể thuộc làm rõ/cải tiến trong H-01/H-02, cần đối chiếu tiêu chí. Hoán đổi H-04 có khả năng thay đầu ra đã ký, cần change control. Email có thể là mở rộng, trừ khi baseline đã bao gồm. Nghiệm thu mỗi Sprint là thay đổi cơ chế nếu hợp đồng chưa quy định, cần xác nhận người có quyền.

**Câu 2:** Tái hiện và xử lý timeout, kiểm thử phân quyền, làm rõ hành vi đăng ký/mở bài, chia lát cắt theo giá trị và tổ chức Review lấy phản hồi trong phạm vi được phép. Nếu prototype được cho phép, có thể thử để hiểu nhu cầu, nhưng không cam kết triển khai ngoài phạm vi.

**Câu 3:** PO có trách nhiệm tối đa hóa giá trị và quản lý backlog, nhưng không mặc nhiên có quyền bỏ deliverable ràng buộc hợp đồng. Không được biến quyền ưu tiên công việc thành quyền thay nghĩa vụ đã ký.

**Câu 4:** Review kiểm tra Increment, học về người dùng và thích ứng Product Backlog; nó **không tự bằng nghiệm thu pháp lý**. Những chứng cứ có thể hỗ trợ thủ tục nghiệm thu sau này nếu phù hợp.

**Câu 5:** Cần Product Owner/nghiệp vụ, Developers/nhà cung cấp để đánh giá và contract manager/procurement/pháp chế/sponsor theo quyền. Tác động có thể gồm giá, mốc, test, dữ liệu, vận hành, điều kiện nghiệm thu và quyền sử dụng kết quả.

**Câu 6:** Báo phần đã đạt DoD và phần còn thiếu, blocker, giả định, các lựa chọn trong baseline hoặc cần CR. Không đưa “90% sẽ đúng hạn” nếu không có cơ sở dữ liệu và mô hình phù hợp.

**Câu 7:** Khi API không xác nhận đã lưu, UI **không được báo chắc chắn thành công** và cần cách kiểm tra/truy vấn trạng thái. Phải kiểm tra tình huống timeout với dữ liệu thử thích hợp, không chỉ unit test trả thành công.

**Câu 8:** Văn bản thay đổi và ngày hiệu lực, baseline H-04, tiêu chí nghiệm thu, mốc/giá nếu tác động, backlog, kế hoạch tích hợp, kiểm thử, tài liệu và trách nhiệm theo quyền.

**Câu 9:** Có thể ghi nhu cầu tương lai, làm prototype trong quyền, thử khả năng sử dụng của báo cáo hiện tại hoặc cải thiện phần phạm vi chưa bị ràng buộc; không tự thay đổi H-04.

**Câu 10 — Thông báo minh họa:**

> “Buổi quan sát cho thấy người học chưa hiểu trạng thái đăng ký và khó tìm bài đầu; nhóm đang đối chiếu cải tiến này với H-01/H-02. Luồng timeout còn chưa đạt DoD nên chưa được coi là phần Increment hoàn tất; Developers đang ưu tiên sửa và kiểm thử. Đề nghị thay H-04 bằng dashboard mới, thêm email và đổi cơ chế nghiệm thu đang cần xác nhận phạm vi/thẩm quyền; hiện chưa có quyết định sửa baseline, vì vậy chúng tôi chưa cam kết giao những thay đổi ấy. Nhóm sẽ gửi các lựa chọn và tác động để bên có thẩm quyền quyết định.”

## 29. Bài tập tình huống B: mua sắm cạnh tranh và phản hồi người dùng

Một tổ chức đang **chưa trao thầu** dự án nền tảng học trực tuyến. Hồ sơ mời thầu dự kiến yêu cầu mỗi người học phải nhận email sau đăng ký, dù khảo sát ban đầu cho thấy nhiều người học muốn xác nhận trực tiếp trong ứng dụng.

Một nhà cung cấp đề nghị có buổi trao đổi riêng với nhóm nghiệp vụ để:

- Trình diễn prototype của họ.
- Đề xuất bỏ email để giảm giá.
- Nhận trước thông tin về tiêu chí đánh giá chưa công bố.

Bộ phận mua sắm lo rằng việc trao đổi riêng như vậy **không phù hợp quy trình cạnh tranh**.

### Câu hỏi

1. Vì sao đề nghị của nhà cung cấp có rủi ro, dù có thể giúp hiểu trải nghiệm người dùng?
2. Làm thế nào để bên mua nhận phản hồi/nghiên cứu nhu cầu mà vẫn bảo đảm kênh và quyền phù hợp?
3. Phân biệt mục tiêu outcome với giải pháp email đang giả định.
4. Nêu ba câu hỏi nên được làm rõ **qua kênh được phép** trước khi chốt yêu cầu.
5. Nếu email là nghĩa vụ bắt buộc theo quy định hiện có, có thể tự bỏ không?
6. Nếu hồ sơ đã được ban hành và có thay đổi, cần lưu ý gì trước khi công bố/áp dụng?
7. Bên bán nên phản hồi thế nào khi chưa có API/môi trường tích hợp thật để ước lượng?
8. Nếu hợp đồng đã ký sau đó, Product Owner có tự đổi email thành xác nhận trong app không?

### Gợi ý lời giải

**Câu 1:** Trao đổi riêng có thể tạo lợi thế thông tin, vượt kênh chính thức hoặc xung đột với quy tắc mua sắm. Mục đích học sản phẩm không tự làm hợp pháp mọi kênh tiếp xúc.

**Câu 2:** Dùng khảo sát/nghiên cứu người dùng do bên mua tổ chức theo quyền; công bố nội dung yêu cầu, câu hỏi–đáp hoặc hoạt động tương tác thị trường theo quy trình được phép. Nếu cần trình diễn, xác minh cách mời, đánh giá và chia sẻ thông tin công bằng.

**Câu 3:** Outcome có thể là “người học nhận biết trạng thái đăng ký và bắt đầu học đúng”, còn email là một **giải pháp cụ thể**. Có thể tồn tại nhiều cách đạt outcome; khả năng thay email phụ thuộc yêu cầu bắt buộc.

**Câu 4:** Ví dụ: Email là yêu cầu pháp lý/nghiệp vụ bắt buộc hay giải pháp đề xuất? Tiêu chí kiểm chứng “người học đã được thông báo” là gì? Khi email thất bại, trạng thái đăng ký và nghĩa vụ thông báo xử lý thế nào?

**Câu 5:** Không. Phải tuân nghĩa vụ áp dụng; nếu muốn thay cần thủ tục và thẩm quyền thích hợp, có thể không có lựa chọn sửa.

**Câu 6:** Quy trình sửa/công bố hồ sơ và đối xử với nhà thầu phải theo cơ chế áp dụng; không tự gửi thông tin quan trọng cho một bên. Bài này không thay tư vấn pháp lý hoặc mua sắm.

**Câu 7:** Nêu giả định, giới hạn thông tin, rủi ro tích hợp và điều kiện kiểm chứng; không tuyên bố chắc chắn chỉ dựa trên prototype.

**Câu 8:** Không mặc nhiên. PO có thể ưu tiên, làm rõ và đề xuất, nhưng thay deliverable đã ký cần xem hợp đồng và quyền phê duyệt.

## 30. Bài tập tình huống C: mốc đã gần, chất lượng còn thiếu

Trong Sprint cuối trước mốc nghiệm thu, hệ thống đăng ký đã chạy được happy path. Tuy nhiên:

| Hạng mục | Tình trạng minh họa | Rủi ro |
| --- | --- | --- |
| Đăng ký bình thường | Test cơ bản đạt | Chưa đủ đánh giá toàn luồng |
| Hai yêu cầu gần đồng thời | Integration test thất bại | Có thể tạo dữ liệu Active trùng |
| Timeout khi lưu | UI báo thành công dù chưa chắc đã ghi | Người học hiểu sai trạng thái |
| Quyền tài khoản | Còn lỗi cho phép xem bản ghi khác tài khoản | Có nguy cơ lộ dữ liệu |
| Báo cáo quản trị | Chưa hoàn tất bộ test theo mốc | Không đủ bằng chứng nghiệm thu |
| Hồ sơ bàn giao | Có phần đang soạn | Chưa đáp ứng toàn bộ yêu cầu theo giả định |

Đại diện kinh doanh đề nghị “ký nghiệm thu nội bộ trước rồi sửa trong bảo hành”. Nhà cung cấp lo rằng nếu không ký thì thanh toán bị chậm.

### Câu hỏi

1. Có nên gọi toàn bộ phần mềm là Done chỉ vì happy path đã hoạt động?
2. Những rủi ro nào cần xử lý theo yêu cầu an toàn trước khi dùng dữ liệu thật?
3. Nếu khách hàng muốn chấp nhận rủi ro, ai có thể quyết định và giới hạn nào vẫn áp dụng?
4. Scrum Team nên trình bày gì tại Sprint Review?
5. Nếu hợp đồng có quy trình nghiệm thu có điều kiện hoặc xử lý sai lệch, ai phải xác minh cách áp dụng?
6. Có thể đưa một phần Increment Done vào sử dụng trước không?
7. Nêu ba điều cần có trong báo cáo rủi ro mốc.
8. Vì sao nên ghi rõ sự khác nhau giữa “đã khắc phục”, “đạt DoD” và “đã nghiệm thu”?

### Gợi ý lời giải

**Câu 1:** Không. Nếu chưa đạt các tiêu chuẩn DoD áp dụng, công việc chưa là Increment Done. Happy path không chứng minh phân quyền, dữ liệu hoặc tích hợp đúng.

**Câu 2:** Phân quyền tài khoản và tính nhất quán dữ liệu cần ưu tiên theo rủi ro; không dùng dữ liệu người học thật theo cách chưa được phép. Các biện pháp ứng cứu nếu có tác động đang diễn ra cần được thực hiện đúng quyền.

**Câu 3:** Người có quyền theo hợp đồng, bảo mật, quyền dữ liệu và quản trị có thể quyết định trong phạm vi được phép. Không ai có thể tự ý miễn nghĩa vụ pháp lý/chuẩn bắt buộc chỉ bằng lời đồng ý miệng; cần xem điều khoản cụ thể.

**Câu 4:** Minh bạch phần nào đạt DoD, phần nào đang thử, lỗi và tác động, phương án cải thiện và thông tin cần để Product Backlog thích ứng. Không giới thiệu phần chưa đạt DoD như Increment hoàn tất.

**Câu 5:** Contract manager, procurement/pháp chế và người ký nghiệm thu có quyền theo quy định; không tự suy diễn “nghiệm thu có điều kiện” hoặc sửa trong bảo hành là hợp lệ.

**Câu 6:** Chỉ khi phần ấy **đã đạt DoD và điều kiện phát hành/nghiệm thu liên quan cho phép**; cần xét phụ thuộc và rủi ro gây hiểu lầm. Không dùng feature flag để che một lỗi an toàn.

**Câu 7:** Bằng chứng chưa đạt, phạm vi/người dùng có thể bị ảnh hưởng, dự báo và giả định, phương án xử lý cùng quyền quyết định và mốc kiểm tra lại.

**Câu 8:** “Đã khắc phục” là hành động kỹ thuật có thể đang chờ kiểm chứng; “đạt DoD” là ngưỡng Increment theo Scrum; “đã nghiệm thu” là trạng thái quyết định theo hợp đồng. Trộn chúng dễ gây hiểu lầm và tranh chấp.

## 31. Mẫu thực hành: ghi một phản hồi và quyết định đúng thẩm quyền

Nhóm có thể dùng một **Decision & Change Brief** ngắn. Đây là mẫu điều phối công việc, **không mặc nhiên thay biểu mẫu pháp lý của tổ chức**.

~~~text
Mã bản ghi:
  ...

Nguồn phản hồi / ngày:
  ...

Người dùng hoặc bộ phận bị ảnh hưởng:
  ...

Vấn đề quan sát và bằng chứng:
  ...

Outcome cần cải thiện:
  ...

Nghĩa vụ / baseline / tiêu chí liên quan:
  ...

Phân loại sơ bộ:
  [ ] Lỗi so với nghĩa vụ hiện có
  [ ] Làm rõ hoặc thiết kế trong phạm vi
  [ ] Điều chỉnh thứ tự thực hiện
  [ ] Thay đổi phạm vi/giá/mốc/nghiệm thu
  [ ] Chưa rõ, cần xác minh

Những phương án có thể chọn:
  A. Giữ nguyên nghĩa vụ, cải thiện cách thực hiện:
     ...
  B. Thay đổi trong phạm vi đã được phép:
     ...
  C. Đề xuất change request chính thức:
     ...

Tác động ước lượng (kèm giả định):
  Giá/nguồn lực:
  Ngày/mốc:
  Chất lượng và DoD:
  Bảo mật/quyền dữ liệu:
  Phụ thuộc:
  Nghiệm thu/thanh toán:

Người có quyền quyết định / cần tham gia:
  ...

Trạng thái:
  [ ] Đang thu thập thông tin
  [ ] Chờ xác nhận phạm vi
  [ ] Chờ quyết định chính thức
  [ ] Được chấp thuận theo tài liệu có hiệu lực
  [ ] Không chấp thuận
  [ ] Hoàn tất và đã kiểm chứng

Quyết định, căn cứ, ngày hiệu lực:
  ...

PBI / bằng chứng / tài liệu cần cập nhật:
  ...

Người theo dõi và mốc xem lại:
  ...
~~~

### 31.1. Ví dụ điền ngắn cho yêu cầu email

> **Phản hồi:** Người học muốn nhận email xác nhận.  
> **Vấn đề:** Trong app, người học chưa chắc đã đăng ký xong và khó tìm lại trạng thái.  
> **Baseline:** H-01 quy định xác nhận trạng thái; chưa thấy nghĩa vụ email rõ ràng trong thông tin đang xem.  
> **Phân loại:** Chưa xác minh phạm vi; có thể là yêu cầu bổ sung.  
> **Phương án A:** Làm rõ xác nhận trong app theo H-01 và kiểm thử lỗi timeout.  
> **Phương án B:** Khảo sát email với dữ liệu thử trong quyền đã cho phép.  
> **Phương án C:** Đề xuất thêm email, phân tích tác động và xin duyệt theo hợp đồng.  
> **Trạng thái:** Chưa cam kết triển khai email, chờ người có quyền xác nhận.  
> **Guardrail:** Không dùng dữ liệu người học ngoài quyền; DoD và quyền tài khoản phải được bảo vệ.

### 31.2. Một agenda ngắn cho workshop khách hàng–nhà cung cấp

| Khoảng tham khảo | Nội dung | Kết quả mong đợi |
| --- | --- | --- |
| 0–10 phút | Hành vi người dùng và vấn đề được quan sát | Thống nhất dữ kiện, chưa vội chọn giải pháp |
| 10–20 phút | Đối chiếu nghĩa vụ, acceptance criteria và DoD | Rõ phần trong phạm vi và phần chưa chắc |
| 20–30 phút | Các phương án và tác động | Có lựa chọn với giá/mốc/chất lượng/rủi ro |
| 30–40 phút | Phân quyền và bước quyết định | Ai được làm ngay, việc nào cần CR |
| 40–45 phút | Tóm tắt và mốc kiểm tra lại | Không còn cam kết miệng mơ hồ |

Thời lượng là **ví dụ**, không phải một sự kiện Scrum bắt buộc. Với một sự cố an toàn đang xảy ra, cần ứng cứu ngay, không chờ buổi workshop.

### 31.3. Working agreement gợi ý

> “Chúng tôi dành thời gian xem Increment và lắng nghe người dùng thường xuyên. Mọi phản hồi được ghi thành vấn đề và lựa chọn, không tự biến thành nghĩa vụ. Product Owner và Developers làm rõ và ưu tiên trong phạm vi quyền được trao; các thay đổi ảnh hưởng hợp đồng, ngân sách, nghiệm thu hoặc quyền dữ liệu được trình đúng thẩm quyền. Chúng tôi không gọi phần chưa đạt DoD là Done, không trình demo như nghiệm thu pháp lý và không triển khai ngoài quyền đã được duyệt. Khi có rủi ro trễ mốc hoặc chất lượng, các bên thông báo sớm kèm bằng chứng và phương án.”

## 32. Checklist cộng tác với khách hàng trong cơ chế mua sắm cứng

### A. Hiểu ràng buộc trước khi quyết định

1. **Nghĩa vụ:** Nhóm biết bộ tài liệu nào thực sự ràng buộc không?
2. **Baseline:** Đã xác định phạm vi, giá, thời hạn, chất lượng và điều kiện nghiệm thu?
3. **Thứ tự tài liệu:** Nếu mâu thuẫn, đã nhờ người có quyền làm rõ thay vì tự suy đoán?
4. **Quyền:** Ai được làm rõ yêu cầu, ưu tiên backlog, sửa hợp đồng và ký nghiệm thu?
5. **Mua sắm:** Kênh trao đổi, tính công bằng và hồ sơ có được tuân theo quy trình áp dụng?
6. **Dữ liệu:** Quyền truy cập, ghi hình, lưu thông tin người dùng và công cụ cộng tác đã rõ?

### B. Cộng tác và phát hiện vấn đề sớm

7. **Người dùng:** Có tiếp cận được người thực sự sử dụng trong phạm vi được phép?
8. **Outcome:** Cuộc trao đổi tập trung vào kết quả người dùng, không chỉ danh sách màn hình?
9. **User story:** Có ví dụ thành công, lỗi và tình huống biên để làm rõ?
10. **Review:** Có nhìn phần mềm hoạt động thường xuyên, không chờ cuối dự án?
11. **Phân biệt:** Có nêu rõ prototype, item chưa Done và Increment đã Done?
12. **Phản hồi:** Nhóm lưu bằng chứng thay vì chỉ ghi yêu cầu giải pháp?
13. **Không tự hứa:** Góp ý được ghi mà không tự trở thành cam kết giao hàng?

### C. Phân loại và quyết định thay đổi

14. **Loại phản hồi:** Lỗi, làm rõ, thiết kế trong phạm vi hay thay đổi nghĩa vụ?
15. **Tác động:** Đã xem giá, mốc, chất lượng, dữ liệu, phụ thuộc và nghiệm thu?
16. **Phương án:** Có lựa chọn tiếp tục trong baseline trước khi yêu cầu sửa nghĩa vụ?
17. **Change control:** Việc vượt quyền có được chuyển đúng quy trình và người có quyền?
18. **Thời điểm:** Chưa thực hiện nghĩa vụ bổ sung trước khi được phép?
19. **Quyết định:** Có văn bản/hồ sơ phù hợp và ngày hiệu lực?
20. **Truy vết:** Baseline, Product Backlog, test và tài liệu đã được đồng bộ sau quyết định?
21. **Bị từ chối:** Nhóm có quay về phương án hợp lệ mà không giấu nhu cầu người dùng?

### D. Chất lượng, giao hàng và nghiệm thu

22. **DoD:** Mọi phần được gọi Done có đạt tiêu chuẩn chất lượng?
23. **An toàn:** Bảo mật, quyền tài khoản, dữ liệu và các nghĩa vụ bắt buộc được giữ?
24. **Tích hợp:** Có kiểm thử UI/API/data và trường hợp lỗi phù hợp?
25. **Release:** Điều kiện phát hành được phân biệt với DoD?
26. **Nghiệm thu:** Người ký và bằng chứng theo hợp đồng đã xác định?
27. **Thanh toán:** Không suy quyền thanh toán từ demo hoặc nhãn Done?
28. **Mốc:** Có nhìn rủi ro đủ sớm để chuẩn bị lựa chọn?
29. **Dự báo:** Có phân biệt mục tiêu, giả định, dự báo và cam kết?

### E. Đo và cải tiến mối quan hệ

30. **Blocked time:** Nhóm biết phụ thuộc về kỹ thuật, quyền và hợp đồng đang gây chờ ở đâu?
31. **Quyết định:** Thời gian CR chờ có được xem theo mức phức tạp và quyền?
32. **Làm lại:** Có đo những sai lệch do hiểu yêu cầu muộn?
33. **Outcome:** Giao đủ đầu ra có gắn với trải nghiệm người dùng?
34. **Guardrail:** Tốc độ không được cải thiện bằng cách hạ DoD hoặc che lỗi?
35. **Minh bạch:** Có thể xem trạng thái nghĩa vụ mà không biến backlog thành bureaucracy?
36. **Phản hồi:** Người dùng, Product Owner, Developers và người quản trị hợp đồng có hiểu quyết định tiếp theo?
37. **Cải tiến:** Nhóm có sửa được hàng chờ/phụ thuộc hợp pháp thay vì lặp lại cùng rào cản?

## 33. Tổng kết: cộng tác để học nhanh, quản trị để cam kết đúng

Agile không chỉ phù hợp với những tổ chức có hợp đồng linh hoạt. Trong môi trường mua sắm và hợp đồng cứng, các giá trị Agile vẫn giúp đội **phát hiện rủi ro sớm, hiểu người dùng, tích hợp phần mềm thường xuyên và tránh làm lại**. Nhưng khả năng thích ứng phải được thực hiện **đúng phạm vi, đúng thẩm quyền và minh bạch với nghĩa vụ thực**.

| Cách làm dễ thất bại | Cách phối hợp có trách nhiệm |
| --- | --- |
| Chỉ đọc hợp đồng, không gặp người dùng đến ngày nghiệm thu | Dùng Sprint Review/prototype/khảo sát theo quyền để nhận phản hồi sớm |
| Tự thay deliverable vì nghĩ nó có giá trị hơn | Trình tác động và xin thay đổi theo quy trình khi cần |
| Mọi góp ý đều bị từ chối là ngoài phạm vi | Phân loại lỗi, làm rõ, cải tiến trong quyền và thay đổi nghĩa vụ |
| PO đồng ý miệng được xem là hợp đồng đã đổi | Làm rõ quyền Product Backlog và quyền ký kết riêng |
| Nhiều technical tasks xong được báo là hoàn tất sản phẩm | Kiểm chứng Increment theo DoD và đối chiếu nghĩa vụ |
| Sprint Review bị coi là biên bản nghiệm thu | Phân biệt kiểm tra sản phẩm và thủ tục nghiệm thu hợp đồng |
| Chờ mốc cuối mới kiểm thử hợp đồng tích hợp | Tạo lát cắt dọc, CI, acceptance tests và bằng chứng thường xuyên |
| Giấu rủi ro trễ mốc hoặc lỗi để giữ quan hệ | Báo sớm bằng sự kiện, dự báo, giả định và các phương án |
| Viết mọi quyết định vào chat rồi không theo dõi | Ghi quyền, quyết định, baseline liên quan, ngày hiệu lực và người thực hiện |
| Coi procurement là kẻ cản trở | Cùng tìm cách giảm chờ trong các quy tắc phải tuân thủ |
| Tối ưu số CR đóng hoặc số story points | Đo thời gian ra quyết định, chất lượng, rủi ro và outcome người dùng |
| Hạ DoD hoặc bỏ an toàn để kịp nghiệm thu | Giữ chất lượng và đưa những đánh đổi không còn khả thi lên đúng thẩm quyền |

**Ghi nhớ:** Vòng làm việc hữu ích là **Lắng nghe khách hàng → Quan sát hành vi thực → Làm rõ nhu cầu và nghĩa vụ → Phân loại thay đổi theo phạm vi/quyền → Giao phần giá trị nhỏ đạt DoD → Thu phản hồi và bằng chứng → Quyết định/điều chỉnh hợp lệ → Tiếp tục cải tiến**. Trong **AGILE_DEVELOPMENT**, Scrum giữ Product Goal, Product Backlog, Sprint Goal và Increment/DoD rõ ràng; Kanban giúp nhìn WIP và hàng chờ quyết định; XP hỗ trợ kiểm thử, tích hợp và refactoring để sửa sớm; Lean giúp giảm làm lại và bàn giao không tạo giá trị. **Cộng tác với khách hàng không có nghĩa bỏ thương lượng hoặc thủ tục hợp đồng; nó có nghĩa dùng hiểu biết chung và bằng chứng để các bên đưa ra cam kết đúng, thay đổi có thẩm quyền và giao sản phẩm đáng tin cậy.**
