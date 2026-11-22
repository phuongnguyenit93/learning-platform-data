# Không chia sẻ SecurityContext có thể thay đổi giữa nhiều công việc trong Spring Security Servlet

## 1. Mục tiêu: bảo vệ danh tính khi xử lý bất đồng bộ

Khi một ứng dụng **Spring Security Servlet** chuyển việc từ request thread sang **ExecutorService**, **@Async**, **CompletableFuture** hoặc scheduler, lập trình viên thường muốn công việc nền biết người đã khởi tạo tác vụ. Một cách làm nguy hiểm là lấy **SecurityContextHolder.getContext()**, giữ nguyên đối tượng **SecurityContext**, rồi truyền cùng đối tượng ấy cho nhiều công việc.

**SecurityContext là đối tượng có thể thay đổi**: phương thức **setAuthentication(...)** thay Authentication mà context nắm giữ. Nếu nhiều tác vụ cùng sử dụng một instance, một tác vụ thay Authentication có thể khiến tác vụ khác đọc thấy danh tính và quyền không thuộc về nó. Hậu quả có thể là truy vấn sai tenant, xử lý dữ liệu dưới quyền user khác hoặc ghi audit sai.

Bài học này giúp bạn:
- Hiểu **SecurityContextHolder**, **ThreadLocal**, **SecurityContext** và **Authentication** khác nhau như thế nào.
- Phân biệt **truyền ngữ cảnh (propagation)** với **cách ly ngữ cảnh (isolation)**.
- Biết vì sao **setContext(...) không deep-copy SecurityContext**, và clearContext() không tự xóa một race đã xảy ra.
- Tái hiện lỗi bằng ví dụ **Java 17** có CountDownLatch để kết quả xác định.
- Tạo SecurityContext độc lập cho mỗi công việc, kiểm soát Authentication mutable và dọn ThreadLocal.
- Sử dụng wrapper **DelegatingSecurityContextRunnable/Executor** đúng mục đích, hiểu giới hạn khi chia sẻ mutable object.
- Ưu tiên truyền **actor ID bất biến + phân quyền lại theo nghiệp vụ** đối với các job chạy lâu.
- Thiết kế kiểm thử đồng thời, thread reuse, session concurrency, logout và thu hồi quyền.

**Phạm vi:** Spring Security Servlet. Spring WebFlux có cơ chế reactive context khác, không áp dụng nguyên xi các quy tắc dựa trên Servlet ThreadLocal.

## 2. Ba lớp trạng thái: ThreadLocal, SecurityContext, Authentication

### 2.1. SecurityContextHolder chứa tham chiếu cho thread hiện hành

Code đọc danh tính thông thường:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
Authentication auth = context.getAuthentication();
~~~

Trong Servlet stack, **SecurityContextHolder** thường sử dụng một chiến lược **ThreadLocal**. ThreadLocal cho phép thread A và thread B có những vị trí lưu riêng. Nhưng nếu cả hai vị trí trỏ tới **cùng một đối tượng**, việc có hai ThreadLocal slots **không tạo ra hai bản sao**.

~~~text
Worker thread A -> ThreadLocal A ---+
                                     +---> SecurityContext S
Worker thread B -> ThreadLocal B ---+              |
                                                    v
                                          Authentication = alice
~~~

Sau khi B gọi **S.setAuthentication(bob)**, cả hai thread có thể thấy S đang chứa bob. Tương tự như hai biến Java cùng trỏ đến một List mutable: biến khác tên không làm List thành hai đối tượng độc lập.

### 2.2. SecurityContext là vỏ mutable

SecurityContext có **getAuthentication()** và **setAuthentication(...)**. Để tạo đối tượng context mới:

~~~java
SecurityContext independent =
        SecurityContextHolder.createEmptyContext();
independent.setAuthentication(verifiedAuthentication);
~~~

Còn đây chỉ là lấy instance hiện hành:

~~~java
SecurityContext reference = SecurityContextHolder.getContext();
~~~

Nếu lưu **reference** vào static field, instance singleton hoặc nhiều Runnable, đó là **chia sẻ mutable object**. Gọi **SecurityContextHolder.setContext(reference)** trên một thread khác chỉ cài đặt tham chiếu đó vào SecurityContextHolder của thread mới; không sao chép deep và không đóng băng trạng thái.

### 2.3. Authentication và principal cũng có thể mutable

Ngay cả khi hai SecurityContexts khác nhau:

~~~text
SecurityContext A --+
                    +--> Authentication X --> mutable principal/details
SecurityContext B --+
~~~

chúng có thể dùng chung một **Authentication** hoặc một **principal** có thể thay đổi. Một số Authentication implementations cho phép thay **details**, xóa credentials hoặc chứa đối tượng domain/principal mutable. Vì vậy, **createEmptyContext() rồi gán nguyên original.getAuthentication() cho nhiều context chưa chắc cách ly hoàn toàn**.

Không có API deep-copy mọi Authentication một cách phổ quát và an toàn. Với async jobs dài hạn, phương án tốt hơn thường là chuyển **định danh và tham số bất biến**, rồi xác minh quyền tại thời điểm thực thi, thay vì chuyển nguyên SecurityContext hoặc các credentials/claims nhạy cảm.

## 3. Context propagation không đồng nghĩa context isolation

**Propagation:** làm sao tác vụ trên thread khác có thể nhận SecurityContext phù hợp?

**Isolation:** khi hai tác vụ chạy đồng thời, tác vụ A có thể bị B thay đổi principal/authority đang dùng không?

Đó là **hai tính chất độc lập**. Một wrapper có thể truyền đúng object đến worker thread, nhưng chính object đó vẫn có thể được dùng chung ở các tác vụ khác.

~~~text
Request: SecurityContext S (alice)
                 |
         +-------+--------+
         |                |
         v                v
   Async task A      Async task B
   setContext(S)     setContext(S)
   read: alice       S.setAuthentication(bob)
   read: bob         [thay đổi chung]
~~~

Một số hệ quả:
- **Authorization nhầm người:** task A xử lý dữ liệu alice nhưng sau đó đọc Authentication là bob.
- **Audit sai:** lệnh thực hiện bởi A lại mang actor name của B.
- **Tenant confusion:** A có thể truy cập nhầm dữ liệu tenant khác nếu service dựa vào context thay đổi.
- **Stale privilege:** context được capture trước logout hoặc revoke quyền vẫn dùng ở công việc nền chạy muộn.
- **Thread leak:** một thread pool quên clear context có thể làm job sau thấy danh tính của job trước.

**Đừng kết luận Spring Security tự lan truyền SecurityContext tới mọi thread.** Lỗi chia sẻ xuất hiện khi mã ứng dụng, wrapper, cấu hình session/repository hoặc một cơ chế propagation đã đưa **chung instance** vào các phạm vi xử lý. Ngược lại, một executor không được cấu hình propagation có thể chỉ thấy Authentication null.

## 4. Tình huống nguy hiểm thường gặp

### 4.1. Capture cùng context cho nhiều Runnable

~~~java
SecurityContext shared = SecurityContextHolder.getContext();

executor.execute(() -> {
    SecurityContextHolder.setContext(shared);
    try {
        processOrderA();
    } finally {
        SecurityContextHolder.clearContext();
    }
});

executor.execute(() -> {
    SecurityContextHolder.setContext(shared);
    try {
        processOrderB();
    } finally {
        SecurityContextHolder.clearContext();
    }
});
~~~

Đây là **trích đoạn anti-pattern**, không phải file Java độc lập. Cả hai tasks dùng một object. **clearContext()** chỉ dọn context của thread sau khi task kết thúc; nó không ngăn task B thay object trong lúc task A đang chạy.

### 4.2. Dùng context chung cho các wrapper

~~~java
SecurityContext shared = SecurityContextHolder.getContext();

Runnable a = new DelegatingSecurityContextRunnable(taskA, shared);
Runnable b = new DelegatingSecurityContextRunnable(taskB, shared);
~~~

**DelegatingSecurityContextRunnable** giúp đưa context vào thread khi delegate chạy và xử lý cleanup/restore theo contract, nhưng **không tự deep-copy shared**. Nếu shared bị đổi trong lúc tasks chờ hoặc chạy, các wrapper vẫn có thể thấy thay đổi.

### 4.3. Hai request đồng thời của cùng HttpSession

Trong một số thiết kế session-based tùy repository/lifecycle, hai request cùng session có thể tham chiếu tới một context chung. Nếu custom authentication code dùng **SecurityContextHolder.getContext().setAuthentication(newAuth)**, một request có thể ảnh hưởng request còn lại.

~~~text
Browser session S
    |                |
    v                v
Request A          Request B
    |                |
    +---- context X --+
               |
       setAuthentication(...)
~~~

Đây là **một tình huống cần kiểm thử trên cấu hình thực**, không phải khẳng định mọi version/repository đều chia sẻ một instance. Tạo context mới khi authentication infrastructure cần thay Authentication giúp tránh đột biến context cũ đang được tham chiếu.

### 4.4. MODE_INHERITABLETHREADLOCAL hoặc MODE_GLOBAL

**MODE_INHERITABLETHREADLOCAL** cho thread con kế thừa giá trị tại thời điểm thread được tạo; điều này không đồng nghĩa an toàn với thread pool được tái sử dụng cho các user khác nhau. **MODE_GLOBAL** không phù hợp với server nhiều users vì tạo trạng thái chung. Không chọn các mode này chỉ để “chữa” @Async không thấy Authentication.

## 5. Ví dụ Java 17 có thể chạy: shared context vs isolated context

Dùng Spring Security Core để tái hiện **object reference sharing**, không cần khởi động HTTP server. Bài mẫu có **CountDownLatch** nhằm ép các bước đọc/thay đổi/đọc lại diễn ra theo đúng thứ tự, tránh test lúc đậu lúc rớt do Thread.sleep.

Kết quả mong muốn:

~~~text
shared: alice -> bob
isolated: alice -> alice, bob -> carol
~~~

Tình huống đầu tiên cố tình **sai**; tình huống thứ hai sử dụng **context riêng** cho mỗi job. Authentication trong bài là **test fixture đã được đánh dấu authenticated chỉ để mô phỏng**; tuyệt đối không tạo Authentication tương tự từ một username chưa xác thực trong API thật.

Cấu trúc Maven:

~~~text
context-isolation/
├── pom.xml
└── src/
    ├── main/java/example/context/ContextIsolationDemo.java
    └── test/java/example/context/ContextIsolationDemoTest.java
~~~

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>context-isolation</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-core</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. src/main/java/example/context/ContextIsolationDemo.java

~~~java
package example.context;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

public final class ContextIsolationDemo {
    private ContextIsolationDemo() {
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            System.out.println("shared: " + sharedRace(pool));
            System.out.println("isolated: " + isolatedContexts(pool));
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    // Chỉ để mô phỏng Authentication đáng tin trong demo.
    // Không chấp nhận username tùy ý từ request thật rồi tạo token này.
    private static Authentication auth(String name) {
        return UsernamePasswordAuthenticationToken.authenticated(
                name, null,
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private static SecurityContext newContext(String name) {
        SecurityContext ctx = SecurityContextHolder.createEmptyContext();
        ctx.setAuthentication(auth(name));
        return ctx;
    }

    private static void await(CountDownLatch latch)
            throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Latch timed out");
        }
    }

    // SAI có chủ đích: cả hai job thay/đọc cùng một instance.
    static String sharedRace(ExecutorService pool) throws Exception {
        SecurityContext shared = newContext("alice");
        CountDownLatch readerReady = new CountDownLatch(1);
        CountDownLatch changed = new CountDownLatch(1);

        Future<String> reader = pool.submit(() -> {
            SecurityContextHolder.setContext(shared);
            try {
                String before = SecurityContextHolder.getContext()
                        .getAuthentication().getName();
                readerReady.countDown();
                await(changed);
                String after = SecurityContextHolder.getContext()
                        .getAuthentication().getName();
                return before + " -> " + after;
            } finally {
                SecurityContextHolder.clearContext();
            }
        });

        Future<?> writer = pool.submit(() -> {
            await(readerReady);
            shared.setAuthentication(auth("bob"));
            changed.countDown();
            return null;
        });

        writer.get(10, TimeUnit.SECONDS);
        return reader.get(10, TimeUnit.SECONDS);
    }

    // ĐÚNG VỀ OBJECT ISOLATION: mỗi task có context riêng.
    static String isolatedContexts(ExecutorService pool) throws Exception {
        SecurityContext alice = newContext("alice");
        SecurityContext bob = newContext("bob");
        CountDownLatch readerReady = new CountDownLatch(1);
        CountDownLatch changed = new CountDownLatch(1);

        Future<String> reader = pool.submit(() -> {
            SecurityContextHolder.setContext(alice);
            try {
                String before = SecurityContextHolder.getContext()
                        .getAuthentication().getName();
                readerReady.countDown();
                await(changed);
                String after = SecurityContextHolder.getContext()
                        .getAuthentication().getName();
                return before + " -> " + after;
            } finally {
                SecurityContextHolder.clearContext();
            }
        });

        Future<String> writer = pool.submit(() -> {
            SecurityContextHolder.setContext(bob);
            try {
                String before = SecurityContextHolder.getContext()
                        .getAuthentication().getName();
                await(readerReady);
                bob.setAuthentication(auth("carol"));
                changed.countDown();
                String after = SecurityContextHolder.getContext()
                        .getAuthentication().getName();
                return before + " -> " + after;
            } finally {
                SecurityContextHolder.clearContext();
            }
        });

        String bobResult = writer.get(10, TimeUnit.SECONDS);
        String aliceResult = reader.get(10, TimeUnit.SECONDS);
        return aliceResult + ", " + bobResult;
    }
}
~~~

**Đọc code:** reader của sharedRace gắn **shared** vào ThreadLocal rồi đọc alice. Writer chờ reader bắt đầu, sau đó thay Authentication của chính **shared** thành bob. Reader được mở latch và đọc lại: nó thấy bob vì cùng object. Trong isolatedContexts, alice và bob được tạo từ **hai lần createEmptyContext()**, cùng với hai Authentication test độc lập; writer sửa bob thành carol, reader của alice không thay đổi.

Bước **clearContext()** trong finally tránh rò ThreadLocal khi thread pool reuse. Nhưng nó **không thể sửa race ở sharedRace** vì thay đổi object đã xảy ra trước cleanup.

### 5.3. Lệnh chạy và stdout dự kiến

Trong thư mục gốc Maven:

~~~bash
mvn test
mvn -q exec:java -Dexec.mainClass=example.context.ContextIsolationDemo
~~~

Hai dòng stdout của chương trình, không tính log Maven/tooling:

~~~text
shared: alice -> bob
isolated: alice -> alice, bob -> carol
~~~

CountDownLatch buộc thứ tự thay vì dùng sleep, nên chương trình không dựa vào tình cờ race diễn ra. Để chạy thực tế cần Java 17, Maven và kết nối tới nguồn dependency trong lần tải thư viện đầu.

## 6. Unit tests với JUnit

Tạo file **src/test/java/example/context/ContextIsolationDemoTest.java**:

~~~java
package example.context;

import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class ContextIsolationDemoTest {

    @Test
    void sharedContextChangesAnotherTasksIdentity()
            throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            assertEquals("alice -> bob",
                    ContextIsolationDemo.sharedRace(pool));
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }

    @Test
    void independentContextsRemainIsolated()
            throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            assertEquals("alice -> alice, bob -> carol",
                    ContextIsolationDemo.isolatedContexts(pool));
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
~~~

Hai test xác nhận:
1. **Negative case:** nếu dùng chung object mutable, một tác vụ có thể quan sát principal bị thay bởi tác vụ khác.
2. **Positive case:** hai contexts độc lập không ảnh hưởng danh tính của nhau khi một context bị thay Authentication.

Đây là **unit test object isolation**, chưa chứng minh tích hợp session, Servlet filters hoặc executor do Spring Boot quản lý. Cần test riêng integration thật.

## 7. Tạo SecurityContext mới: đúng nhưng chưa đủ

Khi **authentication infrastructure** đã xác minh principal và cần đặt một Authentication mới, mô hình tránh mutating context cũ:

~~~java
SecurityContext fresh =
        SecurityContextHolder.createEmptyContext();
fresh.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(fresh);
~~~

Đây là **trích đoạn minh họa**, không phải login endpoint hoàn chỉnh. **verifiedAuthentication** phải có nguồn xác thực tin cậy. Không được tạo UsernamePasswordAuthenticationToken với isAuthenticated=true chỉ vì request đưa username.

Trái lại, đoạn sau thay Authentication trên object đang có:

~~~java
SecurityContextHolder.getContext()
        .setAuthentication(verifiedAuthentication);
~~~

Nếu context này vẫn được request khác hoặc Runnable khác tham chiếu, sửa đó có thể ảnh hưởng họ. Cần hiểu SecurityContextRepository, HttpSession và lifecycle trên phiên bản Spring Security đang chạy.

### 7.1. Bẫy shallow copy

~~~java
SecurityContext original = SecurityContextHolder.getContext();
SecurityContext first = SecurityContextHolder.createEmptyContext();
SecurityContext second = SecurityContextHolder.createEmptyContext();

first.setAuthentication(original.getAuthentication());
second.setAuthentication(original.getAuthentication());
~~~

**first != second** nhưng cả hai có thể vẫn dùng **chung một instance Authentication**. Một Authentication hoặc principal mutable bị thay trong job đầu tiên vẫn có thể ảnh hưởng job thứ hai. Vì thế **chỉ tách vỏ SecurityContext chưa tự bảo đảm tách tất cả mutable data**. Không có một cách deep-copy Authentication phổ quát cho mọi loại OAuth2/JWT/form login.

### 7.2. Snapshot quyền có thể hết hiệu lực

Ngay cả khi context và Authentication không bị task khác đổi, quyền có thể **bị thu hồi** sau khi lập lịch. Một job chạy 1 giờ sau khi user logout không thể mặc định sử dụng mọi quyền ở thời điểm enqueue. Phải có policy rõ về **quyền tại thời điểm yêu cầu**, **quyền tại thời điểm thực hiện**, token expiry, service identity và user delegation.

**Object isolation** ngăn race giữa tasks; **fresh authorization** giải quyết quyền còn hiệu lực; **least privilege** giới hạn tác động của từng job. Ba mục tiêu này không thay thế nhau.

## 8. DelegatingSecurityContextRunnable và Executor

Spring Security có wrappers như **DelegatingSecurityContextRunnable**, **DelegatingSecurityContextExecutor**, **DelegatingSecurityContextExecutorService** và **DelegatingSecurityContextAsyncTaskExecutor** để truyền SecurityContext vào công việc ở luồng khác.

Ví dụ trích đoạn:

~~~java
SecurityContext context =
        SecurityContextHolder.getContext();

Runnable wrapped = new DelegatingSecurityContextRunnable(
        () -> performWork(), context);

executor.execute(wrapped);
~~~

Wrapper có nhiệm vụ thiết lập context của delegate khi chạy và cleanup/restore theo contract. Nhưng **nó không deep-copy context**. Nếu dùng cùng **context** làm tham số cho nhiều wrappers thì vẫn có thể chia sẻ object mutable.

Lưu ý hai trường hợp:
- **Explicit context:** truyền một object SecurityContext đã có vào wrapper; các tác vụ có thể nhìn thấy thay đổi trên object đó.
- **Capture context khi wrap/submit:** một số constructor/executor wrappers lấy context hiện hành ở thời điểm phù hợp theo API; **capture không đồng nghĩa snapshot bất biến**.

Muốn mỗi tác vụ có object riêng, phải chủ động xác định **ownership** và dữ liệu Authentication/principal. Với **@Async**, cấu hình **DelegatingSecurityContextAsyncTaskExecutor** giúp giải quyết propagation, nhưng không biến mọi biến đổi Authentication thành thread-safe.

Trích đoạn dành cho trường hợp thật sự cần SecurityContext trong một job:

~~~java
SecurityContext taskContext =
        SecurityContextHolder.createEmptyContext();
taskContext.setAuthentication(trustedAuthForThisTask);

Runnable task = new DelegatingSecurityContextRunnable(
        () -> performWork(), taskContext);
executor.execute(task);
~~~

**trustedAuthForThisTask** phải là kết quả xác thực do hệ thống kiểm soát, và không được dùng chung như một đối tượng mutable cho nhiều tasks. Đoạn này không phải file Java đầy đủ; performWork, trustedAuthForThisTask và executor phải được ứng dụng khai báo. Nếu chỉ cần actor ID, nên tránh truyền nguyên context.

## 9. Trong Spring MVC: thường chỉ cần actor ID bất biến

Đối với background job, cách dễ kiểm thử hơn là controller đã xác thực **trích một identifier ổn định**, gửi command DTO bất biến, rồi worker kiểm tra quyền theo contract nghiệp vụ.

Ví dụ minh họa trong @RestController:

~~~java
@PostMapping("/reports")
ResponseEntity<Void> queue(
        @CurrentSecurityContext(
                expression = "authentication") Authentication auth,
        @RequestBody CreateReportRequest request) {

    String actorId = auth.getName();
    jobQueue.enqueue(new ReportJob(actorId, request.reportId()));
    return ResponseEntity.accepted().build();
}

record ReportJob(String actorId, long reportId) {}
~~~

Đây là **trích đoạn**, không phải file standalone: cần import Spring MVC/Security types, khai báo CreateReportRequest, jobQueue và config. **actorId** là String bất biến, không phải SecurityContext mutable; không serialize Authentication hoặc access token vào hàng đợi.

Tuy vậy, cách này **không tự giải quyết authorization**:
- Controller phải chạy sau cơ chế authentication phù hợp, trong endpoint được bảo vệ.
- **auth.getName()** phải được diễn giải theo contract identity; với đa tenant/issuer có thể cần **issuer + subject + tenant**, không chỉ email/display name.
- Report ID do client gửi có thể thuộc người khác. Check ownership/ACL khi enqueue và có thể phải **check lại lúc execute**.
- Worker dùng service credentials phải phân biệt **actor đã yêu cầu** và **principal thực thi**, tránh giả lập một Authentication authenticated từ actorId không đáng tin.
- Job payload cần integrity/idempotency/expiry và auditing phù hợp.
- Với browser gửi cookie tự động, các request POST vẫn cần **CSRF protection** thích hợp; chuyển việc sang async không làm CSRF biến mất.

### Khi nào phải chuyển SecurityContext?

Có thể cần nếu API cũ hoặc method-security code đọc trực tiếp SecurityContextHolder trong worker. Khi ấy dùng wrapper chuẩn với một context được sở hữu riêng và lifetime rõ ràng, kiểm thử quyền; tránh tự quản lý static context. Trong long-running job, không giả định context được snapshot lúc enqueue cho phép truy cập vô hạn sau logout.

## 10. Servlet session concurrency và thay đổi danh tính

Khi web app dùng HttpSession, hai request cùng session có thể chạy song song. Tùy repository và cách lưu context, chúng có thể tham chiếu một SecurityContext được dùng chung hoặc có cập nhật session cạnh tranh. Nếu custom filter hoặc controller thay Authentication **trên object cũ** thì xuất hiện nguy cơ ảnh hưởng request còn lại.

Các tình huống cần xét:
- Hai tab browser đồng thời dùng cùng session.
- Một request đang xử lý lâu, request khác logout hoặc đổi tài khoản.
- Re-authentication hoặc step-up authentication khi một request khác đang đọc authorities.
- API có web session và Bearer token trong các SecurityFilterChain khác nhau.
- Một tác vụ nền cầm reference context sống lâu hơn request khởi tạo.
- Session invalidate/role revocation trong lúc job chưa hoàn tất.

Để phòng ngừa, **đừng tự dùng SecurityContextHolder làm kho trạng thái global**, tránh sửa object đang có nếu nó có thể được chia sẻ; để authentication infrastructure và repository quản lý lifecycle đúng phiên bản. Cần kiểm thử concurrency với hệ thống session thật, không suy luận chỉ từ một request MockMvc.

## 11. ThreadLocal cleanup và context restoration

Một executor dùng lại thread. Nếu task A cài context alice mà không dọn, task B có thể tiếp tục thấy alice dù task B do bob khởi tạo. Ví dụ nguyên tắc cho worker thread riêng:

~~~java
SecurityContextHolder.setContext(contextForThisTask);
try {
    doWork();
} finally {
    SecurityContextHolder.clearContext();
}
~~~

**clearContext() là bắt buộc trong code tự quản lý context** để không rò dữ liệu giữa các lần reuse, nhưng nó **không sửa được việc hai tasks dùng chung object trước đó**.

Nếu công việc chạy lồng trong một thread đang có context hợp lệ, không phải lúc nào clear vô điều kiện cũng đúng: có thể cần **khôi phục context trước đó**. Nên dùng wrapper/strategy chuẩn của Spring Security cho tác vụ nested thay vì tự viết toàn bộ lifecycle tùy tiện.

Không chuyển sang **MODE_GLOBAL** hoặc **MODE_INHERITABLETHREADLOCAL** làm “giải pháp chung” cho pooled executor. Thread mới có thể kế thừa context một thời điểm, nhưng worker thread tái sử dụng giữa users có lifecycle khác.

## 12. Chiến lược kiểm thử thực tế

| Test | Mục tiêu |
| --- | --- |
| Shared mutable context với CountDownLatch | Chứng minh A có thể thấy Authentication mới của B |
| Independent contexts | Chứng minh mutation ở context B không ảnh hưởng context A |
| Thread pool chỉ có một worker, chạy hai jobs lần lượt | Phát hiện context còn sót sau job trước |
| Hai users alice/bob chạy công việc đồng thời | Đảm bảo actor/tenant không trộn |
| Hai request cùng HttpSession | Kiểm thử thay đổi Authentication/logout đồng thời |
| Job chờ lâu sau khi user logout | Kiểm tra policy về quyền còn hiệu lực |
| Authorities bị revoke khi job đã enqueue | Kiểm tra re-authorization tại thời điểm chạy |
| Task thất bại với exception | Kiểm tra context cleanup trong finally |
| Nested wrapper/executor invocation | Kiểm tra restore context caller |
| Long-running task được retry | Kiểm tra idempotency, current permissions và audit |

### 12.1. Kiểm tra thread reuse

Trích đoạn định hướng test, không standalone:

~~~java
ExecutorService oneWorker = Executors.newSingleThreadExecutor();
try {
    oneWorker.submit(() -> {
        SecurityContextHolder.setContext(contextForAlice);
        try {
            assertAlice();
        } finally {
            SecurityContextHolder.clearContext();
        }
    }).get();

    oneWorker.submit(() -> {
        assertNoAuthenticationFromPreviousTask();
    }).get();
} finally {
    oneWorker.shutdownNow();
}
~~~

Các helper **assertAlice**, **assertNoAuthenticationFromPreviousTask** và biến **contextForAlice** cần được định nghĩa trong test thật. Dùng một worker để hai tasks chắc chắn chạy cùng thread, xác nhận **SecurityContextHolder.getContext().getAuthentication()** không còn Authentication từ task trước.

### 12.2. Kiểm tra danh tính ở nhiều điểm

Một integration test đáng tin cần đo identity tại **start**, **trước khi gọi service**, **trước commit** và **khi ghi audit**:

~~~text
Task A: alice -> alice -> alice -> alice
Task B: bob   -> bob   -> bob   -> bob
~~~

Cần assert không chỉ status mà còn **record owner/tenant** và actor thực tế. Khi dùng async Servlet/Callable, custom Executor hoặc @Async, phải test **đúng execution model và security chain** production. Kiểm thử .with(user(...)) của MockMvc không chứng minh mọi context propagation hoặc quyền OIDC/JWT thực tế.

## 13. Các sai lầm hay gặp

1. **“ThreadLocal là thread-safe cho mọi object.”** Sai: các slots có thể trỏ cùng object mutable.
2. **“setContext() tạo bản copy.”** Sai: nó cài tham chiếu context.
3. **“DelegatingSecurityContextRunnable deep-copy Authentication.”** Sai: wrapper chủ yếu xử lý propagation/lifecycle.
4. **“createEmptyContext() rồi set cùng Authentication cũ là deep-copy.”** Sai: Auth/principal còn có thể dùng chung.
5. **“clearContext() loại bỏ race.”** Sai: nó dọn thread sau khi chạy, không ngăn task khác mutate object trong lúc chạy.
6. **“@Async sẽ tự có Authentication đúng.”** Không chắc, tùy cấu hình context propagation và executor.
7. **“Có username thì tạo một authenticated token cho job được.”** Sai khi username chưa được xác minh; sẽ bypass authentication.
8. **“Job đã được phép lúc enqueue thì mãi được phép.”** Không mặc nhiên, quyền có thể bị revoke hoặc thay đổi.
9. **“Chia sẻ context qua static field giúp dễ truy cập.”** Rất nguy hiểm: có thể khiến nhiều users dùng chung danh tính.
10. **“Chỉ cần unit test chạy 200.”** Không đủ; cần concurrency tests, cleanup tests và authorization/resource ownership.
11. **“Session được Spring quản lý thì mọi custom mutation đều an toàn.”** Không, custom filters có thể đột biến một context được tham chiếu ở request khác.
12. **“Không cần phân biệt audit initiator và executor.”** Sai: một job có thể do user đặt lịch nhưng chạy với service credentials khác.

## 14. Checklist production

- [ ] Xác định task thực sự cần SecurityContext hay chỉ cần actor ID/tenant ID.
- [ ] Không đưa SecurityContext vào static field/singleton/cache dùng chung các users.
- [ ] Không dùng chung một instance mutable cho nhiều tasks độc lập.
- [ ] Nếu tạo context riêng, kiểm tra cả Authentication/principal/details còn dùng chung hay không.
- [ ] Có lifecycle rõ ràng: capture, submit, start, finish, cleanup/restore.
- [ ] Tránh tự thay Authentication trên context có thể được request/task khác tham chiếu.
- [ ] Dùng wrapper Spring Security đúng API nếu cần propagation, không giả định nó tạo immutable snapshot.
- [ ] Tránh MODE_GLOBAL và lạm dụng MODE_INHERITABLETHREADLOCAL với pooled threads.
- [ ] Không tạo authenticated token từ dữ liệu caller tự khai báo.
- [ ] Xác định chính sách re-authorization khi job chạy sau logout hoặc thu hồi quyền.
- [ ] Không truyền raw credentials/access token/refresh token qua queue khi không cần.
- [ ] Có tests shared/isolated, reuse, concurrency, session, exception cleanup, role revocation.
- [ ] Có audit actor/tenant/resource rõ ràng và cảnh báo cross-user data access.
- [ ] Vẫn thực thi security rules và CSRF khi trình duyệt dùng session/cookie.

## 15. Câu hỏi tự đánh giá

1. **SecurityContextHolder dùng ThreadLocal, vậy SecurityContext tự bất biến?** Không; ThreadLocal chỉ cất tham chiếu theo thread.
2. **Hai thread có thể giữ cùng SecurityContext?** Có, nếu code/wrapper/repository truyền cùng instance.
3. **Một task gọi setAuthentication(bob) trên context dùng chung sẽ tác động ra sao?** Task khác có thể thấy bob.
4. **clearContext() giải quyết điều gì?** Dọn ThreadLocal sau khi làm việc; không tách object đang dùng chung.
5. **DelegatingSecurityContextRunnable có deep-copy object không?** Không.
6. **createEmptyContext() + original.getAuthentication() đã cách ly hoàn toàn?** Chưa chắc; Authentication có thể vẫn là cùng reference.
7. **Có phải mọi background job cần SecurityContext?** Không; nhiều job chỉ cần actor ID bất biến cùng policy rõ ràng.
8. **User mất quyền sau khi enqueue thì sao?** Thiết kế re-authorization/revocation theo yêu cầu nghiệp vụ.
9. **Vì sao dùng CountDownLatch thay Thread.sleep trong unit test?** Để khóa thứ tự sự kiện, giúp kiểm thử xác định.
10. **Điểm khác propagation và isolation?** Propagation đưa context đến task; isolation ngăn task này đổi context của task kia.

**Kết luận:** Trong Spring Security Servlet, **SecurityContext là mutable object**. Chuyển chung một tham chiếu giữa nhiều công việc có thể làm danh tính và quyền của task này bị task khác thay đổi. Hãy **cách ly context và authentication state theo tác vụ**, quản lý cleanup/restore đúng lifecycle, không dùng wrapper propagation như bằng chứng isolation, và với công việc nền dài hạn ưu tiên **immutable identity + authorization theo thời điểm thực thi**.
