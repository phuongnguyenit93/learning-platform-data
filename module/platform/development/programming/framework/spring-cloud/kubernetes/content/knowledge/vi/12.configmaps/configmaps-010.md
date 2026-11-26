# Đọc ConfigMap từ volume thay vì gọi Kubernetes API

Trong chương **ConfigMap** của **SPRING_CLOUD_KUBERNETES**, ứng dụng không nhất thiết phải có Kubernetes client chỉ để nhận cấu hình. Kubernetes có thể lấy ConfigMap, đưa dữ liệu vào volume của Pod, rồi Spring Boot đọc các tệp đó bằng cơ chế Config Data.

Cách này phù hợp khi bạn muốn ứng dụng sử dụng cấu hình dưới dạng tệp, giới hạn nhu cầu truy cập Kubernetes API và quản lý thay đổi bằng quy trình triển khai. Nếu ứng dụng còn dùng DiscoveryClient, Spring Cloud LoadBalancer hoặc Configuration Watcher, cần đánh giá riêng nhu cầu của từng tính năng; việc đọc ConfigMap từ volume không tự loại bỏ mọi lời gọi API khác.

## 1. Đường đi của dữ liệu khác nhau ở đâu?

### Đọc trực tiếp qua API

```text
Tiến trình ứng dụng
    -> Kubernetes client
    -> Kubernetes API
    -> ConfigMap
    -> Spring Environment
```

Ứng dụng phải có thư viện, thông tin truy cập và quyền cho các thao tác API thực sự được thực hiện.

### Đọc từ volume

```text
ConfigMap trong namespace của Pod
    -> Kubernetes chuẩn bị volume
    -> Tệp trong container
    -> Spring Boot Config Data
    -> Spring Environment
```

Tiến trình Java mở tệp như các tệp cấu hình bên ngoài thông thường. Nó không cần quyền `get`, `list` hoặc `watch` ConfigMap qua Kubernetes API chỉ để đọc các tệp đã được mount.

Điều này không có nghĩa Kubernetes không dùng API ở phía hạ tầng. Kubernetes vẫn chịu trách nhiệm lấy dữ liệu và cung cấp volume; ứng dụng chuyển trách nhiệm truy xuất nguồn sang nền tảng.

## 2. Chọn hình thức dữ liệu trước khi viết import

Có hai hình thức phổ biến:

| Hình thức trong ConfigMap | Kết quả trong volume | Cách Spring Boot đọc |
| --- | --- | --- |
| Một khóa chứa toàn bộ `application.yaml` hoặc `application.properties` | Một tệp cấu hình có cấu trúc | Import tệp bằng `file:` |
| Mỗi khóa là một thuộc tính | Nhiều tệp, mỗi tệp chứa một giá trị | Import thư mục bằng `configtree:` |

Ví dụ hình thức thứ nhất:

```text
/etc/checkout/application.yaml
    nội dung là tài liệu YAML
```

Ví dụ hình thức thứ hai:

```text
/etc/checkout-kv/checkout.request-timeout
    nội dung là "2s"

/etc/checkout-kv/checkout.currency
    nội dung là "VND"
```

Không hoán đổi hai cách import mà không đổi cách tổ chức dữ liệu. Một tệp YAML hoàn chỉnh không tự trở thành nhiều thuộc tính chỉ vì đặt nó trong thư mục được import bằng `configtree:`.

Các ví dụ dưới đây dùng cơ chế Config Data của Spring Boot, có từ thế hệ Spring Boot 2.4. Dự án cần chọn bộ phiên bản Spring Boot và Spring Cloud tương thích với các tính năng Spring Cloud Kubernetes còn sử dụng.

## 3. Phương án A: mount một tệp YAML hoàn chỉnh

Giả sử `checkout-service` cần ba thuộc tính không bí mật:

- Địa chỉ dịch vụ thanh toán.
- Timeout cho lời gọi thanh toán.
- Mã phiên bản cấu hình để quan sát quá trình triển khai.

### Bước 1: tạo ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-file-config
  namespace: shop
data:
  application.yaml: |
    checkout:
      payment-base-url: "http://payment-service"
      request-timeout: "2s"
      config-version: "v1"
```

Có hai lớp YAML:

1. YAML bên ngoài định nghĩa đối tượng ConfigMap.
2. Chuỗi sau `application.yaml: |` là nội dung tệp mà Spring Boot sẽ phân tích.

Kubernetes không phân tích nội dung chuỗi này theo mô hình thuộc tính của Spring. ConfigMap được chấp nhận không chứng minh tài liệu bên trong có cú pháp hoặc ý nghĩa hợp lệ đối với ứng dụng.

Tên khóa `application.yaml` sẽ được ánh xạ thành tên tệp khi mount. Tên ConfigMap là `checkout-file-config`, được tham chiếu trong manifest Pod; không có bước tự chọn ConfigMap theo `spring.application.name` ở đường đọc volume này.

### Bước 2: mount tệp vào container

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-service
  namespace: shop
spec:
  replicas: 1
  selector:
    matchLabels:
      app: checkout-service
  template:
    metadata:
      labels:
        app: checkout-service
    spec:
      automountServiceAccountToken: false
      containers:
        - name: app
          image: example.invalid/checkout-service:training
          volumeMounts:
            - name: application-config
              mountPath: /etc/checkout
              readOnly: true
      volumes:
        - name: application-config
          configMap:
            name: checkout-file-config
            items:
              - key: application.yaml
                path: application.yaml
```

Image trong ví dụ là chỗ giữ cho tài liệu, cần thay bằng image của ứng dụng khi thực hành.

Mẫu Pod này được thiết kế cho ứng dụng không gọi Kubernetes API. Vì vậy, nó không tự mount ServiceAccount token. Nếu vẫn cần discovery hoặc một tích hợp API khác, phải điều chỉnh thiết lập danh tính và quyền tương ứng.

Các điểm quan trọng của volume:

- ConfigMap và Pod ở cùng namespace `shop`.
- `configMap.name` chọn đối tượng Kubernetes cần mount.
- `items[].key` chọn khóa dữ liệu.
- `items[].path` đặt đường dẫn tương đối bên trong volume.
- `mountPath` chọn thư mục volume xuất hiện trong container.
- `readOnly: true` thể hiện ứng dụng chỉ đọc dữ liệu cấu hình.

Sau khi mount, ứng dụng nhìn thấy:

```text
/etc/checkout/application.yaml
```

Manifest không dùng `subPath`; sự khác biệt này quan trọng khi nguồn được cập nhật.

### Bước 3: import tệp bằng Spring Boot

Trong cấu hình khởi động của ứng dụng, chẳng hạn `application.yml` đóng gói trong image:

```yaml
spring:
  application:
    name: checkout-service
  config:
    import: "file:/etc/checkout/application.yaml"
  cloud:
    kubernetes:
      config:
        enabled: false
      secrets:
        enabled: false
      discovery:
        enabled: false
```

Đường dẫn import phải khớp với đường dẫn trong container, không phải đường dẫn trên máy phát triển.

Các cờ dưới `spring.cloud.kubernetes` dành cho trường hợp ứng dụng vẫn có những thư viện tương ứng trên classpath nhưng mẫu này không cần các chức năng đó. Nếu chỉ dùng Spring Boot để đọc tệp và không dùng Spring Cloud Kubernetes, không cần thêm starter Kubernetes chỉ để hoàn thành việc import này.

Trong phương án này, không giữ thêm `spring.config.import: "kubernetes:"` để nạp lại chính ConfigMap đó qua API. Nếu không có nhu cầu khác, hai đường nạp chỉ làm tăng cấu hình và tạo thêm khả năng ghi đè khó giải thích.

Không đặt thông tin import duy nhất vào chính tệp chưa được tìm thấy. Spring cần biết `/etc/checkout/application.yaml` từ một nguồn đã có sẵn trước khi đọc tệp này.

## 4. Phương án B: mỗi khóa trở thành một tệp thuộc tính

Nếu cấu hình được quản lý dưới dạng cặp khóa–giá trị, có thể dùng `configtree:`.

### ConfigMap dạng từng thuộc tính

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-key-config
  namespace: shop
data:
  checkout.payment-base-url: "http://payment-service"
  checkout.request-timeout: "2s"
  checkout.config-version: "v1"
```

Thay phần mount và nguồn volume tương ứng trong Pod bằng:

```yaml
volumeMounts:
  - name: application-config
    mountPath: /etc/checkout-kv
    readOnly: true
```

```yaml
volumes:
  - name: application-config
    configMap:
      name: checkout-key-config
```

Đây là các mảnh cấu hình thay thế ở đúng vị trí trong Deployment, không phải hai manifest độc lập. Trong ví dụ này, các khóa của ConfigMap được mount thành tệp trong thư mục:

```text
/etc/checkout-kv/
    checkout.payment-base-url
    checkout.request-timeout
    checkout.config-version
```

Import thư mục:

```yaml
spring:
  config:
    import: "configtree:/etc/checkout-kv/"
```

Giữ các lựa chọn tắt chức năng API không cần dùng như phương án trước. Không cần giữ import tệp của phương án A nếu bạn đã chuyển hoàn toàn sang phương án B.

Với `configtree:`, tên tệp trở thành tên thuộc tính, nội dung tệp trở thành giá trị. Tệp `checkout.request-timeout` chứa `2s` cung cấp thuộc tính `checkout.request-timeout=2s`.

### Lỗi chọn sai cách import

| Dữ liệu thực tế | Cách import sai | Kết quả dễ gặp |
| --- | --- | --- |
| Một tệp `application.yaml` chứa nhiều thuộc tính | Import thư mục bằng `configtree:` | Không nhận được các thuộc tính lồng trong YAML như mong muốn |
| Nhiều tệp, mỗi tệp chứa một giá trị | Import một tệp giá trị như tài liệu YAML | Không có cấu trúc thuộc tính mong đợi |
| Tệp nằm ở `/etc/checkout/application.yaml` | Import `/config/application.yaml` | Không tìm thấy tệp tại đường dẫn đã khai báo |

Hãy bắt đầu từ cách Kubernetes tạo tệp, rồi chọn bộ đọc phù hợp của Spring Boot.

## 5. Binding vẫn giống các nguồn cấu hình Spring khác

Sau khi đọc tệp, dữ liệu tham gia Spring Environment. Bean ứng dụng không cần biết giá trị đến từ volume hay từ một nguồn API.

Ví dụ đối tượng cấu hình với Java 17, Spring Boot 3 và Bean Validation:

```java
package com.example.checkout;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        @NotNull URI paymentBaseUrl,
        @NotNull Duration requestTimeout,
        @NotBlank String configVersion) {
}
```

Đăng ký bằng `@ConfigurationPropertiesScan` trên lớp ứng dụng hoặc cơ chế đăng ký thuộc tính tương đương. Dự án cần thư viện validation thích hợp để thực hiện các ràng buộc đã khai báo.

Các ràng buộc trên phát hiện giá trị thiếu, nhưng chưa bảo đảm mọi điều kiện nghiệp vụ. Ví dụ:

- Timeout `0s` có thể hợp lệ về kiểu nhưng không phù hợp với client của bạn.
- Một URI hợp lệ về cú pháp không chứng minh Service đích tồn tại.
- Một địa chỉ trỏ sai môi trường có thể bind thành công.

Vì vậy, kiểm tra kiểu dữ liệu, ràng buộc nghiệp vụ và khả năng sử dụng tài nguyên là các bước khác nhau.

Việc nạp Config Data diễn ra trước khi các bean ứng dụng thông thường được tạo. Không cần gọi Kubernetes API trong constructor để “điền thêm” các thuộc tính đã được import từ volume.

### Giá trị từ tệp chưa chắc là giá trị cuối cùng

Một biến môi trường như `CHECKOUT_REQUESTTIMEOUT`, theo quy tắc chuyển tên thuộc tính sang biến môi trường của Spring Boot, có thể cung cấp `checkout.request-timeout`. Các nguồn cấu hình có thứ tự ưu tiên cao hơn có thể ghi đè giá trị từ tệp.

Khi tệp ghi `2s` nhưng bean nhận giá trị khác, cần kiểm tra các lớp cấu hình hiệu lực trước khi kết luận volume mount sai.

Trong bài thực hành, tránh đặt cùng thuộc tính ở nhiều nguồn nếu mục tiêu chỉ là xác nhận việc đọc tệp.

## 6. Quyền truy cập: giảm quyền API, vẫn bảo vệ tệp và Pod

Đọc volume không đòi ứng dụng có Role đọc ConfigMap qua API chỉ cho mục đích đó. Tuy nhiên, vẫn có các ranh giới quyền khác:

| Chủ thể hoặc tài nguyên | Điều cần quản lý |
| --- | --- |
| Người hoặc pipeline tạo ConfigMap | Có quyền thay đổi cấu hình ứng dụng |
| Người có quyền tạo/sửa Pod | Có thể điều chỉnh nguồn mount hoặc workload được chạy |
| Container trong Pod | Chỉ mount dữ liệu vào container thực sự cần |
| Người có quyền truy cập container | Có thể đọc tệp theo quyền hệ điều hành và công cụ được cấp |
| Tiến trình Java | Cần quyền đọc đường dẫn cấu hình |
| Tính năng API khác của ứng dụng | Vẫn cần danh tính và RBAC riêng |

`readOnly: true` ngăn ứng dụng sử dụng mount theo hướng ghi như một vùng dữ liệu thông thường. Nó không ngăn Kubernetes cập nhật nội dung volume từ phía nền tảng.

Không dùng thư mục mount cấu hình để ghi log, cache hoặc tệp tạm. Việc ghi một tệp trong container cũng không phải cơ chế cập nhật ngược đối tượng ConfigMap trong Kubernetes.

### Trường hợp vẫn cần DiscoveryClient

Nếu ứng dụng đọc cấu hình qua volume nhưng dùng DiscoveryClient gọi Kubernetes API:

1. Giữ cơ chế đọc tệp cho ConfigMap.
2. Chỉ bật tính năng discovery cần dùng.
3. Cung cấp danh tính API cho client theo môi trường.
4. Cấp RBAC cho tài nguyên và thao tác discovery thực sự cần thiết.
5. Không cấp thêm quyền đọc Secret hoặc ConfigMap qua API chỉ vì ứng dụng có Kubernetes client.

Trong trường hợp này, không áp dụng nguyên xi `automountServiceAccountToken: false` của mẫu không gọi API nếu client đang cần token được mount để xác thực. Phải xem xét toàn bộ cấu hình xác thực thay vì chỉ một chức năng đọc tệp.

### Dữ liệu bí mật vẫn thuộc Secret

ConfigMap không phù hợp để chứa mật khẩu, token hoặc khóa riêng. Việc chuyển sang volume không biến ConfigMap thành kho bí mật.

Nếu cần cả ConfigMap và Secret, có thể mount chúng ở các thư mục riêng rồi import theo cơ chế tệp phù hợp. Khi đó cần quản lý quyền tệp, truy cập Pod, việc ghi log và vòng đời xoay vòng bí mật; không chỉ xem xét RBAC của ứng dụng.

## 7. Tệp được cập nhật không có nghĩa bean tự thay đổi

Volume ConfigMap thông thường có thể được Kubernetes cập nhật khi đối tượng nguồn thay đổi. Việc phân phối không nhất thiết tức thời; nó phụ thuộc cơ chế đồng bộ và cache của Kubernetes.

Có ít nhất bốn trạng thái cần quan sát:

```text
ConfigMap đã có giá trị mới
    -> tệp trong volume đã có giá trị mới
    -> Spring đã đọc lại nguồn
    -> bean sử dụng giá trị mới
```

Không bỏ qua các bước ở giữa.

| Sự kiện | Điều có thể kết luận | Điều chưa thể kết luận |
| --- | --- | --- |
| ConfigMap được cập nhật thành công | Đối tượng Kubernetes đã đổi | Tệp của mọi Pod đã đổi |
| Tệp trong container đã đổi | Volume của container đó đã nhận dữ liệu mới | Environment đã được nạp lại |
| Environment đã được cập nhật bởi một cơ chế riêng | Các lần tra cứu tương ứng có thể thấy giá trị mới | Mọi trường và đối tượng đã tạo đều đã đổi |
| Client được tạo lại hoặc hỗ trợ tái cấu hình thành công | Thành phần đó có thể dùng cấu hình mới | Mọi Pod và thành phần khác đều đã hoàn tất chuyển đổi |

Spring Boot xử lý `spring.config.import` trong giai đoạn nạp Config Data. Một tệp bên ngoài thay đổi không tự kích hoạt việc đọc lại tất cả cấu hình và tạo lại mọi bean.

Ví dụ, HTTP client đã nhận timeout `2s` khi khởi tạo có thể tiếp tục dùng `2s` dù tệp đã ghi `5s`. Tương tự, một đối tượng thuộc tính bất biến đã tạo không tự đổi các thành phần bên trong.

Nếu ứng dụng tự mở và giữ một luồng đọc tệp, còn phải xét hành vi của handle tệp khi Kubernetes thay thế dữ liệu volume. Không giả định một handle cũ luôn phản ánh nội dung mới của đường dẫn. Với Config Data, cách an toàn về mặt hiểu biết là coi lần nạp khởi động tạo ra cấu hình của instance đó, trừ khi có cơ chế cập nhật được thiết kế rõ ràng.

## 8. Vì sao nên tránh subPath nếu cần nhận cập nhật tệp?

Mount `subPath` thường được dùng để đặt riêng một tệp vào một thư mục có sẵn:

```yaml
volumeMounts:
  - name: application-config
    mountPath: /etc/checkout/application.yaml
    subPath: application.yaml
    readOnly: true
```

Đây là một cách mount khác với mount cả thư mục trong ví dụ chính. Với ConfigMap được mount bằng `subPath`, container không nhận cập nhật tự động của nguồn theo cách volume ConfigMap thông thường.

Có hai lý do độc lập khiến cấu hình mới chưa được dùng:

1. `subPath` khiến tệp mount không nhận cập nhật tự động.
2. Dù tệp nhận cập nhật, Spring vẫn cần cơ chế đọc lại và áp dụng giá trị.

Chuyển từ `subPath` sang mount thư mục chỉ giải quyết lớp thứ nhất. Nó không tự tạo cơ chế refresh cho Spring.

### Mount thư mục cũng có điều cần chú ý

Mount volume lên một thư mục có sẵn trong image làm các tệp bên dưới vị trí đó bị che khuất trong góc nhìn của container tại mount point. Vì vậy, nên chọn một thư mục riêng như `/etc/checkout`, không mount bừa lên thư mục chứa JAR hoặc các tài nguyên khác của ứng dụng.

Nếu muốn chọn một vài khóa, dùng `items` để kiểm soát tệp được đưa vào volume thay vì chỉ dựa vào tên thư mục.

Không sửa trực tiếp các symlink và cấu trúc nội bộ mà Kubernetes dùng để trình bày volume. Ứng dụng nên đọc các đường dẫn được mount theo giao diện tệp, còn thay đổi nguồn được thực hiện qua quy trình quản lý ConfigMap.

## 9. Chọn cơ chế áp dụng thay đổi

### Lựa chọn 1: rollout có kiểm soát

Đây là lựa chọn rõ ràng khi ứng dụng không cần cập nhật nóng:

1. Chuẩn bị cấu hình mới.
2. Kiểm tra cú pháp và các thuộc tính bắt buộc.
3. Cập nhật ConfigMap hoặc tạo ConfigMap có tên phiên bản mới.
4. Kích hoạt rollout bằng quy trình triển khai.
5. Xác nhận instance mới đọc đúng phiên bản.
6. Chỉ chuyển đủ lưu lượng khi readiness đáp ứng yêu cầu.
7. Giữ khả năng khôi phục phù hợp trước khi dọn nguồn cũ.

Chỉ cập nhật nội dung ConfigMap không tự thay đổi Pod template của Deployment và không tự bảo đảm có rollout.

Để ranh giới phiên bản rõ hơn, có thể tạo `checkout-file-config-v2` rồi sửa `volumes[].configMap.name` trong Pod template. Instance mới được tạo sẽ tham chiếu nguồn mới.

Một cách khác là quy trình triển khai thay đổi annotation trong Pod template dựa trên nội dung cấu hình. Annotation không tự tính checksum; công cụ triển khai phải thực sự cập nhật nó.

Nếu dùng ConfigMap bất biến, thay đổi nội dung cần một nguồn mới theo khả năng của Kubernetes. Tên phiên bản và cơ chế bất biến nên được thiết kế cùng quy trình khôi phục.

### Lựa chọn 2: cập nhật nóng có thiết kế

Nếu bắt buộc đổi timeout hoặc một tham số lúc ứng dụng đang chạy, phải có câu trả lời cho từng bước:

- Ai phát hiện thay đổi tệp hoặc đối tượng nguồn?
- Ai nạp lại dữ liệu vào ứng dụng?
- Thuộc tính nào được bind lại hoặc tạo lại?
- Client nào hỗ trợ thay đổi mà không cần restart?
- Xử lý giá trị không hợp lệ và khôi phục thế nào?
- Các yêu cầu đang thực hiện được bảo vệ ra sao?

Configuration Watcher có thể tham gia quy trình phản ứng với thay đổi nếu được triển khai và cấu hình phù hợp. Nó không phải hệ quả tự động của việc mount volume, và không bảo đảm mọi bean hoặc pool kết nối hỗ trợ refresh.

Không bật đồng thời nhiều cơ chế theo dõi chỉ vì chúng đều có chữ “reload”. Phải biết cơ chế nào phát hiện, cơ chế nào áp dụng và quyền nào được dùng. Với yêu cầu chỉ đọc cấu hình lúc startup, không cần thêm Watcher để thay thế một rollout đã được chấp nhận.

## 10. Nguồn bắt buộc và nguồn tùy chọn

Trong phương án A, ConfigMap, khóa `application.yaml` và tệp import đều được xem là bắt buộc.

Có nhiều lớp lỗi khác nhau:

| Tình huống | Giai đoạn có thể phát hiện |
| --- | --- |
| Không có ConfigMap mà volume bắt buộc tham chiếu | Kubernetes chuẩn bị volume; container có thể chưa chạy được |
| Có ConfigMap nhưng thiếu khóa đã liệt kê trong `items` | Chuẩn bị volume khi khóa không được đánh dấu tùy chọn |
| Volume mount ở đường dẫn khác với import | Spring Boot không tìm thấy tài nguyên cần nạp |
| YAML bên trong sai cú pháp | Spring Boot phân tích Config Data |
| Thiếu thuộc tính bắt buộc | Binding hoặc validation của ứng dụng |
| Giá trị hợp lệ về kiểu nhưng không dùng được | Tạo hoặc sử dụng thành phần phụ thuộc |

Có thể cho phép thiếu tệp bằng:

```yaml
spring:
  config:
    import: "optional:file:/etc/checkout/application.yaml"
```

Nhưng `optional:` ở đây chỉ ảnh hưởng đến việc tìm tài nguyên theo cơ chế import. Nó không tự làm volume Kubernetes trở thành tùy chọn và không biến các thuộc tính bắt buộc thành không bắt buộc.

Ngược lại, đánh dấu nguồn volume là tùy chọn ở phía Kubernetes không tự làm Spring chấp nhận thiếu tệp nếu import vẫn yêu cầu tệp đó.

Chỉ chọn tùy chọn khi ứng dụng có giá trị mặc định hoặc trạng thái giảm chức năng được thiết kế rõ ràng. Không che lỗi thiếu cấu hình production bằng cách âm thầm dùng một đích của môi trường khác.

## 11. Theo dõi startup, readiness và phiên bản cấu hình

Một container Running chưa chứng minh cấu hình đã hợp lệ. Ứng dụng có thể còn khởi tạo, thiếu một thành phần lazy hoặc chưa thử kết nối phụ thuộc bắt buộc.

Có thể dùng `checkout.config-version` như một dấu hiệu không bí mật:

```text
Pod A: config-version=v1
Pod B: config-version=v2
```

Dấu hiệu này giúp nhận biết các instance trong rollout đang dùng phiên bản nào. Cần phân biệt giá trị đọc trực tiếp từ tệp với giá trị bean đang sử dụng; đặt tên log đủ rõ để không nhầm hai lớp.

Readiness nên phản ánh điều kiện cần để ứng dụng phục vụ lưu lượng theo chính sách của hệ thống. Nếu thiếu một cấu hình bắt buộc khiến chức năng chính không thể hoạt động, không nên chỉ dựa vào việc tiến trình Java còn sống.

Startup probe có thể dành thời gian cho quá trình khởi động. Liveness không nên thất bại chỉ vì mọi lỗi tạm thời của dịch vụ bên ngoài, nếu restart không giải quyết được nguyên nhân.

Khi hai Pod cùng dùng một ConfigMap đang được cập nhật, chúng có thể nhận tệp mới hoặc áp dụng giá trị ở những thời điểm khác nhau. Không coi thay đổi một đối tượng cấu hình là một giao dịch đồng bộ trên toàn bộ ứng dụng phân tán.

## 12. Bài thực hành với đường đọc volume

Thực hiện trong môi trường học tập với dữ liệu không bí mật. Chọn phương án A trước để chỉ có một tệp cần quan sát.

| Thử nghiệm | Cách quan sát | Kết luận cần đạt |
| --- | --- | --- |
| Khởi động với `config-version=v1` | Xem thuộc tính đã bind và trạng thái khởi động | Tệp được đọc vào ứng dụng |
| Đổi đường import sang một tệp không có | Xem lỗi startup | Đường dẫn container phải khớp import |
| Viết timeout sai định dạng | Xem lỗi chuyển kiểu | Mount thành công chưa bảo đảm binding thành công |
| Bỏ ConfigMap bắt buộc trước khi tạo Pod | Xem sự kiện volume và trạng thái container | Kubernetes có thể chặn từ trước lúc Java chạy |
| Đổi nguồn sang `v2` khi Pod còn chạy | Quan sát tệp sau khi được đồng bộ và giá trị bean | Tệp mới không chứng minh bean đã cập nhật |
| Rollout sau khi chuẩn bị `v2` | Xem cấu hình hiệu lực ở instance mới | Lần startup mới nạp cấu hình mới |
| Thử mount bằng `subPath` rồi đổi nguồn | So sánh với mount thư mục | Không trông chờ cập nhật tự động của tệp `subPath` |

Sau đó chuyển sang phương án B:

1. Tạo ConfigMap có các khóa thuộc tính riêng.
2. Mount vào `/etc/checkout-kv`.
3. Đổi import sang `configtree:/etc/checkout-kv/`.
4. Giữ đối tượng `CheckoutProperties` như cũ.
5. Xác nhận rằng mã sử dụng thuộc tính không phải biết hình thức lưu dữ liệu.

Nếu giữ `automountServiceAccountToken: false` trong mẫu không có tính năng API khác, việc đọc và binding từ volume vẫn không đòi ứng dụng được cấp Role đọc ConfigMap. Đây là đặc điểm của đường đọc tệp; không suy rộng sang một ứng dụng vẫn dùng discovery qua API.

## 13. Chẩn đoán nhanh các lỗi thường gặp

| Dấu hiệu | Nguyên nhân nên xét | Hướng xử lý |
| --- | --- | --- |
| Pod chưa khởi động container | Nguồn hoặc khóa bắt buộc chưa có, lỗi chuẩn bị volume | Kiểm tra tham chiếu và sự kiện Pod |
| Spring báo thiếu tệp cấu hình | Import khác đường mount hoặc tên tệp | Đối chiếu `mountPath`, `items.path` và đường import |
| Tệp có dữ liệu nhưng thuộc tính không xuất hiện | Chọn sai `file:`/`configtree:` hoặc sai cấu trúc | Chọn bộ đọc theo hình thức dữ liệu |
| Bean nhận giá trị khác tệp | Có nguồn cấu hình ghi đè | Kiểm tra giá trị hiệu lực và nguồn sở hữu |
| Tệp không đổi sau khi ConfigMap đổi | Dùng `subPath`, nguồn bất biến hoặc chưa đến lúc đồng bộ | Kiểm tra kiểu mount và cơ chế cập nhật |
| Tệp đã đổi nhưng ứng dụng vẫn dùng giá trị cũ | Chưa có đường nạp lại hoặc bean giữ trạng thái cũ | Rollout hoặc triển khai cơ chế cập nhật được hỗ trợ |
| Log vẫn có lỗi Kubernetes API | Còn import API hoặc tính năng khác đang gọi API | Xác định thành phần gọi, tắt phần không cần hoặc cấp quyền đúng nhu cầu |
| Không đọc được tệp do quyền hệ điều hành | Danh tính tiến trình và quyền tệp/thư mục không phù hợp | Kiểm tra quyền thực tế trong container |

Chọn volume khi giao diện tệp đáp ứng yêu cầu triển khai của bạn. Cấu hình đúng đường mount, dùng đúng bộ đọc, kiểm tra các thuộc tính bắt buộc và quyết định rõ cách áp dụng thay đổi. Với cách phân chia này, Spring Cloud Kubernetes chỉ cần đảm nhiệm những tính năng Kubernetes mà ứng dụng thực sự sử dụng.
