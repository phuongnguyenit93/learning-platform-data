# Đo đạc lời gọi lồng nhau và đệ quy qua Spring AOP proxy

## 1. Mục tiêu và phạm vi

Trong Spring AOP, advice đo thời gian chỉ chạy khi một lời gọi phương thức **đi qua Spring proxy** và khớp pointcut. Điều này quyết định liệu một lời gọi lồng nhau, một bước đệ quy hay chỉ lời gọi ngoài cùng xuất hiện trong số liệu quan sát.

Sau bài này, bạn có thể:
- Phân biệt lời gọi Java nội bộ trong cùng bean với lời gọi qua proxy do Spring quản lý.
- Giải thích vì sao một lần gọi từ ngoài vào bean có thể tạo nhiều lần chạy `@Around`, hoặc chỉ một lần dù có nhiều phương thức thực thi.
- Đo từng lần đi qua proxy, giữ nguyên kết quả/ngoại lệ, và quản lý mức lồng nhau theo thread.
- Lựa chọn cách tổng hợp **inclusive time**, **exclusive time** và chỉ đo lần ngoài cùng theo mục tiêu quan sát.
- Tránh hiểu sai số liệu khi kết hợp Spring AOP với transaction, async, luồng xử lý reactive hoặc lời gọi chạy trên thread khác.

Bài tập trung vào **cơ chế proxy và advice của Spring AOP**; không triển khai lại lý thuyết AspectJ/AOP tổng quát.

## 2. Chính xác khi nào advice đo thời gian chạy?

Giả sử một Spring bean có hai phương thức công khai `outer()` và `inner()`. Có ba trường hợp khác nhau:

| Đường gọi | Có đi qua Spring proxy tại điểm gọi đó? | Advice khớp `inner()` có chạy? |
| --- | --- | --- |
| Bean khác gọi `service.inner()`, với `service` là Spring proxy | Có | Có |
| `outer()` gọi `this.inner()` hoặc gọi trực tiếp `inner()` trong cùng đối tượng đích | Không | Không |
| `outer()` lấy proxy của bean rồi gọi `proxy.inner()` | Có | Có |

Khi mã bên ngoài gọi `proxy.outer()`, lời gọi `outer()` được advice xử lý. Sau đó, nếu thân `outer()` gọi trực tiếp `inner()`, lời gọi bên trong **không tự quay lại proxy**. Vì vậy việc thêm pointcut cho `inner()` không làm cho lời gọi nội bộ đó được đo riêng.

Tương tự với đệ quy:

~~~text
otherBean -> proxy.outer()        => advice outer
                  |
                  +-> this.inner() => không có advice inner
                         |
                         +-> this.inner() => không có advice inner

otherBean -> proxy.outer()        => advice outer
                  |
                  +-> proxy.inner(2) => advice inner(2)
                           |
                           +-> proxy.inner(1) => advice inner(1)
                                    |
                                    +-> proxy.inner(0) => advice inner(0)
~~~

Một phương thức có thể chạy đệ quy nhiều lần mà advice chỉ thấy **một lần** nếu các bước sau đầu tiên đều gọi trực tiếp vào `this`. Điều này không có nghĩa Spring AOP “bỏ sót” lời gọi đã qua proxy: các lần lồng nhau ấy chưa từng đi qua proxy.

Spring AOP ở đây sử dụng proxy JDK hoặc proxy dựa trên lớp (thường là CGLIB), theo cấu hình. Với proxy JDK, lời gọi phải đi qua giao diện được proxy cung cấp; với proxy dựa trên lớp, phương thức `final` không thể được override để advice áp dụng. Lời gọi `private`, constructor và mã không đi qua Spring proxy cũng không trở thành method join point được đo bằng proxy Spring AOP.

## 3. Ví dụ Spring Boot có thể chạy: trực tiếp so với qua proxy

Ví dụ dùng **Java 17+**, **Spring Boot 3.3.x**, Spring AOP và một bean `WorkService`. Việc dùng `ObjectProvider<WorkService>` chỉ nhằm minh họa cách lấy **Spring-managed proxy ngay tại thời điểm gọi** mà không phải tự tạo đối tượng bằng `new`.

Cấu trúc dự án:

~~~text
pom.xml
src/main/java/com/example/aopdemo/
    DemoApplication.java
    WorkService.java
    TimingAspect.java
~~~

### 3.1. Maven dependency

Tệp `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>aop-recursion-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
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

`spring-boot-starter-aop` cung cấp các phụ thuộc AOP cần thiết và cấu hình tự động Spring AOP trong ứng dụng Spring Boot. Các ví dụ bên dưới giả định cấu hình proxy mặc định của Spring Boot dùng class-based proxy; `WorkService` và các phương thức của nó không khai báo `final`.

### 3.2. Service: hai con đường đệ quy

Tệp `src/main/java/com/example/aopdemo/WorkService.java`:

~~~java
package com.example.aopdemo;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class WorkService {
    private final ObjectProvider<WorkService> self;

    public WorkService(ObjectProvider<WorkService> self) {
        this.self = self;
    }

    public void direct() {
        recurseDirect(2); // gọi trên this, bỏ qua proxy
    }

    public void recurseDirect(int remaining) {
        if (remaining > 0) {
            recurseDirect(remaining - 1); // vẫn trên this
        }
    }

    public void throughProxy() {
        self.getObject().recurseProxy(2); // đi qua Spring proxy
    }

    public void recurseProxy(int remaining) {
        if (remaining > 0) {
            self.getObject().recurseProxy(remaining - 1);
        }
    }
}
~~~

Trong `direct()`, mọi lời gọi `recurseDirect` đều là self-invocation. Trong `throughProxy()`, mỗi lần gọi `recurseProxy` dùng bean lấy từ container; khi Spring áp dụng aspect cho bean này, đó là proxy. Việc gọi `getObject()` tại runtime tránh việc bắt Spring phải giải quyết một tham chiếu tự thân trực tiếp trong constructor.

**Lưu ý thiết kế:** Tự gọi qua proxy hữu ích để chứng minh hành vi AOP nhưng làm service phụ thuộc gián tiếp vào cơ chế proxy. Trong mã nghiệp vụ thường ưu tiên tách thao tác cần advice sang **một Spring bean khác**, sau đó gọi bean đó bằng injection. Tránh tạo bean thủ công với `new WorkService(...)` vì đối tượng ấy không được Spring AOP quản lý.

### 3.3. Aspect: đo mỗi lần proxy gọi vào service

Tệp `src/main/java/com/example/aopdemo/TimingAspect.java`:

~~~java
package com.example.aopdemo;

import java.util.Arrays;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TimingAspect {
    private final ThreadLocal<Integer> depth =
            ThreadLocal.withInitial(() -> 0);

    @Around("execution(public * com.example.aopdemo.WorkService.*(..))")
    public Object measure(ProceedingJoinPoint joinPoint) throws Throwable {
        int currentDepth = depth.get();
        depth.set(currentDepth + 1);
        long started = System.nanoTime();

        try {
            return joinPoint.proceed();
        } finally {
            long elapsed = System.nanoTime() - started;

            if (currentDepth == 0) {
                depth.remove();
            } else {
                depth.set(currentDepth);
            }

            System.out.printf(
                    "depth=%d | %s%s | %.3f ms%n",
                    currentDepth,
                    joinPoint.getSignature().getName(),
                    Arrays.toString(joinPoint.getArgs()),
                    elapsed / 1_000_000.0
            );
        }
    }
}
~~~

Các quyết định có chủ đích:

1. `@Around` bao trọn `proceed()` để đo thời gian thực thi tại **lần gọi qua proxy tương ứng**. `return joinPoint.proceed()` giữ nguyên giá trị trả về, kể cả khi ví dụ hiện tại dùng `void`.
2. `finally` vẫn chạy khi nghiệp vụ ném ngoại lệ, và ngoại lệ gốc tiếp tục truyền ra ngoài. Aspect không âm thầm chuyển một lần thực thi lỗi thành thành công.
3. `System.nanoTime()` dùng đo khoảng thời gian trôi qua (elapsed time), khác `System.currentTimeMillis()` dùng thời gian lịch.
4. `ThreadLocal` đánh dấu mức lồng nhau **trên cùng một thread**. Trước khi thoát advice phải khôi phục mức trước đó; ở mức gốc dùng `remove()` để không giữ state trên thread được tái sử dụng.
5. `depth=0` là lần advice ngoài cùng **trong chuỗi lời gọi đang đo của thread này**; `depth=1` là lời gọi qua proxy nằm trong nó. Đây là độ sâu của advice, không phải độ sâu stack Java hay số bước đệ quy thực tế.
6. `System.out.printf` thích hợp cho bài thực hành; trong ứng dụng thật, ưu tiên hệ thống metrics/tracing và tránh log từng lời gọi nóng.

Pointcut chỉ chọn các phương thức `public` của `WorkService`, giúp thấy chính xác bốn tên phương thức trong ví dụ. Nếu có nhiều aspect, `@Order` và thứ tự interceptor có thể làm điểm bắt đầu/kết thúc phép đo khác nhau; số liệu chỉ mô tả vùng thực thi nằm trong advice này.

### 3.4. Chạy hai kịch bản

Tệp `src/main/java/com/example/aopdemo/DemoApplication.java`:

~~~java
package com.example.aopdemo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner run(WorkService service) {
        return args -> {
            System.out.println("== DIRECT ==");
            service.direct();

            System.out.println("== THROUGH PROXY ==");
            service.throughProxy();
        };
    }
}
~~~

Từ thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Bỏ qua log khởi động Spring Boot, phần log của ví dụ có **thứ tự** như sau; giá trị thời gian thực tế sẽ khác ở mỗi lần chạy:

~~~text
== DIRECT ==
depth=0 | direct[] | <elapsed> ms
== THROUGH PROXY ==
depth=3 | recurseProxy[0] | <elapsed> ms
depth=2 | recurseProxy[1] | <elapsed> ms
depth=1 | recurseProxy[2] | <elapsed> ms
depth=0 | throughProxy[] | <elapsed> ms
~~~

`recurseDirect(2)`, `recurseDirect(1)`, `recurseDirect(0)` **có được thực thi**, nhưng không có dòng đo riêng. Ngược lại, `recurseProxy(2)`, `recurseProxy(1)`, `recurseProxy(0)` đều đi qua proxy; mỗi lời gọi tạo một lượt advice. Log được in ở `finally`, nên xuất hiện theo thứ tự **kết thúc từ sâu nhất ra ngoài cùng**, không phải thứ tự bắt đầu.

Lưu ý: chuỗi `<elapsed>` ở trên là **ký hiệu minh họa**, không phải stdout nguyên văn. Chương trình sẽ in một số dấu phẩy động với ba chữ số thập phân tại vị trí đó, tùy máy và thời điểm chạy.

## 4. Hiểu đúng cách cộng/trừ thời gian

Gọi `T(X)` là khoảng thời gian đo tại advice bọc lời gọi `X`.

- **Inclusive time** của `outer`: tính thời gian nằm trong `outer`, bao gồm thời gian của các lời gọi con chạy đồng bộ bên trong nó.
- **Exclusive/self time** của `outer`: gần đúng bằng thời gian inclusive trừ thời gian inclusive của các **lời gọi con trực tiếp đã đo, không chồng lấn**.
- **Số lần advice chạy**: số lần *cross proxy boundary* khớp pointcut, không nhất thiết bằng số lời gọi Java hoặc số tầng đệ quy thực.

Ví dụ thời gian minh họa: nếu `outer` mất 12 ms và một lời gọi con trực tiếp đã đo mất 7 ms, thì exclusive time của `outer` xấp xỉ 5 ms. Khi `outer` chứa `childA` và `childB` lồng nhau, phải tránh trừ một lần thời gian của cháu rồi lại trừ thông qua thời gian của con.

**Sai lầm thường gặp:** cộng tất cả inclusive time của các lời gọi đệ quy rồi gọi kết quả là tổng thời gian xử lý. Khi lời gọi cha chứa lời gọi con, phép cộng ấy **đếm lặp** thời gian con trong cha. Để đo latency của cả tác vụ, lấy thời gian advice ngoài cùng hoặc một timer bọc toàn bộ tác vụ; để phân tích từng tầng, giữ separate metrics cho từng invocation.

Một cách tính exclusive time trong lời gọi đồng bộ cùng thread là dùng `ThreadLocal<Deque<Frame>>`:

~~~text
Khi vào advice:
    tạo frame {startedAt, childInclusiveNanos=0}
    push frame lên stack

Khi ra advice (trong finally):
    inclusive = nanoTime() - frame.startedAt
    exclusive = inclusive - frame.childInclusiveNanos
    pop frame
    nếu stack còn frame cha:
        frameCha.childInclusiveNanos += inclusive
    ghi metric cho frame vừa hoàn thành
    nếu stack rỗng: remove ThreadLocal
~~~

Đây là **thuật toán minh họa**, không phải lớp Java độc lập biên dịch. Chỉ trừ thời gian của các frame con trực tiếp. Cần xác định liệu thời gian ghi metric/logging của advice con có nằm trong thời gian đo cha hay không; phép trừ dựa trên mốc thời gian không đồng nhất sẽ tạo sai số. Phép tính này cũng không thể áp dụng nguyên xi cho các nhánh chạy song song.

## 5. Ba chính sách đo và cách chọn

| Chính sách | Dữ liệu thu được | Khi nên dùng | Điều cần kiểm soát |
| --- | --- | --- | --- |
| Đo mọi lần qua proxy | Một sample cho từng lời gọi con/đệ quy được intercept | Phân tích hotspot, latency từng method hoặc từng tầng | Số sample có thể tăng mạnh khi đệ quy |
| Đo chỉ mức ngoài cùng của advice (`depth == 0`) | Một sample cho chuỗi lời gọi lồng nhau cùng thread | Latency end-to-end của lời gọi vào proxy | Không có thời gian riêng của các tầng con |
| Ghi inclusive và exclusive | Nhìn tổng latency và ước lượng thời gian tự thân từng lời gọi | Phân tích call hierarchy đồng bộ | Cần stack frame và quy tắc cộng thời gian không chồng lấn |

Nếu dùng `Timer` của Micrometer, hãy xác định rõ metric biểu diễn **một lần gọi method**, **một request**, hay **một tác vụ gốc**. Thẻ phù hợp thường là tên method có tập giá trị giới hạn và outcome (success/error). Tránh đưa input động, ID request, stack đầy đủ hoặc số tầng đệ quy không giới hạn vào tags: những giá trị này gây bùng nổ cardinality của hệ thống metrics.

Có thể chọn policy chỉ đo root bằng một guard trước khi ghi metric, nhưng vẫn phải quản lý `depth` ở mọi lượt advice và khôi phục state trong `finally`. Một guard đánh dấu “đã đo” mà không reset sẽ làm các lượt gọi độc lập sau bị bỏ qua khi dùng thread pool.

## 6. Lỗi thực tế và giới hạn của proxy

### 6.1. Advice không xuất hiện trong lời gọi nội bộ

**Triệu chứng:** có log của `outer()` nhưng không có log `inner()`, mặc dù debug chứng minh `inner()` đã chạy.

**Nguyên nhân:** `this.inner()` / lời gọi trần `inner()` không qua proxy. Kiểm tra thêm bean thực sự lấy từ Spring container và pointcut có khớp method/class hay không.

**Cách giải quyết ưu tiên:** chuyển logic cần advice thành method của bean khác và gọi bean đó qua injected Spring dependency. Nếu muốn giữ trong cùng bean và đã cân nhắc coupling, có thể lấy self proxy như ví dụ. `AopContext.currentProxy()` chỉ hoạt động khi cấu hình expose proxy và khi đang ở lời gọi được proxy intercept; nó làm mã phụ thuộc trực tiếp vào Spring AOP nên không phải lựa chọn mặc định.

### 6.2. Có nhiều lớp advice quanh cùng một lời gọi

Nếu `@Transactional`, security advice, caching hoặc một `@Around` khác cùng tác động, **thứ tự advisor** ảnh hưởng phạm vi thực tế mà timer bao quanh. Ví dụ một timer ở ngoài transaction advice có thể đo thêm thời gian bắt đầu/hoàn tất transaction, trong khi timer ở trong có thể không thấy một phần chi phí đó. Nếu ý nghĩa số đo quan trọng, cấu hình rõ thứ tự bằng `@Order`, chạy kiểm chứng và ghi rõ boundary.

### 6.3. Đệ quy sâu, ngoại lệ và chi phí instrumentation

- Mỗi lần proxy intercept đều chạy chuỗi interceptor, có overhead và thêm frame; đệ quy sâu vẫn có nguy cơ `StackOverflowError`.
- `finally` nên record cả success/failure và vẫn truyền nguyên `Throwable` ra ngoài. Nếu thêm tags kết quả, giữ cardinality hữu hạn; tránh đưa raw message ngoại lệ làm tag.
- Không dùng `System.currentTimeMillis()` cho phép đo ngắn cần tính monotonic; `nanoTime()` chỉ cung cấp độ phân giải thời gian, không bảo đảm độ chính xác tuyệt đối hay đo CPU.
- Tránh log hoặc tạo stack trace trong mỗi bước đệ quy ở đường xử lý nóng. Thử với workload thực tế và xem overhead của advice.

### 6.4. Ranh giới thread và lời gọi bất đồng bộ

`ThreadLocal` chỉ theo dõi những lời gọi chạy trên **cùng một thread**. Khi dùng `@Async`, thread pool hoặc tác vụ song song, cây lồng nhau không tự được ghép lại chỉ nhờ `ThreadLocal`. Một `@Around` đo lời gọi method trả về `CompletableFuture` có thể chỉ đo thời gian **tạo/trả future**, không đo đến khi future hoàn thành. Cần đo vòng đời tác vụ bằng instrumentation phù hợp, hoặc dùng tracing context được truyền có chủ đích qua biên thread.

Với Spring WebFlux/Reactor, method có thể trả `Mono` hoặc `Flux` ngay lập tức; `proceed()` xong không đồng nghĩa publisher đã được subscribe hay xử lý xong. Muốn đo subscription-to-termination nên dùng operator như `doOnSubscribe`, `doFinally` hoặc hệ thống observability tương ứng, thay vì diễn giải thời gian method return là thời gian xử lý reactive hoàn chỉnh.

## 7. Cách kiểm chứng kết quả đo

Khi một biểu đồ cho thấy “ít lượt gọi” hoặc tổng latency lớn bất thường, hãy kiểm tra theo thứ tự:

1. **Đường gọi thật:** caller đang giữ Spring proxy hay đối tượng tự khởi tạo? Các lần gọi tiếp theo có đi qua proxy hay là self-invocation?
2. **Pointcut và khả năng intercept:** method có đúng lớp/giao diện, modifier và scope? Với class-based proxy có dính `final` hay `private` không?
3. **Số lượt và thứ tự:** ở ví dụ này, `direct()` sinh một dòng đo; `throughProxy()` sinh bốn dòng, kết thúc từ sâu nhất. Nếu sai, so lại code và cấu hình AOP.
4. **Ngữ nghĩa thời gian:** đang cộng inclusive samples gây double count hay cần root-only/exclusive? Có advisor khác bao ngoài/bên trong?
5. **Biên bất đồng bộ:** đo method return, future completion hay thời gian hoàn thành publisher? Trace context có được truyền qua thread không?
6. **Sức khỏe state:** sau exception, ThreadLocal depth có trở về 0/remove không? Số lượng method/tags có ổn định khi tải cao?

## 8. Ghi nhớ

Trong Spring AOP, **proxy boundary mới là ranh giới tạo một lần chạy advice**. Self-invocation và đệ quy trực tiếp chạy được nhưng không được advice chặn từng tầng; đi qua Spring proxy ở mỗi lần gọi sẽ làm advice chạy theo từng tầng. Khi đã chọn đúng đường gọi, phải công bố rõ metric là inclusive, exclusive hay chỉ lời gọi ngoài cùng, vì cộng thời gian của các lời gọi lồng nhau có thể đếm lặp. Với async và reactive, luôn xác định chính xác **vòng đời nào** đang được đo.
