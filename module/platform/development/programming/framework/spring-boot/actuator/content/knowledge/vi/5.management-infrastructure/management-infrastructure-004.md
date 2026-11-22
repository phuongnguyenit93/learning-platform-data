# Nhận diện management context và hạ tầng web riêng khi tách cổng

Khi cấu hình Actuator trên cổng khác cổng ứng dụng, điều thay đổi không chỉ là con số trong URL. Spring Boot còn tổ chức một **ngữ cảnh quản trị (management context)** riêng cùng hạ tầng web phục vụ quản trị.

Muốn chẩn đoán đúng, cần phân biệt bốn đối tượng: tiến trình Java, ngữ cảnh Spring, máy chủ web và ánh xạ HTTP. Hai cổng có thể dùng hai máy chủ web trong hai ngữ cảnh khác nhau, nhưng vẫn nằm trong một JVM và sử dụng chung một số bean.

Bài dùng **Spring Boot 3.3.13, Spring MVC, Java 21 và Gradle 8.5**, với máy chủ web nhúng. Các kết luận và đầu ra thực hành được giới hạn trong cơ chế tự cấu hình chuẩn của dự án mẫu.

## 1. Bốn khái niệm cần nhận diện

| Khái niệm | Vai trò |
| --- | --- |
| Tiến trình Java/JVM | Chạy mã ứng dụng, quản lý bộ nhớ và tài nguyên tiến trình |
| `ApplicationContext` | Ngữ cảnh Spring chứa các định nghĩa bean, đối tượng và dịch vụ liên quan |
| `WebServer` | Đối tượng quản lý máy chủ web nhúng và cổng lắng nghe |
| Ánh xạ HTTP | Quy tắc đưa một yêu cầu như `GET /business` tới thành phần xử lý |

**Ngữ cảnh quản trị** là ngữ cảnh Spring phục vụ các cấu hình quản trị. Nó không đồng nghĩa với một endpoint, một trang discovery hoặc một tiến trình Java thứ hai.

Trong Spring Boot, `WebServerApplicationContext` là giao diện cho ngữ cảnh có quản lý máy chủ web nhúng. Có thể lấy máy chủ bằng `getWebServer()` và nhận diện quan hệ ngữ cảnh bằng `getParent()`. [API ngữ cảnh máy chủ web](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/context/WebServerApplicationContext.html)

## 2. Khi nào dùng chung ngữ cảnh, khi nào có ngữ cảnh con?

### 2.1. Cổng ứng dụng và cổng quản trị dùng chung

Ví dụ:

```properties
server.port=8087
```

Khi không đặt cổng quản trị riêng, Actuator HTTP dùng cùng cổng ứng dụng. Đặt rõ `management.server.port=8087` với cổng ứng dụng cũng là `8087` vẫn là bố trí dùng chung.

Mô hình đơn giản của dự án mẫu:

```text
Một JVM
└── Ngữ cảnh ứng dụng chính
    └── Máy chủ web: 8087
        ├── /business
        └── /actuator/info
```

Không có một ngữ cảnh quản trị web con riêng chỉ vì thêm thư viện Actuator.

### 2.2. Cổng quản trị khác cổng ứng dụng

```properties
server.port=8087
management.server.port=9087
```

Trong bố trí này, Spring Boot tạo ngữ cảnh quản trị riêng có ngữ cảnh chính làm cha:

```text
Một JVM
└── Ngữ cảnh ứng dụng chính
    ├── Bean nghiệp vụ và hạ tầng ứng dụng
    ├── Máy chủ web chính: 8087
    │   └── /business
    └── Ngữ cảnh quản trị con
        └── Máy chủ web quản trị: 9087
            └── /actuator/info
```

Nhánh con trong hình biểu diễn quan hệ cha–con giữa các ngữ cảnh. Nó không có nghĩa máy chủ web chính chuyển tiếp từng yêu cầu sang máy chủ quản trị.

Hợp đồng này được mô tả trực tiếp trong `ManagementContextAutoConfiguration`: cùng cổng dùng cùng ngữ cảnh; khác cổng dùng ngữ cảnh riêng có ngữ cảnh ứng dụng chính làm cha. [API tự cấu hình management context](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/web/server/ManagementContextAutoConfiguration.html)

## 3. Quan hệ cha–con quyết định cách tìm bean

### 3.1. Ngữ cảnh con có thể tìm bean ở cha

Nếu ngữ cảnh quản trị không có bean tên `sharedMarker` tại chỗ, phép tra cứu `getBean("sharedMarker")` có thể đi lên bean factory của cha.

Với bean singleton do cha sở hữu và không bị che bởi bean cùng tên ở con, cả hai phép tra cứu có thể trả về **cùng một đối tượng**. Spring không cần sao chép hoặc tạo lại bean chỉ vì có ngữ cảnh quản trị.

Chiều tìm kiếm thông thường đi từ con lên cha. Ngữ cảnh cha không tự tìm xuống mọi ngữ cảnh con để giải quyết một phụ thuộc. Nếu con có bean cùng tên, phép tra cứu từ con có thể chọn bean tại con trước. [Quy tắc tra cứu của `BeanFactory`](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/BeanFactory.html)

### 3.2. “Tìm thấy” khác với “sở hữu tại chỗ”

Hai câu hỏi cần tách biệt:

| Phép kiểm tra | Câu hỏi |
| --- | --- |
| `context.containsBean("sharedMarker")` | Ngữ cảnh có thể tìm thấy tên bean theo cơ chế tra cứu không? |
| `context.containsLocalBean("sharedMarker")` | Bean có thuộc bean factory tại chính ngữ cảnh này không? |

Trong thí nghiệm tách cổng, ngữ cảnh quản trị có thể tìm thấy `sharedMarker`, nhưng `containsLocalBean` trả `false` vì bean được đăng ký ở cha.

Việc đếm hoặc liệt kê bean cũng cần xem hợp đồng API. Không nên mặc định mọi phương thức liệt kê đều tự cộng bean ở các ngữ cảnh tổ tiên. Bài dùng tra cứu theo tên và kiểm tra bean tại chỗ để tránh lẫn hai phạm vi này.

### 3.3. Một singleton không có nghĩa một bản cho toàn JVM

Trong Spring, phạm vi singleton gắn với bean factory sở hữu bean. Nếu chủ động tạo một bean cùng kiểu ở cả cha và con, có thể có hai đối tượng khác nhau.

Điều giúp ví dụ dùng chung đối tượng là **bean chỉ được khai báo ở cha và con tìm lên cha**, không phải một quy tắc rằng mọi bean cùng kiểu trong JVM phải có cùng danh tính.

## 4. Bean nhìn thấy được chưa chắc có ánh xạ HTTP ở cổng đó

Một controller có thể là bean ở ngữ cảnh cha. Ngữ cảnh con có thể tìm thấy bean này qua cơ chế phân cấp, nhưng việc phục vụ `GET /business` còn phụ thuộc các thành phần ánh xạ và xử lý HTTP của máy chủ quản trị.

Spring MVC có cơ chế xác định các phương thức handler trong ngữ cảnh. Cờ `detectHandlerMethodsInAncestorContexts` của `AbstractHandlerMethodMapping` mặc định là `false`: việc phát hiện handler tập trung vào ngữ cảnh hiện tại. [API phát hiện handler trong ngữ cảnh tổ tiên](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/handler/AbstractHandlerMethodMapping.html#setDetectHandlerMethodsInAncestorContexts(boolean))

Vì vậy, trong cấu hình mẫu:

- Cổng chính phục vụ controller `/business`.
- Cổng quản trị phục vụ endpoint Actuator được chọn công bố.
- Khả năng tìm thấy bean `businessController` từ ngữ cảnh quản trị không tự làm `/business` xuất hiện ở cổng quản trị.

Đây là quan hệ cần nhớ khi đọc lỗi `404`: bean tồn tại và đường dẫn được ánh xạ là hai bằng chứng khác nhau.

Cấu hình web tùy biến có thể thay đổi hành vi. Khi ứng dụng có filter, interceptor, servlet hoặc cấu hình MVC riêng, cần kiểm chứng phạm vi đăng ký thực tế thay vì giả định chúng được áp dụng giống hệt trên hai phía.

## 5. Những gì được tách và những gì vẫn dùng chung

| Thành phần | Cách hiểu trong bố trí tách cổng chuẩn |
| --- | --- |
| Ngữ cảnh quản trị | Là ngữ cảnh con riêng |
| Đối tượng máy chủ web quản trị | Khác đối tượng máy chủ web chính |
| Cổng và điểm tiếp nhận HTTP | Riêng theo cấu hình |
| Các thành phần xử lý web | Được tổ chức cho hạ tầng web của phía tương ứng |
| Bean singleton ở cha mà con dùng qua tra cứu | Có thể vẫn là cùng đối tượng |
| Pool dữ liệu do một bean ở cha quản lý | Không tự nhân đôi chỉ vì tách cổng |
| JVM, bộ nhớ tiến trình, CPU và việc tiến trình dừng | Vẫn cùng một tiến trình |

Tách hạ tầng tiếp nhận HTTP giúp quản trị có điểm truy cập riêng. Nó không tạo ra hai hệ thống độc lập hoàn toàn về lỗi hoặc tài nguyên.

Chẳng hạn, máy chủ chính có thể gặp vấn đề nhận kết nối mới trong khi máy chủ quản trị vẫn trả lời. Ngược lại, cạn bộ nhớ JVM hoặc tiến trình dừng có thể ảnh hưởng cả hai. Không nên dùng từ “cô lập” mà chưa chỉ rõ đang nói đến lớp mạng, hạ tầng web hay toàn bộ tiến trình.

## 6. Nhận diện đúng máy chủ qua sự kiện khởi tạo

Spring Boot phát `WebServerInitializedEvent` khi máy chủ web đã sẵn sàng. Sự kiện cho phép lấy:

- Ngữ cảnh đã tạo máy chủ: `event.getApplicationContext()`.
- Máy chủ và cổng thực tế: `event.getWebServer().getPort()`.

Đây là bằng chứng trực tiếp hơn việc chỉ đọc một chuỗi cấu hình cổng. [API sự kiện khởi tạo máy chủ web](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/context/WebServerInitializedEvent.html)

Một điểm dễ nhầm là **sự kiện của ngữ cảnh con có thể được chuyển lên các listener của ngữ cảnh tổ tiên**. Listener ở ứng dụng chính vì vậy có thể thấy sự kiện thuộc máy chủ quản trị.

Nếu cứ lấy cổng của mọi sự kiện rồi ghi đè vào một biến `applicationPort`, bạn có thể gán nhầm cổng quản trị thành cổng chính. Cần đối chiếu danh tính ngữ cảnh của sự kiện. [Sự kiện trong hệ ngữ cảnh cha–con](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)

Ví dụ bên dưới lưu **tập các đối tượng ngữ cảnh đã quan sát**, thay vì đếm số lần listener được gọi hoặc phụ thuộc thứ tự sự kiện.

## 7. Thực hành hoàn chỉnh: quan sát ngữ cảnh, máy chủ và bean

Dự án mẫu có một controller ứng dụng, một bean đánh dấu dùng chung và một đoạn quan sát hạ tầng. Đoạn quan sát không tự tạo ngữ cảnh quản trị; Spring Boot làm việc đó theo cấu hình cổng.

Cần JDK 21, Gradle 8.5 và kết nối để tải phụ thuộc lần đầu. Cổng `8087` và `9087` phải trống. Ví dụ không thêm Spring Security, proxy, ngữ cảnh tùy biến hoặc bộ ánh xạ HTTP khác.

Các đầu ra được nêu là **kết quả mong đợi với đúng dự án mẫu**.

### 7.1. Cấu trúc dự án

```text
management-context-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/
    │   ├── ManagementContextApplication.java
    │   └── BusinessController.java
    └── resources/application.properties
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'management-context-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

### 7.2. Mã quan sát

Tệp `src/main/java/example/ManagementContextApplication.java`:

```java
package example;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ManagementContextApplication {

    public static void main(String[] args) {
        Set<WebServerApplicationContext> observedContexts =
                ConcurrentHashMap.newKeySet();

        SpringApplication application =
                new SpringApplication(ManagementContextApplication.class);

        application.addListeners(
                (ApplicationListener<WebServerInitializedEvent>) event ->
                        observedContexts.add(event.getApplicationContext()));

        WebServerApplicationContext mainContext =
                (WebServerApplicationContext) application.run(args);

        WebServerApplicationContext managementContext = observedContexts.stream()
                .filter(context -> context != mainContext
                        && context.getParent() == mainContext)
                .findFirst()
                .orElse(mainContext);

        boolean separate = managementContext != mainContext;

        Object markerFromMain = mainContext.getBean("sharedMarker");
        Object markerFromManagement =
                managementContext.getBean("sharedMarker");

        System.out.println("WEB_CONTEXTS=" + observedContexts.size());
        System.out.println("SEPARATE_MANAGEMENT_CONTEXT=" + separate);
        System.out.println("MAIN_PORT="
                + mainContext.getWebServer().getPort());
        System.out.println("MANAGEMENT_PORT="
                + managementContext.getWebServer().getPort());
        System.out.println("SAME_WEB_SERVER_INSTANCE="
                + (mainContext.getWebServer()
                        == managementContext.getWebServer()));
        System.out.println("MANAGEMENT_PARENT_IS_MAIN="
                + (separate
                        && managementContext.getParent() == mainContext));
        System.out.println("MANAGEMENT_HAS_LOCAL_MARKER="
                + managementContext.containsLocalBean("sharedMarker"));
        System.out.println("SAME_MARKER_INSTANCE="
                + (markerFromMain == markerFromManagement));
        System.out.println("MANAGEMENT_CAN_RESOLVE_CONTROLLER="
                + managementContext.containsBean("businessController"));
    }

    @Bean
    SharedMarker sharedMarker() {
        return new SharedMarker("owned-by-main");
    }

    public record SharedMarker(String label) {
    }
}
```

Cách đọc mã:

1. Listener được đăng ký trước khi chạy ứng dụng để quan sát các sự kiện máy chủ.
2. Tập `observedContexts` lưu ngữ cảnh theo đối tượng; nhiều thông báo liên quan cùng ngữ cảnh không bị tính thành nhiều ngữ cảnh khác nhau.
3. Sau khi `run` trả về, mã biết chính xác đối tượng ngữ cảnh chính.
4. Trong dự án mẫu chỉ có một ngữ cảnh web con phục vụ quản trị, nên có thể nhận diện nó qua quan hệ `getParent() == mainContext`.
5. Nếu không có ngữ cảnh con như vậy, phép quan sát dùng ngữ cảnh chính làm phía quản trị dùng chung.
6. Mã so sánh cả danh tính máy chủ và danh tính bean, thay vì suy luận hai điều đó từ số cổng.

Đây là công cụ quan sát cho bố trí tối thiểu của bài. Ứng dụng có nhiều ngữ cảnh web con cần thêm tiêu chí nhận diện; không nên lấy “ngữ cảnh con đầu tiên” làm bộ dò tổng quát cho mọi kiến trúc.

### 7.3. Controller và cấu hình

Tệp `src/main/java/example/BusinessController.java`:

```java
package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BusinessController {

    @GetMapping("/business")
    public String business() {
        return "BUSINESS_OK";
    }
}
```

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8087
spring.jmx.enabled=false

management.endpoints.enabled-by-default=false
management.endpoint.health.enabled=true
management.endpoint.info.enabled=true
management.endpoints.web.exposure.include=health,info
management.endpoints.web.base-path=/actuator
```

Không đặt cổng quản trị trong tệp ban đầu để lần chạy A dùng chung ngữ cảnh.

### 7.4. Lần A: dùng chung cổng và ngữ cảnh

Tại thư mục dự án:

```powershell
gradle bootJar
java -jar build/libs/management-context-demo-1.0.0.jar
```

Nếu đã có Gradle Wrapper 8.5, thay lệnh đầu bằng `.\gradlew.bat bootJar`. Gradle biên dịch với các thư viện Spring và đóng gói JAR; không dùng `javac` đơn lẻ cho ví dụ này.

Ngoài nhật ký khởi động của Spring Boot, các dòng do chương trình in ra là:

```text
WEB_CONTEXTS=1
SEPARATE_MANAGEMENT_CONTEXT=false
MAIN_PORT=8087
MANAGEMENT_PORT=8087
SAME_WEB_SERVER_INSTANCE=true
MANAGEMENT_PARENT_IS_MAIN=false
MANAGEMENT_HAS_LOCAL_MARKER=true
SAME_MARKER_INSTANCE=true
MANAGEMENT_CAN_RESOLVE_CONTROLLER=true
```

`MANAGEMENT_PARENT_IS_MAIN=false` ở đây không phải lỗi: phía quản trị chính là ngữ cảnh chính, không có ngữ cảnh con để mang quan hệ cha–con đó.

Mở cửa sổ PowerShell thứ hai:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/business
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
```

Đầu ra mong đợi:

```text
200
200
```

Hai nhóm yêu cầu cùng đi qua máy chủ web chính.

### 7.5. Lần B: tách cổng, quan sát ngữ cảnh con

Dừng lần A bằng `Ctrl+C`, rồi chạy lại cùng JAR:

```powershell
java -jar build/libs/management-context-demo-1.0.0.jar --management.server.port=9087 --management.server.address=127.0.0.1
```

Các dòng quan sát mong đợi:

```text
WEB_CONTEXTS=2
SEPARATE_MANAGEMENT_CONTEXT=true
MAIN_PORT=8087
MANAGEMENT_PORT=9087
SAME_WEB_SERVER_INSTANCE=false
MANAGEMENT_PARENT_IS_MAIN=true
MANAGEMENT_HAS_LOCAL_MARKER=false
SAME_MARKER_INSTANCE=true
MANAGEMENT_CAN_RESOLVE_CONTROLLER=true
```

Đọc từng nhóm bằng chứng:

- `WEB_CONTEXTS=2` và `SEPARATE_MANAGEMENT_CONTEXT=true`: có hai đối tượng ngữ cảnh web được quan sát trong bố trí mẫu.
- `MANAGEMENT_PARENT_IS_MAIN=true`: ngữ cảnh quản trị được nhận diện là con của ngữ cảnh chính.
- `SAME_WEB_SERVER_INSTANCE=false`: hai ngữ cảnh dùng hai đối tượng máy chủ web khác nhau.
- `MANAGEMENT_HAS_LOCAL_MARKER=false` nhưng `SAME_MARKER_INSTANCE=true`: ngữ cảnh con tìm lên cha và lấy cùng bean đánh dấu.
- `MANAGEMENT_CAN_RESOLVE_CONTROLLER=true`: bean controller ở cha vẫn nằm trong phạm vi tra cứu từ con.

Chưa thể dùng dòng cuối để kết luận controller được phục vụ qua cổng quản trị. Cần tiếp tục kiểm tra HTTP.

### 7.6. Lần B: đối chiếu phạm vi ánh xạ HTTP

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/business
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:9087/actuator/info
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:9087/business
```

Đầu ra mong đợi:

```text
200
404
200
404
```

Kết hợp với stdout:

- Controller ở cha tìm thấy được từ con.
- Nhưng `/business` không được tự công bố trên cổng quản trị.
- Actuator `info` được phục vụ bởi hạ tầng web quản trị ở cổng `9087`.

Các mã này áp dụng cho mẫu không có bảo mật hoặc ánh xạ thay thế. Ở ứng dụng thực tế, một bộ lọc có thể xử lý yêu cầu trước bước tìm handler.

### 7.7. Lần C: đặt rõ cùng số cổng

Dừng lần B, rồi chạy:

```powershell
java -jar build/libs/management-context-demo-1.0.0.jar --management.server.port=8087
```

Tham số địa chỉ quản trị của lần B không tự đi theo tiến trình mới.

Các kết quả quan sát quay về bố trí dùng chung của lần A: một ngữ cảnh web được quan sát, cùng đối tượng máy chủ, và bean đánh dấu thuộc chính ngữ cảnh được dùng cho phía quản trị.

Lần này giúp phân biệt “có khai báo khóa `management.server.port`” với “thực sự tách cổng và ngữ cảnh”.

### 7.8. Bảng so sánh

| Bằng chứng | Chung cổng | Tách cổng |
| --- | --- | --- |
| Số ngữ cảnh web quan sát trong mẫu | 1 | 2 |
| Ngữ cảnh quản trị con | Không có | Có |
| Đối tượng máy chủ web chính và quản trị | Cùng | Khác |
| Bean `sharedMarker` lấy từ hai phía | Cùng đối tượng | Vẫn cùng đối tượng |
| Ngữ cảnh quản trị có bean đánh dấu tại chỗ | Có, vì là chính ngữ cảnh chính | Không, bean đánh dấu thuộc cha |
| Controller cha tìm thấy được từ phía quản trị | Có | Có qua phân cấp |
| `/business` tự được phục vụ trên cổng quản trị riêng | Không có cổng riêng để xét | Không trong mẫu chuẩn |

Không lấy riêng một hàng để thay cho toàn bộ mô hình. Chẳng hạn, bean dùng chung không phủ nhận hai máy chủ web riêng; hai máy chủ web riêng cũng không chứng minh các bean dữ liệu đã được nhân đôi.

## 8. Đọc dấu hiệu hạ tầng mà không suy diễn quá mức

### 8.1. Hai dòng máy chủ khởi động là dấu hiệu, chưa phải bản đồ ngữ cảnh

Nhật ký có thể cho thấy máy chủ web khởi động ở hai cổng. Đây là bằng chứng hữu ích, nhưng muốn gắn từng cổng với ngữ cảnh, nên đối chiếu sự kiện hoặc đối tượng khi chương trình chạy.

Không dùng chuỗi ID ngữ cảnh chứa một từ quen thuộc làm tiêu chí duy nhất. ID, dạng nhật ký hoặc tên lớp triển khai có thể thay đổi theo cấu hình. Quan hệ cha–con và danh tính đối tượng là bằng chứng trực tiếp trong ví dụ.

`WebServerApplicationContext` cũng cung cấp không gian tên máy chủ (server namespace) để phân biệt các máy chủ trong một ứng dụng. Khi dùng thông tin này trong công cụ chẩn đoán, hãy kiểm tra giá trị khi chương trình chạy và hợp đồng cấu hình thay vì đoán theo tên hiển thị.

### 8.2. Không mặc định mọi tùy biến web đều có tác động giống nhau

Một filter hoặc cấu hình MVC cần được xét theo nơi đăng ký và máy chủ thực sự xử lý yêu cầu. Việc một bean có thể tra cứu từ con không thay thế việc kiểm tra nó có được gắn vào chuỗi xử lý servlet hay không.

Tương tự, không suy ra các thiết lập về luồng, kết nối hoặc TLS của máy chủ chính luôn được áp dụng nguyên trạng cho phía quản trị. Cần đọc cấu hình và cơ chế tùy biến đang dùng, rồi kiểm chứng yêu cầu trên cả hai cổng.

Đây cũng là lý do không nên “sửa nhanh” bằng cách quét lại toàn bộ gói nghiệp vụ trong ngữ cảnh quản trị: hành động đó có thể làm phát sinh bean hoặc ánh xạ ngoài ý định.

### 8.3. Đường dẫn vẫn thuộc phạm vi của máy chủ tương ứng

Khi tách cổng, đường dẫn Actuator được tính theo `management.server.base-path` và `management.endpoints.web.base-path`. Context path của ứng dụng chính không tự được cộng vào đường dẫn quản trị.

Ví dụ, với `management.server.base-path=/ops` và gốc endpoint `/actuator`, địa chỉ `info` trên cổng quản trị là `/ops/actuator/info`. Đọc đúng ngữ cảnh nhưng gọi sai tiền tố vẫn có thể nhận `404`. [Đường dẫn trên máy chủ quản trị](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)

## 9. Hệ quả đối với giám sát, bảo mật và vòng đời

### 9.1. Kiểm tra sức khỏe ở cổng quản trị chưa bao quát toàn bộ web chính

Hạ tầng web quản trị riêng có thể còn trả lời khi cổng ứng dụng chính gặp vấn đề nhận kết nối. Vì vậy, phản hồi sức khỏe trên cổng quản trị cần được diễn giải theo mục tiêu phép kiểm tra.

Spring Boot hỗ trợ đưa thêm các nhóm kiểm tra sức sống và sẵn sàng phục vụ lên cổng chính:

```properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
```

Khi được bật và công bố phù hợp, có thêm các đường dẫn `/livez` và `/readyz` trên cổng chính. Tính năng này không tự được bật chỉ vì có management context riêng. [Probes khi dùng ngữ cảnh quản trị riêng](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)

### 9.2. Quan hệ ngữ cảnh không thay thế chính sách truy cập

Tách máy chủ quản trị tạo điểm tiếp nhận riêng để cấu hình địa chỉ lắng nghe và đường mạng. Endpoint nào được công bố, ai được gọi và dữ liệu nào được trả vẫn cần chính sách tương ứng.

Khi có Spring Security hoặc cấu hình servlet tùy biến, hãy kiểm chứng trên đúng cổng. Không suy ra rằng ngữ cảnh con tự tạo một ranh giới xác thực hoàn toàn độc lập, cũng không suy ra mọi quy tắc ở cha được sao chép nguyên trạng.

### 9.3. Vòng đời vẫn gắn với một ứng dụng

Bố trí này được Spring Boot quản lý trong một tiến trình. Không có một dịch vụ quản trị độc lập để tiếp tục hoạt động khi JVM chính đã dừng.

Khi chẩn đoán khởi động, cần xem kết quả toàn ứng dụng và cả hai máy chủ. Một dòng nhật ký cho thấy máy chủ chính đã mở cổng chưa đủ để kết luận ngữ cảnh quản trị đã khởi động thành công.

## 10. Tự kiểm tra bằng các câu hỏi cụ thể

1. Vì sao tách cổng có thể tạo hai đối tượng `WebServer` nhưng vẫn lấy được cùng bean `sharedMarker`?
2. `containsBean` và `containsLocalBean` trả lời hai câu hỏi khác nhau như thế nào?
3. Tại sao `MANAGEMENT_CAN_RESOLVE_CONTROLLER=true` vẫn đi cùng HTTP `404` khi gọi `9087/business`?
4. Vì sao listener ở ứng dụng chính có thể nhận sự kiện của máy chủ quản trị?
5. Nếu ghi mọi cổng từ sự kiện vào cùng một biến mà không kiểm tra ngữ cảnh, bạn có thể gán nhầm điều gì?
6. Hai máy chủ web riêng còn chia sẻ những giới hạn nào của JVM?
7. Một phép kiểm tra sức khỏe trên cổng quản trị thành công còn chưa chứng minh điều gì về cổng chính?
8. Nếu ứng dụng có nhiều ngữ cảnh web con, cần bổ sung gì vào tiêu chí nhận diện của ví dụ?

Để trả lời tốt, hãy nối từng kết luận với đúng bằng chứng: ngữ cảnh từ sự kiện, quan hệ từ `getParent()`, máy chủ từ `getWebServer()`, bean từ phép tra cứu và ánh xạ từ yêu cầu HTTP. Cách phân biệt này giúp đọc đúng hạ tầng quản trị khi số cổng và số ngữ cảnh tăng lên.
