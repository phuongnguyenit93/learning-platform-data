# Chọn nguồn ConfigMap, Secret hoặc kết hợp cả hai

Trong chương **Nạp Config Data** của **SPRING_CLOUD_KUBERNETES**, chọn nguồn cấu hình là quyết định về dữ liệu, quyền truy cập và hành vi khởi động. Một ứng dụng có thể lấy tham số vận hành từ ConfigMap, thông tin xác thực từ Secret, hoặc kết hợp hai nguồn để tạo ra một Spring Environment hoàn chỉnh.

Bài học này giúp bạn chọn nguồn theo từng thuộc tính, chọn cách đưa dữ liệu vào Spring và xác định điều kiện để ứng dụng được phép chạy. Các quyết định này cũng ảnh hưởng đến DiscoveryClient, Spring Cloud LoadBalancer và Configuration Watcher: bật thêm một tính năng có thể tạo thêm nhu cầu truy cập Kubernetes API, nhưng không có nghĩa mọi ứng dụng đều cần quyền đọc Secret qua API.

## 1. Tách ba quyết định trước khi viết cấu hình

Có ba câu hỏi khác nhau cần trả lời:

| Quyết định | Câu hỏi cần giải quyết | Ví dụ |
| --- | --- | --- |
| Phân loại dữ liệu | Giá trị này có cần giữ bí mật không? | Timeout là tham số vận hành; mật khẩu cơ sở dữ liệu là bí mật |
| Chọn đối tượng Kubernetes | Giá trị thuộc ConfigMap hay Secret nào? | `checkout-public` hoặc `checkout-private` |
| Chọn cơ chế nạp | Spring nhận giá trị qua Kubernetes API, tệp được mount hay biến môi trường? | Spring Cloud Kubernetes Config Data hoặc Spring Boot `configtree:` |

ConfigMap và Secret là hai loại đối tượng lưu dữ liệu trong Kubernetes. Chúng không tự xuất hiện trong Spring Environment chỉ vì có cùng namespace với Pod. Ứng dụng cần một cơ chế nạp được cấu hình rõ ràng.

Ví dụ, tạo Secret thành công nhưng không import qua API, không mount thành tệp và không khai báo biến môi trường thì ứng dụng vẫn không có mật khẩu. Ngược lại, ứng dụng có thể đọc Secret từ tệp do Kubernetes mount mà không cần tự gọi Kubernetes API để lấy Secret.

## 2. Khi nào chọn ConfigMap?

ConfigMap phù hợp với cấu hình không bí mật, có thể thay đổi giữa các môi trường hoặc các lần triển khai:

- Địa chỉ dịch vụ công khai trong hệ thống, nếu chính sách nội bộ cho phép công khai thông tin này.
- Timeout, số lần thử lại và giới hạn kết nối.
- Cờ tính năng không chứa thông tin xác thực.
- Tiền tệ, định dạng hiển thị, giá trị mặc định theo môi trường.
- Cấu hình hành vi của DiscoveryClient hoặc LoadBalancer khi ứng dụng thực sự sử dụng các tính năng đó.

Ví dụ:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-public
  namespace: shop
data:
  checkout.payment-base-url: "http://payment-service"
  checkout.request-timeout: "2s"
  checkout.currency: "VND"
  spring.datasource.url: "jdbc:postgresql://orders-db:5432/orders"
```

Địa chỉ cơ sở dữ liệu trong ví dụ không chứa tên người dùng hay mật khẩu. Nếu URL có mật khẩu, token trong query string hoặc thông tin hạ tầng mà tổ chức coi là nhạy cảm, phải phân loại lại giá trị đó.

### Những điều ConfigMap không giải quyết

ConfigMap không phải kho bí mật. Đưa mật khẩu vào một khóa có tên `password`, đặt tên đối tượng là `private-config` hoặc giấu giá trị trong một tệp `application.yml` đều không thay đổi bản chất này.

ConfigMap cũng không phải cơ sở dữ liệu dành cho dữ liệu nghiệp vụ thay đổi liên tục. Giỏ hàng, trạng thái thanh toán và lịch sử giao dịch cần nơi lưu trữ phù hợp với nghiệp vụ, không nên trở thành Config Data của ứng dụng.

## 3. Khi nào chọn Secret?

Secret phù hợp với giá trị cần hạn chế người và workload có thể đọc:

- Mật khẩu cơ sở dữ liệu.
- Token gọi dịch vụ bên ngoài.
- Khóa riêng, chứng thư kèm khóa riêng và thông tin xác thực.
- Một chuỗi kết nối có chứa thông tin xác thực.

Ví dụ minh họa cách khai báo bằng `stringData`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: checkout-private
  namespace: shop
type: Opaque
stringData:
  spring.datasource.username: "REPLACE_WITH_RUNTIME_USERNAME"
  spring.datasource.password: "REPLACE_WITH_RUNTIME_PASSWORD"
```

Các giá trị trên chỉ là chỗ giữ trong tài liệu. Không đưa thông tin xác thực thật vào repository học tập hoặc manifest được chia sẻ. Trong triển khai thực tế, dùng quy trình cấp phát bí mật của môi trường để tạo hoặc đồng bộ Secret.

### Secret không đồng nghĩa với mã hóa đầu cuối

Trường `data` của Secret biểu diễn giá trị bằng base64; base64 là cách mã hóa biểu diễn, không bảo vệ bí mật trước người có quyền đọc. `stringData` giúp gửi chuỗi rõ khi tạo hoặc cập nhật đối tượng, không làm giá trị an toàn hơn.

Việc bảo vệ Secret còn phụ thuộc vào:

- RBAC và danh tính nào có quyền lấy đối tượng.
- Cấu hình mã hóa dữ liệu lưu trữ của cluster.
- Quyền truy cập Pod, container, volume và công cụ chẩn đoán.
- Cách ứng dụng ghi log, xuất thông tin cấu hình và tạo bản dump.
- Quy trình cấp phát, thu hồi và xoay vòng thông tin xác thực.

Một Secret đã nạp vào ứng dụng vẫn là dữ liệu bí mật. Không ghi toàn bộ Environment hoặc nội dung Secret ra log để kiểm tra việc nạp.

## 4. Ma trận chọn nguồn

| Tình huống | Nguồn nên chọn | Lý do và điều kiện |
| --- | --- | --- |
| Chỉ có timeout, URL không bí mật, cờ tính năng | ConfigMap | Không phát sinh nhu cầu đọc Secret |
| Chỉ có token; các tham số khác nằm sẵn trong ứng dụng | Secret | Không cần tạo ConfigMap chỉ để đủ một cặp |
| Có cả tham số vận hành và thông tin xác thực | ConfigMap + Secret | Tách vòng đời, quyền quản trị và mức độ nhạy cảm |
| Một chuỗi kết nối chứa cả host và mật khẩu | Secret, hoặc tách thành các thuộc tính | Không để một phần bí mật lọt vào ConfigMap |
| Ứng dụng chỉ cần vài giá trị mặc định cố định | Cấu hình đóng gói trong ứng dụng | Không bắt buộc thêm nguồn Kubernetes |
| Đã có nền tảng quản lý bí mật bên ngoài | Theo cơ chế tích hợp của nền tảng | Không tự sao chép bí mật vào nhiều nơi nếu chưa có nhu cầu |

Không quyết định chỉ dựa trên tên khóa. `client-id` có thể là định danh công khai trong một hệ thống, nhưng được coi là thông tin nhạy cảm trong hệ thống khác. Cần xét ý nghĩa của giá trị và chính sách thực tế.

Cũng không quyết định dựa trên số lượng khóa: một mật khẩu duy nhất vẫn cần được bảo vệ, còn hàng chục tham số không bí mật vẫn có thể nằm trong ConfigMap.

## 5. Khi kết hợp, chia theo trách nhiệm của từng thuộc tính

Với dịch vụ thanh toán đơn hàng `checkout-service`, có thể phân chia như sau:

| Thuộc tính | Nguồn sở hữu | Bắt buộc khi khởi động? |
| --- | --- | --- |
| `checkout.payment-base-url` | ConfigMap `checkout-public` | Có nếu chức năng thanh toán luôn được bật |
| `checkout.request-timeout` | ConfigMap `checkout-public` | Có, hoặc có mặc định được chấp thuận |
| `checkout.currency` | ConfigMap `checkout-public` | Tùy quy tắc nghiệp vụ |
| `spring.datasource.url` | ConfigMap `checkout-public` | Có với ứng dụng luôn sử dụng cơ sở dữ liệu |
| `spring.datasource.username` | Secret `checkout-private` | Có |
| `spring.datasource.password` | Secret `checkout-private` | Có |

Nguyên tắc dễ vận hành nhất là **mỗi thuộc tính có một nguồn sở hữu chính**. Không đặt cùng `spring.datasource.password` ở cả ConfigMap, Secret và biến môi trường rồi trông chờ một nguồn “tự thắng”.

Một thuộc tính có thể có giá trị mặc định trong ứng dụng và được ghi đè theo môi trường, nhưng sự ghi đè đó phải có chủ đích. Với bí mật bắt buộc, không dùng mật khẩu dự phòng chỉ để ứng dụng khởi động thành công.

### Phân chia theo môi trường

Namespace giúp giới hạn phạm vi tìm và truy cập đối tượng. Ví dụ, các namespace `shop-dev` và `shop-prod` có thể cùng có tên ConfigMap `checkout-public`, nhưng chứa giá trị khác nhau.

Không cấu hình ứng dụng production đọc namespace development để “dùng tạm” một mật khẩu hoặc một URL. Khi xác định nguồn, cần xét bộ ba:

```text
loại đối tượng + namespace + tên đối tượng
```

Trong ví dụ của bài, đó là `ConfigMap/shop/checkout-public` và `Secret/shop/checkout-private`.

## 6. Chọn cách nạp: Kubernetes API, tệp hay biến môi trường?

Chọn ConfigMap hoặc Secret chưa quyết định ứng dụng có cần Kubernetes client hay không.

| Cơ chế | Ai lấy dữ liệu từ Kubernetes? | Cách Spring nhận giá trị | Quyền của tiến trình ứng dụng |
| --- | --- | --- | --- |
| Spring Cloud Kubernetes qua API | Kubernetes client trong ứng dụng | Config Data và các PropertySource tương ứng | Cần RBAC cho những API thực sự được gọi |
| Volume + `configtree:` | Kubernetes quản lý và mount volume | Spring Boot đọc tệp, tên tệp trở thành tên thuộc tính | Không cần quyền đọc ConfigMap/Secret qua API chỉ để đọc các tệp này |
| `env` hoặc `envFrom` | Kubernetes đưa giá trị vào môi trường container | Spring Boot đọc biến môi trường | Không cần quyền đọc ConfigMap/Secret qua API chỉ vì dùng biến môi trường |

Nếu ứng dụng vẫn dùng DiscoveryClient hoặc tính năng khác gọi Kubernetes API, nó có thể vẫn cần ServiceAccount token và RBAC cho tính năng đó. Quyền cần để khám phá Service không đồng nghĩa với quyền đọc Secret.

### Cách A: Spring Cloud Kubernetes nạp qua API

Đây là lựa chọn phù hợp khi ứng dụng đã chủ đích sử dụng Spring Cloud Kubernetes Config Data và bạn muốn khai báo rõ các nguồn API.

Ví dụ cấu hình theo mô hình Config Data của Spring Cloud Kubernetes:

```yaml
spring:
  application:
    name: checkout-service
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        enabled: true
        namespace: shop
        sources:
          - name: checkout-public
      secrets:
        enabled: true
        enable-api: true
        namespace: shop
        sources:
          - name: checkout-private
```

Mẫu trên mô tả ý định đọc đúng một ConfigMap và một Secret. Nó giả định dự án đã chọn phiên bản Spring Boot, Spring Cloud và starter Spring Cloud Kubernetes tương thích, có hỗ trợ `kubernetes:` trong Config Data. Cần đối chiếu các thuộc tính với phiên bản đang dùng; không ghép cấu hình bootstrap của một thế hệ thư viện với cơ chế Config Data của thế hệ khác.

Các điểm cần phân biệt:

- `spring.config.import` kích hoạt cơ chế import tương ứng; chỉ khai báo tên ConfigMap không thay cho bước này.
- `config.enabled` điều khiển chức năng cấu hình từ ConfigMap.
- `secrets.enabled` và `secrets.enable-api` có vai trò khác nhau: bật chức năng Secret không tự đồng nghĩa đã cho phép đọc Secret qua API.
- RBAC vẫn phải cho phép thao tác mà client thực hiện. Một cờ cấu hình trong ứng dụng không cấp quyền Kubernetes.
- Không dùng danh sách Secret quá rộng khi ứng dụng chỉ cần một nguồn cụ thể.

Nếu chọn **chỉ ConfigMap**, loại bỏ phần khai báo nguồn Secret không dùng và tắt chức năng Secret qua API theo cấu hình của phiên bản. Nếu chọn **chỉ Secret**, tắt nguồn ConfigMap không cần thiết và khai báo nguồn Secret cần đọc. Không để cấu hình thừa khiến ứng dụng vô tình tìm thêm nguồn theo tên mặc định.

Với mô hình này, thay đổi cấu hình import, tên nguồn hoặc namespace là thay đổi cách ứng dụng xây dựng Environment. Thông thường nên đặt những thông tin định vị nguồn trong cấu hình khởi động hoặc manifest triển khai; đừng đặt thông tin cần để tìm một Secret duy nhất bên trong chính Secret đó.

### Cách B: Mount hai nguồn và dùng `configtree:`

Nếu ứng dụng chỉ cần nhận dữ liệu dưới dạng tệp, có thể mount ConfigMap và Secret rồi dùng Config Data của Spring Boot. Khi đó không cần bật API đọc Secret của Spring Cloud Kubernetes cho mục đích này.

Với hai đối tượng ở trên, phần liên quan của Deployment có thể viết:

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
      containers:
        - name: app
          image: example.invalid/checkout-service:training
          volumeMounts:
            - name: public-config
              mountPath: /etc/app-config
              readOnly: true
            - name: private-config
              mountPath: /etc/app-secret
              readOnly: true
      volumes:
        - name: public-config
          configMap:
            name: checkout-public
        - name: private-config
          secret:
            secretName: checkout-private
```

Địa chỉ image là chỗ giữ cho bài học; thay bằng image của ứng dụng trước khi triển khai. Hai đối tượng nguồn phải ở cùng namespace `shop` với Pod để tham chiếu volume theo cách này.

Cấu hình trong ứng dụng:

```yaml
spring:
  application:
    name: checkout-service
  config:
    import:
      - "configtree:/etc/app-config/"
      - "configtree:/etc/app-secret/"
```

Với ConfigMap có khóa `checkout.request-timeout`, Kubernetes tạo một tệp cùng tên dưới `/etc/app-config/`. `configtree:` ánh xạ tên tệp thành tên thuộc tính và nội dung tệp thành giá trị. Tương tự, tệp `/etc/app-secret/spring.datasource.password` cung cấp thuộc tính `spring.datasource.password`.

Mẫu này dùng **mỗi khóa là một thuộc tính**, không đặt nguyên tài liệu YAML trong một tệp rồi kỳ vọng `configtree:` tự phân tích như `application.yml`. Nếu chọn lưu một tệp YAML hoàn chỉnh, phải dùng cơ chế import tệp YAML phù hợp của Spring Boot và quản lý cấu trúc theo cách đó.

Trong lựa chọn mount tệp này, không đồng thời giữ `spring.config.import: "kubernetes:"` để đọc lại chính các nguồn đó nếu không có nhu cầu rõ ràng. Việc nạp hai lần tạo thêm đường truy cập và làm việc giải thích nguồn của một giá trị khó hơn.

### Cách C: Đưa một số giá trị vào biến môi trường

Với một vài thuộc tính, có thể ánh xạ tường minh:

```yaml
env:
  - name: SPRING_DATASOURCE_PASSWORD
    valueFrom:
      secretKeyRef:
        name: checkout-private
        key: spring.datasource.password
```

Spring Boot ánh xạ `SPRING_DATASOURCE_PASSWORD` tới `spring.datasource.password` theo quy tắc binding cấu hình.

Cách này không cần import Kubernetes API để lấy riêng giá trị đó. Tuy nhiên, biến môi trường của container đang chạy không tự đổi khi Secret đổi. Cần tạo container mới, thường thông qua rollout, nếu muốn cập nhật giá trị bằng cơ chế này.

Với khóa có dấu chấm hoặc dấu gạch nối, ánh xạ `env` tường minh giúp tránh phụ thuộc vào quy tắc tên biến môi trường của môi trường Kubernetes đang dùng. Không mặc định rằng mọi khóa của ConfigMap hoặc Secret sẽ dùng được nguyên dạng qua `envFrom`.

## 7. Quyền tối thiểu phụ thuộc cách lấy dữ liệu

Với API import, lập danh sách thao tác thực tế của Kubernetes client trước khi viết Role:

| Nhu cầu | Phạm vi quyền cần xem xét |
| --- | --- |
| Lấy ConfigMap đã biết tên | Đọc ConfigMap trong namespace cần thiết |
| Lấy Secret đã biết tên | Đọc đúng Secret cần dùng |
| Tìm nguồn theo label | Có thể cần thao tác liệt kê theo cách client triển khai |
| Theo dõi thay đổi qua API | Có thể cần `watch`, cùng các quyền đọc mà cơ chế theo dõi sử dụng |
| Khám phá Service hoặc Endpoint | Quyền cho tài nguyên discovery tương ứng, tách khỏi quyền Secret |

Không suy ra rằng tên nguồn đã cố định thì thư viện chắc chắn chỉ gọi `get`. Một client hoặc một chế độ theo dõi có thể thực hiện `list` trước khi chọn đối tượng. Quyền phải phù hợp với luồng gọi thực tế của phiên bản và tính năng đang bật.

Nếu client chỉ lấy từng đối tượng theo tên, có thể thiết kế Role hẹp với `resourceNames` và thao tác `get`. Nếu client cần `list` hoặc `watch`, cần đánh giá khả năng giới hạn bằng tên và điều kiện của các thao tác đó; không mặc định rằng `resourceNames` sẽ tự lọc mọi lời gọi liệt kê.

Đặc biệt, quyền `list` Secret có thể trả về nội dung của nhiều Secret trong phạm vi cho phép. Không coi đó là quyền “chỉ xem danh sách tên”.

Với volume, tiến trình ứng dụng đọc tệp đã mount nên không cần được cấp Role đọc Secret qua API chỉ vì nó sử dụng tệp đó. Dù vậy, quyền tạo hoặc sửa Pod, quyền truy cập container và cấu hình bảo mật volume vẫn là những phần quan trọng của ranh giới truy cập.

## 8. Kết hợp hai nguồn không tạo ra một giao dịch nguyên tử

ConfigMap và Secret là hai đối tượng độc lập. Chúng có thể được cập nhật, phân phối hoặc đọc ở những thời điểm khác nhau.

Ví dụ, phiên bản cấu hình mới đổi `spring.datasource.url` sang máy chủ khác, nhưng Secret vẫn chứa tài khoản chỉ hợp lệ trên máy chủ cũ. Cả hai nguồn đều tồn tại và đọc thành công, nhưng bộ cấu hình kết hợp không sử dụng được.

Để giảm rủi ro:

1. Xác định các thuộc tính phải thay đổi cùng nhau.
2. Chuẩn bị thông tin xác thực mới trước khi chuyển ứng dụng.
3. Với thay đổi cần nhất quán chặt, tạo các nguồn có tên phiên bản, chẳng hạn `checkout-public-v2` và `checkout-private-v2`.
4. Cập nhật Pod template để tham chiếu đúng cặp đã chuẩn bị rồi rollout.
5. Giữ khả năng khôi phục về cặp cũ theo quy trình triển khai; thu hồi bí mật cũ khi không còn workload phụ thuộc.

Tên có hậu tố phiên bản chỉ giúp định danh bộ cấu hình; nó không tự bảo đảm nội dung bất biến. Cần kiểm soát việc sửa đối tượng hoặc dùng khả năng bất biến của Kubernetes nếu phù hợp.

Không để Configuration Watcher tự động refresh mọi thay đổi ghép cặp nếu ứng dụng chưa có cách xử lý trạng thái trung gian. Một số thay đổi, đặc biệt là thông tin kết nối và đối tượng kết nối đã khởi tạo, phù hợp với rollout có kiểm soát hơn là cập nhật nóng.

## 9. Xử lý trùng khóa và thứ tự ưu tiên

Có hai lớp thứ tự khác nhau:

- Thứ tự giữa các nguồn mà bộ nạp Spring Cloud Kubernetes tạo ra.
- Thứ tự giữa Config Data và các nguồn cấu hình khác của Spring Boot như biến môi trường hoặc tham số dòng lệnh.

Không sử dụng quy tắc chung “Secret luôn thắng ConfigMap”. Kết quả phụ thuộc cơ chế nạp, thứ tự import, cách nguồn được tạo và các lớp cấu hình khác.

Với ví dụ `configtree:`, nếu hai cây cấu hình có cùng thuộc tính, thứ tự import có ý nghĩa đối với giá trị cuối cùng. Ngoài ra, một biến môi trường cùng thuộc tính có thể ghi đè giá trị từ Config Data theo quy tắc của Spring Boot.

Cách xử lý thực tế:

1. Tránh trùng khóa giữa `checkout-public` và `checkout-private`.
2. Quy định nguồn sở hữu của từng thuộc tính trong tài liệu triển khai.
3. Kiểm tra xem manifest có đặt thêm biến môi trường cho cùng thuộc tính không.
4. Khi cần ghi đè có chủ đích, kiểm tra giá trị hiệu lực bằng dấu hiệu không bí mật.
5. Nếu dùng công cụ xem nguồn cấu hình, giới hạn truy cập và che giá trị nhạy cảm; không công khai endpoint chẩn đoán.

Ví dụ, đổi `checkout.request-timeout` từ `2s` thành `3s` là phép kiểm tra an toàn hơn việc in mật khẩu để xác nhận Secret có thắng một nguồn khác hay không.

## 10. Quyết định khi nào thiếu nguồn phải làm ứng dụng dừng

Không phải mọi nguồn đều bắt buộc. Một ConfigMap điều khiển chức năng tùy chọn có thể vắng mặt nếu ứng dụng có mặc định hợp lệ. Ngược lại, Secret chứa mật khẩu của cơ sở dữ liệu bắt buộc không nên được coi là tùy chọn.

Cần kiểm tra ba lớp:

| Lớp kiểm tra | Điều kiện cần phát hiện | Ví dụ |
| --- | --- | --- |
| Truy cập nguồn | Không tìm thấy hoặc không đọc được nguồn cần thiết | Sai namespace, Secret chưa tạo, bị RBAC từ chối |
| Binding và validation | Thiếu khóa, rỗng, sai kiểu hoặc ngoài miền hợp lệ | Thiếu password, timeout âm, URL không hợp lệ |
| Sử dụng tài nguyên | Giá trị có hình thức đúng nhưng không dùng được | Mật khẩu sai, tài khoản hết hạn, đích kết nối không truy cập được |

Việc nguồn tồn tại không bảo đảm nguồn có đủ khóa. Việc bind thành công cũng không bảo đảm thông tin xác thực hợp lệ.

Với mount volume trong ví dụ, không đánh dấu ConfigMap và Secret là tùy chọn. Các import `configtree:` cũng không có tiền tố `optional:`. Đây là lựa chọn có chủ đích cho các nguồn bắt buộc; vẫn phải kiểm tra các thuộc tính bắt buộc sau khi đọc.

Với API import, thiết lập hành vi khi nguồn thiếu hoặc truy cập thất bại bằng các tùy chọn do phiên bản Spring Cloud Kubernetes đang dùng hỗ trợ. Không mặc định rằng có dòng `kubernetes:` là mọi trường hợp thiếu ConfigMap hoặc Secret đều sẽ làm ứng dụng dừng.

Chỉ dùng chế độ tùy chọn khi ứng dụng vẫn có một trạng thái hoạt động được thiết kế rõ ràng. Ví dụ, nếu thiếu token cho nhà cung cấp email phụ thì ứng dụng có thể tắt riêng chức năng gửi qua nhà cung cấp đó. Không dùng token giả, mật khẩu rỗng hoặc âm thầm chuyển sang nguồn bí mật của môi trường khác.

## 11. Cập nhật nguồn không đồng nghĩa ứng dụng đã dùng giá trị mới

| Cách truyền dữ liệu | Điều có thể xảy ra sau khi nguồn đổi | Việc cần xác nhận ở ứng dụng |
| --- | --- | --- |
| API Config Data | Environment đã được tạo khi khởi động; cập nhật đối tượng không tự bảo đảm có lần nạp mới | Có cơ chế refresh hoặc rollout nào được cấu hình? |
| Volume ConfigMap/Secret | Tệp mount thông thường có thể được Kubernetes cập nhật sau một khoảng trễ | Spring có đọc lại tệp và tái cấu hình bean không? |
| Volume mount bằng `subPath` | Không nhận cập nhật tự động của nguồn theo cách volume thông thường | Có rollout để thay container không? |
| Biến môi trường | Container đang chạy giữ giá trị cũ | Container đã được tạo lại chưa? |

Spring Boot đọc `configtree:` khi nạp Config Data; việc nội dung tệp thay đổi không tự làm mọi bean đọc lại thuộc tính.

Configuration Watcher có thể tham gia quy trình phản ứng với thay đổi khi được cài đặt và cấu hình phù hợp. Tuy nhiên, nó không tự bảo đảm mọi bean, pool kết nối hoặc thành phần của bên thứ ba có thể cập nhật nóng. Cần biết rõ cơ chế nào thực sự chạy và thuộc tính nào thành phần đích hỗ trợ thay đổi.

Khi xoay vòng mật khẩu cơ sở dữ liệu, cần kiểm tra cả thời điểm pool mở kết nối mới và cách các kết nối cũ tiếp tục hoạt động. Chỉ quan sát tệp Secret đổi chưa đủ để kết luận ứng dụng đã chuyển sang thông tin xác thực mới.

## 12. Theo dõi sức khỏe Pod theo đúng ý nghĩa

Một container ở trạng thái Running chỉ cho biết tiến trình đang tồn tại. Nó không chứng minh ConfigMap và Secret đã tạo thành bộ cấu hình sử dụng được.

- **Startup**: dành thời gian cho ứng dụng khởi tạo, bao gồm việc nạp cấu hình và các bước khởi tạo cần thiết.
- **Readiness**: phản ánh khả năng phục vụ lưu lượng theo chính sách của ứng dụng. Nếu một chức năng bắt buộc chưa thể hoạt động vì cấu hình sai, cần tránh đưa Pod đó vào phục vụ.
- **Liveness**: phản ánh tình trạng tiến trình cần được khởi động lại. Không gắn mọi lỗi tạm thời của dịch vụ bên ngoài vào liveness để gây vòng lặp restart.

Một Secret thiếu hẳn khi mount có thể khiến container chưa khởi động được. Một Secret tồn tại nhưng có mật khẩu sai có thể khiến ứng dụng lỗi lúc khởi tạo, hoặc chỉ lỗi khi mở kết nối, tùy cách ứng dụng khởi tạo tài nguyên. Hai tình huống cần được phân biệt khi chẩn đoán.

## 13. Bài thực hành chọn một phương án có chủ đích

Giả sử `checkout-service` có bốn yêu cầu:

1. Đọc URL dịch vụ thanh toán và timeout từ môi trường triển khai.
2. Đọc tài khoản cơ sở dữ liệu.
3. Không có nhu cầu tự đọc Kubernetes API chỉ để lấy cấu hình.
4. Chấp nhận rollout khi đổi thông tin xác thực.

Một phương án phù hợp là:

- ConfigMap chứa URL, timeout và URL cơ sở dữ liệu không có mật khẩu.
- Secret chứa username và password theo chính sách của môi trường.
- Mount hai nguồn vào hai thư mục riêng, import bằng `configtree:`.
- Kiểm tra thuộc tính bắt buộc khi khởi động và quan sát readiness.
- Rollout khi đổi bộ thông tin xác thực; không bật Secret API hoặc Configuration Watcher chỉ để hoàn thành bài này.

### Các phép kiểm tra nên thực hiện trong môi trường học tập

| Thay đổi thử nghiệm | Kết quả cần quan sát |
| --- | --- |
| Thay timeout hợp lệ rồi rollout | Ứng dụng dùng timeout mới |
| Bỏ Secret bắt buộc trước khi tạo Pod | Container không thể khởi động với volume nguồn còn thiếu |
| Giữ Secret nhưng bỏ khóa password | Validation hoặc bước khởi tạo phụ thuộc phát hiện thiếu dữ liệu |
| Cấp mật khẩu sai có hình thức hợp lệ | Kiểm tra binding có thể qua, nhưng kết nối thật thất bại |
| Thêm biến môi trường ghi đè timeout | Xác định giá trị hiệu lực và lý do ghi đè |
| Đổi Secret khi Pod vẫn đang chạy | Không kết luận thành công trước khi xác nhận ứng dụng thực sự dùng giá trị mới |

Không đưa giá trị Secret vào kết quả bài thực hành. Ghi nhận sự tồn tại của khóa, trạng thái khởi động, kết quả kết nối và nguồn cấu hình bằng thông tin đã được che.

Nếu yêu cầu thay đổi thành “ứng dụng phải trực tiếp lấy nguồn qua Kubernetes API”, hãy chuyển sang phương án API import và bổ sung RBAC tương ứng. Nếu chỉ bổ sung DiscoveryClient, đánh giá riêng quyền discovery; không tự chuyển toàn bộ việc đọc Secret sang API.

## 14. Những lỗi lựa chọn thường gặp

| Lỗi | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| Đưa cả tệp cấu hình vào ConfigMap dù có token | Bí mật được lưu trong đối tượng không phù hợp | Tách token sang Secret hoặc chuyển phần chứa bí mật sang nguồn phù hợp |
| Chọn Secret cho mọi tham số | Quyền truy cập và vòng đời thay đổi bị gom chung không cần thiết | Phân loại từng thuộc tính trước khi chọn nguồn |
| Chỉ tạo đối tượng, không cấu hình cơ chế nạp | Spring không có giá trị mong đợi | Khai báo API import, mount tệp hoặc ánh xạ biến môi trường |
| Bật Secret API nhưng quên RBAC | Ứng dụng không đọc được nguồn | Cấp đúng quyền cho đúng danh tính và thao tác cần dùng |
| Cấp quyền đọc tất cả Secret để sửa nhanh lỗi | Phạm vi truy cập vượt nhu cầu | Kiểm tra tên nguồn, namespace và thao tác client trước khi chỉnh quyền |
| Dùng cùng khóa ở nhiều nguồn | Khó dự đoán và giải thích giá trị cuối | Chỉ định nguồn sở hữu và ghi đè có chủ đích |
| Đánh dấu mọi nguồn là tùy chọn | Lỗi bị đẩy sang lúc xử lý yêu cầu | Chặn khởi động hoặc readiness khi thiếu điều kiện bắt buộc |
| Coi tệp Secret đã đổi là ứng dụng đã refresh | Bean hoặc pool kết nối tiếp tục dùng dữ liệu cũ | Kiểm tra cơ chế nạp lại hoặc rollout |
| Bật thêm Watcher dù luôn rollout | Tăng thành phần và quyền cần quản lý | Chỉ bật tính năng có yêu cầu vận hành cụ thể |

## 15. Quy tắc áp dụng cho bài toán của bạn

Bắt đầu từ danh sách thuộc tính và đánh dấu giá trị nào là bí mật. Chọn ConfigMap cho phần không bí mật, Secret cho phần bí mật, rồi quyết định ứng dụng sẽ nhận chúng qua API, tệp hoặc biến môi trường.

Sau đó, chốt nguồn sở hữu của từng khóa, cách xử lý khi thiếu và cách triển khai thay đổi. Chỉ bật các tính năng Spring Cloud Kubernetes cần để đáp ứng những quyết định đó. Khi bộ cấu hình đã nạp được, vẫn phải kiểm tra ứng dụng có sử dụng nó thành công và có sẵn sàng nhận lưu lượng hay chưa.
