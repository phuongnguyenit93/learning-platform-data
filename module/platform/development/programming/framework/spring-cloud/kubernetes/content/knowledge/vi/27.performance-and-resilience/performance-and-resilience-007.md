# Ứng xử với dữ liệu đã có khi API server tạm thời không truy cập được

## 1. Mục tiêu và tình huống

Trong chương **Hiệu năng và độ bền** của module **SPRING_CLOUD_KUBERNETES**, bài này giải quyết một câu hỏi cụ thể: ứng dụng đã đọc được cấu hình và thông tin dịch vụ, sau đó mất kết nối với Kubernetes API server, thì nên tiếp tục phục vụ bằng dữ liệu nào?

Sau bài học, bạn có thể:

- Phân biệt cấu hình đang có hiệu lực, cache discovery và dữ liệu do Kubernetes chiếu vào container.
- Đặt giới hạn sử dụng dữ liệu cũ theo từng nghiệp vụ.
- Tách lỗi đồng bộ nền khỏi lỗi xử lý yêu cầu.
- Xử lý phục hồi mà không giữ lại endpoint đã bị xóa hoặc áp dụng cấu hình chưa hợp lệ.
- Thiết kế liveness, readiness và quan sát trạng thái phù hợp.

Ví dụ xuyên suốt: `order-api` gọi `inventory-api`, đọc cấu hình hiển thị từ ConfigMap và dùng thông tin xác thực từ Secret. Lúc 10:00, ứng dụng đã hoạt động bình thường. Lúc 10:02, riêng đường kết nối từ ứng dụng tới API server bị gián đoạn; mạng tới các dịch vụ nghiệp vụ vẫn hoạt động.

Đây là sự cố ở đường quản lý. Nó chưa đủ để kết luận rằng các Pod đích, cơ sở dữ liệu hoặc toàn bộ mạng trong cluster đều hỏng. Ngược lại, việc một yêu cầu nghiệp vụ vẫn thành công cũng chưa chứng minh thông tin discovery và cấu hình đang mới.

**Nguyên tắc của bài:** chỉ tiếp tục dùng dữ liệu đã được chấp nhận nếu dữ liệu đó còn phù hợp với hợp đồng nghiệp vụ, giới hạn độ cũ và yêu cầu bảo mật. Không biến việc mất kết nối thành giấy phép sử dụng mọi dữ liệu cũ vô thời hạn.

## 2. “Dữ liệu đã có” đang nằm ở đâu?

Cần xác định đúng nơi giữ dữ liệu trước khi thiết kế fallback.

| Loại dữ liệu | Nơi thường tồn tại | Khi API server không truy cập được | Điều không thể suy ra |
| --- | --- | --- | --- |
| Cấu hình đã nạp vào Spring | `Environment`, đối tượng cấu hình hoặc bean đang dùng | Giá trị hiện hành có thể tiếp tục được dùng nếu ứng dụng chưa thay thế hoặc hủy nó | Giá trị đó vẫn là phiên bản được quản trị viên mong muốn |
| Danh mục dịch vụ | Informer/lister hoặc cơ chế lưu trữ của discovery implementation | Kết quả phụ thuộc client, trạng thái đồng bộ và phiên bản | Mọi lời gọi `DiscoveryClient` đều có fallback thành công |
| Danh sách instance trong LoadBalancer | Cache hoặc chuỗi `ServiceInstanceListSupplier` | Có thể vẫn còn danh sách trước đó | Các địa chỉ trong danh sách vẫn sống |
| ConfigMap/Secret đã mount | Tệp trong container, do kubelet quản lý | Ứng dụng có thể còn đọc được nội dung đã chiếu | Tệp đã nhận được thay đổi mới nhất từ API |
| Biến môi trường của tiến trình | Môi trường được thiết lập khi container khởi động | Giá trị hiện có không tự biến mất do lỗi API | Một lần refresh Spring sẽ cập nhật lại môi trường container |
| Snapshot do ứng dụng quản lý | Bộ nhớ của tiến trình hoặc kho lưu riêng được thiết kế rõ ràng | Có thể dùng theo chính sách do ứng dụng đặt ra | Snapshot trong RAM sẽ tồn tại sau khi Pod bị thay thế |

Đối với ConfigMap, giá trị qua biến môi trường không tự cập nhật; volume thông thường có cơ chế cập nhật trễ và mount qua `subPath` không nhận cập nhật tự động. Các đường truyền này có hành vi khác nhau. Xem [ConfigMaps của Kubernetes](https://kubernetes.io/docs/concepts/configuration/configmap/#mounted-configmaps-are-updated-automatically).

Với Secret volume, Kubernetes cũng dùng cơ chế cập nhật nhất quán cuối cùng; Secret bắt buộc chưa có có thể ngăn container khởi động. Vì vậy, không coi việc Pod đang chạy bằng Secret đã mount là bảo đảm rằng Pod mới cũng khởi động được trong cùng sự cố. Xem [Secrets của Kubernetes](https://kubernetes.io/docs/concepts/configuration/secret/#using-secrets-as-files-from-a-pod).

### 2.1. Phân biệt dữ liệu nghiệp vụ với metadata Kubernetes

Cache service chỉ biết địa chỉ và metadata để chọn đích. Nó không chứng minh số lượng tồn kho còn đúng, quyền thanh toán còn hiệu lực hoặc một giao dịch đã hoàn tất.

Trong ví dụ:

- Có thể dùng cấu hình banner đã nạp để tiếp tục trả trang.
- Có thể thử gọi một instance `inventory-api` đã biết với timeout ngắn.
- Không được suy từ “đã biết địa chỉ inventory” thành “hàng vẫn còn”.
- Không được trả kết quả đặt hàng thành công nếu chưa có xác nhận nghiệp vụ cần thiết.

Fallback ở lớp hạ tầng phải giữ nguyên ý nghĩa của API nghiệp vụ.

## 3. Phân biệt khởi động mới với tiến trình đang chạy

### 3.1. Tiến trình đã có trạng thái hợp lệ

Ứng dụng đã hoàn tất khởi động và chấp nhận cấu hình `display-v12`. Khi lần đọc tiếp theo bị timeout, một chính sách do ứng dụng thiết kế có thể:

1. Giữ nguyên cấu hình đang có hiệu lực.
2. Ghi nhận việc mất khả năng xác nhận dữ liệu mới.
3. Tiếp tục những chức năng được phép dùng cấu hình đó.
4. Thử đồng bộ lại ở nền với nhịp hữu hạn.
5. Chặn riêng chức năng vượt giới hạn an toàn.

Chính sách này thường được gọi là sử dụng **last-known-good**, tức bản dữ liệu gần nhất đã được kiểm tra và chấp nhận. “Gần nhất” không đồng nghĩa với “vẫn đúng ở hiện tại”.

### 3.2. Tiến trình chưa từng nạp được dữ liệu

Pod mới hoặc tiến trình vừa khởi động lại có thể chưa có cấu hình bắt buộc hay snapshot discovery. Khi đó không có dữ liệu tốt trước đó để dùng.

Phân biệt ba lựa chọn triển khai:

| Dữ liệu cần lúc khởi động | Cách xử lý hợp lý |
| --- | --- |
| Cấu hình bắt buộc ảnh hưởng tính đúng đắn | Không nhận lưu lượng khi chưa có cấu hình hợp lệ; có thể dừng khởi động theo chính sách |
| Cấu hình phụ trợ có giá trị mặc định được duyệt | Khởi động với mặc định và công bố rõ nguồn cấu hình |
| Danh mục discovery chưa đồng bộ | Tuân theo yêu cầu khởi tạo của implementation; không giả lập thành đã đồng bộ |
| Secret bắt buộc chưa khả dụng | Không thay bằng mật khẩu rỗng hoặc thông tin xác thực bịa ra |

Thuộc tính `spring.cloud.kubernetes.discovery.cache-loading-timeout-seconds` được tài liệu mô tả là thời hạn khởi tạo cache discovery, có thể làm ứng dụng dừng khởi động khi vượt hạn. Nó không phải thời gian cho phép sử dụng endpoint cũ khi ứng dụng đang chạy. Xem [phụ lục thuộc tính Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

Một Pod đang sống bằng dữ liệu trong RAM và một Pod mới chưa có RAM đó có thể biểu hiện rất khác nhau. Vì thế, restart hàng loạt trong sự cố API có thể làm giảm thêm năng lực phục vụ.

## 4. Thiết kế chính sách độ cũ theo phạm vi dữ liệu

### 4.1. Ba câu hỏi cần trả lời

Với mỗi nhóm dữ liệu, xác định:

1. **Dữ liệu đã được chấp nhận chưa?** Một phản hồi có mã HTTP thành công nhưng nội dung không hợp lệ chưa phải dữ liệu dùng được.
2. **Độ cũ được tính từ bằng chứng nào?** Đọc lại chính cache của mình không tạo bằng chứng về trạng thái API.
3. **Hậu quả của việc dùng sai là gì?** Sai màu giao diện khác với sai quyền truy cập hoặc dùng credential đã bị thu hồi.

Bảng sau là **chính sách minh họa do ứng dụng đặt ra**, không phải mặc định của Spring Cloud Kubernetes.

| Nhóm dữ liệu | Khi không xác nhận được bản mới | Giới hạn minh họa | Khi vượt giới hạn |
| --- | --- | --- | --- |
| Cấu hình hiển thị không nhạy cảm | Giữ bản hợp lệ gần nhất | 30 phút | Dùng giao diện mặc định được duyệt |
| Instance của dịch vụ đọc dữ liệu | Cho phép thử endpoint đã biết | 60 giây | Từ chối thao tác phụ thuộc discovery này hoặc dùng đường dự phòng đã thiết kế |
| Cấu hình quyết định một thao tác nhạy cảm | Chỉ tiếp tục nếu hợp đồng cho phép độ trễ | Có thể bằng 0 | Chặn thao tác liên quan |
| Credential đã nạp | Chỉ dùng trong thời hạn và chính sách còn hiệu lực | Không vượt hạn của credential; có thể ngắn hơn | Ngừng thao tác cần credential đó |

Các con số phải xuất phát từ đặc điểm hệ thống. Dịch vụ thay Pod thường xuyên cần cách xử lý endpoint khác dịch vụ có địa chỉ ít biến động.

### 4.2. Phân biệt những loại thời gian

- **Thời điểm dữ liệu thay đổi:** lần cuối nội dung tài nguyên thay đổi.
- **Thời điểm xác nhận đồng bộ:** lần cuối adapter xác nhận thành công trạng thái của đúng phạm vi dữ liệu.
- **Thời điểm sử dụng:** lần cuối request đọc dữ liệu cục bộ.
- **Thời điểm phát hiện lỗi:** lần đầu ứng dụng quan sát thấy một vấn đề.

Một ConfigMap không đổi trong nhiều ngày vẫn có thể đang hoàn toàn mới nếu trạng thái của nó vừa được xác nhận. Ngược lại, một cache được request đọc liên tục vẫn có thể đã mất đồng bộ từ lâu.

Có thể tính ngân sách sử dụng dữ liệu theo:

~~~text
tuổi_xác_nhận = thời_gian_đơn_điệu_hiện_tại - mốc_xác_nhận_thành_công
được_phép_dùng = đã_có_snapshot_hợp_lệ
                và tuổi_xác_nhận <= ngân_sách_của_nghiệp_vụ
                và không_vi_phạm_điều_kiện_bảo_mật
~~~

Đồng hồ đơn điệu phù hợp để đo khoảng thời gian trong cùng tiến trình. Thời gian UTC phù hợp cho log và đối chiếu vận hành. Nếu có lưu snapshot qua lần khởi động, phải thiết kế lại cách xác định tuổi; không lưu giá trị `System.nanoTime()` để dùng ở tiến trình khác.

### 4.3. Không dùng sự im lặng làm bằng chứng lỗi

Một watch không nhận sự kiện có thể chỉ vì tài nguyên không đổi. Không có sự kiện chưa đủ để kết luận watch đã hỏng; cũng không đủ để khẳng định watch còn khỏe.

Nếu chưa có tín hiệu xác nhận đủ tin cậy, có thể áp dụng giới hạn bảo thủ tính từ lần đồng bộ đầy đủ gần nhất và chấp nhận việc từ chối sớm hơn. Nếu cần xác nhận định kỳ, thực hiện ở nền trong phạm vi nhỏ và có ngân sách; không gọi API server từ mỗi request.

## 5. Mô hình trạng thái cho khả năng sử dụng dữ liệu

Mô hình sau là thiết kế ở lớp ứng dụng, không phải danh sách trạng thái có sẵn của Spring Cloud Kubernetes.

~~~mermaid
stateDiagram-v2
    [*] --> NO_SNAPSHOT
    NO_SNAPSHOT --> CONFIRMED: Nạp đủ và kiểm tra thành công
    CONFIRMED --> DEGRADED: Mất khả năng xác nhận đồng bộ
    DEGRADED --> EXPIRED: Vượt ngân sách hoặc vi phạm chính sách
    DEGRADED --> RECOVERING: Kết nối lại được
    EXPIRED --> RECOVERING: Kết nối lại được
    RECOVERING --> CONFIRMED: Đồng bộ đủ và chấp nhận bản mới
    RECOVERING --> DEGRADED: Đồng bộ lỗi, bản cũ còn dùng được
    RECOVERING --> EXPIRED: Không có bản nào được phép dùng
~~~

| Trạng thái | Hành vi dữ liệu | Hành vi phục vụ |
| --- | --- | --- |
| `NO_SNAPSHOT` | Chưa có bản hợp lệ | Không nhận thao tác bắt buộc phải có dữ liệu này |
| `CONFIRMED` | Có xác nhận phù hợp với phạm vi và thời hạn | Phục vụ theo chức năng đã công bố |
| `DEGRADED` | Có bản cũ còn được phép dùng | Phục vụ có giới hạn và ghi nhận chế độ suy giảm |
| `EXPIRED` | Bản còn trong bộ nhớ nhưng không còn được phép sử dụng | Từ chối hoặc chuyển sang phương án nghiệp vụ được duyệt |
| `RECOVERING` | Đang xây lại bằng chứng về trạng thái hiện hành | Chưa tuyên bố dữ liệu mới chỉ vì TCP đã kết nối |

Cần trạng thái riêng cho từng phạm vi, chẳng hạn danh mục `inventory-api` trong namespace `shop` và cấu hình banner của `order-api`. Một lỗi cập nhật banner không nên tự động làm vô hiệu mọi dữ liệu trong ứng dụng.

Không nhất thiết xóa dữ liệu khỏi RAM khi hết ngân sách. Có thể giữ nó để chẩn đoán nhưng phải chặn việc sử dụng. Ngược lại, nếu có yêu cầu xóa bí mật hoặc thu hồi quyền, phải áp dụng chính sách đó ngay khi có bằng chứng tương ứng.

## 6. ConfigMap, Secret và Configuration Watcher

### 6.1. Cấu hình đang có hiệu lực và lỗi đọc bản mới

Giả sử `order-api` đang dùng:

~~~yaml
app:
  display:
    version: display-v12
    show-recommendations: true
~~~

Phiên bản `display-v12` là nhãn nghiệp vụ minh họa để quan sát cấu hình đã áp dụng. Nó không phải thuộc tính quản lý phiên bản do Spring Cloud Kubernetes tự cấp.

Một cơ chế cập nhật do ứng dụng thiết kế nên tách ba bước:

~~~text
đọc ứng viên -> kiểm tra toàn bộ ứng viên -> công bố bản được chấp nhận
~~~

Nếu đọc bị timeout, giữ nguyên bản đang có hiệu lực theo chính sách. Nếu ứng viên có giá trị không hợp lệ, không công bố một nửa cấu hình. Với nhiều trường phải thay đổi cùng nhau, có thể bind vào một đối tượng bất biến, kiểm tra ràng buộc và thay tham chiếu nguyên tử.

Đây là yêu cầu thiết kế của ứng dụng. Không mặc định rằng mọi bean, mọi lần refresh Spring hoặc mọi lỗi bind đều tự rollback trọn vẹn về bản cũ. Nếu dựa vào refresh có sẵn, cần xác định chính xác những bean nào thay đổi và hành vi khi lỗi của phiên bản đang dùng.

### 6.2. Fail-fast giải quyết giai đoạn nạp cấu hình

Spring Cloud Kubernetes cung cấp `spring.cloud.kubernetes.config.fail-fast` cho lỗi nạp ConfigMap lúc khởi động và các thuộc tính `spring.cloud.kubernetes.config.retry.*`. Retry cần dependency tương ứng với nhánh phiên bản. Xem [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html).

Ví dụ cho đường nạp ConfigMap qua API khi dự án đã cấu hình dependency retry phù hợp:

~~~yaml
spring:
  cloud:
    kubernetes:
      config:
        fail-fast: true
        retry:
          enabled: true
          max-attempts: 4
          initial-interval: 1000
          multiplier: 2.0
          max-interval: 5000
~~~

Các giá trị trên là lựa chọn minh họa. Chúng giới hạn số lần thử và khoảng chờ của đường nạp tương ứng, không bảo đảm tổng thời gian khởi động vì mỗi lần gọi còn có timeout riêng.

`fail-fast: false` không tạo kho cấu hình offline bền vững. Retry khi khởi động cũng không phải cơ chế giữ endpoint cũ, gia hạn credential hoặc bảo đảm lần refresh thất bại sẽ giữ nguyên toàn bộ bean.

Tên thuộc tính và dependency phải đối chiếu theo Spring Cloud BOM của dự án. Ví dụ được tham chiếu theo tài liệu nhánh 5.1; không sao chép dependency của nhánh này vào dự án nhánh 3.x mà chưa kiểm tra tương thích.

### 6.3. Watcher thông báo thay đổi, không bảo đảm ứng dụng đã áp dụng

Configuration Watcher có thể gửi thông báo refresh qua HTTP hoặc Spring Cloud Bus. Khi dùng HTTP, đường mặc định là `/actuator/refresh`; với cấu hình mount volume còn có độ trễ truyền tệp cần tính đến. Xem [Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Trong tình huống mất kết nối, cần phân biệt:

- Watcher chưa thấy thay đổi.
- Watcher thấy thay đổi nhưng chưa thông báo được.
- Ứng dụng nhận thông báo nhưng chưa đọc được nguồn cấu hình.
- Ứng dụng đọc được nhưng chưa áp dụng thành công.
- Các replica đã áp dụng những phiên bản khác nhau.

Đây là các điểm lỗi có thể xảy ra trong chuỗi xử lý. Thông báo “đã gửi refresh” chưa đủ để xác nhận trạng thái cuối của mọi replica.

Khi phục hồi, quy trình vận hành nên đọc phiên bản cấu hình **thực sự đang có hiệu lực** ở từng replica. Nếu còn chênh lệch, thực hiện đối soát và refresh hoặc rollout có kiểm soát. Không xây nghiệp vụ dựa trên giả định mọi sự kiện trung gian đều được phát lại, đúng một lần và đúng thứ tự sau một lần gián đoạn.

### 6.4. Secret cần chính sách riêng

Tích hợp Secrets PropertySource có thể dùng nguồn mount hoặc API; đọc Secret qua API cần được bật và phân quyền phù hợp. Tài liệu khuyến nghị hạn chế quyền đọc và cân nhắc mount volume. Xem [Secrets PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/secrets-propertysource.html).

Trong chính sách của `order-api`:

- Không ghi giá trị Secret vào log, response, nhãn metrics hoặc snapshot chẩn đoán.
- Không kéo dài thời hạn credential chỉ vì API server đang lỗi.
- Nếu backend từ chối thông tin xác thực, không diễn giải đó thành lỗi discovery rồi thử vô hạn.
- Nếu thao tác cần xác nhận quyền mới mà không còn cách xác nhận, từ chối thao tác đó.
- Không tự ghi Secret ra đĩa để vượt qua restart; lưu bền bí mật cần thiết kế bảo vệ, vòng đời và thu hồi riêng.

## 7. DiscoveryClient và Spring Cloud LoadBalancer

### 7.1. Cache discovery phụ thuộc implementation

Spring Cloud Kubernetes hỗ trợ Fabric8, Kubernetes Java Client và HTTP DiscoveryClient. Tài liệu mô tả việc dùng lister/cache được nạp bất đồng bộ; HTTP client còn phụ thuộc DiscoveryServer. Vì vậy, phải xác định đúng đường xử lý trước khi kết luận mất API có ảnh hưởng thế nào. Xem [DiscoveryClient for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Với phiên bản và client cụ thể, cần quan sát bốn tình huống:

1. Khởi tạo khi chưa từng có dữ liệu.
2. Đọc instance khi đã có dữ liệu và watch bị ngắt.
3. Đồng bộ lại khi API trở về.
4. Nhận danh sách hợp lệ nhưng không còn instance.

Không bọc mọi ngoại lệ thành danh sách rỗng. Ngoại lệ nghĩa là chưa đọc được trạng thái; danh sách rỗng thành công nghĩa là ở phạm vi đã truy vấn không có đích phù hợp. Hai trường hợp cần chính sách khác nhau.

Nếu adapter vừa xác nhận một danh sách rỗng hợp lệ, nó phải thay thế danh sách cũ tương ứng. Không phục hồi các IP trước đó chỉ vì “danh sách cũ có phần tử nên trông tốt hơn”.

### 7.2. Cache LoadBalancer không thay cho chính sách độ cũ

Spring Cloud LoadBalancer có thể cache danh sách instance và cho cấu hình TTL; có nhiều lớp cache thì phải xét khả năng dữ liệu bị giữ lâu hơn dự kiến. Xem [LoadBalancer caching](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html#loadbalancer-caching).

~~~text
request
  -> LoadBalancer cache
  -> DiscoveryClient
  -> informer/lister hoặc DiscoveryServer
  -> Kubernetes API
~~~

Ví dụ suy luận: cache LoadBalancer hết TTL rồi đọc lại từ một informer đã mất kết nối. Danh sách nhận được vẫn có thể là dữ liệu cũ. TTL của cache ngoài chỉ giới hạn tuổi entry trong lớp đó, không chứng minh tuổi dữ liệu tính từ API.

Tương tự, tăng TTL để giảm gọi discovery không tự tạo cơ chế “khi lỗi thì phục vụ bản cũ”. Muốn hành vi đó, phải có hợp đồng và điểm tích hợp rõ ràng.

### 7.3. Endpoint cũ vẫn phải chịu kiểm soát ở đường gọi

Giả sử snapshot còn `10.42.1.8:8080`, nhưng Pod đó đã kết thúc:

- Đặt connect timeout, response timeout và deadline tổng phù hợp.
- Giới hạn retry; các lớp HTTP client, LoadBalancer và nghiệp vụ không được cộng dồn retry ngoài dự kiến.
- Có thể loại đích lỗi tạm thời ở lớp chọn instance nếu kiến trúc hỗ trợ.
- Chỉ thử lại thao tác ghi khi đã bảo đảm tính idempotent hoặc có khóa chống trùng nghiệp vụ.
- Không giữ request chờ API server khôi phục trước khi trả lỗi có kiểm soát.

Địa chỉ cũ còn trả lời cũng không tự chứng minh đúng danh tính dịch vụ: IP có thể được tái sử dụng. Những đường gọi cần bảo đảm danh tính phải dựa vào cơ chế xác thực thích hợp, chẳng hạn xác minh TLS và thông tin nhận diện dịch vụ.

### 7.4. Chọn mức phụ thuộc Kubernetes thực sự cần

Nếu ứng dụng chỉ cần gọi một Kubernetes Service đã biết, có thể cân nhắc URL DNS ổn định, chẳng hạn `http://inventory-api.shop.svc.cluster.local:8080`, bằng HTTP client thông thường. Service cung cấp cách truy cập tập Pod qua một điểm truy cập ổn định. Xem [Kubernetes Service](https://kubernetes.io/docs/concepts/services-networking/service/).

Trong mô hình đó, request nghiệp vụ không cần tự truy vấn Kubernetes API. Đây là cách giảm phụ thuộc trực tiếp ở ứng dụng; nó vẫn cần DNS, mạng và trạng thái định tuyến của cluster hoạt động.

Spring Cloud Kubernetes LoadBalancer phân biệt `POD` và `SERVICE`. Chuyển sang `SERVICE` không đồng nghĩa đã bỏ mọi thao tác tìm Service qua Kubernetes. Xem [LoadBalancer for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/load-balancer.html).

Từ đó có thể suy ra: mất API tạm thời chưa nhất thiết làm hỏng mọi kết nối đã có, nhưng khả năng nhận thay đổi mới của endpoint hoặc định tuyến có thể bị ảnh hưởng. Không dùng một thử nghiệm request thành công để bảo đảm toàn bộ data plane sẽ tiếp tục đúng khi cluster thay đổi.

## 8. Ví dụ Java: giữ snapshot với ngân sách sử dụng

Đoạn mã Java 17 sau minh họa **chính sách của ứng dụng**, không phải lớp có sẵn của Spring Cloud Kubernetes. Nó cũng không tự gắn vào DiscoveryClient, PropertySource hay Configuration Watcher.

~~~java
import java.time.Duration;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

public final class LastKnownGood<T> {

    public record Snapshot<T>(
            T value,
            String version,
            long confirmedAtNanos) {
    }

    private final AtomicReference<Snapshot<T>> current =
            new AtomicReference<>();

    // Chỉ gọi sau khi adapter đã xác nhận đúng phạm vi dữ liệu
    // và ứng dụng đã kiểm tra toàn bộ candidate.
    public void acceptConfirmed(T candidate, String version) {
        Objects.requireNonNull(candidate, "candidate");
        Objects.requireNonNull(version, "version");

        current.set(new Snapshot<>(
                candidate,
                version,
                System.nanoTime()));
    }

    // Đọc snapshot không làm mới confirmedAtNanos.
    public Optional<Snapshot<T>> readWithin(Duration maxAge) {
        Objects.requireNonNull(maxAge, "maxAge");
        if (maxAge.isNegative()) {
            throw new IllegalArgumentException("maxAge must not be negative");
        }

        Snapshot<T> snapshot = current.get();
        if (snapshot == null) {
            return Optional.empty();
        }

        long ageNanos =
                System.nanoTime() - snapshot.confirmedAtNanos();

        if (ageNanos > maxAge.toNanos()) {
            return Optional.empty();
        }

        return Optional.of(snapshot);
    }

    // Dùng khi chính sách yêu cầu vô hiệu hóa ngay,
    // chẳng hạn đã nhận được bằng chứng thu hồi.
    public void invalidate() {
        current.set(null);
    }
}
~~~

Để dùng lớp này đúng ý nghĩa:

1. Adapter phải công bố snapshot bất biến. Với danh sách, có thể sao chép bằng `List.copyOf` trước khi chấp nhận.
2. Adapter phải xử lý tuần tự việc chấp nhận/vô hiệu hóa hoặc có cơ chế chống kết quả bất đồng bộ đến muộn ghi đè trạng thái mới. `AtomicReference` chỉ bảo đảm thay tham chiếu nguyên tử, không giải quyết thứ tự nghiệp vụ.
3. Chỉ gọi `acceptConfirmed` khi có bằng chứng phù hợp về nguồn. Gọi `DiscoveryClient.getInstances()` thành công từ cache chưa đủ để đặt mốc “API vừa được xác nhận”.
4. Timeout hoặc lỗi mạng không gọi `acceptConfirmed` và không tự xóa snapshot cũ.
5. Danh sách rỗng đã được xác nhận là candidate hợp lệ; nếu không còn endpoint thì lớp gọi dịch vụ vẫn phải từ chối vì không có đích.
6. Các điều kiện như hạn credential và thu hồi quyền phải được kiểm tra thêm. Giới hạn tuổi trong ví dụ chỉ giải quyết một phần của chính sách.
7. Không dùng giá trị `version` như số tăng dần nếu đó là `resourceVersion` của Kubernetes. Hãy coi nó là token phục vụ đối chiếu; việc chấp nhận thứ tự thuộc trách nhiệm adapter.

Lớp trên không cung cấp tín hiệu sức khỏe watch. Nếu implementation đang dùng không cho truy cập bằng chứng đồng bộ cần thiết, phải bổ sung adapter quan sát phù hợp hoặc áp dụng chính sách bảo thủ. Không bịa một API kiểm tra độ mới chỉ để hoàn thành đoạn tích hợp.

Bảng diễn giải khi ngân sách là 60 giây:

| Tình huống | Kết quả chính sách |
| --- | --- |
| Chưa có lần chấp nhận nào | Không có snapshot dùng được |
| Có snapshot được xác nhận cách đây 20 giây, lần đọc mới timeout | Có thể dùng snapshot nếu các điều kiện khác vẫn thỏa |
| Request đọc snapshot liên tục trong 90 giây nhưng không có xác nhận mới | Snapshot không được tự gia hạn |
| Nhận kết quả rỗng được xác nhận sau lần có hai endpoint | Snapshot hiện hành là rỗng |
| Nhận ứng viên cấu hình lỗi validation | Không gọi `acceptConfirmed`; quyết định dùng bản trước theo ngân sách còn lại |
| Nhận bằng chứng buộc vô hiệu hóa | Gọi luồng vô hiệu hóa; không chờ hết TTL |

## 9. Liveness, readiness và sức khỏe Pod

Liveness trả lời tiến trình có cần khởi động lại hay không. Readiness trả lời instance có sẵn sàng nhận lưu lượng theo hợp đồng đã định hay không.

Spring Boot khuyến cáo liveness không phụ thuộc hệ thống bên ngoài; các dependency bổ sung trong readiness cần được lựa chọn theo vai trò thực tế. Xem [Kubernetes probes trong Spring Boot](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

Ví dụ bật hai nhóm probe cơ bản:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Phần container, giả sử ứng dụng và Actuator phục vụ ở cổng 8080:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Những giá trị probe này là ví dụ. Nếu ứng dụng có giai đoạn khởi động dài, cần thiết kế thêm startup probe và thời hạn phù hợp.

Cấu hình trên **chưa tự kiểm tra snapshot**. Ứng dụng cần coordinator theo dõi dữ liệu bắt buộc, sau đó cập nhật `ReadinessState` qua cơ chế availability của Spring Boot hoặc cung cấp health contributor riêng và đưa nó vào nhóm readiness. Coordinator phải xét tất cả điều kiện cần để nhận lưu lượng trước khi công bố sẵn sàng.

Chính sách minh họa:

| Tình huống | Liveness | Readiness hoặc hành vi endpoint |
| --- | --- | --- |
| API lỗi, cấu hình phụ trợ cũ còn hợp lệ | Giữ theo sức khỏe nội tại | Có thể tiếp tục nhận lưu lượng |
| API lỗi, chưa từng có cấu hình bắt buộc | Không coi lỗi API là lý do trực tiếp để restart | Chưa nhận lưu lượng |
| Snapshot cho một chức năng phụ đã hết hạn | Không restart chỉ vì điều này | Có thể từ chối riêng chức năng đó |
| Dữ liệu bắt buộc cho mọi request không còn dùng được | Không restart chỉ vì mất đồng bộ | Từ chối lưu lượng theo hợp đồng |
| Deadlock hoặc lỗi nội tại khiến tiến trình không phục vụ | Đánh giá theo kiểm tra nội tại | Thường không sẵn sàng |

Readiness là tín hiệu, không phải hàng rào duy nhất. Nếu đường cập nhật trạng thái endpoint qua control plane đang gián đoạn, việc loại Pod khỏi tuyến có thể chậm. Ứng dụng vẫn cần chặn thao tác không còn an toàn ngay trong đường xử lý request.

Đừng trỏ probe tới toàn bộ `/actuator/health` rồi vô tình đưa sức khỏe discovery hoặc API server vào liveness. Việc cần restart phải có căn cứ là trạng thái nội tại của tiến trình.

## 10. Đồng bộ lại sau khi kết nối phục hồi

“Gọi được API” và “đã có dữ liệu hiện hành” là hai mốc khác nhau.

Trình tự phục hồi nên được thiết kế như sau:

1. Kết nối lại với timeout và backoff phù hợp; tránh mọi replica thử liên tục cùng lúc.
2. Hoàn tất cơ chế đồng bộ lại của client cho đúng namespace, selector và loại tài nguyên.
3. Xử lý cả tài nguyên đã xóa và kết quả rỗng.
4. Kiểm tra tính hợp lệ của dữ liệu trước khi chấp nhận.
5. Công bố trạng thái mới theo đơn vị nhất quán của ứng dụng.
6. Đối soát cache phụ thuộc và phiên bản cấu hình đang dùng.
7. Chỉ khôi phục đầy đủ chức năng khi các điều kiện nghiệp vụ đã thỏa.

Với watch Kubernetes, lịch sử có thể không còn chứa `resourceVersion` mà client yêu cầu. Khi nhận `410 Gone`, client phải bỏ trạng thái watch/cache không còn hợp lệ, lấy lại trạng thái bằng GET/LIST phù hợp và bắt đầu watch từ phiên bản mới. Không bỏ qua lỗi rồi giả định đã nhận đủ thay đổi. Xem [Kubernetes API concepts](https://kubernetes.io/docs/reference/using-api/api-concepts/#efficient-detection-of-changes).

Nếu ứng dụng giữ last-known-good riêng để phục vụ trong lúc xây lại cache, phải tách rõ hai lớp:

~~~text
cache đồng bộ với API:
    có thể cần xây lại để lấy trạng thái đúng

snapshot nghiệp vụ đã chấp nhận:
    chỉ còn được phục vụ trong ngân sách và chính sách cho phép
~~~

Không chèn snapshot cũ trở lại cache đồng bộ để làm như việc relist đã thành công. Việc giữ bản phục vụ cũ cũng không được cản trở quyết định vô hiệu hóa theo bảo mật.

Một tập sự kiện riêng lẻ chưa chắc đủ xác nhận toàn bộ snapshot. Ví dụ, nhận thay đổi của Service A không tự làm mới bằng chứng về Service B. `BOOKMARK` đánh dấu tiến độ watch tới một `resourceVersion`, nhưng Kubernetes không bảo đảm gửi bookmark theo một chu kỳ cố định. Không đặt timeout sống/chết chỉ dựa trên khoảng cách giữa hai bookmark.

Khi dùng informer do thư viện quản lý, ưu tiên cơ chế reconnect và relist của thư viện. Không xây thêm một vòng watch thủ công song song chỉ để giải quyết cùng một sự cố. Phần ứng dụng cần bổ sung là chính sách phục vụ, quan sát và điều kiện chấp nhận dữ liệu.

## 11. Phân loại lỗi trước khi retry

| Dấu hiệu | Hướng phân tích | Hành động |
| --- | --- | --- |
| Connect timeout, connection refused, ngắt kết nối | Mạng hoặc đích API có vấn đề | Thử lại có backoff; dùng snapshot theo ngân sách |
| `401 Unauthorized` | Thông tin xác thực không được chấp nhận | Kiểm tra token và luồng cập nhật credential |
| `403 Forbidden` | Thiếu quyền cho tài nguyên hoặc phạm vi | Sửa RBAC đúng yêu cầu; không tăng retry để thay quyền |
| Lỗi chứng thư/TLS | CA, tên máy chủ hoặc chuỗi tin cậy | Kiểm tra cấu hình; không tắt xác minh TLS |
| `410 Gone` trên watch | Phiên bản lịch sử không còn dùng được | Để client xây lại đồng bộ đúng giao thức |
| Danh sách rỗng thành công | Có thể không có đích phù hợp hoặc truy vấn sai phạm vi | Kiểm tra namespace/selector; không biến thành lỗi mạng |
| Dữ liệu đọc được nhưng validation thất bại | Nguồn cấu hình có lỗi nội dung | Từ chối ứng viên và báo lỗi rõ ràng |

Các dấu hiệu trên định hướng điều tra; không thay cho việc đọc chi tiết lỗi và xác định thành phần đã trả phản hồi.

Đối với RBAC, cấp quyền theo đường truy cập đang dùng:

- Discovery có thể cần `get/list/watch` cho `services` và tài nguyên endpoint tương ứng.
- Nếu dùng EndpointSlice, tài nguyên thuộc API group `discovery.k8s.io`; không cấu hình nhầm thành group lõi.
- Chỉ thêm quyền đọc Pod khi tính năng metadata hoặc đường xử lý thực tế cần tới.
- Việc đọc ConfigMap và Secret có phạm vi quyền riêng. Không cấp quyền Secret chỉ để chữa lỗi đọc Service.
- Thử quyền với đúng ServiceAccount, namespace và động từ mà client sử dụng.

Ví dụ chẩn đoán, chạy từ tài khoản quản trị có quyền impersonation trong môi trường lab:

~~~powershell
kubectl auth can-i list services --as=system:serviceaccount:resilience-lab:catalog-reader -n resilience-lab
kubectl auth can-i watch services --as=system:serviceaccount:resilience-lab:catalog-reader -n resilience-lab
kubectl auth can-i list endpointslices.discovery.k8s.io --as=system:serviceaccount:resilience-lab:catalog-reader -n resilience-lab
~~~

Các lệnh này kiểm tra quyền, không mô phỏng mất mạng và không chứng minh watch đang hoạt động.

## 12. Quan sát khả năng phục vụ bằng dữ liệu cũ

Chỉ đếm số lỗi API chưa đủ. Cần biết ứng dụng còn dùng dữ liệu nào và được dùng đến bao giờ.

Các tên dưới đây là **metrics đề xuất của ứng dụng**, không phải tên metrics mặc định của Spring Cloud Kubernetes.

| Metric đề xuất | Ý nghĩa |
| --- | --- |
| `k8s_snapshot_initialized` | Phạm vi dữ liệu đã từng có bản hợp lệ hay chưa |
| `k8s_snapshot_confirmation_age_seconds` | Tuổi kể từ xác nhận thành công theo hợp đồng adapter |
| `k8s_snapshot_reconcile_failures_total` | Số lần đồng bộ thất bại, phân loại lỗi ở mức hữu hạn |
| `k8s_snapshot_stale_served_total` | Số lần phục vụ bằng snapshot trong chế độ suy giảm |
| `k8s_snapshot_rejected_total` | Số lần bị chặn do hết ngân sách hoặc vi phạm chính sách |
| `k8s_snapshot_recovery_duration_seconds` | Thời gian từ phát hiện sự cố tới khi dữ liệu được chấp nhận lại |

Khi chưa khởi tạo, không xuất tuổi bằng 0 làm người xem tưởng dữ liệu rất mới; dùng tín hiệu initialized riêng hoặc không xuất mẫu tuổi.

Gắn nhãn theo phạm vi ổn định, chẳng hạn loại nguồn và tên dịch vụ trong danh sách giới hạn. Tránh dùng `resourceVersion`, IP thay đổi liên tục hoặc giá trị Secret làm nhãn.

Log nên thể hiện chuyển trạng thái, chẳng hạn:

~~~text
scope=inventory state=DEGRADED reason=api_timeout confirmationAgeSeconds=18
scope=inventory state=EXPIRED reason=age_budget_exceeded confirmationAgeSeconds=61
scope=inventory state=CONFIRMED reason=reconcile_completed instanceCount=1
~~~

Giới hạn log lỗi lặp lại. Cảnh báo quan trọng là hết ngân sách dữ liệu bắt buộc hoặc nhiều replica cấu hình lệch nhau kéo dài; không nhất thiết phát cảnh báo nghiêm trọng cho mỗi lần watch reconnect ngắn.

## 13. Thực hành gián đoạn và phục hồi trong lab

Mục đích là quan sát hành vi thật của **đúng phiên bản, client và chuỗi cache** sẽ triển khai. Các bước dưới đây là hướng dẫn lab; không giả định bài viết này đã chạy một cluster.

### 13.1. Chuẩn bị đường kiểm thử có thể kiểm soát

Trong namespace lab riêng:

1. Chạy `order-api` và ít nhất hai instance `inventory-api`.
2. Ghi nhận phiên bản Spring Cloud Kubernetes, client sử dụng, tài nguyên endpoint và các lớp cache.
3. Đặt một ConfigMap phụ trợ có trường phiên bản ứng dụng quan sát được.
4. Quan sát được danh sách instance ở ứng dụng, cấu hình có hiệu lực, số lần restart và các chỉ số độ cũ.
5. Chuẩn bị fault injector hoặc proxy riêng cho kết nối Kubernetes client của ứng dụng; nếu kiểm tra Watcher thì kiểm soát đường kết nối của Watcher riêng.

Cơ chế gây lỗi phải chặn đúng đường tới API, bao gồm kết nối watch đang mở, mà vẫn giữ được DNS, lưu lượng nghiệp vụ và đường quản trị phục vụ phục hồi. Cách thực hiện phụ thuộc CNI và Kubernetes client; không giả định một NetworkPolicy chặn `kubernetes.default.svc` sẽ bao phủ mọi đường tới API.

Không dừng API server của cluster dùng chung. Trước khi kích hoạt lỗi, xác nhận đã có cách gỡ lỗi độc lập với chính đường kết nối sắp bị chặn.

### 13.2. Quan sát trước, trong và sau sự cố

Có thể dùng các lệnh đọc sau từ máy quản trị còn truy cập được cluster:

~~~powershell
kubectl -n resilience-lab get pods -l app=order-api
kubectl -n resilience-lab get endpointslices -l kubernetes.io/service-name=inventory-api
kubectl -n resilience-lab logs deployment/order-api --since=5m
~~~

Đồng thời, từ kênh truy cập ứng dụng đã chuẩn bị, gọi endpoint nghiệp vụ và hai endpoint probe. Không dùng riêng danh sách EndpointSlice từ máy quản trị để kết luận rằng ứng dụng đã thấy bản mới.

Tiến hành theo bảng:

| Giai đoạn | Thao tác trong lab | Điều cần ghi nhận |
| --- | --- | --- |
| Bình thường | Xác nhận cấu hình và hai instance | Mốc xác nhận, phiên bản đã áp dụng, request thành công |
| Mất API từ ứng dụng | Kích hoạt lỗi đúng đường kết nối | Lỗi nền xuất hiện; tiến trình không restart chỉ do API lỗi |
| Còn ngân sách | Gọi các chức năng được phép dùng dữ liệu cũ | Có thể phục vụ suy giảm; mốc xác nhận không tăng chỉ vì có request |
| Quá ngân sách | Giữ lỗi qua giới hạn đã đặt | Thao tác liên quan bị chặn đúng chính sách |
| Thay đổi phía cluster | Từ kênh quản trị, cập nhật ConfigMap phụ trợ và thay một Pod đích | Phân biệt trạng thái thật với trạng thái ứng dụng còn biết |
| Phục hồi | Gỡ fault injector | Có đồng bộ lại, loại endpoint cũ và xác nhận cấu hình có hiệu lực |
| Khởi động lạnh | Dùng một instance thử nghiệm chưa có snapshot, lặp lại lỗi | Hành vi thiếu dữ liệu ban đầu khác tiến trình đã chạy |

Nếu đường cập nhật cấu hình đi qua Watcher, thực hiện riêng tình huống Watcher bị cô lập trong khi ứng dụng vẫn còn truy cập API và tình huống ngược lại. Hai lỗi không có cùng đường truyền.

Sau thử nghiệm, gỡ toàn bộ fault injection và đối chiếu trạng thái của từng replica. Không kết luận đã phục hồi chỉ vì số lỗi mới giảm.

### 13.3. Tiêu chí quan sát đạt yêu cầu

- Request có thời hạn hữu hạn, không treo chờ API phục hồi.
- Không có vòng lặp restart chỉ vì mất API.
- Không đổi dữ liệu lỗi thành danh sách rỗng giả.
- Dữ liệu cũ không được gia hạn bởi việc đọc cache.
- Danh sách rỗng đã xác nhận thay thế được danh sách có endpoint.
- Chức năng nhạy cảm bị chặn theo chính sách của nó.
- Sau phục hồi, ứng dụng không giữ mãi endpoint đã bị xóa.
- Phiên bản cấu hình có hiệu lực được xác minh ở từng replica.
- Bí mật không xuất hiện trong dữ liệu quan sát.

## 14. Những quyết định cần mang vào thiết kế triển khai

Trước khi dựa vào dữ liệu đã có, nhóm triển khai cần chốt rõ:

1. Nguồn nào là bắt buộc lúc khởi động và nguồn nào có mặc định được duyệt?
2. Ai xác nhận độ mới cho từng snapshot và bằng chứng đó có thực sự đi tới nguồn hay chỉ đọc cache?
3. Ngân sách dữ liệu cũ cho từng chức năng là bao nhiêu?
4. Trường hợp nào phải vô hiệu hóa ngay dù snapshot còn rất mới?
5. Khi hết ngân sách, chặn từng thao tác hay rút cả instance khỏi phục vụ?
6. Client chịu trách nhiệm reconnect/relist ra sao và ứng dụng quan sát nó bằng cách nào?
7. Sau phục hồi, ai xác minh trạng thái hiện hành và cấu hình đã áp dụng ở mọi replica?
8. Có thật sự cần DiscoveryClient và LoadBalancer ở ứng dụng, hay Kubernetes Service cùng DNS đã đáp ứng đủ nhu cầu?

Khả năng tiếp tục phục vụ trong sự cố API đến từ ranh giới dữ liệu và hợp đồng sử dụng rõ ràng. Một bản cấu hình đang có hiệu lực, một danh sách instance cũ và một credential còn hạn là ba loại bằng chứng khác nhau; mỗi loại cần chính sách sử dụng và phục hồi riêng.
