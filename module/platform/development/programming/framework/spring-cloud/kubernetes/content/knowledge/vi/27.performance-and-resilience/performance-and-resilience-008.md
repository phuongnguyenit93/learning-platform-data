# Chi phí bộ nhớ của danh sách tài nguyên và metadata

## 1. Bối cảnh và mục tiêu

Một ứng dụng Spring có thể chỉ gọi vài dịch vụ nhưng vẫn giữ trong heap thông tin về hàng nghìn Service, endpoint hoặc Pod. Phần bộ nhớ này thuộc đường tích hợp với Kubernetes; nó có thể tăng theo quy mô cụm ngay cả khi lưu lượng nghiệp vụ không đổi.

Trong module **SPRING_CLOUD_KUBERNETES**, bài học này thuộc chương **Hiệu năng và độ bền**. Mục tiêu là hiểu chi phí của dữ liệu discovery và cấu hình để chọn đúng những tính năng cần thiết: DiscoveryClient, Spring Cloud LoadBalancer, nguồn ConfigMap/Secret và Configuration Watcher.

Sau bài học, bạn có thể:

- Phân biệt kích thước phản hồi API, bộ nhớ cấp phát tạm thời và bộ nhớ còn được giữ.
- Ước lượng ảnh hưởng của số tài nguyên, số endpoint, metadata và số replica.
- Thu hẹp phạm vi discovery mà vẫn giữ đúng hành vi định tuyến và cập nhật cấu hình.
- Đo bộ nhớ khi khởi động, vận hành ổn định và đồng bộ lại dữ liệu.
- Phân biệt cache có kích thước lớn hợp lệ với việc giữ dữ liệu cũ ngoài ý muốn.

Bài giả định bạn đã biết Service, namespace, nhãn, annotation và cách ứng dụng Spring lấy danh sách ServiceInstance. Các con số phía dưới là **giả định để tính toán**, không phải benchmark hoặc giới hạn cố định của thư viện.

## 2. Một danh sách tài nguyên đi qua những lớp nào?

Xét một ứng dụng dùng Kubernetes client trong cùng tiến trình để phục vụ DiscoveryClient:

~~~text
Kubernetes API
    |
    | LIST ban đầu và các thay đổi qua WATCH
    v
HTTP buffer / dữ liệu giải mã
    |
    v
Đối tượng Java: Service, Endpoints hoặc EndpointSlice...
    |
    v
Store/cache và index của client, nếu implementation sử dụng
    |
    v
Danh sách ServiceInstance và các map metadata
    |
    v
Supplier/cache của LoadBalancer và tham chiếu trong ứng dụng
~~~

Sơ đồ mô tả những lớp **có thể tồn tại**. Nó không khẳng định mọi implementation đều tạo đủ các lớp hoặc sao chép toàn bộ dữ liệu.

Spring Cloud Kubernetes có client dựa trên Fabric8, Kubernetes Java Client và client HTTP sử dụng DiscoveryServer. Với client HTTP, phải tính cả bộ nhớ của server discovery và phía ứng dụng. [Tài liệu DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

### 2.1. Dữ liệu trên mạng

Kích thước JSON hoặc dữ liệu đã nén chỉ mô tả lượng dữ liệu truyền. Sau giải mã, ứng dụng có thể có thêm đối tượng Java, mảng, map, chuỗi và cấu trúc chỉ mục.

Vì vậy, một phản hồi nhỏ trên mạng chưa chứng minh rằng phần dữ liệu tương ứng chiếm ít heap. Không có hệ số chung như “JSON nhân ba” áp dụng chính xác cho mọi client và JVM.

### 2.2. Bộ nhớ được giữ lâu dài

**Retained memory** là phần bộ nhớ còn sống do một chủ thể vẫn giữ tham chiếu, trực tiếp hoặc gián tiếp. Ví dụ, store giữ một Service; Service giữ metadata; metadata giữ các map nhãn và annotation.

Cần phân biệt:

- **Shallow size**: bộ nhớ của chính đối tượng đang xét.
- **Retained size**: phần có thể được thu hồi nếu chủ thể đó cùng những đối tượng chỉ còn được nó giữ trở nên không thể truy cập.

Một đối tượng danh sách có thể rất nhỏ, trong khi các phần tử mà nó giữ chiếm nhiều MiB. Ngược lại, hai danh sách có thể chỉ giữ tham chiếu tới cùng các phần tử, nên cộng toàn bộ retained size của cả hai sẽ đếm trùng.

### 2.3. Bộ nhớ tạm và tốc độ cấp phát

Một lần lấy danh sách có thể đồng thời cần buffer nhận dữ liệu, đối tượng đang giải mã và đối tượng đã xử lý. Khi chuyển đổi sang ServiceInstance, ứng dụng còn có thể tạo các danh sách hoặc map mới.

Hai triệu chứng cần chẩn đoán riêng:

- Heap còn sống sau các chu kỳ GC tăng: kiểm tra số tài nguyên, cache và chủ thể giữ tham chiếu.
- Heap ổn định nhưng GC hoạt động nhiều: kiểm tra tốc độ tạo danh sách, chuyển đổi metadata và tần suất truy vấn.

Việc heap tăng trong lúc nhận dữ liệu rồi giảm không tự chứng minh có rò rỉ bộ nhớ. Điều cần biết là dữ liệu nào vẫn được giữ sau khi đợt xử lý kết thúc.

## 3. Những dữ liệu nào tạo chi phí?

| Nhóm dữ liệu | Điều làm bộ nhớ tăng | Câu hỏi cần trả lời |
| --- | --- | --- |
| Service | Số Service, số cổng và metadata mỗi Service | Ứng dụng cần thấy những Service nào? |
| Endpoints hoặc EndpointSlice | Số địa chỉ, cổng, điều kiện và các đối tượng chứa chúng | Tổng số instance phải định tuyến là bao nhiêu? |
| Pod, nếu tính năng thực sự đọc Pod | Spec, status, container, metadata và index | Có cần toàn bộ đối tượng Pod để thực hiện yêu cầu này không? |
| ConfigMap | Số nguồn cấu hình, kích thước dữ liệu và các biểu diễn sau khi phân tích | Có đang đọc cấu hình của ứng dụng khác không? |
| Secret | Dữ liệu nhận từ API, biểu diễn giải mã và giá trị cấu hình được giữ | Thành phần nào thật sự cần đọc Secret? |
| ServiceInstance | Số endpoint được chuyển đổi, metadata và số snapshot còn sống | Danh sách này được tạo lại và giữ bao lâu? |
| Hàng đợi sự kiện | Tốc độ thay đổi và tốc độ xử lý | Consumer có theo kịp sự kiện không? |

Số Service chưa đủ để mô tả quy mô. Một Service có hàng nghìn endpoint có thể đắt hơn nhiều Service nhỏ. Cũng không nên dùng số Pod thay cho số ServiceInstance một cách máy móc: cổng, họ địa chỉ, trạng thái sẵn sàng và cách chuyển đổi của client đều ảnh hưởng kết quả.

Nếu bật thêm dữ liệu Pod hoặc một tính năng theo dõi khác, hãy kiểm tra implementation và lưu lượng API thực tế. Không mặc định rằng discovery luôn cần tải toàn bộ Pod, hoặc rằng một tùy chọn metadata chắc chắn tạo thêm đúng một cache Pod.

## 4. Mô hình dự toán bộ nhớ

### 4.1. Bộ nhớ ổn định của một tiến trình

Có thể bắt đầu bằng mô hình:

~~~text
H_stable ≈ H_base
         + Σ(N_resource_type × B_retained_per_resource)
         + H_indexes
         + H_instance_snapshots
         + H_queues
         + H_other_features
~~~

Trong đó:

- H_base là heap nền của ứng dụng trong cùng điều kiện tải.
- N_resource_type là số đối tượng thực sự được giữ cho từng loại tài nguyên.
- B_retained_per_resource là chi phí trung bình của đối tượng thuộc loại đó.
- H_indexes là phần riêng của các index, không cộng lại dữ liệu đã được tính ở đối tượng.
- H_instance_snapshots là phần bổ sung cho ServiceInstance và metadata được giữ.
- H_queues là bộ nhớ sự kiện chưa xử lý.
- H_other_features gồm các tính năng khác như nguồn cấu hình, cache nghiệp vụ.

Đây là phép phân rã để đặt câu hỏi và tổ chức phép đo. Khi dùng heap analyzer, phải loại bỏ phần dùng chung giữa các nhóm để tránh cộng hai lần.

### 4.2. Ví dụ tính toán

Giả sử một phép đo thử nghiệm cho kết quả sau. Mỗi dòng biểu thị phần bộ nhớ **riêng**, chưa được tính trong dòng khác:

| Thành phần | Số lượng | Chi phí giả định | Thành tiền |
| --- | ---: | ---: | ---: |
| Service trong store | 1.200 | 6 KiB/Service | 7.200 KiB |
| Đối tượng chứa endpoint | 1.200 | 14 KiB/đối tượng | 16.800 KiB |
| ServiceInstance cùng phần metadata riêng | 12.000 | 1,5 KiB/instance | 18.000 KiB |
| Index và cấu trúc hỗ trợ | Một tập | 5 MiB | 5 MiB |

Tổng phần tích hợp discovery:

~~~text
(7.200 + 16.800 + 18.000) / 1.024 + 5
= 46,015625 MiB
≈ 46,02 MiB
~~~

Nếu 30 replica giữ các tập dữ liệu tương đương:

~~~text
30 × 46,015625 ≈ 1.380,47 MiB
                    ≈ 1,35 GiB
~~~

Đó mới là phần heap discovery trong giả định này. Chưa bao gồm heap nền, bộ nhớ ngoài heap, buffer mạng và tải nghiệp vụ của mỗi replica.

Ví dụ minh họa tác động của việc nhân bản cache. Tăng số replica để xử lý lưu lượng thường nhân thêm các bản dữ liệu discovery; nó không tự chia nhỏ danh sách mà mỗi replica theo dõi.

### 4.3. Dự toán đỉnh

Heap ổn định chưa thể hiện toàn bộ yêu cầu khi khởi động hoặc thay đổi dữ liệu:

~~~text
H_peak ≈ H_stable
       + H_buffers_in_flight
       + H_new_objects_in_flight
       + H_old_snapshots_still_referenced
       + H_event_backlog
~~~

Không mặc định đỉnh luôn gấp đôi trạng thái ổn định. Có implementation cập nhật từng phần; cũng có đường xử lý giữ snapshot cũ trong lúc dựng snapshot mới. Phải đo đúng client, phiên bản và tính năng được bật.

Đặc biệt, giữ danh sách cũ trong một biến lịch sử, một publisher hoặc một cache tự viết có thể kéo dài tuổi thọ dữ liệu dù cache của thư viện đã thay thế nó.

## 5. Vì sao metadata dễ bị đánh giá thấp?

### 5.1. Metadata có thể xuất hiện ở nhiều biểu diễn

Với một Service có E instance và phần metadata riêng kích thước B:

~~~text
Phần sao chép bổ sung tối đa trong mô hình đơn giản ≈ E × B
~~~

Giả sử E bằng 250 và mỗi map metadata riêng chiếm 4 KiB, phần bổ sung là khoảng 1.000 KiB, tức gần 0,98 MiB.

Nếu các instance dùng chung một map bất biến thì mô hình này sẽ phóng đại chi phí. Nếu chỉ sao chép map nhưng chia sẻ chuỗi thì chi phí nằm giữa hai trường hợp. Phải nhìn cấu trúc giữ tham chiếu trong heap; không suy ra số byte từ số lần gọi getMetadata().

### 5.2. Nhãn và annotation cần được xét theo nhu cầu sử dụng

Một khóa nhãn ngắn có thể phục vụ định tuyến theo môi trường hoặc nhóm ứng dụng. Một annotation chứa cấu hình nhiều dòng có thể lớn hơn toàn bộ dữ liệu cần cho việc chọn endpoint.

Các chi phí dễ bị bỏ sót gồm:

- Map, entry và tham chiếu ngoài phần ký tự nhìn thấy.
- Khóa giống nhau nhưng chưa chắc dùng chung cùng đối tượng chuỗi.
- Metadata quản lý của Kubernetes như ownerReferences hoặc managedFields, nếu client tải và giữ các trường đó.
- Snapshot cũ còn sống sau một lần cập nhật.
- Thay đổi metadata tạo thêm công việc xử lý dù địa chỉ endpoint không đổi.

Không cần xóa nhãn mà công cụ vận hành đang dùng. Mục tiêu là tránh chuyển tiếp và giữ những dữ liệu không phục vụ thành phần đang xét.

### 5.3. Tắt metadata ở đầu ra có tác dụng tới đâu?

Spring Cloud Kubernetes cung cấp các cờ bổ sung nhãn, annotation, thông tin cổng và metadata Pod vào kết quả discovery. [Danh mục thuộc tính](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

Cần phân biệt hai phạm vi:

~~~text
Tài nguyên gốc được client giữ
    !=
Metadata được đưa vào ServiceInstance
~~~

Tắt việc thêm annotation vào ServiceInstance có thể giảm phần đối tượng đầu ra. Thao tác đó không chứng minh rằng trường annotation đã biến mất khỏi Service gốc trong store. Cũng không chứng minh số tài nguyên hoặc kích thước phản hồi API đã giảm.

Đây là suy luận từ vị trí dữ liệu trong đường xử lý: muốn giảm một lớp phải tác động vào cách lớp đó tải, chuyển đổi hoặc giữ dữ liệu, rồi kiểm chứng bằng phép đo.

## 6. Thu hẹp dữ liệu trước khi tăng heap

### 6.1. Chọn namespace và Service cần thiết

DiscoveryClient hỗ trợ giới hạn namespace và chọn Service bằng nhãn. Với client HTTP, phạm vi discovery cần cấu hình ở DiscoveryServer. [Phạm vi tìm kiếm của DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Ví dụ dưới đây dành cho ứng dụng dùng client trong tiến trình, chỉ cần discovery ở namespace commerce. Đây là đoạn cấu hình để tích hợp vào dự án đã có bộ dependency tương thích:

~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        all-namespaces: false
        namespaces:
          - commerce
        service-labels:
          discovery-scope: commerce
        metadata:
          add-labels: false
          add-annotations: false
          add-ports: false
          add-pod-labels: false
          add-pod-annotations: false
~~~

Các cờ metadata trong ví dụ chỉ phù hợp khi consumer không dùng những trường bổ sung đó. Đối chiếu tên thuộc tính với phiên bản đang triển khai. [Thuộc tính discovery](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

Service tham gia tập discovery có thể được khai báo như sau:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: inventory
  namespace: commerce
  labels:
    discovery-scope: commerce
spec:
  selector:
    app: inventory
  ports:
    - name: http
      port: 8080
      targetPort: 8080
~~~

Có hai phép chọn độc lập trong ví dụ:

- Nhãn ở metadata.labels xác định Service thuộc tập discovery nào.
- spec.selector xác định Pod phục vụ Service đó.

Gắn nhãn discovery chỉ vào Pod sẽ không làm Service tự có nhãn tương ứng. Khi đánh giá hiệu quả, đếm cả Service lẫn tài nguyên endpoint còn được client giữ; không suy ra mọi store đều thu nhỏ theo cùng một tỷ lệ.

### 6.2. Phân biệt lọc đầu vào và lọc sau khi nhận dữ liệu

Thuộc tính discovery.filter dùng SpEL lọc sau khi đã lấy dữ liệu từ API. Vì vậy, danh sách đầu ra nhỏ không chứng minh chi phí tải dữ liệu nhỏ. [Mô tả thuộc tính filter](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

Đối với một client tự viết, phép chọn ở yêu cầu API có dạng:

~~~http
GET /api/v1/namespaces/commerce/services?labelSelector=discovery-scope%3Dcommerce
~~~

Đường dẫn trên minh họa namespace và nhãn được đưa vào yêu cầu. Khi khảo sát ứng dụng thật, kiểm tra request thực tế hoặc số phần tử trong store thay vì chỉ nhìn YAML cấu hình.

Lọc sớm thường có cơ hội giảm nhiều lớp chi phí hơn. Lọc trong danh sách Java sau khi đã tải đầy đủ vẫn có thể cần cho nghiệp vụ, nhưng không thay thế việc giới hạn phạm vi thu thập.

### 6.3. Kiểm tra các consumer của metadata

Trước khi tắt một nhóm metadata, tìm nơi tiêu thụ nó:

| Consumer | Điều phải xác nhận |
| --- | --- |
| Quy tắc chọn instance | Có dùng nhãn hoặc annotation để chọn phiên bản, nhóm hay vùng không? |
| LoadBalancer hoặc ServiceInstanceListSupplier tùy biến | Có đọc khóa metadata cụ thể không? |
| Chọn cổng | Có code đọc thông tin cổng trong metadata không? |
| Configuration Watcher | Cơ chế xác định đích refresh đang dùng tên hay nhãn? |
| Quan sát và chẩn đoán | Dashboard hoặc mã log có phụ thuộc trường vừa bỏ không? |

Chẳng hạn, Configuration Watcher hỗ trợ xác định đích từ nhãn trong metadata của ServiceInstance; cách đó yêu cầu bật add-labels. [Yêu cầu metadata của Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Nếu consumer cần nhãn, giữ phần đó và cân nhắc giảm annotation hoặc phạm vi discovery. Giảm bộ nhớ chỉ có giá trị khi chức năng sử dụng dữ liệu vẫn hoạt động đúng.

## 7. LIST, WATCH, phân trang và EndpointSlice

### 7.1. Danh sách nhỏ hơn mỗi lần chưa chắc tạo cache nhỏ hơn

Kubernetes hỗ trợ chia kết quả LIST bằng limit và continue. Khi lấy hết các trang rồi giữ mọi đối tượng, cache cuối cùng vẫn chứa toàn bộ tập đã chọn. WATCH cũng không có nghĩa là client không giữ trạng thái. [Cơ chế danh sách và theo dõi thay đổi](https://kubernetes.io/docs/reference/using-api/api-concepts/).

~~~text
Một trang có tối đa 200 đối tượng
    |
    | Lặp qua 25 trang
    v
Store có thể vẫn giữ 5.000 đối tượng
~~~

Phân trang có thể giảm phần dữ liệu đang nhận và giải mã tại một thời điểm. Nó không giải quyết việc ứng dụng giữ quá nhiều đối tượng sau đó. Tương tự, nén mạng không loại bỏ đối tượng Java đã được giải mã.

Với client tự viết, xử lý từng trang rồi bỏ dữ liệu không cần giữ có thể hữu ích. Với framework, phải xác nhận đường gọi và phiên bản có hỗ trợ cơ chế đó; không tự thêm một thuộc tính Spring không được tài liệu hóa.

### 7.2. Đồng bộ lại có thể tạo một đợt cấp phát mới

Khi WATCH nhận 410 Gone do lịch sử cần thiết không còn, client phải lấy lại trạng thái rồi tiếp tục theo dõi. [Xử lý resourceVersion hết hiệu lực](https://kubernetes.io/docs/reference/using-api/api-concepts/).

Đây là tình huống cần đo cùng với khởi động. Một ứng dụng có heap ổn định chấp nhận được vẫn có thể gặp đỉnh lớn khi dựng lại tập dữ liệu.

Cũng cần phân biệt đồng bộ lại từ API với “resync” trong một thư viện informer: thuật ngữ resync có thể chỉ việc xử lý lại đối tượng đã có, tùy implementation; không phải mọi lần resync đều tạo LIST mới.

### 7.3. EndpointSlice chia nhỏ đơn vị cập nhật

EndpointSlice chia tập endpoint thành nhiều đối tượng nhỏ hơn. Điều này có lợi cho cách phân phối và cập nhật endpoint ở quy mô lớn. [Thiết kế EndpointSlice](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).

Tuy nhiên, nếu ứng dụng vẫn cần toàn bộ địa chỉ thì tổng dữ liệu endpoint không biến mất. Số đối tượng chứa, metadata của từng slice và các index còn ảnh hưởng footprint.

Đánh giá việc chuyển sang EndpointSlice bằng cùng số endpoint và cùng tính năng. Phải kiểm tra hỗ trợ của client và quyền truy cập tương ứng; không coi đây là một công tắc bảo đảm giảm heap theo tỷ lệ cố định.

## 8. ConfigMap, Secret, Configuration Watcher và RBAC

### 8.1. Tính riêng các nguồn cấu hình

Phạm vi discovery không đại diện cho phạm vi đọc cấu hình. Khi lập ngân sách, tách các thành phần:

~~~text
Ứng dụng:
  tài nguyên discovery
  + cấu hình thực sự được nạp
  + giá trị cấu hình sau phân tích hoặc binding

Configuration Watcher:
  tài nguyên theo dõi
  + dữ liệu xác định đích cập nhật
  + công việc thông báo chưa xử lý
~~~

Một ConfigMap có thể tồn tại dưới dạng đối tượng client, chuỗi nội dung, property source và đối tượng cấu hình đã bind. Đây là những biểu diễn cần kiểm tra, không phải khẳng định mọi đường nạp đều giữ đủ bốn bản sao.

Tương tự, việc đọc Secret từ API có thể tạo dữ liệu giải mã và giá trị trong bộ nhớ ứng dụng. Đưa Secret vào volume không làm giá trị hết chiếm heap sau khi ứng dụng đọc nó. Khi lấy heap dump để khảo sát, phải bảo vệ dữ liệu cấu hình nhạy cảm có thể xuất hiện trong dump.

Configuration Watcher có cấu hình namespace theo dõi riêng. Giới hạn thành phần này theo tập ứng dụng nó phục vụ. [Phạm vi của Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

### 8.2. RBAC hỗ trợ giới hạn trách nhiệm

Dưới đây là **trích đoạn Role** dành cho một thành phần discovery dùng Service và EndpointSlice trong namespace commerce:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: commerce-discovery-reader
  namespace: commerce
rules:
  - apiGroups: [""]
    resources: ["services"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
~~~

Cần RoleBinding tới đúng ServiceAccount; trích đoạn trên chưa phải bộ triển khai hoàn chỉnh. Nếu client dùng Endpoints thì cần quyền cho tài nguyên đó. Chỉ thêm Pod, ConfigMap hoặc Secret khi chức năng tương ứng cần chúng.

RBAC thông thường không tự giới hạn đối tượng theo nhãn. Giới hạn list/watch bằng resourceNames còn đòi hỏi client gửi field selector metadata.name phù hợp. [Quy tắc RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Vì vậy, namespace và selector trong client vẫn cần được thiết kế rõ ràng. Một yêu cầu quá rộng bị 403 sẽ tạo lỗi cần sửa; không phải một chiến lược giảm bộ nhớ.

## 9. Đo đúng lớp bộ nhớ

### 9.1. Chọn tập tín hiệu

Không kết luận từ một con số memory duy nhất. Thu thập đồng thời:

| Tín hiệu | Giúp trả lời | Giới hạn |
| --- | --- | --- |
| Heap used và heap sau các chu kỳ GC | Dữ liệu sống có tăng không? | Phải so sánh cùng giai đoạn tải |
| Allocation rate và thời gian GC | Có đang tạo quá nhiều đối tượng ngắn hạn không? | Không chỉ ra chủ thể giữ dữ liệu |
| Histogram và dominator tree | Đối tượng nào nhiều, ai giữ chúng? | Histogram chỉ có shallow size theo lớp |
| RSS hoặc working set của container | Container đang tiến gần ngân sách nào? | Khác với heap used |
| Số tài nguyên và độ dài hàng đợi | Footprint tăng theo quy mô hay backlog? | Có thể cần bổ sung metric riêng |
| LIST/WATCH, reconnect và thời gian đồng bộ | Đỉnh có gắn với cập nhật từ API không? | Cần ghép với timeline bộ nhớ |
| Readiness, lỗi gọi dịch vụ và độ trễ | Tối ưu có giữ được hành vi mong muốn không? | Phải kiểm tra theo luồng nghiệp vụ |

Không gắn tên từng Pod hoặc toàn bộ metadata làm nhãn metric bộ nhớ. Một metric tổng hợp theo loại tài nguyên và namespace được kiểm soát thường dễ vận hành hơn; thêm cardinality không cần thiết sẽ tạo một nguồn chi phí quan sát khác.

### 9.2. Quan sát từ Spring Boot Actuator

Trong môi trường thử nghiệm có Actuator và endpoint metrics đã được cấu hình truy cập phù hợp:

~~~bash
curl "http://localhost:8080/actuator/metrics"
curl "http://localhost:8080/actuator/metrics/jvm.memory.used?tag=area:heap"
curl "http://localhost:8080/actuator/metrics/jvm.memory.committed?tag=area:heap"
~~~

Endpoint metrics cho phép xem các meter hiện có và lọc theo tag. Tên meter hiển thị ở đây có thể khác cách đặt tên tại hệ thống xuất metric. [Spring Boot Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).

Heap used lấy ở một thời điểm có thể gồm dữ liệu sắp được GC thu hồi. Hãy ghi chuỗi thời gian và so các đoạn ổn định tương đương. Không dùng heap committed như số byte đối tượng còn sống.

### 9.3. Khảo sát JVM trong môi trường thử nghiệm

Các lệnh dưới đây minh họa chẩn đoán HotSpot, không phải lệnh bắt buộc chạy trên production:

~~~bash
jcmd -l
jcmd <PID> GC.heap_info
jcmd <PID> GC.class_histogram
jcmd <PID> JFR.start name=k8s-memory settings=profile duration=60s filename=/tmp/k8s-memory.jfr
~~~

Thay <PID> bằng PID thật. jcmd cần môi trường và quyền attach phù hợp. GC.class_histogram có mức tác động cao; chỉ dùng khi chấp nhận ảnh hưởng phép đo. [Tài liệu jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).

Khi đọc kết quả, tìm các nhóm liên quan:

- Model của Kubernetes client đang dùng.
- Map, entry, String và mảng byte.
- ServiceInstance và danh sách chứa chúng.
- Store, index, queue và supplier đang giữ tham chiếu.

Tên lớp nhiều nhất chưa đủ để kết luận nguyên nhân. Ví dụ, String có thể thuộc cấu hình, HTTP, discovery hoặc nghiệp vụ. Dùng đường tham chiếu từ GC root và dominator tree để xác định phần nào thuộc tập tài nguyên đang khảo sát.

Nếu chỉ số container tăng trong khi heap sống ổn định, mở rộng khảo sát sang thread stack, direct buffer, metaspace và các phần native. Không quy mọi chênh lệch cho metadata.

## 10. Bài thực hành: thu hẹp dữ liệu nhưng giữ đúng chức năng

Bài thực hành thực hiện trên môi trường thử nghiệm. Không cần cố tình gây OOM để chứng minh chi phí bộ nhớ.

### 10.1. Chuẩn bị một phép so sánh công bằng

Giữ cố định:

- Phiên bản Spring Boot, Spring Cloud, Kubernetes client và JDK.
- Image ứng dụng, cờ JVM, tài nguyên container và số replica.
- Số tài nguyên trong cụm, tải gọi dịch vụ và thời gian quan sát.
- Tính năng discovery, cache và cấu hình đang bật.

Ghi lại namespace cần thiết, các Service đích, tổng endpoint và consumer của metadata. Nếu baseline đã giới hạn phạm vi hợp lý thì dùng chính baseline đó; không cần mở quyền toàn cụm chỉ để tạo một phép so sánh.

### 10.2. Đếm tập dữ liệu quan sát được

Các lệnh chỉ đọc dưới đây chạy từ máy quản trị có kubectl. Chúng giúp kiểm kê, không đo heap của ứng dụng:

~~~bash
kubectl get services -n commerce -o name
kubectl get services -n commerce -l discovery-scope=commerce -o name
kubectl get endpointslices.discovery.k8s.io -n commerce -l kubernetes.io/service-name=inventory -o json
kubectl top pod -n commerce --containers
~~~

Lệnh top cần Metrics Server. Chỉ số container từ top không thay thế phép đo heap và có thể bỏ lỡ một đỉnh ngắn.

Đối chiếu tập kiểm kê với dữ liệu client thực sự giữ. Nếu implementation không có metric số phần tử store, có thể dùng công cụ chẩn đoán trong thử nghiệm hoặc bổ sung metric tổng hợp ở lớp mà ứng dụng kiểm soát. Tránh gọi một API đoán định không tồn tại trong thư viện.

### 10.3. Thực hiện từng thay đổi

| Lượt | Thay đổi | Điều cần quan sát |
| --- | --- | --- |
| A | Giữ baseline | Số tài nguyên, heap ổn định, đỉnh khởi động và hành vi discovery |
| B | Thu hẹp namespace | Những tập dữ liệu nào thực sự nhỏ đi? |
| C | Thêm nhãn chọn Service phù hợp | Store Service và dữ liệu endpoint thay đổi ra sao? |
| D | Bỏ nhóm metadata không dùng | Phần ServiceInstance giảm hay cả tài nguyên gốc cũng giảm? |
| E | Thử cập nhật cấu hình và thay đổi endpoint có kiểm soát | Cache cập nhật đúng, refresh đúng đích và đỉnh vẫn nằm trong ngân sách? |

Giữ mỗi thay đổi đủ lâu để cache đồng bộ và ứng dụng đi qua cùng chu kỳ tải. Các lượt sau kế thừa cấu hình cần thiết của lượt trước; ghi rõ điều đó trong kết quả.

Ở mỗi lượt, lấy mẫu lúc khởi động, lúc ổn định và khi thay đổi endpoint. Nếu cần kiểm tra phục hồi kết nối WATCH, dùng kịch bản thử nghiệm có kiểm soát và ghi nhận client có thực sự LIST lại hay chỉ tiếp tục WATCH.

### 10.4. Mẫu ghi kết quả

Đây là **biểu mẫu**, không phải số đo đã chạy:

| Cấu hình | Service giữ | Endpoint giữ | Heap ổn định sau GC | Heap đỉnh | Memory container đỉnh | Thời gian sẵn sàng | Kết quả chức năng |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline | Điền số đo | Điền số đo | Điền số đo | Điền số đo | Điền số đo | Điền số đo | Điền kết quả |
| Giới hạn namespace | Điền số đo | Điền số đo | Điền số đo | Điền số đo | Điền số đo | Điền số đo | Điền kết quả |
| Thêm selector | Điền số đo | Điền số đo | Điền số đo | Điền số đo | Điền số đo | Điền số đo | Điền kết quả |
| Giảm metadata | Điền số đo | Điền số đo | Điền số đo | Điền số đo | Điền số đo | Điền số đo | Điền kết quả |

Một kết quả thuyết phục cần giải thích được cả số tài nguyên, bộ nhớ và hành vi. Ví dụ: “ServiceInstance bớt giữ map annotation, heap phần đầu ra giảm, trong khi store Service gần như không đổi” cụ thể hơn “ứng dụng nhẹ hơn”.

## 11. Liên hệ giữa bộ nhớ và độ bền

### 11.1. Khởi động đồng thời tạo tải đồng thời

Khi nhiều replica khởi động cùng lúc, chúng có thể đồng thời lấy danh sách và dựng cache. Tổng tác động gồm bộ nhớ từng replica, lưu lượng API và thời gian xử lý.

Đo thêm số replica khởi động đồng thời trong một đợt rollout. Nếu từng Pod ổn định khi chạy riêng nhưng đồng bộ chậm khi cả đợt chạy, cần xem lại cả phía client lẫn tải API.

### 11.2. Đừng để kiểm tra sức khỏe khuếch đại vấn đề

Đường kiểm tra readiness cần phản ánh khả năng phục vụ thực tế, với thời gian đồng bộ ban đầu được tính đến. Việc buộc liveness thất bại mỗi khi Kubernetes API tạm gián đoạn có thể gây restart, tạo thêm LIST và tăng cấp phát.

Khi chẩn đoán, ghép các mốc sau trên cùng timeline:

~~~text
Sự kiện tài nguyên hoặc mất kết nối
    -> hoạt động đồng bộ
    -> cấp phát và GC
    -> readiness / lỗi gọi dịch vụ
    -> restart nếu có
~~~

Nếu restart lặp lại, giảm dữ liệu theo dõi và sửa hành vi kiểm tra sức khỏe có thể quan trọng ngang việc cấp thêm bộ nhớ.

### 11.3. Đặt ngân sách theo container

Một mô hình lập kế hoạch đơn giản:

~~~text
Ngân sách container
    > heap hoạt động và đỉnh đã đo
    + phần ngoài heap đã quan sát
    + phần bộ nhớ khác được tính cho container
    + khoảng dự phòng theo mức biến động
~~~

Đây là ngân sách thực nghiệm, không phải phép cộng chính xác giữa RSS, heap committed và working set. Những chỉ số đó có định nghĩa khác nhau.

Memory limit được thực thi ở cấp container và việc vượt giới hạn có thể dẫn đến OOM kill. Do đó, -Xmx không nên được coi là toàn bộ nhu cầu bộ nhớ của tiến trình Java. [Quản lý bộ nhớ container](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/).

Không áp dụng một tỷ lệ heap cố định cho mọi dịch vụ. Đo tải thực, đỉnh đồng bộ và bộ nhớ ngoài heap trước khi quyết định request, limit và cấu hình JVM.

## 12. Chọn đúng mức tích hợp

| Nhu cầu | Hướng thiết kế để cân nhắc | Phần bộ nhớ vẫn cần tính |
| --- | --- | --- |
| Chỉ gọi một địa chỉ Service ổn định | Dùng DNS/Service của Kubernetes nếu đáp ứng yêu cầu | HTTP client, kết nối và dữ liệu nghiệp vụ |
| Cần danh sách instance để chọn tại ứng dụng | DiscoveryClient với phạm vi rõ ràng | Tài nguyên gốc, ServiceInstance và cache liên quan |
| Nhiều ứng dụng cần discovery qua một server chung | Đánh giá DiscoveryServer cùng yêu cầu sẵn sàng | Cache phía server và kết quả/caches phía client |
| Cần cập nhật cấu hình động | Chọn nguồn cấu hình và phạm vi Configuration Watcher | Dữ liệu cấu hình, dữ liệu theo dõi và thông báo |
| Cần quan sát sức khỏe từng Pod | Xác định dữ liệu và thành phần chuyên trách cần dùng | Dữ liệu Pod hoặc kết quả kiểm tra thực sự được giữ |

Dùng DNS/Service là một lựa chọn kiến trúc khi không cần danh sách instance hoặc metadata ở phía ứng dụng; không thay thế máy móc trong hệ thống đang phụ thuộc chọn instance.

Đưa discovery sang một server chung cũng chỉ chuyển và tổ chức lại trách nhiệm. Server vẫn cần ngân sách bộ nhớ, khả năng chịu lỗi và phạm vi dữ liệu phù hợp; client vẫn có thể giữ kết quả.

Khi hoàn thành bài thực hành, bạn nên có một quyết định cụ thể: giữ những tài nguyên nào, giữ metadata nào, thành phần nào chịu trách nhiệm cập nhật, và bằng chứng nào cho thấy bộ nhớ ổn định lẫn đỉnh đáp ứng ngân sách mà chức năng vẫn đúng.
