# Xác định khả năng hỗ trợ của nền tảng trước khi áp dụng

## Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích vì sao phải đánh giá năng lực thực tế của nền tảng trước khi chọn chiến lược triển khai.
- Phân biệt khả năng do nền tảng cung cấp sẵn, khả năng cần tích hợp thêm và khả năng ứng dụng phải tự hỗ trợ.
- Xác định các yêu cầu về điều phối phiên bản, định tuyến traffic, health check, capacity, dữ liệu, quan sát và phục hồi.
- Đánh giá mức độ phù hợp của rolling update, recreate, blue-green, canary và shadow traffic.
- Lập capability matrix có bằng chứng, giới hạn và người chịu trách nhiệm.
- Thực hiện kiểm chứng ở môi trường an toàn trước khi đưa chiến lược vào production.
- Chọn chiến lược triển khai phù hợp với kiến trúc ứng dụng, ràng buộc vận hành và năng lực nền tảng.

## 1. Không chọn chiến lược triển khai chỉ vì nền tảng quảng cáo có hỗ trợ

Rolling update, blue-green và canary thường được nhắc đến như những cách giảm rủi ro phát hành. Tuy nhiên, một chiến lược chỉ hoạt động tốt khi nền tảng và ứng dụng đáp ứng được các điều kiện cần thiết.

Ví dụ:

- Blue-green cần chạy được hai phiên bản song song và chuyển traffic giữa chúng.
- Canary cần điều khiển được tỷ lệ hoặc nhóm traffic đi đến phiên bản mới, đồng thời đo được kết quả.
- Rolling update cần khả năng chạy đồng thời phiên bản cũ và mới trong một khoảng thời gian.
- Shadow traffic cần nhân bản request hoặc event sang phiên bản mới mà không làm phát sinh tác động nghiệp vụ ngoài ý muốn.

Một nền tảng có thể có tính năng rollout theo tỷ lệ, nhưng load balancer phía trước lại không hỗ trợ weighted routing. Một cluster có thể chạy song song hai deployment, nhưng quota không đủ để giữ cả hai phiên bản. Một nền tảng có readiness probe, nhưng ứng dụng báo ready trước khi kết nối database hoặc nạp cấu hình xong. Một nền tảng có nút rollback, nhưng migration database đã xóa dữ liệu cũ nên việc quay lại phiên bản trước không còn an toàn.

Vì vậy, trước khi áp dụng chiến lược, cần trả lời hai câu hỏi:

1. **Nền tảng thực sự có thể thực hiện những thao tác nào?** Ví dụ tạo phiên bản song song, chuyển traffic, dừng rollout, giữ revision cũ và khôi phục.
2. **Ứng dụng có thể hoạt động đúng trong các trạng thái trung gian hay không?** Ví dụ hai phiên bản cùng đọc/ghi database, xử lý message hoặc chia sẻ session.

Không nên đồng nhất việc một công cụ có tính năng với việc toàn bộ hệ thống đã đủ điều kiện sử dụng tính năng đó. Khả năng thực tế là kết quả của nền tảng, hạ tầng mạng, cấu hình, quyền, dịch vụ phụ thuộc và thiết kế ứng dụng.

## 2. Đánh giá theo toàn bộ đường đi của request

Một chiến lược triển khai thay đổi cách phiên bản mới nhận traffic. Do đó, hãy theo dõi đường đi của request từ người dùng đến ứng dụng.

~~~mermaid
flowchart LR
    U["Client"] --> E["DNS / Edge"]
    E --> L["Load balancer / Ingress"]
    L --> S["Service discovery / Routing"]
    S --> P["Application instances"]
    P --> D["Database / Cache / Queue"]
    P --> O["Logs / Metrics / Traces"]
    O --> G["Rollout decision"]
    G --> L
~~~

Ở mỗi lớp, cần xác định:

- Thành phần nào quyết định request đi đến phiên bản cũ hay mới?
- Có thể điều chỉnh tỷ lệ traffic hoặc chọn nhóm người dùng không?
- Thời gian hội tụ khi thay đổi routing là bao lâu?
- Có sticky session hoặc connection dài hạn không?
- Khi instance không sẵn sàng, traffic có được loại khỏi instance đó không?
- Có telemetry để biết phiên bản nào xử lý request và kết quả ra sao?
- Có thể dừng rollout và đưa traffic về phiên bản trước không?

Ví dụ, thay đổi DNS record có thể không chuyển traffic tức thời vì resolver và client có cache. Nếu cần canary theo tỷ lệ nhỏ và phản ứng nhanh, DNS đơn thuần có thể không đáp ứng yêu cầu. Một load balancer hoặc service mesh có weighted routing có thể phù hợp hơn, nhưng vẫn cần kiểm chứng cấu hình, kết nối và quyền điều khiển.

Cần đánh giá đường đi thực tế của request, bao gồm CDN, API gateway, ingress, service mesh, load balancer nội bộ và kết nối từ client giữ lâu. Một tính năng có ở lớp ứng dụng không tự động điều khiển được mọi lớp phía trước.

## 3. Các nhóm năng lực cần kiểm tra

Một capability assessment có thể chia thành tám nhóm.

| Nhóm năng lực | Câu hỏi chính | Bằng chứng nên thu thập |
|---|---|---|
| Điều phối phiên bản | Có thể chạy, cập nhật và giữ nhiều revision không? | Deployment controller, rollout API, revision history |
| Traffic routing | Có thể chuyển traffic theo tỷ lệ hoặc điều kiện không? | Load balancer, ingress, gateway, service mesh config |
| Health và readiness | Có phát hiện instance chưa sẵn sàng hoặc lỗi không? | Probe, health endpoint, rollout gate |
| Capacity và scheduling | Có đủ tài nguyên cho phiên bản mới chạy song song không? | Quota, node capacity, autoscaling limits |
| Trạng thái và dữ liệu | Phiên bản cũ/mới có thể cùng tồn tại không? | Compatibility tests, migration plan, session design |
| Observability | Có phân biệt được lỗi của phiên bản mới không? | Metrics, logs, traces, dashboard, alert |
| Identity và policy | Ai được rollout, chuyển traffic và rollback? | IAM, service account, approval policy, audit |
| Recovery | Có dừng, quay traffic và phục hồi dữ liệu được không? | Rollback test, backup/restore evidence, runbook |

Không nên chỉ đánh dấu Có/Không. Một khả năng có thể được hỗ trợ ở mức khác nhau:

- **Native:** nền tảng cung cấp sẵn và đã được bật.
- **Integrated:** có thể thực hiện nhờ tích hợp gateway, service mesh, controller hoặc công cụ bên ngoài.
- **Application-dependent:** cần sửa ứng dụng hoặc bổ sung logic nghiệp vụ.
- **Unavailable:** chưa có hoặc không thể đáp ứng với kiến trúc hiện tại.

Cũng cần ghi rõ bằng chứng. Tài liệu nhà cung cấp cho biết tính năng có tồn tại, nhưng thử nghiệm trong đúng cluster, network và quota mới cho biết nó có hoạt động trong môi trường của tổ chức hay không.

## 4. Khả năng điều phối phiên bản

Nền tảng cần có cách quản lý revision và trạng thái của các instance.

Các câu hỏi cần kiểm tra:

- Có thể triển khai phiên bản mới mà vẫn giữ phiên bản cũ không?
- Có thể đặt số lượng instance tối thiểu và tối đa trong rollout không?
- Có thể giới hạn số instance bị unavailable cùng lúc không?
- Có thể pause, resume hoặc abort rollout không?
- Có giữ lịch sử revision và trạng thái rollout không?
- Có hỗ trợ pin artifact theo digest thay vì tag thay đổi không?
- Có thể triển khai theo nhóm instance, zone hoặc region không?
- Khi một instance mới khởi động thất bại, controller phản ứng như thế nào?

Rolling update cần scheduler hoặc deployment controller biết cách thay instance theo từng đợt. Blue-green cần khả năng giữ hai nhóm phiên bản cùng tồn tại. Canary cần có cách xác định subset instance hoặc nhóm traffic nhận phiên bản mới.

Một nền tảng chỉ hỗ trợ thay toàn bộ process sau khi dừng process cũ có thể phù hợp với recreate, nhưng không thể mặc nhiên triển khai rolling hoặc blue-green nếu không có thêm cơ chế điều phối.

Cần kiểm tra cả giới hạn của nền tảng. Ví dụ, một service có thể cho phép tạo hai deployment nhưng policy hoặc quota lại giới hạn số load balancer, IP, volume hoặc replica.

## 5. Khả năng định tuyến và chuyển traffic

Traffic routing là điều kiện quan trọng đối với blue-green, canary và shadow traffic.

### 5.1. Các khả năng cần có

- Chuyển toàn bộ traffic sang một backend khác.
- Chia traffic theo tỷ lệ, ví dụ 1%, 5%, 10% rồi tăng dần.
- Chọn traffic theo header, cookie, tenant, user cohort hoặc region nếu cần.
- Giữ hoặc loại sticky session theo chiến lược.
- Drain connection đang hoạt động trước khi tắt phiên bản cũ.
- Khôi phục routing về backend trước.
- Ghi nhận revision routing đang được áp dụng.

Không phải mọi chiến lược cần tất cả các khả năng này. Canary đơn giản có thể chia theo tỷ lệ; canary theo nhóm người dùng cần định danh hoặc thuộc tính request ổn định.

### 5.2. Weighted routing không chỉ là cấu hình một con số

Khi cấu hình 5% traffic cho phiên bản mới, cần xác minh:

- Tỷ lệ được áp dụng ở đúng lớp routing.
- Có bao gồm mọi vùng hoặc mọi ingress không.
- Connection reuse có làm tỷ lệ thực tế lệch không.
- Traffic nội bộ giữa service có đi theo routing rule không.
- Client retry có làm tăng request đến phiên bản mới không.
- Có thể quan sát số request thực tế theo phiên bản không.

Nếu chỉ nhìn cấu hình khai báo mà không đo traffic thực tế, có thể nghĩ canary đang nhận 5% nhưng một phần lớn traffic lại đi qua đường khác.

### 5.3. Connection dài hạn và session

WebSocket, gRPC stream, TCP connection dài hạn hoặc session sticky có thể làm việc chuyển traffic chậm hơn. Khi routing đổi, các connection hiện tại có thể tiếp tục ở phiên bản cũ cho đến khi đóng.

Cần xác định thời gian drain, timeout, cách xử lý reconnect và khả năng tương thích session giữa các phiên bản. Nếu phiên bản mới không đọc được session do phiên bản cũ tạo ra, rollout có thể gây lỗi dù routing hoạt động đúng.

## 6. Health check và điều kiện sẵn sàng

Nền tảng cần biết khi nào instance mới có thể nhận traffic và khi nào rollout nên dừng.

Phân biệt các loại kiểm tra:

- **Startup check:** ứng dụng đã hoàn tất khởi động chưa; hữu ích khi startup kéo dài.
- **Readiness check:** instance đã sẵn sàng nhận traffic chưa.
- **Liveness check:** process có còn sống và cần được khởi động lại không.
- **Smoke test:** luồng chức năng quan trọng có hoạt động sau deploy không.
- **Rollout analysis:** tỷ lệ lỗi, latency hoặc metric vận hành có nằm trong ngưỡng cho phép không.

Readiness thường được dùng để quyết định có đưa instance vào endpoint phục vụ traffic. Liveness dùng để phát hiện process bị treo hoặc không thể phục hồi. Dùng liveness quá nhạy có thể tạo vòng lặp restart; dùng readiness quá đơn giản có thể cho traffic vào trước khi dependency quan trọng sẵn sàng.

Một health endpoint trả về HTTP 200 chưa chắc chứng minh toàn bộ chức năng hoạt động. Cần chọn kiểm tra phù hợp với mục đích, tránh làm health check tạo tải lớn hoặc phụ thuộc vào mọi dịch vụ không thiết yếu.

Trước khi chọn chiến lược, cần xác minh:

- Nền tảng có hỗ trợ probe hoặc health gate không?
- Có thể dừng rollout khi readiness hoặc smoke test thất bại không?
- Có thể đánh giá metric trong một khoảng thời gian đủ dài không?
- Ngưỡng lỗi có được phân biệt theo phiên bản không?
- Có thể tự động pause hoặc abort khi vượt ngưỡng không?

## 7. Capacity và khả năng chạy song song

Một số chiến lược cần thêm tài nguyên tạm thời. Nếu nền tảng không đủ capacity, rollout có thể bị pending hoặc gây áp lực lên phiên bản đang phục vụ.

### 7.1. Blue-green

Blue-green thường cần giữ nhóm cũ và nhóm mới cùng hoạt động trước khi chuyển traffic. Trong giai đoạn chuyển tiếp, tài nguyên có thể gần gấp đôi phần ứng dụng được triển khai, chưa tính các thành phần phụ trợ.

Cần kiểm tra:

- CPU, memory và quota đủ cho cả hai nhóm không?
- Database có chịu được kết nối từ cả hai phiên bản không?
- Có đủ IP, load balancer, volume và tài nguyên phụ trợ không?
- Autoscaler có thể cấp tài nguyên trong thời gian rollout không?
- Có thể giữ nhóm cũ đủ lâu để rollback không?

### 7.2. Rolling update

Rolling thường cần capacity để tạo instance mới trước hoặc trong lúc instance cũ bị loại bỏ. Các tham số như max surge và max unavailable ảnh hưởng trực tiếp đến khả năng triển khai.

Nếu max surge bằng 0 và nền tảng phải chờ tài nguyên cũ được giải phóng, rollout có thể chậm hoặc gây giảm capacity. Nếu max unavailable quá cao, hệ thống có thể thiếu instance phục vụ.

### 7.3. Canary

Canary thường cần một phần capacity cho phiên bản mới, cộng thêm năng lực quan sát và điều phối. Nếu canary được triển khai theo nhóm instance riêng, cần xác định giới hạn tối thiểu để có đủ mẫu đo. Một canary chỉ nhận rất ít request có thể không tạo đủ dữ liệu để đánh giá lỗi hiếm.

### 7.4. Kiểm tra tài nguyên thực tế

Không chỉ xem quota tổng. Hãy xem capacity theo zone, node pool, region, storage class và giới hạn từng workload. Một cluster còn tổng CPU nhưng node phù hợp không còn chỗ có thể vẫn không schedule được pod mới.

## 8. Tương thích dữ liệu và trạng thái ứng dụng

Nền tảng có thể chạy song song hai phiên bản, nhưng ứng dụng phải chịu được trạng thái đó.

Các dạng state cần xem xét:

- Database schema và dữ liệu.
- Session đăng nhập.
- Cache key và cấu trúc cache.
- Message format trong queue.
- Event schema.
- File hoặc object storage.
- Distributed lock và scheduled job.
- Feature flag và cấu hình động.

Ví dụ, phiên bản cũ ghi trường status với giá trị PENDING, còn phiên bản mới đổi thành WAITING_FOR_PAYMENT. Nếu cả hai phiên bản cùng chạy, mỗi phiên bản có thể hiểu dữ liệu theo cách khác nhau.

Một chiến lược an toàn thường dùng expand-and-contract:

1. Mở rộng schema theo cách tương thích với phiên bản cũ.
2. Triển khai phiên bản mới có thể đọc/ghi cấu trúc tương thích.
3. Chuyển dần luồng sử dụng hoặc dữ liệu.
4. Chỉ loại bỏ cấu trúc cũ sau khi không còn instance nào cần nó.

Đối với message queue, cần xem consumer cũ có đọc được message mới không và consumer mới có đọc được message cũ không. Có thể cần version hóa schema và duy trì tương thích trong giai đoạn chuyển tiếp.

Đối với session, cân nhắc session store dùng chung, token stateless hoặc cơ chế chuyển đổi tương thích. Nếu mỗi phiên bản giữ session trong bộ nhớ riêng, traffic chuyển giữa phiên bản có thể khiến người dùng bị đăng xuất hoặc mất trạng thái.

## 9. Observability là điều kiện để quyết định rollout

Canary và rolling có kiểm soát không thể chỉ dựa vào việc instance mới khởi động thành công. Cần biết phiên bản mới đang hoạt động tốt hay xấu hơn phiên bản cũ.

Các tín hiệu hữu ích:

- Tỷ lệ request thành công và lỗi theo phiên bản.
- Latency p50, p95, p99 theo phiên bản.
- Tỷ lệ timeout và retry.
- CPU, memory và restart count.
- Queue lag hoặc consumer failure.
- Database connection errors và query latency.
- Business metrics như tỷ lệ checkout thành công hoặc thanh toán bị từ chối.
- Log và trace có gắn release ID hoặc version.

Cần phân biệt lỗi do phiên bản mới với lỗi chung của môi trường. Ví dụ, nếu cả phiên bản cũ và mới cùng tăng latency do database quá tải, rollback phiên bản mới có thể không giải quyết nguyên nhân.

Để đánh giá canary, cần xác định:

- Metric nào là chỉ báo chính?
- Baseline so sánh là phiên bản nào?
- Khoảng thời gian quan sát đủ dài chưa?
- Traffic có đủ lớn để tạo mẫu có ý nghĩa không?
- Ngưỡng nào khiến rollout pause, abort hoặc tiếp tục?
- Ai nhận cảnh báo và có quyền quyết định?

Không nên chọn ngưỡng tùy ý. Ngưỡng cần dựa trên SLO, mức biến động bình thường, tải thực tế và mức rủi ro của thay đổi.

## 10. Năng lực phục hồi và rollback

Trước khi dùng một chiến lược, hãy xác định chính xác nền tảng có thể phục hồi phần nào.

Có thể rollback:

- Artifact về digest trước.
- Routing về backend cũ.
- Deployment manifest về revision trước.
- Runtime configuration về revision trước nếu còn hợp lệ.

Nhưng không phải mọi trạng thái đều tự động đảo ngược:

- Database migration có thể đã xóa hoặc biến đổi dữ liệu.
- Message đã phát ra có thể đã được consumer xử lý.
- Email, thanh toán hoặc tác động bên ngoài không thể thu hồi.
- Cache hoặc session có thể đã chuyển sang định dạng mới.
- Secret cũ có thể đã bị revoke.

Do đó, rollback plan cần bao gồm cả ứng dụng, routing, cấu hình và trạng thái dữ liệu. Với thay đổi không thể đảo ngược, cần forward fix hoặc recovery procedure.

Nền tảng cần hỗ trợ ít nhất những thao tác phù hợp với chiến lược:

- Dừng rollout.
- Giữ phiên bản trước.
- Chuyển traffic về phiên bản trước.
- Khôi phục cấu hình.
- Quan sát trạng thái sau phục hồi.
- Ghi audit về quyết định và kết quả.

Nên diễn tập rollback trong môi trường không sản xuất. Một nút rollback tồn tại trong giao diện không chứng minh rằng toàn bộ hệ thống có thể phục hồi an toàn.

## 11. Khả năng của các loại nền tảng thường gặp

Không có loại nền tảng nào mặc nhiên phù hợp với mọi chiến lược. Cần đánh giá cấu hình và dịch vụ thực tế.

| Loại nền tảng | Khả năng thường có | Cần xác minh thêm |
|---|---|---|
| VM hoặc bare metal tự quản lý | Có thể chạy nhiều process/version nếu tự điều phối | Load balancer, service discovery, capacity, health check, rollback automation |
| Container platform | Có cơ chế image, replica và scheduling | Traffic splitting, rollout analysis, storage, quota, controller và policy |
| Kubernetes | Deployment, ReplicaSet, Service, readiness probe và rollout history | Ingress/service mesh, weighted routing, autoscaling, resource quota, stateful compatibility |
| PaaS | Có thể có release, instance scaling và health check do nền tảng quản lý | Blue-green/canary support, routing control, rollback window, giới hạn runtime |
| Serverless | Có thể có version hoặc alias và traffic shifting tùy dịch vụ | Cold start, concurrency quota, event source, state compatibility, observability |
| Edge/CDN platform | Có thể phân phối phiên bản và routing ở biên | Cache invalidation, propagation delay, region consistency và rollback behavior |

Bảng trên mô tả các khả năng thường gặp, không phải cam kết cho mọi sản phẩm. Phiên bản nền tảng, gói dịch vụ, plugin, cấu hình tài khoản và quyền được cấp có thể làm thay đổi đáng kể năng lực thực tế.

Ví dụ, Kubernetes có Deployment rollout nhưng weighted canary traffic thường cần thêm ingress controller, service mesh hoặc progressive delivery controller. Không nên suy luận rằng có Kubernetes đồng nghĩa mọi hình thức canary đều sẵn sàng.

## 12. So sánh yêu cầu của các chiến lược triển khai

| Chiến lược | Năng lực nền tảng cần có | Điều kiện ở ứng dụng | Giới hạn thường gặp |
|---|---|---|---|
| Recreate | Dừng phiên bản cũ, chạy phiên bản mới | Chấp nhận downtime hoặc có cơ chế dự phòng | Downtime trong lúc chuyển |
| Rolling update | Quản lý nhiều instance, readiness, giới hạn surge/unavailable | Phiên bản cũ và mới cùng tương thích | Lỗi có thể lan dần trước khi dừng |
| Blue-green | Chạy hai nhóm, routing switch, giữ nhóm cũ | Hai phiên bản cùng dùng được dữ liệu và dependency | Tốn capacity, state có thể lệch |
| Canary | Traffic split hoặc cohort routing, metric theo version, pause/abort | Có thể phát hiện lỗi và giới hạn tác động theo nhóm | Mẫu traffic nhỏ, routing phức tạp |
| Shadow traffic | Duplicate/replicate request hoặc event, tách side effect | Request có thể chạy an toàn mà không tạo tác động thật | Tốn tài nguyên, dữ liệu nhạy cảm, side effect |

Shadow traffic thường dùng để đánh giá phiên bản mới mà không trả response của nó cho người dùng. Tuy nhiên, nếu request tạo đơn hàng, gửi email hoặc thực hiện thanh toán, bản sao có thể gây side effect. Cần mock, chặn hoặc sandbox các thao tác ghi và gọi dịch vụ bên ngoài trước khi nhân bản traffic.

## 13. Lập capability matrix trước khi quyết định

Một capability matrix giúp đội ngũ chuyển nhận định chung thành bằng chứng có thể review.

Ví dụ cho một dịch vụ chạy trên container platform:

| Năng lực | Mức hỗ trợ | Bằng chứng | Khoảng trống / hành động |
|---|---|---|---|
| Chạy song song hai revision | Native | Hai deployment cùng tồn tại trong test environment | Xác minh quota production |
| Weighted routing | Integrated | Ingress hỗ trợ traffic weight | Cần test propagation và connection reuse |
| Readiness gate | Native | Probe được controller sử dụng | Bổ sung dependency readiness |
| Metric theo version | Application-dependent | Metric có label release | Chuẩn hóa dashboard và alert |
| Tự động abort canary | Integrated | Rollout controller đọc metric | Xác minh ngưỡng và hành vi abort |
| Rollback routing | Native/Integrated | Có thể đổi backend về revision cũ | Diễn tập với connection dài hạn |
| Database compatibility | Application-dependent | Integration test expand-and-contract | Bổ sung test dữ liệu thực tế |
| Capacity cho blue-green | Chưa xác minh | Chưa có load/capacity test | Kiểm tra quota và headroom |

Nên bổ sung các cột:

- Owner của năng lực.
- Môi trường đã kiểm chứng.
- Ngày kiểm chứng và phiên bản nền tảng.
- Link đến test report hoặc runbook.
- Rủi ro còn lại.
- Trạng thái: verified, partial, unknown hoặc unsupported.

Không nên đánh dấu verified chỉ vì đã đọc tài liệu. Một năng lực cần có bằng chứng phù hợp: thử nghiệm, cấu hình thực tế, giới hạn đã đo hoặc xác nhận từ owner nền tảng.

## 14. Quy trình đánh giá nền tảng trước khi áp dụng

Có thể thực hiện theo các bước:

1. **Mô tả mục tiêu phát hành:** cần giảm downtime, giới hạn blast radius, kiểm chứng một nhóm người dùng hay hỗ trợ rollback nhanh?
2. **Xác định yêu cầu ứng dụng:** stateful hay stateless, session, database, queue, connection dài hạn và side effect.
3. **Khám phá nền tảng:** kiểm tra API, tính năng, version, quota, network, identity và policy đang bật.
4. **Lập capability matrix:** đánh dấu native, integrated, application-dependent hoặc unavailable.
5. **Xác định khoảng trống:** cần thêm gateway, service mesh, controller, telemetry hay thay đổi ứng dụng?
6. **Chạy proof of concept:** thử trên môi trường đại diện với cùng cách routing, quota và dependency.
7. **Kiểm tra failure path:** cố ý làm health check thất bại, mất capacity, lỗi routing hoặc lỗi phiên bản mới.
8. **Diễn tập rollback:** xác minh artifact, config, routing và dữ liệu có thể phục hồi.
9. **Chốt chiến lược:** ghi rõ lựa chọn, lý do, điều kiện và rủi ro còn lại.
10. **Đưa vào pipeline:** biến điều kiện đã xác minh thành preflight check, gate và automation.

~~~mermaid
flowchart TD
    A["Xác định mục tiêu release"] --> B["Phân tích ứng dụng và state"]
    B --> C["Khám phá platform capabilities"]
    C --> D["Lập capability matrix"]
    D --> E{"Đủ điều kiện?"}
    E -- "Chưa" --> F["Bổ sung tích hợp hoặc chọn chiến lược khác"]
    F --> C
    E -- "Đủ" --> G["PoC trong môi trường đại diện"]
    G --> H["Test failure và rollback"]
    H --> I{"Bằng chứng đạt?"}
    I -- "Không" --> F
    I -- "Có" --> J["Chốt strategy và policy"]
    J --> K["Tự động hóa thành pipeline gates"]
~~~

Proof of concept cần kiểm tra cả đường thành công và đường thất bại. Một lần deploy thành công không chứng minh được khả năng pause, abort, routing rollback hoặc xử lý instance không sẵn sàng.

## 15. Ví dụ chọn chiến lược theo khả năng nền tảng

Giả sử một dịch vụ API có các đặc điểm:

- Chạy ba replica.
- Có load balancer nhưng chưa có weighted routing.
- Có readiness probe.
- Database dùng chung và schema hiện tại tương thích giữa hai phiên bản.
- Metric có thể phân biệt theo release version.
- Quota đủ để chạy thêm một replica nhưng không đủ để chạy hai nhóm đầy đủ.

Đánh giá:

- **Blue-green:** chưa phù hợp vì capacity không đủ cho hai nhóm hoàn chỉnh.
- **Canary theo tỷ lệ traffic:** chưa sẵn sàng vì load balancer chưa hỗ trợ weighted routing.
- **Rolling update:** có thể phù hợp nếu controller hỗ trợ max surge/unavailable và readiness probe phản ánh đúng khả năng nhận traffic.
- **Recreate:** có thể dùng nhưng có nguy cơ downtime.
- **Canary theo instance:** có thể thử nếu service discovery cho phép thêm một instance mới và traffic có thể được chọn theo một cơ chế khác đã được kiểm chứng.

Trong trường hợp này, rolling update có thể là lựa chọn đầu tiên. Đội ngũ vẫn cần kiểm thử tình huống instance mới lỗi, quota không đủ, readiness không đạt và phiên bản cũ/mới cùng xử lý request. Nếu sau này bổ sung weighted routing và capacity, có thể đánh giá lại canary hoặc blue-green.

Ví dụ này cho thấy chiến lược tốt là chiến lược đáp ứng mục tiêu với năng lực đã được chứng minh, không phải chiến lược có nhiều thuật ngữ hoặc tính năng nhất.

## 16. Các anti-pattern khi đánh giá platform capability

| Anti-pattern | Rủi ro | Cách cải thiện |
|---|---|---|
| Chọn canary vì nền tảng có nút canary | Chưa chắc routing và metrics hoạt động đúng | Kiểm tra đường traffic và rollout analysis thực tế |
| Cho rằng Kubernetes mặc định có weighted canary | Thiếu ingress/service mesh/controller phù hợp | Lập capability matrix theo cluster |
| Chỉ kiểm tra deploy thành công | Không biết platform xử lý failure ra sao | Test pause, abort, unhealthy instance và rollback |
| Không kiểm tra capacity | Blue-green hoặc surge rollout bị pending | Đo headroom theo quota, zone và workload |
| Bỏ qua compatibility dữ liệu | Hai phiên bản làm hỏng dữ liệu của nhau | Kiểm tra schema, message và session compatibility |
| Dùng readiness endpoint quá đơn giản | Instance nhận traffic trước khi sẵn sàng | Thiết kế readiness theo dependency cần thiết |
| Không có metric theo version | Không biết canary có lỗi hơn phiên bản cũ không | Gắn release/version vào metric, log và trace |
| Coi rollback là khôi phục toàn bộ | Dữ liệu hoặc side effect có thể không đảo ngược | Lập recovery plan cho từng loại state |
| Chỉ đọc tài liệu nhà cung cấp | Bỏ qua quota, policy và cấu hình thực tế | PoC trên môi trường đại diện |
| Không ghi ngày và phiên bản kiểm chứng | Capability có thể đã thay đổi | Lưu evidence, platform version và owner |

## 17. Checklist trước khi áp dụng chiến lược triển khai

Trước khi bật một chiến lược trong production, hãy xác nhận:

- [ ] Mục tiêu phát hành và mức rủi ro đã được xác định.
- [ ] Đã mô tả đường đi của request qua DNS, gateway, load balancer và service.
- [ ] Nền tảng có thể quản lý revision theo cách chiến lược yêu cầu.
- [ ] Routing có thể chuyển hoặc chia traffic đúng phạm vi.
- [ ] Connection dài hạn, sticky session và connection draining đã được xem xét.
- [ ] Startup, readiness và liveness có ý nghĩa phù hợp.
- [ ] Rollout có thể pause, abort và quan sát trạng thái.
- [ ] Capacity, quota và autoscaling đủ cho trạng thái chuyển tiếp.
- [ ] Hai phiên bản tương thích với database, cache, queue, session và event.
- [ ] Metric, log và trace phân biệt được phiên bản.
- [ ] Có ngưỡng tiếp tục, pause và abort dựa trên SLO.
- [ ] Identity và policy cho phép đúng người hoặc workload thực hiện.
- [ ] Artifact và cấu hình được định danh bằng revision/digest.
- [ ] Đã thử failure path và rollback trong môi trường đại diện.
- [ ] Rủi ro không thể rollback đã có recovery hoặc forward-fix plan.
- [ ] Capability matrix có bằng chứng, owner, ngày và phiên bản nền tảng.
- [ ] Pipeline có preflight checks để phát hiện năng lực hoặc điều kiện không còn đúng.

## 18. Bài tập tự đánh giá

Một nhóm muốn dùng blue-green cho dịch vụ thanh toán. Nền tảng hiện có:

- Kubernetes với Deployment và Service.
- Ingress controller chỉ route traffic đến một backend tại một thời điểm.
- Database có migration đổi tên một cột.
- Session được lưu trong memory của từng pod.
- Dashboard chỉ hiển thị metric tổng, không phân biệt release version.
- Quota production chỉ đủ cho số replica hiện tại.
- Có rollout history nhưng chưa từng diễn tập rollback.

Hãy đánh giá:

1. Những năng lực nào blue-green cần nhưng nền tảng hiện chưa có?
2. Việc chạy hai Deployment song song có đủ để kết luận blue-green đã sẵn sàng không?
3. Cần thay đổi gì ở ingress hoặc routing để chuyển traffic có kiểm soát?
4. Session trong memory ảnh hưởng thế nào khi traffic chuyển sang nhóm mới?
5. Migration đổi tên cột có tương thích với hai phiên bản cùng chạy không?
6. Cần bổ sung metric và log nào để quan sát từng phiên bản?
7. Quota cần thay đổi hoặc chiến lược cần điều chỉnh ra sao?
8. Cần diễn tập failure và rollback những bước nào?
9. Nếu chưa thể đáp ứng blue-green, chiến lược nào có thể phù hợp hơn với năng lực hiện tại?

Một thiết kế tốt cần chỉ rõ năng lực còn thiếu, bằng chứng cần thu thập và thứ tự khắc phục. Có thể chọn chiến lược khác trong giai đoạn đầu, sau đó đánh giá lại khi nền tảng và ứng dụng đã đáp ứng điều kiện.

## Kết luận

Chiến lược triển khai chỉ có thể giảm rủi ro khi nền tảng và ứng dụng thực sự hỗ trợ các thao tác mà chiến lược yêu cầu. Cần đánh giá điều phối phiên bản, routing, health check, capacity, compatibility dữ liệu, observability, identity và recovery trước khi chọn rolling, blue-green, canary, recreate hoặc shadow traffic.

Hãy lập capability matrix có bằng chứng, kiểm chứng trên môi trường đại diện và thử cả tình huống thất bại lẫn rollback. Khi năng lực chưa đủ, hãy bổ sung tích hợp hoặc chọn chiến lược phù hợp hơn với giới hạn hiện tại. Quyết định dựa trên bằng chứng giúp tránh triển khai một mô hình chỉ tồn tại trong tài liệu nhưng không thể vận hành an toàn trên nền tảng thực tế.

