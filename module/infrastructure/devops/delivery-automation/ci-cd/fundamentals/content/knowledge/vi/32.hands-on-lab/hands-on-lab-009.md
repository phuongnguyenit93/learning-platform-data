# Diễn tập quay lui và xác nhận dịch vụ phục hồi

Một lần triển khai hoàn tất về mặt kỹ thuật chưa chắc đã tạo ra một dịch vụ hoạt động đúng. Container có thể đang chạy, pipeline có thể báo xanh, nhưng một luồng nghiệp vụ quan trọng vẫn trả lỗi hoặc độ trễ đã vượt ngưỡng chấp nhận. Vì vậy, năng lực phát hành an toàn cần bao gồm cả khả năng quay lui về phiên bản đã biết là tốt và xác nhận bằng bằng chứng rằng dịch vụ thực sự phục hồi.

Trong bài thực hành này, bạn sẽ triển khai một dịch vụ mẫu, ghi nhận phiên bản đang hoạt động, đưa vào một bản phát hành có lỗi được mô phỏng, nhận diện tín hiệu cần dừng phát hành, quay lại artifact trước đó và kiểm tra nhiều lớp sau rollback. Toàn bộ bài lab chạy cục bộ bằng Docker Compose; không cần cụm Kubernetes hay tài khoản cloud.

## Mục tiêu thực hành

Sau khi hoàn thành, bạn có thể:

- Phân biệt trạng thái triển khai thành công với trạng thái dịch vụ đã phục hồi.
- Lưu lại định danh artifact đang chạy để có thể quay lại đúng bản đã phát hành.
- Dùng health check, smoke test và tín hiệu nghiệp vụ để phát hiện bản phát hành lỗi.
- Thực hiện rollback bằng artifact cũ đã có sẵn, không tạo lại artifact từ mã nguồn hiện tại.
- Xác minh phiên bản, trạng thái sẵn sàng, luồng nghiệp vụ và tính ổn định sau rollback.
- Ghi lại mốc thời gian, nguyên nhân, hành động và bằng chứng để cải thiện quy trình CI/CD.

## Bối cảnh và tiêu chí hoàn thành

Bạn phụ trách `orders-api`, một dịch vụ HTTP nhỏ. Phiên bản `1.0.0` đang hoạt động bình thường. Nhóm chuẩn bị phát hành `1.1.0`, nhưng phiên bản này có lỗi khiến endpoint sẵn sàng trả HTTP 503 và thao tác tạo đơn hàng trả HTTP 500. Tiến trình vẫn chạy, vì vậy liveness check tiếp tục thành công. Đây là tình huống thường gặp: kiểm tra tiến trình đơn thuần không đủ để chứng minh nghiệp vụ đang phục vụ tốt.

| Giai đoạn | Điều cần chứng minh |
|---|---|
| Trước phát hành | Có artifact `1.0.0`, biết chính xác image ID và các kiểm tra nghiệp vụ đều đạt |
| Sau phát hành lỗi | Phát hiện được readiness hoặc luồng nghiệp vụ thất bại dù container vẫn healthy |
| Khi rollback | Dịch vụ được khởi động lại từ artifact `1.0.0` đã lưu, không build lại |
| Sau rollback | Image ID đúng, readiness và thao tác nghiệp vụ thành công liên tiếp, dịch vụ ổn định trong khoảng quan sát |

Một lệnh rollback trả mã thoát 0 chỉ cho biết công cụ đã hoàn thành thao tác của nó. Chỉ đánh dấu phục hồi khi các kiểm tra sau triển khai xác nhận dịch vụ đang chạy đúng phiên bản, đáp ứng yêu cầu nghiệp vụ và không còn vi phạm ngưỡng vận hành.

## Chuẩn bị

Bạn cần:

- Docker Engine đang chạy và Docker Compose v2 (`docker compose version`).
- Terminal PowerShell, Bash hoặc shell tương đương.
- `curl` để gửi HTTP request. Trên Windows, dùng `curl.exe` để tránh alias `curl` của Windows PowerShell.
- Quyền tạo thư mục và chạy container cục bộ.

Kiểm tra công cụ:

```bash
docker --version
docker compose version
curl --version
```

Trong PowerShell, dùng `curl.exe --version` ở dòng cuối.

Tạo workspace cho bài lab:

```text
rollback-drill/
├── compose.yaml
└── app/
    ├── Dockerfile
    └── server.js
```

Tạo thư mục `rollback-drill`, sau đó tạo `app` bên trong. Các đoạn mã dưới đây là nội dung chính xác của từng file. Nếu bạn dùng PowerShell, có thể tạo thư mục bằng `New-Item -ItemType Directory -Force app`; trên Bash dùng `mkdir -p app`.

## 1. Tạo dịch vụ mô phỏng

Tạo file `app/server.js`:

```javascript
const http = require("node:http");

const version = process.env.APP_VERSION || "unknown";
const failMode = process.env.FAIL_MODE === "true";

function sendJson(response, statusCode, payload) {
  response.writeHead(statusCode, {
    "content-type": "application/json; charset=utf-8",
  });
  response.end(JSON.stringify(payload));
}

const server = http.createServer((request, response) => {
  const pathname = new URL(request.url || "/", "http://localhost").pathname;

  if (pathname === "/health/live") {
    return sendJson(response, 200, { live: true, version });
  }

  if (pathname === "/health/ready") {
    return sendJson(response, failMode ? 503 : 200, {
      ready: !failMode,
      version,
    });
  }

  if (pathname === "/orders") {
    return sendJson(response, failMode ? 500 : 200, {
      service: "orders-api",
      version,
      result: failMode ? "simulated_failure" : "accepted",
    });
  }

  if (pathname === "/") {
    return sendJson(response, 200, { service: "orders-api", version });
  }

  return sendJson(response, 404, { error: "not_found", version });
});

server.listen(8080, "0.0.0.0", () => {
  console.log(`orders-api ${version} listening on port 8080; failMode=${failMode}`);
});
```

Ứng dụng có ba loại endpoint với mục đích khác nhau:

- `/health/live` cho biết tiến trình HTTP còn sống. Endpoint này luôn trả 200 nếu server vẫn nhận request.
- `/health/ready` cho biết phiên bản có sẵn sàng nhận traffic hay không. Ở chế độ lỗi, endpoint trả 503.
- `/orders` mô phỏng một thao tác nghiệp vụ. Ở chế độ lỗi, endpoint trả 500.

Endpoint `/` trả tên dịch vụ và phiên bản để bạn đối chiếu artifact đang chạy. Biến `FAIL_MODE` chỉ là công tắc mô phỏng lỗi trong bài lab; trong hệ thống thật, lỗi có thể đến từ code, cấu hình, dependency, migration hoặc dữ liệu.

Tạo file `app/Dockerfile`:

```dockerfile
FROM node:22-alpine

WORKDIR /app

ARG APP_VERSION=1.0.0
ARG FAIL_MODE=false

ENV APP_VERSION=${APP_VERSION}
ENV FAIL_MODE=${FAIL_MODE}

COPY server.js ./server.js

EXPOSE 8080

CMD ["node", "server.js"]
```

Hai build argument được đóng vào image. Nhờ đó, `1.0.0` và `1.1.0` là hai artifact có tag riêng; phiên bản lỗi không được tạo ra bằng cách thay đổi một biến môi trường của cùng container đang chạy.

Tạo file `compose.yaml` tại thư mục gốc `rollback-drill`:

```yaml
services:
  api:
    image: rollback-drill/orders-api:${APP_VERSION:-1.0.0}
    build:
      context: ./app
      args:
        APP_VERSION: ${APP_VERSION:-1.0.0}
        FAIL_MODE: ${FAIL_MODE:-false}
    ports:
      - "127.0.0.1:8080:8080"
    healthcheck:
      test:
        - CMD
        - node
        - -e
        - "require('node:http').get('http://127.0.0.1:8080/health/live', (response) => process.exit(response.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"
      interval: 5s
      timeout: 2s
      retries: 3
      start_period: 3s
    restart: unless-stopped
```

Port 8080 chỉ được bind vào loopback của máy đang chạy lab. Health check của Compose cố ý kiểm tra liveness; nó không kiểm tra readiness hay luồng nghiệp vụ. Nhờ vậy, bạn có thể quan sát một container ở trạng thái `healthy` nhưng bản phát hành vẫn không đạt smoke test. Trong môi trường thật, cần thiết kế liveness và readiness theo đúng vai trò, đồng thời giữ các kiểm tra nghiệp vụ ở cổng chất lượng sau triển khai.

## 2. Phát hành phiên bản tốt và lưu bằng chứng ban đầu

Mở terminal tại thư mục chứa `compose.yaml`. Đặt phiên bản và chế độ hoạt động cho bản đầu tiên.

PowerShell:

```powershell
$env:APP_VERSION = "1.0.0"
$env:FAIL_MODE = "false"
docker compose config
docker compose up -d --build --wait --wait-timeout 60
```

Bash:

```bash
export APP_VERSION=1.0.0
export FAIL_MODE=false
docker compose config
docker compose up -d --build --wait --wait-timeout 60
```

Lệnh `docker compose config` giúp kiểm tra cấu hình sau khi nội suy biến. Lệnh `up` build image `rollback-drill/orders-api:1.0.0`, khởi động container và chờ health check liveness đạt. Nếu phiên bản Docker Compose của bạn chưa hỗ trợ `--wait`, chạy `docker compose up -d --build`, sau đó theo dõi `docker compose ps` cho đến khi container có trạng thái healthy.

Kiểm tra trạng thái và các endpoint:

```bash
docker compose ps
curl -fsS http://127.0.0.1:8080/
curl -fsS http://127.0.0.1:8080/health/live
curl -fsS http://127.0.0.1:8080/health/ready
curl -fsS http://127.0.0.1:8080/orders
```

Trên Windows, thay `curl` bằng `curl.exe`. Cả bốn request phải trả HTTP 200. Phần thân ở endpoint `/` phải cho biết `version` là `1.0.0`; endpoint `/orders` phải có `result` là `accepted`.

Ghi lại image ID của artifact tốt. Lệnh sau hoạt động trong PowerShell và Bash:

```bash
docker image inspect rollback-drill/orders-api:1.0.0 --format '{{.Id}}'
```

Lưu giá trị này vào nhật ký bài lab cùng thời điểm phát hành. Tag giúp con người tham chiếu phiên bản; image ID hoặc digest mới là định danh cụ thể của artifact đã tạo. Trong registry thực tế, hãy lưu digest bất biến cùng commit, pipeline run và môi trường triển khai.

Điền thông tin ban đầu:

| Trường ghi nhận | Giá trị cần lưu |
|---|---|
| Dịch vụ | `orders-api` |
| Môi trường | local lab |
| Phiên bản hiện tại | `1.0.0` |
| Image tag | `rollback-drill/orders-api:1.0.0` |
| Image ID | Kết quả từ `docker image inspect` |
| Liveness | HTTP 200 |
| Readiness | HTTP 200 |
| Nghiệp vụ `/orders` | HTTP 200, `accepted` |

Đây là mốc chuẩn để so sánh sau rollback. Nếu chưa lưu artifact và bằng chứng của phiên bản tốt, bạn chưa có cơ sở chắc chắn để quay lại đúng trạng thái trước phát hành.

## 3. Phát hành phiên bản lỗi có kiểm soát

Mô phỏng bản phát hành `1.1.0` có lỗi. Ở bước này, `FAIL_MODE=true` được đóng vào image mới.

PowerShell:

```powershell
$env:APP_VERSION = "1.1.0"
$env:FAIL_MODE = "true"
docker compose config
docker compose up -d --build --wait --wait-timeout 60
```

Bash:

```bash
export APP_VERSION=1.1.0
export FAIL_MODE=true
docker compose config
docker compose up -d --build --wait --wait-timeout 60
```

Compose tạo image `rollback-drill/orders-api:1.1.0` và thay container bằng phiên bản mới. Lệnh `up --wait` vẫn có thể hoàn tất thành công vì health check chỉ gọi `/health/live`, trong khi tiến trình vẫn sống. Đây là tín hiệu cho thấy trạng thái của nền tảng triển khai chưa đủ để kết luận bản phát hành tốt.

Kiểm tra từng endpoint:

```bash
docker compose ps
curl -i http://127.0.0.1:8080/health/live
curl -i http://127.0.0.1:8080/health/ready
curl -i http://127.0.0.1:8080/orders
```

Kết quả mong đợi:

| Endpoint | HTTP dự kiến | Diễn giải |
|---|---:|---|
| `/health/live` | 200 | Tiến trình vẫn sống |
| `/health/ready` | 503 | Dịch vụ chưa sẵn sàng nhận traffic |
| `/orders` | 500 | Luồng nghiệp vụ quan trọng đang lỗi |

Ở bước này dùng `curl -i` để nhìn thấy status code. Không thêm `-f`, vì `curl -f` sẽ trả mã thoát khác 0 khi nhận HTTP 4xx hoặc 5xx; ta đang cần quan sát chính phản hồi lỗi được mô phỏng.

Lưu image ID của bản lỗi để có bằng chứng hai artifact khác nhau:

```bash
docker image inspect rollback-drill/orders-api:1.1.0 --format '{{.Id}}'
```

## 4. Ra quyết định rollback

Trong một quy trình phát hành thật, tiêu chí rollback cần được thống nhất trước khi triển khai. Không nên chờ đến khi có sự cố mới tranh luận xem lỗi nào đủ nghiêm trọng. Một bộ tiêu chí tối thiểu có thể gồm:

| Tín hiệu | Ví dụ điều kiện dừng phát hành |
|---|---|
| Kiểm tra quan trọng thất bại | Smoke test của luồng đăng nhập, thanh toán hoặc tạo đơn không đạt |
| Tỷ lệ lỗi tăng | Tỷ lệ HTTP 5xx vượt ngưỡng đã định trong một cửa sổ quan sát |
| Độ trễ tăng | p95 hoặc p99 vượt SLO trong thời gian liên tục |
| Readiness thất bại | Instance không sẵn sàng hoặc liên tục bị loại khỏi traffic |
| Tác động dữ liệu | Phát hiện ghi sai, mất dữ liệu hoặc vi phạm bất biến nghiệp vụ |

Với bài lab, chỉ cần readiness trả 503 hoặc `/orders` trả 500 là đủ kích hoạt rollback. Không cần đợi cả hai điều kiện cùng xảy ra. Khi đã xác nhận lỗi thuộc bản phát hành mới, ghi lại thời điểm phát hiện và lý do kích hoạt. Nếu hệ thống có khả năng điều phối traffic, hãy giảm hoặc dừng traffic vào phiên bản lỗi trong lúc khôi phục.

Phân biệt ba quyết định:

1. **Rollback ứng dụng:** chuyển traffic hoặc workload về artifact ứng dụng đã biết là tốt.
2. **Khôi phục dữ liệu:** xử lý dữ liệu đã bị thay đổi sai. Rollback binary không tự đảo ngược giao dịch hay migration.
3. **Forward fix:** phát hành một phiên bản sửa lỗi mới khi quay lui không an toàn hoặc không tương thích với trạng thái dữ liệu hiện tại.

Bài lab chỉ mô phỏng rollback ứng dụng. Trong production, hãy xác định trước khả năng tương thích ngược của schema, cấu hình, message và dữ liệu trước khi chọn rollback.

## 5. Quay lại artifact tốt đã lưu

Chuyển cấu hình Compose về đúng tag của phiên bản `1.0.0`. Quan trọng: dùng `--no-build` để Compose sử dụng image cũ đã được tạo và lưu tại bước 2. Không build lại source code ở thời điểm rollback rồi gắn tag cũ, vì việc đó có thể tạo ra một artifact khác với bản đã được xác nhận tốt.

PowerShell:

```powershell
$env:APP_VERSION = "1.0.0"
$env:FAIL_MODE = "false"
docker compose config
docker compose up -d --no-build --wait --wait-timeout 60
```

Bash:

```bash
export APP_VERSION=1.0.0
export FAIL_MODE=false
docker compose config
docker compose up -d --no-build --wait --wait-timeout 60
```

Nếu lệnh báo không tìm thấy image, dừng và kiểm tra tag cùng image ID đã ghi ở bước 2. Không tự động build một image mới rồi xem đó là rollback thành công. Với hệ thống dùng registry, artifact trước đó cần được giữ lại và có thể pull bằng digest đã lưu; chính sách dọn dẹp image phải bảo đảm không xóa mất phiên bản còn cần cho rollback.

Kiểm tra trạng thái container và artifact:

```bash
docker compose ps
docker compose images
docker image inspect rollback-drill/orders-api:1.0.0 --format '{{.Id}}'
```

Image ID cuối phải trùng với image ID đã ghi trước khi phát hành `1.1.0`. Nếu tag trỏ đến ID khác, bạn chưa chứng minh được mình đã quay lại đúng artifact.

## 6. Xác nhận dịch vụ thực sự phục hồi

Không kết thúc diễn tập ngay khi container chuyển sang healthy hoặc lệnh rollback trả về thành công. Hãy kiểm tra theo nhiều lớp, từ hạ tầng đến hành vi dịch vụ.

### 6.1. Kiểm tra tiến trình và phiên bản

```bash
docker compose ps
curl -fsS http://127.0.0.1:8080/
curl -fsS http://127.0.0.1:8080/health/live
```

Container phải ở trạng thái đang chạy và healthy. Endpoint `/` phải trả `version` là `1.0.0`. Nếu container healthy nhưng endpoint gốc cho thấy `1.1.0`, cấu hình rollback chưa đưa workload về đúng phiên bản.

### 6.2. Kiểm tra readiness và nghiệp vụ

```bash
curl -fsS http://127.0.0.1:8080/health/ready
curl -fsS http://127.0.0.1:8080/orders
```

Cả hai request phải thành công. Readiness phải trả `ready: true`; thao tác `/orders` phải trả `result: accepted`. Đây là bằng chứng rằng dịch vụ đã sẵn sàng và luồng nghiệp vụ mô phỏng hoạt động trở lại.

Trên PowerShell, có thể kiểm tra thêm phiên bản bằng đoạn sau:

```powershell
$body = curl.exe -fsS http://127.0.0.1:8080/
if ($LASTEXITCODE -ne 0 -or $body -notmatch '"version":"1\.0\.0"') {
    throw "Rollback chưa phục hồi đúng phiên bản 1.0.0"
}
```

Trên Bash:

```bash
body="$(curl -fsS http://127.0.0.1:8080/)"
printf '%s\n' "$body"
printf '%s' "$body" | grep -q '"version":"1.0.0"' || {
  echo "Rollback chưa phục hồi đúng phiên bản 1.0.0" >&2
  exit 1
}
```

### 6.3. Kiểm tra liên tiếp trong cửa sổ ổn định

Một request thành công có thể chỉ là kết quả nhất thời. Hãy lặp lại các kiểm tra quan trọng để phát hiện lỗi chập chờn hoặc quá trình khởi động chưa hoàn tất.

PowerShell:

```powershell
1..10 | ForEach-Object {
    curl.exe -fsS http://127.0.0.1:8080/health/ready | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Readiness thất bại ở lượt $_" }

    curl.exe -fsS http://127.0.0.1:8080/orders | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Nghiệp vụ thất bại ở lượt $_" }

    Start-Sleep -Seconds 2
}
```

Bash:

```bash
for attempt in $(seq 1 10); do
  curl -fsS http://127.0.0.1:8080/health/ready >/dev/null || exit 1
  curl -fsS http://127.0.0.1:8080/orders >/dev/null || exit 1
  sleep 2
done
```

Mười lượt kiểm tra là mức tối thiểu của bài lab, không phải cửa sổ SLO chuẩn cho production. Với dịch vụ thật, hãy quan sát đủ lâu để bao phủ nhịp traffic, tác vụ nền và dependency quan trọng. Đối chiếu tỷ lệ lỗi, độ trễ, saturation, queue lag và các cảnh báo liên quan trong hệ thống giám sát.

### 6.4. Kiểm tra log và dấu hiệu bất thường

```bash
docker compose logs --since 5m --tail 100 api
```

Tìm lỗi khởi động, lỗi kết nối, vòng lặp restart hoặc thông báo cho thấy tiến trình vẫn xử lý request theo cấu hình lỗi. Trong production, kết hợp log với metric và trace theo cùng release ID hoặc correlation ID để xác định traffic đã thực sự chuyển về phiên bản tốt.

Chỉ xác nhận phục hồi khi các lớp kiểm tra sau đều đạt:

| Lớp xác minh | Bằng chứng cần có |
|---|---|
| Artifact | Image ID hoặc digest trùng artifact đã biết là tốt |
| Workload | Instance đang chạy, không restart liên tục, health check đạt |
| Readiness | Instance sẵn sàng nhận traffic |
| Nghiệp vụ | Smoke test của luồng quan trọng thành công |
| Ổn định | Các lần kiểm tra liên tiếp đạt; error rate và latency trở lại ngưỡng |
| Dữ liệu và dependency | Không còn backlog bất thường, lỗi ghi dữ liệu hoặc dependency bị suy giảm |

Nếu một lớp chưa đạt, trạng thái nên là **đang khôi phục** hoặc **rollback chưa xác nhận**. Tiếp tục điều tra, chuyển sang phương án forward fix hoặc runbook khôi phục phù hợp; không đóng sự cố chỉ vì công cụ triển khai báo thành công.

## 7. Ghi nhận diễn tập và đo thời gian phục hồi

Một diễn tập có giá trị khi nhóm có thể tái dựng điều gì đã xảy ra và biết bước nào cần cải thiện. Ghi lại ít nhất các mốc sau:

| Mốc | Nội dung |
|---|---|
| T0 | Bắt đầu triển khai `1.1.0` |
| T1 | Kiểm tra đầu tiên phát hiện readiness hoặc nghiệp vụ thất bại |
| T2 | Quyết định dừng phát hành và kích hoạt rollback |
| T3 | Bắt đầu chuyển workload về `1.0.0` |
| T4 | Artifact `1.0.0` đã chạy và readiness đạt |
| T5 | Smoke test nghiệp vụ và cửa sổ ổn định đều đạt |

Thời gian từ lúc phát hiện sự cố đến khi bắt đầu rollback là thời gian nhận diện và ra quyết định. Thời gian từ lúc kích hoạt rollback đến khi T5 đạt phản ánh thời gian khôi phục thực tế của diễn tập. Hãy thống nhất cách đo trước khi so sánh giữa các lần diễn tập; đừng chỉ đo thời gian lệnh `docker compose up` chạy xong.

Mẫu nhật ký:

| Trường | Giá trị điền trong diễn tập |
|---|---|
| Release lỗi | `1.1.0` và image ID của nó |
| Artifact quay lui | `1.0.0` và image ID đã lưu trước phát hành |
| Trigger | Readiness 503 và/hoặc `/orders` 500 |
| Thời điểm phát hiện (T1) | Ghi timestamp có múi giờ |
| Thời điểm kích hoạt rollback (T2) | Ghi timestamp có múi giờ |
| Thời điểm xác nhận phục hồi (T5) | Ghi timestamp có múi giờ |
| Kết quả smoke test | Số lượt đạt/tổng số lượt |
| Tình trạng sau rollback | Error rate, latency, cảnh báo và backlog nếu có |
| Người điều phối | Vai trò chịu trách nhiệm ra quyết định và xác nhận |
| Việc cần cải thiện | Hành động cụ thể, người phụ trách và hạn hoàn thành |

Ví dụ, nếu T1 là 10:02, T2 là 10:04 và T5 là 10:09 cùng ngày, nhóm đã mất 2 phút để quyết định và 5 phút từ lúc kích hoạt rollback đến lúc xác nhận phục hồi. Đây là số liệu của một lần diễn tập; cần nhiều lần đo và cùng một quy ước trước khi dùng để đặt mục tiêu vận hành.

## 8. Đưa rollback vào quy trình CI/CD

Một pipeline có thể mô hình hóa luồng phát hành an toàn như sau:

```text
Commit đã được kiểm tra
        |
        v
Build một lần -> Gắn version + commit -> Lưu artifact bất biến
        |
        v
Ghi nhận artifact hiện tại làm phiên bản quay lui
        |
        v
Triển khai candidate
        |
        v
Chờ workload sẵn sàng
        |
        v
Smoke test + kiểm tra metric sau triển khai
        |
        +---- đạt ----> Quan sát ổn định ----> Hoàn tất phát hành
        |
        +---- lỗi ----> Dừng/giảm traffic -> Triển khai artifact trước
                                      |
                                      v
                          Smoke test lại + quan sát
                                      |
                            +---------+---------+
                            |                   |
                           đạt                chưa đạt
                            |                   |
                       Xác nhận phục hồi   Kích hoạt runbook sự cố
```

Trong pipeline thật, cần lưu `PREVIOUS_IMAGE_DIGEST` trước khi cập nhật workload. Bước rollback phải dùng đúng digest này, có quyền truy cập registry và được bảo vệ khỏi bước dọn dẹp artifact. Không dựa vào tag `latest` vì tag có thể đã trỏ sang bản mới. Nếu phát hành theo canary hoặc blue-green, có thể chuyển traffic về nhóm instance cũ trước khi xóa hoặc thay thế chúng.

Một cổng sau triển khai nên thực hiện tuần tự:

1. Chờ workload sẵn sàng theo readiness probe.
2. Gọi smoke test cho các luồng nghiệp vụ quan trọng.
3. Đọc metric trong cửa sổ quan sát đã định nghĩa.
4. Nếu có điều kiện rollback, ghi nhận trigger và chuyển về artifact đã lưu.
5. Chạy lại toàn bộ kiểm tra phục hồi trên phiên bản quay lui.
6. Chỉ đóng pipeline khi đã xác nhận phục hồi; nếu rollback hoặc xác minh thất bại, giữ trạng thái thất bại và báo người trực vận hành.

Điều kiện của bước rollback phải phản ánh trạng thái thực tế: chỉ rollback khi candidate đã được triển khai hoặc traffic đã được chuyển sang candidate. Pipeline cũng cần phân biệt lỗi do smoke test, lỗi hạ tầng triển khai và lỗi của chính thao tác rollback để người vận hành chọn đúng runbook.

## 9. Những tình huống rollback không tự giải quyết được

Rollback là một biện pháp phục hồi quan trọng, nhưng không đảo ngược mọi tác động của một bản phát hành.

| Tình huống | Rủi ro | Cách chuẩn bị |
|---|---|---|
| Database migration không tương thích ngược | Code cũ không đọc được schema mới hoặc dữ liệu đã chuyển đổi | Dùng chiến lược expand-contract; tách migration phá hủy thành giai đoạn riêng và chỉ xóa cột sau khi không còn phiên bản cũ |
| Cấu hình hoặc secret đã đổi | Binary cũ chạy với cấu hình mới vẫn có thể lỗi | Phiên bản hóa cấu hình, lưu cấu hình tốt đã biết và kiểm tra tương thích |
| Giao dịch đã tạo side effect | Đơn hàng, thanh toán hoặc message đã ghi không tự biến mất khi quay lui code | Thiết kế idempotency, đối soát và compensating transaction; không giả định rollback ứng dụng là rollback dữ liệu |
| Artifact cũ bị xóa | Không thể khởi động đúng phiên bản trước | Retention policy theo số bản phát hành và thời gian; kiểm tra khả năng pull artifact trước khi phát hành |
| Dependency bên ngoài đang lỗi | Phiên bản ứng dụng cũ vẫn không hoạt động | Kiểm tra dependency, circuit breaker, fallback và runbook độc lập |
| Rollback nhầm môi trường | Có thể làm gián đoạn dịch vụ khác hoặc đưa bản cũ vào sai nơi | Xác minh account, cluster, namespace, service và release ID trước thao tác; dùng guard và quyền phù hợp |
| Chính thao tác rollback thất bại | Hệ thống tiếp tục ở trạng thái lỗi hoặc không xác định | Chuẩn bị runbook thủ công, quyền truy cập khẩn cấp, người chịu trách nhiệm và phương án cô lập traffic |

Với thay đổi dữ liệu có tính phá hủy, cần đánh giá trước liệu rollback có an toàn hay phải forward fix. Nếu có nghi ngờ về tính toàn vẹn dữ liệu, ưu tiên bảo toàn bằng chứng, hạn chế ghi tiếp và gọi đúng quy trình xử lý dữ liệu; không chạy một lệnh đảo ngược tùy tiện.

## 10. Xử lý lỗi thường gặp trong bài lab

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Docker Compose không tìm thấy Docker daemon | Docker Engine chưa chạy | Khởi động Docker Desktop hoặc daemon rồi thử `docker info` |
| Cổng 8080 đã được sử dụng | Ứng dụng khác chiếm cổng | Dừng tiến trình phù hợp hoặc đổi cả port mapping và URL kiểm tra cho nhất quán |
| `up --wait` thành công nhưng smoke test thất bại | Health check chỉ kiểm tra liveness | Kiểm tra readiness và endpoint nghiệp vụ; đây là tình huống lỗi có chủ đích của lab |
| `up --no-build` báo thiếu image | Tag `1.0.0` chưa được build hoặc đã bị xóa | Kiểm tra `docker image ls` và image ID ban đầu; không gắn tag cũ cho một bản build mới |
| Sau rollback vẫn thấy version `1.1.0` | Biến `APP_VERSION` chưa được đặt lại trong đúng terminal hoặc container chưa được thay thế | Chạy `docker compose config`, kiểm tra `docker compose ps` và response ở `/` |
| Readiness đạt nhưng nghiệp vụ vẫn lỗi | Readiness probe quá nông hoặc dependency nghiệp vụ chưa sẵn sàng | Thêm smoke test vào luồng quan trọng và kiểm tra dependency liên quan |
| Lệnh curl trả mã thoát khác 0 | HTTP 4xx/5xx hoặc không kết nối được | Dùng `curl -i` để xem status và kiểm tra log; chỉ dùng `-f` trong các kiểm tra mong đợi HTTP 2xx |

## 11. Dọn dẹp môi trường

Sau khi lưu nhật ký và kết quả diễn tập, dừng container:

```bash
docker compose down
```

Nếu muốn giải phóng image của bài lab sau khi không còn cần bằng chứng, có thể xóa hai tag đã tạo:

```bash
docker image rm rollback-drill/orders-api:1.0.0 rollback-drill/orders-api:1.1.0
```

Không chạy lệnh xóa image trước khi ghi lại image ID và kết quả. Trong hệ thống thật, chỉ dọn artifact theo retention policy đã phê duyệt; luôn giữ đủ artifact để đáp ứng yêu cầu khôi phục.

## 12. Checklist hoàn thành

- [ ] Đã triển khai `1.0.0` và xác nhận liveness, readiness, `/orders` đều thành công.
- [ ] Đã ghi lại image ID của `1.0.0` trước khi phát hành bản mới.
- [ ] Đã triển khai `1.1.0` và quan sát được liveness 200 nhưng readiness 503 hoặc nghiệp vụ 500.
- [ ] Đã ghi nhận lý do và thời điểm kích hoạt rollback.
- [ ] Đã quay lại `1.0.0` bằng `--no-build`.
- [ ] Image ID sau rollback trùng image ID đã ghi ban đầu.
- [ ] Readiness và luồng nghiệp vụ thành công qua nhiều lượt kiểm tra liên tiếp.
- [ ] Đã kiểm tra log và các tín hiệu vận hành liên quan.
- [ ] Đã ghi thời gian phục hồi, bằng chứng và điểm cần cải thiện.
- [ ] Đã dọn dẹp môi trường sau khi hoàn tất ghi nhận.

## Câu hỏi tự đánh giá

1. Vì sao `docker compose up --wait` có thể thành công trong khi bản phát hành vẫn không đạt yêu cầu?
2. Image tag và image ID khác nhau như thế nào? Vì sao rollback cần dùng artifact đã lưu thay vì build lại source code?
3. Những kiểm tra nào chứng minh tiến trình còn sống, dịch vụ sẵn sàng và luồng nghiệp vụ hoạt động? Chúng bổ sung cho nhau ra sao?
4. Nếu smoke test đạt nhưng tỷ lệ lỗi hoặc p95 vẫn vượt SLO, bạn sẽ quyết định thế nào và cần quan sát thêm điều gì?
5. Vì sao rollback ứng dụng không thể tự khôi phục dữ liệu đã bị migration phá hủy hoặc side effect đã phát sinh?
6. Bạn sẽ lưu thông tin nào trong pipeline để rollback có thể tự động, có thể kiểm toán và có thể xác minh?

## Kết quả mong đợi

Bạn hoàn thành bài lab khi đã chứng minh được toàn bộ chu trình: triển khai một phiên bản tốt và lưu định danh artifact; phát hành một phiên bản lỗi; phát hiện lỗi bằng kiểm tra readiness hoặc nghiệp vụ; quay lui về đúng artifact đã lưu; sau đó xác nhận phiên bản, sức khỏe, nghiệp vụ và tính ổn định của dịch vụ. Nhật ký diễn tập phải cho biết thời điểm phát hiện, thời điểm kích hoạt rollback, thời điểm phục hồi được xác nhận và hành động cải thiện tiếp theo.
