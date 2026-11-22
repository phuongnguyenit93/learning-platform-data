# Thiết kế từ đầu: yêu cầu, giả định, phương án và quyết định

Thiết kế kiến trúc đám mây không bắt đầu bằng câu hỏi “dùng Kubernetes hay serverless?”, mà bắt đầu bằng **hệ thống cần giải quyết vấn đề gì, điều gì chưa biết và tổ chức sẵn sàng đánh đổi những gì**. Hai kiến trúc có cùng chức năng có thể khác nhau hoàn toàn vì yêu cầu độ tin cậy, tính nhất quán dữ liệu, tốc độ phát triển, năng lực đội ngũ, quy định và ngân sách khác nhau.

Bài thực hành này thuộc chủ đề **Thực hành thiết kế** của CLOUD_ARCHITECTURE. Người học sẽ đi từ bối cảnh nghiệp vụ đến lựa chọn mạng, compute, dữ liệu, tích hợp và mô hình triển khai; so sánh các phương án, ghi lại quyết định có căn cứ và tự đánh giá kết quả theo những nguyên tắc Well-Architected.

**Kết quả mong đợi:** sau bài, người học có thể tạo một bản thiết kế có thể phản biện, bao gồm:

1. Bảng yêu cầu có nguồn, mức ưu tiên, chỉ số nghiệm thu và giới hạn phạm vi.
2. **Assumption register** nêu rõ điều chưa biết, ảnh hưởng nếu sai, cách kiểm chứng và người chịu trách nhiệm.
3. Ít nhất hai phương án kiến trúc khả thi cùng các đánh đổi về độ tin cậy, bảo mật, hiệu năng, chi phí, vận hành và tiến độ.
4. Sơ đồ ngữ cảnh, sơ đồ thành phần và mô tả các luồng dữ liệu quan trọng.
5. Một hoặc nhiều **ADR** (Architecture Decision Record) giải thích quyết định, phương án bị loại và điều kiện xem xét lại.
6. Kế hoạch xác minh bằng đo tải, kiểm thử lỗi, phục hồi, bảo mật và nghiệm thu nghiệp vụ.

Nội dung gồm **đề bài** để tự giải và **lời giải tham khảo** để đối chiếu. Không có một sơ đồ duy nhất đúng cho mọi tổ chức. Một phương án tốt cần cho thấy giả định nào đang giữ cho quyết định có hiệu lực và bằng chứng nào có thể khiến nhóm thay đổi lựa chọn.

## 1. Quy trình tư duy: từ yêu cầu đến bằng chứng

~~~mermaid
flowchart LR
    B["Bối cảnh & mục tiêu nghiệp vụ"] --> R["Yêu cầu đo được"]
    R --> A["Giả định & điều chưa rõ"]
    A --> C["Ràng buộc & phương án"]
    C --> T["Đánh đổi / quyết định ADR"]
    T --> D["Sơ đồ & thiết kế chi tiết"]
    D --> V["Thử nghiệm / review"]
    V -->|"Có dữ liệu mới"| A
    V -->|"Đạt tiêu chí"| G["Chấp thuận & triển khai theo giai đoạn"]
~~~

Quy trình này có vòng lặp. Ví dụ, đo tải chứng minh database trở thành nút thắt thì nhóm quay lại cân nhắc cache, truy vấn, cấu trúc dữ liệu hoặc tách workload. Quyết định ban đầu là **giả thuyết kiến trúc có thể kiểm chứng**, không phải cam kết bất biến.

### 1.1. Phân biệt bốn loại thông tin

| Loại | Cách hiểu | Ví dụ |
|---|---|---|
| **Requirement — yêu cầu** | Điều hệ thống phải đáp ứng và có người chấp nhận | Khách đặt hàng thành công dù có nhiều lượt truy cập |
| **Constraint — ràng buộc** | Điều không thể tùy ý thay đổi trong phạm vi hiện tại | Phải dùng nhà cung cấp thanh toán đã ký hợp đồng |
| **Assumption — giả định** | Điều tạm coi là đúng nhưng chưa có đủ bằng chứng | Hơn 90% lượt xem catalog có thể cache |
| **Decision — quyết định** | Lựa chọn có căn cứ sau khi cân nhắc phương án | Dùng ứng dụng modular monolith cho bản phát hành đầu |

Phân loại sai làm chất lượng thiết kế suy giảm. Chẳng hạn, “phải dùng microservices” có thể chỉ là một **sở thích công nghệ**, chưa phải requirement; “hệ thống cần chịu lỗi một Availability Zone” là yêu cầu có thể kiểm tra nếu đã được chủ sản phẩm duyệt.

## 2. Đề bài: thiết kế nền tảng bán hàng cho chuỗi cửa hàng

Một doanh nghiệp bán lẻ có **120 cửa hàng vật lý**, dự kiến mở kênh đặt hàng trực tuyến kết hợp giao hàng và nhận tại cửa hàng. Nhóm muốn ra mắt bản đầu trong **6 tháng** với một đội gồm 8 lập trình viên, 2 kỹ sư hạ tầng/vận hành và quyền sử dụng cloud công cộng. Hệ thống quản lý tồn kho tại cửa hàng (ERP) hiện có API nhưng sẽ tiếp tục chạy tại trung tâm dữ liệu ít nhất hai năm.

Đối tượng sử dụng gồm khách hàng, nhân viên cửa hàng, bộ phận chăm sóc khách hàng và quản trị hệ thống. Ứng dụng cần hỗ trợ tìm sản phẩm, xem giá, giỏ hàng, đặt đơn, thanh toán qua đối tác, tra cứu trạng thái đơn và yêu cầu hủy/hoàn tiền theo quy trình kinh doanh.

### 2.1. Số liệu đầu vào do doanh nghiệp cung cấp

| Mục | Giá trị dùng trong bài tập | Ghi chú |
|---|---|---|
| Cửa hàng | 120 | Cửa hàng có tồn kho và khả năng xử lý đơn khác nhau |
| Danh mục | Khoảng 12.000 SKU | Giá và khuyến mãi thay đổi theo chiến dịch |
| Đơn hàng trung bình | 45.000 đơn/ngày | Cần xác minh từ dự báo kinh doanh |
| Cao điểm duyệt sản phẩm | 1.200 request/giây | Là tổng request qua CDN, không phải lưu lượng tới API gốc |
| Cao điểm checkout | 60 lượt thử checkout/giây trong 5 phút | “Thử” không đồng nghĩa 60 đơn đã thanh toán thành công |
| Tỷ lệ đọc so với ghi | Đọc chiếm đa số | Chưa có phân bố theo endpoint |
| Phạm vi triển khai đầu | Một quốc gia, một cloud region | Cần làm rõ yêu cầu lưu trú dữ liệu |
| Thời gian ra mắt | 6 tháng | Ràng buộc năng lực đội và phạm vi tính năng |
| ERP tồn kho | On-premises, có API | Thời gian đáp ứng và độ sẵn sàng chưa đo |
| Thanh toán | Qua đối tác PSP | Không lưu thông tin thẻ gốc trong ứng dụng |

Đây là **dữ liệu giả lập có mục đích sư phạm**, không phải số liệu của một doanh nghiệp thật. Tất cả ngưỡng sau đây phải được xem là đề xuất chờ phê duyệt trong một dự án thực tế.

### 2.2. Yêu cầu chức năng tối thiểu

- Khách có thể xem danh mục, tìm sản phẩm, xem giá theo cửa hàng và thêm vào giỏ hàng.
- Khách có thể đặt đơn với một lựa chọn nhận hàng cụ thể; hệ thống tránh tạo đơn hoặc ghi nhận thanh toán trùng khi người dùng bấm nhiều lần.
- Chỉ xác nhận số lượng hàng sau khi đã kiểm tra/giữ tồn kho theo hợp đồng với ERP hoặc dịch vụ quản lý dự trữ được ủy quyền.
- Khách xem được trạng thái đơn; nhân viên được cấp quyền có thể thực hiện thay đổi hợp lệ có audit.
- Thanh toán, hủy và hoàn tiền có trạng thái rõ ràng; sự kiện từ PSP có thể đến muộn hoặc lặp lại.
- Bộ phận vận hành xem được tình hình đặt hàng và nhận cảnh báo khi luồng kinh doanh quan trọng gặp lỗi.

### 2.3. Câu hỏi người học phải tự làm rõ

Trước khi giải kiến trúc, hãy ghi lại các câu hỏi và giả định:

1. Số lượng sản phẩm có được phép **bán vượt tồn** trong trường hợp ERP không phản hồi không?
2. Khách chấp nhận chờ bao lâu để nhận xác nhận đơn? Mốc thời gian bắt đầu và kết thúc đo là gì?
3. Khi PSP đã thu tiền nhưng dịch vụ đặt đơn mất kết nối, ai tra soát và giải quyết?
4. ERP có hỗ trợ **reservation với TTL và mã idempotency** không? Rate limit và độ trễ thực tế thế nào?
5. Có cần hệ thống phục vụ khi **một vùng cloud mất hoàn toàn** ngay ở bản đầu không, hay chấp nhận khôi phục thủ công trong thời gian đã duyệt?
6. Doanh nghiệp chịu được mất tối đa bao nhiêu dữ liệu đơn hàng, và RTO/RPO được đo cho loại sự cố nào?
7. Dữ liệu cá nhân và bản ghi giao dịch được phép lưu ở đâu, lưu bao lâu, ai có quyền truy cập?
8. Thương mại điện tử cần tách team theo domain ngay hay ưu tiên đơn giản để kịp sáu tháng?

Không tự chọn câu trả lời thuận tiện rồi ghi như yêu cầu đã xác thực. Trong thực tế, những câu hỏi trên là nội dung của cuộc họp discovery với business owner, ERP owner, PSP, security và operations.

### 2.4. Nhiệm vụ đầu ra

**Trong 90–120 phút**, hãy làm bản thiết kế ban đầu với bốn phần: bảng requirement; giả định/rủi ro; hai hoặc ba phương án; một quyết định và kế hoạch xác minh. Sau đó dùng lời giải tham khảo từ mục 7 trở đi để đánh giá.

Thời gian là gợi ý cho workshop, không phải hạn bắt buộc. Mỗi nhóm nên trình bày **một trade-off khó nhất** cùng giả định sẽ làm thay đổi quyết định.

## 3. Bước 1 — Chuyển nhu cầu thành yêu cầu có thể nghiệm thu

Yêu cầu chất lượng nên có tác nhân, điều kiện và phản hồi đo được. “Nhanh”, “bảo mật”, “có HA” hoặc “mở rộng vô hạn” đều quá mơ hồ.

| ID | Yêu cầu được đề xuất cho ví dụ | Cách đo/chấp nhận | Ưu tiên |
|---|---|---|---|
| F-01 | Tìm và xem sản phẩm, cập nhật giỏ hàng, đặt đơn, tra cứu đơn | Bộ kịch bản end-to-end nghiệp vụ | Must |
| F-02 | Không nhân đôi đơn hoặc yêu cầu thu tiền do thao tác retry | Kiểm thử cùng một idempotency key qua nhiều lần gửi | Must |
| F-03 | Không xác nhận bán khi chưa có quyền giữ hàng hợp lệ | Kiểm thử tranh chấp tồn kho và lỗi ERP | Must |
| Q-01 | Checkout sẵn sàng **99,95% theo tháng**, loại trừ theo thỏa thuận đã chốt | Synthetic checks và SLI từ luồng checkout thực | Must |
| Q-02 | p95 latency trang catalog **≤ 300 ms** từ edge/CDN tại thị trường mục tiêu | Kiểm thử tải + đo RUM theo loại kết nối | Should |
| Q-03 | p95 xử lý API checkout nội bộ **≤ 800 ms**, chưa tính thao tác thanh toán do PSP kiểm soát | Load test có phân rã latency | Should |
| Q-04 | Chịu đỉnh **60 checkout attempts/s trong 5 phút** và **1.200 request/s đọc catalog** | Test tải đột biến có phân bố traffic thực tế | Must |
| Q-05 | Với mất toàn region: mục tiêu khôi phục **RTO ≤ 60 phút, RPO ≤ 5 phút** | Diễn tập DR có đối soát sau khôi phục | Đề xuất, cần phê duyệt |
| Q-06 | Không lưu số thẻ/PAN, bảo vệ dữ liệu cá nhân và audit thao tác quản trị | Review luồng dữ liệu, quyền, log và kiểm thử | Must |
| Q-07 | Triển khai bản đầu trong **6 tháng** và không vượt năng lực đội hiện có | Kế hoạch mốc, phụ thuộc, mức hoàn thành và chi phí vận hành | Must |

Các ngưỡng ở Q-01 đến Q-05 chỉ có ý nghĩa khi **định nghĩa đúng SLI**, cửa sổ tính, đối tượng đo, điều kiện loại trừ và người chấp nhận. Ví dụ, 99,95% của một tháng 30 ngày tương đương khoảng **21,6 phút thời gian không đáp ứng mục tiêu** nếu đo trên cơ sở thời gian. Đây là ngân sách sai số minh họa, không phải giấy phép cho mọi loại lỗi; các SLI dựa trên tỷ lệ yêu cầu có công thức khác.

### 3.1. Tách chức năng khỏi đặc tính chất lượng

**“Lưu đơn hàng”** là chức năng; **“không mất đơn đã xác nhận khi lỗi một node”** là độ tin cậy; **“khách không thấy đơn của người khác”** là kiểm soát truy cập; **“luồng đặt hàng có thể khôi phục trong 60 phút khi cả region không dùng được”** là mục tiêu DR. Mỗi loại dẫn tới cơ chế thiết kế và cách kiểm thử khác nhau.

### 3.2. Gắn nguồn và người quyết định

Mẫu bảng yêu cầu nên có các cột: ID, statement, source, stakeholder/owner, priority, acceptance criteria, status (*proposed/approved/challenged*) và link tới test/ADR. Nếu chưa có chủ sở hữu duyệt, đánh dấu **proposed**. Các quyết định kiến trúc dựa vào yêu cầu chưa duyệt phải được coi là có rủi ro.

### 3.3. Xác định ngoài phạm vi

Trong bản đầu, giả định chưa thiết kế chương trình khách hàng thân thiết, marketplace cho bên thứ ba, đa quốc gia, gợi ý ML thời gian thực hoặc thay ERP. Đưa **out-of-scope** vào tài liệu giúp tránh một sơ đồ tự phình to và đánh giá sai chi phí/tiến độ.

## 4. Bước 2 — Quản lý giả định và điều chưa biết

Giả định nên được viết theo cấu trúc: **tạm tin điều gì → ảnh hưởng nếu sai → cách xác thực → người phụ trách → hạn xác thực**.

| ID | Giả định minh họa | Nếu sai thì sao? | Phép kiểm chứng / owner |
|---|---|---|---|
| A-01 | CDN có thể phục vụ ≥ 90% request xem catalog ở cao điểm | Origin/API và database phải gánh tải lớn hơn dự kiến | POC cache + đo hit ratio / Web lead |
| A-02 | ERP hỗ trợ reservation an toàn, idempotent, có timeout rõ | Có nguy cơ oversell hoặc phải đổi quy trình checkout | Thử API và hợp đồng ERP / ERP owner |
| A-03 | PSP hỗ trợ payment intent, idempotency và webhook xác minh được | Retry có thể tạo phí hoặc giao dịch trùng | Sandbox + tài liệu hợp đồng / Payment lead |
| A-04 | Một region, nhiều AZ đáp ứng mục tiêu bản đầu | Cần thêm active-passive/multi-region và ngân sách | BIA, DR workshop / Business owner |
| A-05 | Team vận hành được nền tảng compute managed | Hệ số vận hành, sự cố và bảo trì cao hơn | Pilot deploy, on-call drill / SRE lead |
| A-06 | Dữ liệu khách hàng được lưu trong region đã chọn | Có thể phải thay topology, lưu trữ và chính sách | Data classification/legal review / Security |
| A-07 | Peak checkout 60 attempts/s chỉ kéo dài 5 phút | Cần tăng capacity, quota và ngân sách | Dự báo campaign, load profile / Product |

Không phải giả định nào cũng có tác động như nhau. Ưu tiên kiểm chứng giả định có **hệ quả lớn và độ tin cậy thấp**. Chẳng hạn A-02 quyết định tính đúng đơn hàng, cần được kiểm trước khi chốt sơ đồ dịch vụ; A-01 quyết định kích thước cache và origin, có thể điều chỉnh sau load test.

### 4.1. Ma trận phân loại rủi ro đơn giản

| Tác động nếu sai | Độ tin cậy cao | Độ tin cậy thấp |
|---|---|---|
| **Cao** | Theo dõi, kiểm chứng ở mốc quan trọng | **Spike/POC sớm, chặn quyết định phụ thuộc** |
| **Thấp** | Ghi nhận, review định kỳ | Xác minh khi tối ưu hoặc trước triển khai |

Đừng biến “assumption register” thành nơi chứa lý do biện minh sau khi đã chọn sản phẩm. Nếu một giả định bị bác bỏ, hãy ghi thay đổi, cập nhật ADR và tác động lên phạm vi.

## 5. Bước 3 — Xác định ranh giới nghiệp vụ, dữ liệu và trạng thái

Kiến trúc cần giải được hành trình đặt hàng từ góc nhìn người dùng và các bất biến (invariant) nghiệp vụ. Chọn ranh giới domain trước khi chọn số lượng container.

### 5.1. Bản đồ năng lực nghiệp vụ

| Domain | Trách nhiệm chính | Dữ liệu sở hữu |
|---|---|---|
| **Catalog** | SKU, mô tả, ảnh, giá hiển thị, phân loại sản phẩm | Dữ liệu đọc và bản sao được đồng bộ có thời điểm |
| **Cart** | Giỏ của khách chưa xác nhận | Cart/session có TTL, không phải đơn hàng đã chốt |
| **Checkout/Orders** | Tạo và quản lý vòng đời đơn, idempotency, trạng thái | Đơn hàng, dòng hàng, snapshot giá, lịch sử trạng thái |
| **Inventory integration** | Kiểm tra/giữ/giải phóng tồn kho thông qua ERP | Reservation ID, trạng thái đồng bộ và kết quả đối soát |
| **Payment integration** | Tạo payment intent, nhận webhook, đối soát thanh toán | Payment reference, trạng thái và sự kiện; không lưu PAN |
| **Fulfillment** | Chuyển đơn tới cửa hàng, theo dõi chuẩn bị/giao hàng | Lịch sử xử lý và các mốc giao nhận |
| **Identity & access** | Xác thực khách và quyền nhân viên | Danh tính, vai trò, liên kết tài khoản |

Các domain không nhất thiết phải tương ứng **một microservice cho mỗi domain**. Với đội nhỏ và mốc ra mắt sáu tháng, có thể đặt chúng thành module có hợp đồng rõ ràng trong một ứng dụng triển khai thống nhất, sau đó tách khi có bằng chứng về nhu cầu tự mở rộng, cô lập lỗi hoặc quyền sở hữu đội.

### 5.2. Các bất biến phải giữ

1. **Không xử lý một yêu cầu checkout như hai đơn độc lập** khi người dùng retry cùng idempotency key.
2. **Đơn đã xác nhận** phải gắn với quyết định giữ hàng hợp lệ hoặc quy tắc backorder đã được duyệt.
3. **Không tuyên bố đã thanh toán** chỉ vì trình duyệt chuyển hướng thành công; phải dùng trạng thái đáng tin cậy từ PSP và đối soát.
4. **Mọi chuyển trạng thái** quan trọng có nguồn sự kiện, timestamp, actor và không thể nhảy sang trạng thái bất hợp lệ.
5. **Không lộ dữ liệu liên khách hàng hoặc cửa hàng** qua API, cache, hàng đợi, log và báo cáo.

Đây là những ràng buộc mạnh hơn tên dịch vụ cụ thể. Một sơ đồ đẹp nhưng không giải thích được cách giữ các bất biến ở trên vẫn là thiết kế chưa hoàn chỉnh.

### 5.3. Sơ đồ ngữ cảnh hệ thống

~~~mermaid
flowchart LR
    Customer["Khách hàng"] --> Shop["Nền tảng đặt hàng cloud"]
    Staff["Nhân viên cửa hàng"] --> Shop
    Ops["Vận hành / hỗ trợ"] --> Shop
    Shop <-->|"Giữ hàng, kiểm tra tồn"| ERP["ERP on-premises"]
    Shop <-->|"Payment intent, webhook"| PSP["Đối tác thanh toán"]
    Shop --> Notify["Dịch vụ email/SMS"]
~~~

Hệ ERP và PSP nằm ngoài ranh giới quyền kiểm soát của ứng dụng. Cần ghi **hợp đồng, timeout, quota, retry, cơ chế xác thực, trách nhiệm xử lý sự cố và chủ sở hữu** của mỗi tích hợp.

## 6. Bước 4 — Đề xuất và so sánh phương án

Trước khi chọn, nhóm nên trình bày ít nhất hai lựa chọn có khả năng đáp ứng các yêu cầu “Must”. Không cần nêu mười kiến trúc hình thức để chứng minh đã cân nhắc.

### Phương án A — Modular monolith trên compute managed

Một API ứng dụng chia module rõ theo domain; vận hành bằng container hoặc application platform managed, có autoscaling và triển khai đa AZ. Dữ liệu giao dịch nằm trong relational database managed; cache/CDN phục vụ truy vấn đọc; worker bất đồng bộ xử lý sự kiện từ **transactional outbox** và queue. Hệ thống tích hợp ERP/PSP theo các adapter.

**Ưu điểm:** phát triển, kiểm thử nhất quán dữ liệu và vận hành ban đầu đơn giản hơn; ít hợp đồng giữa dịch vụ; phù hợp đội nhỏ và deadline. **Rủi ro:** cùng một runtime/deployment có thể khuếch đại lỗi, tự mở rộng độc lập từng module khó, cần giữ ranh giới module để tránh coupling.

### Phương án B — Microservices theo domain, tích hợp bằng event

Catalog, Orders, Inventory và Payment triển khai độc lập, mỗi dịch vụ sở hữu dữ liệu; giao tiếp qua API và broker/queue; các nghiệp vụ dài xử lý theo saga hoặc state machine.

**Ưu điểm:** cô lập triển khai và mở rộng từng domain, hợp với nhiều đội độc lập. **Rủi ro:** tăng số hợp đồng version, dữ liệu phân tán, sự kiện trùng/đến muộn, chi phí quan sát và xử lý sự cố; luồng xác nhận đơn phức tạp hơn. Event-driven **không tự tạo** consistency hoặc exactly-once.

### Phương án C — Serverless functions + event-driven workflows

API gateway gọi function theo tính năng; dùng managed queue, workflow engine, database và storage phù hợp. Thích hợp các tác vụ ngắn, lưu lượng biến động và ít trách nhiệm vận hành hệ điều hành.

**Ưu điểm:** co giãn theo request, thanh toán tài nguyên theo mức dùng và tận dụng dịch vụ managed. **Rủi ro:** concurrency/quotas, cold start khi liên quan SLO, giới hạn thời gian chạy, tích hợp mạng tới ERP, khả năng test/debug workflow và biến động chi phí theo traffic.

Ba phương án có thể kết hợp kỹ thuật: ví dụ A vẫn dùng function cho job độc lập; B vẫn dùng managed database; C vẫn cần mô hình trạng thái giao dịch. Phương án được phân biệt chủ yếu bởi **ranh giới triển khai và cách quản trị trạng thái**, không phải logo công nghệ.

### 6.1. Lập bảng đánh đổi

Ví dụ nhóm thống nhất các trọng số vì phải ra mắt nhanh và giữ tính đúng đơn hàng:

| Tiêu chí | Trọng số | A: Modular | B: Microservices | C: Serverless |
|---|---:|---:|---:|---:|
| Độ tin cậy/khả năng hồi phục | 30% | 4 | 4 | 4 |
| Tính nhất quán và dễ đối soát | 25% | 5 | 3 | 3 |
| Tốc độ giao hàng với đội hiện tại | 20% | 5 | 2 | 3 |
| Khả năng mở rộng | 15% | 3 | 5 | 4 |
| Chi phí và công sức vận hành | 10% | 5 | 2 | 4 |
| **Tổng có trọng số (trên 5)** | **100%** | **4,40** | **3,30** | **3,55** |

Thang 1–5 và trọng số chỉ là **đánh giá giả định để làm bài**, cần giải thích bằng dữ liệu POC và hiểu biết của team. Ví dụ, 30% × 4 + 25% × 5 + 20% × 5 + 15% × 3 + 10% × 5 = **4,40** cho A. Nếu doanh nghiệp có nhiều team chuyên sâu platform và yêu cầu triển khai từng domain độc lập, điểm B có thể thay đổi. Nếu ứng dụng xử lý lượng lớn tác vụ bất đồng bộ ngắn, C có thể hợp lý hơn.

Điểm trung bình **không cho phép bỏ qua điều kiện chặn**: một phương án không bảo đảm bất biến dữ liệu, phạm vi bảo mật hoặc hạn chót bắt buộc phải được sửa/loại trước khi chấm điểm.

### 6.2. Phân tích độ nhạy

Hãy thử thay trọng số hoặc một giả định then chốt:

- Nếu tăng ưu tiên mở rộng độc lập và có thêm 5 đội domain, A còn đứng đầu không?
- Nếu PSP không hỗ trợ idempotency, phương án nào cần thay đổi luồng thanh toán?
- Nếu hệ thống phải đạt RTO dưới 5 phút khi **toàn region** mất, yêu cầu topology và đồng bộ dữ liệu tăng bao nhiêu?
- Nếu 90% cache hit chỉ đạt 40%, capacity origin và database có còn đủ?

Một quyết định có sức thuyết phục khi nhóm nói rõ **điều kiện khiến mình đổi quyết định**.

## 7. Lời giải tham khảo — chọn một kiến trúc đủ tốt để triển khai

Giả sử nhóm tạm chọn **phương án A (modular monolith trên compute managed)** vì cần ra mắt trong sáu tháng với đội nhỏ, giao dịch đơn hàng đòi hỏi nhất quán, và mức tải đầu vào chưa chứng minh cần tách nhiều dịch vụ. Chọn A **không có nghĩa** mọi chức năng nằm trong một tiến trình duy nhất hoặc phải đặt tất cả dữ liệu chung một schema thiếu ranh giới.

### 7.1. Sơ đồ thành phần cấp container

~~~mermaid
flowchart TB
    User["Khách hàng / nhân viên"] --> Edge["DNS + CDN + WAF"]
    Edge --> LB["L7 Load Balancer / API ingress"]
    subgraph Region["Cloud region chính"]
      subgraph App["Private compute, nhiều Availability Zone"]
        API["Ứng dụng modular: catalog, cart, checkout, orders"]
        Worker["Worker: outbox, fulfillment, webhook jobs"]
      end
      DB[("Managed relational DB - Multi-AZ")]
      Cache[("Managed cache / session store")]
      Q[("Durable queue / event broker")]
      Object[("Object storage: ảnh, export, backup")]
      Obs["Logs, metrics, traces, alerting"]
      LB --> API
      API --> DB
      API --> Cache
      API --> Object
      Worker --> DB
      Worker --> Q
      Q --> Worker
      API --> Obs
      Worker --> Obs
    end
    API <-->|"Private link/VPN qua adapter"| ERP["ERP tại trung tâm dữ liệu"]
    API <-->|"API xác thực"| PSP["PSP thanh toán"]
    PSP -->|"Webhook xác minh tại endpoint công khai"| LB
    Worker -->|"Gửi thông báo"| Notify["Nhà cung cấp thông báo"]
~~~

Đây là sơ đồ logic, chưa quyết định vendor hay SKU dịch vụ. Trong thiết kế vật lý cần bổ sung VPC/subnet, routing, security groups/firewall, cân bằng tải đa AZ, kết nối riêng tới ERP, egress, DNS, quản lý khóa, backup và vùng dự phòng nếu yêu cầu DR vùng được duyệt.

| Lớp | Chọn trong lời giải | Vì sao |
|---|---|---|
| Edge/CDN | CDN + WAF, cache nội dung catalog/ảnh khi an toàn | Giảm tải origin; hạn chế truy cập độc hại và request bất thường |
| Compute | Dịch vụ container/application managed, tối thiểu đa AZ | Đội nhỏ, cần autoscale và triển khai lặp lại |
| Database | Relational managed DB có HA đa AZ và backup/PITR | Bảo vệ trạng thái đơn hàng và thao tác transaction |
| Cache | Cache cho dữ liệu đọc, session tạm nếu cần | Giảm truy vấn; dữ liệu cache không được là nguồn chuẩn |
| Event/queue | Durable queue và outbox publisher | Tách tác vụ phụ, chống mất sự kiện sau commit |
| Network | Ingress được kiểm soát, app/DB private, VPN hoặc kết nối riêng tới ERP | Giới hạn bề mặt tấn công; kiểm soát độ trễ và phụ thuộc hybrid |
| Observability | Metric theo SLI, tracing, log có correlation ID | Điều tra được đơn lỗi qua API, DB, ERP và PSP |
| Delivery | IaC, CI/CD, migration schema, rollout theo giai đoạn | Lặp lại được, có rollback phần mềm và audit |

Một **cache hit** không tự đảm bảo giá khuyến mãi và tồn kho luôn đúng. Catalog có thể hiển thị giá tạm thời theo TTL, nhưng bước checkout phải xác thực giá và áp dụng chính sách bán hàng hiện hành. Dữ liệu tồn kho nhạy với tranh chấp không được coi là chính xác chỉ vì vừa đọc từ cache.

### 7.2. Mẫu ranh giới mạng và quyền

Các endpoint công khai gồm CDN/ingress cho khách và webhook PSP. Dịch vụ ứng dụng không cần public IP; database, cache, queue được truy cập qua mạng riêng và chính sách tối thiểu. Tài khoản vận hành đi qua hệ định danh tổ chức và quyền theo vai trò. Secret và khóa mã hóa nằm trong dịch vụ quản lý bí mật/khóa, không nằm trong source code hay image.

Đường cloud → ERP cần xác định **bên thiết lập kết nối**, subnet, tường lửa, DNS, mã hóa, cơ chế xác thực, giới hạn kết nối và đường dự phòng. Nếu VPN hỏng, không được tự động chuyển sang endpoint ERP công khai thiếu kiểm soát. Thiết kế cần giữ nguyên trạng thái an toàn: báo “đang xử lý/chưa xác nhận tồn kho” theo hợp đồng nghiệp vụ thay vì xác nhận đơn vô điều kiện.

### 7.3. Thiết kế trạng thái đơn hàng trước khi viết API

Một state machine gợi ý:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING_RESERVATION: Tạo request có idempotency key
    PENDING_RESERVATION --> RESERVED: ERP giữ hàng thành công
    PENDING_RESERVATION --> REJECTED: Hết hàng / không thể giữ
    RESERVED --> PAYMENT_PENDING: Tạo payment intent
    PAYMENT_PENDING --> PAID: Nhận tín hiệu PSP hợp lệ
    PAYMENT_PENDING --> CANCELLED: Hủy/hết hạn
    PAID --> CONFIRMED: Xác minh reservation còn hiệu lực
    PAID --> COMPENSATION_REQUIRED: Reservation hết hạn/lỗi bất thường
    COMPENSATION_REQUIRED --> REFUNDED: Void/refund được đối soát
    CONFIRMED --> FULFILLING: Chuyển cho cửa hàng
    FULFILLING --> COMPLETED: Giao/nhận thành công
    REJECTED --> [*]
    CANCELLED --> [*]
    REFUNDED --> [*]
    COMPLETED --> [*]
~~~

Sơ đồ minh họa **một** chính sách kinh doanh. Doanh nghiệp phải quyết định lúc nào mới “xác nhận đơn” với khách, có tạm giữ tiền (*authorization*) trước khi *capture* hay không, và reservation tồn kho kéo dài bao lâu. Nếu PSP hỗ trợ authorization/capture tách biệt, có thể xác minh hàng và chỉ capture khi các điều kiện đã được đảm bảo. Nếu PSP chỉ hỗ trợ thu tiền ngay, cần chuẩn bị lộ trình void/refund và đối soát khi một bước sau đó thất bại.

**Điểm dễ sai:** không được kết luận “payment success” chỉ từ trang redirect của trình duyệt. Cần xác minh webhook có chữ ký hợp lệ hoặc tra cứu trạng thái qua API của PSP; webhook có thể bị gửi trùng, đến muộn hoặc sai thứ tự. Idempotency phải bao phủ **cả phía ứng dụng và các lời gọi PSP có hỗ trợ**.

### 7.4. Trình tự checkout có thể kiểm chứng

~~~mermaid
sequenceDiagram
    autonumber
    actor C as Khách
    participant A as API / Orders
    participant D as Order DB
    participant E as ERP
    participant P as PSP
    participant W as Outbox worker
    C->>A: POST checkout + idempotency key
    A->>D: Tạo / đọc PENDING_RESERVATION (unique key)
    A->>E: Reserve(orderId, items, TTL)
    alt ERP từ chối / timeout
      A->>D: Ghi từ chối hoặc trạng thái chờ tra cứu
      A-->>C: Chưa xác nhận, không giả định thành công
    else Reservation thành công
      A->>D: Ghi RESERVED
      A->>P: Tạo payment intent (idempotent)
      P-->>A: Payment reference
      A-->>C: Hướng dẫn thanh toán theo payment reference
      P->>A: Webhook báo trạng thái (có thể lặp)
      A->>P: Xác minh khi cần
      A->>D: Transaction: trạng thái đơn + outbox event
      D-->>W: Đọc outbox chờ phát
      W->>W: Publish có retry / dedupe
    end
~~~

Trong thực tế, phần nhận webhook là một endpoint/worker tách logic với request của khách; sơ đồ gộp cùng hộp API để mô tả trách nhiệm. Bước xác minh reservation còn hiệu lực và xử lý refund/void khi không còn hàng phải là một phần của state machine, không được bỏ qua vì lời gọi thanh toán đã trả về thành công.

**Tính nhất quán:** cập nhật trạng thái đơn và chèn outbox event trong **cùng transaction của Order DB**. Worker có thể phát lại sự kiện nếu crash sau khi publish nhưng trước khi đánh dấu đã gửi; consumer cần idempotency theo eventId. Transactional outbox giảm cửa sổ “đã commit đơn nhưng quên phát event”, không bảo đảm exactly-once toàn bộ chuỗi từ ERP tới PSP.

### 7.5. Phương án lỗi theo từng ranh giới

| Lỗi | Phản ứng mong muốn | Tín hiệu kiểm chứng |
|---|---|---|
| Người dùng gửi lại checkout | Trả cùng trạng thái/orderId cho cùng idempotency key còn hiệu lực | Không có hai đơn từ một khóa |
| ERP timeout sau khi đã giữ hàng | Tra cứu reservation theo mã ổn định, không gửi tạo mới vô hạn | Không giữ trùng; timeout được phân loại rõ |
| PSP gửi webhook lặp | Một chuyển trạng thái hợp lệ, một tác động tài chính | Dedupe theo event và payment reference |
| PSP thu tiền nhưng đơn chưa xác nhận | Đưa vào hàng đợi đối soát/compensation, cảnh báo | Giao dịch treo có owner và SLA giải quyết |
| DB primary failover | Request đang dở có thể retry an toàn | Không mất tính nhất quán hoặc tạo đơn trùng |
| Queue tạm thời không nhận | Outbox giữ sự kiện đã commit, worker gửi lại | Backlog được đo, có alert và catch-up |
| Cache mất | Fallback DB trong hạn mức đã tính, không làm sai giá | Test cache outage và bảo vệ DB khỏi dồn tải |
| Toàn region lỗi | Kích hoạt kế hoạch DR đã được duyệt | RTO/RPO thực đo và đối soát phục hồi |

**Không phản hồi** là một trạng thái có ý nghĩa. Đối với phụ thuộc ngoài hệ thống, timeout không chứng minh nghiệp vụ đã thất bại. ERP có thể đã giữ hàng hoặc PSP có thể đã thu tiền ngay trước khi kết nối mất. Cần **tra cứu theo mã giao dịch bền vững và đối soát** trước khi thử thực hiện lại.

## 8. Bước 5 — Ước tính capacity từ workload, không từ cảm giác

Các số ước tính dùng để khởi tạo thiết kế và lên kế hoạch POC; cấu hình cuối phải dựa trên benchmark với dữ liệu, endpoint và độ trễ giống thực tế.

### 8.1. Tách tải CDN khỏi tải origin

Giả định **1.200 request/giây** duyệt catalog và **90% cache hit**, lưu lượng đọc đi tới origin còn:

\[
1\,200 \times (1-0{,}90)=120\ \text{request/giây}.
\]

Kết hợp thêm **60 checkout attempts/giây**, ta có xấp xỉ **180 request/giây cho hai nhóm luồng đang xét**. Đây **không phải tổng hệ thống**: còn login, cart, search, payment webhook, fulfillment, job nền và một số request catalog không cache được.

Giả sử load test ban đầu chứng minh một replica API xử lý **75 request/giây với cơ cấu request tương ứng** mà vẫn đạt SLO. Nếu muốn hoạt động ở mức tối đa khoảng **70% capacity đo được** để có headroom, một replica chỉ được tính:

\[
75 \times 0{,}70 = 52{,}5\ \text{request/giây}.
\]

Nếu triển khai **6 replica chia đều trên 3 Availability Zone**, khi mất 1 AZ còn 4 replica, năng lực tính theo giả định:

\[
4\times52{,}5=210\ \text{request/giây} > 180.
\]

Ví dụ này chỉ cho thấy **cách tính kiểm tra một kịch bản**, không chứng minh hệ thống đã đạt SLO. Khối lượng xử lý checkout thường nặng hơn truy vấn catalog; load test phải phản ánh đúng tỷ lệ, external API, database, connection pool, cache miss và queue. Nếu 75 request/giây chỉ đo với GET nhẹ thì phép tính trên **không hợp lệ**.

### 8.2. Ước tính dữ liệu đơn hàng

Nếu trung bình **45.000 đơn/ngày**, giả sử mỗi đơn và các dòng hàng/metadata liên quan được tính gộp **3 KB dữ liệu thô**:

\[
45\,000\times3\,000=135\,000\,000\ \text{byte/ngày}
\]

tương đương khoảng **135 MB/ngày** và **49,3 GB/năm** dữ liệu thô (đơn vị thập phân, 365 ngày). Dung lượng thực tế cao hơn khi tính index, MVCC/overhead, replication, transaction logs, backup, audit, tăng trưởng dữ liệu và bảng tích hợp. Doanh nghiệp cần tách dữ liệu vận hành nóng khỏi dữ liệu lịch sử theo chính sách lưu trữ và yêu cầu kiểm toán.

### 8.3. Phân tích độ nhạy của cache hit

| Cache hit ở CDN | Catalog origin RPS khi edge nhận 1.200 RPS | Chênh với phương án 90% |
|---|---:|---:|
| 90% | 120 | Baseline giả định |
| 75% | 300 | Gấp 2,5 lần |
| 50% | 600 | Gấp 5 lần |
| 0% | 1.200 | Gấp 10 lần |

Vì vậy, cache hit ratio là **giả định có tác động lớn**. Cần kiểm thử với sản phẩm, giá theo khu vực, cookie, quyền truy cập, TTL, invalidation và hành vi vào giờ khuyến mãi. Tránh cache lẫn dữ liệu cá nhân giữa người dùng do sai cache key.

### 8.4. Capacity của các phụ thuộc ngoài cloud

Khả năng API chịu được 60 checkout attempts/giây **không có nghĩa** ERP chịu được 60 reservation/s hoặc PSP chịu được 60 intent/s. Cần đo:

- Throughput/quota API, connection pool, timeout, p95/p99 và tỷ lệ lỗi ERP/PSP.
- Tốc độ queue tăng khi một phụ thuộc chậm; thời gian xả backlog sau khi phục hồi.
- Số kết nối, transaction duration, lock contention và CPU/IO của database.
- Tốc độ cập nhật giá/tồn kho và rủi ro cache stale.

Thiết kế cần rate limit, circuit breaker, backpressure và **degraded mode** phù hợp nghiệp vụ. Nếu không thể kiểm tra/giữ tồn kho thì có thể cho khách lưu giỏ hoặc đăng ký chờ, nhưng **không được xác nhận còn hàng** nếu chính sách không cho phép.

## 9. Bước 6 — Thiết kế cho lỗi, bảo mật và vận hành

Một kiến trúc đủ thuyết phục phải giải thích **hệ thống cư xử thế nào khi điều kiện không còn lý tưởng**, không chỉ mô tả đường đi thành công.

### 9.1. Ranh giới chịu lỗi và mục tiêu khôi phục

| Sự cố | Cơ chế thiết kế | Điều cần chứng minh |
|---|---|---|
| Mất một instance ứng dụng | Health check, autoscale/restart, request retry idempotent | Không mất trạng thái đã commit |
| Mất một Availability Zone | LB định tuyến sang AZ còn lại; compute và DB có cơ chế HA | Tải còn lại đủ, DB failover đúng và khách không bị tạo đơn trùng |
| DB bị lỗi logic hoặc xóa nhầm | PITR, backup có kiểm chứng, tách quyền | Phục hồi dữ liệu đúng mốc và đối soát |
| Queue/worker dừng | Durable queue/outbox, monitor age/backlog, retry có giới hạn | Không “mất” tác vụ đã commit dù xử lý chậm |
| ERP mất kết nối | Timeout, circuit breaker, chờ hoặc từ chối xác nhận đơn theo policy | Không oversell, không treo request vô hạn |
| PSP có sự cố | Hiển thị rõ trạng thái pending, tra soát sau | Không thu trùng tiền, có đường xử lý giao dịch treo |
| Mất toàn cloud region | DR sang vùng khác theo kế hoạch đã duyệt | Đạt RTO/RPO nếu yêu cầu đó thực sự bắt buộc |

**Multi-AZ không đồng nghĩa multi-region.** Một relational database HA đa AZ bảo vệ nhiều sự cố trong một region, nhưng không tự đáp ứng RTO 60 phút/RPO 5 phút khi **toàn region** mất. Nếu Q-05 được duyệt là bắt buộc ngay khi ra mắt, thiết kế phải có thêm phương án như:

- Bản sao dữ liệu bất đồng bộ sang region dự phòng với cơ chế theo dõi replication lag và quyền ghi rõ ràng.
- Hạ tầng, cấu hình, secret, phụ thuộc mạng và image triển khai có khả năng khởi tạo/chạy tại region dự phòng; không chỉ sao lưu database.
- Cơ chế chuyển DNS/traffic, xử lý giao dịch đang dở và đối soát PSP/ERP sau failover.
- Diễn tập DR đo **thời điểm khôi phục dịch vụ** và **mốc dữ liệu thực tế phục hồi**; nếu không đạt thì phải đầu tư thêm hoặc thương lượng lại mục tiêu.

Bản sao bất đồng bộ có thể mất các bản ghi mới nhất khi region chính mất trước khi replicate. Với đơn hàng và thanh toán, kế hoạch DR phải nêu cách phát hiện và phục hồi giao dịch thiếu từ log bất biến, PSP và ERP. **Không tự khẳng định RPO = 0** chỉ vì đã bật replication.

**RTO/RPO nên phân tách theo cấp sự cố:** restart một pod, failover trong AZ/region, mất cả region, lỗi dữ liệu logic và sự cố nhà cung cấp là các trường hợp khác nhau. Mỗi cấp có phương án và chi phí riêng.

### 9.2. Độ tin cậy của chuỗi phụ thuộc

Checkout có thể phụ thuộc đồng thời API, database, ERP và PSP. Nếu mọi phụ thuộc phải cùng hoạt động, độ sẵn sàng của luồng nghiệp vụ thường **thấp hơn từng thành phần riêng lẻ**. Không thể suy ra checkout đạt 99,95% chỉ từ SLA 99,99% của compute.

Thực hành nên tạo **dependency map** và đo error rate, timeout, latency tại từng đường gọi; thương lượng SLA tích hợp hoặc thiết kế trạng thái chờ có thể chấp nhận. Nếu yêu cầu “đặt đơn thành công ngay” không thể đáp ứng khi ERP offline, cần business owner quyết định có hỗ trợ **đặt chờ, backorder hoặc tạm dừng checkout** hay không.

### 9.3. Bảo mật theo luồng dữ liệu

Hãy đánh dấu trên sơ đồ: PII, token thanh toán, dữ liệu công khai, dữ liệu đơn, tài khoản nhân viên, secret và audit log.

| Bề mặt | Kiểm soát cơ bản | Phép xác minh |
|---|---|---|
| Khách → API | TLS, xác thực thích hợp, rate limit, kiểm tra đầu vào, WAF | Pen test theo phạm vi, thử lạm dụng API và bot |
| Nhân viên → quản trị | SSO/MFA, RBAC/ABAC, least privilege, session policy | Thử truy cập chéo cửa hàng và audit hành động |
| App → DB/cache/queue | Private network, workload identity, quyền tối thiểu | Review network policy/IAM, kiểm thử denied access |
| App → PSP/ERP | TLS/mTLS hoặc cơ chế đã thỏa thuận, webhook signature, secret rotation | Thử giả mạo webhook và timeout/retry |
| Dữ liệu lưu trữ | Encryption at rest, key policy, lifecycle, backup và restore | Kiểm thử quyền đọc, phục hồi và xóa theo chính sách |
| CI/CD và supply chain | Phân quyền deploy, kiểm tra dependency/image, artifact có nguồn gốc | Kiểm thử pipeline, audit quyền thay đổi production |
| Observability | Che dữ liệu nhạy cảm khỏi log, quyền dashboard, retention | Soát log request/error và quy trình truy xuất |

Không lưu thông tin thẻ gốc hoặc dùng cách tích hợp làm phát sinh thêm phạm vi xử lý dữ liệu thẻ khi chưa có đánh giá phù hợp. Chỉ nhận payment token/reference từ PSP và xác định phạm vi tuân thủ theo phương thức tích hợp thực tế.

Khi dùng dữ liệu khách hàng trong cache hoặc bản xuất báo cáo, cần ràng buộc khóa cache với phạm vi người dùng và thiết lập quyền theo chủ thể thực, tránh **IDOR** (truy cập đối tượng không được cấp quyền) hoặc trả dữ liệu của người khác do thiếu kiểm tra ở tầng API.

### 9.4. Khả năng quan sát gắn với nghiệp vụ

Với mỗi đơn, các sự kiện từ frontend, API, ERP adapter, PSP callback, database và worker cần liên kết bằng **correlation ID** và tham chiếu giao dịch thích hợp, nhưng không ghi bí mật hoặc dữ liệu thẻ vào log.

Những dashboard nên có:

- **Business SLI:** tỷ lệ checkout thành công theo định nghĩa, tỷ lệ đơn pending kéo dài, số giao dịch cần đối soát, tỷ lệ hủy do hết hàng.
- **Customer experience:** p95/p99 latency, lỗi theo browser/device/region, Core Web Vitals khi phù hợp, mất request.
- **Dependencies:** ERP/PSP latency, timeout, quota, retry, circuit breaker state.
- **Data/async:** DB connection pool, lock time, replication lag, outbox age, queue depth, dead-letter count.
- **Operations:** error budget burn, số lần rollback deploy, thời gian khắc phục, số lần backup/restore pass.

Alert phải dẫn tới **runbook và người chịu trách nhiệm**. Ví dụ: “số lượng đơn PAID chưa CONFIRMED vượt ngưỡng 10 phút” quan trọng hơn việc một CPU thỉnh thoảng đạt 80% mà không ảnh hưởng dịch vụ.

### 9.5. Thực hành triển khai và thay đổi

Đề xuất pipeline: **commit → kiểm thử → xây image → quét lỗ hổng → triển khai staging → smoke/integration → canary/rolling production → đo SLI → hoàn tất hoặc rollback**. Dùng IaC cho mạng, compute, quyền và cấu hình; quản lý secret riêng, tránh lưu trong Git.

Với database schema, ưu tiên **expand-and-contract migration** để các phiên bản ứng dụng cũ/mới chạy đồng thời trong cửa sổ rollout. Rollback mã nguồn **không tự rollback dữ liệu** đã biến đổi hoặc giao dịch từ PSP; phải có kế hoạch sửa tiến, đối soát và phục hồi phù hợp.

## 10. Bước 7 — Ước tính chi phí và tổ chức giao hàng

Chi phí cần được so sánh theo **total cost of ownership** trong ít nhất các kịch bản thường, cao điểm và lỗi, thay vì so giá một container với giá một function.

### 10.1. Bảng ước tính chi phí dạng biến số

| Thành phần | Đơn vị đo cần thu thập | Biến số làm chi phí tăng |
|---|---|---|
| Compute | Số replica × thời gian × cỡ instance; lượng scaling | Đỉnh traffic, HA đa AZ, cấu hình tối thiểu khi ít tải |
| Database | Node/CPU/RAM, storage, I/O, backup, replica | Giao dịch, index, lịch sử lưu dài, DR |
| Cache | Số node, RAM, khả năng HA | Cardinality SKU, session, cache invalidation |
| Queue/stream | Request, throughput, retention, data transfer | Retry storm, replay, số consumer |
| CDN/WAF/API | Request, bandwidth/egress, rule, log | Cache miss, bot, tải campaign |
| Mạng hybrid | VPN/đường riêng, egress, băng thông dự phòng | Lưu lượng ERP, số kết nối và độ trễ |
| Observability | GB log, số metric/time series, trace sampling | Cardinality, debug logging và retention |
| DR và backup | Replica vùng phụ, lưu trữ bản sao, test failover | RTO/RPO nghiêm ngặt, tần suất diễn tập |
| Nhân sự và công cụ | On-call, bảo trì, phát triển, security review | Số runtime/service, manual operations, technical debt |

Ví dụ, thêm một region dự phòng để đáp ứng Q-05 là **một quyết định chi phí có chủ đích**, không nên bị giấu sau mục “độ tin cậy”. Ngược lại, tối ưu chi phí bằng cách chạy một replica duy nhất trong production có thể vi phạm yêu cầu chịu lỗi một AZ.

Các câu hỏi đánh đổi cần đưa ra:

1. Bao nhiêu phần trăm lưu lượng catalog có thể giảm từ origin qua CDN/cache?
2. Có thể tách lưu trữ dữ liệu lịch sử ra object storage thay vì giữ toàn bộ trong OLTP DB không?
3. Chi phí trả thêm để đạt RTO/RPO vùng nghiêm ngặt có tương xứng thiệt hại kinh doanh ước tính không?
4. Team có đủ năng lực vận hành nhiều microservice, service mesh và broker riêng hay nên mua năng lực managed?
5. Có budget alert, quota, tagging và phân bổ chi phí theo môi trường/nhóm chức năng không?

Không đưa một con số tiền cụ thể nếu chưa có **region, cấu hình, giá dịch vụ hiện hành, thuế, chiết khấu và mô hình lưu lượng**. Khi ước tính thật, hãy ghi nguồn giá, ngày tính và phương án cao/thấp để có thể kiểm toán.

### 10.2. Chia giai đoạn triển khai

| Giai đoạn | Đầu ra có thể kiểm chứng | Điều kiện chuyển tiếp |
|---|---|---|
| **Discovery** | NFR, data classification, ERP/PSP contract, assumption register | Các giả định ảnh hưởng lớn có owner và kế hoạch thử |
| **Architecture spike** | Thử reservation/idempotency, benchmark DB/API, DR cost estimate | Tính đúng và các giả định khó nhất được chứng minh |
| **Foundation** | Network, IAM, secrets, IaC, CI/CD, log/metric, backup | Security baseline và restore được thử |
| **Vertical slice** | Một hành trình checkout end-to-end trên staging | Có đối soát tiền, tồn kho, đơn hàng và tracing |
| **Hardening** | Load, failover, security, chaos/DR drill theo phạm vi | Đạt SLO/SLI đã duyệt, runbook và on-call sẵn sàng |
| **Launch & observe** | Canary rollout, dashboard kinh doanh, hypercare | Quy trình Go/No-Go và xử lý giao dịch treo chạy được |

Các giai đoạn có thể gối nhau; phải tránh đưa tất cả thử nghiệm độ tin cậy và bảo mật xuống cuối dự án. Ví dụ, nếu ERP không có reservation idempotent, phát hiện ở tháng thứ năm sẽ làm thay đổi state machine và phạm vi nghiệm thu.

## 11. Bước 8 — Ghi Architecture Decision Record (ADR)

Một ADR ngắn giúp người khác hiểu **vì sao kiến trúc hiện tại như vậy** và khi nào cần xét lại. Mẫu:

~~~text
ADR-ID:
Tiêu đề:
Trạng thái: Proposed / Accepted / Superseded
Ngày và người phê duyệt:
Bối cảnh và yêu cầu liên quan:
Giả định chưa kiểm chứng:
Phương án đã xét:
Quyết định:
Lý do và bằng chứng:
Hệ quả tích cực / tiêu cực:
Cách kiểm chứng:
Điều kiện xem xét lại:
~~~

### ADR-001 — Chọn modular monolith cho lần ra mắt đầu

**Trạng thái:** Proposed, chờ xác nhận của product/engineering owner.

**Bối cảnh:** đội 8 lập trình viên, 2 kỹ sư hạ tầng, deadline sáu tháng; luồng checkout cần nhất quán và khả năng điều tra nhanh khi lỗi.

**Phương án:** A — modular monolith có outbox và queue; B — microservices theo domain; C — serverless functions + workflow.

**Quyết định đề xuất:** chọn A, triển khai bằng compute managed đa AZ, relational DB managed, cache/CDN và worker bất đồng bộ cho các việc sau commit.

**Lý do:** phù hợp năng lực đội và tiến độ, giảm số giao dịch liên dịch vụ; kết quả ma trận tham khảo A = 4,40; cần POC xác minh khả năng chịu đỉnh.

**Hệ quả:** module có chung lịch release và blast radius runtime; phải áp dụng ranh giới module, test interface, metrics theo domain, tránh truy cập trực tiếp bảng thuộc domain khác dù cùng database khi không cần thiết.

**Cách kiểm chứng:** load test cơ cấu request thật, thử một AZ lỗi, đo thay đổi nghiệp vụ và tốc độ deploy; review coupling định kỳ.

**Xem xét lại khi:** có nhóm triển khai độc lập theo domain, chu kỳ release xung đột thường xuyên, hoặc một module có profile tải/cách ly lỗi mà kiến trúc hiện tại không đáp ứng với chi phí hợp lý.

### ADR-002 — Đơn hàng và outbox dùng chung transaction

**Trạng thái:** Proposed, chờ xác nhận của data/operations owner.

**Bối cảnh:** sau khi xác nhận trạng thái đơn, phải kích hoạt fulfillment và thông báo. Nếu cập nhật DB thành công nhưng publish event thất bại thì có nguy cơ bỏ sót tác vụ.

**Phương án:** (1) ghi DB rồi publish trực tiếp; (2) transaction gồm trạng thái đơn + outbox, worker publish có retry; (3) dùng hệ thống giao dịch phân tán giữa các resource.

**Quyết định đề xuất:** chọn (2). Consumer xử lý idempotent vì event có thể phát lại.

**Hệ quả:** thêm bảng outbox, worker, giám sát độ tuổi backlog và cơ chế dọn dữ liệu; đổi lại tránh lỗ hổng dual-write ở đường commit chính. Không coi queue ack là toàn bộ nghiệp vụ đã hoàn tất.

**Xem xét lại khi:** nền tảng cung cấp cơ chế đảm bảo atomically commit hiệu quả và đã được chứng minh, hoặc nhu cầu throughput/latency thay đổi rõ rệt.

### ADR-003 — Khôi phục khi mất toàn region

**Trạng thái:** Pending business decision.

**Bối cảnh:** đề bài đưa ra **RTO ≤ 60 phút, RPO ≤ 5 phút** cho toàn region nhưng chưa có phê duyệt chi phí và mức chấp nhận rủi ro mất dữ liệu.

**Hai lựa chọn cần trình duyệt:**

- **Đáp ứng ngay:** có warm standby/dữ liệu sao chép ở region dự phòng, quy trình chuyển tuyến, đối soát trạng thái đơn/PSP và diễn tập thường xuyên. Chi phí và vận hành tăng.
- **Triển khai theo giai đoạn:** ban đầu tập trung HA multi-AZ, backup/PITR và quy trình restore; chấp nhận mục tiêu DR vùng khác hoặc thời điểm hoàn tất DR sau launch, **chỉ khi business owner phê duyệt thay đổi yêu cầu**.

**Điều kiện quyết định:** business impact analysis, giới hạn lưu trú dữ liệu, đánh giá nhà cung cấp và kết quả DR POC. Không tuyên bố Q-05 “đã đạt” khi chỉ có backup đa AZ.

### ADR-004 — Tồn kho thuộc nguồn chuẩn ERP trong giai đoạn đầu

**Trạng thái:** Proposed, phụ thuộc A-02.

**Bối cảnh:** hệ thống mới chưa thay ERP; tồn kho có nhiều kênh bán song song. Việc chép số lượng về cloud để hiển thị có thể chấp nhận độ trễ, nhưng khi xác nhận bán phải có cơ chế tránh oversell.

**Quyết định đề xuất:** giữ ERP làm nguồn chuẩn; dùng bản sao chỉ đọc để hiển thị, còn checkout yêu cầu reservation/commit theo giao thức được ERP xác nhận. Từ chối xác nhận hoặc chuyển sang trạng thái pending khi không có bằng chứng giữ hàng.

**Hệ quả:** độ sẵn sàng checkout phụ thuộc ERP/đường WAN; cần đo và có chính sách chờ, timeout, đối soát, dữ liệu chậm, kênh xử lý sự cố. Nếu ERP thiếu reservation idempotent, đây là **blocker kiến trúc** cần thảo luận nghiệp vụ và giải pháp khác.

## 12. Bước 9 — Kiểm chứng thiết kế bằng kịch bản

Không nên chỉ review sơ đồ bằng ý kiến. Mỗi quyết định quan trọng phải có bài kiểm thử, ngưỡng, người thực hiện và bằng chứng.

| Nhóm | Kịch bản xác minh | Kết quả cần đạt |
|---|---|---|
| **Chức năng** | Đặt hàng thành công, hết hàng, hủy, PSP hoàn tiền, tra cứu đơn | Trạng thái và số liệu khớp hợp đồng nghiệp vụ |
| **Idempotency** | Gửi cùng checkout key 100 lần, webhook lặp/sai thứ tự | Không phát sinh đơn/thu tiền trùng do retry |
| **Tải** | Burst 60 checkout attempts/s trong 5 phút cùng read traffic | p95, error rate, throughput đạt ngưỡng đã duyệt |
| **Cache** | Giảm CDN hit từ 90% xuống 50%, cache outage | Không làm lộ dữ liệu, origin có protection, quan sát degraded |
| **ERP** | Timeout sau khi đã reserve, ERP 429/503, mất VPN | Tra cứu/đối soát đúng, không xác nhận tồn kho sai |
| **PSP** | Payment success nhưng webhook đến muộn, bị mất hoặc trùng | Đơn pending được xử lý/đối soát, không tạo yêu cầu thu tiền lặp |
| **Database** | Failover primary giữa transaction và khi outbox worker chạy | Ghi bền vững, retry an toàn và không mất event đã commit |
| **Availability Zone** | Mất một AZ trong tải cao điểm | Capacity còn lại và database failover đáp ứng mục tiêu |
| **Region DR** | Giả lập mất toàn region, phục hồi dịch vụ và đối soát | RTO/RPO thực đo theo yêu cầu đã phê duyệt |
| **Security** | Truy cập chéo tài khoản/cửa hàng, webhook giả, rò secret | Từ chối và audit theo quy định |
| **Operations** | Canary lỗi, rollback code, schema migration không tương thích | Phục hồi được mà không làm sai dữ liệu giao dịch |
| **Cost** | Tải bình thường/cao điểm, log tăng, replication/egress | Budget, quota và cảnh báo phí hoạt động |

### 12.1. Mẫu biên bản kiểm chứng một kịch bản

~~~yaml
scenarioId: LOAD-CHECKOUT-01
requirementRefs: [Q-03, Q-04]
assumptionRefs: [A-01, A-02, A-03]
environment: staging-representative
load:
  checkoutAttemptsPerSecond: 60
  burstDurationMinutes: 5
  catalogRequestsPerSecond: 1200
acceptance:
  checkoutApiP95Ms: 800
  businessInvariants: "Không có đơn hoặc tiền thu trùng"
  dependencyErrors: "Trong ngưỡng riêng đã được phê duyệt"
evidence:
  dashboard: "Bổ sung đường dẫn sau buổi test"
  traceSamples: "Bổ sung đường dẫn sau buổi test"
owner: performance-lead
status: NOT_RUN
~~~

Tệp YAML trên là **mẫu minh họa** cho cách ghi bằng chứng của một thử nghiệm, không phải cấu hình hệ thống hay kết quả đã chạy. Trong dự án thật, thêm trạng thái PASS/FAIL có thời điểm, phiên bản triển khai, dữ liệu test và các ngưỡng error rate; để `NOT_RUN` nếu chưa thực thi.

### 12.2. Thực hành phản biện kiểu ATAM rút gọn

Chọn ba **quality attribute scenarios** gây xung đột:

1. **Giảm chi phí vs. độ tin cậy:** doanh nghiệp yêu cầu một AZ lỗi không mất checkout. Điều gì xảy ra nếu giảm replica còn một và loại bỏ DB HA?
2. **Tốc độ ra mắt vs. chia nhỏ dịch vụ:** tách Payment/Orders ngay có lợi gì và đòi hỏi thêm hợp đồng, tracing, state machine, test chaos nào?
3. **Consistency vs. availability khi ERP offline:** có thể chấp nhận đặt chờ/backorder hay bắt buộc dừng xác nhận đơn?

Mỗi nhóm trình bày **sensitivity point** (tham số khiến thiết kế thay đổi, như cache hit ratio), **trade-off point** (quyết định tác động nhiều thuộc tính, như multi-region replication) và **risk** chưa có bằng chứng.

## 13. Đánh giá theo Well-Architected

Đây là bước rà soát **phương án cụ thể** sau khi nhóm đã có bản thiết kế và risk register.

| Góc đánh giá | Câu hỏi chất vấn | Bằng chứng kỳ vọng |
|---|---|---|
| **Operational Excellence** | Có thể triển khai, quan sát, xử lý và phục hồi mà không phụ thuộc một cá nhân? | IaC, pipeline, runbook, on-call, tracing, health checks |
| **Reliability** | Hỏng node, AZ, DB, queue, ERP hoặc region thì từng luồng nghiệp vụ ra sao? | Failure matrix, RTO/RPO drill, idempotency và đối soát |
| **Security** | Ai được truy cập dữ liệu nào, bí mật được bảo vệ và mọi lệnh có thể truy vết? | IAM/RBAC, phân loại dữ liệu, mã hóa, review luồng, pen test |
| **Performance Efficiency** | p95/throughput và khả năng scale có dựa trên tải đo được? | Workload model, load test, bottleneck, capacity/headroom |
| **Cost Optimization** | Chi phí thường/cao điểm/DR có thể dự đoán và quy trách nhiệm? | Bảng TCO, tag, quota, budget alert, kịch bản nhạy cảm |
| **Sustainability** | Tài nguyên nhàn rỗi, truyền dữ liệu, retention và workload dư thừa đã được xem xét? | Autoscaling, lifecycle, tỷ lệ cache, storage tiering |

Không nên đánh dấu PASS chỉ vì một dịch vụ cloud “có hỗ trợ” tính năng nào đó. Ví dụ **nhà cung cấp hỗ trợ multi-AZ** khác với việc ứng dụng đã được cấu hình, thực hành failover và kiểm chứng thành công. Đối với những mục chưa có bằng chứng, ghi **Open risk** kèm owner/hạn xác minh.

### 13.1. Một mẫu risk register có thể dùng trong review

| Rủi ro | Tác động | Cách giảm rủi ro | Chủ sở hữu / thời điểm |
|---|---|---|---|
| ERP không hỗ trợ reserve idempotent | Trùng giữ hàng, oversell, giao dịch khó phục hồi | Spike + API contract + reconciliation workflow | ERP owner / trước freeze thiết kế |
| Cache hit thực thấp hơn dự kiến | Origin quá tải, tăng chi phí | POC traffic thực, origin scaling, cache strategy | Web lead / trước load test |
| PSP webhook đến trễ/mất | Đơn đã thu tiền chưa được xử lý | Verify, reconciliation, pending state và alert | Payment lead / trước pilot |
| Failover region vượt RTO/RPO | Mất giao dịch hoặc không đạt phục hồi | DR architecture + diễn tập; duyệt mức rủi ro còn lại | SRE & business owner / trước go-live |
| Team chưa vận hành được platform | Sự cố kéo dài, release chậm | Chọn dịch vụ managed, on-call rehearsal, runbook | Engineering manager / trong pilot |

## 14. Bài tập thực hành dành cho người học

Hãy đóng vai kiến trúc sư chịu trách nhiệm trình bày với hội đồng gồm product owner, kỹ sư dữ liệu, security, SRE và đại diện vận hành cửa hàng. Không cần chọn vendor trước buổi thiết kế. Hãy nộp:

1. **Một trang bối cảnh:** mục tiêu, stakeholder, phạm vi và ba hành trình nghiệp vụ quan trọng.
2. **Bảng tối thiểu tám yêu cầu:** có ít nhất bốn NFR đo được, mức ưu tiên, owner và tiêu chí chấp nhận.
3. **Assumption register tối thiểu năm mục:** đánh dấu những giả định cần spike sớm và tác động nếu sai.
4. **Hai phương án kiến trúc** có sơ đồ, mô tả đường dữ liệu và phản ứng khi ERP hoặc PSP mất kết nối.
5. **Bảng so sánh và ba ADR:** ít nhất một ADR còn pending vì thiếu bằng chứng hoặc quyết định nghiệp vụ.
6. **Kế hoạch kiểm chứng:** đo tải, hỏng một AZ, dữ liệu trùng và quyền truy cập; ghi cách quan sát PASS/FAIL.
7. **Một thay đổi tình huống:** business owner báo rằng checkout phải tiếp tục nhận đơn khi ERP mất WAN 45 phút. Hãy giải thích phải thay **quy tắc bán vượt tồn/backorder, reservation, trạng thái đơn hoặc yêu cầu availability** thế nào; không tự cho rằng queue sẽ giải quyết được consistency.

### 14.1. Thang đánh giá 100 điểm

| Hạng mục | Điểm | Biểu hiện của bài làm tốt |
|---|---:|---|
| Hiểu nghiệp vụ, ranh giới và stakeholder | 15 | Nêu rõ luồng giá trị, phạm vi và sở hữu tích hợp |
| Yêu cầu đo được và ưu tiên | 15 | SLI/acceptance có mốc đo và nguồn phê duyệt |
| Giả định, phụ thuộc và risk | 15 | Nhận diện unknown quan trọng, có phép thử/owner |
| So sánh phương án và quyết định | 20 | Có ít nhất hai phương án khả thi, trade-off và ADR có căn cứ |
| Dữ liệu, giao dịch và an toàn | 15 | Giải quyết idempotency, inventory, PSP, quyền và ranh giới dữ liệu |
| Reliability, performance, cost, operations | 10 | Ước tính capacity, DR và chi phí có giới hạn rõ |
| Kế hoạch kiểm chứng và khả năng phản biện | 10 | Test có pass/fail; biết đổi thiết kế khi giả định sai |
| **Tổng** | **100** | |

Một bài có rất nhiều dịch vụ managed nhưng không chứng minh được trạng thái đơn hàng hoặc không xác định được **ai chấp thuận rủi ro** vẫn chưa đạt mục tiêu thực hành.

### 14.2. Câu hỏi nâng cao

- Nếu ngày khai trương đạt **10.000 request/s duyệt catalog** nhưng checkout chỉ tăng nhẹ, có nhất thiết tách Orders thành microservice không? Hay tối ưu cache, CDN, static content và database read path trước?
- Nếu doanh nghiệp mở sang hai quốc gia với quy định lưu trú dữ liệu khác nhau, cấu trúc account/region, key management, tenant và data flow thay đổi thế nào?
- Nếu cửa hàng được phép nhận **backorder có hạn mức**, state machine và SLA trả hàng cần thay đổi ra sao?
- Nếu trong năm đầu có thêm ba đội sản phẩm, ADR-001 còn hợp lý không? Nêu ít nhất hai dấu hiệu vận hành khiến cần xem xét tách domain.
- Nếu yêu cầu **RPO bằng 0 cho đơn đã được xác nhận** khi mất region, lựa chọn đồng bộ dữ liệu, độ trễ, chi phí và hành vi khi mất kết nối cần được thảo luận thế nào?

## 15. Lỗi thường gặp khi thiết kế từ đầu

**Chọn công nghệ trước khi biết yêu cầu:** dẫn đến thiết kế quá phức tạp hoặc bỏ sót bất biến nghiệp vụ. Hãy viết quality scenarios, constraints và data flow trước khi so tên sản phẩm.

**Đánh đồng giả định với sự thật:** “ERP chắc chắn support retry” khiến checkout sai khi mất mạng. Ghi nguồn, owner, phép thử và hạn xác thực.

**So sánh phương án bằng danh sách ưu điểm chung chung:** “microservices dễ scale” chưa đủ; cần trả lời module nào cần scale riêng, tần suất deploy, năng lực đội và chi phí quan sát.

**Gọi dịch vụ managed là bảo đảm SLO:** SLA của một thành phần không đại diện cho luồng checkout qua DB, ERP và PSP. Kiểm thử hành trình end-to-end trong lỗi thực.

**Quên dữ liệu và hiệu ứng bên ngoài:** rollback code không xóa được tiền đã thu; mất webhook không đồng nghĩa PSP chưa xử lý. Thiết kế idempotency và đối soát trước.

**Không tính các trạng thái trung gian:** thanh toán đang chờ, ERP timeout nhưng đã reserve, outbox chưa publish đều là trạng thái hợp lệ cần được mô hình hóa.

**Ước tính chi phí từ một con số trung bình:** bỏ qua tải chiến dịch, băng thông, lưu bản sao, log, DR và nhân sự trực. Luôn có kịch bản thường/cao điểm/sự cố.

**Không biết khi nào quyết định cần thay đổi:** ADR phải nêu giả định, hệ quả và điều kiện xem xét lại, không chỉ ghi “đã quyết định dùng X”.

## 16. Checklist trước khi trình duyệt kiến trúc

- [ ] Có mục tiêu nghiệp vụ, owner, phạm vi và sơ đồ ngữ cảnh hệ thống.
- [ ] Có requirement/NFR đo được và phân biệt yêu cầu đã duyệt với đề xuất.
- [ ] Có giả định chưa xác thực, mức ảnh hưởng, owner và kế hoạch xác minh.
- [ ] Có ít nhất hai phương án hợp lệ và bảng đánh đổi với điều kiện chặn.
- [ ] Đã mô tả dòng dữ liệu, nguồn ghi chuẩn, tính nhất quán và trạng thái khi phụ thuộc lỗi.
- [ ] Có sơ đồ mạng/biên tin cậy, phân quyền, mã hóa, secret, lưu trú và vòng đời dữ liệu.
- [ ] Có ước tính request, capacity, database, cache miss, queue và quota tích hợp.
- [ ] Có kịch bản lỗi node/AZ/region, RTO/RPO và bằng chứng phục hồi tương ứng.
- [ ] Có ước tính chi phí theo workload, phương án DR, quan sát và vận hành.
- [ ] Có ADR giải thích lựa chọn, phương án loại, hệ quả và điều kiện đổi quyết định.
- [ ] Có kế hoạch load/failure/security/DR test với tiêu chí PASS/FAIL và người chịu trách nhiệm.
- [ ] Có danh sách rủi ro còn mở và cơ chế Go/No-Go trước khi triển khai thực tế.

**Điểm mấu chốt của bài thực hành:** kiến trúc cloud tốt là một chuỗi lập luận có thể truy vết từ **yêu cầu → giả định → phương án → quyết định → bằng chứng kiểm chứng**. Khi có thay đổi về nghiệp vụ, dữ liệu, năng lực đội hoặc chi phí, bản thiết kế có thể được điều chỉnh một cách minh bạch mà vẫn giữ các bất biến quan trọng của hệ thống.
