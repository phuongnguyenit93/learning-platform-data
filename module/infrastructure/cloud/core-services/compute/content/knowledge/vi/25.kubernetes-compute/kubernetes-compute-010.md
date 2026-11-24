# Spot node và chiến lược duy trì capacity cho workload quan trọng

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích cách Spot node giảm chi phí và vì sao năng lực của chúng không được bảo đảm liên tục.
- Phân loại workload theo mức độ quan trọng để quyết định nơi chạy phù hợp.
- Thiết kế node pool kết hợp On-Demand và Spot để duy trì năng lực phục vụ.
- Cấu hình Kubernetes scheduling bằng label, taint, toleration, node affinity, PodDisruptionBudget và topology spread.
- Chuẩn bị ứng dụng cho gián đoạn node, kiểm chứng khả năng phục hồi và theo dõi capacity trong vận hành.

## 1. Spot node là gì?

Nhà cung cấp đám mây có thể cung cấp máy ảo Spot từ phần capacity còn dư trong trung tâm dữ liệu. Giá của loại máy này thường thấp hơn máy On-Demand, nhưng nhà cung cấp có quyền thu hồi khi cần capacity hoặc khi điều kiện thị trường thay đổi. Tên gọi tùy nền tảng, ví dụ EC2 Spot Instances trên AWS, Spot VMs trên Google Cloud và Spot Virtual Machines trên Azure.

Trong Kubernetes, Spot node là worker node chạy trên máy ảo Spot. Pod được lập lịch lên node này giống các node khác, nhưng vòng đời của node có thể kết thúc sớm hơn dự kiến. Một thông báo gián đoạn có thể được gửi trước khi thu hồi, song thời gian và khả năng nhận thông báo phụ thuộc nhà cung cấp, loại máy và tình huống thu hồi. Ứng dụng phải luôn giả định node có thể biến mất và không dựa vào thông báo như một bảo đảm.

Spot phù hợp với workload có thể khởi chạy lại, phân tán hoặc tiếp tục từ checkpoint, chẳng hạn:

- Batch xử lý ảnh, video hoặc dữ liệu.
- Worker đọc thông điệp từ hàng đợi và có cơ chế retry.
- Tác vụ CI/CD, kiểm thử hoặc phân tích dữ liệu có thể chạy lại.
- Replica bổ sung cho dịch vụ stateless, khi vẫn còn một tập replica nền trên capacity ổn định.

Spot không phù hợp làm nơi duy nhất chạy thành phần không thể gián đoạn, một Pod đơn lẻ giữ trạng thái quan trọng hoặc dịch vụ cần capacity chắc chắn trong một khoảng thời gian xác định.

### 1.1. So sánh Spot và On-Demand

| Tiêu chí | Spot | On-Demand |
|---|---|---|
| Giá | Thường thấp hơn, có thể biến động theo thị trường và loại máy | Cao hơn nhưng dễ dự toán hơn |
| Khả năng tồn tại | Có thể bị thu hồi khi nhà cung cấp cần capacity | Không bị thu hồi theo cơ chế Spot |
| Khả năng cấp máy | Có thể thiếu capacity ở một vùng hoặc loại máy cụ thể | Thường dễ yêu cầu hơn, nhưng vẫn chịu quota và tình trạng capacity |
| Phù hợp | Workload chịu lỗi, có thể retry hoặc phân tán | Workload nền, dịch vụ quan trọng, thành phần cần ổn định |
| Thiết kế cần có | Phân tán loại máy/vùng, xử lý gián đoạn, khởi chạy lại | Dự phòng, autoscaling và giới hạn ngân sách |

On-Demand giúp giảm rủi ro thu hồi theo cơ chế Spot, nhưng không đồng nghĩa với bảo đảm tuyệt đối trước mọi sự cố hạ tầng. Với workload có yêu cầu nghiêm ngặt về capacity, có thể cần thêm capacity reservation, nhiều vùng sẵn sàng hoặc phương án khôi phục phù hợp với SLA.

## 2. Phân loại workload trước khi chọn node

Không nên chọn Spot chỉ dựa vào việc Pod không lưu dữ liệu cục bộ. Cần đánh giá tác động khi Pod bị dừng, thời gian khôi phục, khả năng chạy lại và phụ thuộc vào các dịch vụ khác.

| Nhóm workload | Ví dụ | Chiến lược capacity |
|---|---|---|
| Rất quan trọng, phục vụ yêu cầu trực tiếp | API thanh toán, xác thực, điều phối đơn hàng | Giữ replica nền trên On-Demand; phân tán qua nhiều zone; cân nhắc capacity reservation |
| Quan trọng nhưng có thể mở rộng ngang | API đọc dữ liệu, dịch vụ stateless có nhiều replica | Duy trì số replica tối thiểu trên On-Demand; dùng Spot cho phần capacity bổ sung nếu ứng dụng chịu được việc mất replica |
| Bất đồng bộ, có thể retry | Worker xử lý hóa đơn, gửi thông báo, chuyển mã media | Có thể chạy trên Spot nếu thông điệp được lưu bền vững, xử lý idempotent và có retry |
| Batch có thể chạy lại | ETL, tổng hợp báo cáo, huấn luyện theo lô | Ưu tiên Spot, lưu checkpoint thường xuyên và thiết kế job có thể tiếp tục |
| Stateful hoặc giữ dữ liệu cục bộ | Database đơn lẻ, cache không có replica, hệ thống lưu file trên đĩa node | Không đặt bản sao duy nhất trên Spot; dùng lưu trữ bền vững, replication và cơ chế failover |

Với một dịch vụ quan trọng, hãy xác định trước số Pod tối thiểu phải còn phục vụ khi toàn bộ Spot node bị thu hồi. Số Pod nền đó cần có khả năng chạy trên On-Demand node mà không phụ thuộc vào việc Spot có sẵn hay không.

Một cách rõ ràng là tách workload nền và workload tăng cường thành hai Deployment cùng phục vụ một Service:

- Deployment nền có số replica tối thiểu, node affinity bắt buộc vào On-Demand.
- Deployment tăng cường có thể scale trên Spot và được phép giảm hoặc khởi chạy lại khi capacity biến động.
- Service chọn chung label ứng dụng để phân phối request đến các Pod sẵn sàng của cả hai Deployment.

Cách tách này giúp kiểm soát phần capacity nền độc lập với phần capacity giá thấp. Nếu chỉ dùng một Deployment với affinity ưu tiên On-Demand, khi On-Demand hết chỗ Pod vẫn có thể được lập lịch lên Spot; điều đó không tạo ra một mức capacity nền được bảo đảm.

## 3. Thiết kế node pool kết hợp

Node pool là nhóm node có cùng chính sách về loại máy, vùng, nhãn, taint và cách tự động mở rộng. Một cluster thường có ít nhất hai nhóm:

- **On-Demand pool:** chứa capacity nền cho dịch vụ quan trọng và thành phần hệ thống cần ổn định.
- **Spot pool:** chứa workload chịu gián đoạn và phần capacity bổ sung có thể mất đi.

Ví dụ cho một cluster xử lý đơn hàng:

| Node pool | Cấu hình minh họa | Workload |
|---|---|---|
| **system-ondemand** | On-Demand, tối thiểu 2 node, triển khai qua nhiều zone | DNS, ingress, autoscaler và thành phần nền tảng |
| **critical-ondemand** | On-Demand, tối thiểu đủ chạy số replica nền và có headroom | API thanh toán, API đơn hàng |
| **elastic-spot** | Spot, tối thiểu 0 node, tối đa theo quota và ngân sách; nhiều loại máy | Worker, batch, replica bổ sung |

Các con số trên chỉ minh họa. Cần tính từ CPU/memory request, số Pod nền, số zone, khả năng chịu lỗi của node và mức dự phòng cần giữ. Không đặt min size của On-Demand chỉ bằng số node đang dùng ở thời điểm bình thường; cần có chỗ cho Pod được reschedule khi một node bị bảo trì hoặc mất kết nối.

### 3.1. Đa dạng hóa Spot capacity

Một Spot pool chỉ dùng một loại máy ở một zone có thể không tìm được capacity khi nhu cầu của nhà cung cấp thay đổi. Nên:

- Cho phép nhiều instance family và size có năng lực tương đương.
- Phân bổ node qua nhiều availability zone nếu ứng dụng và storage hỗ trợ.
- Tránh phụ thuộc vào một cấu hình CPU hoặc kiến trúc phần cứng duy nhất khi ứng dụng có thể chạy trên nhiều loại.
- Đặt giới hạn tổng CPU, bộ nhớ, số node và ngân sách để autoscaler không mở rộng vô hạn.
- Theo dõi tỷ lệ yêu cầu Spot được cấp thành công và thời gian Pod chờ được schedule.

Đa dạng hóa làm tăng khả năng tìm được capacity, nhưng không loại bỏ rủi ro thiếu Spot trong toàn vùng. Cần luôn có phương án chạy workload quan trọng trên On-Demand.

### 3.2. Cluster autoscaler và capacity buffer

Kubernetes scheduler chỉ chọn node đã tồn tại và đủ điều kiện. Khi Pod ở trạng thái Pending vì thiếu tài nguyên, Cluster Autoscaler hoặc cơ chế autoscaling node pool có thể yêu cầu thêm node. Karpenter là một lựa chọn khác trong các cluster hỗ trợ, có thể chọn loại máy theo yêu cầu Pod và chính sách NodePool.

Autoscaler không thể tạo ra Spot capacity nếu nhà cung cấp không còn máy phù hợp. Khi Spot pool không cấp được máy, hệ thống cần một trong các lựa chọn đã được thiết kế trước:

- Để workload chịu lỗi chờ nếu SLA cho phép.
- Chuyển workload có thể chạy trên On-Demand sang pool ổn định theo chính sách fallback.
- Dùng thêm loại máy hoặc zone khác.
- Giữ capacity buffer On-Demand đủ cho số workload quan trọng tối thiểu.

Với workload quan trọng, nên dành sẵn headroom trên On-Demand thay vì đợi node bị thu hồi rồi mới bắt đầu yêu cầu máy mới. Thời gian cấp node, tải image và khởi động ứng dụng đều tạo độ trễ khôi phục.

## 4. Điều khiển Pod bằng label, taint và affinity

Các cơ chế scheduling giúp xác định workload nào được phép chạy trên node nào.

- **Label:** gắn thuộc tính vào node, ví dụ **capacity.example.com/type=on-demand** hoặc **capacity.example.com/type=spot**.
- **Taint:** đánh dấu node để Pod không được schedule lên nếu thiếu toleration phù hợp.
- **Toleration:** cho phép Pod chấp nhận một taint; toleration không tự buộc Pod chạy trên node mang taint đó.
- **Node affinity/nodeSelector:** giới hạn hoặc ưu tiên node dựa trên label.
- **Topology spread constraint:** phân bố Pod qua zone hoặc node để tránh dồn replica vào một miền lỗi.

Nên cấu hình label và taint từ node pool hoặc node provisioning template để node mới có cùng thuộc tính. Không dựa vào thao tác gắn nhãn thủ công sau khi node đã tham gia cluster.

### 4.1. Deployment nền chạy trên On-Demand

Ví dụ API thanh toán cần tối thiểu ba replica và chỉ được chạy trên node mang label On-Demand. Node pool On-Demand phải có đủ tài nguyên ở nhiều zone để đặt ba Pod này.

    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: payment-api-core
    spec:
      replicas: 3
      selector:
        matchLabels:
          app: payment-api
          tier: core
      template:
        metadata:
          labels:
            app: payment-api
            tier: core
        spec:
          affinity:
            nodeAffinity:
              requiredDuringSchedulingIgnoredDuringExecution:
                nodeSelectorTerms:
                  - matchExpressions:
                      - key: capacity.example.com/type
                        operator: In
                        values:
                          - on-demand
          topologySpreadConstraints:
            - maxSkew: 1
              topologyKey: topology.kubernetes.io/zone
              whenUnsatisfiable: DoNotSchedule
              labelSelector:
                matchLabels:
                  app: payment-api
                  tier: core
          containers:
            - name: api
              image: example.invalid/payment-api:v1
              resources:
                requests:
                  cpu: 500m
                  memory: 512Mi
                limits:
                  cpu: "1"
                  memory: 1Gi
              readinessProbe:
                httpGet:
                  path: /ready
                  port: 8080
                periodSeconds: 5
                failureThreshold: 3

Affinity bắt buộc bảo đảm Pod nền chỉ được schedule lên On-Demand node có label phù hợp. **topologySpreadConstraints** giúp phân bố Pod qua zone; cluster phải có đủ zone và node đáp ứng điều kiện, nếu không Pod có thể ở trạng thái Pending. Trong môi trường thật, thay image minh họa bằng image hợp lệ và khai báo các probe, port, security context, secret theo ứng dụng.

Tạo PodDisruptionBudget để giới hạn số replica nền có thể bị gián đoạn trong các thao tác eviction có kiểm soát:

    apiVersion: policy/v1
    kind: PodDisruptionBudget
    metadata:
      name: payment-api-core-pdb
    spec:
      minAvailable: 2
      selector:
        matchLabels:
          app: payment-api
          tier: core

Với ba replica, **minAvailable: 2** cho phép tối đa một Pod bị voluntary eviction tại một thời điểm thông qua eviction API. PDB giúp bảo vệ trong các thao tác như drain node hoặc bảo trì có kiểm soát. PDB không ngăn nhà cung cấp thu hồi Spot node, không bảo vệ khỏi mọi sự cố node và không thay thế việc chạy replica trên nhiều failure domain.

### 4.2. Worker chịu gián đoạn chạy trên Spot

Worker xử lý thông điệp có thể chạy trên Spot nếu thông điệp được lưu trong broker bền vững, worker xác nhận sau khi hoàn tất và có thể nhận lại thông điệp khi Pod dừng giữa chừng.

Ví dụ Deployment worker:

    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: invoice-worker
    spec:
      replicas: 4
      selector:
        matchLabels:
          app: invoice-worker
      template:
        metadata:
          labels:
            app: invoice-worker
        spec:
          terminationGracePeriodSeconds: 60
          tolerations:
            - key: dedicated
              operator: Equal
              value: spot
              effect: NoSchedule
          affinity:
            nodeAffinity:
              requiredDuringSchedulingIgnoredDuringExecution:
                nodeSelectorTerms:
                  - matchExpressions:
                      - key: capacity.example.com/type
                        operator: In
                        values:
                          - spot
          containers:
            - name: worker
              image: example.invalid/invoice-worker:v1
              resources:
                requests:
                  cpu: 500m
                  memory: 512Mi
              env:
                - name: QUEUE_NAME
                  value: invoices
              lifecycle:
                preStop:
                  exec:
                    command: ["/app/worker", "drain"]

Lệnh **preStop** là ví dụ về giao diện drain do ứng dụng cung cấp; chương trình thực tế phải hỗ trợ lệnh này. Khi nhận tín hiệu kết thúc, worker nên dừng lấy thông điệp mới, hoàn tất công việc đang xử lý nếu còn đủ thời gian, hoặc để broker phát lại thông điệp chưa được xác nhận. **terminationGracePeriodSeconds** chỉ đặt thời gian Kubernetes chờ trước khi kết thúc Pod; nó không kéo dài thời hạn thu hồi của nhà cung cấp.

Đối với worker, cần bảo đảm:

- Xử lý idempotent để một thông điệp được giao lại không tạo giao dịch hoặc hóa đơn trùng.
- Chỉ ack sau khi kết quả đã được ghi bền vững.
- Retry có giới hạn, backoff và dead-letter queue cho thông điệp lỗi kéo dài.
- Thời gian xử lý, visibility timeout/ack timeout và thời gian graceful shutdown tương thích.
- Checkpoint định kỳ nếu một tác vụ kéo dài không thể bắt đầu lại từ đầu.

Nếu worker chỉ chạy trên Spot, khi Spot capacity bị thu hồi hàng loạt, tốc độ xử lý có thể giảm mạnh. Có thể giữ một nhóm worker nền trên On-Demand và dùng Spot cho phần worker mở rộng, đặc biệt khi backlog phải được xử lý trong một SLA xác định.

## 5. Duy trì capacity cho workload quan trọng

Chiến lược capacity cần bắt đầu từ mục tiêu dịch vụ. Ví dụ, API đơn hàng phải duy trì ít nhất sáu Pod sẵn sàng trong một zone failure hoặc khi toàn bộ Spot node bị thu hồi. Từ mục tiêu đó, tính ngược tài nguyên cần có trên On-Demand.

Một quy trình ước lượng:

1. Xác định số replica tối thiểu phải tiếp tục phục vụ.
2. Lấy CPU và memory request của mỗi Pod, cộng thêm DaemonSet và workload hệ thống.
3. Tính khả năng đặt Pod sau khi mất một node hoặc một zone theo mô hình lỗi cần chịu được.
4. Cộng headroom cho rolling update, scale out và Pod mới khởi động.
5. Kiểm tra quota, giới hạn instance và capacity reservation nếu SLA yêu cầu.
6. Kiểm chứng bằng cách làm mất node trong môi trường thử nghiệm.

Ví dụ: dịch vụ cần sáu Pod nền, mỗi Pod request 500m CPU và 512 MiB. Nhu cầu riêng của ứng dụng tối thiểu là 3 vCPU và 3 GiB bộ nhớ. Capacity thực tế cần lớn hơn con số này vì node còn chạy DaemonSet, system reserved, kube reserved và cần headroom. Nếu phải chịu được mất một node, hãy tính capacity còn lại sau khi trừ toàn bộ tài nguyên của node đó.

### 5.1. On-Demand baseline và Spot burst

Mô hình thường dùng cho dịch vụ quan trọng:

- Giữ đủ On-Demand capacity cho các replica nền và các Pod hệ thống.
- Dùng Spot cho replica bổ sung hoặc worker có thể retry.
- Khi tải tăng, HPA tăng số Pod; node autoscaler bổ sung capacity theo node pool tương ứng.
- Khi Spot thiếu, workload tăng cường có thể chờ hoặc fallback theo chính sách đã định.
- Khi Spot bị thu hồi, replica nền tiếp tục phục vụ trong khi replica bổ sung được tạo lại khi capacity sẵn có.

Với API cần phục vụ request ngay, phần replica nền nên luôn được đặt trên On-Demand. Phần tăng cường có thể là Deployment riêng, tránh để toàn bộ replica của một Deployment quan trọng bị schedule ngẫu nhiên lên Spot.

### 5.2. Dự phòng theo zone và node

Chạy nhiều replica trên cùng một node không tạo ra khả năng chịu lỗi node. Tương tự, đặt tất cả node trong cùng một zone vẫn có rủi ro khi zone gặp sự cố.

Dùng topology spread hoặc pod anti-affinity để phân tán replica. Kiểm tra các ràng buộc scheduling có thể khiến Pod Pending khi một zone thiếu capacity. Với storage gắn theo zone, phải xét topology của PersistentVolume và khả năng detach/attach khi Pod được lập lịch lại.

Đối với hệ thống stateful, ưu tiên replication ở tầng ứng dụng hoặc dịch vụ dữ liệu được quản lý. Một StatefulSet đơn replica trên Spot cùng một volume không tự trở thành hệ thống có tính sẵn sàng cao. Nếu dùng volume theo zone, việc Pod chạy lại ở zone khác có thể không thực hiện được cho đến khi có cơ chế phục hồi dữ liệu phù hợp.

### 5.3. PriorityClass và PDB

PriorityClass cho phép scheduler ưu tiên Pod quan trọng hơn khi nhiều Pod tranh chấp tài nguyên. Pod priority cao có thể khiến Pod priority thấp bị preempt trong cluster để giải phóng chỗ. Điều này không làm Spot node ít có khả năng bị thu hồi hơn và cũng không tạo thêm capacity.

PDB kiểm soát số Pod được voluntary eviction thông qua Kubernetes eviction API. Nó hữu ích khi drain node hoặc thực hiện bảo trì, nhưng không phải lá chắn trước sự kiện mất node đột ngột. Không đặt PDB quá chặt đến mức mọi thao tác bảo trì đều bị chặn; đồng thời phải bảo đảm số replica thực tế đủ lớn để đáp ứng **minAvailable**.

Với workload Spot có thể retry, PDB có thể cho phép gián đoạn phù hợp với thiết kế. Với workload quan trọng, PDB nên áp dụng lên replica nền chạy trên On-Demand, kết hợp readiness, replica đa zone và capacity dự phòng.

## 6. Xử lý sự kiện thu hồi Spot

Khi node nhận thông báo thu hồi, mục tiêu là chuyển workload đi nơi khác trước khi node biến mất. Cần có cơ chế phát hiện sự kiện từ nhà cung cấp, cordon node, drain Pod và cho scheduler/autoscaler tạo capacity thay thế.

Tùy nền tảng, cơ chế có thể là:

- AWS: AWS Node Termination Handler hoặc tích hợp xử lý sự kiện interruption/rebalance với node provisioning.
- GKE: cơ chế xử lý vòng đời Spot VM của nền tảng và cấu hình workload để chịu được việc node bị thu hồi.
- Azure: tích hợp thông báo eviction của Spot VM với quy trình drain và khởi chạy lại workload.

Tên công cụ và khả năng tích hợp thay đổi theo dịch vụ, phiên bản cluster và cách cấp node. Cần kiểm tra hướng dẫn của nhà cung cấp cho phiên bản đang vận hành. Không giả định rằng Kubernetes tự nhận được mọi thông báo thu hồi của máy ảo.

### 6.1. Trình tự xử lý khi node sắp bị thu hồi

1. Nhận thông báo từ metadata service, event stream hoặc thành phần theo dõi vòng đời node.
2. Đánh dấu node không nhận Pod mới bằng cordon.
3. Drain Pod qua Kubernetes eviction API nếu thời gian còn lại cho phép.
4. Ứng dụng nhận tín hiệu dừng, ngừng nhận công việc mới và flush/checkpoint dữ liệu cần thiết.
5. Scheduler đặt Pod thay thế lên node còn capacity.
6. Autoscaler tạo thêm node theo chính sách; nếu Spot không có sẵn thì dùng capacity fallback hoặc để workload chờ.
7. Theo dõi đến khi replica sẵn sàng và dịch vụ trở lại mức capacity yêu cầu.

Thời gian thông báo trước có thể ngắn hoặc không có trong một số tình huống. Vì vậy, thiết kế ứng dụng phải chịu được mất node bất ngờ. Cơ chế drain cải thiện khả năng kết thúc có trật tự khi có thông báo, nhưng không thay thế retry, replication và lưu trữ bền vững.

### 6.2. Graceful shutdown trong ứng dụng

Đối với API, khi nhận SIGTERM:

- Ngừng nhận request mới hoặc chuyển readiness sang trạng thái không sẵn sàng.
- Chờ load balancer ngừng gửi request mới theo cơ chế của nền tảng.
- Hoàn tất request đang chạy trong giới hạn thời gian.
- Đóng kết nối, flush telemetry và thoát sạch.

Đối với worker:

- Ngừng poll hoặc nhận message mới.
- Hoàn tất tác vụ đang chạy nếu có thể.
- Ghi checkpoint hoặc để message chưa ack được phát lại.
- Đóng kết nối broker và thoát.

**preStop**, **terminationGracePeriodSeconds** và xử lý SIGTERM cần được phối hợp. Nếu thời gian kết thúc dài hơn thời gian thu hồi thực tế, Pod vẫn có thể bị dừng cưỡng bức trước khi hoàn tất.

## 7. Tự động mở rộng và fallback

HPA điều chỉnh số Pod dựa trên metric ứng dụng hoặc tài nguyên; node autoscaler bổ sung node khi Pod không thể schedule. Hai tầng này phải được cấu hình đồng bộ.

Ví dụ:

- HPA của API nền giữ tối thiểu sáu replica trên On-Demand.
- HPA của worker tăng số Pod theo queue depth.
- Spot node pool có min size 0 và max size theo quota.
- On-Demand node pool giữ capacity nền và có giới hạn đủ để chứa workload quan trọng.
- Khi Spot không cấp được máy, worker có thể chờ hoặc chuyển sang On-Demand theo chính sách fallback.

Không đặt max replica của HPA cao hơn khả năng cung cấp node và downstream mà không có giới hạn. Nếu HPA tăng Pod nhanh nhưng node autoscaler mất nhiều phút để cấp máy, Pod sẽ Pending và SLO vẫn bị ảnh hưởng.

Với Karpenter hoặc Cluster Autoscaler, cần kiểm tra:

- NodePool/node group có các loại máy và zone phù hợp với Pod request.
- Taint, label và affinity của node pool khớp với Pod.
- Giới hạn tổng tài nguyên và quota nhà cung cấp.
- Chính sách consolidation/scale down không loại bỏ capacity nền.
- Spot fallback có được phép và có thể chuyển sang On-Demand theo mức ưu tiên đã thiết kế hay không.

Nếu dùng Spot và On-Demand trong cùng một node pool hoặc NodePool policy, hãy xác minh rõ thứ tự ưu tiên, loại máy được phép và hành vi khi Spot không có capacity. Đừng coi fallback là tự động nếu chưa cấu hình và thử nghiệm.

## 8. Theo dõi và cảnh báo

Theo dõi cả trạng thái node, trạng thái Pod và chất lượng dịch vụ. Một cluster có thể vẫn hiển thị node Ready nhưng không còn đủ capacity phù hợp cho workload do taint, affinity hoặc quota.

Các tín hiệu nên quan sát:

| Nhóm | Metric/sự kiện | Ý nghĩa |
|---|---|---|
| Spot lifecycle | Số interruption, rebalance/eviction notice, node bị thu hồi | Nhận biết tần suất gián đoạn |
| Node capacity | CPU/memory allocatable, node Pending/NotReady, số node theo pool/zone | Phát hiện thiếu capacity hoặc phân bố lệch |
| Scheduling | Pod Pending, FailedScheduling, thời gian từ Pending đến Ready | Đo độ trễ cấp capacity |
| Workload | Replica desired/available, restart, eviction, rollout | Xác nhận dịch vụ còn đủ bản sao |
| Queue/batch | Queue depth, tuổi message, retry, checkpoint, job duration | Đánh giá tác động của gián đoạn lên công việc |
| SLO | p95/p99 latency, error rate, availability, request throughput | Xác nhận trải nghiệm người dùng |

Nên cảnh báo khi:

- Replica nền trên On-Demand thấp hơn mức yêu cầu.
- Pod quan trọng Pending hoặc không đạt số replica sẵn sàng trong thời gian cho phép.
- Spot interruption tăng đột biến hoặc Spot pool liên tục không cấp được node.
- Worker backlog hoặc tuổi thông điệp vượt SLA.
- On-Demand pool không còn headroom để nhận Pod khi Spot bị thu hồi.

Đối chiếu chi phí theo từng pool. Spot có giá thấp hơn nhưng nếu thường xuyên phải chạy fallback trên On-Demand, tổng chi phí có thể khác xa dự toán ban đầu. Cần so sánh chi phí với availability, thời gian xử lý và chi phí vận hành sự cố.

## 9. Quy trình kiểm chứng trước production

Thử nghiệm trong staging hoặc cluster có thể kiểm soát:

1. **Ghi nhận baseline:** xác nhận số replica nền, node On-Demand, zone, CPU/memory request và metric SLO.
2. **Kiểm tra scheduling:** tạo Pod nền và Pod Spot thử nghiệm; xác nhận label, taint, toleration, affinity và topology spread hoạt động như dự kiến.
3. **Kiểm tra PDB:** thử drain một node On-Demand trong điều kiện kiểm soát; xác nhận số Pod tối thiểu và hành vi eviction.
4. **Mô phỏng Spot interruption:** kết thúc một Spot node theo quy trình thử nghiệm của nền tảng. Quan sát thông báo, cordon, drain, Pod reschedule và thời gian phục hồi.
5. **Kiểm tra thiếu Spot capacity:** giới hạn hoặc tạm vô hiệu hóa Spot pool trong môi trường thử nghiệm; xác nhận workload quan trọng vẫn chạy trên On-Demand và workload chịu lỗi chờ/fallback đúng chính sách.
6. **Kiểm tra mất node/zone:** xác minh topology spread, replica và capacity còn lại khi một failure domain không còn khả dụng.
7. **Kiểm tra ứng dụng:** xác nhận API không mất request vượt SLO; worker không mất message, xử lý trùng an toàn và tiếp tục từ checkpoint.
8. **Kiểm tra autoscaler:** xác nhận HPA và node autoscaler phối hợp, không tạo quá nhiều Pod Pending hoặc mở rộng vượt quota.
9. **Đối chiếu chi phí:** so sánh tỷ lệ Spot, On-Demand baseline, fallback và chi phí vận hành với ngân sách.

Không thử thu hồi node bằng cách xóa ngẫu nhiên node production. Dùng môi trường staging, quy trình disruption có kiểm soát và kịch bản đã thống nhất với nhóm vận hành.

## 10. Tình huống thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Pod quan trọng Pending dù Spot node còn chỗ | Pod yêu cầu label On-Demand nhưng node hiện có là Spot | Kiểm tra node labels, affinity và capacity On-Demand |
| Worker không được schedule lên Spot | Thiếu toleration hoặc label/taint không khớp | Kiểm tra kubectl describe pod và kubectl describe node |
| Spot bị thu hồi nhưng Pod không được tạo lại | Node autoscaler không có capacity, quota hoặc loại máy phù hợp | Kiểm tra autoscaler events, quota, instance types và zone |
| PDB làm drain node bị chặn | minAvailable quá cao hoặc không đủ replica khỏe mạnh | Kiểm tra PDB status, replica available và kế hoạch drain |
| API vẫn lỗi sau khi tăng replica | Downstream, database hoặc network là nút thắt | Đối chiếu latency, connection pool, error rate và throughput |
| Worker xử lý trùng message sau interruption | Ack trước khi ghi kết quả hoặc thiếu idempotency | Kiểm tra thứ tự commit/ack, retry và khóa idempotency |
| Pod không drain kịp | Shutdown handler chậm hoặc thời gian kết thúc không phù hợp | Kiểm tra SIGTERM, preStop, grace period và thời hạn interruption |
| On-Demand pool thiếu chỗ khi Spot mất | Baseline capacity/headroom quá thấp | Tính lại N+1, quota, zone capacity và reservation |

## 11. Checklist triển khai

- [ ] Phân loại workload theo mức độ quan trọng, khả năng retry và thời gian khôi phục.
- [ ] Xác định số replica nền phải chạy khi toàn bộ Spot capacity biến mất.
- [ ] Giữ On-Demand capacity đủ cho replica nền, hệ thống và headroom cần thiết.
- [ ] Tách Spot và On-Demand node pool; gắn label/taint nhất quán từ cấu hình cấp node.
- [ ] Dùng affinity bắt buộc cho workload cần bảo đảm chạy trên On-Demand.
- [ ] Dùng toleration và affinity phù hợp cho workload chịu gián đoạn.
- [ ] Phân tán replica qua node và zone bằng topology spread hoặc anti-affinity.
- [ ] Cấu hình PDB phù hợp, đồng thời hiểu giới hạn của PDB trước sự cố node.
- [ ] Bảo đảm worker idempotent, retry, ack đúng thời điểm và checkpoint nếu cần.
- [ ] Tích hợp xử lý interruption, cordon/drain và graceful shutdown.
- [ ] Cấu hình autoscaler, quota, giới hạn node pool và fallback khi Spot thiếu.
- [ ] Theo dõi interruption, Pending Pod, capacity theo zone, replica available và SLO.
- [ ] Kiểm thử mất Spot node, thiếu Spot capacity, drain On-Demand và phục hồi workload.
- [ ] Đối chiếu chi phí thực tế với availability và mục tiêu ngân sách.

## Kết luận

Spot node giúp giảm chi phí cho workload có thể bị gián đoạn, nhưng capacity Spot không phải năng lực được bảo đảm liên tục. Hãy duy trì replica nền và headroom trên On-Demand cho workload quan trọng, phân tách node pool bằng label/taint/affinity, phân tán replica qua failure domain và thiết kế ứng dụng có thể drain, retry hoặc phục hồi. Chỉ đưa workload lên Spot sau khi đã kiểm chứng tình huống node bị thu hồi và tình huống Spot không còn capacity.
