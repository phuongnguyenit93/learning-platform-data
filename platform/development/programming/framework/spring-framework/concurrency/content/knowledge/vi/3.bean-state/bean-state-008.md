# Phân biệt phạm vi bean với cơ chế đồng bộ trong Spring Framework

## Mục tiêu

Sau bài này, bạn sẽ phân biệt được **bean scope** (phạm vi tồn tại và chia sẻ *instance* do Spring quản lý) với **cơ chế đồng bộ** (cách bảo vệ trạng thái khi nhiều luồng truy cập cùng lúc). Bạn cũng sẽ biết tại sao `singleton` không đồng nghĩa với “an toàn luồng”, `prototype` không bảo đảm loại bỏ race condition, `request` và `session` không phải khóa, và cách lựa chọn thiết kế đúng cho bean có trạng thái.

Bối cảnh là Spring Framework chạy trong ứng dụng nhiều luồng: yêu cầu HTTP, tác vụ `@Async`, scheduler hoặc executor đều có thể gọi một bean. Không cần dùng đa luồng trong mọi chương trình để hiểu scope, nhưng khi nhiều luồng cùng chạm tới dữ liệu mutable, phải đánh giá thread safety riêng.

## 1. Hai câu hỏi khác nhau

**Bean scope trả lời:** “Spring tạo, lưu và cung cấp *instance bean nào* cho lần yêu cầu này, trong phạm vi và vòng đời nào?”

**Đồng bộ hóa trả lời:** “Nếu nhiều thread đọc/ghi *cùng trạng thái có thể thay đổi*, thao tác nào phải có tính nguyên tử, thứ tự và khả năng nhìn thấy giữa các thread?”

Hãy hình dung:

- **Scope** quyết định ai được cấp chìa khóa vào cùng một phòng (cùng object) và phòng được tạo/hủy khi nào.
- **Synchronization** quyết định cách người trong phòng dùng chung sổ ghi chép mà không mất dòng, đọc sai hoặc ghi đè nhau.

Hai chiều này độc lập. Một singleton hoàn toàn có thể thread-safe nếu không giữ mutable state hoặc bảo vệ state đúng cách. Một prototype vẫn có thể không thread-safe nếu tham chiếu của nó được chia cho hai worker hoặc nó sửa một biến `static`, collection, cache hay tài nguyên dùng chung.

```text
Spring container / scope          Các thread và truy cập trạng thái
        |                                       |
        | lấy hoặc inject instance              | gọi method trên instance
        v                                       v
  Bean instance ------------------------> field / object / storage
        |                                       |
 quyết định chia sẻ instance             cần phân tích race, visibility,
 và vòng đời                              atomicity, invariants
```

**Đừng suy ra** từ `@Scope`, `@Component`, `@Service`, `@Async` hay `@Transactional` rằng framework đã tự động đặt khóa quanh toàn bộ phương thức nghiệp vụ. Mỗi annotation có hợp đồng riêng.

## 2. Các scope phổ biến và mức độ chia sẻ

| Scope | Khi nào Spring cung cấp instance? | Điều cần chú ý về concurrency |
| --- | --- | --- |
| `singleton` (mặc định) | Một object cho một bean definition trong **một Spring IoC container**. Các lần lấy cùng bean definition trả về cùng instance. | Nhiều thread có thể gọi đồng thời và dùng chung các instance field; cần thiết kế an toàn nếu state mutable. |
| `prototype` | Tạo object mới **mỗi lần container được yêu cầu cung cấp bean**. | Không tự tạo một instance cho mỗi method call hay thread; object prototype vẫn có thể được chia sẻ sau khi cấp phát. |
| `request` | Một object cho một HTTP request trong web-aware context. | Các request khác nhau được tách trạng thái bean, nhưng cùng request vẫn có thể có truy cập đa luồng; phải chú ý ngữ cảnh request khi chuyển thread. |
| `session` | Một object theo HTTP session. | Nhiều request song song từ cùng session có thể dùng chung bean; session scope **không** tuần tự hóa thao tác. |
| `application` | Một object cho một `ServletContext`. | Có thể được nhiều request/bean dùng chung; `ServletContext` không phải ranh giới khóa. |
| `websocket` | Gắn với một WebSocket session trong môi trường hỗ trợ. | Nhiều callback/tác vụ liên quan cùng session vẫn cần thiết kế concurrency phù hợp. |

Spring còn hỗ trợ **custom scope**. `SimpleThreadScope` có sẵn nhưng **không được đăng ký mặc định**: nó gắn instance theo thread nếu bạn tự đăng ký. Trong thread pool, một worker có thể chạy nhiều task của nhiều người dùng, nên “mỗi thread một bean” **không tương đương** “mỗi request một bean”. Tránh dùng thread scope như cách chữa race condition chung.

Lưu ý ranh giới:

1. Spring `singleton` là **per container, per bean definition**, không phải một object duy nhất cho toàn JVM, mọi application context hay toàn cụm server. Hai bean definition cùng class vẫn có thể tạo hai singleton khác nhau.
2. Web scopes chỉ hoạt động khi có ngữ cảnh web thích hợp; một `AnnotationConfigApplicationContext` thông thường không tự cấp request/session scope.
3. Scope chỉ kiểm soát **bean được container quản lý**. `new SomeClass()` tự tạo bên ngoài Spring và static field không tự đổi vòng đời chỉ vì class có annotation.
4. Khi nhiều instance dùng chung database, Redis, file, shared cache hoặc tài nguyên khác, việc tách instance cũng không tách tài nguyên bên dưới.

## 3. Nhận diện state nằm trong bean hay bên ngoài bean

Một biến local thuộc từng lần gọi, nhưng **đối tượng được biến local trỏ tới có thể vẫn được chia sẻ**; ngược lại, field của singleton thường được nhiều caller thấy cùng lúc. Trước khi chọn scope hay lock, hãy theo các tham chiếu thực tế:

| Nơi đặt trạng thái | Quan hệ với scope | Câu hỏi cần trả lời |
| --- | --- | --- |
| Tham số, biến cục bộ | Ô biến riêng cho mỗi invocation | Tham chiếu có trỏ tới List/DTO mutable được chia sẻ không? |
| Instance field của singleton | Field thuộc một bean instance được chia sẻ | Field có bị sửa sau khi khởi tạo; mọi reader/writer có phối hợp không? |
| Field của prototype/request/session | Phụ thuộc cách bean được cấp và reference được giữ | Có cùng target bị nhiều thread truy cập hay bị giữ quá vòng đời không? |
| Static, cache, DB, dependency khác | Không được cô lập chỉ vì đổi scope của bean caller | Chủ sở hữu và cơ chế đồng bộ tại tài nguyên dùng chung là gì? |

Ví dụ, `final List<String> items` không khiến list bất biến; `AtomicInteger` bảo vệ phép tăng một giá trị trong một JVM, nhưng không bảo vệ database hoặc một workflow nhiều bước.

## 4. Scope khác gì với synchronization?

Ba thuộc tính concurrency quan trọng:

- **Atomicity (tính nguyên tử):** một thao tác hoặc một nhóm thao tác phải được quan sát như một đơn vị phù hợp. Ví dụ “đọc tồn kho, kiểm tra đủ, trừ tồn” là một invariant nhiều bước.
- **Visibility (khả năng nhìn thấy):** ghi của thread A phải được thread B quan sát theo quan hệ happens-before thích hợp; nếu thiếu, B có thể đọc giá trị cũ.
- **Ordering (thứ tự):** compiler, CPU và runtime có thể tối ưu/sắp xếp lại theo Java Memory Model khi không có quan hệ đồng bộ; phải thiết kế quan hệ happens-before khi logic phụ thuộc thứ tự.

| Công cụ | Giải quyết tốt việc gì? | Không tự giải quyết |
| --- | --- | --- |
| Dữ liệu bất biến, thiết kế stateless | Loại bỏ phần lớn tranh chấp trên state riêng của service. | Race trong các dependency mutable hay storage bên ngoài. |
| Biến cục bộ, object không chia sẻ giữa thread | Giảm chia sẻ trạng thái do mỗi lần gọi giữ state riêng. | Object được trao tiếp cho thread khác hoặc global state vẫn có thể bị tranh chấp. |
| `synchronized` / `ReentrantLock` | Bảo vệ đoạn tới hạn, tạo quan hệ happens-before với cùng khóa, bảo vệ invariant nhiều bước. | Không đồng bộ với code dùng khóa khác hoặc truy cập không tuân thủ cùng quy tắc; không khóa qua nhiều JVM. |
| `AtomicInteger`, `AtomicLong`, CAS | Các thao tác nguyên tử đơn lẻ như tăng bộ đếm. | Invariant phức tạp trải trên nhiều field hoặc nhiều dòng lệnh nếu không thiết kế phối hợp. |
| `volatile` | Visibility và ordering cho field phù hợp, ví dụ cờ dừng. | Biến `count++`, “kiểm tra rồi cập nhật”, hay invariant nhiều bước. |
| `ConcurrentHashMap`, concurrent collections | Các hoạt động đồng thời theo hợp đồng collection; một số thao tác atomic như `computeIfAbsent` theo đặc tả. | Toàn bộ quy trình gồm nhiều thao tác độc lập nếu cần atomicity xuyên suốt. |
| Database transaction / lock / optimistic version | Tính nhất quán tại tầng dữ liệu khi có giao dịch phù hợp. | Thread safety tự động cho instance field trong JVM. |

Với `synchronized`, điều quan trọng là **các thread cùng đồng bộ trên *đúng một lock*** và các truy cập liên quan đều tuân thủ quy tắc đó:

```java
private int count;

public synchronized int increment() {
    return ++count;
}

public synchronized int current() {
    return count;
}
```

Hai method trên dùng monitor của **cùng một instance**. Nếu có hai object khác nhau, mỗi object có khóa riêng; chúng không bảo vệ một tài nguyên dùng chung bên ngoài. Nếu cần khóa cho cùng database record ở nhiều instance ứng dụng, phải dùng chiến lược đồng bộ ở storage / transaction / concurrency control, không chỉ `synchronized` của một bean.

**Không khóa toàn bộ một service theo thói quen.** Việc serialize các lời gọi có thể làm giảm throughput, tăng độ trễ và tạo rủi ro deadlock. Chỉ khóa phần invariant cần thiết, giữ critical section ngắn và ưu tiên immutable/atomic data khi phù hợp.

## 5. Ví dụ chạy được: bean scope và một race condition

Ví dụ sau dùng **Java 17+** và Spring Framework `spring-context` **6.2.0**. Nó cho thấy bốn điều:

1. Hai lần lấy singleton theo cùng bean definition nhận cùng object.
2. Mỗi yêu cầu prototype trực tiếp hoặc qua `ObjectProvider` tạo object khác.
3. Một prototype được **inject một lần vào singleton** không tự làm mới theo mỗi lời gọi singleton.
4. Hai thread gọi cùng singleton có thể mất một lần tăng; dùng `AtomicInteger` thì hai lần tăng được giữ lại.

Để kết quả của race minh họa **ổn định**, `CyclicBarrier` chỉ dùng trong class cố ý viết sai nhằm buộc cả hai thread đọc cùng số `0` trước khi ghi. Đây là dụng cụ tái hiện lỗi, **không phải cơ chế sửa lỗi**.

Tạo cấu trúc:

```text
scope-sync-demo/
├── pom.xml
└── src/main/java/example/ScopeSyncDemo.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>scope-sync-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>example.ScopeSyncDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/example/ScopeSyncDemo.java`:

```java
package example;

import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

public class ScopeSyncDemo {

    // Cố ý không thread-safe để chứng minh mất cập nhật.
    public static class UnsafeCounter {
        private int value;
        private final CyclicBarrier bothHaveRead = new CyclicBarrier(2);

        public void incrementTogether() {
            int snapshot = value; // Cả hai thread phải đọc trước khi ghi.
            try {
                bothHaveRead.await(10, TimeUnit.SECONDS);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Interrupted", ex);
            } catch (BrokenBarrierException | TimeoutException ex) {
                throw new IllegalStateException("Barrier failed", ex);
            }
            value = snapshot + 1;
        }

        public int current() {
            return value;
        }
    }

    // Mỗi incrementAndGet là một thao tác nguyên tử.
    public static class SafeCounter {
        private final AtomicInteger value = new AtomicInteger();

        public int increment() {
            return value.incrementAndGet();
        }

        public int current() {
            return value.get();
        }
    }

    public static class ScratchPad {
        private int notes;

        public void addNote() {
            notes++;
        }

        public int notes() {
            return notes;
        }
    }

    // Singleton giữ một prototype inject lúc khởi tạo,
    // đồng thời có provider để yêu cầu prototype mới.
    public static class Client {
        private final ScratchPad injectedOnce;
        private final ObjectProvider<ScratchPad> provider;

        public Client(ScratchPad injectedOnce,
                      ObjectProvider<ScratchPad> provider) {
            this.injectedOnce = injectedOnce;
            this.provider = provider;
        }

        public ScratchPad injected() {
            return injectedOnce;
        }

        public ScratchPad newPad() {
            return provider.getObject();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public UnsafeCounter unsafeCounter() {
            return new UnsafeCounter(); // singleton mặc định
        }

        @Bean
        public SafeCounter safeCounter() {
            return new SafeCounter(); // cũng là singleton
        }

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public ScratchPad scratchPad() {
            return new ScratchPad();
        }

        @Bean
        public Client client(ScratchPad pad,
                             ObjectProvider<ScratchPad> provider) {
            return new Client(pad, provider);
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            UnsafeCounter unsafe = context.getBean(UnsafeCounter.class);
            SafeCounter safe = context.getBean(SafeCounter.class);
            Client client = context.getBean(Client.class);

            System.out.println("singletonSame="
                + (unsafe == context.getBean(UnsafeCounter.class)));

            ScratchPad direct1 = context.getBean(ScratchPad.class);
            ScratchPad direct2 = context.getBean(ScratchPad.class);
            System.out.println("prototypeDirectDistinct="
                + (direct1 != direct2));

            System.out.println("prototypeInjectedSame="
                + (client.injected() == client.injected()));

            System.out.println("prototypeViaProviderDistinct="
                + (client.newPad() != client.newPad()));

            ExecutorService workers = Executors.newFixedThreadPool(2);
            try {
                Future<?> u1 = workers.submit(
                    () -> { unsafe.incrementTogether(); });
                Future<?> u2 = workers.submit(
                    () -> { unsafe.incrementTogether(); });
                u1.get(); // chờ và quan sát lỗi trước khi in kết quả
                u2.get();

                Future<?> s1 = workers.submit(
                    () -> { safe.increment(); });
                Future<?> s2 = workers.submit(
                    () -> { safe.increment(); });
                s1.get();
                s2.get();
            } finally {
                workers.shutdownNow();
            }

            System.out.println("unsafeAfterTwoCalls=" + unsafe.current());
            System.out.println("safeAfterTwoCalls=" + safe.current());
        }
    }
}
```

Chạy tại thư mục `scope-sync-demo` (đã cài JDK 17+ và Maven):

```bash
mvn -q compile exec:java
```

Các dòng do chương trình in ra, theo thứ tự:

```text
singletonSame=true
prototypeDirectDistinct=true
prototypeInjectedSame=true
prototypeViaProviderDistinct=true
unsafeAfterTwoCalls=1
safeAfterTwoCalls=2
```

Phân tích:

- `unsafe` là một singleton, và hai `Future` đều gọi **cùng instance**; cả hai lấy snapshot `0`, chờ nhau rồi ghi `1`. Lẽ ra hai lần tăng phải cho `2`. `Future.get()` giúp main đợi hai tác vụ và quan sát kết quả sau khi chúng hoàn tất; nó không sửa thao tác tăng bị mất.
- `safe` cũng là **singleton** nhưng dùng `AtomicInteger.incrementAndGet()`: cả hai lần tăng được tính, cho `2`. **Cùng scope, khác tính an toàn luồng**.
- `direct1 != direct2` xác nhận hai yêu cầu lấy prototype tạo hai object. `client.injected()` vẫn trả một object cố định, vì singleton `Client` đã được tạo với dependency đó từ trước.
- `client.newPad()` gọi `ObjectProvider.getObject()` mỗi lần nên tạo prototype mới. Việc có nhiều instance chỉ giảm nguy cơ chia sẻ state khi bạn thực sự không đưa các instance đó cho nhiều thread sử dụng chung.
- `ScratchPad.addNote()` không có đồng bộ; nó chỉ an toàn nếu mỗi instance thực sự được giữ riêng cho một thread/đơn vị công việc hoặc có biện pháp bảo vệ phù hợp.

Trong sản phẩm thật, **không** tạo `CyclicBarrier` bên trong counter như vậy; nó chỉ là thiết bị dựng tình huống lost update trong bài học. Dùng công cụ kiểm thử concurrency hoặc stress test để khảo sát hành vi thực tế. Không kiểm thử bằng giả định “chạy 1.000 lần chắc sẽ phát hiện race”: lỗi phụ thuộc lịch trình thực thi.

## 6. Tại sao prototype không phải cách sửa race mặc định?

Một lời gọi `getBean(PrototypeBean.class)` tạo instance mới, nhưng không có cam kết rằng *mỗi thread* sẽ lấy bean khác nhau. Hãy xét các trường hợp:

**Trường hợp A — prototype inject vào singleton một lần:**

```java
@Service
class CheckoutService {
    private final MutableBasket basket;

    CheckoutService(MutableBasket basket) {
        this.basket = basket; // chỉ inject một lần vào singleton
    }
}
```

Giả sử `MutableBasket` là prototype: sau khi `CheckoutService` khởi tạo, mọi request gọi cùng singleton có thể truy cập **chính basket đã inject**. Đây là ví dụ minh họa một phần, cần khai báo bean/configuration để chạy. Muốn instance mới theo mỗi lần xử lý, dùng `ObjectProvider<MutableBasket>`, method injection hoặc tạo object local thích hợp.

**Trường hợp B — prototype được chia sẻ qua tham chiếu:** một object prototype truyền vào hai task của một executor vẫn là **một object được hai thread chạm tới**. Annotation scope không ngăn Java chia sẻ reference.

**Trường hợp C — state nằm ngoài prototype:** hai prototype ghi chung `static Map`, chung singleton repository hoặc cùng database record. Tách instance prototype không tạo atomicity cho tài nguyên này.

Một nguyên tắc thiết kế thực dụng: chỉ chọn prototype khi thực sự cần vòng đời “cấp một object mới theo yêu cầu”. Nếu công việc chỉ cần state tạm thời, tạo local variable hoặc dùng value object bất biến thường đơn giản hơn. Nếu cần `ObjectProvider`, gọi `getObject()` tại đúng ranh giới công việc; không lưu kết quả đó vào field của singleton rồi kỳ vọng nó tự thay đổi ở lần kế tiếp.

## 7. `request`, `session`, `@Async`: scope không tự đi theo thread

### Request scope

`@RequestScope` gắn bean với HTTP request. Trong một request MVC thông thường, Spring Web thiết lập request context cho đường xử lý request. Hai request khác nhau nhận hai instance request-scoped khác nhau, nhưng điều đó **không chứng minh** rằng cùng request chỉ có một thread có thể dùng instance hoặc rằng mọi thao tác trên nó là atomic.

Ví dụ minh họa riêng cho ứng dụng Spring MVC có web context:

```java
@RequestScope
@Component
public class RequestCart {
    private final java.util.List<String> items = new java.util.ArrayList<>();

    public void add(String item) {
        items.add(item); // không tự thread-safe khi cùng instance bị truy cập đồng thời
    }
}
```

Đây chỉ là snippet cho một ứng dụng MVC, **không** chạy độc lập bằng `AnnotationConfigApplicationContext` của ví dụ trước. Nếu một xử lý HTTP chủ động chạy nhiều tác vụ song song dùng cùng `RequestCart`, cần thiết kế chia sẻ và đồng bộ đúng cách.

Đặc biệt, **request context không mặc nhiên hiện diện trong thread của `@Async`**. Việc gọi request-scoped proxy từ worker không có request attributes hợp lệ có thể thất bại; chuyển ngữ cảnh phải có cơ chế hỗ trợ cụ thể, giữ đúng vòng đời và tránh dùng dữ liệu request sau khi đã kết thúc. Không nên “sửa” bằng `InheritableThreadLocal` tùy tiện với thread pool vì thread được tái sử dụng.

### Session scope

`@SessionScope` gắn object với một HTTP session. Trình duyệt có thể gửi nhiều request cùng session gần như đồng thời (nhiều tab, fetch song song), nên hai request có thể sửa cùng bean session. **Một session không tương đương một thread.** Nếu state session mutable, cân nhắc thiết kế bất biến, thao tác nguyên tử, đồng bộ trên cùng object hoặc chuyển state sang store với concurrency control phù hợp.

### Scoped proxy và dependency có vòng đời ngắn

Singleton cần dùng request/session-scoped bean thường inject **scoped proxy** hoặc `ObjectProvider`. Proxy giữ một điểm tham chiếu ổn định ở singleton và tìm *target bean hiện hành* khi được gọi trong context hợp lệ. Proxy **không tự khóa** phương thức của target. `@RequestScope`/`@SessionScope` cung cấp cấu hình proxy thông dụng để hỗ trợ kiểu inject này.

Với prototype, scoped proxy cũng có ngữ nghĩa riêng: proxy cho prototype có thể lấy target mới cho từng method call; nếu cần nhiều thao tác trên **cùng một prototype** trong một quy trình, nên lấy một object từ provider rồi giữ tham chiếu trong phạm vi quy trình đó. Không trông chờ proxy tự quản lý một “transaction nghiệp vụ” nhiều lời gọi.

### `@Async` và executor

`@Async` khi được kích hoạt đúng qua Spring proxy chuyển *việc thực thi* phương thức sang executor, nhưng **không đổi scope** của service:

```text
HTTP request thread                       Worker trong executor
    | gọi @Async trên singleton                  |
    +------------- submit --------------------->| gọi method cùng singleton
    | nhận Future/CompletableFuture              | đọc/ghi field singleton
    | xử lý việc khác                            |
```

Nếu nhiều HTTP request gọi cùng service singleton có `@Async`, có thể nhiều worker cùng sửa field của cùng instance. `@Async`, `@EnableAsync` và kích thước thread pool **không thay thế** cơ chế đồng bộ. Thread pool size 1 chỉ làm giảm một dạng song song của một executor; request thread hoặc executor khác vẫn có thể truy cập cùng bean. Không thiết kế an toàn dựa vào giả định lúc nào cũng chỉ có một worker.

Tương tự, `@Scheduled` gọi method trên bean theo lịch, không biến field thành thread-safe. Cần xem cách scheduler cấu hình, các đường gọi khác, và liệu nhiều lịch hoặc nhiều instance ứng dụng có thể cùng đụng state.

## 8. Cách thiết kế bean có trạng thái an toàn

### Ưu tiên singleton stateless

Một singleton không cần khóa chỉ vì có nhiều caller: nếu phương thức tính `"Xin chào " + name` từ tham số `String name`, không giữ tên request trong field và không sửa dependency mutable, mỗi invocation có dữ liệu độc lập. Ngược lại, field `currentName` trong singleton là **một ô chung** dù được gắn `volatile` hoặc `AtomicReference`; những cơ chế đó không tách dữ liệu theo request.

Khi cần state theo request, tạo local/DTO riêng hoặc dùng request scope đúng vòng đời. Khi thật sự cần shared mutable state, xác định invariant và bảo vệ các thao tác liên quan.

### Chọn công cụ theo invariant

- Bộ đếm riêng lẻ: `AtomicLong` / `AtomicInteger`.
- Nhiều field phải thay đổi nhất quán: lock chung hoặc lưu snapshot immutable rồi thay thế nguyên tử với cấu trúc phù hợp.
- Cache đa luồng: collection concurrent và thao tác atomic đúng hợp đồng, chú ý bất biến của các **value** đặt trong map.
- Dữ liệu nhiều JVM/replica: transaction database, optimistic locking (`@Version` khi phù hợp với ORM), unique constraint, hoặc concurrency control tại storage.
- Công việc nền quan trọng: cân nhắc hàng đợi bền vững, idempotency và quản lý vòng đời thay vì chỉ tăng số prototype/singleton.

Không đồng nhất `@Transactional` với `synchronized`: transaction bảo vệ tính nhất quán theo cơ chế transaction manager/tầng lưu trữ và isolation đang dùng, không đặt mutex quanh mọi field Java; nhiều transaction vẫn có thể cùng chạy.

### Kiểm tra hệ quả khi có nhiều container và instance

Spring singleton trong ứng dụng A và singleton cùng tên trong ứng dụng B là hai object khác nhau. Khóa nội bộ một bean không phân phối qua các replica. Ngược lại, hai bean prototype trong **cùng JVM** có thể cùng truy cập static state hoặc shared cache. Luôn xác định đúng tài nguyên cần bảo vệ và ranh giới chạy thật.

### Vòng đời

Spring chủ động quản lý singleton từ khởi tạo đến đóng context theo lifecycle tương ứng. Với prototype, Spring tạo/configure và bàn giao instance nhưng **không tự gọi các destruction callbacks của prototype theo cách quản lý trọn đời như singleton**. Nếu prototype giữ file handle, socket hoặc tài nguyên đắt, phía sử dụng phải có trách nhiệm dọn dẹp hợp lý. `request`/`session` có vòng đời theo request/session khi được web context hỗ trợ.

## 9. Những kết luận sai cần tránh

| Nhận định sai | Thực tế |
| --- | --- |
| “Singleton không thread-safe, nên đổi hết sang prototype.” | Stateless singleton hoàn toàn có thể an toàn. Prototype có thể bị chia sẻ hoặc sửa chung storage. |
| “Mỗi task / mỗi thread sẽ tự có prototype riêng.” | Prototype được cấp khi *container được yêu cầu bean*, không dựa trực tiếp vào thread. |
| “Inject prototype vào singleton thì lần gọi service sau nhận prototype mới.” | Dependency được resolve lúc tạo singleton; cần provider hoặc method injection nếu muốn cấp lại. |
| “Request scope bảo đảm không có race condition.” | Nó cô lập giữa HTTP requests; cùng request hoặc object reference vẫn có thể bị truy cập đồng thời. |
| “Session scope khóa mọi request của cùng user.” | Các request cùng session có thể xử lý song song. |
| “`@Async` / `@Scheduled` sẽ tạo bean mới hoặc tự đồng bộ.” | Chúng điều phối thực thi, không định nghĩa scope hoặc mutex cho state. |
| “Đã dùng `volatile`, `count++` sẽ chính xác.” | Volatile bảo đảm visibility theo quy tắc của nó, không làm chuỗi read-modify-write thành atomic. |
| “Đã dùng `@Transactional`, field trong singleton được khóa.” | Transaction không thay thế cơ chế đồng bộ JVM. |
| “Dùng `synchronized` trong một singleton là an toàn cả cụm server.” | Monitor chỉ nằm trên object trong một JVM. |

## 10. Quy trình phân tích một bean trong dự án thật

1. **Xác định instance:** bean được tạo ở đâu, scope gì, số application context / replica, có scoped proxy hoặc `ObjectProvider` không?
2. **Liệt kê state:** field mutable, object được inject, collection, `static` và dữ liệu ở storage; biến nào thực sự dùng chung?
3. **Liệt kê đường gọi:** HTTP request, `@Async`, scheduler, listener, callback, executor; có thể có hai thread cùng đi vào đường ghi không?
4. **Nêu invariant:** ví dụ “đơn hàng chỉ trừ kho một lần”, “số tăng không được mất”, “một session giữ cấu hình hợp lệ”; đơn vị cần atomic là một phép toán hay nhiều bước?
5. **Chọn chiến lược:** bỏ state khỏi singleton, immutable, atomic class, lock cùng monitor, concurrent collection hoặc transaction/lock tại storage.
6. **Kiểm chứng:** viết bài kiểm thử cạnh tranh có điều kiện phối hợp (`CountDownLatch`, `CyclicBarrier`) và điều kiện hậu kiểm rõ; đo race, deadlock và contention khi cần. Không dùng `Thread.sleep()` để giả vờ chứng minh đúng thứ tự.

Ví dụ đọc mã: `@Service` singleton có `Map<String, Cart>` và một controller có nhiều request song song. **Câu hỏi cần trả lời không chỉ là scope**: `Map` có an toàn khi cập nhật đồng thời không, từng `Cart` có bị hai request chung user sửa cùng lúc không, và invariant tổng tiền được bảo vệ ở đâu? Đổi `@Service` sang prototype có thể khiến cache phân mảnh mà vẫn chưa bảo vệ `Cart` dùng chung trong database.

## 11. Tự kiểm tra

**Câu 1.** Một singleton không có field mutable, mọi dữ liệu request đi qua tham số và biến local. Có cần `synchronized` toàn bộ method chỉ vì nó là singleton?

**Đáp án:** Không. Phải xét những dependency/tài nguyên dùng chung, nhưng singleton tự nó không tạo race nếu không có mutable state bị chia sẻ.

**Câu 2.** Một singleton inject `@Scope("prototype") PaymentDraft` qua constructor. Mỗi request gọi singleton có chắc nhận `PaymentDraft` mới không?

**Đáp án:** Không. Prototype chỉ được tạo khi Spring resolve dependency lúc khởi tạo singleton. Muốn tạo tại mỗi quy trình, dùng `ObjectProvider.getObject()` hoặc giải pháp scope phù hợp.

**Câu 3.** Hai request cùng HTTP session cập nhật bean `@SessionScope` vào đúng một thời điểm. Scope có tự bảo vệ `balance = balance - amount` không?

**Đáp án:** Không. Cùng session có thể có xử lý song song. Thêm nữa, balance ở database phải được bảo vệ tại storage; lock JVM không đủ khi có nhiều replica.

**Câu 4.** Một bean singleton dùng `AtomicInteger.incrementAndGet()` cho counter. Có nhất thiết phải đổi sang prototype để hai thread tăng đúng không?

**Đáp án:** Không. Atomic increment đã giải quyết thao tác đơn lẻ đó trên cùng atomic object; singleton hoàn toàn phù hợp.

**Câu 5.** Worker `@Async` được gọi từ request thread và cố dùng request-scoped bean. Điều gì phải kiểm tra?

**Đáp án:** Kiểm tra có request context hợp lệ trên thread thực thi hay không, vòng đời context, cách truyền dữ liệu và khả năng nhiều thread cùng dùng state. Không giả định request context tự động đi theo worker.

### Điều cần nhớ

**Scope quản lý việc cấp phát/chia sẻ bean và vòng đời; đồng bộ hóa quản lý truy cập đồng thời vào trạng thái.** Chỉ khi xác định đúng *object nào*, *thread nào*, *state nào* và *invariant nào* đang bị chia sẻ mới chọn được thiết kế an toàn.

### Tài liệu tham khảo chính thức

- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton, prototype, web scopes, inject prototype vào singleton, scoped proxy, `ObjectProvider` và custom scope.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): executor, `@Async`, scheduler và ranh giới luồng thực thi.
- [Java SE — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): ý nghĩa của phép tăng nguyên tử.
- [Java SE — Java Language Specification, Chapter 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model, synchronization và happens-before.
