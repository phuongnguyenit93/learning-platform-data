# Chữ hoa, chữ thường và ánh xạ cấu hình defaultZone

Khi một ứng dụng Spring Cloud Netflix Eureka khởi động, Eureka Client cần biết địa chỉ của Eureka Server để đăng ký instance và tải danh sách dịch vụ. Địa chỉ này thường được cấu hình qua khóa eureka.client.serviceUrl.defaultZone. Một lỗi nhỏ về chữ hoa, chữ thường trong defaultZone có thể khiến client không nhận được URL đã khai báo và tiếp tục thử kết nối tới địa chỉ mặc định localhost:8761.

Nguyên nhân nằm ở cách ánh xạ cấu hình: serviceUrl là một Map<String, String>, còn defaultZone là khóa của Map đó. Khóa Map được so khớp theo đúng chuỗi, vì vậy defaultZone phải giữ nguyên chữ Z viết hoa. Quy tắc này khác với relaxed binding thông thường của các thuộc tính JavaBean trong Spring Boot.

## 1. Vai trò của defaultZone

Eureka Client có hai nhiệm vụ chính:

- Đăng ký thông tin instance hiện tại với Eureka Server, nếu register-with-eureka được bật.
- Lấy registry để tìm các instance của service khác, nếu fetch-registry được bật.

Cả hai luồng đều cần địa chỉ Eureka Server. Spring Cloud Netflix lưu các địa chỉ này trong thuộc tính serviceUrl, có kiểu Map<String, String>. Mỗi khóa Map biểu diễn một availability zone và giá trị là URL hoặc danh sách URL của Eureka Server trong zone đó.

defaultZone là khóa dự phòng đặc biệt. Khi client không có zone cụ thể phù hợp, nó dùng giá trị defaultZone để tìm Eureka Server. Đây là lý do tài liệu Spring Cloud sử dụng đúng dạng camel case này.

Ví dụ tối thiểu:

    eureka:
      client:
        serviceUrl:
          defaultZone: http://localhost:8761/eureka/

Trong ví dụ, URL của Eureka Server là http://localhost:8761/eureka/. Nếu ứng dụng chạy trong container, localhost trỏ tới chính container ứng dụng. Khi Eureka Server chạy ở container khác trong cùng Docker network, cần dùng DNS service name của container Eureka, ví dụ http://eureka-server:8761/eureka/.

## 2. Vì sao defaultZone phân biệt hoa thường?

Spring Boot hỗ trợ relaxed binding cho tên thuộc tính thông thường. Ví dụ một thuộc tính JavaBean tên serviceUrl có thể được biểu diễn theo các dạng tên thuộc tính tương ứng như service-url hoặc serviceUrl trong các nguồn cấu hình được hỗ trợ.

Tuy nhiên, defaultZone không phải tên một thuộc tính JavaBean riêng. Nó là khóa nằm bên trong Map serviceUrl. Spring Cloud Netflix tra cứu khóa mặc định bằng chuỗi defaultZone. Vì vậy các chuỗi sau là những khóa khác nhau:

| Khóa được khai báo | Có phải khóa fallback chuẩn? | Giải thích |
|---|---|---|
| defaultZone | Có | Đúng camel case, chữ Z viết hoa |
| defaultzone | Không | Chữ z thường, là khóa khác |
| default-zone | Không | Có dấu gạch nối, là khóa khác |
| DEFAULTZONE | Không | Toàn bộ chữ hoa, là khóa khác |
| DefaultZone | Không | Chữ D viết hoa, là khóa khác |

Đừng áp dụng máy móc quy tắc kebab-case của Spring Boot cho tên khóa này. Tài liệu Spring Cloud Netflix nêu rõ defaultZone có phân biệt chữ hoa, chữ thường vì serviceUrl là Map<String, String>; nó không tuân theo quy ước snake-case thông thường của Spring Boot.

## 3. Khai báo đúng trong application.yml

Cấu hình YAML chuẩn:

    spring:
      application:
        name: order-service

    eureka:
      client:
        serviceUrl:
          defaultZone: http://localhost:8761/eureka/
        register-with-eureka: true
        fetch-registry: true

Các phần cần chú ý:

- spring.application.name là tên logic của ứng dụng; Eureka dùng nó làm service ID mặc định nếu không cấu hình tên khác.
- eureka.client.serviceUrl là Map địa chỉ server theo zone.
- defaultZone phải viết đúng chữ Z hoa.
- register-with-eureka điều khiển việc instance hiện tại có đăng ký với Eureka hay không.
- fetch-registry điều khiển việc client tải danh sách instance từ Eureka.

Trong YAML, thụt lề quyết định cấu trúc. defaultZone phải là phần tử con của serviceUrl, nằm trong eureka.client. Nếu đặt sai cấp, Binder có thể tạo một thuộc tính khác hoặc không bind được giá trị vào Map mong muốn.

## 4. Khai báo đúng trong application.properties

Với file properties, dùng tên khóa đầy đủ:

    spring.application.name=order-service
    eureka.client.serviceUrl.defaultZone=http://localhost:8761/eureka/
    eureka.client.register-with-eureka=true
    eureka.client.fetch-registry=true

Có thể dùng cấu hình properties khi muốn giữ nguyên chính xác chuỗi khóa Map và dễ kiểm tra từng dòng. Điều quan trọng vẫn là phần cuối phải là defaultZone, không phải default-zone hoặc defaultzone.

Cấu hình tương đương trong YAML và properties phải tạo ra cùng một Map key:

    serviceUrl = {
        "defaultZone": "http://localhost:8761/eureka/"
    }

Đây là cách hiểu hữu ích khi chẩn đoán lỗi: không chỉ kiểm tra chuỗi URL, mà phải kiểm tra URL đã được gắn vào đúng khóa Map hay chưa.

## 5. Cấu hình sai thường gặp

Ví dụ sai thứ nhất:

    eureka:
      client:
        serviceUrl:
          default-zone: http://localhost:8761/eureka/

default-zone là một khóa Map khác. Relaxed binding không tự đổi khóa Map này thành defaultZone theo ý nghĩa đặc biệt của Eureka.

Ví dụ sai thứ hai:

    eureka:
      client:
        serviceUrl:
          defaultzone: http://localhost:8761/eureka/

defaultzone viết thường chữ z nên không khớp khóa fallback.

Ví dụ sai thứ ba:

    eureka:
      client:
        serviceUrl:
          DEFAULTZONE: http://localhost:8761/eureka/

DEFAULTZONE cũng là một khóa khác. Eureka không tự chuẩn hóa tất cả các khóa Map về cùng một kiểu chữ.

Nếu khóa defaultZone bị thiếu hoặc không được bind đúng, Eureka Client có thể dùng URL mặc định localhost:8761/eureka/. Khi đó log thường thể hiện client đang cố kết nối tới localhost dù cấu hình mong muốn trỏ tới hostname khác.

## 6. Bẫy khi dùng biến môi trường

Biến môi trường thường được dùng để truyền cấu hình vào Docker, Kubernetes hoặc môi trường CI/CD. Với thuộc tính đơn, Spring Boot có quy tắc chuyển đổi tên thuộc tính sang dạng chữ hoa và dấu gạch dưới. Ví dụ:

    eureka.client.enabled
    EUREKA_CLIENT_ENABLED

Nhưng serviceUrl là Map. Spring Boot ghi rõ rằng khi bind biến môi trường vào thuộc tính Map, tên khóa Map được chuyển thành chữ thường. Vì vậy, biến môi trường:

    EUREKA_CLIENT_SERVICEURL_DEFAULTZONE

có thể tạo khóa Map defaultzone. Khóa này không khớp defaultZone mà Eureka cần. Đây là nguyên nhân phổ biến khiến các cấu hình biến môi trường khác hoạt động nhưng Eureka Client vẫn kết nối localhost:8761.

Đối với khóa Map đặc biệt này, nên ưu tiên khai báo bằng application.yml hoặc application.properties. Nếu cần truyền cấu hình qua biến môi trường, có thể dùng SPRING_APPLICATION_JSON để giữ nguyên chữ hoa trong tên khóa JSON:

    SPRING_APPLICATION_JSON={"eureka":{"client":{"serviceUrl":{"defaultZone":"http://eureka-server:8761/eureka/"}}}}

Ví dụ trong Docker Compose:

    services:
      order-service:
        image: example/order-service
        environment:
          SPRING_APPLICATION_JSON: >-
            {"eureka":{"client":{"serviceUrl":{"defaultZone":"http://eureka-server:8761/eureka/"}}}}

JSON property source giữ nguyên tên khóa defaultZone trong nội dung JSON. Hãy xác minh cấu hình thực tế trong ứng dụng sau khi khởi động, đặc biệt khi đồng thời có application.yml, profile và biến môi trường.

Một lựa chọn khác là truyền JVM system property với đúng tên khóa:

    java -Deureka.client.serviceUrl.defaultZone=http://eureka-server:8761/eureka/ -jar order-service.jar

System property cho phép giữ nguyên camel case. Dù chọn cách nào, không nên giả định tên biến môi trường EUREKA_CLIENT_SERVICEURL_DEFAULTZONE luôn tương đương hoàn toàn với khóa Map defaultZone.

## 7. Dùng defaultZone với nhiều Eureka Server

Một giá trị trong serviceUrl có thể chứa một URL hoặc danh sách URL phân tách bằng dấu phẩy. Điều này cho phép client có nhiều địa chỉ để thử kết nối khi một Eureka Server không truy cập được.

Ví dụ:

    eureka:
      client:
        serviceUrl:
          defaultZone: http://eureka-1:8761/eureka/,http://eureka-2:8761/eureka/

Các URL cần trỏ tới những Eureka Server có thể trao đổi registry với nhau theo kiến trúc peer-aware. Cấu hình nhiều URL không tự tạo replication; các Eureka Server vẫn cần được cấu hình peer replication đúng cách.

Nếu triển khai Eureka Server độc lập và không muốn server tự đăng ký hoặc tải registry từ peer, có thể cấu hình:

    eureka:
      client:
        register-with-eureka: false
        fetch-registry: false

Đối với Eureka Client thông thường, hai thuộc tính này thường được giữ true để client vừa đăng ký instance của mình vừa tra cứu dịch vụ khác.

## 8. Zone, region và khóa fallback

Trong triển khai nhiều zone, Eureka Client có thể dùng region và availability zone để xác định nhóm Eureka Server ưu tiên. Map serviceUrl chứa các URL theo tên zone. Nếu không tìm được zone phù hợp cho client, defaultZone đóng vai trò fallback.

Ví dụ minh họa:

    eureka:
      client:
        region: ap-southeast-1
        availability-zones:
          ap-southeast-1: zone-a,zone-b
        serviceUrl:
          zone-a: https://eureka-a.internal/eureka/
          zone-b: https://eureka-b.internal/eureka/
          defaultZone: https://eureka-default.internal/eureka/

Các tên zone là khóa Map nên phải khớp với tên zone mà cấu hình availability-zones trả về. defaultZone vẫn phải viết đúng camel case. Khi thiết kế nhiều zone, cần xác định rõ region, zone của instance và zone mà client sử dụng; nếu chỉ có một Eureka Server, cấu hình defaultZone thường là đủ.

## 9. Kiểm tra cấu hình đã được áp dụng

Khi client không kết nối được Eureka Server, hãy kiểm tra theo trình tự:

1. **Kiểm tra đúng khóa:** xác nhận cấu hình có eureka.client.serviceUrl.defaultZone với chữ Z viết hoa.
2. **Kiểm tra vị trí trong YAML:** serviceUrl phải nằm trong eureka.client; defaultZone phải nằm trong serviceUrl.
3. **Kiểm tra nguồn cấu hình:** xác định profile đang hoạt động và các nguồn có thể ghi đè URL như biến môi trường, JVM system property hoặc command-line argument.
4. **Kiểm tra log:** tìm URL Eureka Client đang sử dụng và lỗi kết nối. Nếu log vẫn nhắc localhost:8761, hãy kiểm tra xem defaultZone có được bind đúng không.
5. **Kiểm tra mạng:** gọi URL từ đúng môi trường chạy ứng dụng. Trong container, dùng service name hoặc DNS mà container có thể phân giải thay cho localhost của host.
6. **Kiểm tra endpoint server:** Eureka Server phải đang chạy và cung cấp context path phù hợp, thường là /eureka/.
7. **Kiểm tra nhiều URL:** xác nhận từng URL trong danh sách phân tách bằng dấu phẩy có thể truy cập và thuộc cùng cụm Eureka mong muốn.

Có thể bật log chi tiết hơn trong lúc chẩn đoán:

    logging:
      level:
        com.netflix.discovery: DEBUG
        org.springframework.cloud.netflix.eureka: DEBUG

Chỉ nên bật DEBUG trong thời gian điều tra vì log có thể tăng đáng kể. Tắt hoặc hạ mức log sau khi xác nhận cấu hình.

Không nên expose endpoint env hoặc configprops ra mạng công khai chỉ để xem cấu hình. Nếu cần kiểm tra effective configuration qua Actuator, hãy giới hạn quyền truy cập và chỉ thực hiện trong môi trường được kiểm soát.

## 10. Ví dụ thực hành hoàn chỉnh

Giả sử Eureka Server chạy trong Docker Compose với service name eureka-server và port 8761. Client order-service cùng nằm trên một Docker network. Cấu hình YAML của client:

    spring:
      application:
        name: order-service

    server:
      port: 8080

    eureka:
      client:
        serviceUrl:
          defaultZone: http://eureka-server:8761/eureka/
        register-with-eureka: true
        fetch-registry: true
        registry-fetch-interval-seconds: 10

Trong ví dụ này:

- defaultZone giữ đúng chữ Z viết hoa.
- eureka-server là DNS service name mà container client có thể phân giải.
- Cổng 8761 là cổng Eureka Server bên trong Docker network.
- /eureka/ là context path của Eureka Server.
- order-service đăng ký với Eureka và tải registry định kỳ.

Sau khi khởi động, xác minh theo ba lớp:

- **Kết nối:** log không còn lỗi kết nối tới localhost:8761; client truy cập được eureka-server.
- **Đăng ký:** Eureka Dashboard hiển thị instance ORDER-SERVICE với host và port mong muốn.
- **Tra cứu:** một Eureka DiscoveryClient khác có thể tìm thấy ORDER-SERVICE bằng service ID.

Nếu client vẫn dùng localhost, kiểm tra lại tên khóa Map và nguồn cấu hình ghi đè trước khi thay đổi network.

## 11. Kết luận

defaultZone là khóa fallback trong Map serviceUrl của Eureka Client. Chữ Z phải viết hoa chính xác vì đây là khóa Map được Eureka tra cứu, không phải một thuộc tính JavaBean được relaxed binding tự chuẩn hóa. Hãy dùng dạng canonical eureka.client.serviceUrl.defaultZone trong properties hoặc serviceUrl.defaultZone trong YAML.

Đặc biệt cẩn thận khi chuyển cấu hình sang biến môi trường: Spring Boot chuyển khóa Map bind từ environment variable thành chữ thường, có thể biến defaultZone thành defaultzone. Dùng file cấu hình, JVM system property hoặc SPRING_APPLICATION_JSON khi cần giữ nguyên tên khóa; sau đó kiểm tra URL thực tế trong log và xác nhận client kết nối tới đúng Eureka Server.

## Tài liệu tham khảo

- [Spring Cloud Netflix — Eureka Client: Registering with Eureka](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Boot — Externalized Configuration: Binding Maps From Environment Variables](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Cloud Netflix — EurekaClientConfigBean](https://github.com/spring-cloud/spring-cloud-netflix/blob/main/spring-cloud-netflix-eureka-client/src/main/java/org/springframework/cloud/netflix/eureka/EurekaClientConfigBean.java)

