# Phân biệt từ đồng nghĩa, từ đa nghĩa và khái niệm có tên gần giống nhau

Trong Domain-Driven Design (DDD), ngôn ngữ chung (Ubiquitous Language) giúp chuyên gia nghiệp vụ và nhóm phát triển trao đổi về cùng một mô hình bằng những thuật ngữ có ý nghĩa rõ ràng. Tuy nhiên, ngôn ngữ trong tổ chức thường hình thành tự nhiên qua nhiều năm. Một khái niệm có thể được gọi bằng nhiều tên, một từ có thể mang nhiều nghĩa, và hai khái niệm khác nhau có thể có tên gần giống nhau. Nếu nhóm không nhận diện được những tình huống này, các cuộc trao đổi dễ dẫn đến hiểu nhầm, còn mô hình và mã nguồn có thể biểu diễn sai nghiệp vụ.

Vì vậy, xây dựng ngôn ngữ chung không chỉ là lập một bảng thuật ngữ. Nhóm cần tìm hiểu từ ngữ được sử dụng trong tình huống nào, ai sử dụng, nó chỉ đến khái niệm nào, quy tắc nào gắn với khái niệm đó và phạm vi nào làm cho ý nghĩa trở nên đúng. Sau đó, nhóm cùng chuyên gia nghiệp vụ quyết định thuật ngữ nào nên được dùng trong từng bounded context, thuật ngữ nào chỉ là tên gọi cũ hoặc bí danh, và những khái niệm nào cần được phân biệt rõ.

Bài học này tập trung vào ba hiện tượng thường gặp: **từ đồng nghĩa**, **từ đa nghĩa** và **các khái niệm có tên gần giống nhau**. Phân biệt đúng ba hiện tượng giúp nhóm đặt tên chính xác cho mô hình, giảm mơ hồ trong giao tiếp và giữ cho ngôn ngữ trong mã nguồn phù hợp với nghiệp vụ.

## 1. Vì sao cần phân biệt thuật ngữ?

Một thuật ngữ nghiệp vụ không chỉ là nhãn hiển thị trên giao diện. Nó thường đại diện cho một khái niệm, một trách nhiệm, một trạng thái hoặc một quy tắc. Khi tên gọi không rõ ràng, nhóm có thể đưa ra quyết định sai ngay cả khi mọi người đều nghĩ rằng mình đang nói về cùng một điều.

Hãy xem yêu cầu: “Cập nhật tài khoản khách hàng”. Cụm từ này có thể chỉ việc thay đổi thông tin đăng nhập, cập nhật hồ sơ khách hàng, điều chỉnh hạn mức tín dụng hoặc sửa tài khoản công nợ. Nếu nhóm bắt đầu thiết kế một đối tượng `CustomerAccount` mà chưa làm rõ ý nghĩa, mô hình có thể gộp những trách nhiệm khác nhau vào cùng một nơi.

Những nhầm lẫn về thuật ngữ thường dẫn đến các vấn đề sau:

- **Sai phạm vi mô hình:** một khái niệm bị đặt vào sai bounded context hoặc bị gộp với khái niệm khác.
- **Sai quy tắc nghiệp vụ:** nhóm áp dụng điều kiện của một nghĩa cho một nghĩa khác.
- **Sai danh tính và vòng đời:** hai đối tượng được xem là một dù chúng được tạo, thay đổi hoặc kết thúc theo các quy tắc khác nhau.
- **Mã nguồn khó hiểu:** tên lớp, phương thức và sự kiện không cho biết rõ hành vi mà chúng đại diện.
- **Tích hợp dễ lỗi:** hai context trao đổi cùng một từ nhưng mỗi bên diễn giải payload theo một mô hình khác nhau.
- **Kiểm thử thiếu chính xác:** ví dụ và điều kiện kiểm thử phản ánh cách hiểu của người viết thay vì chính sách đã được xác nhận.

Ngôn ngữ chung giúp giảm các rủi ro đó bằng cách làm rõ ý nghĩa của thuật ngữ trong phạm vi sử dụng cụ thể. Mục tiêu không phải là buộc toàn tổ chức chỉ dùng một từ cho mọi tình huống, mà là bảo đảm những người cùng làm việc trong một mô hình hiểu từ ngữ theo cùng một cách.

## 2. Từ đồng nghĩa: nhiều cách gọi cho cùng một khái niệm

**Từ đồng nghĩa** là những từ hoặc cụm từ có ý nghĩa giống nhau hoặc gần giống nhau. Trong môi trường nghiệp vụ, một khái niệm có thể được gọi bằng nhiều tên do thói quen của từng phòng ban, lịch sử hệ thống, cách viết trên biểu mẫu hoặc khác biệt vùng miền.

Ví dụ, một nhóm có thể dùng “khách mua”, nhóm khác dùng “người mua”, trong khi cả hai đều muốn nói đến cùng một vai trò trong cùng quy trình. Một hệ thống cũ có thể gọi một đối tượng là “phiếu đặt hàng”, còn nhân viên hiện tại quen gọi là “đơn hàng”. Những cách gọi này có thể là bí danh của cùng một khái niệm, nhưng nhóm cần xác minh trước khi hợp nhất.

### 2.1. Khi nào hai từ thực sự là đồng nghĩa?

Không nên kết luận hai từ là đồng nghĩa chỉ vì chúng thường xuất hiện trong cùng một câu hoặc được dùng thay thế trong một vài cuộc trò chuyện. Hãy kiểm tra xem chúng có cùng chỉ đến một khái niệm trong cùng bounded context hay không.

Một số câu hỏi giúp xác minh:

1. Hai tên có cùng chỉ đến một đối tượng hoặc vai trò trong cùng tình huống nghiệp vụ không?
2. Khi thay tên này bằng tên kia trong các quy tắc đã thống nhất, kết quả có thay đổi không?
3. Hai tên có cùng danh tính, thuộc tính quan trọng, vòng đời và trách nhiệm không?
4. Người sử dụng hai tên có kỳ vọng hệ thống thực hiện cùng một hành vi không?
5. Sự khác biệt chỉ nằm ở thói quen gọi tên, cách viết hoặc lịch sử, hay phản ánh một khác biệt nghiệp vụ thật?

Nếu các câu trả lời cho thấy hai tên chỉ đến cùng một khái niệm và có thể thay thế trong phạm vi đó mà không làm thay đổi ý nghĩa, nhóm có thể chọn một tên chuẩn và ghi các tên còn lại là bí danh.

### 2.2. Chọn một thuật ngữ chuẩn

Trong một bounded context, nhóm nên chọn một thuật ngữ chính để dùng nhất quán trong trao đổi, tài liệu, mô hình và mã nguồn. Thuật ngữ chuẩn nên:

- Được chuyên gia nghiệp vụ hiểu và chấp nhận.
- Diễn đạt đúng trách nhiệm và ý nghĩa của khái niệm.
- Phù hợp với cách người dùng thực sự nói về công việc.
- Phân biệt được với các khái niệm lân cận.
- Có thể dùng tự nhiên khi đặt tên cho hành vi, trạng thái và sự kiện liên quan.

Các tên cũ hoặc cách gọi khác vẫn có thể được ghi trong từ điển thuật ngữ để hỗ trợ tìm kiếm tài liệu, đọc dữ liệu cũ hoặc trao đổi với hệ thống bên ngoài. Tuy nhiên, nhóm cần chỉ rõ đó là bí danh, tên lịch sử hay thuật ngữ chỉ dùng trong một context khác.

Ví dụ:

| Cách gọi được ghi nhận | Quyết định trong context bán hàng | Lý do |
| --- | --- | --- |
| Đơn hàng | Thuật ngữ chuẩn | Tên được thống nhất cho cam kết mua hàng của khách |
| Phiếu đặt hàng | Bí danh cũ, chỉ dùng khi đọc biểu mẫu/hệ thống cũ | Trong quy trình hiện tại, nó chỉ cùng khái niệm với Đơn hàng |
| Yêu cầu mua hàng | Thuật ngữ riêng nếu nói về đề nghị mua nội bộ | Người tạo, quy trình phê duyệt và vòng đời có thể khác Đơn hàng |

Bảng này là ví dụ minh họa. Một tổ chức có thể dùng các từ trên với ý nghĩa khác; quyết định phải dựa trên cách nghiệp vụ thực sự vận hành.

### 2.3. Cẩn thận với những từ chỉ gần đồng nghĩa

Hai từ có thể gần nghĩa nhưng không thể thay thế trong mọi trường hợp. Chẳng hạn, “hủy đơn hàng” và “trả hàng” đều có thể dẫn đến việc khách không giữ hàng đã mua, nhưng chúng thường chỉ hai quy trình khác nhau:

- **Hủy đơn hàng** thường xảy ra trước khi nghĩa vụ giao hàng hoàn tất; đơn có thể chưa được chuẩn bị, đang được xử lý hoặc đang chờ xác nhận.
- **Trả hàng** thường bắt đầu sau khi hàng đã được giao hoặc khách đã nhận hàng; nó có thể kéo theo kiểm tra tình trạng hàng, nhập kho lại và hoàn tiền.

Nếu dùng hai từ này như đồng nghĩa, hệ thống có thể cho phép một hành động không phù hợp với trạng thái hiện tại hoặc bỏ qua bước kiểm tra hàng trả về. Khi phát hiện khác biệt về điều kiện, trách nhiệm hoặc kết quả, nhóm nên xem chúng là hai khái niệm hoặc hai hành vi riêng.

Một phép thử hữu ích là **phép thử thay thế**: lấy một câu nghiệp vụ cụ thể và thay thuật ngữ A bằng thuật ngữ B. Nếu câu mới làm thay đổi quyền hạn, trạng thái, kết quả hoặc kỳ vọng của người dùng, hai từ không phải đồng nghĩa hoàn toàn trong ngữ cảnh đó.

## 3. Từ đa nghĩa: một từ mang nhiều ý nghĩa

**Từ đa nghĩa** là một từ hoặc cụm từ có nhiều ý nghĩa. Các nghĩa có thể có liên hệ với nhau hoặc phát triển theo cách sử dụng trong những lĩnh vực khác nhau. Trong tổ chức, một từ quen thuộc có thể được các phòng ban dùng để chỉ những khái niệm khác nhau.

Ví dụ, từ “tài khoản” có thể được dùng để nói về:

- Tài khoản đăng nhập dùng để xác thực người dùng.
- Tài khoản khách hàng dùng để quản lý quan hệ và thông tin giao dịch.
- Tài khoản công nợ dùng trong nghiệp vụ kế toán.

Các nghĩa này có thể liên quan đến cùng một khách hàng hoặc cùng một người dùng, nhưng mục đích, dữ liệu, quyền sở hữu và quy tắc của chúng khác nhau. Một lớp `Account` duy nhất rất dễ trở thành nơi chứa những trách nhiệm không liên quan.

### 3.1. Từ đa nghĩa trong một context và giữa nhiều context

Nếu một từ có nhiều nghĩa ngay trong cùng một bounded context, đó là dấu hiệu cần làm rõ hoặc thay đổi cách đặt tên. Một mô hình có ngôn ngữ rõ ràng không nên để cùng một thuật ngữ chỉ hai khái niệm khác nhau trong cùng phạm vi, trừ khi ngữ cảnh luôn làm rõ và việc dùng chung tên thực sự có chủ đích.

Giữa các bounded context, cùng một từ có thể có ý nghĩa khác nhau một cách hợp lệ. Ví dụ, “khách hàng” trong context CRM có thể là cá nhân hoặc tổ chức mà doanh nghiệp duy trì quan hệ; trong context thanh toán, “khách hàng” có thể là chủ thể chịu trách nhiệm thanh toán theo hợp đồng; trong context giao hàng, người nhận hàng có thể là một người khác.

DDD không yêu cầu các context phải ép những mô hình này thành một định nghĩa toàn cục. Mỗi bounded context có mô hình và ngôn ngữ riêng. Điều quan trọng là nhóm nhận biết được sự khác nhau và định nghĩa cách chuyển đổi khi thông tin đi qua ranh giới context.

### 3.2. Phân biệt đa nghĩa với nhiều thuộc tính của cùng một khái niệm

Đôi khi một từ có vẻ mang nhiều nghĩa nhưng thực ra đang mô tả các khía cạnh khác nhau của cùng một khái niệm. Ví dụ, “địa chỉ khách hàng” có thể được dùng để chỉ địa chỉ liên hệ, địa chỉ thanh toán hoặc địa chỉ giao hàng. Cần xác định đây là các vai trò địa chỉ riêng hay chỉ là một địa chỉ được tái sử dụng trong nhiều tình huống.

Nếu mỗi loại địa chỉ có quy tắc xác thực, thời điểm sử dụng, quyền chỉnh sửa hoặc lịch sử thay đổi riêng, nhóm nên đặt tên rõ ràng như `BillingAddress` và `ShippingAddress` trong mô hình phù hợp. Nếu chúng chỉ là cùng một địa chỉ được trình bày dưới hai nhãn trên giao diện, không cần tạo hai khái niệm chỉ vì có hai cách gọi.

### 3.3. Không nhầm đa nghĩa với từ đồng âm khác nghĩa

Trong ngôn ngữ học, từ đồng âm khác nghĩa là những từ có hình thức phát âm hoặc chữ viết giống nhau nhưng ý nghĩa không liên quan. Trong công việc mô hình hóa, dù hiện tượng được gọi là đa nghĩa hay đồng âm, vấn đề thực tế vẫn là một nhãn có thể khiến người nghe liên tưởng đến những khái niệm khác nhau.

Nhóm không cần tranh luận phân loại ngôn ngữ học trong mọi trường hợp. Điều cần làm là ghi nhận từng nghĩa, phạm vi sử dụng và thuật ngữ rõ hơn nếu việc dùng chung một từ gây nhầm lẫn trong bounded context.

## 4. Các khái niệm có tên gần giống nhau

Một trường hợp khác xảy ra khi hai khái niệm khác nhau có tên gần giống nhau. Chúng có thể dùng chung một từ gốc, có cấu trúc tên tương tự hoặc chỉ khác nhau ở một từ bổ nghĩa. Vì tên gần giống, nhóm dễ gộp chúng thành một đối tượng hoặc nhầm lẫn hành vi của chúng.

Ví dụ trong nghiệp vụ mua hàng và kho:

- **Đơn mua hàng (Purchase Order):** cam kết hoặc yêu cầu đặt mua gửi cho nhà cung cấp.
- **Phiếu nhận hàng (Goods Receipt):** ghi nhận hàng thực tế đã được nhận vào kho.
- **Phiếu nhập kho:** chứng từ hoặc thao tác ghi nhận hàng được nhập vào một vị trí/kho theo quy trình nội bộ.

Ba khái niệm có liên quan trong cùng quy trình nhưng không nhất thiết là một. Đơn mua hàng có thể được tạo trước khi hàng đến; phiếu nhận hàng được lập khi có hàng thực tế; phiếu nhập kho có thể ghi nhận việc đưa hàng vào vị trí lưu trữ. Một đơn mua hàng có thể được nhận thành nhiều đợt, và một đợt nhận có thể cần nhiều bước kiểm tra hoặc nhập kho.

### 4.1. So sánh bằng trách nhiệm và vòng đời

Khi hai tên gần giống nhau, hãy so sánh những đặc điểm có ý nghĩa đối với mô hình:

| Tiêu chí | Câu hỏi cần làm rõ |
| --- | --- |
| Mục đích | Khái niệm này giải quyết nhu cầu nghiệp vụ nào? |
| Chủ thể tạo | Ai hoặc quy trình nào tạo ra nó? |
| Thời điểm | Nó xuất hiện ở giai đoạn nào của quy trình? |
| Danh tính | Nó có mã định danh và được theo dõi độc lập không? |
| Vòng đời | Nó có những trạng thái nào và kết thúc khi nào? |
| Quy tắc | Điều kiện tạo, sửa, xác nhận hoặc hủy là gì? |
| Trách nhiệm | Bộ phận hoặc bounded context nào sở hữu nó? |
| Quan hệ | Nó liên kết với khái niệm nào và theo quan hệ một-một, một-nhiều hay nhiều-nhiều? |
| Kết quả | Nó tạo ra sự kiện, nghĩa vụ hoặc thay đổi nào? |

Nếu các tiêu chí này khác nhau đáng kể, tên gần giống không phải lý do để gộp hai khái niệm. Ngược lại, nếu các khác biệt chỉ là cách diễn đạt hoặc trường dữ liệu hiển thị, nhóm có thể đang nhìn cùng một khái niệm từ hai góc độ.

### 4.2. Tên gần giống không đồng nghĩa với quan hệ kế thừa

Trong thiết kế hướng đối tượng, nhóm đôi khi thấy hai tên có chung từ gốc và lập tức tạo quan hệ kế thừa. Ví dụ, `PurchaseOrder` và `SalesOrder` cùng có hậu tố `Order`, nhưng điều đó không chứng minh chúng là hai loại của một lớp nghiệp vụ chung.

Đơn mua hàng và đơn bán hàng có thể có người tạo, bên chịu trách nhiệm, trạng thái, điều kiện xác nhận và quy tắc giá khác nhau. Việc dùng chung một lớp cha chỉ hợp lý khi tồn tại một khái niệm trừu tượng có ý nghĩa nghiệp vụ và các bất biến chung thật sự. Quan hệ từ vựng không tự động tạo ra quan hệ mô hình.

## 5. Phân biệt ba hiện tượng trong thực tế

Bảng sau giúp nhóm định hướng cách xử lý khi phát hiện các thuật ngữ khó phân biệt.

| Hiện tượng | Dấu hiệu | Câu hỏi trọng tâm | Cách xử lý thường gặp |
| --- | --- | --- | --- |
| Từ đồng nghĩa | Nhiều tên cùng chỉ một khái niệm trong một context | Có thể thay thế các tên mà không đổi ý nghĩa và quy tắc không? | Chọn một thuật ngữ chuẩn; ghi các tên khác là bí danh hoặc tên cũ |
| Từ đa nghĩa | Một tên được dùng cho nhiều ý nghĩa | Mỗi lần dùng từ này đang chỉ khái niệm nào và trong context nào? | Làm rõ nghĩa theo context; dùng tên cụ thể hơn nếu cùng context bị mơ hồ |
| Khái niệm có tên gần giống | Các tên tương tự nhưng có thể chỉ đối tượng khác nhau | Mục đích, danh tính, vòng đời và quy tắc của chúng có khác nhau không? | Định nghĩa riêng; chọn tên làm rõ khác biệt và mối quan hệ |

Không phải lúc nào cũng có thể phân loại ngay từ một câu nói. Nhóm cần xem xét tình huống, người nói và hành động đang được mô tả. Nếu bằng chứng chưa đủ, hãy ghi nhận câu hỏi chưa được giải đáp thay vì tự quyết định.

## 6. Quy trình làm rõ thuật ngữ

Có thể dùng quy trình sau trong phỏng vấn nghiệp vụ, EventStorming, Domain Storytelling, Example Mapping hoặc các buổi thiết kế mô hình.

### Bước 1: Thu thập từ ngữ nguyên bản

Ghi lại chính xác từ mà người tham gia sử dụng, bao gồm cách gọi trong hội thoại, biểu mẫu, báo cáo, API hoặc hệ thống hiện tại. Ghi nhận ai dùng từ đó, thuộc bộ phận nào, trong tình huống nào và đang mô tả hành động gì.

Không vội chuẩn hóa từ ngay khi nghe thấy. Nếu đổi từ quá sớm, nhóm có thể vô tình làm mất một khác biệt mà người trong nghiệp vụ đang cố diễn đạt.

### Bước 2: Đặt từ vào một tình huống cụ thể

Hỏi người nói kể một trường hợp thực tế: ai thực hiện, đối tượng nào bị tác động, trước đó đang ở trạng thái nào, hành động nào diễn ra và kết quả là gì. Cùng một từ có thể mang nghĩa khác khi xuất hiện trong một quy trình khác.

Ví dụ, khi nghe “tạo tài khoản”, hãy hỏi đó là tạo thông tin đăng nhập cho người dùng, mở tài khoản công nợ cho khách hàng hay tạo hồ sơ khách hàng trong CRM. Tình huống giúp nhóm nhìn thấy khái niệm thực tế đằng sau từ ngữ.

### Bước 3: So sánh các cách gọi

Nếu có nhiều từ, hãy so sánh xem chúng có cùng chỉ đến một đối tượng, vai trò hoặc hành vi không. Sử dụng phép thử thay thế và so sánh các quy tắc, trạng thái, quyền hạn, vòng đời.

Nếu có một từ được dùng theo nhiều nghĩa, hãy liệt kê từng nghĩa cùng context và ví dụ. Nếu có nhiều khái niệm mang tên gần giống, hãy so sánh mục đích, chủ thể tạo, danh tính và kết quả của chúng.

### Bước 4: Xác định ranh giới context

Hỏi xem sự khác biệt có phản ánh hai mô hình nghiệp vụ khác nhau hay không. Một từ có thể được dùng hợp lệ theo hai nghĩa trong hai bounded context. Khi đó, cần giữ rõ định nghĩa của từng context và cách trao đổi giữa chúng.

Nếu hai nghĩa cùng xuất hiện trong một context và gây nhầm lẫn, nhóm nên chọn một thuật ngữ rõ hơn cho từng khái niệm. Không nên trông chờ người đọc phải suy đoán từ màn hình hoặc tên biến xung quanh.

### Bước 5: Thống nhất thuật ngữ chuẩn và bí danh

Chuyên gia nghiệp vụ xác nhận ý nghĩa và cách gọi phù hợp. Nhóm phát triển kiểm tra khả năng dùng tên đó trong mô hình, mã nguồn, API và kiểm thử. Ghi rõ thuật ngữ chuẩn, bí danh được chấp nhận, tên cũ cần nhận diện và các thuật ngữ dễ nhầm cần tránh.

Nếu các chuyên gia chưa thống nhất, hãy ghi lại các cách hiểu và xác định người có thẩm quyền quyết định. Không nên biến cách gọi của một cá nhân thành quy ước chung khi chưa có xác nhận.

### Bước 6: Kiểm chứng bằng ví dụ và phản ví dụ

Đưa thuật ngữ đã chọn vào một số câu nghiệp vụ và tình huống cụ thể. Hỏi người dùng xem cách diễn đạt có đúng với thực tế không. Kiểm tra cả trường hợp bình thường, ngoại lệ và trường hợp hai khái niệm dễ bị nhầm lẫn.

Ví dụ, nếu nhóm định nghĩa “hủy đơn hàng” và “trả hàng” là hai hành vi riêng, hãy kiểm tra một đơn chưa giao, một đơn đã giao và một đơn đã giao một phần. Nếu mô hình không diễn tả được kết quả khác nhau, định nghĩa hoặc ranh giới vẫn cần được xem lại.

### Bước 7: Đưa thuật ngữ vào mô hình và mã nguồn

Sử dụng thuật ngữ chuẩn trong tên entity, value object, aggregate, phương thức, sự kiện và kiểm thử tương ứng. Nếu một context nhận dữ liệu từ context khác với tên gọi khác, hãy chuyển đổi ở ranh giới tích hợp và ghi lại ánh xạ.

Ví dụ, context bán hàng có thể phát sự kiện `OrderCancelled`, trong khi context kho cần xử lý một yêu cầu dừng lấy hàng. Context kho không nhất thiết phải đổi toàn bộ mô hình nội bộ để dùng đúng tên của context bán hàng; nó cần hiểu hợp đồng sự kiện và chuyển đổi sang ngôn ngữ của mình.

### Bước 8: Duy trì và cập nhật từ điển

Khi quy trình, chính sách hoặc hệ thống thay đổi, thuật ngữ cũng có thể thay đổi. Nhóm cần cập nhật định nghĩa, bí danh, ví dụ và ánh xạ liên context. Những tên cũ vẫn có thể cần thiết để đọc dữ liệu lịch sử hoặc hỗ trợ chuyển đổi hệ thống, nhưng phải được đánh dấu rõ trạng thái sử dụng.

## 7. Ghi nhận thuật ngữ trong từ điển ngôn ngữ chung

Một từ điển thuật ngữ hữu ích không chỉ có hai cột “từ” và “định nghĩa”. Nó cần cung cấp đủ ngữ cảnh để người đọc biết cách sử dụng từ và phân biệt nó với các khái niệm liên quan.

Một mục từ có thể gồm các thông tin sau:

| Trường | Ý nghĩa |
| --- | --- |
| Thuật ngữ chuẩn | Tên được thống nhất sử dụng trong bounded context |
| Định nghĩa | Ý nghĩa nghiệp vụ ngắn gọn, đủ để phân biệt với khái niệm khác |
| Bounded context | Phạm vi mà định nghĩa này có hiệu lực |
| Ví dụ | Một hoặc nhiều tình huống sử dụng thuật ngữ đúng |
| Phản ví dụ | Trường hợp dễ nhầm nhưng không thuộc khái niệm này |
| Bí danh | Các tên khác cùng chỉ đến khái niệm, nếu có |
| Thuật ngữ dễ nhầm | Các khái niệm liên quan nhưng cần phân biệt |
| Quy tắc liên quan | Điều kiện, trạng thái hoặc hành vi quan trọng |
| Chủ thể xác nhận | Người hoặc vai trò chịu trách nhiệm xác nhận ý nghĩa |
| Trạng thái thuật ngữ | Đang dùng, cũ, chỉ dùng khi tích hợp hoặc đang chờ xác minh |

Ví dụ về một mục từ:

| Trường | Giá trị minh họa |
| --- | --- |
| Thuật ngữ chuẩn | Đơn hàng |
| Định nghĩa | Cam kết mua hàng được ghi nhận trong quy trình bán hàng |
| Bounded context | Bán hàng |
| Ví dụ | Khách gửi yêu cầu mua và hệ thống ghi nhận đơn hàng |
| Phản ví dụ | Yêu cầu lấy hàng trong kho sau khi đơn bán hàng được xác nhận |
| Bí danh | Phiếu đặt hàng (tên gọi cũ trong một số biểu mẫu) |
| Thuật ngữ dễ nhầm | Yêu cầu mua hàng, phiếu lấy hàng, phiếu giao hàng |
| Quy tắc liên quan | Chỉ được hủy khi thỏa chính sách theo trạng thái đơn |
| Chủ thể xác nhận | Chuyên gia nghiệp vụ bán hàng |
| Trạng thái thuật ngữ | Đang dùng |

Định nghĩa minh họa này không áp dụng cho mọi doanh nghiệp. Mỗi nhóm cần xây dựng từ điển dựa trên miền nghiệp vụ và bounded context của mình.

## 8. Thể hiện sự phân biệt trong thiết kế và mã nguồn

Ngôn ngữ chung cần được phản ánh trong mã nguồn để cuộc trao đổi và phần mềm cùng diễn đạt một mô hình. Việc đặt tên không thay thế thiết kế tốt, nhưng tên rõ ràng giúp người đọc hiểu ý định và phát hiện nơi mô hình còn mơ hồ.

### 8.1. Dùng tên cụ thể khi một từ có nhiều nghĩa

Giả sử hệ thống có cả tài khoản đăng nhập và tài khoản công nợ. Tên `Account` đứng riêng không cho biết nó thuộc nghiệp vụ nào.

```java
public class UserLoginAccount {
    // Thông tin xác thực và trạng thái truy cập của người dùng.
}

public class CustomerReceivableAccount {
    // Hạn mức, số dư và nghĩa vụ công nợ của khách hàng.
}
```

Tên cụ thể giúp người đọc nhận ra hai khái niệm có trách nhiệm khác nhau. Trong một codebase, nhóm có thể dùng package hoặc bounded context để làm rõ phạm vi và tránh lặp tên quá dài ở mọi nơi.

### 8.2. Đặt tên hành vi theo kết quả nghiệp vụ

Tên phương thức nên diễn đạt hành động và ý nghĩa mà người dùng nghiệp vụ nhận biết được. Nếu hủy đơn và trả hàng là hai quy trình riêng, không nên gộp cả hai vào một phương thức mơ hồ như `closeOrder()`.

```java
public class Order {
    public void cancel(CancellationReason reason) {
        // Kiểm tra chính sách hủy theo trạng thái đơn hàng.
    }
}

public class ReturnRequest {
    public void acceptReturnedItems() {
        // Xác nhận hàng trả về theo quy trình tiếp nhận.
    }
}
```

Đoạn mã chỉ minh họa cách đặt tên. Quy tắc thực tế, quyền hạn và cách phối hợp giữa các aggregate cần được xác định cùng chuyên gia nghiệp vụ.

### 8.3. Giữ ngôn ngữ riêng của từng context

Giả sử context bán hàng dùng khái niệm `Order`, còn context kho quản lý `PickingTask`. Một sự kiện từ bán hàng có thể được chuyển thành yêu cầu tạo hoặc dừng nhiệm vụ lấy hàng. Việc ánh xạ này cần được thực hiện rõ ràng tại ranh giới tích hợp.

```text
Sales context                         Warehouse context
--------------                         -----------------
OrderCancelled  --------------------->  StopPickingRequest
OrderConfirmed  --------------------->  CreatePickingTask
```

Context kho có thể lưu tham chiếu đến mã đơn bán hàng để truy vết, nhưng mô hình kho vẫn mô tả công việc lấy hàng bằng khái niệm của kho. Cách làm này giữ cho mỗi context có ngôn ngữ phù hợp với trách nhiệm của nó.

Nếu context nhận phải chuyển đổi nhiều thuật ngữ hoặc cấu trúc từ context gửi, nhóm có thể đặt một lớp chống ăn mòn (Anti-Corruption Layer) ở ranh giới để bảo vệ mô hình nội bộ khỏi cách biểu diễn bên ngoài. Lớp này chuyển đổi ý nghĩa theo hợp đồng tích hợp; nó không phải nơi để che giấu một định nghĩa nghiệp vụ chưa được làm rõ.

## 9. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Gộp hai từ gần nghĩa thành đồng nghĩa ngay lập tức | Quy tắc khác nhau có thể bị hợp nhất | Kiểm tra khả năng thay thế, vòng đời và trách nhiệm |
| Cho rằng mỗi khái niệm chỉ có một tên trong toàn tổ chức | Bỏ qua khác biệt hợp lệ giữa các bounded context | Xác định thuật ngữ theo context và lập ánh xạ khi tích hợp |
| Dùng cùng một từ cho nhiều khái niệm trong một context | Người đọc không biết hành vi nào đang được nói đến | Chọn tên cụ thể hơn và định nghĩa rõ từng khái niệm |
| Dựa vào tên để suy ra quan hệ kế thừa | Mô hình kỹ thuật không phản ánh quan hệ nghiệp vụ | Kiểm tra bất biến, trách nhiệm và hành vi chung trước khi tạo quan hệ |
| Chỉ ghi định nghĩa mà không có ví dụ | Người đọc hiểu định nghĩa theo các cách khác nhau | Bổ sung ví dụ, phản ví dụ và tình huống biên |
| Chọn thuật ngữ chỉ vì nó đã tồn tại trong database | Tên kỹ thuật cũ chi phối mô hình hiện tại | Đối chiếu với ngôn ngữ nghiệp vụ và ánh xạ tên cũ khi cần |
| Không ghi nhận bí danh và thuật ngữ lịch sử | Khó tìm kiếm tài liệu, báo cáo hoặc dữ liệu cũ | Ghi rõ bí danh, nguồn gốc và trạng thái sử dụng |
| Cập nhật tên trong mã nhưng không cập nhật trao đổi và tài liệu | Các bên tiếp tục dùng những cách gọi không thống nhất | Đồng bộ từ điển, tài liệu, mã và kiểm thử |

Một dấu hiệu cho thấy thuật ngữ chưa được làm rõ là các cuộc họp phải liên tục hỏi “ý bạn là loại nào?” hoặc mỗi người dùng một tên khác nhau cho cùng một thao tác. Nhóm nên xem đây là cơ hội cải thiện mô hình, thay vì chỉ yêu cầu mọi người ghi nhớ cách gọi mới.

## 10. Nguyên tắc thực hành

Khi làm việc với từ đồng nghĩa, từ đa nghĩa và các khái niệm có tên gần giống nhau, nhóm nên duy trì các nguyên tắc sau:

- **Luôn hỏi về tình huống sử dụng.** Từ ngữ chỉ có ý nghĩa rõ khi gắn với người nói, hành động, đối tượng và quy trình.
- **Phân biệt tên gọi với khái niệm.** Hai tên khác nhau có thể chỉ cùng một khái niệm; hai tên gần giống có thể chỉ hai khái niệm khác nhau.
- **Kiểm tra bằng quy tắc và vòng đời.** Danh tính, quyền hạn, trạng thái và kết quả nghiệp vụ cung cấp bằng chứng tốt hơn sự giống nhau của từ ngữ.
- **Chuẩn hóa trong phạm vi bounded context.** Một thuật ngữ cần có nghĩa nhất quán trong context của nó; context khác có thể có mô hình và cách gọi riêng.
- **Giữ lại bí danh có ích.** Tên cũ và cách gọi khác có thể cần cho trao đổi, tìm kiếm hoặc tích hợp, nhưng phải được đánh dấu rõ.
- **Dùng ví dụ và phản ví dụ.** Chúng giúp chuyên gia và nhóm phát triển xác nhận rằng mọi người đang hiểu cùng một khái niệm.
- **Để chuyên gia nghiệp vụ xác nhận ý nghĩa.** Nhóm phát triển có thể phát hiện sự mơ hồ và đề xuất cách diễn đạt, nhưng ý nghĩa nghiệp vụ cần được xác nhận bởi người phù hợp.
- **Đưa quyết định vào mã nguồn.** Tên lớp, phương thức, sự kiện và kiểm thử cần phản ánh thuật ngữ đã thống nhất.
- **Cập nhật khi mô hình thay đổi.** Từ điển ngôn ngữ chung là tài liệu sống, cần được điều chỉnh cùng nghiệp vụ và phần mềm.

Phân biệt đúng từ đồng nghĩa, từ đa nghĩa và các khái niệm có tên gần giống giúp nhóm xây dựng mô hình chính xác hơn. Một từ có thể có nhiều bí danh, một tên có thể được dùng với những nghĩa khác nhau giữa các context, và những tên gần giống có thể đại diện cho các vòng đời riêng. Khi nhóm kiểm tra ý nghĩa bằng tình huống, quy tắc và ranh giới context, ngôn ngữ chung trở thành công cụ làm rõ mô hình và hỗ trợ phần mềm phản ánh đúng nghiệp vụ.

## 11. Câu hỏi tự kiểm tra

1. Vì sao hai từ thường được dùng trong cùng một cuộc trò chuyện chưa chắc là từ đồng nghĩa trong mô hình nghiệp vụ?
2. Hãy nêu các câu hỏi dùng để xác minh hai tên có cùng chỉ đến một khái niệm trong một bounded context hay không.
3. Vì sao “hủy đơn hàng” và “trả hàng” thường cần được mô hình hóa như những hành vi riêng?
4. Từ “tài khoản” có thể mang những ý nghĩa nào trong một hệ thống doanh nghiệp? Cách đặt tên nào giúp giảm mơ hồ?
5. Vì sao cùng một thuật ngữ có thể có định nghĩa khác nhau một cách hợp lệ giữa hai bounded context?
6. Khi hai khái niệm có tên gần giống nhau, nhóm cần so sánh những đặc điểm nào trước khi quyết định gộp hoặc tách chúng?
7. Vì sao tên `PurchaseOrder` và `SalesOrder` giống nhau về từ gốc không đủ để kết luận chúng nên kế thừa cùng một lớp?
8. Một mục từ trong từ điển ngôn ngữ chung nên có những thông tin nào ngoài tên và định nghĩa?
9. Anti-Corruption Layer hỗ trợ chuyển đổi ngôn ngữ giữa các context như thế nào?
10. Hãy chọn một thuật ngữ đang được nhiều bộ phận sử dụng, liệt kê các nghĩa hoặc cách gọi của nó và đề xuất cách chuẩn hóa trong từng bounded context.
