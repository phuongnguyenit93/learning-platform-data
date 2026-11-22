# Phân biệt tiến trình JVM, ứng dụng Spring Boot, ApplicationContext và bean

## 1. Bức tranh tổng thể

Khi chạy một ứng dụng Spring Boot bằng `java -jar` hoặc lệnh của Maven/Gradle, bốn khái niệm thường xuất hiện cùng nhau nhưng nằm ở các cấp khác nhau:

| Khái niệm | Bản chất | Ai tạo/quản lý? | Ranh giới và vòng đời |
| --- | --- | --- | --- |
| **Tiến trình JVM (JVM process)** | Một tiến trình của hệ điều hành đang thực thi chương trình Java; có PID, bộ nhớ và các luồng của nó | Hệ điều hành khởi chạy chương trình `java`; JVM quản lý heap, GC và việc thực thi mã Java | Từ lúc tiến trình khởi động đến khi tiến trình kết thúc |
| **Ứng dụng Spring Boot** | Chương trình Java sử dụng Spring Boot để khởi tạo cấu hình, hạ tầng và nghiệp vụ; trong lúc chạy là một phiên ứng dụng | Mã `main` gọi `SpringApplication.run(...)` hoặc cơ chế bootstrap tương đương | Gắn với quá trình khởi động/vận hành của ứng dụng; không phải một loại tiến trình OS riêng |
| **`ApplicationContext`** | Container của Spring: nơi đăng ký định nghĩa bean, tạo và liên kết bean, cung cấp cấu hình, sự kiện và cơ chế quản lý vòng đời | Spring tạo và `refresh` context trong quá trình bootstrap; lập trình viên có thể tạo thêm context | Từ lúc context được tạo/khởi tạo thành công đến khi `close`; có thể có nhiều context trong một JVM |
| **Bean** | Một đối tượng được Spring container quản lý theo một định nghĩa bean và scope cụ thể | `ApplicationContext`/`BeanFactory` tạo, cung cấp, tiêm phụ thuộc và quản lý vòng đời tùy scope | Phụ thuộc scope và context chứa bean; không mặc nhiên sống suốt vòng đời JVM |

Hình dung **trường hợp thông dụng** — một chương trình Spring Boot chạy trong một tiến trình Java và có một context chính:

```text
Hệ điều hành
└── Tiến trình JVM (có PID, heap, threads)
    └── Chương trình Spring Boot đang chạy
        └── ApplicationContext chính
            ├── Bean: OrderService
            ├── Bean: OrderRepository
            ├── Bean: DataSource
            └── Nhiều bean hạ tầng do auto-configuration đăng ký
```

Sơ đồ mô tả quan hệ quản lý ở mức khái niệm, không phải bốn đối tượng cùng kiểu. **Không có quy luật 1 JVM = 1 Spring Boot application = 1 context = 1 bean**: một JVM có thể tạo nhiều context; trong một context có nhiều bean; hai JVM riêng biệt không chia sẻ đối tượng Java trong heap.

## 2. Nhìn từng lớp cho đúng

### 2.1. Tiến trình JVM: ranh giới của hệ điều hành và bộ nhớ

- Lệnh `java -jar app.jar` thường tạo một tiến trình Java riêng, có PID riêng. JVM trong tiến trình đó tải class, chạy bytecode/JIT, quản lý heap, GC và các luồng Java.
- Chương trình có thể dùng Spring Boot, Spring thuần hoặc không dùng Spring. **JVM không biết khái niệm bean**; bean là khái niệm của Spring.
- Một tiến trình có thể chứa nhiều luồng xử lý HTTP và nhiều đối tượng Java nhưng vẫn là **một** tiến trình. Tạo một `Thread`, `ExecutorService` hoặc một bean không tạo JVM mới.
- Chạy cùng một JAR hai lần bằng hai lệnh `java -jar` thường tạo hai PID và hai heap độc lập. Bean trong tiến trình A không phải cùng đối tượng với bean trong tiến trình B.

Có thể quan sát PID ngay trong Java 17+ bằng `ProcessHandle.current().pid()`; ở hệ điều hành dùng Task Manager, `ps`, `jps` hoặc `jcmd` tùy môi trường. PID chỉ nhận diện tiến trình, không nhận diện duy nhất từng context hay bean.

### 2.2. Ứng dụng Spring Boot: chương trình và quá trình bootstrap

Trong mã nguồn, `@SpringBootApplication` thường đánh dấu class cấu hình gốc. Annotation này kết hợp các khả năng cấu hình Spring Boot, auto-configuration và component scanning; **annotation không tự tạo tiến trình JVM**.

Khi `main` chạy và gọi `SpringApplication.run(...)`, Spring Boot thiết lập môi trường, đọc nguồn cấu hình, tạo và khởi tạo `ApplicationContext` thích hợp, đăng ký các bean definition, xử lý auto-configuration, khởi tạo những bean cần thiết và thực thi các bước khởi động. Phương thức `run` trả về một `ConfigurableApplicationContext` khi thành công.

Một ứng dụng Boot có thể chạy như CLI/job không có web server hoặc chạy với embedded servlet/reactive web server. Sự có mặt của HTTP server không quyết định một đối tượng có phải bean hay không. Spring Boot cũng có thể khởi tạo context con hoặc nhiều context theo thiết kế; **một ứng dụng không đồng nghĩa tuyệt đối với đúng một context**.

Phân biệt hai cách nói:

- **“Dự án/ứng dụng Spring Boot”**: mã nguồn, cấu hình và artifact có thể triển khai.
- **“Một phiên ứng dụng đang chạy”**: lần thực thi cụ thể trong một hoặc nhiều tiến trình theo mô hình triển khai. Ở kiểu triển khai JAR thường gặp, một phiên chạy tương ứng một JVM process.

### 2.3. ApplicationContext: container quản lý các đối tượng Spring

`ApplicationContext` là interface của Spring, mở rộng khả năng của `BeanFactory`. Context không phải hệ điều hành, tiến trình Java hay ứng dụng hoàn chỉnh. Nó giữ/cung cấp các bean definition và bean, giải quyết dependency injection, quản lý scope, lifecycle callback, đọc `Environment`/properties và phát sự kiện ứng dụng.

Thông thường, context được cấu hình từ `@Configuration`, các phương thức `@Bean`, class `@Component`/`@Service`/`@Repository`, các import và auto-configuration. **Class được gắn `@Component` chỉ trở thành bean khi thực sự được component scan/đăng ký vào context thích hợp**.

Một số thao tác tiêu biểu:

- `context.getBean(OrderService.class)`: lấy bean đã đăng ký theo type; có thể thất bại nếu thiếu hoặc có nhiều bean cùng type mà không phân giải được.
- `context.getId()`: lấy định danh context, hữu ích để chẩn đoán; không nên xem là PID hay bảo đảm độc nhất toàn hệ thống.
- `context.isActive()` với `ConfigurableApplicationContext`: kiểm tra trạng thái context đã được khởi tạo và đang hoạt động.
- `context.close()`: đóng context, dừng các thành phần phù hợp và gọi callback hủy của bean thuộc diện quản lý.

**Đóng context không đồng nghĩa trực tiếp với gọi `System.exit(...)`.** Tiến trình JVM chỉ kết thúc khi điều kiện kết thúc của JVM được đáp ứng (ví dụ không còn non-daemon thread hoạt động) hoặc bị yêu cầu dừng. Ngược lại, dừng tiến trình đột ngột như `kill -9` có thể khiến lifecycle callback của Spring không được chạy.

### 2.4. Bean: đối tượng Java được Spring quản lý

Bean vẫn là một **đối tượng Java**, chẳng hạn `OrderService`, `DataSource` hoặc một HTTP client. Điểm khác là Spring biết bean definition của nó, có thể xây dựng đối tượng, tiêm dependency và quản lý vòng đời theo scope.

Hai cách khai báo thường gặp:

```java
@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository; // constructor injection
    }
}
```

```java
@Configuration
public class AppConfig {
    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
```

Đoạn mã trên **minh họa cách khai báo**, chưa phải hai chương trình chạy độc lập; cần các import, `OrderRepository` và dự án Spring tương ứng. `@Bean` phù hợp khi muốn đăng ký đối tượng do phương thức factory tạo ra, kể cả class thuộc thư viện bên ngoài. `@Component` và các stereotype thường phù hợp cho class nghiệp vụ do dự án sở hữu.

Ngược lại, `new OrderService(...)` do mã của bạn tự gọi **không tự động biến đối tượng mới thành Spring bean**, dù class có annotation `@Service`. Spring không mặc nhiên tiêm dependency hay gọi lifecycle callback cho đối tượng tự tạo ngoài container.

**Scope rất quan trọng:**

| Scope | Ý nghĩa đối với số lượng instance |
| --- | --- |
| `singleton` (mặc định) | Thông thường một instance **cho mỗi bean definition trong mỗi Spring container**, không phải một instance duy nhất cho toàn JVM hay toàn cluster |
| `prototype` | Container tạo instance mới khi được yêu cầu lấy bean; Spring không tự quản lý toàn bộ giai đoạn hủy của prototype như singleton |
| `request`, `session` | Scope gắn với request/session trong ngữ cảnh web hỗ trợ tương ứng; không phải mọi chương trình CLI đều có các scope này |

Nếu một prototype được inject vào một singleton qua constructor thì dependency thường được giải quyết **một lần khi singleton được tạo**; không tự tạo prototype mới mỗi lần gọi phương thức. Cần lookup/provider phù hợp nếu muốn lấy instance mới theo nhu cầu.

## 3. Thứ tự khởi động và vòng đời

Ở cấu hình Spring Boot thông dụng, đường đi có thể đọc như sau:

```text
OS khởi chạy lệnh java
  → Tiến trình JVM bắt đầu, gọi public static void main(String[] args)
  → SpringApplication.run(...)
  → Chuẩn bị Environment và cấu hình khởi động
  → Tạo ApplicationContext phù hợp
  → Đăng ký bean definition từ configuration, scanning, auto-configuration
  → Refresh context: tạo/wire các non-lazy singleton cần thiết, lifecycle init
  → Gọi ApplicationRunner/CommandLineRunner (nếu có)
  → Ứng dụng sẵn sàng phục vụ công việc
  → Khi đóng context: lifecycle shutdown, @PreDestroy/DisposableBean phù hợp
  → Tiến trình JVM kết thúc khi không còn lý do duy trì nó
```

Đây là mô hình đơn giản hóa: Spring còn có sự kiện, post-processor và các pha lifecycle riêng; bean `lazy`/`prototype` có thể được tạo muộn. Một `ApplicationContext` có thể đóng khi JVM vẫn đang chạy, và một JVM có thể quản lý nhiều context.

Phân biệt các thời điểm:

- **JVM đã chạy**: mã Java đã có thể thực thi, nhưng chưa chắc Spring context tồn tại.
- **Context đang khởi tạo**: bean definition có thể đã đăng ký nhưng không có nghĩa mọi bean instance đã được tạo.
- **Context đã refresh và active**: phần lớn eager singleton đã được tạo; startup runner và các công việc liên quan vẫn có thể tiếp tục sau refresh.
- **Ứng dụng ready**: thông thường sau các startup runner, Spring Boot phát `ApplicationReadyEvent`.
- **Shutdown**: đóng context giải phóng tài nguyên bean theo lifecycle; thời điểm JVM dừng còn tùy các luồng và cách chạy ứng dụng.

## 4. Ví dụ Spring Boot 3.x / Java 17+ chạy được

Trong một dự án Spring Boot dùng Java 17 trở lên, có dependency `spring-boot-starter` (có thể thêm các starter khác), đặt hai file sau cùng package `com.example.runtime`. Ví dụ cố ý dùng `WebApplicationType.NONE` để không mở web server, nhờ đó chỉ quan sát các tầng runtime. Có thể chạy bằng plugin Spring Boot của Gradle hoặc Maven.

**File `src/main/java/com/example/runtime/RuntimeDemoApplication.java`**

```java
package com.example.runtime;

import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class RuntimeDemoApplication {

    public static void main(String[] args) {
        // JVM đã hoạt động trước khi ApplicationContext được tạo.
        System.out.println("JVM PID positive: " + (ProcessHandle.current().pid() > 0));

        try (ConfigurableApplicationContext context =
                new SpringApplicationBuilder(RuntimeDemoApplication.class)
                        .web(WebApplicationType.NONE)
                        .run(args)) {

            GreetingService first = context.getBean(GreetingService.class);
            GreetingService second = context.getBean(GreetingService.class);

            System.out.println("Context active: " + context.isActive());
            System.out.println("Same singleton: " + (first == second));
            System.out.println(first.message());
        } // Tự động gọi close() của context ở đây.
    }
}
```

**File `src/main/java/com/example/runtime/GreetingService.java`**

```java
package com.example.runtime;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class GreetingService {

    public String message() {
        return "Xin chào từ Spring bean";
    }

    @PreDestroy
    public void onDestroy() {
        System.out.println("Bean destroyed");
    }
}
```

Chạy bằng một trong các lệnh tương ứng với **dự án đã có Spring Boot Gradle/Maven plugin và wrapper**:

```bash
# macOS/Linux, dự án Gradle
./gradlew bootRun

# macOS/Linux, dự án Maven
./mvnw spring-boot:run
```

```powershell
# Windows, dự án Gradle
.\gradlew.bat bootRun

# Windows, dự án Maven
.\mvnw.cmd spring-boot:run
```

Các dòng do **mã ví dụ** in ra có thứ tự và giá trị như sau; Spring Boot có thể in thêm banner hoặc log khởi động xen giữa:

```text
JVM PID positive: true
Context active: true
Same singleton: true
Xin chào từ Spring bean
Bean destroyed
```

**Giải thích từng bằng chứng:**

1. Dòng PID được in **trước** `SpringApplicationBuilder.run(...)`: JVM process đang tồn tại ngay cả khi chưa có context.
2. Lời gọi `run` khởi tạo ứng dụng Boot và trả về một context đang active.
3. Hai lần `getBean(GreetingService.class)` trả về cùng tham chiếu vì `GreetingService` là singleton mặc định **trong context này**. Điều đó không nói gì về bean của context khác.
4. Phương thức `message()` là hành vi Java thông thường của đối tượng; Spring quản lý cách nhận được đối tượng và vòng đời của nó.
5. Kết thúc `try` gọi `close` của context, do đó Spring gọi `@PreDestroy` cho singleton này và in `Bean destroyed`. Sau đó `main` kết thúc; trong ví dụ non-web không có công việc nền khác giữ JVM sống.

Nếu tạo hai `ApplicationContext` độc lập và đăng ký cùng bean definition dạng singleton trong mỗi context, kết quả thông thường là **hai instance khác nhau**: gọi `getBean` lặp trong context A cho cùng instance A, trong context B cho instance B. Nếu dùng context cha–con, context con cũng có thể truy cập bean từ cha; lúc đó cần phân biệt bean thuộc container nào.

## 5. Cách chọn đúng khái niệm khi chẩn đoán lỗi

| Dấu hiệu/câu hỏi | Cấp cần kiểm tra | Cách suy luận đúng |
| --- | --- | --- |
| Tiến trình Java ngốn heap hoặc biến mất khỏi danh sách PID | **JVM process** | Kiểm tra PID, heap, thread dump, GC, exit code; chưa đủ căn cứ kết luận lỗi ở một bean cụ thể |
| `SpringApplication.run` thất bại hoặc không khởi động web server | **Boot bootstrap / context refresh** | Đọc exception gốc, cấu hình, dependency, bean creation hoặc lỗi bind port |
| `NoSuchBeanDefinitionException` | **ApplicationContext / bean registration** | Xem bean có được scan/khai báo và điều kiện auto-configuration có thỏa không; không suy ra JVM chưa chạy |
| `NoUniqueBeanDefinitionException` | **Bean resolution** | Có nhiều bean phù hợp một điểm inject; dùng `@Qualifier`/`@Primary` hoặc thiết kế lại sự phụ thuộc |
| Dependency `null` sau khi tự gọi `new SomeService()` | **Bean management** | Đối tượng được tự tạo ngoài container; ưu tiên constructor injection và để Spring tạo đối tượng |
| Một service giữ trạng thái giữa các request | **Bean scope và thread safety** | Singleton thường được nhiều request/thread dùng chung; không nên để mutable per-request state trong singleton |
| Chạy cùng JAR ở hai container/Pod khác nhau | **Nhiều JVM process và nhiều context** | Không chia sẻ heap/bean instance; muốn chia sẻ trạng thái phải dùng hệ thống bên ngoài phù hợp |
| Đóng context rồi nhưng tiến trình chưa thoát | **Context lifecycle so với JVM lifecycle** | Kiểm tra luồng non-daemon hoặc công việc khác; `close()` không phải lệnh kết thúc OS process |

## 6. Những ngộ nhận cần tránh

- **“Spring Boot chính là JVM.”** Sai: Spring Boot là framework/cơ chế bootstrap chạy **trong** JVM, không thay thế JVM.
- **“Cứ có `@Service` thì object nào của class đó cũng là bean.”** Sai: Spring phải quản lý instance cụ thể; `new` bên ngoài context vẫn là đối tượng Java thông thường.
- **“Singleton nghĩa là một object duy nhất trong toàn bộ hệ thống.”** Sai: scope singleton của Spring gắn với bean definition và container; nhiều context, process hoặc instance triển khai có thể có các singleton riêng.
- **“Context chính là tất cả bean.”** Chưa chính xác: context là container và cơ chế quản lý; bean là các đối tượng mà container cung cấp.
- **“Mọi bean tạo ngay khi JVM chạy.”** Sai: JVM chạy trước; nhiều eager singleton được tạo khi context refresh, còn lazy/prototype/request-scoped bean có thời điểm tạo khác nhau.
- **“Tạo một thread, request hoặc bean là tạo thêm ứng dụng Boot/JVM.”** Sai: thread và request thường được xử lý trong tiến trình và context hiện có; scope bean có thể khác nhau nhưng không mặc nhiên tạo thêm JVM.
- **“Đóng một context luôn tắt toàn bộ tiến trình.”** Sai: một JVM có thể có thêm context hoặc luồng công việc khác; với ứng dụng chỉ có một non-web context và không còn luồng giữ sống, tiến trình sẽ kết thúc sau khi `main` hoàn tất.

## 7. Tự kiểm tra hiểu biết

1. **Tại sao `main` có thể in PID trước khi gọi `SpringApplication.run`?** Vì JVM được tạo và bắt đầu thực thi Java trước khi Spring Boot bootstrap context.
2. **Hai lần inject một singleton bean vào hai service trong cùng context có phải hai object?** Mặc định là cùng object cho cùng bean definition; cần xem thêm proxy/scope và cấu hình thực tế khi so sánh identity.
3. **Hai tiến trình `java -jar app.jar` có chia sẻ một singleton `UserService` không?** Không: chúng có heap và context riêng. Chia sẻ dữ liệu giữa tiến trình cần cơ chế bên ngoài JVM như database, cache hoặc messaging.
4. **Một class có `@Component` nhưng nằm ngoài component scan có tự trở thành bean không?** Không, trừ khi được đăng ký bằng cơ chế khác.
5. **Khi `@PreDestroy` không chạy sau `kill -9`, có chứng minh bean không do Spring quản lý không?** Không: tiến trình bị dừng đột ngột nên không có cơ hội shutdown bình thường.

**Ghi nhớ:** JVM là môi trường tiến trình thực thi Java; Spring Boot khởi động ứng dụng trên môi trường đó; `ApplicationContext` là container Spring được khởi tạo; bean là đối tượng do container quản lý. Muốn xác định vòng đời hoặc phạm vi chia sẻ trạng thái, hãy hỏi đang nói tới **tiến trình, context, bean definition hay một bean instance**.
