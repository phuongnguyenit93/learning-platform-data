# Giới hạn cập nhật của biến môi trường và volume

## Mục tiêu bài học

Trong chương **Cập nhật cấu hình** của module **SPRING_CLOUD_KUBERNETES**, một trong những lỗi dễ gây hiểu nhầm nhất là ConfigMap đã đổi nhưng ứng dụng vẫn sử dụng giá trị cũ. Nguyên nhân thường nằm ở cách đưa dữ liệu vào container và thời điểm ứng dụng đọc dữ liệu.

Sau bài học, bạn có thể:

- Giải thích vì sao biến môi trường của tiến trình đang chạy không đổi theo ConfigMap hoặc Secret.
- Phân biệt mount thư mục thông thường, mount bằng `subPath` và bản sao do ứng dụng tạo.
- Nhận biết độ trễ cập nhật volume, ảnh hưởng của file descriptor và giới hạn khi đọc nhiều nguồn.
- Phân biệt file đã đổi với Spring Environment, bean và tài nguyên ứng dụng đã đổi.
- Chọn rollout hoặc refresh theo khả năng thực tế của ứng dụng, đồng thời kiểm tra đúng lớp.

Bài học tập trung vào cơ chế nhận và sử dụng dữ liệu cấu hình. DiscoveryClient và Spring Cloud LoadBalancer không thay thế cơ chế này; Configuration Watcher cũng không biến mọi dạng cấu hình thành cấu hình có thể cập nhật trực tiếp.

## 1. Ba lớp cần kiểm tra riêng

Hãy xét thuộc tính timeout đang có giá trị `2s`, cần đổi sang `3s`:

```text
ConfigMap/Secret trong Kubernetes API
                |
                v
Biến môi trường hoặc file nhìn thấy trong container
                |
                v
Giá trị và tài nguyên ứng dụng đang sử dụng
```

Ba sự kiện khác nhau có thể xảy ra ở ba thời điểm:

| Lớp | Câu hỏi phải trả lời | Bằng chứng phù hợp |
|---|---|---|
| Tài nguyên Kubernetes | Bản dữ liệu mới đã được lưu chưa? | Giá trị không nhạy cảm hoặc định danh phiên bản ở đúng namespace |
| Container | Tiến trình nhận dữ liệu qua env hay file? Dữ liệu nhìn thấy đã đổi chưa? | Quan sát đúng biến hoặc đúng đường dẫn trong đúng container |
| Ứng dụng | Bean, client hoặc tác vụ nghiệp vụ đã sử dụng bản mới chưa? | Dấu vết cấu hình hiệu lực và phép thử hành vi |

`kubectl apply` thành công chỉ xác nhận thao tác lên tài nguyên được chấp nhận. Kết quả đó chưa chứng minh một tiến trình đang chạy đã đổi môi trường, đã mở lại file hoặc đã tái tạo HTTP client.

Ví dụ, cả hai trạng thái sau đều có thể hợp lệ về mặt cơ chế:

- API có `3s`, volume đã có `3s`, nhưng bean Spring còn giữ `2s`.
- Pod tạo trước thay đổi dùng env `2s`, Pod tạo sau thay đổi dùng env `3s`, dù cả hai thuộc cùng một Deployment.

## 2. Bảng giới hạn theo cách nhận cấu hình

| Cách nhận dữ liệu | Khi sửa dữ liệu của cùng ConfigMap/Secret | Việc ứng dụng cần làm |
|---|---|---|
| `env.valueFrom.configMapKeyRef` | Không sửa môi trường của tiến trình đang chạy | Khởi động instance mới theo quy trình rollout |
| `env.valueFrom.secretKeyRef` | Tương tự env từ ConfigMap | Khởi động instance mới; xác minh credential còn hợp lệ |
| `envFrom` | Không phải liên kết động với từng key trong nguồn | Tạo lại instance để nhận bộ môi trường mới |
| Mount ConfigMap/Secret thành thư mục | Các file được chiếu vào volume có thể đổi sau một khoảng trễ | Đọc lại đúng đường dẫn và áp dụng dữ liệu mới |
| Mount bằng `subPath` | Không nhận cập nhật tự động từ nguồn đó | Tạo lại Pod hoặc thay cách mount |
| Sao chép từ volume sang `emptyDir` khi khởi động | Bản sao không tự đi theo nguồn | Có cơ chế sao chép lại và áp dụng lại, hoặc tạo Pod mới |
| Đọc file một lần vào bộ nhớ | File có thể mới nhưng bộ nhớ vẫn cũ | Tải lại dữ liệu hoặc khởi động lại |
| Spring Cloud Kubernetes đọc qua API | Không đi qua đường cập nhật file của kubelet | Cần cơ chế đọc lại/refresh phù hợp với thư viện |

Các đặc tính cập nhật của env, volume và `subPath` được Kubernetes mô tả trong [ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/) và [Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).

Trong bài này, “volume” là các volume nhận dữ liệu ConfigMap/Secret theo cơ chế Kubernetes thông thường. Không suy rộng toàn bộ kết luận sang mọi loại volume, CSI driver hay projected service account token vì các loại đó có vòng đời riêng.

## 3. Biến môi trường là đầu vào khi tiến trình được khởi tạo

### 3.1. Tham chiếu key không phải cơ chế theo dõi

Ví dụ một phần Pod spec:

```yaml
env:
  - name: APP_CHECKOUT_TIMEOUT
    valueFrom:
      configMapKeyRef:
        name: checkout-config
        key: checkout-timeout
  - name: PAYMENT_API_TOKEN
    valueFrom:
      secretKeyRef:
        name: payment-credentials
        key: token
```

Kubernetes dùng nguồn này để chuẩn bị môi trường khi tạo container. Khi ConfigMap đổi, Kubernetes không đi vào JVM đang chạy để thay giá trị `System.getenv("APP_CHECKOUT_TIMEOUT")`.

`envFrom` cũng không bổ sung khả năng cập nhật trực tiếp. Nó chỉ thay cách lựa chọn nhiều key khi chuẩn bị môi trường.

Đối với tiến trình đã chạy, việc gọi lại `System.getenv` không phải một lần truy vấn mới đến Kubernetes API.

### 3.2. Chỉnh môi trường của shell không chỉnh được JVM khác

Chạy `export APP_CHECKOUT_TIMEOUT=3s` trong một shell được mở bằng `kubectl exec` chỉ tác động tới shell đó và các tiến trình con do nó tạo sau đó. Nó không cập nhật môi trường của JVM chính vốn đã được khởi động trước.

Tương tự, một sidecar không thể làm tiến trình Java tự nhận bộ env mới chỉ bằng cách sửa môi trường của chính sidecar.

Khi cần nhận env mới, cách vận hành rõ ràng là rollout để tạo Pod mới. Không dùng việc giết tiến trình, chờ crash hoặc trông cậy container khởi động lại ngoài kế hoạch làm quy trình phân phối cấu hình.

### 3.3. Dữ liệu env có thể khác nhau giữa các Pod

Nếu ConfigMap được sửa nhưng không rollout toàn bộ Deployment:

1. Pod A được tạo trước thay đổi giữ env cũ.
2. Một lần tăng replica hoặc thay Pod vì lý do khác tạo Pod B.
3. Pod B có thể nhận dữ liệu mới tại thời điểm khởi động.
4. Service phân phối yêu cầu đến cả A và B, làm hành vi ứng dụng không đồng nhất.

Tài liệu [cập nhật cấu hình qua ConfigMap](https://kubernetes.io/docs/tutorials/configuration/updating-configuration-via-a-configmap/#update-environment-variables-of-a-pod-via-a-configmap) minh họa chính tình huống env cũ và mới tồn tại ở các Pod khác nhau.

Do đó, khi điều tra lỗi, phải ghi nhận cả tên Pod, thời điểm tạo, số lần restart và phiên bản cấu hình hiệu lực.

## 4. Mount thư mục: file có thể đổi, nhưng không tức thời

### 4.1. Đường cập nhật qua kubelet

Ví dụ mount toàn bộ ConfigMap vào một thư mục:

```yaml
volumeMounts:
  - name: checkout-config
    mountPath: /etc/checkout-config
    readOnly: true

volumes:
  - name: checkout-config
    configMap:
      name: checkout-config
```

Khi dữ liệu trong ConfigMap `checkout-config` thay đổi, kubelet có thể cập nhật nội dung được chiếu vào volume trên node đang chạy Pod. Container không cần có quyền gọi API để nhận cập nhật theo đường này.

`readOnly: true` có nghĩa container không được ghi vào mount. Nó không ngăn kubelet đưa dữ liệu mới từ nguồn vào volume.

### 4.2. Không có thời gian chờ cố định áp dụng cho mọi cụm

Độ trễ chịu ảnh hưởng của chu kỳ đồng bộ kubelet và cách kubelet phát hiện thay đổi: watch, cache có TTL hoặc đọc trực tiếp API. Kubernetes không quy định một mốc cố định kiểu “đúng 10 giây thì mọi Pod đều nhận được”.

Một cách mô tả định tính:

```text
Thời gian đến lúc file mới xuất hiện
  phụ thuộc độ trễ phát hiện/cache
  + chu kỳ đồng bộ kubelet
  + tình trạng kết nối và hoạt động thực tế của node
```

Cơ chế và thành phần độ trễ được nêu trong [Mounted ConfigMaps are updated automatically](https://kubernetes.io/docs/concepts/configuration/configmap/#mounted-configmaps-are-updated-automatically).

Các Pod ở những node khác nhau không nhất thiết cập nhật cùng thời điểm. “Cuối cùng sẽ nhất quán” không phải một giao dịch đồng thời trên toàn bộ replica.

### 4.3. Nguồn phải vẫn là nguồn mà Pod tham chiếu

Pod đang mount `checkout-config-v1` không tự chuyển sang `checkout-config-v2` chỉ vì bạn tạo tài nguyên V2. Tên nguồn trong Pod spec vẫn là V1.

Với tài nguyên `immutable: true`, không sửa được dữ liệu của tài nguyên đó. Muốn áp dụng bản mới, tạo nguồn mới rồi thay tham chiếu trong template của workload và triển khai Pod mới.

Đừng xóa rồi tạo lại một nguồn cùng tên để giả lập cập nhật an toàn. Thao tác đó làm vòng đời và khả năng truy vết khó kiểm soát, đặc biệt khi Pod cũ còn tham chiếu nguồn cũ.

## 5. Giới hạn đặc biệt của subPath và bản sao

### 5.1. subPath chỉ mount một phần đường dẫn

Ví dụ mount riêng một file:

```yaml
volumeMounts:
  - name: checkout-config
    mountPath: /etc/app/checkout.yaml
    subPath: application.yaml
    readOnly: true
```

Cách này hữu ích khi cần đặt một file vào đường dẫn cụ thể mà không mount cả thư mục. Tuy nhiên, ConfigMap/Secret dùng qua `subPath` không nhận cập nhật tự động của nguồn. Chờ lâu hơn hoặc gọi Spring refresh không làm đường mount đó tự chuyển sang dữ liệu mới.

Nếu cần đọc file thay đổi trong vòng đời Pod, ưu tiên mount thư mục riêng, chẳng hạn `/etc/checkout-config`, rồi chỉ cấu hình ứng dụng đọc file trong thư mục đó.

Nếu chọn `subPath` vì yêu cầu ứng dụng, hãy coi thay cấu hình là một thay đổi cần tạo lại Pod.

### 5.2. Tránh hiểu sai khi mount che thư mục có sẵn

Mount một volume lên `/etc/app` làm nội dung volume được nhìn thấy tại đó, che nội dung sẵn có của image ở cùng đường dẫn. Đây không phải thao tác hợp nhất mọi file từ image với ConfigMap.

Một thiết kế đơn giản là dành thư mục riêng cho cấu hình ngoài rồi truyền vị trí đó cho ứng dụng. Nếu cần hợp nhất hoặc dựng file từ nhiều nguồn, phải quản lý vòng đời của bản kết quả.

### 5.3. Sao chép khi khởi động tạo thêm một lớp dữ liệu

Ví dụ luồng thường gặp:

```text
ConfigMap volume
      |
      | init container sao chép một lần
      v
emptyDir chứa file kết quả
      |
      v
Ứng dụng đọc file kết quả
```

Sau khi init container hoàn thành, nguồn ConfigMap có cập nhật cũng không tự sao chép lại vào `emptyDir`. Một sidecar có thể thực hiện việc đồng bộ, nhưng khi đó cần giải quyết thêm cách ghi file an toàn, kiểm tra dữ liệu và báo cho ứng dụng đọc lại.

Cùng nguyên tắc đó áp dụng cho entrypoint sinh file bằng envsubst hoặc script đọc biến môi trường: file sinh ra không trở thành nguồn cập nhật trực tiếp chỉ vì đầu vào ban đầu đến từ Kubernetes.

## 6. Đọc file: mở lại đường dẫn và giữ cấu hình nhất quán

### 6.1. Không mặc định file được ghi đè tại chỗ

Trên Linux, cơ chế chiếu dữ liệu của Kubernetes sử dụng các thế hệ thư mục và liên kết tượng trưng để chuyển sang dữ liệu mới. Cơ chế này được thể hiện trong [AtomicWriter của Kubernetes](https://github.com/kubernetes/kubernetes/blob/master/pkg/volume/util/atomic_writer.go).

Hệ quả khi thiết kế bộ đọc file:

- Stream hoặc file descriptor đã mở có thể tiếp tục trỏ tới dữ liệu của thế hệ cũ.
- Theo dõi đúng một inode chưa chắc bắt được cách thay thế dữ liệu.
- Sau tín hiệu thay đổi, ứng dụng nên mở lại đường dẫn cấu hình và xử lý lỗi đọc tạm thời.
- Bộ theo dõi file cần được kiểm tra với cơ chế volume thực tế; không chỉ kiểm tra bằng cách sửa file thông thường trên máy phát triển.

Không viết mã nghiệp vụ phụ thuộc tên thư mục nội bộ như `..data`. Đó là chi tiết cần hiểu khi chẩn đoán và xây bộ theo dõi, không phải hợp đồng cấu hình của ứng dụng.

### 6.2. Nhiều lần đọc không phải một giao dịch ứng dụng

Việc công bố một thế hệ file không bảo đảm mọi lần mở file riêng rẽ của ứng dụng cùng nhìn thấy một thế hệ. Nếu đọc username trước thời điểm chuyển rồi đọc password sau đó, cần tính đến khả năng tổ hợp dữ liệu không nhất quán.

Đối với hai tài nguyên khác nhau, như ConfigMap và Secret, càng không có giao dịch chung bảo đảm chúng đến mọi Pod cùng lúc.

Đây là hệ quả thiết kế cần tự xử lý:

1. Đọc toàn bộ ứng viên cấu hình vào một đối tượng tạm.
2. Phân tích và kiểm tra tất cả trường liên quan.
3. Xác minh các điều kiện tương thích cần thiết.
4. Chỉ công bố đối tượng mới sau khi toàn bộ bước trên thành công.
5. Mỗi yêu cầu nên giữ một snapshot cấu hình cho suốt phần xử lý cần nhất quán.

Với một bộ giá trị liên quan chặt chẽ và không nhạy cảm, dùng một tài liệu cấu hình có định danh phiên bản giúp giảm rủi ro ghép dữ liệu. Tuy nhiên, điều đó vẫn không tạo giao dịch giữa file, bean và hệ thống bên ngoài.

## 7. Thí nghiệm: cùng một ConfigMap, ba cách đọc

Thí nghiệm dùng dữ liệu không nhạy cảm và một container Linux có shell, nhằm tách hành vi Kubernetes khỏi Spring. Bạn cần cụm lab, kubectl và quyền tạo namespace hoặc thay namespace ví dụ bằng namespace lab đã được cấp.

Tạo tài liệu triển khai `config-limits-lab.yaml` với nội dung:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: config-update-lab
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: limits-demo
  namespace: config-update-lab
data:
  checkout-timeout: "2s"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: config-observer
  namespace: config-update-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: config-observer
  template:
    metadata:
      labels:
        app: config-observer
    spec:
      automountServiceAccountToken: false
      containers:
        - name: observer
          image: busybox:1.36.1
          command:
            - /bin/sh
            - -c
          args:
            - |
              while true; do
                echo "env=$CHECKOUT_TIMEOUT volume=$(cat /etc/live-config/checkout-timeout) subPath=$(cat /tmp/checkout-timeout-fixed)"
                sleep 5
              done
          env:
            - name: CHECKOUT_TIMEOUT
              valueFrom:
                configMapKeyRef:
                  name: limits-demo
                  key: checkout-timeout
          volumeMounts:
            - name: config
              mountPath: /etc/live-config
              readOnly: true
            - name: config
              mountPath: /tmp/checkout-timeout-fixed
              subPath: checkout-timeout
              readOnly: true
      volumes:
        - name: config
          configMap:
            name: limits-demo
```

Image BusyBox ở đây chỉ chạy công cụ quan sát. Khi áp dụng quy trình quản lý image của tổ chức, có thể thay bằng image Linux tương đương được cho phép và ghim digest. Thí nghiệm không phải manifest đầy đủ cho một dịch vụ Spring production.

### 7.1. Quan sát mốc ban đầu

```bash
kubectl config current-context
kubectl apply -f config-limits-lab.yaml
kubectl rollout status deployment/config-observer -n config-update-lab --timeout=120s
kubectl logs deployment/config-observer -n config-update-lab --tail=5
kubectl get pods -n config-update-lab -l app=config-observer -o custom-columns='POD:.metadata.name,UID:.metadata.uid,RESTARTS:.status.containerStatuses[0].restartCount'
```

Kết quả log dự kiến:

```text
env=2s volume=2s subPath=2s
```

Ghi nhận Pod và UID để biết các quan sát tiếp theo còn thuộc cùng một Pod.

### 7.2. Chỉ đổi dữ liệu ConfigMap

Trong file trên, đổi duy nhất `data.checkout-timeout` từ `"2s"` thành `"3s"`. Không sửa Pod template.

```bash
kubectl apply -f config-limits-lab.yaml
kubectl get configmap limits-demo -n config-update-lab -o jsonpath='{.data.checkout-timeout}'
kubectl logs deployment/config-observer -n config-update-lab --tail=5
```

Đọc log lại sau các khoảng chờ phù hợp để thấy sự chuyển đổi. Không đặt điều kiện rằng mọi cụm phải cập nhật trong một số giây cố định.

Sau khi volume đã nhận dữ liệu mới, kết quả dự kiến:

```text
env=2s volume=3s subPath=2s
```

Giải thích:

- `env` giữ giá trị đã có khi container được tạo.
- Lệnh `cat` trong vòng lặp mở lại file ở mount thư mục nên có thể nhìn thấy dữ liệu mới.
- File mount qua `subPath` giữ dữ liệu cũ.
- Pod template không đổi nên việc áp dụng lại cùng Deployment không tự tạo rollout.

Đối chiếu UID và số lần restart lần nữa. Nếu Pod bị thay hoặc container khởi động lại trong lúc thử, hãy ghi nhận điều đó trước khi kết luận.

### 7.3. Tạo Pod mới để nhận lại cấu hình

```bash
kubectl rollout restart deployment/config-observer -n config-update-lab
kubectl rollout status deployment/config-observer -n config-update-lab --timeout=120s
kubectl get pods -n config-update-lab -l app=config-observer
kubectl logs deployment/config-observer -n config-update-lab --tail=5
```

Khi Pod mới được tạo từ nguồn hiện có, kết quả dự kiến:

```text
env=3s volume=3s subPath=3s
```

Trong lúc rollout có thể đồng thời tồn tại Pod cũ và Pod mới. Lệnh lấy log qua Deployment không phải công cụ chứng minh mọi replica đã nhận cấu hình; khi cần, chọn từng Pod cụ thể.

Sau thí nghiệm, có thể xóa đúng hai tài nguyên lab:

```bash
kubectl delete deployment config-observer -n config-update-lab
kubectl delete configmap limits-demo -n config-update-lab
```

Chỉ xóa namespace nếu đó là namespace riêng và không còn tài nguyên cần giữ.

## 8. Khi thay BusyBox bằng ứng dụng Spring

### 8.1. File application.yaml cần được nạp đúng vị trí

Giả sử ConfigMap cung cấp file `application.yaml`:

```yaml
app:
  checkout:
    timeout: 2s
```

Nếu file được mount thành `/etc/checkout-config/application.yaml`, có thể cung cấp vị trí từ Pod:

```yaml
env:
  - name: SPRING_CONFIG_ADDITIONAL_LOCATION
    value: "file:/etc/checkout-config/"
```

Vị trí bổ sung giúp Spring Boot đọc file cấu hình ngoài khi khởi động. Nó không phải lệnh bật theo dõi file liên tục.

Nếu các file riêng lẻ chứa giá trị và tên file là tên thuộc tính, đó là trường hợp configuration tree, chẳng hạn `spring.config.import=configtree:/etc/app-secrets/`. Import configuration tree cũng không phải cam kết mọi bean hoặc kết nối sẽ tự cập nhật khi file đổi.

Cách khai báo vị trí, import và configuration tree được mô tả trong [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).

### 8.2. Giá trị được chụp khi khởi tạo bean vẫn có thể cũ

Ví dụ minh họa một bean chỉ lấy timeout lúc được tạo:

```java
import java.time.Duration;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class CheckoutPolicy {

    private final Duration timeout;

    CheckoutPolicy(Environment environment) {
        this.timeout = environment.getRequiredProperty(
                "app.checkout.timeout", Duration.class);
    }

    Duration timeout() {
        return timeout;
    }
}
```

Giả sử file trên volume đã đổi thành `3s`. Field `timeout` không tự thay đổi vì constructor không tự chạy lại sau mỗi lần file đổi.

Các bean dùng `@Value` hoặc `@ConfigurationProperties` cũng cần được xét theo cách nạp nguồn, khả năng rebind và vòng đời bean. Chỉ thêm một annotation cấu hình không tạo ra cơ chế phát hiện thay đổi của Kubernetes.

Tài nguyên được tạo từ cấu hình, như client có timeout, connection pool hoặc TLS context, có thể giữ bản sao giá trị riêng. Ngay cả khi một thuộc tính đã được đọc lại, tài nguyên cũ chưa chắc đã được xây lại.

### 8.3. File mới có thể bị nguồn khác ghi đè

Nếu đồng thời cấu hình:

```yaml
env:
  - name: APP_CHECKOUT_TIMEOUT
    value: "2s"
```

và trong file có `app.checkout.timeout: 3s`, env có thể giữ ưu tiên cao hơn Config Data. Việc file mới hiện ra không bảo đảm giá trị hiệu lực thay đổi.

Khi chẩn đoán, kiểm tra cả biến môi trường, Java system properties, tham số dòng lệnh, profile và nguồn cấu hình ngoài khác. Xem [thứ tự PropertySource của Spring Boot](https://docs.spring.io/spring-boot/reference/features/external-config.html).

Tránh khai báo một thuộc tính ở nhiều nguồn nếu không có chủ đích và tài liệu về độ ưu tiên.

## 9. Configuration Watcher hỗ trợ điều gì và không hỗ trợ điều gì?

Spring Cloud Kubernetes Configuration Watcher có thể nhận biết thay đổi của các nguồn được theo dõi và gửi thông báo refresh đến ứng dụng theo cách được cấu hình. Việc nhận thông báo, đọc lại nguồn và cập nhật đối tượng là các bước riêng.

Watcher không tự:

- Thay môi trường của JVM đang chạy.
- Biến mount `subPath` thành mount cập nhật liên tục.
- Sửa Pod spec để chuyển sang tên ConfigMap/Secret khác.
- Đảm bảo mọi connection pool hay TLS context đều refresh được.
- Tạo giao dịch đồng thời trên mọi replica.

Với nguồn mount file, có thể xảy ra thứ tự sau:

```text
t0: API lưu bản mới
t1: watcher thấy sự kiện
t2: ứng dụng nhận refresh
t3: kubelet mới cập nhật file
```

Nếu refresh đọc file tại `t2`, nó vẫn có thể đọc bản cũ. Tham số `spring.cloud.kubernetes.configuration.watcher.refreshDelay` giúp điều chỉnh thời điểm gửi thông báo, nhưng một khoảng đợi cố định không thay thế việc xác minh phiên bản đã áp dụng. Xem [Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Với một nguồn cấu hình đọc trực tiếp qua API, đường đi dữ liệu không phụ thuộc volume theo cách trên, nhưng vẫn phải xét cache, nguồn đã chọn và vòng đời bean.

`@RefreshScope` là một cơ chế quản lý vòng đời bean trong Spring Cloud, không phải bộ theo dõi file. Một số loại tài nguyên có giới hạn refresh; không suy rằng mọi bean đều an toàn khi refresh. Xem [Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html#refresh-scope).

Chỉ bật refresh khi ứng dụng có nhu cầu rõ ràng và đã xác định được các đối tượng thực sự đổi an toàn.

## 10. Chọn chính sách cập nhật theo loại cấu hình

| Loại thay đổi | Chính sách thường phù hợp | Điều phải chứng minh |
|---|---|---|
| Tham số chỉ đọc lúc khởi động | Rollout tạo Pod mới | Pod mới dùng đúng bộ dữ liệu |
| Thay đổi cấu trúc bean hoặc tham số server | Rollout có kiểm soát | Khởi động và phục vụ được với bản mới |
| Timeout nghiệp vụ đã hỗ trợ đổi lúc chạy | Refresh hoặc bộ đọc động đã thiết kế | Yêu cầu mới dùng giá trị mới, yêu cầu đang chạy có quy tắc rõ ràng |
| Credential DB hoặc token | Xoay vòng phối hợp backend; rollout hoặc cơ chế reload đã hỗ trợ | Kết nối/phiên xác thực thực sự dùng được bản mới |
| Chứng chỉ TLS | Cơ chế reload của thư viện hoặc rollout | TLS context và kết nối mới dùng đúng chứng chỉ |
| Nhiều thuộc tính phải đổi cùng nhau | Snapshot có phiên bản hoặc rollout tổ hợp nhất quán | Không công bố cấu hình chưa hoàn chỉnh |

Nếu chọn rollout, việc thay ConfigMap cùng tên không tự tạo rollout của Deployment. Có thể chủ động `rollout restart` hoặc quản lý tên cấu hình có phiên bản và tham chiếu từ Pod template. Restart chỉ giải quyết việc tạo tiến trình mới; nó không lưu hộ dữ liệu cũ để quay lui.

Nếu chọn cập nhật trong tiến trình, một luồng xử lý rõ ràng là:

```text
Phát hiện dữ liệu mới
  -> mở lại và đọc toàn bộ ứng viên
  -> parse và validate
  -> chuẩn bị tài nguyên liên quan
  -> công bố snapshot mới
  -> ghi nhận phiên bản đã áp dụng
```

Khi dữ liệu không hợp lệ, có thể giữ bản hợp lệ trước đó theo chính sách và phát cảnh báo. Với thay đổi bảo mật như credential đã thu hồi, không được mặc định bản cũ luôn an toàn để tiếp tục dùng.

## 11. Quan sát sức khỏe và quyền truy cập đúng chỗ

### 11.1. Không dùng liveness làm cơ chế phân phối cấu hình

Cố tình làm liveness thất bại để buộc restart khi cấu hình đổi khiến quá trình cập nhật phụ thuộc cơ chế xử lý lỗi. Điều đó che mất nguyên nhân và có thể gây restart hàng loạt.

Dùng rollout cho thay đổi cần tiến trình mới. Với cập nhật trực tiếp, ghi nhận trạng thái đọc và áp dụng cấu hình; chỉ đánh giá readiness theo khả năng phục vụ thực sự và chính sách của dịch vụ.

Một Pod vẫn Running không chứng minh cấu hình mới đã hiệu lực. Ngược lại, một cấu hình bị từ chối có thể không cần làm Pod chết nếu ứng dụng vẫn phục vụ an toàn bằng snapshot trước.

### 11.2. Không cấp quyền API nếu chỉ cần mount

Đưa ConfigMap/Secret vào container bằng volume hoặc env không yêu cầu ứng dụng phải có quyền `get` tài nguyên đó qua Kubernetes API.

Nếu ứng dụng thực sự dùng Spring Cloud Kubernetes để đọc qua API hoặc dùng DiscoveryClient, phải cấp danh tính và RBAC phù hợp với đường gọi đó. Watcher có danh tính và quyền riêng theo phạm vi nguồn được theo dõi.

Lỗi file không đổi do `subPath` không được giải quyết bằng cách cấp thêm `list/watch` cho ứng dụng. Lỗi env giữ bản cũ cũng không phải bằng chứng thiếu RBAC.

## 12. Quy trình chẩn đoán khi cấu hình chưa có hiệu lực

Thực hiện từ ngoài vào trong:

1. **Xác định đúng đích:** cluster context, namespace, tên nguồn, tên Pod và container.
2. **Xác định cách đưa dữ liệu vào:** env, mount thư mục, `subPath`, file đã sao chép hay API.
3. **Kiểm tra vòng đời:** Pod có được tạo lại không, container có restart không, có replica mới do tăng tải không.
4. **Kiểm tra dữ liệu trong container:** chỉ quan sát giá trị không nhạy cảm hoặc định danh phiên bản được phép công bố.
5. **Kiểm tra đường đọc:** ứng dụng đọc đúng file nào, mở lại hay giữ stream, có cache hoặc bản sao không.
6. **Kiểm tra nguồn hiệu lực:** env, system property hoặc tham số dòng lệnh có ghi đè file không.
7. **Kiểm tra cơ chế áp dụng:** có refresh không, bean và tài nguyên liên quan có hỗ trợ không.
8. **Xác minh hành vi:** kiểm thử một yêu cầu mới hoặc kết nối mới, rồi đối chiếu từng replica cần thiết.

Bảng phân biệt nhanh:

| Hiện tượng | Nguyên nhân cần kiểm tra đầu tiên |
|---|---|
| API mới, env cũ | Tiến trình chưa được thay thế |
| API mới, mount thư mục còn cũ | Đúng nguồn chưa, có `subPath` không, kubelet đã đồng bộ chưa |
| Mount chính mới, file kết quả cũ | File đã được sao chép hoặc sinh một lần |
| File mới, Spring trả giá trị cũ | Nguồn chưa nạp lại hoặc bị nguồn ưu tiên cao hơn ghi đè |
| Thuộc tính mới, hành vi client cũ | Client/pool/context còn giữ cấu hình khi khởi tạo |
| Một số Pod mới, một số Pod cũ | Khác vòng đời, khác node hoặc cập nhật chưa hội tụ |
| Refresh báo thành công nhưng hành vi chưa đổi | Refresh sai nguồn, xảy ra trước khi file mới tới hoặc đối tượng không refresh được |

Với Secret, tránh dùng lệnh in toàn bộ env, nội dung file hay manifest để chứng minh đã cập nhật. Dùng phiên bản không nhạy cảm và phép thử xác thực có kiểm soát. Không công bố hash của mật khẩu ít entropy như một nhãn quan sát.

## 13. Tự thực hành để nhận diện đúng giới hạn

Sau khi hoàn thành lab, có thể mở rộng theo ba hướng:

- Đổi từ mount thư mục sang `subPath` rồi so sánh khả năng nhận bản mới trên cùng Pod.
- Viết chương trình đọc file một lần khi khởi động, đối chiếu nó với chương trình mở lại file theo chu kỳ.
- Áp dụng cùng một cấu hình cho hai replica, thay dữ liệu và ghi nhận thời điểm mỗi replica nhìn thấy bản mới.

Mỗi lần ghi nhận kết quả, tách ba dữ kiện: **bản ở API**, **bản trong container**, **bản ứng dụng đã áp dụng**. Không dùng việc file đã đổi để kết luận bean đã đổi, và không dùng trạng thái Pod Running để kết luận chức năng nghiệp vụ đã dùng cấu hình mới.

Một thiết kế cập nhật cấu hình đầy đủ phải nêu rõ dữ liệu đi vào bằng đường nào, khi nào được đọc lại, ai chịu trách nhiệm áp dụng và bằng chứng nào xác nhận ứng dụng đang sử dụng đúng bản mong muốn.
