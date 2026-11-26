# Pod, container và vòng đời một bản sao ứng dụng

## Mục tiêu bài học

Trong Kubernetes, một bản sao ứng dụng không chỉ là một tiến trình Java được khởi động. Tiến trình chạy bên trong container, container nằm trong Pod, còn Pod được tạo, theo dõi và thay thế bởi các controller như Deployment. Hiểu rõ các lớp này giúp bạn đọc đúng trạng thái triển khai, thiết kế probe phù hợp và giải thích vì sao một ứng dụng Spring Boot có thể “đang chạy” nhưng chưa sẵn sàng nhận traffic.

Bài thuộc chương **Nền tảng Kubernetes** của module **SPRING_CLOUD_KUBERNETES**. Module học cách tích hợp ứng dụng Spring với Kubernetes qua DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer và Configuration Watcher; đồng thời thực hành RBAC, cập nhật cấu hình, theo dõi sức khỏe Pod và lựa chọn tính năng Spring Cloud Kubernetes thực sự cần cho triển khai.

Sau bài này, bạn có thể:

- Phân biệt container, Pod, replica và Deployment.
- Mô tả vòng đời của một Pod từ lúc được lập lịch đến khi kết thúc.
- Hiểu sự khác nhau giữa trạng thái process, container, Pod và Ready condition.
- Thiết kế startup, readiness và liveness probe cho ứng dụng Spring Boot.
- Giải thích lý do một bản sao được tạo mới, bị loại khỏi Service hoặc bị restart.
- Chuẩn bị nền tảng để dùng ConfigMap, Secret, discovery và load balancing đúng cách.

## 1. Từ một process đến một replica

Khi chạy ứng dụng Spring Boot trên máy cá nhân, ta thường hình dung một process Java lắng nghe ở cổng 8080. Trong Kubernetes, cùng ứng dụng đó có nhiều lớp:

    process Java
        → container
        → Pod
        → Deployment replica
        → Service và các client gọi đến

Mỗi lớp có trách nhiệm khác nhau:

| Khái niệm | Ý nghĩa | Câu hỏi cần trả lời |
| --- | --- | --- |
| Process | Tiến trình đang thực thi trong container | JVM còn sống và có lắng nghe cổng không? |
| Container | Đơn vị chạy image với filesystem, environment và resource riêng | Container khởi động bằng lệnh nào và kết thúc với mã nào? |
| Pod | Đơn vị nhỏ nhất Kubernetes lập lịch, chứa một hoặc nhiều container cùng mạng và vòng đời | Các container nào cần chia sẻ địa chỉ mạng hoặc volume? |
| Replica | Một bản sao Pod mong muốn của workload | Hệ thống cần bao nhiêu Pod cùng phục vụ? |
| Deployment | Controller quản lý ReplicaSet và quá trình rollout | Khi image đổi hoặc Pod lỗi, cần tạo thay thế thế nào? |
| Service | Điểm truy cập ổn định đến các Pod phù hợp selector | Pod nào được nhận traffic? |

Nói “ứng dụng có ba replica” thường có nghĩa Deployment duy trì ba Pod tương đương. Nó không có nghĩa một Pod chứa ba container, cũng không có nghĩa một container có ba process Java.

## 2. Container làm gì?

Container được tạo từ image và chạy một command hoặc entrypoint. Image chứa artifact ứng dụng, Java runtime hoặc lớp nền cần thiết. Khi container khởi động, Kubernetes runtime tạo môi trường chạy theo Pod spec:

- filesystem từ image và các volume được mount;
- biến môi trường;
- cổng và network namespace của Pod;
- giới hạn hoặc yêu cầu tài nguyên;
- danh tính ServiceAccount nếu được cấu hình;
- command và argument;
- các hook hoặc probe được khai báo.

Container không phải máy ảo đầy đủ. Nó dùng kernel của node thông qua container runtime và bị giới hạn bởi namespace, cgroup cùng các chính sách bảo mật. Vì vậy, một container không nên giả định nó có quyền quản trị node, truy cập filesystem của container khác hoặc giữ địa chỉ IP cố định.

### 2.1. Process chính quyết định trạng thái container

Container thường được xem là đang chạy khi process chính còn sống. Nếu process chính thoát, container kết thúc. Một ứng dụng có thể trả về mã 0 khi kết thúc bình thường hoặc mã khác 0 khi gặp lỗi; Kubernetes và restart policy sẽ dùng thông tin đó cùng các điều kiện khác để quyết định bước tiếp theo.

Với ứng dụng Spring Boot, process chính thường là JVM. Nếu JVM khởi động xong nhưng thread xử lý bị kẹt, container vẫn có thể được xem là đang chạy. Đây là lý do trạng thái “Running” chưa đủ để kết luận ứng dụng có thể phục vụ request.

Command minh họa:

    java -jar order-service.jar

Nếu cần dùng biến môi trường hoặc tham số, hãy bảo đảm command trong image và command trong Pod spec ghép với nhau đúng. Một lỗi nhỏ ở entrypoint có thể làm container thoát ngay trước khi Spring Boot đọc được cấu hình.

### 2.2. Không lưu dữ liệu lâu dài trong filesystem container

Filesystem ghi trong lớp writable của container thường gắn với vòng đời container. Khi container bị thay thế, dữ liệu đó có thể mất. Dữ liệu nghiệp vụ cần lưu trữ phải đi qua database, object storage, persistent volume hoặc hệ thống phù hợp.

Log ứng dụng cũng nên được ghi ra standard output và standard error để nền tảng thu thập. Không nên chỉ ghi log vào một file bên trong container rồi giả định file đó tồn tại sau rollout.

## 3. Pod là gì?

Pod là đơn vị Kubernetes lập lịch và quản lý vòng đời. Một Pod có thể chứa một container ứng dụng hoặc nhiều container phối hợp chặt chẽ. Các container trong cùng Pod:

- chia sẻ network namespace và thường dùng cùng địa chỉ IP của Pod;
- có thể giao tiếp qua localhost;
- có thể dùng volume chung nếu volume được khai báo;
- được lập lịch trên cùng một node;
- cùng chịu ảnh hưởng khi Pod bị thay thế.

Một ứng dụng Spring Boot thông thường có thể bắt đầu với một container trong một Pod. Sidecar chỉ nên được thêm khi có yêu cầu rõ, chẳng hạn proxy hoặc agent cần cùng vòng đời và cùng network namespace.

### 3.1. Pod không phải là một VM nhỏ

Pod không cung cấp một máy độc lập có IP bền vững. Pod có thể bị xóa và tạo lại với tên, UID và IP khác. Một Service hoặc cơ chế discovery là lớp tạo điểm truy cập ổn định hơn cho client.

Pod cũng không nên được xem là nơi cần sửa trực tiếp bằng tay. Pod do controller quản lý sẽ được controller tạo lại từ template. Thay đổi tạm thời bên trong một Pod không phải một thay đổi triển khai có thể truy vết.

### 3.2. Các container trong cùng Pod

Nếu Pod có sidecar, trạng thái của Pod còn phụ thuộc vào cách các container được khởi động và kết thúc. Cần biết:

- container nào là ứng dụng chính;
- container nào cung cấp proxy, logging hoặc agent;
- container nào cần volume chung;
- probe áp dụng cho container nào;
- khi sidecar lỗi, ứng dụng có được phép tiếp tục nhận traffic không.

Không thêm sidecar chỉ để “đủ chuẩn Kubernetes”. Mỗi container tăng resource, log, quyền và số đường lỗi cần theo dõi.

## 4. Replica và controller

### 4.1. Desired state và observed state

Kubernetes hoạt động theo mô hình desired state. Manifest mô tả trạng thái mong muốn, ví dụ Deployment cần ba replica. Controller liên tục quan sát trạng thái hiện tại và cố đưa nó về trạng thái mong muốn.

    desired replicas = 3
        ↓
    controller tạo hoặc giữ ReplicaSet
        ↓
    ReplicaSet tạo Pod
        ↓
    scheduler chọn node
        ↓
    kubelet tạo container
        ↓
    Pod vượt qua điều kiện sẵn sàng

Nếu một Pod bị node lỗi hoặc bị xóa, ReplicaSet có thể tạo Pod thay thế. Bản sao mới không kế thừa filesystem tạm thời, IP hoặc process của Pod cũ.

### 4.2. Deployment không trực tiếp chạy process

Deployment quản lý ReplicaSet. ReplicaSet quản lý số lượng Pod. Kubelet trên node và container runtime mới là thành phần tạo container. Vì vậy, khi điều tra lỗi cần nhìn đúng lớp:

| Triệu chứng | Lớp cần kiểm tra |
| --- | --- |
| Không có Pod mới | Deployment, ReplicaSet, quota, scheduler |
| Pod Pending | tài nguyên node, affinity, taint, volume hoặc scheduling |
| Container không chạy | image, command, secret, volume, runtime |
| Pod Running nhưng Not Ready | readiness probe, dependency hoặc cấu hình ứng dụng |
| Container restart liên tục | process exit, liveness, OOM hoặc startup failure |
| Service không có backend | selector, Pod labels và Ready condition |

### 4.3. Replica không phải bản sao có bộ nhớ chung

Ba replica của cùng một Deployment là ba process độc lập. Mỗi process có heap riêng, cache riêng và có thể nhận request ở thời điểm khác nhau. Nếu ứng dụng cần session, lock hoặc dữ liệu dùng chung, không nên chỉ lưu chúng trong memory của một Pod.

Thiết kế cần xác định:

- request có stateless không;
- cache có thể mất khi Pod bị thay thế không;
- session được lưu ở đâu;
- thao tác ghi có idempotent không;
- rollout có thể làm hai phiên bản cùng tồn tại trong một khoảng thời gian không.

Những câu hỏi này ảnh hưởng trực tiếp đến retry, load balancing và cập nhật cấu hình.

## 5. Vòng đời một Pod

### 5.1. Từ manifest đến Pod được lập lịch

Khi Deployment hoặc workload tương tự được áp dụng, các bước khái quát là:

1. API Server nhận object và lưu trạng thái mong muốn.
2. Controller tạo hoặc cập nhật ReplicaSet.
3. ReplicaSet tạo Pod object.
4. Scheduler chọn node đáp ứng điều kiện.
5. Kubelet trên node nhận Pod assignment.
6. Kubelet kéo image nếu cần, tạo sandbox mạng và tạo container.
7. Container runtime khởi động process.
8. Các probe bắt đầu theo cấu hình.
9. Pod có thể trở thành Ready nếu các điều kiện cần đạt.
10. Service đưa Pod vào nhóm backend khi Pod được chọn và sẵn sàng.

Không phải bước nào cũng hoàn thành tức thì. Image lớn, node thiếu tài nguyên, registry chậm, volume chưa attach hoặc ứng dụng khởi động lâu đều có thể kéo dài vòng đời.

### 5.2. Pod phase và container state

Pod phase là mô tả tổng quát, còn container state mô tả chi tiết hơn. Các khái niệm này không đồng nghĩa:

| Khái niệm | Diễn giải |
| --- | --- |
| Pending | Pod chưa chạy đầy đủ, có thể đang chờ scheduler, image, volume hoặc resource |
| Running | Pod đã được gán node và ít nhất container chính đang chạy |
| Succeeded | Các container kết thúc thành công, thường phù hợp với Job |
| Failed | Container kết thúc với lỗi hoặc bị hệ thống đánh dấu thất bại |
| Unknown | Không thu thập được trạng thái đầy đủ từ node |

Container state thường được hiểu qua:

- Waiting: đang chờ điều kiện để chạy, có thể kèm lý do;
- Running: process đang chạy;
- Terminated: process đã kết thúc, có exit code, reason và thời điểm.

Một Pod phase Running vẫn có thể chứa container phụ đang Waiting hoặc ứng dụng chưa Ready. Khi xem sự cố, phải đọc cả conditions, container statuses, events và kết quả probe.

### 5.3. Termination và graceful shutdown

Khi Pod bị xóa hoặc bị thay thế, Kubernetes thường gửi tín hiệu để process kết thúc một cách có kiểm soát trong thời gian cho phép. Ứng dụng Spring Boot cần xử lý shutdown đúng để:

- ngừng nhận request mới;
- hoàn tất hoặc hủy request đang xử lý theo chính sách;
- đóng connection pool;
- flush log và metric cần thiết;
- giải phóng lock hoặc tài nguyên bên ngoài.

Nếu process không kết thúc trong thời gian chờ, container có thể bị buộc dừng. Thời gian grace period phải phù hợp với thời gian shutdown thực tế, nhưng không nên kéo dài vô hạn vì sẽ làm rollout và scale chậm.

Một request tạo đơn hàng cần đặc biệt chú ý khi Pod bị terminate giữa chừng. Retry từ client có thể tạo bản ghi trùng nếu API không dùng idempotency key hoặc cơ chế kiểm tra trùng.

## 6. Vòng đời container và restart

### 6.1. Restart container khác với tạo Pod mới

Kubernetes có thể restart container trong cùng Pod. Khi đó Pod có thể giữ cùng IP và metadata, nhưng process cùng filesystem tạm của container có thể được tạo lại. Trong trường hợp khác, controller xóa Pod cũ và tạo Pod mới với IP, tên hoặc UID khác.

Phân biệt hai tình huống:

| Hành động | Điều thường thay đổi | Điều thường giữ ở cấp workload |
| --- | --- | --- |
| Restart container | process, trạng thái trong container, heap | Pod object, Pod IP thường có thể giữ trong lần restart |
| Tạo Pod thay thế | tên, UID, IP, node có thể đổi | template của Deployment, Service selector |

Ứng dụng không nên dựa vào việc Pod IP sẽ được giữ sau lỗi. Client phải dùng Service hoặc cơ chế discovery phù hợp.

### 6.2. Restart policy và CrashLoopBackOff

Nếu process liên tục thoát hoặc probe liveness liên tục thất bại, kubelet có thể khởi động lại container với khoảng chờ tăng dần. “CrashLoopBackOff” là tín hiệu container đang rơi vào chu kỳ lỗi và hệ thống đang giãn thời gian thử lại; nó không phải nguyên nhân gốc.

Nguyên nhân cần kiểm tra có thể gồm:

- command hoặc argument sai;
- thiếu biến môi trường;
- Secret hoặc ConfigMap không tồn tại;
- lỗi quyền đọc nguồn cấu hình;
- port hoặc profile không đúng;
- lỗi kết nối dependency khi khởi động;
- JVM hết memory;
- liveness probe bắt đầu quá sớm;
- ứng dụng thoát vì cấu hình bắt buộc không hợp lệ.

Đừng chỉ tăng thời gian delay để che một lỗi khởi động. Hãy xác định process thoát vì điều gì rồi quyết định fail-fast, retry có giới hạn hoặc dùng startup probe.

## 7. Resource request và limit

### 7.1. Vì sao resource ảnh hưởng vòng đời

Scheduler dùng resource request để quyết định Pod có thể đặt lên node hay không. Container có thể bị giới hạn bởi limit. Nếu ứng dụng Java dùng memory vượt giới hạn, container có thể bị OOMKilled.

Request và limit cần dựa trên đo lường:

- heap tối đa của JVM;
- native memory;
- thread stack;
- metaspace;
- buffer và thư viện native;
- sidecar nếu có;
- tải request thực tế;
- mức tăng đột biến khi khởi động.

Một Pod Pending vì request quá lớn là lỗi scheduling. Một container bị OOMKilled vì limit quá thấp là lỗi resource runtime. Hai lỗi cần cách xử lý khác nhau.

### 7.2. JVM trong container

JVM cần nhận biết giới hạn container và được cấu hình phù hợp với phiên bản runtime. Không nên dành toàn bộ memory limit cho Java heap vì process còn cần native memory và các vùng khác.

Ví dụ khái niệm:

    memory limit của container
        = heap
        + metaspace
        + thread stacks
        + direct buffers
        + native memory
        + overhead

Nếu heap đặt sát limit, một đợt tăng thread hoặc buffer có thể làm process bị OOM dù heap chưa đầy. Theo dõi heap usage và RSS để phân biệt memory leak trong heap với memory ngoài heap.

### 7.3. Resource và số replica

Khi tăng replica, tổng request tài nguyên cũng tăng. Một Deployment với nhiều replica nhưng node không còn capacity sẽ tạo Pod Pending. Khi scale down, cache cục bộ và trạng thái trong memory của các Pod bị loại sẽ mất.

Một bản sao sẵn sàng cần có cả:

- resource request đủ để được lập lịch;
- limit không quá chặt so với mức dùng thực tế;
- probe không gây restart giả;
- dependency có thể chịu được số kết nối tăng khi scale.

## 8. Probe cho ứng dụng Spring Boot

### 8.1. Startup probe

Startup probe phù hợp với ứng dụng khởi động lâu. Trong thời gian startup chưa thành công, Kubernetes có thể trì hoãn việc đánh giá liveness và readiness theo cơ chế probe đã cấu hình. Điều này giúp tránh liveness restart một JVM chỉ vì đang nạp class, kết nối database hoặc chuẩn bị cache.

Startup probe không nên được dùng để che một ứng dụng không thể khởi động. Nếu hết ngưỡng mà ứng dụng vẫn chưa sẵn sàng, cần xem log và nguyên nhân thật.

### 8.2. Readiness probe

Readiness trả lời: “Pod này có nên nhận traffic ngay bây giờ không?” Khi readiness thất bại, Pod có thể vẫn Running nhưng bị loại khỏi backend phù hợp của Service.

Readiness có thể kiểm tra:

- process đã khởi động;
- cổng HTTP lắng nghe;
- các dependency tối thiểu để phục vụ nghiệp vụ;
- trạng thái ứng dụng vừa nhận cấu hình bắt buộc.

Không đưa tất cả dependency vào readiness một cách máy móc. Nếu một hệ thống phụ trợ tạm lỗi nhưng endpoint chính vẫn có thể phục vụ an toàn, làm readiness thất bại có thể loại toàn bộ replica và gây gián đoạn lớn hơn.

### 8.3. Liveness probe

Liveness trả lời: “Process này có cần được khởi động lại không?” Liveness phù hợp với tình trạng tiến trình bị kẹt hoặc không thể tự phục hồi. Nó không nên chỉ kiểm tra mọi dịch vụ bên ngoài.

Ví dụ một ứng dụng có thể tiếp tục xử lý request từ cache khi Kubernetes API tạm thời chậm. Nếu liveness phụ thuộc trực tiếp vào API, lỗi mạng tạm thời có thể khiến mọi Pod restart cùng lúc.

### 8.4. Ví dụ cấu hình probe

Đoạn sau là ví dụ minh họa một phần Pod template:

    ports:
      - name: http
        containerPort: 8080

    startupProbe:
      httpGet:
        path: /actuator/health
        port: http
      failureThreshold: 30
      periodSeconds: 10

    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: http
      periodSeconds: 5

    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: http
      periodSeconds: 10

Các endpoint phải được ứng dụng cung cấp và bảo vệ phù hợp. Giá trị delay, timeout và threshold cần dựa trên thời gian startup, tải và hành vi thực tế; không sao chép nguyên xi vào production.

## 9. Từ Pod đến Service

Service không tạo process và không thay thế Pod. Service cung cấp một địa chỉ ổn định và chọn các Pod qua selector. Pod chỉ nhận traffic từ Service khi labels khớp và Pod được xem là phù hợp để nhận traffic.

Luồng khái quát:

    client
        → DNS của Service
        → Service port
        → endpoint của Pod Ready
        → container port
        → ứng dụng Spring Boot

Nếu Pod Running nhưng readiness fail, Pod có thể không xuất hiện trong nhóm endpoint phục vụ. Đây là hành vi mong muốn khi ứng dụng chưa sẵn sàng.

### 9.1. Label và selector

Ví dụ label trên Pod template:

    metadata:
      labels:
        app: order-service
        version: v1

Selector của Service cần khớp đúng label cần dùng. Selector quá rộng có thể đưa Pod của workload khác vào cùng backend; selector quá hẹp khiến Service không có endpoint.

Khi rollout, có thể tồn tại Pod của phiên bản cũ và mới trong cùng thời gian. Label version giúp quan sát và phân biệt, còn selector của Service phải phản ánh chiến lược routing đã định.

### 9.2. Readiness trong rollout

Deployment có thể tạo Pod mới trước khi loại hết Pod cũ. Readiness giúp Service chỉ đưa Pod mới vào traffic sau khi ứng dụng sẵn sàng. Nếu probe không đúng, rollout có thể:

- kẹt vì Pod mới không Ready;
- đưa traffic vào Pod chưa hoàn tất startup;
- loại quá nhiều Pod cùng lúc nếu ngưỡng rollout không phù hợp.

Rollout cần được quan sát bằng số replica mong muốn, số replica đã cập nhật, số replica sẵn sàng và trạng thái Pod.

## 10. Pod và ConfigMap, Secret

Pod là nơi ứng dụng nhận cấu hình, nhưng Pod không quyết định một mình cách cấu hình được nạp. Các nguồn thường gặp:

| Cách cung cấp | Đặc điểm vòng đời |
| --- | --- |
| Environment variable | Giá trị thường được chụp khi process khởi động |
| Volume mount | File có thể được cập nhật theo cơ chế volume; ứng dụng phải đọc lại |
| Spring Cloud Kubernetes đọc API | Phụ thuộc client, RBAC, cache và cơ chế refresh |

Khi Pod bị thay thế, mọi environment variable được tạo lại từ spec và nguồn tham chiếu tại thời điểm tạo Pod. Khi ConfigMap thay đổi, không nên mặc định process đang chạy đã nhận giá trị mới.

Nếu Secret hoặc ConfigMap bắt buộc không tồn tại, ứng dụng có thể:

- không tạo được container vì volume hoặc env reference không hợp lệ;
- khởi động rồi fail-fast vì property bắt buộc thiếu;
- khởi động với fallback, nếu thiết kế cho phép;
- tiếp tục dùng giá trị đã nạp trước đó trong một cơ chế cache.

Mỗi hành vi cần được chọn rõ. Fallback không phù hợp cho mật khẩu, endpoint production hoặc chính sách bảo mật quan trọng.

## 11. Một Pod không phải một đơn vị bất tử

Kubernetes được thiết kế để thay thế Pod. Pod có thể bị thay vì:

- image hoặc Pod template đổi;
- node bị drain hoặc mất;
- Pod vượt resource limit;
- liveness probe thất bại;
- taint, affinity hoặc chính sách scheduling thay đổi;
- người vận hành xóa Pod để kích hoạt tái tạo;
- controller scale workload;
- rollout cần phiên bản mới.

Ứng dụng nên đáp ứng các nguyên tắc:

1. Khởi động lặp lại được với cùng cấu hình hợp lệ.
2. Không phụ thuộc IP hoặc tên cụ thể của Pod.
3. Shutdown an toàn và có giới hạn thời gian.
4. Có thể mất cache hoặc trạng thái tạm thời.
5. Có health signal để controller đưa ra quyết định.
6. Có log và metric đủ để chẩn đoán bản sao mới.

## 12. Chẩn đoán theo vòng đời

### 12.1. Pod Pending

Kiểm tra:

- node có đủ CPU và memory theo request không;
- taint và toleration có phù hợp không;
- node selector hoặc affinity có giới hạn quá chặt không;
- volume có thể attach và mount không;
- quota namespace có hết không;
- image pull secret hoặc registry có sẵn không.

Pending xảy ra trước khi process Java chạy, vì vậy không nên tìm nguyên nhân đầu tiên trong log Spring Boot.

### 12.2. ImagePullBackOff

Kiểm tra:

- tên image và tag;
- digest nếu dùng;
- registry có truy cập được từ node không;
- imagePullSecrets;
- quyền đọc registry;
- kiến trúc image có phù hợp node không.

Nếu image chưa được kéo, container chưa chạy và probe chưa phải nguyên nhân.

### 12.3. ContainerCreating

Kiểm tra:

- volume mount;
- Secret hoặc ConfigMap tham chiếu;
- network sandbox;
- quyền hoặc lỗi của container runtime;
- event của Pod.

### 12.4. CrashLoopBackOff

Kiểm tra log lần chạy trước, exit code và lý do terminated. Những câu hỏi ưu tiên:

- process có thoát ngay không;
- profile và property bắt buộc có đúng không;
- JVM có OOM không;
- command có gọi đúng artifact không;
- liveness có bắt đầu quá sớm không;
- ứng dụng có lỗi do dependency tạm thời không.

### 12.5. Running nhưng Not Ready

Kiểm tra:

- endpoint readiness có trả lỗi không;
- port probe có đúng không;
- app đã hoàn tất startup chưa;
- dependency bắt buộc có sẵn không;
- Pod condition có cho thấy readiness fail không;
- Service có selector đúng không.

Running và Not Ready có thể là trạng thái hợp lệ trong lúc startup. Vấn đề là thời gian kéo dài và lý do không đạt.

### 12.6. Ready nhưng request lỗi

Khi Pod Ready nhưng request thất bại, kiểm tra thêm:

- Service port và targetPort;
- protocol HTTP hoặc HTTPS;
- path và context path;
- timeout client;
- NetworkPolicy;
- exception trong request;
- load balancing hoặc discovery trả đích cũ;
- ứng dụng đã nhận cấu hình đúng chưa.

Readiness không phải một bài kiểm tra toàn bộ nghiệp vụ. Nó có thể đạt trong khi một endpoint riêng vẫn lỗi.

## 13. Ví dụ vòng đời order-service

Giả sử Deployment muốn duy trì hai replica của order-service:

    Deployment
      desired replicas: 2
        ├── Pod order-service-a
        └── Pod order-service-b

Khi cập nhật image sang phiên bản mới:

1. Deployment tạo ReplicaSet mới.
2. Pod mới được tạo từ template mới.
3. Scheduler gán Pod mới cho node phù hợp.
4. Kubelet kéo image và khởi động container.
5. Startup probe chờ ứng dụng hoàn tất khởi động.
6. Readiness probe bắt đầu kiểm tra khả năng nhận traffic.
7. Pod mới Ready và được đưa vào backend Service.
8. Controller giảm dần replica cũ theo chiến lược rollout.
9. Pod cũ nhận tín hiệu kết thúc và shutdown.
10. Service tiếp tục gửi request đến các Pod còn Ready.

Nếu Pod mới không Ready, controller có thể giữ lại Pod cũ tùy chiến lược rollout. Nếu liveness được cấu hình quá nhạy, Pod mới có thể restart trước khi hoàn tất startup và không bao giờ đạt Ready.

Nếu phiên bản mới đọc ConfigMap khác phiên bản cũ, trong thời gian rollout hai replica có thể có hành vi khác nhau. Cấu hình có thay đổi tương thích ngược hay không là một câu hỏi cần giải quyết ở cấp ứng dụng.

## 14. Các nguyên tắc thiết kế thực tế

### 14.1. Thiết kế stateless trước

Mỗi Pod nên có thể bị thay thế mà không làm mất dữ liệu nghiệp vụ. Cache cục bộ có thể được dùng để tối ưu, nhưng request phải có hành vi đúng khi cache trống hoặc Pod mới khởi động.

### 14.2. Đặt thời gian chờ hữu hạn

Client gọi service, Kubernetes API hoặc watcher endpoint đều cần timeout. Một request treo vô hạn có thể làm đầy thread pool và khiến readiness hoặc liveness trở nên không đáng tin.

### 14.3. Graceful shutdown cần kiểm chứng

Không chỉ khai báo thời gian chờ. Hãy kiểm tra khi Pod bị terminate:

- request đang chạy được xử lý thế nào;
- connection mới có bị chặn không;
- connection pool có đóng đúng không;
- message consumer có commit hoặc trả lại message không;
- metric cuối có được gửi hay không.

### 14.4. Log theo Pod nhưng truy vết theo request

Pod có thể bị thay thế, vì vậy log cần có request ID, trace ID hoặc correlation ID. Đồng thời nên ghi Pod name hoặc version ở metadata để biết request đi qua bản sao nào.

Không ghi Secret, token hoặc toàn bộ header xác thực vào log.

### 14.5. Giới hạn quyền trong Pod

ServiceAccount, volume và container security context cần được chọn theo nhu cầu. Nếu ứng dụng không cần gọi Kubernetes API, không nên cấp quyền đọc tài nguyên chỉ vì module có thể hỗ trợ discovery hoặc config.

## 15. Checklist kiểm tra một replica

### Container

- [ ] Image đúng version hoặc digest.
- [ ] Command và argument khởi động đúng artifact.
- [ ] Port container đúng với ứng dụng.
- [ ] Environment và volume có đủ dữ liệu bắt buộc.
- [ ] Resource request và limit phù hợp.
- [ ] Process thoát với lý do có thể chẩn đoán.

### Pod

- [ ] Pod được lập lịch trên node phù hợp.
- [ ] Container state và Pod conditions được đọc cùng nhau.
- [ ] Pod không phụ thuộc IP hoặc tên cố định.
- [ ] ServiceAccount đúng với yêu cầu.
- [ ] Volume không chứa dữ liệu cần giữ lâu dài nếu chưa có persistent storage.

### Replica và Service

- [ ] Deployment duy trì đúng số replica mong muốn.
- [ ] Labels và selector khớp.
- [ ] Readiness phản ánh đúng khả năng nhận traffic.
- [ ] Service chỉ có backend Pod phù hợp.
- [ ] Rollout có thể dừng, quan sát và rollback.

### Spring Boot

- [ ] Startup probe đủ rộng cho thời gian khởi động thực tế.
- [ ] Readiness và liveness có mục đích riêng.
- [ ] Actuator endpoint được bảo vệ và không lộ dữ liệu.
- [ ] Graceful shutdown đã được kiểm tra.
- [ ] Log có đủ thông tin chẩn đoán nhưng không chứa Secret.

## 16. Những hiểu nhầm thường gặp

**“Pod đang Running nghĩa là ứng dụng đã phục vụ.”** Running chỉ nói rằng Pod và container đang ở trạng thái chạy theo quan sát hiện tại. Readiness mới liên quan trực tiếp đến việc nhận traffic.

**“Restart container và tạo Pod mới là như nhau.”** Restart thay process trong cùng Pod; Pod mới có thể có IP, UID, node và dữ liệu tạm khác.

**“Pod IP là địa chỉ để service khác lưu lại.”** Pod IP có vòng đời ngắn. Client nên dùng Service hoặc discovery.

**“Một replica là một process có thể giữ session cho mọi request.”** Replica độc lập với nhau. Session hoặc trạng thái dùng chung cần lưu ở hệ thống phù hợp.

**“Liveness phải kiểm tra mọi dependency.”** Liveness thất bại sẽ dẫn đến restart. Dependency bên ngoài tạm lỗi không phải lúc nào cũng được sửa bằng restart.

**“Tăng delay probe sẽ sửa CrashLoopBackOff.”** Delay chỉ có ích khi ứng dụng khởi động chậm. Nếu command, image, property hoặc quyền sai, cần sửa nguyên nhân.

**“ConfigMap đổi thì mọi container lập tức dùng giá trị mới.”** Hành vi phụ thuộc cách đưa cấu hình vào Pod và cơ chế reload. Environment thường cần Pod mới; bean cũng phải hỗ trợ cập nhật.

## 17. Tự kiểm tra mức độ hiểu

**Câu 1: Pod và container khác nhau thế nào?**

Container là môi trường chạy process từ image. Pod là đơn vị Kubernetes lập lịch, chứa một hoặc nhiều container có network và vòng đời liên quan. Một Pod không phải chỉ là tên khác của container.

**Câu 2: Vì sao Pod Running nhưng Service không gửi request đến Pod?**

Pod có thể chưa Ready do readiness probe fail, label không khớp selector, Service sai port hoặc endpoint chưa được cập nhật. Running không đủ để chứng minh Pod là backend hợp lệ.

**Câu 3: Khi process Java thoát, Kubernetes có luôn tạo Pod mới không?**

Không nhất thiết. Kubelet có thể restart container trong cùng Pod theo restart policy. Nếu Pod bị controller thay thế, Pod mới mới có UID và địa chỉ khác.

**Câu 4: Tại sao startup probe hữu ích cho Spring Boot?**

Spring Boot có thể cần thời gian nạp class, cấu hình, kết nối dependency hoặc chuẩn bị cache. Startup probe giúp phân biệt giai đoạn khởi động với tình trạng process đã chạy nhưng bị kẹt.

**Câu 5: Khi nào readiness nên thất bại?**

Khi bản sao chưa thể nhận request đúng cách theo tiêu chí phục vụ đã xác định. Readiness không nên thất bại máy móc vì mọi dependency bên ngoài nếu điều đó làm toàn bộ workload bị loại khỏi traffic mà không cần thiết.

**Câu 6: Vì sao ứng dụng cần stateless khi chạy nhiều replica?**

Vì bất kỳ Pod nào cũng có thể bị thay thế. Nếu trạng thái quan trọng chỉ nằm trong memory của một Pod, request tiếp theo đến replica khác có thể mất dữ liệu hoặc sai hành vi.

## Kết luận

Pod là đơn vị lập lịch và vòng đời của Kubernetes; container là nơi process Spring Boot thực thi; Deployment và ReplicaSet duy trì số bản sao; Service tạo điểm truy cập ổn định đến các Pod phù hợp. Một replica chỉ thật sự hữu ích khi container khởi động đúng, Pod có tài nguyên phù hợp, readiness phản ánh đúng khả năng phục vụ và ứng dụng chịu được việc Pod bị thay thế.

Khi chuẩn bị cho DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer hoặc Configuration Watcher, hãy bắt đầu từ vòng đời này. Ứng dụng phải có thể khởi động lặp lại, không phụ thuộc IP Pod, xử lý shutdown, quan sát được probe và phân biệt rõ lỗi process, lỗi mạng, lỗi quyền cùng lỗi cấu hình. Đó là nền tảng để các tính năng Spring Cloud Kubernetes hoạt động có thể dự đoán trong một cluster thực tế.
