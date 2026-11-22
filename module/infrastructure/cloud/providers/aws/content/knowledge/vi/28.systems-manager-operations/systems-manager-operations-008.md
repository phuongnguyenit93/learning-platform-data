# Maintenance Window và giới hạn ảnh hưởng thay đổi

> **Chương:** Vận hành với Systems Manager  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — khám phá hệ sinh thái AWS qua Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có giám sát, phục hồi và kiểm soát chi phí.

Một bản vá hệ điều hành, lần cập nhật agent hoặc thay đổi cấu hình có thể cần khởi động lại máy chủ, tạm rút node khỏi load balancer hoặc làm gián đoạn một dịch vụ. Nếu chạy thay đổi vào giờ cao điểm hoặc đồng thời trên toàn bộ fleet, sự cố vận hành có thể lan rộng trước khi đội ngũ kịp dừng triển khai.

AWS Systems Manager Maintenance Windows cho phép định nghĩa khoảng thời gian được phép bắt đầu các tác vụ bảo trì, chọn đúng tài nguyên đích, sắp xếp thứ tự tác vụ và đặt giới hạn concurrency/error. Bài học tập trung vào cách thiết kế cửa sổ bảo trì sao cho thay đổi diễn ra trong thời gian được phê duyệt và có phạm vi ảnh hưởng kiểm soát được.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của Maintenance Windows trong vận hành AWS.
2. Phân biệt Maintenance Windows với State Manager và Patch Manager.
3. Thiết kế lịch chạy bằng cron, rate hoặc at; hiểu timezone, start/end date và schedule offset.
4. Tính được thời điểm cutoff từ duration và cutoff hours.
5. Chọn target bằng instance ID, tag hoặc AWS Resource Group.
6. Chọn task type phù hợp giữa Run Command, Automation, Lambda và Step Functions.
7. Sắp xếp task bằng priority và hiểu tác vụ nào chạy song song.
8. Đặt `MaxConcurrency` và `MaxErrors` để giới hạn blast radius.
9. Phân biệt `CONTINUE_TASK` với `CANCEL_TASK` khi cutoff đến.
10. Thiết kế IAM service role, task permissions, logging và monitoring theo least privilege.
11. Triển khai canary, rollout theo nhóm và rollback khi có lỗi.
12. Điều tra task execution, target resolution, lỗi quyền và các lần chạy bị bỏ qua.

## 2. Maintenance Windows giải quyết vấn đề gì?

Maintenance Windows là chức năng của AWS Systems Manager dùng để lên lịch cho những hành động có thể gây gián đoạn trên managed nodes hoặc các AWS resources được hỗ trợ. Ví dụ:

- Cài đặt security patches hoặc cập nhật packages.
- Nâng cấp SSM Agent hoặc phần mềm trên máy chủ.
- Khởi động lại instance theo change window.
- Rút node khỏi load balancer, cập nhật, kiểm tra health rồi đưa node trở lại.
- Chạy Automation runbook để tạo AMI hoặc thực hiện chuỗi thay đổi tài nguyên.
- Gọi Lambda hoặc Step Functions để điều phối quy trình bảo trì.

Maintenance Window không phải một lệnh patch duy nhất. Nó là khung điều phối gồm lịch, thời lượng, target và các task đã đăng ký. Mỗi task có cấu hình riêng về loại công việc, priority, concurrency, error threshold, cutoff behavior và role thực thi.

### 2.1. Tách thời gian được phép khởi chạy khỏi thời gian tác vụ thực sự chạy

Một cửa sổ bảo trì xác định thời điểm Systems Manager được phép bắt đầu task invocation. Khi task đã bắt đầu, task có thể tiếp tục sau khi thời gian cửa sổ kết thúc. Vì vậy:

- `Duration` là thời lượng cửa sổ, không phải timeout cứng của mọi script.
- `Cutoff` là khoảng thời gian trước khi cửa sổ kết thúc mà Systems Manager ngừng lập lịch bắt đầu task mới.
- `CutoffBehavior` quyết định cách xử lý invocation đang chạy khi đến cutoff.
- Timeout của command, Automation step hoặc workflow cần cấu hình riêng.

Đừng thiết kế lịch với giả định rằng mọi process sẽ tự dừng đúng thời điểm cửa sổ đóng.

### 2.2. Các thành phần của một Maintenance Window

~~~mermaid
flowchart TD
    S["Schedule<br/>cron / rate / at"] --> W["Maintenance Window"]
    D["Duration + Cutoff"] --> W
    W --> T["Registered targets<br/>IDs / tags / Resource Groups"]
    W --> A["Registered tasks"]
    T --> A
    A --> P["Priority order"]
    P --> R["Rate controls<br/>MaxConcurrency / MaxErrors"]
    R --> X["Run Command / Automation / Lambda / Step Functions"]
    X --> M["Logs, status, alarms, EventBridge"]
~~~

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Schedule | Khi nào cửa sổ được kích hoạt? |
| Duration | Cửa sổ có hiệu lực tối đa bao lâu? |
| Cutoff | Dừng lập lịch task mới trước khi cửa sổ đóng bao lâu? |
| Targets | Resource nào có thể nhận tác vụ? |
| Tasks | Cần thực hiện hành động nào? |
| Priority | Task nào cần được lập lịch trước? |
| MaxConcurrency | Bao nhiêu target được xử lý đồng thời? |
| MaxErrors | Cho phép bao nhiêu lỗi trước khi dừng lập lịch thêm? |
| CutoffBehavior | Task invocation đang chạy xử lý thế nào khi đến cutoff? |

## 3. Khi nào dùng Maintenance Windows?

Systems Manager có nhiều công cụ vận hành với mục đích khác nhau. Chọn đúng công cụ giúp tránh dùng lịch bảo trì để giải quyết một bài toán quản lý trạng thái liên tục.

| Công cụ | Mục đích chính | Ví dụ |
| --- | --- | --- |
| Maintenance Windows | Chạy hành động theo khoảng thời gian đã định | Patch production vào cuối tuần |
| State Manager | Duy trì trạng thái cấu hình mong muốn | Đảm bảo agent hoặc cấu hình luôn ở phiên bản/quy tắc yêu cầu |
| Patch Manager | Định nghĩa patch baseline và điều phối patching | Phê duyệt security updates theo hệ điều hành |
| Automation | Chạy runbook nhiều bước trên AWS resources | Tạo AMI, restart instance, cập nhật resource |
| Run Command | Chạy command/script trên managed nodes | Kiểm tra dịch vụ, cài package, restart process |

Maintenance Windows phù hợp khi team cần kiểm soát *thời điểm* bắt đầu thay đổi, chạy nhiều task theo thứ tự và giới hạn số target được tác động.

### 3.1. Maintenance Windows và State Manager

State Manager duy trì cấu hình mong muốn và có thể áp dụng association khi phát hiện node mới hoặc trạng thái cần được duy trì. Maintenance Windows chạy các hành động trong một khoảng thời gian được chỉ định; nó không tự đảm bảo resource tiếp tục ở trạng thái mong muốn sau khi tác vụ kết thúc.

Ví dụ:

- Muốn mọi managed node luôn có SSM Agent được cấu hình theo chuẩn: cân nhắc State Manager.
- Muốn cập nhật SSM Agent vào 02:00 Chủ nhật, theo nhóm và có giới hạn lỗi: cân nhắc Maintenance Window.

State Manager phù hợp hơn cho compliance/configuration drift; Maintenance Windows phù hợp hơn cho công việc có thời điểm bắt đầu được phê duyệt.

### 3.2. Maintenance Windows và Patch Manager

Patch Manager xác định patch baseline, quy tắc phê duyệt và hoạt động vá lỗi. Maintenance Windows có thể là khoảng thời gian để đăng ký task chạy patching, ví dụ task Run Command hoặc Automation sử dụng document phù hợp.

Với triển khai patching đa account/đa Region, AWS khuyến nghị xem xét Patch Policy trong Systems Manager Quick Setup. Một Maintenance Window cho patching theo mô hình thông thường hoạt động trong một account và một Region; đừng giả định một window đơn lẻ tự điều phối toàn bộ organization.

## 4. Lập lịch: cron, rate và at

Mỗi Maintenance Window cần một schedule. Systems Manager hỗ trợ:

- **Cron:** lịch theo thời gian trong ngày/tuần/tháng.
- **Rate:** lặp theo khoảng thời gian, ví dụ mỗi 7 ngày.
- **At:** chạy một lần tại một timestamp cụ thể.

Maintenance Windows hỗ trợ cron expression sáu trường:

~~~text
cron(Minutes Hours Day-of-month Month Day-of-week Year)
~~~

Ví dụ:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `cron(0 2 ? * SUN *)` | 02:00 Chủ nhật hằng tuần |
| `cron(30 23 ? * TUE#3 *)` | 23:30 ngày thứ Ba thứ ba trong tháng |
| `cron(0 1 1 * ? *)` | 01:00 ngày đầu tiên mỗi tháng |
| `rate(7 days)` | Mỗi 7 ngày |
| `at(2026-12-06T02:00:00)` | Một lần tại timestamp chỉ định theo UTC mặc định |

Cron của Maintenance Windows hỗ trợ trường tháng và các lựa chọn day-of-week như `MON-FRI`, `TUE#3`, `6L`. Không dùng đồng thời một giá trị cụ thể trong cả day-of-month và day-of-week; trường còn lại cần là `?`.

### 4.1. Chọn timezone rõ ràng

Có thể chỉ định timezone theo định dạng IANA bằng `ScheduleTimezone`, ví dụ:

- `UTC`
- `Asia/Ho_Chi_Minh`
- `Asia/Singapore`
- `America/Los_Angeles`

Nếu lịch bảo trì theo giờ địa phương của đội vận hành, hãy khai báo timezone thay vì tự cộng/trừ giờ trong cron. Timezone và `StartDate`/`EndDate` là hai cấu hình độc lập:

- `ScheduleTimezone` xác định múi giờ để diễn giải schedule.
- `StartDate` và `EndDate` xác định khoảng thời gian mà window được phép chạy; timestamp dùng ISO-8601 và có thể mang offset riêng.

Với hệ thống chạy nhiều Region, thống nhất một chuẩn thời gian trong change calendar và ghi rõ timezone trong thông báo vận hành.

### 4.2. StartDate và EndDate

`StartDate` trì hoãn thời điểm window bắt đầu có hiệu lực. `EndDate` xác định thời điểm window ngừng hoạt động. Hai trường này không thay đổi cron/rate; chúng chỉ giới hạn giai đoạn schedule được phép chạy.

Ví dụ:

~~~bash
aws ssm create-maintenance-window \
  --name "prod-weekly-patching" \
  --description "Weekly production patching window" \
  --schedule "cron(0 2 ? * SUN *)" \
  --schedule-timezone "Asia/Ho_Chi_Minh" \
  --start-date "2026-12-01T00:00:00+07:00" \
  --end-date "2027-06-30T23:59:00+07:00" \
  --duration 4 \
  --cutoff 1 \
  --region ap-southeast-1
~~~

Trong ví dụ, lịch chạy lúc 02:00 Chủ nhật theo giờ Việt Nam trong khoảng hiệu lực đã chỉ định. Hãy kiểm tra lịch thực tế trước khi áp dụng, đặc biệt khi thay đổi timezone hoặc chuyển lịch giữa cron và rate.

### 4.3. Schedule offset

`ScheduleOffset` chỉ áp dụng cho cron, có giá trị từ 1 đến 6 ngày. Nó trì hoãn lần chạy sau ngày/giờ được cron xác định.

Ví dụ:

~~~text
cron(30 23 ? * TUE#3 *)
schedule-offset = 2
~~~

Lịch gốc là 23:30 thứ Ba thứ ba trong tháng; offset 2 khiến cửa sổ chạy lúc 23:30 sau đó hai ngày. Offset hữu ích khi cần chờ một mốc lịch khác, ví dụ vài ngày sau khi hoàn tất đợt cập nhật hoặc sau lịch phát hành.

Nếu ngày cron trong kỳ hiện tại đã qua và offset rơi vào tương lai, window có thể phải đợi đến kỳ cron tiếp theo. Đừng suy ra lần chạy đầu chỉ bằng cách cộng số ngày offset vào thời điểm hiện tại.

### 4.4. Giới hạn tần suất cron

Maintenance Windows không hỗ trợ cron schedule nhanh hơn mỗi 5 phút. Schedule offset không áp dụng cho rate hoặc at. Với các thay đổi production có rủi ro, lịch dày không thay thế được việc phê duyệt và kiểm soát blast radius.

## 5. Duration, cutoff và thời điểm window kết thúc

Khi tạo Maintenance Window, hai thông số quan trọng là:

- `Duration`: số giờ tối đa của cửa sổ, từ 1 đến 24.
- `Cutoff`: số giờ trước khi hết duration mà Systems Manager ngừng lập lịch bắt đầu task mới, từ 0 đến 23.

Thời điểm cutoff được tính:

\[
\text{Cutoff time} = \text{Window start} + \text{Duration} - \text{Cutoff}
\]

Ví dụ, window bắt đầu 22:00, `Duration = 4`, `Cutoff = 1`:

~~~text
22:00            01:00            02:00
|----------------|----------------|
Window starts    Cutoff           Window ends
                 No new tasks
~~~

Từ 22:00 đến 02:00 là khoảng duration 4 giờ. Từ 01:00 trở đi, Systems Manager không bắt đầu task invocation mới. Task đã bắt đầu có thể tiếp tục sau 02:00, tùy task type và cutoff behavior.

### 5.1. Cutoff bằng 0

`Cutoff = 0` nghĩa là không dành thêm khoảng giờ trước khi đóng window để chặn việc lập lịch task mới. Task vẫn phải bắt đầu trong thời gian cửa sổ hợp lệ. Nếu công việc thường kéo dài, hãy đặt cutoff đủ lớn để không khởi chạy task mới quá sát giờ kết thúc.

### 5.2. Duration không phải thời gian hoàn thành bắt buộc

Giả sử một patch task bắt đầu lúc 01:30, window đóng lúc 02:00 nhưng patch cần thêm 40 phút. Task có thể vẫn chạy sau 02:00 nếu cấu hình cho phép tiếp tục. Điều đó có nghĩa:

- Không nên dùng duration làm timeout cho script.
- Cấu hình timeout riêng cho Run Command/Automation/workflow. Với Run Command, `TimeoutSeconds` trong task invocation là thời gian chờ command được giao tới SSM Agent; timeout của script/command cần cấu hình trong SSM document hoặc logic chạy lệnh.
- Đặt cutoff theo thời lượng tối đa có thể cần cho task mới.
- Có kế hoạch theo dõi tác vụ còn chạy sau window.
- Nếu hệ thống không cho phép process tiếp tục sau một mốc nhất định, cần thiết kế cơ chế dừng có kiểm soát trong chính task/runbook.

### 5.3. Lập lịch không đảm bảo task hoàn tất trong cửa sổ

Maintenance Window kiểm soát thời điểm bắt đầu và lịch dispatch. Nó không đảm bảo tất cả target hoàn thành trước end time. Thời gian thực tế còn phụ thuộc:

- Số lượng target sau khi resolve tags/Resource Groups.
- `MaxConcurrency` và thời gian xử lý mỗi target.
- Số task và priority.
- SSM Agent/managed node connectivity.
- Thời gian reboot, package download và health checks.
- Thời gian chờ Automation, approval hoặc downstream service.

Trước production, đo thời gian trên một nhóm canary rồi ước lượng thời lượng cho toàn fleet.

## 6. Chọn target và kiểm soát phạm vi tài nguyên

Target quyết định task có thể tác động lên tài nguyên nào. Một task đúng nhưng target sai vẫn có thể gây outage lớn.

Maintenance Windows hỗ trợ target như:

1. **Instance IDs:** chỉ định managed node cụ thể.
2. **Tags:** chọn node theo tag key/value.
3. **AWS Resource Groups:** chọn resources theo resource group và loại tài nguyên được hỗ trợ.

Ví dụ target theo tag:

~~~text
Key=tag:Environment,Values=Production
Key=tag:Role,Values=Web
~~~

Khi có nhiều tag conditions, resource cần khớp tất cả điều kiện được khai báo trong target group. Dùng tag có ý nghĩa vận hành rõ ràng, ví dụ:

| Tag | Ví dụ | Mục đích |
| --- | --- | --- |
| `Environment` | `Production` | Tách production khỏi dev/staging |
| `Service` | `order-api` | Chọn một service cụ thể |
| `MaintenanceRing` | `canary`, `wave-1`, `wave-2` | Chia rollout theo đợt |
| `PatchGroup` | `prod-linux` | Liên kết patch baseline/group |
| `Owner` | `platform-team` | Xác định nhóm chịu trách nhiệm |

### 6.1. Chọn instance ID

Instance IDs phù hợp với một lần bảo trì nhỏ hoặc một canary cụ thể:

~~~bash
aws ssm register-target-with-maintenance-window \
  --window-id mw-0123456789abcdef0 \
  --resource-type INSTANCE \
  --targets "Key=InstanceIds,Values=i-0123456789abcdef0" \
  --name "prod-canary-node" \
  --owner-information "platform-team"
~~~

Ưu điểm là phạm vi rõ ràng và dễ review. Nhược điểm là phải cập nhật danh sách khi fleet thay đổi; nếu instance được thay thế bởi Auto Scaling, target cũ có thể không còn phù hợp.

### 6.2. Chọn bằng tag

~~~bash
aws ssm register-target-with-maintenance-window \
  --window-id mw-0123456789abcdef0 \
  --resource-type INSTANCE \
  --targets "Key=tag:Environment,Values=Production" "Key=tag:MaintenanceRing,Values=canary" \
  --name "prod-canary-ring" \
  --owner-information "platform-team"
~~~

Tag target phù hợp với fleet thay đổi thường xuyên. Khi window chạy, Systems Manager resolve các managed nodes có tag khớp. Vì số lượng target có thể thay đổi, dùng concurrency theo phần trăm khi không biết chính xác fleet size.

### 6.3. Chọn bằng Resource Group

Resource Group có thể chứa nhiều resource types được hỗ trợ. Khi target Resource Group, hãy lọc đúng resource types mà task xử lý. Nếu group chứa resource type không liên quan, task có thể ghi nhận lỗi cho những loại không được hỗ trợ trong khi vẫn chạy trên resource type hợp lệ.

Với node đang offline, Resource Group có thể giúp target theo resource membership; task chỉ thực thi được khi node có thể kết nối và nhận lệnh.

Ví dụ đăng ký Resource Group chứa EC2 instances:

~~~bash
aws ssm register-target-with-maintenance-window \
  --window-id mw-0123456789abcdef0 \
  --resource-type RESOURCE_GROUP \
  --targets "Key=resource-groups:Name,Values=prod-web-nodes" "Key=resource-groups:ResourceTypeFilters,Values=AWS::EC2::INSTANCE" \
  --name "prod-web-resource-group" \
  --owner-information "platform-team" \
  --region ap-southeast-1
~~~

`RESOURCE_GROUP` là target type của Maintenance Windows; `AWS::EC2::INSTANCE` là resource type filter của Resource Group. Hai giá trị này phục vụ hai lớp khác nhau và không thể hoán đổi cho nhau.

### 6.4. AllowUnassociatedTargets

Khi tạo window, `AllowUnassociatedTargets` quyết định task có được target managed nodes chưa đăng ký thành window target hay không:

- `false`: task cần dùng các targets đã đăng ký với window.
- `true`: task có thể chỉ định managed node IDs trực tiếp khi đăng ký task, kể cả khi node chưa nằm trong registered targets.

Chế độ `true` linh hoạt cho task chạy một lần trên một node cụ thể, nhưng làm cho danh sách targets của window khó nhìn thấy tập trung hơn. Với quy trình vận hành chuẩn, ưu tiên đăng ký target trước để review phạm vi.

### 6.5. Không dùng tag quá rộng

Trước khi đăng ký task, hãy xác nhận:

- Tag có tồn tại trên đúng managed nodes không?
- Có node production nào bị gắn nhầm `Environment=Production` không?
- Có tag key nào bị thiếu value hoặc dùng casing không thống nhất không?
- Resource Group có resource types ngoài dự kiến không?
- Target có bao gồm cả database, worker và web nodes trong cùng một đợt không?
- Có node đang trong incident hoặc maintenance khác không?

Thử target resolution bằng danh sách resource trước khi chạy task destructive. Không xem số lượng targets dự kiến là số lượng cố định nếu target dựa trên tag.

## 7. Thiết kế blast radius trước khi đăng ký task

Blast radius là phạm vi tài nguyên có thể bị ảnh hưởng nếu task lỗi hoặc thay đổi tạo ra regression. Maintenance Windows cung cấp các cơ chế giới hạn blast radius, nhưng người vận hành phải thiết kế cách sử dụng chúng.

### 7.1. Chia fleet thành rings

Một rollout an toàn thường chia thành:

| Ring | Ví dụ phạm vi | Mục tiêu |
| --- | --- | --- |
| Canary | 1 instance hoặc 1–2% fleet | Phát hiện lỗi sớm |
| Wave 1 | 5–10% fleet | Kiểm tra hành vi trên nhóm nhỏ |
| Wave 2 | 25–50% fleet | Mở rộng khi health metrics ổn định |
| Final wave | Phần fleet còn lại | Hoàn tất sau khi có đủ bằng chứng |

Tỷ lệ chỉ là ví dụ. Với service có ít instance hoặc mỗi instance giữ state quan trọng, hãy dùng số lượng nhỏ và giữ capacity dự phòng.

### 7.2. Giữ đủ capacity khi bảo trì

Nếu một service có 6 instances sau load balancer và cần giữ ít nhất 4 instances healthy, không nên chạy patch đồng thời trên 3 hoặc 4 nodes. Tính cả:

- Desired/minimum capacity của Auto Scaling Group.
- Health check grace period.
- Thời gian drain connection.
- Session affinity và workload state.
- Khả năng phục hồi khi instance không quay lại healthy.
- Capacity còn lại khi một Availability Zone gặp sự cố.

Không dùng `MaxConcurrency` thay cho capacity planning. Concurrency giới hạn số task cùng lúc; nó không biết ứng dụng cần bao nhiêu healthy nodes để duy trì SLO.

### 7.3. Chia task theo trách nhiệm

Ví dụ một quy trình patching web fleet có thể tách:

1. Pre-check: xác nhận node healthy, đủ disk và có backup/snapshot theo policy.
2. Drain: gỡ node khỏi load balancer hoặc ngừng nhận traffic.
3. Patch: áp dụng update và reboot nếu cần.
4. Validate: kiểm tra service, port, application health và version.
5. Rejoin: đưa node trở lại load balancer.

Có thể điều phối chuỗi này bằng Automation/Step Functions hoặc các task theo priority. Nếu tách thành nhiều task, hãy bảo đảm thứ tự và điều kiện health được kiểm tra rõ ràng; priority không tự tạo logic điều kiện "chỉ chạy bước sau khi bước trước thành công".

## 8. Task types được hỗ trợ

Maintenance Windows hỗ trợ bốn loại task:

| Task type | Dùng khi | Ví dụ |
| --- | --- | --- |
| `RUN_COMMAND` | Chạy SSM Command document trên managed nodes | Shell/PowerShell script, patch command, kiểm tra service |
| `AUTOMATION` | Chạy Automation runbook nhiều bước | Tạo AMI, restart instance, drain/update/rejoin |
| `LAMBDA` | Gọi Lambda function | Kiểm tra precondition hoặc tích hợp hệ thống change |
| `STEP_FUNCTIONS` | Khởi chạy Step Functions Standard workflow | Điều phối quy trình bảo trì có nhiều nhánh/điều kiện |

Maintenance Windows chỉ hỗ trợ Step Functions **Standard** workflows; Express workflows không được hỗ trợ.

### 8.1. Run Command

Run Command phù hợp với thao tác trên managed nodes như Linux shell hoặc Windows PowerShell. Task tham chiếu một SSM Command document, ví dụ `AWS-RunShellScript` hoặc `AWS-RunPowerShellScript`.

Run Command cần ít nhất một target. Nếu node không được Systems Manager quản lý hoặc không kết nối được SSM endpoints/SSM Agent, lệnh có thể ở trạng thái delivery timeout hoặc không hoàn tất.

Ví dụ đăng ký task:

~~~bash
aws ssm register-task-with-maintenance-window \
  --window-id mw-0123456789abcdef0 \
  --name "check-web-service" \
  --task-arn "AWS-RunShellScript" \
  --task-type RUN_COMMAND \
  --targets "Key=WindowTargetIds,Values=11111111-2222-3333-4444-555555555555" \
  --service-role-arn arn:aws:iam::111122223333:role/MaintenanceWindowExecutionRole \
  --priority 10 \
  --max-concurrency "10%" \
  --max-errors "1" \
  --cutoff-behavior CANCEL_TASK \
  --task-invocation-parameters '{"RunCommand":{"Parameters":{"commands":["systemctl is-active nginx"]},"TimeoutSeconds":600,"CloudWatchOutputConfig":{"CloudWatchOutputEnabled":true,"CloudWatchLogGroupName":"/ssm/maintenance"}}}' \
  --region ap-southeast-1
~~~

Ví dụ dùng một `WindowTargetId` đã đăng ký trước đó. Trong thực tế, thay ID, role, command document, log group và parameters theo môi trường. Đảm bảo command an toàn khi retry và có exit code khác 0 khi precondition không đạt.

### 8.2. Automation

Automation phù hợp với runbook có nhiều bước, có thể thao tác AWS resources và có thể thêm approval/wait/branch. Ví dụ:

- Tạo snapshot trước khi cập nhật.
- Xác minh trạng thái instance.
- Thực hiện stop/start/reboot theo quy trình.
- Cập nhật cấu hình và kiểm tra kết quả.

Khi Automation runbook nhận tài nguyên qua input parameters, task có thể không cần target group riêng. Với task targetless, không cấu hình `MaxConcurrency` và `MaxErrors`; Systems Manager có thể hiển thị placeholder `1` trong response.

### 8.3. Lambda

Lambda task phù hợp khi cần gọi logic tùy chỉnh hoặc tích hợp với hệ thống change-management. Payload có thể truyền thông tin maintenance window, service hoặc change ID.

Không nhét credentials vào payload. Lambda nên lấy quyền qua execution role, xác thực input và có idempotency để tránh chạy lặp nếu invocation được retry.

### 8.4. Step Functions

Step Functions Standard phù hợp với workflow điều phối nhiều bước, ví dụ:

1. Gỡ node khỏi load balancer.
2. Chờ connection drain.
3. Chạy patch Automation.
4. Chờ node healthy.
5. Chạy smoke test.
6. Đưa node trở lại load balancer.

Workflow nên có nhánh xử lý lỗi và timeout rõ ràng. Nếu patch thất bại, không nên tự động đưa node lỗi trở lại traffic chỉ vì bước workflow tiếp theo được lập lịch.

### 8.5. Task targetless

Run Command luôn cần target. Automation, Lambda và Step Functions có thể không cần target nếu resource đã được chỉ định trong parameters hoặc logic của task.

Ví dụ, runbook cập nhật AMI nhận AMI ID trong input parameters nên không cần thêm target instance. Khi task targetless, bỏ `--targets`, `--max-concurrency` và `--max-errors`; các rate controls không áp dụng.

## 9. Priority và thứ tự thực thi task

Mỗi task có `Priority`, là số nguyên không âm. Số càng nhỏ thì priority càng cao. Task cùng priority được lập lịch song song; task priority thấp hơn chỉ được lập lịch sau khi task priority cao hơn đạt trạng thái cuối cùng.

Ví dụ:

| Priority | Task | Quan hệ |
| ---: | --- | --- |
| 0 | Pre-check và backup | Chạy trước |
| 10 | Drain và patch canary | Sau priority 0 |
| 20 | Validate canary | Sau priority 10 |
| 30 | Rollout wave 1 | Sau priority 20 |
| 40 | Rollout wave 2 | Sau priority 30 |

### 9.1. Priority không phải điều kiện thành công

Khi task priority cao hơn đạt final state, task priority thấp hơn có thể được lập lịch dù task trước đó kết thúc với trạng thái FAILED. Priority chỉ điều khiển thứ tự, không tự động tạo điều kiện "chỉ chạy nếu task trước SUCCESS".

Nếu task sau chỉ được phép chạy khi health check thành công, hãy đưa logic điều kiện vào Automation/Step Functions hoặc quy trình approval riêng.

### 9.2. Task cùng priority

Task cùng priority có thể chạy song song. Chỉ đặt cùng priority khi các task độc lập và không tranh chấp cùng resource. Nếu một task drain traffic và task khác restart cùng node, chúng cần thứ tự rõ ràng thay vì cùng priority.

### 9.3. Nhiều target groups

AWS ghi rõ rằng khi một maintenance window task được đăng ký với nhiều target groups, các task invocations theo các target groups đó diễn ra tuần tự. Nếu cần các target groups chạy đồng thời, đăng ký task riêng cho từng target group và đặt cùng priority; sau đó cấu hình concurrency/error threshold riêng cho từng task.

Hãy phân biệt target groups đã đăng ký với số managed nodes được resolve bên trong một target group. Kiểm tra cách resolve thực tế trong test window trước khi dựa vào giả định song song.

## 10. MaxConcurrency và MaxErrors

Hai rate controls giới hạn tốc độ triển khai và ngưỡng lỗi trên các target.

### 10.1. MaxConcurrency

`MaxConcurrency` là số lượng hoặc phần trăm targets được chạy đồng thời cho một task. Ví dụ:

- `1`: xử lý một target tại một thời điểm.
- `5`: tối đa năm targets đồng thời.
- `10%`: tối đa khoảng 10% số targets được resolve.
- `100%`: cho phép toàn bộ targets chạy song song, trong giới hạn/quota dịch vụ.

Khi target dựa trên tag hoặc Resource Group và số lượng resource có thể thay đổi, dùng phần trăm giúp giới hạn concurrency tương đối theo quy mô fleet. Chọn tỷ lệ nhỏ cho canary và wave đầu tiên.

### 10.2. MaxErrors

`MaxErrors` là số lượng hoặc tỷ lệ lỗi tối đa trước khi Systems Manager dừng lập lịch task trên các targets còn lại. Ví dụ:

- `0`: không cho phép lỗi; khi lỗi đầu tiên được ghi nhận, ngừng gửi task tới các targets tiếp theo.
- `1`: cho phép một lỗi; khi lỗi thứ hai được nhận, ngừng lập lịch tiếp.
- `5%`: ngừng lập lịch thêm khi vượt ngưỡng lỗi theo phần trăm.

Các target đang xử lý có thể tiếp tục trả lỗi sau khi ngưỡng đã đạt. Do đó, số lỗi cuối cùng có thể lớn hơn giá trị `MaxErrors`.

### 10.3. Ví dụ rate control

Giả sử có 100 instances và task patch có:

~~~text
MaxConcurrency = 10%
MaxErrors      = 2
~~~

Hệ thống có thể dispatch khoảng 10 targets cùng lúc. Với `MaxErrors = 2`, khi lỗi thứ ba được nhận, task dừng lập lịch cho những target còn lại. Các target đang chạy vẫn có thể hoàn thành hoặc báo lỗi.

Đây là cơ chế giới hạn thiệt hại, không phải cơ chế rollback. Khi ngưỡng lỗi bị vượt, team vẫn cần đánh giá những node đã thay đổi và khôi phục nếu cần.

### 10.4. Chọn giá trị theo blast radius

| Giai đoạn | MaxConcurrency gợi ý | MaxErrors gợi ý |
| --- | --- | --- |
| Canary | `1` | `0` hoặc `1` |
| Wave nhỏ | `5%` | `1` hoặc `1%` |
| Wave trung bình | `10–20%` | Theo SLO/error budget |
| Fleet ổn định, rủi ro thấp | Tăng dần sau kiểm chứng | Theo ngưỡng lỗi được phê duyệt |

Đây là giá trị khởi điểm để thiết kế, không phải cấu hình mặc định cho mọi workload. Tính số target, capacity còn lại, thời gian task và mức lỗi có thể chấp nhận trước khi chốt.

## 11. CutoffBehavior: xử lý task đang chạy

`CutoffBehavior` quyết định cách xử lý khi Maintenance Window đến cutoff:

| Giá trị | Hành vi |
| --- | --- |
| `CONTINUE_TASK` | Mặc định. Task invocation đang chạy tiếp tục; task có thể tiếp tục khởi chạy invocation theo cơ chế hiện tại cho tới khi hoàn tất hoặc bị giới hạn bởi window/task behavior. |
| `CANCEL_TASK` | Không bắt đầu invocation mới sau cutoff; cách xử lý invocation đang chạy phụ thuộc task type. |

### 11.1. Với Automation, Lambda và Step Functions

Khi dùng `CANCEL_TASK`, invocation đã chạy vẫn tiếp tục; Systems Manager không bắt đầu invocation mới sau cutoff. Những task chưa hoàn thành có thể mang trạng thái `TIMED_OUT`.

### 11.2. Với Run Command

Khi dùng `CANCEL_TASK`, Systems Manager gửi thao tác `CancelCommand` để cố gắng hủy command. AWS không đảm bảo command/process bên dưới chắc chắn đã dừng. Script cần tự xử lý signal/timeout và tránh để một phần thay đổi ở trạng thái không nhất quán.

### 11.3. Chọn hành vi phù hợp

- Chọn `CONTINUE_TASK` khi task cần hoàn tất an toàn sau cutoff và việc tiếp tục không gây rủi ro.
- Chọn `CANCEL_TASK` khi cần ngăn invocation mới và giảm khả năng task bắt đầu quá sát cuối window.
- Với task destructive hoặc có nhiều bước, xây dựng cleanup/rollback riêng; đừng dựa vào cancel để khôi phục trạng thái.

## 12. CloudWatch alarm như một lớp bảo vệ

Maintenance Window task có thể gắn CloudWatch alarm configuration để theo dõi tín hiệu sức khỏe trong lúc chạy. Ví dụ alarm theo:

- Application 5xx/error rate.
- Latency p95/p99.
- Healthy host count của load balancer.
- CPU, memory hoặc queue depth.
- Custom metric thể hiện lỗi patch/agent.

Alarm configuration được hỗ trợ cho Run Command và Automation tasks. `AlarmConfiguration` chứa một CloudWatch alarm. `IgnorePollAlarmFailure` mặc định là `false`; nếu Systems Manager không lấy được trạng thái alarm, execution có thể dừng. Nếu lấy được trạng thái `OK` hoặc `INSUFFICIENT_DATA`, execution tiếp tục bất kể giá trị `IgnorePollAlarmFailure`.

Khi alarm kích hoạt (trạng thái ALARM), task được dừng. Việc gắn alarm cho Run Command/Automation có thể cần principal đăng ký task có quyền `iam:CreateServiceLinkedRole` theo hướng dẫn AWS.

Thiết kế alarm trước khi chạy task:

1. Chọn metric phản ánh impact thật của service.
2. Đặt threshold và evaluation periods đủ nhạy nhưng tránh false positives.
3. Xác minh alarm ở trạng thái OK trước maintenance.
4. Xác định rõ cách xử lý nếu alarm chuyển ALARM hoặc không truy vấn được.
5. Theo dõi alarm cùng task execution và application dashboard.

Alarm là guardrail bổ sung; nó không thay thế canary, rate controls hoặc health checks trong task.

## 13. IAM roles và phân tách quyền

Maintenance Windows có nhiều lớp quyền. Cấp nhầm role hoặc gom mọi quyền vào một role rộng có thể khiến một task bảo trì được phép thay đổi tài nguyên ngoài phạm vi dự kiến.

### 13.1. Người đăng ký task

Principal tạo window, đăng ký target và task cần quyền Systems Manager tương ứng. Khi chỉ định một IAM service role cho task, principal thường cần `iam:PassRole` đối với đúng role đó.

Giới hạn `iam:PassRole` theo ARN role và điều kiện `iam:PassedToService = ssm.amazonaws.com` khi phù hợp. Không cho người tạo task truyền bất kỳ IAM role nào trong account.

### 13.2. Maintenance Window service role

Đây là role mà Systems Manager assume để chạy task thay mặt người vận hành. Trust policy cơ bản:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ssm.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Permission policy phụ thuộc task type và runbook. Ví dụ:

- Run Command: quyền gửi command tới managed nodes và đọc trạng thái command.
- Automation: quyền bắt đầu/đọc Automation execution và các AWS API mà runbook cần.
- Lambda: quyền invoke đúng function ARN.
- Step Functions: quyền start execution của đúng Standard state machine.
- Resource Groups/tag targeting: quyền đọc resource group/tag metadata cần thiết.

AWS khuyến nghị custom service role với policy chỉ chứa quyền cần thiết cho các task thực tế. Không mặc định dùng service-linked role rộng cho mọi workload; tài liệu AWS hiện tại khuyến nghị tạo role riêng cho Maintenance Windows tasks.

### 13.3. Automation Assume Role

Automation runbook có thể nhận tham số `AutomationAssumeRole`. Khi có tham số này, Automation assume role đó để thực hiện các bước trong runbook. Nếu không chỉ định, runbook có thể sử dụng Maintenance Window service role đã cấu hình.

Ví dụ runbook tạo snapshot cần quyền `ec2:CreateSnapshot`. Nếu service role không có quyền đó và không có Automation Assume Role khác, execution sẽ thất bại ở bước snapshot.

Tách role điều phối khỏi role thực hiện hành động giúp kiểm soát quyền theo từng loại runbook.

### 13.4. Instance profile của managed node

Với Run Command, managed node cần SSM Agent và IAM permissions phù hợp để giao tiếp với Systems Manager. Nếu output được ghi từ node vào S3 hoặc CloudWatch Logs, quyền ghi đó thuộc instance profile/role của node, không phải IAM user đăng ký task.

Nếu S3 bucket hoặc log group nằm ở account khác, cần kiểm tra resource policy ở destination cùng với quyền của node role.

### 13.5. Phân biệt bốn principal

| Principal | Trách nhiệm |
| --- | --- |
| Operator/automation caller | Tạo window, đăng ký task, truyền service role |
| Maintenance Window service role | Systems Manager assume để điều phối task |
| Automation Assume Role | Runbook assume để gọi các AWS APIs trong các bước |
| Managed node instance profile | SSM Agent và node dùng để giao tiếp/ghi output |

Không mặc định các role này là một. Ghi rõ ARN nào được dùng ở từng lớp trong runbook và change record.

## 14. Logging, monitoring và trạng thái execution

Một task kết thúc với trạng thái SUCCESS không tự chứng minh ứng dụng vẫn khỏe. Cần kết hợp trạng thái Systems Manager với command output, application metrics và health checks.

### 14.1. Run Command output

Run Command task có thể gửi output đến:

- Amazon CloudWatch Logs qua `CloudWatchOutputConfig`.
- Amazon S3 qua `OutputS3BucketName` và `OutputS3KeyPrefix`.
- SNS notification qua `NotificationConfig`.

Các trường output này nằm trong `TaskInvocationParameters.RunCommand`. AWS đã deprecated `LoggingInfo` và `TaskParameters` cũ; dùng `TaskInvocationParameters` và `Parameters` cho cấu hình mới.

Ví dụ cấu hình output:

~~~json
{
  "RunCommand": {
    "Parameters": {
      "commands": [
        "systemctl is-active nginx",
        "df -h"
      ]
    },
    "CloudWatchOutputConfig": {
      "CloudWatchOutputEnabled": true,
      "CloudWatchLogGroupName": "/ssm/maintenance"
    },
    "OutputS3BucketName": "company-ssm-command-output",
    "OutputS3KeyPrefix": "maintenance/prod/"
  }
}
~~~

Node role cần quyền ghi vào bucket/log group. Giới hạn retention và reader permissions cho output vì log có thể chứa hostname, package versions, đường dẫn hoặc thông tin cấu hình nội bộ.

### 14.2. EventBridge

Maintenance Windows phát các sự kiện vận hành có thể được dùng với Amazon EventBridge. Dùng EventBridge để:

- Thông báo khi window execution bắt đầu hoặc kết thúc.
- Tạo ticket khi task FAILED/TIMED_OUT.
- Gửi thông báo đến SNS/Chatbot hoặc incident workflow.
- Ghi nhận owner information và change ID cùng event.

EventBridge rule nên lọc theo window ID/task status và tránh tạo alert trùng cho từng invocation nếu chỉ cần một thông báo tổng hợp.

### 14.3. Theo dõi execution history

Các API hữu ích:

- `DescribeMaintenanceWindowExecutions`: liệt kê các lần window chạy.
- `DescribeMaintenanceWindowExecutionTasks`: liệt kê tasks trong một lần chạy.
- `DescribeMaintenanceWindowExecutionTaskInvocations`: liệt kê invocation theo target.
- `GetMaintenanceWindowExecutionTask`: xem chi tiết task execution.
- `ListCommands`, `ListCommandInvocations`: xem kết quả Run Command.
- `GetAutomationExecution`: xem chi tiết Automation execution.

Lưu `WindowExecutionId`, `TaskExecutionId`, `WindowTaskId` và command/automation execution IDs trong change record để điều tra lại.

### 14.4. Trạng thái cần chú ý

| Trạng thái | Ý nghĩa vận hành |
| --- | --- |
| `PENDING` | Đang chờ được xử lý |
| `IN_PROGRESS` | Task đang chạy |
| `SUCCESS` | Task hoàn tất thành công |
| `FAILED` | Task thất bại |
| `TIMED_OUT` | Task không hoàn tất theo giới hạn liên quan |
| `CANCELLING` / `CANCELLED` | Đang hoặc đã hủy |
| `SKIPPED_OVERLAPPING` | Lần chạy bị bỏ qua do window execution bị chồng lấn |

Khi gặp `SKIPPED_OVERLAPPING`, kiểm tra lịch, thời lượng lần chạy trước và số concurrent window executions. Không giả định task bị bỏ qua đồng nghĩa target đã được bảo trì.

## 15. Tạo Maintenance Window và đăng ký target bằng CLI

Phần này minh họa cách tạo window và đăng ký target. Dùng AWS CLI v2 đã cấu hình đúng account/Region. Các ID/ARN là giá trị ví dụ; thay bằng resource của môi trường test trước.

### 15.1. Tạo window

~~~bash
aws ssm create-maintenance-window \
  --name "prod-weekly-patching" \
  --description "Weekly production patching" \
  --schedule "cron(0 2 ? * SUN *)" \
  --schedule-timezone "Asia/Ho_Chi_Minh" \
  --duration 4 \
  --cutoff 1 \
  --no-allow-unassociated-targets \
  --tags Key=Environment,Value=Production Key=Owner,Value=platform-team \
  --region ap-southeast-1
~~~

Lệnh trả về `WindowId`, có dạng `mw-` theo sau 17 ký tự hex. Lưu ID để dùng cho các bước tiếp theo. `--no-allow-unassociated-targets` yêu cầu task dùng targets đã đăng ký với window.

### 15.2. Đăng ký canary target

~~~bash
aws ssm register-target-with-maintenance-window \
  --window-id mw-0123456789abcdef0 \
  --resource-type INSTANCE \
  --targets "Key=tag:Environment,Values=Production" "Key=tag:MaintenanceRing,Values=canary" \
  --name "prod-canary-ring" \
  --owner-information "platform-team" \
  --region ap-southeast-1
~~~

Lệnh trả về `WindowTargetId`. Ghi lại ID này nếu task đăng ký bằng `Key=WindowTargetIds`.

### 15.3. Kiểm tra window và targets

~~~bash
aws ssm get-maintenance-window \
  --window-id mw-0123456789abcdef0 \
  --region ap-southeast-1

aws ssm describe-maintenance-window-targets \
  --window-id mw-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Kiểm tra schedule, timezone, duration, cutoff, enabled state, target type và tag conditions trước khi đăng ký task. Nếu cần, kiểm tra danh sách managed nodes/tag hiện tại bằng Systems Manager và Resource Groups.

### 15.4. Đăng ký Run Command task

~~~bash
aws ssm register-task-with-maintenance-window \
  --window-id mw-0123456789abcdef0 \
  --name "prod-canary-health-check" \
  --task-arn "AWS-RunShellScript" \
  --task-type RUN_COMMAND \
  --targets "Key=WindowTargetIds,Values=11111111-2222-3333-4444-555555555555" \
  --service-role-arn arn:aws:iam::111122223333:role/MaintenanceWindowExecutionRole \
  --priority 10 \
  --max-concurrency "1" \
  --max-errors "0" \
  --cutoff-behavior CANCEL_TASK \
  --task-invocation-parameters '{"RunCommand":{"Parameters":{"commands":["systemctl is-active nginx","curl -fsS http://localhost/health"]},"CloudWatchOutputConfig":{"CloudWatchOutputEnabled":true,"CloudWatchLogGroupName":"/ssm/maintenance"}}}' \
  --region ap-southeast-1
~~~

Task này chỉ chạy trên target đã đăng ký và giới hạn concurrency một target. `MaxErrors=0` dừng lập lịch thêm ngay khi phát sinh lỗi đầu tiên. Trước khi dùng health check thực tế, bảo đảm endpoint và command phù hợp với ứng dụng.

## 16. Cập nhật, vô hiệu hóa và xóa window

Maintenance Window có thể được chỉnh lịch, bật/tắt, thêm/bớt target hoặc task. Thay đổi này ảnh hưởng trực tiếp đến lịch vận hành; quản lý như một change có review.

### 16.1. Tắt window tạm thời

~~~bash
aws ssm update-maintenance-window \
  --window-id mw-0123456789abcdef0 \
  --no-enabled \
  --region ap-southeast-1
~~~

Tắt window ngăn các lần chạy theo lịch tiếp theo. Kiểm tra execution đang chạy trước khi thay đổi; không giả định thao tác disable tự dừng mọi task invocation đã bắt đầu.

### 16.2. Bật lại window

~~~bash
aws ssm update-maintenance-window \
  --window-id mw-0123456789abcdef0 \
  --enabled \
  --region ap-southeast-1
~~~

Trước khi bật lại, xác nhận change window, target tags, task versions, service role và lịch không còn trùng với một lần bảo trì khác.

### 16.3. Sửa task

`UpdateMaintenanceWindowTask` có thể thay task ARN, service role, invocation parameters, priority, concurrency và error threshold. Không thể đổi task type của task hiện có; nếu cần loại task khác, đăng ký task mới và xóa task cũ theo change plan.

Khi cập nhật `TaskInvocationParameters`, phải gửi lại mọi giá trị cần giữ. Các giá trị không gửi lại có thể bị loại bỏ. Đây là lỗi thường gặp khiến cấu hình CloudWatch/S3 output hoặc notification biến mất sau một lần update.

### 16.4. Xóa window

Trước khi xóa window:

1. Kiểm tra không còn execution đang chạy.
2. Xác định dashboards/EventBridge rules/runbooks còn tham chiếu window ID không.
3. Lưu execution history cần thiết.
4. Gỡ targets và tasks theo đúng quy trình API nếu cần.
5. Xóa window sau khi xác nhận không còn consumer phụ thuộc.

Không xóa window chỉ để xử lý một lần chạy lỗi; thường nên giữ history để điều tra và sửa cấu hình.

## 17. Service quotas và giới hạn vận hành

Theo AWS Systems Manager service quotas, các giá trị mặc định cho Maintenance Windows gồm:

| Resource | Quota mặc định |
| --- | ---: |
| Maintenance windows trong một account/Region | 50 |
| Tasks trên mỗi maintenance window | 20 |
| Targets trên mỗi maintenance window | 100 |
| Targets trên mỗi task | 10 |
| Concurrent maintenance window executions | 5 |

Quota có thể thay đổi theo account/Region và có thể được yêu cầu tăng qua AWS Service Quotas. Trước khi thiết kế nhiều cửa sổ song song, kiểm tra quota thực tế thay vì dựa vào giá trị mặc định trong tài liệu.

### 17.1. Những giới hạn khác ảnh hưởng tới rollout

- Run Command chịu quota về command delivery, số invocation và khả năng tiếp nhận của managed nodes.
- Automation có quota concurrency riêng; các execution vượt ngưỡng có thể vào queue.
- Lambda và Step Functions có quota/service availability riêng theo Region.
- SSM Agent, instance profile và network path tới Systems Manager endpoints quyết định node có nhận được task hay không.
- Maintenance Window thông thường được quản lý theo từng account/Region; không coi một window là lịch toàn organization.

### 17.2. Tính khả thi trước khi tạo window

Với một fleet lớn, ước lượng:

1. Số lượng targets được resolve tại thời điểm chạy.
2. Số task cần thiết và số target groups.
3. Thời gian trung bình/mức cao nhất cho mỗi invocation.
4. Số invocations có thể chạy đồng thời theo `MaxConcurrency`.
5. Số window execution khác có thể trùng lịch.
6. Automation/Run Command quotas và capacity của downstream systems.

Nếu tổng thời gian dự kiến vượt thời lượng window, hãy chia rollout thành nhiều kỳ hoặc giảm phạm vi mỗi đợt. Không tăng concurrency chỉ để ép toàn fleet hoàn thành trong một window ngắn.

## 18. Troubleshooting lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| **Window không chạy theo lịch** | Window bị disable, cron/timezone sai hoặc nằm ngoài StartDate/EndDate | Kiểm tra enabled state, schedule, IANA timezone, start/end và next execution time |
| **Window chạy sai giờ địa phương** | ScheduleTimezone chưa được đặt hoặc timestamp bị hiểu theo UTC | Kiểm tra IANA timezone và chuyển đổi timestamp theo UTC |
| **Task không được lập lịch** | Cutoff đã đến, priority cao hơn chưa kết thúc hoặc MaxErrors đã vượt ngưỡng | Kiểm tra cutoff time, priority và task rate controls |
| **Không có target được resolve** | Tag sai key/value/casing, Resource Group sai hoặc node chưa được quản lý | Kiểm tra target definitions, tags, resource types và managed node status |
| **Target có node ngoài dự kiến** | Tag dùng chung hoặc gắn nhầm trên resource | Kiểm tra inventory/tag governance và thu hẹp selector |
| **Task registration AccessDenied** | Caller thiếu SSM permissions hoặc iam:PassRole | Kiểm tra caller identity, policy và role ARN được pass |
| **Task registration thành công nhưng không chạy** | TaskArn/document không hợp lệ, thiếu target hoặc service role không assume được | Kiểm tra task type, TaskArn, target requirement và trust policy |
| **Run Command delivery timeout** | SSM Agent offline, node role sai hoặc network không tới SSM endpoints | Kiểm tra agent, instance profile, DNS và HTTPS 443 tới SSM/ssmmessages/ec2messages |
| **Automation thất bại ở một step** | Service role/Automation Assume Role thiếu permission | Xem Automation execution steps và cấp đúng API permission |
| **Lambda/Step Functions task không đăng ký được** | Dịch vụ chưa hỗ trợ ở Region hoặc ARN sai | Kiểm tra Region availability, function/state machine ARN và task type |
| **Task bị dừng sau vài lỗi** | MaxErrors bị vượt | Kiểm tra số target đã lỗi và ngưỡng count/percentage |
| **Task bắt đầu sau cutoff** | CutoffBehavior đang là CONTINUE_TASK hoặc invocation đã được dispatch | Kiểm tra CutoffBehavior và task invocation timestamps |
| **Run Command vẫn chạy sau khi cancel** | CancelCommand chỉ gửi yêu cầu hủy; process có thể không dừng | Thiết kế timeout/cleanup trong script và kiểm tra process trên node |
| **Task bị SKIPPED_OVERLAPPING** | Lần execution trước còn chồng lấn hoặc quota concurrent windows | Kiểm tra execution history, duration, schedule và quota |
| **Không thấy command output** | Node role thiếu quyền ghi S3/CloudWatch Logs hoặc sai destination | Kiểm tra instance profile policy, bucket/log group policy và output settings |
| **Task bị alarm dừng** | CloudWatch alarm chuyển ALARM | Kiểm tra metric, alarm history, application impact và task execution |
| **Task targetless báo lỗi MaxConcurrency/MaxErrors** | Đã truyền rate controls cho task không có targets | Bỏ hai trường rate controls khỏi task targetless |
| **Không chọn được service role trong console** | Role bị xóa, tên/ARN sai hoặc thiếu iam:ListRoles | Xác minh role tồn tại, trust policy và quyền console |

### 18.1. Kiểm tra managed node

Run Command chỉ hoạt động trên managed nodes đủ điều kiện. Kiểm tra:

- SSM Agent đã cài và đang chạy.
- Instance profile hoặc hybrid activation role có quyền Systems Manager cần thiết.
- Node có kết nối outbound HTTPS 443 tới các Systems Manager endpoints phù hợp Region, gồm `ssm`, `ssmmessages` và tùy môi trường `ec2messages`.
- DNS, route, proxy và VPC endpoints không chặn traffic.
- Node xuất hiện trong Systems Manager Fleet Manager/Managed nodes với trạng thái online.

Node không online có thể vẫn xuất hiện trong target group nhưng command không được giao tới agent.

### 18.2. Kiểm tra vì sao không có task invocation

1. Xác nhận window có execution tại thời điểm mong đợi.
2. Xác nhận task đã được đăng ký và chưa bị xóa.
3. Kiểm tra target resolution và resource type.
4. Kiểm tra task priority, cutoff, MaxErrors và trạng thái task trước đó.
5. Xác nhận role được assume và task ARN/document version hợp lệ.
6. Mở task execution details và invocation details để đọc `StatusDetails`.

Đừng kết luận "không có thay đổi" chỉ vì không thấy command output. Task có thể chưa được dispatch hoặc output có thể đang ghi vào S3/CloudWatch Logs khác.

## 19. Case study: patching web fleet mà giữ đủ capacity

### 19.1. Bối cảnh

Một dịch vụ web chạy 60 EC2 instances trong một Region, phân bổ trên ba Availability Zones. Mỗi AZ có 20 instances. Load balancer cần duy trì ít nhất 4 healthy targets trong mỗi AZ để giữ capacity theo SLO. Đội platform cần cài security updates và reboot khi cần vào sáng Chủ nhật.

### 19.2. Thiết kế target rings

Các instance được gắn tags:

~~~text
Environment=Production
Service=web
MaintenanceRing=canary | wave-1 | wave-2
AvailabilityZone=az-a | az-b | az-c
~~~

Phân chia rollout:

| Ring | Phạm vi | Mục tiêu |
| --- | --- | --- |
| Canary | 1 instance mỗi AZ (3 instances) | Kiểm tra patch, reboot và health checks |
| Wave 1 | 6 instances mỗi AZ (18 instances) | Xác nhận tác động trên nhóm nhỏ |
| Wave 2 | 13 instances còn lại mỗi AZ (39 instances) | Hoàn tất fleet sau khi hai giai đoạn trước ổn định |

Không đưa cả 60 instances vào một task không giới hạn. Tag rings giúp team kiểm soát số target theo từng giai đoạn và tránh cập nhật đồng thời quá nhiều node trong cùng AZ.

### 19.3. Cấu hình window

Window chạy 02:00 Chủ nhật theo `Asia/Ho_Chi_Minh`, duration 5 giờ, cutoff 1 giờ. Như vậy task mới không được lập lịch sau 06:00; window kết thúc lúc 07:00. Những task đã chạy có thể tiếp tục sau 07:00 tùy cutoff behavior.

### 19.4. Thứ tự task

| Priority | Task | Target ring | Rate control |
| ---: | --- | --- | --- |
| 0 | Pre-check capacity và backup/snapshot theo policy | Canary | 1, MaxErrors 0 |
| 10 | Drain, patch, reboot và validate | Canary | 1, MaxErrors 0 |
| 20 | Patch và validate | Wave 1 | 10%, MaxErrors 1 |
| 30 | Patch và validate | Wave 2 | 10%, MaxErrors 1 |
| 40 | Tổng hợp kết quả và kiểm tra fleet health | Không cần target nếu workflow tự lấy dữ liệu | Theo workflow |

Runbook patch cần đưa node ra khỏi traffic trước khi cập nhật, kiểm tra service sau reboot và chỉ rejoin khi health check đạt. Nếu validation thất bại, giữ node ngoài traffic, tạo incident/ticket và dừng wave tiếp theo theo logic workflow/approval.

### 19.5. Alarm và stop conditions

Gắn CloudWatch alarms theo:

- Healthy host count trong từng AZ.
- Application 5xx/error rate.
- p95/p99 latency.
- CPU hoặc queue depth nếu đây là tín hiệu nghẽn chính.

Nếu alarm kích hoạt, task bị dừng. MaxErrors cũng giới hạn số lỗi invocation. Hai guardrails này bổ sung cho nhau: alarm quan sát impact ở cấp service, còn MaxErrors quan sát lỗi của task trên các targets.

### 19.6. Kiểm tra sau bảo trì

- Xác nhận đủ 20 healthy instances trong mỗi AZ hoặc số lượng đã được change plan cho phép.
- Xác nhận tất cả instances có patch level/version mong muốn.
- Xác nhận SSM Agent vẫn online.
- Kiểm tra error rate, latency và traffic distribution.
- Xem task invocations FAILED/TIMED_OUT/CANCELLED.
- Lưu output, event history, command IDs và change record.
- Chỉ đóng change khi service ổn định qua thời gian quan sát đã định.

### 19.7. Bài học

Maintenance Window cung cấp lịch và rate controls. Runbook cung cấp logic drain/patch/validate/rejoin. CloudWatch alarms cung cấp tín hiệu impact. Muốn hạn chế blast radius, cả ba phần phải được thiết kế cùng nhau.

## 20. Bài tập củng cố

### Bài 1 — Chọn công cụ

Một tổ chức muốn đảm bảo mọi managed node luôn dùng một cấu hình agent theo chuẩn. Nên ưu tiên State Manager hay Maintenance Windows?

**Gợi ý:** State Manager duy trì trạng thái mong muốn; Maintenance Windows phù hợp khi cần chạy cập nhật vào thời gian đã phê duyệt.

### Bài 2 — Tính cutoff

Window bắt đầu lúc 23:00, duration 4 giờ, cutoff 1 giờ. Task mới được phép bắt đầu muộn nhất vào lúc nào?

**Gợi ý:** 23:00 + 4 giờ - 1 giờ = 02:00. Window kết thúc lúc 03:00.

### Bài 3 — Chọn schedule

Team muốn bảo trì vào 02:00 Chủ nhật theo giờ Việt Nam. Cần cấu hình gì để không phải tự quy đổi UTC mỗi lần?

**Gợi ý:** cron `cron(0 2 ? * SUN *)` cùng timezone `Asia/Ho_Chi_Minh`.

### Bài 4 — Chọn target

Fleet production thay instance thường xuyên do Auto Scaling. Nên dùng instance IDs hay tag target?

**Gợi ý:** tag target phù hợp hơn; dùng `Environment`, `Service` và `MaintenanceRing` để giới hạn nhóm.

### Bài 5 — MaxConcurrency

Một task có 80 targets, `MaxConcurrency=10%`. Khoảng bao nhiêu target có thể được xử lý đồng thời?

**Gợi ý:** khoảng 8 targets, theo cách resolve và làm tròn của dịch vụ.

### Bài 6 — MaxErrors

Task có `MaxErrors=2`. Khi lỗi thứ ba được nhận, điều gì xảy ra?

**Gợi ý:** Systems Manager dừng lập lịch task cho các targets còn lại; những invocation đang chạy vẫn có thể trả kết quả/lỗi.

### Bài 7 — CutoffBehavior

Một Run Command task cần hoàn tất cleanup ngay cả khi cutoff đến. `CANCEL_TASK` có bảo đảm process dừng sạch không?

**Gợi ý:** không. Systems Manager gửi CancelCommand để thử hủy, nhưng không đảm bảo process bên dưới dừng. Script cần có timeout và cleanup logic riêng.

### Bài 8 — Priority

Task priority 10 thất bại. Task priority 20 có tự động bị bỏ qua không?

**Gợi ý:** không. Priority điều khiển thứ tự; task tiếp theo có thể được lập lịch khi task trước đạt final state. Cần điều kiện success trong Automation/Step Functions nếu muốn chặn bước sau.

### Bài 9 — Role permissions

Run Command ghi output vào S3 nhưng không có file. Cần kiểm tra role nào trước?

**Gợi ý:** instance profile/role của managed node và S3 bucket policy; quyền ghi output thuộc node role, không phải người đăng ký task.

### Bài 10 — SKIPPED_OVERLAPPING

Một window hiển thị `SKIPPED_OVERLAPPING`. Điều tra những gì?

**Gợi ý:** execution trước còn chạy, duration/cutoff quá dài, schedule quá sát hoặc quota concurrent window executions đã đạt.

## 21. Checklist trước khi chạy production

- [ ] Change record có owner, approver, mục tiêu, thời gian và rollback plan.
- [ ] Schedule dùng đúng cron/rate/at và timezone IANA.
- [ ] StartDate/EndDate không vô tình loại bỏ lần chạy mong muốn.
- [ ] Duration đủ dài theo thời gian thực nghiệm; cutoff dành đủ thời gian ngừng dispatch.
- [ ] Đã hiểu task đang chạy có thể tiếp tục sau khi window kết thúc.
- [ ] Targets được review; tag/resource group không bao gồm tài nguyên ngoài phạm vi.
- [ ] Fleet được chia thành canary và các rollout waves.
- [ ] Capacity tối thiểu được duy trì theo AZ/load balancer/SLO.
- [ ] Runbook/SSM document có version cụ thể và đã test trong non-production.
- [ ] Task có timeout, retry/idempotency và cleanup/rollback logic.
- [ ] Task priority thể hiện đúng thứ tự; không nhầm priority với điều kiện thành công.
- [ ] MaxConcurrency không vượt mức capacity/downstream systems chịu được.
- [ ] MaxErrors phù hợp giai đoạn rollout và error budget.
- [ ] CutoffBehavior được chọn có chủ đích cho từng task type.
- [ ] CloudWatch alarms theo dõi impact quan trọng của service.
- [ ] IAM service role là custom role với least privilege.
- [ ] Operator chỉ có quyền `iam:PassRole` đối với role được phê duyệt.
- [ ] Automation Assume Role và node instance profile được phân tách.
- [ ] SSM Agent, instance profile và network path tới Systems Manager endpoints đã được xác minh.
- [ ] Command output có nơi lưu, retention và reader access phù hợp.
- [ ] EventBridge notifications/alarms tạo ticket hoặc cảnh báo đúng người.
- [ ] Đã kiểm tra service quotas và lịch không chồng lấn.
- [ ] Có người trực theo dõi canary, wave rollout và health metrics.
- [ ] Chỉ chuyển sang wave tiếp theo khi validation/approval đạt.
- [ ] Có kế hoạch giữ node ngoài traffic nếu patch/health check thất bại.
- [ ] Execution IDs, task IDs, command IDs và output được lưu trong change record.
- [ ] Kết thúc bảo trì bằng xác nhận service health, patch level và capacity.

## 22. Ghi nhớ

1. Maintenance Windows là bộ điều phối thời gian cho các task có thể gây gián đoạn; nó gồm schedule, duration, cutoff, targets và tasks.
2. Duration 1–24 giờ xác định độ dài window; cutoff 0–23 giờ xác định thời điểm ngừng lập lịch task mới.
3. Task đã bắt đầu có thể chạy sau khi window đóng. CutoffBehavior và timeout của task quyết định cách xử lý thực tế.
4. Dùng tags/Resource Groups cho fleet thay đổi thường xuyên; kiểm tra target resolution để tránh tác động ngoài phạm vi.
5. Run Command, Automation, Lambda và Step Functions phục vụ các kiểu công việc khác nhau; Step Functions phải là Standard workflow.
6. Priority điều khiển thứ tự, không phải điều kiện success. Cùng priority có thể chạy song song.
7. MaxConcurrency và MaxErrors giới hạn tốc độ dispatch và ngưỡng lỗi; chúng không tự rollback thay đổi đã thực hiện.
8. IAM service role, Automation Assume Role và node instance profile là các lớp quyền riêng.
9. CloudWatch alarms, EventBridge, Logs và execution history giúp phát hiện impact và điều tra kết quả.
10. Muốn giảm blast radius, hãy kết hợp canary, waves, capacity planning, health checks và rollback logic.

Maintenance Window chỉ tạo ra khung thời gian và cơ chế điều phối. Mức độ an toàn phụ thuộc vào target được chọn, quyền được cấp, task được viết, concurrency được giới hạn và cách team phản ứng khi health metrics xấu đi.

### Tài liệu AWS chính thức

- [AWS Systems Manager Maintenance Windows](https://docs.aws.amazon.com/systems-manager/latest/userguide/maintenance-windows.html) — khái niệm, task types và use cases.
- [CreateMaintenanceWindow API](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_CreateMaintenanceWindow.html) — duration, cutoff, schedule, timezone và target behavior.
- [Maintenance window scheduling and active period options](https://docs.aws.amazon.com/systems-manager/latest/userguide/maintenance-windows-schedule-options.html) — start/end dates, timezone và schedule offset.
- [Cron and rate expressions for Systems Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/reference-cron-and-rate-expressions.html) — cú pháp lịch.
- [Choosing between State Manager and Maintenance Windows](https://docs.aws.amazon.com/systems-manager/latest/userguide/state-manager-vs-maintenance-windows.html) — chọn công cụ theo mục tiêu.
- [RegisterTargetWithMaintenanceWindow API](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_RegisterTargetWithMaintenanceWindow.html) — target IDs, tags và resource groups.
- [RegisterTaskWithMaintenanceWindow API](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_RegisterTaskWithMaintenanceWindow.html) — task type, priority, rate controls và cutoff behavior.
- [MaintenanceWindowTaskInvocationParameters](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_MaintenanceWindowTaskInvocationParameters.html) — invocation parameters theo task type.
- [Assign tasks to a maintenance window](https://docs.aws.amazon.com/systems-manager/latest/userguide/sysman-maintenance-assign-tasks.html) — task registration, output và alarms.
- [Assign targets to a maintenance window](https://docs.aws.amazon.com/systems-manager/latest/userguide/sysman-maintenance-assign-targets.html) — target selection.
- [Setting up Maintenance Windows permissions](https://docs.aws.amazon.com/systems-manager/latest/userguide/setting-up-maintenance-windows.html) — IAM service role và operator permissions.
- [Registering maintenance window tasks without targets](https://docs.aws.amazon.com/systems-manager/latest/userguide/maintenance-windows-targetless-tasks.html) — task không cần target.
- [Troubleshooting Maintenance Windows](https://docs.aws.amazon.com/systems-manager/latest/userguide/troubleshooting-maintenance-windows.html) — lỗi phổ biến.
- [Systems Manager endpoints and quotas](https://docs.aws.amazon.com/general/latest/gr/ssm.html) — endpoints và service quotas.
