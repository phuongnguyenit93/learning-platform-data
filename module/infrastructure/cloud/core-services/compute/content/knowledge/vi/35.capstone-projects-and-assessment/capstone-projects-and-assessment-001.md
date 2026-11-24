# Xây dựng dịch vụ web nhiều zone với quy trình triển khai tự động

Trong dự án tổng hợp này, bạn sẽ thiết kế và triển khai một dịch vụ web có khả năng tiếp tục phục vụ khi một zone gặp sự cố, đồng thời tự động kiểm thử và phát hành phiên bản mới qua pipeline CI/CD. Dự án kết hợp năng lực compute, mạng, lưu trữ, danh tính, bảo mật, giám sát và tự động hóa thành một hệ thống có thể vận hành.

Ta dùng AWS làm ví dụ triển khai cụ thể: Application Load Balancer (ALB) tiếp nhận HTTPS ở nhiều Availability Zone (AZ), Amazon ECS chạy container trên AWS Fargate trong các subnet riêng, Amazon RDS for PostgreSQL triển khai Multi-AZ, Amazon ECR lưu image và GitHub Actions phát hành qua OIDC. Các khái niệm kiến trúc có thể áp dụng trên cloud khác bằng dịch vụ tương ứng.

Mục tiêu không chỉ là tạo được nhiều bản sao ứng dụng. Bạn cần chứng minh traffic được phân phối qua nhiều zone, ứng dụng phục hồi khi một task hoặc zone không khả dụng, phiên bản mới được phát hành có kiểm soát, dữ liệu không mất khi thay task và có đủ metric để phát hiện lỗi.

Sau dự án, bạn có thể:

- Thiết kế web tier nhiều zone với load balancer và compute không lưu trạng thái cục bộ.
- Tách subnet public, application và database; cấu hình security group theo luồng truy cập tối thiểu.
- Triển khai container service có health check, autoscaling và cơ chế rollback.
- Xây dựng pipeline kiểm thử, build, scan, publish image và triển khai tự động.
- Quản lý schema database, secret, log, metric, backup và quy trình khôi phục.
- Kiểm chứng tính sẵn sàng bằng thử nghiệm lỗi có kiểm soát và ghi lại kết quả.

## 1. Đề bài và tiêu chí nghiệm thu

Bạn được giao xây dựng dịch vụ web nội bộ có API và trang kiểm tra trạng thái. Ứng dụng nhận yêu cầu HTTPS, đọc/ghi dữ liệu đơn hàng mẫu và cung cấp endpoint health check. Người dùng không được truy cập trực tiếp task hoặc database.

Các yêu cầu chức năng:

- Trang chủ hoặc endpoint API trả về phiên bản ứng dụng và mã định danh instance/task để quan sát phân phối request.
- Endpoint readiness chỉ trả thành công khi ứng dụng sẵn sàng nhận traffic.
- Endpoint liveness cho biết tiến trình còn hoạt động.
- API có thể đọc và ghi một bản ghi thử nghiệm trong PostgreSQL.
- Ứng dụng không lưu session hoặc dữ liệu upload quan trọng trên filesystem tạm của container.

Các yêu cầu vận hành:

| Hạng mục | Mục tiêu nghiệm thu |
|---|---|
| Phân vùng lỗi | ALB và application tasks chạy trong ít nhất hai AZ |
| Số bản sao | Có tối thiểu hai task khỏe mạnh ở trạng thái bình thường |
| Phục hồi | Khi một task bị dừng, ECS tạo task thay thế và ALB chỉ gửi traffic đến target khỏe |
| Khả năng chịu lỗi zone | Khi một AZ không khả dụng trong bài thử nghiệm, dịch vụ tiếp tục phục vụ từ AZ còn lại trong giới hạn capacity đã thiết kế |
| Database | Database nằm trong private subnets, có Multi-AZ failover và backup phù hợp |
| Triển khai | Commit vào nhánh phát hành chạy kiểm thử, build image và triển khai tự động |
| Rollback | Deployment lỗi có thể tự rollback hoặc khôi phục revision trước theo runbook |
| Bảo mật | Không có secret trong source code hoặc image; task chỉ có quyền tối thiểu |
| Quan sát | Có log, metric, cảnh báo và lịch sử triển khai |

Trước khi triển khai, hãy xác định mục tiêu dịch vụ với chủ sở hữu ứng dụng: availability target, RTO (thời gian khôi phục), RPO (mức mất dữ liệu cho phép), throughput, latency và ngân sách. Ví dụ trong bài dùng mục tiêu minh họa; production cần được phê duyệt theo yêu cầu thực tế.

## 2. Kiến trúc tham chiếu

~~~mermaid
flowchart LR
  U[Người dùng] --> DNS[Route 53 + ACM]
  DNS --> ALB[ALB - public subnets<br/>AZ-a / AZ-b]
  ALB --> ECS[ECS Fargate - private app subnets<br/>2+ tasks]
  ECS --> DB[RDS PostgreSQL<br/>private DB subnets - Multi-AZ]
  CI[GitHub Actions - OIDC] --> ECR[ECR image registry]
  ECR --> ECS
  ECS --> SM[Secrets Manager]
  ECS --> CW[CloudWatch logs / metrics / alarms]
~~~

Luồng request:

1. Người dùng truy cập hostname dịch vụ. DNS trỏ đến ALB và chứng chỉ TLS được quản lý bởi AWS Certificate Manager (ACM).
2. ALB nhận HTTPS trên listener 443, kiểm tra target health và chuyển request đến ECS task khỏe mạnh qua target group loại IP.
3. ECS service chạy container Fargate trong private subnets thuộc ít nhất hai AZ.
4. Ứng dụng truy cập PostgreSQL qua private network. Database chỉ nhận kết nối từ security group của application.
5. ECS execution role cho phép ECS agent lấy secret được khai báo trong task definition; nếu chính ứng dụng gọi Secrets Manager bằng SDK thì cấp quyền đọc secret tối thiểu cho task role. Log được gửi về CloudWatch Logs.
6. GitHub Actions xác thực với AWS bằng OIDC, đẩy image vào ECR và yêu cầu ECS triển khai task definition revision mới.

Các thành phần dữ liệu và vận hành:

- RDS Multi-AZ giữ bản sao standby đồng bộ để hỗ trợ failover. Standby của Multi-AZ DB instance không phải read replica để mở rộng truy vấn đọc.
- S3 có thể dùng để lưu file upload hoặc artifact bền vững; không dùng writable layer của container làm nơi lưu dữ liệu lâu dài.
- CloudWatch lưu log/metric; CloudTrail ghi lại hoạt động API quản trị.
- AWS WAF có thể được gắn với ALB nếu ứng dụng cần lọc request ở lớp web.
- NAT Gateway hoặc VPC endpoints cung cấp đường đi từ private subnet đến ECR, CloudWatch, Secrets Manager và các dịch vụ AWS cần thiết. Chọn phương án theo yêu cầu mạng và chi phí.

### Bố trí subnet và security group

| Lớp | AZ-a | AZ-b | Quy tắc truy cập chính |
|---|---|---|---|
| Public | Public subnet A: ALB node, NAT nếu chọn | Public subnet B: ALB node, NAT nếu chọn | Internet vào ALB trên 443; 80 chỉ redirect sang 443 |
| Application | Private app subnet A: ECS tasks | Private app subnet B: ECS tasks | Chỉ nhận cổng ứng dụng từ ALB security group |
| Database | Private DB subnet A | Private DB subnet B | Chỉ nhận cổng PostgreSQL từ application security group |

Tạo DB subnet group gồm subnet ở nhiều AZ. Dùng security group tham chiếu security group nguồn thay vì mở database cho toàn bộ CIDR VPC. Không gán public IP cho ECS task hoặc database.

Nếu dùng NAT Gateway, triển khai theo AZ giúp traffic private subnet có đường egress cục bộ và tránh phụ thuộc một NAT duy nhất; đổi lại có thêm chi phí theo giờ và dữ liệu. VPC endpoints cho ECR, S3, CloudWatch Logs và Secrets Manager có thể giảm phụ thuộc NAT, nhưng cần cấu hình endpoint policy, DNS và security group phù hợp.

## 3. Chuẩn bị ứng dụng web

Ứng dụng cần đáp ứng các đặc tính để chạy được nhiều bản sao:

- Stateless: session nằm ở token hoặc kho dùng chung như Redis nếu cần; không giữ trạng thái phiên trong RAM của một task.
- Externalized configuration: endpoint database, log level và feature flag lấy từ cấu hình môi trường.
- Secret separation: password database lấy từ Secrets Manager; không đóng gói secret vào image.
- Graceful shutdown: xử lý SIGTERM, ngừng nhận request mới và hoàn tất request đang chạy trong thời gian ECS cho phép.
- Health endpoints: readiness phản ánh khả năng nhận request; liveness phát hiện tiến trình bị treo.
- Safe database access: connection pool có giới hạn, timeout và retry có kiểm soát.

Ví dụ cấu trúc response để quan sát bản sao:

~~~json
{
  "status": "ok",
  "version": "1.8.0",
  "instance": "task-id-or-hostname"
}
~~~

Không trả thông tin nhạy cảm như hostname nội bộ, IP private, secret, connection string hoặc stack trace ra endpoint công khai. Nếu cần xác minh task đang phục vụ, dùng mã định danh rút gọn hoặc build revision.

### Health check

| Endpoint | Ý nghĩa | Điều kiện trả thành công |
|---|---|---|
| /health/live | Tiến trình còn hoạt động | Runtime và event loop không bị treo |
| /health/ready | Có thể nhận request mới | App đã tải cấu hình, kết nối dependency thiết yếu và sẵn sàng phục vụ |
| /version | Xác định build đang chạy | Trả version và build SHA không nhạy cảm |

Không nên để readiness kiểm tra quá nhiều dependency không thiết yếu. Nếu một dịch vụ analytics phụ trợ tạm lỗi, toàn bộ web tier không nhất thiết phải bị loại khỏi load balancer. Ngược lại, nếu database là dependency bắt buộc và app không thể phục vụ request ghi/đọc, readiness cần phản ánh tình trạng đó theo cách tránh tạo vòng lặp quá tải.

## 4. Hạ tầng dưới dạng mã (IaC)

Quản lý VPC, subnet, route, security group, ALB, ECS, ECR, IAM và RDS bằng Terraform hoặc công cụ IaC được tổ chức phê duyệt. Đưa cấu hình vào Git để review, tái tạo và theo dõi thay đổi.

Một cấu trúc repository có thể dùng:

~~~text
web-multizone/
  app/
    src/
    Dockerfile
    tests/
  infra/
    modules/
      network/
      alb/
      ecs-service/
      database/
    environments/
      staging/
      production/
  deploy/
    task-definition.json
    scripts/
      smoke-test.sh
      rollback.sh
  .github/
    workflows/
      ci-cd.yml
~~~

Tách biến theo môi trường. Không commit state file, secret hoặc file chứa password. Với Terraform, dùng remote state được mã hóa, bật versioning và cơ chế khóa state để tránh hai pipeline cùng apply. Production apply nên có review/approval và quyền IAM giới hạn theo workspace/account.

### Khung cấu hình ECS service

Đoạn Terraform sau minh họa các thuộc tính quan trọng của ECS service; các ARN, subnet, security group và task definition là input được tạo từ module hạ tầng:

~~~hcl
resource "aws_ecs_service" "web" {
  name            = "web-production"
  cluster         = var.ecs_cluster_arn
  task_definition = aws_ecs_task_definition.web.arn
  launch_type     = "FARGATE"
  desired_count   = 2

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = var.private_app_subnet_ids
    security_groups  = [aws_security_group.web_task.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "web"
    container_port   = 8080
  }
}
~~~

Để cấu hình hoạt động, target group của Fargate dùng target type IP; listener HTTPS của ALB phải forward đến target group; task definition khai báo network mode awsvpc, container tên web, port 8080, log driver và execution role. Service cần được đặt trong private subnets ở ít nhất hai AZ. Với service replica, ECS phân phối task theo AZ trong phạm vi subnet/capacity được cung cấp; sau khi triển khai vẫn phải kiểm tra task placement thực tế.

desired_count bằng 2 là mức nền tối thiểu trong ví dụ. Nếu một AZ mất, một task có thể còn lại để phục vụ traffic. Hãy bảo đảm task còn lại có đủ năng lực cho tải cần thiết; với tải lớn hơn, đặt desired count và autoscaling min capacity cao hơn để duy trì headroom khi một AZ không khả dụng.

### Cấu hình target group và database

Target group cần:

- Target type IP cho Fargate awsvpc networking.
- Health check path /health/ready.
- Success code phù hợp với response của ứng dụng.
- Interval, timeout và unhealthy threshold được chọn theo thời gian khởi động và khả năng phục hồi.
- Deregistration delay đủ để request đang chạy kết thúc khi task bị thay thế.

Database:

- RDS PostgreSQL đặt trong DB subnet group riêng tư có subnet ở ít nhất hai AZ.
- Bật Multi-AZ deployment, encryption at rest, backup retention và deletion protection cho production.
- Chỉ application security group được kết nối cổng 5432.
- Đặt connection limit ở ứng dụng và theo dõi database connections.
- Lấy password từ Secrets Manager; luân chuyển secret theo kế hoạch tương thích với connection pool.

Multi-AZ cải thiện khả năng phục hồi database nhưng không thay thế backup và kiểm thử restore. Failover có thể làm gián đoạn kết nối ngắn hạn; ứng dụng phải kết nối lại có backoff và không tạo retry storm.

## 5. Quy trình CI/CD tự động

Pipeline cần phân biệt CI (kiểm tra chất lượng artifact) và CD (phát hành artifact đến môi trường). Mỗi image phải có tag bất biến theo commit SHA hoặc digest; không dùng tag latest làm định danh duy nhất cho production.

Luồng phát hành:

~~~mermaid
flowchart TD
  A[Commit / Pull Request] --> B[Lint và unit tests]
  B --> C[Build container image]
  C --> D[Scan image và dependency]
  D --> E[Push image vào ECR theo commit SHA]
  E --> F[Đăng ký task definition revision]
  F --> G[Chạy migration tương thích]
  G --> H[Update ECS service]
  H --> I[Chờ service ổn định và health checks]
  I --> J[Smoke test qua ALB]
  J --> K[Theo dõi metric và lỗi]
  K --> L{Đạt ngưỡng?}
  L -->|Có| M[Hoàn tất release]
  L -->|Không| N[Rollback revision]
~~~

Các bước nên thực hiện:

1. Pull request chạy lint, unit test, dependency scan và kiểm tra IaC. Không triển khai production từ pull request chưa được review.
2. Khi merge vào nhánh release, build image một lần và scan lỗ hổng. Gắn tag bằng commit SHA, push lên ECR và lưu image digest.
3. Render task definition với image digest mới, CPU/memory, port, log configuration và secret references.
4. Đăng ký task definition revision mới.
5. Nếu có thay đổi schema, chạy migration runner dưới dạng ECS one-off task với cùng image và quyền database tối thiểu; migration phải tương thích ngược với task hiện tại.
6. Cập nhật ECS service và chờ deployment hoàn tất.
7. Chạy smoke test qua hostname ALB/Route 53.
8. Theo dõi alarm, error rate, latency, task count và database health trong khoảng thời gian quan sát.
9. Nếu health check hoặc alarm quan trọng thất bại, rollback task definition về revision trước và ghi nhận nguyên nhân.

### Xác thực pipeline bằng OIDC

GitHub Actions nên dùng OpenID Connect để nhận quyền AWS tạm thời. Cấu hình IAM role trust policy giới hạn đúng GitHub organization/repository và branch hoặc environment được phép. Chỉ cấp các quyền cần thiết như push vào đúng ECR repository, đăng ký task definition, cập nhật đúng ECS service, đọc trạng thái deployment và iam:PassRole giới hạn cho đúng task execution role/task role.

Không lưu access key AWS dài hạn trong GitHub Secrets nếu có thể dùng OIDC. GitHub vẫn cần lưu các giá trị cấu hình không bí mật như AWS region, ECR repository và ECS cluster/service name. Secret ứng dụng nên nằm trong Secrets Manager hoặc Parameter Store và được task runtime truy cập bằng task role.

Phân biệt hai role ECS:

- **Task execution role:** ECS agent dùng để pull image từ ECR, ghi log và lấy secret theo cấu hình được hỗ trợ.
- **Task role:** quyền của chính ứng dụng khi gọi S3, SQS hoặc API AWS khác.

Không gộp quyền deploy của pipeline vào task role của ứng dụng. Giới hạn trust policy, IAM permission và phạm vi resource để một lỗi trong ứng dụng không tự động có quyền triển khai hạ tầng.

### Rolling deployment và blue/green

ECS rolling deployment thay dần task cũ bằng task mới theo ngưỡng healthy percent. Deployment circuit breaker có thể đánh dấu deployment thất bại và rollback nếu service không ổn định. Đây là lựa chọn đơn giản cho dự án này.

Blue/green deployment dùng hai tập target hoặc revision để chuyển traffic có kiểm soát, có thể hỗ trợ bake time và rollback nhanh. Mô hình này cần cấu hình CodeDeploy/ECS hoặc cơ chế tương đương, hai target group và quy trình kiểm thử riêng. Không chuyển traffic sang bản mới trước khi health check và smoke test đạt.

## 6. Migration database an toàn

Một deployment có thể chạy đồng thời task phiên bản cũ và mới. Vì vậy schema database cần tương thích trong giai đoạn chuyển tiếp.

Dùng quy trình expand-and-contract:

1. Expand: thêm cột/bảng/index mới theo cách không phá vỡ code cũ.
2. Deploy code mới có thể đọc schema cũ và mới; bắt đầu ghi dữ liệu mới nếu cần.
3. Backfill dữ liệu theo batch có giới hạn, theo dõi lock và replication lag.
4. Xác minh dữ liệu mới và chuyển đọc sang cấu trúc mới.
5. Sau khi không còn task cũ và đã qua thời gian rollback, contract: xóa cột hoặc cấu trúc cũ trong một release riêng.

Không chạy migration phá hủy trước khi task mới đã sẵn sàng. Không giả định rollback ứng dụng sẽ tự rollback schema. Với thay đổi không tương thích, cần kế hoạch migration riêng, backup và điểm khôi phục được kiểm thử.

## 7. Autoscaling và năng lực khi mất một zone

ECS Service Auto Scaling có thể điều chỉnh desired count theo CPU, memory hoặc metric phù hợp như request count trên target. Thiết lập:

- Minimum capacity đủ để duy trì ít nhất hai task và headroom khi một AZ gặp sự cố.
- Maximum capacity phù hợp quota, database connection budget và ngân sách.
- Scale-out phản ứng đủ nhanh với tăng tải.
- Scale-in có cooldown và bảo vệ task đang xử lý request.

Không scale application độc lập với database. Nếu mỗi task mở 20 connection và service có thể tăng lên 30 task, database có thể nhận đến 600 connection từ web tier. Đặt pool limit theo capacity database, dùng RDS Proxy nếu phù hợp và kiểm thử peak scale.

### Kiểm tra khả năng N-1

N-1 nghĩa là hệ thống vẫn có thể đáp ứng mục tiêu đã định khi mất một đơn vị hạ tầng, ở đây là một AZ. Để tính sơ bộ, nếu mỗi task xử lý an toàn 100 request/giây và cần duy trì 150 request/giây khi mất một AZ, phải còn ít nhất hai task sau sự cố hoặc tăng năng lực mỗi task. Không dựa vào số task desired trước sự cố; tính theo số task còn lại và capacity thực tế.

Với đúng hai AZ, desired count bằng 2 thường tạo một task mỗi AZ. Khi mất một AZ, chỉ còn một task; cấu hình này chỉ đạt mục tiêu nếu task còn lại tự xử lý được toàn bộ tải yêu cầu. Nếu cần hai task còn sống sau khi mất bất kỳ AZ nào, hãy cấp đủ capacity ở mỗi AZ để một AZ riêng lẻ vẫn còn hai task, ví dụ bốn task tổng cộng và xác minh phân bố thực tế. Một lựa chọn khác là dùng ba AZ với ít nhất một task mỗi AZ, khi đó mất một AZ vẫn còn hai task. Số lượng cuối cùng phải dựa trên tải đỉnh, headroom, quota và giới hạn database.

Thực hiện thử nghiệm trên staging:

1. Ghi nhận số task, AZ placement, ALB healthy targets và latency baseline.
2. Tạo tải đại diện và xác nhận service có đủ headroom.
3. Dừng có kiểm soát task trong một AZ hoặc mô phỏng việc loại bỏ một subnet/target theo runbook staging.
4. Xác nhận ALB ngừng gửi traffic đến target unhealthy, ECS tạo task thay thế ở AZ còn khả dụng nếu cấu hình và capacity cho phép.
5. Đo error rate, p95 latency, throughput và thời gian phục hồi.
6. Kiểm tra database connections, failover event và retry behavior.
7. Khôi phục cấu hình, xác nhận task phân bố lại và ghi lại kết quả.

Không thử tắt toàn bộ subnet hoặc tài nguyên production để mô phỏng lỗi nếu chưa có change plan, phạm vi ảnh hưởng, phê duyệt và phương án rollback. Trong production, có thể thực hiện game day có kiểm soát bằng cách drain target hoặc giảm capacity theo từng bước đã được phê duyệt.

## 8. Bảo mật và vận hành

### Bảo mật

- ALB chỉ nhận HTTPS; dùng ACM certificate và redirect HTTP sang HTTPS.
- ECS task không có public IP; inbound chỉ từ ALB security group.
- Database private, inbound chỉ từ application security group.
- Dùng IAM task role theo quyền tối thiểu; tách execution role và deployment role.
- Secret lưu trong Secrets Manager, không nằm trong Git, image, log hoặc task definition plaintext.
- Image dùng base image được duy trì, quét CVE và deploy theo digest.
- Bật encryption cho EBS/RDS/ECR và log theo yêu cầu tổ chức.
- Ghi audit trail cho thay đổi IAM, network, task definition, service và database.

### Quan sát

| Nhóm | Metric/log | Cảnh báo gợi ý |
|---|---|---|
| ALB | Request count, target response time, HTTP 4xx/5xx, healthy host count | Healthy targets dưới ngưỡng; 5xx hoặc latency tăng |
| ECS | Running/pending task count, CPU, memory, deployment failures | Running tasks thấp hơn desired; CPU/memory kéo dài ở mức cao |
| RDS | CPU, free storage, connections, read/write latency, failover events | Connection gần giới hạn; storage thấp; latency tăng |
| Ứng dụng | Request rate, p50/p95/p99 latency, exception, dependency timeout | Error rate tăng; p95 vượt SLO |
| Pipeline | Build/test/scan/deploy result, task definition revision | Deploy thất bại hoặc image scan có critical finding |

Log nên có request ID, version/build SHA và mức độ log phù hợp. Tránh ghi password, access token, dữ liệu cá nhân hoặc nội dung request nhạy cảm. Thiết lập retention theo nhu cầu vận hành và chi phí.

### Runbook sự cố ngắn

**ALB báo không có healthy target:** kiểm tra ECS running tasks, target health reason, container port, health path, security group và log khởi động.

**ECS task liên tục restart:** kiểm tra exit code, OOM, secret access, image pull, startup timeout và kết nối database.

**Database connection tăng đột biến:** kiểm tra task count, connection pool per task, retry loop và truy vấn chậm; giảm tốc độ scale nếu cần và khôi phục theo ngưỡng an toàn.

**Deployment mới gây lỗi:** dừng phát hành tiếp, xem health check/alarm, rollback task definition revision, xác minh database schema tương thích và ghi lại build SHA bị lỗi.

**Một AZ mất khả năng phục vụ:** xác nhận ALB còn target khỏe ở AZ khác, task capacity và database endpoint; theo dõi latency và autoscaling trong lúc failover.

## 9. Kiểm thử và xác minh bằng lệnh

Thay hostname và tên resource bằng giá trị môi trường của bạn. Các lệnh kiểm tra dưới đây không thay đổi hạ tầng.

Kiểm tra HTTPS và endpoint:

~~~bash
curl -fsS https://web.example.com/health/ready
curl -fsS https://web.example.com/version
~~~

Gửi nhiều request để quan sát nhiều task phục vụ:

~~~bash
for i in $(seq 1 20); do
  curl -fsS https://web.example.com/version
  echo
done
~~~

Xem ECS service và task:

~~~bash
aws ecs describe-services \
  --cluster web-production \
  --services web-production \
  --query 'services[0].{desired:desiredCount,running:runningCount,pending:pendingCount,deployments:deployments[*].status}' \
  --output yaml

aws ecs list-tasks \
  --cluster web-production \
  --service-name web-production
~~~

Xem target health của ALB:

~~~bash
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:REGION:ACCOUNT:targetgroup/web/ID \
  --output table
~~~

Xem log ứng dụng:

~~~bash
aws logs tail /ecs/web-production --since 15m --follow
~~~

Kiểm tra kết quả deployment:

~~~bash
aws ecs wait services-stable \
  --cluster web-production \
  --services web-production
~~~

Lệnh waiter chỉ xác nhận service đạt trạng thái ổn định theo ECS; nó không chứng minh ứng dụng đáp ứng SLO. Luôn chạy smoke test và quan sát metric sau khi waiter hoàn tất.

### Ma trận kiểm thử nghiệm thu

| Kịch bản | Cách thử | Kết quả mong đợi |
|---|---|---|
| Bình thường | Gửi request liên tục qua ALB | 2+ task khỏe, response thành công |
| Task lỗi | Dừng một task staging | ALB loại target, ECS tạo task thay thế |
| Deploy phiên bản mới | Merge commit hợp lệ | Image được scan/push, service cập nhật và smoke test pass |
| Deploy lỗi | Dùng build thử nghiệm có health check fail trong staging | Circuit breaker hoặc pipeline phát hiện lỗi và rollback |
| Database failover | Thực hiện theo quy trình thử nghiệm RDS được phê duyệt | App kết nối lại, lỗi có giới hạn, dữ liệu nhất quán |
| AZ không khả dụng | Mô phỏng bằng cách drain target/task theo runbook | Service còn phục vụ từ AZ khác trong capacity đã cam kết |
| Tăng tải | Chạy load test tăng dần | Autoscaling hoạt động, database không quá tải, latency nằm trong mục tiêu |
| Secret rotation | Xoay secret trên môi trường thử nghiệm | Task lấy secret mới theo quy trình, không cần nhúng secret vào image |

Ghi lại thời gian phục hồi, số request lỗi, p95 latency, throughput và số task còn lại cho mỗi kịch bản. Nếu kết quả không đạt, điều chỉnh capacity, timeout, health check, autoscaling hoặc dependency trước khi tuyên bố nghiệm thu.

## 10. Chi phí và các đánh đổi

Thiết kế nhiều zone tăng tính sẵn sàng nhưng tạo chi phí bổ sung:

- ALB có phí theo thời gian và mức sử dụng.
- ECS Fargate tính theo CPU, memory và thời gian task chạy.
- RDS Multi-AZ có chi phí cao hơn triển khai đơn AZ.
- NAT Gateway, VPC endpoints, data transfer và log ingestion có thể chiếm tỷ trọng đáng kể.
- Hai task tối thiểu có thể chạy liên tục ngay cả khi traffic thấp.

Tối ưu bằng cách chọn CPU/memory theo benchmark, đặt autoscaling min/max hợp lý, giới hạn log noise, dùng VPC endpoints khi có lợi và chọn retention phù hợp. Không giảm xuống một task hoặc bỏ Multi-AZ nếu điều đó làm mất yêu cầu availability đã cam kết. Với staging, có thể dùng lịch bật/tắt tài nguyên hoặc cấu hình nhỏ hơn để giảm chi phí nhưng phải giữ khả năng kiểm thử kiến trúc.

## 11. Mở rộng sang Azure và Google Cloud

Nếu cần triển khai cùng mục tiêu trên nền tảng khác, có thể ánh xạ theo vai trò:

| Vai trò kiến trúc | AWS trong dự án | Azure | Google Cloud |
|---|---|---|---|
| HTTPS load balancing | Application Load Balancer | Azure Application Gateway hoặc Azure Load Balancer tùy lớp L7/L4 | External Application Load Balancer |
| Compute nhiều zone | ECS Fargate service | Azure Container Apps, AKS hoặc VM Scale Sets | Cloud Run, GKE hoặc regional Managed Instance Group |
| Container registry | Amazon ECR | Azure Container Registry | Artifact Registry |
| Managed relational database HA | RDS Multi-AZ | Azure Database for PostgreSQL zone-redundant HA nếu region/SKU hỗ trợ | Cloud SQL HA regional |
| Secret management | AWS Secrets Manager | Azure Key Vault | Secret Manager |
| Metrics/logs | CloudWatch | Azure Monitor / Log Analytics | Cloud Monitoring / Cloud Logging |
| CI/CD identity | GitHub OIDC assume IAM role | GitHub OIDC federated credential với Entra ID | Workload Identity Federation |

Không sao chép nguyên cấu hình subnet, firewall, identity hoặc deployment giữa các cloud. Xác minh mô hình zone, giới hạn dịch vụ, failover semantics, quota và giá tại region đích.

## 12. Hồ sơ bàn giao dự án

Khi hoàn tất, repository cần có:

- Source code web app và Dockerfile.
- Unit/integration tests và cách chạy local.
- IaC cho network, ALB, ECS, ECR, database, IAM và logging.
- Cấu hình task definition cùng tham số theo môi trường.
- Pipeline CI/CD và hướng dẫn OIDC trust policy.
- Runbook deploy, rollback, secret rotation, database recovery và AZ failure.
- Báo cáo kiểm thử gồm kiến trúc, sơ đồ, kết quả load test, lỗi đã mô phỏng và metric.
- Ước tính chi phí theo tháng với giả định rõ ràng.

## Checklist nghiệm thu cuối

- [ ] ALB có listener HTTPS và target group health check đúng.
- [ ] ALB được đặt trong public subnets ở ít nhất hai AZ.
- [ ] ECS tasks chạy trong private subnets ở ít nhất hai AZ và không có public IP.
- [ ] Có ít nhất hai task khỏe trong điều kiện bình thường và đủ headroom cho kịch bản mất một AZ.
- [ ] Security group chỉ cho phép ALB gọi application và application gọi database.
- [ ] Database có Multi-AZ, backup, encryption và kiểm thử restore.
- [ ] Ứng dụng stateless, graceful shutdown và có readiness/liveness endpoint.
- [ ] Image được scan, gắn tag bất biến và lưu trong registry.
- [ ] GitHub Actions xác thực bằng OIDC với quyền deploy tối thiểu.
- [ ] Pipeline chạy test, build, scan, publish, migration, deploy, waiter và smoke test.
- [ ] Có rollback task definition và quy trình tương thích schema.
- [ ] Có dashboard/cảnh báo cho ALB, ECS, database, ứng dụng và pipeline.
- [ ] Đã thử lỗi task, deployment, database failover, tăng tải và AZ failure trên môi trường phù hợp.
- [ ] Có runbook, hồ sơ nghiệm thu và ước tính chi phí.

Một dịch vụ web nhiều zone chỉ được xem là hoàn thành khi bạn có bằng chứng về phân phối traffic, phục hồi, triển khai lặp lại được và khả năng quan sát. Hãy lưu kết quả kiểm thử cùng cấu hình IaC để nhóm khác có thể tái tạo hệ thống và xác minh các mục tiêu vận hành.
