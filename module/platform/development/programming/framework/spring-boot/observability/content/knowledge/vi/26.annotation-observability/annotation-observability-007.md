# AspectJ weaver trong annotation observability

> **Chương:** Annotation observability  
> **Bài:** AspectJ weaver  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. AspectJ weaver giải quyết vấn đề gì?

Trong ứng dụng Spring Boot, nhiều hoạt động cần được quan sát có tính lặp lại: đo thời gian method, tạo observation khi gọi service, ghi nhận exception hoặc thêm metadata cho một operation. Nếu mỗi method tự viết mã bắt đầu/kết thúc timer, xử lý exception và khôi phục context, code nghiệp vụ sẽ bị trộn với instrumentation.

Aspect-oriented programming (AOP) tách các hành vi cắt ngang thành **aspect**. AspectJ là một hệ sinh thái AOP cho Java; **weaver** là thành phần kết hợp aspect với bytecode của class để hành vi advice được thực thi tại các join points phù hợp.

Trong annotation observability, một annotation như @Observed hoặc @Timed có thể đánh dấu method cần instrument. Một aspect đọc annotation và bao quanh lời gọi method để tạo Observation, Timer hoặc tracing behavior. Aspect có thể được áp dụng bằng Spring AOP proxy hoặc bằng AspectJ weaving, tùy cách tích hợp.

Điều quan trọng: **AspectJ weaver không phải metrics registry, tracing exporter hay ObservationRegistry.** Nó là công cụ áp dụng aspect vào bytecode. Việc tạo và xuất telemetry vẫn cần instrumentation, handlers, registry/SDK và exporter tương ứng.

~~~mermaid
flowchart TD
  A["Method có annotation"] --> B["Aspect / advice"]
  B --> C{"Cách áp dụng aspect"}
  C --> D["Spring AOP proxy"]
  C --> E["AspectJ weaving"]
  D --> F["Method invocation được bao quanh"]
  E --> F
  F --> G["Micrometer Observation / Timer"]
  G --> H["Metrics handler"]
  G --> I["Tracing handler"]
  H --> J["MeterRegistry / exporter"]
  I --> K["Tracer / span exporter"]
~~~

## 2. Aspect, advice, pointcut và join point

Một aspect thường gồm các khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Aspect | Module chứa cross-cutting behavior | Đo thời gian method |
| Join point | Điểm thực thi có thể được advice áp dụng | Method execution |
| Pointcut | Biểu thức chọn join points | Các method trong package service |
| Advice | Hành vi chạy tại join point | Around advice bắt đầu/dừng timer |
| Weaver | Thành phần kết hợp aspect với target code | AspectJ compiler hoặc LTW weaver |
| Inter-type declaration | Thêm thành viên vào type qua AspectJ | Khai báo method/field bổ sung |

Một around advice có thể thực hiện trước và sau method, đồng thời xử lý exception:

~~~java
@Around("execution(* com.example.orders..*(..))")
public Object observe(ProceedingJoinPoint joinPoint) throws Throwable {
    long started = System.nanoTime();
    try {
        return joinPoint.proceed();
    } finally {
        long elapsed = System.nanoTime() - started;
        recordDuration(joinPoint.getSignature(), elapsed);
    }
}
~~~

Đây là ví dụ minh họa ý tưởng. Nó không phải cấu hình Micrometer hoàn chỉnh và không nên tự dùng thay cho instrumentation có sẵn. Đặc biệt với reactive return types, method return thường chỉ trả Mono/Flux; around advice ở trên có thể chỉ đo thời gian tạo publisher chứ không đo thời gian xử lý sau subscription.

## 3. Spring AOP proxy khác AspectJ weaving thế nào?

Spring AOP thường dùng proxy để intercept method calls đi qua proxy. AspectJ weaving thay đổi bytecode để advice được áp dụng tại join points mà AspectJ hỗ trợ, không cần mọi lời gọi đều đi qua Spring proxy.

| Đặc điểm | Spring AOP proxy | AspectJ weaving |
| --- | --- | --- |
| Cơ chế | JDK dynamic proxy hoặc CGLIB proxy | Biến đổi bytecode |
| Join points | Chủ yếu method execution trên Spring beans | Rộng hơn, gồm method/constructor execution, call, field access… tùy AspectJ |
| Self-invocation | Lời gọi this.method() thường bỏ qua proxy | Có thể được weave nếu pointcut phù hợp |
| Object không do Spring quản lý | Không tự được proxy | Có thể được weave nếu class nằm trong phạm vi weaving |
| Cấu hình | Spring AOP auto-proxy infrastructure | Compile-time, post-compile hoặc load-time weaving |
| Debug | Kiểm tra proxy và bean wiring | Kiểm tra woven bytecode, weaver và classloader |

Spring AOP có thể đủ cho nhiều use cases annotation observability trong Spring Boot. Không thêm AspectJ weaving chỉ vì code có annotation @Observed. Trước tiên kiểm tra aspect cần dùng được Spring đăng ký và method call đi qua proxy.

AspectJ weaving phù hợp khi cần join points mà proxy không bao phủ, ví dụ self-invocation hoặc một số constructor/field join points. Cấu hình phức tạp hơn và cần cân nhắc classloader, build pipeline, startup và khả năng debug.

## 4. Ba kiểu AspectJ weaving

AspectJ hỗ trợ các cách weave phổ biến:

### 4.1. Compile-time weaving (CTW)

AspectJ compiler ajc biên dịch source và aspect thành bytecode đã được weave. Aspect được áp dụng trong quá trình build.

~~~text
Java source + Aspect source
          |
          v
     AspectJ compiler
          |
          v
  Woven .class files
          |
          v
       Application
~~~

Ưu điểm:
- Không cần weaver agent lúc runtime cho phần đã weave.
- Lỗi pointcut/weaving có thể được phát hiện trong build.
- Bytecode đã được chuẩn bị trước khi deploy.

Hạn chế:
- Build cần cấu hình AspectJ compiler/plugin.
- Phải xử lý đúng source sets, generated classes và dependency.
- Thay đổi aspect có thể yêu cầu biên dịch lại các class liên quan.

### 4.2. Post-compile hoặc binary weaving

Class Java được biên dịch trước, sau đó AspectJ compiler weave aspect vào các file .class hoặc JAR đã tạo.

~~~text
Java compiler -> .class / JAR
                       |
                       v
              AspectJ post-compile
                       |
                       v
                 Woven bytecode
~~~

Cách này hữu ích khi không muốn thay compiler cho toàn bộ source. Tuy nhiên phải quản lý thứ tự build, artifact gốc và artifact sau weave rõ ràng.

### 4.3. Load-time weaving (LTW)

LTW weave class khi JVM classloader nạp class. Thường cần AspectJ weaver agent và cấu hình aspect/target classes.

~~~text
JVM startup
   |
   +--> -javaagent:aspectjweaver.jar
   |
ClassLoader loads class
   |
AspectJ weaver transforms bytecode
   |
Woven class is defined
~~~

Ưu điểm là có thể áp dụng weaving lúc runtime mà không cần tạo sẵn woven JAR. Hạn chế là phải cấu hình JVM startup, classloader, weaving scope và runtime environment chính xác.

Không bật đồng thời nhiều cơ chế weaving cho cùng class nếu không có lý do và kiểm chứng rõ. Có thể gây biến đổi lặp hoặc khó truy vết nguồn advice.

## 5. AspectJ weaver không tự bật Micrometer annotations

Micrometer Observation cung cấp API mô tả operation. Micrometer cũng cung cấp các annotation và aspect hỗ trợ trong một số module:

- @Observed đánh dấu method cần được quan sát khi aspect tương ứng được cấu hình.
- @Timed đánh dấu method cần đo thời gian khi TimedAspect được đăng ký.
- ObservationRegistry quản lý lifecycle và handlers.
- MeterRegistry lưu/truy xuất meters.
- Tracing bridge/handler có thể tạo spans từ Observation.

Một annotation chỉ là metadata cho đến khi có thành phần xử lý nó. Thêm dependency aspectjweaver không tự động tạo Observation hoặc Timer.

Ví dụ @Observed:

~~~java
@Service
public class OrderService {

    @Observed(name = "orders.create", contextualName = "create-order")
    public Order create(CreateOrderCommand command) {
        return doCreate(command);
    }
}
~~~

Để annotation được xử lý, cần đăng ký ObservedAspect theo hướng dẫn Micrometer/Spring Boot version đang dùng và cung cấp ObservationRegistry. Cơ chế gọi aspect có thể là Spring AOP proxy trong cấu hình thông thường; không suy ra bắt buộc phải dùng AspectJ LTW chỉ từ việc có annotation.

Ví dụ @Timed:

~~~java
@Service
public class CatalogService {

    @Timed(value = "catalog.refresh", histogram = true)
    public void refresh() {
        reloadCatalog();
    }
}
~~~

@Timed cần TimedAspect được cấu hình trong ứng dụng. Nó đo method theo semantics của aspect; với reactive method, cần xác minh aspect/module có hỗ trợ theo dõi publisher lifecycle hay không. Đừng mặc định method trả Mono được đo tới khi Mono hoàn tất.

## 6. Cấu hình annotation aspects trong Spring Boot

Ví dụ cấu hình khái niệm:

~~~java
@Configuration
public class ObservabilityAspectConfiguration {

    @Bean
    ObservedAspect observedAspect(ObservationRegistry registry) {
        return new ObservedAspect(registry);
    }

    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
~~~

Các class/package và điều kiện auto-configuration cần khớp phiên bản Micrometer/Spring Boot của dự án. Không đăng ký hai aspect tương đương nếu Boot hoặc một starter đã tự cấu hình chúng; việc trùng aspect có thể tạo Observation/Timer lặp.

Dependency thường cần các module Micrometer phù hợp và Spring AOP infrastructure. Dependency AspectJ runtime/weaver chỉ cần khi cách triển khai aspect hoặc weaving thực sự yêu cầu nó. Kiểm tra dependency management/BOM thay vì tự pin version không tương thích.

### 6.1. Kiểm tra aspect có được đăng ký

- Xem Spring application context có bean ObservedAspect/TimedAspect cần thiết không.
- Kiểm tra log startup và condition report nếu auto-configuration có điều kiện.
- Gọi method qua Spring-managed bean.
- Kiểm tra meter/observation có xuất hiện trong registry.
- Kiểm tra aspect có chạy đúng một lần.
- Xác minh trace/span được tạo nếu tracing handler hoạt động.

Không chỉ kiểm tra annotation tồn tại bằng reflection; điều đó chưa chứng minh advice đã được áp dụng.

## 7. Cấu hình Load-time weaving với AspectJ

Nếu use case thực sự cần AspectJ LTW, JVM cần nạp weaver agent trước khi ứng dụng khởi động.

Ví dụ:

~~~bash
java -javaagent:/opt/aspectj/aspectjweaver.jar \
     -jar target/application.jar
~~~

JAR phải là AspectJ weaver version tương thích với Java runtime và AspectJ artifacts của ứng dụng. Đường dẫn ví dụ cần thay bằng vị trí artifact thực tế.

Một cấu hình aop.xml tối giản có thể đặt trong META-INF/aop.xml trên classpath:

~~~xml
<!DOCTYPE aspectj PUBLIC
  "-//AspectJ//DTD//EN"
  "https://www.eclipse.org/aspectj/dtd/aspectj.dtd">
<aspectj>
  <aspects>
    <aspect name="com.example.observability.ExecutionAspect"/>
  </aspects>
  <weaver>
    <include within="com.example.orders..*"/>
  </weaver>
</aspectj>
~~~

Đây là khung cấu hình minh họa. Aspect phải là AspectJ-compatible aspect được compiler/runtime nhận diện; include scope cần giới hạn để tránh weave quá nhiều thư viện. Một aspect Spring @Aspect có thể được áp dụng qua Spring AOP proxy mà không cần đưa vào LTW configuration.

Nếu ứng dụng dùng nhiều classloader hoặc chạy trong container/application server, kiểm tra nơi aop.xml được tìm thấy và class nào được loader nào định nghĩa.

## 8. Compile-time weaving trong build

Compile-time weaving yêu cầu cấu hình AspectJ compiler hoặc plugin build phù hợp. Dự án Maven/Gradle cần xác định:
- Source và target compatibility.
- AspectJ compiler version.
- Aspect source path.
- Compile/test source sets.
- Dependency aspectjrt/aspectjweaver tương ứng.
- Generated classes có cần weave hay không.
- Packaging có chứa bytecode đã weave không.

Một pipeline tổng quát:

~~~mermaid
flowchart TD
  A["Source Java + aspects"] --> B["Compile"]
  B --> C["AspectJ weaving"]
  C --> D["Run unit/integration tests"]
  D --> E["Package woven artifact"]
  E --> F["Deploy"]
~~~

Không copy plugin configuration từ dự án khác mà không kiểm tra version và compiler compatibility. Sau build, xác minh artifact thực sự đã được weave bằng log compiler hoặc công cụ kiểm tra bytecode. Chỉ thấy plugin trong build file không chứng minh class đã được weave.

## 9. Pointcut scope và hiệu năng

Pointcut quá rộng có thể weave nhiều class không liên quan, làm tăng thời gian build/startup, khó debug và tạo advice ở những nơi không mong muốn.

Nên:
- Giới hạn package/domain cụ thể.
- Loại trừ framework, generated code và third-party libraries nếu không cần.
- Chỉ instrument method có ý nghĩa vận hành.
- Tránh pointcut match mọi method Object/getter/setter.
- Theo dõi số class được weave và startup time.
- Test behavior khi proxy và weaving cùng tồn tại.

Không dùng pointcut bắt mọi method để tạo một span cho mỗi lời gọi nội bộ. Điều đó dễ tạo telemetry quá chi tiết, tăng overhead và gây khó đọc trace.

## 10. Self-invocation và giới hạn proxy

Với Spring AOP proxy, method A gọi method B qua this thường không đi qua proxy lần thứ hai:

~~~java
@Service
public class ReportService {

    public void generate() {
        writeReport(); // self-invocation, thường bypass Spring proxy
    }

    @Observed(name = "report.write")
    public void writeReport() {
        // Write report.
    }
}
~~~

Nếu @Observed aspect được áp dụng bằng Spring proxy, lời gọi writeReport() nội bộ có thể không được intercept. Gọi generate() từ bean khác qua proxy không làm cho lời gọi this.writeReport() tự động đi qua proxy.

Cách xử lý:
- Chuyển method được instrument sang một Spring bean khác.
- Gọi qua một collaborator/proxy được inject đúng cách.
- Nếu thật sự cần join point self-invocation, đánh giá AspectJ weaving.
- Hoặc tạo Observation thủ công quanh operation có lifecycle rõ.

Không lạm dụng self-injection hoặc lấy bean từ ApplicationContext chỉ để né proxy limitation; thiết kế collaborator thường dễ hiểu và dễ test hơn.

## 11. Final, private, static và constructor join points

Spring AOP proxy có giới hạn theo loại proxy và method. Ví dụ:
- JDK dynamic proxy chỉ expose interface methods.
- CGLIB subclass proxy không override được final methods/classes.
- Private methods không thể được intercept theo cơ chế proxy thông thường.
- Static method không đi qua instance proxy.
- Constructor execution không phải join point của Spring AOP proxy.

AspectJ weaving hỗ trợ nhiều loại join points rộng hơn, bao gồm constructor execution và field access, tùy pointcut/weaving model. Tuy nhiên không phải mọi loại join point đều phù hợp cho observability. Instrument constructor hoặc field access có thể tạo quá nhiều events và làm lifecycle khó hiểu.

Chọn cơ chế theo yêu cầu thực tế thay vì chuyển toàn bộ ứng dụng sang LTW chỉ để intercept một private method.

## 12. Annotation observability và reactive lifecycle

Annotation aspect truyền thống thường bao quanh lời gọi method đồng bộ. Với method trả Mono/Flux, method có thể kết thúc ngay sau khi tạo publisher; công việc thật diễn ra khi subscribe.

~~~java
@Observed(name = "inventory.lookup")
public Mono<Stock> findStock(String sku) {
    return webClient.get()
            .uri("/stock/{sku}", sku)
            .retrieve()
            .bodyToMono(Stock.class);
}
~~~

Nếu aspect chỉ đo thời gian method invocation, observation có thể kết thúc trước khi HTTP exchange hoàn tất. Cần dùng integration hỗ trợ reactive context/lifecycle hoặc đặt Observation trong reactive pipeline để start/stop theo subscription và terminal signal.

Không dùng blocking để ép reactive method thành đồng bộ chỉ nhằm làm annotation timer hoạt động. Điều đó có thể gây thread starvation và thay đổi semantics.

## 13. Tránh duplicate instrumentation

Duplicate spans/metrics có thể xuất hiện khi cùng một method được instrument bởi:
- Spring AOP @Observed aspect.
- AspectJ woven advice.
- OTel Java Agent.
- Built-in Spring Web/JDBC instrumentation.
- Custom Observation thủ công.
- Một aspect @Timed khác đo cùng operation.

Trước khi bật nhiều cơ chế, xác định owner cho từng boundary. Ví dụ server HTTP span do Spring instrumentation sở hữu, database span do JDBC agent sở hữu, business operation span do @Observed sở hữu.

~~~text
HTTP server span
  orders.create observation
    JDBC query span
~~~

Đây là cấu trúc có ý nghĩa nếu mỗi span đại diện một operation khác nhau. Nếu @Observed và woven aspect cùng tạo hai spans tên orders.create cho cùng method, trace có thể bị lặp.

Kiểm tra waterfall, parent-child relation, span names, duration và meter counts. Đừng chỉ nhìn số span tổng.

## 14. Debug AspectJ weaving

Khi aspect không chạy hoặc class không được weave, điều tra theo thứ tự:

1. Aspect class có được compile/package không?
2. Pointcut có match target class/method không?
3. Cơ chế đang dùng là Spring proxy hay AspectJ weaving?
4. Nếu LTW, JVM có -javaagent đúng JAR không?
5. aop.xml có trên classpath đúng classloader không?
6. Weaver có include target package không?
7. Target class đã được load trước khi agent/config có hiệu lực không?
8. Có classloader/container instrumentation khác can thiệp không?
9. Build artifact có thực sự chứa woven bytecode không?
10. Có exception hoặc warning từ weaver bị bỏ qua không?

AspectJ weaver có thể xuất diagnostics tùy cấu hình. Chỉ bật verbose/weaver debug trong môi trường test hoặc trong thời gian điều tra; log weaving có thể rất nhiều.

### 14.1. Triệu chứng và nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| @Observed không tạo observation | ObservedAspect chưa được đăng ký hoặc method không đi qua proxy | Bean config, proxy, registry |
| @Timed không tạo meter | TimedAspect thiếu hoặc aspect không match | Bean registration và meter registry |
| Self-invocation không chạy advice | Spring proxy bypass | Chuyển bean hoặc dùng weaving có chủ đích |
| LTW không có tác dụng | Thiếu -javaagent hoặc aop.xml không được tìm thấy | JVM command line, classpath |
| Chỉ một số package được weave | Weaver include/exclude scope | aop.xml và diagnostics |
| Class không weave trong container | Classloader hoặc agent startup order | Runtime launch config |
| Advice chạy hai lần | Spring proxy và woven aspect cùng áp dụng | Kiểm tra ownership |
| Startup tăng mạnh | Pointcut quá rộng hoặc nhiều class được weave | Giới hạn scope, profiling |
| Reactive observation quá ngắn | Aspect đo publisher creation thay vì subscription | Reactive-aware instrumentation |
| Final method không được proxy intercept | CGLIB không override final method | Chọn interface/thiết kế khác hoặc AspectJ |
| Aspect có trong JAR nhưng không chạy | Có class không đồng nghĩa được weave/đăng ký | Kiểm tra runtime mechanism |

## 15. Bảo mật và vận hành khi dùng weaver

Weaving thay đổi bytecode mà JVM thực thi. Trong production, cần kiểm soát artifact, agent và cấu hình:

- Pin version weaver và quản lý dependency qua build.
- Chỉ dùng artifact từ nguồn tin cậy.
- Giới hạn class/package được weave.
- Kiểm thử woven artifact giống cách deploy thực tế.
- Theo dõi startup time và runtime overhead.
- Ghi lại JVM arguments và weaving configuration trong deployment manifest.
- Không bật debug weaving lâu dài nếu log volume lớn.
- Có thể rollback bằng cách deploy artifact/config trước đó.

Agent có quyền biến đổi class khi JVM load. Không thêm agent tùy tiện vào production mà không review compatibility, startup ordering và security posture.

## 16. Tình huống thực tế: @Observed không chạy khi self-invocation

**Bối cảnh:** order-service có method createOrder() gọi validateInventory() trong cùng bean. validateInventory() mang @Observed nhưng không thấy observation.

~~~java
@Service
public class OrderWorkflow {

    public Order createOrder(Command command) {
        validateInventory(command);
        return persist(command);
    }

    @Observed(name = "orders.validate-inventory")
    public void validateInventory(Command command) {
        // Validation and inventory checks.
    }

    private Order persist(Command command) {
        return new Order();
    }
}
~~~

### Bước 1 — xác định aspect mechanism

Nhóm đang dùng ObservedAspect thông qua Spring AOP proxy. Call từ controller tới createOrder() đi qua proxy, nhưng lời gọi this.validateInventory() diễn ra bên trong target object.

### Bước 2 — xác nhận proxy limitation

Đặt breakpoint/log ở aspect và gọi validateInventory() trực tiếp từ một bean khác trong test. Nếu call qua proxy được instrument nhưng self-call không được, nguyên nhân phù hợp với proxy semantics.

### Bước 3 — chọn cách sửa đơn giản

Tách validation thành bean riêng:

~~~java
@Service
public class InventoryValidationService {

    @Observed(name = "orders.validate-inventory")
    public void validate(Command command) {
        // Validation and inventory checks.
    }
}
~~~

OrderWorkflow inject InventoryValidationService và gọi method qua Spring bean proxy. Cách này làm ranh giới nghiệp vụ rõ ràng và không cần bật LTW.

### Bước 4 — khi nào mới dùng AspectJ weaving?

Nếu yêu cầu thật sự cần intercept self-invocation hoặc join points không được Spring proxy hỗ trợ, đánh giá compile-time hoặc load-time weaving. Kiểm thử woven bytecode, classloader, startup và không để cùng aspect chạy qua cả proxy lẫn weaver.

### Bước 5 — xác minh telemetry

Gọi một request tạo đơn. Trace cần có một observation orders.validate-inventory đúng vị trí và không bị duplicate. Kiểm tra meter, span duration, error behavior và context propagation.

**Kết quả mong muốn:** hiểu vì sao annotation không chạy, chọn đúng cơ chế interception và giữ trace rõ ràng.

## 17. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — Spring AOP proxy

Tạo service có method @Observed và ObservedAspect. Gọi method từ một bean khác, sau đó gọi bằng self-invocation. So sánh observation count và giải thích proxy boundary.

### Bài tập B — AspectJ LTW trong môi trường test

Tạo một aspect đơn giản và một target class. Cấu hình AspectJ weaver agent cùng aop.xml giới hạn package test. Xác minh advice chạy ở target class và ghi lại JVM arguments cần thiết.

### Bài tập C — so sánh CTW và LTW

Weave cùng một aspect theo compile-time và load-time trong hai profile test riêng. So sánh build artifact, startup, diagnostics và cách rollback.

### Bài tập D — @Observed và @Timed

Đăng ký đúng aspects, gọi method đồng bộ và xác minh Observation/Timer. Kiểm tra không có hai aspects cùng đo một operation ngoài chủ đích.

### Bài tập E — reactive lifecycle

Gắn annotation lên method trả Mono. So sánh thời gian method invocation với thời gian publisher hoàn tất. Dùng instrumentation reactive-aware để đo đúng lifecycle.

### Bài tập F — duplicate instrumentation

Bật Spring instrumentation, custom aspect và agent cho một test endpoint. Đọc waterfall, xác định spans trùng và phân công ownership cho từng boundary.

### Câu hỏi tự kiểm tra

1. AspectJ weaver làm gì với bytecode?
2. Aspect, advice, pointcut và join point khác nhau thế nào?
3. Spring AOP proxy khác AspectJ weaving ở cơ chế nào?
4. Compile-time, post-compile và load-time weaving khác nhau ra sao?
5. Thêm aspectjweaver dependency có tự bật @Observed không?
6. ObservedAspect và TimedAspect có vai trò gì?
7. Vì sao self-invocation thường bypass Spring AOP proxy?
8. Final/private/static methods bị giới hạn thế nào với proxy?
9. Khi nào LTW phù hợp hơn Spring AOP?
10. aop.xml và -javaagent tham gia LTW như thế nào?
11. Vì sao pointcut quá rộng có thể ảnh hưởng startup/performance?
12. Method trả Mono có thể bị đo sai lifecycle ra sao?
13. Làm thế nào tránh proxy aspect và woven aspect chạy hai lần?
14. Làm sao xác minh class thực sự đã được weave?
15. Khi annotation không tạo telemetry, cần kiểm tra những lớp nào?

**Tiêu chí hoàn thành:** giải thích AspectJ weaver và ba weaving modes; phân biệt Spring AOP proxy; cấu hình đúng aspect/annotation; hiểu self-invocation và method limitations; xử lý reactive lifecycle; kiểm tra weaving/debug; tránh duplicate instrumentation và đo overhead.

## 18. Ghi nhớ

- AspectJ weaver kết hợp aspect với bytecode; nó không phải ObservationRegistry, MeterRegistry hay exporter.
- Spring AOP proxy và AspectJ weaving là hai cơ chế interception khác nhau.
- AspectJ hỗ trợ compile-time, post-compile và load-time weaving.
- Thêm aspectjweaver không tự bật Micrometer @Observed hoặc @Timed; phải có aspect tương ứng và cấu hình đúng.
- ObservedAspect dùng ObservationRegistry; TimedAspect dùng MeterRegistry theo API/version phù hợp.
- Self-invocation thường bypass Spring proxy; tách collaborator là cách giải quyết đơn giản trong nhiều trường hợp.
- AspectJ weaving có thể hỗ trợ join points rộng hơn, nhưng cần kiểm soát classloader, build, startup và scope.
- Reactive method cần instrumentation theo subscription/terminal lifecycle, không chỉ thời gian tạo publisher.
- Tránh cùng một operation bị instrument bởi Spring proxy, AspectJ weaver, Java agent và custom Observation cùng lúc.
- Xác minh bằng bean wiring, weaving diagnostics, meter/span thực tế và trace waterfall.

## Tài liệu tham khảo

- [AspectJ — Development Environment and Tools](https://eclipse.dev/aspectj/doc/latest/devguide/)
- [AspectJ — Load-Time Weaving](https://eclipse.dev/aspectj/doc/latest/devguide/ltw.html)
- [Spring Framework — AOP](https://docs.spring.io/spring-framework/reference/core/aop.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot — AOP](https://docs.spring.io/spring-boot/reference/features/aop.html)

