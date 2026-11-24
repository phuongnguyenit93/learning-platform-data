# Thử nghiệm lỗi có kiểm soát và xác minh khả năng phục hồi

Một kiến trúc được thiết kế để có tính sẵn sàng cao vẫn có thể thất bại khi gặp sự cố thật. Health check có thể phát hiện sai, autoscaling có thể không tạo đủ máy, replica có thể trễ, ứng dụng có thể mất kết nối khi chuyển vùng hoặc quy trình khôi phục có thể phụ thuộc vào một tài khoản và một người vận hành duy nhất. Đọc tài liệu thiết kế chưa đủ để biết hệ thống sẽ phản ứng ra sao khi một thành phần biến mất.

**Thử nghiệm lỗi có kiểm soát (controlled fault testing)** chủ động tạo một tình huống lỗi có giới hạn để quan sát cách workload phát hiện, cô lập, chuyển tải, khôi phục và bảo toàn dữ liệu. **Fault injection** là kỹ thuật đưa lỗi vào một thành phần hoặc đường đi cụ thể. **Chaos engineering** mở rộng cách tiếp cận này thành một chương trình thử nghiệm có giả thuyết, phạm vi, quan sát, kiểm soát rủi ro và học hỏi liên tục.

Trong **CLOUD_CORE_SERVICES_COMPUTE**, thử nghiệm có thể bao gồm dừng một VM, làm một instance mất kết nối, tăng latency, mô phỏng lỗi storage, làm một dependency tạm thời không sẵn sàng hoặc kiểm tra khả năng phục hồi khi một zone bị cô lập. Kết quả cần chứng minh được hệ thống giữ SLO, khôi phục trong RTO, giới hạn mất dữ liệu trong RPO và trở lại trạng thái ổn định sau khi lỗi kết thúc.

## 1. Vì sao cần thử nghiệm lỗi?

High availability (HA) và fault tolerance thường được mô tả bằng nhiều thành phần dự phòng: nhiều VM, load balancer, replica database, nhiều zone, autoscaling và backup. Nhưng sự hiện diện của các thành phần này không chứng minh failover hoạt động đúng.

Một số tình huống chỉ lộ ra khi có lỗi:

- Load balancer vẫn gửi request đến instance đã mất khả năng phục vụ vì health check quá nông.
- Autoscaler phát hiện thiếu capacity nhưng subnet hết địa chỉ IP nên không tạo được VM thay thế.
- Replica có dữ liệu nhưng ứng dụng không chuyển kết nối đến replica đó.
- Retry không có giới hạn làm tăng tải lên dependency đang lỗi.
- Một lần mất kết nối ngắn khiến message bị xử lý hai lần.
- VM mới được tạo nhưng bootstrap thiếu quyền đọc secret nên không trở thành healthy.
- Backup hoàn tất nhưng không thể restore trong thời gian yêu cầu.
- Failover sang zone khác hoạt động, nhưng failback làm dữ liệu ghi mới bị ghi đè.

Thử nghiệm có kiểm soát biến những giả định này thành bằng chứng có thể đo lường. Nó giúp phát hiện khoảng cách giữa thiết kế dự kiến và hành vi thực tế trước khi một sự cố ngoài ý muốn xảy ra.

## 2. Phân biệt fault injection, chaos engineering và DR drill

Các hoạt động liên quan nhưng có mục tiêu và phạm vi khác nhau:

| Hoạt động | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Fault injection | Tạo một lỗi cụ thể để kiểm tra phản ứng của thành phần | Dừng một VM hoặc thêm độ trễ mạng |
| Chaos experiment | Kiểm tra giả thuyết về hành vi của hệ thống dưới một lỗi có giới hạn | Mất một instance nhưng API vẫn giữ SLO |
| Load/stress test | Đo khả năng xử lý tải và tìm giới hạn capacity | Tăng request/giây đến ngưỡng xác định |
| Failover test | Kiểm tra chuyển sang thành phần dự phòng | Chuyển database primary sang replica |
| Disaster recovery (DR) drill | Diễn tập phục hồi dịch vụ/dữ liệu sau thảm họa | Khôi phục workload sang region dự phòng |
| Game day | Diễn tập phối hợp giữa kỹ thuật, vận hành và người ứng cứu | Giả lập outage và thực hiện runbook |

Một bài thử có thể kết hợp nhiều kỹ thuật, nhưng cần ghi rõ câu hỏi đang kiểm chứng. Ví dụ, dừng một VM trong group là fault injection; kiểm tra toàn bộ dịch vụ vẫn đạt SLO và group tự phục hồi là chaos experiment; khôi phục cả dịch vụ từ backup ở region khác là DR drill.

## 3. Xác định giả thuyết và trạng thái bình thường

Một thử nghiệm tốt bắt đầu bằng giả thuyết có thể đo được. Không bắt đầu bằng câu “hãy làm hệ thống lỗi để xem chuyện gì xảy ra”.

### 3.1. Viết giả thuyết

Giả thuyết nên mô tả:

- Sự kiện lỗi được tạo ra.
- Hệ thống được kỳ vọng phản ứng thế nào.
- Chỉ số nào chứng minh dịch vụ vẫn hoạt động.
- Thời gian phát hiện và phục hồi mong muốn.
- Mức độ ảnh hưởng tối đa chấp nhận được.

Ví dụ:

> Khi một VM trong nhóm API bị dừng đột ngột, load balancer sẽ ngừng gửi request đến VM đó, các VM còn lại tiếp tục phục vụ với tỷ lệ lỗi dưới ngưỡng đã định, managed group tạo thành viên thay thế và healthy capacity trở lại mức mục tiêu trong vòng 5 phút.

Đây là giả thuyết thử nghiệm, không phải cam kết mặc định của mọi cloud provider. Nhóm cần đặt ngưỡng dựa trên SLO và kiến trúc thực tế.

### 3.2. Xác định steady state

**Steady state** là trạng thái bình thường mà hệ thống cần duy trì. Không nên chỉ dùng CPU utilization làm đại diện cho trạng thái ổn định.

Các tín hiệu có thể gồm:

- Request success rate và error rate.
- p50, p95, p99 latency.
- Throughput hoặc số request/giây.
- Số backend healthy và số instance sẵn sàng.
- Queue depth và consumer lag.
- Database connection, query latency và replication lag.
- Tỷ lệ transaction hoàn tất và tính toàn vẹn dữ liệu.
- Tỷ lệ retry, timeout và circuit breaker open.

Chọn một tập nhỏ các tín hiệu quan trọng, có thể đo liên tục và phản ánh trải nghiệm người dùng. Nếu dịch vụ vẫn trả HTTP 200 nhưng dữ liệu sai hoặc giao dịch bị mất, steady state chưa được duy trì.

### 3.3. Đặt ngưỡng thành công

Một thử nghiệm cần có tiêu chí rõ ràng, ví dụ:

| Tín hiệu | Tiêu chí minh họa |
| --- | --- |
| Request success rate | Không thấp hơn 99,5% trong cửa sổ thử |
| p95 latency | Không vượt 500 ms quá 2 phút |
| Healthy backend | Luôn còn ít nhất 3 instance |
| Detection time | Lỗi được phát hiện trong 30 giây |
| Replacement time | Instance thay thế healthy trong 5 phút |
| Data integrity | Không mất hoặc nhân đôi giao dịch đã xác nhận |

Các con số chỉ minh họa cách viết tiêu chí. Dùng SLO, RTO, RPO và mức tải thực tế của hệ thống để đặt ngưỡng chính thức.

## 4. Nguyên tắc thiết kế thử nghiệm an toàn

Fault injection có thể gây gián đoạn thật. Cần giới hạn tác động và bảo đảm có cách dừng thử nghiệm.

### 4.1. Bắt đầu với phạm vi nhỏ

Thử nghiệm theo thứ tự tăng dần:

1. Môi trường local hoặc sandbox.
2. Môi trường test/staging có cấu hình gần production.
3. Một instance hoặc một nhóm nhỏ được chọn rõ ràng.
4. Một phần traffic hoặc một nhóm người dùng thử nghiệm.
5. Production có kiểm soát, khi đã có bằng chứng từ các bước trước và được phê duyệt theo quy trình tổ chức.

Không bắt đầu bằng cách tắt cả region hoặc làm gián đoạn một dependency dùng chung cho nhiều hệ thống.

### 4.2. Giới hạn blast radius

Blast radius là phạm vi tài nguyên hoặc người dùng có thể bị ảnh hưởng. Có thể giới hạn bằng:

- Chọn target theo tag/label, instance ID hoặc namespace riêng.
- Giới hạn số instance, phần trăm traffic hoặc số worker bị tác động.
- Dùng account/project/subscription và VPC/VNet thử nghiệm riêng.
- Giới hạn thời gian lỗi và tự động hết hạn.
- Không chọn tài nguyên dùng chung ngoài phạm vi.
- Chặn thử nghiệm khi healthy capacity thấp hơn ngưỡng an toàn.

Target selector cần được kiểm tra trước khi chạy. Một bộ lọc tag sai có thể chọn toàn bộ fleet thay vì một VM thử nghiệm.

### 4.3. Guardrails và điều kiện abort

Guardrails là các giới hạn ngăn thử nghiệm vượt khỏi phạm vi. Ví dụ:

- Dừng thử nghiệm nếu error rate vượt ngưỡng trong hai cửa sổ liên tiếp.
- Dừng nếu healthy backend giảm dưới capacity tối thiểu.
- Dừng nếu database replication lag vượt giới hạn.
- Dừng nếu queue depth tăng liên tục hoặc consumer lag không giảm.
- Dừng nếu latency vượt SLO hoặc có dấu hiệu ảnh hưởng người dùng ngoài nhóm thử.
- Dừng nếu monitoring/alerting không hoạt động.

Abort condition phải được xác định trước và có người hoặc cơ chế tự động thực thi. Không chờ đến khi toàn hệ thống mất khả năng phục vụ mới quyết định dừng.

### 4.4. Chuẩn bị khôi phục trước khi gây lỗi

Trước thử nghiệm cần:

- Xác định người chịu trách nhiệm và kênh liên lạc.
- Kiểm tra backup/snapshot và khả năng restore nếu thử nghiệm có thể ảnh hưởng dữ liệu.
- Xác định lệnh hoặc thao tác rollback/stop experiment.
- Bảo đảm có quyền truy cập ngoài băng (out-of-band) nếu network bị tác động.
- Kiểm tra monitoring, logging, tracing và alert routing.
- Xác nhận capacity dự phòng và quota đủ cho phục hồi.
- Thông báo đúng nhóm vận hành và người dùng thử nghiệm.
- Ghi lại baseline và thời điểm bắt đầu.

Không thử nghiệm trên dữ liệu production bằng cách xóa hoặc sửa dữ liệu thật. Dùng dữ liệu tổng hợp, tenant thử nghiệm hoặc cơ chế cô lập phù hợp.

## 5. Vòng đời của một chaos experiment

~~~mermaid
flowchart TD
    A["Chọn rủi ro và giả thuyết"] --> B["Đo steady state và đặt SLO"]
    B --> C["Chọn target, blast radius và thời lượng"]
    C --> D["Kiểm tra guardrails, rollback và backup"]
    D --> E{"Pre-check đạt?"}
    E -- "Không" --> F["Hủy hoặc lên lịch lại"]
    E -- "Có" --> G["Inject fault có kiểm soát"]
    G --> H["Quan sát metric, log, trace và alert"]
    H --> I{"Vượt ngưỡng abort?"}
    I -- "Có" --> J["Dừng fault và phục hồi"]
    I -- "Không" --> K["Kết thúc theo thời lượng"]
    J --> L["Xác minh recovery và data integrity"]
    K --> L
    L --> M["Đối chiếu giả thuyết và ghi bài học"]
    M --> N["Tạo hành động cải thiện và thử lại"]
~~~

Một vòng thử nghiệm nên có đầy đủ các bước sau:

1. Chọn một failure mode có ý nghĩa với kiến trúc.
2. Viết giả thuyết và steady-state metrics.
3. Xác định target và giới hạn tác động.
4. Chạy pre-check.
5. Bắt đầu fault injection và ghi timestamp.
6. Quan sát hệ thống trong thời gian xác định.
7. Dừng fault hoặc kích hoạt abort.
8. Xác minh hệ thống phục hồi hoàn toàn.
9. Đối chiếu kết quả với giả thuyết.
10. Ghi finding, owner, deadline và thử lại sau khi sửa.

## 6. Các nhóm lỗi nên kiểm tra trong compute workload

Không cần thử mọi loại lỗi cùng lúc. Chọn kịch bản dựa trên rủi ro, kiến trúc và lịch sử sự cố.

| Nhóm lỗi | Fault có thể mô phỏng | Khả năng cần xác minh |
| --- | --- | --- |
| Compute/VM | Dừng hoặc terminate một VM | Load balancer loại backend lỗi, group thay máy |
| CPU | Tạo CPU contention có giới hạn | Queue, latency, autoscaling và throttling |
| Memory | Tăng memory pressure trong target test | OOM handling, restart và capacity |
| Network | Thêm latency, packet loss hoặc partition | Timeout, retry, circuit breaker và failover |
| DNS | Làm truy vấn DNS thất bại hoặc trả kết quả trễ trong môi trường thử | Cache DNS, retry và khả năng dùng endpoint dự phòng |
| Storage | Mô phỏng I/O chậm, read-only hoặc mất mount | Timeout, retry, integrity và recovery |
| Dependency | Làm database/cache/queue tạm thời unavailable | Degraded mode, fallback và phục hồi kết nối |
| Zone | Cô lập traffic hoặc capacity của một zone thử nghiệm | Phân phối lại traffic và capacity còn lại |
| Identity | Làm credential thử nghiệm hết hạn hoặc thiếu quyền | Refresh, retry, alert và least privilege |
| Process | Kill một process hoặc service | Supervisor, restart policy và readiness |

### 6.1. Mất một VM trong managed group

Đây là thử nghiệm cơ bản cho fleet stateless:

- Chọn một VM không giữ dữ liệu duy nhất.
- Xác nhận group còn đủ healthy capacity sau khi mất một thành viên.
- Dừng hoặc terminate đúng VM thử nghiệm bằng cơ chế được phê duyệt.
- Theo dõi health check và việc loại backend khỏi traffic.
- Quan sát group tạo VM mới từ template đang dùng.
- Xác minh VM mới hoàn tất bootstrap, identity và readiness.
- Xác minh healthy capacity trở về mục tiêu.

Kết quả không chỉ là “VM mới đã được tạo”. Cần kiểm tra request có bị lỗi, session có mất, queue có xử lý trùng và instance mới có đúng template revision hay không.

### 6.2. CPU contention

CPU contention mô phỏng tình huống một tiến trình tiêu thụ nhiều CPU làm giảm phần tài nguyên còn lại cho ứng dụng. Nó có thể làm tăng request queue, latency và thời gian xử lý.

Trong một VM thử nghiệm riêng, có thể dùng công cụ stress có giới hạn thời gian:

~~~bash
# Chỉ chạy trên VM thử nghiệm đã cô lập
stress-ng --cpu 2 --timeout 60s
~~~

Theo dõi CPU utilization, run queue, steal time nếu có, request latency, error rate và autoscaling signal. Không chạy lệnh này trên host dùng chung hoặc VM production ngoài phạm vi thử nghiệm đã được phê duyệt. Giới hạn số worker và thời gian theo capacity thực tế.

### 6.3. Network latency và packet loss

Network fault có thể được mô phỏng bằng công cụ network emulation trên một interface của máy thử nghiệm. Ví dụ với Linux traffic control:

~~~bash
# Ví dụ minh họa trên interface của VM thử nghiệm
sudo tc qdisc add dev eth0 root netem delay 100ms 20ms loss 1%

# Xóa quy tắc sau thử nghiệm
sudo tc qdisc del dev eth0 root
~~~

Quy tắc trên tác động traffic qua interface đã chọn và có thể làm mất kết nối quản trị. Chỉ chạy trong môi trường cô lập, xác minh đúng interface và chuẩn bị console ngoài băng hoặc cơ chế tự động xóa quy tắc. Với hệ thống dùng chung, ưu tiên công cụ chaos có selector và thời hạn rõ ràng.

Khi thử network fault, quan sát:

- Timeout và retry có bị nhân lên không?
- Retry có backoff và jitter không?
- Connection pool có phục hồi sau khi network trở lại không?
- Circuit breaker có mở và đóng đúng lúc không?
- Request idempotency có ngăn thao tác lặp không?
- DNS cache có giữ địa chỉ cũ quá lâu không?

### 6.4. Storage latency hoặc mất mount

Storage fault cần được thử trên volume/dataset không chứa dữ liệu production quan trọng. Có thể mô phỏng I/O latency bằng công cụ phù hợp trong môi trường kiểm thử, hoặc dùng fault injection capability của nền tảng nếu hỗ trợ.

Các câu hỏi cần xác minh:

- Ứng dụng có timeout khi storage phản hồi chậm không?
- Queue hoặc thread pool có bị chiếm hết bởi I/O đang chờ không?
- Retry có tạo thêm tải lên volume đang lỗi không?
- Khi mount biến mất, ứng dụng có dừng ghi thay vì ghi nhầm vào thư mục trên root disk không?
- Sau khi volume trở lại, dữ liệu có nhất quán và filesystem có được mount đúng không?

Không tháo volume production đang được ghi để thử lỗi. Dùng snapshot/clone hoặc môi trường test có dữ liệu tổng hợp.

### 6.5. Dependency unavailable

Một dịch vụ compute thường phụ thuộc database, cache, message broker, DNS, identity provider hoặc secret manager. Hãy thử từng dependency riêng:

- Làm endpoint thử nghiệm không nhận kết nối trong một khoảng ngắn.
- Giới hạn connection pool để quan sát queue và timeout.
- Làm cache unavailable để kiểm tra fallback và database load.
- Tạm dừng consumer trong test queue để đo backlog và khả năng catch up.
- Làm token thử nghiệm hết hạn để kiểm tra refresh flow.

Đặt timeout hữu hạn và retry budget. Một dependency unavailable không nên khiến ứng dụng tạo vô hạn thread hoặc request retry.

### 6.6. Zone failure

Không nhất thiết phải làm sập một availability zone thật để kiểm tra khả năng chịu lỗi. Có thể mô phỏng bằng cách:

- Loại một nhóm backend thuộc zone khỏi load balancer.
- Giới hạn hoặc dừng các instance thử nghiệm trong zone đó.
- Chặn traffic giữa các thành phần test theo một hướng xác định.
- Tạo kịch bản capacity còn lại chỉ bằng các zone khác.

Sau đó xác minh load balancer phân phối traffic, group giữ đủ capacity, database/cache có endpoint phù hợp và hệ thống không phụ thuộc vào một tài nguyên duy nhất ở zone bị cô lập.

## 7. Xác minh khả năng phục hồi

Khôi phục không có nghĩa chỉ dừng fault injection. Cần xác nhận mọi lớp trở lại hoạt động và không còn tác động phụ.

### 7.1. Detection và isolation

Kiểm tra:

- Hệ thống có phát hiện lỗi không?
- Alert có được gửi đến đúng người và đúng kênh không?
- Health check có loại backend lỗi khỏi traffic không?
- Circuit breaker có ngăn request tiếp tục dồn vào dependency lỗi không?
- Autoscaler/autohealer có phản ứng theo chính sách không?

Ghi lại thời gian từ lúc fault bắt đầu đến lúc hệ thống phát hiện và cô lập thành phần lỗi.

### 7.2. Failover và continuity

Kiểm tra:

- Traffic có được chuyển đến thành phần healthy không?
- Capacity còn lại có đủ phục vụ tải bình thường không?
- Session hoặc request đang xử lý được tiếp tục, retry hay trả lỗi có kiểm soát?
- Consumer có tiếp tục xử lý message mà không mất hoặc nhân đôi?
- Replica/database primary mới có nhận ghi đúng không?
- Dependency khác có bị quá tải do traffic chuyển hướng không?

Failover có thể làm một dependency dự phòng trở thành điểm nóng. Cần quan sát tải trên replica, cache, network và các zone còn lại.

### 7.3. Data integrity

Với workload có ghi dữ liệu, tạo bộ kiểm tra tính toàn vẹn:

- Ghi số lượng transaction đã xác nhận trước, trong và sau thử nghiệm.
- Dùng request ID hoặc idempotency key để phát hiện duplicate.
- Đối chiếu checksum hoặc record count trên nguồn và replica.
- Kiểm tra transaction chưa commit và message đang xử lý.
- Xác minh thứ tự sự kiện nếu hệ thống yêu cầu ordering.
- Kiểm tra dữ liệu mới không bị ghi đè khi failback.

Không dùng riêng HTTP success rate để kết luận dữ liệu an toàn. Một request có thể trả thành công trong khi write chưa được replicate hoặc message chưa được commit bền vững.

### 7.4. Recovery và return to steady state

Sau khi fault kết thúc, xác minh:

- Tài nguyên thử nghiệm đã được khôi phục hoặc quy tắc fault đã được gỡ.
- Healthy capacity trở lại mức mong muốn.
- Autoscaling không tiếp tục scale-out/scale-in ngoài dự kiến.
- Queue backlog giảm về mức bình thường.
- Cache được warm lại nếu cần.
- Database replication lag trở lại ngưỡng.
- Network retry và connection pool ổn định.
- Alert được resolve đúng cách, không bị xóa thủ công khi lỗi vẫn tồn tại.
- Không còn VM, disk, rule hoặc resource tạm gây phát sinh chi phí.

## 8. Đo RTO, RPO và thời gian phục hồi

RTO và RPO giúp chuyển mục tiêu phục hồi thành tiêu chí kiểm chứng.

- **RTO (Recovery Time Objective):** khoảng thời gian gián đoạn tối đa mà nghiệp vụ có thể chấp nhận trước khi dịch vụ được khôi phục.
- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể chấp nhận mất, thường biểu diễn bằng thời gian dữ liệu.

Ví dụ một dịch vụ đặt RTO là 15 phút và RPO là 5 phút. Khi thử nghiệm mất một zone, nhóm cần đo thời gian từ khi dịch vụ bị ảnh hưởng đến khi phục vụ trở lại, đồng thời xác định điểm dữ liệu mới nhất được phục hồi. Nếu dịch vụ hoạt động lại sau 7 phút nhưng mất 12 phút dữ liệu, RTO đạt còn RPO không đạt.

Các mốc nên ghi:

| Mốc | Ý nghĩa |
| --- | --- |
| T0 | Bắt đầu fault injection |
| T1 | Monitoring phát hiện |
| T2 | Thành phần lỗi bị cô lập khỏi traffic |
| T3 | Failover hoặc replacement bắt đầu |
| T4 | Dịch vụ đạt lại SLO |
| T5 | Dữ liệu được xác minh nhất quán |
| T6 | Toàn hệ thống trở về steady state |

Tùy mục tiêu, recovery time có thể được đo từ T0 đến T4 hoặc T6. Cần ghi rõ định nghĩa trong báo cáo để các lần thử có thể so sánh.

## 9. Các chỉ số và tín hiệu cần theo dõi

| Nhóm | Chỉ số |
| --- | --- |
| User experience | Availability, success rate, p95/p99 latency, error rate |
| Compute | Healthy instance count, CPU, memory, restart/replacement count |
| Autoscaling | Desired vs actual capacity, launch time, scale event và cooldown |
| Network | RTT, packet loss, retransmission, connection error, DNS latency |
| Storage | IOPS, throughput, latency, queue depth, I/O error |
| Database | Connection count, query latency, replication lag, failover state |
| Messaging | Queue depth, consumer lag, redelivery và duplicate count |
| Recovery | Detection time, isolation time, failover time, RTO và RPO |
| Operations | Alert delivery, runbook execution, manual intervention và cleanup |

Đặt dashboard theo timeline thử nghiệm và đánh dấu thời điểm inject/stop fault. Điều này giúp đối chiếu metric với sự kiện thay vì chỉ xem biểu đồ tổng hợp.

## 10. Ví dụ thực hành: mất một VM trong nhóm API

Một API stateless chạy trên managed instance group có 4 VM, trải qua 2 zone và nhận traffic qua load balancer. Dịch vụ có health endpoint, autoscaling và logging tập trung.

### 10.1. Giả thuyết

Khi một VM bị dừng, load balancer sẽ loại VM đó khỏi backend, ba VM còn lại tiếp tục phục vụ tải thử nghiệm, group tạo một VM thay thế và healthy capacity trở lại 4 trong vòng 5 phút. Tỷ lệ lỗi không vượt ngưỡng thử nghiệm; dữ liệu giao dịch không bị mất hoặc nhân đôi.

### 10.2. Pre-check

1. Chọn một VM thử nghiệm từ group, xác minh instance ID và zone.
2. Xác nhận không có tác vụ stateful hoặc session duy nhất trên VM đó.
3. Xác nhận ba VM còn lại đủ capacity cho tải thử nghiệm.
4. Kiểm tra load balancer health, autoscaling, quota và subnet IP.
5. Kiểm tra alert, dashboard và log đang hoạt động.
6. Ghi baseline trong ít nhất một khoảng đo ổn định.
7. Chuẩn bị thao tác dừng thử nghiệm và rollback nếu có dấu hiệu bất thường.

### 10.3. Thực hiện và quan sát

1. Ghi timestamp bắt đầu.
2. Dừng đúng VM đã chọn bằng thao tác fault injection được phê duyệt.
3. Theo dõi health check và thời điểm backend bị loại khỏi traffic.
4. Theo dõi success rate, latency, healthy backend count và request distribution.
5. Theo dõi managed group tạo VM mới và bootstrap.
6. Xác minh instance mới dùng đúng template revision, image, identity và network.
7. Đợi readiness đạt rồi xác nhận load balancer đưa instance mới vào backend.
8. Ghi thời điểm healthy capacity trở lại 4.

### 10.4. Xác minh sau thử nghiệm

- So sánh số transaction được xác nhận với dữ liệu nguồn.
- Kiểm tra request retry và duplicate.
- Xác minh VM cũ đã ở trạng thái dự kiến và không còn nhận traffic.
- Xác nhận không còn fault rule hoặc tài nguyên thử nghiệm.
- Đo RTO và thời gian replacement.
- Kiểm tra group không tạo thêm VM ngoài desired capacity.
- Ghi các điểm khác với giả thuyết.

Nếu instance thay thế không trở thành healthy do startup script thiếu quyền đọc secret, thử nghiệm đã phát hiện một điểm yếu thực tế: autohealing có thể tạo máy nhưng không khôi phục được capacity phục vụ. Hành động tiếp theo là sửa identity/bootstrap, kiểm thử image rồi chạy lại thử nghiệm.

## 11. Ví dụ thực hành: dependency database tạm thời unavailable

Một dịch vụ compute gọi database qua connection pool. Nhóm muốn xác minh ứng dụng phản ứng đúng khi database tạm thời không nhận kết nối.

Giả thuyết:

- Request có timeout hữu hạn.
- Retry dùng exponential backoff và jitter.
- Circuit breaker mở khi lỗi vượt ngưỡng.
- API trả degraded response hoặc lỗi có kiểm soát.
- Khi database trở lại, connection pool tạo kết nối mới và traffic phục hồi.
- Không mất transaction đã xác nhận và không tạo duplicate khi client retry.

Thử nghiệm trong môi trường test:

1. Tạo dataset tổng hợp và ghi lại record count/checksum.
2. Đo baseline query latency và connection pool.
3. Chặn endpoint database thử nghiệm trong khoảng thời gian giới hạn.
4. Theo dõi thread pool, timeout, retry, circuit breaker và API latency.
5. Khôi phục đường kết nối.
6. Theo dõi connection pool và query latency trở lại bình thường.
7. Đối chiếu dữ liệu và request ID để phát hiện mất hoặc nhân đôi.

Nếu request retry làm số kết nối và query tăng mạnh sau khi database trở lại, cần thêm retry budget, jitter và giới hạn concurrency để tránh recovery storm.

## 12. Công cụ và nền tảng hỗ trợ

Có thể dùng dịch vụ cloud, công cụ mã nguồn mở hoặc nền tảng chaos engineering chuyên dụng. Lựa chọn phụ thuộc môi trường, mức độ kiểm soát cần thiết và loại lỗi muốn mô phỏng.

| Công cụ/nhóm công cụ | Phạm vi thường dùng |
| --- | --- |
| AWS Fault Injection Service (FIS) | Thử nghiệm fault injection trên tài nguyên AWS được hỗ trợ, với experiment template và stop condition |
| Azure Chaos Studio | Thí nghiệm lỗi trên tài nguyên Azure và môi trường được hỗ trợ |
| Chaos Mesh | Chaos experiment cho workload Kubernetes như pod, network, stress và một số loại lỗi khác |
| Litmus | Chaos engineering cho Kubernetes, experiment và workflow theo chính sách |
| Gremlin hoặc nền tảng tương tự | Mô phỏng lỗi compute, network và dependency với kiểm soát tập trung |
| tc/netem, stress-ng | Công cụ cấp hệ điều hành để mô phỏng network impairment và resource pressure trong môi trường thử nghiệm |

Khả năng hỗ trợ, tên action, giới hạn và vùng khả dụng của dịch vụ cloud thay đổi theo thời gian. Trước khi triển khai, kiểm tra tài liệu phiên bản hiện hành, quyền IAM/RBAC, loại tài nguyên được hỗ trợ và điều kiện cleanup.

### 12.1. Tiêu chí chọn công cụ

- Hỗ trợ đúng loại VM, container, network và storage đang dùng.
- Có target selector rõ ràng và kiểm tra phạm vi trước khi chạy.
- Có thời lượng fault, stop condition và audit trail.
- Có thể giới hạn blast radius và quyền của operator.
- Có tích hợp monitoring/alerting.
- Có khả năng cleanup tự động hoặc rollback đáng tin cậy.
- Có thể lưu experiment definition và kết quả để chạy lại.
- Không yêu cầu quyền rộng hơn mức cần thiết.

## 13. Game day và diễn tập vận hành

Game day kiểm tra cả công nghệ lẫn con người. Một hệ thống có thể tự failover nhưng đội vận hành không biết alert nào quan trọng, không tìm được runbook hoặc không biết ai có quyền thực hiện recovery.

Một game day có thể gồm:

1. Chọn một kịch bản như mất một VM, lỗi database hoặc cô lập một zone.
2. Chỉ định incident commander, operator, observer và người ghi biên bản.
3. Công bố phạm vi, thời gian và điều kiện dừng.
4. Tạo fault theo kịch bản.
5. Để đội trực phát hiện và xử lý theo runbook.
6. Ghi lại quyết định, thời gian và thông tin còn thiếu.
7. Dừng fault và xác minh recovery.
8. Họp rút kinh nghiệm và giao hành động cải thiện.

Observer nên ghi lại khoảng thời gian đội vận hành mất để tìm dashboard, xác định owner, xin quyền và tìm đúng runbook. Những khoảng trễ này có thể làm RTO thực tế dài hơn nhiều so với thời gian failover tự động.

## 14. Khi nào cần dừng thử nghiệm?

Dừng ngay khi:

- Error rate, latency hoặc availability vượt abort threshold.
- Healthy capacity xuống dưới mức an toàn.
- Ảnh hưởng lan sang tenant, dịch vụ hoặc nhóm người dùng ngoài phạm vi.
- Dữ liệu có dấu hiệu mất, sai hoặc bị nhân đôi ngoài mức chấp nhận.
- Backup, replica hoặc dependency quan trọng gặp lỗi đồng thời.
- Monitoring/alerting không còn cung cấp tín hiệu tin cậy.
- Target selector không đúng hoặc không thể xác định phạm vi tài nguyên.
- Thao tác rollback không hoạt động như đã kiểm thử.
- Người chịu trách nhiệm quyết định kết thúc thử nghiệm.

Sau khi abort, ưu tiên gỡ fault, khôi phục traffic và dữ liệu. Giữ lại log và timeline để điều tra; không tiếp tục inject fault chỉ để hoàn thành kịch bản.

## 15. Phân tích kết quả và chuyển thành cải tiến

Kết quả một thử nghiệm có thể thuộc một trong ba nhóm:

- **Giả thuyết được xác nhận:** hệ thống phản ứng và phục hồi trong các ngưỡng đã đặt.
- **Giả thuyết bị bác bỏ:** hệ thống không đạt một hoặc nhiều tiêu chí.
- **Kết quả chưa đủ bằng chứng:** metric, log hoặc target không đủ để kết luận.

Khi giả thuyết thất bại, tìm nguyên nhân ở đúng lớp:

- Thiết kế redundancy chưa đủ?
- Health check không phát hiện đúng?
- Timeout/retry tạo hiệu ứng khuếch đại?
- Autoscaler thiếu quota hoặc capacity?
- Bootstrap, IAM hoặc secret dependency bị lỗi?
- Replication lag vượt RPO?
- Runbook hoặc quyền vận hành gây chậm recovery?
- Monitoring không phát hiện hoặc alert sai?

Mỗi finding nên có owner, mức ưu tiên, deadline, bằng chứng và tiêu chí đóng. Sau khi sửa, chạy lại cùng thử nghiệm để xác minh cải tiến.

## 16. Mẫu báo cáo thử nghiệm

Một báo cáo ngắn có thể dùng cấu trúc:

| Trường | Nội dung cần ghi |
| --- | --- |
| Experiment ID | Mã định danh và phiên bản kịch bản |
| Mục tiêu | Failure mode và giả thuyết |
| Environment | Account/project, region, zone và workload |
| Target | Resource ID, tag/selector và blast radius |
| Preconditions | Baseline, backup, capacity và guardrails |
| Fault | Loại lỗi, thời điểm bắt đầu/kết thúc, cường độ |
| Observations | Metric, log, trace, alert và hành động tự động |
| Recovery | Detection, isolation, failover, RTO/RPO và data integrity |
| Outcome | Pass, fail hoặc inconclusive |
| Findings | Khoảng cách giữa kỳ vọng và thực tế |
| Actions | Owner, priority, due date và retest plan |

Không chỉ ghi “thử nghiệm thành công”. Cần đính kèm timeline, dashboard hoặc query có thể tái hiện kết quả.

## 17. Những sai lầm thường gặp

- Tạo lỗi mà không có giả thuyết và steady-state metrics.
- Thử nhiều failure mode cùng lúc khiến không xác định được nguyên nhân.
- Chọn target bằng tag không được xác minh.
- Bắt đầu ở production khi chưa thử trong môi trường cô lập.
- Không có abort condition hoặc người có quyền dừng thử nghiệm.
- Chỉ theo dõi CPU mà bỏ qua error rate, latency và data integrity.
- Coi VM được thay thế là bằng chứng dịch vụ đã phục hồi.
- Bỏ qua retry storm, queue backlog và recovery storm.
- Không kiểm tra RTO/RPO bằng dữ liệu thực tế.
- Không xác minh cleanup nên fault rule hoặc resource tạm còn tồn tại.
- Không ghi finding thành action có owner và deadline.
- Không chạy lại thử nghiệm sau khi sửa.
- Coi backup thành công là đủ mà không thử restore.
- Mô phỏng zone failure bằng cách gây lỗi tài nguyên dùng chung ngoài phạm vi.

## 18. Checklist trước, trong và sau thử nghiệm

**Trước thử nghiệm**

- [ ] Có giả thuyết, mục tiêu và tiêu chí pass/fail.
- [ ] Đã xác định steady state và SLO liên quan.
- [ ] Đã chọn target cụ thể và giới hạn blast radius.
- [ ] Đã xác minh backup/snapshot và dữ liệu thử nghiệm.
- [ ] Có guardrails, abort condition và rollback.
- [ ] Có owner, observer, kênh liên lạc và thời gian thử.
- [ ] Monitoring, alerting và logging đang hoạt động.
- [ ] Capacity, quota và dependency dự phòng đủ.

**Trong thử nghiệm**

- [ ] Ghi timestamp khi bắt đầu fault.
- [ ] Theo dõi user-facing metric và tài nguyên nền.
- [ ] Xác minh alert và hành động tự động.
- [ ] Theo dõi data integrity, queue và replication lag.
- [ ] Dừng ngay khi vượt abort threshold.
- [ ] Ghi lại mọi thao tác thủ công.

**Sau thử nghiệm**

- [ ] Gỡ fault và cleanup tài nguyên tạm.
- [ ] Xác minh healthy capacity và steady state.
- [ ] Kiểm tra transaction, record, message và replica.
- [ ] Đo detection time, recovery time, RTO và RPO.
- [ ] Đối chiếu kết quả với giả thuyết.
- [ ] Giao owner/deadline cho từng finding.
- [ ] Lập lịch retest sau khi khắc phục.

## 19. Quy trình xây dựng chương trình thử nghiệm liên tục

1. **Lập danh mục rủi ro:** liệt kê VM, group, zone, storage, network và dependency quan trọng.
2. **Ưu tiên failure mode:** chọn lỗi có xác suất hoặc tác động cao và chưa có bằng chứng phục hồi.
3. **Chuẩn hóa giả thuyết:** dùng SLO, RTO, RPO và tiêu chí dữ liệu.
4. **Tạo experiment catalog:** lưu kịch bản, target, quyền, guardrail, cleanup và owner.
5. **Chạy trong môi trường cô lập:** kiểm tra kỹ thuật và chất lượng monitoring.
6. **Mở rộng có kiểm soát:** tăng blast radius theo từng giai đoạn và quy trình phê duyệt.
7. **Diễn tập game day:** kiểm tra phối hợp, runbook, alert và quyền vận hành.
8. **Theo dõi hành động:** quản lý finding như công việc kỹ thuật có owner và deadline.
9. **Retest:** xác nhận lỗi đã được khắc phục và recovery đạt mục tiêu.
10. **Cập nhật kiến trúc:** đưa kết quả vào template, autoscaling, health check, backup và DR plan.

## 20. Nguyên tắc cần ghi nhớ

1. Thử nghiệm lỗi phải bắt đầu bằng giả thuyết và trạng thái bình thường có thể đo.
2. Fault injection tạo lỗi cụ thể; chaos engineering kiểm chứng hành vi toàn hệ thống trong phạm vi có kiểm soát.
3. Giới hạn blast radius, thời gian, target và có điều kiện abort trước khi chạy.
4. Bắt đầu trong môi trường cô lập rồi tăng phạm vi theo bằng chứng và quy trình phê duyệt.
5. Kiểm tra nhiều failure mode: VM, CPU, memory, network, storage, dependency và zone.
6. Xác minh detection, isolation, failover, data integrity và recovery về steady state.
7. Đo RTO/RPO bằng timestamp và dữ liệu, không chỉ dựa vào trạng thái tài nguyên.
8. Kiểm tra retry, queue, replica và dependency để tránh recovery storm.
9. Mọi finding cần owner, deadline và tiêu chí retest.
10. Thử nghiệm chỉ tạo giá trị khi kết quả được dùng để cải thiện kiến trúc và runbook.

Thử nghiệm lỗi có kiểm soát giúp chuyển khả năng chịu lỗi từ một giả định thiết kế thành năng lực đã được kiểm chứng. Khi mỗi experiment có giả thuyết rõ ràng, phạm vi an toàn, tín hiệu đo lường và bước xác minh dữ liệu sau phục hồi, đội vận hành hiểu được hệ thống phản ứng ra sao trước sự cố và biết chính xác cần cải thiện điều gì để đạt mục tiêu sẵn sàng cao.
