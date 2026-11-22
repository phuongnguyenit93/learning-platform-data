# Phân biệt máy chạy do nền tảng cung cấp với máy tự quản lý

Mỗi pipeline CI/CD cần một môi trường để thực thi các lệnh build, test, scan và deploy. Môi trường đó có thể do nền tảng CI cung cấp sẵn, hoặc do tổ chức tự tạo và vận hành. Lựa chọn này ảnh hưởng trực tiếp đến thời gian chờ job, độ ổn định của build, khả năng truy cập mạng nội bộ, chi phí, bảo mật và công sức vận hành.

Máy chạy do nền tảng cung cấp thường được gọi là **hosted runner** hoặc **managed runner**. Nhà cung cấp nền tảng chịu trách nhiệm cấp phát và duy trì hạ tầng chạy job theo dịch vụ của họ. **Self-hosted runner** là máy hoặc môi trường thực thi do tổ chức tự quản lý, đăng ký với nền tảng CI để nhận job. Nó có thể là máy ảo, máy vật lý, máy trong cloud, container host hoặc một pod được tạo theo nhu cầu.

Không có loại runner nào luôn tốt hơn. Hosted runner phù hợp khi cần bắt đầu nhanh, dùng môi trường tiêu chuẩn và giảm việc quản trị máy. Self-hosted runner phù hợp khi cần phần cứng đặc thù, mạng riêng, cấu hình riêng hoặc kiểm soát sâu môi trường. Nhiều tổ chức kết hợp cả hai để mỗi loại job chạy ở nơi phù hợp với yêu cầu và mức độ tin cậy của nó.

## 1. Runner là gì và nằm ở đâu trong pipeline?

Runner là môi trường thực thi nhận một job từ hệ thống CI, chuẩn bị workspace, chạy các lệnh được khai báo và gửi kết quả về nền tảng. Một job thường đi qua các bước:

1. Nền tảng nhận sự kiện Git hoặc yêu cầu chạy pipeline.
2. Bộ lập lịch tìm runner phù hợp với hệ điều hành, kiến trúc CPU, nhãn và quyền truy cập.
3. Runner nhận job, checkout mã nguồn và chuẩn bị công cụ.
4. Các bước build, test, scan hoặc deploy được thực thi.
5. Log, trạng thái và artifact được gửi hoặc lưu theo cấu hình.
6. Runner kết thúc job, dọn workspace hoặc được thu hồi theo cách vận hành của nó.

Có thể hình dung luồng tổng quát:

~~~text
Git event / Manual trigger
          |
          v
   CI scheduler
          |
          v
 Chọn runner phù hợp
      /       \
     /         \
 Hosted      Self-hosted
 runner       runner
     \         /
      \       /
          v
   Checkout source
          |
          v
     Run job steps
          |
          v
  Logs / reports / artifacts
          |
          v
   CI result and status
~~~

Runner là nơi thực thi, còn pipeline definition mô tả cần làm gì và theo điều kiện nào. Một pipeline có thể dùng nhiều runner khác nhau cho các job: kiểm tra mã nguồn trên hosted runner, kiểm thử phần cứng trên self-hosted runner, rồi triển khai tới môi trường đích bằng một runner được cấp quyền riêng.

### Phân biệt runner host, container và môi trường đích

Ba khái niệm này thường bị nhầm lẫn:

- **Runner host:** máy hoặc môi trường mà agent/runner thực sự chạy. Nó cung cấp kernel, CPU, RAM, filesystem và kết nối mạng.
- **Job container:** container được tạo để chạy các lệnh của job. Container có thể đóng gói runtime và dependency, nhưng vẫn dùng kernel và tài nguyên của host.
- **Target environment:** môi trường mà ứng dụng sẽ được triển khai tới, chẳng hạn staging hoặc production. Runner có thể ở một mạng khác và truy cập target qua API, VPN hoặc cơ chế deploy được cấp quyền.

Dùng container cho job không tự biến self-hosted runner thành môi trường hoàn toàn cách ly. Nếu container có quyền truy cập Docker socket, mount thư mục host, dùng privileged mode hoặc nhận credential mạnh, mã chạy bên trong vẫn có thể tác động tới host và tài nguyên khác. Cần thiết kế ranh giới tin cậy dựa trên quyền thực tế, không chỉ dựa vào tên công nghệ.

## 2. Hosted runner và self-hosted runner

### Hosted runner

Hosted runner là tài nguyên thực thi do nền tảng CI hoặc nhà cung cấp hạ tầng cung cấp. Khi job cần chạy, nền tảng cấp một môi trường phù hợp với loại runner được chọn. Tổ chức thường chọn từ danh sách hệ điều hành, kiến trúc hoặc cấu hình máy đã được hỗ trợ.

Ví dụ thường gặp:

- GitHub-hosted runners trong GitHub Actions.
- Shared runners do nền tảng cung cấp (ví dụ GitLab.com hosted runners) hoặc instance runners do quản trị viên tổ chức cấu hình.
- Các dịch vụ CI cloud cung cấp build agent được quản lý.
- Managed build workers của những nền tảng CI khác.

Nhà cung cấp thường chịu trách nhiệm cấp phát máy, duy trì image cơ sở, cập nhật một phần hệ điều hành và thu hồi môi trường sau job theo mô hình dịch vụ. Phạm vi trách nhiệm cụ thể tùy nền tảng, loại runner, gói dịch vụ và cấu hình.

### Self-hosted runner

Self-hosted runner do tổ chức cài đặt, đăng ký và vận hành. Nó có thể chạy trên:

- Máy ảo trong cloud hoặc datacenter.
- Máy vật lý có CPU, GPU, RAM hoặc thiết bị đặc thù.
- Máy trong mạng nội bộ cần truy cập hệ thống riêng.
- Container host hoặc Kubernetes cluster.
- Máy tạm thời được tạo tự động cho từng job hoặc từng nhóm job.

Tổ chức chịu trách nhiệm về vòng đời máy, hệ điều hành, bản vá, agent runner, toolchain, mạng, dung lượng, giám sát và dọn dẹp. Nền tảng CI vẫn có thể quản lý việc xếp hàng và gửi job, nhưng không mặc nhiên chịu trách nhiệm bảo trì hạ tầng self-hosted.

### Bảng so sánh

| Tiêu chí | Hosted runner | Self-hosted runner |
|---|---|---|
| Cấp phát máy | Nền tảng cung cấp theo dịch vụ | Tổ chức tự tạo và đăng ký |
| Bảo trì hệ điều hành | Chủ yếu do nhà cung cấp theo phạm vi dịch vụ | Tổ chức chịu trách nhiệm |
| Tùy chỉnh phần cứng | Chọn trong các cấu hình được cung cấp | Có thể chọn theo nhu cầu và ngân sách |
| Công cụ build | Dùng image/tool có sẵn hoặc cài thêm trong job | Có thể cài sẵn và kiểm soát sâu hơn |
| Mạng nội bộ | Thường bị giới hạn, cần giải pháp kết nối được hỗ trợ | Có thể đặt trong VPC/VNet hoặc mạng nội bộ |
| Khả năng mở rộng | Nền tảng thường cấp phát tự động trong quota | Cần capacity cố định hoặc autoscaling |
| Chi phí | Thường tính theo phút, loại máy hoặc quota | Máy, lưu trữ, mạng, vận hành và thời gian quản trị |
| Cách ly job | Theo mô hình và cam kết của nền tảng | Phụ thuộc thiết kế của tổ chức |
| Tùy biến môi trường | Có giới hạn theo image và dịch vụ | Linh hoạt hơn, đồng thời tăng trách nhiệm bảo trì |
| Công sức vận hành | Thấp hơn | Cao hơn |
| Phù hợp | Job tiêu chuẩn, mã nguồn có mức tin cậy phù hợp | Job cần tài nguyên, mạng hoặc cấu hình riêng |

## 3. Ưu điểm và giới hạn của hosted runner

### Điểm mạnh

**Bắt đầu nhanh.** Nhóm có thể tạo workflow và chạy job mà không cần dựng máy, cài agent hay thiết kế hệ thống mở rộng runner.

**Giảm công việc bảo trì.** Nhà cung cấp xử lý nhiều việc ở tầng hạ tầng như cấp phát máy và duy trì image cơ sở. Nhóm có thêm thời gian tập trung vào pipeline, test và chất lượng sản phẩm.

**Dễ mở rộng theo tải.** Khi nhiều PR được tạo cùng lúc, nền tảng thường cấp nhiều runner theo quota và giới hạn dịch vụ. Nhóm không cần dự đoán chính xác số máy phải duy trì thường trực.

**Môi trường tiêu chuẩn.** Các image phổ biến thường có sẵn Git, shell, runtime và công cụ phát triển. Điều này thuận tiện cho dự án dùng Java, Node.js, Python, .NET hoặc các toolchain phổ biến.

**Phù hợp với job có độ tin cậy thấp hơn.** Với cấu hình cách ly đúng của nền tảng, hosted runner có thể là lựa chọn phù hợp để chạy mã từ PR hoặc nhánh đóng góp bên ngoài mà không đưa mã đó vào máy nội bộ chứa dữ liệu quan trọng.

### Giới hạn

**Môi trường có thể thay đổi.** Alias như ubuntu-latest trỏ tới image mới theo chính sách của nhà cung cấp. Toolchain cài sẵn, phiên bản compiler hoặc thư viện hệ thống có thể thay đổi theo thời gian. Nếu cần tính tái lập cao, hãy chọn image version cụ thể khi nền tảng hỗ trợ, cố định phiên bản công cụ trong pipeline và ghi nhận thông tin build.

**Tài nguyên có giới hạn.** CPU, RAM, dung lượng đĩa, thời gian tối đa và số job đồng thời phụ thuộc loại runner và gói dịch vụ. Job build lớn có thể thiếu bộ nhớ hoặc hết thời gian.

**Khả năng truy cập mạng riêng hạn chế.** Hosted runner thường không nằm trong mạng nội bộ của tổ chức. Muốn truy cập database, registry hoặc hệ thống riêng cần thiết kế kết nối an toàn được nền tảng hỗ trợ. Không nên mở public endpoint chỉ để runner truy cập thuận tiện.

**Khả năng tùy chỉnh phần cứng hạn chế.** Các yêu cầu như GPU cụ thể, thiết bị USB, kiến trúc CPU đặc biệt hoặc hệ điều hành nội bộ có thể không nằm trong danh sách cấu hình hosted.

**Quota và thời gian chờ.** Hạn mức phút, concurrency hoặc hàng đợi có thể ảnh hưởng khi tải tăng. Nền tảng cũng có thể áp dụng chính sách khác nhau cho repository riêng tư, công khai hoặc gói thuê bao.

## 4. Ưu điểm và trách nhiệm của self-hosted runner

### Điểm mạnh

**Tùy chỉnh sâu.** Tổ chức có thể chọn CPU, RAM, ổ đĩa, GPU, hệ điều hành, thiết bị và phiên bản toolchain theo nhu cầu.

**Truy cập mạng riêng.** Runner có thể đặt trong VPC/VNet, subnet riêng hoặc datacenter để truy cập dependency repository, database thử nghiệm, registry hay dịch vụ nội bộ. Kết nối cần được giới hạn theo nguyên tắc tối thiểu.

**Kiểm soát toolchain.** Có thể xây dựng image chuẩn, cài công cụ nội bộ hoặc sử dụng phần mềm chỉ được cấp phép trong tổ chức. Việc này giúp các job chuyên biệt chạy nhất quán hơn nếu image được quản lý phiên bản và cập nhật đúng cách.

**Tối ưu cho tải ổn định hoặc job nặng.** Một nhóm có thể duy trì máy có cấu hình phù hợp, dùng cache cục bộ hoặc phần cứng tăng tốc. Với workload lớn và đều, mô hình này có thể hiệu quả về chi phí sau khi tính đủ chi phí vận hành.

**Hỗ trợ yêu cầu đặc thù.** Ví dụ build ứng dụng iOS cần macOS, kiểm thử thiết bị thật, build firmware, xử lý dữ liệu lớn hoặc kiểm thử trên phần cứng riêng.

### Trách nhiệm đi kèm

Tổ chức phải quản lý vòng đời runner và xem runner như một tài sản hạ tầng có quyền thực thi mã. Các công việc bao gồm:

- Cấp phát, đăng ký, nâng cấp và thu hồi runner.
- Cập nhật hệ điều hành, agent, runtime và công cụ.
- Giám sát CPU, RAM, disk, network, queue và tình trạng agent.
- Xóa workspace, credential tạm và dữ liệu job sau khi hoàn tất.
- Quản lý quyền truy cập repository, group, project và environment.
- Giới hạn network egress và quyền truy cập vào hệ thống nội bộ.
- Xử lý runner bị lỗi, mất kết nối, treo job hoặc bị nghi ngờ xâm nhập.
- Lập kế hoạch capacity, autoscaling và chi phí.
- Duy trì image chuẩn, kiểm tra lỗ hổng và quy trình vá lỗi.

Self-hosted runner không tự động an toàn hơn chỉ vì nó nằm trong mạng của tổ chức. Nếu một job chạy mã không tin cậy trên máy có credential hoặc quyền mạng rộng, runner có thể trở thành đường dẫn để truy cập tài nguyên nội bộ. Càng nhiều quyền đặc biệt thì ranh giới tin cậy và cơ chế cách ly càng cần rõ.

## 5. Bảo mật: runner là nơi thực thi mã

Pipeline có thể chạy lệnh do người đóng góp đưa vào repository. Vì vậy, runner phải được đánh giá theo nguồn gốc mã, quyền của job và khả năng truy cập của máy.

### Mối đe dọa thường gặp

- PR từ fork thay đổi script build để đọc biến môi trường hoặc gửi dữ liệu ra ngoài.
- Job bị xâm nhập ghi credential vào workspace, cache hoặc log.
- Job tiếp theo chạy trên cùng máy đọc được file còn sót lại của job trước.
- Token đăng ký runner hoặc credential cloud bị lộ.
- Runner có quyền truy cập mạng nội bộ rộng, tạo đường đi tới database hoặc hệ thống quản trị.
- Một job có quyền truy cập Docker socket hoặc chạy privileged container và tác động tới host.
- Người dùng không được tin cậy gửi job lên runner nội bộ có quyền deploy.
- Runner cũ không được vá lỗi hoặc agent bị cấu hình sai.

### Không chia sẻ runner đặc quyền với mã không tin cậy

Một quy tắc quan trọng là không để job từ PR không tin cậy dùng chung máy hoặc credential với job triển khai production. Cần phân nhóm runner theo mức độ tin cậy:

| Nhóm job | Runner phù hợp | Quyền nên có |
|---|---|---|
| Kiểm tra PR công khai hoặc fork | Hosted runner hoặc runner cách ly dùng một lần | Quyền đọc mã nguồn và chạy test |
| Build mã nguồn nội bộ | Hosted hoặc self-hosted pool riêng | Quyền lấy dependency và upload artifact cần thiết |
| Publish artifact | Runner riêng cho release | Quyền ghi đúng registry/repository |
| Deploy staging | Runner được phép truy cập staging | Credential staging và quyền triển khai giới hạn |
| Deploy production | Runner và environment được bảo vệ | Quyền production tối thiểu, approval và audit |

Không cấp secret production cho workflow xử lý mã nguồn từ fork hoặc nguồn chưa được tin cậy. Việc giới hạn secret trong giao diện CI là chưa đủ nếu job có thể đọc credential từ file máy, metadata service, biến hệ thống hoặc socket dùng chung.

### Ưu tiên runner dùng một lần cho workload không tin cậy

Runner tạm thời (ephemeral runner) được tạo để nhận một job hoặc một phạm vi công việc giới hạn rồi bị thu hồi. Cách này giảm nguy cơ trạng thái hoặc mã độc từ job trước tồn tại tới job sau.

Một vòng đời điển hình:

~~~text
Provision runner
      |
      v
Register with CI
      |
      v
Receive one job
      |
      v
Execute in isolated workspace
      |
      v
Upload required outputs
      |
      v
Remove runner and temporary storage
~~~

Ephemeral không có nghĩa tự động cách ly tuyệt đối. Nếu nhiều job cùng chia sẻ host, network hoặc volume, vẫn có rủi ro. Cần kiểm soát cả hạ tầng bên dưới và cơ chế thu hồi tài nguyên.

### Phân quyền runner và credential

- Chỉ cho phép repository hoặc project cần thiết sử dụng runner.
- Dùng runner group hoặc cơ chế tương đương để kiểm soát phạm vi truy cập.
- Đặt runner đặc quyền ở nhóm riêng và yêu cầu workflow được bảo vệ.
- Dùng token ngắn hạn hoặc credential có vòng đời giới hạn khi nền tảng hỗ trợ.
- Không lưu credential production trong image cơ sở hoặc thư mục dùng chung.
- Tách quyền đọc source, publish artifact và deploy.
- Ghi log ai đã đăng ký, thay đổi cấu hình hoặc sử dụng runner.
- Thu hồi ngay runner hoặc credential khi có dấu hiệu bị xâm nhập.

## 6. Quản lý vòng đời và tính nhất quán của môi trường

Hosted runner giảm trách nhiệm vận hành máy, nhưng vẫn cần kiểm soát phiên bản công cụ. Self-hosted runner cần quản lý thêm hệ điều hành, agent và image.

### Chuẩn hóa toolchain

Một môi trường build nên khai báo rõ:

- Phiên bản hệ điều hành hoặc image nền.
- Phiên bản JDK, Node.js, Python, .NET SDK hoặc compiler.
- Phiên bản build tool như Gradle hoặc Maven.
- Dependency và lock file.
- Biến môi trường cần thiết.
- Các công cụ phụ trợ và phiên bản của chúng.

Với Java, có thể dùng Gradle Wrapper hoặc Maven Wrapper và khai báo Java toolchain. Điều đó giúp pipeline không phụ thuộc vào một phiên bản Gradle hoặc Maven cài ngẫu nhiên trên runner.

### Dùng image được quản lý phiên bản

Với self-hosted runner, tổ chức có thể tạo image chuẩn chứa các công cụ cần thiết. Image nên được xây dựng từ mã nguồn có review, quét lỗ hổng, gắn version hoặc digest và có lịch cập nhật.

Không nên để một máy self-hosted tồn tại nhiều năm với công cụ cài thủ công mà không có hồ sơ. Nếu máy bị thay thế, nhóm sẽ khó tái tạo môi trường. Image as code hoặc cấu hình provisioning tự động giúp khôi phục runner dễ dàng hơn.

### Dọn workspace và cache

Workspace có thể chứa source, file tạm, log, credential hoặc artifact. Sau job, cần xác định dữ liệu nào được giữ, dữ liệu nào phải xóa.

- Xóa file tạm và credential.
- Không để secret trong cache.
- Phân vùng cache theo repository, nhánh hoặc mức độ tin cậy.
- Không cho job không tin cậy ghi cache được job release tin cậy sử dụng.
- Kiểm soát quyền đọc và ghi cache.
- Định kỳ dọn dung lượng và kiểm tra cache cũ.

Cache là tối ưu hiệu năng, không phải nơi lưu trữ artifact phát hành. Artifact cần được lưu theo version/digest và chính sách retention riêng.

### Cập nhật và vá lỗi

Self-hosted runner cần lịch vá hệ điều hành, agent và công cụ. Việc cập nhật nên có kiểm tra trước khi đưa image mới vào pool chính. Có thể duy trì một nhóm canary runner để xác minh phiên bản mới trước khi triển khai rộng.

Hosted runner cũng có thể thay đổi image và toolchain do nhà cung cấp cập nhật. Hãy theo dõi thông báo thay đổi, tránh dựa vào phiên bản mặc định không được ghi nhận và dùng image cụ thể nếu cần kiểm soát chặt.

## 7. Mở rộng và quản lý năng lực runner

### Hosted runner: mở rộng theo dịch vụ

Nền tảng thường tự cấp runner theo job đang chờ, nhưng có thể giới hạn bởi concurrency, quota hoặc loại máy. Nhóm nên theo dõi queue time, thời gian chạy và số job đồng thời để chọn gói hoặc cấu hình phù hợp.

Nếu pipeline liên tục phải chờ runner, có thể:

- Giảm số job không cần thiết.
- Tách job dài thành các phần độc lập khi có ích.
- Tối ưu cache và dependency download.
- Chọn loại runner phù hợp với workload.
- Điều chỉnh lịch hoặc concurrency theo chính sách nền tảng.

### Self-hosted runner: pool và autoscaling

Một pool runner là nhóm máy có cấu hình và quyền tương tự, được dùng để nhận một loại job. Ví dụ có pool linux-general, windows-build, macos-signing và deploy-staging.

Có thể bắt đầu bằng một số máy cố định, sau đó mở rộng tự động dựa trên độ dài hàng đợi hoặc số job đang chờ. Một bộ autoscaler có thể tạo VM hoặc pod khi tải tăng và thu hồi khi tải giảm.

Một số mô hình thường dùng:

- **Máy cố định:** đơn giản, phù hợp tải ổn định nhưng có thể lãng phí khi ít job.
- **VM tạm thời:** tạo máy theo nhu cầu, sau job thì xóa. Phù hợp workload cần cách ly ở mức máy ảo.
- **Container hoặc Kubernetes pod:** tạo môi trường thực thi nhanh, dễ mở rộng theo cluster; cần thiết kế bảo vệ host và quyền container.
- **Runner scale set:** cơ chế điều phối runner tự động theo nền tảng hoặc controller chuyên dụng.

GitHub Actions Runner Controller (ARC) là một lựa chọn để chạy và mở rộng self-hosted runner trên Kubernetes. GitLab Runner cũng hỗ trợ nhiều executor, bao gồm shell, Docker và Kubernetes. Khi chọn executor, cần hiểu rõ ranh giới giữa job, container, pod, VM và host.

### Đo năng lực theo workload

Không nên chỉ đếm số runner. Cần xem xét:

- Số job đang chờ và queue time.
- Thời gian thực thi theo loại job.
- CPU, RAM, disk I/O và network.
- Số job đồng thời an toàn trên một máy.
- Tỷ lệ runner không sẵn sàng hoặc mất kết nối.
- Tần suất autoscaling và thời gian cấp phát máy.
- Tỷ lệ job thất bại do thiếu tài nguyên.
- Chi phí trên mỗi pipeline thành công.

Một runner mạnh có thể chạy nhiều job nhẹ, nhưng job build lớn hoặc cần thiết bị độc quyền có thể phải chạy riêng. Capacity planning cần dựa vào đặc điểm workload thực tế.

## 8. Cấu hình runner trong pipeline

### Ví dụ GitHub Actions: hosted runner

Workflow có thể chọn loại runner do GitHub cung cấp bằng trường runs-on:

~~~yaml
name: build-on-hosted-runner

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: gradle
      - run: ./gradlew --no-daemon check
~~~

Ở đây, ubuntu-24.04 chọn image Ubuntu cụ thể hơn alias ubuntu-latest. Phiên bản action và toolchain vẫn cần được quản lý theo chính sách của dự án. Nếu cần tái lập chặt chẽ, có thể pin action theo commit SHA và kiểm soát dependency.

### Ví dụ GitHub Actions: self-hosted runner

Self-hosted runner được chọn thông qua nhãn:

~~~yaml
name: build-on-self-hosted-runner

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: [self-hosted, linux, x64, ci-general]
    steps:
      - uses: actions/checkout@v4
      - run: ./gradlew --no-daemon check
~~~

Các nhãn trong runs-on phải khớp với nhãn runner đã đăng ký. Ví dụ này yêu cầu runner có nhãn self-hosted, linux, x64 và ci-general. Nếu không có runner nào đáp ứng tất cả nhãn hoặc runner đang bận, job sẽ chờ.

Không nên đặt nhãn quá chung cho runner có quyền đặc biệt. Một nhãn như production-deploy nên chỉ gắn với runner và repository được phép triển khai production.

### Ví dụ GitLab CI/CD

GitLab Runner có thể được chọn bằng tags. Runner phải có đủ các tag được job yêu cầu:

~~~yaml
stages:
  - verify

verify:
  stage: verify
  tags:
    - linux-docker
    - ci-general
  script:
    - ./gradlew --no-daemon check
~~~

GitLab có thể dùng shared/instance runners hoặc runner do tổ chức tự cài đặt ở cấp project, group hay instance. Việc job có thể dùng runner nào phụ thuộc runner được bật cho project, tag, trạng thái protected và các thiết lập truy cập.

Executor quyết định cách job được thực thi. Shell executor chạy trực tiếp trên máy runner và có mức chia sẻ môi trường lớn hơn. Docker executor chạy job trong container nhưng vẫn phụ thuộc host Docker và cấu hình mount/network. Kubernetes executor tạo pod cho job và cần kiểm soát service account, namespace, network policy và quyền cluster.

### Jenkins agent

Trong Jenkins, agent là máy thực thi job được controller điều phối. Agent có thể là máy cố định, VM, container hoặc pod Kubernetes. Có thể dùng label để chọn agent phù hợp, ví dụ linux-build, windows-signing hoặc macos-test.

Không nên chạy mọi build trên controller. Tách controller và agent giúp giới hạn tải, quyền và bề mặt ảnh hưởng. Với agent dùng chung lâu dài, cần dọn workspace và credential sau mỗi job; với job không tin cậy hoặc có quyền cao, agent tạm thời thường an toàn hơn.

## 9. Chọn runner theo mức độ tin cậy của mã nguồn

Nguồn gốc job quan trọng hơn việc job có vẻ đơn giản. Một lệnh test có thể thực thi script do PR sửa đổi; một job build có thể chạy plugin Gradle hoặc npm package có mã tùy ý.

Một ma trận quyết định đơn giản:

| Nguồn job | Hosted runner | Self-hosted runner |
|---|---|---|
| PR từ fork công khai | Thường là lựa chọn ưu tiên nếu không cấp secret | Chỉ dùng khi runner tạm thời, cách ly và không có quyền nội bộ |
| PR từ thành viên nội bộ | Phù hợp cho kiểm tra thông thường | Có thể dùng pool riêng với quyền giới hạn |
| Build trên nhánh chính đã bảo vệ | Phù hợp hoặc dùng pool nội bộ | Có thể dùng runner chuẩn hóa để tăng hiệu năng |
| Build release | Dùng được nếu đáp ứng yêu cầu artifact và credential | Có thể dùng runner release chuyên biệt |
| Deploy staging | Dùng được nếu có kết nối an toàn tới staging | Thường phù hợp khi staging nằm trong mạng riêng |
| Deploy production | Chỉ khi nền tảng và mô hình quyền đáp ứng chính sách | Có thể dùng runner riêng, protected và có approval |
| Job cần GPU/thiết bị đặc thù | Chỉ khi dịch vụ cung cấp đúng phần cứng | Thường cần self-hosted |
| Job cần phần mềm được cấp phép nội bộ | Có thể bị giới hạn bởi license/network | Có thể phù hợp với máy và license do tổ chức quản lý |

Đây là hướng dẫn định hướng. Quyết định cuối cùng cần dựa trên threat model, chính sách dữ liệu, khả năng kết nối, chi phí và cam kết của nhà cung cấp.

### Tách runner theo trust zone

Một tổ chức có thể thiết kế nhiều vùng:

- **Untrusted zone:** job từ fork hoặc mã nguồn chưa được review; không có secret nội bộ và không truy cập mạng riêng.
- **Build zone:** job trên nhánh được bảo vệ; có quyền lấy dependency và tạo artifact.
- **Release zone:** job publish artifact; chỉ nhận đầu vào đã được xác minh và có quyền ghi registry giới hạn.
- **Deployment zone:** job deploy; có quyền truy cập đúng môi trường và dùng credential riêng.
- **Production zone:** bước triển khai nhạy cảm, yêu cầu runner được bảo vệ, phê duyệt và audit.

Các vùng này có thể dùng hosted runner, self-hosted runner hoặc cả hai. Điều quan trọng là job không thể tự nâng quyền chỉ bằng cách thay đổi YAML trong PR.

## 10. Mô hình kết hợp hosted và self-hosted

Mô hình hybrid dùng hosted runner cho công việc tiêu chuẩn và self-hosted runner cho những job có yêu cầu riêng.

Ví dụ:

~~~text
Pull Request
     |
     v
Hosted runner
  - lint
  - unit test
  - static analysis
     |
     v
Protected main branch
     |
     v
Hosted build runner
  - compile
  - package
  - create artifact
     |
     v
Artifact registry
     |
     v
Self-hosted staging runner
  - deploy staging
  - smoke test
     |
     v
Approval / release gate
     |
     v
Protected production runner
  - deploy production
  - verify runtime
~~~

Lợi ích của mô hình hybrid:

- Giảm số máy nội bộ phải duy trì.
- Không đưa mọi job vào mạng riêng.
- Giữ job cần phần cứng hoặc quyền đặc biệt ở runner phù hợp.
- Tách biệt job kiểm tra thông thường và job triển khai.
- Có thể mở rộng hosted runner theo tải trong khi self-hosted runner được dành cho workload chuyên biệt.

Cần truyền artifact qua kho lưu trữ có định danh và quyền truy cập phù hợp. Không nên dùng workspace trên một máy để chuyển dữ liệu giữa hosted và self-hosted runner. Artifact cần được gắn với commit, version hoặc digest để job phía sau xác minh đúng đầu vào.

## 11. Chi phí: nhìn toàn bộ vòng đời

Hosted runner thường có mô hình tính phí dễ quan sát hơn: phút chạy, loại máy, concurrency hoặc quota theo gói. Self-hosted runner có thể không tính phí theo phút từ nền tảng, nhưng vẫn có chi phí hạ tầng và vận hành.

### Thành phần chi phí hosted

- Số phút hoặc thời gian sử dụng runner.
- Hệ số giá theo loại CPU, RAM hoặc hệ điều hành.
- Phí lưu artifact, cache và log nếu có.
- Phí vượt quota hoặc concurrency theo gói.
- Thời gian chờ nếu cần nâng gói hoặc mua thêm năng lực.

### Thành phần chi phí self-hosted

- VM, máy vật lý, GPU, disk và network.
- Chi phí cluster hoặc Kubernetes nếu dùng.
- Thời gian kỹ sư vận hành, vá lỗi và xử lý sự cố.
- Giám sát, log, backup và bảo mật.
- Dung lượng dự phòng cho tải cao điểm.
- Chi phí máy nhàn rỗi khi nhu cầu giảm.
- Công sức xây dựng autoscaler và image chuẩn.

Không nên so sánh chỉ dựa vào giá mỗi phút. Một self-hosted runner có thể rẻ hơn khi tải lớn và ổn định, nhưng chi phí vận hành, idle capacity và sự cố có thể làm tổng chi phí cao hơn. Hosted runner có thể tiết kiệm công sức cho workload không thường xuyên, dù giá trực tiếp trên mỗi phút cao hơn.

### Cách ước lượng

Có thể dùng công thức định hướng:

~~~text
Tổng chi phí hosted
  = tổng phút runner theo từng loại
  + phí lưu trữ và dịch vụ liên quan

Tổng chi phí self-hosted
  = hạ tầng máy và mạng
  + dung lượng dự phòng
  + lưu trữ và giám sát
  + chi phí vận hành
  + chi phí sự cố và bảo trì
~~~

Nên đo chi phí trên mỗi pipeline thành công hoặc mỗi lần phát hành thay vì chỉ tính chi phí trên mỗi job. Một runner rẻ nhưng thường xuyên thất bại hoặc phải chạy lại có thể làm tổng chi phí tăng.

## 12. Xử lý sự cố runner

Khi job không chạy hoặc thất bại, hãy phân loại vấn đề trước khi thay đổi pipeline.

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Job nằm ở trạng thái queued lâu | Không có runner phù hợp, hết quota hoặc runner bận | Kiểm tra labels/tags, concurrency, quota và trạng thái agent |
| Job không tìm thấy tool | Image hoặc PATH không có công cụ | Kiểm tra runner image, phiên bản toolchain và bước setup |
| Build chỉ lỗi trên self-hosted | Môi trường máy có trạng thái cũ hoặc khác cấu hình | Kiểm tra workspace, cache, biến môi trường và phiên bản hệ điều hành |
| Job không truy cập được service | Network policy, DNS, firewall hoặc credential | Kiểm tra đường mạng, endpoint, quyền và secret |
| Job chạy lâu rồi hết disk | Workspace, cache hoặc artifact tích lũy | Kiểm tra dung lượng, retention và cleanup |
| Job sau đọc được dữ liệu job trước | Workspace hoặc volume dùng chung | Cô lập runner, dọn sạch hoặc chuyển sang ephemeral |
| Runner mất kết nối | Agent, mạng hoặc máy host gặp lỗi | Kiểm tra agent log, health và hệ thống cấp phát |
| Job bị từ chối quyền | Runner group, protected branch hoặc permission | Kiểm tra phạm vi đăng ký và chính sách bảo vệ |
| Job PR có thể đọc secret | Cấu hình trigger hoặc quyền runner không an toàn | Rà soát trust zone, event và cách cấp credential |

Khi runner có dấu hiệu bị xâm nhập, cần ngừng nhận job, thu hồi credential liên quan, cô lập máy và điều tra log. Với runner tạm thời, thu hồi máy sau khi thu thập bằng chứng cần thiết. Không đưa runner trở lại pool chỉ bằng cách khởi động lại agent nếu chưa xác định được nguyên nhân.

## 13. Checklist lựa chọn và vận hành runner

### Trước khi chọn loại runner

- [ ] Đã xác định hệ điều hành, kiến trúc và tài nguyên cần thiết.
- [ ] Đã xác định job có cần truy cập mạng nội bộ hay không.
- [ ] Đã đánh giá nguồn gốc mã nguồn và mức độ tin cậy của job.
- [ ] Đã xác định secret và quyền mà job cần.
- [ ] Đã kiểm tra quota, concurrency và giới hạn thời gian của hosted runner.
- [ ] Đã tính cả chi phí vận hành nếu dùng self-hosted.
- [ ] Đã xem xét yêu cầu phần cứng hoặc phần mềm được cấp phép.

### Khi vận hành self-hosted runner

- [ ] Runner được đăng ký trong phạm vi repository/group/project phù hợp.
- [ ] Runner có nhãn phản ánh đúng OS, kiến trúc và mục đích.
- [ ] Hệ điều hành, agent và toolchain có lịch cập nhật.
- [ ] Job chạy với tài khoản ít quyền nhất có thể.
- [ ] Network egress và truy cập nội bộ được giới hạn.
- [ ] Workspace, cache và credential được dọn hoặc cô lập.
- [ ] Runner có giám sát sức khỏe, disk, CPU, RAM và queue.
- [ ] Có cơ chế thu hồi runner và credential khi có sự cố.
- [ ] Job không tin cậy không dùng chung runner đặc quyền.
- [ ] Có kế hoạch autoscaling hoặc capacity cho tải cao điểm.

### Khi dùng hosted runner

- [ ] Đã chọn image hoặc phiên bản runner phù hợp.
- [ ] Toolchain quan trọng được cố định phiên bản.
- [ ] Pipeline không phụ thuộc ngầm vào công cụ cài sẵn.
- [ ] Không giả định hosted runner có thể truy cập mạng riêng.
- [ ] Secret chỉ được cấp cho job cần thiết và có mức tin cậy phù hợp.
- [ ] Đã theo dõi quota, queue time và chi phí.
- [ ] Artifact được lưu riêng và có định danh để truy vết.

## Kết luận

Hosted runner giúp nhóm bắt đầu nhanh, giảm công việc quản trị và mở rộng theo dịch vụ. Self-hosted runner đem lại quyền kiểm soát phần cứng, toolchain và mạng, nhưng đi kèm trách nhiệm bảo trì, bảo mật và quản lý năng lực. Hãy chọn runner theo yêu cầu của từng job, mức độ tin cậy của mã nguồn và quyền mà job cần. Khi cần cả sự linh hoạt lẫn kiểm soát, mô hình hybrid kết hợp hosted runner với các pool self-hosted chuyên biệt có thể đáp ứng tốt hơn một lựa chọn duy nhất cho toàn bộ pipeline.

