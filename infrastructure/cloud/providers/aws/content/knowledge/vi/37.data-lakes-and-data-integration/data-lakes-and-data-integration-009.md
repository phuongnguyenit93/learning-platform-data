# Amazon EMR trên EC2, EKS và mô hình serverless

Amazon EMR là nền tảng AWS để chạy các framework xử lý dữ liệu phân tán như Apache Spark, Apache Hadoop, Hive, Trino và các engine được hỗ trợ theo từng mô hình triển khai. EMR giúp xử lý dữ liệu lớn trong data lake, ETL, phân tích batch, truy vấn tương tác và một số workload streaming. Khi thiết kế hệ thống, đội dữ liệu có ba lựa chọn triển khai chính: **EMR trên EC2**, **EMR trên EKS** và **EMR Serverless**.

Ba lựa chọn cùng dùng runtime được tối ưu của Amazon EMR nhưng có cách quản lý compute, cách cô lập workload và mô hình chi phí khác nhau. EMR trên EC2 cho quyền kiểm soát cluster và phần cứng; EMR trên EKS chạy job trong Kubernetes namespace để chia sẻ hạ tầng với workload container khác; EMR Serverless tự cấp phát worker theo nhu cầu của ứng dụng Spark/Hive. Chọn đúng mô hình cần xét tần suất job, thời gian chạy, nhu cầu tùy chỉnh, kỹ năng vận hành, yêu cầu bảo mật, khả năng dùng chung compute và tổng chi phí.

Bài học trình bày kiến trúc của từng mô hình, cách chọn storage và compute, IAM/network, autoscaling, vận hành, reliability và cost. Phần so sánh cũng nêu rõ các giới hạn dịch vụ: EMR Serverless không cung cấp HDFS; Spark Structured Streaming trên EMR Serverless là một chế độ riêng; EMR on EKS có thể chạy Spark và Flink theo release/submission model hỗ trợ.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vai trò của Amazon EMR trong data lake và hệ sinh thái AWS.
- Phân biệt EMR on EC2, EMR on EKS và EMR Serverless theo compute, control plane, storage, scaling và billing.
- Thiết kế cluster EMR trên EC2 với primary, core, task nodes, instance groups hoặc instance fleets.
- Chọn HDFS, S3A, EBS và local storage theo vòng đời dữ liệu.
- Tạo virtual cluster trên EKS, hiểu namespace, job run, execution role và pod scheduling.
- Phân biệt Spark Operator, Flink Kubernetes Operator và mô hình StartJobRun.
- Cấu hình EMR Serverless application, worker size, maximum capacity, pre-initialized capacity và auto-stop.
- Chọn deployment model theo workload batch, interactive, streaming, long-running và multi-tenant.
- Tích hợp S3, Glue Data Catalog, Lake Formation, IAM, KMS và VPC.
- Theo dõi job, xử lý lỗi, tối ưu compute và ước tính chi phí.
- Xây dựng quy trình triển khai, nâng cấp, rollback và dọn tài nguyên an toàn.

## 2. Amazon EMR trong kiến trúc data lake

Amazon EMR cung cấp runtime được AWS tối ưu cho các framework mã nguồn mở. Dịch vụ thường nằm ở lớp compute/processing trong kiến trúc data lake:

    Data producers
      |  application events / database exports / files
      v
    Amazon S3 data lake
      |
      +---- AWS Glue Data Catalog
      |
      +---- AWS Lake Formation permissions
      |
      v
    Amazon EMR
      |  Spark / Hive / Trino / Hadoop / Flink
      |
      +---- Transform / join / aggregate / validate
      |
      +---- S3 curated zone / Apache Iceberg / Hudi / Delta
      |
      +---- Data warehouse / search / serving systems
      |
      v
    Athena / Redshift / SageMaker / BI / applications

EMR không phải nơi bắt buộc phải lưu toàn bộ dữ liệu lâu dài. Trong kiến trúc tách storage và compute, dữ liệu gốc, dữ liệu đã chuẩn hóa và dữ liệu curated thường nằm trong S3; EMR cấp phát compute để đọc, xử lý và ghi kết quả. Cách tổ chức này cho phép nhiều cluster/job dùng chung dữ liệu và giúp dừng compute mà không xóa data lake.

### 2.1 Những thành phần liên quan

| Thành phần | Vai trò trong kiến trúc |
|---|---|
| Amazon S3 | Lưu raw, staging, curated, checkpoint, log và artifact |
| AWS Glue Data Catalog | Metadata database/table/schema cho Spark, Hive, Athena và engine tích hợp |
| AWS Lake Formation | Quản lý quyền truy cập dữ liệu chi tiết trên catalog/table/column/row/cell theo tích hợp hỗ trợ |
| Amazon EMR | Runtime xử lý phân tán |
| Amazon EKS | Kubernetes control plane và compute orchestration cho EMR on EKS |
| Amazon EC2 | Compute nodes cho EMR on EC2 hoặc worker nodes của EKS |
| Amazon EBS | Block storage gắn với EC2 node, scratch hoặc HDFS tùy cấu hình |
| Amazon CloudWatch | Metrics, logs, dashboards và alarms |
| AWS IAM | Service role, runtime/job role và quyền người vận hành |
| AWS KMS | Encryption key cho dữ liệu, volume, bucket và secret |
| AWS Step Functions / MWAA | Orchestration pipeline và dependency giữa các job |

### 2.2 Framework không giống deployment model

Framework là engine hoặc thư viện thực hiện tính toán; deployment model quyết định nơi và cách cấp phát hạ tầng:

- Apache Spark: batch, SQL, ML và Structured Streaming.
- Apache Hive: SQL/data warehouse workloads theo phiên bản được hỗ trợ.
- Trino: truy vấn phân tán tương tác khi release/deployment model hỗ trợ.
- Hadoop/MapReduce: batch processing và hệ sinh thái Hadoop.
- Apache Flink: stream processing; có thể chạy trên EMR EC2 và EMR on EKS theo release phù hợp.

Không phải framework nào cũng có trên cả ba mô hình. EMR Serverless application type hiện tập trung vào Spark và Hive. EMR on EKS hỗ trợ Spark job và Flink operator ở các release được tài liệu hóa. Trước khi chọn engine, kiểm tra release label, Region, connector và submission model.

## 3. So sánh ba mô hình triển khai

| Tiêu chí | EMR trên EC2 | EMR trên EKS | EMR Serverless |
|---|---|---|---|
| Compute | EC2 instance trong EMR cluster | Pod trên EKS worker capacity | Worker được dịch vụ cấp phát theo job/application |
| Đơn vị quản lý | Cluster | EKS cluster, namespace, EMR virtual cluster, job run | Application và job run |
| Hạ tầng | Người dùng chọn instance, storage, network và lifecycle | Người dùng quản lý EKS cluster/node capacity; EMR quản lý runtime/job integration | Không quản lý EC2/Kubernetes cluster cho job |
| Framework | Nhiều ứng dụng Hadoop ecosystem tùy release | Spark và Flink theo release/submission model; các khả năng khác cần kiểm tra | Spark và Hive; Spark Structured Streaming có mode riêng |
| Long-running service | Phù hợp với cluster persistent và interactive workloads | Phù hợp job hoặc service chạy trên EKS theo framework hỗ trợ | Phù hợp batch và streaming job Spark; application quản lý worker |
| Tùy chỉnh hạ tầng | Cao: instance type, AMI, bootstrap, EBS, daemon | Cao ở EKS/node/pod template; runtime theo EMR release | Thấp hơn; cấu hình worker, image, application settings |
| Scaling | Managed scaling, instance groups/fleets, Auto Scaling | Kubernetes scheduler, node autoscaling và EMR job controls | Tự cấp worker, maximum capacity, dynamic allocation |
| Cô lập | Cluster/role/security group | Namespace, pod, IAM job execution role | Application và job runtime role |
| Vận hành | Quản lý cluster lifecycle, patch/release, capacity | Cần năng lực Kubernetes/EKS, quota, node pools và networking | Ít việc quản lý compute; vẫn cần quản lý app, role, data và job |
| Storage | HDFS, S3A, EBS, local disk | Chủ yếu S3/object storage và pod ephemeral storage; persistent volume theo thiết kế EKS | Không hỗ trợ HDFS; dùng S3/data services, local worker disk tạm thời |
| Chi phí | EMR charge + EC2/EBS/network/related services | EMR uplift theo vCPU/memory + EKS + EC2/Fargate/storage/network | vCPU, memory, storage của worker theo thời gian sử dụng; thêm pre-initialized idle capacity nếu bật |
| Khi phù hợp | Workload ổn định, cần tùy chỉnh sâu, dùng HDFS hoặc nhiều framework | Tổ chức đã vận hành EKS và muốn chia sẻ compute/quan sát/guardrails | Job không liên tục, traffic biến động, muốn giảm quản lý cluster |

### 3.1 Quy tắc chọn nhanh

- Chọn **EMR trên EC2** khi cần kiểm soát instance/AMI/bootstrap, cluster lâu dài, framework đa dạng, HDFS hoặc tối ưu Spot/managed scaling ở cấp cluster.
- Chọn **EMR trên EKS** khi tổ chức đã có nền tảng Kubernetes, cần multi-tenant namespace, dùng chung compute với ứng dụng container và muốn quản lý Spark/Flink bằng công cụ Kubernetes.
- Chọn **EMR Serverless** khi workload chủ yếu là job Spark/Hive theo lịch hoặc theo sự kiện, mức tải biến động và không muốn duy trì cluster.

Không chọn chỉ dựa trên câu “serverless luôn rẻ hơn” hoặc “Kubernetes luôn tận dụng tốt hơn”. Tổng chi phí phụ thuộc utilization, thời gian chờ, worker sizing, cluster idle, EKS overhead, Spot, pre-initialized capacity và chi phí vận hành.

## 4. EMR trên EC2: kiến trúc cluster

EMR trên EC2 tạo một cluster gồm các EC2 instance. EMR cài framework và thành phần quản lý lên các node, sau đó điều phối job qua YARN hoặc runtime tương ứng.

### 4.1 Ba loại node

| Node type | Nhiệm vụ | Lưu trữ HDFS | Vai trò thường gặp |
|---|---|---|---|
| Primary | Quản lý cluster, YARN ResourceManager, HDFS NameNode và theo dõi job | Metadata/control role | Điều phối và quản lý |
| Core | Chạy task/executor và HDFS DataNode | Có | Compute + lưu intermediate data |
| Task | Chạy task/executor bổ sung | Không lưu HDFS | Mở rộng compute linh hoạt |

Cluster nhỏ có thể chỉ gồm một primary node. Cluster production quan trọng có thể dùng ba primary nodes để tăng high availability cho các thành phần điều phối được hỗ trợ. Core node vừa đóng góp compute vừa lưu HDFS, do đó giảm số core có thể ảnh hưởng cả compute và khả năng lưu dữ liệu. Task node chỉ đóng góp compute nên phù hợp với capacity bổ sung, đặc biệt khi dùng Spot.

### 4.2 Instance groups và instance fleets

EMR có hai cách tổ chức nhóm EC2:

**Instance groups**

- Mỗi group dùng một loại instance.
- Có thể thêm/bớt instance trong group core/task.
- Cấu hình đơn giản và dễ dự đoán.
- Phù hợp khi workload có profile phần cứng tương đối đồng nhất.

**Instance fleets**

- Mỗi fleet có thể chứa nhiều instance type.
- Chỉ định target capacity On-Demand và Spot.
- EMR chọn tổ hợp instance để đáp ứng capacity.
- Có allocation strategy cho On-Demand và Spot.
- Tăng khả năng lấy capacity khi một instance pool thiếu hoặc Spot bị gián đoạn.

Instance groups và instance fleets là lựa chọn khi tạo cluster; không thể chuyển đổi qua lại sau khi cluster đã được tạo. Hãy quyết định dựa trên khả năng thay đổi instance type, độ linh hoạt capacity và cách quản lý Spot.

### 4.3 Chọn instance type

Chọn instance theo đặc điểm workload:

| Workload | Tài nguyên cần ưu tiên |
|---|---|
| Spark SQL/join lớn | Memory, CPU, network và shuffle I/O |
| ML preprocessing | CPU, memory, local disk và network |
| Shuffle-intensive | Network bandwidth và EBS/local I/O |
| HDFS-heavy | Dung lượng và throughput storage của core nodes |
| Trino interactive | CPU, memory và network ổn định |
| Compression/encryption | CPU và vector instruction phù hợp |

Không chọn instance chỉ theo vCPU. Cần đo executor memory, GC, spill, shuffle read/write, network, EBS throughput và skew. Với workload memory-heavy, instance có RAM lớn có thể tiết kiệm tổng chi phí nếu giảm số executor hoặc spill xuống disk.

### 4.4 On-Demand và Spot

On-Demand phù hợp với primary/core capacity cần ổn định và workload không chịu được interruption. Spot phù hợp với task capacity hoặc job có checkpoint/retry và khả năng chạy lại.

Best practice:

- Giữ primary node và phần core thiết yếu trên On-Demand khi cần độ ổn định.
- Dùng Spot cho task nodes hoặc capacity có thể thay thế.
- Dùng nhiều instance type/pool để giảm phụ thuộc một pool.
- Chọn allocation strategy ưu tiên capacity khi workload nhạy với interruption.
- Thiết kế Spark job có retry/checkpoint và output idempotent.
- Không lưu dữ liệu duy nhất trên local disk hoặc HDFS nếu cluster có thể bị terminate.

Instance fleet hỗ trợ allocation strategy như price-capacity-optimized, capacity-optimized, capacity-optimized-prioritized, diversified và lowest-price tùy loại cấu hình/release. Với EMR release 6.10.0 trở lên, price-capacity-optimized là mặc định cho Spot fleets theo tài liệu hiện hành. Lowest-price có thể tăng interruption nếu chỉ chọn pool rẻ nhất mà không xét capacity.

### 4.5 Managed scaling

EMR managed scaling tự điều chỉnh số lượng EC2 instance hoặc units dựa trên workload metrics để cân bằng cost và speed. Người vận hành đặt minimum/maximum capacity, giới hạn On-Demand/Spot và các tham số scaling phù hợp.

Managed scaling có thể giảm capacity khi workload kết thúc, nhưng không thay thế thiết kế job đúng. Nếu một executor giữ resource do skew hoặc job không giải phóng container, cluster có thể vẫn cần capacity cao. Hãy kiểm tra YARN pending containers, Spark executor state và utilization trước khi nâng max capacity.

### 4.6 Auto Scaling và custom scaling

EMR cũng hỗ trợ automatic scaling dựa trên CloudWatch metrics và scaling policy do người dùng cấu hình. Dùng khi cần hành vi cụ thể hơn managed scaling hoặc khi metric custom phản ánh workload tốt hơn. Tránh đặt nhiều scaling policy mâu thuẫn cùng điều khiển một nhóm instance.

## 5. Storage trên EMR EC2

### 5.1 HDFS

HDFS là distributed file system nằm trên core nodes. Nó hữu ích cho intermediate data, cache và workload đọc lặp nhiều lần trên cùng dataset. HDFS có locality với compute nhưng là storage gắn với vòng đời cluster. Khi cluster bị terminate, dữ liệu HDFS và local disk không còn khả dụng.

Không dùng HDFS làm nơi lưu bản duy nhất của raw/curated data cần tồn tại qua nhiều cluster. Hãy ghi kết quả lâu dài ra S3 hoặc storage bền vững khác.

### 5.2 Amazon S3 và S3A

S3 là object storage bền vững, tách biệt compute. EMR đọc/ghi dữ liệu trên S3 bằng filesystem connector. Từ EMR release 7.10.0, S3A đã thay EMRFS làm S3 connector mặc định. Các release cũ có hành vi và cấu hình khác; kiểm tra scheme, connector và compatibility trước khi nâng cấp.

S3 phù hợp với raw/landing zone, curated data, Iceberg/Hudi/Delta table data, checkpoint, event log, artifact và job output. Nó cho phép chia sẻ dataset giữa nhiều cluster/job và giữ dữ liệu sau khi compute dừng.

### 5.3 Local disk và EBS

Local instance store phù hợp scratch, cache và shuffle tạm. Dữ liệu trên instance store mất khi instance bị terminate. EBS có thể cung cấp block storage bổ sung và có vòng đời khác local instance store; tuy nhiên, EBS volume gắn với cluster cần được tính chi phí và dọn theo lifecycle.

Không nhầm HDFS/local disk với S3. Nếu job thất bại sau khi cluster kết thúc, intermediate data trên local storage có thể không còn. Đưa dữ liệu cần phục hồi ra S3 hoặc durable storage.

### 5.4 Chọn storage theo pattern

| Pattern | Lựa chọn gợi ý |
|---|---|
| Đọc một lần, xử lý rồi ghi kết quả | S3A |
| Iterative algorithm đọc cùng data nhiều lần | Cache/HDFS hoặc local storage phù hợp |
| Shuffle lớn trong Spark | Local disk/EBS scratch theo benchmark |
| Dữ liệu cần dùng bởi nhiều cluster | S3 |
| Bảng transactional data lake | S3 + Iceberg/Hudi/Delta theo engine support |
| Temporary staging | Local/EBS nếu chấp nhận mất khi cluster kết thúc |

### 5.5 S3 layout, partitioning và file size

Tổ chức S3 prefix theo domain, zone, table và partition key. Không tạo partition quá nhỏ hoặc quá nhiều file nhỏ vì metadata overhead, listing và query planning có thể tăng. Dùng compaction để hợp nhất small files; chọn partition theo query pattern thay vì tạo partition cho mọi cột.

Với Spark, output task quá nhiều có thể tạo hàng nghìn file nhỏ. Điều chỉnh shuffle partitions, coalesce/repartition, file rolling và table format. Với Iceberg/Hudi/Delta, dùng cơ chế compaction/maintenance tương ứng.

## 6. EMR trên EKS: kiến trúc và khái niệm

EMR on EKS cho phép chạy runtime EMR trong các pod trên một Amazon EKS cluster. Tổ chức có thể chia sẻ EKS compute giữa data workloads và các ứng dụng Kubernetes khác, đồng thời dùng namespace và IAM execution role để cô lập tenant.

### 6.1 EKS cluster, namespace và virtual cluster

| Khái niệm | Ý nghĩa |
|---|---|
| EKS cluster | Kubernetes control plane và worker capacity |
| Kubernetes namespace | Ranh giới logic cho workload, service account, quota và resource |
| EMR virtual cluster | Namespace được đăng ký với EMR để gửi job |
| Job run | Một lần thực thi Spark/Flink application theo submission model |
| Job execution role | IAM role mà job/pod assume để truy cập AWS resource |

Virtual cluster chỉ là đăng ký namespace với EMR; bản thân virtual cluster không tạo resource compute chạy liên tục và không có charge riêng. Chi phí EKS cluster, worker nodes, storage, network và EMR runtime vẫn được tính theo các thành phần sử dụng.

Một EKS cluster có thể chứa nhiều namespace/virtual cluster. Mỗi virtual cluster ánh xạ tới một namespace. Việc chia namespace không tự động bảo đảm cách ly hoàn toàn; cần Kubernetes RBAC, IAM, network policy, resource quota, pod security và job execution role.

### 6.2 Luồng chạy Spark job

    Data engineer / Scheduler
              |
       StartJobRun API
              |
       EMR virtual cluster
              |
       Kubernetes namespace
              |
       Kubernetes scheduler
              |
       Driver pod + Executor pods
              |
       EMR runtime container image
              |
       S3 / Glue / Lake Formation / sinks

Khi submit job, EMR on EKS yêu cầu Kubernetes scheduler cấp pod. Container image chứa base OS, Spark và dependency của EMR release. Nếu image đã cache trên node, lần chạy sau có thể tránh tải lại image. Khi job kết thúc, pod được terminate; log và event log có thể được lưu ở S3/CloudWatch để debug sau đó.

### 6.3 Submission models

Các cách submit job phổ biến:

- StartJobRun API/CLI: gửi job run đến virtual cluster, chỉ định execution role, release label, job driver và configuration override.
- Spark Operator: mô tả Spark application bằng Kubernetes custom resource; operator quản lý lifecycle Spark app.
- spark-submit hoặc Livy theo submission model và release hỗ trợ.
- Với Flink: dùng Flink Kubernetes Operator hoặc Flink Native Kubernetes theo release hỗ trợ.

Chọn một submission model và chuẩn hóa cách logging, retry, tagging, ownership và deployment. Không để nhiều controller cùng quản lý một application.

### 6.4 EMR on EKS hỗ trợ Spark và Flink

EMR on EKS hỗ trợ Spark job run. Với Flink, EMR releases 6.13.0 trở lên hỗ trợ Flink Kubernetes Operator theo hướng dẫn hiện hành; Flink session mode được hỗ trợ từ release 6.15.0. Flink Operator quản lý lifecycle application; HA cần cấu hình metadata storage, checkpoint và job manager behavior phù hợp.

Release label quyết định runtime và framework version. Không suy luận rằng mọi EMR release đều có Spark/Flink cùng phiên bản hoặc cùng feature. Kiểm tra release compatibility matrix và supported releases cho submission model trước khi triển khai.

### 6.5 Job execution role

Job execution role là IAM role mà Spark/Flink pod sử dụng để đọc/ghi data. Role này tách biệt với quyền người dùng gọi StartJobRun và quyền quản lý EKS cluster.

Role thường cần quyền đọc script/JAR và data từ S3, ghi output/log/event log, truy cập Glue Data Catalog, đọc/ghi Kinesis/MSK/DynamoDB/database theo workload và dùng KMS key nếu dữ liệu mã hóa bằng customer managed key.

Với IRSA, trust policy gắn IAM role với Kubernetes service account qua OIDC provider. EMR on EKS cũng hỗ trợ EKS Pod Identity từ các release/submission model được tài liệu hóa, bắt đầu với EMR 7.3.0 cho StartJobRun. Kiểm tra compatibility và cấu hình role association trước khi chọn.

### 6.6 Job concurrency controls

Từ ngày 28-08-2026, EMR on EKS có job run admission controls cho virtual cluster:

- maxConcurrentJobRuns: số job run tối đa được chạy đồng thời.
- maxInQueueJobRuns: số job run tối đa được nhận vào queue chờ chạy.

Khi queue đầy, StartJobRun có thể trả ValidationException để caller backpressure hoặc gửi sang cluster khác. Hai giới hạn là tùy chọn; mặc định không áp dụng giới hạn. Tính năng này hữu ích cho shared EKS cluster nhiều tenant, tránh một nhóm job chiếm hết capacity.

### 6.7 Kubernetes compute capacity

EMR on EKS dùng worker capacity của EKS. EKS cluster có thể dùng EC2 node groups/managed node groups, Karpenter hoặc Fargate ở những workload/configuration được hỗ trợ. Với EC2, chi phí node và EBS phát sinh dù một phần capacity không được job sử dụng. Với Fargate, billing dựa trên vCPU/memory pod theo thời gian và quy tắc tối thiểu của Fargate.

Không dùng Fargate như giả định mặc định cho mọi EMR job. Kiểm tra feature, networking, storage, pod constraints, startup time và pricing của submission model cụ thể.

## 7. EMR Serverless: application và worker

EMR Serverless cho phép tạo application theo framework, sau đó gửi job mà không phải tạo hoặc quản lý EC2/EKS cluster cho compute job. Dịch vụ tự cấp worker, mở rộng theo nhu cầu và giải phóng worker khi job hoàn thành.

### 7.1 Application và job run

| Thành phần | Vai trò |
|---|---|
| Application | Định nghĩa framework type, EMR release, architecture, capacity limit, network và runtime configuration |
| Job run | Một lần thực thi Spark/Hive hoặc streaming workload được hỗ trợ |
| Driver | Điều phối job Spark |
| Executor/worker | Thực hiện task phân tán |
| Runtime role | IAM role cho job đọc/ghi data |
| Maximum capacity | Trần CPU, memory và disk của application |
| Pre-initialized capacity | Worker giữ sẵn để giảm startup latency |

EMR Serverless application type hiện chọn Spark hoặc Hive. Spark job có thể dùng Java/Scala JAR hoặc PySpark script. Với streaming, EMR Serverless hỗ trợ Spark Structured Streaming theo mode riêng, không phải Apache Flink runtime.

### 7.2 Worker sizing

Worker có các cấu hình vCPU, memory và ephemeral disk theo release. Tài liệu hiện hành liệt kê worker từ 1, 2, 4, 8, 16 đến 32 vCPU với memory range riêng theo size. Driver và executor có thể dùng size khác nhau.

Chọn worker theo driver memory/cores, executor cores/memory, Spark memory overhead, shuffle/spill disk, số executor đồng thời và data size/parallelism. Nếu worker memory quá nhỏ, job có thể OOM hoặc spill nhiều. Nếu worker quá lớn, có thể giảm khả năng scale nhỏ và gây lãng phí khi job chỉ cần ít tài nguyên.

### 7.3 Maximum capacity

Maximum capacity đặt giới hạn tổng CPU, memory và disk của application. Đây là guardrail chống một job hoặc burst submissions tiêu thụ quá nhiều capacity. Cấu hình maximum capacity theo số worker × cấu hình worker dự kiến, cộng headroom phù hợp.

Ví dụ nếu muốn giới hạn 40 worker, mỗi worker 2 vCPU, 16 GB memory và 40 GB disk:

    Maximum CPU    = 40 × 2  = 80 vCPU
    Maximum memory = 40 × 16 = 640 GB
    Maximum disk   = 40 × 40 = 1.600 GB

Đây là ví dụ sizing. Cần tính cả driver, executor, concurrency và quota account; job có thể fail khi application/account đạt maximum capacity.

### 7.4 Auto-start và auto-stop

EMR Serverless mặc định có thể auto-start khi submit job và auto-stop khi idle 15 phút. Khi application chuyển sang STOPPED, pre-initialized capacity được giải phóng. Có thể thay đổi hoặc tắt hành vi này.

Auto-stop giúp giảm chi phí capacity giữ sẵn, nhưng job tiếp theo có thể mất thời gian khởi động. Với workload chạy theo lịch thưa, auto-stop thường hợp lý; với interactive workload cần phản hồi nhanh, cân nhắc warm capacity.

### 7.5 Pre-initialized capacity

Pre-initialized capacity giữ driver/worker sẵn sàng để job bắt đầu nhanh. Đây là warm pool của application. Nếu capacity không được sử dụng, vẫn có thể phát sinh phí trong thời gian application ở trạng thái STARTED.

Dùng pre-initialized capacity khi job được submit thường xuyên, startup latency là yêu cầu sản phẩm, interactive session cần phản hồi nhanh hoặc tải nền ổn định đủ để tận dụng worker. Không giữ capacity lớn qua đêm nếu workload chỉ chạy vài phút mỗi ngày. Đặt idle timeout/auto-stop và chọn số worker dựa trên utilization.

### 7.6 Job concurrency và queueing

EMR Serverless hỗ trợ cấu hình maxConcurrentRuns và queueTimeoutMinutes cho application ở các release phù hợp. Khi đạt concurrency limit, job được queue thay vì cấp worker ngay. Queue giúp điều tiết burst submissions và tránh vượt application capacity.

Theo tài liệu hiện hành, job concurrency/queueing có từ EMR 7.0.0; từ 7.3.0 trở lên tính năng được bật mặc định theo mô tả dịch vụ. Kiểm tra release và cấu hình trước khi dựa vào behavior này.

### 7.7 Flex execution

Flex execution cho phép Spark batch job sử dụng spare capacity với mức giá khác Standard và có thể chờ lâu hơn để được cấp executor. Flex không phù hợp với job cần startup nhanh, streaming job hoặc interactive session. Nếu Flex job thất bại, không giả định dịch vụ tự chuyển sang Standard; cần resubmit theo quyết định orchestration.

### 7.8 Streaming jobs trên EMR Serverless

EMR Serverless hỗ trợ Spark Structured Streaming job từ EMR release 7.1.0 trở lên. Job chạy ở mode STREAMING, thường duy trì liên tục, sử dụng checkpoint để phục hồi tiến độ. Các connector hỗ trợ bao gồm Kinesis Data Streams và Kafka/MSK theo hướng dẫn connector.

Đặc điểm quan trọng:

- Chỉ Spark engine với Structured Streaming.
- Job chạy dài hạn; không đặt execution timeout theo cách batch thông thường.
- Có cơ chế auto-retry và AZ resiliency theo dịch vụ.
- Có log rotation và log compaction cho long-running job.
- Có checkpoint để khôi phục state/progress.
- Flex execution không hỗ trợ streaming job.

Nếu cần Apache Flink stateful streaming, hãy đánh giá EMR on EC2, EMR on EKS với Flink hoặc Managed Service for Apache Flink. Không chọn EMR Serverless Spark Streaming rồi coi nó là Flink.

## 8. Chọn deployment model theo workload

### 8.1 Batch ETL hằng ngày

Một job chạy mỗi đêm, đọc 5 TB từ S3, join và ghi Parquet/Iceberg:

- EMR Serverless phù hợp nếu tải biến động, job không quá dài và cần giảm vận hành cluster.
- EMR on EC2 phù hợp nếu job lớn, ổn định, cần Spot/instance fleet hoặc HDFS/local cache.
- EMR on EKS phù hợp nếu tổ chức đã có EKS platform, muốn chuẩn hóa namespace, scheduling và IAM.

### 8.2 Interactive SQL/analytics

Với truy vấn tương tác liên tục, startup latency và warm capacity quan trọng:

- EMR on EC2 có thể giữ cluster lâu dài với Trino/Hive/Spark theo cấu hình.
- EMR on EKS có thể chạy interactive endpoints và chia sẻ EKS capacity theo hỗ trợ.
- EMR Serverless có thể dùng pre-initialized capacity và interactive sessions theo tính năng hỗ trợ.

### 8.3 Multi-tenant platform

Nếu nhiều nhóm cùng gửi job:

- EMR on EKS cung cấp namespace, execution role, Kubernetes quota và scheduler policy.
- EMR Serverless tách application, runtime role và maximum capacity.
- EMR on EC2 có thể tách cluster/role/security configuration theo tenant nhưng thường tăng overhead vận hành.

Không coi namespace là ranh giới bảo mật duy nhất. Cần IAM, network, secret, S3 prefix/bucket policy và catalog permissions.

### 8.4 Streaming

| Nhu cầu | Mô hình cần xem xét |
|---|---|
| Spark Structured Streaming với tự cấp worker | EMR Serverless (release 7.1.0+) |
| Apache Flink trên Kubernetes | EMR on EKS với Flink Operator/release phù hợp |
| Apache Flink trên cluster EMR | EMR on EC2 |
| Spark/Flink cần control sâu về node/daemon | EMR on EC2 hoặc EKS tùy framework |

### 8.5 Custom AMI, bootstrap và native dependencies

Nếu cần cài driver, native library, daemon, kernel hoặc custom OS package, EMR on EC2 thường cho quyền kiểm soát cao nhất qua custom AMI và bootstrap actions. EMR on EKS có thể custom container image/pod template theo runtime. EMR Serverless có custom image nhưng phạm vi thay đổi phụ thuộc feature/runtime và yêu cầu tương thích.

### 8.6 Decision matrix

| Câu hỏi | Nếu câu trả lời là “có” | Hướng ưu tiên |
|---|---|---|
| Cần kiểm soát instance/AMI/bootstrap sâu? | Có | EMR on EC2 |
| Đã có EKS platform dùng chung và team Kubernetes mạnh? | Có | EMR on EKS |
| Job ngắn, tải thất thường, không muốn quản lý cluster? | Có | EMR Serverless |
| Cần HDFS hoặc local cluster storage? | Có | EMR on EC2 |
| Cần Spark hoặc Flink trên Kubernetes? | Có | EMR on EKS |
| Cần Spark Structured Streaming serverless? | Có | EMR Serverless |
| Cần nhiều framework trong cùng cluster? | Có | EMR on EC2 |
| Muốn quản lý nhiều job qua queue/capacity limit? | Có | EMR on EKS hoặc Serverless tùy platform |

## 9. Data lake integration: S3, Glue, Lake Formation và table formats

### 9.1 S3 layout

Một layout thường gặp:

    s3://company-lake/
      raw/
        source=orders/ingest_date=2026-11-20/
      staging/
        job=orders-normalize/run_id=...
      curated/
        domain=commerce/table=orders/
      analytics/
        product=finance/table=monthly_revenue/
      logs/
      checkpoints/
      artifacts/

Raw zone lưu dữ liệu nguồn theo dạng gần nguyên bản. Staging zone chứa intermediate data theo job/run. Curated zone chứa schema đã chuẩn hóa và chất lượng được kiểm tra. Analytics zone phục vụ data product hoặc consumer cụ thể.

Tách bucket/prefix theo môi trường, owner và data classification. Không để job production ghi đè raw input; dùng run ID, partition và atomic commit pattern phù hợp với table format.

### 9.2 AWS Glue Data Catalog

Glue Data Catalog lưu database, table, schema, partition và metadata cho data lake. Spark/Hive/Trino/Athena có thể tích hợp catalog theo engine/release hỗ trợ. Dùng catalog để nhiều compute engine hiểu cùng schema và location.

Khi job ghi bảng:

1. Xác định database/table và schema.
2. Chọn format như Parquet, Iceberg, Hudi hoặc Delta theo engine support.
3. Ghi data files vào S3.
4. Cập nhật metadata/catalog bằng cơ chế được table format hỗ trợ.
5. Kiểm tra snapshot/manifest/partition và concurrent writer behavior.

### 9.3 Lake Formation

Lake Formation quản lý quyền truy cập chi tiết trên database/table/column/row/cell trong Glue Data Catalog theo tích hợp hỗ trợ. Với EMR trên EC2, có thể dùng runtime roles và credential vending để job chỉ đọc dữ liệu được cấp quyền. Tích hợp cần đúng runtime release, Glue Catalog và Lake Formation configuration.

Không nhầm quyền IAM truy cập bucket với quyền Lake Formation. Một role có s3:GetObject không nhất thiết đã được cấp quyền đọc table qua Lake Formation; ngược lại, grant catalog không tự cấp mọi quyền KMS/network cần thiết.

### 9.4 Table formats

| Format | Đặc điểm | Lưu ý |
|---|---|---|
| Parquet | Columnar file format, nén tốt, đọc theo cột | Không tự cung cấp transaction/metadata management |
| Apache Iceberg | Snapshot, schema evolution, partition evolution, time travel | Kiểm tra catalog và engine compatibility |
| Apache Hudi | Upsert/incremental processing và table services | Cần quản lý compaction/clustering |
| Delta Lake | Transaction log và ACID semantics | Kiểm tra Delta runtime/integration support |

Table format ảnh hưởng write semantics, compaction, concurrent writers và khả năng query giữa các engine. Không chọn chỉ dựa vào benchmark một query; cần xét cả ingestion, update, delete, time travel, schema evolution và maintenance.

### 9.5 Small files và compaction

Job quá nhiều task nhỏ có thể tạo file output nhỏ, làm tăng metadata và query overhead. Giải pháp:

- Điều chỉnh partition count và shuffle partitions.
- Dùng coalesce/repartition có kiểm soát.
- Thiết lập target file size.
- Chạy compaction hoặc rewrite data files.
- Tránh partition theo cột cardinality rất cao.
- Theo dõi file count và average object size.

## 10. IAM và bảo mật

### 10.1 EMR on EC2 roles

EMR on EC2 có nhiều lớp role:

- Service role: cho EMR service quản lý AWS resources.
- EC2 instance profile: quyền của software trên EC2 node.
- Runtime role: quyền truy cập dữ liệu theo job/user nếu bật runtime role authorization.
- Người submit job: quyền tạo cluster, submit step, xem log và terminate theo policy.

Tách quyền quản lý hạ tầng khỏi quyền đọc dữ liệu. Nếu mọi job dùng instance profile quyền rộng, một job hoặc user có thể truy cập dữ liệu ngoài phạm vi nghiệp vụ.

### 10.2 EMR on EKS roles

Tách:

- IAM role của người submit/administrator.
- Job execution role cho driver/executor pod.
- EKS cluster/node role.
- Kubernetes service account và RBAC.
- IRSA hoặc EKS Pod Identity association.

Job execution role nên chỉ có quyền trên S3 prefix, Glue database/table, KMS key và log destination cần thiết. Người submit phải được phép iam:PassRole đúng role và không thể chọn role vượt phạm vi cho phép.

### 10.3 EMR Serverless runtime role

EMR Serverless sử dụng execution/runtime role cho từng job. Role cần quyền đọc input, ghi output, đọc script/JAR, truy cập Glue/KMS và ghi log theo cấu hình. Có thể giới hạn quyền job bằng execution IAM policy khi submission API hỗ trợ.

Không đặt access key dài hạn trong script, Spark config hoặc environment variable. Dùng role và secret manager.

### 10.4 Encryption

Mã hóa:

- S3 object bằng SSE-S3 hoặc SSE-KMS theo policy.
- EBS volume và local data theo cấu hình EMR/EC2.
- Data in transit bằng TLS.
- Log, checkpoint, snapshot và artifact.
- KMS key policy cho EMR service role, runtime role và data consumer.

Với EMR on EC2, security configuration có thể đặt encryption at rest cho EMRFS/S3 và local disk, cùng encryption in transit. HDFS transparent encryption có cấu hình riêng. Kiểm tra engine, release và connector.

### 10.5 Network

EMR on EC2 cần subnet, security group, route, NAT/VPC endpoint và access tới S3, Glue, KMS, CloudWatch, source/sink. Với private cluster, ưu tiên VPC endpoint cho AWS services nếu phù hợp.

EMR on EKS cần EKS cluster networking, pod IP capacity, security group for pods nếu dùng, CNI, DNS, node placement, private endpoint và egress. Namespace không tự cách ly network.

EMR Serverless mặc định có thể truy cập một số AWS service endpoint cùng Region mà không cần VPC connection; để truy cập private resource hoặc external service, cấu hình VPC/subnet/security group theo hướng dẫn. VPC mode có thể làm phát sinh NAT, endpoint và data transfer cost.

### 10.6 Data access governance

- Dùng bucket policy và prefix-level access.
- Dùng Lake Formation khi cần fine-grained catalog/table access.
- Dùng Apache Ranger trên EMR khi kiến trúc/release hỗ trợ và cần policy framework cho Hadoop ecosystem.
- Bảo vệ log và Spark UI vì có thể chứa query, path hoặc dữ liệu nhạy cảm.
- Tách dev/test/prod và account theo data classification.
- Audit bằng CloudTrail và log pipeline.

## 11. Triển khai và quản lý phiên bản

### 11.1 Chọn EMR release

EMR release label xác định phiên bản framework, library, Java, Python và runtime optimization. Chọn release dựa trên:

- Spark/Hadoop/Hive/Trino/Flink version cần dùng.
- Connector tương thích với nguồn và đích.
- Java/Python dependency.
- Security patch và support lifecycle.
- Feature cần thiết như Lake Formation, EKS submission model hoặc Graviton.

Không dùng latest một cách mù quáng trong production. Ghim release label và kiểm thử trước khi nâng cấp. Khi muốn tự nhận security update mới nhất, có thể dùng latest theo policy nhưng cần quản lý change window và regression test.

### 11.2 EMR on EC2 cluster lifecycle

    Create cluster
        |
    Provision EC2 instances
        |
    Bootstrap actions
        |
    Install EMR applications
        |
    RUNNING
        |
    Submit steps / interactive work
        |
    WAITING or TERMINATING
        |
    TERMINATED

Cluster có thể chạy transient, tự terminate sau step cuối hoặc long-running. Cluster long-running tiếp tục phát sinh chi phí cho đến khi được terminate. Dùng auto-termination policy cho cluster idle và termination protection cho cluster quan trọng để tránh shutdown nhầm.

### 11.3 Bootstrap actions và custom AMI

Bootstrap actions chạy trên node khi cluster khởi tạo để cài package, cấu hình daemon hoặc chuẩn bị môi trường. Custom AMI cung cấp kiểm soát sâu hơn về OS và package. Giữ script idempotent, versioned, có log và kiểm tra exit code. Không tải dependency không kiểm soát từ Internet trong production.

### 11.4 EMR on EKS job deployment

1. Tạo hoặc chọn EKS cluster và node capacity.
2. Tạo Kubernetes namespace cho workload.
3. Đăng ký namespace thành EMR virtual cluster.
4. Tạo job execution role và IRSA/Pod Identity association.
5. Cấu hình S3 log destination, Glue/KMS access và network.
6. Chọn EMR release label.
7. Submit job qua StartJobRun, Spark Operator hoặc Flink Operator.
8. Theo dõi job status, pod, Spark UI và logs.
9. Dọn virtual cluster/namespace theo lifecycle nếu không còn dùng.

### 11.5 EMR Serverless application deployment

1. Chọn application type Spark hoặc Hive.
2. Chọn EMR release và architecture x86_64/arm64 nếu hỗ trợ.
3. Cấu hình maximum capacity.
4. Cấu hình pre-initialized capacity nếu startup latency quan trọng.
5. Cấu hình auto-start/auto-stop và job concurrency.
6. Cấu hình VPC nếu cần truy cập private data.
7. Tạo runtime role.
8. Submit job với S3 script/JAR, parameters và monitoring configuration.
9. Theo dõi job run state và billedResourceUtilization.
10. Xóa application khi hết nhu cầu và kiểm tra log/data resource liên quan.

## 12. Orchestration và pipeline design

EMR thường là một bước trong pipeline lớn hơn:

    Event / Schedule
          |
    Step Functions / MWAA
          |
    Validate input
          |
    Submit EMR job
          |
    Wait / poll job status
          |
    Validate output and quality
          |
    Update catalog / publish event
          |
    Notify downstream

### 12.1 Idempotency

Job có thể retry khi lỗi hoặc orchestration timeout. Thiết kế output idempotent:

- Mỗi run có run_id.
- Dùng staging prefix trước khi publish.
- Validate record count/schema trước khi commit.
- Với Iceberg/Hudi/Delta, dùng transaction/commit semantics của table format.
- Tránh overwrite partition đang được consumer đọc nếu không có atomic publish strategy.

### 12.2 Retry và timeout

Không retry vô hạn lỗi cấu hình hoặc permission. Phân loại:

- Transient: capacity, network, throttling, temporary service issue.
- Data: corrupt record, schema mismatch, missing partition.
- Code: bug, OOM, wrong SQL.
- Security: AccessDenied, KMS deny, Lake Formation grant missing.

Retry chỉ các lỗi có khả năng tự phục hồi. Dùng exponential backoff và giới hạn attempts; lỗi data cần quarantine/DLQ hoặc remediation.

### 12.3 Dependency và concurrency

Nếu job A ghi partition mà job B đọc, orchestration phải chờ commit/validation xong. Với nhiều job đồng thời, kiểm soát concurrency theo application/virtual cluster, quota account, Glue catalog mutation và sink capacity.

## 13. Monitoring và troubleshooting

### 13.1 EMR on EC2

Theo dõi:

- Cluster state và step state.
- YARN pending containers, allocated memory/vcores.
- Spark executor lost, task retry, shuffle spill.
- HDFS capacity, disk utilization và DataNode health.
- EC2 CPU/network/EBS metrics.
- Spot interruption và instance replacement.
- CloudWatch logs và application logs trên S3.

### 13.2 EMR on EKS

Theo dõi:

- Job run state: SUBMITTED, PENDING, RUNNING, FAILED, CANCELLED.
- Pod state, pending reason, OOMKilled và restart count.
- Node CPU/memory/disk pressure.
- Kubernetes events, scheduler placement và quota.
- Driver/executor logs, Spark UI, Flink dashboard.
- Job queue/concurrency limit và StartJobRun errors.

Nếu pod Pending, kiểm tra node capacity, taints/tolerations, affinity, resource requests, subnet IP và quota. Nếu pod OOMKilled, xem container memory request/limit và Spark executor/driver overhead.

### 13.3 EMR Serverless

Theo dõi:

- Application state: CREATING, CREATED, STARTING, STARTED, STOPPING, STOPPED.
- Job state: SUBMITTED, QUEUED, PENDING, SCHEDULED, RUNNING, SUCCESS, FAILED, CANCELLING, CANCELLED.
- Worker allocation, billedResourceUtilization và application maximum capacity.
- Driver/executor logs, event logs và Spark UI.
- Queue timeout, concurrent runs và account service quota.
- Auto-start/auto-stop và pre-initialized capacity utilization.

Nếu job fail vì maximumCapacity, tăng capacity có kiểm soát hoặc giảm concurrency/worker size. Nếu worker không được allocate, kiểm tra account vCPU quota, application cap và worker configuration.

### 13.4 Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Cluster không launch | EC2 capacity, subnet IP, service role hoặc quota | Kiểm tra events, instance fleet và IAM |
| Job chờ YARN | Thiếu vCore/memory, container bị giữ | Xem YARN UI, scale hoặc điều chỉnh request |
| Spark OOM | Executor/driver memory thấp, skew, collect lớn | Giảm skew, tăng memory hợp lý, tránh collect |
| HDFS full | Core nodes thiếu disk hoặc intermediate data không cleanup | Tăng storage/scale core, dọn scratch đúng cách |
| S3 AccessDenied | IAM/KMS/bucket policy/Lake Formation | Kiểm tra runtime role và key policy |
| EMR on EKS pod Pending | Node capacity, quota, taint, subnet IP | Kiểm tra Kubernetes events và node group |
| EKS job AccessDenied | Job execution role hoặc trust policy sai | Kiểm tra IRSA/Pod Identity và iam:PassRole |
| Serverless job không start | Application chưa STARTED, max capacity/quota | Kiểm tra state, queue và account quota |
| Serverless worker OOM | Worker memory/overhead không đủ | Điều chỉnh driver/executor size |
| Job tạo nhiều file nhỏ | Partition/shuffle configuration không hợp lý | Coalesce/repartition và compaction |
| Job chạy lâu hơn dự kiến | Data skew, shuffle, spill, input tăng | Phân tích Spark UI/stage metrics |
| Chi phí cao dù job xong | Cluster idle, warm capacity hoặc storage còn giữ | Auto-terminate/auto-stop và rà soát resource |

## 14. Reliability, availability và disaster recovery

### 14.1 Decouple storage và compute

Lưu dữ liệu bền vững trên S3, catalog và checkpoint location phù hợp. Cluster hoặc pod có thể bị thay thế mà không mất raw/curated data. HDFS/local disk chỉ nên chứa intermediate data có thể tái tạo.

### 14.2 Multi-AZ

EMR on EC2 cluster chạy trong một Availability Zone theo cluster placement; để tăng resilience, cần thiết kế lại job orchestration và data storage, có thể tái tạo cluster ở AZ khác. EMR on EKS chạy trên EKS cluster multi-AZ; pod placement và node group cần spread topology. EMR Serverless cung cấp AZ resiliency cho các streaming jobs theo tài liệu dịch vụ; vẫn cần thiết kế downstream durability và retry.

### 14.3 Checkpoint và retry

Spark Structured Streaming sử dụng checkpoint location để lưu tiến độ và state. Flink dùng checkpoint/savepoint. Batch job cần output commit và idempotency. Đừng đặt checkpoint trong local disk hoặc HDFS nếu cần phục hồi qua cluster replacement.

### 14.4 Recovery objectives

Định nghĩa:

- RPO: lượng dữ liệu/tiến độ tối đa chấp nhận phải xử lý lại hoặc mất.
- RTO: thời gian tối đa để khôi phục pipeline.
- Replay window: source retention đủ dài để chạy lại.
- Recovery capacity: compute có thể provision ở Region/AZ khác.
- Data consistency: downstream có thể chịu duplicate/replay không?

### 14.5 Cross-Region

Nếu có DR cross-Region:

- Replicate S3 data và metadata/catalog cần thiết.
- Giữ artifact, config, secret và KMS key ở Region đích.
- Kiểm tra Glue Catalog/Lake Formation permissions.
- Đảm bảo EMR release và EC2/EKS capacity có sẵn.
- Tính phí replication, inter-Region transfer và storage.
- Test runbook khôi phục thay vì chỉ dựa vào tài liệu.

## 15. Chi phí và tối ưu

### 15.1 EMR trên EC2

Tổng chi phí có thể gồm:

    EMR EC2 total
      = EMR service charge
      + EC2 On-Demand / Spot
      + EBS / instance storage
      + S3 / Glue / KMS / CloudWatch
      + NAT / VPC endpoints / data transfer

EC2 cluster tiếp tục tính phí khi ở WAITING nếu chưa terminate. Dùng transient cluster, step execution termination hoặc auto-termination policy để tránh idle cost. Spot và managed scaling có thể giảm compute cost nhưng cần resilience.

### 15.2 EMR trên EKS

Chi phí gồm:

- EMR uplift theo vCPU-hour và GB-memory-hour được request bởi EMR pod. Thời gian tính từ lúc tải EMR application image đến khi pod kết thúc, làm tròn theo giây.
- EKS cluster control plane charge.
- EC2 worker node hoặc Fargate.
- EBS, network, NAT, data transfer và logging.
- S3/Glue/KMS và downstream services.

Virtual cluster không tạo compute charge riêng. Dùng chung EKS cluster có thể giảm cluster overhead, nhưng node capacity idle vẫn có chi phí. Phân bổ node cost theo namespace/resource usage để tránh đánh giá thấp cost của workload.

AWS công bố giảm 30% EMR charge trên EKS từ 23-10-2026 cho cả vCPU và memory uplift; chi phí EKS cơ bản không đổi. Kiểm tra pricing page hiện hành theo Region vì giá có thể thay đổi.

### 15.3 EMR Serverless

EMR Serverless tính theo aggregate vCPU, memory và storage worker sử dụng trong khoảng worker sẵn sàng chạy đến khi dừng, làm tròn theo giây với mức tối thiểu một phút cho worker. Billing detail có thể bao gồm storage bổ sung vượt 20 GB mỗi worker; hãy kiểm tra worker configuration và pricing theo Region. Usage của pre-initialized worker không dùng trong job không xuất hiện trong billedResourceUtilization của job, nhưng capacity giữ sẵn vẫn có thể phát sinh chi phí khi application ở trạng thái STARTED.

Chi phí phụ thuộc worker vCPU/memory size và duration, số driver/executor, ephemeral storage và shuffle, Standard hay Flex execution, pre-initialized capacity và idle timeout, application/job concurrency, source/sink, S3, CloudWatch, VPC và network.

### 15.4 So sánh chi phí theo utilization

| Tình huống | Mô hình có thể phù hợp |
|---|---|
| Cluster chạy 24/7 và utilization cao | EMR EC2 hoặc EKS shared capacity |
| Batch job thưa, mỗi job ngắn | EMR Serverless |
| Batch job lớn, ổn định, có thể dùng Spot | EMR EC2 hoặc EMR on EKS |
| Nhiều nhóm đã dùng EKS, compute pool chia sẻ tốt | EMR on EKS |
| Cần warm startup cho job nhỏ liên tục | Serverless với pre-initialized capacity, sau khi tính idle cost |
| Cần HDFS/local cache và custom AMI | EMR EC2 |

### 15.5 Tối ưu thực tế

- Benchmark instance family, Graviton và worker size.
- Điều chỉnh Spark executor cores/memory và dynamic allocation.
- Giảm shuffle, skew và unnecessary repartition.
- Dùng Parquet/columnar format và partition phù hợp.
- Compaction small files.
- Dùng Spot cho phần capacity chịu interruption.
- Bật managed scaling hoặc auto-stop/auto-termination.
- Giới hạn maximum capacity và concurrency.
- Giảm pre-initialized capacity khi utilization thấp.
- Dừng cluster/application khi không còn dùng.
- Tối ưu log retention và metric cardinality.
- Theo dõi cost per TB processed hoặc cost per successful job.

## 16. Ví dụ thiết kế: pipeline dữ liệu đơn hàng

### 16.1 Yêu cầu

Một công ty bán lẻ nhận dữ liệu đơn hàng từ nhiều hệ thống. Mỗi ngày có 2 TB raw data, cần chuẩn hóa schema, loại record lỗi, join thông tin sản phẩm và khách hàng, sau đó ghi curated tables để BI và machine learning sử dụng.

### 16.2 Luồng dữ liệu

    Source systems
        |
    S3 raw zone
        |
    Glue Catalog / Lake Formation
        |
    EMR job (Spark)
        |
    Validate + normalize + join
        |
    S3 curated (Iceberg/Parquet)
        |
    Athena / Redshift / SageMaker / BI

### 16.3 Chọn mô hình

Giả sử workload chỉ chạy một lần mỗi ngày, không cần HDFS, không cần cluster interactive và tải có thể biến động:

- EMR Serverless là phương án khởi đầu phù hợp để giảm cluster management.
- Đặt maximum capacity để giới hạn chi phí.
- Dùng Spark dynamic allocation và worker sizing theo benchmark.
- Dùng S3/Glue Catalog và runtime role.
- Nếu job tăng lên nhiều giờ mỗi ngày hoặc utilization ổn định, benchmark lại EMR EC2/EMR on EKS.

Nếu tổ chức đã có EKS data platform và muốn chuẩn hóa scheduling/namespace, có thể chạy cùng job trên EMR on EKS. Nếu job cần HDFS cache hoặc custom AMI, EMR on EC2 có thể phù hợp hơn.

### 16.4 Kiểm soát chất lượng và commit

Job ghi vào staging prefix theo run_id. Sau khi kiểm tra schema, row count, null ratio và duplicate key, job commit vào curated table. Nếu job fail, giữ staging để debug theo retention; không publish output chưa hoàn chỉnh.

### 16.5 Unit economics

    Cost per TB processed = monthly EMR + related cost / TB input processed
    Cost per successful run = allocated pipeline cost / successful runs

Kết hợp chi phí với duration, throughput, output quality và freshness. Một job nhanh hơn nhưng tạo nhiều small files hoặc cần compaction lớn có thể làm tổng TCO cao hơn.

## 17. Lab A: tạo EMR cluster trên EC2

### Mục tiêu

Tạo cluster EMR chạy Spark, đọc dữ liệu từ S3, ghi output và tự terminate sau khi hoàn thành.

### Chuẩn bị

- AWS account và Region lab.
- S3 bucket chứa input, output và log.
- IAM service role và EC2 instance profile phù hợp.
- VPC/subnet có route tới S3.
- AWS CLI v2 hoặc EMR console.

### Bước 1: chuẩn bị dữ liệu

1. Tạo prefix raw/orders/.
2. Upload file CSV/JSON nhỏ.
3. Xác định schema và expected output.
4. Tạo prefix curated/orders/.

### Bước 2: tạo cluster

1. Mở Amazon EMR console.
2. Chọn EMR on EC2.
3. Chọn release label có Spark.
4. Chọn primary/core node và instance type nhỏ phù hợp lab.
5. Chọn subnet, security group và IAM role.
6. Cấu hình S3 log URI.
7. Bật auto-termination hoặc terminate after last step.
8. Tạo cluster.

### Bước 3: submit Spark step

Có thể dùng SparkPi sample hoặc script PySpark đọc S3, transform và ghi Parquet. Xem step state và YARN/Spark UI.

### Bước 4: xác minh output

1. Kiểm tra S3 curated prefix.
2. Đọc schema và row count.
3. So sánh với input.
4. Xác minh cluster đã terminate.
5. Kiểm tra log vẫn tồn tại ở S3.

### Bước 5: dọn lab

Xóa S3 input/output/log khi không cần, terminate cluster nếu chưa tự terminate và rà soát EBS volume, security group hoặc resource phát sinh.

## 18. Lab B: chạy Spark job trên EMR on EKS

### Mục tiêu

Đăng ký một Kubernetes namespace thành virtual cluster, submit Spark job và kiểm tra job pod/log.

### Chuẩn bị

- EKS cluster có node capacity phù hợp.
- Namespace riêng cho lab.
- IAM role cho job execution.
- IRSA hoặc EKS Pod Identity theo release hỗ trợ.
- S3 bucket input/output/log.
- EMR release label hỗ trợ.

### Bước 1: tạo virtual cluster

1. Tạo namespace, ví dụ emr-lab.
2. Đăng ký namespace với EMR bằng create-virtual-cluster.
3. Lưu virtual cluster ID.
4. Xác minh namespace mapping.

### Bước 2: cấu hình role

1. Tạo job execution role.
2. Cấp quyền S3/Glue/KMS/CloudWatch cần thiết.
3. Cấu hình trust policy cho IRSA hoặc Pod Identity.
4. Cấp quyền người submit gọi StartJobRun và iam:PassRole đúng role.

### Bước 3: submit job

Ví dụ khung lệnh:

    aws emr-containers start-job-run \
      --virtual-cluster-id <VIRTUAL_CLUSTER_ID> \
      --name orders-etl-lab \
      --execution-role-arn <JOB_EXECUTION_ROLE_ARN> \
      --release-label <SUPPORTED_EMR_RELEASE> \
      --job-driver '<JOB_DRIVER_JSON>' \
      --region <AWS_REGION>

Thay các giá trị mẫu bằng ID/ARN thực tế và job driver theo Spark job. Không đưa credential vào command hoặc script.

### Bước 4: quan sát

1. Xem job run status.
2. Dùng kubectl xem driver/executor pods.
3. Xem Kubernetes events nếu pod Pending.
4. Mở Spark UI/logs.
5. Kiểm tra S3 output.

### Bước 5: dọn lab

Hủy job còn chạy, xóa virtual cluster nếu không còn dùng, xóa namespace theo quy trình, thu hồi role association và dọn log/data theo retention.

## 19. Lab C: chạy Spark job trên EMR Serverless

### Mục tiêu

Tạo Spark application, cấu hình maximum capacity, submit PySpark job và kiểm tra billed resource utilization.

### Bước 1: tạo application

1. Chọn type SPARK.
2. Chọn EMR release phù hợp.
3. Chọn x86_64 hoặc arm64 nếu dependency hỗ trợ.
4. Đặt maximum capacity.
5. Chọn auto-start/auto-stop.
6. Chọn pre-initialized capacity chỉ khi cần startup nhanh.

### Bước 2: tạo runtime role

Role cần quyền đọc script/input, ghi output, truy cập Glue/KMS và ghi log. Giới hạn S3 prefix theo lab.

### Bước 3: submit job

    aws emr-serverless start-job-run \
      --application-id <APPLICATION_ID> \
      --execution-role-arn <JOB_RUNTIME_ROLE_ARN> \
      --job-driver '{
        "sparkSubmit": {
          "entryPoint": "s3://<BUCKET>/scripts/orders_etl.py",
          "entryPointArguments": [
            "s3://<BUCKET>/raw/orders/",
            "s3://<BUCKET>/curated/orders/"
          ],
          "sparkSubmitParameters": "--conf spark.executor.cores=2 --conf spark.executor.memory=4g --conf spark.driver.cores=1 --conf spark.driver.memory=2g"
        }
      }' \
      --region <AWS_REGION>

### Bước 4: kiểm tra job

1. Xem job state từ SUBMITTED đến SUCCESS/FAILED.
2. Mở driver/executor logs.
3. Kiểm tra S3 output.
4. Gọi GetJobRun để xem billedResourceUtilization.
5. So sánh duration và worker sizing.

### Bước 5: dọn application

Chờ job kết thúc, xóa application nếu không còn dùng, kiểm tra pre-initialized capacity đã giải phóng và xóa log/artifact theo policy.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Amazon EMR giải quyết vấn đề gì?

**Đáp án:** Cung cấp runtime và hạ tầng tích hợp để chạy framework xử lý dữ liệu phân tán như Spark, Hadoop, Hive, Trino và các engine được hỗ trợ.

**Câu 2.** Ba deployment model chính là gì?

**Đáp án:** EMR trên EC2, EMR trên EKS và EMR Serverless.

**Câu 3.** Primary node có nhiệm vụ gì?

**Đáp án:** Quản lý cluster và điều phối thành phần như YARN ResourceManager, HDFS NameNode theo cấu hình.

**Câu 4.** Core node khác task node thế nào?

**Đáp án:** Core node vừa chạy task vừa lưu HDFS; task node chỉ cung cấp compute, không lưu HDFS.

**Câu 5.** Khi nào dùng instance fleets?

**Đáp án:** Khi muốn kết hợp nhiều EC2 instance type và target On-Demand/Spot linh hoạt để tăng khả năng lấy capacity.

**Câu 6.** Vì sao task node là ứng viên Spot tốt?

**Đáp án:** Task node không giữ HDFS persistent data nên có thể bị thu hồi với tác động thấp hơn nếu job có retry và capacity dự phòng.

**Câu 7.** HDFS có phải durable storage không?

**Đáp án:** Không. HDFS trên EMR EC2 gắn với cluster và bị thu hồi khi cluster terminate; dữ liệu lâu dài nên ở S3.

**Câu 8.** Từ EMR release nào S3A thay EMRFS làm default S3 connector?

**Đáp án:** EMR 7.10.0.

**Câu 9.** Virtual cluster của EMR on EKS là gì?

**Đáp án:** Namespace Kubernetes được đăng ký với EMR; nó không tự tạo compute resource riêng.

**Câu 10.** Job execution role trên EMR on EKS dùng để làm gì?

**Đáp án:** Cấp quyền AWS cho driver/executor pod khi job đọc/ghi dữ liệu và gọi dịch vụ.

**Câu 11.** EMR on EKS hỗ trợ Flink từ release nào?

**Đáp án:** EMR 6.13.0 trở lên hỗ trợ Flink Operator theo tài liệu; session mode từ 6.15.0.

**Câu 12.** Job concurrency controls trên EMR on EKS có tác dụng gì?

**Đáp án:** Giới hạn số job chạy đồng thời và số job được xếp hàng trong virtual cluster để bảo vệ shared EKS capacity.

**Câu 13.** EMR Serverless application type thường chọn gì?

**Đáp án:** Spark hoặc Hive.

**Câu 14.** EMR Serverless có hỗ trợ HDFS không?

**Đáp án:** Không. Worker disk là temporary storage cho shuffle/processing; dữ liệu lâu dài dùng S3 hoặc dịch vụ storage phù hợp.

**Câu 15.** Pre-initialized capacity có thể phát sinh chi phí khi idle không?

**Đáp án:** Có. Worker giữ sẵn vẫn được tính phí trong thời gian application STARTED dù chưa có job sử dụng.

**Câu 16.** EMR Serverless streaming jobs dùng engine nào?

**Đáp án:** Spark Structured Streaming từ EMR release 7.1.0 trở lên; không phải Flink.

**Câu 17.** Flex execution phù hợp với job nào?

**Đáp án:** Spark batch job chịu được startup delay và có thể dùng spare capacity; không phù hợp streaming hoặc interactive job.

**Câu 18.** EMR on EKS cost gồm những gì?

**Đáp án:** EMR uplift theo vCPU/memory, EKS cluster, EC2/Fargate worker, EBS, network, logs và data services.

**Câu 19.** Vì sao phải đặt maximum capacity trên EMR Serverless?

**Đáp án:** Giới hạn tổng CPU/memory/disk để kiểm soát chi phí, tránh một application tiêu thụ quá nhiều account capacity.

**Câu 20.** Vì sao cần idempotent output trong orchestration?

**Đáp án:** Job có thể retry hoặc chạy lại; output idempotent giúp tránh duplicate, overwrite sai hoặc publish dữ liệu chưa hoàn chỉnh.

## 21. Checklist production readiness

- [ ] Deployment model phù hợp với workload và kỹ năng vận hành.
- [ ] EMR release/framework/connector compatibility được xác minh.
- [ ] EC2 node types, instance groups/fleets và Spot policy được thiết kế nếu dùng EC2.
- [ ] HDFS chỉ chứa intermediate data có thể tái tạo.
- [ ] S3 layout, lifecycle, partitioning và file size có quy chuẩn.
- [ ] EKS namespace/virtual cluster, node capacity và quota rõ ràng nếu dùng EKS.
- [ ] Job execution role theo least privilege và trust policy đúng.
- [ ] IRSA/Pod Identity được kiểm tra theo release/submission model.
- [ ] EMR Serverless maximum capacity, worker sizing và concurrency được đặt.
- [ ] Pre-initialized capacity chỉ bật khi có lý do latency và utilization.
- [ ] Streaming mode được phân biệt rõ giữa Spark Structured Streaming và Flink.
- [ ] Glue Catalog/Lake Formation permissions đã được test.
- [ ] S3/KMS/network encryption được cấu hình.
- [ ] Logs, metrics, Spark UI và alerts có owner.
- [ ] Retry, timeout, idempotency và output commit được thiết kế.
- [ ] Checkpoint/replay/source retention đáp ứng RPO/RTO.
- [ ] Auto-termination/auto-stop và cleanup policy được bật phù hợp.
- [ ] Chi phí EMR, EC2/EKS, EBS, storage, network và logs được ước tính.
- [ ] Có load test, failure test và rollback plan.
- [ ] Savings/unit cost được đo từ actual usage sau triển khai.

## 22. Tài liệu tham khảo chính thức

1. [Amazon EMR – Getting started](https://aws.amazon.com/emr/getting-started/) — tổng quan ba deployment model.
2. [Understanding EMR clusters and nodes](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-overview.html) — cluster lifecycle và node types.
3. [Primary, core, and task nodes](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-master-core-task-nodes.html) — vai trò từng node.
4. [Configure EMR cluster hardware and networking](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-plan-instances.html) — EC2 instance và network.
5. [Instance fleets](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-instance-fleet.html) — target capacity và allocation strategy.
6. [Managed scaling](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-managed-scaling.html) — tự điều chỉnh cluster capacity.
7. [Working with storage and file systems](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-plan-file-systems.html) — HDFS, S3A và local storage.
8. [EMRFS](https://docs.aws.amazon.com/emr/latest/ReleaseGuide/emr-fs.html) — thay đổi mặc định S3 connector ở EMR 7.10.0.
9. [Auto-termination policy](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-auto-termination-policy.html) — dọn cluster idle.
10. [EMR on EKS concepts](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/emr-eks-concepts.html) — namespace, virtual cluster và job run.
11. [Running Spark jobs on EMR on EKS](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/job-runs-main.html) — submit job và Spark Operator.
12. [Running Flink jobs on EMR on EKS](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/run-flink-jobs.html) — Flink Operator và native Kubernetes.
13. [Job execution roles on EMR on EKS](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/iam-execution-role.html) — IAM execution role.
14. [EMR on EKS security best practices](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/security-best-practices.html) — least privilege và tenant isolation.
15. [EMR Serverless application behavior](https://docs.aws.amazon.com/emr/latest/EMR-Serverless-UserGuide/app-behavior.html) — worker sizing, maximum capacity và lifecycle.
16. [Pre-initialized capacity](https://docs.aws.amazon.com/emr/latest/EMR-Serverless-UserGuide/pre-init-capacity.html) — warm workers và idle cost.
17. [EMR Serverless job concurrency and queuing](https://docs.aws.amazon.com/emr/latest/EMR-Serverless-UserGuide/applications-concurrency-queuing.html) — điều tiết job submissions.
18. [EMR Serverless streaming jobs](https://docs.aws.amazon.com/emr/latest/EMR-Serverless-UserGuide/jobs-streaming.html) — Spark Structured Streaming và resiliency.
19. [EMR Serverless pricing](https://aws.amazon.com/emr/pricing/) — vCPU, memory, storage và execution mode.
20. [EMR on EKS job concurrency controls – August 28, 2026](https://aws.amazon.com/about-aws/whats-new/2026/08/amazon-emr-eks/) — giới hạn job run và queue.
21. [EMR on EKS 30% pricing reduction – October 23, 2026](https://aws.amazon.com/about-aws/whats-new/2026/10/emr-eks-reduces-emr-charge-30-percent/) — cập nhật EMR uplift.
22. [Integrate EMR with Lake Formation](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-lake-formation.html) — fine-grained data access.
23. [EMR security and encryption](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-security.html) — shared responsibility, IAM và data protection.

---

**Kết luận:** EMR trên EC2, EKS và Serverless cùng phục vụ xử lý dữ liệu lớn nhưng tối ưu cho những cách vận hành khác nhau. EC2 cho quyền kiểm soát cluster và storage; EKS đưa Spark/Flink vào nền tảng Kubernetes dùng chung; Serverless giảm quản lý compute cho Spark/Hive và Spark Structured Streaming. Hãy chọn theo workload, release compatibility, storage semantics, isolation, startup latency, utilization và tổng chi phí, sau đó kiểm chứng bằng benchmark và failure test trước production.
