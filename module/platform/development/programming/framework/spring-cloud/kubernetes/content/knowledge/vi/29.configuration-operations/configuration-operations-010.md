# Tiêu chí xác nhận thay đổi đã có hiệu lực trên toàn bộ bản sao

## 1. Bối cảnh và mục tiêu

Một thay đổi ConfigMap đã được Kubernetes chấp nhận, Configuration Watcher đã gửi thông báo và một request qua Service đã thành công. Ba tín hiệu đó vẫn chưa đủ để kết luận mọi bản sao ứng dụng Spring đang sử dụng cấu hình mới.

Trong module **SPRING_CLOUD_KUBERNETES**, bài học này thuộc chương **Vận hành cấu hình**. Bài tập trung vào cách xác định phạm vi bản sao, thu thập bằng chứng từ tiến trình thực tế và đưa ra kết luận có thể kiểm chứng khi thay đổi ConfigMap hoặc Secret.

Sau bài học, bạn có thể:

- Phân biệt dữ liệu đã được lưu, đã được nạp và đã có hiệu lực trong client.
- Lập danh sách đầy đủ các bản sao cần xác nhận.
- Thiết kế định danh cấu hình cùng phản hồi xác nhận cho từng tiến trình.
- Xử lý bản sao thiếu phản hồi, khởi động lại hoặc xuất hiện trong lúc autoscaling.
- Xác nhận hiệu lực bằng hành vi và chất lượng phục vụ.

Kết luận “toàn bộ bản sao” phải luôn gắn với phạm vi, thời điểm quan sát và độ mới của bằng chứng. Nó không phải cam kết rằng một Pod xuất hiện trong tương lai chắc chắn đã được kiểm tra.

## 2. Phân biệt các mức bằng chứng

Một thay đổi đi qua nhiều lớp:

~~~text
Nguồn cấu hình được quản lý
    -> ConfigMap/Secret trong API
    -> file hoặc dữ liệu client nhận được
    -> Environment và cấu hình đã bind
    -> HTTP client / SDK / pool / bean sử dụng
    -> request hoặc công việc thực tế
~~~

| Tín hiệu | Điều chứng minh được | Điều chưa chứng minh được |
| --- | --- | --- |
| API ghi ConfigMap thành công | Đối tượng đã được lưu | Các Pod đã nhận dữ liệu |
| File trong một Pod đã đổi | Dữ liệu tới filesystem của Pod đó | Client đã đọc và áp dụng lại |
| Thông báo refresh được gửi | Đường thông báo đã được thực hiện tới một mức xác định | Mọi đích nhận và mọi bean đều áp dụng thành công |
| Environment có giá trị mới | Nguồn thuộc tính có hiệu lực đã đổi | Đối tượng giữ bản sao giá trị đã đổi |
| Deployment rollout hoàn tất | Việc thay thế theo Pod template đã đạt trạng thái tương ứng | Cấu hình động bên trong client đã có hiệu lực |
| Readiness hoặc health UP | Điều kiện sức khỏe đã cấu hình đang đạt | Một thay đổi timeout, token hoặc cờ tính năng cụ thể đã hoạt động |
| Một request qua Service thành công | Một đường gọi đã thành công | Mọi replica đã được chạm tới |
| Mỗi tiến trình có xác nhận mới và phép thử phù hợp | Có bằng chứng theo từng bản sao trong phạm vi | Các thành phần ngoài phạm vi cũng đã chuyển |

ConfigMap volume cập nhật theo cơ chế nhất quán cuối cùng; biến môi trường không tự đổi trong tiến trình đang chạy, còn mount bằng subPath không nhận cập nhật tự động. [Cơ chế cập nhật ConfigMap](https://kubernetes.io/docs/concepts/configuration/configmap/).

Những khác biệt này quyết định nên chờ file, thực hiện refresh hay tạo tiến trình mới. Không dùng cùng một tín hiệu để đại diện cho mọi cách nạp cấu hình.

## 3. Xác định “toàn bộ bản sao” trước khi tính tỷ lệ

### 3.1. Chọn phạm vi theo chủ thể quản lý

Ví dụ mục tiêu là Deployment orders trong namespace config-confirmation-lab. Cần xác định Deployment cụ thể, các ReplicaSet liên quan và những Pod thuộc chúng.

Nhãn app: orders giúp tìm kiếm ban đầu nhưng chưa phải định danh quyền sở hữu duy nhất. Một canary, Job hoặc Deployment khác có thể dùng cùng nhãn.

Phạm vi kiểm tra nên ghi rõ:

| Nội dung | Ví dụ cần xác định |
| --- | --- |
| Môi trường | Cụm và namespace |
| Workload | Loại tài nguyên, tên và UID |
| Container | Container thực sự đọc và dùng cấu hình |
| Thành viên đang cần đạt | Pod thuộc thay đổi và năng lực phục vụ mong muốn |
| Thành viên còn dùng bản cũ | Pod đang drain hoặc công việc đang chạy |
| Consumer ngoài Service | Worker, Job hoặc ứng dụng khác dùng chung nguồn |
| Template cho lần chạy tiếp theo | Tham chiếu của CronJob hoặc workload sẽ tạo Pod mới |

Nếu chỉ kiểm tra canary, báo cáo là “canary đã đạt”. Không mở rộng kết luận thành “toàn bộ hệ thống đã đạt”.

### 3.2. Đừng dùng danh sách đã sẵn sàng làm mẫu số duy nhất

Giả sử Deployment cần bốn replica:

~~~text
Pod A: đã dùng cấu hình mới
Pod B: đã dùng cấu hình mới
Pod C: đã dùng cấu hình mới
Pod D: Pending hoặc chưa xác nhận
~~~

Nếu chỉ lấy ba Pod đã phản hồi, tỷ lệ sẽ là 3/3. Nhưng mục tiêu bốn replica vẫn chưa được đáp ứng. Kết quả đúng là ba đã đạt, một chưa có bằng chứng hoặc chưa hoạt động.

Phải kiểm tra riêng:

- Số bản sao cần có theo trạng thái mong muốn hiện hành.
- Tập Pod thực tế thuộc phạm vi.
- Tập tiến trình đã cung cấp bằng chứng hợp lệ.
- Những Pod cũ còn có thể phục vụ hoặc đang hoàn tất công việc.

Không loại Pod lỗi khỏi báo cáo chỉ để làm tỷ lệ đạt 100%.

### 3.3. Service và DiscoveryClient cung cấp các góc nhìn khác nhau

EndpointSlice có các điều kiện ready, serving và terminating phục vụ quyết định định tuyến. Chúng không chứa bằng chứng rằng client bên trong Pod đã dùng cấu hình mục tiêu. [Điều kiện EndpointSlice](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).

DiscoveryClient cũng có phạm vi namespace và bộ lọc Service theo cấu hình. Danh sách nó trả về không mặc nhiên là danh mục mọi consumer của một ConfigMap hoặc Secret. [Phạm vi DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Hãy đối chiếu:

~~~text
Phạm vi workload cần cập nhật
    + các đích còn có thể nhận traffic
    + consumer không đi qua Service
    + trạng thái của hệ thống định tuyến
~~~

Spring Cloud LoadBalancer, proxy hoặc client có thể còn giữ danh sách instance trong cache. Một Pod cũ đang drain hoặc một worker không có endpoint HTTP vẫn cần được xử lý theo phạm vi đã chọn.

## 4. Định danh mục tiêu: biết chính xác điều gì cần có hiệu lực

### 4.1. Tách lần thay đổi khỏi nội dung cấu hình

Có thể dùng hai định danh:

~~~json
{
  "changeId": "orders-change-042",
  "targetConfigRevision": "runtime-r42"
}
~~~

changeId định danh lần điều phối. targetConfigRevision định danh nội dung hoặc bộ cấu hình mong muốn. Khi rollback, một changeId mới có thể trỏ về nội dung runtime-r41; không bắt buộc nội dung mục tiêu luôn có số lớn hơn.

Đây là thiết kế metadata của ứng dụng và hệ thống vận hành, không phải field có sẵn bắt buộc của Spring Cloud Kubernetes.

Không dùng resourceVersion, số revision của Deployment và tên phiên bản nghiệp vụ thay thế lẫn nhau. Chúng phục vụ những cơ chế khác nhau.

### 4.2. Marker phải gắn với dữ liệu sử dụng thật

Nếu chỉ thêm ops.config-revision: runtime-r42 nhưng bỏ quên thay timeout, marker mới không chứng minh hành vi mới.

Một mục tiêu cần có cả:

- Artifact hoặc nguồn dữ liệu mong muốn.
- Những thuộc tính và ràng buộc thực sự cần thay đổi.
- Đối tượng sử dụng phải được cập nhật.
- Phép thử hành vi có thể phân biệt bản cũ và bản mới.

Ví dụ:

~~~text
Mục tiêu runtime-r42:
  orders.remote.timeout = 750 ms
  orders.remote.max-attempts = 1
  inventory client đã được tạo với hai giá trị này
  phép thử timeout có kiểm soát phù hợp với cấu hình đó
~~~

Các khóa trong ví dụ là hợp đồng do ứng dụng tự định nghĩa. Chúng không tự cấu hình mọi HTTP client chỉ vì xuất hiện trong ConfigMap.

### 4.3. Cấu hình giống phiên bản không nhất thiết giống mọi giá trị

Hai replica có thể hợp lệ khi cùng dùng một release cấu hình nhưng khác endpoint theo vùng, profile hoặc shard. Tiêu chí cần mô tả giá trị mong đợi cho từng nhóm thay vì yêu cầu mọi trường luôn giống nhau.

Ngược lại, cùng marker runtime-r42 nhưng một Pod bị biến môi trường ghi đè timeout thành 2 s là trường hợp chưa đạt mục tiêu.

Spring Boot có thứ tự ưu tiên giữa các nguồn cấu hình; biến môi trường hoặc tham số dòng lệnh có thể ghi đè dữ liệu nhập từ file. [Ưu tiên nguồn cấu hình](https://docs.spring.io/spring-boot/reference/features/external-config.html).

Nếu dùng fingerprint, chỉ tính trên tập cấu hình không nhạy cảm đã được chuẩn hóa. Không công khai hash mật khẩu hoặc token như một cách thay thế an toàn cho định danh phiên bản.

## 5. Hợp đồng xác nhận cho từng tiến trình

### 5.1. Định danh bằng Pod UID và lần chạy tiến trình

Tên Pod có thể được sử dụng lại khi một Pod khác thay thế. Container cũng có thể khởi động lại trong cùng Pod. Vì vậy, bằng chứng nên gắn với cả định danh Pod và lần chạy ứng dụng. [Vòng đời Pod và container](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/).

Một khóa thực tế có thể gồm:

~~~text
namespace
+ workload UID đã đối chiếu
+ Pod UID
+ container name
+ process instance ID
~~~

process instance ID do ứng dụng tạo mỗi lần khởi động, hoặc một định danh lần chạy đáng tin cậy từ môi trường. Không dùng phản hồi của tiến trình đã chết để xác nhận tiến trình mới.

Có thể cấp thông tin Pod qua Downward API:

~~~yaml
env:
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
  - name: POD_NAMESPACE
    valueFrom:
      fieldRef:
        fieldPath: metadata.namespace
  - name: POD_UID
    valueFrom:
      fieldRef:
        fieldPath: metadata.uid
~~~

Các trường này có thể được cung cấp mà không buộc ứng dụng tự gọi Kubernetes API chỉ để biết định danh Pod. [Downward API](https://kubernetes.io/docs/concepts/workloads/pods/downward-api/).

Danh tính phản hồi vẫn cần được đối chiếu với inventory và đường thu thập có kiểm soát; không tin một payload tự khai báo UID mà không xác minh nguồn.

### 5.2. Mô tả các mức áp dụng riêng biệt

Một bản ghi trạng thái có thể bao gồm:

| Trường | Ý nghĩa cần được triển khai |
| --- | --- |
| loadedRevision | Snapshot cấu hình đã đọc và phân tích thành công |
| activeRevision | Snapshot đang điều khiển client hoặc đối tượng thực thi |
| verifiedRevision | Snapshot đã qua phép thử phù hợp trên đối tượng đang active |
| processInstanceId | Lần chạy đã tạo bằng chứng |
| result | PASS, REJECTED, APPLYING hoặc trạng thái có ngữ nghĩa rõ |
| verificationId | Phép thử nào đã tạo kết quả |
| verifiedAt hoặc thời điểm nhận | Kiểm tra độ mới của bằng chứng |

Ví dụ giao diện nội bộ tự xây dựng:

~~~json
{
  "podUid": "pod-uid-example-a",
  "container": "app",
  "processInstanceId": "process-example-9",
  "changeId": "orders-change-042",
  "loadedRevision": "runtime-r42",
  "activeRevision": "runtime-r42",
  "verifiedRevision": "runtime-r42",
  "verificationId": "inventory-timeout-check-v1",
  "result": "PASS",
  "verifiedAt": "2026-11-25T03:15:00Z"
}
~~~

Đây là hợp đồng minh họa, không phải endpoint hoặc các metric có sẵn trong Spring.

loadedRevision chỉ được công bố sau khi đọc đúng dữ liệu. activeRevision chỉ đổi khi client tương ứng thật sự được đưa vào sử dụng. verifiedRevision chỉ đổi sau phép thử thành công của chính client đó.

### 5.3. Không tạo xác nhận chỉ từ sự kiện refresh

Refresh Scope có cơ chế proxy và khởi tạo lazy. Một bean có thể chỉ được tạo lại khi có lời gọi tiếp theo, nên sự kiện refresh hoặc HTTP phản hồi thành công chưa chứng minh lần khởi tạo đó đã thành công. [Vòng đời Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html).

Một trình tự ghi nhận hợp lý:

~~~text
Nhận tín hiệu thay đổi
    -> đọc và kiểm tra snapshot mục tiêu
    -> cập nhật hoặc thay đối tượng sử dụng
    -> đánh dấu active khi chuyển đổi đã hoàn tất
    -> thực hiện phép thử an toàn
    -> đánh dấu verified cho đúng snapshot và tiến trình
~~~

Nếu candidate bị từ chối hoặc client mới tạo thất bại, phản hồi cần thể hiện thất bại hoặc còn đang xử lý. Không cập nhật activeRevision chỉ vì Environment đã chứa marker mới.

### 5.4. Bằng chứng phải đủ mới và không lộ bí mật

Một kết quả PASS cũ không đủ khi client đã thay lần nữa hoặc tiến trình vừa khởi động lại. Đặt giới hạn độ mới và thu thập lại khi định danh lần chạy thay đổi.

Nếu các node có độ lệch đồng hồ, không dựa hoàn toàn vào phép trừ timestamp do Pod gửi. Có thể ghi thời điểm nhận tại bộ tổng hợp, kết hợp định danh phép kiểm tra mới và thời điểm quan sát inventory.

Chỉ xuất những trường cần thiết: revision, trạng thái, thời gian và lỗi được làm sạch. Không trả toàn bộ Environment, giá trị Secret, Authorization header hoặc cấu hình client có thông tin truy cập.

## 6. Tiêu chí quyết định thay đổi đã hoàn tất

### 6.1. Điều kiện theo từng bản sao

Một tiến trình thuộc phạm vi chỉ đạt khi đồng thời:

1. Định danh của nó khớp với thành viên đang cần xác nhận.
2. loadedRevision đúng nội dung mục tiêu của nhóm tương ứng.
3. activeRevision chứng minh đối tượng thực thi đã sử dụng bản đó.
4. Phép kiểm tra phù hợp tạo verifiedRevision đúng mục tiêu.
5. Kết quả đủ mới, thuộc lần chạy hiện tại.
6. Không còn trạng thái lỗi áp dụng hoặc ràng buộc bị vi phạm.

Không nhất thiết mọi ứng dụng phải lưu đúng các field ở trên. Cần bảo đảm có bằng chứng tương đương với ngữ nghĩa rõ ràng.

### 6.2. Điều kiện ở cấp toàn bộ phạm vi

Có thể mô tả:

~~~text
Hoàn tất
    = biết đầy đủ tập thành viên cần đạt
      VÀ năng lực/số bản sao mong muốn đã được đáp ứng
      VÀ mọi thành viên bắt buộc có bằng chứng hợp lệ
      VÀ không còn bản cũ phục vụ ngoài chính sách chuyển tiếp
      VÀ hành vi cùng chất lượng phục vụ đạt yêu cầu
      VÀ trạng thái ổn định trong cửa sổ quan sát đã chọn
~~~

Tỷ lệ tham khảo:

~~~text
coverage = số định danh tiến trình hiện tại có bằng chứng đạt
           / số thành viên thực tế bắt buộc phải xác nhận
~~~

coverage = 100% chỉ hữu ích sau khi mẫu số đã được xác minh. Vẫn phải kiểm tra năng lực mong muốn và các Pod chưa tạo được; không để tập thành viên thực tế nhỏ đi che một replica bị thiếu.

Nếu workload đang có không replica, đừng suy ra tất cả tiến trình đã áp dụng chỉ vì không có trường hợp vi phạm. Có thể xác nhận template cho lần chạy sau, nhưng trạng thái hiệu lực runtime cần được ghi là chưa được kiểm chứng hoặc không áp dụng theo chính sách rõ ràng.

### 6.3. Tách các kết quả vận hành

| Kết quả | Khi nào dùng |
| --- | --- |
| PENDING | Còn phân phối, áp dụng hoặc thu thập bằng chứng trong thời hạn |
| FAILED | Có lỗi không chấp nhận được hoặc quá hạn mà tiêu chí vẫn chưa đạt |
| SUCCEEDED | Tất cả điều kiện trong phạm vi đã đạt ở mốc đánh giá |
| SUPERSEDED | Một thay đổi khác đã thay mục tiêu trước khi kết luận |

Không dùng “không thấy lỗi” thay cho SUCCEEDED. Một replica không trả lời cần được ghi là thiếu bằng chứng, không được tự xem là đã đạt.

## 7. Ví dụ: xác nhận timeout mới trên ba replica

### 7.1. Mục tiêu thay đổi

Giả sử Deployment orders có ba replica trong config-confirmation-lab. Bản runtime-r41 dùng timeout 2 s. Bản runtime-r42 cần dùng timeout 750 ms, tối đa một lần gọi tới inventory.

Ứng dụng có client tùy biến hỗ trợ áp dụng snapshot và có phép thử an toàn. Đây là điều kiện của môi trường thực hành; chỉ thêm thuộc tính vào ConfigMap không tự tạo khả năng đó.

ConfigMap mục tiêu minh họa:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-runtime
  namespace: config-confirmation-lab
  labels:
    spring.cloud.kubernetes.config: "true"
  annotations:
    spring.cloud.kubernetes.configmap.apps: "orders"
data:
  application.yaml: |
    ops:
      change-id: orders-change-042
      config-revision: runtime-r42
    orders:
      remote:
        timeout: 750ms
        max-attempts: 1
~~~

Trong phương án volume, ứng dụng có thể nhập file từ thư mục được mount. Trích đoạn sau được tích hợp vào container và PodSpec đã có, không phải một Deployment hoàn chỉnh:

~~~yaml
containers:
  - name: app
    env:
      - name: SPRING_CONFIG_IMPORT
        value: "file:/etc/orders/application.yaml"
      - name: POD_UID
        valueFrom:
          fieldRef:
            fieldPath: metadata.uid
      - name: POD_NAME
        valueFrom:
          fieldRef:
            fieldPath: metadata.name
      - name: POD_NAMESPACE
        valueFrom:
          fieldRef:
            fieldPath: metadata.namespace
    volumeMounts:
      - name: runtime-config
        mountPath: /etc/orders
        readOnly: true
volumes:
  - name: runtime-config
    configMap:
      name: orders-runtime
~~~

Không dùng subPath cho đường cập nhật file của ví dụ này. Với phương án nạp qua API, thay phần kiểm tra file bằng bằng chứng nguồn API đã được đọc và áp dụng đúng.

### 7.2. Trạng thái sau khi gửi thông báo

Giả sử bộ thu thập nhận kết quả:

| Pod hiện tại | Loaded | Active client | Verified | Kết luận theo Pod |
| --- | --- | --- | --- | --- |
| A | r42 | r42 | r42, PASS | Đạt |
| B | r42 | r41 | Chưa có | Chưa đạt |
| C | r41 | r41 | Chưa có | Chưa đạt |

Cả ba Pod có thể vẫn Ready. Một request thông thường qua Service cũng có thể thành công ở cả ba vì inventory trả lời nhanh hơn cả hai timeout.

Kết luận lúc này là một trên ba bản sao có đủ bằng chứng. Không kết luận ba trên ba chỉ vì Watcher đã gửi ba thông báo.

Pod B cần được khảo sát ở bước thay client. Pod C cần được khảo sát ở bước phân phối hoặc đọc nguồn.

### 7.3. Phép thử phải phân biệt được r41 và r42

Trong môi trường thử nghiệm, có thể dùng một API đọc an toàn của inventory simulator, có thời gian trả lời nằm giữa 750 ms và 2 s.

Với điều kiện đường gọi được kiểm soát:

- Client r41 có thể nhận phản hồi trước timeout 2 s.
- Client r42 phải thể hiện timeout tương ứng chính sách 750 ms.
- Số lần gọi ở phía simulator phải phù hợp max-attempts bằng 1.

Không yêu cầu thời gian đo được đúng tuyệt đối 750 ms. Cần định nghĩa trước dung sai và điều kiện thử, do scheduling, mạng, handshake và cách client quản lý ngân sách đều ảnh hưởng kết quả.

Phép thử phải đi qua client đang active của từng tiến trình. Gọi trực tiếp simulator bằng curl chỉ chứng minh simulator có thể truy cập, không kiểm tra được timeout của client orders.

Không đưa fault injection này vào luồng có tác dụng phụ hoặc làm gián đoạn dịch vụ thật. Chọn simulator hoặc route kiểm tra được thiết kế cho phép thử.

### 7.4. Khi cả ba đều đạt

Sau khi B và C áp dụng thành công, cần thu thập bằng chứng mới:

~~~text
A, UID A, process hiện tại: loaded r42, active r42, verified r42
B, UID B, process hiện tại: loaded r42, active r42, verified r42
C, UID C, process hiện tại: loaded r42, active r42, verified r42
~~~

Sau đó đọc lại inventory, đối chiếu khả năng phục vụ và quan sát cửa sổ ổn định. Nếu chưa có thay đổi thành viên và các điều kiện còn lại đạt, có thể kết luận phạm vi đang xét đã hội tụ tại mốc đó.

Nếu HPA vừa tạo Pod D, tập ba bản sao cũ không còn đủ để kết luận về mục tiêu bốn bản sao. D phải được đưa vào phạm vi xác nhận.

## 8. Thu thập bằng chứng từ Kubernetes và ứng dụng

### 8.1. Đọc trạng thái Deployment và quyền sở hữu

Các lệnh dưới đây là hướng dẫn trên môi trường thử nghiệm, không phải kết quả đã được chạy:

~~~bash
kubectl get deployment orders -n config-confirmation-lab -o 'custom-columns=NAME:.metadata.name,UID:.metadata.uid,GENERATION:.metadata.generation,OBSERVED:.status.observedGeneration,DESIRED:.spec.replicas,UPDATED:.status.updatedReplicas,READY:.status.readyReplicas,AVAILABLE:.status.availableReplicas'
kubectl get replicasets -n config-confirmation-lab -l app=orders -o json
kubectl get pods -n config-confirmation-lab -l app=orders -o 'custom-columns=NAME:.metadata.name,UID:.metadata.uid,OWNER_UID:.metadata.ownerReferences[*].uid,PHASE:.status.phase,RESTARTS:.status.containerStatuses[*].restartCount'
~~~

Kiểm tra selector thực tế của Deployment. Từ ownerReferences, đối chiếu owner làm controller và chuỗi Pod → ReplicaSet → Deployment. Không chỉ đếm mọi tài nguyên trùng nhãn.

Các trường observedGeneration, updatedReplicas, readyReplicas và availableReplicas mô tả trạng thái controller và Pod template theo các ý nghĩa riêng. [DeploymentStatus](https://kubernetes.io/docs/reference/kubernetes-api/apps/deployment-v1/).

Cần xác nhận controller đã quan sát generation đang xét và năng lực mong muốn phù hợp. Tuy nhiên, một thay đổi nội dung ConfigMap cùng tên không tự biến updatedReplicas thành bộ đếm client đã nhận cấu hình.

### 8.2. Dùng rollout status đúng phạm vi

~~~bash
kubectl rollout status deployment/orders -n config-confirmation-lab --timeout=300s
~~~

Lệnh hữu ích khi thay đổi được triển khai bằng Pod template mới. Deployment hoàn tất rollout không phải phép thử ngữ nghĩa timeout hoặc token trong ứng dụng. [Trạng thái rollout Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/).

Trong phương án refresh một ConfigMap mutable, Pod template có thể không đổi. Khi đó, rollout status có thể chỉ phản ánh rollout trước đó và không cung cấp bằng chứng cho lần refresh hiện tại.

Số revision Deployment hoặc pod-template-hash cũng không thay thế loadedRevision, activeRevision và phép kiểm tra hành vi.

### 8.3. Đối chiếu đường phục vụ

~~~bash
kubectl get service orders -n config-confirmation-lab -o yaml
kubectl get endpointslices -n config-confirmation-lab -l kubernetes.io/service-name=orders -o yaml
~~~

Đối chiếu những endpoint có targetRef là Pod với UID trong inventory. Không đếm số địa chỉ endpoint như số tiến trình một cách máy móc: có thể có nhiều slice, nhiều cổng hoặc nhiều họ địa chỉ.

Kiểm tra cả đường gọi thực tế qua Service, DiscoveryClient, Spring Cloud LoadBalancer hoặc proxy. Một endpoint bị loại khỏi danh sách mới không chứng minh không còn request đang chạy hoặc cache cũ đang sử dụng nó.

### 8.4. Truy vấn đích cụ thể và xác minh nguồn phản hồi

Bộ thu thập có thể gọi endpoint trạng thái nội bộ của từng Pod hoặc nhận xác nhận từ ứng dụng qua kênh được quản lý. Mỗi cách cần kiểm soát xác thực, timeout, độ mới và ánh xạ tới định danh tiến trình.

Trong chẩn đoán thủ công, có thể mở đường tới một Pod cụ thể:

~~~bash
kubectl port-forward -n config-confirmation-lab pod/orders-example-a 19090:9090
~~~

Thay tên Pod, cổng và đường quản trị theo môi trường. Sau đó dùng client quản trị đã được cấu hình xác thực để đọc giao diện trạng thái tự xây dựng của ứng dụng.

Port-forward tới một Pod giúp chọn đích cụ thể. Nó không chứng minh đường mạng từ Configuration Watcher tới Pod hoạt động. Phải kiểm tra đường refresh thực tế riêng.

Nếu endpoint đi qua proxy hoặc bộ đệm, tránh trả lại bản trạng thái cũ. Xác minh Pod UID, process instance ID và thời điểm tạo bằng chứng trong phản hồi.

Actuator cung cấp công cụ sức khỏe và chẩn đoán, nhưng cần kiểm soát exposure và quyền truy cập; không bật hiển thị toàn bộ cấu hình để thay cho một hợp đồng trạng thái tối thiểu. [Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).

## 9. Xử lý thay đổi thành viên trong lúc kiểm tra

### 9.1. Autoscaling và Pod mới

HPA có thể thay số replica trong thời gian cấu hình đang được áp dụng. Cơ chế kiểm tra cần đọc lại trạng thái mong muốn và inventory trước khi kết luận.

Một vòng đánh giá có thể là:

~~~text
Đọc mục tiêu và inventory
    -> thu thập trạng thái từng tiến trình
    -> kiểm tra điều kiện theo Pod
    -> đọc lại mục tiêu và inventory
    -> nếu có Pod mới hoặc lần chạy mới: bổ sung kiểm tra
    -> nếu mục tiêu bị thay: đánh giá theo thay đổi mới
    -> nếu đủ điều kiện trong cửa sổ quan sát: kết luận
~~~

Đây là thuật toán điều phối minh họa. Không phải chức năng xác nhận fleet có sẵn trong Watcher.

Không cần mặc định tắt HPA để thực hiện mọi thay đổi. Cần một chính sách kiểm tra chịu được thay đổi thành viên và có thời hạn rõ ràng.

### 9.2. Container khởi động lại

Giả sử Pod B đã PASS bằng process-1, rồi container khởi động lại thành process-2. Pod UID có thể vẫn giữ nguyên, nhưng xác nhận của process-1 không còn chứng minh trạng thái process-2.

Cần thu thập lại loaded, active và verified của lần chạy mới. restartCount có thể hỗ trợ phát hiện nhưng không nên là định danh duy nhất trong hợp đồng ứng dụng.

Tương tự, không giữ một bản ghi PASS vô thời hạn trong bộ tổng hợp sau khi Pod tương ứng đã bị xóa.

### 9.3. Pod cũ đang drain

Tùy mục tiêu, có thể cho phép request đã bắt đầu bằng cấu hình cũ hoàn tất. Khi đó, phải ghi rõ điều kiện chuyển tiếp:

- Pod cũ có còn nhận công việc mới không?
- Client hoặc kết nối nào vẫn giữ cấu hình cũ?
- Khi nào việc drain được xem là xong?
- Thời hạn và bằng chứng kết thúc là gì?

“Tất cả replica mới đã PASS” và “không còn hành vi dùng cấu hình cũ” là hai phát biểu khác nhau. Chọn đúng phát biểu cho loại thay đổi.

Nếu cấu hình sửa một vấn đề bảo mật hoặc tính toán sai, việc tiếp tục dùng bản cũ trong request đang chạy cần được quyết định có chủ đích, không tự áp dụng cùng chính sách cho mọi thay đổi.

### 9.4. Worker, Job và lần chạy tương lai

Worker không có HTTP endpoint vẫn cần hợp đồng quan sát phù hợp, chẳng hạn trạng thái ứng dụng gửi về bộ tổng hợp hoặc phép thử công việc an toàn.

Với Job đang chạy, xác định cấu hình đã được nạp và ảnh hưởng của việc tiếp tục thực thi. Với CronJob chưa có Pod, có thể xác nhận template đã tham chiếu đúng nguồn, nhưng chưa thể khẳng định hành vi của một tiến trình chưa xuất hiện.

Báo cáo nên tách “runtime đang chạy đã xác minh” và “template cho lần chạy tiếp theo đã được cập nhật”. Nếu cần bằng chứng runtime trước khi hoàn tất, thực hiện một lần kiểm tra được kiểm soát phù hợp với tác vụ.

## 10. Configuration Watcher là đường truyền thay đổi, không phải biên nhận toàn cục

Configuration Watcher có thể tìm instance qua DiscoveryClient rồi gửi HTTP refresh hoặc dùng Spring Cloud Bus. Việc mount file được cập nhật và việc Spring áp dụng cấu hình là những bước riêng. [Cơ chế Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Có thể quan sát các mốc:

~~~text
Watcher thấy thay đổi
    -> xác định tập đích
    -> gửi thông báo tới từng đích
    -> ứng dụng xử lý tín hiệu
    -> ứng dụng nạp đúng snapshot
    -> client áp dụng
    -> phép thử hành vi thành công
~~~

Số lần gửi refresh, số đích được tìm hoặc số HTTP 2xx không thay thế tập xác nhận theo tiến trình.

Những nguyên nhân làm thiếu đích hoặc thiếu bằng chứng gồm:

| Điểm kiểm tra | Ví dụ vấn đề |
| --- | --- |
| Phạm vi nguồn | Watcher chưa theo dõi namespace hoặc Secret tương ứng |
| Chọn ứng dụng | Tên, annotation hoặc nhãn không khớp |
| Discovery | Bộ lọc, cache hoặc trạng thái endpoint chưa phản ánh đủ đích |
| Kết nối quản trị | Sai cổng, NetworkPolicy, TLS hoặc xác thực |
| Nguồn dữ liệu | File chưa cập nhật khi refresh tới |
| Áp dụng | Bean/client không được làm mới hoặc candidate bị từ chối |
| Xác minh | Không có phép thử sau áp dụng hoặc chưa khởi tạo bean lazy |

Pod không nằm trong danh sách thông báo không tự biến mất khỏi phạm vi phải xác nhận.

Với volume, khoảng chờ refresh có thể giúp giảm khả năng thông báo tới trước file, nhưng một khoảng chờ cố định không phải hàng rào xác nhận đồng loạt. Cần quan sát phiên bản mà từng ứng dụng thực sự đã nạp.

Nếu đường làm mới không phù hợp với đối tượng sử dụng, chuyển sang rollout hoặc cơ chế thay client được hỗ trợ. Không tăng số lần refresh vô hạn để thay thế việc xử lý nguyên nhân.

## 11. Theo dõi tiến độ và xử lý trường hợp chưa hội tụ

### 11.1. Dashboard phải thể hiện cả phần thiếu

Một báo cáo tổng hợp nên có:

| Số liệu | Cách hiểu |
| --- | --- |
| Desired capacity | Năng lực/số replica mong muốn hiện hành |
| Required members | Thành viên phải có bằng chứng theo phạm vi |
| Verified members | Định danh hiện tại đạt đủ tiêu chí |
| Missing members | Chưa nhận được bằng chứng cần thiết |
| Stale evidence | Chỉ có bằng chứng quá cũ hoặc thuộc lần chạy trước |
| Rejected/apply failed | Đã biết ứng dụng không áp dụng được |
| Old serving/draining members | Bản cũ còn cần xử lý theo chính sách |
| Change age và deadline | Thời gian đã dùng so với ngân sách |

Không dùng counter tổng số refresh thành công làm số replica đã đạt. Một Pod có thể nhận nhiều sự kiện và tạo nhiều lần tăng counter.

Nếu dùng metric theo từng Pod, cân nhắc cardinality và vòng đời series. Bộ tổng hợp phải đối chiếu inventory hiện tại, không đếm cả series của Pod đã chết. Các trường chi tiết và lỗi nên được lưu ở nơi phù hợp, không đưa toàn bộ vào nhãn metric.

### 11.2. Định nghĩa thời hạn theo đường áp dụng

Có thể lập ngân sách:

~~~text
T_confirm ≈ T_distribute
          + T_apply
          + T_initialize
          + T_verify
          + T_observe
          + T_margin
~~~

Các giai đoạn có thể chồng lấn. Dùng phép đo của môi trường để chọn thời hạn, độ mới và cửa sổ ổn định; không coi một số giây cố định là quy luật của Kubernetes.

Khi quá hạn mà vẫn có bản sao thiếu bằng chứng, thay đổi chưa đạt tiêu chí. Cần báo rõ Pod, lần chạy và lớp đang bị chặn.

### 11.3. Phân biệt chưa có hiệu lực với không còn sẵn sàng

Một Pod có thể từ chối r42, giữ client r41 và vẫn phục vụ ổn định. Dịch vụ có thể đang sẵn sàng, nhưng lần thay đổi r42 vẫn chưa thành công.

Ngược lại, mọi client có thể đã dùng r42 nhưng cấu hình mới làm tăng lỗi nghiệp vụ. Hiệu lực kỹ thuật đã có, còn tiêu chí chất lượng phục vụ không đạt; không nên kết luận thay đổi vận hành thành công.

Tách hai trục trong báo cáo:

~~~text
Độ bao phủ áp dụng cấu hình
    +
Chất lượng phục vụ sau áp dụng
~~~

### 11.4. Hành động theo nguyên nhân

| Quan sát | Hướng điều tra |
| --- | --- |
| loaded còn cũ | Phân phối file, namespace, nguồn API hoặc đường import |
| loaded mới nhưng active cũ | Vòng đời bean/client, trạng thái candidate, nguồn ghi đè |
| active mới nhưng verified thiếu | Phép thử chưa chạy, đối tượng lazy hoặc đường kiểm tra lỗi |
| verified thuộc tiến trình cũ | Khởi động lại và quản lý vòng đời bằng chứng |
| Chỉ Service test thành công | Có thể mới kiểm tra một phần đích |
| Pod mới xuất hiện chưa PASS | Bổ sung thành viên và thu thập lại |
| Tất cả đã áp dụng nhưng lỗi tăng | Đánh giá nội dung cấu hình và quyết định khôi phục |
| Bằng chứng không khớp inventory | Sai ánh xạ, dữ liệu cũ hoặc đường thu thập không đáng tin cậy |

Nếu chọn rollback, tạo một mục tiêu khôi phục rõ ràng và xác nhận lại bằng cùng nguyên tắc. Lệnh hoàn tác thành công không tự chứng minh mọi client đã trở về bản tốt.

## 12. Bài thực hành và mẫu kết luận

### 12.1. Thực hiện với môi trường thử nghiệm

Chuẩn bị ba replica orders, inventory simulator, cơ chế áp dụng và giao diện quan sát theo hợp đồng của bài.

1. Ghi lại inventory theo UID và process instance ID khi còn dùng r41.
2. Đặt mục tiêu runtime-r42 cùng phép thử phân biệt timeout.
3. Phát hành cấu hình qua cơ chế đã chọn.
4. Thu thập loaded, active và verified theo từng tiến trình.
5. Chủ động tạo một trường hợp nhận file nhưng chưa thay client.
6. Thử khởi động lại một container hoặc thêm replica theo phạm vi được phép.
7. Đọc lại inventory, loại bằng chứng cũ và kiểm tra thành viên mới.
8. Chỉ kết luận khi đủ tiêu chí hiệu lực và chất lượng phục vụ.

Đây là kịch bản hướng dẫn, không phải một đợt thử đã được thực hiện trên cụm cụ thể.

### 12.2. Những trường hợp hệ thống kiểm tra phải phát hiện

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Ba Pod, chỉ hai Pod có xác nhận hợp lệ | PENDING hoặc FAILED theo thời hạn |
| Ba phản hồi đến từ cùng một Pod | Không đếm thành ba bản sao |
| Pod mới dùng lại tên của Pod đã xóa | Không sử dụng PASS của UID cũ |
| Container restart trong cùng Pod | Yêu cầu bằng chứng của process mới |
| Marker r42 nhưng client vẫn có timeout r41 | Không đạt tiêu chí active/behavior |
| HPA tăng từ ba lên bốn | Kiểm tra thành viên và năng lực mới |
| Tất cả Ready nhưng không có phép thử cấu hình | Chưa đủ bằng chứng |
| Endpoint trả phản hồi bị cache | Không chấp nhận như bằng chứng mới |
| Mọi Pod áp dụng r42 nhưng lỗi tăng | Không đạt tiêu chí vận hành |
| Workload scale về không replica | Không tự kết luận runtime đã được xác minh |
| Một thay đổi mới thay r42 trước khi xong | Ghi mục tiêu cũ là SUPERSEDED theo chính sách |

### 12.3. Mẫu phát biểu hoàn thành

Một phát biểu có thể kiểm chứng cần nêu:

~~~text
Phạm vi: Deployment orders trong namespace config-confirmation-lab
Mục tiêu nội dung: runtime-r42
Lần thay đổi: orders-change-042
Mốc đánh giá: thời điểm do bộ tổng hợp ghi nhận
Thành viên: danh sách UID và lần chạy hiện tại đã đối chiếu
Bằng chứng: loaded, active và verified đạt cho mọi thành viên bắt buộc
Năng lực: đáp ứng trạng thái mong muốn đang xét
Bản cũ: không còn phục vụ ngoài điều kiện chuyển tiếp đã chấp nhận
Chất lượng: phép thử và chỉ số vận hành trong cửa sổ quan sát đạt
Kết quả: SUCCEEDED trong phạm vi và mốc đánh giá trên
~~~

Các trường này cần được điền bằng bằng chứng thực tế khi vận hành. Chúng không phải một xác nhận đã chạy sẵn của bài học.

Tiêu chí hoàn thành đáng tin cậy phải nối được trạng thái mong muốn với từng tiến trình đang sử dụng cấu hình và với hành vi thực tế. Thiếu một bản sao hoặc thiếu một lớp bằng chứng thì kết luận phải thể hiện đúng phần còn chưa biết.
