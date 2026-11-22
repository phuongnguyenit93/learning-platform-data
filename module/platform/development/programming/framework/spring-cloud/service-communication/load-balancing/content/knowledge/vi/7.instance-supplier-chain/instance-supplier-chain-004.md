# Ảnh hưởng của thứ tự decorator đến danh sách đầu ra

Spring Cloud LoadBalancer không nhất thiết lấy nguyên danh sách instance từ service registry rồi chọn ngẫu nhiên hoặc Round Robin. Trước khi chọn đích, framework có thể đưa danh sách qua nhiều lớp **ServiceInstanceListSupplier**: lấy instance từ discovery, cache, kiểm tra health, ưu tiên zone, áp dụng hint, xử lý sticky session hoặc tránh instance vừa lỗi khi retry. Các lớp bổ sung này thường được gọi là **decorator**.

Một decorator nhận một supplier khác làm **delegate**, đọc danh sách do delegate trả về rồi tạo danh sách đầu ra theo quy tắc của nó. Vì vậy, **thứ tự decorator có thể thay đổi tập instance, thứ tự phần tử, thời điểm cập nhật và thậm chí ngữ cảnh request còn được truyền xuống các lớp bên trong hay không**.

Bài học đi sâu vào sự khác nhau giữa **thứ tự khai báo builder**, **thứ tự các lớp thực thi**, và **thứ tự biến đổi danh sách**. Mục tiêu là thiết kế chuỗi cung cấp bản sao đúng cho Spring Cloud LoadBalancer khi dùng RestClient, WebClient hoặc OpenFeign, đặc biệt lúc có cache, health check và định tuyến theo yêu cầu.

## 1. ServiceInstanceListSupplier và mô hình decorator

LoadBalancer cần danh sách đối tượng **ServiceInstance** của một service ID. Các instance có thể đến từ DiscoveryClient, ReactiveDiscoveryClient hoặc một nguồn tùy chỉnh. ServiceInstanceListSupplier cung cấp đầu vào này cho thuật toán chọn đích.

Hai phương thức quan trọng của interface là:

~~~java
Flux<List<ServiceInstance>> get();

Flux<List<ServiceInstance>> get(Request request);
~~~

Điểm cần nhớ:

- Mỗi lần phát của Flux là **một danh sách instance**. Không phải mỗi ServiceInstance được phát thành một phần tử riêng của Flux.
- Phương thức có Request cho phép một decorator dựa trên hint, sticky session, retry hoặc thông tin ngữ cảnh khác.
- Một decorator có thể lọc phần tử, sắp xếp lại thứ tự, nhân trọng số, thay đổi tần suất phát hoặc dùng kết quả đã cache.
- **RoundRobinLoadBalancer** hoặc **RandomLoadBalancer** chọn từ danh sách cuối cùng; bản thân thuật toán chọn không sửa được instance đã bị decorator loại trước đó.

Ví dụ một chuỗi:

~~~mermaid
flowchart LR
    A["Discovery supplier"] --> B["Caching decorator"]
    B --> C["ZonePreference decorator"]
    C --> D["HintBased decorator"]
    D --> E["RoundRobin LoadBalancer"]
~~~

Mỗi mũi tên biểu thị dữ liệu danh sách đi từ delegate bên trong ra decorator bên ngoài. Với cấu hình trên, một lần lựa chọn được hiểu là: **discovery → cache → zone preference → hint filter → thuật toán chọn instance**.

## 2. Thứ tự builder và thứ tự xử lý không giống nhau khi đọc mã

Spring Cloud cung cấp builder để tạo chuỗi:

~~~java
ServiceInstanceListSupplier supplier =
        ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .withHints()
                .build(context);
~~~

Lệnh builder được viết từ nguồn sang các decorator bên ngoài. Khi tạo xong, sơ đồ quan hệ delegate có dạng:

~~~text
HintBasedServiceInstanceListSupplier
  └── ZonePreferenceServiceInstanceListSupplier
        └── CachingServiceInstanceListSupplier
              └── DiscoveryClientServiceInstanceListSupplier
~~~

Nhìn từ LoadBalancer, lời gọi vào supplier ngoài cùng diễn ra theo chiều **Hint → Zone → Cache → Discovery** để lấy dữ liệu. Khi dữ liệu trở ra, phép biến đổi lại diễn ra theo chiều **Discovery → Cache → Zone → Hint**.

Đây là nguồn gây nhầm phổ biến: đoạn code ghi **withZonePreference()** trước **withHints()**, nhưng Hint là decorator ngoài cùng và **áp dụng trên danh sách đã qua Zone**.

Có thể mô hình hóa bằng hàm:

- **D()**: trả danh sách từ discovery.
- **C(L)**: dùng cache để cung cấp danh sách L.
- **Z(L)**: ưu tiên instance thuộc zone được cấu hình.
- **H(L, r)**: lọc theo hint trong request r hoặc hint mặc định.

Chuỗi trên tương ứng:

\[
L_{\text{final}}(r) = H(Z(C(D())),r)
\]

Đổi thứ tự hai decorator thành:

~~~java
ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withCaching()
        .withHints()
        .withZonePreference()
        .build(context);
~~~

ta sẽ có:

\[
L_{\text{final}}(r) = Z(H(C(D()),r))
\]

Không được mặc định rằng hai biểu thức trên tương đương. Chúng chỉ cho cùng đầu ra trong một số điều kiện dữ liệu cụ thể.

## 3. Các loại decorator và tác động lên danh sách

| Loại supplier | Tác động chính | Có phụ thuộc Request? | Điểm cần chú ý về thứ tự |
| --- | --- | --- | --- |
| DiscoveryClientServiceInstanceListSupplier | Lấy danh sách từ discovery blocking | Thường không | Là nguồn đầu chuỗi |
| CachingServiceInstanceListSupplier | Cache danh sách theo service ID | Không nên phụ thuộc vào Request | Nên đặt ngay sau nguồn discovery |
| HealthCheckServiceInstanceListSupplier | Duy trì danh sách instance vượt qua health check | Không nên phụ thuộc vào Request | Nên đặt ngay sau nguồn discovery, thường thay cho cache thường |
| ZonePreferenceServiceInstanceListSupplier | Ưu tiên instance cùng zone | Thường dùng cấu hình zone | Có fallback khi không thấy instance cùng zone |
| HintBasedServiceInstanceListSupplier | Lọc theo metadata hint | Có thể đọc hint từ Request | Đặt ngoài cache/health để giữ ngữ cảnh request |
| SameInstancePreferenceServiceInstanceListSupplier | Ưu tiên instance đã chọn trước đó | Phụ thuộc ngữ cảnh/lựa chọn trước | Ảnh hưởng thứ tự ứng viên hoặc mức ưu tiên |
| RequestBasedStickySessionServiceInstanceListSupplier | Ưu tiên instance ID trong cookie | Có | Chỉ có ý nghĩa khi adapter truyền đủ request context |
| RetryAwareServiceInstanceListSupplier | Tránh instance từng được chọn khi retry, nếu còn lựa chọn | Có | Phải nhìn thấy context retry; không thể tạo thêm instance |
| WeightedServiceInstanceListSupplier | Biến đổi phân bố trọng số lựa chọn | Thường dựa metadata/weight function | Có thể tác động phân bố sau khi các filter khác chạy |

Bảng mô tả mục đích của các lớp, không phải cam kết rằng mọi decorator đều chỉ trả về tập con. Ví dụ, weighted supplier có thể làm thay đổi cách biểu diễn/phân bố instance chứ không đơn giản lọc bỏ instance.

**Quy tắc chung:** decorator thuộc nhóm **lấy và ổn định danh sách từ nguồn** nên đặt gần discovery; decorator **lọc/ưu tiên theo request** nên đặt phía ngoài, gần LoadBalancer.

## 4. Vì sao hai bộ lọc có thể không giao hoán?

Nếu cả hai filter chỉ thuần túy lấy giao của hai tập hợp, thứ tự có thể không đổi kết quả. Nhưng nhiều decorator Spring Cloud có cơ chế **fallback**: khi không tìm thấy instance phù hợp, nó trả lại toàn bộ danh sách đầu vào thay vì trả một danh sách rỗng.

Trong Spring Cloud LoadBalancer:

- **ZonePreferenceServiceInstanceListSupplier** ưu tiên instance có metadata zone trùng với zone của client. Nếu không có instance cùng zone hoặc zone không được cấu hình, nó trả lại danh sách delegate.
- **HintBasedServiceInstanceListSupplier** lọc instance có metadata hint trùng với hint của request/cấu hình. Nếu không có hint phù hợp, nó trả lại danh sách delegate.

Chính điều kiện fallback này khiến thứ tự Zone và Hint có thể đổi kết quả.

### 4.1. Dữ liệu đầu vào

Giả sử registry cung cấp đúng hai instance:

| Instance | Zone | Hint | Health |
| --- | --- | --- | --- |
| A | zone-a | red | UP |
| B | zone-b | blue | UP |

Request yêu cầu hint **blue**, còn client cấu hình ưu tiên **zone-a**.

Danh sách discovery ban đầu:

~~~text
D = [A(zone-a,red), B(zone-b,blue)]
~~~

### 4.2. Trường hợp 1: Zone trước, Hint sau

Builder:

~~~java
.withDiscoveryClient()
.withCaching()
.withZonePreference()
.withHints()
~~~

Biến đổi theo thứ tự:

| Bước | Bộ xử lý | Danh sách |
| --- | --- | --- |
| 0 | Discovery | [A, B] |
| 1 | Cache | [A, B] |
| 2 | ZonePreference(zone-a) | [A] |
| 3 | HintBased(blue) | Không có blue trong [A], fallback thành [A] |
| **Cuối cùng** | LoadBalancer nhận | **[A]** |

Hint blue không còn tìm thấy B, vì B đã bị Zone loại bỏ khỏi danh sách được truyền đến Hint. Chính sách fallback của Hint chỉ có thể quay về **[A]**, không thể khôi phục B từ registry.

### 4.3. Trường hợp 2: Hint trước, Zone sau

Builder:

~~~java
.withDiscoveryClient()
.withCaching()
.withHints()
.withZonePreference()
~~~

Biến đổi theo thứ tự:

| Bước | Bộ xử lý | Danh sách |
| --- | --- | --- |
| 0 | Discovery | [A, B] |
| 1 | Cache | [A, B] |
| 2 | HintBased(blue) | [B] |
| 3 | ZonePreference(zone-a) | Không có zone-a trong [B], fallback thành [B] |
| **Cuối cùng** | LoadBalancer nhận | **[B]** |

Kết quả là **B**, ngược hoàn toàn với trường hợp 1. Cả hai lần chọn đều hợp lệ theo hành vi fallback của decorator, nhưng chúng thể hiện hai **độ ưu tiên kinh doanh/vận hành khác nhau**:

- Zone trước rồi Hint sau: **ưu tiên zone**; hint chỉ được chọn bên trong zone còn lại.
- Hint trước rồi Zone sau: **ưu tiên hint**; zone chỉ được chọn bên trong nhóm đã khớp hint.

~~~mermaid
flowchart TD
    S["Nguồn [A(zone-a,red), B(zone-b,blue)]"]
    S --> Z["Zone(zone-a) => [A]"]
    Z --> H1["Hint(blue) không khớp => fallback [A]"]
    S --> H2["Hint(blue) => [B]"]
    H2 --> Z2["Zone(zone-a) không khớp => fallback [B]"]
    H1 --> A["Kết quả A"]
    Z2 --> B["Kết quả B"]
~~~

Ví dụ trên giả định danh sách và metadata không thay đổi trong lúc tính toán. Trong môi trường thật, cache/health và discovery có thể cập nhật bất đồng bộ, nên cần đo trên cùng một snapshot khi so sánh chuỗi.

## 5. Thứ tự HealthCheck và ZonePreference còn có thể nguy hiểm hơn

**HealthCheckServiceInstanceListSupplier** định kỳ kiểm tra instance và thường trả những instance khỏe mạnh. Theo tài liệu Spring Cloud LoadBalancer 5.0.4, khi không có instance nào vượt qua health check, supplier có thể fallback về **toàn bộ danh sách instance đã nhận từ delegate**. Vì vậy, một filter đặt trước health check có thể làm thay đổi cả phạm vi health-check lẫn danh sách fallback.

Giả sử:

| Instance | Zone | Trạng thái thực |
| --- | --- | --- |
| A | zone-a | DOWN |
| B | zone-b | UP |

Client ưu tiên zone-a. Trong ví dụ, giả định lần health check đã cập nhật đầy đủ:

**Thứ tự nên dùng: Health → Zone**

~~~text
Discovery:       [A, B]
HealthCheck:     [B]          // chỉ B khỏe
ZonePreference:  [B]          // không có zone-a, fallback [B]
Kết quả:         [B]
~~~

**Thứ tự gây rủi ro: Zone → Health**

~~~text
Discovery:       [A, B]
ZonePreference:  [A]          // A thuộc zone-a
HealthCheck:     [A]          // A DOWN, không còn healthy;
                               // fallback về đầu vào [A] theo chính sách này
Kết quả:         [A]
~~~

Thứ tự sai có thể khiến LoadBalancer **ưu tiên một instance đang DOWN** vì health supplier đã bị đưa vào danh sách chỉ còn instance cùng zone. Đây là ví dụ cho thấy fallback theo danh sách delegate có thể không đáp ứng kỳ vọng vận hành nếu decorator được sắp xếp thiếu chủ đích.

**Lưu ý về phiên bản:** một số tài liệu hoặc release Spring Cloud cũ có mô tả khác về kết quả khi không còn instance khỏe. Trước khi triển khai quy tắc an toàn trong production, hãy đối chiếu phiên bản chính xác và kiểm thử tình huống tất cả instance trong danh sách đều không khỏe.

Trong cấu hình được khuyến nghị, HealthCheck được đặt **ngay sau discovery, trước mọi filter khác** để nó quan sát danh sách gốc đầy đủ.

## 6. Cache phải đặt gần nguồn discovery

Một thứ tự hợp lý với cache là:

~~~java
ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withCaching()
        .withZonePreference()
        .withHints()
        .build(context);
~~~

Sơ đồ:

~~~text
Discovery → Caching → ZonePreference → HintBased → LoadBalancer
~~~

**Vì sao?** CachingServiceInstanceListSupplier được thiết kế để lưu danh sách instance theo **service ID**. Nó không dùng hint header, cookie của từng người dùng hoặc thông tin một lần retry làm khóa cache.

Với thứ tự này, cùng một danh sách discovery có thể được dùng cho nhiều request nhưng mỗi request vẫn áp dụng hint, zone hoặc các bộ lọc khác ở phía ngoài:

| Request | Danh sách cache chung | Filter sau cache |
| --- | --- | --- |
| Hint=blue | [A, B, C] | Chọn các instance có hint=blue trong [A, B, C] |
| Hint=red | [A, B, C] | Chọn các instance có hint=red trong [A, B, C] |
| Không có hint | [A, B, C] | Theo hint mặc định hoặc trả về danh sách đầu vào |

Cache chia sẻ **nguồn dữ liệu**, không chia sẻ quyết định lọc của một request cụ thể.

### 6.1. Khi đặt cache sau filter theo request

Một cấu hình đáng nghi:

~~~java
ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withHints()
        .withCaching()
        .withZonePreference()
        .build(context);
~~~

Quan hệ decorator trở thành:

~~~text
ZonePreference
  └── Caching
        └── HintBased
              └── Discovery
~~~

Khi cache là decorator ngoài Hint, đường lấy dữ liệu của cache dùng **delegate.get()** và cache theo service ID. Nó không được thiết kế để chuyển tiếp Request riêng của từng người dùng vào Hint. Hệ quả có thể là Hint bên trong **không nhận được header của request**, phải dựa vào hint mặc định hoặc không lọc, trong khi danh sách được lưu và dùng lại cho nhiều request.

Không nên mô tả máy móc rằng “request blue đầu tiên làm mọi request sau luôn blue” đối với implementation cache hiện hành: hành vi cụ thể tùy cách delegate.get() xử lý hint mặc định và cách các lớp khác được tùy biến. Điều chắc chắn là **cache không được đặt bên ngoài filter có dữ liệu phụ thuộc Request**; nó có thể làm mất request context và cache một đầu ra không còn phù hợp cho các request khác.

Với decorator cache tự viết, nếu nó cache danh sách **sau khi đã lọc theo request** nhưng key chỉ là service ID, rủi ro còn rõ hơn: request đến sau có thể nhận lại danh sách đã lọc cho request trước. Phải phân biệt lỗi này với cache mặc định của Spring Cloud.

### 6.2. Cache không sửa được dữ liệu discovery đã cũ

Cache đúng vị trí vẫn có độ trễ cập nhật. Nếu một instance đã hủy đăng ký, danh sách cache có thể giữ instance đó đến khi hết TTL. Điều này là đặc tính dữ liệu cũ (**stale discovery**) chứ không phải lỗi thứ tự filter.

Cấu hình phổ biến:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
        capacity: 256
~~~

Spring Cloud LoadBalancer hiện hành mặc định cache với TTL 35 giây và capacity 256. Nếu DiscoveryClient đã cache, ví dụ Eureka, nên cân nhắc tắt cache ở LoadBalancer để tránh cache hai tầng kéo dài thời gian cập nhật.

## 7. HealthCheck là một nguồn trạng thái động, không chỉ filter đồng bộ

HealthCheckServiceInstanceListSupplier có lịch kiểm tra định kỳ và giữ các kết quả gần nhất bằng cơ chế Reactor Flux replay. Vì vậy, nó không chỉ là phép lọc thuần túy trên một List ở mỗi HTTP request.

Các yếu tố ảnh hưởng đầu ra:

1. **Nguồn delegate:** instance nào được đưa vào để kiểm tra.
2. **Lần kiểm tra gần nhất:** health có thể đã thay đổi từ lần poll trước.
3. **Chính sách khi không còn instance khỏe:** có thể fallback theo hành vi của phiên bản.
4. **Cách phát danh sách:** supplier có thể phát các kết quả trong quá trình kiểm tra, không phải lúc nào cũng chờ đủ toàn bộ instance.
5. **Refresh nguồn:** khi danh sách discovery thay đổi, có thể cần cơ chế refetch nếu delegate không phát cập nhật liên tục.

Tài liệu hiện hành đề cập:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        interval: 25s
        refetch-instances: true
        refetch-instances-interval: 25s
        update-results-list: false
~~~

Đây là **cấu hình minh họa**, không phải bộ giá trị bắt buộc. Khi update-results-list=false, health supplier gom danh sách alive trước khi phát để tránh phát nhiều trạng thái trung gian trong một chu kỳ; cần kiểm tra phiên bản đang sử dụng.

Spring Cloud khuyến nghị đặt **HealthCheckServiceInstanceListSupplier ngay sau discovery**. Không nên tự động ghép thêm CachingServiceInstanceListSupplier quanh nó: health supplier đã có cơ chế replay kết quả, và hai cơ chế lưu trữ có thể làm việc cập nhật khó hiểu hơn.

Ví dụ cấu hình dành cho reactive discovery:

~~~java
class InventoryHealthLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryInstanceListSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withHealthChecks()
                .withZonePreference()
                .withHints()
                .build(context);
    }
}
~~~

Đối với discovery blocking, builder có phương thức **withBlockingDiscoveryClient()** và **withBlockingHealthChecks()**. Không trộn ngẫu nhiên reactive và blocking mà không xem xét HTTP client/provider đang sử dụng.

Health check ở LoadBalancer thường hữu ích với SimpleDiscoveryClient hoặc nguồn không thông báo health. Với registry đã có health trạng thái đáng tin cậy, việc quét lại từng instance có thể dư thừa và gây thêm tải.

## 8. Filter theo Request phải thấy đúng Request

Không phải mọi decorator chỉ đọc một List. Một số cần **Request** để quyết định kết quả:

- Hint có thể được truyền qua header X-SC-LB-Hint hoặc cấu hình hint mặc định.
- Request-based sticky session có thể đọc cookie chứa instance ID.
- Retry-aware có thể đọc instance đã chọn ở lần thử trước.
- Một decorator tùy chỉnh có thể đọc tenant, API version hoặc thông tin phân loại traffic.

Trong Spring Cloud Commons, các decorator kế thừa DelegatingServiceInstanceListSupplier thường có hai đường gọi **get()** và **get(Request)**. Nếu một lớp ngoài chỉ gọi delegate.get() thay vì delegate.get(request), ngữ cảnh ở các lớp sâu bên trong có thể bị mất.

Từ Spring Cloud LoadBalancer 4.1.0, thuộc tính:

~~~yaml
spring:
  cloud:
    loadbalancer:
      call-get-with-request-on-delegates: true
~~~

được đưa vào để hỗ trợ chuyển tiếp Request tới delegate cho các lớp phù hợp, và trong các phiên bản hiện hành là mặc định true. Có **ngoại lệ** đối với CachingServiceInstanceListSupplier và HealthCheckServiceInstanceListSupplier. Đây là lý do hai lớp này phải ở gần nguồn discovery, **trước** các bộ lọc theo Request.

Nếu viết decorator tùy chỉnh, không nên chỉ override get() rồi vô tình làm mất Request. Hãy xác định:

1. Decorator này cần Request hay không?
2. Nó gọi delegate.get() hay delegate.get(request)?
3. Nó có lưu/cố định danh sách qua nhiều request không?
4. Nếu không có request context, nó trả danh sách gốc, áp dụng mặc định hay lỗi?
5. Khi có nhiều adapter HTTP khác nhau, Request có chứa đủ thông tin cần đọc không?

Thiết kế đúng thứ tự chỉ hữu ích khi **Request thực sự được truyền vào từ HTTP client**. Ví dụ, nếu adapter không chuyển hint header đến HintBased supplier trong phiên bản đang dùng, thay đổi thứ tự các decorator không tự khắc phục được việc thiếu header.

## 9. Sticky session, retry và thứ tự ưu tiên

### 9.1. Sticky session

**RequestBasedStickySessionServiceInstanceListSupplier** cố gắng ưu tiên instance ID được chỉ định trong cookie của request. Khi kết hợp với zone/hint, vị trí của sticky decorator quyết định **nó ưu tiên trên danh sách nào**.

Ví dụ:

~~~text
Discovery: [A, B, C]
Zone:     [A, B]
Hint:     [B]
Sticky:   ưu tiên instance mà cookie trỏ tới, nếu còn trong [B]
~~~

Với chuỗi **Discovery → Cache → Zone → Hint → Sticky**, sticky không thể tự chọn A nếu Hint chỉ còn B. Nếu muốn sticky có độ ưu tiên cao hơn hint/zone, cần cân nhắc lại thứ tự và **hợp đồng fallback** của các decorator, chứ không chỉ đổi một flag.

Request-based sticky session không nên thay cho cơ chế lưu session/phân phối trạng thái phù hợp. Nếu instance được cookie chỉ định đã chết, request vẫn phải có khả năng đến instance khác.

### 9.2. Retry-aware

**RetryAwareServiceInstanceListSupplier** có thể loại instance vừa được chọn khỏi danh sách ứng viên của lần retry khi còn instance thay thế. Mục tiêu là tránh gửi lại ngay lập tức tới cùng bản sao vừa gặp lỗi.

~~~text
Sau Zone và Hint:  [B, C]
Lần gọi trước:      B
Retry-aware:        [C]      // nếu chính sách tránh B được áp dụng
LoadBalancer:       chọn C
~~~

Nếu filter trước đó chỉ để lại đúng B, retry-aware không thể tạo ra C. Hành vi fallback khi không còn lựa chọn khác phụ thuộc implementation/chính sách hiện hành; không nên hứa rằng mọi retry đều đổi instance.

Trong một số cấu hình, Spring Cloud tự bọc supplier bằng RetryAwareServiceInstanceListSupplier khi retry được bật. Hãy kiểm tra cả **chuỗi supplier do ứng dụng tạo** và **wrapper do auto-configuration thêm** để biết thứ tự thực tế.

Retry chỉ liên quan đến **chọn lại instance**, không tự làm cho POST/PATCH có side effect trở nên lũy đẳng. Với thao tác tạo đơn, thanh toán hoặc điều chỉnh tồn kho, vẫn cần idempotency key và giới hạn retry/timeout phù hợp.

## 10. Builder mẫu với độ ưu tiên rõ ràng

### 10.1. Caching trước các filter

Khi muốn cache danh sách discovery, ưu tiên zone rồi mới ưu tiên hint:

~~~java
class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventorySupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .withHints()
                .build(context);
    }
}
~~~

Đầu ra có nghĩa: ưu tiên instance **cùng zone** trong danh sách discovery đã cache; sau đó chọn **hint** trong danh sách còn lại.

Nếu muốn hint có độ ưu tiên cao hơn zone, đổi thứ tự hai lệnh cuối:

~~~java
return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withCaching()
        .withHints()
        .withZonePreference()
        .build(context);
~~~

Đầu ra có nghĩa: ưu tiên instance **theo hint** trước; zone chỉ lọc trong tập còn lại, với fallback theo quy tắc ZonePreference.

### 10.2. HealthCheck thay cho cache

Khi dùng health-check scheduler:

~~~java
return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withHealthChecks()
        .withZonePreference()
        .withHints()
        .build(context);
~~~

Đặt HealthCheck ngay sau Discovery; thường **không ghép thêm withCaching()** vì health supplier đã có replay kết quả. Nếu dùng HTTP/discovery blocking, cần chọn phương thức builder blocking tương ứng.

### 10.3. Gắn cấu hình vào đúng service ID

Một cấu hình supplier có thể được áp dụng riêng cho inventory-service:

~~~java
@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class)
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Lớp InventoryLoadBalancerConfiguration trong ví dụ không được đánh dấu @Configuration. Spring Cloud khuyến nghị lớp cấu hình truyền qua @LoadBalancerClient **không bị component scan thu nhận như cấu hình toàn cục**: có thể không gắn annotation @Configuration hoặc đặt ngoài phạm vi scan. Nếu bị quét toàn cục, supplier chỉ định cho một service có thể vô tình ảnh hưởng service khác.

### 10.4. Cấu hình zone, hint và cache

Ví dụ application.yml:

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
      hint:
        default: blue
      cache:
        enabled: true
        ttl: 35s
~~~

**ZonePreference** so sánh zone của client với metadata key **zone** của instance. **HintBased** so sánh hint với metadata key **hint** của instance. Có các thuộc tính trong YAML nhưng registry không ghi metadata tương ứng thì filter có thể fallback về danh sách delegate.

Với HintBased supplier, request header mặc định **X-SC-LB-Hint** có thể ghi đè hint cấu hình khi HTTP adapter chuyển tiếp ngữ cảnh đó. Kiểm tra hành vi thực tế theo HTTP client, release train và cách ứng dụng truyền header.

## 11. Phân biệt tập hợp instance, thứ tự phần tử và số lần phát

Nói “danh sách đầu ra thay đổi” không chỉ có nghĩa là nhiều/ít instance:

| Loại thay đổi | Ví dụ | Hệ quả |
| --- | --- | --- |
| Membership | [A, B, C] thành [B] | Chỉ B còn là ứng viên |
| Thứ tự phần tử | [A, B] thành [B, A] | Có thể đổi lựa chọn theo một số thuật toán/chính sách |
| Trọng số/biểu diễn | A có trọng số 3, B trọng số 1 | Tần suất chọn thực tế có thể khác nhau |
| Độ tươi dữ liệu | Cache giữ [A, B] dù B đã dừng | Gọi đến instance đã lỗi |
| Ngữ cảnh request | Hint blue không được truyền vào supplier | Không lọc đúng nhóm traffic |
| Thời điểm phát | Health publisher phát nhiều snapshot | Request khác nhau có thể quan sát danh sách khác nhau |

**WeightedServiceInstanceListSupplier** sử dụng metadata weight hoặc WeightFunction để điều chỉnh phân bố chọn instance. Vì vậy, đánh giá đúng phải dựa vào **tần suất chọn instance qua nhiều request**, không chỉ so sánh số lượng instance duy nhất trong danh sách.

Với một decorator tùy chỉnh có sắp xếp, thứ tự phần tử có thể ảnh hưởng trực tiếp tới thuật toán sử dụng chỉ số. Tuy nhiên, không nên kết luận phân bố Round Robin chỉ từ một ảnh chụp danh sách: còn có vị trí bộ đếm hiện tại, số request đồng thời, cache và trạng thái instance.

## 12. Thực hành thuần Java: chứng minh hai bộ lọc không giao hoán

Không cần khởi động Eureka hay WebClient để hiểu nguyên lý. Ví dụ Java 17+ dưới đây mô phỏng **quy tắc fallback** của ZonePreference và HintBased bằng hai hàm:

~~~java
import java.util.List;

public class DecoratorOrderDemo {

    record Instance(String id, String zone, String hint) {
    }

    static List<Instance> preferZone(
            List<Instance> input, String preferredZone) {
        List<Instance> matching = input.stream()
                .filter(i -> preferredZone.equals(i.zone()))
                .toList();
        return matching.isEmpty() ? input : matching;
    }

    static List<Instance> preferHint(
            List<Instance> input, String requestedHint) {
        List<Instance> matching = input.stream()
                .filter(i -> requestedHint.equals(i.hint()))
                .toList();
        return matching.isEmpty() ? input : matching;
    }

    public static void main(String[] args) {
        List<Instance> discovered = List.of(
                new Instance("A", "zone-a", "red"),
                new Instance("B", "zone-b", "blue"));

        List<Instance> zoneThenHint =
                preferHint(preferZone(discovered, "zone-a"), "blue");

        List<Instance> hintThenZone =
                preferZone(preferHint(discovered, "blue"), "zone-a");

        System.out.println("Zone -> Hint: " +
                zoneThenHint.stream().map(Instance::id).toList());
        System.out.println("Hint -> Zone: " +
                hintThenZone.stream().map(Instance::id).toList());
    }
}
~~~

Kết quả mong đợi:

~~~text
Zone -> Hint: [A]
Hint -> Zone: [B]
~~~

Đây là **mô phỏng có chủ đích**, không phải code trực tiếp gọi hai lớp Spring Cloud. Ưu điểm là nó tách riêng vấn đề **thứ tự biến đổi danh sách** khỏi thời gian cache, lịch health-check, truy cập registry và trạng thái HTTP client.

Sau khi hiểu ví dụ này, mới kiểm thử chuỗi supplier thật trong ứng dụng Spring.

## 13. Kiểm thử chuỗi supplier thực tế

### 13.1. Chuẩn bị dữ liệu cố định

Hãy chuẩn bị ba hoặc bốn ServiceInstance với metadata tường minh:

| Instance | zone | hint | Trạng thái health giả lập |
| --- | --- | --- | --- |
| A | zone-a | red | UP |
| B | zone-b | blue | UP |
| C | zone-a | blue | DOWN |
| D | zone-b | red | UP |

Có thể dùng supplier giả trong unit test để trả Flux.just(List.of(A, B, C, D)). Với các phép kiểm tra health, dùng endpoint hoặc HTTP client giả để kiểm soát kết quả thăm dò, thay vì dựa vào các instance thật thay đổi ngẫu nhiên.

### 13.2. Bộ kịch bản cần kiểm tra

| Kịch bản | Thao tác | Điều cần xác minh |
| --- | --- | --- |
| Zone trước Hint | Đặt zone-a, request hint blue | Danh sách sau Zone và sau Hint theo đúng thứ tự |
| Hint trước Zone | Đổi vị trí hai decorator | Danh sách cuối có thể khác |
| Không match zone | Chọn zone không tồn tại | ZonePreference fallback về danh sách delegate |
| Không match hint | Gửi hint không tồn tại | HintBased fallback về danh sách delegate |
| Cache trước Hint | Gửi hai request có hint khác nhau | Hai request dùng chung cache discovery nhưng lọc theo hint riêng |
| Cache bên ngoài Hint | Tạm dùng cấu hình sai trong test | Kiểm tra Request có tới Hint và danh sách có bị cố định không |
| Health trước Zone | A DOWN, B UP | Chỉ healthy instance được đưa vào Zone khi probe đã ổn định |
| Zone trước Health | Đảo hai decorator | Quan sát kết quả fallback, so sánh với version đang chạy |
| Retry-aware | Retry sau khi instance B lỗi | Nếu còn ứng viên, quan sát việc tránh B |
| Cập nhật discovery | Thêm hoặc xóa một instance | Xác minh TTL cache/refresh health có tác động như dự kiến |

### 13.3. Không dùng một lần đọc để kết luận health

HealthCheckServiceInstanceListSupplier có scheduler và publisher; một phép subscribe có thể gặp trạng thái chưa ổn định hoặc snapshot trung gian. Khi kiểm thử, hãy chủ động chờ điều kiện đã thiết lập trong môi trường test, cấu hình update-results-list nếu cần và ghi timestamp cho mỗi snapshot.

**Flux<List<ServiceInstance>> có thể phát nhiều danh sách theo thời gian**. Không dùng collectList() trên một luồng phát liên tục rồi chờ nó tự kết thúc. Với unit test cho một snapshot có kiểm soát, có thể sử dụng next() hoặc take(1) cùng timeout phù hợp; với test health, nên chờ snapshot thỏa điều kiện kỳ vọng.

## 14. Quan sát và chẩn đoán

Khi HTTP request đi sai instance, hãy nhìn chuỗi supplier theo từng tầng:

~~~text
Discovery:
  [A, B, C, D]
Cache / Health:
  [A, B, D]
Zone:
  [A]
Hint:
  [A]   (fallback: không có blue sau khi Zone đã lọc)
LoadBalancer:
  chọn A
~~~

Cách log hữu ích:

- Service ID và request ID/trace ID.
- Tên decorator và thứ tự trong chuỗi.
- Danh sách instance ID **trước/sau** mỗi decorator.
- Zone, hint, previous-instance ID và thông tin request context cần thiết.
- Timestamp snapshot discovery/cache/health.
- Instance cuối cùng được Round Robin hoặc Random chọn.

Không log access token, credential hoặc cookie đầy đủ. Nếu dùng sticky session, chỉ nên log instance ID liên quan, không ghi giá trị session nhạy cảm.

### Bảng chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách xác minh |
| --- | --- | --- |
| Request có hint blue nhưng vẫn đến instance red | Hint bị đặt dưới cache hoặc adapter không truyền Request | Quan sát get(Request), thứ tự wrappers và hint từ header |
| Instance khác zone được chọn dù có cấu hình zone | Filter trước đó đã loại hết instance cùng zone; fallback được kích hoạt | So sánh đầu vào/đầu ra ở ZonePreference |
| Instance DOWN xuất hiện trong đầu ra | Health chưa cập nhật, fallback khi không còn healthy, hoặc Health đặt sai vị trí | Kiểm tra lịch probe và danh sách delegate của Health |
| Thay đổi thứ tự filter làm đích thay đổi | Hai filter có fallback không giao hoán | Tái tạo dataset cố định rồi mô phỏng từng bước |
| Sau đổi hint, danh sách vẫn không đổi | Cache giữ danh sách đã lọc hoặc request context mất | Kiểm tra vị trí Cache và get(Request) |
| Registry vừa xóa instance nhưng supplier còn trả | TTL cache hoặc discovery registry chưa làm mới | Kiểm tra cache TTL, heartbeat/deregistration |
| Retry vẫn chọn instance vừa lỗi | Không còn ứng viên khác sau lọc, hoặc retry-aware không nhận context | Kiểm tra danh sách ngay trước retry-aware |
| Sticky session chọn instance không mong đợi | Cookie ID không còn trong danh sách sau filter | Kiểm tra instance ID và thứ tự Sticky/Zone/Hint |

Nếu danh sách đã sai từ discovery thì đổi thứ tự decorator không sửa được dữ liệu registry. Nếu danh sách discovery đúng nhưng đầu ra sai, kiểm tra lần lượt cache, health, zone, hint và request context trước khi thay thuật toán chọn đích.

## 15. Nguyên tắc thiết kế chuỗi an toàn

1. **Có một nguồn instance rõ ràng**: DiscoveryClientServiceInstanceListSupplier hoặc nguồn tùy chỉnh.
2. **Đặt cache hoặc health check sát nguồn**: không đặt filter theo request bên dưới chúng. Theo khuyến nghị Spring Cloud, thông thường chọn một trong hai, tránh ghép cả hai khi không có lý do.
3. **Xác định thứ tự ưu tiên nghiệp vụ**: ưu tiên zone hay hint trước? Sticky session có được vượt qua hint không? Điều này phải được mô tả thành contract.
4. **Đọc kỹ fallback**: một filter có thể trả về đầu vào khi không match; vì thế “filter” không luôn có nghĩa là ràng buộc bắt buộc.
5. **Giữ Request context**: các decorator cần hint/cookie/retry phải thấy đúng request. Kiểm tra call-get-with-request-on-delegates và behavior của adapter.
6. **Không nhầm tính sẵn sàng với vị trí filter**: health có thời gian cập nhật; danh sách UP tại thời điểm chọn không bảo đảm kết nối chắc chắn thành công.
7. **Xem lại wrapper tự động**: Spring Cloud có thể tự thêm retry-aware supplier hoặc các lớp khác dựa trên cấu hình.
8. **Kiểm chứng bằng bảng dữ liệu nhỏ**: chạy cùng snapshot qua hai thứ tự để thấy sự khác biệt.
9. **Đo đầu ra cuối và lỗi thực tế**: theo dõi lựa chọn instance, 503, timeout, retry count và tỷ lệ request bị bỏ do thiếu instance.
10. **Ghi chú version và mặc định**: hành vi fallback, health publisher và truyền Request có thể thay đổi giữa các release train.

## 16. Kết luận

Trong Spring Cloud LoadBalancer, thứ tự decorator **không phải chi tiết trình bày code**. Nó xác định danh sách nào được nhìn thấy bởi mỗi bộ lọc, liệu cache có làm mất request context, health check kiểm tra toàn bộ nguồn hay chỉ một tập con và liệu fallback có trả lại những instance mà một filter trước đó đã loại bỏ.

Quy tắc nên bắt đầu từ **Discovery → Cache hoặc Health → các bộ lọc theo chính sách → bộ lọc theo Request → chọn instance**, sau đó điều chỉnh thứ tự các filter nghiệp vụ theo mục tiêu rõ ràng và kiểm thử với dữ liệu có trường hợp không match. Đặc biệt, **Zone rồi Hint** có thể khác **Hint rồi Zone** vì cơ chế fallback; đây là ví dụ thực tế cho tính không giao hoán của chuỗi decorator.

## 17. Tài liệu tham khảo

- [Spring Cloud LoadBalancer - Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): builder, caching, zone preference, hint, health check và lưu ý về thứ tự decorator.
- [Spring Cloud Commons - Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): service discovery, retry và abstraction cho client-side load balancing.
- [Spring Cloud Commons Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): thuộc tính cache, health-check và call-get-with-request-on-delegates.
- [ServiceInstanceListSupplierBuilder.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/ServiceInstanceListSupplierBuilder.java): thứ tự tạo và ghép các decorator.
- [CachingServiceInstanceListSupplier.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/CachingServiceInstanceListSupplier.java): hành vi cache theo service ID và truy cập delegate.
- [ZonePreferenceServiceInstanceListSupplier.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/ZonePreferenceServiceInstanceListSupplier.java): quy tắc ưu tiên zone và fallback.
- [HintBasedServiceInstanceListSupplier.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/HintBasedServiceInstanceListSupplier.java): lọc theo metadata hint và request.
