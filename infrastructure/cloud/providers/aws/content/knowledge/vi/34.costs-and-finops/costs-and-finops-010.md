# Compute Optimizer và tối ưu kích thước tài nguyên

Một workload AWS có thể chạy ổn định nhưng vẫn tốn nhiều chi phí hơn mức cần thiết. Một EC2 instance có 16 vCPU trong khi ứng dụng chỉ dùng một phần nhỏ; một EBS volume được cấp IOPS cao hơn nhu cầu; một Lambda function cấp quá nhiều memory; hoặc một ECS service trên Fargate giữ task size lớn dù tải thực tế thấp. Ngược lại, giảm cấu hình quá mức có thể làm tăng latency, timeout, lỗi và chi phí vận hành.

**Right-sizing** là quá trình điều chỉnh loại và kích thước tài nguyên để đáp ứng nhu cầu thực tế của workload với chi phí hợp lý. Đây không đơn thuần là chọn cấu hình nhỏ nhất. Một cấu hình tốt phải có đủ headroom cho peak, tăng trưởng, biến động tải và các yêu cầu về độ trễ, tính sẵn sàng.

**AWS Compute Optimizer** phân tích cấu hình tài nguyên và dữ liệu sử dụng để đưa ra khuyến nghị tối ưu. Dịch vụ giúp xác định tài nguyên có thể đang over-provisioned, under-provisioned, đã tối ưu hoặc không đủ dữ liệu để kết luận. Người vận hành có thể xem các lựa chọn, mức rủi ro hiệu năng, biểu đồ utilization và ước tính tiết kiệm trước khi quyết định thay đổi.

Trong hệ sinh thái **CLOUD_PROVIDERS_AWS**, Compute Optimizer hỗ trợ thực hành FinOps bằng dữ liệu đo lường thay vì chỉ dựa vào cảm nhận. Mục tiêu của module là giúp người học chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí. Vì vậy, cần kết hợp khuyến nghị với ngữ cảnh nghiệp vụ, SLO, lịch tải, kiến trúc, giá mua thực tế và quy trình thay đổi có kiểm soát.

## 1. Right-sizing giải quyết vấn đề gì?

Tài nguyên quá lớn gây lãng phí chi phí cố định hoặc chi phí theo giờ. Tài nguyên quá nhỏ có thể gây nghẽn CPU, memory, IOPS, throughput hoặc network. Cả hai tình huống đều ảnh hưởng tới hiệu quả kinh doanh:

- Over-provisioning làm doanh nghiệp trả tiền cho capacity không sử dụng.
- Under-provisioning làm tăng latency, lỗi, queue backlog, thời gian xử lý và nguy cơ vi phạm SLO.
- Cấu hình sai loại tài nguyên có thể gây nghẽn dù số vCPU hoặc dung lượng tổng có vẻ đủ.
- Tài nguyên nhàn rỗi vẫn phát sinh chi phí dù không tạo ra giá trị.

Ví dụ, một máy chủ database có CPU trung bình 8% nhưng memory luôn gần đầy và swap tăng. Chỉ dựa trên CPU để giảm instance có thể khiến database bị thiếu memory. Một volume gp2 có IOPS trung bình thấp nhưng burst balance thường xuyên cạn; đổi sang volume nhỏ hơn có thể làm hiệu năng tệ hơn. Right-sizing phải nhìn vào các chiều tài nguyên liên quan, không chỉ một metric.

### Các nguyên tắc

1. Dùng dữ liệu quan sát đủ dài để bao quát tải bình thường và peak.
2. Xem cả average, maximum, percentile và xu hướng theo thời gian.
3. Giữ headroom phù hợp với SLO và tốc độ tăng trưởng.
4. Kiểm tra dependency, quota, license, kiến trúc CPU và đặc tính lưu trữ.
5. Thử nghiệm thay đổi theo canary hoặc từng nhóm nhỏ.
6. Đo chi phí và hiệu năng sau thay đổi, rồi cập nhật baseline.

## 2. AWS Compute Optimizer hoạt động như thế nào?

Compute Optimizer là dịch vụ phân tích được quản lý. Sau khi account được opt in, dịch vụ đánh giá thông tin cấu hình và utilization metrics của những resource type được hỗ trợ. Từ đó, dịch vụ tạo finding và một hoặc nhiều recommendation options.

Quy trình khái quát:

~~~mermaid
flowchart TD
    A[Opt in Compute Optimizer] --> B[Đọc cấu hình resource]
    B --> C[Phân tích CloudWatch và telemetry được hỗ trợ]
    C --> D[Đánh giá workload theo lookback period]
    D --> E[Finding và recommendation options]
    E --> F[Đánh giá performance risk và savings]
    F --> G[Owner xác minh ngữ cảnh]
    G --> H[Thử nghiệm và thay đổi có kiểm soát]
    H --> I[Theo dõi metric và chi phí sau thay đổi]
~~~

Compute Optimizer không dự đoán chắc chắn mọi thay đổi tải trong tương lai. Khuyến nghị chủ yếu dựa trên cấu hình và lịch sử sử dụng trong khoảng thời gian phân tích. Người vận hành phải bổ sung kế hoạch ra mắt sản phẩm, mùa cao điểm, batch job, tăng trưởng, sự kiện đặc biệt và yêu cầu phục hồi.

### Recommendation không đồng nghĩa với lệnh thay đổi

Khuyến nghị là thông tin hỗ trợ quyết định. Đội vận hành cần xác minh tương thích, đánh giá rủi ro, chọn thời điểm triển khai và chuẩn bị rollback. Một số tài khoản/Region có thể bật Compute Optimizer Automation để áp dụng một số recommended actions được hỗ trợ, nhưng phạm vi action tự động không bao phủ mọi loại right-sizing recommendation.

## 3. Bật Compute Optimizer và quản lý nhiều account

Compute Optimizer cần được opt in. Dịch vụ có thể được bật cho account độc lập hoặc quản lý ở cấp AWS Organizations thông qua management account và delegated administrator theo mô hình được hỗ trợ.

Một tổ chức nhiều account nên:

1. Chọn account chuyên trách FinOps hoặc Security/Platform làm delegated administrator khi phù hợp.
2. Opt in Compute Optimizer tại các Region cần phân tích.
3. Đăng ký member account và kiểm tra trạng thái enrollment.
4. Cấp quyền đọc cần thiết để dịch vụ truy cập cấu hình resource và CloudWatch metrics.
5. Bật Cost Explorer để Compute Optimizer có dữ liệu billing cần thiết cho thông tin giá và savings estimate.
6. Cân nhắc opt in Cost Optimization Hub để xem khuyến nghị rightsizing cùng bối cảnh Savings Plans và Reserved Instances đang có.
7. Xây dựng dashboard hoặc export recommendations để theo dõi tiến độ theo account, Region, application và owner.

Compute Optimizer là dịch vụ theo Region cho các recommendation tương ứng. Bật ở một Region không có nghĩa toàn bộ Region khác đã được bao phủ. Cần kiểm tra enrollment và coverage cho từng Region trong phạm vi tổ chức.

### Quyền truy cập

Tách quyền xem recommendation khỏi quyền sửa resource. FinOps analyst có thể cần quyền đọc recommendation và billing; workload owner có thể xem tài nguyên của nhóm mình; deployment role mới có quyền sửa instance type, volume hoặc memory setting. Không cấp quyền quản trị rộng chỉ để xem báo cáo.

## 4. Những resource type được hỗ trợ

Phạm vi Compute Optimizer rộng hơn EC2. Tuy nhiên, mỗi resource type có loại recommendation và điều kiện riêng. Cần phân biệt **rightsizing recommendation** với **idle resource recommendation**.

| Resource | Recommendation tiêu biểu | Nội dung tối ưu |
|---|---|---|
| EC2 instances | Rightsizing và idle | Instance family/type, vCPU, memory, kiến trúc và hiệu năng |
| EC2 Auto Scaling groups | Rightsizing và idle | Instance types phù hợp với cấu hình group và scaling policy |
| EBS volumes | Rightsizing và idle/unattached | Volume type, size, IOPS, throughput hoặc phát hiện volume không dùng |
| Lambda functions | Memory rightsizing | Mức memory phù hợp với duration và workload |
| ECS services trên Fargate | Task/container CPU và memory | Task size và container resource settings |
| RDS DB instances và Aurora | Instance và storage recommendations | Compute, storage, IOPS và throughput theo loại database |
| Commercial software licenses | License recommendations | Microsoft SQL Server trên EC2 theo điều kiện hỗ trợ |
| NAT Gateway | Idle | Phát hiện gateway có mức sử dụng thấp theo tiêu chí dịch vụ |
| DynamoDB provisioned tables | Idle | Bảng provisioned có dấu hiệu không hoạt động |
| ElastiCache, MemoryDB, DocumentDB | Idle | Cluster hoặc database ít/không sử dụng theo tiêu chí hỗ trợ |
| WorkSpaces và SageMaker endpoints | Idle | Tài nguyên ít sử dụng hoặc không hoạt động |

Danh sách resource và loại recommendation có thể thay đổi theo thời gian. Một số tài nguyên trong bảng chỉ có idle recommendation, không có quyền suy ra rằng Compute Optimizer sẽ đề xuất mọi loại thay đổi cấu hình cho chúng.

## 5. Lookback period và chất lượng dữ liệu

Mặc định, Compute Optimizer thường phân tích utilization trong 14 ngày gần nhất. Với Enhanced Infrastructure Metrics được bật cho resource type đủ điều kiện, lookback có thể mở rộng tới 93 ngày. Enhanced Infrastructure Metrics là tính năng có tính phí; cần cân nhắc lợi ích của lịch sử dài hơn với ngân sách.

Recommendations thường được làm mới hằng ngày. Sau khi opt in hoặc khi chưa đủ dữ liệu, việc tạo recommendation có thể mất tới khoảng 24 giờ hoặc lâu hơn tùy resource và điều kiện dữ liệu.

Đối với nhiều resource type như EC2, Auto Scaling, EBS và Lambda, Compute Optimizer đánh giá điểm utilization lớn nhất trong mỗi khoảng 5 phút của lookback period. Với ECS services trên Fargate, dịch vụ dùng điểm utilization lớn nhất trong mỗi khoảng 1 phút. Điều này giúp mô hình lưu ý các đỉnh tải ngắn, nhưng người vận hành vẫn cần kiểm tra percentile và metric gốc trong CloudWatch.

### Điều kiện dữ liệu ví dụ

| Resource | Điều kiện tiêu biểu để có recommendation |
|---|---|
| EC2 và Auto Scaling group | Ít nhất 30 giờ CloudWatch metric data trong 14 ngày gần nhất; Enhanced Infrastructure Metrics mở rộng lookback tới 93 ngày cho resource đủ điều kiện |
| EBS volume | Volume phải được gắn vào EC2 đang chạy ít nhất 30 giờ liên tục; dữ liệu CloudWatch chỉ có khi volume được attach vào instance đang chạy |
| Lambda | Với recommendation memory, function cần ít nhất 50 invocation trong 14 ngày và memory cấu hình không vượt 1.792 MB; Lambda không cần CloudWatch metric data như EC2 |
| ECS service trên Fargate | Cần ít nhất 24 giờ CloudWatch/ECS utilization metrics trong 14 ngày; step scaling hoặc target tracking đồng thời CPU và memory có thể làm recommendation bị giới hạn |
| RDS/Aurora | DB instance cần ít nhất 30 giờ CloudWatch metrics trong 14 ngày; một số recommendation yêu cầu Performance Insights hoặc điều kiện riêng của Aurora cluster |

Các con số và điều kiện cụ thể có thể khác nhau theo resource type. Khi recommendation không xuất hiện, kiểm tra resource requirements, metric coverage, loại instance, Region và trạng thái enrollment trước khi kết luận tài nguyên không có cơ hội tối ưu.

Với ECS Fargate, nếu service có target tracking chỉ trên CPU, Compute Optimizer có thể chỉ đề xuất memory; nếu chỉ trên memory, có thể chỉ đề xuất CPU. Nếu có scaling policy trên cả hai chiều hoặc step scaling, rightsizing recommendation có thể không được tạo. Với Aurora DB cluster storage, còn có điều kiện riêng như dữ liệu chi phí đủ dài và không có một số cấu hình cluster nhất định.

### Historical data không phải forecast

Lookback 14 ngày có thể không đại diện cho chu kỳ tháng, quý hoặc mùa vụ. Một hệ thống xử lý hóa đơn chỉ tải nặng vào cuối tháng có thể bị đánh giá thiếu capacity nếu giai đoạn phân tích không chứa kỳ cao điểm. Với workload biến động, hãy dùng lookback dài hơn khi phù hợp và đối chiếu lịch nghiệp vụ.

## 6. Hiểu finding, recommendation và performance risk

Compute Optimizer có thể hiển thị finding classification như:

- **Over-provisioned:** tài nguyên được cấp vượt nhu cầu quan sát được; có thể giảm cấu hình và tiết kiệm chi phí.
- **Under-provisioned:** tài nguyên có nguy cơ không đáp ứng nhu cầu; cần xem xét tăng hoặc đổi cấu hình để cải thiện hiệu năng.
- **Optimized:** cấu hình hiện tại được đánh giá phù hợp với yêu cầu và dữ liệu quan sát.
- **Not optimized / Unavailable:** một số resource type hoặc trường hợp có thể dùng trạng thái riêng khi chưa đủ dữ liệu hoặc chưa có recommendation đáng tin cậy.

Tên và trạng thái cụ thể phụ thuộc resource type. Không áp một bộ classification duy nhất cho EC2, Lambda, ECS, EBS và RDS.

### Performance risk

Performance risk biểu thị khả năng cấu hình được đề xuất không đáp ứng đủ nhu cầu workload theo mô hình đánh giá. Tùy trang và resource type, mức rủi ro có thể được thể hiện từ Very low tới High.

Không chọn recommendation chỉ vì savings cao nhất. Hãy so sánh:

| Tiêu chí | Câu hỏi |
|---|---|
| Estimated monthly savings | Ước tính tiết kiệm bao nhiêu và dựa trên giá nào? |
| Performance risk | Cấu hình mới có thể thiếu CPU, memory, IOPS hoặc throughput không? |
| Utilization graph | Recommendation có đủ headroom ở các thời điểm peak không? |
| Compatibility | Ứng dụng có tương thích CPU architecture, OS, driver, license và storage không? |
| Operational impact | Thay đổi cần restart, redeploy, failover hoặc downtime không? |
| Future demand | Tải sắp tới có khác giai đoạn lookback không? |

## 7. Tối ưu EC2 instance

Compute Optimizer phân tích cấu hình và utilization của EC2 để đề xuất instance type phù hợp hơn. Tùy loại workload và metric có sẵn, các chiều dữ liệu có thể gồm CPU, memory, network, EBS throughput, GPU và các metric hiệu năng liên quan.

### CPU không phải metric duy nhất

Một instance có CPU trung bình thấp vẫn có thể cần giữ nguyên hoặc tăng cấu hình nếu:

- Memory utilization cao hoặc thường xuyên swap.
- Network throughput gần giới hạn.
- EBS throughput hoặc IOPS bị nghẽn.
- GPU utilization hoặc GPU memory cao.
- Ứng dụng cần burst CPU trong khoảng thời gian ngắn.
- Workload có yêu cầu latency hoặc tail latency nghiêm ngặt.

Compute Optimizer không tự có đầy đủ memory metric của mọi EC2 instance. Để phân tích memory, cần cài và cấu hình CloudWatch Agent để gửi metric phù hợp. Trên Linux, các metric như mem_used_percent trong namespace CWAgent có thể được dùng; trên Windows, cần cấu hình metric memory phù hợp như Available MBytes. Kiểm tra tài liệu theo hệ điều hành và agent version.

Ví dụ, trên Linux có thể thu thập mem_used_percent trong namespace CWAgent hoặc metric MemoryUtilization cũ trong namespace System/Linux. Trên Windows, Compute Optimizer có thể dùng Available MBytes trong CWAgent; hãy chọn cấu hình agent phù hợp với cách hệ điều hành báo cáo memory.

### Chọn instance family

Không chỉ so sánh số vCPU và RAM. Các family khác nhau về:

- CPU architecture và instruction set.
- Network bandwidth và packet performance.
- EBS bandwidth.
- Local NVMe/instance store.
- GPU, accelerator và memory bandwidth.
- License và phần mềm phụ thuộc kiến trúc.

Compute Optimizer không tạo EC2 rightsizing recommendation cho Spot Instances và chỉ hỗ trợ các instance type nằm trong danh sách được công bố. Nếu không thấy recommendation cho một instance, hãy kiểm tra loại instance và điều kiện hỗ trợ trước khi điều tra metric.

Nếu Compute Optimizer đề xuất Graviton, cần kiểm tra binary, container image, runtime, native dependency và quy trình build multi-architecture. Với workload Windows hoặc phần mềm thương mại, kiểm tra license và khả năng hỗ trợ trước khi chuyển family.

### Burstable instances

Với T family, CPU credit và baseline performance có thể ảnh hưởng hiệu năng. Một cấu hình có CPU trung bình thấp nhưng thường xuyên burst có thể gặp thiếu credit sau khi downsizing. Kiểm tra CPUCreditBalance, CPUCreditUsage, chế độ Unlimited và chi phí surplus credit trước khi thay đổi.

### Đánh giá peak và headroom

Xem biểu đồ maximum và percentile, không chỉ average. Một hệ thống có CPU trung bình 15% nhưng peak 95% trong các đợt batch có thể cần giữ capacity hoặc điều chỉnh lịch batch. Recommendation cần đáp ứng peak được nghiệp vụ chấp nhận, không chỉ mức tải trung bình.

## 8. Tối ưu EC2 Auto Scaling groups

Với Auto Scaling group, Compute Optimizer có thể đề xuất instance type và một số cơ hội idle dựa trên cách group được cấu hình. Recommendation có thể phụ thuộc group dùng một instance type, mixed instances, scaling policy theo CPU hoặc scheduled scaling.

Điểm cần hiểu:

- Recommendation về instance type không đồng nghĩa dịch vụ tự sửa min/max/desired capacity hoặc scaling policy.
- Mixed instance policy có ràng buộc về family, architecture, platform và allocation strategy.
- Một số tổ hợp Spot, instance family hoặc workload có thể không đủ điều kiện cho rightsizing recommendation.
- Group chạy ECS/EKS có thể có giới hạn khác với group EC2 thông thường.

Khi áp dụng thay đổi instance type, có thể dùng EC2 Auto Scaling instance refresh theo chiến lược rolling phù hợp. Chọn min healthy percentage, warm-up, health check và checkpoint; giữ khả năng rollback bằng cách bảo toàn cấu hình trước đó.

## 9. Tối ưu EBS volume

Compute Optimizer có thể đề xuất thay đổi volume type, size, IOPS hoặc throughput cho các loại EBS được hỗ trợ. Ví dụ, volume gp2 có thể được cân nhắc chuyển sang gp3; volume io1/io2 có thể cần điều chỉnh IOPS; volume có throughput thấp có thể cần cấu hình khác.

Các metric cần xem:

- Read/write operations và IOPS.
- Read/write throughput.
- Burst balance đối với loại volume có burst bucket.
- IOPS exceeded check và throughput exceeded check khi metric hỗ trợ.
- Attachment status và thời gian sử dụng.

### Ví dụ lựa chọn gp2 và gp3

gp2 liên kết IOPS với dung lượng và có cơ chế burst. gp3 tách dung lượng khỏi IOPS/throughput provisioned, cho phép cấu hình độc lập trong giới hạn dịch vụ. Việc chuyển gp2 sang gp3 có thể giảm chi phí hoặc cải thiện khả năng điều chỉnh, nhưng phải kiểm tra workload có cần IOPS/throughput cao hơn mức mặc định hay không.

Không giảm volume size chỉ vì phần lớn dung lượng chưa dùng. Cần kiểm tra growth rate, log retention, temporary files, backup staging, database expansion và khả năng mở rộng sau này.

### Volume idle hoặc unattached

Volume không gắn vào instance hoặc có hoạt động rất thấp có thể tạo idle recommendation. Trước khi xóa:

1. Xác định owner, tag và workload cũ.
2. Kiểm tra attachment history và thời gian không sử dụng.
3. Xác nhận dữ liệu không phải bản phục hồi, forensic evidence hoặc volume dự phòng.
4. Tạo snapshot nếu chính sách yêu cầu.
5. Xác nhận snapshot hoàn tất và key giải mã còn khả dụng.
6. Xóa volume qua change process và theo dõi chi phí snapshot.

Không xóa volume chỉ dựa trên finding idle. Một volume có thể được giữ cho DR, audit hoặc quy trình khôi phục định kỳ.

## 10. Tối ưu AWS Lambda

Compute Optimizer tạo memory size recommendation cho Lambda functions đủ điều kiện. Trong Lambda, memory setting có ảnh hưởng tới CPU power và một số tài nguyên thực thi khác. Tăng memory có thể làm function chạy nhanh hơn; dù giá mỗi millisecond cao hơn, tổng duration giảm đủ nhiều có thể khiến chi phí thực tế giảm hoặc tương đương.

Đánh giá:

- Memory configured hiện tại.
- Duration p50/p95/p99.
- Error và timeout rate.
- Invocation count và concurrency.
- Cold start và kích thước package.
- Chi phí theo số invocation và GB-second.

Recommendation memory không có nghĩa mọi function nên chọn mức thấp nhất. Function xử lý ảnh, mã hóa hoặc tính toán có thể cần CPU và memory cao; function chờ network có thể không cải thiện nhiều khi tăng memory.

Theo điều kiện hiện hành của Compute Optimizer, function có memory cấu hình lớn hơn 1.792 MB có thể nhận finding Unavailable/Inconclusive và không xuất hiện trong danh sách recommendation. Vì vậy, không thấy recommendation không có nghĩa function đã được tối ưu.

Sau khi thay đổi memory, chạy test với dữ liệu và concurrency gần thực tế. Theo dõi duration, error, throttling và cost per successful invocation. Với function nhạy cảm, triển khai qua version/alias và traffic shifting để rollback nếu latency hoặc lỗi tăng.

## 11. Tối ưu ECS services trên Fargate

Compute Optimizer có thể đưa ra recommendation cho task size và container size của ECS service trên Fargate. Các metric chính gồm CPU utilization và memory utilization.

Finding có thể cho biết CPU hoặc memory over-provisioned/under-provisioned. Recommendation task-level và container-level cần tương thích: tổng resource reservation của container phải phù hợp với task size.

Một số scaling policy có thể giới hạn loại recommendation. Ví dụ, khi service gắn target tracking cho cả CPU và memory hoặc step scaling, phạm vi khuyến nghị có thể bị hạn chế. Đọc phần requirement của ECS service trước khi kết luận rằng dịch vụ không đưa ra recommendation.

Khi thay đổi:

1. So sánh task CPU/memory hiện tại và đề xuất.
2. Kiểm tra container CPU shares, memory reservation và memory limit.
3. Xem peak utilization và số task tối thiểu.
4. Kiểm tra service autoscaling, deployment configuration và health check.
5. Triển khai task definition mới theo rolling deployment.
6. Theo dõi task restart, OOM, latency và desired/running count.

Không giảm task memory tới sát mức sử dụng trung bình. Một đợt tải ngắn hoặc memory spike có thể gây OOM và làm task liên tục restart.

## 12. Tối ưu Amazon RDS và Aurora

Compute Optimizer hỗ trợ một số loại Amazon RDS và Aurora, gồm recommendation cho DB instance, RDS DB instance storage và Aurora DB cluster storage theo engine/điều kiện được hỗ trợ.

Metric có thể được phân tích gồm:

- CPU utilization.
- Database connections.
- Network receive throughput.
- Read/write IOPS và throughput.
- Free storage space.
- Database load và một số OS metrics khi bật Performance Insights hoặc tính năng quan sát tương ứng.
- I/O usage và chi phí storage của Aurora cluster.

Với một số RDS DB instance, Performance Insights cần được bật để Compute Optimizer tạo recommendation giảm vCPU. Điều kiện và tên tính năng quan sát database có thể thay đổi theo engine và phiên bản dịch vụ; kiểm tra tài liệu RDS/Aurora hiện hành.

### Không chỉ nhìn CPU

Database có CPU thấp nhưng DB load cao có thể bị chặn bởi lock, I/O, connection hoặc query plan. Giảm instance size có thể làm tình hình tệ hơn. Trước khi đổi DB instance class:

1. Xem Database Insights/Performance Insights, DB load và wait events.
2. Kiểm tra connection pool, query latency và slow query.
3. Kiểm tra memory, cache hit, IOPS, throughput và free storage.
4. Xác định read replica, Multi-AZ và failover behavior.
5. Kiểm tra engine/version và khả năng hỗ trợ instance class.
6. Lập kế hoạch maintenance, snapshot và rollback.

Với Aurora, phân biệt instance compute với cluster storage. Recommendation storage có thể liên quan I/O và chi phí cluster; thay đổi instance class và tối ưu storage là hai quyết định khác nhau.

## 13. Recommendation preferences và headroom

Compute Optimizer cho phép tùy chỉnh một số recommendation preferences, ví dụ:

- CPU utilization headroom và threshold.
- Memory utilization headroom.
- Lookback period.
- Instance family preference.
- Một số lựa chọn kiến trúc CPU hoặc phạm vi recommendation theo tổ chức/account/Region.

Headroom thể hiện khoảng dự phòng mà tổ chức muốn giữ. Nếu workload có latency nghiêm ngặt hoặc burst lớn, cần headroom cao hơn. Nếu workload batch có thể trì hoãn và dễ scale, có thể chấp nhận mức utilization cao hơn.

Không nên cấu hình headroom quá thấp chỉ để tăng savings. Cần căn cứ SLO, peak, scale-out time, cold start, quota và tốc độ tăng tải. Recommendation preference thay đổi cách mô hình đánh giá; nó không thay thế việc kiểm tra thực tế.

## 14. Savings estimate và mối liên hệ với FinOps

Compute Optimizer hiển thị estimated monthly savings và price comparison cho nhiều recommendation. Con số này là ước tính dựa trên giả định sử dụng, giá và dữ liệu billing sẵn có; không phải cam kết tiết kiệm.

Để hiểu savings estimate:

1. Kiểm tra account/Region và purchasing option được dùng.
2. Xác nhận Cost Explorer đã bật và billing data có sẵn.
3. Kiểm tra Savings Plans hoặc Reserved Instances đang áp dụng.
4. Xem Cost Optimization Hub nếu cần so sánh recommendation trong bối cảnh discounts/commitments.
5. Tính chi phí thay đổi, migration, downtime, testing và license.
6. Đo actual cost sau khi thay đổi.

### On-Demand và discount

Một recommendation có thể cho thấy savings theo On-Demand nhưng savings thực tế thấp hơn nếu resource đang được bao phủ bởi Savings Plan hoặc Reserved Instance. Ngược lại, rightsizing có thể giải phóng commitment để dùng cho workload khác. Không kết luận chỉ từ hourly price của hai instance type.

Một số chế độ ước tính có thể tính discount riêng của account khi được bật; nếu không, savings estimate có thể dựa trên On-Demand pricing hoặc purchasing option đang chọn. Khi lập business case, đối chiếu với Cost Explorer, Cost Optimization Hub và hóa đơn thực tế của workload.

### Cost Optimization Hub

Cost Optimization Hub tổng hợp các cơ hội tối ưu từ nhiều nguồn, bao gồm rightsizing, idle resources, Savings Plans và Reserved Instances. Compute Optimizer tập trung phân tích cấu hình và utilization của resource; Cost Optimization Hub giúp nhìn các cơ hội trong bức tranh chi phí rộng hơn. Hai công cụ bổ trợ nhau.

## 15. Quy trình đánh giá và triển khai recommendation

Một quy trình FinOps có kiểm soát có thể gồm bảy bước:

1. **Discover:** xuất recommendation theo account, Region, resource type, tag và owner.
2. **Validate data:** kiểm tra lookback period, metric coverage, peak, seasonality và trạng thái resource.
3. **Assess business impact:** xác định criticality, SLO, maintenance window, DR tier và dependency.
4. **Prioritize:** xếp theo savings, performance risk, effort, blast radius và mức tự tin.
5. **Test:** thử ở development/staging hoặc canary, dùng load test và synthetic transaction.
6. **Implement:** thay đổi qua IaC, deployment pipeline hoặc change process có phê duyệt.
7. **Measure:** so sánh cost, latency, error, utilization và savings thực tế sau thay đổi.

### Ma trận ưu tiên ví dụ

| Cơ hội | Savings | Performance risk | Effort | Ưu tiên tham khảo |
|---|---|---|---|---|
| EC2 non-production quá lớn, metric ổn định | Cao | Thấp | Thấp | Cao |
| EBS volume unattached, owner xác nhận | Trung bình | Thấp sau snapshot | Thấp | Cao |
| Lambda memory hơi lớn, test được | Trung bình | Thấp nếu canary tốt | Thấp | Cao |
| RDS production có DB load cao, đề xuất giảm vCPU | Cao | Trung bình/cao | Cao | Cần điều tra sâu |
| ECS service có peak memory gần giới hạn | Thấp nếu giảm size | Cao | Trung bình | Không downsizing |

Không ưu tiên chỉ theo savings. Một thay đổi nhỏ nhưng có rủi ro cao với database production có thể cần trì hoãn; một thay đổi có savings vừa phải và dễ rollback ở môi trường dev có thể thực hiện trước.

## 16. Áp dụng recommendation bằng Automation

AWS Compute Optimizer có tính năng Automation để áp dụng một số recommended actions trực tiếp hoặc theo automation rule định kỳ. Automation có thể giới hạn phạm vi theo Region, resource tag, loại action và lịch daily/weekly/monthly; có thể theo dõi automation event, từng bước thực thi, savings estimate và rollback action được hỗ trợ.

Phạm vi action tự động hiện được tài liệu hóa gồm một số thao tác EBS, ví dụ:

- Tạo snapshot rồi xóa EBS volume unattached đủ điều kiện.
- Nâng cấp một số volume type cũ sang loại mới được hỗ trợ.

Không giả định mọi recommendation về EC2 instance type, Lambda memory, ECS task size hoặc RDS instance class đều có thể được Compute Optimizer Automation tự động áp dụng. Kiểm tra danh sách recommended action type hiện hành ở Region/account.

### Guardrail trước khi bật Automation

- Chỉ bật sau khi owner hiểu quyền service-linked role và phạm vi tài nguyên mà dịch vụ có thể thay đổi.
- Tạo rule theo tag, Region, lookback period và loại action cụ thể.
- Dùng tag opt-out để loại tài nguyên nhạy cảm khỏi phạm vi tự động.
- Loại trừ tài nguyên do IaC quản lý nếu thay đổi tự động có thể gây drift, hoặc chuẩn bị quy trình cập nhật source of truth.
- Preview các action khớp rule trước khi kích hoạt.
- Bắt đầu với account/Region thử nghiệm và lịch ngoài giờ cao điểm.
- Theo dõi event status, step history, savings và ảnh hưởng tới workload.
- Xác nhận khả năng rollback của từng action; không giả định mọi hành động đều có rollback một nút.

Automation giúp giảm thao tác lặp lại nhưng cũng có thể tạo thay đổi diện rộng. Quy tắc không có criteria đủ hẹp có thể áp dụng action ở nhiều Region và resource ngoài dự kiến. Cần quản trị rule như một thay đổi production.

## 17. Truy vấn recommendation bằng AWS CLI

Sau khi opt in, có thể dùng AWS CLI để đọc recommendation. Ví dụ bật enrollment cho account/Region đang dùng:

~~~bash
aws compute-optimizer update-enrollment-status \
  --status Active \
  --region ap-southeast-1
~~~

Lấy recommendation cho một EC2 instance:

~~~bash
aws compute-optimizer get-ec2-instance-recommendations \
  --instance-arns "arn:aws:ec2:ap-southeast-1:111122223333:instance/i-0123456789abcdef0" \
  --region ap-southeast-1
~~~

Lấy recommendation cho một EBS volume:

~~~bash
aws compute-optimizer get-ebs-volume-recommendations \
  --volume-arns "arn:aws:ec2:ap-southeast-1:111122223333:volume/vol-0123456789abcdef0" \
  --region ap-southeast-1
~~~

Các ARN trong ví dụ là dữ liệu minh họa. Caller cần IAM permission phù hợp và phải truy vấn đúng Region. API có thể trả nhiều trường và recommendation options; nên dùng query/output để trích xuất các thuộc tính cần thiết thay vì in dữ liệu lớn vào log.

Có thể dùng các API tương ứng để lấy recommendation cho Lambda, ECS, Auto Scaling và RDS. Khi triển khai báo cáo, xử lý pagination và lỗi resource không đủ điều kiện; không xem response rỗng là bằng chứng rằng resource đã tối ưu.

## 18. Ví dụ thực tế: right-sizing nền tảng Orders

Một nền tảng thương mại điện tử chạy API trên EC2 Auto Scaling group, worker trên ECS Fargate, ảnh hóa đơn trên EBS-backed EC2, database trên RDS và tác vụ xử lý ảnh bằng Lambda. Nhóm FinOps muốn giảm chi phí nhưng không làm ảnh hưởng peak sale.

### Phân tích

1. EC2 API có CPU trung bình thấp nhưng peak tăng mạnh vào giờ flash sale. Nhóm bật memory metrics bằng CloudWatch Agent và chọn lookback dài hơn để quan sát nhiều chu kỳ.
2. Auto Scaling group có mixed instance policy. Nhóm kiểm tra architecture, platform và allocation strategy trước khi áp dụng instance family recommendation.
3. ECS worker có memory utilization thấp nhưng queue backlog tăng theo đợt. Nhóm xem queue age và concurrency để xác định task size có thể giảm hay cần giữ headroom.
4. RDS CPU thấp nhưng DB load và connections cao. Nhóm điều tra wait events và query trước khi giảm DB class.
5. Lambda xử lý ảnh có memory 1.024 MB, duration dài. Nhóm thử memory cao hơn trên alias canary để xem duration và cost per image.
6. Một EBS volume không còn attachment được owner xác nhận là không cần. Nhóm tạo snapshot theo chính sách rồi mới xóa.

### Kế hoạch thay đổi

| Resource | Quyết định | Guardrail |
|---|---|---|
| EC2 API | Thử instance type mới ở một phần ASG | Instance refresh, health check, peak test, rollback |
| ECS worker | Thay task size theo từng service | Theo dõi OOM, queue age, task restart |
| RDS | Chưa downsizing; điều tra DB load | Query analysis, snapshot, maintenance window |
| Lambda | Canary memory configuration | So sánh duration, error và cost per image |
| EBS unattached | Snapshot rồi xóa sau phê duyệt | Kiểm tra owner, retention và KMS |

Sau mỗi thay đổi, nhóm so sánh actual cost và hiệu năng trong cùng điều kiện tải. Nếu chỉ so sánh chi phí của một tuần bình thường với tuần có flash sale, kết luận savings có thể sai lệch.

## 19. Governance và đo lường FinOps

Để right-sizing trở thành hoạt động liên tục, tổ chức cần ownership và chỉ số theo dõi.

### Ownership

- FinOps team quản lý quy trình, báo cáo và ưu tiên.
- Platform team quản lý guardrail, IaC, deployment và automation.
- Application owner xác nhận tải, SLO và khả năng chấp nhận thay đổi.
- Database owner đánh giá query, storage và failover.
- Security team kiểm tra IAM, automation role, audit và tag.

### Metric nên theo dõi

| Metric | Ý nghĩa |
|---|---|
| Recommendation coverage | Tỷ lệ resource nằm trong phạm vi phân tích |
| Actionable recommendation rate | Tỷ lệ recommendation có đủ dữ liệu và owner |
| Estimated savings | Tổng tiết kiệm ước tính trước thay đổi |
| Realized savings | Tiết kiệm thực tế sau khi chuẩn hóa theo usage/discount |
| Adoption rate | Tỷ lệ recommendation đã được xử lý |
| Reversal / rollback rate | Tỷ lệ thay đổi phải hoàn tác |
| Performance regression | Thay đổi gây tăng latency, error hoặc giảm throughput |
| Idle resource backlog | Tài nguyên idle chưa được xử lý |
| Time to action | Thời gian từ recommendation tới quyết định và triển khai |

Không thưởng đội nhóm chỉ theo estimated savings. Nếu downsizing làm tăng lỗi hoặc downtime, tổng chi phí kinh doanh có thể lớn hơn số tiền tiết kiệm hạ tầng. Đánh giá cost per successful transaction, cost per customer hoặc cost per workload unit sẽ phản ánh giá trị tốt hơn.

## 20. Sai lầm thường gặp

### Chỉ nhìn CPU average

Memory, network, EBS, GPU, IOPS và peak có thể là bottleneck. Thu thập đủ metric và xem percentile.

### Dùng lookback quá ngắn cho workload mùa vụ

Recommendation có thể bỏ qua batch cuối tháng hoặc peak sale. Dùng lookback phù hợp và bổ sung lịch nghiệp vụ.

### Coi savings estimate là số tiền chắc chắn tiết kiệm

Giá On-Demand, Savings Plans, Reserved Instances, credits và discount có thể làm kết quả khác. Đo actual billing sau thay đổi.

### Downsizing database chỉ vì CPU thấp

DB load, memory, connection, I/O và wait event có thể đang giới hạn. Điều tra database trước khi thay đổi class.

### Bỏ qua CPU architecture

Chuyển x86 sang Graviton cần kiểm tra binary, runtime, container image và license.

### Thay đổi nhiều resource cùng lúc

Khó xác định nguyên nhân nếu latency hoặc error tăng. Dùng canary và rollout theo đợt.

### Tự động áp dụng recommendation trên toàn tổ chức

Automation rule rộng có thể thay đổi resource ngoài dự kiến hoặc tạo IaC drift. Dùng criteria, preview, opt-out tag và account thử nghiệm.

### Xóa volume idle mà không xác minh owner

Volume có thể chứa backup, forensic evidence hoặc dữ liệu DR. Xác minh và snapshot theo policy.

### Không đo kết quả sau thay đổi

Không thể chứng minh FinOps nếu chỉ đánh dấu recommendation đã xử lý. So sánh chi phí, hiệu năng và reliability trước/sau.

## 21. Checklist triển khai Compute Optimizer

- [ ] Compute Optimizer đã opt in ở account và Region cần phân tích.
- [ ] AWS Organizations và delegated administrator được cấu hình nếu quản lý nhiều account.
- [ ] Cost Explorer đã bật để hỗ trợ thông tin giá và savings estimate.
- [ ] Resource có đủ metric data và đúng điều kiện hỗ trợ.
- [ ] Lookback period phù hợp với seasonality và chu kỳ tải.
- [ ] EC2 có memory metric nếu workload cần đánh giá memory.
- [ ] Finding classification, performance risk và recommendation options đã được xem xét.
- [ ] Có owner, tag, criticality và SLO cho resource.
- [ ] Đã kiểm tra CPU architecture, license, network, EBS và dependency.
- [ ] Đã tính Savings Plans, Reserved Instances và discount thực tế.
- [ ] Thay đổi được thử nghiệm qua canary hoặc môi trường staging.
- [ ] Có backup/snapshot và rollback plan phù hợp.
- [ ] Automation chỉ áp dụng action được hỗ trợ với criteria hẹp.
- [ ] IaC source of truth được cập nhật để tránh drift.
- [ ] CloudWatch alarms theo dõi latency, error, utilization và saturation sau thay đổi.
- [ ] Actual savings và cost per business unit được đo sau triển khai.

## 22. Ghi nhớ

AWS Compute Optimizer phân tích cấu hình và utilization metrics để đưa ra recommendation về rightsizing và idle resources cho các resource type được hỗ trợ. Chất lượng recommendation phụ thuộc vào metric coverage, lookback period, điều kiện resource và bối cảnh workload.

Right-sizing phải cân bằng savings với performance risk. Hãy xem CPU, memory, network, IOPS, throughput, queue, database load và peak; kiểm tra tương thích kiến trúc, license và dependency; rồi triển khai từng bước có canary, monitoring và rollback. Estimated savings cần được đối chiếu với purchasing option, Savings Plans, Reserved Instances và billing thực tế.

Compute Optimizer Automation có thể áp dụng một số recommended actions được hỗ trợ, nhưng cần rule hẹp, quyền tối thiểu, preview và giám sát. FinOps chỉ tạo ra giá trị bền vững khi tiết kiệm được chi phí mà vẫn duy trì SLO, reliability và trải nghiệm người dùng.

## Tài liệu tham khảo

- [What is AWS Compute Optimizer?](https://docs.aws.amazon.com/compute-optimizer/latest/ug/what-is-compute-optimizer.html)
- [AWS Resources Supported by Compute Optimizer](https://docs.aws.amazon.com/compute-optimizer/latest/ug/supported-resources.html)
- [Resource Requirements](https://docs.aws.amazon.com/compute-optimizer/latest/ug/requirements.html)
- [Metrics Analyzed by AWS Compute Optimizer](https://docs.aws.amazon.com/compute-optimizer/latest/ug/metrics.html)
- [Viewing EC2 Instance Recommendations](https://docs.aws.amazon.com/compute-optimizer/latest/ug/view-ec2-recommendations.html)
- [EC2 Instance Metrics Analyzed](https://docs.aws.amazon.com/compute-optimizer/latest/ug/ec2-metrics-analyzed.html)
- [Viewing EBS Volume Recommendations](https://docs.aws.amazon.com/compute-optimizer/latest/ug/view-ebs-recommendations.html)
- [Viewing Lambda Function Recommendations](https://docs.aws.amazon.com/compute-optimizer/latest/ug/view-lambda-recommendations.html)
- [Viewing ECS Services on Fargate Recommendations](https://docs.aws.amazon.com/compute-optimizer/latest/ug/view-ecs-recommendations.html)
- [Viewing Aurora and RDS Database Recommendations](https://docs.aws.amazon.com/compute-optimizer/latest/ug/view-rds-recommendations.html)
- [Rightsizing Recommendation Preferences](https://docs.aws.amazon.com/compute-optimizer/latest/ug/rightsizing-preferences.html)
- [Apply Optimization Recommendations Using Automation](https://docs.aws.amazon.com/compute-optimizer/latest/ug/automation.html)
- [Automation Rules](https://docs.aws.amazon.com/compute-optimizer/latest/ug/automation-rules.html)
- [Cost Optimization Hub](https://docs.aws.amazon.com/cost-management/latest/userguide/cost-optimization-hub.html)
- [AWS Compute Optimizer Pricing](https://aws.amazon.com/compute-optimizer/pricing/)
