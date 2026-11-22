# Kết hợp nhiều điều kiện trong Spring Boot: quy tắc tất cả điều kiện phải thỏa mãn

## 1. Mục tiêu và mô hình tư duy

Spring Boot auto-configuration cung cấp các bean mặc định **có điều kiện** thay vì đăng ký mọi bean một cách vô điều kiện. Khi một class hoặc một phương thức **@Bean** mang nhiều annotation điều kiện, câu hỏi quan trọng không phải là “một điều kiện nào đó đúng chưa?” mà là **“tất cả các điều kiện cần thiết đã thỏa mãn chưa?”**.

Ví dụ, một thư viện muốn cung cấp bean **FeatureStatus** chỉ khi:

1. API Jackson cần thiết hiện diện trên classpath;
2. tính năng được bật bởi thuộc tính cấu hình;
3. chế độ hoạt động là **standard**;
4. ứng dụng chưa cung cấp bean **FeatureStatus** của chính mình.

Bốn yêu cầu này có quan hệ logic **AND**. Nếu thiếu một yêu cầu, Spring Boot không nên tạo **FeatureStatus** mặc định.

Ký hiệu:

~~~text
C = class bắt buộc có trên classpath
E = property enabled cho phép tính năng
M = property mode phù hợp
B = chưa có bean cùng kiểu từ ứng dụng

Tạo bean mặc định = C AND E AND M AND B
                  = C ∧ E ∧ M ∧ B
~~~

Người học sẽ nắm được:

- Cách Spring kết hợp nhiều **@Conditional...** trên cùng class và phương thức bean.
- Cách condition cấp class và cấp phương thức cùng tác động.
- Vì sao một điều kiện **false** đủ ngăn bean mặc định.
- Cách hiểu **@ConditionalOnProperty** khi có nhiều tên property, **havingValue**, **matchIfMissing**.
- Phân biệt AND mặc định với OR/NOT cần biểu diễn rõ ràng.
- Cách dùng **ApplicationContextRunner** chứng minh từng trường hợp và tránh hiểu sai khi bean do người dùng định nghĩa xuất hiện.
- Cách đọc **Condition Evaluation Report** để biết điều kiện nào không thỏa mãn.

Bài thực hành sử dụng **Java 21**, **Gradle** và **Spring Boot 3.3.13** làm phiên bản ví dụ cố định; không hàm ý đây là phiên bản mới nhất.

## 2. Cơ chế tổng quát: điều kiện là cổng cho cấu hình và bean

Trong Spring, **@Conditional** gắn một hoặc nhiều phép kiểm tra vào một class cấu hình hoặc một phương thức bean. Spring Boot xây dựng nhiều annotation thuận tiện dựa trên cơ chế này, ví dụ:

| Annotation | Phát biểu điều kiện |
| --- | --- |
| **@ConditionalOnClass** | Những class yêu cầu có thể tìm thấy trên classpath. |
| **@ConditionalOnMissingClass** | Những class được chỉ định không hiện diện. |
| **@ConditionalOnBean** | Những bean cần thiết đã được đăng ký theo semantics của điều kiện. |
| **@ConditionalOnMissingBean** | Chưa có bean phù hợp nên cấu hình mặc định có thể nhường quyền. |
| **@ConditionalOnProperty** | Property có giá trị hoặc trạng thái tồn tại phù hợp. |
| **@ConditionalOnWebApplication** | Context phù hợp loại ứng dụng web yêu cầu. |
| **@ConditionalOnNotWebApplication** | Context không phải ứng dụng web. |
| **@ConditionalOnResource** | Tài nguyên cấu hình được chỉ định hiện diện. |

Một annotation condition **không tự tạo bean**. Nó trả lời có nên cho phép framework xử lý class/method tương ứng hay không. Việc tạo bean còn phụ thuộc các bước đăng ký, dependency injection, lifecycle và những cấu hình khác.

### 2.1. AND khi nhiều annotation cùng xuất hiện

Mẫu minh họa:

~~~java
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true"
)
@AutoConfiguration
public class FeatureAutoConfiguration {
    // ...
}
~~~

Đây là **đoạn annotation/class minh họa**, chưa phải file Java đầy đủ. Để class cấu hình được áp dụng, cả **classpath condition** và **property condition** phải match. Một annotation đúng không “cứu” annotation khác sai.

Ở cấp phương thức:

~~~java
@Bean
@ConditionalOnMissingBean(FeatureStatus.class)
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "mode",
    havingValue = "standard"
)
FeatureStatus featureStatus() {
    return new FeatureStatus("standard");
}
~~~

Tương tự, **cả hai điều kiện tại method** phải đạt. Khi method nằm trong class có điều kiện, điều kiện của class cũng phải đạt trước khi method có cơ hội tạo bean.

### 2.2. AND giữa cấp class và cấp @Bean

Gọi **C** và **E** là condition của class, **M** và **B** là condition của method:

~~~text
Class auto-configuration được áp dụng?
  C AND E
      |
     false --> class bị bỏ qua; method bean không được đăng ký
      |
     true
      v
Method @Bean có đủ điều kiện?
  M AND B
      |
     false --> không đăng ký FeatureStatus mặc định
      |
     true
      v
Đăng ký định nghĩa bean và tạo instance theo vòng đời Spring
~~~

Không nên hình dung rằng framework **bắt buộc** chạy mọi phép kiểm tra rồi thu đủ bốn boolean trước khi quyết định. Ở thực tế, Spring có thể **dừng/loại một nhánh sớm** và không đánh giá những điều kiện không còn cần thiết. Mô hình AND nói về **quy tắc kết quả**, không hứa hẹn thứ tự thực thi hoặc số lần gọi condition.

## 3. Bảng chân trị: chỉ khi tất cả đúng mới tạo bean mặc định

Với **C ∧ E ∧ M ∧ B**:

| C | E | M | B | Tạo FeatureStatus mặc định? | Giải thích |
| --- | --- | --- | --- | --- | --- |
| Đúng | Đúng | Đúng | Đúng | **Có** | Đủ bốn điều kiện. |
| Sai | Đúng | Đúng | Đúng | Không | Thiếu class yêu cầu. |
| Đúng | Sai | Đúng | Đúng | Không | Tính năng bị tắt. |
| Đúng | Đúng | Sai | Đúng | Không | Chế độ không phù hợp. |
| Đúng | Đúng | Đúng | Sai | Không | Đã có bean do người dùng cung cấp. |
| Sai | Sai | Đúng | Đúng | Không | Có ít nhất một điều kiện sai. |
| Đúng | Sai | Sai | Đúng | Không | Hai property không đáp ứng. |
| Sai | Sai | Sai | Sai | Không | Không có điều kiện nào đủ. |

Bảng này nêu các hàng đại diện. Với bốn boolean có tất cả **16** tổ hợp; kết quả “Có” chỉ ở tổ hợp **Đúng/Đúng/Đúng/Đúng**.

**Lưu ý quan trọng:** Cột “Tạo FeatureStatus mặc định?” không có nghĩa “Context có hay không có FeatureStatus”. Khi **B = Sai** vì ứng dụng **đã có bean FeatureStatus**, context vẫn có thể chứa bean ấy. Chỉ **bean mặc định của auto-configuration** được nhường quyền.

### 3.1. Thứ tự khai báo annotation không có nghĩa thứ tự AND

Đổi thứ tự hai annotation condition trong source Java không biến phép AND thành OR. Không dùng thứ tự dòng annotation để ép việc check nào chạy trước. Khi có phụ thuộc thứ tự xử lý bean, hãy xử lý bằng thiết kế auto-configuration phù hợp và cơ chế ordering được hỗ trợ, không bằng cách hoán đổi dòng code.

### 3.2. Một điều kiện có thể nằm trong composed annotation

Spring cho phép sử dụng meta-annotation hoặc điều kiện tự định nghĩa. Khi viết một annotation tổng hợp, cần hiểu những condition nó mang theo; về nguyên tắc các condition áp dụng cho cùng thành phần vẫn phải cùng cho phép thành phần đó được xử lý, trừ khi bạn **chủ động xây dựng condition tổng hợp có logic khác**.

Với **@ConditionalOnClass** trong meta-annotation, tài liệu Spring Boot lưu ý nên sử dụng thuộc tính **name** thay cho class literal để tránh vấn đề xử lý metadata trong một số trường hợp.

## 4. Hiểu chính xác @ConditionalOnProperty khi kết hợp điều kiện

**@ConditionalOnProperty** là nguồn hiểu nhầm lớn nhất vì nó phân biệt ba thứ: property có tồn tại không, giá trị đang là gì, và điều gì được xem là match khi property bị thiếu.

### 4.1. havingValue và matchIfMissing

Ví dụ:

~~~java
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
~~~

Ý nghĩa:

- Nếu **demo.feature.enabled=true**: match.
- Nếu **demo.feature.enabled=false**: không match.
- Nếu **demo.feature.enabled** không được khai báo: **match** vì **matchIfMissing=true**.
- Nếu property hiện diện với giá trị khác **true**: không match theo giá trị yêu cầu.

**matchIfMissing=true** không có nghĩa Spring đổi property bị thiếu thành chuỗi **true** hoặc tạo ra một property mới. Nó chỉ quyết định **kết quả condition khi không tìm thấy property**.

Nếu dùng:

~~~java
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled"
)
~~~

thì **havingValue** mặc định là chuỗi rỗng, và điều kiện cơ bản match khi property **tồn tại** và **khác false** theo semantics của **@ConditionalOnProperty**. Không nên diễn giải cú pháp mặc định thành “phải bằng boolean true”. Muốn cấu hình bật/tắt rõ ràng, thường nên viết **havingValue = "true"**.

### 4.2. Nhiều name trong một @ConditionalOnProperty cũng là AND

Ví dụ:

~~~java
@ConditionalOnProperty(
    prefix = "demo.audit",
    name = {"enabled", "persisted"},
    havingValue = "true"
)
~~~

Đây là **một annotation** nhưng hai key:

~~~text
demo.audit.enabled
demo.audit.persisted
~~~

**Cả hai phải có giá trị phù hợp**. Không phải “enabled hoặc persisted”. Vì **matchIfMissing** không được khai báo, mặc định là **false** khi key bị thiếu.

| enabled | persisted | Điều kiện match? |
| --- | --- | --- |
| true | true | Có |
| true | false | Không |
| false | true | Không |
| false | false | Không |
| true | thiếu | Không |

Ví dụ này là một minh họa về **AND bên trong một annotation**, khác với AND giữa các annotation độc lập nhưng cho kết quả logic tương tự.

Nếu dùng **name = {"enabled", "persisted"}** với **matchIfMissing=true**, từng key bị thiếu có thể được coi là match theo chính sách missing của annotation; điều đó có thể khiến cấu hình bật khi người vận hành chưa chủ động xác nhận cả hai. Vì vậy với những tính năng quan trọng nên viết tường minh semantics mong muốn và bổ sung kiểm thử.

### 4.3. Các giới hạn của property condition

**@ConditionalOnProperty** đọc các key trong **Environment**; nó không phải công cụ xác thực cấu hình phức tạp. Với thuộc tính dạng **collection**, ví dụ cấu hình **demo.items[0]** mà chỉ kiểm tra **demo.items**, kết quả có thể không phản ánh điều người viết mong đợi. Khi cần kiểm tra nội dung collection hoặc quy tắc kết hợp phức tạp, hãy dùng giải pháp phù hợp như **@ConfigurationProperties** với validation và một condition tùy chỉnh khi thật sự cần.

### 4.4. Bảng nhanh một key có havingValue="true"

| Giá trị property | matchIfMissing=false | matchIfMissing=true |
| --- | --- | --- |
| Không tồn tại | Không | Có |
| "true" | Có | Có |
| "false" | Không | Không |
| "other" | Không | Không |

Đối với ví dụ bài thực hành, **enabled** và **mode** được đặt riêng trên class/method. Cả hai cùng cho phép **thiếu key** để ví dụ mặc định tạo bean, còn khi người dùng khai báo giá trị không phù hợp thì bean bị bỏ qua.

## 5. Một ví dụ hoàn chỉnh, chạy được bằng Java 21 và Gradle

Xây một workspace gồm:

- Module **feature-autoconfigure**: định nghĩa **FeatureStatus**, lớp **@AutoConfiguration** và tệp **AutoConfiguration.imports**.
- Module **sample-app**: một ứng dụng Spring Boot chạy không cần web server, in ra số lượng bean và nhãn của bean để kiểm chứng.
- Kiểm thử trong module thư viện bằng **ApplicationContextRunner**, điều chỉnh classpath/property/bean người dùng để chứng minh phép AND.

Để có classpath condition kiểm chứng được, ví dụ chọn **ObjectMapper** của Jackson làm **class marker**. Cấu hình mẫu không sử dụng ObjectMapper để xử lý JSON; sự tồn tại của class được dùng làm một dữ kiện độc lập trong tổ hợp điều kiện. Một tích hợp production thật sẽ chỉ kiểm tra class nếu cần API đó.

### 5.1. Cấu trúc thư mục

~~~text
conditional-and-lab/
├── settings.gradle
├── build.gradle
├── feature-autoconfigure/
│   ├── build.gradle
│   ├── src/main/java/com/example/condition/api/
│   │   └── FeatureStatus.java
│   ├── src/main/java/com/example/condition/autoconfigure/
│   │   └── FeatureAutoConfiguration.java
│   ├── src/main/resources/META-INF/spring/
│   │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│   └── src/test/java/com/example/condition/autoconfigure/
│       └── FeatureAutoConfigurationTests.java
└── sample-app/
    ├── build.gradle
    └── src/main/java/com/example/consumer/
        └── SampleApplication.java
~~~

### 5.2. settings.gradle

~~~groovy
rootProject.name = 'conditional-and-lab'
include 'feature-autoconfigure', 'sample-app'
~~~

### 5.3. build.gradle ở root

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.13' apply false
    id 'io.spring.dependency-management' version '1.1.7' apply false
}

subprojects {
    apply plugin: 'java'
    apply plugin: 'io.spring.dependency-management'

    group = 'com.example'
    version = '1.0.0'

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(21)
        }
    }

    repositories {
        mavenCentral()
    }

    dependencyManagement {
        imports {
            mavenBom 'org.springframework.boot:spring-boot-dependencies:3.3.13'
        }
    }

    tasks.withType(Test).configureEach {
        useJUnitPlatform()
    }
}
~~~

Root quản lý Java toolchain, phiên bản dependency và cấu hình JUnit Platform. **Spring Boot Gradle plugin chỉ được áp dụng cho ứng dụng**, không áp dụng lên module thư viện để tránh biến thư viện thành executable bootJar.

### 5.4. feature-autoconfigure/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-json'
}
~~~

**Giải thích:** Class auto-configuration dùng API Spring Boot. Test dùng Spring Boot test và starter JSON để bảo đảm **ObjectMapper** có trên test classpath khi không bị chủ động che bởi **FilteredClassLoader**. Module thư viện **không bắt buộc consumer cài Jackson** vì điều kiện dùng **name** dạng chuỗi.

### 5.5. sample-app/build.gradle

~~~groovy
plugins {
    id 'org.springframework.boot'
}

dependencies {
    implementation project(':feature-autoconfigure')
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-json'
}
~~~

**spring-boot-starter** cung cấp nền tảng cho ứng dụng không cần web; **spring-boot-starter-json** đưa Jackson vào runtimeClasspath, giúp classpath condition match trong cấu hình chuẩn.

### 5.6. Định nghĩa type của bean mặc định

Tệp **feature-autoconfigure/src/main/java/com/example/condition/api/FeatureStatus.java**:

~~~java
package com.example.condition.api;

public record FeatureStatus(String label) {
}
~~~

Record Java 21 này chỉ chứa nhãn để dễ kiểm chứng bean mặc định hoặc bean người dùng. Mục tiêu là học về **điều kiện**, không phải nghiệp vụ.

### 5.7. Class auto-configuration có hai điều kiện, method có hai điều kiện

Tệp **feature-autoconfigure/src/main/java/com/example/condition/autoconfigure/FeatureAutoConfiguration.java**:

~~~java
package com.example.condition.autoconfigure;

import com.example.condition.api.FeatureStatus;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(
    name = "com.fasterxml.jackson.databind.ObjectMapper"
)
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "demo.feature",
        name = "mode",
        havingValue = "standard",
        matchIfMissing = true
    )
    @ConditionalOnMissingBean(FeatureStatus.class)
    public FeatureStatus featureStatus() {
        return new FeatureStatus("standard");
    }
}
~~~

Giải thích đúng thứ tự trách nhiệm, **không** phải hứa hẹn thứ tự runtime của từng condition:

1. **@AutoConfiguration** cho phép class được sử dụng như ứng viên tự cấu hình.
2. **@ConditionalOnClass** yêu cầu ObjectMapper tồn tại trên classpath.
3. **@ConditionalOnProperty(enabled)** yêu cầu tính năng không bị tắt, với mặc định cho phép khi key chưa được khai báo.
4. **@ConditionalOnProperty(mode)** yêu cầu chế độ **standard**, cũng cho phép key vắng mặt.
5. **@ConditionalOnMissingBean(FeatureStatus.class)** chỉ tạo bean mặc định khi ứng dụng chưa cung cấp bean FeatureStatus khác.

Nếu điều kiện ở cấp class thất bại, phương thức **featureStatus()** không được đăng ký do auto-configuration này. Nếu class đạt nhưng method condition thất bại, chỉ bean method này bị bỏ qua; trong một cấu hình lớn, các method khác có điều kiện khác vẫn có thể được xử lý.

### 5.8. Đăng ký auto-configuration ứng viên

Tạo đúng tệp:

~~~text
feature-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
com.example.condition.autoconfigure.FeatureAutoConfiguration
~~~

Một dòng là một tên class đầy đủ, không có dấu phẩy hoặc **.class**. Ứng dụng tiêu thụ không cần import class này vào source; Boot đọc tài nguyên imports từ classpath.

## 6. Viết kiểm thử cho từng điều kiện và từng nhánh sai

**ApplicationContextRunner** giúp chạy context nhỏ với từng tổ hợp property, classloader và user-defined bean. Test trong cùng project có **ObjectMapper** trên classpath nhờ starter JSON; riêng test classpath negative sẽ dùng **FilteredClassLoader** che package Jackson.

Tệp **feature-autoconfigure/src/test/java/com/example/condition/autoconfigure/FeatureAutoConfigurationTests.java**:

~~~java
package com.example.condition.autoconfigure;

import com.example.condition.api.FeatureStatus;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class FeatureAutoConfigurationTests {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(
                    FeatureAutoConfiguration.class
                )
            );

    @Test
    void createsDefaultWhenAllConditionsMatch() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(FeatureStatus.class);
            assertThat(context.getBean(FeatureStatus.class).label())
                .isEqualTo("standard");
        });
    }

    @Test
    void disabledFeaturePreventsDefaultBean() {
        runner.withPropertyValues(
            "demo.feature.enabled=false"
        ).run(context -> {
            assertThat(context).doesNotHaveBean(FeatureStatus.class);
        });
    }

    @Test
    void nonStandardModePreventsDefaultBean() {
        runner.withPropertyValues(
            "demo.feature.mode=legacy"
        ).run(context -> {
            assertThat(context).doesNotHaveBean(FeatureStatus.class);
        });
    }

    @Test
    void twoFailedPropertiesStillPreventDefaultBean() {
        runner.withPropertyValues(
            "demo.feature.enabled=false",
            "demo.feature.mode=legacy"
        ).run(context -> {
            assertThat(context).doesNotHaveBean(FeatureStatus.class);
        });
    }

    @Test
    void missingJacksonPreventsDefaultBean() {
        runner.withClassLoader(
            new FilteredClassLoader("com.fasterxml.jackson.databind")
        ).run(context -> {
            assertThat(context).doesNotHaveBean(FeatureStatus.class);
        });
    }

    @Test
    void userBeanWinsInsteadOfDefaultBean() {
        runner.withUserConfiguration(UserFeatureConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(FeatureStatus.class);
                assertThat(context.getBean(FeatureStatus.class).label())
                    .isEqualTo("custom");
                assertThat(context.containsBean("featureStatus"))
                    .isFalse();
                assertThat(context.containsBean("customFeatureStatus"))
                    .isTrue();
            });
    }

    @Test
    void explicitMatchingPropertiesCreateDefaultBean() {
        runner.withPropertyValues(
            "demo.feature.enabled=true",
            "demo.feature.mode=standard"
        ).run(context -> {
            assertThat(context).hasSingleBean(FeatureStatus.class);
        });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserFeatureConfiguration {

        @Bean
        FeatureStatus customFeatureStatus() {
            return new FeatureStatus("custom");
        }
    }
}
~~~

### 6.1. Đọc kết quả test theo logic AND

| Test | Điều kiện bị thay đổi | Kết quả mong đợi |
| --- | --- | --- |
| **createsDefaultWhenAllConditionsMatch** | Không; các property thiếu được xem là match | Có một FeatureStatus mặc định. |
| **disabledFeaturePreventsDefaultBean** | E = false | Không có bean mặc định. |
| **nonStandardModePreventsDefaultBean** | M = false | Không có bean mặc định. |
| **twoFailedPropertiesStillPreventDefaultBean** | E = false, M = false | Không có bean mặc định. |
| **missingJacksonPreventsDefaultBean** | C = false vì class được che | Không có bean mặc định. |
| **userBeanWinsInsteadOfDefaultBean** | B = false vì có bean người dùng | Context có đúng bean custom, không tạo default. |
| **explicitMatchingPropertiesCreateDefaultBean** | E = true, M = true | Có bean mặc định. |

Test **userBeanWinsInsteadOfDefaultBean** đặc biệt quan trọng: kết luận đúng là **“không có bean mặc định”**, chứ không phải **“context không có FeatureStatus”**. Vì vậy assertion xác nhận **hasSingleBean**, giá trị **custom**, tên bean **customFeatureStatus** và việc **featureStatus** không tồn tại.

### 6.2. Chạy test

Từ thư mục gốc:

~~~bash
gradle :feature-autoconfigure:test
~~~

Nếu project có Gradle Wrapper:

~~~bash
./gradlew :feature-autoconfigure:test
~~~

Trên Windows PowerShell có thể dùng **.\gradlew.bat :feature-autoconfigure:test**. Gradle hiển thị task test thành công hoặc báo assertion/lỗi khởi tạo context; không có một bản stdout cố định cho mọi môi trường. Kiểm thử thành công là bằng chứng cho từng trường hợp trong bảng, không phải bằng chứng tất cả dependency trên production classpath giống test.

### 6.3. Bằng chứng test bao phủ và giới hạn

Test này trực tiếp đưa **FeatureAutoConfiguration** vào runner qua **AutoConfigurations.of**. Nó kiểm tra **các condition của class/method**. Nó **chưa chứng minh** JAR phát hành chứa đúng **AutoConfiguration.imports** hoặc consumer khám phá cấu hình khi chỉ thêm dependency. Vì thế cần chạy ứng dụng ở phần tiếp theo.

Ngoài ra, **FilteredClassLoader** mô phỏng việc class không thể được tìm thấy bởi classloader của context test. Điều này phù hợp để test **@ConditionalOnClass**, nhưng không có nghĩa tất cả tình huống xung đột binary version, missing method hoặc packaging đều đã được kiểm chứng.

## 7. Ứng dụng tiêu thụ: quan sát phép AND trong runtime thật

Tệp **sample-app/src/main/java/com/example/consumer/SampleApplication.java**:

~~~java
package com.example.consumer;

import com.example.condition.api.FeatureStatus;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SampleApplication {

    public static void main(String[] args) {
        SpringApplication.run(SampleApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectFeature(ApplicationContext context) {
        return args -> {
            var beans = context.getBeansOfType(FeatureStatus.class);
            System.out.println(
                "FeatureStatus beans: " + beans.size()
            );
            beans.values().forEach(bean ->
                System.out.println(
                    "FeatureStatus label: " + bean.label()
                )
            );
        };
    }
}
~~~

Chú ý package **com.example.consumer** nằm ngoài **com.example.condition.autoconfigure**. Component scanning mặc định của **@SpringBootApplication** không quét package auto-configuration. Khi bean xuất hiện, nó đến từ ứng viên đã đăng ký trong resource imports, không phải vì package ứng dụng vô tình quét class cấu hình.

### 7.1. Kịch bản mặc định

Chạy:

~~~bash
gradle :sample-app:bootRun
~~~

Hai dòng do ApplicationRunner in ra trong cấu hình mẫu:

~~~text
FeatureStatus beans: 1
FeatureStatus label: standard
~~~

Đây là **hai dòng riêng do code in**, không phải toàn bộ log Gradle/Spring Boot. Vì có Jackson trên classpath, **enabled** và **mode** bị thiếu nhưng được xem là match, và chưa có bean người dùng, nên đủ điều kiện tạo FeatureStatus mặc định.

### 7.2. Tắt tính năng bằng property

Chạy:

~~~bash
gradle :sample-app:bootRun --args='--demo.feature.enabled=false'
~~~

Dòng kiểm tra dự kiến:

~~~text
FeatureStatus beans: 0
~~~

Lý do là condition cấp class trên **enabled** không match. Điều kiện **mode** có thể vẫn hợp lệ nhưng không làm thay đổi kết quả tổng AND.

### 7.3. Đổi mode sang giá trị không phù hợp

Chạy:

~~~bash
gradle :sample-app:bootRun --args='--demo.feature.mode=legacy'
~~~

Dòng dự kiến:

~~~text
FeatureStatus beans: 0
~~~

Ở đây class auto-configuration vẫn có thể hợp lệ vì ObjectMapper hiện diện và enabled không bị tắt, nhưng **điều kiện tại phương thức @Bean** không match.

### 7.4. Cố tình làm hai điều kiện false

Chạy:

~~~bash
gradle :sample-app:bootRun --args='--demo.feature.enabled=false --demo.feature.mode=legacy'
~~~

Vẫn nhận:

~~~text
FeatureStatus beans: 0
~~~

Không cần phân biệt “hai false” hay “một false” khi tính kết quả phép AND; chỉ cần một điều kiện không thỏa mãn là đủ ngăn bean mặc định.

### 7.5. Kiểm tra classpath condition bằng dependency

Trong một nhánh thực hành riêng, bỏ dòng:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-json'
~~~

khỏi **sample-app/build.gradle** rồi kiểm tra:

~~~bash
gradle :sample-app:dependencies --configuration runtimeClasspath
gradle :sample-app:dependencyInsight --configuration runtimeClasspath --dependency jackson-databind
~~~

Nếu không có dependency khác mang **com.fasterxml.jackson.databind.ObjectMapper** vào runtime, classpath condition sẽ không match và FeatureStatus mặc định không được tạo. **Không mặc định rằng bỏ một dòng chắc chắn làm Jackson biến mất**: Gradle có thể vẫn resolve Jackson qua dependency khác, và lúc đó kết quả phải được giải thích theo classpath thực tế.

Khôi phục dòng dependency sau thí nghiệm.

## 8. Bản chất của AND khi điều kiện của class và method khác nhau

Xét hai phương thức:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "demo",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
class MultiBeanAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "demo",
        name = "alpha",
        havingValue = "true"
    )
    AlphaBean alphaBean() {
        return new AlphaBean();
    }

    @Bean
    @ConditionalOnProperty(
        prefix = "demo",
        name = "beta",
        havingValue = "true"
    )
    BetaBean betaBean() {
        return new BetaBean();
    }
}
~~~

**Đây là một đoạn ví dụ về cấu trúc điều kiện, không phải file Java đầy đủ**; class **AlphaBean/BetaBean** chưa được định nghĩa.

Khi **demo.enabled=false**, **cả hai** bean methods bị chặn vì class không được áp dụng. Khi enabled=true, việc tạo **AlphaBean** và **BetaBean** có thể khác nhau: mỗi method có condition riêng.

Bảng:

| demo.enabled | demo.alpha | demo.beta | AlphaBean mặc định | BetaBean mặc định |
| --- | --- | --- | --- | --- |
| false | true | true | Không | Không |
| true | true | false | Có | Không |
| true | false | true | Không | Có |
| true | true | true | Có | Có |

Điều kiện cấp class tác động tới **toàn bộ class configuration**, trong khi điều kiện method chỉ quyết định **bean method đó**. Nếu cả hai bean phải cùng có mặt hoặc cùng vắng mặt vì một feature chung, đặt condition chia sẻ ở cấp class hoặc một nested configuration phù hợp, rồi giữ condition riêng cho các biến thể cần thiết.

## 9. Điều kiện nhiều thành phần không tự động thành OR

**Sai lầm phổ biến:** “Đặt hai annotation @ConditionalOnProperty với hai tiêu chí khác nhau nghĩa là một trong hai đúng là được”. Cơ chế mặc định của nhiều điều kiện cùng áp dụng là **AND**, không phải OR.

Nếu yêu cầu nghiệp vụ thực sự là “**mode=standard HOẶC mode=legacy**”, phải biểu diễn **OR** một cách rõ ràng. Có những cách đơn giản:

1. **Thiết kế lại property**: chỉ kiểm tra tính năng enabled ở annotation, còn logic mode được xử lý bằng một **@ConfigurationProperties** có validation phù hợp trong bean factory hoặc service; dùng khi mục tiêu không thực sự là chọn class cấu hình.
2. **Dùng condition tổng hợp** khi cần lựa chọn auto-configuration theo logic OR, ví dụ **AnyNestedCondition** trong Spring Boot.
3. **Tách thành các cấu hình riêng** với condition độc lập nếu muốn có các bean khác nhau cho mỗi mode. Phải cân nhắc trường hợp nhiều mode/điều kiện cùng match dẫn tới bean trùng.

### 9.1. Ví dụ AnyNestedCondition dùng khi thật sự cần OR

Đoạn dưới minh họa một condition tổng hợp cho property **demo.feature.mode**. Đây là **class Java độc lập nếu đặt trong cùng package có import tương ứng**, nhưng khi dùng trong ứng dụng phải thêm **@Conditional(OnStandardOrLegacy.class)** lên class hoặc method muốn bảo vệ:

~~~java
package com.example.condition.autoconfigure;

import org.springframework.boot.autoconfigure.condition.AnyNestedCondition;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.ConfigurationCondition.ConfigurationPhase;

final class OnStandardOrLegacy extends AnyNestedCondition {

    OnStandardOrLegacy() {
        super(ConfigurationPhase.REGISTER_BEAN);
    }

    @ConditionalOnProperty(
        prefix = "demo.feature",
        name = "mode",
        havingValue = "standard"
    )
    static class Standard {
    }

    @ConditionalOnProperty(
        prefix = "demo.feature",
        name = "mode",
        havingValue = "legacy"
    )
    static class Legacy {
    }
}
~~~

**AnyNestedCondition** cho kết quả match nếu **ít nhất một** nested condition match. Trong code này: **mode=standard OR mode=legacy**. Đây là condition **tùy chọn nâng cao**, không được sử dụng trong project chạy ở phần 5–7.

**Chú ý:** Do hai nested annotation ở trên **không** có **matchIfMissing=true**, property mode bị thiếu sẽ **không** match với cả hai. Nếu yêu cầu mặc định bật khi mode thiếu, phải thiết kế rõ nhánh mặc định; đừng âm thầm giả định logic OR có cùng hành vi với ví dụ AND trước đó.

**ConfigurationPhase.REGISTER_BEAN** ở đây phù hợp với việc dùng condition ở cấp bean registration; khi condition áp dụng tại cấp cấu hình hoặc có các loại condition khác, cần xem lại phase thích hợp theo API và thời điểm dữ liệu cần thiết có sẵn.

### 9.2. AllNestedCondition và NoneNestedCondition

Spring Boot cũng có các tiện ích condition tổng hợp:

- **AllNestedConditions**: match khi **tất cả** nested condition match, tức AND có chủ đích.
- **AnyNestedCondition**: match khi **ít nhất một** nested condition match, tức OR.
- **NoneNestedConditions**: match khi **không** nested condition nào match, tương ứng NOT của phép OR.

Không cần dùng AllNestedConditions chỉ để viết **@ConditionalOnClass** và **@ConditionalOnProperty** thông thường trên cùng class: bản thân việc ghép condition ở cùng vị trí đã tạo semantics AND. Condition tổng hợp hữu ích khi yêu cầu phức tạp, cần tái sử dụng hoặc không thể biểu đạt dễ đọc bằng các annotation chuẩn.

### 9.3. NOT không có nghĩa “thiếu property”

Ví dụ một feature “chỉ khi không có bean X” thường dùng **@ConditionalOnMissingBean(X.class)**; nhưng điều đó là phủ định của **sự tồn tại bean phù hợp**, không phải phủ định của mọi condition khác. Tương tự, **@ConditionalOnMissingClass** là sự vắng mặt của class, chứ không phải phủ định của mọi property hoặc môi trường.

Cần xác định chính xác đối tượng của phép NOT, không dùng tên annotation như một công thức chung cho mọi trường hợp.

## 10. Thứ tự xử lý bean và ý nghĩa của @ConditionalOnMissingBean

Về logic, **@ConditionalOnMissingBean(FeatureStatus.class)** thêm một điều kiện nữa vào AND. Nhưng đây là điều kiện đặc biệt: nó đánh giá các **bean definition đã được container xử lý đến thời điểm đó**.

Trong một thư viện auto-configuration, điều kiện này thường được dùng để **nhường quyền cho cấu hình ứng dụng**. Spring Boot thiết kế auto-configuration để được áp dụng sau khi các bean definitions do người dùng khai báo có cơ hội được xem xét theo cơ chế thông thường. Vì vậy custom bean được nhìn thấy và auto-config không tạo default thứ hai.

Tuy nhiên, không nên kết luận rằng **@ConditionalOnMissingBean** biết trước mọi bean sẽ được đăng ký ở bất kỳ thời điểm nào trong tương lai. Khi nhiều auto-configuration phụ thuộc nhau, thứ tự giữa chúng có thể ảnh hưởng kết quả.

### 10.1. Không dùng thứ tự dòng imports để giải quyết mọi xung đột

Nếu thư viện A và B đều cần dựa vào sự hiện diện của bean do auto-configuration khác tạo, hãy cân nhắc:

- Đặt **@AutoConfiguration(after = OtherAutoConfiguration.class)** hoặc **before** khi có phụ thuộc ordering rõ ràng;
- Test các tổ hợp có/không có thư viện liên quan;
- Hạn chế bean type quá chung khiến nhiều autoconfiguration vô tình back off lẫn nhau.

Ordering của auto-configuration nói về **thứ tự xử lý bean definitions do các auto-configuration đăng ký**, không trực tiếp quy định thứ tự khởi tạo instance của mọi bean trong container. Phụ thuộc lúc khởi tạo cần được thiết kế bằng dependency injection và cơ chế Spring phù hợp.

### 10.2. Điều kiện false không đồng nghĩa với “ứng dụng không thể có bean”

Ví dụ, nếu enabled=false nhưng ứng dụng **tự đăng ký FeatureStatus** bằng một @Configuration khác, context vẫn có bean tùy chỉnh ấy. Condition chỉ điều khiển **cấu hình/bean mà nó được gắn lên**. Đây là lý do không nên diễn giải **@ConditionalOnProperty** thành một công tắc global xóa mọi bean cùng type.

Khi xây tính năng bật/tắt cho production, cần làm rõ: tắt **default auto-config**, tắt **mọi hành vi của service**, hay chặn **endpoint**? Chúng có thể là những yêu cầu khác nhau.

## 11. Chẩn đoán tổ hợp điều kiện bằng Condition Evaluation Report

Khi một bean không được tạo, việc thêm ngẫu nhiên **@Bean** hoặc đổi dependency mà chưa có bằng chứng dễ gây lỗi mới. Hãy đọc lý do các condition match hoặc không match.

### 11.1. Bật báo cáo khi chạy ứng dụng

~~~bash
gradle :sample-app:bootRun --args='--debug'
~~~

Trong ứng dụng có condition evaluation report, hãy tìm **FeatureAutoConfiguration** và thông tin liên quan, ví dụ:

- Class điều kiện có hiện diện không?
- Thuộc tính **demo.feature.enabled** có đúng giá trị hoặc đang thiếu key với **matchIfMissing=true** không?
- Thuộc tính **demo.feature.mode** có match **standard** không?
- Đã có bean **FeatureStatus** do ứng dụng cung cấp chưa?

Nội dung, cấu trúc nhóm Positive/Negative Matches và thứ tự ghi log phụ thuộc Spring Boot version và tình trạng runtime. Không viết một đoạn report giả định rồi coi nó là stdout chính xác trên mọi môi trường.

### 11.2. Phân loại nguyên nhân theo bảng

| Hiện tượng | Điểm kiểm tra trước | Nguyên nhân thường gặp |
| --- | --- | --- |
| Toàn bộ auto-config bị bỏ qua | Class-level conditions/exclude | Thiếu ObjectMapper, enabled=false hoặc exclude. |
| Auto-config phù hợp nhưng bean method không được áp dụng | Method-level conditions | mode không phải standard hoặc đã có bean. |
| Context có một bean custom thay vì default | @ConditionalOnMissingBean | Cơ chế back off hoạt động đúng. |
| Test tạo bean nhưng production không tạo | Khác biệt dependency/property/profile | Test classpath có Jackson nhưng runtime không có, hoặc profile config khác. |
| Có hai bean cùng type | Thứ tự đăng ký/điều kiện/kiểu bean | Không nên chữa bằng global overriding khi chưa xác định nguồn. |
| Một condition vẫn match dù property không khai báo | matchIfMissing | Annotation cho phép key vắng mặt. |
| Condition property match khi giá trị không phải true | havingValue mặc định | Mặc định chỉ yêu cầu giá trị không bằng false, không yêu cầu true tuyệt đối. |

### 11.3. Dùng đúng configuration khi kiểm tra classpath

Với Gradle:

~~~bash
gradle :sample-app:dependencies --configuration runtimeClasspath
gradle :sample-app:dependencyInsight --configuration runtimeClasspath --dependency jackson-databind
~~~

Đừng dùng **testRuntimeClasspath** làm bằng chứng rằng ứng dụng production có class tương ứng. Một class có mặt trong test nhưng không có trong bản deploy là nguyên nhân rất thực tế khiến classpath condition cho kết quả khác nhau.

## 12. Khi nhiều điều kiện có thể không cần kiểm tra tất cả

Trong logic thuần túy, phép AND có thể “short-circuit” khi thấy một false. Nhưng Spring thực thi condition qua nhiều pha xử lý metadata, classpath, bean definition và context. Vì vậy:

- Không nên dựa vào thứ tự các annotation để dự đoán chính xác log nào xuất hiện trước.
- Không nên sử dụng side effect trong condition để phục vụ logic nghiệp vụ.
- Điều kiện tự viết phải có hành vi có thể dự đoán, không làm thay đổi context một cách tùy tiện.
- Condition classpath thường có thể được kiểm tra sớm hơn bean-related conditions, nhưng không nên khẳng định mọi condition đều được đánh giá trong một vòng lặp cố định.
- Một điều kiện không match có thể ngăn cả class hoặc chỉ một method; cần biết annotation được đặt **ở cấp nào**.

Cách kiểm chứng chuẩn là **assert trạng thái context cuối cùng** và **đọc condition report**, không suy luận từ việc một câu lệnh print nằm ở cuối một điều kiện tùy chỉnh.

## 13. Những lỗi thiết kế thường gặp

**Lỗi 1 — Dùng hai annotation như OR:** Muốn “một trong hai property đúng” nhưng lại đặt nhiều condition cùng vị trí. Kết quả thực tế là AND; hãy biểu diễn OR rõ ràng hoặc đổi mô hình cấu hình.

**Lỗi 2 — Quên matchIfMissing:** Muốn bật mặc định nhưng khai báo **@ConditionalOnProperty(havingValue="true")** mà không có **matchIfMissing=true**. Khi key vắng mặt, bean không được tạo. Viết test cho trường hợp không có key.

**Lỗi 3 — Đọc sai havingValue mặc định:** Dùng annotation không có **havingValue** rồi giả định chỉ true mới match. Theo semantics Boot, giá trị hiện diện khác false có thể được coi là match; nếu cần boolean rõ ràng, khai báo **havingValue="true"**.

**Lỗi 4 — Đặt điều kiện classpath sai chỗ:** Method **@Bean** có return type thuộc dependency tùy chọn nhưng chỉ được bảo vệ bằng điều kiện đặt trên chính method. Spring có thể phải introspect signature trước. Nên cô lập nhóm method ấy trong configuration class có **@ConditionalOnClass** ở cấp class.

**Lỗi 5 — Kiểm tra bean có/không mà không phân biệt default và custom:** Context chứa một FeatureStatus có thể là bean của người dùng. Hãy xác minh số lượng, tên, nguồn hoặc hành vi của bean để biết auto-config có thực sự tạo bản mặc định không.

**Lỗi 6 — Chỉ test trường hợp all true:** Khi có bốn điều kiện, chỉ test đường thành công là thiếu. Cần ít nhất một negative test cho từng điều kiện độc lập và một test chứng minh back off.

**Lỗi 7 — Áp @ConditionalOnMissingBean ở nơi phụ thuộc thời điểm đăng ký:** Trong cấu hình thông thường, điều kiện bean nên được dùng cẩn thận trong auto-configuration vì phụ thuộc vào các bean definitions đã được xử lý. Không đặt lộn xộn vào app configuration rồi mong nhìn thấy bean được tạo sau đó.

**Lỗi 8 — Dùng @ConditionalOnProperty để kiểm tra collection:** Một key dạng list/indexed property có thể không match như mong đợi. Không biến annotation này thành công cụ validation cho object cấu hình phức tạp.

**Lỗi 9 — Nhầm ứng viên với bean:** Class có mặt trong **AutoConfiguration.imports** chỉ là ứng viên. Nó vẫn có thể bị exclude, không match class-level condition hoặc chỉ có một số bean method được phép.

**Lỗi 10 — Coi kết quả test runner là discovery test:** **AutoConfigurations.of** chỉ định class trực tiếp. Để xác nhận ứng dụng ngoài tự khám phá auto-configuration, cần thêm bài test/ứng dụng tiêu thụ và kiểm tra JAR imports.

## 14. Bài tập thực hành có thể kiểm chứng

### Bài 1 — Dự đoán tổ hợp trước khi chạy

Với cấu hình mẫu, đánh giá kết quả bean mặc định cho:

| enabled | mode | Có ObjectMapper | Có custom FeatureStatus | Kết quả |
| --- | --- | --- | --- | --- |
| thiếu | thiếu | Có | Không | Có mặc định |
| true | standard | Có | Không | Có mặc định |
| false | standard | Có | Không | Không có mặc định |
| true | legacy | Có | Không | Không có mặc định |
| true | standard | Không | Không | Không có mặc định |
| true | standard | Có | Có | Chỉ bean custom |
| false | legacy | Không | Có | Không có mặc định; bean custom có thể vẫn có |

Giải thích vì sao hàng cuối **không thể** được rút gọn thành “không có bean nào trong context”.

### Bài 2 — Thêm một thuộc tính bắt buộc

Thêm yêu cầu **demo.feature.approved=true** vào **@ConditionalOnProperty** cấp class hoặc tạo một annotation condition riêng. Quyết định liệu key bị thiếu nên match hay không. Bổ sung ít nhất ba test: approved=true, approved=false, approved không tồn tại.

Nếu có hai property phải cùng đúng và cùng dùng **havingValue="true"**, cân nhắc **name={"enabled","approved"}**, nhưng phải nhớ **matchIfMissing** lúc này được áp dụng theo policy chung của annotation.

### Bài 3 — So sánh cấp class và cấp method

Thêm bean **FeatureAuditMarker** không có điều kiện mode nhưng vẫn nằm trong FeatureAutoConfiguration. Khi mode=legacy, hãy dự đoán bean marker có thể được tạo hay không nếu class-level conditions match. Dùng test để phân biệt tác động của class-level condition và method-level condition.

### Bài 4 — Tự thiết kế OR có kiểm thử

Cho phép mode **standard** hoặc **legacy**. Viết bảng chân trị rồi dùng **AnyNestedCondition** hoặc thiết kế service phù hợp. Kiểm tra cả trường hợp mode không tồn tại và mode=unsupported để không vô tình thay đổi behavior mặc định.

### Bài 5 — Phân biệt default bean và bean người dùng

Khi enabled=true và mode=standard, đăng ký custom FeatureStatus. Kiểm tra một bean custom và không có bean mặc định. Sau đó thử enabled=false nhưng vẫn giữ custom bean; giải thích vì sao auto-config không có quyền xóa bean được ứng dụng tạo.

### Bài 6 — Chẩn đoán bằng công cụ

Chạy **--debug** với một tổ hợp property không match. Đọc condition report và ghi lại class-level hoặc method-level condition nào dẫn tới việc bỏ qua. Kiểm tra runtimeClasspath để xác nhận ObjectMapper có đúng mặt hay không. Nêu kết luận dựa trên kết quả thực tế, không sao chép một report giả lập.

## 15. Checklist trước khi coi bài học hoàn thành

- [ ] Phát biểu được nguyên tắc **nhiều điều kiện cùng gắn lên một thành phần = tất cả phải thỏa mãn**.
- [ ] Giải thích được phép AND giữa điều kiện trên auto-configuration class và trên từng @Bean method.
- [ ] Vẽ được bảng chân trị cho **C ∧ E ∧ M ∧ B**, chỉ tạo default bean khi tất cả đúng.
- [ ] Hiểu sự khác nhau giữa **havingValue** và **matchIfMissing**.
- [ ] Biết **nhiều name trong một @ConditionalOnProperty cũng phải đồng thời match**.
- [ ] Biết **@ConditionalOnMissingBean** nhường quyền cho bean người dùng chứ không xóa bean người dùng.
- [ ] Biết không dùng nhiều annotation điều kiện như một phép OR không khai báo.
- [ ] Biết khi nào có thể dùng **AnyNestedCondition**, **AllNestedConditions**, **NoneNestedConditions**.
- [ ] Đã viết và chạy được ví dụ auto-configuration có nhiều điều kiện ở class/method.
- [ ] Đã chạy negative test cho từng yếu tố C, E, M và B.
- [ ] Đã quan sát được ứng dụng tiêu thụ chỉ nhận default bean khi các điều kiện đều match.
- [ ] Đã biết dùng **Condition Evaluation Report** và **dependencyInsight** để điều tra kết quả khác dự đoán.
- [ ] Không nhầm kết quả “không tạo default” với “context tuyệt đối không có bean cùng kiểu”.

## Kết luận

Quy tắc dễ nhớ nhất khi đọc Spring Boot auto-configuration là: **tất cả điều kiện áp dụng cho một class hoặc một bean method phải cho phép thành phần đó được xử lý**. Nếu điều kiện cấp class không thỏa mãn, những bean methods của class không được áp dụng. Nếu class hợp lệ nhưng một điều kiện tại method không thỏa mãn, method ấy không tạo bean.

Với bài tập **FeatureStatus**, công thức là **C ∧ E ∧ M ∧ B**: classpath đúng, tính năng được bật, mode phù hợp và chưa có bean cùng kiểu. Từ đây, người học có thể thiết kế cấu hình mặc định an toàn, viết test cho từng nhánh false, hiểu cách bean do ứng dụng khai báo được ưu tiên và chủ động dùng condition tổng hợp khi bài toán thực sự yêu cầu OR/NOT thay vì nhầm lẫn chúng với AND.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Developing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [ConditionalOnProperty — Spring Boot API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [AnyNestedCondition — Spring Boot API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/AnyNestedCondition.html)
