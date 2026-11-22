# Tách nâng cấp JDK khỏi nâng cấp major framework khi có thể

Trong một dự án Java lâu năm, nâng JDK và nâng major framework thường bị gộp thành một nhiệm vụ vì cả hai đều liên quan đến “chuyển lên Java mới”. Nhưng đây là **hai trục thay đổi khác nhau**. Nâng JDK tác động đến JVM, Java SE API, bytecode, compiler, module encapsulation, TLS, GC, thư viện nền và cách chạy ứng dụng. Nâng major framework lại có thể thay đổi cấu trúc dependency, annotation, cấu hình, lifecycle, routing, security defaults, persistence behavior, integration contracts và cách framework khởi tạo ứng dụng.

Nếu thay cả hai cùng một lúc, một lỗi `InaccessibleObjectException`, một truy vấn ORM trả kết quả khác hoặc một endpoint bị 404 có thể đến từ nhiều nguồn. Nhóm khó xác định thay đổi nào gây lỗi, khó rollback và khó đưa ra bằng chứng rằng ứng dụng đang tương thích với JDK hoặc framework mới. Vì vậy, khi điều kiện kỹ thuật cho phép, **nên tách nâng JDK khỏi nâng major framework thành các bước độc lập có baseline, kiểm thử và khả năng khôi phục riêng**.

Tuy nhiên, “tách khi có thể” là điều kiện quan trọng. Framework hiện tại có thể không hỗ trợ JDK đích; framework thế hệ mới có thể yêu cầu một JDK tối thiểu cao hơn JDK hiện tại; hoặc một migration từ `javax.*` sang `jakarta.*` có thể bắt buộc nâng framework/container cùng bộ API. Khi đó cần xây **phiên bản cầu nối** và một chuỗi nâng cấp khả thi, không cố thực hiện một tổ hợp runtime mà nhà cung cấp không hỗ trợ.

Bài học này trình bày cách đọc ma trận hỗ trợ, chia lộ trình, kiểm soát dependency và build tool, thiết kế thử nghiệm để quy trách nhiệm cho lỗi, tổ chức rollout/rollback, cùng các tình huống mà việc nâng phối hợp là cần thiết.

## 1. Hai trục thay đổi phải được theo dõi độc lập

### 1.1. Trục JDK

Đổi JDK có thể thay đổi:

- **JVM runtime:** class loading, bytecode verification, JIT, garbage collectors, memory layout, threading và diagnostic flags.
- **Java SE APIs:** API mới, API đã deprecated hoặc bị loại bỏ, thay đổi hành vi của một số thư viện chuẩn.
- **Strong encapsulation:** khả năng truy cập các package nội bộ JDK và các lỗi liên quan reflection.
- **Compiler/toolchain:** `javac`, `--release`, class-file version, annotation processing và test runner.
- **Security defaults:** TLS protocols, certificate validation, disabled algorithms, keystore/provider behaviors.
- **Runtime packaging:** classpath/module path, Java agents, container image, `jlink` hoặc launcher.
- **Operational characteristics:** heap sizing, cgroup detection, GC logs, startup/warm-up và performance.

Ứng dụng không cần đổi một dòng business code vẫn có thể bị ảnh hưởng khi đổi JVM hoặc JDK vendor/update. Vì vậy phải xác minh **runtime behavior**, không chỉ compile.

### 1.2. Trục major framework

Đổi major framework có thể thay đổi:

- **Public APIs và annotations:** tên package, method signature, annotation attributes.
- **Auto-configuration:** component scanning, beans, dependency injection, default configuration.
- **Web stack:** servlet container, HTTP routing, request/response binding, validation, exception mapping.
- **Persistence:** ORM mapping, transaction semantics, generated SQL, lazy-loading behavior và dialect.
- **Security:** filter chain, authentication/authorization defaults, CSRF, CORS, session management, TLS integration.
- **Serialization:** Jackson/Gson adapters, date/time, enum, polymorphic typing, message converters.
- **Observability:** logging, metrics, tracing, health checks và management endpoints.
- **Dependency BOM:** các phiên bản transitive của thư viện và container đi kèm.
- **Build plugins:** cách tạo executable JAR, test, AOT/native compilation, layered image.
- **Compatibility contracts:** dữ liệu lưu, queue messages, session và đối tác gọi API.

Dù major framework mới chạy cùng JDK cũ, thay đổi này vẫn có thể gây lỗi nghiệp vụ hoặc phá hợp đồng bên ngoài.

### 1.3. Tại sao cần tách?

Giả sử hệ thống hiện tại chạy:

~~~text
JDK cũ + Framework major A
~~~

Cách nâng gộp:

~~~text
(JDK cũ, Framework A)
           |
           v
(JDK mới, Framework B)
~~~

Nếu regression xuất hiện, cần điều tra đồng thời hai tập thay đổi lớn. Nếu ma trận hỗ trợ cho phép, chia thành:

~~~text
(JDK cũ, Framework A)
           |
           | Chỉ nâng JDK
           v
(JDK mới, Framework A)
           |
           | Chỉ nâng major framework
           v
(JDK mới, Framework B)
~~~

Hoặc có thể nâng framework trong dòng major đang dùng lên bản patch/minor hỗ trợ JDK mới trước, rồi mới nâng JDK. Điểm then chốt không phải cố định một thứ tự duy nhất, mà là **mỗi lần chuyển chỉ đưa vào những thay đổi cần thiết để đi đến một tổ hợp được hỗ trợ**.

## 2. Ma trận tương thích là điều kiện đầu tiên

Trước khi đưa ra kế hoạch, lập ma trận JDK × framework. Không suy đoán từ việc bản framework có thể compile một demo đơn giản.

| | JDK hiện tại | JDK mục tiêu |
|---|---|---|
| Framework hiện tại | A — baseline đang chạy | B — điểm trung gian muốn đạt |
| Framework major mới | C — điểm trung gian thay thế | D — trạng thái đích |

Các tổ hợp:

- **A:** môi trường thực tế đang chạy và phải lưu làm baseline.
- **B:** lý tưởng để kiểm chứng riêng ảnh hưởng JDK, **chỉ khả thi nếu framework hiện tại hỗ trợ JDK mới**.
- **C:** có thể dùng để kiểm chứng riêng nâng framework trước, **chỉ khả thi nếu major mới hỗ trợ JDK hiện tại**.
- **D:** trạng thái mong muốn cuối cùng, cần kiểm chứng đầy đủ.

Không bắt buộc cả bốn ô đều hợp lệ. Ví dụ một framework major mới yêu cầu JDK tối thiểu 17 sẽ không chạy trên JDK 11; khi đó ô C không hợp lệ. Một bản framework cũ có thể không hỗ trợ JDK 21; khi đó ô B không hợp lệ. Nhóm phải tìm **bản trung gian hoặc thứ tự khác**, không cưỡng ép runtime bằng các JVM flags.

### 2.1. Các mức đánh giá mỗi ô

Phân biệt:

1. **Được vendor hỗ trợ chính thức:** tổ hợp nằm trong ma trận hỗ trợ và còn trong thời gian bảo trì theo chính sách.
2. **Chưa xác minh:** chưa có thông tin hoặc chưa chạy test; không được mặc định thành tương thích.
3. **Chạy được trong smoke test:** bằng chứng có giá trị nhưng không thay thế cam kết hỗ trợ hoặc integration test.
4. **Không được hỗ trợ:** bị loại khỏi thiết kế hoặc chỉ dùng trong thử nghiệm ngắn hạn với rủi ro đã được chấp nhận.
5. **Đã được dự án kiểm chứng:** đã chạy kiểm thử tương ứng với nghiệp vụ/triển khai thực tế, kèm artifact và môi trường cụ thể.

Một tổ hợp có thể “khởi động được” nhưng không nằm trong tập vendor support, hoặc có thể nằm trong bảng hỗ trợ mà ứng dụng vẫn lỗi vì custom code. Hai loại bằng chứng này bổ sung nhau.

### 2.2. Kiểm tra nhiều tầng support matrix

Không chỉ hỏi framework “hỗ trợ Java mấy?”. Cần kiểm tra:

- **Framework core** và bản patch/minor trong major hiện tại.
- **Framework build plugin** và Maven/Gradle được hỗ trợ.
- **Embedded servlet/reactive server** hoặc application server.
- **ORM/JPA provider** và database driver.
- **Serialization libraries**, HTTP clients, tracing/metrics agents.
- **Bytecode tools:** ASM, Byte Buddy, cglib, Javassist, instrumentation.
- **Java agents:** APM, profiler, monitoring, security agents.
- **Annotation processors và generated code** của dự án.
- **Third-party starters/extensions** không thuộc core framework.
- **OS/CPU và container base image** nếu có native dependencies.
- **JDK vendor và update** nếu hỗ trợ hoặc sự cố phụ thuộc cụ thể một build.

Một framework có thể hỗ trợ JDK 21 nhưng plugin build của dự án vẫn đang dùng phiên bản không hỗ trợ. Không nên kết luận readiness chỉ từ một dòng trên trang tổng quan của framework.

## 3. “Nâng JDK” cũng có nhiều việc: không gộp compile và runtime

Một thay đổi JDK có thể được chia nhỏ thêm:

### 3.1. Đổi JDK chạy build tool

Maven hoặc Gradle chạy trên JVM tương ứng. Plugin cũ có thể thất bại ngay khi build logic được nạp nếu thiếu API hoặc class-file version không phù hợp.

### 3.2. Đổi compiler/toolchain

Dự án có thể biên dịch bằng JDK mới nhưng vẫn phát hành artifact có baseline thấp hơn thông qua `--release`:

~~~text
Build JDK: 21
javac --release 17
Runtime yêu cầu: Java 17 trở lên nếu dependencies cũng tương thích
~~~

`--release` kiểm soát Java language level, Java SE API và class-file target mà compiler cung cấp. Nó **không** đảm bảo mọi dependency third-party trong artifact hỗ trợ runtime cũ, và cũng không kiểm soát JVM thực thi Maven/Gradle.

### 3.3. Đổi runtime production

Đây là bước ứng dụng thực sự chạy trên JVM mới trong container, VM hoặc server. Nó kiểm tra TLS, GC, class loading, logging, native dependencies, performance và behavior.

### 3.4. Dùng Java features mới

Bắt đầu sử dụng records, pattern matching, virtual threads hoặc API mới của Java là một quyết định thay đổi source/runtime requirements riêng. Nếu mục tiêu là phân biệt tác động của JDK, nên **tránh thêm đồng thời các tính năng ngôn ngữ mới không cần thiết** trong đợt đổi runtime.

Một lộ trình có thể là: nâng Maven/Gradle và toolchain, giữ `--release` cũ; chạy framework hiện tại trên JDK mới nếu được hỗ trợ; nâng framework major; cuối cùng mới chủ động thay Java source/target baseline.

## 4. Điều kiện để tách nâng JDK trước

Có thể ưu tiên **JDK-first** khi:

- Bản framework hiện tại có release được vendor xác nhận chạy trên JDK đích.
- Các plugin, agents và libraries thiết yếu có bản vá tương thích với JDK đích mà không đòi major framework mới.
- API nội bộ JDK không còn được dự án/framework sử dụng, hoặc có phương án hỗ trợ hợp lệ.
- Hệ thống có đủ test để xác nhận behavior trên JDK đích.
- Có khả năng chạy canary một nhóm instance trên JDK mới nhưng giữ app/framework version.
- Rollback runtime JDK có thể thực hiện với cùng artifact mà không thay đổi hợp đồng dữ liệu bên ngoài.

Ví dụ lộ trình:

~~~text
A: Framework 2.x patch hiện tại + JDK 17
     |
     | Nâng các bản vá trong cùng major nếu cần
     v
A': Framework 2.x patch hỗ trợ + JDK 17
     |
     | Đổi runtime và build toolchain sang JDK 21
     v
B: Framework 2.x patch hỗ trợ + JDK 21
     |
     | Sau khi vận hành ổn định, nâng framework major
     v
D: Framework 3.x được hỗ trợ + JDK 21
~~~

**Quan trọng:** tên major trong sơ đồ là giả định. Framework 2.x cụ thể có thể **không** hỗ trợ JDK 21; khi đó bước B bị loại. Phải kiểm tra support matrix đúng framework/version, không copy nguyên sơ đồ vào dự án.

### 4.1. Lợi ích của JDK-first

Nếu B pass, nhóm có thể chứng minh rằng runtime JDK mới không làm hỏng những hành vi quan trọng khi framework chưa thay đổi. Những regression xuất hiện ở bước B thường khoanh vùng vào JDK, bytecode/tooling, provider, agent hoặc môi trường vận hành hơn là breaking changes của framework major.

Điều đó giúp release notes và rollback đơn giản hơn: trong giới hạn thiết kế, có thể quay lại runtime JDK cũ mà không cần đồng thời quay lại framework hoặc các hợp đồng API đã thay đổi.

### 4.2. Không cố ép framework cũ chạy bằng cờ JVM

Một số dự án thấy `InaccessibleObjectException` rồi thêm nhiều cờ:

~~~text
--add-opens java.base/java.lang=ALL-UNNAMED
--add-opens java.base/java.util=ALL-UNNAMED
~~~

Những cờ này có thể là workaround tạm cho reflective access trong phạm vi được JDK cho phép, nhưng **không biến phiên bản framework không được hỗ trợ thành tổ hợp có bảo đảm**. Nếu framework phụ thuộc class nội bộ đã bị loại bỏ hoặc bytecode thư viện không hiểu JDK mới, mở package không giải quyết được.

Mọi workaround cần có owner, lý do, test, ngày xem xét lại và phương án nâng thư viện/framework để loại bỏ.

## 5. Điều kiện để tách nâng framework trước

Có thể ưu tiên **framework-first** khi:

- Framework major mới vẫn hỗ trợ JDK hiện tại.
- Phần lớn breaking changes thuộc API/config/framework và có thể được kiểm chứng mà chưa đổi runtime.
- Các dependencies của framework mới có thể chạy trên JDK hiện tại.
- Cần xử lý annotation, routing, security hoặc persistence trước để giảm rủi ro khi nâng runtime.
- Code và packaging có thể giữ Java target hiện tại trong giai đoạn đầu.
- Không có thay đổi dữ liệu không tương thích làm rollback ngay lập tức không khả thi.

Lộ trình:

~~~text
A: Framework A + JDK cũ
          |
          | Nâng framework, giữ JDK
          v
C: Framework B + JDK cũ
          |
          | Khi đã ổn định, nâng JDK
          v
D: Framework B + JDK mới
~~~

Một lần nữa, C chỉ khả thi khi framework B hỗ trợ JDK cũ. Ví dụ các framework major yêu cầu Java tối thiểu cao hơn sẽ khiến phương án này không hợp lệ.

### 5.1. Lợi ích của framework-first

Nếu C pass, thay đổi routing, dependency injection, transaction, JSON binding, ORM và security mặc định đã được kiểm chứng độc lập khỏi JDK mới. Bước D sau đó tập trung vào runtime/toolchain.

### 5.2. Một bản framework major có thể kéo theo JDK tối thiểu mới

Nếu major B yêu cầu JDK 17 nhưng dự án ở JDK 11, không thể đưa C vào production dù một số class compile được với JDK hiện tại. Không nên dùng `--release 11` rồi kỳ vọng framework B hoạt động trên Java 11 khi framework dependency chính có class-file version Java 17 hoặc gọi API mới.

Trong trường hợp này, phải tìm bản framework A patch/minor hỗ trợ JDK trung gian hoặc tiến hành một đợt nâng phối hợp có phạm vi kiểm thử lớn hơn.

## 6. Khi cả hai bước trung gian đều không được hỗ trợ

Đây là tình huống khó: framework cũ không hỗ trợ JDK mục tiêu, trong khi framework mới không hỗ trợ JDK hiện tại.

~~~text
A: Framework cũ + JDK cũ        D: Framework mới + JDK mới
           \                       /
            \  Không có B/C hợp lệ/
             ---------------------
~~~

Một số chiến lược:

1. **Thử phiên bản cầu nối của framework:** một minor/patch release trong major cũ đã bổ sung support cho JDK trung gian hoặc một major trung gian hỗ trợ cả hai JDK.
2. **Thử JDK trung gian:** chuyển qua một JDK release được cả framework hiện tại và framework kế tiếp hỗ trợ.
3. **Tách ở mức build và test dù không thể tách ở production:** chuẩn bị PR độc lập cho build tool/JDK compatibility, framework API changes, dependencies và deployment; tích hợp chỉ sau khi có test matrix.
4. **Sử dụng nhánh migration riêng:** giữ production ổn định, xây một integration branch có checkpoints và tests để kiểm soát thay đổi.
5. **Dùng compatibility adapter hoặc strangler pattern:** cô lập phần framework khó nâng ở service/process riêng, giao tiếp qua hợp đồng ổn định.
6. **Nâng phối hợp có kiểm soát:** nếu không tồn tại tổ hợp trung gian được hỗ trợ, triển khai JDK + framework mới cùng lúc nhưng tăng mức bảo vệ bằng fixtures, canary và rollback thực tế.

Không nên tạo bản fork framework cũ chỉ để “đánh dấu hỗ trợ JDK mới” nếu đội không có khả năng bảo trì và test đầy đủ. Đó là một quyết định kỹ thuật lớn, không phải phương án mặc định.

### 6.1. Phân biệt không có đường trung gian với chưa tìm đủ dữ liệu

Một support matrix chưa có thông tin là **chưa xác minh**, không phải “chắc chắn không thể tách”. Cần tra cứu release notes, compatibility tables và dependency graph của từng bản framework dự kiến. Nếu chưa có bằng chứng, ghi rõ mức độ bất định và không chốt lộ trình dựa trên giả định.

## 7. Bản vá và minor version có thể là cầu nối

Một bước ít rủi ro là nâng lên **patch/minor mới nhất được hỗ trợ của cùng major** trước khi đụng JDK hoặc framework major.

Ví dụ mô hình:

~~~text
Framework A.1 + JDK X
       |
       | Nâng patch/minor A.9 (không đổi major)
       v
Framework A.9 + JDK X
       |
       | Nếu A.9 hỗ trợ JDK Y
       v
Framework A.9 + JDK Y
       |
       | Nâng major B (trong JDK Y)
       v
Framework B + JDK Y
~~~

Không mặc định semver bảo đảm mọi bản minor chỉ thêm tính năng không breaking. Framework ecosystem có thể có breaking changes trong transitive dependencies hoặc cấu hình mặc định thay đổi. Vẫn cần kiểm thử và đọc release notes.

Patch/minor bridge thường hữu ích vì vendor có thể đã cập nhật ASM, bytecode tooling, Java agents, JSON libraries hoặc các khai báo hỗ trợ Java mới trong một bản bảo trì của major hiện tại.

## 8. Ví dụ minh họa với Spring ecosystem

Spring là ví dụ phổ biến về lý do phải phân biệt JDK và framework major. Dự án Spring Boot/Spring Framework có thể có các thay đổi lớn giữa major: Java baseline, Spring Security configuration, web/server stack, validation/servlet APIs và namespace Jakarta.

### 8.1. Đổi `javax.*` sang `jakarta.*` là thay đổi framework/platform

Ở các thế hệ Jakarta EE mới, nhiều API enterprise chuyển từ package `javax.*` sang `jakarta.*`, ví dụ:

~~~java
// Kiểu API cũ:
import javax.servlet.http.HttpServletRequest;
import javax.persistence.Entity;
import javax.validation.Valid;

// Kiểu API mới trong hệ sinh thái tương ứng:
import jakarta.servlet.http.HttpServletRequest;
import jakarta.persistence.Entity;
import jakarta.validation.Valid;
~~~

Đây **không phải** một hiệu ứng tự động của việc nâng JDK. JDK 17 không “đổi tên package javax thành jakarta” cho ứng dụng. Thay đổi này đến từ các version của Jakarta EE, framework, servlet container, JPA/validation provider và dependencies đi kèm.

Nếu vừa nâng JDK, vừa đổi Spring Boot major, vừa chuyển `javax`→`jakarta`, những lỗi như `ClassNotFoundException`, `NoSuchMethodError` hoặc validation không được kích hoạt có thể xuất phát từ nhiều thay đổi. Khi có bản framework cầu nối, tách việc sửa code và dependency theo bước riêng giúp điều tra dễ hơn.

### 8.2. Ví dụ kế hoạch dự án

Một dự án có thể thiết kế:

1. Chốt baseline Spring Boot hiện tại và Java hiện tại.
2. Nâng lên patch release phù hợp trong cùng dòng Spring Boot để cập nhật dependencies/JDK support nếu có.
3. Nâng JDK runtime trước **nếu patch release ấy được công bố hỗ trợ JDK mục tiêu**.
4. Sau khi JDK runtime pass, chuyển Spring Boot major trong một thay đổi riêng, bao gồm Jakarta packages, security configuration, ORM và integration tests.
5. Nếu không có bản Boot cũ hỗ trợ JDK đích, chọn JDK trung gian hoặc làm migration phối hợp.

Không dùng một bản đồ version chung cho mọi Spring project. Các dòng Spring Boot và Spring Framework có yêu cầu Java tối thiểu/tối đa và compatibility thay đổi theo release. Phải kiểm tra ma trận đúng **version cụ thể** của dự án.

### 8.3. Không chỉ có core framework

Một Spring Boot application có thể dùng:

- Spring Data và Hibernate/JPA provider.
- Spring Security và OAuth/JWT integration.
- Embedded Tomcat/Jetty/Undertow hoặc reactive Netty stack.
- Jackson và JSON modules.
- Micrometer, OpenTelemetry, tracing exporters.
- Spring Cloud ecosystem và các starters bên thứ ba.
- Database migration tools.
- Testcontainers, Mockito, Byte Buddy và JUnit.
- APM/Java agents.

Mỗi nhóm có compatibility matrix riêng. Không nên bỏ qua Spring Cloud hoặc một custom starter chỉ vì Spring Boot core đã hỗ trợ JDK đích.

## 9. Với Quarkus, Micronaut, Jakarta EE và application servers

Nguyên tắc tương tự áp dụng cho nhiều nền tảng Java.

### 9.1. Quarkus

Quarkus có build-time augmentation, bytecode generation, CDI, persistence integration và có thể tạo native executables. Nâng major Quarkus thường tác động build plugins, extensions và cơ chế xử lý tại build time, không chỉ runtime JDK. Nếu đồng thời nâng JDK, lỗi có thể xuất hiện trong augmentation trước cả khi ứng dụng chạy.

Hãy xác minh Java baseline và các extension của đúng phiên bản Quarkus, sau đó tách thay đổi build/runtime và thay major khi được hỗ trợ.

### 9.2. Micronaut

Micronaut sử dụng annotation processing và compile-time dependency injection. JDK mới hoặc framework major mới có thể yêu cầu version annotation processors và Gradle/Maven plugins tương ứng. Một build xanh nhưng output generated classes lỗi khi runtime có thể đến từ việc trộn các phiên bản processor/runtime.

Cần quản lý processor path và runtime libraries cùng compatibility matrix, không chỉ chỉnh `JAVA_HOME`.

### 9.3. Jakarta EE / Java EE và application server

Ứng dụng deploy WAR/EAR phụ thuộc cả API specification và **application server** (ví dụ một dòng Tomcat/WildFly/Payara/WebLogic phù hợp). Nâng JDK phải xác minh server version được hỗ trợ; nâng Jakarta EE namespace cần kiểm tra servlet, persistence, validation, CDI và các thư viện WAR.

Nhiều khi runtime/container do bên vận hành cung cấp không nằm trong artifact ứng dụng. Vì vậy bảng dependency Maven chưa phản ánh toàn bộ môi trường framework/platform.

## 10. Đóng băng các yếu tố không thuộc bước đang thử

Mục tiêu của việc tách nâng cấp là kiểm soát biến số.

Khi thử JDK-first:

- Giữ nguyên phiên bản ứng dụng/framework và BOM ở mức cho phép.
- Giữ database schema, API contract, message schema và cấu hình business.
- Không chủ động đổi routing/security behavior cùng lúc.
- Nếu buộc nâng build plugin/driver để hỗ trợ JDK, ghi đây là **dependency change bắt buộc**, không gọi giai đoạn đó là “JDK-only tuyệt đối”.
- Giữ nguyên test data, traffic mix và các chỉ số SLO để so sánh.

Khi thử framework-first:

- Giữ JDK runtime nếu major mới hỗ trợ.
- Giữ các JVM options không liên quan.
- Tách riêng các migration dữ liệu có thể trì hoãn.
- Ghi rõ transitive dependencies thay đổi do BOM/framework.
- Tránh dùng tính năng Java mới đồng thời, trừ khi framework yêu cầu.

**Không thể luôn chỉ đổi đúng một file hoặc một version.** Tách ở đây là tách **trục nguyên nhân và mục tiêu kiểm chứng**, còn các thay đổi hỗ trợ cần thiết phải được liệt kê minh bạch.

## 11. Quản lý Maven và Gradle để tách thay đổi

### 11.1. Maven: tách Java release khỏi framework dependency

Ví dụ phần chính của `pom.xml`:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Dự án thực tế có thể dùng property riêng do framework parent/BOM quy định. Ý nghĩa cần giữ rõ:

- `maven.compiler.release` quản lý Java target nếu Maven Compiler Plugin đang dùng property này.
- Phiên bản parent/BOM và framework plugins xác định các API/dependencies/framework build behavior.
- JDK chạy Maven được xác định từ môi trường hoặc toolchain, không bị khóa chỉ bởi Java property.

Ví dụ đặt compiler release trong plugin:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.13.0</version>
  <configuration>
    <release>17</release>
  </configuration>
</plugin>
~~~

Số plugin chỉ minh họa; phải chọn version tương thích với Maven/JDK của dự án.

Một pipeline có thể cho JDK-first đổi `JAVA_HOME` / Maven toolchain và container base image trước, giữ BOM framework ổn định. Khi framework-first, đổi framework parent/BOM và code tương ứng nhưng giữ JDK runtime nếu được hỗ trợ.

### 11.2. Gradle: phân biệt Java toolchain và plugin version

Ví dụ Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'VERSION_DA_DUOC_XAC_MINH'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

`VERSION_DA_DUOC_XAC_MINH` là placeholder, không phải plugin version dùng trực tiếp. Thay bằng version thực tế được vendor hỗ trợ. Cần kiểm tra Gradle version có hỗ trợ JDK chạy build và Java toolchain đích.

- JDK build/toolchain có thể thay trong bước JDK migration.
- Framework plugin version thay trong bước framework migration.
- `options.release` có thể được giữ cố định để tránh đổi source/bytecode baseline đồng thời.
- Nếu framework major mới yêu cầu Java baseline cao hơn, `--release` phải thay khi đến bước đó và được kiểm chứng.

### 11.3. Khóa dependency graph và lưu bằng chứng

Một framework BOM có thể nâng hàng chục dependency transitive ngay cả khi source chỉ thay một dòng version. Kiểm tra:

~~~bash
# Maven
./mvnw dependency:tree
./mvnw help:effective-pom

# Gradle
./gradlew dependencies
./gradlew dependencyInsight --dependency jackson-core
~~~

Lệnh minh họa; `dependencyInsight` cần configuration phù hợp trong nhiều dự án. So sánh output theo **hai điểm chuyển tiếp** để biết những dependency nào thay đổi ở bước JDK và bước framework.

Không mặc định dependency locking hoặc BOM giải quyết mọi runtime conflict. Trong production còn có JAR do application server cung cấp, Java agents và runtime layers ngoài build.

## 12. Tách build-time compatibility khỏi application runtime compatibility

Một dự án có thể dùng JDK mới để build nhưng chạy ứng dụng cũ trên runtime cũ, hoặc ngược lại. Các thành phần build-time như annotation processors, code generators, test runner và Maven/Gradle plugins có compatibility riêng.

Ví dụ:

~~~text
Build system:
  Maven/Gradle Wrapper
          |
          v
  JDK chạy build tool
          |
          +--> Annotation processor / code generation
          |
          +--> Compiler toolchain / --release
          |
          v
      Application artifact
                |
                v
Production:
  Runtime JDK + framework libraries
                |
                v
    DB / cache / queue / external services
~~~

Một lỗi `UnsupportedClassVersionError` trong annotation processor có thể xảy ra trước khi chương trình chạy. Một lỗi `InaccessibleObjectException` trong ORM có thể chỉ xảy ra khi một entity được ánh xạ lúc runtime. Không nên dùng “Java 21 không tương thích với framework” làm nhãn chung nếu vấn đề thực tế nằm ở build plugin hoặc test instrumentation.

Cần ghi: lỗi xảy ra ở bước **bootstrap build**, **compile**, **test JVM**, **application startup** hay **production request**.

## 13. Thiết lập baseline trước khi nâng bất kỳ trục nào

Baseline phải là một phiên bản có thể chạy lại, không chỉ là một commit hash.

Tối thiểu ghi:

| Nhóm | Thông tin cần có |
|---|---|
| Source | Commit/tag và thay đổi chưa commit |
| JDK | Vendor, feature/update/build, OS/architecture |
| Framework | Core version, plugin version, starters/extensions |
| Build | Maven/Gradle Wrapper, plugins, toolchains, `--release` |
| Dependencies | BOM/lockfile, resolved dependency tree, agents |
| Runtime | Container image digest, JVM options, memory/GC settings |
| Infrastructure | Database driver/version, broker/cache/client versions |
| Data contracts | Schema database, cache, session, event/message |
| Tests | Unit, integration, contract, load, compatibility suites |
| Operations | SLO, p95/p99 latency, error rate, startup, memory/CPU |
| Deployment | Launch command, health checks, rollout/rollback plan |

Nếu baseline đang có lỗi đã biết, ghi rõ chúng. Khi nâng, tránh quy một lỗi tồn tại từ trước thành regression của JDK/framework mới.

### 13.1. Quy tắc thay đổi tối thiểu

Một bước migration nên có **mục tiêu và acceptance criteria rõ**:

~~~text
Change JDK runtime from JDK X to JDK Y.
Framework major/version stays constant except explicitly documented patches.
No changes to public API or persistence schema.
Acceptance: previous behavior and SLO tests pass on JDK Y.
Rollback: restore JDK X runtime image with unchanged app artifact.
~~~

Đây là ví dụ policy, không phải cam kết hợp lệ cho mọi dự án. Nếu library bắt buộc nâng cùng JDK, phải đưa vào danh sách thay đổi và test riêng ảnh hưởng của library đó.

## 14. Kiểm thử để xác định đúng nguyên nhân regression

Muốn phân biệt tác động JDK và framework, cần cùng **bộ kiểm thử và dữ liệu** chạy trên các tổ hợp được hỗ trợ.

### 14.1. Phân nhóm test

1. **Build/compiler tests:** toolchain, generated sources, annotation processors, test plugins.
2. **Unit tests:** logic nghiệp vụ ít phụ thuộc infrastructure.
3. **Framework integration tests:** dependency injection, routing, validation, security, persistence, transactions.
4. **Contract tests:** public HTTP/gRPC APIs, event schemas và các integration với đối tác.
5. **Data compatibility tests:** đọc dữ liệu database/cache/session/message được phiên bản cũ tạo.
6. **Runtime/observability tests:** startup, JVM flags, TLS, agents, logging, GC và metrics.
7. **Performance/load tests:** latency, throughput, memory, CPU, warmup và tail latency.
8. **Rollback tests:** phiên bản cũ có thể quay lại sau dữ liệu/requests của phiên bản mới hay không.

Không dùng một bài smoke test khởi động như bằng chứng tổng thể rằng upgrade thành công.

### 14.2. Golden fixtures và dữ liệu phiên bản cũ

Cần giữ fixture có thể tái sử dụng qua các bước:

~~~text
fixtures/
  http/
    request-v1.json
    response-v1.json
  persistence/
    sample-data-v1.sql
  cache/
    cache-entry-v1.bin
  session/
    session-v1.json
  messages/
    order-created-v1.json
~~~

Fixture phải dùng dữ liệu giả lập/anonymized và không đưa secrets, JWT thật hoặc thông tin khách hàng nhạy cảm vào Git.

Khi thử JDK-first, dùng cùng fixture với framework cũ. Khi thử framework-major, tiếp tục dùng fixture đó để xác định các thay đổi serialization, ORM và validation. Nếu dữ liệu được viết dưới phiên bản mới, phải kiểm tra khả năng đọc ngược nếu rolling deployment/rollback yêu cầu.

## 15. Quan sát các thay đổi ở JDK mà framework test có thể bỏ sót

### 15.1. Strong encapsulation và reflection

JDK mới có thể hạn chế reflection vào package nội bộ JDK. Các framework cũ, thư viện bytecode và công cụ instrumentation có thể gặp:

~~~text
java.lang.reflect.InaccessibleObjectException
java.lang.IllegalAccessError
~~~

Cách sửa ưu tiên là nâng thư viện hoặc đổi sang public APIs. Cờ `--add-opens` chỉ nên dùng như cầu nối có kiểm soát và được ghi chép.

### 15.2. TLS và security providers

JDK mới có thể có chính sách disabled algorithms, TLS protocols hoặc truststore khác. Những lỗi kết nối tới API, database hoặc broker không nhất thiết do framework major.

Khi thử JDK-first, giữ cùng framework giúp phân biệt thay đổi security của JDK với thay đổi client/framework.

### 15.3. GC và memory

JDK mới có default GC, memory ergonomics và container awareness khác theo phiên bản. Một ứng dụng có throughput tốt hơn nhưng p99 latency tệ hơn cần được đánh giá bằng workload thực tế. Không kết luận từ microbenchmark đơn lẻ hoặc chỉ từ kết quả unit test.

### 15.4. Bytecode, class loading và agents

APM/security agents, proxy, mocking và bytecode instrumentation có thể phụ thuộc vào class-file version hoặc API nội bộ. Cần xác minh version agents hỗ trợ JDK mới. Một framework hoạt động bình thường khi tắt agent nhưng lỗi trong production có thể do agent, không phải core framework.

### 15.5. Removed/deprecated Java APIs

Một số API/tool từng có trong JDK cũ đã bị di chuyển hoặc loại bỏ ở thế hệ mới. Khi framework/library phụ thuộc vào chúng, cần dependency thay thế hoặc đổi cách tích hợp. `--add-opens` không khôi phục class đã bị xóa.

## 16. Quan sát các thay đổi framework mà JDK tests có thể bỏ sót

### 16.1. Web và validation

Framework major mới có thể thay đổi:

- Handler mapping hoặc thứ tự route matching.
- JSON serialization defaults.
- Validation annotations và exception mapping.
- HTTP status code cho input không hợp lệ.
- Filter chain, CORS/CSRF và cách redirect/login.
- Content negotiation, multipart/file uploads.

Các thay đổi này có thể xảy ra dù runtime JDK không đổi. Hãy dùng consumer contract tests và end-to-end tests thay vì chỉ test controller method trực tiếp.

### 16.2. ORM và transaction

Nâng ORM provider/dialect có thể đổi SQL được sinh ra, fetch strategy, query translation, schema validation hoặc transaction boundaries. Một truy vấn đúng trong unit test với database giả có thể lỗi trong DB production.

Phải test trên database engine/version gần production, với dữ liệu thật đã được ẩn danh và migration scripts phù hợp. Khi có thay đổi database schema, cần thiết kế expand–contract và khả năng rollback riêng.

### 16.3. Dependency injection và AOP

Bean lifecycle, proxy semantics, annotation processing và conditionals có thể thay đổi. Một bean có thể được tạo khác thứ tự; một aspect không còn áp dụng; hoặc exception handler không được nhận diện như trước.

Các lỗi kiểu này thuộc hành vi framework-major hơn là JDK runtime nếu chúng chỉ xuất hiện ở tổ hợp D sau khi B đã pass.

### 16.4. Configuration defaults và actuator endpoints

Framework major mới có thể đổi tên property, bỏ property deprecated hoặc thay default. Việc cấu hình không còn có hiệu lực đôi khi không tạo exception; ứng dụng vẫn start nhưng hoạt động khác.

Nên bật cơ chế phát hiện unknown/deprecated configuration theo khả năng framework và kiểm tra những settings quan trọng sau khi nâng.

## 17. Dữ liệu và giao thức sống qua nhiều phiên bản

Ngay cả khi tách JDK và framework thành hai đợt, dữ liệu trong database, Redis, session và broker có thể **tồn tại xuyên qua cả hai lần deploy**.

Ví dụ:

~~~text
App v1 / Framework A / JDK X
      |
      +--> Cache value v1
      +--> Session v1
      +--> Kafka event v1
      |
   Nâng JDK
      v
App v1 / Framework A / JDK Y
      |
      +--> Vẫn đọc dữ liệu v1
      |
   Nâng Framework
      v
App v2 / Framework B / JDK Y
      |
      +--> Phải đọc dữ liệu cũ còn tồn tại
~~~

Framework major có thể đổi serializer mặc định, session principal type, Jackson settings, entity names hoặc event mapping. Nếu chỉ test trên dữ liệu do phiên bản mới tạo, rủi ro tương thích bị bỏ sót.

Các nguyên tắc:

- Version payload/schema thay vì gắn lâu dài vào Java class serialization nếu có thể.
- Khi thay schema, nâng **reader trước writer** trong hệ thống có rolling deploy.
- Dùng expand–migrate–contract cho database và persisted state.
- Giữ adapter/compatibility reader tới khi hết TTL, retention, DLQ/replay và backup policy.
- Không xóa session, idempotency keys hoặc messages chỉ để tránh lỗi migration.
- Kiểm tra rollback cả về **code** lẫn **dữ liệu**: app cũ có đọc được dữ liệu mới hay không.

Việc tách JDK khỏi framework chỉ giảm số biến thay đổi, không thay thế kế hoạch tương thích dữ liệu.

## 18. Canary, rolling deployment và dark launch

Để giảm rủi ro, có thể chọn một tập instance chạy tổ hợp mới trước khi rollout toàn hệ thống.

### 18.1. Canary JDK-first

Nếu framework hiện tại hỗ trợ cả JDK cũ và mới:

~~~text
90% traffic -> Framework A + JDK X
10% traffic -> Framework A + JDK Y
~~~

Dùng cùng artifact và cùng loại request/workload khi phù hợp. So sánh CPU, heap, p95/p99, error rate, TLS và log. Nếu lỗi chỉ có ở nhóm JDK Y, khoanh vùng vào JDK/environment.

### 18.2. Canary framework-major

Sau khi JDK Y ổn định:

~~~text
90% traffic -> Framework A + JDK Y
10% traffic -> Framework B + JDK Y
~~~

So sánh HTTP contracts, persistence behavior, security flows, serialization và metrics framework. Nếu lỗi chỉ xuất hiện ở nhóm framework B, nguyên nhân được thu hẹp.

### 18.3. Shared-state có thể phá tính cô lập của canary

Một nhóm canary có thể ghi cache/session/event schema mới vào kho dùng chung và khiến nhóm cũ lỗi. Vì vậy cần kiểm tra:

- Cache key namespace và serializer.
- Session compatibility giữa các node.
- Database schema và transactional migrations.
- Message producer/consumer schema compatibility.
- Token signing key, claims và cookie settings.
- Feature flags chỉ kích hoạt ở canary có làm reader cũ không hiểu dữ liệu không.

Canary application không tự cô lập **data contract**. Nếu chưa có hai chiều tương thích, phải version namespace hoặc giới hạn writer, không phát dữ liệu mới cho consumer cũ ngoài ý muốn.

## 19. Cách dùng feature flag đúng phạm vi

Feature flag có thể giúp tách thay đổi hành vi framework ra khỏi runtime deploy. Ví dụ sau khi nâng framework major, có thể giữ đường xử lý cũ làm mặc định và bật đường mới cho một nhóm traffic.

Tuy nhiên, không phải mọi thay đổi đều có thể giấu sau flag:

- Classfile/JDK compatibility ảnh hưởng startup và load class.
- Namespace `javax`→`jakarta` có thể tác động compile/linking, không thể đơn giản chọn runtime bằng boolean.
- Một ORM migration đã đổi schema hoặc ghi dữ liệu khác có thể không rollback bằng flag.
- Security default đã thay framework layer có thể ảnh hưởng request trước khi feature code chạy.

Feature flag hữu ích cho những đường logic có thể giữ song song và được kiểm chứng. Không nên dùng flag như lý do để bỏ qua ma trận support hoặc thay đổi dữ liệu.

## 20. Release train và commit strategy

Để dễ review, hãy chia thay đổi thành các nhóm có mục đích:

| Nhóm thay đổi | Mục tiêu | Không nên gộp tùy tiện |
|---|---|---|
| Build baseline | Wrapper, plugin tương thích, test infrastructure | Feature nghiệp vụ |
| JDK adaptation | Toolchain, JVM config, API JDK thay thế | Framework major |
| Dependency maintenance | Patch/minor hỗ trợ runtime mục tiêu | Đổi hàng loạt dependency không liên quan |
| Framework API migration | Annotations, configs, package namespace | Nâng JDK thêm lần nữa |
| Data contract migration | Schema, cache/session/message adapters | Xóa dữ liệu không kiểm soát |
| Deployment | Container image, runtime, flags, health checks | Thay API công khai ngoài phạm vi |
| Cleanup | Bỏ workaround, deprecated code, bridge | Nhiều thay đổi mang rủi ro chưa test |

Không cần mỗi mục là một PR trong mọi tổ chức, nhưng mỗi mục phải **có bằng chứng và khả năng quy trách nhiệm**. Nếu tất cả thay đổi đều nằm trong một commit, việc phân tích lỗi và rollback có thể khó hơn nhiều.

### 20.1. Không dùng “green build” làm gate duy nhất

Một PR đổi framework major có thể compile xanh nhưng security filter order thay đổi; một PR nâng JDK có thể test xanh nhưng TLS tới hệ thống đối tác thất bại. Cần gate theo rủi ro thực tế:

- Compilation và test coverage.
- API/contract compatibility.
- Integration với DB, cache, broker và third parties.
- Security regression.
- Runtime/startup/performance.
- Packaging/production-like deployment.
- Rollback và state compatibility.

## 21. Một ví dụ hoàn chỉnh: hệ thống REST + database + Kafka

Giả sử một dịch vụ Java gồm:

~~~text
REST API + security + ORM
          |
          +--> PostgreSQL
          +--> Redis sessions/cache
          +--> Kafka producer/consumer
          +--> External payment API
~~~

Đội dự án muốn chuyển từ JDK X sang JDK Y và nâng framework A lên B.

### 21.1. Inventory và support matrix

Ghi:

- Framework A bản patch hiện tại có hỗ trợ JDK Y không?
- Framework B có yêu cầu JDK tối thiểu nào?
- JDBC driver, Kafka client, Redis client, ORM, security libs có tương thích không?
- Có library/agent sử dụng internal JDK APIs không?
- Có Java serialized cache/session object từ framework A không?
- App v1 và v2 sẽ chạy đồng thời bao lâu?
- Có database migration không thể rollback không?

### 21.2. Nếu hỗ trợ bước B (JDK-first)

1. Nâng build tool/plugins tối thiểu để chạy trên JDK Y.
2. Giữ framework A và API contract, chỉnh các API JDK không còn phù hợp nếu có.
3. Build với `--release` cũ nếu cần; test JDK Y.
4. Tạo image JDK Y và canary cùng app artifact.
5. Xác nhận TLS tới payment API, database, Kafka, Redis và metrics/GC.
6. Rollout JDK Y.
7. Sau giai đoạn quan sát, bắt đầu nhánh framework B.
8. Nâng framework BOM, namespace/config, security, persistence và serialization.
9. Test dữ liệu/session/event tạo bởi phiên bản trước.
10. Rollout framework B với adapter/schema compatibility, sau đó dọn bridge.

### 21.3. Nếu không hỗ trợ bước B

1. Kiểm tra patch/minor framework A hoặc một JDK trung gian.
2. Nếu có bridge, chọn chuỗi phiên bản được hỗ trợ.
3. Nếu không có bridge, thiết kế nâng phối hợp có checkpoints riêng cho build, framework API, JDK/runtime và data schema.
4. Tăng mức kiểm thử integration, rolling compatibility và rollback vì không có môi trường trung gian production hợp lệ.
5. Ghi rõ tại sao tách hoàn toàn không khả thi, tránh tuyên bố “chúng tôi đã thử nên biết framework không hỗ trợ” nếu chưa có bằng chứng vendor/test.

### 21.4. Ví dụ bảng theo dõi

| Giai đoạn | JDK | Framework | Thay đổi chính | Gate |
|---|---|---|---|---|
| A baseline | X | A | Không đổi | Existing tests + metrics |
| A' maintenance | X | A patched | Chỉ bản vá cần thiết | Regression và dependency diff |
| B runtime | Y | A patched | JDK/container/toolchain | TLS, agents, GC, integration, SLO |
| D framework | Y | B | API/BOM/config/framework | Contract, ORM, security, data, rollback |
| Cleanup | Y | B | Gỡ bridge và flags | Historical data/retention evidence |

Nếu B không hợp lệ, thay bảng bằng lộ trình được hỗ trợ; không chạy B trong production chỉ để lấp ô trong kế hoạch.

## 22. Đo hiệu năng theo từng trục thay đổi

Nâng JDK và framework có thể đều ảnh hưởng hiệu năng, nhưng theo các cơ chế khác nhau.

**JDK có thể tác động** JIT compilation, GC pauses, heap sizing, crypto throughput, startup và thread scheduling.

**Framework có thể tác động** request pipeline, serialization, ORM query count, proxy creation, dependency injection, caching và tracing overhead.

Để đo đúng:

- Dùng cùng test data và workload pattern.
- Có warm-up phù hợp, tách cold-start khỏi steady-state.
- So p50/p95/p99, throughput, error rate, CPU, heap/GC và connection pool.
- Giữ nguyên resource limits và container environment nếu có thể.
- Theo dõi SQL query count, external calls và serialized payload size.
- Lặp lại các phép đo để giảm ảnh hưởng noise, không chỉ lấy một lần chạy.
- Không kết luận “JDK mới nhanh/chậm hơn” nếu framework hoặc dependencies cũng đã đổi trong cùng benchmark.

Có thể xuất kết quả theo A/B/D để biết mức thay đổi phát sinh chủ yếu ở đâu.

## 23. Bảo mật và chính sách hỗ trợ có thể buộc nâng nhanh hơn

Khi framework cũ đã hết hỗ trợ, trì hoãn nâng major quá lâu chỉ để tách JDK có thể tăng rủi ro bảo mật. Ngược lại, chạy JDK đã hết hỗ trợ lâu ngày vì chờ framework có thể cũng không chấp nhận được.

Quyết định nên dựa vào:

- Support lifecycle của JDK vendor và framework.
- Các bản vá CVE đang cần.
- Tính khả thi của phiên bản cầu nối.
- Rủi ro runtime không được hỗ trợ.
- Khả năng kiểm thử và rollback.
- Ảnh hưởng nghiệp vụ khi nâng phối hợp hoặc trì hoãn.
- Số lượng integrations và third-party libraries phải cập nhật.

**Tách bước nâng cấp là công cụ giảm rủi ro, không phải mục tiêu tuyệt đối.** Nếu việc tách buộc hệ thống ở lâu trên một runtime/framework không được bảo trì, có thể cần ưu tiên lộ trình nâng phối hợp nhưng kiểm soát chặt.

## 24. Rollback: phân biệt code, runtime và dữ liệu

Một trong những lợi ích của việc tách bước là rollback dễ hơn, nhưng chỉ khi state không bị thay đổi một chiều.

### 24.1. Rollback bước JDK

Nếu cùng artifact/framework và dữ liệu không thay đổi, rollback có thể chủ yếu là đổi container/JDK runtime image. Vẫn phải kiểm tra:

- Artifacts có bytecode/API target phù hợp JDK cũ không.
- JDK mới có làm dữ liệu được lưu theo format mà JDK cũ không đọc được không.
- Keystore, TLS, timezone, native libraries và config có tương thích không.
- Các job/messages phát trong khi chạy JDK mới có khác format không.

### 24.2. Rollback bước framework major

Khó hơn nếu framework mới đã:

- Thay database schema hoặc dữ liệu.
- Ghi cache/session theo serializer mới.
- Phát event JSON/Avro/Protobuf schema mới.
- Đổi cookie/session token format hoặc security claims.
- Chuyển entity/class names khiến Java deserializer cũ không đọc được.
- Thay migration metadata hoặc outbox/inbox structures.

Phải có chiến lược expand–contract, dual-read hoặc compatibility adapter phù hợp. Chỉ quay lại framework JAR cũ không bảo đảm an toàn.

### 24.3. Tính điểm không thể quay lại

Một đợt deploy có thể có mốc **point of no return**: sau khi schema cũ bị xóa, khóa ký cũ bị thu hồi hoặc producer phát một loại event mà consumer cũ không xử lý được, rollback về phiên bản cũ không còn đơn giản.

Hãy xác định mốc này trước rollout và có điều kiện phê duyệt riêng. Việc tách JDK trước giúp giảm một số rủi ro, nhưng không loại bỏ trách nhiệm quản lý điểm không thể quay lại của framework/data migration.

## 25. Triệu chứng và cách tìm trục gây lỗi

| Triệu chứng | Trục nghi ngờ chính | Điều cần xác minh |
|---|---|---|
| `UnsupportedClassVersionError` | JDK/bytecode/toolchain | Classfile target và JVM thực sự đang chạy |
| `InaccessibleObjectException` | JDK encapsulation hoặc framework reflection | Library gọi reflection, JDK version, opens |
| `NoClassDefFoundError` sau major update | Framework/dependency hoặc runtime | BOM, class name, removed API và classpath |
| Lỗi `javax.*` / `jakarta.*` | Framework/platform API migration | Namespace, container/JPA/validation versions |
| Không tìm thấy bean | Framework | Component scanning, annotations, conditions |
| HTTP route/security behavior khác | Framework | Routing/filter/authorization config |
| TLS handshake fail chỉ trên JDK mới | JDK security/provider hoặc client library | Disabled algorithms, trust, protocol |
| ORM SQL/query khác sau framework major | Framework/dependencies | Hibernate/dialect, generated SQL, transaction |
| JSON payload thay đổi sau major | Serializer/framework | Jackson/message converters, contract fixtures |
| Startup/GC/p99 thay đổi sau JDK-only | JDK/runtime | JVM options, heap, GC, agents, workload |
| Build script không chạy trên JDK mới | Build tools/plugins | Wrapper, JVM build, Gradle/Maven compatibility |
| Cache/session cũ không đọc được | Framework serializer hoặc class evolution | Golden fixtures, schema version, class names |
| Rollback vẫn lỗi sau khôi phục code | Shared data contract | DB/cache/message/token do version mới đã ghi |

Không coi bảng là kết luận tự động. Một `NoSuchMethodError` cũng có thể xuất hiện vì dependency binary mismatch khi chỉ đổi JDK mà một agent/library được nâng. Luôn kiểm tra artifact và stack trace cụ thể.

## 26. Quy trình điều tra regression theo so sánh A–B–D

Nếu đã có B hợp lệ và pass:

1. Reproduce lỗi trên D.
2. Kiểm tra lỗi có xuất hiện trên B cùng JDK hay không.
3. Nếu không, so dependency/config/framework diff giữa B và D.
4. Nếu có, so JDK/runtime/toolchain diff giữa A và B.
5. Chạy test tối thiểu với cùng input, DB, broker và environment.
6. Xem root cause; ghi version class/provider/driver được nạp.
7. Xác nhận fix bằng regression test trên các tổ hợp vẫn được hỗ trợ.
8. Ghi vào change log lỗi thuộc trục JDK, framework hay một dependency bắt buộc nâng.

Nếu không có B, dùng các mốc integration branch, unit/integration tests theo component, dependency diff và rollback checkpoint để thu hẹp nguyên nhân. Không tạo tổ hợp không được hỗ trợ trong production để điều tra mà không có kiểm soát rủi ro.

## 27. Acceptance criteria cho từng giai đoạn

### 27.1. Bước JDK

- [ ] JDK đích nằm trong phạm vi hỗ trợ của framework/dependencies đang dùng.
- [ ] Build tool và plugins chạy được trên JDK/toolchain đích.
- [ ] Compiler release target rõ ràng.
- [ ] Unit/integration tests pass, không phát sinh regression không được xử lý.
- [ ] TLS, database, messaging và security providers hoạt động.
- [ ] Không có Java agents/library native không tương thích.
- [ ] Startup, heap/GC, latency và error rate nằm trong ngưỡng chấp nhận.
- [ ] Tài liệu vận hành và JVM flags được cập nhật.
- [ ] Runtime rollback đã được thử trong phạm vi dữ liệu hiện tại.

### 27.2. Bước framework major

- [ ] Framework target và ecosystem được hỗ trợ trên JDK đã chọn.
- [ ] API/annotation/config migrations đã được áp dụng.
- [ ] BOM/third-party starters, security và ORM dependencies được kiểm soát.
- [ ] HTTP/gRPC/events contracts và external integrations đã được test.
- [ ] Session/cache/serialized data cũ có thể được đọc theo thời gian hỗ trợ.
- [ ] Database migration áp dụng expand–contract khi yêu cầu.
- [ ] Canary/mixed deployment có hai chiều tương thích cần thiết.
- [ ] Observability, management endpoints, tracing/metrics hoạt động.
- [ ] Rollback được thử, có xử lý điểm không thể quay lại.
- [ ] Legacy workaround chỉ được gỡ khi có bằng chứng phù hợp.

## 28. Những nhận định dễ sai

**“Nâng JDK và nâng framework đều là nâng Java, nên làm cùng một PR sẽ nhanh hơn.”** Có thể giảm số PR nhưng tăng biến số và thời gian điều tra regression. Cần so tổng rủi ro và chi phí vận hành, không chỉ thời gian gõ code.

**“Framework cũ compile được trên JDK mới tức vendor hỗ trợ.”** Không đúng. Compile, smoke test và support policy là các mức bằng chứng khác nhau.

**“Framework mới sẽ sửa hết lỗi JDK mới.”** Không chắc. Build plugin, Java agent, JDBC driver, TLS provider hoặc custom code vẫn có compatibility riêng.

**“Luôn phải nâng JDK trước.”** Sai nếu framework cũ không hỗ trợ JDK mục tiêu. Khi đó tìm bridge, JDK trung gian hoặc nâng phối hợp.

**“Luôn phải nâng framework trước.”** Sai nếu framework major yêu cầu JDK tối thiểu cao hơn runtime hiện tại.

**“Một runtime JDK mới mà giữ --release cũ nghĩa là chỉ dùng JDK cũ.”** Không đúng. `--release` giới hạn compiler API/bytecode, nhưng runtime behavior của JVM mới vẫn khác.

**“Chỉ cần sửa javax thành jakarta là xong major migration.”** Không đủ. Servlet container, persistence, security, validation, dependencies, configs và external contracts đều cần kiểm tra.

**“Canary 10% cô lập hoàn toàn thay đổi.”** Không đúng nếu 10% instance ghi schema mới vào Redis, database hoặc broker dùng chung.

**“Rollback framework chỉ là chạy lại image cũ.”** Không đúng sau khi database/session/message đã được writer mới thay đổi một chiều.

**“Dùng nhiều --add-opens nghĩa là dự án đã tương thích JDK mới.”** Không đủ. Đây có thể chỉ là cách tạm tránh lỗi reflective access và làm giảm encapsulation.

**“Thành công một lần build và unit tests nghĩa là nâng cấp đã hoàn tất.”** Không đủ đối với hệ thống có DB, queue, security, production agents và performance requirements.

## 29. Checklist lập kế hoạch tách nâng cấp

- [ ] Đã xác định phiên bản JDK cũ/mới (vendor, update) và framework cũ/mới cụ thể.
- [ ] Đã lập ma trận A/B/C/D, phân biệt supported, unsupported và unknown.
- [ ] Đã xem compatibility matrix của framework core, build plugins và ecosystem.
- [ ] Đã tìm bản patch/minor hoặc JDK trung gian có thể làm bridge.
- [ ] Đã chọn thứ tự JDK-first, framework-first hoặc coordinated migration có lý do.
- [ ] Đã phân biệt JDK build, compiler toolchain, `--release` và production runtime.
- [ ] Đã đóng băng các thay đổi không liên quan trong từng giai đoạn khi khả thi.
- [ ] Đã lưu baseline source, dependency tree, container/JVM config và test metrics.
- [ ] Đã kiểm tra các thư viện dùng API nội bộ JDK hoặc bytecode instrumentation.
- [ ] Đã kiểm tra ORM, security, web, JSON, validation và application server.
- [ ] Đã bổ sung test với persisted data/session/cache/message từ phiên bản cũ.
- [ ] Đã thiết kế rollout canary/mixed-version an toàn cho shared-state.
- [ ] Đã xác định dữ liệu và API nào không thể rollback.
- [ ] Đã có rollback artifact/runtime/data strategy cho từng giai đoạn.
- [ ] Đã theo dõi performance, GC, TLS, tracing, errors và business KPIs.
- [ ] Đã ghi rõ workaround tạm, owner và điều kiện loại bỏ.
- [ ] Đã bảo đảm trạng thái cuối nằm trong tập vendor support theo chính sách.
- [ ] Đã lưu kết quả test và quyết định kỹ thuật cho các tổ hợp không khả thi.

## 30. Kết luận

**Tách nâng JDK khỏi nâng major framework** là chiến lược giảm số biến thay đổi, tăng khả năng xác định nguyên nhân regression và đơn giản hóa kiểm thử/rollback trong Java Advance Compatibility Migration. Khi framework hiện tại hỗ trợ JDK mới, có thể nâng JDK trước rồi nâng framework. Khi framework mới hỗ trợ JDK hiện tại, có thể làm ngược lại. Trong cả hai trường hợp, các bản patch/minor và JDK trung gian có thể là cầu nối giúp tránh một đợt chuyển đổi quá lớn.

Không phải lúc nào các ô trung gian trong ma trận JDK × framework cũng hợp lệ. Nếu framework cũ không hỗ trợ JDK đích và major framework mới yêu cầu JDK cao hơn hiện tại, phải lập lộ trình cầu nối hoặc **nâng phối hợp có kiểm soát**, không chạy tổ hợp không được hỗ trợ chỉ để giữ hình thức “hai giai đoạn”.

Thành công không được xác định bằng việc ứng dụng compile hoặc khởi động đơn lẻ. Cần chứng minh từng bước bằng artifact, dependency graph, integration/contract tests, dữ liệu cũ, các chỉ số vận hành và khả năng rollback. Nguyên tắc thực hành là: **thay đổi từng trục khi có thể, ghi rõ các thay đổi phụ trợ bắt buộc, và chỉ chuyển sang giai đoạn tiếp theo sau khi giai đoạn trước có bằng chứng tương thích đủ mạnh**.
