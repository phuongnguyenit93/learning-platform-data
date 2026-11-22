# Ops Agent cho Compute Engine

Ops Agent là tác tử thu thập telemetry chính của Google Cloud dành cho máy ảo Compute Engine. Agent chạy ngay trên VM, đọc log của hệ điều hành và ứng dụng, thu thập chỉ số tài nguyên, đồng thời có thể nhận trace và metric tùy chỉnh qua OpenTelemetry Protocol (OTLP). Dữ liệu sau đó được gửi đến các dịch vụ Cloud Observability tương ứng để truy vấn, dựng dashboard, tạo cảnh báo và điều tra sự cố.

Trong module CLOUD_PROVIDERS_GCP, Ops Agent là phần kết nối giữa máy ảo Compute Engine và năng lực theo dõi độ tin cậy, hiệu năng, vận hành của Google Cloud. Khi triển khai một workload trên VM, người vận hành cần biết agent thu thập loại dữ liệu nào, cài đặt và cấp quyền ra sao, cấu hình pipeline thế nào, quản lý agent trên nhiều VM và xác minh dữ liệu đã đến nơi.

Sau bài học, bạn có thể:

- Giải thích vai trò của Ops Agent và luồng logs, metrics, traces.
- Kiểm tra điều kiện IAM, API, hệ điều hành và network trước khi cài agent.
- Cài đặt và kiểm tra Ops Agent trên Linux hoặc Windows.
- Mở rộng cấu hình bằng receivers, processors và pipelines.
- Thu thập log ứng dụng, metric tùy chỉnh và trace OTLP.
- Quản lý agent trên một fleet VM, theo dõi tình trạng và xử lý lỗi thu thập dữ liệu.

## 1. Ops Agent nằm ở đâu trong kiến trúc Observability?

Observability giúp trả lời ba nhóm câu hỏi khi vận hành hệ thống:

- **Logs**: Điều gì đã xảy ra? Log ghi lại sự kiện, lỗi, request và hoạt động của ứng dụng.
- **Metrics**: Hệ thống đang hoạt động ra sao? Metric biểu diễn giá trị theo thời gian như CPU, bộ nhớ, dung lượng đĩa, độ trễ và số request.
- **Traces**: Một request đi qua những thành phần nào và mất thời gian ở đâu? Trace liên kết các span để quan sát đường đi của một request xuyên qua ứng dụng.

Ops Agent thu thập các tín hiệu này trên Compute Engine. Thành phần xử lý log sử dụng Fluent Bit; thành phần thu thập metrics và traces sử dụng OpenTelemetry Collector.

~~~mermaid
flowchart LR
    subgraph VM["Compute Engine VM"]
        OS["Hệ điều hành"]
        APP["Ứng dụng"]
        OTel["OpenTelemetry SDK"]
        Agent["Ops Agent"]
        OS -->|system logs, host metrics| Agent
        APP -->|application logs| Agent
        OTel -->|OTLP gRPC| Agent
    end
    Agent -->|Logs| CL["Cloud Logging"]
    Agent -->|Metrics| CM["Cloud Monitoring"]
    Agent -->|OTLP traces| CT["Cloud Trace"]
    CL --> LE["Logs Explorer / log-based metrics"]
    CM --> ME["Metrics Explorer / dashboards / alerts"]
    CT --> TE["Trace Explorer"]
~~~

| Tín hiệu | Nguồn thường gặp | Nơi nhận trong Google Cloud |
|---|---|---|
| Logs | Syslog, journald, Windows Event Log, file log ứng dụng, log từ receiver | Cloud Logging |
| Metrics | CPU, memory, disk, network, process, IIS, SQL Server, Prometheus hoặc OTLP | Cloud Monitoring |
| Traces | Ứng dụng được instrument bằng OpenTelemetry SDK và gửi OTLP | Cloud Trace |

Ops Agent có cấu hình YAML thống nhất, hỗ trợ các bản phân phối Linux và Windows được liệt kê trong tài liệu tương thích. Agent có thể thu thập log từ file, systemd journal, Windows Event Log, TCP, Fluent Forward và các tích hợp ứng dụng bên thứ ba. Các metric hệ thống phổ biến được thu thập theo cấu hình mặc định.

Một số giới hạn cần nhớ:

- Ops Agent được thiết kế cho Compute Engine; tài liệu cũng có hướng dẫn riêng cho Bare Metal Solution. Không cài agent này lên Amazon EC2 hoặc máy chủ on-premises như thể đó là VM Compute Engine.
- Log được gửi đến Cloud Logging và metric được gửi đến Cloud Monitoring. Muốn chuyển log đến BigQuery, Cloud Storage hoặc hệ thống đích khác, hãy cấu hình log sink trong Cloud Logging.
- Trace tùy chỉnh cần receiver OTLP, ứng dụng được instrument và quyền ghi Cloud Trace.
- Agent không tự tạo ra trace nghiệp vụ nếu ứng dụng chưa phát sinh span bằng OpenTelemetry.

## 2. Chuẩn bị trước khi cài đặt

### 2.1. Chọn VM và hệ điều hành được hỗ trợ

Kiểm tra hệ điều hành của VM trong danh sách supported operating systems của Google Cloud trước khi cài. Phiên bản Linux hoặc Windows đã hết hỗ trợ có thể khiến repository cài đặt không còn gói tương thích.

Container-Optimized OS có cơ chế tích hợp Cloud Logging riêng; hãy dùng hướng dẫn dành cho hệ điều hành này thay vì tự cài Ops Agent như trên Debian, Ubuntu hoặc Windows Server.

### 2.2. Bật API cần thiết

Project cần bật Cloud Logging API và Cloud Monitoring API:

~~~bash
gcloud services enable logging.googleapis.com monitoring.googleapis.com --project=PROJECT_ID
~~~

Thay PROJECT_ID bằng project chứa các VM cần theo dõi. Nếu sử dụng OTLP để gửi trace, hãy kiểm tra thêm quyền và cấu hình Cloud Trace theo phần 7.

Khi bật thu thập trace OTLP, bật thêm Cloud Trace API:

~~~bash
gcloud services enable cloudtrace.googleapis.com --project=PROJECT_ID
~~~

### 2.3. Cấp danh tính cho VM

Ops Agent sử dụng danh tính service account được gắn vào Compute Engine VM thông qua Application Default Credentials (ADC). Service account này cần quyền ghi dữ liệu quan sát:

| IAM role | Mục đích |
|---|---|
| roles/logging.logWriter | Ghi log vào Cloud Logging |
| roles/monitoring.metricWriter | Ghi metric vào Cloud Monitoring |
| roles/cloudtrace.agent | Ghi trace vào Cloud Trace khi bật thu thập trace OTLP |

Hai role đầu là quyền cơ bản cho log và metric. Role Cloud Trace Agent chỉ cần khi agent gửi trace. Nên gắn service account riêng cho workload hoặc nhóm workload, sau đó cấp đúng role cần thiết ở phạm vi project phù hợp.

Ví dụ cấp quyền cho service account của VM:

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:vm-observability@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:vm-observability@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/monitoring.metricWriter"
~~~

Nếu bật trace OTLP, cấp thêm:

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:vm-observability@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudtrace.agent"
~~~

VM cũng cần OAuth access scope cho API tương ứng. Với VM mới, scope cloud-platform thường là lựa chọn đơn giản khi quyền IAM đã được giới hạn bằng service account. Nếu VM cũ dùng scope hẹp, hãy kiểm tra scope Logging và Monitoring trước khi kết luận IAM role đã cấp là đủ.

Không tải service account key JSON về VM để chạy agent. Danh tính gắn với VM và ADC giúp tránh quản lý key dài hạn trên đĩa.

### 2.4. Kiểm tra agent cũ và đường truyền

Trước khi cài, kiểm tra VM có cài Cloud Logging agent hoặc Cloud Monitoring agent đời cũ hay không. Chạy đồng thời agent mới và agent cũ có thể tạo log trùng lặp hoặc xung đột metric. Nếu cần chuyển đổi, lưu lại cấu hình cũ, lập kế hoạch chuyển receiver/pipeline rồi gỡ agent cũ theo hướng dẫn của Google Cloud.

VM cần truy cập được Cloud Logging và Cloud Monitoring API qua mạng. Nếu workload đi qua proxy hoặc firewall egress, hãy bảo đảm các endpoint cần thiết có thể truy cập. Ops Agent hỗ trợ proxy, nhưng cần cấu hình theo môi trường của VM.

## 3. Cài Ops Agent trên một VM

### 3.1. Cài trên Linux

Kết nối SSH vào VM, chuyển đến thư mục có quyền ghi và chạy script cài đặt chính thức:

~~~bash
curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
sudo bash add-google-cloud-ops-agent-repo.sh --also-install
~~~

Script thêm repository của Google Cloud và cài phiên bản agent mới nhất. Sau khi cài đặt, agent được khởi động tự động.

Có thể dùng tùy chọn --dry-run để xem các lệnh mà script dự định thực thi. Khi triển khai production, hãy xem xét pin phiên bản theo major version để tránh tự động chuyển sang major release có thay đổi tương thích. Cú pháp của script:

~~~bash
sudo bash add-google-cloud-ops-agent-repo.sh --also-install --version="MAJOR_VERSION.*.*"
~~~

Chọn major version đang được tổ chức kiểm thử và hỗ trợ; không sao chép một số phiên bản ví dụ cũ mà chưa kiểm tra vòng đời phát hành hiện tại.

### 3.2. Cài trên Windows

Mở PowerShell bằng quyền Administrator trên VM, tải và chạy script cài đặt:

~~~powershell
(New-Object Net.WebClient).DownloadFile(
  "https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.ps1",
  "$env:UserProfile\add-google-cloud-ops-agent-repo.ps1"
)
Invoke-Expression "$env:UserProfile\add-google-cloud-ops-agent-repo.ps1 -AlsoInstall"
~~~

Sau khi cài đặt, kiểm tra service trong Windows Services hoặc dùng PowerShell ở phần 4.

### 3.3. Cài agent ngay khi tạo VM

Nếu muốn mọi VM mới đều có telemetry từ lúc khởi động, có thể cài Ops Agent trong quy trình tạo VM bằng startup script hoặc cơ chế quản lý cấu hình của tổ chức. Với fleet lớn, cân nhắc VM Extension Manager policies để triển khai, cập nhật phiên bản và áp dụng cấu hình tập trung.

Đối với một vài VM thử nghiệm, cài trực tiếp là cách nhanh để xác nhận log và metric. Khi số lượng VM tăng, hãy chuyển sang cách triển khai có thể lặp lại, kiểm soát phiên bản và kiểm tra được trạng thái từng máy.

## 4. Kiểm tra trạng thái và vận hành agent

### 4.1. Kiểm tra service

Trên Linux:

~~~bash
sudo systemctl status "google-cloud-ops-agent*"
~~~

Để khởi động lại agent sau khi chỉnh cấu hình:

~~~bash
sudo systemctl restart google-cloud-ops-agent
~~~

Trên Windows, kiểm tra service:

~~~powershell
Get-Service google-cloud-ops-agent*
~~~

Khởi động lại:

~~~powershell
Restart-Service google-cloud-ops-agent -Force
~~~

Agent có các thành phần xử lý logs và metrics. Khi xem trạng thái, kiểm tra các thành phần liên quan đều khởi động bình thường và không liên tục restart.

### 4.2. Xác nhận dữ liệu đã đến Google Cloud

Một service ở trạng thái Running chưa đủ để kết luận telemetry đã được ingest thành công. Hãy kiểm tra cả dữ liệu đầu ra:

- Trong Logs Explorer, lọc theo resource type gce_instance và tên VM, sau đó tìm log hệ điều hành hoặc log ứng dụng vừa phát sinh.
- Trong Metrics Explorer, tìm các metric hệ thống có tiền tố agent.googleapis.com, chọn đúng VM và xác nhận có time series mới.
- Nếu dùng trace OTLP, mở Trace Explorer và tìm trace theo service hoặc khoảng thời gian kiểm thử.
- Kiểm tra timestamp, project, zone và instance_id để chắc chắn dữ liệu thuộc đúng VM.

Có thể tạo một log thử nghiệm có nội dung nhận diện rõ, sau đó truy vấn lại trong Logs Explorer. Với metric, tạo chart CPU hoặc memory cho VM và kiểm tra điểm dữ liệu được cập nhật theo chu kỳ thu thập.

## 5. Hiểu cấu hình YAML của Ops Agent

Ops Agent có cấu hình mặc định tích hợp sẵn cho các log và metric phổ biến. Bạn không chỉnh sửa trực tiếp cấu hình mặc định; thay vào đó, tạo file cấu hình người dùng để bổ sung hoặc ghi đè các thành phần.

Đường dẫn cấu hình:

| Hệ điều hành | File cấu hình |
|---|---|
| Linux | /etc/google-cloud-ops-agent/config.yaml |
| Windows | C:\Program Files\Google\Cloud Operations\Ops Agent\config\config.yaml |

File cấu hình người dùng được hợp nhất với cấu hình tích hợp khi agent khởi động lại. Nếu cần ghi đè một receiver, processor hoặc pipeline có sẵn, khai báo cùng identifier để thay cấu hình của thành phần đó.

Một số thiết lập mặc định đáng chú ý:

- Linux thu thập log từ /var/log/messages và /var/log/syslog, đồng thời thu thập host metrics với chu kỳ 60 giây.
- Windows thu thập các channel Event Log System, Application và Security; agent cũng thu thập host metrics cùng metric IIS và SQL Server khi các thành phần tương ứng có mặt.

Vì cấu hình người dùng được hợp nhất với cấu hình tích hợp, thêm một pipeline mới thường không làm mất pipeline mặc định. Nếu muốn thay đổi pipeline mặc định, hãy khai báo lại đúng identifier của pipeline đó.

Ba khối chính:

| Khối | Vai trò |
|---|---|
| receivers | Khai báo nguồn log hoặc metric mà agent cần thu thập |
| processors | Phân tích, chuyển đổi, lọc hoặc bổ sung trường dữ liệu |
| service.pipelines | Kết nối receiver và processor thành luồng xử lý |

Một receiver có thể được dùng trong nhiều pipeline. Thứ tự receiver trong pipeline không quan trọng, nhưng thứ tự processor có ý nghĩa vì mỗi bản ghi đi qua processor theo thứ tự đã khai báo.

~~~mermaid
flowchart LR
    R["Receiver<br/>Nguồn dữ liệu"] --> P1["Processor 1<br/>Parse / filter"]
    P1 --> P2["Processor 2<br/>Transform"]
    P2 --> PL["Pipeline"]
    PL --> DEST["Cloud Logging hoặc<br/>Cloud Monitoring"]
~~~

Sau khi sửa config.yaml, phải restart agent để cấu hình mới có hiệu lực. Nếu file YAML sai cú pháp hoặc khai báo receiver không hợp lệ, agent có thể không khởi động được.

## 6. Thu thập log ứng dụng

### 6.1. Thêm file log vào pipeline

Giả sử ứng dụng Orders ghi mỗi sự kiện thành một dòng JSON tại /var/log/orders/orders.json. Có thể khai báo file receiver và processor parse_json:

~~~yaml
logging:
  receivers:
    orders_json:
      type: files
      include_paths:
        - /var/log/orders/*.json

  processors:
    parse_orders_json:
      type: parse_json

  service:
    pipelines:
      orders_pipeline:
        receivers: [orders_json]
        processors: [parse_orders_json]
~~~

Trong ví dụ:

1. Receiver orders_json đọc các file khớp đường dẫn.
2. Processor parse_orders_json chuyển nội dung JSON thành các trường trong jsonPayload.
3. Pipeline orders_pipeline kết nối nguồn và bước xử lý.
4. Ops Agent gửi log đã xử lý đến Cloud Logging.

Tài khoản chạy agent cần đọc được các file log. Nếu ứng dụng tạo file với permission quá chặt, agent có thể bỏ qua hoặc không đọc được dữ liệu. Kiểm tra quyền thư mục, owner và cách ứng dụng rotate file.

### 6.2. Xử lý log có cấu trúc

Log JSON giúp truy vấn chính xác hơn so với một chuỗi text dài. Ví dụ, một bản ghi ứng dụng có thể chứa:

~~~json
{
  "timestamp": "2026-11-19T08:30:00Z",
  "severity": "ERROR",
  "service": "orders-api",
  "request_id": "req-12345",
  "message": "Database connection timeout",
  "duration_ms": 3200
}
~~~

Sau khi parse, các trường nằm trong jsonPayload và có thể được dùng trong Logs Explorer. Nếu muốn đưa một trường về cấu trúc LogEntry chuẩn, processor modify_fields có thể di chuyển dữ liệu từ jsonPayload sang các trường như severity hoặc httpRequest.

Với log dạng text, parse_regex có thể tách các trường bằng named capture groups. Với stack trace nhiều dòng của Java, processor parse_multiline có thể ghép các dòng exception thành một LogEntry dễ đọc hơn.

### 6.3. Chọn nguồn log hợp lý

Ops Agent hỗ trợ nhiều nguồn log:

- files: đọc file theo đường dẫn và wildcard.
- systemd_journald: đọc log từ systemd journal trên Linux.
- syslog: nhận Syslog qua TCP hoặc UDP trên Linux.
- windows_event_log: đọc các channel của Windows Event Log.
- tcp: nhận log JSON qua TCP.
- fluent_forward: nhận log qua Fluent Forward protocol.

Không nên thu thập toàn bộ file trong /var/log theo wildcard rộng nếu không có nhu cầu rõ ràng. Chọn đúng file, loại bỏ log lặp hoặc log không cần thiết tại nguồn và tránh gửi dữ liệu nhạy cảm như password, token hoặc thông tin cá nhân vào Cloud Logging.

## 7. Thu thập metrics và traces tùy chỉnh

### 7.1. Host metrics

Trên Linux, cấu hình mặc định dùng receiver hostmetrics với chu kỳ thu thập 60 giây. Bạn có thể ghi đè receiver cùng identifier để đổi chu kỳ:

~~~yaml
metrics:
  receivers:
    hostmetrics:
      type: hostmetrics
      collection_interval: 30s
~~~

Ví dụ này thay chu kỳ thu thập host metrics từ 60 giây thành 30 giây. Chu kỳ ngắn hơn có thể giúp phát hiện thay đổi nhanh hơn nhưng làm tăng số mẫu metric được gửi và có thể ảnh hưởng chi phí. Hãy chọn khoảng thời gian dựa trên yêu cầu cảnh báo và độ chi tiết cần quan sát.

Các nhóm metric hệ thống thường gồm CPU, memory, disk, network, swap và process. Một số metric chỉ có trên Linux; Windows có thêm các receiver như IIS và MSSQL.

### 7.2. Metric từ ứng dụng và Prometheus

Ops Agent có thể thu thập metric từ các ứng dụng bên thứ ba được hỗ trợ, receiver Prometheus hoặc receiver OTLP. Trước khi thêm receiver, hãy xác định ứng dụng đang expose metric theo định dạng nào và kiểm tra phiên bản agent có hỗ trợ receiver đó.

Khi mở rộng metric, cần quản lý label có cardinality cao. Không đưa request ID, user ID hoặc giá trị thay đổi liên tục vào label metric vì số lượng time series có thể tăng rất nhanh. Với dữ liệu có tính định danh từng request, log hoặc trace thường phù hợp hơn.

### 7.3. Thu thập trace qua OTLP

Để nhận metric và trace từ ứng dụng instrument bằng OpenTelemetry, Ops Agent cần phiên bản 2.37.0 trở lên và cấu hình OTLP receiver. Ví dụ cấu hình receiver và hai pipeline:

~~~yaml
combined:
  receivers:
    otlp:
      type: otlp

metrics:
  service:
    pipelines:
      otlp:
        receivers: [otlp]

traces:
  service:
    pipelines:
      otlp:
        receivers: [otlp]
~~~

Ứng dụng dùng OpenTelemetry SDK hoặc agent tương ứng để gửi OTLP đến receiver trên VM. Receiver OTLP của Ops Agent hỗ trợ gRPC; HTTP transport không được hỗ trợ trong cấu hình này. Receiver OTLP không thu thập log trực tiếp, vì vậy log ứng dụng vẫn cần pipeline logging riêng.

Metric OTLP được gửi đến Cloud Monitoring, span được gửi đến Cloud Trace. Service account gắn vào VM cần quyền ghi trace thông qua roles/cloudtrace.agent; hai role logWriter và metricWriter mặc định không bao gồm quyền này.

Nếu chỉ cần metric hoặc chỉ cần trace, hãy cấu hình pipeline cho tín hiệu tương ứng. Nếu ứng dụng gửi một tín hiệu mà không có pipeline nhận tín hiệu đó, agent sẽ loại bỏ dữ liệu.

## 8. Quản lý Ops Agent trên nhiều VM

Cài thủ công phù hợp khi thử nghiệm một máy. Với hàng chục hoặc hàng trăm VM, nhóm vận hành cần chính sách cài đặt, nâng cấp và cấu hình thống nhất.

### 8.1. VM Extension Manager policies

VM Extension Manager cho phép tạo extension policy để cài Ops Agent trên fleet Compute Engine. Policy có thể áp dụng toàn project hoặc trong một zone, giữ agent ở phiên bản mong muốn và phân phối cấu hình tùy chỉnh. Chính sách ở cấp folder và organization có trạng thái Preview theo tài liệu hiện hành; cần kiểm tra trạng thái hỗ trợ trước khi đưa vào quy trình production.

Một quy trình quản lý fleet có thể gồm:

1. Chọn phạm vi policy: project hoặc zone.
2. Xác định các VM và hệ điều hành tương thích.
3. Loại bỏ agent quan sát cũ đang gây xung đột.
4. Cấu hình phiên bản agent và nội dung config.yaml.
5. Áp dụng policy theo nhóm VM.
6. Kiểm tra trạng thái extension, phiên bản đang chạy và health của từng VM.
7. Mở rộng rollout sau khi nhóm thử nghiệm gửi đủ log và metric.

VM Extension Manager có các lệnh gcloud để xem trạng thái extension. Ví dụ, xem trạng thái extension trên một VM:

~~~bash
gcloud beta compute instances list-vm-extension-states INSTANCE_NAME \
  --project=PROJECT_ID \
  --zone=ZONE
~~~

Kết quả giúp kiểm tra extension nào đã cài, trạng thái enforcement, health và phiên bản đang hoạt động. Các lệnh gcloud preview/beta có thể thay đổi; kiểm tra tài liệu và phiên bản Google Cloud CLI đang dùng trước khi đưa vào automation.

### 8.2. Công cụ automation

Tài liệu Google Cloud cũng hướng dẫn quản lý Ops Agent bằng Ansible, Chef và Puppet. Những công cụ này phù hợp khi tổ chức đã có hệ thống quản lý cấu hình máy chủ và muốn dùng chung playbook/cookbook/module để cài agent, triển khai YAML và kiểm soát restart.

Với Terraform hoặc Google Cloud CLI, có thể quản lý agent policies và hạ tầng liên quan theo cách khai báo. Nên lưu cấu hình trong Git, review thay đổi, kiểm thử trên một nhóm VM đại diện và ghi nhận phiên bản được phát hành.

### 8.3. Kiểm soát phiên bản và thay đổi cấu hình

Một chính sách fleet tốt cần trả lời:

- VM nào phải chạy Ops Agent?
- Phiên bản nào được phê duyệt?
- Cấu hình nào được áp dụng cho từng nhóm workload?
- Ai có quyền thay đổi policy?
- Làm sao nhận biết VM chưa cài, cài lỗi hoặc không gửi telemetry?

Nên có nhóm canary trước khi rollout toàn bộ. Theo dõi lỗi service, lượng log và metric sau khi cập nhật. Giữ cấu hình có phiên bản để có thể khôi phục khi thay đổi receiver hoặc processor gây lỗi.

## 9. Health checks và xử lý sự cố

### 9.1. Health check lúc khởi động và khi chạy

Ops Agent thực hiện các kiểm tra khi khởi động để phát hiện những điều kiện khiến agent không hoạt động đúng, như lỗi kết nối, cổng cần dùng bị chiếm, thiếu quyền hoặc API chưa được bật. Các phiên bản mới cũng có runtime health checks để báo lỗi phát sinh trong quá trình chạy.

Trên Linux, log health check cục bộ thường nằm tại:

~~~text
/var/log/google-cloud-ops-agent/health-checks.log
~~~

Trên Windows:

~~~text
C:\ProgramData\Google\Cloud Operations\Ops Agent\log\health-checks.log
~~~

Nếu agent được cài và quản lý bằng VM Extension Manager, file health-check có thể nằm trong thư mục trạng thái của Google Guest Agent. Khi đó, đường dẫn chứa instance ID và khác với đường dẫn cài đặt thông thường; hãy dùng hướng dẫn troubleshooting dành cho VM Extension Manager để tìm đúng file.

Thông tin health check cũng có thể được gửi đến Cloud Logging với log ID ops-agent-health. Có thể truy vấn:

~~~text
log_id("ops-agent-health")
~~~

Khi xử lý lỗi, đọc thông báo health check trước rồi mới thay đổi IAM, network hoặc cấu hình. Sau khi khắc phục, restart agent để chạy lại các kiểm tra lúc khởi động.

### 9.2. Kiểm tra agent có đang gửi metric

Ops Agent cung cấp metric uptime của agent. Trong Metrics Explorer, có thể truy vấn bằng PromQL:

~~~promql
rate({"__name__"="agent.googleapis.com/agent/uptime", monitored_resource="gce_instance"}[1m])
~~~

Chọn đúng project và VM. Nếu agent đang chạy nhưng time series không cập nhật, kiểm tra health check, quyền ghi metric, access scope và Monitoring API.

### 9.3. Kiểm tra toàn fleet bằng gcpdiag

gcpdiag có rule kiểm tra Ops Agent đã cài và có gửi log/metric trên các VM Compute Engine hay chưa. Công cụ này là mã nguồn mở được nhóm Google Cloud Support duy trì, không phải một sản phẩm Google Cloud chính thức.

Ví dụ tạo báo cáo fleet:

~~~bash
gcpdiag lint --project=PROJECT_ID --show-skipped --include=gce/ERR/2024_004
~~~

Có thể thêm --name=INSTANCE_NAME để giới hạn vào một VM. Báo cáo giúp phân biệt VM chưa cài agent, VM chưa đủ điều kiện kiểm tra và VM đã gửi được log/metric.

Để chạy gcpdiag trong Cloud Shell, danh tính ADC cần có roles/viewer và roles/serviceusage.serviceUsageConsumer trên project. Các API Cloud Resource Manager, IAM, Cloud Logging và Service Usage phải được bật; VM Manager cũng cần được kích hoạt để công cụ phát hiện agent trên VM. Nếu lệnh báo thiếu quyền hoặc bỏ qua VM, kiểm tra các điều kiện này trước.

### 9.4. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| Cài đặt thất bại | Hệ điều hành không được hỗ trợ hoặc không truy cập được package repository | Kiểm tra danh sách OS, DNS, proxy, firewall và quyền sudo/Administrator |
| Agent không khởi động | YAML sai, receiver không hợp lệ, cổng bị chiếm hoặc agent cũ xung đột | Đọc health-check log, kiểm tra config.yaml và gỡ agent đời cũ theo hướng dẫn |
| Có metric nhưng không có log | Thiếu roles/logging.logWriter, logging pipeline lỗi hoặc file không đọc được | Kiểm tra IAM, log receiver, đường dẫn và quyền đọc file |
| Có log nhưng không có metric | Thiếu roles/monitoring.metricWriter hoặc metrics pipeline bị tắt | Kiểm tra IAM, Monitoring API, access scope và metrics service |
| Không có cả log lẫn metric | VM thiếu service account, thiếu access scope hoặc API chưa bật | Kiểm tra danh tính VM, IAM role, OAuth scope và API |
| Agent chạy nhưng dữ liệu không cập nhật | Mất kết nối, lỗi runtime hoặc pipeline không nhận dữ liệu | Xem ops-agent-health, metric uptime và thử gửi log/metric kiểm tra |
| Không thấy trace trong Cloud Trace | Chưa cấu hình OTLP, agent quá cũ hoặc thiếu roles/cloudtrace.agent | Kiểm tra version >= 2.37.0, pipeline traces, transport gRPC và IAM |
| Log bị trùng | Agent cũ và Ops Agent cùng thu thập một nguồn | Lập kế hoạch chuyển đổi và gỡ agent cũ |
| Console hiển thị Pending lâu | Extension policy chưa áp dụng xong hoặc agent chưa gửi metric | Kiểm tra VM Extension Manager, service và báo cáo gcpdiag |

## 10. Bảo mật, độ tin cậy và chi phí

### 10.1. Bảo vệ dữ liệu log

Log có thể chứa dữ liệu nhạy cảm dù ứng dụng không chủ ý lưu bí mật. Hãy tránh ghi password, access token, session cookie, private key, dữ liệu cá nhân và nội dung request không cần thiết. Nếu dữ liệu đã xuất hiện trong log, xử lý ở nguồn ứng dụng và đánh giá yêu cầu lưu giữ/xóa theo chính sách của tổ chức.

Cấp service account của VM các role ghi telemetry cần thiết. Không cấp quyền Owner hoặc Editor chỉ để agent có thể gửi log và metric. Nếu bật trace, thêm quyền Cloud Trace Agent theo nhu cầu.

### 10.2. Giảm rủi ro mất telemetry

Để duy trì dữ liệu quan sát:

- Cài agent qua image, startup script hoặc fleet policy để VM mới không bị bỏ sót.
- Theo dõi health của agent và tạo cảnh báo khi metric uptime hoặc log health không cập nhật.
- Kiểm tra quyền service account, API và access scope khi thay đổi cấu hình VM.
- Thử nghiệm cấu hình mới trên một nhóm VM trước khi rollout toàn bộ.
- Theo dõi trạng thái agent sau khi nâng cấp hệ điều hành hoặc thay đổi network/proxy.

### 10.3. Kiểm soát chi phí

Chi phí quan sát phụ thuộc vào lượng log được ingest, lượng metric/time series, retention và cách sử dụng dịch vụ đích. Có thể giảm chi phí bằng cách:

- Chỉ thu thập file log và loại log thực sự phục vụ vận hành.
- Loại bỏ log debug lặp lại ở ứng dụng hoặc dùng log exclusion phù hợp.
- Chọn collection_interval theo độ nhạy cảnh báo cần thiết.
- Giảm label cardinality cao trong metric tùy chỉnh.
- Kiểm tra Metrics Management để xem metric nào có ingestion volume, cardinality hoặc lượt đọc cao.
- Dùng log bucket và retention phù hợp với yêu cầu điều tra và tuân thủ.

Không tắt toàn bộ log hoặc metric mặc định chỉ để giảm chi phí trước khi đánh giá ảnh hưởng đến cảnh báo và khả năng điều tra sự cố.

## 11. Tình huống thực tế: theo dõi VM chạy Orders API

Một nhóm vận hành dịch vụ Orders API trên Compute Engine Linux VM. Mục tiêu là theo dõi sức khỏe VM, phát hiện lỗi ứng dụng và truy vết request chậm.

Thiết kế:

1. Gắn service account vm-observability vào VM.
2. Cấp roles/logging.logWriter và roles/monitoring.metricWriter cho service account.
3. Bật Logging API và Monitoring API.
4. Cài Ops Agent và xác nhận service hoạt động.
5. Giữ hostmetrics mặc định để quan sát CPU, memory, disk và network.
6. Thêm file receiver đọc /var/log/orders/*.json và parse JSON.
7. Instrument Orders API bằng OpenTelemetry SDK, cấu hình OTLP receiver nếu cần trace.
8. Cấp roles/cloudtrace.agent khi bật trace.
9. Dùng Logs Explorer lọc theo service và request_id; dùng Metrics Explorer dựng chart CPU/memory; dùng Trace Explorer tìm request có latency cao.
10. Tạo alert khi CPU, memory, lỗi ứng dụng hoặc dữ liệu agent ngừng cập nhật vượt ngưỡng vận hành.

Luồng điều tra một request chậm có thể bắt đầu từ log chứa request_id, mở trace tương ứng để xác định span chậm, rồi đối chiếu metric CPU/memory/disk của VM trong cùng khoảng thời gian. Khi kết hợp ba tín hiệu, nhóm vận hành có thể phân biệt lỗi ứng dụng, nghẽn tài nguyên và vấn đề kết nối đến dịch vụ phụ thuộc.

## 12. Checklist triển khai production

- [ ] VM sử dụng hệ điều hành được Ops Agent hỗ trợ.
- [ ] Cloud Logging API và Cloud Monitoring API đã bật.
- [ ] VM có service account phù hợp và access scope cho API cần dùng.
- [ ] Service account có roles/logging.logWriter và roles/monitoring.metricWriter.
- [ ] Nếu gửi trace, service account có roles/cloudtrace.agent và agent đủ phiên bản.
- [ ] Không chạy Ops Agent đồng thời với Logging/Monitoring agent cũ trên cùng nguồn dữ liệu.
- [ ] Agent đã cài, service đang chạy và health check không báo lỗi.
- [ ] Logs Explorer có log mới và Metrics Explorer có time series của đúng VM.
- [ ] File config.yaml được quản lý trong Git và đã được kiểm tra trên VM thử nghiệm.
- [ ] Pipeline log ứng dụng chỉ thu thập file cần thiết, không lộ secret hoặc dữ liệu cá nhân.
- [ ] Collection interval và metric labels được chọn phù hợp với yêu cầu và chi phí.
- [ ] Fleet có cơ chế cài đặt, nâng cấp và kiểm tra trạng thái nhất quán.
- [ ] Có cảnh báo khi agent ngừng gửi telemetry hoặc health check báo lỗi.

## 13. Câu hỏi tự kiểm tra

**1. Ops Agent gửi logs và metrics đến những dịch vụ nào?**

Logs được gửi đến Cloud Logging; metrics được gửi đến Cloud Monitoring. Trace OTLP được gửi đến Cloud Trace khi receiver và pipeline traces được cấu hình.

**2. Ops Agent dùng những thành phần nào để xử lý telemetry?**

Agent sử dụng Fluent Bit cho log và OpenTelemetry Collector cho metric và trace.

**3. Vì sao service account của VM cần roles/logging.logWriter và roles/monitoring.metricWriter?**

Đây là các quyền cho phép agent ghi log và metric vào dịch vụ đích. Thiếu một role có thể khiến chỉ một loại telemetry bị mất dù agent vẫn chạy.

**4. Khi thêm log file ứng dụng, ba thành phần YAML chính là gì?**

Receiver xác định nguồn log, processor xử lý nội dung và pipeline kết nối các receiver/processor thành luồng thu thập.

**5. Vì sao cần restart Ops Agent sau khi sửa config.yaml?**

Agent hợp nhất cấu hình người dùng với cấu hình mặc định khi khởi động. Restart giúp agent nạp lại cấu hình và khởi tạo pipeline mới.

**6. Làm sao kiểm tra agent đã gửi dữ liệu thành công?**

Kiểm tra service và health check trên VM, sau đó xác nhận log trong Logs Explorer và time series trong Metrics Explorer. Với trace, kiểm tra Cloud Trace.

## 14. Tài liệu tham khảo

- [Ops Agent overview](https://cloud.google.com/monitoring/agent/ops-agent)
- [Install the Ops Agent on individual VMs](https://cloud.google.com/logging/docs/agent/ops-agent/installation)
- [Configure the Ops Agent](https://cloud.google.com/monitoring/agent/ops-agent/configuration)
- [Install the Ops Agent by using VM Extension Manager policies](https://cloud.google.com/monitoring/agent/ops-agent/install-agent-vmem-policies)
- [Install the Ops Agent by using automation tools](https://cloud.google.com/logging/docs/agent/ops-agent/fleet-installation)
- [Troubleshoot Ops Agent installation and start-up](https://cloud.google.com/stackdriver/docs/solutions/agents/ops-agent/troubleshoot-install-startup)
- [Find Ops Agent troubleshooting information](https://cloud.google.com/monitoring/agent/ops-agent/troubleshoot-find-info)
- [Troubleshoot Ops Agent data ingestion](https://cloud.google.com/monitoring/agent/ops-agent/troubleshoot-run-ingest)
- [Use the Ops Agent and OpenTelemetry Protocol (OTLP)](https://cloud.google.com/trace/docs/otlp)

