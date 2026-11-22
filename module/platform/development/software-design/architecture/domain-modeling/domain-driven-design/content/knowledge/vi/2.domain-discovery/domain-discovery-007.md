# Ghi lại giả định, câu hỏi mở và bằng chứng xác nhận mô hình

Trong quá trình khám phá nghiệp vụ, đội phát triển thường nghe nhiều mô tả khác nhau về cùng một quy trình. Chuyên gia nghiệp vụ kể cách công việc diễn ra, nhân viên vận hành nêu các trường hợp ngoại lệ, tài liệu chính sách mô tả quy định chính thức, còn dữ liệu hệ thống cho thấy những gì đã thực sự xảy ra. Những nguồn thông tin này có thể bổ sung cho nhau, nhưng cũng có thể mâu thuẫn.

Domain model vì thế nên được xem là mô hình hiểu biết đang được kiểm chứng. Một nhận định nghe hợp lý trong buổi trao đổi chưa chắc đã là quy tắc nghiệp vụ. Một quy trình được mô tả trong tài liệu chưa chắc phản ánh cách mọi người đang vận hành. Nếu đội phát triển biến những điều chưa rõ thành mã nguồn quá sớm, các giả định vô tình trở thành hành vi mặc định của hệ thống.

Ghi lại giả định, câu hỏi mở và bằng chứng giúp cả chuyên gia nghiệp vụ lẫn đội phát triển nhìn thấy phần nào đã hiểu, phần nào còn chưa chắc chắn và vì sao mô hình hiện tại được hình thành. Đây là hoạt động liên tục trong domain discovery, không phải thủ tục chỉ làm một lần trước khi bắt đầu thiết kế.

## 1. Phân biệt giả định, câu hỏi mở và bằng chứng

Ba loại thông tin này liên quan chặt chẽ với nhau nhưng không thể dùng thay thế cho nhau.

| Loại thông tin | Ý nghĩa | Câu hỏi dùng để nhận diện | Ví dụ |
|---|---|---|---|
| Giả định (assumption) | Một nhận định tạm thời mà nhóm đang dựa vào, nhưng chưa có đủ cơ sở để xem là quy tắc đã xác nhận | “Hiện chúng ta đang tin điều gì nhưng vẫn cần kiểm chứng?” | “Đơn hàng chỉ được xác nhận sau khi tồn kho đã được giữ chỗ.” |
| Câu hỏi mở (open question) | Một điều chưa biết cần được làm rõ để hiểu đúng nghiệp vụ hoặc đưa ra quyết định | “Chúng ta chưa biết điều gì?” | “Nếu chỉ còn đủ hàng cho một phần đơn, doanh nghiệp xử lý đơn như thế nào?” |
| Bằng chứng (evidence) | Thông tin có nguồn gốc và bối cảnh cụ thể, được dùng để ủng hộ, bác bỏ hoặc giới hạn một nhận định | “Chúng ta dựa vào quan sát hoặc nguồn nào?” | “Trong các giao dịch được kiểm tra, hệ thống chỉ chuyển đơn sang trạng thái xác nhận sau khi nhận kết quả giữ chỗ thành công.” |

Giả định là điều đang được tin; câu hỏi mở là điều cần biết; bằng chứng là cơ sở để đánh giá nhận định. Câu trả lời cho một câu hỏi có thể tạo ra quy tắc đã thống nhất, nhưng bản thân câu trả lời vẫn cần được đặt trong bối cảnh và gắn với nguồn xác nhận.

Không nên viết giả định như một yêu cầu đã được phê duyệt. Chẳng hạn, “hệ thống phải từ chối đơn thiếu hàng” nghe giống một yêu cầu triển khai. Cách ghi phù hợp hơn là “Nhóm đang giả định đơn thiếu hàng bị từ chối toàn bộ; cần xác nhận doanh nghiệp có cho phép giao một phần hay không”. Cách diễn đạt thứ hai cho thấy rõ điều chưa chắc chắn và việc cần làm tiếp theo.

Tương tự, “bộ phận vận hành nói rằng...” là thông tin về nguồn phát biểu, chưa tự động trở thành quy tắc áp dụng cho mọi trường hợp. Hãy ghi lại ai cung cấp thông tin, trong hoàn cảnh nào và thông tin đó phản ánh chính sách, kinh nghiệm cá nhân hay một trường hợp cụ thể.

## 2. Nguyên tắc ghi nhận

### Tách sự kiện quan sát được khỏi cách diễn giải

Ghi lại điều đã quan sát trước, sau đó mới ghi nhận cách nhóm diễn giải điều đó. Ví dụ:

- Quan sát: “Trong ba hồ sơ được kiểm tra, nhân viên chỉ gửi yêu cầu giao hàng sau khi trạng thái giữ chỗ tồn kho thành công.”
- Diễn giải: “Có thể việc giữ chỗ là điều kiện để đơn hàng được xác nhận.”
- Câu hỏi cần kiểm chứng: “Quy tắc này áp dụng cho mọi loại đơn hay chỉ cho đơn giao từ kho trung tâm?”

Việc tách ba phần giúp người đọc không nhầm một suy luận thành sự thật đã được xác nhận. Nếu sau đó tìm thấy đơn hàng ngoại lệ, nhóm có thể xem lại phạm vi của quy tắc mà không phải phủ nhận toàn bộ quan sát trước đó.

### Viết nhận định đủ cụ thể để có thể kiểm chứng

Một giả định hữu ích cần nêu rõ đối tượng, điều kiện và phạm vi. “Khách hàng có thể hủy đơn” quá rộng để kiểm chứng. “Khách hàng có thể tự hủy đơn trước khi kho bắt đầu đóng gói” cụ thể hơn, nhưng vẫn cần làm rõ các kênh đặt hàng, loại khách hàng và ngoại lệ.

Tránh những từ không có phạm vi rõ ràng như “thường”, “nhanh”, “hợp lệ”, “đã xử lý” nếu chúng ảnh hưởng đến quy tắc. Hãy hỏi chuyên gia nghiệp vụ ý nghĩa có thể quan sát hoặc đo lường được của những từ đó.

### Ghi rõ phạm vi và thời điểm

Một quy tắc có thể đúng với một chi nhánh, loại hợp đồng, kênh bán hàng hoặc giai đoạn chính sách nhưng không đúng ở nơi khác. Mỗi ghi nhận cần có phạm vi áp dụng và thời điểm thu thập. Khi chính sách thay đổi, nhóm có thể xác định bằng chứng cũ còn phù hợp hay đã lỗi thời.

### Ghi cả bằng chứng trái chiều

Không chỉ lưu những thông tin ủng hộ mô hình hiện tại. Trường hợp ngoại lệ, ý kiến bất đồng và dữ liệu không khớp thường là tín hiệu quan trọng để phát hiện ranh giới của một quy tắc hoặc sự khác nhau giữa các bộ phận. Nếu hai phòng ban dùng cùng một thuật ngữ nhưng diễn giải khác nhau, đó có thể là dấu hiệu cần làm rõ ngôn ngữ chung hoặc ranh giới bounded context.

### Gắn trách nhiệm và bước tiếp theo

Mỗi giả định hoặc câu hỏi mở cần có người chịu trách nhiệm theo dõi, cách kiểm chứng và trạng thái hiện tại. “Đang chờ xác nhận” mà không có người phụ trách hoặc hành động tiếp theo sẽ dễ bị bỏ quên. Người phụ trách có thể là người điều phối discovery, chuyên gia nghiệp vụ hoặc người có thẩm quyền quyết định quy tắc.

## 3. Ghi nhận và quản lý giả định

Giả định thường xuất hiện khi nhóm cần tiếp tục trao đổi dù chưa có đủ thông tin. Việc ghi lại giúp nhóm chủ động kiểm chứng và đánh giá hậu quả nếu nhận định đó sai.

Một bản ghi giả định nên có các thông tin sau:

| Trường | Nội dung cần ghi |
|---|---|
| Mã định danh | Mã ổn định để tham chiếu trong biên bản, mô hình và công việc tiếp theo |
| Phát biểu giả định | Một câu rõ ràng, có thể kiểm chứng hoặc bác bỏ |
| Phạm vi | Quy trình, loại giao dịch, kênh, đơn vị hoặc điều kiện mà giả định áp dụng |
| Cơ sở ban đầu | Lý do nhóm hình thành giả định và nguồn thông tin ban đầu |
| Phần mô hình bị ảnh hưởng | Thuật ngữ, quy tắc, trạng thái, entity, aggregate, domain event hoặc bounded context liên quan |
| Rủi ro nếu sai | Hệ quả đối với quy trình, dữ liệu, khách hàng hoặc thiết kế hệ thống |
| Cách kiểm chứng | Phỏng vấn, quan sát, kiểm tra hồ sơ, đối chiếu chính sách hoặc thử nghiệm phù hợp |
| Người phụ trách | Người theo dõi việc xác minh |
| Trạng thái và thời điểm | Trạng thái hiện tại, ngày ghi nhận và ngày xem xét gần nhất |

Có thể dùng các trạng thái như **Mới ghi nhận**, **Cần kiểm chứng**, **Đã xác nhận trong phạm vi**, **Bị bác bỏ**, **Được thay thế** và **Hết hiệu lực**. Tên trạng thái có thể điều chỉnh theo quy trình của nhóm, nhưng cần phân biệt rõ “đã xác nhận” với “chưa có ai phản đối”. Im lặng không phải bằng chứng xác nhận.

Khi xác nhận một giả định, hãy lưu lại bằng chứng và phạm vi mà kết luận áp dụng. Ví dụ, “đã xác nhận với đơn giao từ kho trung tâm theo chính sách hiện hành” không đồng nghĩa quy tắc đó đúng cho đơn từ cửa hàng hoặc cho chính sách trong tương lai.

Khi bác bỏ, không nên xóa dấu vết cũ. Ghi lại lý do, bằng chứng dẫn đến thay đổi và nhận định mới nếu có. Lịch sử này giúp đội phát triển hiểu tại sao mô hình đã thay đổi và tránh đưa lại một giả định sai trong các buổi trao đổi sau.

## 4. Ghi nhận và xử lý câu hỏi mở

Câu hỏi mở nên xuất phát từ một điểm chưa rõ có ảnh hưởng đến cách hiểu nghiệp vụ, quyết định hoặc mô hình. Câu hỏi tốt thường đủ hẹp để người phù hợp có thể trả lời, đồng thời đủ bối cảnh để tránh câu trả lời chung chung.

Ví dụ, thay vì hỏi “Quy trình giao hàng hoạt động thế nào?”, hãy tách thành các câu hỏi:

- Thời điểm nào được xem là đơn hàng đã bàn giao cho đơn vị vận chuyển?
- Ai có quyền thay đổi địa chỉ sau khi kho bắt đầu đóng gói?
- Khi giao thất bại, đơn hàng được giao lại, hoàn về kho hay chuyển sang quy trình xử lý ngoại lệ?
- Trạng thái nào là căn cứ để tính phí giao hàng?

Một bản ghi câu hỏi mở nên có:

1. **Câu hỏi và bối cảnh:** điều chưa biết, quy trình liên quan và lý do cần câu trả lời.
2. **Ảnh hưởng:** quy tắc, thuật ngữ, luồng công việc hoặc quyết định thiết kế có thể bị tác động.
3. **Người trả lời hoặc người quyết định:** người có hiểu biết trực tiếp hay thẩm quyền về vấn đề đó.
4. **Thông tin cần thu thập:** hồ sơ, dữ liệu, quan sát hoặc ý kiến từ những vai trò nào.
5. **Hành động tiếp theo:** lịch trao đổi, trường hợp cần quan sát hoặc tài liệu cần đối chiếu.
6. **Kết quả:** câu trả lời, bằng chứng liên quan, quyết định đã thống nhất và ngày xem xét.

Có thể phân loại câu hỏi theo chủ đề để điều phối: thuật ngữ nghiệp vụ, quy tắc và điều kiện, luồng công việc, ngoại lệ, quyền quyết định, dữ liệu, trách nhiệm giữa các bộ phận hoặc ranh giới hệ thống. Nếu câu trả lời phụ thuộc vào một quyết định quản trị, cần ghi rõ người có quyền quyết định; đội phát triển không nên tự quyết định thay doanh nghiệp.

Không phải câu hỏi nào cũng cần được giải quyết ngay. Hãy ưu tiên theo mức độ ảnh hưởng và thời điểm cần câu trả lời. Câu hỏi liên quan đến bất biến nghiệp vụ hoặc ranh giới dữ liệu có thể cần được giải quyết trước khi thiết kế aggregate. Câu hỏi về một báo cáo ít quan trọng có thể được hoãn nếu chưa ảnh hưởng đến phạm vi hiện tại. Khi hoãn, ghi rõ lý do và điều kiện khiến câu hỏi cần được mở lại.

## 5. Thu thập và đánh giá bằng chứng

Bằng chứng có thể đến từ nhiều nguồn. Mỗi nguồn cho thấy một khía cạnh khác nhau của nghiệp vụ:

| Nguồn | Có thể giúp xác minh | Giới hạn cần lưu ý |
|---|---|---|
| Quan sát công việc thực tế | Trình tự thao tác, cách xử lý ngoại lệ, điểm bàn giao giữa vai trò | Một ca quan sát có thể không đại diện cho mọi ca hoặc mọi chi nhánh |
| Phỏng vấn chuyên gia và người vận hành | Mục đích, quy tắc được hiểu, lý do của quyết định và các trường hợp ít gặp | Trí nhớ, góc nhìn vai trò và cách dùng thuật ngữ có thể khác nhau |
| Chính sách, hợp đồng, quy trình được phê duyệt | Quy định chính thức, trách nhiệm và giới hạn được công bố | Tài liệu có thể cũ hoặc không phản ánh thực tế vận hành |
| Hồ sơ giao dịch và dữ liệu hệ thống | Tần suất, trạng thái, ngoại lệ và trình tự đã xảy ra | Dữ liệu chỉ phản ánh những gì hệ thống ghi nhận; cách ghi nhận có thể thiếu hoặc sai |
| Nhật ký, thông điệp tích hợp và audit log | Thời điểm, sự kiện và trao đổi giữa các hệ thống | Cần hiểu ngữ nghĩa kỹ thuật và giới hạn lưu trữ của log |
| Prototype hoặc thử nghiệm quy trình | Phản hồi với một cách xử lý hoặc quy tắc đề xuất | Phản hồi trong môi trường thử nghiệm không tự động chứng minh hành vi thực tế |

Không có một thứ bậc nguồn bằng chứng đúng cho mọi tình huống. Tài liệu chính sách có thể là nguồn quyết định khi câu hỏi liên quan đến quy định đã phê duyệt; quan sát thực tế có thể hữu ích hơn khi tìm hiểu công việc đang diễn ra; dữ liệu giao dịch có thể cho thấy tần suất nhưng không giải thích động cơ. Hãy chọn nguồn phù hợp với câu hỏi và ghi rõ giới hạn của nguồn đó.

Một bản ghi bằng chứng nên cho phép người khác truy lại và đánh giá độc lập. Tối thiểu cần có:

- **Mã và loại bằng chứng:** mã tham chiếu ổn định, nguồn là quan sát, phỏng vấn, tài liệu, dữ liệu hay thử nghiệm.
- **Nguồn gốc:** tài liệu nào, hệ thống nào, vai trò nào hoặc buổi trao đổi nào cung cấp thông tin.
- **Thời điểm và phạm vi:** ngày thu thập, khoảng thời gian dữ liệu, đơn vị hoặc nhóm giao dịch được xem xét.
- **Nội dung quan sát:** trích đoạn ngắn hoặc tóm tắt trung thực, tách biệt với diễn giải của nhóm.
- **Liên kết:** giả định hoặc câu hỏi nào được bằng chứng này hỗ trợ, thách thức hay làm rõ.
- **Giới hạn:** dữ liệu thiếu, mẫu nhỏ, nguồn chưa được phê duyệt, chính sách có thể đã thay đổi hoặc góc nhìn chỉ đại diện cho một vai trò.

Nếu bằng chứng chứa dữ liệu khách hàng hoặc thông tin nhạy cảm, chỉ lưu phần tối thiểu cần thiết và tuân thủ quyền truy cập, chính sách bảo mật của tổ chức. Trong tài liệu discovery, mã tham chiếu đến hồ sơ có kiểm soát thường phù hợp hơn việc sao chép dữ liệu cá nhân.

### Đối chiếu nhiều nguồn

Một lời xác nhận trong cuộc phỏng vấn có thể là điểm khởi đầu, nhưng các quy tắc quan trọng nên được đối chiếu với nguồn khác khi có thể. Ví dụ, chuyên gia nói rằng mọi đơn hàng đều được giữ chỗ tồn kho trước khi xác nhận. Nhóm có thể kiểm tra quy trình được phê duyệt, quan sát một số ca xử lý và đối chiếu các giao dịch có ngoại lệ.

Khi nguồn thông tin mâu thuẫn, đừng vội chọn nguồn thuận tiện nhất. Hãy xác định chúng đang nói về cùng phạm vi và thời điểm hay không. Có thể một người mô tả chính sách chuẩn, người khác mô tả cách xử lý ngoại lệ, còn dữ liệu phản ánh một phiên bản quy trình cũ. Nếu mâu thuẫn vẫn còn, giữ câu hỏi ở trạng thái mở và ghi rõ điều cần được quyết định.

Việc không tìm thấy một trường hợp trong tập dữ liệu không chứng minh trường hợp đó không thể xảy ra. Tương tự, một trường hợp ngoại lệ đơn lẻ không nhất thiết làm mất hiệu lực của quy tắc chung. Cần xem xét độ đại diện của mẫu, điều kiện phát sinh và ý nghĩa nghiệp vụ của ngoại lệ.

## 6. Ví dụ: khám phá quy tắc xác nhận đơn hàng

Ví dụ sau là tình huống minh họa trong một doanh nghiệp bán hàng trực tuyến. Các hồ sơ và phát biểu được nêu ra chỉ nhằm minh họa cách ghi nhận, không phải dữ liệu của một doanh nghiệp cụ thể.

Trong buổi discovery, nhóm nghe nhận định: “Đơn hàng chỉ được xác nhận khi kho giữ được hàng”. Nếu ghi ngay câu này thành quy tắc cố định, đội phát triển có thể thiết kế trạng thái đơn hàng và luồng tích hợp dựa trên một hiểu biết chưa đầy đủ.

Nhóm ghi nhận ban đầu như sau:

| Mã | Loại | Nội dung | Trạng thái ban đầu |
|---|---|---|---|
| A-01 | Giả định | Đơn hàng chỉ được xác nhận sau khi yêu cầu giữ chỗ tồn kho thành công | Cần kiểm chứng |
| Q-01 | Câu hỏi mở | Nếu chỉ giữ được một phần số lượng, doanh nghiệp có cho phép xác nhận và giao một phần đơn không? | Mở |
| Q-02 | Câu hỏi mở | Khi khách hàng hủy đơn, thời điểm nào tồn kho được giải phóng? | Mở |
| Q-03 | Câu hỏi mở | Giữ chỗ tồn kho có thời hạn không, và ai xử lý khi hết thời hạn? | Mở |

Trong các buổi tiếp theo, giả sử nhóm thu thập được những thông tin minh họa sau:

| Mã | Bằng chứng minh họa | Ý nghĩa đối với việc khám phá |
|---|---|---|
| E-01 | Quan sát một số giao dịch cho thấy đơn chỉ chuyển sang trạng thái xác nhận sau khi kho trả kết quả giữ chỗ thành công | Ủng hộ A-01 trong phạm vi các giao dịch đã quan sát; chưa đủ để kết luận cho mọi loại đơn |
| E-02 | Quy trình vận hành đã phê duyệt cho phép giao một phần nếu khách hàng đồng ý | Cho thấy giả định “thiếu một phần thì từ chối toàn bộ” sẽ không phù hợp; cần làm rõ cách lưu lựa chọn của khách hàng |
| E-03 | Nhật ký của một nhóm giao dịch thể hiện yêu cầu giữ chỗ có thể hết hạn và được giải phóng | Làm phát sinh quy tắc về thời hạn giữ chỗ và xử lý khi hết hạn; cần xác minh thời hạn áp dụng |

Sau khi đối chiếu, nhóm có thể cập nhật A-01 thành “Đã xác nhận trong phạm vi loại đơn và quy trình đã kiểm tra”, đồng thời giữ Q-03 mở cho đến khi thời hạn và ngoại lệ được xác minh. Q-01 có thể được trả lời bằng chính sách giao một phần, nhưng vẫn cần làm rõ ai ghi nhận sự đồng ý và điều gì xảy ra nếu khách hàng từ chối.

Những phát hiện này ảnh hưởng trực tiếp đến mô hình. Nhóm có thể cần phân biệt trạng thái xử lý đơn hàng với trạng thái giữ chỗ tồn kho, bởi hai quá trình có vòng đời và điều kiện thay đổi khác nhau. Các sự kiện như `InventoryReservationConfirmed`, `InventoryReservationExpired` hoặc `OrderPartiallyAccepted` có thể là những khái niệm cần thảo luận với chuyên gia nghiệp vụ. Tên sự kiện cuối cùng phải phản ánh ngôn ngữ và ý nghĩa mà các bên thống nhất, không chỉ là tên kỹ thuật do đội phát triển đặt ra.

Ví dụ cũng cho thấy bằng chứng có thể làm rõ một quy tắc nhưng đồng thời mở ra câu hỏi mới. Discovery không kết thúc khi một ô trạng thái chuyển thành “đã xác nhận”; mô hình tiếp tục được xem xét khi xuất hiện loại giao dịch, chính sách hoặc ngoại lệ mới.

## 7. Kết nối các ghi nhận với Domain-Driven Design

Ghi nhận có giá trị khi nó giúp mô hình nghiệp vụ chính xác hơn và hỗ trợ quyết định thiết kế.

### Ngôn ngữ chung (Ubiquitous Language)

Giả định và câu hỏi mở thường bộc lộ thuật ngữ chưa rõ nghĩa. Ví dụ, “xác nhận đơn”, “giữ hàng”, “giao thành công” có thể được các vai trò hiểu khác nhau. Hãy ghi lại cách mỗi vai trò sử dụng thuật ngữ, ví dụ cụ thể và định nghĩa đã được thống nhất. Khi một thuật ngữ có nhiều nghĩa hợp lệ ở các bộ phận, không nên ép chúng thành một định nghĩa chung nếu nghiệp vụ thực sự khác nhau.

### Thiết kế chiến lược (Strategic Design)

Mâu thuẫn giữa các nhóm có thể cho thấy mỗi nhóm đang vận hành một mô hình riêng. Bộ phận bán hàng có thể xem đơn là cam kết với khách hàng, trong khi bộ phận kho xem yêu cầu giữ chỗ là một giao dịch quản lý năng lực tồn kho. Việc ghi nhận ai sở hữu quy tắc, dữ liệu và quyết định giúp nhóm nhận diện subdomain, bounded context và mối quan hệ giữa các context trong context map.

Không nên kết luận rằng hai nhóm cần hai bounded context chỉ vì họ bất đồng một lần. Cần kiểm tra xem khác biệt có ổn định, có phản ánh trách nhiệm nghiệp vụ riêng và có dẫn đến mô hình hoặc quy tắc khác nhau hay không.

### Thiết kế chiến thuật (Tactical Design)

Bằng chứng về điều kiện và ngoại lệ giúp xác định bất biến nghiệp vụ, vòng đời đối tượng và ranh giới nhất quán. Khi một quy tắc đã rõ, nhóm mới có cơ sở thảo luận quy tắc đó thuộc aggregate nào, đối tượng nào cần identity để trở thành entity, giá trị nào phù hợp với value object và hành động nào tạo domain event.

Ví dụ, nếu việc giữ chỗ có thể hết hạn độc lập với vòng đời đơn hàng, nhóm cần xem xét liệu hai quá trình có nên được mô hình hóa thành các đối tượng hoặc context riêng hay không. Bản ghi discovery cung cấp căn cứ để thảo luận; nó không tự động quyết định aggregate boundary hoặc kiến trúc.

## 8. Đưa việc ghi nhận vào hoạt động discovery

Để thông tin không thất lạc sau workshop, nhóm nên thống nhất một nơi lưu trữ có thể tìm kiếm và liên kết được với tài liệu mô hình, quyết định và công việc triển khai.

**Trong buổi trao đổi:** ghi lại cách diễn đạt của chuyên gia trước khi diễn giải; đánh dấu ngay câu nào là giả định, câu nào là câu hỏi và thông tin nào có nguồn cụ thể. Khi có bất đồng, ghi lại các góc nhìn và bối cảnh thay vì cố đạt đồng thuận bằng mọi giá.

**Sau buổi trao đổi:** người điều phối tổng hợp các ghi nhận, kiểm tra lại cách diễn đạt với người tham gia khi cần, gắn người phụ trách và lên kế hoạch thu thập bằng chứng. Những điểm có thể ảnh hưởng đến mô hình hoặc quyết định kỹ thuật nên được liên kết đến sơ đồ, glossary, event storming hoặc tài liệu thiết kế liên quan.

**Trong quá trình làm rõ:** cập nhật trạng thái ngay khi có bằng chứng mới. Nếu bằng chứng thay đổi kết luận, ghi lại điều gì đã thay đổi và mô hình nào cần được xem xét. Không chỉ cập nhật bảng theo dõi mà bỏ quên sơ đồ, quy tắc hoặc ví dụ đang được đội sử dụng.

**Trong các buổi rà soát định kỳ:** xem lại câu hỏi quá hạn, giả định có rủi ro cao, bằng chứng đã cũ và các kết luận bị ảnh hưởng bởi thay đổi chính sách. Khi phạm vi dự án thay đổi, đánh giá lại những ghi nhận trước đó có còn áp dụng hay không.

Một mẫu theo dõi đơn giản có thể dùng bảng với các cột `ID`, `Loại`, `Nội dung`, `Phạm vi`, `Nguồn/Bằng chứng`, `Ảnh hưởng đến mô hình`, `Người phụ trách`, `Trạng thái`, `Hành động tiếp theo` và `Ngày rà soát`. Với dự án lớn, có thể tách thành các danh sách riêng cho giả định, câu hỏi và bằng chứng, nhưng cần giữ liên kết bằng mã định danh.

### Mẫu ghi nhận có thể tái sử dụng

```yaml
assumption:
  id: A-001
  statement: "Đơn hàng chỉ được xác nhận sau khi giữ chỗ tồn kho thành công."
  scope: "Đơn giao từ kho trung tâm"
  rationale: "Nhận định từ buổi trao đổi với vận hành"
  affected_concepts:
    - "Trạng thái đơn hàng"
    - "Giữ chỗ tồn kho"
  risk_if_wrong: "Luồng xác nhận đơn có thể từ chối các trường hợp được phép giao một phần."
  owner: "Người phụ trách discovery"
  validation: "Đối chiếu quy trình và hồ sơ giao dịch có ngoại lệ"
  status: "Cần kiểm chứng"
  recorded_at: "YYYY-MM-DD"

open_question:
  id: Q-001
  question: "Doanh nghiệp xử lý thế nào khi chỉ giữ chỗ được một phần số lượng?"
  context: "Quy tắc xác nhận đơn hàng"
  decision_owner: "Chuyên gia nghiệp vụ phụ trách đơn hàng"
  affected_rules:
    - "Điều kiện xác nhận đơn"
    - "Xử lý giao một phần"
  next_action: "Trao đổi với vận hành và kiểm tra hồ sơ thực tế"
  status: "Mở"

evidence:
  id: E-001
  type: "Quan sát giao dịch"
  source: "Hồ sơ giao dịch đã được phép kiểm tra"
  collected_at: "YYYY-MM-DD"
  scope: "Nhóm đơn giao từ kho trung tâm trong khoảng thời gian đã chọn"
  observation: "Ghi lại trình tự trạng thái quan sát được"
  supports:
    - "A-001"
  contradicts: []
  limitations: "Mẫu quan sát chưa bao phủ mọi loại đơn"
```

Đây là mẫu khởi đầu, không phải một schema bắt buộc. Nhóm có thể bổ sung trường phù hợp với quy trình, miễn là vẫn truy được nguồn, phạm vi, trạng thái và mối liên hệ giữa nhận định với bằng chứng.

## 9. Những sai lầm thường gặp

- **Biến giả định thành yêu cầu:** câu nói chưa kiểm chứng được đưa thẳng vào backlog hoặc code. Hãy giữ trạng thái giả định và chỉ chuyển thành quy tắc sau khi có xác nhận phù hợp.
- **Ghi câu hỏi quá rộng:** câu hỏi không chỉ ra quyết định hoặc phần mô hình bị ảnh hưởng sẽ khó được trả lời. Hãy tách thành câu hỏi nhỏ, có bối cảnh và người phụ trách.
- **Chỉ ghi kết luận, bỏ nguồn:** người đọc sau này không thể biết kết luận dựa trên phỏng vấn, chính sách hay dữ liệu. Hãy lưu nguồn và giới hạn của bằng chứng.
- **Coi ý kiến của một cá nhân là quy tắc toàn doanh nghiệp:** cần xác định vai trò, phạm vi thẩm quyền và những nhóm có thể có cách xử lý khác.
- **Bỏ qua trường hợp ngoại lệ:** ngoại lệ có thể chỉ ra điều kiện biên, quy tắc ưu tiên hoặc một quy trình khác. Hãy ghi nhận và tìm hiểu tần suất cùng ý nghĩa của nó.
- **Đóng câu hỏi vì đã có câu trả lời:** câu trả lời cần được kiểm tra về phạm vi, thẩm quyền và bằng chứng hỗ trợ. Nếu chưa đủ, hãy ghi trạng thái tạm thời.
- **Không xem lại ghi nhận cũ:** mô hình có thể tiếp tục dựa vào chính sách đã hết hiệu lực. Hãy gắn thời điểm và rà soát khi có thay đổi liên quan.
- **Tạo quá nhiều thủ tục:** biểu mẫu dài nhưng không phục vụ quyết định sẽ khiến mọi người ngừng cập nhật. Chỉ giữ các trường giúp hiểu, kiểm chứng và truy vết thông tin.

## 10. Kiểm tra chất lượng trước khi dùng kết quả discovery

Trước khi dùng một kết luận để điều chỉnh domain model hoặc tạo quyết định thiết kế, nhóm có thể tự kiểm tra:

- Giả định có được viết thành nhận định cụ thể, có phạm vi và cách kiểm chứng không?
- Câu hỏi mở có chỉ ra điều chưa biết, người phụ trách và hành động tiếp theo không?
- Bằng chứng có nguồn, thời điểm, phạm vi và giới hạn rõ ràng không?
- Nhóm đã tìm kiếm trường hợp trái chiều hoặc ngoại lệ có liên quan chưa?
- Kết luận có được người có thẩm quyền nghiệp vụ xác nhận trong phạm vi phù hợp không?
- Thuật ngữ và quy tắc đã được phản ánh nhất quán trong glossary, sơ đồ và tài liệu mô hình chưa?
- Những phần còn chưa chắc chắn có được giữ lại để tiếp tục theo dõi không?

Không cần chờ mọi câu hỏi được giải quyết mới có thể tiếp tục discovery hoặc phát triển. Điều quan trọng là nhóm biết rõ mức độ chắc chắn của từng phần mô hình, hiểu rủi ro khi một giả định sai và chủ động quay lại kiểm chứng khi có thêm thông tin.

Một domain model tốt không chỉ thể hiện điều nhóm đang tin là đúng. Nó còn cho thấy vì sao nhóm tin như vậy, điều gì vẫn cần xác minh và bằng chứng nào sẽ khiến nhóm thay đổi cách hiểu. Khi những thông tin này được ghi nhận minh bạch và cập nhật thường xuyên, chuyên gia nghiệp vụ và đội phát triển có cơ sở chung để học hỏi, tranh luận và tiến dần đến một mô hình phản ánh đúng nghiệp vụ.
