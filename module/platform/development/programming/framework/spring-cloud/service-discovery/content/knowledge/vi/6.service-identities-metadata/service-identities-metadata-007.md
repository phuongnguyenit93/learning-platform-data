# Phạm vi tên dịch vụ giữa môi trường và nhóm triển khai

Trong Spring Cloud Service Discovery, service ID là tên logic mà consumer dùng để tìm một nhóm instance. Ví dụ, các instance của inventory-service cùng đăng ký dưới service ID inventory-service; order-service tra cứu đúng tên này để lấy danh sách instance và gọi dịch vụ.

Khi hệ thống chỉ có một môi trường và một nhóm triển khai, việc đặt tên khá đơn giản. Nhưng khi dev, staging và production cùng tồn tại, hoặc một dịch vụ có blue/green, canary, nhiều region hay nhiều nhóm triển khai, cần xác định rõ phạm vi của tên dịch vụ. Nếu hai nhóm không liên quan vô tình đăng ký chung một service ID trong cùng registry, consumer có thể nhận cả hai nhóm trong một kết quả discovery. Điều này có thể khiến request đi nhầm môi trường hoặc phiên bản.

Bài viết trình bày cách tổ chức service ID theo môi trường, cách dùng metadata cho nhóm triển khai, và cách bảo đảm consumer chỉ nhìn thấy những instance thuộc phạm vi mong muốn.

## 1. Service ID có phạm vi trong registry

Service ID thường xác định một dịch vụ logic trong phạm vi mà registry đang quản lý. Registry gom các instance có cùng service ID thành một nhóm để consumer tra cứu.

Ví dụ:

~~~text
Service ID: inventory-service
  ├── Instance A: 10.0.1.11:8081
  ├── Instance B: 10.0.1.12:8081
  └── Instance C: 10.0.1.13:8081
~~~

Nếu cả ba instance đăng ký trong cùng registry và cùng service ID, một consumer tra cứu inventory-service có thể nhận cả ba. Registry không tự suy ra rằng Instance A thuộc staging còn Instance B thuộc production, trừ khi ranh giới đó được thể hiện bằng registry/namespace riêng hoặc được áp dụng qua một chính sách lọc rõ ràng.

Vì vậy, khi thiết kế tên dịch vụ, cần trả lời:

- Các ứng dụng đang đăng ký vào cùng một registry hay registry tách biệt?
- Những instance nào được phép xuất hiện trong cùng kết quả tra cứu?
- Consumer nào có quyền gọi các instance đó?
- Môi trường hoặc nhóm triển khai có phải là ranh giới cô lập bắt buộc không?

Tên dịch vụ chỉ có ý nghĩa trong phạm vi registry và cơ chế phân vùng đang dùng. Cùng một service ID có thể được dùng an toàn ở hai registry tách biệt, nhưng có thể gây trộn instance nếu hai môi trường cùng đăng ký vào một registry không có phân vùng phù hợp.

## 2. Phân biệt môi trường và nhóm triển khai

Môi trường và nhóm triển khai là hai chiều phân loại khác nhau.

| Khái niệm | Ví dụ | Mục đích |
|---|---|---|
| Môi trường | dev, test, staging, prod | Tách cấu hình, dữ liệu, quyền truy cập và vòng đời phát hành |
| Region hoặc zone | ap-southeast-1, zone-a, zone-b | Mô tả vị trí triển khai và hỗ trợ định tuyến theo địa lý |
| Nhóm triển khai | blue, green, canary | Phân biệt các nhóm phục vụ rollout hoặc thử nghiệm |
| Phiên bản ứng dụng | v1, v2, 2.4.1 | Nhận biết bản phát hành đang chạy |
| Instance | inventory-7f8c9d | Phân biệt một tiến trình/container cụ thể |

Không nên dùng một trường để biểu diễn tất cả các chiều này. Service ID xác định dịch vụ logic; instance ID định danh một bản chạy; metadata hoặc cơ chế phân vùng biểu diễn môi trường, vùng địa lý, nhóm triển khai và phiên bản khi cần.

~~~mermaid
flowchart TD
    ENV["Môi trường: production"]
    ENV --> S["Service ID: inventory-service"]
    S --> BLUE["Nhóm blue"]
    S --> GREEN["Nhóm green"]
    BLUE --> A["Instance A"]
    BLUE --> B["Instance B"]
    GREEN --> C["Instance C"]
    GREEN --> D["Instance D"]
~~~

Trong sơ đồ, blue và green là hai nhóm triển khai của cùng một service logic trong cùng môi trường. Consumer chỉ nên nhận cả hai nhóm khi chính sách rollout yêu cầu điều đó. Nếu consumer phải gọi riêng một nhóm, hệ thống cần có cách phân vùng hoặc lọc cụ thể.

## 3. Tách môi trường bằng registry hoặc namespace

Dev, staging và production thường cần được cô lập. Cách rõ ràng nhất là sử dụng registry riêng cho từng môi trường hoặc namespace/partition riêng nếu registry và phiên bản triển khai hỗ trợ.

~~~mermaid
flowchart LR
    subgraph DEV["Development"]
      D1["inventory-service"] --> DR[("Dev Registry")]
      DC["Dev Consumer"] --> DR
    end
    subgraph STG["Staging"]
      S1["inventory-service"] --> SR[("Staging Registry")]
      SC["Staging Consumer"] --> SR
    end
    subgraph PROD["Production"]
      P1["inventory-service"] --> PR[("Production Registry")]
      PC["Production Consumer"] --> PR
    end
~~~

Với cách này, cả ba môi trường có thể dùng cùng service ID inventory-service vì dữ liệu đăng ký không nằm chung một phạm vi. Consumer của production chỉ kết nối registry production; consumer staging chỉ kết nối registry staging.

Lợi ích của việc tách registry hoặc namespace:

- Tránh instance của môi trường thử nghiệm xuất hiện trong kết quả discovery của production.
- Có thể áp dụng ACL, network policy và thông tin xác thực riêng.
- Mỗi môi trường có thể thay đổi số lượng instance, metadata và cấu hình mà không ảnh hưởng môi trường khác.
- Giữ service ID ngắn gọn, ổn định và gần với tên nghiệp vụ.

Nếu dùng Consul Enterprise hoặc nền tảng có hỗ trợ namespace/partition, có thể tổ chức phạm vi đăng ký theo khả năng phân vùng của sản phẩm. Cần xác minh tính năng đó có trong phiên bản và edition đang vận hành; không giả định mọi registry đều có namespace hoặc partition tương đương.

### Cấu hình registry endpoint theo môi trường

Có thể giữ nguyên service ID và thay endpoint registry theo cấu hình môi trường. Ví dụ với Eureka:

~~~yaml
spring:
  application:
    name: inventory-service

eureka:
  client:
    service-url:
      defaultZone: ${DISCOVERY_REGISTRY_URL}
~~~

Mỗi môi trường cung cấp DISCOVERY_REGISTRY_URL riêng. Production nhận URL của Eureka production, staging nhận URL của Eureka staging. Không đặt URL production làm mặc định dùng chung cho mọi môi trường nếu điều đó có thể khiến ứng dụng thử nghiệm đăng ký nhầm.

Nếu registry được chia sẻ và không có namespace/partition, một lựa chọn khác là thêm tiền tố môi trường vào service ID, chẳng hạn:

| Môi trường | Service ID |
|---|---|
| Development | dev-inventory-service |
| Staging | stg-inventory-service |
| Production | prod-inventory-service |

Khi dùng tiền tố, provider và consumer phải thống nhất tên tương ứng. Ví dụ consumer production phải tra cứu prod-inventory-service. Có thể cấu hình tên qua biến môi trường hoặc profile, nhưng cần kiểm soát chặt để tránh sai cấu hình.

~~~yaml
spring:
  application:
    name: ${APP_SERVICE_ID:inventory-service}
~~~

Biến APP_SERVICE_ID được cấp riêng trong mỗi môi trường. Cách này linh hoạt, nhưng phải xác thực giá trị cấu hình khi khởi động và trong pipeline triển khai. Một giá trị mặc định không phù hợp có thể khiến service production đăng ký vào nhóm tên của môi trường khác.

## 4. Dùng metadata để phân biệt nhóm triển khai

Khi các nhóm blue/green, canary hoặc các zone cùng cung cấp một service logic trong một môi trường, có thể giữ nguyên service ID và gắn nhãn cho từng instance bằng metadata.

Ví dụ metadata:

~~~yaml
service-id: inventory-service
instance-id: inventory-prod-blue-01
metadata:
  environment: production
  deployment-group: blue
  version: v2
  zone: zone-a
~~~

Metadata giúp consumer, load balancer, gateway hoặc công cụ vận hành nhận biết thuộc tính của instance. Tuy nhiên, chỉ thêm metadata không tự động cô lập nhóm. Nếu consumer gọi inventory-service và discovery trả về mọi instance có service ID đó, consumer vẫn có thể nhận cả blue và green. Muốn chọn riêng một nhóm, phải cấu hình bộ lọc hoặc cơ chế định tuyến sử dụng metadata, hoặc dùng service ID/namespace riêng cho từng nhóm khi cần ranh giới cứng.

### Metadata trong Eureka

Với Spring Cloud Netflix Eureka Client, metadata có thể được khai báo bằng eureka.instance.metadata-map:

~~~yaml
spring:
  application:
    name: inventory-service

eureka:
  instance:
    metadata-map:
      environment: production
      deployment-group: blue
      version: v2
      zone: zone-a
~~~

Các thuộc tính này được gắn vào instance metadata theo cơ chế Eureka. Consumer có thể đọc metadata từ ServiceInstance để quan sát hoặc áp dụng bộ lọc riêng. Metadata không tự biến thành chính sách định tuyến nếu ứng dụng chưa cấu hình thành phần sử dụng nó.

### Tags và metadata trong Consul

Spring Cloud Consul Discovery hỗ trợ service tags và metadata. Ví dụ cấu hình minh họa:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      discovery:
        service-name: inventory-service
        tags:
          - environment=production
          - deployment-group=blue
          - version=v2
        metadata:
          zone: zone-a
          release-track: stable
~~~

Tags và metadata được công bố cùng đăng ký service theo cách mà Consul integration hỗ trợ. Cần kiểm tra phiên bản Spring Cloud Consul đang dùng để xác nhận thuộc tính và cách truy vấn phù hợp. Consumer hoặc công cụ định tuyến phải chủ động sử dụng các nhãn này; không nên giả định việc tra cứu theo service-name sẽ tự lọc theo tag.

## 5. Khi nào đưa nhóm triển khai vào service ID?

Không có một quy tắc đặt tên duy nhất cho mọi kiến trúc. Quyết định phụ thuộc vào việc nhóm triển khai có phải là một đích gọi độc lập hay chỉ là thuộc tính của instance.

| Tình huống | Cách tổ chức phù hợp |
|---|---|
| Dev và production dùng registry riêng | Dùng cùng service ID ở mỗi registry |
| Dev và production dùng chung registry, không có phân vùng | Dùng tiền tố môi trường hoặc tạo ranh giới registry |
| Blue/green cùng cung cấp một API trong production và consumer được phép dùng cả hai | Cùng service ID, metadata phân biệt nhóm |
| Canary chỉ nhận một tỷ lệ request có kiểm soát | Cùng service ID nếu load balancer/gateway có chính sách phân phối canary; metadata hỗ trợ nhận diện |
| Consumer phải gọi riêng nhóm blue hoặc green | Dùng service ID riêng cho từng nhóm hoặc bộ lọc định tuyến có kiểm soát |
| Các nhóm có hợp đồng API hoặc vòng đời độc lập | Cân nhắc service ID riêng vì chúng là các đích logic khác nhau |
| Nhiều zone cùng cung cấp một dịch vụ | Cùng service ID, metadata zone và chính sách ưu tiên vùng |

Nếu nhóm triển khai chỉ là cách phát hành tạm thời, không nên biến mọi nhãn triển khai thành một service ID mới nếu consumer không cần phân biệt. Ngược lại, nếu hai nhóm có ranh giới truy cập hoặc hợp đồng khác nhau, việc dùng chung service ID có thể làm consumer khó chọn đúng đích.

## 6. Ví dụ triển khai blue/green

Giả sử production có hai nhóm inventory-service:

~~~text
Service ID: inventory-service

Blue:
  inventory-prod-blue-01  version=v1  zone-a
  inventory-prod-blue-02  version=v1  zone-b

Green:
  inventory-prod-green-01 version=v2  zone-a
  inventory-prod-green-02 version=v2  zone-b
~~~

Trong giai đoạn kiểm thử green, consumer thông thường có thể tiếp tục gọi nhóm blue. Một gateway hoặc load balancer được cấu hình để chỉ chọn nhóm blue cho lưu lượng chính; một luồng kiểm thử riêng có thể chọn green. Sau khi xác minh, chính sách định tuyến chuyển dần lưu lượng sang green. Khi hoàn tất, nhóm blue được deregister và dừng theo quy trình rollout.

Có hai cách tổ chức phổ biến:

**Một service ID, metadata phân nhóm.** Tất cả instance đăng ký inventory-service. Gateway hoặc bộ lọc tùy chỉnh chỉ chọn instance có deployment-group phù hợp. Cách này giữ một danh tính dịch vụ logic nhưng đòi hỏi chính sách lọc được triển khai và kiểm thử cẩn thận.

**Service ID riêng cho mỗi nhóm.** Blue đăng ký inventory-service-blue, green đăng ký inventory-service-green. Consumer hoặc gateway chọn đúng service ID. Cách này làm ranh giới dễ nhìn và dễ kiểm soát hơn, nhưng tên nhóm trở thành một phần của giao diện discovery và cần được quản lý trong cấu hình consumer.

Không nên chỉ dựa vào thứ tự instance trả về từ registry để chọn blue hoặc green. Thứ tự không phải hợp đồng định tuyến ổn định. Hãy dùng metadata cùng chính sách lọc rõ ràng hoặc service ID riêng.

## 7. Bảo đảm consumer không gọi nhầm môi trường

Sai phạm vi service ID có thể gây rủi ro lớn hơn một lỗi định tuyến thông thường. Consumer production gọi nhầm instance staging có thể đọc dữ liệu thử nghiệm hoặc gửi thao tác ghi đến hệ thống không dành cho production.

Các biện pháp nên áp dụng:

- Tách registry endpoint, namespace hoặc partition giữa môi trường nếu có thể.
- Nếu dùng chung registry, dùng tiền tố service ID rõ ràng và kiểm tra cấu hình khi khởi động.
- Dùng ACL hoặc thông tin xác thực giới hạn provider/consumer trong đúng phạm vi.
- Áp dụng network policy để consumer production không thể truy cập endpoint của staging nếu không có lý do hợp lệ.
- Đưa environment vào metadata để quan sát và kiểm tra chéo, nhưng không xem metadata là ranh giới bảo mật duy nhất.
- Kiểm tra service ID và registry endpoint trong pipeline trước khi triển khai.
- Theo dõi các instance có environment hoặc deployment-group không đúng quy ước.

Metadata do provider đăng ký có thể sai hoặc bị giả mạo nếu không có kiểm soát. Vì vậy, quyền đăng ký, xác thực client và phân đoạn mạng quan trọng hơn việc chỉ gắn nhãn. Không dùng metadata như cơ chế cấp quyền độc lập.

## 8. Kiểm tra phạm vi tên dịch vụ trong thực tế

Khi triển khai một service mới hoặc thêm nhóm rollout, có thể kiểm tra theo trình tự:

1. Xác nhận môi trường đang chạy và registry endpoint mà ứng dụng sẽ kết nối.
2. Kiểm tra service ID cuối cùng sau khi áp dụng profile, biến môi trường và cấu hình ngoài.
3. Xác nhận instance ID duy nhất trong phạm vi registry.
4. Kiểm tra metadata environment, region, zone, deployment-group và version.
5. Tra cứu service ID từ đúng consumer và xác nhận danh sách chỉ chứa instance dự kiến.
6. Kiểm tra chính sách load balancing hoặc gateway có lọc đúng nhóm hay không.
7. Thử rollout một instance mới, xác nhận nó xuất hiện đúng phạm vi, rồi thực hiện deregister instance cũ.
8. Kiểm tra ACL và network policy để xác nhận consumer không có quyền gọi nhầm môi trường.

Một số câu hỏi chẩn đoán hữu ích:

| Hiện tượng | Điểm cần kiểm tra |
|---|---|
| Consumer nhận instance của môi trường khác | Registry endpoint, namespace/partition và service ID |
| Consumer thấy cả blue và green | Metadata có được gắn không, bộ lọc có thực sự dùng metadata không |
| Hai instance ghi đè hoặc trùng định danh | Instance ID và quy tắc tạo ID |
| Consumer không thấy instance mới | Đăng ký provider, quyền registry và độ trễ refresh/cache |
| Chỉ một số consumer gọi sai nhóm | Cấu hình service ID, profile, metadata filter và chính sách load balancer |

## 9. Nguyên tắc đặt tên và tổ chức phạm vi

- Giữ service ID ổn định theo chức năng nghiệp vụ khi các instance cùng cung cấp một dịch vụ.
- Tách registry hoặc namespace theo môi trường để ngăn trộn dữ liệu discovery.
- Chỉ thêm tiền tố môi trường vào service ID khi phải dùng chung registry mà không có cơ chế phân vùng phù hợp.
- Dùng instance ID để phân biệt tiến trình; không dùng instance ID làm tên dịch vụ logic.
- Dùng metadata cho zone, region, version và nhóm rollout khi cần quan sát hoặc định tuyến.
- Không giả định metadata tự lọc instance; cấu hình consumer, gateway hoặc load balancer để áp dụng chính sách rõ ràng.
- Dùng service ID riêng khi nhóm triển khai cần được gọi như một đích logic độc lập hoặc cần ranh giới truy cập cứng.
- Kết hợp registry scope với ACL và network policy; không dựa vào quy ước tên để bảo vệ hệ thống.
- Kiểm tra service ID cuối cùng và registry endpoint trong từng môi trường trước khi rollout.

Một quy ước tên tốt giúp người vận hành hiểu service đang thuộc phạm vi nào, nhưng ranh giới thực tế được quyết định bởi registry/namespace, quyền truy cập và chính sách định tuyến. Trong Spring Cloud, hãy dùng service ID cho danh tính logic, instance ID cho từng bản chạy và metadata cho các thuộc tính triển khai. Khi các phạm vi được thiết kế rõ ràng, discovery có thể mở rộng qua nhiều môi trường, region và nhóm rollout mà không làm consumer gọi nhầm instance.
