# Đóng Spring ApplicationContext bằng try-with-resources — Spring Core Container

## 1. Mục tiêu và tình huống sử dụng

Bạn đã biết tạo Spring IoC container để đăng ký và lấy bean. Bước tiếp theo là **kết thúc vòng đời container đúng cách**. Một ứng dụng Java chạy một tác vụ rồi thoát có thể tự tạo `AnnotationConfigApplicationContext`; khi hoàn tất, nó phải **đóng context** để Spring có cơ hội gọi các callback hủy bean, giải phóng tài nguyên do bean quản lý và đánh dấu context không còn hoạt động.

**Try-with-resources** là cấu trúc Java thích hợp khi chính đoạn code của bạn **sở hữu vòng đời context**: đóng context theo phạm vi khối lệnh thay vì phải nhớ gọi `close()` ở nhiều đường thoát.

Kết thúc bài học, bạn có thể:

- Phân biệt **đóng Spring context** với chỉ rời phương thức `main`, bỏ reference hoặc để JVM tự thoát.
- Dùng cú pháp `try (AnnotationConfigApplicationContext context = ...)` và `try (context)` trong Java 17.
- Giải thích vì sao Spring context đóng được nhờ giao diện `AutoCloseable`/`Closeable`, và `close()` xảy ra cả khi thân `try` thoát bằng exception.
- Chạy ứng dụng Spring Framework thuần với bean có phương thức hủy `@Bean(destroyMethod = "shutdown")` và **quan sát thứ tự stdout**.
- Đóng context kể cả khi phần `register(...)` / `refresh()` được thực hiện bên trong khối và có khả năng thất bại.
- Nhận diện giới hạn: `prototype` không tự được Spring hủy trọn đời, object tạo ngoài container không tự được quản lý, `System.exit`/crash không phải đường dọn tài nguyên bình thường.
- Biết khi nào **không được đóng** context vì lifecycle thuộc Spring Boot, Spring Test, framework host hoặc thành phần khác.

**Phạm vi:** Bài tập trung vào lifecycle và `try-with-resources` của **Spring Core Container**. Không cần Spring Boot, HTTP server, database, transactional API hay cơ chế shutdown phức tạp để học kỹ năng này.

## 2. Ai sở hữu context thì chịu trách nhiệm đóng?

Một ví dụ dễ gặp:

~~~java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfig.class);
GreetingService service = context.getBean(GreetingService.class);
System.out.println(service.greet("Lan"));
// Nếu kết thúc mà không đóng, container không được yêu cầu dọn dẹp có chủ đích.
~~~

**Đoạn trên chỉ minh họa**, chưa gồm `AppConfig`, `GreetingService` và file Java hoàn chỉnh. Khi ứng dụng sở hữu đối tượng context, nên bảo đảm có `context.close()`.

Tại sao không chỉ chờ garbage collector?

- Garbage collector xử lý **bộ nhớ Java đủ điều kiện thu gom**, không có trách nhiệm gọi callback hủy của bean.
- Bean có thể giữ **connection pool, file handle, background executor, socket, cache hoặc thread**; một số tài nguyên cần shutdown có trật tự để dừng công việc/flush dữ liệu.
- Java không bảo đảm `finalize()` là cơ chế quản lý tài nguyên an toàn; không dùng finalization thay `close()`.
- Ứng dụng short-lived có thể kết thúc trước khi bất cứ cơ chế dọn rác nào có ích; ứng dụng chạy lâu có thể giữ tài nguyên do reference còn tồn tại.

**Phân biệt hai loại sở hữu:**

| Context được ai tạo/quản lý? | Ai quyết định đóng? |
| --- | --- |
| Chính code Java khởi tạo `new AnnotationConfigApplicationContext()` để thực hiện một tác vụ | Chính code đó, thường qua `try-with-resources` |
| Một library tạo context nội bộ và trả service cho bạn | Theo hợp đồng của library; không tùy tiện đóng context của library |
| Spring Boot/framework host tạo ApplicationContext chính | Framework/lifecycle chủ sở hữu thường quyết định shutdown; không đóng trong một service xử lý request |
| Spring Test quản lý và cache test context | Test infrastructure quản lý; không tự đóng sau từng test nếu framework cần dùng lại |

Nếu một service nhận `ApplicationContext` từ nơi khác và gọi `close()`, nó có thể **tắt cả ứng dụng** hoặc phá những bean mà thành phần khác còn cần. Đừng biến việc đóng context thành trách nhiệm của bean nghiệp vụ tùy tiện.

## 3. Hai kiểu try-with-resources hợp lệ trong Java 17

### 3.1. Khai báo resource ngay trong ngoặc try

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {

    GreetingService service = context.getBean(GreetingService.class);
    System.out.println(service.greet("Lan"));
} // Java gọi context.close() khi rời khối theo đường bình thường.
~~~

**Đây là snippet**, còn thiếu import và các lớp nghiệp vụ. `AnnotationConfigApplicationContext` thuộc Spring Framework và đáp ứng hợp đồng `AutoCloseable` thông qua các giao diện context. Java tự gọi `close()` khi rời khối, kể cả khi code thân `try` ném exception.

**Cảnh báo khi bootstrap:** constructor `new AnnotationConfigApplicationContext(AppConfig.class)` thông thường tiến hành đăng ký và refresh ngay. Nếu construction/refresh **ném exception trước khi object được gán thành công vào resource của try**, resource đó chưa được thiết lập trong try-with-resources; không nên tuyên bố khối này luôn đóng được mọi đối tượng context mới tạo thất bại nửa chừng.

### 3.2. Resource là biến local đã khai báo trước: try(context)

Từ Java 9 (bao gồm Java 17), có thể viết:

~~~java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

try (context) {
    context.register(AppConfig.class);
    context.refresh();
    GreetingService service = context.getBean(GreetingService.class);
    System.out.println(service.greet("Lan"));
}

System.out.println("active=" + context.isActive());
~~~

Đây cũng là snippet; chương trình hoàn chỉnh ở mục 5.

- Biến `context` phải **final hoặc effectively final** (không được gán lại sau khởi tạo) để dùng dạng `try (context)`.
- Với constructor **không tham số**, context được tạo nhưng **chưa refresh**. Đưa `register(AppConfig.class)` và `refresh()` **vào bên trong khối** để dù refresh thất bại, resource đã nằm trong vùng mà try-with-resources sẽ cố đóng.
- Khi chạy thành công và rời khối, `close()` đã được gọi. `isActive()` sau đó trả `false` trong ví dụ `AnnotationConfigApplicationContext`.
- Biến `context` vẫn tồn tại sau khối chỉ vì nó được khai báo ngoài; **đừng tiếp tục dùng nó để truy xuất bean**, vì context đã đóng.

### 3.3. So sánh với try-finally

Cách Java cũ thường viết:

~~~java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();
try {
    context.register(AppConfig.class);
    context.refresh();
    // Sử dụng bean.
} finally {
    context.close();
}
~~~

Nếu đã khởi tạo context thành công, cách này cũng có ý định dọn dẹp. Nhưng `try-with-resources` ngắn gọn hơn, thể hiện **phạm vi sở hữu resource**, xử lý cơ chế `close()` chuẩn của Java và có semantics chính thức khi cả thân và việc đóng resource ném exception.

**Một lần đóng có chủ đích** là đủ. Không thêm `context.close()` vào trong khối `try (context)` chỉ để “chắc ăn”; dễ làm khó đọc và khiến người học nhầm thứ tự lifecycle.

## 4. Điều gì xảy ra khi context đóng?

Đối với `AnnotationConfigApplicationContext` đã refresh thành công, `close()` đi qua quy trình đóng context của Spring. Trong điều kiện bình thường, Spring:

1. Phát tín hiệu và thực hiện các giai đoạn shutdown/lifecycle thích hợp cho context.
2. Dừng các bean/lifecycle components thuộc cơ chế lifecycle khi có cấu hình tương ứng.
3. Thực hiện các callback hủy trên **các singleton được quản lý** có khai báo/cơ chế hủy thích hợp (ví dụ method qua `@Bean(destroyMethod = "...")`, `DisposableBean`, `@PreDestroy` khi có hỗ trợ annotation).
4. Giải phóng các tài nguyên nội bộ liên quan tới vòng đời context và đánh dấu context không active nữa.

Không phải **mọi bean** đều có destroy callback. Một bean chỉ chứa các giá trị immutable thường không cần làm gì khi đóng. Container không tự biết đóng một resource được tạo ngoài context rồi lưu ở biến global.

### Đóng context không đồng nghĩa đóng từng đối tượng bằng tay

Trong demo sẽ có một `ManagedAudit` bean với method:

~~~java
public void shutdown() {
    System.out.println("destroy=ManagedAudit");
}
~~~

Là snippet trong class, method này tự nó chỉ là Java. Khi factory method mang annotation:

~~~java
@Bean(destroyMethod = "shutdown")
public ManagedAudit managedAudit() {
    return new ManagedAudit();
}
~~~

Spring sẽ đăng ký **destroy callback** cho bean được quản lý đó. Khi đóng context có bean singleton đã tạo, Spring gọi `shutdown()`. Bạn **không cần** lấy bean rồi tự gọi `shutdown()` trong `main`.

**Đừng lẫn `@Bean(destroyMethod=...)` với `@PreDestroy`**: cả hai có thể dùng để chỉ định công việc hủy trong những điều kiện hỗ trợ, nhưng `@PreDestroy` cần annotation Jakarta phù hợp trong Spring 6+, còn demo này dùng cách rõ ràng `destroyMethod="shutdown"` và không phụ thuộc annotation lifecycle ngoài module đang dùng.

## 5. Project hoàn chỉnh: nhìn thấy callback hủy trên stdout

Dùng **JDK 17+, Maven, Spring Framework 7.0.9** (module `spring-context`). Đây là phiên bản ví dụ được cố định để lệnh và dependency tái lập, **không phải lời khẳng định bản Spring mới nhất**. Không cần Spring Boot, database hay HTTP server.

Cấu trúc thư mục:

~~~text
context-close-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ContextCloseDemo.java
~~~

### 5.1. File pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>context-close-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.ContextCloseDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven lấy `spring-context` và những dependency transitively cần thiết. Chạy `javac` thủ công cần classpath tương ứng; chỉ đưa một JAR Spring vào là thường chưa đủ.

### 5.2. File src/main/java/demo/ContextCloseDemo.java

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class ContextCloseDemo {
    private ContextCloseDemo() {}

    public interface GreetingRepository {
        String message(String name);
    }

    public static final class SimpleGreetingRepository
            implements GreetingRepository {
        @Override
        public String message(String name) {
            return "Xin chao, " + name + "!";
        }
    }

    public static final class ManagedAudit {
        private final List<String> events = new ArrayList<>();

        public void record(String name) {
            events.add(name);
        }

        public List<String> snapshot() {
            return List.copyOf(events);
        }

        public void shutdown() {
            System.out.println("destroy=ManagedAudit");
        }
    }

    public static final class GreetingService {
        private final GreetingRepository repository;
        private final ManagedAudit audit;

        public GreetingService(
                GreetingRepository repository, ManagedAudit audit) {
            this.repository = Objects.requireNonNull(repository);
            this.audit = Objects.requireNonNull(audit);
        }

        public String greet(String input) {
            if (input == null || input.isBlank()) {
                throw new IllegalArgumentException("name must not be blank");
            }
            String name = input.strip();
            String message = repository.message(name);
            audit.record(name);
            return message;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public GreetingRepository greetingRepository() {
            return new SimpleGreetingRepository();
        }

        @Bean(destroyMethod = "shutdown")
        public ManagedAudit managedAudit() {
            return new ManagedAudit();
        }

        @Bean
        public GreetingService greetingService(
                GreetingRepository repository, ManagedAudit audit) {
            return new GreetingService(repository, audit);
        }
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        try (context) {
            context.register(AppConfig.class);
            context.refresh();

            GreetingService service = context.getBean(GreetingService.class);
            ManagedAudit audit = context.getBean(ManagedAudit.class);

            System.out.println("insideActive=" + context.isActive());
            System.out.println("singleton=" +
                    (service == context.getBean(GreetingService.class)));
            System.out.println("greeting=" + service.greet(" Lan "));
            System.out.println("audit=" + audit.snapshot());
        }

        System.out.println("afterActive=" + context.isActive());
    }
}
~~~

**Điểm cần hiểu trước khi chạy:**

- `new AnnotationConfigApplicationContext()` tạo context chưa được refresh; `register(AppConfig.class)` và `refresh()` nằm trong `try (context)`.
- Bean `greetingRepository` cung cấp `GreetingRepository`. Bean `managedAudit` được đánh dấu để gọi method `shutdown()` lúc Spring hủy singleton.
- Bean `greetingService` nhận repository và audit qua tham số factory method. Service **không trực tiếp tra ApplicationContext**, không tự quản lý lifecycle audit.
- `ManagedAudit` chỉ là object Java có method `shutdown()`; Spring biết gọi method ấy nhờ metadata `@Bean(destroyMethod="shutdown")`.
- Trong `try`, service ghi một tên đã chuẩn hóa vào audit; tại cuối khối, **Java gọi context.close()**, và Spring gọi callback hủy audit **trước khi** code ngoài khối in `afterActive=false`.
- Để output có thứ tự xác định, chỉ một bean phát thông báo trong destroy callback. Bài không dựa vào thứ tự khởi tạo của các singleton độc lập.

### 5.3. Chạy bằng Maven

Từ thư mục `context-close-demo`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Stdout chính xác do chương trình Java in khi chạy thành công:**

~~~text
insideActive=true
singleton=true
greeting=Xin chao, Lan!
audit=[Lan]
destroy=ManagedAudit
afterActive=false
~~~

Sáu dòng trên là output từ các lệnh `System.out.println(...)` trong mã demo. Các dòng version của JDK/Maven và logging của tool/framework (nếu cấu hình có) **không tính** là output do đoạn mã demo tự in. Spring thực hiện destroy callback khi context đóng; `destroy=ManagedAudit` **không** có nghĩa Java tự động gọi `shutdown()` trên mọi object có method cùng tên.

### 5.4. Tự dùng javac/java

Vì import Spring API, phải biên dịch/chạy với Spring JAR và dependency transitively liên quan. Nhờ Maven tạo file classpath trước:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/ContextCloseDemo.java
java -cp "out:$(cat classpath.txt)" demo.ContextCloseDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/ContextCloseDemo.java
java -cp "out;$deps" demo.ContextCloseDemo
~~~

Dấu phân tách classpath là `:` trên Linux/macOS và `;` trên Windows. Cả hai đường chạy gọi cùng `main`, do đó sáu dòng stdout của code không thay đổi.

## 6. Dòng thời gian: try-with-resources và Spring destroy callback

~~~mermaid
sequenceDiagram
    participant M as main()
    participant J as Java try-with-resources
    participant C as ApplicationContext
    participant S as GreetingService
    participant A as ManagedAudit
    M->>J: try (context)
    J->>C: register(AppConfig) / refresh()
    C->>S: tạo bean + inject dependencies
    M->>S: greet(" Lan ")
    S->>A: record("Lan")
    M-->>J: rời thân try
    J->>C: close()
    C->>A: shutdown() (destroy callback)
    A-->>M: println destroy=ManagedAudit
    M->>C: isActive()
    C-->>M: false
~~~

Đây là mô hình những bước liên quan trực tiếp tới ví dụ, **không mô tả tất cả Spring lifecycle internals**. Java chịu trách nhiệm gọi `close()` theo cấu trúc `try-with-resources`; Spring chịu trách nhiệm diễn giải việc đóng context thành callback trên các bean mà nó quản lý.

Để tránh nhầm:

- `GreetingService.greet(...)` chạy **vì `main` gọi nó**, không phải vì container tạo bean.
- `ManagedAudit.shutdown()` chạy **vì context đóng và bean có destroy metadata**, không phải vì kết thúc scope Java của biến `audit`.
- `context.isActive()` là **trạng thái context**, không phải kiểm tra mỗi bean còn object trong bộ nhớ. Reference tới object có thể vẫn tồn tại sau khi context đóng, nhưng dùng các collaborator đã shutdown là không an toàn hoặc sai hợp đồng.

## 7. Khi có exception: Java bảo đảm gì?

Try-with-resources có mục tiêu giúp resource được **đóng khi rời khối theo cơ chế ngôn ngữ**, kể cả khi thân `try` thất bại:

~~~java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

try (context) {
    context.register(AppConfig.class);
    context.refresh();
    throw new IllegalStateException("example failure");
} // Java vẫn gọi context.close() khi thoát do exception.
~~~

Đây chỉ là **snippet minh họa** để quan sát semantics Java; nó sẽ ném exception và không tạo stdout “happy path”. Không ghép trực tiếp vào chương trình chính nếu đang so sánh sáu dòng đầu ra.

Nếu cần bắt lỗi ứng dụng tại ranh giới, dùng cấu trúc:

~~~java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

try (context) {
    context.register(AppConfig.class);
    context.refresh();
    // Sử dụng bean; có thể ném lỗi.
} catch (RuntimeException failure) {
    System.err.println("Job failed: " + failure.getClass().getSimpleName());
}
~~~

Trong Java, **resource được đóng trước khi phần catch tương ứng ở ngoài xử lý exception**. Nhưng việc bạn catch rồi tiếp tục có hợp lý hay không phụ thuộc nghiệp vụ; đừng nuốt lỗi bootstrap Spring rồi tiếp tục chạy với service null.

### Suppressed exception là quy tắc Java, không phải cam kết của mọi destroy callback Spring

Nếu **thân try** ném exception A và thao tác **close()** của resource cũng ném exception B ra ngoài, Java giữ A làm exception chính, B được gắn dưới `A.getSuppressed()`. Đây là **cơ chế chung của Java try-with-resources**.

Trong Spring, exception từ bean destroy callback có thể được framework ghi log/xử lý theo đường nội bộ; **không được suy ra** tất cả lỗi shutdown của từng bean nhất định sẽ xuất hiện trong `getSuppressed()` của exception thân try. Khi debug đóng context, cần xem logging/callback cụ thể.

**Giới hạn quan trọng:** try-with-resources không thể bảo đảm callback được chạy khi cả JVM/process bị chấm dứt đột ngột, `Runtime.halt(...)`, máy mất điện hoặc crash. Bảo đảm trong ngữ nghĩa Java áp dụng cho **luồng điều khiển thông thường hoặc exception** khi thực sự rời khối và resource đã được đăng ký với try.

## 8. Đặt refresh() bên trong khối để quản lý lỗi bootstrap

So sánh hai cách:

**Cách ngắn cho ví dụ rất nhỏ:**

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {
    // Context đã refresh khi constructor trả về thành công.
}
~~~

**Cách cho phép đưa giai đoạn khởi động vào phạm vi dọn dẹp:**

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext()) {
    context.register(AppConfig.class);
    context.refresh();
    // Chạy tác vụ.
}
~~~

Nếu quá trình `refresh()` trong thân `try` ném lỗi, resource context đã được tạo và gắn vào cơ chế try-with-resources, nên Java vẫn gọi `close()` khi thoát. Điều này **không có nghĩa bean khởi tạo thất bại chắc chắn đã tạo xong hoặc có đầy đủ destroy callback**; Spring có các pha cleanup riêng khi refresh thất bại.

Dạng thứ hai cũng giúp việc thêm cấu hình động rõ ràng:

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext()) {
    context.register(AppConfig.class);
    context.refresh();
    System.out.println(context.containsBean("greetingService"));
}
~~~

Đây là snippet chạy trong một chương trình có `AppConfig`, **không phải file độc lập**. Không gọi `refresh()` lặp nhiều lần trên cùng `GenericApplicationContext/AnnotationConfigApplicationContext`; các context thuộc nhóm này có chính sách refresh một lần.

## 9. Scope và giới hạn của quản lý destroy

| Trường hợp | Hành vi cần nhớ |
| --- | --- |
| Managed singleton đã được tạo, có destroy callback | Context thường gọi callback khi đóng thành công |
| Bean không có callback hay tài nguyên riêng | Không cần in thông báo hoặc làm việc hủy đặc biệt |
| Bean prototype được Spring tạo và giao cho caller | Spring thường **không quản lý toàn bộ bước hủy prototype** sau đó; caller chịu trách nhiệm phù hợp |
| Object tự tạo bằng `new` ngoài container | Không tự nhận destroy callback của Spring |
| Resource được bean mở nhưng không được bean đóng đúng | Đóng context không tự khắc phục lỗi quản lý resource trong mã bean |
| Context bị framework khác sở hữu | Không tùy tiện dùng try-with-resources để đóng context mà thành phần khác còn sử dụng |

### Prototype là ngoại lệ quan trọng

~~~java
@Bean
@org.springframework.context.annotation.Scope("prototype")
SomeWorker someWorker() {
    return new SomeWorker();
}
~~~

Đây chỉ là snippet minh họa, `SomeWorker` không được định nghĩa trong ví dụ này. Spring tạo prototype khi có yêu cầu nhưng **không tự chạy toàn bộ lifecycle destruction** của prototype sau khi giao object cho caller. Nếu `SomeWorker` sở hữu file/socket, code sở hữu object hoặc cơ chế quản lý tài nguyên riêng phải quan tâm đóng.

Đừng đọc câu “đóng context sẽ đóng tất cả bean” theo nghĩa bao trùm mọi loại scope và mọi object do Java tạo ra.

### Có nên dùng @PreDestroy thay @Bean(destroyMethod)?

Có thể, nếu bean được container quản lý và application có API annotation phù hợp. Với Spring Framework 6, annotation tiêu chuẩn là `jakarta.annotation.PreDestroy`, **không phải `javax.annotation.PreDestroy`** của ứng dụng cũ. Khi dùng cần dependency/annotation processing tương ứng theo môi trường.

Trong bài này, `@Bean(destroyMethod="shutdown")` là lựa chọn đơn giản nhất để thấy trực tiếp cách định nghĩa callback ở cấu hình Java, không cần thêm thư viện annotation.

Bean có thể implement `DisposableBean` hoặc một interface Java như `AutoCloseable`; Spring cũng có thể tự suy luận một số destroy method `close`/`shutdown` trong những tình huống phù hợp. Tuy nhiên, **không dựa vào suy luận mơ hồ cho ví dụ cần output xác định**: chỉ định rõ method khi học cơ chế.

## 10. Những lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Tạo context trong tác vụ ngắn mà không bao giờ đóng | Callback hủy/resource cleanup có thể không được thực hiện có chủ đích | Dùng `try-with-resources` hoặc `finally { context.close(); }` |
| Đóng context ngay sau khi trả về một bean cho caller | Bean vẫn được dùng khi container đã shutdown | Để người tạo/chủ sở hữu context quyết định vòng đời |
| Service gọi `context.close()` sau một request | Tắt container chung và ảnh hưởng request khác | Không đặt trách nhiệm đóng context trong service nghiệp vụ |
| Gọi `context.close()` vừa trong thân `try` vừa khi TWR kết thúc | Logic hủy bị lặp ở cấp ý định, làm code khó kiểm soát | Để TWR đảm nhận `close()` một lần theo cấu trúc |
| Cho rằng `@Bean` nào cũng in gì đó khi đóng | Bean không có callback không phát sinh output | Gắn `destroyMethod` hoặc callback thích hợp nếu có công việc cần làm |
| Đánh đồng `close()` với garbage collection | Không hiểu tài nguyên ngoài heap/lifecycle | Tách đối tượng được thu gom với thao tác shutdown bean |
| Expect prototype luôn được tự động destroy | Tài nguyên của prototype bị bỏ quên | Giao trách nhiệm đóng cho owner hoặc dùng scope/cơ chế quản lý phù hợp |
| Tạo context bằng constructor refresh sẵn rồi cho rằng mọi lỗi tạo đều được TWR cleanup | Constructor có thể fail trước khi trở thành resource hợp lệ | Khi cần quản lý lỗi bootstrap, tạo context chưa refresh rồi `register/refresh` trong `try` |
| Dùng lại context sau close | Bean lookup hoặc lifecycle API không còn ở trạng thái dùng được | Tạo context mới ở một phiên làm việc mới khi cần |
| Dùng `System.exit(0)` như phương án cleanup | Có thể bỏ qua đường unwind Java bình thường | Kết thúc luồng qua return/exception, cho TWR đóng theo cấu trúc |
| Cấu hình sai `destroyMethod` | Có thể lỗi khi tạo bean hoặc callback không như mong đợi | Dùng tên method thật, không nhầm method có tham số hoặc tên typo |
| `javac` báo thiếu package Spring | Lỗi classpath, không phải lỗi `close()` | Dùng Maven hoặc tạo đúng classpath transitively |

**Không coi close là công cụ xử lý mọi lỗi:** nếu bean không đóng socket/file của nó theo hợp đồng, container không thể tự sửa logic đó. Cần unit test cho đối tượng sở hữu tài nguyên và smoke test cho context shutdown.

## 11. So sánh ba cách kết thúc lifecycle

| Phương án | Ưu điểm | Giới hạn |
| --- | --- | --- |
| `try (context) { ... }` | Rõ ràng chủ sở hữu, close theo lexical scope, tốt cho Java 17 | Chỉ dùng khi context thật sự do khối code đó sở hữu |
| `try { ... } finally { context.close(); }` | Dùng được ở code cũ và cho pattern phức tạp | Dễ lặp boilerplate hoặc quên `finally` nếu viết ẩu |
| `context.registerShutdownHook()` | Đăng ký JVM shutdown hook giúp đóng context khi JVM shutdown bình thường | Không thay thế close có chủ đích của tác vụ ngắn; không bảo đảm khi terminate/crash/kill -9 |

Đừng thường xuyên trộn `registerShutdownHook()` với TWR cho cùng context nếu không có lý do rõ; dễ làm mờ ownership và kỳ vọng thời điểm callback. Spring có cơ chế bảo vệ trạng thái khi shutdown, nhưng **thiết kế rõ một chủ sở hữu** luôn dễ kiểm tra hơn.

Nếu viết một ứng dụng dài hạn có lifecycle do framework điều phối, phải theo cơ chế shutdown của framework và hạ tầng triển khai, không kết thúc context của cả app sau khi xử lý một request.

## 12. Thực hành mở rộng và QA đầu ra

### Bài 1: Thêm một callback khác

Đăng ký bean phụ `TaskRecorder` có destroy callback riêng và cho `GreetingService` inject nó. Chạy và ghi nhận thứ tự callback thực tế. **Không dựa vào thứ tự khai báo method** để tạo hợp đồng thứ tự. Nếu bean B phụ thuộc A và đều có lifecycle, quan hệ phụ thuộc có thể ảnh hưởng trình tự hủy, nhưng cần thiết kế dựa trên dependency thật, không dựa vào log tình cờ.

### Bài 2: Ném lỗi trong thân try

Trong chương trình demo, thay lời gọi `service.greet(" Lan ")` bằng câu lệnh ném `IllegalStateException` **sau khi context.refresh() thành công**. Quan sát callback `destroy=ManagedAudit` vẫn chạy khi Java unwind vì exception. Không so đầu ra với sáu dòng happy path trong bài thử âm này.

### Bài 3: Làm refresh thất bại

Tạo một `@Bean` yêu cầu dependency bắt buộc mà cấu hình không đăng ký. Dùng pattern tạo context chưa refresh rồi gọi `refresh()` **bên trong try**. Quan sát context fail-fast; không giả định callback hủy của bean chưa được tạo cũng sẽ xuất hiện.

### Bài 4: Chạy với tên input khác

Trong happy path, đổi `" Lan "` thành `" Minh "`. Dự đoán hai dòng thay đổi:

~~~text
greeting=Xin chao, Minh!
audit=[Minh]
~~~

Các dòng trạng thái context/singleton và `destroy=ManagedAudit` không đổi trong cùng cấu hình.

### Bài 5: Viết test kiểm tra shutdown

Với Spring context do test tự tạo, có thể dùng bean fake giữ boolean `closed` và gắn destroy callback để chứng minh `closed==true` sau khi ra khỏi try. Hãy tránh gọi tiếp method nghiệp vụ trên resource đã đóng chỉ để test.

### Checklist để coi bài đạt

- [ ] Biết ai **sở hữu context** và vì sao cần đóng.
- [ ] Phân biệt `close()` của context với việc thu gom bộ nhớ.
- [ ] Dùng `try-with-resources` với context hỗ trợ `AutoCloseable`.
- [ ] Nắm khác biệt giữa `try (Type resource = ...)` và `try (resource)` của Java 9+.
- [ ] Với lỗi bootstrap, biết cách đưa `register/refresh` vào thân try đã sở hữu resource.
- [ ] Gắn callback cụ thể bằng `@Bean(destroyMethod="shutdown")`.
- [ ] Chạy JDK 17+ với Maven hoặc javac/java có classpath Spring.
- [ ] Đối chiếu đủ **sáu dòng stdout** của ví dụ.
- [ ] Phân biệt singleton destruction với prototype/non-managed object.
- [ ] Không đóng context được cấp bởi framework/đối tượng khác khi không sở hữu.
- [ ] Không kỳ vọng TWR luôn cleanup được khi JVM bị kill/crash.
- [ ] Biết dùng log và kiểm thử để xác minh callback thay vì suy đoán.

**Kết luận:** Try-with-resources không phải annotation của Spring; đó là **cơ chế ngôn ngữ Java** bảo đảm gọi `close()` cho resource đã được đăng ký khi rời khối. Vì Spring context triển khai hợp đồng đóng được, cơ chế Java ấy kích hoạt **quy trình shutdown của Spring**, trong đó có destroy callbacks trên các bean được quản lý phù hợp. Hãy **đóng context tại nơi sở hữu nó**, không phải tại mọi nơi đang sử dụng bean.

### Tài liệu chính thức

- [Spring — Shutting Down the Container Gracefully](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring — Using @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Java Language Guide — try-with-resources](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html)
