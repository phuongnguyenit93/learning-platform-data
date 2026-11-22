# Thứ tự @PreDestroy, DisposableBean và destroyMethod khi Spring hủy bean

## 1. Tại sao thứ tự callback hủy bean quan trọng?

Một bean Spring có thể sở hữu connection, thread, bộ đệm, file handle, subscription hoặc tài nguyên bên ngoài. Khi ứng dụng dừng, Spring cần gọi các bước dọn dẹp để trả tài nguyên về trạng thái an toàn. Nếu một bean đồng thời khai báo nhiều cơ chế dọn dẹp, câu hỏi xuất hiện là: **phương thức nào chạy trước, phương thức nào chạy sau và tại thời điểm nào chúng được gọi?**

Trong các phiên bản Spring Framework 6.x / Spring Boot 3.x, nếu **cùng một bean do Spring quản lý** sử dụng ba callback hủy **có tên phương thức khác nhau**, thứ tự thông thường là:

1. **`@PreDestroy`**: callback được xử lý thông qua `DestructionAwareBeanPostProcessor`, điển hình là hạ tầng xử lý chú thích `@PreDestroy`.
2. **`DisposableBean.destroy()`**: callback của interface `org.springframework.beans.factory.DisposableBean`.
3. **Custom destroy method**: phương thức cấu hình qua `@Bean(destroyMethod = "...")` hoặc bean definition tương đương.

```text
ApplicationContext.close()
         |
         v
  Bắt đầu hủy singleton do context quản lý
         |
         v
  [1] @PreDestroy
         |
         v
  [2] DisposableBean.destroy()
         |
         v
  [3] @Bean(destroyMethod = "cleanup")
         |
         v
  Bean hoàn tất chuỗi callback dọn dẹp
```

Đây là **thứ tự các cơ chế trên cùng một bean**, khi chúng thực sự được đăng ký và được gọi. Nó **không** nói rằng Spring sẽ gọi `@PreDestroy` của *mọi* bean trước, rồi mới gọi `DisposableBean.destroy()` của *mọi* bean. Spring thường hoàn tất các callback của từng bean khi hủy bean đó, theo quan hệ phụ thuộc và cơ chế hủy singleton.

Vì vậy trước khi hỏi “callback nào chạy trước”, cần xác định rõ **cùng một bean hay nhiều bean**, **scope nào**, **ai quản lý đối tượng**, và **context đã được đóng đúng cách hay chưa**.

## 2. Ba cách khai báo và trách nhiệm của từng cách

| Cơ chế | Khai báo ở đâu? | Cách Spring gọi | Ưu điểm và đánh đổi |
| --- | --- | --- | --- |
| `@PreDestroy` | Trên phương thức của lớp bean | Hạ tầng `BeanPostProcessor` gọi trước khi hủy bean | Ít phụ thuộc Spring API; dễ đọc; cần chú thích `jakarta.annotation.PreDestroy` trong Boot 3 |
| `DisposableBean` | Lớp `implements DisposableBean` | Spring gọi phương thức `destroy()` | Rõ hợp đồng framework; gắn lớp với API Spring |
| `destroyMethod` | Metadata của bean, thường là thuộc tính `@Bean(destroyMethod = "cleanup")` | Spring gọi phương thức được chỉ định hoặc suy luận theo quy tắc | Phù hợp lớp thư viện bên thứ ba không thể sửa; không cần viết Spring API vào lớp |

Ví dụ ba dạng cơ bản, đặt trong những ngữ cảnh khai báo độc lập:

**Dùng `@PreDestroy`:**

```java
import jakarta.annotation.PreDestroy;

public class MessageCache {

    @PreDestroy
    public void clear() {
        System.out.println("Cleaning message cache");
    }
}
```

Để callback hoạt động, `MessageCache` phải được tạo như **bean do container quản lý**, chẳng hạn qua `@Component` hoặc `@Bean`. Một đối tượng tạo bằng `new MessageCache()` bên ngoài Spring không tự có callback container.

**Dùng `DisposableBean`:**

```java
import org.springframework.beans.factory.DisposableBean;

public class SocketManager implements DisposableBean {

    @Override
    public void destroy() throws Exception {
        System.out.println("Closing managed sockets");
    }
}
```

Spring biết rằng bean triển khai `DisposableBean` và gọi `destroy()` khi bean được hủy theo vòng đời container. Một bean không cần thêm `@PreDestroy` nếu chỉ muốn cơ chế này.

**Dùng `@Bean(destroyMethod = "...")`:**

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ThirdPartyClient thirdPartyClient() {
        return new ThirdPartyClient();
    }
}
```

`ThirdPartyClient` là **kiểu minh họa** thuộc thư viện bên ngoài, cần tồn tại trong dự án với một phương thức `shutdown()` thích hợp. Đoạn này chứng minh rằng ta có thể yêu cầu Spring gọi phương thức hủy mà không sửa source của thư viện.

**Nên dùng cách nào?** Với bean do chính nhóm phát triển sở hữu, `@PreDestroy` thường dễ hiểu và ít gắn với Spring hơn interface. Với lớp từ SDK bên ngoài có sẵn `close()` hoặc `shutdown()`, `destroyMethod` thường thuận tiện. `DisposableBean` hợp lý khi cố tình định nghĩa một thành phần hạ tầng tích hợp chặt với Spring. Không cần gắn cả ba cơ chế cho một bean chỉ để đảm bảo dọn dẹp; ví dụ kết hợp ba cơ chế dưới đây nhằm minh họa thứ tự.

## 3. Ví dụ hoàn chỉnh: cả ba callback nằm trên cùng một bean

Ví dụ này chạy với **Java 17+**, **Spring Boot 3.3.x**, dependency `spring-boot-starter` và một dự án Maven/Gradle đã cấu hình Spring Boot.

Tạo file:

```text
src/main/java/demo/lifecycle/DestroyOrderApplication.java
```

Nội dung:

```java
package demo.lifecycle;

import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DestroyOrderApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(DestroyOrderApplication.class, args)) {
            System.out.println("app.running");
        }

        System.out.println("app.closed");
    }

    @Bean(destroyMethod = "customCleanup")
    CleanupProbe cleanupProbe() {
        return new CleanupProbe();
    }
}

class CleanupProbe implements DisposableBean {

    @PreDestroy
    public void beforeDestroy() {
        System.out.println("1. @PreDestroy");
    }

    @Override
    public void destroy() {
        System.out.println("2. DisposableBean.destroy()");
    }

    public void customCleanup() {
        System.out.println("3. @Bean(destroyMethod)");
    }
}
```

Để tập trung vào vòng đời bean, thêm:

`src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
```

Dependency Gradle trong dự án dùng Spring Boot Gradle plugin:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Chạy bằng Gradle wrapper:

```bash
./gradlew bootRun
```

Hoặc đóng gói rồi chạy executable JAR thực tế:

```bash
./gradlew bootJar
java -jar build/libs/ten-file-jar-thuc-te.jar
```

Phần dòng do **chương trình ví dụ** tự in ra:

```text
app.running
1. @PreDestroy
2. DisposableBean.destroy()
3. @Bean(destroyMethod)
app.closed
```

Spring Boot có thể in thêm log trước, giữa hoặc sau các dòng minh họa; thứ tự của năm dòng do mã ví dụ in ra là kết quả cần kiểm chứng. Nếu một framework khác hoặc bean khác cũng in log trong lúc đóng, tổng stdout không chỉ có năm dòng trên.

### Phân tích từng bước

- `SpringApplication.run(...)` tạo, refresh và trả về `ConfigurableApplicationContext`.
- Phương thức `cleanupProbe()` khai báo một bean singleton (mặc định) do Spring quản lý.
- Bean được đăng ký với **metadata hủy riêng**: `destroyMethod = "customCleanup"`.
- Class của bean được phát hiện có `@PreDestroy` và triển khai `DisposableBean`.
- Khối `try-with-resources` đóng `ConfigurableApplicationContext` khi ra khỏi khối, nên callback dọn dẹp được gọi trước dòng `app.closed`.
- Spring gọi `beforeDestroy()`, `destroy()`, rồi `customCleanup()` theo đúng thứ tự.

**Điều kiện then chốt:** ví dụ cố ý dùng **ba tên phương thức khác nhau** để có thể quan sát ba lần gọi riêng biệt, tránh trường hợp một method được nhiều cơ chế cùng khai báo nhưng bị loại gọi trùng.

### Một lỗi diễn giải thường gặp

Nếu bỏ `try-with-resources` và không gọi `context.close()` thủ công, chương trình có thể vẫn được Spring Boot đăng ký JVM shutdown hook để đóng context khi JVM kết thúc bình thường. Tuy nhiên, thời điểm shutdown hook chạy phụ thuộc vòng đời tiến trình; không nên dùng điều đó để dự đoán chính xác một dòng dọn dẹp sẽ xuất hiện ngay sau dòng `app.running`. Ví dụ dùng `try-with-resources` để bảo đảm **thời điểm đóng context quan sát được**.

Nếu ứng dụng có web server, việc đóng context có thể kích hoạt thêm việc ngừng tiếp nhận request và đóng web server. Những thao tác này thuộc vòng đời context/web server, không thay đổi thứ tự ba callback trên **cùng một bean**.

## 4. Spring gọi ba cơ chế theo trình tự nào ở bên trong?

Trong hệ thống quản lý singleton của Spring, một adapter hủy bean có nhiệm vụ kết hợp các callback đã được đăng ký.

Có thể mô tả gần đúng bằng pseudo-code Java:

```java
void destroyManagedBean(Object bean, String beanName) {

    // 1. Hạ tầng xử lý @PreDestroy và các post-processor hủy.
    for (DestructionAwareBeanPostProcessor processor : destroyProcessors) {
        processor.postProcessBeforeDestruction(bean, beanName);
    }

    // 2. Callback đặc trưng của Spring.
    if (bean instanceof DisposableBean disposable) {
        disposable.destroy();
    }

    // 3. Phương thức destroy được khai báo trong bean definition.
    invokeConfiguredDestroyMethodIfPresent(bean);
}
```

Đây là **pseudo-code giải thích thứ tự**, không phải một class hoàn chỉnh và không chép nguyên source Spring Framework; trong triển khai thật còn có logic chọn phương thức, suy luận `close/shutdown`, tránh trùng lặp và xử lý exception.

`@PreDestroy` được hạ tầng xử lý chú thích đăng ký thông qua cơ chế `DestructionAwareBeanPostProcessor`. Trong Spring Framework, bộ xử lý cho các chú thích lifecycle có thể nhận diện phương thức đã được đánh dấu và kích hoạt nó trước bước `DisposableBean`.

Tiếp theo, adapter kiểm tra bean có triển khai `DisposableBean`. Nếu có, Spring gọi trực tiếp `destroy()` theo hợp đồng interface.

Cuối cùng, nếu bean definition khai báo một phương thức hủy khác, Spring gọi phương thức đó. Như vậy thứ tự không phải do vị trí các method trong file Java, thứ tự import hay thứ tự chú thích trong source quyết định; **nó được framework điều phối ở giai đoạn bean destruction**.

Một cách ghi nhớ:

```text
Annotation callback
        ↓
Spring interface callback
        ↓
Bean-definition custom callback
```

Khi đọc log, nếu một callback không có mặt, hãy xem **có đăng ký cơ chế đó hay không** trước khi nghi ngờ thứ tự bị đảo ngược.

## 5. @PreDestroy: thời điểm phát hiện, yêu cầu và giới hạn

Trong Spring Boot 3.x, dùng:

```java
import jakarta.annotation.PreDestroy;
```

Đối với các dự án Spring Boot 2.x cũ, nhiều ví dụ trên mạng dùng `javax.annotation.PreDestroy`. Spring Framework 6 / Boot 3 đã chuyển sang hệ Jakarta, vì vậy import sai namespace có thể dẫn đến lỗi biên dịch hoặc chú thích không được xử lý như kỳ vọng. Không trộn hướng dẫn của các thế hệ Spring mà không kiểm tra dependency.

Một phương thức `@PreDestroy` thông dụng là method instance, không tham số và trả về `void`:

```java
@Component
public class ReportBuffer {

    @PreDestroy
    public void flushAndClose() {
        System.out.println("Closing report buffer");
    }
}
```

Đoạn trên cần import `org.springframework.stereotype.Component`, `jakarta.annotation.PreDestroy` và nằm trong file `ReportBuffer.java` có package phù hợp. Nó hoạt động khi bean được Spring quét hoặc đăng ký và context đóng theo vòng đời chuẩn.

Các điểm cần nhớ:

1. **Không phải gọi bằng tay**: Spring gọi phương thức khi destroy bean. Gọi `flushAndClose()` từ logic nghiệp vụ là một thao tác Java bình thường và có thể khiến việc đóng lặp lại nếu không kiểm soát.
2. **Annotation nằm trên method của bean**: `@PreDestroy` chỉ có tác dụng nếu đối tượng đi qua hạ tầng quản lý bean và destruction-aware post-processors phù hợp.
3. **Không gắn vào static utility method** rồi kỳ vọng Spring quản lý vòng đời class.
4. **Không ép callback phụ thuộc bean đã bị hủy**: nếu bean sử dụng tài nguyên từ bean khác, nên khai báo quan hệ phụ thuộc đúng để container xử lý thứ tự giữa các bean.
5. **Không dùng để chạy công việc kéo dài**: shutdown có thể bị giới hạn thời gian bởi container, hệ điều hành hoặc orchestrator. Dọn dẹp nên nhanh, an toàn khi gọi lại và có giới hạn thời gian.

`@PreDestroy` cũng có thể sử dụng trên bean được tạo qua `@Bean`, không chỉ trên `@Component`. Trong ví dụ tổng hợp, `CleanupProbe` không có `@Component` nhưng vẫn nhận callback vì instance được khai báo bằng `@Bean` và thuộc phạm vi quản lý của context.

### Khi nào @PreDestroy không được gọi?

- Đối tượng được tạo bằng `new` và **không đăng ký thành bean Spring**.
- Bean thuộc `prototype` mà container không tự theo dõi giai đoạn hủy.
- Tiến trình bị kết thúc đột ngột, ví dụ `kill -9` trên Unix/Linux, sự cố cấp nguồn, hoặc bị hủy không chạy shutdown hook.
- Context chưa từng tạo bean do lazy initialization, nên không có instance tương ứng để hủy.
- Hạ tầng annotation/post-processor bị tùy chỉnh hoặc thiếu trong cấu hình container đặc biệt.
- Mã đã thoát hoặc dừng bằng một cách bỏ qua lifecycle chuẩn.

Vì vậy câu “Spring luôn gọi `@PreDestroy`” cần được đặt trong điều kiện **bean thực sự được quản lý và container thực hiện destruction**.

## 6. DisposableBean.destroy(): hợp đồng riêng của Spring

Interface:

```java
package org.springframework.beans.factory;

public interface DisposableBean {
    void destroy() throws Exception;
}
```

Đây là phiên bản **rút gọn để giải thích hợp đồng**, không phải file cần tạo trong dự án. Khi một bean triển khai interface này, container có đường gọi rõ ràng mà không cần tìm tên callback từ annotation.

Ví dụ:

```java
public final class WorkerPool implements DisposableBean {

    private boolean closed;

    @Override
    public void destroy() {
        if (closed) {
            return;
        }
        closed = true;
        System.out.println("WorkerPool stopped");
    }
}
```

Đoạn này giả định `WorkerPool` được đăng ký thành bean; cần import `DisposableBean`. Cờ `closed` chỉ minh họa xử lý lặp lại ở môi trường đơn luồng. Với mã đa luồng thực tế, cần đồng bộ hóa phù hợp hoặc dùng thành phần quản lý tài nguyên có tính chất idempotent.

Ưu điểm của `DisposableBean` là dấu hiệu lifecycle nằm ngay ở interface: khi đọc tên lớp, biết nó tham gia destruction contract. Nhược điểm là một đối tượng thư viện/nghiệp vụ bị phụ thuộc vào Spring Framework, làm việc sử dụng lại ngoài Spring phức tạp hơn.

Nếu một bean vừa có `@PreDestroy` vừa triển khai `DisposableBean`, **phương thức `@PreDestroy` được gọi trước `destroy()`** trong dòng xử lý chuẩn. Nếu nó còn được cấu hình custom destroy method khác, phương thức custom đó chạy sau.

Không nên trộn vai trò: `DisposableBean.destroy()` là callback khi Spring hủy bean, không phải API để người gọi ra lệnh “tắt cả ứng dụng”. Gọi nó thủ công không tự khiến Spring đóng context, cập nhật bean registry, thực hiện các hủy bean phụ thuộc khác hay dừng web server.

## 7. destroyMethod: khai báo qua metadata của @Bean

`@Bean` cho phép chỉ định tên phương thức dọn dẹp trực tiếp tại nơi tạo bean:

```java
@Configuration
class ResourceConfiguration {

    @Bean(destroyMethod = "release")
    ResourceHolder resourceHolder() {
        return new ResourceHolder();
    }
}

class ResourceHolder {

    public void release() {
        System.out.println("Resource released");
    }
}
```

Đoạn trên cần import `org.springframework.context.annotation.Bean` và `Configuration`, với các class được đặt trong package hợp lệ. Cách này có thể làm việc với thư viện không phụ thuộc Spring.

Có một chi tiết quan trọng về tên gọi: **`destroyMethod` không nhất thiết phải là `destroy()`**. Nó có thể là `release`, `close`, `shutdown` hoặc method khác phù hợp. Thuộc tính `destroyMethod` của `@Bean` chỉ định chính xác tên callback mà Spring cần gọi theo cấu hình bean definition.

Nếu muốn dùng XML thay vì Java config, Spring cũng hỗ trợ `destroy-method="..."` trong bean definition XML. Cơ chế nằm ở **metadata bean**, nên hạ tầng destruction sẽ áp dụng nguyên tắc tương tự.

### Suy luận close/shutdown của @Bean

Trong Spring Framework, `@Bean` mặc định hỗ trợ **suy luận** phương thức hủy `close()` hoặc `shutdown()` khi bean phù hợp. Vì vậy:

```java
@Bean
ExternalClient client() {
    return new ExternalClient();
}
```

Nếu `ExternalClient` là một kiểu có public `close()` hoặc `shutdown()` phù hợp, Spring có thể tự đăng ký callback dọn dẹp mà không cần khai báo thủ công `destroyMethod`. Đây là ví dụ logic mang tính minh họa, cần định nghĩa hoặc thư viện có `ExternalClient`.

Nếu muốn vô hiệu riêng **suy luận destroy method từ `@Bean`**, dùng:

```java
@Bean(destroyMethod = "")
ExternalClient externallyManagedClient() {
    return new ExternalClient();
}
```

Cấu hình này **không biến bean thành unmanaged object** và không phải cách tắt `@PreDestroy`/`DisposableBean.destroy()` đã khai báo. Nó chỉ bỏ phần tự suy luận destroy method theo cơ chế của `@Bean`.

### Vì sao đôi khi close không được gọi?

Cần xác định:

- Bean có được khai báo bằng `@Bean` hoặc bean definition với destroy method tương ứng không?
- Method `close()`/`shutdown()` có thực sự phù hợp với quy tắc suy luận không?
- Lớp hoặc interface trả về của `@Bean` có làm mất thông tin type mà các cơ chế dự đoán cần không?
- `destroyMethod = ""` có được thiết lập ở đâu không?
- Bean có thuộc scope được container tự hủy không?
- Có ai đã tự đóng resource trước khi Spring gọi callback hay chưa?

Hãy kiểm tra lifecycle thực tế thay vì mặc định suy luận luôn hoạt động trong mọi kết hợp interface và runtime type.

## 8. Khi cùng một phương thức tham gia nhiều cơ chế

Để phân tích **thứ tự** rõ ràng, ba callback trong ví dụ ở mục 3 dùng ba tên khác nhau. Nhưng thực tế có người cấu hình:

```java
@Bean(destroyMethod = "destroy")
MyDisposableBean myBean() {
    return new MyDisposableBean();
}
```

trong khi `MyDisposableBean` đã triển khai `DisposableBean` với phương thức `destroy()`.

Spring Framework có logic tránh việc một phương thức được hủy hai lần chỉ vì cùng được nhận diện thông qua nhiều cơ chế. Vì vậy không nên khẳng định “ba cơ chế được khai báo thì chắc chắn có ba lần gọi” nếu chúng đều trỏ về cùng một phương thức.

Tương tự, `AutoCloseable.close()` có thể được lựa chọn làm custom destroy callback qua suy luận hoặc cấu hình. Điều quan trọng là biết ai sở hữu tài nguyên và liệu phương thức đóng đã được đăng ký và gọi hay chưa, chứ không cố tạo các callback trùng nhau.

**Nguyên tắc triển khai:** chỉ có một phương thức thật sự chịu trách nhiệm giải phóng một tài nguyên, hoặc các callback phải phân vai rõ ràng. Nếu `@PreDestroy` và `destroy()` đều đóng cùng connection, nguy cơ đóng hai lần có thể khiến log lỗi hoặc khiến việc dọn dẹp khó hiểu. Dùng callback có thể gọi lại an toàn (idempotent) khi thích hợp, nhưng không dựa vào idempotence để che một thiết kế lifecycle trùng lặp.

## 9. Thời điểm Spring thực hiện destruction khi đóng context

Trong một `ApplicationContext` chuẩn, việc đóng thường đi theo các giai đoạn lớn:

```text
ApplicationContext.close()
    |
    +-- Phát ContextClosedEvent
    |
    +-- Yêu cầu LifecycleProcessor ngừng các Lifecycle/SmartLifecycle beans
    |
    +-- Hủy các singleton được container quản lý
    |     |
    |     +-- chọn bean cần hủy, xét phụ thuộc
    |     |
    |     +-- @PreDestroy
    |     +-- DisposableBean.destroy()
    |     +-- custom destroyMethod
    |
    +-- Đóng hạ tầng BeanFactory / kết thúc context
```

Đây là **sơ đồ rút gọn**; các context cụ thể có hook riêng, và Spring Boot web app có thêm quy trình dừng web server. Những bước chính cần hiểu là:

- **`ContextClosedEvent`** được phát để thông báo context đang đóng. Đây là event của context, không phải callback hủy một bean cụ thể.
- **`Lifecycle` / `SmartLifecycle`** có bước `stop`, thường diễn ra trước các destructor của singleton. Điều này hữu ích với worker chạy nền cần được ngừng nhận việc trước khi các dependency bị đóng.
- **Destruction callbacks** thực hiện việc giải phóng tài nguyên thuộc bean.
- Sau khi bean bị hủy, không nên tiếp tục gọi business method của nó như một bean đang hoạt động.

Vì vậy `@PreDestroy` có thể chạy **sau** khi bean nhận `SmartLifecycle.stop()`, nếu class triển khai cả hai. `stop` và `destroy` là hai cơ chế khác nhau, có thể phối hợp để ngừng luồng xử lý rồi giải phóng tài nguyên.

### SmartLifecycle và shutdown có kiểm soát

Một thành phần nhận request hoặc chạy tác vụ dài có thể cần:

1. Ở `SmartLifecycle.stop(...)`: dừng nhận công việc mới, chờ công việc đang chạy hoàn tất trong giới hạn hợp lý.
2. Ở destructor: đóng pool, giải phóng file, hủy subscription và hoàn tất cleanup.

Trong Spring Boot web app, graceful shutdown được tổ chức thông qua hạ tầng lifecycle/web server thích hợp. Đừng kỳ vọng đặt một `@PreDestroy` ngủ nhiều giây là cách đúng để chờ mọi HTTP request hoàn thành.

## 10. Thứ tự callback trong một bean khác thứ tự hủy nhiều bean

Giả sử bean `InvoiceProcessor` phụ thuộc bean `DatabaseClient`:

```text
InvoiceProcessor ---> DatabaseClient
      (dùng)           (cung cấp kết nối)
```

Khi đóng context, Spring phải tránh hủy tài nguyên của `DatabaseClient` khi `InvoiceProcessor` còn cần thực hiện callback dọn dẹp của chính nó. Với quan hệ phụ thuộc được container biết, **bean phụ thuộc thường bị hủy trước bean mà nó phụ thuộc vào**.

Ví dụ đầy đủ dạng component:

```java
package demo.lifecycle;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
class DatabaseClient {

    void execute(String sql) {
        System.out.println("Executing: " + sql);
    }

    @PreDestroy
    void closeDatabase() {
        System.out.println("DatabaseClient closed");
    }
}

@Component
class InvoiceProcessor {

    private final DatabaseClient databaseClient;

    InvoiceProcessor(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    @PreDestroy
    void stopProcessor() {
        System.out.println("InvoiceProcessor stopped");
    }
}
```

Đây là **hai class package-private trong cùng package**, có thể lưu trong file Java phù hợp thuộc một project Spring Boot quét package `demo.lifecycle`. Phương thức `execute` chỉ minh họa dependency; không cần gọi nó khi đóng.

Với hai bean singleton được đăng ký và tạo thành công, khi context đóng bình thường, thứ tự hai dòng từ destructor thường là:

```text
InvoiceProcessor stopped
DatabaseClient closed
```

**Không kết luận** Spring gọi `@PreDestroy` của mọi bean theo thứ tự tên alphabet hoặc theo dòng code. Quan hệ phụ thuộc đóng vai trò quan trọng.

Khi có nhiều bean độc lập, thứ tự destructor của chúng **không phải một hợp đồng ứng dụng nên phụ thuộc**. Nếu callback của bean A cần bean B còn hoạt động, hãy khai báo dependency thực sự qua constructor injection hoặc thông tin phụ thuộc như `@DependsOn` khi cần. Không dùng cách đặt tên bean để “ép” thứ tự hủy.

`@DependsOn` không chỉ ảnh hưởng thứ tự khởi tạo. Quan hệ được container ghi nhận còn có ý nghĩa cho thứ tự hủy: **bean phụ thuộc được hủy trước dependency**. Tuy nhiên nó không thay thế giải pháp quản lý concurrency và shutdown logic cho các nguồn lực phức tạp.

### Hình dung hai trục thứ tự

```text
Giữa các bean:
  Processor bị hủy
      trước
  DatabaseClient bị hủy

Trong riêng Processor:
  @PreDestroy
      trước
  DisposableBean.destroy()
      trước
  configured destroyMethod

Trong riêng DatabaseClient:
  @PreDestroy
      trước
  DisposableBean.destroy() (nếu có)
      trước
  configured destroyMethod (nếu có)
```

Đây là cách phân biệt đúng hai câu hỏi thường bị nhập làm một.

## 11. Scope quyết định callback nào được Spring chủ động gọi

Không phải mọi bean được tạo ra đều được Spring theo dõi và hủy theo cách giống nhau.

| Scope / đối tượng | Hành vi dọn dẹp cần hiểu |
| --- | --- |
| `singleton` chuẩn | Spring đăng ký callback hủy cho bean phù hợp và gọi khi context/factory đóng |
| `prototype` | Container tạo và cấu hình instance, nhưng **không tự quản lý việc hủy từng instance**; phía sử dụng chịu trách nhiệm cleanup |
| `request` / `session` trong web app | Destruction callback có thể chạy khi scope tương ứng kết thúc, phụ thuộc cơ chế scope thực tế |
| Custom scope | Phụ thuộc việc scope có hỗ trợ và kích hoạt destruction callbacks không |
| Đối tượng tạo thủ công bằng `new` | Không nhận callback của Spring nếu không được quản lý/đăng ký đúng cách |
| Bean lazy chưa từng khởi tạo | Không có instance để gọi destructor |
| Singleton được tạo nhưng context khởi động lỗi | Spring có thể dọn những singleton đã tạo theo đường hủy khi refresh thất bại; không nên dựa vào việc mọi bean đều đã tồn tại |

### Prototype: bẫy dễ gây rò rỉ tài nguyên

Ví dụ:

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
class TemporaryBuffer {

    @PreDestroy
    public void cleanup() {
        System.out.println("Prototype buffer destroyed");
    }
}
```

Đoạn này cần import `Component`, `Scope`, `ConfigurableBeanFactory` và `PreDestroy`. Khi lấy nhiều instance prototype, việc gọi `context.close()` **không mặc nhiên gọi** `cleanup()` cho từng instance mà Spring đã cấp. Nếu prototype giữ file handle hay connection, code nhận instance phải tổ chức việc giải phóng.

Có thể dùng `AutoCloseable`, `try-with-resources` hoặc một abstraction quản lý tài nguyên rõ ràng cho loại đối tượng ngắn hạn đó. Không cần đổi prototype thành singleton chỉ để lấy destructor; phải thiết kế scope dựa trên thời gian sống thật của tài nguyên.

### Singleton có đảm bảo một lần gọi không?

Với shutdown chuẩn, bean singleton được container hủy theo cơ chế quản lý đăng ký. Nhưng việc gọi trực tiếp một method hủy từ nghiệp vụ, restart context theo custom code hoặc các lần tạo context mới có thể khiến cùng logic được gọi thêm ở những đối tượng/lượt chạy khác. Thiết kế dọn dẹp cần tránh phụ thuộc vào giả định “JVM chỉ có duy nhất một bean và duy nhất một lần dừng”.

## 12. Vì sao @PreDestroy không chạy khi tắt ứng dụng?

Nhiều lỗi không nằm ở thứ tự mà ở **việc chưa có sự kiện destruction**.

Những trường hợp cần kiểm tra:

- Ứng dụng chỉ bị dừng bằng cách giết tiến trình không cho JVM chạy shutdown hook, ví dụ `SIGKILL`/`kill -9`.
- Lớp được tạo bằng `new` trong service, không phải bean do Spring quản lý.
- Bean là `prototype` hoặc thuộc custom scope không phát destruction callback.
- Class không được component-scanned, hoặc `@Bean` khai báo không được nạp.
- Dự án Spring Boot 3 nhập nhầm `javax.annotation.PreDestroy` thay vì `jakarta.annotation.PreDestroy`.
- Callback được đặt ở một method không hợp lệ hoặc không được hạ tầng annotation xử lý.
- Context chưa từng được đóng theo đường vận hành đang được kiểm thử; app vẫn còn running.
- Bean lazy chưa có instance vì không bao giờ được yêu cầu.
- Test và runtime khác nhau: test context có thể được cache hoặc đóng ở thời điểm khác mong đợi.

**Kiểm tra tối thiểu:**

```java
ConfigurableApplicationContext context =
        SpringApplication.run(DestroyOrderApplication.class, args);

// Thao tác quan sát ...
context.close();
```

Đây là code minh họa bên trong một phương thức đã có import cần thiết. Với ứng dụng chỉ dùng để thử callback, gọi `close()` rõ ràng giúp phân biệt lỗi wiring với việc chưa tới giai đoạn shutdown.

Trong ứng dụng web sản xuất, không nên gọi `context.close()` từ một endpoint chỉ để kiểm thử destructor. Việc đó làm ngừng toàn bộ ứng dụng và ảnh hưởng request hiện hành.

## 13. Sự khác biệt giữa close(), stop(), ContextClosedEvent và các destructor

| API / sự kiện | Đối tượng áp dụng | Ý nghĩa |
| --- | --- | --- |
| `ConfigurableApplicationContext.close()` | Context | Bắt đầu quy trình đóng và giải phóng hạ tầng |
| `ContextClosedEvent` | Event context | Thông báo context đang đóng; listener có thể phản ứng |
| `Lifecycle.stop()` | Bean hỗ trợ lifecycle | Dừng tác vụ/chế độ chạy mà bean đang quản lý |
| `SmartLifecycle.stop(Runnable callback)` | Bean hỗ trợ async stop contract | Báo hoàn tất stop phase để processor tiếp tục |
| `@PreDestroy` | Bean có annotation hợp lệ | Hook dọn dẹp trước khi hủy bean |
| `DisposableBean.destroy()` | Bean triển khai interface | Hook hủy theo hợp đồng của Spring |
| `@Bean(destroyMethod = "x")` | Bean có metadata tương ứng | Gọi method dọn dẹp được cấu hình |
| `Runtime.getRuntime().addShutdownHook(...)` | JVM | Đăng ký hành động khi JVM shutdown theo quy tắc JVM |

Đừng nhầm **`stop()` của context** với **`close()`**. `stop()` chuyển thông báo lifecycle tới các bean thích hợp; nó không tự động thực hiện toàn bộ bean destruction như `close()`. Tương tự, `ContextClosedEvent` là event được phát trên đường đóng; nó không phải một trong ba callback hủy của bean trong đề bài.

Với Spring Boot, shutdown hook được framework đăng ký theo cấu hình mặc định giúp đóng context khi JVM kết thúc bình thường. Tuy vậy:

- Shutdown hook không hoạt động nếu JVM bị dừng không cho thực thi hook.
- Orchestrator như Kubernetes có giới hạn thời gian shutdown của container; callback quá lâu có thể bị cắt.
- Thứ tự giữa các shutdown hook độc lập của JVM không nên được dùng làm hợp đồng thứ tự dọn dẹp nghiệp vụ.

Chọn điểm dọn dẹp **thuộc Spring lifecycle** khi tài nguyên do Spring quản lý. Chọn cơ chế JVM hook riêng chỉ khi thật sự có nhu cầu nằm ngoài vòng đời của context.

## 14. Ngoại lệ trong callback hủy và nguyên tắc an toàn

Destructor nên thực hiện cleanup theo hướng **best effort**, đồng thời giữ thông tin chẩn đoán nếu thất bại. Khác với xử lý một request, khi context đóng thì trạng thái của hệ thống đang thay đổi; cố dùng lại các bean khác hoặc thực hiện retry không giới hạn có thể làm shutdown khó kiểm soát.

Một thiết kế thường phù hợp:

```java
public final class FileWriterHolder implements AutoCloseable {

    private boolean closed;

    @Override
    public void close() {
        if (closed) {
            return;
        }
        closed = true;
        // Đóng writer thực tế tại đây trong ứng dụng có tài nguyên tương ứng.
    }
}
```

Đoạn này chỉ minh họa idempotence; trong hệ thống đa luồng cần xử lý concurrency, lỗi I/O và tài nguyên thật một cách thích hợp. Khi là bean từ `@Bean` và không tắt destroy inference, `close()` phù hợp có thể được Spring đăng ký gọi lúc hủy.

Những điều cần tránh trong destructor:

1. Ném exception mới và làm mất thông tin lỗi nguyên nhân ban đầu.
2. Chờ vô hạn một HTTP call hoặc connection pool đóng; cần giới hạn thời gian.
3. Gọi business operation giả định mọi bean khác vẫn còn hoạt động.
4. Bắt đầu thêm luồng background hoặc job mới khi container đã ngừng tiếp nhận công việc.
5. In credential, token hoặc nội dung dữ liệu nhạy cảm vào log shutdown.
6. Thực hiện một transaction nghiệp vụ phức tạp cần bảo đảm commit thành công sau khi hệ thống đã bắt đầu đóng.

Spring có xử lý lỗi ở các giai đoạn destruction và có thể tiếp tục dọn các bean khác, nhưng **không nên dựa vào một cơ chế nuốt lỗi để bảo đảm shutdown vẫn sạch**. Hãy ghi nhận lỗi và đặt cleanup ở đúng tầng sở hữu tài nguyên.

### Phân vai ba callback nếu buộc phải dùng cả ba

Nếu một framework tích hợp bắt buộc bean dùng đủ ba cơ chế, có thể phân vai rõ:

- `@PreDestroy`: đánh dấu ngừng nhận việc mới và phát tín hiệu dừng nhẹ.
- `DisposableBean.destroy()`: đóng executor/pool do bean sở hữu.
- `destroyMethod`: phát hành hoặc thu dọn tài nguyên cuối cùng vốn do thư viện bên ngoài cung cấp.

Đây chỉ là **một mô hình thiết kế minh họa**. Khi các bước có dependency phức tạp, thường tốt hơn là gom cleanup vào một phương thức duy nhất, do một callback kích hoạt, để tránh logic phân tán và xử lý lỗi khó.

## 15. Ngược với thứ tự khởi tạo: @PostConstruct và initMethod

Thứ tự hủy có một đối xứng dễ nhớ với thứ tự khởi tạo chuẩn khi một bean cấu hình nhiều cơ chế:

| Giai đoạn | Thứ tự callback trong cùng một bean |
| --- | --- |
| **Khởi tạo** | `@PostConstruct` → `InitializingBean.afterPropertiesSet()` → custom `initMethod` |
| **Hủy** | `@PreDestroy` → `DisposableBean.destroy()` → custom `destroyMethod` |

Khác biệt là mục đích: khi khởi tạo, bean đang được chuẩn bị để dùng; khi hủy, tài nguyên phải được giải phóng. Không suy diễn rằng toàn bộ container khởi tạo bean A rồi B thì luôn hủy theo đúng B rồi A nếu không có quan hệ phụ thuộc/ordering được framework quản lý.

Trong dự án thực tế, thường chỉ cần **một** cơ chế khởi tạo và **một** cơ chế dọn dẹp phù hợp cho từng loại bean. Bảng đối xứng giúp giải thích cách Spring kết hợp callback khi cùng một bean dùng nhiều cơ chế; nó không khuyến khích luôn khai báo đủ ba.

## 16. Thực hành kiểm chứng và bài tập

### Bài 1: tự chạy mô hình ba callback

Chạy chương trình `DestroyOrderApplication` ở mục 3. Đọc kết quả và trả lời:

1. Vì sao `app.running` xuất hiện trước cả ba destructor?
2. Vì sao `@PreDestroy` chạy trước `DisposableBean.destroy()`?
3. Vì sao `customCleanup()` chạy ở vị trí thứ ba?
4. Nếu bỏ `@Bean(destroyMethod = "customCleanup")` nhưng vẫn giữ hai callback kia, còn những dòng nào?
5. Nếu đổi scope sang prototype, kết quả có giống không? Vì sao Spring không tự hủy từng instance prototype?

Đáp án kỳ vọng cho ba bước đầu là: **context đóng ở cuối `try`, hạ tầng destruction gọi annotation callback trước, interface callback sau, và custom destroy metadata cuối cùng**.

### Bài 2: chỉ sử dụng một callback

Thử ba biến thể độc lập:

- Bỏ `implements DisposableBean` và bỏ custom destroy metadata, chỉ giữ `@PreDestroy`.
- Bỏ `@PreDestroy` và custom destroy metadata, chỉ giữ `DisposableBean`.
- Bỏ `@PreDestroy` và `DisposableBean`, giữ `@Bean(destroyMethod = "customCleanup")`.

Mỗi biến thể được kỳ vọng chỉ còn **một** dòng dọn dẹp của `CleanupProbe` sau `app.running`. Đây là cách tách lỗi đăng ký callback khi có nhiều phương thức.

### Bài 3: inferred close()

Tạo một class có public `close()` nhưng không cần Spring API:

```java
public final class ClientHolder implements AutoCloseable {

    @Override
    public void close() {
        System.out.println("ClientHolder.close()");
    }
}
```

Đăng ký bằng `@Bean` rồi đóng context; quan sát liệu Spring gọi `close()` theo cơ chế inference. Sau đó thử `@Bean(destroyMethod = "")` và đối chiếu. Lưu ý cần giữ toàn bộ ví dụ trong dự án Spring hợp lệ và không gọi `close()` thủ công trong các bước đang đo.

### Bài 4: quan hệ phụ thuộc

Tạo hai bean `Consumer` và `Provider`, trong đó `Consumer` inject `Provider`. Mỗi bean có một `@PreDestroy` in tên riêng. Dự đoán thứ tự destruction rồi đóng context.

Đề bài này kiểm tra khả năng phân biệt **thứ tự hủy nhiều bean** với **thứ tự callback trong một bean**. Kết quả mong đợi là bean phụ thuộc `Consumer` được dọn trước `Provider` khi quan hệ phụ thuộc được container biết.

### Bài 5: kiểm thử không làm dừng toàn bộ ứng dụng

Trong test có thể tạo một `AnnotationConfigApplicationContext` độc lập, đăng ký cấu hình chỉ chứa bean cần thử, gọi `refresh()` và `close()` trong phạm vi test. Điều này phù hợp hơn việc đóng application context đang dùng chung giữa các test.

Ví dụ ý tưởng:

```java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext()) {
    context.register(TestConfig.class);
    context.refresh();
    // Quan sát trạng thái trước shutdown.
}
// Kiểm tra callback sau khi context đóng.
```

Đoạn trên cần import `AnnotationConfigApplicationContext` và một class `TestConfig` được khai báo riêng; đây là **mẫu đặt trong một bài test**, không phải một chương trình đầy đủ độc lập. Nên ghi nhận thứ tự vào một `List<String>` do test kiểm soát, rồi so sánh chính xác nội dung list, thay vì cố parse toàn bộ console log.

## 17. Tổng hợp các lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không có dòng `@PreDestroy` | Bean không do Spring quản lý, sai namespace annotation hoặc context chưa đóng | Kiểm tra `@Bean`/scan, `jakarta.annotation.PreDestroy`, vòng đời đóng |
| `DisposableBean.destroy()` không chạy | Lớp chưa implement interface đúng, bean không được đăng ký hoặc scope không được container hủy | Kiểm tra import, bean registration và scope |
| Custom destroy method không chạy | Chưa cấu hình `destroyMethod`, sai tên method hoặc suy luận không áp dụng | Kiểm tra bean definition và public method phù hợp |
| Cả ba có khai báo nhưng chỉ thấy hai dòng | Nhiều cơ chế có thể trỏ cùng một method hoặc một callback không đăng ký | Tách tên callback khi kiểm tra và đọc metadata |
| Destructor chạy hai lần theo log | Cleanup được gọi thủ công và bởi container, hoặc có nhiều instance/context | Xác định ownership; tránh gọi callback thủ công |
| `@PreDestroy` không chạy khi `kill -9` | JVM không được chạy shutdown hook | Dùng tín hiệu dừng bình thường, đặt deadline shutdown và thiết kế recovery |
| Prototype leak resource | Container không tự hủy từng prototype | Để bên sử dụng chịu trách nhiệm đóng instance |
| Destructor của bean A dùng bean B đã đóng | Quan hệ phụ thuộc không được container ghi nhận hoặc thiết kế sai | Khai báo dependency và phân tầng cleanup |
| Cần dừng tác vụ trước khi đóng pool | Chỉ có destructor quá muộn để phối hợp stop phase | Dùng `Lifecycle`/`SmartLifecycle` phù hợp |
| Thử nghiệm trong `@SpringBootTest` lúc nào cũng không gọi callback | Test context được cache, chưa đến lúc teardown | Dùng context riêng hoặc cơ chế test quản lý lifecycle phù hợp |
| Tài nguyên đóng ở môi trường test nhưng không đóng production | Khác cách dừng app, shutdown hook, scope hoặc exception | Kiểm tra runtime shutdown path và log thật |
| Lỗi trong callback làm mất phần cleanup tiếp theo | Callback ném lỗi hoặc chờ vô hạn | Thiết kế cleanup nhỏ, có giới hạn và ghi log đúng chỗ |

Quy trình chẩn đoán nên bắt đầu từ **có hủy bean hay chưa**; tiếp đó mới kiểm tra **callback nào đã đăng ký**; cuối cùng mới phân tích **thứ tự thực thi**. Cách này giúp tránh nhầm vấn đề scope với sai thứ tự framework.

## 18. Những quy tắc cần ghi nhớ

- Với **một bean singleton được container hủy bình thường** và ba callback **khác tên**, thứ tự cơ bản là: **`@PreDestroy` → `DisposableBean.destroy()` → custom `destroyMethod`**.
- `@PreDestroy` của Spring Boot 3.x nhập từ `jakarta.annotation.PreDestroy`.
- `DisposableBean` là interface của Spring; `@Bean(destroyMethod = "...")` khai báo phương thức từ bean definition, phù hợp cả lớp bên thứ ba.
- `@Bean` có cơ chế suy luận `close`/`shutdown`. `@Bean(destroyMethod = "")` chỉ vô hiệu phần suy luận destroy method, không tự tắt các lifecycle callback khác.
- Đừng đánh đồng thứ tự callback **trong một bean** với thứ tự hủy **giữa các bean**. Quan hệ dependency giúp Spring hủy dependent trước dependency.
- `prototype` không mặc nhiên được Spring theo dõi để hủy; object do `new` ở ngoài container cũng không tự nhận các callback Spring.
- `ContextClosedEvent`, `SmartLifecycle.stop()` và `ApplicationContext.close()` là các phần **khác nhau** của quá trình shutdown.
- Với tài nguyên do bean sở hữu, chỉ chọn các callback cần thiết, tránh đóng trùng và không chặn shutdown quá lâu.

### Tài liệu tham khảo

- [Spring Framework — Customizing the Nature of a Bean / Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): interface `DisposableBean`, chú thích `@PreDestroy`, các callback khởi tạo/hủy và tích hợp lifecycle.
- [Spring Framework — Using the @Bean Annotation / Receiving Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): `destroyMethod`, gọi `DisposableBean` và suy luận `close`/`shutdown`.
- [Spring Framework 6.1 — Bean factory lifecycle](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/beans/factory/DisposableBean.html): hợp đồng `DisposableBean.destroy()`.
- [Spring Framework 6.1 — Context close](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html): đóng context và quản lý lifecycle.
