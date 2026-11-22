# Kịch bản sử dụng

Trong giai đoạn khám phá miền của một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL), nhóm cần hiểu người dùng muốn hoàn thành công việc gì, họ tương tác với hệ thống trong điều kiện nào và hệ thống phải phản hồi ra sao. **Kịch bản sử dụng** (*use case scenario*) mô tả một tình huống cụ thể trong đó một tác nhân tương tác với hệ thống để đạt được mục tiêu. Nó biến mô tả nghiệp vụ chung thành chuỗi hành động, quyết định và kết quả có thể thảo luận, kiểm chứng.

Kịch bản sử dụng đặc biệt hữu ích khi khám phá miền vì nó giúp nhóm phát hiện các khái niệm, dữ liệu, quy tắc, trạng thái, sự kiện và ngoại lệ mà DSL cần biểu diễn. Thay vì bắt đầu bằng câu hỏi “DSL cần có những câu lệnh nào?”, nhóm có thể bắt đầu từ công việc thực tế: ai muốn làm gì, điều kiện bắt đầu là gì, những bước nào diễn ra, và điều gì được xem là hoàn thành thành công.

## 1. Kịch bản sử dụng là gì?

Một **ca sử dụng** (*use case*) mô tả một mục tiêu mà một tác nhân đạt được thông qua tương tác với hệ thống. Ca sử dụng thường bao gồm nhiều kịch bản: kịch bản thành công chính và các biến thể hoặc trường hợp ngoại lệ.

Một **kịch bản** (*scenario*) là một chuỗi cụ thể các bước tương tác trong một hoàn cảnh xác định. Kịch bản thành công chính mô tả con đường thông thường dẫn đến mục tiêu. Kịch bản thay thế mô tả một lựa chọn hoặc nhánh khác vẫn có thể hoàn thành mục tiêu. Kịch bản ngoại lệ mô tả điều gì xảy ra khi một điều kiện không được đáp ứng hoặc một bước thất bại.

Ví dụ, ca sử dụng “Đặt phòng họp” có thể có các kịch bản:

- Người dùng chọn phòng còn trống và đặt phòng thành công.
- Phòng được chọn vừa được người khác đặt; người dùng chọn khung giờ khác.
- Người dùng không có quyền đặt phòng có thiết bị đặc biệt.
- Hệ thống lịch không phản hồi; yêu cầu được giữ ở trạng thái chờ hoặc bị từ chối theo chính sách.

Các kịch bản này cùng hướng đến việc hiểu mục tiêu đặt phòng và các quy tắc của miền. Chúng không phải danh sách từng lần nhấp chuột trên giao diện. Nhóm quan tâm đến hành động nghiệp vụ, quyết định và kết quả có ý nghĩa đối với miền.

### Phân biệt ca sử dụng và kịch bản

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Ca sử dụng | Mục tiêu tương tác ở mức đủ lớn để mang lại kết quả có ý nghĩa cho tác nhân. | Đặt phòng họp. |
| Kịch bản chính | Chuỗi bước điển hình dẫn đến kết quả thành công. | Chọn phòng, chọn giờ, kiểm tra khả dụng, xác nhận đặt phòng. |
| Kịch bản thay thế | Một nhánh khác của luồng tương tác, thường vẫn đạt mục tiêu. | Phòng đầu tiên không phù hợp nên người dùng chọn phòng khác. |
| Kịch bản ngoại lệ | Nhánh xử lý khi điều kiện hoặc thao tác không thể tiếp tục như dự kiến. | Dịch vụ lịch bị lỗi nên không thể xác nhận đặt phòng. |

Trong thực tế, đôi khi người viết dùng “kịch bản sử dụng” để chỉ toàn bộ mô tả ca sử dụng, bao gồm các luồng chính và luồng phụ. Điều quan trọng là tài liệu phải nói rõ đang mô tả mục tiêu tổng quát hay một đường đi cụ thể.

## 2. Vì sao dùng kịch bản trong khám phá miền DSL?

DSL cần diễn đạt những điều người dùng thực sự làm và những quy tắc chi phối công việc đó. Kịch bản cung cấp ngữ cảnh cụ thể để khám phá những thông tin này.

**Làm rõ mục tiêu và phạm vi.** Một kịch bản cho thấy hệ thống cần hỗ trợ mục tiêu nào, điểm bắt đầu và điểm kết thúc ở đâu. Điều này giúp tránh đưa vào DSL những hoạt động không thuộc miền đang xem xét.

**Khám phá thuật ngữ và khái niệm miền.** Khi mô tả các bước, người tham gia thường sử dụng các danh từ như phòng, khung giờ, yêu cầu đặt chỗ, người tổ chức, thiết bị và trạng thái xác nhận. Đây có thể là ứng viên cho khái niệm, thực thể hoặc giá trị trong mô hình miền.

**Phát hiện hành động và sự kiện.** Các động từ như kiểm tra khả dụng, giữ chỗ, xác nhận, hủy và thông báo gợi ý các thao tác hoặc sự kiện mà DSL cần mô tả.

**Làm rõ quy tắc nghiệp vụ.** Các điều kiện như “chỉ người thuộc bộ phận được phép mới được đặt phòng có thiết bị chuyên dụng” hoặc “không thể đặt hai cuộc họp trùng thời gian trong cùng một phòng” có thể trở thành ràng buộc và điều kiện kiểm tra.

**Tìm ra trạng thái và chuyển trạng thái.** Một yêu cầu có thể đi từ mới tạo sang chờ xác nhận, đã xác nhận, bị từ chối hoặc đã hủy. Kịch bản cho thấy sự kiện nào gây ra chuyển đổi và ai được phép thực hiện.

**Nhận diện yêu cầu phi chức năng.** Kịch bản cũng làm lộ yêu cầu về thời gian phản hồi, khả năng truy vết, bảo mật, độ tin cậy, tính sẵn sàng và cách phục hồi khi dịch vụ phụ thuộc gặp lỗi.

**Tạo cơ sở kiểm thử.** Một kịch bản được viết rõ có thể chuyển thành ví dụ kiểm thử, tiêu chí chấp nhận hoặc bộ kiểm thử ngữ nghĩa cho DSL.

## 3. Các thành phần của một kịch bản sử dụng

Một kịch bản có thể được ghi ở nhiều mức độ chi tiết. Với hoạt động khám phá miền, nên ghi đủ thông tin để người nghiệp vụ và nhóm kỹ thuật cùng hiểu, đồng thời tránh mô tả quá sâu các thao tác giao diện không liên quan đến quy tắc miền.

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Tên ca sử dụng | Tác nhân muốn đạt được mục tiêu gì? |
| Mục tiêu | Kết quả có ý nghĩa mà tác nhân cần đạt là gì? |
| Phạm vi hệ thống | Hệ thống hoặc miền nào đang được mô tả? |
| Tác nhân chính | Ai khởi tạo tương tác và nhận lợi ích trực tiếp? |
| Tác nhân phụ | Người hoặc hệ thống nào hỗ trợ tương tác? |
| Bên liên quan và mối quan tâm | Ai quan tâm đến kết quả, quy tắc hoặc rủi ro của ca sử dụng? |
| Tiền điều kiện | Điều gì phải đúng trước khi luồng bắt đầu? |
| Kích hoạt | Sự kiện nào khiến ca sử dụng bắt đầu? |
| Luồng thành công chính | Những bước nào đưa tác nhân đến mục tiêu? |
| Luồng thay thế | Có lựa chọn hợp lệ nào khác trong quá trình thực hiện? |
| Luồng ngoại lệ | Điều gì xảy ra khi điều kiện không thỏa mãn hoặc thao tác thất bại? |
| Hậu điều kiện | Trạng thái hệ thống như thế nào sau khi kết thúc? |
| Quy tắc nghiệp vụ | Chính sách hoặc ràng buộc nào chi phối các bước? |
| Dữ liệu liên quan | Thông tin nào được đọc, tạo, thay đổi hoặc trao đổi? |
| Giả định và vấn đề mở | Nội dung nào chưa được xác nhận hoặc cần quyết định thêm? |

Không phải ca sử dụng nào cũng cần mọi trường. Có thể dùng mẫu ngắn trong buổi phỏng vấn và bổ sung chi tiết sau khi xác nhận với người có thẩm quyền.

### Tác nhân chính và tác nhân phụ

**Tác nhân** (*actor*) là vai trò bên ngoài ranh giới hệ thống đang xét, tương tác với hệ thống để đạt mục tiêu hoặc hỗ trợ một tương tác. Tác nhân có thể là con người, một tổ chức hoặc một hệ thống phần mềm khác.

- **Tác nhân chính** khởi tạo ca sử dụng để đạt mục tiêu. Ví dụ: nhân viên muốn đặt phòng họp.
- **Tác nhân phụ** cung cấp dịch vụ hoặc thông tin cho ca sử dụng. Ví dụ: dịch vụ danh tính xác minh người dùng, hệ thống lịch kiểm tra xung đột, dịch vụ thông báo gửi email.

Vai trò tác nhân phụ phụ thuộc vào ranh giới hệ thống được chọn. Nếu đang mô hình hóa riêng dịch vụ đặt phòng, hệ thống lịch bên ngoài là tác nhân. Nếu mô hình hóa toàn bộ nền tảng lịch, thành phần lịch có thể nằm bên trong ranh giới và không còn là tác nhân bên ngoài.

Không nên nhầm tác nhân với một cá nhân cụ thể. “Nhân viên tổ chức cuộc họp” là vai trò; một người có thể đảm nhiệm vai trò đó trong tình huống này và vai trò khác trong tình huống khác.

### Tiền điều kiện, kích hoạt và hậu điều kiện

- **Tiền điều kiện** là điều kiện phải đúng trước khi ca sử dụng bắt đầu. Ví dụ: người dùng đã đăng nhập và có quyền truy cập danh sách phòng.
- **Kích hoạt** là sự kiện khởi đầu tương tác. Ví dụ: người dùng gửi yêu cầu đặt phòng cho một khung giờ.
- **Hậu điều kiện** mô tả điều phải đúng sau khi ca sử dụng kết thúc. Ví dụ: nếu đặt thành công, một lượt đặt phòng được ghi nhận và không gian tương ứng được đánh dấu đã có người sử dụng trong khung giờ đó.

Hậu điều kiện nên phân biệt rõ kết quả thành công và kết quả khi thất bại. Một kịch bản bị từ chối có thể không tạo lượt đặt phòng, nhưng hệ thống vẫn cần ghi nhận lý do từ chối hoặc lưu dấu vết kiểm toán.

## 4. Cách khám phá và viết kịch bản sử dụng

### Bước 1: Chọn mục tiêu nghiệp vụ

Bắt đầu bằng một mục tiêu mà một vai trò muốn hoàn thành. Mục tiêu nên thể hiện kết quả, chẳng hạn “Đặt phòng họp”, “Hủy lượt đặt phòng” hoặc “Phê duyệt yêu cầu mua hàng”. Tránh đặt tên theo màn hình hoặc thao tác kỹ thuật như “Mở trang phòng họp” hay “Nhấn nút Lưu”.

Một ca sử dụng thường có quy mô đủ để tạo ra giá trị quan sát được cho tác nhân. Nếu mục tiêu quá nhỏ, tài liệu dễ trở thành mô tả giao diện. Nếu quá lớn, nó có thể gộp nhiều mục tiêu độc lập và khó xác định ranh giới.

### Bước 2: Xác định ranh giới hệ thống và tác nhân

Vẽ một đường ranh giới quanh hệ thống hoặc miền đang khám phá. Liệt kê vai trò bên ngoài tương tác với hệ thống, gồm người dùng và hệ thống phụ trợ. Ghi rõ ai khởi tạo, ai cung cấp dữ liệu và ai nhận kết quả.

Hãy kiểm tra tác nhân ở cả luồng bình thường lẫn luồng ngoại lệ. Một bộ phận hỗ trợ có thể chỉ xuất hiện khi có tranh chấp; một hệ thống bên ngoài có thể chỉ được gọi khi cần xác thực hoặc thanh toán.

### Bước 3: Viết luồng thành công chính

Mô tả các bước theo thứ tự từ lúc tác nhân khởi tạo đến khi đạt mục tiêu. Mỗi bước nên thể hiện một hành động hoặc phản hồi có ý nghĩa:

1. Tác nhân thực hiện một hành động hoặc cung cấp thông tin.
2. Hệ thống kiểm tra điều kiện hoặc thực hiện một xử lý.
3. Hệ thống trả kết quả hoặc tạo ra một thay đổi trong miền.
4. Tác nhân tiếp tục dựa trên kết quả đó.

Viết bằng ngôn ngữ nghiệp vụ, tránh đưa tên lớp, bảng cơ sở dữ liệu, endpoint hoặc tên hàm vào luồng nếu người tham gia chưa cần đến chi tiết kỹ thuật đó.

### Bước 4: Hỏi “nếu điều kiện thay đổi thì sao?”

Với mỗi bước, tìm các nhánh có thể xảy ra:

- Dữ liệu không hợp lệ hoặc bị thiếu thì sao?
- Tác nhân không có quyền thực hiện thì sao?
- Một tài nguyên không còn khả dụng thì sao?
- Hệ thống phụ trợ không phản hồi thì sao?
- Một quy tắc nghiệp vụ ngăn hành động thì sao?
- Tác nhân đổi ý, hủy hoặc quay lại bước trước thì sao?
- Hai yêu cầu đồng thời cùng thay đổi một tài nguyên thì sao?

Ghi mỗi nhánh tại bước nơi nó phát sinh và mô tả kết quả cuối cùng. Đừng chỉ ghi “xảy ra lỗi”; cần làm rõ hệ thống giữ nguyên dữ liệu, hoàn tác thay đổi, chuyển sang trạng thái chờ hay yêu cầu người dùng xử lý.

### Bước 5: Rút ra quy tắc, dữ liệu và thuật ngữ

Đánh dấu danh từ, động từ, điều kiện và trạng thái xuất hiện trong kịch bản. Với mỗi mục, hỏi người có chuyên môn:

- Khái niệm này có định nghĩa chính thức không?
- Có thuộc tính hoặc giá trị nào bắt buộc?
- Ai sở hữu hoặc có quyền thay đổi nó?
- Điều kiện nào làm nó hợp lệ?
- Hành động nào có thể làm trạng thái thay đổi?
- Có tên gọi khác hoặc cách hiểu khác giữa các bộ phận không?

Đây là bước chuyển từ câu chuyện nghiệp vụ sang hiểu biết có cấu trúc về miền. Không nên tự động biến mọi danh từ thành một thực thể hoặc mọi động từ thành một câu lệnh DSL. Cần xác nhận ý nghĩa và vòng đời của chúng trước.

### Bước 6: Xác nhận với người hiểu miền

Đọc lại kịch bản cùng tác nhân hoặc chuyên gia nghiệp vụ. Yêu cầu họ kể một trường hợp thật, chỉ ra bước bị thiếu, sửa thuật ngữ và xác nhận điều kiện. Với các quyết định có ảnh hưởng lớn, cần xác định ai có thẩm quyền phê duyệt quy tắc.

Sau khi thống nhất, chuyển các kịch bản đại diện thành ví dụ kiểm thử hoặc tiêu chí chấp nhận. Khi mô hình miền hoặc DSL thay đổi, quay lại kiểm tra các kịch bản để bảo đảm chúng vẫn được hỗ trợ.

## 5. Ví dụ đầy đủ: Đặt phòng họp

Giả sử miền đang khám phá là quản lý việc đặt phòng họp trong một tổ chức. DSL dự kiến hỗ trợ mô tả chính sách và quy trình đặt phòng. Ca sử dụng dưới đây minh họa cách mô tả nghiệp vụ trước khi quyết định cú pháp DSL.

### Thông tin ca sử dụng

| Trường | Mô tả |
|---|---|
| Mã | UC-01 |
| Tên | Đặt phòng họp |
| Mục tiêu | Người tổ chức có một phòng phù hợp trong khoảng thời gian cần thiết. |
| Phạm vi | Dịch vụ quản lý đặt phòng họp. |
| Tác nhân chính | Nhân viên tổ chức cuộc họp. |
| Tác nhân phụ | Dịch vụ xác thực, hệ thống lịch và dịch vụ thông báo. |
| Bên liên quan | Người tổ chức, người quản lý cơ sở vật chất, nhóm vận hành và bộ phận kiểm soát quyền truy cập. |
| Tiền điều kiện | Người dùng đã được xác thực và có quyền yêu cầu đặt phòng. |
| Kích hoạt | Người dùng gửi yêu cầu đặt một phòng cho khoảng thời gian xác định. |
| Hậu điều kiện thành công | Lượt đặt phòng được ghi nhận, thời gian được giữ cho cuộc họp và người tổ chức nhận xác nhận. |
| Hậu điều kiện thất bại | Không có lượt đặt phòng hợp lệ mới; lý do thất bại được cung cấp và ghi nhận theo chính sách. |

### Luồng thành công chính

1. Nhân viên cung cấp thời gian bắt đầu, thời gian kết thúc, số người tham dự và các yêu cầu về thiết bị.
2. Hệ thống kiểm tra thông tin bắt buộc và quyền đặt phòng của nhân viên.
3. Hệ thống tìm các phòng đáp ứng sức chứa, thiết bị và khoảng thời gian yêu cầu.
4. Hệ thống hiển thị các phòng phù hợp và thông tin liên quan.
5. Nhân viên chọn một phòng.
6. Hệ thống kiểm tra lại khả dụng của phòng tại thời điểm xác nhận.
7. Hệ thống tạo lượt đặt phòng và ghi nhận người tổ chức, thời gian, phòng và mục đích cuộc họp.
8. Hệ thống gửi xác nhận cho nhân viên và cập nhật lịch phòng.

### Luồng thay thế và ngoại lệ

| Điểm phát sinh | Điều kiện | Cách xử lý và kết quả |
|---|---|---|
| Bước 2 | Người dùng không có quyền đặt phòng. | Từ chối yêu cầu, giải thích quyền còn thiếu và không tạo lượt đặt phòng. |
| Bước 3 | Không có phòng đáp ứng tất cả yêu cầu. | Đề xuất thay đổi thời gian, sức chứa hoặc thiết bị; người dùng có thể điều chỉnh yêu cầu. |
| Bước 6 | Phòng vừa được người khác đặt. | Không xác nhận phòng đó; hiển thị lựa chọn còn khả dụng để người dùng chọn lại. |
| Bước 7 | Dữ liệu lịch không thể ghi nhận. | Không thông báo đặt thành công; xử lý giao dịch theo chính sách nhất quán và cung cấp trạng thái rõ ràng. |
| Bước 8 | Dịch vụ gửi thông báo gặp lỗi sau khi lượt đặt đã được ghi nhận. | Giữ kết quả đặt phòng theo chính sách; ghi nhận lỗi gửi thông báo và cho phép gửi lại hoặc thông báo qua kênh khác. |
| Sau bước 7 | Người dùng yêu cầu hủy lượt đặt phòng. | Chuyển sang ca sử dụng “Hủy lượt đặt phòng”, áp dụng chính sách hủy tương ứng. |

### Quy tắc nghiệp vụ rút ra

Từ kịch bản, nhóm có thể đặt câu hỏi và xác nhận các quy tắc sau:

- Thời gian kết thúc phải sau thời gian bắt đầu.
- Phòng phải có sức chứa ít nhất bằng số người tham dự.
- Phòng phải đáp ứng các yêu cầu thiết bị bắt buộc.
- Một phòng không được có hai lượt đặt phòng chồng lấn thời gian, trừ khi chính sách cho phép một trường hợp đặc biệt.
- Người đặt phòng phải có quyền phù hợp với loại phòng và thời lượng đặt.
- Việc xác nhận phải kiểm tra khả dụng tại thời điểm ghi nhận để tránh hai yêu cầu đồng thời cùng đặt một phòng.
- Lỗi gửi thông báo sau khi đặt thành công không nhất thiết làm lượt đặt phòng mất hiệu lực; đây là hai kết quả cần được theo dõi riêng.

Các quy tắc trên là giả thuyết ban đầu để thảo luận. Nhóm cần xác nhận với người sở hữu chính sách trước khi coi chúng là quy tắc chính thức.

### Khái niệm và dữ liệu miền được phát hiện

| Khái niệm | Thuộc tính hoặc ý nghĩa cần làm rõ |
|---|---|
| Phòng họp | Mã phòng, sức chứa, vị trí, thiết bị, trạng thái khả dụng. |
| Lượt đặt phòng | Người đặt, phòng, thời gian, mục đích, trạng thái và thời điểm tạo. |
| Khoảng thời gian | Thời điểm bắt đầu, kết thúc, múi giờ và quy tắc tính chồng lấn. |
| Người tổ chức | Danh tính, đơn vị, quyền đặt và thông tin liên hệ. |
| Yêu cầu thiết bị | Loại thiết bị, số lượng và điều kiện bắt buộc hoặc tùy chọn. |
| Chính sách đặt phòng | Giới hạn thời lượng, thời gian đặt trước, quyền ưu tiên và quy tắc hủy. |
| Thông báo | Người nhận, kênh gửi, nội dung, trạng thái gửi và số lần thử lại. |

### Mô hình hóa luồng ở mức khái quát

Sơ đồ dưới đây thể hiện các tương tác chính của ca sử dụng. Nó giúp các bên thống nhất phạm vi và luồng nghiệp vụ trước khi nhóm thiết kế chi tiết mô hình hoặc cú pháp DSL.

~~~mermaid
flowchart TD
    A[Nhân viên gửi yêu cầu đặt phòng] --> B[Kiểm tra quyền và dữ liệu]
    B -->|Không hợp lệ| X[Từ chối và nêu lý do]
    B -->|Hợp lệ| C[Tìm phòng phù hợp]
    C -->|Không có phòng| D[Đề xuất điều chỉnh yêu cầu]
    D --> A
    C -->|Có phòng| E[Nhân viên chọn phòng]
    E --> F[Kiểm tra khả dụng lần cuối]
    F -->|Đã bị đặt| G[Hiển thị lựa chọn khác]
    G --> E
    F -->|Còn trống| H[Ghi nhận lượt đặt phòng]
    H --> I[Cập nhật lịch và gửi xác nhận]
    I --> J[Đặt phòng hoàn tất]
~~~

Sơ đồ là bản đơn giản hóa. Trong mô hình chi tiết, nhóm có thể tách việc ghi nhận lượt đặt, cập nhật lịch và gửi thông báo thành các thao tác có trạng thái riêng để xử lý lỗi và thử lại đúng cách.

## 6. Từ kịch bản sử dụng đến mô hình và DSL

Kịch bản sử dụng không phải là cú pháp DSL. Nó là nguồn bằng chứng để nhóm quyết định DSL cần biểu diễn những khái niệm và quy tắc nào. Quá trình chuyển đổi nên được thực hiện có kiểm soát.

| Thành phần trong kịch bản | Câu hỏi khi mô hình hóa miền | Khả năng được DSL hỗ trợ |
|---|---|---|
| Danh từ miền | Đây là thực thể, giá trị, vai trò hay khái niệm tổng hợp? | Khai báo kiểu, thuộc tính hoặc tham chiếu. |
| Hành động | Hành động làm thay đổi trạng thái hay chỉ truy vấn thông tin? | Câu lệnh, thao tác hoặc biểu thức. |
| Điều kiện | Điều kiện nào phải đúng và ai xác nhận ý nghĩa? | Biểu thức điều kiện, ràng buộc hoặc chính sách. |
| Trạng thái | Đối tượng có những trạng thái hợp lệ nào? | Kiểu liệt kê, máy trạng thái hoặc quy tắc chuyển trạng thái. |
| Sự kiện | Điều gì đã xảy ra và thành phần nào cần phản ứng? | Khai báo sự kiện, bộ xử lý hoặc quy tắc phản ứng. |
| Tác nhân và quyền | Ai được phép thực hiện hành động nào? | Vai trò, quyền hạn hoặc quy tắc ủy quyền. |
| Ngoại lệ | Khi xử lý thất bại, hệ thống giữ hoặc hoàn tác dữ liệu ra sao? | Cơ chế lỗi, nhánh thay thế, bù trừ hoặc thử lại. |
| Hệ thống phụ trợ | Dữ liệu và thao tác được trao đổi qua đâu? | Khai báo tích hợp, adapter hoặc hợp đồng giao tiếp. |

Ví dụ, từ kịch bản đặt phòng có thể hình thành một biểu diễn minh họa như sau:

~~~text
booking_policy MeetingRoomPolicy {
    require booking.end > booking.start
    require room.capacity >= booking.attendeeCount
    prevent overlapping_bookings(room, booking.period)

    authorize organizer to reserve room
    on booking.confirmed notify organizer
}
~~~

Đây chỉ là ví dụ giả định để minh họa cách một số quy tắc có thể được biểu diễn. Cú pháp, tên kiểu và ngữ nghĩa thực tế phải được thiết kế dựa trên mô hình miền đã được xác nhận. Không nên sao chép nguyên văn kịch bản thành DSL mà chưa làm rõ tính nhất quán, phạm vi và ý nghĩa của từng cấu trúc.

Một cách làm hữu ích là duy trì liên kết giữa kịch bản, quy tắc và phần tử DSL:

| Mã kịch bản | Quy tắc hoặc yêu cầu | Phần tử mô hình/DSL | Kiểm thử liên quan |
|---|---|---|---|
| UC-01, bước 2 | Người đặt phải có quyền phù hợp. | Quy tắc authorization. | Người không có quyền bị từ chối. |
| UC-01, bước 3 | Phòng phải đủ sức chứa. | Thuộc tính `capacity` và điều kiện so sánh. | Phòng nhỏ hơn số người không được đề xuất. |
| UC-01, bước 6 | Không được xác nhận phòng đã bị đặt. | Ràng buộc không chồng lấn. | Hai yêu cầu đồng thời không thể cùng xác nhận một phòng. |
| UC-01, bước 8 | Gửi thông báo sau khi đặt thành công. | Sự kiện `booking.confirmed` và hành động thông báo. | Lỗi thông báo không làm báo cáo sai trạng thái đặt phòng. |

Liên kết này giúp truy ngược từ một cấu trúc DSL về nhu cầu nghiệp vụ đã tạo ra nó, đồng thời xác định những kịch bản cần cập nhật khi quy tắc thay đổi.

## 7. Mối quan hệ với các kỹ thuật mô hình hóa khác

Kịch bản sử dụng thường được kết hợp với các kỹ thuật khác. Mỗi kỹ thuật trả lời một loại câu hỏi khác nhau.

| Kỹ thuật | Trọng tâm | Khi nên dùng cùng kịch bản |
|---|---|---|
| Sơ đồ ca sử dụng UML | Tác nhân và các mục tiêu tương tác với hệ thống. | Khi cần nhìn tổng thể phạm vi và các ca sử dụng. |
| Sơ đồ hoạt động | Luồng công việc, nhánh điều kiện và xử lý song song. | Khi luồng có nhiều quyết định hoặc nhiều nhánh phức tạp. |
| Sơ đồ tuần tự | Thứ tự thông điệp giữa tác nhân và các thành phần. | Khi cần hiểu tương tác với hệ thống phụ trợ hoặc xử lý đồng thời. |
| Mô hình miền | Khái niệm, thuộc tính và quan hệ trong miền. | Khi cần chuyển danh từ và dữ liệu trong kịch bản thành cấu trúc miền. |
| Bảng quyết định | Tổ hợp điều kiện và kết quả tương ứng. | Khi một bước có nhiều điều kiện nghiệp vụ kết hợp. |
| Mô hình trạng thái | Trạng thái hợp lệ và sự kiện làm thay đổi trạng thái. | Khi vòng đời của đối tượng có nhiều chuyển đổi và quy tắc. |
| User story | Nhu cầu ở góc nhìn người dùng và giá trị mong muốn. | Khi cần quản lý yêu cầu theo backlog; kịch bản bổ sung chi tiết tương tác và ngoại lệ. |
| Quy trình nghiệp vụ (BPMN) | Quy trình giữa nhiều vai trò, bộ phận và hệ thống. | Khi cần mô tả phối hợp liên tổ chức hoặc luồng công việc dài. |

### Kịch bản sử dụng và user story

User story thường diễn đạt ngắn gọn nhu cầu và giá trị, chẳng hạn: “Là người tổ chức, tôi muốn đặt phòng họp để có không gian phù hợp cho cuộc họp.” Nó hữu ích để ghi nhận nhu cầu ở mức backlog.

Kịch bản sử dụng đi sâu vào cách mục tiêu được hoàn thành: tiền điều kiện, luồng chính, nhánh thay thế, ngoại lệ và hậu điều kiện. Hai cách biểu diễn bổ sung cho nhau. User story không tự động thay thế việc khám phá quy tắc và các tình huống phức tạp.

### Kịch bản sử dụng và quy trình nghiệp vụ

Quy trình nghiệp vụ thường mô tả dòng công việc rộng hơn, có thể đi qua nhiều vai trò và tổ chức. Ca sử dụng tập trung vào một mục tiêu tương tác với một hệ thống trong ranh giới đã chọn. Khi một kịch bản kéo dài qua nhiều bộ phận, nhóm có thể cần mô hình quy trình để thể hiện trách nhiệm và điểm bàn giao, rồi dùng các ca sử dụng để mô tả tương tác cụ thể với từng hệ thống.

## 8. Mức độ chi tiết và cách đặt tên

Một ca sử dụng tốt tập trung vào mục tiêu của tác nhân. Mức chi tiết phụ thuộc vào mục đích khám phá, nhưng có một số nguyên tắc thực tế:

- Dùng tên bắt đầu bằng động từ và thể hiện kết quả, ví dụ “Tạo yêu cầu đặt phòng”, “Phê duyệt yêu cầu” hoặc “Hủy lượt đặt”.
- Giữ một ca sử dụng xoay quanh một mục tiêu chính. Tách các mục tiêu độc lập thành ca sử dụng riêng khi chúng có kết quả và quy tắc riêng.
- Viết luồng theo hành động nghiệp vụ, không mô tả mọi thao tác giao diện hoặc chi tiết triển khai.
- Mỗi bước nên rõ ai thực hiện và hệ thống phản hồi điều gì.
- Gắn nhánh thay thế với bước phát sinh để người đọc biết luồng quay lại đâu hoặc kết thúc như thế nào.
- Nêu rõ hậu điều kiện khi thất bại, đặc biệt nếu có thay đổi dữ liệu trước thời điểm lỗi.
- Dùng ví dụ dữ liệu cụ thể để làm rõ các quy tắc về thời gian, tiền tệ, số lượng, quyền hạn hoặc trạng thái.

Nếu ca sử dụng chỉ có một hoặc hai bước nhưng không tạo ra kết quả nghiệp vụ riêng, có thể nó đang ở mức quá nhỏ. Nếu ca sử dụng bao gồm nhiều mục tiêu, nhiều vai trò và nhiều kết quả không liên quan, có thể nó đang ở mức quá lớn.

## 9. Các lỗi thường gặp khi viết kịch bản

**Mô tả giao diện thay vì mục tiêu.** “Người dùng mở màn hình, nhấn nút xanh và chọn tab” thường gắn với một thiết kế giao diện cụ thể. Hãy mô tả hành động nghiệp vụ và kết quả mà người dùng cần.

**Chỉ viết luồng thành công.** Điều này che giấu quy tắc quan trọng như từ chối, xung đột dữ liệu, thiếu quyền, hết tài nguyên và lỗi tích hợp. Hãy chủ động hỏi về nhánh thay thế và ngoại lệ.

**Không xác định ranh giới hệ thống.** Khi ranh giới mơ hồ, nhóm khó phân biệt tác nhân với thành phần nội bộ và dễ gán sai trách nhiệm.

**Dùng thuật ngữ không nhất quán.** Một từ có thể mang ý nghĩa khác nhau giữa các bộ phận. Hãy đưa thuật ngữ vào bảng chú giải và yêu cầu người có thẩm quyền xác nhận.

**Trộn quy tắc với bước tương tác.** “Người dùng nhấn xác nhận” là một hành động; “chỉ được xác nhận khi phòng còn trống” là quy tắc. Nên ghi riêng để quy tắc có thể được tái sử dụng trong nhiều ca sử dụng.

**Đưa giải pháp kỹ thuật vào quá sớm.** Không nên mặc định rằng một bước nghiệp vụ phải được thực hiện bằng một API, bảng dữ liệu hoặc dịch vụ cụ thể. Trước tiên cần hiểu mục đích và ngữ nghĩa của bước đó.

**Bỏ qua trạng thái sau lỗi.** Nếu một phần thao tác đã thành công trước khi bước tiếp theo thất bại, cần xác định dữ liệu được giữ, hoàn tác hay chuyển sang trạng thái cần xử lý.

**Không xác nhận với người thực hiện công việc.** Tài liệu do nhóm dự án tự suy luận có thể bỏ qua các bước thủ công và ngoại lệ. Hãy kiểm chứng bằng ví dụ thực tế với người hiểu miền.

**Viết quá nhiều kịch bản trùng lặp.** Các biến thể chỉ khác dữ liệu đầu vào có thể được gom thành ví dụ hoặc bảng quyết định. Giữ các kịch bản riêng khi chúng khác về quy tắc, luồng hoặc kết quả có ý nghĩa.

## 10. Mẫu tài liệu kịch bản sử dụng

Có thể dùng mẫu sau trong buổi khám phá hoặc lưu trong kho tài liệu dự án. Các trường chưa rõ nên được đánh dấu là câu hỏi mở thay vì tự điền bằng giả định.

~~~text
Mã ca sử dụng:
Tên:
Mục tiêu:
Phạm vi hệ thống:
Tác nhân chính:
Tác nhân phụ:
Bên liên quan và mối quan tâm:

Tiền điều kiện:
Kích hoạt:

Luồng thành công chính:
  1.
  2.
  3.

Luồng thay thế:
  A1. Tại bước ... khi ...:
      1.
      2.

Luồng ngoại lệ:
  E1. Tại bước ... nếu ...:
      1.
      2.

Hậu điều kiện thành công:
Hậu điều kiện thất bại:

Quy tắc nghiệp vụ:
Dữ liệu và thuật ngữ miền:
Yêu cầu phi chức năng:
Giả định:
Câu hỏi mở:
Người xác nhận:
Phiên bản / ngày cập nhật:
~~~

Khi một ca sử dụng có nhiều nhánh, có thể đặt mã cho từng nhánh như A1, A2 hoặc E1, E2 và tham chiếu mã đó trong phần luồng chính. Cách này giúp trao đổi và kiểm thử chính xác hơn.

## 11. Chuyển kịch bản thành ví dụ kiểm thử

Kịch bản có thể trở thành nguồn cho kiểm thử chấp nhận hoặc kiểm thử ngữ nghĩa DSL. Mỗi quy tắc quan trọng nên có ít nhất một ví dụ hợp lệ và một ví dụ không hợp lệ, khi phù hợp.

Với ví dụ đặt phòng:

| Tình huống | Đầu vào hoặc điều kiện | Kết quả mong đợi |
|---|---|---|
| Đặt phòng hợp lệ | Phòng đủ sức chứa, còn trống, người dùng có quyền. | Tạo lượt đặt và phát sinh sự kiện xác nhận. |
| Thời gian không hợp lệ | Thời điểm kết thúc trước hoặc bằng thời điểm bắt đầu. | Từ chối yêu cầu và chỉ rõ điều kiện thời gian. |
| Không đủ sức chứa | Số người tham dự lớn hơn sức chứa phòng. | Phòng không được xem là lựa chọn hợp lệ. |
| Trùng thời gian | Phòng đã có lượt đặt chồng lấn. | Không xác nhận lượt đặt mới cho phòng đó. |
| Không đủ quyền | Người dùng không có quyền đặt loại phòng được chọn. | Từ chối và ghi nhận lý do phù hợp. |
| Gửi thông báo thất bại | Lượt đặt đã ghi nhận nhưng dịch vụ thông báo lỗi. | Lượt đặt vẫn có trạng thái chính xác; lỗi thông báo được xử lý riêng theo chính sách. |

Nếu DSL hỗ trợ kiểm tra tĩnh, một số điều kiện có thể được phát hiện trước khi chạy. Những điều kiện phụ thuộc dữ liệu tại thời điểm thực thi, chẳng hạn phòng còn trống hay không, thường cần được kiểm tra lúc chạy. Việc phân loại này giúp xác định đâu là trách nhiệm của bộ kiểm tra DSL và đâu là trách nhiệm của môi trường thực thi.

## 12. Duy trì và quản lý thay đổi kịch bản

Kịch bản phản ánh hiểu biết hiện tại về miền. Khi chính sách, quy trình, vai trò hoặc hệ thống tích hợp thay đổi, kịch bản có thể không còn chính xác. Vì vậy, mỗi ca sử dụng quan trọng nên có mã định danh, người chịu trách nhiệm xác nhận, ngày cập nhật và liên kết đến quy tắc hoặc yêu cầu liên quan.

Khi có thay đổi:

1. Xác định ca sử dụng và quy tắc bị ảnh hưởng.
2. Ghi rõ tình huống mới, lý do thay đổi và bên liên quan yêu cầu thay đổi.
3. Cập nhật luồng chính, nhánh thay thế, ngoại lệ hoặc hậu điều kiện tương ứng.
4. Kiểm tra tác động đến mô hình miền, cấu trúc DSL, chương trình DSL hiện có và dữ liệu được lưu.
5. Cập nhật ví dụ kiểm thử và xác nhận lại với người có thẩm quyền.

Nếu một thay đổi làm cho nhiều kịch bản cùng cần một quy tắc mới, hãy xem xét đưa quy tắc đó vào mô hình miền dùng chung thay vì lặp lại mô tả ở từng kịch bản. Điều này giúp ngữ nghĩa DSL nhất quán.

## 13. Danh sách câu hỏi khi rà soát một kịch bản

Trước khi dùng kịch bản làm căn cứ thiết kế DSL, hãy xác nhận:

- Mục tiêu có rõ ràng và mang lại kết quả nghiệp vụ có ý nghĩa không?
- Ranh giới hệ thống và tác nhân đã được xác định chưa?
- Luồng chính có thể được người thực hiện công việc xác nhận không?
- Mỗi bước có rõ tác nhân thực hiện và phản hồi của hệ thống không?
- Các nhánh thay thế, ngoại lệ và trường hợp lỗi quan trọng đã được ghi lại chưa?
- Tiền điều kiện và hậu điều kiện có mô tả đúng trạng thái miền không?
- Thuật ngữ, dữ liệu, trạng thái và quy tắc đã được làm rõ hoặc đánh dấu là câu hỏi mở chưa?
- Người có thẩm quyền xác nhận chính sách đã được xác định chưa?
- Có thể tạo ví dụ kiểm thử từ các luồng và quy tắc trong kịch bản không?
- Kịch bản có liên kết với yêu cầu hoặc phần tử mô hình DSL tương ứng không?

Mục đích của việc rà soát là bảo đảm kịch bản đủ rõ để trao đổi và kiểm chứng. Không cần biến mọi kịch bản thành một tài liệu dài; mức chi tiết nên tương xứng với độ phức tạp và rủi ro của quy tắc đang khám phá.

## 14. Quy trình áp dụng trong dự án DSL

Một quy trình thực tế có thể tổ chức theo các hoạt động sau:

1. **Chọn phạm vi khám phá:** xác định miền, mục tiêu và quy trình cần tìm hiểu.
2. **Thu thập tình huống thực tế:** phỏng vấn, quan sát, đọc tài liệu và yêu cầu người tham gia kể các trường hợp đã xảy ra.
3. **Xác định tác nhân và mục tiêu:** phân biệt người khởi tạo, hệ thống phụ trợ và các bên chịu ảnh hưởng.
4. **Viết luồng chính:** mô tả tương tác theo ngôn ngữ nghiệp vụ.
5. **Khám phá biến thể và ngoại lệ:** hỏi về quyền, dữ liệu thiếu, xung đột, lỗi và thay đổi giữa chừng.
6. **Rút trích kiến thức miền:** lập danh sách thuật ngữ, dữ liệu, hành động, sự kiện, trạng thái và quy tắc.
7. **Xác nhận:** rà soát với người thực hiện và người có thẩm quyền về nghiệp vụ.
8. **Liên kết với mô hình và DSL:** chuyển các quy tắc đã xác nhận thành mô hình, cấu trúc ngôn ngữ và kiểm thử phù hợp.
9. **Cập nhật theo thay đổi:** duy trì truy vết giữa kịch bản, quy tắc, mô hình và chương trình DSL.

Kịch bản sử dụng giúp nhóm khám phá miền bằng những tình huống cụ thể mà các bên có thể cùng xem xét. Khi mục tiêu, tác nhân, luồng chính, ngoại lệ và kết quả được mô tả rõ, nhóm có thể xác định chính xác hơn DSL cần diễn đạt điều gì, cần kiểm tra những quy tắc nào và phải phản ứng ra sao trước các tình huống thực tế.
