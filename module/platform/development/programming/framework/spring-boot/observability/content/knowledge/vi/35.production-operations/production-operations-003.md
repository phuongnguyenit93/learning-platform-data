# Quản lý secret exporter

Trong môi trường production, Spring Boot thường gửi traces, metrics hoặc logs đến một OpenTelemetry Collector hay một observability backend. Exporter có thể cần bearer token, API key, thông tin xác thực, chứng thư client hoặc private key để kết nối. Những giá trị này là secret vận hành: nếu bị lộ, người khác có thể gửi dữ liệu giả, đọc dữ liệu telemetry, tiêu tốn quota hoặc sử dụng quyền của service để truy cập hệ thống khác.

Quản lý secret exporter là một phần của thiết kế observability. Ứng dụng phải lấy thông tin xác thực từ nguồn được kiểm soát, chỉ cấp quyền cần thiết cho luồng telemetry, bảo vệ kết nối, hỗ trợ xoay vòng và tránh đưa secret vào logs, traces, metrics hay kho mã nguồn. Các nguyên tắc này áp dụng cho cả Micrometer Observation, Micrometer Tracing, Micrometer registry và OpenTelemetry exporter trong Spring Boot.

## 1. Xác định secret nào được exporter sử dụng

Trước khi cấu hình, hãy lập danh sách các kết nối telemetry và thông tin xác thực tương ứng. Không phải mọi exporter đều cần secret. Ví dụ, Prometheus thường scrape endpoint metrics nội bộ; endpoint đó có thể được bảo vệ ở tầng mạng hoặc reverse proxy. OTLP exporter gửi dữ liệu đến Collector hoặc backend có thể cần token hoặc mTLS.

| Luồng dữ liệu | Secret có thể cần | Mục đích |
| --- | --- | --- |
| Spring Boot → OTLP Collector (traces) | Bearer token, API key hoặc client certificate/private key | Xác thực ứng dụng khi gửi trace |
| Spring Boot → OTLP Collector (metrics) | Token hoặc API key riêng | Giới hạn quyền gửi metrics theo service hoặc môi trường |
| Collector → observability backend | Credential của backend, token hoặc private key | Xác thực Collector khi chuyển tiếp telemetry |
| Exporter dùng HTTP Basic | Username và password | Xác thực với endpoint hỗ trợ Basic Authentication |
| Kết nối mTLS | Client certificate và private key | Xác thực hai chiều giữa client và server |
| Kết nối TLS thông thường | CA trust material nếu dùng CA nội bộ | Xác minh danh tính server; CA certificate thường không phải secret, private key thì có |

Endpoint URL và tên service thường là cấu hình, không phải secret. Tuy nhiên, không nhúng token hoặc password vào URL query string hay user-info của URL vì URL có thể xuất hiện trong log, exception, dashboard hoặc lịch sử cấu hình. Phân biệt rõ server certificate/public CA certificate với private key: chứng thư công khai có thể cần phân phối rộng hơn, còn private key phải được bảo vệ như secret.

Hãy ghi rõ secret được dùng ở đâu, ai sở hữu, nguồn cấp phát, quyền hạn, ngày hết hạn và quy trình xoay vòng. Nếu ứng dụng chỉ gửi telemetry đến Collector nội bộ, credential để Collector truy cập backend thường nên được giữ ở Collector. Khi đó, ứng dụng chỉ cần quyền gửi dữ liệu đến Collector theo chính sách mạng và xác thực giữa hai thành phần.

## 2. Thiết kế luồng cấp phát secret

Một luồng quản lý secret nên có các thành phần tách biệt:

```text
Secret Manager / Vault / Kubernetes Secret
                 |
          workload identity
          hoặc cơ chế mount
                 |
                 v
        Spring Boot application
                 |
        OTLP over TLS / mTLS
                 |
                 v
          OTLP Collector
                 |
       backend credential riêng
                 |
                 v
       Observability backend
```

Secret được tạo và lưu trong hệ thống quản lý secret. Workload nhận đúng secret trong lúc chạy thông qua identity, volume mount hoặc cơ chế tích hợp được nền tảng hỗ trợ. Spring Boot đọc cấu hình khi khởi động và exporter sử dụng credential đó để gửi telemetry. Collector có thể giữ credential phía backend để không phải phân phối secret backend đến mọi ứng dụng.

Nên ưu tiên theo thứ tự sau khi nền tảng hỗ trợ:

1. **Workload identity hoặc credential ngắn hạn:** ứng dụng chứng minh danh tính bằng service account, OIDC hoặc cơ chế tương đương để nhận token ngắn hạn. Cách này giảm nhu cầu phân phối API key tĩnh.
2. **Secret manager tập trung:** lưu credential trong Vault hoặc cloud secret manager, giới hạn quyền đọc theo workload và môi trường.
3. **Secret được mount từ nền tảng điều phối:** ví dụ Kubernetes Secret hoặc CSI Secret Store, với RBAC và mã hóa lưu trữ được cấu hình phù hợp.
4. **Environment variable được cấp lúc chạy:** có thể dùng khi nền tảng không hỗ trợ cách tốt hơn, nhưng phải kiểm soát quyền đọc process, dump và thông tin chẩn đoán.

Không lưu secret trực tiếp trong `application.yml`, `application-prod.yml`, Helm values đã commit, Dockerfile, image layer, file `.env` được đẩy lên Git hoặc tham số build. Không truyền token trên command line nếu có nguy cơ xuất hiện trong process list, shell history hay log của pipeline.

## 3. Cấu hình Spring Boot để đọc secret bên ngoài

Spring Boot hỗ trợ externalized configuration. Có thể dùng placeholder để đưa giá trị từ environment hoặc một property source do nền tảng cung cấp vào cấu hình exporter. Ví dụ dưới đây minh họa OTLP traces và metrics với hai credential độc lập:

```yaml
management:
  otlp:
    tracing:
      endpoint: ${OTLP_TRACES_ENDPOINT}
      headers:
        Authorization: ${OTLP_TRACES_AUTHORIZATION}
    metrics:
      export:
        url: ${OTLP_METRICS_ENDPOINT}
        headers:
          Authorization: ${OTLP_METRICS_AUTHORIZATION}
```

Các thuộc tính trên áp dụng cho cấu hình OTLP tương ứng của Spring Boot và Micrometer. Chỉ khai báo phần tracing hoặc metrics mà ứng dụng thực sự sử dụng; xác minh dependency, phiên bản Spring Boot và exporter đang bật để bảo đảm thuộc tính được bind. Tên header và cách backend xác thực phụ thuộc hệ thống nhận telemetry. Nếu backend yêu cầu `X-API-Key` hoặc một header khác, cấu hình đúng giao thức đã thống nhất. Với bearer authentication, giá trị của biến `OTLP_TRACES_AUTHORIZATION` hoặc `OTLP_METRICS_AUTHORIZATION` phải chứa cả tiền tố `Bearer` và token theo định dạng mà backend yêu cầu; không chỉ lưu token trần nếu exporter không tự thêm tiền tố.

Trong ví dụ, các giá trị `OTLP_TRACES_AUTHORIZATION` và `OTLP_METRICS_AUTHORIZATION` phải được cung cấp ở runtime. Không đặt giá trị mặc định rỗng cho credential production bắt buộc. Khi secret thiếu, ứng dụng nên thất bại sớm hoặc không được đưa vào trạng thái sẵn sàng, thay vì âm thầm gửi telemetry không xác thực và khiến việc quan sát production bị gián đoạn.

### Dùng environment variable

Nền tảng có thể inject các biến `OTLP_TRACES_ENDPOINT`, `OTLP_TRACES_AUTHORIZATION`, `OTLP_METRICS_ENDPOINT` và `OTLP_METRICS_AUTHORIZATION` vào container. Endpoint thường là cấu hình thông thường; các biến chứa token phải được cấp từ secret store và được che trong log triển khai.

Environment variable thuận tiện nhưng có thể xuất hiện trong một số loại process inspection, crash dump, diagnostic bundle hoặc giao diện quản trị. Chỉ cấp cho đúng container, giới hạn người có quyền exec/inspect và tránh in toàn bộ environment trong log. Với workload nhiều secret hoặc yêu cầu kiểm soát chặt, cân nhắc mount secret thành file.

### Dùng config tree với secret được mount thành file

Spring Boot hỗ trợ `configtree:` để nạp file trong một thư mục thành property. Ví dụ, nền tảng mount secret vào `/run/secrets/` với các file có tên tương ứng:

```text
/run/secrets/
├── OTLP_TRACES_AUTHORIZATION
└── OTLP_METRICS_AUTHORIZATION
```

Khai báo import và placeholder trong cấu hình ứng dụng:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"

management:
  otlp:
    tracing:
      endpoint: ${OTLP_TRACES_ENDPOINT}
      headers:
        Authorization: ${OTLP_TRACES_AUTHORIZATION}
    metrics:
      export:
        url: ${OTLP_METRICS_ENDPOINT}
        headers:
          Authorization: ${OTLP_METRICS_AUTHORIZATION}
```

File trong config tree cung cấp giá trị property theo tên file. Mount volume ở chế độ chỉ đọc nếu nền tảng hỗ trợ, giới hạn quyền file và quyền truy cập thư mục. Không đưa nội dung secret vào image. Nếu dùng `optional:configtree:` cho môi trường local, cần bảo đảm profile production vẫn yêu cầu secret và có kiểm tra khởi động phù hợp.

`configtree:` chỉ là cách Spring Boot đọc cấu hình; nó không tự tạo kho secret, mã hóa volume hay kiểm soát ai được phép đọc file. Các trách nhiệm đó thuộc secret manager và nền tảng triển khai.

## 4. Giới hạn quyền và phạm vi của credential

Credential exporter nên có quyền tối thiểu để gửi telemetry đến đúng tenant, project hoặc endpoint. Nếu backend hỗ trợ, tạo token riêng theo service, môi trường và tín hiệu. Token của `checkout` production không nên dùng chung với ứng dụng thử nghiệm hoặc service không liên quan.

Các nguyên tắc cần áp dụng:

- Chỉ cấp quyền ingest/write cho exporter nếu ứng dụng không cần đọc hoặc quản trị dữ liệu telemetry.
- Tách credential giữa production, staging và development; không dùng secret production trong máy cá nhân hoặc CI test.
- Tách token traces và metrics khi backend hỗ trợ quyền theo loại dữ liệu; việc tách này giúp thu hồi hoặc điều tra sự cố chính xác hơn.
- Giới hạn quyền đọc secret theo service account, namespace, workload identity hoặc policy của secret manager.
- Giới hạn người có quyền tạo, đọc, cập nhật và thu hồi secret. Quyền triển khai ứng dụng không mặc nhiên cần quyền đọc giá trị secret.
- Đặt thời hạn cho token và chứng thư; ưu tiên credential ngắn hạn hoặc có thể thu hồi.
- Theo dõi ai đã đọc hoặc thay đổi secret qua audit log của nền tảng.

Kubernetes Secret không tự động an toàn chỉ vì giá trị được biểu diễn bằng Base64. Base64 là mã hóa biểu diễn, không phải mã hóa bảo mật. Cần bật encryption at rest cho dữ liệu Secret trong etcd theo cấu hình cụm, giới hạn RBAC, tránh quyền `get/list/watch` rộng, và kiểm soát quyền truy cập node cũng như backup. Khi dùng external secret operator hoặc CSI driver, kiểm tra cả quyền của controller và quyền mount secret vào pod.

Nếu nhiều ứng dụng gửi telemetry qua một Collector dùng chung, cân nhắc xác thực từng workload ở đoạn app-to-collector và xác thực riêng collector-to-backend. Một token backend có quyền rộng đặt trong mọi ứng dụng làm tăng phạm vi ảnh hưởng khi một pod bị xâm nhập.

## 5. Bảo vệ đường truyền đến exporter

Secret có thể bị lộ nếu gửi qua kết nối không được bảo vệ. Dùng HTTPS/TLS cho OTLP qua HTTP hoặc cấu hình TLS phù hợp với transport đang dùng. Không tắt kiểm tra hostname hoặc certificate chain trong production để xử lý lỗi chứng thư tạm thời.

Với mTLS, ứng dụng giữ client private key và client certificate; Collector hoặc backend xác minh certificate theo trust policy. Private key phải được mount hoặc cấp từ kho secret với quyền đọc hạn chế. Certificate cần có thời hạn, quy trình gia hạn và khả năng triển khai certificate mới trước khi certificate cũ hết hạn. CA certificate dùng để xác minh server thường không cần giữ bí mật, nhưng phải được phân phối từ nguồn đáng tin cậy.

Kiểm soát thêm ở tầng mạng:

- Chỉ cho phép ứng dụng kết nối đến hostname, port và endpoint collector cần thiết.
- Không expose OTLP receiver ra Internet nếu không có nhu cầu và cơ chế bảo vệ tương ứng.
- Dùng NetworkPolicy, firewall hoặc security group để giới hạn nguồn gửi telemetry.
- Tách endpoint nội bộ và endpoint public; không dùng chung credential nếu phạm vi tin cậy khác nhau.
- Kiểm tra DNS, proxy và certificate chain khi triển khai để tránh gửi dữ liệu đến endpoint giả mạo.

Nếu dùng Collector làm điểm trung chuyển, hãy bảo vệ cả receiver lẫn exporter của Collector. Việc chuyển credential từ ứng dụng sang Collector chỉ có ý nghĩa khi Collector được harden, có quyền hạn tối thiểu và có cơ chế quản lý secret riêng.

## 6. Xoay vòng secret mà không làm gián đoạn telemetry

Xoay vòng cần được thiết kế trước khi token hoặc certificate hết hạn. Một quy trình tốt hỗ trợ giai đoạn credential cũ và mới cùng hợp lệ để ứng dụng có thể chuyển đổi an toàn.

Quy trình xoay vòng token thông thường:

1. **Tạo credential mới:** tạo token mới với cùng phạm vi quyền cần thiết, thời hạn và owner rõ ràng. Nếu backend hỗ trợ, đặt thời gian overlap với token cũ.
2. **Cập nhật secret store:** ghi giá trị mới vào secret manager hoặc Kubernetes Secret. Giữ audit trail và version của secret, không sao chép token vào ticket hay chat.
3. **Phân phối đến workload:** cập nhật mount hoặc environment của đúng deployment. Với Spring Boot đọc cấu hình lúc khởi động, thực hiện rolling restart hoặc cơ chế refresh đã được kiểm chứng.
4. **Xác minh export:** kiểm tra ứng dụng sẵn sàng, exporter không còn lỗi authentication, Collector nhận dữ liệu và backend hiển thị telemetry mới.
5. **Thu hồi credential cũ:** chỉ thu hồi sau khi toàn bộ workload liên quan đã chuyển sang credential mới và thời gian overlap đã kết thúc.
6. **Ghi nhận kết quả:** lưu thời điểm xoay vòng, version secret, workload đã cập nhật, kết quả xác minh và thời điểm thu hồi; không lưu giá trị secret.

Không giả định rằng thay đổi file secret hoặc environment variable sẽ tự động cập nhật exporter đang chạy. Environment variable được thiết lập lúc tạo process; cấu hình Spring Boot và HTTP client/exporter có thể được đọc hoặc khởi tạo một lần. Chỉ dùng hot reload khi tích hợp secret provider, cơ chế refresh và exporter đều hỗ trợ việc cập nhật credential đang hoạt động. Nếu chưa xác minh được, rolling restart là cách rõ ràng hơn.

Với certificate, theo dõi ngày hết hạn và triển khai certificate mới trước khi certificate hiện tại hết hạn. Nếu private key thay đổi, phải cập nhật cặp certificate/key đồng bộ và kiểm tra trust chain. Không chờ đến lúc handshake thất bại mới bắt đầu gia hạn.

### Ví dụ trình tự chuyển đổi

```text
Token A đang hoạt động
        |
Tạo Token B, A và B cùng hợp lệ
        |
Cập nhật secret store thành B
        |
Rolling restart các pod
        |
Kiểm tra export thành công bằng B
        |
Thu hồi Token A
```

Nếu xác minh thất bại, có thể khôi phục cấu hình về version secret trước trong thời gian overlap, tìm nguyên nhân và thử lại. Khi credential cũ đã bị thu hồi, không thể coi rollback chỉ là đổi file cấu hình; cần cấp credential hợp lệ mới theo quy trình khẩn cấp.

## 7. Xử lý sự cố authentication và export

Khi exporter không gửi được dữ liệu, hãy phân loại lỗi trước khi thay secret. Lỗi DNS, TLS, timeout, endpoint sai hoặc collector quá tải có thể trông giống sự cố xác thực từ góc nhìn dashboard.

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| HTTP 401 | Token thiếu, hết hạn, sai hoặc không được gửi | Kiểm tra secret version, header name, thời hạn và cấu hình bind; không in giá trị token |
| HTTP 403 | Token hợp lệ nhưng thiếu quyền hoặc sai tenant/project | Kiểm tra scope, policy và endpoint đích |
| TLS handshake failure | Certificate hết hạn, sai hostname, thiếu CA hoặc private key không khớp | Kiểm tra thời hạn, SAN, trust chain và cặp certificate/key |
| Connection refused hoặc timeout | Collector không lắng nghe, network policy, DNS hoặc endpoint sai | Kiểm tra service discovery, port, route, firewall và trạng thái Collector |
| Export thành công nhưng backend không thấy dữ liệu | Sai tenant, sai signal endpoint, bộ lọc hoặc pipeline Collector | Kiểm tra receiver, processor, exporter, routing và truy vấn backend |
| Lỗi tăng sau rotation | Một số pod vẫn dùng secret cũ hoặc secret mới được mount sai | Kiểm tra version đã triển khai theo từng pod và trạng thái rollout |

Một trình tự chẩn đoán hữu ích:

1. Xác định signal bị ảnh hưởng: traces, metrics hay logs; một service hay nhiều service; một vùng hay toàn bộ môi trường.
2. Kiểm tra thời điểm bắt đầu lỗi so với lần deploy, đổi secret, đổi certificate hoặc thay đổi cấu hình Collector.
3. Xem trạng thái exporter và Collector: số lần export thất bại, queue, retry, dropped telemetry và trạng thái receiver/exporter nếu có metrics tương ứng.
4. Phân loại HTTP status hoặc lỗi transport. Kiểm tra endpoint và TLS trước khi thay credential.
5. Xác minh workload đang dùng đúng secret version và credential có quyền ghi vào đúng tenant.
6. Kiểm tra backend đã nhận dữ liệu bằng một truy vấn có phạm vi thời gian và service cụ thể.

Không bật debug log theo cách có thể ghi toàn bộ request headers. Không copy Authorization header, API key, certificate private key hoặc secret value vào issue, log, screenshot hay lệnh hỗ trợ. Nếu cần kiểm tra header có được cấu hình hay không, ghi nhận trạng thái hiện diện và loại credential, không ghi nội dung.

## 8. Ngăn secret rò rỉ qua telemetry và công cụ vận hành

Exporter secret có thể bị lộ ở nhiều điểm ngoài file cấu hình. Kiểm soát các đường rò rỉ thường gặp:

- **Git và code review:** chỉ commit placeholder và tên biến; bật secret scanning ở repository và pipeline. Nếu phát hiện secret đã commit, thu hồi hoặc xoay vòng ngay cả khi commit đã bị xóa khỏi nhánh hiện tại.
- **CI/CD:** lấy secret từ secret store hoặc workload identity trong job; che giá trị trong log; hạn chế ai được đọc log và artifact. Không ghi token vào output debug hoặc cache build.
- **Container image:** không dùng Dockerfile `ARG`/`ENV` để đóng gói credential; không copy `.env` hoặc file secret vào image layer. Dùng runtime secret mount hoặc cơ chế identity của nền tảng.
- **Logs và exception:** không log header, config object có chứa credential hoặc toàn bộ environment. Kiểm tra cả log của ứng dụng, HTTP client, proxy và Collector.
- **Actuator và endpoint quản trị:** hạn chế truy cập `/actuator/env`, `/actuator/configprops` và các endpoint quản trị tương tự; đặt authentication, network boundary và exposure policy phù hợp. Không dựa vào việc một phiên bản framework đang mask giá trị để thay thế kiểm soát truy cập.
- **Heap dump và diagnostic bundle:** coi file dump, support bundle và snapshot container là dữ liệu nhạy cảm vì chúng có thể chứa object cấu hình hoặc chuỗi credential trong bộ nhớ.
- **Trace, baggage và metric tags:** tuyệt đối không đưa token, password, private key hoặc credential vào span attribute, baggage, resource attribute hay metric tag. Baggage có thể được propagate sang service khác và mở rộng phạm vi rò rỉ.
- **Ticket và trao đổi hỗ trợ:** chỉ tham chiếu secret name, version, fingerprint hoặc ID đã được phê duyệt; không gửi giá trị secret qua chat, email hoặc ảnh chụp màn hình.

Secret có thể bị lộ dù exporter đang hoạt động bình thường. Vì vậy, cần kết hợp secret scanning, audit log, quyền truy cập tối thiểu và quy trình thu hồi; chỉ kiểm tra trạng thái export là chưa đủ.

## 9. Giám sát vòng đời và sức khỏe của exporter

Không chỉ theo dõi việc secret có tồn tại. Hãy theo dõi các chỉ số vận hành để biết credential còn dùng được và telemetry vẫn đến đích:

- Số lần export thành công/thất bại và tỷ lệ lỗi theo exporter hoặc signal.
- HTTP status của endpoint nhận, đặc biệt 401 và 403, nếu exporter/Collector cung cấp metric tương ứng.
- Queue size, retry, dropped data, batch size và độ trễ export.
- Thời điểm hết hạn token hoặc certificate thông qua metadata an toàn của secret manager; không cần đọc và log giá trị secret.
- Thời gian từ lúc tạo secret version đến khi toàn bộ workload sử dụng version mới.
- Số workload còn dùng credential sắp hết hạn hoặc version cũ.

Đặt cảnh báo trước thời điểm credential hết hạn đủ lâu để có thể xoay vòng trong giờ làm việc và xử lý lỗi rollout. Cảnh báo authentication failure nên được phân biệt với network timeout và backend outage để đội vận hành chọn đúng hướng xử lý.

Không tạo metric tag từ token, secret version tùy ý, user ID hoặc request ID. Nếu cần theo dõi version, dùng một nhãn hữu hạn hoặc trạng thái triển khai có kiểm soát, không dùng giá trị secret. Tránh tạo dashboard hoặc log chứa nội dung bí mật chỉ để hỗ trợ rotation.

## 10. Ứng phó khi secret exporter bị lộ

Khi nghi ngờ credential bị lộ, ưu tiên chặn khả năng tiếp tục sử dụng và xác định phạm vi ảnh hưởng:

1. Xác định secret name, version, loại credential, quyền được cấp và các workload đang sử dụng. Không phát tán lại giá trị secret để xác minh.
2. Tạo credential thay thế với quyền tối thiểu nếu hệ thống cho phép overlap; triển khai sang workload hợp lệ.
3. Thu hồi hoặc disable credential bị lộ. Với tình huống có nguy cơ bị khai thác ngay, thực hiện thu hồi khẩn cấp theo quy trình incident response dù có thể làm export tạm gián đoạn.
4. Kiểm tra audit log của secret manager, backend telemetry, Collector, identity provider và nền tảng triển khai để tìm hoạt động bất thường.
5. Đánh giá dữ liệu hoặc hệ thống mà credential có thể truy cập. Nếu token chỉ có quyền ingest, kiểm tra việc gửi telemetry giả hoặc tiêu tốn quota; nếu token có quyền đọc, đánh giá nguy cơ lộ dữ liệu.
6. Xác minh tất cả workload đã dùng credential mới, secret cũ không còn được mount và exporter đã hoạt động trở lại.
7. Tìm nguyên nhân rò rỉ, loại bỏ đường rò rỉ và cập nhật chính sách, pipeline hoặc quyền truy cập liên quan.

Xóa secret khỏi Git history, log hoặc artifact không làm credential đã lộ trở nên an toàn. Thu hồi/rotation là bước bắt buộc; việc làm sạch bản sao chỉ giúp giảm khả năng lộ tiếp.

## 11. Checklist quản lý secret exporter

- [ ] Đã liệt kê exporter, endpoint, signal và credential mà từng luồng cần.
- [ ] Credential được lưu trong secret manager hoặc cơ chế runtime secret của nền tảng.
- [ ] Không có secret thật trong Git, application YAML, Dockerfile, image, build argument hay log CI.
- [ ] Spring Boot lấy secret qua placeholder, config tree hoặc cơ chế identity được kiểm soát.
- [ ] Credential có quyền tối thiểu, tách theo môi trường và service khi phù hợp.
- [ ] Kết nối exporter dùng TLS; mTLS private key được bảo vệ và certificate có lịch gia hạn.
- [ ] Secret được mount với quyền hạn chế; Kubernetes Secret có encryption at rest và RBAC phù hợp nếu được sử dụng.
- [ ] Quy trình rotation có overlap, rolling restart/refresh đã kiểm chứng, bước xác minh và thu hồi credential cũ.
- [ ] Có cảnh báo authentication failure, export failure và credential sắp hết hạn.
- [ ] Actuator, diagnostic endpoint, heap dump và log được bảo vệ khỏi truy cập không phù hợp.
- [ ] Không đưa secret vào span, baggage, resource attribute, metric tag, ticket hoặc ảnh chụp màn hình.
- [ ] Có quy trình incident response để thu hồi credential bị lộ và xác minh toàn bộ workload.

Quản lý secret exporter tốt giúp telemetry tiếp tục được gửi an toàn trong suốt vòng đời ứng dụng. Với Spring Boot, cấu hình externalized chỉ giải quyết việc đưa giá trị vào ứng dụng; bảo mật thực tế còn phụ thuộc nguồn cấp phát, identity, quyền đọc, TLS, rotation, kiểm soát log và khả năng thu hồi. Hãy coi credential exporter như một tài sản production có owner, thời hạn, audit trail và quy trình vận hành rõ ràng.
