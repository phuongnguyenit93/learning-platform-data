# Quay lại cấu hình trước khi thay đổi gây lỗi

## 1. Bối cảnh và mục tiêu

Một thay đổi timeout, số lần thử lại hoặc cờ tính năng có thể làm dịch vụ suy giảm dù image ứng dụng không đổi. Khi đó, khôi phục cấu hình cần xử lý cả nguồn dữ liệu lẫn trạng thái đang được sử dụng trong từng tiến trình.

Trong module **SPRING_CLOUD_KUBERNETES**, bài học này thuộc chương **Vận hành cấu hình**. Mục tiêu là quay về một cấu hình đã được chứng minh hoạt động tốt khi ứng dụng Spring nhận cấu hình từ ConfigMap hoặc Secret, qua file được mount hoặc Kubernetes API, và có thể dùng Configuration Watcher để cập nhật.

Sau bài học, bạn có thể:

- Xác định đúng phiên bản cấu hình cần khôi phục và phạm vi ảnh hưởng.
- Phân biệt khôi phục ConfigMap, khôi phục Deployment và khôi phục trạng thái client.
- Chọn refresh tại chỗ hoặc rollout dựa trên cách ứng dụng dùng cấu hình.
- Xác minh từng replica đã dùng cấu hình tốt, thay vì chỉ dựa vào lệnh thành công.
- Xử lý trường hợp cấu hình cũ không còn tương thích hoặc không còn an toàn.

Bài sử dụng một thay đổi cấu hình không chứa bí mật để minh họa. Khi có Secret, cần kiểm tra thêm hiệu lực thông tin truy cập và quyền đọc dữ liệu.

## 2. Khôi phục thành công ở lớp nào?

Có thể chia trạng thái cấu hình thành bốn lớp:

~~~text
Nguồn cấu hình được quản lý
    |
    v
ConfigMap/Secret và tham chiếu trong Pod template
    |
    v
File hoặc property source mà tiến trình đã nhận
    |
    v
Cấu hình và client thực sự đang xử lý request
~~~

Ví dụ, ConfigMap đã về timeout 800 ms nhưng HTTP client vẫn giữ timeout 50 ms thì sự cố chưa được khắc phục.

| Bằng chứng | Cho biết điều gì? | Chưa cho biết điều gì? |
| --- | --- | --- |
| Thay đổi nguồn cấu hình đã được ghi nhận | Ý định khôi phục đã được lưu | Cụm hoặc ứng dụng đã áp dụng |
| Kubernetes chấp nhận ConfigMap | Đối tượng API đã được cập nhật | File trong mọi Pod đã đổi |
| Pod template trỏ về bản cấu hình tốt | Pod mới sẽ dùng tham chiếu đó | Mọi Pod đang phục vụ đã được thay |
| Environment hiển thị giá trị tốt | Nguồn thuộc tính có hiệu lực đã đổi | SDK, pool hoặc bean giữ bản sao đã đổi |
| Client thực hiện đúng hành vi | Một luồng sử dụng cấu hình đã được phục hồi | Tất cả replica và tác vụ đã hội tụ |
| Lỗi và độ trễ trở về mức mong muốn | Chất lượng phục vụ được cải thiện | Thay đổi lỗi sẽ không bị hệ thống điều phối áp dụng lại |

Mục tiêu của rollback là khôi phục hành vi phục vụ phù hợp. Khôi phục một file là một bước trong quá trình đó.

## 3. Chuẩn bị một điểm khôi phục đáng tin cậy

### 3.1. “Bản trước” cần được xác định cụ thể

Bản ngay trước một thay đổi chưa chắc là bản tốt. Có thể đã có nhiều lần thử cấu hình trong thời gian ngắn hoặc một canary chưa được đánh giá.

Một điểm khôi phục nên mô tả:

| Thành phần | Thông tin cần giữ |
| --- | --- |
| Ứng dụng | Image hoặc digest đã kiểm chứng |
| Cấu hình | Tên artifact, nội dung và định danh phiên bản |
| Môi trường | Namespace, profile và nguồn ghi đè |
| Secret liên quan | Tham chiếu phiên bản và trạng thái còn hợp lệ |
| Cách áp dụng | Rollout, refresh hoặc cơ chế client tự quản lý |
| Bằng chứng | Kết quả kiểm thử và chỉ số ở điều kiện tải tương ứng |
| Phụ thuộc | Schema, dịch vụ bên ngoài hoặc hợp đồng dữ liệu cần tương thích |

Không đưa nội dung Secret vào bản ghi sự cố hoặc log chỉ để chứng minh cấu hình cũ là gì. Dùng tham chiếu được quản lý và metadata phù hợp.

### 3.2. resourceVersion không phải kho lịch sử cấu hình

Kubernetes sử dụng resourceVersion để biểu diễn phiên bản phục vụ các cơ chế đọc, cập nhật và theo dõi thay đổi. Client phải coi nó là giá trị opaque. [Resource versions trong Kubernetes API](https://kubernetes.io/docs/reference/using-api/api-concepts/).

Đừng dùng resourceVersion làm số thứ tự phát hành, timestamp hoặc giả định có thể lấy lại tùy ý nội dung ConfigMap cũ từ nó. Muốn khôi phục đáng tin cậy phải giữ nội dung đã duyệt trong hệ thống quản lý cấu hình, artifact theo phiên bản hoặc bản lưu được kiểm soát.

Các sự kiện WATCH, audit và metadata có thể hỗ trợ dựng timeline. Chúng không thay thế bản cấu hình hoàn chỉnh sẵn sàng để khôi phục.

### 3.3. Cấu hình đang có hiệu lực có thể đến từ nhiều nguồn

Spring Boot có thứ tự ưu tiên giữa file cấu hình, biến môi trường, system property, tham số dòng lệnh và các nguồn khác. [Thứ tự nguồn cấu hình](https://docs.spring.io/spring-boot/reference/features/external-config.html).

Nếu một biến môi trường vẫn ghi đè timeout thành 50 ms, khôi phục file về 800 ms chưa đủ. Cũng cần kiểm tra profile, cấu hình theo namespace, thứ tự nhập nguồn và các tham chiếu đang dùng.

Một marker như ops.config-revision giúp quan sát nhưng không chứng minh mọi thuộc tính cùng đến từ marker đó. Phải liên hệ marker với nguồn cấu hình và hành vi client thực tế.

## 4. Chọn cách khôi phục theo cách nạp cấu hình

| Cách ứng dụng nhận cấu hình | Hướng khôi phục cần đánh giá |
| --- | --- |
| ConfigMap/Secret theo phiên bản, tham chiếu trong Pod template | Trỏ template về artifact tốt và rollout |
| Biến môi trường từ ConfigMap/Secret | Khôi phục nguồn hoặc tham chiếu, rồi tạo Pod mới |
| File từ volume thông thường | Khôi phục nguồn, chờ file cập nhật, rồi áp dụng lại vào ứng dụng |
| File được mount bằng subPath | Không trông chờ cập nhật tự động; thường cần tạo lại Pod |
| Property source đọc qua API | Khôi phục nguồn và kiểm chứng cơ chế lấy lại/refresh |
| Client hoặc pool không hỗ trợ làm mới an toàn | Ưu tiên ranh giới thay thế phù hợp, thường là tiến trình mới |
| Cấu hình đã kích hoạt thay đổi dữ liệu | Khôi phục cấu hình và xử lý hậu quả dữ liệu riêng |

ConfigMap dùng làm biến môi trường không tự cập nhật tiến trình; volume có thời gian lan truyền và subPath không nhận cập nhật tự động. [Cách Pod tiêu thụ ConfigMap](https://kubernetes.io/docs/concepts/configuration/configmap/).

Quyết định refresh hay restart phải dựa trên đối tượng sử dụng cấu hình. Một bean singleton đã sao chép giá trị vào HTTP client có thể không thay đổi khi property source đổi.

Đối với những cấu hình liên quan nhau, xác định tập cần khôi phục cùng nhau. Không chỉ đổi timeout mà bỏ lại số lần thử lại, backoff hoặc chế độ tính năng của bản lỗi.

## 5. Tình huống: timeout ngắn tạo nhiều lỗi và retry

Giả sử orders gọi một API đọc tồn kho. Trong môi trường thử nghiệm, inventory thường mất 200–300 ms để trả lời. Cấu hình runtime-r17 đã được kiểm chứng dùng timeout 800 ms và tối đa hai lần thử.

Bản runtime-r18 đổi timeout xuống 50 ms và tăng tối đa sáu lần thử. Các giá trị vẫn đúng kiểu dữ liệu nhưng nhiều request bị timeout, gây thêm tải thử lại.

~~~text
runtime-r17
  timeout: 800 ms
  max-attempts: 2
        |
        | thay cấu hình, không đổi image
        v
runtime-r18
  timeout: 50 ms
  max-attempts: 6
        |
        | lỗi xác nhận gắn với thay đổi
        v
khôi phục tập cấu hình runtime-r17
~~~

Đây là giả định minh họa, không phải benchmark hoặc cấu hình khuyến nghị cho mọi dịch vụ. Retry chỉ phù hợp với thao tác đã được đánh giá về idempotency và ngân sách thời gian.

Trong ví dụ, các khóa orders.remote.* và ops.config-revision là hợp đồng do ứng dụng tự định nghĩa. Chúng không phải thuộc tính tự động cấu hình HTTP client có sẵn của Spring Cloud Kubernetes.

## 6. Phương án A: ConfigMap theo phiên bản và rollout

### 6.1. Giữ bản tốt với tên riêng

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-runtime-r17
  namespace: config-ops-lab
  labels:
    app: orders
    config-revision: runtime-r17
immutable: true
data:
  application.yaml: |
    ops:
      config-revision: runtime-r17
    orders:
      remote:
        timeout: 800ms
        max-attempts: 2
        backoff: 100ms
~~~

Bản lỗi có tên khác:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-runtime-r18
  namespace: config-ops-lab
  labels:
    app: orders
    config-revision: runtime-r18
immutable: true
data:
  application.yaml: |
    ops:
      config-revision: runtime-r18
    orders:
      remote:
        timeout: 50ms
        max-attempts: 6
        backoff: 100ms
~~~

ConfigMap immutable ngăn sửa phần dữ liệu của artifact đã đánh dấu. Mỗi lần thay đổi dùng tên mới; cần giữ những bản còn nằm trong cửa sổ khôi phục. [Immutable ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/).

Bất biến không có nghĩa tự được sao lưu hoặc tự không bị xóa. Quyền quản lý và chính sách dọn artifact vẫn cần phù hợp.

### 6.2. Pod template đang trỏ tới bản lỗi

Giả sử ứng dụng và Service đã tồn tại trong namespace config-ops-lab. Deployment dưới đây minh họa trạng thái r18; thay image bằng image ứng dụng thực tế có hỗ trợ các thuộc tính ở trên:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
  namespace: config-ops-lab
spec:
  replicas: 3
  minReadySeconds: 10
  revisionHistoryLimit: 10
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
      annotations:
        training.example.com/config-revision: runtime-r18
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: registry.example.com/training/orders:1.0.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_CONFIG_IMPORT
              value: "file:/etc/orders/application.yaml"
          volumeMounts:
            - name: runtime-config
              mountPath: /etc/orders
              readOnly: true
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
      volumes:
        - name: runtime-config
          configMap:
            name: orders-runtime-r18
~~~

Ứng dụng cần cấu hình Actuator/probe phù hợp. Readiness thể hiện khả năng nhận traffic theo thiết kế; health UP tự nó chưa chứng minh timeout và retry đang đúng.

Trong ví dụ, image không đổi giữa r17 và r18. Trước khi áp dụng vào hệ thống khác, kiểm tra image hiện tại vẫn hiểu đúng cấu hình r17.

### 6.3. Kiểm tra điểm khôi phục trước khi sửa tham chiếu

Các lệnh dưới đây là hướng dẫn trên môi trường thử nghiệm:

~~~bash
kubectl get configmap orders-runtime-r17 -n config-ops-lab -o 'custom-columns=NAME:.metadata.name,IMMUTABLE:.immutable'
kubectl get deployment orders -n config-ops-lab -o yaml
kubectl get pods -n config-ops-lab -l app=orders -o 'custom-columns=POD:.metadata.name,CONFIG:.spec.volumes[*].configMap.name,READY:.status.containerStatuses[*].ready'
~~~

Đối chiếu nội dung r17 với artifact đã duyệt, thay vì chỉ dựa vào tên. Kiểm tra volume runtime-config đúng là ConfigMap cần thay và xác định có tác nhân triển khai nào đang tiếp tục ghi r18 hay không.

### 6.4. Chỉ đổi tham chiếu cấu hình và marker liên quan

Trong ví dụ dùng kubectl trực tiếp, có thể patch theo tên volume:

~~~bash
kubectl patch deployment orders -n config-ops-lab --type=strategic -p '{"spec":{"template":{"metadata":{"annotations":{"training.example.com/config-revision":"runtime-r17"}},"spec":{"volumes":[{"name":"runtime-config","configMap":{"name":"orders-runtime-r17"}}]}}}}'
kubectl rollout status deployment/orders -n config-ops-lab --timeout=300s
~~~

Strategic merge dùng tên volume để ghép phần tử trong trường hợp Deployment này. Kiểm tra lại template sau patch. Nếu cấu trúc thực tế có tham chiếu khác, phải chuẩn bị thay đổi đúng cấu trúc; không sao chép lệnh mà bỏ qua hiện trạng.

Thay đổi Pod template tạo rollout: Pod mới nạp file của r17 khi khởi động, Pod cũ r18 được thay dần. Annotation được đổi cùng tham chiếu để tránh để lại marker r18 trên template đã khôi phục.

Trong hệ thống quản lý khai báo hoặc GitOps, ghi thay đổi vào đúng nguồn điều phối theo quy trình. Một patch khẩn cấp có thể bị controller ghi đè nếu nguồn mong muốn vẫn là r18.

Các giá trị maxUnavailable và maxSurge giúp điều khiển cập nhật, không bảo đảm chất lượng phục vụ trong mọi sự cố. Cần đủ tài nguyên, readiness phù hợp và hành vi drain của ứng dụng.

## 7. Khi nào dùng kubectl rollout undo?

Deployment chỉ tạo revision khi Pod template thay đổi, và rollback quay lại phần template đó. Nó không lưu hoặc tự phục hồi nội dung ConfigMap bị sửa dưới cùng tên. [Phạm vi rollback Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/).

Ví dụ không có bản sao cấu hình:

~~~text
Revision Deployment 7 -> ConfigMap tên orders-runtime
Revision Deployment 8 -> ConfigMap tên orders-runtime

Nội dung orders-runtime đã bị sửa thành cấu hình lỗi.

Quay về revision 7:
    Pod mới vẫn đọc orders-runtime đang chứa nội dung lỗi.
~~~

Nếu dùng ConfigMap theo phiên bản, template cũ có thể giữ tham chiếu tới artifact tốt. Khi đó, rollback Deployment có thể phù hợp, nhưng còn phải kiểm tra image, biến môi trường và các phần khác trong template cũ.

~~~bash
kubectl rollout history deployment/orders -n config-ops-lab
kubectl rollout history deployment/orders -n config-ops-lab --revision=7
~~~

Trong một môi trường đã xác minh rằng revision Deployment 7 chứa đúng tập cần khôi phục, lệnh có thể là:

~~~bash
kubectl rollout undo deployment/orders -n config-ops-lab --to-revision=7
kubectl rollout status deployment/orders -n config-ops-lab --timeout=300s
~~~

Số 7 là giả định của ví dụ, phải lấy từ lịch sử thực tế. Nó không có quan hệ tự động với tên cấu hình runtime-r17.

Nếu chỉ cần đổi cấu hình nhưng revision cũ còn đổi image hoặc biến môi trường không mong muốn, dùng thay đổi đã chuẩn bị cho đúng tập cần phục hồi thay vì hoàn tác toàn bộ template.

Deployment đang paused không thể rollback bằng cơ chế này cho tới khi được resume. Nếu đã dùng pause trong xử lý sự cố, phải đưa trạng thái đó vào kế hoạch khôi phục; “dừng phát hành tiếp theo” không đồng nghĩa cứ pause mọi Deployment. [Paused Deployment và rollback](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/).

## 8. Phương án B: khôi phục ConfigMap sửa tại chỗ và refresh

### 8.1. Giả định của phương án này

Giả sử ứng dụng dùng ConfigMap tên cố định orders-runtime, mount cả thư mục và nhập file application.yaml. Configuration Watcher đã được triển khai để thông báo khi nguồn đó đổi.

Đây là phương án khác với ConfigMap immutable theo phiên bản. Không áp dụng bằng cách sửa data của orders-runtime-r17 đã được đánh dấu immutable.

Một bản mong muốn sau khôi phục có dạng:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-runtime
  namespace: config-ops-lab
  labels:
    spring.cloud.kubernetes.config: "true"
  annotations:
    spring.cloud.kubernetes.configmap.apps: "orders"
data:
  application.yaml: |
    ops:
      config-revision: runtime-r17
    orders:
      remote:
        timeout: 800ms
        max-attempts: 2
        backoff: 100ms
~~~

Nội dung phải lấy từ bản đã được duyệt, với tập khóa và giá trị đầy đủ. Khi khôi phục, kiểm tra cả các khóa mới xuất hiện trong bản lỗi; việc ghép thêm vài giá trị cũ có thể để lại những trường không mong muốn.

Không sao chép nguyên một phản hồi API cũ rồi ghi đè mù quáng metadata vận hành. Khôi phục nội dung và metadata thuộc phạm vi quản lý, đồng thời giữ cơ chế kiểm soát xung đột của hệ thống triển khai.

### 8.2. Chuỗi khôi phục cần đi hết

~~~text
Khôi phục nguồn quản lý về nội dung đã duyệt
    |
    v
Cập nhật orders-runtime
    |
    v
File hoặc API property source nhận dữ liệu tốt
    |
    v
Watcher hoặc cơ chế điều phối kích hoạt áp dụng
    |
    v
Bean/client phù hợp được cập nhật
    |
    v
Kiểm chứng từng replica và luồng nghiệp vụ
~~~

Configuration Watcher hỗ trợ theo dõi ConfigMap có nhãn phù hợp, xác định ứng dụng đích và gửi refresh. Annotation apps hữu ích khi tên ConfigMap khác tên ứng dụng. [Configuration Watcher và đích cập nhật](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Watcher không phải kho lịch sử và không tự chọn bản cấu hình tốt. Nó chỉ tham gia truyền thay đổi tới ứng dụng theo cơ chế được cấu hình.

Nếu nguồn được nạp qua API, kiểm tra client nhận phiên bản mới và property source được áp dụng. Nếu nguồn là volume, phải kiểm tra file trước khi kết luận refresh đã đọc đúng dữ liệu.

### 8.3. Thông báo có thể tới trước file

Việc API chấp nhận ConfigMap và việc kubelet cập nhật file là những mốc khác nhau. Một thông báo refresh quá sớm có thể khiến ứng dụng đọc lại file vẫn còn dữ liệu lỗi.

Watcher có cấu hình khoảng chờ trước thông báo, chẳng hạn trích đoạn trong Deployment của chính Watcher:

~~~yaml
env:
  - name: SPRING_CLOUD_KUBERNETES_RELOAD_NAMESPACES_0
    value: "config-ops-lab"
  - name: SPRING_CLOUD_KUBERNETES_CONFIGURATION_WATCHER_REFRESHDELAY
    value: "10000"
~~~

Giá trị 10000 là ví dụ cần đo theo môi trường. Không dùng một khoảng chờ cố định làm bằng chứng mọi volume đã hội tụ. [Khoảng chờ refresh của Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Nếu lần refresh đầu chưa áp dụng đúng bản tốt, cần cách chờ hoặc thử lại có giới hạn và quan sát được. Tránh gửi refresh liên tục mà không biết property source đang chứa gì.

### 8.4. Refresh không phải giao dịch nguyên tử cho mọi bean

Một lần refresh được chấp nhận chưa chứng minh tất cả client đã được dựng lại thành công. Bean lazy có thể chỉ bộc lộ lỗi ở lần sử dụng sau.

Nếu ứng dụng có nhiều đối tượng phụ thuộc cùng một tập cấu hình, cần thiết kế cách áp dụng nhất quán. Không để request thấy timeout r17 nhưng endpoint hoặc chính sách retry vẫn thuộc r18.

Có thể dùng quy trình candidate trong ứng dụng tự quản lý:

~~~text
Đọc snapshot cấu hình cần khôi phục
    -> kiểm tra kiểu, ràng buộc và quan hệ giữa các trường
    -> dựng candidate client
    -> chạy phép thử an toàn
    -> công bố candidate theo cơ chế đồng bộ phù hợp
    -> xử lý request còn giữ client trước đó
~~~

Đây là thiết kế cần được triển khai và kiểm thử, không phải hành vi tự có của mọi annotation refresh. Nếu đối tượng không hỗ trợ cập nhật an toàn, dùng rollout để có tiến trình mới là phương án cần đánh giá.

Endpoint refresh phải được bảo vệ và giới hạn đường truy cập. Khi dùng HTTP qua Service, một lần gọi có thể chỉ tới một replica; không dùng nó thay cho cơ chế xác nhận trên từng Pod.

## 9. Xác minh đã khôi phục hành vi phục vụ

### 9.1. Quan sát ba lớp bằng chứng

Một quy trình xác minh nên có:

1. **Tham chiếu:** workload hoặc nguồn mutable đã về đúng artifact/nội dung.
2. **Trạng thái sử dụng:** từng tiến trình và client đã nhận bản tốt.
3. **Hành vi:** request đi qua đường bị ảnh hưởng đã hoạt động đúng.

Các lệnh kiểm kê cho ví dụ rollout:

~~~bash
kubectl get deployment orders -n config-ops-lab -o yaml
kubectl get pods -n config-ops-lab -l app=orders -o 'custom-columns=POD:.metadata.name,CONFIG:.spec.volumes[*].configMap.name,READY:.status.containerStatuses[*].ready'
kubectl get endpointslices -n config-ops-lab -l kubernetes.io/service-name=orders -o yaml
kubectl rollout status deployment/orders -n config-ops-lab --timeout=300s
~~~

Đối với file không chứa bí mật của bài, có thể kiểm tra trên một Pod cụ thể:

~~~bash
kubectl exec -n config-ops-lab orders-example -c app -- cat /etc/orders/application.yaml
~~~

Thay orders-example bằng tên Pod thực tế; lệnh giả định image có cat. Không áp dụng cách in file này cho cấu hình có Secret hoặc dữ liệu nhạy cảm.

File đúng vẫn chưa đủ. HTTP client có thể giữ cấu hình đã sao chép lúc khởi tạo hoặc một nguồn khác có thể ghi đè giá trị.

### 9.2. Thiết kế trạng thái quan sát không lộ dữ liệu

Ứng dụng có thể cung cấp một endpoint nội bộ tự xây dựng, ví dụ:

~~~json
{
  "pod": "orders-example",
  "loadedConfig": "runtime-r17",
  "activeClientConfig": "runtime-r17",
  "lastBehaviorCheck": "PASS"
}
~~~

Đây không phải endpoint có sẵn của Spring Cloud Kubernetes. activeClientConfig cần phản ánh client thật sự xử lý request; không chỉ đọc marker từ Environment rồi gắn nhãn cho toàn bộ trạng thái.

Nếu dùng actuator env hoặc configprops để chẩn đoán, chỉ expose và cấp quyền theo nhu cầu. Không bật hiển thị toàn bộ giá trị như một bước rollback mặc định. [Quản lý và bảo vệ Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).

### 9.3. Không chỉ thử qua Service một lần

Một request thành công có thể liên tục được định tuyến tới một Pod tốt trong khi replica khác vẫn dùng cấu hình lỗi.

Cần kiểm tra các Pod đang phục vụ và những consumer liên quan:

- Replica chính, canary và Pod đang drain.
- Worker xử lý nền hoặc Job cũng dùng nguồn cấu hình.
- Template của tác vụ có thể tạo Pod mới sau đó.
- Instance ở namespace khác nếu cùng nhận thông báo cập nhật.

DiscoveryClient hoặc danh sách endpoint giúp xác định một phần instance, nhưng không thay thế danh mục đầy đủ các consumer. Cũng cần xem cache của Spring Cloud LoadBalancer hoặc proxy còn giữ đích cũ hay không.

### 9.4. Dùng tải và thao tác phù hợp

Với lỗi timeout/retry của bài, đo lại:

| Tín hiệu | Điều cần chứng minh |
| --- | --- |
| Lỗi timeout ở orders | Giảm theo mức mong đợi sau khi dùng r17 |
| Số lần gọi inventory trên một request | Trở lại chính sách thử lại đúng |
| Độ trễ request | Phù hợp ngân sách của luồng |
| Tải và lỗi ở inventory | Không còn bị khuếch đại bởi r18 |
| Cấu hình client theo replica | Không còn Pod phục vụ bằng r18 |
| Readiness và số replica available | Đủ năng lực phục vụ |
| Tác vụ chạy lâu hoặc theo lịch | Không tiếp tục tạo tải bằng cấu hình lỗi |

So sánh ở điều kiện tải tương ứng và trong cửa sổ quan sát đủ cho luồng bị ảnh hưởng. Không chọn số request hoặc thời gian chung cho mọi ứng dụng.

Một thao tác kiểm tra nên đi qua cùng client và cùng chính sách bị thay đổi. Health endpoint chỉ xác nhận tiến trình còn sống không thể thay thế phép thử đó.

## 10. Những giới hạn dễ làm rollback thất bại

### 10.1. Xóa khóa cấu hình không nhất thiết khôi phục mặc định đang chạy

Nếu r18 thêm một khóa mà r17 không có, việc bỏ khóa khỏi nguồn rồi refresh không bảo đảm đối tượng đang chạy quay về trạng thái mặc định mong muốn. Spring Cloud nêu hạn chế của việc xóa giá trị trong quá trình refresh. [Refresh và khóa cấu hình bị xóa](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html).

Với trường hợp này, xác định rõ giá trị mong muốn, kiểm tra khả năng bind lại hoặc dùng một tiến trình mới. Không tự thêm giá trị “trung tính” nếu chưa biết đúng ngữ nghĩa của thuộc tính.

### 10.2. Một số cấu hình hoặc đối tượng cần khởi động lại

Thay đổi cổng, vòng đời bean, một số thiết lập khởi tạo hoặc client có state có thể không phù hợp refresh tại chỗ. HikariDataSource là trường hợp được tài liệu Spring Cloud nêu là không thể refresh theo cơ chế thông thường. [Giới hạn Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html).

Không thêm @RefreshScope vào mọi bean để xử lý sự cố. Chọn lại ranh giới áp dụng, thường là rollout hoặc cơ chế thay client được hỗ trợ.

### 10.3. Cấu hình cũ có thể không còn tương thích

Bản r17 từng hoạt động tốt với image cũ chưa chắc hoạt động với image hiện tại. Có thể đã thay tên thuộc tính, kiểu dữ liệu, profile hoặc hợp đồng dịch vụ.

Nếu cần khôi phục cả image, phải kiểm tra tương thích với dữ liệu và phụ thuộc đang tồn tại. Điều kiện quan trọng là “bộ thành phần tương thích đã được kiểm chứng”, không chỉ “cấu hình có số nhỏ hơn”.

### 10.4. Secret cũ có thể đã bị thu hồi

Quay về tham chiếu Secret cũ không làm token hoặc mật khẩu tự có hiệu lực trở lại ở phía nhận. Không khôi phục credential đã bị thu hồi hoặc nghi lộ chỉ để làm trạng thái deployment giống trước.

Có thể cần giữ cấu hình tốt nhưng tham chiếu credential mới còn hợp lệ, rồi kiểm chứng bộ kết hợp đó. Ghi rõ đây là một cấu hình khôi phục được chuẩn bị, không phải sao chép nguyên xi mọi dữ liệu cũ.

### 10.5. Tác dụng phụ không tự bị hoàn tác

Nếu cấu hình lỗi đã tạo giao dịch, phát sự kiện hoặc ghi dữ liệu sai, rollback chỉ ngăn hoặc thay đổi hành vi từ thời điểm áp dụng. Nó không tự đảo ngược các tác dụng phụ đã xảy ra.

Tách việc khôi phục phục vụ khỏi xử lý dữ liệu: xác định phạm vi ảnh hưởng, cơ chế bù trừ và quyền thực hiện. Với retry, không thử lại thao tác có tác dụng phụ chỉ vì cấu hình đã được sửa mà chưa đánh giá tính trùng lặp.

### 10.6. Phân biệt thứ tự điều phối và phiên bản nội dung

Rollback đưa nội dung r17 trở lại là một quyết định vận hành mới. Nếu mã ứng dụng chỉ chấp nhận tên cấu hình có số lớn hơn r18, nó có thể từ chối chính bản cần khôi phục.

Có thể quản lý hai định danh:

~~~json
{
  "changeId": "rollback-attempt-042",
  "targetConfig": "runtime-r17"
}
~~~

changeId biểu diễn lần điều phối mới; targetConfig biểu diễn nội dung muốn dùng. Đây là thiết kế metadata của hệ thống, không phải field chuẩn bắt buộc của Kubernetes.

Khi xử lý thông báo chậm, không để một thông báo cũ tự đưa r18 trở lại sau khi đã quyết định r17. Cơ chế áp dụng cần đọc đúng trạng thái mong muốn hiện hành, có kiểm soát tính lặp lại và xung đột.

## 11. Runbook xử lý một thay đổi cấu hình gây lỗi

### 11.1. Xác nhận và giới hạn thay đổi đang diễn ra

Ghi nhận thời điểm lỗi bắt đầu, lần thay đổi gần nhất, namespace, workload và luồng bị ảnh hưởng. Kiểm tra mối liên hệ bằng log, metric và hành vi; không mặc định mọi lỗi xuất hiện gần thời điểm triển khai đều do cấu hình.

Ngăn hệ thống phát hành tiếp tục mở rộng thay đổi lỗi theo quy trình của tổ chức. Với GitOps hoặc controller khác, làm rõ nguồn nào đang giữ trạng thái mong muốn để tránh hai tác nhân liên tục ghi đè nhau.

Giữ bằng chứng tối thiểu cần thiết của r18 phục vụ điều tra, đồng thời bảo vệ dữ liệu nhạy cảm.

### 11.2. Chọn điểm khôi phục và cơ chế áp dụng

Trả lời rõ:

- Bản tốt nào đã được xác minh, còn tồn tại và còn tương thích?
- Nguồn cần sửa là file triển khai, ConfigMap, Secret hay tham chiếu template?
- Cần refresh hay tạo tiến trình mới?
- Có thay đổi nào chưa thể hoàn tác, như credential đã thu hồi hoặc schema đã đổi?
- Cần khôi phục những workload và consumer nào?
- Ai hoặc thành phần nào chịu trách nhiệm xác minh?

Nếu không có bản cũ đáng tin cậy, phải chuẩn bị một cấu hình sửa lỗi có kiểm chứng. Không tự đoán “giá trị mặc định trước đây” trong lúc sự cố.

### 11.3. Áp dụng, theo dõi và xác nhận

Thực hiện đúng tập thay đổi đã chuẩn bị, với xung đột và quyền ghi được kiểm soát. Quan sát tiến độ phân phối, tạo Pod hoặc refresh.

Một mô hình thời gian phục hồi có thể phân rã:

~~~text
T_recovery = T_detect
           + T_decide
           + T_distribute
           + T_apply
           + T_verify
~~~

Giữ artifact tốt, metadata rõ và runbook đã diễn tập giúp giảm những giai đoạn này. Không chỉ đo thời gian lệnh kubectl chạy xong.

Nếu quá trình không tiến triển, xác định lớp bị chặn: artifact không còn, mount lỗi, API/RBAC, mạng, bean không refresh được, Pod không ready hoặc nguồn điều phối ghi đè. Tránh restart hàng loạt trước khi biết restart có đưa tiến trình về nguồn đúng hay không.

### 11.4. Hoàn tất trạng thái nguồn và lưu giữ

Sau khi phục vụ ổn định:

1. Đồng bộ nguồn cấu hình được quản lý với trạng thái khôi phục.
2. Ghi lại bản gây lỗi, bản được chọn, cơ chế áp dụng và kết quả xác minh.
3. Giữ artifact và revision còn cần cho cửa sổ khôi phục.
4. Dọn bản cũ theo chính sách sau khi kiểm tra mọi tham chiếu.
5. Chuẩn bị thay đổi sửa lỗi tiếp theo qua kiểm thử và phạm vi phù hợp.

Không xóa ConfigMap tốt ngay khi rollout báo thành công nếu Job, canary hoặc revision còn cần nó. Ngược lại, giữ lịch sử Deployment không thay thế việc giữ ConfigMap và image mà revision tham chiếu.

### 11.5. Quyền và đường truy cập

Ứng dụng chỉ đọc file không tự cần quyền sửa ConfigMap. Configuration Watcher cần quyền và mạng theo phạm vi theo dõi; công cụ rollback cần quyền thay đổi đúng tài nguyên được giao.

Lỗi 403 từ API, timeout tới actuator hoặc thiếu quyền patch là những lỗi cần xử lý ở đúng lớp. Không cấp cluster-admin hoặc mở mọi cổng để biến rollback thành công bằng mọi giá.

Việc ghi Secret, gọi refresh và sửa Deployment nên có dấu vết kiểm toán phù hợp. Không dùng log chứa toàn bộ cấu hình như cơ chế audit mặc định.

## 12. Bài thực hành và điều kiện hoàn thành

### 12.1. Kịch bản chính

Trong môi trường thử nghiệm có workload theo ví dụ:

1. Duy trì tải đọc inventory bằng cấu hình r17, ghi lại lỗi và độ trễ nền.
2. Triển khai r18 trên phạm vi kiểm soát để quan sát timeout và retry.
3. Xác định r17 là điểm khôi phục và kiểm tra artifact vẫn còn.
4. Đổi tham chiếu về r17 hoặc dùng revision Deployment đã xác minh phù hợp.
5. Theo dõi rollout và kiểm tra từng client đang phục vụ.
6. Xác nhận hành vi đọc inventory cùng các chỉ số đã phục hồi.
7. Kiểm tra nguồn điều phối không tự áp dụng lại r18.

Các lệnh, giá trị và manifest trong bài là hướng dẫn thực hành. Chúng không phải kết quả đo đã chạy trên một cụm cụ thể.

### 12.2. Các tình huống bổ sung

| Tình huống | Điều cần chứng minh |
| --- | --- |
| ConfigMap cùng tên bị sửa, chỉ rollout undo | Nhận ra template cũ vẫn đọc nội dung hiện tại |
| Biến môi trường ghi đè file đã khôi phục | Tìm đúng nguồn có ưu tiên cao hơn |
| File đã là r17 nhưng client giữ r18 | Phát hiện ở lớp sử dụng và chọn cơ chế áp dụng lại |
| Một replica không nhận thông báo refresh | Không kết luận từ một request thành công qua Service |
| Artifact r17 đã bị dọn | Runbook phát hiện trước khi làm Pod mới lỗi mount |
| Khóa của r18 không có trong r17 | Kiểm chứng xóa/bind lại hoặc dùng tiến trình mới |
| Source controller tiếp tục ghi r18 | Giải quyết trạng thái mong muốn và quyền sở hữu thay đổi |
| Secret cũ đã mất hiệu lực | Không dùng rollback cấu hình để khôi phục credential không hợp lệ |

### 12.3. Bằng chứng hoàn thành

Bài thực hành đạt mục tiêu khi:

- Có điểm khôi phục rõ ràng và còn tương thích.
- Nguồn cấu hình và tham chiếu đã đúng.
- Từng consumer cần thiết dùng cấu hình tốt trong đối tượng thực thi.
- Luồng bị ảnh hưởng và chất lượng phục vụ đã được kiểm chứng.
- Những tác dụng phụ còn lại được nhận diện và xử lý riêng.
- Hệ thống điều phối không đưa thay đổi lỗi trở lại.
- Lịch sử và artifact cần thiết được giữ theo chính sách.

Một quy trình rollback đáng tin cậy phải nối được bản cấu hình đã duyệt với hành vi đang phục vụ. Mỗi bước chuyển cần có bằng chứng ở đúng lớp thay vì chỉ dựa vào một thông báo cập nhật thành công.
