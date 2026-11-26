# Quy tắc chọn ConfigMap theo tên ứng dụng

Trong chương **ConfigMap** của **SPRING_CLOUD_KUBERNETES**, tên ứng dụng là một đầu vào để xác định nguồn cấu hình. Nó không phải cơ chế tìm mọi ConfigMap “có vẻ liên quan” đến Pod.

Khi sử dụng Spring Cloud Kubernetes để nạp Config Data qua Kubernetes API, ứng dụng cần xác định tên ConfigMap và namespace trước khi lấy dữ liệu để tạo Spring Environment. Hiểu quy tắc này giúp bạn tránh đọc nhầm cấu hình, cấp quyền RBAC quá rộng hoặc bật thêm thành phần theo dõi chỉ để xử lý một lỗi đặt tên.

Bài học tập trung vào lựa chọn nguồn theo tên. DiscoveryClient, Spring Cloud LoadBalancer và Configuration Watcher có thể cùng tồn tại trong ứng dụng, nhưng chúng có vai trò riêng; việc khám phá được một Service không chứng minh ứng dụng đã chọn đúng ConfigMap.

## 1. Phạm vi áp dụng của quy tắc

Các ví dụ chính giả định ứng dụng dùng một bộ phiên bản Spring Boot, Spring Cloud và starter Spring Cloud Kubernetes tương thích, hỗ trợ Config Data với:

```yaml
spring:
  config:
    import: "kubernetes:"
```

Dòng import kích hoạt đường nạp tương ứng khi thư viện cần thiết có trên classpath. Tên ứng dụng được dùng trong quá trình lựa chọn nguồn, không thay thế việc cấu hình cơ chế nạp.

Cần phân biệt ba cách sử dụng ConfigMap:

| Cách sử dụng | Ai chọn ConfigMap? | Vai trò của tên ứng dụng |
| --- | --- | --- |
| Spring Cloud Kubernetes đọc qua API | Bộ nạp cấu hình dựa trên thuộc tính lựa chọn nguồn | Có thể làm tên nguồn mặc định |
| Kubernetes mount ConfigMap thành volume | Manifest Pod chỉ định `configMap.name` | Không tự đổi nguồn volume theo `spring.application.name` |
| Kubernetes đưa dữ liệu vào môi trường container | Manifest chỉ định `configMapKeyRef` hoặc `configMapRef` | Không tự chọn nguồn theo tên ứng dụng |

Nếu Pod mount `checkout-settings` nhưng Spring Cloud Kubernetes được cấu hình đọc `checkout-service`, đó là hai đường truy cập khác nhau. Việc mount thành công không làm bộ nạp API tự chuyển sang ConfigMap đã mount.

## 2. Quy tắc tên cho một nguồn mặc định

Trong trường hợp không khai báo danh sách nguồn `spring.cloud.kubernetes.config.sources`, quy tắc tên có thể hiểu theo thứ tự:

1. Nếu đặt `spring.cloud.kubernetes.config.name`, dùng tên cấu hình đó.
2. Nếu không đặt tên cấu hình riêng, dùng `spring.application.name`.
3. Nếu tên ứng dụng cũng không được đặt, tên mặc định là `application`.

Ví dụ:

| Cấu hình đầu vào | Tên ConfigMap cơ sở được chọn |
| --- | --- |
| `spring.application.name=checkout-service` | `checkout-service` |
| Tên ứng dụng là `checkout-service`, `spring.cloud.kubernetes.config.name=checkout-settings` | `checkout-settings` |
| Không đặt tên ứng dụng, không đặt tên nguồn riêng | `application` |

“Tên cơ sở” là tên trước khi xét các nguồn theo profile nếu tính năng đó được bật. Với nhiều nguồn, cần xét từng phần tử của danh sách nguồn thay vì chỉ áp dụng bảng này cho toàn bộ cấu hình.

Một cách biểu diễn rút gọn:

```text
Nếu có danh sách sources:
    xét từng nguồn được khai báo
Nếu không có danh sách sources:
    config.name
        hoặc spring.application.name
        hoặc "application"
```

Không dựa vào giá trị rỗng để lựa chọn nhánh fallback. Hãy khai báo một tên hợp lệ hoặc bỏ thuộc tính không dùng để ý định rõ ràng.

### Tên phải khớp với metadata.name

Với ứng dụng:

```yaml
spring:
  application:
    name: checkout-service
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        namespace: shop
        include-profile-specific-sources: false
      secrets:
        enabled: false
```

ConfigMap tương ứng là:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-service
  namespace: shop
data:
  checkout.request-timeout: "2s"
  checkout.currency: "VND"
```

Ví dụ tắt nguồn theo profile để minh họa riêng việc chọn một tên cơ sở. Phần Secret được tắt vì bài này chỉ cần ConfigMap.

Ở đây, tên đối tượng cần tìm là `checkout-service`. Các khóa `checkout.request-timeout` và `checkout.currency` là dữ liệu bên trong đối tượng, không phải tên ConfigMap.

Không có quy tắc tự thêm đuôi `-config`, `-settings` hoặc tự chuyển tên Deployment thành tên cấu hình. Nếu muốn đọc `checkout-service-config`, phải khai báo tên đó theo cơ chế lựa chọn nguồn phù hợp.

## 3. Ghi đè tên nguồn mà vẫn giữ nguyên tên ứng dụng

Tên ứng dụng phục vụ nhiều mục đích trong hệ thống. Không nên đổi `spring.application.name` chỉ để khớp một ConfigMap đã có nếu bạn muốn giữ định danh ứng dụng hiện tại.

Ví dụ:

```yaml
spring:
  application:
    name: checkout-service
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        name: checkout-settings
        namespace: shop
        include-profile-specific-sources: false
      secrets:
        enabled: false
```

Và nguồn:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-settings
  namespace: shop
data:
  checkout.request-timeout: "3s"
```

Kết quả:

- Định danh Spring của ứng dụng vẫn là `checkout-service`.
- ConfigMap cơ sở cần đọc là `checkout-settings`.
- Không suy ra rằng ConfigMap `checkout-service` cũng được đọc như một nguồn dự phòng.
- Nếu `checkout-settings` bị thiếu, cách xử lý phụ thuộc chính sách thiếu nguồn; không tự coi đó là yêu cầu tìm ConfigMap khác.

Ghi đè tên nguồn là cách tách quy ước đặt tên ứng dụng khỏi quy ước quản lý cấu hình. Nó cũng giúp việc đổi tên nguồn trở thành một thay đổi rõ ràng trong cấu hình triển khai.

## 4. Tên Deployment, Service và nhãn không tự thay thế tên ứng dụng

Một workload có thể có các tên khác nhau:

```text
Deployment: checkout-backend
Service: checkout-api
Pod: checkout-backend-<replicaset>-<suffix>
Container: app
spring.application.name: checkout-service
ConfigMap được chỉ định: checkout-settings
```

Các tên khác nhau này không tạo mâu thuẫn nếu các tham chiếu được cấu hình đúng.

| Tên hoặc nhãn | Chức năng chính | Có tự làm tên ConfigMap theo quy tắc mặc định không? |
| --- | --- | --- |
| `spring.application.name` | Định danh ứng dụng Spring | Có, khi không ghi đè tên cấu hình và không dùng danh sách nguồn thay thế |
| `Deployment.metadata.name` | Định danh Deployment | Không |
| `Service.metadata.name` | Định danh Service và tham gia địa chỉ dịch vụ | Không |
| Tên Pod | Định danh một Pod | Không |
| Tên container | Định danh container trong Pod | Không |
| Nhãn `app: checkout-service` | Phục vụ chọn và tổ chức đối tượng | Không tự tạo lựa chọn theo tên |
| Tên image | Xác định image chạy | Không |

Spring Cloud Kubernetes có thể hỗ trợ lựa chọn nguồn theo label khi được cấu hình cho cách đó. Đây là một cơ chế lựa chọn khác, không có nghĩa một nhãn `app` bất kỳ sẽ tự được dùng trong cấu hình chọn theo tên.

Tương tự, DiscoveryClient có thể tìm thấy `checkout-api` hoặc một Service đích, nhưng kết quả discovery không tự sửa tên ConfigMap mà Config Data đang tìm.

## 5. Khai báo sources khi cần chỉ định nguồn rõ ràng

Nếu ứng dụng cần nhiều ConfigMap, khai báo danh sách nguồn thay vì cố ghép nhiều tên vào `spring.application.name`.

```yaml
spring:
  application:
    name: checkout-service
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        include-profile-specific-sources: false
        sources:
          - name: platform-shared
            namespace: shop
          - name: checkout-settings
            namespace: shop
      secrets:
        enabled: false
```

Ví dụ thể hiện hai nguồn chủ đích:

```text
ConfigMap/shop/platform-shared
ConfigMap/shop/checkout-settings
```

Trong danh sách này, mỗi `sources[].name` chỉ định tên của nguồn tương ứng. Không tiếp tục lấy `spring.application.name` để thay thế những tên đã được khai báo rõ.

Các nguyên tắc thực hành:

- Khai báo đủ tên và namespace trong các ví dụ triển khai cần tính minh bạch.
- Không để một nguồn trống tên rồi đoán nó sẽ kế thừa từ trường nào; nếu sử dụng giá trị mặc định của từng phần tử, cần kiểm tra hành vi của phiên bản thư viện.
- Không hiểu `config.name` là một ConfigMap luôn được cộng thêm ngoài danh sách `sources`.
- Không giả định ứng dụng tự đọc mọi ConfigMap có cùng tiền tố.
- Phân biệt danh sách nguồn được chọn với quy tắc xử lý khóa trùng sau khi các nguồn được đọc.

### Chọn được nguồn chưa quyết định xong giá trị hiệu lực

Giả sử `platform-shared` và `checkout-settings` cùng chứa `checkout.request-timeout`. Việc biết hai tên nguồn chưa đủ để bỏ qua câu hỏi nguồn nào ghi đè nguồn nào.

Thứ tự xử lý nguồn, nguồn theo profile và các lớp cấu hình khác của Spring Boot đều có thể ảnh hưởng đến giá trị hiệu lực. Với một thuộc tính còn được đặt qua biến môi trường, giá trị từ ConfigMap có thể không phải giá trị cuối cùng.

Trong bài thực hành lựa chọn theo tên, nên cho mỗi nguồn những khóa không trùng:

```text
platform-shared:
    platform.region

checkout-settings:
    checkout.request-timeout
    checkout.currency
```

Nhờ vậy, bạn chứng minh được các nguồn đã được đọc mà chưa phải giải quyết đồng thời bài toán ghi đè. Nếu cần ghi đè có chủ đích, thiết kế và kiểm tra riêng quy tắc đó.

## 6. Namespace là một phần của địa chỉ nguồn

Tên ConfigMap chỉ duy nhất trong phạm vi namespace. Hai đối tượng sau là hai nguồn độc lập:

```text
ConfigMap/shop-dev/checkout-service
ConfigMap/shop-prod/checkout-service
```

Do đó, đầu vào để xác định nguồn không chỉ có tên mà là:

```text
loại đối tượng + namespace + metadata.name
```

Với các nguồn khai báo tường minh, hãy đọc namespace ngay trên từng nguồn. Với nguồn mặc định, xem `spring.cloud.kubernetes.config.namespace` và cơ chế xác định namespace của client khi không cấu hình trực tiếp. Không mặc định rằng namespace luôn là `default`.

Ví dụ, cấu hình:

```yaml
spring:
  application:
    name: checkout-service
  cloud:
    kubernetes:
      config:
        namespace: shop-prod
```

xác định ý định đọc nguồn của production trong namespace `shop-prod`, nếu đường import và các điều kiện cần khác đã được cấu hình. Một ConfigMap cùng tên trong `shop-dev` không thay thế đối tượng còn thiếu ở `shop-prod`.

### Nguồn khác namespace

Với đường API, ứng dụng có thể được thiết kế để đọc một namespace khác nếu cấu hình client và RBAC cho phép. Đây phải là một lựa chọn chủ đích, có đánh giá phạm vi truy cập.

Với volume ConfigMap tham chiếu trực tiếp trong Pod, nguồn được tham chiếu theo namespace của Pod. Không áp dụng khả năng đọc chéo namespace qua API cho tham chiếu volume thông thường.

Không đổi namespace sang nơi có ConfigMap “đang đọc được” chỉ để làm hết lỗi nếu đó là môi trường khác. Trước hết phải xác định đúng nguồn ứng dụng cần sử dụng.

## 7. Profile có thể mở rộng tập tên cần đọc

Tên ứng dụng không phải yếu tố duy nhất khi tính năng nguồn theo profile được bật. Spring Cloud Kubernetes có cơ chế xét ConfigMap có hậu tố theo active profile.

Ví dụ với tên cơ sở `checkout-service` và profile `prod`:

```text
Nguồn cơ sở:       checkout-service
Nguồn theo profile: checkout-service-prod
```

Cấu hình minh họa:

```yaml
spring:
  application:
    name: checkout-service
  profiles:
    active: prod
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        namespace: shop
        include-profile-specific-sources: true
      secrets:
        enabled: false
```

Nếu ghi đè tên cơ sở thành `checkout-settings`, nguồn theo profile được xét dựa trên tên cơ sở đó:

```text
checkout-settings
checkout-settings-prod
```

Đừng tiếp tục suy ra `checkout-service-prod` chỉ vì tên ứng dụng vẫn là `checkout-service`.

Khi nhiều profile cùng hoạt động, tập nguồn có thể mở rộng thêm theo từng profile. Thứ tự ưu tiên giữa các nguồn không nên được suy đoán bằng thứ tự tên trong Kubernetes; cần xét cấu hình nạp và hành vi của phiên bản đang sử dụng.

### Profile không phải namespace

Profile `prod` không tự chuyển namespace từ `shop` sang `shop-prod`. Hai tham số giải quyết hai câu hỏi khác nhau:

| Tham số | Câu hỏi |
| --- | --- |
| Namespace | Đọc đối tượng ở phạm vi Kubernetes nào? |
| Profile | Nạp thêm biến thể cấu hình nào cho ngữ cảnh Spring đang hoạt động? |

Cũng không có phép chuyển đổi mặc định từ label `environment: prod` trên Pod thành active profile Spring. Nếu muốn liên kết hai khái niệm, phải cấu hình tường minh trong quy trình triển khai.

### Khi nào nên tắt nguồn theo profile?

Đặt `include-profile-specific-sources: false` khi bạn muốn tập tên nguồn chỉ gồm các tên đã lựa chọn, chẳng hạn bài thực hành đang dùng các ConfigMap có tên phiên bản rõ ràng và không có biến thể theo profile.

Khi bật lại, cần xem xét thêm:

- Những tên ConfigMap nào có thể được đọc?
- Các đối tượng đó đã tồn tại chưa?
- Quyền truy cập có đáp ứng các thao tác của client không?
- Khi một nguồn theo profile không có, chính sách thiếu nguồn xử lý ra sao?
- Có khóa nào bị ghi đè ngoài ý định không?

Không coi việc thiếu một ConfigMap profile là lý do để tự tìm một tên gần giống khác.

## 8. Cung cấp tên ứng dụng đủ sớm

Bộ nạp cần tên nguồn trước khi có thể lấy nội dung ConfigMap. Vì vậy, thông tin định vị nguồn phải có từ cấu hình khởi động đủ sớm.

Những lựa chọn thông dụng gồm:

- `application.yml` được đóng gói cùng ứng dụng.
- Biến môi trường trong manifest triển khai.
- Tham số dòng lệnh theo quy trình vận hành.
- Một cấu hình cục bộ đã được nạp ở giai đoạn phù hợp.

Ví dụ phần môi trường container:

```yaml
env:
  - name: SPRING_APPLICATION_NAME
    value: checkout-service
  - name: SPRING_CLOUD_KUBERNETES_CONFIG_NAME
    value: checkout-settings
  - name: SPRING_CLOUD_KUBERNETES_CONFIG_NAMESPACE
    value: shop
```

Giả sử các lớp cấu hình khác không ghi đè các giá trị này, nguồn cơ sở là `ConfigMap/shop/checkout-settings`.

Không chỉ đặt `spring.application.name=checkout-service` bên trong ConfigMap `checkout-service` rồi trông chờ bộ nạp biết tìm nó. Trước lần đọc đầu tiên, nội dung đó chưa có để giải quyết bài toán chọn nguồn.

Đặt tên trong một bean `@PostConstruct` hoặc `ApplicationRunner` cũng quá muộn để điều khiển lần nạp Config Data đã xảy ra trong startup.

### Chú ý các lớp ghi đè

Nếu tệp đóng gói đặt tên ứng dụng là `checkout-service` nhưng manifest đặt `SPRING_APPLICATION_NAME=order-worker`, phải xét giá trị hiệu lực tại giai đoạn lựa chọn nguồn.

Trong thứ tự cấu hình thông thường của Spring Boot, biến môi trường có thể ghi đè Config Data. Nếu vẫn có `config.name=checkout-settings` được đặt rõ, việc đổi tên ứng dụng không tự đổi tên ConfigMap cơ sở đó.

Khi chẩn đoán, xem cả ba giá trị hiệu lực:

```text
spring.application.name
spring.cloud.kubernetes.config.name
spring.cloud.kubernetes.config.sources
```

Sau đó xét namespace và profile, thay vì chỉ nhìn một tệp cấu hình trong repository.

## 9. Tên khóa bên trong không quyết định tên đối tượng

Một ConfigMap có hai lớp thông tin cần phân biệt:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-settings
  namespace: shop
data:
  application.yaml: |
    checkout:
      request-timeout: 2s
```

Ở đây:

- `metadata.name=checkout-settings` là tên đối tượng để lựa chọn nguồn.
- `application.yaml` là một khóa dữ liệu có nội dung cấu hình.
- `checkout.request-timeout` là thuộc tính được biểu diễn trong tài liệu YAML.

Sự xuất hiện của khóa `application.yaml` không làm đối tượng đổi tên thành `application`. Bộ nạp phải chọn đúng ConfigMap trước, rồi mới xử lý dữ liệu của nó theo quy tắc được hỗ trợ.

Tương tự, đổi một khóa từ `checkout.request-timeout` sang `order.request-timeout` không chuyển lựa chọn nguồn từ `checkout-settings` sang một ConfigMap tên `order`.

Khi một thuộc tính không có trong Environment, cần tách hai câu hỏi:

1. Đã đọc đúng đối tượng ConfigMap chưa?
2. Nội dung của đối tượng đó có đúng cấu trúc và tên thuộc tính mà ứng dụng cần không?

Không sửa tên nguồn liên tục để xử lý một lỗi thực chất nằm ở nội dung hoặc binding.

## 10. Quy tắc chọn tên phải đi cùng RBAC

Chọn đúng `ConfigMap/shop/checkout-settings` chưa bảo đảm ứng dụng đọc được nguồn. ServiceAccount mà client sử dụng phải được cấp quyền cho các thao tác thực tế.

Phân biệt các trường hợp:

| Tình huống | Bản chất | Việc nên kiểm tra |
| --- | --- | --- |
| ConfigMap không tồn tại ở tên/namespace cần tìm | Không có nguồn tại địa chỉ đã chọn | Manifest tạo nguồn và cấu hình định vị |
| Client bị từ chối quyền | Danh tính không được phép thực hiện thao tác | ServiceAccount, Role, RoleBinding, phạm vi namespace |
| Không kết nối được Kubernetes API | Không truy cập được đường đọc nguồn | Cấu hình client, chứng thư, mạng |
| Đọc nguồn thành công nhưng thiếu khóa | Nguồn tồn tại, dữ liệu không đáp ứng ứng dụng | Tên khóa, cách lưu tài liệu, binding và validation |

Không cấp quyền đọc mọi Secret để giải quyết lỗi đọc ConfigMap. ConfigMap và Secret là các tài nguyên khác nhau, có mức độ nhạy cảm khác nhau.

Khi tập nguồn đã rõ, có thể thiết kế phạm vi truy cập hẹp hơn. Tuy nhiên, biết tên đối tượng không đồng nghĩa thư viện chắc chắn chỉ gọi API `get`. Client hoặc chế độ theo dõi có thể cần `list` hoặc `watch`.

Nếu dùng RBAC giới hạn theo `resourceNames`, cần đối chiếu với thao tác và điều kiện của lời gọi thực tế. Không giả định một quy tắc giới hạn tên tự lọc được mọi lời gọi liệt kê.

Khi bật nguồn theo profile, cần đánh giá thêm các tên biến thể trong chính sách quyền. Khi thêm Configuration Watcher, xem riêng danh tính và quyền của thành phần theo dõi thay vì mặc định cấp toàn bộ quyền đó cho ứng dụng.

## 11. Thiếu nguồn không có nghĩa tự tìm tên dự phòng khác

Các quy tắc fallback tên dùng để **xác định tên khi chưa khai báo đầu vào**, không phải danh sách thử lần lượt mọi đối tượng đang tồn tại.

Ví dụ:

```text
spring.application.name = checkout-service
config.name = checkout-settings
```

Nếu `checkout-settings` không tồn tại, không nên kỳ vọng bộ nạp sẽ tự chuyển sang `checkout-service`, rồi sang `application`.

Tương tự, nếu `spring.application.name` đã được đặt, sự tồn tại của một ConfigMap `application` không tự làm nó trở thành nguồn chung luôn được nạp. Muốn dùng nguồn chung, khai báo chủ đích trong `sources` hoặc cơ chế cấu hình thích hợp.

Hành vi khi thiếu nguồn có thể là bỏ qua, cảnh báo, thử lại hoặc làm startup thất bại tùy tùy chọn và phiên bản. Dù chọn chính sách nào, ứng dụng vẫn cần kiểm tra các thuộc tính bắt buộc.

Không đánh giá việc chọn nguồn chỉ bằng “Pod không crash”. Pod có thể đang chạy bằng giá trị mặc định, biến môi trường hoặc một nguồn khác. Cần có bằng chứng về dữ liệu hiệu lực.

## 12. Đổi tên nguồn là thay đổi cấu hình khởi động

Giả sử phiên bản đầu dùng `checkout-settings-v1` và phiên bản mới cần `checkout-settings-v2`.

Tạo ConfigMap `checkout-settings-v2` không tự chuyển ứng dụng đang chạy sang nguồn mới. Ứng dụng vẫn đang có cấu hình và đồ thị bean được tạo từ lần nạp trước, trừ khi bạn đã thiết kế một cơ chế cập nhật thực sự hỗ trợ việc đổi tập nguồn.

Một quy trình dễ kiểm soát là:

1. Tạo nguồn mới với tên và namespace dự định dùng.
2. Kiểm tra nội dung và quyền truy cập cần thiết.
3. Cập nhật tên nguồn trong cấu hình khởi động hoặc Pod template.
4. Rollout để instance mới nạp nguồn mới.
5. Theo dõi startup và readiness trước khi cho nhận đủ lưu lượng.
6. Chỉ dọn nguồn cũ khi không còn workload cần nó.

Configuration Watcher không phải cơ chế suy đoán rằng một ConfigMap mới có tiền tố giống nguồn cũ thì phải thay thế nguồn cũ. Việc theo dõi thay đổi và việc chọn tập nguồn là hai trách nhiệm khác nhau.

Nếu đổi `spring.application.name` thay vì chỉ đổi `config.name`, cần xem xét cả những thành phần khác đang sử dụng định danh ứng dụng. Việc đổi thuộc tính Spring cũng không tự đổi `metadata.name` của Kubernetes Service hoặc Deployment.

## 13. Bài thực hành: dự đoán nguồn trước khi chạy

Trong namespace học tập `shop`, chuẩn bị các ConfigMap chỉ chứa dữ liệu không bí mật:

| Tên ConfigMap | Thuộc tính đánh dấu |
| --- | --- |
| `application` | `training.config-origin=fallback-source` |
| `checkout-service` | `training.config-origin=application-name-source` |
| `checkout-settings` | `training.config-origin=explicit-name-source` |

Trong các lần thử đầu, tắt nguồn theo profile và không khai báo `sources`. Không đặt `training.config-origin` qua biến môi trường hoặc nguồn ghi đè khác.

Mỗi lần thay cấu hình định vị, tạo một lần startup mới để quan sát rõ ràng.

| Lần thử | Tên ứng dụng | Tên nguồn riêng | Nguồn cơ sở dự kiến |
| --- | --- | --- | --- |
| 1 | `checkout-service` | Không đặt | `checkout-service` |
| 2 | `checkout-service` | `checkout-settings` | `checkout-settings` |
| 3 | Không đặt | Không đặt | `application` |
| 4 | `checkout-service` | `missing-settings` | `missing-settings`, không tự chuyển sang đối tượng khác |

Với lần 3, cần bỏ tên ứng dụng ở mọi lớp cấu hình hiệu lực, bao gồm biến môi trường và tham số dòng lệnh. Chỉ xóa một dòng trong tệp đóng gói chưa đủ nếu manifest vẫn đặt giá trị.

Với lần 4, không đoán trước mọi ứng dụng đều dừng theo cùng cách. Quan sát chính sách thiếu nguồn và validation của ứng dụng; điều cần chứng minh là không tự xuất hiện giá trị đánh dấu từ một tên dự phòng khác.

### Mở rộng sang sources và profile

Sau khi xác nhận lựa chọn một nguồn:

- Khai báo hai nguồn `platform-shared` và `checkout-settings` với các khóa đánh dấu khác nhau, chẳng hạn `training.shared-origin` và `training.app-origin`.
- Xác nhận cả hai khóa có mặt mà không bị một nguồn ghi đè mất bằng chứng.
- Tạo `checkout-settings-prod`, bật profile `prod` và nguồn theo profile.
- Kiểm tra tên cơ sở và biến thể đã được xét đúng, đồng thời xem chính sách quyền cho các thao tác phát sinh.
- Đổi namespace sang một namespace học tập khác để chứng minh rằng cùng tên không có nghĩa cùng đối tượng.

Khi ghi nhận kết quả, chỉ log các khóa đánh dấu không bí mật. Không xuất toàn bộ Environment vì ứng dụng có thể đồng thời chứa Secret từ những nguồn khác.

## 14. Quy trình chẩn đoán khi đọc nhầm hoặc không đọc được ConfigMap

Thực hiện theo thứ tự để tránh đổi nhiều yếu tố cùng lúc:

1. **Xác nhận đường nạp:** API Config Data, volume hay biến môi trường?
2. **Xác nhận cơ chế đã được bật:** starter phù hợp, import và chức năng ConfigMap.
3. **Xem danh sách nguồn:** nếu có `sources`, đọc từng tên và namespace tường minh.
4. **Nếu không có danh sách nguồn:** xét `config.name`, rồi `spring.application.name`, rồi mặc định `application`.
5. **Xét profile:** có biến thể nào được thêm vào tập tên không?
6. **Chốt địa chỉ nguồn:** loại đối tượng, namespace, tên.
7. **Kiểm tra quyền và đường truy cập:** dùng đúng danh tính của client.
8. **Kiểm tra nội dung sau khi chọn nguồn:** khóa có tồn tại và được diễn giải đúng không?
9. **Kiểm tra giá trị hiệu lực:** có lớp cấu hình khác đang ghi đè không?
10. **Kiểm tra vòng đời cập nhật:** instance đang chạy đã thực sự nạp lại hoặc được rollout chưa?

Nếu nguồn đã đọc thành công nhưng readiness vẫn thất bại, tiếp tục kiểm tra binding, ràng buộc giá trị và tài nguyên phụ thuộc. Không kết luận mọi lỗi sức khỏe Pod đều do tên ConfigMap.

Quy tắc lựa chọn theo tên giúp tạo một hợp đồng rõ ràng giữa ứng dụng và triển khai: ứng dụng cần những đối tượng nào, ở namespace nào và từ thời điểm nào. Khi hợp đồng đó được khai báo đủ sớm và có thể kiểm tra, bạn chỉ cần bật những tính năng Spring Cloud Kubernetes thực sự phục vụ nhu cầu đọc cấu hình, discovery, cân bằng tải hoặc theo dõi thay đổi của mình.
