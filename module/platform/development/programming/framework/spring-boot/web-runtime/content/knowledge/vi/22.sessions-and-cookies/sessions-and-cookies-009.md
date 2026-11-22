# Tuần tự hóa dữ liệu phiên và rủi ro khi thay phiên bản ứng dụng

## 1. Session và cookie: dữ liệu nào thật sự được lưu ở đâu?

Trong ứng dụng **Spring Boot web-runtime**, server có thể dùng session để giữ trạng thái giữa nhiều HTTP request: giỏ hàng tạm, bước wizard, thông tin xác thực, một số lựa chọn giao diện. Browser thường chỉ giữ **cookie chứa session ID** và gửi ID đó về server ở các request tiếp theo.

Cơ chế khái niệm:

```text
Browser                                       Spring Boot
   │
   ├── POST /cart/items?sku=BOOK-1 ──────────►  @Controller
   │                                              │
   │                                              ▼
   │                                    HttpSession / WebSession
   │                                              │
   │                                   cart = CartSnapshot(...)
   │                                              │
   │                                   Session store / repository
   │
   ◄── Set-Cookie: <session-id> ────────────────┤
   │
   ├── GET /cart + Cookie: <session-id> ───────►  Lookup theo session ID
   │                                              │
   │                                       Đọc session attributes
   │                                              │
   ◄── JSON/HTML response ───────────────────────┤
```

**Cookie thường không chứa toàn bộ Java object của session.** Nó mang một ID/opaque token để server tìm lại dữ liệu (cookie name có thể là `JSESSIONID`, `SESSION` hoặc tên tùy chỉnh). Không coi cookie là bản sao giỏ hàng hoặc đối tượng `SecurityContext`. Nếu ứng dụng cố ý triển khai client-side session khác mô hình trên, cách quản lý, mã hóa, ký và giới hạn dung lượng sẽ khác.

**Tuần tự hóa (serialization)** là chuyển object/state thành định dạng lưu được (byte stream, JSON, v.v.); **giải tuần tự hóa (deserialization)** là dựng lại object/state từ định dạng đã lưu. Nhu cầu này đặc biệt quan trọng khi session nằm trong Redis, JDBC hoặc được container phân phối/khôi phục.

Câu hỏi của bài: *Nếu phiên bản V1 lưu object A, rồi một request tới phiên bản V2 đọc cùng session, điều gì có thể hỏng?* Ngoài logout, lỗi có thể xuất hiện ở deserialize, cấu trúc dữ liệu, ngữ nghĩa bảo mật hoặc xử lý giỏ hàng, ngay cả khi cookie vẫn còn hợp lệ.

## 2. Khi nào dữ liệu session thực sự được serialize?

Không phải cứ gọi `session.setAttribute(...)` là JVM ngay lập tức serialize object.

| Kiểu lưu session | Lưu ở đâu | Serialization và rủi ro version |
|---|---|---|
| **Servlet container in-memory** (một instance) | Map/object trong RAM của tiến trình | Thường lưu object trực tiếp; có thể không serialize mỗi request. Restart thường làm mất session nếu không cấu hình persistence đặc biệt |
| **Container session replication/persistence** | Cluster hoặc storage do container quản lý | Có thể serialize theo cơ chế riêng của Tomcat/Jetty/deployment; yêu cầu thuộc tính tương thích |
| **Spring Session Redis** | Redis, nhiều instance cùng đọc | Spring Session thường serialize **session attributes**; mặc định dùng JDK serialization theo tài liệu Spring Session 3.x |
| **Spring Session JDBC** | Bảng `SPRING_SESSION` / `SPRING_SESSION_ATTRIBUTES` | Mặc định giá trị attribute thành byte[] bằng JDK serialization; có thể custom converter/schema |
| **Spring WebFlux in-memory WebSession** | In-memory store reactive trong instance | Không mặc nhiên phải đi qua Java serialization mỗi request; reboot/multi-instance là vấn đề khác |
| **Spring Session reactive + Redis** | Redis với `WebSession` | Có vấn đề format và compatibility tương tự khi lưu attribute chung |

Ví dụ bạn chạy một Spring Boot MVC chỉ có `spring-boot-starter-web` và Tomcat nhúng. `HttpSession.setAttribute("cart", object)` có thể hoạt động dù `object` không implement `Serializable` vì object chỉ ở RAM. Nhưng khi chuyển sang Redis/JDBC hoặc cơ chế replication, lỗi `NotSerializableException` hay lỗi đọc object phiên bản khác có thể xuất hiện. Đó là lý do cần **test cấu hình session store thật**, không chỉ test ứng dụng local.

**Cookie hợp lệ ≠ session có thể đọc:** Redis vẫn có key và TTL, nhưng V2 không deserialize được giá trị bên trong. Một số ứng dụng phản ứng bằng exception 5xx, vòng lặp login, mất attribute hoặc session bị coi là không hợp lệ. Hành vi chính xác phụ thuộc framework, serializer và error handler.

## 3. Vòng đời một session ở Redis/JDBC và điểm dễ hỏng khi deploy

```text
Build V1 (JDK/classes V1)
  │
  ├── new CartSnapshotV1(...)
  ├── session.setAttribute("cart", snapshot)
  └── serialize → bytes ở Redis/JDBC
                            │
                       rolling deploy
                            │
Build V2 (JDK/classes V2)   │
  │                         ▼
  ├── request mang cookie ID cũ
  ├── tải bytes thuộc session cũ
  ├── deserialize bằng classpath V2
  │       ├── thành công + semantics đúng
  │       ├── lỗi class/serialVersionUID
  │       └── thành công kỹ thuật nhưng dữ liệu sai logic
  └── response / login / business result
```

Trong **rolling deployment** có thể cùng lúc tồn tại:
- Node **V1 đọc session V1**.
- Node **V2 đọc session V1**.
- Node **V2 ghi session V2**, sau đó request quay lại node V1.
- Node **V1 đọc session V2**.

Vì load balancer không nhất thiết giữ cùng một pod (và sticky sessions không bảo đảm trước failover), một migration an toàn cần xét **hai chiều tương thích** khi V1 và V2 còn chạy song song. Nếu chỉ V2 đọc được dữ liệu cũ nhưng V1 không đọc được dữ liệu mới, chưa thể kết luận rollout an toàn.

Ngoài type của object, những thay đổi có thể ảnh hưởng session:
- Rename/move Java package hoặc class.
- Đổi `serialVersionUID`, thay field type, xóa class.
- Thêm field nhưng business code không xử lý giá trị default.
- Đổi enum values, semantics của field hay trạng thái authorization.
- Đổi Jackson property name, polymorphic subtype, serializer options, module.
- Đổi version Spring Security/Spring Session/Redis serializer.
- Đổi namespace Redis, key attributes, TTL, cookie settings hoặc session ID resolver.
- Cấu hình cùng session store nhưng đa ứng dụng dùng class/format khác nhau.

## 4. Java Serializable: nó làm gì và không làm gì?

JDK serialization chuyển object graph implement `java.io.Serializable` thành binary stream. Để lưu một object Java qua serializer mặc định, **toàn bộ các field thực sự được serialize cũng phải hỗ trợ serialization** (hoặc được khai báo `transient`/custom xử lý). Chỉ đánh dấu class ngoài cùng `implements Serializable` chưa đủ nếu nested field chứa một class không serializable.

Ví dụ:

```java
import java.io.Serial;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

final class CartSnapshot implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final int schemaVersion;
    private final ArrayList<String> items;

    CartSnapshot(int schemaVersion, List<String> items) {
        this.schemaVersion = schemaVersion;
        this.items = new ArrayList<>(items);
    }

    int schemaVersion() {
        return schemaVersion;
    }

    List<String> items() {
        return List.copyOf(items);
    }
}
```

Đây là class Java dùng trong project đầy đủ ở mục 7. `ArrayList<String>` là loại serializable phổ biến; `String` cũng serializable. Không lưu `EntityManager`, socket, stream, connection, thread, executor, request hay Spring bean/service vào session.

### 4.1. `serialVersionUID` không phải schema migration

`serialVersionUID` là số định danh compatibility của Java serialization ở cấp class. Khi stream chứa UID khác so với class đang load, quá trình đọc thường ném `java.io.InvalidClassException`. Khai báo tường minh:

```java
@Serial
private static final long serialVersionUID = 1L;
```

giúp tránh UID mặc định bị tự tính lại vì thay đổi mã nguồn không chủ ý. Tuy nhiên **giữ nguyên UID không bảo đảm logic tương thích**:
- Field mới có thể nhận `null`, `0` hoặc `false` khi đọc stream cũ.
- Đổi tên field có thể khiến field cũ biến mất, field mới mang giá trị mặc định.
- Đổi kiểu field, cấu trúc kế thừa hoặc custom `readObject/writeObject` có thể phá contract.
- Đổi package/class name vẫn có thể dẫn đến `ClassNotFoundException`, bất kể giữ cùng UID.
- Một class con trong object graph cũng có UID/compatibility riêng.

**Đừng sửa UID để "cưỡng ép" đọc dữ liệu** nếu cấu trúc/semantics đã không tương thích. Nên lập kế hoạch version hóa payload và migration có kiểm thử.

### 4.2. Một số exception liên quan

| Lỗi | Tình huống phổ biến |
|---|---|
| `java.io.NotSerializableException` | Có attribute/nested object không implement Serializable khi Java serializer ghi |
| `java.io.InvalidClassException` | UID không khớp, một số thay đổi cấu trúc class không tương thích |
| `java.lang.ClassNotFoundException` | Stream tham chiếu class không tồn tại ở deployment mới |
| `java.io.StreamCorruptedException` | Input binary không đúng định dạng serialization mong đợi hoặc dữ liệu bị hỏng |
| Lỗi Jackson mapping/type-id | JSON property/class metadata không tương thích với mapper V2 |
| Class cast / null dereference | Deserialize có thể thành công nhưng giá trị không đúng model/logic V2 |

Các stack trace thường xuất hiện tại **thời điểm đọc session từ store**, có thể xảy ra trước khi controller xử lý request. Không nên chỉ đặt `try/catch` quanh đoạn `getAttribute("cart")` rồi giả định mọi trường hợp deserialize lỗi đều được bắt ở đó.

## 5. Vì sao nâng cấp phiên bản làm mất session hoặc phát sinh lỗi?

### 5.1. V1 và V2 nhìn cùng tên class nhưng nghĩa khác nhau

Giả sử V1 có:

```java
// V1:
private final String shippingAddress;
```

V2 thay bằng:

```java
// V2:
private final DeliveryAddress shippingAddress;
```

Giá trị serialized từ V1 là String, nhưng V2 kỳ vọng object `DeliveryAddress`. Nếu dùng JDK serialization, đây là thay đổi field type có thể không tương thích; nếu dùng JSON deserializer, cần mapper/migration chuyển dạng cũ sang dạng mới. Nếu một phần pipeline deserialize được nhưng business code coi field mới luôn non-null, vẫn có thể lỗi khi tính phí vận chuyển.

### 5.2. V1 và V2 dùng cùng Redis nhưng ghi hai định dạng khác nhau

Giả sử V1 dùng Java binary serializer và V2 chuyển sang JSON serializer. Redis key `spring:session:...` vẫn tồn tại, nhưng serializer JSON không hiểu binary Java trước đó. Chỉ đổi bean serializer không tự migrate dữ liệu đang nằm trong store. Cần:
- Giai đoạn reader hiểu cả định dạng cũ/mới, hoặc tool migrate có kiểm soát.
- Giữ serializer cũ cho đến khi TTL hết và người dùng được thông báo, nếu chấp nhận mất phiên.
- Namespace mới với kế hoạch logout có chủ đích.
- Một lần deploy có phối hợp và kiểm tra rollback.

**Không thử parse random binary bytes như JSON** rồi im lặng fallback sang object mặc định; cần nhận diện format rõ ràng, validate và logging thích hợp.

### 5.3. Lớp security cũng có thể nằm trong session

Nếu Spring Security dùng HTTP session, attribute `SPRING_SECURITY_CONTEXT` có thể chứa `SecurityContext` và `Authentication`/principal/authorities. Không chỉ `cart` mà các class Spring Security hoặc `UserDetails` tùy biến cũng phải tương thích. Spring Security 6.3 có thay đổi kiểm thử/tính tương thích JDK serialization để giảm nguy cơ qua các minor versions, nhưng **không phải lời bảo đảm mọi custom principal của ứng dụng sẽ tương thích**.

Không dùng `serialVersionUID` chung một cách tùy tiện cho tất cả security classes tự viết; phải test với dữ liệu thật và classpath của cả bản cũ/mới.

## 6. Nguyên tắc mô hình hóa dữ liệu phiên bền vững

**Khuyến nghị:** lưu session attributes tối giản, có schema/version rõ ràng và độc lập tương đối với entity model.

Tốt hơn:
- `cartId` hoặc `draftId` trỏ tới dữ liệu chính trong DB/cache.
- Các cờ/bộ lọc nhỏ như `locale`, `theme`, hoặc danh sách SKU không nhạy cảm.
- DTO dành riêng cho session với field ổn định, danh sách kiểu đơn giản, `schemaVersion`.
- Dữ liệu có TTL/retention phù hợp, không cần phục hồi vô hạn.
- Nếu dùng JSON, có **version discriminator** (ví dụ `schemaVersion: 1`), reader hỗ trợ version cũ trong cửa sổ migration.

Không nên:
- Lưu entity JPA kèm lazy proxies (mang class graph, connection/session ORM và dữ liệu dư).
- Lưu `HttpServletRequest`, `WebClient`, `EntityManager`, `DataSource`, `InputStream`, future, thread, scheduler, lock.
- Lưu mật khẩu thô, OTP, refresh token dài hạn hoặc secrets nếu không có yêu cầu/biện pháp bảo vệ cụ thể.
- Lưu object graph khổng lồ khiến mỗi request read/write tốn tài nguyên.
- Dùng attribute như cache toàn cục không TTL.

**Cẩn thận với mutable object:** một số session repository chỉ phát hiện thay đổi khi gọi `setAttribute` (tùy `SaveMode`) chứ không nhận ra mọi mutation lồng sâu. Ví dụ sửa `cart.getItems().add(sku)` rồi không `setAttribute` lại có thể không được persisted trong Redis/JDBC. Tạo DTO bất biến/defensive copy rồi **setAttribute lại bằng object mới** để tránh lỗi tracking thay đổi, race và dirty checking.

## 7. Ví dụ chạy được: Spring Boot MVC + HttpSession + Serializable DTO

Ví dụ minh họa session object có thể serialize, tạo cookie và tái sử dụng qua nhiều HTTP request. **Bản cơ bản chỉ dùng in-memory session**; không cần Redis để chạy. Bài test ở mục 8 sẽ kiểm chứng JDK serialization thật, tránh nhầm local chạy tốt với cross-version compatibility.

**Yêu cầu:** JDK 17+, Gradle tương thích Spring Boot 3.3.x. Phiên bản 3.3.13 được ghim cho ví dụ học tập có thể tái hiện; với sản phẩm đang vận hành, dùng một dòng Spring Boot hiện còn được hỗ trợ và cập nhật bản vá.

Cấu trúc project:

```text
session-version-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/sessions/SessionVersionApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/sessions/CartSnapshotSerializationTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8080
server.servlet.session.timeout=20m
server.servlet.session.cookie.http-only=true
# Với production HTTPS nên bật cookie.secure=true
# và cấu hình SameSite phù hợp với luồng login/redirect.
```

**`src/main/java/com/example/sessions/SessionVersionApplication.java`:**

```java
package com.example.sessions;

import java.io.Serial;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class SessionVersionApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionVersionApplication.class, args);
    }
}

@RestController
@RequestMapping("/cart")
class CartController {
    private static final String KEY = "cart.snapshot.v1";

    @PostMapping("/items")
    CartView add(HttpServletRequest request, @RequestParam String sku) {
        if (!sku.matches("[A-Za-z0-9_-]{1,24}")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Invalid SKU");
        }

        HttpSession session = request.getSession(true);
        Object stored = session.getAttribute(KEY);
        CartSnapshot old = stored instanceof CartSnapshot snapshot
                ? snapshot : new CartSnapshot(1, List.of());

        List<String> items = new ArrayList<>(old.items());
        items.add(sku);

        CartSnapshot updated = new CartSnapshot(1, items);
        session.setAttribute(KEY, updated); // Giúp repository ghi nhận thay đổi.
        return new CartView(updated.schemaVersion(), updated.items());
    }

    @GetMapping
    CartView view(HttpServletRequest request) {
        // Không tạo session chỉ để xem giỏ rỗng.
        HttpSession session = request.getSession(false);
        Object stored = session == null ? null : session.getAttribute(KEY);
        CartSnapshot current = stored instanceof CartSnapshot snapshot
                ? snapshot : new CartSnapshot(1, List.of());
        return new CartView(current.schemaVersion(), current.items());
    }

    @DeleteMapping
    ResponseEntity<Void> clear(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return ResponseEntity.noContent().build();
    }
}

record CartView(int schemaVersion, List<String> items) {}

// Đây là object dành riêng cho session, KHÔNG phải JPA entity.
final class CartSnapshot implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final int schemaVersion;
    private final ArrayList<String> items;

    CartSnapshot(int schemaVersion, List<String> items) {
        this.schemaVersion = schemaVersion;
        this.items = new ArrayList<>(items);
    }

    int schemaVersion() {
        return schemaVersion;
    }

    List<String> items() {
        return List.copyOf(items);
    }
}
```

**Điểm cần chú ý:**
- Cả `CartView` (DTO response JSON) và `CartSnapshot` (object lưu session) đều tách khỏi entity/database.
- `CartSnapshot` implement `Serializable` và khai báo UID tường minh. `ArrayList<String>` cho object graph đơn giản.
- `session.setAttribute(KEY, updated)` tạo object mới thay vì sửa nested list rồi mong framework tự phát hiện thay đổi.
- `request.getSession(false)` không tạo phiên mới khi chỉ xem; `getSession(true)` tạo nếu thiếu.
- `session.invalidate()` hủy session trên server. Nó khác việc chỉ xóa cookie phía browser; nếu dùng store dùng chung, cần xem TTL/invalidation/replication semantics.
- Không trả session ID trong JSON. Cookie có thể được container gửi về và curl/browser sẽ giữ, không cần app tự gửi ID.
- Code demo không có authentication/authorization/CSRF; production phải áp dụng bảo vệ thích hợp, đặc biệt với mutation POST/DELETE.

**Chạy:**

```bash
gradle bootRun
```

Nếu project có Gradle Wrapper: `./gradlew bootRun` (macOS/Linux) hoặc `.\gradlew.bat bootRun` (Windows PowerShell).

Dùng curl giữ cookie:

```bash
# Lưu cookie từ response tạo session:
curl -i -c cookies.txt -X POST \
  "http://localhost:8080/cart/items?sku=BOOK-1"

# Gửi lại cùng cookie:
curl -i -b cookies.txt "http://localhost:8080/cart"

# Hủy session:
curl -i -b cookies.txt -X DELETE "http://localhost:8080/cart"

# Xem lại bằng cookie cũ sẽ được giỏ rỗng:
curl -i -b cookies.txt "http://localhost:8080/cart"
```

Hai response đầu (khi chưa có dữ liệu khác) dự kiến HTTP 200 và JSON:

```json
{"schemaVersion":1,"items":["BOOK-1"]}
```

Sau `DELETE`, server trả HTTP 204 No Content. Request GET tiếp theo với ID đã invalidated nhận giỏ rỗng:

```json
{"schemaVersion":1,"items":[]}
```

Không dự đoán giá trị của cookie/session ID: nó ngẫu nhiên và riêng từng request. Local in-memory demo **không kiểm chứng** việc sau restart hay giữa nhiều node vẫn giữ được session.

## 8. Test JDK serialization thật bằng Java 17 + JUnit

Bài test này cố ý serialize một `CartSnapshot` ra byte[] rồi deserialize bằng cùng class version. Nó kiểm chứng class hiện tại có thể round-trip nhưng **chưa kiểm chứng V1 đọc được bằng V2**.

**`src/test/java/com/example/sessions/CartSnapshotSerializationTest.java`:**

```java
package com.example.sessions;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

class CartSnapshotSerializationTest {

    @Test
    void cartSnapshotRoundTripsThroughJdkSerialization() throws Exception {
        CartSnapshot before = new CartSnapshot(
                1, List.of("BOOK-1", "BOOK-2"));

        byte[] bytes;
        try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(buffer)) {
            output.writeObject(before);
            output.flush();
            bytes = buffer.toByteArray();
        }

        Object restored;
        try (ByteArrayInputStream buffer = new ByteArrayInputStream(bytes);
             ObjectInputStream input = new ObjectInputStream(buffer)) {
            restored = input.readObject();
        }

        CartSnapshot after = assertInstanceOf(CartSnapshot.class, restored);
        assertEquals(1, after.schemaVersion());
        assertEquals(List.of("BOOK-1", "BOOK-2"), after.items());
    }
}
```

Chạy:

```bash
gradle test
```

Kết quả kỳ vọng: bài test **pass** với code và dependency đúng. Đây là test với stream byte **do chính test vừa tạo và tin cậy**. **Không bao giờ** dùng `ObjectInputStream` để đọc trực tiếp bytes từ request/nguồn không đáng tin mà không có mô hình an toàn thích hợp: Java deserialization với object graph không đáng tin có rủi ro thực thi gadget và tài nguyên.

Muốn kiểm tra cross-version thật, cần lưu **fixture bytes của V1** (tạo bởi artifact/classpath V1) và chạy một test riêng trong build V2 để đọc bytes đó. Một test V2 serialize rồi V2 deserialize không thể chứng minh compatibility của dữ liệu V1 còn ở Redis.

## 9. Dùng Redis để chia sẻ session giữa các instance

Spring Session thay cơ chế lưu session bằng repository, thường thông qua filter của servlet stack. **HTTP API `HttpSession` ở controller không cần đổi**, nhưng lifecycle serialize/persist chuyển sang Redis. Với Spring Boot 3.3 và ví dụ A, thêm vào `dependencies` của `build.gradle`:

```groovy
implementation 'org.springframework.session:spring-session-data-redis'
implementation 'org.springframework.boot:spring-boot-starter-data-redis'
```

Đoạn trên là **hai dòng dependency bổ sung**, không thay thế toàn bộ file build. Dùng Redis server chạy được, cấu hình thêm:

```properties
spring.data.redis.host=localhost
spring.data.redis.port=6379
spring.session.redis.namespace=demo:session:v1
server.servlet.session.timeout=20m
```

Các dòng trên là cấu hình minh họa cho local/dev. Trong production, cấu hình TLS/ACL/auth/secrets, network policy, namespace tách ứng dụng và chính sách TTL. Đừng đưa mật khẩu Redis vào Git. Spring Session Redis cùng Spring Boot auto-configuration thường đủ để quản lý `HttpSession`; không cần đồng thời viết cấu hình `@EnableRedisHttpSession` chỉ để lặp lại auto-config.

Khi có Redis session store, các request chạy trên nhiều node có thể đọc cùng ID nếu cùng repository, key namespace và serializer/class format. Nhưng nó chỉ **cung cấp chỗ lưu chung**, không tự bảo đảm mọi bản build có thể hiểu object phiên bản khác.

Spring Session Redis 3.x theo tài liệu sử dụng **JDK serialization mặc định cho session attributes**. Vì thế:
- `CartSnapshot` trong ví dụ thực sự cần serializable.
- Không serializable có thể lỗi lúc save; lỗi tương thích có thể xuất hiện lúc load.
- Các class cùng package/tên/serialVersionUID mới chỉ là điều kiện ban đầu, không bảo đảm business logic.
- Session TTL/invalidation ảnh hưởng thời gian dữ liệu cũ tồn tại và cửa sổ migration.
- Đổi namespace từ `demo:session:v1` sang `demo:session:v2` sẽ làm app không nhìn thấy session cũ. Đó là **isolation hoặc forced re-login**, không phải tự động migrate.

**Đừng nhầm session persistence và khả năng chuyển đổi class:** một Redis session sống qua restart thành công chỉ chứng minh việc byte stream còn trong Redis, không chứng minh mọi nâng cấp Java/app đều đọc lại được.

## 10. JDBC Session và Spring WebFlux có điểm gì khác?

### 10.1. Spring Session JDBC

Nếu dùng JDBC, Spring Session thường lưu session metadata ở `SPRING_SESSION` và attributes ở `SPRING_SESSION_ATTRIBUTES`. Theo hướng dẫn Spring Session JDBC 3.x, mặc định giá trị attribute được JDK serialize thành **bytes**, vì vậy vấn đề tương thích class vẫn tồn tại dù storage là SQL.

Cấu hình và dependencies thay đổi tùy database/datasource. Ví dụ **mảnh cấu hình** cho ứng dụng đã có datasource thích hợp:

```groovy
implementation 'org.springframework.session:spring-session-jdbc'
implementation 'org.springframework.boot:spring-boot-starter-jdbc'
```

Đây chỉ là dependency bổ sung; muốn chạy phải cấu hình datasource, JDBC driver, schema session, permission và connection pool. Spring Session có SQL scripts riêng cho từng database. Khi tùy biến serializer cho JDBC, phải cấu hình converter thích hợp (thường bean `springSessionConversionService`) cùng schema và SQL cho kiểu column đã chọn. Cách customize khác Redis; **không copy bean Redis serializer để mong JDBC tự đổi format**.

### 10.2. Spring WebFlux dùng `WebSession`

Trong WebFlux, abstraction là `org.springframework.web.server.WebSession`, không phải Servlet `HttpSession`. Model code minh họa trong **một dự án `spring-boot-starter-webflux` riêng**:

```java
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

// Trong @RestController WebFlux, không phải Servlet controller:
@GetMapping("/reactive/cart")
Mono<CartStatus> view(WebSession session) {
    String json = session.getAttribute("cart.json");
    return Mono.just(new CartStatus(json != null));
}

@PostMapping("/reactive/cart")
Mono<Void> mark(WebSession session) {
    session.getAttributes().put("cart.json",
            "{\"schemaVersion\":1,\"items\":[\"BOOK-1\"]}");
    return Mono.empty();
}

record CartStatus(boolean hasCart) {}
```

Đây là **mảnh code minh họa trong controller**, không phải file standalone: cần đặt các method cùng controller và import `GetMapping`/`PostMapping`, tự thiết kế input/validation thích hợp. WebFlux framework phụ trách lưu `WebSession` khi response hoàn tất theo contract; nếu tự viết flow cleanup/invalidating, lưu ý các API như `WebSession.invalidate()` trả `Mono<Void>` cần được compose/return, không tự `subscribe()` bên trong controller.

Nếu dùng Spring Session Redis cho WebFlux, cũng cần kiểm tra serialization/payload compatibility của reactive session attributes. Việc ứng dụng chạy trên Netty thay vì Tomcat **không loại bỏ** rủi ro object cũ trong Redis.

## 11. Version hóa payload JSON do ứng dụng tự kiểm soát

Một cách giảm phụ thuộc vào chi tiết class Java là lưu **chuỗi JSON với schema version tường minh** trong session, thay vì cả Java entity/object graph.

Ví dụ hai định dạng:
- V1: `{"schemaVersion":1,"items":["BOOK-1"]}`
- V2: `{"schemaVersion":2,"skuCodes":["BOOK-1"]}`

V2 có thể **đọc cả V1 và V2**, nhưng chỉ bắt đầu ghi V2 sau khi không còn node V1 nếu V1 chưa biết cách đọc V2.

Ví dụ helper sử dụng Jackson, có sẵn khi project Spring Boot web có Jackson:

**`src/main/java/com/example/sessions/CartJsonCodec.java`:**

```java
package com.example.sessions;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

final class CartJsonCodec {
    private final ObjectMapper mapper = new ObjectMapper();

    String encodeV2(List<String> skuCodes) throws JsonProcessingException {
        return mapper.writeValueAsString(Map.of(
                "schemaVersion", 2,
                "skuCodes", skuCodes));
    }

    List<String> decodeV1OrV2(String text) throws IOException {
        JsonNode root = mapper.readTree(text);
        if (root == null || !root.isObject()) {
            throw new IllegalArgumentException("Invalid cart payload");
        }

        int version = root.path("schemaVersion").asInt(-1);
        JsonNode array;

        if (version == 1) {
            array = root.path("items");
        } else if (version == 2) {
            array = root.path("skuCodes");
        } else {
            throw new IllegalArgumentException(
                    "Unsupported cart schema version: " + version);
        }

        if (!array.isArray() || array.size() > 100) {
            throw new IllegalArgumentException("Invalid cart items");
        }

        ArrayList<String> result = new ArrayList<>();
        for (JsonNode item : array) {
            if (!item.isTextual()
                    || !item.asText().matches("[A-Za-z0-9_-]{1,24}")) {
                throw new IllegalArgumentException("Invalid SKU");
            }
            result.add(item.asText());
        }
        return List.copyOf(result);
    }
}
```

**Dùng trong session (mảnh minh họa đặt trong service/controller):**

```java
CartJsonCodec codec = new CartJsonCodec();

String json = codec.encodeV2(List.of("BOOK-1"));
session.setAttribute("cart.json", json);

// Khi đọc: kiểm tra đúng type trước khi decode.
Object stored = session.getAttribute("cart.json");
if (stored instanceof String text) {
    List<String> items = codec.decodeV1OrV2(text);
    // Xử lý items theo nghiệp vụ.
}
```

Đoạn sử dụng giả định có `HttpSession session` và method cho phép throws/handle `IOException`. Nó **không phải controller hoàn chỉnh**. Trong ứng dụng thực tế nên inject/reuse ObjectMapper/codec, phân biệt lỗi dữ liệu cũ với lỗi nghiệp vụ, có logging/metric an toàn và chính sách invalidate hoặc migrate có chủ đích.

**Vì sao cách này giúp migration?**
- Java `String` có contract serialization ổn định hơn rất nhiều so với object graph ứng dụng. Nếu Spring Session vẫn dùng JDK serializer, giá trị **String** có thể vẫn được JDK serialize thành byte stream; không có nghĩa toàn bộ Redis tự nhiên đã trở thành JSON.
- Schema version và parser của ứng dụng kiểm soát cách đổi `items` → `skuCodes`, kiểm tra giới hạn và giá trị.
- Có thể test bằng JSON fixtures của nhiều bản app mà không cần load class của V1.
- Tuy nhiên nếu Redis vẫn chứa các attribute khác bằng JDK serialization (đặc biệt security context), rủi ro ở các attribute đó vẫn còn.
- Đừng dùng Jackson default polymorphic typing bừa bãi để deserialize class bất kỳ từ dữ liệu không tin cậy; danh sách class được phép và cấu hình security modules phải được thiết kế đúng.

### 11.1. Đổi serializer của toàn bộ Spring Session Redis là việc khác

Spring Session cho phép custom Redis serializer bằng bean tên **`springSessionDefaultRedisSerializer`**. Ví dụ **cấu hình minh họa** (phải kiểm tra tương thích của toàn bộ session attributes trước khi triển khai):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializer;

@Configuration
class SessionSerializerConfig {

    @Bean("springSessionDefaultRedisSerializer")
    RedisSerializer<Object> springSessionDefaultRedisSerializer() {
        return new GenericJackson2JsonRedisSerializer();
    }
}
```

Đoạn này dùng `GenericJackson2JsonRedisSerializer` thuộc Spring Data Redis; nó không phải thay đổi nên áp dụng mặc định cho mọi hệ thống. **Nếu trước đó đã có JDK-serialized sessions, thay serializer sang JSON sẽ không tự đọc dữ liệu cũ.** Cần migration/dual reader/namespace hoặc chính sách hết hạn session.

Với Spring Security, custom `ObjectMapper` thường cần các Jackson modules/mix-ins chuyên biệt để serialize/deserialize `SecurityContext` và principal. Một cấu hình JSON chung có thể hoạt động với giỏ hàng nhưng lỗi khi khôi phục authentication. Kiểm thử **toàn bộ** attributes, chứ không chỉ `cart`. Tránh bật type polymorphism rộng cho bytes không đáng tin; hạn chế quyền truy cập Redis, bảo vệ network/TLS và cấu hình chặt schema/type.

## 12. Rolling deployment: thiết kế tính tương thích hai chiều

Một bảng kiểm tra đơn giản:

| Reader đang phục vụ | Bytes/payload V1 | Bytes/payload V2 |
|---|---|---|
| **Node V1** | Phải đọc được | Có thể không đọc được |
| **Node V2** | Phải đọc được khi rolling upgrade | Phải đọc được |

Trong thời gian V1 và V2 cùng phục vụ traffic, nếu V2 **ghi** định dạng mới mà V1 **không đọc** được, ô phía trên bên phải thất bại. Một kế hoạch an toàn có thể chia thành ba bước:

**Giai đoạn A — Expand reader:** phát hành V1.5 có khả năng đọc cả schema V1 và schema V2 nhưng **vẫn ghi V1**. Đợi toàn bộ node chạy reader mới, kiểm tra metrics deserialize failures, session load/save latency và tỷ lệ 5xx. Đừng triển khai serializer global mới khi còn bytes không đọc được.

**Giai đoạn B — Switch writer:** khi mọi node đã đọc được cả hai, chuyển sang ghi V2 nhưng tiếp tục chấp nhận V1. Nếu rollback cần về V1.5, V1.5 vẫn phải đọc V2. Nếu rollback về V1 nguyên thủy thì chưa an toàn; cần kế hoạch rollback tới bản có dual-reader.

**Giai đoạn C — Contract:** sau khi TTL và thời gian giữ session bảo đảm các payload V1 đã hết/được migrate, có thể bỏ code đọc V1. Chỉ làm khi observability chứng minh session cũ không còn cần và nhóm sản phẩm chấp nhận tác động đến người dùng.

Nếu không thể duy trì compatibility (ví dụ đổi JDK binary class graph phá vỡ) thì các phương án rõ ràng là:
- **Buộc tạo session mới** khi deploy, thông báo re-login và không hứa giữ giỏ hàng chưa lưu.
- **Isolate namespace** giữa V1/V2 và có cơ chế migrate có kiểm soát; đổi namespace **không tự migrate**.
- **Stop-the-world deployment** có downtime được chấp nhận và xoá/migrate session theo kế hoạch.
- **Giữ TTL ngắn** cho phiên không chứa nghiệp vụ quan trọng rồi đợi đến lúc mọi key cũ hết hạn trước khi thay serializer.

Sticky sessions có thể giảm tần suất chuyển node nhưng không giải quyết failover, autoscaling, pod eviction hoặc rollout nhiều revision. Không dùng nó như bằng chứng compatibility.

## 13. Rủi ro nghiệp vụ, bảo mật và vận hành

### 13.1. Sai ngữ nghĩa nguy hiểm hơn exception

Deserialize thành công nhưng field mang ý nghĩa mới có thể gây hại khó phát hiện:
- `roles` từ string CSV thành list không được parse đúng, tạo authorization sai.
- `currency` thêm vào nhưng null → tính tiền với default sai.
- Giỏ hàng cũ chứa SKU đã ngừng bán, giá trị/thuế lỗi thời.
- Wizard state V1 thiếu bước consent hoặc điều khoản mới.
- Đổi tenant/customer context nhưng session cũ vẫn giữ định danh trước đây.

Không lấy session làm nguồn sự thật duy nhất cho giá/stock/privileges. Tính lại dữ liệu nhạy cảm từ nguồn có thẩm quyền, và kiểm tra authorization cho mỗi request. Với bản ghi quan trọng, lưu ở DB dưới một khóa ổn định, session chỉ giữ reference.

### 13.2. Cookie và session security

- Session ID là **bearer secret**; không log nguyên giá trị vào stdout, access logs hoặc analytics.
- Sử dụng HTTPS, `Secure`, `HttpOnly`, `SameSite` phù hợp với luồng đăng nhập/redirect và chính sách CORS/CSRF.
- Regenerate/rotate session ID sau authentication/privilege change để giảm session fixation.
- Invalidate session đúng khi logout/revocation; đồng bộ với Spring Security/session repository.
- Bảo vệ Redis/JDBC: giới hạn network, auth, ACL, encryption, backup và quyền truy cập; stored session có thể chứa PII và security metadata.
- **Không deserialize bytes Java không đáng tin** bằng ObjectInputStream tùy tiện. Java serialization có bề mặt tấn công gadget; kiểm soát input types, object filters và hạn chế classpath nếu buộc phải dùng.
- Đừng coi JSON là tự an toàn: tránh polymorphic deserialization rộng, validate schema/field sizes, giới hạn attribute bytes và số phần tử.

### 13.3. Race giữa hai request cùng session

Hai request đồng thời từ cùng browser có thể load cùng snapshot V1 và ghi đè nhau khi cả hai save, gây **lost update**. Serializable/JSON không cung cấp transaction cho việc sửa session. Nếu yêu cầu consistency của giỏ hàng, nên lưu thay đổi vào DB/Redis data structure có lock/atomic operation phù hợp, thay vì xem một session attribute object là nguồn sự thật duy nhất.

Với `SaveMode` và `FlushMode` của Spring Session, kiểm tra lúc nào attribute được đánh dấu dirty và thời điểm persist. Ví dụ session object mutable được cập nhật lồng sâu có thể không được phát hiện. Thực hành an toàn: copy immutable DTO, `setAttribute` lại; nếu ghi cạnh tranh, thiết kế concurrency control riêng.

### 13.4. TTL, eviction và deploy

TTL của session thường là **inactivity timeout** (thời hạn không hoạt động), không nhất thiết là tuổi tuyệt đối kể từ khi tạo. Session còn được sử dụng liên tục có thể sống qua nhiều lần deploy. Đừng mặc định "đợi 30 phút" đủ nếu người dùng hoạt động liên tục và dữ liệu V1 tiếp tục được refresh. Cần kiểm tra tuổi tối đa/retention, điều kiện lưu lại attribute và metrics thực tế.

Redis eviction do memory pressure cũng có thể làm mất session trước TTL; replication/failover không bảo đảm strong transaction cho toàn bộ quy trình. Tác động người dùng cần có UX: re-login, khôi phục giỏ hàng từ DB nếu cần, lỗi tải session được xử lý đúng.

## 14. Cách test migration thực sự

Một chiến lược test nhiều lớp:

1. **Unit test code hiện tại:** serialize/deserialize cùng V1/V1 hoặc V2/V2. Bắt `NotSerializableException`, kiểm tra object graph và validation.
2. **Golden fixture cross-version:** chạy chương trình V1 để tạo binary fixture thật (`CartSnapshot` và nếu có `SecurityContext`), giữ file fixture trong test resources; build V2 đọc fixture ấy và kiểm tra semantics.
3. **Compatibility matrix:** kiểm tra V1 đọc V2 nếu hai bản sẽ chạy song song; hoặc chứng minh V1 sẽ không còn phục vụ khi writer mới bật.
4. **Redis integration test:** chạy hai artifact khác phiên bản lần lượt/đồng thời với cùng Redis và namespace; tạo cookie từ V1, request tới V2, rồi trả lại V1. Kiểm tra không có 500, login/logout bất ngờ, mất giỏ hàng.
5. **Security fixture:** kiểm tra `SPRING_SECURITY_CONTEXT`, principal class tùy biến, authority và session fixation/invalidation sau nâng cấp.
6. **Rollback rehearsal:** cho V2 ghi session rồi rollback về version được phép và xác nhận đọc được dữ liệu.
7. **Failure injection:** bỏ class khỏi classpath, sửa UID của class demo, thay codec JSON, expire key, Redis down; xác nhận response/log/metric đúng.
8. **Load/concurrency test:** hai request cùng session update giỏ hàng, xác nhận chiến lược chống lost update nếu nghiệp vụ cần.

Ví dụ test ý nghĩa (mã pseudocode, **không chạy độc lập**):

```text
1) Boot V1 + Redis test container + cookie jar
2) POST /cart/items?sku=BOOK-1 -> lưu session V1
3) Tắt V1, boot V2 cùng Redis namespace/serializer
4) GET /cart cùng cookie -> nhận đúng BOOK-1
5) POST /cart/items?sku=BOOK-2 trên V2 -> lưu lại
6) Nếu rolling: đưa request về V1.5 (dual reader)
7) GET /cart -> vẫn thấy BOOK-1, BOOK-2
8) Lặp lại với Spring Security authentication/session riêng
```

Nếu bước 4 thất bại, kiểm tra lỗi serializer, class name, UID và security context. Nếu bước 7 thất bại, reader cũ không hiểu payload mới; chưa được bật writer V2 khi còn node V1.

**Đừng lấy restart local in-memory làm bằng chứng compatibility**: quá trình restart mất session object nên không có dữ liệu phiên bản cũ để thử deserialize. Test phải dùng persistent/shared store hoặc fixture bytes.

## 15. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân đáng nghi | Hướng xử lý |
|---|---|---|
| Local MVC chạy, deploy Redis bị `NotSerializableException` | Attribute/nested class không serializable | Audit object graph; chuyển sang DTO đơn giản/JSON String |
| Sau deploy 500 khi gọi endpoint có cookie cũ | `InvalidClassException`, class không tồn tại hoặc JSON mapping lỗi | Kiểm tra stack trace lúc session load; chạy fixture cross-version |
| Người dùng bị logout ngẫu nhiên giữa các pod | Security context không deserialize được; namespace khác; key mất hoặc TTL/Redis lỗi | Test Spring Security attributes, cookie/session store cấu hình đồng nhất |
| Không lỗi serialize nhưng giỏ hàng bị rỗng | Đổi attribute key/schema, default value khi đọc class cũ | Reader chấp nhận cả hai schema và migration, không im lặng bỏ dữ liệu |
| Sau đổi serializer JSON có 5xx | Redis còn byte stream JDK từ trước | Dùng migration/dual reader hoặc policy invalidate có chủ đích |
| Thêm field mới nhưng code nhận null | Java deserialization điền default cho field không có trong stream | Validate/normalize sau deserialize; cập nhật schema, test old fixture |
| Update list trong session không được persist | Mutation sâu không được đánh dấu dirty | Tạo object mới và `setAttribute`; xem SaveMode |
| Chỉ khi rollback mới lỗi | V1 không đọc được payload do V2 đã ghi | Áp expand–contract, rollback về dual-reader |
| Session mất sớm hoặc không hết hạn | TTL/inactivity, access refresh, eviction, config khác nhau | Quan sát Redis/JDBC expiry và session metadata, thống nhất config |
| Ứng dụng đổi package của DTO bị `ClassNotFoundException` | Binary Java stream gắn với class name cũ | Migration/bridge class có kiểm soát hoặc schema độc lập class |
| Một request thêm 2 món nhưng chỉ thấy 1 | Concurrent requests lost update | Kiểm soát update atomically trong storage nghiệp vụ |

**Quan sát nhưng không lộ bí mật:** log tên attribute/class/serializer, version/build ID, code lỗi, một correlation ID ẩn danh và số key fail; không log cookie value, raw serialized bytes, full principal hoặc PII. Metrics như `session_deserialization_failures_total`, `session_read_latency`, `session_migration_fallback_total`, `session_invalidations_total` giúp biết migration có đang an toàn.

## 16. Checklist trước khi nâng phiên bản ứng dụng

- [ ] Liệt kê nơi lưu session: in-memory, container replication, Spring Session Redis/JDBC, reactive `WebSession`.
- [ ] Liệt kê các attributes và object graph; nhận diện security context/principal và custom serializers.
- [ ] Biết version/build nào đã ghi dữ liệu và reader nào sẽ đọc sau rollout.
- [ ] Có schema version/DTO ổn định, hoặc cross-version Java fixture thật.
- [ ] Test **V2 đọc V1** và nếu rolling thì **V1/V1.5 đọc V2**.
- [ ] Không chuyển serializer JDK↔JSON khi còn bytes cũ mà chưa có kế hoạch migrate/invalidate.
- [ ] Dùng expand–contract, rollout/rollback theo khả năng reader, không dựa duy nhất vào sticky session.
- [ ] Xác định TTL/age thực tế, kế hoạch re-login/khôi phục state nếu buộc làm mất session.
- [ ] Bảo đảm cookie, auth session, Spring Security compatibility và Redis/JDBC security.
- [ ] Kiểm tra mutable state/lost update, metrics deserialize errors và diễn tập rollback.
- [ ] Không coi thành công của unit test với một classpath là bằng chứng tương thích qua deployment.

## 17. Đọc thêm tài liệu chính thức

- Spring Session 3.1 — Boot + Redis: dependency, filter, session timeout và namespace: https://docs.spring.io/spring-session/reference/3.1/guides/boot-redis.html
- Spring Session 3.2 — Redis custom serializer và `springSessionDefaultRedisSerializer`: https://docs.spring.io/spring-session/reference/3.2/configuration/redis.html
- Spring Session 3.3 — JDBC binary JDK serialization và custom converter/JSON: https://docs.spring.io/spring-session/reference/3.3/configuration/jdbc.html
- Spring Boot 3.3 — Spring Session integration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html
- Oracle Java SE 17 — Serializable, `serialVersionUID` và `InvalidClassException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html
- Java Object Serialization Specification — Compatible và incompatible class changes: https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/version.html
- Spring Security — Bài viết về compatibility của JDK serialization từ Spring Security 6.3: https://spring.io/blog/2024/01/19/spring-security-6-3-adds-passive-jdk-serialization-deserialization-for/

**Tóm lược:** cookie thường chỉ là khóa tìm session; rủi ro khi deploy nằm ở **serialized attributes** và cả ý nghĩa nghiệp vụ của chúng. `Serializable`/`serialVersionUID` chỉ giải quyết một phần compatibility. Với môi trường nhiều node và rolling upgrade, cần payload có version, reader tương thích hai chiều trong cửa sổ chuyển đổi, test từ dữ liệu thật V1, và chính sách invalidate/migration/rollback rõ ràng.