# Kiểm chứng dịch vụ và tác động người dùng sau phục hồi

## 1. Vì sao phục hồi xong vẫn cần kiểm chứng?

Sau khi rollback, failover, khôi phục backup hoặc triển khai bản sửa, hệ thống có thể đã chạy lại nhưng chưa chắc đã trở về trạng thái phục vụ bình thường. Process có thể active trong khi request vẫn lỗi; health endpoint có thể trả thành công nhưng giao dịch nghiệp vụ bị sai; database có thể mở kết nối nhưng một phần dữ liệu chưa được đối soát; queue có thể nhận message mới nhưng backlog cũ vẫn chưa được xử lý.

Vì vậy, kết thúc thao tác phục hồi không đồng nghĩa kết thúc sự cố. Nhóm cần xác minh hai khía cạnh:

- **Dịch vụ đã phục hồi:** thành phần kỹ thuật, luồng request, dependency và dữ liệu hoạt động trong giới hạn chấp nhận được.
- **Tác động người dùng đã được hiểu và xử lý:** xác định ai bị ảnh hưởng, giao dịch nào bị lỗi hoặc trì hoãn, dữ liệu nào cần sửa, thông tin nào cần gửi và hỗ trợ nào còn phải thực hiện.

Ví dụ, một dịch vụ đơn hàng được rollback về artifact ổn định. API trả HTTP 200 trở lại, nhưng trong 12 phút trước đó một số đơn đã được tạo mà không phát event sang hệ thống giao vận. Nếu chỉ kiểm tra health endpoint, nhóm có thể tuyên bố phục hồi quá sớm trong khi người dùng vẫn chưa nhận được hàng đúng quy trình.

Kiểm chứng sau phục hồi là bước xác nhận hệ thống thực sự đáp ứng yêu cầu vận hành và nghiệp vụ. Nó cũng cung cấp bằng chứng để đóng incident, thông báo chính xác cho các bên liên quan và ngăn sự cố tái diễn.

## 2. Phân biệt thao tác phục hồi, trạng thái dịch vụ và khôi phục trải nghiệm

Ba mốc cần được ghi nhận riêng:

| Mốc | Ý nghĩa | Ví dụ |
|---|---|---|
| Recovery action completed | Lệnh hoặc quy trình phục hồi đã chạy xong | Workload đã được đưa về image digest trước đó |
| Service restored | Các luồng kỹ thuật/nghiệp vụ quan trọng đã hoạt động trong ngưỡng | Người dùng có thể tạo và tra cứu đơn hàng |
| User impact resolved | Tác động còn tồn đọng đã được xử lý hoặc có kế hoạch được chấp nhận | Đơn bị thiếu event đã được đối soát và gửi lại an toàn |

Một dịch vụ có thể đã restored trong khi user impact vẫn đang được xử lý. Ví dụ, hệ thống thanh toán đã nhận giao dịch mới bình thường nhưng một số giao dịch trong thời gian incident vẫn cần đối chiếu với cổng thanh toán. Cần giữ trạng thái incident phù hợp thay vì gộp tất cả thành “đã xong”.

Tương tự, một thao tác rollback thành công chỉ chứng minh phiên bản được đổi. Nó không tự chứng minh phiên bản cũ hoạt động đúng với schema, secret, cấu hình và dữ liệu hiện tại. Tất cả thành phần cần được kiểm tra trong trạng thái sau phục hồi.

## 3. Xác định phạm vi phục hồi cần kiểm chứng

Trước khi chạy kiểm tra, hãy xác định chính xác sự cố đã ảnh hưởng tới những phần nào. Phạm vi có thể gồm:

- Dịch vụ, API, worker, scheduler hoặc consumer.
- Region, cluster, namespace, host hoặc tenant.
- Endpoint, chức năng và luồng nghiệp vụ.
- Khoảng thời gian bắt đầu và kết thúc ảnh hưởng.
- Nhóm người dùng, loại tài khoản hoặc cohort.
- Database, bảng, partition, object storage hoặc message topic.
- Hệ thống đối tác và dependency bên ngoài.
- Artifact, config revision, secret version và deployment revision.

Không nên chỉ kiểm tra toàn bộ dịch vụ ở mức tổng quát. Nếu sự cố chỉ ảnh hưởng endpoint hoàn tiền, một health check chung không đủ. Nếu chỉ một region bị lỗi, cần xác minh riêng region đó và các luồng failover liên quan.

Một bản ghi phạm vi sự cố nên chỉ rõ điều gì đã biết, điều gì chưa chắc chắn và dữ liệu nào sẽ dùng để xác minh. Khi chưa xác định được toàn bộ phạm vi, ghi rõ giả định và tiếp tục điều tra theo bằng chứng.

## 4. Xây dựng tiêu chí phục hồi trước khi chạy kiểm tra

Tiêu chí phục hồi nên được xác định trong runbook hoặc incident plan, dựa trên SLO, yêu cầu nghiệp vụ và mức độ nghiêm trọng. Không nên chọn ngưỡng sau khi đã nhìn thấy kết quả chỉ để làm cho dashboard chuyển sang màu xanh.

Một tiêu chí có thể bao gồm:

1. Availability và readiness của các instance.
2. Tỷ lệ request thành công và latency của endpoint quan trọng.
3. Các giao dịch nghiệp vụ đại diện chạy thành công.
4. Dependency bắt buộc kết nối được và không có lỗi tăng bất thường.
5. Dữ liệu, queue và event được đối soát trong phạm vi ảnh hưởng.
6. Không còn traffic tới phiên bản hoặc instance ngoài kế hoạch.
7. Người dùng có thể tiếp tục các thao tác chính.
8. Cảnh báo nghiêm trọng đã được xử lý hoặc có owner và thời hạn rõ.

Tiêu chí cần định nghĩa phạm vi, ngưỡng, cửa sổ quan sát, số mẫu tối thiểu và nguồn dữ liệu. Ví dụ, tỷ lệ lỗi cần được đo theo endpoint hoặc nhóm request có liên quan; tỷ lệ giao dịch thành công cần so sánh với baseline cùng điều kiện tải.

## 5. Kiểm tra trạng thái kỹ thuật của dịch vụ

Lớp kiểm tra đầu tiên xác nhận các thành phần đã trở lại trạng thái mong muốn:

| Thành phần | Điều cần xác minh | Bằng chứng |
|---|---|---|
| Application process | Process chạy đúng release và không restart liên tục | Process state, restart count, startup log |
| Workload | Replica/instance đủ số lượng và sẵn sàng | Deployment status, Pod/VM state |
| Network/routing | Route, ingress, load balancer và service discovery hoạt động | Endpoint list, route check |
| Database | Kết nối, truy vấn bắt buộc và connection pool ổn định | DB health, query result, pool metric |
| Cache | Cache truy cập được và dữ liệu có thể tạo lại/đã warm-up | Cache health, hit rate, eviction |
| Queue/broker | Producer/consumer hoạt động, backlog được xử lý | Consumer state, lag, dead-letter count |
| Storage | File/object cần thiết đọc ghi được | Storage probe, permission check |
| Identity/secrets | Credential, certificate và quyền truy cập hợp lệ | Secret reference/version, auth result |

Không nên dùng một endpoint health duy nhất để kết luận toàn hệ thống đã phục hồi. Health check cần phản ánh đúng dependency bắt buộc, nhưng cũng không nên phụ thuộc quá nhiều vào dịch vụ không thiết yếu khiến toàn bộ ứng dụng bị coi là unhealthy khi một tính năng phụ bị gián đoạn.

## 6. Kiểm tra readiness và luồng request đầu cuối

Readiness xác nhận instance có thể nhận traffic; kiểm tra end-to-end xác nhận một request đi qua các thành phần cần thiết và tạo kết quả đúng.

Một bộ kiểm tra tối thiểu có thể gồm:

- Truy cập endpoint từ đúng network path mà client sử dụng.
- Xác thực bằng identity đại diện cho người dùng hoặc workload hợp lệ.
- Thực hiện thao tác đọc dữ liệu quan trọng.
- Thực hiện một giao dịch thử nghiệm an toàn nếu có thể.
- Xác minh response, side effect và trạng thái dữ liệu.
- Kiểm tra request không bị chuyển tới instance cũ hoặc sai region.

Smoke test sau phục hồi cần tránh tạo tác động thật ngoài ý muốn. Với thanh toán, gửi email hoặc tạo vận đơn, nên dùng sandbox, tenant thử nghiệm, giao dịch có thể hủy hoặc test harness được thiết kế riêng. Không dùng dữ liệu production ngẫu nhiên để thử ghi.

Nếu luồng nghiệp vụ không thể kiểm tra bằng giao dịch thử, có thể dùng synthetic check read-only, đối chiếu log/trace và kiểm tra invariant trên dữ liệu đã phát sinh.

## 7. Xác minh theo góc nhìn người dùng

Người dùng quan tâm họ có thể hoàn thành công việc hay không, không chỉ process có chạy. Vì vậy, cần kiểm tra các hành trình quan trọng (critical user journeys):

| Hành trình | Câu hỏi kiểm chứng |
|---|---|
| Đăng nhập | Người dùng có thể xác thực và nhận đúng quyền không? |
| Tra cứu | Dữ liệu hiển thị có đầy đủ và cập nhật không? |
| Tạo đơn/giao dịch | Request có hoàn tất và tạo đúng trạng thái không? |
| Thanh toán | Trạng thái giao dịch có khớp với cổng thanh toán và sổ cái không? |
| Upload/download | File có được lưu và truy xuất đúng không? |
| Thông báo | Email, SMS hoặc push có được gửi hoặc xếp hàng đúng không? |
| Quản trị | Nhân viên hỗ trợ có thể tra cứu và xử lý yêu cầu không? |

Nên chọn hành trình theo mức độ quan trọng, tần suất sử dụng và tác động khi thất bại. Một luồng có tỷ lệ sử dụng thấp nhưng ảnh hưởng tài chính hoặc dữ liệu nhạy cảm vẫn có thể là kiểm tra bắt buộc.

## 8. Kết hợp synthetic monitoring và dữ liệu người dùng thực

Hai nguồn bằng chứng bổ trợ nhau:

- **Synthetic monitoring:** hệ thống chủ động chạy request hoặc kịch bản thử nghiệm từ vị trí/môi trường xác định. Có thể kiểm tra khi lượng người dùng thấp hoặc khi chưa có traffic tự nhiên.
- **Real User Monitoring (RUM):** quan sát trải nghiệm thực tế từ request/session của người dùng, tùy mức thu thập và quyền riêng tư được cho phép.

Synthetic check giúp kiểm soát kịch bản và lặp lại ổn định, nhưng có thể không phản ánh hết cấu hình thiết bị, mạng hoặc hành vi thật. RUM cho thấy tác động thực tế nhưng có thể bị ảnh hưởng bởi sample rate, cache, vùng địa lý và nhóm người dùng.

Sau phục hồi, nên kết hợp:

1. Synthetic test từ các network path hoặc region quan trọng.
2. RUM theo phiên bản ứng dụng, endpoint, browser/device và region.
3. Metric server-side như error rate, latency và saturation.
4. Business event như thanh toán thành công, đơn được tạo hoặc tác vụ hoàn tất.

Không thu thập dữ liệu cá nhân quá mức để xác minh. Dùng định danh đã được pseudonymize, tổng hợp theo cohort và tuân thủ chính sách dữ liệu của tổ chức.

## 9. So sánh metric với baseline và SLO

Một metric đơn lẻ có thể gây hiểu nhầm. Sau phục hồi, nên so sánh với baseline trước incident và SLO/SLI đã thống nhất.

| Chỉ số | Cách xem xét |
|---|---|
| Availability | Tỷ lệ request hợp lệ được phục vụ trong cửa sổ quan sát |
| Error rate | So sánh tỷ lệ lỗi theo endpoint/status/business result với baseline |
| Latency | Xem p50/p95/p99 và các endpoint trọng yếu |
| Saturation | CPU, memory, connection pool, thread pool và queue capacity |
| Throughput | Request/giao dịch mỗi giây so với mức tải dự kiến |
| Retry/timeout | Xem có tăng bất thường hoặc tạo tải khuếch đại không |
| Business success | Tỷ lệ đơn hàng, thanh toán, upload hoặc workflow hoàn tất |
| Support demand | Số ticket, khiếu nại hoặc yêu cầu hỗ trợ liên quan |

SLO mô tả mức dịch vụ cần đạt trong một khoảng thời gian. Một vài phút metric xanh sau phục hồi chưa chắc đủ để kết luận SLO dài hạn đã được khôi phục. Cần xác định cửa sổ quan sát sau incident và cách tính error budget bị tiêu thụ trong thời gian gián đoạn.

Nếu baseline thay đổi theo giờ/ngày, so sánh với cùng khung thời gian hoặc nhóm traffic tương đương. Tránh so sánh một khoảng tải cao với baseline giờ thấp điểm rồi kết luận hệ thống đã ổn định.

## 10. Xác minh tính toàn vẹn và tính đầy đủ của dữ liệu

Phục hồi dịch vụ có thể hoàn tất trước khi dữ liệu được phục hồi đầy đủ. Đây là khoảng cách đặc biệt quan trọng với hệ thống giao dịch, tài chính, đơn hàng, hồ sơ và workflow nhiều bước.

Những câu hỏi cần trả lời:

- Có bản ghi nào bị mất, trùng hoặc cập nhật một phần không?
- Giao dịch đã được xác nhận với người dùng có tồn tại trong hệ thống chính không?
- Event đã publish có được consumer xử lý chưa?
- Có message bị đưa vào dead-letter queue hoặc bị retry quá nhiều không?
- Backup/restore có tạo ra khoảng thiếu dữ liệu so với thời điểm hiện tại không?
- Các hệ thống phụ có trạng thái đồng bộ với hệ thống nguồn không?
- Có side effect bên ngoài nào đã xảy ra nhưng hệ thống nội bộ chưa ghi nhận không?

Các cách kiểm chứng:

- Đối chiếu số lượng và tổng giá trị theo khoảng thời gian bị ảnh hưởng.
- Kiểm tra invariant nghiệp vụ, ví dụ tổng debit/credit cân bằng.
- Đối chiếu transaction ID giữa ứng dụng, database và nhà cung cấp.
- So sánh outbox, event log, queue offset và trạng thái consumer.
- Dùng checksum/count hoặc manifest cho file/object đã khôi phục.
- Kiểm tra các bản ghi ở ranh giới thời gian backup/restore.

Không nên chỉ so sánh số lượng bản ghi. Hai tập dữ liệu có cùng số lượng vẫn có thể chứa nội dung khác nhau. Với dữ liệu quan trọng, cần đối chiếu khóa định danh, trạng thái, tổng tiền hoặc invariant phù hợp.

## 11. Đối soát giao dịch và xử lý side effect

Một sự cố có thể làm hệ thống nội bộ và hệ thống bên ngoài không đồng nhất. Ví dụ, cổng thanh toán đã trừ tiền nhưng ứng dụng timeout trước khi ghi nhận kết quả; người dùng retry và tạo yêu cầu thứ hai.

Quy trình đối soát nên:

1. Xác định khoảng thời gian và loại giao dịch bị ảnh hưởng.
2. Tập hợp định danh giao dịch từ các hệ thống liên quan.
3. Phân loại giao dịch thành thành công, thất bại, đang chờ, trùng hoặc chưa xác định.
4. Đối chiếu với nguồn có thẩm quyền, chẳng hạn provider ledger hoặc bank settlement.
5. Chỉ replay/retry khi thao tác có idempotency key hoặc cơ chế chống trùng.
6. Dùng compensating transaction khi cần hoàn tiền, hủy đơn hoặc sửa trạng thái.
7. Lưu kết quả đối soát và người/phần mềm thực hiện.

Không retry mù một request có side effect nếu chưa biết request trước đã thành công hay chưa. Với trạng thái không xác định, cần truy vấn provider hoặc chờ reconciliation thay vì gửi lại lệnh có thể tạo giao dịch kép.

## 12. Khôi phục queue, event và background job

Sau khi dịch vụ online, backlog có thể vẫn lớn. Một worker đã khởi động chưa có nghĩa các tác vụ tồn đọng đã được xử lý.

Kiểm tra các chỉ số:

- Queue depth và tuổi của message cũ nhất.
- Consumer lag hoặc offset chưa xử lý.
- Tỷ lệ retry, nack và dead-letter.
- Throughput xử lý so với tốc độ message mới đến.
- Số job bị timeout hoặc lease hết hạn.
- Message trùng và kết quả idempotency.
- Thứ tự xử lý nếu nghiệp vụ yêu cầu ordering.

Nếu backlog lớn, tăng concurrency đột ngột có thể gây quá tải database hoặc dependency. Hãy tăng tải theo từng bước, theo dõi saturation và giới hạn tốc độ replay. Với message đã hết hạn hoặc không còn hợp lệ, cần quy tắc loại bỏ/đưa vào xử lý thủ công có kiểm soát.

## 13. Xác minh dependency và tích hợp bên ngoài

Ứng dụng có thể phục hồi nhưng dependency vẫn đang degraded. Một số kiểm tra cần bao gồm:

- Database primary/replica và replication lag.
- Cache, broker và object storage.
- Identity provider, secret manager và certificate authority.
- Payment gateway, email/SMS provider hoặc API đối tác.
- DNS, CDN, load balancer và network path.
- Hệ thống downstream nhận event hoặc dữ liệu đồng bộ.

Phân biệt lỗi do release với lỗi độc lập của dependency. Nếu dependency vẫn không ổn định, không nên kết luận toàn bộ dịch vụ đã phục hồi chỉ vì application health xanh. Có thể đánh dấu partial recovery, bật degraded mode hoặc giữ một số chức năng ở trạng thái hạn chế.

Kiểm tra tích hợp nên dùng endpoint và credential phù hợp. Không chạy thao tác ghi thật trên đối tác nếu chưa có kế hoạch và quyền được phê duyệt.

## 14. Xác minh bảo mật và quyền truy cập sau phục hồi

Một số sự cố phục hồi liên quan đến credential, failover, restore backup hoặc thao tác khẩn cấp. Sau phục hồi, cần xác minh:

- Quyền IAM/RBAC trở về mức dự kiến.
- Credential tạm thời đã được thu hồi hoặc hết hạn.
- Secret/certificate version đang dùng đúng và còn hiệu lực.
- Không còn debug endpoint, maintenance account hoặc access rule khẩn cấp ngoài kế hoạch.
- Audit log ghi nhận các thao tác phục hồi quan trọng.
- Artifact/config đang chạy có provenance và nguồn gốc xác minh được.
- Dữ liệu được restore không làm mở lại quyền hoặc policy đã bị thu hồi.

Nếu incident liên quan đến secret bị lộ, không dùng lại secret cũ chỉ vì ứng dụng chạy được. Rotation và xác minh consumer đã nhận credential mới là một phần của phục hồi.

## 15. Đánh giá tác động người dùng trong khoảng thời gian sự cố

Phục hồi kỹ thuật không xóa đi trải nghiệm đã xảy ra. Nhóm cần xác định:

- Bao nhiêu người dùng hoặc tenant có khả năng bị ảnh hưởng?
- Họ gặp lỗi ở bước nào và trong khoảng thời gian nào?
- Request bị từ chối, timeout hay có kết quả không rõ?
- Có giao dịch nào bị xử lý hai lần hoặc không hoàn tất?
- Có dữ liệu hoặc thông báo nào bị chậm/mất?
- Người dùng đã tự retry hoặc liên hệ hỗ trợ chưa?
- Có nhóm người dùng nào vẫn bị ảnh hưởng sau khi dịch vụ chung đã ổn định?

Nguồn dữ liệu có thể gồm access log, trace, business event, audit log, support ticket, provider report và RUM. Cần tuân thủ quyền riêng tư, giới hạn dữ liệu và retention. Khi chưa thể xác định con số chính xác, hãy công bố phạm vi ước tính và cách tiếp tục xác minh.

Phân loại impact giúp chọn hành động:

| Mức tác động | Ví dụ | Hành động |
|---|---|---|
| Không có bằng chứng người dùng bị ảnh hưởng | Probe nội bộ lỗi nhưng request người dùng vẫn đạt | Lưu bằng chứng và tiếp tục quan sát |
| Gián đoạn tạm thời, không mất dữ liệu | Request timeout nhưng retry thành công | Xác nhận tỷ lệ retry và thông báo nếu cần |
| Giao dịch chưa rõ trạng thái | Provider có thể đã xử lý nhưng ứng dụng chưa ghi nhận | Đối soát trước khi retry hoặc hoàn tiền |
| Dữ liệu thiếu/trùng/sai | Đơn hàng thiếu event hoặc số tiền sai | Dừng luồng liên quan, repair/compensate và xác minh |
| Ảnh hưởng bảo mật/riêng tư | Người không có quyền có thể truy cập dữ liệu | Containment, đánh giá phạm vi và quy trình thông báo theo policy |

## 16. Khôi phục trải nghiệm và hỗ trợ người dùng

Sau khi xác định tác động, nhóm cần xử lý phần việc còn lại:

- Cập nhật trạng thái yêu cầu hoặc giao dịch đang chờ.
- Gửi lại thông báo bị thiếu theo cách tránh gửi trùng.
- Cho phép người dùng tiếp tục workflow bị gián đoạn.
- Hoàn tiền, hủy hoặc sửa giao dịch theo quy trình được phê duyệt.
- Cung cấp hướng dẫn rõ cho thao tác cần người dùng thực hiện lại.
- Cập nhật đội hỗ trợ với mã lỗi, khoảng thời gian và cách tra cứu.
- Theo dõi ticket còn tồn và xác nhận từng nhóm tác động đã được xử lý.

Thông điệp tới người dùng nên nói rõ dịch vụ đã hoạt động trở lại ở phạm vi nào, có giao dịch nào cần kiểm tra và người dùng cần làm gì. Tránh khẳng định dữ liệu hoàn toàn an toàn hoặc mọi giao dịch đã được khôi phục nếu việc đối soát chưa xong.

Với sự cố nghiêm trọng, thông báo ban đầu có thể được cập nhật theo từng mốc: dịch vụ phục hồi, dữ liệu đã đối soát, tác động cuối cùng và biện pháp hỗ trợ. Người phụ trách truyền thông cần dùng thông tin đã được incident owner xác nhận.

## 17. Xác minh theo tenant, region và cohort

Một hệ thống đa tenant hoặc đa region có thể chỉ phục hồi một phần. Không nên dùng một kết quả tổng hợp để che khuất nhóm vẫn còn lỗi.

Nên phân đoạn kiểm tra theo:

- Region/zone/cluster.
- Tenant hoặc loại tài khoản.
- Endpoint và luồng nghiệp vụ.
- Phiên bản client/browser/mobile app.
- Nhóm traffic hoặc cohort rollout.
- Loại dữ liệu và thời điểm phát sinh.

Ví dụ, API đã hoạt động ở hai region nhưng region thứ ba vẫn đang đồng bộ dữ liệu. Trạng thái phù hợp là partial recovery, kèm phạm vi và thời gian dự kiến hoàn tất. Tương tự, người dùng mới có thể đăng nhập được trong khi session cũ vẫn lỗi; cần kiểm tra cả hai nhóm.

## 18. Chọn cửa sổ quan sát sau phục hồi

Một lần kiểm tra thành công ngay sau deploy chưa đủ để kết luận dịch vụ ổn định. Cần có cửa sổ quan sát phù hợp với chu kỳ hoạt động và mức tải.

Khi chọn cửa sổ, cân nhắc:

- Thời gian khởi động và warm-up.
- Chu kỳ tải cao/thấp trong ngày.
- Tần suất chạy scheduled job.
- Thời gian xử lý queue/backlog.
- Chu kỳ batch, settlement hoặc đồng bộ dữ liệu.
- Thời gian provider bên ngoài cập nhật trạng thái.
- Số lượng request/giao dịch tối thiểu cần quan sát.

Với API có lưu lượng lớn, vài phút có thể đủ để phát hiện lỗi phổ biến. Với tác vụ chạy mỗi giờ hoặc thanh toán đối soát cuối ngày, cần theo dõi ít nhất qua chu kỳ nghiệp vụ liên quan. Cửa sổ cần được xác định theo loại dịch vụ, không dùng một thời lượng cố định cho tất cả.

Nếu hệ thống đang ở tải thấp, synthetic test có thể cung cấp bằng chứng bổ sung. Nhưng synthetic test không thay thế việc xác minh backlog, dữ liệu và traffic thật.

## 19. Trạng thái phục hồi và điều kiện đóng incident

Nên dùng trạng thái phản ánh cả kỹ thuật lẫn tác động người dùng:

| Trạng thái | Ý nghĩa |
|---|---|
| Recovering | Đang thực hiện rollback/failover/restore hoặc thao tác sửa |
| Service restored | Luồng dịch vụ chính đã hoạt động trong ngưỡng |
| Partially recovered | Một số region, tenant, chức năng hoặc dependency còn hạn chế |
| Data reconciliation pending | Dịch vụ hoạt động nhưng dữ liệu/giao dịch còn cần đối soát |
| User remediation pending | Còn ticket, thông báo, hoàn tiền hoặc hỗ trợ người dùng |
| Monitoring | Các kiểm tra đạt ban đầu và đang trong cửa sổ quan sát |
| Resolved | Dịch vụ ổn định, tác động đã xử lý hoặc phần còn lại có owner/deadline được chấp nhận |
| Closed | Incident đã được đóng theo quy trình, bằng chứng và follow-up được lưu |

Không nên đóng incident chỉ vì dashboard chuyển xanh. Điều kiện đóng nên bao gồm:

- Dịch vụ đạt tiêu chí kỹ thuật và nghiệp vụ.
- Artifact/config đang chạy được xác minh.
- Dữ liệu quan trọng đã được đối soát hoặc có kế hoạch được chấp thuận.
- User impact đã được định lượng trong phạm vi có thể.
- Thông báo/hỗ trợ cần thiết đã được thực hiện.
- Không còn hành động khẩn cấp không có owner.
- Các vấn đề còn lại có ticket, người chịu trách nhiệm và thời hạn.
- Incident record và timeline được lưu.

## 20. Ví dụ: kiểm chứng sau rollback của dịch vụ đơn hàng

Giả sử release mới gây lỗi khiến một số đơn hàng không phát event sang dịch vụ giao vận. Nhóm rollback về artifact trước đó và mở lại traffic.

| Lớp | Kiểm tra | Điều kiện xác nhận |
|---|---|---|
| Artifact | Image digest của tất cả instance khớp release ổn định | Không còn instance sai digest nhận traffic |
| Availability | API tạo/tra cứu đơn trả kết quả đúng | Readiness và error rate trong ngưỡng |
| Business flow | Tạo đơn thử và xác minh trạng thái | Đơn thử có trạng thái hợp lệ và không tạo side effect thật |
| Data | Đối chiếu đơn trong khoảng incident | Không còn đơn thiếu trạng thái hoặc có owner xử lý |
| Event | So sánh outbox với event broker và consumer | Event thiếu được replay an toàn; backlog giảm |
| User impact | Xác định khách hàng và đơn bị ảnh hưởng | Có danh sách phạm vi, thông báo/hỗ trợ theo policy |
| Monitoring | Theo dõi error, latency và tỷ lệ đơn thành công | Đạt guardrail qua cửa sổ quan sát |

Nhóm không tuyên bố incident đã hoàn tất ngay khi API hoạt động lại. Trạng thái được chuyển sang service restored, data reconciliation pending cho đến khi các đơn bị thiếu event được xử lý và đối soát. Sau đó, nhóm kiểm tra lại tỷ lệ giao vận và các ticket liên quan trước khi đóng incident.

## 21. Ví dụ record kiểm chứng sau phục hồi

Một record khái niệm có thể được lưu như sau:

    recoveryVerification:
      incidentId: INC-2048
      service: order-service
      environment: production
      recoveryAction: rollback
      restoredRelease:
        id: R-104
        artifactDigest: sha256:aaa...
        configRevision: cfg-31
      serviceChecks:
        readiness: passed
        smokeTests: passed
        errorRate: within_guardrail
        latency: within_guardrail
      dataChecks:
        reconciliation: pending
        affectedOrders: 18
        owner: order-operations
      userImpact:
        scope: identified
        communication: sent
        remediation: in_progress
      decision: service_restored_impact_pending

Đây là cấu trúc minh họa, không phải schema của một công cụ cụ thể. Các số liệu phải lấy từ bằng chứng thực tế; không điền số ước lượng như số chính xác. Không lưu thông tin cá nhân hoặc secret không cần thiết trong record. Khi đối soát hoàn tất, cập nhật trạng thái và liên kết báo cáo có quyền truy cập phù hợp.

## 22. Đo lường chất lượng phục hồi

Các chỉ số có thể giúp đánh giá quy trình:

- **Time to service restoration:** từ lúc dịch vụ suy giảm đến khi các luồng chính trở lại trong ngưỡng.
- **Time to user impact resolution:** từ lúc bắt đầu sự cố đến khi tác động còn tồn đọng được xử lý.
- **Recovery verification duration:** thời gian từ khi thao tác phục hồi xong đến khi đủ bằng chứng xác nhận.
- **Data reconciliation completion:** tỷ lệ bản ghi/giao dịch bị ảnh hưởng đã được đối soát.
- **Backlog clearance time:** thời gian xử lý hết backlog liên quan.
- **Residual error rate:** lỗi còn lại sau khi phục hồi.
- **Repeat incident rate:** tỷ lệ sự cố tái diễn do cùng nguyên nhân hoặc cùng thiếu sót.
- **Communication timeliness:** thời gian gửi thông tin phù hợp cho người dùng và các nhóm liên quan.

Không nên tối ưu một chỉ số bằng cách bỏ qua chỉ số khác. Rút ngắn time to service restoration bằng cách mở traffic sớm có thể làm tăng data repair và user impact resolution. Cần theo dõi cả thời điểm dịch vụ trở lại và thời điểm tác động được xử lý.

## 23. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Đóng incident ngay khi rollback xong | Bỏ sót lỗi runtime, dữ liệu và người dùng | Tách recovery action, service restored và impact resolved |
| Chỉ kiểm tra health endpoint | Không phát hiện lỗi nghiệp vụ hoặc side effect | Kiểm tra critical user journeys và business invariants |
| Chỉ kiểm tra một instance | Bỏ sót workload cũ hoặc sai phiên bản | Xác minh toàn bộ instance, endpoint và traffic |
| Coi queue consumer active là backlog đã xử lý | Message cũ vẫn tồn đọng hoặc bị dead-letter | Theo dõi lag, tuổi message và kết quả xử lý |
| Retry giao dịch không rõ trạng thái | Có thể tạo giao dịch trùng | Đối soát provider và dùng idempotency |
| Chỉ so sánh số lượng bản ghi | Không phát hiện nội dung sai hoặc trùng | Đối chiếu ID, trạng thái, tổng giá trị và invariant |
| Thông báo “mọi thứ đã bình thường” quá sớm | Người dùng không biết giao dịch nào còn bị ảnh hưởng | Cập nhật theo phạm vi và bằng chứng đã xác nhận |
| Quan sát quá ngắn | Lỗi theo batch/chu kỳ chưa xuất hiện | Chọn cửa sổ theo chu kỳ nghiệp vụ |
| Gộp partial recovery thành success | Che khuất region/tenant/chức năng còn lỗi | Ghi trạng thái theo phạm vi và owner |
| Không lưu bằng chứng sau phục hồi | Khó kiểm toán và học từ incident | Tạo recovery verification record và timeline |

## 24. Checklist kiểm chứng dịch vụ và tác động người dùng

Sau khi thực hiện rollback, failover, restore hoặc roll-forward, hãy xác minh:

- [ ] Phạm vi incident, service, region, tenant và khoảng thời gian ảnh hưởng đã được xác định.
- [ ] Artifact digest, config revision và release đang chạy khớp với trạng thái được phê duyệt.
- [ ] Tất cả instance/workload cần thiết đã ready và không còn backend sai phiên bản ngoài kế hoạch.
- [ ] Endpoint, routing và traffic thực tế đi tới đúng backend.
- [ ] Critical user journeys và smoke/integration test đạt.
- [ ] Error rate, latency, saturation và business metrics trở lại guardrail.
- [ ] Database, storage, queue, event và dependency đã được kiểm tra.
- [ ] Dữ liệu/giao dịch bị ảnh hưởng đã được đối soát hoặc có owner và deadline.
- [ ] Retry/replay/compensation không tạo side effect trùng.
- [ ] Secret, quyền truy cập và cấu hình khẩn cấp đã được rà soát.
- [ ] Tác động người dùng được định lượng trong phạm vi có thể và thông báo phù hợp.
- [ ] Backlog và ticket hỗ trợ còn lại có kế hoạch xử lý.
- [ ] Cửa sổ quan sát đủ đại diện với chu kỳ tải/nghiệp vụ.
- [ ] Trạng thái service restored được phân biệt với impact resolved.
- [ ] Recovery record, timeline, metric và quyết định được lưu.

## 25. Nguyên tắc thực hành cốt lõi

1. Không coi thao tác rollback/restore hoàn tất là bằng chứng dịch vụ và người dùng đã phục hồi.
2. Tách recovery action, service restored và user impact resolved thành các mốc riêng.
3. Xác định phạm vi ảnh hưởng theo service, region, tenant, chức năng, dữ liệu và thời gian.
4. Kiểm tra artifact/config thực tế, toàn bộ instance, routing và traffic.
5. Kết hợp health/readiness, smoke test, critical user journey và business invariant.
6. Đối chiếu dữ liệu, giao dịch, event và backlog; dùng idempotency trước khi retry/replay.
7. Đánh giá dependency, security, secret và quyền truy cập sau thao tác khẩn cấp.
8. Kết hợp synthetic monitoring, RUM, telemetry và baseline trong cửa sổ quan sát phù hợp.
9. Xác định tác động người dùng, thực hiện remediation và truyền thông trung thực theo bằng chứng.
10. Chỉ đóng incident khi tiêu chí kỹ thuật, dữ liệu, người dùng và follow-up đã được xử lý hoặc giao owner rõ ràng.

Phục hồi chỉ thực sự hoàn tất khi dịch vụ vận hành ổn định và tác động còn lại được hiểu, xử lý hoặc quản lý có trách nhiệm. Kiểm chứng theo cả góc nhìn hệ thống lẫn người dùng giúp nhóm tránh tuyên bố phục hồi quá sớm, bảo vệ tính toàn vẹn dữ liệu và tạo bằng chứng đáng tin cậy cho việc đóng incident.
