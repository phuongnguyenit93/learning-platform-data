# Thiết kế multi-region và lựa chọn active-active hoặc active-passive

## Mục tiêu bài học

Trong hệ sinh thái **Microsoft Azure**, một ứng dụng có thể được triển khai qua nhiều **region** để tiếp tục phục vụ khi một vùng gặp sự cố, đưa người dùng tới điểm phục vụ gần hơn và đáp ứng yêu cầu lưu trữ dữ liệu. Tuy nhiên, việc tạo tài nguyên ở hai region chưa tự động tạo thành kiến trúc khôi phục thảm họa: đường đi của yêu cầu, nơi ghi dữ liệu, quá trình nhân bản, quyền truy cập, năng lực dự phòng và thao tác chuyển vùng đều phải được thiết kế cùng nhau.

Sau bài học này, bạn có thể:

- Phân biệt **Availability Zone**, **region**, **region pair**, dự phòng dữ liệu và **disaster recovery (DR)**.
- Đặt mục tiêu **RTO**, **RPO**, SLI/SLO và dùng chúng làm cơ sở quyết định kiến trúc.
- So sánh **active-active**, **active-passive** (hot/warm/cold standby) và mô hình lai **nhiều vùng đọc, một vùng ghi**.
- Thiết kế định tuyến bằng **Azure Front Door** hoặc **Azure Traffic Manager**, đồng thời điều phối ứng dụng và dữ liệu đúng thứ tự khi failover.
- Xây dựng runbook, giám sát, diễn tập và kế hoạch failback có thể kiểm chứng.

Bài học thuộc chương **Độ tin cậy và khôi phục thảm họa** của module **CLOUD_PROVIDERS_AZURE**, với phạm vi từ subscription, resource group, Entra ID, mạng và compute đến lưu trữ, dữ liệu, giám sát, bảo mật và chi phí. Ví dụ sử dụng dịch vụ Azure; mọi mục tiêu thời gian, dung lượng và chi phí nêu dưới đây đều là **giả định thiết kế**, không phải cam kết SLA của Azure.

## 1. Vì sao phải thiết kế theo nhiều region?

Một region là khu vực địa lý có một hoặc nhiều trung tâm dữ liệu Azure. Trong những region hỗ trợ **Availability Zone (AZ)**, các zone tạo các miền lỗi riêng trong cùng region, giúp giảm tác động của sự cố ở một trung tâm dữ liệu hoặc một phần hạ tầng vùng. **Multi-region** trải ứng dụng và/hoặc dữ liệu ra ít nhất hai region, từ đó xử lý lớp sự cố lớn hơn như gián đoạn toàn bộ region hoặc yêu cầu phục vụ ở nhiều địa bàn.

| Khái niệm | Phạm vi bảo vệ chính | Điều không nên suy diễn |
| --- | --- | --- |
| Nhiều instance trong một zone | Lỗi tiến trình, máy chủ hoặc instance | Không bảo vệ khỏi lỗi toàn zone/region. |
| Zone-redundant trong một region | Lỗi một zone, nếu dịch vụ và cấu hình hỗ trợ | Không đồng nghĩa với dự phòng ở region khác. |
| Multi-region | Sự cố rộng ở region, có thể giảm độ trễ liên vùng | Chỉ có tác dụng khi traffic, ứng dụng, dữ liệu và phụ thuộc cùng sẵn sàng. |
| Geo-replication | Tạo bản sao dữ liệu ở nơi khác theo cơ chế dịch vụ | Không mặc nhiên cho phép ghi ở cả hai region hoặc bảo đảm RPO bằng 0. |
| Backup/restore | Khôi phục dữ liệu bị xóa, mã hóa, ghi sai hoặc hỏng logic | Không tự động tạo dịch vụ luôn sẵn sàng hay chuyển traffic nhanh. |

**Region pair** là quan hệ ghép cặp vùng được Azure định nghĩa cho một số mục đích vận hành và khôi phục. Không phải mọi dịch vụ hay tính năng đều bắt buộc dùng region pair; việc chọn cặp vùng phải dựa vào **dịch vụ có sẵn, ranh giới địa lý dữ liệu, độ trễ, năng lực, giá và kiểu nhân bản**. Region pair cũng không bảo đảm hai vùng sẽ không cùng gặp sự cố.

Ví dụ, một API chỉ có hai Azure App Service ở hai region nhưng cùng truy cập một cơ sở dữ liệu không có phương án khôi phục khi region chứa database mất kết nối thì **chưa có DR đầu cuối**. Tương tự, có bản sao database nhưng chưa có cơ chế chuyển vùng và cập nhật kết nối cũng chưa đạt mục tiêu RTO.

### 1.1. RTO, RPO và thước đo vận hành

- **RTO (Recovery Time Objective):** thời gian tối đa chấp nhận được để khôi phục dịch vụ sau sự cố đủ nghiêm trọng. Ví dụ RTO 30 phút nghĩa là quy trình chuyển vùng phải được thiết kế và diễn tập để đáp ứng mốc đó.
- **RPO (Recovery Point Objective):** khoảng thời gian dữ liệu đã ghi thành công có thể bị mất tối đa khi phục hồi. RPO 5 phút đòi hỏi cơ chế nhân bản, quan sát độ trễ và quy trình failover phù hợp.
- **SLI:** chỉ số đo trải nghiệm thực tế, ví dụ tỷ lệ yêu cầu thành công, độ trễ p95/p99 và tính đúng đắn của giao dịch.
- **SLO:** mức đích cho SLI trong cửa sổ thời gian; chẳng hạn 99,95% yêu cầu thành công trong 30 ngày. Mức này tương ứng **21,6 phút ngân sách lỗi** nếu coi mọi phút có trọng số như nhau; đo theo yêu cầu thực tế có thể cho kết quả khác.

RTO đo **thời gian khôi phục**, RPO đo **mức mất dữ liệu**. Chuyển traffic sang region còn sống trong một phút không đồng nghĩa với RTO một phút nếu ứng dụng vẫn không thể ghi hoặc trả dữ liệu nhất quán. Nhân bản bất đồng bộ (asynchronous replication) có thể mất các giao dịch đã xác nhận ở region chính nhưng chưa đến region phụ khi phải cưỡng bức failover.

Trước khi chọn mô hình, hãy tách yêu cầu theo nghiệp vụ: giao dịch thanh toán có thể cần RPO rất thấp và tránh ghi hai nơi; trang danh mục sản phẩm có thể chịu độ trễ đồng bộ vài phút nhưng cần phục vụ toàn cầu. Một hệ thống thường dùng **nhiều mô hình cho các nhóm dữ liệu khác nhau**.

## 2. Ba phương án vận hành

### 2.1. Active-passive: một region phục vụ chính

Trong **active-passive**, region A xử lý traffic chính; region B giữ ứng dụng và dữ liệu dự phòng theo mức sẵn sàng đã chọn. Khi cần, hệ thống chuyển vai trò sang B. Thông thường, ứng dụng chỉ có **một writer hợp lệ** cho dữ liệu giao dịch tại mỗi thời điểm.

| Kiểu standby | Trạng thái vùng dự phòng | Ưu điểm | Chi phí và đánh đổi |
| --- | --- | --- | --- |
| **Hot** | Ứng dụng, mạng, quyền và năng lực đã chạy; dữ liệu nhân bản liên tục | Có thể chuyển nhanh sau khi xác nhận phụ thuộc | Tốn tài nguyên chạy song song; vẫn phải xử lý promote database. |
| **Warm** | Cấu hình và dữ liệu sẵn; compute có thể chạy quy mô nhỏ rồi scale khi cần | Cân bằng chi phí và RTO | Cần thời gian mở rộng, làm nóng cache, kiểm tra quota. |
| **Cold** | Chủ yếu có template, backup, cấu hình và quy trình dựng lại | Chi phí thường thấp | RTO dài, phụ thuộc thời gian cấp phát và restore; cần diễn tập kỹ. |

**Phù hợp:** hệ thống giao dịch có ràng buộc một nguồn ghi, đội vận hành cần quy trình dễ kiểm soát, hoặc RTO cho phép thời gian promote và tăng năng lực vùng dự phòng. Với warm/cold standby, đừng nhầm **thời gian đổi tuyến của Front Door** với thời gian hệ thống sẵn sàng phục vụ.

### 2.2. Active-active: hai hoặc nhiều region cùng phục vụ

Trong **active-active**, các region đều đang xử lý traffic người dùng. Lợi ích có thể là giảm độ trễ địa lý, sử dụng công suất của cả hai vùng và giảm thời gian chuyển traffic khi một vùng lỗi. Khi region A ngừng phục vụ, region B cần **đủ dung lượng còn trống** để tiếp nhận phần tải chuyển sang.

Điểm khó nhất thường nằm ở **dữ liệu và trạng thái**:

- **Active-active đọc, single-writer ghi:** cả hai region xử lý request đọc, nhưng các thao tác ghi được đưa về một writer. Dễ bảo vệ tính nhất quán hơn nhưng đường ghi phụ thuộc vào region writer.
- **Active-active multi-writer:** hai region cùng ghi vào dữ liệu logic; cần dịch vụ hỗ trợ, chiến lược giải quyết xung đột, khóa định danh, idempotency và chính sách nhất quán rõ ràng.

Ví dụ, Azure Cosmos DB có khả năng cấu hình nhiều region ghi, song ứng dụng vẫn phải hiểu mức consistency và cách giải quyết conflict. Không nên suy ra rằng mọi Azure SQL database, Storage account hoặc hàng đợi đều có thể mở cùng lúc hai writer độc lập và tự hòa giải.

### 2.3. So sánh cho quyết định kiến trúc

| Tiêu chí | Active-passive | Active-active |
| --- | --- | --- |
| Lưu lượng bình thường | Chủ yếu tại một region | Phân bổ qua nhiều region |
| Độ trễ người dùng ở xa | Có thể cao hơn | Có thể thấp hơn nhờ xử lý tại vùng gần |
| Khôi phục khi app một vùng lỗi | Chuyển sang standby; warm/cold cần khởi động | Chuyển sang vùng đang hoạt động nếu còn năng lực |
| Ghi dữ liệu | Thường single-writer, dễ kiểm soát hơn | Single-writer từ nhiều vùng hoặc multi-writer phức tạp |
| Vận hành | Cần runbook promote, chuyển traffic, failback | Cần kiểm soát phân phối tải, đồng bộ, conflict và năng lực N-1 |
| Chi phí thường gặp | Thấp hơn với warm/cold; hot standby vẫn có chi phí lớn | Nhiều môi trường vận hành đầy đủ, cross-region transfer và quan sát phức tạp |
| Rủi ro trọng tâm | Promote dữ liệu chậm, standby thiếu năng lực | Split-brain, xung đột dữ liệu, lỗi chia sẻ phụ thuộc |

**Mô hình lai** thường là lựa chọn thực dụng: hai region active cho frontend hoặc đọc nội dung, nhưng chỉ một region ghi dữ liệu giao dịch. Đó vẫn là **active-active ở tầng ứng dụng**, không nên mô tả thành multi-writer ở tầng dữ liệu.

## 3. Quy trình chọn active-active hay active-passive

Đừng bắt đầu bằng lựa chọn dịch vụ. Hãy trả lời lần lượt:

1. **Sự cố cần chịu đựng là gì?** Mất một instance, AZ, toàn region, mất kết nối giữa hai region, hỏng dữ liệu logic hay mất nhà cung cấp dịch vụ ngoài?
2. **RTO/RPO theo từng luồng nghiệp vụ?** Phân biệt tìm kiếm, xem trang, đặt hàng, thanh toán, cập nhật kho và xử lý sự kiện.
3. **Có được phép mất hoặc trùng giao dịch không?** Nếu không, hãy thiết kế idempotency, cơ chế xác nhận, fencing của writer cũ và hòa giải sau failover.
4. **Dịch vụ dữ liệu hỗ trợ kiểu nhân bản nào?** Đọc bản sao, geo-failover, multi-write, consistency, độ trễ nhân bản và giới hạn theo SKU/region.
5. **Nơi đặt dữ liệu có bị giới hạn không?** Xác định data residency, loại dữ liệu, khóa mã hóa, đường truyền riêng và quy định nội bộ.
6. **Region còn lại có chịu được 100% tải không?** Thử với traffic peak, giới hạn quota, kết nối database, backend pool, cache và tốc độ scale.
7. **Ai và cơ chế nào quyết định failover/failback?** Tự động ở đâu, thao tác phê duyệt ở đâu, cần tín hiệu kiểm tra gì để mở lại ghi?

Một cách chọn nhanh:

| Tình huống nghiệp vụ | Phương án khởi đầu nên đánh giá | Điều cần chứng minh |
| --- | --- | --- |
| API nghiệp vụ có giao dịch quan trọng, một nguồn dữ liệu quan hệ | Active-passive hot hoặc warm với writer duy nhất | RTO của promote và chuyển tuyến; RPO khi nhân bản bất đồng bộ |
| Website đọc nhiều, người dùng phân bố toàn cầu | Active-active frontend/read, single-writer backend | Latency thực tế, cache invalidation và đường ghi |
| Dữ liệu phân tán có thể xử lý conflict theo khóa/tài khoản | Active-active multi-writer, nếu nền tảng hỗ trợ | Quy tắc merge, idempotency, consistency và phát hiện conflict |
| Hệ thống nội bộ chấp nhận khôi phục trong nhiều giờ | Active-passive warm/cold | Khả năng cấp phát, restore từ backup, quy trình kiểm thử |

> Quyết định nên được lưu thành **Architecture Decision Record (ADR)**: giả định tải, mục tiêu RTO/RPO, mô hình ghi dữ liệu, phương án failover, ràng buộc dữ liệu và tiêu chí đo thành công. Khi thay đổi một giả định, cần đánh giá lại kiến trúc.

## 4. Kiến trúc tham chiếu trên Azure

### 4.1. Active-passive với Azure Front Door và Azure SQL

Ví dụ API thương mại điện tử chạy trên **Azure App Service** tại hai region. **Azure Front Door Standard/Premium** tiếp nhận HTTPS toàn cầu, kiểm tra sức khỏe origin và ưu tiên region A. **Azure SQL Database failover group** cung cấp cơ chế nhân bản địa lý bất đồng bộ cùng endpoint logic cho kết nối đọc/ghi. Các tài nguyên giám sát, secret, cấu hình và quyền được chuẩn bị cho cả hai region.

~~~mermaid
flowchart TD
    U[Người dùng HTTPS] --> F[Azure Front Door + WAF]
    F -->|Ưu tiên 1, bình thường| A[App Service region A]
    F -.->|Ưu tiên 2, khi phù hợp| B[App Service region B]
    A --> L[SQL failover group: read-write listener]
    B --> L
    L --> P[(SQL primary region A)]
    P -.->|Nhân bản bất đồng bộ| S[(SQL geo-secondary region B)]
    M[Azure Monitor và cảnh báo] -.-> F
    M -.-> P
    M -.-> S
~~~

Đường nét đứt từ Front Door tới B diễn tả **ưu tiên route**, không có nghĩa B tự động trở thành writer của database. Nếu A mất cả ứng dụng và database, phải bảo đảm **failover group đã chuyển writer sang B**, ứng dụng B kết nối được endpoint hợp lệ, dữ liệu và các phụ thuộc chính đáp ứng kiểm tra trước khi nhận traffic nghiệp vụ.

Một ví dụ **ý định cấu hình** origin group (YAML dưới đây là mô hình logic để thảo luận, **không phải manifest có thể deploy trực tiếp**):

~~~yaml
frontDoor:
  mode: priority-routing
  probe:
    protocol: HTTPS
    method: GET
    path: /health/traffic-ready
  origins:
    - name: api-region-a
      priority: 1
      enabled: true
    - name: api-region-b
      priority: 2
      enabled: true
database:
  writeEndpoint: <sql-failover-group-read-write-listener>
  writesAllowed: single-primary-only
~~~

Trong Azure Front Door, **priority** dùng cho chuyển giữa nhóm origin ưu tiên; **weight** mới là công cụ phân bổ tỷ trọng giữa các origin cùng ưu tiên (theo cấu hình hỗ trợ). Probe app phải phản ánh khả năng phục vụ thực sự, đặc biệt là đường đọc/ghi dữ liệu. Không quảng bá standby là khỏe chỉ vì process còn chạy trong khi toàn bộ thao tác nghiệp vụ đều thất bại.

### 4.2. Active-active ở tầng ứng dụng

~~~mermaid
flowchart TD
    C[Người dùng toàn cầu] --> FD[Azure Front Door + WAF]
    FD -->|Theo độ trễ, sức khỏe, cấu hình| RA[API region A]
    FD -->|Theo độ trễ, sức khỏe, cấu hình| RB[API region B]
    RA --> DA[(Dữ liệu và cache vùng A)]
    RB --> DB[(Dữ liệu và cache vùng B)]
    DA <-->|Cơ chế nhân bản của dịch vụ dữ liệu| DB
    RA --> Q[Đường ghi/điều phối nhất quán]
    RB --> Q
~~~

Sơ đồ cố ý tách **đường ghi/điều phối nhất quán** khỏi hai bản sao dữ liệu. Đường này có thể là một writer duy nhất hoặc mô hình multi-writer được dịch vụ hỗ trợ. Trước khi chọn, phải trả lời rõ: giao dịch có thể ghi ở vùng nào, độ trễ nhìn thấy dữ liệu vừa ghi, cách xử lý conflict và điều gì xảy ra khi hai region mất kết nối với nhau.

### 4.3. Chọn dịch vụ điều phối traffic

| Dịch vụ | Cách hoạt động | Khi thích hợp | Lưu ý |
| --- | --- | --- | --- |
| **Azure Front Door Standard/Premium** | Global HTTP/HTTPS reverse proxy ở tầng 7; origin group, health probe, route, WAF, TLS | Web/API đa vùng, cần xử lý traffic gần người dùng và tự chuyển origin | Phải kiểm tra health, rules và backend readiness; không tự promote database. |
| **Azure Traffic Manager** | Định tuyến bằng câu trả lời DNS theo phương thức cấu hình và endpoint monitoring | Ứng dụng cần chính sách DNS đa vùng hoặc endpoint không đặt sau một global HTTP proxy | Resolver/client có thể cache DNS; thời gian chuyển không chỉ bằng thời gian phát hiện lỗi. |
| **Azure Application Gateway** | Load balancer tầng 7 trong phạm vi triển khai regional, hỗ trợ WAF theo SKU | Cân bằng và bảo vệ traffic vào từng region | Không phải giải pháp global multi-region độc lập. |
| **Azure Load Balancer** | Cân bằng tầng 4 cho phạm vi và SKU tương ứng | TCP/UDP, dịch vụ nội bộ hoặc regional | Không thay thế chiến lược dữ liệu hay global HTTP failover. |

Ưu tiên 1/2 hay định tuyến theo latency là **chính sách**; kết quả thực tế còn phụ thuộc health probe, cache, timeout, session đang mở và các kết nối tồn tại. Với API động cần xem kỹ cache policy của Front Door để không cache nhầm kết quả chứa dữ liệu cá nhân.

## 5. Dữ liệu quyết định giới hạn của mô hình

**Ứng dụng có thể stateless nhưng nghiệp vụ hiếm khi stateless.** Cần kiểm kê database, blob, queue, cache, khóa, secret, file tạm, session, cron job và callback bên thứ ba. Tầng nào chỉ có bản sao tại region A sẽ trở thành single point of failure khi A mất.

| Thành phần Azure | Phương án cần đánh giá | Câu hỏi thiết kế |
| --- | --- | --- |
| **Azure SQL Database** | Failover group/geo-replication theo khả năng dịch vụ và tier; writer logic duy nhất | Độ trễ replica? Read-write listener? Khi forced failover có thể mất giao dịch nào? |
| **Azure Cosmos DB** | Phân phối nhiều region; cấu hình vùng đọc, vùng ghi và consistency | Có cho phép multi-write? Conflict resolution, session consistency và failover hoạt động ra sao? |
| **Azure Storage** | ZRS cho zone, GRS/GZRS hoặc biến thể có read-access cho geo-redundancy | Đọc secondary có phù hợp không? Khi account failover, dữ liệu chưa nhân bản sẽ thế nào? |
| **Azure Service Bus/Event Hubs** | Xem chính xác tính năng geo-recovery/geo-replication của tier và dịch vụ | Tính năng có nhân bản **message/event payload** hay chỉ metadata cấu hình? Xử lý backlog thế nào? |
| **Azure Cache for Redis/giải pháp cache** | Cache độc lập mỗi region, warm-up và cơ chế invalidation | Có thể tái tạo cache? Tránh coi cache là nguồn dữ liệu chính. |
| **Azure Key Vault** | Quyền và secret cần sẵn sàng tại đường chạy của vùng dự phòng | Phụ thuộc region, private endpoint, managed identity và vòng đời secret có cản trở failover không? |

### 5.1. Single-writer và phòng tránh split-brain

**Split-brain** xảy ra khi hai phía đều tin mình có quyền ghi. Ví dụ vùng A bị mất kết nối giám sát nhưng vẫn hoạt động với một nhóm client; đội vận hành promote vùng B, trong khi A tiếp tục nhận đơn hàng. Khi kết nối phục hồi, hai lịch sử giao dịch có thể mâu thuẫn.

Để giảm rủi ro:

1. Quy định **một nguồn quyết định vai trò writer** (nền tảng dữ liệu hoặc quy trình điều phối được kiểm soát).
2. Khi promote, **fence** writer cũ: chặn đường ghi/định tuyến hoặc thu hồi quyền ghi phù hợp với công nghệ; không chỉ sửa DNS.
3. Cho ứng dụng ghi qua **endpoint writer logic**; không hardcode địa chỉ primary của một region.
4. Dùng **idempotency key** cho các lệnh có thể retry (đặt hàng, tạo thanh toán, phát sự kiện) và unique constraint ở nơi lưu trạng thái chính.
5. Khi failback, xác minh chiều nhân bản mới, backlog và tính toàn vẹn trước khi trả quyền writer cho vùng cũ.

Nếu hệ thống đòi **RPO = 0 đối với dữ liệu giao dịch**, nhân bản địa lý bất đồng bộ đơn thuần thường không chứng minh được mục tiêu đó trong mọi kịch bản. Cần thiết kế tính nhất quán và quyết định nghiệp vụ phù hợp, có thể chấp nhận **tạm ngừng ghi** khi chưa có đủ điều kiện an toàn thay vì mở ghi ở cả hai region.

### 5.2. Phiên làm việc, giao dịch, hàng đợi và tác vụ nền

- Đưa session/identity về cơ chế có thể xác minh tại cả hai region (token, session store có kế hoạch DR). Không dựa vào bộ nhớ của một instance để duy trì phiên quan trọng.
- Khi retry do chuyển region, một HTTP request có thể đã được xử lý tại A dù client nhận timeout. API cần **idempotent** hoặc có cơ chế truy vấn lại trạng thái giao dịch.
- Với job theo lịch và consumer, bảo đảm chỉ một tác nhân thực thi công việc không được phép chạy trùng; cân nhắc distributed lease/leader election có điều kiện nhất quán phù hợp.
- Đối với queue/event, định nghĩa xử lý message đang bay, thứ tự, duplicate, dead-letter và backlog, dựa trên **khả năng nhân bản thực tế của từng dịch vụ/SKU**.
- Tách backup và cơ chế phục hồi dữ liệu logic khỏi replication. Lệnh xóa sai hoặc mã độc có thể được **nhân bản sang vùng dự phòng** rất nhanh.

### 5.3. Readiness cho việc chuyển traffic

Một endpoint **liveness** chỉ nói process hoạt động; **traffic readiness** phải nói instance hiện có thể phục vụ luồng yêu cầu dự kiến. Với ứng dụng bắt buộc phải ghi, readiness tối thiểu cần kiểm tra kết nối tới **write endpoint** của database và khả năng truy cập chế độ read-write. Bên dưới là ví dụ ASP.NET Core tối giản với SQL Database (cần package **Microsoft.Data.SqlClient**):

~~~csharp
using Microsoft.AspNetCore.Diagnostics.HealthChecks;
using Microsoft.Data.SqlClient;
using Microsoft.Extensions.Diagnostics.HealthChecks;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddHealthChecks()
    .AddCheck<WritableSqlCheck>("sql-writer");

var app = builder.Build();
app.MapGet("/health/live", () => Results.Ok("alive"));
app.MapHealthChecks("/health/traffic-ready", new HealthCheckOptions
{
    Predicate = _ => true
});
app.Run();

sealed class WritableSqlCheck : IHealthCheck
{
    private readonly IConfiguration _config;
    public WritableSqlCheck(IConfiguration config) => _config = config;

    public async Task<HealthCheckResult> CheckHealthAsync(
        HealthCheckContext context,
        CancellationToken cancellationToken = default)
    {
        try
        {
            var cs = _config.GetConnectionString("ApplicationDb");
            if (string.IsNullOrWhiteSpace(cs))
                return HealthCheckResult.Unhealthy("Missing DB connection");

            await using var connection = new SqlConnection(cs);
            await connection.OpenAsync(cancellationToken);
            await using var cmd = connection.CreateCommand();
            cmd.CommandText =
                "SELECT CAST(DATABASEPROPERTYEX(DB_NAME(), 'Updateability') AS varchar(20))";
            var mode = await cmd.ExecuteScalarAsync(cancellationToken) as string;
            return mode == "READ_WRITE"
                ? HealthCheckResult.Healthy()
                : HealthCheckResult.Unhealthy("SQL is not writable");
        }
        catch (Exception ex)
        {
            return HealthCheckResult.Unhealthy("SQL writer unavailable", ex);
        }
    }
}
~~~

Trong cấu hình vận hành, **ApplicationDb** phải dùng kết nối bảo mật đến writer endpoint, xác thực bằng **Microsoft Entra/managed identity** nếu thiết kế hỗ trợ, tránh đặt mật khẩu trong mã nguồn. Health check cần timeout ngắn, connection pooling, ngưỡng ổn định và giới hạn tần suất. Đoạn mã chỉ minh họa kiểm tra đường SQL; **READ_WRITE không chứng minh toàn bộ nghiệp vụ đã sẵn sàng**. Hãy bổ sung kiểm tra các phụ thuộc trọng yếu, nhưng tránh để lỗi dịch vụ không thiết yếu gây failover dây chuyền.

## 6. Ví dụ thiết kế: API đặt hàng hai region

Giả định một hệ thống đặt hàng có người dùng tại châu Á, cần:

| Ràng buộc | Giả định cho bài tập |
| --- | --- |
| Kịch bản phải chịu | Mất hoàn toàn region ứng dụng và database chính |
| RTO | Tối đa **30 phút** |
| RPO | Tối đa **5 phút** đối với đơn hàng đã xác nhận |
| Dữ liệu | Azure SQL, giao dịch đơn hàng, chỉ một writer |
| Lưu lượng đỉnh | 2.000 request/giây toàn hệ thống |
| Vùng dự phòng | Khác region, đủ dịch vụ/SKU, quota, tuân thủ lưu trú dữ liệu |

**Quyết định:** bắt đầu với **active-passive hot standby** cho API và single-writer SQL failover group. Front Door ưu tiên origin A, sẵn sàng chuyển đến origin B khi B khỏe; các dịch vụ nền và secret của B được chuẩn bị đầy đủ. Nếu phải triển khai nhanh với ngân sách thấp hơn có thể đánh giá warm standby, nhưng thời gian scale phải được tính vào RTO.

**Luồng bình thường:**

1. Front Door nhận HTTPS, WAF áp dụng chính sách và gửi request đến App Service A.
2. Ứng dụng dùng SQL failover group **read-write listener**, không dùng host database vùng A cố định.
3. SQL primary nhân bản bất đồng bộ sang geo-secondary. Giám sát **replication lag**, lỗi ứng dụng và độ trễ người dùng.
4. App Service B được giữ sẵn, có cấu hình, managed identity, quyền mạng, DNS, secret và đường kết nối writer. Probe không chỉ kiểm tra status process.
5. Một yêu cầu tạo đơn có idempotency key; giao dịch database và trạng thái gửi sự kiện sử dụng cơ chế an toàn với retry, chẳng hạn transactional outbox nếu phù hợp.

**Khi region A mất hoàn toàn:**

1. Cảnh báo từ synthetic probe ngoài region, Front Door và Azure Monitor được đối chiếu để tránh quyết định chỉ dựa trên một phép đo chập chờn.
2. Kích hoạt runbook, xác định phạm vi sự cố, độ trễ nhân bản và mức mất dữ liệu dự kiến. Nếu buộc phải forced failover, ghi nhận quyết định rủi ro RPO.
3. Chuyển quyền **SQL primary** sang B theo cơ chế được dịch vụ hỗ trợ; đảm bảo A không tiếp tục ghi sau khi có thể kết nối lại.
4. App Service B xác nhận writer endpoint hoạt động, quyền truy cập hợp lệ, job/consumer an toàn và **traffic readiness** trả thành công.
5. Front Door chuyển traffic về B theo health/priority; giám sát tỷ lệ lỗi, p95, throughput, số đơn hàng và backlog. Mở rộng B nếu tải tăng.
6. Đối soát đơn hàng đang xử lý, request retry và sự kiện chưa gửi, sau đó thông báo trạng thái khôi phục.

**Phân rã RTO để kiểm chứng:** phát hiện 2 phút + xác định/quyết định 3 phút + failover dữ liệu 4 phút + scale/làm nóng 6 phút + ổn định traffic 2 phút + xác minh nghiệp vụ 5 phút = **22 phút** nếu giả sử các bước nối tiếp và thực sự đạt thời gian đó. Đây chỉ là **ngân sách thử nghiệm**; nếu thực tế promote hoặc scale tốn 20 phút, mục tiêu 30 phút có thể bị vượt. Một số bước có thể chạy song song, nhưng chỉ kết quả diễn tập mới xác nhận RTO.

**RPO 5 phút không tự được đảm bảo** bởi SQL failover group. Cần đo độ trễ nhân bản khi tải cao và hiểu rủi ro giao dịch chưa nhân bản trong sự cố bất ngờ. Nếu dữ liệu mất vượt giới hạn nghiệp vụ, cần xem xét cơ chế xác nhận giao dịch, bù trừ và kiến trúc dữ liệu khác.

## 7. Thiết kế vận hành đầy đủ cho từng region

### 7.1. Tài nguyên, mạng, danh tính và bí mật

Tạo cấu hình có thể lặp lại bằng **Bicep hoặc Terraform**, đặt tham số cho mỗi region, đặt tên tài nguyên và tag nhất quán. Dùng pipeline có kiểm tra và quyền tối thiểu để triển khai cả hai vùng. Với mỗi region, rà soát:

- **Compute:** App Service/AKS/Container Apps theo SKU và tính năng có sẵn tại region, số instance tối thiểu, autoscaling và quota.
- **Mạng:** VNet/subnet, private endpoint, private DNS, NSG, firewall, egress, kết nối hybrid và route khi vùng chính mất.
- **Identity và secret:** managed identity, Entra ID, role assignment/RBAC, Key Vault, chứng chỉ TLS, khóa mã hóa và cơ chế cấp phát/luân chuyển secret.
- **Dữ liệu:** primary/secondary, backup, retention, restore, replication và quyền truy cập ghi/đọc.
- **Ops:** Azure Monitor, Application Insights/Log Analytics, cảnh báo, action group, dashboard và đường liên lạc sự cố.
- **Phụ thuộc ngoài:** dịch vụ thanh toán, email, webhook, hệ thống on-premises; kiểm tra chúng có cho phép nguồn yêu cầu mới từ region B hay không.

Đối với bảo mật mạng, Azure Front Door có thể hỗ trợ cơ chế bảo vệ origin phù hợp với loại dịch vụ và tier, nhưng phải kiểm chứng cấu hình cụ thể; không giả định bật WAF là origin sẽ không thể bị gọi trực tiếp. Chú ý cả đường quản trị và cấp quyền khi region chính hoặc một thành phần kết nối private gặp sự cố.

### 7.2. Năng lực N-1 và chi phí

Với **active-active 50/50**, mỗi region bình thường xử lý khoảng 1.000 request/giây trong ví dụ 2.000 request/giây. Nếu một vùng mất, vùng còn lại phải có khả năng xử lý gần **2.000 request/giây**, cộng biên an toàn phù hợp. Không thể chỉ nhân đôi số instance API: database connection, storage throughput, queue consumers, mạng, cache, rate limit và third-party quota cũng cần chịu tải.

Chi phí phải tính toàn vòng đời: compute thường trực ở cả hai nơi, bản sao dữ liệu, backup, replication, **data transfer giữa region**, lưu lượng qua global ingress, logs/metrics, diễn tập và phần năng lực giữ dự phòng. Với hot standby, chi phí có thể tiệm cận hai môi trường sản xuất; với warm standby, giá thấp hơn nhưng có rủi ro thời gian scale và hạn mức cấp phát.

### 7.3. Monitoring phải quan sát trải nghiệm và trạng thái dữ liệu

Một nhóm tín hiệu nên có:

| Tín hiệu | Vì sao cần |
| --- | --- |
| Synthetic test từ nhiều vị trí | Phát hiện người dùng không vào được hệ thống ngay cả khi VM/App Service vẫn báo chạy. |
| Front Door origin health, HTTP 5xx, latency | Xác định traffic đã/đang được chuyển và origin nào trả lỗi. |
| API success rate, p95/p99, dependency failures | Xác minh SLO ở mức nghiệp vụ và trải nghiệm người dùng. |
| SQL replication lag, vai trò writer, connection errors | Theo dõi khả năng đạt RPO và ngăn route tới nơi chưa thể ghi. |
| Cache hit/miss, queue backlog, consumer lag | Phát hiện vấn đề sau khi dồn tải vào region B. |
| Capacity, autoscaling, quota và chi phí | Đảm bảo N-1 capacity và kiểm soát ngân sách DR. |

Ví dụ truy vấn KQL trong **Log Analytics workspace** dùng bảng **AppRequests** (tên cột và nguồn dữ liệu cần kiểm tra theo thiết lập Application Insights):

~~~kusto
AppRequests
| where TimeGenerated > ago(24h)
| summarize Requests = count(),
            Succeeded = countif(Success == true)
    by bin(TimeGenerated, 5m), AppRoleName
| extend SuccessPct = 100.0 * todouble(Succeeded) / Requests
| order by TimeGenerated asc
~~~

Chỉ số trên **không tính được yêu cầu bị chặn ở Front Door hoặc không đến ứng dụng**; muốn đo trải nghiệm đầu cuối phải kết hợp tín hiệu ở edge và synthetic probes. Cảnh báo phải có ngưỡng và cửa sổ quan sát, tránh đổi tuyến liên tục khi một phép đo ngắn hạn dao động.

## 8. Failover, failback và diễn tập

**Failover** là đưa tải và vai trò dữ liệu sang vùng dự phòng. **Failback** là quyết định chuyển lại vùng ban đầu sau khi đã sửa, đồng bộ và đánh giá rủi ro; failback không nhất thiết phải xảy ra ngay khi vùng cũ vừa online.

Một runbook tối thiểu nên nêu người chịu trách nhiệm, điều kiện kích hoạt, số liệu quan sát, lệnh/thao tác đã duyệt cho từng dịch vụ, cách ngăn split-brain, điểm dừng an toàn và đường hoàn tác. Luồng điều phối tham khảo:

~~~mermaid
flowchart TD
    D[Phát hiện suy giảm ở region A] --> V{Sự cố đủ điều kiện failover?}
    V -->|Không| O[Điều tra, tiếp tục theo dõi]
    V -->|Có| G[Đánh giá RPO và khóa đường ghi sai]
    G --> P[Promote writer sang region B theo runbook]
    P --> R{B có thể ghi và phục vụ nghiệp vụ?}
    R -->|Không| S[Dừng mở traffic, khắc phục phụ thuộc]
    R -->|Có| T[Chuyển/mở traffic đến B]
    T --> H[Kiểm tra giao dịch, SLI, backlog và tải]
    H --> F[Phục hồi vùng A, đồng bộ và lập kế hoạch failback]
~~~

Thực hiện **game day** định kỳ với tiêu chí đo rõ ràng:

| Bài thử | Kết quả cần ghi |
| --- | --- |
| Làm một instance hoặc zone lỗi | Sự cố được cô lập; các luồng không liên quan không suy giảm quá SLO. |
| Loại origin A khỏi khả năng phục vụ | Front Door/Traffic Manager chuyển phù hợp, client retry an toàn, đo thời gian và 5xx. |
| Mô phỏng database primary không ghi được | Readiness thất bại đúng chỗ, writer promotion/fencing đúng, kiểm tra RPO thực tế. |
| Chuyển 100% tải sang B trong giờ giả lập cao điểm | Throughput, latency, queue, database và quota còn trong giới hạn. |
| Mất mạng liên vùng nhưng hai app còn chạy | Không có hai writer trái phép; hành vi đọc/ghi theo chính sách consistency. |
| Xóa sai dữ liệu hoặc đưa ra bản phát hành hỏng | Restore/rollback từ backup hoặc artifact an toàn; replication không thay thế phục hồi logic. |
| Failback sau khi A phục hồi | Không mất/trùng đơn, xác nhận lại chiều replication và quyền writer. |

Với mỗi bài thử, ghi **thời gian bắt đầu sự cố, phát hiện, quyết định, dữ liệu cuối cùng còn nguyên, ứng dụng phục vụ thành công trở lại và số lỗi người dùng**. Từ đó tính RTO/RPO đạt được, cập nhật runbook và chỉ tăng mức tự động hóa khi quan sát được hành vi an toàn. Diễn tập trong môi trường không ảnh hưởng production trước; bài thử production phải tuân thủ lịch và kiểm soát thay đổi của đơn vị.

## 9. Sai lầm phổ biến và cách kiểm tra

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Có app hai region và coi như đã có DR | Database, key, queue hoặc DNS trở thành điểm lỗi chung | Vẽ sơ đồ phụ thuộc đầu cuối và thử mất region thực tế. |
| Đặt Front Door probe chỉ tại đường trả HTTP 200 tĩnh | Origin khỏe giả trong khi database không thể ghi | Dùng health phân tầng, route theo khả năng phục vụ nghiệp vụ. |
| Coi geo-replication là backup hoặc RPO = 0 | Hỏng logic lan sang secondary; mất dữ liệu chưa nhân bản | Tách backup/restore và đo replication lag, thử forced failover. |
| Active-active mà dùng session trong bộ nhớ | Người dùng mất phiên hoặc gặp dữ liệu lệch sau chuyển vùng | Externalize session, xác định consistency và idempotency. |
| Chia 50/50 nhưng mỗi vùng chỉ đủ một nửa công suất | Vùng sống sót quá tải ngay sau failover | Kiểm thử N-1 capacity, quota và tốc độ scale. |
| Promote B trong khi A vẫn có thể ghi | Split-brain, lịch sử giao dịch không thể hòa giải tự động | Fencing và writer authority rõ ràng, kiểm tra trước khi mở ghi. |
| Chuyển lại A ngay khi dịch vụ xanh | Backlog, cache và replication chưa ổn định | Failback có lịch, đối soát và quy trình kiểm soát riêng. |

## 10. Bài thực hành thiết kế

Hãy phác thảo một dịch vụ quản lý đơn hàng có frontend toàn cầu, API trên Azure và một Azure SQL database. Yêu cầu giả định: RTO 30 phút, RPO 5 phút, 2.000 request/giây giờ cao điểm và không được ghi trùng đơn. Sản phẩm bàn giao gồm:

1. **ADR một trang** chọn active-passive hot, warm hoặc active-active đọc/single-writer; giải thích bằng RTO/RPO, tính nhất quán và chi phí.
2. **Sơ đồ** gồm edge routing, ít nhất hai region, writer endpoint, đường nhân bản, phụ thuộc identity/secret và hệ thống giám sát.
3. **Bảng quy trình failover** nêu tín hiệu phát hiện, ai cho phép promote, cách ngăn writer cũ, điều kiện readiness, cách chuyển traffic và số đo xác nhận.
4. **Kịch bản thử N-1** với tải 2.000 request/giây và kiểm tra retry bằng idempotency key.
5. **Kế hoạch failback** có điều kiện dừng và cách kiểm tra không thiếu/trùng đơn.

Một đáp án tốt sẽ không khẳng định RPO 5 phút chỉ vì đã bật geo-replication: nó trình bày cách **đo độ trễ nhân bản**, chấp nhận hoặc loại bỏ rủi ro forced failover, và quy trình đối soát những giao dịch chưa chắc đã được nhân bản.

## Ghi nhớ

- **Multi-region là bài toán đầu cuối**, gồm traffic, app, dữ liệu, danh tính, mạng, vận hành và khả năng khôi phục.
- **Active-passive** thường đơn giản hơn khi nghiệp vụ cần một writer; hot/warm/cold standby quyết định chi phí và RTO.
- **Active-active** giúp phục vụ nhiều địa bàn và có thể chuyển traffic nhanh, nhưng phải chứng minh consistency, chống conflict và **N-1 capacity**.
- **Azure Front Door/Traffic Manager giải bài toán định tuyến**; promote database, bảo vệ dữ liệu và failback cần chiến lược riêng.
- **SLO, RTO và RPO chỉ có ý nghĩa khi đo được qua diễn tập**; replication không thay cho backup và hệ thống có hai region không tự bảo đảm an toàn trước mọi sự cố.
