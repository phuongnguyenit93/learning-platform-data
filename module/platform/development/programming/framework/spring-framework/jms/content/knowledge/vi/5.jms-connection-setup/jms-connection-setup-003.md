# Tra cứu ConnectionFactory được quản lý qua JNDI trong Spring JMS

## 1. Bài toán và mô hình quản lý tài nguyên

Trong ứng dụng Spring dùng **Jakarta Messaging (JMS)**, `jakarta.jms.ConnectionFactory` là điểm vào để tạo JMS connection/context. Trên một **Jakarta EE application server**, quản trị viên có thể tạo `ConnectionFactory`, cấu hình broker endpoint, xác thực, TLS, pool và khả năng tham gia transaction, sau đó **bind** đối tượng dưới một tên **JNDI**. Ứng dụng Spring chỉ cần **lookup** tên này rồi đưa factory nhận được vào `JmsTemplate` hoặc listener container.

```text
         Application server / JMS administrator
     ┌──────────────────────────────────────────┐
     │ Tạo, cấu hình và quản lý ConnectionFactory│
     │ broker / TLS / credentials / pool / JTA  │
     └─────────────────┬────────────────────────┘
                       │ bind
                       ▼
          JNDI: java:comp/env/jms/OrdersCF
                       │ lookup
                       ▼
       Spring bean: jakarta.jms.ConnectionFactory
                  /                    \
                 ▼                      ▼
             JmsTemplate           Listener container
                  \                    /
                   └── JMS provider ──┘
```

Cần phân biệt:

1. **Provision:** quản trị viên hoặc server tạo factory thực sự.
2. **Bind:** server liên kết JNDI name với factory; với `java:comp/env` có thể cần mapping resource reference.
3. **Lookup:** Spring lấy object theo tên và kiểm tra kiểu.
4. **Use:** `JmsTemplate` hoặc listener sử dụng factory để tạo/lấy connection, session, producer, consumer và gửi/nhận message.

**Tra cứu thành công không đồng nghĩa broker đang sẵn sàng**. JNDI trả về đối tượng cấu hình; mạng, authentication, authorization, pooling hay failover vẫn có thể lỗi khi JMS bắt đầu sử dụng nó. JNDI không phải một Queue/Topic và cũng không phải JMS transport.

### Lợi ích của ConnectionFactory được quản lý

- Cấu hình hạ tầng nằm ở server: thay endpoint, chứng chỉ, pool hoặc tài khoản theo môi trường mà giảm việc chỉnh sửa code.
- Container có thể cung cấp pooling, bảo mật, tích hợp transaction (JTA/XA), recovery và giám sát theo năng lực của provider.
- Spring làm việc với interface `ConnectionFactory`, giảm phụ thuộc vào constructor cụ thể của một vendor.
- Khi chạy nhiều môi trường, ứng dụng có thể dùng một tên logical resource được map tới tài nguyên khác nhau.

Những tiện ích này **phụ thuộc factory được bind**: lookup qua JNDI không tự biến một factory thường thành XA-aware hay pooled.

## 2. Chọn đúng namespace API: `jakarta.jms` và `javax.naming`

Với Java 17+, Spring Framework 6 hoặc Spring Boot 3:

```java
import jakarta.jms.ConnectionFactory;
import javax.naming.Context;
import javax.naming.InitialContext;
import javax.naming.NamingException;
```

- `ConnectionFactory` hiện thuộc **`jakarta.jms`** (Jakarta Messaging 3.x).
- `InitialContext`, `Context`, `NamingException` vẫn nằm trong **`javax.naming`** của Java SE/JDK. Việc JNDI còn tiền tố `javax` là **đúng**, không phải code legacy.
- `javax.jms.ConnectionFactory` từ JMS 2.0/Java EE 8 **không cùng kiểu** với `jakarta.jms.ConnectionFactory`. Dùng nhầm thư viện có thể khiến lookup trả một object không gán được sang interface Spring 6 mong đợi.

| Thành phần | Vai trò |
| --- | --- |
| `javax.naming.InitialContext` | Truy cập naming context và gọi `lookup("...")`. |
| `javax.naming.NamingException` | Đại diện lỗi naming/context/resource khi tra cứu. |
| `jakarta.jms.ConnectionFactory` | Factory do JMS provider triển khai, cung cấp phương thức tạo connection/context. |
| `org.springframework.jndi.JndiLocatorDelegate` | Helper của Spring để lookup có kiểu và hỗ trợ tên ENC. |
| `org.springframework.jndi.JndiObjectFactoryBean` | Đưa JNDI object thành bean Spring, hỗ trợ cache/lazy proxy. |
| `org.springframework.jms.core.JmsTemplate` | Gửi/nhận JMS bằng factory đã được cấu hình. |

JNDI lookup trả về `Object`; cần kiểm tra type, không ép cast tùy tiện. Sau lookup, factory thường được **inject dùng chung** cho nhiều thành phần; nó không phải đối tượng JMS `Connection` đang mở và interface `ConnectionFactory` không có phương thức `close()`.

## 3. Tên JNDI và phạm vi truy cập

Jakarta Messaging **không bắt buộc một tên chung** cho mọi factory do người dùng định nghĩa. Naming provider, application server và deployment configuration quyết định tên.

| Tên ví dụ | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `java:comp/env/jms/OrdersCF` | Tên trong component environment naming context (ENC). | Phải tồn tại mapping dành cho ứng dụng/component. |
| `jms/OrdersCF` | Tên logical rút gọn. | Có thể được Spring biến thành `java:comp/env/jms/OrdersCF` khi `resourceRef=true`. |
| `java:comp/DefaultJMSConnectionFactory` | Tên default JMS factory được Jakarta EE Platform quy định cho full platform phù hợp. | Chỉ dùng khi server triển khai và expose đúng resource. |
| `java:/JmsXA`, `java:/XAConnectionFactory` | Tên từng thấy ở các server tích hợp JMS/XA, và được Spring Boot thử khi tự dò. | Không phải tên portable giữa mọi server. |
| `java:app/jms/OrdersCF` | Namespace cấp ứng dụng theo cách tổ chức tài nguyên Jakarta EE. | Cần provider hỗ trợ và binding đúng scope. |

Trong bài này, giả định quản trị viên đã cấu hình **`java:comp/env/jms/OrdersCF`** trỏ tới một factory hỗ trợ Jakarta Messaging, có quyền dùng destination `orders.in`. Đây là **giả định để chạy ví dụ**, không phải mặc định mọi application server.

### `resourceRef` trong Spring

Các JNDI helper của Spring có `resourceRef` (mặc định **false**):

```text
resourceRef=true, jndiName="jms/OrdersCF"
  -> Spring lookup "java:comp/env/jms/OrdersCF"

resourceRef=false, jndiName="jms/OrdersCF"
  -> Spring lookup "jms/OrdersCF"

resourceRef=true, jndiName="java:comp/DefaultJMSConnectionFactory"
  -> Spring lookup đúng tên tuyệt đối, không thêm java:comp/env/
```

Nếu tên đã có scheme, ví dụ bắt đầu bằng `java:`, Spring không cộng tiền tố ENC lần nữa. **`resourceRef=true` chỉ biến đổi tên lookup**; nó không tự tạo factory và không thay thế bước mapping phía server.

### Có thể chạy JNDI ở ứng dụng standalone không?

Có thể nếu chủ động cung cấp **JNDI naming provider** và cấu hình `InitialContext` phù hợp. Tuy nhiên tên `java:comp/env/...` thường là context cục bộ do Jakarta EE/servlet container cung cấp, nên **chạy `java -jar` trên máy trống không tự có binding**. Tomcat thuần cũng không mặc nhiên cung cấp JMS provider/pooled factory đầy đủ; phải cấu hình tài nguyên bên ngoài hoặc chọn full Jakarta EE server có JMS.

## 4. Chuẩn bị binding và resource reference

Trước khi viết code, cần xác minh:

1. Runtime cung cấp `jakarta.jms.ConnectionFactory` tương thích với Spring 6/Boot 3.
2. Factory được tạo, đặt đúng broker endpoint, credentials, TLS và quyền, rồi bind theo tên mà ứng dụng lookup.
3. Đã khai báo/mapping `jms/OrdersCF` trong ENC nếu sử dụng `java:comp/env/jms/OrdersCF`.
4. Broker có Queue/Topic mong muốn; policy cho phép gửi/nhận.
5. Chính sách XA/JTA, pool và recovery được thống nhất với application server.

Ví dụ deployment descriptor `WEB-INF/web.xml` để khai báo resource reference trong ứng dụng servlet Jakarta EE (server có thể dùng cấu hình tương đương qua annotation/admin console):

```xml
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         version="6.0">
    <resource-ref>
        <res-ref-name>jms/OrdersCF</res-ref-name>
        <res-type>jakarta.jms.ConnectionFactory</res-type>
        <res-auth>Container</res-auth>
    </resource-ref>
</web-app>
```

Tệp trên **chỉ khai báo logical reference**; server vẫn phải map reference sang factory vật lý đã tạo. Tùy server, việc tạo factory thực hiện bằng admin console, deployment descriptor riêng hoặc resource definitions. Không lưu credentials broker trong source code chỉ để lookup được object.

Một lựa chọn khác trong Jakarta EE full platform là default name:

```java
@Resource(lookup = "java:comp/DefaultJMSConnectionFactory")
private ConnectionFactory connectionFactory;
```

Đây là ví dụ **trong một class do Jakarta EE container quản lý**, cần import `jakarta.annotation.Resource` và `jakarta.jms.ConnectionFactory`. Field injection kiểu `@Resource` của Jakarta EE hoạt động theo lifecycle của component do container quản lý; **không mặc nhiên áp dụng cho một Java object tùy ý tạo bằng `new`**.

## 5. Lookup trực tiếp bằng `InitialContext`

Tạo class `JndiConnectionFactoryLookup.java` (Java 17; dự án cần Jakarta Messaging API ở compile classpath):

```java
import jakarta.jms.ConnectionFactory;
import javax.naming.Context;
import javax.naming.InitialContext;
import javax.naming.NamingException;

public final class JndiConnectionFactoryLookup {

    private JndiConnectionFactoryLookup() {
    }

    public static ConnectionFactory lookup() throws NamingException {
        Context context = new InitialContext();
        try {
            Object resource = context.lookup(
                    "java:comp/env/jms/OrdersCF"
            );

            if (!(resource instanceof ConnectionFactory factory)) {
                throw new NamingException(
                        "JNDI resource is not a jakarta.jms.ConnectionFactory"
                );
            }
            return factory;
        } finally {
            context.close();
        }
    }
}
```

Đây là **class biên dịch được**, nhưng **không phải chương trình standalone có output cố định**: caller phải chạy trong runtime có JNDI provider và resource binding, hoặc cung cấp naming provider tương đương. Không có `main` vì mục đích của class là dùng trong một ứng dụng đã được triển khai.

Cơ chế:

1. `new InitialContext()` lấy naming environment từ runtime.
2. `lookup(name)` hỏi naming provider về object đã bind.
3. `instanceof ConnectionFactory` xác minh kiểu Jakarta JMS.
4. `context.close()` giải phóng context naming. Đối tượng factory là tài nguyên do server quản lý, vẫn có thể được Spring dùng sau lookup.

Nếu tên không tồn tại: thường gặp `NameNotFoundException`. Nếu không có JNDI environment: có thể gặp `NoInitialContextException`. Cả hai thuộc nhóm `NamingException`. **Đừng catch rồi trả `null`** khiến lỗi cấu hình bị trì hoãn tới lúc gửi message.

Trong Spring, nên cấu hình bean singleton thay cho việc tự lookup lặp lại ở từng service.

## 6. Cấu hình Spring Framework trực tiếp bằng JNDI

### 6.1. `JndiLocatorDelegate`: ngắn gọn và có kiểm tra kiểu

Tạo file `src/main/java/example/jms/JndiJmsConfig.java` trong ứng dụng có Spring Framework 6 và Spring JMS:

```java
package example.jms;

import jakarta.jms.ConnectionFactory;
import javax.naming.NamingException;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jndi.JndiLocatorDelegate;

@Configuration
public class JndiJmsConfig {

    @Bean
    public ConnectionFactory connectionFactory()
            throws NamingException {
        return JndiLocatorDelegate
                .createDefaultResourceRefLocator()
                .lookup("jms/OrdersCF", ConnectionFactory.class);
    }

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }
}
```

`createDefaultResourceRefLocator()` đặt `resourceRef=true`, nên `"jms/OrdersCF"` được tra cứu thành `"java:comp/env/jms/OrdersCF"`. Method `lookup(name, ConnectionFactory.class)` trả về đối tượng đúng kiểu hoặc ném `NamingException`. Spring fail lúc tạo bean nếu binding sai, giúp phát hiện lỗi cấu hình sớm.

Nếu muốn dùng factory chuẩn có tên tuyệt đối, **thay** body bean bằng:

```java
return new JndiLocatorDelegate().lookup(
        "java:comp/DefaultJMSConnectionFactory",
        ConnectionFactory.class
);
```

Chỉ chọn một tên đã được admin xác nhận. Đừng khai báo hai bean `ConnectionFactory` trùng vai trò khiến Spring inject mơ hồ.

### 6.2. `JndiObjectFactoryBean`: quản lý JNDI object theo kiểu `FactoryBean`

```java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jndi.JndiObjectFactoryBean;

@Configuration
public class JndiFactoryBeanConfig {

    @Bean("connectionFactory")
    public JndiObjectFactoryBean connectionFactoryFromJndi() {
        var bean = new JndiObjectFactoryBean();
        bean.setJndiName("jms/OrdersCF");
        bean.setResourceRef(true);
        bean.setExpectedType(ConnectionFactory.class);
        return bean;
    }
}
```

`JndiObjectFactoryBean` là Spring `FactoryBean`, nên bean được expose cho client là **object `ConnectionFactory` tra được**, không phải yêu cầu client thủ công gọi `getObject()`. Cấu hình này là **lựa chọn thay thế**, không đặt đồng thời với class ở mục 6.1 dưới cùng tên `connectionFactory`.

Mặc định Spring:

- `lookupOnStartup=true`: tra cứu lúc khởi tạo bean, fail sớm nếu thiếu tài nguyên.
- `cache=true`: giữ đối tượng đã tra cứu thay vì lookup lại cho mỗi lần sử dụng.
- Nếu muốn lazy lookup (`lookupOnStartup=false`) hoặc reload object (`cache=false`), cần proxy interface phù hợp; nên chỉ dùng khi runtime yêu cầu thật sự. Lazy lookup có thể làm lỗi cấu hình xuất hiện ở thời điểm gửi message thay vì startup.

JNDI bean lookup **không tự mở JMS `Connection`**, và cache một `ConnectionFactory` không có nghĩa là tự cache tất cả `Session` hay tự tạo JMS pool.

## 7. Spring Boot: thuộc tính `spring.jms.jndi-name`

Spring Boot 3 có thể cấu hình tìm `ConnectionFactory` từ JNDI khi chạy trong application server. Một số tên server-specific mà Boot có thể thử là `java:/JmsXA` và `java:/XAConnectionFactory`. Để dùng tên đã được quản trị viên provision, khai báo rõ:

```yaml
# src/main/resources/application.yml
spring:
  jms:
    jndi-name: "java:comp/env/jms/OrdersCF"
    pub-sub-domain: false
```

Khi app khởi động trong runtime có resource binding tương ứng, Boot lấy bean `ConnectionFactory` và có thể tự cấu hình `JmsTemplate`/JMS listener infrastructure theo classpath. Với cách này **không khai báo thêm bean `ConnectionFactory` thủ công** ở mục 6 nếu không có lý do cấu hình riêng. Một ứng dụng chạy standalone, thiếu JNDI context, không thể tự lookup thành công chỉ nhờ YAML trên.

### 7.1. Ví dụ ứng dụng WAR Java 17 dùng managed factory

Ví dụ này dùng **Spring Boot 3.3.x / Spring Framework 6**, triển khai trong **application server tương thích Jakarta Servlet/Jakarta Messaging**. Trước khi chạy, admin phải map `jms/OrdersCF` thành `java:comp/env/jms/OrdersCF`, bảo đảm factory kết nối broker và Queue `orders.in` tồn tại. Đường đi quan sát được: HTTP request → `JmsTemplate` → managed `ConnectionFactory` → Queue → `@JmsListener`.

Tạo `settings.gradle`:

```groovy
rootProject.name = 'managed-jndi-jms-demo'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    implementation 'org.springframework:spring-jms'

    // Runtime Jakarta EE server cung cấp JMS API/provider.
    compileOnly 'jakarta.jms:jakarta.jms-api'

    // Đóng gói WAR để triển khai vào Servlet container bên ngoài.
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Trong `src/main/resources/application.yml`:

```yaml
spring:
  jms:
    jndi-name: "java:comp/env/jms/OrdersCF"
    pub-sub-domain: false
```

Tạo `src/main/java/example/jms/ManagedJndiJmsApplication.java`:

```java
package example.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class ManagedJndiJmsApplication
        extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return builder.sources(ManagedJndiJmsApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(ManagedJndiJmsApplication.class, args);
    }
}
```

Tạo `src/main/java/example/jms/MessageEndpoint.java`:

```java
package example.jms;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo")
public class MessageEndpoint {

    private final JmsTemplate jmsTemplate;

    public MessageEndpoint(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @PostMapping(path = "/send",
                 consumes = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> send(@RequestBody String body) {
        if (body == null || body.isBlank()) {
            return ResponseEntity.badRequest().body("blank message");
        }

        jmsTemplate.convertAndSend("orders.in", body);
        return ResponseEntity.accepted().body("accepted");
    }
}
```

Tạo `src/main/java/example/jms/OrderListener.java`:

```java
package example.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(destination = "orders.in")
    public void onOrder(String body) {
        System.out.println("JMS received: " + body);
    }
}
```

**Tại sao ví dụ này thực sự dùng JNDI?** Ứng dụng **không có code tự new vendor factory**. Boot dùng `spring.jms.jndi-name` để lấy `ConnectionFactory`; `MessageEndpoint` chỉ biết `JmsTemplate`. Factory trong server quyết định endpoint/bảo mật/pooling. `OrderListener` cũng dùng hạ tầng JMS do Spring cấu hình.

### 7.2. Biên dịch và xác minh trong môi trường phù hợp

Với Gradle 8.5+ và Java 17, build WAR:

```bash
gradle clean bootWar
```

Nếu có Gradle Wrapper, dùng `./gradlew clean bootWar` trên Linux/macOS hoặc `gradlew.bat clean bootWar` trên Windows. File WAR nằm trong `build/libs/`. Triển khai WAR theo hướng dẫn của application server đã cấu hình resource mapping.

Giả sử server dùng HTTP port 8080 và context path `/managed-jndi-jms-demo`, có thể gửi message test:

```bash
curl -i -X POST \
  -H "Content-Type: text/plain; charset=UTF-8" \
  --data-binary "Xin chào JMS" \
  http://localhost:8080/managed-jndi-jms-demo/demo/send
```

Nếu JNDI lookup, Queue, broker, quyền và consumer đều hoạt động, endpoint có thể trả `202 Accepted` với body `accepted`. Nếu chính listener trong app nhận được message, log có thể xuất hiện:

```text
JMS received: Xin chào JMS
```

**Đây là output có điều kiện**, không phải kết quả đã chạy trong môi trường mẫu. Port/context path phụ thuộc server, tên Queue phải đúng, và nếu có consumer khác trên cùng Queue thì listener này không nhất thiết được giao message. Nếu thiếu JNDI binding, Spring context có thể không khởi tạo nên không có endpoint nào sẵn sàng. Chạy `main()` ngoài application server khi chưa có naming provider cũng không tự có `java:comp/env`.

Endpoint trên là mã demo học tập; môi trường thật phải yêu cầu xác thực, hạn chế quyền, dữ liệu đầu vào và chính sách chống lạm dụng trước khi cho phép gửi message.

## 8. ConnectionFactory JNDI khác với Destination JNDI

**`ConnectionFactory`** và **`Queue`/`Topic`** đều có thể là *JMS administered objects*; tuy nhiên chúng là **hai tài nguyên khác nhau**.

- Lookup `ConnectionFactory` qua `spring.jms.jndi-name` chỉ quyết định Spring tạo connection qua factory nào.
- `jmsTemplate.convertAndSend("orders.in", body)` mặc định thường giải chuỗi `orders.in` thành destination name của provider thông qua `DynamicDestinationResolver`, **không tự lấy `Queue` từ JNDI**.
- Nếu server chỉ cho phép destination đã bind dưới `java:comp/env/jms/OrdersQueue`, hãy inject `Queue` hoặc cấu hình `JndiDestinationResolver`.

Ví dụ **riêng** cho ứng dụng Spring Framework cấu hình cả hai object qua JNDI:

```java
@Bean
JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
    var destinationResolver = new JndiDestinationResolver();
    destinationResolver.setResourceRef(true);

    var template = new JmsTemplate(connectionFactory);
    template.setDestinationResolver(destinationResolver);
    return template;
}
```

Đoạn trên đặt bên trong class `@Configuration`, cần import `jakarta.jms.ConnectionFactory`, `org.springframework.jms.core.JmsTemplate` và `org.springframework.jms.support.destination.JndiDestinationResolver`. Khi gửi tới `"jms/OrdersQueue"`, resolver tra cứu `java:comp/env/jms/OrdersQueue`; phải có binding/ACL tương ứng. **Listener container** cũng cần destination resolver riêng nếu `@JmsListener(destination=...)` muốn resolve tên JNDI. Không trộn bean ví dụ này vào Spring Boot demo nếu chưa xác định rõ cách thay thế bean tự cấu hình.

## 9. Lifecycle, pooling và transaction sau lookup

### Lifecycle đúng

- `ConnectionFactory` được server quản lý thường là đối tượng dùng chung; đặt làm Spring singleton và inject tới `JmsTemplate`/container.
- `InitialContext.close()` đóng naming context; **không** thu hồi resource `ConnectionFactory` từ server.
- Đừng tự gọi destroy/unbind trên resource của server khi application shutdown. Đóng các JMS connection/session **do chính mình tạo** theo quy tắc JMS; các helper Spring thường quản lý lifecycle tương ứng.
- `JndiObjectFactoryBean` cache object lookup không đồng nghĩa cache session. Tương tự, một factory managed có thể đã dùng pool; không tự bọc thêm `CachingConnectionFactory`/pool nếu chưa xác minh tính tương thích với container và transaction.

### Transaction là trách nhiệm riêng

Một factory trả qua JNDI có thể hỗ trợ JTA/XA, **nhưng lookup qua JNDI không tự bảo đảm** DB và JMS tham gia một transaction nguyên tử. Phải kiểm tra transaction manager, cách Spring sử dụng connection/session, server enlistment và listener ack/commit.

Ví dụ một handler nhận message rồi ghi database, sau đó ứng dụng chết trước khi JMS acknowledge: message có thể bị **redelivery** dù DB đã ghi. Nên có event ID nghiệp vụ ổn định và idempotency/inbox khi cần. Không suy diễn đảm bảo *exactly once* cho HTTP/DB side effects từ việc dùng JNDI factory.

### Hai kiểu hỏng khác nhau

```text
A. JNDI layer:
  NoInitialContext / NameNotFound / wrong Java type

B. JMS layer sau lookup:
  broker unreachable / wrong credential / SSL / pool exhaustion
  destination missing / denied / transaction rollback / redelivery
```

Một factory lookup thành công **chưa kiểm chứng** connect/send/receive; muốn biết hệ thống sẵn sàng phải thực hiện smoke test có destination/permission phù hợp.

## 10. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `NoInitialContextException` | Ứng dụng chạy ngoài naming provider/container hoặc thiếu JNDI environment. | Xác nhận runtime; không giả định `java:comp/env` tồn tại trong `java -jar`. |
| `NameNotFoundException` | Tên sai, resource-ref chưa map, sai application scope, sai `resourceRef`. | Kiểm tra tên đã bind và scope theo admin console / deployment config. |
| `NamingException` hoặc Spring `BeanCreationException` | Không thể lookup vì cấu hình naming/quyền/lifecycle. | Xem **root cause** trong stack trace và server naming log. |
| `ClassCastException`/type mismatch | Binding sai loại hoặc trộn `javax.jms` với `jakarta.jms`. | Kiểm tra interface, classloader, version API/provider. |
| `NoClassDefFoundError` (JMS API) | Thiếu API JMS ở runtime hoặc xung đột dependency/server module. | Kiểm tra Spring Boot WAR, server Jakarta Messaging và dependency tree. |
| Lookup OK nhưng send fail | Broker down, tài khoản/TLS sai, pool cạn, Queue/Topic không hợp lệ. | Kiểm tra broker health, ACL, endpoint, pool và vendor JMS log. |
| App A thành công, app B thất bại | ENC khác nhau, principal hoặc resource mapping khác. | So sánh deployment/role/binding của đúng application. |
| Đã đổi JNDI binding nhưng app dùng resource cũ | Lookup object đã được cache; cần redeploy hoặc cấu hình refresh theo vendor. | Kiểm tra `cache`, `lookupOnStartup` và lifecycle; không vô cớ tắt cache. |

**Thứ tự xử lý hợp lý:** đọc JNDI name thực tế → xác minh resource được bind → xác minh kiểu trả về là `jakarta.jms.ConnectionFactory` → thử tạo connection/gửi test với Queue được cấp quyền → kiểm tra transaction, concurrent consumers, failover và tài nguyên pool.

**Bảo mật:** Không nhận tên JNDI tùy ý từ HTTP input hay dữ liệu không tin cậy rồi thực hiện lookup; không đổ nguyên JNDI environment, password hoặc message body nhạy cảm vào log. Dùng các tên cấu hình đã được allowlist và nguyên tắc least privilege cho ứng dụng.

## 11. Kiểm thử, triển khai và ranh giới trách nhiệm

**Unit test:** chỉ test logic của service dùng `JmsTemplate` hoặc interface publisher do ứng dụng định nghĩa bằng mock/test double. Không bắt unit test phải dựng application server/JNDI provider để kiểm tra phương thức nghiệp vụ.

**Integration test:** deploy trên server thật hoặc môi trường đủ tương đương để kiểm chứng JNDI binding, `jakarta.jms` compatibility, quyền, pooling, transaction và destination. Nếu dùng mock JNDI context, test chỉ xác nhận tên/type lookup, không thể chứng minh XA/JTA hoặc behavior của server thật.

**Ở production**, tên binding nên được cấu hình ngoài mã nguồn, quản lý theo deployment; admin cung cấp certificate/credentials; quan sát pool exhaustion, broker health, latency và message retry. Với remote JNDI provider bên ngoài server, việc thiết lập `Context.INITIAL_CONTEXT_FACTORY`/`Context.PROVIDER_URL` cần theo vendor docs và được bảo vệ an toàn. Không tự coi remote JNDI là tương đương ENC của Jakarta EE.

| Môi trường | Lựa chọn hợp lý |
| --- | --- |
| Spring Boot trong Jakarta EE app server có factory đã bind | `spring.jms.jndi-name` và `JmsTemplate` tự cấu hình. |
| Spring Framework thuần | Bean `ConnectionFactory` qua `JndiLocatorDelegate` hoặc `JndiObjectFactoryBean`. |
| Jakarta EE component được container quản lý | `@Resource(lookup="...")` hoặc `InitialContext`. |
| Standalone app không có JNDI naming provider | Cấu hình client/provider `ConnectionFactory` trực tiếp; chỉ dùng JNDI khi có provider/binding thật. |
| Nhiều factory | Đặt bean names rõ, inject `@Qualifier`; tránh nhầm transaction domain. |

## 12. Tự kiểm tra kiến thức

**Câu 1:** Vì sao `java:comp/env/jms/OrdersCF` có thể lookup trong server nhưng lỗi ở một JVM Java SE độc lập?

**Đáp án:** ENC thường được container cung cấp và bind trong scope ứng dụng; Java SE không tự có provider/binding đó.

**Câu 2:** Spring `resourceRef=true` và `jndiName="jms/OrdersCF"` dùng tên cuối cùng nào?

**Đáp án:** `java:comp/env/jms/OrdersCF`; điều này không tự tạo factory.

**Câu 3:** Vì sao phải import `jakarta.jms.ConnectionFactory` nhưng vẫn là `javax.naming.InitialContext`?

**Đáp án:** Jakarta Messaging đã đổi namespace; JNDI vẫn là API `javax.naming` trong JDK.

**Câu 4:** Lookup thành công có chứng minh broker sẵn sàng, transaction XA và destination tồn tại không?

**Đáp án:** Không. Phải kiểm tra từng điều kiện ở JMS/server runtime.

**Câu 5:** Chỉ cấu hình JNDI `ConnectionFactory` có khiến annotation `@JmsListener(destination="jms/OrdersQueue")` tự lấy `Queue` từ JNDI không?

**Đáp án:** Không. Destination resolution cần cấu hình `JndiDestinationResolver` cho listener container hoặc inject destination tương ứng.

**Câu 6:** Khi managed factory đã pooled/XA, có nên bọc tự động thêm một pool khác?

**Đáp án:** Không mặc định. Cần xét lifecycle, session/connection caching, transaction enlistment và chính sách vendor trước.

## 13. Tài liệu tham khảo

- [Jakarta Messaging: ConnectionFactory API](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/jms/connectionfactory)
- [Jakarta EE Tutorial: JMS administered objects và JNDI](https://jakarta.ee/learn/docs/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html)
- [Spring Framework: Using JMS / Connections](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework 6.2: JndiLocatorDelegate](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jndi/JndiLocatorDelegate.html)
- [Spring Framework 6.2: JndiObjectFactoryBean](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jndi/JndiObjectFactoryBean.html)
- [Spring Boot: JMS và `spring.jms.jndi-name`](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html)
- [Java SE 17: InitialContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/InitialContext.html)

**Ghi nhớ:** Application server **tạo và bind** JMS factory; Spring **lookup đúng JNDI name** để lấy **`jakarta.jms.ConnectionFactory`**; sau đó `JmsTemplate` và listener mới **dùng factory để giao tiếp với provider**. Mỗi bước có lỗi và trách nhiệm riêng.
