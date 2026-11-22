# Đăng ký hoặc loại bỏ contributor bằng HealthContributorRegistry

## 1. Registry quản lý những phép kiểm tra nào đang tham gia health

Một ứng dụng có thể kết nối tới nhiều tài nguyên thay đổi trong lúc chạy: thêm một khách thuê (tenant), kích hoạt một tích hợp tìm kiếm hoặc gỡ một kết nối đã kết thúc sử dụng. Nếu danh sách phép kiểm tra sức khỏe chỉ được xác định lúc khởi động, health endpoint có thể thiếu tài nguyên mới hoặc tiếp tục kiểm tra tài nguyên đã ngừng sử dụng.

`HealthContributorRegistry` là sổ đăng ký các thành phần cung cấp thông tin sức khỏe (`HealthContributor`), theo từng tên định danh. Thông qua registry, ứng dụng có thể thêm hoặc gỡ một contributor khi đang chạy mà không phải khởi động lại.

Cần phân biệt hai câu hỏi:

- **Contributor còn thuộc phạm vi giám sát không?** Registry quyết định nó có mặt hay vắng mặt.
- **Tài nguyên đang hoạt động tốt không?** `HealthIndicator` thực hiện phép kiểm tra và trả `Health` với trạng thái như `UP` hoặc `DOWN`.

Một dịch vụ tìm kiếm vẫn được sử dụng nhưng đang mất kết nối cần tiếp tục có mặt và báo `DOWN`. Chỉ gỡ contributor khi tài nguyên thực sự rời khỏi phạm vi giám sát. Gỡ một phép kiểm tra đang `DOWN` có thể làm báo cáo tổng hợp tốt lên dù lỗi chưa được xử lý.

Bài này dùng API đồng bộ trong package `org.springframework.boot.actuate.health` của **Spring Boot 3.3.x**, phù hợp với ứng dụng Servlet. Ví dụ cố định dependency ở 3.3.0 để tái lập; dự án đang dùng bản vá 3.3.x khác nên giữ quản lý phiên bản nhất quán theo BOM của dự án.

## 2. Mối liên hệ giữa contributor, bean Spring và health endpoint

`HealthContributor` là kiểu chung. Hai dạng thường gặp là:

| Kiểu | Vai trò |
| --- | --- |
| `HealthIndicator` | Một phép kiểm tra có phương thức `health()` trả về `Health` |
| `CompositeHealthContributor` | Một nhóm contributor con, hình thành một nhánh trong cây sức khỏe |
| `HealthContributorRegistry` | Quản lý contributor cấp gốc theo ID, cho phép thêm, tra cứu, duyệt và gỡ |

Với cấu hình tự động thông thường, Spring Boot xây dựng registry từ các bean contributor trong `ApplicationContext`. `HealthEndpoint` dùng registry đó để tìm các contributor cần kiểm tra. Vì thế, trong ứng dụng Spring Boot, hãy **tiêm registry do ứng dụng đang sử dụng** vào lớp quản lý vòng đời.

Tự tạo `new DefaultHealthContributorRegistry()` chỉ tạo một registry riêng. Nếu không cấu hình health endpoint dùng registry ấy, thêm contributor vào nó không làm `/actuator/health` thay đổi. Registry riêng rất phù hợp cho ví dụ cô lập ở phần 4, nhưng không thay cho registry được tiêm trong ứng dụng.

Thao tác registry cũng độc lập với vòng đời bean:

- `registerContributor` không đăng ký một bean mới vào `ApplicationContext`. Một đối tượng tạo bằng `new` rồi đưa vào registry không tự được Spring tiêm phụ thuộc hoặc gọi các callback vòng đời bean.
- `unregisterContributor` không xóa bean Spring và không tự đóng connection pool, HTTP client hay dừng tác vụ nền.
- Gỡ một contributor không làm tài nguyên bên dưới tự ngừng phục vụ nghiệp vụ.

Đó là thay đổi danh sách quan sát. Việc cấp phát, ngừng nhận yêu cầu, chờ xử lý đang chạy và giải phóng tài nguyên cần có cơ chế vòng đời riêng. Cấu hình mặc định của endpoint và registry được mô tả trong [HealthEndpointConfiguration của Spring Boot 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/HealthEndpointConfiguration.java).

## 3. Các thao tác và hợp đồng cần nhớ

Các chữ ký dưới đây là dạng sử dụng với `HealthContributorRegistry`; thao tác thay đổi được kế thừa từ `ContributorRegistry<HealthContributor>`:

```java
void registerContributor(String name, HealthContributor contributor);
HealthContributor getContributor(String name);
HealthContributor unregisterContributor(String name);
```

| Thao tác | Kết quả cần hiểu |
| --- | --- |
| `registerContributor(id, contributor)` | Thêm contributor theo ID; không trả kết quả và không tự chạy `health()` |
| `getContributor(id)` | Trả đối tượng đã đăng ký, hoặc `null` nếu không có |
| `unregisterContributor(id)` | Trả chính contributor đã gỡ, hoặc `null` nếu ID không tồn tại |
| Duyệt registry | Nhận từng `NamedContributor<HealthContributor>`, gồm tên và đối tượng; duyệt không tự chạy phép kiểm tra |

Trong triển khai mặc định của dòng 3.3, đăng ký trùng ID gây `IllegalStateException`, kể cả khi truyền lại chính đối tượng cũ. Đây không phải phép cập nhật ghi đè. Tên hoặc contributor truyền vào thao tác đăng ký không được `null`.

Không ép mọi contributor thành `HealthIndicator`: giá trị nhận được còn có thể là một `CompositeHealthContributor`. Chỉ ép kiểu khi biết chắc ID đang trỏ tới loại nào, hoặc kiểm tra bằng `instanceof`.

### Đặt ID rõ ràng và nhất quán

ID là tên xuất hiện trong cây health, không phải tên lớp Java hoặc URL tùy ý. Cấu hình mặc định có quy tắc rút gọn tên bean, chẳng hạn bean `searchHealthIndicator` thường xuất hiện dưới tên `search`. Khi đăng ký động, nên chọn sẵn ID chuẩn như `externalSearch` hoặc `tenantAlpha`, rồi dùng đúng ID ấy để tra cứu và gỡ.

Không dựa vào việc tất cả phương thức đều tự rút gọn tên theo cùng một cách. Đặc biệt, hãy tra cứu bằng tên thực tế trong registry. Không dùng `/` để giả lập một đường dẫn con; tên nên ổn định, dễ nhận biết và tránh đụng tên contributor tự cấu hình hoặc tên health group.

Có thể kiểm tra danh sách tên mà không gọi mạng:

```java
registry.forEach(named -> System.out.println(named.getName()));
```

Đây là đoạn mã đặt trong nơi đã có biến `registry`, không phải chương trình độc lập. Xem hợp đồng chính thức tại [ContributorRegistry](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/ContributorRegistry.html) và [NamedContributors](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/NamedContributors.html).

## 4. Chương trình Java chạy được: thêm, đổi trạng thái, gỡ

Ví dụ này dùng một registry riêng để quan sát trực tiếp hành vi API. Nó **không khởi động Spring Boot, không mở cổng HTTP và không gọi dịch vụ bên ngoài**. `AtomicBoolean` mô phỏng tình trạng tài nguyên; `AtomicInteger` đếm số lần thực sự kiểm tra.

Tạo thư mục riêng, chứa hai tệp `pom.xml` và `RegistryDemo.java`. Cần JDK 17 trở lên và Maven; lần tải dependency đầu tiên cần kết nối tới Maven Central.

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>health-registry-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
            <version>3.3.0</version>
        </dependency>
    </dependencies>
</project>
```

`RegistryDemo.java`:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.actuate.health.DefaultHealthContributorRegistry;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributor;
import org.springframework.boot.actuate.health.HealthContributorRegistry;
import org.springframework.boot.actuate.health.HealthIndicator;

public class RegistryDemo {
    public static void main(String[] args) {
        HealthContributorRegistry registry = new DefaultHealthContributorRegistry();
        AtomicBoolean available = new AtomicBoolean(false);
        AtomicInteger checks = new AtomicInteger();

        HealthIndicator tenantAlpha = () -> {
            checks.incrementAndGet();
            return available.get()
                    ? Health.up().build()
                    : Health.down().withDetail("reason", "simulated-unavailable").build();
        };

        String id = "tenantAlpha";
        System.out.println("present-before=" + (registry.getContributor(id) != null));
        registry.registerContributor(id, tenantAlpha);
        System.out.println("present-after=" + (registry.getContributor(id) != null));
        System.out.println("checks-after-register=" + checks.get());
        System.out.println("first-status=" + tenantAlpha.health().getStatus());

        try {
            registry.registerContributor(id, tenantAlpha);
        }
        catch (IllegalStateException ex) {
            System.out.println("duplicate=" + ex.getClass().getSimpleName());
        }

        available.set(true);
        HealthIndicator registered = (HealthIndicator) registry.getContributor(id);
        System.out.println("second-status=" + registered.health().getStatus());

        HealthContributor removed = registry.unregisterContributor(id);
        System.out.println("removed-same-instance=" + (removed == tenantAlpha));
        System.out.println("present-after-remove=" + (registry.getContributor(id) != null));
        System.out.println("remove-again=" + registry.unregisterContributor(id));
        System.out.println("detached-status=" + tenantAlpha.health().getStatus());
    }
}
```

Trong PowerShell trên Windows, chạy tại thư mục chứa hai tệp:

```powershell
mvn -q dependency:copy-dependencies "-DoutputDirectory=lib"
javac --release 17 -cp "lib/*" RegistryDemo.java
java -cp ".;lib/*" RegistryDemo
```

Trên Linux/macOS, hai lệnh đầu tương tự; lệnh chạy dùng dấu `:` làm dấu phân cách classpath:

```bash
java -cp ".:lib/*" RegistryDemo
```

Stdout của chương trình, không tính thông báo từ Maven hoặc trình biên dịch:

```text
present-before=false
present-after=true
checks-after-register=0
first-status=DOWN
duplicate=IllegalStateException
second-status=UP
removed-same-instance=true
present-after-remove=false
remove-again=null
detached-status=UP
```

Các dòng kết quả chứng minh từng phần khác nhau:

1. Sau đăng ký, contributor có thể được tìm thấy, nhưng số lần kiểm tra vẫn là `0`. Đăng ký chỉ thay đổi tập thành viên.
2. Lần gọi `health()` đầu tiên trả `DOWN` vì cờ `available` đang là `false`.
3. Đăng ký lại cùng ID thất bại. Contributor đang tồn tại không bị thay thế.
4. Đổi cờ sang `true` làm lần kiểm tra tiếp theo trả `UP`; không cần gỡ rồi đăng ký lại.
5. Gỡ trả về đúng đối tượng ban đầu; tra cứu sau đó không còn thấy ID.
6. Gỡ lần nữa trả `null`. Đây không phải lỗi “tài nguyên đang DOWN”.
7. Tham chiếu `tenantAlpha` vẫn gọi được sau khi gỡ. Registry không hủy đối tượng.

Phép ép kiểu trong ví dụ hợp lệ vì chính chương trình vừa đăng ký một `HealthIndicator` dưới ID đó. Không áp dụng phép ép kiểu này một cách máy móc cho contributor lấy từ registry của một ứng dụng bất kỳ.

## 5. Tích hợp vào ứng dụng Spring Boot: một nơi sở hữu một ID

Giả sử một tính năng tìm kiếm có thể được kích hoạt hoặc ngừng sử dụng trong lúc ứng dụng chạy. Một lớp quản lý chịu trách nhiệm duy nhất đối với ID `externalSearch`.

Đặt lớp dưới đây trong vùng package được ứng dụng quét, ví dụ `src/main/java/example/health/DynamicSearchHealth.java`. Ứng dụng cần các dependency `spring-boot-starter-web` và `spring-boot-starter-actuator`, với phiên bản do cùng BOM Spring Boot quản lý. Đây là lớp tích hợp vào ứng dụng đã có; không phải một ứng dụng độc lập có `main`.

```java
package example.health;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributorRegistry;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Service;

@Service
public final class DynamicSearchHealth {
    private static final String ID = "externalSearch";

    private final HealthContributorRegistry registry;
    private final AtomicBoolean available = new AtomicBoolean(false);
    private final HealthIndicator indicator = () -> available.get()
            ? Health.up().build()
            : Health.down().build();
    private boolean registered;

    public DynamicSearchHealth(HealthContributorRegistry registry) {
        this.registry = registry;
    }

    public synchronized void activate() {
        if (registered) {
            return;
        }
        registry.registerContributor(ID, indicator);
        registered = true;
    }

    public void setAvailable(boolean value) {
        available.set(value);
    }

    public synchronized void deactivate() {
        if (!registered) {
            return;
        }
        if (registry.getContributor(ID) != indicator) {
            throw new IllegalStateException("Contributor ownership changed: " + ID);
        }
        registry.unregisterContributor(ID);
        registered = false;
    }
}
```

Cách sử dụng từ cơ chế quản lý tính năng hoặc tài nguyên bên trong ứng dụng:

```java
searchHealth.activate();          // Bắt đầu giám sát; trạng thái ban đầu là DOWN.
searchHealth.setAvailable(true);  // Tài nguyên đã sẵn sàng; lần kiểm tra sau trả UP.
searchHealth.setAvailable(false); // Tài nguyên gặp lỗi; vẫn giữ contributor và báo DOWN.
searchHealth.deactivate();        // Chỉ gọi khi tài nguyên rời phạm vi giám sát.
```

Đây là đoạn gọi minh họa, với `searchHealth` là bean `DynamicSearchHealth` đã được tiêm. Bốn lệnh chạy liền nhau nên không tạo ra các khoảng dừng để người dùng gọi HTTP giữa từng bước. Để quan sát từng giai đoạn, thực hiện từng thay đổi qua luồng quản lý tính năng của ứng dụng rồi mới gửi yêu cầu health.

Trong ví dụ, `AtomicBoolean` chỉ mô phỏng trạng thái. Với tài nguyên thật, contributor cần kiểm tra điều kiện phù hợp, có timeout cho thao tác I/O và trả kết quả phản ánh đúng tài nguyên. Không thay phép kiểm tra thật bằng một cờ luôn `true`.

### Vì sao có cờ registered và synchronized?

`registered` ghi nhận việc đăng ký mà lớp này đã thực hiện thành công. Nó chỉ đổi sang `true` sau khi `registerContributor` hoàn tất; nếu có xung đột ID, ngoại lệ được giữ nguyên để phát hiện lỗi cấu hình. Gọi `activate()` hoặc `deactivate()` lặp lại qua cùng bean không tạo thêm bản đăng ký.

`synchronized` tuần tự hóa hai phương thức quản lý vòng đời **trên cùng đối tượng này**. `AtomicBoolean` giúp luồng kiểm tra nhìn thấy thay đổi của cờ trạng thái. Hai cơ chế giải quyết hai việc khác nhau.

Điều kiện bắt buộc là mọi thay đổi của ID `externalSearch` phải đi qua lớp sở hữu đó. Khóa của lớp không ngăn mã khác ghi trực tiếp vào registry. Phép kiểm tra tham chiếu trong `deactivate()` giúp phát hiện một số thay đổi ngoài ý muốn, nhưng không tạo ra thao tác “kiểm tra rồi gỡ” nguyên tử đối với tác nhân bên ngoài.

Nếu có nhiều nơi cùng quản lý một ID, cần thống nhất quyền sở hữu hoặc thiết kế điều phối chung. Không giải quyết tranh chấp bằng cách bắt mọi `IllegalStateException` rồi bỏ qua.

## 6. Quan sát tác động qua health endpoint

Trong môi trường thực hành cục bộ, có thể bật hiển thị component:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-components: always
      show-details: never
```

Cấu hình trên giúp nhìn tên các contributor, đồng thời không yêu cầu hiển thị chi tiết kiểm tra. Nó không thay cấu hình phân quyền truy cập HTTP. Với hệ thống thật, chọn chính sách hiển thị phù hợp, chẳng hạn `when-authorized`, và không đưa dữ liệu nhạy cảm vào kết quả kiểm tra.

Gửi yêu cầu sau khi đã thực hiện từng thay đổi:

```bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/health/externalSearch
```

Trong PowerShell có thể dùng `curl.exe` để gọi đúng chương trình curl. Các URL trên giả sử cổng `8080`, đường dẫn management mặc định, không có context path bổ sung và người gọi được phép truy cập.

Giả sử mọi contributor khác đều `UP`, không có ánh xạ HTTP tùy chỉnh và `externalSearch` được chọn vào báo cáo đang xét:

| Giai đoạn | Contributor externalSearch | Health tổng hợp |
| --- | --- | --- |
| Chưa kích hoạt | Chưa có trong registry | Do các contributor còn lại quyết định |
| Đã `activate()`, cờ vẫn `false` | `DOWN` | `DOWN`, HTTP 503 |
| Đã `setAvailable(true)` | `UP` | `UP`, HTTP 200 |
| Đã `setAvailable(false)` | Vẫn có mặt và trả `DOWN` | `DOWN`, HTTP 503 |
| Đã `deactivate()` | Không còn trong registry | Do các contributor còn lại quyết định |

Khi component còn tồn tại và được phép hiển thị, URL thành phần có thể trả:

```json
{"status":"DOWN"}
```

Sau khi gỡ, đường dẫn component đó thông thường trả HTTP 404 vì không tìm thấy contributor. Điều này khác với HTTP 503 của một contributor vẫn có mặt nhưng báo `DOWN`. Cấu hình bảo mật có thể khiến người gọi nhận 401/403 trước khi tới phép tra cứu health.

Không suy ra “gỡ xong thì health tổng luôn UP”. Contributor khác có thể vẫn `DOWN`; nếu tập trạng thái được tổng hợp rỗng, kết quả có thể là `UNKNOWN`. Trạng thái tổng do `StatusAggregator` quyết định, còn mã HTTP do `HttpCodeStatusMapper` quyết định.

Việc có mặt trong registry cũng không đảm bảo tên component luôn xuất hiện trong JSON: chính sách hiển thị component, quyền truy cập và bộ lọc của health group đều có thể ảnh hưởng kết quả quan sát. Xem [tài liệu Health Information của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

## 7. Khi có composite, health group hoặc ứng dụng reactive

### Composite: đăng ký một nhánh, không đăng ký đường dẫn giả

Nếu một khách thuê có nhiều tài nguyên con, có thể xây dựng `CompositeHealthContributor` rồi đăng ký nó theo một ID gốc:

```java
HealthIndicator database = () -> Health.up().build();
HealthIndicator cache = () -> Health.down().build();

CompositeHealthContributor tenant = CompositeHealthContributor.fromMap(
        Map.<String, HealthContributor>of(
                "database", database,
                "cache", cache));

registry.registerContributor("tenantAlpha", tenant);
```

Đây là đoạn minh họa cần các import tương ứng từ `java.util.Map` và `org.springframework.boot.actuate.health`, cùng biến `registry` đã có. Cây health có nhánh `tenantAlpha` và các con `database`, `cache`. Đường dẫn thành phần tương ứng có thể là `/actuator/health/tenantAlpha/cache`.

`registry.unregisterContributor("tenantAlpha")` gỡ cả nhánh khỏi registry cấp gốc. Truyền `"tenantAlpha/cache"` vào registry cấp gốc không có nghĩa là nó sẽ tự đi vào composite để xóa con. Thêm hoặc gỡ con động cần do triển khai composite và cơ chế sở hữu của nhánh đó quản lý; `fromMap` không cung cấp API registry con có thể thay đổi.

### Health group: thành viên được chọn còn phụ thuộc cấu hình

Một group cấu hình `include: db` sẽ không tự theo dõi mọi contributor mới có ID khác. Cần kiểm tra đúng group đang quan sát.

Nếu group nêu đích danh contributor chỉ được đăng ký sau khi ứng dụng đã khởi động, bước xác thực thành viên lúc khởi động có thể báo lỗi vì ID chưa tồn tại. Có thể cân nhắc thay đổi thời điểm đăng ký, mô hình group hoặc cấu hình `management.endpoint.health.validate-group-membership` sau khi đánh giá yêu cầu.

Tắt xác thực thành viên không tự tạo contributor còn thiếu và không đảm bảo group luôn có đủ phép kiểm tra quan trọng. Với tài nguyên bắt buộc, giữ một contributor ổn định và thay đổi trạng thái thường giúp báo cáo rõ hơn việc để thành viên lúc có lúc không.

Có thể đối chiếu quy tắc chọn và xác thực thành viên tại [Health Groups của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.groups).

### Reactive: dùng đúng registry mà endpoint đang đọc

Trong ứng dụng WebFlux, dùng `ReactiveHealthContributorRegistry` cho thay đổi động. Khi cần đưa một contributor đồng bộ vào registry reactive, API có `ReactiveHealthContributor.adapt(...)`. Không giả định rằng sửa registry đồng bộ sẽ tự phản chiếu mọi thay đổi sang registry reactive đang phục vụ endpoint.

Phần này chỉ xác định ranh giới API; ví dụ của bài dùng registry đồng bộ. Có thể đối chiếu thêm [HealthContributorRegistry](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthContributorRegistry.html), [CompositeHealthContributor](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeHealthContributor.html) và [ReactiveHealthContributorRegistry](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/ReactiveHealthContributorRegistry.html).

## 8. Đồng thời, thay thế và giải phóng tài nguyên

Triển khai registry mặc định bảo vệ thay đổi cấu trúc của danh sách contributor. Điều đó không biến mọi chuỗi nghiệp vụ thành một giao dịch nguyên tử, cũng không tự làm mã `health()` an toàn khi nhiều luồng gọi.

Những tình huống cần thiết kế rõ:

- **Kiểm tra rồi đăng ký:** giữa `getContributor(id) == null` và `registerContributor(id, value)`, một luồng khác có thể đăng ký trước. Phải có cơ chế sở hữu/điều phối và xử lý xung đột.
- **Gỡ rồi thêm để thay thế:** đó là hai thao tác riêng. Yêu cầu health ở giữa có thể thấy thiếu contributor; nếu bước thêm thất bại, contributor cũ cũng đã bị gỡ. API này không có một thao tác `replaceContributor` nguyên tử.
- **Yêu cầu health đang chạy:** một lượt kiểm tra có thể đã giữ tham chiếu tới contributor trước khi nó bị gỡ. Gỡ khỏi registry không hủy lượt kiểm tra đó và không bảo đảm tất cả yêu cầu đồng thời nhìn cùng một ảnh chụp danh sách.
- **Đóng tài nguyên quá sớm:** không đóng HTTP client hoặc pool chỉ vì `unregisterContributor` vừa trả về, nếu còn nghiệp vụ hoặc phép kiểm tra đang dùng nó. Việc ngừng nhận công việc, chờ xử lý đang chạy và đóng tài nguyên thuộc bộ phận quản lý vòng đời.
- **Nhiều instance ứng dụng:** registry nằm trong tiến trình hiện tại, không phải kho trạng thái phân tán. Thay đổi trên một instance không tự cập nhật các instance khác hoặc tồn tại sau khi khởi động lại. Danh sách mong muốn cần được tái dựng từ nguồn cấu hình/nghiệp vụ có thẩm quyền.

Nếu tài nguyên vẫn tồn tại và chỉ thay đổi tình trạng, hãy giữ ID cùng contributor ổn định, cập nhật dữ liệu kiểm tra theo cách an toàn cho nhiều luồng. Điều này tránh khoảng trống quan sát do gỡ rồi đăng ký lại.

## 9. Lỗi thường gặp và cách phân biệt

| Hiện tượng | Nguyên nhân nên kiểm tra | Cách xử lý phù hợp |
| --- | --- | --- |
| Đăng ký xong nhưng HTTP không đổi | Sửa registry tự tạo, sửa sai loại registry hoặc đang gọi instance khác | Tiêm registry của ứng dụng, xác minh loại ứng dụng và instance |
| Có ID nhưng không thấy component trong JSON | Component bị ẩn hoặc group không chọn ID đó | Kiểm tra chính sách hiển thị, quyền và cấu hình group |
| Đăng ký lần hai ném ngoại lệ | ID đã tồn tại hoặc xung đột với tên được dành cho group | Dùng ID phù hợp và một nơi sở hữu; không coi đăng ký là ghi đè |
| Tra cứu trả `null` | Dùng tên lớp/tên bean thay ID thực tế, sai chữ hoa/thường hoặc đã gỡ | Duyệt tên trong registry và dùng ID nhất quán |
| Health vẫn `DOWN` sau khi gỡ | Contributor khác còn lỗi hoặc phép kiểm tra đồng thời đã bắt đầu | Đọc component cụ thể và phân biệt lượt kiểm tra đang chạy |
| Health “tốt lên” ngay sau khi gỡ | Phép kiểm tra lỗi đã bị loại khỏi tập tổng hợp | Chỉ gỡ khi thay đổi phạm vi giám sát là đúng nghiệp vụ |
| Pool vẫn còn sau khi gỡ contributor | Registry không quản lý việc đóng tài nguyên | Dùng cơ chế vòng đời tài nguyên riêng |
| Gỡ root bằng tên có `/` không xóa được con | Nhầm registry cấp gốc với cấu trúc composite | Quản lý nhánh con tại composite hoặc gỡ đúng ID root |

## 10. Tự thực hành và kiểm tra mức độ hiểu

1. Chạy `RegistryDemo`, giải thích vì sao `checks-after-register=0` dù `present-after=true`.
2. Đổi `available` từ `false` sang `true` mà giữ nguyên bản đăng ký. Nêu khác biệt giữa đổi trạng thái và đổi thành viên.
3. Bỏ khối `try/catch` quanh lần đăng ký trùng và chạy lại. Xác định vì sao chương trình dừng trước bước gỡ.
4. Thêm một contributor thứ hai, gỡ `tenantAlpha` rồi duyệt tên. Xác minh thao tác gỡ chỉ áp dụng cho ID được chỉ định.
5. Trong ứng dụng thử nghiệm, quan sát root health và component health trước/sau khi gỡ. Giải thích vì sao một component không còn tồn tại khác với một component đang `DOWN`.
6. Với yêu cầu “dịch vụ tìm kiếm vẫn bắt buộc nhưng tạm thời không kết nối được”, lựa chọn giữ contributor báo `DOWN` hay gỡ contributor. Giải thích tác động tới người vận hành và hệ thống giám sát.

Sau bài này, người học cần chỉ ra được **ai sở hữu ID**, **registry nào được endpoint sử dụng**, **khi nào cần đổi trạng thái** và **khi nào tài nguyên thực sự phải rời danh sách giám sát**.
