# Cân bằng tải, giữ phiên trên một nút và kho phiên dùng chung trong Spring Boot

## 1. Vấn đề: một người dùng có thể đi qua nhiều instance

Khi Spring Boot chỉ chạy trên **một JVM**, ứng dụng Servlet thường lưu `HttpSession` của người dùng trong bộ nhớ của web server. Browser nhận một **session cookie** chứa ID; ở request tiếp theo, server tra ID để tìm các thuộc tính như giỏ hàng tạm, dữ liệu form wizard hoặc `SecurityContext` nếu hệ thống xác thực sử dụng session.

Khi triển khai **nhiều instance** phía sau load balancer (LB), các request của cùng browser có thể được chuyển đến những JVM khác nhau. Nếu trạng thái phiên chỉ ở RAM của từng JVM, node B không tự biết dữ liệu đã tạo ở node A.

~~~text
Browser (giữ session cookie)
             |
             v
       Load balancer
         /       \
        v         v
   Spring A     Spring B
   RAM: S123    RAM: không có S123
   cart=3       không có cart
~~~

Đây là vấn đề **phân phối session state**, không phải lỗi cookie hay một controller `@GetMapping` cụ thể. Có hai hướng giải quyết điển hình:

1. **Giữ phiên trên một nút (sticky session, session affinity):** LB cố đưa các request cùng client/session về lại node A. Session vẫn nằm trong RAM A.
2. **Kho phiên dùng chung (shared/distributed session store):** A và B cùng đọc/ghi session qua Redis hoặc JDBC bằng một ID. Request có thể đến bất kỳ node nào phù hợp.

Hai lựa chọn có thể kết hợp nhưng giải quyết các vấn đề khác nhau. Sticky session là **quy tắc định tuyến**; shared store là **cách lưu dữ liệu**. Không nên đồng nhất "có sticky" với "session được sao lưu và tự failover".

Bài này xét chủ yếu Spring Boot 3.x + Spring MVC/Servlet (`HttpSession`), sau đó phân biệt riêng Spring WebFlux (`WebSession`).

## 2. HTTP cookie mang gì, session được lưu ở đâu?

Trong mô hình session phía server:

~~~text
Response sau khi tạo session:
Set-Cookie: JSESSIONID=<opaque-id>; Path=/; HttpOnly

Request tiếp theo:
Cookie: JSESSIONID=<opaque-id>

Server:
ID từ cookie -> session repository -> attribute map + thời hạn
~~~

`JSESSIONID` thường là tên cookie mặc định của servlet container khi dùng `HttpSession` cục bộ. **Spring Session** với cookie resolver mặc định thường dùng tên **`SESSION`**. Tên thực tế có thể được tùy chỉnh và không phải tiêu chí quyết định session đang lưu ở đâu: hãy xác minh `Set-Cookie` và cấu hình đang chạy.

Thông thường cookie **chỉ chứa session ID** (chuỗi khó đoán), còn thuộc tính session nằm trong RAM/container hoặc trong kho Redis/JDBC. Không trộn với một thiết kế khác là lưu toàn bộ trạng thái đã ký/mã hóa trong cookie; bài này tập trung **server-side sessions**.

Dữ liệu đi theo các tầng:

1. Browser nhận `Set-Cookie` khi ứng dụng tạo session.
2. Browser gửi `Cookie` ở request sau nếu domain, path, Secure, SameSite và các quy tắc trình duyệt cho phép.
3. LB quyết định route tới A hoặc B (có hoặc không affinity).
4. Node được chọn giải quyết ID ở container-local session manager hoặc shared repository.
5. Server cập nhật/đọc thuộc tính và có thể làm mới thời hạn hoạt động.

**Cookie không gắn với port.** Với cùng hostname `localhost`, hai URL `http://localhost:8081` và `http://localhost:8082` có thể cùng nhận cookie có Domain/Path phù hợp; đây là cơ sở để thí nghiệm hai node. Nhưng `localhost` và `127.0.0.1` là hai host khác nhau đối với cookie. Ở hệ thống thật, cookie domain/path và cấu hình LB/HTTPS phải nhất quán.

## 3. Không có sticky session và không có shared store sẽ xảy ra gì?

Giả sử một user đang làm checkout, node A lưu `cartSize=3` trong `HttpSession` cục bộ:

~~~text
T1 Browser -> LB -> A: Cookie=S123, A đọc cartSize=3
T2 Browser -> LB -> B: Cookie=S123, B không có S123
T3 B tạo session mới hoặc xử lý như chưa đăng nhập
T4 Browser trở lại A hoặc B: trạng thái có thể chập chờn
~~~

Tùy cấu hình, node B có thể sinh session/cookie khác, request không được xác thực, giỏ hàng biến mất hoặc dữ liệu form quay về ban đầu. Ngay cả khi LB dùng round-robin và hai node đều "healthy", **trạng thái chưa chắc nhất quán**.

Lỗi biểu hiện có thể là:

- Người dùng thỉnh thoảng bị logout hoặc phải login lại.
- Giỏ hàng/thông báo session thay đổi theo lần refresh.
- Tác vụ nhiều bước mất trạng thái giữa request.
- CSRF token/session-based security context không khớp sau khi đổi node.
- Test một instance luôn pass, test qua LB nhiều instance lúc pass lúc fail.

Điểm kiểm tra đầu tiên không phải sửa cookie trước: hãy ghi nhận **node xử lý**, cookie session ID đã gửi và backend repository có session ID đó không (không log nguyên giá trị ID vào log công khai).

## 4. Sticky session: giữ request về một node

**Session affinity** là khả năng LB nhớ/ổn định lựa chọn backend cho một client theo một khóa nào đó. LB có thể dùng:

- Cookie affinity của **chính LB**: LB phát cookie routing riêng, ví dụ biểu thị backend hoặc mapping. Không nhất thiết là `JSESSIONID` hay `SESSION`.
- Hash theo source IP: request từ cùng IP thường về cùng node.
- Hash theo một thuộc tính đã chuẩn hóa, hoặc lookup ID qua một cơ chế LB hỗ trợ.

~~~text
Browser cookie affinity -> LB
                            |
                            +--> A (gần như mọi request của client này)
                            |
                            +--> B (nhận client khác)
RAM A: phiên user1, user2
RAM B: phiên user3, user4
~~~

Sticky có thể cho hệ thống dùng **local `HttpSession`** hoạt động trong một khoảng thời gian vì request quay lại nơi có dữ liệu. Chi phí triển khai ban đầu tương đối thấp và không phải gọi shared store mỗi request. Tuy nhiên nó tạo **ràng buộc client ↔ node**:

- **Node A chết/restart:** A mất RAM; LB phải chuyển tới B nhưng B không có session cục bộ của A. User có thể mất trạng thái hoặc login lại.
- **Scale in/rolling deploy:** drain node và kết thúc kết nối không có nghĩa session RAM đã được di chuyển sang node khác.
- **Mất cân bằng tải:** một node có nhiều client "nặng" vẫn quá tải dù node khác còn rảnh. Affinity theo source IP đặc biệt kém công bằng sau NAT, proxy hoặc mạng di động.
- **Thay IP/cookie routing:** user có thể đến node khác và mất session.
- **Multi-region:** một phiên gắn vào một node/zone là hạn chế lớn nếu phải điều hướng vùng hoặc failover.
- **Tác vụ nền:** sticky không chuyển object trong RAM, thread đang chạy, WebSocket hay upload dở dang sang node khác.

Đừng xem sticky session là khả năng chịu lỗi. Trong trường hợp A chết, nó chỉ xác định cố gắng route về A trước khi LB biết A chết; **không cung cấp dữ liệu cho B**.

### Ví dụ NGINX `ip_hash` minh họa affinity

~~~nginx
upstream spring_nodes {
    ip_hash;
    server 127.0.0.1:8081;
    server 127.0.0.1:8082;
}

server {
    listen 8090;

    location / {
        proxy_pass http://spring_nodes;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
~~~

`ip_hash` là **affinity theo IP**, không phải sticky cookie per-user. Khi nhiều browser sau NAT có cùng IP, chúng có thể cùng dồn vào một node; khi IP nguồn thay đổi, backend có thể thay đổi. Chính sách sticky cookie của các LB/cloud platform khác cần cấu hình theo sản phẩm của nhà cung cấp, không suy diễn từ ví dụ này.

Chỉ tin forwarded headers từ các reverse proxy được kiểm soát. Không dùng `X-Forwarded-For` client gửi trực tiếp để xác thực danh tính người dùng. Đặt health-check, timeout, retry và connection draining phù hợp với khả năng nhận request đã commit.

## 5. Shared session store: nhiều instance dùng chung một phiên

Thay vì lưu mọi thuộc tính trong JVM:

~~~text
 Browser --Cookie: SESSION=S123-->
                   Load balancer
                      /    \
                     v      v
                Spring A  Spring B
                     \      /
                      v    v
                 Redis / JDBC
                key S123 -> attributes
~~~

Node A nhận `SESSION=S123` thì đọc session từ repository; request sau đến B cũng truy xuất cùng ID. Nếu A hỏng **sau khi trạng thái đã được lưu thành công vào store**, B có thể tiếp tục xử lý dựa trên dữ liệu persisted đó.

Spring Session cung cấp abstraction thay thế repository phiên:

- Với **Servlet**, tích hợp `HttpSession` qua filter, giúp phần lớn controller/service đang dùng `HttpSession` không phải tự chuyển sang Redis API.
- Với **WebFlux**, có hỗ trợ `WebSession` thông qua reactive session repository.
- Redis phù hợp truy cập phiên tần suất cao và có TTL; JDBC có thể thuận tiện nếu muốn khai thác hạ tầng relational DB và mô hình transaction/quản trị khác.
- Dùng store chung **không làm tất cả trạng thái ứng dụng trở thành phân tán**. Các cache JVM, in-memory locks, singleton mutable field, file tạm và connection WebSocket vẫn riêng mỗi node.

Lợi ích chính: **đổi node mà không mất phiên đã được lưu**, hỗ trợ rollout/scale linh hoạt hơn, giảm phụ thuộc affinity. Chi phí: mọi node phụ thuộc độ sẵn sàng, độ trễ, serialization, bảo mật và quản trị của session store.

## 6. So sánh kiến trúc: Local, sticky và shared store

| Tiêu chí | Local session + không sticky | Local session + sticky | Shared Redis/JDBC + LB tùy node |
| --- | --- | --- | --- |
| Các request của một user đến node khác | Dễ mất/trượt trạng thái | Bình thường cố tránh, nhưng vẫn có thể xảy ra | Vẫn có thể đọc session đã lưu |
| Node chứa phiên chết | Phiên RAM biến mất | Phiên RAM biến mất | Phiên có thể tiếp tục nếu store và bản ghi còn |
| Phụ thuộc kho session bên ngoài | Không | Không | Có |
| Scale in/rolling deploy | Dễ gây mất session | Cần drain/chính sách affinity; mất session khi A biến mất | Ít ràng buộc node hơn |
| Cân bằng tải các request | Linh hoạt nhưng state sai | Có nguy cơ lệch tải | Linh hoạt hơn |
| Chi phí read/write store | Chủ yếu RAM | Chủ yếu RAM | Network + serialization + storage |
| Dữ liệu khi process restart | Mất nếu không có persistence đặc biệt | Vẫn mất | Còn trong thời hạn store nếu lưu thành công |
| Đồng thời cập nhật cùng session | Có nguy cơ race trong một JVM | Có nguy cơ race trong một JVM | Có thêm nguy cơ lost update giữa node |
| Mức độ triển khai | Đơn giản nhất cho single node | Cần LB affinity | Cần library, store HA và vận hành |

**Không có lựa chọn tối ưu tuyệt đối.** Nếu một ứng dụng nhỏ chỉ có một instance và chấp nhận mất session lúc restart, local đủ dùng. Nếu ứng dụng nhiều instance và có yêu cầu failover/rollout, shared store thường là hướng phù hợp hơn. Sticky có thể dùng như lựa chọn tạm hoặc tối ưu định tuyến, nhưng không thay shared storage khi cần giữ phiên qua node failure.

Một phương án khác là kiến trúc **stateless** (ví dụ access token được kiểm tra độc lập), song nó không tự giải quyết lưu giỏ hàng, revoke token, CSRF, refresh token hoặc workflow state. Chọn mô hình dựa trên hợp đồng nghiệp vụ và bảo mật.

## 7. Spring Boot Servlet: từ `HttpSession` cục bộ sang Spring Session + Redis

### 7.1. Ví dụ ứng dụng một mã nguồn, chạy hai instance

Ví dụ Spring Boot 3.3.x + Java 17+, Spring MVC, embedded Tomcat. Controller tăng biến đếm `visits` trong session và trả cả node đang xử lý. Mục tiêu là **quan sát routing và persistence**, không dùng counter này làm chức năng thương mại có yêu cầu giao dịch nguyên tử.

Cấu trúc dự án:

~~~text
session-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/session/SessionLabApplication.java
    └── resources/application.properties
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'session-lab'
~~~

`build.gradle` — **pha 1: local session**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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

tasks.named('bootJar') {
    archiveFileName = 'session-lab.jar'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8080
server.servlet.session.timeout=30m
~~~

`src/main/java/demo/session/SessionLabApplication.java` — **Java 17+ chạy được**:

~~~java
package demo.session;

import jakarta.servlet.http.HttpSession;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SessionLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionLabApplication.class, args);
    }
}

@RestController
class VisitController {
    private final String node;

    VisitController(@Value("${demo.node-id:local}") String node) {
        this.node = node;
    }

    @GetMapping("/visit")
    VisitReply visit(HttpSession session) {
        Object current = session.getAttribute("visits");
        int next = current instanceof Integer count ? count + 1 : 1;
        session.setAttribute("visits", next);
        return new VisitReply(node, session.getId(), next);
    }

    @PostMapping("/logout-demo")
    void invalidate(HttpSession session) {
        session.invalidate();
    }

    record VisitReply(String node, String sessionId, int visits) {
    }
}
~~~

Giải thích:

1. `HttpSession` do Spring MVC/Servlet cung cấp. Lần đầu client chưa có session hợp lệ, container tạo session mới; `session.setAttribute` lưu số lượt truy cập.
2. `@Value("${demo.node-id:local}")` lấy nhãn node từ command line; đây **chỉ là nhãn chẩn đoán**, không phải cấu hình route của LB.
3. `session.getId()` được trả về **chỉ để quan sát trong bài lab**. **Không trả session ID trong JSON ở production**, vì ID là credential dạng bearer cho phiên và có nguy cơ session hijacking nếu lộ.
4. `POST /logout-demo` minh họa gọi `invalidate()`. Trong ứng dụng có Spring Security, hãy dùng logout flow chính thức để dọn authentication, CSRF, cookie và các state liên quan đúng cách.
5. Counter kiểu `Integer` dễ lưu trong Redis. Ở production, lưu session càng gọn càng tốt và thiết kế cập nhật đồng thời nếu yêu cầu đúng tuyệt đối.

### 7.2. Chạy hai node từ cùng executable JAR

Build một lần:

~~~bash
./gradlew clean bootJar
~~~

Mở **hai terminal riêng**, chạy cùng JAR với port và nhãn khác nhau:

~~~bash
# Terminal A
java -jar build/libs/session-lab.jar --server.port=8081 --demo.node-id=A
~~~

~~~bash
# Terminal B
java -jar build/libs/session-lab.jar --server.port=8082 --demo.node-id=B
~~~

Với hai JVM có container session manager riêng, các thuộc tính `HttpSession` không được tự đồng bộ. **Không** chỉ dựa vào việc cả hai được build từ một JAR để suy ra chúng dùng chung RAM/session.

Dùng cURL kiểm tra, giữ cookie của lần đầu và gửi nguyên cookie đến B:

~~~bash
# Lần 1 đến A: lưu cookie vào file riêng
curl -s -c cookies.local.txt http://localhost:8081/visit

# Lần 2 đến A: gửi cookie đã lưu
curl -s -b cookies.local.txt http://localhost:8081/visit

# Gửi CÙNG cookie session của A đến B
curl -s -b cookies.local.txt http://localhost:8082/visit
~~~

Các response **minh họa** (ID ngẫu nhiên, không cố định):

~~~json
{"node":"A","sessionId":"id-on-A","visits":1}
~~~

~~~json
{"node":"A","sessionId":"id-on-A","visits":2}
~~~

~~~json
{"node":"B","sessionId":"new-id-on-B","visits":1}
~~~

Cùng cookie của A đến B nhưng B không có session RAM tương ứng nên tạo session mới hoặc xử lý request không có session phù hợp. Trong lab, `@GetMapping` nhận `HttpSession` nên ứng dụng tạo một phiên mới. Nếu có LB sticky đưa request về A, bạn sẽ thấy `visits` tiếp tục tăng — **miễn A vẫn sống và cookie affinity còn hiệu lực**.

CURL chỉ gửi session cookie cho cùng host/path phù hợp; lệnh dùng `localhost` ở cả hai port, không đổi sang `127.0.0.1`. Khi test, không thêm `-c cookies.local.txt` cho lệnh gửi tới B nếu muốn giữ nguyên cookie A để tiếp tục kiểm chứng sau đó.

## 8. Pha 2: dùng Redis làm kho phiên chung

### 8.1. Thêm Spring Session và Redis cho Spring Boot 3.3.x

Trong **cùng `build.gradle`** của pha 1, thay block dependencies bằng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.session:spring-session-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Spring Boot quản lý phiên bản tương thích cho Spring Session/Spring Data Redis. `spring-boot-starter-data-redis` mang theo Redis client/infrastructure (Lettuce theo mặc định); `spring-session-data-redis` cung cấp repository và filter session.

**Lưu ý phiên bản:** tài liệu Spring Boot 4.x hiện có starter tên `spring-boot-starter-session-data-redis`, nhưng ví dụ **Spring Boot 3.3.x** này dùng dependency `org.springframework.session:spring-session-data-redis` theo hệ 3.x. Đừng copy tên starter của một major release khác vào build cũ nếu chưa kiểm tra tương thích.

Trong cấu hình Spring Boot cho Servlet, việc thêm đúng Spring Session module thường cho phép **auto-configuration** session Redis. Không cần bắt buộc thêm `@EnableRedisHttpSession`. Nếu chủ động dùng annotation cấu hình repository, một phần Spring Boot auto-configuration có thể lùi lại; cần thống nhất một cơ chế cấu hình để tránh xung đột.

### 8.2. Cấu hình kết nối, namespace và timeout

`src/main/resources/application.properties`:

~~~properties
server.port=8080

# Phiên hết hạn sau 30 phút không hoạt động.
spring.session.timeout=30m

# Các node phải dùng cùng Redis, database và namespace để chia sẻ phiên.
spring.data.redis.host=127.0.0.1
spring.data.redis.port=6379
spring.session.redis.namespace=demo:session-lab

# Ví dụ chế độ ghi khi repository save session.
spring.session.redis.flush-mode=on_save
~~~

Một số điểm:

- `spring.session.timeout` đặt khoảng không hoạt động tối đa cho session. Nếu property không đặt, Spring Boot Servlet có thể dùng `server.servlet.session.timeout` theo cấu hình; kiểm tra effective property trong phiên bản sử dụng.
- Namespace Redis phân biệt dữ liệu ứng dụng này với ứng dụng khác. **Hai node cần namespace giống nhau** để đọc cùng session; hai ứng dụng không được chủ ý dùng chung namespace nếu không có hợp đồng chia sẻ.
- Các node phải dùng cùng Redis **logic**, cùng database/cluster và format serialized attributes tương thích.
- `flush-mode=on_save` mô tả thời điểm thay đổi được flush vào store khi session được save (thường cuối request qua filter). Không giả định mỗi lần `setAttribute` tức thì đã có trạng thái durable trước một JVM crash.
- Đặt connection/auth/TLS/secret của Redis theo môi trường. Không commit password vào `application.properties` mẫu được lưu trong source control; dùng secret manager/config injection cho production.
- Khi Redis không khả dụng, request cần session có thể lỗi/không xác thực; **Spring Session không tự an toàn chuyển sang RAM local giữ nguyên session**.

Để chạy Redis local, có thể dùng một Redis service đã cài và lắng nghe `127.0.0.1:6379`, hoặc container lab (Docker đã được cài):

~~~bash
docker run --rm --name session-lab-redis \
  -p 127.0.0.1:6379:6379 redis:7
~~~

Lệnh trên chạy foreground; giữ terminal Redis riêng và dừng khi hoàn tất. Cổng được bind vào loopback để **không public Redis ra toàn mạng**. Không dùng cấu hình container này như khuyến nghị triển khai Redis production, vì nó chưa có xác thực, persistence, TLS, failover hay monitoring.

### 8.3. Chạy lại hai node, cùng session được đọc từ Redis

Build lại JAR sau khi thêm dependency:

~~~bash
./gradlew clean bootJar
~~~

Sau khi Redis sẵn sàng, chạy A và B với hai terminal như mục 7.2. Lưu cookie mới trong một file khác, tránh dùng lại cookie local session từ pha 1:

~~~bash
curl -s -c cookies.redis.txt http://localhost:8081/visit
curl -s -b cookies.redis.txt http://localhost:8082/visit
curl -s -b cookies.redis.txt http://localhost:8081/visit
~~~

Response **minh họa**:

~~~json
{"node":"A","sessionId":"same-shared-id","visits":1}
~~~

~~~json
{"node":"B","sessionId":"same-shared-id","visits":2}
~~~

~~~json
{"node":"A","sessionId":"same-shared-id","visits":3}
~~~

Để quan sát rõ: node được trả về thay đổi A → B → A, nhưng session ID logic và `visits` được giữ **vì cả hai node đọc/ghi cùng Redis**. Cookie name ở pha này thường là `SESSION` thay vì `JSESSIONID`; dùng `curl -i` khi cần xem `Set-Cookie` thực tế.

**Giới hạn của thí nghiệm:** đây là các request **tuần tự** để tránh vấn đề read-modify-write khi hai request cùng lúc tăng counter. Nó chứng minh chia sẻ session, chưa chứng minh tính nguyên tử của việc cộng một giá trị trong nhiều request đồng thời.

## 9. Cơ chế Spring Session thay `HttpSession` như thế nào?

Trong web Servlet:

~~~text
Browser -- Cookie: SESSION=S123 --> Node B
       |
       v
springSessionRepositoryFilter
       |
       v
SessionRepository.findById("S123")
       |
       v
Redis: attributes / lastAccessedTime / maxInactiveInterval
       |
       v
HttpServletRequest + HttpSession wrapper
       |
       v
Controller (HttpSession) -> setAttribute("visits", n)
       |
       v
Session saved according to repository/save/flush lifecycle
       |
       v
Response + cookie khi cần
~~~

Spring Session sử dụng `springSessionRepositoryFilter` thay đổi cách Servlet API lấy/lưu session. Vì vậy controller lab vẫn dùng `jakarta.servlet.http.HttpSession` như trước. **Code controller không cần trực tiếp gọi Redis** để tăng counter hoặc invalidating session.

Khi Session repository hết hạn, bị xóa, hoặc ID không tồn tại, request có thể bị xem là session mới/unauthenticated tùy endpoint và Spring Security. Shared store bảo đảm **truy xuất trạng thái đã ghi vào cùng store trong thời hạn còn hiệu lực**, không bảo đảm session tồn tại vĩnh viễn.

### Timeout: idle TTL khác cookie lifetime

- `maxInactiveInterval` / `spring.session.timeout` diễn đạt session server-side được phép không hoạt động trong bao lâu; việc truy cập/sửa session có thể làm mới hoạt động và TTL theo repository.
- Browser session cookie mặc định có thể sống tới khi đóng browser; cookie persistent có `Max-Age` riêng.
- Cookie vẫn còn **không có nghĩa** session trong Redis còn. Ngược lại cookie bị xóa nhưng store còn key sẽ không giúp browser tự tìm lại session ID.
- `SESSION` cookie với thời hạn dài hơn Redis TTL có thể dẫn tới browser gửi ID đã hết hạn; ứng dụng tạo phiên mới/yêu cầu login lại.
- Không dùng `spring.cache.redis.time-to-live` để điều khiển Spring Session TTL; đó là property của cache abstraction, **không phải** cấu hình phiên.

Với requirement bảo mật cao, có thể cần thêm **thời hạn tuyệt đối** kể từ lúc login, timeout idle, chính sách logout và session revocation ngoài cơ chế idle TTL.

## 10. Shared store không tự giải quyết mọi race condition

Giả sử hai HTTP request **đồng thời** từ cùng browser được LB gửi tới A/B:

~~~text
Redis ban đầu: visits=3
A đọc visits=3              B đọc visits=3
A tính 4                     B tính 4
A save 4                     B save 4
Kết quả có thể 4 (mất một increment), không phải 5
~~~

Session attribute **không phải distributed atomic counter**. Nếu cần chính xác tuyệt đối cho tổng đơn hàng, tồn kho, giao dịch hoặc quota, lưu dữ liệu đó ở DB/Redis primitive có thao tác nguyên tử và transaction/locking/optimistic concurrency thích hợp. Đừng dùng `HttpSession` để thực hiện business transaction xuyên node.

Một số rủi ro khác:

- **Serialization:** Redis repository phải serialize session attributes. `String`/`Integer` dễ dùng; object tùy chỉnh có thể gặp vấn đề khi thay phiên bản class giữa các node hoặc khi deserialization. Theo cấu hình mặc định Spring Session Redis thường dùng Java serialization; đánh giá độ tương thích, bảo mật serializer và chính sách triển khai đồng phiên bản. Có thể cấu hình Redis serializer JSON, nhưng không biến JSON thành “an toàn tuyệt đối” nếu type metadata/polymorphic deserialization được bật tùy tiện.
- **Save mode:** repository có các mode theo thuộc tính đã thay đổi hoặc luôn lưu; chọn theo version và semantics, không mặc định mọi mutation nội bộ của một object trong session đều được phát hiện. Cách an toàn cho demo là gọi `setAttribute` với giá trị mới.
- **Network partitions:** phiên đọc được ở node A nhưng Redis chậm/timeout có thể gây lỗi request. Cần timeout, bulkhead/circuit breaker theo đặc tính hệ thống và chính sách không cho phép bypass auth khi store lỗi.
- **Redis failover:** replication/asynchronous persistence có thể làm mất các thay đổi mới chưa replicate; “shared” không đồng nghĩa “không mất bất kỳ một lần ghi nào”.
- **Session size:** dữ liệu session lớn khiến mọi request phải truyền/serialize nhiều, tăng độ trễ và áp lực memory/Redis. Chỉ lưu metadata nhỏ, không nhét toàn bộ giỏ hàng đối tượng phức tạp, file upload hay kết quả truy vấn cồng kềnh.
- **Multi-version deploy:** node A chạy class phiên bản cũ, B chạy class mới; serialized object có thể không giải mã được. Kiểm tra backward compatibility hoặc dùng schema phiên bản độc lập class JVM.

## 11. Cookie, bảo mật, TLS và session fixation

**Session ID là bearer credential.** Ai có thể sử dụng ID hợp lệ trong đúng phạm vi cookie/session store có thể chiếm phiên nếu các biện pháp khác không ngăn chặn. Vì vậy:

1. Dùng **HTTPS** từ browser tới endpoint public; cấu hình `Secure` cho cookie ở production. Sau TLS termination, app có thể thấy HTTP nội bộ; cấu hình forwarded headers và trusted proxy đúng để server suy luận scheme/cookie security. Không để client trực tiếp giả mạo các header mà app tin.
2. Dùng `HttpOnly` để JavaScript trên trang không đọc trực tiếp session cookie; điều này **không loại bỏ tất cả rủi ro XSS**.
3. Chọn `SameSite=Lax/Strict/None` phù hợp luồng truy cập. Với `SameSite=None` trong browser hiện đại thường cần `Secure`. **SameSite không thay cơ chế CSRF defense** khi cookie tự động gửi theo request.
4. Chọn cookie `Domain` và `Path` tối thiểu cần thiết, tránh chia cookie/session cho ứng dụng hoặc subdomain không đáng tin.
5. Rotate session ID khi đăng nhập/thăng quyền để giảm session fixation; nếu có Spring Security, dùng session fixation protection và logout của framework.
6. Logout/invalidate phải xóa hoặc vô hiệu hóa **bản ghi trong shared store** và xử lý cookie; xóa cookie trên browser mà không invalidate store có thể để session cũ tồn tại tới hết hạn.
7. Không in giá trị `SESSION`/`JSESSIONID` nguyên dạng vào logs, URL, analytics, response JSON production hoặc metrics labels.
8. Redis chỉ cho các app được phép kết nối, có network isolation, ACL/auth, TLS khi cần, patch/backup/HA đúng mục tiêu. Namespace chỉ giúp phân tách key, **không phải ranh giới bảo mật thay Redis ACL**.

### Cấu hình cookie cần phù hợp phiên bản và resolver

Với Servlet container local sessions, Spring Boot có các property thuộc `server.servlet.session.cookie.*`. Khi Spring Session thay session resolver/filter, một số chi tiết cookie do **`CookieSerializer`** của Spring Session điều khiển. Đừng giả định đổi một property Tomcat sẽ luôn đổi cookie `SESSION` của Spring Session.

Ví dụ tùy chỉnh **ở lớp cấu hình Spring Session Servlet** (snippet thêm vào một class `@Configuration` của ứng dụng, không chạy độc lập):

~~~java
@Bean
CookieSerializer cookieSerializer() {
    DefaultCookieSerializer cookie = new DefaultCookieSerializer();
    cookie.setCookieName("SESSION");
    cookie.setCookiePath("/");
    cookie.setUseHttpOnlyCookie(true);
    cookie.setUseSecureCookie(true); // production HTTPS
    cookie.setSameSite("Lax");
    return cookie;
}
~~~

Cần imports `org.springframework.context.annotation.Bean`, `org.springframework.session.web.http.CookieSerializer` và `org.springframework.session.web.http.DefaultCookieSerializer`. Đoạn này phục vụ **production HTTPS**; nếu bật `Secure` rồi test bằng HTTP local, browser/cURL có thể không gửi cookie như dự kiến. Hãy thử dưới HTTPS hoặc cấu hình cho môi trường dev một cách có ý thức. Tránh tự đổi cookie name giữa hai node, vì request sẽ không mang cùng session key tới cả hai.

## 12. Session affinity là trách nhiệm LB, kho phiên là trách nhiệm ứng dụng

Sơ đồ kiến trúc:

~~~text
                    Client
                      |
             HTTPS / Set-Cookie
                      |
                      v
                Load balancer
              routing + health
                /           \
               v             v
          Spring A         Spring B
       same app/version   same app/version
               \             /
                \           /
                   Redis HA
                   same namespace
~~~

**LB không được định tuyến chỉ dựa vào việc có Redis**: routing vẫn cần health checks, retry policy, readiness, connection draining và phân phối tải. Redis không giải quyết một node bị quá tải CPU, socket quá nhiều, GC pause hay app code lỗi.

### Khi node A chết

**Chỉ sticky + local session**:

~~~text
A chết -> LB chuyển request sang B
B không thấy session RAM của A
-> phiên thường mất / user cần tạo session hoặc login lại
~~~

**Shared store, session đã được lưu thành công**:

~~~text
A chết -> LB chuyển request sang B
B đọc session ID trong Redis/JDBC
-> có thể tiếp tục dùng session đang còn hạn
~~~

Lưu ý tại thời điểm A chết, bất kỳ request/transaction chưa hoàn tất nào trên A vẫn có thể bị mất, và thay đổi session chưa flush vào store có thể không có trên B. Failover **không đồng nghĩa replay an toàn** request như thanh toán. Nghiệp vụ có side effect cần idempotency/transaction riêng.

### Rolling deployment và drain

Khi thay thế các node:

1. Đặt node cũ **not ready** để LB ngừng gửi request mới.
2. Cho request đang xử lý thời gian kết thúc (graceful shutdown) trong ngưỡng deadline đã đặt.
3. Với shared sessions, node mới dùng cùng store/namespace và schema tương thích.
4. Theo dõi tỷ lệ session miss/logout, latency của store, lỗi deserialize và error rate sau rollout.

Sticky không tự chuyển RAM phiên sang node mới; dù triển khai "zero downtime" ở network layer, user state có thể mất khi node cũ bị remove. Shared store giảm rủi ro nhưng cần bảo đảm session compatibility khi chuyển version.

### Session affinity vẫn hữu ích khi đã có Redis không?

Có thể nhưng không mặc định cần. Một số hệ thống dùng affinity để giảm thay đổi node vì các tối ưu local cache hoặc workload đặc thù, nhưng mỗi request vẫn đọc state từ shared store theo hợp đồng và cần chịu được đổi node. Nếu app chạy đúng **chỉ khi sticky**, tức là vẫn còn một phụ thuộc state cục bộ chưa xử lý; không nên coi Redis đã giải quyết hoàn toàn vấn đề.

## 13. Failover của session store cũng là bài toán riêng

Redis/JDBC là thành phần hạ tầng cần thiết. Nếu Redis là **single instance không persistence** và chết, mọi node Spring Boot đều có thể mất khả năng đọc session. Chuyển Redis sang cluster/Sentinel/managed HA tăng mức sẵn sàng nhưng phải xem:

- **Replication lag/durability:** bản ghi session vừa cập nhật có được replicate trước failover không?
- **Eviction policy và memory pressure:** Redis evict key vì hết RAM làm người dùng logout đột ngột dù chưa hết timeout; thiết kế memory/quota và eviction policy phù hợp.
- **TTL expiration:** key hết hạn hợp lệ, xóa/expire behavior có thể không tuyệt đối chính xác từng mili giây; đừng dùng TTL Redis để cam kết “logout đúng thời điểm X” cho quy tắc pháp lý mà chưa có thiết kế bổ sung.
- **Connection pool, timeout, circuit breaker:** một store bị chậm có thể khiến cả fleet web chậm; đo latency p95/p99 và tỷ lệ lỗi.
- **Backup/recovery:** phiên có thể mang dữ liệu nhạy cảm; backup phải được bảo vệ và có retention hợp lý. Khôi phục backup cũ có thể hồi sinh session mà chính sách yêu cầu đã bị invalidate, cần cân nhắc.
- **Readiness vs liveness:** lỗi Redis tạm thời không nhất thiết cần kill toàn bộ pod, nhưng node không thể phục vụ các request phụ thuộc session. Thiết kế health/readiness theo SLO và degradation policy, tránh restart storm.

Nếu Redis không thể truy cập, không nên tự “đăng nhập tạm” user từ cookie ID chưa xác minh. Với các endpoint đòi hỏi authentication, **fail closed** hoặc dùng chính sách phục hồi đã được kiểm chứng thay vì tạo quyền truy cập giả.

## 14. Quan hệ giữa sticky session và Spring Security

Khi Spring Security cấu hình login qua session, `SecurityContext` thường được lưu hoặc liên kết với server-side session. Trong multi-node local store không sticky, request sang B có thể không thấy authentication, dẫn tới 401/redirect login. Khi dùng Spring Session, dữ liệu authentication có thể được lưu trong shared repository để các node xử lý nhất quán hơn.

Nhưng **Spring Session không tự bật authentication hoặc authorization**. Cần Spring Security cấu hình filter chain, login/logout, CSRF, session fixation, concurrency control, timeouts. Với bearer-token API thuần stateless, ứng dụng có thể không dùng `HttpSession` cho authentication; khi đó đặt sticky hoặc Redis chỉ để “giữ login” có thể không đúng bài toán.

Cần cân nhắc session events (created/destroyed/expired) và concurrent-session control: một số tính năng phụ thuộc indexed repository/event processing, không mặc nhiên tương đương ở mọi repository. Nếu yêu cầu “đăng nhập chỉ một thiết bị” hoặc “admin revoke toàn bộ session”, chọn repository và event/configuration có hỗ trợ rồi test thực tế.

Không lưu một object `Authentication` tùy biến quá phức tạp mà không xét serialization và compatibility. Spring Security version và lớp domain thay đổi giữa release có thể gây lỗi deserialization khi rolling deploy.

## 15. Khác biệt với ứng dụng Spring WebFlux

WebFlux dùng **`WebSession`** của reactive web stack, không phải Servlet `HttpSession`. Bản chất cân bằng tải tương tự: session cục bộ mỗi node sẽ gặp vấn đề khi request chuyển node, còn Spring Session có thể tích hợp Redis để cung cấp distributed reactive sessions.

Đoạn minh họa đọc WebSession trong WebFlux:

~~~java
@GetMapping("/reactive-visit")
Mono<Integer> visit(ServerWebExchange exchange) {
    return exchange.getSession().map(session -> {
        Integer count = session.getAttribute("visits");
        int next = (count == null ? 1 : count + 1);
        session.getAttributes().put("visits", next);
        return next;
    });
}
~~~

Đoạn trên là **snippet** trong một `@RestController` WebFlux, không phải Java class độc lập. Nếu dùng WebFlux, khai báo dependency webflux + Spring Session Redis tương ứng và để Spring Boot auto-configure khi thích hợp, hoặc cấu hình rõ `@EnableRedisWebSession` trong trường hợp quản lý manual. **Không** bê nguyên `jakarta.servlet.http.HttpSession` vào WebFlux thuần.

Cẩn thận khi triển khai session store reactive: các thao tác I/O cần reactive repository và không `block()` trong Netty event loop. Một ứng dụng thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux` thường được Boot ưu tiên Servlet/MVC theo auto-detection; xác nhận web application type trước khi chọn giải pháp.

## 16. Kiểm thử có ý nghĩa: từ local state đến shared state

### Test A — Local, không affinity

Khởi động hai instance chưa có Spring Session/Redis (mục 7). Dùng cookie từ A gọi B:

- A lần đầu tạo local session, `visits=1`.
- A lần hai với cùng cookie tăng `visits=2`.
- B với cookie của A có thể tạo session mới, `visits=1`.

Kết quả là **hành vi đúng theo mô hình lưu RAM cục bộ**, nhưng là rủi ro khi LB round-robin.

### Test B — Sticky, local session

Đặt LB `ip_hash` hoặc sticky-cookie rule theo sản phẩm, gọi qua **một địa chỉ LB** nhiều lần với cookie jar:

~~~bash
curl -s -c cookies.lb.txt http://localhost:8090/visit
curl -s -b cookies.lb.txt http://localhost:8090/visit
curl -s -b cookies.lb.txt http://localhost:8090/visit
~~~

Quan sát thường thấy cùng node và `visits=1,2,3` nếu LB giữ affinity và không có lỗi. Tắt node đã chọn, gọi lại: LB có thể chuyển node và local state mất. Với ví dụ `ip_hash`, một IP có thể luôn đi tới A; nếu LB đổi mapping vì topology thay đổi, kết quả thay đổi theo.

**Không chạy test kill container/nút production.** Dùng lab/staging để kiểm chứng failover.

### Test C — Redis shared, không cần affinity

Khởi động cùng hai instance với Spring Session + Redis (mục 8), gọi lần lượt vào từng port, giữ cookie:

~~~bash
curl -s -c cookies.shared.txt http://localhost:8081/visit
curl -s -b cookies.shared.txt http://localhost:8082/visit
curl -s -b cookies.shared.txt http://localhost:8081/visit
~~~

Kỳ vọng `node=A,B,A` và `visits=1,2,3` với cùng session ID logic trong thời hạn còn hiệu lực. Vì backend Redis chung, không cần LB sticky cho test này.

Sau đó dừng node A, vẫn gọi node B với cookie lưu sẵn: `visits` phải tiếp tục tăng nếu trước đó đã được flush vào store và Redis còn dữ liệu. Để kiểm tra timeout, đợi hơn `spring.session.timeout` trong lab (hoặc đặt một giá trị ngắn *chỉ để test*) rồi yêu cầu tiếp, kỳ vọng session được coi là hết hạn và count reset hoặc cần login lại theo policy.

### Test D — Chạy đồng thời để phát hiện race

Gửi nhiều request cùng cookie đồng thời tới A/B và so sánh counter. Nếu kết quả thiếu lượt, đó là dấu hiệu `getAttribute` → `setAttribute` là **read-modify-write không atomic**. Không dùng counter session làm nguồn dữ liệu đúng tuyệt đối. Chuyển thành Redis atomic `INCR` hoặc business DB transaction nếu yêu cầu.

### Test E — Thử lỗi lưu trữ

Trong lab, làm Redis tạm thời không thể truy cập, rồi xem request cần session có lỗi gì và app có phục hồi sau khi Redis trở lại không. Thử rolling deploy khi node A/B khác phiên bản entity session để phát hiện serializer compatibility. Kiểm tra lỗi không làm ứng dụng vô tình bỏ xác thực hoặc để lộ stack trace/session ID.

## 17. Chẩn đoán theo triệu chứng

| Hiện tượng | Nguyên nhân có khả năng | Cách kiểm tra |
| --- | --- | --- |
| Login thành công rồi request sau bị logout ngẫu nhiên | Local session, LB phân phối sang node khác | Ghi node name, cookie name và session repository; thử cùng cookie vào từng port |
| Dùng sticky vẫn bị logout khi rolling deploy | Node cũ đã tắt, RAM session biến mất | Quan sát drain/affinity; cần shared store hoặc chính sách session migration |
| Có Redis nhưng mỗi node tạo session khác | Cookie name/path/domain lệch, Redis namespace/database khác, hoặc chưa enable Spring Session | So cấu hình effective, `Set-Cookie`, dependency, store key |
| Redis báo lỗi deserialize khi triển khai | Hai phiên bản class session attribute không tương thích | Kiểm tra serializer, schema và rolling deployment |
| Sau 30 phút user logout dù browser còn cookie | Server-side session TTL hết | Xác nhận `spring.session.timeout`, clock và last accessed time |
| Cấu hình `spring.cache.redis.time-to-live` nhưng session không đổi | Đang chỉnh TTL của cache abstraction | Dùng property session timeout tương ứng |
| Redis chạy tốt nhưng lượt truy cập counter thiếu khi tải cao | Race read-modify-write giữa hai request | Dùng atomic business store hoặc thiết kế concurrency |
| NGINX `ip_hash` dồn nhiều người về A | NAT/proxy cùng source IP | Chọn affinity khác hoặc shared store không cần sticky |
| Qua HTTPS bị loop login, localhost HTTP lại chạy | Cookie `Secure`, forwarded proto/host/path hoặc SameSite sai | Xem cookie gửi/nhận và cấu hình trusted proxy |
| Login thành công ở A, B không nhận SecurityContext | Chưa chia sẻ session/auth context, security config không đồng nhất | Kiểm tra Spring Security session config và store |
| Redis bị eviction, user logout sớm | Memory pressure/eviction policy | Xem Redis memory, key eviction, TTL và capacity |
| Redis gặp sự cố, toàn fleet lỗi | Phụ thuộc store chung không có HA/failover đúng | Kiểm tra topology, timeout, retries, readiness |

**Quy trình điều tra gợi ý:**

1. Xác nhận LB chọn node nào cho mỗi request bằng node label/trace ID.
2. Xem cookie `JSESSIONID` hay `SESSION` có được client gửi đúng domain/path/HTTPS không; tuyệt đối không dán ID thật vào ticket công khai.
3. Kiểm tra cấu hình effective của session repository ở cả hai node: local hay Spring Session; Redis endpoint, DB, namespace, serializer và timeout.
4. Đối chiếu store metrics, request logs, expiry/eviction và node restart tại thời điểm logout.
5. Chạy test thủ công có cùng cookie trên A → B để tách lỗi cookie, LB affinity và shared persistence.
6. Kiểm thử failover, rolling deploy, concurrent requests và security flows trước khi công bố rằng hệ thống đáp ứng yêu cầu HA.

## 18. Checklist kiến trúc trước khi triển khai

- **State:** Session chứa những gì? Có thực sự cần server-side session, có object nặng hoặc bí mật không?
- **Routing:** LB sử dụng round-robin, IP hash, cookie affinity hay thuật toán khác? Khi node mất readiness, request cũ được xử lý thế nào?
- **Storage:** Nếu dùng Redis/JDBC, mọi node có cùng store/namespace và có HA phù hợp SLO không?
- **Lifecycle:** timeout idle, absolute lifetime, cookie Max-Age, logout, invalidate và session fixation được định nghĩa nhất quán chưa?
- **Security:** HTTPS + Secure/HttpOnly/SameSite, CSRF, trusted proxy, session ID secrecy, authorization và Redis access control đã có chưa?
- **Consistency:** hai request cùng session có thể đến hai node đồng thời; dữ liệu cần transaction có nằm ngoài session không?
- **Serialization:** rolling deploy version mới/cũ có đọc được session attribute của nhau không?
- **Operations:** session count, session miss, Redis p95, error, eviction, memory, store failover và node distribution có monitoring/alert không?
- **Release:** có test A→B với cùng cookie, node failure, scale in và restart trong staging không?

Không dùng sticky như phương án duy nhất cho ứng dụng yêu cầu tiếp tục phiên sau node failure. Không coi Redis là “HA hoàn chỉnh” khi chính Redis hoặc serialization còn là điểm lỗi đơn.

## 19. Câu hỏi tự kiểm tra

**1.** LB phân phối request lần lượt tới A/B, hai node chỉ dùng `HttpSession` RAM. Vì sao browser có thể mất giỏ hàng?

**Đáp án:** Session attributes được lưu ở A, B không tự có chúng. Cookie ID còn tồn tại nhưng repository local của B không chứa dữ liệu tương ứng.

**2.** Bật sticky cookie ở LB có làm session chuyển từ A sang B khi A chết không?

**Đáp án:** Không. Sticky điều khiển routing, không copy session. Nếu A chết, B không đọc RAM của A.

**3.** Redis shared store với hai node chạy cùng app có cần sticky để giữ `HttpSession` không?

**Đáp án:** Thường không; cả A và B có thể đọc session đã lưu với cùng ID. Sticky chỉ là một lựa chọn route/tối ưu riêng nếu có yêu cầu.

**4.** Vì sao test Redis `visits=1,2,3` tuần tự vẫn chưa chứng minh counter an toàn khi chạy đồng thời?

**Đáp án:** Hai request đồng thời có thể cùng đọc 1, cùng ghi 2, dẫn đến lost update. Session repository không mặc nhiên là transaction business.

**5.** Browser gửi cookie `SESSION` nhưng Redis key đã hết hạn. Node B có thể tiếp tục phiên cũ không?

**Đáp án:** Không. Cookie chỉ mang ID, không giữ lại toàn bộ thuộc tính. Ứng dụng có thể tạo session mới hoặc yêu cầu login.

**6.** Một Spring Boot WebFlux dùng `HttpSession` và `spring.servlet.session.timeout` có phù hợp không?

**Đáp án:** Với WebFlux thuần, dùng `WebSession` và reactive session repository. Không áp dụng nguyên code Servlet vào WebFlux.

**7.** Nếu Redis trục trặc thì có nên cho phép request được xác thực bằng cookie ID mà không kiểm tra store?

**Đáp án:** Không; ID không thể được xác minh/giải quyết thành authentication state. Hệ thống nên fail closed hoặc có giải pháp phục hồi rõ ràng đã kiểm chứng.

**8.** Session cookie `Secure` nhưng bạn đang test qua `http://localhost`, vì sao test A→B có thể không hoạt động?

**Đáp án:** Cookie bảo mật có thể không được gửi trên HTTP tùy client và exception localhost; nên test production policy bằng HTTPS hoặc điều chỉnh cấu hình local có kiểm soát.

## 20. Tài liệu chính thức

- [Spring Boot 3.4 — Spring Session](https://docs.spring.io/spring-boot/3.4/reference/web/spring-session.html): auto-configuration session repositories, timeout và khi cấu hình thủ công làm Boot back off.
- [Spring Session 3.1 — Spring Boot Redis Guide](https://docs.spring.io/spring-session/reference/3.1/guides/boot-redis.html): dependency `spring-session-data-redis`, cấu hình kết nối Redis, `springSessionRepositoryFilter` và cookie session.
- [Spring Session — HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html): thay thế `HttpSession` qua Servlet filter, session repository và hỗ trợ cluster.
- [Spring Session — Redis Configurations](https://docs.spring.io/spring-session/reference/configuration/redis.html): namespace, serializer, RedisSessionRepository, các lựa chọn indexed repository và xử lý expiry.
- [Spring Session 3.3 — WebSession Integration](https://docs.spring.io/spring-session/reference/3.3/web-session.html): reactive `WebSession` và Redis trong WebFlux.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): session fixation protection, invalidation và chính sách authentication.

**Kết luận:** Với Spring Boot nhiều instance, **sticky session** giữ client quay lại một node nhưng không bảo toàn RAM khi node chết. **Spring Session + Redis/JDBC** lưu trạng thái phiên ra kho mà các node cùng truy cập, cho phép thay node tốt hơn. Cả hai vẫn cần đúng cookie, timeout, security, serializer, monitoring và kiểm thử failover; session không phải nơi thực hiện transaction nguyên tử của nghiệp vụ.
