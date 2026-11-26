# Nguy cơ đưa dữ liệu nhạy cảm vào metadata công khai

Trong chương **ServiceInstance và cổng** của module **SPRING_CLOUD_KUBERNETES**, metadata giúp mô tả một instance để các thành phần khám phá và gọi dịch vụ sử dụng. Khi đưa label, annotation hoặc thuộc tính tùy biến vào metadata, bạn đồng thời quyết định dữ liệu nào được chuyển tới những bên tiêu thụ thông tin khám phá.

Nếu metadata chứa token, thông tin kết nối có mật khẩu, dữ liệu khách hàng hoặc chi tiết hạ tầng không cần thiết, một tiện ích quan sát có thể trở thành đường phát tán dữ liệu. Rủi ro tăng khi ứng dụng trả nguyên `ServiceInstance` qua API, ghi toàn bộ đối tượng vào log hoặc chuyển metadata sang hệ thống giám sát có nhiều người đọc.

Bài học hướng dẫn xác định ranh giới dữ liệu, giới hạn thông tin được công bố, sử dụng Secret đúng mục đích và kiểm chứng việc lọc metadata. Các ví dụ dùng dữ liệu giả; không cần dùng bí mật thật để thử một đường rò rỉ.

Sau bài học, bạn có thể:

- Phân biệt metadata phục vụ khám phá với dữ liệu cấu hình riêng của ứng dụng.
- Giải thích vì sao quyền đọc Secret không bảo vệ một giá trị đã bị sao chép sang Service hoặc log.
- Nhận diện các đường công bố metadata ngoài phạm vi dự kiến.
- Thiết kế danh sách cho phép theo cả key và giá trị.
- Tắt việc bổ sung metadata không cần thiết mà vẫn giữ các trường phục vụ discovery đúng mục đích.
- Lập cách kiểm tra và xử lý khi dữ liệu đã bị lộ.

## 1. “Công khai” cần được hiểu theo đối tượng được quyền đọc

Trong bài này, metadata được **công bố** khi một thành phần đưa nó cho bên tiêu thụ khác đọc. Điều đó không mặc định có nghĩa dữ liệu đã xuất hiện trên Internet.

Một Service có thể chỉ được đọc trong cluster, nhưng dữ liệu của nó vẫn đi tới nhiều nhóm người và hệ thống hơn so với bí mật ứng dụng ban đầu.

| Phạm vi | Ví dụ bên đọc | Câu hỏi cần trả lời |
| --- | --- | --- |
| Kubernetes API | ServiceAccount có quyền đọc Service | Đọc Service có đồng thời đọc được label và annotation nhạy cảm không? |
| Discovery nội bộ | Ứng dụng gọi dịch vụ, DiscoveryServer | Bên gọi có cần biết các thuộc tính đó không? |
| Công cụ vận hành | Dashboard, API chẩn đoán, hỗ trợ kỹ thuật | Ai có thể xem hoặc xuất dữ liệu? |
| Hệ thống lưu trữ quan sát | Log tập trung, tracing, báo cáo lỗi | Dữ liệu được nhân bản và giữ lại ở đâu? |
| API cho bên ngoài | Client của API công khai | Hợp đồng API có thật sự cần tiết lộ cấu trúc instance không? |

Việc một endpoint chỉ mở trong mạng nội bộ không tự làm mọi giá trị bên trong phù hợp để công bố. Cần so người được đọc dữ liệu với người được phép sử dụng bí mật gốc.

Ngược lại, không phải mọi metadata đều nhạy cảm. Một giá trị như `release-channel=stable` có thể hữu ích và được phép chia sẻ trong hệ thống. Quyết định cần dựa trên mục đích, người đọc và mức độ chi tiết, thay vì cấm toàn bộ metadata hoặc mặc định mọi thứ đều vô hại.

## 2. ServiceInstance chứa những gì và dữ liệu có thể đến từ đâu?

Ở mức giao diện Spring Cloud, `ServiceInstance` mô tả một instance bằng các thông tin như:

```java
instance.getServiceId();
instance.getHost();
instance.getPort();
instance.isSecure();
instance.getMetadata();
```

`getMetadata()` trả về map các cặp key–value. Tùy implementation và cấu hình Spring Cloud Kubernetes, map này có thể chứa thông tin được suy ra hoặc bổ sung từ Service, label, annotation, cổng và dữ liệu liên quan.

Không coi map đó là kho cấu hình riêng của tiến trình. Những dữ liệu được thêm vào có thể được mọi bên tiêu thụ cùng luồng discovery quan sát.

Các nhóm dữ liệu phải được phân biệt:

| Nhóm | Ví dụ | Cách sử dụng phù hợp |
| --- | --- | --- |
| Thông tin định vị instance | Host, cổng, service ID | Dùng trong luồng gọi dịch vụ được kiểm soát. |
| Metadata phục vụ lựa chọn đích | Kênh phát hành, phiên bản API đã chuẩn hóa | Chỉ công bố nếu bên gọi cần và có hợp đồng rõ ràng. |
| Cấu hình nội bộ | URL đối tác, tên cụm dữ liệu | Phân loại trước khi chia sẻ; không tự động coi là metadata discovery. |
| Bí mật | Mật khẩu, API token, private key | Giữ ở nguồn bí mật và chỉ cấp cho workload cần dùng. |

Host và port nằm ngoài map metadata vẫn có thể tiết lộ cấu trúc hạ tầng. Việc lọc sạch `getMetadata()` không có nghĩa trả nguyên đối tượng `ServiceInstance` cho một API công khai là phù hợp.

Spring Cloud Kubernetes không tự động biến mọi giá trị trong Secret thành metadata. Đường rò rỉ xuất hiện khi con người, template triển khai, mã ứng dụng hoặc một thành phần tích hợp sao chép giá trị nhạy cảm sang nơi được công bố rộng hơn.

## 3. Labels và annotations không phải nơi cất bí mật

Label dùng để tổ chức, chọn và liên kết tài nguyên. Annotation chứa metadata bổ sung, thường tự do hơn về nội dung. Sự khác nhau về cú pháp và mục đích này không tạo ra ranh giới bảo mật cho annotation.

Ví dụ sau minh họa một thiết kế sai. Các giá trị bắt đầu bằng `DEMO_ONLY` là dữ liệu giả:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: commerce
  labels:
    app: catalog
  annotations:
    integration.example.com/access-token: "DEMO_ONLY_NOT_A_REAL_TOKEN"
    integration.example.com/connection: "https://demo-user:DEMO_ONLY_PASSWORD@partner.example.invalid/api"
spec:
  selector:
    app: catalog
  ports:
    - name: http
      port: 80
      targetPort: 8080
```

Hai annotation làm dữ liệu cần bảo vệ đi cùng đối tượng Service. Bất kỳ bên nào được quyền đọc đầy đủ Service đó qua Kubernetes API cũng có thể nhìn thấy chúng, dù bên đó không được quyền đọc Secret của ứng dụng.

Nếu annotation tiếp tục được đưa vào `ServiceInstance.getMetadata()`, phạm vi phát tán có thể mở rộng tới các ứng dụng hoặc công cụ chỉ được cấp dữ liệu discovery.

### 3.1. RBAC thông thường không che riêng một annotation

Quyền `get`, `list` hoặc `watch` trên Service áp dụng theo cơ chế RBAC của tài nguyên. Không mặc định rằng một người chỉ đọc được `spec.ports` nhưng không đọc được một annotation có tên chứa `secret`.

Một bộ lọc discovery phía ứng dụng cũng không thay đổi quyền Kubernetes API đã cấp. Nếu ServiceAccount vẫn có quyền đọc Service chứa annotation nhạy cảm, tắt việc xuất annotation vào metadata chỉ chặn một đường truyền tiếp; nó không xóa dữ liệu khỏi Service.

### 3.2. Đổi vị trí hoặc đổi tên không làm dữ liệu bớt nhạy cảm

Các thao tác sau không phải biện pháp bảo vệ bí mật:

- Chuyển token từ label sang annotation.
- Đổi key thành `internal-token`, `private-value` hoặc một tên khó đoán.
- Thêm prefix vào key metadata.
- Base64 giá trị rồi tiếp tục công bố nó.
- Chỉ ẩn giá trị trên giao diện trong khi response API vẫn chứa đầy đủ.

Base64 là cách biểu diễn dữ liệu, không phải mã hóa để giữ bí mật. Một chuỗi đã được encode vẫn có thể là thông tin xác thực sử dụng được sau khi decode.

## 4. Những loại dữ liệu cần loại khỏi metadata được chia sẻ

Một chính sách thực tế cần bao quát cả bí mật trực tiếp và thông tin không cần công bố.

| Loại dữ liệu | Ví dụ | Nguy cơ hoặc lý do cần hạn chế |
| --- | --- | --- |
| Thông tin xác thực | API token, bearer token, mật khẩu, private key | Bên đọc có thể sử dụng để truy cập hệ thống khác. |
| Chuỗi kết nối có credential | JDBC URL hoặc URL có user/password | Giá trị trông như cấu hình nhưng chứa bí mật. |
| URL mang quyền truy cập | URL có chữ ký, query chứa token | Người có URL có thể có quyền cho tới khi hết hạn hoặc bị thu hồi. |
| Dữ liệu người dùng | Email, số điện thoại, định danh khách hàng | Phát tán sang bên không cần dữ liệu đó. |
| Chi tiết vận hành | Tên cụm nội bộ, đường dẫn quản trị, topology chi tiết | Tăng mức độ lộ thông tin nếu không cần cho bên tiêu thụ. |
| Toàn bộ cấu hình | JSON hoặc YAML nhúng trong annotation | Dễ chứa thêm bí mật khi cấu hình được mở rộng sau này. |

Không chỉ dò tên key chứa `password` hoặc `secret`. Một key chung như `url`, `config`, `context` hay `note` vẫn có thể chứa token. Ngược lại, tên key có từ nhạy cảm không phải bằng chứng rằng giá trị thực tế là bí mật. Cần kết hợp quy tắc thiết kế và kiểm tra nội dung phù hợp.

Ngay cả giá trị đã che một phần cũng cần cân nhắc. Bốn ký tự cuối của token hoặc một định danh được rút gọn vẫn có thể giúp liên kết dữ liệu giữa các hệ thống. Nếu không cần thông tin đó, không công bố sẽ đơn giản hơn việc nghĩ ra một cách che không rõ mục đích.

## 5. Đường rò rỉ thường bắt đầu từ một thao tác tiện lợi

### 5.1. Trả nguyên ServiceInstance qua API chẩn đoán

Đoạn mã sau là ví dụ cần tránh khi endpoint được cho phép truy cập rộng mà không có thiết kế dữ liệu phù hợp:

```java
@GetMapping("/debug/discovery/{serviceId}")
public List<ServiceInstance> instances(@PathVariable String serviceId) {
    return discoveryClient.getInstances(serviceId);
}
```

Endpoint này do ứng dụng tự tạo, không phải một endpoint mặc định được bảo đảm tồn tại trong mọi ứng dụng Spring Cloud Kubernetes.

Khi serializer chuyển đối tượng thành JSON, response có thể chứa metadata và các thuộc tính định vị instance. Việc endpoint có chữ `debug` trong đường dẫn không hạn chế ai được đọc nó. Xác thực giúp kiểm soát người truy cập, nhưng nội dung trả về vẫn cần được tối thiểu hóa theo nhiệm vụ của người đó.

### 5.2. Ghi toàn bộ metadata vào log hoặc trace

```java
// Không dùng với metadata chưa được phân loại.
log.info("discovery metadata={}", instance.getMetadata());
```

Log thường được tập trung, lập chỉ mục và chia sẻ với nhiều nhóm. Một token bị ghi vào log có thể tồn tại lâu hơn Pod đã tạo log. Tương tự, thêm toàn bộ metadata vào span attribute, nhãn metric hoặc báo cáo lỗi làm dữ liệu đi sang những hệ thống khác.

Các giá trị nhiều biến thể như token, email hoặc toàn bộ URL cũng có thể gây tăng số lượng giá trị nhãn metric. Không chuyển cả map metadata thành nhãn quan sát chỉ để dễ tìm kiếm.

### 5.3. Template triển khai sao chép cấu hình hàng loạt

Một template có thể nhận map cấu hình rồi đổ toàn bộ vào annotation hoặc metadata. Ban đầu map chỉ có `release-channel`; sau đó một người thêm credential vào cùng nguồn dữ liệu và template tiếp tục sao chép mà không phân loại.

Tránh cơ chế “sao chép tất cả rồi che vài key”. Cần có nguồn dữ liệu hoặc phép ánh xạ riêng cho phần được phép chia sẻ.

### 5.4. Nhiều lớp trung gian giữ bản sao

```text
Nguồn cấu hình hoặc thao tác triển khai
    -> label / annotation trên Service
    -> metadata do discovery bổ sung
    -> DiscoveryServer hoặc ứng dụng tiêu thụ
    -> API chẩn đoán / log / trace / dashboard
    -> cache, bản xuất dữ liệu và hệ thống lưu trữ
```

Số lớp thực tế tùy kiến trúc. Khi dữ liệu đã tới các lớp cuối, việc xóa một annotation ở đầu chuỗi không tự xóa các bản sao hoặc làm credential mất hiệu lực.

## 6. Giới hạn metadata ngay ở nguồn khám phá

Với implementation hỗ trợ các tùy chọn bổ sung metadata tương ứng, có thể chủ động tắt những nhóm không cần dùng:

```yaml
spring:
  cloud:
    kubernetes:
      discovery:
        metadata:
          add-labels: false
          add-annotations: false
          add-ports: false
```

Đây là ví dụ cho nhóm thuộc tính `spring.cloud.kubernetes.discovery.metadata`. Cần đối chiếu implementation và phiên bản dependency của dự án trước khi áp dụng; không suy ra rằng mọi mô hình HTTP client hoặc mọi phiên bản xử lý các tùy chọn tại cùng một thành phần.

Ý nghĩa cần hiểu đúng:

| Lựa chọn | Mục tiêu | Điều không được suy ra |
| --- | --- | --- |
| Tắt bổ sung labels | Giảm dữ liệu label được đưa vào map metadata | Label biến mất khỏi tài nguyên Kubernetes. |
| Tắt bổ sung annotations | Giảm dữ liệu annotation được đưa vào map metadata | Annotation chứa bí mật đã được bảo vệ khỏi mọi người đọc Service. |
| Tắt bổ sung ports | Giảm danh sách thông tin cổng được bổ sung vào metadata | Cổng chính của `ServiceInstance` biến mất hoặc cổng mạng được đóng. |

Các tùy chọn này không tự xóa metadata do mã tùy biến thêm vào, không bảo đảm map kết quả không còn mọi trường do implementation tạo và không loại bỏ host/port khỏi các getter của instance.

Nếu dùng DiscoveryServer, xác định thành phần nào thực sự xây dựng và trả metadata. Đặt một thuộc tính ở ứng dụng HTTP client không mặc định làm dữ liệu trên server được lọc lại.

Một số thuộc tính metadata có thể được bên gọi hoặc chính implementation sử dụng cho lựa chọn đích, giao thức và cổng. Trước khi thay đổi cấu hình, xác định phần nào cần giữ cho luồng nội bộ và phần nào chỉ cần loại khỏi đầu ra quan sát. Không xóa hoặc thay toàn bộ map của instance dùng chung để làm đẹp response.

