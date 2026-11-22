# Phân biệt tự chủ về nghiệp vụ với độc lập về hạ tầng trong Microservices

## Mục tiêu học tập

Khi thiết kế Microservices, một hệ thống có thể có nhiều container, nhiều repository, nhiều database và nhiều pipeline triển khai, nhưng vẫn là một **distributed monolith**: mỗi thay đổi nghiệp vụ nhỏ buộc nhiều dịch vụ sửa cùng lúc. Ngược lại, một **modular monolith** có thể chứa những ranh giới nghiệp vụ rõ ràng trong cùng một tiến trình, dù chưa có hạ tầng triển khai riêng cho từng mô-đun.

Sự khác biệt xuất phát từ hai câu hỏi độc lập:

- **Tự chủ về nghiệp vụ (business/domain autonomy):** Thành phần có quyền sở hữu và tiến hóa một năng lực nghiệp vụ, quy tắc và dữ liệu của nó thông qua hợp đồng rõ ràng đến mức nào?
- **Độc lập về hạ tầng (infrastructure/deployment independence):** Thành phần có thể build, triển khai, chạy, mở rộng, giám sát và phục hồi bằng những cơ chế riêng đến mức nào?

Hai tính chất này hỗ trợ nhau nhưng **không đồng nghĩa**. Microservices chỉ đem lại giá trị bền vững khi ranh giới nghiệp vụ, hợp đồng tích hợp, quyền sở hữu dữ liệu và năng lực vận hành phù hợp với lý do tổ chức tách hệ thống.

Sau bài học, bạn có thể:

1. Giải thích được khác biệt giữa **tự chủ quyết định nghiệp vụ** và **tách biệt tài nguyên hoặc công cụ triển khai**.
2. Nhận diện service có container riêng nhưng vẫn lệ thuộc chặt vào database, quy tắc, hợp đồng hoặc lịch phát hành của service khác.
3. Sử dụng **bounded context**, business capability, invariant, data ownership và change coupling để đánh giá ranh giới dịch vụ.
4. Phân tích bốn tình huống kết hợp mức tự chủ nghiệp vụ và mức độc lập hạ tầng, kèm giới hạn thực tế của từng tình huống.
5. Lựa chọn giữa mô-đun trong modular monolith, service độc lập, hay tiếp tục tích hợp qua ranh giới rõ ràng dựa trên chi phí và lợi ích có thể kiểm chứng.
6. Xây dựng bộ câu hỏi và bài thực hành để chứng minh một dịch vụ có khả năng thay đổi nghiệp vụ độc lập trong điều kiện thực tế.

**Bối cảnh:** Bài học thuộc nhóm **Ranh giới dịch vụ** của kiến trúc Microservices. “Độc lập” trong bài luôn là một phổ mức độ và một mục tiêu thiết kế có điều kiện; không có hệ thống phân tán thực tế nào hoàn toàn không có phụ thuộc.

## 1. Hai khái niệm thường bị trộn lẫn

### 1.1. Tự chủ về nghiệp vụ là gì?

Một thành phần có **tự chủ về nghiệp vụ** khi nó sở hữu một trách nhiệm nghiệp vụ tương đối trọn vẹn và có quyền điều chỉnh cách thực hiện trách nhiệm đó mà không liên tục phải phối hợp chỉnh sửa nội bộ của các thành phần khác.

Các dấu hiệu thường gặp:

- **Trách nhiệm rõ ràng:** Có thể nói “Inventory chịu trách nhiệm giữ và giải phóng hàng” hoặc “Payment chịu trách nhiệm vòng đời giao dịch thanh toán”, thay vì “service A xử lý controller, service B xử lý repository”.
- **Quy tắc nghiệp vụ nằm đúng chủ sở hữu:** Inventory tự đảm bảo không giữ vượt số hàng khả dụng; Order không truy cập bảng của Inventory để tự trừ tồn kho.
- **Dữ liệu có nguồn sự thật:** Mỗi dữ liệu quan trọng có một chủ thể chịu trách nhiệm về ý nghĩa, tính hợp lệ và thao tác ghi. Thành phần khác tích hợp qua API hoặc event.
- **Hợp đồng thay đổi có kiểm soát:** Service có thể thay đổi thuật toán, schema nội bộ hoặc chính sách của mình mà giữ nguyên contract hoặc cung cấp con đường tương thích cho consumer.
- **Quyết định và ownership rõ:** Nhóm sở hữu domain hiểu nhu cầu nghiệp vụ, đưa ra quyết định trong phạm vi được giao và chịu trách nhiệm cho hành vi của service.
- **Ít thay đổi dây chuyền:** Một thay đổi trong chính sách của một bounded context thông thường không buộc nhiều context sửa mã cùng lúc.

Tự chủ không có nghĩa “mỗi dịch vụ tự làm gì cũng được”. Một service vẫn phải tuân thủ chính sách bảo mật, chuẩn dữ liệu liên miền, quy định tổ chức, nghĩa vụ tương thích hợp đồng và cam kết với người dùng. Tự chủ là **quyền sở hữu quyết định trong ranh giới xác định**, không phải miễn mọi phối hợp.

### 1.2. Độc lập về hạ tầng là gì?

Một thành phần có **độc lập về hạ tầng** ở mức cao khi nhiều quyết định kỹ thuật và vòng đời vận hành của nó có thể được thực hiện riêng:

- **Build:** Có artifact/version riêng, không bắt buộc rebuild tất cả thành phần khác.
- **Deploy:** Có thể phát hành, rollback và cấu hình riêng trong mức tương thích được hỗ trợ.
- **Runtime isolation:** Chạy bằng tiến trình hoặc container riêng, lỗi của một tiến trình không đồng nghĩa tất cả tiến trình khác sập.
- **Resource scaling:** CPU, memory, concurrency và số replica có thể phân bổ phù hợp tải của service đó.
- **Data infrastructure:** Có schema, database, tài khoản truy cập hoặc hệ quản trị riêng tùy yêu cầu. Mức cách ly vật lý là một quyết định hạ tầng khác với quyền sở hữu dữ liệu.
- **Operations:** Có health signal, logging, metrics, tracing, cảnh báo, runbook và quy trình phục hồi tương ứng.
- **Delivery tooling:** Có pipeline, kiểm thử, cấu hình, quyền truy cập và cơ chế triển khai đủ rõ để service không bị ràng buộc vô cớ vào lịch phát hành của toàn hệ thống.

Một service chạy trên **pod riêng trong cùng Kubernetes cluster** đã có một mức cách ly tiến trình; điều đó không tự chứng minh nghiệp vụ của nó độc lập. Ngược lại, service dùng chung hệ thống logging, ingress, message broker, CI platform hoặc cloud account không có nghĩa nó mất toàn bộ quyền tự chủ nghiệp vụ.

### 1.3. Điểm khác biệt cốt lõi

| Câu hỏi | Tự chủ về nghiệp vụ | Độc lập về hạ tầng |
|---|---|---|
| Đối tượng chính | Năng lực, quy tắc, dữ liệu và quyết định nghiệp vụ | Build, deployment, tiến trình, tài nguyên, công cụ vận hành |
| Ranh giới thường dùng | Business capability, bounded context, aggregate/invariant | Process/container, deployment unit, network, cluster, database instance |
| Bằng chứng mạnh | Đổi quy tắc cục bộ mà ít consumer phải sửa; service sở hữu nguồn sự thật | Triển khai/rollback/mở rộng riêng có thể thực hiện và kiểm chứng |
| Câu hỏi về phụ thuộc | Ai phải đồng ý hoặc sửa code khi chính sách đổi? | Thành phần nào phải rebuild, release hay vận hành cùng lúc? |
| Thất bại đặc trưng | Shared schema, domain logic ở nhiều nơi, coupling về ngữ nghĩa | Shared process, deploy lockstep, phụ thuộc tài nguyên hoặc hạ tầng chung |
| Cách cải thiện | Điều chỉnh bounded context, hợp đồng và quyền sở hữu dữ liệu | Tách artifact/runtime, pipeline, cơ chế isolation và vận hành |
| Rủi ro nếu tối đa hóa vô điều kiện | Chia domain quá nhỏ, trùng quy tắc, tranh chấp ownership | Tăng chi phí, phân mảnh nền tảng, nhiều hạ tầng phải quản lý |

**Kết luận đầu tiên:** “Triển khai được độc lập” là khả năng kỹ thuật. “Thay đổi được độc lập” là khả năng kiến trúc gắn với cách nghiệp vụ được phân ranh. Nếu chỉ có khả năng thứ nhất, microservices dễ trở thành hệ thống phân tán bị coupling chặt.

## 2. Hai trục tạo thành bốn tình huống khác nhau

Xem **tự chủ nghiệp vụ** và **độc lập hạ tầng** như hai trục thay vì hai tên gọi của cùng một chất lượng.

| | Độc lập hạ tầng thấp | Độc lập hạ tầng cao |
|---|---|---|
| **Tự chủ nghiệp vụ cao** | **A. Modular monolith được chia miền tốt:** các mô-đun Order, Inventory có trách nhiệm và hợp đồng nội bộ rõ, nhưng deploy cùng một ứng dụng | **B. Microservices có ranh giới phù hợp:** service sở hữu nghiệp vụ, dữ liệu và có năng lực triển khai, scale, phục hồi riêng |
| **Tự chủ nghiệp vụ thấp** | **C. Monolith coupling chặt:** quy tắc lẫn giữa nhiều mô-đun, dùng chung dữ liệu không rõ chủ và phát hành một khối | **D. Distributed monolith:** nhiều tiến trình/container/pipeline nhưng cùng chia một quy tắc hoặc schema, thay đổi phải phối hợp đồng bộ |

Ma trận giúp tránh ba nhầm lẫn:

1. **A không mặc định kém B.** Modular monolith có ranh giới tốt thường là điểm khởi đầu hợp lý nếu nhu cầu vận hành và tổ chức chưa đủ để bù chi phí phân tán.
2. **D không mặc định tốt hơn C.** Chuyển từ monolith coupling chặt sang nhiều service mà giữ nguyên coupling nghiệp vụ thường thêm network failures, độ trễ và chi phí mà không tạo độc lập thay đổi.
3. **B không đồng nghĩa “mỗi service có cả cluster của riêng mình”.** Độc lập cần được định nghĩa ở những chiều phục vụ mục tiêu: deploy, scale, release, failure isolation, ownership. Chia sẻ nền tảng tiêu chuẩn có thể hỗ trợ B.

Sơ đồ tư duy:

~~~mermaid
quadrantChart
    title Hai trục độc lập của kiến trúc
    x-axis "Hạ tầng dùng chung cao" --> "Hạ tầng độc lập cao"
    y-axis "Nghiệp vụ phụ thuộc cao" --> "Nghiệp vụ tự chủ cao"
    quadrant-1 "Microservices phù hợp"
    quadrant-2 "Modular monolith tốt"
    quadrant-3 "Monolith coupling"
    quadrant-4 "Distributed monolith"
    "A - Mô-đun rõ miền": [0.20, 0.82]
    "B - Service có chủ quyền": [0.82, 0.85]
    "C - Module lẫn trách nhiệm": [0.20, 0.16]
    "D - Container hóa máy móc": [0.80, 0.15]
~~~

Các tọa độ chỉ minh họa khái niệm, không phải chỉ số định lượng hay cách xếp hạng công nghệ.

### Ví dụ ngắn của từng ô

**A — Modular monolith:** Trong một ứng dụng Java có ba module domain riêng, module Order chỉ dùng interface của Inventory; Inventory tự giữ quy tắc dự trữ và schema nội bộ. Cả hai cùng được triển khai trong một JAR. Nghiệp vụ có ranh giới rõ nhưng runtime/release còn chung.

**B — Microservices đúng mục tiêu:** Order, Inventory và Payment có dữ liệu chủ, contract versioned và capability riêng; thay đổi logic giữ hàng không yêu cầu deploy Order nếu contract giữ tương thích. Có thể scale Inventory theo tải đọc/ghi tồn kho mà không scale Payment.

**C — Monolith coupling:** OrderController vừa kiểm tra chính sách giảm giá, vừa cập nhật tồn kho, vừa tính phí và ghi thẳng nhiều bảng. Một yêu cầu nhỏ phải sửa nhiều phần; nhưng vẫn có lợi thế transaction và debug trong cùng tiến trình, nên cần đánh giá lại cấu trúc trước khi tách.

**D — Distributed monolith:** Các chức năng ở C được đưa sang ba container và ba repository, nhưng Order vẫn ghi trực tiếp bảng inventory, Payment đọc trạng thái order bằng SQL chung, mọi thay đổi schema buộc cả ba deploy cùng lúc. Về mặt network hệ thống đã phân tán; về quyền quyết định nghiệp vụ vẫn phụ thuộc chặt.

## 3. Bounded context là cơ sở xác định tự chủ nghiệp vụ

### 3.1. Business capability khác với tầng kỹ thuật

Một cách chia chưa hợp lý:

~~~text
API-Service       → nhận HTTP và kiểm tra input
Business-Service  → chứa toàn bộ thuật toán
Data-Service      → CRUD cho mọi bảng
~~~

Mỗi chức năng đặt hàng hoặc thanh toán có thể phải đi qua cả ba “dịch vụ”, trong khi quy tắc nghiệp vụ và dữ liệu thực chất không thuộc về một service có mục tiêu rõ. Cấu trúc này là **phân tầng kỹ thuật qua mạng**, chưa phải decomposition theo năng lực nghiệp vụ.

Cách nhìn theo capability:

~~~text
Catalog     → mô tả sản phẩm, thông tin hiển thị
Order       → vòng đời đơn hàng, trạng thái đặt hàng
Inventory   → tồn kho khả dụng, giữ hàng, giải phóng giữ hàng
Payment     → yêu cầu thanh toán, trạng thái giao dịch, đối soát
Promotion   → điều kiện và chính sách áp dụng khuyến mãi
~~~

Không có nghĩa năm mục trên **bắt buộc** trở thành năm microservice. Đây là những ứng viên bounded context để thảo luận. Quy mô, quy tắc, invariant, tổ chức nhóm và tần suất thay đổi quyết định nên giữ các context trong một deployable hay tách độc lập.

### 3.2. Bounded context xác định ý nghĩa, service là một cách triển khai

Trong Domain-Driven Design, **bounded context** đặt giới hạn cho một mô hình/ngôn ngữ nghiệp vụ nhất quán. Cùng một từ có thể mang ý nghĩa khác nhau trong các context:

- Trong **Order**, “đơn đã xác nhận” nghĩa là điều kiện đặt hàng đã hoàn thành theo chính sách bán hàng.
- Trong **Payment**, “thanh toán thành công” là kết quả của một giao dịch tài chính.
- Trong **Inventory**, “hàng đã giữ” là một reservation còn hiệu lực, không nhất thiết đồng nghĩa hàng đã xuất kho.

Nếu mọi service dùng chung một enum Status hoặc một “CustomerModel” tổng quát cho tất cả bối cảnh, việc sửa khái niệm trong một miền có thể làm vỡ các miền khác. Sự phụ thuộc này là **semantic coupling**, ngay cả khi code chạy trong container riêng.

Một bounded context có thể triển khai bằng **một module**, **một service**, hoặc trong trường hợp có lý do rõ ràng, **nhiều service liên quan**. Không có ánh xạ cứng “một bounded context = một deployment unit” cho mọi hệ thống. Điều cần giữ là chủ sở hữu mô hình, invariant và hợp đồng tích hợp.

### 3.3. Aggregate và invariant giúp tìm ranh giới đúng

**Invariant** là quy tắc bắt buộc phải đúng. Ví dụ Inventory không cho giữ nhiều hơn số hàng khả dụng theo chính sách, Payment không ghi nhận hai lần một logical charge, Order không chuyển trạng thái từ CANCELLED về PENDING tùy tiện.

Nếu một invariant cần **atomic transaction và kiểm tra nhất quán ngay**, hãy cân nhắc giữ quy tắc và dữ liệu cần thiết trong **một ownership boundary**. Phân tán cùng invariant sang nhiều service có thể ép hệ thống dùng distributed transaction hoặc bù trừ phức tạp cho mọi yêu cầu.

Vì vậy, trước khi tách một service, hãy hỏi:

- Quy tắc nào phải nhất quán **ngay trong một transaction**?
- Dữ liệu cần để kiểm tra quy tắc do thành phần nào sở hữu?
- Nếu một service khác chậm/mất kết nối, ranh giới này có còn thực thi được quy tắc cốt lõi của mình không?
- Những quyết định nào thực sự có thể hoàn thành cục bộ, và quyết định nào cần quy trình phối hợp?
- Nếu cần phối hợp, có cho phép trạng thái trung gian và bù trừ không?

**Tự chủ nghiệp vụ không có nghĩa không có workflow liên miền.** Nó có nghĩa các bước trong workflow vẫn được thực hiện bởi đúng chủ sở hữu, qua contract thay vì thông qua truy cập dữ liệu nội bộ.

## 4. Quyền sở hữu dữ liệu không giống sở hữu máy chủ cơ sở dữ liệu

Câu “mỗi microservice phải có database riêng” dễ khiến người học nhầm **data ownership** với **database-server isolation**.

### 4.1. Data ownership là một ranh giới logic và quyền ghi

Inventory sở hữu các thao tác ReserveStock, ReleaseReservation và AdjustStock. Không service nào khác được tự cập nhật trực tiếp bảng reservation hoặc stock rồi tự tuyên bố nghiệp vụ thành công. Mọi thay đổi trạng thái có ý nghĩa phải đi qua API, command hoặc cơ chế tích hợp có hợp đồng của Inventory.

Điều này không bắt buộc mỗi service phải dùng một **máy chủ PostgreSQL riêng** trong mọi môi trường. Một hạ tầng database chung có thể lưu nhiều schema tách biệt với quyền truy cập và ownership độc lập. Tuy nhiên, cùng instance vẫn tạo **operational coupling**: nâng cấp instance, sự cố storage, pool connection và quota tài nguyên có thể ảnh hưởng đồng thời nhiều service.

Tách thành database instance riêng cải thiện một số mặt cô lập tài nguyên và vận hành, nhưng **không tự sửa** việc nhiều service đọc/ghi chung schema hoặc sao chép cùng quy tắc nghiệp vụ.

### 4.2. Bốn mô hình cần phân biệt

| Mô hình | Tự chủ dữ liệu | Rủi ro hạ tầng | Nhận xét |
|---|---|---|---|
| Mọi service đọc/ghi chung một nhóm bảng không có chủ sở hữu | Thấp | Phụ thuộc chung cao | Schema và logic chồng lấn; dễ thành distributed monolith |
| Mỗi service sở hữu schema/tables riêng trong cùng DB instance, ACL chặn ghi chéo | Khá cao nếu contract và ownership được thực thi | Chia sẻ instance/availability | Phù hợp một số giai đoạn; cần quản lý resource contention |
| Mỗi service dùng database instance riêng, tích hợp qua API/event | Cao nếu nghiệp vụ phân ranh đúng | Mức cô lập tài nguyên tốt hơn | Chi phí triển khai, migration và quản trị tăng |
| Mỗi service có DB riêng nhưng vẫn copy dữ liệu và cập nhật quy tắc chéo thủ công | Có nguy cơ thấp | Hạ tầng tách biệt | Vẫn coupling về semantic/schema và đồng bộ dữ liệu |

**Nguồn sự thật (source of truth)** quan trọng hơn vị trí vật lý của database. Một read model tại Order có thể sao chép một số thông tin tồn kho để phục vụ hiển thị, nhưng nguồn sự thật về lượng có thể giữ hàng vẫn thuộc Inventory. Khi dữ liệu sao chép chậm, giao diện phải có semantics phù hợp, không coi view là quyền được ghi trở lại.

### 4.3. Database per service không có nghĩa “không được chia sẻ dữ liệu”

Các miền nghiệp vụ cần chia sẻ **sự kiện và sự thật có chủ sở hữu**. Ví dụ Inventory công bố StockReserved hoặc ReservationExpired; Order cập nhật trạng thái đơn từ event đã thỏa thuận. Hợp đồng event phải thể hiện danh tính, phiên bản, ý nghĩa và điều kiện phát.

Không nên cho Order đọc thẳng bảng của Inventory chỉ để tiết kiệm một lần gọi API nếu việc đọc đó khiến Order biết cấu trúc nội bộ và phụ thuộc vào migration schema. Với truy vấn liên miền phức tạp, cân nhắc **API composition**, projection/read model hoặc giải pháp báo cáo được thiết kế có chủ đích.

## 5. Quyền thay đổi độc lập phụ thuộc vào hợp đồng, không chỉ vào pipeline

Giả sử Inventory có artifact riêng và một nút Deploy riêng trong CI/CD. Ngày mai nhóm Inventory đổi chính sách giữ hàng từ “giữ ngay” sang “giữ trong 15 phút và tự hết hạn”.

Nếu Order phải sửa SQL truy vấn bảng reservation, thay enum dùng chung, đổi logic hết hạn và đồng thời deploy để tránh lỗi, thì khả năng deploy tách biệt chỉ là **bề mặt kỹ thuật**. Hai service chưa tự chủ về mô hình và contract.

Một hợp đồng dịch vụ tốt cần làm rõ:

- **Ai chịu trách nhiệm:** Tên operation diễn đạt hành vi nghiệp vụ, ví dụ ReserveInventory thay vì UpdateInventoryTable.
- **Tiền điều kiện:** Thao tác có thể bị từ chối khi hết hàng, mã đơn không hợp lệ hoặc quá giới hạn.
- **Kết quả và trạng thái trung gian:** Accepted, Reserved, Rejected, Expired; cách kiểm tra operation chưa rõ kết quả.
- **Tính lặp an toàn:** Idempotency key và semantic của việc gửi lại command/event.
- **Tương thích:** Quy tắc phát triển schema/API (thêm trường tùy chọn, không tùy tiện đổi nghĩa trường cũ, giai đoạn deprecation).
- **Kỳ vọng vận hành:** Latency, availability, timeout, retry và degradation phù hợp với nghiệp vụ.
- **Thay đổi quyền truy cập:** Consumer không có quyền gọi mọi API nội bộ chỉ vì có network connection.

### Ví dụ contract

~~~http
POST /inventory/reservations
Idempotency-Key: order-O-101-reserve-v1
Content-Type: application/json

{
  "orderId": "O-101",
  "items": [{"sku": "SKU-8", "quantity": 2}]
}
~~~

Kết quả minh họa:

~~~json
{
  "reservationId": "RES-501",
  "status": "RESERVED",
  "expiresAt": "2026-11-11T15:30:00Z"
}
~~~

Order chỉ cần biết hợp đồng về việc giữ hàng, mã reservation, trạng thái và hạn hiệu lực. Inventory có thể thay đổi thuật toán phân bổ, bố trí kho hay schema nội bộ mà không làm Order sửa theo, miễn contract và semantics còn tương thích.

**Lưu ý:** Đây là ví dụ hợp đồng minh họa, không phải tiêu chuẩn bắt buộc. Trong một luồng khác, ReserveInventory có thể được xử lý bất đồng bộ và trả PENDING/ACCEPTED trước khi phát StockReserved. Lựa chọn tùy yêu cầu nghiệp vụ, SLO và điều kiện nhất quán.

### Consumer-driven contract test giúp giữ quyền tự chủ

Tự chủ được bảo vệ bằng **bằng chứng tương thích**, không chỉ bằng lời cam kết. Producer nên kiểm tra rằng phiên bản mới vẫn đáp ứng những giả định hợp lệ của consumer. Consumer phải tránh phụ thuộc vào trường/chi tiết không thuộc contract.

Khi một service có thể:

1. Build phiên bản mới;
2. Chạy unit/integration/contract tests;
3. Triển khai canary hoặc rolling update;
4. Phục vụ các phiên bản consumer còn được hỗ trợ;
5. Rollback nếu vi phạm SLO;

...thì đó là bằng chứng mạnh hơn của **independent delivery** so với việc service chỉ nằm trong repo riêng.

## 6. Ví dụ xuyên suốt: Order, Inventory và Payment

Xét hệ thống bán hàng có ba năng lực:

| Service/Context | Quyết định nghiệp vụ thuộc quyền | Dữ liệu nguồn sự thật | Hợp đồng tiêu biểu |
|---|---|---|---|
| Order | Tạo/hủy/xác nhận đơn, quy trình đặt hàng | Order state, order line, saga state | CreateOrder, GetOrder, OrderConfirmed |
| Inventory | Khả năng bán, giữ/giải phóng hàng, hết hạn reservation | Stock, reservation | ReserveInventory, ReleaseInventory, StockReserved |
| Payment | Khởi tạo, xác nhận, đối soát và hoàn giao dịch thanh toán | Payment intent, transaction, refund | AuthorizePayment, GetPaymentStatus, PaymentAuthorized |

Cả ba liên quan đến **một đơn hàng**, nhưng không phải cùng sở hữu **một mô hình Order khổng lồ**. Mỗi context có thể sử dụng một định danh orderId làm liên kết mà không cần cùng ghi bảng orders.

### 6.1. Một thiết kế lệch ranh giới

~~~mermaid
flowchart LR
    O["Order Service"] -->|SQL cập nhật tồn kho| DB[("Shared DB: order + stock + payment")]
    I["Inventory Service"] -->|SQL trực tiếp| DB
    P["Payment Service"] -->|SQL trực tiếp| DB
    O -->|Gọi Payment sau khi đọc bảng của Payment| P
    I -. "Model chung, deploy đồng thời" .-> P
~~~

Trong thiết kế này:

- Order tự sửa stock, Inventory không còn là chủ thể thực thi quy tắc giữ hàng.
- Payment phụ thuộc schema Orders và Order phụ thuộc schema Payments.
- Mọi service đều có container riêng nhưng cùng sở hữu bảng, khó xác định nhóm nào chịu trách nhiệm khi dữ liệu sai.
- Migration schema có thể yêu cầu release đồng thời.
- Khi database chung trục trặc, nhiều service cùng bị ảnh hưởng bất chấp container tách biệt.

**Vấn đề chính là ranh giới nghiệp vụ và dữ liệu**, còn sự phụ thuộc hạ tầng chung làm tăng phạm vi ảnh hưởng của sự cố.

### 6.2. Thiết kế theo ownership và contract

~~~mermaid
flowchart TB
    U["Client"] --> O["Order\nSở hữu trạng thái đơn"]
    O -->|ReserveInventory| I["Inventory\nSở hữu reservation"]
    O -->|AuthorizePayment| P["Payment\nSở hữu giao dịch"]
    I -->|StockReserved / StockRejected| O
    P -->|PaymentAuthorized / PaymentRejected| O
    O --- OD[("Order-owned data")]
    I --- ID[("Inventory-owned data")]
    P --- PD[("Payment-owned data")]
    subgraph SharedPlatform["Nền tảng vận hành dùng chung"]
      OBS["Logs / Metrics / Traces"]
      DEP["CI/CD / Broker / Ingress"]
    end
    O -.-> OBS
    I -.-> OBS
    P -.-> OBS
~~~

Trong phương án này, dữ liệu có chủ sở hữu và tương tác đi qua contract. Nền tảng quan sát, deployment tooling hoặc broker có thể dùng chung. Đó là **chia sẻ năng lực hạ tầng**, không phải cho các service tùy ý sửa dữ liệu nghiệp vụ của nhau.

Order vẫn phải **phối hợp quy trình**: tạo đơn, yêu cầu giữ hàng, thực hiện thanh toán, xác nhận hoặc hủy. Một saga orchestrated do Order làm chủ có thể hợp lý nếu quy trình là trách nhiệm của Order. Điều cần tránh là một “central business service” áp đặt toàn bộ quy tắc nội bộ cho mọi domain.

### 6.3. Thay đổi chính sách tồn kho: phép thử tự chủ

Yêu cầu mới: “Reservation tự hết hạn sau một khoảng thời gian cấu hình được.”

**Thiết kế lệch ranh giới:** Nhóm Order sửa timer trong Order, nhóm Inventory sửa bảng reservation, nhóm Payment sửa điều kiện thanh toán; phải triển khai cùng một ngày. Thay đổi domain Inventory gây hiệu ứng dây chuyền.

**Thiết kế có quyền sở hữu:**

1. Inventory thay đổi thuật toán tính hạn giữ hàng và xử lý Expired.
2. Inventory vẫn công bố contract với reservationId, trạng thái, expiresAt và event tương thích.
3. Order chỉ xử lý sự kiện ReservationExpired theo luồng đơn đang PENDING, nếu nghiệp vụ đặt hàng yêu cầu.
4. Payment không cần biết cấu trúc reservation hay quy tắc hết hạn, trừ khi có một chính sách liên miền cụ thể cần phối hợp.
5. Nhóm Inventory có thể phát hành logic mới khi consumer tương thích; thay đổi hợp đồng liên miền phải có kế hoạch versioning.

Tính tự chủ xuất hiện ở **quyền thay đổi quy tắc giữ hàng** và **số nơi phải sửa**. Khả năng deploy riêng hỗ trợ phát hành thay đổi đó, nhưng không tạo ra ownership nếu ranh giới ban đầu sai.

### 6.4. Thay đổi liên miền là điều bình thường

Yêu cầu mới: “Chỉ xác nhận Order khi Payment thành công và Inventory còn reservation hợp lệ.”

Đây là **quy trình nhiều context**. Order phải phối hợp kết quả từ hai service; nghiệp vụ có thể yêu cầu saga, trạng thái PENDING và hành động bù trừ. Việc cần phối hợp **không chứng minh tách service sai**. Câu hỏi là liệu ranh giới có rõ ai chịu trách nhiệm từng quyết định, và phối hợp có diễn ra qua hợp đồng ổn định hay không.

Một thay đổi thực sự liên miền có thể đòi hỏi nhiều nhóm thảo luận và phát hành các thay đổi có thứ tự. **Tự chủ không xóa bỏ tính phụ thuộc nghiệp vụ thật**; nó giúp các thay đổi cục bộ không bị biến thành phụ thuộc chéo vô cớ.

## 7. Độc lập về hạ tầng có nhiều chiều, không chỉ “có container riêng”

### 7.1. Build và source ownership

Dùng repository riêng không tự tạo business autonomy; dùng monorepo cũng không ngăn service có artifact, ownership và pipeline độc lập. Điều quan trọng là:

- Có thể xác định những code owner và những thay đổi ảnh hưởng đến service nào.
- Test và build một service không yêu cầu thay đổi code không liên quan.
- Thư viện dùng chung có versioning/compatibility rõ; không để mọi service bắt buộc nâng cùng một model/domain library cho thay đổi cục bộ.
- Artifact có định danh version, nguồn build và lịch sử phát hành có thể truy vết.

Một **shared utility library** chứa logging hay primitive ổn định thường khác với **shared domain model library** chứa enum trạng thái hoặc business rules liên tục thay đổi. Loại thứ hai dễ tạo coupling semantic và release lockstep.

### 7.2. Deployment independence

Một service có thể triển khai độc lập nếu phiên bản mới hoạt động với các phiên bản dependency còn được hỗ trợ mà không đòi deploy đồng loạt. Điều đó thường cần:

- Contract backward/forward compatibility theo phạm vi đã định.
- Database migration theo hướng **expand → migrate → contract**, tránh drop/rename trường ngay khi consumer còn dùng.
- Có health checks và deployment strategy phù hợp (rolling/canary/blue-green nếu cần).
- Có khả năng rollback hoặc roll forward khi phát hiện lỗi.
- Mọi dependency quan trọng đều có version và chính sách cập nhật.

**Có pipeline riêng** là cần thiết trong nhiều trường hợp nhưng chưa đủ. Nếu mỗi release Inventory phải đợi Payment cùng đổi schema hoặc cập nhật thư viện chung, thì sự độc lập phát hành thực tế vẫn thấp.

### 7.3. Runtime và resource independence

Tách process/container cho phép giới hạn CPU, memory, số kết nối và replica riêng. Nhưng các điểm chung như cluster, node, VPC, database instance, broker hoặc control plane vẫn tạo phụ thuộc vận hành.

Ví dụ:

- Inventory có 10 replica, Payment có 2 replica: có thể scale độc lập.
- Cả hai cùng chạy trên một cluster: sự cố cluster vẫn có thể ảnh hưởng đồng thời.
- Cả hai có DB riêng nhưng chung một network gateway: gateway là shared dependency.
- Cả hai dùng cùng message broker: broker outage có thể cản trở luồng liên miền.

Mục tiêu hợp lý là **phù hợp mức độ cô lập với yêu cầu SLO và blast radius**, không phải nhân bản mọi hạ tầng đến mức chi phí vượt lợi ích.

### 7.4. Công cụ nền tảng dùng chung có thể tăng tự chủ

Một platform team cung cấp CI templates, secret management, distributed tracing, service discovery, policy-as-code và deployment “golden path” có thể **giảm gánh nặng cho các nhóm domain**. Tính tự chủ nghiệp vụ vẫn được bảo vệ nếu nhóm domain có quyền đưa ra quyết định trong giới hạn hợp đồng và nền tảng không buộc release tất cả service cùng lúc.

Phân biệt:

- **Tiêu chuẩn chung:** Mọi service phải công bố metrics, dùng cơ chế identity phù hợp và vượt kiểm thử bảo mật. Đây là governance cần thiết.
- **Quyền quyết định miền:** Inventory chọn chính sách giữ hàng, mô hình reservation và lộ trình nâng cấp hợp đồng của nó.
- **Phụ thuộc phê duyệt:** Nếu mọi thay đổi cục bộ đều phải qua hội đồng trung tâm hoặc nhóm hạ tầng chỉnh tay, năng lực giao hàng độc lập có thể bị giới hạn dù code được chia tốt.

Tự chủ là một **mô hình trách nhiệm**, không phải lý do bỏ qua các tiêu chuẩn bảo mật, tuân thủ hoặc khả năng phục hồi.

## 8. Những dạng coupling cần kiểm tra trước khi tách Microservices

“Coupling” không chỉ là import một class hoặc gọi một API. Dưới đây là các dạng thường làm tự chủ nghiệp vụ thấp dù hạ tầng đã tách.

| Loại coupling | Dấu hiệu | Hệ quả | Hướng xử lý |
|---|---|---|---|
| **Data coupling** | Service A đọc/ghi thẳng bảng nội bộ của B | Schema migration và invariant phụ thuộc chéo | Chủ sở hữu dữ liệu, API/event/read model |
| **Semantic coupling** | Cùng một model Status/Order được tái sử dụng cho nhiều context | Một quy tắc đổi làm nhiều bên hiểu sai | Tách mô hình theo bounded context, mapping rõ |
| **Temporal coupling** | Mọi operation đòi B,C,D phản hồi tức thời cùng lúc | Availability và latency phụ thuộc dây chuyền | Xác định nhu cầu sync thật, cân nhắc async |
| **Change coupling** | Một user story thường sửa 4–5 service cùng lúc | Chi phí phối hợp và regression cao | Điều chỉnh boundary, làm ổn định contract |
| **Deployment coupling** | Bắt buộc phát hành tất cả service cùng phiên bản | Mất independent delivery | Versioning, migration tương thích, contract test |
| **Organizational coupling** | Không rõ ai quyết định hoặc on-call, liên tục qua nhiều nhóm phê duyệt | Quyết định chậm và lỗi ownership | Giao trách nhiệm domain rõ, quy trình phối hợp |
| **Runtime coupling** | Dùng chung một process/tài nguyên giới hạn hoặc synchronous chain dài | Sự cố lan rộng | Isolation, timeout, bulkhead, capacity planning |
| **Build coupling** | Mọi thay đổi library kích hoạt nâng version toàn hệ thống | Release bị khóa và dễ regression | Tách domain library, versioning, semantic contracts |
| **Operational coupling** | Một team duy nhất phải deploy/rollback mọi service bằng thao tác thủ công | Nghẽn vận hành | Self-service platform và runbooks phù hợp |

Không phải coupling nào cũng loại bỏ được. Một đơn hàng thật sự liên quan đến thanh toán và giữ hàng; contract giữa Order với Inventory là **phụ thuộc nghiệp vụ hợp lệ**. Mục tiêu là loại bỏ coupling **vô tình hoặc không cần thiết**, giữ đúng phụ thuộc bắt buộc, và làm rõ cách xử lý lỗi.

### Phép thử “cùng thay đổi” (change-together test)

Chọn 5–10 thay đổi nghiệp vụ gần đây hoặc mô phỏng:

1. Đổi cách tính hạn giữ hàng.
2. Thêm trạng thái thanh toán cần đối soát.
3. Thay điều kiện đủ để xác nhận đơn.
4. Thay thuật toán xếp ưu tiên kho.
5. Bổ sung hình thức khuyến mãi.

Với mỗi yêu cầu, ghi lại **service/module nào phải thay đổi code**, **hợp đồng nào thay đổi**, **database nào cần migration**, **service nào phải deploy đồng thời** và **nhóm nào cần phê duyệt**.

Nếu phần lớn các thay đổi **cục bộ theo domain** vẫn luôn sửa cùng một cụm service, có thể boundary đang bị cắt quá nhỏ hoặc không phù hợp. Không nên ngay lập tức gộp/tách theo số lần gọi; cần xét lý do nghiệp vụ, tính nhất quán, performance và quyền ownership.

## 9. Ranh giới dịch vụ tốt được chứng minh bằng một loạt câu hỏi

Trước khi coi một thành phần là microservice độc lập, hãy trả lời bảy nhóm câu hỏi.

### 9.1. Trách nhiệm nghiệp vụ

- Nếu hỏi “service này chịu trách nhiệm kết quả nào?”, nhóm có thể trả lời bằng ngôn ngữ nghiệp vụ không?
- Có phần quy tắc cốt lõi nào bị đặt ở service khác chỉ vì thuận tiện code?
- Có hai service đang cùng có quyền sửa một quyết định nghiệp vụ quan trọng không?

Một service chỉ mang tên BusinessService nhưng chứa tất cả logic cho nhiều domain không có nghĩa nó là một bounded context.

### 9.2. Quyền sở hữu invariant và dữ liệu

- Đâu là nguồn sự thật? Ai có quyền ghi?
- Dữ liệu được sao chép có mục đích rõ và độ trễ được chấp nhận không?
- Một transaction cục bộ có giữ được invariant cốt lõi không, hay mọi operation đều cần distributed lock/transaction?

### 9.3. Hợp đồng tích hợp

- API hoặc event có mô tả **hành vi nghiệp vụ**, hay chỉ lộ cấu trúc bảng nội bộ?
- Consumer có biết chi tiết schema hoặc thuật toán của producer không?
- Thay đổi tương thích có thể được kiểm tra tự động không?

### 9.4. Quyền phát hành

- Có thể triển khai phiên bản mới của service khi các service liên quan vẫn chạy phiên bản cũ được hỗ trợ không?
- Có cần migration đồng bộ hoặc bật tắt feature toàn cục cho một sửa đổi nhỏ không?
- Nếu rollback service này, cần rollback bao nhiêu service khác?

### 9.5. Khả năng chịu lỗi

- Nếu dependency khác mất kết nối, service này có còn thực hiện được chức năng cục bộ nào?
- Luồng liên miền có timeout, retry, idempotency, trạng thái trung gian và cơ chế đối soát phù hợp không?
- Lỗi một service có buộc toàn hệ thống ngừng hay chỉ ảnh hưởng capability liên quan?

### 9.6. Ownership tổ chức

- Nhóm nào quyết định mô hình và chính sách nghiệp vụ?
- Nhóm nào trực on-call và chịu SLO của capability?
- Khi cần thay đổi liên miền, có hợp đồng, người liên hệ và quy trình rõ không?

### 9.7. Giá trị so với chi phí

- Độc lập deploy/scale có giải quyết một nhu cầu cụ thể không?
- Độ trễ, chi phí network, dữ liệu phân tán và vận hành mới tăng bao nhiêu?
- Một modular monolith với ranh giới rõ có đủ tốt ở giai đoạn hiện tại không?

Không cần tất cả câu trả lời đều hoàn hảo trước khi tạo service đầu tiên. Nhưng cần nhận diện **ràng buộc thật**, đặt ưu tiên và đo bằng bằng chứng sau khi thay đổi.

## 10. Tự chủ nghiệp vụ không có nghĩa “hoàn toàn không cần dịch vụ khác”

Một luồng nghiệp vụ như **đặt hàng** là một business process liên miền. Order cần thông tin Inventory, Payment và có thể Promotion. Việc các service phối hợp không mâu thuẫn với tự chủ nếu:

- Mỗi service tự ra quyết định đúng trong phạm vi mô hình và invariant của mình.
- Quy trình chung biểu diễn bằng hợp đồng rõ và trạng thái có thể quan sát.
- Service khác không phải đọc/ghi dữ liệu nội bộ hoặc sửa trực tiếp quy tắc nghiệp vụ của service chủ.
- Một thay đổi cục bộ có thể được phát hành với ít sự phối hợp nhất có thể.
- Khi có thay đổi liên miền thật, nhóm liên quan phối hợp qua versioning, migration và kế hoạch release minh bạch.

### Choreography và orchestration đều cần ranh giới trách nhiệm

**Choreography:** Service phản ứng với event do context khác công bố. Đơn giản với luồng nhỏ nhưng có thể khó nắm quy trình toàn cục nếu mọi quyết định bị phân tán.

**Orchestration:** Một thành phần điều phối quy trình liên miền, ví dụ Order chịu trách nhiệm saga tạo đơn. Cách này làm flow rõ nhưng phải tránh biến orchestrator thành chủ sở hữu quy tắc nội bộ của Inventory/Payment.

**Không chọn choreography chỉ vì muốn “tự chủ tối đa”.** Các luồng xử lý cần ngữ nghĩa rõ về trạng thái, bù trừ, đối soát và chủ sở hữu quy trình; mô hình phù hợp phụ thuộc yêu cầu nghiệp vụ.

### Hợp đồng không loại bỏ hoàn toàn sự phụ thuộc thời gian chạy

Nếu Order bắt buộc gọi Payment đồng bộ để trả kết quả trong 500 ms, hai service vẫn phụ thuộc availability và latency của nhau. Đó là **temporal coupling**. Không nên tuyên bố độc lập hoàn toàn chỉ vì contract tốt. Có thể phải thay đổi flow sang PENDING/async, cache/replica hoặc graceful degradation nếu trải nghiệm và tính nhất quán cho phép.

## 11. Ranh giới nhóm phát triển và quyền quyết định

Ranh giới service liên quan tới **cách tổ chức đội nhóm**, nhưng không có quy tắc cứng “một team = một service”. Một nhóm có thể sở hữu vài service liên quan; một bounded context lớn có thể cần chia trách nhiệm nội bộ rõ hơn. Điều quan trọng là tránh ownership phân tán tới mức một thay đổi nhỏ đi qua nhiều nhóm vô cớ.

### Ba dạng trách nhiệm thường gặp

**Nhóm theo domain/capability:** Quyết định chính sách, mã nguồn, hợp đồng, dữ liệu và chất lượng dịch vụ trong phạm vi năng lực nghiệp vụ.

**Nhóm nền tảng:** Xây các năng lực dùng chung như pipeline, observability, identity, secret management và self-service deployment để nhóm domain không phải xây lặp từ đầu.

**Nhóm quản trị kiến trúc/bảo mật:** Thiết lập giới hạn và quy tắc liên hệ thống như tiêu chuẩn API, security, compliance và độ tin cậy; việc áp dụng nên được tự động hóa khi có thể.

Một cấu trúc tốt thường khiến team domain **có thể tự phát hành trong khuôn khổ chính sách**. Nếu mọi lần sửa timeout hoặc đổi quy tắc Inventory đều phải nhờ team trung tâm sửa service và deploy thủ công, độc lập thực tế thấp.

**Cẩn thận với khẩu hiệu “You build it, you run it”:** Quyền sở hữu vận hành cần đi cùng quyền truy cập, công cụ, năng lực on-call và ngân sách. Giao trách nhiệm mà không có quyền hoặc khả năng thực hiện không tạo tự chủ.

## 12. Khi nào tách hạ tầng riêng đem lại giá trị?

Tách service/runtime thường hợp lý hơn khi có một hoặc nhiều nhu cầu sau:

1. **Scale khác nhau:** Catalog cần chịu tải đọc cao; Payment có lượng giao dịch ít hơn nhưng yêu cầu kiểm soát chặt.
2. **Phát hành khác nhịp:** Inventory thay đổi thường xuyên, Payment cần chu kỳ kiểm thử và tuân thủ nghiêm ngặt.
3. **Cô lập sự cố:** Lỗi xử lý ảnh hoặc công việc nặng không được làm nghẽn thanh toán.
4. **Đa dạng nhu cầu kỹ thuật thật:** Một workload xử lý dữ liệu cần mô hình tài nguyên hay thời gian chạy khác biệt.
5. **Quyền hạn và dữ liệu:** Một capability có yêu cầu truy cập, mã hóa hoặc phạm vi vận hành đặc biệt.
6. **Quy mô tổ chức:** Nhiều team có ownership ổn định và cần giảm phụ thuộc release.
7. **Đo lường được lợi ích:** Lead time, phạm vi lỗi, throughput hoặc chi phí thay đổi được cải thiện đủ để bù chi phí phân tán.

Ngược lại, giữ modular monolith có thể hợp lý khi domain còn biến động mạnh, nhóm nhỏ, nhu cầu scale chưa khác biệt, số lượng thay đổi liên miền nhiều hoặc tổ chức chưa đủ khả năng quan sát/triển khai hệ thống phân tán.

### Tách hạ tầng quá sớm gây ra điều gì?

- Nhiều network call cho một giao dịch vốn đơn giản trong một process.
- Dữ liệu trước kia transaction cục bộ giờ phải dùng saga/outbox/reconciliation.
- Nhiều pipeline, registry, config, secrets và incident phải vận hành.
- Thời gian debug tăng vì cần tracing qua nhiều service.
- Các nhóm buộc phối hợp nhiều hơn do ranh giới chưa ổn định.
- Chi phí mở rộng hệ thống không tương xứng với tính năng thực có.

Chi phí này là lý do việc **xác định boundary nghiệp vụ trước** thường có ích, kể cả khi quyết định cuối cùng là chưa tách runtime.

## 13. Cách tiến hóa từ modular monolith sang Microservices

Không cần phải tách toàn bộ hệ thống một lần. Một lộ trình có kiểm soát:

### Giai đoạn 1 — Làm rõ ranh giới ngay trong mã nguồn

Tách module Order, Inventory, Payment theo trách nhiệm. Dùng interface/port, package boundary và quyền truy cập dữ liệu rõ. Không cho module A gọi repository nội bộ của module B. Kiểm thử invariant cục bộ và phụ thuộc module.

**Bằng chứng cần có:** Sửa chính sách Inventory không phải sửa logic nội bộ của Order, trừ contract tích hợp đã định.

### Giai đoạn 2 — Đo phụ thuộc thực tế

Quan sát lịch sử thay đổi, thống kê modules thường sửa cùng nhau, transaction xuyên module, call graph, latency và nhu cầu release. Chọn capability có boundary tương đối ổn định và lý do tách rõ.

**Bằng chứng cần có:** Có yêu cầu cụ thể như scale/release/isolate độc lập; đã chỉ ra chi phí vận hành tăng.

### Giai đoạn 3 — Thiết lập contract và ownership dữ liệu

Định nghĩa operation nghiệp vụ và dữ liệu cần chia sẻ, chuyển dần truy cập bảng trực tiếp qua API/event hoặc read model. Bổ sung versioning, contract tests và cơ chế bảo đảm dữ liệu đang chuyển đổi.

**Bằng chứng cần có:** Không còn producer/consumer phụ thuộc bảng nội bộ ngoài những ngoại lệ chuyển tiếp có thời hạn.

### Giai đoạn 4 — Tách một capability ra runtime riêng

Có thể dùng **strangler pattern** hoặc điểm điều hướng API để chuyển một nhóm use case sang service mới. Tách dần nguồn ghi dữ liệu theo quyền sở hữu; áp dụng migration tương thích, quan sát và rollback. Nếu dùng CDC hay đồng bộ chuyển tiếp, phải xác định ai là nguồn sự thật trong từng giai đoạn, tránh hai bên cùng ghi vô kiểm soát.

**Bằng chứng cần có:** Service mới xử lý được use case và lỗi quan trọng; hệ thống cũ và mới không sinh hai nguồn sự thật mâu thuẫn.

### Giai đoạn 5 — Kiểm chứng tính độc lập bằng thay đổi thật

Thử đổi quy tắc nghiệp vụ cục bộ rồi deploy riêng; đo số service/code owners phải đổi, số consumer bị ảnh hưởng, thời gian release và phạm vi sự cố. Nếu không cải thiện, xem lại boundary hoặc cách tích hợp.

**Bằng chứng cần có:** Có ít nhất một thay đổi cục bộ được phát hành mà không cần release dây chuyền, và không làm giảm tính đúng đắn nghiệp vụ.

### Giai đoạn 6 — Điều chỉnh mức cách ly hạ tầng

Sau khi có số liệu, quyết định dùng chung hay tách riêng database instance, broker, cluster, deployment environment hoặc capacity. Không mặc định phải chia hạ tầng theo đúng mọi ranh giới domain; tính toán SLO, blast radius, security và cost.

**Bằng chứng cần có:** Quyết định cô lập tài nguyên dựa trên yêu cầu/metric, không dựa trên số lượng service.

## 14. Đánh giá ranh giới bằng số đo

Tính tự chủ là khái niệm kiến trúc, nhưng có thể kiểm chứng qua quan sát. Không nên chỉ đếm số repository, microservice hoặc container.

| Chỉ số/tín hiệu | Đo điều gì? | Cách diễn giải thận trọng |
|---|---|---|
| Số service phải sửa trong một thay đổi **cục bộ** | Change coupling | Nếu thường phải sửa nhiều service, boundary hoặc contract có thể chưa tốt |
| Số deployment bắt buộc diễn ra cùng nhau | Deployment coupling | Càng nhiều release lockstep, độc lập giao hàng càng thấp |
| Tần suất schema/API breaking changes | Sự ổn định hợp đồng | Breaking changes cao có thể biểu hiện mô hình chung chưa được phân ranh |
| Lead time từ quyết định đến production | Khả năng thay đổi | Đo cùng quy mô/độ rủi ro thay đổi, tránh so sánh khập khiễng |
| Cross-team wait time | Tổ chức có tự chủ thực không | Chờ phê duyệt/lịch deploy chung có thể là bottleneck |
| Số tác vụ phải truy cập data owner khác trực tiếp | Data ownership | Phụ thuộc query chéo schema là cảnh báo |
| Mức phân tách tải CPU, replica, queue | Quyền scale độc lập | Có giá trị khi các workload thực sự khác nhau |
| SLO, thời gian phục hồi và phạm vi ảnh hưởng sự cố | Failure isolation | Shared infrastructure vẫn có thể tạo common failure |
| Cost per transaction và vận hành | Chi phí của sự phân tán | Tách service mà không tăng giá trị có thể không hiệu quả |

### Đánh giá bằng kịch bản, không dùng một điểm số duy nhất

Với từng service, lập ba kịch bản:

**Thay đổi cục bộ:** Điều chỉnh chính sách nội bộ mà contract không đổi. Có sửa/deploy service nào khác không?

**Thay đổi hợp đồng:** Thêm dữ liệu hoặc trạng thái mới. Có kế hoạch tương thích để producer và consumer tiến hóa không đồng bộ không?

**Sự cố runtime:** Service bị chậm, restart hoặc database phụ thuộc lỗi. Hệ thống có phân biệt capability nào bị ảnh hưởng, có cơ chế suy giảm phù hợp và có công cụ điều tra không?

Ba kịch bản thể hiện ba mặt khác nhau của tự chủ: **domain change**, **evolution** và **operational isolation**.

## 15. Một bộ tình huống quyết định kiến trúc

### Tình huống A — Hệ thống nhỏ, một team, nhiều yêu cầu thay đổi cùng nhau

Nhóm năm người vận hành một sản phẩm mới. Mô hình nghiệp vụ và ranh giới thường xuyên thay đổi; có nhiều transaction cần nhất quán ngay. Tách 12 microservices sẽ tăng coordination và vận hành. Có thể bắt đầu bằng modular monolith được chia domain tốt, đặt interface và ownership để dễ tách về sau.

**Quyết định:** Ưu tiên business boundary trong code, chưa cần hạ tầng phân tán.  
**Dữ liệu cần theo dõi:** Modules sửa cùng nhau, bottleneck hiệu năng, tần suất phát hành, cơ chế ownership.

### Tình huống B — Inventory có tải và tốc độ thay đổi khác phần còn lại

Inventory xử lý rất nhiều reservation/stock updates; nhóm riêng chịu trách nhiệm tồn kho. Contract khá ổn định, dữ liệu chủ rõ. Việc tách runtime và scale riêng giúp cô lập tài nguyên, cải thiện throughput và release.

**Quyết định:** Cân nhắc tách Inventory khi có test contract, idempotency và observability.  
**Dữ liệu cần theo dõi:** Throughput reservation, p95/p99 latency, failed reservations, cost, service availability.

### Tình huống C — Mọi service có container riêng nhưng dùng chung schema

Order, Payment và Inventory deploy độc lập về mặt nút bấm nhưng mọi thay đổi business flow phải cập nhật stored procedure và ORM model dùng chung. Schema migration khiến release lockstep.

**Quyết định:** Ưu tiên lập lại quyền sở hữu dữ liệu, tách hợp đồng và giảm phụ thuộc schema. Việc bổ sung cluster riêng chưa giải quyết gốc coupling.  
**Dữ liệu cần theo dõi:** Shared-table accesses, required joint releases, conflicts of ownership.

### Tình huống D — Có platform team cung cấp hạ tầng dùng chung

Nhiều service chạy chung cluster với centralized tracing, secret manager và deployment templates. Mỗi nhóm domain có pipeline, quyền phát hành, data owner và SLA/SLO riêng trong khuôn khổ governance.

**Quyết định:** Đây có thể là microservices có tự chủ nghiệp vụ cao, dù dùng chung nền tảng. Chỉ tách hạ tầng chuyên biệt khi có nhu cầu isolation/SLO/security.  
**Dữ liệu cần theo dõi:** Common-mode incidents, platform dependency bottlenecks, self-service deploy success rate.

### Tình huống E — Hai service luôn phải sửa và triển khai cùng nhau

Pricing và Discount tách riêng, nhưng mỗi thay đổi quy tắc khuyến mãi bắt buộc cập nhật cả hai, chia sẻ chung calculation state và không có quyết định cục bộ rõ ràng.

**Quyết định:** Kiểm tra xem đó có phải cùng một bounded context nên gộp lại hoặc cần thiết kế lại contract. Không mặc định rằng tăng thêm message/event sẽ làm hai miền độc lập.  
**Dữ liệu cần theo dõi:** Co-change frequency, business invariants, contract churn, operational overhead.

## 16. Những ngộ nhận thường gặp

**Ngộ nhận 1 — “Có container riêng nghĩa là một microservice tự chủ.”**  
Container cho cách ly tiến trình và cấu hình tài nguyên; boundary nghiệp vụ phải được kiểm chứng riêng.

**Ngộ nhận 2 — “Mỗi service cần một database server riêng.”**  
Điều quan trọng nhất là quyền sở hữu và kiểm soát dữ liệu. Mức tách biệt vật lý phụ thuộc nhu cầu bảo mật, vận hành, hiệu năng và chi phí.

**Ngộ nhận 3 — “Dùng monorepo thì không thể deploy độc lập.”**  
Monorepo có thể build và deploy từng service riêng nếu dependency, pipeline và hợp đồng được thiết kế phù hợp.

**Ngộ nhận 4 — “Service có repo riêng sẽ không còn coupling.”**  
Repo không ngăn semantic coupling, shared schema, synchronous call chain hay sự phụ thuộc release.

**Ngộ nhận 5 — “Một bounded context bắt buộc tương ứng đúng một process.”**  
Bounded context là ranh giới mô hình; deployable boundary là quyết định kỹ thuật có thể điều chỉnh theo tải, quy mô và vận hành.

**Ngộ nhận 6 — “Tự chủ tức là không cần thống nhất chuẩn.”**  
Service vẫn cần chuẩn bảo mật, hợp đồng tích hợp, logging, ownership và các quy định tổ chức. Nền tảng dùng chung còn có thể giúp tăng tự chủ.

**Ngộ nhận 7 — “Mỗi microservice phải dùng một công nghệ khác nhau.”**  
Polyglot persistence/stack là quyền lựa chọn khi có lợi ích, không phải tiêu chí thành công. Công nghệ không cần thiết khác nhau sẽ làm tăng chi phí bảo trì.

**Ngộ nhận 8 — “Nếu hai service vẫn phải gọi nhau thì không tự chủ.”**  
Nghiệp vụ liên miền đương nhiên cần phối hợp. Vấn đề là contract ổn định và quyền quyết định nội bộ, không phải số lượng kết nối bằng không.

**Ngộ nhận 9 — “Càng nhiều service càng scalable.”**  
Tăng số lượng service có thể tăng coordination, network cost và latency. Scale đúng dựa trên workload, boundary và giới hạn tài nguyên.

**Ngộ nhận 10 — “Chỉ cần tách deploy là đã thay đổi độc lập.”**  
Một service có thể triển khai riêng nhưng bắt buộc phối hợp thay đổi code/schema ở nhiều bên. Cần đo **independent change**, không chỉ **independent deployment**.

## 17. Bài thực hành: chấm bằng bằng chứng, không chỉ nhìn sơ đồ

**Đề bài:** Một hệ thống thương mại có Catalog, Order, Inventory và Payment. Hiện tại tất cả ở cùng một ứng dụng. Nhóm muốn tách Inventory ra microservice để có thể mở rộng khi số đơn tăng.

### Bước 1 — Ghi rõ capability

Viết danh sách cho Inventory gồm: đọc tồn kho khả dụng, giữ hàng, giải phóng hàng, hết hạn reservation, điều chỉnh stock sau kiểm kê. Đánh dấu invariant và dữ liệu cần để thực hiện các quyết định này.

**Đầu ra:** Một mô tả trách nhiệm Inventory đủ cụ thể, không cần nói đến database engine hoặc tên container.

### Bước 2 — Phát hiện phụ thuộc dữ liệu

Kiểm tra (trên mô hình giả định) xem Order có truy cập thẳng bảng inventory hoặc cập nhật stock không. Tìm nơi logic giữ hàng bị sao chép. Vẽ sơ đồ dữ liệu và quyền ghi hiện tại.

**Đầu ra:** Danh sách dependency nội bộ cần thay bằng contract.

### Bước 3 — Thiết kế contract

Định nghĩa ReserveInventory, ReleaseReservation, GetReservationStatus và kết quả tương ứng. Chọn sync/async theo trải nghiệm người dùng. Mô tả idempotency key, duplicate event, timeout sau commit và cách đối soát.

**Đầu ra:** Một API/event contract và bảng trường hợp thất bại.

### Bước 4 — Thiết kế ownership và vận hành

Xác định nhóm nào sở hữu business rules, DB/schema, API contract, SLO, deployment và runbook. Có thể dùng chung cluster, CI templates và tracing; mọi quyền ghi nghiệp vụ vẫn phải đi qua Inventory.

**Đầu ra:** Bảng ownership giữa nhóm Inventory, Order và Platform.

### Bước 5 — Thử thay đổi cục bộ

Giả lập yêu cầu “Reservation hết hạn sau 15 phút”. Thực hiện thay đổi trong Inventory, chạy contract tests với Order hiện tại. Ghi lại số service cần sửa code và số service cần deploy.

**Đầu ra:** Bằng chứng cho hoặc chống lại tuyên bố “Inventory tự chủ về nghiệp vụ”.

### Bước 6 — Thử sự cố độc lập

Giả lập Inventory chậm hoặc mất kết nối. Theo dõi Order phản hồi như thế nào, request nào timeout, job nào pending, ai trực xử lý. Đo blast radius và nguồn tài nguyên chia sẻ.

**Đầu ra:** Bằng chứng cho mức độc lập runtime thực tế và những shared dependencies cần quản lý.

### Bước 7 — Viết ADR

Ghi bối cảnh, những phương án đã cân nhắc (**giữ module / tách service chung cluster / tách hạ tầng chuyên biệt**), các trade-off, điều kiện thành công và thời điểm đánh giá lại.

**Đầu ra:** Một quyết định review được, tránh suy luận rằng “có microservice luôn tốt hơn”.

## 18. Mẫu bảng đánh giá một service boundary

Bảng dưới đây có thể dùng trong workshop. Không bắt buộc chấm số; nên điền bằng ví dụ và bằng chứng.

| Tiêu chí | Dấu hiệu ranh giới tốt | Bằng chứng cần thu |
|---|---|---|
| Trách nhiệm | Một capability có mục đích rõ | Danh sách use case, decision owner |
| Invariant | Chủ thể thực thi invariant được xác định | Dữ liệu và transaction boundary |
| Data ownership | Quyền ghi riêng và nguồn sự thật rõ | ACL, schema owner, API/event |
| Semantic independence | Mô hình riêng của bounded context | Context map, model translation |
| Contract stability | Thay đổi nội bộ không phá consumer | Contract tests, schema compatibility |
| Change coupling | Thay đổi cục bộ ít phải sửa service khác | Lịch sử co-change, số PR liên quan |
| Deployment independence | Có thể release/rollback một service | Pipeline, rollout test, runbook |
| Resource isolation | Có thể scale/giới hạn tải theo nhu cầu | Resource limits, autoscale, load test |
| Failure isolation | Sự cố có phạm vi ảnh hưởng dự đoán được | Trace, outage simulation, SLO |
| Team ownership | Người quyết định và chịu trách nhiệm rõ | Code owners, on-call, ADR |
| Cost/benefit | Giá trị độc lập lớn hơn chi phí phân tán | Latency, incident cost, vận hành |

Mẫu kết luận cho mỗi boundary:

~~~text
Capability:
Chủ sở hữu nghiệp vụ:
Quy tắc/invariant:
Dữ liệu nguồn sự thật:
Hợp đồng được công bố:
Các phụ thuộc chéo bắt buộc:
Các phụ thuộc chéo có thể loại bỏ:
Đơn vị build/deploy:
Những tài nguyên/hạ tầng dùng chung:
Bằng chứng có thể thay đổi cục bộ:
Bằng chứng có thể deploy độc lập:
Rủi ro về latency, transaction, fault isolation:
Quyết định hiện tại:
Điều kiện đánh giá lại:
~~~

## 19. Câu hỏi ôn tập

1. Một service có repository, container và database riêng nhưng Order phải sửa theo mỗi lần Inventory đổi chính sách reservation. Service đó độc lập ở chiều nào và còn thiếu gì?
2. Vì sao chia theo tầng ControllerService, BusinessService, DataService thường không tạo ranh giới nghiệp vụ tốt?
3. Bounded context và deployable microservice liên quan nhưng không tương đương ở điểm nào?
4. Database instance riêng có tự đảm bảo ownership dữ liệu không? Điều gì xảy ra nếu mọi service vẫn đọc/ghi dữ liệu chéo?
5. Có thể tự chủ nghiệp vụ trong modular monolith không? Hãy nêu cách đặt interface và nguồn sự thật.
6. Vì sao shared platform (logging, CI/CD, secrets, ingress) không tự làm service mất tự chủ nghiệp vụ?
7. Hãy đưa ra ví dụ một thay đổi cục bộ của Inventory và một thay đổi thực sự liên miền Order–Inventory–Payment. Yêu cầu phối hợp khác nhau như thế nào?
8. Contract test và migration tương thích giúp độc lập phát hành ra sao?
9. Tại sao một chuỗi synchronous calls dài có thể làm khả năng chịu lỗi thấp dù service boundary tốt?
10. Khi nào nên gộp hai service đang phải thay đổi cùng nhau? Những bằng chứng nào cần có trước khi quyết định?
11. Nếu Payment cần bảo mật và compliance cao hơn Catalog, bạn sẽ cân nhắc tách ở những chiều hạ tầng nào?
12. Một nhóm platform có thể giúp các nhóm domain tự chủ mà vẫn đảm bảo governance bằng những cơ chế nào?
13. Trong đánh giá của bạn, đâu là sự khác biệt giữa **quyền tự thay đổi** và **khả năng tự deploy**?
14. Nếu microservices tăng gấp đôi nhưng lead time và mức phụ thuộc release không cải thiện, bạn sẽ điều tra nguyên nhân từ đâu?
15. Lợi ích gì của modular monolith khiến nó là phương án hợp lý cho domain đang biến động mạnh?

## 20. Checklist kết thúc bài học

- [ ] Tôi diễn đạt được định nghĩa **tự chủ về nghiệp vụ** mà không dùng tên container, repository hoặc Kubernetes.
- [ ] Tôi diễn đạt được **độc lập về hạ tầng** theo nhiều chiều: build, deploy, runtime, scale, data infra, operations.
- [ ] Tôi giải thích được bốn ô ma trận, đặc biệt sự khác biệt giữa **modular monolith tốt** và **distributed monolith**.
- [ ] Tôi xác định được bounded context, business capability, invariant và nguồn sự thật cho một ví dụ cụ thể.
- [ ] Tôi biết vì sao database server riêng không tự động mang lại data ownership.
- [ ] Tôi có thể chỉ ra data coupling, semantic coupling, temporal coupling và deployment coupling bằng ví dụ.
- [ ] Tôi mô tả được hợp đồng API/event đủ để consumer không cần hiểu schema nội bộ của producer.
- [ ] Tôi biết sử dụng change-together test và contract test để đánh giá quyền thay đổi độc lập.
- [ ] Tôi hiểu shared platform có thể tăng tự chủ nếu cung cấp công cụ tự phục vụ và contract rõ.
- [ ] Tôi không mặc định mọi bounded context phải là một service hoặc mọi service phải có hạ tầng vật lý riêng.
- [ ] Tôi có thể giải thích khi nào giữ modular monolith và khi nào tách một capability thành service.
- [ ] Tôi có thể viết ADR dựa trên nghiệp vụ, tổ chức, SLO, độ trễ, rủi ro và tổng chi phí thay vì dựa trên “số microservice”.

**Thông điệp chính:** Tự chủ về nghiệp vụ là khả năng **sở hữu và tiến hóa một năng lực kinh doanh qua ranh giới hợp đồng**. Độc lập về hạ tầng là khả năng **đóng gói, triển khai, mở rộng và vận hành** năng lực đó với mức cô lập phù hợp. Hai trục hỗ trợ nhau nhưng không thay thế nhau. Ranh giới Microservices nên bắt đầu từ miền nghiệp vụ, dữ liệu và quyền quyết định; cách tách hạ tầng được chọn để phục vụ các nhu cầu đã nhận diện và kiểm chứng.