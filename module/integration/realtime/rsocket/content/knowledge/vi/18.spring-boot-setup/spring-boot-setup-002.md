# Quản lý phiên bản tương thích bằng dependency management của Spring Boot

Một ứng dụng RSocket dùng Spring Boot thường có nhiều thư viện phối hợp: Spring Boot, Spring Framework, Spring Messaging, Reactor, RSocket Java và transport như Reactor Netty. Các thư viện này có quan hệ phụ thuộc và được phát triển theo những nhịp phát hành khác nhau. Nếu tự chọn phiên bản cho từng dependency, dự án có thể vô tình ghép các thành phần không tương thích.

Spring Boot giải quyết phần lớn công việc này bằng dependency management. Mỗi phiên bản Spring Boot đi kèm một bộ phiên bản dependency đã được kiểm tra cùng nhau, được công bố qua BOM (Bill of Materials) <code>spring-boot-dependencies</code>. Khi dùng Spring Boot parent hoặc import BOM đúng cách, ta khai báo các starter mà không cần gắn phiên bản riêng cho từng thư viện.

Với RSocket, cách làm này giúp Spring Boot, Spring Messaging, Reactor và các dependency RSocket do BOM quản lý đi cùng một bộ phiên bản nhất quán. Nhờ vậy, nhóm phát triển tập trung vào route, payload, stream và cấu hình transport thay vì tự giải quyết xung đột phiên bản ở từng lần build.

## 1. Vì sao cần quản lý phiên bản tập trung?

Một ứng dụng RSocket có thể có cây dependency như sau:

~~~text
Ứng dụng Spring Boot
       |
       +-- spring-boot-starter-rsocket
       |       |
       |       +-- Spring Messaging
       |       +-- RSocket integration
       |       +-- Reactor / transport dependencies
       |
       +-- spring-boot-starter-webflux
       |       |
       |       +-- Spring WebFlux
       |       +-- Reactor
       |       +-- Reactor Netty
       |
       +-- spring-boot-starter-test
               |
               +-- JUnit
               +-- AssertJ
               +-- Spring Test
~~~

Các nhánh có thể cùng phụ thuộc vào một thư viện. Ví dụ, starter RSocket và WebFlux đều cần Reactor. Nếu một dependency trực tiếp khai báo phiên bản Reactor khác với phiên bản mà Spring Boot quản lý, Maven hoặc Gradle có thể chọn phiên bản không phù hợp với các thư viện Spring còn lại.

Một số rủi ro khi quản lý phiên bản thủ công:

- Lệch phiên bản giữa Spring Boot và Spring Framework.
- Reactor Core không tương thích với các module Reactor hoặc Spring đang dùng.
- RSocket Java khác phiên bản mà tích hợp Spring đã được kiểm thử.
- Netty hoặc các thư viện transport bị kéo lên phiên bản không tương thích.
- Build chạy được nhưng lỗi xuất hiện khi khởi động context, tạo connection hoặc xử lý payload.

Dependency management cung cấp một nguồn phiên bản thống nhất. Dự án chỉ cần chọn phiên bản Spring Boot phù hợp, sau đó để BOM quản lý các dependency nằm trong danh mục của release đó.

## 2. BOM của Spring Boot là gì?

BOM là một POM đặc biệt chứa các khai báo <code>dependencyManagement</code>. Nó xác định phiên bản mặc định cho các thư viện mà một nền tảng sử dụng. BOM không tự thêm tất cả dependency vào ứng dụng; nó chỉ cung cấp phiên bản khi dependency được khai báo.

Spring Boot công bố BOM:

<code>org.springframework.boot:spring-boot-dependencies</code>

BOM này quản lý phiên bản của các thư viện trong hệ sinh thái Spring Boot, gồm các thành phần Spring, Reactor và những thư viện bên thứ ba mà release tương ứng có đưa vào dependency management. Danh sách cụ thể có thể thay đổi theo phiên bản Spring Boot.

Ví dụ, khi dự án khai báo:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-rsocket</artifactId>
</dependency>
~~~

Maven lấy phiên bản starter từ dependency management đang có hiệu lực. Các dependency bắc cầu của starter cũng được giải quyết theo cây phiên bản mà BOM cung cấp, nếu chúng nằm trong danh mục được quản lý.

Điểm cần nhớ:

- BOM quản lý phiên bản; nó không tự đưa dependency vào classpath.
- Starter là dependency thực tế mà ứng dụng khai báo.
- Phiên bản của starter và dependency bắc cầu được chọn theo BOM đang có hiệu lực.
- BOM chỉ quản lý những dependency được liệt kê trong BOM đó.
- Mỗi release Spring Boot có BOM tương ứng; không nên lấy BOM của một release rồi ghép tùy ý với starter hoặc plugin từ release khác.

## 3. Dùng Spring Boot parent trong Maven

Cách đơn giản nhất với Maven là kế thừa từ <code>spring-boot-starter-parent</code>. Parent này đã nhập BOM <code>spring-boot-dependencies</code> và cung cấp cấu hình mặc định cho build Maven, chẳng hạn quản lý phiên bản plugin, encoding và cấu hình compiler.

Ví dụ POM:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>rsocket-service</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-rsocket</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Phiên bản <code>3.5.0</code> trong ví dụ chỉ minh họa cách khai báo. Khi tạo dự án, hãy chọn một phiên bản Spring Boot đã được tổ chức chuẩn hóa và tương thích với phiên bản Java của môi trường triển khai. Giữ nguyên phiên bản đó trong parent và các plugin liên quan.

Ở phần dependencies, không cần khai báo version cho <code>spring-boot-starter-rsocket</code> hoặc <code>spring-boot-starter-test</code>. Maven lấy phiên bản đã được parent quản lý. Nếu tự thêm version cho từng starter, dự án có thể vô tình ghi đè lựa chọn của BOM.

### Khi dự án đã có parent riêng

Maven chỉ cho phép một parent trực tiếp. Nếu công ty đã có parent POM riêng, dự án không thể đồng thời kế thừa <code>spring-boot-starter-parent</code>. Khi đó, có thể import BOM của Spring Boot trong <code>dependencyManagement</code>.

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-boot.version>3.5.0</spring-boot.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-rsocket</artifactId>
    </dependency>
</dependencies>
~~~

Trong ví dụ rút gọn này, giá trị ở property và BOM version cần được giữ đồng nhất khi dự án thay đổi release. Khi import BOM theo cách này, dependency versions được quản lý nhưng các cấu hình plugin mặc định từ <code>spring-boot-starter-parent</code> không tự được kế thừa. Vì vậy, dự án cần tự cấu hình phiên bản và execution của <code>spring-boot-maven-plugin</code>, compiler plugin và các plugin build khác theo chuẩn của tổ chức.

Không cần import BOM thêm lần nữa nếu đã kế thừa từ Spring Boot parent. Chọn một cơ chế quản lý dependency rõ ràng để tránh cấu hình trùng lặp khó đọc.

## 4. Dùng Spring Boot dependency management với Gradle

Gradle có thể quản lý phiên bản bằng plugin <code>io.spring.dependency-management</code> hoặc BOM thông qua native platform support. Spring Boot Gradle Plugin được thiết kế để phối hợp với dependency management của Spring Boot.

Ví dụ dùng plugin:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Các version trong phần plugins là ví dụ minh họa. Thay chúng bằng phiên bản plugin được dự án lựa chọn. Plugin dependency management tích hợp BOM Spring Boot để các dependency starter không cần ghi version riêng.

### Dùng Gradle native platform

Gradle có sẵn cơ chế platform để nhập BOM:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<boot-version>'
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:<boot-version>'
    )

    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Thay <code>&lt;boot-version&gt;</code> bằng cùng một phiên bản Spring Boot đã chọn cho plugin. Native platform dùng cơ chế dependency constraints của Gradle. Nếu chọn cách này, hãy cấu hình build nhất quán và tránh nhập BOM nhiều lần bằng cả plugin dependency management lẫn platform trừ khi có lý do cụ thể.

Với Gradle Kotlin DSL, cú pháp tương ứng:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "<boot-version>"
}

dependencies {
    implementation(
        platform("org.springframework.boot:spring-boot-dependencies:<boot-version>")
    )
    implementation("org.springframework.boot:spring-boot-starter-rsocket")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

## 5. Các dependency thường dùng trong dịch vụ RSocket

Một dịch vụ RSocket Spring Boot thường bắt đầu với starter RSocket. Có thể bổ sung WebFlux, Actuator hoặc thư viện kiểm thử theo nhu cầu thực tế.

| Dependency | Mục đích |
| --- | --- |
| <code>spring-boot-starter-rsocket</code> | Tích hợp RSocket với Spring Messaging và cấu hình Spring Boot. |
| <code>spring-boot-starter-webflux</code> | Dùng WebFlux và Reactor cho HTTP reactive hoặc các thành phần reactive liên quan. |
| <code>spring-boot-starter-actuator</code> | Cung cấp endpoint và metric vận hành nếu ứng dụng cần. |
| <code>spring-boot-starter-test</code> | Công cụ kiểm thử Spring Boot, JUnit và assertion. |
| <code>reactor-test</code> | Kiểm thử Publisher bằng StepVerifier; phiên bản cần được quản lý đồng bộ với Reactor. |

Không phải ứng dụng nào cũng cần khai báo trực tiếp tất cả các thư viện trên. Hãy thêm starter theo chức năng đang dùng. Trước khi thêm <code>rsocket-core</code>, <code>reactor-core</code> hoặc Netty trực tiếp, kiểm tra xem starter đã cung cấp chúng qua dependency bắc cầu hay chưa.

Nếu cần gọi API cấp thấp của RSocket Java mà starter không đưa dependency cần thiết vào compile classpath, hãy khai báo dependency trực tiếp nhưng vẫn để BOM quản lý version nếu BOM của release đó có quản lý artifact. Không nên chọn một version RSocket Java độc lập chỉ vì đó là bản mới nhất trên Maven Central.

## 6. Dependency management giúp tương thích những lớp nào?

Trong một ứng dụng RSocket, cần xem xét nhiều lớp tương thích:

| Lớp | Thành phần | Điều cần giữ đồng bộ |
| --- | --- | --- |
| Nền tảng ứng dụng | Spring Boot | Chọn một release line và dùng nhất quán cho plugin, parent và BOM. |
| Framework | Spring Framework, Spring Messaging | Dùng phiên bản mà release Spring Boot đã quản lý. |
| Reactive | Reactor Core, Reactor Test, Reactor Netty | Tránh trộn các release train Reactor không tương thích. |
| Giao thức | RSocket Java | Dùng phiên bản được Boot BOM quản lý hoặc override có chủ đích. |
| Transport | Netty và thư viện liên quan | Tránh ép một module Netty đơn lẻ lệch khỏi bộ phiên bản được quản lý. |
| Build | Maven/Gradle plugin | Quản lý plugin riêng; BOM dependency không tự quản lý mọi plugin build. |

BOM Spring Boot giúp chọn các phiên bản đã được kiểm tra cùng nhau, nhưng không bảo đảm mọi thư viện bên ngoài BOM đều tương thích. Nếu dự án thêm một SDK, serializer hoặc thư viện transport bên thứ ba, cần kiểm tra yêu cầu phiên bản của chính thư viện đó.

## 7. Không tự ý override phiên bản dependency

Đôi khi dự án cần nâng một thư viện do bản vá bảo mật, lỗi đã biết hoặc yêu cầu tích hợp. Việc override có thể cần thiết, nhưng nên là quyết định có chủ đích.

Trước khi override:

1. Xác định dependency nào đang được BOM quản lý và phiên bản thực tế trong cây dependency.
2. Đọc ghi chú phát hành của Spring Boot, Spring Framework, Reactor hoặc RSocket Java liên quan.
3. Kiểm tra thư viện được nâng có yêu cầu phiên bản tối thiểu của các thành phần khác hay không.
4. Chỉ override phạm vi cần thiết, không nâng hàng loạt dependency bắc cầu theo cảm tính.
5. Chạy kiểm thử khởi động ứng dụng, kết nối TCP/WebSocket và các interaction model được dùng.
6. Ghi lại lý do override và kế hoạch bỏ override khi Spring Boot release mới đã tích hợp bản vá.

Với Maven, có thể khai báo version cụ thể trong dependency management của dự án để ghi đè phiên bản do BOM nhập vào:

Một fragment Maven có thể tham chiếu property đã được dự án phê duyệt:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>${approved.reactor.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Property <code>approved.reactor.version</code> phải được khai báo với một phiên bản thực tế đã được phê duyệt và kiểm chứng tương thích với Spring Boot release đang chạy. Khi dùng Gradle native platform, có thể dùng constraint hoặc dependency version được tổ chức phê duyệt, nhưng cần tránh tạo nhiều nguồn version cạnh tranh.

Không nên ghi version trực tiếp cho starter chỉ để cố sửa một dependency bắc cầu. Starter version và phiên bản của thư viện con là hai cấp khác nhau. Hãy xác định chính xác artifact gây xung đột trước khi thay đổi.

## 8. Cấu hình RSocket sau khi dependency đã được quản lý

Khi dependency đã được chọn từ BOM, Spring Boot có thể cấu hình RSocket server bằng properties. Ví dụ server TCP:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 7000
~~~

Một controller có thể khai báo route:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class TelemetryController {

    @MessageMapping("telemetry.watch")
    public Flux<TelemetryEvent> watch(TelemetryRequest request) {
        return telemetryService.watch(request.deviceId());
    }
}
~~~

Các class <code>TelemetryEvent</code>, <code>TelemetryRequest</code> và <code>telemetryService</code> là thành phần nghiệp vụ của ứng dụng. Spring Messaging ánh xạ route tới method; Reactor biểu diễn luồng phản hồi; RSocket đảm nhận truyền message và điều tiết demand.

Nếu dùng WebSocket, cấu hình transport và endpoint mapping theo yêu cầu client/server của ứng dụng. Dependency management không tự chọn TCP hay WebSocket; nó chỉ giúp các thư viện dùng để triển khai transport có phiên bản nhất quán.

## 9. Kiểm tra cây dependency sau khi build

Không nên chỉ nhìn file POM hoặc build.gradle rồi kết luận phiên bản thực tế. Hãy kiểm tra dependency graph mà Maven hoặc Gradle đã giải quyết.

Với Maven:

~~~bash
mvn dependency:tree
~~~

Để lọc các nhóm thư viện liên quan tới RSocket:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=org.springframework,org.springframework.boot,io.projectreactor,io.rsocket,io.netty
~~~

Đầu ra cho biết dependency nào kéo một thư viện vào, phiên bản nào được chọn và có phiên bản nào bị bỏ do conflict resolution. Với Maven, có thể dùng thêm <code>help:effective-pom</code> để kiểm tra cấu hình parent và dependency management sau khi kế thừa/import BOM.

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Để xem vì sao một dependency có phiên bản cụ thể:

~~~bash
./gradlew dependencyInsight --dependency reactor-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency rsocket-core --configuration runtimeClasspath
~~~

Hãy xác nhận:

- Chỉ có release line Spring Boot mà dự án đã chọn.
- Spring Framework và Spring Messaging nằm trong bộ phiên bản do Boot quản lý.
- Reactor Core và Reactor Netty không bị ép sang phiên bản ngoài kế hoạch.
- RSocket Java và transport dependency không có xung đột không giải thích được.
- Test runtime không dùng phiên bản Reactor khác với ứng dụng nếu không có chủ đích.

Nếu dependency tree hiển thị nhiều version, điều đó không luôn có nghĩa build sai; Maven và Gradle có cơ chế chọn version. Tuy nhiên, cần hiểu lý do chọn version và xác nhận các module liên quan tương thích với nhau.

## 10. Kiểm thử tương thích sau khi nâng Spring Boot

Nâng Spring Boot có thể kéo theo thay đổi phiên bản Spring Framework, Reactor, RSocket Java, Netty và các thư viện khác. Một build thành công mới chỉ xác nhận compile và resolve dependency; chưa chứng minh session RSocket hoạt động đúng khi runtime.

Với dịch vụ RSocket, nên kiểm tra tối thiểu:

1. Ứng dụng Spring Boot khởi động và server bind đúng transport, port hoặc WebSocket path.
2. Client tạo được session và hoàn tất SETUP.
3. Request-response gọi được route và giải mã payload đúng.
4. Fire-and-forget được gửi theo hợp đồng ứng dụng.
5. Request-stream và request-channel phát dữ liệu đúng, có backpressure và cancellation.
6. Metadata được mã hóa/giải mã theo MIME type đã thống nhất.
7. Lỗi ứng dụng và lỗi transport được truyền tới client đúng cách.
8. Reconnect hoặc Resume hoạt động theo cấu hình mà ứng dụng hỗ trợ.

Có thể dùng <code>StepVerifier</code> từ <code>reactor-test</code> để kiểm tra Publisher, đồng thời dùng integration test với RSocket client/server để xác nhận mapping và transport thực tế.

## 11. Những lỗi quản lý phiên bản thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Starter RSocket bị lỗi resolve version | Không có Boot parent hoặc BOM trong dependency management. | Kế thừa parent hoặc import BOM đúng cách. |
| Maven build được nhưng plugin đóng gói không chạy đúng | Chỉ import BOM mà chưa quản lý phiên bản plugin. | Khai báo plugin version và cấu hình build riêng. |
| Spring Framework bị lệch so với Boot | Ghi version trực tiếp cho module Spring. | Bỏ override và dùng version từ Boot BOM nếu không có yêu cầu đặc biệt. |
| Reactor runtime có lỗi khó đoán | Reactor Core hoặc Netty bị ép sang version khác. | Kiểm tra dependency tree và đồng bộ release train. |
| RSocket API không tồn tại ở compile time | Khai báo starter nhưng thiếu dependency trực tiếp cho API cấp thấp cần dùng. | Thêm artifact cần thiết và để BOM quản lý version nếu có. |
| Gradle resolve ra version ngoài dự kiến | Có constraint, platform hoặc dependency khác ưu tiên version. | Dùng dependencyInsight để tìm nguồn version. |
| Nâng Boot nhưng integration test thất bại | Thay đổi API hoặc hành vi giữa các release. | Đọc release notes và kiểm thử transport, route, payload, metadata. |
| Nhiều module dùng các Boot BOM khác nhau | Version catalog hoặc parent/module cấu hình không thống nhất. | Chuẩn hóa một Boot release line cho cùng ứng dụng. |

## 12. Quy trình chuẩn khi tạo hoặc nâng cấp dự án RSocket

Một quy trình thực tế có thể áp dụng:

1. Chọn release Spring Boot tương thích với Java runtime và chính sách hỗ trợ của tổ chức.
2. Chọn một cách quản lý dependency: Spring Boot parent, import BOM hoặc Gradle dependency management/native platform.
3. Khai báo starter RSocket và chỉ thêm các starter cần thiết.
4. Không gắn version riêng cho dependency do BOM quản lý.
5. Build và kiểm tra cây dependency thực tế.
6. Chỉ override khi có lý do kỹ thuật rõ ràng và đã kiểm thử tương thích.
7. Chạy integration test cho transport, SETUP, route, interaction model, metadata và xử lý lỗi.
8. Ghi lại phiên bản Spring Boot và mọi override để lần nâng cấp sau có thể kiểm tra.

Quản lý phiên bản tập trung không loại bỏ nhu cầu kiểm thử. Nó tạo một baseline nhất quán để việc kiểm thử và nâng cấp có thể dự đoán được hơn.

## 13. Ghi nhớ

- Spring Boot BOM <code>spring-boot-dependencies</code> quản lý phiên bản cho các dependency được liệt kê trong release tương ứng.
- Maven có thể dùng <code>spring-boot-starter-parent</code> hoặc import BOM nếu dự án đã có parent riêng.
- Gradle có thể dùng dependency management plugin hoặc native platform để áp dụng BOM.
- Starter RSocket nên dùng phiên bản do Spring Boot quản lý; tránh tự đặt version cho từng dependency bắc cầu.
- BOM quản lý dependency, không tự quản lý tất cả Maven/Gradle build plugin.
- Chỉ override Spring Framework, Reactor, RSocket Java hoặc Netty sau khi xác minh yêu cầu tương thích và có kiểm thử.
- Dùng <code>mvn dependency:tree</code>, <code>help:effective-pom</code>, Gradle <code>dependencies</code> và <code>dependencyInsight</code> để xác minh phiên bản thực tế.
- Sau khi nâng Spring Boot, kiểm thử runtime RSocket: transport, SETUP, route, payload, metadata, backpressure, cancellation và lỗi.

## Tài liệu tham khảo

- [Spring Boot — Managing Dependencies](https://docs.spring.io/spring-boot/reference/using/build-systems.html#using.build-systems.dependency-management)
- [Spring Boot Maven Plugin](https://docs.spring.io/spring-boot/maven-plugin/)
- [Spring Boot Gradle Plugin](https://docs.spring.io/spring-boot/gradle-plugin/)
- [RSocket — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/rsocket.html)
