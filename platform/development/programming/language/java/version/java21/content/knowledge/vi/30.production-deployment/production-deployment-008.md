# Canary deployment, kiểm tra tính tương thích và rollback

Canary deployment là cách đưa một phiên bản ứng dụng mới tới một phần nhỏ traffic production trước khi mở rộng cho toàn bộ người dùng. Với dịch vụ Java 21, cách làm này giúp phát hiện sớm regression do thay đổi code, JDK patch, runtime image, thư viện native, cấu hình hoặc dependency. Nếu các tín hiệu vận hành xấu đi, đội triển khai có thể dừng rollout và chuyển traffic về phiên bản đã ổn định.

Canary chỉ an toàn khi phiên bản cũ và mới có thể cùng tồn tại trong thời gian rollout, dữ liệu dùng chung vẫn tương thích và có tiêu chí quyết định rõ ràng. Rollback binary không tự đảo ngược thay đổi database, message đã phát, file đã ghi hoặc side effect đã xảy ra. Vì vậy, kiểm tra tương thích và thiết kế thay đổi có thể tiến/lùi là phần cốt lõi của chiến lược triển khai.

## 1. Canary deployment giải quyết vấn đề gì?

Một bản build vượt qua unit test và staging vẫn có thể gặp vấn đề khi nhận traffic thật: phân phối request khác dự kiến, dữ liệu production đa dạng hơn, dependency có tải thực tế, TLS/certificate khác môi trường test hoặc một đường code hiếm mới được kích hoạt.

Canary giới hạn phạm vi ảnh hưởng ban đầu:

1. Triển khai artifact mới song song với phiên bản ổn định.
2. Chuyển một tỷ lệ traffic nhỏ tới phiên bản mới.
3. So sánh chất lượng phục vụ của canary với phiên bản ổn định dưới điều kiện tương đương.
4. Mở rộng traffic từng bước nếu các tiêu chí đều đạt.
5. Dừng hoặc rollback nếu xuất hiện regression vượt ngưỡng đã thống nhất.

```text
                    Ingress / traffic router
                              |
                 +------------+------------+
                 |                         |
             Stable pool                Canary pool
             version A                  version B
                 |                         |
                 +------------+------------+
                              |
                   Shared dependencies
              database / cache / message broker

       Tăng traffic canary khi các quality gate đều đạt
       Dừng rollout và chuyển traffic về stable khi gate thất bại
```

Canary giúp giới hạn blast radius, nhưng không bảo đảm phát hiện mọi lỗi. Một lỗi chỉ xảy ra với một tenant, một loại dữ liệu hoặc một tác vụ chạy theo lịch có thể không xuất hiện trong thời gian canary. Cần kết hợp traffic production, synthetic test, contract test và kiểm tra dữ liệu đại diện.

## 2. Phân biệt canary, rolling và blue-green deployment

Các chiến lược này có thể kết hợp nhưng có cách kiểm soát traffic và rollback khác nhau:

| Chiến lược | Cách triển khai | Điểm mạnh | Điểm cần lưu ý |
|---|---|---|---|
| Rolling update | Thay dần instance cũ bằng instance mới | Không cần duy trì toàn bộ hai fleet lâu dài | Trong rollout có thể tồn tại nhiều phiên bản; cần tương thích giữa chúng |
| Blue-green | Dựng môi trường mới song song rồi chuyển traffic | Chuyển traffic nhanh, có thể quay lại môi trường cũ | Tốn tài nguyên cho hai môi trường; dữ liệu dùng chung vẫn có thể đã thay đổi |
| Canary | Chuyển một phần traffic sang phiên bản mới, sau đó tăng dần | Quan sát hành vi dưới traffic thật với blast radius nhỏ | Cần routing theo tỷ lệ và telemetry đủ tốt để so sánh |

Rolling update không tự động là canary: nếu mỗi replica mới nhận traffic ngay khi sẵn sàng nhưng không có tỷ lệ traffic nhỏ và quality gate riêng, đây chỉ là thay thế instance theo từng đợt. Blue-green cũng có thể kết hợp canary bằng cách chuyển 1% traffic sang green trước khi chuyển hoàn toàn.

## 3. Điều kiện tiên quyết trước khi bật canary

Trước khi đưa traffic production vào bản mới, cần chuẩn bị:

- **Artifact bất biến:** image/JAR đã build, scan và kiểm thử; ghi lại image digest, source revision, JDK vendor/version/build và cấu hình liên quan.
- **Phiên bản stable để đối chứng:** xác định rõ artifact đang phục vụ bình thường và cách chuyển traffic trở lại.
- **Traffic routing:** ingress, gateway hoặc service mesh có thể phân chia traffic theo tỷ lệ hoặc theo cohort; xác nhận health check và sticky session không làm sai tỷ lệ.
- **Telemetry:** có metric theo version/revision cho request rate, error rate, latency histogram, saturation và business outcome.
- **Quality gate:** ngưỡng tiếp tục, dừng, rollback và thời gian quan sát đã được thống nhất trước.
- **Tương thích dữ liệu:** schema database, message, cache, session và API có thể được dùng đồng thời bởi phiên bản cũ/mới.
- **Quyền vận hành:** người trực có quyền dừng rollout, đổi traffic và thực hiện rollback; runbook đã được kiểm tra.
- **Dung lượng:** hệ thống đủ capacity để chạy đồng thời stable và canary, kể cả khi phải rollback hoặc tăng traffic.

Không bắt đầu canary nếu không thể xác định phiên bản nào xử lý request, không phân biệt được metric giữa hai phiên bản hoặc chưa biết cách khôi phục traffic.

## 4. Thiết kế các giai đoạn canary

Một rollout điển hình có thể tăng traffic theo các mức như 1%, 5%, 10%, 25%, 50% và 100%. Đây chỉ là ví dụ; tỷ lệ và số giai đoạn cần điều chỉnh theo RPS, độ nhạy của hệ thống, số lượng tenant, mức độ rủi ro và năng lực rollback.

| Giai đoạn | Traffic mới (ví dụ) | Mục tiêu |
|---|---:|---|
| Pre-production | 0% production | Kiểm tra startup, smoke test, integration và migration |
| Canary nhỏ | 1% | Xác nhận routing, startup, health và lỗi nghiêm trọng |
| Canary mở rộng | 5–10% | Thu đủ request để đánh giá latency, lỗi và dependency |
| Rollout một phần | 25–50% | Xác nhận hành vi ổn định dưới tải đáng kể |
| Hoàn tất | 100% | Chuyển toàn bộ traffic và tiếp tục theo dõi sau triển khai |

Không chuyển giai đoạn chỉ vì đã hết một khoảng thời gian cố định. Mỗi bước cần đủ số request và đủ thời gian để quan sát các hành vi liên quan, chẳng hạn giờ cao điểm, scheduled job hoặc chu kỳ nghiệp vụ. Với traffic thấp, 1% có thể không tạo đủ mẫu; có thể dùng cohort/tenant đại diện hoặc tăng tỷ lệ ban đầu theo đánh giá rủi ro.

### Giữ cohort và điều kiện so sánh công bằng

Nếu có thể, giữ cùng một nhóm người dùng/tenant trong một phiên bản trong suốt phiên làm việc. Điều này tránh request tạo dữ liệu ở phiên bản A nhưng request tiếp theo đọc dữ liệu từ phiên bản B với semantics khác nhau. Tuy nhiên, sticky routing phải có giới hạn và không được làm mất cân bằng tải.

So sánh canary và stable trong cùng khoảng thời gian, vùng địa lý, loại request và điều kiện tải. Nếu canary nhận toàn bộ request nặng còn stable nhận request nhẹ, so sánh latency trực tiếp sẽ không có ý nghĩa. Có thể phân tích theo endpoint, tenant tier, request class hoặc dependency để kiểm soát khác biệt workload.

## 5. Xây dựng quality gate từ SLI và SLO

Quality gate nên dựa trên chỉ số người dùng cảm nhận và giới hạn tài nguyên, không chỉ dựa vào CPU hoặc việc process còn sống.

| Nhóm | Metric nên theo dõi | Dấu hiệu cần dừng rollout |
|---|---|---|
| Availability | Tỷ lệ request thành công, HTTP 5xx, lỗi nghiệp vụ | Error rate tăng vượt ngưỡng hoặc SLO burn rate xấu đi rõ rệt |
| Latency | p50, p95, p99 theo endpoint/operation | Tail latency tăng đáng kể so với stable hoặc vượt SLO |
| Saturation | CPU, heap, GC pause, thread/virtual thread, queue depth | Resource tiến gần giới hạn, queue tăng liên tục hoặc OOM |
| Dependency | Connection pool wait, timeout, retry, remote latency | Canary làm dependency quá tải hoặc tăng retry amplification |
| Business | Thanh toán thành công, đơn hàng hoàn tất, dữ liệu xử lý đúng | Tỷ lệ nghiệp vụ thành công giảm hoặc xuất hiện dữ liệu sai |
| Runtime | Restart, crash, startup failure, JFR/GC signal | Canary liên tục restart, lỗi runtime hoặc regression bất thường |

Nên dùng cả ngưỡng tuyệt đối và so sánh tương đối. Ví dụ: error rate không được vượt giới hạn SLO và cũng không được cao hơn stable quá một mức delta đã định. Một phiên bản có thể có error rate tương đối tăng mạnh nhưng vẫn dưới ngưỡng tuyệt đối khi mẫu nhỏ; ngược lại, stable và canary đều có thể cùng vi phạm SLO do một dependency bên ngoài.

### Đặt ngưỡng và số mẫu trước khi triển khai

Không có một ngưỡng phần trăm phù hợp cho mọi hệ thống. Đội sở hữu service cần xác định:

- Error budget và SLO hiện hành.
- Baseline của stable theo từng loại request.
- Mức regression tối đa có thể chấp nhận.
- Số request tối thiểu để kết luận một metric có ý nghĩa.
- Khoảng thời gian tối thiểu để quan sát chu kỳ traffic và dependency.
- Ngưỡng tự động dừng và điều kiện cần người trực xác nhận.

Với traffic nhỏ, một vài lỗi có thể làm error rate biến động lớn. Hãy xem số lượng mẫu và khoảng tin cậy, không chỉ phần trăm. Với metric hiếm như lỗi thanh toán hoặc mất dữ liệu, cần thêm synthetic test, invariant check và reconciliation thay vì chờ canary tạo đủ mẫu thống kê.

## 6. Kiểm tra tính tương thích của runtime Java 21

Khi thay đổi JDK patch, vendor build hoặc runtime image, cần kiểm tra nhiều lớp tương thích:

### Java version và bytecode

- Xác nhận artifact được biên dịch với target phù hợp, ví dụ `--release 21` khi yêu cầu chạy trên Java 21.
- Chạy test bằng đúng JDK vendor, version và patch build sẽ triển khai.
- Kiểm tra dependency yêu cầu class file version hoặc Java API cao hơn runtime mục tiêu.
- Kiểm tra module, service provider, reflection, native library và các tính năng chỉ có trong runtime cụ thể.

`--release 21` giới hạn API và bytecode lúc biên dịch; nó không bảo đảm các khác biệt vendor, provider, OS hoặc cấu hình runtime không gây lỗi. Nếu canary đồng thời đổi JDK patch và application code, khi xảy ra regression sẽ khó xác định nguyên nhân. Khi rủi ro cao, tách hai thay đổi thành hai release hoặc giữ nguyên một biến để dễ phân tích.

### Security provider, TLS và certificate

JDK update có thể cập nhật security policy, thuật toán bị hạn chế, provider, CA certificates hoặc TLS behavior. Trước canary cần kiểm tra:

- TLS handshake với các dependency thực tế.
- Certificate chain, hostname verification, truststore và private CA.
- Cipher suite, signature algorithm và key size đang sử dụng.
- JDBC driver, HTTP client, message broker client và outbound TLS.
- Hệ thống dùng custom `Provider` hoặc FIPS configuration có tương thích không.

Không giải quyết lỗi handshake bằng cách tắt certificate validation hoặc nới security property một cách rộng rãi. Xác định thay đổi bảo mật và cập nhật certificate/algorithm/configuration theo policy.

### Timezone, locale và dữ liệu runtime

JDK update có thể mang theo timezone database hoặc locale data mới. Kiểm thử các nghiệp vụ nhạy với thời gian như lịch chạy, daylight saving time, ngày hết hạn, timestamp lưu trong database và định dạng ngày/tiền tệ. Không giả định mọi container có cùng OS tzdata hoặc locale package.

### Native library và runtime image

Nếu ứng dụng dùng JNI, FFM, font, compression, image processing hoặc thư viện native, xác minh binary đúng OS, libc và CPU architecture. Kiểm thử trên chính runtime image cuối cùng; chạy trên JDK đầy đủ ở máy developer không chứng minh custom runtime hoặc distroless image có đủ thư viện.

## 7. Kiểm tra tương thích giữa phiên bản cũ và mới

Trong canary, hai phiên bản có thể cùng đọc/ghi database, cache, message broker hoặc gọi API của nhau. Vì vậy, tương thích trong một phiên bản đơn lẻ chưa đủ; cần kiểm tra tương thích *N và N-1* trong thời gian rollout và rollback.

### Database schema: expand-contract

Một migration an toàn thường chia làm nhiều bước:

1. **Expand:** thêm cột/bảng/index mới theo cách phiên bản cũ vẫn chạy được; tránh xóa hoặc đổi nghĩa field cũ ngay.
2. **Deploy compatible code:** bản mới có thể đọc dữ liệu cũ và ghi theo quy ước tương thích; nếu cần, tạm thời dual-write có kiểm soát.
3. **Migrate data:** backfill dữ liệu theo batch, có checkpoint và khả năng tiếp tục.
4. **Verify:** kiểm tra dữ liệu mới đầy đủ và không có replica cũ còn cần field cũ.
5. **Contract:** chỉ trong release sau, khi không còn consumer cũ, mới xóa field/index hoặc đường tương thích cũ.

Ví dụ, nếu đổi `customer_name` thành `display_name`, không xóa `customer_name` trong cùng release canary đầu tiên. Bản mới có thể đọc `display_name` nếu có, fallback sang `customer_name`, rồi cập nhật dữ liệu theo kế hoạch. Chỉ xóa cột cũ sau khi mọi phiên bản và consumer đã chuyển đổi.

Không giả định rollback ứng dụng sẽ rollback được DDL hoặc data migration. Nhiều thay đổi schema không thể đảo ngược an toàn sau khi đã ghi dữ liệu mới.

### Message và event schema

Nếu phiên bản mới phát message mà consumer cũ không đọc được, canary có thể làm hỏng luồng xử lý dù API HTTP vẫn khỏe. Kiểm tra:

- Thêm field có default hoặc optional theo schema contract.
- Consumer cũ có bỏ qua field không biết hay không.
- Enum mới có làm consumer cũ lỗi khi parse không.
- Serialization format và version header có tương thích không.
- Retry, dead-letter queue, ordering và idempotency có được giữ nguyên không.

Trong giai đoạn mixed-version, ưu tiên thay đổi additive và backward-compatible. Nếu phải thay đổi format không tương thích, cần versioning hoặc quy trình chuyển đổi có thứ tự giữa producer và consumer.

### API, cache và session

- Kiểm tra API consumer/provider theo contract test; tránh đổi nghĩa field hoặc status code mà client cũ chưa hiểu.
- Cache key và serialized value cần tương thích giữa hai phiên bản; cân nhắc namespace/versioned key khi format thay đổi.
- Session affinity và session serialization phải hỗ trợ việc request tiếp tục ở phiên bản khác, hoặc routing phải giữ session trong cohort có kiểm soát.
- Feature flag và config phải có default an toàn khi phiên bản cũ chưa biết flag mới.
- Các job nền và scheduler không được chạy trùng ở cả hai fleet nếu công việc không idempotent; dùng leader election, distributed lock hoặc cơ chế single-owner phù hợp.

## 8. Kiểm thử trước canary

Một bộ kiểm thử release nên bao gồm:

| Loại test | Mục tiêu |
|---|---|
| Unit và component test | Xác nhận logic và các nhánh nghiệp vụ chính |
| Integration test | Kiểm tra database, broker, cache, HTTP client và provider thực tế |
| Contract test | Xác nhận tương thích giữa consumer/provider và message schema |
| Migration test | Chạy migration trên bản sao dữ liệu đại diện và kiểm tra tương thích N/N-1 |
| Runtime compatibility test | Chạy bằng đúng JDK vendor/build, OS, module và native library |
| Security test | TLS, certificate, crypto provider, quyền file và secret access |
| Performance/load test | Throughput, p95/p99, heap, GC, queue và dependency wait |
| Smoke/synthetic test | Kiểm tra luồng nghiệp vụ quan trọng sau khi instance sẵn sàng |
| Recovery test | Thử dừng instance, restart, rollback và khôi phục consumer/job |

Test phải chạy trên image production candidate đã pin digest. Nếu có custom `jlink` runtime, hãy chạy test bằng runtime đó thay vì JDK đầy đủ.

### Kiểm tra riêng ứng dụng dùng virtual thread

Nếu dịch vụ dùng virtual thread trong Java 21, đo thêm:

- Số request in-flight và số task đang chờ dependency.
- Pinning event (`jdk.VirtualThreadPinned`) và stack trace trong JDK 21.
- Queue/connection pool wait và số lượng timeout.
- Hành vi cancellation khi request client ngắt kết nối.
- Thread dump và JFR trong image đã triển khai.

Nếu nâng runtime qua JDK 24+, diễn giải monitor-related pinning theo JEP 491; không dùng baseline pinning của JDK 21 để kết luận runtime mới có regression.

## 9. Triển khai canary và theo dõi từng bước

Một quy trình tổng quát:

1. Build và ký artifact; ghi lại image digest, JDK vendor/build, source revision và SBOM.
2. Deploy canary với replica/instance đủ để phục vụ tỷ lệ traffic dự kiến.
3. Chạy startup/readiness check và synthetic smoke test trước khi nhận traffic thật.
4. Route tỷ lệ traffic nhỏ tới canary; gắn metric/span với release version.
5. Theo dõi quality gate và so sánh stable/canary trong cùng cửa sổ thời gian.
6. Nếu đạt, tăng traffic theo từng bước; nếu không đạt, ngừng tăng và thực hiện rollback hoặc điều tra.
7. Sau khi 100% traffic đã chuyển, tiếp tục theo dõi trong khoảng thời gian phù hợp với chu kỳ nghiệp vụ.
8. Chỉ xóa fleet cũ sau khi hết cửa sổ rollback và xác nhận không còn consumer/job/session cần phiên bản cũ.

### Ví dụ kế hoạch tăng traffic

| Bước | Stable | Canary | Gate trước bước kế tiếp |
|---|---:|---:|---|
| 1 | 99% | 1% | Startup, smoke, error nghiêm trọng, routing đúng |
| 2 | 95% | 5% | Đủ request mẫu; error/latency trong giới hạn |
| 3 | 75% | 25% | Dependency và resource không xấu đi; business KPI ổn định |
| 4 | 50% | 50% | So sánh hai cohort dưới tải tương đương |
| 5 | 0% | 100% | Hoàn tất rollout; tiếp tục post-deploy monitoring |

Các tỷ lệ chỉ là ví dụ để minh họa. Nếu traffic rất lớn, có thể bắt đầu ở tỷ lệ thấp hơn; nếu traffic ít, cần thiết kế cohort đủ lớn để kiểm tra. Không mở rộng chỉ dựa trên một lần smoke test thành công.

## 10. Readiness, liveness và graceful shutdown

Trong môi trường container/orchestrator, health check phải phản ánh đúng trạng thái ứng dụng:

- **Startup probe:** cho JVM và ứng dụng đủ thời gian khởi động, load class, kết nối dependency cần thiết và hoàn tất initialization.
- **Readiness probe:** chỉ cho phép nhận traffic khi instance có thể phục vụ request. Khi shutdown hoặc đang drain, readiness phải chuyển sang not-ready.
- **Liveness probe:** phát hiện process bị kẹt không thể tự phục hồi; không nên fail chỉ vì một dependency bên ngoài tạm thời chậm, nếu restart không giải quyết được nguyên nhân.

Khi rollout hoặc rollback:

1. Đưa instance ra khỏi endpoint/traffic pool bằng readiness.
2. Ngừng nhận request mới và chờ connection/request đang xử lý trong giới hạn termination grace period.
3. Đóng executor, connection pool, message consumer và resource theo lifecycle.
4. Flush dữ liệu/telemetry cần thiết và kết thúc process.

Với Java, có thể dùng shutdown hook hoặc lifecycle mechanism của framework để gọi `ExecutorService.close()`/shutdown và đóng pool. Shutdown hook phải có giới hạn thời gian vận hành; không để task blocking vô hạn làm process không kết thúc trước khi orchestrator gửi SIGKILL.

## 11. Khi nào cần rollback?

Rollback nên được kích hoạt khi có bằng chứng bản mới gây regression vượt ngưỡng đã thống nhất hoặc làm tăng rủi ro mất dữ liệu/an toàn. Một số điều kiện thường gặp:

- Error rate hoặc SLO burn rate vượt ngưỡng canary.
- p95/p99 tăng vượt mức chấp nhận trong khi stable không có cùng biến động.
- Crash loop, startup failure, OOM hoặc restart tăng rõ rệt.
- Connection pool cạn, timeout/retry tăng và gây áp lực lan sang dependency.
- Business invariant sai, dữ liệu bị ghi sai hoặc giao dịch không hoàn tất.
- TLS/security provider regression làm mất kết nối tới dependency quan trọng.
- Metric hoặc telemetry của canary mất khiến không thể xác định mức độ an toàn để tiếp tục.

Không cần chờ mọi metric xấu cùng lúc. Một lỗi nghiêm trọng về tính toàn vẹn dữ liệu hoặc bảo mật có thể đủ để dừng ngay rollout, ngay cả khi availability và latency vẫn tốt.

### Dừng rollout khác với rollback

- **Pause:** ngừng tăng tỷ lệ traffic để thu thập thêm dữ liệu hoặc điều tra.
- **Disable canary routing:** đưa traffic mới về stable nhưng giữ canary instance để lấy log/dump nếu an toàn.
- **Rollback binary:** triển khai lại artifact stable đã biết tốt.
- **Roll forward:** sửa lỗi và tạo artifact mới khi rollback không an toàn hoặc không tương thích với state đã thay đổi.

Chọn hành động theo loại lỗi và trạng thái dữ liệu. Không xóa canary instance ngay nếu cần giữ bằng chứng chẩn đoán, nhưng cũng không tiếp tục gửi traffic người dùng vào một bản đã xác định là nguy hiểm.

## 12. Thiết kế rollback an toàn

Rollback cần chuẩn bị trước release:

### Giữ artifact stable bất biến

- Lưu image digest, JDK vendor/version/build, SBOM và source revision của phiên bản stable.
- Xác nhận registry vẫn giữ image và cluster có thể pull artifact đó.
- Không rollback bằng tag trôi nổi; dùng digest đã kiểm thử.
- Có runbook chuyển traffic và khôi phục replica count/capacity.

### Database và dữ liệu

- Dùng expand-contract để phiên bản cũ và mới cùng đọc/ghi trong giai đoạn chuyển tiếp.
- Không xóa column/table/field cũ trước khi hết thời gian rollback.
- Backfill có checkpoint, idempotent và có cách xác minh.
- Với migration không thể đảo ngược, lập kế hoạch roll-forward và backup/restore trước khi chạy.
- Xác định dữ liệu nào đã được bản mới ghi; rollback code không tự chuyển dữ liệu đó về format cũ.

### Message và side effect

- Đảm bảo consumer cũ có thể đọc message mới trong giai đoạn mixed-version hoặc giữ producer ở format tương thích.
- Xử lý message đã phát bằng schema/versioning rõ ràng; không xóa queue để “làm sạch” nếu chưa có đánh giá nghiệp vụ.
- Các thao tác thanh toán, gửi email, tạo đơn hoặc gọi API ngoài cần idempotency key, deduplication hoặc reconciliation.
- Không giả định rollback sẽ thu hồi được email, webhook, giao dịch hoặc message đã gửi.

### Feature flag và config

Nếu thay đổi có thể bật/tắt bằng feature flag, tách việc deploy code khỏi việc kích hoạt behavior. Đặt default an toàn, giới hạn ai có quyền đổi flag và ghi log/audit thay đổi. Flag không thay thế kiểm thử tương thích schema hoặc side effect.

## 13. Runbook rollback mẫu

Một runbook cần nêu rõ người quyết định, lệnh/công cụ được phép, artifact đích và cách xác minh. Quy trình mẫu:

1. Tuyên bố pause rollout và ghi nhận timestamp, release ID, canary digest.
2. Nếu lỗi nghiêm trọng, chuyển traffic canary về stable theo traffic router.
3. Xác minh stable đủ capacity để nhận lại toàn bộ traffic; nếu không, scale stable trước hoặc dùng phương án giảm tải đã phê duyệt.
4. Dừng consumer/job của bản mới nếu chúng có thể tiếp tục ghi dữ liệu hoặc phát message không tương thích.
5. Triển khai stable artifact theo digest đã biết tốt và kiểm tra readiness.
6. Chạy smoke test, kiểm tra error rate, latency, dependency và business invariant.
7. Xác minh database/schema/message state có tương thích với stable; nếu không, chuyển sang kế hoạch roll-forward hoặc restore đã được phê duyệt.
8. Lưu log, JFR, thread dump, metric và event để phân tích nguyên nhân.
9. Thông báo trạng thái theo quy trình incident của tổ chức và mở follow-up trước khi thử rollout lại.

Không thực hiện database downgrade tự động như một phần mặc định của rollback. DDL và dữ liệu có thể đã được dùng bởi phiên bản mới hoặc consumer khác; việc đảo ngược phải dựa trên migration plan riêng.

## 14. Diễn tập rollback và kiểm tra khả năng phục hồi

Một rollback chưa từng được thử chỉ là giả định. Trước khi áp dụng rộng rãi, diễn tập trong staging hoặc môi trường production-like:

- Dừng canary giữa rollout và chuyển traffic về stable.
- Kiểm tra stable có đủ capacity khi nhận lại traffic.
- Kiểm tra readiness, connection draining và graceful shutdown.
- Thử rollback sau một schema expand migration.
- Xác minh consumer cũ đọc được message do bản mới phát trong giai đoạn tương thích.
- Kiểm tra idempotency/reconciliation cho side effect.
- Đo thời gian từ quyết định rollback tới khi SLI phục hồi.
- Xác nhận image digest stable còn tồn tại và có thể pull.

Đặt mục tiêu thời gian khôi phục phù hợp với SLO và mức độ ảnh hưởng. Sau mỗi lần rollback thật hoặc diễn tập, cập nhật runbook theo những bước thực tế đã mất thời gian hoặc cần quyền bổ sung.

## 15. Checklist canary và rollback cho Java 21

- [ ] Stable và canary có artifact/digest/version được ghi nhận rõ ràng.
- [ ] Traffic router có thể chia tỷ lệ và chuyển traffic trở lại stable.
- [ ] Canary và stable được so sánh trên workload/cohort tương đương.
- [ ] Có SLI/SLO, baseline, ngưỡng dừng, số mẫu và thời gian quan sát.
- [ ] Có metric theo release version: error, latency, saturation, dependency và business outcome.
- [ ] Đã test trên đúng JDK 21 vendor/build và runtime image production.
- [ ] Đã kiểm tra TLS, provider, CA, timezone, locale và native dependencies.
- [ ] Database migration theo expand-contract và tương thích N/N-1.
- [ ] API, message, cache và session tương thích trong thời gian mixed-version.
- [ ] Scheduled job/consumer không chạy trùng hoặc tạo side effect ngoài dự kiến.
- [ ] Readiness, liveness, startup probe và graceful shutdown hoạt động đúng.
- [ ] Stable artifact được giữ theo digest và đủ capacity để nhận lại traffic.
- [ ] Rollback/roll-forward cho schema, message và side effect đã được xác định.
- [ ] Đã diễn tập rollback và đo thời gian khôi phục.
- [ ] Có người trực, quyền thao tác và runbook trong suốt rollout.

## Tài liệu tham khảo

- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): rolling update, rollout status, pause/resume và revision history.
- [Kubernetes Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): startup, readiness và liveness probe.
- [Google SRE Workbook — Canarying Releases](https://sre.google/workbook/canarying-releases/): thiết kế canary, chọn metric, phân tích và quyết định rollout.
- [Google SRE Book — Release Engineering](https://sre.google/sre-book/release-engineering/): release process, kiểm thử, rollout và khả năng tái lập artifact.
- [OpenTelemetry Metrics](https://opentelemetry.io/docs/concepts/signals/metrics/): metric counter, gauge và histogram để theo dõi SLI.
- [OpenTelemetry Traces](https://opentelemetry.io/docs/concepts/signals/traces/): theo dõi request qua các service và dependency.
- [Java SE 21 Runtime Environment](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): tùy chọn runtime và cách xác định JVM đang chạy.
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444): mô hình virtual thread trong Java 21 và các lưu ý khi vận hành.
- [JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): khác biệt monitor-related pinning từ JDK 24 khi nâng runtime sau Java 21.
