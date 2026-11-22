# Chạy nhiều context trong một JVM và trách nhiệm đóng từng context

Một tiến trình Java có thể chứa **nhiều Spring `ApplicationContext` cùng lúc**. Mỗi context quản lý một tập định nghĩa bean, bean instance và vòng đời riêng; tất cả vẫn chạy trong **cùng một JVM**. Khả năng này hữu ích khi cần chạy hai phần ứng dụng độc lập, thử nghiệm nhiều cấu hình trong một tiến trình, hoặc xây dựng quan hệ parent–child giữa các context. Tuy nhiên, tạo được nhiều context không có nghĩa Spring tự quản lý việc tắt từng phần giúp ứng dụng: **context nào được tạo thì phải có chủ thể chịu trách nhiệm đóng context đó đúng thời điểm**.

Trong bài này, “context” là **Spring `ApplicationContext`**, không phải HTTP servlet context, `SecurityContext` hay các khái niệm context khác.

## 1. Một JVM, nhiều container Spring

Hình dung hai context độc lập trong cùng tiến trình:

```text
JVM / một process Java
|
+-- ApplicationContext A
|   +-- BeanFactory, bean definitions của A
|   +-- Singleton A, lifecycle callbacks của A
|   +-- Tài nguyên do A quản lý
|
+-- ApplicationContext B
    +-- BeanFactory, bean definitions của B
    +-- Singleton B, lifecycle callbacks của B
    +-- Tài nguyên do B quản lý

Cả hai vẫn dùng chung JVM, classloader (thường là vậy),
các static field, system properties và tài nguyên cấp process.
```

Điều này tạo ra hai lớp phạm vi khác nhau:

- **Trong phạm vi một context**, `@Scope("singleton")` (mặc định đối với bean thông thường) nghĩa là một bean instance cho mỗi Spring container sở hữu bean đó. Cùng một bean definition có thể tạo ra **hai instance khác nhau** trong hai context độc lập.
- **Trong phạm vi JVM**, các `static` field, class được nạp bởi classloader chung, system properties và một số thư viện/registry toàn cục có thể được hai context cùng nhìn thấy. Spring không tự nhân đôi hoặc tự đặt lại các trạng thái này chỉ vì bạn tạo thêm context.

Ví dụ, hai context có thể đều định nghĩa bean tên `paymentService` mà không xung đột vì chúng nằm trong hai registry độc lập. Nhưng nếu cả hai bean trỏ đến cùng một `static` cache, thì cập nhật cache ở context A vẫn có thể ảnh hưởng context B.

Đừng nhầm **nhiều context** với **nhiều JVM**. Các context trong một JVM vẫn chia sẻ bộ nhớ và số phận của tiến trình: gọi `System.exit(...)` sẽ tác động cả process, không chỉ một context.

## 2. Ví dụ chạy được: hai context độc lập

Ví dụ dưới đây dành cho **Java 17+ và Spring Boot 3.x**, với dependency `spring-boot-starter`. Ta cố ý sử dụng `WebApplicationType.NONE` để tập trung vào vòng đời Spring, tránh khởi tạo web server và tranh chấp cổng HTTP.

Tạo tệp `src/main/java/com/example/multicontext/TwoContextsDemo.java`:

```java
package com.example.multicontext;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class TwoContextsDemo {

    private TwoContextsDemo() {
    }

    public static void main(String[] args) {
        ConfigurableApplicationContext first = open(args);

        try {
            ConfigurableApplicationContext second = open(args);

            try {
                ManagedResource bean1 =
                        first.getBean(ManagedResource.class);
                ManagedResource bean2 =
                        second.getBean(ManagedResource.class);

                System.out.println("Cùng bean? " + (bean1 == bean2));
                System.out.println(
                        "IDs: " + bean1.id() + ", " + bean2.id());

                // Chỉ đóng context thứ nhất.
                first.close();

                System.out.println(
                        "Context 1 active: " + first.isActive());
                System.out.println(
                        "Context 2 active: " + second.isActive());
                System.out.println(
                        "Context 2 bean ID: "
                                + second.getBean(ManagedResource.class).id());
            } finally {
                // Dù đoạn xử lý trên ném lỗi, vẫn đóng context 2.
                second.close();
            }
        } finally {
            // Nếu tạo context 2 thất bại, context 1 vẫn được đóng.
            if (first.isActive()) {
                first.close();
            }
        }
    }

    private static ConfigurableApplicationContext open(String[] args) {
        return new SpringApplicationBuilder(DemoConfiguration.class)
                .web(WebApplicationType.NONE)
                .run(args);
    }

    @Configuration(proxyBeanMethods = false)
    public static class DemoConfiguration {

        @Bean(destroyMethod = "close")
        ManagedResource resource() {
            return new ManagedResource();
        }
    }

    public static final class ManagedResource implements AutoCloseable {

        private static final AtomicInteger NEXT_ID =
                new AtomicInteger();

        private final int id = NEXT_ID.incrementAndGet();

        int id() {
            return id;
        }

        @Override
        public void close() {
            System.out.println("Đóng resource #" + id);
        }
    }
}
```

Chạy tại thư mục dự án đã cấu hình Spring Boot Gradle plugin, với `TwoContextsDemo` là main class:

```bash
./gradlew bootRun
```

Trên Windows, dùng `.\gradlew.bat bootRun`. Nếu dự án Maven đã cấu hình Spring Boot Maven plugin thì có thể chạy `./mvnw spring-boot:run` với main class phù hợp. Đây là mã ứng dụng Spring Boot; không thể biên dịch độc lập bằng `javac TwoContextsDemo.java` nếu thiếu thư viện Spring trên classpath.

Bỏ qua banner và log của Spring Boot, **các dòng do chính ví dụ in ra**, theo thứ tự, sẽ là:

```text
Cùng bean? false
IDs: 1, 2
Đóng resource #1
Context 1 active: false
Context 2 active: true
Context 2 bean ID: 2
Đóng resource #2
```

Tại sao lại như vậy?

1. `open(args)` lần đầu tạo context A, xử lý `DemoConfiguration` và tạo một `ManagedResource` có ID 1.
2. `open(args)` lần hai tạo **context mới**, xử lý cùng lớp cấu hình nhưng tạo `ManagedResource` khác, có ID 2. Vì thế phép so sánh `bean1 == bean2` cho `false`.
3. `first.close()` đóng context A, kích hoạt destroy callback của bean do A sở hữu, nên in `Đóng resource #1`.
4. Context B vẫn còn hoạt động và vẫn lấy được bean ID 2.
5. Khối `finally` đóng context B, nên in `Đóng resource #2`. Khối `finally` bên ngoài chỉ đóng A nếu A còn active.

Trường `NEXT_ID` là `static`, vì vậy cả hai context nhìn thấy **cùng một bộ đếm cấp JVM**. Bộ đếm dùng `AtomicInteger` để an toàn nếu có nhiều luồng cùng tạo đối tượng. Đây là ví dụ có chủ ý cho thấy bean instance được tách theo context nhưng `static` state không được tách.

Cũng cần chú ý: lớp `DemoConfiguration` chỉ khai báo `@Configuration` và `@Bean`. Nó không cần `@SpringBootApplication` để minh họa việc chạy Spring context qua `SpringApplicationBuilder`. Trong ứng dụng Boot điển hình, lớp gốc có thể dùng `@SpringBootApplication` để kích hoạt thêm component scan và auto-configuration.

## 3. `close()` thực sự đóng những gì?

Đối tượng trả về từ `SpringApplicationBuilder.run(...)` hoặc `SpringApplication.run(...)` là `ConfigurableApplicationContext`. Interface này cho phép đóng context bằng `close()`:

```java
context.close();
```

Trong một lần đóng bình thường, Spring thực hiện quy trình hủy context, bao gồm dừng những lifecycle component thuộc quyền quản lý của container và thực hiện callback hủy cho các singleton bean do context sở hữu. Các cơ chế thường gặp là:

| Cơ chế | Được dùng cho |
|---|---|
| `@PreDestroy` | Phương thức dọn dẹp trên bean được quản lý; Spring Boot 3 dùng annotation từ `jakarta.annotation`. |
| `DisposableBean.destroy()` | Callback hủy do Spring định nghĩa. |
| `@Bean(destroyMethod = "close")` | Gọi phương thức đóng được chỉ định trên object do factory method trả về. |
| Phương thức `close`/`shutdown` được Spring suy luận | Áp dụng khi bean được khai báo phù hợp và không vô hiệu hóa cơ chế suy luận. |
| `SmartLifecycle.stop()` | Dừng thành phần có vòng đời vận hành; thời điểm stop trước hoặc trong giai đoạn hủy tùy cơ chế lifecycle. |

Ở ví dụ mục 2, `@Bean(destroyMethod = "close")` khiến Spring gọi `ManagedResource.close()` khi context tương ứng bị đóng. Bạn không cần tự gọi `bean1.close()` rồi lại gọi `first.close()`; làm vậy có nguy cơ đóng cùng tài nguyên hai lần nếu đối tượng không hỗ trợ đóng lặp.

Một số giới hạn cần hiểu rõ:

- Context chỉ tự quản lý việc hủy đối tượng được đăng ký và có hợp đồng lifecycle phù hợp. **Luồng tự tạo bằng `new Thread(...)`, kết nối mở thủ công ngoài bean, callback lưu trong global registry hoặc tài nguyên tĩnh** không tự biến mất chỉ vì context đóng.
- Spring **không mặc định theo dõi và hủy mọi prototype bean** sau khi chúng đã được tạo và bàn giao cho caller. Nếu prototype sở hữu tài nguyên, caller hoặc cơ chế quản lý bổ sung phải thu hồi chúng.
- Đóng một context không mặc nhiên gọi `close()` lên context độc lập khác. Nhưng nếu hai context cùng sử dụng một object bên ngoài hoặc cùng sở hữu một tài nguyên vật lý, việc đóng một bên **có thể gây ảnh hưởng gián tiếp** đến bên kia.
- Sau khi context đóng, `isActive()` trở thành `false` và không nên tiếp tục lấy bean hoặc gửi công việc vào các bean đã hủy. Tham chiếu Java tới một bean cũ có thể vẫn tồn tại trong bộ nhớ, nhưng không có nghĩa tài nguyên của bean còn dùng được.

Ví dụ, một `ExecutorService` tự tạo nhưng chưa đăng ký thành bean có thể tiếp tục duy trì các luồng sau khi context đóng. Với tài nguyên chạy nền, hãy dùng component do Spring quản lý, khai báo callback dọn dẹp hoặc chủ động gọi `shutdown()`/`close()` tại đúng nơi sở hữu.

## 4. Trách nhiệm đóng từng context thuộc về ai?

Quy tắc thực dụng là: **đoạn code tạo hoặc điều phối một context phải xác định rõ ai có quyền đóng nó**. Điều này tránh cả rò rỉ tài nguyên lẫn việc nhiều chủ thể cùng đóng một resource.

| Loại tài nguyên | Chủ sở hữu hợp lý | Khi đóng context |
|---|---|---|
| Singleton bean được tạo riêng trong A | Context A | A chạy destroy callback của bean đó. |
| Singleton bean được tạo riêng trong B | Context B | A đóng không làm B bị hủy. |
| Bean được khai báo trong parent và child sử dụng | Parent context | Child đóng không phải là lệnh hủy bean của parent. |
| Web server nhúng riêng của một web context | Chính web context đó | Được dừng theo vòng đời context. |
| Shared client hoặc pool tạo **một lần** bên ngoài các context | Chủ sở hữu được chỉ định rõ | Không để cả A và B tự ý hủy cùng object. |
| `static` cache/registry hoặc system property | Cấp process hoặc code sở hữu chúng | Không tự được reset theo vòng đời một context. |
| Đối tượng tạo thủ công ngoài Spring | Code tạo đối tượng | Phải tự thu hồi đúng lúc. |

Một ví dụ nguy hiểm: hai context cùng trỏ đến **một object `DataSource` có thật** và cả hai đều khai báo quyền hủy object đó. Khi A đóng, pool kết nối dùng chung bị đóng; B còn active nhưng truy cập database có thể lỗi. Đây không phải lỗi của `ApplicationContext`: vấn đề là **một tài nguyên có hai chủ sở hữu lifecycle**.

Có hai hướng xử lý phổ biến:

1. Tạo tài nguyên riêng cho từng context nếu cần cách ly hoàn toàn, chấp nhận chi phí bộ nhớ và kết nối.
2. Tạo tài nguyên dùng chung trong parent hoặc một thành phần sở hữu bên ngoài; các child chỉ sử dụng và không tự đóng tài nguyên dùng chung.

Khi chọn dùng chung, đừng chỉ nghĩ đến việc truyền reference: hãy quyết định **ai khởi tạo, ai đóng, khi nào đóng, và điều gì xảy ra nếu một consumer còn đang sử dụng**.

## 5. Đóng đúng cách khi có lỗi trong lúc khởi động

Mẫu quan trọng nhất là bảo đảm context đã tạo được đóng nếu một context khởi động sau đó ném exception. Ví dụ:

```java
ConfigurableApplicationContext a = null;
ConfigurableApplicationContext b = null;

try {
    a = open(args);
    b = open(args);

    // Sử dụng cả a và b.
} finally {
    if (b != null) {
        b.close();
    }
    if (a != null) {
        a.close();
    }
}
```

Đây là **đoạn minh họa đặt trong lớp có phương thức `open(args)`** như ví dụ mục 2, không phải một file Java độc lập. Nó đóng theo thứ tự ngược lúc tạo: B trước, A sau. Việc kiểm tra `null` rất quan trọng nếu `open(args)` thứ hai chưa trả về context hợp lệ.

Với context độc lập và không cần đóng sớm từng bên, có thể dùng `try-with-resources` vì `ConfigurableApplicationContext` hỗ trợ `close()`:

```java
try (ConfigurableApplicationContext a = open(args);
     ConfigurableApplicationContext b = open(args)) {

    // Dùng cả hai context trong phạm vi try.
}
// Java đóng b trước rồi đóng a, kể cả khi thân try ném lỗi.
```

Mẫu này cũng là đoạn mã sử dụng lại `open(args)` ở ví dụ trước.

Điểm khác nhau giữa hai lựa chọn: `try-with-resources` ngắn gọn khi vòng đời hai context trùng nhau; `try/finally` linh hoạt hơn khi phải đóng A trước nhưng vẫn tiếp tục sử dụng B.

Nếu **chính lời gọi `run(...)`** thất bại giữa quá trình tạo một context, Spring Boot có cơ chế xử lý startup failure và dọn dẹp context đang khởi tạo. Dù vậy, điều đó **không giải phóng trách nhiệm đóng các context khác đã khởi động thành công trước đó**.

## 6. Hai context độc lập và quan hệ parent–child khác nhau thế nào?

Không phải mọi cặp context đều có quan hệ giống nhau.

### Hai context độc lập

Ví dụ mục 2 gọi `open(args)` hai lần, tạo A và B không có liên kết parent–child:

```text
JVM
+-- A: BeanFactory A
+-- B: BeanFactory B
```

Thông thường, A không tự nhìn thấy các bean do B đăng ký; B cũng không tự nhìn thấy bean của A. Muốn cộng tác, ứng dụng phải truyền dữ liệu qua một giao diện/channels phù hợp hoặc chủ động thiết kế tài nguyên chung.

### Context phân cấp parent–child

Spring hỗ trợ một context có context cha:

```text
Parent context
  +-- CommonService (bean do Parent sở hữu)
  |
  +-- Child context
        +-- FeatureService (bean do Child sở hữu)
        +-- Có thể tra cứu CommonService từ Parent
```

Trong quan hệ này, child thường có thể tìm thấy bean của parent nếu chính child không có bean phù hợp ghi đè về tên/phạm vi tra cứu. **Parent không tự tra cứu ngược được bean chỉ tồn tại trong child.** Hai context vẫn có vòng đời riêng, nhưng child có thể phụ thuộc trực tiếp vào bean đang được parent quản lý.

Spring Boot cung cấp `SpringApplicationBuilder` để tạo phân cấp. Đoạn sau minh họa việc khởi chạy, với `ParentConfig` và `ChildConfig` là **hai lớp `@Configuration` cần tự định nghĩa cho ứng dụng**:

```java
SpringApplicationBuilder parentBuilder =
        new SpringApplicationBuilder(ParentConfig.class)
                .web(WebApplicationType.NONE);

ConfigurableApplicationContext child = parentBuilder
        .child(ChildConfig.class)
        .web(WebApplicationType.NONE)
        .run(args);

ConfigurableApplicationContext parent =
        (ConfigurableApplicationContext) child.getParent();

try {
    // Các bean của child có thể dùng bean được khai báo ở parent.
} finally {
    try {
        child.close();
    } finally {
        parent.close();
    }
}
```

Việc ép kiểu trên dựa vào trường hợp cụ thể **parent cũng do Spring Boot builder tạo ra** và là `ConfigurableApplicationContext`. Không nên ép kiểu như vậy tùy tiện đối với một `ApplicationContext` bất kỳ.

Điều cần nhớ về vòng đời phân cấp:

- **Đóng child trước, đóng parent sau** là lựa chọn an toàn khi child cần bean thuộc parent để hoạt động hoặc dọn dẹp.
- `child.close()` không phải lệnh `parent.close()`; đừng ngầm coi một lời gọi đóng sẽ tự xử lý toàn bộ cấu trúc tùy ý.
- Việc đóng parent khi child vẫn đang hoạt động có thể khiến child giữ reference đến bean/tài nguyên parent đã bị hủy.
- Nếu nhiều child dùng chung parent, chỉ đóng parent khi các child phụ thuộc đã hoàn tất và được đóng đúng cách.
- Bean cùng tên trong child có thể che bean ở parent khi tra cứu từ child. Hãy tổ chức cấu hình để không vô tình khai báo trùng hoặc đặt kỳ vọng sai về injection.

Ngoài bean visibility, còn có yếu tố **event propagation**: sự kiện được phát từ child có thể được chuyển lên parent, khiến listener ở parent quan sát hoạt động của child. Với các listener cần xử lý **riêng từng context**, hãy kiểm tra nguồn phát sự kiện hoặc thiết kế đăng ký listener phù hợp.

Một chi tiết khác: việc xây dựng hierarchy có thể khiến `Environment` và một số thiết lập của các builder liên quan được truyền/ghép qua quan hệ cha–con. Đừng mặc định mỗi context phân cấp luôn có profile và properties tách biệt hoàn toàn; phải thiết kế và kiểm chứng cấu hình thực tế.

## 7. Nhiều web context: tránh tranh chấp cổng HTTP

Trong ứng dụng console ở mục 2, `WebApplicationType.NONE` giúp hai context không cần web server. Nếu cả A và B đều là **web application context**, mỗi context có thể khởi động máy chủ HTTP nhúng riêng. Khi cả hai cố bind cùng một địa chỉ và cổng, context khởi động sau có thể thất bại vì cổng đã được sử dụng.

Ví dụ, nếu hai ứng dụng Servlet đều muốn nghe trên `localhost:8080`, việc cả hai nằm trong cùng một JVM không làm cổng 8080 tự được chia sẻ.

Khi thực sự cần **hai web server riêng**, phải cấu hình cổng không xung đột, chẳng hạn:

```java
new SpringApplicationBuilder(ApiOneApplication.class)
        .properties("server.port=8081")
        .run(args);

new SpringApplicationBuilder(ApiTwoApplication.class)
        .properties("server.port=8082")
        .run(args);
```

Đây là **mã minh họa**, giả sử `ApiOneApplication` và `ApiTwoApplication` là hai cấu hình Spring Boot web hợp lệ. Thuộc tính truyền qua `properties(...)` là default property và vẫn có thể chịu sự ưu tiên của những nguồn cấu hình khác; cần kiểm tra **cổng hiệu lực** khi ứng dụng chạy.

Trong môi trường test, `server.port=0` có thể yêu cầu server chọn một cổng còn trống. Nhưng nếu muốn kiểm tra nhiều context trong cùng JVM, hãy phân biệt rõ: context được dùng trong test nào, server nào thuộc context nào, và ai gọi `close()`.

Một web context có thể được đóng trong khi web context khác tiếp tục phục vụ request, miễn là chúng không phụ thuộc vào tài nguyên bị dừng. “Context B vẫn active” chỉ nói đến trạng thái context; readiness thật của HTTP endpoint và các dependency bên ngoài cần kiểm tra thêm.

## 8. Tác vụ chạy nền, runner và shutdown hook

Hai context dùng chung một lớp cấu hình không chỉ tạo bean hai lần: chúng còn có thể **thực hiện công việc khởi động hai lần**.

Chẳng hạn, mỗi context có thể chạy các bean `CommandLineRunner` / `ApplicationRunner` của chính nó; nếu bật scheduling, mỗi context có thể tự đăng ký các tác vụ `@Scheduled`. Điều này có thể hữu ích khi mỗi context quản lý một nhóm công việc riêng, nhưng cũng có thể dẫn đến chạy trùng tác vụ, gửi trùng thông điệp hoặc xử lý cùng một hàng đợi nếu không được thiết kế rõ.

Ví dụ về rủi ro khi dùng chung một storage hoặc dịch vụ ngoài:

- Context A và B đều chạy mã “khởi tạo dữ liệu đầu tiên” trên cùng database.
- Cả hai đều đăng ký scheduler dọn dẹp trên cùng bảng.
- Một context đóng client dùng chung trong khi runner của context kia vẫn cần gọi client đó.

Nhiều ứng dụng Spring Boot đăng ký JVM shutdown hook để đóng context khi JVM kết thúc bình thường. Cơ chế đó hữu ích ở cuối tiến trình, **nhưng không thay thế việc điều phối vòng đời nếu một context cần được dừng sớm trong khi JVM và các context khác vẫn chạy**. Nếu code cần chọn dừng một context cụ thể, dùng `context.close()` và làm rõ quyền sở hữu tài nguyên, thay vì gọi `System.exit(...)`.

Với thread pool, scheduler, consumer và connection pool, bạn cần quan tâm cả **ngừng nhận việc mới**, **xử lý công việc đang chạy**, và **dọn tài nguyên**. Các callback mặc định có thể không đáp ứng chính xác mọi yêu cầu nghiệp vụ; khi cần, hãy cấu hình graceful shutdown và timeout theo framework/thư viện đang sử dụng.

## 9. Quyết định có nên dùng nhiều context hay không

Nhiều context giải quyết bài toán **tách phạm vi cấu hình và vòng đời Spring** trong một process. Nó hợp lý khi những phần ứng dụng thật sự cần được khởi tạo, sử dụng và đóng độc lập.

Một vài tình huống:

| Nhu cầu | Hướng cân nhắc |
|---|---|
| Chạy hai tập bean có cấu hình khác nhau trong một tiến trình | Hai context độc lập; làm rõ cách ly properties và tài nguyên. |
| Nhiều tính năng cần dùng chung service nền tảng | Parent chứa tài nguyên chung, child chứa bean riêng, với thứ tự đóng rõ ràng. |
| Kiểm thử các cấu hình khởi động khác nhau | Context riêng cho từng thử nghiệm; luôn đóng sau test. |
| Chỉ muốn chia code thành nhiều chức năng | Thường đủ dùng một context với package, module, profile và cấu hình bean phù hợp. |
| Cần cách ly lỗi, tài nguyên hoặc quyền bảo mật giữa các dịch vụ | Nhiều context trong một JVM không tạo ranh giới cách ly tiến trình; cân nhắc các process/service riêng. |

Mỗi context có chi phí khởi tạo và bộ nhớ. Hai context độc lập có thể tạo hai pool kết nối, hai bộ scheduler, hai bộ cache và hai bộ cấu hình tương ứng. Ngược lại, chia sẻ những tài nguyên này quá tùy tiện lại làm mất tính độc lập về vòng đời. Việc chọn mô hình phải dựa vào ranh giới thật sự của dữ liệu và tài nguyên.

## 10. Các lỗi hay gặp và cách nhận diện

**Lỗi 1 — “Singleton chỉ có một instance trong toàn JVM”.**

Sai với Spring singleton thông thường. Một bean singleton được tạo **một lần cho mỗi container sở hữu bean đó**, không phải cho toàn JVM. Ví dụ mục 2 cho thấy hai context độc lập tạo hai `ManagedResource`.

**Lỗi 2 — “Đóng A sẽ tự đóng B vì cả hai dùng cùng class cấu hình”.**

Sai. Dùng chung class cấu hình không làm hai context trở thành một. Context B chỉ bị ảnh hưởng khi có quan hệ phụ thuộc hoặc tài nguyên thực sự dùng chung.

**Lỗi 3 — “Có thể đóng parent trước, các child vẫn an toàn”.**

Không bảo đảm. Child có thể dùng bean hoặc client do parent sở hữu. Cần dừng các child và công việc phụ thuộc trước, sau đó mới đóng parent.

**Lỗi 4 — “Chạy cùng ứng dụng web hai lần sẽ có hai server trên 8080”.**

Hai server không thể cùng bind một cặp địa chỉ/cổng giống nhau theo cách thông thường. Hãy cấu hình cổng riêng hoặc dùng một web context nếu đó mới là kiến trúc mong muốn.

**Lỗi 5 — “`close()` xử lý cả các thread và object do tôi tự `new` ở mọi nơi”.**

Không. Spring chỉ có thể quản lý vòng đời các thành phần được nó sở hữu hoặc những tài nguyên mà mã ứng dụng gắn rõ với callback lifecycle. Việc tự tạo tài nguyên mà không có đường dọn dẹp là nguyên nhân phổ biến gây rò rỉ.

**Lỗi 6 — “Để JVM tắt là đủ, không cần cleanup từng context”.**

Nếu JVM còn phải chạy context khác, chờ process exit sẽ giữ những context không cần thiết và tài nguyên của chúng lâu hơn mong muốn. Ngoài ra, shutdown hook không thay thế cho một quy trình dừng có thứ tự, có kiểm soát.

**Lỗi 7 — “Hai context độc lập thì mọi trạng thái cũng độc lập”.**

Các `static` field, system properties, file, cổng mạng và dịch vụ bên ngoài vẫn có thể chung. Cần đánh giá cả phạm vi Spring container **và** phạm vi JVM/hệ thống.

## 11. Cách tự kiểm tra khi debug

Khi ứng dụng thực tế giữ nhiều context, có thể quan sát từng đối tượng bằng debugger và những lệnh như:

```java
System.out.println(contextA.isActive());
System.out.println(contextB.isActive());
System.out.println(contextA.getParent() == null);
System.out.println(contextA == contextB);
```

Đây là đoạn kiểm tra minh họa khi đã có các biến `contextA` và `contextB`; nó không phải chương trình độc lập. Trong hai context độc lập, `contextA == contextB` phải là `false`. Với hierarchy, `getParent()` giúp quan sát quan hệ cha–con.

Khi kiểm tra sự cố, trả lời lần lượt:

1. Context nào tạo bean hoặc tài nguyên đang gặp vấn đề? Bean nằm ở parent hay child?
2. Ai giữ reference đến tài nguyên đó? Có phải cùng một object được nhiều context dùng chung?
3. Context nào đã `close()`, theo thứ tự nào? Có runner, scheduled task hoặc consumer nào vẫn đang chạy không?
4. Nếu có web server, mỗi context đang bind vào địa chỉ và cổng nào?
5. Khi một context đóng, context khác còn active **và** còn sử dụng được các tài nguyên cần thiết không?

**Mô hình cần ghi nhớ:** Một JVM có thể chạy nhiều `ApplicationContext`; singleton bean và lifecycle thuộc về **context sở hữu**, còn static state và tài nguyên cấp process có thể **dùng chung**. Muốn đóng riêng từng context an toàn, hãy quản lý rõ reference, tài nguyên và thứ tự shutdown — đặc biệt với parent–child, web server và các công việc chạy nền.
