# Giới hạn port exposed trong image: từ Dockerfile đến ranh giới mạng container

Một image ứng dụng chỉ cần nhận HTTPS thông qua reverse proxy, nhưng Dockerfile lại khai báo nhiều cổng như 8080, 9090 và 5005. Khi nhóm vận hành chạy image bằng tùy chọn tự động publish hoặc đưa vào môi trường container có cấu hình mạng quá rộng, các dịch vụ quản trị, metrics hoặc debug có thể bị truy cập từ nơi không mong muốn. Ngược lại, có ứng dụng **không hề khai báo EXPOSE** nhưng vẫn lắng nghe và được publish ra Internet nhờ cấu hình runtime. Hai tình huống này chỉ ra sự thật quan trọng: **giới hạn cổng ở image là một phần của quản trị bề mặt tấn công, không phải cơ chế firewall**.

Chủ đề **“Giới hạn port exposed trong image”** yêu cầu hiểu rõ vai trò của **metadata EXPOSE trong Docker/OCI image**, sự khác biệt giữa port **được khai báo**, port **đang lắng nghe**, port **được ánh xạ ra host** và port **có thể truy cập từ mạng thực tế**. Quy trình phòng thủ tốt không dừng ở việc xóa một dòng Dockerfile: cần thiết kế image tối giản, cấu hình runtime có chủ đích, network policy theo trust boundary, hạn chế cổng debug/quản trị và kiểm chứng sau triển khai.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, nội dung thuộc chương **Bảo mật mạng container**, gắn với phân đoạn mạng, firewall, TLS/mTLS, VPN, IDS/IPS, giám sát lưu lượng và kiến trúc cloud. Các lệnh dùng tên image, container và hostname giả định; chỉ thực hành trên **máy/lab hoặc hệ thống được phê duyệt**. Không quét port của tài sản bên ngoài phạm vi hoặc đưa container thí nghiệm lên mạng public chỉ để kiểm tra.

> **Thông điệp trọng tâm:** Dockerfile **EXPOSE không tự mở/publish cổng**. Bỏ EXPOSE **không chặn tiến trình lắng nghe** và cũng không ngăn người vận hành dùng **-p** để publish cổng. Bảo vệ thật sự đến từ **ứng dụng bind đúng interface, runtime publish có kiểm soát, phân đoạn mạng, firewall/network policy, xác thực và kiểm thử kết nối**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **image metadata, process listening socket, container port, host published port và network reachability**.
2. Giải thích đúng **Dockerfile EXPOSE**, **docker run -p/-P**, **Docker Compose expose/ports** và tác động của từng lựa chọn.
3. Nhận ra khi nào cổng quản trị, metrics, debug hoặc database **không nên xuất hiện trong hợp đồng network** của image chạy production.
4. Phân tích khác biệt giữa **127.0.0.1, 0.0.0.0, ::, Pod IP, host IP** và điểm kết thúc TLS.
5. Hiểu tác động của **bridge, user-defined networks, host networking, rootless mode, port forwarding và host firewall**.
6. Phân biệt metadata **containerPort** với quyền truy cập thật trong Kubernetes; xác định vai trò của **Service, Ingress/Gateway, hostPort, hostNetwork, NetworkPolicy và cloud firewall**.
7. Xây **port inventory**, ma trận **ALLOW/DENY**, kiểm tra drift và kiểm soát image/runtime bằng CI/CD hoặc policy-as-code.
8. Kiểm tra an toàn với **docker image inspect, docker ps, docker port, docker inspect, Compose config và kubectl** trong phạm vi được phép.
9. Điều tra port bất ngờ, thiếu port mapping, lỗi bind, hoặc service nội bộ lộ ra ngoài mà **không nhầm metadata EXPOSE với tính reachable**.

## 2. Năm khái niệm không được đánh đồng

Một cổng có thể được **khai báo**, **mở bởi tiến trình**, **được publish**, **có route tới** và **thực sự được sử dụng thành công** — đó là năm trạng thái khác nhau.

| Khái niệm | Ai quyết định? | Có chứng minh truy cập được từ Internet không? |
|---|---|---|
| **Declared/EXPOSE** | Dockerfile hoặc image config | **Không**: chỉ là metadata hợp đồng/gợi ý |
| **Listening** | Process và socket bind trong network namespace | **Không**: còn phụ thuộc interface và policy |
| **Published** | Runtime/orchestrator cấu hình port forwarding/binding | **Chưa đủ**: phụ thuộc host IP, route/firewall |
| **Reachable** | Network path + ACL/SG/firewall + listener | Có thể tới được transport, chưa có quyền |
| **Authorized** | TLS/mTLS, token, IAM và application policy | Phải xác minh riêng theo người dùng/workload |

~~~text
      Dockerfile image metadata
         EXPOSE 8080/tcp
                 |
                 v
       Container runtime process
       listen 0.0.0.0:8080
                 |
                 v
       Host port mapping (nếu có)
       127.0.0.1:18080 -> 8080
                 |
                 v
       Host firewall / SG / routing
                 |
                 v
         Client application
       authentication / authorization
~~~

Sơ đồ biểu diễn **những điều kiện độc lập**, không phải chuỗi bắt buộc. Ứng dụng có thể **listen mà không EXPOSE**, và runtime có thể **publish dù image không khai báo EXPOSE**. Ngược lại, image có EXPOSE nhưng không có process listen, khi đó không có dịch vụ thực sự ở cổng ấy.

### Ví dụ nhanh

~~~text
Image metadata:  EXPOSE 8080/tcp
Process:         chỉ listen 127.0.0.1:8080 bên trong container
Docker publish:  -p 18080:8080
Host firewall:   allow TCP/18080 từ mạng test

Kết quả khả dĩ: host port được publish, nhưng forwarded connection
không tới được ứng dụng nếu application chỉ bind loopback của container.
~~~

Điểm quan trọng là **127.0.0.1 của container không phải 127.0.0.1 của host** trong mô hình bridge thông thường.

## 3. Dockerfile EXPOSE thực chất làm gì?

Một Dockerfile có thể ghi:

~~~dockerfile
FROM example-runtime:stable
WORKDIR /app
COPY app/ /app/
EXPOSE 8080/tcp
CMD ["./server"]
~~~

**EXPOSE 8080/tcp** khai báo image dự kiến có dịch vụ sử dụng cổng TCP/8080. Nó **không tự làm process khởi động**, không bắt process bind TCP/8080, không thay đổi firewall host, không tự thiết lập host port mapping và không xác nhận ứng dụng an toàn.

### Cú pháp thông dụng

~~~dockerfile
EXPOSE 8080
EXPOSE 8080/tcp
EXPOSE 8125/udp
EXPOSE 8080/tcp 8125/udp
~~~

Nếu không ghi protocol, cú pháp Dockerfile EXPOSE thông thường mặc định **TCP**. **TCP và UDP trên cùng số port là hai đối tượng khác nhau**; khai báo TCP/53 không tự đồng nghĩa có khai báo UDP/53.

### EXPOSE không phải quy tắc DENY

| Image metadata | Runtime có thể làm gì? |
|---|---|
| EXPOSE 8080 | Chạy mà không publish cổng nào |
| EXPOSE 8080 | Publish bằng **-p 127.0.0.1:18080:8080** |
| Không có EXPOSE | Vẫn có thể publish **-p 18080:8080** |
| EXPOSE 8080, 9090 | Có thể chỉ publish 8080 nếu runtime được cấu hình như vậy |
| EXPOSE 8080 | Process có thể không lắng nghe; publish không tự tạo server |
| EXPOSE 8080 | Container trong một mạng được phép có thể truy cập cổng đang listen dù không có host publish |

**Xóa EXPOSE 9090 khỏi Dockerfile không tự đóng metrics endpoint nếu process vẫn listen trên 0.0.0.0:9090 và peer có route tới container.** Phải kiểm soát listener/namespace/network policy thực tế.

## 4. Vì sao vẫn nên giới hạn metadata EXPOSE?

Dù EXPOSE không phải firewall, khai báo đúng vẫn có giá trị bảo mật và vận hành:

1. **Documentation contract:** mô tả những cổng image dự kiến phục vụ.
2. **Tránh tự động publish ngoài ý định:** với một số cách chạy, ví dụ **docker run -P**, runtime dựa vào EXPOSE để chọn cổng sẽ publish.
3. **Giảm nhầm lẫn khi triển khai:** người vận hành không giả định debug/management port là public API.
4. **Kiểm tra image provenance:** CI có thể phát hiện thay đổi EXPOSE bất thường trong một image mới.
5. **Giảm bề mặt cấu hình:** hạn chế những cổng không cần thiết được truyền vào template Compose/Kubernetes/Helm.
6. **Owner review:** phát hiện base image hoặc dependency kéo theo metadata dịch vụ không phù hợp.

Nhưng cần đánh giá **security outcome** đúng:

~~~text
Đã xóa EXPOSE 9090?
          |
          +-- Có -> Metadata ít hơn
          |
          +-- Process còn listen 9090?
          |        |
          |        +-- Có -> Surface vẫn tồn tại
          |
          +-- Host/pod/peer còn reach 9090?
                   |
                   +-- Có -> Cần policy/runtime/app fix
~~~

**Hành động có giá trị lớn nhất** là xóa dịch vụ listener không cần thiết, hạn chế interface, không publish và chặn đường tiếp cận ngoài quyền; EXPOSE chỉ là phần khai báo.

## 5. Threat model: port nào gây rủi ro?

Không phải mọi port đều nguy hiểm như nhau; rủi ro phụ thuộc **dịch vụ lắng nghe, vị trí mạng, thông tin được phục vụ, authentication, quyền của process và khả năng khai thác lỗi**.

| Loại endpoint | Ví dụ | Mối nguy điển hình |
|---|---|---|
| **Public application** | HTTP/gRPC trên 8080, 8443 | Lỗi xác thực/ủy quyền, WAF bypass, DDoS |
| **Admin UI/API** | Management HTTP trên 9000/9090 | Thao tác cấu hình hoặc dữ liệu nhạy cảm |
| **Debug agent** | Remote debugger 5005 | Kiểm soát tiến trình hoặc thông tin runtime nếu không bảo vệ |
| **Metrics** | Prometheus-style metrics trên 9090 | Lộ topology, internal labels, workload status |
| **Health endpoint** | /health trên cùng app port hoặc port riêng | Lộ chi tiết dependency, abuse nếu kiểm tra nặng |
| **Database/broker** | PostgreSQL 5432, Redis 6379 hoặc service riêng | Truy cập dữ liệu, lạm dụng khi auth/network policy yếu |
| **Service discovery/control plane** | Nhiều port TCP/UDP tùy hệ thống | Lộ metadata, thao tác điều khiển |
| **Sidecar/service mesh** | Listener inbound/outbound, admin port | Bypass policy hoặc lộ xDS/admin interface tùy cấu hình |

Port number là **quy ước**, không phải bằng chứng chức năng. Một service HTTP có thể dùng cổng 5432, và PostgreSQL có thể cấu hình cổng khác. Muốn đánh giá cần xem **process thực, socket bind và luồng mạng có phép**, không suy từ số port.

### Câu hỏi thiết kế

- Endpoint có cần nhận kết nối từ **Internet, host, cùng pod, cùng cluster, VPN, private service, monitoring** hay không?
- Ai chịu trách nhiệm **authenticate/authorize**?
- Có cần một listener riêng, hay có thể dùng **sidecar/Unix domain socket/reverse proxy** trong trust boundary?
- Nếu chỉ phục vụ metrics nội bộ, có nên **bind loopback** và dùng trusted collector thay vì expose ra toàn subnet?
- Khi chạy nhiều replica, có **port mapping tự động, NodePort, hostPort hoặc hostNetwork** làm khác phạm vi truy cập?

## 6. Lập port inventory trước khi sửa image

Đừng bắt đầu từ câu “nên chỉ EXPOSE 8080”. Trước tiên xây danh mục mọi listener và người sử dụng chúng.

| Trường | Ý nghĩa |
|---|---|
| Image name + immutable digest | Xác định chính xác phiên bản image |
| Dockerfile/build context owner | Nhóm chịu trách nhiệm thay đổi image |
| Image **ExposedPorts** | Metadata đang có, gồm protocol |
| Runtime command/process | Tiến trình nào thật sự khởi động |
| Listen IP:port/protocol | Socket 127.0.0.1, 0.0.0.0, :: hoặc IP cụ thể |
| Publish host IP:port → container port | Bề mặt truy cập từ ngoài container |
| Network namespace/mode | bridge, host, overlay, Kubernetes Pod network |
| Service/Ingress/LB mapping | Đường truy cập qua orchestrator |
| Caller/service owner | Ứng dụng/tenant/system nào cần truy cập |
| Authentication/TLS policy | Biện pháp bảo vệ cao hơn port |
| Intended exposure | public, private, same-host, same-pod hoặc none |
| Evidence timestamp | Thời điểm kiểm tra và nguồn dữ liệu |

### Ví dụ inventory tổng hợp

| Port/proto | Component | Image EXPOSE | Process listen | Publish/Service | Mong muốn |
|---|---|---|---|---|---|
| TCP/8080 | Web API | Có | 0.0.0.0:8080 | Private ingress → API | Private từ gateway |
| TCP/9090 | Metrics | Không cần | 127.0.0.1:9090 | Không publish | Chỉ collector được phép |
| TCP/5005 | Debug | Không | Không trong production | Không publish | DENY production |
| TCP/5432 | Database | Không thuộc API image | Không | DB service riêng | Chỉ app tới DB |
| UDP/8125 | Telemetry | Chỉ nếu thiết kế thực sự yêu cầu | Tùy agent | Private network | Chỉ collector/agent |

Những số port và giao thức trong bảng là **ví dụ**, không phải danh sách cổng của một image thực. Hãy ghi rõ khi một port do **sidecar** hoặc process khác sở hữu; không quy tất cả listener trong Pod cho ứng dụng chính.

## 7. Thiết kế Dockerfile tối giản và đúng mục đích

### Image production chỉ có một API listener

~~~dockerfile
# Ví dụ minh họa; trong hệ thống thật dùng base image được phê duyệt,
# pin theo digest và quét lỗ hổng theo quy trình.
FROM example-runtime:stable

WORKDIR /app
COPY app/ /app/

# Metadata: đây là cổng ứng dụng được thiết kế phục vụ.
EXPOSE 8080/tcp

USER 10001
CMD ["./server"]
~~~

**EXPOSE là hợp đồng khai báo**; còn ứng dụng phải bind đúng interface để client dự kiến có thể kết nối. Chạy với **USER không phải root** giảm một số rủi ro khi process bị khai thác, nhưng không thay network policy, application authorization hoặc quản lý Linux capabilities.

### Production không nên vô tình bật debug listener

~~~dockerfile
# Không nên đưa vào image production nếu debug không được sử dụng:
EXPOSE 5005/tcp
~~~

Quan trọng hơn việc bỏ dòng trên:

- Không khởi chạy runtime với **remote debugging enabled** trong production trừ trường hợp đặc biệt được phê duyệt và cô lập.
- Không dùng **0.0.0.0** cho debug agent nếu không cần remote debugging.
- Không publish port debug qua Docker/Kubernetes/Service/Ingress/hostPort.
- Đánh giá remote debugging như một **khả năng điều khiển process**, không chỉ là cổng TCP.
- Dùng môi trường staging hoặc quy trình debug có kiểm soát thay vì bật vĩnh viễn trên production.

**Không xóa EXPOSE rồi cho rằng debug đã bị chặn** nếu tham số JVM/runtime vẫn bật listener.

## 8. Base image và multi-stage build: metadata có thể được kế thừa

Khi dùng **FROM base-image**, image cuối có thể kế thừa cấu hình image từ base, bao gồm **ExposedPorts**, tùy stage cuối và cách build. Vì vậy **Dockerfile cuối không viết EXPOSE** chưa chắc image cuối không có metadata EXPOSE.

~~~dockerfile
# Stage build minh họa
FROM example-builder:stable AS build
WORKDIR /src
COPY src/ /src/
RUN ./build.sh

# Stage runtime là image độc lập hơn và được review riêng.
FROM example-minimal-runtime:stable
WORKDIR /app
COPY --from=build /src/out/server /app/server
USER 10001
EXPOSE 8080/tcp
CMD ["/app/server"]
~~~

Ví dụ giả định các base image và lệnh build tồn tại trong lab của tổ chức; đây **không phải Dockerfile hoàn chỉnh có thể build ngay**.

### Điều cần kiểm tra

1. **Final stage FROM** dựa vào image nào và nó đã khai báo port gì?
2. Image cuối có metadata **ExposedPorts** thực tế thế nào sau build?
3. Có runtime process hoặc entrypoint bổ sung từ base image không?
4. Có port khác được mở bằng runtime flags/env hoặc sidecar không?
5. Nếu muốn loại bỏ metadata thừa kế, có cần **chọn lại runtime base/build strategy** thay vì chỉ bỏ EXPOSE trong Dockerfile?

Không giả định một lệnh **EXPOSE mới ghi đè/xóa tất cả EXPOSE đã có** trong base image. Chỉ kiểm tra image artifact sau build mới cho kết quả chính xác.

## 9. Docker run -p, -P: publish không giống EXPOSE

### Không publish

~~~bash
docker run --name api-lab --rm demo-api:lab
~~~

Nếu image có **EXPOSE 8080**, chạy lệnh này **không tự publish TCP/8080 ra host** bằng cơ chế Docker port mapping. Tuy nhiên, những container khác trên mạng Docker thích hợp **có thể truy cập listener** tùy network isolation/firewall; và network mode không phải bridge mặc định có thể khác.

### Publish có chỉ định host interface

~~~bash
docker run --name api-lab --rm \
  -p 127.0.0.1:18080:8080 \
  demo-api:lab
~~~

Lệnh này minh họa ánh xạ **host loopback TCP/18080 → container TCP/8080** trên Docker Engine trong cấu hình hỗ trợ. Nó giảm phạm vi host binding so với publish tới tất cả host interfaces, nhưng phải kiểm tra **phiên bản Engine, network driver, host firewall và bề mặt truy cập thực**; không xem loopback binding là giải pháp bảo mật toàn bộ nếu có proxy/tunnel hoặc cấu hình nền tảng khác.

### Publish rộng

~~~bash
docker run --name api-lab --rm \
  -p 18080:8080 \
  demo-api:lab
~~~

Khi không nêu host IP, Docker bridge port publishing thường dùng **all host addresses theo cấu hình Docker network mặc định**, điều này có thể khiến service reachable từ các mạng ngoài host nếu route/firewall cho phép. Với dual-stack, cần xác minh IPv4 và IPv6. Đừng mặc định “cổng trên máy mình” nghĩa là chỉ localhost.

### Publish toàn bộ port được khai báo bằng -P

~~~bash
docker run --name api-lab --rm -P demo-api:lab
~~~

**-P / --publish-all** yêu cầu Docker publish những port được image khai báo EXPOSE (hoặc cấu hình exposed tương ứng) tới host ports được cấp tự động theo khả năng runtime. Nếu image chứa một metadata EXPOSE thừa như cổng debug, lựa chọn -P có thể làm cổng đó **được publish ngoài ý định**. Đây là một lý do nên **giảm EXPOSE metadata** và tránh sử dụng -P không kiểm soát trong production.

| Cơ chế | Dựa vào EXPOSE? | Có thể mở host port? |
|---|---|---|
| **EXPOSE 8080** trong Dockerfile | Là bản thân metadata | Không tự mở |
| **docker run** không -p/-P | Không publish theo EXPOSE | Không bằng port mapping Docker |
| **docker run -p 18080:8080** | **Không yêu cầu** EXPOSE tồn tại | Có |
| **docker run -P** | Dựa vào exposed ports trong image/container config | Có, tự chọn host port |
| **host network mode** | Không cần port mapping theo kiểu bridge | Process dùng network namespace của host; phải bảo vệ riêng |

**-p có thể publish một cổng không hề có trong EXPOSE**, nhưng nếu không có process lắng nghe phù hợp thì kết nối vẫn không cung cấp dịch vụ.

## 10. Bind address của ứng dụng khác host published address

Đây là hai quyết định ở **hai network namespace khác nhau** khi dùng bridge:

~~~text
Within container:
  app listen 127.0.0.1:8080  -> chỉ loopback của container
  app listen 0.0.0.0:8080    -> mọi IPv4 interface của container

On host:
  -p 127.0.0.1:18080:8080  -> chỉ định host bind localhost
  -p 18080:8080            -> thường host bind rộng nếu không thay default
~~~

### Tình huống thường gặp

| Container listen | Host publish | Kết quả/kết luận |
|---|---|---|
| 0.0.0.0:8080 | 127.0.0.1:18080:8080 | Có thể kết nối từ host loopback theo policy |
| 0.0.0.0:8080 | 0.0.0.0:18080:8080 | Có thể reachable từ mạng ngoài host; cần firewall/auth |
| 127.0.0.1:8080 | 0.0.0.0:18080:8080 | Mapping tồn tại nhưng bridge traffic thường không tới listener chỉ ở container loopback |
| 0.0.0.0:8080 | Không publish | Có thể reachable từ peer trong mạng container phù hợp |
| Không listen 8080 | Publish 18080:8080 | Publish không tự tạo ứng dụng |

**Binding 0.0.0.0 trong container không đồng nghĩa Internet exposure.** Nó cho phép nhận kết nối ở các interface IPv4 container; Internet reachability còn tùy runtime publish, mạng, route và firewall. Ngược lại, bind localhost có thể làm backend **không kết nối được** nếu nó ở container hoặc Pod khác.

### IPv6 bind

**::** là IPv6 unspecified address. Tùy OS, socket option và runtime, bind IPv6 có thể chỉ nhận IPv6 hoặc có hành vi dual-stack. **0.0.0.0 và :: không hoán đổi tuyệt đối**. Khi bật IPv6 cho host/container, phải kiểm tra **effective listeners, published addresses và firewall IPv6** thay vì chỉ nhìn IPv4.

## 11. Kiểm kê image và runtime bằng Docker CLI chỉ đọc

Trong lab hoặc máy thuộc quyền quản trị, có thể quan sát metadata và port publishing mà không chỉnh cấu hình container.

### 11.1. Xem image EXPOSE metadata

~~~bash
docker image inspect demo-api:lab \
  --format '{{json .Config.ExposedPorts}}'
~~~

Ví dụ kết quả:

~~~json
{"8080/tcp":{}}
~~~

Đây là metadata image. Kết quả rỗng/null **không chứng minh image không chứa ứng dụng lắng nghe port**, cũng không chứng minh runtime đã chặn mọi kết nối.

### 11.2. Xem container được publish thế nào

~~~bash
docker ps --format 'table {{.Names}}\t{{.Ports}}'
docker port api-lab
docker inspect api-lab --format '{{json .NetworkSettings.Ports}}'
~~~

Tùy runtime/state, các lệnh có thể hiển thị mapping như:

~~~text
8080/tcp -> 127.0.0.1:18080
~~~

**Docker ps/port/inspect cho biết cấu hình/mapping đang quan sát**, không thay cho kiểm chứng mạng từ nguồn cụ thể. Một mapping có thể tồn tại dù process không listen hoặc host firewall/network policy chặn kết nối.

### 11.3. Xem listener thật trong container nếu được phép

~~~bash
# Cần container tồn tại, quyền exec và có utility ss.
docker exec api-lab sh -c 'ss -lntup'
~~~

Lệnh này chỉ nhằm quan sát sockets; **không phải mọi image tối giản đều có shell hoặc ss**. Khi thiếu công cụ, có thể dùng host/container telemetry, runtime introspection hoặc debug container được tổ chức cho phép; **không cài thêm tool vào production image chỉ để rà cổng**.

### Trình tự kết luận

1. **Image inspect** → declared EXPOSE metadata.
2. **Runtime inspect** → host/container published mapping và network mode.
3. **Process/socket observation** → lắng nghe thực sự.
4. **Network policy/firewall/route** → reachable từ đâu.
5. **Authorized test** → service có chấp nhận kết nối và xử lý đúng quyền không.

Một **Docker ps PORTS** hiển thị **8080/tcp** mà **không có mũi tên host mapping** không tự chứng minh dịch vụ đó public.

## 12. Docker Compose: expose khác ports

Trong Docker Compose, hai cấu hình rất dễ nhầm:

~~~yaml
services:
  api:
    image: demo-api:lab
    expose:
      - "8080"
    networks:
      - app_net

  frontend:
    image: demo-frontend:lab
    networks:
      - app_net

networks:
  app_net: {}
~~~

**expose** khai báo các cổng mà service dự định tiếp nhận từ các service khác trong network phù hợp; **không publish port ra host**. Tuy nhiên, **cùng một user-defined Docker network**, các container có thể kết nối tới những port đang lắng nghe phù hợp **kể cả khi chúng không có tên trong expose**, theo network isolation/firewall hiện hành. Vì vậy **expose cũng không phải allowlist bảo mật** giữa các container.

### Compose ports: cấu hình host publishing

~~~yaml
services:
  api:
    image: demo-api:lab
    ports:
      - "127.0.0.1:18080:8080"
    networks:
      - app_net

networks:
  app_net: {}
~~~

**ports** có thể yêu cầu Docker publish host TCP/18080 từ localhost tới container TCP/8080. Cách biểu diễn, phạm vi host bind và kết quả phụ thuộc runtime/network driver; phải xem cấu hình đã được resolve và kiểm tra từ nguồn mạng dự kiến.

### So sánh nhanh

| Compose/Runtime | Đặc điểm | Có làm service public không? |
|---|---|---|
| **image EXPOSE** | Khai báo metadata | Không tự |
| **Compose expose** | Khai báo service ports, không publish host | Không tự; peer có route vẫn có thể tới listener |
| **Compose ports** | Yêu cầu publish host–container | Có thể, tùy host IP/route/firewall |
| **expose + network isolation** | Có thể mô tả ý định và giới hạn network peer | Phải kiểm chứng bằng network topology và policy |
| **Compose internal network** | Hỗ trợ cấu hình mạng cô lập ngoài theo semantics Engine | Không tự thay auth hoặc host policy |

### Kiểm tra cấu hình Compose trước deploy

~~~bash
docker compose config
docker compose ps
~~~

**docker compose config** hiển thị cấu hình Compose được hợp nhất/diễn giải theo khả năng CLI và có thể chứa các giá trị cấu hình nhạy cảm nếu Compose sử dụng chúng. Hãy **kiểm tra/redact trước khi chia sẻ kết quả**. **docker compose ps** cho thấy service và published ports tại thời điểm kiểm tra, không thay thế phép thử mạng.

Nếu chỉ muốn phục vụ API từ một reverse proxy cùng mạng, thường không cần publish app port ra host; **proxy/gateway là điểm ingress được cấp quyền**. Nhưng phải bảo đảm các container/workload không tin cậy không được gắn chung network và có đường tới API không được xác thực.

## 13. Docker bridge, network segmentation và đường truy cập nội bộ

Trong Docker bridge networking, container có địa chỉ mạng và có thể giao tiếp với peer theo cấu hình mạng, routes và firewall. **Không host-publish** thường loại bỏ một đường truy cập qua host port mapping, nhưng không phải **cách ly container khỏi mọi peer**.

~~~text
                         Host
   +-----------------------------------------------+
   | Reverse proxy (published 443)                 |
   |        |                                      |
   |        v                                      |
   |   app_net: API:8080                           |
   |        |                                      |
   |        v                                      |
   |   data_net: DB:5432                           |
   |                                               |
   | Guest container: không tham gia app_net       |
   +-----------------------------------------------+
~~~

### Nguyên tắc phân đoạn

- Tách **public-facing gateway** khỏi service/backend bằng các network group theo vai trò.
- Chỉ gắn container vào những mạng nó **thật sự cần**, không nối mọi workload vào một shared network rộng.
- Database không cần được publish ra host chỉ vì API gọi được database.
- Không dựa vào **service name hoặc alias** như bằng chứng xác thực identity; DNS trong network chỉ giúp tìm đích.
- Nếu dùng **internal** networks, xác minh chính xác semantics về external connectivity, host access và network gateway của phiên bản Docker đang vận hành.
- Xem xét **host firewall và cloud security groups** bên ngoài Docker, không chỉ container network config.

### Cách dùng network_mode làm thay đổi giả định

| Network mode (khái quát) | Hệ quả |
|---|---|
| **bridge** | Container có namespace/network riêng; port mapping là lựa chọn runtime |
| **none** | Container bị hạn chế connectivity mạng theo runtime, thường chỉ có loopback |
| **host** | Container dùng network namespace của host; **-p không có ý nghĩa bridge mapping như thông thường** |
| **container:... / share namespace** | Container chia sẻ network namespace với container khác theo lựa chọn runtime |
| **overlay/other driver** | Scope/connectivity thay đổi theo orchestrator và driver |

**Host networking là trường hợp đặc biệt rủi ro**: process bind 0.0.0.0 trên host network có thể lắng nghe trực tiếp trên host interfaces dù image **không có EXPOSE** hoặc người triển khai không chỉ định **-p**.

## 14. host networking, privileged mode và quyền trên host

~~~text
Bridge mode:
  app binds container-IP:8080
  host publish is an independent mapping decision

Host mode:
  app binds host-network:8080
  container/host share network namespace
~~~

### Vì sao host networking cần phê duyệt riêng?

1. Nó bỏ đi giả định rằng container có **network namespace tách biệt khỏi host**.
2. Port bind conflict với host process hoặc container host-network khác có thể xảy ra.
3. Host firewall và các network interfaces trở nên đặc biệt quan trọng.
4. Một process nhầm lẫn bind mọi interface có thể mở service ở ngoài ý định.
5. NetworkPolicy tại mức pod/container có thể có giới hạn áp dụng lên host-network workloads tùy nền tảng/CNI.

**Privileged container** và các capability liên quan networking là một lớp rủi ro khác. Không cần privileged mode để chạy một HTTP application thông thường. Một process root/capability rộng có thể thay đổi cấu hình mạng hoặc có nhiều quyền hơn khi bị xâm nhập, dù EXPOSE ít cổng.

### Rootless containers và cổng thấp

Rootless Docker hoặc process không có quyền root có những ràng buộc khác với binding cổng đặc quyền (như một số port dưới 1024), phụ thuộc OS/sysctl/runtime và cách port forwarding được triển khai. **Không sửa quyền/capability toàn hệ thống chỉ để image có thể bind TCP/80** nếu có thể phục vụ trên cổng không đặc quyền như 8080 phía trong và để proxy/LB kết thúc public HTTPS/TCP/443 phía ngoài.

## 15. Một Pod Kubernetes chia sẻ network namespace

Trong Kubernetes, **các container trong cùng một Pod chia sẻ network namespace**, bao gồm **Pod IP và không gian TCP/UDP ports**. Vì vậy:

- Hai container trong cùng Pod không thể cùng bind cùng một địa chỉ/protocol/port nếu socket đó đã chiếm.
- Một sidecar thường có thể gọi process ở **localhost** trong cùng Pod nếu listener phù hợp.
- Một container trong Pod không có EXPOSE vẫn có thể listen và được peer trong/ngoài Pod truy cập tùy policies.
- **Pod network policy thường được đánh giá ở phạm vi Pod**, không dùng để tách các container cùng Pod theo từng port nội bộ như những trust boundary độc lập.

~~~text
              Kubernetes Pod
      +-----------------------------+
      | Pod IP: 10.244.1.20         |
      |                             |
      | app container               |
      |   listen 0.0.0.0:8080       |
      |                             |
      | sidecar container           |
      |   listen 127.0.0.1:15000    |
      |                             |
      | Shared localhost/ports      |
      +-----------------------------+
~~~

Nếu metrics ở **127.0.0.1:15000**, những container **cùng Pod** vẫn có thể truy cập localhost này nếu đủ quyền, nhưng những Pod khác **không thể trực tiếp kết nối tới nó qua Pod IP** như một socket bind trên Pod IP. Đừng dùng loopback như ranh giới bảo mật giữa các container **cùng Pod**.

## 16. Kubernetes containerPort cũng là khai báo, không phải firewall

Trong Pod spec, có thể khai báo:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
  namespace: app-prod
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      containers:
        - name: api
          image: registry.example.test/catalog-api@sha256:EXAMPLE_DIGEST
          ports:
            - name: http
              containerPort: 8080
              protocol: TCP
~~~

**Lưu ý:** Digest trong ví dụ là placeholder, không dùng để deploy. Đây là **manifest minh họa**; còn cần registry, image hợp lệ, namespace, probes, tài nguyên và kiểm soát khác để chạy thực tế.

**containerPort 8080 không publish TCP/8080 ra node hoặc Internet** và **không tự chặn** những port không khai báo. Kết nối tới process qua Pod IP có thể hoạt động **dù không khai containerPort**, miễn là có listener và mạng/policy cho phép. Khai báo containerPort hữu ích để **đặt tên port, tham chiếu trong Service/probes và mô tả ứng dụng**.

### Image EXPOSE so với Pod containerPort

| Phần | Phạm vi | Thực sự thực thi network access? |
|---|---|---|
| **Dockerfile EXPOSE** | Image metadata | Không |
| **Kubernetes containerPort** | Pod/container spec metadata | Không |
| **Kubernetes Service** | Cách định tuyến dịch vụ tới Pod | Tạo một đường truy cập tùy type/config |
| **Kubernetes NetworkPolicy** | Chính sách ingress/egress tới Pod theo CNI hỗ trợ | Có thể thực thi lọc traffic theo policy |
| **Cloud firewall/security group** | Network boundary của node/LB/cluster | Có theo policy và kiến trúc |
| **Process bind** | Socket thực trong Pod network namespace | Quyết định có listener trên interface nào |

### Probe khác ingress công khai

Các cấu hình **livenessProbe, readinessProbe, startupProbe** có thể dùng port của ứng dụng, nhưng **không tự khiến cổng ấy public**. Một liveness probe TCP thành công chỉ chứng minh một mức reachability nhất định, không đảm bảo identity/auth hoặc readiness nghiệp vụ. Phải kiểm tra probe không lộ dữ liệu nhạy cảm hoặc gây tải quá lớn.

## 17. Kubernetes Service: ClusterIP, NodePort, LoadBalancer

Kubernetes Service tạo một abstraction truy cập tới các Pod mà nó chọn, tùy **type, selector, ports, targetPort và network implementation**.

~~~text
Client outside cluster
         |
      Ingress / Gateway / LB
         |
       Service
     port: 80
       |
       v
 Pod targetPort: 8080
       |
       v
 Process listens on Pod IP:8080
~~~

### Các loại Service thường gặp

| Service type | Đường truy cập chung | Rủi ro cần xét |
|---|---|---|
| **ClusterIP** | Virtual IP/dịch vụ bên trong cluster theo routing/network | Không có nghĩa chỉ riêng một namespace được quyền gọi |
| **NodePort** | Cổng được cấp trên node theo cơ chế Service | Có thể reachable từ mạng ngoài node nếu route/firewall cho phép |
| **LoadBalancer** | Tích hợp external/internal LB tùy provider/config | Có thể tạo public LB nếu chưa chỉ định internal/private rõ |
| **ExternalName** | DNS alias tới tên ngoài theo mô hình Service | Không tự là proxy/TLS enforcement |

### Ví dụ Service private

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: app-prod
spec:
  type: ClusterIP
  selector:
    app: catalog-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
~~~

Service **ClusterIP** là phương tiện tìm/định tuyến tới workload trong cluster; nó **không có nghĩa workload chỉ nhận từ một caller đáng tin**, và không tự xác thực người gọi. Cần **NetworkPolicy, mTLS, authentication, authorization** để hạn chế truy cập.

**Một Service numeric targetPort như 8080 có thể gửi traffic đến listener Pod cho dù containerPort không được khai báo**. Việc xóa EXPOSE hoặc containerPort vì thế không đảm bảo Service ngừng hoạt động.

## 18. Ingress, Gateway API, hostPort và hostNetwork

### Ingress/Gateway

Một Ingress controller hoặc Gateway API implementation có thể tạo route từ public/private LB đến Service. Bề mặt phơi lộ phụ thuộc **controller class, listener, hostname, TLS, route, LB annotations/parameters, cloud firewall và gateway policy**, không chỉ từ image.

~~~text
Public Internet
      |
  Cloud LB:443
      |
  Ingress/Gateway controller
      |
  ClusterIP service:80
      |
  Pod:8080
~~~

Nếu không muốn public, cần chỉ định **internal/private gateway/LB theo platform** và kiểm thử từ nguồn ngoài. Không suy “Service là ClusterIP” nghĩa toàn bộ kiến trúc private nếu Ingress hoặc LoadBalancer public đã định tuyến tới Service đó.

### hostPort

Kubernetes **hostPort** yêu cầu ánh xạ một port ở node tới container port theo cơ chế runtime/CNI, tạo bề mặt cần xem xét tại node.

~~~yaml
ports:
  - name: http
    containerPort: 8080
    hostPort: 18080
    protocol: TCP
~~~

Không nên dùng hostPort khi Service/Ingress chuẩn đã đáp ứng mục tiêu, vì nó có thể làm tăng phụ thuộc vào port trên node, gây tranh chấp khi scheduling và thay đổi network exposure.

### hostNetwork

~~~yaml
spec:
  hostNetwork: true
~~~

Với **hostNetwork**, Pod dùng network namespace của node theo semantics Kubernetes, không còn sự cách ly Pod IP thông thường. Những listener bind all interfaces cần được coi là **node-level attack surface**, phải xét cloud SG, node firewall, service account, capabilities và CNI/NetworkPolicy coverage.

**Không được coi Image EXPOSE hoặc containerPort là biện pháp hạn chế hostPort/hostNetwork**.

## 19. Kubernetes NetworkPolicy: kiểm soát truy cập bằng thực thi CNI

Nếu container chạy Kubernetes, giới hạn ingress/egress theo **nguồn Pod/namespace, địa chỉ IP và port** có thể thực thi bằng **NetworkPolicy**, khi cluster sử dụng CNI có hỗ trợ chính sách mạng.

### Ví dụ chỉ cho gateway được chọn gọi TCP/8080

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: catalog-api-allow-gateway
  namespace: app-prod
spec:
  podSelector:
    matchLabels:
      app: catalog-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-system
          podSelector:
            matchLabels:
              app: trusted-gateway
      ports:
        - protocol: TCP
          port: 8080
~~~

**Ý nghĩa:** Trong namespace **app-prod**, policy chọn Pod có nhãn **app: catalog-api** và cho phép ingress TCP/8080 từ Pod **app: trusted-gateway** nằm trong namespace có nhãn **kubernetes.io/metadata.name: ingress-system**. Trong một phần tử **from** chứa cả namespaceSelector lẫn podSelector, hai điều kiện đó được kết hợp **AND**; nếu đặt thành hai phần tử danh sách độc lập, phạm vi có thể thành **OR** rộng hơn dự định.

### Những điều cần kiểm chứng

1. CNI thực tế **có enforce NetworkPolicy** hay resource chỉ tồn tại mà không được áp?
2. Các Pod có **labels chính xác** và namespace selector đúng không?
3. Có những NetworkPolicy khác cùng chọn Pod không? **Các allowed flows thường là hợp (union) của những policy áp dụng**, không phải policy sau ghi đè policy trước.
4. **Ingress isolation** không tự tạo egress isolation nếu không có policy chọn Pod cho egress theo semantics Kubernetes.
5. Lưu lượng từ node/hostNetwork và một số luồng đặc biệt có **ngoại lệ/phụ thuộc CNI**; phải thử thật trong staging.
6. Nếu chặn egress mặc định, có cần thêm đường **DNS, CA/PKI, logging, auth service, database** theo thiết kế không?
7. Một Pod có thể nhận traffic từ service mesh sidecar/ingress node theo source identity/địa chỉ khác dự đoán; xem flow path thật.

**NetworkPolicy không thay authentication**. Một Pod được phép tới TCP/8080 chưa chắc có quyền gọi API; backend vẫn phải xác minh caller, token/mTLS và resource authorization.

### Default deny theo hướng cụ thể

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: catalog-api-default-deny-ingress
  namespace: app-prod
spec:
  podSelector:
    matchLabels:
      app: catalog-api
  policyTypes:
    - Ingress
  ingress: []
~~~

Một policy riêng **default deny ingress** có thể là nền tảng tốt nếu có các allow policy cần thiết khác. Không nên áp vào production chưa kiểm kê caller hợp lệ; nó có thể cắt readiness path, gateway traffic hoặc service-to-service connections nếu chưa thiết kế đúng.

## 20. Giới hạn egress: port không publish vẫn có thể tạo rủi ro

Mối đe dọa không chỉ là **ai kết nối vào container**. Một image bị chèn mã độc hoặc một process bị khai thác có thể chủ động gọi tới dịch vụ nội bộ, external API, DNS resolver hoặc máy quản trị nếu egress không bị giới hạn.

| Luồng egress | Rủi ro nếu quá rộng | Kiểm soát phù hợp |
|---|---|---|
| API → Database | Truy cập các DB khác không thuộc quyền | NetworkPolicy/SG, DB auth, mTLS |
| API → Internet | Gửi dữ liệu ra endpoint ngoài ý muốn | Egress gateway/proxy, allowlist đích theo policy |
| API → Metadata/management service | Đọc quyền/secret của workload tùy cấu hình | IAM tối thiểu, metadata controls, network policy khi áp dụng |
| API → DNS | DNS tunneling/queries bất thường | Resolver policy, logging, hạn chế egress theo kiến trúc |
| Metrics collector → Pod | Thu thập quá nhiều endpoint | Access control, service identity, mạng monitoring riêng |

**Bỏ EXPOSE không giới hạn egress.** Cần phối hợp egress policies với **service account/IAM tối thiểu, DNS policy, TLS và application-level outbound allowlist** khi có yêu cầu.

### Một nguyên tắc không được hiểu sai

**NetworkPolicy là mô hình L3/L4 dựa trên Pod/namespace/IP/port**, không bảo đảm lọc ổn định theo FQDN trên mọi CNI. Nếu cần quản lý FQDN/HTTP host/URL, sử dụng tính năng gateway/proxy/CNI mở rộng được hỗ trợ và kiểm thử DNS cache/IP changes thay vì giả định Kubernetes NetworkPolicy thuần tự làm được.

## 21. Phân biệt port của API, metrics, debug và health

Một image đa chức năng có thể có:

~~~text
api-server:
  :8080  main HTTP/gRPC API
  :9090  metrics/management
  :5005  remote debug
  :8081  health
~~~

### Chiến lược giảm bề mặt tấn công

| Loại | Khuyến nghị thực hành |
|---|---|
| **API chính** | Một ingress path có TLS/gateway/auth và policy phù hợp |
| **Metrics** | Chỉ collector đã phê duyệt; có thể bind loopback/Pod-local hoặc private monitoring path |
| **Debug** | Không bật trên production trừ trường hợp đặc biệt có kiểm soát, thời hạn và audit |
| **Health** | Không lộ stack trace, secret hay dependency inventory ra Internet; probe ít tác động |
| **Admin** | Identity mạnh, network riêng, VPN/Zero Trust/mTLS và audit nếu phải hỗ trợ |

### Có nên dùng một port cho mọi endpoint?

Một listener duy nhất giảm số socket/public routes cần quản trị nhưng có thể **gộp trust boundary**: /admin và /metrics chạy cùng hostname/API nếu route/auth không được thiết kế đúng. Tách port có thể giúp áp network policy khác nhau, nhưng cũng tăng cấu hình/điểm lộ nếu publish nhầm.

**Không có câu trả lời chung “ít port luôn an toàn hơn”**: mục tiêu là **ít điểm tiếp cận ngoài quyền**, đúng lớp xác thực, dễ kiểm toán và không tạo bypass.

## 22. TLS termination và quyền truy cập container port

Kiến trúc thường dùng reverse proxy/gateway:

~~~text
User
  |
  | TLS 1.3 HTTPS :443
  v
Public LB / Reverse Proxy
  |
  | TLS riêng hoặc internal transport
  v
Private container :8080
  |
  v
Application authorization
~~~

### Những điều không được suy từ EXPOSE

- Image EXPOSE 8080 không cho biết **TLS có được bật ở container không**.
- Container nghe HTTP cleartext phía sau LB chưa chắc đáp ứng yêu cầu bảo mật đường **LB → backend**, đặc biệt qua nhiều host/subnet/cluster.
- TLS client → LB không tự bảo vệ **LB → App**; cần threat model và xác minh hop đó.
- Host publish chỉ localhost không chứng minh người dùng có identity hợp lệ; có thể có local proxy/chương trình trên host truy cập cổng.
- Metrics/debug trên port riêng cần **network policy và auth** nếu chúng có khả năng nhận từ thành phần ngoài trust boundary.

**Kiểm tra từng TLS hop, certificate/trust, service identity và authorization** theo kiến trúc. Không dùng “chỉ nội bộ” làm lý do mặc định bỏ mTLS hoặc access control cho dữ liệu nhạy cảm.

## 23. Port scanning và phân tích image: ưu tiên ít tác động

Để biết image có listener ngoài ý muốn, quy trình nên ưu tiên:

1. **Đọc Dockerfile/final image config** (EXPOSE, entrypoint, CMD) từ artifact được phép.
2. **Đọc runtime config** (publishing, network namespace/mode, Service/Ingress/hostPort) từ API quản trị.
3. **Quan sát sockets/process telemetry** của container được quản lý, nếu có khả năng.
4. **Đối chiếu network policy/SG/firewall** và source identity được phép.
5. **Kiểm thử kết nối có giới hạn** từ nguồn đại diện đã được cấp quyền.

### Vì sao scanner chỉ nhìn EXPOSE chưa đủ?

- Có thể báo “port 9090 exposed” dù runtime không publish và process không listen.
- Có thể bỏ qua “port 5005” vì EXPOSE không khai báo, dù process vẫn bật remote debugging.
- Có thể đánh dấu image “an toàn” trong CI rồi runtime khai báo **hostNetwork/NodePort/LoadBalancer**.
- Có thể chỉ thử IPv4, bỏ sót IPv6 hoặc mạng overlay/hybrid.
- Không quan sát được **TLS/authorization** chỉ từ port.

**Không cần quét Internet để chứng minh một image an toàn.** Phép đo phải bám theo **asset owner, lab/staging, nguồn mạng và điều kiện dừng**, đồng thời ưu tiên các API chỉ đọc để hạn chế tác động.

## 24. Tạo hợp đồng port cho image và runtime

Một **port contract** ghi rõ cổng nào **được khai báo trong image**, cổng nào **được phép listen**, cổng nào **được phép publish**, và ai là **caller** được chấp thuận. Điều này giúp tránh tình huống team image nghĩ platform đã hạn chế truy cập, trong khi platform nghĩ image chỉ có một port vì EXPOSE chỉ ghi 8080.

### Ví dụ hợp đồng máy đọc được (schema minh họa)

~~~yaml
workload: catalog-api
owner: catalog-platform
environment: production
image:
  allowed_exposed_ports:
    - "8080/tcp"
runtime:
  allowed_listeners:
    - "0.0.0.0:8080/tcp"
    - "127.0.0.1:9090/tcp"
  forbidden_ports:
    - "5005/tcp"
  forbid_host_network: true
  forbid_privileged: true
  forbid_host_port: true
  host_published_ports: []
network:
  ingress:
    - from: trusted-ingress-gateway
      protocol: tcp
      destination_port: 8080
  egress:
    - to: catalog-database
      protocol: tcp
      destination_port: 5432
    - to: approved-dns
      protocol: udp
      destination_port: 53
security:
  require_authenticated_api: true
  require_approved_tls_hops: true
~~~

Đây là **đề xuất mô tả ý định**, không phải Kubernetes NetworkPolicy, Docker Compose hoặc cú pháp thực thi của một sản phẩm. Từng trường phải được **chuyển thành admission checks, deployment validation, CNI/SG policies và application controls** tương ứng. Nếu hệ thống không dùng metrics 9090, hãy **tắt listener**, không để lại chỉ vì tài liệu từng nêu.

### Quy tắc phân loại port

| Nhóm | Cách quản lý |
|---|---|
| **REQUIRED** | Có owner, purpose, source/destination, protocol, TLS/auth và test |
| **INTERNAL_ONLY** | Không host-publish; chỉ peer được phê duyệt qua private network/policy |
| **LOCAL_ONLY** | Bind loopback đúng namespace và kiểm soát người có thể truy cập namespace |
| **TEMPORARY** | Có ticket, thời hạn hết quyền, người phê duyệt, audit |
| **FORBIDDEN** | Không listen/publish ở production; CI và runtime kiểm tra |
| **UNKNOWN** | Không tự động cho phép; điều tra trước khi triển khai |

**Port contract là chính sách ý định**, không phải bằng chứng đã thực thi. Nó chỉ đáng tin khi **image artifact và runtime topology thật được đối chiếu**.

## 25. Kiểm tra CI/CD và admission trước khi chạy

Một pipeline có thể kiểm tra các thay đổi port trong image và workload manifest:

~~~text
     Developer commits Dockerfile/manifests
                     |
            Build final image
                     |
       Inspect image Config.ExposedPorts
                     |
       Compare with approved port contract
                     |
       Scan app config/entrypoint for debug flags
                     |
         Validate Compose/K8s runtime spec
                     |
       Check hostPort / hostNetwork / Service types
                     |
          Policy review + security tests
                     |
             Deploy into staging
                     |
        Observe real listeners and reachability
                     |
           Promote with owner approval
~~~

### Kiểm tra nên tự động hóa

| Check | Nguy cơ được giảm |
|---|---|
| **Image Config.ExposedPorts allowlist** | Metadata mới đưa debug/management port vào image |
| **Entrypoint/runtime flags review** | Debug listener được bật dù không EXPOSE |
| **Final image digest validation** | Tag bị trỏ tới image khác so với artifact đã duyệt |
| **Docker/Compose published port diff** | Runtime mở thêm host port hoặc host bind rộng |
| **hostNetwork/hostPort deny policy** | Workload có đường lộ node ngoài thiết kế |
| **Service type and ingress audit** | NodePort/LoadBalancer/Ingress public xuất hiện ngoài change |
| **NetworkPolicy coverage** | Pod không bị cô lập hoặc có rule allow quá rộng |
| **Dual-stack coverage** | IPv6 bypass nếu chỉ kiểm tra IPv4 |
| **Runtime listener comparison** | Socket bất ngờ không được khai báo |
| **Authorized positive/negative tests** | Cả đường hợp lệ và đường trái quyền được kiểm tra |

### Vì sao static lint không đủ?

- EXPOSE có thể **thừa kế** từ final base image.
- Process có thể lắng nghe do **env, feature flag, plugin, sidecar hoặc remote agent** chỉ xuất hiện khi chạy.
- Helm/Kustomize hoặc deployment template có thể **biến đổi manifest** theo môi trường.
- Cloud LoadBalancer có thể mặc định tạo một đường public hoặc private tùy annotations/provider settings.
- Security policy có thể có **exception** không hiện rõ trong một file.
- CI không biết thực tế **DNS/routing/firewall của runtime** trừ khi có phép kiểm tra phù hợp.

**Chính sách tốt dùng cả build-time và runtime evidence**, đồng thời có người chịu trách nhiệm giải quyết sự khác biệt.

## 26. Giám sát và detection cho cổng ngoài ý muốn

Một số telemetry hữu ích gồm **image metadata, runtime socket inventory, orchestrator API, cloud network configuration, flow logs, host firewall logs và application access logs**. Chọn điểm quan sát phù hợp vì mạng container có nhiều namespace và lớp proxy.

| Nguồn | Quan sát được | Không tự chứng minh |
|---|---|---|
| **Image inspect** | EXPOSE metadata | Process đang listen hoặc dịch vụ public |
| **docker ps/port/inspect** | Published port mappings/network mode | App chấp nhận request hoặc client có quyền |
| **Container socket inventory** | Địa chỉ/protocol/port process đang listen | Reachable từ Internet |
| **Compose/Kubernetes spec** | Cấu hình mong muốn đã triển khai | CNI/iptables/eBPF/cloud routes vận hành đúng |
| **Cloud LB/SG/flow logs** | Đường và traffic được chấp thuận/chặn theo phạm vi | Token, tenant và business authorization |
| **Ingress/API gateway logs** | Request tới route/host, TLS, policy decision | Những bypass trực tiếp tới Pod/node |
| **Runtime/EDR/eBPF telemetry** | Tiến trình mở socket, network events theo khả năng | Không phải mọi sản phẩm đều có context nghiệp vụ |
| **Synthetic probes** | Một kết nối từ nguồn đại diện có hoạt động | Không đại diện mọi nguồn/region/IPv6 |

### Alert hữu ích

~~~text
ALERT: CONTAINER_UNAPPROVED_LISTENER
Workload: catalog-api
Environment: production
Image digest: [approved digest]
Container/Pod: [resource ID]
Declared exposed ports: 8080/tcp
Observed listener: 0.0.0.0:5005/tcp
Host/Service publish: [not observed / observed / unknown]
Caller reachability: [not tested]
Owner: catalog-platform
Severity: [based on network exposure and debug capability]
Next action: review runtime debug flags and network policies
~~~

Alert này phân biệt **observed listener** với **verified reachability**: không nên kết luận 5005 “đã lộ Internet” khi mới chỉ thấy socket. Nhưng debug listener ngoài ý muốn trong production vẫn cần xử lý theo rủi ro dù chưa có bằng chứng truy cập ngoài.

### Cần theo dõi thay đổi, không chỉ một snapshot

- Image digest thay đổi → EXPOSE metadata có đổi?
- Deployment được sửa → có thêm **hostPort, hostNetwork, port publishing**?
- Service/Ingress mới → endpoint nào xuất hiện bên ngoài?
- Runtime process mở socket mới sau deploy/feature toggle?
- Cloud security group/LB listener hoặc NetworkPolicy bị sửa?
- IPv6/dual-stack được bật → policy được cập nhật tương ứng chưa?
- Port từ **debug/temporary** có hết hạn theo ticket chưa?

## 27. Quy trình xử lý khi phát hiện port đáng ngờ

### Giai đoạn 1 — Thu bằng chứng không phá hoại

1. Xác định **cluster/host, namespace/network, container, image digest, version và owner**.
2. Xem **Config.ExposedPorts** và phân biệt nó với **running listeners**.
3. Kiểm tra process thực sự bind **IP:port/protocol** nào, ở network namespace nào.
4. Đọc **host publish mapping**, Service/Ingress/NodePort/LoadBalancer, hostNetwork và network policy.
5. Xác định **source networks** có thể truy cập, qua route/firewall/LB/VPN nào.
6. Xem **change history, CI artifact, access logs** và sự kiện mở listener.

### Giai đoạn 2 — Phân loại mức độ ảnh hưởng

| Tình huống | Nhận định ban đầu |
|---|---|
| EXPOSE 5005 nhưng không có listener hoặc publish | Metadata drift; vẫn cần gỡ cấu hình thừa và kiểm tra -P |
| Listen 127.0.0.1:5005 trong Pod | Chỉ loopback Pod trực tiếp, nhưng sidecar cùng Pod có thể truy cập |
| Listen 0.0.0.0:5005 ở Pod | Có bề mặt truy cập từ network peer nếu policy cho phép |
| Docker host publish 0.0.0.0:5005 | Có khả năng reachable từ host interfaces; kiểm tra cloud FW/route |
| Kubernetes Service/Ingress trỏ tới debug port | Đường truy cập mới có thể làm lộ chức năng quản trị |
| hostNetwork bật không được phê duyệt | Listener có thể là node-level exposure |
| EXPOSE không có nhưng Service vẫn route được | Metadata không thực thi bảo mật, cần fix runtime/policy |

### Giai đoạn 3 — Kiềm chế theo đúng lớp

- Nếu chỉ metadata EXPOSE thừa, sửa image build, duyệt **final image config** và ngăn **-P** không kiểm soát.
- Nếu process không cần thiết đang listen, **tắt runtime feature/debug agent** ở cấu hình ứng dụng, không chỉ xóa EXPOSE.
- Nếu cổng bị publish sai, sửa **ports/Service/Ingress/NodePort/hostPort/LB** có rollback.
- Nếu có peer ngoài quyền, cập nhật **network segmentation, CNI NetworkPolicy, SG/host firewall hoặc proxy authorization**.
- Nếu nghi ngờ đã bị truy cập, kích hoạt incident response, bảo toàn log/bằng chứng và đánh giá khả năng lộ dữ liệu.
- Không áp deny-all ở production mà chưa biết dependencies hợp lệ; canary/rollout có stop conditions khi thay network.

### Giai đoạn 4 — Xác minh sau sửa

1. Không còn **unapproved listener** hoặc đã cô lập đúng với ngoại lệ được duyệt.
2. Port không được phép **không còn publish/reachable** từ các nguồn trong phạm vi test.
3. API chính vẫn hoạt động qua gateway/TLS và client có quyền.
4. Client không có quyền vẫn **bị từ chối** ở network hoặc application phù hợp.
5. Health, metrics collection, DNS, egress và service-to-service traffic vẫn đáp ứng SLO.
6. CI/admission/monitoring ngăn lỗi lặp lại.

## 28. Case study 1: dùng -P làm publish cổng debug

**Bối cảnh giả định:** Một image Java cũ dùng để phát triển có metadata:

~~~dockerfile
EXPOSE 8080/tcp
EXPOSE 5005/tcp
~~~

Nhóm vận hành cho rằng EXPOSE không tự mở cổng nên không quan tâm, sau đó dùng:

~~~bash
# Chỉ minh họa sai sót; KHÔNG chạy image chứa remote debugger
# trên host production hoặc host public.
docker run -P legacy-api:lab
~~~

Vì **-P** publish những port exposed, Docker có thể cấp **host ports** cho cả 8080 và 5005, tùy runtime và điều kiện mạng. Nếu JVM đang bật remote debugging và bind có thể được truy cập, đây là một bề mặt có rủi ro lớn.

### Chứng cứ cần tìm

- Final image **ExposedPorts** gồm cổng nào?
- Remote debugging có **thực sự bật** và listen IP:port nào?
- Docker runtime publish host IP:port nào cho 5005?
- Firewall/SG/routing có cho nguồn ngoài quyền truy cập tới đó không?
- Có dấu hiệu kết nối/debug session không được phép không?

### Phương án xử lý

1. Ngừng dùng **-P** trong deployment chưa kiểm soát; publish tường minh **chỉ cổng cần thiết**.
2. Xóa **debug EXPOSE** khỏi image production và đảm bảo không kế thừa metadata ngoài ý định.
3. **Tắt remote debugger** ở production bằng cấu hình runtime được kiểm tra sau deploy.
4. Tách profile dev/staging khỏi production và đặt runtime network policy.
5. Xác minh từ đúng nguồn rằng debug port bị từ chối; vẫn giữ API hoạt động.

**Bài học:** EXPOSE chỉ là metadata, nhưng vẫn ảnh hưởng **những tiện ích tự động dựa vào metadata**, điển hình là **-P**.

## 29. Case study 2: không có EXPOSE nhưng Kubernetes vẫn làm lộ API

**Bối cảnh giả định:** Nhóm build một image Go không có dòng **EXPOSE**. Ứng dụng listen **0.0.0.0:8080**. Trong Kubernetes, một Service kiểu **LoadBalancer** trỏ tới TCP/8080 và provider cấp địa chỉ public theo cấu hình.

~~~text
Dockerfile:          không khai báo EXPOSE
Application:         listen 0.0.0.0:8080
Pod:                 Pod IP:8080
Service:             type LoadBalancer
Service targetPort:  8080
Cloud:               public LB theo cấu hình giả định
External access:     phụ thuộc cloud firewall/routes
~~~

### Lỗi trong suy luận

Người đánh giá chỉ xem Dockerfile, thấy **không có EXPOSE** và kết luận image không thể reachable từ Internet. Nhưng **Service/LoadBalancer** tạo một đường mới tới **process đang listen**, độc lập với metadata.

### Cách sửa

- Xác định API này **phải public hay private**.
- Nếu chỉ dành cho nội bộ, dùng **Service/Ingress/LB internal** theo provider và network policy giới hạn nguồn.
- Nếu public thật, áp **TLS, gateway, authentication, WAF/rate limit** và cloud network controls.
- Duyệt Service annotations, selectors, targetPorts, namespace và owner.
- Kiểm tra **người dùng hợp lệ thành công** và **nguồn không được phép bị từ chối**.

**Bài học:** Nguy cơ truy cập phải kiểm tra **runtime/orchestration và cloud boundary**, không thể suy từ số dòng EXPOSE.

## 30. Case study 3: metrics chỉ được dùng nội bộ nhưng Pod khác vẫn đọc được

**Bối cảnh giả định:** Một microservice expose API TCP/8080 và metrics TCP/9090. Không host publish và không có Ingress cho metrics. Kỹ sư kết luận metrics đã private. Nhưng ứng dụng bind metrics ở **0.0.0.0:9090**, trong khi Pod khác trong cùng cluster có thể truy cập Pod IP do **không có NetworkPolicy ingress isolation**.

### Đường truy cập thực

~~~text
Pod A:
  10.244.1.20:8080   API
  10.244.1.20:9090   Metrics

Pod B trong cluster:
  Có route tới 10.244.1.20:9090

Docker image EXPOSE: 8080/tcp
Service public: chỉ API

Metrics vẫn có thể reachable từ Pod B nếu network policy cho phép.
~~~

### Khắc phục theo nhu cầu

1. Nếu collector **cùng Pod**, cân nhắc bind metrics ở **127.0.0.1:9090** trong shared Pod network namespace.
2. Nếu monitoring collector nằm ở **Pod khác**, giữ metrics listener trên Pod IP cần thiết nhưng áp **NetworkPolicy chỉ cho collector**, kết hợp auth/mTLS nếu phù hợp.
3. Kiểm tra chính sách do **CNI thực thi**, không chỉ sự tồn tại của manifest.
4. Không ghi token, key hoặc dữ liệu nhạy cảm vào metrics labels/nội dung.
5. Kiểm thử cho phép collector hợp lệ và từ chối một Pod không được phép.

**Bài học:** “Không public ra Internet” khác “không reachable từ workload không đáng tin trong cluster”. Phạm vi cần bảo vệ là **đúng trust boundary**, không chỉ đường host publish.

## 31. Thực hành có kiểm soát: kiểm tra EXPOSE, publish và listener

Mục tiêu bài lab là **quan sát sự khác nhau giữa metadata và cấu hình runtime**, không kiểm thử xâm nhập hoặc scan những hệ thống không thuộc quyền. Chỉ thực hiện trên **máy thí nghiệm hoặc môi trường staging được cấp phép**, không dùng image chứa debug console, secret hoặc dữ liệu thật.

### 31.1. Chuẩn bị

- Máy có Docker Engine/Desktop được phép sử dụng, Docker CLI và curl phù hợp.
- Không gian port host riêng, chẳng hạn **127.0.0.1:18080**, bảo đảm chưa bị ứng dụng khác dùng.
- Một image HTTP thử nghiệm được tổ chức phê duyệt, ví dụ **nginx:alpine** trong lab. Với pipeline thật, phải **pin digest**, kiểm tra provenance và quét lỗ hổng theo chuẩn tổ chức; tag ở đây chỉ để minh họa.
- Quyền tạo/xóa **container lab** và người phụ trách kiểm chứng.
- Không thay Docker daemon network defaults, firewall hệ thống hay cloud SG chỉ để làm bài.

### 31.2. Đọc metadata trước khi chạy

~~~bash
docker image inspect nginx:alpine \
  --format '{{json .Config.ExposedPorts}}'
~~~

Kỳ vọng tùy phiên bản image: có thể thấy **80/tcp** là declared port. **Không cần container đang chạy** để đọc metadata; nếu image chưa có local hoặc tổ chức chặn pull, dùng artifact image lab sẵn có.

### 31.3. Chạy thử với loopback host publish

~~~bash
# Chỉ chạy trên host lab, dùng host port đã được phép.
docker run --rm -d --name port-lab \
  -p 127.0.0.1:18080:80 \
  nginx:alpine

docker ps --format 'table {{.Names}}\t{{.Ports}}'
docker port port-lab

curl --fail --show-error --silent --head \
  http://127.0.0.1:18080/
~~~

**Giải thích:** Trong bài lab, HTTP cleartext ở **localhost** là đủ để quan sát host mapping; **không phải mẫu triển khai public production**. Một phản hồi HTTP thành công cho thấy kết nối từ **host loopback** hoạt động, **không chứng minh** cổng không thể reachable từ mọi mạng khác hoặc chứng minh quyền ứng dụng.

### 31.4. Đọc mapping runtime

~~~bash
docker inspect port-lab \
  --format '{{json .NetworkSettings.Ports}}'
~~~

Đối chiếu kết quả với **image Config.ExposedPorts**. Hai trường trả lời câu hỏi khác nhau:

- Image: “Những port nào được image **khai báo**?”
- Runtime: “Những port được container **publish/map** đến host theo cấu hình quan sát được?”

### 31.5. Dọn tài nguyên lab

~~~bash
docker rm -f port-lab
~~~

Chỉ chạy lệnh xóa với **container lab do mình vừa tạo**. Nếu dùng container khác hoặc môi trường có dữ liệu, không thay thế tên theo phỏng đoán.

### 31.6. Bài phân tích không cần tạo thêm traffic

Giả sử image B khai báo:

~~~text
EXPOSE 8080/tcp
EXPOSE 9090/tcp

Actual listeners:
  0.0.0.0:8080
  0.0.0.0:9090

Desired:
  Gateway được gọi API 8080
  Collector được gọi metrics 9090
  Guest workload không được gọi 9090
~~~

Hãy trả lời:

1. Nếu chạy không có **-p/-P**, image B có tự publish port ra host không?
2. Nếu chạy **-P**, cần kiểm tra những host mappings nào?
3. Nếu peer cùng Docker network truy cập 9090, **xóa EXPOSE 9090** có đủ chặn không?
4. Nếu metrics chỉ cần trong cùng Pod, có thể thay **listen address** thế nào?
5. Nếu collector ở Pod khác, cần thiết kế **NetworkPolicy/identity** nào?
6. Khi chính sách chặn khách lạ hoạt động, bằng chứng nào chứng minh **collector hợp lệ vẫn lấy metrics**?

### 31.7. Đọc metadata Kubernetes (chỉ khi có cluster lab)

~~~bash
# Chỉ dùng context/namespace thuộc quyền của mình.
kubectl -n app-prod get deployment catalog-api
kubectl -n app-prod get svc
kubectl -n app-prod get ingress
kubectl -n app-prod get networkpolicy
~~~

Không phải cluster nào cũng sử dụng resource **Ingress**; có thể dùng Gateway API hoặc nền tảng khác. Những lệnh **get** chỉ cho biết tài nguyên tại thời điểm quan sát; chúng **không bảo đảm NetworkPolicy được CNI enforce**, và không thay thế việc kiểm tra LB public/private, node firewall hoặc kết nối từ những nguồn đã được cấp quyền.

### Mẫu ghi nhận

~~~text
Lab ID:                    CONTAINER-PORT-001
Timestamp/timezone:        [value]
Host / cluster / namespace:[approved environment]
Image reference + digest:  [immutable version]
Image ExposedPorts:        [port/protocol list]
Observed listeners:       [IP:port/protocol, source]
Runtime mode:             [bridge/host/pod/other]
Host published mapping:   [host IP:port -> container IP:port]
Service/Ingress mapping:  [if applicable]
Network controls:         [SG/host FW/NetworkPolicy]
Approved caller:          [principal/zone]
Unapproved caller:        [principal/zone]
Expected access:          [ALLOW and DENY cases]
Observed access:          [evidence]
TLS/auth status:          [verified or not tested]
Result:                   [PASS / FAIL / INCONCLUSIVE]
Owner / next action:      [responsible team]
~~~

## 32. Ma trận kiểm thử giới hạn exposed ports

Ma trận nên được thực hiện theo **môi trường và phạm vi có phép**, ưu tiên static analysis, cấu hình runtime và **kết nối thử ít tác động**. Không cần quét toàn bộ host hoặc Internet để kiểm tra những điều được thiết kế bằng policy.

| Test ID | Điều kiện cần kiểm | Kết quả mong đợi |
|---|---|---|
| **PORT-01** | Image cuối chỉ khai báo API 8080/tcp theo hợp đồng | ExposedPorts không chứa cổng ngoài danh mục |
| **PORT-02** | Final base image có EXPOSE thừa | CI phát hiện metadata kế thừa và owner xử lý |
| **PORT-03** | Image không có EXPOSE nhưng process vẫn listen 8080 | Inventory phát hiện listener, không coi không EXPOSE là deny |
| **PORT-04** | Image EXPOSE 9090 nhưng không có process listen | Phân loại metadata drift, không gắn nhãn service reachable |
| **PORT-05** | Docker chạy không -p/-P trên bridge | Không tự host-publish bởi EXPOSE |
| **PORT-06** | Docker -p publish cổng không có EXPOSE | Mapping vẫn được tạo; security policy kiểm tra |
| **PORT-07** | Docker -P với image có 8080 và 5005 | CI/runbook phát hiện nguy cơ publish cả debug metadata |
| **PORT-08** | Publish host loopback 127.0.0.1 | Đúng host binding được phê duyệt và có kiểm tra path |
| **PORT-09** | Runtime publish trên all interfaces ngoài ý định | Policy phát hiện và deployment bị từ chối/sửa |
| **PORT-10** | App chỉ bind container loopback, có host mapping bridge | Phân loại đúng lỗi reachability/listen address |
| **PORT-11** | App bind 0.0.0.0 nhưng không host publish | Peer isolation kiểm soát access; không tự kết luận public |
| **PORT-12** | Compose expose nhưng không có ports | Không tạo host publish chỉ bởi expose |
| **PORT-13** | Peer cùng Docker network gọi port không trong expose | Kết quả cho thấy expose không phải firewall allowlist |
| **PORT-14** | Container được bật host networking | Phát hiện node-level port exposure và yêu cầu review |
| **PORT-15** | hostPort/privileged bị cấm với API thường | Admission policy chặn hoặc có ngoại lệ có hạn |
| **PORT-16** | Kubernetes Pod có containerPort | Không tự tạo NodePort/LB hoặc public endpoint |
| **PORT-17** | Kubernetes Service targetPort numeric, Pod không khai containerPort | Không hiểu nhầm metadata thiếu sẽ chặn traffic |
| **PORT-18** | Service ClusterIP thuộc internal traffic | Chỉ caller theo network policy/mTLS được phép |
| **PORT-19** | Service loại NodePort xuất hiện ngoài kế hoạch | Detect cổng node, firewall và owner review |
| **PORT-20** | Service LoadBalancer được tạo | Xác định public/private thật theo provider/config |
| **PORT-21** | Ingress/Gateway public route vào ClusterIP | Đánh giá cả edge và Pod trust boundary |
| **PORT-22** | NetworkPolicy chỉ cho trusted gateway vào TCP/8080 | Gateway ALLOW, Pod khác DENY đúng CNI semantics |
| **PORT-23** | Có NetworkPolicy khác cũng chọn Pod | Xem hợp allow rules, không ngộ nhận policy ghi đè |
| **PORT-24** | Default-deny egress được bật | DNS/PKI/DB/logging hợp lệ vẫn được permit có kiểm soát |
| **PORT-25** | Metrics 9090 chỉ phục vụ collector | Caller không được phép không lấy được metrics |
| **PORT-26** | Remote debug 5005 trong prod | Không listen/publish, runtime config không bật debug |
| **PORT-27** | Health endpoint được triển khai | Readiness/health đúng, không lộ internal diagnostics |
| **PORT-28** | Chạy qua IPv4 và IPv6 | Chính sách exposure tương đương theo address family |
| **PORT-29** | API TLS termination ở gateway | Backend hop được bảo vệ theo policy, auth không bypass |
| **PORT-30** | Image digest cập nhật sau build | Artifact được deploy khớp image đã kiểm tra |
| **PORT-31** | Compose/Helm manifest thay đổi port | CI tạo diff, owner phê duyệt, có rollback |
| **PORT-32** | NetworkPolicy manifest tồn tại nhưng CNI không enforce | Test phát hiện blind spot, không đánh dấu PASS giả |
| **PORT-33** | API chạy nhưng client thiếu quyền | Application từ chối dù network kết nối được |
| **PORT-34** | Container bị xâm nhập giả định trong lab | Egress policy hạn chế destination không được duyệt |
| **PORT-35** | Một node/region dự phòng có cấu hình khác | Phát hiện drift và bảo đảm ALLOW/DENY nhất quán |
| **PORT-36** | Sau vá lỗi port exposure | Không còn đường ngoài quyền, chức năng hợp lệ vẫn đáp ứng SLO |

**PASS** phải ghi rõ **nguồn đo, đích, protocol/port, image digest, network namespace, runtime policy và thời điểm**. **INCONCLUSIVE** khi chưa chứng minh được cổng reachable từ đâu, chưa rõ CNI có enforce hay không hoặc không có quyền kiểm tra đường công khai/đường dự phòng.

## 33. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| “EXPOSE tự mở port cho Internet” | EXPOSE là metadata | Kiểm tra -p/-P, Service/LB, route/firewall |
| “Xóa EXPOSE là đóng port” | Process vẫn có thể listen | Tắt listener hoặc chặn bằng runtime/network policy |
| “-p chỉ áp dụng với cổng EXPOSE” | Docker cho phép publish cổng được chỉ định không có EXPOSE | Audit runtime mapping độc lập |
| “-P không liên quan EXPOSE” | -P dựa vào exposed ports | Tránh -P thiếu kiểm soát |
| “EXPOSE 53 nghĩa cả TCP và UDP” | Không ghi protocol thường mặc định TCP | Khai báo từng protocol cần thiết |
| “Docker ps hiện 8080/tcp là public” | Có thể chỉ là declared port | Tìm host mapping và kiểm tra path |
| “Bind 0.0.0.0 trong container nghĩa public Internet” | Chỉ là container interfaces | Xem host publish, route, SG, network policy |
| “Bind 127.0.0.1 của container cho host truy cập bằng -p” | Loopback thuộc network namespace container | Hiểu đúng namespace và interface |
| “Docker host loopback publish bảo đảm an toàn tuyệt đối” | Có thể có proxy/forwarding/config/version khác | Xem effective exposure và host firewall |
| “Compose expose là firewall giữa các service” | Peer trên cùng network có thể gọi listener khác | Phân đoạn network và auth |
| “Không publish nghĩa mọi container khác bị chặn” | Peer có route trong mạng container có thể truy cập | Network isolation/microsegmentation |
| “Một Pod là một container” | Pod có thể chứa sidecar, chia sẻ network namespace | Xem tất cả listener của Pod |
| “Pod containerPort là cổng public” | Chỉ metadata | Xem Service/Ingress/hostPort/hostNetwork |
| “Không khai containerPort là không thể gọi Pod” | Listener và network có thể vẫn cho phép | Policy/route quyết định reachability |
| “ClusterIP chỉ cho đúng namespace gọi” | Không phải cơ chế phân quyền namespace mặc định | NetworkPolicy và identity |
| “Một NetworkPolicy ALLOW mới sẽ ghi đè policy cũ” | Cho phép thường là hợp các policy áp dụng | Xét effective set và test |
| “Có NetworkPolicy YAML là chắc chắn enforced” | Phụ thuộc CNI hỗ trợ và path | Xác minh trên cluster thật |
| “Service LoadBalancer luôn private” | Provider/config có thể tạo public LB | Chỉ rõ internal/public và kiểm tra |
| “hostNetwork không ảnh hưởng cổng” | Pod dùng node network namespace | Node-level exposure và host firewall |
| “Metrics không có Ingress là an toàn” | Peer trong cluster có thể tới Pod IP | Giới hạn collector/identity |
| “Một API port là đủ để cấp mọi quyền” | Transport reachability không xác thực user | TLS/mTLS, IAM, object authorization |
| “TCP open chứng minh HTTP/gRPC thành công” | TLS hoặc application có thể lỗi | End-to-end authorized tests |
| “Chỉ cần chặn ingress, không cần egress” | Process có thể kết nối ra ngoài | Egress allowlist/policy theo threat model |
| “Quét EXPOSE là biết toàn bộ attack surface” | Listener có thể không khai báo hoặc xuất hiện theo runtime | Kết hợp artifact + socket + network path |
| “IPv4 policy tự bảo vệ IPv6” | Dual-stack có đường và rule riêng | Kiểm thử cả IPv4/IPv6 |
| “Giới hạn port thay thế firewall/WAF” | Không hiểu ứng dụng, token, DDoS hay identity | Defense-in-depth |
| “Chỉ cần sửa Dockerfile rồi incident kết thúc” | Deployment cũ hoặc LB/Service có thể vẫn tồn tại | Readback runtime và kiểm thử ALLOW/DENY |

## 34. Câu hỏi tự kiểm tra

1. Giải thích vì sao **EXPOSE 8080** không tự làm một TCP service reachable từ host hoặc Internet.
2. Phân biệt **declared, listening, published, reachable và authorized** bằng một ví dụ.
3. Một image không có EXPOSE nhưng chạy **docker run -p 18080:8080** có thể reachable không? Cần thêm điều kiện gì?
4. **docker run -P** khác **-p** thế nào, và vì sao metadata thừa kế từ base image quan trọng?
5. Dockerfile **EXPOSE 53** mặc định mô tả protocol nào? Làm sao khai báo UDP/53?
6. Vì sao **Docker ps** hiện cổng không đủ để kết luận port public?
7. Khi process trong container chỉ bind **127.0.0.1:8080**, mapping bridge từ host tới container IP:8080 có thể gặp vấn đề gì?
8. **127.0.0.1** của container có giống host localhost không? Khi nào namespace được chia sẻ?
9. Với Compose, **expose** và **ports** tạo những hành vi khác nhau ra sao?
10. Nếu hai service cùng user-defined Docker network, xóa **expose 9090** có chặn peer gọi listener 9090 không?
11. Vì sao việc tách network public gateway, backend và DB có lợi hơn nối mọi container chung mạng?
12. Dùng **host network mode** thay đổi giả định gì về việc publish cổng?
13. Vì sao nên hạn chế privileged/capabilities dù chỉ một port API được mở?
14. Một Pod gồm app và sidecar có chia sẻ localhost và không gian port không?
15. Metadata **containerPort** ở Kubernetes có tự tạo Service hoặc NodePort không?
16. Service **ClusterIP, NodePort và LoadBalancer** khác nhau thế nào về đường truy cập?
17. Vì sao **ClusterIP** chưa đủ bảo vệ API khỏi Pod không đáng tin trong cùng cluster?
18. Một Service targetPort numeric có thể route tới Pod dù Pod không khai containerPort không?
19. Một **Ingress** public có thể route tới Service ClusterIP không? Hệ quả với security boundary?
20. Một Kubernetes **NetworkPolicy** chỉ cho gateway truy cập có cần CNI enforce không? Làm thế nào kiểm chứng?
21. Trong NetworkPolicy **from** cùng một phần tử có namespaceSelector và podSelector khác gì việc dùng hai phần tử riêng?
22. Vì sao **hai NetworkPolicy cùng chọn một Pod** không tự có quan hệ deny-overrides-allow?
23. Nếu default-deny egress được bật, những dependency mạng nào cần inventory trước?
24. Khi metrics chỉ cần sidecar cùng Pod, nên cân nhắc bind address và trust boundary ra sao?
25. Vì sao việc bỏ cổng debug trong **EXPOSE** chưa đủ nếu JVM vẫn bật remote debugger?
26. Image scanning và runtime listener inspection có những blind spot khác nhau nào?
27. Một NodePort hoặc hostPort được thêm trong deployment có thể làm thay đổi network exposure như thế nào?
28. Nếu LB trả public IP trong khi image không EXPOSE, cần đánh giá những resource nào?
29. Khi IPv6 được bật, tại sao một kiểm thử chỉ từ IPv4 có thể bỏ sót đường truy cập ngoài quyền?
30. Những bằng chứng tối thiểu nào giúp kết luận một port đã bị chặn từ **nguồn không được phép** nhưng vẫn phục vụ **collector hoặc gateway hợp lệ**?
31. Vì sao giảm số lượng port không thay thế authentication và object-level authorization?
32. Thiết kế một **port contract** cho API 8080, metrics 9090 và debug 5005 trong môi trường production.
33. Hãy nêu runbook xử lý khi phát hiện container mới listen **0.0.0.0:5005** sau deploy.
34. Tại sao phải ghi **image digest**, không chỉ image tag, khi xác minh thay đổi EXPOSE?

## 35. Ghi nhớ trọng tâm

**EXPOSE là khai báo metadata của image, không phải firewall, không tự publish port và không ngăn một ứng dụng listen cổng khác.** Hãy phân biệt năm trạng thái **declared → listening → published → reachable → authorized**. Với Docker, **-p** có thể publish bất kỳ container port được chọn dù không EXPOSE, trong khi **-P** dựa vào exposed ports và có thể publish cả cổng debug/metrics ngoài ý định. Compose **expose** cũng không phải allowlist giữa các container; **ports** mới là cấu hình yêu cầu host publishing.

Trong Kubernetes, **containerPort** chỉ là khai báo. Đường truy cập thật phụ thuộc **Pod listener, Service type, Ingress/Gateway, hostPort/hostNetwork, CNI NetworkPolicy, cloud LB, firewall và identity policy**. Pod có thể chứa nhiều container dùng chung network namespace; một port chỉ bind localhost có thể truy cập từ sidecar cùng Pod nhưng không tự reachable qua Pod IP. **ClusterIP không phải phân quyền caller**; mTLS, token và object authorization vẫn cần thiết.

Để giới hạn bề mặt tấn công, hãy **không khởi động debug/admin listeners không cần thiết**, khai báo image ports tối thiểu, tách runtime profiles, hạn chế host binding và network membership, áp **ingress/egress policy theo caller**, kiểm tra cả IPv4/IPv6 và cloud boundaries. Quy trình đáng tin phải đối chiếu **final image digest/ExposedPorts, runtime mappings, actual listening sockets, Service/Ingress/NetworkPolicy và phép kiểm thử ALLOW/DENY có quyền**, có CI/CD guardrails, telemetry, runbook và rollback. **Một image không EXPOSE không mặc nhiên an toàn; một port không public cũng không mặc nhiên an toàn với mọi peer trong mạng nội bộ.**
