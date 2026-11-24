# Giữ cùng dữ liệu, cấu hình, dependency và hạ tầng khi so sánh

## 1. Vì sao phải kiểm soát điều kiện benchmark?

Khi đánh giá Spring Boot chạy trên JVM và GraalVM Native Image, mục tiêu là đo ảnh hưởng của **runtime model** tới ứng dụng: thời gian khởi động, độ trễ, thông lượng, CPU và bộ nhớ. Kết quả chỉ có ý nghĩa khi hai phiên bản thực hiện cùng một công việc trong điều kiện tương đương.

Nếu bản JVM dùng database gần hơn, cache đã nóng, pool lớn hơn hoặc chạy trên máy nhiều CPU hơn, chênh lệch đo được không thể quy cho JVM hay Native Image. Tương tự, nếu native build bỏ bớt dependency, tắt một listener hoặc dùng payload nhỏ hơn, benchmark không còn so sánh cùng một ứng dụng.

Bài học này thuộc chương **Đo hiệu năng** của module **SPRING_BOOT_NATIVE_IMAGE**. Module thực hành biên dịch Spring Boot thành GraalVM Native Image bằng Spring AOT để đánh giá lợi ích về thời gian khởi động và bộ nhớ; đồng thời thực hành build Maven/Gradle, cấu hình reflection và resource, kiểm thử tương thích, đóng gói container và vận hành bản native. Nội dung ở đây thiết lập một phương pháp đo công bằng, có thể lặp lại và giải thích được.

Sau bài học, người học có thể:

- Xác định biến cần giữ cố định khi so sánh JVM với Native Image.
- Chuẩn hóa dữ liệu, request mix, cấu hình ứng dụng và dependency.
- Cấp cùng giới hạn CPU, memory, network và dịch vụ phụ trợ.
- Tách cold start khỏi hiệu năng sau warm-up.
- Đo latency, throughput, CPU và memory bằng các chỉ số có ý nghĩa.
- Lặp lại benchmark, tổng hợp số liệu và ghi rõ giới hạn kết luận.

Nguyên tắc xuyên suốt: **chỉ thay đổi yếu tố đang được nghiên cứu**. Trong phép so sánh cơ bản, yếu tố đó là cách chạy ứng dụng: JVM hoặc Native Image. Mọi yếu tố còn lại phải được giữ giống nhau hoặc được ghi nhận rõ nếu không thể giống hoàn toàn.

## 2. Xác định biến độc lập và các điều kiện phải giữ cố định

Trước khi chạy benchmark, viết rõ câu hỏi cần trả lời. Ví dụ: “Với cùng commit, cùng dữ liệu và giới hạn container 2 CPU/1 GiB, bản native có giảm thời gian readiness và RSS so với bản JVM không?”

Trong thí nghiệm này:

- **Biến độc lập:** runtime được so sánh (JVM hoặc Native Image).
- **Biến phụ thuộc:** startup-to-ready, latency, throughput, CPU, RSS, memory peak và các chỉ số đã chọn.
- **Biến kiểm soát:** source code, dependency ứng dụng, dữ liệu, request mix, cấu hình nghiệp vụ, tài nguyên cấp phát, hạ tầng và công cụ đo.

Bảng sau là checklist điều kiện:

| Nhóm | Phải giữ giống nhau | Ví dụ cần ghi lại |
|---|---|---|
| Source | Cùng commit và cùng thay đổi nghiệp vụ | Git commit, build number |
| Spring/AOT | Cùng version Spring Boot, Framework và cấu hình AOT tương ứng | Spring Boot, Java, Native Build Tools |
| Dependency | Cùng phiên bản thư viện runtime và driver | Dependency lock/tree, checksum artifact |
| Dữ liệu | Cùng snapshot, số lượng, phân bố và trạng thái dữ liệu | Dataset ID, row count, seed |
| Request | Cùng payload, tỉ lệ endpoint, concurrency/arrival rate | Kịch bản load, thời lượng |
| Cấu hình | Cùng profile, feature flag và giá trị nghiệp vụ | Config revision, environment variables |
| Hạ tầng | Cùng CPU, memory, kernel, network và dịch vụ ngoài | Host, architecture, cgroup limits |
| Đo lường | Cùng load generator, metric definitions và sampling | Tool/version, dashboard/query |

Không dùng kết quả từ hai lần chạy không có hồ sơ điều kiện này để tuyên bố một runtime nhanh hơn. Nếu một điều kiện bắt buộc khác nhau, ghi rõ khác biệt và xem nó là yếu tố gây nhiễu cần được kiểm soát trong lần đo tiếp theo.

## 3. Giữ nguyên source, phiên bản và dependency

Bắt đầu từ cùng một commit. Build JVM artifact và native artifact từ cùng source tree, cùng cấu hình ứng dụng và cùng tập dependency runtime. Spring AOT có thể sinh thêm mã khởi tạo và RuntimeHints; đó là đầu ra phục vụ runtime native, không phải lý do để thay đổi logic nghiệp vụ giữa hai bản.

Ghi nhận tối thiểu:

- Git commit SHA và trạng thái working tree.
- Phiên bản Spring Boot, Spring Framework, Java/JDK.
- Phiên bản GraalVM và Native Image Build Tools.
- Maven/Gradle wrapper version và build profile.
- Dependency tree hoặc lockfile của runtime classpath.
- Native build arguments, optimization level, GC và PGO nếu có.
- Checksum của JAR, native executable và container image.

Ví dụ lưu thông tin build:

```bash
git rev-parse HEAD
./mvnw -version
java -version
native-image --version
./mvnw -Pnative dependency:tree
```

Với Gradle, có thể dùng:

```bash
git rev-parse HEAD
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
```

Lệnh `dependency:tree` hoặc report Gradle giúp phát hiện khác biệt dependency; nó không thay thế việc kiểm tra artifact cuối. Hãy xác nhận các thư viện runtime, JDBC driver, messaging client, serializer và native libraries cần thiết đều thuộc cùng phiên bản ở hai cách build.

Native Image cần GraalVM compiler và một số build-time dependency riêng. Các công cụ build này không nhất thiết phải xuất hiện trong runtime package của JVM. Điều cần giữ tương đương là **dependency mà ứng dụng thực sự dùng khi xử lý workload**. Ghi riêng toolchain build để người khác có thể tái tạo artifact.

Không loại bỏ dependency hoặc tính năng chỉ ở native profile để làm binary nhỏ hơn rồi so với JAR đầy đủ. Nếu sản phẩm có một profile triển khai khác, phải áp dụng profile tương đương cho cả hai runtime và xác minh chức năng vẫn giống nhau.

## 4. Giữ nguyên dữ liệu và trạng thái ban đầu

Dữ liệu quyết định đáng kể chi phí truy vấn, serialization, cache, allocation và network. Cùng một câu SQL có thể rất nhanh với 100 row nhưng chậm hơn nhiều với hàng triệu row hoặc dữ liệu phân bố lệch.

Chuẩn bị một dataset có thể tái tạo:

- Cùng số lượng record và quan hệ giữa các bảng.
- Cùng độ dài chuỗi, kích thước JSON, số phần tử collection và tỷ lệ null.
- Cùng phân bố hot key/cold key và cardinality.
- Cùng index, schema, statistics và database version.
- Cùng trạng thái cache ở đầu mỗi lượt đo.
- Cùng random seed nếu benchmark sinh dữ liệu/request ngẫu nhiên.

Với workload có ghi dữ liệu, không để bản chạy đầu làm thay đổi trạng thái khiến bản chạy sau được hưởng lợi hoặc chịu bất lợi. Có thể restore database snapshot trước mỗi lượt, dùng namespace riêng với cùng dữ liệu seed hoặc chạy workload chỉ đọc nếu đó là câu hỏi đang nghiên cứu. Nếu không thể reset, hãy thiết kế các record và thứ tự request sao cho hai lượt nhận cùng trạng thái đầu.

Cache cần được định nghĩa rõ. Có hai câu hỏi khác nhau:

- **Cold-cache:** ứng dụng bắt đầu với cache rỗng hoặc cache của database/proxy đã được reset.
- **Warm-cache:** cache đã được làm nóng bằng cùng một chuỗi request trước khi bắt đầu đo.

Không so bản JVM warm-cache với bản native cold-cache. Nếu muốn biết cả hai trường hợp, chạy thành hai benchmark riêng và ghi rõ cách reset/làm nóng.

Dùng cùng database, broker, object storage và dịch vụ phụ trợ. Nếu không thể dùng chung do dữ liệu ghi, tạo hai môi trường tương đương từ cùng snapshot, cùng cấu hình và cùng vị trí mạng. Không để một runtime gọi database qua mạng nội bộ trong khi runtime còn lại gọi database ở cùng host.

## 5. Giữ nguyên cấu hình ứng dụng và hành vi

Cùng source không bảo đảm hai process đang chạy cùng cấu hình. Profile, feature flag, biến môi trường, cron, connection pool hoặc cache size có thể làm thay đổi đường thực thi.

Lập một bản cấu hình chuẩn và cấp bản đó cho cả hai runtime. Các giá trị nên được đối chiếu gồm:

| Khu vực | Ví dụ |
|---|---|
| Spring profile | `spring.profiles.active` |
| HTTP | port, compression, TLS, server thread pool |
| Database | URL, pool size, timeout, transaction isolation |
| Cache | provider, max entries, TTL, eviction policy |
| Messaging | broker, topic/queue, consumer group, concurrency |
| Serialization | ObjectMapper modules, naming strategy, schema version |
| Scheduling | task enablement, cron, timezone, initial delay |
| Logging/metrics | log level, appenders, exporter, sampling |
| Feature flags | bật/tắt cùng tính năng và nhánh nghiệp vụ |

Một số runtime option chỉ có ở một nền tảng. Ví dụ JVM có `-Xms`, `-Xmx`, lựa chọn GC và JIT options; Native Image có heap/GC options và build-time optimization. Không thể ép hai runtime dùng cùng một cờ không có cùng ngữ nghĩa. Thay vào đó, giữ **cùng giới hạn tài nguyên và cùng hành vi ứng dụng**, đồng thời ghi rõ runtime-specific options.

Nên thực hiện hai vòng:

1. **Baseline:** dùng cấu hình mặc định hoặc cấu hình production hiện tại của từng runtime, chỉ đặt cùng giới hạn CPU/memory. Ghi toàn bộ runtime options.
2. **Tuned:** tối ưu JVM và Native Image riêng theo mục tiêu tương đương, sau đó đo lại. Ghi cấu hình, thời gian tuning và kết quả.

Không so một JVM chưa tuning với một native image đã tuning sâu rồi quy toàn bộ chênh lệch cho mô hình runtime. Cũng không thay đổi pool size, cache hoặc feature flag chỉ ở một bên trong cùng vòng baseline.

Trước khi đo, chạy một bộ kiểm tra chức năng để xác nhận hai bản trả cùng kết quả cho cùng input: status code, response body, database side effects, message output và lỗi nghiệp vụ. Benchmark không có functional parity thì không phải phép so sánh hợp lệ.

## 6. Giữ nguyên hạ tầng và giới hạn tài nguyên

Chạy hai phiên bản trên cùng loại máy hoặc hai host có cấu hình tương đương. Ghi lại CPU model/core count, RAM, kiến trúc, kernel, filesystem, container runtime và trạng thái tải nền. Tránh chạy benchmark đồng thời trên cùng host nếu chúng tranh CPU, memory bandwidth, disk hoặc network.

Nếu benchmark trong container, cấp cùng quota CPU và memory. Ví dụ:

```bash
docker run --rm \
  --cpus=2 \
  --memory=1g \
  --memory-swap=1g \
  -p 8080:8080 \
  my-service:jvm
```

Chạy bản native với cùng giới hạn:

```bash
docker run --rm \
  --cpus=2 \
  --memory=1g \
  --memory-swap=1g \
  -p 8080:8080 \
  my-service:native
```

Các giá trị 2 CPU và 1 GiB chỉ là ví dụ; chọn theo giới hạn thực tế của workload. Trong Docker, `--cpus` giới hạn lượng CPU mà container có thể sử dụng, còn `--memory` đặt giới hạn memory. `--memory-swap` ảnh hưởng tổng memory và swap được phép, vì vậy phải giữ giống nhau. Nếu chỉ đặt memory limit mà không kiểm soát swap, hai lần chạy có thể có điều kiện khác nhau khi memory pressure xuất hiện.

Giữ tương đương thêm các yếu tố:

- CPU affinity/cpuset nếu đã pin process vào core.
- Network namespace, DNS, TLS, connection reuse và khoảng cách tới dịch vụ ngoài.
- Filesystem và mount options, nhất là khi workload đọc/ghi file.
- Số replica và mức độ cạnh tranh tài nguyên.
- Quyền user, file descriptor limit và các giới hạn process/thread.

Container image của JVM và native có thể khác base image vì binary cần runtime library khác nhau. Hãy dùng cùng OS family, architecture và libc compatibility khi có thể; nếu khác, ghi rõ kích thước image, thư viện runtime và tác động tiềm tàng. Phân biệt benchmark **runtime trong cùng giới hạn container** với benchmark **kích thước image**: đây là hai câu hỏi khác nhau.

## 7. Chọn workload đại diện và cùng mô hình tải

Một benchmark chỉ có giá trị nếu workload giống công việc thật mà ứng dụng sẽ xử lý. Đừng dùng một endpoint trả chuỗi tĩnh để kết luận toàn bộ ứng dụng Spring Boot nhanh hơn.

Xác định request mix theo lưu lượng thực tế, ví dụ:

| Nhóm workload | Tỷ lệ minh họa | Điều cần giữ |
|---|---:|---|
| Đọc dữ liệu | 60% | Cùng query, row count, cache state |
| Ghi dữ liệu | 20% | Cùng transaction, record size và reset strategy |
| Serialization/report | 15% | Cùng payload size, format và schema |
| Health/metadata | 5% | Cùng endpoint và tần suất |

Tỷ lệ trên chỉ là ví dụ. Lấy tỷ lệ từ production telemetry hoặc use case đã xác định, loại bỏ thông tin nhạy cảm và tái tạo payload bằng dữ liệu kiểm thử.

Giữ cùng mô hình tạo tải:

- **Concurrency:** số request đồng thời hoặc số virtual users.
- **Arrival rate:** số request mới mỗi giây; hữu ích khi muốn giữ offered load cố định.
- **Duration:** thời gian warm-up và thời gian đo.
- **Payload mix:** tỷ lệ request nhỏ/lớn và các endpoint.
- **Connection behavior:** keep-alive, TLS, HTTP version và số connection.
- **Think time/retry:** thời gian chờ, retry policy và timeout.

Concurrency cố định và arrival rate cố định trả lời những câu hỏi khác nhau. Với concurrency cố định, tốc độ request hoàn thành có thể thay đổi theo latency. Với arrival rate cố định, hệ thống phải xử lý một lượng request được gửi tới theo nhịp định trước; khi quá tải, queue và latency có thể tăng. Chọn mô hình phù hợp với mục tiêu, không thay đổi mô hình giữa hai runtime.

Dùng load generator ở máy riêng hoặc xác nhận nó còn dư CPU để không trở thành nút thắt. Cùng một kịch bản, cùng tool version và cùng tham số phải được dùng cho cả hai phiên bản. Nếu dùng dữ liệu replay, giữ nguyên thứ tự hoặc dùng cùng seed để tạo cùng chuỗi request.

## 8. Tách cold start, warm-up và steady-state

Không gộp mọi kết quả vào một phép đo. JVM và Native Image có mô hình khởi động và tối ưu runtime khác nhau, nên cần đo riêng các giai đoạn:

| Giai đoạn | Câu hỏi | Cách thực hiện |
|---|---|---|
| Process start | Từ lúc tạo process tới khi process bắt đầu chạy | Ghi timestamp ngay trước lệnh start |
| Application ready | Khi nào ứng dụng sẵn sàng nhận traffic | Chờ readiness probe thành công |
| First request | Request nghiệp vụ đầu tiên mất bao lâu | Gửi request sau readiness và ghi riêng |
| Warm-up | Hành vi thay đổi thế nào khi runtime/cache ổn định | Gửi cùng warm-up workload, không tính vào steady-state |
| Steady-state | Latency/throughput sau khi hệ thống ổn định | Đo trên cửa sổ thời gian cố định |
| Shutdown | Mất bao lâu để dừng và giải phóng tài nguyên | Gửi shutdown signal và ghi thời gian thoát |

**Cold start** phải được định nghĩa cho từng thí nghiệm. Một container mới nhưng host còn page cache không phải cold boot của cả máy. Một process mới nhưng database connection pool và remote cache đã nóng cũng không phải cold start của toàn hệ thống. Ghi rõ phần nào được reset: process/container, application cache, database cache, DNS, broker connection hoặc host.

Với steady-state, cho cả JVM và native nhận cùng warm-up request. JVM có JIT compilation và có thể cải thiện hiệu năng sau một khoảng chạy; Native Image không dùng HotSpot JIT theo cùng cách. Không loại bỏ warm-up của JVM rồi so với native đã được chạy ổn định, cũng không bỏ qua warm-up nghiệp vụ như cache, connection pool và schema loading ở bản native.

Nếu mục tiêu sản phẩm là scale-to-zero hoặc serverless, cold-start là chỉ số quan trọng và cần benchmark riêng. Nếu ứng dụng chạy liên tục nhiều ngày, throughput, tail latency, GC và RSS ở steady-state thường có trọng số lớn hơn.

## 9. Quy trình chạy lặp lại và cân bằng thứ tự

Một lượt chạy đơn lẻ rất dễ bị ảnh hưởng bởi CPU turbo, nhiệt độ, background jobs, cache, network jitter hoặc hoạt động của database. Hãy chạy nhiều lượt độc lập và giữ lại dữ liệu từng lượt.

Quy trình khuyến nghị:

1. Chốt commit, dependency, cấu hình, dataset và workload.
2. Xác nhận functional parity giữa JVM và native.
3. Khởi động host/container phụ trợ và đợi trạng thái ổn định.
4. Chạy JVM hoặc native theo kịch bản đã định; không chạy đồng thời nếu cùng tranh tài nguyên.
5. Thực hiện warm-up theo cùng workload và thời lượng.
6. Chạy cửa sổ đo với cùng arrival rate/concurrency và thời lượng.
7. Lưu kết quả thô, log, metrics, cấu hình và trạng thái host.
8. Dừng process/container, reset dữ liệu/cache theo protocol.
9. Chạy phiên bản còn lại.
10. Lặp lại ít nhất vài lượt độc lập; tăng số lượt nếu độ biến thiên còn lớn.

Để tránh một runtime luôn được đo trước khi máy nóng hoặc sau khi cache đã ổn định, luân phiên thứ tự chạy. Ví dụ:

```text
Run 1: JVM -> Native
Run 2: Native -> JVM
Run 3: JVM -> Native
Run 4: Native -> JVM
Run 5: JVM -> Native
```

Có thể randomize thứ tự thay vì luân phiên cố định. Dù dùng cách nào, hãy ghi thứ tự chạy và khoảng nghỉ. Nếu benchmark làm thay đổi dữ liệu, reset về cùng snapshot trước từng lượt.

Chọn warm-up và measurement duration dựa trên ứng dụng. Với service nhỏ có thể bắt đầu bằng 30–60 giây warm-up và vài phút đo; với workload dài hoặc có cache/GC chu kỳ, cần thời gian dài hơn. Không coi các con số ví dụ là chuẩn cho mọi ứng dụng. Kiểm tra biểu đồ throughput/latency theo thời gian để xác nhận cửa sổ đo đã ổn định.

## 10. Đo startup tới trạng thái readiness

Thời gian process được tạo không giống thời gian ứng dụng sẵn sàng nhận traffic. Spring Boot Actuator cung cấp các metric startup như:

- `application.started.time`: thời gian ứng dụng bắt đầu.
- `application.ready.time`: thời gian ứng dụng sẵn sàng phục vụ request.

Có thể dùng hai metric này để phân tích nội bộ startup. Để đo trải nghiệm triển khai end-to-end, đo từ lúc container/process được start tới lúc readiness probe thành công. Giữ cùng readiness endpoint, timeout, polling interval và điều kiện phụ thuộc bên ngoài cho hai runtime.

Ví dụ script chờ readiness trên Linux:

```bash
#!/usr/bin/env bash
set -euo pipefail

start_ns=$(date +%s%N)
./service &
app_pid=$!

cleanup() {
  kill "$app_pid" 2>/dev/null || true
  wait "$app_pid" 2>/dev/null || true
}
trap cleanup EXIT

until curl --fail --silent http://127.0.0.1:8080/actuator/health/readiness >/dev/null; do
  if ! kill -0 "$app_pid" 2>/dev/null; then
    echo "Application exited before readiness" >&2
    exit 1
  fi
  sleep 0.1
done

ready_ns=$(date +%s%N)
awk -v start="$start_ns" -v ready="$ready_ns" \
  'BEGIN { printf "startup_to_ready_ms=%.2f\n", (ready-start)/1000000 }'
```

Script chỉ là ví dụ trên Linux; cần chỉnh command khởi chạy, readiness path và process management theo ứng dụng. Với container, timestamp bắt đầu nên được ghi ngay trước lệnh `docker run`, còn readiness nên được lấy từ probe bên ngoài container để tính cả image startup và orchestration overhead nếu đó là điều cần đo.

Không dùng log “Started Application in … seconds” của JVM làm metric duy nhất nếu native được đo bằng readiness probe bên ngoài. Hai con số có thể bao gồm các khoảng thời gian khác nhau. Chọn một mốc thống nhất cho kết quả so sánh và có thể ghi thêm metric nội bộ để giải thích.

Chạy nhiều lần với process/container mới. Báo median, min/max hoặc percentile của startup-to-ready; không lấy lần nhanh nhất làm đại diện.

## 11. Đo latency, throughput và tỷ lệ lỗi

Với service HTTP, các chỉ số cơ bản gồm:

- **Throughput:** request hoàn tất mỗi giây (RPS), hoặc message xử lý mỗi giây.
- **Latency:** thời gian từ khi client gửi request tới khi nhận response.
- **Tail latency:** p95 và p99, cho biết trải nghiệm ở nhóm request chậm.
- **Error rate:** tỷ lệ timeout, HTTP 5xx, lỗi nghiệp vụ hoặc request không hoàn tất.
- **Saturation:** queue depth, pool usage, thread count, CPU throttling và connection wait.

Báo cáo ít nhất p50, p95, p99 cùng throughput và error rate. Trung bình (mean) có thể hữu ích nhưng thường che khuất tail latency. Một runtime có throughput cao hơn nhưng p99 tăng mạnh hoặc tỷ lệ lỗi cao hơn chưa chắc phù hợp hơn.

Chạy nhiều mức tải thay vì chỉ một mức:

1. **Low load:** xác định latency nền khi hệ thống còn nhiều headroom.
2. **Expected load:** tải trung bình dự kiến trong vận hành.
3. **Peak load:** tải cao nhưng vẫn nằm trong phạm vi mục tiêu.
4. **Overload/limit test:** tăng tải để tìm điểm saturation và cách hệ thống suy giảm.

Giữ cùng load profile và thời lượng cho mỗi runtime. Dùng cùng HTTP keep-alive, TLS, connection count, request body, response body và timeout. Đặt load generator trên máy riêng để tránh chính nó làm giới hạn kết quả.

Ví dụ với k6, cùng một script có thể chạy lần lượt cho hai base URL:

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    steady: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '3m',
      preAllocatedVUs: 50,
      maxVUs: 200,
    },
  },
};

export default function () {
  const url = __ENV.BASE_URL + '/api/orders/42';
  const response = http.get(url);
  check(response, {
    'status is 200': (r) => r.status === 200,
  });
}
```

Ví dụ dùng arrival rate 200 request/giây trong 3 phút; phải điều chỉnh rate, VU, endpoint và thời lượng theo workload. Chạy cùng script với biến `BASE_URL` trỏ lần lượt tới JVM và native. Theo dõi dropped iterations, timeout và error rate; nếu load generator không phát đủ request theo cấu hình, kết quả không phản ánh offered load dự kiến.

## 12. Đo memory và CPU đúng cách

### 12.1. RSS là chỉ số chính cho footprint tiến trình

Khi so sánh bộ nhớ ở cấp triển khai, hãy đo **resident set size (RSS)** hoặc memory usage của cgroup/container. RSS thể hiện lượng trang bộ nhớ đang resident của process. Với container, ghi cả current usage và peak usage trong cùng cửa sổ đo.

Không so trực tiếp JVM heap với Native Image heap rồi kết luận runtime nào dùng ít memory hơn. JVM process còn có metaspace, code cache, thread stacks, direct buffers và các vùng native khác. Native Image cũng dùng bộ nhớ ngoài Java heap cho code, stacks và cấu trúc runtime. Heap chỉ là một phần của RSS.

Có thể ghi đồng thời:

| Chỉ số | Ý nghĩa |
|---|---|
| Container/cgroup memory current | Memory container đang sử dụng |
| Container/cgroup memory peak | Mức memory cao nhất trong lượt đo |
| Process RSS | Trang memory resident của process |
| JVM heap used/committed | Thông tin heap của JVM |
| Native Image Java heap | Heap object do Native Image quản lý |
| Thread count/stack | Số thread và bộ nhớ stack |
| Direct/off-heap buffers | Bộ nhớ ngoài heap nếu ứng dụng sử dụng |

RSS và cgroup memory không hoàn toàn giống nhau. Cgroup có thể tính cả page cache hoặc các thành phần khác theo cách kernel/version cấu hình. Ghi rõ nguồn metric và dùng cùng nguồn cho cả hai runtime.

### 12.2. CPU và GC

Đo CPU utilization theo thời gian và CPU time trên mỗi request/message. CPU percentage có thể bị hiểu sai nếu không biết container có quota bao nhiêu core; ghi CPU cores được cấp và throttling time cùng với utilization.

Với JVM, có thể thu GC logs, JFR và Micrometer JVM metrics. Spring Boot Actuator có thể cung cấp metric memory pool, GC, thread, process/system CPU và HTTP request. Với Native Image, dùng metrics/runtime monitoring phù hợp với GraalVM version và cùng mức instrumentation cần thiết.

So sánh throughput cùng CPU consumption giúp trả lời liệu một runtime xử lý cùng lượng công việc với ít CPU hơn hay không. Nếu chỉ nhìn CPU thấp, có thể đó là vì service đang xử lý ít request hơn.

### 12.3. Đừng quên memory limit và OOM

Đặt cùng container memory limit và swap policy. Ghi nhận container restart, OOM kill, `OutOfMemoryError`, GC pause và thời điểm đạt memory peak. Một bản có RSS trung bình thấp nhưng có spike vượt limit trong lúc xử lý batch có thể không phù hợp với môi trường production.

Native Image có nhiều GC implementation và heap policy tùy GraalVM distribution/edition/architecture. Ghi rõ GC và runtime options. Nếu đổi GC hoặc heap policy để tối ưu, hãy tạo một lượt tuned riêng và giữ nguyên workload/giới hạn container.

## 13. Chọn công cụ đo và giữ instrumentation tương đương

Không có một công cụ duy nhất đo mọi khía cạnh. Chọn công cụ theo câu hỏi:

| Mục tiêu | Công cụ có thể dùng | Lưu ý |
|---|---|---|
| HTTP load | k6, Gatling, JMeter, wrk | Chạy load generator bên ngoài máy service |
| Startup/readiness | Readiness probe, script timestamp, Actuator startup metrics | Dùng cùng mốc bắt đầu/kết thúc |
| Container CPU/memory | Docker stats, cgroup metrics, Prometheus | Giữ cùng sampling interval |
| JVM runtime | JFR, GC log, Micrometer/JMX | Có overhead; ghi rõ khi bật |
| Native process | OS process metrics, cgroup, GraalVM runtime metrics/tooling theo version | Chọn cùng metric cấp process/container |
| Microbenchmark Java | JMH | Dùng cho method/component cô lập, không thay load test service |

Spring Boot Actuator và Micrometer cung cấp các metric JVM như memory pool, garbage collection, thread, class loading và JIT compilation; đồng thời có system/process metrics, startup metrics và HTTP request observations. Bật cùng instrumentation cho cả hai runtime nếu dùng các metric này trong so sánh. Nếu một metric chỉ tồn tại ở JVM, dùng nó để chẩn đoán JVM và không đặt cạnh metric khác nghĩa của Native Image như thể chúng tương đương.

JMH phù hợp để đo các đoạn code Java nhỏ và kiểm soát warm-up, measurement iteration và fork. Nó không thay thế benchmark toàn bộ Spring Boot service qua HTTP/broker. Để so sánh JVM với native executable, cần một load harness có thể gửi cùng workload tới hai process độc lập. Không suy ra latency production từ một microbenchmark chạy trong IDE.

Instrumentation có thể làm thay đổi hiệu năng. JFR, profiler, debug logging, tracing exporter và metrics scraping đều có chi phí. Nếu mục tiêu là số liệu production-like, tắt profiler nặng ở cả hai bên và chỉ bật instrumentation tối thiểu giống nhau. Nếu cần profile để giải thích kết quả, chạy một lượt profiling riêng, ghi rõ overhead và không trộn kết quả đó với baseline.

## 14. Tách baseline, tuning và Profile-Guided Optimization

Một so sánh công bằng cần ghi rõ đang đo cấu hình mặc định hay cấu hình đã tối ưu. GraalVM Native Image có các optimization level và tùy chọn GC; JVM cũng có GC, heap, JIT và compiler options. Thay đổi các tùy chọn này có thể ảnh hưởng throughput, latency, memory và build time.

Thực hiện theo từng vòng:

### 14.1. Baseline

- Dùng cùng source, dependency, dữ liệu, cấu hình nghiệp vụ và workload.
- Cấp cùng CPU/memory quota.
- Dùng cùng cấu hình ứng dụng/production profile; dùng runtime options mặc định của từng nền tảng trong baseline và ghi đầy đủ các khác biệt.
- Ghi lại toàn bộ JVM flags, native build options, GC, heap policy và container image.
- Không thêm PGO hoặc profiling đặc biệt cho một bên nếu bên kia không có phép đo tương ứng.

Baseline trả lời: với cách triển khai hiện tại, hai runtime khác nhau thế nào?

### 14.2. Tuning

Sau baseline, có thể tối ưu riêng từng runtime. Ví dụ, điều chỉnh JVM heap/GC hoặc Native Image GC/heap/optimization level. Mỗi thay đổi phải được ghi thành một cấu hình riêng và đo lại bằng đúng dataset, load profile và hạ tầng.

Không thay đổi nhiều biến cùng lúc. Nếu đồng thời đổi GC, pool size và connection limit, sẽ khó xác định thay đổi nào tạo ra kết quả. Thay một nhóm nhỏ, đo, giữ lại hoặc rollback rồi mới thử nhóm tiếp theo.

### 14.3. PGO cho Native Image

Profile-Guided Optimization (PGO) có thể cải thiện throughput cho một số ứng dụng. Quy trình chung là build image có instrumentation, chạy workload đại diện để tạo profile, sau đó build lại với profile đó. Vì PGO dùng dữ liệu workload để định hướng tối ưu, profile phải đến từ request mix gần với production.

Với Native Image CLI, luồng khái quát có dạng:

```bash
# Tạo executable có instrumentation để thu profile.
native-image --pgo-instrument -jar target/my-application.jar

# Chạy executable vừa tạo với workload đại diện; profile mặc định được ghi
# vào default.iprof trong working directory.
./my-application

# Build lại image sử dụng profile đã thu thập.
native-image --pgo -jar target/my-application.jar
```

Đây là ví dụ CLI khái quát; với Maven/Gradle Native Build Tools, truyền các option tương ứng qua cấu hình plugin và kiểm tra output directory của build. Đừng lấy profile cũ từ commit, dependency hoặc workload khác mà không xác minh tính tương thích.

Nếu đưa PGO vào benchmark:

- Tạo một kết quả riêng, không gộp với native baseline.
- Dùng cùng workload đại diện để tạo profile.
- Ghi rõ GraalVM distribution/edition, version, build option và file profile.
- Tính cả chi phí tạo profile và build lại nếu câu hỏi bao gồm chi phí phát hành.
- So sánh với JVM đã được warm-up tương ứng và cùng workload.

Một profile thu từ chỉ một endpoint hoặc dữ liệu lệch có thể làm native binary tối ưu cho tình huống đó nhưng kém ở các luồng còn lại. PGO cũng phụ thuộc edition và phiên bản GraalVM; kiểm tra khả năng hỗ trợ của toolchain đang dùng.

## 15. Tổng hợp và diễn giải kết quả

Giữ dữ liệu thô của từng lượt. Với mỗi chỉ số, tính giá trị từng lượt rồi báo median cùng độ phân tán (min/max, interquartile range hoặc confidence interval phù hợp). Đừng chỉ gộp toàn bộ request từ các lần chạy thành một số rồi bỏ qua khác biệt giữa các lần.

Với chỉ số mà **thấp hơn là tốt hơn** (startup, latency, RSS, CPU time), có thể tính phần trăm thay đổi:

```text
Improvement (%) = (JVM - Native) / JVM * 100
```

Với throughput, **cao hơn là tốt hơn**:

```text
Improvement (%) = (Native - JVM) / JVM * 100
```

Ví dụ, nếu median startup-to-ready của JVM là 1.20 giây và native là 0.45 giây:

```text
(1.20 - 0.45) / 1.20 * 100 = 62.5%
```

Con số này chỉ mô tả kết quả trong điều kiện benchmark đã ghi, không phải mức cải thiện được bảo đảm cho mọi ứng dụng.

Mẫu bảng kết quả:

| Chỉ số | JVM median | Native median | Thay đổi | Ghi chú |
|---|---:|---:|---:|---|
| Startup-to-ready (ms) | — | — | — | Process mới, cùng readiness probe |
| First request p95 (ms) | — | — | — | Đo riêng sau readiness |
| Steady-state p50 (ms) | — | — | — | Cùng request mix |
| Steady-state p95 (ms) | — | — | — | Cùng offered load |
| Steady-state p99 (ms) | — | — | — | Cùng offered load |
| Throughput (RPS) | — | — | — | Không có dropped iterations |
| Error rate (%) | — | — | — | Cùng tiêu chí lỗi |
| RSS median (MiB) | — | — | — | Cùng cửa sổ đo |
| RSS peak (MiB) | — | — | — | Cùng cgroup limit |
| CPU cores average | — | — | — | Ghi cả throttling |
| CPU time/request (ms) | — | — | — | Cùng workload |

Khi đọc bảng, hãy đặt các chỉ số cạnh nhau. Nếu native giảm RSS nhưng p99 tăng, cần xác định trade-off đó có chấp nhận được không. Nếu native khởi động nhanh hơn nhưng throughput thấp hơn ở tải dài, quyết định triển khai phụ thuộc vào kiểu workload và mục tiêu sản phẩm.

Không đưa ra kết luận khi error rate khác nhau đáng kể, load generator bị bão hòa, một lượt chạy thiếu request, container bị throttling bất thường hoặc dữ liệu không được reset giống nhau. Đánh dấu lượt đó là invalid và chạy lại theo cùng protocol; không âm thầm bỏ kết quả bất lợi mà không ghi lý do.

## 16. Hồ sơ benchmark có thể tái tạo

Mỗi báo cáo nên lưu cả kết quả và điều kiện đã tạo ra kết quả. Có thể dùng YAML làm manifest đơn giản:

```yaml
benchmark:
  name: spring-boot-jvm-vs-native
  commit: "<git-sha>"
  dataset: "orders-snapshot-2026-11"
  workload: "orders-read-write-mix-v2"
  runs: 5

application:
  springBoot: "<version>"
  java: "<version>"
  graalvm: "<version>"
  dependencyLockHash: "<sha256>"
  profile: "benchmark"

infrastructure:
  os: "linux"
  architecture: "amd64"
  cpuLimit: "2"
  memoryLimit: "1GiB"
  memorySwap: "1GiB"
  database: "<version-and-location>"
  broker: "<version-and-location>"

load:
  model: "constant-arrival-rate"
  ratePerSecond: 200
  warmup: "60s"
  measurement: "180s"
  requestMix: "orders-read-write-mix-v2"

runtime:
  jvm:
    image: "<image-digest>"
    options: "<record-all-flags>"
  native:
    image: "<image-digest>"
    buildOptions: "<record-all-options>"
```

Các giá trị trong manifest là placeholder hoặc ví dụ, cần thay bằng dữ liệu thật. Lưu thêm raw load-test output, metric export, log startup, GC/JFR nếu có, image digest và command line đầy đủ. Không lưu credential, token hoặc dữ liệu khách hàng trong manifest.

Một benchmark chỉ có thể tái tạo khi người khác biết chính xác artifact, dữ liệu, cấu hình, môi trường và cách tạo tải. Ghi ngày giờ, host, kernel, container runtime, tool versions và thứ tự chạy để giải thích các khác biệt giữa lần chạy.

## 17. Những yếu tố gây nhiễu thường gặp

| Sai lệch | Vì sao làm sai kết quả | Cách xử lý |
|---|---|---|
| JVM được warm-up, native chưa warm-up nghiệp vụ | Cache/connection pool khác nhau | Chạy cùng warm-up workload |
| Dataset hoặc cache state khác | Chi phí DB/cache khác | Restore snapshot và reset theo protocol |
| CPU/memory limit khác | Một runtime được cấp nhiều tài nguyên hơn | Đặt cùng cgroup quota và ghi throttling |
| Chạy hai process cùng lúc trên một host | Tranh CPU, memory bandwidth và I/O | Chạy tuần tự hoặc cấp host riêng tương đương |
| JVM heap so với native heap | Không đo cùng phạm vi bộ nhớ | Dùng RSS/cgroup memory làm chỉ số footprint chính |
| Chỉ đo mean latency | Che khuất request chậm | Báo p50/p95/p99 và error rate |
| Load generator bão hòa | Không gửi đủ offered load | Đặt generator riêng và theo dõi dropped iterations |
| Bật profiler ở một bên | Instrumentation tạo overhead khác nhau | Tắt ở baseline hoặc bật tương đương |
| Dependency/profile khác | Đường thực thi và chức năng khác | Soát lockfile, profile và functional parity |
| Chỉ chọn lượt chạy nhanh nhất | Bỏ qua độ biến thiên | Lặp lại và báo median/phân tán |
| PGO chỉ chạy một kịch bản | Native tối ưu lệch workload | Dùng request mix đại diện và báo riêng |
| Base image/libc khác không ghi nhận | Runtime dependency và startup khác | Ghi image, libc, OS/architecture |

Một số sai lệch không thể loại bỏ hoàn toàn. Khi đó, ghi rõ giới hạn và tránh quy kết nhân quả quá mức. Benchmark là phép đo trong một môi trường và workload cụ thể; nó không tự chứng minh mọi deployment sẽ có cùng kết quả.

## 18. Checklist trước khi công bố kết quả

- [ ] Cùng git commit và source code nghiệp vụ.
- [ ] Cùng Spring Boot/Framework version và dependency runtime.
- [ ] Đã ghi GraalVM/JDK, build tools và native build options.
- [ ] Cùng dataset snapshot, schema, index, seed và trạng thái cache.
- [ ] Cùng Spring profile, feature flags và cấu hình nghiệp vụ.
- [ ] Cùng database, broker, dịch vụ phụ trợ và network path.
- [ ] Cùng CPU/memory/swap limit, architecture và số replica.
- [ ] Cùng request mix, payload, connection behavior và load model.
- [ ] Đã xác nhận functional parity trước benchmark.
- [ ] Đã tách startup, first request, warm-up và steady-state.
- [ ] Đã chạy nhiều lượt và cân bằng/randomize thứ tự.
- [ ] Đã đo p50/p95/p99, throughput, error rate, RSS, CPU và memory peak.
- [ ] Đã xác nhận load generator không bão hòa.
- [ ] Đã ghi runtime-specific options, GC và PGO nếu có.
- [ ] Đã lưu raw data, manifest, logs và image digest.
- [ ] Đã nêu rõ giới hạn và các điều kiện không thể giữ giống nhau.

## Tài liệu tham khảo

- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): JVM/system/process metrics, startup metrics, HTTP request observations và task scheduling metrics.
- [GraalVM Native Image — Memory Management](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/MemoryManagement/): Native Image heap, GC, throughput, latency, footprint và phần memory ngoài heap.
- [GraalVM Native Image — Optimizations and Performance](https://www.graalvm.org/jdk25/reference-manual/native-image/optimizations-and-performance/): optimization levels, PGO và các tùy chọn hiệu năng.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): hướng dẫn microbenchmark Java, warm-up, measurement và setup benchmark đáng tin cậy.
- [Docker — Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/): giới hạn CPU, memory, swap và ảnh hưởng của cgroup tới container.
- [Oracle Java — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): JVM options, unified logging và JFR.

## Kết luận

So sánh JVM với GraalVM Native Image chỉ đáng tin khi hai bản chạy cùng source, dependency runtime, dữ liệu, cấu hình nghiệp vụ, workload và hạ tầng. Đo startup-to-ready riêng với first request và steady-state; báo latency percentiles cùng throughput/error rate; dùng RSS hoặc cgroup memory để so footprint thay vì đặt JVM heap cạnh Native Image heap. Lặp lại nhiều lượt, lưu manifest và raw data, đồng thời tách baseline khỏi các lượt tuning/PGO. Kết quả thu được khi đó mới giúp nhóm quyết định runtime phù hợp với workload Spring Boot và giới hạn triển khai thực tế.
