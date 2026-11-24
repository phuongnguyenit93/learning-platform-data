# Tách câu chuyện theo luồng sử dụng, quy tắc nghiệp vụ và mức độ rủi ro

Một yêu cầu sản phẩm thường bắt đầu bằng câu chuyện có vẻ đơn giản: “Là học viên, tôi muốn tiếp tục bài học đang dở để không phải tìm lại tiến độ”. Khi thảo luận, nhóm phát hiện hàng loạt tình huống: học trên một hoặc nhiều thiết bị, bài đã hoàn thành, mạng gián đoạn, khóa học bị thu hồi quyền truy cập, dữ liệu cũ không nhất quán và việc đồng bộ tiến độ cần đáp ứng yêu cầu bảo mật. Nếu đưa tất cả vào một user story, nhóm có thể phải chờ lâu mới giao được giá trị; nếu chia thành các đầu việc “làm database”, “làm API”, “làm UI”, từng phần lại chưa mang đến trải nghiệm sử dụng được.

**Tách user story (story splitting)** là chia một nhu cầu lớn thành các câu chuyện nhỏ hơn, mỗi câu chuyện thể hiện một **lát cắt giá trị theo chiều dọc**: người dùng hoặc bên nhận giá trị có thể thực hiện một hành vi có ích, còn nhóm có thể kiểm tra kết quả và nhận phản hồi. Ba góc nhìn đặc biệt hữu ích để tìm những lát cắt đó là **luồng sử dụng**, **quy tắc nghiệp vụ** và **mức độ rủi ro**.

Bài thuộc chương **User story** của module **AGILE_DEVELOPMENT**. Theo tinh thần Agile, nhóm cần học từ phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục. Cách tách câu chuyện quyết định nhóm có thể kiểm chứng giả định sản phẩm nhanh tới đâu, duy trì chất lượng kỹ thuật bằng các thực hành như XP, tổ chức backlog trong Scrum hoặc quản lý dòng chảy bằng Kanban như thế nào.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **chia việc kỹ thuật** và **tách user story thành lát cắt tạo giá trị**.
2. Nhận diện luồng sử dụng chính, biến thể, điểm ngoại lệ và ranh giới của từng câu chuyện.
3. Phân nhóm quy tắc nghiệp vụ để mở rộng hành vi sản phẩm theo những bước có thể kiểm chứng.
4. Đánh giá rủi ro **giá trị, khả dụng, khả thi, chất lượng và phụ thuộc** nhằm chọn thứ tự tách và thực hiện.
5. Viết câu chuyện nhỏ cùng tiêu chí chấp nhận rõ ràng, có thể kiểm thử, với điều kiện hoàn tất thích hợp.
6. Tránh các cách tách khiến backlog nhiều ticket nhưng không có Increment sử dụng được.
7. Thiết kế một chuỗi câu chuyện từ yêu cầu lớn, cân đối phản hồi sớm với bảo mật, dữ liệu, tính đúng đắn và nợ kỹ thuật.

## 2. “Nhỏ hơn” không tự động đồng nghĩa “tốt hơn”

User story thường được diễn đạt theo dạng:

> **Là** [vai trò/người dùng], **tôi muốn** [khả năng hoặc hành vi] **để** [đạt lợi ích hoặc giải quyết vấn đề].

Đây là một khuôn mẫu giao tiếp hữu ích, không phải định nghĩa duy nhất của user story. Câu chuyện cần có **cuộc trao đổi** làm rõ nhu cầu và **tiêu chí xác nhận** kết quả. Chỉ viết đúng ba vế chưa đủ để nhóm hiểu và kiểm thử.

Một câu chuyện lớn có thể mô tả đúng nhu cầu nhưng vẫn khó triển khai:

> “Là học viên, tôi muốn học tiếp trên mọi thiết bị, cả khi mạng yếu, để không mất tiến độ trong bất kỳ tình huống nào.”

Yêu cầu này chứa nhiều luồng và rủi ro. Có thể tách theo hai kiểu:

| Cách chia | Hạng mục tạo ra | Vấn đề hoặc lợi ích |
| --- | --- | --- |
| **Theo lớp kỹ thuật** | Thiết kế bảng tiến độ; viết API; tạo giao diện; viết kiểm thử | Thuận tiện phân công kỹ thuật, nhưng từng hạng mục không nhất thiết tạo kết quả người dùng quan sát được; giá trị thường chỉ xuất hiện khi ghép đủ |
| **Theo lát cắt hành vi** | Học viên đã đăng nhập tiếp tục bài đang dở trên cùng thiết bị; sau đó thêm đồng bộ giữa thiết bị; sau đó xử lý retry khi mất mạng | Mỗi lát cắt hoàn chỉnh một hành vi có thể kiểm tra, giao, học từ phản hồi và mở rộng |

**Chia việc kỹ thuật vẫn cần thiết**. Developers có thể chia một story thành tác vụ API, UI, database, kiểm thử và triển khai để phối hợp. Điểm quan trọng là không trình bày từng tác vụ đó như một user story đã đem lại giá trị độc lập.

### Lát cắt theo chiều dọc

~~~mermaid
flowchart TB
    U["Hành vi người học:<br/>Tiếp tục bài đang dở"] --> UI["Giao diện"]
    UI --> API["Xử lý ứng dụng / API"]
    API --> DATA["Lưu và truy xuất tiến độ"]
    DATA --> TEST["Kiểm thử, quan sát và tiêu chuẩn Done"]
    TEST --> V["Một khả năng sử dụng được,<br/>có thể nhận phản hồi"]
~~~

Sơ đồ minh họa một lát cắt đi qua các thành phần cần thiết của hệ thống. Tùy kiến trúc, một lát cắt có thể dùng dữ liệu giả lập được kiểm soát hoặc chưa cần xây kho dữ liệu mới; điều quyết định là **lời hứa của story được thực hiện trung thực, không che giấu giới hạn ảnh hưởng người dùng**.

## 3. Ba lăng kính tách chuyện: luồng, quy tắc và rủi ro

| Lăng kính | Câu hỏi để tách | Ví dụ lát cắt | Tác dụng chính |
| --- | --- | --- | --- |
| **Luồng sử dụng (workflow / path)** | Người dùng đi qua những bước nào? Đâu là hành trình tối thiểu đem lại giá trị? Có nhánh ít phổ biến nào có thể triển khai sau? | Trước tiên tiếp tục bài dở trên cùng thiết bị; sau đó tiếp tục trên thiết bị khác | Giao sớm đường đi có giá trị, quan sát hành vi thực |
| **Quy tắc nghiệp vụ (business rules)** | Có các điều kiện, giới hạn, phân loại hoặc phép tính nào quyết định hành vi? Quy tắc nào là bắt buộc ngay từ đầu? | Trước tiên tiến độ của bài đang học; sau đó xử lý bài đã hoàn thành và bài bị khóa | Giới hạn độ phức tạp từng bước, kiểm thử ranh giới |
| **Mức độ rủi ro (risk / uncertainty)** | Điều gì sai sẽ làm mất giá trị, gây lỗi nghiêm trọng hoặc khiến phải làm lại nhiều? Cần chứng minh điều gì sớm? | Kiểm tra sớm tính đúng đắn của đồng bộ tiến độ trước khi đầu tư UI nâng cao | Giảm bất định, phát hiện điểm khó hoặc hướng sai khi chi phí còn thấp |

Ba lăng kính có thể **kết hợp**, không phải ba phương pháp loại trừ nhau. Một story có thể là “luồng chính cho người học đã đăng nhập, theo quy tắc bài chưa hoàn thành, được thử nghiệm trước vì rủi ro giá trị cao”. Tách tốt là cách chọn **ranh giới có ý nghĩa** giữa giá trị, quy tắc và rủi ro.

### Những câu hỏi mở đầu một phiên refinement

- **Giá trị:** Ai cần hành vi này? Khi nào họ cần? Nếu thiếu, họ phải làm gì bằng cách thủ công?
- **Luồng:** Hành trình ngắn nhất từ ý định tới kết quả là gì? Nhánh nào xảy ra thường xuyên nhất?
- **Quy tắc:** Điều kiện nào thay đổi quyết định của hệ thống? Có trường hợp nào không được phép bỏ qua?
- **Rủi ro:** Điều nào nhóm chỉ đang giả định? Nếu sai, phần nào của giải pháp phải làm lại?
- **Hoàn tất:** Thế nào là Done theo tiêu chuẩn chất lượng? Có thể cho một nhóm người dùng dùng thử an toàn không?
- **Phản hồi:** Sau khi giao lát cắt này, nhóm sẽ biết được điều gì trước đây chưa biết?

## 4. Bắt đầu từ một câu chuyện lớn và mục tiêu giá trị

Giả sử sản phẩm cần hỗ trợ người học tiếp tục khóa học. Mục tiêu sản phẩm được phát biểu:

> “Giúp học viên tìm lại điểm học dở và tiếp tục học thuận tiện, đồng thời bảo đảm tiến độ được lưu đúng.”

Câu chuyện ban đầu:

> “Là học viên, tôi muốn tiếp tục bất kỳ khóa học nào từ vị trí gần nhất trên mọi thiết bị, kể cả khi mất mạng hoặc thay đổi quyền truy cập, để không lãng phí thời gian và không mất tiến độ.”

Điều này thường quá lớn cho một vòng phát triển ngắn vì chứa nhiều hành vi độc lập và điều kiện phức tạp. Trước khi tách, hãy làm rõ:

1. **Ai được hưởng giá trị trước?** Học viên đã đăng nhập đang học dở một khóa.
2. **Khoảnh khắc tạo giá trị là gì?** Mở lại đúng bài và vị trí có thể tiếp tục.
3. **Hành trình chính có những bước nào?** Mở trang khóa học → nhìn thấy bài đang học → chọn “Học tiếp” → hệ thống mở bài phù hợp.
4. **Những quy tắc nào bắt buộc?** Không cho người dùng khác xem tiến độ; không mở bài đã mất quyền truy cập; không ghi dữ liệu sai.
5. **Rủi ro lớn là gì?** Không biết học viên có gặp khó khăn thật không; đồng bộ tiến độ có thể gây ghi đè; log hành vi có thể không đáng tin.
6. **Làm sao đo?** Thời gian tìm bài, tỷ lệ mở đúng bài, lỗi điều hướng, phản hồi người dùng và tỷ lệ học tiếp; các chỉ số phải có định nghĩa rõ.

Từ đây, nhóm mới chọn các story nhỏ. Nếu bắt đầu bằng “chia đều cho bốn lập trình viên”, backlog có thể phản ánh cấu trúc tổ chức hơn là hành trình tạo giá trị.

## 5. Tách theo luồng sử dụng: giao đường đi đơn giản trước

**Luồng sử dụng** là chuỗi bước người dùng thực hiện để đạt mục đích. Một hệ thống thường có luồng chính, các nhánh thay thế và tình huống ngoại lệ.

Ví dụ:

~~~text
Học viên mở trang khóa học
  ├─ Có bài đang học dở
  │    ├─ Cùng thiết bị, đang trực tuyến
  │    ├─ Thiết bị khác, đang trực tuyến
  │    └─ Mất mạng, vừa khôi phục kết nối
  ├─ Đã hoàn thành tất cả bài
  ├─ Chưa bắt đầu bài nào
  └─ Không còn quyền truy cập khóa học
~~~

Thay vì gom mọi nhánh vào một story, nhóm xác định **đường đi đầu tiên có thể sử dụng được**. Một chuỗi ví dụ:

| Story | Luồng được bổ sung | Giá trị kiểm chứng được |
| --- | --- | --- |
| **US-01: Tiếp tục bài dở trực tuyến trên cùng thiết bị** | Học viên đã đăng nhập, có quyền truy cập, đang học dở một bài | Có thể trở lại bài đang học bằng một thao tác |
| **US-02: Tiếp tục sau khi đổi thiết bị** | Học viên cùng tài khoản truy cập từ thiết bị thứ hai | Trải nghiệm nhất quán giữa thiết bị, không phải tìm thủ công |
| **US-03: Tiếp tục khi kết nối vừa được khôi phục** | Thiết bị có thay đổi tiến độ trong lúc mạng gián đoạn rồi đồng bộ | Giảm nguy cơ mất tiến độ và xử lý được một hành trình khó |
| **US-04: Hướng dẫn khi chưa có tiến độ** | Học viên mới chưa học bài nào | Có điểm bắt đầu rõ thay vì nút dẫn sai |
| **US-05: Thông báo khi không còn quyền học** | Bài/khóa học không còn quyền truy cập | Học viên hiểu trạng thái và tránh truy cập trái phép |

Các mã US là minh họa, không phải thứ tự bắt buộc. Nếu dữ liệu cho thấy phần lớn học viên đổi thiết bị và đó là vấn đề quan trọng nhất, **luồng nhiều thiết bị có thể cần ưu tiên ngay từ đầu**. Nếu trường hợp không còn quyền truy cập là ràng buộc an toàn bắt buộc, kiểm tra quyền truy cập phải có từ lát cắt đầu tiên dù màn hình hướng dẫn chi tiết có thể phát triển sau.

### Một lát cắt “đơn giản” vẫn phải đúng và an toàn

Làm luồng chính trước **không có nghĩa** cho phép bỏ qua xác thực, phân quyền, kiểm soát dữ liệu, quy tắc tính tiền hoặc các điều kiện chất lượng thiết yếu. Những yêu cầu bắt buộc này được đưa vào **Definition of Done**, tiêu chí chấp nhận hoặc quy tắc tối thiểu của story đầu tiên.

Ví dụ, US-01 có thể chưa xử lý đồng bộ offline phức tạp, nhưng **không được** trả tiến độ của người dùng khác. Nếu không thể cung cấp hành vi đã hứa một cách an toàn trong phạm vi hẹp, lát cắt đó chưa đủ điều kiện để giao.

### Luồng chính trước, ngoại lệ sau: khi nào hợp lý?

Phù hợp khi:

- Luồng chính đủ thường xuyên và có giá trị để lấy phản hồi thực.
- Ngoại lệ là những mở rộng được xác định rõ, có thể giới hạn phạm vi mà không gây hại.
- Nhóm có thể kiểm tra đủ các điều kiện bắt buộc ngay ở lát cắt đầu tiên.

Không phù hợp khi:

- “Ngoại lệ” thực ra là con đường sử dụng chủ đạo của phần lớn người dùng.
- Thiếu xử lý ngoại lệ tạo nguy cơ mất dữ liệu, lộ thông tin hoặc thu tiền sai.
- Không có cách giới hạn người dùng/phạm vi của bản đầu tiên, khiến hành vi thiếu hoàn chỉnh gây hậu quả lớn.

## 6. Tách theo quy tắc nghiệp vụ: đi từ bộ quy tắc tối thiểu đến biến thể

**Quy tắc nghiệp vụ** xác định hệ thống phải xử lý thế nào dựa trên các điều kiện của lĩnh vực: quyền truy cập, trạng thái bài học, điều kiện tính hoàn thành, giới hạn thời gian, giá, loại tài khoản hoặc chính sách hỗ trợ.

Ví dụ với hành vi “Học tiếp”, có thể có các quy tắc:

| Mã | Quy tắc | Mức bắt buộc | Cách dùng để tách |
| --- | --- | --- | --- |
| R1 | Người dùng chỉ xem và cập nhật tiến độ thuộc tài khoản của mình | **Bắt buộc ngay** | Điều kiện chất lượng và bảo mật của mọi lát cắt, không được hoãn |
| R2 | Với bài đã bắt đầu nhưng chưa hoàn thành, “Học tiếp” mở đúng bài | Cốt lõi của luồng chính | Story đầu tiên |
| R3 | Khi bài hiện tại đã hoàn thành, đề xuất bài kế tiếp hợp lệ | Giá trị bổ sung rõ | Story riêng theo trạng thái hoàn thành |
| R4 | Nếu chưa có tiến độ, gợi ý bài đầu tiên được phép học | Biến thể cho người học mới | Story riêng theo trạng thái chưa bắt đầu |
| R5 | Nếu khóa học không còn quyền truy cập, không mở nội dung được bảo vệ | **Bắt buộc ngay ở phần phân quyền** | Chặn truy cập từ đầu; trải nghiệm giải thích chi tiết có thể là story sau |
| R6 | Khi nhận nhiều cập nhật tiến độ gần nhau, hệ thống tránh mất dữ liệu hoặc ghi đè sai | Rủi ro tính đúng đắn | Kiểm chứng sớm nếu kiến trúc dự kiến có cập nhật cạnh tranh |
| R7 | Với bài đánh dấu “đã hoàn thành”, tiếp tục tại điểm thích hợp theo chính sách khóa học | Quy tắc theo loại bài/khóa học | Tách thành story biến thể nếu chưa cần ở lát cắt đầu |

Cần phân biệt **quy tắc bắt buộc cho tính đúng đắn** với **quy tắc mở rộng hành vi**. Chỉ nhóm thứ hai mới có thể trì hoãn tương đối an toàn. Khi một quy tắc liên quan pháp lý, phân quyền, thanh toán hay bảo toàn dữ liệu, phải đánh giá rủi ro cụ thể trước khi quyết định thứ tự.

### Những kỹ thuật tách theo quy tắc

**Theo trạng thái:** chưa bắt đầu → đang học → hoàn thành → bị khóa. Mỗi trạng thái là một nhánh hành vi có thể kiểm tra nếu được xác định rõ.

**Theo loại đối tượng:** khóa học miễn phí trước, khóa học có kiểm tra đầu vào sau, nếu không làm sai quy tắc đối với khóa học đang được hỗ trợ. Tránh giới hạn không được thông báo khiến người dùng tưởng mọi loại khóa học đã được xử lý.

**Theo mức phức tạp của phép tính:** tính tiến độ theo số bài hoàn thành trước, rồi tính thêm trọng số theo thời lượng nếu sản phẩm thực sự cần. Không triển khai công thức đơn giản nhưng gọi đó là “tiến độ chính xác” nếu nó đưa ra kết quả gây hiểu nhầm.

**Theo tham số hoặc chính sách:** trước tiên hỗ trợ một ngưỡng có căn cứ, sau đó thêm các cấu hình khác. Ví dụ chính sách nhắc học một lần trước khi hỗ trợ lịch nhắc tùy chỉnh.

**Theo đầu vào và điều kiện biên:** ưu tiên đầu vào hợp lệ phổ biến, sau đó mở rộng định dạng đặc biệt; tuy nhiên kiểm tra đầu vào không hợp lệ mang tính an toàn vẫn phải có ngay.

### Cách diễn đạt dễ kiểm thử

Tránh:

> “Hệ thống phải xử lý mọi tình huống tiến độ hợp lý.”

Nên dùng:

> “Với học viên đã đăng nhập, còn quyền truy cập và đang học dở bài A, khi chọn ‘Học tiếp’ trên trang khóa học thì hệ thống mở bài A và khôi phục điểm dừng đã lưu hợp lệ.”

Một câu chuyện rõ ranh giới giúp nhóm thảo luận tiêu chí chấp nhận, thiết kế kiểm thử và biết khi nào cần mở rộng quy tắc.

## 7. Sử dụng bảng quyết định để nhìn thấy các trường hợp

Khi có nhiều điều kiện kết hợp, thảo luận bằng văn bản dài rất dễ bỏ sót các trường hợp. **Bảng quyết định (decision table)** giúp tách quy tắc và xác định phản hồi mong đợi.

Ví dụ giản lược cho nút “Học tiếp”:

| Đăng nhập | Có quyền học | Có bài đang dở | Mọi bài đã hoàn tất | Hành vi mong đợi |
| --- | --- | --- | --- | --- |
| Không | — | — | — | Yêu cầu đăng nhập trước khi truy xuất tiến độ cá nhân |
| Có | Không | — | — | Không mở nội dung bị hạn chế; hiển thị trạng thái phù hợp |
| Có | Có | Có | Không | Mở đúng bài đang dở tại tiến độ hợp lệ |
| Có | Có | Không | Không | Đề xuất bài chưa học đầu tiên được phép truy cập |
| Có | Có | Không | Có | Hiển thị hoàn thành hoặc hành động học lại theo chính sách |

Dấu “—” nghĩa là điều kiện không quyết định kết quả ở dòng đó. Bảng chỉ mô tả trường hợp mẫu; hệ thống thực tế còn có thể phải xét đăng ký khóa học, lịch mở bài, dữ liệu hết hạn và đồng bộ.

Một cách tách theo bảng:

1. Dòng “Có quyền, có bài đang dở” là lát cắt cốt lõi có giá trị.
2. Dòng “Không có bài đang dở, chưa hoàn tất” tạo hành vi riêng cho người mới.
3. Dòng “Mọi bài đã hoàn tất” thêm quy tắc hoàn thành.
4. Dòng “Không có quyền” **phải được bảo vệ ngay trong mọi xử lý truy cập**; giao diện thông báo chi tiết có thể thay đổi sau.

Bảng quyết định giúp xác định ranh giới, không tự động chứng minh các story độc lập hoặc có thể phát hành an toàn. Developers và người hiểu nghiệp vụ cần cùng xem xét hậu quả nếu trì hoãn từng dòng.

## 8. Tách theo rủi ro: học sớm điều có thể làm thay đổi hướng

Không phải story nào đem lại nhiều giá trị trực tiếp nhất cũng nên làm đầu tiên. Có những giả định kỹ thuật hoặc sản phẩm mà nếu sai sẽ khiến nhóm phải làm lại phần lớn giải pháp. Lúc đó, chọn lát cắt giúp **giảm rủi ro lớn** là hợp lý.

### Những nhóm rủi ro phổ biến

| Nhóm rủi ro | Câu hỏi cần giải đáp | Bằng chứng hữu ích |
| --- | --- | --- |
| **Rủi ro giá trị** | Người dùng có thực sự gặp vấn đề và muốn thay đổi hành vi không? | Phỏng vấn trải nghiệm thực, quan sát tác vụ, thử nghiệm sản phẩm nhỏ |
| **Rủi ro khả dụng** | Người dùng có hiểu và hoàn thành hành vi mong muốn không? | Prototype và usability test với người dùng phù hợp |
| **Rủi ro khả thi kỹ thuật** | API, lưu trữ và cơ chế đồng bộ có hoạt động trong điều kiện quan trọng không? | Spike, proof of concept, kiểm thử tích hợp hoặc thử tải |
| **Rủi ro tính đúng đắn/chất lượng** | Có mất tiến độ, truy cập sai quyền hay lỗi hồi quy nghiêm trọng không? | Kiểm thử tự động, kiểm thử điều kiện biên, đánh giá bảo mật phù hợp |
| **Rủi ro phụ thuộc** | Nhóm có phải chờ API, quyền truy cập, thiết kế, dữ liệu hay phê duyệt từ bên khác không? | Hợp đồng tích hợp, môi trường thử, xác nhận phụ thuộc, phối hợp sớm |
| **Rủi ro vận hành** | Có theo dõi, phát hành, rollback và xử lý sự cố được không? | Diễn tập triển khai, kiểm tra cảnh báo, thử phục hồi phù hợp |

### Quy tắc ưu tiên đơn giản

Đánh giá từng giả định theo bốn chiều:

1. **Khả năng sai / mức bất định:** hiện có bao nhiêu bằng chứng tin cậy?
2. **Tác động nếu sai:** mất giá trị, mất dữ liệu, chi phí làm lại hay ảnh hưởng uy tín ở mức nào?
3. **Thời điểm cần biết:** phải quyết trước khi nhóm cam kết công việc lớn hoặc phụ thuộc kéo dài không?
4. **Chi phí học:** có cách kiểm chứng sớm, an toàn và tương đối ít tốn kém không?

| Giả định | Bất định | Hậu quả nếu sai | Thứ tự xử lý gợi ý |
| --- | --- | --- | --- |
| Học viên thực sự khó tìm lại bài đang học | Cao | Cao vì có thể xây sai tính năng | Quan sát người học và thử lát cắt giao diện sớm |
| API tiến độ không bị ghi đè khi cập nhật đồng thời | Trung bình | Rất cao vì nguy cơ mất dữ liệu | Kiểm thử kỹ thuật và xác định chính sách xung đột trước khi mở rộng |
| Biểu tượng trên nút màu xanh dễ nhận ra hơn màu xám | Trung bình | Thấp, dễ đảo ngược | Thử sau các rủi ro nền tảng |
| Bên cung cấp dịch vụ xác thực sẽ cấp môi trường tuần tới | Cao | Cao vì chặn tích hợp | Xác nhận sớm, làm hợp đồng mô phỏng có kiểm chứng |

Các mức trên là **ví dụ định tính**, không phải phép tính xác suất. Đừng bịa điểm số chính xác để tạo cảm giác khách quan.

### Kiểm chứng rủi ro bằng story hay bằng spike?

Nếu có thể tạo **một hành vi sử dụng được và học từ nó**, ưu tiên story dọc. Ví dụ: “Học viên lưu và khôi phục tiến độ một bài trên cùng tài khoản” vừa mang giá trị vừa kiểm chứng cơ chế lưu trữ.

Nếu cần tìm lời giải cho bất định kỹ thuật trước khi triển khai đầy đủ, nhóm có thể làm **spike có giới hạn thời gian**: dựng thử cách giải quyết xung đột đồng bộ và kiểm tra khả thi. Spike có đầu ra là kiến thức, bằng chứng, phương án kỹ thuật hoặc quyết định; **nó không tự động là Increment sử dụng được**. Sau spike, nhóm vẫn cần story hoàn chỉnh và tiêu chuẩn Done trước khi tuyên bố đã giao giá trị sản phẩm.

Một spike tốt có câu hỏi rõ, thời gian dừng, cách đo và kết quả ra quyết định. Spike mơ hồ kiểu “nghiên cứu đồng bộ cho đến khi thấy ổn” dễ kéo dài vô hạn.

## 9. Kết hợp ba lăng kính trong cùng một backlog

Khi lập kế hoạch, hãy xem ba góc nhìn như các bộ lọc liên tiếp:

~~~mermaid
flowchart TD
    A["Nhu cầu lớn của người dùng"] --> B["Xác định hành trình tạo giá trị"]
    B --> C["Chọn luồng đầu tiên<br/>có ích và quan sát được"]
    C --> D["Làm rõ quy tắc bắt buộc,<br/>quy tắc có thể mở rộng"]
    D --> E["Đánh giá rủi ro giá trị,<br/>kỹ thuật, chất lượng, phụ thuộc"]
    E --> F["Viết một story nhỏ<br/>và tiêu chí chấp nhận"]
    F --> G{"Có thể đạt Done<br/>và kiểm chứng giá trị?"}
    G -->|Chưa| H["Điều chỉnh ranh giới,<br/>giảm phụ thuộc hoặc thử spike"]
    H --> F
    G -->|Có| I["Ưu tiên, triển khai,<br/>kiểm tra và học"]
    I --> J["Cập nhật thứ tự<br/>các lát cắt tiếp theo"]
~~~

Ví dụ, nếu hành trình “tiếp tục trên thiết bị khác” được nhiều học viên quan tâm nhưng nguy cơ ghi đè tiến độ lớn, nhóm có thể:

1. Chọn luồng sử dụng nhiều thiết bị làm mục tiêu.
2. Tách quy tắc thành “đọc tiến độ từ máy chủ” và “cập nhật tiến độ theo nguyên tắc xử lý xung đột đã xác nhận”.
3. Kiểm tra sớm rủi ro đồng thời/ghi đè bằng spike hoặc kiểm thử nhỏ.
4. Giao story khôi phục đúng tiến độ với kiểm thử tích hợp, phân quyền, theo dõi lỗi và phạm vi người dùng phù hợp.
5. Lấy phản hồi rồi quyết định có mở rộng sang đồng bộ offline phức tạp hay không.

Ở đây rủi ro không phải lý do để trì hoãn giá trị mãi mãi; nó giúp chọn **bằng chứng tối thiểu cần có trước khi mở rộng**.

## 10. Ví dụ chi tiết: tách một yêu cầu thành các Increment tăng dần

### 10.1. Epic ban đầu

> “Là học viên, tôi muốn tiếp tục học từ nơi đã dừng trong mọi tình huống để giữ được tiến độ.”

Epic chứa mục tiêu hợp lý nhưng quá rộng. Nhóm phân tích theo luồng, quy tắc và rủi ro:

| Nhánh | Câu hỏi còn thiếu | Hành động khám phá |
| --- | --- | --- |
| Luồng | Học viên thường quay lại cùng thiết bị hay đổi thiết bị? | Phân tích hành vi theo tài khoản và phỏng vấn theo trải nghiệm đã xảy ra |
| Quy tắc | “Tiến độ” là bài gần nhất, phút phát video hay câu hỏi đang làm? | Trao đổi người hiểu nghiệp vụ và viết ví dụ minh họa |
| Rủi ro | Có thể mất tiến độ khi nhiều thiết bị cùng cập nhật? | Thử nghiệm đồng thời và kiểm thử tính đúng đắn |
| Giá trị | Giảm thao tác tìm bài có làm người học quay lại nhiều hơn không? | Thử lát cắt “Học tiếp”, quan sát thời gian tìm bài và hành vi học tiếp |

### 10.2. Chuỗi story minh họa

| Thứ tự minh họa | Story nhỏ | Lăng kính chính | Tiêu chí quan sát được |
| --- | --- | --- | --- |
| **S1** | Học viên đã đăng nhập, có quyền học, tiếp tục bài chưa hoàn thành trên cùng thiết bị đang trực tuyến | Luồng chính | Từ trang khóa học, nhấn “Học tiếp” mở đúng bài và vị trí lưu hợp lệ |
| **S2** | Học viên mới chưa bắt đầu được dẫn đến bài đầu tiên có thể học | Quy tắc theo trạng thái | Không có tiến độ thì nút bắt đầu mở bài hợp lệ, không báo lỗi trống |
| **S3** | Học viên hoàn tất bài đang học được gợi ý bài kế tiếp theo thứ tự khóa học | Quy tắc nghiệp vụ | Không quay lại bài cũ sai chính sách; đề xuất đúng bài tiếp theo |
| **S4** | Học viên đăng nhập trên thiết bị thứ hai có thể tiếp tục từ tiến độ đã lưu | Luồng nhiều thiết bị | Truy xuất và hiển thị đúng tiến độ máy chủ; không lộ dữ liệu tài khoản khác |
| **S5** | Tiến độ được bảo toàn khi hai thiết bị cập nhật gần nhau theo chính sách xung đột đã thống nhất | Rủi ro tính đúng đắn | Kiểm thử các tình huống xung đột, retry và dữ liệu không hợp lệ |
| **S6** | Học viên đang học khi mất mạng có thể đồng bộ lại sau khi kết nối trở lại | Luồng ngoại lệ + rủi ro | Hiển thị trạng thái đồng bộ, tránh ghi đè sai, có thể phục hồi |
| **S7** | Học viên nhận hướng dẫn rõ khi khóa học không còn quyền truy cập | Quy tắc quyền truy cập + UX | Không thể xem nội dung bị khóa; biết vì sao không thể tiếp tục |

**Chú ý:** Điều kiện phân quyền, tính đúng đắn dữ liệu cần thiết, kiểm thử, theo dõi lỗi và bảo mật áp dụng từ S1. S7 chỉ bổ sung **trải nghiệm giải thích** sau khi quyền truy cập đã được kiểm soát, không trì hoãn bảo vệ dữ liệu đến S7. Tương tự, việc xử lý xung đột không được để sau nếu S1 đã có thể gây mất dữ liệu trong vận hành thực tế.

Chuỗi này chỉ minh họa. Product Owner cùng nhóm có thể đổi thứ tự khi bằng chứng cho thấy một nhánh quan trọng hơn, phụ thuộc phải xử lý sớm hơn hoặc tính năng ban đầu cần giới hạn phạm vi rõ.

### 10.3. Đọc một lát cắt từ đầu đến cuối

Story S1:

> **Là** học viên đã đăng nhập và có quyền vào khóa học, **tôi muốn** mở lại bài chưa hoàn thành ngay trên trang khóa học **để** tiếp tục học mà không phải tìm thủ công.

**Phạm vi:** Một học viên, một khóa học được phép truy cập, có bài dở dang; thao tác đang trực tuyến; hệ thống lưu và khôi phục vị trí hợp lệ. Không hứa hỗ trợ offline hoặc đồng bộ đồng thời nhiều thiết bị trong bản đầu nếu chưa có cơ chế đầy đủ và chưa mở quyền sử dụng cho các trường hợp đó.

**Giá trị có thể quan sát:** Học viên tìm được bài dở và tiếp tục ngay. Nhóm có thể quan sát người dùng thực hiện nhiệm vụ và đo thời gian từ khi mở trang khóa học đến khi mở đúng bài, với dữ liệu đo tin cậy.

**Chất lượng bắt buộc:** Phân quyền, truy xuất tiến độ đúng tài khoản, kiểm thử tự động theo tiêu chí, xử lý dữ liệu không hợp lệ theo thiết kế, logging không lộ dữ liệu nhạy cảm và đạt Definition of Done.

### 10.4. Cùng một epic, những cách chia khác nhau

| Nếu mục tiêu hiện tại là... | Ưu tiên lát cắt... | Lý do |
| --- | --- | --- |
| Xác minh người học có cần nút “Học tiếp” không | S1 với nhóm người dùng phù hợp | Nhận phản hồi về vấn đề và luồng chính sớm |
| Giảm lỗi đồng bộ gây mất tiến độ hiện có | S5 hoặc kiểm chứng nền tảng tính đúng đắn trước khi mở rộng | Rủi ro dữ liệu quan trọng hơn giao diện mới |
| Phục vụ người học chủ yếu trên điện thoại khác nhau | S4 có thể ưu tiên rất sớm | Luồng nhiều thiết bị là giá trị cốt lõi của phân khúc |
| Tuân thủ yêu cầu quyền truy cập nội dung | Kiểm soát quyền trong mọi story, bổ sung S7 về giải thích | Tính an toàn bắt buộc, không phải tính năng tùy chọn |

Không tồn tại một “danh sách story chuẩn” dùng được cho mọi sản phẩm. Thứ tự hợp lý phụ thuộc bằng chứng về giá trị, quy tắc bắt buộc và rủi ro thực tế.

## 11. Viết tiêu chí chấp nhận cho từng lát cắt

**Acceptance criteria** mô tả điều kiện để một story được chấp nhận về mặt hành vi và nghiệp vụ. Nó cần rõ ràng, có thể kiểm tra và phù hợp ranh giới đã chọn. Đối với những hành vi có nhiều điều kiện, cú pháp **Given–When–Then** có thể giúp nhóm trao đổi bằng ví dụ cụ thể.

Ví dụ S1:

~~~gherkin
Feature: Tiếp tục bài đang học

  Scenario: Học viên mở lại bài đang dở
    Given học viên đã đăng nhập và còn quyền truy cập khóa học K
      And học viên đã học dở bài B trong khóa học K
      And hệ thống có tiến độ hợp lệ của học viên ở bài B
    When học viên mở trang khóa học K và chọn "Học tiếp"
    Then hệ thống mở bài B tại vị trí đã lưu
      And không hiển thị tiến độ thuộc tài khoản khác

  Scenario: Học viên không còn quyền truy cập
    Given học viên đã đăng nhập nhưng không còn quyền truy cập khóa học K
    When học viên yêu cầu tiếp tục bài B của khóa học K
    Then hệ thống không trả về nội dung bài B
      And hiển thị trạng thái không thể truy cập phù hợp
~~~

Tại sao có kịch bản “không còn quyền truy cập” dù S7 nằm sau? Vì **bảo vệ truy cập là quy tắc bắt buộc** từ lát cắt đầu tiên. S7 có thể hoàn thiện nội dung hướng dẫn và hướng xử lý khi bị hạn chế; S1 phải chặn việc trả nội dung ngay.

### Tách tiêu chí chấp nhận khỏi Definition of Done

| Thành phần | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Acceptance criteria** | Story này phải hoạt động ra sao? | Nhấn “Học tiếp” mở đúng bài và vị trí cho học viên hợp lệ |
| **Definition of Done** | Công việc phải đạt tiêu chuẩn chất lượng chung nào để Increment được xem là hoàn tất? | Code review, kiểm thử phù hợp, tích hợp, bảo mật, tài liệu/giám sát theo chuẩn tổ chức |
| **Tiêu chí kiểm chứng outcome** | Sau khi giao, liệu giải pháp có thật sự tạo giá trị? | Thời gian tìm bài giảm và tỷ lệ hoàn thành thao tác học tiếp thay đổi theo hướng mong muốn |

Một story có thể đạt acceptance criteria và Definition of Done nhưng giả thuyết giá trị vẫn chưa được thị trường xác nhận. Khi đó, phản hồi từ người dùng cần quay trở lại backlog để điều chỉnh.

## 12. Tách bằng ví dụ cụ thể: từ quy tắc mơ hồ đến các trường hợp

Khi nhóm bất đồng về ý nghĩa “học xong”, hãy dùng **example mapping** hoặc bảng ví dụ:

**Câu chuyện:** “Khi học viên hoàn thành một bài, hệ thống đề xuất bài tiếp theo.”

| Loại thẻ/thành phần | Ví dụ thảo luận | Kết quả mong muốn |
| --- | --- | --- |
| **Quy tắc** | Bài được đánh dấu hoàn thành khi học viên đạt điều kiện học của loại bài | Cần làm rõ điều kiện theo loại bài |
| **Ví dụ** | Video đã xem đủ ngưỡng theo quy tắc khóa học | Đánh dấu hoàn thành; gợi ý bài hợp lệ tiếp theo |
| **Ví dụ** | Bài trắc nghiệm chưa đạt điểm yêu cầu | Giữ trạng thái chưa hoàn thành; hướng dẫn làm lại |
| **Ví dụ** | Bài cuối cùng của khóa học đã hoàn tất | Thông báo hoàn thành thay vì gợi ý bài không tồn tại |
| **Câu hỏi chưa biết** | Bài được mở có điều kiện tiên quyết từ mô-đun khác không? | Cần quyết định quy tắc quyền học trước khi xác nhận story |

Các tấm thẻ ví dụ cho thấy quy tắc “hoàn thành” chứa nhiều chính sách. Có thể chọn **loại bài được sử dụng nhiều nhất** cho lát cắt đầu tiên, sau đó bổ sung loại bài khác. Nhưng tiêu chí nào bắt buộc từ đầu phải thống nhất với người hiểu nghiệp vụ và hậu quả khi hỗ trợ chưa đủ.

### Khi nào nên tách một quy tắc thành story riêng?

Một quy tắc đáng tách khi nó tạo ra **hành vi mới có thể quan sát**, có lợi ích hoặc rủi ro rõ, và có thể làm hoàn chỉnh trong một phạm vi nhỏ. Ngược lại, quy tắc chỉ là điều kiện kiểm tra an toàn chung (như “không được xem dữ liệu của người khác”) thường nên là phần bắt buộc của mọi story liên quan.

Tránh tạo story vô nghĩa như “Là hệ thống, tôi muốn kiểm tra quyền truy cập để hợp lệ” nếu điều đó chỉ là một phần kỹ thuật của hành vi người dùng và chưa có lợi ích độc lập để kiểm chứng. Tuy nhiên, một công việc cải thiện hạ tầng an toàn có thể là backlog item kỹ thuật chính đáng khi cần; không nhất thiết gượng ép nó vào mẫu “Là người dùng...”.

## 13. Kiểm tra kích thước và chất lượng của story trước khi nhận làm

Một tiêu chí tham khảo quen thuộc là **INVEST**:

| Tiêu chí | Câu hỏi thực tế |
| --- | --- |
| **Independent — tương đối độc lập** | Story có thể được ưu tiên, triển khai và kiểm tra mà không buộc hoàn tất một loạt story khác cùng lúc không? |
| **Negotiable — có thể thương lượng** | Nhóm còn không gian trao đổi giải pháp, phạm vi và cách triển khai không? |
| **Valuable — có giá trị** | Người dùng hoặc bên nhận giá trị được lợi gì sau lát cắt này? |
| **Estimable — có thể ước lượng hợp lý** | Bất định đã đủ rõ để dự báo phạm vi/năng lực tương đối chưa? |
| **Small — đủ nhỏ** | Có khả năng hoàn thành với chất lượng cần thiết trong nhịp làm việc hiện tại không? |
| **Testable — có thể kiểm tra** | Có ví dụ và kết quả quan sát được để xác định chấp nhận không? |

INVEST là **heuristic** (bộ câu hỏi hỗ trợ) chứ không phải bộ luật tuyệt đối. Một số story vẫn có phụ thuộc hoặc khó ước lượng do công nghệ mới; lúc đó nhóm cần nhận diện và giảm rủi ro thay vì che giấu.

### Một bảng rà soát nhanh

| Câu hỏi | Nếu câu trả lời là “không” |
| --- | --- |
| Story mô tả được một kết quả sử dụng cụ thể? | Quay lại xác định nhu cầu/hành vi; xem đang mô tả task kỹ thuật hay không |
| Có thể kiểm thử từ góc nhìn người dùng/nghiệp vụ? | Bổ sung ví dụ và acceptance criteria |
| Có thể hoàn thành qua các lớp cần thiết? | Giảm phạm vi theo luồng/quy tắc, tháo phụ thuộc |
| Quy tắc an toàn bắt buộc có mặt? | Bổ sung vào lát cắt hiện tại; không coi là chuyện “làm sau” |
| Có dữ liệu hoặc cách lấy phản hồi? | Làm rõ giả thuyết giá trị và cách quan sát |
| Các điều kiện còn lại đã được ghi vào backlog? | Ghi nhận biến thể/ngoại lệ để tránh quên khi giao phần đầu |

“Đủ nhỏ” không có nghĩa bắt buộc mọi story phải cùng số giờ hay cùng số story point. Kích thước hợp lý phụ thuộc khả năng nhóm, độ phức tạp, tiêu chuẩn Done và mức bất định. Nếu story thường xuyên bị kéo qua nhiều chu kỳ, hãy kiểm tra cách tách và các trở ngại hệ thống thay vì chỉ ép ước lượng thấp hơn.

## 14. Những mẫu tách dễ gây ra backlog sai

### 14.1. Tách theo tầng kỹ thuật rồi gọi mỗi tầng là user story

> Story A: tạo bảng tiến độ. Story B: viết REST API. Story C: làm nút giao diện.

Các công việc này có thể là **task** cần thiết, nhưng chỉ khi chúng được kết nối thành một trải nghiệm hoàn chỉnh, người dùng mới nhận được giá trị. Nếu không thể giao tăng dần, nhóm nên đặt chúng dưới cùng một story dọc và phối hợp để đạt Done.

### 14.2. Tách đến mức mỗi story chỉ thay đổi một dòng chữ

Story “Thêm nhãn nút”, “Thêm màu nút”, “Thêm icon” có thể khiến backlog dài nhưng thiếu mối liên hệ với nhu cầu. Thường chúng là bước hoàn thiện giao diện hoặc task của một story lớn hơn. Chỉ nên xem như story độc lập nếu một thay đổi thật sự là giả thuyết giá trị có thể kiểm chứng độc lập.

### 14.3. Cố làm đường đi đẹp nhưng bỏ qua điều kiện an toàn

“Phát hành nhanh trước, sau mới thêm phân quyền” không phải cách tách hợp lý nếu hệ thống có thể lộ dữ liệu. Quy tắc bắt buộc về bảo mật, tính đúng đắn và quyền truy cập phải được thỏa mãn ngay trong phần giao.

### 14.4. Gom toàn bộ ngoại lệ vào một story cuối cùng

Story “Xử lý mọi trường hợp đặc biệt” không rõ ranh giới, khó ước lượng và khó kiểm thử. Nên phân loại ngoại lệ theo nguyên nhân: mất mạng, hết quyền truy cập, trạng thái hoàn thành, dữ liệu cũ, đồng bộ đồng thời. Ngoại lệ rủi ro cao cần được xử lý sớm hơn.

### 14.5. Dùng thứ tự “dễ làm trước” thay cho giá trị và rủi ro

Xử lý màu giao diện rất nhanh nhưng giả định nền tảng về đồng bộ sai có thể khiến toàn bộ thiết kế phải làm lại. Ưu tiên tốt kết hợp **giá trị, bất định, hậu quả và phụ thuộc**, không chỉ sự thuận tiện của người thực hiện.

### 14.6. Tách xong nhưng không định nghĩa giới hạn hỗ trợ

Nếu sản phẩm chỉ hỗ trợ tiếp tục học trên cùng thiết bị, giao diện và tài liệu không nên tạo kỳ vọng “đồng bộ mọi thiết bị” khi chưa triển khai. Cần định nghĩa rõ điều được hỗ trợ, cho đúng nhóm người dùng dùng thử nếu cần và có phương án chuyển đổi khi mở rộng.

### 14.7. Tối ưu số story hoàn thành thay vì kết quả

Tăng số ticket Done có thể do story bị chia vụn, chưa chắc làm giá trị tới người dùng nhanh hơn. Theo dõi cả **thời gian từ ý tưởng đến phần sử dụng được, chất lượng, phản hồi và outcome**, không xếp hạng cá nhân theo số story đóng.

## 15. Tách story và phối hợp trong Scrum

Trong Scrum, Product Backlog là danh sách được sắp xếp thứ tự về những gì cần để cải thiện sản phẩm. **Product Backlog refinement** là hoạt động liên tục nhằm làm các mục nhỏ hơn và rõ hơn; nó không phải một sự kiện bắt buộc có thời lượng cố định trong Scrum Guide.

Nhóm có thể sử dụng ba lăng kính tách story khi refinement:

1. **Product Owner** làm rõ mục tiêu, giá trị, thứ tự ưu tiên và các giả định sản phẩm cần kiểm chứng.
2. **Developers** trao đổi các luồng, quy tắc, rủi ro kỹ thuật, phụ thuộc, cách kiểm thử và phạm vi có thể đưa tới Done.
3. **Người hiểu nghiệp vụ, thiết kế, vận hành, bảo mật hoặc người dùng** bổ sung các trường hợp thực tế trong phạm vi cần thiết.
4. **Scrum Master** hỗ trợ Scrum Team hiểu và thực hành refinement hiệu quả, tháo gỡ trở ngại; không thay quyền quyết định Product Backlog của Product Owner.

### Liên hệ với Sprint Goal

Sprint Goal là mục tiêu chung của Sprint, không phải một tập hợp ticket không liên quan. Nếu Sprint Goal là “Học viên đã đăng nhập có thể trở lại đúng bài đang học”, nhóm có thể chọn story S1 cùng công việc chất lượng cần thiết. Các story nâng cao như đa thiết bị hoặc offline có thể đưa vào Sprint sau khi có bằng chứng và năng lực.

Khi xuất hiện thông tin mới, Developers và Product Owner có thể thương lượng phạm vi để bảo vệ Sprint Goal và Definition of Done. **Đổi phạm vi hợp lý không đồng nghĩa bỏ tiêu chuẩn chất lượng.**

### Một Increment hoàn chỉnh có thể nhỏ

Increment không phải đợi đủ mọi khả năng của epic mới có ích. Một luồng “tiếp tục bài dở trên cùng thiết bị” đạt Definition of Done, giới hạn người dùng phù hợp và có thể sử dụng thực tế đã giúp nhóm học sớm. Increment có thể được phát hành trong Sprint khi sẵn sàng; Scrum không bắt buộc chờ đến cuối Sprint.

## 16. Tách story và quản lý dòng công việc bằng Kanban

Kanban giúp nhóm trực quan hóa những story đang được xử lý, giới hạn WIP và nhìn ra nút thắt. Tách quá lớn khiến item nằm lâu trong “Doing” và khó nhận phản hồi; tách quá nhỏ có thể tăng chi phí điều phối và làm số đo throughput trở nên khó diễn giải.

Ví dụ workflow:

~~~text
Đã làm rõ → Sẵn sàng → Đang phát triển → Review/kiểm thử → Hoàn tất
                WIP theo chính sách của nhóm ở các bước đang xử lý
~~~

Các chỉ số hỗ trợ:

| Chỉ số | Ý nghĩa | Tín hiệu liên quan việc tách story |
| --- | --- | --- |
| **Cycle time** | Thời gian từ mốc bắt đầu đến mốc hoàn tất được định nghĩa | Story lớn hoặc phụ thuộc nhiều có thể tạo thời gian hoàn tất dài và biến thiên cao |
| **Work item age** | Tuổi của item đang thực hiện | Câu chuyện quá rộng hoặc bị kẹt ở quy tắc chưa rõ sẽ ngày càng già |
| **WIP** | Số item đã bắt đầu nhưng chưa Done | Nếu quá nhiều story dở dang, nên hoàn thành lát cắt hiện tại trước khi nhận thêm |
| **Throughput** | Số item hoàn tất trong một khoảng thời gian | Chỉ có ý nghĩa khi hiểu kích thước và loại công việc; không dùng làm “điểm năng suất” tuyệt đối |

**Thay đổi cách tách story sẽ làm thay đổi ý nghĩa của chỉ số.** Nếu hôm qua mỗi ticket bằng một luồng hoàn chỉnh, hôm nay mỗi ticket chỉ là một thay đổi CSS, throughput tăng không chứng minh nhóm giao giá trị nhanh hơn. Cần giữ định nghĩa loại công việc nhất quán hoặc chú thích rõ khi có thay đổi.

Nhóm có thể đặt chính sách: “Một item chỉ vào Ready khi có mục tiêu giá trị, luồng/điều kiện chính, tiêu chí chấp nhận và phụ thuộc quan trọng đã được làm rõ đủ”. Nhưng chính sách phải phù hợp ngữ cảnh, được nhóm xem xét khi dữ liệu chỉ ra vấn đề.

## 17. XP giúp những lát cắt nhỏ vẫn an toàn khi thay đổi

Tách theo luồng và quy tắc thường làm nhóm thay đổi cùng một phần hệ thống nhiều lần. Nếu mỗi lần sửa đều làm hỏng hành vi đã có, lợi ích giao tăng dần sẽ mất đi. Các thực hành kỹ thuật thường gắn với **Extreme Programming (XP)** giúp giảm rủi ro đó:

- **Test-Driven Development (TDD)** phù hợp giúp định nghĩa và kiểm tra hành vi từng lát cắt, nhất là quy tắc nghiệp vụ.
- **Refactoring** cải thiện cấu trúc mã trong khi giữ hành vi cũ, giảm chi phí mở rộng quy tắc.
- **Continuous Integration (CI)** phát hiện xung đột và lỗi tích hợp sớm khi nhiều story đi qua cùng các lớp kỹ thuật.
- **Pair programming/code review** hỗ trợ trao đổi hiểu biết về trường hợp biên và quyết định thiết kế.
- **Small releases** giúp nhận phản hồi sớm với thay đổi nhỏ, hạn chế lượng chức năng chưa được kiểm chứng.

### Ví dụ TDD cho quy tắc chọn bài tiếp theo

~~~text
Red:
  Khi học viên chưa hoàn thành bài B,
  "Học tiếp" phải mở bài B, không nhảy sang bài C.

Green:
  Viết lượng mã nhỏ nhất để quy tắc được đáp ứng.

Refactor:
  Tách logic chọn bài thành hàm có tên rõ,
  giữ các kiểm thử cũ luôn chạy qua.

Story kế tiếp:
  Khi bài B đã hoàn thành, chọn bài C hợp lệ
  theo chính sách khóa học.
~~~

TDD không thay thế kiểm thử tích hợp, kiểm thử bảo mật hay kiểm chứng giá trị người dùng. Nó giúp nhóm mở rộng nhiều trường hợp nghiệp vụ mà vẫn duy trì tín hiệu chất lượng trong quá trình thay đổi.

## 18. Quy trình workshop tách story trong 45–60 phút

Một buổi refinement có Product Owner, Developers và đại diện nghiệp vụ có thể diễn ra theo sáu bước dưới đây. Thời lượng chỉ là gợi ý để tập trung, không phải quy định Scrum:

| Bước | Thời gian gợi ý | Hoạt động | Sản phẩm đầu ra |
| --- | --- | --- | --- |
| 1. Nhắc mục tiêu | 5 phút | Làm rõ người dùng, vấn đề, outcome và lý do ưu tiên | Một câu mục tiêu giá trị |
| 2. Vẽ hành trình | 10 phút | Liệt kê bước, luồng chính và nhánh khác | Bản đồ luồng sử dụng |
| 3. Làm rõ quy tắc | 10–15 phút | Viết điều kiện, ví dụ đúng/sai, tình huống biên | Bảng quy tắc và câu hỏi chưa rõ |
| 4. Nhìn rủi ro | 10 phút | Đánh giá giả định giá trị, kỹ thuật, dữ liệu, an toàn và phụ thuộc | Những rủi ro cần chứng minh sớm |
| 5. Đề xuất lát cắt | 10–15 phút | Chọn một story nhỏ có thể Done, gắn acceptance criteria và giới hạn hỗ trợ | Story đầu tiên và các story tiếp theo |
| 6. Kiểm tra và quyết định | 5 phút | Hỏi giá trị, độc lập tương đối, cách đo, chất lượng, thứ tự ưu tiên | Backlog được tinh chỉnh và chủ sở hữu câu hỏi mở |

### Minh họa cuộc trao đổi

**Product Owner:** “Học viên phàn nàn không tìm lại được bài đang học. Chúng ta muốn giảm thời gian họ mất để tiếp tục.”

**Developer:** “Ở bản đầu, một người học đã đăng nhập trên cùng thiết bị có thể mở bài dở chỉ bằng một nút. Đồng bộ nhiều thiết bị rủi ro hơn vì cập nhật cạnh tranh.”

**Người hiểu nghiệp vụ:** “Nhưng phải kiểm tra quyền truy cập khóa học từ đầu; chúng ta không thể cho người hết quyền mở bài cũ.”

**Tester:** “Tôi đề xuất bảng ví dụ cho đang học, chưa bắt đầu, đã hoàn thành, hết quyền. Luồng đang học là story đầu, phân quyền là điều kiện bắt buộc.”

**Product Owner:** “Đồng ý. Chúng ta ưu tiên luồng đang học trong phạm vi an toàn, đồng thời thử nghiệm kỹ thuật cho xung đột dữ liệu trước khi mở rộng nhiều thiết bị. Sau bản đầu sẽ quan sát người dùng có thực sự tìm bài nhanh hơn không.”

Điểm hữu ích của cuộc trao đổi là **mỗi góc nhìn làm rõ một phần bất định**, không phải một bên “viết story xong rồi giao cho bên khác thực hiện”.

## 19. Bài tập thực hành

### Bài tập A — Nhận diện story dọc và task kỹ thuật

Phân loại những hạng mục sau:

1. “Tạo bảng lưu giỏ hàng trong database.”
2. “Là khách đã đăng nhập, tôi muốn thêm một sản phẩm còn hàng vào giỏ để tiếp tục mua sau.”
3. “Viết endpoint POST cho chức năng lưu tiến độ.”
4. “Là học viên đang học dở, tôi muốn nhấn ‘Học tiếp’ và mở đúng bài để không tìm thủ công.”
5. “Tạo bộ kiểm thử hồi quy cho việc từ chối truy cập dữ liệu tiến độ người dùng khác.”

**Gợi ý:** (2) và (4) là những story theo hành vi người dùng có thể phát triển thành lát cắt dọc. (1), (3) và (5) là các task kỹ thuật hoặc công việc chất lượng có thể nằm trong story hoặc là backlog item kỹ thuật cần thiết. Task không phải không quan trọng; vấn đề là **cách nhận diện giá trị và trạng thái hoàn tất**.

### Bài tập B — Tách theo ba lăng kính

Epic: “Là người mua hàng, tôi muốn áp mã khuyến mãi khi thanh toán để nhận ưu đãi phù hợp.”

Hãy đề xuất ít nhất ba story, lần lượt giải thích:

- **Theo luồng sử dụng:** Người mua nhập một mã hợp lệ rồi thấy tổng tiền được cập nhật; biến thể có mã tự động hoặc sửa mã sau đó.
- **Theo quy tắc nghiệp vụ:** Mã giảm theo phần trăm, giảm số tiền cố định, chỉ áp dụng cho một nhóm sản phẩm, giới hạn mỗi tài khoản hoặc thời gian hiệu lực.
- **Theo rủi ro:** Không cho dùng lại mã một lần, tránh giảm tiền âm, chống cập nhật đồng thời khiến khuyến mãi bị tính sai, bảo đảm tổng thanh toán chính xác.

**Điều kiện:** Không được tách để một story “giảm giá đơn giản” cho phép thu sai tiền hoặc bỏ qua các kiểm soát bắt buộc. Nếu quy tắc an toàn chưa được giải quyết, phần đó phải được kiểm chứng và triển khai trước khi giao chức năng thanh toán.

### Bài tập C — Chọn story đầu tiên

Giả sử nghiên cứu cho thấy:

- 70% người dùng được khảo sát sử dụng một thiết bị trong một khóa học, nhưng mẫu khảo sát còn hạn chế.
- Phản hồi hỗ trợ ghi nhận lỗi mất tiến độ ở một số tài khoản dùng nhiều thiết bị.
- Nhóm chưa có kiểm thử cập nhật tiến độ đồng thời.
- Product Owner muốn chứng minh nút “Học tiếp” giúp người dùng tìm bài nhanh hơn.

Bạn sẽ chọn story nào trước và vì sao? Có cần một spike kỹ thuật song song không? Điều gì phải nằm trong Definition of Done ngay ở bản đầu? Làm sao tránh dùng một con số khảo sát nhỏ để kết luận cho toàn bộ học viên?

**Gợi ý lập luận:** Có thể làm luồng trực tuyến đơn giản để kiểm chứng nhu cầu, đồng thời ưu tiên kiểm thử rủi ro mất dữ liệu và phân quyền nếu chúng có thể ảnh hưởng người dùng. Thứ tự cụ thể tùy điều kiện giới hạn phát hành và bằng chứng bổ sung. Một câu trả lời tốt phải thể hiện **đánh đổi có lý do**, không chỉ chọn việc dễ.

### Bài tập D — Viết acceptance criteria

Viết ít nhất ba ví dụ Given–When–Then cho story “Học viên đã hoàn thành bài hiện tại được đề xuất bài kế tiếp hợp lệ”, bao gồm:

1. Còn bài tiếp theo, học viên có quyền.
2. Đã hoàn thành bài cuối cùng.
3. Bài tiếp theo có điều kiện tiên quyết chưa được đáp ứng.

Sau đó trả lời: tiêu chí nào thuộc hành vi của story, tiêu chí nào phải là yêu cầu chất lượng xuyên suốt và điều gì cần được đo sau khi phát hành để xác nhận người dùng thật sự được lợi?

## 20. Checklist trước khi chốt các lát cắt

- [ ] Đã nêu rõ **người dùng, vấn đề và giá trị mong muốn** của câu chuyện lớn.
- [ ] Đã vẽ **luồng sử dụng chính** và các biến thể quan trọng.
- [ ] Lát cắt đầu tiên đủ nhỏ để tạo một **hành vi hoàn chỉnh, sử dụng được**.
- [ ] Không gọi các lớp database/API/UI rời rạc là những user story tạo giá trị độc lập.
- [ ] Đã tách **quy tắc mở rộng** khỏi **quy tắc bắt buộc về an toàn và tính đúng đắn**.
- [ ] Bảng quyết định hoặc ví dụ cụ thể giúp nhìn thấy trạng thái, điều kiện và trường hợp biên.
- [ ] Các **rủi ro giá trị, khả dụng, kỹ thuật, chất lượng, phụ thuộc** quan trọng được nhận diện.
- [ ] Những giả định có hậu quả lớn được kiểm chứng **trước khi đầu tư mở rộng**.
- [ ] Có sự phân biệt rõ giữa **spike giảm bất định** và **story giao Increment**.
- [ ] Story có acceptance criteria rõ và phù hợp Definition of Done.
- [ ] Ranh giới tính năng, đối tượng được hỗ trợ và hành vi chưa hỗ trợ được công bố đúng.
- [ ] Có cách quan sát **outcome** sau khi giao, bên cạnh việc xác nhận phần mềm chạy đúng.
- [ ] Những story còn lại được ghi trong backlog, có thể sắp xếp lại theo phản hồi mới.
- [ ] Thứ tự thực hiện cân đối **giá trị, rủi ro và năng lực nhóm**, không chỉ độ dễ viết mã.
- [ ] Các chỉ số flow được hiểu theo kích thước/loại story và không bị dùng để xếp hạng cá nhân.

## 21. Tóm tắt và tài liệu đọc tiếp

**Tách theo luồng sử dụng** trả lời: *đường đi nhỏ nhất nào đã tạo ra giá trị và có thể thử với người dùng?*  
**Tách theo quy tắc nghiệp vụ** trả lời: *hành vi nào thay đổi theo trạng thái, điều kiện và chính sách, trong khi những quy tắc bắt buộc vẫn phải đúng từ đầu?*  
**Tách theo rủi ro** trả lời: *điều gì cần chứng minh sớm để tránh xây sai, làm mất dữ liệu hoặc tạo phụ thuộc tốn kém?*

Ba cách này kết hợp với nhau để tạo một chuỗi **Increment nhỏ, có thể kiểm tra và học từ phản hồi**. User story là lời mời trao đổi về kết quả người dùng mong muốn; task kỹ thuật, kiểm thử, thiết kế và triển khai là những phần công việc cần thiết để biến kết quả ấy thành hiện thực. Agile có được khả năng thích ứng khi nhóm giao được giá trị từng phần, bảo vệ chất lượng và sử dụng điều vừa học để điều chỉnh backlog.

Tài liệu tham khảo hữu ích:

- [Manifesto for Agile Software Development](https://agilemanifesto.org/): giá trị và nguyên tắc giao phần mềm sớm, phản hồi và thích ứng.
- [The Scrum Guide](https://scrumguides.org/): Product Backlog refinement, Sprint Goal, Increment, Definition of Done và trách nhiệm trong Scrum.
- Bill Wake, “INVEST in Good Stories, and SMART Tasks” (2003): bộ câu hỏi về tính độc lập, giá trị, khả năng ước lượng, kích thước và kiểm thử của câu chuyện.
- Jeff Patton, *User Story Mapping* (2014): cách nhìn hành trình người dùng để tạo lát cắt phát hành có giá trị.
- Gojko Adzic, *Specification by Example* (2011): làm rõ quy tắc nghiệp vụ và các trường hợp bằng ví dụ có thể kiểm chứng.

**Điểm cần nhớ:** Một story được tách tốt không chỉ “vừa để lập trình”; nó **đủ trọn vẹn để tạo ra một kết quả người dùng có thể nhận ra, đủ rõ để kiểm thử và đủ nhỏ để nhóm sớm kiểm chứng giá trị hoặc giảm rủi ro**.
