# Duy trì đối thoại thường xuyên với chuyên gia nghiệp vụ

Domain-Driven Design (DDD) bắt đầu từ hiểu biết về nghiệp vụ. Đội phát triển cần biết tổ chức đang cố gắng đạt mục tiêu gì, ai đưa ra quyết định, quy tắc nào chi phối công việc và những ngoại lệ nào thường xảy ra. Những hiểu biết này không thể được suy ra đầy đủ từ tên bảng, API hoặc tài liệu yêu cầu đã viết từ trước. Chúng cần được khám phá và kiểm chứng qua đối thoại với những người thực sự hiểu công việc.

Đối thoại với chuyên gia nghiệp vụ không phải một cuộc phỏng vấn diễn ra ở đầu dự án rồi kết thúc khi tài liệu được ký duyệt. Quy tắc thay đổi, thị trường thay đổi, nhân viên phát hiện ngoại lệ mới và mô hình phần mềm cũng làm lộ ra những câu hỏi trước đây chưa ai đặt ra. Vì vậy, DDD cần một vòng trao đổi liên tục: cùng quan sát ví dụ, đặt câu hỏi, xây mô hình, thử mô hình bằng tình huống thực tế và cập nhật cách hiểu khi có bằng chứng mới.

Bài học này trình bày cách thiết lập nhịp cộng tác bền vững giữa đội phát triển và chuyên gia nghiệp vụ, từ chuẩn bị buổi trao đổi, khám phá ngôn ngữ chung, xác thực quy tắc, ghi nhận quyết định cho đến duy trì tài liệu sống. Mục tiêu là giúp mô hình phần mềm phản ánh đúng cách tổ chức vận hành và có thể tiến hóa khi hiểu biết nghiệp vụ thay đổi.

Sau bài học, người học có thể:

- giải thích vì sao đối thoại với chuyên gia phải diễn ra xuyên suốt vòng đời phát triển;
- chọn đúng người tham gia theo quyết định và phạm vi nghiệp vụ cần khám phá;
- chuẩn bị và điều phối buổi trao đổi bằng ví dụ cụ thể;
- dùng Event Storming, Example Mapping và Domain Storytelling đúng mục đích;
- phát hiện thuật ngữ mơ hồ, từ đồng âm khác nghĩa và khác biệt giữa các Bounded Context;
- kiểm chứng Entity, Value Object, Aggregate, Domain Event và quy tắc nghiệp vụ bằng tình huống thực;
- ghi lại giả định, quyết định, câu hỏi mở và thay đổi mô hình;
- thiết lập vòng phản hồi để tài liệu và phần mềm cùng phản ánh hiểu biết mới.

## 1. Đối thoại là hoạt động cốt lõi của DDD

DDD xem mô hình miền là kết quả cộng tác giữa người hiểu nghiệp vụ và người xây dựng phần mềm. Chuyên gia nghiệp vụ biết mục tiêu, quy trình, ngoại lệ và cách tổ chức đánh đổi giữa các mục tiêu. Nhà phát triển biết cách biểu diễn những quy tắc đó thành mô hình, kiểm soát tính nhất quán và tổ chức hệ thống. Mỗi bên có kiến thức mà bên kia không thể tự thay thế.

Nếu đội phát triển chỉ nhận yêu cầu qua tài liệu hoặc qua một người trung gian, nhiều chi tiết có thể bị mất:

- Một từ được dùng trong nhiều nghĩa nhưng tài liệu chỉ ghi một định nghĩa.
- Quy tắc chỉ tồn tại trong kinh nghiệm của nhân viên lâu năm.
- Ngoại lệ được xử lý bằng thao tác thủ công nên không xuất hiện trong sơ đồ quy trình.
- Hai phòng ban mô tả cùng một khách hàng nhưng có quyền và trách nhiệm khác nhau.
- Một điều kiện pháp lý hoặc chính sách có ngày hiệu lực riêng mà hệ thống hiện tại chưa biểu diễn.

Đối thoại giúp phát hiện những khoảng trống đó trước khi chúng trở thành giả định trong code.

### Đối thoại không chỉ để thu thập yêu cầu

Một cuộc trao đổi tốt có thể làm thay đổi cả cách hiểu bài toán. Nhà phát triển đưa ra một mô hình ban đầu; chuyên gia nghiệp vụ dùng ví dụ thực tế để xác nhận hoặc phản bác; hai bên điều chỉnh thuật ngữ và quy tắc. Đây là quá trình khám phá, không phải thủ tục lấy chữ ký cho một thiết kế đã hoàn thành.

~~~mermaid
flowchart LR
    A[Quan sát công việc và ví dụ] --> B[Đặt câu hỏi]
    B --> C[Hình thành ngôn ngữ và mô hình]
    C --> D[Thử bằng tình huống thực]
    D --> E{Chuyên gia xác nhận?}
    E -->|Có| F[Ghi nhận quyết định và áp dụng]
    E -->|Chưa| B
    F --> G[Quan sát kết quả trong phần mềm]
    G --> A
~~~

Mô hình chỉ đáng tin khi nó tiếp tục giải thích được những tình huống thật. Nếu chuyên gia phải thường xuyên nói “trường hợp đó không giống cách chúng tôi làm”, mô hình cần được xem xét lại.

## 2. Chọn đúng chuyên gia cho đúng câu hỏi

Không có một người duy nhất hiểu mọi khía cạnh của một domain lớn. Một nhân viên bán hàng có thể hiểu cách tư vấn và chốt đơn; nhân viên kho hiểu giữ hàng và xuất hàng; kế toán hiểu ghi nhận doanh thu; nhân viên hỗ trợ hiểu khiếu nại và hoàn tiền. Mỗi người có góc nhìn và quyền quyết định khác nhau.

### Phân biệt các vai trò

| Vai trò | Kiến thức thường đóng góp | Câu hỏi cần làm rõ |
|---|---|---|
| Domain Expert | Quy tắc, thuật ngữ và quyết định trong một lĩnh vực | Ai có quyền xác nhận quy tắc này? |
| End User / Operator | Cách công việc diễn ra hằng ngày | Thực tế bạn làm gì khi tình huống này xảy ra? |
| Process Owner | Trách nhiệm và kết quả của quy trình | Ai chịu trách nhiệm khi quy trình thất bại? |
| Policy / Compliance Specialist | Ràng buộc chính sách, pháp lý và kiểm soát | Quy tắc nào bắt buộc, có hiệu lực từ khi nào? |
| Product Owner / Business Analyst | Mục tiêu, ưu tiên và phạm vi sản phẩm | Kết quả nào có giá trị cao nhất trong giai đoạn này? |
| Developer / Domain Modeler | Mô hình, tính nhất quán và khả năng thực thi | Quy tắc này thuộc context và đối tượng nào? |
| Facilitator | Giữ cuộc trao đổi tập trung và bảo đảm mọi góc nhìn được lắng nghe | Chúng ta đã xác định rõ điều chưa thống nhất chưa? |

Một người có thể giữ nhiều vai trò, nhưng không nên mặc định người có chức danh cao nhất là người hiểu mọi thao tác chi tiết. Khi câu hỏi liên quan đến công việc thực tế, hãy nói chuyện với người trực tiếp thực hiện. Khi câu hỏi liên quan đến chính sách, cần người có thẩm quyền xác nhận.

### Xây bản đồ người cần tham gia

Với mỗi chủ đề, xác định:

- Ai thực hiện công việc?
- Ai chịu trách nhiệm kết quả?
- Ai phê duyệt ngoại lệ?
- Ai bị ảnh hưởng bởi quyết định?
- Ai sở hữu dữ liệu hoặc quy tắc?
- Ai có thể cung cấp ví dụ lịch sử đáng tin cậy?

Ví dụ, quy tắc hủy đơn có thể cần đại diện chăm sóc khách hàng, vận hành kho, thanh toán và người sở hữu chính sách hoàn tiền. Nếu chỉ trao đổi với nhân viên chăm sóc khách hàng, đội có thể bỏ sót thời điểm kho đã bàn giao hàng hoặc khoản thanh toán đã được capture.

### Không biến chuyên gia thành người duyệt mọi chi tiết kỹ thuật

Chuyên gia nghiệp vụ cần xác nhận ý nghĩa và chính sách nghiệp vụ. Họ không cần phê duyệt tên class, cấu trúc package hoặc cách triển khai repository nếu các quyết định đó không làm thay đổi quy tắc. Đội phát triển chịu trách nhiệm lựa chọn kỹ thuật và phải giải thích hệ quả nghiệp vụ khi lựa chọn đó ảnh hưởng đến người dùng hoặc quy trình.

## 3. Duy trì nhịp đối thoại thay vì tổ chức một buổi kickoff duy nhất

Nhịp cộng tác cần phù hợp với độ phức tạp và mức độ thay đổi của domain. Một số câu hỏi có thể được giải quyết trong một buổi workshop; những quy tắc khác chỉ lộ ra sau khi có prototype hoặc khi người dùng thử luồng mới.

Một nhịp tham khảo:

| Nhịp | Hoạt động | Kết quả mong đợi |
|---|---|---|
| Hằng tuần hoặc theo iteration | Review ví dụ mới, quy tắc chưa rõ và thay đổi của mô hình | Câu hỏi được giải quyết trước khi code đi quá xa |
| Trước một capability lớn | Workshop khám phá quy trình và ranh giới context | Bức tranh nghiệp vụ và các quyết định quan trọng |
| Trong khi phát triển | Trao đổi ngắn khi gặp trường hợp chưa được mô hình giải thích | Giảm giả định và làm rõ acceptance criteria |
| Khi có thay đổi chính sách | Phiên xác nhận tác động và ngày hiệu lực | Quyết định cập nhật được ghi nhận |
| Sau khi đưa tính năng vào sử dụng | Quan sát phản hồi, lỗi vận hành và thao tác thủ công | Phát hiện khoảng cách giữa model và thực tế |

Đây là gợi ý, không phải lịch cứng. Một nhóm có thể tổ chức office hour mỗi tuần, trao đổi bất đồng bộ hằng ngày và workshop sâu mỗi tháng. Điều quan trọng là câu hỏi có đường đến người trả lời và quyết định có đường quay lại mô hình, test và tài liệu.

### Đưa câu hỏi đến đúng thời điểm

Không nên đợi đến cuối iteration mới hỏi một quy tắc có thể làm thay đổi thiết kế. Khi phát hiện một điểm chưa rõ, hãy ghi lại ngay với:

- tình huống đã quan sát;
- câu hỏi cần xác nhận;
- quyết định nào đang bị chặn;
- người có thể trả lời;
- thời điểm cần câu trả lời;
- hệ quả nếu tạm thời dùng một giả định.

Câu hỏi rõ giúp chuyên gia chuẩn bị câu trả lời mà không cần đọc toàn bộ code hoặc tài liệu kỹ thuật.

## 4. Chuẩn bị một buổi trao đổi có mục tiêu

Một buổi họp không nên bắt đầu bằng câu “Anh/chị hãy mô tả toàn bộ nghiệp vụ”. Phạm vi quá rộng khiến người tham gia kể nhiều thông tin nhưng nhóm khó chuyển thành quyết định cụ thể.

### Trước buổi trao đổi

Người điều phối nên chuẩn bị:

1. **Mục tiêu:** sau buổi này cần hiểu hoặc quyết định điều gì?
2. **Phạm vi:** quy trình, vai trò hoặc tình huống nào sẽ được thảo luận?
3. **Người tham gia:** ai có trải nghiệm hoặc thẩm quyền phù hợp?
4. **Ví dụ:** một giao dịch thật đã hoàn thành, một trường hợp thất bại và một ngoại lệ.
5. **Câu hỏi:** các điểm mơ hồ hoặc giả định cần kiểm tra.
6. **Artifact:** sơ đồ, event list, model sketch hoặc acceptance example đủ để mọi người cùng nhìn.
7. **Đầu ra:** quyết định, câu hỏi mở, owner và thời hạn xử lý.

### Agenda mẫu cho phiên 60 phút

| Thời lượng | Hoạt động |
|---:|---|
| 5 phút | Nêu mục tiêu và phạm vi |
| 10 phút | Chuyên gia kể một tình huống thực tế từ đầu đến cuối |
| 15 phút | Làm rõ quyết định, điều kiện và ngoại lệ |
| 15 phút | Cùng vẽ quy trình, event hoặc model |
| 10 phút | Thử mô hình với một tình huống khác |
| 5 phút | Đọc lại kết luận, câu hỏi mở và người chịu trách nhiệm |

Nếu chủ đề cần khám phá sâu hơn, hãy chia thành nhiều phiên có mục tiêu nhỏ. Không cần cố hoàn tất mọi quyết định trong một cuộc họp.

### Bắt đầu từ một trường hợp cụ thể

Thay vì hỏi “Quy trình hoàn tiền hoạt động thế nào?”, hãy hỏi:

- “Hãy kể về lần hoàn tiền gần nhất.”
- “Ai đã yêu cầu hoàn tiền?”
- “Điều gì khiến yêu cầu được chấp nhận?”
- “Hàng đã được giao chưa?”
- “Tiền đã được capture hay chỉ authorize?”
- “Ai xác nhận số tiền được hoàn?”
- “Có trường hợp nào một phần tiền được hoàn không?”
- “Khách được thông báo ở thời điểm nào?”

Một câu chuyện cụ thể thường làm lộ ra nhiều quy tắc hơn một mô tả chung chung.

## 5. Hỏi để khám phá quy tắc, không chỉ ghi lại câu trả lời

Câu hỏi tốt mở ra tình huống và quyết định. Câu hỏi đóng có thể hữu ích để xác nhận, nhưng nếu dùng quá sớm, người trả lời chỉ chọn Có/Không mà không giải thích ngữ cảnh.

### Nhóm câu hỏi nên dùng

| Nhóm | Ví dụ |
|---|---|
| Quy trình | Điều gì xảy ra trước và sau bước này? |
| Tác nhân | Ai khởi tạo, ai phê duyệt, ai chịu trách nhiệm? |
| Điều kiện | Khi nào thao tác được phép hoặc bị từ chối? |
| Ngoại lệ | Lần gần nhất quy trình không diễn ra như thường lệ là khi nào? |
| Thời gian | Thời điểm nào quyết định hạn, ngày hiệu lực hoặc cut-off? |
| Dữ liệu | Giá trị nào cần giữ nguyên để giải thích giao dịch? |
| Ownership | Ai có quyền sửa hoặc xác nhận thông tin này? |
| Ranh giới | Bộ phận khác dùng từ này với cùng ý nghĩa không? |
| Mức độ ưu tiên | Nếu không thể đáp ứng mọi điều kiện, điều gì quan trọng nhất? |
| Bằng chứng | Có hồ sơ, ví dụ hoặc báo cáo nào thể hiện tình huống này? |

### Dùng câu hỏi “điều gì xảy ra nếu…”

Các câu hỏi giả định giúp thử độ bền của quy tắc:

- Nếu khách yêu cầu hủy sau khi kho đã đóng gói thì sao?
- Nếu thanh toán được xác nhận nhưng phản hồi đến muộn thì sao?
- Nếu một phần đơn hàng đã giao thì chính sách hoàn tiền áp dụng thế nào?
- Nếu khách đổi địa chỉ sau khi tạo nhãn vận chuyển thì sao?
- Nếu hai nhân viên cùng xử lý một yêu cầu thì ai có quyền quyết định?

Mục tiêu không phải tạo ra mọi tình huống tưởng tượng. Hãy chọn những trường hợp có khả năng xảy ra hoặc hậu quả lớn.

### Hỏi về lý do và mục đích

Một quy tắc chỉ được mô tả bằng câu “hệ thống phải làm vậy” có thể chưa đủ. Hãy hỏi tại sao:

- Vì luật hoặc hợp đồng yêu cầu?
- Vì giới hạn của nhà cung cấp?
- Vì giảm rủi ro gian lận?
- Vì chính sách dịch vụ?
- Vì thao tác vận hành hiện tại?

Biết lý do giúp phân biệt invariant bắt buộc với quy ước có thể thay đổi. Nó cũng giúp đội đánh giá tác động khi chính sách thay đổi.

## 6. Kể chuyện nghiệp vụ và Event Storming

Domain Storytelling và Event Storming là hai kỹ thuật hữu ích để nhiều vai trò cùng nhìn vào một quy trình. Chúng không thay thế đối thoại; chúng tạo một bề mặt chung để đối thoại cụ thể hơn.

### Domain Storytelling

Người tham gia kể một quy trình theo góc nhìn của tác nhân:

- Ai thực hiện hành động?
- Họ làm gì?
- Họ tác động lên đối tượng nào?
- Thông tin nào được tạo hoặc sử dụng?
- Điều gì xảy ra tiếp theo?

Ví dụ:

~~~text
Khách hàng
   |
   | gửi yêu cầu đặt hàng
   v
Nhân viên bán hàng
   |
   | kiểm tra điều kiện bán
   v
Đơn hàng
   |
   | yêu cầu giữ hàng
   v
Nhân viên kho
   |
   | xác nhận số lượng được giữ
   v
Đơn hàng được xác nhận
~~~

Sau khi vẽ, hãy hỏi chuyên gia về ngoại lệ: thiếu hàng, khách thay đổi yêu cầu, đơn bị giữ để kiểm tra hoặc kho không phản hồi.

### Event Storming

Event Storming thường bắt đầu từ các sự kiện nghiệp vụ đã xảy ra, dùng tên ở dạng quá khứ:

- OrderPlaced
- StockReserved
- PaymentAuthorized
- OrderConfirmed
- ShipmentDispatched
- RefundIssued

Sau đó nhóm khám phá command, actor, policy, aggregate và hệ thống bên ngoài liên quan.

~~~mermaid
flowchart LR
    A[Customer places order] --> B[OrderPlaced]
    B --> C[ReserveStock command]
    C --> D{Inventory decision}
    D -->|Available| E[StockReserved]
    D -->|Unavailable| F[StockReservationRejected]
    E --> G[RequestPayment command]
    G --> H[PaymentAuthorized]
    H --> I[OrderConfirmed]
~~~

Sơ đồ này chỉ là một giả thuyết ban đầu. Chuyên gia cần xác nhận liệu thanh toán diễn ra trước hay sau giữ hàng, trường hợp authorize thất bại được xử lý thế nào và ai chịu trách nhiệm giải phóng reservation.

### Dùng màu sắc hoặc ký hiệu để tách loại thông tin

Trong một workshop, có thể quy ước:

- Event: điều đã xảy ra.
- Command: yêu cầu thực hiện hành động.
- Actor: người hoặc hệ thống khởi tạo.
- Policy: quy tắc phản ứng với một event.
- Aggregate: nơi bảo vệ một nhóm invariant.
- External system: hệ thống ngoài ranh giới đang khảo sát.
- Hotspot: điểm chưa rõ hoặc có tranh luận.

Màu sắc chỉ giúp quan sát. Giá trị thật nằm ở câu hỏi và ví dụ được thảo luận tại từng hotspot.

## 7. Example Mapping: kiểm chứng quy tắc bằng ví dụ

Example Mapping phù hợp khi một user story hoặc use case có nhiều điều kiện. Nhóm tách:

- **Story:** mục tiêu hoặc hành vi đang được xem xét.
- **Rules:** các quy tắc chi phối hành vi.
- **Examples:** tình huống cụ thể chứng minh cách áp dụng quy tắc.
- **Questions:** điểm chưa được xác định.

Ví dụ story: “Khách có thể hủy đơn trước khi đơn được bàn giao cho đơn vị vận chuyển.”

| Loại | Nội dung |
|---|---|
| Story | Hủy đơn |
| Rule 1 | Đơn chưa bàn giao vận chuyển có thể được yêu cầu hủy |
| Example | Đơn ở trạng thái PLACED, chưa tạo shipment: hủy được |
| Rule 2 | Đơn đã bàn giao vận chuyển cần quy trình trả hàng |
| Example | Shipment đã DISPATCHED: không dùng thao tác hủy thông thường |
| Rule 3 | Nếu đã thu tiền, cần tạo yêu cầu hoàn tiền |
| Example | Payment CAPTURED: OrderCancelled và RefundRequested có thể xuất hiện |
| Question | Nếu chỉ một phần hàng đã bàn giao thì xử lý theo từng dòng hay toàn đơn? |

Nếu một story tạo ra quá nhiều rule và câu hỏi chưa giải quyết, có thể story đang quá rộng hoặc cần một phiên khám phá riêng. Không nên biến mọi câu hỏi thành acceptance criteria bằng cách tự đoán câu trả lời.

### Ví dụ giúp biến từ ngữ chung thành quy tắc kiểm thử được

“Đơn hợp lệ” là một cụm từ mơ hồ. Hãy yêu cầu ví dụ:

- Đơn có một sản phẩm hết hàng có hợp lệ không?
- Đơn có địa chỉ chưa xác minh có hợp lệ không?
- Đơn có thanh toán pending có được xác nhận không?
- Đơn có tổng tiền bằng 0 do voucher có hợp lệ không?

Mỗi câu trả lời có thể làm lộ một quy tắc, một ngoại lệ hoặc một khái niệm riêng trong model.

## 8. Xây dựng Ubiquitous Language cùng chuyên gia

Ubiquitous Language là ngôn ngữ chung được dùng nhất quán trong trao đổi nghiệp vụ, mô hình, code và tài liệu trong một Bounded Context. Nó không phải một danh sách thuật ngữ được tạo riêng bởi đội phát triển rồi gửi chuyên gia ký.

### Thuật ngữ phải được xác nhận bằng ví dụ

Giả sử nhóm dùng từ “đơn đã xác nhận”. Chuyên gia có thể hiểu đó là:

- khách đã xác nhận đặt hàng;
- kho đã giữ đủ hàng;
- thanh toán đã được authorize;
- nhân viên đã duyệt đơn.

Bốn nghĩa này dẫn đến các trạng thái và event khác nhau. Hãy hỏi “Điều gì phải đúng trước khi anh/chị gọi đơn là đã xác nhận?” và “Có thể cho ví dụ đơn đã xác nhận nhưng chưa thanh toán không?”

### Glossary cần ghi cả ngữ cảnh và ranh giới

| Thuật ngữ | Định nghĩa trong context | Ví dụ | Ghi chú |
|---|---|---|---|
| Order | Cam kết mua hàng do Sales quản lý | ORD-1001 được tạo sau checkout | Không đồng nghĩa Shipment |
| Reservation | Lượng hàng được Inventory giữ trong thời hạn | 2 sản phẩm giữ đến 15:30 | Có lifecycle riêng |
| Authorization | Khoản tiền được Payment provider cho phép thu | PAY-101 được authorize | Chưa đồng nghĩa đã capture |
| Capture | Khoản tiền được ghi nhận thu | PaymentCaptured | Có thể xảy ra sau authorization |
| Dispatch | Hàng được bàn giao cho đơn vị vận chuyển | ShipmentDispatched | Khác với tạo nhãn |

Glossary nên ghi:
- thuật ngữ chuẩn;
- định nghĩa ngắn;
- context sở hữu;
- thuật ngữ dễ nhầm;
- ví dụ và phản ví dụ;
- người xác nhận;
- ngày cập nhật nếu định nghĩa thay đổi.

### Một từ có thể có nghĩa khác ở context khác

Không cần ép toàn tổ chức dùng một định nghĩa duy nhất cho mọi từ. “Customer” trong Sales có thể là người mua và hồ sơ thương mại; trong Billing có thể là pháp nhân nhận hóa đơn; trong Support có thể là người liên hệ. Context Map cần làm rõ các quan hệ và cách chuyển đổi giữa các mô hình.

Nếu một thuật ngữ được dùng khác nhau, hãy ghi rõ phạm vi thay vì tạo một định nghĩa tổng quát làm mất khác biệt.

### Không nhầm từ viết trong code với Ubiquitous Language

Một class tên Customer không tự chứng minh model đã có ngôn ngữ chung. Điều quan trọng là chuyên gia cũng hiểu và dùng khái niệm đó với cùng ý nghĩa trong context tương ứng. Nếu code gọi là “Fulfillment” nhưng nhân viên chỉ hiểu “chuẩn bị giao hàng”, nhóm cần thảo luận xem đó là cùng một khái niệm hay có nhiều bước khác nhau.

## 9. Đối thoại để khám phá Strategic Design

Các cuộc trao đổi không chỉ giúp làm rõ field và rule của một entity. Chúng còn giúp xác định Subdomain, Bounded Context và Context Map.

### Khám phá Subdomain

Hỏi về mục tiêu và năng lực nghiệp vụ:

- Tổ chức tạo ra giá trị chính bằng hoạt động nào?
- Năng lực nào tạo khác biệt cạnh tranh?
- Hoạt động nào là cần thiết nhưng có thể mua hoặc thuê ngoài?
- Hoạt động nào có quy tắc ổn định và phổ biến?
- Nếu hoạt động này thất bại, tác động đến doanh nghiệp là gì?

Câu trả lời giúp phân biệt Core, Supporting và Generic Subdomain. Không nên phân loại chỉ dựa trên tên phòng ban hoặc sơ đồ tổ chức.

### Khám phá Bounded Context

Hỏi về sự nhất quán của ngôn ngữ và mô hình:

- Một thuật ngữ có cùng định nghĩa ở các nhóm không?
- Ai chịu trách nhiệm thay đổi quy tắc?
- Có lifecycle khác nhau cho cùng một khái niệm không?
- Một nhóm có thể thay đổi mô hình mà không cần nhóm khác phê duyệt không?
- Dữ liệu nào được trao đổi qua ranh giới và vì mục đích gì?

Dấu hiệu quan trọng của một context không chỉ là một service hay database riêng. Đó là phạm vi trong đó một mô hình và ngôn ngữ có ý nghĩa nhất quán.

### Khám phá Context Map

Khi hai context trao đổi, hỏi:

- Context nào là upstream và context nào là downstream?
- Ai kiểm soát hợp đồng tích hợp?
- Downstream có phải thích nghi với mô hình upstream không?
- Có cần Anti-Corruption Layer không?
- Có một Published Language chung không?
- Thay đổi schema được thông báo và tương thích thế nào?

Đối thoại nên tập trung vào trách nhiệm và quyền quyết định. Một sơ đồ có mũi tên nhưng không có ownership và contract thường chưa đủ để hướng dẫn thiết kế.

## 10. Đối thoại để khám phá Tactical Design

Sau khi phạm vi context rõ hơn, tiếp tục trao đổi về các khái niệm trong mô hình.

### Entity

Hỏi:

- Điều gì làm đối tượng này vẫn là cùng một đối tượng qua thời gian?
- ID được cấp khi nào?
- Có thể đổi tên hoặc đổi thuộc tính mà vẫn là cùng entity không?
- Ai có quyền tạo, sửa hoặc kết thúc lifecycle?

Ví dụ, một Order vẫn là cùng đơn hàng khi địa chỉ giao hàng thay đổi. Điều đó gợi ý identity không nên phụ thuộc vào địa chỉ.

### Value Object

Hỏi:

- Giá trị này được xác định bằng những thuộc tính nào?
- Hai giá trị bằng nhau khi nào?
- Có đơn vị, currency, precision hoặc quy tắc chuẩn hóa không?
- Giá trị có thể thay đổi sau khi tạo không?

Ví dụ, Money cần amount và currency; chỉ so sánh amount là chưa đủ.

### Aggregate và invariant

Hỏi:

- Những điều kiện nào phải luôn đúng sau một thao tác?
- Có những cập nhật nào phải được kiểm soát cùng nhau?
- Ai có quyền thay đổi trạng thái?
- Có thể chấp nhận trạng thái tạm thời không nhất quán giữa các context không?
- Một đối tượng con có thể được thay đổi độc lập không?

Ví dụ, tổng số lượng đã giữ không được vượt lượng có thể bán. Nếu Inventory chịu trách nhiệm invariant này, Order không nên tự sửa tồn kho bằng một bản sao cũ.

### Domain Event

Hỏi:

- Sự việc nào đã xảy ra và không còn là yêu cầu đang chờ?
- Ai cần biết sự việc đó?
- Sự kiện mang dữ liệu nào để consumer hiểu?
- Thời điểm xảy ra và thời điểm ghi nhận có khác nhau không?
- Có thể phát sự kiện trùng hoặc đến muộn không?

Tên event nên mô tả fact ở quá khứ, ví dụ StockReserved hoặc PaymentCaptured, thay vì tên chung như UpdateStatus.

## 11. Xác thực mô hình bằng tình huống thực tế

Một mô hình không nên được xác nhận chỉ bằng cách nhìn sơ đồ và nói “trông hợp lý”. Hãy đưa mô hình trở lại các tình huống:

1. Một trường hợp bình thường.
2. Một trường hợp biên.
3. Một trường hợp thất bại.
4. Một trường hợp ngoại lệ cần người phê duyệt.
5. Một trường hợp có thay đổi chính sách theo thời gian.

Ví dụ với quy tắc giữ hàng:

| Scenario | Câu hỏi xác thực |
|---|---|
| Đủ hàng | Inventory tạo reservation khi nào? |
| Không đủ hàng | Có giữ một phần hay từ chối toàn bộ? |
| Reservation hết hạn | Ai phát hiện và giải phóng? |
| Khách hủy đơn | Reservation được release theo command hay tự hết hạn? |
| Hai đơn cùng tranh một sản phẩm | Invariant được bảo vệ ở đâu? |

Nếu mô hình không trả lời được một scenario, ghi lại câu hỏi. Đừng lấp chỗ trống bằng một giả định không có owner.

### Dùng test như một công cụ đối thoại

Acceptance example hoặc domain test có thể giúp chuyên gia phản hồi cụ thể:

~~~text
Given Inventory có 5 đơn vị có thể bán
When hai đơn đồng thời yêu cầu giữ 4 đơn vị
Then tổng số lượng được xác nhận giữ không vượt quá 5
And ít nhất một yêu cầu phải bị từ chối hoặc chỉ được giữ một phần
~~~

Chuyên gia xác nhận phần kết quả nghiệp vụ; đội phát triển xác định cơ chế kỹ thuật bảo vệ invariant. Test làm cho thảo luận có thể lặp lại khi model thay đổi.

## 12. Ghi nhận quyết định và câu hỏi mở

Đối thoại thường tạo ra nhiều thông tin hơn những gì nhóm có thể quyết định ngay. Nếu không ghi nhận, cùng một câu hỏi sẽ được thảo luận lại và những giả định tạm thời có thể bị coi nhầm là sự thật.

### Decision Log

Một decision log có thể có cấu trúc:

| Trường | Nội dung |
|---|---|
| ID | Mã quyết định |
| Date | Ngày quyết định |
| Context | Bounded Context liên quan |
| Question | Câu hỏi cần giải quyết |
| Decision | Quyết định đã được xác nhận |
| Rationale | Lý do và bằng chứng |
| Owner | Người có thẩm quyền xác nhận |
| Consequence | Tác động đến model, workflow hoặc integration |
| Review trigger | Sự kiện khiến cần xem xét lại |

Ví dụ:

~~~text
Decision: ORD-DEC-014
Context: Order
Question: Có thể hủy đơn sau khi shipment được dispatch không?
Decision: Không dùng thao tác Cancel Order thông thường.
          Chuyển sang Return Request.
Rationale: Hàng đã được bàn giao cho carrier.
Owner: Order Operations
Consequence: Order và Return có lifecycle riêng.
Review trigger: Thay đổi hợp đồng với carrier.
~~~

Decision log nên ghi cả lý do và điều kiện xem xét lại. Một quyết định có thể đúng trong chính sách hiện tại nhưng không phải chân lý vĩnh viễn.

### Assumption Log

Nếu chưa có câu trả lời, ghi rõ giả định:

~~~text
ASSUMPTION: Reservation hết hạn sau 15 phút.
STATUS: Chưa được Inventory Owner xác nhận.
IMPACT: Checkout có thể báo hết hàng sớm hoặc giữ hàng quá lâu.
OWNER TO CONFIRM: Inventory Operations.
REVIEW BY: Trước khi hoàn tất luồng checkout.
~~~

Giả định phải có trạng thái và owner. Khi được xác nhận, chuyển nó thành quyết định hoặc rule. Khi bị bác bỏ, cập nhật model và test liên quan.

### Phân biệt decision, assumption và open question

- Decision: đã được người có thẩm quyền xác nhận.
- Assumption: tạm dùng để tiếp tục nhưng chưa có bằng chứng đủ.
- Open question: câu hỏi chưa có phương án hoặc chưa rõ người quyết định.
- Observation: điều nhóm đã thấy trong dữ liệu hoặc quy trình thực tế.

Không ghi tất cả dưới nhãn “requirement”. Chúng có mức độ tin cậy khác nhau.

## 13. Tài liệu sống hỗ trợ đối thoại

Tài liệu có ích khi nó giúp mọi người cùng hiểu và kiểm tra mô hình. Tài liệu không thể thay thế trao đổi, nhưng nó giúp giữ lại kết quả của trao đổi.

Một bộ tài liệu gọn có thể gồm:

| Artifact | Mục đích | Ai thường cập nhật |
|---|---|---|
| Domain Glossary | Thuật ngữ và định nghĩa theo context | Chuyên gia và modeler |
| Process Story / Workflow | Cách quy trình diễn ra qua ví dụ | Operator và facilitator |
| Event Catalog | Các fact nghiệp vụ được công bố | Domain team |
| Context Map | Quan hệ giữa các context | Architect và context owners |
| Decision Log | Quyết định và lý do | Người điều phối / decision owner |
| Assumption & Question Log | Điểm chưa xác nhận | Người phụ trách discovery |
| Example / Acceptance Criteria | Quy tắc có thể kiểm thử | Chuyên gia, tester, developer |
| Model Diagram | Entity, VO, aggregate và quan hệ | Domain team |

### Ghi đúng mức cần thiết

Không cần viết biên bản dài sau mọi cuộc họp. Hãy ưu tiên:
- định nghĩa mới hoặc thay đổi;
- quyết định có tác động;
- ví dụ làm rõ rule;
- câu hỏi chưa giải quyết;
- người chịu trách nhiệm và thời điểm xem lại.

Một ghi chú ngắn nhưng có owner và trạng thái hữu ích hơn một tài liệu dài không ai biết còn đúng hay không.

### Liên kết tài liệu với code và test

Khi có thể, dùng ID ổn định để liên kết:
- decision ID trong pull request hoặc issue;
- event name trong Event Catalog;
- example ID trong acceptance test;
- context name trong package hoặc service documentation.

Liên kết giúp người đọc lần từ quyết định đến model, test và implementation. Tránh nhúng quá nhiều tài liệu vào code comment nếu nội dung có thể được duy trì ở một nguồn có owner rõ.

## 14. Cộng tác bất đồng bộ và làm việc từ xa

Không phải chuyên gia nào cũng có thể tham dự workshop thường xuyên. Cộng tác bất đồng bộ giúp giảm phụ thuộc lịch họp, nhưng cần câu hỏi ngắn và artifact dễ phản hồi.

Một yêu cầu phản hồi tốt nên chứa:

- bối cảnh ngắn;
- một câu hỏi chính;
- ví dụ cụ thể;
- các lựa chọn nếu đã có;
- hệ quả của mỗi lựa chọn;
- người cần phản hồi;
- thời hạn và lý do thời hạn.

Ví dụ:

~~~text
Bối cảnh:
Đơn đã authorize thanh toán nhưng Inventory chưa xác nhận giữ hàng.

Câu hỏi:
Nếu không giữ đủ hàng, Payment có được capture không?

Tình huống:
- Inventory trả đủ số lượng.
- Inventory từ chối.
- Inventory timeout nhưng có thể đã tạo reservation.

Cần xác nhận:
Quy tắc nghiệp vụ và hành động bù trừ cho từng trường hợp.

Người xác nhận:
Payment Owner và Inventory Owner.
~~~

### Không dùng chat làm nguồn quyết định duy nhất

Một câu trả lời trong chat có thể bị mất giữa nhiều thread. Khi quyết định có tác động đến model hoặc integration, hãy đưa kết quả vào decision log hoặc artifact chính thức và gửi lại đường dẫn để chuyên gia xác nhận.

### Chuẩn bị sơ đồ để người không chuyên kỹ thuật đọc được

Sơ đồ nên dùng tên nghiệp vụ, tránh chi tiết class hoặc database nếu không cần. Nếu chuyên gia không hiểu sơ đồ, đó là dấu hiệu nhóm đang dùng ngôn ngữ kỹ thuật thay vì mô tả công việc.

## 15. Xử lý bất đồng và nhiều góc nhìn

Hai chuyên gia có thể đưa ra câu trả lời khác nhau mà không ai sai. Họ có thể làm việc ở hai context, xử lý hai loại khách hàng hoặc nhìn vào hai giai đoạn của cùng quy trình.

Khi có bất đồng:

1. ghi lại từng cách hiểu bằng thuật ngữ của người nói;
2. yêu cầu ví dụ cụ thể cho mỗi cách hiểu;
3. xác định context, vai trò và thời điểm áp dụng;
4. hỏi ai có quyền quyết định chính sách;
5. xác định liệu đây là một rule chung hay hai rule theo ngữ cảnh;
6. ghi quyết định và hệ quả sau khi người có thẩm quyền xác nhận.

Không nên giải quyết bất đồng bằng cách chọn ý kiến của người có chức danh cao hơn mà không làm rõ phạm vi trách nhiệm. Cũng không nên ép mọi nhóm dùng cùng một mô hình nếu công việc của họ thực sự khác nhau.

### Tách sự thật, chính sách và sở thích

Một số bất đồng xuất phát từ việc trộn ba loại thông tin:

- Sự thật quan sát được: shipment đã được carrier nhận.
- Chính sách: sau khi carrier nhận, đơn không được hủy theo luồng thông thường.
- Sở thích: nhân viên muốn giao diện có nút hủy ngay cả khi phải xử lý ngoại lệ.

Hãy ghi riêng từng loại. Chính sách cần owner xác nhận; sở thích có thể là input cho thiết kế trải nghiệm.

## 16. Duy trì đối thoại khi model đã được triển khai

Đối thoại không kết thúc khi feature được release. Dữ liệu và hành vi thật có thể cho thấy model chưa phản ánh đầy đủ domain.

Các tín hiệu cần đưa trở lại discovery:

- người dùng thường xuyên ghi chú ngoài hệ thống;
- một bước xử lý thủ công xuất hiện lặp lại;
- nhiều ticket hỗ trợ cùng hỏi một khái niệm;
- nhân viên phải sửa dữ liệu sau khi quy trình hoàn tất;
- một event được phát nhưng consumer không hiểu ý nghĩa;
- một quy tắc mới khiến nhiều context phải thay đổi cùng lúc;
- báo cáo nghiệp vụ không khớp với cách vận hành.

Đừng chỉ xem đây là bug hoặc yêu cầu giao diện. Có thể mô hình đang thiếu một trạng thái, một khái niệm, một context boundary hoặc một policy.

### Feedback loop sau triển khai

~~~mermaid
flowchart TD
    A[Quan sát sử dụng thực tế] --> B[Thu thập ví dụ và vấn đề]
    B --> C[Trao đổi với người vận hành]
    C --> D[Điều chỉnh glossary và model]
    D --> E[Cập nhật examples và tests]
    E --> F[Thay đổi phần mềm]
    F --> A
~~~

Vòng lặp này giúp phần mềm và hiểu biết nghiệp vụ tiến hóa cùng nhau.

## 17. Ví dụ workshop: làm rõ quy trình đổi địa chỉ giao hàng

### Bối cảnh

Khách hàng có thể yêu cầu đổi địa chỉ sau khi đặt hàng. Các nhóm liên quan gồm Customer Support, Order Operations, Warehouse và Shipping.

### Bước 1: nghe câu chuyện thực tế

Chuyên gia kể một trường hợp:
- khách đặt đơn lúc 09:00;
- kho nhận yêu cầu chuẩn bị lúc 09:10;
- khách gọi đổi địa chỉ lúc 09:15;
- kho chưa bàn giao hàng;
- nhân viên cập nhật địa chỉ và gửi yêu cầu tạo lại shipping label.

### Bước 2: xác định event

Nhóm ghi các fact:
- OrderPlaced
- FulfillmentRequested
- DeliveryAddressChangeRequested
- DeliveryAddressChangeApproved
- ShippingLabelVoided
- ShippingLabelCreated

### Bước 3: làm rõ rule

| Rule | Ví dụ | Câu hỏi cần xác nhận |
|---|---|---|
| Trước khi kho xử lý | Có thể đổi địa chỉ trực tiếp | Có cần xác minh lại địa chỉ không? |
| Đã tạo label nhưng chưa dispatch | Có thể phải void label cũ | Ai chịu phí label? |
| Đã dispatch | Không đổi địa chỉ theo luồng thông thường | Có thể yêu cầu carrier redirect không? |
| Đã giao | Không đổi địa chỉ | Có tạo Return hoặc Support Case không? |

### Bước 4: phát hiện ownership

- Customer Context sở hữu địa chỉ hồ sơ.
- Order Context sở hữu snapshot địa chỉ đã chọn cho đơn.
- Warehouse/Fulfillment Context sở hữu trạng thái chuẩn bị hàng.
- Shipping Context sở hữu label và trạng thái bàn giao carrier.

Khi khách đổi địa chỉ của một đơn, Order Context cần điều phối yêu cầu theo trạng thái fulfillment. Nó không nên tự sửa dữ liệu label trong Shipping Context.

### Bước 5: xác nhận model và event

Một command có thể là RequestDeliveryAddressChange. Nếu được chấp nhận, Order phát DeliveryAddressChanged. Fulfillment và Shipping phản ứng theo hợp đồng đã thống nhất.

~~~mermaid
sequenceDiagram
    actor Customer
    participant Support as Customer Support
    participant Order as Order Context
    participant Fulfillment as Fulfillment Context
    participant Shipping as Shipping Context

    Customer->>Support: Request address change
    Support->>Order: RequestDeliveryAddressChange
    Order->>Fulfillment: Check fulfillment state
    Fulfillment-->>Order: NotDispatched
    Order->>Order: Approve and update order snapshot
    Order->>Shipping: Void old label / request new label
    Order-->>Support: Address change accepted
~~~

Sơ đồ vẫn cần được xác thực với chuyên gia: nếu Shipping từ chối tạo label mới sau khi Order đã cập nhật snapshot thì quy trình bù trừ là gì? Có cần reservation cho năng lực carrier không? Workshop nên ghi những câu hỏi còn mở thay vì giả định mọi bước luôn thành công.

### Bước 6: lưu quyết định

Decision log ghi:
- thời điểm cuối cùng cho phép đổi địa chỉ;
- owner quyết định theo từng trạng thái;
- snapshot nào cần giữ;
- event nào được phát;
- cách xử lý khi label mới thất bại;
- ngày hoặc điều kiện xem xét lại chính sách.

Sau workshop, đội có thể tạo acceptance examples và test cho từng nhánh. Chuyên gia review ví dụ trước khi logic được triển khai.

## 18. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Chỉ phỏng vấn chuyên gia một lần | Quy tắc mới và ngoại lệ không được phát hiện | Duy trì nhịp trao đổi theo discovery và iteration |
| Chỉ nói chuyện với quản lý | Bỏ sót thao tác thực tế và ngoại lệ | Kết hợp process owner và operator |
| Hỏi câu hỏi quá rộng | Có nhiều thông tin nhưng ít quyết định | Bắt đầu từ một giao dịch cụ thể |
| Chỉ hỏi happy path | Model không xử lý được trường hợp thật | Hỏi lỗi, ngoại lệ và trường hợp biên |
| Dùng thuật ngữ kỹ thuật với chuyên gia | Hai bên tưởng đã hiểu nhưng thực ra khác nghĩa | Dùng ngôn ngữ công việc và ví dụ |
| Ép một định nghĩa cho toàn tổ chức | Che khuất khác biệt giữa Bounded Context | Ghi định nghĩa theo context và Context Map |
| Xem tài liệu là nguồn chân lý bất biến | Tài liệu nhanh chóng lỗi thời | Xác thực và cập nhật sau mỗi quyết định |
| Không ghi giả định | Giả định tạm thời trở thành rule không ai kiểm tra | Dùng assumption log có owner và hạn xác nhận |
| Ghi biên bản nhưng không có action | Câu hỏi được thảo luận lặp lại | Gắn owner, thời hạn và quyết định |
| Để developer tự quyết chính sách | Code phản ánh suy đoán kỹ thuật | Đưa quyết định về đúng business owner |
| Chờ mọi thứ rõ mới bắt đầu model | Discovery kéo dài, không có feedback | Dùng model giả thuyết và kiểm tra bằng ví dụ |
| Biến mọi bất đồng thành tranh luận cá nhân | Mất cơ hội phát hiện khác biệt theo context | Tách vai trò, phạm vi và bằng chứng |
| Không quay lại sau triển khai | Model không học từ thực tế | Tạo feedback loop từ vận hành |

## 19. Quy trình cộng tác có thể áp dụng

Một vòng cộng tác cho một capability có thể đi theo các bước:

1. **Xác định mục tiêu:** nêu quyết định hoặc quy trình cần hiểu.
2. **Chọn người tham gia:** có operator, domain expert và decision owner phù hợp.
3. **Thu thập ví dụ:** một trường hợp bình thường, một ngoại lệ và một thất bại.
4. **Kể lại quy trình:** xác định actor, hành động, event và dữ liệu.
5. **Làm rõ ngôn ngữ:** thống nhất thuật ngữ trong phạm vi context.
6. **Khám phá quy tắc:** điều kiện, invariant, policy, thời gian và ownership.
7. **Phác thảo model:** entity, value object, aggregate, event hoặc context boundary khi có căn cứ.
8. **Thử bằng ví dụ:** kiểm tra model với scenario thực và scenario biên.
9. **Ghi quyết định:** phân biệt decision, assumption, observation và open question.
10. **Áp dụng vào code/test:** dùng cùng ngôn ngữ và ví dụ trong implementation.
11. **Review với chuyên gia:** xác nhận model và behavior có thể quan sát.
12. **Theo dõi sau triển khai:** đưa phản hồi vận hành trở lại discovery.

Không nhất thiết hoàn tất tất cả bước trong một buổi. Đây là vòng lặp có thể chạy nhiều lần khi hiểu biết sâu hơn.

## 20. Checklist cho một nhịp đối thoại hiệu quả

### Trước buổi trao đổi

- [ ] Mục tiêu và phạm vi được viết rõ.
- [ ] Có đúng người thực hiện và người có quyền xác nhận.
- [ ] Có ví dụ thực tế, không chỉ mô tả lý tưởng.
- [ ] Có câu hỏi mở và các giả định cần kiểm tra.
- [ ] Artifact dùng trong buổi họp dễ hiểu với chuyên gia.
- [ ] Đã xác định đầu ra cần có.

### Trong buổi trao đổi

- [ ] Bắt đầu từ một tình huống cụ thể.
- [ ] Làm rõ actor, hành động, event và kết quả.
- [ ] Hỏi về điều kiện, ngoại lệ và lý do.
- [ ] Ghi lại thuật ngữ và nghĩa theo context.
- [ ] Phân biệt fact, policy, assumption và preference.
- [ ] Thử model với ít nhất một scenario khác.
- [ ] Đánh dấu điểm chưa thống nhất thay vì tự đoán.

### Sau buổi trao đổi

- [ ] Quyết định có owner và rationale.
- [ ] Câu hỏi mở có người phụ trách và thời điểm xem lại.
- [ ] Glossary hoặc model được cập nhật.
- [ ] Acceptance examples hoặc tests phản ánh rule đã xác nhận.
- [ ] Người tham gia có cơ hội kiểm tra bản ghi kết quả.
- [ ] Thay đổi ảnh hưởng context khác được thông báo.
- [ ] Có thời điểm xem lại sau khi triển khai.

## Kết luận

Duy trì đối thoại thường xuyên với chuyên gia nghiệp vụ giúp DDD giữ mô hình gần với thực tế của tổ chức. Cuộc trao đổi hiệu quả bắt đầu từ ví dụ cụ thể, làm rõ tác nhân, quyết định, quy tắc và ngoại lệ, sau đó cùng xây ngôn ngữ và mô hình có thể kiểm chứng. Event Storming, Domain Storytelling và Example Mapping giúp biến hiểu biết thành artifact chung; glossary, decision log và assumption log giúp lưu lại kết quả mà không biến tài liệu thành thứ bất biến. Khi feedback từ code và vận hành quay trở lại cuộc đối thoại, Entity, Value Object, Aggregate, Domain Event và ranh giới Bounded Context có thể tiến hóa dựa trên hiểu biết đã được xác nhận thay vì giả định.

