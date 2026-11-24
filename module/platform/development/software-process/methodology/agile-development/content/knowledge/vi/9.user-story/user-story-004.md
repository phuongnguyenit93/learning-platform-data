# Đánh giá chất lượng câu chuyện bằng các tiêu chí INVEST

Một **user story** có thể được viết đúng mẫu “Là một..., tôi muốn..., để...” mà vẫn khó triển khai: quá lớn, phụ thuộc nhiều chức năng chưa có, mô tả sẵn một giải pháp chưa được kiểm chứng hoặc không có cách xác nhận hoàn thành. Ngược lại, một story rất ngắn vẫn có thể hiệu quả nếu tạo ra cuộc trao đổi rõ ràng về **người dùng, giá trị và hành vi cần có**.

**INVEST** là bộ sáu tiêu chí thường dùng để xem xét chất lượng của user story:

- **I — Independent:** Có tính độc lập tương đối.
- **N — Negotiable:** Có thể thương lượng cách giải quyết.
- **V — Valuable:** Tạo giá trị.
- **E — Estimable:** Có thể ước lượng ở mức đủ để lập kế hoạch.
- **S — Small:** Đủ nhỏ để hoàn thành và kiểm chứng.
- **T — Testable:** Có thể kiểm chứng bằng bằng chứng rõ ràng.

Trong mô-đun **AGILE_DEVELOPMENT**, sử dụng INVEST giúp nhóm phát triển phần mềm Agile chia nhỏ công việc, tổ chức Product Backlog, nhận phản hồi sớm và bàn giao Increment tăng dần. INVEST là **công cụ thảo luận và cải thiện story**, không phải tiêu chuẩn chính thức bắt buộc của Scrum hay bảng chấm điểm máy móc. Một story chưa đạt một tiêu chí là **dấu hiệu cần thảo luận**, chưa tự động là story “sai”.

## 1. User story tốt phục vụ cuộc hội thoại và vòng phản hồi

Cấu trúc thường gặp của user story:

> Là **[vai trò hoặc nhóm người dùng]**, tôi muốn **[khả năng/hành vi]**, để **[đạt mục tiêu hoặc lợi ích]**.

Ví dụ:

> Là người bệnh đặt lịch trực tuyến, tôi muốn xem các khung giờ khám còn trống của cơ sở đã chọn, để tìm được thời gian phù hợp trước khi quyết định đặt lịch.

Mẫu câu này có ích vì định hướng người đọc tới một người dùng và một kết quả. Tuy nhiên, nó chưa trả lời tất cả câu hỏi: Thế nào là “còn trống”? Múi giờ nào được dùng? Nếu không có giờ phù hợp thì hiển thị gì? Dữ liệu được cập nhật từ hệ thống nào?

Mô hình **3C — Card, Conversation, Confirmation** giúp hiểu cách làm việc với story:

| Thành phần | Ý nghĩa | Minh họa |
| --- | --- | --- |
| **Card** | Lời nhắc ngắn gọn về nhu cầu, không phải bản đặc tả đầy đủ | “Người bệnh xem khung giờ khám còn trống” |
| **Conversation** | Trao đổi với người hiểu nghiệp vụ, người dùng, Developers và kiểm thử để làm rõ hành vi, giới hạn và đánh đổi | “Giờ còn trống” được tính từ lịch bác sĩ hay lịch cơ sở? |
| **Confirmation** | Ví dụ và tiêu chí chấp nhận chứng minh cách hiểu đã thống nhất | Với cơ sở A không còn lịch trong ngày, hiển thị thông báo và lựa chọn ngày khác |

INVEST hỗ trợ kiểm tra chất lượng của những gì được ghi trên Card và học được qua Conversation; **acceptance criteria** hỗ trợ Confirmation. Điều này phù hợp với Agile: hiểu biết về yêu cầu phát triển qua các vòng phản hồi thay vì được cho là hoàn chỉnh ngay trong lần viết đầu tiên.

### Nhìn INVEST như sáu câu hỏi

| Tiêu chí | Câu hỏi cần trả lời | Dấu hiệu cần xem lại |
| --- | --- | --- |
| **I — Independent** | Story có thể tiến triển, kiểm thử và bàn giao mà ít phải chờ nhiều story khác không? | Phải hoàn tất hàng loạt hạng mục mới xem được giá trị |
| **N — Negotiable** | Nhóm còn quyền trao đổi cách giải quyết để đạt mục tiêu không? | Story chỉ định thiết kế hoặc công nghệ mà không nêu lý do |
| **V — Valuable** | Ai nhận giá trị và thay đổi có ích nào sẽ xuất hiện? | Story chỉ mô tả thao tác kỹ thuật, không thấy đóng góp cho mục tiêu |
| **E — Estimable** | Nhóm có hiểu đủ để dự báo mức độ công sức/rủi ro không? | Nhiều câu hỏi cơ bản chưa được giải đáp, phụ thuộc chưa rõ |
| **S — Small** | Có thể hoàn thành một lát cắt có ý nghĩa trong khoảng thời gian phù hợp không? | Trộn nhiều hành trình, vai trò và trường hợp vào một story |
| **T — Testable** | Có bằng chứng quan sát được cho biết hành vi đạt hay chưa không? | Dùng từ “tốt”, “nhanh”, “dễ dùng” mà không có điều kiện đo |

Các tiêu chí **liên quan lẫn nhau**. Chia nhỏ một story có thể giúp ước lượng và kiểm chứng dễ hơn, nhưng nếu chia thành “xong database”, “xong API” và “xong UI”, từng phần lại thiếu giá trị độc lập. Vì vậy, cần cân bằng cả sáu tiêu chí thay vì chỉ tối ưu một chữ.

## 2. I — Independent: độc lập tương đối để tạo dòng công việc thông suốt

Một story **Independent** khi có thể xem xét ưu tiên, phát triển và kiểm chứng với **ít phụ thuộc không cần thiết** vào các story khác. Tính độc lập giúp Product Owner dễ thay đổi thứ tự backlog; nhóm ít phải đợi nhau và có thể bàn giao phần hữu ích sớm.

Không có nghĩa là story tuyệt đối không dùng chung dữ liệu, giao diện hoặc hệ thống. Những ràng buộc thực tế như đăng nhập, phân quyền hoặc quy tắc đặt lịch có thể khiến một số phụ thuộc cần thiết.

### Phân biệt phụ thuộc cần thiết và phụ thuộc do cách chia việc

Giả sử nhóm viết ba story:

1. “Tạo bảng dữ liệu khung giờ”.
2. “Tạo API lấy danh sách khung giờ”.
3. “Làm màn hình chọn khung giờ”.

Ba hạng mục đều phụ thuộc vào nhau để người dùng nhìn thấy một chức năng. Chúng có thể là **nhiệm vụ kỹ thuật** hợp lý bên trong kế hoạch thực hiện, nhưng nếu coi chúng là ba user story thì mỗi story riêng lẻ khó tạo phản hồi về giá trị.

Một lát cắt tốt hơn:

> Là người bệnh, tôi muốn xem các khung giờ còn chỗ của **một cơ sở khám thí điểm** theo ngày đã chọn, để quyết định ngày nào tôi có thể đến khám.

Lát cắt này đi qua giao diện, logic, dữ liệu và kiểm thử cần thiết. Nó có thể được sử dụng hoặc trình diễn cho đúng nhóm người dùng để học liệu thông tin hiển thị có dễ hiểu không.

### Cách cải thiện tính độc lập

- **Chia theo mục tiêu hoặc hành trình người dùng:** Ví dụ xem lịch trống, sau đó yêu cầu giữ một khung giờ, rồi đổi lịch — mỗi phần có giá trị và điều kiện bàn giao rõ.
- **Tách các biến thể ít phụ thuộc:** Một cơ sở thí điểm trước; nhiều cơ sở sau, nếu biến thể sau không ảnh hưởng tính đúng đắn của phần đầu.
- **Giảm ghép nối kỹ thuật:** Thiết lập giao diện hợp đồng, dữ liệu thử hoặc tích hợp tối thiểu đã thống nhất để một lát cắt có thể kiểm chứng mà không phải chờ toàn bộ hệ thống mở rộng.
- **Đưa công việc nền tảng vào đúng chỗ:** Nếu cần di chuyển dữ liệu hoặc sửa hạ tầng trước, thể hiện rủi ro và sự phụ thuộc minh bạch; không ép mọi hạng mục kỹ thuật thành user story giả tạo.
- **Ưu tiên hoàn tất thay vì mở nhiều việc:** Khi phụ thuộc là thật, cả nhóm có thể phối hợp hoàn thành lát cắt đang làm trước khi bắt đầu thêm lát cắt khác.

**Câu hỏi kiểm tra:** “Nếu story khác bị hoãn, story này vẫn tạo ra điều gì có thể dùng hoặc kiểm chứng không?” Nếu câu trả lời luôn là “không”, hãy xem lại cách chia, nhưng không loại bỏ phụ thuộc thiết yếu chỉ để đạt chữ I.

## 3. N — Negotiable: đủ rõ mục tiêu, vẫn mở cách thực hiện

Một story **Negotiable** là lời mời cộng tác, có thể trao đổi phạm vi và cách thực hiện để tìm phương án tốt nhất. Story không nên khóa quá sớm một thiết kế mà nhóm chưa xác nhận có giải quyết đúng vấn đề.

Ví dụ chưa tốt:

> Là người bệnh, tôi muốn một popup màu xanh rộng 600 px, có ba nút và thư viện lịch X, để chọn lịch khám.

Câu này trộn nhu cầu với thiết kế và công nghệ. Nếu không có lý do bắt buộc, nhóm mất cơ hội tìm giải pháp thuận tiện hơn trên điện thoại.

Ví dụ tốt hơn:

> Là người bệnh, tôi muốn nhận biết ngay những khung giờ còn chỗ khi chọn ngày khám, để tránh mất thời gian thử từng khung không khả dụng.

Nhóm có thể trao đổi xem nên làm danh sách, lịch tuần, bộ lọc hay cách hiển thị khác; thử bản mẫu với người dùng trước khi chọn. **Mục tiêu được giữ rõ, giải pháp có không gian thương lượng.**

### Negotiable không phải “muốn đổi gì cũng được”

Những ràng buộc đã được xác nhận vẫn có thể là bắt buộc:

- Chính sách nghiệp vụ đã được người có thẩm quyền quyết định.
- Bảo mật, quyền riêng tư và khả năng truy cập cần thiết.
- Giao diện tích hợp mà hệ thống khác thực sự phụ thuộc.
- Điều kiện chấp nhận quan trọng để ngăn sai dữ liệu hoặc thao tác gây hại.

Ví dụ, nhóm có thể thương lượng cách hiển thị trạng thái, **nhưng không được tự tuyên bố “đã xác nhận lịch” khi chưa giữ được chỗ**. Thương lượng ở đây là tìm cách đạt kết quả trong các giới hạn thực tế, không phải bỏ tiêu chuẩn chất lượng hoặc quyết định nghiệp vụ.

**Câu hỏi kiểm tra:** “Đâu là mục tiêu bắt buộc, đâu là đề xuất giải pháp, và lựa chọn nào vẫn có thể thay đổi nếu chúng ta học được điều mới?”

## 4. V — Valuable: tạo ra giá trị có thể giải thích

**Valuable** là tiêu chí giữ story gắn với lý do tồn tại của sản phẩm. Sau khi hoàn thành, phải có **người hoặc nhóm hưởng lợi** và một thay đổi có ích có thể mô tả được.

Hai tầng giá trị thường gặp:

- **Giá trị trực tiếp:** Người dùng hoàn thành tác vụ, giảm nhầm lẫn, tiết kiệm thời gian hoặc giảm sai sót.
- **Giá trị hỗ trợ:** Sản phẩm an toàn, ổn định, giảm rủi ro, giảm thời gian phục hồi, cho phép thay đổi trong tương lai với chi phí hợp lý.

### Phân biệt hoạt động, đầu ra và kết quả

| Cấp độ | Ví dụ | Có chứng minh giá trị cuối cùng chưa? |
| --- | --- | --- |
| Hoạt động | Viết code API lịch khám | Chưa; chỉ mô tả công việc |
| Đầu ra | Có API và màn hình hiển thị lịch trống | Có khả năng mới, cần kiểm chứng chất lượng |
| Kết quả người dùng | Người bệnh tìm được giờ phù hợp và hiểu khung giờ nào có thể đặt | Có bằng chứng gần với giá trị |
| Tác động sản phẩm | Tăng tỷ lệ tự đặt lịch thành công, giảm lượt gọi hỏi giờ khám | Liên hệ trực tiếp hơn với Product Goal, vẫn cần đo đáng tin |

Một user story như “Tạo API lấy lịch” thiếu góc nhìn giá trị nếu không có ngữ cảnh. Có thể viết:

> Là người bệnh, tôi muốn thấy lịch khám còn chỗ theo ngày, để quyết định nên đến cơ sở nào.

Sau đó triển khai API là **công việc con** để hỗ trợ story. Tuy nhiên, nếu thay đổi cốt lõi là nâng cấp nền tảng giám sát, bảo mật hoặc di chuyển dữ liệu, có thể ghi đó là **Product Backlog Item kỹ thuật** kèm giá trị và rủi ro được giảm, thay vì cố gán vai trò người dùng một cách thiếu tự nhiên.

### Giá trị là một giả thuyết cần xác nhận

Một câu “để người dùng dễ dàng hơn” vẫn còn mơ hồ. Hãy hỏi:

- Người dùng nào? Trong tình huống nào? Khó khăn hiện tại là gì?
- Điều gì có thể quan sát để biết tình huống đã cải thiện?
- Story đóng góp ra sao cho **Product Goal** hoặc mục tiêu sản phẩm hiện tại?
- Những chỉ số bảo vệ nào phải giữ: lỗi đặt trùng, hiệu năng, khả năng truy cập?

Nếu chỉ vài người dùng thích bản mẫu, nhóm đã có tín hiệu ban đầu nhưng chưa chắc kết quả tồn tại trên quy mô lớn. Agile sử dụng phản hồi sớm để học và điều chỉnh, **không coi việc viết phần “để...” là bằng chứng giá trị**.

**Câu hỏi kiểm tra:** “Nếu bỏ story này khỏi backlog, ai bị mất khả năng gì hoặc rủi ro nào không được giảm?”

## 5. E — Estimable: hiểu đủ để dự báo và nhận diện bất định

Một story **Estimable** khi nhóm có đủ thông tin về phạm vi, tình huống, phụ thuộc và rủi ro để **ước lượng ở mức hữu ích cho kế hoạch**. Không bắt buộc mọi story phải có số story point, số giờ chính xác hoặc một kỹ thuật ước lượng duy nhất.

Thực tế, ước lượng luôn có độ bất định. “Ước lượng được” không đồng nghĩa với dự báo chắc chắn; chỉ có nghĩa là mức độ thiếu thông tin không còn khiến mọi lựa chọn thực hiện khác nhau quá xa.

### Dấu hiệu story chưa đủ điều kiện để ước lượng

> “Là người bệnh, tôi muốn hệ thống đặt lịch thông minh cho mọi cơ sở để được phục vụ nhanh nhất.”

Nhóm chưa biết “thông minh” theo tiêu chí gì, dữ liệu các cơ sở có gì, có bao nhiêu loại lịch, thuật toán có cần tối ưu hành trình hay chỉ hiển thị chỗ trống, và thế nào là “nhanh nhất”. Hai người có thể ước lượng rất khác nhau vì đang tưởng tượng những sản phẩm khác nhau.

Các câu hỏi làm rõ:

1. Phạm vi cơ sở khám nào trong lần bàn giao đầu tiên?
2. Quy tắc “còn chỗ” do hệ thống nào cung cấp?
3. Tần suất cập nhật và cách xử lý dữ liệu không đồng bộ?
4. Điều kiện nào xác nhận thành công hoặc thất bại?
5. Có giới hạn bảo mật, dữ liệu nhạy cảm hoặc khả năng truy cập nào?
6. Những điều chưa biết nào cần thử trước khi ước lượng phần còn lại?

### Khi bất định kỹ thuật lớn: dùng phép nghiên cứu có giới hạn

Ví dụ nhóm chưa biết API của đối tác có trả về khung giờ trống đáng tin không. Có thể tạo một hạng mục nghiên cứu ngắn có giới hạn thời gian (**timeboxed spike**) với mục tiêu:

> Trong một khoảng thời gian đã thống nhất, thử tích hợp API trên môi trường phù hợp, ghi nhận dữ liệu trả về, các lỗi thường gặp, giới hạn tốc độ và đề xuất phương án xử lý.

**Kết quả của spike là kiến thức và quyết định kỹ thuật**, không phải mặc nhiên là Increment có giá trị người dùng. Sau đó nhóm quay lại làm rõ hoặc chia story bàn giao. Đừng dùng spike như cách kéo dài nghiên cứu vô hạn.

### Ước lượng phục vụ lập kế hoạch

Nhóm có thể dùng thảo luận tương đối, story point, dự báo bằng throughput/cycle time hoặc cách khác phù hợp. Quan trọng là **nêu được lý do khác biệt**. Nếu có người dự kiến một ngày và người khác hai tuần, hãy hỏi mỗi người đang bao gồm những ngoại lệ, kiểm thử và phụ thuộc nào.

**Câu hỏi kiểm tra:** “Nhóm có thể nói ra các giả định chính và khoảng rủi ro của ước lượng chưa? Nếu chưa, điều gì cần kiểm chứng trước?”

## 6. S — Small: đủ nhỏ để hoàn thành, nhận phản hồi và đổi hướng

Một story **Small** khi nhóm có thể tạo phần giá trị hoàn chỉnh và kiểm chứng trong **khoảng thời gian làm việc phù hợp**. Với nhóm Scrum, một hướng dẫn thực tế là story nên đủ nhỏ để hoàn thành trong một Sprint; đây **không phải điều kiện bắt buộc của Scrum Guide** cho mọi Product Backlog Item, và không có một kích thước tiêu chuẩn áp dụng cho mọi đội.

Story quá lớn thường trộn nhiều đối tượng, hành trình, kênh sử dụng và ngoại lệ. Nó làm tăng thời gian chờ nhận phản hồi và khiến ước lượng thiếu tin cậy.

### Ví dụ story quá lớn

> Là người bệnh, tôi muốn tìm bác sĩ, so sánh cơ sở, đặt lịch, thanh toán, đổi lịch, hủy lịch và nhận thông báo trên mọi thiết bị, để chủ động chăm sóc sức khỏe.

Nhu cầu tổng thể có ý nghĩa, nhưng **không nên coi cả hành trình là một story nhỏ**. Nhóm có thể xem đây là epic hoặc phạm vi sản phẩm cần chia thành các khả năng bàn giao dần.

### Những trục chia story thường hữu ích

| Trục chia | Ví dụ | Điều cần giữ |
| --- | --- | --- |
| **Bước trong hành trình** | Xem lịch còn chỗ → gửi yêu cầu đặt → xem kết quả xác nhận | Mỗi bước có kết quả dùng được và điều kiện rõ |
| **Nhóm người dùng / bối cảnh** | Một cơ sở thí điểm trước; nhiều cơ sở sau | Không khiến phiên bản đầu vi phạm nhu cầu bắt buộc của nhóm thử |
| **Quy tắc nghiệp vụ** | Lịch khám thông thường trước; lịch cần phê duyệt đặc biệt sau | Không bỏ quy tắc quan trọng để bảo đảm tính đúng |
| **Kênh sử dụng** | Luồng web cơ bản trước; trải nghiệm tối ưu kênh khác sau | Không tuyên bố đã hỗ trợ kênh chưa làm |
| **Độ phức tạp của hành vi** | Tìm lịch theo ngày trước; lọc nhiều tiêu chí và gợi ý nâng cao sau | Phần đơn giản phải thực sự giải quyết một vấn đề |
| **Mức độ chính xác / trình bày** | Danh sách lịch rõ ràng trước; xem lịch dạng tuần sau nếu có nhu cầu | Không đổi chất lượng bắt buộc lấy tốc độ |
| **Nguồn dữ liệu / phạm vi tích hợp** | Một nguồn dữ liệu có thể kiểm chứng trước; nhiều nguồn sau | Minh bạch giới hạn; không hiển thị dữ liệu thiếu như đầy đủ |

Đây là các trục lựa chọn, **không phải công thức phải làm theo thứ tự cố định**. Nếu tính đúng đắn đòi hỏi xử lý đồng thời hoặc kiểm soát truy cập ngay trong lát cắt đầu, hãy đưa vào phần đầu thay vì đẩy sang “giai đoạn sau”.

### Lát cắt dọc thay vì chia theo lớp kỹ thuật

~~~mermaid
flowchart TD
    A["Epic: Người bệnh tự đặt lịch khám đáng tin cậy"] --> B["Story 1: Xem giờ trống của một cơ sở theo ngày"]
    A --> C["Story 2: Gửi yêu cầu đặt một khung giờ và xem kết quả"]
    A --> D["Story 3: Xem hoặc hủy lịch theo quy tắc đã xác nhận"]
    B --> E["Mỗi story đi qua UI + logic + dữ liệu + kiểm thử cần thiết"]
    C --> E
    D --> E
~~~

Một lát cắt cần có **tiêu chí thành công và phản hồi riêng**. Nếu chỉ làm “tạo bảng lịch” thì chưa có hành vi người dùng để thử. Nếu story “xem giờ trống” phải chờ đến khi có toàn bộ thanh toán và nhắc lịch, cần xem lại cách giải phóng phụ thuộc.

### Khi chia quá nhỏ cũng gây hại

Các hạng mục như “thêm một nhãn”, “đổi tên biến”, “viết một endpoint” có thể là **task** phù hợp bên trong story hoặc một sửa lỗi độc lập, nhưng không tự động là user story tốt. Chia quá nhỏ có thể làm mất ngữ cảnh và khiến backlog đầy các mảnh khó thấy giá trị.

**Câu hỏi kiểm tra:** “Sau khi hoàn thành story này, có phần hành vi nào đủ ý nghĩa để người dùng, stakeholder hoặc hệ thống kiểm chứng không?”

## 7. T — Testable: xác nhận được điều đã thống nhất

Một story **Testable** khi nhóm có thể xác định **bằng chứng quan sát được** để trả lời “đã đáp ứng kỳ vọng chưa?”. Chỉ viết “hệ thống phải tốt, nhanh và dễ dùng” không cho biết mức đạt, điều kiện đo hoặc hành vi cần xác nhận.

Tiêu chí chấp nhận (**acceptance criteria**) thường giúp cụ thể hóa story; các kiểm thử tự động hoặc kiểm thử với người dùng giúp lấy bằng chứng. **Testable không đồng nghĩa với việc mọi khía cạnh đều phải tự động hóa**: khả dụng có thể cần quan sát người dùng, còn hiệu năng phải đo trong điều kiện xác định.

### Từ phát biểu mơ hồ tới điều kiện kiểm chứng

| Mơ hồ | Cách làm rõ có thể kiểm chứng |
| --- | --- |
| “Trang lịch phải nhanh” | Định nghĩa ngưỡng thời gian phản hồi, thiết bị, lưu lượng, nguồn dữ liệu và cách đo phù hợp |
| “Hiển thị thông báo dễ hiểu” | Cho người dùng mục tiêu thực hiện tác vụ và xác định đúng trạng thái; ghi tiêu chí quan sát |
| “Không cho đặt trùng” | Khi chỉ còn một chỗ và hai yêu cầu đồng thời, tối đa một yêu cầu được xác nhận |
| “Chức năng hoạt động tốt trên di động” | Xác định nhóm kích thước màn hình và tác vụ quan trọng, kiểm tra thao tác và khả năng truy cập |
| “Xử lý mọi lỗi” | Liệt kê lỗi có tác động cao và hành vi mong đợi; lỗi không xác định phải có phương án an toàn phù hợp |

Trường hợp có số đo, **ngưỡng cụ thể phải do nhóm xác định theo bối cảnh**. Ví dụ “p95 dưới 500 ms” có thể là một mục tiêu thử nghiệm ở một hệ thống nhất định, nhưng không phải chuẩn phổ quát cho mọi sản phẩm.

### Given–When–Then giúp kiểm tra cách hiểu chung

Giả sử story:

> Là người bệnh, tôi muốn xem các giờ còn trống ở một cơ sở theo ngày, để biết khi nào có thể đặt lịch.

Nhóm thống nhất các quy tắc minh họa:

1. Người dùng chọn một cơ sở và một ngày.
2. Hệ thống chỉ hiển thị giờ còn chỗ theo nguồn dữ liệu lịch đã thống nhất.
3. Nếu không có giờ còn chỗ, hiển thị thông báo rõ và gợi ý chọn ngày khác.
4. Khi không truy vấn được lịch, không được hiển thị dữ liệu cũ như thể đó là dữ liệu đang chắc chắn còn chỗ.
5. Thời gian hiển thị theo múi giờ của cơ sở; điều này phải được làm rõ với nghiệp vụ và người dùng.

Ví dụ kiểm thử chấp nhận theo định dạng **Given–When–Then**:

~~~gherkin
Tính năng: Xem khung giờ còn chỗ

  Kịch bản: Có hai khung giờ còn chỗ trong ngày
    Cho cơ sở A sử dụng múi giờ Asia/Ho_Chi_Minh
    Và ngày 12/12/2026 có hai giờ còn chỗ là 09:00 và 10:30
    Khi người bệnh chọn cơ sở A và ngày 12/12/2026
    Thì hệ thống hiển thị giờ 09:00 và 10:30
    Và không hiển thị các giờ đã hết chỗ như còn trống

  Kịch bản: Không có giờ còn chỗ
    Cho cơ sở A không còn khung giờ trống trong ngày đã chọn
    Khi người bệnh xem lịch của ngày đó
    Thì hệ thống thông báo không còn khung giờ phù hợp
    Và người bệnh có thể chọn một ngày khác

  Kịch bản: Không thể lấy dữ liệu lịch
    Cho dịch vụ cung cấp lịch hiện không phản hồi
    Khi người bệnh xem các khung giờ
    Thì hệ thống thông báo chưa thể tải lịch
    Và không hiển thị giờ chưa được xác thực như thể chắc chắn còn chỗ
~~~

Các dữ liệu trong ví dụ chỉ dùng để giải thích cách viết tiêu chí; không phải lịch khám thật. Khi đưa vào hệ thống, nhóm cần kiểm tra cả điều kiện dữ liệu, quyền truy cập và cách hiện thực phụ thuộc.

### Acceptance criteria khác Definition of Done

| Khái niệm | Đối tượng và mục đích | Ví dụ |
| --- | --- | --- |
| **Acceptance criteria** | Kỳ vọng riêng của một story / Product Backlog Item | Không có giờ trống thì hiển thị thông báo; không hiển thị lịch lỗi là còn trống |
| **Definition of Done (DoD)** | Chuẩn chất lượng chung để Increment được coi là hoàn thành | Kiểm thử cần thiết đạt, mã tích hợp, bảo mật và kiểm tra chất lượng theo tiêu chuẩn nhóm |

Trong Scrum, **Definition of Done là commitment gắn với Increment**. Đáp ứng acceptance criteria nhưng **chưa đạt DoD** không làm Increment trở thành đã hoàn thành. Ngược lại, một Increment đạt DoD chưa chứng minh người dùng thấy tính năng có giá trị; vẫn cần quan sát outcome sau khi đưa vào ngữ cảnh phù hợp.

**Câu hỏi kiểm tra:** “Nếu hai người độc lập thử story này, họ có thể quan sát và đi đến cùng kết luận đạt/chưa đạt dựa trên các ví dụ đã thống nhất không?”

## 8. Ví dụ trọn vẹn: cải thiện một story qua sáu tiêu chí INVEST

### Bản nháp ban đầu

> “Là người dùng, tôi muốn có hệ thống đặt lịch hoàn chỉnh, nhanh và hiện đại, gồm đăng ký, tìm bác sĩ, lọc cơ sở, giữ chỗ, thanh toán và nhắc lịch bằng SMS, để đặt lịch tiện lợi.”

**Đánh giá ban đầu:**

| Tiêu chí | Vấn đề ở bản nháp |
| --- | --- |
| **Independent** | Nhiều mảng chỉ có ý nghĩa khi hoàn thành toàn bộ luồng lớn |
| **Negotiable** | Ấn định sẵn SMS và nhiều thành phần giải pháp |
| **Valuable** | “Tiện lợi” và “người dùng” quá chung; chưa rõ vấn đề đang ưu tiên |
| **Estimable** | Chưa rõ phạm vi cơ sở, thanh toán, lịch bác sĩ, tích hợp và quy tắc |
| **Small** | Gom nhiều hành trình và khả năng trong một story |
| **Testable** | “Nhanh”, “hiện đại”, “hoàn chỉnh” thiếu điều kiện kiểm chứng |

Nhóm không nên sửa bản nháp chỉ bằng cách thêm từ vào câu. Họ cần trao đổi để phát hiện **mục tiêu và giả định nào đáng kiểm chứng trước**.

### Bước 1 — Làm rõ vấn đề và người dùng

Sau khi trao đổi với đại diện cơ sở và quan sát người đặt lịch, nhóm có giả thuyết:

> Người bệnh tại cơ sở A bỏ dở vì khó xác định ngày nào còn giờ khám phù hợp.

Nhóm chọn một lát cắt trước khi xây cả hệ thống thanh toán, đổi lịch và SMS:

> **Story A:** Là người bệnh muốn khám tại cơ sở A, tôi muốn xem các giờ còn trống theo ngày, để chọn được ngày có khả năng đặt lịch phù hợp.

Chưa có nghĩa là nhóm đã chứng minh vấn đề; đây là **lát cắt để kiểm chứng giả thuyết**.

### Bước 2 — Xác định giới hạn của lát cắt

Phạm vi đầu tiên gồm:

- Chỉ **một cơ sở A** với nguồn lịch đã được xác định.
- Người bệnh chọn ngày và xem giờ còn trống, kể cả trạng thái không có chỗ.
- Không tự động giữ chỗ khi chỉ xem lịch.
- Không tuyên bố có thể đặt thành công nếu chưa triển khai quy trình xác nhận.
- Trình bày rõ khi dữ liệu lịch lỗi hoặc chưa được cập nhật.

Nhóm ghi rõ những yêu cầu **ngoài phạm vi lần đầu**: thanh toán, nhắc SMS, nhiều cơ sở, đổi/hủy lịch. Nếu quy tắc về khả năng hiển thị giờ trống phụ thuộc quyền truy cập hoặc dữ liệu nhạy cảm, vẫn phải xử lý ràng buộc đó ngay.

### Bước 3 — Đặt tiêu chí chấp nhận

| Tình huống | Mong đợi |
| --- | --- |
| Ngày có giờ còn chỗ | Chỉ hiển thị những giờ còn chỗ của cơ sở và ngày được chọn |
| Ngày không còn giờ | Hiển thị trạng thái không có giờ và cho phép chọn ngày khác |
| Dịch vụ lịch không phản hồi | Không biểu diễn dữ liệu chưa xác nhận như lịch còn chỗ; có thông báo phù hợp |
| Người dùng đổi ngày | Danh sách giờ thay đổi theo ngày được chọn, không giữ kết quả của ngày cũ như thể đúng |
| Múi giờ | Hiển thị theo quy tắc múi giờ đã thống nhất với cơ sở |

Kèm kiểm thử kỹ thuật cần thiết và quan sát người dùng thử tác vụ “tìm một ngày có thể đến khám”. Dữ liệu người dùng giúp nhóm biết cách trình bày có dễ hiểu không; kiểm thử giúp xác nhận hệ thống tuân thủ quy tắc đã thống nhất.

### Bước 4 — Xem lại INVEST sau cải thiện

| Tiêu chí | Đánh giá có điều kiện cho Story A |
| --- | --- |
| **I** | Có thể kiểm chứng một khả năng xem lịch riêng; vẫn cần API và dữ liệu cơ sở A |
| **N** | Người dùng cần thấy lịch còn chỗ; cách hiển thị vẫn có thể trao đổi và thử |
| **V** | Giúp người bệnh quyết định ngày khám, liên hệ với mục tiêu tự phục vụ |
| **E** | Phạm vi và nguồn dữ liệu đã giới hạn; cần xác nhận thêm nếu API không ổn định |
| **S** | Một luồng nhỏ hơn nhiều so với toàn bộ đặt lịch; nhóm cần kiểm tra năng lực thực tế để biết có phù hợp Sprint không |
| **T** | Có các tình huống cụ thể về ngày có/không có lịch, lỗi dữ liệu, đổi ngày và múi giờ |

Đánh giá là **nhận định của nhóm sau khi có thêm thông tin**, không thể thay bằng dấu tích tự động. Nếu phát hiện tích hợp lịch phức tạp hơn dự kiến, story vẫn có thể cần một spike kỹ thuật hoặc chia lại.

### Bước 5 — Quyết định story kế tiếp dựa trên phản hồi

Nếu người bệnh hiểu lịch trống nhưng không biết liệu “chọn giờ” đã được xác nhận, nhóm có thể ưu tiên:

> **Story B:** Là người bệnh, tôi muốn gửi yêu cầu đặt một giờ đã chọn và biết kết quả xác nhận, để không phải gửi trùng hoặc gọi điện kiểm tra.

Story B cần làm rõ quy tắc giữ chỗ, xử lý cạnh tranh đồng thời và thông điệp khi xác nhận thất bại. Không nên chỉ ghép nút “Đặt ngay” vào Story A nếu hệ thống chưa có cơ chế xác nhận đáng tin cậy.

Điều này minh họa chu trình **viết story → làm rõ → chia lát cắt → bàn giao → kiểm chứng → cập nhật backlog**, gắn INVEST với tư duy Agile thay vì dùng nó như bài kiểm tra lý thuyết.

## 9. Thảo luận INVEST trong buổi backlog refinement

**Product Backlog refinement** là hoạt động liên tục chia nhỏ và làm rõ các Product Backlog Item. Có thể dùng INVEST theo trình tự ngắn để cải thiện chất lượng cuộc hội thoại.

### Quy trình thực hành gợi ý

1. **Nhắc lại Product Goal hoặc mục tiêu liên quan.** Story đang giải quyết vấn đề nào và vì sao được xem xét?
2. **Đọc story bằng ngôn ngữ người dùng.** Người hưởng lợi, khả năng và kết quả mong muốn đã rõ chưa?
3. **Xem I và V trước.** Có giá trị riêng và phụ thuộc nào khiến không thể giao phần nhỏ?
4. **Xem N.** Những phần nào thực sự bắt buộc, phần nào là lựa chọn giải pháp?
5. **Xem S và E.** Có thể thu hẹp phạm vi, chia lát cắt hoặc kiểm chứng bất định trước khi ước lượng?
6. **Xem T.** Liệt kê các ví dụ chấp nhận, đặc biệt trường hợp biên, lỗi và các điều kiện quan trọng.
7. **Chốt điều còn mở và việc tiếp theo.** Ghi quyết định, người phụ trách câu hỏi, phần cần nghiên cứu hoặc story được chia.

Mỗi bước không nhất thiết tương ứng một cuộc họp. Một nhóm có Product Owner, Developers, người kiểm thử và chuyên gia nghiệp vụ đủ gần công việc có thể làm rõ ngay khi phát sinh câu hỏi. Với Kanban, nhóm có thể dùng những câu hỏi này trước khi kéo một mục vào làm; với Scrum, chúng giúp chuẩn bị cho Sprint Planning và bàn giao Increment có thể kiểm chứng.

### Những câu hỏi nên có người trả lời

| INVEST | Câu hỏi gợi ý trong refinement | Ai nên góp thông tin? |
| --- | --- | --- |
| **I** | Story này đang chờ hạng mục nào? Có cách chia để giải phóng phụ thuộc không? | Developers, người phụ trách tích hợp, Product Owner |
| **N** | Điều gì là mục tiêu, điều gì chỉ là phương án đề xuất? | Người hiểu người dùng, nghiệp vụ, thiết kế và kỹ thuật |
| **V** | Nếu hoàn thành, ai được lợi và kết quả nào có thể thay đổi? | Product Owner, stakeholder, người dùng |
| **E** | Bất định nào khiến ước lượng chênh lệch? Có thể thử trước không? | Developers, kiểm thử, chuyên gia kỹ thuật |
| **S** | Có thể cắt một lát nhỏ dùng được trong kỳ này không? | Product Owner và Developers |
| **T** | Có ví dụ đủ rõ cho cả luồng chính và lỗi quan trọng không? | Nghiệp vụ, Developers và kiểm thử |

Người ra quyết định ưu tiên và đánh đổi cần được xác định rõ. Trong Scrum, **Product Owner chịu trách nhiệm quản lý Product Backlog**; Developers chịu trách nhiệm tạo kế hoạch triển khai và chất lượng Increment. INVEST giúp trao đổi, **không thay thế các trách nhiệm này**.

## 10. INVEST có liên hệ thế nào với Sprint Goal và Definition of Ready?

Ba khái niệm thường bị đánh đồng:

- **INVEST:** Heuristic kiểm tra chất lượng và khả năng làm rõ của một user story.
- **Definition of Ready (DoR):** Một thỏa thuận tùy chọn mà một số nhóm dùng để xác định khi nào một hạng mục đủ thông tin để cân nhắc bắt đầu. **DoR không phải artifact hoặc commitment bắt buộc trong Scrum Guide.**
- **Definition of Done (DoD):** Mô tả chính thức trạng thái của Increment khi đáp ứng những tiêu chuẩn chất lượng được yêu cầu; **DoD là commitment của Increment trong Scrum**.

| Khía cạnh | INVEST | DoR (nếu nhóm dùng) | DoD |
| --- | --- | --- | --- |
| Dùng khi nào? | Trong khám phá và refinement story | Trước khi nhận công việc theo chính sách nhóm | Khi đánh giá Increment đã hoàn thành |
| Trọng tâm | Giá trị, kích thước, khả năng triển khai/kiểm chứng và tính linh hoạt | Thông tin, phụ thuộc hoặc điều kiện tối thiểu để bắt đầu | Chất lượng và sự hoàn thành của sản phẩm |
| Bắt buộc theo Scrum Guide? | Không | Không | Có, dưới dạng commitment của Increment |
| Có thay thế kết quả người dùng không? | Không | Không | Không |

Một story có vẻ đạt INVEST vẫn có thể bị xếp sau nếu **ít đóng góp cho Product Goal**. Một story chưa rõ có thể được ưu tiên nghiên cứu nếu chứa rủi ro lớn. Và một Increment không đạt DoD thì chưa được coi là hoàn thành chỉ vì story đã được đánh dấu “đạt INVEST”.

### Tránh biến checklist thành cổng phê duyệt cứng nhắc

Nếu nhóm yêu cầu mọi story phải có sáu ô đều “100% đạt” trước khi thảo luận, họ dễ tạo thêm hàng chờ và hình thức. Thay vì vậy, xác định **điểm nào còn thiếu, ảnh hưởng ra sao và quyết định gì cần thực hiện**. Ví dụ:

> “Story có giá trị, nhỏ, có ví dụ chấp nhận, nhưng chưa ước lượng được vì API đối tác chưa rõ. Tạo phép thử tích hợp có giới hạn, cập nhật ước lượng và cân nhắc lại sau khi có kết quả.”

Đây là kết luận hành động được, tốt hơn việc chỉ gán điểm E = 0 và bỏ story.

## 11. Lỗi thường gặp khi sử dụng INVEST

| Dấu hiệu | Vì sao chưa ổn? | Cách sửa |
| --- | --- | --- |
| **Mọi story phải độc lập tuyệt đối** | Một số phụ thuộc nghiệp vụ và kỹ thuật là cần thiết | Giảm phụ thuộc không cần thiết, công khai phần bắt buộc |
| **Nghĩ Negotiable nghĩa là chưa cần quy tắc** | Quy tắc quan trọng không rõ dẫn đến sai dữ liệu và làm lại | Giữ mục tiêu/ràng buộc chắc chắn, thương lượng giải pháp |
| **Gán “Là người dùng...” cho mọi task hạ tầng** | Vai trò người dùng giả, giá trị bị che khuất | Ghi PBI kỹ thuật với rủi ro hoặc năng lực được cải thiện |
| **Ước lượng chính xác tới từng giờ mới đạt E** | Tạo độ chắc chắn giả và tốn công vô ích | Ước lượng ở mức có ích; thể hiện bất định còn lại |
| **Chia theo frontend/backend/database** | Mỗi phần khó bàn giao giá trị và lấy phản hồi riêng | Chia lát cắt dọc theo hành vi người dùng |
| **Chia story nhỏ đến mức mất mục tiêu** | Backlog thành danh sách thao tác, không còn giá trị | Giữ một khả năng có ý nghĩa; chi tiết là task |
| **T chỉ kiểm tra luồng thành công** | Bỏ sót lỗi, giới hạn hoặc trường hợp nguy hiểm | Thêm trường hợp biên, lỗi và điều kiện chất lượng phù hợp |
| **Đánh dấu “testable” vì có thể viết unit test** | Test logic không chứng minh nhu cầu và trải nghiệm | Kết hợp acceptance test với phản hồi người dùng |
| **INVEST được dùng như điểm KPI cá nhân** | Khuyến khích tạo nhiều story dễ đạt điểm hơn là giải quyết vấn đề | Dùng để cải thiện trao đổi và dòng công việc của nhóm |
| **Mọi phản hồi đều khiến phải viết lại story đang làm** | Mất tập trung và có thể làm hỏng Sprint Goal | Đánh giá tác động, cập nhật backlog và thương lượng phạm vi đúng lúc |

**Lưu ý về trade-off:** Cải thiện một tiêu chí có thể ảnh hưởng tiêu chí khác. Story độc lập hơn có thể cần công sức chuẩn bị tích hợp; story nhỏ hơn có thể mất giá trị nếu không còn hành vi sử dụng được. Mục tiêu là **cân bằng để giao giá trị và học hỏi**, không tối đa hóa điểm của từng chữ.

## 12. Đánh giá INVEST một cách thực dụng

Nhóm có thể dùng ba mức thảo luận:

| Mức | Nghĩa | Hành động |
| --- | --- | --- |
| **Rõ / phù hợp hiện tại** | Có đủ bối cảnh để tiến tới bước tiếp theo | Tiếp tục theo ưu tiên và kế hoạch |
| **Cần làm rõ** | Còn câu hỏi nhưng có thể giải quyết bằng trao đổi hoặc ví dụ ngắn | Ghi câu hỏi và người phụ trách, bổ sung tiêu chí |
| **Rủi ro lớn / chưa phù hợp** | Có phụ thuộc, bất định hoặc phạm vi khiến khó bàn giao an toàn | Chia nhỏ, thay đổi cách tiếp cận, thử nghiệm giới hạn hoặc xem lại ưu tiên |

Đây là **thang gợi ý cho thảo luận**, không phải chuẩn INVEST chính thức hay yêu cầu phần mềm phải tính điểm. Thay vì điền bảng 6 × 5 điểm rồi cộng, nên ghi **lý do và việc phải làm** cho những tiêu chí chưa phù hợp.

Mẫu ghi nhận ngắn cho một story:

~~~text
Story:
  Người bệnh xem các giờ khám còn chỗ theo ngày tại cơ sở A.

Giá trị / Product Goal:
  Giảm việc phải gọi hỏi giờ khám; tăng khả năng tự tìm lịch.

Đánh giá INVEST:
  I: Khá rõ; cần xác nhận API lịch của cơ sở A.
  N: Giữ cách trình bày mở; quy tắc "còn chỗ" là bắt buộc.
  V: Giá trị với người muốn chọn ngày khám.
  E: Chưa chắc do tốc độ và chất lượng dữ liệu API.
  S: Giới hạn một cơ sở; sẽ xem lại sau kiểm tra tích hợp.
  T: Có ví dụ lịch có chỗ, hết chỗ và lỗi nguồn dữ liệu.

Việc tiếp theo:
  Thử truy vấn API lịch với dữ liệu mẫu phù hợp,
  cập nhật phụ thuộc và ước lượng trước khi chọn vào Sprint.
~~~

Khi cần chọn story để triển khai, nhóm cần nhìn thêm mức độ ưu tiên, năng lực và rủi ro hiện tại. **“Đạt INVEST” không tự động có nghĩa là nên làm ngay**.

## 13. Kiểm tra hiệu quả bằng kết quả thực tế

INVEST là cách cải thiện **đầu vào công việc**. Cần kiểm chứng xem cách cải thiện đó có giúp nhóm tạo kết quả tốt hơn không:

| Tín hiệu | Có thể nói gì? | Điều cần tránh |
| --- | --- | --- |
| **Cycle time** của các lát cắt | Story đi từ bắt đầu đến hoàn tất có bớt chờ không? | Giảm thời gian bằng cách bỏ kiểm thử |
| **Thời gian bị chặn vì phụ thuộc** | Tính độc lập và cách phối hợp có tiến bộ không? | Đổ lỗi cá nhân cho phụ thuộc hệ thống |
| **Số lần làm lại do hiểu sai** | Conversation và Confirmation có giúp làm rõ không? | Xem mọi thay đổi dựa trên học hỏi là thất bại |
| **Tỷ lệ hạng mục hoàn thành theo kế hoạch** | Kích thước và ước lượng có phù hợp với cách nhóm làm việc không? | Chạy theo số lượng story hoặc story point |
| **Thời gian tới phản hồi người dùng** | Các lát cắt có giúp kiểm chứng giá trị sớm không? | Coi bản build xanh là phản hồi về nhu cầu |
| **Chỉ số outcome và lỗi sản phẩm** | Thay đổi có giúp người dùng đạt mục tiêu mà vẫn an toàn không? | Quy giá trị cho story chỉ vì đã phát hành |

Ví dụ, sau khi nhóm chuyển từ story “xây toàn bộ hệ thống đặt lịch” sang các lát cắt có thể dùng được, **thời gian đến bản thử đầu tiên** có thể ngắn lại. Nhưng nếu chỉ số đặt lịch thành công không cải thiện, cần xem lại **giả thuyết về nhu cầu**, không chỉ tiếp tục chia story nhỏ hơn.

Số liệu nên được quan sát theo xu hướng và bối cảnh; không nên dùng thành tích INVEST hoặc velocity để so sánh cá nhân và các nhóm khác nhau.

## 14. Bài thực hành: phát hiện và sửa story chưa đạt INVEST

### Bài 1 — Chỉ ra tiêu chí có nguy cơ

Xem các story sau:

| Story | Gợi ý vấn đề |
| --- | --- |
| A. “Là người mua, tôi muốn toàn bộ thanh toán, hoàn tiền, mã giảm giá, tích điểm và xuất hóa đơn trên mọi nền tảng để mua nhanh hơn.” | Quá lớn; phụ thuộc và yêu cầu chưa rõ |
| B. “Là người học, tôi muốn một nút đỏ kích thước 200 × 50 px dùng thư viện Y để bắt đầu học.” | Khóa giải pháp; giá trị chưa được nêu |
| C. “Là người quản trị, tôi muốn báo cáo thật đẹp và tải nhanh.” | Khó kiểm chứng “đẹp”, “nhanh”; đối tượng và mục đích chưa rõ |
| D. “Là hệ thống, tôi muốn di chuyển cơ sở dữ liệu để nâng cấp thành công.” | Giá trị và đối tượng hưởng lợi không rõ; có thể là PBI kỹ thuật |
| E. “Là khách, tôi muốn xem tình trạng đơn hàng trong ngày để biết có cần liên hệ hỗ trợ không.” | Có giá trị, nhưng còn thiếu quy tắc trạng thái và ví dụ |

**Yêu cầu:** Với mỗi story, đánh dấu tiêu chí cần hỏi thêm, rồi viết **ít nhất một câu hỏi làm rõ**. Không cần gán “đạt/trượt” cứng nhắc nếu thiếu thông tin.

### Bài 2 — Sửa một story theo sáu tiêu chí

Chọn Story C. Một phương án cải thiện:

> Là quản lý hỗ trợ khách hàng, tôi muốn xem số đơn hàng giao trễ trong bảy ngày gần nhất theo từng ngày, để nhận biết thời điểm có nhiều đơn cần xử lý.

Ví dụ câu hỏi để hoàn chỉnh:

1. **I:** Báo cáo có thể lấy từ dữ liệu đơn hiện tại mà không chờ hệ thống BI mới không?
2. **N:** Biểu đồ cột hay bảng là giải pháp phù hợp hơn với người dùng thử? Phần nào bắt buộc?
3. **V:** Quản lý sẽ đưa ra quyết định nào nhờ báo cáo?
4. **E:** Quy tắc “giao trễ” xác định theo thời hạn nào và có dữ liệu lịch sử không?
5. **S:** Lần đầu chỉ báo cáo theo ngày trong một khu vực, chưa cần lọc mọi chi nhánh được không?
6. **T:** Với bộ dữ liệu mẫu xác định rõ đơn trễ/không trễ, tổng theo từng ngày có đúng không? Khi thiếu dữ liệu hiển thị thế nào?

Đây là **phương án gợi ý**. Nếu quản lý cần báo cáo theo ca trực, không phải theo ngày, nhóm phải cập nhật story theo nhu cầu thực tế.

### Bài 3 — Tách epic thành các lát cắt có giá trị

**Epic:** “Người học quản lý tiến độ học tập, chứng chỉ, nhắc học, thảo luận nhóm và phân tích kết quả”.

Hãy đề xuất ba lát cắt:

1. Người học xem tiến độ các bài đã bắt đầu và biết bài nào chưa hoàn thành.
2. Người học tiếp tục tại bài gần nhất, với trạng thái đã lưu nhất quán.
3. Người học nhận thông báo nhắc tiếp tục học nếu chủ động bật và lựa chọn kênh phù hợp.

Với mỗi lát cắt, trả lời: **giá trị riêng là gì, có thể thử với ai, phụ thuộc nào cần giải quyết, tiêu chí chấp nhận đầu tiên là gì?** Nếu quy định lưu tiến độ hoặc quyền riêng tư yêu cầu xử lý ngay từ lát cắt đầu, hãy đưa điều kiện đó vào phạm vi thay vì để về sau.

### Bài 4 — Phân biệt story và task

Sắp xếp các hạng mục sau theo vai trò hợp lý trong Product Backlog và kế hoạch thực hiện:

- “Người mua biết rõ tổng tiền trước khi xác nhận đơn.”
- “Tạo bảng lưu thông tin phí vận chuyển.”
- “Viết test trường hợp API tính phí không phản hồi.”
- “Cải thiện cơ chế bảo vệ dữ liệu thanh toán theo rủi ro đã xác định.”

**Gợi ý:** Hạng mục thứ nhất có thể là user story tạo khả năng người mua; các việc tạo bảng và viết test có thể là task để thực hiện story. Công việc bảo vệ dữ liệu có thể là **Product Backlog Item kỹ thuật riêng** nếu phạm vi và giá trị giảm rủi ro đủ độc lập, hoặc là phần bắt buộc của Definition of Done/kiểm soát chất lượng trong hạng mục liên quan. Cách tổ chức tùy ngữ cảnh, miễn người thực hiện hiểu mục đích và mức chất lượng yêu cầu.

## 15. Câu hỏi ôn tập

1. INVEST gồm sáu chữ nào, và mỗi chữ kiểm tra đặc điểm gì của user story?
2. Vì sao story đúng mẫu “Là..., tôi muốn..., để...” vẫn có thể chưa tốt?
3. Tính độc lập tuyệt đối có phải điều kiện bắt buộc của mọi user story không?
4. Negotiable khác với việc “chưa cần quyết định quy tắc nghiệp vụ” thế nào?
5. Một công việc cải thiện bảo mật nhưng không có giao diện trực tiếp có thể có giá trị không? Nên mô tả ra sao?
6. Khi không thể ước lượng vì API đối tác chưa rõ, bước tiếp theo hữu ích là gì?
7. Vì sao chia story theo frontend/backend/database thường chưa tạo lát cắt giá trị?
8. Testable có bắt buộc mọi tiêu chí chấp nhận đều viết thành kiểm thử tự động không?
9. Acceptance criteria và Definition of Done khác nhau như thế nào?
10. Story có vẻ đáp ứng đủ INVEST nhưng không đóng góp nhiều cho Product Goal có nên được ưu tiên trước không?
11. Việc ép dùng DoR cứng nhắc có thể gây vấn đề gì cho dòng công việc?
12. Những tín hiệu nào cho thấy cách dùng INVEST đã giúp nhóm nhận phản hồi và giao giá trị tốt hơn?

**Ghi nhớ:** **INVEST** giúp nhóm đặt sáu câu hỏi đúng về user story: **đủ độc lập, có thể thương lượng, tạo giá trị, ước lượng được, đủ nhỏ và kiểm chứng được**. Giá trị của INVEST nằm ở **cuộc trao đổi và các quyết định làm story rõ hơn**, không nằm ở việc đánh dấu đủ sáu ô. Một story tốt giúp đội giao một phần giá trị có chất lượng, học sớm từ phản hồi và điều chỉnh Product Backlog theo mục tiêu sản phẩm.
