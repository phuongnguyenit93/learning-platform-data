# Ảnh hưởng của private, final và khả năng chặn lời gọi trong Spring concurrency

Trong Spring Framework, khi một phương thức được đánh dấu **@Async**, việc chạy bất đồng bộ thường không xảy ra nhờ bản thân annotation hay vì từ khóa của Java làm đổi luồng. Ở chế độ mặc định **proxy-based**, Spring tạo một **proxy** đứng trước bean. Một lời gọi đi **qua proxy** mới có cơ hội được bộ chặn (interceptor/advice) nhận diện, gửi tác vụ sang **TaskExecutor** và trả về cho caller theo hợp đồng async.

Vì vậy, **private**, **final**, kiểu proxy và **đường đi của lời gọi** ảnh hưởng trực tiếp đến khả năng chặn lời gọi:

- **private method** không thể được gọi qua giao diện public của proxy và không thể bị class-based proxy ghi đè để chặn.
- **final method** không thể bị **class-based (CGLIB) proxy** ghi đè. Nhưng **JDK interface proxy** có thể chặn một lời gọi qua **interface**, kể cả khi phương thức triển khai ở target được khai báo **final**; đây là điểm cần phân biệt.
- **final class** không thể được subclass bằng CGLIB. Tuy vậy, một **final class triển khai interface** vẫn có thể được bao bởi **JDK interface proxy**, nếu cấu hình và lời gọi đi qua interface.
- **self-invocation**, chẳng hạn **this.work()** hoặc gọi tên method không có this ngay trong bean, thường **bỏ qua proxy**, dù work() là public và không final.
- Một **public method có thể chặn** không có nghĩa tất cả lời gọi vào nó đều được chặn: phải xem caller giữ **proxy hay target**.

Bài Knowledge thuộc nhóm **Proxy và lời gọi** của **Spring Framework - concurrency**. Trọng tâm là hiểu rõ vì sao **@Async không chạy trên worker như mong đợi**, cách phân tích lời gọi, tự kiểm chứng bằng Java 17, chọn kiểu proxy và sửa cấu trúc code an toàn.

## 1. Proxy nằm ở đâu trong đường gọi?

Một đối tượng Java thông thường thực hiện lời gọi trực tiếp:

~~~text
Caller ----> instance service ----> service.work()
~~~

Trong Spring AOP ở chế độ proxy, bean được đưa cho caller có thể là **proxy**, không phải đối tượng target nguyên bản:

~~~text
                         lời gọi qua proxy
Caller ----> Proxy ----> Async interceptor ----> Executor
                 |                                 |
                 |                                 +-- worker thread:
                 |                                      target.work()
                 |
                 +-- có thể trả về Future/CompletableFuture

Khi target gọi this.work():
target ------> target.work()         (không quay lại Proxy)
~~~

Đường đi này lý giải hai hiện tượng quan trọng:

1. **Chỉ annotation chưa đủ.** Spring phải bật hỗ trợ async, bean phải được Spring quản lý và lời gọi phải đi qua cấu trúc mà interceptor có thể chặn.
2. **Một lần gọi vào target từ bên trong target không tự động vòng qua proxy.** Vấn đề không nằm ở tên method hoặc độ phức tạp của logic; đó là đặc tính phân phối lời gọi trong proxy-based AOP.

Ở tầng JDK, Spring có thể dùng **JDK dynamic proxy** (đứng trên interface) hoặc **CGLIB subclass proxy** (tạo lớp con của target). Hai phương án đều là proxy, nhưng giới hạn kỹ thuật khác nhau.

**Phạm vi bài:** giải thích cơ chế proxy-based **@Async**, đồng thời chỉ ra những giới hạn proxy cũng thường tác động tới **@Transactional**, **@Cacheable** và lời khuyên AOP khác. Không đồng nhất tất cả annotation hoặc tất cả phiên bản Spring: chúng có quy tắc phát hiện annotation, phạm vi phương thức và cấu hình riêng.

## 2. private trong Java và vì sao proxy không chặn được

Một **private method** chỉ truy cập trực tiếp được bên trong class khai báo nó, theo quy tắc truy cập của Java. Khi một method public gọi helper private, lời gọi private được xử lý bên trong đối tượng; nó **không trở thành một lời gọi đi qua proxy chỉ vì method private có @Async**.

~~~java
import org.springframework.scheduling.annotation.Async;

public class InvoiceService {
    public void submitInvoice() {
        sendInBackground(); // Gọi nội bộ, không đi qua proxy.
    }

    @Async
    private void sendInBackground() {
        // Không được Spring proxy intercept để chuyển sang thread khác.
    }
}
~~~

Đây là **đoạn minh họa trong một ứng dụng Spring**; không phải tệp Java độc lập. Với proxy-based async:

- CGLIB tạo subclass để intercept các method có thể override; **private không được override** trong Java, nên proxy không chèn interceptor vào lời gọi này.
- JDK proxy chỉ trình bày phương thức thuộc **interface được proxy**, không tạo một điểm gọi private của implementation cho caller.
- Annotation đặt trên private method **không biến lời gọi nội bộ thành async**.
- Nếu gọi **submitInvoice()** trực tiếp từ request thread, helper private thường chạy trong cùng thread đó, trừ khi code chủ động dùng một executor ở chỗ khác.

**Điều cần tránh:** chạy qua debugger thấy @Async trên private rồi suy ra method đã gửi task; cần kiểm tra **Thread.currentThread()** hoặc kiểm thử tương quan thread identity.

### Một helper private vẫn có thể chạy trên worker khi nào?

Nếu **một public method được proxy chặn và chuyển sang executor**, method public đó có thể gọi helper private *bên trong worker*. Điều này hợp lệ và hữu ích:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    @Async("notificationExecutor")
    public void deliver(String recipient) {
        validateAndSend(recipient); // Chạy trên thread đã thực thi deliver.
    }

    private void validateAndSend(String recipient) {
        // Helper nội bộ; không cần @Async riêng.
    }
}
~~~

**deliver** phải được **bean khác gọi qua proxy** và cấu hình hỗ trợ async phải hợp lệ. Helper **validateAndSend** được chạy từ body của deliver, tức là có thể chạy trên worker sau khi deliver được dispatch; **không phải** vì proxy đã chặn helper private.

Tách hai ý:

- “private method được intercept độc lập bởi Spring AOP proxy?” → **Không**.
- “private helper có thể được thực hiện trong worker do public @Async gọi?” → **Có**, nếu public @Async đã thực sự được dispatch.

Đây là lý do việc **đổi @Async từ private helper sang một public entry point** thường giải quyết được trường hợp lỗi, miễn caller gọi public entry point qua proxy.

## 3. final method: không thể override bằng CGLIB

**final method** trong Java không cho lớp con override. CGLIB class-based proxy dùng cách tạo subclass của target, rồi **ghi đè các method có thể override** để đưa advice vào đường gọi.

Vì thế, một method **public final** không thể được CGLIB chặn bằng kỹ thuật override:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;

public class BillingService {
    @Async("billingExecutor")
    public final CompletableFuture<String> calculate() {
        return CompletableFuture.completedFuture("ready");
    }
}
~~~

Đây là **đoạn minh họa**, không phải chương trình chạy đầy đủ. Khi Spring dùng **class-based proxy**, **calculate()** là final nên interceptor không thể override method đó để dispatch sang executor. Lời gọi tới final method có thể đi thẳng vào implementation theo Java và **không có ranh giới @Async** như dự kiến.

**Không được phát biểu quá rộng rằng mọi final method trên mọi kiểu proxy đều không thể chặn.** Hạn chế override này thuộc **class-based proxy**. Một interface-based proxy có cơ chế khác, phân tích ở mục 5.

### final class nghiêm ngặt hơn final method

~~~java
public final class ClosedService {
    public String work() {
        return "ok";
    }
}
~~~

Một subclass **không thể kế thừa ClosedService**, nên CGLIB không thể tạo class proxy của class này. Nếu bean cần class-based proxy, ứng dụng có thể gặp lỗi tạo proxy trong quá trình khởi động; không nên giả định Spring sẽ tự biến một final class thành proxy hợp lệ.

Nếu **final class có interface nghiệp vụ** và cấu hình phù hợp, JDK dynamic proxy vẫn có thể đứng **trước interface** để chặn lời gọi đến instance của final class. Khi đó bean được inject bằng **interface**, không phải đối tượng proxy có cùng concrete class.

**final field khác final method.** Field final ngăn gán lại tham chiếu sau khởi tạo (theo quy tắc Java), không ngăn một **public non-final method** của class được subclass proxy intercept. Việc bean chứa field final **không tự động khiến @Async thất bại**.

| Thứ được khai báo final | Tác động |
| --- | --- |
| **final local variable** | Không cho gán lại biến trong phạm vi Java. |
| **final field** | Không cho gán lại field theo quy tắc Java; không khóa các object nested mutable. |
| **final method** | Không cho override; **CGLIB không thể đặt advice bằng override** lên method đó. |
| **final class** | Không cho subclass; **CGLIB không thể tạo subclass proxy** của class đó. |

Khi review một class, hãy xem final áp lên **điều gì**, không chỉ tìm chuỗi “final”.

## 4. Giới hạn modifier: đối chiếu trực tiếp JDK và CGLIB

Bài về hai kiểu proxy đã so sánh cấu trúc và khả năng injection. Ở đây tập trung vào một câu hỏi hẹp: **modifier Java nào quyết định method có thể được chặn độc lập?**

| Điều kiện trên target | JDK interface proxy | CGLIB class-based proxy |
| --- | --- | --- |
| `private method` | Không có lời gọi vào private method qua interface proxy. | Không thể override để intercept. |
| `public final method` thuộc interface | Có thể intercept **lời gọi qua interface proxy** trước khi delegate tới implementation final. | Không thể override final method để advice. |
| `final class` triển khai interface | JDK proxy vẫn có thể đứng trước interface nếu advisor/cấu hình phù hợp. | Không tạo subclass từ final class. |
| `this.publicAsync()` nội bộ | Lời gọi bỏ qua proxy. | Lời gọi bỏ qua proxy. |

JDK proxy xử lý lời gọi qua `InvocationHandler` **trước** khi ủy quyền tới target, nên implementation final không ngăn interface interception. CGLIB cần subclass/override, do đó tuân thủ `final` và `private`. Đây là bảng **khả năng kỹ thuật**, không bảo đảm annotation đã được Spring nhận diện hoặc executor đã nhận task; luôn kiểm tra proxy type, method signature và đường gọi thực. Ví dụ tiếp theo chứng minh ranh giới JDK Proxy bằng Java thuần.

## 5. Ví dụ Java 17 chạy độc lập: final target vẫn được JDK interface proxy chặn

Ví dụ đầu tiên **không dùng Spring**; nó chỉ minh họa **đúng cơ chế JDK dynamic proxy** để phân biệt “final ở target” và “chặn lời gọi ở proxy”. Ta ghi số lần handler nhìn thấy method run. Sau khi gọi run qua proxy, counter tăng. Sau khi gọi outer qua proxy, target tự gọi run bằng **this.run()**, counter không tăng thêm.

Lưu thành tệp **InterfaceProxyDemo.java**:

~~~java
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;

public class InterfaceProxyDemo {
    public interface TaskPort {
        String run();
        String outer();
    }

    public static final class FinalTarget implements TaskPort {
        @Override
        public final String run() {
            return "work-done";
        }

        @Override
        public String outer() {
            return this.run();
        }
    }

    public static void main(String[] args) {
        FinalTarget target = new FinalTarget();
        AtomicInteger advisedRunCount = new AtomicInteger();

        TaskPort proxy = (TaskPort) Proxy.newProxyInstance(
                TaskPort.class.getClassLoader(),
                new Class<?>[] { TaskPort.class },
                (p, method, params) -> {
                    if (method.getName().equals("run")) {
                        advisedRunCount.incrementAndGet();
                    }
                    return method.invoke(target, params);
                }
        );

        System.out.println("Kết quả proxy.run: " + proxy.run());
        System.out.println("Final method qua interface được chặn: "
                + (advisedRunCount.get() == 1));

        System.out.println("Kết quả proxy.outer: " + proxy.outer());
        System.out.println("Lời gọi this.run được chặn: "
                + (advisedRunCount.get() == 2));
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 InterfaceProxyDemo.java
java InterfaceProxyDemo
~~~

**Stdout của chương trình:**

~~~text
Kết quả proxy.run: work-done
Final method qua interface được chặn: true
Kết quả proxy.outer: work-done
Lời gọi this.run được chặn: false
~~~

**Lý giải:**

1. **FinalTarget** là final class, và **run()** của nó cũng là final.
2. **proxy.run()** là lời gọi qua interface **TaskPort**. InvocationHandler chạy, tăng counter rồi mới gọi target.run().
3. **proxy.outer()** cũng qua handler, nhưng handler chỉ tăng counter nếu method được gọi tên **run**. Đến bên trong target.outer(), **this.run()** gọi target.run() trực tiếp, **không gọi lại interface proxy**.
4. Vì vậy counter của run vẫn bằng 1 sau lời gọi outer, nên dòng cuối là false.
5. Đây là ví dụ **JDK Proxy tự viết**, không chứng minh mọi cấu hình Spring @Async áp dụng thành công trên final method. Muốn kiểm chứng Spring phải dùng Spring context và @Async thực sự như các phần sau.

**Quan sát:** final class và final implementation không tự chặn JDK interface proxy. Vấn đề nằm ở việc lời gọi có đi qua proxy và advice được cấu hình để xử lý lời gọi đó hay không.

## 6. Lời gọi nội bộ (self-invocation): public cũng có thể mất advice

Xét một service:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ExportService {
    public void startExport() {
        exportAsync(); // Tương đương this.exportAsync().
    }

    @Async("exportExecutor")
    public void exportAsync() {
        // Công việc nặng.
    }
}
~~~

Nếu một bean khác gọi **startExport()** qua proxy, phương thức startExport có thể được thực thi như một cuộc gọi thông thường. Bên trong, lời gọi **this.exportAsync()** không quay ra proxy để Spring phát hiện @Async. Vì thế **exportAsync có thể chạy đồng bộ ngay trên thread caller của startExport**.

Đây là lỗi rất dễ xuất hiện khi lập trình viên nghĩ:

> “Tôi đã ghi @Async trên method rồi, mọi lần gọi method đều chạy bất đồng bộ.”

Thực tế **@Async ở chế độ proxy chặn *đường gọi*, không biến method thành một thân hàm có cơ chế đa luồng tự động**.

Không chỉ cách viết explicit this mới mắc lỗi. Cả hai dạng sau đều là lời gọi nội bộ:

~~~java
this.exportAsync();
exportAsync();
~~~

Nếu gọi trực tiếp một instance tạo bằng **new ExportService()**, kể cả từ bean khác, instance đó không được Spring proxy quản lý; annotation không có tác dụng như khi đi qua Spring bean proxy.

## 7. Cách sửa self-invocation an toàn: tách điểm gọi sang bean khác

Cách dễ hiểu và dễ test nhất là **tách orchestration** và **async worker** thành hai bean; một bean inject bean còn lại.

**ExportWorker.java** — public entry point:

~~~java
package example.demo;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ExportWorker {
    @Async("exportExecutor")
    public CompletableFuture<String> export(long orderId) {
        String result = "export-" + orderId;
        return CompletableFuture.completedFuture(result);
    }
}
~~~

**ExportFacade.java** — gọi qua bean do Spring inject:

~~~java
package example.demo;

import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class ExportFacade {
    private final ExportWorker worker;

    public ExportFacade(ExportWorker worker) {
        this.worker = worker;
    }

    public CompletableFuture<String> start(long orderId) {
        return worker.export(orderId);
    }
}
~~~

Đoạn code này giả định có **@EnableAsync**, executor tên **exportExecutor** và Spring component scanning hoặc đăng ký bean phù hợp. Đây là **mẫu nhiều file cho ứng dụng Spring**, không phải chương trình javac độc lập.

Vì **worker** là dependency được Spring cung cấp, caller dùng đối tượng proxy hợp lệ khi bean được tạo với async advice. Lời gọi worker.export(...) đi qua proxy, interceptor có thể đưa việc vào executor. Đây là cách làm ưu tiên so với việc nhồi tất cả method vào cùng một class rồi thử gọi self-reference.

### Có nên inject proxy của chính mình?

Có thể có các kỹ thuật tự inject chính bean qua proxy hoặc gọi **AopContext.currentProxy()**, nhưng chúng tạo coupling khó hiểu, có thể gây vòng phụ thuộc hoặc yêu cầu cấu hình exposeProxy riêng. **Không nên chọn làm giải pháp đầu tiên**. Tách một worker bean với trách nhiệm rõ ràng thường đơn giản, dễ kiểm thử và ít bất ngờ hơn.

## 8. Ví dụ Spring thực tế: so sánh public, private, final và self-call

Ví dụ sau sử dụng **Spring Framework 6.2.x**, **Java 17**, một **class-based proxy** được yêu cầu tường minh bằng **@EnableAsync(proxyTargetClass = true)**. Nó dùng method trả **CompletableFuture<Boolean>**, rồi kiểm tra body thực sự chạy ở thread khác caller hay không. Để kết quả rõ, không in tên thread vốn có thể thay đổi.

Cấu trúc:

~~~text
async-proxy-demo/
├── pom.xml
└── src/main/java/example/ProxyAsyncDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>async-proxy-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.ProxyAsyncDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/ProxyAsyncDemo.java**:

~~~java
package example;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ProxyAsyncDemo {
    @Configuration
    @EnableAsync(proxyTargetClass = true)
    public static class Config {
        @Bean("lessonExecutor")
        public ThreadPoolTaskExecutor lessonExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("lesson-");
            return executor;
        }

        @Bean
        public Worker worker() {
            return new Worker();
        }
    }

    public static class Worker {
        @Async("lessonExecutor")
        public CompletableFuture<Boolean> publicAsync(Thread caller) {
            return CompletableFuture.completedFuture(
                    Thread.currentThread() != caller);
        }

        public boolean selfCall(Thread caller) {
            return this.publicAsync(caller).join();
        }

        @Async("lessonExecutor")
        private CompletableFuture<Boolean> privateAsync(Thread caller) {
            return CompletableFuture.completedFuture(
                    Thread.currentThread() != caller);
        }

        public boolean callPrivate(Thread caller) {
            return privateAsync(caller).join();
        }

        @Async("lessonExecutor")
        public final CompletableFuture<Boolean> finalAsync(Thread caller) {
            return CompletableFuture.completedFuture(
                    Thread.currentThread() != caller);
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            Worker worker = context.getBean(Worker.class);
            Thread caller = Thread.currentThread();

            System.out.println("Public qua proxy: "
                    + worker.publicAsync(caller)
                            .get(5, TimeUnit.SECONDS));
            System.out.println("Tự gọi public: "
                    + worker.selfCall(caller));
            System.out.println("Gọi private bên trong: "
                    + worker.callPrivate(caller));
            System.out.println("Gọi final qua CGLIB: "
                    + worker.finalAsync(caller).join());
        }
    }
}
~~~

Chạy từ thư mục chứa **pom.xml** với JDK 17 và Maven:

~~~bash
mvn -q compile exec:java
~~~

**Stdout mong đợi của ứng dụng** trong cấu hình đã nêu (không tính thông tin Maven/Spring logging):

~~~text
Public qua proxy: true
Tự gọi public: false
Gọi private bên trong: false
Gọi final qua CGLIB: false
~~~

**Giải thích kỹ các dòng:**

1. **Public qua proxy: true.** Một caller ngoài bean gọi method publicAsync trên proxy CGLIB. Async interceptor gửi task tới lessonExecutor; body so sánh **Thread.currentThread()** với caller và thấy khác nhau. **get(timeout)** chờ kết quả để output ổn định.
2. **Tự gọi public: false.** Method **selfCall** chạy bình thường, rồi gọi **this.publicAsync** trên target, không vòng qua proxy. Body chạy ngay tại caller thread. Giá trị CompletableFuture ở đây chỉ là completedFuture được tạo trực tiếp; không có dispatch @Async.
3. **Gọi private bên trong: false.** **callPrivate** gọi privateAsync trực tiếp, không có điểm override/interception. Body vẫn chạy trên thread gọi callPrivate.
4. **Gọi final qua CGLIB: false.** Spring được ép tạo class-based proxy, nhưng CGLIB không thể override finalAsync. Lời gọi không được interceptor @Async bao quanh; code so sánh thread ra false.
5. **Worker** không final, để CGLIB tạo subclass proxy. Chính **final method** trong class mới được dùng để minh họa hạn chế. Class-based proxy không thể khắc phục lỗi này chỉ bằng cách thêm annotation.

Ví dụ này **dùng các boolean và lệnh get(timeout)** thay vì dựa vào lịch scheduler, thứ tự log hay tên thread. Các cấu hình **proxyTargetClass**, tên executor và phạm vi bean đều được khai báo tường minh. Nếu môi trường dùng cấu hình AOP khác hoặc phiên bản Spring khác, hãy kiểm tra proxy thực tế và điều chỉnh cách kiểm thử, thay vì lấy stdout này làm bảo đảm cho mọi môi trường.

**Lưu ý quan trọng về @Async:** return type trong ví dụ là **CompletableFuture<Boolean>**. Theo hợp đồng Spring, một phương thức @Async trả kết quả được khai báo bằng **Future/CompletableFuture**; bên trong thân method có thể trả **completedFuture** chứa kết quả đã tính, còn interceptor cung cấp ranh giới bất đồng bộ cho caller. Không bọc thêm **supplyAsync** vào common pool nếu không có chủ đích.

## 9. Khi dùng interface-based proxy: final implementation có thể vẫn intercept

Giả sử một service cung cấp **interface public**:

~~~java
package example.api;

import java.util.concurrent.CompletableFuture;

public interface TaskPort {
    CompletableFuture<String> perform(String id);
}
~~~

Implementation:

~~~java
package example.api;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public final class TaskPortImpl implements TaskPort {
    @Override
    @Async("taskExecutor")
    public final CompletableFuture<String> perform(String id) {
        return CompletableFuture.completedFuture("done:" + id);
    }
}
~~~

Đây là **hai tệp riêng trong một ứng dụng Spring**, không phải một ví dụ Maven đầy đủ. Với **JDK interface-based proxy** và async advisor phát hiện được annotation, lời gọi **taskPort.perform(id)** qua **TaskPort proxy** có thể được intercept, dù implementation method và class đều là final. Vì JDK proxy không tạo subclass của **TaskPortImpl**.

Để áp dụng an toàn:

- Inject bean theo **TaskPort**, không yêu cầu proxy là TaskPortImpl.
- Kiểm tra ứng dụng thực sự chọn **JDK dynamic proxy** chứ không bị cấu hình toàn cục ép CGLIB.
- Kiểm tra annotation được Spring phát hiện theo vị trí đặt annotation/phiên bản đang dùng.
- Viết integration test chứng minh **method thực sự chạy trên executor**, không chỉ assert annotation tồn tại.
- Nếu ứng dụng ép class-based proxy đối với **TaskPortImpl final**, cách tạo proxy có thể lỗi. Khi đó cần bỏ final class, đổi strategy hay tổ chức lại interface/service.

Điểm quan trọng là **không dùng phương án “cứ bỏ final khỏi tất cả method”** nếu dự án có chính sách Java khác. Trước tiên xác định proxy type và API exposure; tuy nhiên với một worker @Async mới, một **public non-final method trên bean không final được Spring quản lý** vẫn là lựa chọn dễ hiểu, dễ dùng và ít rủi ro.

## 10. Spring chọn proxy nào? Cách kiểm tra runtime

Ở ứng dụng Spring 6.x, **@EnableAsync** mặc định hoạt động với **AdviceMode.PROXY**. Thuộc tính **proxyTargetClass** cho phép yêu cầu class-based proxy khi dùng chế độ PROXY.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync(proxyTargetClass = true)
public class AsyncConfiguration {
}
~~~

Đây là **tệp cấu hình Spring**. Việc ép proxy class-based có thể ảnh hưởng tới các bean cần AOP khác tùy cơ chế cấu hình toàn cục. Bởi vậy, không tùy tiện bật nó chỉ để sửa một private/final method.

Một số ứng dụng Spring Boot có thể kích hoạt class-based proxy theo property hoặc cấu hình AOP khác. Khi cần kết luận chính xác, **kiểm tra instance proxy thật**:

~~~java
import org.springframework.aop.support.AopUtils;

Object bean = applicationContext.getBean("worker");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
~~~

Đây là **đoạn minh họa trong một method có biến applicationContext**; cần Spring AOP trong classpath. Các boolean phản ánh kiểu proxy của bean **tại thời điểm chạy**. Đừng đoán proxy type từ tên class source hoặc từ tên bean.

Cần chú ý rằng **JDK proxy không phải subtype của concrete target**. Code inject phụ thuộc bằng concrete class có thể không hoạt động, dù interface-based proxy hoàn toàn hợp lệ cho các method được interface công khai.

### Bảng kiểm đường gọi

| Trường hợp | Có cơ hội Spring proxy advice chạy? | Vì sao |
| --- | --- | --- |
| Bean khác gọi public non-final method qua class proxy | **Có**, nếu advice khớp | Proxy override method để intercept |
| Bean khác gọi public interface method qua JDK proxy | **Có**, nếu advice khớp | Lời gọi đi tới invocation handler |
| Method private có @Async, caller nội bộ gọi | **Không** | Private không là method có thể intercept qua proxy |
| Method final qua CGLIB | **Không** | Không thể override |
| Method final của target được gọi qua JDK interface proxy | **Có thể** | Điểm chặn nằm ở interface proxy, không cần override final implementation |
| final class bị yêu cầu CGLIB proxy | **Không** | Không thể subclass |
| final class triển khai interface, JDK proxy phù hợp | **Có thể** | JDK proxy implements interface |
| Bean gọi this.publicAsync() | **Không** | Self-invocation bỏ qua proxy |
| Một instance tạo bằng new thay cho Spring bean | **Không** | Instance không qua proxy của Spring |
| Public @Async chạy trên worker và gọi private helper | Helper chạy trên worker, **nhưng không được intercept riêng** | Worker context đã được thiết lập ở public entry point |

Bảng nói về **khả năng chặn lời gọi**, không phải cam kết mọi lời gọi luôn bất đồng bộ: còn phụ thuộc @EnableAsync, advisor, executor, bão hòa, rejection, cách inject và độ hợp lệ của return type.

## 11. Vấn đề còn lại: private/protected/package-private và quy tắc riêng từng annotation

Trong Spring AOP, private và final là hai giới hạn cấu trúc rất rõ của class-based proxy. Tuy nhiên, với những mức visibility còn lại, không nên đưa một quy tắc duy nhất áp cho tất cả annotation:

- Với **@Async**, để bài học và code production dễ dự đoán, **public method** được bean khác gọi qua proxy là mẫu nên ưu tiên.
- Một số subsystem khác trong Spring 6.x, chẳng hạn **@Transactional** trên class-based proxy, có hỗ trợ những method **protected hoặc package-private** trong điều kiện nhất định; điều đó **không tự chứng minh @Async trên mọi non-public method hoạt động tương tự**.
- Một package-private method ở superclass khác package có thể **không nhìn thấy được để override** từ proxy subclass, hiệu quả gần giống private.
- **Static method** cũng không được override như instance method thông thường; @Async được thiết kế quanh lời gọi instance qua Spring bean proxy. Không xem static method như một @Async entry point đáng tin.
- **Constructor** và **@PostConstruct** không phải một điểm vào proxy-based @Async bình thường. Nếu cần khởi động việc async sau khi bean sẵn sàng, dùng một bean khác thực hiện lời gọi phù hợp khi lifecycle cho phép.

**Sai lầm thường gặp:** đọc một bài hướng dẫn riêng về @Transactional, rồi cho rằng private/protected/final có cùng hành vi ở @Async. Hãy phân biệt giới hạn AOP **chung** với hợp đồng và cơ chế **riêng** của từng annotation.

### Kotlin và record là những trường hợp đáng chú ý

Kotlin class và method mặc định là **final** trừ khi khai báo open hoặc áp dụng plugin hỗ trợ. Nếu dùng Spring AOP class-based proxy, cần chú ý cách compiler/plugin tạo class và method có thể được proxy. **Không tự giả định annotation Spring luôn khiến mọi Kotlin method mở.**

Trong Java, **record** là **final class**. Một record làm DTO bất biến có thể rất phù hợp để **truyền dữ liệu cho task**, nhưng không phải loại bean thích hợp nếu bạn cần CGLIB subclass proxy cho @Async entry point. Tách DTO record và service bean có method public non-final sẽ giảm xung đột.

## 12. Sự khác nhau giữa @Async và CompletableFuture.supplyAsync

Một câu hỏi quan trọng: “Nếu private hoặc final method không bị @Async intercept, có cách nào vẫn chạy task trên thread khác không?”

Có, nhưng **đó không phải interception của annotation**. Một method có thể **chủ động gửi task tới ExecutorService hoặc CompletableFuture.supplyAsync**, dù method bao quanh private/final. Cần tách hai cơ chế:

**Cơ chế A — Spring proxy chặn lời gọi:**

~~~java
@Async("jobExecutor")
public CompletableFuture<String> runAsync() {
    return CompletableFuture.completedFuture("ok");
}
~~~

Khi gọi qua Spring proxy hợp lệ, interceptor chuyển việc sang executor.

**Cơ chế B — tự submit bên trong method:**

~~~java
private CompletableFuture<String> createTask(
        java.util.concurrent.Executor executor) {
    return CompletableFuture.supplyAsync(
            () -> "ok",
            executor);
}
~~~

Đây là **hai đoạn minh họa không độc lập**, có import/context tương ứng. Trong cơ chế B, task có thể chạy trên executor **vì code gọi supplyAsync**; **không có yêu cầu phải proxy private method**.

Đừng lấy việc thấy một CompletableFuture trả về để kết luận @Async đã được áp dụng. **CompletableFuture.completedFuture** có thể hoàn tất ngay trong caller. Ngược lại, supplyAsync có thể thật sự chạy ở worker **mà không cần annotation**.

**Nguy cơ double scheduling:** nếu method public đã được @Async proxy chuyển sang executor, rồi trong body lại gọi supplyAsync không truyền executor hoặc truyền executor khác, tác vụ có thể bị đẩy sang luồng thứ hai ngoài kế hoạch. Điều này làm khó quản lý context, shutdown, transaction, lỗi và đo latency. Chỉ thêm một tầng bất đồng bộ khi có lý do cụ thể.

## 13. Tính đúng đắn của việc chạy @Async cần kiểm tra gì ngoài proxy?

Một lời gọi đã đi qua proxy chưa bảo đảm hệ thống xử lý công việc thành công:

1. **Executor có nhận task không?** Pool có thể bão hòa hoặc shutdown và ném **TaskRejectedException** ở ranh giới submit.
2. **Tác vụ đã bắt đầu chưa?** Có thể phải chờ trong queue tùy cấu hình ThreadPoolTaskExecutor.
3. **Kết quả/exception được trả qua gì?** Với Future/CompletableFuture, caller có thể quan sát thành công hoặc lỗi. Với @Async void, lỗi task không tự biến thành exception trong caller.
4. **Caller có tự chặn lại bằng join()/get()?** Nếu gọi get ngay, caller đợi và không còn hưởng lợi về thời gian phản hồi.
5. **Dữ liệu đầu vào đã an toàn để sang thread khác chưa?** Mutable object và request-scoped context có thể gây race/đọc sai dữ liệu, kể cả khi proxy chạy đúng.
6. **ThreadLocal/SecurityContext/MDC/transaction có cần propagation không?** Những ngữ cảnh gắn thread không mặc nhiên xuất hiện đúng ở worker.
7. **Task có deadline/cancellation và graceful shutdown không?** Chạy async mà giữ worker vô hạn vẫn có thể làm nghẽn hệ thống.

Đừng sửa lỗi proxy bằng cách làm **mọi field singleton mutable** rồi đọc từ background thread. Cách đó khiến nhiều request ảnh hưởng tới nhau. Hãy truyền dữ liệu nghiệp vụ qua method parameter/immutable snapshot và quản lý giới hạn executor.

## 14. Ngoại lệ: AspectJ weaving không dùng cùng mô hình proxy

Spring có thể dùng **AdviceMode.ASPECTJ** cho hỗ trợ async với cấu hình và dependency phù hợp, thay vì **AdviceMode.PROXY** mặc định. AspectJ dùng cơ chế **weaving** (compile-time hoặc load-time) để gắn advice ở các join point, không phụ thuộc vào một wrapper proxy đứng trước target theo cùng cách.

Hệ quả quan trọng:

- Giới hạn **self-invocation bỏ qua proxy** có thể được khắc phục với cơ chế AspectJ weaving đúng, vì không còn phụ thuộc vào lời gọi đi qua một đối tượng proxy.
- Chỉ đổi **@EnableAsync(mode = AdviceMode.ASPECTJ)** trong source rồi chạy lại **không đủ**. Cần **spring-aspects** và cấu hình weaving thích hợp; phải kiểm chứng artifact đã được weave và advisor thực tế có hoạt động.
- Thuộc tính **proxyTargetClass** không phải chìa khóa khi dùng AdviceMode.ASPECTJ, vì lúc đó không tạo proxy theo hai kiểu JDK/CGLIB như phần trên.
- Không tự động khẳng định **mọi private/final method** được xử lý theo cách giống nhau trong mọi thiết lập weaving; cần xem loại join point, rules của AspectJ, phiên bản, visibility và integration tests.

Trong phần lớn ứng dụng Spring sử dụng @Async thông thường, **tách một public async service bean và gọi qua proxy** là giải pháp đơn giản, ít cấu hình hạ tầng hơn chuyển sang weaving.

## 15. Lỗi khó nhận biết khi kết hợp @Transactional và @Async

Đây là tình huống liên quan trực tiếp tới **khả năng chặn lời gọi**, không phải bài chuyên sâu về transaction:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.transaction.annotation.Transactional;

public class OrderService {
    public void create() {
        saveInTransaction(); // Self-invocation có thể bỏ qua advice.
    }

    @Transactional
    public void saveInTransaction() {
        // Nếu chỉ được gọi qua this, transaction proxy có thể không chạy.
    }

    @Async
    public void notifyAsync() {
        // Nếu gọi this.notifyAsync(), async proxy có thể không chạy.
    }
}
~~~

Đây là **đoạn minh họa** với cấu hình Spring tương ứng; không phải service hoàn chỉnh. Với proxy-based AOP, cả @Transactional và @Async có thể bị bypass bởi self-invocation. Nhưng sửa bằng cách tách bean không có nghĩa **transaction sẽ tự chuyển từ request thread sang worker thread**. Transaction context gắn thread và thường cần boundary của chính worker.

Ví dụ về thiết kế:

~~~text
OrderFacade (HTTP/request thread)
    |
    +-- orderService.save(...)       -> transaction riêng
    |
    +-- notificationWorker.send(...) -> @Async qua proxy
                                         -> worker logic / transaction nếu cần
~~~

Nếu cần công việc chỉ được gửi **sau khi giao dịch commit**, cân nhắc cơ chế **transactional event/outbox** phù hợp. Chỉ gọi @Async trước commit có thể làm worker đọc trạng thái database chưa được commit hoặc gặp thứ tự nghiệp vụ sai.

**Không trộn khái niệm:** lỗi “@Async không chạy vì final/private/self-call” là lỗi **interception**. Lỗi “worker không có transaction/request context” là lỗi **thread/context boundary**. Hai vấn đề có thể cùng xuất hiện nhưng phải chẩn đoán và sửa riêng.

## 16. Kiểm thử thật: đừng chỉ nhìn thread name

Trong kiểm thử Spring AOP, tối thiểu cần kiểm tra:

- **Bean lấy từ ApplicationContext**, không phải instance tự new.
- **AopUtils.isAopProxy(bean)** xác nhận có proxy nếu cấu hình yêu cầu.
- **AopUtils.isJdkDynamicProxy / isCglibProxy** xác định kiểu, không suy đoán.
- Lời gọi @Async được thực hiện từ **một bean khác** hoặc từ runner giữ Spring-managed proxy.
- Tác vụ xác nhận **Thread.currentThread() khác caller** khi cần chứng minh dispatch sang worker.
- Với CompletableFuture, **get(timeout)** để tránh test treo không giới hạn.
- Đặt test rõ cho **private, final và self-invocation** để ghi nhận các trường hợp không có interception.
- Test trường hợp executor **reject** và trường hợp logic worker **ném lỗi**, không nhầm với lỗi proxy.

Một test vô tình có thể báo pass dù @Async không hoạt động:

~~~java
@Async
public CompletableFuture<String> method() {
    return CompletableFuture.completedFuture("ok");
}
~~~

Nếu test chỉ assert future.get() trả “ok”, nó vẫn đúng **khi method chạy đồng bộ vì self-invocation**. Cần kiểm tra **thread identity hoặc tín hiệu về dispatch**, chẳng hạn dùng CountDownLatch chặn body và quan sát caller có trả về trước khi body hoàn tất không.

Không nên dựa vào **Thread.sleep(100)** để mong chắc chắn worker đã chạy. Latch/Barrier và timeout khiến kiểm thử rõ ràng hơn. Đừng assert chính xác tên thread hoặc thứ tự log nếu executor có nhiều worker.

### Dùng CountDownLatch để kiểm chứng ranh giới proxy

Một kiểm thử có thể:

1. Ghi lại **Thread caller** trước khi invoke bean.
2. Chuẩn bị worker method public non-final có **CountDownLatch started** và **CountDownLatch release**.
3. Gọi qua proxy, kiểm tra caller có nhận Future trước khi mở release, khi executor chưa bão hòa.
4. Sau đó mở release và chờ future.get(timeout).
5. Ghi **Thread.currentThread()** trong worker, assert khác caller.
6. Lặp lại cho self-call từ target và đối chiếu, nhưng **không dùng chính một caller thread đang bị giữ để điều phối release** vì sẽ tự deadlock; dùng thread test riêng hoặc thiết kế barrier đúng.

Với class-based proxy, test public final method cần phân biệt **không bị intercept** khỏi “đã chạy nhanh nên nhìn như đồng bộ”. Một method chạy rất nhanh có thể hoàn tất tức thì ngay cả khi được dispatch đúng. Thử so sánh thread identity như ví dụ đầy đủ sẽ mạnh hơn.

## 17. Debug từng bước khi @Async không chạy trên thread khác

Dùng một quy trình điều tra ngắn, theo thứ tự có thể xác minh:

**Bước 1 — Xác nhận điểm gọi.** Code gọi bean lấy từ Spring (injected hoặc context.getBean) hay dùng **new**?

**Bước 2 — Kiểm tra Spring có bật async chưa.** Có @EnableAsync, cấu hình tương đương hoặc cơ chế framework bật async thực tế?

**Bước 3 — Xác định method được annotate.** Annotation đặt trên **public entry point** thích hợp hay bị đặt ở private helper/final method?

**Bước 4 — Xác định proxy type.** AopUtils cho biết JDK hay CGLIB? Có class/method final xung đột với subclass proxy không?

**Bước 5 — Kiểm tra đường gọi.** Caller gọi qua proxy từ bean khác hay **this.method()**? Có method A gọi method B trong cùng target rồi kỳ vọng B được intercept không?

**Bước 6 — Kiểm tra executor.** Bean name trong @Async("...") có tồn tại, đúng loại Executor, đang chạy và có capacity nhận task không?

**Bước 7 — Kiểm tra kết quả.** Đo thread identity trong body, future completion và exception path. Đừng chỉ nhìn “method trả về quá nhanh/chậm”.

**Bước 8 — Phân biệt lỗi khác.** Worker có thể chạy đúng thread nhưng mất MDC, request context, security context hoặc transaction; đó là vấn đề propagation/ownership, không phải bản thân proxy.

**Bước 9 — Đưa test vào CI.** Một integration test nhỏ xác nhận proxy type và thread boundary giúp phát hiện thay đổi do refactor, việc thêm final, đổi interface, cấu hình Boot hoặc nâng version Spring.

## 18. Những nhầm lẫn thường gặp

**“Cứ thấy @Async là Java tạo luồng.”** Sai. @Async cần Spring interception và executor; annotation không biến bytecode Java thành lệnh tạo thread trong chế độ proxy.

**“Method private có @Async sẽ chạy background khi được public method gọi.”** Sai. Private method không được proxy intercept riêng. Nếu public method được @Async dispatch trước thì private helper có thể chạy **trên worker của public method**, nhưng đó là chuyện khác.

**“final method luôn không thể chặn bởi mọi loại proxy.”** Sai. CGLIB không override được final; JDK interface proxy vẫn có thể chặn **interface call** tới target có method final.

**“final class chắc chắn không bao giờ dùng được AOP.”** Không chính xác. Không thể CGLIB subclass final class, nhưng JDK interface proxy có thể bao một final implementation triển khai interface.

**“Có interface thì chắc chắn Spring đang dùng JDK proxy.”** Không thể khẳng định. Spring Boot hoặc cấu hình global có thể ép class-based proxy; xác nhận runtime.

**“@Async trên method public non-final chắc chắn chạy khác thread.”** Chưa chắc. Self-invocation, gọi instance new, chưa bật @EnableAsync, rejection, cấu hình executor và caller-runs policy đều ảnh hưởng.

**“this.async() vẫn chạy qua proxy vì this là bean Spring.”** Sai trong proxy-based AOP: lời gọi nội bộ trực tiếp trên target không qua wrapper proxy.

**“Gọi method proxy rồi immediately future.join() vẫn hoàn toàn nonblocking.”** Sai. join() có thể chặn caller đến khi xong.

**“Một private helper chạy trong worker có nghĩa @Async trên helper đã được intercept.”** Sai. Nó được gọi bởi body public method đã được dispatch.

**“Cứ bật proxyTargetClass=true là sửa được private/final.”** Sai. Đó chính là mô hình subclass nên càng chịu ràng buộc override, không vượt qua private/final.

**“@Transactional và @Async có cùng quy tắc visibility trong mọi phiên bản.”** Sai. Cần phân biệt từng annotation/subsystem, nhất là protected/package-private.

**“Đổi AdviceMode sang ASPECTJ là đủ.”** Sai. Cần dependency, weaving thực tế và test.

**“Future trả đúng giá trị nghĩa là đã chạy bất đồng bộ.”** Sai. Một completedFuture tạo trực tiếp trong caller vẫn trả kết quả giống hệt.

## 19. Bài tập suy luận

**Câu 1.** Một method có @Async, được khai báo private; một public method trong cùng class gọi nó. Trong chế độ proxy, private method có bị Spring intercept không?

**Đáp án:** Không. Không có điểm vào proxy có thể intercept private method. Nó chạy trong thread của public caller trừ khi public caller đã được chuyển thread bởi cơ chế khác.

**Câu 2.** Public @Async method không final nhưng được gọi bằng this.method() từ cùng bean. Có chắc chạy trên executor không?

**Đáp án:** Không. Self-invocation bỏ qua proxy trong AdviceMode.PROXY. Chuyển điểm gọi sang bean khác dùng Spring-managed proxy.

**Câu 3.** Một public final method trong bean được tạo class-based proxy. Có thể CGLIB override method để advice không?

**Đáp án:** Không. final cấm override. Cần đổi cấu trúc hoặc sử dụng cơ chế khác đáp ứng yêu cầu.

**Câu 4.** Một final class implements TaskPort, method perform() final. JDK dynamic proxy có thể intercept lời gọi TaskPort.perform() không?

**Đáp án:** Có thể. JDK proxy implements interface và chặn lời gọi trước khi delegate tới target; không cần subclass final class. Phải bảo đảm Spring advisor khớp và app dùng interface proxy thật.

**Câu 5.** Bean có field **private final TaskRepository repo**. Điều đó có ngăn public non-final @Async method được proxy không?

**Đáp án:** Không. Field final khác method/class final; field injection/cấu trúc dữ liệu của bean và khả năng override method là hai chuyện khác nhau.

**Câu 6.** Một public @Async method chạy trên worker, bên trong gọi private validate(). validate có chạy trên worker không?

**Đáp án:** Có, vì đó là một lời gọi nội bộ xảy ra **sau khi** public entry point đã được dispatch. Nhưng validate không được Spring intercept độc lập.

**Câu 7.** App Spring Boot được cấu hình dùng class-based proxy. Việc service có interface có chứng minh final method được chặn không?

**Đáp án:** Không. Nếu runtime thực tế dùng CGLIB, final method vẫn không thể override. Kiểm tra AopUtils hoặc bean proxy type.

**Câu 8.** Trong Java 17 JDK Proxy ví dụ, vì sao proxy.outer() không tăng bộ đếm advice của run()?

**Đáp án:** Invocation handler thấy **outer**, nhưng target.outer() gọi **this.run()** trực tiếp trên target. Lời gọi run không quay về proxy.

**Câu 9.** Nếu chuyển sang CompletableFuture.supplyAsync trong private method, task có thể chạy async không?

**Đáp án:** Có thể, vì **supplyAsync** tự submit tới executor. Đây không phải tác dụng của @Async proxy trên private method.

**Câu 10.** Một phép thử chỉ gọi method và so sánh Future.get() với chuỗi expected có đủ xác nhận @Async không?

**Đáp án:** Không. Nó chỉ xác nhận kết quả. Cần quan sát đường gọi, proxy, thread identity hoặc tín hiệu dispatch.

## 20. Checklist trước khi phát hành service dùng @Async

- [ ] Method async entry point được đặt ở **bean Spring-managed**, không phải instance new.
- [ ] Async support được bật trong đúng ApplicationContext.
- [ ] Lời gọi vào method async **đi qua proxy**; tránh self-invocation.
- [ ] Với class-based proxy, **bean class không final** và **method cần chặn không private/final**.
- [ ] Nếu dùng JDK proxy, inject bằng **interface** và xác nhận method được giao diện công khai.
- [ ] Không đánh đồng field final với method final.
- [ ] Kiểm tra proxy type bằng **AopUtils** thay vì suy đoán default.
- [ ] Chọn executor name rõ ràng, xác nhận capacity, rejection và shutdown policy.
- [ ] Dùng Future/CompletableFuture cho tác vụ cần kết quả và xử lý exceptional completion.
- [ ] Chụp input thích hợp trước khi qua thread boundary; không chia sẻ mutable state của singleton bean giữa request.
- [ ] Kiểm tra transaction/context propagation tại worker nếu nghiệp vụ cần.
- [ ] Viết integration test chứng minh method thật sự chạy trên thread của executor; không chỉ assert giá trị return.
- [ ] Nếu sử dụng AspectJ weaving, kiểm chứng dependency, cấu hình weaving và kết quả trong môi trường chạy.

## Kết luận

**Khả năng chặn lời gọi của Spring phụ thuộc vào *đường gọi và kiểu proxy*, không phụ thuộc vào việc source chỉ có một annotation.** Trong chế độ @Async dựa trên proxy, private method không phải điểm chặn thích hợp, final method không thể được CGLIB override, final class không thể được CGLIB subclass, và lời gọi nội bộ this.method() bỏ qua proxy dù method public. **JDK interface proxy có điểm mạnh riêng:** có thể intercept lời gọi qua interface ngay cả khi implementation class hoặc method là final, với điều kiện Spring thực sự dùng interface proxy và advice nhận diện đúng.

Thiết kế dễ bảo trì nhất thường là **public non-final @Async method trên một worker bean không final, được bean khác gọi qua dependency do Spring inject**. Luôn kiểm tra runtime proxy type, kết quả thực thi trên thread nào, overload của executor và hợp đồng Future để tránh “async giả” — phương thức trả kết quả đúng nhưng thực tế chạy đồng bộ.

**Tài liệu tham khảo:** Spring Framework Reference — [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html), [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html); Javadoc của **@EnableAsync**, **@Async**, **AopUtils**, **ThreadPoolTaskExecutor**; Java 17 Javadoc của **java.lang.reflect.Proxy** và **java.lang.reflect.InvocationHandler**.
