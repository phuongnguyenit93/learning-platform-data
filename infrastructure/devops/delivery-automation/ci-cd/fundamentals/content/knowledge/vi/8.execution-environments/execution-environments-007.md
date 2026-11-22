# Quản lý tài nguyên, thời gian chờ và giới hạn kết nối

Một pipeline CI/CD có thể đúng về logic nhưng vẫn chậm, không ổn định hoặc làm gián đoạn dịch vụ dùng chung nếu các job tiêu thụ tài nguyên không được kiểm soát. Nhiều job chạy đồng thời có thể làm cạn CPU, bộ nhớ và dung lượng đĩa của runner. Một job chờ dịch vụ bên ngoài vô thời hạn có thể giữ worker và làm tắc hàng đợi. Một nhóm test mở quá nhiều kết nối đến database hoặc API có thể vượt giới hạn của hệ thống phụ thuộc.

Quản lý môi trường thực thi vì vậy không chỉ là chọn máy chạy pipeline. Cần thiết kế rõ **ngân sách tài nguyên, thời gian chờ, mức song song và giới hạn kết nối** cho từng job. Các giới hạn này giúp pipeline có thời gian hoàn thành dự đoán được, sử dụng hạ tầng hiệu quả và không gây quá tải cho dịch vụ bên ngoài.

## 1. Môi trường thực thi tiêu thụ những tài nguyên nào?

Mỗi job chạy trên runner, máy ảo, container hoặc môi trường thực thi do nền tảng cung cấp. Trong suốt vòng đời, job có thể tiêu thụ nhiều loại tài nguyên:

| Tài nguyên | Nơi sử dụng | Dấu hiệu thiếu hoặc quá tải |
|---|---|---|
| CPU | Biên dịch, nén, phân tích mã, chạy test | Job kéo dài, CPU luôn ở mức cao, nhiều tiến trình tranh chấp |
| RAM | Compiler, test runner, container, cache trong bộ nhớ | OOM kill, tiến trình bị dừng, garbage collection tăng |
| Disk | Checkout, dependency cache, build output, Docker layer, log | Hết dung lượng, ghi file lỗi, build thất bại giữa chừng |
| I/O | Đọc dependency, giải nén, ghi artifact, database test | CPU thấp nhưng job vẫn chậm, hàng đợi I/O tăng |
| Network | Tải dependency, gọi API, push image, truy cập dịch vụ test | Timeout, retry tăng, throughput thấp, lỗi kết nối |
| Process/thread | Test song song, compiler daemon, worker | Vượt giới hạn tiến trình, context switching nhiều |
| Connection | Database pool, HTTP client, registry, service endpoint | Connection refused, pool timeout, HTTP 429 hoặc 503 |
| Quota nền tảng | Phút CI, số runner, artifact storage, API rate limit | Job phải chờ, bị từ chối hoặc không thể publish |

Không phải job nào cũng cần nhiều CPU. Một job tải dependency có thể bị giới hạn bởi mạng hoặc registry; một job integration test có thể bị giới hạn bởi database; một job build image có thể tiêu thụ nhiều disk và I/O. Vì thế, không nên chỉ nhìn thời gian chạy tổng thể để kết luận cần tăng cấu hình máy.

Cần đo tài nguyên theo từng loại job và theo giai đoạn. Ví dụ, nếu build mất nhiều thời gian ở bước tải dependency nhưng CPU gần như nhàn rỗi, tăng số core có thể không giúp ích. Nếu runner hết disk do giữ nhiều Docker image cũ, tăng CPU hoặc RAM cũng không giải quyết nguyên nhân.

## 2. Xác định ngân sách tài nguyên cho job

Mỗi loại job nên có ngân sách tài nguyên phù hợp với khối lượng công việc và mức song song dự kiến. Ngân sách có thể gồm CPU, RAM, disk, thời gian tối đa, số tiến trình và số kết nối được phép mở.

Ví dụ phân loại sơ bộ:

| Loại job | Đặc điểm | Tài nguyên cần chú ý |
|---|---|---|
| Lint và static analysis | Nhiều thao tác đọc mã, có thể xử lý nhiều file | CPU, RAM |
| Unit test | Có thể chạy nhiều test process | CPU, RAM, process/thread |
| Integration test | Khởi động database, broker hoặc service phụ trợ | RAM, disk, network, connection |
| Build package | Compiler, linker, đóng gói | CPU, RAM, disk và I/O |
| Build container image | Tạo layer, nén và lưu cache | CPU, RAM, disk, I/O |
| Publish artifact | Upload package hoặc image | Network, connection, registry quota |
| Deploy | Gọi API điều khiển hạ tầng và chờ rollout | Network, API rate limit, timeout |
| End-to-end test | Gọi nhiều dịch vụ và tạo dữ liệu kiểm thử | Network, connection, thời gian và tài nguyên dịch vụ |

Ngân sách cần tính đến phần tài nguyên dành cho hệ điều hành, agent của CI và các tiến trình nền. Không nên phân bổ toàn bộ RAM hoặc CPU nhìn thấy được cho ứng dụng của job. Trên runner dùng chung, phải tính tổng nhu cầu của các job đồng thời, không chỉ nhu cầu của một job riêng lẻ.

### 2.1. Ước lượng mức song song

Giả sử runner có 8 vCPU và 16 GiB RAM. Một job build cần trung bình 2 vCPU và 4 GiB RAM. Nếu chỉ xét hai tài nguyên này, số job đồng thời tối đa về lý thuyết là:

~~~text
min(floor(8/2), floor(16/4)) = 4
~~~

Nhưng con số 4 chưa tính tài nguyên dự phòng, I/O, disk, process, network và tiến trình nền. Nếu dành 2 vCPU và 4 GiB RAM làm phần dự phòng, mức song song thực tế theo ví dụ chỉ còn:

~~~text
min(floor((8-2)/2), floor((16-4)/4)) = 3
~~~

Đây vẫn chỉ là ước lượng. Hãy kiểm tra bằng số liệu khi chạy tải thực tế, vì mức sử dụng đỉnh và mức sử dụng trung bình có thể khác nhau đáng kể.

Với nhiều loại job khác nhau, số job đồng thời bị giới hạn bởi tài nguyên khan hiếm nhất:

~~~text
C <= min(C_CPU, C_RAM, C_disk, C_network, C_connections, C_quota)
~~~

Trong đó C là mức song song được phép. Nếu runner có đủ CPU nhưng database chỉ chấp nhận thêm 20 kết nối, giới hạn database có thể quyết định số integration test chạy cùng lúc.

### 2.2. Đặt giới hạn và yêu cầu tài nguyên

Tùy nền tảng, tài nguyên được cấu hình ở runner, container, executor, Kubernetes pod hoặc chính lệnh chạy test. Nên phân biệt:

- **Request:** lượng tài nguyên dự kiến cần để scheduler bố trí môi trường.
- **Limit:** mức tối đa tiến trình được phép sử dụng.
- **Concurrency limit:** số job hoặc tác vụ được chạy cùng lúc.
- **Quota:** tổng tài nguyên hoặc thời lượng được phép tiêu thụ trong một khoảng thời gian.

Ví dụ Docker Compose cho một dịch vụ kiểm thử có thể khai báo giới hạn CPU và bộ nhớ theo khả năng của môi trường triển khai:

~~~yaml
services:
  integration-test:
    image: example/test-runner:1.0
    command: ./run-integration-tests.sh
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 4G
~~~

Cấu hình trên minh họa ý tưởng giới hạn tài nguyên. Cách áp dụng trường deploy.resources phụ thuộc phiên bản Docker Compose, chế độ triển khai và runtime; cần xác minh nền tảng thực tế có thực thi giới hạn đó hay không. Nếu giới hạn chỉ tồn tại trong file nhưng executor bỏ qua, job vẫn có thể tiêu thụ nhiều tài nguyên hơn dự kiến.

Không đặt limit quá thấp khiến job bị OOM hoặc throttling liên tục. Cũng không cấp limit quá cao cho tất cả job vì có thể làm giảm số job đồng thời và tăng chi phí. Hãy dùng số liệu thực tế để điều chỉnh request và limit.

## 3. Kiểm soát mức song song và hàng đợi

CI/CD thường có nhiều nguồn kích hoạt cùng lúc: nhiều pull request, nhiều lần push, build release và lịch kiểm tra định kỳ. Nếu mọi job đều chạy đồng thời, hạ tầng và dịch vụ phụ thuộc có thể quá tải.

Cần phân biệt các lớp song song:

- **Pipeline concurrency:** số pipeline đang chạy trong repository hoặc project.
- **Job concurrency:** số job được scheduler phân phối đồng thời.
- **Step/process parallelism:** số tiến trình hoặc test worker bên trong một job.
- **Service concurrency:** số request, session hoặc connection gửi đến dịch vụ phụ thuộc.

Tăng song song ở một lớp có thể làm tăng tải ở tất cả lớp còn lại. Ví dụ, 5 pipeline cùng chạy, mỗi pipeline có 4 job integration test, mỗi job mở pool 10 kết nối sẽ tạo ra tối đa 200 kết nối tiềm năng đến database.

Một số cách kiểm soát:

1. Đặt giới hạn job đồng thời theo nhóm runner hoặc loại tác vụ.
2. Dùng queue để điều tiết các job cần tài nguyên khan hiếm.
3. Hủy lần chạy cũ đã lỗi thời khi có commit mới nếu chính sách cho phép.
4. Giới hạn số test worker bên trong mỗi job.
5. Tách runner cho build CPU-intensive, integration test và deploy.
6. Giới hạn concurrency của job publish hoặc deploy theo môi trường.
7. Dùng semaphore hoặc lock khi nhiều pipeline cùng sửa một tài nguyên dùng chung.

Ví dụ GitHub Actions dùng concurrency group để chỉ giữ một lần chạy mới nhất cho cùng workflow và ref:

~~~yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: ./mvnw --batch-mode verify
~~~

Cấu hình này phù hợp với CI có thể thay thế bằng lần chạy mới hơn. Không nên dùng cancel-in-progress cho mọi loại job. Một lần deploy đang thay đổi môi trường, migration hoặc publish release có thể cần hoàn tất hoặc đi qua quy trình hủy an toàn. Với những tác vụ đó, cần concurrency group riêng, cơ chế tuần tự hóa và xử lý trạng thái giữa các lần chạy.

## 4. Quản lý timeout theo từng lớp

Timeout là giới hạn thời gian chờ cho một thao tác hoặc công việc. Không có timeout, job có thể giữ runner vô thời hạn khi một dịch vụ không phản hồi, một tiến trình bị treo hoặc một request không bao giờ kết thúc.

Không nên dùng một giá trị timeout duy nhất cho toàn bộ hệ thống. Cần xác định các lớp thời gian chờ:

| Lớp timeout | Phạm vi | Ví dụ |
|---|---|---|
| Queue timeout | Thời gian chờ được scheduler cấp runner | Job chờ runner trong hàng đợi |
| Job timeout | Tổng thời gian thực thi job | Build hoặc test hoàn tất trong giới hạn |
| Step timeout | Một bước trong job | Tải dependency hoặc deploy |
| Command timeout | Một tiến trình hoặc lệnh con | Maven, Gradle, Docker build |
| Connection timeout | Thiết lập kết nối | Mở kết nối database hoặc API |
| Read/response timeout | Chờ dữ liệu phản hồi | HTTP request hoặc đọc từ socket |
| Test timeout | Một test hoặc nhóm test | Integration test bị treo |
| Deployment/rollout timeout | Chờ tài nguyên đạt trạng thái mong muốn | Kubernetes rollout |

Các nền tảng CI có thể định nghĩa timeout khác nhau. Một số có job timeout nhưng không có timeout riêng cho từng step; một số cho phép timeout ở cấp stage hoặc task. Hãy kiểm tra đúng semantics của nền tảng, đặc biệt là thời điểm bắt đầu tính timeout và cách hủy tiến trình con.

### 4.1. Chọn timeout có cơ sở

Timeout quá ngắn làm job thất bại giả khi hệ thống chậm tạm thời. Timeout quá dài làm tài nguyên bị giữ lâu và che giấu lỗi treo.

Có thể chọn timeout dựa trên phân phối thời gian chạy thực tế:

- Thu thập thời gian hoàn thành của nhiều lần chạy thành công.
- Phân tích median và các percentile cao như p95 hoặc p99.
- Xác định mức dao động hợp lý do tải, cache miss và mạng.
- Đặt timeout cao hơn thời gian thông thường nhưng thấp hơn ngưỡng gây lãng phí hoặc ảnh hưởng SLA.
- Theo dõi số lần timeout và điều chỉnh khi khối lượng công việc thay đổi.

Ví dụ, nếu 95% lần chạy unit test hoàn thành trong 4 phút, còn 99% hoàn thành trong 6 phút, có thể đặt timeout 10 phút để có khoảng đệm. Nếu job thường mất 8 phút nhưng timeout 10 phút liên tục bị chạm, cần điều tra tải hoặc tối ưu job thay vì chỉ tăng timeout.

### 4.2. Timeout tổng và timeout thao tác

Job timeout là giới hạn tổng. Bên trong job, các thao tác mạng và lệnh dài cũng cần giới hạn riêng. Nếu job timeout là 20 phút nhưng một HTTP request có thể treo 20 phút, các bước xử lý lỗi hoặc lưu log có thể không còn thời gian chạy.

Nên phân bổ ngân sách thời gian theo cấu trúc:

~~~text
T_job >= T_checkout + T_build + T_test + T_publish + T_cleanup + T_reserve
~~~

Với một request, thời gian kết nối và thời gian đọc phản hồi nên có giới hạn riêng. Ví dụ, kết nối API tối đa 3 giây, chờ phản hồi tối đa 15 giây, và toàn bộ bước publish có timeout 5 phút. Các con số thực tế phải dựa trên latency và SLA của dịch vụ.

### 4.3. Ví dụ timeout trong GitHub Actions

~~~yaml
jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4

      - name: Run unit tests
        run: ./mvnw --batch-mode test

      - name: Package application
        timeout-minutes: 8
        run: ./mvnw --batch-mode package -DskipTests
~~~

Trong GitHub Actions, timeout-minutes có thể được đặt ở job và step. Timeout ở step cần nhỏ hơn ngân sách còn lại của job nếu muốn job tiếp tục chạy các bước sau. Ví dụ trên chỉ minh họa cách khai báo; thời gian phù hợp phụ thuộc loại project và runner.

## 5. Timeout cho network và dịch vụ phụ thuộc

Job CI thường gọi registry, package repository, database, API, Kubernetes API hoặc dịch vụ test. Mỗi loại thao tác có đặc điểm chờ khác nhau.

Nên phân biệt:

- **DNS timeout:** không phân giải được tên dịch vụ.
- **Connect timeout:** không thiết lập được TCP/TLS connection trong thời gian quy định.
- **TLS handshake timeout:** không hoàn tất bắt tay bảo mật.
- **Read timeout:** đã kết nối nhưng không nhận được dữ liệu đúng hạn.
- **Overall request deadline:** tổng thời gian cho toàn bộ request, bao gồm retry nếu có.

Một request có connect timeout 3 giây và read timeout 10 giây vẫn có thể kéo dài lâu hơn 13 giây nếu ứng dụng retry nhiều lần. Vì vậy, cần có deadline tổng cho thao tác.

Với thao tác có thể kéo dài như tải image lớn hoặc deploy, timeout phải dựa trên kích thước dữ liệu, băng thông và thời gian rollout. Không dùng timeout quá ngắn khiến upload bị ngắt giữa chừng, nhưng cũng không để kết nối treo vô hạn.

Khi timeout xảy ra, log nên ghi rõ loại timeout, endpoint hoặc dịch vụ liên quan (không ghi secret), thời gian đã chờ, số lần thử và mã lỗi. Thông tin này giúp phân biệt lỗi DNS, lỗi mạng, quá tải dịch vụ và lỗi ứng dụng.

## 6. Quản lý giới hạn kết nối

Một kết nối là tài nguyên có trạng thái. Database, HTTP server, registry và broker đều có giới hạn số kết nối đồng thời. Mở quá nhiều kết nối có thể làm dịch vụ từ chối kết nối mới, tăng bộ nhớ và làm giảm hiệu năng cho cả pipeline lẫn ứng dụng đang chạy.

### 6.1. Connection pool

Thay vì mở một kết nối mới cho mỗi thao tác, ứng dụng hoặc test runner thường sử dụng connection pool. Pool tái sử dụng các kết nối hiện có và giới hạn số kết nối tối đa.

Các tham số quan trọng:

| Tham số | Ý nghĩa |
|---|---|
| Maximum pool size | Số kết nối tối đa trong một pool |
| Minimum idle | Số kết nối nhàn rỗi tối thiểu được duy trì |
| Connection timeout | Thời gian chờ lấy kết nối từ pool |
| Idle timeout | Thời gian một kết nối nhàn rỗi được giữ |
| Max lifetime | Tuổi thọ tối đa của một kết nối |
| Validation | Cách kiểm tra kết nối còn sử dụng được |

Nếu một job chạy 8 worker test và mỗi worker tạo pool tối đa 10 kết nối, một job có thể mở tới 80 kết nối. Nếu có 4 job tương tự chạy đồng thời, tổng tiềm năng là 320 kết nối. Con số này có thể vượt xa giới hạn database.

### 6.2. Tính tổng kết nối từ pipeline

Một công thức đơn giản để lập ngân sách:

~~~text
N_total = N_jobs * N_workers_per_job * N_pool_per_worker + N_other
~~~

Trong đó N_other là kết nối từ ứng dụng, monitoring, migration, người vận hành và các dịch vụ khác.

Ví dụ database có giới hạn 500 connection. Nhóm dành 100 connection cho ứng dụng và vận hành, 50 connection dự phòng, còn 350 connection cho CI. Nếu mỗi integration test job có 5 worker và mỗi worker pool tối đa 5 connection, mỗi job có thể dùng 25 connection. Mức job đồng thời tối đa theo giới hạn này là:

~~~text
floor(350/25) = 14
~~~

Không nên sử dụng hết 14 slot theo lý thuyết nếu tải thực tế biến động. Hãy giữ headroom cho kết nối đột biến và các thao tác quản trị.

Nếu connection pool được tạo ở cấp process thay vì mỗi worker, hãy dùng cấu trúc pool thực tế để tính. Công thức chỉ là khung ước lượng; cần đo số kết nối thật tại database hoặc proxy.

### 6.3. HTTP client và giới hạn theo host

HTTP client cũng nên tái sử dụng connection thông qua keep-alive và giới hạn số kết nối đồng thời. Một pipeline có thể gọi cùng lúc nhiều request đến package registry hoặc API của cloud provider. Nếu số request vượt giới hạn phía server, hệ thống có thể trả HTTP 429 (Too Many Requests), 503 hoặc đóng kết nối.

Cần cấu hình:

- Số connection tối đa tổng thể và theo từng host.
- Số request đồng thời.
- Thời gian chờ lấy connection từ pool.
- Connection idle timeout và keep-alive.
- Request deadline.
- Giới hạn retry và cách xử lý Retry-After nếu dịch vụ trả về.

Không nên tăng connection pool chỉ để giảm thời gian chờ mà chưa đo tải phía server. Một pool quá lớn có thể làm tăng tranh chấp và khiến dịch vụ phụ thuộc quá tải nhanh hơn.

## 7. Retry, backoff và rate limit

Retry có thể giúp vượt qua lỗi tạm thời như timeout ngắn, connection reset hoặc HTTP 503. Tuy nhiên, retry không phải giải pháp cho mọi lỗi.

**Nên cân nhắc retry khi:**

- Lỗi có khả năng tạm thời.
- Thao tác có thể lặp lại an toàn hoặc có idempotency key.
- Còn thời gian trong deadline tổng.
- Dịch vụ cho phép retry và không có chỉ dẫn khác.

**Không nên retry mù quáng khi:**

- Lỗi xác thực hoặc phân quyền (401, 403).
- Request sai dữ liệu (400, 422).
- Thao tác có tác dụng phụ chưa rõ trạng thái.
- Dịch vụ đang trả rate limit và chưa đến thời điểm được phép thử lại.
- Deadline tổng đã hết.

Dùng exponential backoff để tăng dần thời gian chờ giữa các lần thử. Thêm jitter ngẫu nhiên để nhiều job không cùng retry tại một thời điểm:

~~~text
delay_n = min(delay_max, delay_base * 2^n) + jitter
~~~

Số lần retry cần giới hạn. Nếu 100 job cùng gặp lỗi và tất cả retry sau đúng 1 giây, hệ thống có thể tiếp tục bị dồn tải. Jitter giúp phân tán các lần thử.

Với HTTP 429, cần tôn trọng Retry-After nếu có. Rate limit có thể tính theo token, request, user, IP, repository hoặc project; hãy kiểm tra chính sách của dịch vụ. Một job nên log số lần retry và thời gian chờ để có thể phân tích.

Không retry thao tác deploy hoặc publish một cách tùy tiện nếu không biết lần gọi trước đã thành công hay chưa. Hãy kiểm tra trạng thái tài nguyên, dùng request idempotent hoặc truy vấn lại theo định danh artifact/release trước khi gửi lại.

## 8. Tài nguyên của dịch vụ phụ trợ trong integration test

Integration test thường khởi động database, message broker, cache hoặc service container. Các tài nguyên này cũng có giới hạn riêng và cần được quản lý cùng runner.

Một số nguyên tắc:

- Khởi động đúng số service cần cho test; không chạy bản sao không cần thiết.
- Dùng dữ liệu riêng cho mỗi test suite hoặc worker để tránh xung đột.
- Đóng connection, thread, file và container sau khi test kết thúc.
- Đặt timeout cho health check và startup.
- Giới hạn CPU/RAM cho service container nếu runtime hỗ trợ.
- Dọn volume và network tạm thời theo chính sách.
- Tránh chạy migration phá hủy trên database dùng chung.
- Dùng database hoặc namespace riêng cho các job chạy song song.

Nếu nhiều job dùng chung một database test, hãy xem xét giới hạn concurrency hoặc tạo schema/database riêng theo run ID. Một job bị treo không nên giữ lock hoặc transaction mở vô thời hạn. Test framework cần timeout cho test case và teardown để giải phóng tài nguyên.

Dịch vụ phụ trợ cũng có thể là điểm nghẽn. Nếu runner có 16 core nhưng database test chỉ chịu được 4 job đồng thời, tăng test parallelism có thể làm tổng thời gian dài hơn vì contention, lock và connection wait.

## 9. Disk, cache và artifact cũng cần giới hạn

Dung lượng đĩa thường bị bỏ qua cho đến khi runner hết chỗ. Checkout nhiều repository, cache dependency, Docker layer, test report và artifact có thể tích lũy nhanh.

Nên kiểm soát:

- Kích thước workspace và số lần checkout.
- Dung lượng cache và thời hạn lưu.
- Số lượng Docker image/layer giữ lại.
- Kích thước artifact và retention policy.
- Log lớn hoặc test output lặp lại.
- Dữ liệu test và file tạm cần xóa sau job.

Cache giúp giảm thời gian tải dependency, nhưng cache không phải nơi lưu trữ artifact phát hành. Không cache secret, token hoặc dữ liệu nhạy cảm. Cache key nên phản ánh dependency lockfile và nền tảng phù hợp để tránh dùng lại cache sai phiên bản.

Artifact phát hành cần retention đủ lâu để hỗ trợ triển khai, rollback và kiểm toán. Dung lượng artifact storage và thời gian lưu nên được tính vào quota của nền tảng.

## 10. Quan sát và chẩn đoán tình trạng quá tải

Không thể quản lý tốt nếu chỉ nhìn trạng thái thành công/thất bại. Cần theo dõi các chỉ số ở cả runner, job và dịch vụ phụ thuộc.

| Chỉ số | Điều cần tìm |
|---|---|
| Queue wait time | Job chờ runner lâu hay không |
| Job duration | Thời gian chạy thay đổi bất thường |
| CPU utilization | CPU bão hòa hoặc throttling |
| Memory peak / OOM | RAM chạm giới hạn |
| Disk usage | Workspace hoặc cache tăng bất thường |
| Network throughput | Tải dependency hoặc upload bị nghẽn |
| Connection pool wait | Job chờ connection lâu |
| Active connections | Số kết nối tiến gần giới hạn dịch vụ |
| HTTP 429/5xx | Rate limit hoặc dịch vụ quá tải |
| Timeout/retry rate | Lỗi tạm thời tăng hay timeout cấu hình không phù hợp |
| Cancellation rate | Job bị hủy thường xuyên, có thể do concurrency hoặc timeout |

Khi job chậm, hãy đối chiếu thời gian chờ queue với thời gian thực thi. Queue wait cao có thể là thiếu runner hoặc concurrency quota; execution time cao có thể do job nặng hoặc dịch vụ phụ thuộc chậm.

Khi nhiều job cùng timeout ở một endpoint, hãy điều tra endpoint và giới hạn kết nối trước khi tăng timeout cho tất cả. Khi OOM xảy ra, cần xác định process nào dùng RAM, mức peak, số worker và container limit. Khi disk đầy, kiểm tra cache, Docker layer, artifact và file tạm.

Log nên có run ID, job ID, endpoint/service name, thời lượng, số lần retry và loại lỗi. Không ghi credential hoặc nội dung nhạy cảm khi thêm thông tin chẩn đoán.

## 11. Ví dụ thiết kế ngân sách cho một pipeline

Giả sử một dịch vụ Java có pipeline gồm verify, integration test, package và publish. Nhóm dùng runner 8 vCPU, 16 GiB RAM và một database test có giới hạn 200 connection.

Một cấu hình ngân sách minh họa:

| Job | CPU dự kiến | RAM dự kiến | Timeout | Kết nối DB tối đa |
|---|---:|---:|---:|---:|
| Lint + unit test | 2 vCPU | 3 GiB | 10 phút | 0 |
| Integration test | 2 vCPU | 4 GiB | 20 phút | 20 |
| Package | 3 vCPU | 5 GiB | 12 phút | 0 |
| Publish | 1 vCPU | 1 GiB | 8 phút | 0 |

Giả sử nhóm giữ lại 40 connection cho dịch vụ khác và 20 connection dự phòng. Database còn 140 connection cho integration test. Nếu mỗi job dùng tối đa 20 connection, có thể cho phép tối đa 7 integration test job đồng thời theo giới hạn database. Tuy nhiên, runner và quota có thể giới hạn thấp hơn.

Nhóm có thể quyết định chỉ cho tối đa 2 integration test job chạy trên một runner 8 vCPU/16 GiB, sau đó đo thời gian thực tế. Nếu muốn chạy nhiều hơn, có thể thêm runner hoặc database capacity sau khi xác nhận các giới hạn khác.

Một thiết kế hợp lý sẽ:

1. Chạy lint và unit test sớm vì ít phụ thuộc dịch vụ.
2. Giới hạn integration test theo số connection và tài nguyên database.
3. Chạy package sau khi test bắt buộc đạt.
4. Publish với concurrency thấp và retry có giới hạn.
5. Đặt timeout riêng cho từng job và cho request đến registry.
6. Lưu log, báo cáo và metric để điều chỉnh ngân sách.

Các con số trong ví dụ chỉ minh họa phương pháp. Cần đo tải thật, peak memory, connection count và thời gian chạy trước khi dùng làm cấu hình production.

## 12. Checklist vận hành môi trường thực thi

Trước khi đưa pipeline vào sử dụng hoặc tăng mức song song, hãy kiểm tra:

- [ ] Đã xác định CPU, RAM, disk, I/O và network cần cho từng loại job.
- [ ] Request và limit phù hợp với mức sử dụng thực tế.
- [ ] Có tài nguyên dự phòng cho runner và tiến trình nền.
- [ ] Mức concurrency không vượt năng lực runner, dịch vụ phụ thuộc và quota.
- [ ] Job có timeout tổng; các thao tác mạng và test quan trọng có timeout riêng.
- [ ] Timeout được chọn từ số liệu thực tế và có ngân sách cho cleanup.
- [ ] Connection pool có giới hạn và đã tính tổng trên mọi job/worker.
- [ ] HTTP client có connection limit, request deadline và keep-alive phù hợp.
- [ ] Retry có giới hạn, backoff, jitter và tôn trọng Retry-After.
- [ ] Thao tác có tác dụng phụ được thiết kế idempotent hoặc có bước xác minh trạng thái.
- [ ] Integration test giải phóng connection, container, lock và dữ liệu tạm.
- [ ] Cache, log và artifact có giới hạn dung lượng và retention.
- [ ] Có metric cho queue wait, job duration, CPU, RAM, disk, connection và timeout.
- [ ] Có cách dừng hoặc giảm tải an toàn khi dịch vụ phụ thuộc quá tải.

Quản lý tài nguyên, timeout và kết nối là một phần của thiết kế pipeline, không phải bước tinh chỉnh sau cùng. Khi ngân sách được xác định theo từng job, mức song song được giới hạn theo năng lực thật và mỗi thao tác có deadline rõ ràng, pipeline sẽ ổn định hơn, dễ dự đoán chi phí và ít gây ảnh hưởng đến các hệ thống dùng chung.

