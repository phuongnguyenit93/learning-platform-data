# Giải quyết khoảng trống trách nhiệm khi tổ chức có vai trò quản lý dự án

Một công ty đang chuyển từ mô hình dự án truyền thống sang Scrum. Tổ chức vẫn có **Project Manager (PM – người quản lý dự án)** chịu trách nhiệm theo dõi hợp đồng, ngân sách, phụ thuộc giữa các phòng ban và báo cáo cho ban điều hành. Đồng thời, nhóm sản phẩm có **Product Owner**, **Scrum Master** và **Developers**. Chẳng bao lâu, những câu hỏi xuất hiện:

- Ai quyết định chức năng nào phải làm trước nếu khách hàng yêu cầu thêm trong Sprint?
- PM có được giao story trực tiếp cho từng lập trình viên không?
- Nếu nhà cung cấp chậm bàn giao API, ai chịu trách nhiệm xử lý?
- Nếu dự kiến phát hành bị trễ, ai có quyền thương lượng ngày và phạm vi?
- Một hạng mục chưa qua kiểm thử có thể được PM xác nhận là “hoàn thành” để báo cáo tiến độ không?

Chỉ trả lời **“Scrum không có vai trò Project Manager”** là chưa đủ. Điều đó đúng về cấu trúc Scrum, nhưng không làm biến mất các nhu cầu quản trị ngân sách, hợp đồng, nguồn lực tổ chức, pháp lý hay phối hợp liên nhóm. Ngược lại, giữ tên Scrum trong khi để PM chỉ đạo mọi quyết định sản phẩm và kỹ thuật cũng không tạo ra Scrum thực chất.

Bài học thuộc chương **Trách nhiệm Scrum** của module **AGILE_DEVELOPMENT**. Trọng tâm là **làm rõ quyền quyết định, trách nhiệm giải trình và cơ chế phối hợp**, giúp nhóm giao phần mềm tăng dần, nhận phản hồi sớm và cải tiến liên tục. User story, Product Backlog, Sprint Goal, Kanban, XP và các chỉ số dòng công việc sẽ được dùng để minh họa cách làm minh bạch mà không thêm các tầng phê duyệt vô ích.

Sau bài này, bạn có thể:

1. Phân biệt ba **accountabilities** được Scrum định nghĩa với những nhiệm vụ quản trị dự án vẫn tồn tại trong tổ chức.
2. Nhận diện những **khoảng trống, chồng lấn hoặc xung đột quyền quyết định** thường xuất hiện khi có PM.
3. Thiết lập bảng phân định quyền quyết định cho Product Backlog, Sprint, chất lượng, phát hành, ngân sách và phụ thuộc.
4. Phối hợp giữa PM, Product Owner, Scrum Master, Developers và các bộ phận chuyên trách mà không làm suy yếu tính tự quản của Scrum Team.
5. Xử lý tình huống thực tế như đổi phạm vi giữa Sprint, deadline cố định, sự cố chất lượng và phụ thuộc bên ngoài.
6. Dùng kết quả sản phẩm cùng dữ liệu dòng công việc để báo cáo tình trạng trung thực, thay vì biến Scrum thành hệ thống giao việc cá nhân.

## 1. Hiểu đúng “khoảng trống trách nhiệm” trong chuyển đổi sang Scrum

**Khoảng trống trách nhiệm** xuất hiện khi một việc cần thiết không có người hoặc cơ chế chịu trách nhiệm rõ ràng. **Chồng lấn trách nhiệm** xảy ra khi nhiều người tưởng mình có quyền quyết định cùng một vấn đề theo những cách mâu thuẫn.

Ví dụ:

| Tình huống | Dấu hiệu | Hệ quả có thể xảy ra |
| --- | --- | --- |
| Không ai xác nhận phụ thuộc API với đối tác | Developers chờ, PM cho rằng Scrum Master sẽ lo, Scrum Master cho rằng PM đã ký hợp đồng. | Story bị chặn, Sprint Goal gặp rủi ro. |
| PM và Product Owner sắp backlog theo hai danh sách khác nhau | PM ra lệnh làm tính năng X, PO ưu tiên xử lý lỗi Y. | Developers nhận chỉ đạo mâu thuẫn, khó tập trung. |
| PM chấp nhận công việc chưa đạt DoD để giữ mốc | Báo cáo “100% hoàn thành” nhưng kiểm thử tích hợp còn dang dở. | Tiến độ sai lệch và rủi ro phát hành tăng. |
| Scrum Master bị xem là thư ký báo cáo | Chỉ tổng hợp giờ công, không có cơ hội hỗ trợ gỡ trở ngại hoặc cải thiện Scrum. | Sự kiện Scrum trở thành hình thức. |
| Không ai có quyền quyết định mở release | Increment đã Done nhưng chưa có đầu mối đánh giá vận hành và điều kiện phát hành. | Chờ đợi kéo dài dù phần mềm có thể sử dụng. |

Bảng này không khẳng định mọi tổ chức đều gặp những vấn đề đó. Nó cho thấy vì sao **bảng tên chức danh** chưa đủ để tổ chức phối hợp hiệu quả.

### Phân biệt ba loại trách nhiệm

- **Accountability – trách nhiệm giải trình:** người hoặc tập thể chịu trách nhiệm cuối cùng về một kết quả, dù có thể ủy quyền thực hiện một phần công việc.
- **Responsibility – trách nhiệm thực hiện:** người thực hiện hành động hoặc cung cấp kết quả cụ thể.
- **Authority – thẩm quyền quyết định:** quyền lựa chọn hoặc phê duyệt trong một phạm vi xác định.

Một người có thể **thực hiện** nhiệm vụ mà không có quyền quyết định ưu tiên của toàn sản phẩm; một người có thể **chịu trách nhiệm giải trình** về kết quả dù không tự viết code. Khi có PM, việc cần làm là làm rõ cả ba tầng, không chỉ hỏi “ai làm task này”.

## 2. Scrum chính thức định nghĩa những trách nhiệm nào?

Theo cấu trúc của **Scrum Guide 2020**, Scrum Team có ba **accountabilities**: **Product Owner**, **Scrum Master** và **Developers**. Scrum không định nghĩa một accountability riêng mang tên **Project Manager**.

Scrum Team là một đơn vị nhỏ, **liên chức năng (cross-functional)** và **tự quản (self-managing)**; không có các nhóm con hay thứ bậc bên trong Scrum Team theo cấu trúc Scrum. Nhóm cùng tập trung vào Product Goal và chịu trách nhiệm cho những hoạt động liên quan đến sản phẩm trong phạm vi cần thiết.

Điều này không đồng nghĩa mọi người có kỹ năng giống nhau hay tổ chức không còn quản lý nhân sự. Nó có nghĩa **cách Scrum Team chọn ai làm gì, khi nào và như thế nào** không nên bị một cấp chỉ đạo công việc bên trong áp đặt thay cho khả năng tự quản đã xác định.

### 2.1. Product Owner: tối đa hóa giá trị sản phẩm

**Product Owner (PO)** chịu trách nhiệm tối đa hóa giá trị sản phẩm có được từ công việc của Scrum Team và bảo đảm **Product Backlog được quản lý hiệu quả**. Những nội dung này gồm:

- Phát triển và truyền đạt rõ Product Goal.
- Tạo và truyền đạt rõ các Product Backlog Items.
- **Sắp thứ tự Product Backlog Items**.
- Bảo đảm Product Backlog minh bạch, dễ nhìn thấy và được hiểu đúng.

PO có thể ủy quyền người khác thực hiện những hoạt động cụ thể, **nhưng vẫn giữ trách nhiệm giải trình**. Một tổ chức nên tôn trọng các quyết định của PO về nội dung Product Backlog; không tạo một danh sách ưu tiên thứ hai từ PM rồi buộc Developers phục tùng cả hai.

PO là **một người**, không phải một ủy ban. PO cần lắng nghe các bên liên quan, còn ý kiến và dữ liệu từ PM có thể rất quan trọng khi sản phẩm nằm trong dự án có hợp đồng và ngân sách.

### 2.2. Developers: tạo Increment và tự lập kế hoạch thực hiện

**Developers** là những người trong Scrum Team cam kết tạo ra bất kỳ khía cạnh nào của **Increment có thể sử dụng** trong mỗi Sprint. Họ chịu trách nhiệm:

- Tạo kế hoạch cho Sprint, tức **Sprint Backlog**.
- Bảo đảm chất lượng bằng cách tuân thủ **Definition of Done (DoD)**.
- Thích ứng kế hoạch hằng ngày để hướng tới **Sprint Goal**.
- Giữ nhau có trách nhiệm với tư cách những người làm việc chuyên nghiệp.

“Developers” trong Scrum là tên accountability, **không chỉ người lập trình**. Thành viên có chuyên môn kiểm thử, phân tích, thiết kế hay vận hành sản phẩm cũng có thể là Developers theo cách tổ chức nhóm.

Developers chọn cách thực hiện, chia nhỏ công việc và phối hợp chuyên môn. Một PM không nên sử dụng lịch giao việc chi tiết để thay Developers quyết định ai làm từng task trong Sprint.

### 2.3. Scrum Master: hiệu quả và việc sử dụng Scrum đúng nghĩa

**Scrum Master (SM)** chịu trách nhiệm thiết lập Scrum như được định nghĩa trong Scrum Guide và chịu trách nhiệm về **hiệu quả của Scrum Team**. Điều này có thể bao gồm:

- Hướng dẫn các thành viên hiểu và thực hiện Scrum.
- Hỗ trợ Scrum Team cải thiện tính tự quản và liên chức năng.
- Hỗ trợ tập trung vào những Increment có giá trị, đáp ứng DoD.
- **Làm cho trở ngại được tháo gỡ** (*causing the removal of impediments*).
- Giúp các sự kiện Scrum diễn ra hiệu quả và trong timebox.
- Hỗ trợ PO với các kỹ thuật xác định Product Goal, quản lý Product Backlog và cộng tác với các bên liên quan.
- Hỗ trợ tổ chức hiểu và áp dụng Scrum, giảm rào cản giữa bên liên quan và Scrum Team.

SM **không mặc nhiên là PM**, không phải chủ sở hữu backlog, không phải quản lý trực tiếp Developers và cũng không bắt buộc **tự xử lý tất cả** trở ngại. “Làm cho trở ngại được tháo gỡ” có thể là kết nối đúng người có thẩm quyền, thúc đẩy phối hợp và cải tiến hệ thống.

### Bảng phân biệt nhanh

| Accountability Scrum | Kết quả phải bảo vệ | Không nên bị biến thành |
| --- | --- | --- |
| **Product Owner** | Giá trị sản phẩm, Product Goal và Product Backlog hiệu quả. | Người nhận danh sách tính năng cố định từ PM và chỉ nhập ticket. |
| **Developers** | Sprint Backlog, Increment đạt DoD, thích ứng kế hoạch hướng Sprint Goal. | Các cá nhân nhận task độc lập từ PM, không có quyền phối hợp cách làm. |
| **Scrum Master** | Scrum được hiểu, áp dụng và Scrum Team hiệu quả hơn. | Thư ký ghi giờ, người đốc thúc deadline cá nhân hoặc “cảnh sát quy trình”. |

## 3. Không có Project Manager trong Scrum có nghĩa gì?

**Không có PM như một accountability Scrum** không có nghĩa “mọi công việc quản trị dự án đều bị cấm”. Điều đó chỉ có nghĩa Scrum **không quy định** một quyền lực bổ sung có thể thay Product Owner, Developers hoặc Scrum Master.

Ở cấp tổ chức, một người mang chức danh PM có thể tiếp tục làm nhiều việc cần thiết, chẳng hạn:

- Theo dõi **ngân sách, hợp đồng và mốc nghĩa vụ** của dự án.
- Phối hợp **nhiều nhóm, nhà cung cấp và phòng ban**.
- Quản lý **phụ thuộc, lịch trình cấp tổ chức và thông tin dự báo tổng thể**.
- Kết nối với bộ phận **mua sắm, pháp lý, bảo mật, tuân thủ, vận hành**.
- Chuẩn bị thông tin và lựa chọn cho người có thẩm quyền ra quyết định về **nguồn lực hoặc cam kết bên ngoài**.
- Tổ chức truyền thông các mốc và rủi ro cho những bên không trực tiếp tham dự các sự kiện Scrum.

Các hoạt động trên **không trở thành quyền tự động để PM quyết định Product Backlog, giao task hay hạ DoD**.

### Ba cách bố trí nhân sự thường gặp

| Mô hình tổ chức | Cách phối hợp hợp lý | Rủi ro cần tránh |
| --- | --- | --- |
| **Không có PM riêng** | Scrum Team và các chức năng tổ chức phân chia rõ công việc ngân sách, hợp đồng, vận hành và liên nhóm theo thẩm quyền. | Nhầm “không có PM” với “không cần ai theo dõi nghĩa vụ tổ chức”. |
| **PM nằm ngoài Scrum Team** | PM phối hợp quản trị dự án, phụ thuộc và truyền thông; dùng cùng thông tin mục tiêu, backlog và dự báo với Scrum Team. | PM tạo bộ máy chỉ đạo song song áp xuống Sprint. |
| **Một cá nhân kiêm nhiệm nhiều vai trò** | Nêu rõ lúc nào người đó thực hiện accountability Scrum, lúc nào thực hiện nhiệm vụ quản trị tổ chức; kiểm soát xung đột lợi ích. | Cho rằng chức danh PM tự động trao quyền PO, Developers hoặc SM. |

Một người có thể có **chức danh công ty** và **accountability Scrum** khác nhau, nhưng việc kiêm nhiệm cần minh bạch về quyền và khả năng thực hiện, không phải cách xóa nhòa những ranh giới đang gây mâu thuẫn.

### Quy tắc điều phối cốt lõi

> **Giữ nguyên các accountabilities của Scrum; phân bổ rõ những trách nhiệm tổ chức còn lại; tạo một luồng quyết định minh bạch thay vì hai hệ thống quyền lực cạnh tranh.**

Nếu tổ chức đã có cơ chế bắt buộc về phê duyệt tài chính hoặc tuân thủ, Scrum Team không được tự bỏ qua. Nhưng cơ chế đó cũng nên được làm rõ **về mục đích, người quyết định và thời gian phản hồi**, tránh biến thành các phê duyệt trùng lặp không tạo thêm kiểm soát thực sự.

## 4. Xác định khoảng trống bằng cách lập bản đồ quyết định

Một câu hỏi hữu ích hơn “PM còn làm gì?” là:

> “Những **quyết định cần thiết** nào đang được đưa ra trong vòng đời sản phẩm, và người nào có quyền thực hiện hoặc chịu trách nhiệm giải trình cho từng quyết định?”

Bắt đầu bằng những tình huống cụ thể thay vì tranh luận chức danh:

1. Có yêu cầu thay đổi từ khách hàng.
2. Cần sắp thứ tự Product Backlog.
3. Cần xác định Sprint Goal và chọn phần công việc.
4. Một task bị chặn bởi hạ tầng hay đối tác.
5. Phát hiện lỗi hoặc rủi ro bảo mật.
6. Có Increment đã Done cần đánh giá đưa vào sử dụng.
7. Deadline hoặc ngân sách có nguy cơ vượt giới hạn.
8. Cần điều chỉnh hợp đồng, phạm vi hoặc cam kết bên ngoài.

Với mỗi quyết định, ghi **người quyết định theo quyền hạn hiện có, người thực hiện, người cần tham vấn và dấu hiệu phải chuyển cấp**.

### Phân loại nguyên nhân

| Trạng thái | Dấu hiệu | Phản ứng đầu tiên |
| --- | --- | --- |
| **Khoảng trống** | Không ai biết ai có quyền xác nhận thay đổi release cho khách hàng. | Tìm người có thẩm quyền theo tổ chức, thống nhất kênh và thời gian phản hồi. |
| **Chồng lấn** | PM và PO đều phát hành lệnh ưu tiên khác nhau. | Làm rõ Product Backlog do PO sắp thứ tự; PM cung cấp dữ kiện về nghĩa vụ và hạn. |
| **Quyền không phù hợp trách nhiệm** | Developers chịu lỗi chất lượng nhưng bị yêu cầu bỏ kiểm thử. | Khôi phục DoD và quyền lập kế hoạch chất lượng; chuyển cấp rủi ro cần thiết. |
| **Phụ thuộc không được quản lý** | Nhà cung cấp chưa trả lời, không có đầu mối xử lý hợp đồng. | Giao rõ đầu mối nhà cung cấp và phối hợp với SM để gỡ trở ngại cho team. |
| **Phản hồi bị chặn** | Stakeholder chỉ gửi yêu cầu qua PM; PO không nhận dữ liệu người dùng. | Thiết kế lại luồng thông tin để PO tiếp cận người liên quan và bằng chứng kịp thời. |

Đây là **chẩn đoán cơ chế làm việc**, không nên dùng làm công cụ tìm người đổ lỗi.

## 5. Ma trận quyền quyết định: Scrum Team và công việc quản trị dự án

Bảng dưới đây là **mẫu gợi ý** cho một tổ chức có PM riêng, PO, SM, Developers và các bên chuyên trách. Nó mô tả trách nhiệm nên được làm rõ; những việc ngoài Scrum phải được tổ chức xác nhận chính thức theo quyền hạn thực tế.

| Quyết định hoặc hoạt động | Quyền/trách nhiệm cốt lõi | PM có thể đóng góp gì? | Lưu ý ranh giới |
| --- | --- | --- | --- |
| **Product Goal và giá trị sản phẩm** | Product Owner chịu trách nhiệm quản lý và truyền đạt Product Goal. | Cung cấp bối cảnh chiến lược, hợp đồng, nguồn lực, kỳ vọng bên liên quan. | PM không tự thay Product Goal nếu không giữ accountability PO. |
| **Thứ tự Product Backlog** | **Product Owner** chịu trách nhiệm. | Đưa dữ liệu mốc, chi phí trì hoãn, ràng buộc đối tác và rủi ro. | Không tạo danh sách backlog bắt buộc thứ hai. |
| **Sprint Goal** | **Scrum Team** cùng hình thành trong Sprint Planning. | Cung cấp bối cảnh bên ngoài qua PO và trao đổi phù hợp. | Không áp từ ngoài một danh sách task thay cho Sprint Goal. |
| **Số PBI chọn cho Sprint, kế hoạch thực hiện** | **Developers** chọn và lập kế hoạch sau trao đổi trong Sprint Planning. | Nêu hạn/nguồn lực đã biết, giúp tháo gỡ phụ thuộc bên ngoài. | Không phân task trực tiếp cho từng Developer. |
| **Thực thi kỹ thuật và tổ chức công việc** | **Developers** tự quản cách thực hiện, giữ chất lượng. | Phối hợp đối tác và cấp tổ chức khi cần. | Yêu cầu quản trị phải làm rõ mục tiêu, không áp cách code hoặc ai code. |
| **Definition of Done** | Chuẩn tổ chức áp dụng nếu có; nếu không, **Scrum Team** tạo DoD phù hợp. Developers tuân thủ để tạo Increment. | Nêu nghĩa vụ kiểm soát/tiêu chuẩn bên ngoài, tham vấn chuyên gia. | PM không thể đổi “chưa Done” thành “Done” bằng xác nhận tiến độ. |
| **Scrum hiệu quả và trở ngại** | **Scrum Master** chịu trách nhiệm hỗ trợ hiệu quả và làm cho trở ngại được tháo gỡ. | Giúp xử lý rào cản hợp đồng, ngân sách, phối hợp liên đơn vị. | SM không nhất thiết tự ký hợp đồng; PM không mặc nhiên quản lý Scrum. |
| **Dự báo, mốc tổng thể và báo cáo quản trị** | Tùy tổ chức, PM có thể chịu trách nhiệm tổng hợp; dữ liệu thực thi đến từ Scrum Team. | Tổng hợp minh bạch phạm vi, rủi ro, phụ thuộc và phương án. | Báo cáo không được sửa định nghĩa Done hay ép cá nhân tăng points. |
| **Ngân sách, mua sắm, nhân sự theo tuyến quản lý** | Chủ ngân sách, quản lý chuyên môn hoặc cơ quan có thẩm quyền của tổ chức. | Chuẩn bị đề xuất, theo dõi, phối hợp thực hiện. | Scrum không tự cấp PM quyền phê duyệt các khoản này. |
| **Hợp đồng và cam kết bên ngoài** | Theo quyền hạn ký kết/thương lượng của tổ chức. | Theo dõi nghĩa vụ, chuẩn bị lựa chọn khi dự báo thay đổi. | Nghĩa vụ cần thông tin từ PO/Developers; không lấy estimate làm cam kết tự động. |
| **Phát hành/mở tính năng cho người dùng** | Tùy quy định sản phẩm và tổ chức: có thể là quyết định phối hợp của PO cùng vận hành, bảo mật, kinh doanh. | Điều phối mốc, hỗ trợ liên phòng ban và thông báo. | **Scrum không quy định PM là người phê duyệt release**; Increment Done khác release. |
| **Sự cố bảo mật, mất dữ liệu, tuân thủ** | Theo quy trình kiểm soát và người có thẩm quyền của tổ chức, có Developers/chuyên gia liên quan. | Phối hợp chuyển cấp và tác động tới cam kết. | Không giải quyết bằng bỏ phiếu hoặc bỏ điều kiện chất lượng. |

Bảng này không phải một **RACI chuẩn bắt buộc** của Scrum. Nếu tổ chức chọn RACI (*Responsible, Accountable, Consulted, Informed*), cần bảo đảm nhãn “A” trong bảng quản trị **không vô tình chuyển accountability Scrum sang PM**.

### Thế nào là một bảng phân định có ích?

Một bảng tốt phải giúp người đang làm việc trả lời trong vài phút:

- Khi nhận yêu cầu mới, tôi gửi cho ai?
- Khi cần quyết định triển khai, ai có quyền chọn?
- Khi rủi ro vượt ngưỡng, báo cho ai và qua kênh nào?
- Ai có quyền thương lượng với khách hàng?
- Khi câu trả lời chậm, ai giúp gỡ và bao lâu thì chuyển cấp?
- Quyết định và lý do được ghi ở đâu để mọi người nhìn thấy?

Nếu bảng chỉ có tên chức danh mà không giải quyết được câu hỏi này, cần bổ sung **luồng thông tin, điểm ra quyết định và tiêu chí chuyển cấp**.

## 6. Quy tắc phối hợp giữa PM, PO, SM và Developers

### 6.1. PM và Product Owner: đầu vào nghĩa vụ, đầu ra là ưu tiên sản phẩm

PM có thể biết ngày hết hạn hợp đồng, điều kiện khách hàng phải nghiệm thu và chi phí nếu chậm. PO có thể biết hành vi người dùng, giá trị từng lát sản phẩm và điều kiện Product Goal. Hai nguồn thông tin phải **gặp nhau trước khi thay đổi Product Backlog**.

Ví dụ:

- PM: “Theo hợp đồng, cần cung cấp khả năng xuất dữ liệu phù hợp vào thời điểm X; nếu trễ, cần thông báo trước Y ngày.”
- PO: “Tôi sẽ làm rõ kết quả tối thiểu, đưa nghĩa vụ vào thứ tự Product Backlog và trao đổi lựa chọn phạm vi với Developers.”
- Developers: “Chúng tôi sẽ đánh giá tính khả thi, phụ thuộc và điều kiện DoD; forecast sẽ có giả định và thời điểm cập nhật.”

**Không phù hợp:** PM tự gửi chỉ thị “Sprint này mỗi người phải làm thêm hai story” trong khi PO và Developers chưa trao đổi.

### 6.2. PM và Scrum Master: hợp tác tháo gỡ trở ngại, không hoán đổi accountability

Một API bên ngoài chậm có thể cần:

- Developers mô tả chính xác hợp đồng kỹ thuật đang bị chặn và khả năng dùng giải pháp thay thế.
- Scrum Master làm cho trở ngại hiển thị, hỗ trợ kết nối và cải thiện cách phối hợp.
- PM theo dõi nghĩa vụ bên nhà cung cấp, kích hoạt đầu mối hợp đồng hoặc kênh chuyển cấp thuộc thẩm quyền tổ chức.
- PO đánh giá ảnh hưởng tới giá trị, ưu tiên và dự báo phát hành.

Mọi người đều có thể đóng góp, nhưng mỗi người **giữ phạm vi trách nhiệm khác nhau**.

### 6.3. PM và Developers: trao đổi giới hạn, không quản lý vi mô

PM có thể hỏi:

> “Hiện phụ thuộc nào ảnh hưởng tới mốc phát hành, điều kiện để có forecast tốt hơn là gì, và tổ chức cần hỗ trợ gì?”

Nên tránh:

> “Bạn A phải sửa API trước 15 giờ; bạn B làm database chiều nay; mỗi người gửi số giờ hoàn tất cho tôi.”

Developers có thể chủ động đề xuất cách chia lát dọc, phối hợp kiểm thử và lựa chọn kỹ thuật. PM được cung cấp **thông tin tiến độ kết quả**, không cần phân công thay Developers.

### 6.4. Các chức năng quản lý nhân sự

Trong nhiều tổ chức, quản lý tuyến (*line manager*) chịu trách nhiệm tuyển dụng, phát triển nghề nghiệp và đánh giá nhân sự. Các trách nhiệm đó có thể tiếp tục tồn tại. Điều cần rõ là **quyền quản lý nhân sự không mặc nhiên trao quyền sắp Product Backlog hoặc quyết định Sprint Backlog**.

Nếu một cá nhân vừa là quản lý trực tiếp vừa giữ accountability Scrum, nguy cơ người khác ngại phản biện cần được nhận diện. Nhóm nên thiết lập cách nêu rủi ro an toàn và phân định quyết định dựa trên mục tiêu, dữ kiện, thẩm quyền đã thống nhất.

## 7. Luồng yêu cầu mới: tránh hai hàng chờ công việc cạnh tranh

Một nguyên nhân phổ biến của khoảng trống trách nhiệm là yêu cầu đi qua **nhiều lối vào** rồi xuất hiện dưới dạng lệnh khác nhau: khách hàng nhắn PM, phòng kinh doanh nhắn PO, cấp quản lý giao trực tiếp Developers.

Có thể thiết kế một luồng phối hợp đơn giản:

~~~mermaid
flowchart TD
    A["Yêu cầu / rủi ro / phản hồi mới"] --> B["Thu nhận bối cảnh: giá trị, nghĩa vụ, mức khẩn"]
    B --> C{"Có sự cố hoặc yêu cầu kiểm soát khẩn?"}
    C -->|"Có"| D["Xử lý theo cơ chế sự cố / thẩm quyền phù hợp"]
    C -->|"Không"| E["Product Owner làm rõ và sắp Product Backlog"]
    D --> F["Thông báo ảnh hưởng tới sản phẩm và kế hoạch"]
    F --> E
    E --> G["Developers trao đổi khả thi, phụ thuộc, cách chia lát"]
    G --> H{"Liên quan Sprint đang chạy?"}
    H -->|"Có"| I["Trao đổi tác động tới Sprint Goal và Sprint Backlog"]
    H -->|"Không"| J["Xem xét ở nhịp lập kế hoạch phù hợp"]
    I --> K["Developers lập / thích ứng kế hoạch, giữ DoD"]
    J --> K
    K --> L["Increment có thể sử dụng; đánh giá phát hành"]
    L --> M["Phản hồi về người dùng, chất lượng, luồng công việc"]
    M --> E
~~~

**Lưu ý:** Sơ đồ là gợi ý làm việc, không phải một thủ tục Scrum bắt buộc. Một sự cố nghiêm trọng có thể cần phản ứng tức thời; việc xử lý không nên chờ Product Backlog refinement. Sau đó, những hệ quả liên quan tới sản phẩm và ưu tiên cần được làm minh bạch.

### Chính sách đầu vào có thể rất ngắn

- Yêu cầu sản phẩm thông thường đi tới **PO** hoặc kênh Product Backlog đã thống nhất.
- Nghĩa vụ hợp đồng, ngân sách, phụ thuộc nhà cung cấp được **PM cung cấp bối cảnh và đầu mối**.
- Rủi ro bảo mật, dữ liệu hoặc vận hành nghiêm trọng đi qua **kênh kiểm soát sự cố** tương ứng.
- Developers có quyền và trách nhiệm **nêu khả thi, rủi ro chất lượng và đề xuất chia lát**.
- Các quyết định ảnh hưởng kế hoạch đã công bố phải được **cập nhật minh bạch** cho những bên liên quan.

Điểm mục tiêu là **một nguồn sự thật về ưu tiên sản phẩm**, không nhất thiết chỉ có một phần mềm quản lý ticket cho toàn tổ chức.

## 8. Tình huống 1: PM yêu cầu chen tính năng vào Sprint

Nhóm đang thực hiện Sprint Goal:

> “Người học có thể rời video rồi tiếp tục ở đúng vị trí đã lưu, đáp ứng điều kiện chất lượng để thử nghiệm.”

Giữa Sprint, PM nhận yêu cầu từ đối tác: “Thêm báo cáo xuất Excel trong tuần này; đối tác muốn xem ở buổi họp.”

### Cách phản ứng dễ gây rối

PM nhắn trực tiếp hai Developers chuyển sang làm Excel, không trao đổi với PO. Sprint Backlog bị thay đổi ngầm. Đến Sprint Review, chức năng “Học tiếp” chưa hoàn tất và nhóm chỉ biết giải thích rằng “có việc gấp”.

**Vấn đề:** chưa làm rõ liệu yêu cầu Excel thực sự có nghĩa vụ trong tuần, ai được quyền ưu tiên, và việc đổi phạm vi ảnh hưởng Sprint Goal thế nào.

### Cách phối hợp có trách nhiệm

1. **PM làm rõ tính bắt buộc:** buổi họp cần bản dùng thật hay demo dữ liệu mẫu được mô tả trung thực? Có cam kết/hậu quả nào nếu không có Excel?
2. **PO đánh giá giá trị và Product Backlog:** yêu cầu ảnh hưởng mục tiêu sản phẩm hiện tại ra sao?
3. **Developers xem ảnh hưởng Sprint Goal:** có thể tạo một lát nhỏ nào phù hợp không, cần công việc nào được giảm hoặc hoãn?
4. **Scrum Master hỗ trợ trao đổi:** đảm bảo rủi ro và trở ngại được nhìn thấy; không âm thầm áp lịch cá nhân.
5. **Quyết định được công bố:** giữ Sprint Goal và lên lịch Excel sau, hoặc điều chỉnh kế hoạch một cách minh bạch nếu cần và phù hợp.
6. **Nếu Sprint Goal trở nên lỗi thời:** trong Scrum, chỉ **Product Owner** có thẩm quyền hủy Sprint; đây là ngoại lệ, không phải công cụ xử lý mọi thay đổi nhỏ.

### Mẫu đối thoại ngắn

**PM:** “Đối tác đang yêu cầu xuất Excel trước thứ Sáu; tôi sẽ xác nhận xem đó là điều khoản bắt buộc hay nhu cầu demo.”

**PO:** “Tôi sẽ đánh giá mức ưu tiên và tác động tới Product Goal, rồi làm rõ với nhóm.”

**Developer:** “Sprint Goal hiện cần chúng tôi hoàn thành phần kiểm thử lưu tiến độ. Nếu thêm Excel, có rủi ro không hoàn tất theo DoD; chúng tôi sẽ nêu lựa chọn phạm vi.”

**Scrum Master:** “Chúng ta cần một quyết định rõ, không giao việc riêng lẻ làm thay đổi kế hoạch mà nhóm không biết.”

Kết quả tốt không nhất thiết là từ chối Excel. Kết quả tốt là **đưa ra lựa chọn có căn cứ, với người quyết định đúng trách nhiệm**.

## 9. Tình huống 2: PM chịu deadline nhưng PO quyết định ưu tiên

Tổ chức cần ra mắt bản thử của nền tảng học trước một sự kiện đã lên lịch. PM chịu trách nhiệm báo cáo mốc ra mắt cho ban điều hành, PO ưu tiên chức năng có giá trị, còn Developers cảnh báo một phần tích hợp chưa rõ.

### Phân biệt target, forecast và cam kết

- **Target:** tổ chức mong muốn ra mắt trước sự kiện.
- **Forecast:** dự báo khả năng hoàn tất dựa trên phạm vi, năng lực, dữ liệu và phụ thuộc hiện tại.
- **Cam kết chính thức:** điều tổ chức thực sự đã thống nhất với bên ngoài, gồm ngày, phạm vi, tiêu chuẩn và trách nhiệm liên quan.

Không nên biến một con số ước lượng của Developers thành **cam kết ngày cố định** chỉ qua một báo cáo PM.

### Một bảng lựa chọn phát hành

| Lựa chọn | Được giữ | Điều thay đổi | Điều kiện không thể bỏ |
| --- | --- | --- | --- |
| **Giữ ngày, phạm vi cốt lõi** | Mốc thử nghiệm. | Chưa làm báo cáo nâng cao, AI hoặc đồng bộ đa thiết bị. | Chức năng lõi dùng được, quyền truy cập và dữ liệu đúng, đáp ứng DoD. |
| **Giữ phạm vi lớn hơn** | Tập chức năng dự kiến. | Cần xem lại ngày hoặc phân kỳ phát hành. | Không hạ chuẩn bảo mật và kiểm thử. |
| **Mở cho nhóm nhỏ trước** | Cơ hội nhận phản hồi gần mốc sự kiện. | Giới hạn đối tượng, cơ chế hỗ trợ và điều kiện mở rộng. | Minh bạch phạm vi thử, vận hành an toàn và có phương án xử lý sự cố. |
| **Thử kỹ thuật sớm, cập nhật forecast** | Mục tiêu giá trị. | Thời điểm chốt quyết định dựa trên bằng chứng mới. | Tiêu chí dừng và đầu mối quyết định rõ. |

### Ai làm gì?

- **PM:** điều phối thông tin mốc, hợp đồng, truyền thông ban điều hành và phương án về nguồn lực/cam kết.
- **PO:** xác định phần giá trị cốt lõi nào nên ưu tiên trong Product Backlog.
- **Developers:** đánh giá khả thi và chất lượng, chia lát dọc, dự báo trên thực tế.
- **SM:** hỗ trợ tính minh bạch và cải thiện phối hợp/loại bỏ trở ngại.
- **Bộ phận phát hành/vận hành/pháp lý nếu cần:** quyết định hoặc cung cấp điều kiện thuộc thẩm quyền của họ.

Scrum không gán mặc định **quyền ký hợp đồng** hoặc **quyền cho phép phát hành** cho một trong ba accountability. Những quyền đó phải được tổ chức làm rõ.

## 10. Tình huống 3: phụ thuộc bên ngoài làm chậm cả nhóm

Nhóm cần tích hợp API thanh toán từ một nhà cung cấp. Tài khoản kiểm thử chưa được cấp sau nhiều ngày.

Nếu không phân định trách nhiệm, một vòng đùn đẩy có thể hình thành:

- Developers nói đang chờ tài khoản nên không thể làm tiếp.
- SM được yêu cầu “lo mọi trở ngại”.
- PM cho rằng SM chịu trách nhiệm xử lý vì đó là việc của nhóm Scrum.
- PO tiếp tục nhận thêm chức năng mới dù phụ thuộc có thể đe dọa mốc phát hành.

### Cách xử lý theo lớp trách nhiệm

| Công việc | Đầu mối phù hợp | Đầu ra kỳ vọng |
| --- | --- | --- |
| Mô tả chính xác quyền truy cập/API đang thiếu và tác động kỹ thuật. | Developers | Một yêu cầu rõ, điều kiện thử và mức rủi ro. |
| Làm trở ngại hiển thị, hỗ trợ phối hợp và tìm cách giảm thời gian chờ. | Scrum Master cùng Developers | Kế hoạch tháo gỡ hoặc giảm phụ thuộc; không để issue mất dấu. |
| Liên hệ nhà cung cấp qua cơ chế hợp đồng, chuyển cấp nếu cần. | PM hoặc người sở hữu quan hệ/hợp đồng theo tổ chức | Thông tin phản hồi chính thức, mốc và khả năng hỗ trợ. |
| Đánh giá thay đổi ưu tiên khi phụ thuộc kéo dài. | Product Owner | Product Backlog và lựa chọn phạm vi phản ánh thực tế. |
| Đánh giá tác động mốc tổng thể, thông báo bên liên quan. | PM phối hợp với PO/Developers | Forecast có điều kiện và phương án giảm rủi ro. |

Nếu Developers có thể sử dụng **mock có giới hạn** để thử sớm hợp đồng giao tiếp, việc đó hữu ích để giảm rủi ro; nhưng mock **không thay thế** kiểm chứng tích hợp thật trước khi coi luồng thanh toán đã đủ để phát hành.

### Quy tắc chuyển cấp cần cụ thể

> “Nếu sau hai ngày làm việc yêu cầu truy cập chưa có phản hồi có thể sử dụng, PM kích hoạt kênh đối tác cấp tiếp theo. Developers cập nhật các công việc bị chặn, PO xem lại phạm vi release, SM hỗ trợ nhóm chọn phần việc có giá trị khác trong lúc chờ.”

Hai ngày chỉ là **ví dụ**, không phải ngưỡng chung. Một sự cố nghiêm trọng có thể cần chuyển cấp ngay. Quy tắc tốt phải cân xứng với tác động và nghĩa vụ.

## 11. Tình huống 4: ai xác nhận “Done” và ai quyết định “Release”?

Một PM muốn báo cáo 100% tiến độ khi cả giao diện và API của tính năng đã viết xong. Tuy nhiên, Developers cho biết kiểm thử tích hợp lỗi và chưa đáp ứng Definition of Done.

### Hai trạng thái không thể gộp

| Trạng thái | Nghĩa chính | Có đủ để công bố là Increment Done? |
| --- | --- | --- |
| **Code complete** | Phần code chính đã viết xong. | **Chưa đủ.** |
| **Acceptance criteria đã kiểm tra** | Các hành vi cụ thể của story đáp ứng ví dụ đã thỏa thuận. | Vẫn cần thỏa toàn bộ DoD liên quan. |
| **Increment đạt DoD** | Phần tiến bộ tích hợp với sản phẩm, có thể sử dụng và đạt tiêu chuẩn hoàn tất. | **Có**, theo nghĩa Scrum. |
| **Deployed** | Bản phần mềm đã được đưa lên môi trường chạy. | Chưa tự chứng minh được người dùng có khả năng sử dụng hoặc tạo giá trị. |
| **Released** | Khả năng sản phẩm đã được mở cho nhóm người dùng được xác định. | Có thể thu phản hồi; chưa chứng minh đạt mục tiêu kinh doanh. |

**Không ai có thể “phê duyệt bằng lời” để làm một phần chưa đạt DoD thành Increment đã Done.** Nếu tổ chức có thủ tục nghiệm thu bên ngoài, thủ tục đó là một bước quản trị riêng, không thay định nghĩa của Done trong Scrum.

### Mô hình phối hợp phát hành

1. Developers minh bạch về các Increment đã đạt DoD và các rủi ro chưa xử lý.
2. PO làm rõ giá trị, nhóm người dùng và mục tiêu của lần phát hành.
3. PM điều phối lịch, thông báo và các phụ thuộc/cam kết cấp tổ chức.
4. Các chức năng có thẩm quyền về bảo mật, vận hành, pháp lý hoặc phát hành tham gia khi cần.
5. Người được tổ chức giao quyền ra quyết định release xác nhận điều kiện và phạm vi.
6. Nhóm quan sát phản hồi, lỗi và kết quả người dùng sau phát hành.

Đây là **mô hình gợi ý**, không phải một chuỗi cổng bắt buộc theo Scrum. Nếu tổ chức có khả năng phát hành liên tục an toàn, các bước có thể được tự động hóa hoặc xử lý theo chính sách ngắn gọn.

## 12. Trách nhiệm quản trị dự án không chỉ là lịch và báo cáo

Khi áp dụng Scrum, tổ chức đôi khi bỏ qua những việc ít hiện trên Product Backlog nhưng có tác động thực:

- **Ngân sách và mua sắm:** môi trường thử nghiệm, giấy phép, dịch vụ bên ngoài.
- **Hợp đồng:** thời điểm cung cấp tài liệu, quyền sử dụng dữ liệu, nghiệm thu, thay đổi phạm vi.
- **Điều phối liên bộ phận:** lịch triển khai với vận hành, hỗ trợ khách hàng và bộ phận đào tạo.
- **Tuân thủ:** chứng cứ kiểm soát, phân loại dữ liệu, lưu trữ và khả năng truy xuất khi có nghĩa vụ.
- **Truyền thông dự án:** kết quả đã đạt, rủi ro, phương án lựa chọn và tác động tới bên liên quan.
- **Quản lý thay đổi ở tổ chức:** hướng dẫn người sử dụng, chuẩn bị hỗ trợ, thay đổi quy trình nghiệp vụ.
- **Nguồn lực và năng lực:** nhu cầu chuyên gia, phụ thuộc nhóm khác, rủi ro thiếu người có kỹ năng.

Những hoạt động này **có thể do PM điều phối**, do chức năng khác chịu trách nhiệm hoặc được một người phù hợp đảm nhận trong cơ cấu tổ chức. Scrum không buộc phải dùng chức danh PM; cũng không cấm tổ chức có những người đảm nhiệm các công việc đó.

### Đừng đưa mọi hoạt động quản trị thành “task của Scrum Team”

Nếu việc gia hạn hợp đồng là trách nhiệm của bộ phận mua sắm, không cần biến Product Backlog thành nơi chứa mọi email và ký duyệt. Tuy nhiên, nếu gia hạn quyết định khả năng phát hành, phụ thuộc đó phải được nhóm biết, quản lý rủi ro và đưa vào forecast.

**Nguyên tắc:** hoạt động nào ảnh hưởng đến khả năng tạo Increment và giá trị sản phẩm phải được kết nối bằng thông tin/phụ thuộc rõ; không phải hoạt động nào cũng cần chuyển quyền thực hiện vào Scrum Team.

## 13. Sử dụng RACI hoặc bảng thẩm quyền mà không phá vỡ Scrum

Một số tổ chức quen dùng **RACI**:

- **R – Responsible:** trực tiếp thực hiện.
- **A – Accountable:** chịu trách nhiệm cuối cùng trong phạm vi quyết định.
- **C – Consulted:** cần trao đổi trước hoặc trong khi quyết định.
- **I – Informed:** cần được thông tin sau khi quyết định hoặc khi trạng thái thay đổi.

RACI có thể giúp làm rõ quy trình hợp đồng, ngân sách, triển khai liên phòng ban. Tuy nhiên, nếu dùng bất cẩn, bảng có thể ghi **“PM = A cho Product Backlog”**, trái với accountability PO trong Scrum.

### Ví dụ bảng RACI giới hạn cho một hoạt động bên ngoài Scrum

Giả sử tổ chức đã xác nhận **chủ ngân sách** là người phê duyệt một khoản mua dịch vụ, PM điều phối hồ sơ. Đây là ví dụ về quản trị tổ chức, không phải định nghĩa Scrum:

| Hoạt động: mua dịch vụ kiểm thử cần cho release | Chủ ngân sách | PM | Developers | PO | SM |
| --- | --- | --- | --- | --- | --- |
| Xác định yêu cầu kỹ thuật của dịch vụ | I | C | **R** | C | I |
| Chuẩn bị hồ sơ/điều phối mua sắm | C | **R** | C | I | I |
| Phê duyệt chi phí theo quyền tổ chức | **A** | R hoặc C tùy quy trình | C | C | I |
| Cập nhật tác động tới kế hoạch sản phẩm | I | **R** về dữ kiện mốc | C | **A** về thay đổi Product Backlog | C |

Bảng có thể có **hai loại phạm vi trách nhiệm khác nhau**: quyền chi ngân sách và quyền quản lý Product Backlog. Để tránh nhầm, nên tách theo **quyết định** hơn là ép một dòng bao trùm cả “mua dịch vụ và thay kế hoạch”.

Trong trường hợp không cần RACI, một **decision log** ngắn có tên người quyết định, các bên liên quan và thời điểm xem lại có thể đủ hữu ích.

## 14. Khi có nhiều Scrum Team, chương trình hoặc nhà cung cấp

Quy mô tổ chức lớn thường tăng nhu cầu phối hợp: nhiều nhóm cùng làm một sản phẩm, tích hợp với nhà cung cấp, phụ thuộc vào hạ tầng dùng chung hoặc có hợp đồng triển khai theo giai đoạn.

### 14.1. Nhiều nhóm cùng một sản phẩm

Nếu nhiều Scrum Teams cùng làm trên một sản phẩm, cần giữ **Product Goal, Product Backlog và định nghĩa Increment** nhất quán theo cách áp dụng Scrum; cùng sản phẩm nên có **một Product Owner** và một Product Backlog, các nhóm phải phối hợp để phần tăng trưởng tương thích. PM có thể hỗ trợ nhìn các phụ thuộc cấp chương trình nhưng không nên tạo những Product Backlog cạnh tranh cho từng nhóm dựa trên thứ tự ưu tiên riêng.

### 14.2. Phụ thuộc xuyên nhóm

Ví dụ nhóm A cần API từ nhóm B. Cách phối hợp hữu ích:

- Hai nhóm làm rõ **hợp đồng giao tiếp, ví dụ dữ liệu và tiêu chí tích hợp**.
- PO liên quan trao đổi về giá trị và thứ tự công việc.
- Developers tạo cách thử tích hợp sớm, thay vì chờ tới cuối release.
- SM hỗ trợ tháo gỡ trở ngại phối hợp giữa nhóm.
- PM, nếu có trách nhiệm điều phối tổng thể, cung cấp minh bạch về mốc, ngân sách và nghĩa vụ bên ngoài.

Không cần tạo chuỗi “PM A giao việc cho PM B, PM B giao cho nhóm B” cho mọi câu hỏi kỹ thuật nếu các Developers có thể phối hợp trực tiếp và minh bạch.

### 14.3. Nhà cung cấp và hợp đồng

Một nhà cung cấp có thể không hoạt động theo Scrum. PM có thể sở hữu kênh thương mại/hợp đồng; Developers vẫn cần kênh kỹ thuật để làm rõ đặc tả và thử tích hợp. PO cần thông tin để lựa chọn phạm vi và ưu tiên.

**Rủi ro chính:** “hợp đồng có ngày” không bảo đảm tích hợp có thể Done ngày đó. Phải đánh giá chất lượng, điều kiện nghiệm thu, dữ liệu và khả năng xử lý khi phụ thuộc trễ.

### 14.4. Quản trị nhiều cấp không đồng nghĩa nhiều cấp giao task

Ở tổ chức lớn, ban điều hành hoặc PMO có thể yêu cầu báo cáo tổng hợp. Báo cáo nên lấy từ **kết quả có thể kiểm chứng** và dự báo minh bạch, không buộc mỗi Scrum Team tạo một bảng điểm cá nhân riêng để phục vụ cấp trên.

## 15. Báo cáo tiến độ mà không biến Scrum thành quản lý vi mô

PM thường cần thông tin để trả lời ban điều hành và đối tác. Có thể sử dụng một định dạng ngắn tập trung vào **mục tiêu, Increment, rủi ro và quyết định cần hỗ trợ**.

### Báo cáo nên trả lời gì?

| Nội dung | Ví dụ thông tin có ích | Cách hiểu sai cần tránh |
| --- | --- | --- |
| **Mục tiêu hiện tại** | Sprint Goal là khôi phục tiến độ bài học an toàn. | Chỉ liệt kê giờ làm của từng người. |
| **Kết quả đã hoàn tất** | Lát lưu/đọc tiến độ đã đạt DoD và có thể demo. | “80% code” được báo thành tính năng Done. |
| **Giá trị đã kiểm chứng** | Nhóm thử có thể tiếp tục video; vẫn đang đo tỷ lệ quay lại. | Cho rằng chức năng có sẵn là đã tạo outcome. |
| **Rủi ro/điểm nghẽn** | API đối tác chưa được cấp quyền, đe dọa mốc tích hợp. | Giấu rủi ro để giữ trạng thái xanh. |
| **Dự báo cập nhật** | Phạm vi lõi có khả năng phù hợp cửa sổ hiện tại nếu phụ thuộc được gỡ trước mốc X. | Xem forecast như bảo đảm. |
| **Quyết định cần hỗ trợ** | Cần chủ ngân sách phê duyệt môi trường test hoặc đối tác xác nhận giao thức. | Yêu cầu Developers tự giải quyết nghĩa vụ ngoài quyền hạn. |
| **Bước kế tiếp** | Hoàn tất kiểm thử quyền truy cập; đánh giá dữ liệu thử; cập nhật backlog. | Giao thêm việc chỉ để tăng số ticket đang làm. |

Một mẫu báo cáo một đoạn:

> “Sprint Goal hiện tại là đưa khả năng tiếp tục học tới mức thử nghiệm được. Lát khôi phục tiến độ đã đạt DoD; phần liên kết từ trang chủ còn đang kiểm thử trường hợp không có quyền. Phụ thuộc tài khoản test của đối tác làm rủi ro mốc tích hợp tăng. PM đang xử lý kênh nhà cung cấp, SM hỗ trợ tháo gỡ trở ngại và Developers sẽ cập nhật forecast sau thử tích hợp. PO sẽ xem lại các phần nâng cao trước quyết định phát hành.”

Thông tin có thể được **tạo từ Product Backlog, Sprint Backlog và bảng luồng hiện có**, tránh hai hệ thống nhập liệu trùng lặp.

### Những số đo phù hợp

- **Kết quả sản phẩm:** người dùng hoàn thành tác vụ, phản hồi về trải nghiệm, giá trị kỳ vọng.
- **Chất lượng:** lỗi sau phát hành, mức nghiêm trọng, các mục đạt DoD, khả năng khôi phục.
- **Luồng công việc:** throughput, cycle time, WIP và tuổi công việc.
- **Khả năng dự báo:** phạm vi dự báo, giả định, thay đổi so với dữ liệu mới và các phụ thuộc.
- **Quản trị tổ chức:** ngân sách đã sử dụng, nghĩa vụ hợp đồng, trạng thái phê duyệt, rủi ro liên phòng ban.

Story points/velocity, nếu nhóm dùng, chỉ nên là **công cụ lập kế hoạch trong bối cảnh nhóm**, không là bảng so sánh năng suất cá nhân hoặc thước đo chuẩn giữa các nhóm.

## 16. Thiết lập working agreement để không lặp lại tranh chấp quyền hạn

Một **working agreement** ngắn giữa Scrum Team và PM giúp những tình huống quen thuộc được xử lý nhất quán. Đây là thỏa thuận phối hợp tự chọn của tổ chức, **không phải hiện vật Scrum bắt buộc**.

### Mẫu thỏa thuận làm việc

~~~text
MỤC TIÊU PHỐI HỢP
  Giao Increment có giá trị, đạt DoD; minh bạch nghĩa vụ và rủi ro tổ chức.

QUYẾT ĐỊNH SẢN PHẨM
  Product Owner chịu trách nhiệm Product Goal và thứ tự Product Backlog.
  PM cung cấp nghĩa vụ hợp đồng, dữ liệu mốc và rủi ro bên ngoài.

QUYẾT ĐỊNH SPRINT / KỸ THUẬT
  Scrum Team hình thành Sprint Goal.
  Developers chọn công việc và điều chỉnh kế hoạch thực hiện, giữ DoD.
  Không giao task trực tiếp từ ngoài làm thay đổi Sprint Backlog ngầm.

TRỞ NGẠI VÀ PHỤ THUỘC
  Developers mô tả tác động kỹ thuật.
  Scrum Master làm cho trở ngại được tháo gỡ.
  PM hỗ trợ những việc thuộc quyền phối hợp hợp đồng/tổ chức.

PHÁT HÀNH / CAM KẾT BÊN NGOÀI
  Nêu rõ người có thẩm quyền theo tổ chức và điều kiện cần đáp ứng.
  Phân biệt Increment Done, deployment và release.

LUỒNG THAY ĐỔI
  Yêu cầu sản phẩm vào Product Backlog qua Product Owner.
  Sự cố nghiêm trọng theo cơ chế xử lý sự cố tương ứng.
  Mọi thay đổi ảnh hưởng mục tiêu hoặc mốc được thông báo minh bạch.

BÁO CÁO
  Dùng một nguồn thông tin về công việc, mục tiêu, chất lượng và dự báo.
  Không dùng story points cá nhân làm thước đo năng suất.

XEM LẠI
  Thống nhất khi nào đánh giá thỏa thuận và ai chủ trì thảo luận.
~~~

Không cần điền đầy đủ mọi mục ngay trong một cuộc họp dài. Nhóm có thể bắt đầu với ba vướng mắc gây ảnh hưởng lớn nhất rồi điều chỉnh sau một vài Sprint hoặc mốc công việc.

### Kiểm tra working agreement bằng một tình huống thực tế

Sau khi thống nhất, hãy hỏi: “Nếu khách hàng gọi PM lúc 16 giờ yêu cầu thêm chức năng gấp, PM phải làm gì?” Nếu mọi người còn trả lời mâu thuẫn, thỏa thuận chưa đủ rõ.

Một câu trả lời khả thi:

> “PM thu thập lý do, nghĩa vụ và mốc cần đáp ứng; chuyển thông tin cho PO. PO đánh giá thứ tự Product Backlog và trao đổi với Developers về khả thi, tác động Sprint Goal. SM hỗ trợ cuộc trao đổi nếu phát sinh trở ngại. PM cập nhật bên liên quan theo quyết định và dự báo đã được thống nhất.”

## 17. Những sai lầm thường gặp và cách điều chỉnh

| Sai lầm | Vì sao gây hại | Cách sửa |
| --- | --- | --- |
| **“Scrum không có PM nên mọi quản trị dự án tự biến mất.”** | Ngân sách, hợp đồng, phụ thuộc và thẩm quyền ngoài Scrum không có đầu mối. | Phân bổ rõ công việc quản trị tổ chức, giữ accountabilities Scrum. |
| **PM thành Product Owner thứ hai.** | Backlog có hai người ra ưu tiên khác nhau. | Tôn trọng PO chịu trách nhiệm thứ tự Product Backlog; PM cung cấp đầu vào. |
| **PM trực tiếp giao task cho Developers giữa Sprint.** | Phá tự quản, gây xung đột kế hoạch và Sprint Goal. | Chuyển yêu cầu qua cơ chế Product Backlog và trao đổi với Scrum Team. |
| **SM bị biến thành trợ lý báo cáo PM.** | Mất khả năng cải thiện hiệu quả Scrum và gỡ trở ngại hệ thống. | SM tập trung coaching, hiệu quả Scrum Team và trở ngại; báo cáo có thể dùng dữ liệu sẵn có. |
| **PO có chức danh nhưng không có quyền quyết định thực.** | Người chịu accountability không kiểm soát được ưu tiên; phản hồi người dùng bị chặn. | Làm rõ thẩm quyền theo Scrum và xử lý mâu thuẫn ở cấp tổ chức. |
| **PM coi estimate là deadline và points là năng suất.** | Tăng che giấu rủi ro, giảm chất lượng và dữ liệu dự báo mất tin cậy. | Phân biệt forecast/target/cam kết; dùng kết quả, chất lượng và flow metrics. |
| **Duyệt “Done” bằng email trước khi đạt DoD.** | Báo cáo tiến độ không phản ánh phần mềm có thể sử dụng. | Giữ DoD rõ, tách code complete, Done và release. |
| **Tất cả vấn đề bị chuyển cho SM “tự giải quyết”.** | Trở ngại vượt quyền như hợp đồng hoặc mua sắm bị chậm. | SM hỗ trợ làm cho trở ngại được tháo gỡ; đúng người có quyền xử lý phần việc tổ chức. |
| **RACI được dùng để đổi accountability Scrum.** | Bảng quản trị trở thành cấp trên thực tế của PO/Developers. | Tách quyền tổ chức và trách nhiệm Scrum; không ghi PM = A cho mọi quyết định. |
| **Release chờ nhiều cổng duyệt không rõ giá trị.** | Lãng phí thời gian, phản hồi người dùng chậm. | Giữ cổng kiểm soát cần thiết, công khai người quyết định và thời gian phản hồi. |
| **Scrum Team né rủi ro vì “PM lo tất”.** | Mất minh bạch và trách nhiệm với sản phẩm. | Developers nêu rủi ro kỹ thuật, PO quản lý giá trị, SM hỗ trợ hiệu quả; PM hỗ trợ tổ chức. |
| **Một người kiêm nhiều vai trò nhưng không nêu khi nào dùng quyền nào.** | Người khác khó phản biện, không biết đường chuyển cấp. | Công khai accountability theo quyết định, tạo kênh xử lý xung đột lợi ích. |

## 18. Bài tập tình huống: chuyển đổi một tổ chức có PMO sang Scrum

Một tổ chức xây **nền tảng quản lý lớp học trực tuyến** có cấu trúc:

- Một **PM** thuộc PMO báo cáo tiến độ, ngân sách và lịch với ban điều hành.
- Một **Product Owner** chịu trách nhiệm nhu cầu giáo viên và học viên.
- Một **Scrum Master** và sáu **Developers** đa chuyên môn.
- Một bộ phận **vận hành/bảo mật** có quy trình kiểm soát trước khi mở tính năng cho khách hàng.
- Một **nhà cung cấp dịch vụ video** do PM quản lý hợp đồng.

Sprint Goal hiện tại:

> “Giáo viên có thể tạo một buổi học trực tuyến và học viên được cấp quyền tham gia đúng buổi, với luồng đăng nhập và truy cập đáng tin cậy.”

Giữa Sprint xảy ra bốn việc:

1. PM nhận yêu cầu từ lãnh đạo phải thêm dashboard màu sắc để demo cuối tuần.
2. Developers phát hiện link phòng học có thể bị chia sẻ để truy cập trái phép.
3. Nhà cung cấp video chậm cấp quyền thử tích hợp.
4. PM muốn báo cáo **100% Done** vì code chính đã xong, dù bài kiểm thử quyền truy cập chưa đạt.

### Nhiệm vụ thực hành

1. **Phân loại:** Mỗi vấn đề thuộc quyết định sản phẩm, chất lượng kỹ thuật, quản trị hợp đồng hay báo cáo?
2. **Phân định trách nhiệm:** Ai chịu trách nhiệm thứ tự Product Backlog? Ai quyết định cách khắc phục quyền truy cập? Ai có quyền hỗ trợ nhà cung cấp theo hợp đồng? Ai hỗ trợ tháo gỡ trở ngại?
3. **Sprint Goal:** Việc thêm dashboard có phù hợp mục tiêu Sprint không? Cần trao đổi những gì trước khi thay đổi phạm vi?
4. **Chất lượng:** Vì sao “code xong” chưa đủ để báo Done? Những điều kiện nào phải xác minh?
5. **Release:** Ai quyết định mở tính năng cho người dùng thật, và cần kiểm tra điều gì với bộ phận vận hành/bảo mật?
6. **Truyền thông:** Viết một báo cáo ngắn cho ban điều hành, phân biệt việc đã Done, việc bị chặn, rủi ro và lựa chọn.
7. **Thỏa thuận làm việc:** Đề xuất ba điều khoản ngắn giúp tránh lặp lại xung đột giữa PM, PO, SM và Developers.

### Hướng giải gợi ý

**Dashboard màu sắc** là một yêu cầu về ưu tiên sản phẩm: PM cần làm rõ giá trị và tính khẩn, chuyển thông tin tới PO. PO cân nhắc thứ tự Product Backlog và trao đổi với Developers về tác động Sprint Goal. Không đưa dashboard trực tiếp vào task cá nhân chỉ vì có lãnh đạo yêu cầu.

**Lỗ hổng link phòng học** ảnh hưởng quyền truy cập và an toàn. Developers cần xác định và xử lý đúng kỹ thuật với tiêu chí kiểm thử rõ; bộ phận bảo mật có thể có quyền kiểm soát bắt buộc theo tổ chức. PM cần được thông báo nếu có ảnh hưởng mốc; không được yêu cầu bỏ rủi ro để báo đúng ngày.

**Nhà cung cấp chậm** là phụ thuộc vừa kỹ thuật vừa hợp đồng: Developers mô tả điều đang bị chặn, SM làm cho trở ngại được tháo gỡ, PM kích hoạt đầu mối nhà cung cấp theo thẩm quyền, PO đánh giá tác động phạm vi/giá trị.

**Code chưa đạt kiểm thử quyền truy cập** không thể coi là Increment Done vì chưa thỏa DoD. PM có thể báo “code hoàn tất, kiểm thử truy cập chưa đạt, release đang bị chặn”; điều này trung thực và có ích hơn “100% xong”.

**Quyết định phát hành** cần được tổ chức phân định; Scrum không mặc định giao quyền này cho PM. Bên có thẩm quyền phải dựa trên Increment đạt DoD, điều kiện bảo mật, vận hành và giới hạn người dùng sẽ được phục vụ.

**Ba điều khoản phối hợp minh họa:**

1. “Mọi yêu cầu chức năng thông thường được làm rõ và sắp thứ tự qua Product Owner; PM cung cấp bối cảnh nghĩa vụ và tác động mốc.”
2. “Developers tự lập kế hoạch và giữ DoD; không ai xác nhận một phần chưa đạt DoD thành Done chỉ để báo cáo.”
3. “Trở ngại liên tổ chức có đầu mối, thời gian phản hồi và quy tắc chuyển cấp; SM hỗ trợ hiệu quả phối hợp, PM hỗ trợ cơ chế hợp đồng hoặc nguồn lực theo thẩm quyền.”

## 19. Tự kiểm tra hiểu biết

**Câu 1.** Scrum có định nghĩa vai trò Project Manager là accountability thứ tư trong Scrum Team không?

**Đáp án:** Không. Scrum Team có Product Owner, Scrum Master và Developers. Tổ chức vẫn có thể có PM thực hiện các trách nhiệm quản trị bên ngoài cấu trúc Scrum, nhưng không tự động trao cho PM quyền thay ba accountability đó.

**Câu 2.** PM phụ trách hợp đồng với đối tác có được tự sắp Product Backlog để đáp ứng hợp đồng không?

**Đáp án:** Không mặc định. PM cung cấp dữ kiện, nghĩa vụ và rủi ro; **Product Owner chịu trách nhiệm thứ tự Product Backlog**. Nếu có ràng buộc bên ngoài, các bên cần làm rõ và phối hợp theo thẩm quyền.

**Câu 3.** Scrum Master có bắt buộc tự gọi điện nhà cung cấp, tự ký hợp đồng và tự cấp quyền truy cập để “gỡ trở ngại” không?

**Đáp án:** Không. SM chịu trách nhiệm làm cho trở ngại được tháo gỡ và hỗ trợ hiệu quả Scrum Team; nhiều trở ngại cần hành động từ PM, bộ phận mua sắm, nhà cung cấp hoặc người có quyền tương ứng.

**Câu 4.** Developers đã viết code xong, PM đồng ý nghiệm thu, nhưng kiểm thử tích hợp bắt buộc chưa đạt. Đây có phải Increment Done không?

**Đáp án:** Chưa. Increment phải có thể sử dụng, được tích hợp và đáp ứng Definition of Done. Nghiệm thu quản trị bên ngoài không thay thế tiêu chuẩn Done.

**Câu 5.** Có Sprint Goal rồi, PO có được tự giao một loạt task mới cho từng Developers giữa Sprint không?

**Đáp án:** Không theo cách thay Developers tự quản kế hoạch. Product Owner chịu trách nhiệm Product Backlog, còn Developers thích ứng Sprint Backlog hướng Sprint Goal; các bên trao đổi về thay đổi phạm vi và tác động.

**Câu 6.** Nếu Scrum Team hoàn tất Increment, Scrum có buộc phải phát hành ngay không?

**Đáp án:** Không. Increment có thể sử dụng và đạt DoD không đồng nghĩa đã release. Quyết định phát hành và các kiểm soát liên quan tùy tổ chức và bối cảnh; Sprint Review không phải cổng bắt buộc trước release.

**Câu 7.** Một quản lý tuyến cũng là Scrum Master. Việc đó tự động trao cho người ấy quyền quyết định thứ tự Product Backlog không?

**Đáp án:** Không. Chức danh quản lý nhân sự và accountability Scrum phải được phân biệt. Product Owner chịu trách nhiệm Product Backlog.

**Câu 8.** Khi nhiều nhóm cùng làm một sản phẩm, PM nên tạo một backlog riêng với ưu tiên khác cho từng nhóm để dễ báo cáo không?

**Đáp án:** Không nên tạo các nguồn ưu tiên cạnh tranh. Các nhóm cần phối hợp hướng cùng sản phẩm, Product Goal và Product Backlog theo cách áp dụng Scrum; PM có thể tổng hợp phụ thuộc và mốc mà không phân mảnh quyết định giá trị.

**Câu 9.** Nếu có deadline cố định, PM nên yêu cầu Developers cắt kiểm thử để bảo đảm ngày không?

**Đáp án:** Không. Nhóm cần làm rõ nghĩa vụ, forecast, phạm vi có thể điều chỉnh và điều kiện chất lượng/an toàn bắt buộc; PM giúp phối hợp lựa chọn và thông báo rủi ro.

**Câu 10.** Vì sao chỉ đếm số story points từng Developer là cách kém tin cậy để đánh giá hiệu quả?

**Đáp án:** Points có tính tương đối theo nhóm, story có đóng góp của nhiều người và các việc hỗ trợ, kiểm thử, xử lý rủi ro có thể không được đếm tương xứng. Cần xem kết quả sản phẩm, chất lượng, hợp tác và bối cảnh làm việc.

## 20. Ghi nhớ trọng tâm

- **Scrum định nghĩa ba accountabilities: Product Owner, Scrum Master và Developers.** Không có accountability “Project Manager” trong Scrum, nhưng tổ chức vẫn có những nhu cầu quản trị dự án cần đầu mối.
- **Đừng xóa công việc quản trị, cũng đừng đặt PM làm cấp chỉ đạo song song bên trong Scrum Team.** Phân biệt hợp đồng, ngân sách, cam kết và phối hợp bên ngoài với Product Backlog, Sprint Backlog và DoD.
- **Product Owner chịu trách nhiệm giá trị sản phẩm và thứ tự Product Backlog; Developers tự quản kế hoạch thực hiện và chất lượng; Scrum Master hỗ trợ hiệu quả Scrum và tháo gỡ trở ngại.**
- **PM có thể cung cấp bối cảnh nghĩa vụ, điều phối phụ thuộc, quản trị ngân sách và báo cáo tổng thể** theo thẩm quyền tổ chức, nhưng không tự động có quyền sắp backlog, giao task hay xác nhận Done.
- **Làm rõ quyền quyết định theo tình huống cụ thể**, không chỉ theo tên chức danh. Khi cần, dùng bảng trách nhiệm hoặc working agreement đủ ngắn và có cơ chế chuyển cấp.
- **Thay đổi phạm vi phải đi qua trao đổi về giá trị, Sprint Goal, tính khả thi và chất lượng.** Đừng để hai hệ thống giao việc cùng chỉ đạo Developers.
- **Phân biệt code complete, Increment Done, deployment và release.** Không dùng phê duyệt quản trị để che đi việc chưa đạt Definition of Done.
- **Báo cáo trung thực về mục tiêu, kết quả, chất lượng, phụ thuộc và forecast.** Tránh dùng story points cá nhân hay đếm ticket làm bằng chứng duy nhất về năng suất.
- **Đo giá trị người dùng cùng chất lượng và dòng công việc.** Phản hồi sớm và phần tăng trưởng nhỏ có ích hơn những báo cáo xanh nhưng chưa có sản phẩm dùng được.
- **Cải tiến cơ chế phối hợp thường xuyên.** Khi xuất hiện khoảng trống mới, hãy xác định ai quyết định, ai thực hiện, ai cần tham vấn và điều kiện xem lại.

Một tổ chức áp dụng Scrum hiệu quả không cần phủ nhận những công việc quản trị dự án đang tồn tại. Tổ chức cần **đưa mỗi quyết định về đúng phạm vi trách nhiệm, giữ thông tin minh bạch và trao quyền cho những người tạo giá trị**. Khi PM, PO, SM, Developers và các chuyên môn hỗ trợ phối hợp đúng ranh giới, nhóm có thể tập trung giao phần mềm đạt chất lượng, nhận phản hồi sớm và thích ứng với những thay đổi thực tế.
