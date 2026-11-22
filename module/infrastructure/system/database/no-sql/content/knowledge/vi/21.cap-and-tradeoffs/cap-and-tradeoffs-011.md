# Liên hệ đánh đổi kỹ thuật với yêu cầu nghiệp vụ và phương án suy giảm dịch vụ

## 1. Từ định lý CAP đến quyết định sản phẩm

Trong chương **CAP và các đánh đổi**, câu hỏi quan trọng không chỉ là *“Database thiên về nhất quán (C) hay khả dụng (A)?”* mà còn là:

> “Khi một phần hệ thống NoSQL mất kết nối, chậm hoặc không thể cung cấp bảo đảm bình thường, tính năng nào phải giữ đúng tuyệt đối, tính năng nào được tiếp tục với dữ liệu cũ, và người dùng sẽ được thông báo như thế nào?”

Giả sử một nền tảng thương mại có:

- Danh mục hàng hóa và trang tìm kiếm.
- Giỏ hàng.
- Tồn kho.
- Tạo đơn và thanh toán.
- Hồ sơ khách hàng.
- Mã giảm giá.
- Gợi ý sản phẩm.
- Báo cáo doanh số.
- Hệ thống đăng nhập, phân quyền và chống gian lận.

Một sự cố chia cắt mạng giữa hai vùng triển khai có thể khiến các bản sao dữ liệu không nhìn thấy nhau. Nếu hệ thống cố duy trì mọi tính năng như lúc bình thường, nguy cơ là:

- Hai vùng cùng bán **đơn vị hàng cuối cùng**.
- Hai lần thanh toán cho một ý định mua hàng.
- Mã giảm giá dùng quá hạn mức.
- Người đã bị thu hồi quyền vẫn thực hiện thao tác nhạy cảm.
- Hai worker cùng tạo một đơn hàng.
- Thông báo sai rằng một giao dịch đã thành công dù trạng thái commit chưa được xác nhận.

Ngược lại, nếu **tắt toàn bộ website** chỉ vì một index tìm kiếm bị chậm, tổn thất sản phẩm có thể lớn hơn mức sự cố kỹ thuật đòi hỏi.

Một thiết kế có trách nhiệm phải nối bốn yếu tố:

~~~text
Yêu cầu nghiệp vụ
       |
       v
Bất biến dữ liệu + mức trễ chấp nhận được
       |
       v
Bảo đảm thực tế của NoSQL / kiến trúc phân tán
       |
       v
Chế độ suy giảm dịch vụ có kiểm soát
       |
       v
Khôi phục, đối soát, giám sát và kiểm chứng
~~~

**Suy giảm dịch vụ (graceful degradation)** không phải là cố trả một response thành công bằng mọi giá. Đó là chủ động giữ lại **phần chức năng an toàn và có giá trị**, đồng thời giảm mức phục vụ ở những nơi không còn đủ điều kiện để thực hiện đúng hợp đồng.

## 2. CAP thực sự nói gì?

### 2.1. Ba chữ C, A, P

Trong ngữ cảnh định lý CAP:

- **C — Consistency:** thường được hiểu theo mô hình *single-copy consistency* hay tính tuyến tính hóa (linearizability): các thao tác quan sát một trạng thái tương đương một bản sao có thứ tự hợp lệ, tôn trọng thứ tự thời gian thực theo định nghĩa.
- **A — Availability:** mỗi yêu cầu gửi tới một nút không lỗi trong mô hình phải cuối cùng nhận một phản hồi không lỗi. Đây là định nghĩa lý thuyết, **không đồng nhất** với chỉ số uptime 99,9% của một dịch vụ.
- **P — Partition tolerance:** hệ hoạt động trong điều kiện một số thông điệp giữa các nút bị thất lạc hoặc mạng bị chia cắt, dù một số nút vẫn đang chạy.

Điểm dễ nhầm là **P không phải một nút gạt bật/tắt** theo ý muốn. Trong hệ nhiều node, chia cắt mạng là rủi ro phải tính đến. Khi một partition xảy ra, hệ có thể phải đánh đổi việc tiếp tục trả response cho mọi yêu cầu với việc giữ bảo đảm nhất quán mạnh.

### 2.2. Một sự cố minh họa

~~~text
                   Trước sự cố
             Region A <------> Region B
                 K=10             K=10

                    Mạng bị chia cắt
             Region A    X       Region B
                 |                    |
           Client A ghi K=11     Client B đọc/ghi K

Hai hướng phổ biến:

Ưu tiên nhất quán:
  Một bên không được phép xác nhận operation xung đột,
  hoặc một số yêu cầu phải đợi/bị từ chối.

Ưu tiên availability:
  Hai bên tiếp tục phục vụ request cục bộ,
  chấp nhận có trạng thái tạm khác nhau và cần hội tụ/conflict resolution.
~~~

Không được biến ví dụ thành mệnh đề “mọi CP database luôn chặn toàn bộ reads” hoặc “mọi AP database luôn ghi cả hai phía”. Hành vi thực tế tùy **phạm vi khóa, quorum/leader, consistency level, loại thao tác và topology**.

### 2.3. CAP không nói rằng chỉ được chọn hai chữ cố định

Câu nói “chọn hai trong ba” là cách nhớ dễ gây hiểu sai. Khi **không có partition**, một hệ có thể đồng thời phục vụ request và duy trì linearizability. Khi partition thực sự tồn tại, việc đạt cả C và A như hai định nghĩa mạnh nói trên không thể luôn được bảo đảm cho mọi yêu cầu.

Một sản phẩm có thể:

- Cho phép read cũ nhưng không cho write xung đột.
- Chặn payment confirmation nhưng vẫn cho duyệt catalog.
- Dùng quorum khác nhau cho từng operation.
- Chuyển sang read-only mode ở một region.
- Trả trạng thái `PENDING` thay vì `SUCCESS`.
- Dừng ghi một khóa cụ thể nhưng tiếp tục ghi khóa khác.
- Phục vụ cache có giới hạn độ cũ cho dữ liệu không nhạy cảm.

Vì vậy nên mô tả **hành vi theo đường truy cập và bất biến nghiệp vụ**, thay vì gắn toàn bộ sản phẩm bằng một nhãn CP/AP.

### 2.4. Consistency trong CAP khác ACID consistency

Trong ACID, chữ **C** liên quan đến việc một transaction đưa dữ liệu từ trạng thái thỏa các ràng buộc sang trạng thái cũng thỏa ràng buộc.

Trong CAP, chữ **C** nói về hành vi quan sát của các thao tác phân tán theo mô hình nhất quán.

Hai khái niệm liên quan nhưng **không đồng nghĩa**. Một database có read linearizable cho từng key vẫn có thể không bảo vệ invariant nhiều item nếu ứng dụng thực hiện những writes rời rạc.

## 3. Những đánh đổi ngoài CAP: PACELC và vận hành thực tế

CAP tập trung vào tình huống **network partition**. Tuy nhiên, phần lớn thời gian hệ thống chạy khi mạng tương đối bình thường. Khi ấy vẫn có đánh đổi:

- Muốn xác nhận ghi ở nhiều replica/region thì có thêm round-trip.
- Muốn đọc dữ liệu mới nhất có thể cần leader/quorum.
- Muốn đọc replica gần người dùng có thể chấp nhận dữ liệu cũ.
- Muốn transaction xuyên nhiều partition sẽ tăng phối hợp/chi phí.
- Muốn giảm latency ở p99 đôi khi phải trả giá bằng mức nhất quán hoặc phạm vi tính năng.

Mô hình tư duy **PACELC** tóm tắt:

> Nếu có partition (P), hệ cân nhắc Availability hay Consistency (A/C); Else (E), khi không có partition, hệ thường cân nhắc Latency hay Consistency (L/C).

Không phải mọi sản phẩm chỉ có một lựa chọn cho toàn hệ. Một ứng dụng có thể kết hợp các lựa chọn này theo use case.

### 3.1. Bảng đánh đổi thực tế

| Lựa chọn | Lợi ích có thể có | Chi phí/rủi ro có thể có |
|---|---|---|
| Read từ replica gần | Latency thấp, giảm tải leader | Dữ liệu chậm hơn authority |
| Read mạnh từ authority | Quan sát mới hơn theo bảo đảm | Tăng latency hoặc bị từ chối khi authority unreachable |
| Ghi chỉ cần ACK cục bộ | Response nhanh hơn | Replication lag, rủi ro failover/RPO tùy kiến trúc |
| Ghi chờ quorum/coordination | Bảo vệ thứ tự/độ bền trong phạm vi cam kết | Thêm round-trip, có thể giảm availability |
| Transaction nhiều item | Bảo vệ invariant rộng hơn | Chi phí phối hợp, contention, giới hạn phạm vi |
| Asynchronous read model | Query/search/analytics nhanh và dễ scale | Độ trễ dữ liệu, cần reconciliation |
| Sử dụng cache khi backend lỗi | Giữ UX đọc một phần | Staleness và invalidation |
| Từ chối thao tác nhạy cảm khi không xác minh được | Giữ tính đúng và bảo mật | Giảm khả dụng chức năng đó |

Đừng coi lợi ích trong bảng là bảo đảm tuyệt đối. Cần đo trên đúng workload và cấu hình.

## 4. Bắt đầu bằng bất biến nghiệp vụ, không bắt đầu bằng cấu hình database

**Bất biến (invariant)** là điều kiện không được phép bị vi phạm trong trạng thái mà hệ thống công bố là hợp lệ.

Ví dụ:

- Tồn kho không bị phân bổ vượt số lượng khả dụng.
- Một lần bấm “Thanh toán” với cùng idempotency key không tạo hai khoản thu.
- Số dư và bút toán không mất một vế chuyển tiền.
- Một username chỉ thuộc một tài khoản theo phạm vi định nghĩa.
- Không cho người đã bị thu hồi quyền truy cập dữ liệu nhạy cảm.
- Đơn ở trạng thái `CANCELLED` không được tự động chuyển thành `SHIPPED` bởi callback cũ.
- Một reservation đã hết hạn không được xác nhận như còn hiệu lực.

Các bất biến trên khác hẳn những mục tiêu như:

- Danh mục sản phẩm hiện giá mới trong vòng vài giây.
- Gợi ý sản phẩm có thể là dữ liệu hôm qua.
- Báo cáo doanh số cập nhật mỗi phút.
- Bộ đếm lượt xem có thể chậm vài phút.
- Người dùng vừa sửa hồ sơ thì chính họ cần nhìn được thay đổi mới.

Những yêu cầu sau thường là **freshness, UX hoặc SLO**, không nhất thiết đòi transaction mạnh trên toàn hệ.

### 4.1. Phân loại theo mức độ được phép sai

| Lớp | Tính chất | Ví dụ | Hướng mặc định |
|---|---|---|---|
| I0 — Không được vi phạm | Invariant tiền, quyền, ownership, uniqueness | Debit, inventory reserve, revoke ACL | Kiểm tra tại authority; thiếu điều kiện thì từ chối/đợi |
| I1 — Phải hội tụ có kiểm soát | Workflow nhiều bước, eventual theo thiết kế | Order projection, shipment update | Pending, outbox, idempotency, reconciliation |
| I2 — Có thể hiển thị bản cũ giới hạn | Dữ liệu đọc ít nhạy cảm | Product description, bài viết công khai | Cache có TTL/version, cảnh báo khi cần |
| I3 — Có thể thiếu/tắt tạm | Chức năng hỗ trợ | Recommendations, ranking, analytics dashboard | Bỏ module, fallback đơn giản, trả unavailable |

Đây là **phân loại thiết kế**, không phải chuẩn chung của tất cả ngành. Cùng một trường dữ liệu có thể thuộc nhiều lớp tùy hành động. Giá sản phẩm có thể hiển thị cache khi duyệt, nhưng **giá tính tiền phải được xác nhận ở bước chốt giao dịch**.

### 4.2. Một trường dữ liệu, hai yêu cầu khác nhau

Ví dụ `product.price`:

**Trang danh mục:** có thể hiển thị giá cache kèm chính sách cập nhật nếu hợp đồng cho phép.

**Bước thanh toán:** phải áp dụng giá/chương trình khuyến mãi hợp lệ theo quy định kinh doanh, có thể lấy quote có hạn dùng hoặc xác minh ở authority trước khi chốt.

Không thể dùng lý do “giá có thể stale trên catalog” để cho phép thu tiền theo một giá sai đã hết hiệu lực.

## 5. Xác định phạm vi bảo đảm trước khi chọn cách suy giảm

Một cơ sở dữ liệu NoSQL có thể có những bảo đảm khác nhau theo:

1. **Một key/document:** atomic update, CAS/conditional write.
2. **Một logical partition:** các operation hoặc transaction có phạm vi nhất định.
3. **Nhiều item/partition trong transaction:** có API riêng với giới hạn.
4. **Một phiên client:** read-your-writes hoặc monotonic reads.
5. **Một region:** read/write acknowledgement và quorum theo nội vùng.
6. **Nhiều region:** replication và conflict resolution.
7. **Read model bên ngoài:** search, cache, vector, analytics có lịch đồng bộ khác nguồn.

Ví dụ:

~~~text
Client
  |
  v
Order API
  |
  +--> Orders DB (source of truth)
  |        |
  |        +--> Region B replica
  |
  +--> OrdersByCustomer projection
  |
  +--> Search index
  |
  +--> Analytics warehouse
~~~

Một transaction thành công trong Orders DB không làm bốn bản sao/đường truy cập cùng nhìn thấy kết quả ở một thời điểm, nếu không có hợp đồng phối hợp cụ thể.

**Định nghĩa chế độ suy giảm phải theo đường thao tác thực tế**: “GET /orders từ nguồn”, “GET /orders qua projection”, “POST /payments qua cổng thanh toán” không mặc nhiên chung một mức consistency.

## 6. Chuyển nhu cầu nghiệp vụ thành hợp đồng kỹ thuật

Trước khi chọn cách triển khai, hãy viết thành những câu có thể kiểm thử.

### 6.1. Ví dụ yêu cầu quá chung chung

> “Đơn hàng phải nhất quán.”

Câu này chưa nói được:

- Đơn không được tạo trùng?
- Khách phải thấy ngay đơn vừa tạo?
- Tất cả region phải thấy ngay?
- Danh sách tìm kiếm đơn phải cập nhật trong bao lâu?
- Có được nhận yêu cầu tạo đơn khi kho inventory unreachable không?
- Nếu payment response timeout, trạng thái đơn hiển thị gì?

### 6.2. Viết lại thành hợp đồng cụ thể

> “Một idempotency key tạo tối đa một đơn hàng đã được hệ thống chấp nhận.”

> “Chỉ trả `CONFIRMED` khi nguồn authoritative xác nhận reservation và trạng thái đơn theo giao thức đã thiết kế.”

> “Sau phản hồi tạo đơn thành công, API tra cứu đơn bằng ID có đường đọc bảo đảm người tạo thấy phiên bản vừa xác nhận.”

> “Danh sách đơn theo khách có thể chậm tối đa theo freshness SLO được công bố; giao diện dùng trạng thái chờ đồng bộ khi chưa có bản ghi.”

> “Khi không thể xác minh inventory, endpoint không xác nhận có hàng, mà từ chối hoặc tiếp nhận yêu cầu ở trạng thái chưa cam kết nếu chính sách cho phép.”

Như vậy, mỗi lời hứa được gắn với **dữ liệu, phạm vi và hành vi khi hệ không đáp ứng**.

## 7. Ba kiểu phản ứng khi mất bảo đảm bình thường

### 7.1. Fail closed

Từ chối thao tác khi không thể xác minh điều kiện an toàn.

Ví dụ:

- Không thực hiện payment nếu không xác nhận được idempotency/state.
- Không cấp quyền truy cập khi không kiểm tra được quyền bắt buộc.
- Không xác nhận đặt vé cuối cùng nếu không thể truy cập authority quản lý slot.
- Không cấp thêm hạn mức khi quota không thể xác minh.

**Ưu điểm:** giảm nguy cơ vi phạm invariant.

**Đánh đổi:** một phần chức năng không khả dụng.

### 7.2. Fail open có giới hạn

Tiếp tục phục vụ dù thiếu một phần thông tin, **chỉ khi rủi ro được chấp nhận trước**.

Ví dụ:

- Hiển thị bài viết công khai đã cache.
- Dùng thứ tự phổ biến thay cho thuật toán gợi ý cá nhân hóa.
- Hiển thị danh sách danh mục cũ trong một ngưỡng TTL được cho phép.
- Cho phép xem lịch sử tải về đã có trên thiết bị trong chế độ offline, nếu quyền sử dụng ngoại tuyến hợp lệ.

Không nên tự động fail open ở những tính năng liên quan **phân quyền, tiền, kho, giới hạn rủi ro** chỉ để giảm HTTP 5xx.

### 7.3. Pending/queued, không khẳng định thành công

Nếu một request có thể được tiếp nhận an toàn nhưng chưa thể hoàn thành, API có thể:

- Ghi một request intent bền vững.
- Trả trạng thái `PENDING` hoặc `ACCEPTED`.
- Cung cấp request ID để tra cứu.
- Hoàn tất sau khi dependency hồi phục.
- Cho người dùng biết việc chưa được xác nhận.

Ví dụ:

~~~json
{
  "requestId": "REQ-1001",
  "status": "PENDING",
  "message": "Yêu cầu đã được tiếp nhận; chưa xác nhận đặt hàng.",
  "statusUrl": "/api/requests/REQ-1001"
}
~~~

**Ranh giới quan trọng:** không được trả `202 Accepted` nếu request **chưa được lưu bền vững** ở một nơi có thể phục hồi theo hợp đồng. Nếu chỉ giữ trong memory rồi process chết, lời hứa “đã tiếp nhận” là sai.

## 8. Các mức suy giảm dịch vụ

Một cách vận hành là định nghĩa chế độ ở mức **tính năng hoặc dependency**, không chỉ một công tắc toàn hệ.

| Mức | Mô tả | Hành vi người dùng |
|---|---|---|
| D0 — Bình thường | Đường đọc/ghi và dependency đáp ứng SLO | Đầy đủ chức năng |
| D1 — Giảm tính năng phụ | Recommendations/analytics chậm hoặc lỗi | Ẩn module phụ, dùng fallback |
| D2 — Đọc bằng bản sao có kiểm soát | Source chậm; cache/replica đủ điều kiện | Xem dữ liệu cũ trong ngưỡng cho phép |
| D3 — Read-only chọn lọc | Không thể xác minh tính đúng khi ghi | Vẫn xem dữ liệu phù hợp, khóa thao tác thay đổi |
| D4 — Tiếp nhận chờ | Có durable queue nhưng xử lý đồng bộ chưa thể hoàn tất | Trạng thái PENDING, tra cứu tiến độ |
| D5 — Tạm từ chối | Không có đường thực hiện đúng/bền vững | Báo unavailable hoặc retry-later rõ ràng |

Các mức trên **không nhất thiết tăng tuyến tính**. Payment có thể ở D5 trong khi catalog ở D2 và recommendations ở D1.

### 8.1. Chế độ không nên được kích hoạt bằng cảm tính

Mỗi mode cần:

- Trigger định lượng hoặc điều kiện sự cố;
- Phạm vi service/region/tenant;
- Đường dữ liệu được phép dùng;
- Bất biến không được bỏ;
- Hành vi API/UX;
- Giới hạn thời gian;
- Người hoặc hệ có quyền bật/tắt;
- Điều kiện phục hồi;
- Cách ghi log/audit.

## 9. Ma trận suy giảm theo chức năng nghiệp vụ

| Chức năng | Điều không được sai | Khi dependency quan trọng hỏng | Có thể giữ lại |
|---|---|---|---|
| Product catalog | Không lộ dữ liệu trái quyền; không khẳng định giá chốt sai | Cache stale trong TTL cho dữ liệu công khai | Duyệt sản phẩm, ảnh, mô tả |
| Search | Không trả nội dung ngoài ACL | Dùng keyword/basic search hoặc báo tạm lỗi | Tìm kiếm đơn giản |
| Recommendation | Không lộ dữ liệu cá nhân | Tắt personalization; dùng danh sách phổ biến được phép | Trang vẫn hoạt động |
| Cart | Không mất ý định người dùng vô thông báo | Local draft/queued edit với trạng thái chưa đồng bộ | Xem và chỉnh bản nháp |
| Inventory | Không oversell | Không xác nhận reservation; có thể tiếp nhận waitlist | Xem availability ước lượng có nhãn |
| Checkout | Không nhân đôi đơn hoặc thanh toán | Read-only/đợi; nếu có durable intent, PENDING | Giữ giỏ, cho xem thông tin |
| Payment | Không thu trùng; không báo đã thanh toán khi chưa rõ | UNKNOWN/PENDING, đối soát provider | Xem trạng thái và mã tham chiếu |
| Voucher quota | Không vượt quota theo policy | Tạm tắt áp mã mới | Giữ giá thường, cho thử lại sau |
| User profile | Chống lost update/đọc sai quyền | Cache chỉ cho nội dung không nhạy cảm; chặn chỉnh sửa | Xem phần được phép |
| Authorization | Không cho thao tác trái quyền | Fail closed ở hành động nhạy cảm | Nội dung công khai hoặc đã được cấp quyền offline theo policy |
| Order tracking | Không tạo trạng thái chuyển sai | Hiển thị mốc cập nhật gần nhất | Xem tiến trình đã xác nhận |
| Analytics | Không hiển thị báo cáo như realtime khi trễ | Cảnh báo “cập nhật đến...” | Báo cáo lịch sử |
| Notifications | Không phát sự kiện sai/nhân đôi không kiểm soát | Queue/retry có idempotency | App vẫn dùng được |

Bảng là **khởi điểm thiết kế**, không phải lời khuyên áp dụng đồng loạt. Đặc biệt, những sản phẩm tài chính/y tế/an toàn có thể cần quy tắc fail closed chặt hơn.

## 10. Catalog và tìm kiếm: suy giảm mà vẫn hữu ích

### 10.1. Catalog là ứng viên cho cache có kiểm soát

Nội dung như tên, mô tả, ảnh và thông số công khai thường thay đổi ít hơn trạng thái thanh toán.

Một đường đọc:

~~~text
GET /products/P100
       |
       v
Cache có freshness metadata?
       |
       +-- yes, đủ mới --> trả bản cache
       |
       +-- no ----------> đọc Product DB
                              |
                              +-- OK --> cập nhật cache
                              |
                              +-- FAIL --> kiểm tra stale policy
                                           |
                                           +-- cho phép --> trả stale có nhãn
                                           +-- không --> unavailable
~~~

**Stale policy** cần theo field, không chỉ theo document. Một bản cache chứa mô tả cũ có thể chấp nhận được, nhưng `isAvailable` hoặc giá dùng để thanh toán không được mặc định hợp lệ.

### 10.2. Stale-while-revalidate

Một chiến lược cache:

- Trong **fresh TTL**, trả dữ liệu đã cache.
- Sau fresh TTL nhưng còn trong **stale window**, có thể trả bản cũ và kích hoạt refresh.
- Ngoài stale window, phải thử nguồn hoặc từ chối theo hợp đồng.

Ví dụ định hướng:

~~~text
fresh TTL  = 60 giây
stale TTL  = 10 phút
~~~

Các con số chỉ để minh họa cách thiết kế, không phải mặc định an toàn cho mọi dữ liệu.

### 10.3. Có thể “cũ” nhưng không thể “không được phép”

Nếu một tài liệu từng công khai nhưng vừa chuyển thành riêng tư, việc trả cache cũ sau revoke có thể vi phạm quyền. Vì vậy cache stale cho nội dung nhạy cảm cần:

- Kiểm tra ACL tại authority hoặc có revocation epoch;
- Phân biệt public và restricted;
- Bỏ qua cache khi quyền không thể xác minh;
- Cơ chế invalidate ưu tiên cao cho thay đổi quyền.

Không nên áp **fail open** như một quy tắc vô điều kiện cho catalog.

### 10.4. Search index bị lỗi

Sản phẩm có thể:

1. Dùng một bộ lọc cơ bản theo danh mục/thuộc tính nếu nguồn hỗ trợ;
2. Tắt vector search nhưng giữ keyword search;
3. Dùng kết quả cache chỉ nếu phù hợp phân quyền và freshness;
4. Hiện thông báo “Tìm kiếm nâng cao tạm thời chưa khả dụng”.

Không nên tự chuyển một search query tốn kém sang **full scan toàn bộ NoSQL** chỉ vì index hỏng: phương án fallback có thể khiến database nguồn quá tải và làm hỏng cả checkout.

### 10.5. Chặn fallback gây sự cố dây chuyền

Nếu search service mất, hàng nghìn request cùng scan primary DB sẽ làm tăng CPU/I/O và đẩy các thao tác quan trọng vào timeout.

Cần giới hạn:

- QPS fallback;
- Max scan/response size;
- Timeout;
- Tenant budget;
- Cache hit;
- Circuit breaker;
- Load shedding.

“Có phương án fallback” chưa đủ; phương án đó phải được đo tải và **có giới hạn tác động tới dependency khác**.

## 11. Giỏ hàng: cho thao tác offline nhưng không giả vờ đã đặt hàng

Giỏ hàng thường là một **ý định mua**, không phải bằng chứng rằng inventory đã được giữ.

### 11.1. Bản nháp cục bộ

Nếu Cart DB không thể ghi, ứng dụng có thể lưu:

~~~json
{
  "cartDraftId": "DRAFT-2001",
  "syncState": "LOCAL_ONLY",
  "items": [
    {"productId": "P100", "quantity": 2}
  ]
}
~~~

Giao diện phải phân biệt:

- **Đã lưu trên thiết bị**;
- **Đã đồng bộ với tài khoản**;
- **Đã kiểm tra hàng/giá**;
- **Đã đặt hàng thành công**.

Bốn trạng thái này không tương đương.

### 11.2. Xung đột khi đồng bộ lại

Giả sử phone thêm 2 đơn vị, laptop xóa sản phẩm và cả hai offline. Khi reconnect, nên dùng chiến lược nào?

- Last-write-wins theo timestamp?
- Merge theo operation?
- Counter kiểu CRDT?
- Hỏi người dùng?
- Ưu tiên thao tác xóa?
- Gộp giỏ từng item?

Không có lựa chọn mặc định đúng cho mọi app. Nếu người dùng xóa sản phẩm vì không muốn mua, một phép merge cộng dồn có thể **tự thêm lại** sản phẩm không mong muốn.

### 11.3. Không dùng cart quantity làm available inventory

`cart.quantity=2` không có nghĩa hàng còn đủ. Checkout phải kiểm tra bằng một reservation/transaction ở nguồn authoritative theo hợp đồng.

## 12. Inventory: trường hợp điển hình cần fail closed đối với cam kết cuối

### 12.1. Điều kiện cần bảo vệ

Với hàng vật lý có số lượng giới hạn:

\[
available \geq 0
\]

hoặc mô hình đầy đủ hơn:

\[
onHand - reserved - allocated \geq 0
\]

Tùy hệ thống, có thể có pre-order/backorder được phép; lúc đó invariant phải phản ánh chính sách này. Không được ngầm coi mọi sản phẩm chỉ có một cơ chế tồn kho.

### 12.2. Conditional decrement

Giả sử nguồn lưu item:

~~~json
{
  "productId": "P100",
  "available": 1,
  "version": 12
}
~~~

Một atomic conditional update:

~~~text
IF available >= 1:
   available := available - 1
   version := version + 1
ELSE:
   NOT_APPLIED
~~~

Nếu database xác nhận thành công theo cơ chế nhất quán có thẩm quyền, thao tác reserve được ghi nhận. Nếu không thể đạt quorum/authority, **không nên suy hàng còn chỉ vì replica cũ hiển thị 1**.

### 12.3. Khi inventory authority unreachable

Các lựa chọn nghiệp vụ:

**Từ chối checkout tạm thời:** giữ nguyên giỏ, thông báo thử lại sau. Phù hợp khi không được oversell.

**Tiếp nhận yêu cầu “đang chờ xác nhận”:** chỉ khi có durable queue/intent, user hiểu chưa có reservation và không bị tính tiền như confirmed.

**Cho pre-order/backorder:** chỉ nếu sản phẩm có chính sách bán vượt stock rõ ràng và quy trình giao hàng phù hợp.

Không nên tự tạo một “reservation tạm” ở hai region riêng biệt rồi coi nó có hiệu lực toàn cục.

### 12.4. Hạn mức phân bổ trước theo region

Một hệ muốn tiếp tục bán khi liên vùng mất kết nối có thể **phân bổ quota độc lập trước sự cố**:

~~~text
Tổng stock P100 = 100

Region A được quyền bán tối đa 60
Region B được quyền bán tối đa 40
~~~

Mỗi region giảm trong phần quota được cấp bền vững; tổng quyền phân bổ không vượt stock.

Ưu điểm: có thể tiếp tục giao dịch cục bộ mà không cần phối hợp từng order.

Đánh đổi:

- Nếu A đã hết 60 còn B còn 20 nhưng mạng chia cắt, A không thể tự lấy quota của B.
- Chuyển quota phải có một cơ chế nguyên tử và không cấp trùng.
- Khi restock/return phải đối soát quota/stock.
- Phân bổ không phù hợp nếu một khu vực có nhu cầu khó dự đoán và tồn kho nhỏ.

Đây là ví dụ **thay đổi mô hình nghiệp vụ để đạt availability tốt hơn mà vẫn giữ invariant**, không phải đánh lừa CAP.

### 12.5. Phân biệt availability hiển thị và availability để chốt

Có thể hiển thị “Dự kiến còn hàng” dựa trên index/cached estimate, nhưng nút xác nhận phải có bước reserve chính thức. Giao diện phải tránh tạo kỳ vọng “đã giữ hàng” khi chưa có nguồn xác nhận.

## 13. Thanh toán: timeout không có nghĩa giao dịch thất bại

Đây là bài toán mà sai một lần có thể tốn tiền và niềm tin.

### 13.1. Kịch bản phản hồi bị mất

~~~text
Client                  Payment Service                Provider
   |                           |                          |
   |--- Pay(requestId=R1) ---->|                          |
   |                           |--- charge(R1) ---------->|
   |                           |<-- success --------------|
   |                           X    network timeout       |
   |<-- 504 / unknown ---------|                          |
   |                                                      |
   | User bấm lại?                                       |
~~~

Provider đã thu tiền, nhưng service chưa nhận hoặc chưa ghi kết quả.

Nếu API trả “thất bại, thanh toán lại” và dùng **request ID mới**, có thể thu hai lần.

### 13.2. Trạng thái kết quả cần phân biệt

| Trạng thái | Ý nghĩa | UI phù hợp |
|---|---|---|
| `SUCCEEDED` | Có bằng chứng provider + trạng thái nguồn đã xác nhận theo protocol | Hiển thị đã thanh toán |
| `DECLINED` | Provider xác nhận từ chối, chưa có charge thành công | Cho chọn phương thức khác |
| `PENDING` | Đã gửi/đang xử lý, chưa có kết luận | Hiển thị đang xác minh |
| `UNKNOWN` | Mất phản hồi; có thể đã commit | Không cho tạo charge mới vô điều kiện |
| `REQUIRES_ACTION` | Provider cần bước xác thực/3DS... | Dẫn tới bước tiếp theo |

Tên trạng thái tùy hệ. Nguyên tắc là không tự chuyển `UNKNOWN` thành `FAILED` nếu không có bằng chứng.

### 13.3. Idempotency key

Một payment intent có khóa:

~~~json
{
  "paymentIntentId": "PAY-1001",
  "orderId": "O100",
  "idempotencyKey": "PAY-O100-attempt-1",
  "amountMinor": 250000,
  "currency": "VND",
  "status": "PENDING"
}
~~~

Khi retry, sử dụng khóa theo đúng contract của provider để tránh nhân đôi charge. Cùng key với payload khác phải được từ chối hoặc xử lý theo policy rõ.

**Idempotency key chỉ bảo vệ trong phạm vi mà provider hoặc hệ đã triển khai**. Nó không tự đảm bảo một database và payment gateway cùng commit nguyên tử.

### 13.4. Suy giảm khi provider lỗi

- Không xác nhận thanh toán nếu trạng thái chưa rõ.
- Tạm ngừng phương thức lỗi hoặc chuyển sang phương thức khác nếu sản phẩm cho phép.
- Cho người dùng xem pending payment và mã tham chiếu.
- Chạy reconciliation với provider.
- Tạm giữ reservation theo deadline phù hợp hoặc giải phóng an toàn khi biết payment không thành công.
- Tránh queue vô hạn các lệnh charge có thể retry gây trùng.

Một trải nghiệm “Đơn đang chờ xác minh thanh toán” tốt hơn thông báo “Đã thanh toán” không có cơ sở.

## 14. Xác thực, phân quyền và chống gian lận: không suy giảm bằng cách bỏ kiểm tra

### 14.1. Quyền có thể thay đổi giữa hai lần đọc

Giả sử admin thu hồi quyền U42. Region B còn cached ACL cũ:

~~~text
Source: U42 role=REVOKED, version=12
Cache B: U42 role=ADMIN, version=11
~~~

Nếu một API quản trị dùng cache cũ và tiếp tục chấp nhận action, đó có thể là lỗ hổng bảo mật.

### 14.2. Fail closed ở hành động nhạy cảm

Khi không thể xác minh trạng thái quyền mới nhất theo chính sách:

- Trả lỗi tạm thời hoặc yêu cầu xác thực lại.
- Không thực hiện thao tác quản trị.
- Không trả tài liệu riêng tư nếu chưa chứng minh quyền.
- Không dựa vào stale cache không có revocation guarantee.

Một số use case offline có thể được cho phép theo policy riêng, với token/scope ngắn và tài nguyên đã cấp quyền. **Đây phải là quyết định an ninh được định nghĩa trước**, không phải fallback ngẫu hứng.

### 14.3. Phân biệt nhận diện và phân quyền

Token chứng minh danh tính không tự chứng minh user **vẫn có quyền** trên resource hiện tại. Hệ có thể cần permission version, revocation epoch, authoritative check hoặc TTL giới hạn.

### 14.4. Chống gian lận

Nếu hệ risk scoring không khả dụng:

- Có thể giới hạn những giao dịch rủi ro cao;
- Yêu cầu kiểm tra bổ sung;
- Chuyển đơn sang `REVIEW_PENDING`;
- Cho các giao dịch rủi ro thấp qua ngưỡng được phê duyệt trước, nếu chính sách cho phép.

Không nên “tắt mọi fraud check” để giữ conversion rate mà không có risk budget và sự cho phép nghiệp vụ.

## 15. Hồ sơ người dùng và read-your-writes

Đọc trạng thái ngay sau khi ghi là một kỳ vọng UX quan trọng.

### 15.1. Người dùng sửa địa chỉ

~~~text
T0: PATCH /profile/address -> success
T1: GET /profile/address -> địa chỉ cũ
~~~

Nếu API hứa **read-your-writes**, đây là lỗi trải nghiệm theo hợp đồng.

### 15.2. Các giải pháp

- Đọc lại từ authority/leader sau write.
- Mang session/causal token giữa request.
- Trả bản ghi vừa commit trong write response.
- Tạm bypass cache đối với key vừa sửa.
- Đợi read model đạt `sourceVersion` tối thiểu.
- Sử dụng OCC/ETag để ngăn ghi đè khi hai thiết bị sửa đồng thời.

### 15.3. Trường hợp hai thiết bị

RYW của điện thoại **không buộc** laptop thấy ngay nếu chúng không chia sẻ session. Nếu sản phẩm cần đồng bộ tức thì trên mọi thiết bị, phải chọn mức visibility giữa sessions phù hợp và định nghĩa latency cụ thể.

## 16. Báo cáo và phân tích: đúng thời điểm dữ liệu quan trọng hơn “realtime giả”

Analytics thường chạy trên pipeline:

~~~text
OLTP NoSQL -> CDC/Outbox -> Stream -> Warehouse/OLAP -> Dashboard
~~~

Có thể có delay do:

- Broker lag;
- Batch window;
- Transform;
- Dedup/reconciliation;
- Dashboard cache.

### 16.1. Hiển thị watermark

Thay vì chỉ ghi:

> “Doanh thu hôm nay: 50 triệu.”

nên có metadata:

~~~json
{
  "revenueMinor": 50000000,
  "currency": "VND",
  "completeThrough": "2026-11-14T08:30:00Z",
  "generatedAt": "2026-11-14T08:34:00Z",
  "isPartial": true
}
~~~

UI có thể thông báo:

> “Dữ liệu cập nhật đến 08:30 UTC; một số giao dịch gần đây có thể chưa được tính.”

### 16.2. Báo cáo không phải ledger thanh toán

Không dùng tổng doanh thu từ warehouse trễ để quyết định hoàn tiền hoặc xác nhận giao dịch. Nguồn authoritative là ledger/payment state có bảo đảm phù hợp.

### 16.3. Khi pipeline ngừng

Có thể giữ dashboard ở phiên bản cuối:

- Ghi rõ timestamp/watermark;
- Không hiển thị như realtime;
- Tắt hành động dựa vào dữ liệu chưa đủ;
- Alert khi freshness vượt SLO;
- Tăng cấp hỗ trợ nếu reconciliation phát hiện lệch.

## 17. Chọn nguồn sự thật và read model

Một kiến trúc NoSQL có thể được tổ chức:

~~~text
                       Client / API
                            |
                    +-------+--------+
                    |                |
                    v                v
             Command path        Query path
                    |                |
                    v                v
             Source of truth      Search / Cache /
             (Orders, Ledger,     Projection /
              Inventory, ACL)     Analytics
                    |
             CDC / Outbox / Log
                    |
                    +----> Projectors
                    |
                    +----> Region replicas
~~~

Điểm quan trọng:

- **Command path** bảo vệ bất biến khi ghi.
- **Query path** tối ưu latency/UX và có thể chấp nhận staleness theo use case.
- **Event path** kết nối source với read models, cần version/ordering/retry.
- **Security path** phải kiểm tra quyền ở nơi đủ tin cậy.

Không phải mọi command phải dùng một database mạnh toàn cục, nhưng mỗi invariant phải có một authority hoặc giao thức kiểm tra đầy đủ.

## 18. Thiết kế API minh bạch về trạng thái suy giảm

### 18.1. Chỉ trả thành công khi hợp đồng thực sự hoàn thành

Ví dụ xác nhận đặt hàng:

~~~http
POST /api/orders
Idempotency-Key: ORDER-REQ-1001
Content-Type: application/json

{
  "cartId": "C100",
  "shippingAddressId": "A42"
}
~~~

Nếu có thể commit order theo hợp đồng:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "orderId": "O100",
  "status": "CONFIRMED",
  "version": 4
}
~~~

Nếu chỉ có thể lưu yêu cầu để xử lý sau:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "requestId": "ORDER-REQ-1001",
  "status": "PENDING",
  "orderId": null,
  "message": "Yêu cầu đã tiếp nhận, chưa xác nhận đơn hàng.",
  "statusUrl": "/api/order-requests/ORDER-REQ-1001"
}
~~~

Nếu không thể tiếp nhận bền vững:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 30
Content-Type: application/json

{
  "code": "ORDER_ACCEPTANCE_UNAVAILABLE",
  "message": "Hiện chưa thể tiếp nhận đơn hàng an toàn. Vui lòng thử lại."
}
~~~

Đây là các **mẫu hợp đồng minh họa**; HTTP status và schema phải nhất quán với API thực. `Retry-After` nên dựa trên chính sách hợp lý, không hứa đúng lúc service phục hồi.

### 18.2. Trạng thái tạm khác commit

Nên tách:

~~~text
LOCAL_DRAFT
QUEUED
PENDING_VALIDATION
RESERVED
CONFIRMED
FAILED
CANCELLED
UNKNOWN_NEEDS_RECONCILIATION
~~~

Không nên gộp tất cả thành một boolean `success`. Các trạng thái tạm có đường chuyển hợp lệ và SLA xử lý riêng.

### 18.3. Retry an toàn

Nếu client gửi lại cùng `Idempotency-Key` sau timeout:

- Backend có thể trả kết quả cũ đã commit.
- Hoặc trả trạng thái PENDING đang xử lý.
- Hoặc cho phép retry idempotent theo protocol.
- Không tạo thêm payment/order mới cho cùng ý định nghiệp vụ.

Cần định nghĩa thời gian lưu idempotency key, scope theo tenant/user và cách xử lý cùng key nhưng payload khác.

## 19. Circuit breaker: ngắt đường lỗi trước khi làm sập mọi thứ

Một dependency chậm có thể làm request treo, tiêu thụ thread/connection pool và gây sập dây chuyền.

### 19.1. Ba trạng thái phổ biến

~~~text
             failures vượt ngưỡng
       CLOSED ------------------------> OPEN
         ^                                |
         |                                | sau cooldown
         |                                v
         +--------------------------- HALF_OPEN
              probe thành công / thất bại
~~~

- **CLOSED:** cho request đi qua, theo dõi lỗi.
- **OPEN:** fail fast hoặc fallback thay vì gọi dependency đang lỗi.
- **HALF_OPEN:** cho số ít request thử nghiệm để xác định khả năng phục hồi.

### 19.2. Circuit breaker không quyết định business safety

Một breaker quanh Inventory DB không nên fallback thành “giữ hàng thành công” khi DB unreachable. Fallback hợp lệ có thể là `PENDING` hoặc `503`.

Một breaker quanh Recommendation API có thể fallback sang danh sách sản phẩm phổ biến.

**Cùng kỹ thuật resilience, nhưng fallback khác nhau theo invariant.**

### 19.3. Theo dõi lỗi đúng loại

- Timeout/connection error;
- 5xx từ dependency;
- Rate limiting;
- Conflict/conditional check failed;
- Business validation error.

Không nên tính **một conditional write bị từ chối đúng nghiệp vụ** như lỗi hạ tầng và mở circuit breaker vô cớ. Error classifier phải phân biệt failure categories.

## 20. Timeout, retry, backoff, hedging và rủi ro nhân đôi tác động

### 20.1. Timeout là giới hạn chờ của client

Client timeout không chứng minh server chưa commit:

~~~text
Client -> DB: Conditional write
DB commit thành công
Response bị mất
Client thấy TIMEOUT
~~~

Do đó, retry phải dựa trên idempotency/operation ID hoặc reconciliation thích hợp.

### 20.2. Exponential backoff với jitter

Một chính sách minh họa:

\[
delay_n = \min(maxDelay,\ baseDelay \cdot 2^n) + jitter
\]

Mục đích là giảm retry đồng loạt khi dependency đang quá tải. Cần giới hạn:

- Số attempt;
- Tổng retry budget;
- Deadline request;
- Concurrent retries;
- QPS theo tenant/user;
- Các lỗi **được phép retry**.

Không retry vô hạn một mutation không idempotent.

### 20.3. Hedged requests

Hedging gửi thêm request khi request đầu chậm có thể giảm tail latency của **read phù hợp**, nhưng:

- Tăng tải;
- Có thể đọc từ nguồn khác version;
- Không phù hợp cho write có side effect nếu thiếu idempotency;
- Cần tôn trọng read consistency/session token;
- Có thể làm hệ quá tải thêm.

“Đọc nơi nào phản hồi nhanh nhất” không phải “đọc nơi nào đủ mới nhất”.

### 20.4. Load shedding

Khi hệ đạt ngưỡng tài nguyên, từ chối một phần request **ít quan trọng hơn** có thể giúp giữ đường thanh toán/đăng nhập an toàn:

~~~text
Total capacity có giới hạn
       |
       +--> Priority 1: critical commands
       |
       +--> Priority 2: core reads
       |
       +--> Priority 3: search/recommendations
       |
       +--> Priority 4: batch/analytics
~~~

Thứ tự cụ thể tùy sản phẩm. Cần đảm bảo priority queue không làm các nhóm user bị đói dịch vụ vô hạn và không phá fairness/bảo mật.

## 21. Bulkhead: cô lập lỗi giữa các chức năng

**Bulkhead** dùng tài nguyên tách biệt để một dependency không ăn hết ngân sách của chức năng khác.

Ví dụ:

~~~text
                  API Gateway
                      |
        +-------------+--------------+
        |             |              |
        v             v              v
 Checkout pool    Catalog pool    Analytics pool
    30 threads      100 threads      10 threads
        |             |              |
    Inventory      Product DB        Warehouse
~~~

Những con số chỉ để minh họa. Trong hệ async, bulkhead có thể là semaphore/concurrency limiter thay vì thread pool.

Nếu search chậm:

- Search pool đầy;
- Một số search requests bị giới hạn;
- Checkout pool vẫn còn tài nguyên để xử lý;
- Alert riêng cho search.

Không nên cho fallback search quét source và chiếm chung connection pool tới Inventory DB. Khi thiết kế bulkhead, chú ý cả:

- Thread/concurrency;
- Connection pools;
- CPU;
- Memory;
- Queue;
- I/O;
- Rate limits theo tenant;
- Chi phí downstream.

## 22. Hàng đợi và backpressure: chờ một cách có trách nhiệm

### 22.1. Queue là cách làm phẳng tải, không phải phép màu tăng capacity

Nếu hệ xử lý tối đa 1.000 command/giây nhưng nguồn vào 5.000 command/giây liên tục, queue sẽ tăng:

\[
queueGrowthRate = arrivalRate - serviceRate
\]

với các điều kiện của mô hình hàng đợi tương ứng.

Trong ví dụ, backlog tăng khoảng 4.000 command/giây trong lúc chênh lệch kéo dài. Không thể “cứ queue vô hạn là ổn”.

### 22.2. Điều kiện để trả 202 Accepted

- Intent đã được persist/ack theo mức durability yêu cầu;
- Có operation ID idempotent;
- Có consumer xử lý an toàn;
- Có SLA/deadline và trạng thái timeout;
- Có retry/DLQ;
- Có sức chứa/backpressure;
- Có chính sách hủy request;
- Có cách người dùng tra cứu;
- Có kế hoạch khi queue không thể ghi.

### 22.3. Khi backlog quá lớn

Ứng dụng có thể:

- Thắt chặt rate limit;
- Trả 429 hoặc 503 theo policy;
- Tắt batch/low priority producers;
- Thông báo thời gian xử lý **không được hứa chắc nếu chưa biết**;
- Chặn phát sinh yêu cầu không cần thiết;
- Tăng worker nếu downstream có capacity;
- Không tự thêm worker nếu bottleneck là một partition/lock nóng.

### 22.4. At-least-once delivery và idempotency

Hàng đợi phổ biến có thể giao lại event sau crash hoặc timeout. Vì vậy “queue đã nhận một message” không có nghĩa side effect chỉ diễn ra một lần. Dùng idempotency key, version, processed-event log hoặc transaction/outbox pattern khi phù hợp.

## 23. Outbox, saga và reconciliation cho các workflow nhiều bước

### 23.1. Vì sao hai writes rời không đủ?

Workflow tạo đơn:

~~~text
1. Reserve inventory
2. Create order
3. Publish event
4. Charge payment
~~~

Nếu bước 1 thành công rồi bước 2 thất bại, tồn kho bị giữ mà không có đơn. Nếu bước 2 thành công rồi bước 3 không publish, read model không biết đơn tồn tại.

### 23.2. Transactional outbox

Trong nguồn hỗ trợ transaction phù hợp:

~~~text
BEGIN
  UPDATE Order state=CREATED
  INSERT Outbox event ORDER_CREATED
COMMIT
~~~

Một relay đọc outbox và gửi đến broker. Điều này giúp tránh khoảng “DB commit nhưng event chưa được ghi ở đâu” trong phạm vi transaction, nhưng relay có thể publish trùng; consumer cần idempotent.

### 23.3. Saga

Khi không có transaction xuyên mọi service, một workflow có thể có state machine:

~~~text
REQUESTED
    |
    v
INVENTORY_RESERVED
    |
    v
PAYMENT_PENDING
    |
    +--> PAYMENT_CONFIRMED --> ORDER_CONFIRMED
    |
    +--> PAYMENT_FAILED ---> RELEASE_INVENTORY
    |
    +--> UNKNOWN ----------> RECONCILIATION
~~~

Mỗi transition có điều kiện/version, operation ID và retry semantics. Compensation **không phải rollback vật lý tức thời**; nó là hành động nghiệp vụ có thể cần thực hiện và thất bại độc lập.

### 23.4. Khi suy giảm, saga vẫn phải tiến lên hoặc dừng an toàn

Nếu payment provider lỗi, không tự giữ inventory vô thời hạn. Cần deadline và quy tắc:

- Có tiếp tục giữ reservation trong một khoảng cho phép?
- Nếu không xác nhận payment, có giải phóng không?
- Nếu provider đã charge nhưng client chưa biết, khi nào reconcile?
- User có được hủy request đang pending không?
- Cách chống duplicate release/double charge?

Chế độ suy giảm phải bao gồm **quy trình phục hồi**, không chỉ response HTTP lúc đầu.

## 24. Version, fencing và trạng thái không đi lùi

Một hệ dùng nhiều replica/read model dễ gặp callback đến muộn:

~~~text
Event v10: Order CREATED
Event v11: Order PAID
Event v12: Order CANCELLED

Consumer nhận v12 trước v11.
~~~

Nếu projector upsert vô điều kiện, trạng thái `CANCELLED` có thể bị event `PAID` cũ ghi đè.

### 24.1. Version guard

Một rule:

~~~text
if incoming.version <= current.version:
    ignore
else:
    apply mutation and record version atomically
~~~

Cần lưu marker/version ngay cả khi object bị xóa để chặn sự kiện cũ tạo lại record. Nếu key được tái sử dụng, thêm generation/epoch.

### 24.2. Fencing cho stale worker

Khi lease của worker A hết hạn và worker B được cấp thế hệ mới:

~~~text
A token=41
B token=42
~~~

Tài nguyên đích cần kiểm tra token cùng mutation:

~~~text
ACCEPT write token=42
REJECT write token=41
~~~

Owner token random không tự là fencing token vì nó không có thứ tự thế hệ.

### 24.3. Không nhầm version với snapshot toàn cục

`Order.version=12` chỉ cho biết phiên bản của order. Nó không chứng minh Inventory, Payment và Search đều ở mốc tương ứng. Để tạo snapshot toàn hệ cần giao thức/checkpoint khác.

## 25. Multi-region: thiết kế suy giảm khác nhau theo phạm vi của partition

### 25.1. Leader/authority đơn vùng

Nếu một region được chọn làm authority của inventory:

- Bình thường, cả hai region route critical write về authority.
- Khi mạng liên vùng đứt, region khác có thể bị chặn checkout.
- Catalog, lịch sử đọc có thể vẫn phục vụ trong giới hạn.
- Có thể dùng waitlist/durable intent cục bộ nếu product contract cho phép và không xác nhận reservation.

Ưu điểm: dễ giữ một nơi quyết định invariant. Nhược điểm: latency cross-region và giảm write availability khi đường đến authority lỗi.

### 25.2. Quorum phân tán nhiều vùng

Hệ cần một ngưỡng đồng thuận trước khi xác nhận mutation. Khi partition mạng:

- Nhóm có quorum có thể tiếp tục;
- Nhóm không có quorum phải từ chối/đợi những thao tác cần quorum;
- Một số reads có thể vẫn phục vụ theo consistency yếu hơn nếu product cho phép;
- Failover có thể tăng latency.

Không nên quảng cáo “quorum=3 trong RF=5” là bảo đảm transaction nguyên tử cho **mọi item của hệ**. Scope vẫn phải được xác định.

### 25.3. Multi-master eventual

Hai vùng có thể đồng thời chấp nhận writes rồi giải quyết conflict. Phù hợp hơn với dữ liệu có thể merge và rủi ro chấp nhận được; không tự phù hợp với uniqueness hoặc quota nghiêm ngặt.

Ví dụ giỏ hàng có thể merge theo quy tắc; còn payment ID hay username duy nhất cần một authority/quy trình tránh trùng.

### 25.4. Phân vùng trước quyền ghi

Nếu muốn tiếp tục nhận một số writes ngay khi chia cắt mạng, có thể phân bổ trước **quyền tiêu thụ/hạn mức** theo region. Bằng cách đưa invariant tổng vào lúc cấp quyền, mỗi region được quyền thao tác trong quota riêng.

Đánh đổi: khả dụng cục bộ bị giới hạn bởi quota đã cấp; không tự vay phần của vùng khác khi mất mạng.

### 25.5. Chuyển authority sau sự cố

Failover không được đơn giản là:

~~~text
Primary A unreachable -> chọn B làm primary ngay
~~~

nếu A có thể vẫn hoạt động và chấp nhận writes. Cần cơ chế:

- Leader election/fencing;
- Term/epoch;
- Quorum hoặc membership;
- Kiểm tra mốc replication;
- Quy tắc từ chối stale primary;
- Điều kiện phát lại writes chưa rõ commit.

Một thiết kế thiếu fencing có nguy cơ **split-brain**: hai vùng đều nghĩ mình là authority.

## 26. RPO, RTO, consistency và tính bền là những khái niệm riêng

### 26.1. Recovery Point Objective (RPO)

RPO nói về lượng dữ liệu có thể mất khi thảm họa, thường biểu diễn thành khoảng thời gian hoặc mốc dữ liệu chấp nhận mất.

### 26.2. Recovery Time Objective (RTO)

RTO nói về mục tiêu thời gian phục hồi dịch vụ sau sự cố.

### 26.3. Không đánh đồng

Một region A có thể cung cấp strongly consistent reads với writes đã ACK trong A, nhưng dữ liệu chưa replicate sang B. Nếu A mất vĩnh viễn, failover B có thể thiếu một số writes theo mô hình replication/durability.

Ngược lại, một hệ có nhiều bản sao bền vững vẫn có thể trả **stale read** từ một replica chậm.

| Khái niệm | Câu hỏi |
|---|---|
| Consistency | Các client được phép thấy những phiên bản nào, theo thứ tự nào? |
| Atomicity | Một nhóm thao tác có commit như một đơn vị không? |
| Durability | Mutation đã ACK có sống sót khi xảy ra lỗi nào? |
| Availability | Yêu cầu nào tiếp tục được phục vụ khi lỗi? |
| Latency | Thao tác mất bao lâu? |
| RPO | Có thể mất bao nhiêu dữ liệu sau thảm họa? |
| RTO | Mất bao lâu để phục hồi? |

Khi quyết định failover, không thể chỉ nhìn một chỉ số “database up”.

## 27. Khi sử dụng từng NoSQL, hãy hỏi đúng khả năng thực tế

### 27.1. DynamoDB

Các cơ chế có thể liên quan:

- Conditional writes theo item;
- Transaction APIs cho nhiều item trong phạm vi được hỗ trợ;
- Strongly consistent read với những loại đường đọc hỗ trợ;
- GSI có đường cập nhật bất đồng bộ;
- Global tables với cấu hình/kiểu replication và consistency tùy trường hợp.

Suy giảm hợp lý:

- Khi GSI lag, không coi “không tìm thấy qua index” là item không tồn tại.
- Khi conditional inventory write không được xác nhận, không báo reservation thành công.
- Khi vùng xa chưa bắt kịp, tùy use case route read phù hợp hoặc hiển thị trạng thái đang đồng bộ.
- Không mặc định mọi cấu hình global tables có cùng consistency semantics.

### 27.2. MongoDB

Các thành phần phải phân biệt:

- Atomic update một document;
- Read concern, write concern, read preference;
- Causally consistent sessions;
- Multi-document transactions;
- Replica set failover;
- Change streams/search projections.

Suy giảm hợp lý:

- Form profile dùng version/ETag để chống lost update.
- Quyết định chốt đơn không dựa vào secondary read có thể stale.
- Search/projection chậm không đồng nghĩa source write thất bại.
- Không giữ transaction dài trong lúc chờ payment API.

### 27.3. Cassandra

Có:

- Consistency levels theo read/write và data center;
- Regular writes và LWT cho conditional write;
- Anti-entropy repair;
- Tombstone/TTL semantics;
- Mô hình bảng theo access pattern.

Suy giảm hợp lý:

- Chọn CL theo invariant và vùng yêu cầu, không chỉ vì latency.
- Khi không đủ replica/consensus cho LWT, không tự xác nhận claim duy nhất.
- Giao dịch nhiều bảng phi chuẩn hóa cần workflow/đối soát.
- Khi node offline lâu, cần quy trình repair/rebuild an toàn trước khi đưa dữ liệu cũ vào.

### 27.4. Cosmos DB for NoSQL

Có các consistency models như strong, bounded staleness, session, consistent prefix, eventual; đồng thời có transaction scope theo logical partition trong những API hỗ trợ.

Suy giảm hợp lý:

- Giữ session token khi cần read-your-writes;
- Kiểm tra chế độ vùng/multi-write;
- Không coi session consistency là global strong transaction;
- Nếu token chưa được một replica đáp ứng, đợi/route hoặc báo không khả dụng theo hợp đồng, không âm thầm trả dữ liệu cũ rồi vẫn quảng cáo RYW.

### 27.5. Firestore

Có transaction/precondition và consistency theo mô hình sản phẩm; concurrency mode/SDK có thể ảnh hưởng cách lock/retry.

Suy giảm hợp lý:

- Transaction callback không gọi side effect ngoài DB.
- Khi transaction abort vì contention, retry có giới hạn.
- Nếu cache client đang offline, phải phân biệt thay đổi đã ghi local và đã được backend xác nhận.
- Trường hợp nhiều document cần xem transaction boundary thật, không chỉ version trên từng doc.

### 27.6. Redis

Một số thao tác đơn key được thực thi nguyên tử ở server, nhưng replication/failover, durability và TTL có bảo đảm riêng.

Suy giảm hợp lý:

- Dùng Redis như cache fallback cho dữ liệu đủ điều kiện.
- Không coi Redis cache là authority cho ACL hoặc số dư quan trọng.
- Không để lock `SET NX` đơn lẻ trở thành bảo đảm payment exactly-once.
- Khi Redis cache chết, tránh đẩy toàn bộ lượng query sang database nguồn.

### 27.7. Search/vector engines

Search index thường là read model với refresh/ingest lag. Vector similarity có thêm tính gần đúng về retrieval, **khác** consistency của dữ liệu gốc.

Suy giảm hợp lý:

- Tắt semantic ranking khi vector index lỗi;
- Giữ keyword/basic search theo ngân sách;
- Tái kiểm tra quyền và dữ liệu giao dịch ở nguồn;
- Không dùng một kết quả ANN/stale index để chốt điều kiện kinh doanh.

Các mô tả trên là định hướng; **phiên bản, topology, API và tính năng có thể thay đổi**, nên hợp đồng production phải bám đúng hệ đang vận hành.

## 28. Chuyển đổi chế độ bằng feature flags và policy engine

Một service có thể có policy:

~~~yaml
checkout:
  requiredConsistency: authoritative-reservation
  onInventoryUnavailable: reject
  onPaymentUnknown: pending-reconcile

catalog:
  allowStalePublicContent: true
  maxStaleSeconds: 600
  onSearchUnavailable: basic-filter

recommendations:
  onModelUnavailable: popular-public-items

adminActions:
  onAclAuthorityUnavailable: deny
~~~

Đây là **YAML minh họa policy**, không phải file cấu hình được hệ nào tự hiểu.

### 28.1. Tránh tính năng suy giảm không được kiểm soát

Khi bật chế độ:

- Có audit ai/điều kiện nào kích hoạt.
- TTL của feature flag nếu đó là mode khẩn cấp.
- Không có khả năng vượt bypass quyền/cam kết tài chính.
- Có canary/giới hạn theo tenant nếu phù hợp.
- Có cách rollback.
- Có runbook phục hồi.

### 28.2. Tách lỗi dependency khỏi mode sản phẩm

Một lỗi Search API không nhất thiết buộc mọi product endpoint chuyển read-only. Nếu inventory healthy, checkout có thể tiếp tục.

Ngược lại, một lỗi coordinator của inventory có thể khiến checkout dừng dù toàn bộ website vẫn hiển thị bình thường.

## 29. Monitoring: đo thứ người dùng thực sự nhận

### 29.1. Nhóm metric hạ tầng

- Replica/region replication lag;
- Quorum timeout;
- Leader election/failover;
- Transaction commit/abort;
- Database read/write p95/p99;
- Cache hit rate;
- Queue depth và oldest message age;
- Consumer lag;
- Circuit breaker state;
- Load-shed/retry rate;
- Regional error rate.

### 29.2. Nhóm metric nghiệp vụ

- Số reservation trùng hoặc oversell;
- Idempotency duplicate prevented;
- Payment `UNKNOWN` tồn đọng;
- Order `PENDING` quá deadline;
- Số đơn có trạng thái lệch inventory;
- ACL revocation latency;
- Source–projection version gap;
- User vừa ghi nhưng đọc lại bản cũ;
- Số lần hiển thị dữ liệu stale ngoài ngưỡng;
- Compensation/backfill backlog.

**Latency thấp không chứng minh consistency đúng.** Sự cố hiếm nhưng làm trùng charge là vấn đề nghiêm trọng dù availability dashboard vẫn đẹp.

### 29.3. Freshness lag so với guarantee

Một hệ eventual consistency có thể có:

- Mục tiêu p99 projection lag dưới 5 giây.
- Thực tế p99 dao động theo tải.
- Không có hard bound mà database cam kết.

Đây là **SLO vận hành**, không tự biến eventual consistency thành bounded staleness guarantee.

### 29.4. Error budget theo tính năng

Một hệ có thể chấp nhận recommendations downtime nhiều hơn checkout. Phải dùng SLO khác nhau, không lấy availability trung bình toàn site để che việc checkout thường xuyên bị từ chối.

## 30. Chọn phương án theo RTO, RPO và mức hậu quả

### 30.1. Một bảng quyết định mẫu

| Nghiệp vụ | Hậu quả nếu sai | Cho phép stale read? | Khi mất authority | Recovery priority |
|---|---|---|---|---|
| Payment ledger | Mất/nhân đôi tiền | Gần như không cho quyết định tiền | Pending/reconcile, chặn xác nhận | Rất cao |
| Inventory reserve | Oversell | Catalog có thể, reserve không | Reject/waitlist | Cao |
| Quản trị quyền | Lộ dữ liệu/chiếm quyền | Chặt theo policy | Fail closed | Rất cao |
| Tạo username | Trùng danh tính | Không cho claim toàn cục sai | Tạm dừng claim | Cao |
| Cart draft | Mất ý định UX | Có, với đồng bộ rõ | Local draft/queued | Trung bình |
| Product search | Kết quả cũ/thiếu | Có, nếu công khai và trong ngưỡng | Fallback hạn chế | Trung bình |
| Recommendations | Cá nhân hóa kém | Có | Tắt module | Thấp |
| Analytics | Báo cáo chậm | Có, ghi mốc cập nhật | Hiển thị snapshot cũ | Tùy người dùng |

### 30.2. Phân loại theo tác động thay vì tên dịch vụ

“User Profile Service” có thể chứa avatar, ngôn ngữ, địa chỉ giao hàng, thông tin định danh và quyền. Mỗi field có hậu quả khác nhau khi stale.

Vì vậy cần phân loại ở **dữ liệu và hành động**, không chỉ ở service name.

## 31. Phân tích định lượng sơ bộ

### 31.1. Mức khả dụng của chuỗi phụ thuộc

Nếu một request cần A, B, C đều hoạt động và ta giả định lỗi **độc lập** với availability tương ứng `a`, `b`, `c` thì:

\[
P(\text{thành công chuỗi}) \approx a \times b \times c
\]

Ví dụ đơn giản mỗi dependency đạt 99,9% và tất cả bắt buộc:

\[
0.999^3 \approx 0.997003
\]

tức khoảng **99,7003%**, dưới 99,9%.

Đây là phép tính dưới giả định độc lập và mô hình lý tưởng; hệ thực thường có lỗi tương quan, retry, cache, timeout và mối phụ thuộc khác.

### 31.2. Vì sao bỏ dependency phụ giúp availability?

Nếu Recommendations là dependency bắt buộc trong checkout, khi nó lỗi checkout cũng lỗi. Nếu chuyển recommendations sang optional với fallback hợp lệ, nó không còn nằm trên critical path.

Tuy nhiên, **không được tùy tiện loại Inventory/Payment Authority khỏi critical path** vì chúng bảo vệ invariant.

### 31.3. Latency của đường tuần tự

Nếu request gọi ba dependency tuần tự, latency có thể gần:

\[
L_{\text{total}} \approx L_A + L_B + L_C + L_{\text{application}}
\]

Ở thực tế cần xét phân phối latency, network, retry và mức đồng thời. Một đường bắt buộc gọi thêm remote quorum có thể làm tăng p99 đáng kể.

Một giải pháp không phải luôn “chọn consistency yếu hơn”; có thể:

- Gom invariant vào aggregate;
- Giảm số round-trip;
- Dùng transaction native;
- Tách đường read/command;
- Cache dữ liệu không nhạy cảm;
- Chuyển tác vụ phụ sang async;
- Giới hạn phạm vi consensus.

### 31.4. Phân bổ trước quota

Giả sử có 100 slot, A được 60, B được 40:

\[
allocated_A + allocated_B \leq totalCapacity
\]

Nếu không có cấp quota trùng và mỗi vùng không tiêu quá hạn mức được cấp, hệ có thể giữ invariant tổng trong khi mất liên vùng. Chi phí là quota có thể bị “kẹt” ở một vùng khi vùng khác thiếu.

Đây là ví dụ một **thay đổi mô hình quyền ghi** giúp giảm nhu cầu phối hợp thời gian thực.

## 32. Runbook suy giảm: không để đến lúc sự cố mới quyết định

Một runbook tối thiểu cho dependency quan trọng:

### 32.1. Phát hiện

- Chỉ số nào vượt ngưỡng?
- Sự cố tại một node, partition, region hay toàn dịch vụ?
- Đường đọc/ghi nào đang sai consistency?
- Có vi phạm invariant đã phát hiện không?

### 32.2. Khoanh vùng

- Chặn/giới hạn request gây áp lực.
- Cô lập faulty region/dependency.
- Chọn một authority nếu thiết kế cho phép.
- Không cho stale primary tiếp tục ghi sau leader change.
- Tách traffic quan trọng khỏi batch/fallback.

### 32.3. Chuyển mode

- Xác định chức năng tiếp tục.
- Xác định thao tác phải từ chối.
- Có PENDING mode bền vững hay không.
- Phát thông báo rõ ràng cho người dùng.
- Ghi audit thời điểm chuyển.

### 32.4. Theo dõi trong sự cố

- Queue depth/oldest age;
- Number of pending orders;
- Payment unknown count;
- Inventory reservation mismatch;
- Region replication lag;
- ACL revocation delay;
- Error budget consumption;
- Tỷ lệ fallback đúng policy.

### 32.5. Phục hồi

- Chọn authority đúng để reconcile.
- Xác định dữ liệu nào đã commit.
- Replay event theo version/idempotency.
- Repair bản sao và read model.
- Đối soát payment/inventory/order.
- Chuyển traffic dần với canary.
- Chỉ tắt degrade mode khi đủ điều kiện.
- Ghi hậu kiểm và cập nhật runbook.

**Phục hồi availability không đồng nghĩa dữ liệu đã hội tụ chính xác.** Không vội mở lại checkout khi còn split-brain hoặc ledger chưa được đối soát.

## 33. Kiểm thử các kịch bản suy giảm

### 33.1. Network partition giữa hai region

Mô phỏng A và B không liên lạc được trong môi trường kiểm soát. Xác minh:

- Region nào có quyền xác nhận inventory writes?
- Region không có authority trả gì?
- Read-only catalog có hoạt động không?
- Hai vùng có xác nhận cùng một slot không?
- Khi mạng phục hồi, reconcile thế nào?

### 33.2. Mất leader hoặc quorum

- Command quan trọng có bị từ chối khi không đủ điều kiện?
- SDK retry có tạo bão request không?
- Có stale leader tiếp tục nhận write không?
- Fencing/epoch có chặn split-brain không?

### 33.3. Search outage

- Search fallback có làm primary DB quá tải không?
- Có trả nội dung trái ACL qua stale cache không?
- Checkout có bị ảnh hưởng do pool chung không?
- Module recommendation có tắt an toàn không?

### 33.4. Payment timeout sau commit

- Provider đã charge nhưng response mất.
- Client retry cùng idempotency key.
- Không tạo charge thứ hai.
- Order vào PENDING/UNKNOWN rồi được reconcile đúng.
- User không được yêu cầu trả tiền lần hai vô điều kiện.

### 33.5. Queue backlog

- Producer nhanh hơn consumer nhiều lần.
- Hệ có thực hiện load shedding không?
- Khi queue đầy, có từ chối thay vì giả vờ đã tiếp nhận?
- Có DLQ/retry/backoff?
- Sau phục hồi, có xử lý duplicate an toàn?

### 33.6. Replica stale

- Client vừa sửa profile, read ở region khác trả bản cũ.
- Session token có được mang đúng không?
- API xử lý read-your-writes như đã hứa?
- Có fallback authority khi replica chưa bắt kịp?

### 33.7. Quyền vừa bị thu hồi

- Admin revoke quyền ở nguồn.
- Cache/search còn bản cũ.
- API nhạy cảm phải từ chối theo chính sách.
- Không được trả dữ liệu riêng tư từ stale cache.

### 33.8. Chaos testing phải có giới hạn an toàn

Không chạy network partition, kill quorum hay restore snapshot cũ bừa bãi trên production. Cần môi trường test, fake data, phạm vi rõ, rollback và quan sát đủ để đánh giá business invariants.

## 34. Những sai lầm thường gặp

**“Chọn AP thì mọi request phải trả success.”** Sai. CAP availability có định nghĩa lý thuyết, còn API có thể/nhất thiết trả lỗi nghiệp vụ khi bất biến không thỏa.

**“Chọn CP thì toàn website phải tắt khi mất mạng.”** Sai. Có thể chặn critical writes và giữ những reads phụ an toàn.

**“Không có partition thì không có đánh đổi.”** Sai. PACELC nhắc latency/consistency vẫn cần quyết định.

**“Strong consistency làm mọi transaction đa bảng là ACID.”** Sai. Phải xem scope/isolation.

**“Eventual nghĩa là tối đa 1 giây sẽ đồng bộ.”** Không có bound nếu sản phẩm không bảo đảm.

**“Cache stale luôn an toàn.”** Sai với ACL, dữ liệu nhạy cảm, giá chốt, quota hoặc inventory.

**“Search index không thấy item thì item chưa được tạo.”** Sai vì index có thể lag.

**“Chỉ cần đưa checkout vào queue là đã đặt hàng thành công.”** Không. Queue nhận intent không đồng nghĩa inventory/payment đã commit.

**“202 Accepted có thể trả dù request mới nằm trong RAM.”** Không nên nếu hợp đồng hứa durable acceptance.

**“Timeout nghĩa chắc chắn chưa charge.”** Sai. Có thể đã commit và mất phản hồi.

**“Redis lock đảm bảo payment exactly-once.”** Không. Cần idempotency và tài nguyên đích bảo vệ.

**“Hai vùng cùng xác nhận username rồi LWW giải quyết là đủ.”** Không nếu hợp đồng yêu cầu chỉ một request từng được xác nhận.

**“Khôi phục kết nối là dữ liệu tự đúng.”** Không. Cần conflict resolution, replay, repair và reconciliation.

**“Tăng retry giúp availability.”** Không luôn; retry storm có thể đẩy toàn hệ quá tải.

**“Fallback search bằng full scan là miễn phí.”** Có thể kéo sập DB nguồn.

**“Feature flag degrade mode là đủ, không cần runbook.”** Sai. Cần trigger, audit, TTL, điều kiện phục hồi và kiểm thử.

**“Có 99,9% uptime là không bao giờ vi phạm invariant.”** Uptime không đo tính đúng nghiệp vụ.

**“Một mức consistency có thể áp dụng cho mọi dữ liệu.”** Chi phí và hậu quả sai khác nhau theo use case.

**“Có thể đánh đổi quyền riêng tư để giữ conversion.”** Không nên bỏ kiểm tra quyền bắt buộc khi thiếu authority.

**“Chỉ cần mở lại traffic khi health check xanh.”** Chưa đủ nếu còn backlog, stale replicas, unknown payments hoặc split-brain.

## 35. Quy trình thiết kế theo từng bước

### Bước 1 — Chọn một user journey cụ thể

Ví dụ “Tìm sản phẩm → thêm giỏ → đặt hàng → thanh toán → theo dõi”.

Không chọn phương án degrade từ tên database đơn lẻ.

### Bước 2 — Liệt kê các trạng thái và side effect

- Product được hiển thị;
- Cart intent;
- Inventory reserved;
- Order created;
- Payment requested;
- Payment confirmed;
- Shipment created;
- Notification sent.

### Bước 3 — Viết bất biến

- Không reserve quá số lượng được phép.
- Không tạo hai order confirmed cho cùng request ID.
- Không xác nhận payment khi chưa có bằng chứng.
- Không giao hàng cho order không hợp lệ.
- Không trả dữ liệu ngoài quyền.

### Bước 4 — Chọn authority và transaction boundary

Với mỗi invariant, hỏi:

- Nằm trong một item/partition không?
- Có conditional write không?
- Có multi-item transaction phù hợp không?
- Nếu vượt nhiều service, dùng saga/ledger/outbox thế nào?
- Multi-region có một authority hay nhiều writers?
- Read model nào có thể stale?

### Bước 5 — Viết ma trận suy giảm

Cho từng dependency failure:

- Fail closed hay tiếp tục?
- Cache/replica nào được dùng?
- Staleness tối đa là gì?
- Có durable pending path không?
- UX/status code là gì?
- Khi phục hồi phải reconcile gì?

### Bước 6 — Gắn SLO và risk budget

- Checkout correctness;
- Payment duplicate rate;
- Search fallback p95;
- Projection lag p99;
- ACL revoke latency;
- Pending time;
- RPO/RTO;
- Capacity và lỗi khi degrade.

### Bước 7 — Triển khai guardrails

- Circuit breaker;
- Timeouts;
- Retry budgets;
- Idempotency;
- Feature flags;
- Load shedding;
- Bulkheads;
- Version/fencing;
- Monitoring;
- Audit.

### Bước 8 — Diễn tập

Test partition, failover, unknown commit, queue lag, stale cache và phục hồi. Kiểm tra cả **trạng thái cuối cùng** và các phản hồi mà client nhìn thấy trong sự cố.

## 36. Bài tập thực hành

### Bài tập 1 — Catalog hay thanh toán?

Product DB chậm nhưng cache còn mô tả và giá từ 5 phút trước.

**Câu hỏi:** Có nên hiển thị sản phẩm không? Có nên dùng chính giá cache để chốt tiền không?

**Gợi ý:** Có thể hiển thị một phần nếu policy chấp nhận stale và quyền hợp lệ; giá tính tiền cần xác nhận qua cơ chế quote/authority phù hợp.

### Bài tập 2 — Tồn kho cuối cùng

Hai region mất liên lạc, mỗi bên có cache `available=1` cho cùng SKU.

**Câu hỏi:** Có thể cho cả hai region xác nhận bán một sản phẩm cuối không?

**Gợi ý:** Không nếu invariant không oversell. Cần authority/quota độc lập được cấp trước hoặc từ chối một phần.

### Bài tập 3 — Payment unknown

Provider đã charge nhưng response mất. Client thấy timeout và muốn bấm lại.

**Câu hỏi:** API nên trả trạng thái gì và cần cơ chế nào?

**Gợi ý:** UNKNOWN/PENDING, idempotency key, tra cứu provider/reconciliation; không tạo charge mới vô điều kiện.

### Bài tập 4 — Search outage

Search index lỗi, backend dự kiến chuyển tất cả queries thành full scan 20 triệu documents.

**Câu hỏi:** Vì sao đây có thể là một fallback nguy hiểm?

**Gợi ý:** Tải lên primary DB, độ trễ, contention, ảnh hưởng checkout. Cần fallback có giới hạn hoặc tạm tắt tìm kiếm.

### Bài tập 5 — Read-your-writes

User đổi địa chỉ thành công rồi reload qua cache và thấy địa chỉ cũ.

**Câu hỏi:** Có cách nào giữ UX mà không bắt mọi query toàn hệ dùng strong consistency?

**Gợi ý:** Bypass cache key vừa sửa, session token, direct authoritative read hoặc trả bản ghi từ response write.

### Bài tập 6 — ACL revoke

Admin thu hồi quyền; region khác giữ ACL cũ 30 giây.

**Câu hỏi:** Nếu một API đọc dữ liệu riêng tư trong khoảng đó, có được fail open không?

**Gợi ý:** Với yêu cầu revoke ngay, phải kiểm tra authority/revocation epoch hoặc fail closed.

### Bài tập 7 — Pending queue

Order API đã trả `202 Accepted` nhưng message chỉ nằm trong memory của pod. Pod crash.

**Câu hỏi:** Lỗi hợp đồng là gì?

**Gợi ý:** Yêu cầu chưa được lưu bền vững mà API đã xác nhận tiếp nhận; phải có durable queue/intent hoặc từ chối.

### Bài tập 8 — Quorum và availability

RF=3, yêu cầu quorum=2, chỉ một replica còn liên lạc. Một critical write cần quorum.

**Câu hỏi:** Có nên hạ xuống ONE để luôn trả success?

**Gợi ý:** Không tự động. Phải xét invariant, stale/conflicting writes, durability và hợp đồng; có thể từ chối hoặc dùng pending path an toàn.

### Bài tập 9 — Multi-region quota

Total capacity là 100, region A được 60 và B được 40. A hết quota, B còn 20 nhưng mạng bị chia cắt.

**Câu hỏi:** Tại sao A vẫn phải ngừng bán dù tổng còn hàng?

**Gợi ý:** Đó là cái giá của phân bổ trước quyền ghi; A không được tự dùng quota của B khi chưa có chuyển giao an toàn.

### Bài tập 10 — Failover leader

A không trả heartbeat; B được bầu leader. A vẫn chạy và nhận write.

**Câu hỏi:** Điều gì ngăn split-brain?

**Gợi ý:** Leader term/epoch, fencing/quorum và kiểm tra ở nơi commit, không chỉ health check.

### Bài tập 11 — Analytics stale

Dashboard lấy dữ liệu đến 08:30 nhưng hiển thị “Doanh thu hiện tại”.

**Câu hỏi:** Vấn đề gì?

**Gợi ý:** UX tuyên bố mức freshness không được bảo đảm. Cần watermark/nhãn dữ liệu chưa cập nhật.

### Bài tập 12 — Retry storm

Backend lỗi 5 giây. Mỗi client retry ngay 10 lần, gây tăng tải gấp nhiều lần.

**Câu hỏi:** Biện pháp nào phù hợp?

**Gợi ý:** Backoff+jitter, retry budget, circuit breaker, rate limiting, load shedding và idempotency.

### Bài tập 13 — Cross-service atomicity

Inventory reservation đã commit, tạo order thất bại.

**Câu hỏi:** Một atomic conditional update inventory có đủ cho toàn workflow không?

**Gợi ý:** Không. Cần transaction đa item nếu cùng phạm vi hoặc saga/compensation/reconciliation.

### Bài tập 14 — Monotonic reads

Client thấy order status `SHIPPED`, đổi region rồi thấy `PAID` cũ.

**Câu hỏi:** Điều nào bị ảnh hưởng và cách giảm?

**Gợi ý:** Monotonic reads trong session; dùng session token/version routing hoặc đảm bảo read path phù hợp.

### Bài tập 15 — Độ mới dữ liệu

Service báo “99% projections trong 2 giây” nhưng vài request chậm 1 phút.

**Câu hỏi:** Đây có phải bounded staleness guarantee 2 giây không?

**Gợi ý:** Không. Đó là percentile SLO, không có hard bound cho tất cả truy vấn.

### Bài tập 16 — CAP và định nghĩa availability

Một node trả lỗi 503 vì không thể đạt quorum thay vì trả dữ liệu sai.

**Câu hỏi:** Trong mô hình CAP, điều gì đang được đánh đổi? Có thể nói toàn hệ thống 0% uptime không?

**Gợi ý:** Từ chối một số operation để bảo vệ C; CAP availability khác uptime sản phẩm, các chức năng khác vẫn có thể hoạt động.

### Bài tập 17 — Circuit breaker trên Payment

Provider lỗi, circuit breaker mở. Developer muốn fallback bằng cách lưu `paymentStatus=SUCCEEDED` và reconcile sau.

**Câu hỏi:** Vì sao không phù hợp?

**Gợi ý:** Không có bằng chứng thu tiền. Dùng PENDING/UNKNOWN và workflow xác minh.

### Bài tập 18 — Cache quyền và cache public

Hai cache đều stale 5 phút: A chứa ảnh sản phẩm public, B chứa quyền admin.

**Câu hỏi:** Có nên dùng chung stale policy?

**Gợi ý:** Không. Dữ liệu public có thể stale trong giới hạn; ACL nhạy cảm cần bảo vệ chặt hơn.

### Bài tập 19 — Tính availability chuỗi

Một request phải đi qua ba dependency bắt buộc độc lập, mỗi dependency có xác suất hoạt động 0,999 tại thời điểm xét.

**Câu hỏi:** Xác suất đơn giản cho chuỗi là bao nhiêu?

**Gợi ý:** \(0.999^3 \approx 0.997003\). Giả định độc lập hiếm khi hoàn toàn đúng thực tế.

### Bài tập 20 — Quy trình khôi phục

Mạng liên vùng đã trở lại, metrics HTTP 200 bình thường, nhưng vẫn còn 1.000 `PENDING_PAYMENT` và projection lag 10 phút.

**Câu hỏi:** Có nên tuyên bố sự cố kết thúc hoàn toàn?

**Gợi ý:** Chưa. Cần reconcile payment, kiểm tra backlog/projection và invariant trước khi xác nhận dữ liệu hội tụ và tắt chế độ suy giảm.

## 37. Checklist trước khi áp dụng vào production

- [ ] Đã xác định user journeys và hành động nhạy cảm.
- [ ] Đã ghi rõ invariant không được vi phạm.
- [ ] Đã phân loại dữ liệu nào được stale, bao lâu, trong ngữ cảnh nào.
- [ ] Đã chọn authority/transaction boundary cho mỗi invariant.
- [ ] Đã hiểu CAP availability khác uptime và CAP C khác ACID C.
- [ ] Đã xem latency/consistency trade-off khi không có partition.
- [ ] Đã phân biệt per-key/per-partition/per-session/per-region guarantees.
- [ ] Đã thiết kế fallback riêng theo tính năng, không một mode toàn hệ.
- [ ] Không có fallback nào bỏ kiểm tra tiền, tồn kho hoặc quyền bắt buộc.
- [ ] Pending path có durable storage, operation ID và status API.
- [ ] Request timeout/unknown commit có idempotency/reconciliation.
- [ ] Cache stale có freshness metadata và chính sách phân quyền.
- [ ] Search fallback có giới hạn tải, không kéo sập source DB.
- [ ] Circuit breaker và retry phân biệt business conflict với infrastructure failure.
- [ ] Có backpressure, queue capacity và load shedding.
- [ ] Có bulkhead bảo vệ core commands khỏi tính năng phụ.
- [ ] Đã xét multi-region authority, fencing, failover và conflict resolution.
- [ ] Đã thống nhất RPO/RTO, latency và visibility contracts.
- [ ] API/UX không trả `SUCCESS` khi mới tiếp nhận yêu cầu.
- [ ] Có watermark và version cho read models quan trọng.
- [ ] Có metric về correctness, pending, freshness và compensation.
- [ ] Runbook định nghĩa trigger, action, owner, recovery gate và audit.
- [ ] Đã diễn tập network partition, unknown commit, provider outage và region failover.
- [ ] Đã đối soát sau phục hồi, không chỉ dựa trên health check xanh.

## 38. Tổng kết

Định lý CAP giúp nhận ra rằng khi một mạng phân tán bị chia cắt, hệ không thể luôn vừa duy trì **tính nhất quán mạnh theo mô hình CAP** vừa bảo đảm mọi yêu cầu tới node còn hoạt động đều được phục vụ thành công. Nhưng quyết định kiến trúc thực tế không dừng ở việc gắn nhãn CP hoặc AP. Còn cần đánh giá **latency, durability, phạm vi transaction, region, read models, khả năng phục hồi và chi phí vận hành**.

Phương án tốt nhất phụ thuộc vào **ý nghĩa nghiệp vụ của dữ liệu**:

- Với tiền, quyền, tồn kho và uniqueness, ưu tiên authority/conditional write/transaction phù hợp; khi thiếu điều kiện xác nhận phải **fail closed hoặc pending một cách trung thực**.
- Với catalog, nội dung công khai, search và recommendations, có thể **dùng cache stale có giới hạn, fallback đơn giản hoặc tắt module phụ** để giữ trải nghiệm hữu ích.
- Với workflow trải nhiều service, cần **idempotency, outbox/saga, version guard, retry có giới hạn và reconciliation**; một lock hoặc một write thành công chưa đủ.
- Với multi-region, cần mô tả ai được commit, vùng nào có thể stale, cách ngăn split-brain và cách phục hồi sau khi mạng trở lại.

**Suy giảm dịch vụ đúng không phải là che giấu lỗi.** Nó là thiết kế trước cách tiếp tục cung cấp giá trị mà không vi phạm những điều bắt buộc phải đúng, kèm trạng thái minh bạch, giám sát và đường phục hồi có thể kiểm chứng.

**Nguyên tắc cuối cùng:** hãy quyết định *điều gì được phép cũ, điều gì được phép chờ, điều gì bắt buộc phải từ chối* dựa trên hậu quả nghiệp vụ — rồi mới chọn consistency level, database mechanism và fallback tương ứng.

