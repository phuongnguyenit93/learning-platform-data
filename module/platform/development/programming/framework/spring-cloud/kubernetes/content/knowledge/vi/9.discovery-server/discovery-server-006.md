# Định dạng và ý nghĩa dữ liệu khám phá được trả về

## 1. Dữ liệu Discovery Server giúp trả lời câu hỏi nào?

Trong chương **Discovery Server** của module **SPRING_CLOUD_KUBERNETES**, đối tượng cần hiểu là dữ liệu mô tả dịch vụ và các instance mà một ứng dụng có thể tìm thấy qua HTTP. Đọc đúng dữ liệu này giúp ứng dụng chọn đích gọi, đối chiếu namespace và cổng, đồng thời phát hiện thông tin đã cũ hoặc không đủ điều kiện sử dụng.

Discovery Server đứng giữa Kubernetes API và ứng dụng dùng HTTP discovery:

```text
Service, Pod, Endpoints hoặc EndpointSlice
                    |
           Kubernetes API + RBAC
                    |
              Discovery Server
                    |
         HTTP + dữ liệu JSON khám phá
                    |
      HTTP DiscoveryClient / công cụ chẩn đoán
                    |
       danh sách ServiceInstance cho ứng dụng
```

Đường truyền dữ liệu khám phá và đường gọi nghiệp vụ là hai kết nối khác nhau. Nhận JSON từ Discovery Server thành công chỉ chứng minh ứng dụng đọc được danh mục ở thời điểm đó; chưa chứng minh ứng dụng kết nối được đến các địa chỉ backend trong JSON.

Bài này tập trung vào cấu trúc phản hồi, ý nghĩa trường, cách đọc và cách kiểm tra dữ liệu. ConfigMap, Secret và Configuration Watcher thuộc luồng cấu hình; chúng không tự trở thành nội dung nghiệp vụ của phản hồi discovery. Spring Cloud LoadBalancer có thể dùng danh sách instance để chọn đích, nhưng bản thân JSON không chứa một chính sách cân bằng tải hoàn chỉnh.

Các địa chỉ, UUID, tên dịch vụ và phản hồi trong bài là dữ liệu minh họa. Không có kết quả nào được trình bày như một lần gọi cụm Kubernetes đã thực hiện.

## 2. Ba cấp truy vấn và hình dạng JSON

### 2.1. Chốt phiên bản trước khi chốt đường dẫn

Hai truy vấn cơ bản là:

| Request | Dữ liệu nhận được | Kiểu ở gốc JSON |
| --- | --- | --- |
| `GET /apps` | Danh mục các dịch vụ, mỗi dịch vụ có danh sách instance | Mảng các object dịch vụ |
| `GET /apps/orders` | Các instance của dịch vụ `orders` | Mảng các object instance |
| `GET /apps/orders/{instanceId}` | Một instance cụ thể trong phiên bản 5.1.0 | Object instance khi tìm thấy |

Mã nguồn controller ở tag **v5.1.0** khai báo đường lấy một instance bằng `/apps/{name}/{instanceId}`. Tag **v3.3.3** có cả đường đó và `/app/{name}/{instanceId}`, trong đó đường số ít đã bị đánh dấu deprecated. Vì ví dụ trong trang hướng dẫn có thể vẫn ghi `/app/...`, hãy dùng hợp đồng của đúng image server đang triển khai. [Controller v5.1.0](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v5.1.0/spring-cloud-kubernetes-controllers/spring-cloud-kubernetes-discoveryserver/src/main/java/org/springframework/cloud/kubernetes/discoveryserver/DiscoveryServerController.java), [controller v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-controllers/spring-cloud-kubernetes-discoveryserver/src/main/java/org/springframework/cloud/kubernetes/discoveryserver/DiscoveryServerController.java).

Phần thực hành bên dưới dùng đường `/apps/...` của 5.1.0 làm mốc đọc hợp đồng, không yêu cầu nâng phiên bản dự án. Khi áp dụng, ghi lại image tag hoặc digest và giữ server/client trong bộ phiên bản tương thích của dự án.

### 2.2. Phản hồi danh mục `/apps`

Giả sử server quan sát namespace `shop`, Service `orders` có hai endpoint HTTP đã được chọn. Một phản hồi minh họa:

```json
[
  {
    "name": "orders",
    "serviceInstances": [
      {
        "instanceId": "7aa13dc1-78f1-4cf6-90cd-6a63c9bc0001",
        "serviceId": "orders",
        "host": "10.42.1.15",
        "port": 8080,
        "uri": "http://10.42.1.15:8080",
        "secure": false,
        "metadata": {
          "label.app": "orders",
          "annotation.owner": "checkout-team",
          "port.http": "8080",
          "k8s_namespace": "shop",
          "type": "ClusterIP"
        },
        "namespace": "shop",
        "cluster": null,
        "podMetadata": {},
        "scheme": "http"
      },
      {
        "instanceId": "7aa13dc1-78f1-4cf6-90cd-6a63c9bc0002",
        "serviceId": "orders",
        "host": "10.42.2.21",
        "port": 8080,
        "uri": "http://10.42.2.21:8080",
        "secure": false,
        "metadata": {
          "label.app": "orders",
          "annotation.owner": "checkout-team",
          "port.http": "8080",
          "k8s_namespace": "shop",
          "type": "ClusterIP"
        },
        "namespace": "shop",
        "cluster": null,
        "podMetadata": {},
        "scheme": "http"
      }
    ]
  }
]
```

Ví dụ đã chọn prefix metadata để dễ nhận diện nguồn; không phải cam kết rằng mọi server mặc định trả về đúng các khóa đó. Tùy phiên bản và cấu hình serialization, một số trường tùy chọn có thể rỗng, `null` hoặc không xuất hiện.

Ở lớp ngoài:

- `name` là tên dịch vụ được khám phá, ở đây là `orders`.
- `serviceInstances` là một danh sách. Một Service không đồng nghĩa với chỉ một instance.
- Thông tin namespace nằm ở instance; object bọc trong ví dụ không có trường namespace riêng.

Mô hình bọc của Spring là một tên và một danh sách instance. Không nhầm nó với `ServiceList` của Kubernetes có `apiVersion`, `kind`, `items`. [Mô hình Service của Discovery Server](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v5.1.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/discovery/Service.java).

### 2.3. Danh sách instance và một instance

`GET /apps/orders` trả trực tiếp mảng instance, không bọc thêm `name` và `serviceInstances`:

```text
/apps                  -> [ { name, serviceInstances: [instance, ...] }, ... ]
/apps/orders           -> [ instance, instance, ... ]
/apps/orders/<id>      -> instance, nếu tìm được theo hợp đồng server
```

Vì vậy một parser của `/apps` không thể được dùng nguyên xi cho `/apps/orders`. Đối với truy vấn một instance, cần xử lý trường hợp không có kết quả theo HTTP status và body thực tế của phiên bản triển khai; không tự giả định server luôn trả `404`, `null` hay `[]`.

Trước khi giải mã JSON, kiểm tra request thành công, Content-Type phù hợp và body không phải trang HTML từ proxy. Một object lỗi có các trường như `status`, `error`, `path` không phải object instance chỉ vì nó cũng là JSON.

## 3. Từ điển các trường instance

Các trường nền tảng của một instance thường được đọc như sau:

| Trường | Kiểu JSON thông thường | Cách sử dụng |
| --- | --- | --- |
| `instanceId` | Chuỗi | Định danh instance trong dữ liệu khám phá; coi là giá trị opaque |
| `serviceId` | Chuỗi | Tên dịch vụ logic dùng trong truy vấn discovery |
| `host` | Chuỗi | Địa chỉ backend hoặc tên được khám phá; kiểm tra khả năng truy cập |
| `port` | Số nguyên | Cổng được chọn cho instance |
| `uri` | Chuỗi URI | Biểu diễn đích kết nối do server tạo |
| `secure` | Boolean | Chỉ dấu sử dụng kết nối secure theo quy tắc discovery |
| `scheme` | Chuỗi | Scheme, thông thường `http` hoặc `https` |

Các trường này thuộc biểu diễn ServiceInstance; không có trường nào trong nhóm trên tự chứng minh request nghiệp vụ sẽ thành công. [Mô tả dữ liệu DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Các thông tin mở rộng trong mô hình Kubernetes:

| Trường | Kiểu JSON thông thường | Cách đọc |
| --- | --- | --- |
| `metadata` | Object có giá trị chuỗi | Thuộc tính bổ sung; khóa phụ thuộc cấu hình |
| `namespace` | Chuỗi hoặc giá trị chưa có | Namespace của instance, không phải namespace của máy gọi |
| `cluster` | Chuỗi hoặc `null` | Thông tin cluster khi được cung cấp |
| `podMetadata` | Object lồng các map chuỗi | Metadata Pod khi tính năng tương ứng được bật và có dữ liệu |

Mô hình có thể có các trường mở rộng này nhưng không bảo đảm chúng luôn chứa dữ liệu. Client nên phân biệt “trường được hỗ trợ” với “giá trị có mặt trong phản hồi cụ thể”. [Mô hình DefaultKubernetesServiceInstance](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v5.1.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/discovery/DefaultKubernetesServiceInstance.java).

### 3.1. `serviceId` và `instanceId` có vòng đời khác nhau

Giả sử `orders` được rollout:

```text
Trước: serviceId=orders, instanceId=A, host=10.42.1.15
Sau:   serviceId=orders, instanceId=B, host=10.42.3.44
```

Tên dịch vụ có thể giữ nguyên, còn backend và định danh thay đổi. Không lưu `instanceId` vào cơ sở dữ liệu như mã nghiệp vụ của đơn hàng, không phân tích UUID để suy ra namespace và không coi ID là một địa chỉ để kết nối.

Cũng không khẳng định `instanceId` luôn bằng Pod name hoặc Pod UID cho mọi client và mọi kiểu Service. Khi cần đối chiếu Pod, dùng thêm trạng thái Kubernetes và địa chỉ endpoint.

### 3.2. `host` không phải luôn là ClusterIP

Trong luồng khám phá endpoint của Service có selector, `host` có thể là IP backend. Không thay nó bằng ClusterIP chỉ vì `metadata.type` có giá trị `ClusterIP`: trường type mô tả loại Service, không phải kiểu của mọi địa chỉ instance.

Với kiểu ExternalName được hỗ trợ và bật trong discovery, địa chỉ có thể là tên bên ngoài. Do đó parser không nên bắt buộc `host` luôn khớp biểu thức IPv4. Cần xác định ca sử dụng nào cho phép DNS, IPv6 hoặc địa chỉ ngoài cụm.

## 4. Đọc cổng và giao thức như một hợp đồng kết nối

### 4.1. Cổng instance và cổng Service có thể khác nhau

Xét phần manifest của Service `orders`:

```yaml
spec:
  selector:
    app: orders
  ports:
    - name: http
      port: 80
      targetPort: 8080
```

Trong đường gọi qua Service, ứng dụng dùng tên Service với cổng 80. Trong đường gọi trực tiếp backend, cặp đích có thể là Pod IP với 8080. Kubernetes cho phép ánh xạ `port` sang `targetPort` như vậy. [Cổng của Kubernetes Service](https://kubernetes.io/docs/concepts/services-networking/service/).

Vì thế JSON sau có thể hoàn toàn phù hợp với manifest trên:

```json
{
  "host": "10.42.1.15",
  "port": 8080,
  "uri": "http://10.42.1.15:8080",
  "secure": false,
  "scheme": "http"
}
```

Đây là **trích riêng nhóm trường kết nối**, không phải phản hồi instance đầy đủ. Khi đọc kết quả, luôn giữ cặp `host` và `port` cùng nhau; không lấy Pod IP từ JSON rồi ghép với cổng Service 80 theo suy đoán.

Service nhiều cổng cũng không có nghĩa mỗi instance sẽ tự trở thành một danh sách socket. Trường `port` biểu diễn cổng được chọn. Metadata có thể mô tả thêm các cổng khác, nhưng đó không phải chỉ thị tự động gửi request nghiệp vụ đến mọi cổng tìm thấy.

Nếu manifest có cổng `http` và `management`, cần biết server chọn cổng nào. Một request đến management có thể trả health 200 dù đường API nghiệp vụ không tồn tại ở đó. Kiểm tra thêm đường dẫn và phản hồi ứng dụng.

### 4.2. `secure`, `scheme` và `uri` phải được đọc cùng nhau

Với một backend HTTP thông thường:

```text
secure=false, scheme=http, uri=http://10.42.1.15:8080
```

Với một backend HTTPS thông thường:

```text
secure=true, scheme=https, uri=https://orders.internal.example:8443
```

`secure: true` là thông tin dùng để hình thành kết nối; nó không chứng nhận rằng TLS handshake đã thành công, certificate còn hạn hoặc tên trên certificate khớp đích gọi. Nếu gọi Pod IP trong khi chứng thư chỉ cấp cho tên DNS, JSON hợp lệ vẫn có thể dẫn tới lỗi xác minh tên.

Khi kiểm tra một instance HTTP/HTTPS có cổng dương, có thể yêu cầu URI nhất quán với trường host, port và scheme. Nếu dữ liệu mâu thuẫn, ghi nhận lỗi hợp đồng, thay vì âm thầm chọn một trường để “sửa” thông tin còn lại.

Không áp dụng bất biến này máy móc cho mọi giá trị đặc biệt: mô hình 5.1.0 xử lý riêng trường hợp không có cổng và ExternalName. Một consumer chỉ hỗ trợ backend HTTP có cổng xác định có thể từ chối `port <= 0` theo chính sách của mình; đó là giới hạn consumer, không phải khẳng định mọi phản hồi như vậy đều sai giao thức. [Cách mô hình tạo URI](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v5.1.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/discovery/DefaultKubernetesServiceInstance.java).

### 4.3. Phân tích URI bằng thư viện

Không dùng phép tách chuỗi theo dấu `:` để đọc đích. URI IPv6 hợp lệ cần dấu ngoặc vuông quanh địa chỉ khi biểu diễn cùng cổng, ví dụ:

```text
http://[fd00:42::15]:8080
```

Parser nên dùng kiểu URI/URL, kiểm tra scheme được phép và xử lý lỗi có thông tin. Nếu server ở phiên bản đang dùng tạo URI IPv6 không hợp lệ, báo lỗi tương thích; không nối chuỗi mới một cách tùy tiện rồi bỏ qua hợp đồng.

Base URI của instance cũng không mặc định chứa `/api/orders`, `/actuator/health` hoặc đường dẫn Ingress. Đường dẫn nghiệp vụ do consumer xây dựng theo API của dịch vụ. Tiền tố URL được thêm ở gateway không tự xuất hiện trên backend trực tiếp.

## 5. Metadata: object JSON nhưng giá trị thường là chuỗi

### 5.1. Kiểu dữ liệu có ý nghĩa

Trong một instance:

```json
{
  "port": 8080,
  "secure": false,
  "metadata": {
    "port.http": "8080",
    "annotation.feature-enabled": "false"
  }
}
```

- `port` ngoài cùng là số.
- `secure` ngoài cùng là Boolean.
- `metadata["port.http"]` là chuỗi `"8080"`.
- `metadata["annotation.feature-enabled"]` là chuỗi `"false"`, không phải Boolean JSON.

Nếu consumer cần dùng metadata làm số hoặc Boolean, phải chuyển kiểu và xác thực rõ ràng. Không ép kiểu theo “có chuỗi nghĩa là true”; cách đó sẽ biến chuỗi `"false"` thành một quyết định sai trong nhiều ngôn ngữ.

Object metadata cũng không phải một bản sao nguyên vẹn `metadata` của tài nguyên Kubernetes. Nó là tập dữ liệu mà discovery quyết định xuất ra, có thể chứa các giá trị đã thêm prefix và các khóa phục vụ framework.

### 5.2. Prefix giúp phân biệt nguồn khóa

Có thể cấu hình trên **Discovery Server** để cách đặt tên metadata rõ ràng hơn:

```yaml
spring:
  cloud:
    kubernetes:
      discovery:
        metadata:
          add-labels: true
          labels-prefix: "label."
          add-annotations: true
          annotations-prefix: "annotation."
          add-ports: true
          ports-prefix: "port."
          add-pod-labels: false
          add-pod-annotations: false
```

Đây là cách đặt cấu hình trong ứng dụng server; nếu triển khai bằng image có sẵn, truyền các thuộc tính qua cơ chế cấu hình mà image hỗ trợ. Không giả định cấu hình ở ứng dụng HTTP client sẽ tự sửa những gì server đã xuất ra.

Với quy ước trên, label `app: orders` trở thành khóa `label.app`, còn annotation `owner: checkout-team` trở thành `annotation.owner`. Các thuộc tính bật/tắt và prefix có trong danh mục cấu hình Spring Cloud Kubernetes; mặc định `ports-prefix` được tài liệu hiện hành ghi là `port.`. [Các thuộc tính metadata](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

Khi đọc một ví dụ cũ có khóa `http` thay vì `port.http`, không kết luận ngay có lỗi JSON. So sánh phiên bản và cấu hình prefix. Đồng thời, nếu không có prefix cho labels và annotations, các khóa cùng tên có thể gây nhập nhằng nguồn; consumer không nên gán ý nghĩa nghiệp vụ cho khóa chưa có quy ước rõ ràng.

### 5.3. Metadata Service và metadata Pod khác nhau

Label gắn trên Service có thể nói dịch vụ thuộc nhóm `checkout`; label của Pod có thể nói instance chạy revision `v2`. Hai dữ liệu đó có mức chi tiết khác nhau.

`metadata` thường phục vụ các thuộc tính của Service và thông tin discovery bổ sung. `podMetadata`, khi được bật và thu thập, là cấu trúc lồng thay vì một chuỗi JSON phẳng. Không coi hai object này là hai cách viết tương đương của cùng một tập labels.

Khi thấy:

```json
{
  "metadata": {"label.app": "orders"},
  "podMetadata": {}
}
```

chỉ có thể kết luận phản hồi không mang dữ liệu Pod trong object đó. Không thể suy ra Pod thực tế không có label. Việc thu thập có thể chưa bật hoặc chưa có dữ liệu khả dụng.

### 5.4. Annotation chứa JSON vẫn là một chuỗi

Một annotation có thể chứa dữ liệu cấu trúc được escape:

```json
{
  "metadata": {
    "annotation.example.com/hint": "{\"team\":\"checkout\",\"tier\":2}"
  }
}
```

Ở đây `metadata["annotation.example.com/hint"]` vẫn có kiểu chuỗi sau lần parse JSON đầu tiên. Chỉ parse lần thứ hai nếu consumer có hợp đồng riêng cho khóa đó. Không tự động coi mọi chuỗi bắt đầu bằng `{` là object, và không thực thi nội dung annotation như biểu thức hoặc mã lệnh.

Metadata có thể làm lộ tên nội bộ, topology hoặc annotation dài. Chỉ ghi log các khóa được chọn, hạn chế quyền đọc API discovery theo nhu cầu. Việc Secret không thuộc payload chuẩn không bảo đảm annotation của tổ chức chưa vô tình chứa thông tin nhạy cảm.

## 6. Namespace và định danh khi có nhiều môi trường

Tên `orders` có thể tồn tại đồng thời trong namespace `shop-dev` và `shop-prod`. Khi phạm vi server gồm nhiều namespace, chỉ nhìn `serviceId` không đủ để biết instance thuộc môi trường nào.

Một nhóm dịch vụ theo tên có thể chứa các instance cùng tên nhưng khác namespace. Khi kiểm tra dữ liệu, luôn xem namespace ở từng instance và đối chiếu phạm vi discovery đã cấu hình. Không tự đổi truy vấn thành `/apps/orders.shop-prod` hoặc thêm tham số `?namespace=...` nếu API của phiên bản đó không quy định cách lọc này.

Với HTTP discovery, phạm vi namespace cần đặt phía server. Tài liệu cũng lưu ý danh sách tên dịch vụ được loại trùng theo tên dù có cùng tên ở nhiều namespace. [Phạm vi namespace và tên dịch vụ](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Trong màn hình giám sát hoặc log, một khóa do **consumer tự định nghĩa** có thể là:

```text
nguồn-server + cluster-đã-xác-định + namespace + serviceId + instanceId
```

Đây là khóa phục vụ đối chiếu của hệ thống bạn, không phải một trường được API chuẩn cam kết trả về. Nếu `cluster` là `null`, giữ lại nguồn Discovery Server hoặc định danh cụm từ cấu hình tin cậy; không biến `null` thành tên cụm thật và không dùng trường chưa có dữ liệu để gộp các môi trường.

Nếu có cả `namespace` và `metadata.k8s_namespace`, kiểm tra chúng nhất quán theo hợp đồng đã chọn. Một consumer hỗ trợ phiên bản chỉ có khóa metadata có thể dùng fallback được ghi rõ; khi cả hai có mặt nhưng mâu thuẫn, nên báo lỗi thay vì âm thầm chọn dữ liệu thuận tiện hơn.

## 7. Phản hồi là ảnh chụp quan sát, không phải cam kết sức khỏe

Giả sử các sự kiện xảy ra liên tiếp:

```text
T0: một Pod rời trạng thái Ready
T1: nguồn endpoint được cập nhật
T2: Discovery Server nhận thay đổi
T3: consumer nhận phản hồi mới
T4: consumer gửi request nghiệp vụ
```

Giữa các mốc có độ trễ. Một instance xuất hiện ở T3 vẫn có thể mất kết nối ở T4. Vì vậy cần timeout cho request, cơ chế xử lý thất bại phù hợp và giới hạn thời gian giữ cache; không cache danh sách IP vĩnh viễn.

Đồng thời, phản hồi discovery thông thường không có các trường sau theo hợp đồng ví dụ của bài:

- Trạng thái `UP`/`DOWN` đã đo bằng request nghiệp vụ tại lúc consumer sử dụng.
- `observedAt`, TTL hoặc Kubernetes `resourceVersion` cho toàn bộ kết quả.
- Cam kết giao dịch nguyên tử rằng tất cả dịch vụ trong `/apps` cùng đến từ một thời điểm.
- Token truy cập backend hoặc xác nhận ứng dụng đã nạp ConfigMap/Secret revision nào.

Nếu consumer cần timestamp, nó có thể tự gắn `receivedAt` khi nhận phản hồi. Giá trị đó có nghĩa “thời điểm nhận ở client”, không được đổi tên thành “thời điểm Pod được kiểm tra khỏe”.

Điều kiện readiness của endpoint là dữ liệu nguồn quan trọng, nhưng payload instance không nhất thiết xuất mọi condition của Kubernetes. Muốn điều tra terminating hoặc not-ready, đọc nguồn endpoint tương ứng. EndpointSlice có các condition như `ready`, `serving`, `terminating`; không suy diễn chúng chỉ từ việc JSON có một địa chỉ. [Điều kiện endpoint trong Kubernetes](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).

## 8. Rỗng, thiếu trường và lỗi là những trạng thái khác nhau

| Dữ liệu hoặc hiện tượng | Cách hiểu ban đầu | Điều cần kiểm tra tiếp |
| --- | --- | --- |
| `/apps` trả `[]` | Danh mục đang đọc không có mục nào | Phạm vi server, bộ lọc, nguồn dữ liệu và log |
| Một mục có `serviceInstances: []` | Tên dịch vụ có trong danh mục nhưng chưa có instance được trả về | Selector, endpoint, readiness và quá trình hội tụ |
| `/apps/orders` trả `[]` | Không có instance được truy vấn trả về lúc đó | Chưa đủ kết luận Service đã bị xóa |
| `metadata: {}` | Map hiện tại không có thuộc tính | Có thể do cấu hình xuất metadata |
| Một khóa metadata không tồn tại | Không có dữ liệu cho khóa đó | Áp dụng quy tắc thiếu khóa đã định nghĩa |
| `cluster: null` | Không có giá trị cluster ở trường đó | Dùng nguồn định danh tin cậy khác nếu cần |
| Body HTTP rỗng | Chưa có JSON để parse | Status, loại truy vấn và hành vi phiên bản |
| HTTP 401/403 | Quyền gọi HTTP API bị từ chối ở một lớp | Auth của server, ingress hoặc proxy |
| HTTP 5xx, timeout, body không hợp lệ | Lỗi lấy dữ liệu hoặc lỗi dịch vụ trung gian | Không chuyển thành danh sách rỗng im lặng |

Một chính sách vận hành có thể cho phép dùng cache cũ trong thời gian ngắn khi discovery lỗi. Khi đó phải đánh dấu nguồn dữ liệu đang cũ, giới hạn tuổi cache và ghi nhận lỗi gốc. Không biến lỗi parse thành “không có dịch vụ” rồi báo hệ thống bình thường.

Tương tự, lỗi HTTP 403 mà consumer nhận từ endpoint discovery không tự chứng minh ServiceAccount của server thiếu quyền Kubernetes. Đây là hai chặng phân quyền khác nhau. Muốn kết luận server thiếu RBAC, cần log hoặc bằng chứng lỗi gọi Kubernetes API ở phía server.

## 9. Đọc phản hồi thực tế bằng PowerShell

### 9.1. Chuẩn bị một đường truy cập chẩn đoán

Giả sử cụm đã có Service tên `spring-cloud-kubernetes-discoveryserver` trong namespace `discovery-system`, công bố cổng 80. Giữ lệnh sau trong một terminal:

```powershell
kubectl port-forward service/spring-cloud-kubernetes-discoveryserver -n discovery-system 18761:80
```

Tên, namespace và cổng trong lệnh là giả định của ví dụ; thay bằng tài nguyên được triển khai thực tế. Port-forward giúp lấy phản hồi trên máy phát triển nhưng không làm cho địa chỉ Pod trong JSON trở nên truy cập được từ máy đó.

Ở terminal khác:

```powershell
$discoveryBase = 'http://127.0.0.1:18761'
curl.exe --silent --show-error --fail-with-body --max-time 10 -H 'Accept: application/json' "$discoveryBase/apps"
```

Dùng `curl.exe` để tránh nhầm với alias của PowerShell cũ. Cờ `--fail-with-body` cần bản curl hỗ trợ; có thể dùng `Invoke-WebRequest` như bước sau nếu môi trường không có cờ này. Không đưa credential vào lệnh mẫu hoặc lịch sử shell; nếu API có xác thực, dùng cơ chế quản lý credential của môi trường thực hành.

### 9.2. Kiểm tra hình dạng trước khi duyệt

Ví dụ đọc `/apps` và liệt kê các instance của `orders`:

```powershell
$response = Invoke-WebRequest `
    -Uri "$discoveryBase/apps" `
    -Headers @{ Accept = 'application/json' } `
    -TimeoutSec 10 `
    -UseBasicParsing

$contentType = [string]$response.Headers['Content-Type']
if ($contentType -notmatch '^application/json(?:\s*;|$)') {
    throw "Content-Type không đúng hợp đồng: $contentType"
}
$body = [string]$response.Content
if ([string]::IsNullOrWhiteSpace($body)) {
    throw 'Body rỗng, không thể coi là danh mục JSON'
}
if (-not $body.TrimStart().StartsWith('[')) {
    throw 'Đang chờ mảng danh mục ở gốc JSON'
}
$catalog = @($body | ConvertFrom-Json -ErrorAction Stop)
$orders = @($catalog | Where-Object { $_.name -eq 'orders' })
if ($orders.Count -ne 1) {
    throw 'Không tìm thấy đúng một nhóm tên orders trong phản hồi'
}
$instances = @($orders[0].serviceInstances)
if ($instances.Count -eq 0) {
    throw 'Có nhóm orders nhưng ca thử cần ít nhất một instance'
}
$instances | Select-Object serviceId, instanceId, namespace, host, port, secure, uri
```

Đây là bước thăm dò cho một hợp đồng cụ thể, không phải bộ kiểm tra schema tổng quát. Đặc biệt, `@(...)` giúp xử lý kết quả có 0, 1 hoặc nhiều phần tử trong PowerShell; nó không chứng minh từng phần tử đúng kiểu.

Nếu cần `/apps/orders`, bỏ bước đọc object bọc và duyệt trực tiếp mảng instance của endpoint đó. Không truy cập `.serviceInstances` trên kết quả `/apps/orders`.

### 9.3. Đi từ danh sách đến chi tiết

Sau khi có `$instances` từ bước trước, dùng một ID vừa đọc để minh họa truy vấn chi tiết:

```powershell
$serviceSegment = [uri]::EscapeDataString('orders')
$idSegment = [uri]::EscapeDataString([string]$instances[0].instanceId)
$detail = Invoke-RestMethod `
    -Uri "$discoveryBase/apps/$serviceSegment/$idSegment" `
    -Headers @{ Accept = 'application/json' } `
    -TimeoutSec 10
$detail | Select-Object serviceId, instanceId, namespace, host, port, uri
```

Việc dùng phần tử đầu ở đây chỉ phục vụ ví dụ chuyển từ danh sách sang một bản ghi chi tiết. Đây không phải thuật toán cân bằng tải và không cam kết phần tử đầu ổn định qua các lần đọc.

Instance có thể biến mất giữa hai request. Khi đó xử lý tình huống không tìm thấy theo hợp đồng server, rồi có thể đọc lại danh sách với số lần thử hữu hạn. Không giữ ID cũ và lặp vô hạn.

### 9.4. Đối chiếu khi dữ liệu gây nghi ngờ

Khi có quyền đọc namespace chứa ứng dụng:

```powershell
kubectl get service orders -n shop -o yaml
kubectl get pods -n shop -l app=orders -o wide
kubectl get endpointslices.discovery.k8s.io -n shop -l kubernetes.io/service-name=orders -o yaml
```

Nếu server đang dùng nguồn Endpoints, đối chiếu thêm đúng nguồn đó:

```powershell
kubectl get endpoints orders -n shop -o yaml
```

Nguồn endpoint phải phù hợp cấu hình server. Không coi việc EndpointSlice đúng là bằng chứng server chắc chắn đã đọc được slice; server có thể đang dùng Endpoints hoặc thiếu quyền ở API group tương ứng.

Khi đối chiếu nhiều slice, giữ quan hệ địa chỉ–cổng trong từng slice. Hai IP thuộc hai nhóm cổng khác nhau không được ghép chéo để tạo ra một instance chưa từng tồn tại.

## 10. Dùng dữ liệu qua DiscoveryClient trong ứng dụng Spring

Ứng dụng Spring có thể dùng starter HTTP discovery `spring-cloud-starter-kubernetes-discoveryclient` rồi làm việc với abstraction `DiscoveryClient`, thay vì tự duy trì parser REST. Starter này phục vụ luồng HTTP Discovery Server. [Tài liệu Discovery Server](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-discoveryserver.html).

Ví dụ thuộc tính client, với tên Service và domain cụm phù hợp triển khai giả định:

```yaml
spring:
  cloud:
    kubernetes:
      discovery:
        discovery-server-url: http://spring-cloud-kubernetes-discoveryserver.discovery-system.svc.cluster.local
```

Thuộc tính trên chỉ định URL server; không làm client nhận quyền đọc Kubernetes API hoặc thay đổi phạm vi namespace mà server quan sát. Trong môi trường có domain cụm khác, proxy hoặc TLS, dùng URL thực tế của hệ thống. [Thuộc tính discovery-server-url](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

Một component chỉ đọc các URI được khám phá có thể viết:

```java
package example.discovery;

import java.net.URI;
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class OrdersDiscoveryView {
    private final DiscoveryClient discoveryClient;

    public OrdersDiscoveryView(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<URI> currentBaseUris() {
        return discoveryClient.getInstances("orders").stream()
            .map(ServiceInstance::getUri)
            .toList();
    }
}
```

Ví dụ giả định dự án đã cấu hình bộ phiên bản tương thích và có bean discovery. Phương thức chỉ trả danh sách hiện tại; nó chưa chọn backend, chưa gọi HTTP và chưa thực hiện kiểm tra sức khỏe.

Dùng abstraction giảm phụ thuộc vào chi tiết serialization. Tuy vậy consumer vẫn phải quyết định cách xử lý danh sách rỗng, namespace mong muốn, URI không dùng được và lỗi request. Nếu cần đọc JSON trực tiếp vì viết công cụ đa ngôn ngữ, hãy quản lý schema như một hợp đồng phiên bản riêng.

## 11. Quy tắc cho consumer đọc JSON trực tiếp

Một consumer bền vững cần tách ba bước: lấy phản hồi, xác thực hợp đồng, rồi mới dùng dữ liệu.

1. **Xác thực giao vận:** đặt timeout, kiểm tra HTTP status, Content-Type, giới hạn kích thước body phù hợp số dịch vụ.
2. **Xác thực hình dạng:** gốc là mảng hay object theo endpoint; phân biệt mảng instance với object bọc dịch vụ.
3. **Xác thực kiểu cốt lõi:** chuỗi cho định danh/host, số nguyên cho cổng, Boolean cho secure. Không âm thầm dùng cổng 0 hoặc secure=false chỉ vì trường bắt buộc bị thiếu.
4. **Xác thực ngữ nghĩa:** serviceId, namespace, nguồn server và URI thuộc phạm vi consumer được phép sử dụng.
5. **Dung nạp mở rộng có kiểm soát:** trường lạ có thể được bỏ qua, nhưng trường cốt lõi sai kiểu phải tạo lỗi có thể quan sát.
6. **Giữ phân biệt trạng thái:** không có instance, lỗi đọc discovery và dữ liệu không hợp lệ phải có cách xử lý riêng.

Với consumer chỉ hỗ trợ backend HTTP/HTTPS trực tiếp, một chính sách tối thiểu là: có serviceId và host, cổng trong 1–65535, URI tuyệt đối thuộc scheme được phép, không chứa userinfo, namespace đúng môi trường và không mâu thuẫn giữa các trường kết nối. Đối với ExternalName hoặc mô hình cổng đặc biệt, phải có nhánh hợp đồng riêng trước khi chấp nhận.

Metadata thuộc quyền thay đổi của các chủ tài nguyên và cấu hình server. Không dùng một annotation tùy ý làm bằng chứng phân quyền người dùng. Nếu có logic routing theo metadata, xác định rõ danh sách khóa, kiểu giá trị và bên được phép sửa chúng.

Thứ tự phần tử JSON object không có ý nghĩa lựa chọn backend. Thứ tự instance trong mảng cũng không nên được nâng thành độ ưu tiên nếu server không có cam kết về thứ tự. Khi so sánh hai phản hồi, dùng khóa nhận diện và tập dữ liệu có ý nghĩa thay vì so nguyên chuỗi JSON.

## 12. Các tình huống nên dùng để kiểm chứng cách đọc

Các phép kiểm chứng sau phục vụ consumer của bạn; không phải yêu cầu sửa payload server để làm vừa parser.

| Tình huống đầu vào | Kết quả consumer cần thể hiện |
| --- | --- |
| Hai instance hợp lệ của cùng dịch vụ | Giữ đủ hai đích; không mất phần tử do giả định chỉ có một |
| Cùng serviceId nhưng khác namespace | Nhận diện môi trường, lọc hoặc từ chối theo chính sách |
| Instance bị thay trong lần đọc kế tiếp | Cập nhật tập đích, không dùng IP cũ vô hạn |
| `metadata` rỗng hoặc thiếu khóa tùy chọn | Xử lý được và không bịa giá trị nghiệp vụ |
| Có thêm trường mở rộng chưa biết | Đọc được phần hợp đồng đang hỗ trợ |
| `secure` là chuỗi `"false"` trong hợp đồng yêu cầu Boolean | Báo dữ liệu sai kiểu |
| Danh sách rỗng hợp lệ | Đi vào nhánh không có instance, không báo parse lỗi |
| HTTP lỗi hoặc body HTML | Đi vào nhánh lỗi lấy dữ liệu, không giả thành `[]` |
| URI không hợp lệ hoặc cổng không hỗ trợ | Từ chối có nguyên nhân trước khi gửi request |
| Instance có mặt nhưng backend không phản hồi | Ghi nhận lỗi đường gọi nghiệp vụ, không kết luận JSON sai chỉ vì kết nối thất bại |

Đối với bài toán thực tế, chọn một instance và đối chiếu đủ bốn lớp: Service định nghĩa gì, nguồn endpoint công bố gì, Discovery Server trả gì và ứng dụng gọi nhận được gì. Chỉ khi các lớp đó thống nhất mới có bằng chứng đầy đủ cho một đường gọi.

## 13. Ranh giới với cấu hình và sức khỏe ứng dụng

Trong phạm vi module, ba câu hỏi thường bị trộn lẫn:

| Câu hỏi | Nguồn bằng chứng thích hợp |
| --- | --- |
| Dịch vụ có những đích nào được khám phá? | JSON Discovery Server hoặc DiscoveryClient |
| Ứng dụng đã nhận ConfigMap/Secret mới chưa? | Cơ chế nạp cấu hình, revision và trạng thái ứng dụng |
| Backend có xử lý được request hiện tại không? | Readiness phù hợp và phép gọi nghiệp vụ thực tế |

Configuration Watcher hỗ trợ luồng thông báo thay đổi cấu hình theo cách triển khai của hệ thống. Không có cơ sở coi một instance vẫn xuất hiện trong `/apps` là xác nhận refresh đã thành công. Tương tự, phản hồi discovery không phải kho phân phối nội dung Secret cho consumer.

Nếu ứng dụng chỉ cần gọi một Service ổn định qua DNS, không nhất thiết phải đọc danh sách từng Pod. Chọn HTTP Discovery Server khi kiến trúc cần dữ liệu instance qua HTTP, metadata hoặc tích hợp abstraction discovery. Hiểu đúng dữ liệu trả về giúp dùng đúng tính năng cần thiết và giữ việc chẩn đoán dựa trên bằng chứng cụ thể.
