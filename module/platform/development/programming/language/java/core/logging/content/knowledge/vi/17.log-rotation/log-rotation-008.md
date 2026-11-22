# Rotation trong container: quản lý log Java trên Docker và Kubernetes

## 1. Rotation trong container là gì?

**Log rotation** là quá trình giới hạn, đổi hoặc thay thế các tệp/đoạn log đang tăng kích thước, thường đi kèm chính sách giữ và xóa dữ liệu cũ. Trong ứng dụng Java chạy dưới dạng **container**, một câu hỏi quan trọng hơn "chọn thư viện rolling file nào?" là: **ai sở hữu đầu ra log và ai thực sự thực hiện rotation?**

Có hai kiến trúc chính:

- **Ứng dụng ghi stdout/stderr:** Logback, Log4j 2 hoặc JUL chuyển sự kiện tới console. Docker/container runtime và, nếu có, kubelet quản lý tệp log container trên node. Rotation thường nằm **ngoài JVM**.
- **Ứng dụng ghi file:** Logback `RollingFileAppender` hoặc Log4j 2 `RollingFile` quản lý file bên trong filesystem của container hoặc trên volume. Rotation có thể nằm **trong ứng dụng**; runtime chỉ tự quản lý stdout/stderr, không tự xoay mọi tệp nghiệp vụ do Java tạo.

Một container vẫn có thể vừa ghi console vừa ghi file, nhưng nếu hai tuyến này thu cùng một sự kiện thì phải phân biệt **fan-out có chủ đích** với nhân đôi vô tình.

Ví dụ:

```text
Ứng dụng Java
   |
   +-- ConsoleAppender --> stdout/stderr
   |                         |
   |                         v
   |                   Container runtime
   |                         |
   |                         v
   |                   Node log segments
   |                         |
   |                Runtime/kubelet rotation
   |                         |
   |                         v
   |                   Collector -> kho log
   |
   +-- RollingFileAppender --> /app/logs/app.log
                                 |
                                 v
                          Rotation trong JVM
                                 |
                                 v
                          Filesystem/volume
                                 |
                                 v
                          Collector đọc file (nếu có)
```

**Điểm mấu chốt:** giới hạn dung lượng log của Docker không tự giới hạn file `/app/logs/app.log` do `RollingFileAppender` ghi. Ngược lại, bật rolling policy cho Logback không tự cấu hình dung lượng tệp log stdout do Docker hoặc kubelet quản lý.

## 2. Vì sao container cần rotation?

Container được triển khai lại, scale theo replica và chạy trên các node có dung lượng đĩa hữu hạn. Log không được kiểm soát có thể:

1. Làm đầy filesystem/ephemeral storage của node hoặc volume.
2. Gây áp lực I/O, làm chậm runtime và tiến trình khác.
3. Khiến pod bị ảnh hưởng bởi cảnh báo áp lực dung lượng, eviction hoặc lỗi ghi.
4. Tạo lượng dữ liệu lớn cho collector, mạng và kho tập trung.
5. Khi retry hoặc exception phát sinh liên tục, nhân chi phí lưu trữ và làm nhiễu việc điều tra.
6. Giữ bí mật hoặc dữ liệu cá nhân lâu hơn chính sách cho phép.
7. Làm quá trình xem log, tìm kiếm và giữ stack trace khó vận hành.

Rotation giới hạn phần **log cục bộ có thể giữ lại**; nó không phải giải pháp duy nhất. Nếu lượng log tăng gấp mười, cũng cần xem lại log level, sampling, bản ghi trùng, lượng stack trace, tốc độ collector và các metric vận hành.

### Ba khái niệm dễ nhầm

| Khái niệm | Trả lời câu hỏi gì? | Ví dụ |
| --- | --- | --- |
| **Rotation** | Khi nào chuyển khỏi đoạn/file đang ghi? | Khi file đạt khoảng 10 MiB. |
| **Retention** | Giữ bao nhiêu file/bao lâu trước khi xóa? | Giữ tối đa ba file cục bộ. |
| **Shipping/collection** | Log được gửi và lưu ở hệ thống khác như thế nào? | Agent đọc log node rồi gửi về kho tập trung. |

Có rotation **không đồng nghĩa** đã có bản sao bền vững ở hệ thống log tập trung. Có collector cũng **không đảm bảo** mọi bản ghi sẽ được gửi trước khi file cục bộ bị xoay và xóa.

## 3. Nguyên tắc mặc định: ưu tiên stdout/stderr cho ứng dụng container thông thường

Đối với nhiều Java service chạy trong Docker/Kubernetes, kiến trúc dễ quản lý là:

```text
SLF4J/Log4j 2 API
      |
      v
Logback/Log4j 2 ConsoleAppender
      |
      v
stdout/stderr
      |
      v
container runtime / kubelet
      |
      v
node log files + rotation
      |
      v
node-level collector
      |
      v
central log storage
```

Ưu điểm của việc **ghi ra console**:

- Không phải tự quản lý vị trí thư mục log trong image.
- Không phải cấu hình writable volume chỉ để giữ text log.
- Logging theo vòng đời container trở nên nhất quán.
- Runtime và nền tảng có cơ chế truy cập như `docker logs` hoặc `kubectl logs`.
- Node-level collector có thể đọc log của nhiều workload theo cùng cách.
- Trách nhiệm rotation, retention, alert và quyền truy cập dễ tập trung ở tầng vận hành.

Tuy nhiên, **stdout không có nghĩa là dữ liệu được giữ vĩnh viễn**. Một container bị xóa, node hỏng, log file bị rotation/xóa hoặc collector bị chậm đều có thể làm mất phần log chỉ tồn tại cục bộ. Với sự kiện audit hoặc dữ liệu kinh doanh cần bảo đảm, phải thiết kế cơ chế lưu/gửi có độ tin cậy thích hợp thay vì chỉ dựa vào console.

### Chọn stdout hay stderr?

Không có quy tắc Java bắt buộc `ERROR` ghi vào `stderr`. Logback `ConsoleAppender` có thể cấu hình `System.out` hoặc `System.err`; Log4j 2 có `SYSTEM_OUT` và `SYSTEM_ERR`. Nhiều ứng dụng ghi toàn bộ log có trường `level` ra stdout; một số tách stderr cho lỗi. Cần **chọn một hợp đồng rõ ràng rồi kiểm thử**, không giả định tên mức tự quyết định stream.

Khi dùng Kubernetes, cả stdout và stderr của container đều có thể được runtime ghi lại kèm thông tin stream. Nếu giao diện hiển thị trộn hai stream, thứ tự giữa các bản ghi không nhất thiết được bảo toàn tuyệt đối.

## 4. Docker lưu log console ở đâu và ai thực hiện rotation?

Khi ứng dụng ghi vào stdout/stderr, Docker Engine chuyển dữ liệu sang **logging driver** được cấu hình cho container. Các driver phổ biến bao gồm `json-file`, `local`, `journald` hoặc các đích bên ngoài tùy hệ thống. **Cơ chế rotation cụ thể phụ thuộc driver đang dùng**, không phải một chính sách chung áp dụng y hệt cho mọi driver.

Với driver **`json-file`**, Docker lưu các bản ghi theo định dạng nội bộ có thông tin thời gian và stream. Cấu hình `max-size` và `max-file` có thể giới hạn dung lượng và số file cục bộ.

Ví dụ:

```bash
docker run --name java-log-demo \
  --log-driver json-file \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  my-java-image
```

Đây là **lệnh minh họa**; image `my-java-image` phải tồn tại trước khi chạy. Các tham số quan trọng:

- `--log-driver json-file`: chọn driver cho container này.
- `--log-opt max-size=10m`: giới hạn kích thước khoảng 10 MB của mỗi tệp log theo cú pháp driver.
- `--log-opt max-file=3`: giới hạn số tệp được giữ theo cách driver xử lý rotation.
- `--name`: đặt tên để dễ `docker logs`, `docker inspect`.

**Không mặc định rằng mọi Docker Engine bật rotation sẵn.** Driver `json-file` có thể ghi tăng không giới hạn nếu chưa thiết lập max-size, tùy cấu hình daemon và môi trường. Ngoài ra, `max-file` chỉ có ý nghĩa rotation khi kết hợp với cấu hình kích thước tương ứng theo driver.

### Docker logging driver và collector là hai lớp riêng

`docker logs` chủ yếu là giao diện **đọc các bản ghi mà driver hỗ trợ cung cấp**, không phải nơi thiết lập retention. Collector có thể gửi log cục bộ sang hệ thống tập trung, nhưng việc collector thất bại không nhất thiết ngăn rotation xóa file cũ.

Việc Docker giữ tối đa vài file trên host không cam kết rằng toàn bộ lịch sử log của một container còn có thể xem sau một tuần. Muốn lưu lâu hơn, phải cấu hình kho tập trung và retention của kho đó.

### `local` driver và các driver khác

Docker cũng có driver `local` hướng tới việc quản lý log cục bộ hiệu quả hơn trong nhiều môi trường, với khả năng rotation theo các tùy chọn riêng. Nhưng không phải mọi driver có cùng tên option, cùng hành vi `docker logs` hoặc cùng cơ chế đọc log.

**Cách xác minh:** kiểm tra driver và các option thực tế của container; sau đó tra đúng tài liệu của driver và phiên bản Docker đang dùng. Đừng áp chính sách của `json-file` cho một driver gửi log trực tiếp đến mạng mà chưa kiểm chứng.

## 5. Docker Compose: cấu hình rotation cho một Java service

Trong `compose.yaml`, có thể đặt driver và option tại **service**:

```yaml
services:
  app:
    build: .
    logging:
      driver: json-file
      options:
        max-size: "1m"
        max-file: "3"
```

**Chú ý:** các giá trị như `"1m"` và `"3"` là **chuỗi**, phù hợp kiểu option của logging driver. Thông số này giới hạn log stdout/stderr **do Docker quản lý** cho container của service, không tự can thiệp file khác bên trong filesystem.

Với Compose đang chạy, xác định ID container rồi kiểm tra:

```bash
docker compose ps -a -q app
docker compose logs --tail=20 app
```

Nếu muốn xem log configuration thực tế, sau khi biết container ID:

```bash
docker inspect --format '{{json .HostConfig.LogConfig}}' <container-id>
```

Trong lệnh trên, `<container-id>` là **giá trị thật** cần thay bằng ID từ `docker compose ps -a -q app`; đây là **lệnh minh họa thao tác kiểm tra**, không phải ký tự có thể chạy nguyên văn.

Kết quả inspect cần cho biết driver là `json-file` cùng option dung lượng/số file mong muốn. **Có cấu hình đúng chưa có nghĩa rotation đã thực sự xảy ra**: để xác minh hành vi, phải phát đủ log vượt ngưỡng và quan sát phần dữ liệu cũ được giữ/xóa theo chính sách.

### Cấu hình mặc định toàn Docker daemon

Khi có quyền quản trị Docker Engine, một chính sách mặc định có thể được đặt trong cấu hình daemon, ví dụ:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

Đây là **nội dung cấu hình daemon minh họa**, không phải JSON do ứng dụng Java đọc. Vị trí file và cách nạp lại/restart daemon phụ thuộc hệ điều hành và cách cài đặt Docker. Việc đổi mặc định **không tự động áp dụng hồi tố cho tất cả container đã tạo**; thông thường cần tạo lại container với cấu hình mong muốn.

Đừng tùy tiện restart Docker daemon trên host production vì có thể ảnh hưởng workload. Áp dụng cấu hình qua quy trình hạ tầng, có kiểm thử và lịch bảo trì khi cần.

## 6. Ví dụ Java 17 chạy được: tạo log console có thể kiểm chứng

Ví dụ dùng **JDK 17 thuần**, không cần thư viện logging ngoài JDK, để tách rõ cơ chế **phát bytes ra stdout/stderr** với cơ chế **rotation do Docker quản lý**.

Trong ứng dụng production, nên dùng logging facade/backend có structured fields và mức log thay vì rải `System.out.println` ở nhiều service. Bài này cố ý dùng standard streams để cách định tuyến **không phụ thuộc** vào một backend cụ thể.

### 6.1. Tệp `ContainerLogDemo.java`

```java
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

public final class ContainerLogDemo {
    private ContainerLogDemo() {
    }

    public static void main(String[] args) {
        int count = args.length == 0 ? 6 : Integer.parseInt(args[0]);

        if (count < 1) {
            throw new IllegalArgumentException("count must be positive");
        }

        PrintStream out =
                new PrintStream(System.out, true, StandardCharsets.UTF_8);
        PrintStream err =
                new PrintStream(System.err, true, StandardCharsets.UTF_8);

        for (int i = 1; i <= count; i++) {
            out.println("INFO|event=order.created|seq=" + i
                    + "|order=O-" + i);

            if (i % 3 == 0) {
                err.println("ERROR|event=gateway.failed|seq=" + i
                        + "|code=UPSTREAM_TIMEOUT");
            }
        }
        out.flush();
        err.flush();
    }
}
```

Các thuộc tính:

1. Mặc định tạo **6 sự kiện INFO** và **2 sự kiện ERROR**, với giá trị `seq` xác định.
2. INFO đi `stdout`; ERROR đi `stderr` do chính mã Java lựa chọn.
3. `PrintStream(..., UTF_8)` mã hóa dữ liệu theo UTF-8; buffer có auto-flush.
4. Không cố định timestamp/thread để đầu ra dễ kiểm thử.
5. Nếu truyền một số dương làm đối số, chương trình tạo đúng số vòng lặp; dùng được trong môi trường kiểm thử tải log.
6. Ví dụ **không tự xoay file** và **không tự xóa log**. Nó chỉ ghi vào stream để runtime xử lý.

Biên dịch và chạy tại máy có JDK 17:

```bash
javac -encoding UTF-8 ContainerLogDemo.java
java ContainerLogDemo >stdout.log 2>stderr.log
```

Sau lệnh trên, **nội dung chính xác của `stdout.log`** với không có đối số:

```text
INFO|event=order.created|seq=1|order=O-1
INFO|event=order.created|seq=2|order=O-2
INFO|event=order.created|seq=3|order=O-3
INFO|event=order.created|seq=4|order=O-4
INFO|event=order.created|seq=5|order=O-5
INFO|event=order.created|seq=6|order=O-6
```

**Nội dung chính xác của `stderr.log`:**

```text
ERROR|event=gateway.failed|seq=3|code=UPSTREAM_TIMEOUT
ERROR|event=gateway.failed|seq=6|code=UPSTREAM_TIMEOUT
```

Các dòng được ghi riêng theo từng stream; khi cùng hiển thị lên một terminal, **không nên assert thứ tự trộn tuyệt đối** giữa stdout và stderr.

### 6.2. Tệp `Dockerfile`

Dùng multi-stage build để chỉ đưa class file và JRE vào image runtime:

```dockerfile
FROM eclipse-temurin:17-jdk AS build
WORKDIR /src
COPY ContainerLogDemo.java .
RUN javac -encoding UTF-8 ContainerLogDemo.java

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /src/ContainerLogDemo.class .
USER 10001
ENTRYPOINT ["java", "ContainerLogDemo"]
CMD ["6"]
```

Giải thích:

- Stage `build` có JDK 17 để biên dịch.
- Stage runtime chỉ có JRE cần để chạy.
- Java process ghi ra **stdout/stderr**, không ghi trực tiếp file `/var/log/app.log`.
- `USER 10001` dùng người dùng không phải root trong container; ví dụ không cần quyền ghi file nào.
- `CMD ["6"]` cung cấp đối số mặc định; có thể thay số vòng lặp khi chạy container.
- Image `eclipse-temurin` là ví dụ; cần có Docker và truy cập image registry để build.

Build image:

```bash
docker build -t java-rotation-lab:1 .
```

Chạy một container không tự xóa để có thể kiểm tra cấu hình và lịch sử gần nhất:

```bash
docker run --name java-rotation-lab \
  --log-driver json-file \
  --log-opt max-size=1m \
  --log-opt max-file=3 \
  java-rotation-lab:1 6
```

Xem log:

```bash
docker logs --tail 20 java-rotation-lab
```

`docker logs` hiển thị bản ghi được driver hỗ trợ; stdout và stderr có thể xuất cùng trên một giao diện. **Đừng coi thứ tự trộn của hai stream là expected stdout cố định**. Nếu muốn biết chính xác stream nào nhận dữ liệu, dùng bài kiểm tra hai stream độc lập ở `stdout.log` và `stderr.log` hoặc công cụ có metadata stream.

Kiểm tra cấu hình logging của container:

```bash
docker inspect --format '{{json .HostConfig.LogConfig}}' java-rotation-lab
```

Dự kiến phần cấu hình thể hiện loại `json-file` và option `max-size=1m`, `max-file=3` (cách trình bày JSON có thể khác thứ tự). Một lần chạy với 6 vòng lặp tạo **quá ít dữ liệu để kích hoạt rotation**, vì thế kết quả test này mới chứng minh **đường log và cấu hình**, chưa chứng minh file đã xoay.

Dọn container thử nghiệm sau khi đã kiểm tra:

```bash
docker rm java-rotation-lab
```

### 6.3. Tạo đủ log để thử rotation

Có thể tạo một container kiểm thử riêng với số vòng lặp lớn, nhưng cần làm trên môi trường được phép và biết trước dung lượng/tải:

```bash
docker run --name java-rotation-load \
  --log-driver json-file \
  --log-opt max-size=1m \
  --log-opt max-file=3 \
  java-rotation-lab:1 30000
```

Lệnh này sinh 30.000 INFO và 10.000 ERROR ở hai stream; tổng số byte sẽ vượt đáng kể 1 MB trên các cấu hình ghi log thông dụng. **Không in toàn bộ dữ liệu ra terminal khi kiểm tra**, chỉ xem phần gần nhất:

```bash
docker logs --tail 20 java-rotation-load
docker inspect --format '{{json .HostConfig.LogConfig}}' java-rotation-load
```

Kỳ vọng cần kiểm tra:

- Quá trình ghi không bị lỗi chỉ vì log lớn hơn một file.
- Giới hạn log driver đang có hiệu lực.
- Đĩa cục bộ được khống chế theo chính sách sau khi rotation chạy.
- Những sự kiện mới vẫn có thể xem theo khả năng đọc của driver.
- **Không đòi hỏi phải xem lại đủ 40.000 dòng cũ**: rotation và retention có thể đã loại các segment cũ.

Việc xác minh số lượng file và dung lượng thực tế trên host cần công cụ/đặc quyền của người quản trị và phải theo quy định của runtime. **Không tự sửa, xóa hoặc truncate các file log nội bộ của Docker trong thư mục dữ liệu engine**; thao tác trực tiếp ngoài driver có thể phá quản lý file và làm dữ liệu/đọc log không nhất quán.

Dọn container:

```bash
docker rm java-rotation-load
```

Lưu ý `docker rm` chỉ có thể xóa container đã dừng. Ví dụ Java kết thúc bình thường nên container trở về trạng thái exited.

### 6.4. Phân biệt ví dụ chạy được và quy trình hệ thống

Tệp Java chạy độc lập bằng JDK 17, có output được xác định theo từng stream. Ví dụ Docker cần Docker Engine, quyền chạy container và image từ registry. Kết quả `docker inspect` và vị trí các segment phụ thuộc môi trường; vì thế bài học **không bịa số lượng byte, inode hoặc đường dẫn tuyệt đối của tệp log trên node**.

## 7. Docker Compose áp dụng cho chương trình Java vừa tạo

Sau khi có `Dockerfile` và `ContainerLogDemo.java`, đặt `compose.yaml` trong cùng thư mục:

```yaml
services:
  app:
    build: .
    logging:
      driver: json-file
      options:
        max-size: "1m"
        max-file: "3"
    command: ["6"]
```

Ở image mẫu, `ENTRYPOINT ["java", "ContainerLogDemo"]` nhận `CMD ["6"]`; `command: ["6"]` của Compose có cùng vai trò truyền đối số số vòng lặp.

Chạy rồi xem log:

```bash
docker compose up -d --build
docker compose logs --tail=20 app
docker compose ps -a
docker compose down
```

Với số vòng lặp mặc định, không có rotation thực sự vì log quá ít. Muốn kiểm thử kích thước, có thể chủ động đổi `command` thành số lớn trong **môi trường thử nghiệm**, nhưng cần tránh làm đầy quota hoặc làm nghẽn collector. Sau khi sửa logging options trong Compose, phải đảm bảo container được **tạo lại** theo cấu hình mới; thay YAML mà chỉ xem một container cũ không đủ bằng chứng.

**Không áp cấu hình `compose.yaml` cho Kubernetes.** Kubernetes không sử dụng trực tiếp `logging.driver`/`logging.options` của Docker Compose cho pod. Đây là hai tầng triển khai khác nhau.

## 8. Kubernetes: rotation chủ yếu thuộc kubelet và container runtime

Trên Kubernetes, ứng dụng Java thường ghi stdout/stderr. Container runtime ghi dữ liệu theo định dạng log của runtime/CRI trên node; kubelet đảm nhiệm việc điều phối **container log rotation** theo cấu hình node và khả năng runtime tương ứng.

Đường đi khái quát:

```text
Java -> stdout/stderr -> container runtime
                               |
                               v
                     node container log files
                               |
                               v
                         kubelet rotation
                               |
                      +--------+---------+
                      |                  |
                      v                  v
                 kubectl logs      node log agent
                                         |
                                         v
                                   central storage
```

Một số thuộc tính cấu hình kubelet liên quan đến rotation:

```yaml
containerLogMaxSize: "10Mi"
containerLogMaxFiles: 5
```

Đây là **đoạn trong cấu hình kubelet**, **không phải Pod manifest** hoàn chỉnh và không phải thuộc tính có thể dán vào `containers:` của Kubernetes Deployment. Ý nghĩa:

- `containerLogMaxSize`: kích thước tối đa theo cấu hình cho một container log file trước khi cần rotation.
- `containerLogMaxFiles`: số file log tối đa theo chính sách kubelet giữ cho mỗi container.
- Hành vi thực tế còn phụ thuộc phiên bản Kubernetes, runtime và cơ chế xử lý của node.

Trong các cụm được quản lý (managed Kubernetes), việc đổi cấu hình kubelet có thể yêu cầu chỉnh node pool/launch template/provider settings và triển khai node phù hợp. **Không tự sửa trực tiếp cấu hình kubelet trên node production** khi chưa có quy trình quản lý hạ tầng; thay đổi có thể bị quản lý cụm ghi đè.

### Rotation không phải biến môi trường của Pod

Các dòng sau **không cấu hình kubelet rotation**:

```yaml
env:
  - name: LOG_ROTATE_MAX_SIZE
    value: "10Mi"
```

Đoạn trên chỉ định một biến môi trường tên do ứng dụng lựa chọn. Nó không tự tác động kubelet nếu không có một thành phần thật sự đọc biến đó và thực hiện hành vi tương ứng. Nếu Java application dùng RollingFileAppender và tự đọc biến, đó lại là **rotation trong ứng dụng**, khác node-level rotation của stdout/stderr.

### `kubectl logs` đọc được phạm vi nào?

Một số lệnh thường dùng:

```bash
kubectl logs my-pod -c app --tail=100
kubectl logs my-pod -c app --since=10m
kubectl logs my-pod -c app --previous
```

Các tên pod/container ở trên là **ví dụ minh họa**, cần thay bằng tên thật trong cụm.

- `--tail=100`: lấy tối đa số dòng cuối theo cơ chế lệnh.
- `--since=10m`: giới hạn khoảng thời gian.
- `--previous`: tìm log từ **lần chạy container trước trong cùng pod**, khi runtime/kubelet còn lưu được.
- `--previous` **không có nghĩa** là đọc "file rotated trước đó".

Trong Kubernetes thông dụng, `kubectl logs` có giới hạn dữ liệu được kubelet cung cấp từ log container hiện có; các segment đã xoay không nên được coi là truy cập đầy đủ qua lệnh này. Một số tài liệu Kubernetes mô tả rằng `kubectl logs` chỉ cung cấp nội dung file log mới nhất sau rotation, không toàn bộ lịch sử. Muốn tra log cũ hơn hoặc qua nhiều lần restart/node, cần **collector và kho tập trung có retention phù hợp**.

### Container restart, Pod replacement và node loss

Ba sự kiện vận hành khác nhau:

1. **Container restart trong cùng pod:** runtime có thể giữ một phần log lần chạy trước; `kubectl logs --previous` có thể hữu ích.
2. **Pod bị xóa/thay bằng pod mới:** khả năng truy cập log cục bộ của pod cũ giảm hoặc mất theo garbage collection của node/runtime.
3. **Node hỏng hoặc bị thay:** dữ liệu chỉ nằm trên node có thể mất hoàn toàn.

Do đó, rotation và `kubectl logs` phục vụ **debug gần hiện tại**, không thay thế chiến lược lưu trữ lâu dài.

## 9. Kubernetes: một Deployment log stdout/stderr đúng cách

Ví dụ ứng dụng đã được đóng gói trong image `registry.example.com/demo/java-rotation:1`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: java-rotation-demo
spec:
  replicas: 1
  selector:
    matchLabels:
      app: java-rotation-demo
  template:
    metadata:
      labels:
        app: java-rotation-demo
    spec:
      containers:
        - name: app
          image: registry.example.com/demo/java-rotation:1
          args: ["6"]
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              memory: "256Mi"
```

Đây là **manifest minh họa cấu trúc**, không thể triển khai nguyên vẹn nếu image chưa được build/push và cluster không truy cập được registry. Ứng dụng vẫn chỉ ghi stdout/stderr; **không cần volume** cho log text trong cách tiếp cận này. Rotation được cấu hình trên node/kubelet, không ở Deployment.

Sau triển khai với image thật, có thể xem:

```bash
kubectl get pods -l app=java-rotation-demo
kubectl logs deployment/java-rotation-demo -c app --tail=20
```

Vì chương trình Java mẫu kết thúc nhanh, nếu chạy như **Deployment** (dự kiến workload luôn sống) thì kubelet sẽ **restart container**, có thể thành vòng khởi chạy lặp lại. Đây **không phải cấu hình production phù hợp cho một chương trình batch ngắn**. Với tác vụ chỉ chạy rồi kết thúc, Kubernetes `Job` thích hợp hơn; ví dụ Deployment ở đây chỉ minh họa vị trí image/args và sự tách biệt giữa Pod spec và cấu hình rotation node.

Đối với service Java chạy lâu (web API, message consumer), tiến trình JVM phải tiếp tục phục vụ hoặc đợi công việc; khi đó Deployment mới phù hợp.

### Kiểm tra tình huống log tăng nhanh trên cụm

Nếu một pod phát log quá nhiều:

- Xác định nguyên nhân: log level DEBUG bị mở, exception lặp, retry loop, message payload lớn hay bug.
- Kiểm tra collector có thu kịp không.
- Kiểm tra ephemeral storage và dấu hiệu disk pressure/eviction trên node.
- Kiểm tra giới hạn log rotation của kubelet/node pool.
- Đảm bảo hệ thống log trung tâm còn dữ liệu cần điều tra trước khi node xóa bản cũ.
- Cân nhắc sampling/giới hạn event theo ý nghĩa, không chỉ tăng kích thước mỗi file.

**Cần sửa nguồn tạo log ồn**, không chỉ tăng max size. Rotation giúp giới hạn hậu quả trên đĩa cục bộ nhưng không chữa ứng dụng đang ghi hàng triệu stack trace giống nhau.

## 10. Logback trong Java container: ghi console để runtime quản lý rotation

Với ứng dụng dùng `SLF4J 2.x + Logback`, một cấu hình `src/main/resources/logback.xml` phù hợp kiến trúc stdout có thể là:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS,UTC} %-5level [%thread] %logger - %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT" />
    </root>
</configuration>
```

Đây là tệp cấu hình **độc lập về XML**, nhưng nó chỉ có tác dụng khi runtime thật sự sử dụng Logback Classic làm backend và có dependency phù hợp. Ví dụ Java 17 ở phần 6 **không dùng Logback**, nên sẽ không bị `logback.xml` này chi phối.

Lời gọi trong ứng dụng Logback có thể là:

```java
log.info("event=order.created order_id={}", orderId);
```

Đây là **đoạn minh họa** với logger và `orderId` đã có trong mã nghiệp vụ. Sau khi event được encoder xuất ra stdout, container runtime mới quyết định ghi và xoay phần output.

**Không cấu hình hai lớp rotation cho cùng một byte stream một cách mù quáng.** Nếu Java chỉ dùng ConsoleAppender, Docker/kubelet quản lý log file của container. Nếu Java dùng thêm RollingFileAppender ra `/app/logs`, đó là **một tuyến file khác** cần retention và collector riêng.

### Log4j 2 tương đương về mục tiêu

Với Log4j 2 Core, một `Console` appender:

```xml
<Configuration>
    <Appenders>
        <Console name="STDOUT" target="SYSTEM_OUT">
            <PatternLayout
                pattern="%d{ISO8601} %-5level [%t] %c - %m%n"
                charset="UTF-8" />
        </Console>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="STDOUT" />
        </Root>
    </Loggers>
</Configuration>
```

Đây là cấu hình Log4j 2, không dùng được nguyên văn làm `logback.xml`. Cả hai ví dụ đều chủ đích **không tự xoay file bên trong JVM**. Cấu hình rotation thuộc tầng runtime/kubelet.

## 11. Khi ứng dụng thật sự cần ghi file trong container

Một số hệ thống cần file riêng vì:

- Ứng dụng legacy hoặc agent chỉ đọc file.
- Tích hợp với phần mềm có hợp đồng file cụ thể.
- Cần ghi sự kiện khác loại theo quyền hoặc định dạng riêng.
- Khối lượng/log binary đặc biệt cần một pipeline do nhóm vận hành thiết kế.

Khi đó có thể dùng **Logback RollingFileAppender** hoặc **Log4j 2 RollingFile**. Nhưng trước khi chọn, hãy trả lời:

1. File nằm ở **writable layer** của container hay trên volume?
2. File cần tồn tại qua container restart, pod replacement hay node replacement không?
3. Ai xóa file cũ: ứng dụng, logrotate bên ngoài hay agent?
4. Collector đọc file nào và có theo kịp khi file đổi tên/đóng/mở không?
5. Có nhiều replica cùng ghi **một đường dẫn** không?
6. Disk quota, file permission, UID/GID và backup/retention là gì?
7. Khi thư mục log đầy, ứng dụng và node phản ứng thế nào?

### Ví dụ Logback tự rolling file

Đây là **đoạn cấu hình cho Logback**, dùng khi có `logback-classic` tương thích:

```xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>/app/logs/application.log</file>

        <rollingPolicy
            class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>/app/logs/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>10MB</maxFileSize>
            <maxHistory>7</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
        </rollingPolicy>

        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE" />
    </root>
</configuration>
```

Giải thích:

- `RollingFileAppender` ghi file `/app/logs/application.log`.
- `SizeAndTimeBasedRollingPolicy` dùng mẫu tên theo ngày và chỉ số `%i`, đồng thời xử lý kích thước theo cấu hình.
- `maxFileSize` giới hạn khoảng kích thước file trước rollover theo policy.
- `maxHistory=7` cùng mẫu thời gian theo ngày liên quan số kỳ lịch sử được giữ, không phải cam kết cứng "đúng bảy file".
- `totalSizeCap` bổ sung giới hạn tổng dung lượng lịch sử theo cơ chế cleanup.
- Việc xóa/giữ có thể diễn ra trong các thời điểm rollover/cleanup, không có nghĩa file giảm ngay khi người quản trị thay XML.

**Điều kiện quan trọng:** `/app/logs` phải tồn tại và có quyền ghi cho UID của tiến trình Java. Với image chạy dưới non-root, một mount/volume có quyền không phù hợp sẽ khiến file không được mở.

### Vì sao Docker rotation không xử lý file Logback?

Docker logging driver mặc định quản lý dữ liệu được gửi từ stdout/stderr của container. File do Java ghi trực tiếp vào `/app/logs/application.log` chỉ là **file thường** ở filesystem; Docker driver `json-file` không tự phát hiện và xoay file này.

Nếu đồng thời có:
- Docker rotation cho stdout.
- Logback RollingFile cho `/app/logs`.

thì đó là **hai log store** có vòng đời khác nhau. Cần hai quy tắc retention/thu thập và có thể gây log trùng khi cả hai tuyến phát cùng event.

## 12. Volume, filesystem tạm và vòng đời Pod

Một file log nằm trong writable layer của container thường chỉ có ý nghĩa với vòng đời container, và không nên coi là kho dữ liệu bền vững. Một số lựa chọn:

| Nơi ghi | Đặc điểm | Rủi ro |
| --- | --- | --- |
| stdout/stderr | Runtime/kubelet thu thập theo cơ chế container | Có rotation và GC; không lưu lâu nếu thiếu collector. |
| Writable layer trong container | Ghi file đơn giản nhưng gắn với vòng đời container | Mất khi container bị thay/xóa; tăng áp lực storage. |
| Kubernetes `emptyDir` | Volume dùng chung trong vòng đời Pod | Có thể tồn tại qua restart container trong cùng pod, nhưng mất khi Pod bị xóa khỏi node. |
| PersistentVolume | Có thể tồn tại ngoài vòng đời Pod theo policy/storage class | Quyền ghi, chi phí, concurrency và lifecycle phức tạp hơn. |
| HostPath | Truy cập filesystem node cụ thể | Ràng buộc node, vấn đề bảo mật/permissions; khó vận hành multi-node. |

**Một volume không thay thế cho log rotation.** Nếu gắn PVC rồi ghi không giới hạn, volume vẫn có thể đầy. Với nhiều Java replica cùng ghi cùng một file trên shared volume, rename/rollover và file lock có thể xung đột, làm mất hoặc trộn log. Thường nên mỗi instance có đường dẫn riêng hoặc quay về kiến trúc stdout + collector.

### Bẫy của chạy non-root

Nhiều image Java production dùng `USER` không phải root. Nếu volume được mount với owner/permission không phù hợp, RollingFileAppender không thể tạo file. Không nên "chữa nhanh" bằng `chmod 777` mọi nơi; cần quyền phù hợp với UID/GID, nhóm vận hành, security context, hoặc cơ chế provisioning được kiểm soát.

### File đang mở và thao tác rename

Trên hệ điều hành kiểu Unix, tiến trình giữ file descriptor có thể tiếp tục ghi vào **inode cũ** dù file đã được đổi tên bên ngoài. Vì thế, dùng một công cụ rotation ngoài Java để rename file mà không yêu cầu logger mở lại file có thể khiến dữ liệu đi sai chỗ. Cách `copytruncate` cũng có thể gây mất hoặc trùng log ở khoảng thời gian copy/truncate khi ghi đồng thời.

**Không chạy Logback RollingFileAppender và một logrotate bên ngoài trên cùng file mà chưa thiết kế rõ quyền sở hữu rotation**. Chọn một cơ chế chủ đạo và thử tình huống đang ghi khi rollover.

## 13. Sidecar và collector: rotation liên quan thế nào?

Một cách thu thập log file là có agent/sidecar đọc file từ volume chung; cách khác là dùng agent cấp node đọc log stdout/stderr do runtime tạo.

```text
Phương án A (thường đơn giản):
Java stdout -> runtime log -> node agent -> central storage

Phương án B (ứng dụng cần file):
Java RollingFile -> shared volume -> sidecar/agent -> central storage
```

Trong phương án B, cần kiểm tra:

- Agent theo dõi file cũ và file mới khi rotation xảy ra.
- Agent nhận diện offset/inode/rotation, không đọc lại mọi file từ đầu hoặc bỏ phần cuối.
- File bị nén/xóa trước khi agent đọc hết có thể dẫn tới mất log.
- Có hạn chế về số file, kích thước file, backpressure và quyền đọc.
- Nếu Java restart, agent xử lý được file tiếp tục ghi hoặc file mới.
- Khi pod bị xóa, log chưa chuyển đi có thể bị mất cùng volume tạm.

Trong phương án A, runtime và kubelet xoay log node; node agent cần tương thích với cơ chế CRI/container log và thời điểm rotation của node. **Rotation nhanh hơn tốc độ thu thập** là một nguồn dữ liệu mất mát phổ biến ở cả hai phương án.

### Vì sao sidecar tail stdout trực tiếp có thể phức tạp?

Nếu ứng dụng vốn đã ghi stdout, không cần bắt nó ghi file rồi chạy sidecar `tail -f` để in lại stdout, trừ khi có yêu cầu riêng đã được chứng minh. Cách này thêm một lớp buffer/stream, tăng tài nguyên và có nguy cơ log trùng hoặc thất lạc khi tiến trình tail chậm, restart hoặc file xoay.

## 14. JSON logging, multiline và kích thước một sự kiện

Khi Logback/Log4j 2 ghi text, một stack trace có thể gồm hàng chục dòng vật lý. Docker/Kubernetes runtime vẫn nhận byte từ stdout/stderr; bộ thu thập có thể lưu theo dòng hoặc chunk, đôi khi phải ghép các phần từ CRI/driver.

Với structured logging, ứng dụng có thể phát **một JSON object trên mỗi dòng**:

```json
{"level":"ERROR","event_code":"payment.failed","request_id":"req-7","message":"Gateway timeout"}
```

Đây chỉ là **ví dụ schema**, không phải output tự động của Java `System.out` hoặc Logback `PatternLayout`.

Một encoder JSON đáng tin cần escape dấu xuống dòng trong giá trị string, dấu nháy kép và ký tự điều khiển. Tự ghép text theo dạng `{"message":"%msg"}` dễ tạo JSON không hợp lệ nếu message chứa các ký tự đặc biệt.

### Rotation và log lớn một dòng

Nếu một JSON event đơn lẻ có kích thước rất lớn (ví dụ payload nhiều MB), có thể:

1. Vượt giới hạn kích thước bản ghi/line của collector hoặc dịch vụ lưu trữ.
2. Bị runtime chia thành nhiều đoạn/partial record theo cơ chế cụ thể.
3. Tăng nguy cơ mất dữ liệu khi collector không ghép đúng.
4. Làm tăng chi phí storage và truy vấn.
5. Khiến rotation diễn ra rất nhanh dù số sự kiện thấp.

Không nên log toàn bộ request/response hoặc object lớn để “dễ debug”. Hãy ghi event code, ID liên kết, kích thước, error code và dữ liệu được phép. Khi thật sự cần dữ liệu lớn, sử dụng kho lưu trữ riêng được kiểm soát.

### Một dòng log không phải một giao dịch

Một request có thể tạo nhiều event và stack trace. Vì vậy, không dùng số dòng trong file rotated làm **số giao dịch** hay **error rate**. Muốn đo số lỗi giao dịch, dùng metric/counter hoặc một sự kiện hoàn tất request có định nghĩa và cơ chế bảo toàn phù hợp.

## 15. Chính sách retention: max-size và max-files chưa đủ cho mọi mục tiêu

Một cấu hình như `max-size=10m` và `max-file=3` thường nhằm giới hạn **dữ liệu cục bộ** còn nằm dưới driver, không phải bảo đảm dữ liệu còn đủ ba ngày.

Tại sao?

- Ứng dụng ghi nhiều có thể xoay hết ba file chỉ sau vài phút.
- Ứng dụng ít ghi có thể giữ một file trong nhiều ngày.
- Dữ liệu sau rotation còn chịu lifecycle của container/node.
- Collector có thể mất kết nối khi log cũ bị xóa.
- Kho tập trung có retention và chính sách xóa khác.

Vì thế, hãy xác định các yêu cầu riêng:

| Yêu cầu | Cơ chế phù hợp |
| --- | --- |
| Không làm đầy node | Rotation/giới hạn file cục bộ, alert disk pressure |
| Có thể xem log vài phút gần nhất | Runtime/kubelet local logs |
| Tìm log nhiều ngày/tuần | Kho log tập trung và retention |
| Điều tra một request qua nhiều replica | Trace/request ID, collector, search |
| Không để mất event audit | Cơ chế gửi/lưu bền vững riêng, có đối soát |
| Xóa dữ liệu theo chính sách | Retention của kho, phân quyền và quy trình xóa |
| Chi phí log có thể dự đoán | Level/sampling/quota + theo dõi volume |

**Rotation không thay thế cho compliance retention.** Có thể cần giữ audit log lâu hơn, nhưng không nên tăng dung lượng đĩa node vô hạn để đáp ứng điều đó. Dữ liệu cần được lưu ở hệ thống được thiết kế cho mục tiêu lâu dài.

## 16. Cách kiểm thử rotation trong container một cách có trách nhiệm

Kiểm thử nên tách **độ đúng cấu hình**, **hành vi rotation**, **đường tới collector** và **lifecycle**.

### 16.1. Kiểm tra cấu hình

- Với Docker, xác định logging driver/`max-size`/`max-file` qua inspect sau khi container được tạo.
- Với Kubernetes, xác định kubelet/runtime node đang dùng và các cấu hình rotation thực tế theo công cụ quản trị được cấp quyền.
- Với Java RollingFile, xác định file path/rollingPolicy/retention và quyền ghi của JVM.
- Đừng chỉ thấy một dòng `max-size` trong file source rồi kết luận đã có hiệu lực ở runtime.

### 16.2. Kiểm tra hành vi với log thử nghiệm

Một quy trình an toàn trên **môi trường test**:

1. Đặt ngưỡng nhỏ nhưng hợp lệ, ví dụ 1 MB, và giới hạn số file.
2. Phát các sự kiện mẫu có `event_code` và số thứ tự tăng dần.
3. Cho tổng dung lượng vượt ngưỡng nhiều lần, không dùng secret hay thông tin thật.
4. Quan sát cấu hình/driver và các segment thông qua công cụ quản trị được hỗ trợ, không chỉnh tay file nội bộ của runtime.
5. Xác nhận những bản ghi mới vẫn đọc được.
6. Xác nhận local disk không tiếp tục tăng vô hạn vì cùng một container khi policy hoạt động.
7. Nếu có collector, so sánh sequence/offset đã nhận với sequence phát ra, xác định phần mất/trùng và độ trễ.
8. Xóa/dừng thử nghiệm và dọn tài nguyên theo quy trình.

**Không khẳng định “test pass nếu đọc được đủ tất cả các dòng cũ bằng `docker logs`”**; mục tiêu retention cục bộ là có thể xóa dòng cũ. Muốn kiểm tra tính toàn vẹn lịch sử thì phải kiểm tra cả kho tập trung, chính sách giao nhận và dữ liệu cũ đã bị rotation.

### 16.3. Kiểm tra khi restart hoặc deploy

Tạo các kịch bản:

- Container restart nhanh sau khi ghi log.
- Pod bị thay bằng Pod mới.
- Node có disk pressure.
- Collector dừng trong một khoảng rồi hoạt động lại.
- Nhiều replica ghi cùng event code nhưng trace ID khác nhau.
- Một exception có stack trace nhiều dòng.
- Pipeline cần đọc log cũ đúng lúc node đã rotation.

Chỉ nên mô phỏng các sự cố trên môi trường được phép. Không gây disk pressure thực trên production để thử xem kubelet có eviction hay không.

### 16.4. Những chỉ số nên theo dõi

- Dung lượng và tốc độ tăng log cục bộ trên node/volume.
- Số lần rotation và lỗi khi rotate nếu platform cung cấp metric.
- Dung lượng queue/buffer collector, số record drop/retry.
- Độ trễ ingest từ lúc event phát đến lúc xuất hiện tại kho trung tâm.
- Số lượng ERROR/WARN theo event code, tránh đếm lặp một failure.
- Số node/pod bị eviction hoặc có warning storage.
- Chi phí storage và lượng dữ liệu theo service/environment.

Không phải mọi runtime có cùng metric name; cần dùng telemetry cụ thể của hệ thống đang triển khai.

## 17. Lỗi phổ biến khi xử lý rotation trong container

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Node đầy đĩa dù ứng dụng chỉ dùng stdout | Log driver chưa có giới hạn, kubelet rotation chưa đúng hoặc log quá nhiều | Kiểm tra runtime, kubelet, local usage và tốc độ sinh log. |
| Đã đặt Docker `max-file` nhưng file vẫn tăng | Thiếu `max-size` hoặc container cũ chưa được tạo lại | Xác minh option hiệu lực trên container. |
| Logback RollingFile hoạt động nhưng Docker log vẫn lớn | Java còn ghi stdout; đây là tuyến khác | Kiểm tra cả appender và logging driver. |
| Docker rotation không làm file `/app/logs` nhỏ hơn | File do Java ghi trực tiếp, không thuộc stdout/stderr | Dùng RollingFile policy hoặc quy trình rotation file riêng. |
| `kubectl logs --previous` không thấy log rotated | `--previous` là container instance trước, không phải segment cũ | Dùng collector/kho tập trung để tìm lịch sử. |
| Container restart làm mất log cũ | Dữ liệu chỉ ở runtime node, bị xóa/GC hoặc collector chưa gửi | Điều tra lifecycle và retention của pipeline. |
| Collector thiếu đoạn dữ liệu | Rotation nhanh hơn đọc, backpressure, parser sai, node mất | So sánh sequence, offset, queue, độ trễ ingest. |
| Một stack trace thành nhiều sự kiện giả | Collector không ghép multiline/partial đúng | Dùng JSON escaping hoặc cấu hình multiline/CRI parser. |
| Hai replica ghi vào một file chung bị hỏng | Rolling cùng path trên shared volume | Tách file theo instance hoặc dùng stdout + collector. |
| File rename rồi vẫn thấy ghi vào file cũ | Logger giữ file descriptor cũ | Phối hợp rotation/reopen, không thao tác rename bên ngoài tùy tiện. |
| Copytruncate mất vài dòng | Ứng dụng đang ghi khi file bị copy/truncate | Tránh kết hợp hai cơ chế rotation không đồng bộ. |
| Không thể tạo `/app/logs` | Container chạy non-root, volume sai permissions | Kiểm tra UID/GID, mount và quyền ghi. |
| JSON log bị parse sai | Tự ghép JSON bằng pattern, dấu xuống dòng/quote | Dùng encoder JSON được hỗ trợ và test parser. |
| Đặt max-size rất nhỏ làm mất log điều tra | Retention cục bộ quá ngắn so với tốc độ ingest | Điều chỉnh lưu trữ/collector và giảm volume log tại nguồn. |
| Có đủ log ở Docker nhưng không có trong kho tập trung | Collector chưa đọc, filter/route lỗi hoặc index sai | Kiểm tra toàn pipeline thay vì chỉ rotation. |
| ERROR log bị gửi lặp | Nhiều appender/route, retry hoặc nhiều tầng Java cùng log | Phân biệt event ID và tuyến từng đích. |

## 18. Bài tập thực hành có đáp án

### Bài 1: Hai loại rotation

Một ứng dụng Logback có `RollingFileAppender` ghi `/app/logs/app.log`. Docker lại được cấu hình `--log-driver json-file --log-opt max-size=10m --log-opt max-file=3`. Hỏi cấu hình Docker có tự xoay `app.log` không?

**Đáp án:** Không. Docker driver xử lý stdout/stderr của container; `app.log` là file do JVM mở trực tiếp. Nếu có ConsoleAppender và RollingFileAppender cùng chạy, cần quản lý **hai tuyến log** riêng, không nhầm một với một.

### Bài 2: Cấu hình Kubernetes

Một nhóm đặt trong Pod manifest:

```yaml
env:
  - name: containerLogMaxSize
    value: "10Mi"
```

Hỏi kubelet có tự áp giới hạn đó không?

**Đáp án:** Không chỉ vì biến môi trường này có mặt. `containerLogMaxSize` là thuộc tính của cấu hình kubelet, không phải biến môi trường tiêu chuẩn của container. Nếu cần node-level rotation, cấu hình đúng tầng node/kubelet theo công cụ quản lý cụm.

### Bài 3: Log sau nhiều lần rotate

Docker giới hạn tối đa ba file cục bộ và service ghi rất nhiều dòng mỗi giây. Có thể dựa vào `docker logs` để tìm đủ log của tuần trước không?

**Đáp án:** Không. Retention cục bộ theo **dung lượng và số file** có thể chỉ còn vài phút; container/node còn có lifecycle riêng. Cần ship log sang kho trung tâm với retention phù hợp nếu muốn tìm dữ liệu lâu dài.

### Bài 4: `kubectl logs --previous`

Một Pod có log đã rotate ba lần nhưng container chưa restart. Có thể dùng `kubectl logs --previous` để đọc file rotated ngay trước đó không?

**Đáp án:** Không. Tùy chọn này liên quan **lần chạy container trước**, không phải file segment trước. Log đã rotate có thể nằm ngoài phạm vi dữ liệu mà API kubelet cung cấp; cần dựa vào pipeline thu thập.

### Bài 5: Non-root image

Một Java image dùng `USER 10001` và Logback ghi `/app/logs/app.log`. Khi deploy, appender báo không tạo được file. Nên tăng max-file ở Docker hay làm gì?

**Đáp án:** Đây là vấn đề **đường dẫn/quyền ghi file trong container**, không phải Docker log rotation. Kiểm tra thư mục, mount, UID/GID và security context; hoặc chuyển sang stdout để tránh cần file ghi riêng.

### Bài 6: Rotation và data loss

Collector ngừng hoạt động 20 phút, trong khi runtime xoay và xóa log cũ sau vài phút do lượng log lớn. Khi collector phục hồi, có chắc lấy lại được toàn bộ log không?

**Đáp án:** Không. File bị xóa trước khi được đọc sẽ không tự xuất hiện lại. Cần tăng khả năng buffer/retention phù hợp, giảm lượng log, giám sát backpressure và thiết kế cơ chế lưu/giao nhận đáp ứng yêu cầu thực tế.

### Bài 7: Hai replica cùng rolling file

Hai Pod Java mount cùng một PVC và cùng ghi `/logs/application.log` bằng RollingFileAppender. Rủi ro là gì?

**Đáp án:** Hai JVM có thể đồng thời ghi/rename/rollover cùng path, dẫn tới xung đột file, log lẫn nhau, mất dữ liệu hoặc metadata rolling sai. Nên tách đường dẫn theo instance hoặc dùng stdout với collector node-level để tránh file chung.

### Bài 8: Kiểm thử kiến trúc end-to-end

Bạn vừa cấu hình Compose `max-size=1m` và `max-file=3`. Hãy đề xuất các assertion cần có mà không đòi hỏi giữ toàn bộ lịch sử log.

**Đáp án gợi ý:**

1. `docker inspect` thấy driver/option đúng trên container thật.
2. Chạy chương trình mẫu với lượng log vượt ngưỡng.
3. Runtime vẫn ghi các sự kiện gần nhất và app không lỗi vì log tăng.
4. Dung lượng local tuân theo chính sách rotation khi quan sát bằng công cụ hỗ trợ.
5. Collector (nếu có) nhận dữ liệu và ghi nhận đầy đủ/trùng/mất theo mục tiêu hệ thống.
6. Restart/thay container được kiểm thử riêng với retention mong muốn.
7. Dọn container và file thử nghiệm an toàn.

## 19. Checklist triển khai rotation cho Java container

Trước khi chuyển sang production, cần xác nhận:

- [ ] **Đường đi:** Java ghi stdout/stderr hay file? Có nhiều appender cho cùng event không?
- [ ] **Owner rotation:** Docker driver, kubelet/node runtime hay Logback/Log4j 2?
- [ ] **Kích thước:** `max-size`/`containerLogMaxSize`/`maxFileSize` có phù hợp tốc độ log?
- [ ] **Số lượng/retention:** số segment hoặc ngày giữ có phù hợp nhu cầu tra cứu ngắn hạn?
- [ ] **Vòng đời:** dữ liệu còn khi container restart, pod replacement và node loss ở mức nào?
- [ ] **Thu thập:** collector có đọc kịp trước khi file cũ bị xóa không?
- [ ] **Quan sát:** có metric về disk pressure, số log drop, queue và ingest lag?
- [ ] **Bảo mật:** không log secret, quyền đọc và thời gian giữ phù hợp?
- [ ] **Tính đúng:** stack trace, Unicode, JSON Lines và partial record được parse chuẩn?
- [ ] **Đa replica:** không có nhiều tiến trình cùng rotate một file trên shared volume?
- [ ] **Xác minh runtime:** tùy chọn thực sự có hiệu lực, không chỉ hiện trong YAML/XML source?
- [ ] **Kiểm thử:** có bài test log volume, rotation, collector tạm ngưng và restart?
- [ ] **Phương án điều tra:** khi `docker logs`/`kubectl logs` không còn lịch sử, biết tìm tại kho nào?
- [ ] **Giới hạn trách nhiệm:** audit/đối soát quan trọng dùng cơ chế bền vững phù hợp, không chỉ console log.

**Kết luận:** Với đa số Java service chạy container, hãy ưu tiên **ConsoleAppender → stdout/stderr → runtime/kubelet rotation → collector**, mỗi tầng có trách nhiệm riêng. Khi ứng dụng cần file riêng, dùng rolling policy có quyền sở hữu rõ ràng và kiểm tra volume/sidecar. Rotation chỉ giới hạn log **cục bộ**; khả năng điều tra lâu dài và chống mất dữ liệu phụ thuộc vào pipeline thu thập, lưu trữ và chính sách retention được kiểm chứng.