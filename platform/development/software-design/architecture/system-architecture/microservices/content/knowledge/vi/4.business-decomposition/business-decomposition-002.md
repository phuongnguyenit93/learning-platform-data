# Khảo sát quy trình, tác nhân và ngôn ngữ của miền

## 1. Vì sao cần khảo sát miền trước khi phân rã Microservices?

Trong thiết kế Microservices, việc phân rã nghiệp vụ bắt đầu từ **cách doanh nghiệp tạo ra giá trị, ra quyết định và phối hợp công việc**. Những thứ thấy ngay trong code như controller, bảng dữ liệu, endpoint và màn hình chỉ là biểu hiện kỹ thuật của một mô hình nghiệp vụ nào đó. Nếu dùng chúng làm cơ sở chia dịch vụ quá sớm, hệ thống dễ rơi vào tình trạng nhiều service nhưng các tính năng vẫn phải sửa, kiểm thử và triển khai đồng loạt.

Bước **khảo sát quy trình, tác nhân và ngôn ngữ của miền** là hoạt động tìm hiểu có cấu trúc nhằm trả lời ba câu hỏi:

1. **Quy trình:** Một kết quả nghiệp vụ được tạo ra qua những bước, quyết định và ngoại lệ nào?
2. **Tác nhân:** Ai khởi xướng, thực hiện, phê duyệt, chịu trách nhiệm hoặc nhận kết quả của từng bước?
3. **Ngôn ngữ miền:** Người trong nghiệp vụ dùng những khái niệm, trạng thái và quy tắc nào, và mỗi khái niệm có ý nghĩa chính xác ở đâu?

Ba góc nhìn bổ sung cho nhau. Quy trình cho thấy công việc và điểm chuyển giao; tác nhân cho thấy quyền hạn và trách nhiệm; ngôn ngữ cho thấy mô hình tri thức ẩn sau từng quyết định. Kết quả khảo sát là đầu vào để nhận diện **subdomain**, **bounded context**, chủ sở hữu dữ liệu và các ứng viên ranh giới dịch vụ. Không phải mỗi bước quy trình, mỗi vai trò hay mỗi danh từ đều trở thành một microservice.

### 1.1. Phân biệt một số thuật ngữ nền tảng

- **Domain (miền nghiệp vụ):** lĩnh vực vấn đề mà phần mềm phục vụ, chẳng hạn thương mại điện tử, ngân hàng hoặc quản lý vận tải.
- **Business process (quy trình nghiệp vụ):** chuỗi hoạt động và quyết định hướng tới một kết quả, ví dụ từ khi khách đặt hàng đến khi giao hàng thành công.
- **Business capability (năng lực nghiệp vụ):** khả năng tương đối bền vững mà tổ chức cần có, ví dụ quản lý đơn hàng, giữ tồn kho, thu tiền hoặc giao vận.
- **Subdomain (miền con):** phần vấn đề chuyên biệt trong domain, có tri thức và quy tắc riêng. Có thể xem xét phân loại core, supporting hoặc generic subdomain theo giá trị cạnh tranh và đặc tính miền.
- **Bounded context:** ranh giới mà bên trong đó thuật ngữ, mô hình và quy tắc nghiệp vụ được hiểu nhất quán. Một từ có thể có nghĩa khác khi bước qua ranh giới này.
- **Microservice:** đơn vị triển khai/vận hành có trách nhiệm nghiệp vụ rõ; có thể triển khai một bounded context hoặc một phần phù hợp của nó, nhưng không có quy tắc bắt buộc ánh xạ một-một.

Các khái niệm thuộc những mức trừu tượng khác nhau. Quy trình thường **đi xuyên qua nhiều năng lực**; bounded context xác định nơi mô hình có ý nghĩa; service là một lựa chọn triển khai. Cần giữ sự phân biệt này khi khảo sát.

## 2. Xác định phạm vi khảo sát và câu hỏi cần giải quyết

Một buổi khảo sát hiệu quả bắt đầu từ **kết quả nghiệp vụ cụ thể**, thay vì câu hỏi “chúng ta nên tách bao nhiêu service?”. Ví dụ:

> Tìm hiểu quy trình đặt hàng và xử lý thanh toán từ khi khách xác nhận giỏ hàng đến khi đơn được chấp nhận hoặc hủy, bao gồm giữ hàng, thanh toán thất bại và hết hạn giữ hàng.

Phạm vi này có điểm bắt đầu, kết thúc và những tình huống cần quan sát. Nó có thể mở rộng khi phát hiện phụ thuộc quan trọng, nhưng phải ghi rõ giới hạn để buổi làm việc không biến thành thảo luận toàn bộ doanh nghiệp.

### 2.1. Đầu vào nên thu thập

- Mục tiêu nghiệp vụ, kết quả mong đợi và các chỉ số như thời gian xử lý, tỉ lệ thành công, lỗi đơn hàng hoặc tỉ lệ hoàn tiền.
- Nhóm người tham gia: chuyên gia nghiệp vụ, người vận hành trực tiếp, product owner, hỗ trợ khách hàng, kỹ thuật và đại diện các hệ thống tích hợp.
- Tài liệu hiện có: quy trình vận hành, chính sách kinh doanh, hợp đồng đối tác, form nhập liệu, báo cáo, hướng dẫn xử lý sự cố và mẫu giao dịch thực.
- Dữ liệu tình huống: hồ sơ mẫu thành công, thất bại, hủy, trễ, sửa hoặc phát sinh tranh chấp.
- Các ràng buộc: thời gian phản hồi, pháp lý, phân quyền, giờ làm việc, điều kiện phê duyệt, phụ thuộc đối tác và yêu cầu kiểm toán.

Tài liệu và phần mềm hiện hành hữu ích nhưng có thể phản ánh **cách đang triển khai**, không phải cách nghiệp vụ thật sự nên vận hành. Luôn hỏi điều gì là quy tắc bắt buộc, điều gì là cách làm tạm thời và điều gì chỉ tồn tại vì hạn chế của hệ thống cũ.

### 2.2. Khảo sát cả hiện tại và mục tiêu

Cần phân biệt:

- **As-is:** thực tế người dùng và hệ thống đang làm gì, kể cả thao tác thủ công và đường vòng khi lỗi.
- **To-be:** điều doanh nghiệp muốn thay đổi hoặc tối ưu.
- **Domain invariant:** quy tắc phải luôn được giữ, dù thao tác hay giao diện thay đổi.
- **Implementation constraint:** giới hạn kỹ thuật/hạ tầng hiện tại, có thể thay đổi trong tương lai.

Ví dụ: “Nhân viên kế toán đang tải CSV rồi đánh dấu đơn đã thanh toán” là cách vận hành hiện tại. “Không xác nhận đã thu tiền nếu chưa có chứng cứ thanh toán hợp lệ” mới là bất biến nghiệp vụ đáng giữ khi thiết kế hệ thống mới.

## 3. Khảo sát tác nhân: nhận diện vai trò, quyền hạn và trách nhiệm

**Tác nhân (actor)** là người, nhóm vai trò, hệ thống bên ngoài hoặc tác nhân tự động tương tác với quy trình để tạo ra hành động, quyết định hay thông tin. Tác nhân không đồng nghĩa với tài khoản người dùng, phòng ban hay tên một service.

Một người có thể đóng nhiều vai trò; một vai trò có thể được thực hiện bởi nhiều người; một hệ thống có thể đại diện cho nhiều bên nghiệp vụ khác nhau.

### 3.1. Các loại tác nhân thường gặp

| Loại tác nhân | Ví dụ trong bán hàng | Điều cần khảo sát |
| --- | --- | --- |
| Người khởi xướng | Khách hàng đặt mua | Mục tiêu, dữ liệu cung cấp, quyền hủy/sửa |
| Người thực hiện nghiệp vụ | Nhân viên kho, nhân viên giao hàng | Thao tác thực tế, quyền quyết định, quy tắc kiểm tra |
| Người phê duyệt | Quản lý duyệt hoàn tiền giá trị lớn | Điều kiện phê duyệt, bằng chứng, vết kiểm toán |
| Người giám sát | Nhân viên chăm sóc khách hàng | Thông tin cần xem, hành động được phép thực hiện |
| Hệ thống đối tác | Cổng thanh toán, đơn vị vận chuyển | Hợp đồng, độ tin cậy, độ trễ, thông báo bất đồng bộ |
| Tác nhân tự động | Job hết hạn giữ hàng, bộ phát hiện gian lận | Điều kiện kích hoạt, thời gian, khả năng chạy lặp |
| Tác nhân nhận kết quả | Khách nhận thông báo, hệ thống báo cáo | Dữ liệu cần nhận, thời điểm và mức cập nhật cho phép |

Với mỗi tác nhân, ghi rõ **điều họ muốn đạt được**, **hành động được phép**, **dữ liệu họ cung cấp/tiêu thụ**, **quyết định họ có quyền đưa ra** và **ai chịu trách nhiệm cuối cùng**. Các câu hỏi này thường bộc lộ những ranh giới bảo mật và quyền sở hữu nghiệp vụ quan trọng.

### 3.2. Vai trò nghiệp vụ và quyền truy cập là hai lớp khác nhau

“Nhân viên hỗ trợ” là một vai trò; “được hoàn tiền tới một hạn mức nhất định” là một chính sách quyền hạn. Không suy luận toàn bộ quyền từ tên vai trò mà chưa hỏi quy tắc ngoại lệ, ủy quyền, cấp phê duyệt và tình huống khẩn cấp.

Ví dụ, bộ phận chăm sóc khách hàng có thể **khởi tạo yêu cầu hoàn tiền**, nhưng chỉ Payment/Refund domain mới thực hiện quy tắc xác định số tiền hoàn được phép và ghi nhận giao dịch. Người quản lý có thể phê duyệt ngoại lệ; việc phê duyệt đó nên có dấu vết và trạng thái nghiệp vụ riêng.

### 3.3. Bảng tác nhân minh họa

| Tác nhân | Kích hoạt hoặc tham gia | Quyền quyết định quan trọng | Kết quả quan tâm |
| --- | --- | --- | --- |
| Khách hàng | Đặt, theo dõi, hủy đơn | Chấp nhận giá, địa chỉ và phương thức thanh toán | Đơn hợp lệ, thông tin trạng thái rõ |
| Nhân viên kho | Xử lý yêu cầu xuất/giữ hàng | Xác nhận tình trạng hàng vật lý trong phạm vi được giao | Độ chính xác tồn kho |
| Payment provider | Xử lý hoặc thông báo kết quả giao dịch | Chấp nhận/từ chối giao dịch theo hợp đồng đối tác | Trạng thái thanh toán có chứng cứ |
| Chăm sóc khách hàng | Tiếp nhận yêu cầu sửa/hủy | Quyết định trong giới hạn chính sách được cấp | Giải quyết vấn đề của khách |
| Bộ lập lịch | Phát hiện reservation quá hạn | Kích hoạt xử lý theo chính sách hết hạn | Hàng không bị giữ vô thời hạn |

Một bảng như vậy giúp thảo luận quyền hạn, nhưng chưa đủ để chia dịch vụ: cần đối chiếu tiếp các quy trình và mô hình dữ liệu.

## 4. Khảo sát quy trình: từ hành động đến sự kiện nghiệp vụ

Một quy trình là chuỗi **kích hoạt → hoạt động/quyết định → kết quả → chuyển giao hoặc kết thúc**. Người khảo sát cần thấy cả luồng bình thường lẫn luồng bất thường. Quy trình thường dài hơn một giao dịch cơ sở dữ liệu và có thể kéo qua nhiều bounded context.

### 4.1. Cấu trúc tối thiểu của một bước quy trình

| Trường khảo sát | Câu hỏi cần trả lời |
| --- | --- |
| Mục tiêu | Bước này tạo giá trị hoặc loại bỏ rủi ro gì? |
| Trigger | Sự kiện, yêu cầu hoặc mốc thời gian nào kích hoạt? |
| Actor | Ai yêu cầu, ai thực hiện, ai được quyết định? |
| Input | Điều kiện tiên quyết, thông tin và bằng chứng nào cần có? |
| Command/Action | Ai yêu cầu hệ thống làm điều gì? |
| Policy/Invariant | Quy tắc nào cho phép, từ chối hoặc thay đổi kết quả? |
| Outcome/Event | Điều gì đã xảy ra và có thể xác nhận được? |
| Owner | Ai giữ dữ liệu và chịu trách nhiệm về kết quả? |
| Failure/Alternative | Có thể trễ, trùng, lỗi, hủy, hoàn tác hoặc cần phê duyệt không? |
| Timing | Phải trả kết quả ngay, trong vài phút hay có thể xử lý sau? |

Ví dụ, “giữ hàng” có đầu vào là mã đơn và danh sách SKU/số lượng, chính sách kiểm tra tồn khả dụng, kết quả là **Hàng đã được giữ** hoặc **Yêu cầu giữ hàng bị từ chối**. Người sử dụng màn hình đặt hàng không nên tự quyết định tồn kho bằng cách đọc và sửa trực tiếp bảng của kho.

### 4.2. Phân biệt hành động, sự kiện và trạng thái

- **Command (lệnh/yêu cầu):** mong muốn thực hiện việc gì, ví dụ **ReserveInventory**, **CapturePayment**, **CancelOrder**. Lệnh có thể thất bại.
- **Domain event (sự kiện miền):** một sự thật nghiệp vụ đã xảy ra, ví dụ **InventoryReserved**, **PaymentCaptured**, **OrderCancelled**. Đặt tên ở thì quá khứ giúp phân biệt với yêu cầu.
- **State (trạng thái):** tình trạng đang có của một đối tượng hoặc quy trình, ví dụ **PENDING_PAYMENT**, **RESERVED**, **CANCELLED**.
- **Policy (chính sách):** quy tắc quyết định phản ứng với sự kiện, ví dụ “sau 15 phút chưa thanh toán thì giải phóng hàng đã giữ”, nếu đây thực sự là quy tắc của doanh nghiệp.

Từ “đã thanh toán” đặc biệt cần làm rõ: khách đã bấm thanh toán, cổng thanh toán đã ủy quyền, giao dịch đã thu tiền hay kế toán đã đối soát? Những mốc này có hậu quả nghiệp vụ khác nhau. Khảo sát có giá trị khi phát hiện các chỗ tưởng như “ai cũng hiểu” nhưng đang mang nhiều nghĩa.

### 4.3. Vẽ luồng chính và luồng ngoại lệ

Có thể bắt đầu bằng bản đồ đơn giản:

~~~text
Khách đặt hàng
  -> Kiểm tra đơn hợp lệ?
      | Không -> Từ chối / yêu cầu sửa
      | Có
  -> Yêu cầu giữ hàng
      | Hết hàng -> Thông báo không thể đáp ứng / kết thúc
      | Giữ thành công
  -> Yêu cầu thanh toán
      | Thành công -> Xác nhận đơn -> Chuyển giao vận
      | Thất bại -> Hủy hoặc cho phép thử lại -> Giải phóng hàng
      | Chưa rõ -> Chờ xác minh -> Đối soát / hết hạn
~~~

Mỗi nhánh phải có chủ thể chịu trách nhiệm, trạng thái rõ và điều kiện kết thúc. Đặc biệt ghi nhận những trường hợp bị bỏ qua khi chỉ hỏi “luồng bình thường”: request lặp, khách đóng trình duyệt, webhook đến trễ, hàng thay đổi giữa hai lần kiểm tra, người vận hành sửa thủ công, đối tác không trả lời, tác vụ chạy lại sau sự cố.

### 4.4. Dùng swimlane để nhìn điểm chuyển giao

Swimlane đặt từng hoạt động trong làn của một actor hoặc năng lực nghiệp vụ. Nó làm lộ các **handoff**: ai chuyển giao cho ai, thông tin nào được chuyển, thời gian chờ và trách nhiệm xử lý lỗi. Khi một bước cần người thứ hai phê duyệt hoặc một hệ thống đối tác xác nhận, điểm chuyển giao thường đáng xem xét như hợp đồng giao tiếp hoặc ranh giới quyền hạn.

Không diễn giải “mỗi làn = một microservice”. Làn thể hiện trách nhiệm ở cấp đang khảo sát. Một phòng ban có thể vận hành nhiều năng lực; một năng lực có thể có nhiều tác nhân; và một quy trình xuyên nhiều làn có thể vẫn chạy trong một hệ thống triển khai chung.

## 5. Khai thác tri thức miền từ chuyên gia và người vận hành

Thông tin quan trọng thường không xuất hiện trong sơ đồ chính thức. Nó nằm trong lời giải thích của nhân viên khi xử lý ngoại lệ, quy tắc ngầm của người duyệt hoặc các trường hợp khách hàng phàn nàn.

### 5.1. Các nguồn thông tin bổ sung cho nhau

**Phỏng vấn có cấu trúc:** hỏi một chuyên gia giải thích một tình huống thực tế từ đầu đến cuối, ai quyết định, căn cứ nào được dùng và kết quả được ghi nhận ở đâu.

**Quan sát công việc:** xem trực tiếp thao tác một giao dịch thành công và một giao dịch bất thường. Ghi các bước chuyển ngoài hệ thống như gọi điện, file Excel, email hoặc chờ phê duyệt.

**Phân tích tài liệu và dữ liệu:** so sánh quy định chính thức với log giao dịch, báo cáo thống kê, danh sách lỗi và các mẫu ticket hỗ trợ. Những khác biệt phải được mang trở lại trao đổi với chuyên gia.

**Workshop liên vai trò:** đưa người bán hàng, vận hành, tài chính, sản phẩm và kỹ thuật vào cùng một bàn để thống nhất thuật ngữ và tìm điểm giao nhau giữa quy trình.

**Event Storming:** khám phá chuỗi domain event và quyết định nghiệp vụ theo thời gian; phù hợp khi quy trình có nhiều tác nhân, ngoại lệ và sự phụ thuộc giữa các năng lực.

Mỗi phương pháp bù cho sự thiếu hụt của phương pháp khác. Chỉ phỏng vấn người quản lý có thể bỏ sót cách nhân viên xử lý khi công cụ không đáp ứng; chỉ đọc code có thể nhầm quy tắc kinh doanh với giới hạn kỹ thuật hiện tại.

### 5.2. Bộ câu hỏi dùng khi phỏng vấn

Với người thực hiện quy trình:

1. Điều gì khiến công việc này bắt đầu? Ai thông báo cho bạn?
2. Một trường hợp gần đây diễn ra chính xác như thế nào?
3. Bạn cần thông tin nào trước khi có thể quyết định?
4. Khi nào bạn từ chối yêu cầu hoặc chuyển cho người khác?
5. Trường hợp nào khó nhất, mất nhiều thời gian nhất hoặc phải xử lý thủ công?
6. Nếu đối tác/hệ thống trả lời chậm hoặc hai người thao tác cùng lúc thì sao?
7. Khi nào coi công việc hoàn thành? Ai xác nhận điều đó?
8. Những từ nào người mới thường hiểu nhầm?

Với người chịu trách nhiệm nghiệp vụ:

1. Quy tắc nào tuyệt đối không được vi phạm?
2. Quy tắc nào thay đổi thường xuyên theo chiến dịch, sản phẩm hay thị trường?
3. Điều kiện nào cần phê duyệt và ai có quyền phê duyệt?
4. Hậu quả của việc làm sai, làm trễ hoặc thực hiện hai lần là gì?
5. Cần bằng chứng gì để kiểm toán, đối soát hoặc giải quyết tranh chấp?
6. Công việc nào làm nên lợi thế của doanh nghiệp, công việc nào có thể chuẩn hóa?

Với đội kỹ thuật và tích hợp:

1. Hiện tại hệ thống nào là nguồn sự thật của từng dữ liệu quan trọng?
2. Có ai truy cập trực tiếp database hay sử dụng file export của hệ thống khác?
3. Những thay đổi nào thường buộc nhiều đội phát hành đồng thời?
4. Hợp đồng tích hợp có bảo đảm thứ tự, thời điểm, duy nhất hay chỉ giao ít nhất một lần?
5. Có trạng thái tạm thời, cơ chế thử lại và cách khôi phục sau sự cố không?

Ghi câu trả lời gắn với **tình huống và nguồn thông tin**. Khi hai người đưa ra hai cách hiểu khác nhau, đó là phát hiện cần làm rõ, không phải lỗi phải xóa bỏ ngay khỏi bản khảo sát.

## 6. Ngôn ngữ của miền: xây dựng Ubiquitous Language

**Ubiquitous Language** là bộ thuật ngữ nghiệp vụ được chuyên gia miền và đội xây dựng phần mềm cùng sử dụng khi thảo luận, mô hình hóa, viết ví dụ và thiết kế giao diện. Mục đích là tránh tình trạng một từ có nhiều nghĩa không được nhận diện, hoặc cùng một khái niệm bị gọi bằng các tên khác nhau.

Ngôn ngữ chung không bắt buộc toàn doanh nghiệp dùng **một mô hình dữ liệu toàn cục**. Trong DDD, một thuật ngữ có thể khác nhau hợp lệ giữa các bounded context. Điều cần có là định nghĩa chính xác **bên trong từng bối cảnh**, cùng cách chuyển đổi ý nghĩa khi đi qua bối cảnh khác.

### 6.1. Ghi thuật ngữ theo tình huống

| Thuật ngữ | Định nghĩa cần xác minh | Ví dụ câu hỏi làm rõ |
| --- | --- | --- |
| Đơn hàng | Yêu cầu mua đã được ghi nhận; trạng thái và hiệu lực do nghiệp vụ quy định | Có đơn trước khi thanh toán không? |
| Giữ hàng | Tạm dành một lượng tồn cho yêu cầu cụ thể | Giữ bao lâu? Có gia hạn không? |
| Hàng khả dụng | Số lượng có thể cam kết theo chính sách kho | Có trừ hàng đang được giữ? |
| Thanh toán thành công | Một mốc xử lý giao dịch theo quy tắc Payment | Thành công nghĩa là ủy quyền, thu tiền hay đối soát? |
| Hủy đơn | Kết thúc hoặc đảo một yêu cầu mua | Sau khi giao cho vận chuyển còn “hủy” được không? |
| Hoàn tiền | Trả lại một phần/toàn bộ số tiền đã thu | Trả tiền thành công có đồng nghĩa hoàn tất yêu cầu đổi trả? |

Bảng trên là ví dụ những câu hỏi cần hỏi, không phải định nghĩa mặc định áp dụng cho mọi doanh nghiệp.

### 6.2. Mỗi thuật ngữ nên có hồ sơ ngắn

Với những khái niệm quan trọng, ghi:

- **Tên chính thức và tên thường gọi:** có thể có thuật ngữ tiếng Việt/tiếng Anh cùng ý nghĩa.
- **Bối cảnh sử dụng:** nhóm nào dùng, trong bước quy trình nào.
- **Định nghĩa và ví dụ:** một trường hợp thuộc khái niệm, một trường hợp không thuộc.
- **Trạng thái và chuyển trạng thái:** đặc biệt với đơn hàng, thanh toán, hoàn tiền và giữ tồn.
- **Quy tắc/bất biến liên quan:** điều kiện nào phải đúng trước/sau thay đổi.
- **Nguồn sự thật:** ai có quyền xác nhận hoặc thay đổi giá trị.
- **Thuật ngữ dễ nhầm:** những từ trông tương tự nhưng khác nghĩa ở bối cảnh khác.

Ví dụ, **Đơn đã xác nhận** trong Order Context có thể nghĩa là người bán đồng ý đáp ứng yêu cầu, còn **Giao dịch đã xác nhận** trong Payment Context là một trạng thái của tiền. Nếu hệ thống dùng một enum chung **CONFIRMED** cho cả hai mà không ghi rõ ngữ cảnh, đội ngũ dễ thiết kế API và báo cáo sai.

### 6.3. Nhận diện ngôn ngữ khác nhau giữa các context

Cùng từ “khách hàng” có thể mang các khía cạnh khác nhau:

- Trong **Sales/Order**, khách hàng là chủ thể đặt mua, có địa chỉ liên hệ và lịch sử đơn.
- Trong **Billing**, khách hàng có thể là bên chịu trách nhiệm thanh toán, với thông tin xuất hóa đơn.
- Trong **Support**, khách hàng là người yêu cầu hỗ trợ, với quyền xác minh và lịch sử tương tác.

Không nên gộp mọi nghĩa vào một đối tượng **Customer** khổng lồ rồi bắt tất cả service cập nhật cùng schema. Mỗi bounded context có thể sở hữu mô hình phù hợp với mục đích riêng; khi giao tiếp, phải chỉ rõ định danh và ý nghĩa của dữ liệu truyền qua hợp đồng.

### 6.4. Dùng ngôn ngữ miền trong ví dụ và hợp đồng

Tên use case, event và endpoint nên thể hiện **hành vi nghiệp vụ** thay vì chỉ công việc CRUD. Ví dụ:

- **ReserveInventory** diễn tả ý định giữ hàng; **InventoryReserved** cho biết việc đó đã xảy ra.
- **RequestRefund** khác với **RefundApproved**, **RefundSubmitted** hoặc **RefundSettled**.
- **CancelOrder** là một yêu cầu có thể bị từ chối nếu đơn đã vượt mốc cho phép; **OrderCancelled** là kết quả được xác nhận.

Thời điểm phát sự kiện và điều kiện khiến nó đúng cần thống nhất. Không phát **PaymentCaptured** chỉ vì đã gửi yêu cầu thu tiền, nếu chưa nhận chứng cứ thu tiền thực sự.

## 7. Workshop Event Storming để khám phá quy trình liên miền

Event Storming là cách trực quan hóa những gì xảy ra trong domain bằng cách xếp các sự kiện nghiệp vụ trên một trục thời gian, sau đó tìm tác nhân, lệnh, chính sách và các điểm khó hiểu. Không cần công cụ chuyên biệt; bảng lớn và giấy ghi chú hoặc bảng trực tuyến đều có thể dùng.

### 7.1. Cách tiến hành

**Bước 1 — Chọn một câu chuyện thực:** ví dụ “khách đặt hàng hai sản phẩm, thanh toán thành công và hàng được giao”; thống nhất điểm bắt đầu, kết thúc.

**Bước 2 — Ghi các domain event:** đặt tên cho sự thật đã xảy ra, chẳng hạn **OrderPlaced**, **InventoryReserved**, **PaymentAuthorized**, **OrderConfirmed**, **ShipmentCreated**. Xếp theo thứ tự thời gian; chưa cần quyết định service hay database.

**Bước 3 — Điền khoảng trống:** ai yêu cầu sự kiện xảy ra, bằng lệnh nào, theo quy tắc nào, dựa trên thông tin gì? Đánh dấu những bước chỉ “có thể” xảy ra.

**Bước 4 — Thêm nhánh ngoại lệ:** hết hàng, bị từ chối thanh toán, thanh toán đến trễ, yêu cầu hủy sau khi giữ hàng, hai yêu cầu cạnh tranh một lượng tồn, sự kiện đến trùng.

**Bước 5 — Xác định điểm quyết định và điểm nóng:** nơi chuyên gia không thống nhất từ ngữ, nơi rủi ro nghiệp vụ cao, nơi phải đồng bộ dữ liệu hoặc chờ hệ thống khác.

**Bước 6 — Gom các cụm có mô hình nhất quán:** tìm những nhóm sự kiện, chính sách và dữ liệu có cùng ngôn ngữ/chủ sở hữu; từ đó hình thành ứng viên bounded context.

**Bước 7 — Ghi câu hỏi mở:** ai sẽ xác minh, bằng chứng nào cần lấy và quyết định thiết kế nào đang phụ thuộc câu trả lời.

### 7.2. Kết quả sơ bộ minh họa

~~~text
Khách hàng
  |
  v
[Đặt đơn] --OrderPlaced-->
  |
  v
[Giữ tồn] --InventoryReserved / InventoryReservationRejected-->
  |
  v
[Yêu cầu thanh toán] --PaymentAuthorized / PaymentDeclined-->
  |
  v
[Xác nhận đơn] --OrderConfirmed-->
  |
  v
[Tạo yêu cầu giao] --ShipmentRequested-->

Ngoại lệ:
- ReservationExpired -> giải phóng tồn -> xem xét hủy đơn
- PaymentDeclined -> cho phép thử lại hoặc hủy
- PaymentCallbackReceived nhiều lần -> xử lý idempotent
- ShipmentFailed -> báo lỗi và chuyển quy trình xử lý
~~~

Đây là bản đồ **sự kiện và tương tác nghiệp vụ**, chưa phải lời khẳng định rằng từng ô chữ trên hình tương ứng với một service. Tên sự kiện, thứ tự và quyền quyết định cần được xác minh qua tình huống thực tế.

### 7.3. Những điều nên ghi lại trong workshop

- **Điểm chưa thống nhất:** hai nhóm hiểu khác nhau về “đơn hoàn tất”.
- **Hotspot rủi ro:** có thể thu tiền nhưng chưa ghi nhận đơn vì callback trễ.
- **Quy tắc chưa rõ:** giữ hàng bao lâu và ai được gia hạn?
- **Tích hợp bên ngoài:** cổng thanh toán không bảo đảm phản hồi ngay.
- **Điểm nhất quán mạnh:** hai giao dịch cùng cố giữ đơn vị hàng cuối cùng.
- **Phụ thuộc thời gian:** sau bao lâu hệ thống phải đối soát?
- **Cơ hội tách trách nhiệm:** Payment có quy tắc và dữ liệu riêng biệt với Order.

Không bỏ qua câu hỏi khó để tạo ra sơ đồ “đẹp”. Chính các mâu thuẫn thường là nơi cần ranh giới ngôn ngữ hoặc quy tắc mới.

## 8. Ví dụ xuyên suốt: khảo sát quy trình đặt hàng trực tuyến

Giả sử doanh nghiệp bán hàng đang có một ứng dụng lớn xử lý đặt hàng, quản lý kho, thanh toán và giao hàng. Mục tiêu là hiểu nghiệp vụ để xem phần nào có thể tự chủ hơn, chứ chưa quyết định số lượng microservice.

### 8.1. Xác định câu chuyện và tác nhân

**Tình huống chính:** khách chọn sản phẩm, xác nhận địa chỉ, đặt hàng, hệ thống giữ tồn, thu tiền và chuyển giao hàng.

**Tác nhân liên quan:** khách hàng, nhân viên hỗ trợ, nhân viên kho, bên thanh toán, bên vận chuyển, hệ thống xử lý hết hạn và người quản lý có thẩm quyền xử lý ngoại lệ.

**Kết quả mong đợi:** một yêu cầu mua có trạng thái xác thực; tồn kho không bị cam kết vượt khả năng; tiền thu được ghi nhận đúng; đơn đủ điều kiện mới được gửi giao.

### 8.2. Chuỗi hành vi cần khảo sát

| Chặng | Actor/yêu cầu | Sự kiện hoặc kết quả có thể xảy ra | Quy tắc cần xác minh |
| --- | --- | --- | --- |
| Đặt hàng | Khách gửi yêu cầu | OrderPlaced / OrderRejected | Giá tại thời điểm đặt, địa chỉ, giới hạn mua |
| Giữ hàng | Quy trình đơn yêu cầu kho | InventoryReserved / ReservationRejected | Số tồn khả dụng, thời hạn giữ, cạnh tranh đồng thời |
| Thanh toán | Quy trình đơn yêu cầu thanh toán | PaymentAuthorized / PaymentDeclined / Unknown | Chống gửi trùng, xác thực nguồn callback, thời gian chờ |
| Xác nhận đơn | Quy trình đánh giá các điều kiện | OrderConfirmed | Có cần vừa giữ hàng vừa xác nhận thu tiền? |
| Chuyển giao | Quy trình yêu cầu giao vận | ShipmentRequested / ShipmentRejected | Hàng đủ điều kiện xuất kho, địa chỉ và thời gian |
| Hủy/ngoại lệ | Khách, hỗ trợ hoặc job | OrderCancelled / CompensationRequested | Điều kiện hủy, hoàn tiền, giải phóng tồn |

Điều cần giữ là ngôn ngữ và quy tắc do doanh nghiệp xác nhận. Ví dụ, một mô hình có thể cho phép đặt trước khi có hàng, một mô hình khác chỉ chấp nhận đơn nếu đã giữ hàng. Không áp quy trình minh họa thành luật chung.

### 8.3. Đi sâu vào ngoại lệ để phát hiện ranh giới

**Hai khách mua đơn vị hàng cuối cùng.** Ai có quyền quyết định yêu cầu nào được giữ hàng? Câu trả lời thường nằm tại mô hình tồn kho có quyền cập nhật số lượng khả dụng. Nếu Order tự đọc tồn và tự trừ số lượng, nó đang thực hiện quy tắc của miền kho và dễ gây oversell khi có nhiều yêu cầu song song.

**Khách bị trừ tiền nhưng Order chưa nhận thông báo.** Payment và Order đang giữ hai loại sự thật khác nhau. Cần khảo sát trạng thái “đang xác minh”, nguyên tắc đối soát và cách xử lý callback đến trễ. Không thể mặc định “không nhận phản hồi = thanh toán thất bại”.

**Khách hủy trong thời gian đang giao.** “Hủy đơn” có thể khác “yêu cầu hoàn hàng”. Cần hỏi điểm nào không thể đảo trực tiếp thao tác giao hàng, ai có quyền cho phép hoàn, ai ra quyết định hoàn tiền. Tình huống này có thể làm lộ bối cảnh **Return/Refund** riêng so với trạng thái Order.

**Webhook gửi lại.** Nếu nhà cung cấp thanh toán giao cùng thông báo nhiều lần, hệ thống phải nhận diện giao dịch trùng và không cộng tiền hoặc xác nhận đơn nhiều lần. Chính sách idempotency là một phần nghĩa vụ nghiệp vụ và tích hợp, cần ghi rõ.

**Giữ hàng đã hết hạn nhưng thanh toán vừa hoàn tất.** Không đủ để vẽ đường thẳng “giữ hàng rồi thanh toán”. Cần xác định chính sách ưu tiên, người chịu trách nhiệm đối soát và các hành động bù nếu không thể xác nhận đơn.

Các tình huống bất thường thường tiết lộ **ai là chủ sở hữu sự thật** rõ hơn luồng bình thường.

### 8.4. Thuật ngữ nảy sinh trong tình huống

| Khái niệm | Nơi xuất hiện | Phân biệt cần làm rõ |
| --- | --- | --- |
| Order | Xác lập ý định mua và vòng đời đơn | Khác giao dịch thu tiền |
| Reservation | Ghi nhận phần tồn tạm dành cho một yêu cầu | Khác xuất hàng vật lý |
| Available Stock | Số lượng có thể nhận cam kết theo chính sách | Khác số tồn thực tế trên kệ |
| Payment Attempt | Một lần thử thanh toán | Khác payment cuối cùng của đơn |
| Settlement | Hoàn tất một mốc đối soát/chuyển tiền theo đối tác | Khác xác nhận yêu cầu thanh toán |
| Shipment | Nghiệp vụ giao vận | Khác trạng thái đơn tổng hợp |
| Refund | Giao dịch trả lại tiền | Khác việc khách trả hàng vật lý |

Sau khi thống nhất từ ngữ, có thể dùng chúng trong use case, event và tài liệu API; từng context vẫn có quyền dùng mô hình phù hợp của mình.

### 8.5. Phác thảo ứng viên bounded context

Từ quy trình và ngôn ngữ trên, có thể nêu các ứng viên ban đầu:

- **Order Context:** ý định mua, dòng hàng đã đặt, điều kiện xác nhận và vòng đời đơn.
- **Inventory Context:** tồn khả dụng, giữ hàng, giải phóng tồn, chính sách giới hạn cam kết.
- **Payment Context:** lần thử, giao dịch, trạng thái thanh toán và đối soát kết quả.
- **Shipping Context:** lệnh giao, vận đơn và trạng thái vận chuyển.
- **Return/Refund Context (cần khảo sát thêm):** yêu cầu trả hàng, điều kiện chấp nhận, xử lý hoàn tiền tùy quy mô nghiệp vụ.

Đây chỉ là **giả thuyết ranh giới** cần tiếp tục kiểm chứng bằng mức độ nhất quán nghiệp vụ, tần suất thay đổi, ownership và chi phí vận hành. Một tổ chức nhỏ có thể giữ các context này trong cùng một modular monolith; tổ chức khác có thể có lý do triển khai một số context thành microservice.

## 9. Từ kết quả khảo sát đến giả thuyết phân rã nghiệp vụ

Sau khi có sơ đồ quy trình, bảng tác nhân và glossary, nhiệm vụ kế tiếp là tìm các cụm có **tính gắn kết nội tại cao** và **phụ thuộc thay đổi ra ngoài thấp**. Không quyết định theo số bảng, số API hoặc số bước trong một quy trình.

### 9.1. Dấu hiệu của một ranh giới tốt

1. **Một nhóm quy tắc cùng thay đổi:** các bất biến và trạng thái có lý do nghiệp vụ để ở gần nhau.
2. **Ngôn ngữ nhất quán:** cùng thuật ngữ có ý nghĩa ổn định trong ranh giới.
3. **Quyền sở hữu dữ liệu xác định:** có một nơi có quyền ghi và diễn giải sự thật chính.
4. **Hợp đồng trao đổi tự nhiên:** bên ngoài có thể yêu cầu năng lực hoặc nhận sự kiện mà không cần biết bảng/nội bộ.
5. **Trách nhiệm đội ngũ rõ:** có nhóm đủ hiểu miền để phát triển, vận hành và chịu trách nhiệm về kết quả.
6. **Phù hợp yêu cầu nhất quán:** dữ liệu cần giao dịch cục bộ đặt trong ranh giới hợp lý; tương tác liên miền có cơ chế phối hợp rõ.
7. **Có giá trị triển khai độc lập:** những thay đổi quan trọng có thể được thực hiện theo nhịp riêng với chi phí chấp nhận được.

Ví dụ, quy tắc “không giữ quá tồn kho khả dụng” nên nằm cùng nơi quản lý reservation và tồn khả dụng. Nếu mỗi lần thay đổi thuật toán giữ hàng phải thay đổi Order, Checkout và Inventory đồng thời, cần xem lại cách phân quyền quyết định.

### 9.2. Context map: làm rõ quan hệ giữa các miền

Khi hai bounded context cần hợp tác, ghi rõ **thông tin nào chuyển qua ranh giới, ai là nguồn sự thật và thuật ngữ được dịch như thế nào**.

Ví dụ:

~~~text
Order Context
  | yêu cầu giữ hàng: orderId, SKU, quantity
  v
Inventory Context
  | kết quả: reservationId, RESERVED / REJECTED
  v
Order Context

Payment Context
  | thông báo giao dịch: paymentId, orderId, trạng thái đã xác minh
  v
Order Context
~~~

Order cần biết **kết quả giữ hàng**; không cần ghi cột **available_quantity** của Inventory. Order cần biết **trạng thái thanh toán đủ để quyết định đơn**; không nhất thiết phải giữ toàn bộ mô hình đối soát nội bộ của Payment. Khi các context dùng tên hoặc định dạng khác nhau, có thể có lớp chuyển đổi dữ liệu và thuật ngữ ở ranh giới tích hợp.

### 9.3. Những điều chưa nên quyết định trong lúc khảo sát

- Số lượng container, tên repository hoặc cấu trúc package cuối cùng.
- Công nghệ message broker, framework, database engine.
- Quy tắc “mỗi danh từ = một service” hoặc “mỗi actor = một service”.
- Việc mọi tác vụ đều phải bất đồng bộ.
- Mức tách vật lý ngay lập tức khi chưa có nhu cầu deploy độc lập hoặc khả năng vận hành tương ứng.

Có thể ghi những yếu tố kỹ thuật như ràng buộc, nhưng không để chúng thay thế việc hiểu domain.

## 10. Bộ hiện vật nên có sau một vòng khảo sát

Một vòng khảo sát hữu ích tạo ra những đầu ra giúp người khác kiểm chứng lại lời giải thích, thay vì chỉ giữ hình vẽ không chú giải.

### 10.1. Bản mô tả phạm vi

~~~text
Quy trình: Đặt hàng và xác nhận thanh toán
Bắt đầu: Khách gửi yêu cầu đặt mua
Kết thúc: Đơn được xác nhận, từ chối hoặc hủy có lý do
Kết quả nghiệp vụ: Trạng thái đơn đáng tin cậy;
                   không cam kết tồn vượt khả năng;
                   thanh toán được đối soát
Ngoài phạm vi phiên khảo sát: Tối ưu tuyến giao hàng
Các ngoại lệ cần phân tích: Hết hàng, thanh toán chậm,
                            callback lặp, hết hạn giữ hàng
~~~

### 10.2. Bản đồ tác nhân và quyết định

Đối với mỗi vai trò, có mô tả công việc, trigger, hành động, quyền phê duyệt, dữ liệu truy cập, kết quả mong đợi và đầu mối xác minh. Đối với hệ thống đối tác, thêm giới hạn giao thức, độ trễ và cách nhận biết kết quả cuối cùng.

### 10.3. Bản đồ quy trình có nhánh

Sơ đồ hoặc bảng cần chỉ ra trạng thái đầu/cuối, sự kiện, lệnh, người chịu trách nhiệm, quy tắc phân nhánh, đường thất bại, xử lý bù và timeout. Có thể dùng BPMN, swimlane, Event Storming hoặc bảng theo trình tự; công cụ nào thể hiện đủ nghĩa thì dùng công cụ đó.

### 10.4. Glossary theo context

Mỗi thuật ngữ chính có định nghĩa, ví dụ, chủ sở hữu, trạng thái liên quan và những nghĩa dễ nhầm. Tên gọi chưa thống nhất được đánh dấu kèm câu hỏi và người có quyền chốt định nghĩa; không tự đồng nhất hai nghĩa khi chưa có bằng chứng.

### 10.5. Sổ quyết định và câu hỏi mở

Ví dụ:

| Vấn đề | Tác động | Người cần xác nhận | Cách xác minh |
| --- | --- | --- | --- |
| Thời hạn giữ hàng | Quy trình hết hạn và xử lý thanh toán trễ | Vận hành kho + sản phẩm | Xem chính sách thực tế, mẫu đơn quá hạn |
| “Thanh toán thành công” nghĩa gì? | Trạng thái Order và tích hợp Payment | Tài chính + tích hợp thanh toán | Đọc hợp đồng đối tác, trường trạng thái |
| Ai có quyền hoàn tiền một phần? | Phân quyền và quy tắc Refund | CS + tài chính | Xem quy trình phê duyệt, tình huống thực |
| Có cho phép đặt vượt tồn? | Ranh giới nhất quán của Inventory | Kinh doanh + kho | Kiểm tra sản phẩm đặt trước và ưu tiên khách |

Danh sách này giúp các giả thuyết phân rã có **nguồn gốc từ nhu cầu nghiệp vụ**, tránh biến một suy đoán kỹ thuật thành quy tắc không ai chịu trách nhiệm.

### 10.6. Bảng ứng viên context và dữ liệu sở hữu

| Ứng viên context | Năng lực | Dữ liệu nguồn sự thật | Hợp tác quan trọng |
| --- | --- | --- | --- |
| Order | Quản lý vòng đời đơn | Order, order line, các quyết định xác nhận/hủy | Inventory, Payment, Shipping |
| Inventory | Quản lý tồn và reservation | Stock, reservation | Order, Warehouse |
| Payment | Quản lý giao dịch thanh toán | Payment attempt, transaction, kết quả đối soát | Order, Payment provider |
| Shipping | Quản lý chuyển giao và vận chuyển | Shipment, tracking state | Order, nhà vận chuyển |

Chủ sở hữu xác định theo **ý nghĩa nghiệp vụ và quyền ghi**, không chỉ theo nơi lưu bản sao dữ liệu. Ví dụ Order có thể lưu bản chiếu trạng thái thanh toán để hiển thị, nhưng nguồn sự thật thanh toán thuộc Payment.

## 11. Một quy trình khảo sát mẫu cho nhóm thiết kế

Có thể tổ chức một chuỗi làm việc ngắn, lặp lại theo từng quy trình có giá trị cao:

**Phiên 1 — Xác định tình huống và tác nhân.** Chọn một business outcome rõ, liệt kê ai tham gia, mỗi người muốn gì, thu thập ca thực và quyết định phạm vi.

**Phiên 2 — Đi theo luồng thực tế.** Vẽ hành động/sự kiện từ trigger đến kết quả; quan sát nơi phê duyệt, chuyển giao, chờ đợi và xử lý thủ công. Bổ sung các nhánh ngoại lệ.

**Phiên 3 — Làm rõ ngôn ngữ và quy tắc.** Đối chiếu các thuật ngữ gây tranh cãi, xác định trạng thái, bất biến và nguồn sự thật. Viết ví dụ nghiệp vụ có thể kiểm chứng cho từng quy tắc quan trọng.

**Phiên 4 — Gom nhóm và nêu giả thuyết ranh giới.** Tìm các cụm có mô hình và trách nhiệm nhất quán; ghi phụ thuộc, hợp đồng, chỗ cần nhất quán mạnh và chỗ có thể chấp nhận xử lý trễ.

**Phiên 5 — Xác nhận với người sở hữu miền.** Dùng một trường hợp thành công và một trường hợp lỗi để kiểm tra rằng sơ đồ mô tả đúng ý nghĩa. Ghi quyết định, câu hỏi chưa trả lời và dữ liệu cần điều tra tiếp.

Đây là trình tự tham khảo, có thể gộp hoặc tách phiên theo mức độ phức tạp. Khi phát hiện câu trả lời mới, quay lại cập nhật process map và glossary. Khảo sát miền là quá trình học và điều chỉnh mô hình, không phải một buổi họp duy nhất.

## 12. Sai lầm phổ biến và cách tránh

### 12.1. Xem màn hình hoặc database như bản đồ miền

Một màn hình “Quản lý đơn” có thể hiển thị cả thanh toán, kho và vận chuyển. Nó là một góc nhìn hỗ trợ người dùng, không chứng minh mọi dữ liệu trên màn hình thuộc cùng một context. Tương tự, một bảng có nhiều cột không đồng nghĩa một miền duy nhất sở hữu mọi quy tắc trên các cột đó.

**Cách làm:** hỏi nguồn sự thật, hành vi nghiệp vụ và ai có quyền thay đổi; tách projection hiển thị khỏi dữ liệu sở hữu.

### 12.2. Chỉ mô tả happy path

Nếu bỏ qua thanh toán không rõ kết quả, giữ hàng hết hạn, yêu cầu lặp hay hủy sau khi giao vận bắt đầu, mô hình sẽ thiếu phần chứa nhiều quy tắc quan trọng nhất.

**Cách làm:** luôn lấy ít nhất một ca thành công, một ca thất bại, một ca trễ, một ca trùng lặp và một ca cần xử lý thủ công để làm rõ các đường thay thế.

### 12.3. Đánh đồng tên phòng ban với bounded context

Sơ đồ tổ chức phản ánh cách quản lý con người; một phòng ban có thể làm nhiều năng lực và một năng lực có thể đi qua nhiều phòng ban. Ranh giới có thể trùng khi phản ánh ownership thực tế, nhưng không nên suy ra một cách máy móc.

**Cách làm:** kiểm tra thuật ngữ, bất biến, dữ liệu và nhịp thay đổi trước khi đề xuất context.

### 12.4. Áp một định nghĩa cho mọi bối cảnh

Từ “khách hàng”, “xác nhận” hay “đã hoàn thành” có thể khác nghĩa hợp lệ ở Sales, Payment và Shipping. Ép dùng một entity hoặc enum chung thường tạo phụ thuộc sâu và gây hiểu lầm khi tích hợp.

**Cách làm:** gắn thuật ngữ với context; ghi mapping và chuyển đổi ngữ nghĩa khi dữ liệu đi qua ranh giới.

### 12.5. Đặt tên sự kiện trước khi hiểu kết quả

“ProcessPayment” không nói thanh toán đã thành công, đang chạy hay thất bại. Phát event quá sớm hoặc dùng từ quá chung làm consumer quyết định sai.

**Cách làm:** phân biệt yêu cầu với sự thật đã hoàn tất; làm rõ nguồn xác minh, điều kiện phát và ngữ nghĩa của từng trạng thái.

### 12.6. Chia service ngay trong workshop

Nếu cứ mỗi event, bảng hoặc actor lại vẽ một microservice, thiết kế dễ bị chia vụn, tăng độ trễ và giao tiếp mạng. Mục đích workshop là học miền và tìm ứng viên ranh giới, chưa phải quyết định deployment topology.

**Cách làm:** gom theo mô hình, quyền sở hữu, ranh giới nhất quán và giá trị thay đổi độc lập. Có thể giữ các context dưới dạng module trước khi cần triển khai tách.

### 12.7. Biến tài liệu khảo sát thành một “sự thật” không được xác nhận

Một mô hình do riêng đội kỹ thuật vẽ có thể có vẻ hợp lý nhưng bỏ sót chính sách thật hoặc khác với từ ngữ người vận hành dùng.

**Cách làm:** lưu nguồn ví dụ, người xác nhận và các câu hỏi mở; diễn giải lại bằng trường hợp thực cho chuyên gia miền kiểm tra.

## 13. Bài thực hành: khảo sát miền đặt vé

Hãy hình dung một nền tảng bán vé sự kiện đang có ba màn hình: **Đặt vé**, **Thanh toán** và **Quản lý ghế**. Người quản lý nói “vé được giữ 10 phút”, nhân viên hỗ trợ nói “vé đã khóa”, còn nhà cung cấp thanh toán trả trạng thái “đang xử lý”.

### Phần A — Xác định tác nhân

Liệt kê khách mua, người tổ chức sự kiện, nhân viên hỗ trợ, cổng thanh toán và bộ xử lý quá hạn. Với từng tác nhân, ghi mục tiêu, quyền quyết định, dữ liệu họ cần và điều họ không được tự làm.

### Phần B — Vẽ quy trình

Lập một luồng từ chọn ghế đến phát hành vé. Thêm ít nhất bốn trường hợp: hai khách chọn cùng ghế; hết thời hạn giữ; cổng thanh toán phản hồi trễ; khách hủy khi đã thu tiền.

Đối với từng bước, ghi trigger, command, event, trạng thái, chính sách và người chịu trách nhiệm giải quyết ngoại lệ.

### Phần C — Làm rõ ngôn ngữ

Viết định nghĩa có ví dụ cho **Ghế khả dụng**, **Giữ ghế**, **Khóa ghế**, **Vé được phát hành**, **Thanh toán thành công** và **Hủy vé**. Chỉ ra chỗ nào hai thuật ngữ đang bị dùng thay cho nhau nhưng thật ra có nghĩa khác.

### Phần D — Nêu giả thuyết bounded context

Tìm những năng lực có quyền sở hữu và dữ liệu riêng, chẳng hạn Booking, Seat Inventory và Payment; mô tả dữ liệu nguồn sự thật của mỗi bên và hai hợp đồng tương tác quan trọng. Trình bày một thay đổi nghiệp vụ có thể thực hiện trong một context và một thay đổi phải phối hợp nhiều context.

Bài tập hoàn thành khi có thể dùng **một tình huống thành công và một tình huống lỗi** để giải thích rõ ai quyết định, dữ liệu nào chứng minh kết quả và thuật ngữ nào có nghĩa trong từng bối cảnh. Không cần quyết định sẽ chạy bao nhiêu container.

## 14. Ghi nhớ

- **Khảo sát quy trình** giúp thấy hành vi, quyết định, ngoại lệ, thời gian chờ và điểm chuyển giao tạo ra giá trị nghiệp vụ.
- **Khảo sát tác nhân** giúp phân biệt người/hệ thống khởi xướng, người có quyền quyết định và người chịu trách nhiệm về kết quả.
- **Khảo sát ngôn ngữ miền** giúp thống nhất định nghĩa trong từng bối cảnh và phát hiện nơi một từ mang nhiều nghĩa khác nhau.
- **Event Storming, phỏng vấn, quan sát và đối chiếu ca thực** là những cách bổ sung cho nhau để khám phá tri thức miền.
- **Bounded context và ứng viên microservice** được suy ra sau khi hiểu quy tắc, ownership, dữ liệu và nhịp thay đổi; quy trình, actor hay entity riêng lẻ không quyết định sẵn ranh giới triển khai.
- Một bản khảo sát hữu ích cho phép người khác truy nguyên từ **tình huống nghiệp vụ → quy tắc và thuật ngữ → chủ sở hữu → giả thuyết ranh giới**, rồi tiếp tục kiểm chứng trước khi triển khai kiến trúc.
