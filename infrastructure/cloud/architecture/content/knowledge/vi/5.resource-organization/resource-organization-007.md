# Áp dụng giới hạn dịch vụ, ngân sách và chính sách tổ chức

## 1. Vì sao quản trị tài nguyên là một quyết định kiến trúc?

Một ứng dụng đám mây có thể chạy tốt khi thử nghiệm nhưng thất bại ở quy mô thực tế: bộ tự mở rộng không tạo được máy vì chạm **service quota**, chi phí tăng mạnh do tài nguyên bỏ quên, hoặc nhóm phát triển tạo cơ sở dữ liệu tại khu vực không được phép. Các vấn đề này xuất hiện dù mã nguồn ứng dụng không có lỗi. Vì vậy, **tổ chức tài nguyên** là một phần của thiết kế kiến trúc và vận hành, chứ không chỉ là thủ tục quản trị sau khi triển khai.

Trong module **CLOUD_ARCHITECTURE**, việc chuyển từ yêu cầu nghiệp vụ sang lựa chọn mạng, compute, dữ liệu và mô hình triển khai cần đi kèm cơ chế bảo vệ các mục tiêu về **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và khả năng vận hành**. Ba nhóm công cụ quan trọng là:

- **Giới hạn dịch vụ (service quota/limit):** giới hạn số lượng tài nguyên, công suất hoặc tần suất thao tác mà nền tảng cho phép trong một phạm vi.
- **Ngân sách (budget):** mục tiêu chi tiêu đi kèm cảnh báo, dự báo và quy trình xử lý khi chi phí tiến gần hoặc vượt mức cho phép.
- **Chính sách tổ chức (organization policy/guardrail):** quy định hành động, vị trí, cấu hình và kiểu tài nguyên được phép sử dụng.

Ví dụ xuyên suốt bài: một doanh nghiệp có nền tảng đặt chỗ với môi trường **development, staging, production**; lượt tìm kiếm tăng mạnh theo mùa, còn dữ liệu đặt chỗ cần kiểm soát truy cập và phục hồi sau sự cố. Những con số dưới đây là **giả định học tập**, không phải quota mặc định hay mức chi phí được bảo đảm cho mọi nhà cung cấp.

## 2. Phân biệt quota, budget, policy và phân quyền

| Cơ chế | Câu hỏi cần trả lời | Ví dụ | Điều không được suy diễn |
| --- | --- | --- | --- |
| **Service quota** | Tối đa sử dụng được bao nhiêu trong phạm vi nào? | Số vCPU theo nhóm máy/vùng, số địa chỉ IP, số request API mỗi giây | Không bảo đảm nhà cung cấp có sẵn công suất vật lý; không cấp quyền cho người dùng |
| **Budget** | Đang hoặc có thể sẽ chi bao nhiêu so với mục tiêu? | Cảnh báo khi dự báo cuối tháng vượt ngân sách | Cảnh báo thường không tự động ngắt dịch vụ hay chặn hóa đơn ngay tại ngưỡng |
| **Organization policy** | Cấu hình hay hành động nào được phép? | Chặn tạo tài nguyên production ngoài region đã phê duyệt | Không tự cấp quyền IAM cho người dùng |
| **IAM/RBAC** | Danh tính nào được thao tác gì trên tài nguyên nào? | Dev có quyền xem log môi trường dev, không được xóa DB production | Không thay thế quota hoặc dự báo chi phí |
| **Rate limit của ứng dụng** | Client được gửi bao nhiêu yêu cầu vào API của sản phẩm? | Mỗi tài khoản được tìm kiếm 100 lần/phút | Không thay quota do nhà cung cấp cloud áp lên API dịch vụ |

Một người có quyền tạo máy ảo vẫn có thể nhận lỗi do vượt quota. Một dự án còn quota vẫn có thể vượt ngân sách. Một chính sách cấm tài nguyên công khai có thể từ chối thao tác dù người dùng có quyền và quota còn trống. Do đó ba cơ chế phải được thiết kế cùng nhau.

### Các kiểu giới hạn cần nhận biết

- **Quota điều chỉnh được:** có thể yêu cầu tăng, nhưng còn phụ thuộc xét duyệt và khả năng cung cấp; yêu cầu tăng không đồng nghĩa được chấp thuận.
- **Giới hạn không điều chỉnh được:** thuộc tính của dịch vụ hoặc kiến trúc, có thể buộc phân vùng workload hay thay đổi giải pháp.
- **Quota số lượng/công suất:** số instance, vCPU, địa chỉ IP, volume, kết nối hoặc nhiệm vụ đồng thời.
- **Quota tốc độ:** số request hay thao tác trong một khoảng thời gian, có thể dẫn đến throttling khi vượt ngưỡng.
- **Ngưỡng cảnh báo nội bộ:** mức sử dụng nhóm tự đặt, chẳng hạn 70% hoặc 85% của quota được cấp, nhằm có thời gian xử lý trước khi chạm giới hạn.

**Phạm vi quota rất quan trọng:** có quota tính theo tài khoản, subscription, project, region, zone, nhóm máy hoặc từng tài nguyên. Tên, cách tính, khả năng tăng và ngưỡng mặc định phụ thuộc nhà cung cấp, loại dịch vụ và thời điểm. Cần lấy giá trị tại **đúng phạm vi đang vận hành** từ API/console và tài liệu dịch vụ chính thức.

## 3. Thiết kế ranh giới tổ chức trước khi đặt giới hạn

Cách chia tài nguyên ảnh hưởng tới bảo mật, quota, khả năng quy trách nhiệm và phân bổ ngân sách. Một tổ chức có thể dùng cấu trúc logic:

~~~mermaid
flowchart TB
    ORG["Tổ chức"]
    ORG --> SHARED["Đơn vị dùng chung"]
    ORG --> PROD["Đơn vị production"]
    ORG --> NONPROD["Đơn vị non-production"]
    SHARED --> LOG["Tài khoản/dự án logging, security"]
    SHARED --> NET["Tài khoản/dự án mạng chung"]
    PROD --> API["Tài khoản/dự án ứng dụng prod"]
    PROD --> DATA["Tài khoản/dự án dữ liệu prod"]
    NONPROD --> STAGING["Tài khoản/dự án staging"]
    NONPROD --> DEV["Tài khoản/dự án dev"]
~~~

Đây là cấu trúc minh họa. Số tài khoản/dự án thực tế phụ thuộc quy mô nhóm, yêu cầu cô lập, cách áp policy và phạm vi quota. Không cần tách mọi microservice thành một tài khoản khi chi phí vận hành vượt lợi ích.

| Lý do tách phạm vi | Hướng tổ chức | Lợi ích và đánh đổi |
| --- | --- | --- |
| Bảo vệ production | Phân tách tài khoản/dự án production với sandbox | Giảm nguy cơ thao tác nhầm; thêm quản lý danh tính và kết nối |
| Phân bổ chi phí | Phân chia theo sản phẩm/môi trường, kèm nhãn owner | Báo cáo rõ hơn; chi phí dùng chung vẫn cần quy tắc phân bổ |
| Chính sách nhất quán | Áp guardrail ở cấp nhóm tổ chức và các cấp con phù hợp | Giảm sai lệch; phải hiểu chính xác cơ chế kế thừa và ngoại lệ |
| Nhu cầu quota khác nhau | Phân nhóm workload có tải và mức rủi ro khác nhau | Giảm tranh chấp tài nguyên; không được phân tách chỉ để lách kiểm soát |
| Vận hành tập trung | Logging, security và network hub có chủ sở hữu riêng | Dễ quản trị; phải tránh điểm lỗi chung và quyền quá rộng |

Ví dụ khái niệm: AWS có Organizations và accounts; Azure có management groups, subscriptions và resource groups; Google Cloud có organization, folders và projects. **Các tầng này không hoàn toàn tương đương về tính kế thừa, quota và cách từ chối hành động**. Khi áp một policy thực tế phải kiểm tra semantics của đúng dịch vụ, không tự suy từ hình vẽ chung.

Nhãn tài nguyên (tag/label) mô tả ứng dụng, nhóm, môi trường và trung tâm chi phí. Nhãn hỗ trợ kiểm toán, truy vấn và phân bổ hóa đơn, nhưng **không phải ranh giới bảo mật thay cho IAM, network isolation và tổ chức tài khoản**.

## 4. Từ yêu cầu chất lượng đến kế hoạch quota

Giới hạn dịch vụ cần được xem ngay khi xác định yêu cầu về tải đỉnh, mở rộng, thời gian triển khai và khôi phục. Cách làm là dự báo **nhu cầu bình thường → tải đỉnh → triển khai/rollout → kịch bản lỗi/DR**, rồi đối chiếu quota của tất cả dịch vụ có liên quan.

### 4.1. Lập danh mục quota

Đối với từng workload, ghi đủ:

1. **Tên dịch vụ, quota và đơn vị đo:** instance, vCPU, IP, connections, throughput, API calls, concurrent jobs...
2. **Phạm vi:** tổ chức/tài khoản/subscription/project, region/zone hoặc tài nguyên cụ thể.
3. **Giá trị được cấp và mức sử dụng hiện tại:** lấy từ dashboard/API; ghi nguồn và ngày đo.
4. **Dự báo nhu cầu:** bình thường, cao điểm, mở rộng khi rollout, khi chuyển vùng và khi khôi phục.
5. **Khả năng tăng:** quota có điều chỉnh được không; có cần ticket, lead time, phê duyệt không.
6. **Owner, cảnh báo, runbook:** ai phản ứng và cách khắc phục khi sắp chạm giới hạn.

| Nhóm quota | Vì sao ảnh hưởng kiến trúc? | Ví dụ lỗi nếu bỏ qua |
| --- | --- | --- |
| vCPU/instance theo loại và vùng | Bộ tự mở rộng, dự phòng và phục hồi cần tạo tài nguyên mới | Không tạo được máy dù tải đang tăng |
| IP, subnet, giao diện mạng | Việc tạo compute/endpoint còn phụ thuộc tài nguyên mạng | Còn vCPU nhưng hết địa chỉ IP trong subnet |
| DB connection, dung lượng, IOPS/throughput | Dịch vụ dữ liệu có trần năng lực riêng, không nhất thiết tăng cùng ứng dụng | Tăng instance ứng dụng làm cạn connection pool |
| Request/API của dịch vụ được quản lý | Tác vụ hàng loạt, triển khai hoặc retry có thể bị throttle | Tắc nghẽn API ngay lúc khôi phục |
| Giới hạn hàng đợi, job, tác vụ đồng thời | Ảnh hưởng độ trễ xử lý bất đồng bộ | Backlog lớn dù máy ứng dụng còn rảnh |
| Quota cho log, security, networking | Quan sát và kiểm soát cần tài nguyên đi kèm | Không tạo được rule giám sát hoặc endpoint dự phòng |

### 4.2. Ví dụ tính nhu cầu compute

Giả sử load test xác nhận một instance xử lý bền vững **40 yêu cầu/giây** mà vẫn đạt mục tiêu p95. Dự báo tải đỉnh là **600 yêu cầu/giây**. Nhóm quyết định thêm **20% số instance dự phòng** so với nhu cầu lý thuyết.

~~~text
Instance cần để xử lý đỉnh = ceil(600 / 40) = 15
Instance mục tiêu sau headroom = ceil(15 * 1,20) = 18
~~~

Mức 18 là **số instance phục vụ trong kịch bản minh họa**, không phải quota nên đặt chính xác 18. Nếu rolling deployment cần thêm 6 instance tạm, nhu cầu kiểm tra có thể lên **24 instance đồng thời**. Mặt khác, phương án chịu lỗi khi mất một availability zone có thể cần cấp phát thêm instance ở những zone còn lại. Khi đó phải đánh giá quota theo số vCPU và loại máy, IP, load balancer, volume, kết nối DB và các quota phụ thuộc. Phép tính này chưa xem xét thời gian startup, hiệu suất thực tế sau failover và tốc độ autoscaler phản ứng.

**Quota không phải capacity reservation.** Dù được cấp hạn mức đủ lớn, một vùng/zone có thể thiếu công suất sẵn có hoặc loại instance cần thiết. Khả năng phục hồi còn đòi hỏi chiến lược loại máy thay thế, phân bố zone/vùng, năng lực mạng/dữ liệu và diễn tập tạo tài nguyên.

### 4.3. Ứng phó khi tiến gần giới hạn

Mức sử dụng quota phải được giám sát cùng tình trạng quá tải và lỗi cấp phát. Những thao tác kỹ thuật thường cần:

- Retry có **backoff, jitter và giới hạn số lần thử**, phân biệt lỗi tạm thời với lỗi không thể khắc phục bằng retry.
- Hàng đợi và **backpressure** để tránh làm sập dịch vụ phụ thuộc khi tải tăng.
- Timeout/circuit breaker đối với luồng đồng bộ; không cho một phụ thuộc nghẽn gây lỗi dây chuyền.
- Idempotency cho thao tác có thể lặp để không tạo tài nguyên hoặc giao dịch trùng.
- Cảnh báo trước khi cạn quota và runbook xử lý có chủ sở hữu, thay vì chờ autoscaler thất bại.

## 5. Quản trị quota trong vận hành và phục hồi

Một bản ghi quản trị quota có thể trông như sau:

| Thuộc tính | Giá trị minh họa |
| --- | --- |
| ID | Q-COMPUTE-PROD-01 |
| Workload/owner | API tìm kiếm / Platform SRE |
| Quota/phạm vi | vCPU nhóm máy dự kiến tại region production |
| Mức quota hiện tại | Chờ đọc và xác nhận từ API/console nhà cung cấp |
| Nhu cầu | 18 instance đỉnh có headroom; có thể tới 24 khi rollout |
| Ngưỡng vận hành | 70% xem xét, 85% xử lý ưu tiên; ngưỡng minh họa |
| Kế hoạch | Kiểm tra các quota liên quan, gửi yêu cầu tăng nếu cần, thử scale |
| Bằng chứng | Load test, dashboard quota, ticket tăng quota, kết quả diễn tập |

Chu trình áp dụng:

1. **Trước khi triển khai**, đối chiếu quota và nhu cầu ở đúng vùng, môi trường, nhóm tài nguyên và thời điểm; kiểm tra mọi phụ thuộc trên đường triển khai.
2. **Trước mùa cao điểm**, so tải đỉnh và công suất phụ thuộc, cập nhật dự báo, gửi yêu cầu tăng quota đủ sớm và chuẩn bị phương án khi yêu cầu không được duyệt.
3. **Sau khi yêu cầu tăng được chấp nhận**, đọc lại quota thực tế; một ticket đã gửi chưa phải quota đã đổi.
4. **Trong vận hành**, cảnh báo theo mức dùng và lỗi throttle, kiểm tra các quota tăng nhanh hoặc từng là nguồn gây sự cố.
5. **Trước khi diễn tập DR**, kiểm tra quota riêng tại vùng dự phòng, quyền cấp phát, số lượng IP/vCPU, quyền khôi phục DB và dung lượng cần thiết.

Đừng tăng mọi quota vô điều kiện với suy nghĩ như thế sẽ an toàn nhất. Hạn mức quá thấp gây lỗi mở rộng; quản trị quá lỏng trong khi IAM không chặt có thể tăng rủi ro tiêu thụ và chi phí. Hạn mức chỉ là **một lớp bảo vệ** trong kiến trúc.

## 6. Lập ngân sách và phân bổ chi phí có trách nhiệm

Ngân sách phải gắn với mục tiêu kinh doanh, mức tải đã được ước tính và chủ sở hữu quyết định chi phí. Bảng giá một máy chủ không đại diện cho tổng chi phí vòng đời.

~~~text
Chi phí cloud cần dự báo =
    compute + database + storage
  + network, NAT/load balancer và truyền dữ liệu ra
  + log/metric/trace, bảo mật, khóa và kiểm toán
  + backup, replication, DR và phục hồi
  + phí hỗ trợ, giấy phép và vận hành liên quan
~~~

Một kế hoạch minh họa cho hệ thống đặt chỗ là **15.000 USD/tháng**:

| Hạng mục | Dự báo USD/tháng | Điều cần xác minh |
| --- | ---: | --- |
| Compute và dịch vụ ứng dụng | 5.000 | Tải trung bình/đỉnh, autoscaling, công suất rỗi |
| Database và storage | 3.500 | Dung lượng, tốc độ tăng, đọc/ghi, backup |
| Mạng và truyền dữ liệu | 2.000 | Egress, NAT, lưu lượng chéo zone/vùng, traffic nội bộ |
| Logging, monitoring, security | 1.000 | Số metric, log/trace, retention và audit |
| Backup và DR | 1.500 | Bản sao, dữ liệu khác vùng, diễn tập khôi phục |
| **Tổng vận hành dự kiến** | **13.000** | Cần đo lại khi có hệ thống thực |
| **Khoảng dự phòng ngân sách** | **2.000** | Chênh lệch kế hoạch, không phải phí được thu tự động |
| **Ngân sách mục tiêu** | **15.000** | Bao gồm phương án phân bổ chi phí chung |

Phải ghi rõ giả định về tải, kích thước dữ liệu, tăng trưởng, region, dịch vụ, chi phí hỗ trợ và thuế/tỷ giá nếu áp dụng. Nên có ít nhất **ba kịch bản: bình thường, mùa cao điểm và sự cố/DR**; một lần khôi phục hoặc kiểm thử tải lớn có thể khiến chi phí vượt mức ngày thường.

### 6.1. Phân bổ theo môi trường và owner

| Phạm vi | Ngân sách ví dụ USD/tháng | Chịu trách nhiệm |
| --- | ---: | --- |
| Production | 10.000 | Product Owner và SRE |
| Staging | 3.000 | QA/Platform |
| Development | 2.000 | Engineering Manager |
| **Tổng** | **15.000** | Finance/FinOps tổng hợp |

Chi phí dùng chung như network hub, logging tập trung, backup hoặc hỗ trợ phải có phương pháp phân bổ nhất quán. Có thể phân chia theo tỷ lệ sử dụng, tài nguyên, môi trường hoặc quy tắc tài chính được duyệt. Tránh **tính trùng** và tránh bỏ sót chi phí không gắn được nhãn.

Một taxonomy nhãn có thể gồm:

| Nhãn | Giá trị ví dụ | Mục đích |
| --- | --- | --- |
| environment | prod, staging, dev | Tách vòng đời và mức rủi ro |
| application | booking-platform | Gắn chi phí với sản phẩm |
| team | reservations | Nhóm sở hữu |
| cost-center | CC-104 | Phân bổ tài chính |
| data-classification | confidential | Hỗ trợ chính sách dữ liệu |
| managed-by | terraform | Xác định nguồn khai báo tài nguyên |

Không phải mọi dịch vụ đều hỗ trợ nhãn trên từng tài nguyên và mọi mục hóa đơn. Phân bổ chi phí cần kết hợp **cấu trúc tài khoản/dự án, dữ liệu billing, tag/label hợp lệ và quy tắc phân bổ dùng chung**. Không đưa bí mật hoặc thông tin cá nhân vào nhãn.

### 6.2. Cảnh báo không đồng nghĩa giới hạn chi tiêu cứng

Một quy trình tham khảo:

- **50% ngân sách actual:** so sánh số ngày đã qua với mức chi dự kiến; kiểm tra các chiến dịch hay thử tải đã lên kế hoạch.
- **80% actual hoặc forecast:** cảnh báo chủ ứng dụng và FinOps, phân tích cost driver, tài nguyên bỏ quên, egress, retention và thay đổi gần đây.
- **100% hoặc dự báo vượt mục tiêu:** mở quy trình giải trình và điều chỉnh có phê duyệt; ưu tiên giữ các dịch vụ quan trọng và nghĩa vụ dữ liệu.

Mức 50/80/100% chỉ là **ngưỡng minh họa**. Chi 80% vào ngày cuối tháng khác với 80% ngay đầu tháng. Nên kết hợp actual, forecast, tốc độ tăng và phát hiện bất thường; dữ liệu billing có thể có độ trễ.

**Budget alert thường không tự chặn tài nguyên hoặc dừng hóa đơn.** Nếu cần ngăn hành vi có chi phí lớn, phải kết hợp giới hạn quyền, policy, quy trình phê duyệt loại máy/tài nguyên hoặc automation được thiết kế và kiểm thử. Không tự động tắt production hay DR chỉ vì một cảnh báo ngân sách, khi hành động đó có thể vi phạm SLO, RTO hoặc yêu cầu bảo vệ dữ liệu.

## 7. Chính sách tổ chức: chuyển quy tắc thành guardrail

**Organization policy** giúp ràng buộc cách tài nguyên được tạo và sử dụng ở phạm vi quản trị. Chính sách cần xuất phát từ **nghĩa vụ, rủi ro hoặc mục tiêu vận hành cụ thể**. Một quy định như "mọi tài nguyên đều phải an toàn" quá mơ hồ để kiểm chứng; một quy định như "không được tạo cơ sở dữ liệu chứa dữ liệu khách hàng có endpoint công cộng ở production" có thể kiểm tra được.

### 7.1. Các nhóm chính sách cần xem xét

| Nhóm | Ví dụ quy tắc | Điều cần lưu ý |
| --- | --- | --- |
| Vị trí triển khai | Dữ liệu phân loại confidential chỉ được xử lý trong các region đã phê duyệt | Xem xét cả log, backup, bản sao và hệ thống hỗ trợ |
| IAM và quyền quản trị | Chỉ nhóm vận hành có quyền sửa/xóa cơ sở dữ liệu production, dùng xác thực mạnh | Giới hạn quyền cấp tổ chức không đồng nghĩa cấp quyền IAM |
| Bảo mật mạng | Database production không được có endpoint Internet trực tiếp | Kiểm tra route, firewall, endpoint, DNS và các ngoại lệ kết nối hợp lệ |
| Mã hóa và bí mật | Dữ liệu nhạy cảm được mã hóa khi truyền/lưu; secrets đặt trong dịch vụ quản lý bí mật | Cần quản lý khóa, rotation, audit và quy trình khôi phục |
| Chuẩn compute | Chỉ dùng image và họ máy đã kiểm tra ở production; giới hạn kích thước ở sandbox | Không vô tình chặn loại máy dự phòng được phê duyệt |
| Gắn nhãn | Tài nguyên hỗ trợ tag phải có environment, application, team, cost-center | Một số dịch vụ không hỗ trợ tag lúc tạo hoặc không lập hóa đơn theo tag |
| Logging và kiểm toán | Bật audit log cho hành động quản trị; log được giữ theo thời hạn đã duyệt | Giảm ghi dữ liệu nhạy cảm thừa và bảo vệ log khỏi sửa/xóa |
| Bảo vệ tài nguyên trọng yếu | Cấm xóa backup hoặc DB production ngoài quy trình được phê duyệt | Phải có phương án break-glass an toàn khi xảy ra sự cố |

Khả năng của **chính sách cấp tổ chức** và **IAM** không đồng nhất. Chẳng hạn, trong AWS, Service Control Policies (SCP) có vai trò giới hạn quyền tối đa mà các principal thuộc phạm vi áp dụng có thể sử dụng; bản thân SCP **không cấp quyền IAM**. Ở nền tảng khác, một chính sách có thể từ chối việc tạo tài nguyên sai cấu hình hoặc đánh giá trạng thái tuân thủ. Khi triển khai phải kiểm tra **loại tài nguyên được hỗ trợ, cách kế thừa, thứ tự đánh giá, quyền miễn trừ và hiệu lực đối với tài nguyên đã tồn tại**.

### 7.2. Preventive, detective và corrective

| Lớp kiểm soát | Cách hoạt động | Minh họa |
| --- | --- | --- |
| **Preventive** — ngăn chặn | Từ chối cấu hình/hành động sai ngay khi tạo hoặc ngay trong pipeline | Chặn database production có truy cập công cộng |
| **Detective** — phát hiện | Quét và cảnh báo về trạng thái không phù hợp, kể cả tài nguyên cũ | Phát hiện bucket không có owner hoặc audit log bị tắt |
| **Corrective** — khắc phục | Mở ticket, chạy runbook hoặc tự động sửa theo phạm vi được phép | Gỡ cấu hình public sai, thông báo owner và lưu bằng chứng |

Chỉ kiểm tra IaC trong CI/CD không đủ vì người dùng còn có thể thay đổi qua console/API hoặc các tài nguyên cũ chưa được khai báo bằng code. Ngược lại, chỉ đặt policy ở cloud khiến nhóm phát triển phát hiện lỗi quá muộn. Cần dùng cả **kiểm tra trước triển khai, guardrail khi triển khai và theo dõi drift sau triển khai**.

### 7.3. Mô tả chính sách dưới dạng dữ liệu

Ví dụ dưới đây là **đặc tả trung lập để thảo luận**, không phải cú pháp có thể triển khai trực tiếp lên AWS, Azure hoặc Google Cloud:

~~~yaml
policyId: GOV-REGION-01
description: Hạn chế vùng triển khai của dữ liệu confidential
scope:
  environment: prod
  dataClassification: confidential
rule:
  when: resource.region NOT_IN approvedRegions
  effect: DENY
approvedRegions:
  - region-a  # Tên minh họa, thay bằng vùng được phê duyệt thực tế
owner: cloud-platform-team
evidence:
  - policy-evaluation-log
  - compliance-report
exception:
  approver: security-owner
  reasonRequired: true
  expiryDateRequired: true
  auditRequired: true
~~~

Khi biến quy tắc này thành policy-as-code, phải xác nhận cách nền tảng xử lý **dịch vụ toàn cục**, tài nguyên có vùng đặc biệt, tài nguyên tạo bằng dịch vụ quản lý và dữ liệu ở backup/log. Một quy định deny tất cả vùng khác có thể vô tình chặn chức năng nền tảng hoặc luồng DR hợp lệ nếu thiếu kiểm thử.

## 8. Áp dụng chính sách có kiểm soát và có ngoại lệ

Chính sách quá rộng có thể làm gián đoạn hoạt động; chính sách dễ bị bỏ qua thì không bảo vệ được gì. Đối với quy tắc ảnh hưởng nhiều tài khoản/dự án, nên làm theo các bước:

1. **Xác định mục tiêu và nguồn:** yêu cầu bảo mật, nghĩa vụ hợp đồng, quy tắc chi phí hoặc hạn chế vận hành nào tạo ra chính sách?
2. **Kiểm kê hiện trạng:** có bao nhiêu tài nguyên đang không đạt, có dịch vụ nào không hỗ trợ điều kiện kiểm soát hay không?
3. **Thử ở nonproduction:** kiểm tra thao tác hợp lệ và không hợp lệ, các pipeline, backup, thay đổi cấu hình và quá trình DR.
4. **Dùng chế độ audit/mô phỏng nếu nền tảng có hỗ trợ:** quan sát phạm vi ảnh hưởng trước khi bật từ chối.
5. **Triển khai từng phạm vi:** thử ở một nhóm tài nguyên/tài khoản trước, theo dõi lỗi và hỗ trợ xử lý.
6. **Giám sát và xem lại:** theo dõi đánh giá policy, thay đổi trực tiếp, trường hợp ngoại lệ và tình huống bị chặn nhầm.

### Quy trình ngoại lệ cần ghi lại điều gì?

Một ngoại lệ phải chứa tối thiểu **ID policy, phạm vi, workload, lý do, rủi ro, biện pháp bù trừ, người phê duyệt, ngày hết hạn và cách kiểm tra thu hồi**. Ví dụ, để mở endpoint tạm cho bên tích hợp, có thể giới hạn địa chỉ nguồn, thời gian, loại dữ liệu và cơ chế ghi log. Hết hạn phải thu hồi hoặc được xét duyệt lại; không để ngoại lệ tạm trở thành quyền vĩnh viễn.

Đối với truy cập khẩn cấp (*break-glass*), tổ chức cần tài khoản/quy trình được bảo vệ đặc biệt, ghi audit và kiểm tra sau sự cố. Quy trình này phải được thử cùng backup và khôi phục; không nên thiết kế chính sách mạnh đến mức không thể thực hiện hành động phục hồi đã được phê duyệt.

### Phân công trách nhiệm tham khảo

| Vai trò | Trách nhiệm |
| --- | --- |
| Product Owner | Xác nhận ưu tiên kinh doanh và mức tác động nếu bị giới hạn |
| Platform/Cloud Engineering | Thiết kế ranh giới tài nguyên, automation, quota monitoring, policy-as-code |
| SRE/Operations | Dự báo capacity, chuẩn bị failover, cảnh báo, runbook và diễn tập |
| Security/Compliance | Kiểm tra dữ liệu, phê duyệt policy nhạy cảm và ngoại lệ |
| Finance/FinOps | Dự báo/giám sát chi phí, phân bổ và xử lý bất thường ngân sách |
| Chủ sở hữu ứng dụng | Gắn nhãn, giải trình tài nguyên, sửa vi phạm và duy trì tiêu chí nghiệm thu |

## 9. Kết hợp quota, budget và policy trên cùng vòng đời kiến trúc

Một quyết định đúng về giới hạn cũng phải xét tác động lên các lớp **compute, mạng, dữ liệu, bảo mật và vận hành**:

~~~mermaid
flowchart TD
    A["Mục tiêu nghiệp vụ, SLO và ràng buộc dữ liệu"]
    A --> B["Cấu trúc tổ chức và ranh giới tài nguyên"]
    B --> Q["Quota và capacity planning"]
    B --> C["Budget, tagging và cost allocation"]
    B --> P["Policy, IAM và quy trình ngoại lệ"]
    Q --> D["IaC, CI/CD và kiểm soát thay đổi"]
    C --> D
    P --> D
    D --> W["Workload đang vận hành"]
    W --> M["Telemetry: quota, cost, audit, SLI"]
    M --> R["Rà soát và điều chỉnh"]
    R --> A
~~~

### Bốn tình huống cho thấy sự phối hợp

**Tình huống A — tăng tải theo mùa:** bộ tự mở rộng cần thêm compute. SRE kiểm tra quota **trước** chiến dịch, kết hợp load test và yêu cầu mở rộng; Finance xem dự báo chi phí, còn policy cho phép nhóm máy/vùng đã được duyệt. Nếu một quy tắc giới hạn kích thước máy chặn nhầm capacity hợp lệ, cần thay đổi có phê duyệt trước thời điểm cao điểm.

**Tình huống B — vùng triển khai sai:** một nhóm tạo database ở region không được phê duyệt. Quota vẫn còn và budget có thể chưa vượt, nhưng policy phải chặn hoặc phát hiện, kiểm tra dữ liệu đã đi qua hay chưa và ghi nhận khắc phục. Sau đó bổ sung kiểm tra tương đương trong pipeline.

**Tình huống C — ngân sách vượt vì khôi phục sự cố:** DR yêu cầu chạy máy dự phòng, mạng và khôi phục dữ liệu. Budget phát cảnh báo để người chịu trách nhiệm xác nhận chi phí; không nên tự động dừng luồng phục hồi khiến vi phạm RTO/RPO. Các ngoại lệ ngân sách/khả năng cấp phát cần được quyết định và lưu vết.

**Tình huống D — quota DR không đủ:** bản vẽ có hệ thống dự phòng ở vùng khác nhưng tài khoản dự phòng không tạo được đủ vCPU, IP hoặc DB. Đội ngũ phải kiểm tra quota **tại từng vùng và phạm vi thực**, xác minh khả năng cấp phát, quyền khôi phục và policy không cản trở failover; sau đó diễn tập để đo RTO/RPO.

### Ma trận truy vết: yêu cầu → kiểm soát → bằng chứng

| Yêu cầu | Quota cần kiểm tra | Chi phí/ngân sách | Policy/IAM | Bằng chứng |
| --- | --- | --- | --- | --- |
| Tìm kiếm chịu 600 rps | vCPU, IP, LB, DB connections, API rate | Dự báo cao điểm và chi phí scale | Vùng và họ máy được phép; quyền autoscaler | Load test, quota dashboard, hóa đơn thử nghiệm |
| Không lộ dữ liệu đặt chỗ | Quota không tự kiểm soát bảo mật | Chi phí audit, encryption, retention | Private endpoint, IAM, key policy, audit | Kiểm thử truy cập và đánh giá cấu hình |
| RTO 2 giờ/RPO 15 phút | Tài nguyên tại vùng DR, backup/restore và API | Backup, replication, standby, diễn tập | Quyền/phạm vi khôi phục đã phê duyệt | Kết quả DR drill, thời gian và điểm phục hồi dữ liệu |
| Chi phí mục tiêu 15.000 USD/tháng | Giới hạn kích thước sandbox khi phù hợp | Budget theo owner, actual, forecast, anomaly alert | Owner/tag bắt buộc, phê duyệt tài nguyên lớn | Báo cáo billing và hồ sơ quyết định |

Nên gắn mỗi yêu cầu với **người sở hữu và ngày cần xem lại**, đặc biệt với các giả định tải và chi phí. Việc gắn nhãn tài nguyên hay tạo dashboard không tự biến một yêu cầu thành kiểm soát hiệu quả; cần kiểm tra kết quả.

## 10. Đánh giá theo tư duy Well-Architected

| Trụ cột/góc nhìn | Câu hỏi cần đánh giá |
| --- | --- |
| **Operational Excellence** | Có owner, runbook, quản trị thay đổi, kiểm thử policy và quy trình xử lý quota/budget alert không? |
| **Security** | Chính sách vị trí dữ liệu, IAM, mã hóa, log, kiểm toán và ngoại lệ có phù hợp rủi ro đã xác nhận không? |
| **Reliability** | Quota/capacity đủ cho đỉnh, rollout và phục hồi; đã thử khi thiếu zone, thiếu kết nối và bị từ chối cấp phát chưa? |
| **Performance Efficiency** | Các giới hạn có cản auto scaling, tạo bottleneck DB/API hoặc gây retry storm không? |
| **Cost Optimization** | Có phân bổ chi phí tới owner, tối ưu tài nguyên nhàn rỗi, cảnh báo bất thường và dự báo nhiều kịch bản không? |
| **Sustainability** | Có quản lý công suất sử dụng, thời hạn giữ dữ liệu/log và tránh tài nguyên nhàn rỗi lâu dài không? |

Một quyết định tăng quota có thể tăng khả năng phục hồi nhưng cũng tăng mức sử dụng tối đa tiềm năng. Một chính sách khóa chặt máy/region giúp quản trị chi phí hoặc dữ liệu nhưng có thể làm suy giảm hiệu năng và khả năng DR. Do đó, **đánh đổi phải được chấp thuận dựa trên nhu cầu và bằng chứng**, không chỉ bằng một quy tắc chung cứng nhắc.

## 11. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Chỉ kiểm tra quota vùng chính | Không tạo được hạ tầng ở vùng dự phòng | Kiểm kê theo vùng/phạm vi và chạy thử failover |
| Nhầm quota với capacity được đảm bảo | Autoscaler vẫn thất bại khi thiếu công suất thực | Có chiến lược loại máy thay thế, dự phòng và thử nghiệm |
| Tin budget sẽ ngắt hóa đơn | Chi phí tiếp tục phát sinh sau ngưỡng | Kết hợp actual, forecast, quy trình phê duyệt và kiểm soát riêng |
| Dựa vào nhãn để cô lập truy cập | Người có quyền sai vẫn truy cập được tài nguyên | Dùng IAM, network isolation và policy thực thi |
| Cấm region/loại tài nguyên mà không thử DR | Không tạo được tài nguyên khôi phục | Kiểm thử policy theo kịch bản lỗi, có ngoại lệ được kiểm soát |
| Không có owner của cảnh báo | Cảnh báo bị bỏ qua hoặc không ai phản ứng | Chỉ định người trực, escalation, SLO xử lý và runbook |
| Chỉ tính tiền compute | Egress, log, backup và support gây vượt ngân sách | TCO nhiều kịch bản và đối chiếu hóa đơn |
| Tăng quota để xử lý mọi vấn đề hiệu năng | DB, thuật toán hoặc retry vẫn là điểm nghẽn | Đo saturation, phân tích bottleneck và tối ưu ứng dụng |
| Bật deny toàn tổ chức ngay lập tức | Làm gián đoạn môi trường cũ và automation | Kiểm kê, thử hẹp, theo dõi rồi mở rộng |

## 12. Bài thực hành: quản trị nền tảng đặt chỗ

**Đề bài:** hệ thống tìm kiếm cần xử lý đỉnh 600 request/giây. Một instance thực nghiệm đạt 40 request/giây tại SLO yêu cầu; dự phòng bằng cách thêm 20% số instance cần thiết. Rolling deployment có thể dùng thêm 6 instance tạm. Nhóm cần triển khai ở một vùng chính và có phương án DR vùng khác. Ngân sách giả định là 15.000 USD/tháng; dữ liệu khách hàng chỉ được xử lý ở các vùng được phê duyệt.

**Yêu cầu thực hiện:**

1. **Vẽ cấu trúc tài nguyên:** chia production, staging, development, logging/network dùng chung; giải thích ranh giới quyền, quota, policy và cost ownership.
2. **Tính capacity:** số instance ở tải đỉnh, thêm headroom và rollout; lập danh mục những quota khác vẫn có thể chặn triển khai dù compute đủ.
3. **Lập sáu bản ghi quota:** chọn compute, IP/network, database, hàng đợi, API và vùng DR. Với mỗi bản ghi, nêu phạm vi, mức được cấp (cần xác minh), mức dùng, owner, ngưỡng cảnh báo và hành động.
4. **Đề xuất budget:** chia ngân sách theo môi trường và giải thích cách phân bổ logging, egress, backup; thiết kế cảnh báo actual, forecast và bất thường.
5. **Đề xuất bốn policy:** hạn chế region, quyền xóa database production, kiểm soát endpoint công cộng và chuẩn nhãn chi phí; ghi cơ chế thực thi, kiểm chứng và ngoại lệ.
6. **Diễn tập:** mô phỏng autoscaler không tạo được máy vì quota và khôi phục DR bị policy chặn. Đo thời gian phát hiện, tác động, xử lý và khả năng đạt mục tiêu phục hồi.
7. **Ghi quyết định kiến trúc:** nêu lựa chọn, rủi ro còn lại, người phê duyệt, các kiểm thử bắt buộc và ngày xem lại.

### Tiêu chí đánh giá

| Tiêu chí | Dấu hiệu đạt |
| --- | --- |
| Tính chính xác về quota | Phân biệt phạm vi và loại quota; tính đúng 15 instance, mục tiêu 18 có headroom và 24 trong rollout minh họa |
| Phù hợp độ tin cậy | Có kiểm tra DR riêng, giới hạn phụ thuộc, kịch bản mất vùng và thử phục hồi |
| Quản trị được | Có owner, ngưỡng cảnh báo, runbook và quy trình tăng quota/ngoại lệ |
| Tài chính rõ ràng | Actual và forecast, chi phí dùng chung, kịch bản cao điểm/sự cố, cảnh báo không bị nhầm là chặn chi phí |
| Bảo mật | Policy áp đúng phạm vi, có bằng chứng kiểm thử và đường xử lý hành động hợp lệ bị từ chối |
| Khả năng truy vết | Kiểm soát liên kết với yêu cầu nghiệp vụ, chất lượng hoặc ràng buộc đã phê duyệt |

## 13. Checklist trước khi đưa vào production

- [ ] Xác định cấu trúc tài khoản/dự án/môi trường và owner của từng nhóm tài nguyên.
- [ ] Ghi đầy đủ quota quan trọng ở đúng phạm vi và vùng, biết quota nào có thể tăng.
- [ ] Dự báo nhu cầu bình thường, đỉnh, rollout, failover và khôi phục dữ liệu.
- [ ] Có ngưỡng cảnh báo quota và quy trình tăng hạn mức hoặc kế hoạch xử lý khi bị từ chối.
- [ ] Có budget thực tế/dự báo theo owner, chính sách phân bổ chi phí chung và cảnh báo bất thường.
- [ ] Không nhầm budget alert với giới hạn chi tiêu cứng.
- [ ] Có quy tắc về dữ liệu, region, IAM, mạng, audit, nhãn và tài nguyên theo rủi ro.
- [ ] Đã kiểm thử các policy với thao tác hợp lệ, bất hợp lệ, triển khai và DR.
- [ ] Có ngoại lệ được phê duyệt, có thời hạn, có audit và cách thu hồi.
- [ ] Đã kết hợp kiểm tra IaC/CI/CD, kiểm tra drift và hoạt động giám sát sau triển khai.
- [ ] Đã ghi nhận đánh đổi về reliability, security, performance, cost và operations.

**Điểm cốt lõi:** quota trả lời **"có thể dùng tối đa bao nhiêu?"**, budget trả lời **"chi tiêu so với mục tiêu thế nào?"**, còn chính sách tổ chức trả lời **"điều gì được phép và phải tuân thủ?"**. Kết hợp đúng cả ba theo ranh giới tài nguyên, có dữ liệu đo, owner, cảnh báo, bằng chứng kiểm thử và quy trình ngoại lệ sẽ giúp kiến trúc đám mây **mở rộng, vận hành và khôi phục có kiểm soát**.
