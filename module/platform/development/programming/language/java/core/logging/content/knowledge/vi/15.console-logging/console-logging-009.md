# Thu thập log container trong Java: từ stdout/stderr đến hệ thống logging tập trung

## 1. Thu thập log container nghĩa là gì?

Khi chạy ứng dụng Java trong Docker hoặc Kubernetes, log không còn chỉ nằm trong một terminal hoặc tệp cục bộ cố định. Một container có thể bị khởi động lại, thay thế, chuyển sang node khác hoặc bị xóa sau một đợt triển khai. Nếu chỉ mở terminal và xem những dòng log đang xuất hiện, người vận hành rất dễ mất bối cảnh khi có lỗi.

**Thu thập log container** là quá trình đưa các sự kiện do ứng dụng phát ra — thường qua **stdout** và **stderr** — đến một nơi có thể **lưu giữ, truy vấn, phân tích và cảnh báo** độc lập với vòng đời container.

Mục tiêu của bài là hiểu rõ:

1. Ứng dụng Java nên **phát log** theo cách nào trong container.
2. Container runtime và Docker logging driver **tiếp nhận stdout/stderr** ra sao.
3. Kubernetes kubelet và định dạng **CRI container logs** đóng vai trò gì.
4. **Node-level agent, sidecar và đẩy trực tiếp** khác nhau thế nào.
5. Chọn định dạng **văn bản một dòng hoặc JSON Lines**, thêm metadata, xử lý stack trace.
6. Quản lý **rotation, buffering, mất hoặc trùng log, bảo mật và chi phí**.
7. Tự chạy ví dụ Java 17 trong Docker rồi quan sát với `docker logs`, cùng một cách triển khai Pod kiểm chứng được trên cụm thử nghiệm.

### Cần phân biệt ba việc

| Việc | Ai thường phụ trách | Bằng chứng |
| --- | --- | --- |
| **Phát log** | Ứng dụng Java và logging framework | `System.out`, `System.err`, Logger/Appender |
| **Lưu log ngắn hạn gần container** | Container runtime, logging driver, kubelet | Log local trên node, `docker logs`, `kubectl logs` |
| **Thu và lưu tập trung** | Agent/collector và backend | Có dữ liệu trong hệ thống truy vấn sau restart, reschedule hoặc node lỗi |

**Nhìn thấy dòng log trong `docker logs` hoặc `kubectl logs` chưa chứng minh sự kiện đã được lưu bền ở hệ thống tập trung.** Hai lệnh đó chủ yếu phục vụ truy xuất log mà runtime/kubelet hiện đang cung cấp.

## 2. Dòng chảy điển hình từ Java tới collector

```text
Java service
   |
   +-- LOG.info(...) / LOG.error(...)
   |        |
   |        v
   |   Logger + Level + Filter
   |        |
   |        v
   |   Console Appender/Handler + Layout
   |        |
   +---- stdout / stderr
                 |
                 v
           Container runtime
                 |
                 v
         Local container log
         (driver hoặc CRI file)
                 |
                 v
          Node logging agent
          (DaemonSet/collector)
                 |
           Parse + enrich + batch
                 |
                 v
          Central log backend
                 |
                 v
       Search / dashboard / alert
```

Các tầng có trách nhiệm riêng:

- **Logger** nhận sự kiện, mức `INFO`/`WARN`/`ERROR` và tham số.
- **Console Appender/Handler** xuất dữ liệu ra luồng chuẩn.
- **Layout/Encoder** tạo chuỗi văn bản hay JSON; nó không tự quyết định nơi lưu bền.
- **Container runtime** chuyển hướng stdout/stderr tới cơ chế log được cấu hình.
- **Collector** đọc log, giải mã định dạng, bổ sung metadata và gửi đến backend.
- **Backend** quản lý index, thời gian lưu, phân quyền, truy vấn và cảnh báo.

Luồng trên là kiến trúc điển hình, không phải quy định mọi ứng dụng đều phải dùng cùng các thành phần. Một ứng dụng có thể gửi log trực tiếp qua OTLP/HTTP hoặc socket, hoặc một sidecar có thể đọc tệp chung. Nhưng **stdout/stderr + node-level agent** là lựa chọn dễ vận hành cho nhiều ứng dụng container.

## 3. stdout và stderr trong container

Trong Java, các luồng chuẩn gồm `System.in`, `System.out` và `System.err`. Với logging, hai luồng quan trọng là:

- **stdout**: thường dùng cho kết quả hoặc log ứng dụng mà runtime sẽ thu.
- **stderr**: thường dùng cho thông báo lỗi hoặc chẩn đoán.
- **Level khác stream**: một sự kiện `ERROR` vẫn có thể được Console Appender xuất ra stdout; một sự kiện `INFO` của JUL `ConsoleHandler` mặc định lại đi stderr.

Khi chạy container, runtime có thể thu **cả stdout lẫn stderr**. Ví dụ `docker logs` thường hiển thị dữ liệu từ cả hai, vì vậy thứ tự nhìn thấy trên một terminal **không phải bằng chứng** cho luồng gốc của mỗi dòng.

Một quy tắc thiết kế hữu ích:

- Đối với **dịch vụ Java chạy nền**, có thể cấu hình một appender xuất các log được chấp nhận thành một dòng text/JSON trên stdout. Nếu cần chia stream theo mức, thiết kế filter tương ứng để tránh trùng.
- Đối với **CLI xuất JSON hoặc dữ liệu máy đọc qua stdout**, không trộn log text vào stdout dữ liệu. Ghi chẩn đoán qua stderr hoặc kênh khác.
- Không sử dụng `System.out.println` rải rác như một framework logging đầy đủ: nó không tự cung cấp filter, timestamp, thread, logger name, exception cause hay cấu hình thống nhất.

**Lưu ý JUL:** `java.util.logging.ConsoleHandler` mặc định ghi `System.err`. Muốn dùng JUL cho stdout, có thể dùng `StreamHandler(System.out, formatter)` với vòng đời và flush được kiểm soát; `StreamHandler.close()` có thể đóng luôn stream gốc. Trong những framework như Log4j2 hoặc Logback, một ConsoleAppender có thể chọn stdout trực tiếp qua cấu hình.

## 4. Ví dụ Java 17 chạy độc lập và trong Docker

Ví dụ này chủ ý **không dùng thư viện logging ngoài JDK** để tập trung minh họa **hành trình stdout/stderr**. Mã xuất ba sự kiện JSON một dòng, hai sự kiện ở stdout và một sự kiện ở stderr. Chuỗi JSON là **hằng số cố định để xác định output**, không phải hướng dẫn tự ghép dữ liệu người dùng thành JSON. Trong ứng dụng thật cần encoder/logger chuyên dụng.

### 4.1. Tệp `ContainerLogDemo.java`

```java
public final class ContainerLogDemo {
    private ContainerLogDemo() {
    }

    public static void main(String[] args) {
        System.out.println(
                "{\"level\":\"INFO\",\"event\":\"application_started\","
                + "\"service\":\"orders\"}");

        System.err.println(
                "{\"level\":\"WARN\",\"event\":\"dependency_slow\","
                + "\"service\":\"orders\",\"duration_ms\":250}");

        System.out.println(
                "{\"level\":\"INFO\",\"event\":\"order_processed\","
                + "\"service\":\"orders\",\"order_id\":\"ORD-101\","
                + "\"outcome\":\"SUCCESS\"}");
    }
}
```

Chạy trực tiếp bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ContainerLogDemo.java
java ContainerLogDemo
```

**Stdout chính xác, theo thứ tự trong chính stdout:**

```json
{"level":"INFO","event":"application_started","service":"orders"}
{"level":"INFO","event":"order_processed","service":"orders","order_id":"ORD-101","outcome":"SUCCESS"}
```

**Stderr chính xác:**

```json
{"level":"WARN","event":"dependency_slow","service":"orders","duration_ms":250}
```

Nếu terminal gộp hai luồng khi hiển thị, dòng `WARN` có thể xuất hiện giữa hai dòng `INFO`, hoặc thứ tự hiển thị có thể khác vì hai stream được thu độc lập. **Không khẳng định thứ tự tổng thể giữa stdout và stderr** chỉ dựa vào thứ tự lời gọi `println`.

Bạn có thể kiểm chứng bằng shell Linux/macOS:

```bash
java ContainerLogDemo > stdout.log 2> stderr.log
cat stdout.log
cat stderr.log
```

Hai file nhận đúng những dòng thuộc từng stream. `stdout.log` và `stderr.log` là file do **shell chuyển hướng**, không phải do code Java mở bằng `FileWriter`.

### 4.2. `Dockerfile`

Trong cùng thư mục với `ContainerLogDemo.java`, tạo tệp `Dockerfile`:

```dockerfile
FROM eclipse-temurin:17-jdk AS build
WORKDIR /src
COPY ContainerLogDemo.java .
RUN javac -encoding UTF-8 ContainerLogDemo.java

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /src/ContainerLogDemo.class .
ENTRYPOINT ["java", "-cp", "/app", "ContainerLogDemo"]
```

Đây là **multi-stage build**:

1. Stage `build` dùng JDK 17 để biên dịch.
2. Stage chạy dùng JRE 17, chỉ copy `ContainerLogDemo.class` đã được biên dịch.
3. Dạng `ENTRYPOINT` mảng JSON chạy Java trực tiếp, không cần thêm shell trung gian chỉ để khởi động.
4. Java vẫn viết vào stdout/stderr của process bên trong container, và Docker runtime tiếp nhận những stream đó.
5. Trong ví dụ không có file log do ứng dụng tự ghi trong container; vì vậy tắt/xóa container không làm thay đổi logic định dạng sự kiện.

Bản build này dùng tag image công khai của Eclipse Temurin; các tag có thể cập nhật nội dung theo thời gian. Muốn build bit-for-bit ổn định hoặc kiểm soát chuỗi cung ứng, hãy pin image digest và kiểm tra nguồn base image theo quy định của dự án.

### 4.3. Build và chạy bằng Docker

Cần Docker Engine/Desktop hoạt động và có quyền chạy container:

```bash
docker build -t container-log-demo:1.0 .
docker run --name java-log-demo \
  --log-driver json-file \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  container-log-demo:1.0
```

Trong shell PowerShell, có thể đặt lệnh `docker run` trên **một dòng** thay vì dùng dấu gạch chéo ngược để nối dòng:

```powershell
docker build -t container-log-demo:1.0 .
docker run --name java-log-demo --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 container-log-demo:1.0
```

Đợi container kết thúc (chương trình minh họa chạy rất ngắn), sau đó:

```bash
docker logs java-log-demo
docker logs --timestamps java-log-demo
docker inspect --format '{{.HostConfig.LogConfig.Type}}' java-log-demo
docker rm java-log-demo
```

`docker inspect` được mong đợi hiển thị `json-file` vì lệnh chạy đã chọn driver đó. `docker logs` thường hiển thị cả ba dòng JSON do ứng dụng phát ra (không có phần wrapper ở `json-file`), nhưng **không nên coi thứ tự xen kẽ stdout/stderr là bất biến**. `--timestamps` bổ sung mốc thời gian từ dữ liệu runtime, không phải do code Java tự tạo.

Không dùng `--rm` ngay trong lệnh `docker run` nếu bạn muốn gọi `docker logs java-log-demo` **sau khi** tiến trình kết thúc; cờ đó có thể xóa container trước khi bạn kịp tra cứu log. Xóa bằng `docker rm` sau khi kiểm chứng.

**Đầu ra của `docker build`, tải image và thông báo của Docker** phụ thuộc môi trường. Các chuỗi có thể khẳng định chính xác là stdout/stderr của **chương trình Java** tại phần 4.1; không khẳng định toàn bộ dòng mà Docker CLI hiển thị là một chuỗi cố định.

## 5. Docker logging driver là gì?

Docker cung cấp **logging drivers** để thu và định tuyến output của container. Nếu không chỉ định, Docker Engine thường dùng driver mặc định **`json-file`**; có thể kiểm tra cấu hình thực tế bằng:

```bash
docker info --format '{{.LoggingDriver}}'
```

Một số driver thường gặp:

| Driver | Đặc tính | Cần chú ý |
| --- | --- | --- |
| `json-file` | Lưu stdout/stderr của mỗi container dưới dạng các bản ghi JSON nội bộ | Mặc định phổ biến; cần rotation để tránh đầy đĩa khi log nhiều |
| `local` | Lưu log cục bộ ở định dạng tối ưu hơn về dung lượng | Docker khuyến nghị cho nhiều tình huống Docker Engine độc lập; có rotation mặc định |
| `journald` | Gửi thông tin tới systemd journal | Phụ thuộc cấu hình hệ điều hành và quyền truy cập |
| `syslog` | Chuyển đến syslog | Cần cấu hình endpoint và giao thức |
| `fluentd` | Chuyển log đến Fluentd collector | Phụ thuộc collector và chính sách lỗi |
| `gelf` | Gửi theo Graylog Extended Log Format | Collector phải nhận đúng giao thức |
| `none` | Không ghi log qua Docker driver | `docker logs` không có log để trả về cho container đó |

Lựa chọn driver ảnh hưởng cách `docker logs` và các công cụ thu thập truy xuất log. **Không tự đọc/chỉnh sửa file nội bộ của Docker logging driver** bằng script ứng dụng; Docker quản lý những file này và thao tác ngoài có thể gây hành vi không mong muốn.

### `json-file` là wrapper của runtime, không phải JSON của ứng dụng

Khi dùng `json-file`, một bản ghi nội bộ có dạng minh họa:

```json
{
  "log": "{\"level\":\"INFO\",\"event\":\"application_started\",\"service\":\"orders\"}\n",
  "stream": "stdout",
  "time": "2026-11-09T12:00:00.000000000Z"
}
```

Ở đây:

- `log` chứa **dữ liệu do ứng dụng in ra**, vốn là một chuỗi JSON.
- `stream` cho biết dữ liệu đến từ `stdout` hay `stderr`.
- `time` là timestamp do driver/runtime thêm (giá trị ngày giờ ở ví dụ chỉ minh họa).
- Đối tượng JSON bao ngoài **không có nghĩa collector đã parse sâu** chuỗi JSON bên trong thuộc tính `log` thành các trường `event` và `service`.

Một pipeline thường cần hai giai đoạn: **giải mã wrapper của runtime** rồi **parse payload ứng dụng** nếu payload là JSON có cấu trúc. Nếu chỉ lưu `log` như một chuỗi, dashboard không tự tìm kiếm được `order_id` như trường riêng.

### Cấu hình rotation để tránh đầy đĩa

Ví dụ dùng trong Docker Engine `daemon.json`:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

Ở file `daemon.json`, các giá trị `log-opts` có dạng **chuỗi**, kể cả `"3"`. Các thiết lập daemon mặc định thường chỉ áp dụng cho **container tạo mới** sau khi cấu hình được áp dụng; container đã tồn tại không tự nhận cấu hình mới. Cách thay đổi cấu hình và khởi động lại daemon phụ thuộc môi trường quản trị.

Docker tài liệu chính thức lưu ý rằng `json-file` là mặc định vì lý do tương thích và **không có rotation mặc định** trong nhiều cấu hình; với Docker Engine độc lập, driver `local` có rotation mặc định là lựa chọn đáng cân nhắc. Nhưng nếu nền tảng đã triển khai một pipeline/kubelet nhất định, không tự đổi driver mà chưa kiểm tra yêu cầu runtime.

**Rotation là giới hạn lưu cục bộ**, không phải cơ chế đồng bộ dữ liệu lên kho tập trung. Nếu collector không kịp đọc trước khi file cũ bị xóa, một phần log có thể mất.

## 6. Docker blocking và non-blocking: độ tin cậy có đánh đổi

Docker logging driver có cơ chế truyền output theo **blocking** hoặc **non-blocking** tùy driver/cấu hình.

- **Blocking** là chế độ mặc định phổ biến: khi driver hoặc nơi nhận chậm, việc ghi stdout/stderr có thể bị chặn, tác động đến đường xử lý ứng dụng.
- **Non-blocking** đưa bản ghi qua buffer trung gian có dung lượng giới hạn; khi buffer đầy, các bản ghi mới có thể bị **bỏ** thay vì chặn ứng dụng.
- **Non-blocking không phải “vừa không chặn vừa không bao giờ mất log”**. Cần chọn giữa độ trễ ứng dụng, độ bền log và khả năng đo giám sát.

Ví dụ Docker, với `json-file`:

```bash
docker run --name buffered-log-demo \
  --log-driver json-file \
  --log-opt mode=non-blocking \
  --log-opt max-buffer-size=4m \
  container-log-demo:1.0
```

Đây là **lệnh minh họa**, không phải khuyến nghị bật non-blocking mặc định cho mọi hệ thống. Với bài demo rất ngắn, khó tái hiện điều kiện buffer đầy; cần kiểm thử tải có kiểm soát để quan sát trade-off.

Các câu hỏi vận hành cần trả lời:

1. Mất vài dòng `DEBUG` có chấp nhận được không?
2. Mất một sự kiện `ERROR` có ảnh hưởng điều tra sự cố quan trọng không?
3. Nếu collector bị nghẽn, yêu cầu HTTP có được phép chậm vì ghi log không?
4. Có metric/cảnh báo cho dropped log, queue occupancy, retry và tốc độ ingest không?
5. Có cần một cơ chế **audit/event store bền vững riêng** cho sự kiện bắt buộc lưu không?

Trong hệ thống thật, **log quan sát** và **bằng chứng giao dịch** không nên bị đánh đồng. Việc `LOG.info("payment_completed")` đã chạy không chứng minh dữ liệu thanh toán đã commit hoặc collector đã lưu bền.

## 7. Kubernetes thu log container ra sao?

Trong Kubernetes, container runtime tiếp nhận stdout/stderr của các container, còn kubelet cho phép truy xuất log qua API; lệnh phổ biến là `kubectl logs`. Kubelet và runtime dùng cơ chế ghi log theo **Container Runtime Interface (CRI)**.

Tài liệu Kubernetes nêu:

- Log ứng dụng đơn giản nhất thường đi qua **stdout/stderr** của container.
- Mặc định trên Linux, kubelet hướng runtime ghi log container trong khu vực `/var/log/pods` của node.
- Kubelet quản lý **log rotation** theo các thông số cấu hình.
- `kubectl logs` thường đọc thông tin từ log local của node; nó **không phải kho lưu trữ cluster-level**.
- Nếu Pod bị evict hoặc node mất, log local có thể biến mất cùng vòng đời node/Pod.
- Để lưu lâu dài và truy vấn xuyên node, cần **backend lưu trữ riêng**, ví dụ pipeline có agent/collector.

```text
Pod: orders-api container
      |
 stdout/stderr
      |
      v
Container runtime + CRI log
      |
      v
Node local log files
  /var/log/pods/...
      |
      +--> kubelet API --> kubectl logs
      |
      +--> DaemonSet agent
                    |
                    v
            Central collector/backend
```

Một điều dễ nhầm: `kubectl logs` có thể hiện cả stdout và stderr trong một luồng trình bày. Khả năng query tách riêng stream phụ thuộc phiên bản và tính năng được kích hoạt; đừng suy rằng lệnh mặc định cho biết mỗi dòng thuộc stream nào nếu không có metadata.

### CRI container log format

Một bản ghi local theo CRI có dạng khái niệm:

```text
<timestamp> <stream> <tag> <content>
```

Ví dụ:

```text
2026-11-09T12:00:00.123456789Z stdout F {"level":"INFO","event":"application_started","service":"orders"}
2026-11-09T12:00:00.223456789Z stderr F {"level":"WARN","event":"dependency_slow","service":"orders","duration_ms":250}
```

Đây là **ví dụ minh họa của file do runtime ghi trên node**, không phải stdout nguyên văn của Java hoặc đầu ra chính xác của `kubectl logs`.

- `timestamp`: thời điểm do runtime ghi, thường theo chuẩn RFC 3339 với độ chính xác cao.
- `stdout` / `stderr`: stream nguồn.
- `F`: bản ghi đầy đủ theo framing CRI.
- `P`: fragment **partial** khi bản ghi bị chia; collector phải có chiến lược xử lý fragment để không tạo các event sai.
- `content`: payload của ứng dụng, có thể là text hoặc JSON trên một dòng.

Đừng dùng một regex chỉ bắt đầu bằng `"{"` để parse file CRI từ đầu: trước payload còn có timestamp/stream/tag. Collector cần **parser cho container log format**, sau đó mới parse JSON ứng dụng nếu muốn các trường độc lập.

## 8. Ví dụ chạy trên Kubernetes Pod

Ví dụ `Dockerfile` ở phần 4 đã tạo image `container-log-demo:1.0`. Để chạy trên Kubernetes, image đó phải được **cung cấp tới các node**: push lên registry được cluster truy cập hoặc nạp vào cluster thử nghiệm như kind.

### 8.1. Manifest `pod.yaml`

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: java-log-demo
  labels:
    app: java-log-demo
spec:
  restartPolicy: Never
  containers:
    - name: demo
      image: container-log-demo:1.0
      imagePullPolicy: IfNotPresent
```

Đây là **Pod thử nghiệm đơn giản**, không phải deployment cho dịch vụ liên tục. Nó chạy Java rồi hoàn tất nên phase của Pod có thể là `Succeeded`; không có service/port hoặc volume cần thiết.

Nếu dùng **kind** và đã xây image trong Docker local:

```bash
kind load docker-image container-log-demo:1.0
kubectl apply -f pod.yaml
kubectl get pod java-log-demo
kubectl logs pod/java-log-demo -c demo
kubectl logs pod/java-log-demo -c demo --timestamps
```

Lệnh `kind load docker-image` giả định bạn đã cài kind và đang dùng cluster kind mặc định. Nếu cluster có tên khác, cần chọn đúng cluster. Với Kubernetes ngoài kind, hãy push image đến registry mà node có quyền pull và sửa `image` trong manifest; **không** mong cluster từ xa nhìn thấy một image chỉ tồn tại trên laptop.

Dòng `kubectl logs` thường chứa ba message JSON của ứng dụng theo khả năng lưu local, nhưng **không khẳng định thứ tự xen kẽ hai stream hay timestamp là cố định**. Nếu Pod không chạy vì `ImagePullBackOff`, kiểm tra phân phối image và registry, không đổ lỗi ngay cho logging.

Khi kết thúc thử nghiệm:

```bash
kubectl delete pod java-log-demo
```

Sau khi xóa Pod, không coi log local của Pod đó là nguồn lưu lâu dài. Nếu cần xem sự kiện sau khi Pod bị xóa, phải có giải pháp cluster-level logging đã thu từ trước.

### 8.2. Một số lệnh kiểm tra hữu ích

```bash
kubectl logs pod/java-log-demo -c demo
kubectl logs pod/java-log-demo -c demo --timestamps
kubectl logs pod/java-log-demo -c demo --tail=50
kubectl logs pod/java-log-demo -c demo --since=10m
```

Với một dịch vụ chạy lâu, `kubectl logs -f` giúp theo dõi log mới. Nếu container có lần chạy trước sau restart, `kubectl logs --previous` có thể giúp truy xuất log của lần trước **nếu kubelet còn giữ bản đó**. Nó không phải kho lưu tất cả phiên bản container đã từng chạy.

**Giới hạn cần nhớ:** Kubernetes tài liệu hiện hành ghi rõ `kubectl logs` chỉ cung cấp nội dung **file log hiện hành mới nhất** của container theo cơ chế kubelet, ngay cả khi node đã rotation nhiều file. Đừng dùng kết quả `kubectl logs` để khẳng định toàn bộ lịch sử log vẫn còn. Một Pod bị evict có thể mất log local và node lỗi cũng có thể làm log không thể truy xuất.

## 9. Rotation và retention trong Kubernetes

Kubelet quản lý rotation file log container theo cấu hình. Những trường thường gặp:

| Trường cấu hình kubelet | Ý nghĩa | Giá trị mặc định được tài liệu Kubernetes nêu |
| --- | --- | --- |
| `containerLogMaxSize` | Giới hạn kích thước mỗi file log của container | `10Mi` |
| `containerLogMaxFiles` | Số file log được giữ cho mỗi container | `5` |
| `containerLogMaxWorkers` | Mức song song công việc rotation | Phụ thuộc cấu hình/phiên bản |
| `containerLogMonitorInterval` | Chu kỳ kiểm tra rotation | Phụ thuộc cấu hình/phiên bản |

Những giá trị trên là **mặc định tài liệu tham khảo**, không được dùng để phỏng đoán thông số của cụm đang chạy. Quản trị viên có thể thay đổi; môi trường có cấu hình hoặc bản phát hành khác nhau.

Ví dụ, nếu ứng dụng ghi 40 MiB, node rotation theo 10 MiB, thì `kubectl logs` có thể chỉ trả nội dung file cuối cùng, không phải toàn bộ 40 MiB.

Phân biệt:

- **Rotation:** giới hạn dung lượng file log trên node.
- **Retention tại backend:** chính sách lưu trữ dữ liệu đã được collector gửi tới hệ thống tập trung.
- **Sampling/drop policy:** quyết định bản ghi nào được chọn hoặc loại bỏ ở các tầng xử lý.
- **Backup/audit:** bảo đảm lưu dữ liệu quan trọng; không đồng nghĩa rotation hay retention bình thường.

Không chỉnh sửa trực tiếp các file CRI đang được runtime/kubelet quản lý để “chữa” log. Agent nên dùng công cụ tail/parser tương thích với rotation và theo dõi offset theo chính sách.

## 10. Ba mô hình thu thập log trong Kubernetes

Kubernetes mô tả ba cách tiếp cận phổ biến để thực hiện cluster-level logging.

| Mô hình | Cách vận hành | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| **Node-level agent / DaemonSet** | Một agent trên từng node đọc log của các container trên node đó | Không cần sửa code ứng dụng; chia sẻ chi phí thu log giữa nhiều Pod | Cần quyền đọc log host, parser, buffering và cấu hình bảo mật |
| **Sidecar logging container** | Một container bổ trợ đọc file/socket của ứng dụng hoặc chuyển log riêng sang stdout | Phù hợp ứng dụng cũ chỉ ghi file; tách pipeline theo Pod | Tăng CPU/RAM/IO, quản lý volume, có nguy cơ ghi dữ liệu trùng |
| **Đẩy trực tiếp từ ứng dụng** | Appender/SDK gửi log tới backend/collector qua mạng | Kiểm soát giao thức và một số metadata ngay trong ứng dụng | Ứng dụng phụ thuộc mạng/collector, retry/backpressure, khó thống nhất nếu nhiều thư viện |

### 10.1. Node-level agent

Đây là kiến trúc thường dùng khi nhiều ứng dụng đã ghi stdout/stderr:

```text
Node A                                   Node B
  Pod orders                               Pod payments
      |                                        |
  CRI log files                           CRI log files
      |                                        |
  Logging agent (DaemonSet)              Logging agent (DaemonSet)
      |                                        |
      +------------------+---------------------+
                         |
                         v
                   Central backend
```

Agent có thể là Fluent Bit, Vector hoặc OpenTelemetry Collector có receiver phù hợp. Nó đọc file ở node, parse định dạng container, bổ sung metadata như namespace/pod/container, rồi gửi sự kiện đến backend.

**Lưu ý về quyền:** agent thường cần mount đường dẫn log của host vào Pod và có quyền đọc tương ứng. Không tự cấp `privileged: true` hoặc quyền toàn cluster nếu agent không cần. Thiết kế RBAC, hostPath, network policy và phân quyền secret theo nguyên tắc tối thiểu.

### 10.2. Sidecar

Sidecar hữu ích với một ứng dụng không thể đổi khỏi việc ghi file hoặc có nguồn log đặc biệt. Một sidecar có thể tail file chung rồi in ra stdout của chính nó để tận dụng pipeline node-level hiện có.

Nhưng việc đọc file rồi in lại stdout có thể làm **tăng gấp đôi lưu trữ cục bộ** (file gốc và CRI log của sidecar). Nếu agent của node vừa đọc file gốc vừa thu stdout sidecar, kho tập trung còn có thể nhận **hai bản của cùng sự kiện**.

Đừng thêm sidecar chỉ vì muốn log ra stdout trong một ứng dụng Java đã có ConsoleAppender.

### 10.3. Gửi trực tiếp

Một ứng dụng có thể dùng Log4j2 SocketAppender, HTTP/OTLP exporter hoặc một công cụ khác để đẩy log trực tiếp. Cần lập chính sách timeout, TLS, retry, buffer và phản ứng khi collector không sẵn sàng.

**Không suy ra TCP hoặc TLS đồng nghĩa log được lưu bền.** Một lần ghi socket thành công không phải ACK rằng backend đã index và giữ sự kiện. Nếu yêu cầu không mất log, thiết kế lưu bền và acknowledgment chuyên dụng, không chỉ dựa vào lời gọi logger.

## 11. OpenTelemetry Collector và filelog receiver

**OpenTelemetry Collector** là một lựa chọn cho node-level collection. Với bản phân phối có **`filelog` receiver** (chẳng hạn Collector Contrib hoặc bản Kubernetes tương ứng), agent có thể tail file log của container và gửi vào một pipeline gồm receiver, processor và exporter.

Một ví dụ ý tưởng của receiver:

```yaml
receivers:
  filelog:
    include:
      - /var/log/pods/*/*/*.log
    include_file_path: true
    operators:
      - id: container-parser
        type: container
```

Đây **chỉ là snippet**, không phải một Collector config đầy đủ: nó chưa có `service.pipelines.logs`, processor, exporter, credentials, mount hostPath và RBAC. Receiver phải có quyền đọc các đường dẫn thực trên node, và phiên bản/distribution Collector phải hỗ trợ operator `type: container`.

Operator container parser được thiết kế để xử lý định dạng file log container tương ứng và có thể giải mã thông tin stream/metadata hữu ích. Sau khi parse outer CRI format, pipeline còn có thể cần parse JSON payload của ứng dụng nếu muốn tách `event`/`order_id` thành trường thực.

### Ví dụ Helm preset

OpenTelemetry Collector Helm chart có lựa chọn preset:

```yaml
mode: daemonset

presets:
  logsCollection:
    enabled: true
```

Đây là **một đoạn `values.yaml` minh họa**, không phải cấu hình triển khai đầy đủ cho production. Phải chọn image/distribution có `filelog` receiver, cấu hình **exporter tới backend thật**, xác thực/TLS, resource limits và kiểm tra cấu hình chart hiện hành.

Một điểm rất quan trọng: nếu collector thu **stdout của chính collector** trong khi exporter debug lại in tất cả log đã nhận ra stdout, có thể hình thành **vòng lặp log tăng bùng nổ**. Khi dùng preset, cần hiểu chế độ exclude log collector và đảm bảo không cho dữ liệu ingest quay lại chính receiver.

### Nguyên tắc xử lý ở agent

- Lưu offset/checkpoint theo khả năng của agent để giảm mất/trùng dữ liệu khi restart.
- Xử lý rotation: file cũ biến mất hoặc file bị truncate cần chính sách cụ thể.
- Giới hạn memory/queue và cung cấp retry khi backend chậm.
- Phân biệt lỗi parse với lỗi vận chuyển; cần metric/cảnh báo cho cả hai.
- Không tự giả định exactly-once: gửi lại sau timeout có thể gây trùng dù giải pháp cố tránh mất.
- Kiểm soát nhãn và cardinality để không tạo vô số series/index từ ID thay đổi ở từng request.

## 12. Structured logging: một sự kiện trên một dòng

Để collector dễ parse, log JSON một sự kiện trên một dòng (**JSON Lines/NDJSON**) thường là lựa chọn tốt khi hạ tầng hỗ trợ:

```json
{"timestamp":"2026-11-09T12:00:00Z","level":"INFO","service":"orders","event":"order_processed","order_id":"ORD-101","outcome":"SUCCESS","correlation_id":"req-7a"}
```

Đây là **mẫu JSON minh họa**, không phải đảm bảo mọi logger Java đều tạo nội dung giống hệt.

Nên giữ ổn định:

| Trường | Ý nghĩa | Gợi ý |
| --- | --- | --- |
| `timestamp` | Thời điểm sự kiện tại ứng dụng hoặc tầng thu | Định dạng có timezone, thường UTC |
| `level` | Mức log | `INFO`, `WARN`, `ERROR`… theo framework |
| `service` | Danh tính ứng dụng | Tên ổn định, không nhét ID request vào tên |
| `event` | Loại sự kiện | `order_processed`, `payment_retry` |
| `order_id` | ID nghiệp vụ có giá trị cho điều tra | Không dùng làm label tăng cardinality nếu không cần |
| `outcome` | Kết quả | Tập giá trị có quy ước |
| `reason_code` | Mã lý do | Tập mã ổn định, không là câu lỗi tự do |
| `correlation_id` / `trace_id` | Nối các log cùng request/trace | Được truyền qua các boundary phù hợp |
| `exception` | Thông tin lỗi/stack trace | Mã hóa vào JSON theo encoder để không vỡ dòng |

Với **Java logging thực tế**, đừng xây JSON bằng cộng chuỗi chứa dữ liệu người dùng; cần encoder/layout có xử lý dấu nháy kép, backslash, newline và kiểu dữ liệu. Ví dụ phần 4 chỉ in **hằng JSON đã kiểm tra trước** để minh họa stream.

Một encoder JSON có thể chứa stack trace dưới dạng **một chuỗi JSON có ký tự newline đã escape**, nhờ vậy một LogEvent vẫn là một dòng NDJSON. Nếu dùng text formatter tạo stack trace nhiều dòng, collector cần **multiline aggregation** có quy tắc rõ; nếu không, một exception có thể bị biến thành hàng chục event rời.

## 13. Log4j2 và Logback cho Java container

### 13.1. Log4j2 ConsoleAppender

Trong Log4j2, ConsoleAppender cho phép chọn đích `SYSTEM_OUT`. Một cấu hình dùng **JSON Template Layout**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <JsonTemplateLayout/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

Đây là file `log4j2.xml` **có cấu trúc cấu hình đầy đủ**, nhưng để chạy cần cả `log4j-api`, `log4j-core` và dependency **`log4j-layout-template-json`** có phiên bản tương thích. Layout quyết định schema JSON; `target="SYSTEM_OUT"` quyết định stream. **Không giả định đầu ra có cùng tên trường với mẫu JSON ở phần 12** khi chưa kiểm tra template/encoder.

Một cấu hình text đơn giản hơn chỉ cần PatternLayout và Core:

```xml
<Console name="CONSOLE" target="SYSTEM_OUT">
    <PatternLayout charset="UTF-8"
        pattern="%d{ISO8601} %-5p %c - %enc{%m}{CRLF}%n"/>
</Console>
```

Đây là **snippet Appender**, không phải file XML độc lập; gắn vào `<Appenders>` và tham chiếu ở logger/root. `%enc{%m}{CRLF}` giúp escape CR/LF trong message để giảm log injection qua message; nó không tự che bí mật hoặc bảo vệ dữ liệu từ mọi converter khác.

### 13.2. Logback ConsoleAppender

Với ứng dụng SLF4J dùng Logback, `logback.xml` có thể chứa:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level %logger{0} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Đây là **file Logback hoàn chỉnh về cấu trúc**, nhưng chỉ có hiệu lực nếu ứng dụng đang dùng phiên bản Logback/SLF4J tương thích. Pattern text này không tự biến mỗi dòng thành JSON. Nếu cần JSON thật, dùng encoder JSON tương thích và cấu hình schema.

### 13.3. SLF4J API khác provider

Nếu code gọi `org.slf4j.Logger.info(...)`, bản thân API SLF4J không quyết định stdout/stderr. Provider/backend mới làm điều đó.

Ví dụ `slf4j-simple` mặc định ghi ra stderr, nhưng có thể đặt:

```properties
org.slf4j.simpleLogger.logFile=System.out
```

trong `simplelogger.properties` của runtime. Cấu hình này dành cho **SimpleLogger**, không thay đổi đích của Logback hoặc Log4j2.

Một lỗi phổ biến là thêm nhiều provider/adapter cùng lúc, dẫn tới cảnh báo hoặc ghi trùng. Trước khi chỉnh logging trong container, xác định backend thực tế do framework (ví dụ starter) đã chọn.

## 14. Timestamp của ứng dụng và timestamp của runtime

Một dòng JSON ứng dụng có thể có `"timestamp"` do logger/encoder thêm. Docker `json-file` hoặc CRI còn ghi timestamp ở lớp ngoài. Khi collector parse, bạn có thể có **hai mốc thời gian**:

1. **Event timestamp**: lúc ứng dụng tạo sự kiện.
2. **Observed/ingest timestamp**: lúc runtime/agent/backend nhận hoặc ghi sự kiện.

Chúng không nhất thiết trùng nhau do buffering, scheduling, mạng, retry và đồng hồ host khác nhau.

Khi điều tra một luồng xử lý phân tán:

- Dùng timestamp có múi giờ rõ ràng, ưu tiên UTC ISO 8601.
- Biết dashboard sắp xếp bằng trường nào; nếu chuyển từ ingestion time sang event time, có thể thấy sự kiện “đến muộn”.
- Không suy ra thứ tự tuyệt đối giữa hai container chỉ từ timestamp nếu đồng hồ không đồng bộ hoàn toàn.
- Cần `trace_id`, `span_id`, `correlation_id` để liên kết request thay vì chỉ dựa vào thời gian.
- Kiểm tra xem timestamp của wrapper runtime có bị ghi đè timestamp của ứng dụng không; nên bảo toàn ý nghĩa của từng trường.

Không dùng thời gian hiện tại trong hằng output của ví dụ học tập nếu mục tiêu là **stdout xác định**, vì kết quả sẽ thay đổi theo mỗi lần chạy. Ví dụ Java phần 4 cố ý bỏ timestamp động.

## 15. Metadata của Kubernetes: pod, node, namespace, container

Để truy vấn log của nhiều replica, chỉ có message `"request failed"` là không đủ. Collector thường bổ sung **resource metadata** như:

```text
service.name       = orders
k8s.namespace.name = shop
k8s.pod.name       = orders-5bf...
k8s.container.name = app
k8s.node.name      = worker-02
deployment.environment = staging
```

Đây là **minh họa tên trường trong một hệ thống dùng semantic conventions**, không phải trường mà Kubernetes tự in vào từng message stdout.

Bổ sung metadata theo nơi phù hợp:

- Ứng dụng biết **event, outcome, order_id, correlation_id**.
- Kubernetes/agent biết **namespace, pod, container, node**, và có thể thêm labels từ metadata API.
- Nền tảng triển khai biết **environment, version, cluster, region**.
- Backend quyết định cách index các trường, giới hạn cardinality và quyền truy vấn.

Không nhất thiết copy tất cả biến môi trường và labels của Pod vào log. Một số giá trị có thể chứa dữ liệu bí mật hoặc tạo số lượng nhãn không kiểm soát. Cần chọn metadata có ích, có chính sách riêng với secret và ID có độ biến thiên cao.

## 16. Multiline stack trace và CRI partial log

Một exception Java truyền thống có thể xuất ra nhiều dòng:

```text
ERROR event=order_save_failed
java.io.IOException: connection timeout
    at example.orders.Repository.save(Repository.java:42)
    at example.orders.OrderService.create(OrderService.java:18)
Caused by: java.net.SocketTimeoutException: Read timed out
    at example.net.Client.call(Client.java:25)
```

Đây là **log minh họa**. Nếu collector coi mỗi newline là một sự kiện riêng, một lỗi có thể biến thành nhiều bản ghi, làm dashboard đếm sai và mất liên kết stack trace.

Có hai lựa chọn:

**A. JSON one-event-per-line:** encoder mã hóa stack trace thành một field string; ký tự newline trong string JSON được escape, nên parser NDJSON vẫn xem đó là một event. Đây thường là cách ổn định cho pipeline cấu trúc.

**B. Multiline aggregation tại collector:** dùng quy tắc nhận diện dòng bắt đầu, stack frame, `Caused by` và giới hạn số dòng/thời gian. Quy tắc này cần kiểm thử với format thực tế của các thư viện/phiên bản.

Bên cạnh multiline của **ứng dụng**, CRI runtime còn có trạng thái **`P` (partial)** và **`F` (full)** khi chia bản ghi ở tầng container. Hai việc khác nhau và đôi khi phải xử lý cả hai:

- Ghép fragment CRI về nội dung bản ghi trước khi parse payload.
- Nếu payload ứng dụng vẫn có stack trace nhiều dòng, có thể cần multiline parser tiếp theo.

Đừng gộp mọi dòng theo một regex chung mà không giới hạn kích thước/thời gian: dữ liệu không chuẩn có thể làm collector giữ buffer quá lâu, tốn RAM hoặc trộn hai sự kiện độc lập.

## 17. Mất log, trùng log và điều tra sự cố

Log pipeline có thể gặp vấn đề ở nhiều vị trí:

| Hiện tượng | Vị trí cần xem | Hướng xử lý |
| --- | --- | --- |
| Ứng dụng chạy nhưng không có log mới | Level/Filter, backend, stdout/stderr | Xác minh logger/provider và cấu hình console |
| `docker logs` trống | Driver `none`, cấu hình runtime hoặc tiến trình chưa ghi | Kiểm tra driver/container và lệnh chạy |
| `kubectl logs` có nhưng dashboard không có | Agent/collector/backend | Xem filelog tail, parser, exporter, auth, network |
| Dashboard có log nhưng thiếu `order_id` | JSON payload chưa parse, schema sai | Parse tầng runtime rồi payload; kiểm tra tên trường |
| Mất log sau restart/node lỗi | Rotation/local retention, agent chưa thu | Tối ưu thu tập trung và độ bền buffer nếu cần |
| Log xuất hiện hai lần | Console + file cùng được thu; nhiều agent trên node; retry | Chỉ định nguồn chuẩn, theo dõi ID/dedup |
| Log quá chậm | Backpressure, queue, mạng hoặc backend chậm | Quan sát queue, retry, thời gian ingest |
| Stack trace bị chia thành nhiều event | Sai CRI partial handling hoặc multiline parser | Dùng container parser và multiline policy |
| Log tăng bùng nổ ở collector | Agent đang thu chính output debug của nó | Loại nguồn collector hoặc đổi exporter phù hợp |
| File log node chiếm đầy đĩa | Rotation/retention sai hoặc tốc độ log quá cao | Kubelet/Docker rotation, giảm log ồn |
| Có log nhưng thiếu pod/namespace | Metadata enrichment sai hoặc RBAC thiếu | Kiểm tra đường file, parser, quyền API |
| Dữ liệu bị lộ qua log | Ứng dụng ghi secret, collector phân quyền sai | Giảm dữ liệu, redaction, secret policy, RBAC |

### Quy trình kiểm tra theo từng lớp

1. **Tại ứng dụng:** kiểm tra đúng logger, đúng level, output stdout/stderr và một sự kiện có mã `event` rõ.
2. **Tại container runtime:** `docker logs` hoặc `kubectl logs` có thấy sự kiện không? Nếu không, xác định appender hoặc runtime driver đã sai ở đâu.
3. **Tại node/agent:** agent có đọc được log files không; offset/rotation/permission và parser có hoạt động không?
4. **Tại collector:** có nhận event, parse CRI + payload, thêm metadata và chuyển đi không?
5. **Tại backend:** có bị lỗi xác thực, quota, rate limit, pipeline transform hoặc retention không?
6. **Tại dashboard:** truy vấn có dùng đúng trường timestamp, namespace, service, level và environment không?

Đừng cứ tăng log level hoặc thêm `println` khi event đã có trong `kubectl logs` nhưng thiếu ở dashboard; lúc đó cần điều tra **phần sau runtime**, không phải viết thêm log vào ứng dụng.

## 18. Bảo mật và riêng tư của log container

Một container có thể thuộc namespace nội bộ nhưng log vẫn được gom vào hệ thống mà nhiều nhóm cùng truy cập. Vì vậy phải thiết kế bảo mật từ **nội dung phát ra** đến **đích lưu**.

Những nguyên tắc cốt lõi:

1. **Không ghi secret:** mật khẩu, token, session cookie, API key, OTP, private key, số thẻ đầy đủ và payload nhạy cảm.
2. **Giới hạn PII:** mã người dùng/đơn hàng có thể cần mã hóa, che bớt hoặc thay bằng ID an toàn tùy chính sách; không phải mọi ID đều vô hại.
3. **Dùng encoder an toàn:** thông điệp có thể chứa newline, dấu nháy hoặc ký tự điều khiển, gây log injection nếu không được escape.
4. **Không lấy mọi biến môi trường:** environment variables có thể chứa secret; metadata enrichment phải chọn trường được phép.
5. **Giới hạn quyền agent:** hostPath, service account, RBAC và network egress chỉ cấp mức cần thiết.
6. **Bảo vệ đường truyền:** TLS, xác thực exporter/collector và quản lý chứng chỉ; tránh gửi log không mã hóa qua mạng không tin cậy.
7. **Phân quyền backend:** truy vấn và xuất dữ liệu cần role-based access, audit hoạt động truy cập, retention theo chính sách.
8. **Giới hạn dung lượng:** log volume quá lớn vừa tốn chi phí vừa tăng bề mặt lưu trữ dữ liệu nhạy cảm.
9. **Kiểm tra nơi log bị nhân bản:** CI logs, Docker local files, node agent buffers, kho tạm của collector, backup và archive.
10. **Không coi log là hệ thống kiểm toán duy nhất:** audit cần tính toàn vẹn, khả năng xác nhận và thiết kế nghiệp vụ riêng.

Logging JSON giúp giảm sai sót parse, nhưng **JSON hợp lệ không tự bảo mật dữ liệu**. TLS bảo vệ đường truyền, nhưng collector vẫn giải mã và xử lý nội dung; không nên gửi secret chỉ vì đã bật HTTPS.

## 19. Kiểm soát khối lượng, hiệu năng và chi phí

Dịch vụ có tải cao có thể phát hàng trăm nghìn sự kiện mỗi phút. Không chỉ ứng dụng mà runtime, agent, collector và backend đều chịu chi phí.

Một chiến lược cần xem đồng thời:

- **Mức log:** `INFO` cho sự kiện có giá trị vận hành; `DEBUG`/`TRACE` dùng khi điều tra với phạm vi và thời gian giới hạn.
- **Số lượng sự kiện:** tránh in cùng một exception ở controller, service và repository như ba sự cố riêng.
- **Kích thước:** không ghi toàn bộ request/response hoặc object có `toString()` quá lớn.
- **Sampling:** có thể giảm log ít quan trọng nhưng không áp dụng tùy tiện cho những sự kiện bắt buộc theo dõi.
- **Buffer/queue:** giới hạn và giám sát; khi đầy phải biết chính sách block, drop hay retry.
- **Rotation:** ngăn đầy đĩa node, nhưng có thể cắt mất lịch sử nếu agent đọc chậm.
- **Backpressure:** stdout/pipe hoặc exporter nghẽn có thể ảnh hưởng tiến trình phát log.
- **Cardinality:** không biến `request_id`, `order_id` thành label được index với chi phí không giới hạn ở mọi hệ thống.
- **Retention:** không cần mọi log ở mức `TRACE` tồn tại nhiều năm; chính sách tùy nghiệp vụ.
- **Độ bền dữ liệu:** nếu sự kiện nhất định phải lưu, xây nguồn bền vững như database/audit store/transactional outbox ngoài logging quan sát.

Các metric vận hành có ích là input events/bytes, processed events, dropped records, parse errors, exporter retries, queue size, backend ingest lag và node disk usage. Không chỉ dựa vào số dòng nhìn thấy trong `kubectl logs` để khẳng định pipeline toàn vẹn.

## 20. Câu hỏi tự kiểm tra

1. **Log container bắt đầu từ đâu?** Thường từ logger của ứng dụng đi qua Console Appender ra stdout/stderr.
2. **`docker logs` có phải kho log tập trung không?** Không. Nó đọc dữ liệu runtime/driver còn cung cấp.
3. **Docker Engine thường dùng driver mặc định nào?** `json-file` nếu không đổi cấu hình; phải kiểm tra daemon thực tế.
4. **Driver `json-file` tự parse JSON trong `log` thành `event` và `order_id` chưa?** Không. Wrapper JSON có trường `log` chứa payload, collector có thể phải parse thêm.
5. **Vì sao nên có rotation?** Tránh file log cục bộ chiếm hết đĩa; không đồng nghĩa lưu log vĩnh viễn.
6. **Docker non-blocking có bảo đảm không rơi log không?** Không. Buffer đầy có thể bỏ bản ghi.
7. **Trong Kubernetes, kubelet thường hướng runtime ghi log ở đâu trên node Linux?** Khu vực `/var/log/pods`.
8. **CRI log có những thành phần gì?** Timestamp, stream, tag partial/full và nội dung log.
9. **`F` và `P` ở CRI biểu thị gì?** Full record và partial fragment.
10. **`kubectl logs` có trả toàn bộ các file rotation cũ không?** Không; thông thường chỉ file hiện hành mới nhất.
11. **`kubectl logs --previous` có xem được mọi lần restart lịch sử không?** Không. Chỉ lần trước còn được kubelet giữ, nếu có.
12. **Vì sao DaemonSet thường được dùng cho node-level log agent?** Để có agent đọc file log trên từng node.
13. **Khi nào dùng sidecar?** Khi app không thể xuất stdout trực tiếp hoặc cần pipeline log riêng theo Pod; phải cân nhắc overhead và trùng dữ liệu.
14. **Một JSON event trên stdout có tự trở thành JSON có cấu trúc trong backend không?** Không; collector phải parse payload và bảo toàn schema.
15. **Tại sao không nên ghi Java stack trace nhiều dòng mà không có multiline parser?** Một exception có thể bị tách thành nhiều event giả.
16. **Hai timestamp trong log có ý nghĩa gì?** Một có thể là thời điểm ứng dụng phát, một là lúc runtime/collector nhận.
17. **Tại sao một collector có thể tự tạo vòng lặp log?** Nó thu stdout của chính nó rồi lại export debug ra stdout, tạo dữ liệu thu lặp.
18. **Có nên dựa vào log stdout làm bằng chứng giao dịch đã commit?** Không. Logging là quan sát, không thay thế nguồn trạng thái bền vững.
19. **Nếu `kubectl logs` có sự kiện nhưng dashboard không có, kiểm tra đâu?** Agent, parser, exporter, backend và truy vấn trước khi sửa code Java.
20. **Một Pod bị xóa thì log có chắc còn xem được không?** Không. Cần hệ thống cluster-level đã thu và lưu độc lập với Pod/node.

## 21. Tài liệu tham khảo

- Kubernetes, Logging Architecture: https://kubernetes.io/docs/concepts/cluster-administration/logging/
- Kubernetes, Observability: https://kubernetes.io/docs/concepts/cluster-administration/observability/
- Docker Engine, Configure logging drivers: https://docs.docker.com/engine/logging/configure/
- Docker Engine, JSON File logging driver: https://docs.docker.com/engine/logging/drivers/json-file/
- Docker Engine, Local file logging driver: https://docs.docker.com/engine/logging/drivers/local/
- OpenTelemetry, Collector Helm chart and logs collection preset: https://opentelemetry.io/docs/platforms/kubernetes/helm/collector/
- OpenTelemetry, Container log parser: https://opentelemetry.io/blog/2024/otel-collector-container-log-parser/

Các tài liệu này có thể thay đổi theo phiên bản Docker, Kubernetes, runtime và collector. Khi triển khai hệ thống thật, cần đối chiếu cấu hình tương thích với môi trường đang chạy thay vì coi giá trị minh họa là cấu hình chuẩn của mọi cluster.

**Ghi nhớ:** **ứng dụng Java phát log → container runtime thu stdout/stderr → kubelet/driver giữ log ngắn hạn → agent/collector parse và chuyển tiếp → backend lưu và tìm kiếm**. Hãy chọn một định dạng có cấu trúc, bảo toàn ranh giới sự kiện và metadata, hiểu rotation/buffer/multiline, giám sát mất/trùng log và tách biệt **quan sát hệ thống** khỏi **dữ liệu nghiệp vụ bắt buộc lưu bền**.
