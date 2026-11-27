# Tham số test và production khác nhau thế nào?

Một ứng dụng Spring Modulith có thể cần cấu hình khác nhau khi chạy test và khi chạy production. Trong test, nhóm phát triển thường muốn khởi tạo một module riêng lẻ, thay thế dependency từ module khác bằng mock, bật log chi tiết hoặc chọn một profile dữ liệu giả lập. Trong production, ứng dụng cần khởi tạo đầy đủ các thành phần cần thiết, kết nối hạ tầng thật và áp dụng cấu hình vận hành phù hợp.

Điều quan trọng là phân biệt cấu hình chỉ phục vụ kiểm thử với cấu hình mô tả kiến trúc và hành vi của ứng dụng. Spring Modulith cung cấp các tham số riêng cho module integration test, trong khi những quy tắc như cách phát hiện module và named interface cần nhất quán với mô hình mà ứng dụng sử dụng ở production.

## 1. Phân biệt ba nhóm cấu hình

Khi tổ chức cấu hình, hãy chia thành ba nhóm:

| Nhóm | Mục đích | Nơi thường khai báo |
|---|---|---|
| Cấu hình kiến trúc | Xác định module, package gốc, named interface và phụ thuộc được phép | Production sources, annotation và cấu hình ứng dụng |
| Cấu hình test | Chọn module cần bootstrap, phạm vi dependency, mock và dữ liệu kiểm thử | Test sources, test resources và annotation trên test |
| Cấu hình runtime | Điều khiển hành vi khi ứng dụng khởi động và phục vụ request | Production resources, environment variables hoặc secret/config của môi trường |

Ví dụ, tên module, package API và quy tắc allowedDependencies mô tả kiến trúc của ứng dụng. Chúng không nên thay đổi tùy tiện giữa test và production, vì test cần xác minh chính mô hình sẽ được đóng gói để triển khai.

Ngược lại, database URL, thông tin đăng nhập, cổng dịch vụ, endpoint giả lập và bootstrap mode của một module test có thể khác nhau theo môi trường. Những giá trị này nên được cung cấp qua profile hoặc cấu hình riêng phù hợp với vòng đời sử dụng.

## 2. Cấu hình kiến trúc dùng chung

Spring Modulith phát hiện application module từ package gốc của lớp Spring Boot. Mặc định, các package con trực tiếp của package chứa lớp ứng dụng được xem là module. Ví dụ:

~~~text
com.example
├── Application.java
├── orders
├── billing
└── inventory
~~~

Các annotation như @ApplicationModule và @NamedInterface nằm trong source code và mô tả ranh giới module. Ví dụ, module billing chỉ được phụ thuộc vào named interface api của orders:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::api"
)
package com.example.billing;
~~~

Quy tắc này cần có hiệu lực trong cả test và production. Nếu test dùng một mô hình module khác với mô hình trong artifact production, kết quả test có thể không phản ánh đúng cấu trúc được triển khai.

Một điểm khác cần giữ thống nhất là package gốc của ứng dụng. Trong test kiến trúc, dùng cùng lớp Application làm điểm bắt đầu:

~~~java
var modules = ApplicationModules.of(Application.class);
~~~

Nếu test trỏ đến một lớp nằm trong package khác, mô hình module được phát hiện có thể khác với dự định. Hãy đặt lớp ứng dụng tại package gốc hợp lý và dùng cùng entry point cho các kiểm tra kiến trúc.

## 3. Dependency dành riêng cho test

Spring Modulith cung cấp starter để tích hợp module testing với JUnit và Spring Boot. Khai báo dependency trong phạm vi test.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
}
~~~

Dependency này cung cấp các thành phần hỗ trợ như @ApplicationModuleTest và các tiện ích kiểm thử module. Vì dependency nằm trong test scope, nó không cần được đóng gói vào runtime classpath của production.

Nếu chỉ cần kiểm tra cấu trúc module bằng ApplicationModules.verify(), có thể dùng dependency chứa core API trên test classpath. Starter test phù hợp khi cần bootstrap Spring context theo phạm vi module và sử dụng các tiện ích kiểm thử chuyên biệt của Spring Modulith.

## 4. Các tham số của @ApplicationModuleTest

@ApplicationModuleTest cho phép khởi tạo một application module trong phạm vi hẹp hơn một lần chạy @SpringBootTest toàn ứng dụng. Đặt test class trong package của module hoặc package con và khai báo annotation:

~~~java
package com.example.orders;

import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class OrderIntegrationTests {

    // Các test tích hợp cho module orders.
}
~~~

Theo mặc định, test chạy ở chế độ STANDALONE. Spring Modulith giới hạn component scanning, auto-configuration và entity scanning vào package của module đang kiểm thử. Điều này giúp test tập trung vào trách nhiệm của module.

Các bootstrap mode thường dùng:

| Mode | Phạm vi module được khởi tạo | Khi nên dùng |
|---|---|---|
| STANDALONE | Chỉ module hiện tại | Test module độc lập và mock các dependency bên ngoài |
| DIRECT_DEPENDENCIES | Module hiện tại và các module mà nó phụ thuộc trực tiếp | Khi cần kiểm tra một luồng phối hợp trực tiếp giữa các module |
| ALL_DEPENDENCIES | Module hiện tại và toàn bộ cây dependency của nó | Khi hành vi cần các module ở nhiều tầng phụ thuộc |

Ví dụ chạy module orders cùng các module mà nó phụ thuộc trực tiếp:

~~~java
package com.example.orders;

import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;

@ApplicationModuleTest(mode = BootstrapMode.DIRECT_DEPENDENCIES)
class OrderIntegrationTests {

}
~~~

Ngoài mode, annotation còn có các thuộc tính hữu ích:

| Thuộc tính | Ý nghĩa |
|---|---|
| mode | Chọn STANDALONE, DIRECT_DEPENDENCIES hoặc ALL_DEPENDENCIES |
| verifyAutomatically | Tự động kiểm tra cấu trúc module; mặc định là true |
| extraIncludes | Bổ sung module cần khởi tạo ngoài phạm vi của mode |
| module | Chỉ rõ tên module khi test class nằm ngoài package module |
| classes | Chỉ rõ lớp cấu hình hoặc lớp ứng dụng để bootstrap |
| webEnvironment | Chọn môi trường web của Spring Boot test khi cần |

Chỉ tăng phạm vi bootstrap khi test thực sự cần những module đó. Nếu module đang kiểm thử có nhiều bean phụ thuộc vào module khác, việc liên tục thêm module vào test có thể che khuất coupling. Trong nhiều trường hợp, mock bean ở biên là lựa chọn phù hợp hơn.

## 5. Mock dependency từ module khác trong test

Ở chế độ STANDALONE, Spring Modulith chỉ khởi tạo module hiện tại. Nếu một bean trong module cần inject bean của module khác, context có thể không khởi động vì dependency đó nằm ngoài phạm vi test.

Ví dụ, module orders gọi một bean từ billing. Nếu test của orders không nhằm kiểm tra tích hợp với billing, có thể thay bean đó bằng mock:

~~~java
package com.example.orders;

import com.example.billing.InvoiceService;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@ApplicationModuleTest
class OrderIntegrationTests {

    @MockitoBean
    InvoiceService invoiceService;
}
~~~

Spring Boot đăng ký bean mock trong ApplicationContext của test. Module orders vẫn chạy với cấu trúc bootstrap giới hạn, còn test có thể thiết lập kết quả trả về và xác minh tương tác cần thiết. Với các phiên bản Spring Boot cũ hơn chưa có @MockitoBean, dự án có thể dùng @MockBean theo API của phiên bản đó.

Nếu mục tiêu của test là xác nhận tích hợp thật giữa orders và billing, hãy chọn DIRECT_DEPENDENCIES hoặc ALL_DEPENDENCIES phù hợp. Không dùng mock trong test mà mục tiêu chính là kiểm chứng hành vi của chính tích hợp đó.

Lựa chọn giữa mock và mở rộng bootstrap scope phụ thuộc vào câu hỏi test cần trả lời:

- Test một module trong cô lập: dùng STANDALONE và mock dependency ngoài module.
- Test một quan hệ tích hợp trực tiếp: dùng DIRECT_DEPENDENCIES.
- Test một luồng đi qua nhiều tầng module: cân nhắc ALL_DEPENDENCIES.
- Nếu test cần khởi tạo gần như toàn ứng dụng, xem lại liệu đó có phải module integration test hay nên là một integration test cấp ứng dụng.

## 6. Đặt cấu hình test trong test resources

Các giá trị chỉ phục vụ kiểm thử nên nằm trong test resources hoặc được cung cấp trực tiếp cho test. Ví dụ, file src/test/resources/application-test.yml có thể chứa cấu hình database test, endpoint giả lập và mức log:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:orders-test
    username: sa
    password:
  jpa:
    hibernate:
      ddl-auto: create-drop

logging:
  level:
    org.springframework.modulith: DEBUG
~~~

Kích hoạt profile test cho test class khi cần:

~~~java
package com.example.orders;

import org.springframework.test.context.ActiveProfiles;
import org.springframework.modulith.test.ApplicationModuleTest;

@ActiveProfiles("test")
@ApplicationModuleTest
class OrderIntegrationTests {

}
~~~

Các cấu hình này chỉ nên chứa giá trị an toàn cho môi trường test. Không sao chép mật khẩu production, token thật hoặc thông tin truy cập hạ tầng thật vào test resources.

Nếu cần ghi đè một property cho một test cụ thể, có thể dùng cơ chế cấu hình test của Spring Boot và Spring Test, chẳng hạn @TestPropertySource hoặc @DynamicPropertySource. Với giá trị được tạo động như cổng server giả lập, @DynamicPropertySource giúp đăng ký giá trị trong thời gian test.

## 7. Cấu hình production nằm ở đâu?

Production configuration thường được đặt trong src/main/resources/application.yml và các file profile như application-prod.yml. Giá trị nhạy cảm hoặc phụ thuộc môi trường nên được truyền qua biến môi trường, secret manager hoặc hệ thống cấu hình của nền tảng triển khai.

Ví dụ:

~~~yaml
spring:
  datasource:
    url: ${DATABASE_URL}
    username: ${DATABASE_USERNAME}
    password: ${DATABASE_PASSWORD}

  jpa:
    open-in-view: false

logging:
  level:
    org.springframework.modulith: INFO
~~~

Các biến DATABASE_URL, DATABASE_USERNAME và DATABASE_PASSWORD được cung cấp từ môi trường chạy. Không đặt credential thật trong file được commit vào repository.

Production profile cần chứa các cấu hình phục vụ ứng dụng thật: datasource, message broker, endpoint tích hợp, pool, logging, observability và các property Spring Modulith cần cho runtime. Cấu hình test như database in-memory, mock server hoặc profile test không nên được đưa vào production resources.

## 8. Module detection trong test và production

Spring Modulith mặc định phát hiện module từ các direct sub-package của package chứa lớp Spring Boot. Nếu cần thay đổi cách phát hiện, có thể cấu hình property:

~~~properties
spring.modulith.detection-strategy=explicitly-annotated
~~~

Giá trị explicitly-annotated yêu cầu module được đánh dấu rõ bằng @ApplicationModule hoặc annotation @Module của jMolecules. Có thể đăng ký một implementation ApplicationModuleDetectionStrategy tùy chỉnh bằng tên lớp đầy đủ trong property này.

Ví dụ đăng ký một strategy tùy chỉnh:

~~~properties
spring.modulith.detection-strategy=com.example.CustomApplicationModuleDetectionStrategy
~~~

Điểm khác biệt quan trọng nằm ở nơi đặt custom strategy:

- Nếu chỉ dùng module detection để xác minh kiến trúc hoặc tạo tài liệu trong test, implementation và registration có thể được đặt trong test sources.
- Nếu ứng dụng dùng các thành phần Spring Modulith ở runtime, ví dụ module initialization, actuator hoặc observability, custom detection strategy cần có trong production sources để các thành phần runtime nhìn thấy cùng mô hình module.
- Nếu test và production cần cùng một chiến lược, đặt implementation và registration trong main sources để tránh hai mô hình khác nhau.

Không nên vô tình để test phát hiện module theo một convention nhưng production lại dùng convention mặc định. Nếu hai mô hình không đồng nhất, test có thể xác minh sai tập module hoặc tài liệu kiến trúc không phản ánh cấu trúc thực tế khi chạy.

## 9. Phiên bản và dependency phải đồng bộ

Các artifact Spring Modulith có quan hệ phiên bản với nhau. Hãy dùng Spring Modulith BOM để quản lý version đồng bộ thay vì đặt version riêng lẻ cho từng artifact.

Maven:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-bom</artifactId>
            <version>${spring-modulith.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Khi BOM đã quản lý phiên bản, dependency có thể bỏ trường version:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Gradle có thể import BOM bằng platform:

~~~groovy
dependencies {
    implementation platform("org.springframework.modulith:spring-modulith-bom:${springModulithVersion}")

    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
    runtimeOnly 'org.springframework.modulith:spring-modulith-runtime'
}
~~~

Chọn phiên bản Spring Modulith tương thích với dòng Spring Boot mà ứng dụng đang sử dụng. Khi nâng cấp, hãy đọc release notes và migration notes của phiên bản đích, đặc biệt nếu thay đổi annotation test, property hoặc artifact runtime.

Một số khác biệt theo phiên bản cần lưu ý:

- @ApplicationModuleTest và các bootstrap mode có thể được bổ sung thuộc tính qua các phiên bản. Kiểm tra API của đúng phiên bản dependency thay vì sao chép thuộc tính từ tài liệu của phiên bản khác.
- Change-aware test execution được giới thiệu từ Spring Modulith 1.3 thông qua artifact spring-modulith-junit. Tính năng này có các property riêng cho việc phát hiện thay đổi và chọn test.
- Runtime support và runtime verification có yêu cầu artifact, property và phiên bản riêng. Không giả định một property có mặt ở mọi dòng Spring Modulith.
- Không trộn các artifact Spring Modulith từ nhiều release train trong cùng một ứng dụng.

## 10. Các tham số test không nên ảnh hưởng production

Một số property chỉ có ý nghĩa trong quá trình kiểm thử. Ví dụ, change-aware test execution có thể dùng các property:

~~~properties
spring.modulith.test.reference-commit=${commit-id}
spring.modulith.test.on-no-changes=skip-all
~~~

Property reference-commit giúp JUnit extension xác định thay đổi kể từ lần build thành công trước đó trong CI. Property on-no-changes điều khiển cách xử lý khi không phát hiện thay đổi liên quan. Đây là tham số cho test execution, không phải cấu hình ứng dụng phục vụ request.

Tương tự, bootstrap mode STANDALONE hoặc DIRECT_DEPENDENCIES chỉ điều khiển phạm vi ApplicationContext của @ApplicationModuleTest. Chúng không phải chế độ chạy module trong production.

Để tránh rò rỉ cấu hình:

- Đặt property chỉ phục vụ test trong src/test/resources hoặc cấu hình CI.
- Đặt test dependency trong test scope.
- Không đưa test profile vào biến môi trường production.
- Không đặt test-only mock hoặc test bean trong main sources.
- Giữ các annotation và quy tắc kiến trúc trong production sources để test và runtime cùng đọc được.

## 11. Kiểm tra cấu hình test và production

Có thể dùng bảng sau để rà soát một dự án:

| Thành phần | Test | Production |
|---|---|---|
| Spring Modulith core | Có trên test classpath | Có nếu ứng dụng/runtime feature cần |
| spring-modulith-starter-test | Test scope | Không cần |
| spring-modulith-runtime | Có thể thêm nếu test cần kiểm tra runtime behavior | Runtime scope khi dùng runtime support |
| @ApplicationModule và @NamedInterface | Đọc từ production sources | Có trong artifact production |
| Custom module detection | Test sources nếu chỉ phục vụ test/docs | Production sources nếu runtime feature cần |
| Database | In-memory, container hoặc test instance | Database của môi trường |
| External service | Mock hoặc test container | Endpoint và credential của môi trường |
| Logging | Có thể bật DEBUG để chẩn đoán | Mức log phù hợp vận hành |
| Bootstrap mode | Điều khiển module integration test | Không áp dụng |

Trước khi phát hành, xác nhận rằng production artifact không phụ thuộc vào test-only library, test profile không được kích hoạt nhầm, và cấu hình module detection nhất quán với kiến trúc đã được test.

## 12. Bài tập thực hành

1. Thêm spring-modulith-starter-test trong test scope.
2. Tạo một @ApplicationModuleTest trong package của module orders.
3. Chạy test ở mode STANDALONE và quan sát phạm vi bean được khởi tạo.
4. Thay một bean dependency của module khác bằng @MockitoBean.
5. Chạy lại với DIRECT_DEPENDENCIES và so sánh các module được bootstrap.
6. Tạo application-test.yml với database test và mức log DEBUG cho org.springframework.modulith.
7. Đặt datasource production trong application-prod.yml hoặc biến môi trường.
8. Nếu dùng custom ApplicationModuleDetectionStrategy, thử đặt registration trong test sources khi chỉ xác minh; sau đó chuyển vào main sources nếu runtime feature cần cùng chiến lược.
9. Import Spring Modulith BOM và xác nhận các artifact dùng chung một release.
10. Kiểm tra CI chỉ truyền property test execution trong job test và production chỉ nhận cấu hình của môi trường triển khai.

Sau bài tập, bạn cần giải thích được vì sao cấu hình kiến trúc phải nhất quán giữa test và production, khi nào nên dùng từng bootstrap mode, cách đặt dependency và property theo đúng scope, và vì sao custom module detection cần nằm trong production sources khi runtime features sử dụng nó.

## Tài liệu tham khảo

- [Integration Testing Application Modules – Spring Modulith](https://docs.spring.io/spring-modulith/reference/testing.html)
- [Fundamentals – Customizing Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith Configuration Properties](https://docs.spring.io/spring-modulith/reference/appendix.html)
- [ApplicationModuleTest API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/test/ApplicationModuleTest.html)
- [Spring Modulith project and supported versions](https://spring.io/projects/spring-modulith)
