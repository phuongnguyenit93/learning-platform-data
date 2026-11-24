# Truy vấn định kỳ, theo dõi thay đổi và lưu đệm danh sách

Trong microservice, danh sách instance của một dịch vụ thay đổi theo thời gian. Instance mới có thể được tạo khi tải tăng; instance cũ có thể bị dừng, thay thế hoặc chuyển sang máy khác. Consumer cần cập nhật thông tin discovery để tránh gọi địa chỉ đã lỗi thời và có thể sử dụng những instance vừa tham gia hệ thống.

Trong Spring Cloud, DiscoveryClient cung cấp cách truy vấn instance theo service ID. Tuy nhiên, một lần gọi getInstances() chỉ trả lời câu hỏi discovery client biết những instance nào tại thời điểm truy vấn. Để theo dõi thay đổi theo thời gian, hệ thống cần một chiến lược cập nhật: truy vấn định kỳ, nhận tín hiệu thay đổi từ registry nếu nền tảng hỗ trợ, hoặc kết hợp cả hai. Lưu đệm giúp giảm số lần truy vấn và độ trễ, nhưng cũng tạo ra nguy cơ dữ liệu cũ.

Bài viết này tập trung vào cách tổ chức chu kỳ truy vấn, phát hiện thay đổi và quản lý cache danh sách instance trong Spring Cloud Service Discovery.

## 1. Vì sao cần cập nhật danh sách instance?

Giả sử order-service gọi inventory-service. Lúc khởi động, consumer phát hiện hai instance:

~~~text
inventory-service
  10.0.2.15:8081
  10.0.2.16:8081
~~~

Sau đó, nền tảng triển khai thêm instance thứ ba và dừng instance thứ hai:

~~~text
inventory-service
  10.0.2.15:8081
  10.0.3.21:8081
~~~

Nếu consumer tiếp tục sử dụng danh sách ban đầu, nó có thể bỏ lỡ instance mới và gửi request đến địa chỉ đã ngừng hoạt động. Một số hậu quả thường gặp:

- Request thất bại vì địa chỉ cũ không còn nhận kết nối.
- Tải phân phối không đều vì consumer không biết instance mới.
- Consumer ở các thời điểm khác nhau nhìn thấy những danh sách khác nhau.
- Một thay đổi đã được registry ghi nhận nhưng chưa đến được cache của consumer hoặc load balancer.

Do đó, discovery không chỉ là thao tác tìm instance một lần. Ứng dụng cần có cách làm mới dữ liệu và giới hạn khoảng thời gian mà dữ liệu cũ được phép tồn tại.

## 2. Truy vấn định kỳ (polling)

Polling là cách consumer hoặc một thành phần discovery định kỳ hỏi registry xem danh sách service instance hiện tại như thế nào. Mỗi lần truy vấn, client lấy kết quả mới rồi cập nhật cache hoặc so sánh với kết quả trước đó.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant D as DiscoveryClient
    participant R as Service Registry
    loop Theo chu kỳ
        C->>D: getInstances(inventory-service)
        D->>R: Đọc danh sách instance (nếu cần)
        R-->>D: Danh sách hiện tại
        D-->>C: ServiceInstance list
        C->>C: So sánh và cập nhật snapshot
    end
~~~

Chu kỳ có thể được đặt theo nhu cầu vận hành. Chu kỳ ngắn giúp phát hiện thay đổi nhanh hơn nhưng làm tăng số lần truy vấn và lượng công việc xử lý. Chu kỳ dài giảm tải cho registry nhưng khiến consumer có thể tiếp tục dùng dữ liệu cũ lâu hơn.

### Polling có thể diễn ra ở nhiều lớp

Không phải mọi request của ứng dụng đều truy vấn registry. Tùy registry và tích hợp Spring Cloud, có thể có nhiều lớp cập nhật:

| Lớp | Cách cập nhật | Mục đích |
|---|---|---|
| Registry client | Đồng bộ hoặc tải danh sách từ registry theo chu kỳ | Duy trì dữ liệu discovery phía ứng dụng |
| Ứng dụng consumer | Gọi DiscoveryClient theo lịch hoặc khi cần | Quan sát danh sách, tạo snapshot hoặc thực hiện logic riêng |
| Load balancer | Lấy danh sách instance từ supplier và có thể dùng cache | Chọn instance cho request |
| Gateway hoặc proxy | Đồng bộ đích đến hoặc truy vấn registry theo cơ chế tích hợp | Định tuyến request từ phía server |

Ví dụ, một registry client có thể tự cập nhật danh sách từ server và cung cấp dữ liệu cục bộ cho DiscoveryClient. Khi consumer gọi getInstances(), lời gọi đó có thể đọc cache cục bộ thay vì tạo một truy vấn mạng mới đến registry. Cần hiểu cơ chế của implementation đang dùng trước khi kết luận mỗi lần gọi API đều tạo tải cho registry.

### Chọn chu kỳ truy vấn

Khi chọn chu kỳ, hãy cân nhắc:

- **Thời gian chấp nhận dữ liệu cũ:** hệ thống cho phép mất bao lâu để một instance mới được nhìn thấy hoặc instance đã dừng bị loại khỏi danh sách?
- **Quy mô:** có bao nhiêu consumer, mỗi consumer theo dõi bao nhiêu service ID?
- **Chi phí truy vấn:** registry có chịu được số lần đọc và lượng dữ liệu trả về không?
- **Tần suất thay đổi:** instance thay đổi liên tục hay chỉ trong các đợt triển khai?
- **Khả năng phục hồi:** khi registry tạm thời không truy cập được, consumer cần tiếp tục dùng snapshot gần nhất trong bao lâu?

Nếu có nhiều consumer cùng dùng một chu kỳ cố định, chúng có thể đồng loạt truy vấn tại cùng thời điểm. Có thể thêm jitter (độ lệch ngẫu nhiên nhỏ) để phân tán thời điểm truy vấn, tránh tạo đỉnh tải đồng bộ.

fixedDelay và fixedRate cũng có hành vi khác nhau. fixedDelay tính khoảng chờ sau khi lần thực thi trước hoàn tất; fixedRate lập lịch theo nhịp thời gian cố định. Với tác vụ truy vấn có thể mất thời gian, cần kiểm soát khả năng chạy chồng lấn, timeout và kích thước thread pool.

## 3. Theo dõi thay đổi bằng cách so sánh snapshot

Một snapshot là bản chụp danh sách instance tại một thời điểm. Khi có kết quả truy vấn mới, consumer so sánh snapshot mới với snapshot cũ để phát hiện:

- **Instance được thêm:** xuất hiện trong danh sách mới nhưng không có trong danh sách cũ.
- **Instance bị loại:** có trong danh sách cũ nhưng không còn trong danh sách mới.
- **Instance thay đổi thuộc tính:** cùng một instance nhưng host, port, scheme hoặc metadata đã thay đổi.
- **Không có thay đổi:** hai snapshot tương đương theo các thuộc tính mà ứng dụng quan tâm.

~~~mermaid
flowchart TD
    A["Nhận danh sách mới"] --> B["Chuẩn hóa và sắp xếp"]
    B --> C["So sánh snapshot cũ"]
    C --> D{"Có thay đổi?"}
    D -->|"Không"| E["Giữ snapshot hiện tại"]
    D -->|"Có"| F["Tính instance thêm, bỏ, cập nhật"]
    F --> G["Công bố snapshot mới"]
    G --> H["Ghi log / metric / xử lý tiếp"]
~~~

Để so sánh chính xác, cần chọn thuộc tính định danh instance. Có thể dùng instance ID nếu registry cung cấp ổn định; nếu không, có thể dùng URI kết hợp metadata phù hợp. Không nên chỉ so sánh số lượng instance: hai danh sách cùng có hai phần tử nhưng cả hai địa chỉ đều có thể đã thay đổi.

Metadata cũng cần được đưa vào phép so sánh nếu nó ảnh hưởng đến định tuyến hoặc lựa chọn instance. Ví dụ, thay đổi zone hoặc version có thể quan trọng dù host và port không đổi. Ngược lại, không cần phát hiện thay đổi ở những metadata không ảnh hưởng đến logic của consumer.

### Ví dụ so sánh hai danh sách

Danh sách trước:

~~~text
10.0.2.15:8081
10.0.2.16:8081
~~~

Danh sách sau:

~~~text
10.0.2.15:8081
10.0.3.21:8081
~~~

Kết quả so sánh:

| Loại thay đổi | Instance |
|---|---|
| Giữ nguyên | 10.0.2.15:8081 |
| Bị loại | 10.0.2.16:8081 |
| Được thêm | 10.0.3.21:8081 |

Việc so sánh giúp quan sát topology và thực hiện logic bổ sung. Tuy nhiên, nếu mục tiêu chỉ là gửi request, không nên tự xây dựng bộ chọn instance từ snapshot này khi Spring Cloud LoadBalancer đã đảm nhiệm vai trò đó.

## 4. Ví dụ polling bằng DiscoveryClient trong Spring

Với ứng dụng cần quan sát thay đổi của một service cụ thể, có thể tạo một tác vụ định kỳ. Ví dụ sau lấy URI và metadata của các instance inventory-service, chuẩn hóa thành danh sách chữ ký rồi so sánh với snapshot trước.

~~~java
@Configuration
@EnableScheduling
public class DiscoverySchedulingConfiguration {
}
~~~

~~~java
@Component
public class InventoryDiscoveryMonitor {

    private static final Logger log =
        LoggerFactory.getLogger(InventoryDiscoveryMonitor.class);

    private final DiscoveryClient discoveryClient;

    private final AtomicReference<List<String>> snapshot =
        new AtomicReference<>(Collections.emptyList());

    public InventoryDiscoveryMonitor(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @Scheduled(fixedDelayString =
        "${discovery.inventory.refresh-delay-ms:10000}")
    public synchronized void refresh() {
        try {
            List<String> current = discoveryClient
                .getInstances("inventory-service")
                .stream()
                .map(instance ->
                    instance.getUri() + "|" +
                    new TreeMap<>(instance.getMetadata()))
                .sorted()
                .collect(Collectors.toList());

            List<String> next =
                Collections.unmodifiableList(current);
            List<String> previous = snapshot.get();

            if (!previous.equals(next)) {
                log.info(
                    "inventory-service discovery changed: {} -> {}",
                    previous,
                    next
                );
                snapshot.set(next);
            }
        } catch (RuntimeException ex) {
            log.warn("Cannot refresh inventory-service discovery", ex);
        }
    }
}
~~~

Đây là ví dụ minh họa cho việc quan sát thay đổi, không phải một load balancer tự viết. Các import cần thiết gồm DiscoveryClient, Component, Configuration, EnableScheduling, Scheduled, Logger, LoggerFactory, AtomicReference, Collections, List, TreeMap và Collectors.

Một số điểm cần chú ý:

- @EnableScheduling bật cơ chế chạy tác vụ theo lịch trong ứng dụng.
- fixedDelayString lấy chu kỳ chờ từ cấu hình, ở ví dụ mặc định là 10.000 mili giây sau khi lần chạy trước hoàn tất.
- URI và metadata được chuẩn hóa thành chữ ký để so sánh. TreeMap giúp thứ tự key metadata ổn định khi tạo chuỗi.
- Snapshot chỉ được thay khi danh sách mới khác danh sách cũ.
- Khi truy vấn ném lỗi, ví dụ giữ snapshot gần nhất và ghi log. Không nên xóa cache chỉ vì một lần refresh thất bại.

Trong ứng dụng thực tế, nên giới hạn log thay đổi để tránh ghi quá nhiều khi topology biến động liên tục. Có thể phát metric về số instance, số lần refresh lỗi và thời điểm refresh thành công gần nhất. Nếu cần phân biệt “dịch vụ thực sự không có instance” với “registry đang lỗi”, cần dùng thêm tín hiệu sức khỏe hoặc trạng thái lỗi do registry implementation cung cấp. API discovery chung có thể trả về danh sách rỗng mà không đủ thông tin để phân biệt mọi nguyên nhân.

## 5. Cập nhật theo sự kiện hoặc watch

Polling không phải lựa chọn duy nhất. Một số registry cung cấp cơ chế watch, event, long polling hoặc subscription để consumer nhận biết khi dữ liệu thay đổi. Khi có hỗ trợ, consumer có thể cập nhật sớm hơn mà không cần liên tục gửi truy vấn đầy đủ.

Ví dụ về cách tiếp cận:

- Consul có cơ chế watch và blocking query để theo dõi thay đổi của catalog hoặc dữ liệu liên quan.
- Eureka client thường duy trì bản sao registry ở phía client và làm mới bản sao theo chu kỳ cấu hình.
- Một số nền tảng hoặc service mesh có thể phát sự kiện thay đổi endpoint cho proxy hoặc sidecar.

Các cơ chế trên là đặc điểm của registry hoặc tích hợp cụ thể. DiscoveryClient của Spring Cloud cung cấp abstraction tra cứu service và instance, nhưng không đảm bảo một API sự kiện thay đổi thống nhất cho mọi registry. Nếu ứng dụng cần watch, phải kiểm tra khả năng và API của implementation đang dùng.

### Kết hợp watch với polling đối soát

Watch có thể giúp phát hiện thay đổi nhanh, nhưng kết nối có thể bị ngắt, sự kiện có thể bị bỏ lỡ hoặc consumer có thể khởi động lại trong lúc registry thay đổi. Vì vậy, một cách triển khai bền vững là:

1. Lấy snapshot đầy đủ ban đầu khi consumer khởi động.
2. Đăng ký watch hoặc subscription nếu registry hỗ trợ.
3. Khi nhận tín hiệu, làm mới dữ liệu liên quan hoặc lấy snapshot mới.
4. Định kỳ thực hiện truy vấn đối soát để sửa sai lệch nếu sự kiện bị bỏ lỡ.
5. Khi kết nối watch bị mất, thử kết nối lại với backoff và lấy snapshot mới trước khi tiếp tục xử lý sự kiện.

Sự kiện có thể được xem là tín hiệu yêu cầu làm mới. Snapshot từ nguồn discovery vẫn cần được xác minh trước khi công bố cho consumer khác sử dụng.

## 6. Lưu đệm danh sách instance

Cache giữ kết quả discovery trong bộ nhớ hoặc một kho lưu trữ trung gian để tránh truy vấn lặp lại. Cache có thể nằm ở registry client, ứng dụng consumer, ServiceInstanceListSupplier của Spring Cloud LoadBalancer, gateway hoặc proxy.

Lợi ích của cache:

- Giảm số lần đọc registry và lưu lượng mạng.
- Giảm độ trễ khi cần lấy danh sách instance.
- Giúp consumer tiếp tục hoạt động trong một khoảng thời gian khi registry tạm thời không truy cập được.
- Giảm công việc lặp lại khi nhiều request liên tiếp cần cùng một danh sách.

Đổi lại, cache tạo ra độ trễ cập nhật. Nếu một instance bị dừng nhưng cache vẫn còn địa chỉ cũ, request có thể tiếp tục được định tuyến đến instance đó. Nếu cache không có instance vừa được thêm, tải có thể không được phân phối đến instance mới.

### TTL và thời điểm làm mới

TTL (time to live) là khoảng thời gian một mục cache được xem là còn hiệu lực. Khi TTL hết hạn, cache cần được làm mới trước hoặc trong lần đọc tiếp theo, tùy chiến lược triển khai.

| TTL | Lợi ích | Rủi ro |
|---|---|---|
| Ngắn | Nhìn thấy thay đổi nhanh hơn | Tăng số lần truy vấn và xử lý cache |
| Dài | Giảm tải registry, tăng khả năng dùng dữ liệu đã có | Danh sách có thể lỗi thời lâu hơn |
| Không giới hạn | Truy vấn rất ít | Có thể giữ địa chỉ không còn hợp lệ vô thời hạn nếu không có cơ chế cập nhật khác |

Không có một TTL đúng cho mọi hệ thống. Hãy chọn dựa trên thời gian chấp nhận dữ liệu cũ, tốc độ thay đổi instance và chi phí truy vấn. TTL của các lớp cache cần được xem xét cùng nhau: cache registry client, cache load balancer và cache riêng của ứng dụng có thể cộng dồn độ trễ cập nhật.

### Cache snapshot theo kiểu last-known-good

Khi refresh thất bại vì timeout hoặc registry tạm thời không sẵn sàng, xóa ngay snapshot có thể làm ứng dụng mất toàn bộ thông tin định vị. Một lựa chọn là giữ snapshot thành công gần nhất trong một khoảng thời gian giới hạn, đồng thời đánh dấu dữ liệu đang stale.

Chiến lược này thường gồm:

1. Chỉ công bố snapshot mới sau khi lần truy vấn hoàn tất và dữ liệu đã được kiểm tra.
2. Khi refresh thất bại, giữ snapshot gần nhất thay vì thay bằng dữ liệu chưa xác minh.
3. Ghi lại thời điểm thành công gần nhất và tuổi của snapshot.
4. Đặt giới hạn tuổi tối đa cho dữ liệu stale; khi vượt ngưỡng, cảnh báo hoặc chuyển sang chính sách an toàn.
5. Tiếp tục thử refresh theo backoff để tránh dồn request vào registry đang gặp sự cố.

Không nên giữ dữ liệu stale vô thời hạn. Địa chỉ cũ có thể đã được cấp cho một tiến trình khác hoặc không còn được định tuyến đến provider ban đầu. Việc dùng last-known-good cần kết hợp timeout, xử lý lỗi request và giới hạn thời gian rõ ràng.

### Tránh nhiều lớp cache không cần thiết

Spring Cloud LoadBalancer có cơ chế supplier và có thể tích hợp cache để lưu danh sách instance dùng cho lựa chọn. Registry client cũng có thể đã cache dữ liệu. Nếu ứng dụng tiếp tục tạo một cache độc lập mà không hiểu hai lớp kia, hệ thống có thể có nhiều snapshot với thời điểm làm mới khác nhau.

Trước khi thêm cache riêng, hãy xác định:

- Registry client đã tự làm mới dữ liệu chưa?
- Load balancer đang dùng supplier nào và cache ở đâu?
- Cache mới phục vụ mục đích gì: quan sát, báo cáo, định tuyến đặc thù hay giảm tải?
- TTL và cơ chế invalidation của các lớp cache có tương thích không?

Với việc gửi request thông thường, nên sử dụng tích hợp Spring Cloud LoadBalancer để lựa chọn instance. Cache tự quản lý trong ví dụ ở trên chỉ phục vụ theo dõi topology. Nếu thật sự cần chính sách định tuyến riêng, cần đảm bảo cache được cập nhật và xử lý lỗi nhất quán với các lớp discovery còn lại.

## 7. Xử lý lỗi khi polling và refresh

Refresh discovery có thể gặp nhiều dạng lỗi:

| Tình huống | Biểu hiện | Cách xử lý |
|---|---|---|
| Registry không truy cập được | Timeout hoặc exception khi truy vấn | Giữ snapshot hợp lệ gần nhất trong giới hạn; retry có backoff |
| Service chưa có instance | Danh sách trả về rỗng | Kiểm tra provider, service ID và trạng thái đăng ký; không mặc định đây là lỗi registry |
| Instance vừa dừng | Snapshot cũ vẫn chứa địa chỉ | Làm mới danh sách, đặt timeout request và loại đích lỗi theo cơ chế phù hợp |
| Instance mới chưa xuất hiện | Snapshot chưa có địa chỉ mới | Kiểm tra chu kỳ đăng ký, refresh và cache ở từng lớp |
| Watch bị ngắt | Không nhận được sự kiện mới | Kết nối lại, lấy snapshot đầy đủ và tiếp tục polling đối soát |
| Refresh chạy chồng lấn | Kết quả cũ có thể ghi đè kết quả mới | Dùng một luồng cập nhật hoặc cơ chế đồng bộ/phiên bản snapshot |

### Retry và backoff

Nếu registry đang quá tải hoặc mất kết nối, việc mọi consumer retry liên tục theo cùng một chu kỳ ngắn có thể làm sự cố nặng hơn. Exponential backoff tăng dần khoảng chờ giữa các lần thử; jitter phân tán thời điểm retry giữa các consumer.

Ví dụ minh họa khoảng chờ:

~~~text
Lần thử 1: 1 giây
Lần thử 2: 2 giây
Lần thử 3: 4 giây
Lần thử 4: 8 giây
...
~~~

Trong thực tế cần đặt giới hạn tối đa cho backoff và có thể reset chu kỳ sau khi refresh thành công. Không retry vô hạn với tần suất cao. Với tác vụ đọc discovery, retry cần có timeout tổng thể để không giữ tài nguyên quá lâu.

### Phân biệt kết quả rỗng và lỗi truy vấn

Danh sách rỗng có thể là kết quả hợp lệ nếu dịch vụ chưa có instance hoặc tất cả instance đã bị loại. Nó cũng có thể là dấu hiệu cấu hình sai service ID hoặc hành vi của implementation khi registry gặp sự cố. Không nên tự động thay thế một snapshot còn tốt bằng danh sách rỗng nếu không biết rõ ý nghĩa kết quả từ registry.

Hãy quan sát thêm trạng thái registry, lỗi kết nối, thời điểm refresh thành công và số instance. Nếu adapter phân biệt được lỗi truy vấn với kết quả rỗng, dùng thông tin đó để quyết định có công bố snapshot mới hay giữ dữ liệu cũ.

## 8. Vận hành và quan sát chất lượng discovery

Để biết cache và polling có hoạt động đúng hay không, nên theo dõi một số chỉ số:

| Chỉ số | Ý nghĩa |
|---|---|
| Refresh success/failure | Số lần cập nhật thành công và thất bại |
| Refresh duration | Thời gian hoàn thành một lần truy vấn |
| Last successful refresh | Thời điểm gần nhất có snapshot mới hợp lệ |
| Snapshot age | Tuổi của dữ liệu đang được sử dụng |
| Instance count | Số instance được phát hiện theo service ID |
| Added/removed/updated count | Số instance thay đổi giữa hai snapshot |
| Watch reconnect count | Số lần kết nối watch phải thiết lập lại |

Log nên ghi service ID, số lượng instance, kết quả refresh và nguyên nhân lỗi; tránh ghi dữ liệu nhạy cảm hoặc thông tin kết nối có thể bị lạm dụng. Với hệ thống có nhiều service, nên dùng metric có nhãn được kiểm soát để tránh cardinality quá cao.

Một cảnh báo hữu ích là snapshot quá cũ so với ngưỡng vận hành. Cảnh báo này giúp phát hiện consumer vẫn hoạt động nhưng không còn cập nhật được danh sách discovery. Cũng nên cảnh báo khi một dịch vụ quan trọng không có instance trong thời gian dài, sau khi đã loại trừ tình huống scale-to-zero có chủ đích.

## 9. Nguyên tắc thiết kế

- Chỉ truy vấn những service ID mà ứng dụng thực sự cần theo dõi, nếu không cần toàn bộ catalog.
- Chọn chu kỳ refresh dựa trên thời gian chấp nhận dữ liệu stale và tải của registry.
- Thêm jitter cho polling hoặc retry khi có nhiều consumer để tránh truy vấn đồng loạt.
- So sánh danh tính và metadata quan trọng, không chỉ so sánh số lượng instance.
- Công bố snapshot mới một cách nguyên tử sau khi đã xử lý xong kết quả.
- Giữ last-known-good có giới hạn khi refresh lỗi; theo dõi tuổi dữ liệu và không dùng stale vô thời hạn.
- Hiểu cache sẵn có trong registry client và Spring Cloud LoadBalancer trước khi thêm cache riêng.
- Nếu dùng watch/event, vẫn có cơ chế lấy snapshot đầy đủ và polling đối soát để phục hồi sau khi mất sự kiện.
- Để Spring Cloud LoadBalancer đảm nhiệm lựa chọn instance cho request thông thường; dùng cache giám sát riêng cho mục đích quan sát hoặc logic đã được thiết kế rõ.

Truy vấn định kỳ, watch và cache là ba cơ chế bổ trợ nhau. Polling giúp đối soát trạng thái theo chu kỳ; watch có thể rút ngắn thời gian nhận biết thay đổi khi registry hỗ trợ; cache giảm tải và tăng tốc truy cập nhưng cần TTL cùng giới hạn dữ liệu stale. Kết hợp đúng các cơ chế này giúp consumer theo kịp vòng đời instance và giảm nguy cơ định tuyến đến địa chỉ đã lỗi thời trong Spring Cloud Service Discovery.
