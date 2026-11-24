# Thu thập kết quả, log và mã thoát để xác nhận thất bại trong CI

> **Chương: Kiểm thử native.** Module **SPRING_BOOT_NATIVE_IMAGE** biên dịch ứng dụng Spring Boot thành GraalVM Native Image bằng Spring AOT để đánh giá thời gian khởi động, bộ nhớ và khả năng vận hành. Trong CI, một dòng log cuối cùng hoặc trạng thái build màu xanh chưa đủ để kết luận native test thành công. Bài học này hướng dẫn thu thập exit code, log, báo cáo kiểm thử và trạng thái container để xác định chính xác giai đoạn thất bại và giữ lại bằng chứng phục vụ điều tra.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt exit code của build, native test, native executable và container.
2. Thu stdout, stderr, log build và báo cáo JUnit mà không làm mất mã thoát gốc.
3. Nhận diện lỗi compile, lỗi tạo Native Image, test assertion, lỗi khởi động, timeout và process bị hệ điều hành kết thúc.
4. Bảo đảm CI đánh dấu job thất bại khi native test hoặc smoke test thất bại.
5. Lưu log, test report, thông tin môi trường và exit code thành artifact để có thể tải về sau khi job kết thúc.
6. Dùng readiness check và container inspection để phân biệt ứng dụng chưa sẵn sàng với ứng dụng đã chạy nhưng xử lý request thất bại.
7. Thiết kế tiêu chí pass/fail rõ ràng, tránh false positive do test bị skip, report bị thiếu hoặc shell che giấu lỗi.

## 2. Vì sao cần thu thập nhiều loại bằng chứng?

Native Image có nhiều giai đoạn độc lập. Một pipeline có thể biên dịch executable thành công nhưng native test thất bại; test có thể pass nhưng ứng dụng không khởi động trong container; ứng dụng có thể khởi động nhưng endpoint nghiệp vụ trả lỗi.

| Giai đoạn | Bằng chứng cần giữ | Câu hỏi cần trả lời |
|---|---|---|
| Resolve dependency và Spring AOT | Build log, dependency/version, AOT log | Cấu hình và dependency có được chuẩn bị đúng không? |
| Native Image compilation | Native build log, compiler output, exit code | GraalVM có tạo được executable không? |
| Native test | JUnit XML, test report HTML, test log, exit code | Test nào pass, fail, error hoặc bị skip? |
| Chạy executable | stdout, stderr, exit code, thời gian khởi động | Process có khởi động và kết thúc đúng không? |
| Container smoke test | Container log, health status, inspect output, exit code | Image có chạy được trong môi trường triển khai không? |
| CI job | Job summary, artifact, stage status | Pipeline có phản ánh đúng mọi thất bại không? |

**Exit code cho biết process kết thúc thành công hay thất bại; log và test report giải thích nguyên nhân.** Cần lưu cả ba. Không nên suy ra test pass chỉ từ việc native build hoàn tất hoặc không thấy dòng `BUILD FAILED` trong một phần log đã bị cắt.

## 3. Exit code là tín hiệu chính để xác nhận thất bại

Trên shell Unix/Linux, process trả về mã thoát khi kết thúc. Quy ước phổ biến:

| Exit code | Ý nghĩa thường gặp | Cách điều tra |
|---:|---|---|
| `0` | Process báo hoàn tất thành công | Kiểm tra thêm test report và điều kiện nghiệp vụ |
| `1` | Lỗi tổng quát do ứng dụng, build tool hoặc script | Đọc log gần thời điểm lỗi và stack trace |
| `2` | Lỗi cú pháp/tham số ở một số chương trình | Kiểm tra command line và cấu hình |
| `124` | GNU `timeout` kết thúc lệnh vì quá thời gian | Xác định startup/test bị treo hay timeout quá ngắn |
| `134` | Thường là process kết thúc bởi `SIGABRT` | Tìm fatal error, assertion native hoặc abort từ thư viện |
| `137` | Thường tương ứng `SIGKILL` | Kiểm tra OOM, giới hạn container hoặc runner bị dừng |
| `139` | Thường tương ứng `SIGSEGV` | Điều tra native crash, JNI, native library hoặc lỗi bộ nhớ |
| `143` | Thường tương ứng `SIGTERM` | Kiểm tra timeout, cancellation hoặc thao tác stop container |

Các mã signal ở trên theo quy ước shell Unix `128 + signal number`; chúng không phải quy tắc tuyệt đối cho mọi hệ điều hành và CI provider. Đặc biệt, exit code `137` không tự chứng minh có Out Of Memory. Nó chỉ cho biết process thường đã nhận `SIGKILL`; cần kiểm tra trạng thái container, memory limit và log của runner để xác định nguyên nhân.

Exit code `0` cũng chưa đủ chứng minh hệ thống đúng. Ví dụ, một test task có thể bị cấu hình bỏ qua failure, không phát hiện test nào hoặc không chạy test native như dự kiến. Hãy kiểm tra exit code cùng số lượng test và báo cáo JUnit.

## 4. Thu stdout, stderr và exit code trong shell

Một lỗi phổ biến là chạy command trong pipeline rồi chỉ lấy exit code của `tee`. Cách đơn giản, dễ kiểm soát là ghi output vào file, lấy mã thoát ngay sau command, sau đó in log:

```bash
#!/usr/bin/env bash
set -u

mkdir -p ci-artifacts

set +e
./gradlew nativeTest --no-daemon --console=plain --stacktrace \
    > ci-artifacts/native-test.log 2>&1
test_rc=$?
set -e

cat ci-artifacts/native-test.log
printf 'nativeTest_exit_code=%s\n' "$test_rc" \
    > ci-artifacts/native-test-exit-code.txt

exit "$test_rc"
```

Trong ví dụ, stdout và stderr được gộp vào cùng file để giữ thứ tự thông báo. Nếu cần phân tích riêng hai luồng, dùng:

```bash
set +e
./gradlew nativeTest --no-daemon --console=plain --stacktrace \
    > ci-artifacts/native-test.stdout.log \
    2> ci-artifacts/native-test.stderr.log
test_rc=$?
set -e

printf 'nativeTest_exit_code=%s\n' "$test_rc" \
    > ci-artifacts/native-test-exit-code.txt
exit "$test_rc"
```

Đặt `set +e` ngay trước command cần lấy exit code để shell không thoát trước khi gán `test_rc`. Sau khi đã lưu mã thoát, có thể bật lại `set -e`. Cuối script phải trả lại đúng mã thất bại để CI đánh dấu step/job là failed.

### 4.1. Khi cần dùng tee

`tee` hữu ích khi muốn vừa xem log trực tiếp trên CI vừa lưu file. Hãy bật `pipefail` và tắt `errexit` trong đoạn cần capture:

```bash
set +e
set -o pipefail

./gradlew nativeTest --no-daemon --console=plain --stacktrace \
    2>&1 | tee ci-artifacts/native-test.log
test_rc=$?

set -e
printf 'nativeTest_exit_code=%s\n' "$test_rc" \
    > ci-artifacts/native-test-exit-code.txt
exit "$test_rc"
```

`pipefail` làm pipeline trả về trạng thái khác 0 nếu một command trong pipeline thất bại. Nếu thiếu `pipefail`, pipeline thông thường trả exit code của command cuối là `tee`; khi Gradle thất bại nhưng `tee` ghi file thành công, shell có thể báo `0` và CI hiểu nhầm là pass.

### 4.2. Không để script vô tình nuốt lỗi

Các cách sau có thể làm CI báo thành công dù native test đã thất bại:

```bash
# Sai: echo là command cuối nên status thường là 0.
./gradlew nativeTest
echo "Native test finished"

# Sai: ép exit code thành 0.
./gradlew nativeTest || true

# Có nguy cơ mất exit code nếu không bật pipefail.
./gradlew nativeTest 2>&1 | tee native-test.log
```

Nếu cần chạy bước thu thập log sau khi test thất bại, hãy lưu exit code trước, chạy bước thu thập, rồi trả lại mã thoát gốc. Không dùng `|| true` cho test gate; chỉ dùng nó cho thao tác cleanup hoặc thu thập tùy chọn mà kết quả không quyết định pass/fail.

## 5. Thu log và report từ Gradle

Với dự án đã cấu hình GraalVM Native Build Tools Gradle plugin, task `nativeTest` chạy test trên Native Image. Có thể dùng:

```bash
./gradlew nativeTest --no-daemon --console=plain --stacktrace
```

Khi điều tra sâu hơn, thêm `--info`; chỉ bật `--debug` khi thật sự cần vì log rất lớn và có thể chứa thông tin cấu hình nhạy cảm.

Các file báo cáo Gradle thường nằm trong:

| Loại | Đường dẫn thường gặp |
|---|---|
| JUnit XML | `build/test-results/nativeTest/` |
| HTML test report | `build/reports/tests/nativeTest/` |
| Console log | File do CI redirect hoặc `tee` tạo |

Tên task và thư mục report có thể thay đổi nếu dự án đổi tên source set/task hoặc cấu hình test report. Kiểm tra output thực tế của task trong dự án, không tạo một thư mục report rỗng rồi coi đó là bằng chứng test đã chạy.

Native Image compilation của ứng dụng thường được thực hiện bằng task `nativeCompile`. Task này chỉ xác nhận quá trình tạo executable; cần chạy `nativeTest` hoặc smoke test trên executable để xác minh hành vi:

```bash
./gradlew nativeCompile --no-daemon --console=plain --stacktrace
./gradlew nativeTest --no-daemon --console=plain --stacktrace
```

Nếu `nativeTest` tự thực hiện các bước biên dịch cần thiết, không nhất thiết phải chạy riêng `nativeCompile` trước đó. Chỉ giữ cả hai task khi pipeline cần cả binary ứng dụng lẫn test report.

## 6. Thu log và report từ Maven

Với dự án Spring Boot đã cấu hình native profile, một cách chạy native test thường gặp là:

```bash
./mvnw -PnativeTest test -e
```

Profile `nativeTest` phải được khai báo để gắn Maven Native Build Tools plugin với goal chạy test bằng native executable. Tên profile và lifecycle cụ thể phụ thuộc cấu hình dự án. Hãy xác minh log cho thấy test thực sự chạy trên native executable, không chỉ chạy Surefire trên JVM.

Các report Maven Surefire thường nằm trong:

| Loại | Đường dẫn thường gặp |
|---|---|
| JUnit XML và dump | `target/surefire-reports/` |
| Build log | File do CI redirect hoặc `tee` tạo |
| Native executable/build output | Theo cấu hình `native-maven-plugin` và Spring Boot plugin |

Nếu cần chẩn đoán plugin hoặc lifecycle, có thể dùng `-X` để lấy debug log Maven. Chỉ bật khi cần vì log rất lớn và có thể tiết lộ URL nội bộ, biến môi trường hoặc tham số cấu hình. Kiểm tra và redaction trước khi lưu artifact có thời hạn dài.

Một Maven command trả `0` cần được đối chiếu với Surefire report: số test được chạy, failure, error, skipped. Nếu test bị skip do điều kiện môi trường hoặc profile không đúng, pipeline phải xử lý theo chính sách rõ ràng thay vì mặc định coi là native test pass.

## 7. Ghi nhận kết quả từng giai đoạn riêng biệt

Không nên dùng một exit code chung cho toàn pipeline mà không biết nó đến từ bước nào. Lưu một file trạng thái cho mỗi giai đoạn:

```text
ci-artifacts/
  native-build.log
  native-build-exit-code.txt
  native-test.log
  native-test-exit-code.txt
  application-smoke.log
  application-smoke-exit-code.txt
  container-inspect.json
  container-logs.log
  test-reports/
```

Ví dụ script chạy build và test:

```bash
#!/usr/bin/env bash
set -u

mkdir -p ci-artifacts

set +e
./gradlew nativeCompile --no-daemon --console=plain --stacktrace \
    > ci-artifacts/native-build.log 2>&1
build_rc=$?
set -e

printf '%s\n' "$build_rc" > ci-artifacts/native-build-exit-code.txt
cat ci-artifacts/native-build.log

if [ "$build_rc" -ne 0 ]; then
    exit "$build_rc"
fi

set +e
./gradlew nativeTest --no-daemon --console=plain --stacktrace \
    > ci-artifacts/native-test.log 2>&1
test_rc=$?
set -e

printf '%s\n' "$test_rc" > ci-artifacts/native-test-exit-code.txt
cat ci-artifacts/native-test.log

exit "$test_rc"
```

Script dừng nếu native compilation thất bại vì test không thể chạy trên binary chưa được tạo. Nếu build thành công nhưng test thất bại, script trả exit code của test. CI vẫn cần có bước upload artifact chạy `always()` hoặc `if: always()` để log và report được lưu kể cả khi script trả non-zero.

Nếu pipeline có nhiều bước độc lập, ghi riêng mã thoát của từng bước và tổng hợp kết quả cuối cùng theo chính sách gate. Không ghi đè file status của build bằng status test.

## 8. Kiểm tra native executable trực tiếp

Native test task kiểm tra test suite. Một số lỗi chỉ xuất hiện khi chạy executable ứng dụng với cấu hình gần production, vì vậy cần có smoke test riêng:

```bash
mkdir -p ci-artifacts
set +e
timeout --signal=TERM --kill-after=10s 120s \
    ./build/native/nativeCompile/orders-service \
    > ci-artifacts/application-smoke.log 2>&1
app_rc=$?
set -e

printf 'application_exit_code=%s\n' "$app_rc" \
    > ci-artifacts/application-smoke-exit-code.txt
cat ci-artifacts/application-smoke.log
exit "$app_rc"
```

Đường dẫn executable trong ví dụ chỉ mang tính minh họa; dùng output path thật của Gradle/Maven build. GNU `timeout` trả `124` khi hết thời gian chờ và có thể trả `137` nếu process bị kill sau khoảng grace period. Nếu binary là web server chạy liên tục, không dùng lệnh trên như một test hoàn chỉnh vì server khỏe mạnh sẽ không tự kết thúc; hãy dùng readiness check và request smoke test.

### 8.1. Readiness check cho ứng dụng Spring Boot

Với ứng dụng có Actuator readiness endpoint, một quy trình smoke test đơn giản:

```bash
#!/usr/bin/env bash
set -u

mkdir -p ci-artifacts
./orders-service > ci-artifacts/application.log 2>&1 &
app_pid=$!

ready=0
for attempt in $(seq 1 30); do
    if curl --fail --silent --show-error \
        http://127.0.0.1:8080/actuator/health/readiness; then
        ready=1
        break
    fi
    sleep 2
done

if [ "$ready" -ne 1 ]; then
    cat ci-artifacts/application.log
    kill "$app_pid" 2>/dev/null || true
    wait "$app_pid" 2>/dev/null || true
    exit 1
fi

curl --fail --silent --show-error \
    http://127.0.0.1:8080/api/orders/health-check
smoke_rc=$?

kill "$app_pid" 2>/dev/null || true
wait "$app_pid"
app_rc=$?

cat ci-artifacts/application.log
printf 'smoke_exit_code=%s\n' "$smoke_rc" \
    > ci-artifacts/application-smoke-exit-code.txt
printf 'application_exit_code=%s\n' "$app_rc" \
    > ci-artifacts/application-exit-code.txt

if [ "$smoke_rc" -ne 0 ]; then
    exit "$smoke_rc"
fi
if [ "$app_rc" -ne 0 ] && [ "$app_rc" -ne 143 ]; then
    exit "$app_rc"
fi
```

Ví dụ cần được điều chỉnh theo endpoint thực tế, port, cơ chế xác thực và cách ứng dụng xử lý `SIGTERM`. Endpoint readiness phải được bật và được phép truy cập trong môi trường test. Nếu ứng dụng cần database hoặc cache, readiness check và smoke request nên xác minh dependency đó đã sẵn sàng.

Không coi một lần `curl` thất bại ngay sau khi process start là ứng dụng hỏng; server cần thời gian khởi động. Ngược lại, cũng không chờ vô hạn: giới hạn thời gian và giữ log để biết ứng dụng chưa bind port, lỗi cấu hình hay không kết nối được dependency.

## 9. Thu log và exit code từ Docker container

Đối với container chạy một tác vụ kết thúc (one-shot), có thể giữ container sau khi kết thúc để đọc log và trạng thái:

```bash
set +e
docker run --name orders-native-ci orders-native:ci \
    > ci-artifacts/container-run.log 2>&1
docker_rc=$?

docker inspect orders-native-ci \
    > ci-artifacts/container-inspect.json
inspect_rc=$?

docker logs orders-native-ci \
    > ci-artifacts/container-logs.log 2>&1
logs_rc=$?

docker rm orders-native-ci
rm_rc=$?

printf 'docker_run_exit_code=%s\n' "$docker_rc" \
    > ci-artifacts/container-exit-code.txt

if [ "$docker_rc" -ne 0 ]; then
    exit "$docker_rc"
fi
if [ "$inspect_rc" -ne 0 ] || [ "$logs_rc" -ne 0 ]; then
    exit 1
fi
if [ "$rm_rc" -ne 0 ]; then
    exit "$rm_rc"
fi
```

Không dùng `--rm` trong ví dụ này vì cần inspect container sau khi process kết thúc. Nếu cần cleanup trong mọi trường hợp, đặt lệnh `docker rm` trong trap hoặc bước cleanup của CI. Với server chạy nền, hãy dùng `docker run -d`, kiểm tra health/readiness, gửi request, thu `docker logs` và `docker inspect` trước khi stop/remove container.

Các trường quan trọng trong `docker inspect`:

- `State.Status`: trạng thái container.
- `State.Running`: container còn chạy hay đã dừng.
- `State.ExitCode`: mã thoát của process chính trong container.
- `State.OOMKilled`: Docker có ghi nhận container bị OOM kill hay không.
- `State.Error`: lỗi khi runtime tạo hoặc khởi chạy container.
- `State.Health.Status`: trạng thái health check nếu image có khai báo health check.

Exit code của lệnh `docker run`, exit code trong `State.ExitCode` và mã thoát của một lệnh `docker inspect` là ba giá trị khác nhau. Lưu chúng dưới tên riêng để tránh nhầm lẫn. Với container chạy server, việc container vẫn `Running` không chứng minh endpoint đã sẵn sàng; hãy kiểm tra health status hoặc gửi request thật.

## 10. Phân loại lỗi dựa trên log và báo cáo

| Dấu hiệu | Giai đoạn có thể lỗi | Bằng chứng cần xem |
|---|---|---|
| `UnsupportedFeatureError`, thiếu registration hoặc lỗi reachability | Native Image analysis/build | Native build log, stack trace, Runtime Hints và metadata |
| Compiler error hoặc lỗi linker | Native compilation | GraalVM compiler output, toolchain, OS/architecture |
| JUnit failure/error | Native test | XML report, test name, assertion và test log |
| Process thoát trước khi log `Started` | Startup/runtime initialization | Native stderr, stack trace, config, resource và dependency |
| Process khởi động nhưng readiness không đạt | Startup hoặc dependency | Application log, health details, DB/cache/network status |
| HTTP smoke request trả 4xx/5xx | Application behavior | Request/response, security config, server log và correlation ID |
| Container exit `137` hoặc `OOMKilled=true` | Container/runtime resource | Docker inspect, memory limit, runner/container events |
| Container exit `139` | Native crash | stderr, core dump nếu có, JNI/native library và architecture |
| Test report không tồn tại | Test chưa chạy hoặc report path sai | CI command, task execution log và cấu hình test report |
| Exit code `0` nhưng test count bằng 0 | Test discovery/profile/filter sai | JUnit XML, Gradle/Maven summary và test selectors |

Không chỉ tìm từ khóa `FAILED` bằng grep rồi kết luận. Một log có thể chứa từ `failed` trong retry message nhưng cuối cùng test pass; ngược lại process có thể bị kill mà không kịp ghi dòng `BUILD FAILED`. Dùng exit code và report có cấu trúc làm tín hiệu chính, dùng log để giải thích.

## 11. Lưu test report và artifact ngay cả khi job thất bại

CI thường dừng các step tiếp theo sau khi một step trả non-zero. Nếu bước upload artifact cũng bị skip, log quan trọng sẽ mất. Hãy cấu hình bước upload luôn chạy:

```yaml
steps:
  - name: Run native tests
    shell: bash
    run: |
      set +e
      ./gradlew nativeTest --no-daemon --console=plain --stacktrace \
        > native-test.log 2>&1
      test_rc=$?
      cat native-test.log
      printf '%s\n' "$test_rc" > native-test-exit-code.txt
      exit "$test_rc"

  - name: Upload native test diagnostics
    if: always()
    uses: actions/upload-artifact@v4
    with:
      name: native-test-diagnostics
      if-no-files-found: warn
      path: |
        native-test.log
        native-test-exit-code.txt
        build/test-results/nativeTest/
        build/reports/tests/nativeTest/
```

Đây là ví dụ cho GitHub Actions. Với CI provider khác, dùng điều kiện tương đương `always()`/`finally` để upload report sau khi test fail. Điều kiện upload không được biến test step thành pass; step chạy test vẫn phải trả exit code gốc.

Artifact nên chứa:

- Log build native và native test.
- Exit code của từng giai đoạn.
- JUnit XML và HTML report.
- Log stdout/stderr của executable hoặc container.
- `docker inspect` hoặc trạng thái runtime tương đương.
- Thông tin GraalVM JDK, Native Build Tools, Spring Boot, OS/architecture và commit.

Đặt retention phù hợp với thời gian điều tra. Log có thể chứa endpoint nội bộ, tên user, query hoặc dữ liệu test; phải redaction token/password và tránh lưu secret vào artifact. Nếu cần log chi tiết hơn, bật ở một pipeline điều tra riêng với quyền truy cập giới hạn.

## 12. Tiêu chí pass/fail cho native CI

Một job native test nên chỉ pass khi tất cả điều kiện bắt buộc được thỏa mãn:

1. Native Image build hoàn tất với exit code `0`.
2. Native test task/goal thực sự được thực thi và trả exit code `0`.
3. Test report được tạo ở vị trí dự kiến, có test được chạy và không có failure/error.
4. Không có test quan trọng bị skip ngoài chính sách đã định.
5. Native executable khởi động trong thời gian cho phép.
6. Readiness endpoint và smoke request nghiệp vụ trả kết quả mong đợi.
7. Container không bị OOM kill hoặc crash; exit code và health state phù hợp.
8. Log, report và exit code được upload kể cả khi job thất bại.

Ví dụ ma trận gate:

| Điều kiện | Pass | Fail |
|---|---|---|
| Native build | Exit code `0` | Non-zero hoặc timeout |
| Native test | Exit code `0`, report hợp lệ | Assertion/error hoặc test không được chạy |
| Test report | Có XML, test count lớn hơn 0 | Thiếu report, report rỗng hoặc parse lỗi |
| Startup | Readiness đạt trước deadline | Process thoát hoặc readiness timeout |
| Smoke request | HTTP/status và body đúng kỳ vọng | Request fail hoặc response sai |
| Container | Không OOM/crash, trạng thái phù hợp | OOMKilled, runtime error hoặc exit ngoài dự kiến |
| Diagnostics | Artifact được lưu | Không có log/report để điều tra |

Nếu một dự án cố ý không có native test cho một dependency hoặc môi trường không hỗ trợ container, hãy ghi rõ điều kiện `Not Applicable` và có gate thay thế được phê duyệt trong thiết kế pipeline. Không tự động coi test bị bỏ qua là pass.

## 13. Bài tập thực hành

Thiết lập một CI job cho dịch vụ Spring Boot đã có native build:

1. Chạy `nativeCompile` và lưu `native-build.log` cùng `native-build-exit-code.txt`.
2. Chạy `nativeTest`, lưu log, JUnit XML và HTML report.
3. Cố ý làm một test thất bại để xác nhận command trả non-zero và pipeline chuyển sang failed.
4. Cố ý dùng một timeout ngắn để xác nhận log và mã `124` được lưu lại.
5. Chạy native executable với readiness check và một smoke request.
6. Đóng gói/chạy container, lưu `docker logs`, `docker inspect` và exit code.
7. Cấu hình upload artifact chạy ngay cả khi test/build thất bại.
8. Thử một trường hợp test bị skip hoặc test count bằng 0 và xác nhận gate không báo pass.

Mẫu báo cáo:

| Bằng chứng | File hoặc giá trị | Kết quả |
|---|---|---|
| Native build log | `native-build.log` | Có/Không |
| Native build exit code | `native-build-exit-code.txt` | `0`/non-zero |
| Native test log | `native-test.log` | Có/Không |
| JUnit report | XML/HTML | Test count, failure, skipped |
| Application log | `application-smoke.log` | Startup/readiness |
| Container inspect | `container-inspect.json` | Status, exit code, OOM |
| CI artifact | Tên artifact và retention | Đã upload/Chưa |
| Job result | Pass/Fail | Có phản ánh đúng lỗi thử nghiệm? |

## 14. Câu hỏi tự kiểm tra

1. Vì sao exit code và log cần được lưu cùng nhau?
2. Vì sao `tee` có thể làm mất exit code của Gradle nếu không bật `pipefail`?
3. `nativeCompile` thành công có chứng minh native test pass không?
4. Gradle native test report thường nằm ở đâu và vì sao phải kiểm tra path thực tế?
5. Làm thế nào để CI vẫn upload JUnit report sau khi test step trả non-zero?
6. Exit code `137` chứng minh điều gì và không chứng minh điều gì?
7. Vì sao container `Running` chưa có nghĩa ứng dụng đã readiness?
8. Khi nào nên dùng timeout cho native executable và khi nào nên dùng readiness check?
9. Vì sao test count bằng 0 phải được coi là vấn đề?
10. Những dữ liệu nào cần redaction trước khi lưu CI artifact?

## Ghi nhớ

**CI chỉ có thể xác nhận thất bại đáng tin cậy khi giữ đúng exit code, log và test report của từng giai đoạn.** Thu output mà không che giấu lỗi shell, phân biệt build/test/startup/container, dùng readiness check cho server, kiểm tra trạng thái container và upload artifact kể cả khi job fail. Native build thành công là một tín hiệu cần thiết; kết luận cuối cùng phải dựa trên native tests và smoke test thực tế.

## Tài liệu tham khảo

- [Gradle — Testing in Java & JVM projects](https://docs.gradle.org/current/userguide/java_testing.html): test task, JUnit XML và HTML reports.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): console output, stacktrace và cách chạy task.
- [GraalVM Native Build Tools — Gradle Plugin](https://graalvm.github.io/native-build-tools/latest/gradle-plugin): `nativeTest`, `nativeCompile` và cấu hình native build.
- [GraalVM Native Build Tools — Maven Plugin](https://graalvm.github.io/native-build-tools/latest/maven-plugin.html): native test goal và cấu hình Maven.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): kiểm thử ứng dụng Spring Boot.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): health endpoint và readiness state.
- [Docker — Run containers](https://docs.docker.com/reference/cli/docker/container/run/): exit status và cách chạy container.
- [Docker — Inspect containers](https://docs.docker.com/reference/cli/docker/container/inspect/): trạng thái, exit code và thông tin runtime.
- [GitHub Actions — Store and share data with workflow artifacts](https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts): upload và lưu artifact sau khi job kết thúc.
