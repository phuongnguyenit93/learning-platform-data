# Secret và ranh giới bảo vệ thông tin nhạy cảm

Trong chương **Secret** của **SPRING_CLOUD_KUBERNETES**, cần hiểu Secret như một cơ chế phân phối dữ liệu nhạy cảm có kiểm soát. Nó giúp tách mật khẩu, token và khóa riêng khỏi cấu hình thông thường, nhưng không tự bảo vệ dữ liệu trước mọi người dùng, workload hoặc công cụ vận hành.

Một hệ thống chỉ được bảo vệ khi quyền trên Kubernetes, cách đưa dữ liệu vào ứng dụng Spring, việc ghi log và vòng đời thông tin xác thực cùng được thiết kế đúng. Bật Secret trong Spring Cloud Kubernetes không thay thế RBAC; đưa Secret vào volume cũng không ngăn tiến trình đã đọc nó làm lộ giá trị.

Bài học này xây dựng ranh giới trách nhiệm đó để bạn chọn đúng cơ chế nạp, chỉ bật các tính năng Kubernetes cần dùng và kiểm tra sức khỏe ứng dụng mà không công khai bí mật.

## 1. Secret giải quyết vấn đề nào?

Secret là đối tượng Kubernetes có namespace, dùng để chứa dữ liệu cần kiểm soát truy cập như:

- Mật khẩu tài khoản cơ sở dữ liệu.
- API token của nhà cung cấp thanh toán hoặc email.
- Khóa riêng dùng cho TLS hoặc ký dữ liệu.
- Thông tin xác thực tới registry hoặc hệ thống khác, tùy loại Secret.

Một ứng dụng có thể nhận dữ liệu Secret qua volume, biến môi trường hoặc Kubernetes API. Lựa chọn này ảnh hưởng đến quyền cần cấp, các vị trí dữ liệu xuất hiện và cách cập nhật khi bí mật được xoay vòng.

Secret đem lại một đối tượng và giao diện riêng để áp dụng chính sách. Nó không phải lời cam kết rằng giá trị đã được mã hóa ở mọi nơi hoặc chỉ ứng dụng chính mới có thể đọc.

### Phân loại dựa trên nội dung

| Giá trị | Nguồn thường phù hợp | Lưu ý |
| --- | --- | --- |
| Timeout, giới hạn kết nối, cờ tính năng không nhạy cảm | ConfigMap hoặc cấu hình đóng gói | Không cần quyền Secret chỉ để dùng các tham số này |
| URL dịch vụ không có thông tin xác thực | ConfigMap, nếu chính sách cho phép | URL vẫn có thể chứa thông tin hạ tầng cần hạn chế |
| URL có password hoặc token trong query string | Secret hoặc tách phần bí mật | Không coi toàn bộ URL là công khai chỉ vì khóa có tên `url` |
| Mật khẩu và access token | Secret hoặc hệ thống quản lý bí mật phù hợp | Cần quản lý cả cấp phát, hạn dùng và thu hồi |
| Khóa riêng | Secret hoặc cơ chế quản lý khóa phù hợp | Không nhầm với chứng thư hoặc khóa công khai |
| Dữ liệu nghiệp vụ nhạy cảm của khách hàng | Kho dữ liệu nghiệp vụ có kiểm soát | Secret không phải cơ sở dữ liệu cho toàn bộ dữ liệu nhạy cảm |

Tên khóa không quyết định mức độ nhạy cảm. Một khóa tên `config` vẫn có thể chứa mật khẩu; một đối tượng tên `public-settings` vẫn có thể bị dùng sai để lưu token.

## 2. Base64 không phải ranh giới bảo mật

Ví dụ một Secret minh họa:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: checkout-credentials
  namespace: shop
type: Opaque
stringData:
  payment.api-token: "REPLACE_WITH_TRAINING_TOKEN"
```

Giá trị là chỗ giữ để đọc ví dụ, không phải token dùng trong triển khai. Không thay nó bằng thông tin xác thực thật rồi commit manifest vào repository.

Hai trường dữ liệu có vai trò khác nhau:

| Trường | Cách biểu diễn đầu vào | Ý nghĩa bảo mật |
| --- | --- | --- |
| `data` | Giá trị được biểu diễn bằng base64 | Người đọc được giá trị có thể giải mã biểu diễn này |
| `stringData` | Chuỗi rõ thuận tiện khi tạo hoặc cập nhật | Không làm dữ liệu bí mật hơn; cần bảo vệ manifest và đường truyền |

Kubernetes chuyển dữ liệu chuỗi được gửi qua `stringData` sang dạng dữ liệu của Secret. Cả hai cách đều không biến manifest chứa giá trị thật thành một tài liệu an toàn để chia sẻ.

`type: Opaque` mô tả loại dữ liệu Secret tổng quát; nó không phải lựa chọn thuật toán mã hóa.

Cần phân biệt:

- **Base64**: cách biểu diễn dữ liệu có thể đảo ngược.
- **Mã hóa khi truyền**: bảo vệ đường truyền theo cơ chế và cấu hình được sử dụng.
- **Mã hóa khi lưu trữ**: bảo vệ dữ liệu lưu ở lớp lưu trữ theo cấu hình cluster.
- **Kiểm soát truy cập**: quyết định danh tính nào được phép lấy hoặc sử dụng giá trị.

Mã hóa khi lưu trữ không chặn một danh tính đã được API cho phép đọc Secret. Khi đọc hợp lệ, bên nhận cần được cung cấp giá trị có thể sử dụng.

Không suy ra trạng thái mã hóa khi lưu trữ chỉ từ việc đối tượng có `kind: Secret`. Cần biết cấu hình thực tế của cluster, cách bảo vệ khóa mã hóa và các bản sao lưu liên quan.

## 3. Xác định các ranh giới mà bí mật đi qua

Một đường đi thường gặp:

```text
Hệ thống cấp phát thông tin xác thực
    -> quy trình triển khai hoặc đồng bộ
    -> Kubernetes Secret
    -> Kubernetes API hoặc volume hoặc môi trường container
    -> tiến trình Spring
    -> client gọi tài nguyên đích
```

Tại mỗi mũi tên, cần biết ai được phép truy cập và dữ liệu có bị sao chép ra nơi khác không.

| Ranh giới | Chủ thể cần xem xét | Nguy cơ cần kiểm soát |
| --- | --- | --- |
| Cấp phát | Quản trị viên, pipeline, hệ thống quản lý bí mật | Token quá rộng quyền, không có hạn dùng hoặc không thể thu hồi |
| Lưu trong Kubernetes | Danh tính API, quản trị cluster, hệ thống sao lưu | Đọc ngoài nhu cầu, truy cập bản lưu hoặc khóa bảo vệ |
| Đưa vào Pod | Người tạo Pod, cấu hình volume, quyền truy cập container | Workload không được phép vẫn có đường nhận bí mật |
| Dùng trong ứng dụng | Mã ứng dụng, thư viện, công cụ chẩn đoán | Log, exception, dump hoặc endpoint làm lộ giá trị |
| Gọi dịch vụ ngoài | Client và hệ thống đích | Lộ qua URL, header được log, kênh truyền hoặc tài khoản bị lạm dụng |
| Hết vòng đời | Quy trình rotation và thu hồi | Giá trị cũ vẫn dùng được dù Secret đã bị thay hoặc xóa |

Một Secret có RBAC chặt nhưng bị in vào log vẫn vượt qua ranh giới ứng dụng. Một Secret được mã hóa khi lưu nhưng cho mọi workload đọc vẫn có phạm vi truy cập quá rộng.

## 4. Ai đọc được Secret qua Kubernetes API?

RBAC cần xét cả tài nguyên, thao tác và phạm vi namespace.

- `get` cho phép lấy đối tượng theo yêu cầu tương ứng.
- `list` Secret có thể trả về nội dung của nhiều Secret trong phạm vi được phép, không chỉ danh sách tên.
- `watch` có thể nhận các sự kiện kèm dữ liệu đối tượng theo quyền và yêu cầu tương ứng.
- Quyền đọc ở nhiều namespace hoặc toàn cluster mở rộng phạm vi ảnh hưởng.

Không cấp `list` tất cả Secret chỉ để xem một token cụ thể có tồn tại hay không.

Một chính sách hẹp cho client chỉ cần lấy một Secret theo tên có thể được biểu diễn bằng:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: checkout-read-credential
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    resourceNames: ["checkout-credentials"]
    verbs: ["get"]
```

Role chưa có tác dụng với ServiceAccount nếu chưa được gắn qua RoleBinding. Ví dụ, với ServiceAccount `checkout-service` đã được tạo:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: checkout-read-credential
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: checkout-service
    namespace: shop
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: checkout-read-credential
```

Mẫu này mô tả quyền `get` đúng một tên; nó không bảo đảm mọi Kubernetes client hoặc cơ chế theo dõi đều chạy chỉ với quyền đó. Một phiên bản thư viện có thể dùng `list` để tìm nguồn hoặc cần thao tác khác.

Nếu client cần `list` hoặc `watch`, phải kiểm tra cách gọi và điều kiện giới hạn tài nguyên tương ứng. Không giả định `resourceNames` tự lọc được mọi lời gọi liệt kê. Trước khi mở rộng quyền, cân nhắc cấu hình nguồn cụ thể hoặc chọn đường truyền dữ liệu khác.

Namespace giúp tổ chức phạm vi tài nguyên nhưng không tự tạo ra ranh giới vững chắc nếu danh tính đã được cấp quyền rộng ở nhiều namespace.

## 5. Không có quyền get Secret chưa đủ để kết luận không thể lấy bí mật

Cần xét cả các quyền cho phép đưa dữ liệu tới một workload do người dùng kiểm soát.

Ví dụ, một người có quyền tạo Pod trong namespace có thể tạo workload tham chiếu Secret, nếu các chính sách admission và các ràng buộc khác không ngăn việc đó. Kubernetes có thể cung cấp Secret cho Pod mà không yêu cầu ServiceAccount của tiến trình ứng dụng có quyền `get` Secret qua API.

Các đường truy cập cần xem xét gồm:

- Tạo hoặc sửa workload để mount Secret.
- Thêm container hoặc thay image để đọc dữ liệu được cấp cho Pod.
- Dùng quyền truy cập thực thi trong container đang giữ bí mật.
- Truy cập node hoặc thành phần hạ tầng có khả năng tiếp cận dữ liệu của workload.
- Đọc log, bản dump hoặc dữ liệu giám sát mà ứng dụng đã làm lộ.

Do đó, chính sách bảo vệ Secret cần kết hợp RBAC, chính sách workload, quyền vận hành và ranh giới hạ tầng. Không dùng một phép kiểm tra quyền `get secrets` duy nhất như bằng chứng hoàn chỉnh rằng bí mật không thể bị đọc.

Quyền sửa Secret cũng đáng chú ý: người không cần đọc giá trị hiện tại nhưng có thể thay nó vẫn có khả năng đổi đích xác thực, gây gián đoạn hoặc tác động đến hành vi ứng dụng. Cần bảo vệ cả tính bí mật và tính toàn vẹn.

## 6. Chọn đường đưa Secret vào Spring

| Đường nạp | Ứng dụng có trực tiếp gọi API để lấy Secret không? | Điểm cần bảo vệ |
| --- | --- | --- |
| Spring Cloud Kubernetes qua API | Có | Danh tính client, RBAC, phạm vi nguồn, dữ liệu trong tiến trình |
| Secret volume + Spring Boot đọc tệp | Không chỉ để đọc tệp đã mount | Tham chiếu volume, container nhận mount, quyền tệp, dữ liệu trong tiến trình |
| Biến môi trường từ Secret | Không chỉ để nhận biến môi trường | Môi trường tiến trình, công cụ chẩn đoán, dữ liệu trong tiến trình |

Không có lựa chọn nào giữ bí mật tuyệt đối trước chính mã ứng dụng đã được phép sử dụng giá trị. Khi tiến trình bị chiếm quyền, phải coi những bí mật mà tiến trình đọc được là có nguy cơ bị lộ.

### Lựa chọn A: đọc qua Spring Cloud Kubernetes

Một mẫu ý định nạp một nguồn Secret qua API:

```yaml
spring:
  application:
    name: checkout-service
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        enabled: false
      secrets:
        enabled: true
        enable-api: true
        name: checkout-credentials
        namespace: shop
```

Mẫu giả định bộ phiên bản Spring Boot, Spring Cloud và starter Spring Cloud Kubernetes tương thích, có hỗ trợ Config Data bằng `kubernetes:`. Cần kiểm tra tùy chọn nguồn theo profile hoặc các lựa chọn bổ sung của phiên bản để xác định đầy đủ tập đối tượng client sẽ đọc.

Ba điều kiện không thay thế nhau:

1. Thư viện và import phải cho phép nạp nguồn.
2. Cấu hình chức năng phải cho phép đọc Secret qua API.
3. Danh tính thực tế phải được RBAC cho phép thực hiện thao tác cần thiết.

`enable-api: true` không tự cấp Role. Ngược lại, có Role đọc Secret không tự làm giá trị xuất hiện trong Environment nếu không cấu hình cơ chế nạp.

Nếu ứng dụng chỉ cần đọc một Secret cụ thể, không mở rộng sang lựa chọn tất cả Secret trong namespace cho tiện. Nếu không cần API đọc Secret, cân nhắc đường volume thay vì giữ thêm quyền và client chỉ cho mục đích này.

### Lựa chọn B: mount thành tệp và dùng configtree

Với Secret minh họa ở trên, có thể tạo Pod:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: checkout-secret-demo
  namespace: shop
spec:
  automountServiceAccountToken: false
  containers:
    - name: app
      image: example.invalid/checkout-service:training
      volumeMounts:
        - name: payment-credential
          mountPath: /run/app-secrets
          readOnly: true
  volumes:
    - name: payment-credential
      secret:
        secretName: checkout-credentials
        items:
          - key: payment.api-token
            path: payment.api-token
```

Image là chỗ giữ cho bài học. Mẫu này giả định ứng dụng không cần gọi Kubernetes API bằng token ServiceAccount được mount.

Kubernetes đưa khóa đã chọn thành tệp:

```text
/run/app-secrets/payment.api-token
```

Cấu hình khởi động của Spring Boot:

```yaml
spring:
  config:
    import: "configtree:/run/app-secrets/"
  cloud:
    kubernetes:
      config:
        enabled: false
      secrets:
        enabled: false
      discovery:
        enabled: false
```

Ở đây, Spring Boot đọc cây tệp; chức năng đọc Secret của Spring Cloud Kubernetes không cần bật để thực hiện việc đó. Nếu dự án không có các thư viện Kubernetes tương ứng, chỉ cần phần import phục vụ đọc tệp.

Tắt chức năng Secret của Spring Cloud Kubernetes không xóa các tệp mà Kubernetes đã mount và không ngăn Spring Boot đọc chúng bằng cơ chế riêng.

`items` chỉ đưa khóa cần thiết vào volume của ví dụ. Không mount toàn bộ tập thông tin xác thực vào một container chỉ cần một token.

Nếu ứng dụng vẫn cần DiscoveryClient hoặc một tính năng khác gọi API, phải cấu hình lại danh tính và quyền tương ứng. Việc đọc Secret từ volume không cấp quyền discovery, cũng không đòi cấp quyền đọc Secret qua API cho client discovery.

### Lựa chọn C: biến môi trường

Ví dụ ánh xạ một khóa:

```yaml
env:
  - name: PAYMENT_APITOKEN
    valueFrom:
      secretKeyRef:
        name: checkout-credentials
        key: payment.api-token
```

Tên `PAYMENT_APITOKEN` biểu diễn `payment.api-token` theo quy tắc chuyển tên thuộc tính sang biến môi trường của Spring Boot: thay dấu chấm bằng gạch dưới, bỏ dấu gạch nối và viết hoa.

Không đưa giá trị thật vào trường `value` của manifest thay cho `secretKeyRef`. Cũng không in toàn bộ biến môi trường khi xử lý sự cố.

Biến môi trường của container đang chạy không tự đổi khi Secret đổi. Nếu dùng cách này, phải có chiến lược tạo lại container để nhận giá trị mới.

## 7. Giữ ranh giới bảo vệ sau khi binding

Khi dữ liệu vào Spring Environment, nó vẫn là bí mật. Binding thành công không đổi mức độ nhạy cảm.

Ví dụ đối tượng thuộc tính cho Java 17, Spring Boot 3 và Bean Validation:

```java
package com.example.checkout;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment")
public class PaymentCredentials {

    @NotBlank
    private String apiToken;

    public String getApiToken() {
        return apiToken;
    }

    public void setApiToken(String apiToken) {
        this.apiToken = apiToken;
    }
}
```

Đăng ký lớp này qua `@ConfigurationPropertiesScan` hoặc cơ chế tương đương và có thư viện validation phù hợp.

Lớp không sinh `toString()` chứa token. Đây chỉ là một biện pháp tránh lộ ngoài ý muốn, không phải bảo vệ trước mã có quyền gọi getter hoặc đọc bộ nhớ.

Các nguyên tắc sử dụng:

- Chỉ đưa token tới thành phần cần dùng.
- Không trả đối tượng thuộc tính qua API chẩn đoán.
- Không dùng annotation hoặc công cụ tự sinh `toString()` chứa bí mật.
- Không ghi token vào exception, URL hoặc thông báo validation.
- Kiểm tra việc log request/response, đặc biệt là header xác thực.
- Giới hạn quyền truy cập heap dump, bản ghi chẩn đoán và các endpoint quản trị.

Record có thể sinh `toString()` từ các thành phần; vì thế, không chọn record chứa token rồi log cả đối tượng như một cấu hình thông thường.

Cơ chế che giá trị của công cụ quản trị là một lớp hỗ trợ. Không mặc định mọi khóa tùy biến đều được che đúng hoặc mọi endpoint đều đã có kiểm soát truy cập. Hãy kiểm tra trên dữ liệu giả và chỉ công bố thông tin tối thiểu cần cho vận hành.

## 8. Repository, pipeline và bản sao lưu cũng nằm trong phạm vi bảo vệ

Bí mật có thể bị lộ trước khi được tạo thành đối tượng Kubernetes.

Những vị trí cần kiểm soát gồm:

| Vị trí | Tình huống dễ làm lộ | Cách giảm rủi ro |
| --- | --- | --- |
| Repository | Commit manifest có `stringData` thật hoặc `data` base64 thật | Chỉ lưu mẫu không có giá trị thật, hoặc dùng cơ chế quản lý bí mật được tổ chức phê duyệt |
| Pipeline | In lệnh, biến hoặc nội dung tệp bí mật | Hạn chế dữ liệu đưa vào log, dùng cơ chế truyền bí mật của nền tảng |
| Artifact | Đóng gói mật khẩu trong image hoặc tệp cấu hình | Cấp dữ liệu khi triển khai theo cơ chế phù hợp |
| Công cụ quản trị | Xuất toàn bộ Secret để chia sẻ xử lý lỗi | Chia sẻ trạng thái, tên khóa và mã lỗi đã được xem xét thay vì giá trị |
| Audit và giám sát | Thu thập payload hoặc trường nhạy cảm quá mức | Xem xét chính sách ghi nhận và quyền đọc dữ liệu vận hành |
| Bản sao lưu | Chứa dữ liệu Secret nhưng được chia sẻ rộng | Bảo vệ bản sao và khóa bảo vệ tương ứng, kiểm soát phục hồi |

Xóa một giá trị khỏi phiên bản mới nhất của repository không xóa nó khỏi lịch sử hoặc các bản clone. Nếu giá trị thật đã được công khai ngoài phạm vi cho phép, cần xử lý như một sự cố lộ bí mật và thu hồi hoặc thay thế tại hệ thống cấp phát.

Hệ thống quản lý bí mật bên ngoài có thể hỗ trợ cấp phát, thời hạn và chính sách truy cập. Nhưng nếu dữ liệu được đồng bộ thêm vào Kubernetes Secret, bản sao trong Kubernetes vẫn cần được bảo vệ. Việc có một nguồn quản lý tập trung không xóa trách nhiệm với các bản sao và tiến trình đã nhận dữ liệu.

## 9. Xoay vòng phải đi tới nơi thực sự sử dụng giá trị

Cần phân biệt ba sự kiện:

```text
Thông tin xác thực mới được cấp
    -> Secret được cập nhật
    -> ứng dụng thực sự dùng thông tin xác thực mới
```

Một Secret mới chỉ giải quyết lớp phân phối. Hệ thống đích mới là nơi quyết định thông tin xác thực nào được chấp nhận.

| Cách truyền vào ứng dụng | Sau khi Secret đổi | Điều cần làm rõ |
| --- | --- | --- |
| Biến môi trường | Container đang chạy giữ giá trị đã nhận | Tạo lại container để nhận dữ liệu mới |
| Volume thông thường | Kubernetes có thể cập nhật tệp sau một khoảng trễ | Spring và client có đọc lại, áp dụng lại không? |
| Volume qua `subPath` | Không nhận cập nhật tự động như mount volume thông thường | Có rollout để nhận dữ liệu mới không? |
| Config Data qua API | Lần nạp startup không tự bảo đảm có lần nạp tiếp theo | Cơ chế theo dõi, refresh hoặc rollout nào được cấu hình? |

Configuration Watcher có thể tham gia đường phản ứng với thay đổi, nhưng không bảo đảm mọi bean, connection pool hoặc thư viện client đều có thể đổi thông tin xác thực tại chỗ.

Nếu ứng dụng không có yêu cầu cập nhật nóng, rollout có kiểm soát thường là một lựa chọn dễ xác định: instance mới nạp cấu hình mới và tạo lại thành phần sử dụng bí mật.

### Một quy trình rotation có thể kiểm soát

Trong trường hợp hệ thống đích cho phép khoảng chuyển tiếp với hai thông tin xác thực:

1. Cấp thông tin xác thực mới với quyền tối thiểu và hạn dùng phù hợp.
2. Đưa giá trị mới vào nguồn phân phối theo quy trình được bảo vệ.
3. Cập nhật workload hoặc cơ chế nạp để các instance nhận giá trị mới.
4. Xác nhận hành vi xác thực thực tế, không chỉ kiểm tra Secret đã tồn tại.
5. Xác nhận các instance cần chuyển đổi đã hoàn tất.
6. Thu hồi thông tin xác thực cũ tại hệ thống đích.
7. Dọn các nguồn và bản sao không còn cần theo chính sách.

Nếu hệ thống không hỗ trợ hai giá trị cùng hiệu lực, cần kế hoạch chuyển đổi phù hợp với giới hạn đó. Không mặc định mọi loại token, tài khoản hoặc khóa đều có cùng giao thức rotation.

Khi có nghi ngờ bị lộ, ưu tiên và thứ tự xử lý có thể khác một đợt rotation thông thường. Không khôi phục về một giá trị đã bị lộ chỉ để rollback cấu hình.

### Xóa Secret không phải thu hồi thông tin xác thực

Xóa đối tượng Kubernetes không tự:

- Vô hiệu hóa token ở nhà cung cấp.
- Đổi mật khẩu ở cơ sở dữ liệu.
- Xóa giá trị đã nhận khỏi môi trường hoặc bộ nhớ của tiến trình.
- Thu hồi các bản sao đã ghi vào log hoặc artifact.
- Đóng mọi phiên hoặc kết nối đã được thiết lập.

Cần thu hồi ở nơi cấp và xác minh hành vi của hệ thống đích. Việc đóng hoặc thay kết nối đang tồn tại còn phụ thuộc sản phẩm và giao thức sử dụng.

Tương tự, ConfigMap hoặc Secret bất biến giúp kiểm soát việc sửa nội dung tại chỗ; tính bất biến không ngăn người có quyền đọc lấy giá trị và không thay thế RBAC.

## 10. Quan sát và health check mà không làm lộ bí mật

Mục tiêu chẩn đoán là biết hệ thống có cấu hình cần thiết và có sử dụng được hay không, không phải xem giá trị thật.

Có thể ghi nhận:

- Tên nguồn và namespace nếu thông tin đó được phép công bố.
- Tình trạng có hoặc thiếu khóa cần thiết.
- Mã phiên bản triển khai hoặc thế hệ thông tin xác thực không bí mật.
- Kết quả binding và khởi tạo với thông báo đã được xem xét.
- Thành công hoặc thất bại của thao tác xác thực ở mức thông tin cần thiết.

Không dùng mật khẩu, token, một phần token hoặc hash của bí mật làm định danh log mặc định. Những dấu vết đó cũng có thể tạo thêm thông tin hữu ích cho người không được phép.

Phân biệt ba lỗi:

| Lỗi | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| Không đọc được nguồn | Dữ liệu chưa tới ứng dụng theo đường dự định | Kiểm tra tham chiếu, namespace, cơ chế truyền, quyền |
| Có giá trị nhưng binding/validation thất bại | Dữ liệu không đáp ứng cấu trúc hoặc ràng buộc | Kiểm tra tên khóa, kiểu, giá trị bắt buộc mà không công khai bí mật |
| Bind thành công nhưng xác thực thất bại | Hình thức hợp lệ nhưng hệ thống đích không chấp nhận | Kiểm tra cấp phát, hạn dùng, phạm vi quyền, rotation |

Một token giả không rỗng vẫn có thể qua `@NotBlank`. Validation thuộc tính không chứng minh token đúng, chưa hết hạn hoặc có đủ quyền.

Readiness nên phản ánh khả năng phục vụ mà ứng dụng cần bảo đảm. Nếu thông tin xác thực của một chức năng bắt buộc không dùng được, cần xử lý readiness theo thiết kế của hệ thống. Nếu phụ thuộc là tùy chọn, có thể cần trạng thái giảm chức năng thay vì chặn toàn bộ.

Không cho liveness thất bại với mọi lỗi xác thực hoặc phụ thuộc bên ngoài chỉ để restart liên tục. Restart không sửa được token đã bị thu hồi hoặc quyền sai.

## 11. Tình huống thực tế: token thanh toán của checkout-service

Giả sử ứng dụng có:

- ConfigMap chứa địa chỉ nhà cung cấp và timeout.
- Secret chứa `payment.api-token`.
- Một client thanh toán tạo khi startup.
- DiscoveryClient phục vụ một nhu cầu khác trong cluster.

Một thiết kế cần nêu rõ các ranh giới sau:

1. Token đi qua volume hay API? Không nạp hai lần nếu không có mục đích.
2. Nếu dùng volume, container nào được mount và đường dẫn nào được import?
3. Nếu dùng API, ServiceAccount nào đọc và client thực hiện những thao tác nào?
4. Quyền discovery có tách khỏi quyền đọc Secret không?
5. Client giữ token lúc tạo hay hỗ trợ thay đổi sau đó?
6. Ai kích hoạt rollout hoặc refresh?
7. Cách xác nhận client đã dùng token mới mà không ghi giá trị ra log?
8. Ai thu hồi token cũ tại nhà cung cấp?

Giả sử Secret đã đổi nhưng client vẫn giữ token cũ trong trường được gán lúc tạo. Pod có thể Running và binding lúc startup đã thành công, nhưng các yêu cầu thanh toán mới bị từ chối sau khi token cũ bị thu hồi.

Cách sửa không phải in cả Secret để so sánh. Cần xác định đường nạp, vòng đời client và quá trình chuyển đổi các instance, rồi áp dụng cơ chế tạo lại hoặc tái cấu hình đã được hỗ trợ.

## 12. Bài thực hành nhận diện ranh giới

Chỉ sử dụng dữ liệu giả trong namespace học tập.

| Thử nghiệm | Điều cần chứng minh |
| --- | --- |
| Tạo Secret bằng `stringData` với token giả | Cách nhập chuỗi không phải cơ chế giữ manifest bí mật |
| Quan sát biểu diễn `data` trên dữ liệu giả | Base64 là biểu diễn có thể đảo ngược |
| Dùng Role chỉ đọc một tên với client chỉ cần `get` | Quyền có thể gắn với nhu cầu cụ thể |
| Mount Secret cho ứng dụng không gọi API | Đọc tệp không đòi tiến trình có quyền đọc Secret qua API |
| Bỏ khóa token bắt buộc hoặc để rỗng | Khâu mount hoặc validation phát hiện theo cấu hình tương ứng |
| Dùng token giả không rỗng | Validation có thể qua nhưng không chứng minh xác thực thành công |
| Đổi Secret khi client đã tồn tại | Phân phối dữ liệu mới khác với áp dụng vào client |
| Kiểm tra log và thông báo lỗi bằng dữ liệu giả | Xác định có giá trị nhạy cảm bị xuất ngoài ý muốn không |

Không dùng việc truy cập được tệp như bằng chứng rằng mô hình quyền đã hoàn chỉnh. Cần xem thêm người sửa workload, người truy cập container, quyền của pipeline và dữ liệu chẩn đoán.

## 13. Các câu hỏi cần chốt trước triển khai

- Giá trị nào thực sự là bí mật và ai chịu trách nhiệm cấp phát?
- Mỗi workload cần chính xác những khóa nào?
- Bí mật được truyền qua API, volume hay môi trường container?
- Những danh tính nào có thể đọc trực tiếp hoặc tạo đường đọc gián tiếp?
- Cấu hình mã hóa, bản sao lưu và khóa bảo vệ của môi trường đã được xác định chưa?
- Ứng dụng có thể làm lộ giá trị qua log, serialization, endpoint hoặc dump không?
- Khi Secret đổi, client nào cần được tạo lại hoặc tái cấu hình?
- Khi giá trị cũ bị lộ, ai có quyền thu hồi tại hệ thống đích?
- Cách quan sát và readiness có cung cấp đủ bằng chứng mà không công khai bí mật không?

Secret tạo ra một nơi phân phối và áp dụng chính sách riêng cho dữ liệu nhạy cảm. Hiệu quả bảo vệ phụ thuộc vào toàn bộ đường đi của dữ liệu, từ cấp phát đến thu hồi, cùng những danh tính và tiến trình được phép sử dụng nó. Trong Spring Cloud Kubernetes, hãy chỉ mở quyền và bật tính năng tương ứng với đường đi đã chọn.
