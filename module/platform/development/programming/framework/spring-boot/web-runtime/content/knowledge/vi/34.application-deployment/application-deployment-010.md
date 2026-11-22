# Giữ tương thích dữ liệu phiên khi nhiều phiên bản ứng dụng cùng tồn tại

## 1. Bài toán thực tế: một cookie, hai phiên bản ứng dụng

Trong một lần **rolling deployment**, **canary release** hoặc **blue–green deployment**, không phải tất cả request của một người dùng đều đi tới cùng một phiên bản phần mềm. Có thể xảy ra chuỗi:

```text
Browser của người dùng
  Cookie: SESSION=abc123
         │
         ├── request 1 ──► App V1 (pod cũ) ──┐
         │                                   │
         ├── request 2 ──► App V2 (pod mới) ──┤── Redis / JDBC
         │                                   │    session chung
         └── request 3 ──► App V1 (pod cũ) ──┘
```

Nếu V1 lưu một đối tượng `CartSession` kiểu Java vào session còn V2 đã đổi package, field hoặc kiểu dữ liệu, V2 có thể **không giải mã được** session V1. Ngược lại, khi V2 ghi một cấu trúc hoàn toàn mới, request tiếp theo quay về V1 có thể lỗi. Người dùng nhìn thấy đăng xuất bất ngờ, giỏ hàng trống, HTTP 500, lỗi deserialization hoặc tình trạng giỏ hàng thay đổi qua lại giữa hai request.

Chuyển từ session in-memory của Tomcat sang **Spring Session Redis/JDBC** giúp nhiều pod truy cập cùng dữ liệu; **nó không tự bảo đảm tương thích serialization, schema và business semantics**. Tương tự, sticky sessions chỉ giảm xác suất request đổi pod, không bảo vệ khi pod cũ bị xóa, autoscale, health check hoặc rollout.

Bài thuộc nhóm **Triển khai ứng dụng** của module **Spring Boot - web-runtime**. Mục tiêu:
- Phân biệt **session ID/cookie**, **session store** và **session attributes**.
- Hiểu rủi ro khi JDK Serializable/JSON/DTO/Spring Security context thay đổi giữa V1 và V2.
- Biết lập **ma trận đọc/ghi** trong thời gian chạy song song và rollback.
- Triển khai **schemaVersion**, dual-reader, writer gate và chiến lược expand–migrate–contract.
- Thử nghiệm bằng **Java 17+, Spring Boot 3.3.13**, một dự án MVC chạy độc lập, các unit/integration tests và phương án kết nối Redis khi nhiều instances cùng dùng session.
- Biết chọn giải pháp không gây mất dữ liệu/cưỡng bức logout ngoài kế hoạch.

**Phạm vi phiên bản:** ví dụ API dựa trên Spring Boot **3.3.13**, Spring Framework 6.1 và Spring Session 3.3. Đây là mốc minh họa; production nên dùng phiên bản còn được hỗ trợ và vá bảo mật. Tài liệu Spring Session **4.x hiện hành** có thể dùng starter/package khác; không sao chép nguyên cấu hình 4.x vào Boot 3.3 mà chưa đối chiếu.

## 2. Một session gồm nhiều lớp, lớp nào thực sự phải tương thích?

```text
Browser                          Application V1 / V2
 ┌──────────────────────┐           ┌───────────────────────┐
 │ Cookie               │           │ HTTP session wrapper  │
 │ SESSION=opaque-id     ├──────────►│ HttpSession/WebSession│
 │ HttpOnly/Secure/...   │           │                       │
 └──────────────────────┘           └───────────┬───────────┘
                                              │ lookup ID
                                              ▼
                                     ┌──────────────────────┐
                                     │ Shared session store │
                                     │ Redis / JDBC         │
                                     │ session metadata     │
                                     │ + attribute bytes    │
                                     └───────────┬──────────┘
                                                 │ decode
                                   ┌─────────────┴─────────────┐
                                   ▼                           ▼
                             V1 Java classes             V2 Java classes
                             V1 JSON contract            V2 JSON contract
```

| Lớp | Nội dung | Lỗi thường gặp |
|---|---|---|
| **Cookie/session ID** | Opaque identifier phía browser | Đổi tên cookie/path/domain; session ID không được gửi tới pod mới |
| **Session repository** | Redis/JDBC/in-memory và namespace | V1/V2 ghi vào hai namespace, hoặc pods dùng Redis khác |
| **Serialization format** | Java JDK bytes, JSON, custom serializer | V1 ghi JDK, V2 chỉ hiểu JSON; class/package không có |
| **Attribute schema** | Key như `cart.snapshot`, version, fields, types | V2 đổi `skuIds` thành `items`, V1 không hiểu |
| **Business meaning** | Giá trị có nghĩa thế nào? | Đổi đơn vị tiền, locale, enum, quyền, quy tắc coupon |
| **Security context** | Principal/roles, authentication object | V2 không deserialize được SecurityContext V1 |
| **Lifecycle** | Timeout, cookie expiration, invalidation | Session mất do đổi TTL/namespace hoặc ID rotation không đồng bộ |

**Cookie chỉ chứa ID** trong cách lưu session server-side phổ biến, không chứa toàn bộ giỏ hàng. Tuy vậy nếu hệ thống cố ý lưu **stateless token/cookie mang payload** hoặc dùng Spring Session khác, mô hình phải được kiểm tra thực tế. Không suy từ việc có cookie `SESSION` rằng tất cả session data đã được encrypt hoặc ký; server-side session ID vẫn cần bảo vệ khỏi bị đánh cắp.

### 2.1. In-memory session và shared session khác nhau

Với Tomcat mặc định không có shared session repository, mỗi pod có local session state. Một cookie `JSESSIONID` từ pod A không có nghĩa pod B biết dữ liệu tương ứng. Sticky load balancing có thể làm demo trông ổn, nhưng khi A chết dữ liệu vẫn mất.

Với **Spring Session**, Servlet `HttpSession` được thay bằng abstraction có repository (Redis/JDBC...), thông thường Spring Session đăng ký `springSessionRepositoryFilter`. Nhiều instances chỉ thật sự chia sẻ session khi chúng đồng bộ:
- Kết nối cùng repository.
- Cùng namespace/table.
- Cùng cookie name/path/domain cho browser trong phạm vi phù hợp.
- Cùng serializer/attribute contract và security settings.
- Cùng timeout/clock/configuration không gây hành vi bất ngờ.

**Chia sẻ nơi lưu không đồng nghĩa chia sẻ mã Java.** Hai pod có thể cùng đọc một Redis key mà một bên không giải mã được attribute của bên kia.

## 3. Các kiểu triển khai dễ tạo dữ liệu phiên “lai phiên bản”

| Cách triển khai | Hai phiên bản cùng phục vụ? | Rủi ro phiên |
|---|---|---|
| Rolling update nhiều pods | Có, khi thay dần replicas | Request chuyển V1↔V2 khi load balancer điều phối |
| Canary 5% traffic V2 | Có | Một người dùng có thể gặp V2 rồi quay về V1 |
| Blue–green traffic switch | Có thể trong thời gian chuyển | V2 ghi phiên rồi rollback traffic về V1 |
| A/B experiment | Có trong thời gian dài | Phiên có dữ liệu features khác nhau |
| Hotfix rollback | V2 mới bị rollback về V1 | Old reader không hiểu session do V2 ghi |
| Autoscaling nhiều images | Có nếu rollout/config không nhất quán | Session serializer và feature flags khác nhau |
| Multi-region active–active | Có, còn thêm replication lag | Session stale/lost update, thứ tự và TTL |
| Sticky session | Ít hoán đổi pod hơn | Không giải quyết pod crash, rollback, scaling |

Một canary **1%** vẫn có thể gây lỗi cho **100% request tiếp theo của các session mà nó đã ghi phiên bản mới**, nếu chúng quay về V1 và V1 không hiểu định dạng đó. Vì vậy không lấy tỷ lệ canary nhỏ để kết luận việc thay session schema là an toàn.

### 3.1. Một timeline hỏng thực tế

```text
12:00  V1 ghi Java CartState(skus=[A, B])
12:01  V2 nhận 5% traffic, đọc hoặc ghi CartStateV2
12:02  Redis sessionAttr:cart được thay bằng bytes mới
12:03  Browser quay lại V1
12:03  V1 deserialize:
       java.io.InvalidClassException
       hoặc ClassNotFoundException
       hoặc JSON schema unsupported
12:04  Người dùng báo giỏ hàng biến mất / 500
12:05  Team rollback toàn bộ về V1
12:06  V1 vẫn không đọc được các session đã bị V2 ghi
```

**Rollback image không rollback session bytes.** Đây là lý do kỹ thuật cơ bản khiến một thay đổi session format phải được xem là **data migration**, không chỉ là deploy code.

## 4. Rủi ro JDK Serialization: Serializable không phải hợp đồng bất biến

Spring Session Redis/JDBC phiên bản 3.3 sử dụng **Java serialization** cho session attributes theo mặc định trừ khi bạn chủ động cấu hình serializer/conversion khác. Java `Serializable` lưu graph đối tượng gắn với tên class, serial version UID, field descriptors và những quy tắc compatibility của Java serialization.

Ví dụ V1:

```java
package com.example.v1;

import java.io.Serializable;
import java.util.List;

public class CartState implements Serializable {
    private static final long serialVersionUID = 1L;
    private List<String> skuIds;
}
```

V2 có thể đổi thành:

```java
package com.example.v2;

import java.io.Serializable;
import java.util.List;

public class CartState implements Serializable {
    private static final long serialVersionUID = 1L;
    private List<CartItem> items;
}
```

Đây là **hai mảnh class minh họa**, không phải hai file của project chạy bên dưới. Dù đều có `serialVersionUID=1L`, đổi **fully qualified class name** từ `com.example.v1.CartState` sang `com.example.v2.CartState` khiến code không có class cũ có thể ném `ClassNotFoundException`. Đổi field types/object graph có thể khiến dữ liệu cũ bị null/default, lỗi type hoặc làm mất ý nghĩa dữ liệu. Cố giữ cùng UID **không bảo đảm semantic compatibility**.

Một số triệu chứng:
- `java.io.InvalidClassException`: stream/class descriptor không tương thích, serialVersionUID khác.
- `ClassNotFoundException`: phiên bản mới không còn class cũ trong classpath.
- `NotSerializableException`: session chứa object graph có field không Serializable.
- `ClassCastException`: vẫn deserialize được nhưng code ép sang class/type khác.
- Null/default values: một số thay đổi field có thể không ném lỗi nhưng tạo state sai.
- Java deserialization attack surface: deserialize dữ liệu không đáng tin có thể nguy hiểm; cần bảo vệ Redis/JDBC, dependency versions và serialization filters theo threat model.

**Không chữa tất cả bằng cách cố định serialVersionUID=1L.** Một class JPA entity, Hibernate proxy, lazy collection, authentication principal hay DTO có graph phức tạp vẫn có thể không ổn khi deploy V2.

### 4.1. Không đặt mutable entity/proxy trong session

Không khuyến khích:

```java
session.setAttribute("currentCustomer", customerJpaEntity);
session.setAttribute("cart", mutableCartWithHibernateCollection);
```

Những objects này có thể:
- Chứa lazy proxy không serialize được.
- Mang state đã stale so với database.
- Giữ cả graph lớn và làm phình Redis/BLOB.
- Phụ thuộc version ORM/module/package giữa hai release.
- Bị mutate trong chỗ mà Spring Session không phát hiện dirty state.

Thay vào đó chỉ lưu **ID hoặc snapshot nhỏ, có version**:

```text
sessionAttr:cart.snapshot =
  {"schemaVersion":1,"skuIds":["SKU-1","SKU-2"]}
```

Nguồn sự thật cho payment/order/inventory/authorization vẫn là database/service có cơ chế validation riêng. Session cart là dữ liệu UI tạm thời, không phải sổ cái giao dịch.

## 5. JSON không tự giải quyết mọi vấn đề phiên bản

JSON loại bỏ sự phụ thuộc trực tiếp vào tên Java class trong **application payload** khi thiết kế như một schema ổn định. Nhưng nó vẫn đòi:
- Tên field và types có hợp đồng.
- Version và rule chuyển đổi.
- Mặc định hợp lý cho field mới.
- Reader rõ cho dữ liệu cũ.
- Chính sách khi gặp version mới chưa biết.
- Phân biệt backward compatibility, forward compatibility và rollback.
- Không dùng polymorphic type metadata bừa bãi có thể dẫn tới deserialize gadget/security risk.

**Quan trọng:** chuyển **toàn bộ Spring Session serializer** từ JDK sang JSON qua một bean RedisSerializer mới **không có nghĩa các session cũ JDK tự được đọc dưới serializer mới**. Bạn cần dual-format serializer, migration tool, giữ legacy decoder hoặc chủ động chấp nhận logout. Trong project demo, ta giữ Spring Session serializer mặc định nhưng lưu **String chứa JSON schema** ở attribute `cart.snapshot`; chuỗi Java `String` ổn định khi serialize giữa nhiều Java 17 app, còn phần schema JSON do ứng dụng quản lý.

Hai cấp version khác nhau:
1. **Container serializer**: bytes Redis/JDBC → `String` attribute (JDK serialization hoặc serializer do cấu hình).
2. **Application schema**: `String` → JSON `schemaVersion=1/2` → object domain.

Nếu tầng (1) thay định dạng không tương thích, reader tầng (2) **chưa bao giờ được chạy**. Điều này phải được kiểm thử riêng.

## 6. Thiết kế envelope có version, hạn chế silent data loss

Đặt một key session ổn định `cart.snapshot`. Hai định dạng ví dụ:

**Schema V1** — lưu danh sách SKU:

```json
{
  "schemaVersion": 1,
  "skuIds": ["SKU-1", "SKU-2"]
}
```

**Schema V2** — đổi tên danh sách và thêm coupon:

```json
{
  "schemaVersion": 2,
  "items": ["SKU-1", "SKU-2"],
  "coupon": "WELCOME"
}
```

Quy tắc đọc:
- Reader tương thích **V1+V2** có thể đọc cả `skuIds` và `items`.
- Với V1, `coupon` mặc định chuỗi rỗng.
- Với V2, validate type/count/schema; coupon là field mới có ý nghĩa nghiệp vụ.
- Unknown `schemaVersion` phải được xử lý an toàn: **fail closed** hoặc trả thông báo bảo trì có kiểm soát; không tự biến thành giỏ hàng rỗng.
- Không tự bỏ unknown fields trong khi đang **downgrade writer** nếu fields đó còn cần giữ.

Quy tắc ghi:
- **Writer V1** chỉ ghi `schemaVersion=1` + `skuIds` và **không cho phép** dùng feature coupon, vì V1 không chứa được coupon.
- **Writer V2** ghi `schemaVersion=2` + `items` + `coupon`.
- Chỉ bật Writer V2 khi **không còn V1-only reader** nhận traffic và rollback target vẫn hỗ trợ V2.
- Nếu còn pod writer V1 cùng pod writer V2, pod writer V1 có thể **đọc V2 rồi ghi lại V1 và làm mất coupon**. Đó là lỗi **lost field on downgrade**; rollout phải có writer fencing hoặc chung một write policy nhất quán.

**Không coi “V2 đọc được V1” là đã an toàn để V2 ghi V2 trong mọi môi trường.** Mục tiêu trong mixed deployments là **mọi writer đang chạy phải tạo ra format mà mọi reader đang chạy đọc được**, không chỉ mới đọc cũ.

## 7. Ma trận compatibility đọc–ghi và rollback

Giả sử có ba binary/behavior:
- **A**: reader chỉ hiểu V1, writer V1.
- **B**: reader hiểu V1+V2, writer V1 (giai đoạn mở rộng reader).
- **C**: reader hiểu V1+V2, writer V2.

| Dữ liệu trong store | A: R1/W1 | B: R1+2/W1 | C: R1+2/W2 |
|---|---|---|---|
| JSON V1 | Đọc được, ghi V1 | Đọc được, ghi V1 | Đọc được, nếu mutate ghi V2 |
| JSON V2 | **Lỗi** | Đọc được, nhưng nếu mutate có thể downgrade/làm mất field mới | Đọc/ghi V2 |
| Unknown V3 | **Lỗi** | **Lỗi theo policy** | **Lỗi theo policy** |

**Kết luận an toàn theo phase:**

| Phase | Pods có thể đồng thời chạy | Định dạng được phép ghi | Rollback target |
|---|---|---|---|
| 0. Trước nâng cấp | A | V1 | A |
| 1. Expand readers | A + B | **V1** | A (an toàn đối với cart format) |
| 2. Toàn bộ reader mới | B | **V1** | B hoặc A nếu chưa có V2 data |
| 3. Switch writer | B/C nếu được **fence** để không còn W1 ghi mất field | V2 | **B-compatible reader với khả năng giữ/migrate V2**, không nên về A |
| 4. Hết rollout | C | V2 | B/C sau khi kiểm soát writer policy |
| 5. Contract old schema | C và sau hết rollback/session retention | V2 | Chỉ binary có reader V2 |

**Phức tạp ở Phase 3:** nếu B còn nhận requests và có code ghi V1, nó có thể hạ cấp session V2. Kịch bản an toàn cần **writer gate nhất quán**, hoặc tạm dừng writes ngắn, hoặc backend enforcement/CAS, hoặc writer B khi thấy V2 thì bảo tồn schema/fields đầy đủ. Một feature flag rải rác cập nhật theo thời gian có thể tạo mixed writers; **không mặc định toggle flag là atomic trên mọi pod**.

### 7.1. Giữ tương thích cho rollback

Nếu ứng dụng C đã ghi V2, rollback toàn traffic về binary A sẽ thất bại vì A không hiểu V2. Một trong các lựa chọn:
1. **Giữ binary rollback B+**, đọc được cả V1/V2, không chuyển về A.
2. **Dual-write/format compatibility** có kiểm thử và tránh last-write-wins; chỉ dùng khi đủ nghiệp vụ cho phép.
3. **Chưa bật writer V2** cho tới hết khoảng thời gian có thể cần rollback về A.
4. **Migrate data back** bằng tool có schema/rollback hỗ trợ; phải kiểm soát dữ liệu v2-only (coupon) nếu backward transformation bị mất thông tin.
5. **Buộc người dùng tạo session mới** một cách có chủ đích chỉ khi đã chấp nhận mất session state/re-auth; không âm thầm flush cả Redis.

Rollback chiến lược phải bao gồm **code, schema, data đã ghi, feature flags, cookies, security contexts và backend session store**. Một cú `kubectl rollout undo` không hoàn tác tất cả những thứ đó.

## 8. Project runnable: Spring Boot MVC với JSON schema V1/V2 trong HttpSession

Ta xây một dự án **không cần Redis để chạy unit/API tests**. Mục đích là chứng minh contract JSON và các mode Writer V1/V2 trước. Khi cần multi-pod, mục 12 thêm Redis Session vào **biến thể build/deploy**; tests với MockMvc không được nhầm là chứng cứ về Redis thực.

Project có:
- `GET /api/cart`: đọc session cart.
- `POST /api/cart/items?sku=SKU-1`: thêm SKU và ghi lại session attribute.
- `POST /api/cart/coupon?code=WELCOME`: chỉ cho phép nếu Writer V2 đã được bật.
- `POST /api/session/logout`: invalidate session (chỉ mang ý nghĩa lab, không thay authentication logout).
- `CartCodec`: dual-reader V1/V2, writer được chọn bằng property `demo.cart.write-version`.
- `@RestControllerAdvice`: từ chối session có format lạ thay vì xóa giỏ hàng âm thầm.
- JUnit codec contract tests + MockMvc session continuity tests.

### 8.1. Cấu trúc thư mục

```text
session-compat-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/sessioncompat/
    │   │   └── SessionCompatibilityApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/sessioncompat/
            └── SessionCompatibilityTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'session-compat-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

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
spring.application.name=session-compat-demo

# Giai đoạn expand: cả V1/V2-capable instances vẫn ghi V1.
demo.cart.write-version=1

# In-memory Tomcat session trong bản build cơ sở.
server.servlet.session.timeout=30m
server.servlet.session.cookie.http-only=true
```

**Không có Redis trong base build** nên mỗi app instance giữ session local; không dùng base build để khẳng định session từ pod 8081 được pod 8082 đọc. Mục 12 mới là bài kiểm thử store dùng chung.

### 8.2. Java application: record bất biến, codec theo schemaVersion và controller

**`src/main/java/com/example/sessioncompat/SessionCompatibilityApplication.java`:**

```java
package com.example.sessioncompat;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import jakarta.servlet.http.HttpSession;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class SessionCompatibilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionCompatibilityApplication.class, args);
    }
}

// Snapshot nhỏ; không lưu JPA entity hoặc object graph có proxy.
record CartSnapshot(List<String> items, String coupon) {
    CartSnapshot {
        items = List.copyOf(items);
        coupon = coupon == null ? "" : coupon;
    }

    static CartSnapshot empty() {
        return new CartSnapshot(List.of(), "");
    }
}

record CartView(List<String> items, String coupon) {
    static CartView from(CartSnapshot state) {
        return new CartView(state.items(), state.coupon());
    }
}

class IncompatibleSessionException extends RuntimeException {
    IncompatibleSessionException(String message) {
        super(message);
    }

    IncompatibleSessionException(String message, Throwable cause) {
        super(message, cause);
    }
}

@Component
class CartCodec {

    private static final int MAX_ITEMS = 50;
    private final ObjectMapper mapper;

    CartCodec(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    String encode(CartSnapshot state, int version) {
        if (version != 1 && version != 2) {
            throw new IllegalArgumentException(
                    "Supported writer versions are 1 and 2");
        }

        ObjectNode root = mapper.createObjectNode();
        root.put("schemaVersion", version);

        ArrayNode array = mapper.createArrayNode();
        state.items().forEach(array::add);

        if (version == 1) {
            if (!state.coupon().isEmpty()) {
                throw new IllegalArgumentException(
                        "V1 cannot represent coupon");
            }
            root.set("skuIds", array);
        } else {
            root.set("items", array);
            root.put("coupon", state.coupon());
        }

        try {
            return mapper.writeValueAsString(root);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException(
                    "Cannot encode cart snapshot", e);
        }
    }

    CartSnapshot decode(String encoded) {
        if (encoded == null || encoded.length() > 16_384) {
            throw new IncompatibleSessionException(
                    "Session cart payload is absent or too large");
        }

        final JsonNode root;
        try {
            root = mapper.readTree(encoded);
        } catch (JsonProcessingException e) {
            throw new IncompatibleSessionException(
                    "Invalid JSON in session cart", e);
        }

        if (root == null || !root.isObject()) {
            throw new IncompatibleSessionException(
                    "Session cart must be a JSON object");
        }

        JsonNode versionNode = root.get("schemaVersion");
        if (versionNode == null || !versionNode.isInt()) {
            throw new IncompatibleSessionException(
                    "Missing or invalid session schemaVersion");
        }

        int version = versionNode.intValue();
        if (version == 1) {
            return new CartSnapshot(readItems(root.get("skuIds")), "");
        }

        if (version == 2) {
            String coupon = "";
            JsonNode couponNode = root.get("coupon");
            if (couponNode != null && !couponNode.isNull()) {
                if (!couponNode.isTextual()
                        || couponNode.asText().length() > 20) {
                    throw new IncompatibleSessionException(
                            "Invalid session cart coupon");
                }
                coupon = couponNode.asText();
            }

            return new CartSnapshot(
                    readItems(root.get("items")), coupon);
        }

        // Không tự diễn giải dữ liệu từ version chưa biết.
        throw new IncompatibleSessionException(
                "Unsupported session schemaVersion");
    }

    private List<String> readItems(JsonNode array) {
        if (array == null || !array.isArray()
                || array.size() > MAX_ITEMS) {
            throw new IncompatibleSessionException(
                    "Invalid session cart items");
        }

        List<String> items = new ArrayList<>();
        for (JsonNode element : array) {
            if (!element.isTextual()
                    || !element.asText().matches(
                            "[A-Z0-9_-]{1,32}")) {
                throw new IncompatibleSessionException(
                        "Invalid session cart SKU");
            }
            items.add(element.asText());
        }
        return List.copyOf(items);
    }
}

@RestController
@RequestMapping("/api/cart")
class CartController {

    private static final String CART_KEY = "cart.snapshot";

    private final CartCodec codec;
    private final int writerVersion;

    CartController(CartCodec codec,
            @Value("${demo.cart.write-version:1}")
            int writerVersion) {
        if (writerVersion != 1 && writerVersion != 2) {
            throw new IllegalArgumentException(
                    "demo.cart.write-version must be 1 or 2");
        }
        this.codec = codec;
        this.writerVersion = writerVersion;
    }

    @GetMapping
    CartView get(HttpSession session) {
        return CartView.from(read(session));
    }

    @PostMapping("/items")
    CartView addItem(
            @RequestParam String sku, HttpSession session) {

        if (!sku.matches("[A-Z0-9_-]{1,32}")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid SKU");
        }

        CartSnapshot before = read(session);
        List<String> items = new ArrayList<>(before.items());
        if (!items.contains(sku)) {
            items.add(sku);
        }
        if (items.size() > 50) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Too many items");
        }

        CartSnapshot after =
                new CartSnapshot(items, before.coupon());

        // Explicit setAttribute để Spring Session có thể
        // nhận biết attribute đã thay đổi theo save-mode.
        session.setAttribute(
                CART_KEY, codec.encode(after, writerVersion));

        return CartView.from(after);
    }

    @PostMapping("/coupon")
    CartView applyCoupon(
            @RequestParam String code, HttpSession session) {

        if (writerVersion != 2) {
            // Chặn feature mới trước writer switchover.
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT,
                    "Coupon feature is not active");
        }
        if (!code.matches("[A-Z0-9]{1,20}")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid coupon");
        }

        CartSnapshot before = read(session);
        CartSnapshot after =
                new CartSnapshot(before.items(), code);

        session.setAttribute(
                CART_KEY, codec.encode(after, writerVersion));

        return CartView.from(after);
    }

    private CartSnapshot read(HttpSession session) {
        Object stored = session.getAttribute(CART_KEY);

        if (stored == null) {
            return CartSnapshot.empty();
        }
        if (!(stored instanceof String json)) {
            throw new IncompatibleSessionException(
                    "Session cart attribute is not a String");
        }

        return codec.decode(json);
    }
}

@RestController
@RequestMapping("/api/session")
class SessionLifecycleController {

    @PostMapping("/logout")
    ResponseEntity<Void> logout(HttpSession session) {
        session.invalidate();
        return ResponseEntity.noContent().build();
    }
}

@RestControllerAdvice
class SessionErrorAdvice {

    @ExceptionHandler(IncompatibleSessionException.class)
    ResponseEntity<ProblemDetail> incompatible(
            IncompatibleSessionException error) {

        // Không xóa dữ liệu và không lộ raw session contents.
        // Production cần correlation ID/metric và incident policy.
        ProblemDetail problem = ProblemDetail.forStatus(
                HttpStatus.SERVICE_UNAVAILABLE);
        problem.setTitle("Session temporarily unavailable");
        problem.setDetail(
                "Session data cannot be read by this application version");

        return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(problem);
    }
}
```

**Giải thích chi tiết:**

- File chỉ có một top-level `public class` đúng tên `SessionCompatibilityApplication.java`. Các record, controller, codec, advice là package-private, hợp lệ trong Java 17 và được Spring component scan.
- `CartSnapshot` sao chép `List` bằng `List.copyOf`, không để mutate một đối tượng session phức tạp mà Spring Session không đánh dấu dirty.
- `CartCodec.decode` hỗ trợ cả V1 và V2 nhưng **không giả định version không rõ là V1**. Invalid JSON/schema gây một exception riêng, lời khuyên vận hành là ghi metric và trả response an toàn.
- `CartCodec.encode` không cho ghi V1 nếu đã có coupon. Điều này ngăn **silent data loss** ở tầng codec; nó không ngăn được toàn bộ last-write-wins giữa hai requests song song.
- Writer version là một property cấu hình tại lúc khởi động. **Không dùng hai writer versions đồng thời nếu có V2-only fields**; khi chuyển flag phải có một release barrier và kiểm soát inflight writes/instances cũ.
- `session.setAttribute` được gọi sau mỗi mutation, quan trọng với Spring Session `save-mode=on-set-attribute`. Sửa trực tiếp list bên trong attribute mà không `setAttribute` có thể không được persist theo save mode.
- `@RestControllerAdvice` trả 503 khi app không hiểu session; không tự invalidate session và không log JSON/session ID. Đây là policy minh họa; production có thể dùng error page/support path phù hợp.
- Endpoint `/api/session/logout` chỉ dùng để học session invalidation, **không thay Spring Security logout handlers, CSRF/session fixation protections**. Trong sản phẩm thực, các POST endpoints cần authentication/authorization và CSRF policy theo loại client.
- Demo chưa có atomic compare-and-set/version counter cho concurrent updates; giỏ hàng/financial state quan trọng nên đặt ngoài HttpSession trong một durable store với transaction/optimistic locking.

### 8.3. Chạy demo một instance

Yêu cầu JDK 17+ và Gradle tương thích Spring Boot 3.3:

```bash
gradle bootRun
```

Nếu project có Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `.\gradlew.bat bootRun` trên Windows PowerShell. Chạy mặc định cổng **8080**; project cơ sở dùng local Tomcat session.

Dùng curl với cookie jar để **giữ đúng session ID** giữa các requests:

```bash
# Tạo / làm mới cookie jar cho ví dụ local:
curl -i -c cookies.txt -b cookies.txt \
  -X POST \
  "http://localhost:8080/api/cart/items?sku=SKU-1"

curl -i -c cookies.txt -b cookies.txt \
  "http://localhost:8080/api/cart"

curl -i -c cookies.txt -b cookies.txt \
  -X POST \
  "http://localhost:8080/api/cart/coupon?code=WELCOME"
```

Dự kiến hai request đầu có body tương tự:

```json
{"items":["SKU-1"],"coupon":""}
```

Request cuối nhận HTTP **409 Conflict** vì `demo.cart.write-version=1`. Đây **không phải** lỗi Redis hay serialization: đó là **feature gate** chủ động ngăn schema V2-only bị ghi sớm.

Đổi config khi chạy:

```bash
gradle bootRun --args='--demo.cart.write-version=2'
```

Bây giờ controller hỗ trợ coupon, tuy nhiên local Tomcat session của một process mới không thể đọc session in-memory đã tạo bởi process đã dừng. Để minh họa **đúng cross-instance**, chuyển sang Redis như mục 12 và dùng cùng cookie jar ở cả hai cổng.

## 9. Các bài kiểm thử độc lập: JSON V1, V2, unknown version và HttpSession

**`src/test/java/com/example/sessioncompat/SessionCompatibilityTest.java`:**

```java
package com.example.sessioncompat;

import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.servlet.http.HttpSession;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(properties = "demo.cart.write-version=1")
@AutoConfigureMockMvc
class SessionCompatibilityTest {

    @Autowired
    CartCodec codec;

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void v1PayloadCanBeReadByExpandedReader() {
        CartSnapshot cart =
                new CartSnapshot(List.of("SKU-1"), "");

        String encoded = codec.encode(cart, 1);
        CartSnapshot decoded = codec.decode(encoded);

        assertThat(decoded).isEqualTo(cart);
        assertThat(encoded).contains("\"schemaVersion\":1");
        assertThat(encoded).contains("\"skuIds\"");
    }

    @Test
    void v2PayloadCanBeReadByExpandedReader() {
        CartSnapshot cart =
                new CartSnapshot(List.of("SKU-2"), "WELCOME");

        String encoded = codec.encode(cart, 2);
        CartSnapshot decoded = codec.decode(encoded);

        assertThat(decoded).isEqualTo(cart);
        assertThat(encoded).contains("\"schemaVersion\":2");
        assertThat(encoded).contains("\"items\"");
        assertThat(encoded).contains("\"coupon\"");
    }

    @Test
    void unknownVersionIsRejectedWithoutDeletingData() {
        assertThatThrownBy(() -> codec.decode(
                "{\"schemaVersion\":3,\"items\":[]}"))
                .isInstanceOf(IncompatibleSessionException.class);
    }

    @Test
    void writerV1CannotSilentlyDropCoupon() {
        CartSnapshot cart =
                new CartSnapshot(List.of("SKU-1"), "WELCOME");

        assertThatThrownBy(() -> codec.encode(cart, 1))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("V1 cannot represent coupon");
    }

    @Test
    void oldReaderWouldFailOnV2Schema() throws Exception {
        String v2 = codec.encode(
                new CartSnapshot(List.of("SKU-1"), "WELCOME"), 2);

        JsonNode node = mapper.readTree(v2);

        // Simulate một old reader chỉ hỗ trợ schemaVersion=1.
        assertThat(node.get("schemaVersion").asInt()).isEqualTo(2);
        assertThat(node.has("skuIds")).isFalse();
        assertThatThrownBy(() -> legacyReadV1Only(v2))
                .isInstanceOf(IllegalArgumentException.class);
    }

    private String legacyReadV1Only(String json) throws Exception {
        JsonNode root = mapper.readTree(json);
        if (root.path("schemaVersion").asInt(-1) != 1) {
            throw new IllegalArgumentException(
                    "Old reader only knows V1");
        }
        return root.path("skuIds").toString();
    }

    @Test
    void mockHttpSessionReusesCartAcrossRequests()
            throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/api/cart/items")
                        .param("sku", "SKU-1")
                        .session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0]").value("SKU-1"));

        mvc.perform(get("/api/cart").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0]").value("SKU-1"))
                .andExpect(jsonPath("$.coupon").value(""));

        Object saved = session.getAttribute("cart.snapshot");
        assertThat(saved).isInstanceOf(String.class);
        assertThat((String) saved).contains(
                "\"schemaVersion\":1");
    }

    @Test
    void couponIsNotEnabledBeforeWriterSwitch()
            throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/api/cart/coupon")
                        .param("code", "WELCOME")
                        .session(session))
                .andExpect(status().isConflict());

        assertThat(session.getAttribute(
                "cart.snapshot")).isNull();
    }
}
```

Chạy:

```bash
gradle test
```

**Kết quả kỳ vọng:** bảy tests pass với Java 17/Boot 3.3.13 và dependencies đã nêu. Đây là **kỳ vọng từ phân tích code; không phải kết quả Gradle đã được chạy**.

**Phạm vi các test:**
- `v1PayloadCanBeReadByExpandedReader`: chứng minh **new reader đọc old payload**.
- `v2PayloadCanBeReadByExpandedReader`: chứng minh reader V1+V2 đọc new payload.
- `unknownVersionIsRejectedWithoutDeletingData`: không default về empty cart.
- `writerV1CannotSilentlyDropCoupon`: tránh làm mất field v2-only khi downgrade.
- `oldReaderWouldFailOnV2Schema`: mô phỏng chính xác giả định reader V1-only bằng một method nhỏ, không giả vờ đã chạy binary cũ.
- `mockHttpSessionReusesCartAcrossRequests`: chứng minh session key lưu chuỗi và setAttribute theo API Servlet.
- `couponIsNotEnabledBeforeWriterSwitch`: feature bị từ chối trong Phase 1.

**Chưa chứng minh** Redis migration, cross-process serialization, auth context Spring Security hay sticky LB, vì `MockHttpSession` nằm trong một JVM test. Các tình huống đó cần suite ở mục 13/16.

## 10. Vì sao tests trên chỉ là điểm khởi đầu: cross-version contract thật

Trong dự án thật, có ít nhất **hai phiên bản code/artefact**. Nếu V1 build với classpath không có DTO mới, test trong V2 JVM có đầy đủ class mới không phát hiện `ClassNotFoundException` xảy ra trên V1. Vì vậy phải giữ:
- Golden session payload bytes/JSON fixture **được tạo bởi binary V1 thật**.
- Test V2 đọc bytes của V1, không phải chỉ V2 encode rồi V2 decode.
- Golden payload của V2, test rollback binary B đọc được.
- Integration test cùng Redis/JDBC thực, không dùng Mockito cho serialization layer.
- Cross-instance request test với cookie qua hai base URLs.
- Test rolling upgrade khi một pod còn dùng old writer và một pod dùng new writer.
- Test security login continuity và logout/invalidate từ cả hai phía.
- Test read/write race và TTL expiration.

**Golden fixtures có thể chứa thông tin nhạy cảm** nếu được lấy từ production. Dùng synthetic test sessions; không commit production cookie/token, session IDs, customer data hoặc principal objects vào repo.

### 10.1. Một ma trận integration cần chạy tự động

| Producer | Consumer | Data | Kỳ vọng |
|---|---|---|---|
| A V1 writer | A V1 reader | V1 | PASS |
| A V1 writer | B dual-reader | V1 | PASS |
| B V1 writer | A V1 reader | V1 | PASS |
| C V2 writer | B dual-reader | V2 | PASS read; tránh B ghi V1 làm mất coupon |
| C V2 writer | A V1-only reader | V2 | **Dự kiến không tương thích**; không được cho traffic đó |
| C V2 writer | C V2 reader | V2 | PASS |
| B reader + C reader | Concurrent mutate cùng cart | V1/V2 | Không được silent lost update/field |
| Unknown future schema V3 | B/C | V3 | Fail closed, không xóa session |
| Session expired | B/C | No data | Tạo session mới theo policy |
| Wrong cookie name/domain | B/C | No ID | Dùng cookie contract nhất quán |
| Redis unavailable | B/C | Existing ID | Error/fail policy rõ, không tự tạo login giả |
| SecurityContext V1 bytes | Security V2 | Authentication | Read được hoặc migration/reauth có kế hoạch |
| Rollback sau V2 write | B/C rollback | V2 | Đọc được, bảo toàn field mới |
| Rollback về A | A old | V2 | **Không deploy** nếu không có backward migration |

Không chỉ assert status 200; kiểm tra **dữ liệu vẫn đúng** sau một chuỗi V1→V2→V1, và không có update bị mất do concurrent writers.

## 11. Thêm dữ liệu mới có cần đổi schemaVersion không?

Không phải field mới nào cũng cần một schema version mới, nhưng **đổi ý nghĩa hoặc khả năng biểu diễn** thì cần contract rõ.

| Loại thay đổi | Rủi ro | Gợi ý |
|---|---|---|
| Thêm optional JSON field với default phù hợp | Thấp nếu old reader ignore unknown và writer preserve | Compatibility test, có thể cùng schema nếu hợp đồng quy định |
| Rename `skuIds` → `items` | Cao nếu old reader expect key cũ | Dual reader/dual-write hoặc new schemaVersion |
| Thay `priceCents` thành `priceDollars` | Cao dù JSON vẫn là number | Version, migration + unit conversion |
| Đổi enum `PENDING` → `QUEUED` | Cao với old switch/mapper | Expand enums hoặc stable wire value mapping |
| Đổi timezone semantics | Cao nhưng có thể không lỗi parser | UTC/ISO-8601 contract và migration |
| Đổi UUID string thành object | Cao | V2 schema và decoder hai dạng |
| Thêm coupon/discount không thể encode trong V1 | Cao khi rollback | Feature gate + writer barrier |
| Chuyển package Java class Serializable | Cao với JDK bytes | Giữ legacy class/serializer hoặc migration |
| Thay Redis serializer JDK→JSON | Rất cao | Dual decoder/namespace migration có kế hoạch |
| Đổi cookie `SESSION` ↔ `JSESSIONID` | Cao ở authentication/session lookup | Cookie transition strategy |
| Đổi encryption key cho signed cookie/token | Cao | Key rotation overlap và dual-key verification |

**Đừng tự đoán “Jackson sẽ ignore unknown fields”** nếu deserializer được cấu hình `FAIL_ON_UNKNOWN_PROPERTIES` hay custom type binder. Trong demo ta dùng `JsonNode` và chọn trường bằng tên nên dễ kiểm soát; nếu dùng DTO với Jackson, cần cấu hình rõ và kiểm thử với cả V1/V2 fixtures.

### 11.1. Nếu chỉ là ID trong session

Với app API stateless hơn, có thể lưu `userId`/`cartId` và mỗi request đọc trạng thái thực từ DB/cache, tránh lưu một graph DTO lớn. Đổi DTO Java ở application layer lúc này ít tác động serialization session. Tuy nhiên:
- Không tin userId từ client; phải xác thực.
- Không dùng session ID làm authorization token cho DB object không kiểm tra quyền.
- DB/cache schema vẫn phải tương thích nhiều versions.
- Thao tác đọc thêm DB có latency/cost cần đo.
- TTL, concurrency và invalidation vẫn cần quản trị.

Với giỏ hàng và thông tin giao dịch quan trọng, lưu `cartId` rồi quản lý cart state trong một store có optimistic locking/idempotency thường đáng tin hơn lưu giỏ hàng mutable hoàn toàn trong session.

## 12. Biến thể triển khai thực: Spring Session Redis dùng chung giữa nhiều pods

**Quan trọng về phiên bản:** trong Spring Boot **3.3**, sử dụng modules được quản lý version như:

```groovy
// Thêm các dòng sau vào dependencies của build.gradle Boot 3.3:
implementation 'org.springframework.boot:spring-boot-starter-data-redis'
implementation 'org.springframework.session:spring-session-data-redis'
```

Đừng dùng starter `org.springframework.boot:spring-boot-starter-session-data-redis` theo tài liệu Boot **4.x** rồi giả định artifact đó có cùng GAV ở Boot 3.3. Spring Boot 3.3 sẽ auto-configure Spring Session Redis khi Spring Session và Redis connection dependencies thích hợp có mặt. Chỉ dùng một session store implementation nếu không có chủ đích chọn store.

Cấu hình chung cho **mọi instance**:

**`src/main/resources/application.properties`** hoặc environment overrides:

```properties
spring.data.redis.host=127.0.0.1
spring.data.redis.port=6379

# Dùng cùng một namespace qua tất cả các release của cùng app.
spring.session.redis.namespace=demo:sessioncompat

# Timeout cho session repository; không lẫn với cookie max-age.
spring.session.timeout=30m

# Chỉ ghi thay đổi khi save; đồng bộ attribute khi setAttribute.
spring.session.redis.flush-mode=on-save
spring.session.redis.save-mode=on-set-attribute

# Vẫn dùng writer V1 trong phase expand.
demo.cart.write-version=1
```

Những property này có trong Spring Boot 3.3, nhưng **đặt vào app chưa có Redis dependencies không tự tạo Redis-backed sessions**. Nếu thêm dependencies rồi quên chạy Redis, endpoints truy cập session có thể thất bại do Redis connection unavailable.

Spring Session Redis:
- Lưu session metadata + attributes vào Redis với keys trong namespace, có expiration/TTL.
- Sử dụng JDK serialization cho attribute values theo mặc định ở Spring Session 3.3.
- Thay thế container `HttpSession` thông qua `springSessionRepositoryFilter` ở Servlet stack.
- Mặc định cookie thường tên `SESSION` khi Spring Session cookie resolver được dùng, **không nhất thiết là Tomcat `JSESSIONID`**.
- Quản lý session timeout; không đồng nghĩa browser cookie Max-Age, Redis TTL và auth token expiry đều giống nhau.
- Có thể cấu hình flush/save mode, indexed repository, expiration events tùy nhu cầu, không tự bật mọi event/capability.
- Thời điểm write/flush ở end-of-request có thể làm một thao tác update xuất hiện muộn hơn với request đồng thời; điều này cần cross-node concurrency tests.

### 12.1. Chạy hai processes với cùng Redis (lab)

Cần local Redis (không dùng production store):

```bash
docker run --rm --name sessioncompat-redis \
  -p 127.0.0.1:6379:6379 redis:7
```

Build project **sau khi đã thêm hai dependencies Redis**:

```bash
gradle clean bootJar
```

Với `settings.gradle` đã chỉ định, jar dự kiến:

```text
build/libs/session-compat-demo-1.0.0.jar
```

Terminal 1 — instance B (reader V1+V2, writer V1):

```bash
java -jar build/libs/session-compat-demo-1.0.0.jar \
  --server.port=8081 \
  --demo.cart.write-version=1
```

Terminal 2 — instance C (reader V1+V2, writer V2):

```bash
java -jar build/libs/session-compat-demo-1.0.0.jar \
  --server.port=8082 \
  --demo.cart.write-version=2
```

Đây là **hai processes cùng source code với hai write policies**, không phải hai binary Java thực sự khác nhau; nó minh họa phần schema/persistence của rollout, **không thay golden cross-version tests**.

Trong **phase expand**, hãy để **cả 8081 và 8082 ghi V1**. Chỉ chuyển instance writer2 khi:
1. Không còn V1-only reader trong fleet.
2. Không còn W1 cũ có thể làm mất v2-only fields, hoặc đã có write-fencing.
3. Rollback artifact đọc được V2.
4. Business feature mới đã được gate và tests pass.

### 12.2. Kiểm thử cookie qua hai base URLs

Sau khi đã thiết lập phase phù hợp:

```bash
# Bắt đầu bằng instance 8081:
curl -i -c cookies.txt -b cookies.txt \
  -X POST \
  "http://localhost:8081/api/cart/items?sku=SKU-1"

# Giữ cookie và đọc từ instance 8082:
curl -i -c cookies.txt -b cookies.txt \
  "http://localhost:8082/api/cart"

# Tại 8082 với writer2, thêm coupon:
curl -i -c cookies.txt -b cookies.txt \
  -X POST \
  "http://localhost:8082/api/cart/coupon?code=WELCOME"

# Đọc lại ở 8081 chỉ khi reader của nó đã hiểu V2:
curl -i -c cookies.txt -b cookies.txt \
  "http://localhost:8081/api/cart"
```

Cookie không phân biệt TCP port theo HTTP cookie model (domain/path/scheme mới quan trọng), nên `localhost:8081` và `localhost:8082` có thể dùng một jar nếu cookie attributes phù hợp. **Dùng cùng host `localhost`**, đừng lẫn `localhost` và `127.0.0.1` trong test cookies.

Sau khi writer2 ghi V2, reader1+2 ở 8081 đọc được. Tuy nhiên nếu 8081 (writer1) **mutate** giỏ hàng lúc coupon đang tồn tại, `codec.encode(...,1)` của demo chủ động ném lỗi thay vì làm mất coupon. Đó là hàng rào an toàn ở mức codec, không phải trải nghiệm người dùng mong muốn. Production cần **ngừng cho W1 nhận write traffic hoặc đồng bộ writer policy**.

**Không kết luận “hai ports hoạt động = mọi production browser session đều ổn”.** Còn phải kiểm thử cookie Domain/SameSite/Secure, TLS/WSS, sticky LB, Redis availability, auth context, login/logout, concurrency và rollback.

## 13. Redis namespace, cookie và TTL: cùng store vẫn có thể “mất phiên”

Các release cần dùng chung cấu hình ổn định:

| Thuộc tính | V1 | V2 | Nếu khác |
|---|---|---|---|
| Redis endpoint/cluster/DB | Cùng môi trường | Cùng môi trường | Session ID tra không ra data |
| `spring.session.redis.namespace` | `shop:session` | `shop:session` | Hai keyspaces tách biệt, nhìn như logout |
| Cookie name | `SESSION` | `SESSION` | Browser gửi cookie sai/khác |
| Cookie path/domain | `/` / domain chuẩn | Tương thích | Cookie không tới app mới |
| Cookie Secure/SameSite | TLS & policy hiện hành | Tương thích | Browser có thể từ chối/gửi thiếu cookie |
| Session timeout | 30m | 30m | Các pod có kỳ vọng expiry khác |
| JDK/JSON serializer | Cùng contract | Cùng contract | Không đọc được attribute bytes |
| Security context serialization | Có lớp & modules tương thích | Tương thích | Authentication biến mất hoặc lỗi |
| Clock/TTL behavior | Time sync | Time sync | Session hết hạn bất ngờ |
| Field-schema reader | V1 | V1+V2 | Phải kiểm tra trước khi writer V2 |

**Redis namespace không phải schema migration.** Đổi namespace từ `shop:session:v1` sang `shop:session:v2` mà không bridge/migrate thực tế làm cho các sessions cũ không được tìm thấy. Nếu muốn cô lập dữ liệu mới bằng namespace mới, cần thiết kế cách xác định session ID ở cả hai kho, tránh bypass security, kế hoạch logout/rehydration và dừng ghi tại namespace cũ.

**TTL thường là sliding inactivity timeout** (maxInactiveInterval) tùy repository/cách session được truy cập. Không suy từ `spring.session.timeout=30m` rằng mọi session sống tối đa đúng 30 phút kể từ login; người dùng hoạt động có thể gia hạn. Vì vậy thời gian chờ “hết sessions V1” có thể cần deadline/absolute max age riêng, hoặc migration/lazy read repair.

**Không chạy** `redis-cli FLUSHALL` để “fix” lỗi migration. Nó xóa cả session của những hệ thống khác cùng Redis và gây logout diện rộng. Nếu cần xử lý có chọn lọc, phải dùng namespace/keys có owner rõ, snapshot/backup và rollout plan được phê duyệt.

### 13.1. Quan sát session keys một cách an toàn

Ví dụ kiểm tra metadata trong local Redis:

```bash
redis-cli --scan --pattern 'demo:sessioncompat:sessions:*'
```

Đừng dump nguyên session values vào logs/tickets vì chứa authentication, user preferences và dữ liệu có thể nhạy cảm. Khi cần xem cấu trúc ở môi trường test, sử dụng synthetic cookie/session IDs và môi trường Redis cô lập.

Redis TTL, session cleanup và expiration events là các cơ chế có thể có delay/implementation-specific. Không dùng event “session expired” như một distributed lock/quyết định tài chính phải chính xác tuyệt đối về thời điểm.

## 14. Session Redis/JDBC serializer: không chuyển format trực tiếp trong một rollout

Nếu V1 dùng **JDK serialized attribute bytes** còn V2 thay Spring Session serializer sang JSON:
- Dữ liệu JDK không tự thành JSON.
- Đổi serializer có thể làm V2 fail ngay ở bước load `SPRING_SECURITY_CONTEXT`/`cart` dù application cart JSON schema còn đúng.
- Nếu V2 ghi JSON bytes, V1 JDK serializer có thể không đọc được → rollback hỏng.
- Thay Redis namespace để “tránh mismatch” lại khiến session cũ không còn nhìn thấy.
- Một dual-format serializer cần nhận diện format an toàn, parse theo allowlist, encode có version và test cả read/write/rollback.

Trong Spring Session Redis 3.3 có thể override bằng bean tên **`springSessionDefaultRedisSerializer`**. Ví dụ dưới đây **chỉ minh họa API extension point**, **không được bật ngay trong app có session JDK cũ**:

```java
// Fragment trong @Configuration, không phải class standalone:
@Bean("springSessionDefaultRedisSerializer")
RedisSerializer<Object> sessionSerializer() {
    return new GenericJackson2JsonRedisSerializer();
}
```

Đoạn này cần imports `org.springframework.data.redis.serializer.RedisSerializer`, `GenericJackson2JsonRedisSerializer` và `org.springframework.context.annotation.Bean`. **Không copy rồi deploy trực tiếp** nếu có existing JDK sessions: nó có thể làm người dùng mất session/không deserialize được và có rủi ro polymorphic deserialization. Nếu dùng Spring Security, cần xử lý Jackson modules/mix-ins tương ứng, kiểm soát allowed polymorphic types và version.

Với **Spring Session JDBC**, attributes thường được lưu trong bảng `SPRING_SESSION_ATTRIBUTES` dưới dạng serialized bytes (`ATTRIBUTE_BYTES`); thay conversion hoặc DB column encoding cũng là migration phải được kiểm thử. Không coi việc chuyển Redis→JDBC tự động giữ sessions; store migration cần design riêng, data sync/dual read/controlled relogin.

**Khuyến nghị:** nếu mục tiêu chỉ là thay đổi một attribute nghiệp vụ, giữ nguyên session repository serializer và version riêng **value của attribute đó**. Chỉ đổi serializer của toàn session khi đã có lý do rõ ràng, dual decoder và kế hoạch áp dụng rộng vì nó ảnh hưởng cả authentication state.

## 15. Migrate từ object phiên Java cũ sang chuỗi JSON mới

Giả sử đang có legacy attribute `"cart"` chứa `LegacyCart implements Serializable`. Version mới muốn dùng `"cart.snapshot"` là String JSON. Migration **không thể chỉ đọc key mới** vì sessions cũ chưa có.

Một chiến lược có kiểm soát:

**Phase A – Compatibility bridge:**
- Giữ class `LegacyCart` với package/serialVersionUID tương thích để decode bytes cũ.
- Khi request đọc session, kiểm tra cả key cũ và mới theo quy tắc ưu tiên được thiết kế.
- Chuyển legacy object sang DTO nhỏ, encode JSON schema V1.
- Trong giai đoạn còn old pods, chưa vội xóa legacy attribute nếu old reader còn phụ thuộc.
- Tránh ghi hai key độc lập và không có cơ chế đồng bộ: chúng sẽ drift khi mỗi pod chỉ cập nhật một key.

**Phase B – Cutover source of truth:**
- Đưa mọi reader lên bridge trước.
- Đồng bộ/fence writers cũ để không còn ghi lại legacy key sau migration.
- Định nghĩa rõ key nào là source-of-truth, viết migration với một version/revision marker và xử lý concurrent writes.
- Nếu dùng read-repair khi đọc, chỉ ghi sau khi bảo đảm không ghi đè newer data; xem optimistic locking/CAS.
- Có metrics số legacy sessions đọc/migrated và errors.

**Phase C – Retire legacy:**
- Đợi rollback window và session TTL/absolute retention đủ.
- Chỉ lúc đó mới loại legacy DTO/decoder.
- Loại legacy Redis/JDBC attributes có chọn lọc khi không cần, không xóa cả session và authentication.

Một đoạn code **ý tưởng, không phải class runnable**:

```java
Object rawNew = session.getAttribute("cart.snapshot");
Object rawLegacy = session.getAttribute("cart");

if (rawNew instanceof String json) {
    return codec.decode(json);
}
if (rawLegacy instanceof LegacyCart old) {
    CartSnapshot state = migrateLegacyCart(old);

    // Chỉ được ghi nếu source-of-truth/concurrent writer rules
    // đã được giải quyết. Không làm read-repair mù quáng.
    session.setAttribute(
            "cart.snapshot", codec.encode(state, 1));
    return state;
}
return CartSnapshot.empty();
```

`LegacyCart` và `migrateLegacyCart` phải thực sự có implementation, classpath và type contract của V1. Nếu legacy bytes **không thể deserialize** vì class cũ đã bị xóa, code trên **không bao giờ chạy tới instanceof**: phải giữ module legacy hoặc xây offline migration dùng đúng compatible classpath/serializer.

## 16. Spring Security: session data không chỉ có cart

Ứng dụng đăng nhập bằng Spring Security có thể lưu authentication state trong session attribute mang tên **`SPRING_SECURITY_CONTEXT`**. Object graph thường gồm:
- `SecurityContext`/`Authentication` implementation.
- Principal/user-details types.
- Granted authorities/roles và custom claims.
- Các objects từ security libraries hay SSO integration.
- Serialization metadata nếu dùng JDK/JSON serializer.

Khi nâng Spring Boot/Spring Security hoặc đổi custom principal, hai pods có thể **không tương thích authentication serialized state**, ngay cả khi `cart.snapshot` đọc tốt. Một V2 không giải mã SecurityContext V1 có thể gây logout/401/500. Một V1 nhận authentication từ V2 có thể có vấn đề tương tự.

Checklist bảo vệ:
1. Kiểm thử login trên V1 → request authenticated trên V2 → trở lại V1.
2. Kiểm thử remember-me, logout/invalidate và session ID rotation nếu đang dùng.
3. Giữ custom principal nhỏ/stable, tránh JPA entity/lazy proxy.
4. Nếu chuyển Java serializer→JSON, dùng Spring Security Jackson modules/mix-ins cần thiết, không bật Jackson default typing rộng trên untrusted data.
5. Kiểm tra rules về authorities/roles ở cả V1/V2, không chỉ rằng object deserialize không lỗi.
6. Không tự tạo authenticated principal khi session attr không đọc được; **fail securely**.
7. Không gửi session ID, serialized SecurityContext hoặc tokens vào logs/metrics.
8. Có kế hoạch **controlled re-authentication** nếu một format change không thể backward compatible.

**Session fixation:** khi authentication thành công, Spring Security có cơ chế đổi session ID nhằm bảo vệ. V1/V2 và proxy phải cùng hiểu cookie/ID rotation. Không coi việc session ID thay đổi hợp lệ khi login là bằng chứng store migration thất bại.

**CSRF/SameSite:** nếu frontend dùng cookie session, các thao tác POST/PUT/DELETE vẫn cần CSRF defenses phù hợp (Spring Security mặc định/chiến lược token tùy architecture). SameSite giúp giảm một số tấn công nhưng không thay authorization/CSRF hoàn chỉnh.

## 17. Concurrent writes: schema tương thích vẫn có thể mất dữ liệu

Khi hai requests cùng dùng một session:
1. Request A đọc cart có item `SKU-1`.
2. Request B đọc cart cũng chỉ có `SKU-1`.
3. A thêm `SKU-2` rồi save.
4. B thêm `SKU-3` trên snapshot cũ rồi save.
5. Store giữ phiên cuối cùng do B ghi → có thể **mất SKU-2**.

```text
Time ──────────────────────────────────────────►

Request A: read [1] ── add [2] ── save [1,2]
Request B:   read [1] ── add [3] ──────── save [1,3]
Session:   [1]         → [1,2]          → [1,3]
                                               ▲ lost update
```

Đây là vấn đề **concurrency/last-write-wins**, không phải riêng schemaVersion. `session.setAttribute(...)` đánh dấu thay đổi để save, **không phải compare-and-swap toàn session**. Một `synchronized(session)` trong một JVM không đồng bộ nhiều pod.

Nếu cart quan trọng:
- Đặt state trong DB/Redis key có **revision** và dùng optimistic locking hoặc atomic script/transaction.
- Dùng idempotency key cho mutations từ browser/retry.
- Có semantics merge cho các thay đổi độc lập; tránh ghi đè dựa snapshot stale.
- Với discount/coupon có tính tiền, luôn validate lại theo current rules khi checkout.
- Tách user session ID khỏi business cart/order state.
- Đo conflicts và tự retry **chỉ khi phép biến đổi idempotent/mergeable**.

Thay đổi V1↔V2 còn khiến vấn đề khó hơn vì một writer cũ có thể làm mất field mới. Nếu rollout không thể bảo đảm writer barrier, hãy giữ session cart **read-only trong thời gian chuyển schema** hoặc chuyển mutation vào một backend chung kiểm soát version.

## 18. Lập kế hoạch triển khai theo expand–migrate–contract

### 18.1. Trước khi triển khai

- Liệt kê toàn bộ session attributes đang lưu, kiểu dữ liệu, serializer, kích thước, TTL, owner/service.
- Xác định attributes có thể ảnh hưởng login/checkout/payment/role, không chỉ cart UI.
- Tạo fixtures từ version đang chạy; test read-back với build mới.
- Định nghĩa schemaVersion, fallback defaults, rule cho unknown version, invalid JSON.
- Kiểm tra old writer có ignore/drop unknown fields hay không.
- Xác định thời hạn session tối đa/trong trạng thái active; không chỉ TTL inactivity.
- Ghi chính sách canary/rollback và quyền thay session format.
- Bật metrics dành cho session decode failures/migrations trước khi thay writer.

### 18.2. Phase 1: triển khai dual-reader nhưng giữ writer cũ

Build **B**:
- Đọc V1 và V2.
- Ghi **chỉ V1**.
- Chưa bật feature chỉ V2 mới biểu diễn được (coupon).
- Giữ same cookie/store/namespace/timeout.
- Canaries được phép vì các sessions họ ghi ra vẫn là V1 mà A hiểu.

Test:
- A ghi → B đọc.
- B ghi → A đọc.
- B đọc dữ liệu bị hỏng/unknown → fail safely.
- Login A → B → A.

### 18.3. Phase 2: retire V1-only readers

- Rollout B đến **100%** và xác nhận A đã không còn nhận traffic, kể cả queues, old ingress routes, idle keep-alive và background workers.
- Theo dõi session decode success/error, auth failures và session store latency.
- Xác nhận **rollback target** không còn là binary A cũ không đọc V2.
- Nếu có nhiều regions/tenants, cần chứng minh tất cả đang reader-compatible.

### 18.4. Phase 3: đổi writer có barrier

- Giữ tất cả binaries đã có dual-reader.
- Chuyển mọi writers sang V2 **như một thay đổi có điều phối**, không để W1 cũ hạ cấp V2 sau khi users bật coupon.
- Cân nhắc feature gate tại edge/business service, khóa tạm mutations trong lúc switch nếu cần.
- Backend có thể dùng compare-and-set/version guard để cấm session downgrade.
- Bật coupon chỉ sau khi writer V2 ổn định và rollback baseline đọc/ghi được V2.
- Cảnh báo nếu quan sát `schemaVersion=2` bị ghi thành `1`.

### 18.5. Phase 4: contract sau expiry/rollback window

- Đợi các V1 sessions được migrate hoặc hết hạn theo policy.
- **Không tự suy sau 30 phút là không còn V1** khi timeout là sliding inactivity và users liên tục hoạt động.
- Khi metrics cho thấy V1-read đã về 0 trong một khoảng có ý nghĩa, cùng rollback đã đóng, có thể cân nhắc bỏ reader V1.
- Đừng xóa legacy decoder sớm nếu còn raw JDK sessions từ thời trước migrate.
- Cleanup legacy attributes/keys có scope và backup; không chạy FLUSHALL.

Đây là chiến lược tổng quát. Khi có nhiều session stores, đa vùng hoặc migrations có tổn thất thông tin, cần bổ sung runbook và dry-run trên snapshot synthetic/anonymized.

## 19. Triển khai Kubernetes, blue–green và sticky LB

Một Deployment có thể bắt đầu replacement pods mới trước khi pods cũ bị rút khỏi Service. Nếu chỉ dùng cùng image tag mà dependencies khác nhau, serialization vẫn có thể thay đổi. Hãy coi **image digest** và **serializer config** là một phần của deployment compatibility contract.

Kubernetes không bảo đảm “request tiếp theo của user chỉ tới đúng pod cũ”, kể cả khi sessionAffinity được bật:
- Pod bị xóa khi rolling update.
- Client IP thay đổi hoặc nhiều users dùng chung NAT.
- Service/Ingress có chính sách affinity khác nhau.
- HTTP/2 keep-alive connection tồn tại trước rollout.
- Browser reconnect sau timeout/pod drain.
- Blue–green rollback trả traffic về bản cũ.

**Sticky sessions không thay shared/durable store** nếu yêu cầu giữ session qua pod recreation. Nhưng shared store **không bảo đảm schema compatibility**; cả hai là những vấn đề riêng.

### 19.1. Readiness và graceful shutdown

Với Spring Boot 3.3:
- `management.endpoint.health.probes.enabled=true` có thể bật liveness/readiness endpoints khi dùng Actuator.
- `server.shutdown=graceful` và `spring.lifecycle.timeout-per-shutdown-phase=...` giúp in-flight HTTP requests hoàn tất trong budget khi app đóng.
- Readiness/Ingress routing giảm requests mới tới terminating pod.
- `terminationGracePeriodSeconds` phải đủ cho preStop + graceful + margin.

**Không dùng graceful shutdown để che việc reader không hiểu writer mới.** Một request hoàn tất trên V2 có thể ghi session V2; request ngay sau đó có thể tới V1 và lỗi khi đọc. Cần compatibility plan trước cả khi bàn tới network drain.

### 19.2. Blue–green traffic switch và rollback

Trong blue–green, có thể chỉ green nhận traffic ở một thời điểm, nhưng:
- Sessions vẫn nằm trong Redis chung.
- Green có thể đã migrate/ghi format mới.
- Rollback về blue **vẫn đọc dữ liệu mới**.
- Nếu green đổi cookie name/namespace, browser còn cookie cũ có thể không kết nối được phiên.
- Nếu green đổi security principal serialization, người dùng có thể mất auth.

Hãy mô phỏng **switch sang green, tạo/mutate session, switch về blue** trong staging. Chỉ ghi “rollback tested” khi **đã kiểm tra cross-version session bytes và behavior**, không chỉ thấy pods Running.

## 20. Các tình huống cần tránh để không phá session production

### 20.1. Không xóa cả session khi gặp một attribute không đọc được

Nếu cart schema lạ, invalidate toàn session có thể làm người dùng mất login và các attributes hợp lệ. Theo yêu cầu nghiệp vụ:
- Có thể trả 503/409 có kiểm soát.
- Ghi metric/correlation ID, giữ state để hỗ trợ migration.
- Nếu dữ liệu mất an toàn rõ ràng, làm invalidation theo policy bảo mật được duyệt.
- Nếu chỉ cart có thể tái tạo, có thể làm reset **riêng cart attribute** sau xác nhận/khuyến cáo, không tự xóa SecurityContext.

Demo trả 503 mà không xóa session; đây là lựa chọn bảo tồn để dễ rollback/điều tra. Nó không phải HTTP status bắt buộc theo Spring.

### 20.2. Không tự động deserialize payload bất kỳ do client gửi

Redis/JDBC session backend cần được bảo vệ bằng network ACL, auth/TLS và least privilege. Không cho client truyền raw Redis keys, Java serialized object bytes hoặc tùy ý chọn class type để deserialize. Với Jackson polymorphism, tránh bật default typing rộng hoặc chấp nhận `@class` bất kỳ từ untrusted JSON; có allowlist và modules đã kiểm thử.

### 20.3. Không mang secrets/PII trong tags/logs

Không log:
- Giá trị cookie `SESSION`/`JSESSIONID`.
- Raw SecurityContext/Authentication.
- Redis session payload hoặc serialized Java bytes.
- Refresh/access tokens, password, PII, cart data nhạy cảm.
- Unknown raw JSON từ clients.

Metrics nên dùng **schemaVersion, deployment version, result=success/failure, reason code hữu hạn, store type** làm dimensions có giới hạn; không dùng session ID/user ID làm low-cardinality tags.

## 21. Quan sát sức khỏe session trong rollout

Đề xuất thu thập những tín hiệu:

| Metric/log | Gợi ý tag | Ý nghĩa |
|---|---|---|
| `session.decode.total` | format=1/2/unknown, appVersion | Reader đang gặp phiên bản nào |
| `session.decode.errors` | reason=bad_json/class_missing/uid_mismatch | Lỗi không tương thích cần rollback/fix |
| `session.write.total` | writerSchema=1/2 | Có writer V1 còn hoạt động không |
| `session.schema.downgrade.blocked` | from=2,to=1 | Phát hiện writer cũ làm mất field |
| `session.migration.total` | from=1,to=2,result | Tiến độ read repair/migration |
| `session.redis.errors` | operation=read/write/timeout | Lỗi kho session, khác schema incompatibility |
| `session.auth.failures` | reason=principal_decode/expired/invalid | Không nhầm lỗi auth với cart |
| `session.size.bytes` | histogram/percentiles | Tránh session graph phình lớn |
| `session.ttl.remaining` | bucketed/aggregated | Theo dõi data retention/expiry |
| `http.server.requests` | URI template/status/outcome | Tác động lên HTTP client |
| `session.concurrent.conflicts` | operation=cart_mutate | Detect lost updates nếu có revision/CAS |

**Điều quan trọng nhất:** tách **Redis unavailable** khỏi **không hiểu schema**. Nếu mọi V2 request báo mất session, có thể do V2 dùng namespace khác, không phải JSON decode. Nếu chỉ sessions tạo trước deploy lỗi, có thể do class/serializer incompatibility.

Những metrics này là **tên gợi ý cần tự instrument**, không phải tất cả có sẵn từ Spring Boot. Tracing với Actuator/Micrometer cần dependency/exposition phù hợp; không tự động đưa thông tin attribute/session ID vào span.

### 21.1. Đặt rollback thresholds dựa trên người dùng

Không chỉ quan sát `HTTP 5xx rate`. Một app có thể catch deserialization exception rồi tạo cart trống, trả HTTP 200, khiến dashboard nhìn “success” nhưng khách hàng mất dữ liệu.

Vì vậy đặt SLI/SLO:
- Tỷ lệ người dùng phải login lại ngay sau rollout.
- Tỷ lệ cart reset/empty bất ngờ.
- Tỷ lệ session decode lỗi theo binary version.
- Tỷ lệ missing/invalid SecurityContext.
- Concurrency conflicts/lost updates.
- Redis p95/p99 latency, availability và connection pool.
- Support complaints/checkout regressions (không dùng PII labels).

## 22. Troubleshooting lỗi giữ session giữa nhiều phiên bản

| Triệu chứng | Nguyên nhân có thể | Hướng chẩn đoán |
|---|---|---|
| Đổi pod là phải login lại | In-memory sessions, sticky không ổn | Kiểm tra Spring Session repository thật/cookie |
| Có Redis nhưng vẫn mất session | Namespace/Redis DB/cluster/cookie mismatch | So sánh app config, Redis key prefixes và cookie attributes |
| `InvalidClassException` | JDK UID/field graph không tương thích | Giữ legacy class, contract test fixture, migration |
| `ClassNotFoundException` khi đọc session | Class đổi package/bị xóa | Backward-compatible class adapter hoặc migration trước remove |
| `NotSerializableException` lúc save | Attribute graph chứa class không Serializable | Lưu String/DTO nhỏ, không lưu entity/proxy |
| V2 đọc V1 được nhưng V1 đọc V2 lỗi | Forward compatibility không có | Không bật writer2 khi old reader còn phục vụ |
| Rollback image xong vẫn 500 | Redis lưu bytes mới V2 | Rollback về reader B tương thích hoặc data migration |
| Cart mất coupon khi quay về pod cũ | Writer1 đọc V2 rồi ghi V1 | Writer gate/fencing, prohibit downgrade, CAS |
| Cart thêm item bị mất ngẫu nhiên | Concurrent requests lost update | Durable store revision/optimistic locking |
| V1 JSON bị parse thành cart trống | Reader default sai/missing key không validate | Explicit versioned read + validation/fail closed |
| Cookie `SESSION` biến thành `JSESSIONID` | Đổi Spring Session/container cookie resolver | Thống nhất cookie name/migration |
| Logout một pod nhưng pod khác còn login | Session store khác/invalidation/cache stale | Đồng nhất repository và auth invalidation semantics |
| Auth fail nhưng cart vẫn còn | SecurityContext/principal serializer mismatch | Kiểm tra custom principal, Security modules, fixtures |
| V2 không khởi động do Redis fail | Redis config/ACL/TLS/availability | Health/log connection, network policy, fail-safe rollout |
| Read-only request làm session version đổi | Read-repair không có write barrier | Không migrate khi old writers còn hoạt động |
| JSON serializer mới không đọc bytes cũ | Thay RedisSerializer toàn session một lần | Dual serializer/migration; không đổi trực tiếp |
| JDBC sessions không tồn tại sau switch | Chuyển Redis→JDBC không migrate | Chọn store stable hoặc plan migration |
| Session expire “ngay” sau deploy | TTL/clock/timeout/cookie max-age khác | Kiểm tra session.timeout và cookie config |
| Sticky session che lỗi khi test | Client luôn ở một backend | Test hai ports/pods bằng cùng cookie, ép route đổi |
| Nhiều 200 nhưng khách báo mất giỏ | Handler silently clears incompatible data | Metric data preservation, fail closed, QA ở business layer |
| V2-only feature hiển thị trước writer2 | Feature flag thiếu gate | Disable UI/API cho tới khi writer mode ổn định |
| Không thể bỏ V1 reader sau 30m | Sliding TTL và users còn active | Đo legacy-read, absolute expiry/migration plan |
| Chạy FLUSHALL làm mọi app logout | Nhầm key namespace với toàn Redis | Không dùng mass delete, có ownership/backup |

## 23. Lựa chọn khác khi không thể bảo đảm compatibility

Không phải hệ thống nào cũng có thể hỗ trợ hai định dạng cũ/mới song song. Một số lựa chọn được phép theo mức độ chấp nhận của sản phẩm:

**A. Controlled re-login:** nếu thay security context không thể deserialize an toàn, có thể buộc đăng nhập lại trong maintenance window với thông báo, session invalidation có chọn lọc và SLO rõ ràng. Thích hợp hơn việc vô tình login failure liên tục.

**B. Side-by-side session stores:** V1 dùng namespace A, V2 dùng namespace B; cần sticky/canary routing, cookie transition strategy, và không được giả định có state continuity. Phù hợp nếu quyết định session isolation và chấp nhận re-auth/transfer.

**C. Central session gateway/service:** ứng dụng giữ stable token hoặc session ID, dịch vụ trung tâm quản lý state với schema/version được kiểm soát. Tăng latency/dependencies nhưng giúp contracts tập trung.

**D. Stateless authentication + external business state:** dùng token theo tiêu chuẩn (kiểm tra signing/expiry/rotation) và lưu cart/workflow ở DB. Không loại bỏ mọi session-like state; refresh token/revocation, CSRF, token compatibility vẫn cần quản lý.

**E. Longer backward compatibility window:** giữ dual-reader/legacy decoder thêm vài releases; có thể tốn code nhưng thường ít rủi ro hơn mất hàng loạt sessions.

Lựa chọn phụ thuộc business cost của logout/cart loss, khả năng migration, mức độ nhạy cảm, dung lượng sessions và thời gian rollout/rollback.

## 24. Quy trình sự cố và rollback khi phát hiện lỗi sau rollout

Giả sử sau khi bật writer2, 2% người dùng bị `session.decode.errors`:

1. **Dừng mở rộng rollout** và xác định phiên bản nào đang ghi V2.
2. **Không vội rollback về A V1-only** nếu C đã ghi V2; nó có thể làm tình hình xấu hơn.
3. Giữ/đưa traffic về binary B/C **đọc được V2**, và vô hiệu feature/writes gây lỗi nếu cần.
4. Thu thập synthetic/anonymized example của format version, exception type, deployment version, namespace và connector; **không log session raw của người dùng**.
5. Kiểm tra lỗi do Redis connect, serializer, classpath, cookie hay app JSON schema.
6. Chặn writer downgrade/mixed writes khi chưa có protection.
7. Kiểm tra auth/carts quan trọng, session data loss và retry paths.
8. Nếu bắt buộc data migration, chạy trên backup/test trước, định nghĩa forward/backward conversion; có logs/metrics và rollback data.
9. Chỉ khi mọi reader/writer compatibility được kiểm chứng mới tiếp tục canary.
10. Sau sự cố, bổ sung golden binary fixtures, cross-node tests và deployment gates cho CI/CD.

**Không xóa session để làm biểu đồ lỗi giảm nếu dữ liệu có thể cứu được.** Một số lỗi nằm ở app binary V2, việc rollback về B reader-compatible có thể khôi phục ngay mà không cần đụng Redis data.

## 25. Checklist QA trước deployment

- [ ] Có inventory session attribute keys, types, serializer và owners.
- [ ] Chọn rõ store (in-memory/Redis/JDBC), namespace và cookie contract.
- [ ] V1 và V2 dùng cùng Redis/JDBC connection/schema khi định chia sẻ session.
- [ ] Không giả định sticky LB hoặc same cookie đồng nghĩa dữ liệu tương thích.
- [ ] SchemaVersion và rule validate/unknown version được định nghĩa.
- [ ] New reader đã đọc được golden payload do old binary thực tạo.
- [ ] Old/rollback reader đã đọc được tất cả các formats có thể xuất hiện sau writer switch.
- [ ] Writer V1 không thể làm mất V2-only fields hoặc đã được fence.
- [ ] Feature V2-only được gate tới sau khi writer V2 an toàn.
- [ ] Không lưu JPA entities/proxies/mutable graph lớn trong session.
- [ ] Spring Session save mode phù hợp; setAttribute sau khi mutate snapshot.
- [ ] Nếu thay serializer JDK→JSON, có dual-decode/migration hoặc controlled relogin.
- [ ] Spring Security context/principal compatibility được kiểm thử.
- [ ] Login/logout/session ID rotation và CSRF/cookie attributes nhất quán.
- [ ] Concurrent requests có strategy chống last-write-wins nếu state quan trọng.
- [ ] Có TTL/absolute retention plan, không chỉ đợi một idle timeout.
- [ ] Có cross-instance test V1→V2→V1 dùng cùng cookie và Redis thật.
- [ ] Có rollback test **sau khi V2 đã ghi** session data.
- [ ] Metrics decode/write versions, auth failures, cart loss, Redis availability.
- [ ] Không log raw cookie/session payload/token hoặc xóa cả Redis làm workaround.
- [ ] Deployment barrier/feature flags được đồng bộ, có runbook xử lý sự cố.

## 26. Câu hỏi tự kiểm tra

**1. Hai pod cùng kết nối Redis có bảo đảm session tương thích không?**  
Không. Chúng còn phải đồng nhất cookie/namespace/serializer và reader schema. Redis không tự chuyển object V1 thành DTO V2.

**2. Sticky session có tránh được mọi lỗi khi rolling deployment không?**  
Không. Pod cũ có thể chết, traffic đổi route, cookie/namespace đổi hoặc rollback xảy ra.

**3. `serialVersionUID=1L` ở cả hai class đã đủ không?**  
Không. Fully qualified class name, object graph, field types và semantic state vẫn có thể không tương thích.

**4. Vì sao V2 đọc được V1 chưa đủ để bật V2 writer?**  
Vì V1-only pod và rollback artifact có thể không đọc V2. Nếu V1 writer còn chạy, nó còn có thể downgrade và làm mất v2-only fields.

**5. Rollback V2→V1 có tự rollback Redis session bytes không?**  
Không. Redis vẫn giữ data format mà V2 đã ghi.

**6. Tại sao lưu JSON trong `String` lại dễ migrate hơn lưu DTO Java trực tiếp?**  
Vì app quản lý schemaVersion, field mapping và fallback trong JSON; không phụ thuộc class name của business DTO ở lớp session attribute. Nhưng serializer chung vẫn phải được giữ tương thích.

**7. Đổi `springSessionDefaultRedisSerializer` từ JDK sang JSON có an toàn ngay không?**  
Không. Existing JDK bytes sẽ không tự được JSON decoder đọc; cả SecurityContext cũng có thể bị ảnh hưởng.

**8. Session timeout 30m có nghĩa sau đúng 30m từ login không còn V1 session?**  
Không. Timeout nhiều trường hợp là inactivity-based, có thể được gia hạn khi user hoạt động. Cần retention/migration/metrics rõ.

**9. Vì sao `session.setAttribute` quan trọng khi dùng on-set-attribute save mode?**  
Vì nó đánh dấu attribute đã thay đổi; mutate một object cũ tại chỗ có thể không được repository save như mong đợi.

**10. Có thể bỏ V1 reader ngay khi rollout V2 đạt 100% không?**  
Chưa chắc. Store còn V1 sessions, rollback windows, background/multi-region writers và active users. Dùng metrics/retention policy để quyết định.

**11. Khi V1/V2 cùng ghi một cart, schema đúng có giải quyết mất update không?**  
Không. Concurrent writes vẫn có thể last-write-wins; cần revision/optimistic locking hoặc durable cart store cho state quan trọng.

**12. Nếu chỉ authentication state không đọc được, nên reset cart hay xóa mọi session?**  
Không nên tự quyết định. Phải xử lý auth theo fail-safe security policy, cân nhắc controlled re-login và không xóa state khác không cần thiết.

**13. MockMvc tests đã chứng minh cross-node Redis session chưa?**  
Chưa. Nó kiểm tra code/Servlet session trong test JVM. Cần Redis thật và hai processes/binaries khác nhau với cùng cookie.

**14. Phương án rollback an toàn sau khi C writer V2 đã hoạt động?**  
Rollback về một reader-compatible binary (B+ đọc V2 và bảo tồn state), hoặc có migration thực sự; không quay mù quáng về A V1-only.

## 27. Tài liệu tham khảo chính thức

1. **Spring Boot 3.3.13 — Spring Session**: auto-configuration, Servlet/Reactive stores và session timeout. https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html
2. **Spring Boot 3.3 — Common Application Properties**: `spring.session.redis.*`, `spring.session.timeout`, `server.servlet.session.*`. https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
3. **Spring Session 3.3 — Redis Configuration**: JDK serialization mặc định, `springSessionDefaultRedisSerializer`, namespace, indexed/default repository. https://docs.spring.io/spring-session/reference/3.3/configuration/redis.html
4. **Spring Session 3.3 — Spring Boot + Redis Guide**: `springSessionRepositoryFilter` và cookie/Redis lifecycle. https://docs.spring.io/spring-session/reference/3.3/guides/boot-redis.html
5. **Spring Session 3.3 — JDBC Configuration**: `SPRING_SESSION_ATTRIBUTES`, binary attribute serialization, conversion. https://docs.spring.io/spring-session/reference/3.3/configuration/jdbc.html
6. **Spring Session 3.3 — WebSession Integration**: reactive WebSession, SessionRepository-backed store. https://docs.spring.io/spring-session/reference/3.3/web-session.html
7. **Spring Framework — Web MVC Sessions**: Servlet `HttpSession` and session attributes. https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/httpsession.html
8. **Spring Security — Session Management**: session fixation, authentication context và session lifecycle. https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
9. **Oracle Java Object Serialization Specification**: stream class descriptors, compatibility và `serialVersionUID`. https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/
10. **Kubernetes — Deployments / Rolling Update**: rollout và rollback lifecycle. https://kubernetes.io/docs/concepts/workloads/controllers/deployment/

**Kết luận:** Khi V1 và V2 phục vụ traffic đồng thời, session phải được xem như **dữ liệu có schema và vòng đời triển khai độc lập với image**. Shared Redis/JDBC giúp cả hai đọc cùng key, nhưng không tự giúp code hiểu bytes cũ/mới. Hãy dùng reader hỗ trợ nhiều versions, writer policy có barrier, feature gating, golden cross-binary fixtures, kiểm thử cookie xuyên pods và rollback sau khi ghi V2. Nếu một thay đổi không thể tương thích, hãy chọn migration hoặc controlled re-login có kế hoạch — thay vì để người dùng âm thầm mất phiên.