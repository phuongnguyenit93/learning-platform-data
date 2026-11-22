# Bài thực hành xây dựng Monitoring alarms và thu thập logs

Trong chương **Thực hành nền tảng OCI**, bài này hướng dẫn xây dựng một luồng quan sát cho máy ảo Oracle Cloud Infrastructure: lấy metrics của Compute, thu thập log ứng dụng, phát hiện bất thường và gửi thông báo. Phạm vi thuộc mô-đun **CLOUD_PROVIDERS_ORACLE**, kết nối kiến thức về tenancy, compartment, IAM và VCN với công việc vận hành hạ tầng có phân quyền, giám sát và kiểm soát chi phí.

Tình huống thực hành là một máy ảo chạy ứng dụng nội bộ. Người vận hành cần biết khi CPU tăng kéo dài, khi luồng metrics bị gián đoạn và những sự kiện ứng dụng xảy ra quanh thời điểm đó. Bài dùng log mô phỏng để thao tác được trên một VM Linux, không cần triển khai thêm ứng dụng hay cơ sở dữ liệu.

## 1. Kết quả cần đạt và kiến trúc

Sau khi hoàn thành, người học có thể:

- Xác định đúng region, compartment, metric namespace và instance cần giám sát.
- Tạo topic Notifications với email subscription đã xác nhận.
- Thu thập một file log qua Custom Logs Monitoring và tìm lại bản ghi theo mã lần chạy.
- Tạo alarm CPU cao và alarm thiếu metrics, giải thích được điều kiện kích hoạt.
- Kiểm chứng chu trình `OK → FIRING → OK` bằng lịch sử alarm và thông báo.
- Đối chiếu metrics với logs, khoanh vùng lỗi thu thập và dọn tài nguyên của bài.

Dành khoảng 90–120 phút, cộng thêm thời gian chờ agent và cấu hình đồng bộ nếu môi trường chưa được chuẩn bị.

~~~mermaid
flowchart LR
    subgraph VM["Compute VM trong compartment lab"]
        C["Compute Instance Monitoring"]
        F["File log ứng dụng"]
        U["Custom Logs Monitoring / Unified Monitoring Agent"]
        F --> U
    end
    C --> M["OCI Monitoring: metrics"]
    M --> A["Alarms: CPU cao / thiếu metrics"]
    A --> N["Notifications topic"]
    N --> E["Email đã xác nhận"]
    U --> L["OCI Logging: custom log"]
    L --> S["Logging Search"]
~~~

Có hai đường dữ liệu độc lập. Compute Instance Monitoring cung cấp metrics như `CpuUtilization`; Custom Logs Monitoring sử dụng Unified Monitoring Agent để thu thập custom logs. Bật một plugin không thay cho việc cấu hình plugin còn lại. Tên plugin và cách bật/tắt được mô tả trong [Oracle Cloud Agent](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/manage-plugins.htm).

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Metric | CPU của VM đang sử dụng bao nhiêu phần trăm? |
| Alarm | Điều kiện bất thường có kéo dài đủ lâu để báo động? |
| Notifications | Người phụ trách có nhận được thông báo? |
| Custom log | Ứng dụng ghi nhận sự kiện gì quanh thời điểm đó? |
| Log group | Các log nào cùng phạm vi quản lý và tìm kiếm? |

Một bản ghi `ERROR` trong Logging không tự trở thành một metric hoặc Monitoring alarm. Trong bài, alarm đánh giá metrics; logs cung cấp ngữ cảnh điều tra.

## 2. Chuẩn bị môi trường và quy ước

### 2.1. Tài nguyên cần có

Chuẩn bị một compartment lab, ví dụ `lab-observability`, cùng một VM Oracle Linux đang chạy và có Oracle Cloud Agent trên image được hỗ trợ. Dùng máy thử nghiệm mà bạn được phép tạo tải và thay đổi trạng thái plugin. Bảo đảm có đủ RAM cho hệ điều hành, các agent và phiên SSH.

Bạn cần:

1. Quyền truy cập Console và các quyền IAM ở phần tiếp theo.
2. Phiên SSH vào VM với quyền `sudo`.
3. Địa chỉ email do bạn kiểm soát để xác nhận subscription.
4. Đường kết nối từ VM đến API của OCI tại region đang dùng, bao gồm Monitoring và Logging.
5. Đồng hồ hệ điều hành được đồng bộ và DNS hoạt động.
6. OCI CLI đã được xác thực nếu làm phần tự động hóa tùy chọn.

Với subnet riêng, kiểm tra route, service gateway đến các dịch vụ OCI được hỗ trợ trong region, và luật egress HTTPS phù hợp. Nếu agent cần tải gói từ kho phần mềm bên ngoài, cần thêm đường ra tương ứng, chẳng hạn NAT gateway. Việc gửi metrics/logs không yêu cầu mở thêm cổng inbound từ Internet. Điều kiện phát metrics của Compute được nêu trong [Managing Alarms](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/managingalarms.htm).

### 2.2. Ghi lại các định danh

| Giá trị | Ý nghĩa |
| --- | --- |
| `REGION` | Region của VM, ví dụ region mà tenancy đã đăng ký |
| `COMPARTMENT_OCID` | OCID compartment chứa VM và các tài nguyên lab |
| `INSTANCE_OCID` | OCID chính xác của VM cần theo dõi |
| `TOPIC_OCID` | OCID topic Notifications sẽ tạo |
| `LOG_GROUP_OCID` | OCID log group sẽ tạo |
| `LOG_OCID` | OCID custom log nhận dữ liệu |
| `ALARM_OCID` | OCID alarm CPU, dùng nếu kiểm tra bằng CLI |

Các chuỗi trong dấu `<...>` bên dưới là chỗ cần thay bằng giá trị thực. Không dùng tên hiển thị của instance thay cho `INSTANCE_OCID`.

Trong bài, VM, metrics, alarms, topic, log group và agent configuration cùng nằm trong một compartment và region để dễ kiểm tra. Nếu triển khai tập trung sang compartment khác, phải cấp quyền riêng tại cả nguồn dữ liệu và nơi lưu cấu hình.

### 2.3. Phân biệt nơi chạy lệnh

| Loại thao tác | Nơi thực hiện |
| --- | --- |
| Tạo policy, dynamic group, topic, log và alarm | OCI Console |
| Tạo file log, phát marker, tạo tải CPU, xem systemd | Phiên Bash qua SSH trên VM |
| Lệnh bắt đầu bằng `oci` | Cloud Shell hoặc terminal đã cài và cấu hình OCI CLI |
| MQL và Logging Search | Ô truy vấn đúng dịch vụ trong Console |

Không chạy đoạn tạo tải hoặc ghi `/var/log/oci-lab` trên Cloud Shell vì khi đó bạn đang thao tác lên môi trường khác VM cần theo dõi.

## 3. Phân quyền IAM cho người thao tác và cho agent

Người dùng Console và tiến trình agent trên VM là hai chủ thể khác nhau. Quyền của người tạo log không tự cấp quyền gửi log cho instance.

### 3.1. Quyền của nhóm người thực hành

Quản trị viên tạo hoặc dùng nhóm `LabObservers` và gán người học vào nhóm. Ví dụ policy sau giới hạn thao tác dữ liệu và cấu hình vào compartment lab:

~~~text
Allow group LabObservers to read metrics in compartment lab-observability
Allow group LabObservers to manage alarms in compartment lab-observability
Allow group LabObservers to manage ons-topics in compartment lab-observability
Allow group LabObservers to manage log-groups in compartment lab-observability
Allow group LabObservers to manage unified-configuration in compartment lab-observability
Allow group LabObservers to read log-content in compartment lab-observability
Allow group LabObservers to read instances in compartment lab-observability
Allow group LabObservers to read instance-agent-plugins in compartment lab-observability
Allow group LabObservers to inspect dynamic-groups in tenancy
Allow group LabObservers to inspect compartments in tenancy
~~~

Nhóm có quyền quản lý alarm, đọc metrics và quản lý topic để tạo nơi nhận thông báo. Nếu topic đã được quản trị viên chuẩn bị, có thể thu hẹp quyền topic theo nhiệm vụ. Các quyền Monitoring và Notifications dựa trên [Policy Builder Policy Templates](https://docs.oracle.com/en-us/iaas/Content/Identity/policiescommon/commonpolicies.htm).

Quyền `read log-content` cho phép xem nội dung; `manage log-groups` phục vụ quản lý log group và log; `unified-configuration` phục vụ cấu hình agent. Việc chọn host group cần quyền xem nhóm tương ứng. Tham khảo [Logs and Log Groups](https://docs.oracle.com/en-us/iaas/Content/Logging/Task/managinglogs.htm).

Policy trên chưa cho phép cập nhật VM. Nếu người học tự bật/tắt plugin trong bài, quản trị viên có thể cấp thêm quyền sau cho compartment lab, hoặc trực tiếp thực hiện các lần đổi trạng thái plugin:

~~~text
Allow group LabObservers to use instances in compartment lab-observability
~~~

`use instances` còn cho phép những thao tác vận hành VM khác; chỉ giao trong phạm vi lab thích hợp. Tạo dynamic group và tạo policy vẫn là phần chuẩn bị của quản trị viên. Khi nhóm thuộc identity domain riêng, dùng cách định danh nhóm phù hợp, chẳng hạn `'TenDomain'/'LabObservers'`.

### 3.2. Dynamic group dành riêng cho VM

Tạo dynamic group `LabLogInstances` với matching rule:

~~~text
ALL {instance.id = '<INSTANCE_OCID>'}
~~~

Quy tắc nhắm đến đúng một VM giúp tránh thu thập ngoài phạm vi. Cú pháp chọn instance bằng ID được minh họa trong [Managing Agent Configurations](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/agent-configurations.htm).

Tạo policy cho instance principal:

~~~text
Allow dynamic-group LabLogInstances to use log-content in compartment lab-observability
~~~

Đây là quyền cho agent lấy cấu hình và đưa log vào Logging theo mô hình custom logs; không cần chép API signing key cá nhân lên VM. Oracle trình bày quyền này trong [Selecting Target Hosts with Dynamic Groups](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/custom_logs_multihost.htm).

Không diễn giải `use log-content` là quyền chỉ ghi tuyệt đối: quyền này còn bao gồm các khả năng đọc liên quan mà Logging định nghĩa. Compartment lab riêng giúp giới hạn phạm vi. Sau thay đổi IAM, chờ việc đồng bộ quyền và kiểm tra lại trước khi tiếp tục sửa policy.

## 4. Thiết lập thông báo và kiểm tra metrics nền

### 4.1. Tạo topic và email subscription

Trong Console, tìm dịch vụ **Notifications**, chọn đúng region và compartment rồi:

1. Tạo topic `lab-ops-alerts`.
2. Trong topic, tạo subscription với protocol **Email** và địa chỉ nhận của bạn.
3. Mở email xác nhận, bấm liên kết xác nhận.
4. Quay lại Console, kiểm tra subscription chuyển sang `ACTIVE`.
5. Dùng chức năng **Publish message** của topic để gửi thông điệp thử, ví dụ `OCI lab notification path ready`.
6. Xác minh email thử xuất hiện, kể cả trong thư mục spam nếu cần.

Email subscription ở `PENDING` chưa đủ điều kiện nhận các thông báo vận hành. Cơ chế xác nhận được mô tả trong [Creating a Subscription](https://docs.oracle.com/en-us/iaas/Content/Notification/Tasks/create-subscription-basic.htm).

Thông điệp thử chỉ kiểm tra đoạn topic → email. Sau đó vẫn phải kiểm tra đoạn alarm → topic → email.

### 4.2. Bật plugin và xác nhận có dữ liệu

Mở **Compute → Instances → VM của bài → Oracle Cloud Agent**. Bật **Compute Instance Monitoring** và **Custom Logs Monitoring**, sau đó đợi trạng thái chạy phù hợp. Với plugin không được image hỗ trợ, đổi sang image hỗ trợ trước khi tiếp tục; không coi việc bật công tắc là bằng chứng agent đã hoạt động.

Tìm **Monitoring → Metrics Explorer**, chọn compartment chứa VM và:

| Thuộc tính | Giá trị |
| --- | --- |
| Metric namespace | `oci_computeagent` |
| Metric name | `CpuUtilization` |
| Dimension | `resourceId = <INSTANCE_OCID>` |
| Interval | `1m` |
| Statistic | `mean` |
| Time range | Khoảng 15–30 phút gần nhất |

Ở chế độ MQL, truy vấn nền là:

~~~text
CpuUtilization[1m]{resourceId = "<INSTANCE_OCID>"}.mean()
~~~

Xác nhận có điểm dữ liệu mới và ghi lại mức CPU thông thường. `CpuUtilization` là tên metric có phân biệt chữ hoa/chữ thường, đơn vị phần trăm; `resourceId` là dimension dùng để chọn tài nguyên. Tham khảo [Compute Instance Metrics](https://docs.oracle.com/en-us/iaas/Content/Compute/References/computemetrics.htm).

Nếu biểu đồ rỗng, dừng tại đây để xử lý nguồn metrics. Không giảm ngưỡng alarm nhằm khắc phục việc thiếu dữ liệu.

## 5. Thu thập custom log từ VM

OCI Logging phân biệt Audit logs, service logs và custom logs. Bài dùng **custom log** do bạn chủ động ghi vào file. Audit ghi nhận hoạt động API của OCI; service logs xuất phát từ các dịch vụ được hỗ trợ khi cấu hình bật tương ứng. Không dùng Audit thay cho log ứng dụng trong VM. Xem [Logging Overview](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/loggingoverview.htm).

### 5.1. Chuẩn bị file log và mã lần chạy

Chạy trong phiên Bash qua SSH trên VM:

~~~bash
sudo install -d -m 0755 -o "$(id -un)" -g "$(id -gn)" /var/log/oci-lab

export LOG_FILE=/var/log/oci-lab/app.log
touch "$LOG_FILE"
chmod 0644 "$LOG_FILE"

export LAB_RUN="lab-$(date -u +%Y%m%dT%H%M%SZ)"

lab_log() {
  printf '%s level=%s app=oci-lab run_id=%s event=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$LAB_RUN" "$2" \
    >> "$LOG_FILE"
}

lab_log INFO file-created
printf 'RUN_ID=%s\n' "$LAB_RUN"
tail -n 5 "$LOG_FILE"
~~~

Ghi lại `LAB_RUN` để lọc riêng lần thực hành. Nếu mở phiên SSH mới, đặt lại `LOG_FILE`, `LAB_RUN` bằng giá trị đã ghi và khai báo lại hàm `lab_log`.

Quyền `0644` ở đây chỉ dùng cho dữ liệu mô phỏng, giúp tài khoản agent đọc được file mà không cấp quyền ghi cho mọi người. Với log thật chứa thông tin nội bộ, thiết kế nhóm hoặc ACL riêng và kiểm tra quyền của tài khoản chạy agent. Agent cần đọc được file và đi qua được toàn bộ thư mục cha.

### 5.2. Tạo log group và custom log

Trong **Logging → Log Groups**, tạo `lab-observability-logs` tại compartment lab.

Trong log group, tạo custom log `lab-app-log`, đặt retention **30 ngày**. Có thể chọn thêm agent configuration ngay trong trình tạo custom log hoặc thêm sau. Với bài này, chọn thêm cấu hình sau để quan sát rõ từng tài nguyên. Luồng tạo custom log được mô tả trong [Creating a Log](https://docs.oracle.com/en-us/iaas/Content/Logging/Task/create-logging-log.htm).

Log group là container quản lý; custom log là đích nhận dữ liệu. Tạo hai đối tượng này chưa làm cho file trên VM tự xuất hiện trong Logging.

### 5.3. Tạo agent configuration

Mở **Logging → Agent Configurations**, tạo `lab-app-agent-config` với:

| Mục cấu hình | Giá trị của bài |
| --- | --- |
| Compartment | `lab-observability` |
| Trạng thái | Enabled |
| Host group type | Dynamic group |
| Host group | `LabLogInstances` |
| Input type | Log path / Log Directory (Tail), tùy nhãn giao diện |
| Input name | `lab-app-file` |
| File path | `/var/log/oci-lab/app.log` |
| Parser | `None` |
| Message key | `message` nếu giao diện yêu cầu |
| Destination log group | `lab-observability-logs` |
| Destination log | `lab-app-log` |

Lưu cấu hình và chờ agent tải về. Cấu hình cần đồng thời chọn đúng host group, input và destination; quy trình được trình bày trong [Creating an Agent Configuration](https://docs.oracle.com/en-us/iaas/Content/Logging/Task/create-logging-agent-configuration.htm).

Chọn parser **None** để giữ nguyên từng dòng văn bản trong trường thông điệp. Các chuỗi `level=INFO` và `run_id=...` vẫn nằm trong nội dung, chưa trở thành field JSON độc lập. Nếu chuyển sang JSON parser ở một bài triển khai khác, cần phát JSON hợp lệ và thống nhất cách xử lý thời gian. Các parser được hỗ trợ được liệt kê trong [Log Inputs and Parsers](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/log_inputs_and_parsers.htm).

Nếu cấu hình có lựa chọn bật operational metrics riêng của logging agent, giữ nguyên trạng thái tắt cho bài cơ bản. Phần đó cần thiết kế thêm namespace và quyền phát metrics; không cần để thu thập file log trong bài này.

### 5.4. Phát dữ liệu mới sau khi agent sẵn sàng

Giữ phiên SSH đang có hàm `lab_log`, rồi chạy:

~~~bash
lab_log INFO collector-ready
lab_log WARN synthetic-retry
lab_log ERROR synthetic-failure
tail -n 5 "$LOG_FILE"
~~~

Phát marker sau khi agent đã nhận cấu hình giúp tránh phụ thuộc vào việc agent có đọc lại những dòng cũ hay không. Nếu chưa thấy dữ liệu, kiểm tra agent trước rồi phát một marker mới.

Trên Oracle Linux, các lệnh chẩn đoán cơ bản là:

~~~bash
sudo systemctl status unified-monitoring-agent --no-pager
sudo journalctl -u unified-monitoring-agent -n 50 --no-pager
sudo journalctl -u unified-monitoring-agent_config_downloader -n 50 --no-pager
~~~

Khi cần chủ động yêu cầu tải lại cấu hình:

~~~bash
sudo systemctl restart unified-monitoring-agent_config_downloader
~~~

Không khởi động lại toàn bộ VM chỉ để tải lại cấu hình. Việc tải cấu hình tự động có thể mất thời gian; các unit và cách kiểm tra được mô tả trong [Troubleshooting Logging](https://docs.oracle.com/en-us/iaas/Content/Logging/troubleshooting.htm).

### 5.5. Tìm bản ghi bằng Logging Search

Mở **Logging → Search**, chọn đúng region và khoảng thời gian bao gồm lúc vừa phát marker, chẳng hạn 30 phút gần nhất. Trước tiên tìm toàn bộ dữ liệu trong custom log:

~~~text
search "<COMPARTMENT_OCID>/<LOG_GROUP_OCID>/<LOG_OCID>"
| sort by datetime desc
~~~

Mở một bản ghi ở chế độ JSON, kiểm tra trường `data.message` và metadata của nguồn. Sau đó lọc theo mã lần chạy, thay giá trị minh họa bằng `LAB_RUN` thực tế:

~~~text
search "<COMPARTMENT_OCID>/<LOG_GROUP_OCID>/<LOG_OCID>"
| where data.message = '*run_id=lab-20261121T030000Z*'
| sort by datetime desc
~~~

Để xem những lỗi mô phỏng của đúng lần chạy:

~~~text
search "<COMPARTMENT_OCID>/<LOG_GROUP_OCID>/<LOG_OCID>"
| where data.message = '*run_id=lab-20261121T030000Z*'
  and data.message = '*level=ERROR*'
| sort by datetime desc
~~~

Cấu trúc scope `compartment/log-group/log` và cách tham chiếu field thuộc Logging Query Language, được mô tả trong [Logging Query Language Specification](https://docs.oracle.com/en-us/iaas/Content/Logging/Reference/query_language_specification.htm). Đây là ngôn ngữ khác MQL; không dán truy vấn `search ...` vào ô điều kiện alarm.

Nếu trường thông điệp thực tế khác do cấu hình parser, sửa đường dẫn field theo bản ghi JSON đã quan sát. Vì parser None giữ văn bản thô, truy vấn `data.level = 'ERROR'` không phù hợp với cấu hình đang dùng.

**Điểm kiểm chứng:** tìm được cả `collector-ready`, `synthetic-retry` và `synthetic-failure` của cùng một `LAB_RUN`. Việc thấy file trên VM mới chỉ chứng minh bước ghi file, chưa chứng minh bước đưa log lên OCI.

## 6. Tạo alarm CPU vượt ngưỡng

### 6.1. Xây dựng điều kiện MQL

Từ truy vấn nền, thêm ngưỡng:

~~~text
CpuUtilization[1m]{resourceId = "<INSTANCE_OCID>"}.mean() > 60
~~~

Diễn giải:

- `[1m]` là cửa sổ tổng hợp một phút.
- `resourceId` giới hạn dữ liệu vào VM của bài.
- `mean()` tính giá trị trung bình trong cửa sổ.
- `> 60` kiểm tra điều kiện vượt 60 phần trăm CPU.

Ngưỡng 60% chỉ phục vụ lab. Khi vận hành thật, đặt ngưỡng dựa trên hành vi bình thường, mức ảnh hưởng và thời gian phản ứng cần thiết.

Phân biệt **interval** với **trigger delay**. Interval quyết định cửa sổ tính thống kê; trigger delay hay `pendingDuration` yêu cầu điều kiện vi phạm duy trì đủ lâu trước khi alarm chuyển sang `FIRING`. Hai phút trigger delay không có nghĩa là chỉ lấy một điểm của cửa sổ hai phút. Cơ chế đánh giá được giải thích trong [Overview of Monitoring](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Concepts/monitoringoverview.htm).

### 6.2. Tạo định nghĩa alarm

Trong **Monitoring → Alarm Definitions**, chọn **Create Alarm**:

| Thuộc tính | Giá trị |
| --- | --- |
| Alarm name | `lab-cpu-high` |
| Alarm compartment | `lab-observability` |
| Metric compartment | Compartment chứa VM |
| Namespace | `oci_computeagent` |
| Query | MQL CPU ở trên |
| Trigger delay | 2 phút, tương ứng `PT2M` |
| Severity | `WARNING` |
| Destination | Topic `lab-ops-alerts` |
| Repeat notifications | Tắt trong lần kiểm thử đầu |
| Enable alarm | Bật |

Nếu giao diện cho chọn cách nhóm thông báo, một metric stream của một VM là đủ cho bài. Không cần gom toàn bộ instance trong compartment vào cùng điều kiện.

Điền nội dung thông báo, ví dụ:

~~~text
LAB: CPU VM vuot 60% lien tuc theo trigger delay 2 phut.
Kiem tra instance OCID, bieu do CpuUtilization va logs theo UTC.
Neu dang chay tai thu, dung cac tien trinh thu va theo doi phuc hoi.
~~~

Mẫu này có hướng dẫn xử lý và nhắc phạm vi lab. Không đưa mật khẩu hoặc dữ liệu ứng dụng nhạy cảm vào alarm body. Các trường tạo alarm được mô tả trong [Creating a Basic Alarm](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/create-alarm-basic.htm).

Lưu alarm. Nếu CPU nền thấp hơn ngưỡng và đang có dữ liệu, trạng thái ổn định mong đợi là `OK`. Xác nhận query trong định nghĩa vẫn có đúng `INSTANCE_OCID`; việc chọn đúng tên VM trong một trang khác không tự sửa query đã lưu.

### 6.3. Ví dụ thời gian đánh giá

Giả sử chuỗi dữ liệu đã đến đầy đủ:

| Cửa sổ một phút | CPU trung bình | Điều kiện `> 60` | Diễn giải |
| --- | --- | --- | --- |
| 09:00–09:01 UTC | 12% | Sai | Bình thường |
| 09:01–09:02 UTC | 78% | Đúng | Bắt đầu chuỗi vi phạm |
| 09:02–09:03 UTC | 82% | Đúng | Có thể đủ trigger delay khi được đánh giá |
| 09:03–09:04 UTC | 80% | Đúng | Vi phạm tiếp tục |
| 09:04–09:05 UTC | 15% | Sai | Điều kiện phục hồi xuất hiện |

Bảng giúp hiểu logic, không cam kết email đến đúng giây kết thúc cửa sổ. Còn có thời gian thu thập, đưa metrics lên dịch vụ, đánh giá alarm và chuyển phát thông báo. Khi điều kiện hết vi phạm, alarm có thể trở lại `OK` mà không chờ thêm một khoảng phục hồi bằng trigger delay đã cấu hình.

## 7. Kiểm thử alarm CPU và đối chiếu logs

### 7.1. Tạo tải CPU có thời hạn

Chỉ thực hiện trên VM lab đã chuẩn bị. Đoạn dưới tạo một tiến trình bận cho mỗi CPU logic, tự dừng sau khoảng bảy phút; giới hạn tối đa bốn CPU logic để tránh chạy ngoài dự kiến trên máy lớn. Có thể bấm `Ctrl+C` trong phiên chạy để dừng sớm.

Chạy trong phiên Bash SSH đang có hàm `lab_log`:

~~~bash
lab_log WARN cpu-load-started

(
  lab_cores=$(nproc)
  if [ "$lab_cores" -gt 4 ]; then
    printf 'Can dung VM lab co toi da 4 CPU logic.\n' >&2
    exit 1
  fi

  lab_cpu_pids=""

  stop_lab_load() {
    if [ -n "$lab_cpu_pids" ]; then
      kill $lab_cpu_pids 2>/dev/null || true
    fi
  }

  trap stop_lab_load EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM

  for lab_worker in $(seq 1 "$lab_cores"); do
    timeout --signal=TERM 420s sh -c 'while :; do :; done' &
    lab_cpu_pids="$lab_cpu_pids $!"
  done

  wait || true
  lab_cpu_pids=""
)

lab_log INFO cpu-load-ended
~~~

Lệnh `kill` trong hàm dọn dẹp chỉ nhắm đến PID của các tiến trình `timeout` do lần chạy này tạo. Không dùng `killall` hoặc `pkill` với tên tiến trình chung.

Trong thời gian tạo tải, dùng một cửa sổ Console khác để theo dõi `CpuUtilization` và alarm. Nếu VM dùng cơ chế CPU chia sẻ hoặc giới hạn hiệu năng, mức CPU quan sát có thể khác dự kiến. Chọn ngưỡng thử thấp hơn mức tải thực tế và cao hơn mức nền khi cần, đồng thời ghi rõ cấu hình đã dùng. Không tăng kích cỡ VM chỉ để làm cho alarm phát thông báo.

### 7.2. Kiểm tra từng mắt xích

Ghi nhận các bằng chứng sau:

1. Biểu đồ CPU có dữ liệu của đúng VM và vượt ngưỡng đủ thời gian.
2. Lịch sử `lab-cpu-high` xuất hiện trạng thái `FIRING`.
3. Email từ Notifications chứa đúng tên alarm và trạng thái liên quan.
4. Logging Search tìm được `cpu-load-started` của đúng `LAB_RUN`.
5. Sau khi tải kết thúc, CPU giảm và alarm trở về `OK`.
6. Có thông báo phục hồi tương ứng và tìm được marker `cpu-load-ended`.

Nếu tải đã kết thúc trước khi điều kiện duy trì đủ lâu, kết quả `OK` có thể hoàn toàn đúng. Hãy kiểm tra biểu đồ trước khi sửa alarm.

Bằng chứng log và alarm không cần có timestamp giống từng giây. Log ghi thời điểm phát marker; metric biểu diễn thống kê theo cửa sổ; thông báo có thời điểm chuyển phát. Dùng UTC để đặt chúng trên cùng dòng thời gian.

### 7.3. Mẫu ghi nhận kết quả

| Sự kiện | Thời điểm UTC quan sát | Bằng chứng |
| --- | --- | --- |
| Bắt đầu tải | Điền khi chạy | Log `cpu-load-started` |
| CPU vượt ngưỡng | Điền từ biểu đồ | Query có đúng `resourceId` |
| Alarm FIRING | Điền từ lịch sử | Tên và OCID alarm |
| Nhận email FIRING | Điền từ hộp thư | Nội dung thông báo |
| Kết thúc tải | Điền khi chạy | Log `cpu-load-ended` |
| Alarm trở lại OK | Điền từ lịch sử | Có metrics mới dưới ngưỡng |

Đây là mẫu điền bằng kết quả thật của người thực hành, không phải kết quả đã chạy sẵn. Việc CPU cao chứng minh tải trên host; để kết luận ứng dụng lỗi còn cần logs, kiểm tra chức năng hoặc chỉ số ứng dụng.

## 8. Tạo alarm mất dữ liệu giám sát

### 8.1. Tách thiếu dữ liệu khỏi giá trị bằng không

CPU bằng 0% là một giá trị đo được. Không có điểm metric mới là một tình trạng khác: có thể do plugin, kết nối, IAM hoặc instance ngừng hoạt động. Alarm CPU cao không thay thế được việc giám sát tính liên tục của dữ liệu.

Tạo alarm thứ hai `lab-compute-metrics-missing`, dùng cùng metric compartment, namespace và destination topic, với query:

~~~text
CpuUtilization[1m]{resourceId = "<INSTANCE_OCID>"}.groupBy(resourceId).absent()
~~~

Đặt trigger delay **5 phút** và severity `WARNING`. Nội dung thông báo cần nêu rõ “không nhận được metrics”, kèm hướng kiểm tra plugin và kết nối. Không ghi rằng VM chắc chắn đã hỏng.

`absent()` trả kết quả có/không thiếu metric trong interval; `groupBy(resourceId)` giúp nhóm các stream của instance. Trigger delay năm phút yêu cầu tình trạng thiếu dữ liệu duy trì theo cấu hình. **Absence detection period** mặc định hai giờ là giới hạn hành vi trả giá trị khi thiếu kéo dài, không phải thời gian phải chờ hai giờ mới báo. Oracle giải thích các điểm này trong [Creating an Absence Alarm](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/create-alarm-absence.htm).

### 8.2. Mô phỏng gián đoạn một nguồn metrics

Chỉ làm sau khi cả hai alarm đã có dữ liệu nền và quá trình thử CPU đã kết thúc:

1. Phát marker trên VM: `lab_log WARN metrics-plugin-test-started`.
2. Trong tab **Oracle Cloud Agent**, tạm tắt riêng **Compute Instance Monitoring** của VM lab.
3. Giữ **Custom Logs Monitoring** hoạt động.
4. Theo dõi Metrics Explorer cho đến khi không còn điểm CPU mới; dữ liệu quá khứ vẫn được hiển thị.
5. Đợi alarm `lab-compute-metrics-missing` chuyển `FIRING` và kiểm tra email.
6. Trong thời gian đó, chạy `lab_log INFO logging-still-working` và tìm marker này trên Logging.
7. Bật lại Compute Instance Monitoring ngay sau khi thu đủ bằng chứng.
8. Chờ có điểm CPU mới, kiểm tra alarm thiếu metrics trở về `OK`.
9. Phát `lab_log INFO metrics-plugin-test-ended`.

Thay đổi trạng thái plugin cần quyền cập nhật instance đã nêu ở phần IAM. Nếu môi trường không giao quyền đó, quản trị viên thực hiện các bước tắt/bật trong cùng buổi thực hành; phần tạo alarm và kiểm chứng vẫn do người học thực hiện.

Chỉ tắt plugin mục tiêu giúp giữ nguyên đường log để quan sát. Sau bài phải xác nhận plugin đã hoạt động trở lại, kể cả khi trước đó bạn phải dừng kiểm thử giữa chừng.

Nếu thiếu metrics kéo dài quá absence detection period, đừng coi riêng trạng thái alarm là bằng chứng nguồn đo đã phục hồi. Kiểm tra thêm timestamp của điểm metric mới. Tương tự, nhận được log mới chỉ chứng minh đường log đang hoạt động, chưa chứng minh đường metrics đã hoạt động.

## 9. Tự động hóa định nghĩa alarm bằng OCI CLI

Phần này là lựa chọn thay cho bước tạo alarm CPU trong Console, giúp thực hành cấu hình có thể lặp lại. Nếu đã tạo `lab-cpu-high` ở trên, dùng lệnh đọc để kiểm tra hoặc bỏ qua lệnh tạo; không tạo thêm bản sao chỉ để thử cú pháp.

Chạy bằng Bash trong Cloud Shell hoặc terminal có OCI CLI đã được xác thực:

~~~bash
export REGION='<REGION>'
export COMPARTMENT_OCID='<COMPARTMENT_OCID>'
export INSTANCE_OCID='<INSTANCE_OCID>'
export TOPIC_OCID='<TOPIC_OCID>'

oci monitoring alarm create \
  --region "$REGION" \
  --compartment-id "$COMPARTMENT_OCID" \
  --metric-compartment-id "$COMPARTMENT_OCID" \
  --display-name 'lab-cpu-high' \
  --namespace 'oci_computeagent' \
  --query-text "CpuUtilization[1m]{resourceId = \"$INSTANCE_OCID\"}.mean() > 60" \
  --pending-duration 'PT2M' \
  --severity 'WARNING' \
  --destinations "[\"$TOPIC_OCID\"]" \
  --is-enabled true \
  --body 'LAB: Kiem tra CPU, instance OCID va application logs theo UTC.' \
  --query 'data.id' \
  --raw-output
~~~

Lưu OCID trả về vào hồ sơ thực hành. Để đọc định nghĩa đã tạo:

~~~bash
export ALARM_OCID='<ALARM_OCID>'

oci monitoring alarm get \
  --region "$REGION" \
  --alarm-id "$ALARM_OCID"
~~~

`--compartment-id` chọn nơi chứa alarm; `--metric-compartment-id` chọn nơi lấy metrics. Bài cố ý dùng cùng một giá trị, nhưng hai vai trò này khác nhau. `--destinations` nhận một JSON array chứa OCID topic; `PT2M` là biểu diễn ISO 8601 của hai phút. Các tham số được mô tả trong [OCI CLI: monitoring alarm create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/monitoring/alarm/create.html).

Lệnh create chỉ tạo tài nguyên mới, không phải lệnh đồng bộ trạng thái mong muốn. Khi dùng cho nhiều môi trường, cần quản lý OCID, cập nhật tài nguyên đã tồn tại và tách giá trị cấu hình theo region/compartment. Không nhúng OCID của lab cá nhân vào template dùng chung.

## 10. Điều tra sự cố theo đường dữ liệu

Thứ tự kiểm tra hữu ích là **nguồn → agent → quyền và mạng → dịch vụ nhận → query → thông báo**. Mỗi lần chỉ thay một cấu hình để quan sát được tác động.

| Hiện tượng | Kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| Không có `oci_computeagent` hoặc CPU rỗng | Region, compartment, plugin và thời gian dữ liệu | Xác nhận đúng VM, plugin chạy và kết nối dịch vụ hoạt động |
| CPU trên VM cao nhưng alarm vẫn OK | Mean trong cửa sổ, ngưỡng, dimension và trigger delay | Đọc query đã lưu; dùng dữ liệu Monitoring để đối chiếu |
| Alarm đã FIRING nhưng không có email | Topic đích và trạng thái subscription | Kiểm tra `ACTIVE`, spam và phát message thử vào đúng topic |
| Agent configuration đã tạo nhưng không có log | Host group, matching rule, destination và file path | So lại OCID instance, group và đường dẫn tuyệt đối |
| File có dữ liệu nhưng Search không thấy | Quyền đọc file, trạng thái agent và bản ghi mới | Xem journal rồi phát marker mới sau khi cấu hình được tải |
| Lỗi truy cập API của agent | Dynamic group, policy và phạm vi compartment | Kiểm tra principal của VM và nơi chứa cấu hình/đích log |
| Search rỗng nhưng agent có vẻ bình thường | Region, time range, scope và field | Tìm toàn bộ log trước, sau đó thêm từng bộ lọc |
| Alarm thiếu metrics không kích hoạt | Dữ liệu nền, plugin đã thực sự dừng và interval | Kiểm tra timestamp mới nhất và chờ đủ chuỗi đánh giá |
| Có log bị trùng | Nhiều configuration hoặc pattern cùng đọc một file | Loại bỏ cấu hình thu thập chồng lấn |
| Alarm thay đổi liên tục | Ngưỡng quá sát nền hoặc tải dao động | Điều chỉnh theo dữ liệu thực, giữ khả năng phát hiện sự cố |

Những đường dẫn hữu ích khi xử lý log trên Oracle Linux:

~~~bash
sudo tail -n 50 /var/log/unified-monitoring-agent/unified-monitoring-agent.log
sudo tail -n 50 /var/log/oracle-cloud-agent/plugins/unifiedmonitoring/unifiedmonitoring.log
ls -ld /var/log/oci-lab
ls -l /var/log/oci-lab/app.log
date -u
~~~

Các vị trí log của agent và plugin được mô tả trong [Troubleshooting Logging](https://docs.oracle.com/en-us/iaas/Content/Logging/troubleshooting.htm). Dữ liệu chẩn đoán có thể chứa định danh hạ tầng; chỉ chia sẻ phần cần thiết khi yêu cầu hỗ trợ.

Alarm CPU và log `synthetic-failure` cùng thời điểm chưa chứng minh CPU gây lỗi ứng dụng. Trong bài, marker lỗi được tạo có chủ đích. Trong tình huống thật, cần thêm request ID, trạng thái ứng dụng và dữ liệu trước/sau sự kiện để kiểm tra giả thuyết.

## 11. Kiểm soát chi phí, dữ liệu và tính sẵn sàng

### 11.1. Giới hạn dữ liệu thu thập

Bài chỉ đọc một file và phát một lượng nhỏ marker. Tránh mở rộng input thành `/var/log/**` khi chưa hiểu khối lượng và nội dung. Mỗi nguồn log bổ sung cần mục đích, người được đọc và chính sách giữ dữ liệu tương ứng.

Retention custom log của bài là 30 ngày. Logging hỗ trợ các mốc 30 ngày đến 180 ngày; thay đổi retention có thể khiến dữ liệu cũ không còn tìm kiếm được. Không dùng việc tăng retention sau này để kỳ vọng khôi phục dữ liệu đã hết thời hạn. Tham khảo [Editing a Log](https://docs.oracle.com/iaas/Content/Logging/Task/update-logging-log.htm).

Theo dõi mức dùng thực tế của Compute, dung lượng log và các dịch vụ đi kèm trên tenancy. Không giả định toàn bộ bài luôn miễn phí. Nếu bổ sung lưu trữ dài hạn, xác định thêm đích lưu, thời hạn và chi phí của đường chuyển dữ liệu trước khi triển khai.

### 11.2. Thiết kế thông báo có người xử lý

Mỗi alarm dùng trong vận hành cần người phụ trách, ngữ cảnh tài nguyên và hướng xử lý ngắn gọn. Một email đã đến hộp thư thử nghiệm chưa chứng minh có người trực nhận và xử lý đúng hạn.

Nếu có bảo trì định kỳ, dùng cửa sổ suppression có thời hạn để kiểm soát thông báo và đặt lịch kiểm tra kết thúc bảo trì. Suppression tác động đến thông báo, không tự khôi phục agent, mạng hoặc ứng dụng. Sau bảo trì phải kiểm tra nguồn dữ liệu và trạng thái tài nguyên.

Trong môi trường cần sẵn sàng cao, triển khai giám sát cho từng instance và các kiểm tra chức năng của dịch vụ. Một metric CPU của một VM chỉ phản ánh một phần hệ thống; chưa đại diện cho trải nghiệm người dùng hoặc trạng thái cơ sở dữ liệu Oracle phía sau.

### 11.3. Giữ log hữu ích mà không phát tán bí mật

Marker trong bài không chứa thông tin người dùng. Với ứng dụng thật, tránh ghi token, mật khẩu, private key hoặc toàn bộ dữ liệu nhạy cảm vào log. Chuẩn hóa timestamp, mức độ, tên dịch vụ và mã tương quan để điều tra được mà không cần thu thập quá nhiều nội dung.

## 12. Nghiệm thu và dọn tài nguyên

### 12.1. Tiêu chí hoàn thành thực hành

| Hạng mục | Điều kiện đạt |
| --- | --- |
| Phạm vi | Ghi được region, compartment và instance OCID đúng |
| IAM | Người thao tác có quyền đúng phạm vi; agent thuộc dynamic group mục tiêu |
| Metrics nền | Có điểm `CpuUtilization` mới của VM |
| Notifications | Subscription `ACTIVE` và nhận được message thử |
| Custom log | Tìm được marker mới theo `LAB_RUN` trong Logging Search |
| Alarm CPU | Có bằng chứng `FIRING` và trở lại `OK` sau thử tải |
| Alarm thiếu metrics | Có bằng chứng kích hoạt khi dừng nguồn và phục hồi khi metrics mới xuất hiện |
| Vận hành sau thử | Không còn tải CPU mô phỏng; plugin cần thiết đã bật lại |
| Hồ sơ | Ghi thời điểm UTC, query, cấu hình ngưỡng và các bằng chứng liên quan |

Lưu kết quả thật vào hồ sơ thực hành của bạn, che thông tin nhận diện nếu chia sẻ công khai. Không đánh dấu đạt một bước chỉ vì tài nguyên đã tạo thành công.

### 12.2. Dọn dẹp theo quan hệ phụ thuộc

Sau khi lưu bằng chứng:

1. Dừng tải thử nếu còn và xác nhận CPU trở về nền.
2. Bật lại Compute Instance Monitoring nếu giữ VM; kiểm tra có điểm metric mới.
3. Disable hoặc xóa hai alarm lab để kết thúc việc gửi thông báo thử.
4. Disable rồi xóa agent configuration `lab-app-agent-config` để dừng đọc file.
5. Xóa custom log `lab-app-log` và log group `lab-observability-logs` khi không cần dữ liệu nữa.
6. Xóa subscription và topic `lab-ops-alerts` nếu chúng chỉ phục vụ bài.
7. Gỡ policy và dynamic group được tạo riêng cho bài khi không còn tài nguyên sử dụng.
8. Nếu giữ VM, chỉ xóa file `/var/log/oci-lab/app.log` và thư mục lab sau khi chắc chắn cấu hình thu thập đã dừng và không còn dữ liệu cần giữ.
9. Nếu VM được tạo riêng cho bài, kết thúc VM theo quy trình lab và kiểm tra cả boot volume, volume bổ sung hoặc tài nguyên mạng phát sinh.

Không xóa group, topic, policy hoặc VM dùng chung chỉ vì tên gần giống tài nguyên của bài. Việc xóa log hoặc VM phải diễn ra sau khi đã lưu các bằng chứng cần thiết.

Khi kết thúc, bạn cần chỉ ra được bốn mắt xích bằng bằng chứng quan sát: **VM phát tín hiệu, OCI nhận dữ liệu, alarm đánh giá điều kiện, và người phụ trách nhận thông báo**. Đó là cơ sở để mở rộng cùng cách làm sang Compute nhiều instance và các dịch vụ OCI khác.

