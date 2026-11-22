# Ngăn vòng lặp phát event trong Spring Application Events

## 1. Bài toán: event chain có thể quay lại chính nó

Trong Spring Framework, `ApplicationEventPublisher` giúp các bean phối hợp qua event thay vì gọi trực tiếp lẫn nhau. Một luồng bình thường có thể là:

~~~text
OrderCreated -> OrderValidated -> NotificationScheduled
~~~

Vấn đề xuất hiện khi một listener nhận sự kiện rồi **phát lại cùng sự kiện hoặc một sự kiện dẫn ngược về bước trước**, tạo vòng tròn:

~~~text
A -> B -> C -> A -> B -> C -> ...
~~~

Nếu dùng cấu hình mặc định đồng bộ, việc gọi `publishEvent(...)` từ listener sẽ dẫn tới **lời gọi listener lồng nhau trên cùng call stack**. Nếu không có điều kiện dừng, ứng dụng có thể gặp `StackOverflowError`, transaction kéo dài, log tăng đột biến hoặc use case thất bại. Nếu chuyển sang xử lý bất đồng bộ hoặc broker, call stack có thể không tăng ngay, nhưng vòng lặp biến thành **event storm**, khiến queue, CPU, bộ nhớ hoặc chi phí xử lý tăng không giới hạn.

Bài này thuộc nội dung **Phát lại và chuỗi event**, tập trung vào cách ngăn các vòng lặp ở đúng ranh giới, thay vì chỉ chữa triệu chứng bằng cách tăng thread pool hoặc giới hạn log.

Kết thúc bài học, bạn cần biết:

- Những con đường làm event được phát tiếp trong Spring và vì sao sinh vòng lặp.
- Khác biệt giữa recursion đồng bộ, phản hồi bất đồng bộ và redelivery/retry.
- Cách chặn bằng **điều kiện nghiệp vụ**, **visited-state/cycle detection**, **hop budget**, **idempotency** và **correlation/causation ID**.
- Cách viết ví dụ Java 17+ chạy được với `ApplicationEventPublisher` và `@EventListener`.
- Giới hạn của mỗi biện pháp, cách quan sát hệ thống và chiến lược kiểm thử vòng lặp.

## 2. Các cơ chế phát event liên tiếp trong Spring

### 2.1. Listener chủ động publish event mới

Spring cho phép một listener inject `ApplicationEventPublisher` để tiếp tục một luồng xử lý:

~~~java
// Minh họa: các kiểu A, B và Spring bean cần được định nghĩa thêm.
@Component
public class StageListener {
    private final ApplicationEventPublisher publisher;

    public StageListener(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @EventListener
    public void onA(A event) {
        publisher.publishEvent(new B(event.processId()));
    }
}
~~~

Đây là cách xây dựng event chain hợp lệ **khi luồng có điểm kết thúc**. Nếu có một listener khác nhận `B` rồi lại phát `A` với cùng tiến trình, đường đi trở thành `A → B → A`.

`ApplicationEventPublisher.publishEvent(...)` là **handoff** sang cơ chế multicaster. Nó không tự kiểm tra đã từng xử lý event này hay chưa, cũng không tự giải quyết vòng lặp. Với `SimpleApplicationEventMulticaster` mặc định, listener bình thường nhận event trên **thread đang publish**; mỗi lần nested publish làm call stack sâu hơn.

### 2.2. Phương thức `@EventListener` trả về event

Đây là một nguồn tạo vòng lặp dễ bị bỏ sót. Một phương thức `@EventListener` trả về giá trị **khác `void`** có thể khiến Spring coi giá trị trả về đó là **event mới**. Nếu trả về collection hoặc array, từng phần tử cũng có thể được publish thành event riêng.

~~~java
// Chỉ minh họa Anti-pattern, KHÔNG chạy:
@EventListener
public Ping onPing(Ping event) {
    return event; // Spring có thể tự publish lại chính Ping!
}
~~~

Nếu `Ping` lại được `onPing` nhận, vòng lặp có thể được tạo ra **mà không hề có lời gọi `publisher.publishEvent` trong thân method**.

Không trả lại cùng kiểu event chỉ vì muốn “trả kết quả” cho publisher. Muốn trả kết quả đồng bộ cho caller, hãy dùng phương thức service thông thường hoặc một contract đáp ứng yêu cầu thực tế; nếu cố ý tạo event tiếp theo, phải có điều kiện dừng rõ ràng.

**Lưu ý:** cơ chế publish event qua return value của `@EventListener` không được hỗ trợ cho listener bất đồng bộ `@Async`. Trong listener async, muốn tạo event tiếp theo, cần inject `ApplicationEventPublisher` và publish tường minh. Điều này không có nghĩa async tự ngăn vòng lặp.

### 2.3. Chu kỳ gián tiếp qua nhiều listener

Không chỉ có trường hợp `A → A`. Ví dụ:

~~~text
OrderCreated
  -> InventoryReserved
      -> OrderUpdated
          -> OrderCreated
~~~

Một listener có thể hoàn toàn không biết rằng event nó phát tiếp là nguyên nhân kích hoạt chính nó ở tầng khác. Càng nhiều module và listener, chu kỳ càng khó nhìn thấy nếu không có sơ đồ luồng và thông tin trace.

### 2.4. Vòng lặp do integration, retry hoặc phản hồi trạng thái

Có các vòng lặp không nằm trên một call stack:

- Service A gửi `CustomerUpdated` sang B; B đồng bộ ngược dữ liệu sang A; A thấy thay đổi và gửi lại `CustomerUpdated`.
- Consumer retry không giới hạn một poison message; mỗi lần fail tạo lại cùng công việc.
- Webhook nhận bản cập nhật rồi gọi API làm hệ thống gửi lại webhook.
- Một listener viết lại entity dù dữ liệu thực tế không đổi; hook persistence hoặc CDC lại phát event.

Những trường hợp này cần **idempotency**, kiểm soát business transition, retry limit và deduplication bền vững; một `ThreadLocal` guard trong một JVM không giải quyết được chu kỳ trải qua nhiều service.

## 3. Tại sao vô hạn recursion nguy hiểm?

### Trên multicaster mặc định đồng bộ

Giả sử `A` được publish và callback A tạo thêm B. Dispatcher đồng bộ gọi B trước khi callback A kết thúc. Nếu B lại tạo A, stack là:

~~~text
publish(A)
  onA(A)
    publish(B)
      onB(B)
        publish(A)
          onA(A)
            ...
~~~

Tác động có thể gồm `StackOverflowError`, số lượng side effect tăng, transaction bị giữ mở lâu, lock database kéo dài hoặc request treo. **Tăng kích thước stack không phải giải pháp**; nó chỉ làm vòng lặp chạy thêm vài bước rồi vẫn lỗi.

Exception từ listener đồng bộ (theo cấu hình mặc định không có error handler nuốt lỗi) có thể lan về publisher. Nếu publisher nằm trong một transaction `@Transactional`, nó còn có thể khiến use case rollback. `StackOverflowError` thuộc nhóm `Error`, không nên coi là một lỗi nghiệp vụ để catch rồi “bỏ qua”.

### Khi dùng `@Async`, executor hoặc message broker

Luồng bất đồng bộ có thể không làm stack tăng theo cách trên, nhưng vẫn gây:

- Event tự tạo ra event mới liên tục khiến queue backlog và latency tăng.
- CPU, DB connections và network calls bị tiêu thụ vô ích.
- Một event được xử lý nhiều lần, tạo email/thanh toán/bản ghi trùng.
- Retry “đánh thức” chu kỳ đã có; số lần gửi tăng theo số consumer.

Chuyển sang async **thay đổi cách thất bại**, không loại bỏ nguyên nhân vòng lặp. Khi di chuyển giữa threads, `ThreadLocal`, transaction context và MDC không tự động đi theo, vì vậy guard đặt trong `ThreadLocal` càng không đáng tin để kiểm soát chuỗi phân tán.

## 4. Giải pháp 1 — Chặn tại quy tắc chuyển trạng thái nghiệp vụ

Biện pháp tốt nhất thường là **không phát event mới nếu trạng thái không thật sự thay đổi**.

Ví dụ một `Order` chỉ được chuyển `CREATED → VALIDATED → APPROVED`. Nếu một listener nhận `APPROVED` rồi yêu cầu `approve()` lần nữa, domain model nên từ chối hoặc coi đó là thao tác idempotent và **không tạo thêm `OrderApproved`**.

~~~java
// Minh họa domain logic, không phải chương trình độc lập.
public boolean approve() {
    if (status == Status.APPROVED) {
        return false; // Không có transition, không sinh event mới.
    }
    if (status != Status.VALIDATED) {
        throw new IllegalStateException("Invalid state transition");
    }
    status = Status.APPROVED;
    return true;
}
~~~

Application service chỉ publish event khi method trả về `true` (hoặc aggregate ghi nhận một event mới hợp lệ). Quy tắc này ngăn vòng lặp ở **nguồn phát**, không chỉ ở listener.

Cần chú ý:

- Nếu nghiệp vụ cho phép quay lại cùng một trạng thái (ví dụ `REVIEW → DRAFT → REVIEW`), chỉ chặn theo tên trạng thái là quá thô. Nên kiểm soát **chuyển tiếp cụ thể**, version của aggregate và **một hành động nghiệp vụ có thật**.
- Kiểm tra và cập nhật trạng thái cần bảo đảm tính nhất quán khi có concurrency; với database dùng optimistic locking, unique constraint hoặc transaction phù hợp.
- `@EventListener(condition = "...")` có thể lọc event trước khi chạy listener, nhưng biểu thức condition không thay thế việc kiểm tra invariant tại domain model.

## 5. Giải pháp 2 — Theo dõi các bước đã đi qua trong cùng một chain

Khi muốn thực hiện một chuỗi event hữu hạn, có thể đặt metadata **theo từng chuỗi xử lý**:

- `flowId` hoặc `correlationId`: định danh cùng một chuỗi.
- `step`: bước xử lý hiện tại.
- `visited`: tập các bước hoặc transition keys đã qua trong chain.
- `hop`: số lần chuyển từ event ban đầu đến event hiện tại.

Trước khi phát event kế tiếp, listener kiểm tra:

1. Bước kế tiếp đã nằm trong `visited` chưa?
2. `hop` đã đạt giới hạn chưa?
3. Transition này có hợp lệ theo workflow hiện tại không?

Nếu chạm một điều kiện chặn, dừng việc publish và log/tracing có cấu trúc. **Phải mang metadata trong event** nếu chain có thể vượt thread/process; một biến global hoặc static set sẽ làm các workflow độc lập ảnh hưởng lẫn nhau.

### Giới hạn của `visited`

`visited` theo tên bước phù hợp với **workflow không được lặp bước**. Nó không phù hợp với những bài toán có vòng lặp nghiệp vụ hợp lệ như “retry bước VERIFY tối đa ba lần”. Trong trường hợp đó, dùng **transition key**, `attempt`, version hoặc state machine có quy tắc lặp hữu hạn thay vì cấm mọi lần quay lại cùng trạng thái.

Không để tập visited tăng không giới hạn trong event gửi qua broker. Với chain dài, có thể thay bằng các cờ trạng thái và ngân sách bước; việc lưu trace đầy đủ nên thực hiện trong observability system.

## 6. Giải pháp 3 — Giới hạn số chặng (hop budget)

Ngay cả khi chưa phát hiện một chu kỳ rõ, mỗi event có thể mang **hop count** để tạo trần an toàn:

~~~text
hop = 0 : OrderCreated
hop = 1 : OrderValidated
hop = 2 : InventoryReserved
...
hop = max : DỪNG, không phát tiếp
~~~

Quy tắc: **mỗi khi phát event con, `hop` phải tăng đúng 1**, đồng thời `maxHops` phải có giới hạn hữu hạn. Với event đầu tiên, `hop=0`.

Hop limit là **lớp phòng vệ phụ**, không phải điều kiện nghiệp vụ đủ để quyết định “thành công”. Nếu một workflow hợp lệ bị chặn ở hop limit, cần phản hồi lỗi quan sát được thay vì im lặng coi đã hoàn tất.

Trong hệ thống phân tán, ngân sách hop phải được giữ khi chuyển sang message envelope hoặc outbox, tránh mỗi service tự reset về 0 làm chu kỳ không bao giờ chạm giới hạn.

## 7. Ví dụ Java 17+ chạy được: guard hai lớp chống vòng lặp

Dự án dùng **Spring Framework 6.2.12**, JDK 17+ và Maven. Không cần Spring Boot hoặc database.

Luồng được cố ý thiết kế có chu kỳ:

~~~text
CREATED -> VALIDATED -> NOTIFIED -> CREATED
~~~

Nếu không có guard, listener nhận CREATED, tạo VALIDATED; listener nhận VALIDATED, tạo NOTIFIED; listener nhận NOTIFIED lại tạo CREATED và chu kỳ tái diễn mãi.

Chương trình dùng **hai điều kiện độc lập**:

1. Nếu bước tiếp theo đã xuất hiện trong `visited`, in `stop cycle` và không publish.
2. Nếu `hop >= MAX_HOPS`, in `stop hop limit` và không publish.

Dùng record Java để sao chép `visited` thành tập bất biến, không chia sẻ mutable set giữa listener. Ví dụ thứ hai cố ý đưa một event đã sử dụng hết hop budget để chứng minh lớp bảo vệ giới hạn.

Tạo cấu trúc:

~~~text
spring-event-cycle-guard/
├── pom.xml
└── src/main/java/demo/EventCycleGuardDemo.java
~~~

### 7.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-event-cycle-guard</artifactId>
    <version>1.0.0</version>

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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.2. `src/main/java/demo/EventCycleGuardDemo.java`

~~~java
package demo;

import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventCycleGuardDemo {

    public record FlowEvent(
            String flowId,
            String step,
            int hop,
            Set<String> visited) {

        public FlowEvent {
            if (flowId == null || flowId.isBlank()) {
                throw new IllegalArgumentException("flowId is required");
            }
            if (step == null || step.isBlank()) {
                throw new IllegalArgumentException("step is required");
            }
            if (hop < 0) {
                throw new IllegalArgumentException("hop cannot be negative");
            }
            if (visited == null || !visited.contains(step)) {
                throw new IllegalArgumentException("visited must contain step");
            }
            visited = Set.copyOf(visited);
        }
    }

    public static class GuardedFlowListener {
        private static final int MAX_HOPS = 3;
        private final ApplicationEventPublisher publisher;

        public GuardedFlowListener(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        @EventListener
        public void handle(FlowEvent event) {
            System.out.println(
                "receive " + event.flowId()
                + " " + event.step()
                + " hop=" + event.hop());

            String next = switch (event.step()) {
                case "CREATED" -> "VALIDATED";
                case "VALIDATED" -> "NOTIFIED";
                case "NOTIFIED" -> "CREATED"; // Cố ý tạo chu kỳ.
                default -> null;
            };

            if (next == null) {
                return; // Không có bước tiếp theo.
            }

            // Guard 1: mỗi bước trong flow này chỉ được đi qua một lần.
            if (event.visited().contains(next)) {
                System.out.println(
                    "stop cycle " + event.step() + " -> " + next);
                return;
            }

            // Guard 2: giới hạn độ dài chuỗi, kể cả khi không lặp bước.
            if (event.hop() >= MAX_HOPS) {
                System.out.println(
                    "stop hop limit " + event.step() + " -> " + next);
                return;
            }

            Set<String> newVisited = new LinkedHashSet<>(event.visited());
            newVisited.add(next);

            publisher.publishEvent(new FlowEvent(
                event.flowId(), next, event.hop() + 1, newVisited));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public GuardedFlowListener guardedFlowListener(
                ApplicationEventPublisher publisher) {
            return new GuardedFlowListener(publisher);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            context.publishEvent(new FlowEvent(
                "flow-1", "CREATED", 0, Set.of("CREATED")));

            // Mô phỏng một envelope đã sử dụng hết hop budget.
            context.publishEvent(new FlowEvent(
                "flow-2", "CREATED", 3, Set.of("CREATED")));

            System.out.println("finished");
        }
    }
}
~~~

Chạy ở thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.EventCycleGuardDemo
~~~

Những dòng do **chính chương trình** in ra:

~~~text
receive flow-1 CREATED hop=0
receive flow-1 VALIDATED hop=1
receive flow-1 NOTIFIED hop=2
stop cycle NOTIFIED -> CREATED
receive flow-2 CREATED hop=3
stop hop limit CREATED -> VALIDATED
finished
~~~

Một số môi trường có thể hiển thị thêm log của Maven/Spring. Phần stdout trên chỉ mô tả các dòng được in từ `System.out` trong ví dụ.

### 7.3. Vì sao output xác định?

- `flow-1` bắt đầu ở CREATED với `visited={CREATED}` và `hop=0`.
- Listener nhận CREATED, thấy VALIDATED chưa có trong visited và hop chưa đạt 3, nên publish event VALIDATED với `hop=1`.
- Listener tiếp tục publish NOTIFIED với `hop=2`.
- Tại NOTIFIED, bước tiếp theo sẽ là CREATED nhưng CREATED đã tồn tại trong visited, nên `stop cycle` được in và chuỗi dừng.
- `flow-2` bắt đầu với `hop=3`, visited chưa có VALIDATED. Kiểm tra visited không chặn, nhưng `MAX_HOPS=3`, vì vậy in `stop hop limit`.
- Với multicaster mặc định đồng bộ, hai chuỗi đều kết thúc trước khi main in `finished`. Không có `Thread.sleep` hoặc race condition trong ví dụ.

Ví dụ cố ý dùng một `FlowEvent` chung với field `step` để quan sát chu kỳ dễ dàng. Trong code production, các event nghiệp vụ nên có **kiểu rõ ràng** (ví dụ `OrderCreated`, `OrderValidated`) và transition/state machine tường minh; không bắt buộc gom tất cả sự kiện về một kiểu stringly typed.

### 7.4. Tại sao phải copy visited?

Nếu dùng cùng một `HashSet` mutable truyền qua nhiều event, listener khác có thể sửa lịch sử sự kiện, đặc biệt khi bật `@Async` hoặc nhiều subscriber. Constructor của record dùng `Set.copyOf` để bảo vệ payload. Trước mỗi event mới, listener tạo `LinkedHashSet` từ visited cũ, thêm bước mới rồi tạo một record khác.

Cấu trúc ví dụ là **snapshot cho từng event**, không có global state và không làm hai flow khác nhau ảnh hưởng lẫn nhau.

## 8. Giải pháp 4 — Event ID và xử lý idempotent

`visited`/hop ngăn **chuỗi gọi lặp vô hạn**, nhưng chưa giải quyết việc cùng một event được giao **nhiều lần** (retry, redelivery, consumer restart).

Một event envelope trong thực tế có thể chứa:

~~~java
// Minh họa dữ liệu: không phải chương trình độc lập.
public record EventEnvelope<T>(
        String eventId,
        String correlationId,
        String causationId,
        String aggregateId,
        long aggregateVersion,
        int hop,
        T payload
) {}
~~~

- **eventId:** định danh một event occurrence. Redelivery cùng event nên giữ lại ID để deduplication.
- **correlationId:** gắn những event trong cùng một flow/request nghiệp vụ.
- **causationId:** chỉ rõ event hoặc command nào trực tiếp gây ra event mới.
- **aggregateId/version:** giúp subscriber kiểm soát trạng thái hiện tại, thứ tự và xử lý thay đổi cũ.
- **hop:** ngân sách chiều dài chuỗi; event con dùng hop của event cha cộng 1.

Đừng kỳ vọng `eventId` khác nhau sẽ tự phát hiện vòng lặp: chu kỳ A→B→A thường tạo một **ID mới cho mỗi event**. Muốn phát hiện chu kỳ, cần xét **quan hệ nhân quả/transition** hoặc trạng thái workflow, không chỉ trùng eventId.

Đối với consumer bền vững, một mẫu idempotency là lưu `(consumerName, eventId)` vào bảng có **unique constraint** cùng transaction với side effect. Nếu xử lý lại cùng event, duplicate key hoặc kiểm tra trạng thái đã xử lý giúp bỏ qua side effect; việc check-then-insert không nguyên tử dễ xảy ra race. Với HTTP webhook có thể dùng idempotency key tương đương.

Ví dụ mô hình SQL:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Tùy database, nên thực hiện insert idempotent và cập nhật nghiệp vụ trong cùng transaction; nếu một trong hai lỗi, cả hai cùng rollback.

## 9. Giải pháp 5 — Cấm phản hồi vô nghĩa và điều phối theo state machine

Một nguyên nhân kinh điển của vòng lặp là các module chỉ phản ứng với **“dữ liệu có event”** mà không xét **“dữ liệu có thực sự thay đổi không”**:

~~~text
InventoryUpdated -> OrderSync -> InventoryUpdated -> ...
~~~

Giải pháp ở tầng nghiệp vụ:

1. Listener đọc trạng thái/phiên bản hiện tại.
2. Tính trạng thái mong muốn.
3. Nếu trạng thái mong muốn **giống trạng thái hiện tại**, kết thúc và **không phát event mới**.
4. Nếu thực sự có transition hợp lệ, commit thay đổi và chỉ tạo event mô tả transition ấy.
5. Có version/optimistic locking hoặc khóa phù hợp để xử lý concurrent updates.

Với workflow có nhiều trạng thái, tốt hơn là khai báo đồ thị chuyển trạng thái hữu hạn:

~~~text
CREATED --validate--> VALIDATED --approve--> APPROVED
                      |
                      +--reject--> REJECTED
~~~

Nếu callback sau APPROVED lại yêu cầu CREATED cho cùng version mà không có luật rollback rõ ràng, state machine từ chối. Khi phải cho phép một vòng nghiệp vụ (ví dụ gửi lại yêu cầu review), đưa `revision`, `attempt` hoặc `cycleNumber` vào state và giới hạn số lần.

Trong hệ thống có nhiều service, cân nhắc **orchestrator/process manager** thay vì để mọi listener tự phát bất kỳ event nào. Orchestrator định nghĩa chuyển trạng thái, timeout, compensation và điều kiện hoàn tất; event chỉ cung cấp thông tin về các bước đã xảy ra.

## 10. Giải pháp 6 — Ngăn vòng lặp qua broker, webhook và retry

Đối với integration event, các biện pháp thêm thường cần thiết:

| Nguyên nhân | Biện pháp |
| --- | --- |
| A đồng bộ dữ liệu sang B, B gửi ngược cùng bản cập nhật về A | `originService`, `correlationId`, entity version và kiểm tra thay đổi thực |
| Consumer gặp poison message rồi retry vô hạn | Giới hạn retry, backoff, dead-letter queue, alert |
| Broker giao lại cùng event | Idempotency key và processed-event store |
| Webhook phản hồi thay đổi do chính mình tạo | Source marker + version, tránh tạo cùng transition một lần nữa |
| Event chain vượt quá kỳ vọng | Propagate `hop`/TTL, giới hạn tối đa và log lý do bị chặn |
| Hai publisher đồng thời phát cùng transition | Transaction, unique constraint, optimistic locking |
| Relay gửi message thành công nhưng chưa kịp đánh dấu outbox | Consumer idempotent, trạng thái relay rõ ràng |

**Transactional outbox** (ghi event cần gửi trong cùng transaction với dữ liệu nghiệp vụ, relay phát lại sau commit) giúp giải quyết mất message khi process crash. Nhưng outbox **không tự ngăn vòng lặp**; nếu consumer tiếp tục tạo sự kiện phản hồi vô hạn thì outbox có thể làm chu kỳ **bền vững và kéo dài hơn**. Vẫn cần state machine, deduplication và hop budget.

Khi dùng `@TransactionalEventListener(AFTER_COMMIT)`, sự kiện được xử lý sau commit, nhưng annotation **không có khả năng phát hiện chu kỳ** và không phải một message queue có replay. Chuỗi phản ứng qua nhiều transaction vẫn có thể quay lại bước đầu nếu code liên tục tạo business transitions không hợp lệ.

## 11. Thiết kế bảo vệ theo phạm vi

Không có một guard phù hợp cho tất cả hệ thống. Chọn guard theo **đơn vị muốn ngăn lặp**:

| Phạm vi | Khóa/metadata phù hợp | Điều ngăn được |
| --- | --- | --- |
| Trong cùng method/call stack | Local visited set, recursion depth, state transition | Tự publish quay lại ngay |
| Trong một flow/request | correlationId, visited transitions, hop budget | Vòng event qua nhiều listener/thread |
| Trên một aggregate | aggregateId, version, valid state transitions | Áp dụng lại cùng thay đổi nghiệp vụ |
| Theo delivery | consumerName + eventId | Redelivery/retry cùng event |
| Giữa nhiều service | correlation/causation, origin, version, TTL, outbox + idempotency | Echo loop và retry storm |

Lưu ý quan trọng: **global static set chứa mọi event từng thấy không phải giải pháp**. Nó có thể chặn nhầm những workflow mới, rò bộ nhớ và không đúng khi ứng dụng có nhiều instance. Nếu phải lưu lịch sử, hãy xác định khóa và thời hạn lưu (TTL) theo nghiệp vụ; dùng storage phân tán khi nhiều instance cùng xử lý.

## 12. Quan sát và xử lý sự cố

Các vòng lặp event thường phát hiện được sớm bằng metrics/tracing nếu mỗi event có metadata:

- Log `eventType`, `eventId`, `correlationId`, `causationId`, `aggregateId`, `hop` và kết quả `processed/skipped/blocked`.
- Đo số event publish và số event sinh ra mỗi event đầu vào (**fan-out**).
- Cảnh báo khi một correlationId có quá nhiều event, hop bất thường hoặc chu kỳ chuyển trạng thái lặp nhanh.
- Theo dõi queue backlog, retry count, DLQ, CPU/thread pool và transaction latency.
- Nếu đã block, log lý do `cycle_detected`, `hop_limit`, `duplicate` hoặc `invalid_transition`; không âm thầm bỏ lỗi nghiệp vụ.
- Dùng tracing span links để thể hiện quan hệ nhân quả khi event chạy qua async hoặc broker.

Khi gặp vòng lặp production, thao tác an toàn là giảm tải ở **nguồn publish hoặc consumer gây feedback**, xác định correlation/causation chain và sửa quy tắc sinh event. Chỉ tắt toàn bộ logging hoặc tăng worker count có thể che triệu chứng và làm tăng áp lực lên hệ thống.

## 13. Kiểm thử những tình huống nào?

### Kiểm thử đồng bộ

- Publish CREATED, xác nhận mỗi bước CREATED → VALIDATED → NOTIFIED chỉ xuất hiện một lần.
- Xác nhận NOTIFIED không phát lại CREATED khi visited đã chứa nó.
- Kiểm tra chuỗi kết thúc và caller trở về; không cần `Thread.sleep`.
- Đặt `hop` bằng max và xác nhận không có event con.
- Gửi hai flowId độc lập để chắc chắn visited của flow này không làm flow khác bị chặn.

### Kiểm thử state machine và concurrency

- Khi command không thay đổi trạng thái, assert **không publish** event mới.
- Khi aggregate đã ở trạng thái APPROVED, lặp approve không gửi thêm một `OrderApproved` vô nghĩa.
- Khi hai request cùng xử lý một aggregate/version, dùng optimistic locking hoặc unique constraint để không phát hai transition mâu thuẫn.
- Kiểm tra workflow có vòng lặp **hợp lệ** với attempt giới hạn, tránh dùng visited quá đơn giản làm mất nghiệp vụ.

### Kiểm thử async và tích hợp

- Bật executor cho listener thích hợp và kiểm tra hop/correlation có được truyền giữa threads không.
- Với broker, giả lập redelivery cùng eventId, assert side effect chỉ thực hiện một lần.
- Giả lập poison message; sau số retry hữu hạn, message đi DLQ và không sinh vô hạn các event phản hồi.
- Với outbox, kiểm tra crash/restart không làm bỏ mất thông điệp nhưng cũng không tự phát sinh lại các side effect đã idempotent.
- Nếu có webhook hai chiều, kiểm tra origin marker và version có ngăn echo loop.

## 14. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Listener `@EventListener` trả lại cùng event để “trả kết quả” | Spring tự publish lại, có thể recursion vô hạn | Dùng `void` cho callback không tạo event; chỉ trả về event mới có chủ ý và điểm dừng |
| A tạo B, B lại tạo A không có guard | Stack overflow hoặc event storm | State machine, visited transitions, hop budget |
| Chuyển sang `@Async` và tưởng đã giải quyết | Chỉ biến recursion thành queue storm | Vẫn phải dừng tại nguồn, truyền metadata qua threads |
| Chỉ deduplicate theo eventId | Mỗi vòng tạo eventId mới, chu kỳ vẫn tiếp tục | Kiểm tra correlation/transition/state |
| Chặn mọi event cùng tên trên toàn JVM | Chặn nhầm flow độc lập, rò bộ nhớ | Guard theo flowId/aggregate/version và TTL |
| Giới hạn hop nhưng không có cảnh báo | Workflow hợp lệ bị cắt, lỗi bị che | Thông báo trạng thái blocked và điều tra |
| Để retry vô hạn poison message | Queue backlog và side effect trùng | Bounded retry, backoff, DLQ |
| Dùng `@Order` để nghĩ không còn vòng lặp | Order chỉ sắp ưu tiên, không xóa cạnh A→B→A | Sửa đồ thị trạng thái và điều kiện publish |
| Tin rằng `AFTER_COMMIT`/outbox tự chống feedback | Chu kỳ có thể kéo dài qua nhiều transaction | Idempotency, state machine và hop/TTL |

## 15. Checklist áp dụng

1. Ai phát event nào? Hãy vẽ đồ thị **event type → listener → event mới** và tìm các chu kỳ.
2. Event mới có đại diện cho **một thay đổi thật sự** không?
3. Có bước kết thúc hoặc invariant ngăn quay lại trạng thái sai không?
4. Event có `correlationId`, `causationId`, `eventId` và `hop` khi cần không?
5. Guard chống cycle gắn với **đúng flow/aggregate**, không phải global static set chứ?
6. Hop limit có được propagate qua executor/broker và có log khi bị chặn không?
7. Consumer có idempotency khi redelivery cùng eventId không?
8. Retry có số lần tối đa, backoff, DLQ và monitoring không?
9. Code có vô tình dùng `@EventListener` return value để phát tiếp event cùng kiểu không?
10. Test đã chứng minh chuỗi kết thúc ở cả chế độ đồng bộ lẫn bất đồng bộ chưa?

**Kết luận:** Ngăn vòng lặp phát event trong Spring không phải là “không cho listener publish event khác”, mà là làm cho **mỗi cạnh chuyển tiếp có ý nghĩa nghiệp vụ, mỗi chain có giới hạn và mỗi lần xử lý có khả năng chống lặp**. Hãy dùng state machine và idempotency làm nền tảng; bổ sung visited/hop budget, trace metadata, bounded retry và cảnh báo để hệ thống không biến một sự kiện hợp lệ thành một vòng phản hồi vô hạn.

## Tài liệu chính thức

- Spring Framework 6.2 — ApplicationContext events, synchronous listeners, `@EventListener` return value và `@Async`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — `@EventListener` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html
- Spring Framework 6.2 — `ApplicationEventPublisher` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2 — `SimpleApplicationEventMulticaster` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
