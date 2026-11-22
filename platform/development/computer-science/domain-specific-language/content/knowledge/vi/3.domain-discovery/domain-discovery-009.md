# Duy trì bảng thuật ngữ trong quá trình khám phá miền

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích vai trò của bảng thuật ngữ trong hoạt động khám phá miền và thiết kế ngôn ngữ chuyên biệt miền (Domain-Specific Language, DSL).
- Phân biệt thuật ngữ, khái niệm, tên gọi, từ đồng nghĩa và những trường hợp một từ có nhiều nghĩa.
- Xây dựng một mục thuật ngữ có định nghĩa, phạm vi áp dụng, ví dụ, quan hệ và thông tin quản lý cần thiết.
- Tổ chức quy trình thu thập, xác minh, phê duyệt, công bố và cập nhật thuật ngữ cùng các bên liên quan.
- Sử dụng bảng thuật ngữ để giữ sự nhất quán giữa trao đổi nghiệp vụ, mô hình miền, cú pháp và ngữ nghĩa của DSL.

## 1. Bảng thuật ngữ là gì?

Bảng thuật ngữ (glossary) là tập hợp có tổ chức những thuật ngữ quan trọng trong một lĩnh vực, đi kèm định nghĩa và thông tin giúp người đọc hiểu đúng cách sử dụng chúng. Trong một dự án phần mềm, bảng thuật ngữ ghi lại những khái niệm mà các bên liên quan dùng khi mô tả nghiệp vụ, dữ liệu, quy trình và quy tắc.

Khi khám phá một miền để xây dựng DSL, nhóm phát triển thường làm việc với nhiều nguồn thông tin: phỏng vấn chuyên gia nghiệp vụ, tài liệu quy trình, biểu mẫu, màn hình ứng dụng, mã nguồn, cơ sở dữ liệu và các cuộc họp. Cùng một khái niệm có thể được gọi bằng nhiều tên; một tên có thể mang nhiều nghĩa; hoặc các nhóm khác nhau có thể dùng những từ gần giống nhau nhưng chỉ những khái niệm khác nhau. Nếu không ghi nhận và thống nhất cách hiểu, những khác biệt đó dễ đi vào mô hình miền và ngôn ngữ.

Bảng thuật ngữ tạo ra một điểm tham chiếu chung. Khi một thành viên nhắc đến “đơn hàng”, người khác có thể tra cứu để biết thuật ngữ này chỉ đối tượng nào, thời điểm nào nó được tạo, trạng thái nào nó có thể có và nó khác “giỏ hàng” ra sao.

Bảng thuật ngữ không chỉ là danh sách từ và nghĩa từ điển. Một mục hữu ích cần thể hiện cách một thuật ngữ được hiểu và sử dụng trong bối cảnh cụ thể của dự án. Định nghĩa phải giúp người đọc phân biệt khái niệm đó với các khái niệm lân cận, hiểu cách áp dụng và tránh những cách dùng sai phổ biến.

## 2. Vì sao cần duy trì bảng thuật ngữ?

### 2.1. Tạo cách hiểu chung giữa các bên liên quan

Chuyên gia nghiệp vụ, lập trình viên, kiểm thử viên, nhà phân tích và người dùng cuối có thể xuất phát từ những cách nhìn khác nhau. Một thuật ngữ được sử dụng thường xuyên chưa chắc đã được mọi người hiểu giống nhau.

Ví dụ, nhân viên bán hàng có thể gọi một yêu cầu mua hàng là “đơn hàng” ngay khi khách nhấn nút đặt mua. Bộ phận kho có thể chỉ gọi đó là đơn hàng sau khi hệ thống xác nhận thanh toán. Nếu hai nhóm không làm rõ thời điểm tạo và trạng thái của đơn, yêu cầu nghiệp vụ sẽ trở nên mơ hồ.

Khi thuật ngữ được định nghĩa, các cuộc trao đổi có thể tập trung vào quy tắc thực tế thay vì liên tục tranh luận về cách gọi. Bảng thuật ngữ cũng giúp thành viên mới hiểu nhanh những từ chuyên môn của dự án.

### 2.2. Phát hiện sự khác biệt và mâu thuẫn trong miền

Việc thu thập thuật ngữ là một kỹ thuật khám phá miền. Khi so sánh các cách gọi, nhóm có thể phát hiện:

- Hai từ khác nhau nhưng cùng chỉ một khái niệm.
- Một từ được dùng cho hai khái niệm khác nhau.
- Một khái niệm chưa có tên gọi ổn định.
- Các nhóm có định nghĩa khác nhau cho cùng một từ.
- Một quy trình đang gộp nhiều trạng thái hoặc đối tượng vốn cần được phân biệt.

Những khác biệt này là tín hiệu cần điều tra. Không nên tự động xóa khác biệt bằng cách chọn một từ duy nhất. Có thể các nhóm thực sự làm việc với các khái niệm khác nhau hoặc đang vận hành trong các ngữ cảnh riêng biệt.

### 2.3. Giữ mô hình miền nhất quán

Mô hình miền mô tả các khái niệm quan trọng và quan hệ giữa chúng. Nếu tài liệu dùng “khách hàng”, mã nguồn dùng “người mua”, cơ sở dữ liệu dùng “account” nhưng không có quy ước ánh xạ, nhóm khó biết chúng có đại diện cho cùng một khái niệm hay không.

Bảng thuật ngữ liên kết tên gọi với khái niệm đã được thống nhất. Nó hỗ trợ đặt tên cho lớp, thuộc tính, trạng thái, sự kiện, thao tác và quan hệ trong mô hình miền. Khi mô hình thay đổi, bảng thuật ngữ giúp nhóm kiểm tra xem định nghĩa và cách dùng liên quan có cần cập nhật hay không.

### 2.4. Là nền tảng cho từ vựng của DSL

DSL diễn đạt công việc bằng các khái niệm của miền. Từ khóa, tên trường, tên kiểu, tên hành động và thông báo lỗi đều cần phản ánh đúng cách hiểu đã thống nhất.

Ví dụ, nếu bảng thuật ngữ phân biệt rõ “giỏ hàng” với “đơn hàng”, DSL nên dùng hai tên riêng cho hai đối tượng. Nếu cả hai cùng được gọi là order trong ngôn ngữ, người viết quy tắc có thể hiểu sai vòng đời của dữ liệu hoặc áp dụng hành động vào sai đối tượng.

Một bảng thuật ngữ tốt giúp nhóm quyết định:

- Thuật ngữ nào nên trở thành từ khóa hoặc tên kiểu trong DSL.
- Thuật ngữ nào là thuộc tính của một đối tượng.
- Thuật ngữ nào mô tả trạng thái, sự kiện hoặc hành động.
- Tên nào được chấp nhận như bí danh và tên nào cần tránh.
- Những khái niệm nào chỉ có ý nghĩa trong một ngữ cảnh cụ thể.

### 2.5. Hỗ trợ tài liệu, kiểm thử và bảo trì

Định nghĩa rõ giúp viết yêu cầu, tiêu chí chấp nhận, kịch bản kiểm thử và hướng dẫn sử dụng nhất quán. Khi một thuật ngữ đổi nghĩa hoặc bị thay thế, nhóm có thể truy tìm tài liệu, biểu thức DSL và thành phần phần mềm chịu ảnh hưởng.

Đối với DSL đã được sử dụng, thay đổi từ vựng có thể ảnh hưởng đến mã nguồn người dùng viết. Vì vậy, bảng thuật ngữ còn là một phần của quản lý thay đổi và tương thích ngược.

## 3. Phân biệt các khái niệm liên quan

### 3.1. Thuật ngữ và khái niệm

**Khái niệm (concept)** là ý niệm về một đối tượng, sự kiện, thuộc tính, quan hệ hoặc quy tắc trong miền. **Thuật ngữ (term)** là tên gọi được dùng để biểu đạt khái niệm đó trong một ngôn ngữ hoặc cộng đồng.

Một khái niệm có thể có nhiều thuật ngữ, ví dụ “khách hàng”, “người mua” và “buyer”. Ngược lại, một thuật ngữ như “tài khoản” có thể chỉ những khái niệm khác nhau trong kế toán, thương mại điện tử và quản lý người dùng. Vì vậy, cần quản lý cả khái niệm lẫn tên gọi, thay vì chỉ lưu một danh sách chuỗi từ.

### 3.2. Bảng thuật ngữ và từ điển

Từ điển ngôn ngữ thông thường giải thích nghĩa của từ trong ngôn ngữ nói chung. Bảng thuật ngữ của dự án ghi lại ý nghĩa được chấp nhận trong một miền và một phạm vi cụ thể.

Ví dụ, từ “hủy” trong ngôn ngữ thông thường có thể chỉ việc chấm dứt một hoạt động. Trong miền đơn hàng, “hủy đơn” cần được định nghĩa chính xác: ai được hủy, trước trạng thái nào, có cần hoàn tiền hay không và sự kiện nào được ghi nhận.

### 3.3. Bảng thuật ngữ và mô hình miền

Bảng thuật ngữ tập trung vào tên gọi và định nghĩa. Mô hình miền thể hiện thêm cấu trúc, thuộc tính, hành vi, quan hệ, ràng buộc và quy tắc giữa các khái niệm.

Ví dụ, bảng thuật ngữ có thể định nghĩa “Đơn hàng” là yêu cầu mua các sản phẩm được khách hàng gửi và hệ thống tiếp nhận. Mô hình miền có thể mô tả Đơn hàng gồm nhiều Dòng đơn hàng, thuộc về một Khách hàng, có Trạng thái đơn hàng và liên quan đến một hoặc nhiều Giao dịch thanh toán.

Bảng thuật ngữ giúp đặt tên và thống nhất ý nghĩa; mô hình miền giúp diễn tả cách các khái niệm cấu thành hệ thống. Hai tài sản này nên liên kết với nhau.

### 3.4. Bảng thuật ngữ và ngôn ngữ phổ biến thống nhất (Ubiquitous Language)

Trong phương pháp Domain-Driven Design (DDD), Ubiquitous Language là ngôn ngữ chung được nhóm phát triển và chuyên gia miền sử dụng xuyên suốt quá trình trao đổi, mô hình hóa và triển khai. Bảng thuật ngữ là một công cụ quan trọng để ghi lại, giải thích và duy trì ngôn ngữ chung đó.

Ngôn ngữ chung không chỉ tồn tại trong tài liệu. Nó cần xuất hiện nhất quán trong hội thoại, mô hình, mã nguồn, tên DSL và tài liệu vận hành. Nếu bảng thuật ngữ nói “Giao dịch thanh toán” nhưng mã và tài liệu vẫn dùng lẫn lộn “Payment”, “Phiếu thu” và “Đơn thanh toán” cho cùng khái niệm, ngôn ngữ chung chưa được áp dụng đầy đủ.

### 3.5. Bảng thuật ngữ và từ vựng của một bounded context

Trong DDD, bounded context là ranh giới trong đó một mô hình và cách dùng thuật ngữ có ý nghĩa nhất quán. Một thuật ngữ có thể có nghĩa khác nhau ở hai bounded context mà không nhất thiết là sai.

Ví dụ, “Khách hàng” trong ngữ cảnh bán hàng có thể là người đặt đơn; trong ngữ cảnh hỗ trợ, hồ sơ khách hàng có thể bao gồm người liên hệ, lịch sử yêu cầu và tổ chức mà họ đại diện. Nếu hai ngữ cảnh có mô hình khác nhau, bảng thuật ngữ cần ghi rõ phạm vi thay vì ép hai định nghĩa thành một.

Do đó, bảng thuật ngữ toàn dự án có thể đóng vai trò chỉ mục, nhưng mỗi định nghĩa quan trọng cần gắn với miền con hoặc bounded context tương ứng.

## 4. Cấu trúc của một mục thuật ngữ

Không phải dự án nào cũng cần mọi trường dữ liệu. Tuy nhiên, một mục thuật ngữ nên có đủ thông tin để người đọc nhận biết khái niệm, hiểu phạm vi và biết cách sử dụng.

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| ID | Mã định danh ổn định của mục | ORD-001 |
| Thuật ngữ chuẩn | Tên được ưu tiên sử dụng | Đơn hàng |
| Định nghĩa | Ý nghĩa chính xác trong miền | Yêu cầu mua hàng được hệ thống tiếp nhận từ khách hàng |
| Ngữ cảnh | Miền con hoặc bounded context | Bán hàng trực tuyến |
| Loại khái niệm | Đối tượng, sự kiện, trạng thái, hành động, thuộc tính, quy tắc... | Đối tượng |
| Từ đồng nghĩa | Các tên khác cùng chỉ khái niệm | Order |
| Tên không khuyến nghị | Tên dễ gây nhầm lẫn hoặc không còn dùng | Phiếu mua |
| Ví dụ | Trường hợp minh họa đúng | Đơn hàng ORD-2026-001 |
| Phản ví dụ | Trường hợp dễ nhầm nhưng không thuộc khái niệm | Giỏ hàng chưa được gửi |
| Quan hệ | Khái niệm liên quan | Có các Dòng đơn hàng |
| Nguồn | Người hoặc tài liệu xác nhận | Chuyên gia nghiệp vụ bán hàng |
| Chủ sở hữu | Người chịu trách nhiệm nội dung | Product Owner miền bán hàng |
| Trạng thái | Tình trạng xử lý mục | Đã phê duyệt |
| Phiên bản/ngày cập nhật | Dấu vết thay đổi | v1.2, 15/11/2026 |

### 4.1. Định nghĩa cần ngắn gọn nhưng đủ phân biệt

Định nghĩa tốt thường:

- Nêu bản chất của khái niệm bằng ngôn ngữ rõ ràng.
- Giải thích phạm vi hoặc điều kiện để một đối tượng được xem là thuộc khái niệm.
- Phân biệt với các khái niệm gần nghĩa.
- Tránh dùng chính thuật ngữ cần định nghĩa để giải thích vòng quanh.
- Không đưa quy trình triển khai hoặc chi tiết kỹ thuật không cần thiết vào định nghĩa.

Ví dụ chưa tốt:

> Đơn hàng là một order được tạo khi khách mua hàng.

Định nghĩa này chỉ thay từ tiếng Việt bằng tiếng Anh, chưa giải thích điều gì khiến một yêu cầu trở thành đơn hàng.

Ví dụ rõ hơn:

> Đơn hàng là bản ghi đại diện cho yêu cầu mua các sản phẩm mà khách hàng đã gửi và hệ thống bán hàng tiếp nhận. Đơn hàng có mã định danh, khách hàng đặt mua, các dòng hàng, tổng tiền và trạng thái xử lý. Giỏ hàng chưa được gửi chưa phải là đơn hàng.

Định nghĩa thứ hai cho biết phạm vi, các đặc điểm quan trọng và một trường hợp không thuộc khái niệm.

### 4.2. Phân biệt định nghĩa với quy tắc nghiệp vụ

Định nghĩa trả lời “khái niệm này là gì?”. Quy tắc nghiệp vụ trả lời “điều gì được phép, bắt buộc hoặc xảy ra trong hoàn cảnh nào?”.

Ví dụ:

- Định nghĩa: “Đơn hàng đã xác nhận” là đơn hàng đã vượt qua bước kiểm tra và được hệ thống ghi nhận để xử lý.
- Quy tắc: “Chỉ đơn hàng ở trạng thái Chờ xác nhận mới được xác nhận.”

Hai nội dung có liên quan nhưng không nên trộn lẫn. Một mục thuật ngữ có thể liên kết đến các quy tắc áp dụng cho khái niệm đó.

### 4.3. Ghi nhận nguồn và mức độ chắc chắn

Định nghĩa có thể bắt nguồn từ phỏng vấn, quy trình nội bộ, hợp đồng, quy định pháp lý, tài liệu sản phẩm hoặc hành vi hiện tại của phần mềm. Cần ghi nguồn để người đọc biết định nghĩa dựa trên bằng chứng nào và có thể xác minh ở đâu.

Nếu các nguồn mâu thuẫn, hãy đánh dấu mục là đang tranh luận hoặc chờ xác nhận. Không nên biến một giả định của nhóm phát triển thành định nghĩa đã được nghiệp vụ phê duyệt.

## 5. Nhận diện và xử lý các quan hệ giữa thuật ngữ

### 5.1. Từ đồng nghĩa

Từ đồng nghĩa là những cách gọi khác nhau cùng chỉ một khái niệm trong một phạm vi nhất định. Ví dụ, một nhóm có thể gọi “mã đơn hàng”, nhóm khác gọi “số đơn”.

Nhóm cần chọn một thuật ngữ chuẩn cho giao tiếp và DSL, sau đó ghi các tên còn lại làm bí danh hoặc tên tìm kiếm. Bí danh giúp người đọc tìm được mục cần thiết, nhưng không có nghĩa mọi tên đều nên xuất hiện trong cú pháp chính thức.

Không nên kết luận hai từ là đồng nghĩa chỉ vì chúng thường được dùng thay thế nhau trong hội thoại. Hãy hỏi liệu chúng có cùng vòng đời, thuộc tính, quy tắc và hệ quả nghiệp vụ hay không.

### 5.2. Từ gần nghĩa nhưng khác khái niệm

Hai thuật ngữ có thể gần nhau nhưng không thể thay thế. Ví dụ:

- Giỏ hàng là tập hợp sản phẩm khách đang cân nhắc mua.
- Đơn hàng là yêu cầu mua đã được gửi và tiếp nhận.
- Giao dịch thanh toán là hoạt động ghi nhận việc thu hoặc hoàn tiền.

Nếu gộp cả ba thành “đơn mua”, nhóm sẽ mất những ranh giới quan trọng về thời điểm, trạng thái và hành vi.

Để xử lý, hãy mô tả sự khác nhau bằng điều kiện nhận diện và ví dụ. Bảng so sánh ngắn thường hữu ích hơn một định nghĩa dài.

### 5.3. Một thuật ngữ có nhiều nghĩa

Khi một từ được dùng cho nhiều khái niệm, cần xác định đó là đa nghĩa thực sự hay chỉ là cách nói thiếu chính xác.

Ví dụ, “tài khoản” có thể chỉ:

- Hồ sơ đăng nhập của một người dùng.
- Tài khoản kế toán ghi nhận số dư và phát sinh.
- Tài khoản thanh toán tại một tổ chức tài chính.

Đây là các khái niệm khác nhau, có thuộc tính và quy tắc khác nhau. Bảng thuật ngữ nên tạo các mục riêng, có ngữ cảnh và tên chuẩn đủ rõ như “Tài khoản người dùng”, “Tài khoản kế toán” và “Tài khoản thanh toán”.

Nếu các nghĩa tồn tại trong các bounded context khác nhau, hãy giữ nguyên cách dùng địa phương khi nó có giá trị với người dùng của ngữ cảnh đó. Tại ranh giới tích hợp, cần định nghĩa ánh xạ để tránh hiểu nhầm.

### 5.4. Quan hệ rộng hơn, hẹp hơn và thành phần

Các thuật ngữ có thể biểu diễn quan hệ phân loại hoặc cấu thành:

- “Phương thức thanh toán” là khái niệm rộng; “Thẻ ngân hàng” và “Chuyển khoản” là các loại cụ thể.
- “Đơn hàng” gồm một hoặc nhiều “Dòng đơn hàng”.
- “Địa chỉ giao hàng” là một loại địa chỉ được dùng cho mục đích giao nhận.

Hãy ghi quan hệ có tên và chiều rõ ràng, ví dụ “là một loại của”, “bao gồm”, “thuộc về”, “được tạo từ” hoặc “phát sinh từ”. Tránh ghi đơn giản “liên quan đến” nếu mối quan hệ cụ thể đã biết.

### 5.5. Phân biệt đối tượng, trạng thái, sự kiện và hành động

Đây là nguồn gây nhầm lẫn thường gặp trong mô hình hóa miền:

- **Đối tượng:** thứ có định danh hoặc được quản lý trong miền, ví dụ Đơn hàng.
- **Trạng thái:** tình trạng của đối tượng tại một thời điểm, ví dụ Đang xử lý hoặc Đã giao.
- **Sự kiện:** điều đã xảy ra và có ý nghĩa nghiệp vụ, ví dụ Đơn hàng đã được xác nhận.
- **Hành động:** thao tác được yêu cầu thực hiện, ví dụ Xác nhận đơn hàng hoặc Hủy đơn hàng.

Các cách gọi có liên quan nhưng không đồng nghĩa. “Hủy đơn” là hành động; “Đơn hàng đã hủy” là trạng thái hoặc mô tả kết quả; “Yêu cầu hủy đơn được tiếp nhận” có thể là một sự kiện. Phân biệt chúng giúp thiết kế câu lệnh DSL và quy tắc chuyển trạng thái chính xác.

## 6. Quy trình xây dựng và duy trì bảng thuật ngữ

Quy trình dưới đây có thể áp dụng cho dự án mới hoặc dự án đang có hệ thống và tài liệu lâu năm. Nhóm có thể lặp lại các bước khi phát hiện khái niệm mới hoặc khi phạm vi miền thay đổi.

### Bước 1: Xác định phạm vi và người dùng

Trước khi thu thập từ ngữ, cần xác định:

- Miền hoặc miền con nào đang được khám phá?
- Bảng thuật ngữ phục vụ ai: chuyên gia nghiệp vụ, nhóm phát triển, người viết DSL hay người vận hành?
- Tài liệu sẽ dùng trong hội thoại, thiết kế, triển khai hay tất cả các giai đoạn?
- Có những bounded context nào cần tách riêng?

Không nên bắt đầu bằng mục tiêu thu thập tất cả từ ngữ của doanh nghiệp. Hãy giới hạn theo bài toán và nhóm người dùng để bảng thuật ngữ có thể được xác minh và duy trì.

### Bước 2: Thu thập thuật ngữ từ nhiều nguồn

Các nguồn thường hữu ích gồm:

| Nguồn | Có thể tìm thấy | Cần chú ý |
|---|---|---|
| Phỏng vấn chuyên gia | Từ ngữ thực tế, cách giải thích, ngoại lệ | Một người có thể dùng thuật ngữ theo thói quen riêng |
| Workshop mô hình hóa | Điểm bất đồng và cách gọi đang được thương lượng | Ghi lại cả câu hỏi chưa được giải quyết |
| Quy trình và chính sách | Định nghĩa chính thức, điều kiện và trách nhiệm | Tài liệu có thể đã lỗi thời |
| Biểu mẫu và màn hình | Tên trường, nhãn, trạng thái mà người dùng nhìn thấy | Nhãn giao diện có thể bị rút gọn |
| Mã nguồn và API | Tên lớp, hàm, trường dữ liệu và enum | Tên kỹ thuật hiện tại không nhất thiết phản ánh đúng nghiệp vụ |
| Cơ sở dữ liệu và báo cáo | Cấu trúc dữ liệu và tên gọi lịch sử | Tên cột có thể được đặt vì lý do kỹ thuật |
| Hợp đồng và quy định | Thuật ngữ có ý nghĩa pháp lý hoặc ràng buộc | Cần xác định nguồn có thẩm quyền và phạm vi áp dụng |
| Khiếu nại và hỗ trợ | Cách người dùng mô tả vấn đề thực tế | Cách gọi có thể mang tính địa phương hoặc không chính xác |

Khi thu thập, ghi nguyên văn cách gọi và câu nói có ngữ cảnh. Đừng vội chuẩn hóa mọi từ ngay trong buổi phỏng vấn, vì cách gọi ban đầu có thể chứa thông tin quan trọng về cách các nhóm hiểu công việc.

### Bước 3: Tạo danh sách thuật ngữ ứng viên

Tập hợp các từ, cụm từ và cách diễn đạt lặp lại. Có thể bắt đầu từ danh từ chỉ đối tượng, động từ chỉ hành động, tên trạng thái, sự kiện, thuộc tính, vai trò và quy tắc.

Mỗi ứng viên nên có nguồn ghi nhận và ngữ cảnh xuất hiện. Nếu chưa biết định nghĩa, hãy đánh dấu là “chưa xác minh” thay vì đoán.

### Bước 4: Gom nhóm và tìm khái niệm trùng hoặc mơ hồ

So sánh các ứng viên để xác định:

- Những tên có vẻ là từ đồng nghĩa.
- Những từ có nhiều nghĩa.
- Những khái niệm chưa có tên.
- Những tên gần nhau nhưng khác ranh giới.
- Những định nghĩa mâu thuẫn giữa các nguồn.

Có thể tổ chức workshop với chuyên gia để xem xét ví dụ thực tế. Hãy hỏi “trường hợp nào được tính là X?” và “trường hợp nào chắc chắn không phải X?” thay vì chỉ hỏi “X nghĩa là gì?”.

### Bước 5: Viết định nghĩa và ví dụ

Chọn thuật ngữ chuẩn, viết định nghĩa, ghi bí danh, ngữ cảnh, ví dụ và phản ví dụ. Nếu có nhiều nghĩa hợp lệ, tạo các mục riêng và ghi rõ phạm vi.

Định nghĩa cần được kiểm tra bằng tình huống thực tế. Một định nghĩa có thể nghe hợp lý nhưng không phân loại được các trường hợp biên hoặc mâu thuẫn với quy trình hiện tại.

### Bước 6: Xác nhận với người có thẩm quyền trong miền

Chuyên gia miền hoặc chủ sở hữu nghiệp vụ cần xác nhận định nghĩa và ranh giới. Nhóm phát triển có thể đề xuất cách diễn đạt rõ ràng, nhưng không nên tự quyết định ý nghĩa nghiệp vụ chỉ dựa trên tên biến hoặc cấu trúc cơ sở dữ liệu.

Nếu chưa đạt đồng thuận, hãy ghi nhận các cách hiểu, người đưa ra, bằng chứng và quyết định còn chờ. Một mục “đang tranh luận” minh bạch có giá trị hơn một mục được đánh dấu phê duyệt khi chưa ai xác nhận.

### Bước 7: Công bố và áp dụng

Đặt bảng thuật ngữ ở nơi các thành viên có thể tìm thấy và cập nhật. Liên kết mục thuật ngữ với mô hình miền, yêu cầu, tài liệu API, mã nguồn hoặc đặc tả DSL có liên quan.

Khi đặt tên thành phần mới, hãy tra cứu thuật ngữ chuẩn trước. Nếu cần thuật ngữ mới, tạo yêu cầu bổ sung thay vì để mỗi người tự đặt tên.

### Bước 8: Theo dõi thay đổi và rà soát định kỳ

Bảng thuật ngữ phải thay đổi khi hiểu biết về miền thay đổi. Cần ghi người đề xuất, lý do, nội dung trước và sau, ngày hiệu lực, người phê duyệt và các tài sản chịu ảnh hưởng.

Rà soát khi có quy trình mới, thay đổi chính sách, tích hợp hệ thống, mở rộng miền, phát hiện thuật ngữ mơ hồ hoặc chuẩn bị phát hành phiên bản DSL mới.

## 7. Vòng đời và trạng thái của thuật ngữ

Một quy trình trạng thái đơn giản có thể gồm:

~~~text
Ứng viên
   |
   v
Đang định nghĩa
   |
   v
Chờ xác nhận -----> Cần làm rõ
   |                    |
   v                    |
Đã phê duyệt <----------+
   |
   v
Đang sử dụng
   |
   v
Không khuyến nghị / Đã lỗi thời
   |
   v
Đã ngừng sử dụng
~~~

Ý nghĩa các trạng thái:

- **Ứng viên:** thuật ngữ được ghi nhận nhưng chưa có định nghĩa được xác nhận.
- **Đang định nghĩa:** nhóm đang làm rõ khái niệm, phạm vi và ví dụ.
- **Chờ xác nhận:** định nghĩa đã được soạn và cần người có thẩm quyền duyệt.
- **Cần làm rõ:** còn bất đồng hoặc thiếu bằng chứng; cần bổ sung thông tin.
- **Đã phê duyệt:** định nghĩa được chấp nhận trong ngữ cảnh đã ghi.
- **Đang sử dụng:** thuật ngữ đã được áp dụng trong tài liệu, mô hình hoặc DSL.
- **Không khuyến nghị/Đã lỗi thời:** không nên dùng cho nội dung mới, nhưng vẫn cần tra cứu để hiểu tài liệu cũ.
- **Đã ngừng sử dụng:** thuật ngữ không còn được dùng trong phạm vi hiện tại; thông tin lịch sử vẫn được lưu để truy vết.

Không phải mục nào cũng phải đi qua mọi trạng thái. Một thuật ngữ có thể được phê duyệt ngay khi có đủ bằng chứng; một thuật ngữ khác có thể bị loại bỏ nếu chỉ là cách gọi sai. Trạng thái cần phản ánh đúng mức độ chắc chắn và tình trạng áp dụng.

Không xóa mục đã lỗi thời nếu tài liệu, cấu hình hoặc mã DSL cũ vẫn có thể tham chiếu đến nó. Hãy giữ ID và thông tin chuyển đổi để hỗ trợ tra cứu và di chuyển.

## 8. Ví dụ bảng thuật ngữ cho miền bán hàng trực tuyến

Giả sử nhóm đang khám phá miền bán hàng trực tuyến để thiết kế một DSL mô tả quy tắc xử lý đơn hàng. Bảng sau minh họa một phần từ vựng ban đầu:

| Thuật ngữ chuẩn | Định nghĩa ngắn | Bí danh/tên cần phân biệt | Quan hệ |
|---|---|---|---|
| Khách hàng | Cá nhân hoặc tổ chức thực hiện hoạt động mua hàng trong hệ thống | Người mua | Có thể tạo Giỏ hàng và Đơn hàng |
| Giỏ hàng | Tập hợp sản phẩm khách đang lựa chọn trước khi gửi yêu cầu mua | Cart | Có các Dòng giỏ hàng |
| Dòng giỏ hàng | Một mục sản phẩm và số lượng trong Giỏ hàng | Cart item | Tham chiếu Sản phẩm |
| Đơn hàng | Yêu cầu mua đã được khách gửi và hệ thống tiếp nhận | Order; không đồng nhất với Giỏ hàng | Có các Dòng đơn hàng |
| Dòng đơn hàng | Một mục sản phẩm, số lượng và giá được ghi nhận trong Đơn hàng | Order line | Thuộc về một Đơn hàng |
| Giao dịch thanh toán | Bản ghi một lần xử lý thu, xác nhận hoặc hoàn tiền | Payment transaction | Có thể liên quan đến Đơn hàng |
| Trạng thái đơn hàng | Giá trị mô tả giai đoạn xử lý hiện tại của Đơn hàng | Order status | Thay đổi thông qua sự kiện hoặc hành động hợp lệ |
| Yêu cầu hủy đơn | Đề nghị chấm dứt việc xử lý Đơn hàng được gửi bởi chủ thể có quyền | Cancellation request | Có thể được chấp nhận hoặc từ chối |
| Hủy đơn hàng | Hành động chuyển Đơn hàng sang trạng thái hủy theo các điều kiện cho phép | Cancel order | Có thể phát sinh sự kiện Đơn hàng đã hủy |

### 8.1. Phân tích các ranh giới quan trọng

**Giỏ hàng và Đơn hàng:** Giỏ hàng thường có thể được chỉnh sửa trong khi khách lựa chọn. Đơn hàng được tạo khi một điều kiện tiếp nhận đã xảy ra, chẳng hạn khách gửi yêu cầu và hệ thống ghi nhận. Định nghĩa chính xác cần theo quy trình thực tế của tổ chức.

**Đơn hàng và Giao dịch thanh toán:** Một đơn hàng có thể có nhiều lần thử thanh toán, một giao dịch thanh toán có thể thất bại, và việc hoàn tiền có thể phát sinh giao dịch riêng. Vì vậy, không nên dùng “thanh toán” như một trạng thái duy nhất bao trùm mọi hoạt động tài chính nếu mô hình cần phân biệt các lần giao dịch.

**Yêu cầu hủy và Hủy đơn:** Yêu cầu hủy là đề nghị cần được xem xét hoặc xử lý. Hủy đơn là hành động được thực hiện khi điều kiện cho phép. Hai khái niệm này khác nhau nếu hệ thống hỗ trợ phê duyệt, từ chối hoặc xử lý hủy tự động.

### 8.2. Ví dụ một mục thuật ngữ đầy đủ

~~~yaml
id: ORD-001
term: Đơn hàng
context: Bán hàng trực tuyến
conceptType: business-object
definition: >
  Yêu cầu mua các sản phẩm do khách hàng gửi và hệ thống bán hàng tiếp nhận.
  Đơn hàng có mã định danh, các dòng hàng, thông tin khách hàng,
  tổng tiền và trạng thái xử lý.
synonyms:
  - Order
avoid:
  - Giỏ hàng
examples:
  - Đơn hàng ORD-2026-001 đã được tiếp nhận.
counterExamples:
  - Giỏ hàng khách đang chỉnh sửa nhưng chưa gửi.
relations:
  - has-part: Dòng đơn hàng
  - placed-by: Khách hàng
status: approved
owner: Product Owner miền bán hàng
source: Workshop khám phá quy trình đặt hàng
updatedAt: 2026-11-15
~~~

Đây là cấu trúc dữ liệu minh họa, không phải một chuẩn YAML bắt buộc. Dự án có thể dùng Markdown, bảng tính, hệ thống quản lý tri thức hoặc công cụ mô hình hóa, miễn là thông tin có thể tìm kiếm, cập nhật và truy vết.

## 9. Sử dụng bảng thuật ngữ khi thiết kế DSL

### 9.1. Chuyển thuật ngữ thành tên trong ngôn ngữ

Khi một khái niệm đã được xác nhận, nhóm có thể quyết định cách biểu diễn nó trong DSL:

| Vai trò trong miền | Cách biểu diễn có thể có trong DSL |
|---|---|
| Đối tượng | Kiểu hoặc thực thể, ví dụ Order |
| Thuộc tính | Trường, ví dụ order.total |
| Trạng thái | Giá trị enum hoặc điều kiện, ví dụ order.status |
| Sự kiện | Sự kiện miền, ví dụ OrderConfirmed |
| Hành động | Lệnh hoặc thao tác, ví dụ cancel order |
| Quy tắc | Biểu thức điều kiện và kết quả, ví dụ when ... then ... |

Tên cụ thể phụ thuộc vào thiết kế ngôn ngữ, nhưng ý nghĩa của chúng phải khớp với bảng thuật ngữ. Một từ khóa không nên mang nghĩa khác với cách chuyên gia miền đã xác nhận mà không có lý do và tài liệu rõ ràng.

### 9.2. Giữ nhất quán giữa cú pháp và ngữ nghĩa

Giả sử bảng thuật ngữ định nghĩa “Đơn hàng đã xác nhận” là đơn hàng đã vượt qua kiểm tra và được chấp nhận để xử lý. DSL có thể cung cấp điều kiện:

~~~text
when order.status is CONFIRMED
then ...
~~~

Ngữ nghĩa của CONFIRMED phải khớp với định nghĩa đó. Nếu một nhóm hiểu CONFIRMED là “đã thanh toán”, trong khi nhóm khác hiểu là “đã được chấp nhận”, cùng một điều kiện có thể tạo ra hành vi sai.

Khi DSL có tên tiếng Anh còn bảng thuật ngữ dùng tiếng Việt, cần ghi ánh xạ hai chiều. Việc dịch không nên chỉ dựa trên từ điển; cần xác minh rằng hai tên đại diện cho cùng một khái niệm trong đúng ngữ cảnh.

### 9.3. Tránh quá tải tên và từ đồng nghĩa trong cú pháp

Một bảng thuật ngữ có thể lưu nhiều bí danh để hỗ trợ tìm kiếm, nhưng DSL thường nên có một tên chuẩn cho mỗi khái niệm trong một ngữ cảnh. Nếu mọi từ đồng nghĩa đều được chấp nhận như từ khóa, ngôn ngữ sẽ có nhiều cách viết cho cùng một ý nghĩa, làm tăng gánh nặng tài liệu và bảo trì.

Nếu cần hỗ trợ tên cũ, hãy quy định rõ tên đó là bí danh tương thích, tên đã lỗi thời hay tên chỉ được dùng trong một bounded context. Cung cấp thông báo hoặc công cụ chuyển đổi khi người dùng cần thay thế tên cũ.

### 9.4. Tạo thông báo lỗi có ý nghĩa nghiệp vụ

Bảng thuật ngữ giúp thông báo lỗi dùng đúng khái niệm mà người dùng hiểu. Ví dụ, thay vì báo “invalid object state”, công cụ có thể báo “Không thể hủy Đơn hàng đã giao” nếu đây là cách diễn đạt đã được xác nhận.

Thông báo cần nói rõ khái niệm, điều kiện vi phạm và hướng xử lý. Tên trong thông báo phải nhất quán với tên trong cú pháp và tài liệu.

### 9.5. Duy trì liên kết giữa thuật ngữ và đặc tả

Có thể gắn ID thuật ngữ vào tài liệu DSL, đặc tả kiểu, kiểm thử và mã nguồn. Khi định nghĩa đổi, nhóm có thể tìm các thành phần phụ thuộc.

Ví dụ, mục ORD-001 có thể được tham chiếu trong:

- Đặc tả kiểu Order.
- Tài liệu cú pháp truy cập thuộc tính của đơn hàng.
- Quy tắc xác nhận và hủy đơn.
- Bộ kiểm thử trạng thái đơn hàng.
- Hướng dẫn viết quy tắc DSL cho chuyên viên nghiệp vụ.

Liên kết này biến bảng thuật ngữ thành một phần của hệ thống tri thức dự án thay vì một tài liệu rời rạc.

## 10. Quản trị và phân công trách nhiệm

Bảng thuật ngữ chỉ duy trì được khi có người chịu trách nhiệm. Mọi thành viên có thể đề xuất thuật ngữ, nhưng quyền xác nhận ý nghĩa nghiệp vụ cần thuộc về người có hiểu biết và thẩm quyền phù hợp.

| Vai trò | Trách nhiệm |
|---|---|
| Chuyên gia miền | Giải thích khái niệm, cung cấp ví dụ và xác nhận ý nghĩa nghiệp vụ |
| Product Owner hoặc chủ sở hữu nghiệp vụ | Quyết định định nghĩa và ưu tiên khi có xung đột trong phạm vi phụ trách |
| Business Analyst | Thu thập thuật ngữ, ghi nhận nguồn, soạn định nghĩa và điều phối xác nhận |
| Kiến trúc sư hoặc người thiết kế DSL | Đảm bảo cách biểu diễn trong mô hình và ngôn ngữ phản ánh đúng thuật ngữ |
| Lập trình viên | Áp dụng tên chuẩn trong mã, kiểu, API và thông báo lỗi |
| Kiểm thử viên | Dùng định nghĩa và ví dụ để xây dựng trường hợp kiểm thử |
| Người quản lý tài liệu | Duy trì cấu trúc, lịch sử thay đổi, khả năng tìm kiếm và công bố |

Trong nhóm nhỏ, một người có thể đảm nhận nhiều vai trò. Điều quan trọng là phải phân biệt người đề xuất, người xác minh nội dung và người chịu trách nhiệm công bố.

### 10.1. Quy tắc quản trị tối thiểu

Một quy trình đơn giản nên quy định:

1. Ai có thể đề xuất thuật ngữ mới hoặc sửa định nghĩa.
2. Những trường thông tin nào bắt buộc.
3. Ai xác nhận ý nghĩa theo từng miền.
4. Cách xử lý bất đồng và định nghĩa chưa chắc chắn.
5. Cách ghi phiên bản, ngày hiệu lực và lịch sử thay đổi.
6. Cách thông báo cho người đang sử dụng thuật ngữ bị đổi hoặc ngừng dùng.

Không nên biến quy trình thành thủ tục nặng nề khiến mọi chỉnh sửa nhỏ đều bị đình trệ. Mức phê duyệt nên tương ứng với ảnh hưởng của thay đổi.

## 11. Quản lý thay đổi, phiên bản và tương thích

### 11.1. Khi nào cần sửa một mục?

Một mục cần được xem xét khi:

- Phạm vi khái niệm được làm rõ sau workshop hoặc triển khai thử nghiệm.
- Quy trình nghiệp vụ hoặc chính sách thay đổi.
- Phát hiện thuật ngữ đang gộp hai khái niệm.
- Một tên gây hiểu nhầm hoặc không còn được người dùng chấp nhận.
- Bounded context mới sử dụng cùng một từ với nghĩa khác.
- DSL cần thêm tên, kiểu hoặc trạng thái mới.

### 11.2. Phân loại mức độ thay đổi

| Loại thay đổi | Ví dụ | Ảnh hưởng có thể có |
|---|---|---|
| Sửa diễn đạt | Làm rõ câu chữ nhưng không đổi nghĩa | Thấp, chủ yếu ảnh hưởng tài liệu |
| Bổ sung ví dụ | Thêm trường hợp biên đã xác minh | Thấp đến trung bình |
| Bổ sung bí danh | Ghi nhận một cách gọi khác | Có thể ảnh hưởng tìm kiếm và nhập liệu |
| Đổi tên chuẩn | Thay tên đang dùng bằng tên mới | Ảnh hưởng mã DSL, tài liệu và người dùng |
| Thay đổi định nghĩa | Điều chỉnh ranh giới hoặc bản chất khái niệm | Có thể ảnh hưởng mô hình, quy tắc và dữ liệu |
| Tách hoặc hợp nhất khái niệm | Chia một mục thành hai hoặc gộp hai mục | Ảnh hưởng lớn đến mô hình và khả năng tương thích |
| Ngừng sử dụng | Không còn dùng thuật ngữ trong phạm vi hiện tại | Cần hướng dẫn thay thế và giữ dấu vết lịch sử |

Đổi tên chuẩn không nhất thiết có nghĩa khái niệm đã đổi. Ngược lại, giữ nguyên tên nhưng thay đổi định nghĩa có thể là thay đổi ngữ nghĩa rất lớn. Cần ghi riêng hai việc này.

### 11.3. Giữ lịch sử và ID ổn định

Mỗi khái niệm nên có một ID ổn định để tham chiếu. Tên gọi có thể đổi theo thời gian, nhưng ID giúp liên kết lịch sử và các tài liệu phụ thuộc không bị đứt gãy.

Khi tách một khái niệm thành hai, giữ mục cũ ở trạng thái đã thay thế và liên kết đến các mục mới. Khi hợp nhất, ghi rõ các mục cũ chuyển về mục nào. Không tái sử dụng ID đã ngừng dùng cho một khái niệm hoàn toàn khác.

### 11.4. Tương thích với DSL đã phát hành

Nếu DSL đã có người sử dụng, thay đổi tên có thể làm chương trình cũ không phân tích được. Nhóm nên:

- Đánh giá các biểu thức DSL đang dùng tên cũ.
- Quyết định có giữ bí danh tương thích trong một khoảng thời gian hay không.
- Đánh dấu tên cũ là không khuyến nghị và đưa ra hướng thay thế.
- Cung cấp thông báo cảnh báo hoặc công cụ chuyển đổi nếu phù hợp.
- Xác định phiên bản DSL mà thay đổi có hiệu lực.
- Cập nhật ví dụ, tài liệu, parser, kiểm thử và thông báo lỗi.

Ví dụ, DSL phiên bản 1 chấp nhận buyer, còn phiên bản 2 chuẩn hóa thành customer. Nếu hai tên cùng chỉ một khái niệm trong cùng ngữ cảnh, phiên bản 2 có thể tạm chấp nhận buyer như bí danh đã lỗi thời, đồng thời cảnh báo người dùng chuyển sang customer.

## 12. Lựa chọn cách lưu trữ và công cụ

Không có công cụ duy nhất phù hợp với mọi dự án. Điều quan trọng là bảng thuật ngữ dễ tìm, có lịch sử thay đổi, có người chịu trách nhiệm và có thể liên kết với các tài sản khác.

| Cách lưu trữ | Phù hợp khi | Điểm cần cân nhắc |
|---|---|---|
| Markdown trong Git | Nhóm kỹ thuật quản lý bằng pull request và muốn xem lịch sử | Cần quy ước cấu trúc và cách tìm kiếm |
| Bảng tính | Nhóm nhỏ cần lọc, sắp xếp và cùng chỉnh sửa nhanh | Khó biểu diễn quan hệ phức tạp và lịch sử định nghĩa |
| Wiki hoặc hệ thống tri thức | Nhiều nhóm cần tra cứu và liên kết tài liệu | Cần quyền sở hữu và quy trình cập nhật |
| Công cụ mô hình hóa | Cần quản lý quan hệ giữa khái niệm và mô hình | Có thể tốn công thiết lập và đào tạo |
| Kho thuật ngữ chuyên dụng | Cần quản lý đa ngôn ngữ, quy trình duyệt và API | Cần đánh giá tích hợp, chi phí và mức phù hợp |

Một dự án nhỏ có thể bắt đầu bằng Markdown hoặc bảng tính. Khi số lượng thuật ngữ và nhóm sử dụng tăng, có thể chuyển sang kho tri thức có tìm kiếm, phân quyền, phiên bản và liên kết.

### 12.1. Cấu trúc thư mục gợi ý

~~~text
domain-knowledge/
├── glossary/
│   ├── README.md
│   ├── sales.md
│   ├── payment.md
│   └── glossary-data.yml
├── domain-model/
│   ├── sales-context.md
│   └── payment-context.md
└── dsl/
    ├── language-reference.md
    └── migration-guide.md
~~~

Đây chỉ là một cách tổ chức. Dự án có thể đặt thuật ngữ cạnh mô hình miền hoặc quản lý trong một hệ thống tài liệu tập trung. Tránh sao chép định nghĩa sang nhiều nơi mà không có nguồn chuẩn, vì các bản sao sẽ dần khác nhau.

## 13. Tiêu chí đánh giá chất lượng bảng thuật ngữ

Một bảng thuật ngữ hữu ích có thể được xem xét qua các tiêu chí sau:

| Tiêu chí | Dấu hiệu đạt yêu cầu |
|---|---|
| Có phạm vi | Người đọc biết bảng áp dụng cho miền hoặc ngữ cảnh nào |
| Định nghĩa rõ | Có thể xác định trường hợp thuộc và không thuộc khái niệm |
| Nhất quán | Các thuật ngữ liên quan không mâu thuẫn hoặc trùng nghĩa không giải thích |
| Có ngữ cảnh | Các từ đa nghĩa được tách hoặc gắn với bounded context |
| Có nguồn | Biết ai hoặc tài liệu nào xác nhận định nghĩa |
| Có người sở hữu | Có người chịu trách nhiệm xử lý đề xuất thay đổi |
| Có trạng thái | Phân biệt mục ứng viên, đang tranh luận và đã phê duyệt |
| Có lịch sử | Truy được ai thay đổi, thay đổi gì và vì sao |
| Có khả năng tìm kiếm | Người dùng tra cứu được cả tên chuẩn và bí danh |
| Được áp dụng | Mô hình, tài liệu và DSL sử dụng thuật ngữ theo quy ước |

Có thể theo dõi thêm các chỉ số vận hành như số mục chưa xác nhận, số yêu cầu thay đổi đang chờ, số thuật ngữ trùng lặp được phát hiện và thời gian xử lý một đề xuất. Các chỉ số này giúp nhận biết bảng thuật ngữ có được duy trì hay chỉ tồn tại trên giấy.

Không nên đánh giá chất lượng chỉ bằng số lượng thuật ngữ. Một bảng có ít mục nhưng định nghĩa chính xác và được sử dụng thường xuyên có thể hữu ích hơn một danh sách rất dài không ai xác nhận.

## 14. Những lỗi thường gặp khi duy trì bảng thuật ngữ

### 14.1. Chỉ thu thập từ mà không xác minh nghĩa

Danh sách tên gọi không giải quyết được sự mơ hồ. Mỗi thuật ngữ quan trọng cần định nghĩa, ví dụ và nguồn xác nhận.

### 14.2. Ép mọi nhóm dùng một từ cho mọi ngữ cảnh

Các bounded context có thể có mô hình và cách dùng từ riêng. Hãy thống nhất tại ranh giới tích hợp, đồng thời giữ các định nghĩa địa phương khi chúng phản ánh đúng công việc của nhóm.

### 14.3. Nhầm tên kỹ thuật với khái niệm nghiệp vụ

Tên cột, tên lớp hoặc tên API có thể phản ánh lịch sử triển khai. Không nên mặc nhiên coi chúng là định nghĩa chuẩn. Cần so sánh với cách chuyên gia mô tả nghiệp vụ và hành vi thực tế.

### 14.4. Định nghĩa vòng quanh hoặc quá rộng

Nếu định nghĩa chỉ lặp lại từ đang giải thích, người đọc không hiểu thêm điều gì. Nếu định nghĩa bao gồm quá nhiều trường hợp, nó không còn giúp phân biệt khái niệm.

### 14.5. Không ghi ví dụ và phản ví dụ

Các từ gần nghĩa thường chỉ được phân biệt rõ khi có tình huống cụ thể. Ví dụ và phản ví dụ giúp chuyên gia kiểm tra định nghĩa và giúp người mới hiểu ranh giới.

### 14.6. Không chỉ định chủ sở hữu

Khi không ai chịu trách nhiệm, mục đang tranh luận sẽ tồn tại mãi và các thay đổi không được cập nhật. Mỗi miền cần người có thẩm quyền xác nhận.

### 14.7. Không lưu lịch sử và trạng thái lỗi thời

Xóa tên cũ có thể khiến người đọc không hiểu tài liệu, dữ liệu hoặc mã DSL cũ. Hãy giữ mục lịch sử và liên kết đến tên thay thế.

### 14.8. Bảng thuật ngữ tách rời khỏi công việc hằng ngày

Nếu thành viên không tra cứu hoặc cập nhật bảng khi viết yêu cầu, mô hình và mã nguồn, bảng sẽ nhanh chóng lỗi thời. Hãy đưa việc tra cứu và đề xuất thuật ngữ vào quy trình phát triển thông thường.

## 15. Ví dụ xử lý một bất đồng thuật ngữ

Trong một workshop, nhóm bán hàng dùng từ “khách mua” để chỉ người tạo đơn. Nhóm chăm sóc khách hàng dùng “khách hàng” để chỉ hồ sơ có thông tin liên hệ và lịch sử hỗ trợ. Nhóm kỹ thuật có một bảng users dùng chung cho người mua, nhân viên và quản trị viên.

Nếu nhóm chọn ngay một tên duy nhất là “Khách hàng”, ba cách hiểu có thể bị trộn lẫn. Cách xử lý có hệ thống gồm:

1. Ghi lại từng cách dùng cùng nguồn và câu ví dụ.
2. Hỏi nhóm bán hàng: đối tượng này có phải người hoặc tổ chức đứng tên đặt mua không?
3. Hỏi nhóm chăm sóc: hồ sơ hỗ trợ có bao gồm người liên hệ chưa từng đặt hàng không?
4. Hỏi nhóm kỹ thuật: users đại diện cho danh tính đăng nhập hay đối tượng nghiệp vụ?
5. So sánh vòng đời, định danh, thuộc tính và hành vi của từng đối tượng.
6. Xác định có một khái niệm chung hay nhiều khái niệm được liên kết.
7. Ghi các mục riêng nếu ranh giới khác nhau, đồng thời mô tả quan hệ và ánh xạ.

Kết quả có thể là:

- **Người dùng hệ thống:** danh tính có thể đăng nhập và sử dụng chức năng.
- **Khách hàng mua hàng:** cá nhân hoặc tổ chức thực hiện hoạt động mua trong miền bán hàng.
- **Hồ sơ hỗ trợ:** tập hợp thông tin được nhóm chăm sóc sử dụng để quản lý liên hệ và yêu cầu.

Ba khái niệm có thể liên kết trong một số trường hợp, nhưng không mặc nhiên đồng nhất. Khi thiết kế DSL, nhóm cần quyết định quy tắc nào áp dụng cho Khách hàng mua hàng, quy tắc nào áp dụng cho Người dùng hệ thống và cách biểu diễn một người có nhiều vai trò.

Ví dụ này cho thấy bảng thuật ngữ không chỉ giải quyết cách viết. Nó giúp nhóm khám phá cấu trúc thực tế của miền và phát hiện các ranh giới mô hình.

## 16. Checklist thực hành cho một lần cập nhật

Khi đề xuất thuật ngữ mới hoặc sửa mục hiện có, người phụ trách có thể dùng các câu hỏi sau:

1. Thuật ngữ này thuộc miền con hoặc bounded context nào?
2. Khái niệm mà thuật ngữ biểu đạt là gì?
3. Có thuật ngữ nào hiện có chỉ cùng khái niệm không?
4. Có từ nào giống tên này nhưng mang nghĩa khác không?
5. Định nghĩa có chỉ ra ranh giới và trường hợp không thuộc không?
6. Có ví dụ và phản ví dụ thực tế không?
7. Nguồn nào xác nhận nội dung và ai có quyền phê duyệt?
8. Thuật ngữ này là đối tượng, thuộc tính, trạng thái, sự kiện, hành động hay quy tắc?
9. Những mô hình, tài liệu, API, biểu thức DSL và kiểm thử nào chịu ảnh hưởng?
10. Có cần bí danh, tên thay thế hoặc kế hoạch chuyển đổi không?
11. Trạng thái, ID, ngày hiệu lực và lịch sử đã được cập nhật chưa?
12. Người sử dụng có thể tìm thấy và hiểu cách dùng thuật ngữ sau khi công bố không?

## 17. Bài tập tự kiểm tra

### Bài 1: Viết một mục thuật ngữ

Chọn một khái niệm trong miền đăng ký khóa học, chẳng hạn “Học viên”, “Lớp học”, “Buổi học” hoặc “Đăng ký”. Hãy viết mục thuật ngữ gồm tên chuẩn, định nghĩa, ngữ cảnh, từ đồng nghĩa, ví dụ, phản ví dụ, quan hệ và nguồn xác nhận.

Sau đó, nhờ một người khác đọc định nghĩa và phân loại ba tình huống. Nếu hai người phân loại khác nhau, hãy điều chỉnh định nghĩa để ranh giới rõ hơn.

### Bài 2: Phân biệt từ đồng nghĩa và đa nghĩa

Một nhóm dùng “tài khoản” để chỉ hồ sơ đăng nhập; nhóm khác dùng “tài khoản” để chỉ tài khoản ghi sổ kế toán. Hãy xác định đây là từ đồng nghĩa, từ đa nghĩa hay cùng một khái niệm. Đề xuất cách ghi hai mục trong bảng thuật ngữ và giải thích vì sao.

### Bài 3: Phân biệt hành động, sự kiện và trạng thái

Với các cụm từ “Xác nhận đơn hàng”, “Đơn hàng đã xác nhận” và “Đơn hàng đang chờ xác nhận”, hãy phân loại đâu là hành động, sự kiện hoặc trạng thái. Có thể cần tách “hành động xác nhận” và “sự kiện đã xác nhận” nếu hệ thống ghi nhận việc xảy ra.

### Bài 4: Xử lý thay đổi tên trong DSL

Một DSL đang dùng tên buyer, nhưng nhóm nghiệp vụ thống nhất thuật ngữ chuẩn mới là “Khách hàng” và tên DSL được chọn là customer. Hãy lập kế hoạch cập nhật bảng thuật ngữ, tài liệu, parser, ví dụ, kiểm thử và người dùng đang có biểu thức cũ. Xác định có cần giữ buyer như bí danh tương thích trong một phiên bản hay không.

### Bài 5: Tìm ranh giới giữa các ngữ cảnh

Trong hệ thống bệnh viện giả định, từ “bệnh nhân” xuất hiện trong tiếp nhận, khám bệnh, thanh toán và chăm sóc sau khám. Hãy tìm xem mỗi ngữ cảnh có cần cùng một định nghĩa hay có những khái niệm riêng như “người đến khám”, “hồ sơ bệnh án” và “người thanh toán”. Nêu cách bảng thuật ngữ ghi nhận các ranh giới và ánh xạ.

## Kết luận

Duy trì bảng thuật ngữ là hoạt động liên tục trong khám phá miền. Bảng ghi lại khái niệm, tên gọi chuẩn, định nghĩa, ngữ cảnh, ví dụ, quan hệ, nguồn và trạng thái để các bên liên quan có thể dùng chung một cách hiểu. Việc quản lý đồng nghĩa, đa nghĩa, ranh giới giữa các khái niệm và lịch sử thay đổi giúp mô hình miền rõ ràng hơn. Khi thiết kế DSL, bảng thuật ngữ trở thành cơ sở để đặt tên cho kiểu, trường, trạng thái, sự kiện, hành động và thông báo lỗi. Một bảng thuật ngữ có giá trị khi được xác minh bởi người hiểu miền, có chủ sở hữu, được cập nhật theo thay đổi và được sử dụng thực tế trong tài liệu, mô hình, mã nguồn và ngôn ngữ.
