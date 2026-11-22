# Kiểm thử chịu lỗi bằng Azure Chaos Studio

## 1. Vì sao cần chủ động tạo lỗi?

Một ứng dụng chạy trên Azure có thể vượt qua kiểm thử chức năng và hiệu năng nhưng vẫn ngừng phục vụ khi một máy ảo, tiến trình, đường mạng hoặc dịch vụ phụ thuộc gặp sự cố. Những lỗi ấy thường chỉ xuất hiện trong thực tế, khi hệ thống chịu tải, có truy cập đồng thời và có các thành phần phụ thuộc nhau.

**Chaos engineering** là phương pháp đưa một tác động gây lỗi **có kiểm soát** vào hệ thống, quan sát hành vi thực tế và kiểm chứng giả thuyết về khả năng chịu lỗi. Mục tiêu không phải làm hệ thống hỏng nhiều nhất có thể, mà là khám phá điểm yếu khi phạm vi tác động còn nhỏ và có thể xử lý.

**Azure Chaos Studio** là dịch vụ Azure giúp định nghĩa và thực thi các *chaos experiment* trên những loại tài nguyên và *fault* được hỗ trợ. Một thí nghiệm có thể mô phỏng việc ngừng một máy ảo hoặc một loại lỗi khác trong thư viện fault của dịch vụ, sau đó nhóm vận hành đối chiếu số liệu ứng dụng với tiêu chí đã định.

Trong một kiến trúc Azure gồm subscription, resource group, Microsoft Entra ID, mạng ảo, compute, storage và database, khả năng chịu lỗi không chỉ đến từ việc bật nhiều replica. Nó còn phụ thuộc vào health probe, đường chuyển lưu lượng, retry, timeout, quyền truy cập, dữ liệu nhất quán, cảnh báo và runbook khôi phục. Chaos Studio giúp **kiểm chứng** các cơ chế ấy bằng thực nghiệm.

Sau bài học, bạn có thể:

- Phân biệt chaos engineering, kiểm thử tải, kiểm thử khôi phục thảm họa và kiểm thử chức năng.
- Giải thích các thành phần của Chaos Studio: experiment, target, capability, fault, step, branch và managed identity.
- Xác định trạng thái ổn định (*steady state*), giả thuyết, phạm vi tác động (*blast radius*) và điều kiện dừng an toàn.
- Thiết kế và thực hiện thí nghiệm ngừng một VM thử nghiệm trong hệ thống có dự phòng, đo kết quả với Azure Monitor/Application Insights.
- Phân tích kết quả theo SLI/SLO, thời gian phát hiện, thời gian phục hồi và giới hạn của RTO/RPO.
- Xây quy trình mở rộng từ môi trường lab sang staging và production có kiểm soát.

## 2. Chaos engineering kiểm tra điều gì?

Một **giả thuyết chịu lỗi** phải có thể bác bỏ bằng số liệu. Ví dụ:

> Khi một trong hai VM phục vụ API bị ngừng, Azure Load Balancer loại VM không khỏe khỏi vòng phân phối, và ít nhất 99,5% yêu cầu đọc hợp lệ vẫn thành công trong giai đoạn kiểm thử.

Giả thuyết này tốt hơn câu “hệ thống có high availability” vì nêu rõ sự cố, điều kiện và kết quả đo. Nếu lưu lượng quá thấp, telemetry thiếu hoặc tỷ lệ thành công không đạt, ta không thể kết luận hệ thống chịu lỗi như mong đợi.

| Loại kiểm thử | Câu hỏi trả lời | Điểm khác |
| --- | --- | --- |
| Unit/integration test | Hàm, API và thành phần tích hợp có cho kết quả đúng không? | Chủ yếu kiểm tra logic trong điều kiện có thể dự đoán |
| Load/performance test | Ứng dụng xử lý bao nhiêu tải, độ trễ tăng thế nào? | Tập trung vào tải và năng lực xử lý |
| **Chaos experiment** | Khi một phụ thuộc hoặc thành phần lỗi, dịch vụ thực tế có tiếp tục đáp ứng mục tiêu không? | Cố ý tạo fault và quan sát phản ứng đầu cuối |
| Backup/restore test | Có lấy lại dữ liệu từ bản sao lưu được không? | Kiểm chứng dữ liệu, điểm khôi phục và quy trình restore |
| DR exercise | Khi có thảm họa lớn, có đạt RTO/RPO và khôi phục nghiệp vụ không? | Đánh giá toàn bộ kế hoạch phục hồi, thường có nhiều bước và nhiều đội |
| Penetration test | Có thể khai thác lỗ hổng bảo mật không? | Đánh giá an ninh, khác mục đích với lỗi độ tin cậy |

Các loại kiểm thử **bổ sung cho nhau**. Chaos Studio không tự chứng minh dữ liệu an toàn, không đo đầy đủ bảo mật và không thay thế diễn tập DR liên vùng.

### 2.1 Vòng lặp thực nghiệm

~~~mermaid
flowchart TD
    A["Quan sát trạng thái bình thường"] --> B["Nêu giả thuyết và SLI"]
    B --> C["Chọn một fault, target, blast radius"]
    C --> D["Thiết lập giám sát và điều kiện dừng"]
    D --> E["Chạy experiment"]
    E --> F["Đo khi có lỗi và sau khi lỗi kết thúc"]
    F --> G{"Đạt tiêu chí?"}
    G -->|Không| H["Khắc phục kiến trúc, cấu hình, runbook"]
    G -->|Có| I["Ghi bằng chứng, mở rộng có kiểm soát"]
    H --> A
    I --> A
~~~

Một experiment tốt tạo ra **bằng chứng**: thời điểm bắt đầu fault, tài nguyên bị ảnh hưởng, tín hiệu của ứng dụng, thời gian phát hiện, tốc độ hồi phục, quyết định dừng và kết quả cuối.

## 3. Các khái niệm trong Azure Chaos Studio

| Thành phần | Vai trò | Điều cần lưu ý |
| --- | --- | --- |
| **Experiment** | Tài nguyên Azure mô tả kịch bản thực nghiệm và lịch thực thi các fault | Có danh tính, cấu hình, quyền, bước và lịch sử thực thi; việc tạo experiment không có nghĩa đã chạy |
| **Target** | Tài nguyên hoặc đối tượng được Chaos Studio bật khả năng nhắm tới | Phải chủ động bật target; chọn chính xác resource ID và môi trường |
| **Capability** | Cho phép áp dụng một loại fault cụ thể lên target | Chỉ bật fault cần thử, theo danh sách tính năng được hỗ trợ của target |
| **Fault** | Hành động gây lỗi như ngừng VM hoặc mô phỏng bất ổn mạng khi loại target hỗ trợ | Mỗi fault có tham số, giới hạn, tác động và yêu cầu riêng |
| **Step** | Một giai đoạn trong experiment | Có thể sắp xếp nhiều giai đoạn theo thứ tự |
| **Branch** | Một nhánh thực thi trong step | Các branch có thể thực thi song song; cần kiểm soát tác động cộng dồn |
| **Action** | Thao tác trong branch, ví dụ một fault với tham số cụ thể | Thời lượng và hành vi sau khi kết thúc tùy fault |
| **Managed identity / RBAC** | Cấp quyền cho experiment thực hiện tác động lên resource | Cần quyền đúng phạm vi; không tự có quyền vì cùng subscription |

Tên và lựa chọn hiển thị trong Azure Portal có thể thay đổi theo cập nhật dịch vụ. Thư viện fault, SKU/region được hỗ trợ và yêu cầu cấu hình của từng target cũng có thể thay đổi. **Chỉ lựa chọn fault xuất hiện là tương thích với tài nguyên của bạn sau khi đối chiếu các điều kiện hỗ trợ và tài liệu dịch vụ hiện hành**.

### 3.1 Service-direct fault và agent-based fault

Chaos Studio có hai mô hình gây lỗi chính:

**Service-direct**: Chaos Studio làm việc với API/control plane của dịch vụ Azure đích. Ví dụ phù hợp để học là fault mô phỏng ngừng một Azure VM khi fault đó được thư viện và cấu hình hiện tại hỗ trợ. Không cần cài agent Chaos Studio trong guest chỉ để sử dụng một service-direct fault; cần cấp quyền điều khiển tài nguyên phù hợp.

**Agent-based**: một agent hoặc thành phần hỗ trợ chạy gần hệ thống đích thực hiện các thao tác bên trong môi trường chạy, chẳng hạn loại tác động tới CPU, bộ nhớ, network hoặc process trên nền tảng được hỗ trợ. Cần cài đặt/đăng ký agent, bật đúng capability và đáp ứng yêu cầu hệ điều hành, kết nối, quyền cũng như thời lượng fault. Không nên suy rằng mọi fault đều chạy trên mọi loại VM, AKS hay App Service.

| Tiêu chí | Service-direct | Agent-based |
| --- | --- | --- |
| Vị trí tác động | Điều khiển tài nguyên qua khả năng dịch vụ Azure hỗ trợ | Bên trong máy/khối workload có agent hỗ trợ |
| Thành phần cần chuẩn bị | Target, capability, identity và RBAC | Các yêu cầu trên cùng agent/extension và quyền runtime phù hợp |
| Ví dụ ý tưởng | Ngừng một VM của backend pool | Thêm network latency cho một workload hỗ trợ |
| Điều dễ bỏ sót | API tác động có thể gây thay đổi trạng thái thực và yêu cầu phục hồi riêng | Agent mất kết nối, fault không chạy, hoặc điều kiện hoàn nguyên phụ thuộc loại fault |

**Không nhầm “experiment báo Completed” với “dịch vụ đã khôi phục”.** Kết thúc workflow chỉ cho biết quá trình thực thi đạt trạng thái nhất định; cần xem trạng thái từng action, logs và các SLI để đánh giá thành công nghiệp vụ. Một số lỗi có thể cần bước khởi động lại, khôi phục cấu hình hoặc xử lý thủ công sau khi experiment ngừng.

## 4. Chuẩn bị kịch bản trên hệ thống giả định

Ta dùng một API đọc đơn hàng đặt trong môi trường **lab**:

- Hai Azure VM chạy cùng phiên bản API, nằm trong backend pool của Azure Standard Load Balancer.
- Load-balancing rule và health probe đã cấu hình đúng cổng/đường dẫn readiness.
- Một máy tạo lưu lượng thử nghiệm từ **ngoài backend pool**, gửi các request GET không thay đổi dữ liệu.
- Azure Monitor và Application Insights thu thập request success, duration, dependency failure và availability tests.
- Nhóm vận hành có quyền xem metrics/logs, có quyền điều khiển thí nghiệm trên **một** VM được chọn và cách khôi phục VM.

~~~mermaid
flowchart LR
    G["Load generator / synthetic client"] --> LB["Azure Load Balancer"]
    LB --> VM1["VM-A: API"]
    LB --> VM2["VM-B: API"]
    VM1 --> DB["Data service (phục vụ đọc)"]
    VM2 --> DB
    VM1 --> MON["Application Insights"]
    VM2 --> MON
    CS["Chaos Studio"] -. "Fault lên VM-A" .-> VM1
~~~

Giả định vùng dữ liệu, database và đường truy cập vẫn khỏe. Thí nghiệm này đo khả năng chịu lỗi **một VM**, chưa kiểm chứng mất availability zone, region hoặc database. Nếu API phụ thuộc duy nhất một database không dự phòng, kết quả tốt khi ngừng VM không có nghĩa hệ thống chịu được lỗi database.

### 4.1 Đặt tiêu chí trước khi chạy

Ví dụ chọn các mục tiêu sau **chỉ cho bài lab**, không phải SLA sản phẩm Azure:

| Đại lượng | Trước fault (baseline) | Trong và sau fault | Điều kiện đạt |
| --- | --- | --- | --- |
| Tỷ lệ request tốt | Đủ mẫu, ổn định gần 100% | Quan sát mỗi phút; xem cả lỗi tạm thời | Tổng tỷ lệ tốt ≥ **99,5%** trong cửa sổ fault + phục hồi |
| Độ trễ p95 | Ví dụ dưới 200 ms | Có thể tăng khi một VM mất | p95 trong giai đoạn ổn định sau chuyển tải ≤ **500 ms** |
| Health probe | VM-A và VM-B đều healthy | VM-A bị loại, VM-B vẫn healthy | Request không tiếp tục bị đưa tới VM-A khi probe đánh dấu không khỏe |
| Phát hiện sự cố | Cảnh báo hoạt động | Phát hiện VM-A ngừng hoặc SLI suy giảm | Cảnh báo trong **≤ 2 phút** nếu đường đo và tần suất hỗ trợ |
| Thời gian hồi phục | API đáp ứng bình thường | Từ lúc fault tác động đến lúc request tốt trở lại ổn định | **≤ 3 phút** cho tình huống một VM lỗi |
| Toàn vẹn dữ liệu | Có dữ liệu kiểm thử nhất quán | Không ghi/chỉnh sửa dữ liệu trong thử nghiệm GET | Không có dữ liệu thay đổi do test |

Định nghĩa **request tốt**: yêu cầu GET hợp lệ, được phục vụ đúng dữ liệu và trong thời gian chấp nhận. Không tính health probe vào traffic người dùng. Nếu chỉ dựa vào HTTP 200 mà dữ liệu trả sai, phép đo chưa đủ tin cậy.

Phải đủ tải để quan sát: nếu trong thí nghiệm chỉ có 20 request, **một lỗi** khiến tỷ lệ thành công là 95% và có độ biến động lớn. Chọn thời gian và tải phù hợp rồi ghi rõ cỡ mẫu trước khi chạy.

## 5. Thiết kế phạm vi và điều kiện dừng an toàn

Chaos experiment có thể gây gián đoạn thật. Trước khi bật target hay bắt đầu experiment:

1. **Phạm vi**: chỉ VM-A trong resource group lab, đúng subscription và region. Không chọn nhầm backend pool, VM-B hoặc một resource group production.
2. **Giới hạn thời gian**: fault ngắn, chẳng hạn 2 phút, theo cấu hình hỗ trợ của fault được chọn. Mốc thời gian là ví dụ; giới hạn hợp lệ phụ thuộc capability.
3. **Điều kiện dừng**: nếu tỷ lệ request tốt xuống dưới 98% liên tục 2 phút, mất cả hai backend, xuất hiện sai dữ liệu hoặc cảnh báo nghiêm trọng ngoài dự kiến thì dừng và thực hiện runbook an toàn.
4. **Người chịu trách nhiệm**: có người theo dõi dashboard, người có quyền dừng experiment và người có quyền khởi động/khôi phục VM.
5. **Khả năng phục hồi**: biết trước việc fault có tự hoàn nguyên hay không, thao tác restart, health check và khả năng gỡ target/disable capability khi cần.
6. **Dữ liệu thử**: request an toàn, không dùng thông tin khách hàng thật hoặc phát sinh đơn hàng/thanh toán thật.
7. **Phụ thuộc bên ngoài**: thông báo cho đội chịu trách nhiệm database, mạng và giám sát nếu cần; tránh trùng thời điểm bảo trì.

**Điều kiện dừng của nhóm không tự trở thành tính năng dừng theo SLI trong Chaos Studio.** Nếu thí nghiệm không tích hợp tự động hóa giám sát hoặc gate riêng, người trực phải chủ động quan sát và yêu cầu dừng. Hơn nữa, **dừng experiment không bảo đảm mọi tác động đã được hoàn nguyên ngay**.

Một bảng đăng ký thí nghiệm dễ review:

~~~yaml
# Đặc tả kế hoạch thử nghiệm để nhóm review.
# Đây là ví dụ tài liệu YAML, KHÔNG PHẢI schema Azure Chaos Studio để deploy.
experiment_id: lab-single-vm-failure
business_journey: "GET /orders/{id}"
scope: "rg-chaos-lab, VM-A only"
hypothesis: "LB removes unhealthy VM-A; service continues on VM-B"
fault:
  category: service-direct
  effect: "stop VM-A (only if supported capability is enabled)"
  planned_duration: "2 minutes"
traffic:
  source: "external synthetic client"
  load: "known constant rate; record request count"
success_conditions:
  success_rate: ">= 99.5% over fault + recovery window"
  recovery: "<= 3 minutes for this scenario"
abort_conditions:
  - "Both backends unhealthy"
  - "Success rate < 98% for 2 continuous minutes"
  - "Any unexpected data integrity impact"
cleanup:
  - "Ensure VM-A running"
  - "Verify both backends healthy"
  - "Compare SLI and publish evidence"
~~~

Không đưa file kế hoạch trên trực tiếp vào REST API Chaos Studio. Nó dùng để review giả thuyết trước khi điền thông số tương ứng trong Portal hoặc khai báo experiment theo schema được hỗ trợ.

## 6. Chuẩn bị Azure Chaos Studio

### 6.1 Xác định subscription, khu vực và điều kiện hỗ trợ

Người quản trị kiểm tra target VM và dịch vụ Chaos Studio có hỗ trợ region, fault, hệ điều hành/SKU và cách kích hoạt mong muốn. Khả năng hỗ trợ thay đổi theo thời gian; phải đối chiếu **fault library và điều kiện hiện hành** của Azure Chaos Studio cho resource thực tế.

Lệnh Azure CLI sau **chỉ đọc** cấu hình subscription và tình trạng đăng ký resource provider:

~~~bash
az account show --query "{subscription:id,name:name,tenantId:tenantId}" -o table
az provider show --namespace Microsoft.Chaos \
  --query "{namespace:namespace,registrationState:registrationState}" -o table
~~~

Nếu provider chưa được đăng ký, người có quyền có thể thực hiện:

~~~bash
# Thao tác quản trị: đăng ký resource provider trên subscription thật.
az provider register --namespace Microsoft.Chaos
~~~

Lệnh register **thay đổi cấu hình subscription**; nó không phải một fault, nhưng cần quản trị đúng quyền. Đồng thời kiểm tra chính sách Azure Policy, resource lock, quota và networking có ảnh hưởng đến experiment hoặc agent.

### 6.2 Bật target và capability

Trên Azure Portal:

1. Mở **Azure Chaos Studio** và khu vực **Targets** (tên màn hình có thể thay đổi).
2. Chọn chính xác VM-A của lab; kiểm tra resource ID, subscription, resource group và region.
3. Bật target với kiểu tương ứng. Đối với thí nghiệm này, chọn **service-direct target** nếu VM shutdown fault đang được hỗ trợ.
4. Chọn **capability** dành cho kiểu fault định thử. Tránh bật toàn bộ fault không sử dụng.
5. Xác nhận trạng thái target/capability đã sẵn sàng và kiểm tra lại scope trước bước tạo experiment.

Việc bật target là bước cho phép Chaos Studio nhắm tới tài nguyên; **không tự động gây fault**. Nếu dùng agent-based fault trong bài nâng cao, cần thêm yêu cầu cài đặt agent/extension và xác thực kết nối theo loại target hỗ trợ.

### 6.3 Danh tính và quyền của experiment

Experiment cần danh tính và quyền thích hợp để thực hiện fault lên resource đích. Thực hành tốt:

- Dùng **managed identity** được Chaos Studio hỗ trợ cho experiment, thay vì nhúng client secret vào tài liệu hoặc mã.
- Cấp **role/permission tối thiểu** đúng theo loại fault và đúng scope tài nguyên. Một fault ngừng VM cần các quyền phù hợp để điều khiển VM; quyền đọc Azure Monitor không đủ.
- Nếu dùng role dựng sẵn hoặc custom role, xác minh danh sách thao tác theo hướng dẫn của fault và môi trường đang dùng.
- Hạn chế ai được sửa experiment, bật capability, gán role và chạy experiment. Một người chỉ có quyền xem dashboard không nhất thiết được quyền gây lỗi.
- Kiểm tra việc phân quyền sau khi tạo identity, vì role assignment có thể mất thời gian mới có hiệu lực.

Không cấp quyền rộng ở subscription nếu experiment chỉ cần tác động lên một VM lab. Nhóm nên có bản ghi phê duyệt cho experiment và nhận diện được ai khởi chạy.

## 7. Tạo và chạy experiment ngừng một VM

### 7.1 Tạo experiment qua Azure Portal

Các bước tổng quát:

1. Trong Azure Chaos Studio, mở **Experiments** và tạo một experiment mới trong resource group lab; đặt tên dễ truy vết như `exp-lab-vm-single-failure`.
2. Chọn danh tính cho experiment theo tùy chọn được hỗ trợ và cấu hình permission trên VM-A.
3. Trong trình thiết kế experiment, tạo **một step** có **một branch**; thêm **một fault action** tương ứng VM shutdown/stop được thư viện hỗ trợ.
4. Chọn target **VM-A**, capability chính xác và thời lượng ngắn hợp lệ. Ghi rõ trong tài liệu fault có tự khôi phục trạng thái hay cần restart.
5. Kiểm tra bản tóm tắt cấu hình: experiment và target phải ở đúng subscription, không có VM-B hay tài nguyên production.
6. Lưu experiment. Việc lưu cấu hình khác với thao tác **Start**.

Một số giao diện cho phép nhiều branch và nhiều fault chạy theo tổ hợp. Ở lần đầu, **chỉ dùng một fault** để kết quả dễ giải thích và giảm blast radius.

### 7.2 Thiết lập baseline

Trước khi nhấn Start:

- Xác minh **hai VM healthy** từ hệ thống LB và probe.
- Đo từ ít nhất một điểm ngoài backend pool: GET endpoint, tỷ lệ thành công, độ trễ và nội dung trả về.
- Tạo lưu lượng ổn định bằng công cụ phù hợp như Azure Load Testing hoặc một load generator được phép; không nhầm chaos experiment với công cụ tạo tải.
- Mở dashboard Azure Monitor/Application Insights, health probe, metrics VM và dependency, kiểm tra alert có đi tới đúng người trực.
- Ghi T-10 đến T0 (ví dụ 10 phút baseline), UTC timestamp, commit/release của API và cấu hình LB.

Nếu baseline đã nhiều lỗi hoặc không có telemetry, **không chạy thử để “xem sao”**: khắc phục điều kiện đo trước, tránh nhầm lỗi nền với tác động do experiment.

### 7.3 Thực thi và quan sát

1. Người trực xác nhận mọi người sẵn sàng và thông qua phạm vi/điều kiện dừng.
2. Bắt đầu experiment và ghi **T0 = thời điểm fault thật sự bắt đầu tác động**, tách khỏi thời điểm bấm Start.
3. Quan sát lần lượt trạng thái action, VM-A, health probe, traffic của VM-B, số request thành công và độ trễ từ synthetic client.
4. Nếu đạt điều kiện dừng, yêu cầu dừng experiment và thực hiện quy trình khôi phục; không phụ thuộc hoàn toàn vào hành vi tự rollback của fault.
5. Khi fault hết thời lượng, xác nhận **VM-A thật sự Running**, app process hoạt động và LB probe đưa backend trở lại healthy. Khôi phục thủ công nếu fault đó yêu cầu.
6. Tiếp tục đo một khoảng sau fault để phát hiện lỗi đọng, queue backlog, rò rỉ kết nối hoặc một backend chưa hồi phục.

Chỉ đánh giá PASS khi giả thuyết về **người dùng** được hỗ trợ bằng telemetry đủ dữ liệu; experiment execution thành công chỉ là một phần bằng chứng.

### 7.4 Trạng thái nào cần phân biệt?

| Dữ kiện | Ý nghĩa | Có đủ để kết luận PASS? |
| --- | --- | --- |
| Experiment ở trạng thái hoàn tất | Engine đã kết thúc quy trình chạy | Không |
| Fault action báo thực thi thành công | Tác động được kích hoạt theo cơ chế fault | Chưa |
| VM-A ngừng theo quan sát | Có bằng chứng fault ảnh hưởng đúng target | Chưa |
| VM-B nhận và xử lý yêu cầu | LB có đường dự phòng hữu dụng | Chưa, phải đo SLI và nội dung |
| SLI, latency và thời gian hồi phục đạt ngưỡng | Hệ thống đáp ứng giả thuyết | Có điều kiện, nếu cỡ mẫu, telemetry và cleanup hợp lệ |
| VM-A được khởi động lại và healthy | Hệ thống lab đã về trạng thái vận hành | Bắt buộc cho hoàn tất cleanup |

## 8. Đo kết quả với Azure Monitor và Application Insights

Azure Monitor hỗ trợ metrics, logs, alert rules và workbooks. Application Insights có thể đo request, dependency, exception và distributed trace của ứng dụng, tùy kiểu tích hợp. Nếu ứng dụng dùng **workspace-based Application Insights**, dữ liệu request thường nằm trong bảng `AppRequests` của Log Analytics; hãy kiểm tra schema thật.

### 8.1 KQL: tỷ lệ thành công và độ trễ theo phút

Ví dụ đo API giả định có `AppRoleName == "orders-read-api"`, lấy cửa sổ 60 phút gần nhất:

~~~kusto
let observationWindow = 60m;
AppRequests
| where TimeGenerated >= ago(observationWindow)
| where AppRoleName == "orders-read-api"
| where Name contains "/orders"
| where Name !contains "/health"
| summarize
    Eligible = sum(ItemCount),
    Good = sumif(ItemCount, Success == true),
    P95LatencyMs = percentile(DurationMs, 95)
  by bin(TimeGenerated, 1m)
| extend
    SuccessRatePct = iff(
        Eligible == 0,
        real(null),
        100.0 * todouble(Good) / todouble(Eligible)
    )
| project TimeGenerated, Eligible, Good, SuccessRatePct, P95LatencyMs
| order by TimeGenerated asc
~~~

**Cách đọc:**

- `Eligible` là số request ước tính từ `ItemCount` khi telemetry có sampling; cần hiểu cách sampling trước khi dùng làm quyết định SLO.
- `Success` phụ thuộc instrumentation. Với request GET đơn hàng, HTTP 404 hợp lệ hoặc nghiệp vụ trả sai dữ liệu cần được xét theo định nghĩa SLI cụ thể.
- `P95LatencyMs` được tính trên các dòng request quan sát được; nếu sampling hoặc phân phối tải không đồng đều, percentile có thể bị sai lệch. Hãy kiểm tra cách đo ở tầng edge hoặc dùng nguồn telemetry thích hợp.
- Truy vấn theo route chỉ là ví dụ; `Name` trong môi trường thực có thể được chuẩn hóa hoặc khác pattern trên.
- **Không có request** không phải bằng chứng 100% thành công. Nếu thiếu log đúng lúc VM lỗi, cần đối chiếu load generator và metric LB.

Để so sánh trước/trong/sau, nên dùng timestamp chính xác từ experiment/fault logs. Thí dụ, các mốc thực tế được ghi dưới dạng UTC:

~~~text
13:50 - 14:00  Baseline: chưa gây fault
14:00 - 14:02  VM-A chịu tác động fault
14:02 - 14:07  Phục hồi và quan sát ổn định
~~~

Chỉnh bộ lọc thời gian của truy vấn để đối chiếu đúng các khoảng; không dùng thời điểm click Start thay cho lúc fault thực sự xảy ra.

### 8.2 KQL: lỗi phụ thuộc có tăng không?

Nếu ứng dụng gửi dependency telemetry:

~~~kusto
AppDependencies
| where TimeGenerated >= ago(60m)
| where AppRoleName == "orders-read-api"
| summarize
    Calls = sum(ItemCount),
    FailedCalls = sumif(ItemCount, Success == false)
  by Target, bin(TimeGenerated, 1m)
| extend
    DependencyFailurePct = iff(
        Calls == 0,
        real(null),
        100.0 * todouble(FailedCalls) / todouble(Calls)
    )
| order by TimeGenerated asc
~~~

Nhìn vào dependency giúp phát hiện các lỗi không trực tiếp hiện ở tỷ lệ HTTP: retry tăng, database connection pool bị cạn, request chậm do timeout hay lỗi ở tầng thứ ba. Cần có tracing/correlation để biết một yêu cầu người dùng bị ảnh hưởng bởi dependency nào.

### 8.3 Bằng chứng bổ sung ngoài KQL

| Nguồn | Cần ghi nhận |
| --- | --- |
| Chaos Studio experiment run | Thời gian, trạng thái action, fault/target, thông báo lỗi, người chạy |
| Azure VM metrics / Activity Log | Thời điểm VM-A bị tác động, trạng thái máy và thao tác điều khiển |
| Load Balancer metrics / health probe | Backend healthy/unhealthy và biến động phân phối |
| Azure Monitor/Application Insights | SLI request, latency, exception, dependency, tracing |
| Load generator/synthetic client | Số request đã gửi, thời gian timeout, HTTP status, tính đúng kết quả |
| Alerting / incident record | Thời gian phát hiện, cảnh báo tới người trực, phản ứng và quyết định dừng |
| Runbook cleanup | Thời gian VM-A trở lại healthy, kiểm tra hậu sự cố |

**Một thử nghiệm có thể hợp lệ về mặt kỹ thuật nhưng không hợp lệ về mặt đo lường** nếu thiếu baseline, không có traffic, mất telemetry hoặc lỗi không thực sự được đưa vào. Khi đó kết luận nên là **INCONCLUSIVE**, không báo PASS.

## 9. Chấm kết quả: PASS, FAIL hay INCONCLUSIVE?

Giả định kết quả minh họa (không phải dữ liệu Azure thực):

| Chỉ tiêu | Quan sát | Ngưỡng đã đặt | Kết luận |
| --- | --- | --- | --- |
| Fault trúng VM-A | Có, VM-B vẫn healthy | Chỉ VM-A bị tác động | PASS |
| Tỷ lệ request tốt trong fault + recovery | 99,2% | ≥ 99,5% | **FAIL** |
| p95 sau khi LB hoàn thành chuyển tải | 420 ms | ≤ 500 ms | PASS |
| Phát hiện sự cố | 75 giây | ≤ 2 phút | PASS |
| Phục hồi trải nghiệm ổn định | 3 phút 20 giây | ≤ 3 phút | **FAIL** |
| Cleanup VM-A | VM chạy lại, backend healthy | Phải được xác nhận | PASS |

Kết luận tổng thể là **FAIL giả thuyết độ tin cậy**, dù experiment có thể chạy đúng. Cần tìm nguyên nhân:

1. Health probe mất quá nhiều thời gian để nhận diện VM-A không khỏe?
2. VM-B có đủ CPU, bộ nhớ, kết nối database và giới hạn concurrent request để nhận toàn bộ tải?
3. Client retry sai, timeout quá ngắn hoặc không idempotent khiến lỗi tăng?
4. Connection pool, session state hoặc sticky sessions khiến một phần người dùng gắn với VM-A?
5. Traffic generator hoặc instrumentation có bị lỗi, gây sai số hoặc làm giả tạo tình trạng xấu?

Sau khi sửa cấu hình hoặc kiến trúc, chạy lại **cùng một thí nghiệm được phiên bản hóa**, so sánh dữ liệu theo cùng SLI và khối lượng tải. Không sửa ngưỡng chỉ để kết quả thành PASS sau khi nhìn thấy thất bại.

### 9.1 Đo thời gian phục hồi cho fault một VM

Đặt các mốc:

- T0: fault bắt đầu ảnh hưởng VM-A hoặc request.
- T1: Azure Monitor tạo cảnh báo hoặc người trực nhận ra lỗi.
- T2: LB loại VM-A và tỷ lệ request tốt trở lại ngưỡng đã quy định.
- T3: VM-A chạy lại và cả hai backend healthy.

Trong bài lab, mục tiêu có thể là **T2 − T0 ≤ 3 phút**. T3 có thể trễ hơn nếu một VM chưa trở lại pool, nhưng cần kiểm tra và đóng cleanup. Tách hai mốc giúp không nhầm **phục hồi chức năng cho người dùng** với **phục hồi đầy đủ dư thừa tài nguyên**.

## 10. Kết nối với SLI/SLO, RTO/RPO

Các phép đo trong chaos experiment cần liên hệ với mục tiêu kinh doanh:

**SLI/SLO** đo chất lượng dịch vụ trong cửa sổ thời gian được định nghĩa. Ví dụ SLO 99,9% request tốt trong rolling 28 ngày cho phép tỷ lệ request xấu 0,1%. Một thí nghiệm lỗi có thể tiêu thụ error budget, nhất là khi chạy dưới tải cao hoặc trên production.

~~~text
ErrorBudgetRequests = EligibleRequests × (1 − SLOTarget)
BudgetConsumed      = BadRequestsDuringWindow / ErrorBudgetRequests
~~~

Ví dụ nếu có 500.000 eligible request trong cửa sổ, SLO 99,9% thì budget là 500 request xấu. Một chaos experiment tạo thêm 120 request xấu sẽ tiêu thụ 24% budget của cửa sổ theo dữ liệu giả định; nếu có lỗi khác, ngân sách còn lại thấp hơn. Không tự loại trừ request lỗi do chaos experiment khỏi SLO trừ khi cách tính đó đã được phê duyệt và công khai trước.

**RTO** định nghĩa giới hạn thời gian để dịch vụ phục hồi sau kịch bản gián đoạn. Thí nghiệm VM-A cho phép đo một chỉ số phục hồi theo tình huống **mất một VM**, nhưng kết quả không chứng minh RTO khi mất region hoặc database.

**RPO** là giới hạn mất dữ liệu theo thời gian. Một experiment ngừng VM của API stateless **không đo được RPO của Azure SQL hay hệ thống lưu trữ**. Muốn kiểm chứng RPO, phải chọn kịch bản dữ liệu phù hợp, lưu các mốc commit nhất quán, thực hiện backup/restore hoặc failover được phê duyệt và đối soát giao dịch.

| Mục tiêu | Kết quả từ thí nghiệm VM-A | Điều vẫn cần kiểm chứng |
| --- | --- | --- |
| SLI/SLO | Đo thành công, độ trễ, lỗi trong và sau fault | Cửa sổ dài hơn, nhiều loại sự cố, traffic thực |
| RTO một VM | Đo T2 − T0 đến khi API phục vụ ổn định | Giờ cao điểm, mất nhiều VM, lỗi mạng và dependency |
| RTO mất region | Chưa được kiểm chứng | Điều phối DR liên vùng, DNS/route, database, identity |
| RPO dữ liệu | Chưa được kiểm chứng | Replication lag, backup/PITR, tính nhất quán và đối soát |

Như vậy, chaos engineering tạo bằng chứng cho **một giả thuyết có phạm vi xác định**. Không mở rộng kết luận “chịu lỗi một VM” thành “chịu mọi loại thảm họa”.

## 11. Bài nâng cao: gây lỗi latency cho một dependency

Sau khi thí nghiệm service-direct trên VM an toàn và có khả năng quan sát tốt, có thể xem xét một fault dạng **network latency** qua cơ chế agent-based **nếu loại target, agent, hệ điều hành và fault đó được Chaos Studio hỗ trợ**.

Ví dụ giả thuyết:

> Khi độ trễ kết nối từ một backend tới dependency tăng thêm 300 ms trong 2 phút, API trả lỗi có kiểm soát, không tạo request treo vô hạn và không làm cạn connection pool; p95 của đường đọc không vượt quá ngưỡng đã định sau khi hệ thống ổn định.

Các bước thiết kế:

1. Chọn một backend hoặc phạm vi traffic nhỏ. Đừng áp fault mạng lên cả cụm cùng lúc khi chưa có thử nghiệm nhỏ.
2. Cấu hình **timeout** của HTTP client và dependency, retry có giới hạn với exponential backoff/jitter, circuit breaker nếu phù hợp và idempotency cho thao tác ghi.
3. Tách health/readiness probe khỏi kiểm tra sâu có thể làm cả cụm bị đánh dấu unhealthy khi một dependency chậm.
4. Bật agent-based target/capability đúng kiểu được hỗ trợ; xét kỹ quyền cài đặt, kết nối và tác động ở host/container.
5. Theo dõi request duration, dependency duration, số retry, số connection và hàng đợi, không chỉ CPU.
6. Chạy fault ngắn, kiểm tra điều kiện dừng và bảo đảm không còn shaping/latency sau khi experiment hoàn tất.

**Không nên cấu hình retry vô hạn** để che lỗi. Nếu mọi backend retry đồng thời, hệ thống có thể khuếch đại sự cố bằng *retry storm*. Chaos test cần kiểm tra rằng giới hạn retry và timeout bảo vệ tổng thể.

Một tình huống khác có giá trị là mô phỏng một thành phần data path bị chậm hoặc không truy cập được, nhưng chỉ chọn fault đã được hỗ trợ và lên kế hoạch khôi phục dữ liệu. Những fault có khả năng gây mất dữ liệu hoặc quyền truy cập diện rộng cần được đánh giá nghiêm ngặt hơn fault một VM lab.

## 12. Đưa chaos testing vào quy trình vận hành

### 12.1 Tăng phạm vi theo từng vòng

Một lộ trình thực tế:

| Cấp độ | Môi trường | Phạm vi thử | Điều kiện mở rộng |
| --- | --- | --- | --- |
| 1 | Lab độc lập | Một VM, một fault, tải tổng hợp | Thấy fault thật; telemetry, cleanup và runbook đạt |
| 2 | Staging tương đồng production | Một instance, lỗi mạng hoặc dependency được hỗ trợ | Kiến trúc, config và giám sát đủ tương đồng; giả thuyết đạt |
| 3 | Production giới hạn | Một instance/nhóm canary, giờ đã phê duyệt, có trực ca | SLO còn error budget, blast radius nhỏ, có kill switch/runbook |
| 4 | Kiểm thử có lịch và kịch bản rộng hơn | Nhiều loại fault nhưng từng đợt được kiểm soát | Có bằng chứng ổn định và review sau mỗi lần; không chạy song song tùy tiện |

Mỗi bước cần điều kiện dừng, người chịu trách nhiệm, quyền giới hạn và khả năng phục hồi thật. Nếu một fault trên lab cho thấy điểm lỗi đơn, **khắc phục và kiểm chứng lại** trước khi nghĩ tới thử nghiệm production.

### 12.2 Tích hợp với IaC và CI/CD

Có thể quản lý cấu hình experiment bằng Infrastructure as Code (ARM/Bicep hoặc quy trình API được hỗ trợ) để review và truy vết; chú ý kiểm tra schema tài nguyên, API version và fault parameters của phiên bản đang sử dụng. Không nên sao chép cấu hình fault từ ví dụ cũ sang production mà không kiểm tra tài nguyên đích và quyền.

Một pipeline vận hành có thể gồm các giai đoạn:

~~~mermaid
flowchart LR
    A["Deploy bản thử nghiệm"] --> B["Smoke test + baseline"]
    B --> C{"Đạt điều kiện chạy?"}
    C -->|Không| D["Dừng pipeline"]
    C -->|Có| E["Phê duyệt chaos test"]
    E --> F["Chạy Chaos Studio experiment"]
    F --> G["Thu thập metrics + xác minh cleanup"]
    G --> H{"Đạt SLI và recovery?"}
    H -->|Không| I["Tạo issue + khắc phục"]
    H -->|Có| J["Ghi report + tiếp tục phát hành"]
~~~

Một experiment có thể được gọi từ automation thông qua API/SDK hoặc cách tích hợp hỗ trợ. **Phải phân biệt “gửi lệnh chạy” với “chờ chạy xong và xác nhận kết quả”**: gọi start thành công chưa có nghĩa fault đã áp đúng mục tiêu, hệ thống đã phục hồi hay SLI đạt.

Nếu đưa vào release gate, pipeline cần thu thập đủ:

- Trạng thái cuối cùng của experiment **và từng fault action**.
- Bằng chứng target thực sự chịu tác động, đúng scope.
- Cửa sổ quan sát có đủ sample/traffic và không mất telemetry.
- Ngưỡng SLI, latency và recovery được đánh giá bởi mã kiểm tra hoặc người phê duyệt rõ ràng.
- Cleanup hoàn tất; hệ thống không còn fault hoặc tài nguyên lỗi.

**Cần quyền tối thiểu và bảo vệ nhánh**: không cho pull request không tin cậy sử dụng credential hoặc managed identity có thể điều khiển tài nguyên production qua Chaos Studio.

### 12.3 Báo cáo sau thí nghiệm

Một biên bản cần có:

| Trường | Ví dụ |
| --- | --- |
| Hypothesis | Một VM lỗi thì API vẫn đạt ≥ 99,5% request tốt |
| Experiment version | `exp-lab-vm-single-failure`, commit/config version |
| Scope | Subscription, resource group, VM resource ID, region |
| Fault | Loại, tham số, thời lượng, capability |
| Timeline | T0 fault; T1 alert; T2 ứng dụng ổn định; T3 cleanup |
| Quan sát | SLI, p95, probe, số request, dependency, action logs |
| Kết luận | PASS/FAIL/INCONCLUSIVE với lý do |
| Sửa đổi | Issue, owner, hạn xử lý, thay đổi kiến trúc/runbook |
| Thử lại | Điều kiện và ngày dự kiến chạy thí nghiệm đã sửa |

Giữ báo cáo ở nơi chỉ người có quyền mới truy cập được; tài liệu có thể chứa resource ID, thông tin mạng và cách gây lỗi. Không đưa token, secret hoặc nội dung dữ liệu khách hàng vào report.

## 13. Lỗi thường gặp khi sử dụng Chaos Studio

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm được target/fault mong muốn | Loại tài nguyên, region, fault, agent hoặc điều kiện hỗ trợ không phù hợp | Kiểm tra fault library và hỗ trợ hiện hành; thay đổi loại fault/phạm vi |
| Experiment không tác động được VM | Chưa bật capability, identity thiếu quyền, sai resource ID, policy/lock ngăn thao tác | Kiểm tra target/capability, managed identity, RBAC và activity logs |
| Agent-based fault không chạy | Agent chưa sẵn sàng, kết nối/extension hoặc permission lỗi | Kiểm tra agent health và prerequisites đúng nền tảng |
| Experiment hoàn tất nhưng app vẫn lỗi | Hành vi fault cần khôi phục riêng, app chưa restart, LB probe hoặc dependency chưa hồi | Chạy runbook; đo ứng dụng đến khi healthy |
| Không thấy lỗi khi ngừng VM | Fault chưa tới đúng VM, thiếu lưu lượng, chỉ xem metrics ở VM-B, hoặc dự phòng hoạt động tốt | Xác nhận fault action, target ID, traffic và kết quả theo giả thuyết |
| Tỷ lệ request tốt thấp nhưng baseline cũng thấp | Ứng dụng chưa ổn định từ đầu hoặc lưu lượng/telemetry thiếu | Dừng đánh giá; sửa baseline và đo lại |
| Nhầm lỗi đo thành lỗi ứng dụng | Sampling, bộ lọc telemetry, mất logs, clock lệch | Đối chiếu synthetic client, ingress, experiment logs và timestamp UTC |
| VM-A không trở lại pool sau thí nghiệm | Máy chưa Running, service readiness lỗi, network/probe bị sai | Xác nhận từng lớp và cleanup; không kết luận test xong khi còn mất redundancy |

Lưu ý thêm: **Chaos Studio không tự tạo điều kiện bảo vệ kinh doanh**. Quyết định thời điểm chạy, ai được quyền, có cần approval hay không, và khi nào phải dừng là trách nhiệm của tổ chức.

## 14. Bài tập và câu hỏi tự kiểm tra

### Bài tập 1: Viết giả thuyết đủ đo lường

Hệ thống có hai VM phía sau Azure Load Balancer. Nhóm nói: “Nếu một VM lỗi, hệ thống vẫn ổn.”

Hãy viết lại câu trên thành một giả thuyết có fault, target, SLI, ngưỡng đạt, thời gian quan sát và điều kiện dừng.

**Lời giải tham khảo:** “Khi tạm dừng VM-A của lab trong 2 phút bằng fault được hỗ trợ, ít nhất 99,5% GET /orders hợp lệ trong giai đoạn fault + phục hồi vẫn thành công, p95 sau chuyển tải ≤ 500 ms, thời gian đến khi request ổn định ≤ 3 phút; dừng nếu cả hai backend unhealthy hoặc tỷ lệ thành công dưới 98% liên tục 2 phút.” Các ngưỡng chỉ là giả định; cần điều chỉnh theo baseline và tác động nghiệp vụ.

### Bài tập 2: Chấm kết quả và đưa ra quyết định

Trong 5 phút thí nghiệm, client gửi **10.000 request** GET hợp lệ. Có **9.930 request tốt**, latency p95 sau chuyển tải là 450 ms, thời gian hồi phục ổn định 2 phút 45 giây. Các ngưỡng đã đặt: tỷ lệ request tốt ≥ 99,5%, p95 ≤ 500 ms, phục hồi ≤ 3 phút.

Tính:

\[
\mathrm{SuccessRate}=\frac{9\,930}{10\,000}\times100\%=99{,}3\%.
\]

**Kết luận:** FAIL vì tỷ lệ thành công 99,3% thấp hơn 99,5%, dù latency và thời gian phục hồi đều đạt. Cần phân tích thời gian LB phát hiện health probe lỗi, năng lực VM-B và retry/timeout trước khi thử lại. Không hợp thức hóa kết quả bằng cách chỉ nhìn hai metric đạt.

### Bài tập 3: Phạm vi kiểm chứng

Giả sử experiment VM-A đạt toàn bộ chỉ tiêu. Nhóm dự định ghi trong báo cáo: “Ứng dụng đáp ứng RTO 30 phút và RPO 0 khi mất cả region.”

**Đánh giá:** Kết luận không hợp lệ. Thí nghiệm chỉ tác động một VM trong một region và không đo khôi phục dữ liệu. Để kiểm chứng RTO/RPO khi mất region, cần kịch bản DR riêng với dịch vụ tính toán, data store, replication, network, identity, tuyến truy cập, checkpoint nhất quán và giao dịch đối soát.

### Câu hỏi tự kiểm tra

1. Tại sao phải chọn SLI và baseline trước khi bắt đầu fault?
2. Khác biệt chính giữa service-direct và agent-based fault là gì?
3. Target, capability và managed identity có vai trò gì trong một Chaos Studio experiment?
4. Tại sao trạng thái Completed của experiment chưa đủ kết luận PASS?
5. Khi dừng một VM sau Load Balancer, ngoài trạng thái VM cần quan sát những gì?
6. Vì sao dừng experiment không đồng nghĩa mọi fault đã tự động hoàn nguyên?
7. Vì sao một thí nghiệm mất một VM không chứng minh RTO/RPO khi mất cả region?
8. Những điều kiện nào phải đạt trước khi mở rộng từ lab sang production?

**Kết quả cần đạt:** Bạn có thể biến một nhận định mơ hồ như “ứng dụng Azure có dự phòng” thành một **giả thuyết chịu lỗi đo được**, sử dụng Azure Chaos Studio để tạo fault trên đúng tài nguyên, đối chiếu với SLI/SLO và khôi phục hệ thống an toàn. Giá trị của chaos engineering nằm ở bằng chứng đo được, bài học rút ra và cải tiến kiến trúc sau mỗi lần thử nghiệm.
