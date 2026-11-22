# Event Storming như công cụ khám phá hành vi và sự kiện

> **Chủ đề:** Software Design Architecture System Architecture Microservices  
> **Nhánh kiến thức:** Phân rã nghiệp vụ  
> **Trọng tâm:** Dùng Event Storming để cùng chuyên gia nghiệp vụ khám phá điều gì thực sự xảy ra trong một hệ thống, nguyên nhân của các thay đổi, quy tắc vận hành, ranh giới trách nhiệm và các câu hỏi còn bỏ ngỏ trước khi quyết định kiến trúc.

## 1. Vì sao cần Event Storming?

Khi bắt đầu thiết kế hệ thống, nhóm phát triển thường hỏi ngay: “Có những service nào?”, “Bảng dữ liệu nào?”, “API nào?”. Những câu hỏi này dễ khiến mô hình kỹ thuật đi trước hiểu biết nghiệp vụ. Một sơ đồ chỉ có các thực thể như Order, Payment, Inventory không cho biết **điều gì khiến chúng đổi trạng thái**, ai quyết định, hay trường hợp ngoại lệ nào làm quy trình thất bại.

**Event Storming** là kỹ thuật workshop cộng tác, gắn với Domain-Driven Design (DDD), trong đó các bên cùng mô tả dòng hành vi của một miền nghiệp vụ bằng **những sự kiện đã xảy ra**. Mọi người bắt đầu từ các câu như “Đơn hàng đã được đặt”, “Thanh toán đã bị từ chối”, “Hàng đã được bàn giao”. Từ chuỗi sự kiện này, nhóm lần theo lệnh, vai trò, chính sách, quy tắc bất biến, sự phụ thuộc và điểm chưa rõ.

Mục đích chính là **khám phá và xây dựng hiểu biết chung**. Kết quả có thể hỗ trợ thiết kế một ứng dụng đơn thể, khối đơn thể mô-đun hoặc hệ thống vi dịch vụ. Việc vẽ nhiều sự kiện trên bảng **không tự động có nghĩa** phải triển khai event sourcing, event bus hay tách mỗi vùng thành một microservice.

### Sau bài này, người học có thể

- Phân biệt sự kiện miền nghiệp vụ với lệnh, trạng thái, truy vấn và tín hiệu hạ tầng.
- Chuẩn bị, điều phối và đọc kết quả một workshop Event Storming.
- Đi từ chuỗi sự kiện sang quy tắc nghiệp vụ, hotspot, aggregate, candidate bounded context và tương tác giữa các vùng.
- Biết phần nào của bảng khám phá có thể chuyển thành quyết định kiến trúc, phần nào chỉ là giả thuyết cần kiểm chứng.
- Nhận diện các tình huống lỗi, xử lý không đồng bộ và rủi ro khi tích hợp qua sự kiện.

## 2. Tư duy cốt lõi: kể lại điều đã xảy ra

Một **domain event** là sự thật nghiệp vụ quan trọng đã xảy ra trong một bối cảnh xác định. Tên sự kiện thường diễn đạt ở thì hoàn thành hoặc quá khứ:

- “Đơn hàng đã được tạo”.
- “Hạn mức tín dụng đã được phê duyệt”.
- “Chỗ ngồi đã được giữ”.
- “Yêu cầu hoàn tiền đã bị từ chối”.

Sự kiện nên diễn đạt bằng ngôn ngữ mà chuyên gia nghiệp vụ hiểu được. Nó nói **điều gì đã xảy ra**, không ra lệnh cho ai phải làm gì.

| Khái niệm | Ví dụ | Câu hỏi khám phá |
| --- | --- | --- |
| **Domain event** | Đơn hàng đã được xác nhận | Chuyện gì vừa xảy ra? Có ý nghĩa gì đối với nghiệp vụ? |
| **Command / ý định hành động** | Xác nhận đơn hàng | Ai hoặc điều gì yêu cầu hành động? Có thể bị từ chối không? |
| **Actor / tác nhân** | Khách hàng, nhân viên kho | Ai khởi xướng hoặc tham gia? |
| **Policy / quy tắc phản ứng** | Khi thanh toán thành công, yêu cầu chuẩn bị hàng | Sự kiện nào kích hoạt hành động tiếp theo? Có điều kiện nào không? |
| **Aggregate / điểm giữ bất biến** | Đơn hàng | Quy tắc nào cần đúng tại thời điểm chấp nhận lệnh? |
| **Read model / góc nhìn tra cứu** | Màn hình theo dõi đơn | Người dùng cần nhìn thông tin gì để ra quyết định? |
| **External system** | Cổng thanh toán, đơn vị vận chuyển | Phần nào nằm ngoài quyền kiểm soát của nhóm? |
| **Hotspot / điểm nóng** | Hàng hết trong lúc đang thanh toán | Đâu là tranh cãi, rủi ro, ngoại lệ hoặc câu hỏi chưa trả lời? |
| **Bounded context (ứng viên)** | Order Management, Inventory, Payment | Trong phạm vi nào thuật ngữ và quy tắc có nghĩa nhất quán? |

Các loại thẻ, hình dạng và màu giấy là **quy ước của workshop**, không phải đặc tính cố định của DDD. Nhiều nhóm sử dụng màu cam cho domain event, xanh lam cho command, tím cho policy, vàng cho actor, đỏ hoặc hồng cho hotspot. Hãy ghi chú giải trên bảng và ưu tiên sự rõ ràng hơn là tranh luận màu sắc.

### Sự kiện phải đáng để kể

“OrderRowInserted” mô tả cách lưu dữ liệu; “OrderPlaced” mô tả một chuyển biến nghiệp vụ. “ButtonClicked” thường chỉ là tương tác giao diện; “RefundRequested” mới thể hiện ý định có ý nghĩa trong quy trình hoàn tiền. Không phải mọi thay đổi trường dữ liệu đều cần xuất hiện thành sự kiện trên bảng.

Tùy miền nghiệp vụ, một thuật ngữ có thể là sự kiện ở ngữ cảnh này nhưng chỉ là bước kỹ thuật ở ngữ cảnh khác. Hãy hỏi: **Nếu sự kiện này xảy ra, người làm nghiệp vụ có quan tâm hay phải làm điều gì khác không?**

## 3. Ba mức độ Event Storming

Event Storming thường được tổ chức với ba mức độ chi tiết; không cần dùng cả ba trong một buổi.

### 3.1. Big Picture: nhìn xuyên suốt hành trình

**Mục tiêu:** xây dựng bức tranh lớn của một quy trình hoặc toàn bộ miền nghiệp vụ; khám phá thuật ngữ, các giai đoạn, sự lệch hiểu và điểm nóng.

- Mời đại diện từ nhiều bộ phận: kinh doanh, vận hành, chăm sóc khách hàng, sản phẩm, kỹ thuật và các bên liên quan trực tiếp.
- Mở rộng phạm vi đủ để nhìn thấy điểm bàn giao và sự phụ thuộc.
- Dùng dòng thời gian từ trái sang phải, từ trước tới sau; chấp nhận nhiều nhánh và vòng lặp.
- Chưa cần quyết định mỗi sự kiện sẽ là một message, topic, table hay API.

**Đầu ra:** bản đồ hành vi, các câu hỏi cần kiểm chứng, ngôn ngữ chung, vùng thay đổi độc lập có thể trở thành bounded context.

### 3.2. Process Modeling: hiểu một luồng cụ thể

**Mục tiêu:** bóc tách chuỗi actor → command → quyết định → event → policy → command cho một quy trình quan trọng.

- Chọn một kịch bản hẹp như đặt hàng và thanh toán.
- Bổ sung điều kiện, nhánh lỗi, hết hạn, hủy, thử lại, xử lý thủ công.
- Xác định ai chịu trách nhiệm từng bước và thông tin cần được hiển thị ở đâu.
- Làm rõ các phản ứng đồng bộ hoặc có thể trễ về mặt nghiệp vụ.

**Đầu ra:** luồng có thể trao đổi với BA, product owner và developer; các quy tắc chấp nhận hoặc từ chối hành động.

### 3.3. Software Design: nối hành vi với mô hình triển khai

**Mục tiêu:** đi sâu vào một bounded context để đề xuất aggregate, command handler, chính sách, mô hình đọc, event contract và giao tiếp ngoài ranh giới.

- Hỏi quy tắc bất biến nào phải giữ trong một giao dịch.
- Phân biệt domain event nội bộ với integration event công bố ra bên ngoài.
- Làm rõ nguồn sự thật, quyền sở hữu dữ liệu và nhu cầu nhất quán.
- Chỉ thiết kế chi tiết cho khu vực đã hiểu đủ và có nhu cầu triển khai thực tế.

**Đầu ra:** một hoặc nhiều mô hình thiết kế ứng viên, quyết định cần ghi nhận, giả định cần xác nhận bằng prototype hoặc dữ liệu sản xuất.

## 4. Chuẩn bị workshop

### 4.1. Đặt câu hỏi dẫn đường

Một workshop tốt nên có mục đích đủ cụ thể. Ví dụ:

> “Từ khi khách nhấn Đặt hàng đến lúc giao hàng hoàn tất hoặc hoàn tiền, các biến cố nghiệp vụ nào xảy ra, ai quyết định, và xử lý ra sao khi thanh toán thành công nhưng kho không còn hàng?”

Tránh mục tiêu mơ hồ như “Thiết kế hệ thống microservices mới”. Mục tiêu khám phá hành vi sẽ giúp nhóm không bỏ qua người dùng và ngoại lệ.

### 4.2. Chọn phạm vi và người tham gia

- **Phạm vi:** điểm bắt đầu, điểm kết thúc, vai trò liên quan, biến thể quan trọng; ghi rõ những gì nằm ngoài buổi này.
- **Chuyên gia nghiệp vụ:** người thực sự vận hành quy trình, biết ngoại lệ và các lối xử lý thủ công.
- **Facilitator:** giữ nhịp, hỏi để làm rõ, không tự áp đặt lời giải.
- **Người ghi nhận:** chụp/ghi bản đồ, hotspot, câu hỏi, quyết định và thuật ngữ sau buổi họp.
- **Thành viên kỹ thuật:** đặt câu hỏi về nguyên nhân, trách nhiệm, nhất quán; chưa vội áp công nghệ.

Nếu chỉ có kỹ sư mà thiếu người hiểu thực tế vận hành, sơ đồ rất dễ phản ánh giả định nội bộ của nhóm xây dựng.

### 4.3. Công cụ và quy ước tối thiểu

Dùng tường giấy dài hoặc bảng cộng tác như Miro, FigJam; chuẩn bị note, bút, vùng để ghi chú giải, khung phạm vi, khu vực hotspot. Với workshop từ xa, cần người điều phối các lượt phát biểu, phóng to vùng đang thảo luận và lưu bản chụp theo từng vòng.

Thống nhất trước:

1. Sự kiện đặt ở dạng **đã xảy ra** và dùng từ nghiệp vụ.
2. Trục thời gian đi từ trái sang phải; nhánh song song đặt theo hàng riêng.
3. Bất đồng chưa giải quyết được đánh dấu hotspot, không xóa ý kiến khác.
4. Có thể di chuyển, gộp hoặc đổi tên thẻ khi hiểu biết mới xuất hiện.
5. Trong vòng đầu **không tranh luận code, bảng dữ liệu hay tên service**.

## 5. Quy trình điều phối từ sự kiện đến ranh giới

### Bước 1 — Nêu bối cảnh và điểm bắt đầu/kết thúc

Facilitator diễn giải câu hỏi dẫn đường, các actor chính, điểm đầu và cuối. Ví dụ: bắt đầu khi giỏ hàng được gửi yêu cầu đặt; kết thúc khi đơn giao thành công, bị hủy hoặc hoàn tiền. Nếu giới hạn chưa rõ, đặt một hotspot “Biên quy trình cần thống nhất”.

### Bước 2 — “Storm” các sự kiện bằng tiếng nói của nghiệp vụ

Cho mọi người vài phút viết riêng các domain event mà họ nhớ. Mỗi note chỉ có **một điều đã xảy ra**. Khuyến khích ghi cả trường hợp hiếm gặp:

- Giỏ hàng đã được gửi thành đơn.
- Đơn hàng đã được đặt.
- Thanh toán đã được chấp nhận.
- Yêu cầu giữ tồn kho đã bị từ chối.
- Đơn hàng đã bị hủy do quá hạn.
- Kiện hàng đã bị trả lại.

Đừng chặn những sự kiện dường như trùng; giai đoạn này ưu tiên bộc lộ cách hiểu khác nhau.

### Bước 3 — Ghép dòng thời gian và nhánh ngoại lệ

Cả nhóm sắp sự kiện theo trình tự. Hỏi “Điều gì đã xảy ra ngay trước đó?”, “Có phải lúc nào cũng xảy ra sau bước này?”, “Có nhánh song song nào?”, “Tối đa chờ được bao lâu?”.

Đừng ép mọi thứ thành một đường thẳng. Nhiều quy trình có kết quả bất đồng bộ, timeout, manual review hoặc khách đổi ý giữa chừng. Vẽ rõ nhánh thành công và nhánh thất bại.

### Bước 4 — Tìm command và actor

Với mỗi sự kiện quan trọng, hỏi “Ai muốn điều này xảy ra?” và “Lệnh nào đã được yêu cầu?”. Một command diễn đạt ý định tương lai, có thể bị từ chối. Ví dụ:

- Actor **Khách hàng** gửi command **Đặt đơn hàng**.
- Hệ thống chấp nhận lệnh và phát sinh event **Đơn hàng đã được đặt**.
- Actor **Nhân viên kho** gửi command **Xác nhận đóng gói**.
- Nếu quy tắc được đáp ứng, event **Đơn hàng đã được đóng gói** xảy ra.

Không phải mọi event đều phải có một command do người dùng tạo. Một bộ đếm thời gian, tác vụ định kỳ hoặc thông báo từ hệ thống bên ngoài cũng có thể làm thay đổi hành vi.

### Bước 5 — Tìm policy và phản ứng tự động

Hỏi: “Sau khi X xảy ra, hệ thống hoặc tổ chức thường làm gì?”, “Điều kiện nào khiến hành động kế tiếp bị bỏ qua hoặc chuyển hướng?”.

Ví dụ:

- **Khi Đơn hàng đã được đặt**, chính sách kiểm tra điều kiện thanh toán và **Yêu cầu thanh toán**.
- **Khi Thanh toán đã được chấp nhận**, chính sách **Yêu cầu giữ hàng**.
- **Khi Giữ hàng đã thất bại**, chính sách **Yêu cầu hủy đơn** và có thể **Yêu cầu hoàn tiền**, tùy trạng thái thanh toán.
- **Khi Đơn đã quá hạn thanh toán**, chính sách **Hủy đơn chưa thanh toán**.

Policy là mô tả quan hệ nhân quả; chưa nhất thiết là một service, message consumer hay workflow engine. Nếu có nhiều phản ứng cạnh tranh, giữ chúng trên bảng và đánh dấu câu hỏi về thứ tự, điều kiện.

### Bước 6 — Nhận diện dữ liệu cần xem, hệ thống ngoài và ràng buộc

Hỏi người làm nghiệp vụ cần nhìn gì trước khi hành động: số lượng có thể bán, lịch sử thanh toán, tình trạng giao vận, lý do từ chối, hạn giữ hàng. Đó là ứng viên **read model** hoặc màn hình nghiệp vụ.

Đánh dấu các hệ thống bên ngoài như payment gateway, ERP, hãng vận chuyển; mô tả điều gì được hệ thống của mình quan sát và điều gì chỉ nhận qua callback hoặc đối soát. Chỉ ra các ràng buộc: “Không được giao hàng khi thanh toán chưa được xác nhận”, “Một phiếu hoàn tiền không được thực hiện hai lần”.

### Bước 7 — Khoanh hotspot, nhóm trách nhiệm, tìm bounded context

Đặt hotspot tại những điểm có tranh luận hoặc rủi ro:

- “Đã trừ tiền nhưng giữ kho thất bại thì ai ra lệnh hoàn tiền?”
- “Thanh toán bị báo chậm; đơn đã hết hạn xử lý thế nào?”
- “Từ ‘đã xác nhận’ có nghĩa giống nhau với bán hàng và kho không?”
- “Ai được phép chuyển đơn từ Hủy sang Khôi phục?”

Sau đó nhóm các sự kiện, command và quy tắc thuộc cùng một ngôn ngữ/đơn vị chịu trách nhiệm. Vùng này là **ứng viên bounded context**, cần kiểm chứng bằng tính gắn kết nghiệp vụ, quyền sở hữu dữ liệu, quy tắc thay đổi, ranh giới nhất quán và đội ngũ phụ trách.

### Bước 8 — Chốt điều đã hiểu và việc cần xác nhận

Cuối buổi, mỗi hotspot cần ít nhất một người nhận tìm hiểu hoặc một nguồn có thể kiểm chứng. Lưu bản đồ với phiên bản/ngày, bảng thuật ngữ, danh sách quyết định đã thống nhất và câu hỏi mở. Chỉ chuyển giả thuyết kiến trúc thành quyết định chính thức khi có đủ bằng chứng.

## 6. Ví dụ xuyên suốt: đặt hàng thương mại điện tử

Giả định một nền tảng có khách hàng, bộ phận bán hàng, kho, cổng thanh toán và hãng vận chuyển. Sản phẩm cho phép khách đặt đơn, thanh toán online, đóng gói, giao hàng và hủy/hoàn tiền trong một số điều kiện.

### 6.1. Bản đồ sự kiện mức Big Picture

Một nhánh thành công tối giản:

~~~text
[Khách gửi yêu cầu đặt đơn]
          |
          v
(Đơn hàng đã được đặt)
          |
          v
(Yêu cầu thanh toán đã được khởi tạo)
          |
          v
(Thanh toán đã được chấp nhận)
          |
          v
(Tồn kho đã được giữ)
          |
          v
(Đơn hàng đã được chuyển sang chuẩn bị)
          |
          v
(Kiện hàng đã được bàn giao vận chuyển)
          |
          v
(Đơn hàng đã được giao)
~~~

Các ngoặc tròn trong sơ đồ biểu thị event nghiệp vụ; dòng chữ đầu là hành động khởi xướng. Trong workshop thật, sơ đồ này thường có nhánh ngang và các bước diễn ra bất đồng bộ.

Các nhánh quan trọng không nên bỏ:

- **Thanh toán bị từ chối** → khách có thể thử lại; hết hạn → đơn bị hủy.
- **Thanh toán thành công nhưng giữ kho thất bại** → cần chính sách hủy và xử lý hoàn tiền.
- **Hết thời gian giữ hàng** → kho giải phóng tồn; đơn có thể cần đặt lại.
- **Hãng vận chuyển không nhận kiện** → yêu cầu thử lại hoặc chọn đơn vị khác.
- **Khách yêu cầu hủy** khi hàng đã bàn giao → có thể chuyển sang quy trình trả hàng thay vì hủy tức thời.
- **Webhook thanh toán đến trễ hoặc trùng** → cần phân biệt trạng thái nghiệp vụ với số lần thông báo kỹ thuật.

### 6.2. Thêm command, actor và policy

| Nguồn/kích hoạt | Command hoặc quyết định | Kết quả có thể xảy ra | Điều cần làm rõ |
| --- | --- | --- | --- |
| Khách hàng nhấn xác nhận | Đặt đơn hàng | Đơn hàng đã được đặt / Đặt đơn bị từ chối | Giá và số lượng có còn hợp lệ? |
| Đơn hàng đã được đặt | Yêu cầu thanh toán | Yêu cầu thanh toán đã được tạo | Có hỗ trợ thanh toán khi nhận hàng? |
| Cổng thanh toán xác nhận | Ghi nhận thanh toán | Thanh toán đã được chấp nhận | Nguồn nào xác nhận kết quả cuối cùng? |
| Thanh toán đã được chấp nhận | Giữ tồn kho | Tồn kho đã được giữ / Giữ kho thất bại | Ưu tiên hàng cho đơn nào? |
| Tồn kho đã được giữ | Yêu cầu chuẩn bị hàng | Đơn đã được chuyển sang chuẩn bị | Ai chịu trách nhiệm đóng gói? |
| Giữ kho thất bại | Yêu cầu hủy và hoàn tiền | Đơn bị hủy; hoàn tiền được yêu cầu | Hoàn tiền tự động hay cần phê duyệt? |
| Hàng đã bàn giao | Cập nhật tình trạng giao | Đơn đã được giao / Giao thất bại | Sự kiện từ hãng vận chuyển đáng tin đến đâu? |

Lưu ý: bảng chỉ là một **kịch bản giả định** để khám phá, không phải quy tắc phổ quát. Có doanh nghiệp **giữ kho trước khi thanh toán** để giảm trường hợp phải hoàn tiền, doanh nghiệp khác thu tiền trước rồi xác nhận khả năng đáp ứng. Event Storming giúp làm lộ sự khác biệt để nhóm chọn đúng mô hình của mình.

### 6.3. Đọc một đoạn hành vi ở mức sâu hơn

~~~text
Actor: Khách hàng
  → Command: Đặt đơn hàng
  → Kiểm tra: giỏ có mặt hàng hợp lệ, giá còn hiệu lực, địa chỉ có thể phục vụ?
  → Event: Đơn hàng đã được đặt

Policy: Khi đơn đã được đặt
  → Command: Tạo yêu cầu thanh toán
  → Event: Yêu cầu thanh toán đã được tạo

External system: Cổng thanh toán
  → Tín hiệu kết quả thanh toán
  → Command: Ghi nhận thanh toán thành công
  → Event: Thanh toán đã được chấp nhận

Policy: Khi thanh toán đã được chấp nhận
  → Command: Giữ tồn kho
  → Event: Tồn kho đã được giữ
     hoặc Event: Giữ tồn kho đã thất bại
~~~

Một câu hỏi mấu chốt: **Ai là nguồn sự thật cho “Thanh toán đã được chấp nhận”?** Nếu đây là sự kiện của Payment context, Order context nên phản ứng qua một hợp đồng rõ ràng, thay vì tự đọc bảng thanh toán. Nếu thanh toán có bước pending và đối soát, cần thể hiện những trạng thái đó trong quy trình khám phá.

### 6.4. Những câu hỏi cần ghi vào hotspot

1. Một đơn được phép thanh toán nhiều lần trong trường hợp thử lại không? Phân biệt nhiều payment attempt với một khoản tiền đã thu như thế nào?
2. Nếu request timeout nhưng cổng thanh toán thực tế đã thu tiền, ai đối soát?
3. Khi tồn kho thiếu, có cho phép giao thiếu, chờ nhập hàng hoặc hủy toàn bộ?
4. Nếu người dùng yêu cầu hủy đúng lúc đơn chuyển sang đóng gói, ai quyết định ưu tiên?
5. “Đã giao” có nghĩa hãng vận chuyển báo thành công hay khách thực sự nhận hàng?
6. Khi hoàn tiền thất bại, có quy trình thủ công hay thử lại tự động?
7. Đơn dùng voucher sau khi hoàn tiền thì voucher được phục hồi ra sao?

Đây là những câu hỏi làm thay đổi mô hình nghiệp vụ và thiết kế giao tiếp, nên đáng ưu tiên hơn tranh luận sớm về framework.

## 7. Từ bản đồ sự kiện đến ranh giới nghiệp vụ

Event Storming giúp nhận ra **cụm hành vi gắn với cùng quy tắc và ngôn ngữ**. Những cụm đó là đầu mối thảo luận bounded context.

| Bounded context ứng viên | Ngôn ngữ, trách nhiệm thường gặp | Domain event tiêu biểu |
| --- | --- | --- |
| **Ordering** | vòng đời đơn, điều kiện nhận đơn, hủy đơn | Đơn hàng đã được đặt; Đơn hàng đã bị hủy |
| **Payments** | yêu cầu thanh toán, kết quả thu tiền, hoàn tiền | Thanh toán đã được chấp nhận; Hoàn tiền đã hoàn tất |
| **Inventory** | số lượng có thể bán, giữ hàng, giải phóng hàng | Tồn kho đã được giữ; Giữ tồn kho đã bị từ chối |
| **Fulfillment** | đóng gói, bàn giao, xuất kho | Đơn đã được đóng gói; Kiện đã được bàn giao |
| **Shipping** | hành trình, phát hàng, giao lại | Giao hàng đã thất bại; Đơn hàng đã được giao |

Cần hỏi tiếp về ranh giới:

- **Ngôn ngữ:** “đơn”, “thanh toán thành công”, “còn hàng” có định nghĩa khác nhau ở mỗi bộ phận không?
- **Quyền quyết định:** vùng nào được phép chấp nhận hoặc từ chối command?
- **Quyền sở hữu dữ liệu:** ai là nguồn chính xác cuối cùng cho một sự thật?
- **Tính nhất quán:** quy tắc nào cần đúng tức thì trong một transaction, quy tắc nào chịu được cập nhật trễ?
- **Khả năng thay đổi:** các chính sách thường thay đổi cùng nhau hay độc lập?
- **Tổ chức:** đội nào có đủ tri thức và quyền vận hành phần trách nhiệm đó?

**Một bounded context không đồng nghĩa một microservice.** Nhiều context có thể là các module trong một modular monolith; một context cũng có thể chứa nhiều thành phần triển khai vì quy mô hoặc yêu cầu vận hành. Bảng Event Storming giúp phân rã **miền nghiệp vụ**, còn quyết định triển khai cần cân nhắc giao dịch, độ trễ, tải, tính độc lập triển khai, đội ngũ và chi phí vận hành.

### 7.1. Aggregate và bất biến: đừng chọn chỉ bằng danh từ

Trong Ordering, có thể khám phá các quy tắc:

- Đơn đã hủy không thể được chuyển trực tiếp sang trạng thái giao hàng.
- Không được chấp nhận command Xác nhận đơn khi danh sách dòng hàng rỗng.
- Một yêu cầu hủy hợp lệ không được xử lý hai lần làm tăng khoản hoàn tiền.

Một **aggregate** là ranh giới nhất quán cho một nhóm trạng thái và bất biến cần bảo vệ khi xử lý command. Các quy tắc trên giúp thảo luận liệu Order là aggregate root phù hợp và trạng thái nào phải nằm trong cùng transaction. Không tự kết luận rằng mọi sự kiện có chữ “Order” đều thuộc một aggregate, hoặc một aggregate tương đương một service.

### 7.2. Nhìn các quan hệ giữa context

Ví dụ, Ordering cần biết Payment đã xác nhận thanh toán; Inventory cần biết yêu cầu giữ hàng; Shipping cần nhận thông tin bàn giao. Khi các context giao tiếp, cần xác định:

- Context nào **phát biểu sự thật** và context nào **tiêu thụ sự thật**?
- Bên nhận cần toàn bộ dữ liệu hay chỉ một bộ trường tối thiểu?
- Bên nhận phải phản ứng trong bao lâu; một chút trễ có được không?
- Nếu bên phát thay đổi hợp đồng, ai chịu ảnh hưởng?
- Nếu hai bên dùng từ “confirmed” khác nghĩa, có cần lớp chuyển đổi ngôn ngữ (anti-corruption layer) không?

Những câu trả lời này có giá trị hơn việc vẽ mũi tên tùy ý giữa các service.

## 8. Diễn giải sang thiết kế mà không nhầm khái niệm

### 8.1. Domain event khác integration event

**Domain event** ghi nhận sự thật trong một mô hình miền. Nó có thể là đối tượng nội bộ giúp xử lý hành vi và cập nhật trạng thái. **Integration event** là thông điệp/hợp đồng được công bố để context khác nhận biết một sự thay đổi có ý nghĩa.

Không phải mọi domain event đều phải phát lên message broker. Khi công bố ra ngoài, cần chọn dữ liệu và ý nghĩa ổn định. Ví dụ:

~~~text
Tên: PaymentCaptured
Ý nghĩa: Payment context xác nhận đã thu thành công số tiền của một giao dịch.
Trường gợi ý:
  eventId        : định danh duy nhất của sự kiện
  paymentId      : định danh khoản thanh toán
  orderId        : tham chiếu đơn hàng
  amount         : số tiền được thu
  currency       : loại tiền
  occurredAt     : thời điểm sự kiện nghiệp vụ xảy ra
  schemaVersion  : phiên bản hợp đồng
~~~

Bộ trường trên là minh họa, chưa phải thiết kế áp dụng ngay. Cần làm rõ quyền truy cập dữ liệu, định danh, khả năng tái phát sự kiện, múi giờ và tính chính xác của số tiền. Hạn chế dữ liệu cá nhân hoặc bí mật thanh toán trong message phát rộng.

### 8.2. Event Storming không bắt buộc event sourcing

| Khái niệm | Đích sử dụng |
| --- | --- |
| **Event Storming** | Kỹ thuật cộng tác để khám phá và mô hình hóa hành vi nghiệp vụ |
| **Event-driven architecture** | Kiến trúc cho phép thành phần phản ứng với thông báo về sự kiện |
| **Event sourcing** | Cách lưu trạng thái bằng lịch sử sự kiện làm nguồn dữ liệu gốc |
| **CQRS** | Phân tách mô hình lệnh/thay đổi với mô hình đọc khi có lý do phù hợp |

Có thể làm Event Storming rồi xây một hệ thống CRUD dùng transaction thông thường. Ngược lại, việc chọn event sourcing đòi hỏi cân nhắc projection, thay đổi schema, replay, xóa dữ liệu, audit và vận hành riêng; workshop không tự trả lời các vấn đề đó.

### 8.3. Những rủi ro cần thiết kế khi phản ứng bất đồng bộ

Nếu quyết định dùng message/event để nối các context, bản đồ workshop cho biết **khi nào cần phản ứng**; kiến trúc phải giải quyết thêm:

- **Phát hành đáng tin:** tránh trường hợp transaction lưu trạng thái thành công nhưng không phát được event; cân nhắc transactional outbox hoặc cơ chế tương đương.
- **Giao lặp:** nhiều broker đảm bảo at-least-once; consumer cần xử lý idempotent bằng event ID hoặc khóa nghiệp vụ, không giả định chỉ nhận đúng một lần.
- **Thứ tự:** xác định thứ tự cần giữ theo payment/order, thay vì giả định tất cả message toàn hệ thống có thứ tự.
- **Thử lại và lỗi kéo dài:** backoff, giới hạn retry, lưu lỗi để điều tra và cách khôi phục tác vụ.
- **Dữ liệu cuối cùng nhất quán:** UI có thể hiển thị trạng thái “đang xử lý” trong thời gian chờ; cần làm rõ mức trễ chấp nhận được.
- **Theo dõi:** correlation ID, tracing, log có ngữ cảnh nghiệp vụ, metric về độ trễ và tỷ lệ xử lý lỗi.
- **Tiến hóa hợp đồng:** schema versioning, khả năng tương thích và lộ trình thay đổi consumer.
- **Bảo mật:** chỉ phát dữ liệu cần thiết, phân quyền người đọc/ghi và chính sách lưu giữ phù hợp.

Các điểm này là vấn đề thiết kế **sau khi** làm rõ ý nghĩa nghiệp vụ, không cần đưa mọi chi tiết hạ tầng lên bảng Big Picture.

### 8.4. Quy trình kéo dài: điều phối hay phản ứng phân tán?

Thanh toán, giữ kho, chuẩn bị và giao hàng có thể trải qua nhiều context và không nằm trong một transaction ACID toàn hệ thống. Event Storming giúp thấy các bước, hành động bù và điểm dừng. Khi triển khai, có thể cân nhắc:

- **Choreography:** mỗi context phản ứng với sự kiện quan trọng, phù hợp luồng đơn giản và quan hệ rõ; quá nhiều phản ứng ngầm dễ khó theo dõi.
- **Orchestration / process manager:** một thành phần theo dõi tiến trình và phát command tương ứng, phù hợp workflow dài với trạng thái và timeout phức tạp; cần tránh biến nó thành nơi chứa mọi quy tắc nghiệp vụ.
- **Saga / hành động bù:** với các bước phân tán, có thể cần hoàn tiền hoặc giải phóng tồn kho khi bước sau thất bại. Hành động bù là nghiệp vụ mới, không phải “rollback database” trên các service.

Lựa chọn phụ thuộc mức độ phức tạp, trách nhiệm, độ quan sát và khả năng kiểm soát lỗi.

## 9. Kỹ thuật hỏi để khám phá sâu

Facilitator cần tạo không gian cho những người hiểu nghiệp vụ giải thích, đặc biệt khi cùng một câu được hiểu theo nhiều cách. Một bộ câu hỏi hữu ích:

**Hỏi về thời gian và nguyên nhân**

- Điều gì phải xảy ra trước để sự kiện này hợp lệ?
- Sự kiện này là tức thời, có thể trễ hay cần xác nhận thủ công?
- Trường hợp nào khiến nó không bao giờ xảy ra?
- Nếu hai sự kiện xảy ra gần đồng thời, cái nào được ưu tiên?

**Hỏi về quyết định và trách nhiệm**

- Ai có quyền chấp nhận hoặc từ chối hành động?
- Quy tắc nào đang được áp dụng? Có ngoại lệ được phê duyệt không?
- Khi xử lý lỗi, ai được thông báo và ai có quyền sửa?
- Bộ phận nào chịu trách nhiệm về tính đúng đắn của thông tin?

**Hỏi về ngôn ngữ**

- “Đã xác nhận” là xác nhận điều gì và bởi ai?
- Từ này có nghĩa giống nhau tại kho, thanh toán và chăm sóc khách hàng không?
- Có hai thuật ngữ khác nhau đang mô tả cùng một sự kiện không?
- Có một thuật ngữ chung đang che giấu hai hành vi khác nhau không?

**Hỏi về sự thật đối lập**

- Tuần trước có tình huống nào đi ngược quy trình chuẩn?
- Nếu hệ thống thanh toán trả kết quả khác với sao kê, nhóm vận hành làm gì?
- Khi không biết kết quả, người dùng được phép thử lại hay phải chờ?

Nên dùng các ví dụ cụ thể có thời điểm và tác nhân, thay vì thảo luận hoàn toàn trừu tượng.

## 10. Kế hoạch workshop mẫu 120 phút

Một lịch tham khảo cho buổi khám phá luồng đặt hàng:

| Thời lượng | Hoạt động | Kết quả mong đợi |
| --- | --- | --- |
| 0–10 phút | Nêu mục tiêu, phạm vi, quy ước thẻ | Hiểu chung câu hỏi dẫn đường |
| 10–25 phút | Mọi người viết domain event độc lập | Bộ sự kiện ban đầu đa góc nhìn |
| 25–45 phút | Ghép timeline và các nhánh | Dòng hành vi được kể thành chuyện |
| 45–60 phút | Phát hiện hotspot và bất đồng thuật ngữ | Danh sách vấn đề cần đào sâu |
| 60–75 phút | Bổ sung actor, command, policy | Quan hệ nguyên nhân và quyết định |
| 75–95 phút | Tìm bất biến, hệ thống ngoài, read model | Điểm trách nhiệm và dữ liệu đầu vào |
| 95–110 phút | Nhóm candidate bounded context | Các đường ranh giới giả thuyết |
| 110–120 phút | Chốt câu hỏi mở và người phụ trách | Bản đồ được lưu cùng hành động tiếp theo |

Quy trình phức tạp có thể cần nửa ngày hoặc nhiều buổi. Tốt hơn là chia thành Big Picture rồi các buổi Process Modeling theo hotspot, tránh cố làm chi tiết toàn hệ thống trong một lần.

### Vai trò của facilitator trong suốt buổi

- Cho chuyên gia nghiệp vụ lên tiếng trước khi kỹ sư đề xuất giải pháp.
- Mời những người ít phát biểu xác nhận luồng và ngoại lệ; tránh để một bộ phận định nghĩa toàn bộ nghiệp vụ.
- Khi nhóm tranh luận không có dữ liệu, ghi hotspot và người xác nhận.
- Khi xuất hiện tên bảng, tên endpoint hoặc broker, hỏi hành vi nghiệp vụ mà kỹ thuật đó đang phục vụ.
- Ghi rõ các nhánh “hiện tại đang vận hành” và “mong muốn sau cải tiến”, không vô tình trộn chúng.
- Giữ bản đồ thay đổi linh hoạt; thẻ có thể đổi vị trí và tên khi nhóm học được điều mới.

## 11. Đầu ra sử dụng được sau workshop

Bản đồ note là phương tiện học cùng nhau. Để chuyển hiểu biết thành công việc kiến trúc, nên ghi lại các sản phẩm cụ thể sau:

### 11.1. Bảng thuật ngữ nghiệp vụ

| Thuật ngữ | Định nghĩa làm việc | Context | Câu hỏi còn mở |
| --- | --- | --- | --- |
| Đơn đã đặt | Yêu cầu mua đã được hệ thống chấp nhận để tiếp tục xử lý | Ordering | Có giữ giá tại thời điểm này không? |
| Thanh toán thành công | Cổng thanh toán xác nhận đã thu khoản tiền | Payments | Có cần chờ đối soát cuối ngày không? |
| Hàng đã được giữ | Số lượng dành cho đơn trong một thời hạn | Inventory | Thời hạn có thể gia hạn không? |

Nếu chưa thống nhất định nghĩa, đánh dấu là **giả thuyết** và nêu người cần xác nhận; không âm thầm coi thuật ngữ là chuẩn.

### 11.2. Bảng candidate bounded context và quan hệ

Với mỗi vùng, ghi: mục tiêu nghiệp vụ, ngôn ngữ, lệnh do vùng sở hữu, sự kiện do vùng công bố, dữ liệu do vùng làm nguồn sự thật, phụ thuộc vào vùng khác và câu hỏi về nhất quán. Vẽ context map khi các quan hệ đã đủ rõ.

### 11.3. Danh sách hotspot có người phụ trách

~~~text
HOTSPOT-01: Thanh toán thành công nhưng giữ hàng thất bại
Mức ảnh hưởng: có thể thu tiền mà không thể giao hàng
Chưa rõ: tự hoàn tiền hay đưa vào hàng đợi xử lý thủ công?
Người xác nhận: đại diện Payments + vận hành
Bằng chứng cần tìm: quy trình đối soát, chính sách hoàn tiền, số liệu lỗi
Trạng thái: chờ xác minh
~~~

Không dùng những hotspot chưa giải quyết để suy diễn ra luồng chuẩn.

### 11.4. Giả thuyết và quyết định kiến trúc

Ví dụ một giả thuyết:

> “Ordering và Inventory có thể tách module vì mỗi bên có quy tắc và nguồn sự thật riêng. Trước mắt thử mô hình modular monolith để giữ khả năng thay đổi nhanh; việc tách process chỉ xem xét khi có nhu cầu độc lập triển khai hoặc mở rộng đã được chứng minh.”

Viết lại theo bối cảnh thực tế, ghi lý do và tiêu chí đánh giá. Với quyết định đã chốt, dùng ADR ngắn: **bối cảnh → lựa chọn → lý do → hệ quả → điều kiện xem lại**. Event Storming cung cấp dữ liệu đầu vào cho ADR, không thay thế đánh giá kỹ thuật.

## 12. Các lỗi thường gặp và cách xử lý

| Dấu hiệu | Hệ quả | Cách chỉnh trong workshop |
| --- | --- | --- |
| Bắt đầu bằng tên microservice, bảng hoặc API | Khóa trước ranh giới kỹ thuật | Quay về điều đã xảy ra, ai quyết định, lý do nghiệp vụ |
| Viết event ở dạng mệnh lệnh, ví dụ “Gửi email” | Nhầm command với sự thật | Hỏi “Email đã được gửi chưa?” và xác định ai yêu cầu gửi |
| Chỉ mô tả happy path | Không thấy hành vi thật khi lỗi | Hỏi timeout, hủy, thử lại, trùng callback, thao tác thủ công |
| Coi một thẻ là một message/topic phải triển khai | Tạo độ phức tạp dư thừa | Phân biệt thẻ khám phá với hợp đồng tích hợp |
| Gộp các thuật ngữ giống chữ nhưng khác nghĩa | Ranh giới trách nhiệm mơ hồ | Đặt định nghĩa và context cạnh mỗi thuật ngữ |
| Một người độc thoại cả buổi | Bản đồ thiên lệch | Dành thời gian viết độc lập, hỏi lần lượt từng vai trò |
| Bất đồng kéo dài và không tiến triển | Mất thời gian, vẫn thiếu bằng chứng | Gắn hotspot, giao người xác nhận, tiếp tục khám phá |
| Chia mỗi danh từ thành một service | Service quá nhỏ, giao tiếp chằng chịt | Nhóm theo hành vi, quy tắc, tính nhất quán và team ownership |
| Dùng sự kiện kỹ thuật như “RowUpdated” làm ngôn ngữ chính | Che giấu ý nghĩa nghiệp vụ | Đổi sang sự kiện mà người nghiệp vụ có thể xác nhận |
| Không ghi lại bản đồ và quyết định | Workshop không đi vào triển khai | Lưu bản đồ, glossary, action owner, ADR và câu hỏi mở |

## 13. Bài tập thực hành

**Bối cảnh:** một nền tảng đặt lịch khám cho phép bệnh nhân chọn khung giờ; một khung có thể giữ trong 10 phút; bệnh nhân có thể hủy; phòng khám có thể đổi lịch; tin nhắn xác nhận được gửi sau khi lịch được chấp nhận.

**Yêu cầu:**

1. Viết ít nhất tám domain event theo ngôn ngữ nghiệp vụ, gồm cả nhánh thất bại.
2. Đặt các sự kiện vào timeline, tách nhánh đặt thành công, hết hạn giữ chỗ và phòng khám đổi lịch.
3. Chọn ba event và hỏi command/actor/policy nào dẫn đến hoặc phản ứng sau chúng.
4. Đánh dấu ít nhất năm hotspot, đặc biệt trường hợp hai bệnh nhân giữ cùng một chỗ, thông báo đến trễ và yêu cầu hủy sát giờ.
5. Đề xuất bounded context ứng viên, giải thích ranh giới bằng quy tắc và trách nhiệm.
6. Xác định một bất biến bắt buộc được bảo vệ tức thì; một kết quả có thể cập nhật bất đồng bộ.
7. Viết một ADR giả định ngắn cho lựa chọn modular monolith hoặc microservices; nêu điều kiện có thể làm đổi quyết định.

**Gợi ý event hợp lệ:** “Khung giờ đã được giữ”, “Lượt giữ chỗ đã hết hạn”, “Lịch hẹn đã được xác nhận”, “Yêu cầu đặt lịch đã bị từ chối”, “Lịch hẹn đã được hủy”, “Phòng khám đã đổi giờ hẹn”, “Thông báo xác nhận đã được gửi”. Hãy tự bổ sung hành vi gắn với chính sách của bài toán thay vì mặc định những tên này là toàn bộ quy trình.

Một hướng trả lời cho bất biến: tại một thời điểm, cùng một bác sĩ và khung giờ không được có hai lịch hẹn **đã xác nhận** xung đột. Phần thông báo SMS có thể diễn ra sau khi lịch được xác nhận; phải có trạng thái/thao tác xử lý khi gửi thất bại, nhưng không cần đưa việc gửi SMS vào cùng transaction xác nhận lịch.

## 14. Checklist ứng dụng vào một dự án thực

Trước buổi workshop:

- [ ] Có câu hỏi dẫn đường, phạm vi rõ và người hiểu nghiệp vụ thực tế.
- [ ] Có bảng trắng/canvas, chú giải ký hiệu và người ghi chép.
- [ ] Có sự thống nhất rằng sự kiện là điều đã xảy ra, thiết kế hạ tầng để sau.

Trong workshop:

- [ ] Có cả nhánh bình thường và nhánh lỗi, trễ, timeout, hủy.
- [ ] Với sự kiện quan trọng, xác định được tác nhân, command/policy và quy tắc quyết định.
- [ ] Hotspot không được che giấu và thuật ngữ tranh cãi được ghi lại.
- [ ] Ranh giới ứng viên dựa trên hành vi và trách nhiệm, không dựa riêng vào bảng dữ liệu.
- [ ] Người làm nghiệp vụ đã xác nhận phần mà họ thực sự hiểu và chỉ rõ phần chưa chắc.

Sau workshop:

- [ ] Lưu bản đồ, glossary, danh sách câu hỏi kèm người phụ trách.
- [ ] Chọn một hoặc hai luồng quan trọng để mô hình chi tiết hơn.
- [ ] Tách giả thuyết về bounded context khỏi quyết định tách service.
- [ ] Đánh giá nhất quán, độ trễ, khả năng vận hành và tích hợp khi đi vào thiết kế.
- [ ] Chỉ chốt ADR khi có căn cứ đủ và đã nêu hệ quả đánh đổi.

## 15. Ghi nhớ

Event Storming đặt **hành vi, thời gian và quyết định nghiệp vụ** lên trung tâm cuộc thảo luận. Bắt đầu bằng sự kiện đã xảy ra giúp phát hiện các câu chuyện mà danh sách yêu cầu chức năng hoặc sơ đồ bảng dữ liệu thường bỏ sót. Khi đã nhận biết được command, actor, policy, ngoại lệ và ranh giới ngôn ngữ, nhóm có chất liệu tốt để phân rã miền nghiệp vụ và lựa chọn kiến trúc.

Giá trị lớn nhất của buổi workshop là những người liên quan cùng hiểu quy trình thực tế và những điều chưa biết. Mô hình sự kiện là công cụ để học và giao tiếp; lựa chọn giữa monolith, modular monolith và microservices là bước thiết kế tiếp theo dựa trên nhu cầu thực tế của hệ thống.
