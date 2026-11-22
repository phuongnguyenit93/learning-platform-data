# Triển khai trên Kubernetes với operator và giới hạn trách nhiệm

Triển khai PostgreSQL trên Kubernetes bằng operator giúp quản lý database theo cách khai báo: người vận hành mô tả trạng thái mong muốn trong một tài nguyên Kubernetes, còn operator theo dõi và thực hiện các bước cần thiết để đưa hệ thống về trạng thái đó. Cách làm này có thể tự động hóa việc tạo instance, cấu hình replica, failover, backup hoặc nâng cấp, tùy khả năng của operator được chọn.

Operator không thay thế toàn bộ vai trò của DBA, đội nền tảng hay đội phát triển ứng dụng. Kubernetes chịu trách nhiệm điều phối container và tài nguyên hạ tầng; operator hiểu vòng đời PostgreSQL trong phạm vi đã triển khai; DBA và các đội sản phẩm vẫn phải quyết định chính sách dữ liệu, mục tiêu khôi phục, tải ứng dụng và cách xử lý sự cố. Phân định rõ các ranh giới này là điều kiện để hệ thống vận hành an toàn.

## 1. Operator là gì và hoạt động như thế nào?

Trong Kubernetes, operator thường gồm hai thành phần chính:

- **Custom Resource Definition (CRD):** mở rộng Kubernetes API bằng một loại tài nguyên mới. Ví dụ, một operator PostgreSQL có thể định nghĩa tài nguyên đại diện cho một cụm database.
- **Controller:** tiến trình theo dõi các tài nguyên đó và thực hiện vòng lặp reconcile để đưa trạng thái thực tế gần với trạng thái mong muốn.

Người dùng tạo một custom resource (CR) để mô tả cấu hình. Controller nhận sự kiện khi CR thay đổi, đọc trạng thái hiện tại của cluster, so sánh với cấu hình mong muốn rồi tạo hoặc cập nhật các đối tượng cần thiết. Những đối tượng đó có thể gồm Pod, StatefulSet, PVC, Service, Secret, ConfigMap, Job hoặc tài nguyên riêng của operator.

Luồng khái quát:

~~~mermaid
flowchart TD
    A[Người vận hành khai báo PostgreSQL CR] --> B[Kubernetes API lưu trạng thái mong muốn]
    B --> C[Operator theo dõi thay đổi]
    C --> D[Đọc trạng thái thực tế]
    D --> E[Reconcile: tạo hoặc điều chỉnh tài nguyên]
    E --> F[Pod, PVC, Service, backup job...]
    F --> G[Operator quan sát kết quả]
    G -->|Chưa hội tụ| D
    G -->|Đã hội tụ| H[Cập nhật status và condition]
~~~

Vòng lặp reconcile có tính lặp lại. Controller có thể nhận cùng một sự kiện nhiều lần, khởi động lại hoặc xử lý lại sau khi một tài nguyên được sửa. Vì vậy, thao tác reconcile cần an toàn khi lặp và dựa trên trạng thái thực tế, thay vì giả định mỗi sự kiện chỉ đến đúng một lần.

Cần phân biệt ba khái niệm:

- **CRD** định nghĩa kiểu tài nguyên và schema của nó.
- **CR** là một đối tượng cụ thể do người dùng khai báo, chứa cấu hình cho một cụm database.
- **Operator** là phần mềm điều khiển, đọc CR và quản lý các tài nguyên liên quan.

Một CR tồn tại không đồng nghĩa database đã sẵn sàng. PVC có thể đang chờ volume, Pod có thể chưa được schedule, database có thể đang khởi tạo hoặc replica chưa bắt kịp WAL. Hãy đọc `status`, `conditions`, event và log của operator để biết tiến trình thực tế.

## 2. Operator quản lý được những gì?

Mỗi PostgreSQL operator có phạm vi và mức độ tự động hóa khác nhau. Các khả năng thường gặp gồm:

| Nhóm chức năng | Operator có thể đảm nhiệm | Điều cần xác minh |
|---|---|---|
| Khởi tạo cụm | Tạo PostgreSQL instance, cấu hình ban đầu, user và database theo schema được hỗ trợ | Cách bootstrap, xử lý secret và quyền sở hữu tài nguyên |
| Replication | Cấu hình primary/standby, theo dõi trạng thái replica | Đồng bộ hay bất đồng bộ, cách phát hiện replica trễ |
| HA và failover | Chọn primary mới khi primary hiện tại lỗi, cập nhật endpoint | Cơ chế fencing, điều kiện failover, nguy cơ mất dữ liệu |
| Storage | Tạo PVC, gắn volume, mở rộng dung lượng nếu hỗ trợ | CSI driver, StorageClass, giới hạn mở rộng và khôi phục volume |
| Backup | Lên lịch base backup, lưu WAL, quản lý retention hoặc restore job | Đích lưu trữ, mã hóa, PITR và quy trình kiểm thử restore |
| Cấu hình | Áp dụng tham số PostgreSQL, tài nguyên CPU/RAM | Tham số nào cần restart, phạm vi cấu hình được hỗ trợ |
| Nâng cấp | Điều phối thay đổi image hoặc phiên bản PostgreSQL | Hỗ trợ minor/major upgrade, extension và khả năng rollback |
| Quan sát | Xuất metric, event, log hoặc trạng thái cluster | Tích hợp hệ thống monitoring và cảnh báo của tổ chức |

Không nên suy ra một operator có đầy đủ các khả năng trên chỉ từ tên gọi “PostgreSQL Operator”. Hãy đọc tài liệu đúng phiên bản, schema CRD, ma trận tương thích và giới hạn của sản phẩm. Một số operator chỉ quản lý vòng đời cơ bản; một số khác cung cấp thêm backup, connection pooler hoặc cơ chế nâng cấp.

Operator cũng không tự động làm cho một database trở nên có tính sẵn sàng cao. HA phụ thuộc topology, storage, mạng, phân bố node, replication, cơ chế chọn primary, fencing và khả năng ứng dụng kết nối lại. Nếu một trong các lớp này không đáp ứng yêu cầu, việc có operator vẫn không bảo đảm dịch vụ liên tục.

## 3. Kiến trúc triển khai PostgreSQL trên Kubernetes

Một cụm PostgreSQL thường có một primary nhận ghi và một hoặc nhiều standby nhận WAL từ primary. Tùy cấu hình, standby có thể phục vụ truy vấn đọc. Operator theo dõi các instance và phối hợp các hành động trong vòng đời cụm.

Các thành phần thường gặp:

- **PostgreSQL Pod:** chạy tiến trình PostgreSQL. Mỗi instance cần một định danh và vòng đời riêng.
- **PersistentVolumeClaim (PVC):** yêu cầu dung lượng lưu trữ bền vững cho dữ liệu của instance. Pod có thể được tạo lại nhưng dữ liệu phải được gắn lại đúng volume.
- **PersistentVolume (PV):** tài nguyên lưu trữ được Kubernetes cấp phát tĩnh hoặc động thông qua StorageClass.
- **Service:** cung cấp địa chỉ ổn định để ứng dụng kết nối. Operator có thể tạo endpoint riêng cho primary và replica.
- **Backup target:** thường là object storage hoặc hệ thống lưu trữ ngoài cluster để giữ base backup và WAL.
- **Monitoring:** thu thập metric từ PostgreSQL, exporter, Pod, node và operator.

Ví dụ kiến trúc logic:

~~~text
Ứng dụng
   |
   +---- Service ghi ----> Primary PostgreSQL
   |                          |
   |                          +---- WAL replication ----> Standby 1
   |                          |
   |                          +---- WAL replication ----> Standby 2
   |
   +---- Service đọc ----> Standby (nếu chính sách cho phép)

Operator
   +---- Theo dõi CR và trạng thái instance
   +---- Quản lý Pod, PVC, Service và cấu hình
   +---- Điều phối failover, backup, restore theo khả năng hỗ trợ

Backup target ngoài cluster
   +---- Base backup
   +---- WAL archive
~~~

Sơ đồ trên chỉ mô tả một topology phổ biến. Operator có thể dùng StatefulSet, Pod riêng, sidecar, agent hoặc thành phần điều phối khác. Không nên phụ thuộc vào tên Pod hay tên StatefulSet nội bộ nếu operator không công bố chúng như API ổn định. Ứng dụng nên kết nối qua Service hoặc endpoint được operator hỗ trợ.

### Primary, standby và đường kết nối

Ứng dụng ghi cần kết nối đến endpoint đại diện cho primary. Endpoint đọc có thể phân phối truy vấn đến standby, nhưng chỉ nên sử dụng khi ứng dụng chấp nhận độ trễ replication và semantics đọc tương ứng. Không phải mọi truy vấn đọc đều an toàn khi chuyển sang replica: một truy vấn ngay sau khi ghi có thể không thấy thay đổi vừa commit nếu replica chưa replay WAL đến vị trí cần thiết.

Khi failover, vai trò primary thay đổi. Operator có thể cập nhật endpoint hoặc nhãn chọn Pod, nhưng connection TCP hiện có thường không tự chuyển sang server mới. Connection pool cần phát hiện connection lỗi, loại bỏ connection cũ và tạo kết nối mới. Ứng dụng cần retry có kiểm soát đối với thao tác có thể retry, đặc biệt lưu ý kết quả của transaction có thể không rõ ràng nếu kết nối đứt đúng lúc commit.

### Chống split-brain

Split-brain xảy ra khi hai instance cùng tin rằng mình là primary và cùng nhận ghi. Đây là nguy cơ nghiêm trọng vì hai nhánh dữ liệu có thể phân kỳ. Một giải pháp HA phải có cơ chế bảo đảm primary cũ không tiếp tục nhận ghi khi primary mới được thăng cấp. Cơ chế này thường được gọi là fencing hoặc leader coordination và có thể liên quan đến trạng thái điều phối, quyền truy cập storage hoặc hành động cô lập instance.

Không tự xây dựng failover chỉ bằng cách thay đổi nhãn Pod hay Service. Việc đổi endpoint mà không bảo đảm primary cũ đã bị vô hiệu hóa có thể tạo split-brain. Hãy hiểu rõ cơ chế failover/fencing của operator và kiểm thử trong môi trường thử nghiệm trước khi dùng production.

## 4. Lập kế hoạch trước khi cài operator

Trước khi tạo cluster, cần xác định các yêu cầu vận hành:

**Mục tiêu dữ liệu và phục hồi.** Xác định RPO (mức mất dữ liệu tối đa chấp nhận được) và RTO (thời gian tối đa để khôi phục dịch vụ). RPO ảnh hưởng đến chính sách replication và backup; RTO ảnh hưởng đến topology, quy trình failover, restore và năng lực trực vận hành.

**Tải và dung lượng.** Ước lượng số kết nối đồng thời, TPS, tỷ lệ đọc/ghi, kích thước dữ liệu, tốc độ tăng trưởng, dung lượng WAL và nhu cầu IOPS. Tính cả không gian cho backup tạm, index build, vacuum và các đợt tăng tải.

**Phiên bản và tương thích.** Chọn phiên bản PostgreSQL, extension, client driver và operator có ma trận tương thích phù hợp. Xác định chu kỳ cập nhật minor, kế hoạch major upgrade và cách xử lý extension native.

**Topology và failure domain.** Quyết định số instance, vùng sẵn sàng, node pool, anti-affinity, topology spread và yêu cầu đồng bộ replication. Ba Pod trên cùng một node không tương đương ba bản sao ở ba failure domain độc lập.

**Storage.** Chọn StorageClass và CSI driver đáp ứng độ bền, độ trễ, IOPS, khả năng mở rộng và chính sách snapshot. Xác minh volume có thể được gắn lại sau khi Pod chuyển node và hiểu các ràng buộc theo zone.

**Bảo mật và vận hành.** Xác định namespace, RBAC, service account, network policy, TLS, nơi lưu secret, quyền truy cập backup target, monitoring, cảnh báo và người chịu trách nhiệm trực.

## 5. Cài đặt và quản lý vòng đời operator

Operator thường được cài trong namespace riêng hoặc namespace dùng chung cho một nhóm workload. Cách cài đặt tùy dự án: manifest, Helm chart, Operator Lifecycle Manager hoặc quy trình đóng gói nội bộ.

Trước khi cài, kiểm tra:

- Phiên bản operator tương thích với phiên bản Kubernetes và PostgreSQL dự kiến.
- CRD sẽ được cài hoặc cập nhật có schema tương thích với các CR đang tồn tại.
- Quyền RBAC chỉ đủ để operator quản lý những tài nguyên cần thiết.
- Phạm vi watch: một namespace hay toàn cluster.
- Số replica của controller và cách bảo đảm controller không xử lý xung đột.
- Quy trình nâng cấp, rollback và khôi phục CRD/webhook.
- Image registry, image signature, nguồn cung cấp và chính sách quét lỗ hổng.

Operator là một workload quan trọng. Nếu controller dừng, database đang chạy thường không tự dừng chỉ vì controller không hoạt động, nhưng các thao tác reconcile, failover hoặc backup mà operator phụ trách có thể bị gián đoạn. Vì vậy, cần giám sát chính operator, webhook và các thành phần phụ trợ của nó.

Không xóa CRD chỉ để “cài lại cho sạch”. Xóa CRD có thể xóa các custom resource thuộc loại đó và làm mất đối tượng điều khiển cluster. Cần hiểu rõ hành vi uninstall, finalizer và chính sách giữ hoặc xóa PVC trước khi gỡ operator.

## 6. Khai báo cụm database

Người vận hành thường tạo một custom resource để mô tả cụm PostgreSQL. Tên loại tài nguyên, API version và cấu trúc `spec` phụ thuộc operator.

Ví dụ sau là **YAML minh họa khái niệm**, không phải manifest dùng trực tiếp cho một operator cụ thể:

~~~yaml
apiVersion: database.example.io/v1
kind: PostgreSQLCluster
metadata:
  name: orders-db
  namespace: data
spec:
  instances: 3
  postgres:
    version: "major-version-supported-by-operator"
    storage:
      size: 200Gi
      storageClass: database-ssd
    resources:
      requests:
        cpu: "2"
        memory: 8Gi
      limits:
        memory: 8Gi
  backup:
    enabled: true
    destination: object-storage-reference
~~~

Trong tài nguyên thật, các trường có thể mang tên khác, được lồng theo cấu trúc khác hoặc yêu cầu thêm cấu hình cho user, database, replication, TLS, backup credential và monitoring. Luôn dùng schema và ví dụ của đúng phiên bản operator; Kubernetes API server sẽ từ chối field không hợp lệ hoặc operator có thể bỏ qua cấu hình không được hỗ trợ.

Khi áp dụng CR, theo dõi quá trình hội tụ:

~~~bash
kubectl apply -f postgres-cluster.yaml

kubectl get <postgres-resource> -n data
kubectl describe <postgres-resource> orders-db -n data
kubectl get pods,pvc,svc -n data
kubectl get events -n data --sort-by=.lastTimestamp
~~~

`<postgres-resource>` là tên resource plural do CRD của operator định nghĩa. Thay placeholder này bằng tên thật lấy từ CRD hoặc tài liệu operator.

Không coi `kubectl apply` thành công là bằng chứng database đã sẵn sàng. Cần xác nhận:

1. CR được API server chấp nhận và operator nhận biết.
2. PVC được cấp phát và gắn thành công.
3. Pod đã schedule, khởi động và vượt readiness probe.
4. PostgreSQL chấp nhận kết nối.
5. Primary/standby có vai trò đúng và replication đạt trạng thái mong muốn.
6. Service trỏ đến đúng instance.
7. Backup đầu tiên thành công và có thể kiểm tra metadata.
8. Metric và log được thu thập.

## 7. Storage và tính bền vững của dữ liệu

Database cần storage bền vững. Container filesystem thuộc vòng đời Pod và không phải nơi lưu dữ liệu PostgreSQL lâu dài. Operator thường yêu cầu PVC cho từng instance; PVC được bind vào PV thông qua StorageClass hoặc cấp phát tĩnh.

Khi chọn StorageClass, cần xem xét:

- Độ trễ đọc/ghi và IOPS ở tải thực tế.
- Throughput tuần tự, đặc biệt khi ghi WAL hoặc chạy backup/restore.
- Cách CSI driver xử lý detach/attach khi Pod được schedule sang node khác.
- Giới hạn volume theo node và vùng sẵn sàng.
- Chính sách reclaim khi PVC bị xóa.
- Hỗ trợ mở rộng volume và giới hạn filesystem.
- Hành vi snapshot, clone và restore của nhà cung cấp storage.

`ReadWriteOnce` thường có nghĩa volume được mount read-write bởi một node tại một thời điểm; nó không phải cam kết volume chỉ được một process sử dụng. Quy tắc access mode và khả năng attach thực tế còn phụ thuộc CSI driver. Không tự sửa access mode hoặc gắn chung một data volume cho nhiều PostgreSQL instance nếu kiến trúc operator không hỗ trợ.

Việc xóa Pod không nhất thiết xóa PVC, nhưng chính sách đó phụ thuộc owner reference, finalizer và cấu hình operator. Hãy xác minh hành vi khi xóa CR, scale down, thay instance hoặc gỡ operator. Cần biết rõ trường hợp nào giữ volume và trường hợp nào có thể xóa dữ liệu.

Snapshot của volume có thể hữu ích cho backup hoặc clone môi trường, nhưng snapshot filesystem đơn thuần không mặc nhiên tương đương backup PostgreSQL nhất quán. Cần dùng cơ chế backup được PostgreSQL/operator hỗ trợ, phối hợp checkpoint/WAL hoặc quy trình snapshot nhất quán. Đối với yêu cầu PITR, cần bảo đảm có base backup hợp lệ và chuỗi WAL liên tục.

## 8. High availability và giới hạn của replication

Một topology nhiều instance giúp giảm thời gian gián đoạn khi một instance hoặc node gặp lỗi, nhưng phải phân biệt:

- **Replication:** truyền thay đổi dữ liệu từ primary đến standby.
- **Failover:** chuyển vai trò primary sang standby được chọn.
- **Fencing:** bảo đảm primary cũ không tiếp tục nhận ghi.
- **Routing:** đưa kết nối mới đến endpoint đúng sau khi vai trò thay đổi.
- **Recovery:** đưa instance lỗi trở lại cụm và đồng bộ dữ liệu.

Replication bất đồng bộ có thể mất một phần transaction đã commit trên primary nhưng chưa đến standby tại thời điểm primary bị mất. Replication đồng bộ có thể giảm nguy cơ mất dữ liệu theo cấu hình, đổi lại transaction commit có thể phải chờ standby xác nhận và chịu ảnh hưởng khi standby hoặc mạng chậm. Cần hiểu chính xác chế độ sync, số standby được yêu cầu và hành vi khi không đủ standby.

Replica không phải backup. Một câu lệnh xóa nhầm, dữ liệu bị mã hóa bởi mã độc hoặc lỗi logic được ghi trên primary có thể được replication sang standby. Backup độc lập và khả năng PITR vẫn cần thiết.

Kubernetes cung cấp cơ chế schedule và khởi động lại Pod, nhưng không hiểu đầy đủ trạng thái transaction hoặc khả năng an toàn khi thăng cấp một standby. Operator phải phối hợp logic database để thực hiện failover đúng cách. Đừng tự động xóa Pod primary chỉ vì readiness probe thất bại nếu chưa hiểu operator dùng tín hiệu đó như thế nào.

Để tăng khả năng chịu lỗi, cân nhắc:

- Phân bố instance trên các node và zone khác nhau bằng anti-affinity hoặc topology spread.
- Có đủ node và tài nguyên dự phòng để Pod có thể được schedule sau sự cố.
- Dùng PodDisruptionBudget (PDB) phù hợp để giới hạn gián đoạn do eviction tự nguyện.
- Kiểm tra disruption do drain node, nâng cấp cluster và autoscaling.
- Kiểm thử node failure, network partition, replica lag và mất primary trong môi trường staging.
- Đo thời gian phát hiện lỗi, thời gian failover, thời gian kết nối lại và mức dữ liệu có thể mất.

PDB chủ yếu giới hạn eviction tự nguyện thông qua Kubernetes Eviction API. Nó không ngăn được node crash, không tự tạo replica mới và không thay thế cơ chế failover của operator.

## 9. Backup, WAL archive và phục hồi theo thời điểm

Một hệ thống production cần chính sách backup độc lập với replication. Một phương án phổ biến là tạo base backup định kỳ và lưu WAL liên tục đến object storage hoặc kho lưu trữ ngoài cluster. Khi có base backup và chuỗi WAL cần thiết, PostgreSQL có thể phục hồi đến một thời điểm trong phạm vi dữ liệu đã lưu.

Chính sách backup cần xác định:

- Tần suất base backup và giới hạn thời gian hoàn thành.
- WAL archive có liên tục hay không và cảnh báo khi archive bị gián đoạn.
- Retention, thời hạn lưu, bản sao ngoài vùng hoặc ngoài tài khoản cloud.
- Mã hóa khi truyền và khi lưu, quyền truy cập và quản lý credential.
- Tính bất biến hoặc bảo vệ backup trước thao tác xóa ngoài ý muốn.
- Mục tiêu RPO/RTO và dung lượng cần thiết khi restore.
- Người có quyền khởi chạy restore và quy trình phê duyệt.

Operator có thể tạo backup job và quản lý cấu hình archive, nhưng đội vận hành vẫn phải xác minh backup thực sự có thể dùng. Một job có trạng thái thành công không thay thế được bài kiểm tra restore.

Hãy tổ chức diễn tập khôi phục định kỳ:

1. Chọn một backup và xác định mốc thời gian cần khôi phục.
2. Tạo môi trường restore cô lập, tránh ghi đè production.
3. Khôi phục base backup và replay WAL đến mốc yêu cầu.
4. Kiểm tra database khởi động, extension được nạp và dữ liệu nghiệp vụ nhất quán.
5. Đo thời gian hoàn tất, lượng dữ liệu mất và các bước thủ công.
6. Ghi lại lỗi, cập nhật runbook và thực hiện lại sau khi sửa.

Khi xóa cluster hoặc namespace, phải xác định backup target nằm ngoài phạm vi bị xóa và có retention độc lập. Không giả định PVC còn tồn tại sau khi xóa CR hoặc rằng object storage sẽ tự giữ dữ liệu theo mong muốn.

## 10. Tài nguyên, cấu hình và hiệu năng

Kubernetes scheduler dùng resource requests để quyết định Pod có thể chạy trên node nào. CPU limit có thể gây throttling khi workload cần nhiều CPU hơn giới hạn; memory limit có thể dẫn đến OOM kill. Với database, các lần restart và throttling bất ngờ có thể ảnh hưởng latency, replication lag và thời gian recovery.

Cần dự trù:

- CPU và RAM cho workload bình thường, peak và maintenance.
- Dung lượng page cache của hệ điều hành, shared buffers và bộ nhớ backend.
- Số kết nối đồng thời và chi phí bộ nhớ theo connection.
- WAL generation, checkpoint, autovacuum và truy vấn dài.
- Dung lượng tạm cho sort/hash, index build và backup.
- Tài nguyên dự phòng để chạy replica hoặc khôi phục sau node failure.

Không đặt `work_mem` quá cao chỉ vì muốn tăng tốc sort. Tham số này có thể được dùng nhiều lần trong một truy vấn và đồng thời trên nhiều session; tổng bộ nhớ tiêu thụ có thể lớn hơn nhiều lần giá trị cấu hình. `max_connections` cao cũng làm tăng overhead. Connection pooler có thể giảm số kết nối trực tiếp đến PostgreSQL, nhưng phải được cấu hình phù hợp với session state, prepared statement và transaction pooling.

Các tham số PostgreSQL nên được quản lý qua cơ chế cấu hình mà operator hỗ trợ. Một số tham số có thể reload, một số cần restart. Không chỉnh trực tiếp file cấu hình trong container đang chạy nếu operator sẽ ghi đè hoặc không theo dõi thay đổi đó. Hãy lưu cấu hình mong muốn trong nguồn khai báo được quản lý.

Theo dõi ít nhất CPU, memory, disk latency, disk usage, WAL rate, checkpoint, autovacuum, active connection, lock wait, replication lag, transaction age, dead tuple và lỗi kết nối. Từ đó mới có thể phân biệt thiếu tài nguyên Kubernetes với vấn đề query, index hoặc cấu hình PostgreSQL.

## 11. Bảo mật và phân quyền

Database chứa dữ liệu quan trọng, vì vậy bảo mật phải được thiết kế ở cả lớp Kubernetes và PostgreSQL.

**RBAC và service account.** Operator cần quyền tạo và cập nhật tài nguyên trong phạm vi của nó. Tránh cấp cluster-admin nếu không có yêu cầu rõ ràng. Tách quyền quản trị cluster, quyền quản lý database và quyền truy cập dữ liệu ứng dụng.

**Secret.** Mật khẩu, chứng chỉ TLS và credential object storage nên được lưu trong Secret hoặc hệ thống quản lý secret được tổ chức phê duyệt. Secret Kubernetes được base64 encode không có nghĩa dữ liệu đã được mã hóa. Cần bật encryption at rest cho Kubernetes datastore, giới hạn quyền đọc Secret, xoay vòng credential và tránh đưa secret vào Git hoặc log.

**Mạng.** Dùng NetworkPolicy hoặc cơ chế tương đương để giới hạn nguồn có thể kết nối cổng PostgreSQL, cổng replication, metrics và webhook. Chỉ mở kết nối cần thiết giữa operator, database, backup target và ứng dụng.

**TLS.** Mã hóa kết nối client và replication khi yêu cầu bảo mật cần thiết. Quản lý CA, vòng đời chứng chỉ, xác minh hostname và quy trình xoay chứng chỉ. Không tắt xác minh TLS để khắc phục nhanh lỗi certificate.

**Pod và image.** Dùng image từ nguồn tin cậy, pin phiên bản hoặc digest theo chính sách, quét lỗ hổng, hạn chế quyền Linux, filesystem và capability. Áp dụng Pod Security Standards hoặc chính sách tương đương. Không chạy container với quyền root hoặc privileged nếu không có lý do kỹ thuật được phê duyệt.

**Tài khoản database.** Tạo role riêng cho ứng dụng, migration, backup và quản trị. Cấp quyền tối thiểu cần thiết; không dùng superuser cho kết nối ứng dụng thông thường. Ghi nhận và rà soát quyền định kỳ.

## 12. Nâng cấp operator và PostgreSQL

Có ít nhất hai vòng đời phiên bản riêng:

1. **Phiên bản operator:** thay đổi controller, CRD, webhook và logic reconcile.
2. **Phiên bản PostgreSQL:** thay đổi server database, catalog, extension và định dạng dữ liệu ở major version.

Nâng cấp operator không đồng nghĩa nâng cấp PostgreSQL. Ngược lại, nâng phiên bản PostgreSQL có thể yêu cầu operator mới hỗ trợ image, bootstrap hoặc quy trình migration tương ứng.

Trước khi nâng cấp:

- Đọc release note và ma trận tương thích của operator, Kubernetes, PostgreSQL và extension.
- Xác định CRD có thay đổi schema hay conversion webhook không.
- Sao lưu CR và cấu hình cần thiết; xác minh backup dữ liệu.
- Thử trên bản sao staging với kích thước dữ liệu và extension tương tự production.
- Đo downtime, thời gian catch-up, dung lượng tạm và khả năng rollback.
- Xác định endpoint ứng dụng, connection pool và lịch schema migration.

Minor upgrade thường có quy trình đơn giản hơn nhưng vẫn cần kiểm tra extension, image và khả năng restart. Major upgrade có thể cần `pg_upgrade`, logical replication hoặc phương thức migration khác tùy operator. Không được giả định đổi trường version trong CR là đủ để chuyển đổi data directory.

Rollback một major upgrade thường phức tạp vì data directory sau nâng cấp có thể không tương thích ngược. Phải chuẩn bị phương án restore hoặc chuyển traffic về cụm cũ, đồng thời xác định cách đồng bộ các ghi phát sinh trong thời gian cutover.

Nâng cấp Kubernetes node hoặc CSI driver cũng có thể gây gián đoạn database. Cần kiểm tra PDB, khả năng reschedule, volume attach, anti-affinity và thứ tự drain node. Không tiến hành bảo trì đồng thời trên tất cả failure domain của cụm.

## 13. Quan sát và xử lý sự cố

Khi database không sẵn sàng, cần xác định sự cố nằm ở lớp nào: CR/operator, Kubernetes scheduling, storage, network, PostgreSQL hay ứng dụng.

Các điểm quan sát:

| Lớp | Nguồn quan sát | Câu hỏi cần trả lời |
|---|---|---|
| Custom resource | `kubectl get`, `describe`, status/conditions | Operator đã nhận cấu hình chưa? Condition nào đang lỗi? |
| Operator | Controller log, event, webhook log | Reconcile thất bại ở bước nào? Có quyền hoặc schema error không? |
| Kubernetes | Pod status, event, node condition | Pod pending, crash loop, OOM hay bị eviction? |
| Storage | PVC/PV, CSI event, volume metric | Volume đã bind/attach/mount chưa? Có hết dung lượng hoặc lỗi I/O không? |
| PostgreSQL | Server log, `pg_stat_activity`, replication view | Database có nhận kết nối? Có lock, checkpoint hoặc replica lag bất thường không? |
| Ứng dụng | Connection pool, timeout, SQLSTATE, request trace | Kết nối đang đi đúng endpoint? Retry có an toàn không? |

Một số lệnh hỗ trợ điều tra:

~~~bash
kubectl get pods -n data -o wide
kubectl describe pod <postgres-pod> -n data
kubectl logs <operator-pod> -n operator-namespace
kubectl logs <postgres-pod> -n data
kubectl get pvc -n data
kubectl get events -n data --sort-by=.lastTimestamp
~~~

Tên namespace, Pod và container cần thay bằng giá trị của môi trường. Nếu Pod có nhiều container, chỉ rõ container cần xem bằng tùy chọn `-c`.

Từ một kết nối PostgreSQL có quyền phù hợp, có thể kiểm tra vai trò và hoạt động:

~~~sql
SELECT pg_is_in_recovery();

SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE datname = current_database();

SELECT *
FROM pg_stat_replication;
~~~

`pg_is_in_recovery()` trả về `false` trên primary đang hoạt động và `true` khi instance ở chế độ recovery/standby. `pg_stat_replication` cung cấp thông tin về các standby đang kết nối với primary; trên standby, view này không thay thế việc kiểm tra trạng thái replay WAL.

Khi có sự cố, không vội xóa Pod, PVC hoặc CR. Trước hết thu thập event, log, condition, trạng thái volume và vai trò database. Xóa một Pod có thể làm mất bằng chứng hoặc kích hoạt hành động mà operator không mong muốn. Xóa PVC có thể làm mất dữ liệu. Nếu cần can thiệp thủ công, phải theo runbook của operator và có người sở hữu quyết định.

## 14. Ranh giới trách nhiệm giữa các đội

Một hệ thống vận hành tốt cần ghi rõ ai chịu trách nhiệm cho từng lớp. Bảng dưới đây là mô hình tham khảo; tổ chức có thể phân công khác, nhưng không nên để các trách nhiệm quan trọng không có chủ sở hữu.

| Chủ thể | Trách nhiệm chính | Không nên mặc định thuộc phạm vi |
|---|---|---|
| Kubernetes control plane và node platform | API, scheduler, node, runtime, networking nền tảng, policy và năng lực cluster | Tính đúng đắn của transaction, schema hay query PostgreSQL |
| Storage/Cloud platform | CSI, volume durability, hiệu năng và giới hạn của storage, object storage | Chính sách backup database, PITR và xác nhận dữ liệu nghiệp vụ sau restore |
| PostgreSQL operator | Reconcile tài nguyên theo CR; quản lý vòng đời, replication, failover, backup hoặc upgrade trong phạm vi được hỗ trợ | Tự quyết định RPO/RTO, phân tích query, mô hình dữ liệu và mọi quy trình nghiệp vụ |
| DBA/Data platform | Thiết kế database, HA/backup policy, tham số, quyền database, nâng cấp, restore test và runbook dữ liệu | Vận hành toàn bộ Kubernetes node hoặc thay thế trách nhiệm của đội ứng dụng |
| Application team | Connection pool, timeout, retry, idempotency, query, migration schema và xử lý lỗi kết nối | Tự ý thay đổi cấu hình cluster hoặc xóa tài nguyên database |
| Security/Compliance | Chính sách truy cập, mã hóa, audit, retention và yêu cầu tuân thủ | Thay thế việc kiểm thử khôi phục và vận hành kỹ thuật hàng ngày |

### Operator chịu trách nhiệm đến đâu?

Operator có thể tự động hóa những hành động đã được thiết kế và cấu hình: tạo Pod, duy trì replica, thực hiện failover, khởi chạy backup hoặc áp dụng cấu hình. Tuy nhiên, operator không thể tự biết mọi quyết định nghiệp vụ.

Ví dụ, operator có thể phát hiện primary mất kết nối và thăng cấp standby theo chính sách. Nó không thể tự quyết định liệu mất một vài giây dữ liệu có chấp nhận được với hệ thống thanh toán hay không. Quyết định sync replication, RPO và cách xử lý transaction chưa rõ kết quả cần DBA và đội ứng dụng thống nhất.

Operator có thể tạo backup theo lịch, nhưng đội sở hữu dữ liệu phải quyết định retention, yêu cầu lưu trữ ngoài vùng, quyền truy cập và kiểm tra restore. Operator có thể áp dụng resource limit, nhưng việc sizing cần dựa trên workload và quan sát thực tế.

### Kubernetes chịu trách nhiệm đến đâu?

Kubernetes quản lý Pod lifecycle, scheduling, service discovery, resource quota, volume attachment thông qua CSI và các policy của cluster. Kubernetes không tự hiểu một Pod PostgreSQL là primary hay standby, không xác nhận dữ liệu đã replay đủ và không tự bảo đảm transaction không mất khi Pod bị thay thế.

Readiness probe cho biết một Pod có nên nhận traffic theo điều kiện được khai báo hay không. Liveness probe có thể khiến container được restart. Cấu hình probe sai có thể gây restart lặp hoặc loại Pod khỏi Service trong lúc database chỉ đang tải cao. Probe cần phản ánh trạng thái phù hợp với mục đích và phối hợp với cơ chế của operator.

### Đội ứng dụng chịu trách nhiệm đến đâu?

Sau failover, kết nối hiện tại có thể bị ngắt. Ứng dụng phải có timeout hợp lý, pool có khả năng loại connection hỏng và retry an toàn. Một lỗi mạng tại thời điểm commit không cho biết chắc transaction đã commit hay chưa. Những thao tác không idempotent cần cơ chế định danh yêu cầu hoặc kiểm tra trạng thái trước khi retry để tránh ghi trùng.

Đội ứng dụng cũng sở hữu query, index theo workload, migration schema và tương thích driver. Operator không tự tối ưu một truy vấn chậm hoặc sửa logic transaction gây lock contention.

## 15. Các tình huống dễ nhầm lẫn

**Pod restart được xem là database đã phục hồi.** Pod có thể ở trạng thái Running nhưng PostgreSQL chưa sẵn sàng nhận traffic, đang replay WAL hoặc chưa đồng bộ replica. Cần kiểm tra readiness, vai trò database và trạng thái replication.

**Có ba replica nên không cần backup.** Replication sao chép cả thao tác sai và hỏng dữ liệu logic. Backup độc lập, WAL archive và restore test vẫn bắt buộc theo mục tiêu dữ liệu.

**PDB bảo đảm HA.** PDB chỉ điều tiết một số eviction tự nguyện. Nó không xử lý primary crash, split-brain, lỗi storage hay mất cả zone.

**PVC tồn tại nghĩa dữ liệu an toàn.** PVC chỉ đại diện yêu cầu lưu trữ. Cần hiểu độ bền của PV/CSI, reclaim policy, snapshot và quy trình khôi phục.

**Operator tự nâng cấp PostgreSQL an toàn.** Khả năng nâng cấp tùy phiên bản, extension, data directory và chiến lược migration. Cần đọc tài liệu và diễn tập trước.

**Service luôn trỏ đúng primary ngay lập tức.** Endpoint có thể cần thời gian cập nhật; DNS cache và connection pool có thể giữ trạng thái cũ. Ứng dụng phải xử lý connection failure và xác minh server role theo cách phù hợp.

**Sửa trực tiếp Pod hoặc StatefulSet để khắc phục.** Tài nguyên do operator quản lý có thể bị reconcile ghi đè. Hãy thay đổi CR hoặc cơ chế cấu hình chính thức, trừ khi runbook yêu cầu thao tác tạm thời cụ thể.

**Giao toàn bộ trách nhiệm cho DBA hoặc đội platform.** DBA không thể kiểm soát node và CSI nếu không có quyền platform; platform không thể chịu trách nhiệm về tính đúng đắn của transaction và backup nghiệp vụ nếu không có chủ sở hữu dữ liệu. Mỗi đội phải sở hữu phần việc mà mình kiểm soát.

## 16. Checklist trước khi đưa vào production

- [ ] Đã chọn operator và phiên bản tương thích với Kubernetes, PostgreSQL và extension.
- [ ] Đã đọc CRD schema, phạm vi hỗ trợ, quy trình cài đặt, nâng cấp và gỡ bỏ.
- [ ] RPO, RTO, topology và chính sách replication đã được DBA/data owner phê duyệt.
- [ ] Instance được phân bố qua các node hoặc failure domain phù hợp.
- [ ] StorageClass, CSI, dung lượng, IOPS, mở rộng volume và reclaim policy đã được kiểm chứng.
- [ ] PVC không bị xóa ngoài ý muốn khi xóa hoặc thay đổi CR.
- [ ] Backup và WAL archive lưu ở đích độc lập; đã diễn tập PITR/restore.
- [ ] Failover, fencing, routing và ứng dụng reconnect đã được thử nghiệm.
- [ ] PDB, anti-affinity, topology spread và node drain có cấu hình phù hợp.
- [ ] CPU/RAM requests, limits, connection pool và PostgreSQL settings được sizing theo tải.
- [ ] RBAC, Secret, TLS, NetworkPolicy và image policy đáp ứng yêu cầu bảo mật.
- [ ] Metric, log, event, cảnh báo và runbook có người trực chịu trách nhiệm.
- [ ] Có kế hoạch riêng cho nâng cấp operator, CRD, PostgreSQL minor và major version.
- [ ] Đội ứng dụng đã kiểm thử timeout, retry, idempotency và schema migration.
- [ ] Ranh giới trách nhiệm và người quyết định trong sự cố đã được ghi lại.

Triển khai PostgreSQL bằng operator hiệu quả khi trạng thái mong muốn được khai báo rõ, operator được chọn phù hợp với nhu cầu, storage và mạng đáp ứng yêu cầu database, và mỗi đội hiểu phần trách nhiệm của mình. Operator tự động hóa vòng đời kỹ thuật trong phạm vi được hỗ trợ; độ tin cậy của dịch vụ vẫn phụ thuộc vào thiết kế dữ liệu, backup có thể khôi phục, ứng dụng chịu được gián đoạn và quy trình vận hành được diễn tập.

