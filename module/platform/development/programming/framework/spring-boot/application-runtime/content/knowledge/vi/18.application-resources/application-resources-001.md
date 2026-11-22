# Xác định chủ sở hữu và thời hạn sống của từng tài nguyên trong Spring Boot

## 1. Bài toán: tạo được tài nguyên chưa đủ, phải biết ai đóng nó

Một ứng dụng Spring Boot sử dụng nhiều tài nguyên: connection pool, HTTP client, executor, file stream, JDBC connection, message consumer, transaction, cache, thread, socket và cả những đối tượng cấp phát trong mỗi request. **Mỗi tài nguyên cần có chủ sở hữu (owner) và thời hạn sống (lifetime) được xác định rõ.**

Ví dụ, một HTTP request muốn đọc dữ liệu:
- Request handler **mượn** một connection từ pool.
- Pool **sở hữu các kết nối vật lý** và quyết định mở, tái sử dụng, loại bỏ chúng.
- Code nghiệp vụ **sở hữu handle/lease** đang mượn và phải trả nó đúng lúc.
- `ApplicationContext` (thường thông qua một bean pool) quản lý thời hạn sống của pool trong ứng dụng.
- Máy chủ database bên ngoài **không thuộc sở hữu của JVM**, nên shutdown ứng dụng không có quyền xóa database.

Nếu nhầm các vai trò này, hai lỗi đối nghịch sẽ xảy ra:

1. **Rò tài nguyên:** không ai đóng file, connection, response body, thread hoặc subscription.
2. **Đóng quá sớm:** một request đóng pool/client dùng chung, làm các request khác thất bại.

Câu hỏi của bài không phải chỉ là “nên dùng `@PreDestroy` hay `try-with-resources`?” mà là: **Ai đã tạo hoặc nhận trách nhiệm sở hữu, ai chỉ mượn, ai có quyền đóng, khi nào quyền sử dụng hết hiệu lực, và ai dọn dẹp nếu khởi tạo lỗi?**

## 2. Năm trường thông tin phải ghi rõ cho mỗi tài nguyên

Một bảng quyết định tốt nên mô tả ít nhất:

| Thuộc tính | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Creator** | Ai gọi API tạo/mở? | Auto-configuration tạo `DataSource` |
| **Owner** | Ai chịu trách nhiệm đảm bảo release? | Bean connection pool được container quản lý |
| **Borrower/User** | Ai được phép dùng nhưng không sở hữu resource gốc? | Repository mượn JDBC connection |
| **Lifetime** | Tài nguyên hợp lệ từ mốc nào đến mốc nào? | Pool tồn tại cùng ApplicationContext |
| **Close trigger** | Điều gì kết thúc và ai thực thi close? | Context shutdown → destroy method của pool |

Nên bổ sung **failure cleanup**: khi khởi tạo thành công được một phần, ai đóng các phần đã mở? Với resource có I/O không xác định, cần thêm deadline, cancellation, retry và giám sát.

### Owner khác creator

Đối tượng gọi constructor không nhất thiết phải tự đóng. Một factory có thể tạo resource rồi **chuyển quyền sở hữu** cho một component quản lý khác. Tuy nhiên việc chuyển quyền phải rõ ràng: từ thời điểm transfer thành công, creator không được tùy tiện close nữa, còn bên nhận phải đảm bảo cleanup.

Ví dụ:
- Method `@Bean` tạo một client và trả nó cho Spring IoC container. Thông thường container quản lý destruction của bean singleton.
- Factory trả một `InputStream` cho code gọi. Theo contract Java thông thường, caller nhận trách nhiệm close nếu không có tuyên bố khác.
- Pool tạo connection vật lý, nhưng code nghiệp vụ nhận một lease. Khi gọi `Connection.close()` trên một connection lấy từ pool, thực tế thường là **trả handle về pool**, không đóng toàn bộ pool.

### Owner có thể là một đối tượng bao lớn hơn

Ownership thường tạo thành cây:

~~~text
JVM / tiến trình
  |
  +-- Spring ApplicationContext
       |
       +-- Singleton bean: Connection Pool (owner)
       |      +-- các kết nối vật lý (pool quản lý)
       |      +-- request A: JDBC Connection lease (request sở hữu lease)
       |      +-- request B: JDBC Connection lease (request sở hữu lease)
       |
       +-- Singleton bean: HTTP client (owner)
       |      +-- request: response stream (operation sở hữu handle)
       |
       +-- SmartLifecycle consumer (owner của subscription/worker)
       |      +-- mỗi delivery: processing context / ack handle
       |
       +-- Controller/Service (borrower của các singleton trên)
~~~

Đây là sơ đồ **quyền sở hữu**, không phải sơ đồ kế thừa class Java hay bean graph một-một. Một Java object có thể chỉ là wrapper, còn resource thật nằm ở thư viện hoặc server ngoài.

## 3. Thời hạn sống: không có một scope áp dụng cho mọi resource

### 3.1. Phân loại theo lifetime

| Tài nguyên | Lifetime đề xuất điển hình | Owner phù hợp | Người sử dụng |
| --- | --- | --- | --- |
| `DataSource` / connection pool | Theo ApplicationContext | Bean do Spring/auto-configuration quản lý | Service, repository, transaction manager |
| HTTP client tái sử dụng | Theo application hoặc client bean | Bean singleton / cấu hình client | Nhiều request, task |
| `ExecutorService` tự tạo | Theo bean owner hoặc worker lifecycle | Bean quản lý executor | Các task được submit |
| Kafka consumer / message listener container | Theo SmartLifecycle component | Framework container / listener bean | Handler nhận message |
| JDBC `Connection` mượn | Theo operation/transaction | Caller hoặc transaction manager | Câu truy vấn hiện tại |
| `InputStream` / `Files.lines` | Theo đoạn đọc file | Scope có `try-with-resources` | Parser xử lý file |
| HTTP response body/stream | Theo một outbound request | Code nhận response hoặc abstraction client | Response parser |
| Temporary file | Đến khi hoàn tất job/retention | Job/component tạo file | Các bước job |
| Per-request upload buffer | Theo request hoặc task chuyển tiếp | Framework/handler theo API | Request handler |
| Scheduled task handle | Theo lần đăng ký task | Component đăng ký | Scheduler |
| Socket session | Theo kết nối | Server/session manager | Handler từng message |
| Bean `@Scope("prototype")` có resource | Theo người nhận instance | Caller nhận prototype sau khi tạo | Một operation |
| DB server, topic, cloud bucket bên ngoài | Ngoài JVM; có lifetime riêng | Hệ thống quản trị hạ tầng | Ứng dụng là client |

Đây là định hướng, không phải các luật bất biến. Một HTTP client có thể do framework sở hữu; một file tạm có thể cần sống qua nhiều request cho tới khi job hoàn thành. Quan trọng là **lifetime phù hợp với ngữ cảnh nghiệp vụ và được diễn đạt bằng API/ownership rõ ràng**.

### 3.2. “Ai đóng?” phải tách khỏi “ai dùng?”

Một service được inject `DataSource` thường **không sở hữu pool**, nên không được làm:

~~~java
// Sai ý tưởng: service mượn pool nhưng tự đóng pool chung.
((AutoCloseable) dataSource).close();
~~~

Đây là pseudocode minh họa lỗi: không phải mọi `DataSource` implement `AutoCloseable`; ép kiểu rồi đóng cũng có thể gây lỗi. Quan trọng hơn, pool được chia sẻ giữa nhiều component và owner của pool phải quyết định thời điểm đóng.

Ngược lại, một `InputStream` được mở trong method có lifetime rất ngắn:

~~~java
try (InputStream in = Files.newInputStream(path)) {
    // Đọc file ở đây.
}
~~~

Đây là đoạn minh họa cần import `java.io.InputStream`, `java.nio.file.Files` và biến `path`. Tại cuối block, caller của `Files.newInputStream` đóng stream kể cả có exception. Đừng hoãn việc đóng stream tới `ApplicationContext.close()`.

## 4. Bean scope và resource lifetime: liên quan nhưng không đồng nhất

Spring hỗ trợ nhiều scope. Phải biết **khi nào container tạo bean và khi nào nó cam kết gọi destruction**.

| Scope của bean | Số lượng/lifetime điển hình | Destruction do Spring quản lý? | Lưu ý resource |
| --- | --- | --- | --- |
| `singleton` (mặc định) | Một bean instance trên mỗi Spring container/bean definition | Có, với singleton do container sở hữu | Thường phù hợp pool/client chia sẻ |
| `prototype` | Tạo instance khi có yêu cầu | **Không tự gọi destroy callback cho từng prototype sau khi bàn giao** | Caller phải tự cleanup |
| `request` (Web) | Một instance theo HTTP request | Được web scope quản lý khi request kết thúc, trong ngữ cảnh hỗ trợ | Không giữ connection lâu hơn request |
| `session` (Web) | Một instance theo HTTP session | Phụ thuộc vòng đời session/web scope | Không giữ socket/JDBC connection sống cả session một cách vô ý |
| `application` (Servlet web scope) | Theo ServletContext | Do scope quản lý theo web app | Không đánh đồng với singleton trong nhiều context |
| Custom scope | Theo contract tùy biến | Phụ thuộc implementation của Scope | Tự kiểm chứng destruction callback |

**Quan trọng nhất:** Spring Framework nêu rõ bean `prototype` được tạo, cấu hình và bàn giao, nhưng container **không quản lý toàn bộ lifecycle sau đó**: configured destroy callbacks không được tự gọi cho từng prototype. Nếu prototype chứa resource, bên nhận phải chịu trách nhiệm đóng hoặc dùng một cơ chế tracking riêng.

### Một prototype inject vào singleton chỉ được lấy lúc inject

~~~java
@Component
class SingletonWorker {
    private final PerOperationResource resource;

    SingletonWorker(PerOperationResource resource) {
        this.resource = resource;
    }
}
~~~

Đây là đoạn minh họa không độc lập. Nếu `PerOperationResource` có prototype scope, việc constructor inject vào singleton thông thường chỉ tạo/lấy prototype **tại lúc singleton được tạo**. Nó không tự biến thành một prototype mới cho mỗi method call.

Khi cần mỗi operation một instance, dùng `ObjectProvider<PerOperationResource>`, factory riêng hoặc scoped proxy thích hợp; **sau khi lấy instance prototype có resource, hãy xác định cách đóng nó**. `ObjectProvider.getObject()` chỉ lấy instance, không tự thêm try-with-resources nếu type không hỗ trợ `AutoCloseable`.

### Scope request không đồng nghĩa giữ resource tới hết request là tốt nhất

Ngay cả khi request scope có destruction callback, một file stream hay JDBC connection chỉ cần dùng trong 5 ms nên đóng sớm tại cuối operation. Chờ tới hết request có thể làm cạn pool dưới tải cao. Chọn lifetime **ngắn nhất đủ đáp ứng mục đích**.

### Spring singleton khác Java static singleton

Singleton của Spring là một instance theo bean definition **trong một container**, không mặc định là một singleton toàn JVM. Nếu test tạo nhiều context hoặc ứng dụng có parent/child contexts, có thể có nhiều bean singleton cùng class. Một biến `static` dùng chung giữa các context có lifetime JVM và có thể bị close nhầm khi một context đóng.

## 5. Quy tắc quản lý tài nguyên trong một method

**Người mở hoặc mượn một handle cho operation thường phải trả handle ở cuối operation**, trừ khi contract nói rõ transaction/framework đang quản lý nó.

### 5.1. Try-with-resources cho tài nguyên theo operation

~~~java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
~~~

Đoạn trên chưa độc lập vì `path` và `process` là placeholder của ứng dụng; cần import `BufferedReader` và `Files`. Pattern chính xác là **mở → sử dụng → close tại đúng lexical scope**. Java gọi `AutoCloseable.close()` khi thoát block kể cả có exception.

Nếu `close()` cũng ném lỗi trong khi thân block đã ném lỗi, Java giữ lỗi chính và gắn lỗi đóng vào danh sách `suppressed exceptions`. Không nên bắt tất cả exception rồi bỏ qua, vì như vậy sẽ che rò tài nguyên.

### 5.2. JDBC connection mượn từ pool

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement stmt =
             connection.prepareStatement("select id from users where id = ?")) {
    stmt.setLong(1, userId);
    try (ResultSet rs = stmt.executeQuery()) {
        if (rs.next()) {
            return rs.getLong(1);
        }
        return null;
    }
}
~~~

Đây là **đoạn minh họa trong DAO không độc lập**, cần biến `dataSource`, `userId`, import các JDBC type và kiểu trả về `Long`. Caller đóng `ResultSet`, statement và connection handle ở cuối operation. Với một pool như HikariCP, close trên pooled connection **thường trả lease về pool**, không đóng toàn bộ pool.

**Cảnh báo về `@Transactional`:** nếu Spring transaction manager/JdbcTemplate đang quản lý connection đã bind với transaction, không tự can thiệp đóng connection mà framework sở hữu. Ưu tiên `JdbcTemplate`, JPA hoặc abstraction transaction tương ứng thay vì trộn raw `DataSource.getConnection()` với connection do Spring transaction đồng bộ. Trong tầng có framework quản lý, cần tuân thủ contract trả handle/release của framework, không áp một quy tắc close máy móc.

### 5.3. HTTP response và stream

Nếu thư viện HTTP trả `Response` hoặc body dạng stream, hãy đọc Javadoc để biết ai phải close. Với streaming HTTP, việc không close có thể giữ connection khỏi pool; ngược lại, đóng toàn bộ HTTP client chia sẻ sau mỗi request sẽ phá lifetime của các request khác.

Nói cách khác: **đóng response/lease theo request; đóng client/pool theo application** (nếu client thuộc sở hữu của application).

## 6. Spring sở hữu tài nguyên ở cấp bean như thế nào?

### 6.1. Tạo và trao quyền sở hữu cho container

~~~java
@Configuration
class ClientConfig {

    @Bean(destroyMethod = "close")
    SharedRemoteClient sharedRemoteClient() {
        return new SharedRemoteClient();
    }
}
~~~

Đoạn này minh họa configuration, không độc lập: cần `SharedRemoteClient` và các import. Khi bean là singleton do Spring quản lý, Spring gọi destroy method của bean khi container đóng theo đường bình thường.

Trong Java configuration, `@Bean` mặc định còn có cơ chế **suy luận destroy method**: public `close()` hoặc `shutdown()` có thể được tự nhận diện, kể cả `AutoCloseable` / `Closeable`. Việc chỉ định `destroyMethod = "close"` khiến hợp đồng sở hữu explicit hơn. Không nên vừa gọi `close()` thủ công ở nhiều borrower, vừa dựa vào Spring đóng lại mà không có idempotence.

### 6.2. Resource được mượn từ bên ngoài container

Đôi khi một factory trả về object **do hệ thống khác sở hữu**. Nếu đăng ký object đó làm `@Bean`, mặc định Spring có thể suy luận một method `close()` và **đóng nhầm tài nguyên được mượn** khi context kết thúc.

Nếu contract rõ Spring chỉ được sử dụng nhưng không được đóng object này:

~~~java
@Bean(destroyMethod = "")
ExternalOwnedClient borrowedExternalClient() {
    return externalSystem.client();
}
~~~

Đây là đoạn minh họa, chưa độc lập; `externalSystem` và `ExternalOwnedClient` là đối tượng giả định. `destroyMethod = ""` tắt suy luận custom destroy method trên `@Bean`. Nó **không vô hiệu hóa mọi dạng destruction**, ví dụ callback từ `DisposableBean` hoặc annotation destroy riêng nếu bean có. Phải kiểm tra toàn bộ hợp đồng khi giao một object ngoài cho container.

Trong nhiều trường hợp, cách tốt hơn là **không đăng ký object mượn như bean sở hữu**, mà tạo một adapter/wrapper có contract lifecycle rõ. Điểm quyết định là ai chịu trách nhiệm close thực tế, không phải chỉ việc đặt annotation.

### 6.3. @PreDestroy, DisposableBean, destroyMethod

Các lựa chọn phổ biến:

- `@PreDestroy`: callback trong class bean, dùng `jakarta.annotation.PreDestroy` trên Spring Boot 3.x.
- `DisposableBean.destroy()`: interface cụ thể của Spring, phù hợp khi cần contract Spring trực tiếp.
- `@Bean(destroyMethod = "close")`: chỉ định method đóng ở bean factory, tiện cho class từ thư viện.
- `AutoCloseable.close()`: contract Java cho đối tượng có thể đóng, kết hợp try-with-resources hoặc destroy method inference.

Chúng không hoàn toàn thay thế nhau. Nếu cấu hình nhiều callback khác nhau cho cùng bean, chúng có thể được gọi theo thứ tự khác nhau; tránh mỗi callback đều tự close resource gốc và vô tình double-close. Ưu tiên **một đường cleanup được sở hữu rõ và gọi lại an toàn**.

### 6.4. Không dùng finalize hoặc System.gc để bảo đảm đóng

Không dựa vào garbage collector hoặc finalizer để giải phóng handle hữu hạn đúng thời điểm. GC phụ thuộc áp lực bộ nhớ, không phụ thuộc số connection còn lại trong pool; một JVM có thể hết connection/file descriptor trước khi GC thu hồi object. Java hiện đại ưu tiên `AutoCloseable`, lexical scope, lifecycle callback và cơ chế close tường minh.

## 7. Ví dụ chạy được: owner sống theo context, lease sống theo operation

Ví dụ này tạo một **client giả lập** với hai cấp tài nguyên:

- `SharedClient`: singleton bean **được ApplicationContext sở hữu** và đóng khi context đóng.
- `Lease`: handle mượn client, **được operation sở hữu** và đóng ngay khi kết thúc xử lý.
- `ApplicationRunner`: dùng client nhưng **không sở hữu quyền đóng client**.
- `main()`: mở Spring context bằng `SpringApplication.run`, sau đó đóng context bằng `try-with-resources` khi hoàn tất bài demo.

Mã không mở socket thật để stdout xác định. Đây là mô hình ownership, không phải implementation connection pool production.

### 7.1. Tạo Maven project Java 17+

~~~text
resource-ownership-demo/
├── pom.xml
└── src/main/java/com/example/ownership/
    └── ResourceOwnershipApplication.java
~~~

**Tệp pom.xml:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>resource-ownership-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot 3.5.16 là một version 3.5.x đã phát hành. Ví dụ nhằm học cơ chế ở nhánh 3.5; với hệ thống production cần chọn nhánh hiện được hỗ trợ và kiểm tra API theo version thực dùng.

### 7.2. File Java đầy đủ

**Tệp src/main/java/com/example/ownership/ResourceOwnershipApplication.java:**

~~~java
package com.example.ownership;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ResourceOwnershipApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ResourceOwnershipApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            SharedClient client = context.getBean(SharedClient.class);
            System.out.println(
                    "07_MAIN_OWNER_STILL_OPEN=" + !client.isClosed());
        }

        System.out.println("09_CONTEXT_CLOSED");
    }

    // ApplicationContext là owner của singleton SharedClient.
    @Bean(destroyMethod = "close")
    SharedClient sharedClient() {
        return new SharedClient();
    }

    // Runner chỉ sử dụng SharedClient; nó không gọi client.close().
    @Bean
    ApplicationRunner demo(SharedClient client) {
        return args -> {
            System.out.println("02_RUNNER_BEGIN");

            // Operation này là owner của Lease.
            try (Lease lease = client.borrow()) {
                lease.execute();
            }

            System.out.println("06_RUNNER_END");
        };
    }

    static final class SharedClient implements AutoCloseable {
        private boolean closed;
        private int activeLeases;

        SharedClient() {
            System.out.println("01_SHARED_CLIENT_CREATED");
        }

        synchronized Lease borrow() {
            ensureOpen();
            activeLeases++;
            System.out.println(
                    "03_LEASE_ACQUIRED active=" + activeLeases);
            return new Lease(this);
        }

        synchronized void use() {
            ensureOpen();
            System.out.println("04_LEASE_USED");
        }

        synchronized void release() {
            if (activeLeases <= 0) {
                throw new IllegalStateException("release without borrow");
            }
            activeLeases--;
            System.out.println(
                    "05_LEASE_RELEASED active=" + activeLeases);
        }

        synchronized boolean isClosed() {
            return closed;
        }

        private void ensureOpen() {
            if (closed) {
                throw new IllegalStateException("client already closed");
            }
        }

        @Override
        public synchronized void close() {
            if (closed) {
                return; // Idempotent shutdown.
            }
            if (activeLeases != 0) {
                throw new IllegalStateException(
                        "cannot close with active leases="
                                + activeLeases);
            }
            closed = true;
            System.out.println("08_SHARED_CLIENT_CLOSED");
        }
    }

    static final class Lease implements AutoCloseable {
        private final SharedClient owner;
        private final AtomicBoolean closed = new AtomicBoolean();

        Lease(SharedClient owner) {
            this.owner = owner;
        }

        void execute() {
            if (closed.get()) {
                throw new IllegalStateException("lease already closed");
            }
            owner.use();
        }

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                owner.release(); // Trả lease, KHÔNG close owner.
            }
        }
    }
}
~~~

Mã là **một tệp Java đầy đủ** trong Maven project trên, không đòi database hay server HTTP. `SharedClient` không có annotation `@Component` và được đăng ký **một lần** qua `@Bean`; `Lease` không phải bean và do operation tự sở hữu.

**Phân tích ownership:**

| Đối tượng | Ai tạo? | Ai sở hữu? | Khi nào đóng? |
| --- | --- | --- | --- |
| `ConfigurableApplicationContext` | `SpringApplication.run` | `main()` trong chương trình CLI demo | Cuối `try-with-resources` ở main |
| `SharedClient` | Factory method `@Bean` | Spring context | Spring gọi `close()` khi đóng context |
| `Lease` | `SharedClient.borrow()` | Block operation của runner | Cuối `try-with-resources` của runner |
| `ApplicationRunner` | Spring context | Spring context | Runner không tự close SharedClient |
| Tài nguyên server ngoài | Không được tạo trong demo | Hệ thống ngoài | Không thuộc quyền close của demo |

Giả lập này tách rạch ròi **close một lease** với **close owner**. Khi `Lease.close()` gọi `owner.release()`, nó chỉ trả handle về cấp quản lý; nó không đóng SharedClient. Spring context sẽ đóng SharedClient sau khi các operation hoàn tất.

`SharedClient.close()` kiểm tra `activeLeases`. Trong demo, nếu một lease bị giữ quá lâu, việc đóng owner sẽ báo lỗi để không che tình trạng còn handle đang mượn. Trong production, owner thường cần graceful drain với timeout, chính sách hủy task và metrics; chỉ ném lỗi trong destroy method không phải phương án shutdown hoàn chỉnh.

### 7.3. Biên dịch và chạy

Tại thư mục chứa pom.xml:

~~~bash
mvn package
java -jar target/resource-ownership-demo-0.0.1-SNAPSHOT.jar
~~~

Hoặc:

~~~bash
mvn spring-boot:run
~~~

**Các dòng do chính chương trình in ra** theo thứ tự sau (banner, Maven output và Spring Boot logs có thể chen giữa):

~~~text
01_SHARED_CLIENT_CREATED
02_RUNNER_BEGIN
03_LEASE_ACQUIRED active=1
04_LEASE_USED
05_LEASE_RELEASED active=0
06_RUNNER_END
07_MAIN_OWNER_STILL_OPEN=true
08_SHARED_CLIENT_CLOSED
09_CONTEXT_CLOSED
~~~

Giải thích trình tự:

1. `SharedClient` được Spring tạo một lần trong giai đoạn chuẩn bị singleton.
2. `ApplicationRunner` được Boot gọi sau khi context refresh.
3. Runner mượn Lease, active leases tăng 0 → 1.
4. Runner dùng Lease, không đóng owner.
5. Khi thoát try-with-resources, Lease trả lại, active leases giảm 1 → 0, kể cả nếu code trong block ném exception.
6. Runner hoàn tất; SharedClient **vẫn còn mở**.
7. `SpringApplication.run` trả về; main xác minh owner vẫn sống.
8. Main đóng context ở cuối block. Spring gọi destroyMethod `close` của singleton, owner được đóng.
9. Main tiếp tục sau khi context đóng.

**Điểm cần nhớ:** method tạo bean trả về `SharedClient`, nhưng chính **context** sở hữu trách nhiệm destruction. Runner nhận reference dùng chung, không được gọi `client.close()` sau một lượt xử lý.

### 7.4. Đọc output một cách đúng đắn

Nếu nhìn vào log Spring Boot “Started...” trước các dòng runner, đừng kết luận JVM đã xong toàn bộ startup. `ApplicationRunner` thực thi sau refresh và trước Ready. Demo in marker khi runner chạy và khi context đóng rõ ràng, nên dễ phân biệt lifecycle startup, operation và shutdown.

Ví dụ không có web server; vì vậy chương trình chủ động đóng context sau runner. **Không áp dụng nguyên cách đóng context ngay sau `run()` vào web service cần sống lâu dài**: nó sẽ khiến server dừng ngay.

### 7.5. Thử tình huống lỗi

- Bỏ `try-with-resources` của Lease rồi mượn mà không close: đến lúc context đóng, `activeLeases` còn dương, owner phát hiện và báo lỗi. Đây là một cơ chế phát hiện rò, không thay thế cleanup thực.
- Gọi `client.close()` bên trong runner sau khi đã trả Lease: caller mượn đã đóng owner quá sớm. Một operation khác sẽ nhận “client already closed”.
- Đổi `Lease.close()` thành gọi `owner.close()`: ownership bị sai, và có thể gây lỗi khi nhiều Lease đang hoạt động.
- Gọi `Lease.close()` hai lần: `AtomicBoolean` bảo vệ việc release một lần. Dù idempotence tốt, vẫn phải đặt close tại đúng scope.
- Trong một ứng dụng thật, thêm test về close khi có nhiều request đồng thời, thời hạn drain, ngoại lệ trong close và các trường hợp context fail khi startup.

## 8. Trách nhiệm trong đường lỗi và shutdown

### 8.1. Mở một phần nhưng khởi tạo thất bại

Giả sử tạo một client cần ba bước: mở socket, authenticate rồi subscribe. Nếu subscribe lỗi, owner phải đóng socket đã mở trước đó; không thể chỉ chờ destruction callback cho bean chưa tạo thành công.

Pattern minh họa:

~~~java
Socket socket = new Socket();
try {
    socket.connect(address, timeoutMillis);
    authenticate(socket);
    subscribe(socket);
    return socket; // Chuyển ownership nếu factory thành công.
} catch (Exception failure) {
    try {
        socket.close();
    } catch (Exception closeFailure) {
        failure.addSuppressed(closeFailure);
    }
    throw failure;
}
~~~

Đây là **đoạn minh họa không độc lập**: `address`, `timeoutMillis`, `authenticate` và `subscribe` là các API/biến giả định. Điều quan trọng là rollback partial resource trước khi rethrow. Nếu factory đã chuyển quyền sở hữu thành công, caller/container mới chịu trách nhiệm đóng sau đó.

### 8.2. Shutdown bình thường của Spring

Trên đường đóng context chuẩn:

~~~text
Yêu cầu ApplicationContext.close()
  |
  +-- ContextClosedEvent
  +-- Dừng Lifecycle / SmartLifecycle bean thích hợp
  +-- Thực hiện destroy callbacks của singleton
  |     +-- @PreDestroy
  |     +-- DisposableBean.destroy()
  |     +-- custom @Bean(destroyMethod = "...")
  |
  +-- Hoàn tất đóng context
~~~

Thứ tự khái quát này giúp thiết kế: **ngừng phát sinh công việc mới trước khi đóng resource mà các công việc đang dùng**. Nếu consumer phụ thuộc pool, consumer nên stop và drain trước khi pool bị close. Có thể dùng `SmartLifecycle.getPhase()` và dependency relationships để phối hợp.

Không đồng nghĩa mọi trường hợp đều có đủ callback: JVM bị `SIGKILL`, crash, mất điện hoặc startup lỗi quá sớm có thể bỏ qua một phần lifecycle. External resource cần TTL, lease expiry, timeout và cơ chế phục hồi phù hợp.

### 8.3. SmartLifecycle cho tài nguyên hoạt động nền

Một executor hoặc message consumer có hai giai đoạn:
- **stop**: ngừng nhận việc mới và đợi work đang chạy (trong thời hạn cho phép);
- **destroy/close**: giải phóng resource sau khi work đã dừng.

`SmartLifecycle.stop(Runnable)` cho phép thông báo cho lifecycle processor **sau khi stop thật sự hoàn tất**. Gọi callback ngay sau `ExecutorService.shutdown()` trong khi các task vẫn chạy sẽ báo hoàn tất quá sớm. Ngược lại, không gọi callback sẽ khiến Spring có thể chờ tới timeout của phase.

Với Spring Boot, có thể cấu hình:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Property này giới hạn thời gian processor chờ từng phase; nó không cưỡng chế task/network tự đóng. Resource owner vẫn phải có timeout và chính sách force-stop/cancellation riêng.

### 8.4. Đừng đóng tài nguyên theo thời điểm event sai

`ApplicationStartedEvent` xảy ra sau refresh nhưng trước runner; `ApplicationReadyEvent` sau runner và trước readiness event. Chúng là **mốc khởi động**, không phải trigger đóng client. `ContextClosedEvent` là mốc đóng context, nhưng listener của event đó thường chạy **trước** destroy callbacks; dùng nó để phối hợp ngừng nhận work, không phải nơi mọi borrower cạnh tranh đóng cùng một pool.

## 9. Ownership trong dependency injection và nhiều context

### 9.1. Inject dependency không trao quyền close

Nếu service nhận một singleton qua constructor injection, nó thường chỉ nhận **quyền sử dụng**. Nó không trở thành owner:

~~~java
@Service
class OrderService {
    private final SharedClient client;

    OrderService(SharedClient client) {
        this.client = client;
    }

    void execute() {
        // Sử dụng SharedClient theo API của nó.
        // Không gọi client.close() ở đây.
    }
}
~~~

Đây là đoạn minh họa không độc lập: cần các import, implementation và contract tương ứng. Rule này tránh lỗi một bean dùng chung bị dừng bởi một borrower ngắn hạn.

### 9.2. Prototype cần người nhận quản lý

Một bean prototype chứa resource là trường hợp dễ bị rò:

~~~java
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
@Bean
PerJobHandle perJobHandle() {
    return new PerJobHandle();
}
~~~

Đây là đoạn minh họa config, không độc lập. Spring không tự gọi destruction callback cho mỗi prototype sau khi bàn giao. Nếu một job lấy instance từ `ObjectProvider<PerJobHandle>`, job cần đóng handle hoặc giao trách nhiệm đó cho một owner khác. Không chỉ dựa vào annotation `@PreDestroy` trên prototype rồi giả định Spring sẽ gọi khi ApplicationContext.close().

Tốt hơn trong nhiều trường hợp là inject một **factory singleton** tạo `AutoCloseable` handle cho từng operation và sử dụng try-with-resources; cách đó khiến ownership hiển thị ngay trong code.

### 9.3. Parent và child ApplicationContext

Trong hệ thống có nhiều context:
- Parent context có thể sở hữu một pool dùng chung.
- Child context có thể tạo service, controller hoặc consumer riêng.
- Đóng child context không nên đóng tài nguyên do parent sở hữu, vì child khác có thể đang sử dụng.
- Một `static` pool dùng chung nhiều context không tự biến thành resource do một context bất kỳ sở hữu.

Cần ghi rõ scope owner **theo context nào**, không viết chung “Spring quản lý” rồi bỏ qua ranh giới.

### 9.4. Reload, test và multiple contexts

Test dùng `@SpringBootTest` có thể cache context giữa các test; không nên tự đóng global client từ một test case khi context còn được dùng lại. Nếu test tự tạo `ConfigurableApplicationContext`, nên đóng nó sau khi test hoàn tất; nếu Spring TestContext sở hữu, để framework quản lý.

Khi có nhiều context trong cùng JVM, số bean singleton hoặc pool có thể lớn hơn một. Vì vậy **giới hạn tài nguyên theo context** và số lần tạo context ảnh hưởng thực tế tới tài nguyên file descriptor, kết nối DB và memory.

## 10. Hợp đồng ownership khi chuyển qua async/thread

Một method có thể kết thúc trước khi công việc bất đồng bộ sử dụng resource xong. Ví dụ:

~~~java
try (InputStream in = Files.newInputStream(path)) {
    executor.submit(() -> consume(in));
}
~~~

Đây là **pseudocode minh họa**, với biến `path`, `executor` và method `consume` chưa định nghĩa. Block thoát ngay sau `submit()`, stream bị đóng trước khi task nền kịp đọc. Đây là lỗi **lifetime của resource ngắn hơn lifetime của borrower**.

Các cách thiết kế đúng hơn:

1. Để task **tự mở và đóng** InputStream bên trong task, vì task là owner của operation.
2. Chuyển ownership bằng một abstraction explicit và bảo đảm người nhận close trong `finally`; sender không đóng sau transfer thành công.
3. Đợi task hoàn thành bên trong block nếu thực sự cần giữ stream do caller sở hữu, có timeout và xử lý interruption.
4. Nếu dùng resource dùng chung như HTTP client/pool, task chỉ mượn client; không close owner ở cuối task.
5. Với executor do ứng dụng sở hữu, stop nhận task mới, đợi in-flight task, rồi mới đóng pool/client mà task sử dụng.

**Quy tắc:** resource phải sống ít nhất đến khi **mọi borrower hợp lệ đã xong**, nhưng không nên sống lâu hơn cần thiết. Điều này bao gồm luồng async, callback, stream lazily evaluated và reactive subscription.

### Ownership trong reactive/streaming

Một Publisher/Flux có thể được tạo trong request nhưng thực tế được subscribe muộn. Không dùng lexical try-with-resources để đóng resource trước khi pipeline hoàn thành. Hãy dùng các API quản lý resource theo lifecycle subscription, ví dụ `using` / `usingWhen` trong thư viện reactive phù hợp, và tuân thủ ownership contract của HTTP client đang dùng.

Đừng mặc định một entity được emit xong là HTTP connection đã được release; điều đó phụ thuộc cách response body/stream được consume và API cụ thể.

## 11. Chẩn đoán rò và đóng quá sớm

| Dấu hiệu | Khả năng | Kiểm tra |
| --- | --- | --- |
| Pool hết connection dù RPS chưa cao | Lease không được trả, transaction quá dài | Active/idle/pending connections, stacktrace của borrower |
| “Connection is closed” ngẫu nhiên | Borrower đóng owner hoặc lease dùng sau close | Log lifecycle, owner/lease ID |
| Thread tiếp tục chạy sau shutdown | Executor không được đóng hoặc stop không đợi tasks | Thread dump, executor state, shutdown callback |
| Mở file lỗi “too many open files” | Stream/channel không close | File descriptor count, đường lỗi |
| Không thấy `@PreDestroy` chạy cho prototype | Spring không tự destroy prototype | Xác định scope và caller chịu trách nhiệm cleanup |
| Nhiều pool sau mỗi integration test | Mỗi context tạo singleton riêng | Context cache, test lifecycle, bean creation |
| Một request khiến toàn service lỗi | Shared pool/client bị đóng bởi request | Tìm `close()` trong code borrower |
| Shutdown bị treo | Có work đang giữ resource, callback không hoàn tất | Timeout, in-flight count, SmartLifecycle |
| Memory còn tăng dù close connection | Buffer/cache/listener giữ references | Heap dump, subscription registration, callbacks |
| Vừa close vừa tạo resource mới | Start/stop race, thiếu closing state | Đồng bộ resource ownership và generation |
| JVM tắt mà cloud job vẫn chạy | External job không thuộc lifecycle của JVM | Remote lease/TTL/cancel API, contract hệ thống ngoài |

**Quan sát tối thiểu** của một resource owner production nên có: current state (OPEN/CLOSING/CLOSED), active borrowers, create/close count, pending tasks, thời gian drain và lỗi cleanup. Không log password/token/credential trong các sự kiện lifecycle.

### Close đúng không bảo đảm không có leak

Một client có thể đã close nhưng từng response body/lease bị giữ lâu hơn dự kiến, khiến tài nguyên không được tái sử dụng trước shutdown. Vì vậy cần đo cả **owner lifetime** lẫn **borrower lifetime**, không chỉ một boolean “closed”.

## 12. Chọn công cụ quản lý đúng cho từng loại tài nguyên

| Nhu cầu | Công cụ ưu tiên | Lý do |
| --- | --- | --- |
| File/stream/handle cục bộ trong method | `try-with-resources` | Cleanup khi thoát lexical scope, kể cả exception |
| Client/pool dùng chung nhiều service | Singleton `@Bean` + destroy callback | Context quản lý lifetime và đóng lúc shutdown |
| Một resource gắn với bean riêng | `@PreDestroy` hoặc configured destroy method | Bean chịu trách nhiệm giải phóng |
| Worker/consumer cần start/stop có thứ tự | `SmartLifecycle` | Điều phối phase, graceful stop |
| JDBC transaction | `@Transactional`, `JdbcTemplate`, transaction manager | Framework quản lý transaction/connection |
| Prototype có resource | Factory + `AutoCloseable` handle và caller close | Prototype không được tự destroy theo container |
| HTTP request scoped state | Request scope phù hợp, close operation càng sớm càng tốt | Tránh giữ connection qua request dài |
| Asynchronous job | Job/task owner, completion callback / future cleanup | Lifetime theo công việc, không theo method đã return |
| Object từ API ngoài được mượn | Không đóng owner; adapter explicit | Tránh container suy luận destroy sai |
| External durable resource | Contract provisioning/lease/TTL độc lập | JVM không sở hữu toàn bộ hệ thống ngoài |

Không nên chọn `@PreDestroy` cho mọi thứ vì “dễ nhớ”. Cũng không nên dùng `try-with-resources` cho một singleton bean ngay trong method factory rồi trả object đã đóng. Mỗi cơ chế tương ứng một **ranh giới ownership/lifetime** khác nhau.

## 13. Các anti-pattern cần loại bỏ

### 13.1. Đóng pool dùng chung trong finally của request

~~~java
try {
    doWork(sharedDataSource);
} finally {
    closeTheWholePool(sharedDataSource); // Sai ownership.
}
~~~

Đây là pseudocode. Request chỉ mượn, không sở hữu toàn bộ pool. Sửa bằng cách giải phóng lease/transaction mà request thực sự sở hữu, để pool owner đóng pool cuối đời ứng dụng.

### 13.2. Trả resource đã đóng cho caller

~~~java
InputStream load(Path path) throws IOException {
    try (InputStream in = Files.newInputStream(path)) {
        return in; // Sai: caller nhận stream đã đóng.
    }
}
~~~

Đây là đoạn minh họa phương thức, cần import tương ứng. Nếu method chuyển quyền sở hữu stream cho caller, **không đóng trước khi trả**, và phải document “caller closes”. Tốt hơn nữa là method trả dữ liệu đã đọc (byte array / domain object) nếu dữ liệu nhỏ, để ẩn hoàn toàn ownership.

### 13.3. Giữ transaction connection cả session

Một HTTP session có thể kéo dài hàng chục phút hoặc lâu hơn. Giữ JDBC Connection trong session khiến pool cạn, kết nối stale và transaction vượt phạm vi cần thiết. Nên mở/mượn connection theo transaction ngắn, đóng/trả ngay sau unit of work.

### 13.4. Tự tạo executor ở mỗi callback

Nếu mỗi message đến đều gọi `Executors.newSingleThreadExecutor()` mà không quản lý close, số thread tăng không giới hạn. Thường nên inject một executor có ownership rõ hoặc dùng task executor do framework cấu hình, có quy trình shutdown xác định.

### 13.5. Dựa vào GC để đóng

File descriptor, socket và connection pool có hạn mức hữu hạn; chúng có thể hết trước khi GC chạy. Không dùng finalizer hoặc System.gc làm cleanup contract.

### 13.6. Double-close qua hai destroy callbacks

Nếu một bean vừa có `@PreDestroy` riêng, vừa cấu hình `@Bean(destroyMethod = "close")` và cả hai method đóng cùng resource, các callback khác nhau có thể chạy nối tiếp và double-close. Nên có một đường cleanup idempotent hoặc bỏ đăng ký dư thừa.

### 13.7. Đóng ngay trong ApplicationReadyEvent

Ready chỉ cho biết startup hoàn tất; nó không phải điểm kết thúc tài nguyên. Đóng pool/client ngay khi ready sẽ làm các request đến sau thất bại. Tài nguyên dùng chung thường cần sống tới lúc context đóng; việc ngừng nhận task mới nên gắn với shutdown lifecycle.

### 13.8. Chuyển ownership bất đồng bộ mơ hồ

Sender submit task rồi close stream, hoặc sender nghĩ task sẽ close nhưng task không có finally. Hãy làm hợp đồng chuyển giao một chiều, có thể test và ghi trong API.

## 14. Kiểm thử ownership, lifetime và failure path

### 14.1. Kiểm thử lease theo operation

Với `SharedClient` trong ví dụ:

~~~text
Client OPEN, active=0
borrow()             -> active=1
lease.execute()       -> thành công
lease.close()         -> active=0
lease.close() lần hai -> vẫn active=0
client.isClosed()     -> false
context.close()       -> client.isClosed() == true
~~~

Đây là **expected behavior** của implementation ví dụ, không phải một framework API tự in ra các dòng này.

### 14.2. Test đóng quá sớm

Cố tình close owner trước khi borrow:
- Borrow phải từ chối.
- Không cấp thêm lease sau CLOSE.
- Không có operation nào được dùng một owner đã đóng.

Với ứng dụng nhiều luồng, cần phối hợp close và borrow atomic, tránh race “check open → context close → create lease”. Demo dùng `synchronized` cho borrow, release và close để giữ state nhất quán.

### 14.3. Test rò tài nguyên

Borrow một lease nhưng không close, sau đó thử close owner. Demo báo lỗi vì active lease vẫn còn. Trong production, cần leak detection và policy: đợi drain, đặt deadline, cảnh báo và force-close khi cần, nhưng không bỏ qua ownership ambiguity.

### 14.4. Test lỗi giữa operation

Cho `lease.execute()` ném exception. Với `try-with-resources`, `lease.close()` vẫn chạy và trả handle. Phải kiểm tra cả trạng thái lease và active counter sau lỗi, không chỉ exception message.

### 14.5. Test startup fail một phần

Factory mở resource A, bước B thất bại. Kiểm tra A được close trong đường lỗi, dù bean chưa được đăng ký thành công để nhận destruction callback từ Spring.

### 14.6. Test nhiều context

Tạo và đóng hai context một cách độc lập. Kiểm tra mỗi context sở hữu đúng resource của mình và không đóng nhầm một resource bên ngoài được chia sẻ giữa contexts. Không dùng static mutable singleton làm owner khi không có giao thức bàn giao rõ.

### 14.7. Test shutdown khi còn task

Khi consumer đang xử lý message:
- Ngừng nhận task mới.
- Đợi in-flight tasks trong giới hạn phù hợp.
- Trả/đóng lease còn hoạt động.
- Cuối cùng đóng pool/client owner.
- Timeout phải có policy rõ và được ghi nhận.

### 14.8. Test forced termination

Giả lập process bị kill: callback Java có thể không chạy. Những tài nguyên ngoài như lock phân tán, lease cloud, message delivery cần TTL hoặc retry/recovery độc lập.

## 15. Checklist dùng khi thiết kế một resource mới

Dành cho code review, trả lời từng câu:

1. **Resource là gì?** Client/pool gốc hay chỉ là lease/handle?
2. **Ai tạo?** Constructor, @Bean, factory, thư viện, transaction manager hay hệ thống ngoài?
3. **Ai sở hữu?** Spring context, bean, operation, task, request hay external service?
4. **Ai mượn?** Có bao nhiêu borrower đồng thời? Borrower có được close owner không?
5. **Lifetime bắt đầu khi nào?** Context refresh, lần borrow, request bắt đầu hay subscription?
6. **Lifetime kết thúc khi nào?** End-of-block, completion, cancellation, session end, context close?
7. **Trigger cleanup nào?** try-with-resources, AutoCloseable, @PreDestroy, SmartLifecycle, lease expiry?
8. **Resource có thể được tạo một phần rồi lỗi không?** Rollback ở đâu?
9. **Nếu close bị gọi hai lần?** Có idempotent không? Callback có bị rơi không?
10. **Nếu close cạnh tranh với borrow?** Có lock/state machine để ngăn thao tác sau close không?
11. **Nếu async chạy lâu hơn method?** Ai giữ và cuối cùng trả resource?
12. **Nếu shutdown bị cưỡng bức?** Có TTL, deadline, recovery hoặc retry bên ngoài không?
13. **Có test resource count và timing không?** Test success, error, cancel, timeout và concurrent calls?
14. **Có thông tin nhạy cảm trong log không?** Không log credential/token theo resource lifecycle.
15. **Có ghi contract vào API không?** Ví dụ “caller must close response”, “client managed by Spring”.

Một thiết kế tốt khiến người đọc code có thể xác định owner và điểm đóng **mà không cần đoán**.

## 16. Câu hỏi ôn tập

**Câu 1:** Service được inject singleton DataSource có quyền đóng pool sau một request không?

**Trả lời:** Không, trừ khi chính service được giao quyền sở hữu pool một cách explicit. Service thường chỉ mượn API, còn bean/auto-configuration quản lý lifetime pool.

**Câu 2:** Ai đóng JDBC Connection mượn từ pool trong method không dùng Spring transaction abstraction?

**Trả lời:** Caller phải release handle đúng lúc, thường bằng try-with-resources. Đóng connection handle từ pool thường là trả lease về pool, không đóng pool.

**Câu 3:** Prototype bean có @PreDestroy có được Spring tự động gọi destruction khi context đóng không?

**Trả lời:** Không thể dựa vào điều đó. Spring không quản lý destruction của từng prototype sau khi bàn giao; caller cần cleanup riêng.

**Câu 4:** Bean singleton có public close và được khai báo bằng @Bean, nếu không ghi destroyMethod có thể bị Spring tự đóng không?

**Trả lời:** Có. Java config @Bean mặc định suy luận public close/shutdown làm destroy method. Nếu đó là borrowed external object, cần chú ý và điều chỉnh contract.

**Câu 5:** Vì sao try-with-resources quanh InputStream rồi submit task sử dụng stream là nguy hiểm?

**Trả lời:** Block của caller có thể thoát trước khi task dùng stream, khiến stream bị đóng sớm. Lifetime phải theo task hoặc caller phải chờ completion.

**Câu 6:** Client pool sống cùng ApplicationContext có đồng nghĩa mọi Connection phải sống cùng context không?

**Trả lời:** Không. Pool là owner dài hạn, mỗi connection lease có lifetime ngắn theo operation/transaction.

**Câu 7:** Nếu start tạo resource một phần rồi lỗi, có thể chờ @PreDestroy tự cleanup không?

**Trả lời:** Không. Bean có thể chưa được tạo thành công nên callback destroy không được đăng ký. Factory/owner phải rollback partial resource.

**Câu 8:** Khi context đóng, nên đóng consumer hay pool mà consumer cần trước?

**Trả lời:** Thông thường ngừng consumer và đợi in-flight work trước, sau đó đóng pool. Dùng lifecycle phase, dependency và graceful shutdown để điều phối.

**Câu 9:** Spring singleton có phải một object duy nhất toàn JVM không?

**Trả lời:** Không. Singleton có phạm vi theo container/bean definition; nhiều context có thể tạo nhiều singleton khác nhau.

**Câu 10:** Vì sao context đóng không chắc chắn giải phóng tài nguyên ngoài hệ thống?

**Trả lời:** JVM crash, SIGKILL hoặc mạng lỗi có thể bỏ qua callback. Resource ngoài cần cơ chế lease/TTL/retry/recovery riêng.

## 17. Bài tập thực hành

**Bài tập A — ownership table:** Liệt kê DataSource, JDBC Connection, HTTP client, HTTP response body, InputStream, ExecutorService và Kafka consumer trong dự án. Điền creator, owner, borrower, lifetime, close trigger và failure cleanup cho từng loại.

**Bài tập B — lease idempotent:** Chạy demo mục 7. Gọi `lease.close()` hai lần trong cùng operation, kiểm tra `activeLeases` không giảm dưới 0. Giải thích vì sao close lease không ảnh hưởng `SharedClient.isClosed()`.

**Bài tập C — rò lease:** Cố tình giữ lại một Lease tới khi context đóng. Quan sát owner từ chối đóng khi còn active lease. Đề xuất cơ chế drain có deadline cho production.

**Bài tập D — prototype resource:** Tạo prototype bean chứa handle AutoCloseable, lấy instance bằng `ObjectProvider` rồi close từ caller. Kiểm chứng Spring không tự đảm bảo destruction cho prototype đã bàn giao.

**Bài tập E — asynchronous lifetime:** Di chuyển thao tác đọc file vào `CompletableFuture`. Cố ý close stream quá sớm rồi sửa bằng cách cho task tự mở/đóng stream. Test normal, exceptional và cancellation paths.

**Bài tập F — bean được mượn:** Giả lập một client được tạo ngoài Spring và đăng ký bằng `@Bean`. So sánh default destroy inference với `@Bean(destroyMethod = "")`. Giải thích vì sao cần thêm quy tắc ownership nếu object còn có callback hủy khác.

**Bài tập G — graceful shutdown:** Tạo một worker SmartLifecycle mượn SharedClient. Chọn phase sao cho worker stop/drain trước khi bean client bị destroy; dùng timeout và kiểm tra số lease còn hoạt động tại thời điểm close.

## 18. Tài liệu tham khảo chính thức

- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html): singleton, prototype, web scope và prototype destruction.
- [Spring Framework — Bean Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): @PostConstruct, @PreDestroy, DisposableBean, SmartLifecycle, inferred close/shutdown.
- [Spring Framework — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): destroyMethod và cách Spring quản lý bean từ Java configuration.
- [Spring Boot 3.5 — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): ApplicationContext, shutdown hook và application events.
- [Spring Boot 3.5.16 — SpringApplication Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html): việc tạo context và shutdown hook.
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): try-with-resources, close và suppressed exceptions.

### Ghi nhớ cuối cùng

1. **Mỗi resource cần một owner rõ ràng.** Creator và user không nhất thiết là owner.
2. **Owner đóng resource gốc, borrower chỉ trả lease/handle.** Không đóng pool/chung trong một request.
3. **Lifetime phải khớp với phạm vi sử dụng**, không đơn giản khớp một annotation scope.
4. **Singleton Spring do context sở hữu** thường có destruction callbacks; **prototype đã bàn giao không tự được Spring destroy**.
5. **@Bean có inferred close/shutdown**; với external borrowed object phải tránh bàn giao quyền close không chủ ý.
6. **try-with-resources** dành cho tài nguyên theo operation; **bean destroy/SmartLifecycle** dành cho tài nguyên dài hạn và background activity.
7. **Trong failure path, cleanup phần đã mở** trước khi trả exception; không chờ context destroy bean chưa tạo thành công.
8. **Async cần lifetime theo task/stream/subscription**, không theo method đã return.
9. **Shutdown phải dừng borrower trước khi đóng owner**, có timeout và chính sách cho forced termination.
10. **Ownership là một contract có thể kiểm thử**: ai được close, khi nào, số handle active và hành vi khi lặp/đồng thời.
