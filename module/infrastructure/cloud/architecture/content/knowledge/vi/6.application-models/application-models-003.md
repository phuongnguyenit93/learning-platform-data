# Kiến trúc hướng dịch vụ và kiến trúc vi dịch vụ

> **Chương:** Mô hình ứng dụng  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến mạng, compute, dữ liệu và mô hình triển khai. Bài học phân tích **Service-Oriented Architecture (SOA)** và **Microservices Architecture** theo các đánh đổi về độ tin cậy, bảo mật, khả năng mở rộng, chi phí, vận hành và tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt SOA, kiến trúc vi dịch vụ (microservices) và ứng dụng nguyên khối có tổ chức tốt (modular monolith).
2. Thiết kế ranh giới dịch vụ theo năng lực nghiệp vụ và **bounded context**, tránh chia dịch vụ chỉ theo tầng kỹ thuật hoặc bảng dữ liệu.
3. Lựa chọn giao tiếp đồng bộ/bất đồng bộ, định nghĩa hợp đồng API/sự kiện, xử lý lỗi và giao dịch xuyên dịch vụ.
4. Áp dụng nguyên tắc độc lập triển khai, sở hữu dữ liệu, bảo vệ giao tiếp, quan sát và khôi phục trên nền tảng cloud.
5. So sánh phương án bằng yêu cầu đo được, TCO, độ phức tạp tổ chức và khả năng tuân thủ.
6. Phác thảo quá trình chuyển đổi theo từng giai đoạn và đánh giá thiết kế với các trụ cột Well-Architected.

## 1. Bản chất của SOA và microservices

### 1.1. Kiến trúc hướng dịch vụ (SOA) là gì?

**Service-Oriented Architecture — SOA** là phong cách kiến trúc tổ chức khả năng phần mềm thành các **dịch vụ có hợp đồng rõ ràng**, để các ứng dụng hoặc quy trình nghiệp vụ khác có thể sử dụng qua giao diện đã công bố.

Một dịch vụ có thể đại diện cho năng lực như **quản lý khách hàng**, **kiểm tra tín dụng**, **tra cứu tồn kho**, hoặc **xử lý hóa đơn**. Bên sử dụng không cần biết toàn bộ cách triển khai nội bộ, nhưng phải hiểu các khả năng, quy tắc, dữ liệu và giới hạn mà hợp đồng dịch vụ cung cấp.

SOA thường xuất hiện trong các tổ chức lớn cần tích hợp nhiều ứng dụng lâu đời, công nghệ khác nhau hoặc hệ thống của nhiều đơn vị. SOA **không bị định nghĩa bởi một công nghệ duy nhất**: SOAP/WSDL, REST, message broker, API gateway và các hình thức giao tiếp khác đều có thể tham gia tùy bối cảnh.

Trong một số giải pháp SOA doanh nghiệp, **Enterprise Service Bus (ESB)** thực hiện trung gian định tuyến, chuyển đổi thông điệp, phối hợp quy trình và áp dụng chính sách tích hợp. ESB là một mẫu triển khai thường gặp, **không phải điều kiện bắt buộc** để một hệ thống được gọi là SOA.

### 1.2. Kiến trúc vi dịch vụ (microservices) là gì?

**Microservices Architecture** xây dựng ứng dụng thành tập hợp những dịch vụ có **ranh giới nghiệp vụ rõ**, thường do các nhóm chịu trách nhiệm từ phát triển đến vận hành, có thể **phát hành và mở rộng tương đối độc lập**.

Mỗi dịch vụ nên sở hữu logic và dữ liệu thuộc phạm vi của mình; các dịch vụ cộng tác bằng API hoặc sự kiện có hợp đồng. Điểm cốt lõi là **tính tự chủ và giảm phụ thuộc khi thay đổi**. “Micro” không có nghĩa phải ít dòng code, có một bảng dữ liệu hay một endpoint.

Vi dịch vụ có thể xem là một cách hiện thực hóa ý tưởng hướng dịch vụ, nhấn mạnh các thuộc tính như triển khai độc lập, dữ liệu phân quyền, tự động hóa và khả năng tổ chức theo nhóm nghiệp vụ. Tuy vậy **SOA và microservices không phải hai bộ quy tắc loại trừ nhau**; một hệ thống có thể mang đặc điểm của cả hai.

### 1.3. Nguyên khối có tổ chức tốt vẫn là một lựa chọn

**Modular monolith** chứa nhiều mô-đun nghiệp vụ với ranh giới rõ nhưng được đóng gói, chạy và thường triển khai cùng nhau. Nó có thể cho phép giao dịch dữ liệu trực tiếp, dễ kiểm thử end-to-end và chi phí vận hành ban đầu thấp hơn.

Đừng kết luận “microservices là bước tiến bắt buộc của monolith”. Nếu đội nhỏ, domain chưa rõ hoặc hệ thống chưa có nhu cầu triển khai độc lập, modular monolith thường giúp giao hàng an toàn và nhanh hơn.

### 1.4. Minh họa ba cách tổ chức

~~~mermaid
flowchart TB
    subgraph M["Modular monolith"]
      MA["Catalog module"] --> MB["Order module"]
      MB --> MC["Payment module"]
      MD[("Một đơn vị triển khai")]
    end
    subgraph S["SOA: tích hợp nhiều hệ thống"]
      SA["CRM"] --> SE["API / trung gian tích hợp"]
      SB["ERP"] --> SE
      SE --> SC["Billing service"]
      SE --> SD["Inventory service"]
    end
    subgraph U["Microservices"]
      UA["Order service"] --> UB["Inventory API"]
      UA --> UC["Payment API"]
      UA --> UE["Event broker"]
      UE --> UD["Notification service"]
    end
~~~

Sơ đồ mô tả ý tưởng, không biểu thị rằng mọi hệ thống SOA bắt buộc dùng một trung tâm tích hợp hay mọi microservice đều phải giao tiếp trực tiếp.

## 2. Điểm giống và khác: đừng chỉ đếm số dịch vụ

| Tiêu chí | SOA theo hướng tích hợp doanh nghiệp | Microservices | Modular monolith |
| --- | --- | --- | --- |
| Mục tiêu thường gặp | Tái sử dụng năng lực, tích hợp hệ thống đa nền tảng | Tự chủ thay đổi, triển khai và mở rộng theo miền nghiệp vụ | Đơn giản triển khai, giữ ranh giới module rõ |
| Phạm vi dịch vụ | Có thể khá rộng, phục vụ nhiều ứng dụng | Thường tập trung vào một năng lực/bounded context | Mô-đun trong cùng ứng dụng |
| Hợp đồng | API và thông điệp, thường có quản trị tích hợp | API/sự kiện có phiên bản, chú trọng tự chủ | Giao diện module trong process |
| Dữ liệu | Có thể sử dụng mô hình dữ liệu dùng chung hoặc phối hợp | Ưu tiên quyền sở hữu dữ liệu riêng từng service | Có thể chia sẻ một DB với quy tắc module |
| Phát hành | Có thể phụ thuộc quy trình tích hợp chung | Mục tiêu là phát hành tương đối độc lập | Phát hành cả ứng dụng |
| Tích hợp | Có thể có ESB hoặc tầng orchestration chung | Dùng API gateway, broker, service-to-service; tránh nút trung tâm chứa quá nhiều logic nghiệp vụ | Gọi nội bộ trong process |
| Kiểm soát thay đổi | Có thể quản trị hợp đồng tập trung | Chủ yếu theo contract và quyền sở hữu nhóm | Theo quy tắc đóng gói và kiểm thử |
| Chi phí vận hành | Phụ thuộc nền tảng tích hợp và hệ thống kế thừa | Nhiều đơn vị triển khai, quan sát, bảo mật, dữ liệu | Thường thấp hơn lúc đầu |
| Điểm yếu thường gặp | Trung gian tích hợp thành nút nghẽn hoặc thay đổi chậm | Distributed monolith, lỗi mạng, dữ liệu bất đồng bộ | Khó mở rộng/phát hành riêng nếu ranh giới phát triển không tốt |

**Lưu ý:** bảng nói về xu hướng thiết kế; không có luật rằng SOA phải dùng SOAP hoặc ESB, microservice phải dùng REST hoặc Kubernetes, hay một dịch vụ SOA không thể triển khai độc lập.

### Đánh giá bằng “mức độ gắn kết”

Một hệ thống 40 service nhưng phải deploy cùng lúc mỗi khi đổi một trường dữ liệu có thể là **distributed monolith**. Nó chịu chi phí của mạng và hạ tầng phân tán, trong khi không nhận được tính tự chủ.

Ngược lại, một ứng dụng có sáu module nghiệp vụ rõ ràng, ít phụ thuộc vòng, kiểm thử tốt và phát hành hàng ngày có thể đáp ứng yêu cầu tốt hơn ở giai đoạn đầu.

Hỏi ba câu trước khi đặt tên kiến trúc:

1. Một nhóm có thể **thay đổi và phát hành năng lực nghiệp vụ** mà ít buộc nhóm khác sửa code không?
2. Lỗi, tải và dữ liệu nhạy cảm được **giới hạn phạm vi tác động** thế nào?
3. Chi phí vận hành và mức phức tạp có tương xứng với **yêu cầu đo được** hay không?

## 3. Chia ranh giới dịch vụ theo miền nghiệp vụ

### 3.1. Bounded context và quyền sở hữu

Trong **Domain-Driven Design (DDD)**, *bounded context* là phạm vi mà thuật ngữ, quy tắc và mô hình nghiệp vụ có ý nghĩa nhất quán. Ranh giới context là điểm khởi đầu hữu ích để tìm ranh giới service, nhưng **không buộc một bounded context phải tương ứng đúng một service**.

Ví dụ ứng dụng đặt chỗ:

- **Catalog:** thông tin dịch vụ, lịch mở bán và điều kiện hiển thị.
- **Booking:** trạng thái đặt chỗ, quy tắc giữ chỗ và hủy.
- **Payment:** yêu cầu thanh toán, trạng thái giao dịch, xử lý hoàn tiền.
- **Customer:** hồ sơ khách hàng và các chính sách truy cập.
- **Notification:** gửi thông điệp và theo dõi kết quả gửi.

Các context có thể hiểu từ “trạng thái” khác nhau. Booking có **CONFIRMED/CANCELLED**; Payment có **AUTHORIZED/CAPTURED/REFUNDED**. Nếu ép chúng dùng cùng một enum toàn hệ thống, các domain sẽ phụ thuộc nhau không cần thiết.

~~~mermaid
flowchart LR
    CU["Người dùng"] --> API["API Gateway / BFF"]
    API --> BK["Booking"]
    API --> CA["Catalog"]
    BK --> PA["Payment"]
    BK --> IN["Inventory"]
    BK --> EV["Event broker"]
    EV --> NO["Notification"]
    BK --> DB1[("Booking data")]
    PA --> DB2[("Payment data")]
    IN --> DB3[("Inventory data")]
~~~

Mũi tên là phụ thuộc nghiệp vụ minh họa. Chúng không buộc tất cả các bước phải gọi đồng bộ hay tạo giao dịch phân tán.

### 3.2. Tiêu chí chọn ranh giới tốt

Một service thường hợp lý khi:

- Có **năng lực nghiệp vụ và ngôn ngữ riêng**; có người/nhóm chịu trách nhiệm quy tắc.
- Các thay đổi của nó có thể kiểm thử và triển khai tương đối độc lập.
- Nó sở hữu dữ liệu cần để bảo vệ **bất biến nghiệp vụ** cốt lõi.
- Nó có đặc điểm tải, độ sẵn sàng, dữ liệu hoặc tuân thủ khác đáng kể với phần còn lại.
- API/sự kiện có mục đích rõ, không phải tập hợp thao tác CRUD mở trực tiếp các bảng nội bộ.
- Lợi ích phân tách đủ lớn để bù chi phí mạng, dữ liệu, deployment, logging và trực sự cố.

**Tránh chia theo lớp kỹ thuật** thành CustomerControllerService, CustomerRepositoryService, CustomerDatabaseService nếu một yêu cầu nghiệp vụ phải đi qua các “service” đó để thực hiện công việc cơ bản. Cách này tăng giao tiếp mạng mà không tạo ranh giới tự chủ.

### 3.3. Các dấu hiệu ranh giới bị chia sai

- Mọi tính năng đều yêu cầu sửa nhiều service cùng lúc.
- Service A phải truy vấn trực tiếp bảng của service B để thực hiện logic của mình.
- Một request người dùng phải gọi hàng chục bước đồng bộ; độ trễ và tỷ lệ lỗi tăng nhanh.
- Service “dùng chung” chứa rất nhiều quy tắc nghiệp vụ của các domain khác nhau.
- Các team chờ một nhóm quản trị trung gian sửa orchestration chung cho mỗi thay đổi nhỏ.

Khi thấy các dấu hiệu này, cân nhắc **gộp service**, đổi ranh giới bounded context, đưa điều phối về nơi sở hữu quy trình hoặc dùng sự kiện để giảm phụ thuộc thời gian.

## 4. Hợp đồng giao tiếp: đồng bộ, bất đồng bộ và tích hợp

### 4.1. Giao tiếp đồng bộ (request/response)

Service gọi API của service khác và thường chờ phản hồi. Phù hợp khi người gọi thực sự cần **kết quả ngay**, chẳng hạn Booking cần xác nhận điều kiện thanh toán trước khi trả trạng thái.

Các lựa chọn kỹ thuật thường gặp:

- **HTTP/REST:** dễ tương tác với client, hệ sinh thái lớn, biểu diễn tài nguyên/nghiệp vụ rõ.
- **gRPC:** hợp đồng kiểu dữ liệu chặt, hỗ trợ streaming và giao tiếp hiệu quả trong một số môi trường.
- **SOAP:** còn phổ biến ở hệ thống tích hợp doanh nghiệp có hợp đồng và yêu cầu tiêu chuẩn riêng.
- **Message request/reply:** có thể thực hiện qua broker, nhưng vẫn tạo phụ thuộc chờ kết quả nếu logic người gọi đồng bộ.

Chọn công nghệ dựa vào hợp đồng, môi trường, độ trễ và khả năng vận hành. **Không có giao thức nào tự động biến một dịch vụ thành microservice hoặc SOA.**

**Rủi ro:** lỗi mạng, timeout, kết nối bị reset, phiên bản contract không tương thích và fan-out nhiều bước khiến độ trễ/tỷ lệ lỗi tăng. Không nên giả định gọi service nội bộ có độ tin cậy như gọi hàm cùng process.

### 4.2. Giao tiếp bất đồng bộ qua sự kiện/thông điệp

Service xuất bản sự kiện mô tả một thay đổi đã xảy ra; các service quan tâm tiêu thụ để cập nhật dữ liệu cục bộ hoặc tạo tác vụ.

Ví dụ sau khi Booking xác nhận đơn:

~~~json
{
  "event_id": "evt-731a",
  "event_type": "BookingConfirmed",
  "event_version": 1,
  "occurred_at": "2026-11-18T04:30:00Z",
  "booking_id": "bkg-204",
  "customer_id": "cust-19",
  "tenant_id": "tenant-08"
}
~~~

Dữ liệu minh họa. Event cần hợp đồng, định danh sự kiện, phiên bản, thời gian, quy tắc phân quyền và khả năng theo dõi. Đừng gửi thông tin nhạy cảm chỉ vì broker “nội bộ”.

**Lợi ích:** producer và consumer không cần sẵn sàng đồng thời; dễ mở rộng consumer, tạo luồng phản ứng sau khi nghiệp vụ hoàn tất. **Đánh đổi:** giao hàng có thể bị lặp, sai thứ tự, chậm hoặc thất bại; hệ thống cần idempotency, retry có kiểm soát, dead-letter handling và quy trình replay.

### 4.3. Orchestration và choreography

- **Orchestration:** một thành phần điều phối biết các bước quy trình, quyết định gọi ai tiếp theo, xử lý timeout và bù trừ. Dễ thấy toàn bộ workflow nhưng coordinator có thể trở thành điểm phụ thuộc lớn.
- **Choreography:** các service phản ứng với sự kiện từ service khác. Giảm điều phối tập trung nhưng khó lần theo chuỗi hành động nếu quá nhiều sự kiện và các bên phụ thuộc ngầm.

Cả hai đều có thể dùng trong SOA và microservices. Nên chọn dựa trên tính phức tạp nghiệp vụ, yêu cầu quan sát, khả năng phục hồi và đội sở hữu workflow; không mặc định choreography luôn tốt hơn.

### 4.4. API Gateway, ESB và service mesh không thay thế nhau

| Thành phần | Trách nhiệm thường gặp | Không nên gánh thay |
| --- | --- | --- |
| **API Gateway / BFF** | Điểm vào từ client; xác thực sơ bộ, routing, rate limit, chuyển đổi giao diện cho client | Quy tắc nghiệp vụ lõi của mọi domain |
| **ESB / integration platform** | Kết nối hệ thống khác giao thức, chuyển đổi dữ liệu, điều phối tích hợp có quản trị | Trở thành nơi tập trung mọi logic sản phẩm nếu làm chậm thay đổi |
| **Message broker** | Định tuyến và lưu đệm thông điệp/sự kiện theo khả năng của nền tảng | Bảo đảm bất biến nghiệp vụ hoặc exactly-once end-to-end |
| **Service mesh** | Chính sách kết nối service-to-service, mTLS, telemetry, traffic management tùy nền tảng | Thiết kế quyền nghiệp vụ, ranh giới dữ liệu, transaction |

**Không nhất thiết cần tất cả**. Một hệ thống nhỏ có thể chỉ cần API gateway và hàng đợi được quản lý. Thêm nhiều tầng trung gian tăng cấu hình, năng lực vận hành và chi phí.

## 5. Dữ liệu và giao dịch xuyên dịch vụ

### 5.1. Mỗi service sở hữu dữ liệu, không nhất thiết mỗi service có server DB riêng

Nguyên tắc **database ownership** nghĩa là chỉ service có quyền sở hữu mới được ghi hoặc quy định cấu trúc dữ liệu nghiệp vụ của mình. Có thể có database/schema riêng, hoặc phân tách bằng quyền và quy tắc truy cập trong hạ tầng quản lý chung; yêu cầu cốt lõi là **không phụ thuộc trực tiếp vào bảng nội bộ của service khác**.

Nếu Booking cần trạng thái Payment, hãy dùng API được công bố hoặc giữ một **read model/projection** cập nhật từ sự kiện có hợp đồng. Không khuyến khích Booking join trực tiếp vào bảng Payment trong cơ sở dữ liệu dùng chung, vì mọi đổi schema Payment có thể phá vỡ Booking.

### 5.2. Vì sao transaction phân tán khó?

Trong một database, giao dịch ACID có thể cập nhật nhiều bảng liên quan nguyên tử. Khi Booking, Inventory và Payment sở hữu dữ liệu riêng, không thể mặc định có một transaction database chung bảo vệ toàn bộ quy trình.

Các cách tiếp cận:

- **Giữ bất biến trong một service** khi có thể; các tác vụ cần tính nhất quán mạnh nên nằm trong cùng ranh giới nghiệp vụ/giao dịch.
- **Saga** cho workflow nhiều service với các bước cục bộ và hành động bù trừ khi bước sau thất bại.
- **Transactional outbox** để ghi dữ liệu nghiệp vụ và bản ghi sự kiện trong **cùng giao dịch local**, sau đó relay sự kiện tới broker.
- **Idempotent consumer** để nhận lại cùng một thông điệp mà không tạo trùng tác dụng.
- **CQRS/read projection** khi cần một góc nhìn tổng hợp nhanh, chấp nhận trễ cập nhật trong phạm vi đã thiết kế.

Không phải mọi saga đều “rollback” chính xác về trạng thái trước đó: hoàn tiền sau khi đã charge có thể phát sinh nghiệp vụ, phí hoặc thời gian chờ; cần quy định rõ các trạng thái trung gian và xử lý thủ công khi bù trừ thất bại.

### 5.3. Ví dụ Saga đặt chỗ

Giả sử workflow: **giữ tài nguyên → thu tiền → xác nhận đặt chỗ**. Khi không thu được tiền, hệ thống phải giải phóng chỗ đã giữ.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant B as Booking / Orchestrator
    participant I as Inventory
    participant P as Payment
    participant E as Event broker
    C->>B: POST /bookings (idempotency key)
    B->>B: Tạo trạng thái PENDING
    B->>I: Reserve(item, bookingId)
    I-->>B: Reservation token
    B->>P: Charge(amount, bookingId)
    alt Thanh toán thành công
      P-->>B: Charged
      B->>B: CONFIRMED + ghi outbox
      B-->>C: Trạng thái CONFIRMED
      B-->>E: BookingConfirmed qua outbox relay
    else Bị từ chối hoặc xác nhận thất bại
      P-->>B: Failed hoặc không xác định
      B->>B: Kiểm tra kết quả/idempotency
      B->>I: Release(reservation token) khi phù hợp
      B-->>C: FAILED / PENDING_REVIEW
    end
~~~

Đây là sơ đồ khái niệm. Trong thực tế, **timeout Payment không chứng minh Payment thất bại**: phải tra cứu trạng thái giao dịch hoặc xử lý callback/webhook với khóa idempotency trước khi bù trừ. Đặc biệt tránh thu tiền hai lần do retry.

### 5.4. Outbox và idempotency

Một thiết kế outbox minh họa:

~~~sql
BEGIN;
UPDATE booking
SET status = 'CONFIRMED'
WHERE id = :booking_id;

INSERT INTO outbox_event
    (event_id, aggregate_id, event_type, payload, created_at)
VALUES
    (:event_id, :booking_id, 'BookingConfirmed', :payload, CURRENT_TIMESTAMP);
COMMIT;
~~~

Một relay riêng đọc các bản ghi outbox chưa phát, gửi tới broker và đánh dấu đã xử lý. Vì relay có thể gửi trùng khi crash ở ranh giới gửi/đánh dấu, consumer cần xử lý **at-least-once delivery** theo giả định bảo thủ. Ví dụ consumer lưu **event_id** đã xử lý trong cùng transaction với cập nhật trạng thái liên quan, hoặc dùng unique constraint phù hợp.

**Idempotency key** ở API được tạo/kiểm soát theo phạm vi người dùng hoặc tenant, gắn với một thao tác logic và có thời hạn lưu rõ ràng. Đừng gộp request có cùng key nhưng payload khác nhau mà không kiểm tra.

## 6. Độ tin cậy: mạng trở thành một phần của mô hình lỗi

Một lời gọi hàm trong process có độ trễ và cách thất bại khác lời gọi qua mạng. Trong kiến trúc phân tán, mỗi dependency tạo thêm điểm hỏng và đường chậm.

Ví dụ **ước lượng đơn giản**: một đường đi nối tiếp phải gọi bốn service, mỗi service có xác suất thành công độc lập 99,9% cho cùng khoảng đo và điều kiện. Khi đó xác suất tất cả cùng thành công xấp xỉ:

\[
0{,}999^4 \approx 99{,}60\%
\]

Con số này **chỉ minh họa** khi có giả định độc lập; sự cố chia sẻ hạ tầng, retries và cache làm kết quả thực khác. Ý nghĩa thực hành là tránh chuỗi đồng bộ dài và thiết kế suy giảm có kiểm soát.

### Những cơ chế cần có

| Cơ chế | Mục đích | Điều cần tránh |
| --- | --- | --- |
| **Timeout và deadline** | Giới hạn thời gian chờ; truyền ngân sách thời gian từ request gốc | Timeout quá dài làm nghẽn thread/connection pool |
| **Retry có backoff và jitter** | Vượt lỗi tạm thời, tránh đồng loạt retry | Retry không giới hạn; retry thao tác gây tác dụng phụ không idempotent |
| **Circuit breaker** | Ngăn lỗi dependency tiếp tục kéo sập caller | Xem breaker là biện pháp sửa lỗi gốc |
| **Bulkhead / isolation** | Tách quota, thread pool, connection và tải giữa nhóm công việc | Để một service chậm làm cạn toàn bộ tài nguyên |
| **Rate limit và backpressure** | Chặn quá tải trước khi lan rộng | Hàng đợi tăng vô hạn |
| **Graceful degradation** | Giữ chức năng cốt lõi nếu phụ trợ lỗi | Trả thành công giả cho nghiệp vụ cần tính đúng đắn |
| **Health checks** | Tách liveness và readiness; điều khiển routing/khởi động | Readiness phụ thuộc mọi hệ thống không thiết yếu rồi gây lỗi dây chuyền |
| **Multi-AZ / DR** | Giảm tác động mất thành phần/vùng, phục hồi dữ liệu | Tin RTO/RPO chỉ từ sơ đồ mà chưa diễn tập |

Ví dụ: dịch vụ gợi ý sản phẩm không phản hồi không nên khiến toàn bộ checkout thất bại nếu gợi ý không phải bước bắt buộc. Ngược lại, khi không xác nhận được kết quả thu tiền, **không được hiển thị “đã thanh toán”** chỉ để trải nghiệm người dùng mượt hơn.

### Cơ chế mở rộng

Microservices có thể mở rộng riêng dịch vụ nhiều tải, nhưng chỉ khi **điểm nghẽn thực sự** nằm trong dịch vụ đó và dependency phía sau đủ năng lực. Tăng gấp đôi số bản sao API không giúp nếu database, broker hoặc đối tác thanh toán đã đạt giới hạn.

Cần đo CPU, bộ nhớ, throughput, p95/p99 latency, queue depth/age, tỷ lệ lỗi và saturation của dependency trước khi chọn cấu hình autoscaling. Với tác vụ nền, mở rộng theo độ sâu/tuổi hàng đợi có thể hữu ích hơn CPU.

## 7. Bảo mật và quản trị ranh giới tin cậy

Hệ thống có nhiều dịch vụ và kết nối cần kiểm soát **cả truy cập từ ngoài vào và truy cập giữa các dịch vụ**.

1. **Identity và authorization:** xác thực client bằng cơ chế phù hợp; API gateway kiểm tra token cơ bản, còn service sở hữu dữ liệu phải tự thực thi quyền nghiệp vụ. Không mặc định request đi từ mạng nội bộ là đáng tin cậy.
2. **Service identity:** mỗi workload có danh tính và quyền tối thiểu; dùng mTLS hoặc phương thức bảo vệ đường truyền phù hợp, quản lý chứng chỉ và vòng đời khóa.
3. **Segmentation và egress:** định tuyến qua vùng mạng/endpoint được phép, policy truy cập DB/broker, kiểm soát kết nối ra ngoài và phân tách môi trường.
4. **Secrets:** dùng hệ thống quản lý secrets, tránh ghi key trong image/source/log; luân chuyển khi có thay đổi người dùng hoặc sự cố.
5. **Data classification và residency:** xác định nơi dữ liệu cá nhân, thông tin thanh toán, bản sao, log và sự kiện được lưu/truyền; áp dụng mã hóa khi lưu và truyền.
6. **Threat modeling:** xem xét API authorization, replay, giả mạo sự kiện, lộ dữ liệu qua log, cấu hình mesh/gateway, pipeline supply chain, image và thư viện.
7. **Audit:** ghi sự kiện truy cập và thay đổi quan trọng đủ để truy nguyên, nhưng tránh đưa dữ liệu nhạy cảm vào trace hoặc payload sự kiện không cần thiết.

Một mô hình chia nhỏ dịch vụ có thể **tăng số điểm tấn công** nếu IAM hoặc network policy cấu hình rộng; tách service không tự động tăng bảo mật. Tương tự, ESB hoặc API gateway không thay thế kiểm tra quyền nghiệp vụ ở service đích.

Nếu hệ thống có nhiều tenant, phải truyền **tenant context đã xác thực** xuyên các API, queue và job, đồng thời ngăn truy cập chéo ở tầng dữ liệu. Tenant ID do client gửi không tự nó là bằng chứng ủy quyền.

## 8. Triển khai trên cloud: quyết định hạ tầng phải đi theo yêu cầu

### 8.1. Compute và mô hình triển khai

SOA và microservices có thể dùng máy ảo, container, nền tảng container được quản lý hoặc serverless. Chọn theo yêu cầu triển khai, thời gian khởi động, tải, kết nối, chi phí vận hành và ràng buộc tổ chức.

| Lựa chọn | Phù hợp khi | Cần kiểm soát |
| --- | --- | --- |
| **VM/managed app platform** | Cần môi trường đơn giản hoặc ứng dụng legacy | Image chuẩn, bản vá, autoscaling, HA |
| **Container orchestration** | Nhiều workload cần rolling update, service discovery, tự phục hồi | Cluster vận hành, chính sách mạng, quyền, capacity, chi phí |
| **Serverless functions / managed containers** | Tải biến động, tác vụ ngắn/độc lập, muốn giảm quản trị máy chủ | Cold start, giới hạn chạy, concurrency, kết nối DB, chi phí theo lưu lượng |
| **Managed database / broker** | Muốn giảm gánh nặng vận hành thành phần nền tảng | Backup, quyền, quota, failover, giới hạn dịch vụ, vùng triển khai |

**Kubernetes không phải điều kiện định nghĩa microservices.** Một vài service chạy trên nền tảng ứng dụng được quản lý vẫn có thể phát hành độc lập; một monolith chạy trên Kubernetes vẫn là monolith.

### 8.2. Mạng và phát hiện dịch vụ

Khi triển khai lên cloud cần xác định:

- Ranh giới public/private, ingress, load balancer, API gateway, DNS và cách service discovery hoạt động.
- Vùng và availability zone đặt workload/data; độ trễ và phí **truyền liên vùng** nếu có.
- Kết nối tới database, broker, đối tác ngoài; chính sách egress và giới hạn cổng/kết nối.
- Nơi áp dụng TLS/mTLS, IAM, rate limit, network policy và web application firewall nếu có yêu cầu.
- Cơ chế thay đổi route/version an toàn khi triển khai và phục hồi.

Không nên dùng service discovery hoặc mesh để che giấu hợp đồng giao tiếp chặt: kết nối đến được không đồng nghĩa mọi thay đổi API đều tương thích.

### 8.3. CI/CD và độc lập phát hành

Một service phát hành độc lập cần pipeline tối thiểu: build, kiểm tra dependency, test contract, scan bảo mật, tạo artifact có định danh, triển khai có giới hạn, giám sát và rollback hoặc roll-forward phù hợp.

**Tính tương thích ngược** đặc biệt quan trọng:

- Thêm field tùy chọn có mặc định; không yêu cầu toàn bộ consumer nâng cấp tức thì.
- Với API công khai, tránh thay đổi ngữ nghĩa cùng tên trường; đặt version khi thay đổi phá vỡ hợp đồng.
- Với sự kiện, consumer phải xử lý các phiên bản được hỗ trợ, dữ liệu thiếu và thông điệp trùng.
- Với database, ưu tiên chu trình **expand → migrate → contract** để tránh phiên bản ứng dụng mới/cũ cùng lúc gây lỗi.

Trong mô hình SOA với nền tảng tích hợp, cần kiểm tra thêm tương thích mapping, routing, schema chuẩn hóa và ảnh hưởng của việc thay đổi flow ESB.

## 9. Observability, vận hành và khôi phục

Một hệ thống phân tán không thể được vận hành tốt bằng cách chỉ xem log ở từng máy.

### Các dữ liệu cần kết nối

- **Metrics:** request rate, error rate, p50/p95/p99, saturation, số request timeout, queue age, job retry, tỷ lệ lỗi dependency, mức tiêu thụ tài nguyên.
- **Distributed tracing:** correlation ID/trace ID xuyên API, queue và job; dùng để hiểu đường đi thực tế của một yêu cầu.
- **Structured logs:** chứa định danh service, phiên bản, môi trường, request/trace ID và mã lỗi; tránh ghi token, mật khẩu, dữ liệu nhạy cảm.
- **Service map và ownership:** ai phụ trách service, dependency upstream/downstream, runbook, dashboard, on-call rotation.
- **Business metrics:** số đơn đặt thành công, số lần thu tiền trùng/không rõ trạng thái, sự kiện chờ xử lý, sai lệch đối soát.

Theo dõi **SLI/SLO theo luồng người dùng**, không chỉ theo sức khỏe từng container. Ví dụ SLO checkout phải quy định thế nào là checkout thành công, thời hạn phản hồi, kỳ đo và điều kiện loại trừ hợp lý. **SLA** là cam kết trong hợp đồng và có thể khác SLO nội bộ.

### Quản lý sự cố và lỗi dữ liệu

Một runbook phù hợp cần trả lời: dịch vụ hoặc luồng nào bị ảnh hưởng; ai nhận cảnh báo; có thể giảm tải hay tắt tính năng phụ trợ không; có thông điệp nào tồn đọng hoặc bị xử lý trùng; cách replay an toàn; và ai quyết định phục hồi dữ liệu.

**RTO** là thời gian tối đa chấp nhận để khôi phục; **RPO** là lượng dữ liệu có thể mất tính theo thời gian. Hai chỉ tiêu này phải được xác định cho luồng nghiệp vụ và dữ liệu liên quan, không chỉ cho từng VM. Ví dụ restore Booking nhưng mất outbox Payment có thể tạo bất nhất giao dịch dù tất cả server hoạt động.

Diễn tập các tình huống thực: một service mất kết nối DB, broker chậm, một AZ mất khả dụng, dependency trả lỗi dài hạn, event bị gửi lại và deploy tương thích sai. Ghi lại kết quả theo SLO, RTO/RPO và chi phí xử lý.

## 10. Hiệu năng, chi phí và các đánh đổi Well-Architected

### 10.1. Microservices không mặc định nhanh hơn

Gọi hàm nội bộ thường ít overhead hơn HTTP qua mạng. Với microservices, serialization, TLS, DNS, load balancing, database phân tán và hàng đợi đều có chi phí. Thiết kế nên ưu tiên **giảm số hop trên đường găng**, dùng cache đọc có kiểm soát và đưa công việc không cần kết quả tức thì sang bất đồng bộ.

Khi cần hiệu năng, phải đo **p95/p99 tại tải mục tiêu**, không chỉ trung bình. Microservices giúp **mở rộng chọn lọc**, nhưng không bảo đảm throughput tốt nếu hệ thống thường xuyên cần gọi đồng bộ giữa nhiều dịch vụ.

### 10.2. TCO bao gồm hạ tầng lẫn độ phức tạp

Một mô hình khái niệm:

\[
TCO = C_{\text{compute}} + C_{\text{data}} + C_{\text{network}} + C_{\text{platform}} + C_{\text{ops}} + C_{\text{reliability/security}}
\]

Trong đó:

- **Compute:** bản sao dịch vụ, capacity dự phòng, autoscaling, môi trường test.
- **Data:** DB, index, backup, replica, storage và khôi phục.
- **Network:** load balancer, gateway, egress, truyền liên AZ/vùng khi tính phí.
- **Platform:** broker, discovery, mesh, registry, CI/CD, observability.
- **Ops:** on-call, sự cố, kiểm thử contract, quản lý schema và quyền.
- **Reliability/security:** kiểm thử DR, audit, scanning, secrets, chính sách và sửa lỗi.

Microservices có thể tiết kiệm chi phí khi một phần nhỏ ứng dụng cần tài nguyên rất lớn; ngược lại tách quá nhiều service có tải nhỏ làm tăng tài nguyên nền và công vận hành. SOA tích hợp nhiều hệ thống có thể tránh nhân bản năng lực chung, nhưng ESB hoặc lớp trung gian nặng cũng có chi phí và điểm nghẽn.

### 10.3. Đặt quyết định trong sáu trụ cột Well-Architected

| Trụ cột đánh giá | Câu hỏi cho SOA và microservices |
| --- | --- |
| **Operational Excellence** | Đội nào sở hữu service? Có IaC, runbook, pipeline và quản lý thay đổi? |
| **Security** | Identity, quyền theo service, dữ liệu, secret và audit có ranh giới rõ? |
| **Reliability** | Có timeout, circuit breaker, idempotency, HA, chiến lược DR và diễn tập? |
| **Performance Efficiency** | Có đo p95/p99, tránh chuỗi đồng bộ dài và mở rộng đúng nút nghẽn? |
| **Cost Optimization** | Có phân bổ TCO theo ứng dụng/service; có giảm dịch vụ và tài nguyên không cần? |
| **Sustainability** | Có quyền chọn kích thước, autoscaling, giảm chạy nhàn rỗi và lưu trữ không cần thiết? |

Các trụ cột giúp **đánh giá và cải tiến định kỳ**, không tạo ra một đáp án duy nhất. Một quyết định có thể tốt cho khả năng phát hành nhưng làm tăng chi phí và rủi ro vận hành; phải ghi rõ ai chấp nhận đánh đổi.

## 11. Khi nào chọn SOA, microservices hoặc modular monolith?

### Khung quyết định

| Tín hiệu từ yêu cầu | Cách tiếp cận thường đáng xem xét |
| --- | --- |
| Cần tích hợp CRM, ERP, billing và các ứng dụng lâu đời của nhiều bộ phận | SOA và nền tảng tích hợp có quản trị hợp đồng |
| Có các team/domain độc lập, cần phát hành khác nhịp và tải rất khác nhau | Microservices theo ranh giới domain |
| Đội nhỏ, domain thay đổi nhanh, thiếu tự động hóa và observability | Modular monolith có kỷ luật ranh giới module |
| Một phần hệ thống cần cô lập bảo mật/tải/chi phí đặc biệt | Tách có chọn lọc thành service riêng; phần còn lại có thể giữ monolith |
| Nhiều service hiện phải triển khai cùng nhau và chia sẻ trực tiếp một schema | Xem lại ranh giới; tránh “distributed monolith” |
| Yêu cầu đồng bộ dữ liệu mạnh trong một quy trình ngắn và không có lợi ích tách đáng kể | Giữ giao dịch trong cùng ranh giới xử lý khi phù hợp |
| Phải hỗ trợ nhiều đối tác với hợp đồng tích hợp đã có | Tổ chức adapter, API contract và event integration; không nhất thiết microservice hóa tất cả |

**Đừng quyết định chỉ vì một thuật ngữ đang phổ biến.** Trước khi tách, hỏi tác động nghiệp vụ: cần mở rộng độc lập đến mức nào, nhóm nào chịu trách nhiệm, độ tin cậy bắt buộc bao nhiêu, và chi phí hạ tầng/vận hành tối đa được chấp nhận là gì.

### Điều kiện tối thiểu để microservices đem lại lợi ích

- Ranh giới domain được hiểu đủ để có **ownership** rõ.
- CI/CD và triển khai một service không buộc release mọi service khác.
- Kiểm thử contract/API, chiến lược version, chạy được nhiều phiên bản cạnh nhau khi cần.
- Quan sát phân tán, dashboard và người nhận cảnh báo có trách nhiệm.
- Kế hoạch xử lý dữ liệu, transaction và lỗi mạng.
- Công cụ và kỹ năng vận hành tương xứng số lượng service.

Nếu những nền tảng này chưa có, có thể đầu tư vào **module hóa, test, CI/CD, metrics** trước, rồi tách dần các domain có bằng chứng cần tự chủ.

## 12. Tình huống thực hành xuyên suốt: nền tảng đặt chỗ trên cloud

Một nền tảng có chức năng tìm dịch vụ, đặt chỗ, thanh toán và gửi thông báo. Đội sản phẩm quan sát:

- Tìm kiếm chiếm phần lớn lưu lượng, tăng đột biến theo chiến dịch.
- Booking cần bảo đảm không tạo trùng đơn và tránh đặt quá số lượng chỗ.
- Payment phụ thuộc cổng thanh toán bên ngoài, có callback trễ.
- Notification quan trọng với trải nghiệm nhưng không được làm tắc quy trình thanh toán.
- Nhóm vận hành đặt mục tiêu theo dõi **p95**, tỷ lệ đặt chỗ thành công, chi phí mỗi đơn và khả năng phục hồi sau sự cố.

### 12.1. Đề xuất phân ranh giới

| Thành phần | Sở hữu | Giao tiếp ưu tiên | Rủi ro chính |
| --- | --- | --- | --- |
| Catalog/Search | Nội dung và kết quả tìm kiếm | API đọc, cập nhật chỉ mục bất đồng bộ | Cache cũ, tăng tải tìm kiếm |
| Booking | Đơn, trạng thái giữ chỗ, quy tắc hủy | API từ client; phối hợp Inventory/Payment | Trùng đơn, bất nhất sau timeout |
| Inventory | Số lượng chỗ khả dụng và reservation | API đặt/giải phóng giữ chỗ với key | Overselling, race condition |
| Payment | Lệnh thanh toán, đối soát, webhook | API + webhook/sự kiện | Thu trùng, trạng thái không rõ |
| Notification | Tạo, gửi, theo dõi thông báo | Consume event sau trạng thái nghiệp vụ | Gửi trùng, backlog, lỗi provider |

Đây chỉ là một phương án; nếu đội nhỏ hoặc transaction Booking–Inventory gắn kết chặt, hai domain này có thể nằm cùng service hoặc module lúc đầu, miễn tính đúng đắn được chứng minh.

### 12.2. Một luồng đặt chỗ có khả năng phục hồi

~~~mermaid
flowchart TD
    UI["Client / API Gateway"] --> BK["Booking API"]
    BK --> BDB[("Booking DB + Outbox")]
    BK --> INV["Inventory API / DB"]
    BK --> PAY["Payment API / DB"]
    PAY --> EXT["Cổng thanh toán"]
    BDB --> RELAY["Outbox relay"]
    RELAY --> BROKER["Broker"]
    BROKER --> NOTIFY["Notification worker"]
    BROKER --> REPORT["Analytics projection"]
~~~

Luồng cần xác định trạng thái như **PENDING, RESERVED, PAYMENT_PENDING, CONFIRMED, FAILED, CANCELLED** và hành động hợp lệ của từng trạng thái. Không nên cố gắng giữ một HTTP request chờ callback thanh toán bên thứ ba trong thời gian dài; có thể trả trạng thái pending kèm mã tra cứu và cập nhật bất đồng bộ.

### 12.3. Bảng xử lý lỗi

| Tình huống | Cách xử lý hợp lý | Bằng chứng cần kiểm chứng |
| --- | --- | --- |
| User bấm đặt chỗ nhiều lần | Idempotency key, unique constraint theo nghiệp vụ | Một yêu cầu logic không tạo hai booking |
| Timeout sau khi gọi Payment | Tra cứu trạng thái bằng transaction key, không tự thu lại ngay | Không thu tiền hai lần khi retry |
| Inventory từ chối giữ chỗ | Trả trạng thái rõ, không thực hiện thanh toán sai | Không oversell dưới tải đồng thời |
| Broker tạm thời lỗi | Lưu outbox trong giao dịch, relay lại có kiểm soát | Sự kiện cuối cùng được xử lý, consumer idempotent |
| Notification provider lỗi | Retry có hạn mức và dead-letter path | Checkout vẫn hoàn tất đúng |
| Database Booking lỗi | Health check, failover/restore, kiểm tra outbox và nhất quán | RTO/RPO đo qua diễn tập |
| Search quá tải | Cache, rate limit, autoscale, suy giảm có kiểm soát | Checkout không bị kéo sập bởi search |

### 12.4. Yêu cầu kiến trúc và phép kiểm chứng minh họa

Các giá trị sau là **giả định phục vụ bài tập**, không phải mức SLO mặc định:

| Yêu cầu giả định | Phép thử |
| --- | --- |
| Search p95 ≤ 300 ms ở 500 request/giây trong kịch bản chốt | Load test với dữ liệu và cache thực tế đại diện |
| Booking không tạo trùng đơn khi gửi lại request với cùng idempotency key | Concurrency/retry test và kiểm tra constraint |
| Tỷ lệ checkout thành công theo SLI/SLO đã được Product, SRE thống nhất | Synthetic transaction, dashboard end-to-end |
| Lỗi Notification không ngăn Booking ghi nhận giao dịch thành công | Thử ngắt provider và xử lý backlog |
| Không mất sự kiện xác nhận do crash sau commit Booking | Diễn tập relay outbox, gửi trùng và replay |
| Đáp ứng RTO/RPO đã được phê duyệt cho Booking + Payment | Diễn tập restore/failover và đối soát dữ liệu |
| Chi phí cloud trong ngân sách ở tải bình thường/đỉnh | Cost model gồm compute, network, broker, DB, observability, DR |

**Quan trọng:** yêu cầu “không tạo trùng booking/không thu trùng” không đạt được chỉ bằng retry hoặc thêm replica. Phải thiết kế bất biến nghiệp vụ, khóa idempotency, constraint database và đối soát.

## 13. Chuyển đổi dần từ hệ thống hiện có

Áp dụng **Strangler Fig Pattern**: đưa một số luồng qua façade/API gateway rồi thay dần chức năng cũ bằng dịch vụ mới, thay vì cố chia toàn bộ ứng dụng trong một lần.

~~~mermaid
flowchart LR
    C["Client"] --> F["Façade / Gateway"]
    F --> OLD["Ứng dụng hiện tại"]
    F --> NEW["Dịch vụ mới được tách"]
    NEW --> OWN[("Dữ liệu sở hữu")]
    OLD --> LEGACY[("Dữ liệu cũ")]
    OLD -. "Sự kiện / adapter chuyển tiếp" .-> NEW
~~~

### Kế hoạch sáu bước

1. **Lập bản đồ domain và dependency.** Đo số yêu cầu thay đổi liên module, deployment cadence, tải, lỗi và quyền truy cập dữ liệu. Chọn một năng lực có ranh giới rõ, ít transaction xuyên miền.
2. **Ổn định hợp đồng.** Định nghĩa API/sự kiện có phiên bản, ownership và dữ liệu tối thiểu cần trao đổi; thiết kế consumer còn chạy khi producer deploy trước.
3. **Tạo đường triển khai độc lập.** CI/CD, image/artifact, cấu hình, secrets, logs, metrics, alerts, rollback và runbook cho service mới.
4. **Tách quyền sở hữu dữ liệu.** Tránh ghi đồng thời không kiểm soát vào hai schema. Khi cần migration, dùng sao chép, đối soát và cutover rõ ràng; thử khôi phục.
5. **Chuyển lưu lượng có kiểm soát.** Canary, feature flag, shadow read (khi phù hợp), giám sát sai lệch; có tiêu chí dừng và quay lại.
6. **Gỡ phụ thuộc cũ.** Sau khi có bằng chứng đủ lâu, xóa route/adapter/code không còn dùng; cập nhật ADR và sơ đồ hệ thống.

**Chọn điểm tách:** Notification thường dễ độc lập hơn một transaction thanh toán hoặc tồn kho đang phụ thuộc sâu vào cùng database. Nhưng “dễ” còn phụ thuộc mức độ liên kết và khả năng đối soát của hệ thống thực tế.

### Các phép kiểm tra khi tách

- Contract tests giữa producer/consumer, schema compatibility và khả năng chạy hai phiên bản.
- Kiểm thử fault injection: service mới chết, mạng chậm, message lặp, broker trì hoãn.
- Theo dõi độ trễ, lỗi, chi phí, triển khai, số sự cố trước/sau khi tách.
- Kiểm tra phân quyền IAM, TLS, secret, service identity, dữ liệu lưu trú và audit.
- Diễn tập rollback khi đường cũ và đường mới đang có dữ liệu hoặc sự kiện chồng lấn.

Không nên coi việc tạo thêm deployment là “di cư thành công” nếu vẫn cần phát hành đồng bộ và chia sẻ bảng nghiệp vụ xuyên service.

## 14. Cách ghi quyết định bằng Architecture Decision Record (ADR)

Một ADR giúp người đến sau hiểu mục tiêu, các lựa chọn, thử nghiệm và rủi ro đã được chấp nhận.

~~~markdown
# ADR-032: Tách Notification khỏi ứng dụng đặt chỗ

Trạng thái: Đề xuất / chấp thuận có điều kiện
Decision owner: Kiến trúc sư và đại diện Product/SRE
Ngày: YYYY-MM-DD

Bối cảnh:
- Provider gửi thông báo có lỗi tạm thời, gây chậm checkout.
- Notification có tải và vòng đời triển khai khác Booking.
- Team đã có CI/CD, broker, dashboard và on-call.

Phương án:
A. Giữ một modular monolith, xử lý qua job nội bộ.
B. Tách Notification service tiêu thụ sự kiện từ outbox.
C. Tách toàn bộ các miền ngay lập tức.

Quyết định đề xuất:
- Chọn B, giữ Booking là nguồn sự thật của trạng thái đơn.
- Booking ghi sự kiện vào outbox cùng transaction local.
- Notification xử lý idempotent, retry có giới hạn, DLQ khi cần.

Đánh đổi:
- Phát sinh độ trễ eventual consistency và vận hành broker.
- Cần trace xuyên dịch vụ, xử lý replay và quan sát backlog.

Tiêu chí nghiệm thu:
- Lỗi provider không làm checkout thất bại.
- Không mất sự kiện sau crash/restart; gửi trùng xử lý an toàn.
- Đo p95 checkout, queue age, chi phí và quy trình phục hồi.

Điều kiện xem lại:
- Tải hoặc chi phí đổi đáng kể; SLO bị vi phạm;
  nhu cầu domain thay đổi hoặc lỗi replay không xử lý được.
~~~

## 15. Sai lầm thường gặp và cách tránh

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chia service theo từng bảng hoặc controller | Quá nhiều hop và phát hành đồng bộ | Chia theo bounded context/bất biến nghiệp vụ |
| Cho mọi service truy cập chung schema | Thay đổi DB gây lỗi dây chuyền | Quyền sở hữu dữ liệu, API hoặc event projection |
| Dùng ESB/gateway chứa mọi quy tắc nghiệp vụ | Tầng tích hợp thành nút nghẽn đổi mới | Giữ logic nghiệp vụ ở domain sở hữu |
| Coi microservices bắt buộc dùng Kubernetes | Mua thêm độ phức tạp hạ tầng | Chọn runtime theo yêu cầu đo được |
| Không thiết kế lỗi mạng và timeout | Sự cố cục bộ lan rộng | Timeout budget, retry an toàn, bulkhead, circuit breaker |
| Mặc định message chỉ được xử lý một lần | Đặt/thu tiền/gửi thông báo trùng | Idempotency, deduplication, outbox và đối soát |
| Chỉ đo CPU của từng service | Không thấy lỗi business workflow | SLO theo hành trình người dùng, trace, business metrics |
| Chia service trước khi rõ domain | Phải liên tục sửa nhiều dịch vụ | Module hóa trước, tách theo dữ liệu sử dụng thực |
| Sao chép dữ liệu nhưng thiếu quy tắc nhất quán | Projection sai hoặc luồng nghiệp vụ đưa ra quyết định trên dữ liệu cũ | Quy định mức nhất quán, freshness, quyền source-of-truth |
| Triển khai độc lập nhưng thiếu owner/on-call | Không ai xử lý lỗi giao tiếp | Ownership, runbook, alert và trách nhiệm trực rõ |
| Xem bảo mật mesh/gateway thay cho authorization | Vẫn có thể đọc sai dữ liệu nghiệp vụ | Kiểm tra quyền ở service và data layer |
| Chỉ tính chi phí compute | Thiếu ngân sách broker, DB, egress, observability và DR | TCO đầy đủ theo các kịch bản tải |

## 16. Bài tập thực hành

Một công ty có một ứng dụng quản lý bán hàng lớn phục vụ 200 cửa hàng. Ứng dụng tích hợp ERP, thanh toán và vận chuyển; mỗi tháng có nhiều đợt ra mắt tính năng. Gần đây, lỗi gửi email làm nghẽn luồng tạo đơn, trong khi tìm kiếm sản phẩm có lưu lượng cao gấp nhiều lần thanh toán. Đội kỹ thuật gồm ba nhóm độc lập nhưng chưa có distributed tracing đầy đủ.

Hãy hoàn thành:

1. **Phân tích yêu cầu:** viết ít nhất sáu yêu cầu có tiêu chí đo cho tạo đơn, tìm kiếm, tích hợp ERP, thanh toán, bảo mật, chi phí và vận hành. Chỉ rõ các chỉ tiêu nào vẫn là giả định cần xác nhận.
2. **Đề xuất ba phương án:** (A) modular monolith có job nền, (B) SOA với tầng tích hợp các hệ thống hiện hữu, (C) tách có chọn lọc thành microservices. Nêu ưu/nhược, phụ thuộc và mức phù hợp với năng lực đội.
3. **Phác thảo ranh giới domain:** xác định dữ liệu sở hữu của Order, Catalog/Search, Payment, Notification và Adapter/Integration.
4. **Vẽ luồng lỗi:** khi Payment timeout sau khi đã nhận yêu cầu, hệ thống phân biệt “chưa thanh toán” và “không rõ kết quả” như thế nào? Làm sao tránh thu trùng khi retry?
5. **Thiết kế contract:** một API có idempotency key và một sự kiện có event_id/version; chỉ rõ thời điểm phát sự kiện và cách xử lý message lặp.
6. **Vận hành:** đề xuất SLI/SLO, dashboard, trace propagation, cảnh báo queue age, runbook khi broker mất kết nối và một kịch bản DR.
7. **Quyết định:** viết ADR ngắn chọn phương án phù hợp; trình bày rủi ro còn lại, TCO ước tính và điều kiện xem xét lại.

**Gợi ý tự đánh giá:** bài làm tốt không cần tách nhiều dịch vụ nhất. Nó chỉ ra rõ ai sở hữu dữ liệu và quy tắc, khi nào bắt buộc đồng bộ, nơi có thể dùng sự kiện, cách giữ tính đúng đắn và bằng chứng cần đo để quyết định.

## 17. Checklist rà soát trước khi chốt kiến trúc

- [ ] Bắt đầu từ mục tiêu nghiệp vụ, tải, SLO, RTO/RPO, bảo mật, ngân sách và năng lực đội.
- [ ] Ranh giới service/module bám theo năng lực nghiệp vụ; xác định owner và nguồn dữ liệu sự thật.
- [ ] Mỗi API/sự kiện có hợp đồng, phiên bản và cách xử lý thay đổi tương thích.
- [ ] Các luồng qua mạng có timeout, retry an toàn, backpressure và xử lý lỗi rõ.
- [ ] Những thao tác tạo tác dụng phụ có idempotency/deduplication; có đối soát nếu kết quả không rõ.
- [ ] Không phụ thuộc truy cập trực tiếp DB nội bộ của service khác.
- [ ] Các workflow phân tán nêu rõ trạng thái trung gian, bù trừ, outbox và quy trình replay.
- [ ] Có thiết kế identity, authorization, secret, network policy, mã hóa, audit và dữ liệu lưu trú.
- [ ] Có pipeline triển khai độc lập thực tế và chiến lược rollback/roll-forward.
- [ ] Có trace, logs, metrics, SLI/SLO theo hành trình người dùng và ownership khi sự cố.
- [ ] Có phép thử tải, lỗi mạng, message trùng, DR và dữ liệu bất nhất.
- [ ] So sánh TCO gồm hạ tầng, dữ liệu, truyền mạng, platform và vận hành.
- [ ] Có ADR với đánh đổi, rủi ro còn lại, bằng chứng kiểm chứng và điều kiện xem xét lại.

## Ghi nhớ

**SOA** tổ chức năng lực phần mềm thành dịch vụ có hợp đồng để tích hợp và tái sử dụng, đặc biệt hữu ích trong môi trường nhiều hệ thống. **Microservices** chú trọng ranh giới nghiệp vụ, quyền sở hữu dữ liệu và khả năng triển khai tương đối độc lập, phù hợp khi nhu cầu và tổ chức đủ lớn để hưởng lợi từ tự chủ từng dịch vụ. **Modular monolith** vẫn là lựa chọn đáng cân nhắc khi bài toán chưa cần phân tán.

Kiến trúc tốt được chứng minh bằng khả năng đáp ứng **yêu cầu nghiệp vụ, tính đúng đắn, SLO, bảo mật, mở rộng, chi phí và vận hành** trong thực tế. Tên mô hình chỉ là điểm khởi đầu; hợp đồng, ranh giới dữ liệu, kiểm thử lỗi và bằng chứng Well-Architected mới cho thấy lựa chọn có phù hợp hay không.
