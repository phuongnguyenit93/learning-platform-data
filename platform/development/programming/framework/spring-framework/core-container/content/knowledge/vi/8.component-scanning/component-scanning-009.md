# Xung đột do quét trùng và giới hạn quét theo mô-đun trong Spring Core Container

## 1. Bài toán: mở rộng component scan trong dự án nhiều mô-đun

Giả sử hệ thống có ba Gradle module: `catalog` quản lý danh mục sản phẩm, `audit` ghi nhận sự kiện, `app` lắp ghép hai khả năng đó. Cả `catalog` lẫn `audit` đều định nghĩa một class tên ngắn `ReportService` và đánh dấu `@Service`:

```text
catalog -> demo.catalog.service.ReportService
audit   -> demo.audit.service.ReportService
app     -> cấu hình ApplicationContext
```

Mỗi class Java có tên đầy đủ khác nhau, nên **không có xung đột ở trình biên dịch Java**. Nhưng nếu component scanner phát hiện cả hai class trong cùng một Spring `BeanDefinitionRegistry`, chiến lược tên mặc định có thể đặt cho cả hai bean name `reportService`. Container khi đó không biết đăng ký hai bean definitions không tương thích dưới cùng một tên và sẽ báo lỗi.

Một tình huống khác: ứng dụng quét `demo.catalog` và đồng thời quét `demo.catalog.service`. Một component bên trong `demo.catalog.service` xuất hiện trong cả hai vùng. Có phải cứ **quét chồng lấn** là tạo hai instance hoặc lỗi? **Không nhất thiết.** Spring scanner kiểm tra bean definition đã đăng ký; nếu candidate thứ hai là cùng source hoặc tương thích, scanner thường **bỏ qua đăng ký lặp**, không tạo bean thứ hai.

Vì vậy cần phân biệt:

- **Quét chồng lấn:** cùng một class được tìm qua nhiều lượt hoặc nhiều package root giao nhau.
- **Xung đột tên:** các bean definitions không tương thích dùng cùng bean name.
- **Trùng kiểu:** nhiều bean có kiểu tương thích với một dependency đơn, gây ambiguity khi autowire.
- **Đăng ký qua nhiều cơ chế:** cùng/khác class xuất hiện qua `@ComponentScan`, `@Bean`, `@Import`, auto-configuration hoặc code đăng ký bean; kết quả phụ thuộc nguồn và chính sách override.

Mục tiêu bài học là nắm quy tắc, chọn ranh giới scan đúng theo Java package và Gradle module, phân tích lỗi thực tế, đồng thời xây ví dụ Java 17+ với Spring Framework để quan sát cả trường hợp **không lỗi**, **có xung đột**, và **cách sửa**.

## 2. Mô hình quét: classpath, package và bean registry

`@ComponentScan` từ `org.springframework.context.annotation` yêu cầu Spring khám phá component candidates trong một hoặc nhiều base package. Mặc định, scanner nhận `@Component` và các stereotype như `@Service`, `@Repository`, `@Controller`, `@Configuration` hoặc custom stereotype có meta-annotation `@Component`.

Khi `@ComponentScan(basePackages = "demo.catalog")` được xử lý:

```text
Runtime classpath có các .class của module phụ thuộc
                     |
                     v
Spring scan demo.catalog và package con của nó
                     |
                     v
Áp dụng stereotype + exclude/include filters/condition
                     |
                     v
BeanNameGenerator tạo tên cho mỗi bean definition
                     |
                     v
BeanDefinitionRegistry kiểm tra tên / tương thích
                     |
                     v
  Đăng ký mới, bỏ qua bản trùng tương thích,
  hoặc báo lỗi nếu đụng definition không tương thích
                     |
                     v
ApplicationContext khởi tạo bean theo scope/lifecycle
```

**Ba không gian tên khác nhau:**

1. **Java package**: ví dụ `demo.catalog.service`. Nó xác định namespace Java và phạm vi tìm class của component scanner.
2. **Build module**: ví dụ Gradle project `:catalog`. Nó quyết định class nào được compile và có trên runtime classpath của module khác.
3. **Spring bean name**: ví dụ `reportService`. Đây là key để đăng ký/lookup bean trong một BeanFactory/registry cụ thể.

Spring **không lấy tên Gradle module làm phạm vi scan tự động**. Hai Gradle modules có thể dùng cùng Java package prefix; một module Gradle có thể chứa nhiều package; một package có thể trải trên nhiều JAR. Component scanner làm việc với package + classpath, chứ không nhận lệnh “chỉ quét Gradle module A” qua `@ComponentScan`.

### 2.1. Một class trên classpath chưa chắc là một bean

Để một class được đăng ký nhờ scanning, cần đồng thời:

- Artifact chứa `.class` có mặt trong runtime classpath (hoặc module path phù hợp).
- Package của class nằm trong một base package được quét.
- Class là candidate hợp lệ (concrete, independent, đúng stereotype/filter).
- Không bị `@Profile`, `@Conditional` hoặc exclude filter loại bỏ.
- Bean name/metadata có thể đăng ký mà không gây xung đột không tương thích.

Việc Gradle có `implementation project(':audit')` chỉ khiến mã audit khả dụng cho `app`; nó **không tự mở component scan** sang `demo.audit`.

### 2.2. Registry của từng `ApplicationContext`

Bean name có tính duy nhất trong phạm vi **một registry**, không phải toàn JVM. Hai `ApplicationContext` độc lập đều có thể có bean tên `reportService` mà không xung đột. Xung đột xuất hiện khi hai definitions không tương thích cùng đi vào **một** registry dưới cùng tên.

Với quan hệ parent-child context, khả năng lookup bean từ parent/child và hiện tượng shadowing phụ thuộc tên/vị trí bean. Đừng kết luận rằng hai bean cùng tên ở **hai context khác nhau** luôn giống một xung đột đăng ký trong một registry.

## 3. Khi quét trùng không gây lỗi: candidate tương thích

Spring `ClassPathBeanDefinitionScanner` có bước `checkCandidate(beanName, definition)`. Ý nghĩa của bước này:

- Chưa có bean definition trùng tên: candidate có thể đăng ký.
- Có definition tương thích: scanner **bỏ qua candidate lặp**.
- Có definition không tương thích: scanner có thể ném lỗi, thường liên quan `ConflictingBeanDefinitionException`.

Với hai root giao nhau:

```java
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackages = {
        "demo.catalog",
        "demo.catalog.service"
})
class OverlappingConfig {
}
```

Nếu `demo.catalog.service.ReportService` là một bean class cụ thể có stereotype và không có đăng ký xung đột, root `demo.catalog` đã bao phủ class này; scan tiếp root `demo.catalog.service` sẽ gặp cùng component. Mặc định Spring nhận ra duplicate tương thích nên không tạo hai bean độc lập chỉ vì hai root giao nhau.

Đây là **đoạn minh họa cấu hình**, chạy đầy đủ trong ví dụ mục 7.

**Đừng suy luận quá mức:** sự tương thích không có nghĩa mọi loại duplicate đều an toàn. Nếu hai source đăng ký bean definitions khác nhau dưới cùng tên, chính sách check/override còn phụ thuộc kiểu definition, cấu hình registry và thứ tự đăng ký. Với hai class khác nhau cùng được scanner phát hiện, xung đột tên là vấn đề khác hẳn so với quét hai lần *cùng một class*.

### 3.1. Quét một class hai lần không đồng nghĩa hai singleton

Một component default singleton được đăng ký vào registry **một lần** dưới cùng bean name trong tình huống scan trùng tương thích. Một lần lookup có thể trả cùng singleton, không xuất hiện “singleton thứ hai” do lặp scan.

Nếu bạn thật sự cần hai bean instances của cùng class với cấu hình khác nhau, hãy khai báo hai bean definitions có chủ đích (ví dụ hai `@Bean` methods với tên và tham số khác nhau) và quản lý scope/lifecycle; đừng dùng scan chồng lấn để cố tạo hai instances.

### 3.2. Không dựa vào thứ tự scan để giải quyết conflict

Thứ tự filesystem/classpath scanning không nên là hợp đồng nghiệp vụ. Trường hợp các bean definitions thực sự mâu thuẫn phải được sửa bằng naming, scan boundaries hoặc explicit registration. Không thiết kế logic “class nào được quét trước thì class đó thắng” vì thay đổi JAR, build hoặc package layout có thể thay đổi hành vi.

## 4. Khi trùng tên của hai class khác nhau gây conflict

Mặc định, `AnnotationBeanNameGenerator` thường lấy **tên class ngắn** theo quy tắc JavaBeans, ví dụ `ReportService` → `reportService`.

Giả sử:

```java
// catalog/src/main/java/demo/catalog/service/ReportService.java
package demo.catalog.service;

import org.springframework.stereotype.Service;

@Service
public class ReportService {
}
```

và:

```java
// audit/src/main/java/demo/audit/service/ReportService.java
package demo.audit.service;

import org.springframework.stereotype.Service;

@Service
public class ReportService {
}
```

Hai file hợp lệ vì Java package khác nhau. Nhưng quét cả hai:

```java
@Configuration
@ComponentScan(basePackages = {"demo.catalog", "demo.audit"})
class ConflictConfig {
}
```

có thể khiến cả hai cùng được đăng ký dưới bean name `reportService`. Vì bean classes khác nhau, scanner gặp hai definitions không tương thích và báo `ConflictingBeanDefinitionException` (đôi khi được bọc trong exception cấp cao hơn).

Câu báo lỗi thường chứa tên `reportService`, tên đầy đủ hai class và thông tin “conflicts with existing ... bean definition”. Khi chẩn đoán, đọc **hai class names** và **bean name** trong exception thay vì chỉ tìm một từ “duplicate”.

### 4.1. Cách giải quyết theo mức độ cần thiết

**Cách A — Quét đúng module cần dùng.** Nếu `app` chỉ sử dụng catalog, giới hạn scanner vào `demo.catalog`. Đừng kéo audit component vào registry chỉ vì audit library cũng có mặt trong classpath.

**Cách B — Đặt tên riêng trên component.** Nếu cần cả hai services:

```java
@Service("catalogReportService")
public class ReportService {
}
```

ở catalog và:

```java
@Service("auditReportService")
public class ReportService {
}
```

ở audit. Hai đoạn là **biến thể minh họa**; chúng thuộc hai file/package khác nhau như trên. Tên explicit giúp phân biệt và ổn định khi đổi class name, nhưng cần sửa các tham chiếu string nếu đã phụ thuộc tên cũ.

**Cách C — Fully-qualified bean names.** Spring cung cấp `FullyQualifiedAnnotationBeanNameGenerator` để sinh fallback bean names theo class name có package:

```java
@Configuration
@ComponentScan(
    basePackages = {"demo.catalog", "demo.audit"},
    nameGenerator = FullyQualifiedAnnotationBeanNameGenerator.class
)
class QualifiedConfig {
}
```

Khi đó hai bean có thể tên `demo.catalog.service.ReportService` và `demo.audit.service.ReportService`. Generator này vẫn giữ explicit stereotype names; nếu hai class đều khai báo `@Service("reportService")`, **nó không tự xóa được xung đột explicit name**.

**Cách D — Đăng ký tường minh.** Nếu không muốn scan toàn bộ audit, có thể import một `@Configuration` module audit cung cấp bean qua `@Bean(name = "...")`, hoặc dùng `@Import` để đăng ký class/cấu hình cần thiết. Cách này tạo hợp đồng ranh giới module rõ ràng hơn, nhất là thư viện có nhiều component nội bộ.

### 4.2. Đổi generator không giải quyết ambiguity theo type

Hai bean khác tên nhưng cùng implement interface `ReportPort` có thể cùng được đăng ký thành công. Nếu một constructor inject **một** `ReportPort` mà không có chính sách lựa chọn, Spring vẫn có thể ném `NoUniqueBeanDefinitionException`.

| Vấn đề | Dấu hiệu | Cách sửa |
| --- | --- | --- |
| Trùng bean name | Hai definitions không tương thích cùng key; conflict khi register | Tên explicit khác nhau, FQ generator, giới hạn scan |
| Trùng candidates theo type | Hai bean names khác nhau nhưng caller cần một bean type chung | `@Qualifier`, `@Primary`, hoặc thiết kế injection tập hợp |
| Thiếu bean | Không được scan/import, thiếu runtime dependency hoặc bị condition loại | Sửa package/classpath/cấu hình |
| Cùng class quét lặp tương thích | Scanner gặp cùng definition qua vùng giao nhau | Thường bỏ qua đăng ký lặp; vẫn nên đơn giản hóa scan khi có thể |

## 5. Ranh giới quét khi dự án chia mô-đun

Một dự án nhiều mô-đun có thể tổ chức theo trách nhiệm:

```text
workspace/
├── app/           -> demo.app
├── catalog/       -> demo.catalog
├── audit/         -> demo.audit
└── contracts/     -> demo.contracts (interface/DTO)
```

Về build, `app` có thể phụ thuộc `catalog` và `audit`; `catalog`, `audit` có thể cùng phụ thuộc `contracts`. Nhưng **component scanning không suy ra ranh giới module từ dependency graph**.

Khi cấu hình:

```java
@ComponentScan(basePackages = "demo")
```

Spring sẽ xét tất cả component candidates trong `demo` và các subpackage **có trên runtime classpath**. Điều này có thể kéo vào container các adapter, service nội bộ, configuration class demo/test support hoặc optional integration không mong muốn, và làm phát sinh conflict.

Thay vì quét quá rộng, nên xác định rõ “application composition root”:

- Module nào thực sự cung cấp beans cho ứng dụng hiện tại?
- Các package **API công khai** hoặc **configuration entry point** của module là gì?
- Module nào cần tách biệt internal components, chỉ public bean qua `@Bean`/`@Import`?
- Có test hoặc profile nào dự định tạo context chỉ với một phần các module?
- Khi một dependency mới xuất hiện trên classpath, có nên tự động khiến toàn bộ component bên trong nó tham gia runtime không?

Một module library có thể cung cấp **configuration class công khai** để application `@Import` thay vì yêu cầu quét hết package nội bộ. Cách thiết kế này giúp việc tích hợp có mục tiêu hơn và hạn chế xung đột tên ngoài dự kiến.

### 5.1. `basePackageClasses` giúp giới hạn theo package root

`@ComponentScan(basePackageClasses = CatalogMarker.class)` lấy package chứa `CatalogMarker` làm root quét. Nếu marker nằm tại `demo.catalog`, Spring quét `demo.catalog` và các subpackage.

```java
@Configuration
@ComponentScan(basePackageClasses = {
        CatalogMarker.class,
        AuditMarker.class
})
class ModuleComposition {
}
```

Đây là đoạn minh họa cần các marker trong package root tương ứng. Marker class không cần mang stereotype. Cách này **type-safe hơn chuỗi package khi refactor**, nhưng nó vẫn là chọn **Java package root** chứ không phải giới hạn chính xác theo Gradle module/JAR. Nếu hai module chia sẻ package `demo.catalog`, scanner có thể đọc class từ cả hai nếu chúng nằm trên classpath.

Nếu muốn chỉ đưa ra **một vài bean** của module mà package chứa nhiều internal components, `basePackageClasses` không đủ; nên dùng explicit configuration, filters phù hợp hoặc tách package theo kiến trúc.

### 5.2. Quét chồng lên package con

`@ComponentScan(basePackages = {"demo.catalog", "demo.catalog.service"})` không cần thiết nếu đã scan `demo.catalog`. Package con đã được bao phủ. Khuyến nghị bỏ root thứ hai để cấu hình dễ đọc, dù scan lặp tương thích thường không gây lỗi.

Một root `demo.catalog.service` **không bao phủ** sibling `demo.catalog.persistence`. Nếu service phụ thuộc repository ở sibling, cấu hình hẹp có thể gây `UnsatisfiedDependencyException`. Đừng sửa bằng cách vội vàng mở sang `demo`: chọn đúng common root `demo.catalog` hoặc import/đăng ký chính xác những bean cần thiết.

### 5.3. Spring Boot và module boundaries

Trong Spring Boot, `@SpringBootApplication` bao gồm cơ chế component scan; mặc định root thường là package chứa class application. Đặt class tại root ứng dụng giúp scan các subpackage của ứng dụng, nhưng nếu root quá cao (ví dụ `demo`), các module library chia sẻ prefix có thể đều được quét.

Có thể cấu hình:

```java
@SpringBootApplication(
    scanBasePackageClasses = {
        CatalogMarker.class,
        AuditMarker.class
    }
)
public class MainApplication {
}
```

Đây là đoạn minh họa Boot; cần dependencies/imports thích hợp. Trong Boot, `scanBasePackages`/`scanBasePackageClasses` điều khiển **component scanning**, không thay thế cấu hình **JPA entity scanning** hoặc **Spring Data repository scanning** (`@EntityScan`, `@EnableJpaRepositories` trong bối cảnh phù hợp). Một Spring Data repository interface không được component scanner tạo proxy chỉ vì có package phù hợp; Spring Data có cơ chế riêng.

**Lưu ý khi tùy chỉnh:** nếu thêm `@ComponentScan` thủ công lên class Boot, cần kiểm tra những filter mặc định Boot cung cấp qua composed annotation và các cấu hình đang hoạt động. Đừng coi việc thay annotation quét là thay đổi hoàn toàn vô hại.

### 5.4. Điều kiện để module xuất hiện

| Điều kiện | Ảnh hưởng |
| --- | --- |
| Dependency vào module có trên runtime classpath | Class khả dụng để scanner tìm |
| Package của module nằm trong scan roots | Các component có cơ hội thành candidates |
| Có đúng stereotype/filters | Candidate được xét tiếp |
| `@Profile`/`@Conditional` phù hợp | Bean được đăng ký trong môi trường tương ứng |
| Bean name không xung đột | Registry có thể hoàn tất đăng ký |
| Dependency của bean đầy đủ | Có thể khởi tạo instance bình thường |

**Mấu chốt:** “mô-đun nằm trong build” và “bean của mô-đun có trong container” là hai việc khác nhau.

## 6. Các nguồn duplicate khác ngoài hai lượt scan

### 6.1. `@Component` và `@Bean` cùng đăng ký một trách nhiệm

```java
@Component
class MessageSender {
}

@Configuration
class SenderConfig {
    @Bean
    MessageSender messageSender() {
        return new MessageSender();
    }
}
```

Đây là **đoạn minh họa**. Nếu component được scan và method `@Bean` cũng được xử lý, bạn có thể gặp chồng chéo registration: trùng tên, một definition bị bỏ qua/ghi đè trong một số cấu hình, hoặc nhiều bean cùng kiểu nếu tên khác nhau. Kết quả cụ thể phụ thuộc tên và chính sách registry; **không giả định mỗi con đường luôn tạo một bean riêng**.

Đối với một component ứng dụng, thường chỉ cần một cách đăng ký. Với class bên thứ ba không chỉnh source, `@Bean` là lựa chọn rõ ràng.

### 6.2. `@Import` và `@ComponentScan` cùng phát hiện cấu hình

Một `@Configuration` vừa được component-scanned vừa được `@Import` có thể tham gia hai đường đăng ký. Spring configuration class processor có cơ chế xử lý metadata/configuration candidates, nhưng trường hợp có nhiều tên/nguồn không tương thích vẫn cần rà soát. Tránh phụ thuộc vào việc import/scan cùng một class nhiều lần để tăng số instance hoặc “đảm bảo” được xử lý.

### 6.3. Bean overriding và “ẩn” lỗi

`BeanDefinitionRegistry` có chính sách bean definition overriding tùy implementation/cấu hình. **Bật overriding không phải cách chữa mặc định** cho conflict:

- Với collision giữa hai scanned definitions không tương thích, scanner có thể ném `ConflictingBeanDefinitionException` thay vì cho definition thứ hai ghi đè.
- Với các nguồn đăng ký khác, ghi đè có thể khiến một bean mong đợi bị thay đổi âm thầm.
- Spring Boot hiện đại thường cấu hình chính sách chống override theo mặc định trừ khi cho phép tường minh; không dùng một setting override toàn cục chỉ để né lỗi chưa hiểu rõ.

Hướng đúng là làm rõ **ai sở hữu bean name**, package nào được scan, và nơi nào tạo bean. Nếu chủ ý thay thế một bean qua profile/condition, hãy chọn extension point hoặc policy chính thức thay vì dựa vào thứ tự đăng ký.

### 6.4. Component scanning không tự tạo Spring Data repository

Một interface `JpaRepository<Order, Long>` thường được Spring Data đăng ký dưới dạng repository proxy, theo cơ chế scan riêng. Nếu tìm xung đột bean name, cần phân biệt tên do component scanner, repository scanner và factory method tạo ra. Đổi `@ComponentScan` chưa chắc tác động tới các registry extension khác.

## 7. Ví dụ hoàn chỉnh Java 17+ và Spring 6: ba Gradle module

Ví dụ này chứng minh ba trường hợp:

1. Quét chồng lấn package catalog: một component vẫn chỉ có một bean definition tương thích.
2. Quét cả catalog và audit với tên mặc định: hai class `ReportService` khác package gây xung đột tên `reportService`.
3. Quét cả hai nhưng dùng `FullyQualifiedAnnotationBeanNameGenerator`: đăng ký thành công với hai tên riêng.

Dự án dùng Spring Framework `6.2.18` và Gradle multi-project, không cần Spring Boot, web server hoặc database.

### 7.1. Cấu trúc dự án

```text
component-scan-modules/
├── settings.gradle
├── build.gradle
├── catalog/
│   ├── build.gradle
│   └── src/main/java/demo/catalog/service/ReportService.java
├── audit/
│   ├── build.gradle
│   └── src/main/java/demo/audit/service/ReportService.java
└── app/
    ├── build.gradle
    └── src/main/java/demo/app/ScanConflictDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'component-scan-modules'
include 'catalog', 'audit', 'app'
```

File `build.gradle` tại root:

```groovy
subprojects {
    apply plugin: 'java'

    repositories {
        mavenCentral()
    }

    tasks.withType(JavaCompile).configureEach {
        options.release = 17
    }
}
```

Mỗi subproject đều có plugin Java, Maven Central và compile target Java 17. Cần chạy Gradle bằng một JDK tương thích; với ví dụ này sử dụng JDK 17 trở lên.

File `catalog/build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}
```

File `audit/build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}
```

File `app/build.gradle`:

```groovy
plugins {
    id 'application'
}

dependencies {
    implementation project(':catalog')
    implementation project(':audit')
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'demo.app.ScanConflictDemo'
}
```

Từ `app`, hai module được đưa lên runtime classpath nhờ dependency Gradle. Nhưng mỗi context vẫn có quyền quyết định package nào được component-scanned.

### 7.2. Component của catalog

File `catalog/src/main/java/demo/catalog/service/ReportService.java`:

```java
package demo.catalog.service;

import org.springframework.stereotype.Service;

@Service
public class ReportService {
    public String report() {
        return "catalog";
    }
}
```

Bean name mặc định trong một lượt scan thông thường là `reportService`.

### 7.3. Component của audit

File `audit/src/main/java/demo/audit/service/ReportService.java`:

```java
package demo.audit.service;

import org.springframework.stereotype.Service;

@Service
public class ReportService {
    public String report() {
        return "audit";
    }
}
```

Mặc dù class name ngắn trùng với catalog, tên Java đầy đủ `demo.audit.service.ReportService` là một kiểu khác. Default bean name vẫn là `reportService` nếu class được scanner tìm thấy.

### 7.4. Main class với ba context

File `app/src/main/java/demo/app/ScanConflictDemo.java`:

```java
package demo.app;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.FullyQualifiedAnnotationBeanNameGenerator;

public class ScanConflictDemo {

    @Configuration(proxyBeanMethods = false)
    @ComponentScan(basePackages = {
            "demo.catalog",
            "demo.catalog.service"
    })
    static class OverlapConfig {
    }

    @Configuration(proxyBeanMethods = false)
    @ComponentScan(basePackages = {
            "demo.catalog",
            "demo.audit"
    })
    static class CollisionConfig {
    }

    @Configuration(proxyBeanMethods = false)
    @ComponentScan(
            basePackages = {"demo.catalog", "demo.audit"},
            nameGenerator = FullyQualifiedAnnotationBeanNameGenerator.class
    )
    static class QualifiedConfig {
    }

    private static boolean hasNameConflict(Throwable error) {
        for (Throwable current = error;
                current != null;
                current = current.getCause()) {
            if ("ConflictingBeanDefinitionException"
                    .equals(current.getClass().getSimpleName())) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(OverlapConfig.class)) {
            String[] catalogNames = context.getBeanNamesForType(
                    demo.catalog.service.ReportService.class);
            System.out.println("overlap.beanCount = " + catalogNames.length);
            System.out.println("overlap.defaultName = " +
                    context.containsBean("reportService"));
        }

        boolean conflictFound = false;
        try (var context =
                     new AnnotationConfigApplicationContext(CollisionConfig.class)) {
            // Không vào nhánh này khi hai bean definitions xung đột.
        } catch (RuntimeException exception) {
            if (!hasNameConflict(exception)) {
                throw exception;
            }
            conflictFound = true;
        }
        System.out.println("default.conflict = " + conflictFound);

        try (var context =
                     new AnnotationConfigApplicationContext(QualifiedConfig.class)) {
            System.out.println("qualified.catalog = " +
                    context.containsBean("demo.catalog.service.ReportService"));
            System.out.println("qualified.audit = " +
                    context.containsBean("demo.audit.service.ReportService"));
            System.out.println("qualified.shortName = " +
                    context.containsBean("reportService"));

            String catalog = context.getBean(
                    demo.catalog.service.ReportService.class).report();
            String audit = context.getBean(
                    demo.audit.service.ReportService.class).report();
            System.out.println("qualified.reports = " + catalog + "," + audit);
        }
    }
}
```

Class cấu hình lồng nhau là `static`, độc lập với instance của `ScanConflictDemo`, được đưa trực tiếp vào `AnnotationConfigApplicationContext`. Ba context **không dùng chung registry**.

Method `hasNameConflict` kiểm tra exception chain theo tên class exception, chỉ nhằm trình bày output xác định mà không in toàn bộ stack trace; nếu lỗi khác xảy ra, chương trình ném lại exception để tránh che lỗi cấu hình không liên quan.

### 7.5. Lệnh chạy

Tại thư mục root `component-scan-modules`:

```bash
gradle :app:run --quiet
```

Với Gradle Wrapper: `./gradlew :app:run --quiet` (Linux/macOS) hoặc `.\gradlew.bat :app:run --quiet` (Windows PowerShell).

Các dòng **do chính chương trình in ra**:

```text
overlap.beanCount = 1
overlap.defaultName = true
default.conflict = true
qualified.catalog = true
qualified.audit = true
qualified.shortName = false
qualified.reports = catalog,audit
```

**Lưu ý về log:** Spring có thể ghi thêm cảnh báo/lỗi vào stderr khi context có collision; bảng trên chỉ mô tả các dòng `System.out.println`, không khẳng định toàn bộ output của process chỉ có các dòng này.

### 7.6. Giải thích từng kết quả

- `overlap.beanCount = 1`: root `demo.catalog` đã bao phủ `demo.catalog.service`. Quét lại package con tìm đúng class ban đầu, nên scanner không đăng ký thêm một definition không tương thích.
- `overlap.defaultName = true`: class catalog được đăng ký dưới tên mặc định `reportService`.
- `default.conflict = true`: trong `CollisionConfig`, catalog và audit cùng sinh tên `reportService` dù class khác nhau; scanner phát hiện collision.
- `qualified.catalog = true` và `qualified.audit = true`: generator fully-qualified đặt hai tên tách biệt.
- `qualified.shortName = false`: hai component không khai báo tên tường minh; strategy này không đăng ký alias `reportService` mặc định.
- `qualified.reports = catalog,audit`: có thể lấy hai bean qua **class đầy đủ** tương ứng và gọi method của từng module mà không cần cast.

**Giới hạn:** ví dụ chỉ minh họa component scanning và naming. Khi cả hai bean implement cùng một interface, việc inject interface đơn vẫn có thể mơ hồ dù tên đã phân biệt; đó là bài toán autowiring cần `@Qualifier`/`@Primary` riêng.

## 8. Tách ranh giới bằng configuration entry point

Nếu `audit` là library, ứng dụng có thể muốn **dùng đúng một adapter** nhưng không muốn scan mọi class nội bộ thuộc `demo.audit`.

Một lựa chọn là module audit công bố class cấu hình:

```java
package demo.audit.config;

import demo.audit.service.ReportService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AuditModuleConfig {

    @Bean("auditReportService")
    ReportService auditReportService() {
        return new ReportService();
    }
}
```

Đây là **biến thể thiết kế minh họa**, không nằm trong mã dự án chạy mục 7. Nếu giữ `@Service` trên `ReportService` và đồng thời scan `demo.audit`, có thể tạo thêm definition hoặc chồng đăng ký tùy tên/cấu hình; khi chuyển hoàn toàn sang explicit configuration thì nên **không scan implementation ấy** hoặc bỏ stereotype khỏi class để tránh đăng ký hai lần.

Ứng dụng có thể sử dụng:

```java
@Configuration
@Import(AuditModuleConfig.class)
@ComponentScan(basePackages = "demo.catalog")
class AppComposition {
}
```

Đoạn trên cần imports `@Configuration`, `@Import`, `@ComponentScan` và `AuditModuleConfig`. Phương thức `@Bean("auditReportService")` định nghĩa chính xác một bean audit theo hợp đồng module. Lợi ích:

- Application chọn rõ module/configuration nào tham gia context.
- Không cần scan tất cả internal package của library.
- Bean names/roles công bố qua configuration được kiểm soát.
- Tránh vô tình đưa các component thử nghiệm hoặc optional adapter vào ứng dụng chỉ vì chúng có trên classpath.

Tuy nhiên, `@Import` class configuration vẫn cho phép configuration đó đăng ký nhiều bean definitions và import khác. Cần xem nó như **API tích hợp module**, và review nội dung cấu hình như các dependency khác.

### 8.1. Cân nhắc auto-configuration

Trong Spring Boot, một thư viện có thể cung cấp auto-configuration đăng ký bean theo `@ConditionalOnClass`, `@ConditionalOnMissingBean` hoặc những điều kiện tương ứng. Đây là extension point riêng, không cần scanner quét tất cả package của thư viện. Khi xây Spring Boot starter, nên dùng auto-configuration theo quy ước Boot thay vì bắt người dùng thêm scan root rộng.

Không nhầm `@ComponentScan` với auto-configuration: một library JAR có mặt trên classpath chưa chắc bean của nó được đăng ký bằng component scan, và một bean do auto-configuration tạo cũng không cần class implementation mang `@Component`.

## 9. Trùng bean name và tên tường minh: lưu ý khi sửa

Dùng `FullyQualifiedAnnotationBeanNameGenerator` là giải pháp tốt cho **tên mặc định** của hai class khác package. Nhưng nếu chúng khai báo:

```java
@Service("sharedReport")
class CatalogReportService {
}

@Service("sharedReport")
class AuditReportService {
}
```

Hai đoạn minh họa trên là hai class khác nhau với **cùng tên explicit**. Fully-qualified generator vẫn tôn trọng `"sharedReport"`, nên conflict vẫn có thể xuất hiện. Hãy đặt tên tường minh riêng theo vai trò, hoặc điều chỉnh phạm vi scan.

Một hệ thống đang dùng `@Qualifier("reportService")`, `@Resource(name="reportService")`, `getBean("reportService")` hay `Map<String, ReportPort>` cũng sẽ chịu ảnh hưởng khi chuyển sang fully-qualified names. Bean name là một phần hợp đồng nếu code/config bên ngoài tham chiếu bằng string.

**Không chủ động đổi generator toàn hệ thống** chỉ để sửa một conflict lẻ nếu ứng dụng phụ thuộc nhiều vào bean names hiện có. Khi đó một cách sửa hẹp như đặt tên explicit cho hai component xung đột hoặc giới hạn scan có thể dễ kiểm soát hơn.

## 10. Lỗi thường gặp và phương án điều tra

| Biểu hiện | Khả năng xảy ra | Cách kiểm tra/sửa |
| --- | --- | --- |
| `ConflictingBeanDefinitionException` với `reportService` | Hai class khác nhau cùng short name ở hai package được scan | Đối chiếu FQCN của hai classes; dùng explicit names, FQ generator hoặc giảm scan |
| Quét cùng package hai lần mà không lỗi | Scanner bỏ qua definition tương thích từ cùng class | Đây là hành vi có thể mong đợi; không giả định hai instances |
| Thêm `implementation project(':audit')` rồi startup lỗi conflict | Class audit nay có trên runtime classpath và root scan đủ rộng | Thu hẹp root/explicit registration thay vì scan mọi module |
| `NoUniqueBeanDefinitionException` sau khi sửa tên trùng | Hai bean khác names nhưng cùng implement interface được inject đơn | Chọn qua `@Qualifier`/`@Primary` hoặc inject collection |
| `NoSuchBeanDefinitionException` sau khi thu hẹp scan | Bean cần thiết nằm ở package ngoài roots | Thêm root phù hợp hoặc import configuration module |
| Bean có mặt dù package không được scan | Được tạo qua `@Bean`, `@Import`, Spring Data, auto-config hoặc registration khác | Tìm nguồn bean definition; đừng chỉ đọc `@ComponentScan` |
| Gắn `@Component` và `@Bean` cùng class | Trùng đường đăng ký hoặc có nhiều beans cùng type | Chọn một chiến lược rõ ràng, kiểm tra registry |
| Bật bean overriding nhưng scanner vẫn báo conflict | Hai scanned definitions không tương thích có thể bị chặn trước override bình thường | Sửa naming/scan boundaries; không dựa vào override |
| Xung đột xuất hiện chỉ ở test | Test context quét rộng, import nhiều configs hoặc profile khác | So sánh test configuration, package roots, active profiles |
| Một module dùng chung package root với module khác | Scan theo package có thể kéo class từ cả hai JAR | Tách package theo module responsibility hoặc dùng explicit config |
| Component thư viện không được quét | Thiếu dependency runtime hoặc package không trong roots | Kiểm tra Gradle runtimeClasspath và annotation/filter |
| Bean được đăng ký nhưng tạo thất bại | Constructor dependency thiếu, circular dependency, scope hoặc factory lỗi | Đọc exception chain, phân biệt registration với instantiation |
| Conflict explicit name dù dùng FQ generator | Built-in generator giữ tên tường minh | Sửa các `@Service("...")`/custom stereotype aliases |
| Spring Data repository chưa thấy dù component scan rộng | Repository interface dùng cơ chế Spring Data riêng | Kiểm tra `@EnableJpaRepositories`/repository bootstrap |
| Scan `demo` gây rất nhiều beans | Root quá cao bao gồm module ngoài ý muốn | Chọn từng package root bằng marker hoặc import module config |

### 10.1. Cách debug có hệ thống

**Bước 1 — Xác định loại exception.** `ConflictingBeanDefinitionException` liên quan bean definition names trong lúc scan; `NoUniqueBeanDefinitionException` liên quan nhiều candidates lúc resolve dependency; `NoSuchBeanDefinitionException` thường nghĩa là không có bean phù hợp.

**Bước 2 — Đọc hai phía của conflict.** Nếu thông báo liệt kê hai class với tên đầy đủ, hãy xác định chúng đến từ module/JAR nào và vì sao cả hai được scan.

**Bước 3 — Xác định package roots đang hoạt động.** Kiểm tra `@ComponentScan` trên các cấu hình thực sự đăng ký, vị trí `@SpringBootApplication` và các import/auto-config liên quan. Không giả định cấu hình chỉ có đúng một scanner.

**Bước 4 — Kiểm tra runtime classpath.** Trong Gradle, từ module app có thể dùng lệnh:

```bash
gradle :app:dependencies --configuration runtimeClasspath
```

Nếu một module bất ngờ xuất hiện, kiểm tra khai báo dependency. Công cụ dependency graph cho biết **sự hiện diện của JAR/module**, không trả lời trực tiếp những bean nào đã được scan.

**Bước 5 — Xem bean definitions với context chạy được.** Ví dụ trong mã có `AnnotationConfigApplicationContext context`:

```java
String[] names = context.getBeanNamesForType(
        demo.catalog.service.ReportService.class);
java.util.Arrays.sort(names);
System.out.println(java.util.Arrays.toString(names));
```

Đây là đoạn minh họa, cần class trong runtime classpath. Nếu context đã thất bại khi refresh do conflict, bạn phải **sửa hoặc thu hẹp cấu hình trước**, rồi mới inspect registry cuối cùng. Không thể gọi `getBean...` trên một context không khởi tạo thành công.

**Bước 6 — Rà soát hợp đồng bean name.** Sau khi đổi generator, kiểm tra `@Qualifier`, `@Resource`, bean name string và map keys; test lại chức năng thực tế. Bean registry tạo được không đảm bảo mọi consumer đã được cập nhật.

## 11. Kiến trúc quét có kiểm soát cho dự án nhiều mô-đun

### 11.1. Ranh giới rõ ràng hơn package root toàn cục

Một quy ước hữu ích:

```text
com.example.app               -> composition root / main app
com.example.catalog           -> catalog public config + internal packages
com.example.audit             -> audit public config + internal packages
com.example.integration.*     -> integrations tùy chọn theo profile/condition
```

Thay vì `@ComponentScan("com.example")`, application chỉ scan package thuộc trách nhiệm trực tiếp, và dùng `@Import`/module configuration hoặc Boot auto-configuration cho library. Điều này tránh việc thêm một dependency Gradle lập tức đưa mọi component của thư viện vào registry.

### 11.2. Một module, nhiều package

Nếu một Gradle module `:catalog` có cả `com.example.catalog` và `com.example.sharedcatalog`, một marker `CatalogMarker` ở package đầu chỉ bao phủ một nhánh. Lúc đó hãy dùng nhiều root markers hoặc tổ chức lại package nếu điều đó phản ánh đúng kiến trúc. Đừng tưởng Spring suy ra toàn bộ module build từ class marker.

### 11.3. Một package nằm ở nhiều JAR

Nếu hai Gradle module cùng khai báo classes dưới `com.example.catalog`, scanner quét package này sẽ xem các class khả dụng từ cả hai JAR khi runtime classpath chứa chúng. Nếu kiến trúc cần cách ly, phải thay đổi packaging/classpath hoặc chọn explicit bean configuration; không thể chỉ dùng string package root để ràng buộc scanner chính xác theo JAR.

### 11.4. Filters và conditions

`@ComponentScan` có `excludeFilters`, `includeFilters`, `useDefaultFilters`, nhưng chúng vận hành **bên trong phạm vi package đã chọn**. Ví dụ:

```java
@Configuration
@ComponentScan(
    basePackages = "com.example",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = LegacyReportService.class
    )
)
class AppConfig {
}
```

Đây là đoạn minh họa, cần imports và class `LegacyReportService` tương ứng. Exclude filter có thể loại một class khỏi **lượt scan này**, nhưng không cấm một `@Bean` khác đăng ký class ấy. Khi số lượng exclusions tăng nhiều, đó có thể là dấu hiệu base package đã chọn quá rộng.

`@Profile` và `@Conditional` còn có thể loại các component theo môi trường/cấu hình. Để bảo đảm test/prod cùng đúng, kiểm thử phạm vi scan với các active profiles và điều kiện quan trọng.

### 11.5. Naming convention

Đặt tên bean theo **vai trò** khi thật sự cần tham chiếu theo tên. Nếu hai modules có `ReportService`, tên `catalogReportService` và `auditReportService` diễn đạt intent rõ hơn hai tên ngắn `reportService`. FQ generator giúp tránh collision quy mô lớn nhưng khiến tên phụ thuộc vào package; refactor package có thể làm thay đổi bean name. Khi một bean name là external contract, ưu tiên explicit name có chủ đích và tests.

## 12. Bài tập có đáp án

### Bài 1 — Scan chồng lấn

Config quét `demo.catalog` và `demo.catalog.service`; class `demo.catalog.service.ReportService` có `@Service`. Có chắc sẽ sinh hai singleton không?

**Đáp án:** Không. Đây là trường hợp cùng class xuất hiện trong hai root giao nhau, scanner có cơ chế kiểm tra candidate tương thích và thường chỉ giữ một bean definition.

### Bài 2 — Trùng class name ở hai modules

Hai module chứa `demo.catalog.service.ReportService` và `demo.audit.service.ReportService`, mỗi class có `@Service`. Config quét cả hai package, dùng default generator. Nguyên nhân conflict chính là gì?

**Đáp án:** Hai types khác nhau cùng sinh **bean name** `reportService`. Java class names vẫn khác, nhưng registry không đăng ký hai definitions không tương thích dưới cùng tên.

### Bài 3 — Fully-qualified generator có phải luôn giải quyết collision?

Giả sử cả hai class đều có `@Service("reportService")`. Thay `AnnotationBeanNameGenerator` bằng `FullyQualifiedAnnotationBeanNameGenerator` có đủ không?

**Đáp án:** Không. Built-in FQ generator giữ explicit name. Cần sửa tên explicit hoặc giới hạn registration.

### Bài 4 — Tên đã phân biệt nhưng injection vẫn lỗi

Hai bean `catalogReportService` và `auditReportService` đều implement `ReportPort`. Constructor `Reporter(ReportPort port)` bị `NoUniqueBeanDefinitionException`. Có phải scanner vẫn đang tạo trùng tên?

**Đáp án:** Không. Đây là ambiguity **theo kiểu**, không phải duplicate name. Sửa bằng `@Qualifier`/`@Primary` hoặc nhận collection khi nghiệp vụ thực sự cần cả hai.

### Bài 5 — Gradle dependency và root scan

`:app` có `implementation project(':audit')` nhưng chỉ quét `demo.catalog`. Bean `demo.audit.service.ReportService` có tự xuất hiện không?

**Đáp án:** Không qua lượt scan đó. Gradle thêm class vào classpath; để là bean cần scan/registration phù hợp và các điều kiện khác.

### Bài 6 — Marker được đặt ở package quá sâu

`@ComponentScan(basePackageClasses = CatalogServiceMarker.class)` với marker nằm trong `demo.catalog.service`. Repo bean ở `demo.catalog.persistence` có được quét không?

**Đáp án:** Không vì package persistence là sibling. Chọn marker tại `demo.catalog` hoặc nhập cấu hình repo phù hợp.

### Bài 7 — Quét package toàn cục

App trước đây chỉ có `catalog`; sau khi thêm dependency `audit` thì startup có conflict. Có nên bật bean override toàn hệ thống ngay không?

**Đáp án:** Không. Hãy xem component scan root có đang bao gồm cả audit package, xác định hai bean definitions xung đột, rồi thu hẹp scan, đổi naming hoặc đăng ký tường minh. Bật override có thể che vấn đề và không đảm bảo scanner chấp nhận definitions không tương thích.

### Bài 8 — Lựa chọn cấu hình mô-đun

Một module chứa 40 internal components nhưng app chỉ cần một adapter. Quét toàn bộ package module hay import một configuration công khai với một `@Bean`?

**Đáp án:** Import configuration công khai thường diễn đạt ranh giới rõ hơn khi module được thiết kế như một thư viện tích hợp. Cần bảo đảm class không đồng thời được scan ở con đường khác để tránh chồng registration.

### Bài 9 — Hai contexts

Context A scan catalog, context B scan audit; mỗi context có bean name `reportService`. Có phải chắc chắn sẽ gặp `ConflictingBeanDefinitionException`?

**Đáp án:** Không. Hai registry độc lập có thể dùng cùng tên; conflict đăng ký xảy ra khi definitions không tương thích tranh một tên trong cùng registry.

## 13. Checklist trước khi sửa một lỗi do quét trùng

1. Đọc exception chain để phân biệt **duplicate bean name**, **missing bean** và **ambiguous type**.
2. Xác định **package/class name đầy đủ** của từng bean liên quan.
3. Xác định **runtime module/classpath** chứa các bean ấy và các Gradle dependencies.
4. Liệt kê các root của **component scan thực sự hoạt động**, kể cả scan mặc định của Boot và config nhập thêm.
5. Kiểm tra đó là **cùng class quét lặp** hay **hai class khác nhau cùng bean name**.
6. Kiểm tra các đường đăng ký khác: `@Bean`, `@Import`, library auto-configuration, Spring Data.
7. Chọn một giải pháp có chủ đích: thu hẹp root, explicit names, FQ generator, module configuration hoặc filters.
8. Sau khi đổi tên, kiểm tra `@Qualifier`, `@Resource`, map keys và `getBean(String)`.
9. Kiểm thử context tương ứng với profiles/test/prod quan trọng; xác nhận đủ bean và không còn conflict.
10. Tránh dựa vào scan order hoặc bật global bean override để giấu vấn đề.

## 14. Ghi nhớ

- **Quét chồng lấn cùng component** thường được scanner nhận diện là cùng/compatible bean definition và bỏ qua đăng ký lặp; không đồng nghĩa tự sinh duplicate singleton.
- **Xung đột thực sự** thường bắt nguồn từ **hai bean definitions không tương thích cùng tên**, đặc biệt hai class khác package có simple class name giống nhau dưới default naming.
- **Gradle module** quyết định classpath, **Java package** quyết định phạm vi component scan, **bean name** quyết định định danh trong registry. Đây là ba ranh giới riêng.
- **Component scan root không phải module boundary theo JAR**. Thêm dependency có thể khiến scanner quét thêm component nếu package roots đã bao phủ nó.
- **Tên khác nhau không giải quyết tự động ambiguity theo type**. Sau khi đăng ký thành công, dependency đơn có thể cần `@Qualifier` hoặc `@Primary`.
- Khắc phục bằng scan scope rõ ràng, explicit naming, `FullyQualifiedAnnotationBeanNameGenerator` hoặc configuration entry point riêng cho module. Không dùng bean overriding như cách sửa mặc định.

### Tài liệu chính thức

- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html).
- [Spring Framework 6.2 — `ClassPathBeanDefinitionScanner` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/ClassPathBeanDefinitionScanner.html).
- [Spring Framework 6.2 — `@ComponentScan` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/ComponentScan.html).
- [Spring Framework 6.2 — `FullyQualifiedAnnotationBeanNameGenerator` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/FullyQualifiedAnnotationBeanNameGenerator.html).
- [Spring Framework — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html).
- [Spring Boot — Structuring Your Code](https://docs.spring.io/spring-boot/reference/using/structuring-your-code.html).
