# Quản lý phiên bản bằng Spring Cloud BOM

Một dự án Spring thường dùng nhiều thư viện có quan hệ chặt với nhau: Spring Boot, Spring Cloud Commons, Spring Cloud Kubernetes, Spring Cloud LoadBalancer và các thư viện nền tảng khác. Nếu khai báo từng phiên bản độc lập, dự án có thể biên dịch được nhưng lỗi khi khởi động, thiếu class lúc chạy hoặc có hành vi không tương thích giữa các module.

Spring Cloud BOM là một tập dependency management được phát hành để quản lý các phiên bản thư viện Spring Cloud trong cùng một dòng tương thích. BOM không tự thêm thư viện vào ứng dụng. Nó cung cấp quy tắc phiên bản để khi dự án khai báo một module Spring Cloud, Maven hoặc Gradle biết nên dùng phiên bản nào.

Bài học thuộc chương **Thiết lập dự án** của module **SPRING_CLOUD_KUBERNETES**. Mục tiêu là hiểu vai trò của BOM, ghép đúng dòng Spring Boot và Spring Cloud, khai báo dependency cho các tích hợp Kubernetes theo cách nhất quán và kiểm tra kết quả trước khi triển khai.

## 1. BOM là gì?

BOM, viết tắt của Bill of Materials, là một POM hoặc metadata tập hợp các phiên bản dependency đã được kiểm thử cùng nhau. Khi import BOM vào phần quản lý dependency, dự án có thể khai báo module mà không lặp lại phiên bản của từng module được BOM quản lý.

Có thể hình dung:

~~~text
Spring Boot version
        +
Spring Cloud release train
        |
        v
Bộ phiên bản thư viện Spring Cloud tương thích
        |
        +--> module discovery
        +--> module config
        +--> module load balancer
        +--> module chung của Spring Cloud
~~~

BOM giải quyết bài toán đồng bộ phiên bản trong một nhóm thư viện. Nó không giải quyết mọi loại tương thích:

- BOM không làm phiên bản Spring Boot và Spring Cloud bất kỳ trở thành tương thích.
- BOM không bảo đảm image JDK, Kubernetes cluster hoặc client runtime đều phù hợp.
- BOM không thay thế kiểm thử tích hợp với API server, RBAC và ConfigMap/Secret.
- BOM không tự chọn starter nào dự án cần.
- BOM không biến dependency transitively có sẵn thành API ổn định cho mã ứng dụng.

Vì vậy, lựa chọn release train phải bắt đầu từ bảng tương thích của dòng Spring Cloud và Spring Boot đang dùng. Không nên chọn phiên bản bằng cách lấy bản mới nhất của từng dependency rồi ghép lại.

## 2. Quan hệ giữa Spring Boot và Spring Cloud

Spring Boot cung cấp nền tảng khởi động ứng dụng, auto-configuration, actuator và quản lý dependency ở cấp Boot. Spring Cloud bổ sung các abstraction và tích hợp cho hệ thống phân tán, trong đó có discovery, config, load balancing và kết nối với Kubernetes.

Quan hệ đúng cần có dạng:

| Lớp | Quyết định cần chốt | Ví dụ vai trò |
| --- | --- | --- |
| JDK | Phiên bản Java mà runtime và thư viện hỗ trợ | Compile, test và image dùng cùng mục tiêu |
| Spring Boot | Dòng framework nền tảng | Quản lý lifecycle và auto-configuration |
| Spring Cloud release train | Dòng Spring Cloud tương thích với Boot | Quản lý các module Cloud qua BOM |
| Spring Cloud Kubernetes | Module tích hợp Kubernetes trong release train | Discovery, config hoặc tính năng liên quan |
| Kubernetes client/runtime | API server, namespace và cơ chế xác thực | ServiceAccount, RBAC, DNS, EndpointSlice |

Tên release train và bảng tương thích thay đổi theo thời gian. Hãy dùng tài liệu của phiên bản được tổ chức chọn làm nguồn quyết định. Trong file build, nên ghi rõ phiên bản Boot và Spring Cloud được chọn để người khác có thể tái tạo.

Một nguyên tắc thực hành là chỉ có một nguồn chính cho phiên bản Spring Cloud. Nếu BOM quản lý phiên bản một module, không nên lặp lại phiên bản module đó trong dependency trừ khi có lý do đã được đánh giá.

## 3. Import Spring Cloud BOM trong Maven

Với Maven, BOM thường được import trong dependencyManagement bằng type pom và scope import. Ví dụ dùng Spring Boot parent để cung cấp các quy tắc nền tảng, sau đó import Spring Cloud BOM:

~~~xml
<project>
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>BOOT_VERSION</version>
    <relativePath/>
  </parent>

  <groupId>com.example.shop</groupId>
  <artifactId>order-api</artifactId>
  <version>0.0.1-SNAPSHOT</version>

  <properties>
    <java.version>JAVA_VERSION</java.version>
    <spring-cloud.version>SPRING_CLOUD_RELEASE_TRAIN_VERSION</spring-cloud.version>
  </properties>

  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-dependencies</artifactId>
        <version>${spring-cloud.version}</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <!-- Chọn module Spring Cloud Kubernetes phù hợp với nhu cầu thật -->
    <dependency>
      <groupId>SPRING_CLOUD_KUBERNETES_GROUP</groupId>
      <artifactId>SPRING_CLOUD_KUBERNETES_MODULE</artifactId>
    </dependency>
  </dependencies>
</project>
~~~

Các giá trị BOOT_VERSION, JAVA_VERSION và SPRING_CLOUD_RELEASE_TRAIN_VERSION là chỗ thay bằng tổ hợp phiên bản đã được xác nhận. Tên module Kubernetes trong ví dụ được biểu diễn tượng trưng để nhấn mạnh nguyên tắc: chọn artifact theo tài liệu của release train, không sao chép tên module từ một dự án khác mà chưa kiểm tra.

Trong Maven, dependencyManagement không thêm dependency vào classpath. Nó chỉ cung cấp phiên bản và các thuộc tính quản lý cho dependency được khai báo bên dưới hoặc trong module con. Nếu chỉ import BOM mà không khai báo starter/module, ứng dụng không tự có DiscoveryClient, ConfigMap integration hay LoadBalancer.

Nếu dự án không dùng spring-boot-starter-parent, vẫn có thể import Spring Cloud BOM. Khi đó, dự án cần tự quản lý hoặc kế thừa các quy tắc Boot khác theo cách đã chọn:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-dependencies</artifactId>
      <version>BOOT_VERSION</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-dependencies</artifactId>
      <version>${spring-cloud.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
~~~

Thứ tự và cách override giữa nhiều BOM cần được hiểu rõ. Nếu hai BOM quản lý cùng một artifact với phiên bản khác nhau, kết quả có thể phụ thuộc thứ tự import hoặc dependency management gần hơn. Đừng giải quyết xung đột bằng cách đổi thứ tự ngẫu nhiên; hãy xác định BOM nào sở hữu phiên bản và xem dependency tree sau thay đổi.

## 4. Khai báo dependency sau khi import BOM

Sau khi BOM quản lý phiên bản, dependency có thể bỏ trường version:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>SPRING_CLOUD_KUBERNETES_DISCOVERY_MODULE</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>SPRING_CLOUD_KUBERNETES_CONFIG_MODULE</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>SPRING_CLOUD_LOADBALANCER_MODULE</artifactId>
  </dependency>
</dependencies>
~~~

Chỉ thêm module phù hợp với hành vi cần dùng:

- Nếu ứng dụng gọi một Service bằng DNS ổn định, có thể không cần module discovery.
- Nếu cần abstraction truy vấn instance, chọn module discovery tương thích.
- Nếu đọc ConfigMap hoặc Secret trực tiếp qua Kubernetes API, chọn module cấu hình và thiết kế RBAC.
- Nếu chọn instance ở phía client, thêm LoadBalancer cùng HTTP client được tích hợp.
- Nếu cần refresh động, phải thiết kế cả nguồn cấu hình, cơ chế thông báo và bean có thể cập nhật.

Không nên thêm toàn bộ nhóm starter “cho đủ”. Mỗi module có thể kéo theo auto-configuration, kết nối API server, quyền RBAC hoặc phụ thuộc mạng. Dependency tối thiểu làm giảm startup path và giúp chẩn đoán rõ hơn.

Tên dependency thực tế có thể được tách theo chức năng và thay đổi giữa các dòng phiên bản. Hãy kiểm tra tài liệu chính thức của release train đã chọn trước khi điền artifactId. Không nên dùng một artifactId từ bài hướng dẫn thuộc dòng phiên bản khác mà không kiểm tra lại.

## 5. Spring Cloud BOM không quản lý mọi dependency

BOM của Spring Cloud chủ yếu quản lý các module thuộc hệ sinh thái Spring Cloud và những dependency liên quan mà nó công bố. Nó không nhất thiết quản lý mọi thư viện trong dự án như PostgreSQL driver, client cloud, thư viện JSON bên ngoài hoặc image tooling.

Cần phân biệt ba trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| Có version trực tiếp | Dự án tự chịu trách nhiệm chọn và cập nhật |
| Có version từ Spring Boot BOM | Boot quản lý phiên bản đó |
| Có version từ Spring Cloud BOM | Cloud quản lý phiên bản đó |

Không nên thêm một phiên bản thủ công chỉ vì IDE hiển thị dependency transitively. Trước hết hãy kiểm tra dependency management đang cung cấp phiên bản từ đâu. Nếu thư viện không được BOM nào quản lý, đặt version trực tiếp có chủ ý và ghi lý do nếu nó ảnh hưởng đến tương thích.

Có thể dự án dùng một BOM nội bộ của tổ chức ở trên các BOM nền tảng. Trong trường hợp đó, cần xác định quy tắc sở hữu phiên bản và tránh để nhiều module con khai báo override không đồng nhất.

## 6. Import BOM trong Gradle

Gradle có thể dùng plugin dependency management để import Maven BOM:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'BOOT_VERSION'
    id 'io.spring.dependency-management' version 'PLUGIN_VERSION'
}

group = 'com.example.shop'
version = '0.0.1-SNAPSHOT'

ext {
    set('springCloudVersion', 'SPRING_CLOUD_RELEASE_TRAIN_VERSION')
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Chọn module Spring Cloud Kubernetes thực tế cần dùng.
    implementation 'SPRING_CLOUD_KUBERNETES_GROUP:SPRING_CLOUD_KUBERNETES_MODULE'
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}
~~~

Với Gradle Kotlin DSL, cú pháp tương ứng thường dùng chuỗi interpolation của Kotlin:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "BOOT_VERSION"
    id("io.spring.dependency-management") version "PLUGIN_VERSION"
}

extra["springCloudVersion"] = "SPRING_CLOUD_RELEASE_TRAIN_VERSION"

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("SPRING_CLOUD_KUBERNETES_GROUP:SPRING_CLOUD_KUBERNETES_MODULE")

    dependencyManagement {
        imports {
            mavenBom(
                "org.springframework.cloud:spring-cloud-dependencies:" +
                    property("springCloudVersion")
            )
        }
    }
}
~~~

Gradle cũng hỗ trợ mô hình platform. Cú pháp cụ thể phụ thuộc cách dự án dùng plugin và nền tảng dependency management:

~~~groovy
dependencies {
    implementation platform('org.springframework.cloud:spring-cloud-dependencies:SPRING_CLOUD_RELEASE_TRAIN_VERSION')
    implementation 'SPRING_CLOUD_KUBERNETES_GROUP:SPRING_CLOUD_KUBERNETES_MODULE'
}
~~~

Không nên trộn nhiều cách quản lý phiên bản trong cùng dự án mà không hiểu hiệu lực của từng cách. Hãy chọn mô hình theo convention của repository và kiểm tra dependency insight sau khi thay đổi. Nếu dùng Spring Boot Gradle plugin, hãy xem cách plugin đang quản lý Boot dependencies trước khi thêm platform khác.

Khi khai báo module không có version sau khi import BOM, mục tiêu là mọi module được chọn nhận cùng bộ version management. Nếu một dependency vẫn cần version trực tiếp, hãy ghi nhận đó là ngoại lệ và kiểm tra tương thích trong CI.

## 7. Chọn module Spring Cloud Kubernetes cho dự án

BOM chỉ quản lý phiên bản; kiến trúc quyết định module nào cần được thêm. Với module SPRING_CLOUD_KUBERNETES, có thể lập bảng nhu cầu trước khi sửa build:

| Nhu cầu triển khai | Có thể bắt đầu từ | Câu hỏi cần trả lời |
| --- | --- | --- |
| Gọi Service nội bộ bằng tên ổn định | DNS và Service của Kubernetes | Có thật sự cần danh sách instance ở tầng ứng dụng không? |
| Truy vấn service/instance theo abstraction Spring Cloud | Discovery integration | Ứng dụng có cần đọc API và RBAC nào? |
| Đọc ConfigMap/Secret qua API | Config integration | Dữ liệu có thể inject bằng env/volume đơn giản hơn không? |
| Chọn endpoint ở client | Spring Cloud LoadBalancer | Client đã tích hợp LoadBalancer hay chỉ có hostname? |
| Theo dõi thay đổi cấu hình | Watcher và cơ chế refresh phù hợp | Bean nào có thể cập nhật khi giá trị đổi? |
| Báo sức khỏe cho Kubernetes | Spring Boot Actuator và probe | Readiness/liveness có phản ánh đúng khả năng phục vụ không? |

Một ứng dụng chỉ gọi catalog-api qua http://catalog-api có thể không cần discovery dependency. Một ứng dụng cần đọc danh sách instance để thực hiện định tuyến theo metadata có thể cần discovery và LoadBalancer. Hai trường hợp có cùng Kubernetes Service nhưng dependency graph khác nhau.

Việc chọn module cũng ảnh hưởng đến ServiceAccount. Dependency chỉ dùng DNS không tự cần quyền đọc Kubernetes API. Dependency đọc ConfigMap trực tiếp cần danh tính và quyền tương ứng. Dependency watcher riêng có thể cần Role khác với ứng dụng nghiệp vụ.

## 8. BOM và auto-configuration

Spring Boot và Spring Cloud có thể dùng auto-configuration khi dependency và property phù hợp xuất hiện trên classpath. Thêm một starter có thể làm thay đổi startup path dù mã ứng dụng chưa gọi trực tiếp API của module.

Khi thêm dependency, hãy kiểm tra:

- Auto-configuration nào được bật.
- Bean nào được tạo và có điều kiện nào kích hoạt.
- Ứng dụng có cố kết nối Kubernetes API trong môi trường local không.
- Có property nào làm thay đổi discovery hoặc config import không.
- Startup có phụ thuộc ConfigMap, Secret hoặc ServiceAccount không.
- Test unit có cần tắt hoặc mock integration không.

Môi trường local thường không có Kubernetes API in-cluster. Nếu module tự động tìm API server khi ứng dụng khởi động, cấu hình local cần profile hoặc test slice phù hợp. Không nên tắt toàn bộ auto-configuration chỉ vì local thiếu cluster mà không hiểu production sẽ cần bean nào.

Một chiến lược rõ ràng là tách profile theo môi trường, nhưng tránh để profile làm thay đổi logic nghiệp vụ không cần thiết. Profile nên điều chỉnh nguồn cấu hình, endpoint và integration; các validation quan trọng vẫn nên chạy ở mọi môi trường.

## 9. Kiểm tra dependency tree trong Maven

Sau khi import BOM, hãy kiểm tra dependency tree để xem phiên bản thực tế và nguồn transitively:

~~~text
mvn dependency:tree -Dincludes=org.springframework.cloud
mvn help:effective-pom
~~~

Các lệnh trên chỉ là ví dụ kiểm tra dành cho người phát triển. Điều cần quan sát:

- Có module Spring Cloud bị kéo ở nhiều phiên bản không.
- Module Kubernetes và module Commons có cùng release train không.
- Có dependency trực tiếp override phiên bản BOM không.
- Có thư viện cũ bị kéo transitively bởi một starter khác không.
- Scope của dependency có đúng runtime/test không.

Trong dependency tree, một dòng bị “omitted for conflict” không tự có nghĩa dự án sai; nó cho biết Gradle/Maven đã chọn một phiên bản trong xung đột. Hãy xác định phiên bản được chọn có nằm trong tổ hợp tương thích không.

Effective POM giúp nhìn kết quả sau khi parent và BOM đã được hợp nhất. Nó hữu ích khi một module con không rõ vì sao nhận một version. Không nên chỉ đọc POM gốc rồi kết luận; dependency management có thể đến từ parent hoặc BOM import.

## 10. Kiểm tra dependency insight trong Gradle

Với Gradle, dependency tree và dependency insight giúp truy tìm lý do một version được chọn:

~~~text
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud --configuration runtimeClasspath
~~~

Hãy kiểm tra configuration phù hợp với lỗi. Một dependency có thể đúng trong compileClasspath nhưng khác trong runtimeClasspath hoặc testRuntimeClasspath. Khi lỗi chỉ xuất hiện lúc khởi động, runtimeClasspath thường quan trọng hơn danh sách compile.

Cần xem:

- Component được chọn và các candidate bị loại.
- Constraint đến từ BOM, platform hay dependency trực tiếp.
- Có forced version hoặc resolutionStrategy nào không.
- Test có đang dùng một version khác production không.
- Dependency có bị exclude làm mất auto-configuration không.

Đừng dùng resolutionStrategy.force như phản xạ đầu tiên. Force có thể che dấu xung đột và tạo một tổ hợp chưa được release train kiểm thử. Nếu phải force vì vấn đề bảo mật hoặc yêu cầu tổ chức, ghi rõ phạm vi, kiểm thử và kế hoạch loại bỏ override.

## 11. Khi cần override phiên bản

Override là quyết định có rủi ro. Một số lý do chính đáng gồm bản vá bảo mật, lỗi đã biết, yêu cầu runtime của tổ chức hoặc một dependency ngoài BOM cần mức mới hơn. Nhưng đổi phiên bản một module Spring Cloud riêng lẻ có thể phá vỡ binary compatibility với module cùng train.

Trước khi override, hãy trả lời:

1. Phiên bản mới có nằm trong release train tương thích không?
2. Nó có thay đổi API, property hoặc auto-configuration không?
3. Các module Spring Cloud liên quan có cần đổi cùng không?
4. Có CVE hoặc issue chính thức giải thích lý do không?
5. Dependency tree sau override có còn một phiên bản duy nhất không?
6. Đã có test startup và test integration cho đường Kubernetes chưa?
7. Có ghi chú để bỏ override khi BOM mới phát hành không?

Maven override thường được đặt trong dependencyManagement sau khi import BOM hoặc bằng property do parent quản lý, tùy cấu trúc dự án. Gradle có thể dùng constraint hoặc dependency management. Cú pháp không quan trọng bằng việc phạm vi override rõ và được kiểm chứng.

Không nên override bằng cách thêm version trực tiếp vào mọi dependency. Cách đó làm mất lợi ích của BOM và khiến các module con dễ trôi phiên bản. Nếu cần một ngoại lệ, tập trung nó ở một nơi có thể audit.

## 12. BOM, bảo mật và cập nhật định kỳ

BOM không phải công cụ quét bảo mật. Một release train tương thích có thể vẫn chứa dependency cần cập nhật theo advisory mới, hoặc một thư viện ngoài train có CVE riêng. Quy trình cập nhật cần kết hợp dependency management với scan và kiểm thử.

Khi nâng BOM:

- Đọc release notes của Spring Boot và Spring Cloud.
- Kiểm tra bảng tương thích của release train.
- Xem các thay đổi deprecation và property.
- Cập nhật dependency tree.
- Chạy test unit, test context và test integration phù hợp.
- Kiểm tra startup trong môi trường có Kubernetes.
- Kiểm tra discovery, config, readiness và RBAC nếu module liên quan.
- Ghi nhận thay đổi và đường lui nếu rollout thất bại.

Nếu chỉ cập nhật một version transitive để đóng CVE, hãy kiểm tra liệu bản cập nhật đó có được release train mới quản lý hay không. Giữ nhiều override lâu dài làm tăng nợ kỹ thuật và khó biết tổ hợp nào đã được kiểm thử.

Không nên tắt kiểm tra bảo mật vì dependency tree có nhiều cảnh báo không liên quan. Hãy phân loại cảnh báo, nâng cấp theo dependency sở hữu và lưu bằng chứng cho các trường hợp chấp nhận rủi ro.

## 13. Đặt version ở đâu để dễ bảo trì?

Một dự án nên có một nơi rõ ràng cho version của Boot, Cloud release train và plugin build. Ví dụ Maven:

~~~xml
<properties>
  <java.version>JAVA_VERSION</java.version>
  <spring-boot.version>BOOT_VERSION</spring-boot.version>
  <spring-cloud.version>SPRING_CLOUD_RELEASE_TRAIN_VERSION</spring-cloud.version>
</properties>
~~~

Nếu dùng Spring Boot parent, version Boot thường nằm ở parent. Đừng khai báo lại cùng property nếu không cần. Nếu dùng parent nội bộ, hãy kiểm tra property nào đã được quản lý trước khi thêm property trùng tên.

Ví dụ Gradle có thể đặt version trong một catalog hoặc biến build tập trung:

~~~toml
[versions]
spring-boot = "BOOT_VERSION"
spring-cloud = "SPRING_CLOUD_RELEASE_TRAIN_VERSION"
~~~

Cấu trúc thật phụ thuộc convention của dự án. Điều cần đạt là một thay đổi release train có thể được review ở một vị trí, thay vì phải tìm và sửa nhiều module con.

Trong multi-module build, module con nên dùng dependency không có version cho phần đã được BOM quản lý. Module con chỉ khai báo phiên bản khi dependency không thuộc management hoặc có ngoại lệ đã được quyết định ở cấp dự án.

## 14. Xử lý lỗi khởi động sau khi đổi BOM

Sau khi đổi BOM, ứng dụng có thể gặp lỗi như NoSuchMethodError, ClassNotFoundException, BeanDefinitionException hoặc auto-configuration không thỏa điều kiện. Đừng sửa bằng cách thêm ngẫu nhiên một jar.

Trình tự kiểm tra:

| Bước | Câu hỏi |
| --- | --- |
| 1 | Boot và Cloud release train có đúng quan hệ tương thích không? |
| 2 | Dependency tree có nhiều phiên bản Spring Framework hoặc Spring Cloud không? |
| 3 | Module bị lỗi có bị override trực tiếp không? |
| 4 | Có dependency cũ kéo transitively một API không tương thích không? |
| 5 | Property hoặc auto-configuration có đổi tên theo release train không? |
| 6 | Lỗi xảy ra khi compile, test, startup hay gọi Kubernetes API? |
| 7 | Có thể tái hiện bằng một context test tối thiểu không? |

NoSuchMethodError thường gợi ý binary mismatch giữa lúc compile và runtime. ClassNotFoundException có thể do dependency bị thiếu, scope sai hoặc exclude. BeanDefinitionException có thể do nhiều auto-configuration cùng tạo bean hoặc điều kiện property thay đổi.

Nếu lỗi chỉ xảy ra khi gọi Kubernetes API, đừng kết luận BOM là nguyên nhân duy nhất. Kiểm tra endpoint API, token, namespace, RBAC, NetworkPolicy và phiên bản API server. Dependency alignment và môi trường cluster là hai lớp cần phân tích riêng.

## 15. Ví dụ quy trình nâng release train

Một quy trình review có thể diễn ra như sau:

1. Chọn release train tương thích với dòng Spring Boot mục tiêu.
2. Đổi một property hoặc parent version ở nơi tập trung.
3. Giữ dependency Spring Cloud Kubernetes không có version riêng nếu BOM quản lý.
4. Xem dependency tree và nhận diện các override.
5. Chạy context test để phát hiện lỗi auto-configuration.
6. Chạy test integration cho discovery/config nếu dự án dùng chúng.
7. Tạo image và kiểm tra startup với ServiceAccount, ConfigMap/Secret mẫu.
8. Kiểm tra readiness, log không lộ Secret và hành vi khi API server tạm lỗi.
9. Triển khai canary hoặc rollout có kiểm soát.
10. Ghi lại phiên bản, kết quả kiểm tra và cách rollback.

BOM giúp bước 3 đơn giản hơn, nhưng không loại bỏ các bước còn lại. Nó là điểm kiểm soát dependency, không phải bằng chứng rằng ứng dụng đã tương thích với cluster.

## 16. Checklist thiết lập dependency

Trước khi commit thay đổi build, hãy kiểm tra:

- JDK, Spring Boot và Spring Cloud release train đã được chọn theo quan hệ tương thích.
- BOM được import ở đúng phạm vi dependency management.
- Dependency Spring Cloud Kubernetes không lặp version nếu BOM đã quản lý.
- Chỉ thêm module phục vụ nhu cầu thực tế.
- Đã phân biệt dependency compile, runtime và test.
- Maven effective POM hoặc Gradle dependency insight cho kết quả dễ giải thích.
- Không có override tùy ý hoặc force version không có lý do.
- Dependency ngoài BOM có version và owner rõ ràng.
- Auto-configuration mới được xem xét ở local, test và production.
- Nếu module đọc Kubernetes API, RBAC và ServiceAccount được thiết kế riêng.
- Nếu module chỉ gọi DNS/Service, không cấp quyền API không cần thiết.
- Có test startup và test integration phù hợp.
- Đã xem release notes, deprecation và advisory bảo mật.
- Có kế hoạch rollback khi rollout sau nâng version thất bại.

## 17. Tự kiểm tra

1. BOM quản lý phiên bản như thế nào và vì sao nó không tự thêm dependency?
2. Vì sao không nên ghép phiên bản mới nhất của Spring Boot và Spring Cloud một cách độc lập?
3. Trong Maven, import BOM khác gì với khai báo một dependency thông thường?
4. Trong Gradle, dependency management và platform có vai trò gì?
5. Nếu ứng dụng chỉ gọi Service bằng DNS, có nhất thiết cần Spring Cloud Kubernetes discovery không?
6. Vì sao thêm một starter có thể làm thay đổi startup path dù mã ứng dụng chưa gọi API?
7. Khi dependency tree có xung đột, tại sao force version không nên là lựa chọn đầu tiên?
8. Những kiểm tra nào cần thực hiện sau khi override một module do lý do bảo mật?
9. Nếu lỗi là NoSuchMethodError sau khi đổi BOM, cần phân biệt compile classpath và runtime classpath ra sao?
10. Dependency alignment có chứng minh ứng dụng đã đúng RBAC và readiness trong Kubernetes không?

Spring Cloud BOM giúp đặt các module Spring Cloud trên cùng một mặt bằng phiên bản, nhưng giá trị của nó chỉ phát huy khi đi cùng lựa chọn release train đúng, dependency tối thiểu và kiểm tra dependency tree. Với Spring Cloud Kubernetes, hãy để BOM quản lý phiên bản, còn kiến trúc quyết định có cần discovery, config, LoadBalancer hay watcher. Sau đó kiểm tra cả classpath, startup, RBAC, cấu hình và hành vi Pod trước khi coi việc nâng phiên bản là hoàn tất.

