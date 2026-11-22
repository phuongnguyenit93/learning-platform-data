# Thiết kế runner làm nóng dữ liệu trước khi công bố readiness trong Spring Boot

## 1. Mục tiêu và tình huống thực tế

Một Spring Boot application có thể tạo xong ApplicationContext và khởi động embedded web server nhưng **chưa có dữ liệu đủ điều kiện phục vụ request**. Ví dụ: service tính giá cần snapshot bảng giá đã xác minh; service routing cần bảng quy tắc; ứng dụng tra cứu sản phẩm cần nạp catalogue tại chỗ; hoặc bộ máy phân quyền cần một tập metadata bắt buộc.

Nếu hệ thống được công bố ready khi cache vẫn trống hoặc đang nạp dở, request đầu có thể nhận dữ liệu thiếu, trả kết quả sai hoặc bị chậm do mỗi request tự làm warm-up. Chỉ kiểm tra JVM còn sống, port HTTP đã mở hoặc Spring log **Started** là chưa đủ.

Spring Boot cung cấp **ApplicationRunner** và **CommandLineRunner** để thực thi công việc **sau khi ApplicationContext được refresh nhưng trước ApplicationReadyEvent**. Một runner chạy đồng bộ, hoàn tất đầy đủ việc nạp/kiểm tra/công bố dữ liệu rồi mới return sẽ hoạt động như một **startup gate**: Spring Boot chỉ chuyển readiness sang **ACCEPTING_TRAFFIC** sau khi tất cả runners chạy thành công.

Bài này thiết kế giải pháp trên **Spring Boot 3.5.x, Java 17+**, có Maven POM, code Java runnable, HTTP endpoint đọc cache, Actuator readiness, lỗi khởi động có chủ đích, phép thử curl/Kubernetes, failure policy và các bẫy concurrency.

**Kết quả mong muốn:** khi warming, trạng thái readiness là **REFUSING_TRAFFIC**; khi snapshot đã nhất quán và runner hoàn thành, Spring Boot phát ApplicationReadyEvent và đổi sang **ACCEPTING_TRAFFIC**. Nếu warm-up bắt buộc thất bại, startup phải thất bại có kiểm soát chứ không báo ready giả.

## 2. Sự khác biệt giữa Started, Live và Ready

Spring Boot công bố ba khái niệm dễ bị nhầm:

- **Context refreshed:** giai đoạn BeanFactory, auto-configuration, singleton initialization và embedded server đã hoàn thành refresh.
- **LivenessState.CORRECT:** ứng dụng không bị xem là hỏng về trạng thái nội tại sau refresh.
- **ReadinessState.ACCEPTING_TRAFFIC:** ứng dụng được coi là đủ điều kiện nhận traffic, sau khi các ApplicationRunner/CommandLineRunner hoàn tất.

Sơ đồ chuẩn theo Spring Boot 3.5:

~~~text
SpringApplication.run(args)
     |
     +--> Environment / ApplicationContext preparation
     |
     +--> ApplicationContext.refresh()
     |       Bean definitions, singleton beans, web server
     |
     +--> ApplicationStartedEvent
     |
     +--> AvailabilityChangeEvent(LivenessState.CORRECT)
     |       ReadinessState = REFUSING_TRAFFIC
     |
     +--> ApplicationRunner / CommandLineRunner
     |       - load bắt buộc
     |       - kiểm tra dữ liệu
     |       - publish snapshot
     |
     +--> ApplicationReadyEvent
     |
     +--> AvailabilityChangeEvent(
     |        ReadinessState.ACCEPTING_TRAFFIC)
     |
     +--> SpringApplication.run trả về thành công
~~~

Khi runner ném exception, SpringApplication xử lý **startup failure** và không phát mốc Ready thành công. Context có thể đã refresh nhưng quá trình startup tổng thể vẫn **chưa thành công**.

| Thời điểm | Liveness | Readiness | Có nên route traffic? |
| --- | --- | --- | --- |
| Trước refresh | BROKEN trong mô hình startup | REFUSING_TRAFFIC | Không |
| Sau refresh, trước runners | CORRECT | REFUSING_TRAFFIC | Không |
| Runner đang warm-up | CORRECT | REFUSING_TRAFFIC | Không |
| Mọi runner hoàn tất | CORRECT | ACCEPTING_TRAFFIC | Có, nếu probe/hạ tầng nhận ra |
| Runner throw | Startup failure | Không công bố Ready thành công | Không |
| Graceful shutdown | Có thể vẫn CORRECT trong lúc drain | REFUSING_TRAFFIC | Không nhận mới |

**Quan trọng:** readiness là trạng thái và cơ chế để hạ tầng **quyết định định tuyến**. Nó không phải firewall tự động chặn tất cả request trực tiếp vào IP/port. HTTP connector/probes cũng có thể tạm chưa phục vụ trong giai đoạn startup; việc curl không kết nối được trước Ready không tự chứng minh warm-up có lỗi.

## 3. Vì sao chọn ApplicationRunner thay vì @PostConstruct?

### @PostConstruct

Được gọi khi Spring đang khởi tạo một bean, tức vẫn nằm trong **refresh()**. Nó phù hợp với init nhẹ, local, không phụ thuộc vào việc toàn bộ ứng dụng đã hoàn tất cấu hình. Đưa I/O dài, truy vấn nhiều bảng hoặc retry network vào @PostConstruct sẽ làm bean creation chậm và lỗi dưới dạng BeanCreationException; nhiều dependencies có thể chưa sẵn.

### ApplicationRunner

Được Spring Boot gọi **sau refresh** và trước Ready. Có thể inject Repository, HTTP client, DataSource, Environment, cache service và dùng các beans đã cấu hình. Nó thích hợp cho tác vụ startup bắt buộc có điều kiện thành công/không thành công rõ ràng.

~~~java
@Bean
ApplicationRunner warmup(MyWarmupService service) {
    return args -> {
        service.loadAndValidateSynchronously();
    };
}
~~~

Đây là mảnh code minh họa, cần MyWarmupService và cấu hình Spring thực. Ý nghĩa: **run() chỉ return sau khi loadAndValidateSynchronously() kết thúc thành công**.

### Một số hooks khác

| Hook | Thời điểm/đặc trưng | Khuyến nghị |
| --- | --- | --- |
| Constructor | Trong tạo bean | Không làm I/O lâu |
| @PostConstruct | Khi bean init trong refresh | Init ngắn, không lạm dụng để warm-up nghiệp vụ |
| SmartInitializingSingleton | Khi các singleton non-lazy đã khởi tạo | Phù hợp wiring, không phải startup readiness gate dễ đọc nhất |
| ApplicationRunner | Sau Started, trước Ready | **Ưu tiên** cho required warm-up |
| CommandLineRunner | Cùng giai đoạn, dùng String args | Có thể dùng tương đương |
| @EventListener(ApplicationReadyEvent.class) | Khi Ready event đang được phát | Không thiết kế warm-up required dựa vào mốc này |
| @Scheduled | Thực thi theo lịch | Dùng cho refresh sau startup, không thay runner |
| @Async task do runner submit rồi return | Work có thể còn chạy sau khi runner xong | Nguy hiểm nếu readiness phụ thuộc task |

**Sự khác biệt thực tế:** Runner là công cụ chờ điều kiện đã thỏa mãn; không phải tự động là một worker pool, retry engine hoặc readiness probe.

## 4. Xác định hợp đồng dữ liệu trước khi lập trình

Không phải cache nào cũng cần chặn readiness.

### Nhóm Required

Thiếu dữ liệu sẽ khiến request **sai**, vi phạm invariant hoặc không thể phục vụ an toàn. Ví dụ: bảng giá hiệu lực, danh sách tenant/region mapping, policy kiểm soát truy cập hay schema version bắt buộc.

Hợp đồng hoàn tất cần quy định:

1. **Nguồn dữ liệu:** database, file versioned, remote API hoặc shared cache.
2. **Phạm vi:** tất cả records hay một tập keys bắt buộc.
3. **Consistency:** các records có cùng version/snapshot hay không.
4. **Validation:** không có khóa trùng, không thiếu field, version/checksum đúng.
5. **Deadline:** timeout riêng từng I/O và tổng thời gian có thể chờ.
6. **Failure:** fail startup thay vì quảng bá ready khi không đạt điều kiện.
7. **Publication:** snapshot chỉ hiển thị cho readers sau khi kiểm tra hoàn tất.

### Nhóm Best effort

Cache chỉ để tăng tốc; cache miss được xử lý bằng nguồn chính với timeout/fallback an toàn. Nếu warm-up lỗi, ứng dụng vẫn trả kết quả **đúng** nhưng có thể chậm hơn. Có thể log/metric rồi tiếp tục Ready theo chính sách được phê duyệt.

**Không được gọi một cache best effort chỉ vì muốn bỏ qua lỗi.** Nếu không có cache mà trả sai giá/thiếu quyền hoặc làm nghẽn toàn bộ nguồn backend, đó là vấn đề required hoặc cần một degraded-mode contract rõ ràng.

### Phải biết dataset rỗng có hợp lệ không

Trong bài ví dụ, hợp đồng là **đúng ba sản phẩm**, nên dữ liệu rỗng là lỗi. Với hệ thống thật, 0 rows có thể hợp lệ; trong trường hợp ấy hãy dùng cờ **initialized** hoặc metadata version tách khỏi **Map.isEmpty()**. Không dùng độ lớn map làm chuẩn ready cho mọi bài toán.

## 5. Thiết kế pipeline warm-up chuẩn

~~~text
ApplicationRunner.run()
      |
      +--> START: ghi thời điểm, deadline
      |
      +--> LOAD: đọc từ source với timeout
      |
      +--> VALIDATE: đếm records, kiểm tra khóa/giá/version
      |
      +--> BUILD: tạo một immutable snapshot riêng
      |
      +--> PUBLISH: atomic swap vào cache
      |
      +--> END: ghi duration/size rồi return
      |
      v
Boot hoàn tất runners
      |
      v
ApplicationReadyEvent
      |
      v
ReadinessState.ACCEPTING_TRAFFIC
~~~

Nếu LOAD/VALIDATE thất bại, **không publish snapshot nửa chừng**. Runner phải ném exception với thông điệp có hành động, cho phép SpringApplication kết thúc startup không thành công.

### Vì sao dùng immutable snapshot?

Sai lầm thường gặp:

~~~java
sharedCache.clear();
for (Product item : sourceItems) {
    sharedCache.put(item.sku(), item);
}
~~~

Đây là **mảnh phản ví dụ**, các biến/class chưa định nghĩa. Request đến giữa vòng lặp có thể thấy một phần dữ liệu; exception giữa chừng để lại cache chưa đủ.

Mẫu phù hợp hơn:

~~~java
Map<String, Product> next = loadAndValidate();
cacheSnapshot.set(Map.copyOf(next));
~~~

Đây là mảnh khái niệm, cần biến và method thật. Xây ở vùng riêng, tạo immutable Map rồi dùng **AtomicReference.set** để công bố **một reference hoàn chỉnh**. Nếu Product cũng là immutable record, consumers không có đường sửa snapshot nội bộ.

**Chú ý:** nếu có hai map liên hệ với nhau, hãy đóng cả hai trong một immutable object **CatalogSnapshot** và swap một reference; không publish mỗi map riêng để rồi readers thấy hai versions khác nhau.

## 6. Ví dụ Spring Boot 3.5 runnable trên Java 17+

Ví dụ tạo ba products trong một nguồn dữ liệu giả, có độ trễ 6 giây để người học quan sát readiness khi runner còn đang làm việc. Nạp xong, nó kiểm tra trùng SKU, thiếu tên và giá âm, rồi publish snapshot một lần.

Ứng dụng có:

- **Spring Web** để kiểm tra GET /catalog/P101.
- **Actuator** để kiểm tra GET /actuator/health/readiness hoặc /readyz.
- Cờ **demo.warmup.fail=true** để cố tình gây lỗi required startup.
- Event observer cho **ApplicationReadyEvent** và **AvailabilityChangeEvent**.
- Không cần database/mạng ngoài; sau đó có thể thay source bằng JDBC/HTTP.

### 6.1. Thư mục

~~~text
readiness-warmup/
  pom.xml
  src/main/
    java/com/example/warmup/ReadinessWarmupApplication.java
    resources/application.properties
~~~

Có thể tạo Maven Wrapper từ Spring Initializr; ở đây lệnh dùng Maven cài sẵn.

### 6.2. pom.xml đầy đủ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>readiness-warmup</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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

POM dùng starter-parent để quản lý compatible Spring Framework/Jackson/Tomcat versions; plugin tạo executable JAR. Không cần Spring Security cho demo trên localhost; trong production cần bảo vệ endpoints theo kiến trúc.

### 6.3. application.properties

~~~properties
spring.application.name=readiness-warmup
server.port=8080

# Bật probe groups cả khi chạy trên máy local:
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info

# /livez và /readyz ngay trên application server port:
management.endpoint.health.probes.add-additional-paths=true

# Property riêng của demo:
demo.warmup.fail=false
~~~

Đừng nhầm demo.warmup.fail với property tiêu chuẩn của Spring Boot; nó chỉ được code ví dụ đọc.

### 6.4. Java file hoàn chỉnh

Đặt tại **src/main/java/com/example/warmup/ReadinessWarmupApplication.java**:

~~~java
package com.example.warmup;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ReadinessWarmupApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReadinessWarmupApplication.class, args);
    }

    public record Product(String sku, String name, long price) {
    }

    @Component
    static class CatalogSource {

        List<Product> load() throws InterruptedException {
            // Giả lập thao tác I/O. Client thật phải có timeout.
            TimeUnit.SECONDS.sleep(6);

            return List.of(
                    new Product("P101", "Sổ tay", 45000),
                    new Product("P102", "Bút chì", 12000),
                    new Product("P103", "Kẹp giấy", 18000));
        }
    }

    @Component
    static class CatalogCache {

        private final AtomicReference<Map<String, Product>> current =
                new AtomicReference<>(Map.of());

        void publish(Map<String, Product> data) {
            current.set(Map.copyOf(data));
        }

        boolean isLoaded() {
            return !current.get().isEmpty();
        }

        Product find(String sku) {
            return current.get().get(sku);
        }
    }

    @Bean
    ApplicationRunner warmupRunner(
            CatalogSource source,
            CatalogCache cache,
            ApplicationAvailability availability,
            Environment environment) {

        return args -> {
            System.out.println("WARMUP_BEGIN readiness="
                    + availability.getReadinessState());

            boolean forceFailure = environment.getProperty(
                    "demo.warmup.fail", Boolean.class, false);

            if (forceFailure) {
                System.out.println("WARMUP_FORCED_FAILURE");
                throw new IllegalStateException(
                        "Required catalogue warm-up failed");
            }

            Map<String, Product> next = new LinkedHashMap<>();

            try {
                for (Product product : source.load()) {

                    if (product.sku() == null
                            || product.sku().isBlank()
                            || product.name() == null
                            || product.name().isBlank()
                            || product.price() < 0) {
                        throw new IllegalStateException(
                                "Invalid product in source");
                    }

                    Product previous =
                            next.putIfAbsent(product.sku(), product);

                    if (previous != null) {
                        throw new IllegalStateException(
                                "Duplicate SKU: " + product.sku());
                    }
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Warm-up interrupted", ex);
            }

            if (next.size() != 3) {
                throw new IllegalStateException(
                        "Incomplete catalogue: expected 3");
            }

            cache.publish(next);
            System.out.println("WARMUP_DONE count=" + next.size());
        };
    }

    @RestController
    static class CatalogController {

        private final CatalogCache cache;

        CatalogController(CatalogCache cache) {
            this.cache = cache;
        }

        @GetMapping("/catalog/{sku}")
        public ResponseEntity<?> find(@PathVariable String sku) {

            // Bảo vệ nếu có request bypass readiness routing.
            if (!cache.isLoaded()) {
                return ResponseEntity
                        .status(HttpStatus.SERVICE_UNAVAILABLE)
                        .body(Map.of("status", "WARMING_UP"));
            }

            Product product = cache.find(sku);

            if (product == null) {
                return ResponseEntity.notFound().build();
            }

            return ResponseEntity.ok(product);
        }
    }

    @Component
    static class ReadyObserver {

        @EventListener
        public void onReady(ApplicationReadyEvent event) {
            System.out.println("EVENT_APPLICATION_READY");
        }

        @EventListener
        public void onAvailability(AvailabilityChangeEvent<?> event) {
            if (event.getState()
                    == ReadinessState.ACCEPTING_TRAFFIC) {
                System.out.println("READINESS_ACCEPTING_TRAFFIC");
            }
        }
    }
}
~~~

### 6.5. Giải thích code và QA biên dịch

- Public class **ReadinessWarmupApplication** khớp tên file/package.
- Java 17 hỗ trợ record Product; nested record là static, có public accessors.
- **@SpringBootApplication** kích hoạt auto-configuration và component scanning.
- Nested static classes có @Component/@RestController được Spring quản lý.
- ApplicationRunner là functional interface; lambda được Spring Boot gọi sau refresh.
- **CatalogSource.load** dùng sleep 6 giây giả lập I/O, ném InterruptedException hợp lệ.
- **Environment.getProperty** với Boolean.class và default false sử dụng conversion service của Spring.
- **LinkedHashMap.putIfAbsent** cho phép phát hiện duplicate SKU trước publication.
- **Map.copyOf** tạo snapshot không thể sửa qua Map interface; Product là immutable record.
- **AtomicReference.set** là một lần publish, tránh consumers thấy map được điền dở.
- **ResponseEntity<?>** hợp lệ cho 503 body Map, 404 no body hoặc 200 Product.
- **AvailabilityChangeEvent<?>** lắng nghe các availability changes rồi lọc đúng ReadinessState.ACCEPTING_TRAFFIC.
- @EventListener(ApplicationReadyEvent) chỉ in marker, không dùng để nạp dữ liệu bắt buộc.
- Chương trình không dùng API Java mới hơn 17; dependencies được khai báo trong POM.

Trong ứng dụng thật, thay sleep bằng client có **connect/read/query timeout**, không chỉ đo duration sau khi một blocking call đã hoàn tất. Tất cả stdout markers ở ví dụ là từ System.out, còn Spring/Tomcat/Maven có thêm log riêng.

### 6.6. Build và chạy

~~~bash
java -version
mvn -version
mvn clean package
java -jar target/readiness-warmup-0.0.1-SNAPSHOT.jar
~~~

Nếu có Maven Wrapper từ Initializr:

~~~bash
# Linux/macOS:
./mvnw clean package

# Windows PowerShell/cmd:
# .\mvnw.cmd clean package
~~~

Với artifactId/version của POM, JAR đúng là **target/readiness-warmup-0.0.1-SNAPSHOT.jar**.

### 6.7. Output mong đợi

Các dòng **do chính code ví dụ in**, không gồm Boot/Tomcat logs:

~~~text
WARMUP_BEGIN readiness=REFUSING_TRAFFIC
WARMUP_DONE count=3
EVENT_APPLICATION_READY
READINESS_ACCEPTING_TRAFFIC
~~~

Thời gian giữa BEGIN và DONE khoảng 6 giây cộng overhead. **Log Started** của Spring Boot có thể xuất hiện trước WARMUP_BEGIN hoặc khi quá trình runner chưa xong; đó không phải Ready event.

### 6.8. Kiểm tra sau khi hoàn tất

~~~bash
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/catalog/P101
curl -i http://localhost:8080/catalog/UNKNOWN
~~~

Sau startup bình thường, readiness thường có HTTP 200 và nội dung:

~~~json
{"status":"UP"}
~~~

Sản phẩm P101:

~~~json
{"sku":"P101","name":"Sổ tay","price":45000}
~~~

UNKNOWN trả 404. JSON field order và Unicode escaping tùy Jackson. Những điều nên assertion là **status và giá trị dữ liệu**, không phải headers/JSON byte-for-byte.

### 6.9. Quan sát trong lúc runner chưa hoàn tất

Trong terminal Linux/macOS A:

~~~bash
java -jar target/readiness-warmup-0.0.1-SNAPSHOT.jar &
APP_PID=$!
echo "$APP_PID"
~~~

Trong terminal B:

~~~bash
for i in 1 2 3 4 5 6 7 8; do
  curl -s -o /dev/null -w "HTTP=%{http_code}\n" \
    http://localhost:8080/actuator/health/readiness
  sleep 1
done
~~~

**Không hardcode kết quả mỗi giây.** Trước khi connector sẵn, curl có thể hiển thị 000. Khi connector cho phép truy vấn probe nhưng readiness còn REFUSING_TRAFFIC, health group có thể báo OUT_OF_SERVICE/503. Sau Ready thành công, thường là UP/200.

Spring Boot Reference mô tả availability state và việc connector có thể không sẵn trong một số phase; vì vậy hãy đối chiếu **event markers và probe**, không kết luận từ một status mạng đơn lẻ. Việc direct HTTP request bypass Kubernetes Service có thể khác cách routing qua readinessProbe; CatalogController có guard 503 riêng nếu cache chưa loaded.

### 6.10. Mô phỏng required warm-up failure

Dừng tiến trình, rồi:

~~~bash
java -jar target/readiness-warmup-0.0.1-SNAPSHOT.jar --demo.warmup.fail=true
~~~

Những marker do code in:

~~~text
WARMUP_BEGIN readiness=REFUSING_TRAFFIC
WARMUP_FORCED_FAILURE
~~~

Đường lỗi này không in:

~~~text
WARMUP_DONE count=3
EVENT_APPLICATION_READY
READINESS_ACCEPTING_TRAFFIC
~~~

Boot sẽ ghi exception startup và đóng context theo xử lý lỗi. Khi runner ném IllegalStateException, **không công bố Ready thành công**. Không nên assertion mã exit/log wrapper chính xác ở mọi shell và runtime.

## 7. Chuẩn hóa timeout và retry cho production

Giả lập TimeUnit.SECONDS.sleep giúp dễ quan sát, nhưng **không đặt thời hạn cho database/network thật**. Một runner production cần các ngân sách:

| Ngân sách | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Connect timeout | 2s | Không chờ tạo kết nối vô hạn |
| Query/response timeout | 5s | Giới hạn một lần gọi DB/API |
| Retry count | 3 attempts | Chỉ thử lại lỗi transient |
| Backoff | 1s, 2s + jitter | Tránh đồng loạt retry |
| Overall warm-up deadline | 20s | Không chờ quá lâu trước Ready |
| Kubernetes startup budget | Tùy service, lớn hơn startup thật | Tránh kubelet restart quá sớm |

**Những số trên chỉ minh họa**, không phải defaults của Spring Boot hoặc một HTTP client cụ thể.

Tính tổng: ba attempts mỗi lần tối đa 5s và hai backoffs tổng 3s có thể tốn khoảng **18s** cộng validation, connection acquisition và overhead. Phải tính theo thư viện thực tế.

### Mẫu kiểm soát deadline

~~~java
// Pseudocode: source.fetch, validate, isTransient, publish
// và các types là API do ứng dụng cung cấp.
long deadline = System.nanoTime() + budget.toNanos();

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    long remaining = deadline - System.nanoTime();
    if (remaining <= 0) {
        throw new IllegalStateException("Warm-up deadline exceeded");
    }

    try {
        Dataset dataset = source.fetch(
                Duration.ofNanos(remaining));
        validate(dataset);
        publish(dataset);
        break;
    } catch (RemoteDataException ex) {
        if (attempt == maxAttempts || !isTransient(ex)) {
            throw ex;
        }
        // Bounded backoff với remaining deadline.
    }
}
~~~

Đây **không phải file chạy độc lập**: các biến, class và API ứng dụng chỉ được minh họa. Nó cho thấy cấu trúc cần có. Tránh viết stopwatch rồi gọi một operation không có per-call timeout; deadline sau khi operation trở về không thể cứu thread đang block vô hạn.

Không retry lỗi cố định như invalid schema, permission denied hay thiếu config bắt buộc. Không retry vô hạn vì có thể khiến startup probe thất bại mãi và làm quá tải downstream.

## 8. Những bẫy @Async, CompletableFuture và virtual threads

Mẫu sai:

~~~java
@Bean
ApplicationRunner brokenWarmup(AsyncCatalogLoader loader) {
    return args -> {
        loader.loadAsync(); // Không chờ.
    };
}
~~~

Mảnh này không độc lập; giả định AsyncCatalogLoader bean. Runner return ngay nên Boot có thể tiếp tục ApplicationReadyEvent trong khi async task chưa làm xong. Một CompletableFuture bị lỗi ở background không tự hủy startup đã được báo ready.

Nếu cần song song hóa các phần nạp:

~~~java
CompletableFuture<PartA> left = service.loadPartA();
CompletableFuture<PartB> right = service.loadPartB();

CompletableFuture.allOf(left, right).join();
PartA a = left.join();
PartB b = right.join();
validateThenPublish(a, b);
~~~

Đây là mảnh khái niệm, cần service, types và imports. **Join không tự có timeout**; cần timeout/cancellation cho required tasks. Khi dùng Spring @Async, nhớ bật @EnableAsync và gọi qua Spring bean proxy; self-invocation có thể không được intercept.

**Virtual threads trên Java 21+ không thay đổi lifecycle readiness.** Dù bật spring.threads.virtual.enabled, Boot vẫn chỉ chờ runner **run() hoàn thành**, không tự chờ các threads mà ứng dụng tạo. Cần await và propagate lỗi như bình thường.

## 9. Nhiều runners, @Order và dependency ordering

Ứng dụng có thể có Runner A kiểm tra schema, Runner B nạp policy, Runner C warm-up cache. Spring Boot hỗ trợ **Ordered** hoặc **@Order** để chọn thứ tự khi có nhiều ApplicationRunner/CommandLineRunner beans.

~~~java
@Component
@Order(10)
class SchemaCheckRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("schema-check");
    }
}
~~~

Mảnh class minh họa cần imports và đặt trong project. Nó chỉ in marker, **không thực sự kiểm tra schema**. Khi nghiệp vụ có dependency phức tạp, thường tốt hơn gom thành **một coordinator runner** gọi các bước theo thứ tự explicit để tránh một loạt @Order rải rác.

Nếu một runner throw, các runners sau có thể chưa chạy và startup thất bại. Không viết logic phụ thuộc vào side effect của runner khác nếu không có thứ tự và transaction/recovery policy rõ ràng.

### Với Flyway/Liquibase

Đừng tự viết migration trong runner chỉ vì muốn chạy trước Ready. Spring Boot có tích hợp schema migration phù hợp với auto-configuration; runner có thể kiểm tra hậu điều kiện và làm warm-up dữ liệu sau migration. Nếu runner seed dữ liệu có side effects, cần idempotency và transaction.

## 10. Readiness sau startup: cache hỏng thì làm gì?

ApplicationRunner chỉ chạy khi startup. Nếu cache mất dữ liệu, hết hạn, schema đổi hoặc remote source lỗi **sau khi đã Ready**, Boot không tự gọi runner lại.

Có thể thiết kế refresh task định kỳ hoặc theo event, kết hợp:

1. Tạo snapshot phiên bản mới ngoài vùng đang công bố.
2. Validate đầy đủ.
3. Atomic swap nếu thành công.
4. Nếu refresh thất bại nhưng snapshot cũ vẫn hợp lệ, giữ snapshot cũ và cảnh báo.
5. Nếu snapshot cũ không còn an toàn để phục vụ, chuyển instance sang **REFUSING_TRAFFIC** theo chính sách rõ ràng.
6. Khi khôi phục thành công, xem xét publish ACCEPTING_TRAFFIC lại.

Spring Boot có API:

~~~java
AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.REFUSING_TRAFFIC);
~~~

Đây là mảnh minh họa; phải có ApplicationContext và imports. Không tự publish ACCEPTING_TRAFFIC **trước khi runner required hoàn tất** để "làm xanh" readiness.

Nếu cache hoàn toàn optional, đừng đưa mọi cache miss thành readiness failure. Nếu một external dependency dùng chung thất bại, tự đưa mọi Pod về unready có thể tạo outage toàn cluster. Thiết kế readiness dựa trên **khả năng phục vụ thật** và có circuit breaker/fallback.

## 11. Kubernetes readinessProbe, livenessProbe và startupProbe

Với Actuator cấu hình như mục 6, có thể dùng **/readyz** và **/livez** ngay trên main port.

Fragment PodSpec:

~~~yaml
spec:
  containers:
    - name: catalog
      image: registry.example.com/readiness-warmup:1.0
      ports:
        - name: http
          containerPort: 8080
      readinessProbe:
        httpGet:
          path: /readyz
          port: http
        periodSeconds: 2
        timeoutSeconds: 1
        failureThreshold: 2
      livenessProbe:
        httpGet:
          path: /livez
          port: http
        periodSeconds: 10
        timeoutSeconds: 2
        failureThreshold: 3
      startupProbe:
        httpGet:
          path: /livez
          port: http
        periodSeconds: 5
        failureThreshold: 12
~~~

Đây là fragment, không phải Deployment đầy đủ. Image phải thay bằng artifact thật. **startupProbe** giúp ngăn liveness restart một ứng dụng mất nhiều thời gian chuẩn bị, còn **readinessProbe** điều phối thời điểm instance được nhận traffic.

- **ReadinessProbe:** thất bại trong warm-up là bình thường; Kubernetes không route traffic vào Pod chưa ready.
- **LivenessProbe:** không nên phụ thuộc trực tiếp vào mọi external DB/API vì có thể tạo restart storm.
- **StartupProbe:** hữu ích khi khởi động chậm; nếu được cấu hình, liveness/readiness checks được trì hoãn cho tới khi startup probe thành công theo Kubernetes semantics.
- **Actuator management port riêng:** có thể báo health tốt dù main connector lỗi. Vì vậy Spring Boot khuyến nghị cân nhắc các probe paths trên **main server port**.

**Không mặc định đọc 503 từ chính Pod ở mọi thời điểm:** khi web connector chưa mở hoặc ingress không có ready endpoints, client có thể gặp lỗi kết nối hoặc mã lỗi từ load balancer thay vì Spring Actuator.

### Startup budget

Nếu runner thường cần 25s, startupProbe với periodSeconds=5 và failureThreshold=12 có khoảng 60s ngân sách xấp xỉ trước khi kubelet kết luận thất bại, còn chịu timeout, scheduling và startup thực tế. Chọn budget dựa trên cold starts và p95/p99, không phải đo một lần trên máy nhanh rồi kết luận.

## 12. Warm-up ở nhiều replicas và khi rolling deploy

Một rủi ro thường bị bỏ qua: **thundering herd**.

Nếu mỗi Pod tải một dataset lớn từ DB, việc tăng 1 lên 30 replicas có thể làm 30 lần cùng truy vấn nặng, chiếm connection pool, tăng latency và khiến tất cả startup cùng chậm.

Cần cân nhắc:

- Tăng replica từng đợt, có readiness gating và rollout budgets.
- Rate limit hoặc semaphore tại downstream thực sự giới hạn.
- Bounded retry, jitter và backoff.
- Snapshot/artifact precomputed nếu dữ liệu phù hợp để chia sẻ.
- Dữ liệu có version/checksum để không ghi đè nhầm bản cũ.
- Giới hạn memory peak khi tạo immutable snapshot và giữ bản cũ.
- Cache warm-up có phải diễn ra trên mọi replica hay chỉ cần một shared cache.
- Timeout của ingress, Pod startup và deployment progress deadline.

**Một startup nhanh hơn không chắc service tốt hơn** nếu nó chỉ đẩy chi phí sang request đầu hoặc làm source DB nghẽn trong thời gian rollout. Đo cả **time-to-ready** và **first-request latency**.

## 13. Transaction, side effects và idempotency

Warm-up đơn thuần đọc và tạo immutable cache thường dễ restart. Nhưng runner có thể đồng thời **seed DB, ghi message hoặc tạo tài nguyên**. Khi startup lỗi rồi Kubernetes restart:

- Dữ liệu đã commit có thể vẫn tồn tại.
- Một transaction khác có thể rollback nhưng external API đã có side effect.
- Chạy lại runner có thể tạo duplicate rows/messages.
- Tác vụ chạy trên nhiều replicas có thể thực hiện cùng một việc nhiều lần.

Thiết kế:

1. **Business key** ổn định và unique constraint.
2. Insert-if-absent/upsert có semantics rõ.
3. Transaction boundary trong Spring service proxy/TransactionTemplate hợp lệ.
4. Distributed lock/lease nếu thực sự chỉ một replica được phép thực thi.
5. Retry không gây duplicate side effects; outbox khi liên quan DB + message broker.
6. Timeout cho DB/network và chính sách recovery.

**ApplicationRunner throw không tự rollback mọi tác động đã commit**. Spring Boot startup failure chỉ xử lý lifecycle/container, không có quyền undo một HTTP call hoặc email đã gửi.

## 14. Kiểm thử đầy đủ

### Test logic cache

- Source trả đúng ba records, cache giữ đủ dữ liệu và API trả đúng.
- SKU trùng, SKU trống, tên trống, giá âm → validation fail.
- Trả thiếu sản phẩm → fail thay vì publish.
- Source ném InterruptedException → restore flag và fail.
- Cache snapshot đang dùng không bị sửa khi build snapshot tiếp theo.
- Read đồng thời khi publish → không nhìn thấy dữ liệu nửa chừng.
- Nếu dataset rỗng là hợp lệ trong hệ thống khác, dùng explicit initialized state.

### Test startup lifecycle

- ApplicationStartedEvent được quan sát **trước khi runner bắt đầu**.
- ReadinessState vẫn REFUSING_TRAFFIC trong required warm-up.
- Runner thành công rồi ApplicationReadyEvent/ACCEPTING_TRAFFIC.
- Runner ném lỗi → không phát Ready bình thường.
- Không có Promise/Future required chạy trôi sau khi runner return.
- ReadinessProbe không được coi là UP trong khi required data chưa sẵn.

### Test tích hợp/kubernetes

- StartupProbe đủ budget khi source chậm.
- ReadinessProbe /readyz chuyển UP sau warm-up.
- Đường trực tiếp bypass readiness không trả sai business data.
- Khi pod scale down, shutdown và request in-flight được xử lý theo lifecycle riêng.
- Nhiều pods cùng start không làm DB quá tải.
- Retry source khi timeout không gây thác requests.
- Warm-up ở production không đưa secrets/payload lớn vào log.

Với @SpringBootTest cần nhớ context caching: không mặc định runner được chạy lại cho mỗi test method. Với startup-failure scenarios, ưu tiên test tạo context mới hoặc chạy process tích hợp có kiểm soát.

## 15. Quan sát và đo chất lượng warm-up

Nên ghi:

| Thông tin | Ý nghĩa |
| --- | --- |
| warmup.begin timestamp | Mốc bắt đầu startup task |
| warmup.duration | Thời gian đến snapshot published |
| warmup.records.loaded | Số records đã nạp |
| warmup.data.version | Version/checksum của snapshot |
| warmup.validation.failure | Phân biệt data không hợp lệ |
| warmup.retry.attempts | Chỉ báo network/source bất ổn |
| application.ready time | Mốc kết thúc startup thực |
| cache.hit/miss sau Ready | Warm-up có lợi ích thực tế không |
| pod readiness timeline | Khi nào hạ tầng bắt đầu route |
| memory/GC trong warm-up | Chi phí nạp và copy snapshot |

Log ví dụ thiết kế:

~~~text
warmup.start source=catalog required=true
warmup.load.complete records=3 elapsedMs=6020
warmup.validate.complete version=v42
warmup.publish.complete count=3
readiness=ACCEPTING_TRAFFIC
~~~

Đây là **mẫu log minh họa**, không phải output nguyên văn của demo. Dùng số đo và version thật khi triển khai. Không log mật khẩu, tokens hay dữ liệu nhạy cảm của records.

## 16. Các lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân | Khuyến nghị |
| --- | --- | --- |
| Spring log Started nhưng cache chưa xong | Started trước runners | Xem ApplicationReadyEvent/ReadinessState |
| App báo Ready khi Future vẫn chạy | Runner return quá sớm | Await required tasks + propagate failure |
| Warm-up lỗi nhưng Pod vẫn ready | Catch-all bỏ qua lỗi | Required: throw/fail startup |
| Map chỉ có một nửa records | Publish trong lúc load | Build offline, validate, atomic swap |
| 404 cho SKU tồn tại | Source thiếu/invalid data | Kiểm tra completeness trước publication |
| Pod bị kill trước warm-up | Liveness/startupProbe budget thiếu | Cấu hình startupProbe hợp lý |
| Probe không kết nối được khi vừa start | HTTP connector chưa sẵn | Phân biệt network failure và readiness state |
| Liveness phụ thuộc DB shared | DB outage gây restart hàng loạt | Dùng liveness nội tại, readiness có cân nhắc |
| Runner chờ vô hạn | Remote client không có timeout | Per-call timeout và overall deadline |
| Hàng chục Pod warm-up đồng thời gây nghẽn DB | Thundering herd | Rate limit, precompute, stagger rollout |
| Dữ liệu sau Ready lỗi thời | Runner chỉ chạy một lần | Refresh policy + atomic swap |
| Management probe UP nhưng app không phục vụ | Hai connectors riêng | Main-port /readyz và end-to-end checks |
| Trạng thái cache rỗng hợp lệ bị coi lỗi | !map.isEmpty() dùng sai contract | Explicit initialized flag |
| @PostConstruct gọi API ngoài chậm | I/O trong refresh | Chuyển sang runner với deadline |
| Runner seed dữ liệu trùng sau restart | Side effect không idempotent | Unique keys, transaction/outbox |
| @Order không đủ biểu diễn dependency | Thứ tự runners rải rác | Coordinator và dependencies rõ |

## 17. Bài tập tự kiểm tra

**1.** ApplicationRunner chạy trước hay sau ApplicationStartedEvent? Trước hay sau ApplicationReadyEvent?

**2.** Khi runner vẫn đang warm-up, LivenessState và ReadinessState thường là gì?

**3.** Một runner chỉ gọi asyncLoader.load() rồi return. Có bảo đảm warm-up xong trước Ready không?

**4.** Vì sao @PostConstruct kém phù hợp hơn runner cho việc nạp nhiều nguồn dữ liệu phụ thuộc các Spring-managed services?

**5.** Vì sao không nên viết trực tiếp từng record vào shared HashMap trong lúc warm-up?

**6.** Map.copyOf + AtomicReference.set bảo vệ điều gì? Có tự làm các Product mutable trở thành immutable không?

**7.** Nếu source trả hai records thay vì ba, demo sẽ ra Ready hay fail startup?

**8.** Nếu một cache rỗng là hợp lệ, tại sao kiểm tra map.isEmpty() không đúng?

**9.** Vì sao chỉ có stopwatch không đủ giới hạn một JDBC/HTTP call bị treo?

**10.** ReadinessProbe khác startupProbe và livenessProbe thế nào?

**11.** Nếu management port khác main port, vì sao probe UP chưa chứng minh request tới main server thành công?

**12.** Nếu runner seed dữ liệu rồi throw, dữ liệu đã commit có tự rollback không?

**13.** Tại sao warm-up 30 pods có thể chậm hơn warm-up 1 pod?

**14.** Sau khi đã Ready, cache bị hỏng. Runner có tự chạy lại không, và cách quản lý readiness phù hợp?

### Gợi ý đáp án

1. Runner sau Started, trước Ready.
2. Liveness CORRECT và readiness REFUSING_TRAFFIC.
3. Không; Boot chờ runner return, không đợi Future một cách tự động.
4. @PostConstruct trong refresh, dependencies/lifecycle chưa hoàn chỉnh như sau refresh.
5. Reader có thể thấy partial dataset và cache bị hỏng nếu exception giữa chừng.
6. Công bố một immutable snapshot atomically; values cũng cần immutable riêng.
7. Throw IllegalStateException, không công bố Ready thành công.
8. Cần initialized state/version độc lập với số lượng records.
9. Operation phải có timeout/cancellation ngay tại thư viện I/O.
10. Readiness route traffic; startupProbe chờ đủ thời gian khởi động; liveness phục vụ quyết định restart.
11. Hai connectors có thể hỏng độc lập, cần main-port probes/end-to-end.
12. Không; cần transaction, idempotency và recovery.
13. Tài nguyên DB/API và bandwidth bị cạnh tranh, tạo thundering herd.
14. Không; cần runtime refresh và tùy severity publish REFUSING_TRAFFIC hoặc dùng fallback.

## 18. Checklist giao bài và vận hành

- [ ] Data required hay best effort được định nghĩa rõ.
- [ ] Điều kiện hoàn tất có validation: keys, version, completeness.
- [ ] Runner thực thi sau context refresh và trước Ready.
- [ ] Required work hoàn tất **trước khi runner return**.
- [ ] Source có network/query timeout hữu hạn.
- [ ] Retry có giới hạn và backoff/jitter.
- [ ] Snapshot immutable, publish một lần sau validation.
- [ ] Không có partial data exposure.
- [ ] Required fail thì throw, không catch rồi return.
- [ ] Không ép ACCEPTING_TRAFFIC sớm.
- [ ] Có readinessProbe hợp lệ và phù hợp main server port.
- [ ] Có startupProbe nếu liveness có thể kill app đang khởi động.
- [ ] Tránh dùng liveness check gọi DB/API shared liên tục.
- [ ] Có xử lý runtime cache loss và recovery.
- [ ] Có metrics time-to-ready, duration, retries, loaded records.
- [ ] Có điều tiết load khi nhiều replicas khởi động.
- [ ] Side effects idempotent và transaction rõ.
- [ ] Có test happy, invalid data, network timeout, concurrency và restart.
- [ ] Không đưa secrets/PII vào log.

## 19. Kết luận và tài liệu chính thức

**Một runner làm nóng dữ liệu đúng chức năng phải thực sự là cổng điều kiện trước readiness:**

~~~text
Spring context refreshed
         |
         v
ApplicationStartedEvent
         |
         v
ApplicationRunner
    load + timeout
    validate + completeness
    build immutable snapshot
    atomic publish
         |
         +--> SUCCESS --> return
         |                  |
         |                  v
         |          ApplicationReadyEvent
         |                  |
         |                  v
         |          ReadinessState.ACCEPTING_TRAFFIC
         |
         +--> FAILURE --> throw
                            |
                            v
                       Startup failure
                       KHÔNG Ready thành công
~~~

Ba điểm cần nhớ:

1. **Runner chạy đồng bộ hoặc await toàn bộ required tasks trước khi return.**
2. **Kiểm tra toàn vẹn dữ liệu rồi atomic publish**, tránh consumers nhìn thấy cache chưa đủ.
3. **Readiness và liveness có ý nghĩa khác nhau**; kết hợp Actuator probes và Kubernetes routing để traffic chỉ tới Pod đủ điều kiện.

Nguồn tham khảo đúng nhánh Spring Boot 3.5:

1. Spring Boot 3.5 Reference — SpringApplication, Application Events and Listeners, Application Availability, ApplicationRunner: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
2. Spring Boot 3.5 Reference — Actuator, Kubernetes Liveness and Readiness Probes, Application Lifecycle: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
3. Spring Boot 3.5 API — ApplicationAvailability: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html
4. Spring Boot 3.5 API — ReadinessState: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ReadinessState.html
5. Spring Boot 3.5 API — ApplicationRunner: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ApplicationRunner.html
6. Spring Framework Reference — Bean lifecycle callbacks: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
7. Kubernetes — Liveness, Readiness and Startup Probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/

**Phiên bản ví dụ:** Java 17+, Spring Boot 3.5.16, Spring MVC và Actuator. Thời gian sleep 6 giây và ba sản phẩm là dữ liệu giả lập để quan sát readiness; khi dùng JDBC/Redis/HTTP thật cần bổ sung timeout client, transaction/snapshot consistency, data security và cơ chế khôi phục theo nghiệp vụ.