# Thực hành: Mô phỏng build lỗi, mất kết nối và hai lần triển khai đồng thời

Trong module **DEVOPS_CI_CD_FUNDAMENTALS**, bài thực hành này giúp bạn kiểm tra cách một pipeline phản ứng khi ba sự cố thường gặp xảy ra: build hoặc test thất bại, kết nối tới dịch vụ bị gián đoạn, và hai phiên bản cùng tìm cách triển khai vào một môi trường. Mục tiêu là làm cho lỗi dễ nhận biết, giới hạn ảnh hưởng của lần chạy lỗi và bảo vệ trạng thái đang phục vụ người dùng.

Bạn sẽ chủ động tạo từng sự cố, quan sát kết quả, khôi phục hệ thống rồi áp dụng cơ chế kiểm soát tương ứng. Các ví dụ pipeline dùng GitHub Actions và Gradle; phần mô phỏng cục bộ dùng Bash, Node.js và `curl`. Hãy chạy các lệnh Bash trên Linux, macOS hoặc WSL. Nếu dự án dùng Maven hay công cụ CI/CD khác, thay lệnh build và cú pháp pipeline bằng cơ chế tương đương.

## Kết quả cần đạt

Sau bài thực hành, bạn có thể:

- Nhận biết build/test thất bại qua exit code và log, đồng thời ngăn pipeline tạo artifact hoặc triển khai khi bước kiểm tra chưa đạt.
- Mô phỏng timeout và dịch vụ không thể kết nối; cấu hình timeout cùng số lần retry có giới hạn cho thao tác an toàn.
- Giải thích vì sao hai lần triển khai cùng ghi vào một môi trường có thể ghi đè phiên bản mới bằng phiên bản cũ.
- Tuần tự hóa các lần triển khai, triển khai cùng một artifact đã được kiểm tra và xác minh sức khỏe sau khi phát hành.

## Chuẩn bị

Bạn cần một dự án Java có Gradle Wrapper, JDK 21, Bash, Node.js và `curl`. Phần khóa tệp dùng lệnh `flock` thường có trên Linux. GitHub Actions sẽ chạy trên `ubuntu-latest` trong ví dụ bên dưới.

Kiểm tra công cụ:

```bash
java -version
./gradlew --version
node --version
curl --version
flock --version
```

Nếu dự án không sinh JAR tại `build/libs/`, điều chỉnh đường dẫn artifact trong workflow theo cấu hình đóng gói của dự án. Không đưa thông tin đăng nhập hoặc token thật vào script mô phỏng.

## Tình huống 1: Build hoặc test thất bại

### Tạo lỗi có chủ đích

Chọn một unit test hiện có và tạm thời làm sai giá trị kỳ vọng. Ví dụ, nếu `Calculator.add(2, 2)` trả về `4`, đổi assertion thành:

```java
@Test
void addsTwoNumbers() {
    assertEquals(5, Calculator.add(2, 2)); // Cố ý sai để tạo test failure
}
```

Chạy build và test:

```bash
./gradlew --no-daemon clean test
```

Kết quả mong đợi là Gradle trả về exit code khác `0`, báo test thất bại và chỉ ra test cùng assertion gây lỗi. Trong log, hãy tìm các phần `FAILED`, tên test và expected/actual. Đây là tín hiệu máy có thể dùng để quyết định pipeline có được đi tiếp hay không.

Nếu muốn quan sát exit code một cách tường minh trong Bash:

```bash
./gradlew --no-daemon clean test
build_status=$?
printf 'build exit code: %s\n' "$build_status"
```

Giá trị khác `0` biểu thị bước build/test thất bại. Trong script có `set -e`, lệnh có thể dừng ngay tại bước lỗi; đó thường là hành vi mong muốn của pipeline. Không thêm `|| true` hoặc `continue-on-error` chỉ để làm cho pipeline hiển thị màu xanh, vì cách đó che mất tín hiệu lỗi.

### Quan sát tác động trong pipeline

Một pipeline nên đặt build và test trước bước đóng gói, lưu artifact và triển khai. Khi `clean build` thất bại, job triển khai phụ thuộc vào job này phải được bỏ qua. Artifact của một bản build chưa đạt kiểm tra cũng không được phát hành.

Sửa assertion về giá trị đúng, sau đó chạy lại:

```bash
./gradlew --no-daemon clean build
```

Xác nhận lệnh trả về `0`, toàn bộ test đạt và artifact được tạo theo cấu hình dự án. Giữ lại log của lần chạy lỗi để đối chiếu với lần chạy thành công.

**Điểm cần rút ra:** build lỗi là một trạng thái của pipeline, không phải một cảnh báo để người vận hành tự nhớ. Exit code, quan hệ phụ thuộc giữa các job và điều kiện phát hành phải khiến pipeline tự dừng trước khi triển khai.

## Tình huống 2: Mất kết nối hoặc dịch vụ không phản hồi

Lỗi kết nối có thể xuất hiện khi runner không kết nối được tới máy chủ, DNS hoặc proxy gặp sự cố, dịch vụ đích đang khởi động, hay kết nối được thiết lập nhưng máy chủ không trả lời. Hai biểu hiện thường gặp là kết nối bị từ chối và request hết thời gian chờ. Chúng cần được phân biệt với phản hồi HTTP báo lỗi như `500` hoặc `503`.

### Mô phỏng một dịch vụ bị treo

Mở terminal thứ nhất và chạy một HTTP server không gửi phản hồi. Server vẫn nhận kết nối nhưng để request chờ mãi:

```bash
node -e 'require("http").createServer((_req, _res) => {}).listen(8080, "127.0.0.1")'
```

Mở terminal thứ hai và đặt giới hạn thời gian cho request:

```bash
curl --verbose --connect-timeout 2 --max-time 3 \
  http://127.0.0.1:8080/health
printf 'curl exit code: %s\n' "$?"
```

Request sẽ hết thời gian chờ; `curl` thường trả về mã `28` cho timeout. Dừng server bằng `Ctrl+C`, sau đó chạy lại lệnh `curl`. Lần này kết nối thường bị từ chối và `curl` trả về mã `7`. Như vậy, timeout và không thể thiết lập kết nối là hai tín hiệu khác nhau dù cả hai đều khiến bước kiểm tra thất bại.

### Khôi phục dịch vụ và kiểm tra lại

Khởi động một server trả về HTTP 200:

```bash
node -e 'require("http").createServer((_req, res) => { res.writeHead(200, {"content-type":"text/plain"}); res.end("ok"); }).listen(8080, "127.0.0.1")'
```

Ở terminal thứ hai, gọi endpoint với timeout hữu hạn:

```bash
curl --fail --silent --show-error \
  --connect-timeout 2 --max-time 5 \
  http://127.0.0.1:8080/health
```

Kết quả mong đợi là nội dung `ok` và exit code `0`. Dừng server sau khi hoàn thành mô phỏng.

### Thiết kế retry có giới hạn

Với health check dùng HTTP GET, bạn có thể retry một số lỗi tạm thời. Ví dụ sau giới hạn thời gian kết nối, thời gian mỗi request và tổng thời gian retry:

```bash
curl --fail --silent --show-error \
  --connect-timeout 2 --max-time 5 \
  --retry 2 --retry-delay 1 --retry-max-time 15 \
  "$HEALTH_URL/health"
```

`--retry 2` cho phép tối đa hai lần thử lại sau lần đầu. Khi dịch vụ vẫn không sẵn sàng, lệnh cuối cùng phải trả về mã lỗi để pipeline thất bại. Retry chỉ giảm ảnh hưởng của sự cố thoáng qua; nó không biến một dịch vụ đang hỏng thành dịch vụ khỏe mạnh.

Một số nguyên tắc khi xử lý mất kết nối:

- Đặt timeout cho cả bước kết nối và request. Không để runner chờ vô hạn.
- Chỉ retry hữu hạn, có khoảng nghỉ; cân nhắc exponential backoff và jitter khi nhiều runner có thể cùng retry.
- Ưu tiên retry thao tác đọc hoặc thao tác đã được thiết kế idempotent. Với lệnh triển khai hoặc request ghi dữ liệu, timeout không cho biết máy chủ đã xử lý hay chưa. Hãy kiểm tra trạng thái phát hành trước khi gửi lại, hoặc dùng idempotency key.
- Ghi log URL đích ở mức an toàn, thời gian chờ, số lần thử và mã lỗi. Không in token, mật khẩu hay header xác thực.
- Nếu hết số lần retry, dừng pipeline và giữ nguyên trạng thái thất bại. Không bỏ qua health check để tiếp tục phát hành.

**Điểm cần rút ra:** retry là cơ chế phục hồi có điều kiện. Timeout, số lần thử và tính idempotent phải được thiết kế cùng nhau; retry vô hạn hoặc retry mù một thao tác triển khai có thể làm sự cố nghiêm trọng hơn.

## Tình huống 3: Hai lần triển khai đồng thời

Giả sử phiên bản `release-A` bắt đầu triển khai trước nhưng mất nhiều thời gian hơn. Trong lúc đó, `release-B` được triển khai và hoàn tất nhanh hơn. Nếu cả hai cùng ghi vào một vị trí dùng chung, `release-A` có thể hoàn tất sau và ghi đè `release-B`. Người dùng khi đó thấy phiên bản cũ dù bản mới đã từng được kích hoạt.

### Tái hiện cuộc đua ghi đè

Trong một thư mục tạm, tạo file `deploy-race.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

release="${1:?Cần truyền mã phiên bản}"
delay="${2:-0}"

printf 'Bắt đầu triển khai %s\n' "$release"
sleep "$delay"
tmp_file="current-release.$$"
printf '%s\n' "$release" > "$tmp_file"
mv "$tmp_file" current-release.txt
printf 'Đã kích hoạt %s\n' "$release"
```

Chạy hai tiến trình gần như đồng thời. Phiên bản A mất bốn giây; phiên bản B bắt đầu sau một giây và hoàn tất ngay:

```bash
bash deploy-race.sh release-A 4 &
pid_a=$!
sleep 1
bash deploy-race.sh release-B 0 &
pid_b=$!
wait "$pid_a" "$pid_b"
cat current-release.txt
```

Kết quả cuối thường là `release-A`: B đã ghi trước nhưng A hoàn tất sau và ghi đè. Đây là race condition. Trong hệ thống thật, vùng trạng thái dùng chung có thể là thư mục phát hành, symlink `current`, tag môi trường, bản ghi trong cơ sở dữ liệu hoặc cấu hình của load balancer.

### Tuần tự hóa bằng khóa

Tạo file `deploy-locked.sh` để khóa toàn bộ vùng triển khai. Tiến trình thứ hai phải đợi tiến trình thứ nhất nhả khóa:

```bash
#!/usr/bin/env bash
set -euo pipefail

release="${1:?Cần truyền mã phiên bản}"
delay="${2:-0}"

exec 9>deploy.lock
flock 9

printf 'Đã lấy khóa, triển khai %s\n' "$release"
sleep "$delay"
tmp_file="current-release.$$"
printf '%s\n' "$release" > "$tmp_file"
mv "$tmp_file" current-release.txt
printf 'Đã kích hoạt %s và nhả khóa\n' "$release"
```

Chạy lại hai phiên bản trong cùng thư mục:

```bash
bash deploy-locked.sh release-A 4 &
pid_a=$!
sleep 1
bash deploy-locked.sh release-B 0 &
pid_b=$!
wait "$pid_a" "$pid_b"
cat current-release.txt
```

Vì A lấy khóa trước, B phải chờ đến khi A hoàn tất. Kết quả cuối là `release-B`. Khóa bảo đảm hai tiến trình không cùng sửa trạng thái triển khai trong một thời điểm. Lệnh `mv` thay file tạm bằng file đích trong cùng filesystem, giúp người đọc không nhìn thấy nội dung file bị ghi dở.

Khóa bằng `flock` phù hợp để mô phỏng các tiến trình trên cùng máy và cùng vùng filesystem hỗ trợ khóa. Nó không tự bảo vệ nhiều runner ở các máy khác nhau nếu mỗi runner có filesystem riêng. Với triển khai phân tán, dùng cơ chế khóa/lease ở hệ thống dùng chung hoặc chức năng điều phối deployment của nền tảng. Lease nên có thời hạn và fencing token để một tiến trình cũ đã mất quyền không thể tiếp tục ghi đè trạng thái mới.

### Cấu hình concurrency trong GitHub Actions

Ở cấp job triển khai, khai báo một concurrency group theo môi trường:

```yaml
deploy-production:
  needs: build-test
  if: ${{ needs.build-test.result == 'success' }}
  runs-on: ubuntu-latest
  environment: production
  concurrency:
    group: production-deploy
    cancel-in-progress: false
  steps:
    - uses: actions/checkout@v4
    - uses: actions/download-artifact@v4
      with:
        name: app-${{ github.sha }}
        path: build/libs
    - name: Deploy the verified artifact
      run: ./scripts/deploy.sh
```

Các lần chạy cùng `production-deploy` sẽ không thực thi job triển khai song song. `cancel-in-progress: false` giữ job đang chạy tiếp tục thay vì hủy nó khi có lần chạy mới. Tuy nhiên, GitHub Actions chỉ giữ tối đa một job đang chạy và một job đang chờ trong cùng concurrency group; job chờ cũ có thể bị thay thế khi có job chờ mới, và thứ tự xử lý không được bảo đảm. Nếu yêu cầu phải triển khai mọi phiên bản theo FIFO, hãy dùng hàng đợi phát hành chuyên dụng hoặc bộ điều phối có chính sách thứ tự rõ ràng.

**Điểm cần rút ra:** khóa giải quyết việc hai tiến trình cùng sửa môi trường; chính sách hàng đợi giải quyết thứ tự phát hành. Đây là hai yêu cầu liên quan nhưng không giống nhau. Cần quyết định rõ hệ thống muốn tuần tự hóa mọi phiên bản hay chỉ triển khai phiên bản mới nhất.

## Ghép các kiểm soát vào một pipeline

Ví dụ dưới đây minh họa luồng tối thiểu cho dự án Gradle trên GitHub Actions. Job triển khai chỉ phụ thuộc vào build/test thành công, tải artifact được tạo từ cùng commit và kiểm tra sức khỏe sau triển khai. `scripts/deploy.sh` là script triển khai của dự án; bạn cần kết nối script đó với môi trường thử nghiệm của mình.

```yaml
name: ci-cd-failure-lab

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  build-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Build and test
        run: ./gradlew --no-daemon clean build

      - name: Upload the verified artifact
        uses: actions/upload-artifact@v4
        with:
          name: app-${{ github.sha }}
          path: build/libs/*.jar
          if-no-files-found: error

  deploy-staging:
    needs: build-test
    if: ${{ needs.build-test.result == 'success' }}
    runs-on: ubuntu-latest
    environment: staging
    concurrency:
      group: staging-deploy
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@v4

      - uses: actions/download-artifact@v4
        with:
          name: app-${{ github.sha }}
          path: build/libs

      - name: Confirm artifact exists
        run: test -n "$(find build/libs -maxdepth 1 -type f -name '*.jar' -print -quit)"

      - name: Deploy
        env:
          DEPLOY_TOKEN: ${{ secrets.STAGING_DEPLOY_TOKEN }}
        run: ./scripts/deploy.sh

      - name: Check service health
        env:
          HEALTH_URL: ${{ secrets.STAGING_HEALTH_URL }}
        run: |
          test -n "$HEALTH_URL"
          curl --fail --silent --show-error \
            --connect-timeout 2 --max-time 5 \
            --retry 2 --retry-delay 1 --retry-max-time 15 \
            "$HEALTH_URL/health"
```

Trước khi dùng workflow, xác nhận dự án thực sự tạo JAR ở `build/libs/*.jar`, hai secret được cấu hình trong repository/environment và script triển khai nhận đúng artifact. Nếu dự án không tạo JAR, đổi đường dẫn upload/download và lệnh kiểm tra theo loại artifact thực tế. Không xây dựng lại ứng dụng trong job deploy: hãy triển khai chính artifact đã vượt qua build/test để tránh việc mã được kiểm tra khác với mã được phát hành.

Luồng xử lý khi có sự cố:

| Sự cố | Tín hiệu cần quan sát | Hành vi mong đợi |
|---|---|---|
| Compile hoặc test lỗi | Gradle exit code khác `0`, log có lỗi | Job build thất bại; upload artifact và deploy không chạy |
| Dịch vụ không phản hồi | `curl` timeout, thường là mã `28` | Request dừng theo timeout; retry hữu hạn; health check cuối thất bại thì job deploy thất bại |
| Không kết nối được máy chủ | `curl` không mở được kết nối, thường là mã `7` | Ghi nhận lỗi kết nối; thử lại trong giới hạn; không đánh dấu deploy thành công |
| Hai lần deploy cùng môi trường | Hai job cùng concurrency group | Chỉ một job triển khai chạy tại một thời điểm; chính sách hàng đợi quyết định job nào được chờ |
| Deploy xong nhưng health check lỗi | Endpoint không trả HTTP thành công | Phát hành được đánh dấu lỗi; kích hoạt quy trình điều tra hoặc rollback đã định nghĩa |

## Kiểm tra kết quả thực hành

Hoàn thành từng mục và ghi lại bằng chứng trong log hoặc ghi chú của bạn:

- [ ] Tạo một test failure có chủ đích, xác định test lỗi và exit code khác `0`.
- [ ] Xác nhận job deploy bị bỏ qua khi job build/test thất bại.
- [ ] Mô phỏng server không phản hồi và phân biệt timeout với connection refused.
- [ ] Khôi phục server, gọi health endpoint thành công và kiểm tra exit code `0`.
- [ ] Chứng minh retry có giới hạn kết thúc bằng lỗi khi dịch vụ vẫn không sẵn sàng.
- [ ] Chạy hai script triển khai không khóa và quan sát phiên bản cũ có thể ghi đè phiên bản mới.
- [ ] Chạy lại với khóa và xác nhận hai lần ghi được tuần tự hóa.
- [ ] Kiểm tra concurrency group của pipeline dùng đúng tên môi trường và không hủy job đang triển khai.
- [ ] Xác nhận artifact được tạo một lần, gắn với commit và được dùng lại trong job deploy.
- [ ] Kiểm tra health check sau deploy có timeout và kết quả thất bại được phản ánh trong pipeline.

## Câu hỏi tự đánh giá

1. Vì sao một pipeline không nên tiếp tục triển khai khi unit test thất bại, dù bước đóng gói vẫn có thể tạo được file JAR?
2. Khi `curl` timeout sau một request ghi dữ liệu, vì sao gửi lại request ngay có thể tạo ra tác động lặp?
3. Trong mô phỏng race condition, vì sao phiên bản bắt đầu trước lại có thể trở thành phiên bản cuối cùng được kích hoạt?
4. `flock` trên một máy giải quyết được vấn đề nào và còn thiếu điều gì khi runner chạy trên nhiều máy?
5. `cancel-in-progress: false` bảo vệ job đang chạy ra sao, và giới hạn của một concurrency group là gì nếu nhiều phiên bản đang chờ?
6. Vì sao nên triển khai artifact đã được kiểm tra thay vì build lại trong job deploy?

Một pipeline đáng tin cậy phải làm rõ trạng thái thành công/thất bại, giới hạn thời gian chờ, kiểm soát số lần thử và bảo vệ vùng triển khai dùng chung. Sau bài lab, hãy áp dụng các nguyên tắc này vào môi trường staging trước, quan sát log và lịch sử phát hành, rồi mới đưa cấu hình đã kiểm chứng vào production.
