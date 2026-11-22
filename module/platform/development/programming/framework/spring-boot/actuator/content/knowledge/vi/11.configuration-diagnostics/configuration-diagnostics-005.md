# Khám phá bean, kiểu bean và quan hệ phụ thuộc bằng endpoint beans

## 1. Từ mã nguồn đến các thành phần thực sự được Spring quản lý

Có lớp `OrderService` trong mã nguồn chưa trả lời được câu hỏi: ứng dụng đang chạy có đăng ký bean đó không, bean dùng lớp triển khai nào và Spring đã nối nó với thành phần nào?

**Bean** là đối tượng do bộ chứa Spring quản lý. **ApplicationContext** là ngữ cảnh ứng dụng chứa cấu hình và các thành phần đó. **Bean name** là tên dùng để nhận diện bean trong một bộ chứa; **bean type** là kiểu Java Spring xác định cho bean. Một bean có thể có thêm tên khác gọi là **bí danh (alias)**. Tên bean và tên lớp là hai thông tin khác nhau. Xem [BeanFactory của Spring Framework](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/beans/factory/BeanFactory.html).

Trong bài này, ta dùng `GET /actuator/beans` để kiểm tra ba việc:

1. Bean cần tìm có xuất hiện trong ngữ cảnh đang quan sát không?
2. Tên, bí danh và kiểu Java của nó là gì?
3. Nó phụ thuộc vào những bean nào; ngược lại, bean nào đang phụ thuộc vào nó?

Đây là công cụ đọc cấu trúc thành phần của ứng dụng. Chẳng hạn, khi một cấu hình chạy thử dùng kho dữ liệu trong bộ nhớ còn cấu hình triển khai dùng kho dữ liệu thật, ta có thể kiểm tra thành phần đang được đăng ký trước khi suy đoán từ tên lớp.

## 2. Bật đúng endpoint và hiểu cấu trúc phản hồi

Bài thực hành dùng Spring Boot **3.3.0**, Java **21** và Gradle **8.5** để có một bộ phiên bản cụ thể. Các đường dẫn tài liệu Spring Boot 3.3 bên dưới mô tả dòng 3.3; không trộn thuộc tính cấu hình của các dòng mới vào ví dụ này.

Với Boot 3.3, `beans` được bật theo mặc định nhưng không được công bố qua HTTP theo mặc định. Cần có Actuator và đưa `beans` vào `management.endpoints.web.exposure.include`. Nếu cấu hình chung đã tắt endpoint, dùng `management.endpoint.beans.enabled=true`. `exclude` được ưu tiên hơn `include`. Xem [cấu hình endpoint trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#exposing-endpoints).

Đường dẫn mặc định là `/actuator/beans`; cổng, đường dẫn gốc của ứng dụng, cổng quản trị và cấu hình đổi base path có thể làm URL thực tế khác đi. Ví dụ bên dưới dùng một cổng và giữ các đường dẫn mặc định.

Phản hồi là một đối tượng JSON có cấu trúc sau:

| Thành phần | Cách đọc |
| --- | --- |
| `contexts` | Tập các ngữ cảnh được mô tả, có khóa là mã ngữ cảnh. |
| `contexts.<id>.parentId` | Mã ngữ cảnh cha, nếu có. |
| `contexts.<id>.beans` | Tập bean của ngữ cảnh, có khóa là tên bean. |
| `aliases` | Các bí danh của bean. |
| `scope` | Phạm vi quản lý bean. |
| `type` | Tên kiểu Java đầy đủ. |
| `resource` | Tài nguyên nơi bean được định nghĩa, nếu có. |
| `dependencies` | Tên các bean mà bean này phụ thuộc vào. |

Đây là các trường của [API beans trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/beans.html). Không nên viết công cụ chỉ đọc `contexts.application`: mã ngữ cảnh là dữ liệu cần khám phá.

## 3. Thực hành với một ứng dụng nhỏ chạy độc lập

Tạo một dự án riêng cho bài thực hành, có cấu trúc:

~~~text
beans-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/BeansLabApplication.java
    └── resources/application.properties
~~~

### 3.1. Khai báo dự án và thư viện

Nội dung `settings.gradle`:

~~~groovy
rootProject.name = 'beans-lab'
~~~

Nội dung `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

`spring-boot-starter-web` cung cấp máy chủ HTTP; `spring-boot-starter-actuator` cung cấp các endpoint quản trị. Dự án này không cần cơ sở dữ liệu hay một API nghiệp vụ riêng để quan sát bean.

### 3.2. Cấu hình phạm vi thực hành

Nội dung `src/main/resources/application.properties`:

~~~properties
spring.application.name=beans-lab
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,beans
management.endpoint.beans.enabled=true
~~~

Máy chủ của ví dụ chỉ lắng nghe trên địa chỉ loopback. Ví dụ không thêm Spring Security, nên yêu cầu HTTP từ máy cục bộ không cần đăng nhập.

Trên ứng dụng có Spring Security, công bố endpoint và cấp quyền truy cập là hai việc riêng. Không sao chép cấu hình mở truy cập vào môi trường triển khai: phản hồi có thể lộ tên lớp, cấu trúc thành phần và nguồn cấu hình. Xem [bảo vệ Actuator trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#security).

### 3.3. Đăng ký bean, bí danh và một quan hệ phụ thuộc

Toàn bộ tệp `src/main/java/example/BeansLabApplication.java`:

~~~java
package example;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication(proxyBeanMethods = false)
public class BeansLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(BeansLabApplication.class, args);
    }

    @Bean(name = {"orderRepository", "repoAlias"})
    OrderRepository orderRepository() {
        return new MemoryOrderRepository();
    }

    @Bean
    OrderService orderService(
            @Qualifier("orderRepository") OrderRepository repository) {
        return new OrderService(repository);
    }
}

interface OrderRepository {
    long count();
}

class MemoryOrderRepository implements OrderRepository {
    @Override
    public long count() {
        return 7L;
    }
}

class OrderService {
    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public long countOrders() {
        return repository.count();
    }
}
~~~

Trong tệp này:

- `orderRepository` là tên chính của bean; `repoAlias` là bí danh của cùng bean đó.
- Phương thức tạo bean khai báo kiểu trả về `OrderRepository`, nhưng đối tượng được tạo là `MemoryOrderRepository`.
- Spring truyền bean kho dữ liệu vào tham số của phương thức `orderService(...)`; phương thức này chuyển tiếp nó cho hàm khởi tạo `OrderService`.
- `@Qualifier("orderRepository")` chỉ rõ lựa chọn ở điểm tiêm phụ thuộc.
- Hai phương thức `@Bean` là phương thức đối tượng của bean cấu hình `beansLabApplication`.

`proxyBeanMethods=false` phù hợp ở đây vì các phương thức tạo bean không gọi trực tiếp lẫn nhau; chúng nhận phụ thuộc qua tham số. Những lớp không có `public` được đặt cùng tệp để ví dụ gọn và vẫn biên dịch được; khi tổ chức dự án lớn có thể tách chúng thành tệp riêng.

### 3.4. Chạy và lấy dữ liệu

Nếu máy đã có Gradle 8.5, đứng tại thư mục `beans-lab` để tạo wrapper một lần:

~~~powershell
gradle wrapper --gradle-version 8.5
~~~

Sau đó chạy trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Trên Linux/macOS dùng `./gradlew bootRun`. Lần đầu cần tải Gradle và các thư viện. `bootRun` sử dụng classpath của ứng dụng; không chạy `javac BeansLabApplication.java` đơn lẻ vì tệp này cần thư viện Spring. Xem [chạy ứng dụng bằng Gradle](https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html).

Khi ứng dụng đã khởi động, mở PowerShell khác:

~~~powershell
$response = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/beans'
$response.contexts.PSObject.Properties.Name
~~~

Có thể tải phản hồi gốc bằng `curl.exe` trên Windows:

~~~powershell
curl.exe --fail --silent --show-error 'http://127.0.0.1:8080/actuator/beans' --output beans.json
~~~

Một phần phản hồi liên quan đến hai bean của bài có dạng sau. Những bean khác được bỏ khỏi hình minh họa; thứ tự các khóa và phần tử phụ thuộc không phải hợp đồng cần dựa vào:

~~~json
{
  "contexts": {
    "beans-lab": {
      "beans": {
        "orderRepository": {
          "aliases": ["repoAlias"],
          "scope": "singleton",
          "type": "example.MemoryOrderRepository",
          "resource": "example.BeansLabApplication",
          "dependencies": ["beansLabApplication"]
        },
        "orderService": {
          "aliases": [],
          "scope": "singleton",
          "type": "example.OrderService",
          "resource": "example.BeansLabApplication",
          "dependencies": [
            "beansLabApplication",
            "orderRepository"
          ]
        }
      }
    }
  }
}
~~~

Các trường của hai bean này được kiểm chứng với `BeansEndpoint` của Boot 3.3.0. Khi đổi cách khai báo hoặc đóng gói ứng dụng, mô tả `resource` có thể thay đổi.

## 4. Đọc tên, kiểu và phạm vi mà không suy diễn quá mức

### Tên chính và bí danh

Khóa `orderRepository` nhận diện bean trong tập `beans`. Bí danh `repoAlias` nằm trong mảng `aliases`; không cần có một mục JSON độc lập mang khóa `repoAlias`.

Hai tên này cùng tra cứu đến một bean. Vì vậy, đếm alias thành một bean mới sẽ làm sai số lượng. Khi tìm theo tên, hãy xét cả khóa của bean và danh sách bí danh.

### Kiểu Java

Trong ví dụ đã khởi tạo, `type` là `example.MemoryOrderRepository`. Điểm tiêm phụ thuộc vẫn dùng giao diện `OrderRepository`. Điều đó bình thường: kiểu được yêu cầu tại nơi nhận phụ thuộc và kiểu được mô tả của bean không nhất thiết là một chuỗi giống nhau.

Một lớp có thể triển khai nhiều giao diện nhưng `type` không phải danh sách các giao diện đó. Vì vậy, lọc chuỗi bằng đúng tên giao diện có thể bỏ sót bean phù hợp. Nếu cần kiểm chứng quan hệ gán kiểu trong mã, dùng API như `isTypeMatch` hoặc `getBeanNamesForType`, thay vì suy luận chỉ từ phép so sánh chuỗi. Xem [BeanFactory: kiểm tra kiểu](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/beans/factory/BeanFactory.html#isTypeMatch(java.lang.String,java.lang.Class)) và [ListableBeanFactory: tìm theo kiểu](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/beans/factory/ListableBeanFactory.html#getBeanNamesForType(java.lang.Class)).

Với proxy hoặc `FactoryBean`, phải kiểm tra kiểu Spring xác định trong tình huống cụ thể. Không mặc định rằng `type` luôn là lớp ghi trong mã nguồn, cũng không mặc định rằng nó luôn là tên lớp proxy. Trong Boot 3.3.0, endpoint lấy kiểu qua `BeanFactory.getType(beanName)`.

### Phạm vi và tài nguyên định nghĩa

`singleton` nghĩa là một đối tượng dùng chung cho một bean trong bộ chứa tương ứng. Hai bean khác tên có thể cùng kiểu Java; tên kiểu trùng nhau không chứng minh chúng là cùng một đối tượng. `prototype` biểu thị cơ chế cung cấp đối tượng mới khi yêu cầu bean; dữ liệu endpoint không phải danh sách mọi đối tượng prototype đã được tạo. Xem [phạm vi bean của Spring](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html).

`resource` giúp lần về cấu hình khai báo bean. Nó không phải giá trị các thuộc tính bên trong đối tượng, không phải đường dẫn API nghiệp vụ và cũng không phải mã nguồn đầy đủ. Ví dụ trên trả về tên lớp cấu hình; trường này có thể vắng khi không có mô tả tài nguyên.

## 5. Phân tích đúng chiều quan hệ phụ thuộc

Với mục `orderService`, mảng `dependencies` chứa `orderRepository`. Đọc thành:

~~~text
orderService ──phụ thuộc vào──> orderRepository
~~~

Đừng đảo thành “orderRepository cần orderService”.

Dữ liệu còn có cạnh từ cả hai bean đến `beansLabApplication`. Đây là bean cấu hình chứa phương thức tạo chúng. Vì vậy, danh sách phụ thuộc có thể bao gồm thành phần phục vụ quá trình tạo bean, bên cạnh các cộng tác viên nghiệp vụ được tiêm vào nó.

Boot 3.3.0 lấy các tên này từ `getDependenciesForBean`. Chiều ngược lại trong Spring là `getDependentBeans`: các bean đang phụ thuộc vào bean được hỏi. Xem [ConfigurableBeanFactory](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/beans/factory/config/ConfigurableBeanFactory.html#getDependenciesForBean(java.lang.String)).

Có ba giới hạn cần nhớ khi phân tích một đồ thị:

- **Phụ thuộc trực tiếp khác phụ thuộc bắc cầu.** Nếu A có B trong mảng và B có C, phải đi thêm một bước mới suy ra đường A → B → C; không đòi C xuất hiện trong mảng của A.
- **Quan hệ do bộ chứa ghi nhận khác luồng gọi phương thức.** Dữ liệu không cho biết yêu cầu HTTP nào đã gọi phương thức nào, bao nhiêu lần hay mất bao lâu.
- **Đồ thị không biểu diễn mọi tham chiếu Java.** Đối tượng tự tạo bằng `new`, tra cứu trì hoãn hoặc liên kết hình thành ngoài cơ chế đăng ký phụ thuộc cần thêm bằng chứng. Mảng rỗng chỉ nói rằng lần mô tả này không trả về tên phụ thuộc đã ghi nhận.

Một cạnh cũng chưa chứng minh bean đang hoạt động tốt hoặc được sử dụng thường xuyên. Muốn trả lời các câu hỏi đó cần kiểm tra chức năng hoặc công cụ quan sát khác.

## 6. Truy vấn thực tế bằng PowerShell

Phần này dùng PowerShell 5.1+ hoặc 7 và đối tượng `$response` đã lấy ở trên. Các truy vấn chạy phía máy đọc dữ liệu; chúng không tạo thêm endpoint.

Trước hết chuyển từng mục JSON thành một bản ghi dễ lọc, đồng thời giữ mã ngữ cảnh để tránh nhập nhằng tên:

~~~powershell
$rows = @(
    foreach ($context in $response.contexts.PSObject.Properties) {
        foreach ($entry in $context.Value.beans.PSObject.Properties) {
            [pscustomobject]@{
                Context      = $context.Name
                Name         = $entry.Name
                Aliases      = @($entry.Value.aliases)
                Scope        = $entry.Value.scope
                Type         = $entry.Value.type
                Resource     = $entry.Value.resource
                Dependencies = @($entry.Value.dependencies)
            }
        }
    }
)
~~~

### 6.1. Tìm theo tên chính hoặc bí danh

~~~powershell
$wanted = 'repoAlias'
$rows |
    Where-Object { $_.Name -ceq $wanted -or $_.Aliases -ccontains $wanted } |
    Select-Object Context, Name, Type, Scope
~~~

Với ví dụ này, bản ghi tìm được mang tên chính `orderRepository`, kiểu `example.MemoryOrderRepository` và phạm vi `singleton`.

Dùng `-ceq` và `-ccontains` để so sánh phân biệt hoa thường, phù hợp với tên bean Java. Phép so sánh mặc định của PowerShell không phân biệt hoa thường.

### 6.2. Lọc theo kiểu được trả về

~~~powershell
$rows |
    Where-Object { $_.Type -ceq 'example.MemoryOrderRepository' } |
    Select-Object Context, Name, Type
~~~

Muốn khảo sát các bean thuộc mã của ví dụ:

~~~powershell
$rows |
    Where-Object { $_.Type -clike 'example.*' } |
    Sort-Object Context, Name |
    Select-Object Context, Name, Type, Scope
~~~

Đây là lọc chuỗi tên kiểu; nó không thực hiện kiểm tra kế thừa hay triển khai giao diện.

### 6.3. Tìm phụ thuộc của orderService

Lấy đúng một bản ghi trong ví dụ một ngữ cảnh này:

~~~powershell
$service = @($rows | Where-Object { $_.Name -ceq 'orderService' })
if ($service.Count -ne 1) {
    throw 'Can chon ro mot context chua orderService.'
}
$service[0].Dependencies | Sort-Object
~~~

Kết quả của ví dụ sau khi sắp xếp:

~~~text
beansLabApplication
orderRepository
~~~

Trong hệ thống có nhiều ngữ cảnh, bổ sung điều kiện `Context` lấy từ dữ liệu thực tế trước khi chọn bản ghi.

### 6.4. Tìm bean đang phụ thuộc vào orderRepository

~~~powershell
$rows |
    Where-Object { $_.Dependencies -ccontains 'orderRepository' } |
    Sort-Object Context, Name |
    Select-Object Context, Name, Type
~~~

Trong ứng dụng mẫu, truy vấn tìm thấy `orderService`. Đây là cách đảo chiều các cạnh đã có trong phản hồi, không phải gọi một thao tác ghi lên Spring.

Nếu có nhiều ngữ cảnh cùng chứa tên `orderRepository`, kết quả cần được giải nghĩa cùng quan hệ cha–con; mỗi chuỗi trong `dependencies` không mang sẵn mã ngữ cảnh đích. Không gộp toàn bộ theo tên rồi coi đó là một đồ thị duy nhất không nhập nhằng.

### 6.5. Xuất danh sách cạnh để phân tích tiếp

~~~powershell
$edges = @(
    foreach ($row in $rows) {
        foreach ($dependency in $row.Dependencies) {
            [pscustomobject]@{
                Context   = $row.Context
                Bean      = $row.Name
                DependsOn = $dependency
            }
        }
    }
)
$edges |
    Sort-Object Context, Bean, DependsOn |
    Format-Table -AutoSize
~~~

Mỗi hàng biểu diễn `Bean → DependsOn`. Khi đi tiếp qua nhiều tầng, công cụ duyệt cần giữ tập đỉnh đã thăm để không lặp vô hạn. Đừng dùng thứ tự mảng JSON làm thứ tự khởi tạo hoặc thứ tự thực thi.

## 7. Chẩn đoán khi kết quả không như dự kiến

### Không gọi được endpoint

Kiểm tra theo thứ tự ngắn gọn:

1. Ứng dụng đã khởi động và URL có đúng cổng/đường dẫn quản trị không?
2. Đã thêm Actuator, bật `beans` và công bố nó qua HTTP chưa?
3. Có cấu hình `exclude` hoặc quy tắc bảo mật ngăn truy cập không?

`401` hoặc `403` gợi ý cần kiểm tra xác thực/quyền truy cập; `404` cần kiểm tra URL, việc bật và công bố endpoint, đồng thời xét quy tắc của ứng dụng hoặc proxy. Không kết luận “bean không tồn tại” từ việc chưa lấy được tài liệu JSON.

Endpoint tích hợp trong bài là `GET /actuator/beans`. Đừng tự giả định có `/actuator/beans/orderService` hoặc bộ lọc `?name=orderService`; hãy lấy tài liệu rồi lọc phía máy đọc như phần 6.

### Gọi được nhưng không thấy bean

Trước hết tìm tên chính, bí danh và tất cả ngữ cảnh được trả về. Sau đó kiểm tra mã khai báo bean, phạm vi quét thành phần và điều kiện cấu hình.

Riêng triển khai `BeansEndpoint` **3.3.0** có những giới hạn quan sát quan trọng:

- Nó duyệt các tên có `BeanDefinition`; một đối tượng singleton đăng ký thủ công mà không có định nghĩa tương ứng không thuộc tập duyệt đó.
- Định nghĩa mang vai trò `ROLE_INFRASTRUCTURE` bị loại khỏi danh sách.
- Với định nghĩa khởi tạo trì hoãn, endpoint chỉ đưa vào khi bộ chứa đã có singleton tương ứng.

Các điểm này được đối chiếu trực tiếp với triển khai trong JAR `spring-boot-actuator:3.3.0`; khi đổi phiên bản cần kiểm tra lại. Vì vậy, không thấy một bean trì hoãn chưa khởi tạo là chưa đủ để kết luận nó chưa được khai báo. Không chủ động gọi `getBean` hàng loạt chỉ để làm danh sách “đầy đủ”: thao tác đó có thể khởi tạo các thành phần đang cố ý trì hoãn.

Nếu ứng dụng thất bại ngay trong quá trình tạo ngữ cảnh, hãy đọc lỗi khởi động và cấu hình điều kiện; không trông chờ endpoint HTTP của ứng dụng đó hoạt động để giải thích lỗi.

### Có bean nhưng triển khai hoặc phụ thuộc khác kỳ vọng

Với ví dụ này, nếu tìm thấy `orderRepository` nhưng `type` không còn là `MemoryOrderRepository`, hãy đối chiếu cấu hình đang chạy và nơi định nghĩa bean trước khi sửa `OrderService`.

Nếu có nhiều bean cùng đáp ứng một giao diện, riêng danh sách `beans` chưa mô tả đầy đủ quy tắc lựa chọn tại từng điểm tiêm. Đối chiếu `@Qualifier`, `@Primary`, kiểu yêu cầu và cấu hình khai báo. Nếu chưa tạo nổi ngữ cảnh do phụ thuộc mơ hồ, dùng lỗi khởi động làm bằng chứng.

`conditions` hỗ trợ giải thích điều kiện cấu hình; `env` và `configprops` phục vụ các câu hỏi về cấu hình giá trị; `health` phục vụ tình trạng sức khỏe. Chọn công cụ theo câu hỏi, không dùng danh sách bean để thay thế tất cả các phép chẩn đoán.

## 8. Bài tập kiểm chứng và cách tự đối chiếu

**Bài 1 — Tên và bí danh.** Tìm `repoAlias` bằng truy vấn 6.1. Giải thích vì sao kết quả mang tên `orderRepository`.

Đối chiếu: bí danh là tên khác của cùng bean; nó không yêu cầu một bản ghi bean mới.

**Bài 2 — Kiểu khai báo và kiểu được mô tả.** So sánh kiểu trả về của phương thức `orderRepository()` với trường `type`.

Đối chiếu: phương thức khai báo giao diện `OrderRepository`; trong ví dụ đã khởi tạo, Spring mô tả `example.MemoryOrderRepository`. Không suy ra giao diện là một bean thứ hai.

**Bài 3 — Hai chiều của quan hệ.** Chạy truy vấn 6.3 và 6.4, rồi vẽ các cạnh liên quan đến hai bean nghiệp vụ.

Đối chiếu:

~~~text
orderService ────────> orderRepository
      │                      │
      └──────────┬───────────┘
                 v
       beansLabApplication
~~~

Cạnh tới bean cấu hình xuất phát từ cách tạo bean bằng phương thức đối tượng `@Bean`. Chiều truy vấn ngược giúp tìm `orderService` từ `orderRepository`.

**Bài 4 — Thay đổi alias có kiểm soát.** Đổi riêng `repoAlias` thành `storageAlias`, khởi động lại, lấy một phản hồi mới và tìm lại bằng tên mới.

Đối chiếu: tên chính, kiểu và phụ thuộc nghiệp vụ vẫn như trước; mảng alias phản ánh tên mới. Phải dùng dữ liệu mới sau khi khởi động lại thay vì lọc lại biến `$response` cũ.

**Bài 5 — Kết luận từ bằng chứng.** Một phản hồi không chứa bean mong muốn, hoặc chứa bean nhưng mảng phụ thuộc rỗng. Nêu kiểm tra tiếp theo trước khi kết luận.

Đối chiếu: xác nhận ngữ cảnh, cách đăng ký, trạng thái khởi tạo trì hoãn và giới hạn quan sát; mảng rỗng không chứng minh đối tượng không cộng tác với bất kỳ đối tượng Java nào.

Sau bài này, mục tiêu thực hành là đọc được một bản ghi bean, phân biệt tên với kiểu, truy vết đúng chiều phụ thuộc và nêu rõ giới hạn của kết luận rút ra từ phản hồi.
