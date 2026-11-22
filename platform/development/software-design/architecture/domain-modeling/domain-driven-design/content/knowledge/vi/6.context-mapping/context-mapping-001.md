# Bản đồ ngữ cảnh (Context Map) và các quan hệ phụ thuộc

Trong Domain-Driven Design (DDD), mỗi **Bounded Context** xác định ranh giới mà bên trong đó một mô hình miền và ngôn ngữ chung có ý nghĩa nhất quán. Khi hệ thống có nhiều Bounded Context, các mô hình không tồn tại độc lập hoàn toàn: chúng có thể trao đổi dữ liệu, cung cấp năng lực, chia sẻ một phần mô hình hoặc phụ thuộc vào quyết định của nhau.

**Context Map** là bản đồ mô tả các Bounded Context và mối quan hệ giữa chúng. Nó giúp đội phát triển nhìn thấy ai cung cấp thông tin hoặc năng lực cho ai, mô hình được trao đổi theo cách nào, nhóm nào có quyền quyết định và nơi nào cần cơ chế bảo vệ mô hình miền. Bản đồ này là công cụ của strategic design, đồng thời cung cấp căn cứ để thiết kế tích hợp và tổ chức cộng tác giữa các đội.

Một Context Map có ích khi trả lời được những câu hỏi:

- Có những Bounded Context nào trong phạm vi hệ thống?
- Mỗi context chịu trách nhiệm cho phần nghiệp vụ nào?
- Context nào cung cấp dữ liệu hoặc dịch vụ cho context nào?
- Bên nào có ảnh hưởng đến mô hình, hợp đồng và lịch thay đổi?
- Hai bên có dùng chung ngôn ngữ và mô hình hay cần chuyển đổi?
- Quan hệ phụ thuộc có đang làm một nhóm bị chậm hoặc bị buộc phải thay đổi theo nhóm khác không?
- Cần áp dụng cách cộng tác hoặc tích hợp nào để bảo vệ tính nhất quán của từng mô hình?

## 1. Bounded Context và lý do cần Context Map

### 1.1. Bounded Context là ranh giới của mô hình

Bounded Context là ranh giới trong đó một mô hình miền, thuật ngữ và quy tắc được định nghĩa nhất quán. Một thuật ngữ có thể mang ý nghĩa khác nhau ở những context khác nhau.

Ví dụ trong thương mại điện tử:

- Trong **Catalog Context**, Product mô tả sản phẩm được giới thiệu: tên, mô tả, hình ảnh, thuộc tính và danh mục.
- Trong **Inventory Context**, sản phẩm được quan tâm dưới góc nhìn mã hàng, số lượng có thể bán, vị trí lưu kho và trạng thái giữ chỗ.
- Trong **Ordering Context**, dòng hàng trong đơn cần thông tin sản phẩm tại thời điểm đặt hàng, số lượng, đơn giá đã chốt và các điều kiện liên quan.
- Trong **Shipping Context**, hàng hóa được biểu diễn theo kiện, trọng lượng, kích thước, địa chỉ và yêu cầu giao nhận.

Cùng một sản phẩm vật lý có thể xuất hiện trong các mô hình này, nhưng mỗi context chỉ giữ những khái niệm và quy tắc cần thiết cho trách nhiệm của nó. Nếu cố gắng ép mọi nhóm dùng một mô hình Product duy nhất, thay đổi của kho có thể ảnh hưởng đến catalog, còn yêu cầu của vận chuyển có thể làm mô hình đặt hàng trở nên khó hiểu.

### 1.2. Context Map cho thấy quan hệ giữa các ranh giới

Khi đã xác định các Bounded Context, đội cần hiểu cách chúng liên hệ với nhau. Context Map đặt các context lên cùng một bức tranh và biểu diễn quan hệ giữa chúng.

Context Map có thể ghi nhận:

- **Ranh giới và quyền sở hữu:** tên context, trách nhiệm nghiệp vụ và đội sở hữu.
- **Chiều phụ thuộc:** context upstream cung cấp năng lực hoặc thông tin; context downstream sử dụng và chịu ảnh hưởng.
- **Kiểu quan hệ:** hai đội hợp tác, chia sẻ mô hình, một bên cung cấp cho bên kia, hoặc bên tiêu thụ phải thích nghi với mô hình bên cung cấp.
- **Cách tích hợp:** API, sự kiện, batch, trao đổi tệp hoặc quy trình thủ công.
- **Cách bảo vệ mô hình:** chuyển đổi dữ liệu, Published Language, Open Host Service hoặc Anti-Corruption Layer.
- **Vấn đề cần cải thiện:** phụ thuộc chặt, thay đổi không đồng bộ, ngôn ngữ mơ hồ hoặc thiếu chủ sở hữu hợp đồng.

Context Map không nhất thiết mô tả đầy đủ mọi thành phần kỹ thuật. Nó tập trung vào quan hệ giữa các mô hình và các nhóm chịu trách nhiệm. Chi tiết triển khai như topic, endpoint, database hay giao thức có thể được liên kết trong tài liệu kỹ thuật riêng.

### 1.3. Context Map không phải sơ đồ phòng ban hay sơ đồ microservice

Một phòng ban có thể sở hữu nhiều Bounded Context; một Bounded Context cũng có thể cần nhiều nhóm cùng tham gia. Tương tự, một Bounded Context có thể được triển khai bằng nhiều service, hoặc nhiều context có thể cùng tồn tại trong một ứng dụng.

Do đó:

- Không suy ra Bounded Context chỉ từ cơ cấu tổ chức.
- Không mặc định mỗi microservice là một Bounded Context.
- Không vẽ một mũi tên chỉ vì hai service gọi API của nhau; cần hiểu quan hệ nghiệp vụ và quyền quyết định phía sau.
- Không dùng Context Map để thay thế sơ đồ luồng dữ liệu, sơ đồ triển khai hoặc sơ đồ mạng.

Một sơ đồ kỹ thuật có thể cho biết hệ thống nào gọi hệ thống nào. Context Map cần giải thích thêm ý nghĩa nghiệp vụ, sự phụ thuộc về mô hình và cách các đội quản lý quan hệ đó.

## 2. Upstream và Downstream

Upstream và downstream là hai vai trò tương đối trong một quan hệ giữa các context.

### Upstream

**Upstream Context** là phía cung cấp năng lực, dữ liệu hoặc mô hình mà context khác phụ thuộc vào. Thay đổi trong upstream có thể ảnh hưởng đến downstream.

Ví dụ, Catalog Context công bố thông tin sản phẩm để Search Context lập chỉ mục. Trong quan hệ này, Catalog là upstream đối với Search.

Upstream thường chịu trách nhiệm:

- Xác định và duy trì mô hình mà nó sở hữu.
- Công bố hợp đồng hoặc cách trao đổi mà downstream có thể sử dụng.
- Thông báo thay đổi có ảnh hưởng đến bên tiêu thụ.
- Phối hợp kiểm thử và xử lý sự cố theo thỏa thuận giữa các bên.

Upstream không có nghĩa là bên quản lý cao hơn, quan trọng hơn hoặc có quyền điều khiển toàn bộ downstream. Đây chỉ là vai trò trong một quan hệ phụ thuộc cụ thể.

### Downstream

**Downstream Context** là phía tiêu thụ năng lực hoặc thông tin từ upstream. Nó phải xử lý ảnh hưởng khi upstream thay đổi, trừ khi hai bên có cơ chế phối hợp hoặc cách ly phù hợp.

Ví dụ, Checkout Context sử dụng thông tin giá từ Pricing Context để tạo đơn hàng. Trong quan hệ này, Pricing là upstream và Checkout là downstream.

Downstream cần làm rõ:

- Dữ liệu hoặc hành vi nào thực sự cần từ upstream?
- Nó phụ thuộc vào cấu trúc dữ liệu, thuật ngữ hay quy tắc nào?
- Có thể chấp nhận độ trễ, dữ liệu thiếu hoặc thay đổi phiên bản đến mức nào?
- Cần chuyển đổi mô hình bên ngoài sang mô hình nội bộ ra sao?
- Ai chịu trách nhiệm khi hợp đồng thay đổi hoặc dữ liệu không hợp lệ?

### 2.1. Chiều quan hệ không đồng nghĩa với chiều dữ liệu

Một context có thể gửi dữ liệu ngược lại cho upstream, ví dụ gửi phản hồi, trạng thái hoặc kết quả xử lý. Vai trò upstream/downstream mô tả sự phụ thuộc về năng lực và quyền định hình mô hình, không đơn thuần mô tả hướng truyền thông điệp.

Một quan hệ có thể có nhiều luồng dữ liệu, nhưng vẫn cần xác định rõ ai là bên cung cấp mô hình hoặc dịch vụ mà bên kia phụ thuộc. Nếu hai context thực sự cùng quyết định và phải phối hợp chặt, có thể xem xét Partnership thay vì cố gán một bên là chủ đạo.

### 2.2. Một context có thể có nhiều vai trò

Vai trò upstream hoặc downstream được xác định theo từng cặp quan hệ. Một context có thể là upstream với context này, đồng thời là downstream với context khác.

Ví dụ:

- Catalog là upstream đối với Search.
- Catalog có thể là downstream đối với Supplier Integration nếu nó nhận thông tin sản phẩm từ nhà cung cấp.
- Ordering có thể là downstream đối với Pricing và Inventory, nhưng lại là upstream đối với Fulfillment khi phát sự kiện đơn hàng đã xác nhận.

Khi vẽ bản đồ, hãy ghi vai trò trên từng quan hệ thay vì gắn nhãn upstream/downstream cố định cho toàn bộ context.

## 3. Các pattern quan hệ giữa Bounded Context

DDD cung cấp một số pattern để mô tả cách các nhóm và mô hình phối hợp. Pattern không phải nhãn trang trí; nó diễn tả quyền ảnh hưởng, cách chia sẻ tri thức và cách bảo vệ mô hình. Một quan hệ thực tế có thể kết hợp nhiều pattern ở những khía cạnh khác nhau.

### 3.1. Partnership – Quan hệ đối tác

Partnership xuất hiện khi hai nhóm phụ thuộc đáng kể vào nhau và cần cùng thành công. Không bên nào có thể đơn phương quyết định mọi thay đổi mà không gây ảnh hưởng nghiêm trọng đến bên còn lại.

Hai nhóm thường:

- Cùng lập kế hoạch cho những thay đổi có liên quan.
- Thống nhất mục tiêu, ưu tiên và lịch phát hành.
- Phối hợp kiểm thử tích hợp và xử lý sự cố.
- Thảo luận sớm khi một bên muốn thay đổi mô hình hoặc hợp đồng.

Ví dụ: Pricing Context và Promotion Context cùng chịu trách nhiệm cho khả năng tính giá cuối cùng của một chiến dịch phức tạp. Một thay đổi về quy tắc cộng dồn ưu đãi có thể ảnh hưởng cả hai bên, vì vậy hai đội cần phối hợp thiết kế và phát hành.

Partnership phù hợp khi sự phụ thuộc hai chiều là thực chất và cả hai đội có khả năng cộng tác. Nếu chỉ gọi tên quan hệ là Partnership mà không có cơ chế phối hợp, lịch chung và trách nhiệm rõ ràng, hai đội vẫn có thể rơi vào tình trạng chờ đợi lẫn nhau.

### 3.2. Shared Kernel – Nhân dùng chung

Shared Kernel là phần nhỏ của mô hình hoặc mã nguồn được hai Bounded Context cùng chia sẻ. Vì một thay đổi trong phần chung có thể ảnh hưởng cả hai context, các nhóm phải thống nhất quyền sở hữu và phối hợp thay đổi.

Shared Kernel có thể bao gồm:

- Một tập hợp khái niệm nghiệp vụ được hai bên hiểu giống nhau.
- Một số kiểu dữ liệu hoặc value object ổn định.
- Một phần mã nguồn được chia sẻ và có quy trình kiểm thử chung.
- Một tập hợp quy tắc hoặc schema được quản lý cùng nhau.

Ví dụ: Ordering Context và Billing Context thống nhất chia sẻ một thư viện nhỏ chứa kiểu biểu diễn Money với quy tắc tiền tệ, độ chính xác và phép tính cơ bản. Các khái niệm về đơn hàng và hóa đơn vẫn thuộc mô hình riêng của từng context.

Shared Kernel cần được giữ nhỏ và có kiểm soát:

- Chỉ chia sẻ phần thực sự có cùng ý nghĩa nghiệp vụ.
- Có người chịu trách nhiệm và quy trình phê duyệt thay đổi.
- Kiểm thử tương thích cho tất cả context sử dụng.
- Tránh đưa toàn bộ mô hình của một context vào thư viện chung.

Nếu hai nhóm không thể phối hợp lịch thay đổi, Shared Kernel dễ trở thành nguồn gây phụ thuộc và làm giảm khả năng phát triển độc lập.

### 3.3. Customer-Supplier – Khách hàng và nhà cung cấp

Trong quan hệ Customer-Supplier, upstream đóng vai trò nhà cung cấp, downstream là khách hàng sử dụng năng lực của upstream. Downstream có thể đưa ra nhu cầu và ảnh hưởng đến ưu tiên của upstream thông qua một quan hệ làm việc rõ ràng.

Ví dụ: Reporting Context cần dữ liệu đơn hàng từ Ordering Context. Reporting là khách hàng của dữ liệu; Ordering là nhà cung cấp. Hai đội thống nhất những trường dữ liệu, sự kiện, độ trễ và lịch thay đổi mà Reporting cần.

Quan hệ này thường có:

- Danh sách nhu cầu từ downstream.
- Thỏa thuận về ưu tiên, thời hạn và chất lượng dịch vụ.
- Hợp đồng dữ liệu hoặc API.
- Cơ chế thông báo và quản lý phiên bản.
- Quy trình phản hồi khi upstream không đáp ứng cam kết.

Customer-Supplier phù hợp khi hai bên có thể thương lượng và upstream sẵn sàng tính đến nhu cầu downstream. Nếu upstream chỉ ưu tiên mục tiêu của mình và không đáp ứng nhu cầu của downstream, quan hệ có thể chuyển thành Conformist.

### 3.4. Conformist – Tuân theo mô hình upstream

Conformist xảy ra khi downstream chấp nhận mô hình và cách biểu diễn của upstream, không yêu cầu upstream thay đổi để phù hợp với nhu cầu riêng của mình. Downstream xây dựng mô hình dựa trên dữ liệu hoặc hợp đồng đã nhận.

Ví dụ: một ứng dụng nội bộ tiêu thụ API của nhà cung cấp vận chuyển. API chỉ cung cấp một mô hình trạng thái giao hàng cố định; ứng dụng nội bộ sử dụng trực tiếp các trạng thái đó vì không có khả năng thương lượng với nhà cung cấp.

Ưu điểm:

- Tích hợp đơn giản hơn vì ít phải xây lớp chuyển đổi.
- Giảm chi phí thiết kế và duy trì một mô hình trung gian.
- Có thể phù hợp với bài toán generic hoặc năng lực bên ngoài không tạo khác biệt.

Rủi ro:

- Mô hình của upstream có thể không phù hợp với ngôn ngữ nội bộ.
- Thay đổi từ upstream có thể lan trực tiếp vào downstream.
- Downstream có thể bị ràng buộc vào cách phân loại, trạng thái hoặc giả định của nhà cung cấp.

Conformist là một lựa chọn có chủ đích khi chi phí chuyển đổi lớn hơn lợi ích bảo vệ mô hình. Nếu mô hình upstream làm méo mó khái niệm cốt lõi của downstream, nên cân nhắc Anti-Corruption Layer.

### 3.5. Anti-Corruption Layer (ACL) – Lớp chống xâm nhập mô hình

Anti-Corruption Layer là lớp chuyển đổi và bảo vệ mô hình nội bộ của downstream khỏi mô hình bên ngoài. Nó dịch thuật ngữ, cấu trúc dữ liệu và ý nghĩa nghiệp vụ từ upstream sang cách biểu diễn phù hợp với downstream.

Ví dụ: nhà cung cấp thanh toán trả về các trạng thái authorized, captured, voided, refunded cùng các mã lỗi riêng. Payment Integration Context chuyển đổi chúng thành các khái niệm nội bộ như PaymentAuthorized, PaymentSettled, PaymentCancelled hoặc RefundCompleted, theo đúng ý nghĩa mà miền thanh toán nội bộ cần.

ACL có thể gồm:

- Adapter hoặc gateway để giao tiếp với hệ thống bên ngoài.
- Translator để chuyển đổi schema, enum, mã lỗi và đơn vị đo.
- Mapper để chuyển đổi giữa mô hình ngoài và mô hình nội bộ.
- Quy tắc xử lý khác biệt ngữ nghĩa, thiếu dữ liệu và lỗi giao tiếp.
- Kiểm thử hợp đồng để phát hiện thay đổi từ upstream.

ACL không chỉ đổi tên trường JSON. Nó phải chuyển đổi ý nghĩa nghiệp vụ. Ví dụ, không nên ánh xạ trạng thái shipped của nhà vận chuyển thành Delivered nếu hàng mới rời kho.

ACL đặc biệt hữu ích khi:

- Upstream nằm ngoài quyền kiểm soát của tổ chức.
- Mô hình upstream không phù hợp với ngôn ngữ nội bộ.
- Mô hình nội bộ là core domain và cần được bảo vệ.
- Nhà cung cấp có thể thay đổi schema, trạng thái hoặc cách diễn giải.

ACL có chi phí phát triển và vận hành. Với một tích hợp đơn giản, ổn định và ít ảnh hưởng đến mô hình miền, lớp chuyển đổi lớn có thể không đáng giá. Hãy xây ACL ở nơi nó bảo vệ được tính nhất quán quan trọng.

### 3.6. Open Host Service (OHS) – Dịch vụ công khai

Open Host Service là một giao diện hoặc tập hợp dịch vụ được upstream thiết kế để nhiều context khác nhau có thể tích hợp theo cách nhất quán. Thay vì tạo một giao diện riêng cho từng khách hàng, upstream công bố một dịch vụ có chủ đích và được quản lý.

Ví dụ: Catalog Context cung cấp API truy vấn sản phẩm, API tra cứu danh mục và luồng sự kiện sản phẩm thay đổi cho Search, Recommendation và Ordering.

Một OHS tốt cần:

- Có hợp đồng rõ ràng, ổn định và được tài liệu hóa.
- Xác định quyền truy cập, giới hạn tải và cam kết vận hành.
- Có chính sách tương thích và quản lý phiên bản.
- Cung cấp dữ liệu đúng với ngôn ngữ công khai mà upstream cam kết.
- Hỗ trợ nhiều downstream mà không để mỗi bên phụ thuộc vào chi tiết nội bộ.

OHS là cách upstream mở cửa cho các context khác sử dụng năng lực của mình. Nó không bắt buộc phải là REST API; có thể là API đồng bộ, sự kiện, giao thức hoặc cơ chế truy cập khác phù hợp với nghiệp vụ.

### 3.7. Published Language (PL) – Ngôn ngữ được công bố

Published Language là một ngôn ngữ trao đổi được công bố để các context độc lập có thể hiểu và sử dụng. Nó thường được thể hiện qua schema, message format, thuật ngữ và quy tắc diễn giải.

Ví dụ: Ordering Context công bố sự kiện OrderConfirmed với schema có phiên bản, mã đơn, thời điểm xác nhận, các dòng hàng và thông tin giá đã chốt. Fulfillment Context và Customer Notification Context có thể tiêu thụ sự kiện đó mà không cần biết cấu trúc nội bộ của Ordering.

Published Language giúp:

- Giảm phụ thuộc vào mô hình nội bộ của upstream.
- Cho phép nhiều downstream cùng hiểu một hợp đồng.
- Quản lý phiên bản và thay đổi schema có chủ đích.
- Tạo nền tảng cho kiểm thử hợp đồng và tích hợp bất đồng bộ.

Published Language cần có ngữ nghĩa rõ. Một schema hợp lệ về cú pháp vẫn có thể gây hiểu nhầm nếu status, amount hoặc effectiveAt không có định nghĩa nghiệp vụ nhất quán.

OHS và Published Language thường đi cùng nhau: OHS cung cấp dịch vụ công khai, còn PL định nghĩa ngôn ngữ dùng trong giao tiếp. Tuy vậy, chúng là hai ý tưởng khác nhau. OHS tập trung vào cách cung cấp dịch vụ; PL tập trung vào cách biểu diễn thông tin được trao đổi.

### 3.8. Separate Ways – Phát triển riêng

Separate Ways mô tả lựa chọn để hai context giải quyết nhu cầu của mình độc lập, không tích hợp trực tiếp. Điều này có thể hợp lý khi lợi ích tích hợp thấp hơn chi phí phối hợp và phụ thuộc.

Ví dụ: bộ phận nhân sự và hệ thống phân tích sản phẩm đều cần danh sách ngày nghỉ lễ, nhưng không có yêu cầu nghiệp vụ về một nguồn dữ liệu thời gian thực duy nhất. Mỗi bên có thể quản lý tập dữ liệu phù hợp với nhu cầu riêng, nếu sai khác không gây rủi ro đáng kể.

Separate Ways có thể giúp:

- Giảm phụ thuộc giữa các đội.
- Cho phép mỗi context lựa chọn mô hình và nhịp thay đổi riêng.
- Tránh tích hợp chỉ vì hai hệ thống có dữ liệu trông giống nhau.

Đổi lại, có thể xuất hiện dữ liệu trùng lặp, quy tắc lặp lại hoặc kết quả không đồng nhất. Cần đánh giá chi phí sai khác, nhu cầu đồng bộ và rủi ro nghiệp vụ trước khi chọn.

### 3.9. So sánh các pattern

| Pattern | Quan hệ chính | Cách xử lý mô hình | Khi nên cân nhắc |
|---|---|---|---|
| Partnership | Hai đội phối hợp chặt và cùng chịu trách nhiệm thành công | Thỏa thuận thay đổi và phối hợp thiết kế | Phụ thuộc hai chiều, mục tiêu liên kết |
| Shared Kernel | Hai context cùng sở hữu một phần nhỏ mô hình/mã | Chia sẻ có kiểm soát và kiểm thử chung | Có phần mô hình thật sự đồng nhất và hai đội cộng tác tốt |
| Customer-Supplier | Upstream cung cấp, downstream có tiếng nói về nhu cầu | Hợp đồng và ưu tiên được thương lượng | Upstream có thể đáp ứng nhu cầu khách hàng nội bộ |
| Conformist | Downstream chấp nhận mô hình upstream | Dùng trực tiếp mô hình được cung cấp | Không thể thương lượng và chi phí chuyển đổi không đáng kể |
| Anti-Corruption Layer | Downstream bảo vệ mô hình của mình | Dịch và chuyển đổi ngữ nghĩa | Mô hình upstream không phù hợp hoặc có nguy cơ làm biến dạng miền |
| Open Host Service | Upstream cung cấp giao diện dùng chung | Dịch vụ công khai và hợp đồng ổn định | Nhiều downstream cần truy cập cùng năng lực |
| Published Language | Các bên trao đổi qua ngôn ngữ/schema công bố | Schema hoặc thông điệp có ngữ nghĩa và phiên bản | Cần giao tiếp độc lập qua API hoặc sự kiện |
| Separate Ways | Hai context không tích hợp | Mỗi bên duy trì mô hình riêng | Giá trị tích hợp thấp hơn chi phí phụ thuộc |

Các pattern không loại trừ lẫn nhau. Ví dụ, một quan hệ Customer-Supplier có thể sử dụng OHS và PL ở phía cung cấp; downstream vẫn có thể dùng ACL để chuyển PL sang mô hình nội bộ. Một Shared Kernel có thể tồn tại giữa hai nhóm Partnership. Hãy ghi rõ pattern mô tả khía cạnh nào của quan hệ.

## 4. Cách đọc và vẽ Context Map

Không có một ký hiệu hình học bắt buộc duy nhất cho mọi Context Map. Điều quan trọng là bản đồ có legend, hướng phụ thuộc rõ ràng và tên pattern dễ hiểu. Nhóm cần thống nhất cách đọc mũi tên trước khi dùng bản đồ trong thảo luận.

Một quy ước đơn giản:

- Mỗi hộp là một Bounded Context.
- Mũi tên từ upstream đến downstream biểu diễn hướng phụ thuộc vào năng lực hoặc mô hình được cung cấp.
- Nhãn trên mũi tên ghi pattern quan hệ.
- Ghi tên đội sở hữu context nếu thông tin này có ích.
- Có thể thêm ghi chú về API, event, schema hoặc cơ chế tích hợp, nhưng không để chi tiết kỹ thuật lấn át ý nghĩa nghiệp vụ.

Ví dụ sơ đồ:

~~~mermaid
flowchart LR
    Catalog["Catalog Context<br/>Đội Catalog"]
    Search["Search Context<br/>Đội Discovery"]
    Ordering["Ordering Context<br/>Đội Commerce"]
    Pricing["Pricing Context<br/>Đội Pricing"]
    Inventory["Inventory Context<br/>Đội Supply"]
    Fulfillment["Fulfillment Context<br/>Đội Logistics"]
    Payment["Payment Provider<br/>Bên ngoài"]

    Catalog -->|"OHS + Published Language"| Search
    Pricing -->|"Customer-Supplier"| Ordering
    Inventory -->|"Published Language / Events"| Ordering
    Ordering -->|"Published Language: OrderConfirmed"| Fulfillment
    Payment -->|"Conformist hoặc ACL ở phía tích hợp"| Ordering
~~~

Sơ đồ này minh họa một số quan hệ có thể có. Nó không khẳng định mọi thương mại điện tử đều có cấu trúc như vậy. Khi áp dụng vào hệ thống thực, cần xác nhận chủ sở hữu, hợp đồng, chiều phụ thuộc và pattern qua trao đổi với các đội.

### 4.1. Phân biệt chiều phụ thuộc và chiều thông điệp

Trong sơ đồ trên, Ordering tiêu thụ giá từ Pricing, nên Pricing là upstream đối với Ordering. Nhưng Ordering vẫn có thể gửi thông tin đơn hàng hoặc phản hồi về Pricing. Việc có thông điệp đi ngược chiều không tự động đảo vai trò upstream/downstream.

Nếu một context vừa cung cấp vừa tiêu thụ các năng lực quan trọng của context khác, hãy vẽ các quan hệ riêng và giải thích rõ mỗi quan hệ. Đừng cố nén tất cả vào một mũi tên không có nghĩa rõ ràng.

### 4.2. Ghi chú quan hệ trên bản đồ

Với mỗi đường nối, có thể ghi:

| Thông tin | Ví dụ |
|---|---|
| Upstream | Pricing Context |
| Downstream | Ordering Context |
| Năng lực trao đổi | Tính giá cho giỏ hàng |
| Pattern | Customer-Supplier |
| Giao diện | API Quote |
| Ngôn ngữ trao đổi | Price Quote schema |
| Quyền thay đổi | Pricing sở hữu quy tắc giá; hai đội thống nhất thay đổi hợp đồng |
| Chất lượng dịch vụ | Thời gian phản hồi và tính sẵn sàng đã thỏa thuận |
| Rủi ro | Thay đổi quy tắc làm đơn hàng tính lại giá |
| Cơ chế kiểm soát | Contract test, versioning và thông báo thay đổi |

Không phải Context Map nào cũng cần mọi cột. Hãy chọn thông tin đủ để nhóm hiểu quan hệ và quyết định việc cần làm tiếp theo.

## 5. Quy trình xây dựng Context Map

### Bước 1: Xác định mục tiêu và phạm vi bản đồ

Làm rõ bản đồ phục vụ khám phá domain, thiết kế tích hợp, tái cấu trúc hay cải thiện phối hợp giữa các đội. Xác định sản phẩm, hệ thống, nhóm nghiệp vụ và khoảng thời gian nằm trong phạm vi.

Một bản đồ toàn doanh nghiệp có thể hữu ích cho chiến lược nhưng quá lớn để thảo luận chi tiết. Có thể tạo bản đồ tổng quan trước, sau đó tạo bản đồ con cho một hành trình hoặc khu vực nghiệp vụ.

### Bước 2: Liệt kê các Bounded Context

Với mỗi context, ghi tên, mục đích, ngôn ngữ quan trọng, trách nhiệm, chủ sở hữu và ranh giới. Nếu một nhóm đang dùng nhiều nghĩa cho cùng thuật ngữ, cần làm rõ trước khi kết luận context đã ổn định.

Không vội gộp hai context chỉ vì chúng dùng chung một cơ sở dữ liệu hoặc cùng một đối tượng dữ liệu. Cũng không vội tách context chỉ vì hai nhóm dùng công nghệ khác nhau.

### Bước 3: Tìm các phụ thuộc thực tế

Hỏi từng đội:

- Context nào cần dữ liệu hoặc quyết định từ context khác để hoàn thành trách nhiệm?
- Dữ liệu được lấy theo yêu cầu, qua sự kiện, theo lịch hay thủ công?
- Ai sở hữu định nghĩa và quy tắc của dữ liệu?
- Nếu bên cung cấp thay đổi, bên tiêu thụ bị ảnh hưởng thế nào?
- Có phụ thuộc ngầm qua bảng dữ liệu, báo cáo, tệp hoặc thao tác của nhân viên không?

Quan sát luồng nghiệp vụ và các trường hợp sự cố để phát hiện phụ thuộc mà sơ đồ hệ thống có thể không thể hiện.

### Bước 4: Xác định upstream, downstream và quyền ảnh hưởng

Với mỗi cặp context, xác định bên cung cấp năng lực hoặc mô hình, bên tiêu thụ và ai có quyền quyết định thay đổi. Nếu hai bên cùng phụ thuộc và cần phối hợp, hãy ghi nhận sự cộng tác hai chiều.

Đừng chỉ dựa vào hướng gọi API. Một context có thể gọi API của context khác nhưng thực tế lại là bên định hình hợp đồng hoặc sở hữu chính sách. Hãy hỏi ai kiểm soát mô hình và ai phải thích nghi khi có thay đổi.

### Bước 5: Chọn pattern mô tả quan hệ

Thảo luận cách hai bên làm việc:

- Có phối hợp như Partnership không?
- Có chia sẻ một phần mô hình như Shared Kernel không?
- Downstream có thể thương lượng nhu cầu như Customer-Supplier không?
- Downstream có buộc phải chấp nhận mô hình như Conformist không?
- Có cần ACL để bảo vệ mô hình nội bộ không?
- Upstream có nên công bố OHS và PL không?
- Có thể chọn Separate Ways vì tích hợp không đáng giá không?

Một quan hệ có thể có pattern cộng tác và pattern tích hợp khác nhau. Ví dụ, hai đội có quan hệ Customer-Supplier về ưu tiên nhưng trao đổi dữ liệu bằng Published Language.

### Bước 6: Ghi nhận cơ chế tích hợp và hợp đồng

Với quan hệ cần tích hợp, ghi rõ giao diện, schema, sự kiện, tần suất, độ trễ, quyền truy cập, cách xử lý lỗi, tương thích ngược và quy trình thay đổi. Xác định dữ liệu nào là nguồn sự thật và context nào chịu trách nhiệm xác nhận ý nghĩa của dữ liệu.

### Bước 7: Đánh dấu rủi ro và điểm nghẽn

Tìm các quan hệ có:

- Phụ thuộc vào một nhóm upstream không có cam kết phản hồi.
- Nhiều downstream cùng bị ảnh hưởng bởi thay đổi không báo trước.
- Mô hình dùng chung quá lớn hoặc khó thay đổi.
- Dữ liệu trao đổi thiếu ngữ nghĩa hoặc không có chủ sở hữu.
- Một context phải hiểu trực tiếp mô hình nội bộ của context khác.
- Tích hợp thủ công hoặc sao chép dữ liệu tạo sai khác khó kiểm soát.

### Bước 8: Xác nhận với các đội và duy trì bản đồ

Đưa bản đồ cho chủ sở hữu context và các đội liên quan kiểm tra. Xác nhận tên, trách nhiệm, pattern, chiều phụ thuộc và hợp đồng. Ghi ngày cập nhật, người xác nhận và những điểm còn giả định.

Context Map cần được cập nhật khi xuất hiện context mới, thay đổi quyền sở hữu, thay đổi mô hình, thay đổi nhà cung cấp hoặc khi một phụ thuộc được loại bỏ. Nếu bản đồ không còn phản ánh thực tế, nó sẽ dẫn đến quyết định kiến trúc sai.

## 6. Ví dụ phân tích một quan hệ cụ thể

Giả sử Ordering Context cần biết tồn kho khả dụng trước khi xác nhận đơn hàng.

### 6.1. Mô tả nhu cầu nghiệp vụ

Ordering cần biết liệu sản phẩm có thể được bán tại thời điểm khách đặt hàng. Inventory sở hữu thông tin số lượng, giữ chỗ, điều chỉnh và trạng thái hàng. Ordering không nên tự tính lại tồn kho từ các bảng nội bộ của Inventory.

### 6.2. Xác định vai trò

- Inventory là upstream vì nó sở hữu năng lực và quy tắc tồn kho.
- Ordering là downstream vì nó sử dụng kết quả để quyết định tiếp nhận đơn.
- Hai bên cần thống nhất ý nghĩa của available, reserved và out of stock.

### 6.3. Chọn pattern

Nếu đội Ordering có thể thương lượng nhu cầu và Inventory cam kết cung cấp một hợp đồng phù hợp, quan hệ có thể là Customer-Supplier. Inventory có thể cung cấp một API kiểm tra và giữ chỗ tồn kho, hoặc công bố sự kiện qua Published Language.

Nếu Inventory là hệ thống nhà cung cấp bên ngoài với mô hình khó thay đổi, Ordering có thể đặt một ACL ở ranh giới tích hợp để chuyển đổi trạng thái và thuật ngữ sang mô hình nội bộ.

Nếu hai đội thường xuyên phải cùng thiết kế quy tắc giữ chỗ và xác nhận đơn, họ có thể cần một cơ chế Partnership cho những thay đổi liên quan. Pattern cộng tác này không nhất thiết thay thế hợp đồng OHS/PL dùng để tích hợp.

### 6.4. Làm rõ hợp đồng

Một hợp đồng tồn kho cần làm rõ:

- availableQuantity là số lượng có thể bán hay số lượng vật lý trong kho?
- Khi kiểm tra tồn kho, số lượng có được giữ chỗ ngay hay chỉ là kết quả tại một thời điểm?
- Thời hạn giữ chỗ là bao lâu?
- Điều gì xảy ra nếu hai khách hàng cùng đặt sản phẩm cuối cùng?
- Khi yêu cầu giữ chỗ thất bại, Ordering nhận mã lỗi và thông tin nào?
- Inventory có phát sự kiện khi giữ chỗ hết hạn hoặc bị hủy không?
- Ordering xử lý ra sao nếu phản hồi đến trễ hoặc bị gửi lặp?

Những câu hỏi này cho thấy hợp đồng tích hợp phải mô tả ngữ nghĩa nghiệp vụ và vòng đời, không chỉ liệt kê trường dữ liệu.

## 7. Dùng Context Map để nhận diện và cải thiện phụ thuộc

Context Map không chỉ ghi lại hiện trạng. Nó giúp đội nhìn thấy nơi cần thay đổi cách cộng tác hoặc ranh giới mô hình.

### Phụ thuộc quá chặt

Nếu downstream truy cập trực tiếp database hoặc dùng các lớp nội bộ của upstream, thay đổi nội bộ có thể gây lỗi dây chuyền. Hãy cân nhắc một hợp đồng công khai, Published Language hoặc ACL tùy mức độ cần bảo vệ.

### Upstream trở thành nút thắt

Nếu nhiều downstream phải chờ một đội upstream ưu tiên thay đổi, thời gian giao hàng của cả hệ thống có thể bị kéo dài. Hãy làm rõ nhu cầu, cam kết và quyền ưu tiên theo Customer-Supplier; nếu hai bên cùng phụ thuộc sâu, cân nhắc Partnership.

### Shared Kernel mở rộng quá mức

Khi phần dùng chung chứa ngày càng nhiều khái niệm, mọi thay đổi đều cần nhiều đội phối hợp. Hãy xem lại khái niệm nào thật sự có cùng ý nghĩa, khái niệm nào nên thuộc mô hình riêng và phần nào nên được trao đổi qua hợp đồng.

### Mô hình bên ngoài làm biến dạng miền nội bộ

Nếu downstream phải dùng trực tiếp mã trạng thái, thuật ngữ hoặc cấu trúc của nhà cung cấp, mô hình nội bộ dễ phản ánh giới hạn của bên ngoài. ACL có thể tạo lớp chuyển đổi có chủ đích.

### Tích hợp không tạo đủ giá trị

Hai context có thể cùng giữ một số dữ liệu nhưng không cần đồng bộ tức thời. Nếu chi phí tích hợp, vận hành và phối hợp lớn hơn lợi ích, Separate Ways có thể là lựa chọn hợp lý.

### Thiếu Published Language

Nếu mỗi downstream tự diễn giải một schema không rõ nghĩa, cùng một trường có thể mang nhiều cách hiểu. Hãy công bố thuật ngữ, schema, quy tắc phiên bản và ví dụ hợp lệ.

## 8. Tác động đến chiến lược đội ngũ và thiết kế hệ thống

Các quan hệ trong Context Map phản ánh cách tổ chức cộng tác. Đây là một phần quan trọng của strategic design.

- **Partnership** đòi hỏi mục tiêu và kế hoạch phối hợp giữa các đội.
- **Shared Kernel** đòi hỏi cơ chế sở hữu và kiểm thử chung.
- **Customer-Supplier** đòi hỏi quản lý nhu cầu, ưu tiên và cam kết dịch vụ.
- **Conformist** đòi hỏi downstream chấp nhận mức độ phụ thuộc vào mô hình upstream.
- **ACL** đòi hỏi downstream đầu tư vào chuyển đổi và bảo vệ mô hình của mình.
- **OHS và PL** đòi hỏi upstream quản lý giao diện công khai và ngôn ngữ trao đổi.
- **Separate Ways** đòi hỏi tổ chức chấp nhận một mức trùng lặp hoặc sai khác có kiểm soát.

Từ đó, đội có thể xem xét:

- Ai sở hữu từng Bounded Context và hợp đồng tích hợp?
- Đội nào có quyền quyết định thay đổi mô hình?
- Những thay đổi nào cần phối hợp trước khi phát hành?
- Context nào cần triển khai độc lập?
- Context nào cần có chuyên gia miền tham gia thường xuyên?
- Đội nào cần đầu tư vào kiểm thử hợp đồng, quan sát hệ thống và xử lý lỗi tích hợp?

Context Map cũng có thể giúp phát hiện rủi ro tổ chức: một đội phải hỗ trợ quá nhiều downstream, nhiều nhóm cùng sửa một mô hình, hoặc một năng lực quan trọng không có chủ sở hữu rõ ràng.

## 9. Các lỗi thường gặp khi lập Context Map

**Chỉ vẽ các hộp và đường nối.** Bản đồ không ghi rõ ý nghĩa, chiều phụ thuộc và pattern sẽ khó dùng để ra quyết định. Hãy ghi trách nhiệm và lý do của từng quan hệ.

**Nhầm upstream với hệ thống gửi request.** Hướng gọi API không luôn phản ánh quyền định hình mô hình. Xác định ai sở hữu năng lực và ai phải thích nghi khi hợp đồng thay đổi.

**Xem một context là upstream trong mọi quan hệ.** Vai trò upstream/downstream phụ thuộc vào cặp context và năng lực đang xét. Một context có thể có nhiều vai trò.

**Dùng một mô hình chung cho mọi context.** Từ ngữ giống nhau không chứng minh ý nghĩa giống nhau. Chia sẻ chỉ khi khái niệm thực sự có cùng ngữ nghĩa và lợi ích lớn hơn chi phí phối hợp.

**Tạo ACL cho mọi tích hợp.** ACL có giá trị khi cần bảo vệ mô hình hoặc chuyển đổi ngữ nghĩa. Dùng nó cho mọi trường hợp đơn giản sẽ làm tăng mã và chi phí vận hành.

**Coi OHS là một REST API.** OHS là dịch vụ công khai được thiết kế cho nhiều khách hàng. Cách triển khai có thể là API, sự kiện hoặc cơ chế khác.

**Coi Published Language chỉ là schema.** Schema cần ngữ nghĩa, quy tắc tương thích và cách diễn giải. Nếu không, các bên vẫn có thể hiểu sai dù cấu trúc hợp lệ.

**Nhầm Shared Kernel với thư viện tiện ích dùng chung.** Shared Kernel là phần mô hình được các context cùng chia sẻ, vì vậy cần quản lý thay đổi và ý nghĩa nghiệp vụ. Một thư viện kỹ thuật chung không tự động là Shared Kernel.

**Tích hợp mọi thứ vì có thể.** Mỗi tích hợp tạo thêm hợp đồng, vận hành và phụ thuộc. Hãy chứng minh giá trị trước khi nối hai context.

**Không cập nhật bản đồ.** Context Map lỗi thời có thể làm người mới hiểu sai quyền sở hữu và đường phụ thuộc. Cần xác định người cập nhật và sự kiện kích hoạt việc xem lại.

## 10. Mẫu ghi nhận Context Map

Có thể bắt đầu với một bảng đơn giản:

| Upstream | Downstream | Năng lực hoặc thông tin | Pattern | Cơ chế trao đổi | Rủi ro / việc cần làm |
|---|---|---|---|---|---|
| Catalog | Search | Thông tin sản phẩm và danh mục | OHS + Published Language | API và sự kiện | Quản lý phiên bản schema |
| Pricing | Ordering | Báo giá và điều kiện áp dụng | Customer-Supplier | API Quote | Xác định thời hạn hiệu lực của báo giá |
| Inventory | Ordering | Khả năng giữ chỗ hàng | Customer-Supplier | API và sự kiện | Xử lý giữ chỗ đồng thời và hết hạn |
| Ordering | Fulfillment | Đơn hàng đã xác nhận | Published Language | Domain Event | Quản lý sự kiện lặp và thứ tự |
| Payment Provider | Payment Integration | Kết quả giao dịch thanh toán | Conformist + ACL | API bên ngoài | Chuyển đổi trạng thái và mã lỗi |

Bảng này là ví dụ. Trong hệ thống thực, cần xác nhận từng quan hệ với người sở hữu context và ghi rõ nguồn của thông tin.

Mẫu tối thiểu cho một context:

~~~text
BOUNDED CONTEXT
- Tên:
- Mục đích nghiệp vụ:
- Trách nhiệm:
- Thuật ngữ quan trọng:
- Đội / người sở hữu:
- Phạm vi không bao gồm:

QUAN HỆ VỚI CONTEXT KHÁC
- Upstream:
- Downstream:
- Năng lực hoặc dữ liệu trao đổi:
- Pattern:
- Hợp đồng / ngôn ngữ trao đổi:
- Cách chuyển đổi mô hình:
- Quyền thay đổi và cơ chế phối hợp:
- Rủi ro và vấn đề chưa giải quyết:

QUẢN LÝ BẢN ĐỒ
- Người xác nhận:
- Ngày cập nhật:
- Sự kiện cần xem xét lại:
~~~

## 11. Tiêu chí tự kiểm tra

Trước khi dùng Context Map để định hướng thiết kế hoặc tổ chức đội ngũ, hãy tự hỏi:

- Mỗi hộp có thực sự đại diện cho một Bounded Context với mô hình và ngôn ngữ có ý nghĩa nhất quán không?
- Trách nhiệm và chủ sở hữu của từng context đã rõ chưa?
- Mỗi quan hệ có giải thích được năng lực hoặc mô hình mà downstream phụ thuộc không?
- Vai trò upstream và downstream đã được xác định theo từng quan hệ chưa?
- Đã phân biệt chiều phụ thuộc với chiều truyền dữ liệu hoặc request chưa?
- Pattern được chọn có phản ánh cách các đội thực sự cộng tác và quyền ảnh hưởng không?
- Hợp đồng trao đổi có ngữ nghĩa, phiên bản và quy tắc tương thích không?
- Mô hình nội bộ có cần được bảo vệ bằng ACL không?
- Việc chia sẻ Shared Kernel có thực sự đáng với chi phí phối hợp không?
- Những phụ thuộc ngầm, điểm nghẽn và tích hợp thủ công đã được nhận diện chưa?
- Bản đồ có legend, người xác nhận và ngày cập nhật không?
- Đã xác định ai sẽ cập nhật bản đồ khi ranh giới hoặc quan hệ thay đổi chưa?

Context Map tốt giúp mọi người hiểu các mô hình miền liên hệ với nhau như thế nào và ai chịu trách nhiệm cho từng mối quan hệ. Khi các phụ thuộc được nhìn thấy rõ, đội có thể chọn cách cộng tác phù hợp, quản lý hợp đồng có chủ đích và bảo vệ ngôn ngữ riêng của mỗi Bounded Context trong toàn bộ hệ thống Domain-Driven Design.
