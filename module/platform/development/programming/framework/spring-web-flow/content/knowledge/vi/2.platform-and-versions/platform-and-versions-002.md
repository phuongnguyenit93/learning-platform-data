# Chọn dòng Web Flow phù hợp với Java và Spring Framework

Một ứng dụng **Spring Web Flow (SWF)** thường sống qua nhiều năm: người dùng đi qua các bước nhập dữ liệu, xác nhận, chuyển nhánh và gọi subflow; máy chủ phải giữ đúng `state`, xử lý `event`, chạy `transition`, bind form và bảo vệ `flowScope` qua nhiều HTTP request. Vì Web Flow gắn chặt với **Spring MVC**, **Servlet API**, **cơ chế phiên** và các dependency Spring, chọn sai dòng phiên bản có thể khiến ứng dụng lỗi từ lúc khởi động, chưa cần chạy đến bước đầu tiên của flow.

Bài này hướng dẫn chọn dòng SWF phù hợp với **Java**, **Spring Framework**, **Spring Boot (nếu dùng)** và **Servlet/Jakarta EE**; đồng thời đưa ra quy trình kiểm tra tương thích trước khi phát triển hoặc nâng cấp một ứng dụng nhiều bước.

> **Mốc thông tin: 25/11/2026.** Các phiên bản cụ thể dùng để minh họa trạng thái phát hành ở thời điểm biên soạn. Trước khi tạo dự án mới hoặc triển khai production, kiểm tra lại tài liệu từng dòng, bản vá bảo mật và các phiên bản đã được thử nghiệm trong ứng dụng của bạn.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Chọn đúng nhánh **Web Flow 2.5.x, 3.0.x hoặc 4.0.x** dựa trên Java, Spring Framework và Servlet.
2. Giải thích vì sao Spring Boot và Spring Web Flow là **hai sản phẩm có phiên bản độc lập** dù cùng chạy trên Spring MVC.
3. Phát hiện sự khác nhau giữa namespace `javax.*` và `jakarta.*` trước khi thêm dependency.
4. Dùng Maven/Gradle kiểm tra dependency thực tế thay vì chỉ nhìn phiên bản khai báo.
5. Lập kế hoạch nâng cấp sao cho logic `state → event → transition`, binding, validation và phiên thực thi flow vẫn hoạt động.
6. Nhận diện rủi ro bảo mật và tránh giữ lại bản SWF có lỗ hổng đã biết.

## 2. Bản đồ tương thích các dòng Spring Web Flow

Các thế hệ nên được hiểu như **một tổ hợp nền tảng**, không chỉ là phiên bản một file JAR.

| Dòng SWF | Java tối thiểu | Spring Framework mục tiêu | Servlet / namespace | Phù hợp trong thực tế |
| --- | --- | --- | --- | --- |
| **2.5.x** | Java 8 | Spring Framework **5.x** | Servlet 3.1+ thuộc hệ `javax.servlet.*` | Bảo trì ứng dụng legacy Spring 5; cần xem xét nguồn bản vá và lộ trình nâng cấp |
| **3.0.x** | Java 17 | Spring Framework **6.x** | Hệ **Jakarta EE**, `jakarta.servlet.*` | Ứng dụng Spring 6, điển hình là Spring Boot 3.x |
| **4.0.x** | Java 17 | Spring Framework **7.0 baseline** | **Servlet 6.1**, `jakarta.servlet.*` | Ứng dụng Spring 7, điển hình là Spring Boot 4.x, với servlet container tương thích |

**Nguồn của các mốc kỹ thuật:** [Web Flow 2.5.1 Reference](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/), [Web Flow 3.0.2 Reference](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/), [Web Flow 4.0.2 Reference](https://docs.spring.io/spring-webflow/docs/4.0.2/reference/).

Một vài điểm đọc bảng cho đúng:

- “Java tối thiểu” là **điều kiện bắt buộc**, không phải cam kết mọi JDK mới đều đã được kiểm thử với ứng dụng của bạn. Java 21/25 có thể phù hợp với dòng yêu cầu Java 17+, nhưng vẫn phải xác minh JVM, compiler, thư viện và container thực tế.
- “Spring Framework mục tiêu” là dòng nên **ghép cùng hệ sinh thái**. Chẳng hạn tài liệu 3.0 ghi “Spring Framework 6.0 or higher”, nhưng khi Spring 7 đã có dòng Web Flow 4.0 riêng, không nên mặc định đưa SWF 3.0 vào ứng dụng Spring 7 mà bỏ qua kiểm thử.
- **Web Flow 4.0 có baseline Spring Framework 7.0 và Servlet 6.1**; không thể chỉ nâng Java từ 17 lên 21 là biến Web Flow 3.0 thành Web Flow 4.0.
- **Web Flow 2.5** thuộc thế hệ Java EE/`javax.*`. Thay namespace ở một file không làm các JAR thế hệ cũ tự tương thích với Jakarta EE.
- Nếu ứng dụng dùng **JSF**: Web Flow 3.0 yêu cầu JSF 4.0+, Web Flow 4.0 yêu cầu JSF 4.1+; ngoài MVC, còn phải kiểm tra integration JSF và implementation tương ứng.

### 2.1. Những mốc phát hành minh họa

Tại thời điểm biên soạn:

| Nhánh | Bản phát hành được dùng trong ví dụ | Điểm cần nhớ |
| --- | --- | --- |
| 2.5 | `2.5.1.RELEASE` trong tài liệu OSS; có các bản vá doanh nghiệp riêng | Bản legacy, không nên lấy làm mặc định cho dự án mới |
| 3.0 | `3.0.2` | Cập nhật bảo mật tháng 6/2026; dành cho nền tảng Spring 6 |
| 4.0 | `4.0.2` (19/11/2026) | Nhánh Web Flow 4; release này nâng dependency Spring Framework lên 7.0.11 |

Xem danh sách phát hành trực tiếp tại [spring-projects/spring-webflow/releases](https://github.com/spring-projects/spring-webflow/releases). **Phiên bản mới nhất của Spring Framework không mặc nhiên là phiên bản mới nhất được kiểm chứng với SWF**: hãy kiểm tra cả bản vá SWF và dependency tree của ứng dụng.

## 3. Sơ đồ quyết định chọn phiên bản

~~~mermaid
flowchart TD
    A["Bắt đầu: hệ thống dùng Java/Spring nào?"] --> B{"Spring Framework chính?"}
    B -->|"5.x"| C{"Có cần duy trì hiện trạng?"}
    C -->|"Có"| D["SWF 2.5.x cho legacy; kiểm tra bản vá"]
    C -->|"Có kế hoạch nâng cấp"| E["Nâng Java, Servlet, Spring trước"]
    E --> F["Chọn lại SWF theo nền mới"]
    B -->|"6.x"| G{"JDK >= 17 và Jakarta?"}
    G -->|"Có"| H["SWF 3.0.x, bản vá mới"]
    G -->|"Không"| E
    B -->|"7.x"| I{"Servlet >= 6.1?"}
    I -->|"Có"| J["SWF 4.0.x, bản vá mới"]
    I -->|"Không"| K["Nâng servlet container/Jakarta stack"]
    K --> J
    B -->|"Khác / chưa rõ"| L["Kiểm tra BOM, dependency tree, runtime"]
    L --> B
~~~

Sơ đồ dùng để xác định **ứng viên ban đầu**. Quyết định cuối cùng còn phụ thuộc đến Spring Security, JSF nếu có, template engine, thư viện validation, cấu hình flow executor, các bản vá và kết quả kiểm thử.

### 3.1. Trường hợp A — đang chạy Java 8 + Spring Framework 5

Một cổng dịch vụ nội bộ ra đời từ Spring 5 có thể dùng Web Flow 2.5 để giữ màn hình đăng ký nhiều bước hoạt động. Đây là lựa chọn **bảo trì ngắn hạn có kiểm soát**, không phải cơ sở nên sao chép sang dự án mới.

Các bước cần làm:

1. Xác định chính xác Java runtime, Spring 5.x, Servlet container và bản SWF đang có.
2. Kiểm tra các bản vá phù hợp với nhánh legacy, nhất là các lỗ hổng đã công bố.
3. Kiểm tra endpoint thực thi flow, CSRF, binding và session timeout.
4. Lập lộ trình **Java 17 + Spring 6 + Jakarta + Web Flow 3** hoặc **Spring 7 + Web Flow 4** nếu hạ tầng cho phép; bước nhảy cần được kiểm thử riêng.

**Không thử ghép SWF 3.0 vào JVM Java 8.** Bản 3.0 đòi Java 17 và có dependency dùng namespace Jakarta.

### 3.2. Trường hợp B — dự án Spring Boot 3.x / Spring Framework 6.x

Đây là tổ hợp điển hình để chọn **Web Flow 3.0.x** khi ứng dụng triển khai màn hình nhập và xác nhận nhiều bước bằng Spring MVC.

Trước khi quyết định, kiểm tra:

- Build chạy bằng **Java 17 trở lên**.
- Servlet API và các library của ứng dụng dùng `jakarta.servlet.*`; Bean Validation cũng theo namespace Jakarta tương ứng.
- Không còn dependency tích hợp chỉ dành cho Spring 5 hoặc `javax.servlet.*` trên code path.
- Chọn **bản vá 3.0.x còn phù hợp**, thay vì mặc định dùng bản 3.0.0 từ ví dụ cũ.

Nếu dùng Spring Boot, Boot sẽ quản lý nhiều dependency Spring/Servlet. Tuy nhiên không được mặc định rằng mọi phiên bản `spring-webflow` đều được Boot BOM quản lý: cần xem effective dependency và khai báo rõ khi BOM không quản lý artifact đó.

### 3.3. Trường hợp C — Spring Boot 4.x / Spring Framework 7.x

Chọn **Web Flow 4.0.x** làm ứng viên cho hệ Spring 7. Theo tài liệu 4.0.2, baseline gồm **Java 17+, Spring Framework 7.0, Servlet 6.1**. Spring Boot 4 chuyển nền tảng tới Jakarta EE 11 và Servlet 6.1.

Ngoài SWF, hãy kiểm tra:

- Servlet container thực sự hỗ trợ **Servlet 6.1**; Java 17+ không thay thế được yêu cầu Servlet.
- Cách khai báo starter của Boot 4; **`spring-boot-starter-webmvc`** là starter mới được ưu tiên so với tên cũ `spring-boot-starter-web`.
- Sự khác biệt của Spring Security, dependency validation, Jackson, template engine và cấu hình nếu ứng dụng nâng từ Boot 3.
- Ứng dụng vẫn cung cấp các bean kết nối `FlowRegistry`, `FlowExecutor` và MVC handler mapping/adapter theo cấu hình đã chọn.
- Nếu dùng JSF, kiểm tra **JSF 4.1+** và khả năng hỗ trợ của thư viện component.

Với các bản Spring Framework **7.1** hoặc các bản mới ngoài baseline được tài liệu SWF 4.0.2 mô tả, phải kiểm chứng bằng dependency resolution và integration test trước khi công bố tương thích.

## 4. Web Flow, Spring Framework và Spring Boot có vai trò riêng

Ba thành phần thường được ghi chung một dòng trong tài liệu dự án, nhưng trách nhiệm khác nhau:

| Thành phần | Trách nhiệm | Ví dụ cần kiểm tra |
| --- | --- | --- |
| **Java/JDK** | Runtime, bytecode, compiler, standard API | `java -version`, Java toolchain |
| **Spring Framework / Spring MVC** | IoC container, `DispatcherServlet`, data binding, validation, handler adapters | Spring `spring-core`, `spring-webmvc` đã resolve |
| **Spring Web Flow** | Flow execution, `view-state`, `action-state`, event, transition, subflow, scope | `org.springframework.webflow:spring-webflow` |
| **Spring Boot** (tùy chọn) | Tổ chức application, dependency management, autoconfiguration, embedded server | Boot plugin, BOM và starter |
| **Servlet container** | Xử lý HTTP, servlet/filter/session | Container phù hợp với mức Servlet của Spring/Boot |
| **Security, JSF, templating** (nếu có) | Phân quyền, giao diện, thành phần tích hợp | Version và namespace của từng thư viện |

~~~mermaid
flowchart TD
    JVM["Java runtime / JDK"] --> SERVER["Servlet container"]
    SERVER --> MVC["Spring Framework: MVC + IoC"]
    MVC --> WF["Spring Web Flow: FlowExecutor + FlowRegistry"]
    WF --> F["Flow definitions + state + event + transition"]
    WF --> S["Service beans + validation + persistence"]
    BOOT["Spring Boot: cấu hình ứng dụng và BOM"] -.-> SERVER
    BOOT -.-> MVC
    BOOT -.-> WF
~~~

Các mũi tên nét đứt biểu thị Boot giúp cấu hình và quản lý phụ thuộc; Boot không biến Web Flow thành tính năng có sẵn của mọi starter. **Spring Web Flow tập trung vào ứng dụng web dựa trên Spring MVC/Servlet**, không nên suy rằng có thể cắm nguyên bộ `FlowHandlerAdapter` của MVC vào stack **Spring WebFlux** chỉ vì cùng tên “Spring web”.

## 5. Kiểm tra `javax` và `jakarta` trước khi nâng cấp

Đây là ranh giới kỹ thuật quan trọng giữa dòng **2.5** và các dòng **3.0/4.0**.

| Chủ đề | Spring 5 / SWF 2.5 | Spring 6+ / SWF 3+ |
| --- | --- | --- |
| Servlet request | `javax.servlet.http.HttpServletRequest` | `jakarta.servlet.http.HttpServletRequest` |
| Servlet filter | `javax.servlet.Filter` | `jakarta.servlet.Filter` |
| Bean Validation | `javax.validation.Valid` | `jakarta.validation.Valid` |
| JSF | Các API JSF thế hệ Java EE | `jakarta.faces.*`, version theo dòng Web Flow |
| Servlet container | Container hỗ trợ thế hệ Java EE/`javax` | Container hỗ trợ thế hệ Jakarta tương ứng |

Ví dụ sự khác biệt không thể bỏ qua:

~~~java
// Nguồn Spring 5 / Java EE:
import javax.servlet.http.HttpServletRequest;
import javax.validation.Valid;

// Nguồn Spring 6+ / Jakarta EE (dùng thay thế khi migrate):
// import jakarta.servlet.http.HttpServletRequest;
// import jakarta.validation.Valid;
~~~

Hai bộ package này định danh **hai kiểu khác nhau**, dù tên class tương tự. Nếu một integration cũ nhận `javax.servlet.http.HttpServletRequest` mà runtime/framework chỉ cung cấp `jakarta.servlet.http.HttpServletRequest`, lỗi có thể xảy ra ở compile, load class hoặc khởi tạo bean.

Vì vậy cần kiểm tra **cả source lẫn các dependency transitive**, bao gồm custom filter, servlet listener, thư viện JSP/JSF, validation provider và các JAR tích hợp Web Flow. Việc đổi import trên source chưa thay thế được JAR cũ. Ngược lại, một hệ thống có Java 17 nhưng vẫn dùng Spring 5/`javax` không tự động trở thành Jakarta chỉ vì JDK mới hơn.

## 6. Ví dụ khai báo dependency theo nền tảng

### 6.1. Gradle: Spring Boot 3.x với Web Flow 3.0.x

Trích đoạn dành cho **`build.gradle` dùng Groovy DSL**, giả định dự án đã có plugin Java/Spring Boot 3.x và repository Maven Central:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.webflow:spring-webflow:3.0.2'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

`3.0.2` ở đây là bản cụ thể để nghiên cứu tương thích. Với một ngày triển khai khác, cần chọn bản vá thích hợp ở nhánh 3.0.x. `spring-boot-starter-validation` là ví dụ về implementation validation; nếu ứng dụng không cần bean validation thì quyết định dependency dựa trên nhu cầu thật.

### 6.2. Gradle: Spring Boot 4.x với Web Flow 4.0.x

Trích đoạn dành cho dự án đã cấu hình plugin Boot 4.x và Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.webflow:spring-webflow:4.0.2'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Spring Boot 4 tách starter theo công nghệ rõ hơn. Nếu dùng thêm Security, persistence hoặc Thymeleaf thì khai báo các dependency tương ứng, kiểm tra BOM và phiên bản cùng một thế hệ. **Hai đoạn trên chỉ mô tả dependency, chưa phải cấu hình chạy flow đầy đủ**: ứng dụng còn phải đăng ký `FlowRegistry`, `FlowExecutor`, flow handler và tài nguyên view.

### 6.3. Maven: tọa độ artifact ổn định giữa các dòng

Ví dụ chọn SWF 4.0.2:

~~~xml
<dependency>
    <groupId>org.springframework.webflow</groupId>
    <artifactId>spring-webflow</artifactId>
    <version>4.0.2</version>
</dependency>
~~~

Những phiên bản khác giữ cùng `groupId`/`artifactId` và thay version theo nền tảng đã quyết định. Chỉ khai báo artifact không bảo đảm tích hợp MVC tự động hoàn chỉnh.

### 6.4. Để BOM quản lý Spring Framework, kiểm chứng lại SWF

Trong ứng dụng Spring Boot, nên để **Spring Framework, Spring MVC và các Spring dependency liên quan** được quản lý đồng bộ theo BOM đang dùng; tránh ghi đè ngẫu nhiên `spring-core`, `spring-webmvc`, `spring-context` để chữa lỗi compile.

Một `spring-webflow` version được pin rõ ràng có thể kéo vào thư viện transitive. Nếu dependency resolution xuất hiện hai thế hệ Spring, chỉ nhìn khai báo `implementation` là chưa đủ. Cần xem phiên bản **thực sự được chọn** ở runtime classpath.

## 7. Quy trình kiểm chứng phiên bản thực tế

Nên thực hiện kiểm tra theo thứ tự dưới đây ở chính dự án đang chạy:

### Bước 1 — ghi nhận nền hiện tại

Ghi tối thiểu: JDK chạy build; JDK chạy production; Spring Boot nếu có; Spring Framework; SWF; Servlet container và version Servlet API; namespace `javax`/`jakarta`; JSF nếu dùng. Đặc biệt trong ứng dụng triển khai WAR, **runtime của application server có thể khác với môi trường build**.

### Bước 2 — xem dependency tree

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webflow --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.servlet-api --configuration runtimeClasspath
~~~

Maven:

~~~bash
mvn dependency:tree
mvn help:effective-pom
~~~

Các lệnh trên là **hướng dẫn tự kiểm tra**, chưa được thực thi trong bài học. Với ứng dụng WAR, dependency Servlet có thể ở scope `provided` nên đôi khi không nằm trong runtime classpath cục bộ; cần xem cả cấu hình server triển khai.

### Bước 3 — kiểm tra dấu hiệu lệch thế hệ

Các tình huống cần xử lý trước khi viết flow:

| Phát hiện | Câu hỏi cần trả lời |
| --- | --- |
| SWF 2.5 cùng Spring 6 | Vì sao vẫn còn artifact `javax` trong hệ Spring Jakarta? |
| SWF 3.x cùng Spring 7 | Tại sao chưa chuyển sang SWF 4.x có baseline Spring 7? |
| SWF 4.x trên container thiếu Servlet 6.1 | Runtime có đáp ứng hợp đồng Servlet không? |
| JDK 11 + Spring 6/SWF 3 | Có thể nâng JDK tối thiểu lên 17 không? |
| Nhiều bản `spring-core` / `spring-webmvc` trên classpath | BOM, constraint hay override nào đã chọn bản cuối cùng? |
| JSF cũ đi với SWF 3/4 | Có thể nâng lên JSF 4.0/4.1 và thư viện component tương ứng không? |

### Bước 4 — thử cấu hình flow tối thiểu

Sau khi dependency resolution sạch, dựng một flow thật nhỏ, ví dụ:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <view-state id="details" view="booking/details">
        <transition on="next" to="review"/>
    </view-state>
    <view-state id="review" view="booking/review">
        <transition on="back" to="details"/>
        <transition on="confirm" to="done"/>
    </view-state>
    <end-state id="done" view="booking/done"/>
</flow>
~~~

Đây là **định nghĩa flow minh họa**, chưa bao gồm cấu hình Spring MVC/Web Flow và view templates. Mục tiêu của kiểm tra là xác nhận:

1. Application context tạo được bean SWF và MVC adapter.
2. URL mở đúng flow, flow registry nạp XML và hiển thị `details`.
3. Event `next` chuyển sang `review`, `back` trở về `details`, `confirm` kết thúc.
4. Khi thêm form model, dữ liệu bind và validate đúng; khi thêm subflow, input/output không bị mất.
5. Session timeout, back/refresh và mở nhiều tab được xử lý đúng theo chính sách repository/flow.

Một flow chạy được ở máy local chưa chứng minh môi trường production đáp ứng, đặc biệt với session store, reverse proxy, CSP/CSRF, clustered deployment và JSF.

## 8. Bảo mật và bản vá quyết định cách chọn dòng

Chọn phiên bản không chỉ là bài toán compile. Ngày **10/06/2026**, Spring công bố các bản **Web Flow 3.0.2** và **4.0.1** nhằm xử lý hai lỗ hổng:

- **CVE-2026-40985**: vấn đề data binding khi ứng dụng cấu hình Unified EL parser ở một số điều kiện cụ thể.
- **CVE-2026-40986**: `RemotingHandler` trong JavaScript remoting có thể render response không phải HTML như HTML.

Với CVE-2026-40985, advisory chính thức ghi những phiên bản bị ảnh hưởng gồm **SWF 3.0.0–3.0.1**, **4.0.0** và **2.5.1.RELEASE hoặc cũ hơn**; bản khắc phục OSS gồm **3.0.2** và **4.0.1**. Dòng 2.5 có bản vá qua dịch vụ hỗ trợ thương mại theo advisory. Xem [Spring Security Advisory CVE-2026-40985](https://spring.io/security/cve-2026-40985/) và [thông báo 3.0.2 / 4.0.1](https://spring.io/blog/2026/06/10/spring-webflow-4-0-1-and-3-0-2-available-now/).

Do vậy:

- Với Spring 6, chọn **bản SWF 3.0.x đã có bản vá** phù hợp, không dừng tại 3.0.0 chỉ vì ví dụ cũ.
- Với Spring 7, chọn **bản SWF 4.0.x đã có bản vá** phù hợp; tại thời điểm biên soạn có 4.0.2.
- Với Spring 5/SWF 2.5 legacy, xác minh lựa chọn bản vá có hỗ trợ; nếu không, coi đó là ràng buộc đáng kể trong kế hoạch nâng cấp.
- Vẫn phải cấu hình **binding whitelist**, validation và kiểm tra quyền ở service. Bản vá framework không thay thế các biện pháp bảo mật ở tầng ứng dụng.

Không nên chỉ pin version cho một JAR rồi bỏ qua Spring Framework, Spring Security, servlet container và các advisory khác. Khi thay đổi version, thực hiện lại kiểm thử các nhánh xử lý event và các trường form có quyền cập nhật.

## 9. Nâng cấp từ Web Flow 2.5 lên 3.0 hoặc 4.0

Nâng cấp nên được thực hiện theo **từng ranh giới nền tảng rõ ràng** để dễ khoanh vùng lỗi.

### 9.1. Kiểm kê trước khi thay dependency

Liệt kê:

- Flow XML: `view-state`, `action-state`, `decision-state`, `subflow-state`, `end-state`; event và transition.
- Java actions, biểu thức EL, validators, converters, formatters và các custom listener.
- Cấu hình `FlowRegistry`, `FlowExecutor`, `FlowHandlerMapping`/`FlowHandlerAdapter`, ViewResolver.
- Cách lưu state qua `flowScope`, `conversationScope`, HTTP session và persistence.
- Security rules, CSRF, binding giới hạn field, cơ chế xử lý submit lặp.
- Các giao diện JSP, Thymeleaf, Tiles, JSF hay Ajax/fragment rendering.

Việc này giúp phân biệt **lỗi tương thích runtime** với **lỗi hành vi flow** sau khi nâng cấp.

### 9.2. Lộ trình từ Java 8 / Spring 5 / SWF 2.5

Một chuỗi thực hành hợp lý:

1. **Chốt baseline** trên hệ cũ: chạy lại kịch bản nghiệp vụ có back, cancel, validation, timeout, lỗi service và submit lặp.
2. **Nâng JDK/runtime** tối thiểu lên 17; kiểm tra build plugin và thư viện bên thứ ba.
3. **Chuyển Servlet/Jakarta stack**: cập nhật container, `javax.servlet`, `javax.validation`, JSF và các integration có liên quan.
4. **Nâng Spring Framework lên 6.x** (nếu dùng Boot, chọn Boot 3.x phù hợp) và **SWF 3.0.x có bản vá**.
5. **Thử flow thật** và sửa các thay đổi về template, binding/conversion/validation, security, session repository.
6. Nếu mục tiêu là Spring 7, thực hiện thêm **một đợt nâng riêng** lên Spring 7/Boot 4, Servlet 6.1 và SWF 4.x; kiểm tra lại starter và JSF 4.1 nếu sử dụng.

Ví dụ một dự án dùng **Apache Tiles** cần xem lại giao diện: quá trình chuyển từ SWF 2.5 sang 3.0 đã được Spring minh họa bằng việc bỏ Tiles trong sample vì Tiles chưa migrate sang Jakarta; sample booking MVC chuyển sang Thymeleaf Layouts. Tham khảo [thông báo phát hành SWF 3.0](https://spring.io/blog/2023/07/13/spring-web-flow-3-0-0-released/).

### 9.3. Tách lỗi build khỏi lỗi hành trình

~~~mermaid
flowchart TD
    A["Nâng version"] --> B{"Build / start thành công?"}
    B -->|"Không"| C["Xử lý classpath, JDK, Jakarta, container, bean wiring"]
    B -->|"Có"| D{"Flow vào màn hình đầu?"}
    D -->|"Không"| E["Kiểm tra FlowRegistry, MVC mapping, view resolver"]
    D -->|"Có"| F{"Event/binding/validation đúng?"}
    F -->|"Không"| G["Kiểm tra model, converters, validators, transition"]
    F -->|"Có"| H["Thử session, back, subflow, timeout, lỗi service"]
    H --> I["Đủ điều kiện tiếp tục kiểm thử và triển khai"]
~~~

Không nên “khắc phục” lỗi dependency bằng cách trộn Spring Framework 5 và 6/7 trong cùng runtime hoặc ép SWF version khác nền tảng. Điều đó dễ chuyển lỗi compile thành `NoSuchMethodError`, `ClassNotFoundException` hoặc lỗi handler khi chạy.

## 10. Kịch bản kiểm thử sau khi chọn phiên bản

Một ứng dụng đặt lịch có flow **`details → review → confirm`**, có nhánh `back`/`cancel` và một subflow xác minh thông tin, cần được thử ít nhất ở những trường hợp sau:

| Kịch bản | Kết quả kỳ vọng |
| --- | --- |
| Mở flow từ URL hợp lệ | Vào đúng state đầu, render đúng view |
| Gửi form hợp lệ với event `next` | Bind dữ liệu và chuyển đúng transition |
| Gửi form thiếu trường bắt buộc | Giữ đúng state và hiển thị lỗi; không lưu nghiệp vụ |
| Event `back` từ review | Trở về state đã định nghĩa, không mất bản nháp ngoài ý muốn |
| Gọi subflow và trả kết quả | Input/output giữa flow chính và subflow hợp lệ |
| Kết thúc bằng `confirm` | Gọi service đúng một lần với dữ liệu đã xác thực |
| Bấm xác nhận hai lần | Service/database chống xử lý trùng nếu nghiệp vụ yêu cầu |
| Refresh/back khi flow kết thúc | Xử lý execution hết hạn một cách kiểm soát |
| HTTP session hết hạn giữa chừng | Có thông báo và đường bắt đầu lại rõ ràng |
| Hai tab hoặc hai người dùng | Không trộn dữ liệu, không rò trạng thái singleton |
| Không đủ quyền trên một bước | Server từ chối thao tác, kể cả khi event được gửi thủ công |
| Chạy trên môi trường triển khai thật | Servlet container/session store/proxy hoạt động đúng |

Đặc biệt, một bản nâng cấp có thể **compile thành công** nhưng đổi cách bind hoặc convert form, làm dữ liệu ở bước review bị sai. Vì vậy cần kiểm tra theo góc nhìn **state và event của người dùng**, ngoài kiểm tra cấu hình dependency.

## 11. Những nhầm lẫn phổ biến

**“Java 17 nghĩa là phải dùng Web Flow 3.0.”** Sai. Java chỉ là một trục quyết định. Spring Framework 7.0 + Servlet 6.1 sẽ định hướng tới SWF 4.0; Spring 5 cũ trên Java 17 có thể vẫn đang chạy SWF 2.5.

**“Đã nâng Spring Boot thì Web Flow tự nâng theo.”** Không được giả định. Spring Boot là công cụ cấu hình và quản lý một tập dependency; phải kiểm tra version của artifact `org.springframework.webflow:spring-webflow` và runtime classpath.

**“Spring MVC 7 có thể chạy với Servlet 5 vì vẫn dùng Jakarta.”** Không phù hợp baseline Web Flow 4.0: tài liệu nêu **Servlet 6.1**. Namespace Jakarta giống nhau không đồng nghĩa mức Servlet API và container tương thích.

**“Cứ dùng bản Web Flow mới nhất cho ứng dụng Spring 6.”** Không đúng cách chọn. Đặt nhánh Web Flow cạnh thế hệ Spring/Servlet phù hợp; nếu muốn SWF 4, cần nâng toàn bộ nền lên Spring 7/Servlet 6.1 và kiểm thử.

**“Chỉ đổi namespace import là migration xong.”** Không. Còn JAR transitive, Jakarta Validation, JSF, Spring Security, template engine, session và hành vi form binding.

**“Flow XML không đổi nghĩa là không cần test.”** Không. Một flow XML hợp lệ vẫn có thể thay hành vi vì view, converter, validator, security hoặc session repository khác.

## 12. Bài tập áp dụng và đáp án

### Bài tập A — chọn dòng theo bốn hệ thống

Cho bốn dự án và hãy chọn ứng viên SWF, kèm điểm cần kiểm tra:

| Dự án | Thông tin đang có | Ứng viên / hướng xử lý |
| --- | --- | --- |
| A | Java 8, Spring Framework 5.3, Servlet `javax` | SWF 2.5.x legacy; xem bản vá và lập kế hoạch migrate |
| B | Java 17, Spring Boot 3.x, Spring Framework 6.x | SWF 3.0.x đã vá; kiểm tra Jakarta và Spring MVC |
| C | Java 21, Spring Boot 4.x, Spring Framework 7.x, Servlet 6.1 | SWF 4.0.x đã vá; kiểm tra MVC starter, view, security |
| D | Java 17, Spring Framework 7.x, container chỉ Servlet 5 | **Chưa đủ điều kiện** cho SWF 4; nâng container Servlet 6.1 trước |

### Bài tập B — đọc dependency

Giả sử dự án báo:

~~~text
JDK runtime: 17
spring-core: 6.2.x
spring-webmvc: 6.2.x
spring-webflow: 2.5.1.RELEASE
servlet-api: jakarta.servlet
~~~

Câu hỏi: tại sao không thể xem đây là tổ hợp tương thích?

**Đáp án:** SWF 2.5 thuộc thế hệ Spring 5/`javax`, còn runtime đã lên Spring 6/Jakarta. Cần xác minh và loại dependency legacy, sử dụng SWF 3.0.x có bản vá phù hợp, sau đó test flow. Chỉ đổi import của controller không giải quyết JAR SWF cũ.

### Bài tập C — thiết kế kế hoạch nâng cấp

Với flow đăng ký tài khoản có các bước `profile`, `terms`, `review`, `finish`, hãy lập bảng các kiểm thử cho chuyển Spring 6/SWF 3 sang Spring 7/SWF 4: loại event, state đích, dữ liệu cần giữ trong `flowScope`, lỗi validation, kết quả khi session timeout và hành vi khi submit hai lần. Gắn mỗi trường hợp với một cơ chế kiểm soát tại flow, MVC, service hoặc database.

## 13. Checklist trước khi chốt phiên bản

- [ ] Java runtime/build đáp ứng baseline dòng đã chọn.
- [ ] Spring Framework và Spring MVC cùng một thế hệ, được quản lý nhất quán.
- [ ] SWF cùng thế hệ nền và ở bản vá an toàn phù hợp.
- [ ] Servlet container đáp ứng API yêu cầu, đặc biệt Servlet 6.1 với SWF 4.x.
- [ ] Namespace `javax`/`jakarta` và các thư viện validation/JSF nhất quán.
- [ ] Dependency tree không còn thư viện transitive xung đột.
- [ ] `FlowRegistry`, `FlowExecutor`, MVC adapter và view resolver khởi động được.
- [ ] Test state/event/transition, form binding, validation, subflow và scope đều đạt.
- [ ] Test timeout, back/refresh, nhiều tab, CSRF, quyền truy cập và submit trùng đều đạt.
- [ ] Đã đối chiếu release notes, security advisories và hỗ trợ của các thư viện tích hợp.

## 14. Tài liệu tham khảo chính thức

1. [Spring Web Flow 2.5.1 — Reference Guide](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/) — yêu cầu Java 8/Spring 5, đặc điểm legacy.
2. [Spring Web Flow 3.0.2 — Reference Guide](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — baseline Java 17/Spring 6, tích hợp MVC và JSF 4.0.
3. [Spring Web Flow 4.0.2 — Reference Guide](https://docs.spring.io/spring-webflow/docs/4.0.2/reference/) — baseline Java 17/Spring 7/Servlet 6.1, JSF 4.1.
4. [Spring Web Flow — Releases](https://github.com/spring-projects/spring-webflow/releases) — các bản phát hành mới và thay đổi dependency.
5. [Spring Boot 4.0 — Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide) — Jakarta EE 11/Servlet 6.1, starter và migration.
6. [Spring Web Flow 3.0 released](https://spring.io/blog/2023/07/13/spring-web-flow-3-0-0-released/) — chuyển đổi Spring Framework 6/Jakarta.
7. [Spring Web Flow 3.0.2 / 4.0.1 security release](https://spring.io/blog/2026/06/10/spring-webflow-4-0-1-and-3-0-2-available-now/) và [CVE-2026-40985 advisory](https://spring.io/security/cve-2026-40985/).

**Kết luận kỹ thuật:** Muốn chọn đúng dòng Spring Web Flow, hãy bắt đầu từ **Spring Framework + Servlet container**, xác nhận **JDK và namespace Jakarta/Java EE**, rồi chọn **bản SWF đã vá tương ứng**. Sau khi dependency chạy được, phải kiểm thử hành vi người dùng qua từng state, event, transition, subflow và session; đó mới là bằng chứng ứng dụng nhiều bước thực sự tương thích.
