# SLI, SLO và mối liên hệ với trải nghiệm người dùng

Một hệ thống microservices có thể báo mọi pod đều Running, CPU trung bình chỉ 30% và database không có lỗi kết nối, nhưng người mua vẫn không đặt được hàng. Một API trả HTTP 200 trong 200 ms nhưng response chứa trạng thái đơn sai; một trang sản phẩm hiển thị được nhưng không cho thêm vào giỏ; hoặc yêu cầu thanh toán thành công trong backend nhưng người dùng nhìn thấy vòng xoay chờ vô hạn. Các hiện tượng đó cho thấy **sức khỏe hạ tầng không đồng nhất với chất lượng trải nghiệm người dùng**.

**Service Level Indicator (SLI)** là phép đo về chất lượng dịch vụ, **Service Level Objective (SLO)** là mục tiêu đặt lên phép đo đó trong một khoảng thời gian, còn **Service Level Agreement (SLA)** là thỏa thuận về mức dịch vụ và hệ quả khi không đáp ứng (thường có tính hợp đồng). Khi thiết kế tốt, SLI/SLO chuyển câu hỏi chung chung “hệ thống có ổn không?” thành những câu kiểm tra được: *Bao nhiêu người thực hiện được hành động họ cần? Trong thời gian chấp nhận được? Dữ liệu họ nhận có đúng và đủ mới không?*

Bài này sử dụng ví dụ hệ thống thương mại điện tử có các microservice Catalog, Cart, Checkout, Order, Payment và Inventory. Con số SLO, ngưỡng latency và thời gian quan sát chỉ là ví dụ để học cách tư duy; không phải mục tiêu áp dụng mặc định cho mọi hệ thống.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt **SLI, SLO, SLA** và error budget; không nhầm chỉ số hạ tầng với chỉ số người dùng.
- Chọn hành trình người dùng quan trọng (user journey) và chuyển thành định nghĩa sự kiện tốt/xấu có thể đo.
- Thiết kế SLI về availability, latency, correctness, freshness và durability tùy ngữ cảnh.
- Xác định **mẫu số**, **tử số**, traffic đủ điều kiện, loại trừ và cửa sổ đo để tránh kết luận sai.
- Giải thích vì sao percentile, request success ratio, availability theo thời gian và synthetic test có thể mô tả những góc nhìn khác nhau.
- Tính error budget đúng đơn vị, dùng burn rate để ưu tiên xử lý sự cố mà không đánh đồng sự cố nhỏ với sự cố nghiêm trọng.
- Phân rã SLO đầu-cuối xuống microservice mà không tạo một rừng mục tiêu nội bộ vô nghĩa.
- Thiết kế instrumentation, dashboard, alert và quy trình review SLO gắn với thay đổi sản phẩm và mức độ tin cậy thực tế.

## 2. SLI, SLO, SLA và error budget

| Khái niệm | Câu hỏi trả lời | Ví dụ minh họa |
|---|---|---|
| SLI | Chúng ta đo chất lượng bằng phép đo nào? | Tỷ lệ checkout attempts hoàn tất hợp lệ |
| SLO | Trong khoảng thời gian nào, kết quả đo phải đạt mức nào? | Ít nhất 99,9% checkout attempts hợp lệ thành công trong 30 ngày trượt |
| SLA | Chúng ta đã cam kết gì với khách hàng, hậu quả khi không đạt là gì? | Điều khoản hợp đồng về mức dịch vụ và cơ chế bồi hoàn |
| Error budget | Phần không đạt mục tiêu được phép trong một cửa sổ SLO là bao nhiêu? | Với mục tiêu 99,9%, tối đa 0,1% eligible events không đạt |
| SLI specification | Định nghĩa chi tiết cách tính và nguồn dữ liệu | Điều kiện attempt, thành công, timeout, bot, hệ thống đo |
| Monitoring/alert policy | Khi nào cần thông báo và hành động? | Burn rate cao trên cửa sổ ngắn và dài |

Một SLO nên được diễn đạt bằng một phát biểu đầy đủ:

> Trong **30 ngày trượt**, ít nhất **99,9%** các lần **bắt đầu checkout hợp lệ** của khách hàng có thể **hoàn tất bằng một order xác nhận hợp lệ**, không tính các lần cố tình hủy của người dùng.

Phát biểu này tốt hơn “Checkout có uptime 99,9%” vì nó nói rõ người dùng, hành động, tiêu chí thành công, cửa sổ và phạm vi loại trừ.

**Phân biệt SLO và SLA:** một đội kỹ thuật có thể đặt SLO nội bộ chặt hơn hoặc khác với SLA thương mại. Không mặc định mọi SLO đều tạo nghĩa vụ pháp lý; cũng không dùng một số SLA chung làm chỉ số duy nhất để quản lý vận hành hàng ngày.

## 3. Bắt đầu từ hành trình người dùng, không từ dashboard CPU

Muốn liên kết độ tin cậy với trải nghiệm, trước hết xác định những **hành trình tạo giá trị**:

~~~text
Người dùng:
  Tìm sản phẩm -> Xem chi tiết -> Thêm vào giỏ
       -> Checkout -> Thanh toán -> Xem trạng thái đơn

Các dịch vụ có thể tham gia:
  Search/Catalog -> Cart -> Checkout/Order
                         -> Inventory/Payment
                         -> Notification/Tracking
~~~

Các hành trình không có cùng mức quan trọng:

- **Xem sản phẩm:** nhạy với latency, khả năng tìm thấy thông tin và độ mới giá/tồn kho.
- **Thêm giỏ:** cần ghi nhận lựa chọn đúng và phản hồi rõ ràng.
- **Checkout:** quan trọng về tỷ lệ hoàn thành, idempotency, không tạo đơn trùng và không bán vượt tồn kho.
- **Thanh toán:** cần xác nhận kết quả chính xác; trạng thái chưa biết có thể gây tác hại lớn dù endpoint phản hồi nhanh.
- **Xem trạng thái đơn:** cần eventual consistency có giới hạn, trạng thái không bị ghi lùi.
- **Thông báo:** cần giao đúng nội dung trong thời gian phù hợp, có thể ít quan trọng hơn luồng thanh toán trực tiếp.

**Bài học:** không nên sao chép một SLO 99,9% / 300 ms cho mọi endpoint. Hãy chọn một số ít hành trình quan trọng, mô tả kỳ vọng của người dùng rồi mới thiết kế phép đo.

### Từ lời phàn nàn đến chỉ số

| Người dùng phản ánh | SLI có thể hữu ích | Điều phép đo phải bao phủ |
|---|---|---|
| “Bấm thanh toán mà không biết đã trả tiền chưa” | Checkout completion/correctness | Kết quả cuối được hiển thị, không charge trùng |
| “Trang tìm kiếm mãi không hiện” | Search latency và success | Từ thao tác người dùng tới kết quả hữu ích |
| “Giá vừa đổi nhưng trang vẫn hiển thị cũ” | Catalog freshness | Độ trễ từ cập nhật gốc tới dữ liệu nhìn thấy |
| “Đơn đã tạo nhưng vài phút vẫn chưa thấy” | Order visibility freshness | Thời gian từ commit tới khi giao diện truy vấn được |
| “Một khách hàng lớn làm tất cả chậm” | Latency/SLO theo phân khúc | Phân rã tenant/tier để không che tác động |
| “Thanh toán đôi lúc bị trừ tiền hai lần” | Correctness invariant | Count charge thực theo payment attempt |

Các SLI nội bộ như CPU, memory, queue length, thread count, DB lock wait vẫn hữu ích để **chẩn đoán nguyên nhân**, nhưng hiếm khi là cách mô tả hoàn chỉnh về những gì khách hàng nhận được.

## 4. Chất lượng trải nghiệm có nhiều chiều

Một request trả 200 không nhất thiết đồng nghĩa “good user event”. Tùy sản phẩm, người dùng quan tâm các chiều khác nhau.

| Chiều | Ví dụ SLI | Điều cần tránh |
|---|---|---|
| Availability/success | Tỷ lệ thao tác đủ điều kiện thành công | Chỉ đếm pod Up |
| Latency | Tỷ lệ thao tác hoàn tất dưới ngưỡng chấp nhận | Chỉ nhìn latency trung bình |
| Correctness | Tỷ lệ kết quả đúng theo hợp đồng | Coi mọi HTTP 2xx là đúng |
| Freshness | Tỷ lệ dữ liệu mới hơn ngưỡng chấp nhận | Cache trả dữ liệu cũ nhưng vẫn 200 |
| Durability | Tỷ lệ dữ liệu xác nhận vẫn tồn tại sau lỗi | Chỉ kiểm tra ACK mà không kiểm tra persistence |
| Coverage/partial experience | Tỷ lệ hành trình hoàn tất với đủ chức năng quan trọng | Coi trang render rỗng là success |
| Consistency | Tỷ lệ đọc trả trạng thái hợp lệ theo quy tắc | Ghi lùi hoặc hiển thị mâu thuẫn |
| Time to recover | Thời gian chức năng phục hồi sau lỗi | Chỉ nhìn thời gian restart pod |

Chưa chắc cần tất cả những chiều này thành SLO riêng. Nếu một sản phẩm có đặc trưng đặc biệt, ví dụ hệ thống phân tích chấp nhận dữ liệu trễ 5 phút, freshness có thể quan trọng hơn độ trễ API truy vấn 20 ms.

## 5. Định nghĩa “good event” và “eligible event”

Với SLI theo request/event, công thức khái niệm:

~~~text
SLI = số good events / số eligible events
~~~

Ở đây, **eligible event** là một sự kiện thuộc phạm vi chất lượng dịch vụ mà đội đã định nghĩa. **Good event** là một eligible event đáp ứng tiêu chí chất lượng. Cần viết quy tắc phân loại trước khi tính.

Ví dụ SLI của Checkout:

| Tình huống | Có đưa vào mẫu số? | Có tính là good? | Giải thích |
|---|---|---|---|
| Khách bắt đầu checkout hợp lệ, nhận order đã xác nhận | Có | Có | Hoàn tất hành trình |
| Khách checkout hợp lệ, Payment timeout và không thấy kết quả | Có | Không | Trải nghiệm không đạt |
| Payment đã charge nhưng UI trả lỗi, khách không thấy order | Có | Không | Kết quả hiển thị không đạt; cần kiểm tra correctness |
| Khách chủ động bấm hủy trước khi xác nhận | Theo định nghĩa, thường loại khỏi hoàn tất cưỡng bức | Không áp dụng | Không nên coi lựa chọn tự nguyện là lỗi hệ thống |
| Payload sai do bot/abuse bị chặn theo chính sách | Có thể loại trừ nếu quy tắc rõ và audit được | Không áp dụng | Không nên dùng loại trừ tùy tiện để làm đẹp SLI |
| Khách thao tác hợp lệ nhưng backend trả 4xx do bug mapping | Có | Không | Không thể coi mọi 4xx là “lỗi phía client” |
| Khách retry cùng idempotency key sau mất response | Theo quy tắc logical attempt | Phụ thuộc outcome cuối | Không đếm một thao tác người dùng thành nhiều nhu cầu độc lập |
| Hệ thống trả response 200 nhưng ghi sai số tiền | Có | Không | Correctness phải quan trọng hơn status code |

**Mẫu số quyết định ý nghĩa SLI.** Nếu chỉ tính request đến HTTP handler mà bỏ traffic bị gateway từ chối, DNS lỗi hoặc client không kết nối được, đo được service-side success chứ chưa phải trải nghiệm đầu-cuối. Nếu chỉ đếm order đã hoàn tất mà bỏ attempt thất bại, SLI sẽ luôn đẹp giả tạo.

### SLI theo logical operation hay transport attempt?

Một người bấm “Thanh toán” một lần nhưng client và gateway retry thành ba HTTP requests. SLI theo HTTP requests có 3 sự kiện; SLI theo logical checkout chỉ có 1 attempt. Cả hai đều có thể hữu ích, nhưng phản ánh hai ý nghĩa khác nhau.

- **Transport request SLI:** tốt cho kiểm soát HTTP service và capacity.
- **User action/transaction SLI:** gần với người dùng hơn; cần correlation/idempotency key và trạng thái cuối.
- **Dependency attempt SLI:** đo chất lượng một upstream theo từng lần gọi; giúp tìm nguyên nhân.

Nên đặt tên và tài liệu rõ để không so sánh nhầm các loại phép đo.

## 6. Availability SLI: làm được việc hay chỉ trả được HTTP?

Một SLI đơn giản:

~~~text
Checkout success ratio =
  số checkout attempts thành công hợp lệ
  -------------------------------------
  tổng số checkout attempts đủ điều kiện
~~~

Giả sử trong 30 ngày có 1.000.000 checkout attempts hợp lệ và 998.800 attempts thành công:

~~~text
SLI = 998.800 / 1.000.000 = 99,88%
~~~

Nếu SLO là 99,9%, mức thực tế **chưa đạt**. Con số 99,88% có thể nghe rất cao, nhưng 1.200 lần checkout thất bại có thể ảnh hưởng trực tiếp tới doanh thu và niềm tin của khách hàng.

Ngược lại, endpoint kỹ thuật /health trả 100% thành công không chứng minh checkout thành công; health có thể bỏ qua database hoặc third-party payment. SLI end-to-end phải chọn vị trí đo phù hợp với hành trình.

### Chọn outcome chính xác

Một API có thể trả:

- 2xx khi order đã xác nhận.
- 202 Accepted khi công việc được xếp hàng, kết quả chưa biết.
- 4xx do user nhập dữ liệu sai theo hợp đồng.
- 5xx do hệ thống lỗi.
- Timeout ở client dù server đã commit.

Định nghĩa success cần dựa trên hợp đồng sản phẩm. Ví dụ 202 chỉ nên được xem là thành công cho **SLI nhận yêu cầu** nếu hợp đồng là nhận vào queue; nó chưa đủ để xem là thành công cho **SLI hoàn tất checkout**, vốn cần kết quả cuối được xác nhận trong cửa sổ thích hợp.

## 7. Latency SLI: người dùng chờ bao lâu?

Latency có thể đo từ nhiều vị trí:

~~~text
User click
  |-- Browser processing/network
  |-- CDN/API Gateway
  |-- Checkout API
  |-- Inventory + Payment + DB
  |-- Response truyền ngược
  |-- UI render/confirmation
User thấy trạng thái cuối
~~~

**Server-side latency** đo phần ứng dụng nhìn thấy. **Client-side latency** hoặc Real User Monitoring (RUM) có thể bao gồm thêm mạng và xử lý UI. Hai phép đo không thay thế nhau.

Một SLI latency theo ngưỡng:

~~~text
Checkout latency SLI =
  số eligible checkout attempts thành công trong <= 1.500 ms
  ----------------------------------------------------------
  tổng số eligible checkout attempts
~~~

Nếu chỉ tính latency của những request đã thành công và bỏ request timeout khỏi mẫu số, dashboard có thể cho thấy “99% request thành công nhanh” ngay cả khi số request thất bại tăng cao. Có thể tách availability SLI và latency-on-success SLI, nhưng cần biểu diễn rõ mối quan hệ, hoặc sử dụng **good event** kết hợp vừa thành công vừa đủ nhanh để tránh hiểu nhầm.

### Percentile khác threshold-ratio

| Phép đo | Câu hỏi trả lời |
|---|---|
| p50 latency | Một nửa request có latency không lớn hơn giá trị nào? |
| p95 latency | 95% request có latency không lớn hơn giá trị nào? |
| p99 latency | 99% request có latency không lớn hơn giá trị nào? |
| Tỷ lệ request dưới 800 ms | Bao nhiêu phần trăm thao tác đáp ứng ngưỡng 800 ms? |

Ví dụ mục tiêu “99% request tốt dưới 800 ms” dễ liên hệ error budget vì mỗi eligible event được phân loại tốt/xấu. Mục tiêu “p99 <= 800 ms” có thể diễn đạt một ý gần giống trong một phạm vi thời gian, nhưng cách aggregate percentile, mức bao phủ traffic và xử lý lỗi có thể khác. Không lấy trung bình p99 của từng pod để suy ra p99 toàn hệ thống.

### Timeout và phản hồi không hoàn chỉnh

Nếu browser chờ 30 giây rồi bỏ cuộc, trong khi server xử lý trong 100 ms sau khi nhận request, server-side histogram có thể bỏ qua thời gian nghẽn trước server. Cần theo dõi timeout ở gateway/client và trải nghiệm thực sự.

Đặc biệt, thời gian phản hồi nhanh với một kết quả sai (ví dụ đánh dấu payment thất bại dù đã charge) là vấn đề correctness, không được che bởi latency SLI đẹp.

## 8. Correctness SLI và invariant nghiệp vụ

Trong thương mại điện tử, tính đúng có thể quan trọng hơn thời gian phản hồi của một số thao tác:

- Không thu tiền hai lần cho cùng payment attempt.
- Không bán vượt số lượng tồn hợp lệ.
- Order đã xác nhận không biến mất hoặc bị ghi lùi trạng thái.
- Tổng tiền, thuế và phí phù hợp hợp đồng.
- Sự kiện PaymentCompleted không bị xử lý hai lần tạo thêm tác động.

Một correctness SLI minh họa:

~~~text
Payment correctness ratio =
  số payment attempts có kết quả được đối soát chính xác
  -----------------------------------------------------
  số payment attempts đủ điều kiện đã được quyết toán/đối soát
~~~

Cần nói rõ **độ trễ của kết quả đối soát**: nếu mất nhiều giờ mới xác nhận được tính đúng, SLI correctness có thể là phép đo trễ. Nên kết hợp kiểm tra nhanh (idempotency, transaction, invariant) với reconciliation định kỳ.

Một SLI kiểu “0 giao dịch bị charge trùng” có thể phù hợp dưới dạng **invariant hoặc mức rủi ro không được phép**, không nhất thiết phải gộp cơ học vào một availability SLO 99,9%. Đừng biến “cho phép 0,1% lỗi” thành giấy phép chấp nhận charge trùng hoặc mất tiền.

### Các nguồn đo correctness

- Ledger/record của provider và của hệ thống được đối chiếu.
- Bảng order và payment attempt với unique business key.
- Event audit/outbox/inbox và dữ liệu đã commit.
- Hệ thống đối soát độc lập.
- Mẫu kiểm tra kết quả nghiệp vụ có oracle đáng tin.

**Nguồn đo phải đủ độc lập và đáng tin.** Nếu chính code sinh lỗi cũng tự ghi metric “success” trước khi database commit, metric có thể báo thành công cho giao dịch chưa thật sự bền vững.

## 9. Freshness SLI: dữ liệu có đủ mới?

Một service có thể trả 200 rất nhanh từ cache nhưng dữ liệu đã cũ 20 phút. Nếu người dùng cần thấy trạng thái đơn sau khi thanh toán trong vòng 10 giây, response nhanh mà stale vẫn là trải nghiệm kém.

Ví dụ:

~~~text
Order visibility freshness SLI =
  số order updates hiển thị cho người dùng trong <= 10 giây
  --------------------------------------------------------
  tổng số order updates đủ điều kiện
~~~

Các timestamp liên quan:

- `committedAt`: thời điểm cập nhật nghiệp vụ được commit ở nguồn có thẩm quyền.
- `publishedAt`: thời điểm event được phát ra broker.
- `consumedAt`: thời điểm consumer nhận event.
- `visibleAt`: thời điểm dữ liệu có thể được đọc bởi bề mặt người dùng.

Cần xác định đồng hồ, độ lệch clock giữa service và cách theo dõi dữ liệu bền vững. Trong một số hệ thống có thể dùng sequence/offset hoặc timestamp do một nguồn tin cậy cấp để tránh sai do đồng hồ lệch.

### Các cách đo freshness

- End-to-end synthetic write rồi truy vấn read model cho đến khi cập nhật hiển thị.
- Metric về consumer lag + thời gian xử lý và materialized view lag.
- Sample các entity được cập nhật, so sánh source version với read model version.
- Audit tiến trình cập nhật ở nhiều hop bằng correlation.

Không đồng nhất Kafka consumer lag theo records với độ trễ trải nghiệm theo giây: một partition có 1.000 records lag có thể tương ứng vài giây hoặc nhiều phút tùy tốc độ và mức tải.

## 10. Durability và data-loss SLI

Đối với đơn đã xác nhận hoặc giao dịch tài chính, người dùng kỳ vọng dữ liệu vẫn tồn tại sau restart, failover và sự cố hạ tầng.

Một phép đo minh họa:

~~~text
Order durability SLI =
  số order đã xác nhận có bản ghi còn đọc được/đối soát được
  --------------------------------------------------------
  số order đã được xác nhận thuộc kỳ đánh giá
~~~

Cần làm rõ thời gian kiểm tra, nơi đọc dữ liệu và điều kiện consistency. Một order được tạo nhưng trả response trước khi commit bền vững có thể làm SLI success giả cao và durability thấp.

Những kiểm thử hỗ trợ:

1. Commit DB rồi restart service, xác minh dữ liệu còn.
2. Crash sau commit nhưng trước khi ACK broker; replay không tạo order trùng.
3. Failover primary/replica, kiểm tra RPO đã cam kết.
4. Khôi phục backup vào môi trường cô lập, kiểm tra dữ liệu và thời gian hồi phục.
5. So sánh số order được xác nhận với ledger và event log.

Độ bền dữ liệu thường đòi assurance và quy trình kiểm thử riêng, không thể được suy ra chỉ từ uptime.

## 11. Chọn SLO bắt đầu từ kỳ vọng sản phẩm

Không nên chọn 99,999% chỉ vì một đội khác có mục tiêu đó. SLO cao kéo theo chi phí, độ phức tạp và hạn chế tốc độ phát hành; SLO quá thấp có thể làm người dùng chịu tổn hại không chấp nhận được.

Một quá trình chọn mục tiêu:

1. **Xác định hành trình:** người dùng làm gì, tác động khi thất bại là gì?
2. **Thu thập baseline:** SLI thực tế trong các cửa sổ đủ đại diện, kể cả giờ cao điểm.
3. **Tham khảo kỳ vọng:** nghiên cứu người dùng, ticket hỗ trợ, hành vi bỏ giỏ, tỷ lệ chuyển đổi và điều khoản sản phẩm.
4. **Phân loại tác hại:** khó chịu nhẹ, mất doanh thu, vi phạm dữ liệu, rủi ro an toàn hoặc pháp lý.
5. **Chọn ngưỡng:** giới hạn không ảnh hưởng đáng kể tới người dùng hoặc ràng buộc kinh doanh.
6. **Chọn time window:** phản ánh chu kỳ sử dụng và có thể điều hành.
7. **Kiểm tra khả thi:** đo SLI có đáng tin, có owner, có playbook, có giải pháp khi vi phạm?
8. **Công bố và review:** mục tiêu có thể được điều chỉnh qua dữ liệu và quyết định sản phẩm có chủ đích.

### Ví dụ danh mục SLO

| User journey | SLI minh họa | SLO giả định |
|---|---|---|
| Xem sản phẩm | Tỷ lệ xem thông tin hợp lệ thành công trong <= 800 ms | >= 99,0% trong 28 ngày |
| Thêm giỏ hàng | Tỷ lệ thao tác ghi giỏ thành công đúng dữ liệu | >= 99,9% trong 30 ngày |
| Checkout | Tỷ lệ eligible attempts hoàn tất bằng order đúng | >= 99,9% trong 30 ngày |
| Xem trạng thái đơn | Tỷ lệ cập nhật hiển thị <= 10 giây | >= 99,5% trong 30 ngày |
| Thanh toán | Không charge trùng, kết quả đối soát nhất quán | Invariant nghiêm ngặt + giám sát riêng |

Các số liệu là ví dụ để minh họa cách thiết kế nhiều chiều SLO. **Đừng biến các số đó thành tiêu chuẩn chung** nếu chưa có dữ liệu đo và quyết định sản phẩm.

## 12. Request-based SLO và time-based SLO

Hai loại SLO hay bị trộn lẫn:

**Request-based SLO:** đánh giá tỷ lệ sự kiện người dùng đủ điều kiện.

~~~text
good requests / eligible requests
~~~

**Time-based SLO:** đánh giá tỷ lệ các khoảng thời gian dịch vụ đạt điều kiện, ví dụ số phút tốt/tổng số phút trong 30 ngày.

~~~text
good minutes / total minutes
~~~

Hai loại cho kết quả khác nhau khi lưu lượng theo thời gian không đồng đều.

Ví dụ: outage 5 phút vào lúc 3 giờ sáng có 10 request; outage 5 phút trong flash sale có 100.000 request. Time-based SLO có thể coi hai outage bằng nhau về phút hỏng, còn request-based SLO phản ánh số thao tác bị ảnh hưởng khác nhau.

Không có loại nào đúng trong mọi tình huống. Chọn theo tác hại đối với người dùng, mức traffic, tính liên tục của chức năng và khả năng đo. Với service ít traffic, request-based có thể dao động mạnh hoặc không có đủ mẫu; có thể bổ sung synthetic checks hoặc một time-based measure.

### Một số bẫy của “uptime 99,9%”

Nếu dựa vào ping một endpoint mỗi phút, một lần lỗi ngắn giữa hai lần ping có thể bị bỏ sót. Nếu chỉ đo pod readiness, người dùng có thể vẫn không checkout được. Nếu probe từ một khu vực địa lý, kết quả có thể không đại diện cho mọi vùng người dùng. Nên tài liệu hóa nguồn quan sát và độ bao phủ của phép đo.

## 13. Cửa sổ đo: 30 ngày trượt khác tháng lịch

Một SLO cần time window rõ:

- **Rolling 30 days:** tại mỗi thời điểm nhìn lại 30 ngày gần nhất; thuận tiện cho đánh giá liên tục.
- **Calendar month:** từ đầu tới cuối tháng; dễ liên hệ báo cáo tháng nhưng số ngày có thể khác nhau.
- **28-day rolling:** khoảng thời gian cố định bốn tuần, đôi khi thuận tiện cho nhịp vận hành.
- **Weekly/seasonal:** có thể phù hợp một số workload nhưng dễ dao động do số mẫu nhỏ.

Không được diễn đạt “99,9% mỗi tháng” rồi vừa tính bằng tháng 28 ngày, vừa lấy error budget 30 ngày, vừa alert theo 31 ngày mà không chuẩn hóa.

### Khối lượng request thay đổi

Request-based error budget cũng thay đổi khi traffic thay đổi. Một hệ thống có 1 triệu eligible requests trong một cửa sổ với SLO 99,9% sẽ cho phép tối đa 1.000 bad events theo phép tính phần trăm; nếu có 10 triệu eligible requests, budget về số request là 10.000. Điều này không có nghĩa 10.000 thất bại đều ít gây hại; cần xem mức tác động, nhóm người dùng và những bất biến không được phép vi phạm.

## 14. Error budget: “chi phí cho phần không đạt”

Với request-based availability SLO:

~~~text
SLO target = 99,9%
Allowed bad ratio = 1 - 0,999 = 0,001 = 0,1%

Error budget (events) = total eligible events × 0,001
Budget consumed ratio = bad events / error budget
~~~

Ví dụ 2.000.000 eligible checkout attempts trong 30 ngày:

~~~text
Allowed bad events = 2.000.000 × 0,001 = 2.000
Actual bad events  = 1.200
Budget consumed    = 1.200 / 2.000 = 60%
Budget remaining   = 800 events, tương đương 40% budget
Current SLI        = 99,94%
~~~

Ở đây SLI 99,94% đạt mục tiêu 99,9%. Nhưng nếu một outage tiếp theo gây thêm 1.500 bad attempts trước khi cửa sổ trượt thay đổi đáng kể, nhóm có thể vượt budget.

### Error budget theo thời gian

Nếu đo một chức năng theo **time-based availability** trong đúng 30 ngày (30 × 24 × 60 = 43.200 phút), SLO 99,9% tương ứng tối đa:

~~~text
30 ngày × 24 giờ × 60 phút × 0,001
= 43,2 phút
= 43 phút 12 giây
~~~

Đây là phép quy đổi **theo thời gian**, không phải quyền được “down đúng 43 phút” cho một request-based SLO. Nếu SLO theo tỷ lệ request, không thể đổi trực tiếp ra số phút outage khi traffic thay đổi.

### Budget policy để ra quyết định

Error budget không phải giấy phép chủ động gây sự cố. Nó giúp nhóm cân bằng **độ tin cậy** với **tốc độ thay đổi**:

- Budget còn nhiều và SLI ổn định: có thể tiếp tục rollout theo rủi ro đã đánh giá.
- Budget tiêu nhanh: tăng mức kiểm soát rollout, xử lý nguyên nhân lỗi và tập trung giảm bad events.
- Budget cạn: cân nhắc tạm dừng các thay đổi rủi ro cao, ngoại trừ sửa lỗi/bảo mật cần thiết.
- Nếu đo SLI không đáng tin: sửa hệ thống đo trước khi dùng budget để quyết định lớn.

Không áp dụng chính sách “đóng băng toàn bộ release” máy móc nếu bản release cần thiết để khôi phục chất lượng hoặc vá lỗ hổng nghiêm trọng. Quyết định phải dựa trên rủi ro và tác động thực tế.

## 15. Burn rate và cảnh báo khi budget bị tiêu quá nhanh

**Burn rate** là tốc độ tạo bad events so với tốc độ cho phép theo SLO.

Với SLO 99,9%, tỷ lệ lỗi cho phép là 0,1%. Nếu trong cửa sổ hiện tại bad event ratio là 1%:

~~~text
Burn rate = observed bad ratio / allowed bad ratio
          = 1% / 0,1%
          = 10×
~~~

Nghĩa là budget đang bị tiêu nhanh gấp 10 lần tốc độ cho phép, nếu traffic và rate duy trì trong điều kiện đo tương ứng.

Một cảnh báo kiểu multi-window thường quan sát đồng thời:

- **Cửa sổ ngắn:** phát hiện sự cố gần đây có tốc độ tiêu budget lớn.
- **Cửa sổ dài:** tránh báo chỉ vì một spike rất ngắn hoặc lượng mẫu quá nhỏ.
- **Nhiều mức độ:** page khi có rủi ro mất budget đáng kể nhanh chóng; ticket khi tình trạng nhỏ nhưng kéo dài.

Ví dụ, với error budget 30 ngày, burn rate 10× kéo dài 1 giờ sẽ tiêu khoảng:

~~~text
10 × (1 giờ / 720 giờ) ≈ 1,39% tổng budget
~~~

Cách ước lượng trên áp dụng cho **time-normalized constant-rate model**; với request-based SLO, lượng budget tiêu thực tế phụ thuộc số eligible events và lưu lượng trong khoảng đó. Không diễn giải chính xác phần trăm budget theo giờ nếu traffic có thay đổi mạnh.

**Không đặt alert chỉ dựa vào p99 vượt ngưỡng một phút.** Có thể cần low-traffic guard, đủ sample size, cửa sổ dài/ngắn và mức tác động người dùng. Cảnh báo nên đại diện cho khả năng vi phạm SLO và tạo hành động vận hành rõ ràng.

## 16. SLO không thay thế alert kỹ thuật

Có hai lớp tín hiệu:

**Tín hiệu triệu chứng (symptom):** checkout success ratio giảm, người dùng thấy timeout, dữ liệu quá cũ. Dùng để định nghĩa SLI/SLO và cảnh báo mức ảnh hưởng.

**Tín hiệu nguyên nhân (cause):** DB connection pool cạn, Kafka lag, CPU saturation, GC pause, pod restart, cache miss tăng. Dùng để điều tra và chủ động phòng ngừa.

Một dashboard hữu ích đặt hai lớp cạnh nhau:

~~~text
User experience:
  checkout_good_ratio, checkout_latency_good_ratio,
  order_visibility_freshness, payment_correctness

Service and dependency health:
  HTTP 5xx, retry, timeout, queue lag,
  DB lock wait, pool wait, saturation, GC
~~~

Một service có nhiều pod restart nhưng không vi phạm SLO vẫn đáng điều tra; tuy nhiên mức độ ưu tiên page có thể khác sự cố checkout thất bại hàng loạt. Ngược lại, nếu SLO xấu nhưng metric hạ tầng đều đẹp, cần xem lại nơi đo hoặc bug nghiệp vụ.

## 17. Chọn điểm đo end-to-end

Một hệ thống có các hop:

~~~text
Browser -> CDN/Gateway -> Checkout -> Order
                           |           |
                           |           +-> Inventory
                           +--------------> Payment
                                     |
                                     v
                              Order confirmed
~~~

Có các vị trí đo với trade-off khác nhau:

| Vị trí | Đo được | Có thể bỏ sót |
|---|---|---|
| Browser/RUM | Từ tương tác tới UI hiển thị; mạng và frontend | Người dùng bị chặn trước khi script chạy, ad blocker, sampling |
| CDN/API Gateway | Request đi vào edge, status/latency ở ranh giới ngoài | Client render, network phía client, correctness trong UI |
| Checkout application | Kết quả nghiệp vụ sau khi service xử lý | Request không tới được app, UI/edge |
| Payment adapter | Độ tin cậy dependency Payment | Trải nghiệm checkout tổng thể |
| Synthetic test | Hành trình chủ động thử theo kịch bản định sẵn | Phân bố thiết bị, mạng và dữ liệu thật của mọi người dùng |
| Business analytics/ledger | Hoàn tất order/charge đúng | Có thể cập nhật trễ, cần làm sạch dữ liệu |

Nên dùng **một nguồn chính** để tính SLO với định nghĩa rõ; các nguồn khác đối chiếu và tìm điểm mù. Đừng lấy một nguồn SLI client-side khi thiếu dữ liệu rồi tùy ý thay bằng backend-side số đẹp hơn mà không đánh dấu khác biệt.

### RUM và synthetic bổ sung nhau

- **RUM:** phản ánh traffic thực ở những client có telemetry; có thiên lệch do thiết bị, mạng, browser, quyền riêng tư và tỷ lệ sampling.
- **Synthetic monitoring:** chạy kiểm tra theo lịch trên đường nghiệp vụ cố định; phát hiện một số lỗi cả khi traffic thực thấp.
- **Server instrumentation:** giúp phân loại status, route và dependency latency; thường có độ phủ ổn định hơn đối với request đã đến server.

Có thể kết hợp cả ba để đánh giá trải nghiệm, nhưng phải tránh cộng lẫn mẫu số hoặc suy ra tỷ lệ người dùng thất bại chỉ từ synthetic probes.

## 18. Instrumentation cho logical checkout attempt

Đo thao tác người dùng khác với đếm mỗi request HTTP. Một ví dụ sự kiện:

~~~json
{
  "operationId": "checkout-42",
  "journey": "checkout",
  "eligible": true,
  "outcome": "success",
  "durationMs": 870,
  "completed": true,
  "source": "checkout-orchestrator",
  "environment": "production"
}
~~~

Trong thực tế, không đưa payment token, dữ liệu thẻ, địa chỉ cá nhân hoặc thông tin nhạy cảm vào metric label. `operationId` có cardinality cao nên lưu ở trace/log có kiểm soát hoặc bảng nghiệp vụ, không làm label Prometheus cho từng operation.

### Cách xác định thời điểm kết thúc

Nếu checkout được xử lý đồng bộ, completion có thể là response xác nhận đúng. Nếu checkout là quy trình bất đồng bộ, cần một trạng thái terminal hoặc kết quả cuối trong một time window: `confirmed`, `rejected`, `timed_out`, `cancelled_by_user` tùy hợp đồng.

Điểm khó: một attempt đang Pending không nên bị bỏ mãi khỏi mẫu số, vì SLI sẽ đẹp giả tạo. Cần quy tắc khi nào pending quá hạn trở thành bad event, cách late success được phản ánh và cách tránh đếm lặp.

### Dedupe theo operation ID

Browser có thể retry, gateway retry, worker replay. Nếu một logical checkout tạo ba transport attempts, hệ thống đo ở lớp nghiệp vụ cần quy về **một kết quả cuối của một operation**, nếu SLI được định nghĩa theo logical operation. Event logging với at-least-once delivery phải tự deduplicate theo stable ID.

## 19. Ví dụ Java: tách business outcome khỏi metric ghi nhận

Ví dụ minh họa một adapter ghi nhận thao tác đã **có kết quả xác định**. Nó không phụ thuộc framework metrics cụ thể để làm rõ vị trí tạo phép đo.

~~~java
public enum CheckoutOutcome {
    SUCCESS,
    SERVER_FAILURE,
    USER_CANCELLED,
    TIMED_OUT
}

public record CheckoutObservation(
        String operationId,
        CheckoutOutcome outcome,
        long durationMillis
) {}

public interface CheckoutSliRecorder {
    void record(CheckoutObservation observation);
}
~~~

Service nghiệp vụ gọi recorder sau khi xác định kết quả theo contract:

~~~java
// Pseudocode cho kiến trúc, không phải implementation đầy đủ.
long startedNanos = System.nanoTime();
CheckoutOutcome outcome = null;

try {
    CheckoutReceipt receipt = checkoutOrchestrator.execute(command);
    outcome = receipt.confirmed()
            ? CheckoutOutcome.SUCCESS
            : CheckoutOutcome.SERVER_FAILURE;
    return receipt;
} catch (TimeoutException e) {
    outcome = CheckoutOutcome.TIMED_OUT;
    throw e;
} finally {
    long elapsedMillis =
            java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startedNanos);
    if (outcome != null) {
        sliRecorder.record(new CheckoutObservation(
            command.operationId(), outcome, elapsedMillis));
    }
}
~~~

**Giới hạn quan trọng:** đoạn code minh họa không tự cung cấp correctness cho luồng bất đồng bộ hoặc thao tác đã commit nhưng response mất. Nếu outcome thực tế chưa biết lúc finally chạy, không nên tự gán chắc chắn thất bại nghiệp vụ. Có thể ghi metric transport timeout riêng, rồi xử lý SLI logical operation dựa trên trạng thái cuối/reconciliation.

`System.nanoTime()` phù hợp đo duration trong cùng process, không dùng để so timestamp giữa nhiều máy. Với quy trình nhiều service, cần trace/correlation và mốc thời gian từ nguồn tin cậy theo thiết kế.

### Gắn event vào metric backend

Một recorder thực có thể phát bộ đếm với nhãn có cardinality nhỏ:

~~~text
checkout_attempts_total{outcome="success"}
checkout_attempts_total{outcome="server_failure"}
checkout_attempts_total{outcome="timed_out"}

checkout_duration_seconds_bucket{outcome="success",le="1.5"}
~~~

Các tên metric chỉ minh họa, phải được định nghĩa cùng đội observability. Nếu chỉ có counter của HTTP request attempts, không nên đặt tên như đang đo logical checkout attempts.

## 20. Ví dụ PromQL tính SLI từ counters

Giả sử instrumentation đã thực hiện dedupe logical attempt, và bộ đếm có những outcome:

- `success`: hoàn tất hợp lệ;
- `server_failure`: lỗi thuộc phạm vi SLI;
- `timed_out`: quá hạn xử lý;
- `user_cancelled`: hủy tự nguyện, không thuộc eligible denominator.

Khi đó truy vấn khái niệm cho tỷ lệ trong cửa sổ 30 ngày:

~~~promql
sum(increase(checkout_attempts_total{outcome="success"}[30d]))
/
sum(increase(checkout_attempts_total{
  outcome=~"success|server_failure|timed_out"
}[30d]))
~~~

Đây là công thức minh họa; cú pháp và nguồn metric phải phù hợp backend Prometheus đang dùng. Cần xử lý trường hợp mẫu số bằng 0, thiếu dữ liệu scrape, counter reset và sai lệch do thời điểm thu thập. `increase()` là ước lượng dựa trên mẫu counters; không phải phép kiểm toán tuyệt đối từng checkout record khi có thiếu scrape hoặc retention không đủ.

Nếu mục tiêu latency là “eligible attempts phải vừa thành công vừa hoàn tất <= 1,5 giây”, có thể instrument riêng `checkout_good_total` ở thời điểm kết quả cuối được xác định, rồi chia cho eligible denominator cùng quy tắc:

~~~promql
sum(increase(checkout_good_total[30d]))
/
sum(increase(checkout_eligible_total[30d]))
~~~

Định nghĩa hai counters phải nhất quán: mỗi eligible operation chỉ làm tăng denominator một lần và tối đa một lần tăng numerator. Không cộng một attempt vào numerator tại thời điểm HTTP 200 nếu transaction chưa thật sự đạt điều kiện nghiệp vụ.

### Histograms và percentile

Histogram thích hợp để đo phân phối duration ở nhiều instance. Nếu dùng `histogram_quantile()`, cần aggregate theo bucket đúng và cân nhắc bucket boundaries/độ sai xấp xỉ. Một tỷ lệ good events theo ngưỡng có thể tính từ bucket, miễn bucket chứa đầy đủ những event hợp lệ và trạng thái failure được xử lý phù hợp.

Không lấy `avg(instance_p99)` làm p99 toàn dịch vụ: percentile không cộng gộp đơn giản. Dùng histogram/distribution aggregation hoặc dữ liệu raw phù hợp để tổng hợp across instances.

## 21. Latency, retry và sự che khuất lỗi

Giả sử Checkout gọi Payment. Lần đầu timeout sau 800 ms; retry lần hai thành công sau 700 ms. HTTP response cuối trả 200 và tổng thời gian 1.500 ms, chưa kể backoff.

Nếu chỉ đếm HTTP status cuối, availability có vẻ đạt. Nhưng người dùng vẫn phải chờ lâu; nhiều retries có thể làm tăng tải dependency và timeout cho các khách khác.

Các phép đo cần phối hợp:

- **User journey latency** gồm toàn bộ thời gian retry và backoff.
- **Service request latency** tại mỗi service.
- **Dependency attempts/error ratio** để phát hiện một downstream đang kém.
- **Retry attempts per logical operation** để theo dõi tải nhân lên.
- **Business outcome correctness** để chống charge trùng và xử lý kết quả chưa biết.

Không nhầm lần thử đầu thất bại với logical checkout thất bại nếu hệ thống tự phục hồi trong thời hạn hợp đồng. Ngược lại, không cho phép retry vô hạn để tăng tỷ lệ success nhưng phá ngưỡng latency hoặc tạo side effect trùng.

## 22. SLO đầu-cuối và SLO từng microservice

Hành trình checkout phụ thuộc nhiều thành phần:

~~~text
Checkout user journey SLO
    |
    +-- API Gateway
    +-- Checkout Orchestrator
    +-- Order DB
    +-- Inventory reservation
    +-- Payment provider / adapter
    +-- Read model hiển thị xác nhận
~~~

Mỗi thành phần có thể có SLI kỹ thuật riêng, nhưng người dùng thường chỉ quan tâm **checkout hoàn tất đúng và đủ nhanh**.

### Nguy cơ quản lý chỉ bằng service-level SLO

Giả sử Order, Inventory và Payment đều đạt 99,9% availability trên những tập request riêng. Không thể kết luận checkout cũng đạt 99,9%. Nếu ba bước bắt buộc được gọi tuần tự và lỗi độc lập, phép xấp xỉ tích các tỷ lệ thành công sẽ thấp hơn tỷ lệ của từng bước. Khi lỗi có tương quan hoặc hệ thống có retry/fallback, mô hình còn phức tạp hơn.

Một phép nhân 0,999 × 0,999 × 0,999 ≈ 99,7003% chỉ là **minh họa giả định độc lập và cả ba bước đều bắt buộc**, không phải công thức phổ quát để suy ra end-to-end availability.

### Phân rã SLO hữu ích

- SLO đầu-cuối đặt ở ranh giới hành trình người dùng.
- Service SLI giúp tìm ownership, thành phần gây lỗi và ngân sách latency.
- Dependency SLI dùng để quyết định cải thiện timeout, retry, circuit breaker hoặc lựa chọn vendor.
- Mức ưu tiên lấy từ tác động end-to-end, không phải service nào có nhiều metric đỏ hơn.

Không nhất thiết cho mọi service cùng mục tiêu 99,99%. Một hệ thống có thể cần Payment correctness cực nghiêm ngặt nhưng chấp nhận Notification gửi email trễ vài phút, miễn người dùng vẫn thấy xác nhận giao dịch đúng.

## 23. Phân biệt degraded mode với thất bại

Trong microservices, một dependency phụ có thể lỗi nhưng hành trình chính vẫn hoàn tất:

- Recommendation không hoạt động, Catalog vẫn hiển thị sản phẩm.
- Email thông báo chậm, Order vẫn được xác nhận và hiển thị.
- Search ranking fallback về thuật toán cơ bản, kết quả vẫn có ích.
- Một payment provider lỗi, hệ thống có đường thay thế được phép.

Với từng chức năng, cần quyết định:

- **Core success:** kết quả tối thiểu mà người dùng nhận được.
- **Degraded-but-acceptable:** chức năng phụ thiếu nhưng vẫn đúng kỳ vọng cốt lõi.
- **Bad event:** chức năng không đủ hữu ích hoặc mất correctness.
- **Separate SLI:** nếu degraded mode có ảnh hưởng đáng kể, đo bằng chỉ số riêng thay vì coi luôn là success.

Ví dụ Catalog hiển thị giá đúng nhưng thiếu recommendation có thể vẫn là good event của “xem sản phẩm”. Tuy nhiên nếu hiển thị giá sai, không thể coi good chỉ vì page render thành công.

## 24. Phân khúc người dùng và tính công bằng

Một SLO trung bình toàn dịch vụ có thể che việc một nhóm người dùng luôn chịu trải nghiệm kém.

Ví dụ:

~~~text
99% requests đến từ khu vực A: 99,99% success
 1% requests đến từ khu vực B: 90,00% success

Global success ≈ 99,8901%
~~~

Nếu chỉ nhìn global, có thể không thấy B đang gặp sự cố rất nghiêm trọng. Với 99,9% global SLO, phép đo này còn có thể chưa đạt, nhưng kể cả khi tổng đạt thì mức thiệt hại B vẫn cần xem riêng.

Các chiều phân tích hữu ích:

- Khu vực/region/availability zone.
- Ứng dụng mobile/web và phiên bản client.
- Gói dịch vụ/tenant tier.
- Hành trình, route, loại payment.
- Loại kết nối hoặc phiên bản API được hỗ trợ.

Cần cẩn trọng về cardinality và dữ liệu cá nhân. Không nhất thiết tạo một SLO hợp đồng riêng cho từng user; có thể duy trì **slice dashboards** và guardrails cho nhóm quan trọng hoặc nhóm có rủi ro bị bỏ sót.

### Weighted SLI và công bằng

Weighted averages theo traffic nói nhiều về **tổng lượng thao tác bị ảnh hưởng**, nhưng có thể che nhóm nhỏ. Có thể xem đồng thời global SLI và per-segment SLI, cùng chỉ số lượng người dùng duy nhất bị ảnh hưởng. Khi áp dụng trọng số, phải công bố phương pháp để tránh thay đổi định nghĩa theo kết quả mong muốn.

## 25. Dữ liệu đo có thể sai

Một dashboard số đẹp chưa chắc là bằng chứng tốt nếu pipeline telemetry có lỗ hổng.

Các câu hỏi cần kiểm tra:

1. Có đo được request bị chặn trước application không?
2. Client timeout có được ghi nhận không?
3. Counter có mất khi process crash trước khi flush không?
4. Có trùng event khi broker redeliver không?
5. Sampling có thiên lệch theo khu vực/device hoặc loại lỗi không?
6. Các worker có dùng cùng định nghĩa good/eligible không?
7. Có phân biệt production với staging và synthetic traffic không?
8. Khi deploy phiên bản mới, metric labels/outcomes có đổi nghĩa không?
9. Time window có đủ retention và dữ liệu scrape ổn định không?
10. Có phân biệt “không có traffic” với “100% good” không?

Nếu không có eligible events, phép chia good/eligible không được tự coi là 100% success. Có thể hiển thị **No data/Insufficient traffic** và bổ sung synthetic checks. Nếu nguồn telemetry bị gián đoạn, cần có alert về chính **khả năng đo**.

### Đo từ nhiều nguồn để đối chiếu

Một phát hiện hữu ích: API metric báo 99,99% success nhưng tỷ lệ complete order trong ledger giảm. Khả năng là endpoint trả Accepted rồi công việc nền thất bại, hoặc instrumentation đếm thành công quá sớm. Việc đối chiếu telemetry với dữ liệu nghiệp vụ giúp phát hiện SLI specification không còn phản ánh trải nghiệm.

## 26. Quy trình điều tra một SLO đang vi phạm

Giả sử checkout SLO 99,9% trên rolling 30 days, và dashboard báo burn rate cao.

**Bước 1 — Xác minh ảnh hưởng người dùng.** Bao nhiêu eligible attempts bị bad? Khu vực nào, loại payment nào, thời điểm nào? Có lỗi correctness nghiêm trọng không?

**Bước 2 — Kiểm tra phép đo.** Có rollout thay đổi instrumentation hoặc bug phân loại outcome không? Có telemetry gap không? Không trì hoãn ứng cứu nếu bằng chứng người dùng rõ ràng.

**Bước 3 — Chọn mốc lỗi.** So sánh thay đổi trong success ratio, latency, retry, timeout và thời điểm deploy/feature flag.

**Bước 4 — Truy vết critical path.** Tìm hop gây timeout/failure, dùng trace/correlation, xem database, gateway, provider và queue.

**Bước 5 — Giảm thiệt hại.** Cân nhắc rollback, giảm tải, circuit breaker, disable feature rủi ro, failover hoặc fallback an toàn. Không mở rộng retry vô hạn để che lỗi.

**Bước 6 — Bảo vệ dữ liệu.** Nếu outcome thanh toán chưa rõ, dùng reconciliation và idempotency; không tự khởi tạo charge mới khi chưa biết kết quả cũ.

**Bước 7 — Theo dõi phục hồi.** Xác nhận bad-event rate giảm, budget consumption chậm lại, backlog tiêu hết và số người dùng gặp lỗi đang giảm.

**Bước 8 — Review và hành động dài hạn.** Viết sự cố theo timeline, khắc phục nguyên nhân, bổ sung test, chỉnh ngưỡng alert và xác định liệu SLI có phản ánh đúng hành trình không.

Trong incident, một dashboard SLO giúp nhóm trả lời “người dùng còn bị ảnh hưởng không?”; metric hạ tầng và trace giúp trả lời “vì sao?”.

## 27. Kết nối SLO với phát triển sản phẩm

SLO hữu ích khi ảnh hưởng tới quyết định của đội, không chỉ xuất hiện trong báo cáo:

- **Ưu tiên roadmap:** nếu người dùng mất nhiều thời gian ở checkout, cải thiện latency có thể quan trọng hơn tối ưu CPU ở service ít ảnh hưởng.
- **Chọn kiến trúc:** cần synchronous dependency hay có thể dùng async/outbox? Người dùng chấp nhận trạng thái Pending bao lâu?
- **Thiết kế graceful degradation:** nếu recommendations lỗi, trang Catalog nên còn hoạt động.
- **Chính sách release:** khi budget gần cạn, tăng tỷ lệ canary và kiểm soát các thay đổi rủi ro.
- **Đầu tư khả năng chịu lỗi:** kết hợp retry có giới hạn, idempotency, circuit breaker, queue, caching, partitioning hoặc capacity.
- **Trao đổi sản phẩm-vận hành:** SLO tạo ngôn ngữ chung về mức trải nghiệm cần bảo vệ và chi phí để đạt được.

SLO cũng không phải một con số bất biến. Khi hành vi người dùng, lưu lượng, thị trường hoặc chức năng thay đổi, nên review định kỳ. Tuy nhiên mọi thay đổi định nghĩa cần lưu lịch sử để không làm đứt chuỗi so sánh hoặc che một thời kỳ vi phạm.

## 28. Thiết kế dashboard SLO dễ hành động

Một dashboard Checkout nên có phần trên cùng trả lời câu hỏi người dùng:

~~~text
CHECKOUT USER JOURNEY — rolling 30d

SLO target:           99.90%
Current good ratio:   99.94%
Error budget used:    60%
Recent burn rate:     theo cửa sổ 5m / 1h / 6h / 1d
Affected attempts:    theo volume và phân khúc
Latency good ratio:   mục tiêu riêng nếu có

Phía dưới:
  Failures by outcome
  Trend theo region, client type và payment method
  End-to-end latency distribution
  Retry/timeout và payment provider failure
  Database/queue/consumer lag
  Deploy markers và feature flags
  Link incident/runbook/owner
~~~

Lưu ý nếu current good ratio và error budget used đến từ cùng tập dữ liệu thì phải nhất quán về cửa sổ/mẫu số. Nếu dashboard ghép số 7 ngày và 30 ngày trong cùng một khối mà không ghi nhãn, người xem có thể đưa ra quyết định sai.

### Dashboard cho lãnh đạo hoặc sản phẩm

Có thể tập trung hơn vào:

- Số người dùng/checkout attempts bị ảnh hưởng.
- Mức đạt SLO và error budget.
- Những hành trình đang chịu tác động lớn nhất.
- Phân khúc chịu thiệt hại, xu hướng thay đổi và tác động tới conversion.
- Sự cố nghiêm trọng, mức phục hồi và ưu tiên đầu tư.

Không cần hiển thị tất cả metric JVM/GC ở báo cáo sản phẩm; chúng nên có trong phần chẩn đoán kỹ thuật.

## 29. SLO và tác động kinh doanh: liên hệ nhưng không đồng nhất

Một checkout thất bại có thể dẫn tới bỏ giỏ hoặc khách thử lại. Tuy nhiên không thể nhân thẳng “số bad events × giá trị đơn trung bình” rồi kết luận đó là doanh thu bị mất thực tế; có khách retry thành công, có khách chưa có ý định mua, hoặc lệnh thanh toán đang Pending.

Có thể kết hợp:

- Tỷ lệ bad events của checkout.
- Tỷ lệ bỏ giỏ theo thời điểm/lỗi.
- Conversion funnel có phân nhóm.
- Số checkout attempts có outcome chưa xác định.
- Tỷ lệ retry thành công và thời gian phục hồi.
- Khi thích hợp, nghiên cứu nhân quả hoặc thí nghiệm để ước lượng tác động doanh thu.

SLI/SLO trả lời **mức độ chất lượng kỹ thuật đã cung cấp**; product analytics giúp liên hệ nó với **hành vi và giá trị nhận được**. Hai nguồn nên đối chiếu, không thay thế nhau.

## 30. Thực hành tính SLI và error budget

Một nhóm thu được dữ liệu 30 ngày cho 2.000.000 checkout attempts đủ điều kiện:

~~~text
Success:        1.998.800
Server failure:       700
Timeout:              500
Eligible total: 2.000.000

Success trong <= 1.500 ms: 1.970.000
~~~

Giả định các nhóm outcome loại trừ lẫn nhau và đã deduplicate theo logical operation.

### 30.1. Availability

~~~text
Availability SLI = 1.998.800 / 2.000.000 = 99,94%
SLO target       = 99,90%
Allowed bad      = 2.000.000 × 0,001 = 2.000
Observed bad     = 700 + 500 = 1.200
Budget consumed  = 1.200 / 2.000 = 60%
Budget remaining = 800 operations = 40%
~~~

Kết quả availability SLO **đạt** trong cửa sổ giả định.

### 30.2. Latency-good

Nếu định nghĩa good là *eligible checkout vừa thành công vừa hoàn tất trong <= 1.500 ms*:

~~~text
Latency-good SLI = 1.970.000 / 2.000.000 = 98,50%
~~~

Nếu latency SLO là 99,0%, kết quả **không đạt** dù availability 99,94% đạt. Đây là minh họa quan trọng: API có thể hiếm khi thất bại nhưng thường xuyên chậm so với mức người dùng chấp nhận.

### 30.3. Kiểm tra phân khúc

Giả sử một khu vực có 10.000 attempts nhưng 500 timeout trong khi khu vực khác hoạt động tốt. Hãy xem per-region SLI bên cạnh global SLI. Một nhóm nhỏ có thể chịu trải nghiệm đặc biệt tệ mà không dễ thấy trong trung bình.

### 30.4. Quyết định vận hành

- Xem nguyên nhân 30.000 attempts không đạt latency-good (trong đó 1.200 không thành công; phần còn lại thành công nhưng chậm).
- Phân rã critical path: Payment, Inventory, order DB, queue, frontend.
- Kiểm tra retry và provider timeout, tránh cải thiện latency bằng cách bỏ bước xác minh thanh toán.
- Đặt alert về xu hướng budget của cả availability và latency, chứ không chỉ HTTP 5xx.
- Thử nghiệm canary và đo lại SLI trên traffic đủ đại diện.

Không kết luận phải tăng mọi pod khi chưa biết bottleneck: vấn đề có thể là một dependency, hot partition, DB lock hoặc trình duyệt mobile.

## 31. Lập SLI specification mẫu cho một dịch vụ

Một bản mô tả đầy đủ giúp các nhóm giữ phép đo ổn định:

~~~yaml
name: checkout_completion
owner: checkout-team
journey: checkout
environment: production

event_unit: logical_checkout_attempt
identity: checkout_operation_id

eligible:
  included:
    - user_initiated_valid_checkout
  excluded:
    - explicit_user_cancel_before_submission
    - approved_abuse_or_synthetic_test_traffic

good:
  - confirmed_order_exists
  - user_visible_confirmation_within_contract
  - no_known_invariant_violation

bad:
  - server_failure
  - terminal_timeout
  - outcome_unresolved_beyond_contract

measurement:
  primary_source: checkout_outcome_ledger
  supporting_sources:
    - gateway_metrics
    - payment_reconciliation
    - synthetic_checkout
  window: rolling_30_days

objective:
  good_ratio_at_least: 0.999

notes:
  - "Ví dụ khái niệm; chưa là schema của công cụ triển khai cụ thể"
  - "Pending phải được phân loại khi vượt deadline hợp đồng"
~~~

Tài liệu SLI nên bổ sung quy tắc xử lý late events, replay, migration, telemetry outage, owner review và độ tin cậy của source. Ví dụ `confirmed_order_exists` không nhất thiết tự chứng minh tiền đã được thanh toán đúng; nếu checkout contract yêu cầu thanh toán thành công, cần kiểm tra cả ledger/provider phù hợp.

## 32. Những sai lầm phổ biến

**Chọn SLO theo CPU, memory hoặc pod count.** Các metric này giúp điều tra nhưng không nói người dùng có hoàn tất hành động hay không.

**Dùng HTTP 200 làm toàn bộ tiêu chí success.** 200 có thể trả payload sai, partial result hoặc confirmation trước DB commit.

**Bỏ timeout khỏi mẫu số vì request không có response.** Điều đó khiến SLI nhìn tốt lên khi lỗi nghiêm trọng tăng.

**Chỉ đo những request đến application.** DNS/edge/network có thể làm người dùng thất bại trước khi hệ thống có trace.

**Lấy trung bình latency và bỏ p99 hoặc threshold-ratio.** Một nhóm nhỏ request rất chậm có thể bị che trong mean.

**Chỉ đặt SLO cho mỗi microservice và không đo end-to-end.** Người dùng trải qua toàn bộ chuỗi phụ thuộc, không trải nghiệm từng service một cách độc lập.

**Áp một con số 99,99% cho mọi service.** Mức độ cần thiết khác nhau, tăng chi phí không chắc tăng trải nghiệm.

**Tính error budget thời gian cho request-based SLO.** Tỷ lệ request không đổi trực tiếp ra phút downtime khi traffic biến động.

**Đếm retry HTTP thành nhiều user checkout độc lập.** Có thể làm sai mẫu số, che hoặc khuếch đại bad events.

**Không phân biệt user-cancel với server-failure.** Phải định nghĩa điều kiện loại trừ rõ, không dùng loại trừ tùy tiện để làm đẹp dashboard.

**Đặt alert 5xx trên một pod thay cho SLO burn rate.** Alert có thể quá nhiều hoặc bỏ sót lỗi nghiệp vụ, latency, freshness.

**Không có chủ sở hữu và runbook.** Một SLO đỏ nhưng không ai biết phải làm gì không hỗ trợ vận hành thực chất.

**Dùng budget để hợp thức hóa lỗi nghiêm trọng.** Một hệ thống có thể đạt 99,9% availability nhưng vẫn phải xử lý khẩn cấp lỗi charge trùng, mất dữ liệu hoặc sự cố an toàn.

**Không kiểm soát telemetry quality.** Mất metrics hoặc đổi định nghĩa outcome không được phép biến thành “SLO đạt”.

## 33. Bài tập thực hành

### Bài A — Viết SLI từ một lời hứa người dùng

Sản phẩm hứa rằng 99% lượt xem trạng thái đơn được cập nhật trong vòng 10 giây sau khi đơn thay đổi. Hãy xác định event unit, nguồn thời gian commit và thời gian visible, numerator, denominator, cách xử lý event trùng/muộn và nguồn đo đáng tin.

### Bài B — Không bỏ timeout khỏi mẫu số

Trong 10.000 attempts có 9.900 thành công, 50 HTTP 500 và 50 client timeout. Nếu một dashboard chỉ tính response có status, nó cho ra tỷ lệ khác với SLI logical user attempt. Hãy tính hai tỷ lệ và giải thích phép đo nào phản ánh đúng hợp đồng checkout.

### Bài C — Error budget

SLO request-based 99,95% trong 30 ngày, có 4.000.000 eligible requests. Tính số bad events cho phép, số budget còn lại nếu 1.500 requests đã bad, và giải thích vì sao không đổi trực tiếp budget này thành phút downtime.

### Bài D — Latency khác availability

Một service trả 99,99% success nhưng chỉ 93% eligible actions hoàn tất trong 1 giây, trong khi mục tiêu latency-good là 98%. Hãy xác định SLO nào đạt, SLO nào không đạt và đề xuất metric phụ trợ để tìm nguyên nhân.

### Bài E — Tổng hợp nhiều service

Checkout gọi Order, Inventory, Payment. Mỗi service báo availability 99,9%. Hãy giải thích vì sao không thể khẳng định checkout đạt 99,9%; nêu các giả định để có phép xấp xỉ và mô tả cách đo trực tiếp end-to-end.

### Bài F — SLI của workflow bất đồng bộ

Checkout trả 202 Accepted và xử lý payment qua queue. Hãy thiết kế bộ đo phân biệt “request accepted” với “order confirmed”, cách phân loại Pending quá deadline, late success và duplicate event.

### Bài G — Chiến lược alert

Một checkout service có 30-day SLO 99,9%. Trong 10 phút traffic tăng mạnh, bad ratio đạt 2%; trong khoảng 6 giờ, bad ratio gần mức baseline. Hãy đề xuất cơ chế cảnh báo dùng cửa sổ ngắn và dài, điều kiện lượng mẫu và hành động vận hành, tránh kết luận chỉ từ một spike.

### Bài H — Phân khúc và tính công bằng

Global SLO nhìn tốt nhưng khách ở một khu vực có tỷ lệ lỗi gấp 10 lần khu vực khác. Hãy đề xuất dashboard phân khúc, ngưỡng cảnh báo, cách bảo vệ thông tin cá nhân và tiêu chí ưu tiên khắc phục.

### Bài I — Correctness nghiêm ngặt

Một lỗi khiến 2 payment attempts bị charge hai lần trong tổng 2 triệu attempts; availability SLO vẫn đạt. Hãy thiết kế invariant, detection/reconciliation và quy trình ứng cứu riêng; giải thích vì sao không dùng error budget 0,1% để chấp nhận lỗi này.

## 34. Kết luận

**SLI là định nghĩa phép đo; SLO là mục tiêu về chất lượng; SLA là thỏa thuận có thể gắn hệ quả hợp đồng.** Muốn chúng hữu ích trong kiến trúc microservices, phải bắt đầu từ hành trình người dùng: một thao tác có hoàn tất, đủ nhanh, dữ liệu có đúng và đủ mới không.

Một hệ thống tốt không nhất thiết có mọi pod đều xanh mọi lúc. Nó cần đảm bảo người dùng nhận được kết quả đúng trong ngưỡng đã được sản phẩm chấp nhận, và đội vận hành phát hiện được khi điều đó không còn đúng. Availability, latency, correctness, freshness và durability là các góc nhìn bổ sung; không dùng một metric duy nhất để thay thế mọi chiều chất lượng.

Khi có định nghĩa good/eligible rõ ràng, nguồn đo đáng tin, cửa sổ nhất quán, error budget có chủ sở hữu, cảnh báo burn rate có hành động và kiểm thử end-to-end, SLI/SLO trở thành công cụ quyết định **đầu tư độ tin cậy ở đâu và khi nào nên thay đổi hệ thống**, thay vì một tập phần trăm đẹp trên dashboard.
