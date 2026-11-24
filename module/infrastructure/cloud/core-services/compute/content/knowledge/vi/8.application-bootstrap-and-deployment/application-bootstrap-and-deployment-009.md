# Graceful shutdown và hoàn tất tác vụ trước khi máy bị thu hồi

Trong môi trường cloud, một máy ảo hoặc container có thể phải dừng bất cứ lúc nào do triển khai phiên bản mới, scale-in, bảo trì host, lỗi hạ tầng hoặc thu hồi tài nguyên có thể bị gián đoạn. Nếu tiến trình bị tắt đột ngột khi đang xử lý yêu cầu hay ghi dữ liệu, ứng dụng có thể làm mất công việc, tạo giao dịch dở dang hoặc khiến thông điệp được xử lý lặp lại.

**Graceful shutdown** là quy trình dừng có kiểm soát: ứng dụng ngừng nhận công việc mới, cho các yêu cầu đang chạy hoàn tất trong giới hạn thời gian, lưu trạng thái cần thiết, đóng kết nối và thoát đúng cách. Với workload có thể bị thu hồi, ứng dụng còn cần nhận biết tín hiệu hoặc thông báo sắp dừng, chủ động bảo toàn tiến độ và sẵn sàng tiếp tục trên một máy khác.

Bài học thuộc module **CLOUD_CORE_SERVICES_COMPUTE**, tập trung vào cách thiết kế vòng đời ứng dụng để hoàn tất tác vụ trước khi VM hoặc container bị dừng. Nội dung áp dụng cho API, worker hàng đợi, batch job, streaming consumer và dịch vụ chạy dài hạn trên máy ảo hoặc nền tảng container.

## 1. Vì sao máy tính toán có thể bị dừng?

Một workload không nên giả định rằng máy chủ sẽ tồn tại mãi. Các tình huống thường gặp gồm:

| Tình huống | Điều gì xảy ra | Yêu cầu đối với ứng dụng |
|---|---|---|
| Scale-in | Auto Scaling giảm số máy khi nhu cầu tải giảm | Ngừng nhận tải mới và drain các yêu cầu đang xử lý |
| Spot/preemptible eviction | Nhà cung cấp thu hồi tài nguyên có thể bị gián đoạn | Nhận thông báo sớm nếu có, lưu checkpoint và kết thúc nhanh |
| Rolling deployment | Bản cũ được thay thế bằng bản mới | Dừng nhận request, hoàn tất request đang chạy và thoát sạch |
| Host maintenance | VM được di chuyển, khởi động lại hoặc dừng để bảo trì | Chấp nhận gián đoạn theo thông báo và phục hồi từ trạng thái bền vững |
| Lỗi hệ điều hành hoặc tiến trình | Máy hoặc ứng dụng không thể tiếp tục hoạt động bình thường | Dựa vào timeout, lease, retry và phục hồi ở cấp ứng dụng |
| Người vận hành chủ động dừng | VM được tắt hoặc xóa theo lịch | Thực hiện quy trình drain, backup hoặc checkpoint trước khi dừng |

Spot hoặc preemptible VM thường có giá thấp hơn vì nhà cung cấp có quyền thu hồi năng lực khi cần. Cơ chế thông báo và thời gian báo trước khác nhau theo nhà cung cấp, loại tài nguyên và tình huống. Có nền tảng cung cấp interruption notice hoặc sự kiện metadata; có tình huống máy có thể dừng nhanh hơn dự kiến. Không được thiết kế ứng dụng dựa trên một khoảng thời gian báo trước cố định cho mọi cloud.

Ngay cả VM thông thường cũng có thể gặp lỗi đột ngột. Vì vậy, graceful shutdown làm giảm mất mát khi có thời gian chuẩn bị, còn khả năng phục hồi sau sự cố bất ngờ vẫn phải được thiết kế riêng.

## 2. Graceful shutdown là gì?

Graceful shutdown là chuỗi bước giúp ứng dụng dừng ở một ranh giới an toàn. Thay vì kết thúc tiến trình ngay khi nhận tín hiệu, ứng dụng chuyển sang trạng thái **đang dừng** và phối hợp với load balancer, hệ điều phối, hàng đợi và các dịch vụ phụ thuộc.

Một quy trình điển hình:

1. Nhận tín hiệu dừng hoặc thông báo thu hồi.
2. Đánh dấu instance không còn sẵn sàng nhận công việc mới.
3. Ngừng nhận request, message hoặc batch mới.
4. Chờ request và tác vụ đang chạy hoàn tất trong thời gian cho phép.
5. Lưu checkpoint hoặc trả công việc chưa hoàn tất về hàng đợi theo giao thức.
6. Ghi dữ liệu bền vững, flush buffer và đóng giao dịch.
7. Đóng connection pool, consumer, listener và các tài nguyên khác.
8. Ghi log trạng thái cuối cùng rồi thoát với mã phù hợp.

~~~mermaid
sequenceDiagram
    participant P as Cloud / Orchestrator
    participant L as Load Balancer / Queue
    participant A as Application
    participant D as Database / Storage
    P->>A: Gửi tín hiệu hoặc thông báo dừng
    A->>A: Chuyển sang trạng thái draining
    A->>L: Báo không nhận thêm request hoặc message
    L-->>A: Ngừng phân phối công việc mới
    A->>A: Hoàn tất request và job đang chạy
    A->>D: Commit dữ liệu hoặc lưu checkpoint
    D-->>A: Xác nhận ghi bền vững
    A->>A: Đóng kết nối và tài nguyên
    A-->>P: Thoát trước deadline
~~~

Thứ tự có thể thay đổi theo loại workload. Ví dụ, API cần được loại khỏi luồng phân phối request trước khi chờ request đang chạy; worker hàng đợi cần dừng polling trước khi hoàn tất job hiện tại. Mục tiêu chung là không nhận thêm việc sau khi bắt đầu dừng và không đánh dấu công việc hoàn tất trước khi kết quả đã được lưu an toàn.

## 3. Tín hiệu dừng và deadline

Ứng dụng cần biết khi nào phải bắt đầu shutdown. Tín hiệu thường gặp:

- **SIGTERM:** yêu cầu tiến trình kết thúc có kiểm soát trên Unix/Linux và nhiều runtime container.
- **SIGINT:** thường phát sinh khi người dùng hoặc terminal yêu cầu ngắt tiến trình.
- **Service control:** trên Windows, Service Control Manager gửi yêu cầu dừng tới Windows Service.
- **Orchestrator lifecycle event:** nền tảng điều phối thông báo pod, task hoặc instance sẽ bị thay thế.
- **Cloud interruption notice:** nhà cung cấp báo trước khi thu hồi Spot/preemptible instance nếu tình huống hỗ trợ.
- **Application endpoint hoặc admin command:** hệ thống quản trị gọi API nội bộ để bắt đầu drain.

Không nên chỉ dựa vào tín hiệu từ một nguồn. Ví dụ, ứng dụng có thể nhận SIGTERM khi triển khai nhưng nhận sự kiện metadata khi Spot VM bị thu hồi. Nên gom các sự kiện này về cùng một hàm chuyển trạng thái sang draining.

### 3.1. Thời gian shutdown có giới hạn

Hệ điều hành hoặc nền tảng điều phối thường chỉ chờ trong một khoảng thời gian. Nếu ứng dụng chưa thoát khi hết hạn, hệ thống có thể kết thúc cưỡng bức tiến trình hoặc VM. Vì thế, graceful shutdown phải có deadline.

Gọi:

- T_n: thời gian ngừng nhận tải và cập nhật trạng thái.
- T_f: thời gian tối đa dành cho request/job đang chạy.
- T_p: thời gian ghi checkpoint hoặc hoàn tất dữ liệu.
- T_c: thời gian đóng kết nối và thoát.
- T_g: khoảng dự phòng để xử lý biến động.
- T_d: tổng thời gian được cấp trước khi bị kết thúc cưỡng bức.

Thiết kế cần bảo đảm:

\[
T_n + T_f + T_p + T_c + T_g < T_d
\]

Đây là ngân sách thời gian, không phải thời gian chờ cố định bắt buộc. Cần đo thời gian thực tế của request/job, chọn giới hạn phù hợp và giữ phần dự phòng cho lúc hệ thống bận. Nếu một job thường kéo dài hàng chục phút nhưng máy chỉ được báo trước vài chục giây, không thể trông chờ job hoàn tất; phải chia nhỏ công việc, lưu checkpoint thường xuyên hoặc chọn compute phù hợp hơn.

### 3.2. Hai lớp timeout

Nên có ít nhất hai giới hạn:

- **Application deadline:** ứng dụng tự giới hạn thời gian chờ request, job, flush dữ liệu và shutdown.
- **Platform termination deadline:** giới hạn mà hệ điều hành, container runtime hoặc cloud provider áp dụng.

Application deadline phải ngắn hơn platform deadline để ứng dụng có thời gian đóng sạch. Nếu hai giới hạn bằng nhau, tiến trình có thể bị kill trước khi hoàn tất cleanup.

## 4. Ngừng nhận tải và drain kết nối

Một API có thể đang xử lý request trong khi load balancer tiếp tục gửi request mới. Nếu tiến trình bị dừng ngay, các request mới và request đang chạy đều có nguy cơ thất bại.

Quy trình drain cho dịch vụ tương tác thường gồm:

1. Đánh dấu instance là draining hoặc not ready.
2. Ngừng nhận kết nối mới hoặc ngừng quảng bá endpoint.
3. Chờ load balancer và service discovery cập nhật.
4. Tiếp tục xử lý request đã nhận trong giới hạn thời gian.
5. Trả response hoặc đóng kết nối theo giao thức.
6. Thoát khi không còn request đang chạy hoặc hết deadline.

Readiness và liveness có ý nghĩa khác nhau. Readiness cho biết instance có nên nhận traffic hay không; liveness cho biết tiến trình có còn hoạt động và cần được khởi động lại hay không. Khi bắt đầu shutdown, nên chuyển readiness sang false. Không nên làm liveness thất bại chỉ để drain, vì orchestrator có thể restart tiến trình theo cách không mong muốn.

### 4.1. HTTP keep-alive và request đang chạy

HTTP keep-alive cho phép tái sử dụng kết nối. Khi shutdown, server cần ngừng nhận request mới trên listener, xử lý các request đã được chấp nhận và đóng socket đúng cách. Với HTTP/2 hoặc WebSocket, cần xử lý stream hoặc kết nối dài hạn theo giao thức; không nên cắt socket mà không thông báo nếu có thể gửi tín hiệu đóng phù hợp.

Đối với request mất nhiều thời gian, có thể cần deadline ở tầng ứng dụng và cơ chế client retry. Retry chỉ an toàn khi request có idempotency key hoặc thao tác có thể thực hiện lặp lại mà không tạo giao dịch trùng.

### 4.2. Tránh nhận traffic trong thời gian load balancer cập nhật

Thay đổi readiness hoặc deregister khỏi load balancer có thể cần thời gian lan truyền. Ứng dụng nên có một khoảng drain phù hợp với cơ chế của nền tảng. Nếu dừng listener quá sớm, request đã được định tuyến có thể bị reset; nếu chờ quá lâu, ứng dụng có thể vượt shutdown deadline.

Hãy kiểm thử thời gian từ lúc đánh dấu unhealthy/not-ready đến khi request mới thực sự ngừng đến. Không mặc định mọi load balancer, service mesh hoặc DNS resolver cập nhật tức thời.

## 5. Hoàn tất tác vụ của worker và hàng đợi

Worker xử lý message thường có thể bị dừng khi đang thực hiện một job. Cần phân biệt ba trạng thái:

- **Đã nhận:** worker đã lấy message hoặc lease công việc.
- **Đang xử lý:** kết quả chưa được xác nhận bền vững.
- **Đã hoàn tất:** kết quả đã được ghi an toàn và message được acknowledge.

Quy tắc quan trọng: **chỉ acknowledge sau khi kết quả đã được lưu bền vững**. Nếu acknowledge trước rồi worker bị kill khi ghi dữ liệu, message đã biến mất nhưng công việc chưa hoàn thành. Nếu ghi dữ liệu xong rồi worker bị kill trước acknowledge, message có thể được giao lại; do đó, thao tác cần idempotent.

### 5.1. Dừng polling trước, hoàn tất job hiện tại sau

Khi nhận tín hiệu shutdown, worker nên:

1. Ngừng gọi receive/poll để không lấy thêm message.
2. Giữ lease hoặc visibility timeout cho job hiện tại trong giới hạn hợp lý.
3. Hoàn tất job nếu có thể trước deadline.
4. Commit kết quả và chỉ sau đó acknowledge.
5. Nếu không thể hoàn tất, lưu checkpoint hoặc trả job về queue theo giao thức.
6. Đóng consumer và connection.

Nếu queue hỗ trợ visibility timeout, thời hạn này phải đủ dài cho xử lý bình thường hoặc được gia hạn có kiểm soát. Khi worker dừng, lease có thể hết hạn để worker khác nhận lại. Không nên giữ lease vô thời hạn hoặc gia hạn sau khi ứng dụng đã không còn khả năng hoàn tất.

### 5.2. Idempotency và xử lý trùng lặp

Nhiều hệ thống queue cung cấp giao nhận at-least-once: message có thể được giao nhiều lần nếu worker mất kết nối hoặc không acknowledge kịp. Vì vậy, worker cần idempotency:

- Mỗi job có một ID duy nhất hoặc idempotency key.
- Lưu trạng thái xử lý trong database hoặc kho bền vững.
- Dùng transaction để cập nhật kết quả và trạng thái công việc khi có thể.
- Kiểm tra job đã hoàn tất trước khi tạo hiệu ứng phụ lần nữa.
- Dùng unique constraint hoặc conditional write để ngăn ghi trùng.

Không nên giả định rằng graceful shutdown có thể bảo đảm exactly-once processing. Exactly-once là thuộc tính phức tạp của toàn bộ pipeline; thông thường phải kết hợp idempotency, transaction, checkpoint và giao thức của hệ thống truyền nhận.

### 5.3. Ví dụ worker Python

Đoạn mã dưới đây minh họa ý tưởng dừng polling, hoàn tất job đang chạy trong giới hạn và acknowledge sau khi xử lý thành công. Các hàm queue và process_job là adapter giả định cần được thay bằng thư viện thực tế.

~~~python
import asyncio
import signal

stop_requested = asyncio.Event()
MAX_JOB_SECONDS = 40

async def handle_one_job(queue, job):
    try:
        # Giới hạn thời gian xử lý để phù hợp shutdown budget.
        result = await asyncio.wait_for(
            process_job(job),
            timeout=MAX_JOB_SECONDS,
        )
        # Chỉ acknowledge sau khi kết quả đã được lưu bền vững.
        await persist_result(job.id, result)
        await queue.ack(job)
    except Exception:
        # Retry/release phải tuân theo semantics của queue.
        await queue.retry_or_release(job)

async def run_worker(queue):
    while not stop_requested.is_set():
        job = await queue.receive(timeout=1)
        if job is None:
            continue

        # Nếu tín hiệu dừng đến trong lúc receive, trả job lại thay vì bắt đầu xử lý.
        if stop_requested.is_set():
            await queue.release(job)
            break

        await handle_one_job(queue, job)

        # Nếu shutdown đến trong lúc xử lý, kết thúc vòng lặp tại đây.
        if stop_requested.is_set():
            break

    await queue.close()

def request_shutdown():
    stop_requested.set()

async def main(queue):
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, request_shutdown)
    loop.add_signal_handler(signal.SIGINT, request_shutdown)
    await run_worker(queue)
~~~

Trong ứng dụng thực tế, cần xử lý riêng cancellation, lỗi khi persist, lỗi khi ack và thời gian đóng queue. MAX_JOB_SECONDS phải được chọn theo thời gian dừng của nền tảng; nếu job dài hơn ngân sách, cần checkpoint hoặc chia nhỏ job thay vì chỉ tăng timeout. Cách đăng ký signal ở ví dụ phù hợp với event loop chạy trên nền tảng Unix; Windows cần cơ chế signal hoặc service control tương ứng.

## 6. Checkpoint cho tác vụ dài

Một job batch có thể kéo dài lâu hơn thời gian báo trước khi máy bị thu hồi. Khi đó, cần lưu tiến độ theo checkpoint để máy mới có thể tiếp tục.

Checkpoint có thể chứa:

- ID job và phiên bản thuật toán.
- Vị trí đã xử lý, chẳng hạn offset, số bản ghi hoặc tên partition.
- Trạng thái trung gian cần thiết để tiếp tục.
- Thời điểm và phiên bản dữ liệu đầu vào.
- Thông tin kiểm tra tính toàn vẹn.

Checkpoint cần được ghi vào nơi bền vững như database hoặc object storage. Không nên chỉ lưu trong RAM hoặc ổ đĩa tạm của VM có thể bị thu hồi.

### 6.1. Tần suất checkpoint

Checkpoint quá thường xuyên làm tăng I/O và chi phí; checkpoint quá thưa làm tăng lượng công việc phải chạy lại khi có sự cố. Có thể xác định chu kỳ dựa trên:

- Thời gian xử lý giữa hai checkpoint.
- Chi phí ghi và kích thước checkpoint.
- Mức mất tiến độ tối đa chấp nhận được.
- Xác suất gián đoạn và thời gian phục hồi.

Với job có thể chia thành các partition độc lập, lưu tiến độ theo partition giúp worker khác tiếp tục phần chưa hoàn tất. Khi ghi checkpoint, nên dùng thao tác atomic hoặc versioned write để tránh trạng thái nửa chừng.

### 6.2. Tránh checkpoint không nhất quán

Checkpoint và dữ liệu đầu ra phải phản ánh cùng một tiến độ. Nếu checkpoint ghi trước nhưng output chưa được lưu, lần chạy sau có thể bỏ qua dữ liệu chưa tạo. Nếu output ghi xong nhưng checkpoint chưa cập nhật, job có thể chạy lại phần đó. Hãy dùng transaction, commit marker, idempotent output hoặc giao thức hai pha phù hợp để xử lý tình huống này.

## 7. Graceful shutdown trên Linux và Windows

### 7.1. Linux và systemd

Trên Linux, SIGTERM thường là tín hiệu yêu cầu tiến trình kết thúc có kiểm soát. Ứng dụng nên đăng ký signal handler, ngừng nhận việc mới, đợi tác vụ đang chạy và đóng tài nguyên. SIGKILL không thể bị bắt hoặc xử lý; nếu tiến trình còn chạy sau deadline, hệ thống có thể dùng SIGKILL để kết thúc.

Với dịch vụ systemd, có thể cấu hình thời gian chờ dừng:

~~~ini
[Unit]
Description=Catalog background worker
After=network-online.target

[Service]
Type=simple
User=catalog
ExecStart=/opt/catalog/bin/worker
Restart=on-failure
KillSignal=SIGTERM
TimeoutStopSec=55s

[Install]
WantedBy=multi-user.target
~~~

TimeoutStopSec là ví dụ cấu hình cho service systemd. Ứng dụng phải tự hoàn tất shutdown trong khoảng thời gian này; nếu không, systemd có thể kết thúc tiến trình theo chính sách kill của service. Cần đặt timeout phù hợp với deadline của VM hoặc container bên ngoài. Timeout ở lớp trong không thể kéo dài thời gian mà cloud provider cho phép máy tồn tại.

Các bước kiểm tra service:

~~~bash
# Xem trạng thái dịch vụ
systemctl status catalog-worker

# Gửi yêu cầu dừng mềm
systemctl stop catalog-worker

# Xem log trong lúc dừng
journalctl -u catalog-worker --since "10 minutes ago"
~~~

Không dùng kill -9 như cách dừng bình thường vì SIGKILL bỏ qua cleanup.

### 7.2. Windows Service

Windows Service nhận yêu cầu dừng qua Service Control Manager (SCM), thường là SERVICE_CONTROL_STOP. Service nên chuyển sang trạng thái stop pending, ngừng nhận việc mới, hoàn tất tác vụ đang chạy, lưu dữ liệu và báo trạng thái stopped khi kết thúc.

Với tác vụ cleanup dài, Windows có cơ chế preshutdown notification cho service được cấu hình hỗ trợ. Thời gian chờ preshutdown và timeout của SCM phải được phối hợp với quy trình dừng của máy và nền tảng cloud. Không nên giả định một service luôn được cấp thời gian vô hạn để kết thúc.

Các điểm cần triển khai:

- Xử lý stop control và hủy listener/consumer mới.
- Đặt deadline cho request hoặc job đang chạy.
- Dùng cancellation token hoặc cơ chế tương đương để truyền tín hiệu dừng xuống các thành phần.
- Flush log và dữ liệu quan trọng.
- Đóng database connection, thread, timer và handle.
- Ghi event log nếu shutdown thất bại hoặc hết thời gian.

PowerShell có thể gửi lệnh dừng service:

~~~powershell
# Xem trạng thái service
Get-Service -Name "CatalogWorker"

# Yêu cầu dừng service
Stop-Service -Name "CatalogWorker"

# Xác minh service đã dừng
Get-Service -Name "CatalogWorker"
~~~

Đây là lệnh quản trị minh họa; tài khoản thực thi cần quyền phù hợp và service phải triển khai handler dừng có kiểm soát.

## 8. Graceful shutdown trong container và Kubernetes

Container runtime và orchestrator có vòng đời riêng. Khi dừng container, runtime thường gửi tín hiệu kết thúc tới tiến trình chính (PID 1), chờ trong một khoảng thời gian rồi mới kết thúc cưỡng bức nếu tiến trình chưa thoát. Tín hiệu mặc định và thời gian chờ có thể cấu hình theo runtime.

Ứng dụng trong container cần:

- Chạy tiến trình chính trực tiếp hoặc dùng init phù hợp để chuyển tiếp signal.
- Bắt SIGTERM và thực hiện cleanup.
- Không để shell wrapper giữ signal mà không chuyển tiếp đến ứng dụng.
- Có readiness endpoint hoặc cơ chế tương đương để drain.
- Đặt thời gian shutdown phù hợp với giới hạn của orchestrator.

### 8.1. Kubernetes termination flow

Khi Pod bị xóa hoặc thay thế, Kubernetes đánh dấu Pod đang terminating, cập nhật EndpointSlice để ngừng đưa Pod vào các endpoint sẵn sàng mới, chạy preStop hook nếu có, gửi tín hiệu dừng tới container và chờ hết terminationGracePeriodSeconds. Nếu container vẫn chưa thoát khi hết thời gian, runtime có thể gửi SIGKILL.

Việc cập nhật endpoint và phân phối mạng có độ trễ. Ứng dụng vẫn cần xử lý request đã được chuyển tới trong lúc thay đổi lan truyền.

Ví dụ Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: api
          image: registry.example/catalog-api:v2
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /ready
              port: http
          livenessProbe:
            httpGet:
              path: /health
              port: http
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
~~~

Ví dụ này minh họa khoảng grace period 60 giây và một preStop hook ngắn. sleep không tự drain request; ứng dụng vẫn phải xử lý SIGTERM và đóng server đúng cách. Hook cũng tiêu thụ thời gian trong grace period, nên không được cộng thêm thời gian hook bên ngoài ngân sách đã cấu hình. Trong production, nên dùng endpoint drain hoặc hành vi ứng dụng phù hợp thay vì dựa vào sleep cố định.

### 8.2. Shutdown budget trong Kubernetes

Giả sử Pod có terminationGracePeriodSeconds là 60 giây. Có thể phân bổ một phần thời gian cho endpoint drain, phần còn lại cho request đang chạy và cleanup. Giá trị cụ thể phải được đo theo ứng dụng. Nếu preStop dùng 10 giây, ứng dụng còn ít thời gian hơn để xử lý request sau khi nhận SIGTERM.

Không nên để livenessProbe thất bại ngay khi Pod bắt đầu terminating. Readiness nên loại Pod khỏi traffic; liveness nên tiếp tục phản ánh sức khỏe tiến trình trong thời gian nó đang hoàn tất công việc.

## 9. Thu hồi Spot/preemptible VM

Spot hoặc preemptible VM có thể bị thu hồi khi nhà cung cấp cần tài nguyên. Một số nền tảng cung cấp sự kiện hoặc thông báo trước qua API, metadata endpoint, event service hoặc notification channel.

Thiết kế ứng dụng nên theo các nguyên tắc:

1. Có thành phần theo dõi interruption notice theo đúng tài liệu nhà cung cấp.
2. Khi nhận notice, chuyển ứng dụng sang draining ngay.
3. Ngừng nhận job mới hoặc deregister khỏi load balancer.
4. Lưu checkpoint và hoàn tất tác vụ có thể kết thúc trong ngân sách.
5. Đưa công việc chưa hoàn tất về hàng đợi hoặc để lease hết hạn theo cơ chế an toàn.
6. Ghi nhận lý do dừng và trạng thái checkpoint để instance mới tiếp tục.
7. Dùng fleet hoặc nhóm instance thay thế để duy trì năng lực phục vụ.

Không nên để logic ứng dụng phụ thuộc trực tiếp vào một endpoint metadata cụ thể nếu muốn chạy đa cloud. Có thể xây dựng một adapter phát ra sự kiện nội bộ như ShutdownRequested(reason, deadline), rồi triển khai adapter riêng cho từng nền tảng.

### 9.1. Ví dụ giao diện sự kiện nội bộ

~~~text
ShutdownRequested
  reason: "spot-interruption" | "scale-in" | "deployment" | "maintenance"
  deadline: timestamp
  source: "cloud-event" | "signal" | "orchestrator" | "operator"
~~~

Ứng dụng nhận sự kiện này và sử dụng cùng một quy trình shutdown. Deadline cho phép tính ngân sách còn lại thay vì giả định thời gian dừng luôn như nhau.

### 9.2. Thay thế instance và duy trì năng lực

Với API stateless, load balancer có thể chuyển traffic sang instance khác sau khi instance sắp bị thu hồi được drain. Với worker, queue giữ công việc để worker mới tiếp tục. Với batch, scheduler có thể khởi chạy job thay thế từ checkpoint.

Cần duy trì đủ capacity dự phòng hoặc khả năng khởi chạy instance mới. Graceful shutdown chỉ bảo vệ việc kết thúc một instance; nó không tự bảo đảm hệ thống còn đủ năng lực phục vụ sau khi instance bị thu hồi.

## 10. Thiết kế shutdown cho từng loại workload

| Workload | Khi bắt đầu dừng | Cách bảo toàn công việc |
|---|---|---|
| HTTP API | Đánh readiness false, ngừng nhận kết nối mới | Hoàn tất request đang chạy, đóng server |
| Worker queue | Dừng polling và nhận message mới | Hoàn tất job, commit rồi ack; hoặc release/để lease hết hạn |
| Batch job | Ngừng lấy partition hoặc bước xử lý mới | Lưu checkpoint và trạng thái output |
| Streaming consumer | Dừng nhận partition hoặc record mới | Commit offset sau khi output được lưu an toàn |
| WebSocket service | Từ chối session mới, thông báo client hiện tại | Cho client reconnect hoặc chuyển session nếu ứng dụng hỗ trợ |
| GPU job | Ngừng nhận batch mới | Lưu model/checkpoint và đồng bộ dữ liệu ra storage bền vững |
| Database | Dừng kết nối ghi mới theo quy trình database | Dùng cơ chế shutdown/replication/backup của database engine |

Database cần được xử lý đặc biệt. Không nên tự gửi kill signal cho tiến trình database thay cho quy trình shutdown chính thức. Hãy dùng cơ chế quản lý của database engine hoặc dịch vụ được quản lý, bảo đảm transaction được xử lý và dữ liệu có thể phục hồi.

## 11. Quan sát và ghi nhận quá trình shutdown

Không thể cải thiện shutdown nếu không biết ứng dụng mất bao lâu và thường thất bại ở bước nào. Nên ghi log có cấu trúc và metric cho các giai đoạn:

- Thời điểm nhận tín hiệu shutdown và nguồn phát tín hiệu.
- Thời gian chuyển readiness sang false hoặc deregister khỏi load balancer.
- Số request/job đang chạy khi bắt đầu dừng.
- Số request/job hoàn tất, bị retry hoặc được checkpoint.
- Thời gian flush dữ liệu và đóng connection pool.
- Thời gian shutdown tổng cộng.
- Số lần bị kill cưỡng bức hoặc vượt deadline.
- Số job chạy lại, message giao trùng hoặc request thất bại quanh thời điểm deploy.

Một số metric gợi ý:

| Metric | Ý nghĩa |
|---|---|
| shutdown_started_total | Số lần ứng dụng bắt đầu shutdown |
| shutdown_duration_seconds | Thời gian từ lúc nhận tín hiệu đến khi thoát |
| shutdown_deadline_exceeded_total | Số lần vượt shutdown budget |
| inflight_requests | Request đang xử lý khi drain |
| inflight_jobs | Job đang xử lý khi shutdown |
| checkpoint_duration_seconds | Thời gian lưu checkpoint |
| jobs_retried_after_shutdown_total | Job phải chạy lại sau khi instance dừng |

Tên metric là ví dụ; cần tuân theo quy ước telemetry của hệ thống. Không ghi dữ liệu nhạy cảm, token hoặc payload đầy đủ vào log shutdown.

## 12. Kiểm thử graceful shutdown

Kiểm thử shutdown cần thực hiện trong môi trường đại diện, không chỉ kiểm tra rằng tiến trình có thể nhận SIGTERM.

Các kịch bản nên thử:

1. Dừng ứng dụng khi không có request hoặc job nào đang chạy.
2. Dừng khi có nhiều request đồng thời và kết nối keep-alive.
3. Dừng khi một job gần hoàn tất.
4. Dừng khi job vượt quá shutdown budget.
5. Dừng trong lúc ghi dữ liệu hoặc commit transaction.
6. Mất kết nối tới queue hoặc database trong lúc shutdown.
7. Gửi hai tín hiệu shutdown liên tiếp.
8. Gửi SIGKILL hoặc mô phỏng mất host để kiểm tra phục hồi bất ngờ.
9. Thực hiện rolling deployment hoặc scale-in dưới tải.
10. Mô phỏng Spot interruption và xác minh instance mới tiếp tục từ checkpoint.

Tiêu chí đạt:

- Không nhận công việc mới sau khi đã chuyển sang draining.
- Request đang chạy được hoàn tất hoặc thất bại có kiểm soát.
- Message chỉ được ack sau khi kết quả bền vững.
- Job chưa hoàn tất có thể được retry hoặc resume.
- Không có dữ liệu dở dang làm hỏng trạng thái nghiệp vụ.
- Ứng dụng thoát trước deadline trong điều kiện được hỗ trợ.
- Hệ thống duy trì đủ capacity hoặc phục hồi theo mục tiêu dịch vụ.

Phải kiểm thử cả trường hợp graceful shutdown không có cơ hội chạy. Cloud có thể mất host hoặc tiến trình bị kill đột ngột; backup, replication, queue, transaction và idempotency là lớp bảo vệ tiếp theo.

## 13. Ví dụ thực tế: worker xử lý đơn hàng

Một cửa hàng trực tuyến có nhiều worker đọc message từ queue để xử lý đơn hàng. Mỗi job gồm xác minh tồn kho, ghi trạng thái đơn hàng và yêu cầu dịch vụ thanh toán. Khi một worker nhận thông báo scale-in, nó cần dừng nhận job mới nhưng vẫn hoàn tất đơn hàng đang xử lý.

Quy trình phù hợp:

1. Worker đặt trạng thái draining và dừng polling queue.
2. Worker tiếp tục xử lý job hiện tại trong thời gian cho phép.
3. Các thao tác cập nhật đơn hàng dùng transaction hoặc idempotency key.
4. Kết quả được ghi bền vững vào database.
5. Worker acknowledge message sau khi commit thành công.
6. Worker đóng connection tới queue và database rồi thoát.
7. Nếu deadline sắp hết mà job chưa xong, worker lưu checkpoint hoặc release job để worker khác nhận lại.

Nếu worker ack ngay khi vừa nhận message, đơn hàng có thể bị bỏ dở khi máy bị thu hồi. Nếu worker commit database nhưng chưa ack, message có thể được giao lại; idempotency giúp tránh tạo thanh toán hoặc đơn hàng trùng. Đây là lý do quy trình dừng phải được thiết kế cùng với semantics của queue và database.

## 14. Checklist thiết kế

Trước khi đưa workload lên cloud, hãy xác định:

- Ứng dụng nhận tín hiệu dừng nào: SIGTERM, service control, orchestrator event hay cloud interruption notice?
- Ai chịu trách nhiệm chuyển readiness và ngừng nhận tải mới?
- Có bao nhiêu request/job có thể đang chạy đồng thời?
- Thời gian xử lý lớn nhất và shutdown deadline là bao nhiêu?
- Dữ liệu nào cần commit, flush hoặc checkpoint?
- Message được ack ở thời điểm nào? Lease/visibility timeout được quản lý ra sao?
- Job có idempotent và có thể retry an toàn không?
- Kết nối nào cần đóng và thứ tự đóng là gì?
- Có log/metric để biết shutdown thành công hay vượt deadline không?
- Đã kiểm thử rolling deployment, scale-in, interruption và mất host đột ngột chưa?

## 15. Những sai lầm thường gặp

- **Chỉ xử lý SIGTERM nhưng không drain traffic:** load balancer vẫn có thể gửi request mới trong lúc ứng dụng thoát.
- **Ack message quá sớm:** message bị xóa khỏi queue trước khi kết quả được lưu bền vững.
- **Không có idempotency:** message giao lại tạo giao dịch hoặc hiệu ứng phụ trùng lặp.
- **Job dài không có checkpoint:** máy bị thu hồi khiến toàn bộ tiến độ phải chạy lại.
- **Không đặt deadline:** cleanup kéo dài đến khi nền tảng kill tiến trình.
- **Đặt application timeout bằng platform timeout:** không còn thời gian dự phòng để đóng kết nối.
- **Coi preStop là graceful shutdown hoàn chỉnh:** hook không thay thế logic dừng bên trong ứng dụng.
- **Dùng liveness để drain:** có thể kích hoạt restart không cần thiết thay vì ngừng nhận traffic.
- **Tin rằng thông báo Spot luôn đến đúng hạn:** sự kiện có thể khác theo provider và loại lỗi.
- **Chỉ thử dừng mềm:** không kiểm tra tình huống mất điện, mất host hoặc SIGKILL.
- **Chỉ bảo vệ instance mà quên capacity:** instance thoát an toàn nhưng hệ thống vẫn thiếu năng lực phục vụ.

## 16. Ghi nhớ

Graceful shutdown giúp ứng dụng dừng có kiểm soát khi triển khai, scale-in, bảo trì hoặc thu hồi compute. Ứng dụng cần nhận tín hiệu, chuyển sang draining, ngừng nhận công việc mới, hoàn tất hoặc checkpoint công việc đang chạy, lưu dữ liệu bền vững, đóng tài nguyên và thoát trước deadline.

Đối với worker và streaming consumer, phải phối hợp checkpoint, lease, retry, commit và acknowledge. Đối với API, cần drain request và kết nối. Trên Linux, Windows và Kubernetes, cơ chế gửi tín hiệu khác nhau nhưng ứng dụng nên quy về cùng một quy trình shutdown có giới hạn thời gian. Cuối cùng, hãy kiểm thử cả shutdown mềm lẫn mất máy đột ngột để bảo đảm workload có thể tiếp tục trên compute khác mà không làm mất hoặc nhân đôi công việc.
