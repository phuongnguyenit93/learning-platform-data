# Job definition, môi trường thực thi và đầu vào của tác vụ

Trong xử lý nền và xử lý theo lô, một **job definition** mô tả cách một công việc sẽ được chạy: chương trình hoặc container image nào được sử dụng, cần bao nhiêu CPU và bộ nhớ, lệnh khởi động ra sao, quyền truy cập nào được cấp và dữ liệu đầu vào được truyền bằng cách nào. Khi cần xử lý một lô dữ liệu, hệ thống tạo một lần chạy job từ định nghĩa đó, cung cấp đầu vào cụ thể và đưa công việc vào hàng đợi hoặc bộ lập lịch.

Cần phân biệt ba thành phần:

- **Job definition:** bản mô tả có phiên bản về cấu hình chạy, thường được tái sử dụng cho nhiều lần xử lý.
- **Môi trường thực thi:** tài nguyên và ngữ cảnh mà job thực sự chạy, gồm máy hoặc runtime, container, hệ điều hành, mạng, danh tính, dung lượng lưu trữ và giới hạn tài nguyên.
- **Đầu vào của tác vụ:** dữ liệu và tham số riêng của một lần chạy, chẳng hạn khoảng ngày cần xử lý, object URI, mã khách hàng, partition hoặc định danh batch.

Tách rõ ba thành phần này giúp tái lập lần chạy, kiểm soát quyền, mở rộng số worker và điều tra lỗi. Đây là năng lực quan trọng trong các mô hình tính toán trên đám mây, nơi job có thể chạy trên máy ảo, container hoặc môi trường được quản lý mà người vận hành không cần quản lý máy chủ trực tiếp.

## 1. Job definition và lần chạy job

Job definition là mẫu cấu hình mô tả công việc. Nó thường xác định:

- Image hoặc gói chương trình cần thực thi.
- Lệnh khởi động, entrypoint và tham số mặc định.
- CPU, bộ nhớ, GPU hoặc tài nguyên chuyên dụng.
- Biến môi trường, cấu hình ứng dụng và cách tham chiếu secret.
- Quyền truy cập dịch vụ, storage, queue và API.
- Volume hoặc vùng lưu trữ tạm được mount.
- Yêu cầu mạng, vùng triển khai và placement constraint.
- Chính sách retry, timeout, logging và kết quả đầu ra mặc định.

Một **lần chạy job** bổ sung dữ liệu cụ thể cho một yêu cầu xử lý. Cùng một job definition có thể được dùng cho nhiều batch khác nhau, mỗi lần có tham số, input object và mã tương quan riêng.

Ví dụ, định nghĩa `daily-sales-aggregation` có thể luôn chạy chương trình tổng hợp doanh thu. Lần chạy ngày 21/11/2026 truyền ngày xử lý là `2026-11-21`, URI của manifest đầu vào và đường dẫn output riêng. Ngày hôm sau có thể tạo lần chạy khác từ cùng định nghĩa với ngày và manifest mới.

~~~mermaid
flowchart TD
    A["Job definition<br/>image, command, resources, permissions"] --> C["Submit job"]
    B["Input của lần chạy<br/>parameters, object URI, batch ID"] --> C
    C --> D["Queue / scheduler"]
    D --> E["Môi trường thực thi"]
    E --> F["Task attempt"]
    F --> G["Đọc input và xử lý"]
    G --> H["Ghi output / trạng thái"]
    H --> I["Kết quả job"]
~~~

Job definition nên thay đổi khi logic hoặc cấu hình nền tảng cần thay đổi. Dữ liệu thay đổi theo từng lần chạy nên được truyền vào invocation/job submission thay vì sửa định nghĩa cho mỗi batch.

## 2. Phân biệt job, task, attempt và worker

Các nền tảng có cách gọi khác nhau, nhưng có thể dùng mô hình khái niệm sau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Job definition | Mẫu cấu hình để tạo công việc | Image, command, CPU, memory, role và retry policy |
| Job | Một yêu cầu xử lý cụ thể được gửi đến hệ thống | Tổng hợp doanh thu cho ngày 21/11 |
| Task hoặc task unit | Phần công việc có thể được thực thi; đôi khi là một lần chạy container | Xử lý một partition hoặc một file |
| Attempt | Một lần thử chạy job/task | Lần đầu thất bại vì timeout, lần hai chạy lại |
| Worker | Tiến trình hoặc tài nguyên nhận và thực thi công việc | Container worker chạy trên một node |

Một job có thể chỉ có một task, hoặc được chia thành nhiều task độc lập. Ví dụ, job xử lý 1.000 file có thể tạo 100 task, mỗi task xử lý 10 file. Khi một task lỗi, hệ thống có thể retry riêng task đó thay vì chạy lại toàn bộ batch, nếu kiến trúc và công cụ điều phối hỗ trợ.

Không nên giả định tên gọi này giống nhau tuyệt đối ở mọi nhà cung cấp. Trong AWS Batch, job được submit từ job definition và có thể được thực thi trong một hoặc nhiều container tùy loại job. Trong Kubernetes, Job quản lý Pod để hoàn thành một công việc hữu hạn; Pod là đơn vị thực thi cụ thể. Trong Google Cloud Batch, job gồm các task và task group được chạy trên tài nguyên được cấp cho job. Khi đọc tài liệu nền tảng, cần xác định rõ đối tượng nào được submit, đối tượng nào được scheduler tạo và đối tượng nào được retry.

## 3. Môi trường thực thi của job

Môi trường thực thi là nơi chương trình chạy sau khi scheduler chấp nhận job. Nó bao gồm cả phần tính toán lẫn các dịch vụ và cấu hình giúp job hoạt động.

### 3.1. Hạ tầng tính toán

Job có thể chạy trên:

- **Máy ảo hoặc node pool:** nhà cung cấp hoặc người vận hành cấp máy, hệ điều hành và agent quản lý. Có thể chọn loại máy theo CPU, RAM, GPU, local SSD và vùng sẵn sàng.
- **Container trên cụm được quản lý:** job chạy trong container trên node do dịch vụ điều phối quản lý. Image giúp đóng gói ứng dụng và dependency.
- **Môi trường batch serverless hoặc fully managed:** người dùng khai báo job và yêu cầu tài nguyên; nhà cung cấp quản lý việc cấp phát, scheduling và thu hồi hạ tầng theo khả năng của dịch vụ.

Máy ảo cho phép kiểm soát sâu hệ điều hành và phần mềm nền, nhưng làm tăng công việc vá lỗi, bảo trì và quản lý dung lượng. Container giúp đóng gói môi trường ứng dụng nhất quán, nhưng vẫn cần hiểu node, image, mạng và tài nguyên. Dịch vụ batch được quản lý giảm việc vận hành máy chủ, đổi lại người dùng phải tuân theo giới hạn runtime, vùng hỗ trợ, loại instance và mô hình tính phí của dịch vụ.

### 3.2. Runtime và dependency

Môi trường thực thi cần xác định rõ:

- Hệ điều hành và kiến trúc CPU, ví dụ Linux x86-64 hoặc ARM64.
- Runtime như Java, Python, Node.js hoặc .NET nếu chương trình chạy trực tiếp trên máy.
- Phiên bản thư viện và dependency.
- Locale, timezone, chứng thư CA và cấu hình hệ thống cần thiết.
- Image digest hoặc phiên bản artifact để tránh chạy nhầm mã.
- Dung lượng đĩa tạm, thư mục làm việc và giới hạn file descriptor nếu liên quan.

Container image nên được build một lần, kiểm thử rồi phát hành bằng digest bất biến. Dùng tag như `latest` có thể khiến hai lần chạy cùng job definition thực tế sử dụng nội dung image khác nhau nếu tag bị cập nhật.

### 3.3. Tài nguyên và khả năng mở rộng

Job definition cần mô tả nhu cầu tài nguyên thực tế. Ví dụ:

- CPU cho giải nén, biến đổi dữ liệu và tính toán.
- Bộ nhớ cho kích thước working set và số bản ghi xử lý đồng thời.
- GPU cho mô hình hoặc thuật toán tăng tốc.
- Ephemeral storage cho file trung gian.
- Network bandwidth và số kết nối tới database, object storage hoặc API.

Nếu khai báo thiếu CPU hoặc bộ nhớ, job có thể chạy chậm, bị throttling hoặc bị OOM. Nếu yêu cầu quá cao, scheduler khó tìm node phù hợp và chi phí mỗi task tăng. Với job chạy song song, tổng tài nguyên có thể xấp xỉ số task đồng thời nhân với nhu cầu mỗi task; cần tính cả tài nguyên dự phòng và giới hạn quota.

### 3.4. Mạng, danh tính và lưu trữ

Môi trường thực thi phải truy cập đúng dịch vụ cần thiết:

- Subnet, route, DNS, firewall/security group và endpoint dịch vụ.
- Danh tính runtime hoặc task role với quyền tối thiểu.
- Secret được lấy từ secret manager tại runtime.
- Volume hoặc object storage để đọc input và ghi output.
- Log và metric được gửi tới hệ thống giám sát.

Không nên nhúng access key, mật khẩu database hoặc token vào image. Quyền của job nên giới hạn theo tài nguyên và hành động, ví dụ chỉ đọc prefix input và ghi prefix output dành cho batch đó.

## 4. Đầu vào của tác vụ

Đầu vào xác định chính xác công việc mà một lần chạy phải thực hiện. Có thể chia thành các nhóm:

| Nhóm đầu vào | Ví dụ | Cách truyền thường dùng |
|---|---|---|
| Tham số nghiệp vụ | Ngày bắt đầu/kết thúc, mã tenant, loại báo cáo | CLI arguments, job parameters hoặc payload |
| Định danh dữ liệu | Object URI, bucket/key, database partition, manifest | Tham chiếu URI hoặc ID; không truyền file lớn trực tiếp trong command |
| Cấu hình xử lý | Batch size, định dạng output, chế độ dry-run | Config file hoặc parameter store |
| Thông tin tương quan | Job ID, batch ID, correlation ID | Metadata hoặc environment variable |
| Bí mật truy cập | Credential hoặc token cần thiết | Secret manager hoặc identity federation |
| Tín hiệu điều khiển | Partition index, shard count, retry attempt | Task metadata hoặc tham số runtime |

Nên phân biệt **tham số** và **dữ liệu**. Tham số thường nhỏ, mô tả cách xử lý; dữ liệu có thể lớn và được lưu trong object storage, database hoặc stream. Truyền object URI thay vì toàn bộ file trong payload giúp giảm kích thước message, tránh giới hạn API và cho phép worker tải dữ liệu theo nhu cầu.

Một input manifest có thể liệt kê các object cần xử lý:

~~~json
{
  "batchId": "sales-2026-11-21",
  "businessDate": "2026-11-21",
  "inputVersion": "v3",
  "objects": [
    "s3://company-data/sales/date=2026-11-21/part-0001.parquet",
    "s3://company-data/sales/date=2026-11-21/part-0002.parquet"
  ],
  "outputPrefix": "s3://company-results/sales/date=2026-11-21/",
  "schemaVersion": 3
}
~~~

Manifest nên có version, checksum hoặc thông tin nhận diện nguồn khi cần tái lập. Nếu dữ liệu đầu vào thay đổi sau khi job được submit, job có thể cho kết quả khác dù tham số không đổi. Có thể dùng object version, immutable key hoặc checksum để đóng băng tập input cho lần chạy.

## 5. Kiểm tra và xác thực đầu vào

Job không nên tin cậy hoàn toàn dữ liệu do caller truyền vào. Trước khi xử lý, cần kiểm tra:

1. **Schema:** trường bắt buộc có mặt, đúng kiểu và đúng phiên bản.
2. **Miền giá trị:** ngày hợp lệ, batch size trong giới hạn, số partition không âm.
3. **Quyền sở hữu:** caller được phép yêu cầu xử lý dữ liệu của tenant hoặc khách hàng tương ứng.
4. **Tài nguyên:** kích thước file, số lượng object và tổng khối lượng dữ liệu nằm trong giới hạn đã thiết kế.
5. **Nguồn dữ liệu:** object tồn tại, đúng version/checksum, định dạng và schema tương thích.
6. **An toàn:** tên file và URI không cho phép truy cập đường dẫn tùy ý hoặc tài nguyên ngoài phạm vi.
7. **Tính nhất quán:** manifest và metadata batch cùng chỉ tới một snapshot hoặc phiên bản dữ liệu.

Với input không hợp lệ, nên từ chối job sớm và trả lỗi rõ ràng. Không nên để worker chạy lâu rồi mới phát hiện thiếu trường hoặc quyền truy cập sai. Log lỗi nên chứa job ID, tên trường hoặc mã lỗi, nhưng không ghi secret hay toàn bộ payload nhạy cảm.

## 6. Ví dụ định nghĩa và submit job theo mô hình batch

Giả sử nhóm dữ liệu cần chạy chương trình tổng hợp doanh thu hằng ngày. Mỗi lần chạy xử lý một manifest đầu vào và ghi kết quả vào một prefix riêng.

Ví dụ YAML dưới đây là **mô hình khái niệm**, giúp nhìn rõ phần định nghĩa cố định và phần input theo lần chạy. Đây không phải schema trực tiếp để nộp cho một nhà cung cấp cụ thể.

~~~yaml
jobDefinition:
  name: daily-sales-aggregation
  version: "7"
  image: registry.example.com/data/sales-aggregator@sha256:IMAGE_DIGEST
  command:
    - python
    - -m
    - sales_aggregator
  resources:
    cpu: "2"
    memory: "4Gi"
    ephemeralStorage: "10Gi"
  runtime:
    architecture: amd64
    operatingSystem: linux
  identity:
    role: sales-batch-runtime
  environment:
    LOG_LEVEL: INFO
  retry:
    attempts: 3
  timeoutSeconds: 1800

jobRun:
  name: sales-2026-11-21
  parameters:
    businessDate: "2026-11-21"
    inputManifest: "s3://company-data/manifests/sales-2026-11-21.json"
    outputPrefix: "s3://company-results/sales-2026-11-21/"
  metadata:
    batchId: "sales-2026-11-21"
    schemaVersion: "3"
~~~

Job definition giữ image, command, tài nguyên, identity và chính sách retry. Job run mang ngày nghiệp vụ, manifest và output prefix riêng. Khi phát hành image mới, nhóm có thể tạo phiên bản definition mới; những lần chạy trước vẫn có thể truy vết tới phiên bản cũ.

Với AWS Batch, một job definition đã đăng ký được tham chiếu khi submit job. Lệnh minh họa:

~~~bash
aws batch submit-job \
  --job-name sales-2026-11-21 \
  --job-queue analytics-queue \
  --job-definition daily-sales-aggregation:7 \
  --parameters businessDate=2026-11-21,inputManifest=s3://company-data/manifests/sales-2026-11-21.json
~~~

Tên queue, job definition và parameter phải tồn tại trong tài khoản/vùng triển khai; ví dụ cần điều chỉnh theo cấu hình thật. Các giá trị override của container có thể được khai báo bằng API/CLI phù hợp. Không đưa secret vào tham số dòng lệnh vì chúng có thể xuất hiện trong log hoặc lịch sử thao tác.

## 7. Phân chia input cho nhiều task

Khi dữ liệu lớn, một job có thể được chia thành nhiều task song song. Có hai cách thường gặp:

- **Chia theo danh sách:** mỗi task nhận một nhóm object hoặc record ID.
- **Chia theo partition:** mỗi task nhận partition index hoặc khoảng khóa để đọc một phần dữ liệu.

Ví dụ có 120 file và muốn chạy 12 task. Mỗi task nhận 10 file trong manifest. Cần bảo đảm các nhóm không trùng nhau và bao phủ hết input. Nếu file có kích thước rất khác nhau, chia theo số file có thể gây mất cân bằng; nên cân nhắc chia theo kích thước hoặc ước lượng khối lượng xử lý.

~~~mermaid
flowchart TD
    A["Input manifest: 120 files"] --> B["Partition planner"]
    B --> C["Task 0: files 1-10"]
    B --> D["Task 1: files 11-20"]
    B --> E["Task 2: files 21-30"]
    B --> F["..."]
    B --> G["Task 11: files 111-120"]
    C --> H["Output partition 0"]
    D --> I["Output partition 1"]
    E --> J["Output partition 2"]
    G --> K["Output partition 11"]
    H --> L["Validate and aggregate"]
    I --> L
    J --> L
    K --> L
~~~

Nếu một task thất bại, chỉ partition đó cần retry khi output được ghi theo key xác định và thao tác có tính idempotent. Mỗi task nên lưu partition ID, input range, attempt và output reference để điều tra.

Cần tránh hai worker cùng ghi đè một output không có kiểm soát. Có thể dùng output key chứa batch ID và partition ID, ghi tạm rồi commit manifest kết quả khi task hoàn tất. Bước tổng hợp cuối chỉ đọc những partition đã được xác nhận thành công.

## 8. Phiên bản hóa và khả năng tái lập

Một job có thể được chạy lại sau vài tuần để điều tra sai lệch hoặc tạo lại báo cáo. Muốn kết quả có thể tái lập, cần lưu đủ thông tin để biết lần chạy đã sử dụng điều gì:

- Job definition name và revision/version.
- Container image digest hoặc artifact checksum.
- Runtime architecture và phiên bản dependency.
- Tham số đầu vào và phiên bản schema.
- Input manifest, object version hoặc checksum.
- Cấu hình nghiệp vụ quan trọng và version của model/rule.
- Danh tính runtime, queue, region và loại tài nguyên liên quan.
- Job ID, task ID, attempt, thời điểm bắt đầu/kết thúc và kết quả.

Không nên lưu secret trực tiếp trong lịch sử job. Hãy lưu tên secret hoặc version tham chiếu, đồng thời bảo đảm quyền truy cập và chính sách retention phù hợp. Với dữ liệu có yêu cầu kiểm toán, nên giữ manifest và metadata dưới dạng bất biến hoặc có audit trail.

Nếu definition thay đổi giữa hai lần chạy, cần tạo version mới thay vì âm thầm thay đổi cấu hình đang dùng. Khi chạy lại batch cũ, người vận hành có thể chủ động chọn version cũ hoặc version mới và ghi rõ lý do.

## 9. Retry, timeout và xử lý lỗi

Job batch thường chạy lâu hơn một request đồng bộ và có thể gặp lỗi hạ tầng hoặc lỗi dữ liệu. Chính sách retry nên phân biệt:

- **Lỗi tạm thời:** lỗi mạng, throttling, dịch vụ phụ thuộc tạm thời không sẵn sàng. Có thể retry với exponential backoff và jitter.
- **Lỗi đầu vào:** schema sai, file không tồn tại, quyền truy cập không hợp lệ. Thường cần sửa dữ liệu hoặc cấu hình trước khi chạy lại.
- **Lỗi logic:** bug hoặc điều kiện nghiệp vụ không xử lý được. Cần ghi log, dừng hoặc đưa vào hàng đợi điều tra.
- **Lỗi tài nguyên:** OOM, thiếu CPU, hết dung lượng tạm hoặc timeout. Cần điều chỉnh tài nguyên hoặc chia nhỏ công việc.

Timeout nên dựa trên thời gian xử lý dự kiến và có khoảng dự phòng hợp lý. Nếu job có thể chạy hàng giờ, cân nhắc checkpoint để tiếp tục từ partition hoặc bước gần nhất. Retry toàn bộ job lớn có thể tốn kém và tạo output trùng.

Đặt số lần thử tối đa, backoff, timeout và dead-letter/failure queue rõ ràng. Sau khi hết retry, lưu trạng thái cuối cùng, mã lỗi, attempt cuối và thông tin cần thiết để phát lại có kiểm soát. Không retry vô hạn với lỗi đầu vào hoặc lỗi logic.

## 10. Bảo mật đầu vào và môi trường thực thi

Job thường xử lý dữ liệu lớn hoặc dữ liệu nội bộ, do đó cần bảo vệ cả input lẫn môi trường chạy:

- Cấp quyền tối thiểu cho job role; tách quyền đọc input và ghi output.
- Dùng secret manager hoặc workload identity thay cho khóa tĩnh.
- Mã hóa dữ liệu khi truyền và khi lưu theo chính sách tổ chức.
- Chỉ cho phép network egress tới dịch vụ cần thiết; cân nhắc private endpoint.
- Xác thực object URI, tenant ID và quyền sở hữu trước khi đọc.
- Không đưa dữ liệu cá nhân, token hoặc secret vào command line, tag hay log.
- Quét image, ghim image digest và cập nhật dependency có kiểm soát.
- Dọn file tạm và dữ liệu trung gian theo retention policy.
- Giới hạn concurrency và quota để job không làm cạn tài nguyên dùng chung.

Đối với dữ liệu nhiều tenant, không dựa vào prefix do caller tự cung cấp để quyết định quyền. Ứng dụng cần xác thực tenant trong metadata đáng tin cậy và kiểm tra quyền ở lớp truy cập dữ liệu.

## 11. Theo dõi và xác minh một lần chạy

Một lần submit thành công chỉ có nghĩa scheduler đã nhận yêu cầu. Nó không bảo đảm job đã chạy, đọc đúng input hoặc ghi output đầy đủ.

Quy trình xác minh nên gồm:

1. **Sau submit:** lưu job ID, definition revision và tham số đã gửi; xác nhận job vào đúng queue.
2. **Khi được lập lịch:** kiểm tra môi trường thực thi đã được cấp, image tải thành công và container bắt đầu.
3. **Trong khi chạy:** theo dõi CPU, memory, disk, network, thời gian xử lý, số record/file và log theo task.
4. **Khi hoàn tất:** xác nhận exit code, trạng thái job, số task thành công/thất bại và output manifest.
5. **Sau hoàn tất:** kiểm tra số lượng, checksum, schema và quy tắc nghiệp vụ của output; đối chiếu với input.
6. **Nếu lỗi:** giữ lại job ID, attempt, task ID, log và input manifest để điều tra; chỉ phát lại theo chính sách retry.

Với AWS Batch, có thể xem thông tin job và queue bằng các lệnh:

~~~bash
aws batch describe-jobs --jobs JOB_ID
aws batch describe-job-queues --job-queues analytics-queue
~~~

Với Kubernetes Job, có thể kiểm tra trạng thái Job, Pod và log:

~~~bash
kubectl describe job sales-aggregation -n batch
kubectl get pods -n batch -l job-name=sales-aggregation
kubectl logs JOB_POD_NAME -n batch
~~~

Các lệnh này giúp xác định trạng thái điều phối và runtime. Cần kiểm tra thêm dữ liệu đầu ra và metric nghiệp vụ để kết luận batch thành công.

Các metric hữu ích gồm queue wait time, scheduling delay, job duration, task success/failure, retry count, CPU/memory utilization, OOM, disk usage, input/output bytes, records processed, throughput và chi phí mỗi batch.

## 12. Checklist thiết kế job

- [ ] Job definition có tên và version rõ ràng, mô tả image/artifact, command và tài nguyên.
- [ ] Image được ghim bằng digest hoặc artifact có checksum.
- [ ] Môi trường thực thi xác định đúng architecture, runtime, dependency, network và storage.
- [ ] CPU, memory, GPU và ephemeral storage phù hợp với khối lượng xử lý.
- [ ] Job role chỉ có quyền cần thiết đối với input, output và dịch vụ phụ thuộc.
- [ ] Đầu vào có schema, version, validation và định danh dữ liệu rõ ràng.
- [ ] File lớn được truyền bằng object URI/manifest thay vì nhúng vào payload.
- [ ] Input manifest bất biến hoặc có version/checksum để tái lập lần chạy.
- [ ] Job/task có ID tương quan, attempt và output location riêng.
- [ ] Đã chọn chiến lược partition, concurrency và retry phù hợp.
- [ ] Timeout, backoff, dead-letter và checkpoint được xác định.
- [ ] Output được xác minh về trạng thái, số lượng, checksum và tính đúng đắn nghiệp vụ.
- [ ] Log và metric đủ để truy vết nhưng không chứa secret hoặc dữ liệu nhạy cảm.

Job definition giúp chuẩn hóa cách chạy; môi trường thực thi cung cấp năng lực và quyền để chương trình hoạt động; đầu vào xác định công việc cụ thể của từng lần chạy. Khi phiên bản hóa cả ba phần, xác thực input, giới hạn tài nguyên và lưu metadata của từng attempt, hệ thống batch có thể mở rộng song song mà vẫn kiểm soát được khả năng tái lập, bảo mật và chi phí.
