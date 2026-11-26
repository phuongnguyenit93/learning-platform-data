# Phân biệt leader của ứng dụng với leader của control plane

Trong module **SPRING_CLOUD_KUBERNETES**, bầu leader của ứng dụng giải quyết câu hỏi: **replica nào được đảm nhiệm một công việc riêng của ứng dụng?** Bầu leader trong control plane giải quyết việc phối hợp giữa các instance của một thành phần hạ tầng Kubernetes.

Ví dụ, ba Pod `reporting` cùng có lịch tổng hợp báo cáo. Việc Kubernetes đã có leader của `kube-scheduler` không khiến lịch trong Spring chỉ chạy ở một Pod. Ngược lại, Pod được bầu làm leader tạo báo cáo cũng không trở thành scheduler hoặc thành viên quản trị cụm.

Bài thuộc chương **Bầu leader**, tập trung vào ranh giới trách nhiệm, phạm vi bầu chọn và cách quan sát đúng tầng. Ví dụ Spring dùng cơ chế Fabric8 dựa trên ConfigMap của **Spring Cloud Kubernetes 3.3.x**; không trộn thuộc tính hay sự kiện của các implementation khác.

## 1. Leader luôn gắn với một nhóm và một trách nhiệm

Câu “Pod này là leader” chưa đủ rõ. Cần trả lời thêm:

| Câu hỏi | Ví dụ của ứng dụng báo cáo |
| --- | --- |
| Leader của công việc nào? | Điều phối tác vụ tạo báo cáo ngày |
| Những instance nào tham gia? | Các replica của `reporting` |
| Phạm vi phối hợp ở đâu? | Namespace `sck-lab` và bản ghi bầu chọn riêng |
| Tín hiệu nào cho phép bắt đầu hoặc dừng? | Sự kiện leadership của thư viện trong ứng dụng |
| Ai bảo vệ kết quả nghiệp vụ? | Mã ứng dụng và hệ thống lưu kết quả |

Một ứng dụng có thể có nhiều vai trò cần phối hợp, chẳng hạn điều phối nhập dữ liệu và tạo báo cáo. Tùy thiết kế, chúng dùng các nhóm bầu chọn riêng hoặc một leader chung. Không có quy tắc rằng mọi công việc của mọi ứng dụng trong cụm phải dùng một leader duy nhất.

Từ `role` trong cấu hình bầu leader mô tả vai trò tranh quyền của ứng dụng. Nó không phải tài nguyên `Role` của Kubernetes RBAC.

## 2. So sánh hai tầng trách nhiệm

| Tiêu chí | Leader của ứng dụng | Leader của thành phần control plane |
| --- | --- | --- |
| Mục đích | Điều phối một tác vụ hoặc vai trò nghiệp vụ | Điều phối hoạt động của thành phần quản lý cụm |
| Ứng viên | Các instance ứng dụng được cấu hình cùng nhóm | Các instance của thành phần tương ứng |
| Ví dụ | Một replica điều phối xuất báo cáo | Một instance scheduler đảm nhiệm lập lịch trong cấu hình HA |
| Phạm vi công việc | Dữ liệu và tiến trình của ứng dụng | Trạng thái và vòng điều khiển của Kubernetes |
| Tài nguyên phối hợp | Có thể là ConfigMap, Lease hoặc cơ chế khác | Thường là Lease cho scheduler/controller manager hiện đại |
| Chủ thể cấu hình | Nhóm phát triển và vận hành ứng dụng | Nhóm nền tảng hoặc nhà cung cấp Kubernetes |
| Khi mất leader | Tác vụ cần leadership có thể tạm ngừng hoặc chuyển instance | Chức năng quản lý của thành phần đó có thể tạm gián đoạn |
| Quyền cần có | Quyền API cho cơ chế phối hợp và dữ liệu thực sự cần | Quyền hệ thống phù hợp trách nhiệm control plane |
| Có tự chọn leader ứng dụng không? | Đây là phạm vi mà ứng dụng phải triển khai | Không thực hiện việc này thay ứng dụng |

“Leader của control plane” là cách nói rút gọn dễ gây hiểu nhầm. Kubernetes không có một chức danh duy nhất chọn ra một máy làm leader của toàn bộ cụm, rồi để máy đó quyết định mọi hoạt động.

[Tài liệu Kubernetes Components](https://kubernetes.io/docs/concepts/overview/components/) phân biệt API server, scheduler, controller manager và etcd theo trách nhiệm. Các cơ chế phối hợp của chúng cũng phải được nhìn theo từng thành phần.

## 3. Trong control plane có những khái niệm leader nào?

### Scheduler và controller manager có phạm vi bầu chọn riêng

Trong cấu hình HA có bật leader election, các instance `kube-scheduler` phối hợp để chọn instance đảm nhiệm hoạt động lập lịch của nhóm đó. `kube-controller-manager` có cơ chế phối hợp riêng cho các vòng điều khiển mà nó quản lý.

Tham số khóa bầu chọn được mô tả riêng trong tài liệu [kube-scheduler](https://kubernetes.io/docs/reference/command-line-tools-reference/kube-scheduler/) và [kube-controller-manager](https://kubernetes.io/docs/reference/command-line-tools-reference/kube-controller-manager/). Các tên như `kube-system/kube-scheduler` hoặc `kube-system/kube-controller-manager` là những ví dụ thường gặp; cấu hình thực tế có thể khác.

Hai thành phần không bắt buộc có leader nằm trên cùng một máy. Mất leader của scheduler cũng không có nghĩa mọi process đang chạy trong các Pod ứng dụng lập tức dừng lại.

### Leader của etcd thuộc giao thức đồng thuận của etcd

Nếu cụm dùng etcd làm kho dữ liệu, các thành viên etcd phối hợp qua Raft. Leader của nhóm etcd tham gia quá trình sao chép và đồng thuận dữ liệu của nhóm đó.

Theo [tài liệu hiệu năng etcd](https://etcd.io/docs/v3.6/op-guide/performance/), etcd dùng Raft để sao chép yêu cầu và đạt đồng thuận. Cơ chế này không phải việc các Pod Spring tranh một ConfigMap.

Số replica ứng dụng không làm thay đổi số thành viên bỏ phiếu của etcd. Ba Pod `reporting` không trở thành ba thành viên Raft; ứng dụng thông thường truy cập Kubernetes API thay vì kết nối trực tiếp vào etcd.

### API server không vận hành theo mô hình một leader phục vụ mọi yêu cầu

`kube-apiserver` có thể chạy nhiều instance và phân phối lưu lượng giữa các instance. [Kubernetes Cluster Architecture](https://kubernetes.io/docs/concepts/architecture/#kube-apiserver) mô tả khả năng mở rộng ngang này.

Một API server nhận yêu cầu cập nhật khóa của ứng dụng không vì thế trở thành leader nghiệp vụ của ứng dụng. Không cần tìm “API server leader” để ứng dụng gửi tất cả yêu cầu Kubernetes API vào đó.

### Một cấu hình HA có thể đồng thời có nhiều leader khác nhau

Ví dụ **minh họa**, không phải cách Kubernetes bắt buộc phân bố thành phần:

~~~text
Nhóm scheduler           -> instance trên control-plane-2
Nhóm controller manager  -> instance trên control-plane-1
Nhóm Raft của etcd       -> etcd-member-3
Vai trò daily-report     -> Pod reporting-a trên worker-1
Vai trò import-catalog   -> Pod importer-b trên worker-2
~~~

Các dòng này mô tả những trách nhiệm khác nhau. Không có mâu thuẫn khi chúng có các leader khác nhau.

## 4. Dùng chung Kubernetes API không có nghĩa cùng cuộc bầu chọn

Ứng dụng có thể dùng Kubernetes làm nơi lưu bản ghi phối hợp. Control plane cũng có thể dùng các đối tượng Kubernetes cho bầu chọn thành phần. Điểm giống nhau về hạ tầng lưu trữ không gộp hai miền trách nhiệm.

~~~mermaid
flowchart TD
    subgraph APP["Nhóm ứng dụng reporting"]
        A["reporting-a"]
        B["reporting-b"]
        C["reporting-c"]
    end
    subgraph SYS["Các nhóm thành phần Kubernetes"]
        S["Nhóm kube-scheduler"]
        M["Nhóm kube-controller-manager"]
    end
    A --> K1["ConfigMap khóa reporting trong sck-lab"]
    B --> K1
    C --> K1
    S --> K2["Lease riêng của scheduler"]
    M --> K3["Lease riêng của controller manager"]
    K1 --> API["Kubernetes API"]
    K2 --> API
    K3 --> API
    API --> STORE["Kho dữ liệu cụm"]
    STORE --> RAFT["Nhóm etcd tự thực hiện đồng thuận Raft"]
~~~

Sơ đồ thể hiện đường phụ thuộc logic, không phải kết nối mạng trực tiếp đến một “đối tượng khóa”. Client đọc hoặc cập nhật tài nguyên thông qua API.

Để xác định một miền bầu chọn của ứng dụng, cần xét các thông tin mà implementation sử dụng, chẳng hạn:

~~~text
namespace
+ loại tài nguyên khóa
+ tên tài nguyên khóa
+ vai trò hoặc khóa logic bên trong bản ghi
~~~

Nếu hai nhóm ứng dụng được cấu hình để tranh cùng một khóa logic, chúng có thể ảnh hưởng nhau. Nếu cùng tên tài nguyên nhưng khác namespace hoặc khác loại tài nguyên, đó không mặc nhiên là cùng một miền phối hợp.

Tên `spring.application.name` hoặc tên Deployment giống nhau chưa đủ chứng minh các replica cùng tranh một khóa. Phải kiểm tra cấu hình bầu chọn thực sự có hiệu lực.

## 5. Đối tượng Lease không phải lúc nào cũng là khóa bầu leader

Kubernetes có tài nguyên `Lease` thuộc API group `coordination.k8s.io`. Mục đích của một đối tượng Lease phụ thuộc thành phần sử dụng nó.

| Quan sát | Ý nghĩa có thể có |
| --- | --- |
| Lease của scheduler/controller manager | Phối hợp leader cho thành phần tương ứng |
| Lease tên Node trong `kube-node-lease` | Heartbeat của kubelet |
| Lease công bố danh tính API server | Nhận diện instance API server |
| Lease do một workload tạo | Cơ chế phối hợp do workload đó định nghĩa |

[Tài liệu Leases của Kubernetes](https://kubernetes.io/docs/concepts/architecture/leases/) mô tả các cách dùng này. Vì vậy, chỉ thấy `holderIdentity` trong một Lease chưa đủ kết luận “đây là leader toàn cụm”.

Với một Lease dùng cho bầu chọn, các trường như `holderIdentity`, `renewTime` và `leaseDurationSeconds` hỗ trợ client theo dõi người giữ khóa và trạng thái gia hạn. Ý nghĩa trường được mô tả trong [Kubernetes Lease API](https://kubernetes.io/docs/reference/kubernetes-api/coordination/lease-v1/).

Cần đọc theo giao thức của client. Một giá trị holder còn nằm trong đối tượng không tự chứng minh process đó vẫn có quyền thực hiện nghiệp vụ. Hết hạn phối hợp cũng không đồng nghĩa đối tượng Lease phải tự biến mất khỏi API.

Lease của Kubernetes và khái niệm lease bên trong etcd là hai giao diện khác nhau. Không áp dụng máy móc cơ chế TTL của khóa etcd cho vòng đời đối tượng `Lease` Kubernetes.

## 6. Ví dụ Spring: một vai trò daily-report giữa ba replica

Giả sử nhóm vận hành đã có ứng dụng `reporting` gồm ba replica trong namespace `sck-lab`. Tất cả cùng tham gia vai trò `daily-report`.

### Dependency và cấu hình minh họa

[Tài liệu Leader Election của Spring Cloud Kubernetes 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/leader-election.html) mô tả implementation Fabric8 dùng ConfigMap và các sự kiện Spring Integration.

Thêm dependency với phiên bản được quản lý bằng Spring Cloud BOM tương thích với ứng dụng:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-kubernetes-fabric8-leader</artifactId>
</dependency>
~~~

Cấu hình minh họa:

~~~yaml
spring:
  application:
    name: reporting
  cloud:
    kubernetes:
      leader:
        enabled: true
        namespace: sck-lab
        config-map-name: reporting-daily-election
        role: daily-report
~~~

Các thuộc tính `namespace`, `config-map-name` và `role` được định nghĩa trong [LeaderProperties 3.3.3](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/leader/LeaderProperties.java).

Đây là cấu hình **leader của ứng dụng**, không phải tham số `--leader-elect` của scheduler hoặc controller manager.

Các replica cần credential và RBAC phù hợp với các thao tác của implementation: đọc/cập nhật khóa, tạo khóa nếu cấu hình cho phép và truy cập tài nguyên phụ trợ cần thiết. Một Role chỉ đọc ConfigMap không đủ cho thành phần phải sửa bản ghi bầu chọn. Bộ quyền chi tiết phải khớp client thực tế.

Khóa `reporting-daily-election` là dữ liệu phối hợp, nên tách khỏi ConfigMap chứa cấu hình nghiệp vụ. Không gắn nhầm label khiến Configuration Watcher coi cập nhật khóa là thay đổi cấu hình cần refresh ứng dụng.

### Ghi log sự kiện để nhận biết đúng tầng

Đặt lớp sau trong package được Spring Boot quét:

~~~java
package example.reporting;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.integration.leader.event.OnGrantedEvent;
import org.springframework.integration.leader.event.OnRevokedEvent;
import org.springframework.stereotype.Component;

@Component
public class ApplicationLeadershipObserver {

    private static final Logger log =
            LoggerFactory.getLogger(ApplicationLeadershipObserver.class);

    private final String instance =
            System.getenv().getOrDefault("HOSTNAME", "local");

    @EventListener
    public void onGranted(OnGrantedEvent event) {
        log.info("APPLICATION_LEADERSHIP_GRANTED instance={}", instance);
    }

    @EventListener
    public void onRevoked(OnRevokedEvent event) {
        log.info("APPLICATION_LEADERSHIP_REVOKED instance={}", instance);
    }
}
~~~

Ví dụ giả định một vai trò bầu leader được cấu hình trong application context này. Với nhiều nhóm hoặc vai trò, cần phân loại sự kiện theo nguồn/context tương ứng, không dùng chung một cờ không phân biệt.

Hai sự kiện trên được phát trong ứng dụng khi framework xử lý thay đổi leadership. Chúng không phải sự kiện “node control plane được bầu”. Theo [Spring Integration Leadership Event Handling](https://docs.spring.io/spring-integration/reference/leadership-event-handling.html), ứng dụng có thể dùng leadership để điều khiển vòng đời các endpoint hoặc thành phần xử lý phù hợp.

Lớp minh họa chỉ ghi log. Thêm dependency và nhận sự kiện không tự khiến mọi `@Scheduled`, HTTP endpoint hoặc luồng xử lý trong ứng dụng chỉ chạy trên leader. Mã nghiệp vụ phải chủ động sử dụng trạng thái và vòng đời leadership.

### Follower vẫn có thể phục vụ công việc khác

Một thiết kế thường gặp:

~~~text
reporting-a: leader daily-report + phục vụ HTTP
reporting-b: follower daily-report + phục vụ HTTP
reporting-c: follower daily-report + phục vụ HTTP
~~~

Quyền điều phối báo cáo không nhất thiết quyết định toàn bộ readiness của Pod. Nếu follower vẫn phục vụ các API bình thường, đánh dấu nó không sẵn sàng chỉ vì không phải leader có thể làm giảm dung lượng phục vụ không cần thiết.

Nếu có endpoint chỉ leader được xử lý, cần cơ chế định tuyến hoặc từ chối/chuyển tiếp rõ ràng. DiscoveryClient và Spring Cloud LoadBalancer thông thường không tự suy ra người giữ khóa bầu chọn để chỉ gửi lưu lượng vào đó.

## 7. Phạm vi khóa quyết định ai đang cạnh tranh

Ba replica chỉ phối hợp khi chúng thực sự dùng cùng miền bầu chọn mà implementation hiểu.

| Cấu hình | Hệ quả có thể có |
| --- | --- |
| Cùng namespace, cùng ConfigMap và cùng vai trò | Cùng tranh một vai trò |
| Cùng tên ConfigMap nhưng khác namespace | Hai miền dữ liệu tách biệt |
| Khác khóa hoặc khác vai trò logic | Có thể có các leader độc lập |
| Hai ứng dụng vô tình dùng chung khóa và vai trò | Có thể cạnh tranh ngoài ý muốn |
| Mỗi replica tự tạo một tên khóa riêng | Không tạo được một leader chung cho cả nhóm |

Ví dụ, `daily-report` ở môi trường thử nghiệm và sản xuất nên được tách theo phạm vi triển khai phù hợp. Ngược lại, trong một đợt blue/green, nếu hai phiên bản phải phối hợp để chỉ một bên điều phối tác vụ chung, việc vô tình đổi tên khóa theo mỗi Deployment có thể tạo thành hai nhóm độc lập.

Thiết kế khóa phải xuất phát từ phạm vi nghiệp vụ: một leader cho toàn hệ thống, cho từng tenant hay cho từng phân vùng công việc. Không quyết định chỉ dựa vào tên Pod hoặc số replica.

Tương tự, nhãn node `node-role.kubernetes.io/control-plane` mô tả vai trò của node. Nó không xác định Pod ứng dụng nào đang giữ leadership. Một Pod chạy trên node control plane, nếu được phép lập lịch tại đó, vẫn không vì vị trí chạy mà trở thành thành phần control plane.

## 8. Khi các loại leader thay đổi, điều gì bị ảnh hưởng?

### Mất một leader ứng dụng

Ví dụ `reporting-a` đang điều phối báo cáo rồi dừng:

1. Các replica còn lại và thư viện phải nhận biết tình trạng theo cơ chế của implementation.
2. Một replica phù hợp có thể tiếp nhận leadership.
3. Mã nghiệp vụ trên replica mới bắt đầu hoặc tiếp tục nhiệm vụ theo thiết kế.
4. Các tác vụ dở dang cần được xử lý bằng checkpoint, retry và cơ chế bảo vệ dữ liệu.

Việc chuyển leadership không tự khôi phục bộ nhớ, thread hoặc transaction đang dang dở trong Pod cũ. Nó cũng không đòi hỏi scheduler hoặc etcd phải đổi leader.

Nếu process đã chết, không thể trông chờ nó chạy callback `OnRevokedEvent` để dọn dẹp. Cơ chế an toàn không được phụ thuộc duy nhất vào một callback chắc chắn được thực thi trước khi chết.

### Mất leader của scheduler

Trong cấu hình HA phù hợp, instance scheduler khác có thể tiếp quản. Trong khoảng chuyển tiếp, quyết định lập lịch mới có thể bị chậm.

Pod ứng dụng đang chạy không tự mất trạng thái leadership chỉ vì scheduler đổi leader. Tuy nhiên, nếu ứng dụng cần Pod mới thay thế một Pod hỏng thì sự chậm trễ của tầng hạ tầng có thể ảnh hưởng gián tiếp đến thời gian phục hồi.

### Mất leader của controller manager

Các vòng điều khiển do thành phần đó đảm nhiệm có thể tạm chậm cho đến khi có instance tiếp quản. Tùy vòng điều khiển, việc duy trì số replica hoặc cập nhật trạng thái liên quan có thể chịu ảnh hưởng.

Điều này không phải một lệnh gửi tới Spring để đổi leader nghiệp vụ.

### Mất khả năng ghi qua API hoặc mất quorum etcd

Ứng dụng dùng Kubernetes làm nơi phối hợp phụ thuộc khả năng truy cập API và khả năng lưu thay đổi khóa.

[Tài liệu thiết kế etcd](https://etcd.io/docs/v3.6/learning/design-learner/) phân tích vai trò của quorum trong các tình huống phân vùng mạng. Nếu đường phối hợp không hoạt động, cả leader election của ứng dụng và các thành phần hạ tầng phụ thuộc đường đó có thể gặp vấn đề.

Tuy nhiên, không suy ra mọi Pod đang chạy đều lập tức dừng. Process nghiệp vụ có thể tiếp tục chạy bằng trạng thái cũ hoặc thực hiện công việc không phụ thuộc API. Điều này càng làm chính sách an toàn khi không xác nhận được leadership trở nên quan trọng.

### Tách quan hệ phụ thuộc khỏi quan hệ đồng nhất

~~~text
API/etcd gặp sự cố
    -> có thể ảnh hưởng nhiều nhóm phối hợp

Không suy ra:
    leader reporting = leader scheduler = leader etcd
~~~

Các nhóm bầu chọn độc lập về trách nhiệm vẫn có thể cùng chịu một sự cố hạ tầng.

## 9. Một leader không đồng nghĩa tác vụ chỉ có hiệu ứng đúng một lần

Giả sử ứng dụng cần xuất báo cáo `report-date=2026-11-24`. Sau khi leader cũ gửi yêu cầu lưu kết quả, kết nối timeout. Leader mới không biết việc lưu đã thành công hay chưa và thực hiện lại.

Ngay cả khi việc chuyển leadership diễn ra đúng, vẫn có thể xuất hiện:

- Tác vụ chạy lại sau một kết quả không xác định.
- Hai công việc chồng lấn trong khoảng chuyển tiếp.
- Process cũ tiếp tục thực hiện side effect sau khi mất quyền.
- Một phần công việc đã hoàn thành nhưng checkpoint chưa ghi nhận.

Tài liệu [client-go leader election](https://pkg.go.dev/k8s.io/client-go/tools/leaderelection) nêu rõ cơ chế đó không bảo đảm fencing. Đây là giới hạn cần hiểu khi dùng bầu leader làm cơ chế phối hợp; không được biến sự tồn tại của một bản ghi khóa thành lời hứa rằng mọi side effect bên ngoài đã được loại trừ trùng lặp.

Đối với ứng dụng nghiệp vụ, cần phân biệt:

| Cơ chế | Vấn đề xử lý |
| --- | --- |
| Leader election | Chọn instance điều phối một vai trò |
| Idempotency key | Tránh lặp hiệu ứng cho cùng thao tác nghiệp vụ |
| Unique constraint/transaction | Bảo vệ bất biến trong kho dữ liệu |
| Fencing token | Cho hệ thống đích từ chối quyền sở hữu đã cũ |
| Checkpoint và retry | Tiếp tục công việc sau gián đoạn |

Ví dụ `daily-report:2026-11-24` có thể là khóa idempotency. Việc kiểm tra và ghi khóa cần được thiết kế cùng thao tác nghiệp vụ tại nơi bảo vệ dữ liệu; một cờ `isLeader` trong RAM không thay thế điều đó.

Fencing đòi hỏi hệ thống đích kiểm tra thứ tự/quyền sở hữu phù hợp và từ chối thao tác từ chủ cũ. Tự sinh một số trong từng Pod hoặc coi `metadata.resourceVersion` là số nguyên fencing dùng chung cho mọi hệ thống không phải thiết kế mặc nhiên đúng.

Vì vậy, leader election giúp giảm sự cạnh tranh và tổ chức trách nhiệm; tính đúng đắn của kết quả vẫn phải được bảo vệ tại lớp nghiệp vụ và lưu trữ.

## 10. Thực hành quan sát hai miền bầu chọn

Mục tiêu là chứng minh một leader ứng dụng không đồng nhất với các leader hạ tầng. Không cần gây lỗi control plane để học sự khác biệt này.

### Điều kiện

- Có ứng dụng `reporting` đã triển khai ba replica trong `sck-lab`, nhãn `app=reporting`.
- Các replica dùng cùng cấu hình bầu chọn ở phần 6.
- ServiceAccount ứng dụng đã được cấp quyền phù hợp với implementation.
- Người quan sát được đọc Pod, log và ConfigMap của ứng dụng.
- Phần xem Lease hệ thống chỉ thực hiện nếu tài khoản vận hành được cấp quyền đó. Managed Kubernetes có thể không công bố đầy đủ control plane cho người dùng.

Các lệnh trong bài dùng PowerShell. Đây là thao tác quan sát trên môi trường đã chuẩn bị, không phải bộ cài đặt cụm hoặc triển khai đầy đủ ứng dụng.

### Bước 1: ghi lại danh sách replica và khóa ứng dụng

~~~powershell
kubectl -n sck-lab get pods -l app=reporting -o wide
kubectl -n sck-lab get configmap reporting-daily-election -o yaml
~~~

Ghi lại:

- Namespace và loại tài nguyên khóa.
- Tên khóa và vai trò `daily-report` đã cấu hình.
- Các trường dữ liệu bầu chọn do implementation thực tế lưu.
- Danh tính ứng viên/leader, đối chiếu với định danh mà thư viện sử dụng.

Không mặc định mọi trường leader ID đều bằng tên Pod. HOSTNAME trong ví dụ log chỉ là thông tin nhận diện instance quan sát được.

Đọc đúng ConfigMap khóa, không tìm Lease của ứng dụng rồi kết luận thất bại nếu đang dùng implementation ConfigMap của bài.

### Bước 2: xem log leadership của từng replica

~~~powershell
$reportingPods = (kubectl -n sck-lab get pods -l app=reporting -o json | ConvertFrom-Json).items.metadata.name

foreach ($podName in $reportingPods) {
    kubectl -n sck-lab logs $podName --prefix --since=10m --tail=200
}
~~~

Tìm `APPLICATION_LEADERSHIP_GRANTED` và `APPLICATION_LEADERSHIP_REVOKED`. Nếu log khởi động đã nằm ngoài khoảng đọc, điều chỉnh thời gian hoặc xem hệ thống log tập trung.

Hai Pod từng có log granted ở hai thời điểm khác nhau không chứng minh có hai leader đồng thời. Cần đặt chúng lên cùng dòng thời gian và xem quá trình chuyển quyền.

Ngược lại, chỉ đọc được log của một Pod không chứng minh các Pod khác không thực hiện tác vụ. Quan sát đầy đủ các replica và kết quả công việc mới giúp đánh giá đúng.

### Bước 3: quan sát Lease control plane bằng quyền vận hành

Nếu có quyền đọc:

~~~powershell
kubectl -n kube-system get leases.coordination.k8s.io -o custom-columns='NAME:.metadata.name,HOLDER:.spec.holderIdentity,RENEW:.spec.renewTime,DURATION:.spec.leaseDurationSeconds'
~~~

Xác định các Lease thực sự thuộc scheduler/controller manager theo cấu hình cụm. Không coi toàn bộ dòng trong namespace `kube-system` là khóa cùng một cuộc bầu chọn.

Nếu có các tên thông thường, có thể đọc riêng:

~~~powershell
kubectl -n kube-system get lease kube-scheduler -o yaml
kubectl -n kube-system get lease kube-controller-manager -o yaml
~~~

Nếu tài nguyên không tồn tại hoặc bị từ chối đọc, kết luận phù hợp là **chưa quan sát được qua tài khoản và giao diện này**. Điều đó không chứng minh thành phần không có cơ chế HA hoặc không có leader election.

Không cần cấp quyền sửa các Lease này cho ứng dụng để hoàn thành bài học.

### Bước 4: đối chiếu bằng một bảng thời gian

| Mốc | Leader daily-report | Holder scheduler | Holder controller manager | Điều kiện quan sát |
| --- | --- | --- | --- | --- |
| Ban đầu | Điền từ khóa và log | Điền nếu được phép xem | Điền nếu được phép xem | Cụm hoạt động ổn định |
| Sau thay đổi replica ứng dụng trong lab | Điền quan sát mới | Điền quan sát mới | Điền quan sát mới | Không cố ý thay đổi control plane |
| Sau khi hệ thống ổn định | Điền quan sát mới | Điền quan sát mới | Điền quan sát mới | Kiểm tra tác vụ nghiệp vụ |

Trong một bài kiểm tra chuyển quyền ứng dụng đã được chuẩn bị, có thể dừng có kiểm soát replica đang giữ leadership rồi theo dõi replica khác tiếp nhận. Không cần dừng scheduler, sửa khóa hệ thống hoặc tác động vào thành viên etcd.

Kỳ vọng là thay đổi leader ứng dụng không đòi hỏi đổi holder của scheduler/controller manager. Nếu có nhiều thay đổi trùng thời điểm, cần kiểm tra sự kiện hạ tầng thay vì kết luận chúng là cùng một cuộc bầu chọn.

Không áp dụng một thời gian failover cố định từ implementation Lease khác cho cơ chế ConfigMap trong bài. Hãy đo trên phiên bản và cấu hình thực tế.

### Bước 5: kiểm tra ranh giới quyền

Với người vận hành có quyền impersonate:

~~~powershell
$appIdentity = "system:serviceaccount:sck-lab:reporting"

kubectl auth can-i get configmaps/reporting-daily-election -n sck-lab --as=$appIdentity
kubectl auth can-i update configmaps/reporting-daily-election -n sck-lab --as=$appIdentity

kubectl auth can-i update leases.coordination.k8s.io/kube-scheduler -n kube-system --as=$appIdentity
kubectl auth can-i update leases.coordination.k8s.io/kube-controller-manager -n kube-system --as=$appIdentity
~~~

Các quyền trên khóa ứng dụng phải phù hợp thao tác của implementation. Các quyền sửa khóa hệ thống không thuộc nhu cầu của ứng dụng báo cáo và được kỳ vọng trả `no` trong chính sách lab.

Nếu câu trả lời rộng hơn dự định, kiểm tra tổng các binding đã cấp. Đổi `role` của Spring không làm thay đổi quyền RBAC của ServiceAccount.

## 11. Chẩn đoán đúng tầng khi có sự cố

| Hiện tượng | Giả thuyết cần kiểm tra trước | Không nên suy ra ngay |
| --- | --- | --- |
| Cả ba replica đều chạy cùng tác vụ | Mã tác vụ chưa sử dụng leadership hoặc khóa/vai trò không cùng nhóm | Scheduler có nhiều leader |
| Không replica nào nhận leadership | Cấu hình, quyền khóa, credential, API và trạng thái ứng viên | Phải đổi leader etcd |
| Một Pod nhận revoked liên tục | Lỗi API, vòng đời ứng dụng, tranh khóa và implementation | Node đó bị loại khỏi control plane |
| Không lên được Pod thay thế | Lập lịch, tài nguyên, controller và node | Chỉ cần sửa listener Spring |
| API không ghi được khóa, nhiều workload cùng bị ảnh hưởng | Kết nối API hoặc vấn đề hạ tầng dùng chung | Mọi ứng dụng đang cùng tranh một khóa |
| etcd đổi leader nhưng leader ứng dụng giữ nguyên | Bầu chọn etcd đã phục hồi và đường phối hợp ứng dụng chưa mất điều kiện | Listener ứng dụng bị hỏng |
| Hai cụm đều có leader của cùng ứng dụng | Mỗi cụm có khóa và miền API riêng | Kubernetes đang vi phạm tính duy nhất toàn cầu |

Một số câu hỏi hữu ích khi đọc log:

1. Log do process Spring hay thành phần hạ tầng phát?
2. Danh tính leader được nhắc tới là Pod, instance control plane hay thành viên etcd?
3. Đối tượng phối hợp nằm ở namespace nào và thuộc loại tài nguyên nào?
4. Cùng một tên vai trò có đang bị dùng bởi nhiều nhóm ngoài ý muốn không?
5. Có bằng chứng side effect trùng lặp hay mới chỉ có các sự kiện granted ở những thời điểm khác nhau?
6. Sự cố chỉ ảnh hưởng một vai trò hay nhiều đường truy cập API?

Chỉ thấy chữ “leader” trong log chưa đủ xác định phạm vi sự cố.

## 12. Khi nào ứng dụng thật sự cần bầu leader?

Trong phạm vi Spring Cloud Kubernetes, hãy bắt đầu từ yêu cầu công việc, không từ việc có sẵn một dependency.

| Nhu cầu | Hướng suy nghĩ |
| --- | --- |
| API stateless phục vụ song song trên nhiều replica | Thường không cần thêm leader chỉ để xử lý HTTP |
| Một replica điều phối công việc dùng chung | Có thể cần bầu leader hoặc cơ chế điều phối tương đương |
| Công việc đã được hệ thống hàng đợi phân công | Đánh giá cơ chế phân công hiện có trước khi thêm một leader toàn cục |
| Tác vụ cần tránh lặp hiệu ứng | Bảo vệ bằng idempotency/transaction; leadership chưa đủ |
| Cần một điều phối viên cho nhiều cụm | Khóa chỉ trong từng cụm không tự tạo phạm vi toàn cầu |
| Muốn bảo vệ tính sẵn sàng của scheduler/etcd | Đây là thiết kế control plane do nền tảng quản lý |

Việc có ba replica giúp dự phòng process, nhưng không tự quy định replica nào được thực hiện tác vụ độc quyền. Việc chỉ chạy một replica cũng không tạo lời bảo đảm “đúng một lần” khi có restart, retry hoặc kết quả ghi không xác định.

Nếu quyết định dùng leader election, phải xác định rõ cách bắt đầu công việc, cách ngừng nhận công việc mới khi mất quyền và cách bảo vệ thao tác đang dở. Không chạy một tác vụ dài ngay trong listener chỉ để chứng minh đã trở thành leader; nên quản lý vòng đời công việc theo thiết kế ứng dụng.

Quan sát sức khỏe cũng cần tách biệt:

- `Running` cho biết trạng thái Pod theo Kubernetes, không xác nhận quyền điều phối.
- `Ready` cho biết điều kiện nhận traffic đã cấu hình, không tự xác nhận leadership.
- Leadership xác định vai trò đang được framework cấp, không chứng minh tác vụ nghiệp vụ đã hoàn thành.
- Thành công nghiệp vụ cần được xác nhận tại hệ thống xử lý hoặc lưu kết quả.

## 13. Tự kiểm tra bằng tình huống

**Tình huống 1:** Cụm có ba control-plane node và ba replica Spring, mỗi replica có một lịch chạy giống nhau. Đã có HA control plane thì lịch có tự chạy một lần không?  
Không. HA của thành phần hạ tầng không lựa chọn replica chạy tác vụ Spring. Ứng dụng cần cơ chế điều phối phù hợp và bảo vệ kết quả.

**Tình huống 2:** `reporting-b` nhận `OnGrantedEvent`. Có cần ServiceAccount của nó có quyền sửa Lease `kube-scheduler` không?  
Không. Sự kiện chỉ liên quan vai trò ứng dụng. Quyền phối hợp chỉ cần khớp tài nguyên và phạm vi của cơ chế đang dùng.

**Tình huống 3:** Thấy ba Lease công bố danh tính API server trong `kube-system`. Có phải có ba leader Kubernetes không?  
Không. Lease có nhiều mục đích; bản ghi danh tính không phải bằng chứng các instance đang cùng tranh một quyền điều phối duy nhất.

**Tình huống 4:** Leader cũ mất kết nối API nhưng vẫn kết nối được cơ sở dữ liệu. Có thể mặc định nó không ghi thêm dữ liệu không?  
Không. Cần xem hành vi implementation, vòng đời tác vụ và cơ chế bảo vệ ở hệ thống đích. Một bản ghi khóa không tự chặn process cũ.

**Tình huống 5:** Mỗi cụm có một ứng dụng cùng tên và cùng tên ConfigMap khóa. Có thể có hai leader cho cùng công việc toàn cầu không?  
Có. Nếu chỉ phối hợp trong API của từng cụm, đó là hai miền bầu chọn độc lập. Yêu cầu độc quyền toàn cầu cần thiết kế phạm vi phối hợp tương ứng.

Hoàn thành bài học khi bạn mô tả được **leader của việc gì, giữa những ứng viên nào, trên khóa và phạm vi nào**, đồng thời chỉ ra được phần trách nhiệm thuộc ứng dụng và phần thuộc nền tảng Kubernetes.
