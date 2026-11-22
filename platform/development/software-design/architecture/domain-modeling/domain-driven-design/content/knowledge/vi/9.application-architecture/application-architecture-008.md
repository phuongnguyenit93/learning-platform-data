# Lựa chọn kiến trúc vừa đủ thay vì áp dụng mọi mẫu cùng lúc

Domain-Driven Design (DDD) giúp đội phát triển hiểu miền nghiệp vụ, xác định Bounded Context và xây dựng mô hình phản ánh các quy tắc quan trọng. Kiến trúc ứng dụng quyết định cách tổ chức mã nguồn, ranh giới phụ thuộc, giao tiếp giữa các phần và cách hệ thống được triển khai, vận hành.

Có nhiều mẫu kiến trúc hữu ích như Layered Architecture, Hexagonal Architecture, Modular Monolith, Microservices, CQRS và Event-Driven Architecture. Tuy nhiên, chúng giải quyết những vấn đề ở các cấp độ khác nhau. Áp dụng tất cả cùng lúc có thể tạo thêm lớp trung gian, giao thức, cơ sở dữ liệu và quy trình vận hành mà nghiệp vụ chưa cần đến.

Nguyên tắc thực tế là **chọn kiến trúc dựa trên vấn đề cần giải quyết, ràng buộc hiện có và thuộc tính chất lượng quan trọng**. Bắt đầu bằng cấu trúc đơn giản có thể bảo vệ mô hình miền; chỉ bổ sung mẫu kiến trúc khi có bằng chứng cho thấy cấu trúc hiện tại không đáp ứng được nhu cầu.

## 1. Kiến trúc ứng dụng cần phục vụ điều gì?

Kiến trúc ứng dụng là tập hợp các quyết định cấu trúc có ảnh hưởng lâu dài đến cách phần mềm được phát triển và vận hành. Nó bao gồm cách chia trách nhiệm, hướng phụ thuộc, cách các thành phần giao tiếp, nơi quản lý dữ liệu và cách hệ thống được đóng gói, triển khai.

Trong một hệ thống theo DDD, kiến trúc cần giúp:

- Giữ các quy tắc nghiệp vụ quan trọng dễ tìm, dễ hiểu và dễ kiểm thử.
- Bảo vệ mô hình của từng Bounded Context khỏi chi tiết kỹ thuật thay đổi thường xuyên.
- Làm rõ quyền sở hữu dữ liệu và trách nhiệm giữa các context.
- Cho phép thay đổi một phần hệ thống với phạm vi ảnh hưởng có thể kiểm soát.
- Đáp ứng yêu cầu về hiệu năng, độ tin cậy, bảo mật, khả năng mở rộng và vận hành.
- Hỗ trợ đội ngũ phát triển, triển khai và xử lý sự cố với năng lực thực tế.

Một kiến trúc tốt không nhất thiết có nhiều service, nhiều tầng hoặc nhiều công nghệ. Nó phù hợp với quy mô bài toán và giúp tổ chức thay đổi phần mềm với chi phí chấp nhận được.

### 1.1. Phân biệt kiến trúc nghiệp vụ và kiến trúc triển khai

DDD nói về domain, subdomain và Bounded Context để mô tả cách hiểu và phân chia trách nhiệm nghiệp vụ. Kiến trúc ứng dụng đưa ra quyết định về cách hiện thực hóa các ranh giới đó.

Ví dụ:

- **Bounded Context:** Ordering chịu trách nhiệm về đơn hàng và các quy tắc xác nhận đơn.
- **Module:** mã nguồn Ordering có thể được tổ chức thành một module riêng trong ứng dụng.
- **Process hoặc service:** module có thể chạy trong cùng tiến trình với các module khác hoặc được triển khai thành service độc lập.
- **Database:** module có thể sở hữu schema riêng trong một database dùng chung, hoặc có database riêng tùy yêu cầu.

Không có ánh xạ bắt buộc một-một giữa Bounded Context, module, service và database. Tách Bounded Context là quyết định về mô hình và ngôn ngữ; tách service là quyết định triển khai có thêm chi phí giao tiếp, vận hành và quản lý dữ liệu phân tán.

### 1.2. Không chọn kiến trúc chỉ vì công nghệ đang phổ biến

Một công nghệ hoặc mẫu kiến trúc có thể rất phù hợp với một tổ chức nhưng không cần thiết với tổ chức khác. Trước khi chọn, hãy diễn đạt vấn đề bằng ngôn ngữ cụ thể:

- Thay đổi chính sách giá thường xuyên nhưng mỗi lần sửa lại ảnh hưởng đến nhiều phần không liên quan.
- Báo cáo cần truy vấn dữ liệu lớn và đang làm chậm giao dịch đặt hàng.
- Các đội cần triển khai độc lập nhưng hiện phải phát hành toàn bộ hệ thống cùng lúc.
- Một nhà cung cấp bên ngoài thay đổi schema khiến mô hình nội bộ bị ảnh hưởng.
- Tác vụ gửi email có thể chậm hoặc thử lại mà không giữ request của khách hàng.

Những vấn đề cụ thể giúp chọn đúng giải pháp. Câu nói “chúng ta cần microservices” hoặc “phải dùng CQRS” chưa phải mô tả vấn đề.

## 2. Xác định ràng buộc và thuộc tính chất lượng

Trước khi so sánh mẫu kiến trúc, hãy xác định điều hệ thống phải làm tốt và những giới hạn mà đội không thể bỏ qua.

### 2.1. Thuộc tính chất lượng thường gặp

| Thuộc tính | Câu hỏi cần trả lời | Ví dụ yêu cầu |
|---|---|---|
| Maintainability – Khả năng bảo trì | Có thể hiểu và thay đổi quy tắc với phạm vi ảnh hưởng nhỏ không? | Thay đổi chính sách hoàn trả không làm hỏng báo cáo khách hàng |
| Modifiability – Khả năng thay đổi | Một phần có thể thay đổi mà không cần sửa nhiều phần khác không? | Quy tắc khuyến mãi được điều chỉnh độc lập |
| Performance – Hiệu năng | Thời gian phản hồi và thông lượng cần đạt là bao nhiêu? | 95% yêu cầu tra cứu đơn phản hồi trong 300 ms ở tải dự kiến |
| Scalability – Khả năng mở rộng | Phần nào cần tăng năng lực khi tải tăng? | Tìm kiếm cần mở rộng theo lưu lượng đọc |
| Availability – Tính sẵn sàng | Hệ thống có thể gián đoạn bao lâu? | Dịch vụ đặt hàng cần đáp ứng mục tiêu sẵn sàng đã cam kết |
| Reliability – Độ tin cậy | Làm sao tránh mất, lặp hoặc xử lý sai giao dịch? | Một yêu cầu thanh toán lặp không tạo hai lần ghi nhận |
| Security – Bảo mật | Ai được phép xem hoặc thay đổi dữ liệu? | Chỉ nhân viên có thẩm quyền mới phê duyệt hoàn tiền |
| Testability – Khả năng kiểm thử | Có thể kiểm tra quy tắc mà không cần dựng toàn bộ hạ tầng không? | Quy tắc tính phí được kiểm thử độc lập |
| Operability – Khả năng vận hành | Đội có thể triển khai, quan sát và khôi phục sự cố không? | Có log, metric, trace và quy trình khôi phục phù hợp |

Không nên ghi tất cả thuộc tính ở mức “rất quan trọng”. Hãy chọn một số thuộc tính có ảnh hưởng lớn nhất, mô tả tình huống cụ thể và xác định mức chấp nhận được.

### 2.2. Viết kịch bản chất lượng

Một kịch bản chất lượng nên có:

1. **Nguồn kích hoạt:** người dùng, hệ thống khác hoặc sự kiện nào tạo ra tình huống.
2. **Điều kiện:** tải, trạng thái hệ thống, quy mô dữ liệu hoặc hoàn cảnh xảy ra.
3. **Phản hồi mong muốn:** hệ thống cần làm gì.
4. **Tiêu chí đo:** thời gian, tỷ lệ thành công, mức mất dữ liệu hoặc giới hạn khác.

Ví dụ:

> Khi khách hàng gửi yêu cầu xác nhận đơn trong giờ cao điểm với 1.000 yêu cầu mỗi giây, hệ thống phải phản hồi kết quả tiếp nhận trong 500 ms ở phân vị 95, không xác nhận hai lần cùng một đơn do request bị gửi lặp.

Kịch bản này giúp đội đánh giá cần tối ưu luồng đồng bộ, cơ chế idempotency, lưu trữ hay khả năng mở rộng. Nó hữu ích hơn câu “hệ thống phải nhanh và chịu tải cao”.

### 2.3. Ghi nhận ràng buộc thực tế

Các ràng buộc có thể bao gồm:

- Năng lực và kinh nghiệm của đội ngũ.
- Ngân sách, thời hạn và mức độ chấp nhận rủi ro.
- Hệ thống cũ và hợp đồng với đối tác.
- Quy định pháp lý, lưu trữ dữ liệu và yêu cầu kiểm toán.
- Hạ tầng, nền tảng triển khai và công cụ vận hành sẵn có.
- Cách tổ chức đội ngũ và quyền sở hữu sản phẩm.
- Mức độ độc lập cần thiết giữa các nhóm.

Kiến trúc phải có thể vận hành được trong tổ chức hiện tại. Một hệ thống microservices đòi hỏi đội ngũ có khả năng quản lý nhiều dịch vụ, quan sát phân tán, triển khai tự động, bảo mật giao tiếp và xử lý lỗi mạng. Nếu tổ chức chưa có những năng lực đó, chi phí chuyển đổi có thể lớn hơn lợi ích.

## 3. Những mẫu kiến trúc giải quyết các vấn đề khác nhau

Các mẫu dưới đây không phải những lựa chọn loại trừ nhau. Chúng tác động ở các chiều khác nhau: tổ chức phụ thuộc trong mã nguồn, bảo vệ miền, phân chia đơn vị triển khai, mô hình đọc/ghi và cách giao tiếp.

### 3.1. Layered Architecture – Kiến trúc phân lớp

Layered Architecture chia ứng dụng thành các lớp trách nhiệm. Một cấu trúc thường gặp:

- **Presentation:** nhận request, xác thực đầu vào ở mức giao diện và trả response.
- **Application:** điều phối use case, quản lý luồng công việc và gọi các thành phần cần thiết.
- **Domain:** chứa mô hình miền, quy tắc, invariant và hành vi nghiệp vụ.
- **Infrastructure:** triển khai lưu trữ, truy cập mạng, gửi email và tích hợp công nghệ.

~~~mermaid
flowchart TD
    P["Presentation"] --> A["Application"]
    A --> D["Domain"]
    A --> I["Infrastructure"]
    I --> D
~~~

Sơ đồ này chỉ thể hiện cách phân chia trách nhiệm ở mức khái quát. Hướng phụ thuộc thực tế cần được kiểm soát để domain không bị ràng buộc vào framework hoặc database.

**Phù hợp khi:**

- Ứng dụng có quy mô nhỏ đến vừa và luồng xử lý tương đối rõ.
- Đội cần cấu trúc dễ hiểu, dễ onboarding.
- Các lớp trách nhiệm có thể tách biệt mà không cần nhiều cơ chế giao tiếp.

**Rủi ro khi dùng không đúng:**

- Tạo quá nhiều lớp chỉ chuyển tiếp lời gọi mà không có trách nhiệm.
- Đưa toàn bộ nghiệp vụ vào Application Service hoặc controller.
- Domain phụ thuộc trực tiếp vào ORM, framework hoặc hạ tầng.
- Cấu trúc phân lớp nhưng không có ranh giới module rõ ràng, dẫn đến phụ thuộc chéo.

Layered Architecture không có nghĩa mọi thao tác phải đi qua mọi lớp. Hãy giữ các lớp có trách nhiệm rõ ràng và để luồng đơn giản khi use case không cần thêm điều phối.

### 3.2. Hexagonal Architecture – Kiến trúc lục giác

Hexagonal Architecture (Ports and Adapters) đặt logic ứng dụng và miền ở trung tâm, giao tiếp với thế giới bên ngoài thông qua **port** và **adapter**.

- **Port:** mô tả một điểm giao tiếp hoặc khả năng mà ứng dụng cần cung cấp/tiếp nhận.
- **Adapter:** triển khai cách kết nối cụ thể, chẳng hạn HTTP, database, message broker hoặc nhà cung cấp thanh toán.

Ví dụ:

- HTTP Controller là adapter nhận lệnh từ người dùng.
- OrderRepository là port mà ứng dụng cần để lưu và tải đơn hàng.
- Adapter dùng JPA hoặc SQL thực hiện port đó.
- Adapter thanh toán giao tiếp với cổng thanh toán bên ngoài.

~~~mermaid
flowchart TB
    subgraph External["Bên ngoài"]
        HTTP["HTTP / UI"]
        DB["Database"]
        PSP["Payment Provider"]
    end
    subgraph App["Ứng dụng và miền"]
        IN["Input Port / Use Case"]
        DOMAIN["Domain Model"]
        OUT["Output Ports"]
        IN --> DOMAIN
        IN --> OUT
    end
    HTTP --> IN
    OUT --> DB
    OUT --> PSP
~~~

**Phù hợp khi:**

- Muốn bảo vệ mô hình miền khỏi framework và công nghệ bên ngoài.
- Cần kiểm thử use case bằng adapter giả lập.
- Có nhiều cách giao tiếp với cùng một năng lực, chẳng hạn HTTP và message consumer.
- Muốn thay đổi database hoặc nhà cung cấp mà ít ảnh hưởng đến miền.

**Rủi ro khi dùng không đúng:**

- Tạo interface cho mọi lớp dù không có nhu cầu thay thế hoặc kiểm soát phụ thuộc.
- Adapter chỉ đổi tên lời gọi, không có trách nhiệm chuyển đổi.
- Port bị thiết kế theo API của database hoặc framework thay vì nhu cầu của ứng dụng.
- Cấu trúc thư mục phức tạp hơn nhiều so với số use case thực tế.

Hexagonal Architecture không yêu cầu phải có sáu cạnh hoặc một sơ đồ lục giác trong mã nguồn. Ý tưởng cốt lõi là xác định ranh giới giao tiếp và giữ phụ thuộc hướng vào phần logic quan trọng.

### 3.3. Modular Monolith – Ứng dụng nguyên khối có module

Modular Monolith là một ứng dụng được triển khai như một đơn vị, nhưng mã nguồn và trách nhiệm được chia thành các module có ranh giới rõ.

Ví dụ:

- Ordering Module sở hữu quy tắc và dữ liệu đơn hàng.
- Pricing Module sở hữu quy tắc báo giá.
- Inventory Module sở hữu trạng thái và quy tắc tồn kho.
- Identity Module quản lý tài khoản và quyền truy cập.

Các module có thể giao tiếp qua API nội bộ, application interface hoặc sự kiện nội bộ. Cần tránh việc một module truy cập trực tiếp bảng hoặc lớp nội bộ của module khác.

**Phù hợp khi:**

- Sản phẩm hoặc đội ngũ chưa đủ lớn để cần triển khai độc lập nhiều service.
- Muốn có ranh giới miền rõ ràng nhưng vẫn giữ vận hành đơn giản.
- Nhiều use case cần transaction nhất quán trong cùng ứng dụng.
- Tổ chức muốn phát triển và kiểm chứng ranh giới trước khi tách triển khai.

**Rủi ro khi dùng không đúng:**

- Module chỉ là thư mục, mọi nơi vẫn gọi trực tiếp lẫn nhau.
- Có database dùng chung nhưng không rõ module nào sở hữu bảng.
- Một module thay đổi làm nhiều module khác phải sửa theo.
- Dần hình thành một khối nguyên khối không có ranh giới thực.

Modular Monolith thường là điểm khởi đầu hợp lý cho một sản phẩm mới. Nó cho phép học từ ranh giới nghiệp vụ trong khi giữ chi phí triển khai và vận hành thấp.

### 3.4. Microservices – Kiến trúc dịch vụ nhỏ

Microservices chia hệ thống thành các service có thể triển khai và vận hành độc lập. Mỗi service nên sở hữu một năng lực nghiệp vụ đủ rõ, có trách nhiệm dữ liệu và hợp đồng giao tiếp được quản lý.

Trong DDD, Bounded Context có thể là một ứng viên để tổ chức ranh giới service, nhưng không có quy tắc bắt buộc một context tương ứng một service. Một context có thể được triển khai bằng nhiều service vì lý do tải hoặc vận hành; nhiều context nhỏ cũng có thể cùng nằm trong một đơn vị triển khai nếu điều đó phù hợp.

**Lợi ích có thể có:**

- Triển khai và mở rộng từng năng lực độc lập.
- Đội ngũ có thể sở hữu vòng đời của service rõ hơn.
- Cô lập một số lỗi và giới hạn phạm vi thay đổi.
- Chọn công nghệ phù hợp cho từng nhu cầu khi tổ chức đủ năng lực quản trị.

**Chi phí và rủi ro:**

- Giao tiếp qua mạng có độ trễ, lỗi và trạng thái không chắc chắn.
- Transaction phân tán và dữ liệu nhất quán cuối cùng khó xử lý hơn.
- Cần quản lý phiên bản API, sự kiện và hợp đồng giữa các service.
- Quan sát hệ thống cần log, metric, trace và tương quan request.
- Triển khai, bảo mật, cấu hình và xử lý sự cố phức tạp hơn.
- Một use case xuyên nhiều service có thể tạo chuỗi phụ thuộc và khó kiểm thử.

Microservices phù hợp khi có lý do rõ ràng về khả năng triển khai độc lập, tải khác biệt, quyền sở hữu đội ngũ hoặc ranh giới vận hành. Chúng không tự động làm mô hình miền tốt hơn và không phải điều kiện để áp dụng DDD.

### 3.5. CQRS – Tách mô hình đọc và ghi

CQRS (Command Query Responsibility Segregation) tách trách nhiệm xử lý thay đổi trạng thái (**Command**) khỏi trách nhiệm truy vấn dữ liệu (**Query**).

- Command diễn đạt ý định thay đổi, chẳng hạn ConfirmOrder.
- Query yêu cầu thông tin, chẳng hạn GetOrderDetails.
- Mô hình ghi tập trung bảo vệ quy tắc và invariant.
- Mô hình đọc có thể được tổ chức để trả dữ liệu thuận tiện cho từng màn hình hoặc báo cáo.

CQRS có thể chỉ là hai đường xử lý trong một ứng dụng và dùng cùng database. Nó không bắt buộc phải có message broker, event sourcing hoặc hai service riêng.

**Cân nhắc CQRS khi:**

- Mô hình đọc và ghi có nhu cầu hoặc hình dạng dữ liệu khác nhau rõ rệt.
- Truy vấn phức tạp làm ảnh hưởng đến luồng cập nhật quan trọng.
- Có nhiều màn hình hoặc báo cáo cần projection riêng.
- Cần mở rộng năng lực đọc độc lập với năng lực ghi.

**Không cần CQRS khi:**

- CRUD đơn giản, truy vấn và cập nhật có cùng cấu trúc.
- Một mô hình dữ liệu duy nhất vẫn dễ hiểu và đủ hiệu năng.
- Đội chưa có nhu cầu xử lý độ trễ đồng bộ hoặc dữ liệu đọc dẫn xuất.

CQRS làm tăng số mô hình cần duy trì và có thể tạo độ trễ giữa dữ liệu ghi với dữ liệu đọc. Nếu dùng projection bất đồng bộ, giao diện và nghiệp vụ cần hiểu rằng kết quả đọc có thể chưa phản ánh ngay lệnh vừa thực hiện.

### 3.6. Event-Driven Architecture – Kiến trúc hướng sự kiện

Event-Driven Architecture sử dụng sự kiện để thông báo một điều đã xảy ra và cho phép thành phần khác phản ứng. Sự kiện có thể được truyền trong cùng tiến trình hoặc qua message broker giữa các ứng dụng.

Ví dụ:

- Ordering phát OrderConfirmed.
- Fulfillment nhận sự kiện và tạo yêu cầu chuẩn bị hàng.
- Notification nhận sự kiện và gửi thông báo cho khách.
- Analytics nhận sự kiện để cập nhật số liệu.

**Phù hợp khi:**

- Các bên có thể xử lý độc lập và không cần kết quả đồng bộ ngay.
- Muốn giảm phụ thuộc thời gian giữa producer và consumer.
- Có nhiều consumer cần phản ứng với cùng một sự kiện.
- Cần xử lý tác vụ nền, thử lại hoặc hấp thụ tải theo hàng đợi.

**Rủi ro cần quản lý:**

- Consumer có thể nhận sự kiện trùng hoặc sai thứ tự.
- Sự kiện có thể đến trễ hoặc không đến nếu hệ thống không có cơ chế bảo đảm phù hợp.
- Dữ liệu giữa các context thường nhất quán cuối cùng, không nhất quán tức thời.
- Khó truy vết một quy trình đi qua nhiều consumer.
- Thay đổi schema có thể ảnh hưởng đến nhiều bên tiêu thụ.

Event-driven không đồng nghĩa với việc mọi lời gọi phải chuyển thành event. Nếu người dùng cần kết quả ngay để quyết định tiếp theo, giao tiếp đồng bộ có thể đơn giản và rõ hơn.

### 3.7. So sánh nhanh

| Mẫu kiến trúc | Vấn đề chính được giải quyết | Chi phí hoặc rủi ro nổi bật |
|---|---|---|
| Layered | Chia trách nhiệm theo lớp | Lớp trung gian rỗng, phụ thuộc sai hướng |
| Hexagonal | Bảo vệ logic miền qua port và adapter | Quá nhiều interface và adapter không cần thiết |
| Modular Monolith | Ranh giới module trong một đơn vị triển khai | Ranh giới module bị phá vỡ theo thời gian |
| Microservices | Triển khai, mở rộng và sở hữu độc lập | Vận hành phân tán, mạng, dữ liệu và hợp đồng |
| CQRS | Tách nhu cầu đọc và ghi | Đồng bộ projection, nhiều mô hình |
| Event-Driven | Phối hợp bất đồng bộ qua sự kiện | Trùng lặp, thứ tự, độ trễ và khả năng quan sát |

Các mẫu này có thể kết hợp. Ví dụ, một Modular Monolith có thể dùng Hexagonal Architecture bên trong mỗi module, CQRS cho một use case đọc phức tạp và event nội bộ để thông báo thay đổi. Không cần triển khai Microservices chỉ vì đã dùng CQRS hoặc Event-Driven.

## 4. Nhìn kiến trúc theo các chiều riêng biệt

Một nguyên nhân khiến đội áp dụng quá nhiều mẫu là coi chúng như các lựa chọn cùng cấp. Thực tế, mỗi mẫu tác động đến một chiều khác nhau.

| Chiều kiến trúc | Câu hỏi | Lựa chọn có thể xem xét |
|---|---|---|
| Tổ chức trách nhiệm | Mã nguồn được chia thành phần nào? | Layered, module theo Bounded Context |
| Hướng phụ thuộc | Miền phụ thuộc vào framework và hạ tầng thế nào? | Hexagonal, Clean Architecture, Dependency Inversion |
| Ranh giới triển khai | Thành phần được phát hành cùng nhau hay độc lập? | Modular Monolith, Microservices |
| Mô hình tương tác | Thành phần trao đổi đồng bộ hay bất đồng bộ? | API, message, Event-Driven |
| Mô hình đọc/ghi | Đọc và cập nhật có cần cấu trúc riêng không? | CRUD, CQRS |
| Quản lý lịch sử thay đổi | Trạng thái hiện tại hay chuỗi sự kiện là nguồn chính? | State-based persistence, Event Sourcing |

Một hệ thống có thể chọn một phương án ở mỗi chiều mà không cần chọn mọi phương án trong cùng một hàng. Ví dụ: Modular Monolith + Hexagonal + CRUD + gọi đồng bộ là một kiến trúc hợp lệ nếu đáp ứng yêu cầu.

### 4.1. Event-Driven không đồng nghĩa Event Sourcing

Hai khái niệm này thường bị nhầm lẫn:

- **Event-Driven Architecture:** các thành phần giao tiếp hoặc phản ứng dựa trên sự kiện.
- **Event Sourcing:** trạng thái hiện tại của một đối tượng được tái dựng từ chuỗi sự kiện đã lưu làm nguồn dữ liệu chính.

Một hệ thống có thể phát domain event sau khi cập nhật trạng thái thông thường mà không dùng Event Sourcing. Event Sourcing có lợi trong một số bài toán cần lịch sử quyết định đầy đủ, nhưng làm tăng yêu cầu về versioning, replay, projection và quản lý dữ liệu lịch sử. Chỉ chọn khi nhu cầu nghiệp vụ thực sự cần.

### 4.2. CQRS không đồng nghĩa Microservices

CQRS có thể nằm trong một module hoặc một tiến trình. Một hệ thống microservices cũng có thể dùng mô hình đọc/ghi đơn giản trong từng service. Hai lựa chọn giải quyết vấn đề khác nhau:

- CQRS phân tách trách nhiệm đọc và ghi.
- Microservices phân tách đơn vị triển khai và vận hành.

Chỉ kết hợp chúng khi có lý do cho cả hai.

### 4.3. Hexagonal có thể kết hợp với Layered

Layered giúp phân chia trách nhiệm; Hexagonal nhấn mạnh ranh giới giao tiếp và hướng phụ thuộc. Một module có thể tổ chức application/domain/infrastructure theo lớp, đồng thời dùng port và adapter để đảo hướng phụ thuộc. Không cần tạo hai bộ cấu trúc trùng lặp chỉ để gắn hai tên kiến trúc.

## 5. Quy trình lựa chọn kiến trúc vừa đủ

### Bước 1: Nêu vấn đề cần giải quyết

Viết vấn đề bằng một câu có thể kiểm chứng. Ví dụ: “Thay đổi chính sách hoàn tiền thường buộc đội sửa cả phần báo cáo và tích hợp cổng thanh toán”. Xác định ảnh hưởng, tần suất và hậu quả.

Tránh bắt đầu bằng tên công nghệ. Nếu chưa thể nói rõ vấn đề, chưa có căn cứ để chọn mẫu kiến trúc.

### Bước 2: Xác định ranh giới nghiệp vụ

Xem xét domain, subdomain và Bounded Context liên quan. Ghi rõ context sở hữu quy tắc nào, dữ liệu nào và ai chịu trách nhiệm. Xác định phụ thuộc giữa chúng qua Context Map.

Nếu ranh giới nghiệp vụ chưa rõ, việc chia service hoặc database có thể chỉ chuyển sự mơ hồ vào kiến trúc kỹ thuật.

### Bước 3: Xếp hạng thuộc tính chất lượng

Chọn khoảng ba đến năm thuộc tính quan trọng nhất cho tình huống hiện tại. Mô tả kịch bản, tiêu chí đo và mức chấp nhận được. Ghi nhận cả những thuộc tính không được phép suy giảm, chẳng hạn tính chính xác tài chính hoặc khả năng kiểm toán.

### Bước 4: Kiểm tra ràng buộc và năng lực đội

Đánh giá kỹ năng, hạ tầng, công cụ triển khai, khả năng giám sát và năng lực xử lý sự cố. Ước tính chi phí sở hữu, không chỉ chi phí viết mã ban đầu.

### Bước 5: Chọn phương án đơn giản nhất đáp ứng yêu cầu

Bắt đầu bằng cấu trúc module và phụ thuộc rõ ràng. Có thể dùng Layered hoặc Hexagonal để bảo vệ miền, triển khai dưới dạng Modular Monolith và dùng giao tiếp đồng bộ khi chưa có nhu cầu bất đồng bộ.

Đưa ra một hoặc hai phương án thay thế, nêu lý do chọn và lý do chưa chọn. Không cần lập danh sách dài mọi mẫu kiến trúc có thể dùng.

### Bước 6: Kiểm tra bằng kịch bản và nguyên mẫu nhỏ

Thử một use case quan trọng, chẳng hạn xác nhận đơn hoặc hoàn tiền. Kiểm tra:

- Quy tắc miền có nằm ở nơi dễ hiểu và dễ kiểm thử không?
- Có thể thay đổi adapter hoặc database mà không sửa mô hình miền không?
- Các module có giữ được quyền sở hữu dữ liệu không?
- Hiệu năng và độ tin cậy có đạt kịch bản chất lượng không?
- Đội có thể triển khai, quan sát và khôi phục khi có lỗi không?

### Bước 7: Ghi lại quyết định kiến trúc

Lưu quyết định ngắn gọn theo cấu trúc:

- Bối cảnh và vấn đề.
- Các thuộc tính chất lượng và ràng buộc.
- Phương án được chọn.
- Các phương án đã cân nhắc.
- Lý do và đánh đổi.
- Hệ quả cần chấp nhận.
- Điều kiện khiến quyết định cần được xem xét lại.

### Bước 8: Đánh giá lại khi có bằng chứng mới

Kiến trúc không phải quyết định bất biến. Khi tải, cơ cấu đội, quy tắc nghiệp vụ hoặc nhu cầu triển khai thay đổi, hãy đánh giá lại. Không nên tách service chỉ vì dự báo mơ hồ; hãy dùng số liệu về nút thắt, phạm vi thay đổi và nhu cầu triển khai độc lập.

~~~mermaid
flowchart TD
    A["Mô tả vấn đề thực tế"] --> B["Xác định Bounded Context và phụ thuộc"]
    B --> C["Chọn thuộc tính chất lượng quan trọng"]
    C --> D["Kiểm tra ràng buộc và năng lực đội"]
    D --> E["Đề xuất kiến trúc đơn giản đáp ứng yêu cầu"]
    E --> F["Thử với use case và kịch bản chất lượng"]
    F --> G{"Đạt yêu cầu?"}
    G -->|Chưa| H["Điều chỉnh cấu trúc hoặc chọn mẫu bổ sung"]
    H --> F
    G -->|Đạt| I["Ghi quyết định và đánh đổi"]
    I --> J["Theo dõi và xem xét lại khi bối cảnh đổi"]
~~~

## 6. Ví dụ: chọn kiến trúc cho một hệ thống bán hàng trực tuyến

Giả sử một đội nhỏ đang xây dựng hệ thống bán hàng trực tuyến. Hệ thống có các năng lực:

- Catalog quản lý thông tin sản phẩm.
- Pricing tính giá và khuyến mãi.
- Ordering tiếp nhận và xác nhận đơn.
- Inventory quản lý tồn kho.
- Payment tích hợp cổng thanh toán.
- Notification gửi email và tin nhắn.

Ở giai đoạn đầu, lưu lượng vừa phải, đội có sáu kỹ sư và một nhóm vận hành nhỏ. Yêu cầu quan trọng nhất là thay đổi quy tắc dễ kiểm soát, bảo toàn giao dịch và có thể phát hành thường xuyên.

### 6.1. Phương án khởi đầu

Một lựa chọn phù hợp có thể là:

- **Modular Monolith:** tổ chức các module theo trách nhiệm nghiệp vụ.
- **Hexagonal hoặc Layered có kiểm soát:** giữ domain độc lập với framework và database.
- **Giao tiếp đồng bộ trong các use case cần kết quả ngay:** ví dụ yêu cầu báo giá hoặc giữ chỗ hàng.
- **Sự kiện nội bộ cho tác vụ không cần phản hồi tức thời:** ví dụ gửi email sau khi đơn được xác nhận.
- **CRUD hoặc mô hình đọc đơn giản:** cho đến khi có bằng chứng về nhu cầu CQRS.

~~~mermaid
flowchart TB
    UI["Web / Mobile API"] --> APP["Application Layer"]
    APP --> ORDER["Ordering Module"]
    APP --> PRICE["Pricing Module"]
    APP --> INV["Inventory Module"]
    APP --> PAY["Payment Module"]
    ORDER --> DB1[("Ordering Data")]
    PRICE --> DB2[("Pricing Data")]
    INV --> DB3[("Inventory Data")]
    PAY --> DB4[("Payment Data")]
    ORDER --> EVT["Internal Domain Events"]
    EVT --> NOTI["Notification Handler"]
    NOTI --> EMAIL["Email Provider"]
~~~

Các module có thể cùng dùng một tiến trình và hạ tầng triển khai, nhưng mỗi module sở hữu mô hình và dữ liệu nghiệp vụ của mình. Nếu dùng chung một database vật lý, cần giữ quyền truy cập bảng theo module và tránh truy vấn chéo vào schema nội bộ.

### 6.2. Vì sao chưa cần Microservices?

Hiện tại chưa có nhu cầu triển khai độc lập hoặc mở rộng khác biệt đủ lớn. Đội nhỏ có thể phối hợp phát hành toàn ứng dụng. Tách thành nhiều service ngay sẽ tạo thêm pipeline, cấu hình, giám sát, xác thực giữa service, quản lý lỗi mạng và quy trình xử lý dữ liệu phân tán.

Giữ Modular Monolith giúp đội học xem ranh giới Ordering, Pricing và Inventory có phù hợp không. Khi có bằng chứng về tải, quyền sở hữu hoặc nhu cầu phát hành độc lập, có thể tách một module với hợp đồng đã rõ.

### 6.3. Vì sao vẫn dùng sự kiện cho một số công việc?

Sau khi đơn được xác nhận, gửi email thông báo không cần nằm trong thời gian phản hồi của request xác nhận đơn. Một handler có thể nhận OrderConfirmed và gửi thông báo ở chế độ nền.

Tác vụ gửi email có thể thử lại khi nhà cung cấp tạm thời lỗi. Điều này không buộc toàn bộ hệ thống phải chuyển sang kiến trúc event-driven phân tán. Một cơ chế hàng đợi hoặc event nội bộ vừa đủ có thể đáp ứng nhu cầu.

### 6.4. Khi nào nên bổ sung CQRS?

Sau một thời gian, báo cáo lịch sử đơn hàng có thể cần kết hợp nhiều nguồn, truy vấn phức tạp và làm chậm các thao tác cập nhật. Nếu số liệu cho thấy đây là nút thắt thực sự, đội có thể tạo read model riêng cho báo cáo hoặc màn hình tổng hợp.

Chỉ use case có nhu cầu rõ mới cần mô hình đọc riêng. Các thao tác cập nhật đơn vẫn dùng mô hình ghi bảo vệ invariant. Những màn hình đơn giản có thể tiếp tục dùng truy vấn thông thường.

### 6.5. Khi nào cân nhắc tách một service?

Ví dụ, Notification tăng tải đột biến theo chiến dịch, cần triển khai độc lập và có thể hoạt động với dữ liệu sự kiện đã công bố. Khi đó, tách Notification thành service có thể đem lại lợi ích thực tế.

Trước khi tách, cần có:

- Hợp đồng sự kiện ổn định và có phiên bản.
- Cơ chế xử lý sự kiện trùng và thử lại.
- Theo dõi lỗi, độ trễ và hàng đợi tồn đọng.
- Quy trình triển khai và khôi phục độc lập.
- Chủ sở hữu chịu trách nhiệm vận hành service.

Nếu chưa có những điều kiện đó, tách service có thể chỉ chuyển sự phức tạp vào vận hành.

## 7. Dấu hiệu cho thấy nên bổ sung mẫu kiến trúc

| Dấu hiệu quan sát được | Hướng xem xét | Bằng chứng cần thu thập |
|---|---|---|
| Domain phụ thuộc trực tiếp vào ORM hoặc framework | Hexagonal / Dependency Inversion | Khó kiểm thử, khó thay adapter, thay đổi công nghệ lan vào miền |
| Module thường xuyên sửa dữ liệu nội bộ của nhau | Làm rõ module boundary, API nội bộ | Lịch sử thay đổi, lỗi do truy cập chéo, ownership không rõ |
| Một phần cần triển khai hoặc mở rộng độc lập | Tách service có chọn lọc | Tải, lịch phát hành, yêu cầu cô lập và năng lực đội |
| Truy vấn đọc làm chậm cập nhật | Read model riêng hoặc CQRS | Query plan, latency, CPU, contention và hình dạng truy vấn |
| Công việc nền giữ request quá lâu | Queue hoặc Event-Driven | Thời gian xử lý, mức chấp nhận độ trễ, nhu cầu retry |
| Nhiều consumer cần phản ứng với một thay đổi | Published Domain Event | Số consumer, hợp đồng, yêu cầu thứ tự và idempotency |
| Nhà cung cấp có mô hình không phù hợp với miền nội bộ | Anti-Corruption Layer | Khác biệt ngữ nghĩa, tần suất thay đổi và phạm vi ảnh hưởng |
| Lịch sử mọi thay đổi trạng thái là yêu cầu nghiệp vụ | Xem xét Event Sourcing | Yêu cầu kiểm toán, replay, truy vết và chi phí lưu trữ |

Các dấu hiệu là lý do để điều tra, không phải lệnh tự động áp dụng một mẫu. Ví dụ, truy vấn chậm có thể do index, câu SQL hoặc cache chưa hợp lý; không nhất thiết phải triển khai CQRS.

## 8. Quản lý dữ liệu và transaction giữa các ranh giới

Kiến trúc ứng dụng theo DDD cần làm rõ context nào sở hữu dữ liệu và quy tắc thay đổi dữ liệu đó.

### 8.1. Mỗi context sở hữu mô hình và quy tắc của mình

Ordering sở hữu trạng thái đơn hàng và quy tắc xác nhận. Inventory sở hữu số lượng và giữ chỗ. Payment sở hữu giao dịch thanh toán. Context khác có thể nhận dữ liệu qua hợp đồng nhưng không nên tự sửa bảng nội bộ của context sở hữu.

Nếu nhiều context cùng cập nhật một bảng hoặc cùng quyết định ý nghĩa của một trường, ranh giới trách nhiệm đang không rõ.

### 8.2. Transaction cục bộ và quy trình nhiều bước

Trong một module hoặc service, transaction database thường phù hợp để bảo vệ invariant cục bộ. Khi một use case đi qua nhiều context, không nên giả định có thể dùng một transaction ACID xuyên mọi hệ thống.

Ví dụ xác nhận đơn có thể gồm:

1. Ordering tiếp nhận yêu cầu.
2. Inventory giữ chỗ hàng.
3. Payment xác nhận điều kiện thanh toán.
4. Ordering xác nhận đơn sau khi có đủ kết quả.

Nếu bước thanh toán thất bại sau khi giữ chỗ, hệ thống cần giải phóng giữ chỗ hoặc xử lý theo chính sách. Đây là quy trình nhiều bước có thể cần Saga hoặc cơ chế điều phối tương ứng khi được triển khai phân tán. **Saga** phối hợp một chuỗi transaction cục bộ ở các context; khi một bước không thành công, quy trình có thể chạy hành động bù trừ đã định nghĩa để đưa nghiệp vụ về trạng thái chấp nhận được. Saga không tạo ra một transaction ACID toàn cục và cần xử lý retry, timeout, sự kiện đến trễ cùng các trường hợp bù trừ thất bại.

Không cần đưa Saga vào mọi use case. Chỉ xem xét khi có nhiều transaction cục bộ cần phối hợp và phải định nghĩa rõ hành động bù trừ, thời hạn, retry và trạng thái trung gian.

### 8.3. Nhất quán cuối cùng cần được thể hiện trong nghiệp vụ

Khi dùng sự kiện bất đồng bộ, một context có thể chưa thấy ngay thay đổi từ context khác. Điều này cần được phản ánh trong trải nghiệm và quy tắc:

- Giao diện hiển thị trạng thái “Đang xử lý” thay vì khẳng định hoàn tất quá sớm.
- Người dùng có thể tra cứu trạng thái mới nhất từ context sở hữu.
- Consumer xử lý sự kiện lặp một cách an toàn.
- Có cơ chế phát hiện và xử lý sự kiện thất lạc hoặc bị kẹt.
- Nghiệp vụ xác định khoảng thời gian chấp nhận được cho trạng thái chưa đồng bộ.

Không nên dùng nhất quán cuối cùng ở nơi nghiệp vụ đòi hỏi quyết định tức thời, chẳng hạn xác nhận một số lượng tồn kho cuối cùng mà không có cơ chế giữ chỗ đáng tin cậy.

## 9. Các nguyên tắc giúp giữ kiến trúc vừa đủ

**Bảo vệ điều quan trọng nhất trước.** Mô hình miền và quy tắc cốt lõi cần rõ ràng, dễ kiểm thử. Không cần tạo nhiều tầng nếu chúng không bảo vệ được một ranh giới hoặc trách nhiệm cụ thể.

**Tách theo lý do thay đổi.** Hai phần có thể nằm cùng module nếu chúng thường thay đổi cùng nhau và có cùng trách nhiệm. Hai phần nên tách khi quy tắc, quyền sở hữu hoặc nhịp thay đổi khác nhau rõ rệt.

**Giữ ranh giới nghiệp vụ trước ranh giới triển khai.** Hãy hiểu Bounded Context và hợp đồng trước khi quyết định service, database hoặc message broker.

**Chỉ phân tán khi có lợi ích đo được.** Mạng, triển khai độc lập và mở rộng riêng có giá trị, nhưng đi cùng chi phí quan sát, bảo mật, xử lý lỗi và dữ liệu phân tán.

**Dùng giao tiếp đồng bộ khi cần câu trả lời ngay.** API request/response thường dễ hiểu cho các quyết định cần kết quả tức thời. Dùng sự kiện khi các bên có thể phản ứng độc lập và chấp nhận độ trễ.

**Không tạo abstraction trước nhu cầu.** Interface, adapter, factory, event bus hoặc service riêng cần có trách nhiệm cụ thể. Abstraction rỗng làm người đọc phải đi qua nhiều tệp mà không hiểu thêm nghiệp vụ.

**Ghi lại đánh đổi.** Mỗi lựa chọn đều có chi phí. Ghi lý do chọn và điều kiện xem xét lại để người khác hiểu quyết định trong bối cảnh ban đầu.

**Đo trước khi tối ưu.** Dùng metric, trace, log, profile và phản hồi người dùng để xác định nút thắt. Không dùng Microservices, CQRS hoặc cache như giải pháp mặc định cho mọi vấn đề hiệu năng.

## 10. Mẫu ghi nhận quyết định kiến trúc

Có thể dùng mẫu Architecture Decision Record (ADR) ngắn sau:

~~~text
# ADR: [Tên quyết định]

## Trạng thái
Đề xuất / Đã chấp nhận / Đã thay thế

## Bối cảnh
- Vấn đề nghiệp vụ hoặc kỹ thuật:
- Bounded Context liên quan:
- Thuộc tính chất lượng quan trọng:
- Ràng buộc:

## Quyết định
- Phương án được chọn:
- Phạm vi áp dụng:
- Các lựa chọn không áp dụng:

## Lý do
- Bằng chứng:
- Lợi ích kỳ vọng:
- Vì sao phương án khác chưa phù hợp:

## Đánh đổi và hệ quả
- Chi phí phát triển:
- Chi phí vận hành:
- Rủi ro:
- Tác động đến các context khác:

## Điều kiện xem xét lại
- Chỉ số hoặc sự kiện kích hoạt:
- Người chịu trách nhiệm:
- Ngày xem xét:
~~~

Ví dụ:

| Mục | Nội dung |
|---|---|
| Vấn đề | Đội nhỏ cần ranh giới nghiệp vụ rõ nhưng chưa cần triển khai độc lập |
| Quyết định | Dùng Modular Monolith, module theo Bounded Context |
| Lý do | Giữ vận hành đơn giản, dễ phát hành và kiểm thử; ranh giới module tạo cơ sở thay đổi sau này |
| Đánh đổi | Các module cùng phát hành và cùng chia sẻ tài nguyên tiến trình |
| Điều kiện xem xét lại | Một module có nhu cầu mở rộng hoặc phát hành độc lập được chứng minh bằng số liệu |

## 11. Những sai lầm thường gặp

**Áp dụng mọi mẫu cùng lúc.** Kết hợp Microservices, CQRS, Event Sourcing, Event-Driven và Hexagonal từ đầu có thể tạo nhiều cơ chế mà chưa có nhu cầu. Chọn theo vấn đề và bổ sung từng phần khi có bằng chứng.

**Đồng nhất DDD với Microservices.** DDD tập trung vào mô hình và ranh giới miền. Có thể áp dụng DDD trong một Modular Monolith hoặc ứng dụng đơn giản.

**Tách service theo danh từ hoặc bảng dữ liệu.** Một service cho Customer, một service cho Product và một service cho Address chưa chắc tạo ra ranh giới nghiệp vụ có ý nghĩa. Hãy phân chia theo năng lực và trách nhiệm.

**Dùng CQRS cho mọi màn hình.** Hai mô hình đọc/ghi làm tăng công sức đồng bộ và duy trì. Chỉ dùng khi nhu cầu đọc và ghi thực sự khác biệt.

**Biến mọi thao tác thành sự kiện.** Sự kiện không thay thế mọi API. Luồng cần kết quả ngay thường rõ ràng hơn với giao tiếp đồng bộ.

**Nhầm Event-Driven với Event Sourcing.** Phát sự kiện sau khi lưu trạng thái không có nghĩa chuỗi sự kiện là nguồn dữ liệu chính.

**Tạo interface và adapter không có mục đích.** Mỗi abstraction cần bảo vệ một ranh giới, hỗ trợ thay thế hoặc làm rõ hợp đồng. Nếu không, nó chỉ làm luồng điều khiển khó theo dõi.

**Bỏ qua năng lực vận hành.** Tách service mà không có log, metric, trace, cảnh báo và quy trình khôi phục sẽ làm thời gian xử lý sự cố tăng lên.

**Để database dùng chung phá vỡ module boundary.** Các module có thể cùng dùng một database vật lý, nhưng cần quyền sở hữu schema và quy tắc truy cập rõ ràng.

**Không xem xét lại quyết định.** Kiến trúc phù hợp ở giai đoạn đầu có thể không còn phù hợp khi tải, đội ngũ hoặc chiến lược thay đổi. Hãy gắn quyết định với chỉ số và điều kiện xem xét lại.

## 12. Tiêu chí tự kiểm tra

Trước khi chốt kiến trúc ứng dụng, hãy kiểm tra:

- Vấn đề cần giải quyết đã được mô tả cụ thể chưa?
- Các Bounded Context và trách nhiệm nghiệp vụ liên quan đã rõ chưa?
- Những thuộc tính chất lượng quan trọng có kịch bản và tiêu chí đo chưa?
- Các ràng buộc về đội ngũ, hạ tầng, bảo mật và vận hành đã được tính đến chưa?
- Mỗi mẫu kiến trúc được chọn có giải quyết một vấn đề xác định không?
- Có phân biệt tổ chức mã nguồn, hướng phụ thuộc, đơn vị triển khai và mô hình giao tiếp không?
- Đã cân nhắc phương án đơn giản hơn chưa?
- Quyền sở hữu dữ liệu và hợp đồng giữa các context có rõ không?
- Transaction, retry, idempotency và độ trễ đã được xem xét ở nơi cần thiết chưa?
- Đội có đủ năng lực triển khai, giám sát và khôi phục kiến trúc đã chọn không?
- Các đánh đổi và điều kiện xem xét lại có được ghi lại không?

Kiến trúc ứng dụng hiệu quả là kiến trúc giải quyết được vấn đề hiện tại, bảo vệ những quy tắc nghiệp vụ quan trọng và cho phép tiến hóa khi nhu cầu thay đổi. Chọn vừa đủ giúp đội tập trung vào mô hình miền và giá trị kinh doanh, đồng thời tránh gánh chi phí của những cơ chế mà hệ thống chưa cần.
