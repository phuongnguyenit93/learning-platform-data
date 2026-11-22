# `@ConditionalOnJava` và khoảng phiên bản JVM được chấp nhận

## 1. Mục đích: chọn bean theo JVM đang chạy

Trong Spring Boot Auto Configuration, đôi khi một phần tích hợp chỉ phù hợp khi ứng dụng chạy bằng một phiên bản Java nhất định. Ví dụ:

- Một adapter tối ưu được thiết kế cho **Java 21 trở lên**.
- Một adapter tương thích dành cho **Java trước 21**.
- Một nhánh cấu hình chỉ muốn kích hoạt khi JVM nằm trong một khoảng phiên bản đã kiểm chứng.

`@ConditionalOnJava` của Spring Boot cho phép Spring quyết định có đăng ký một class cấu hình hoặc một phương thức `@Bean` dựa trên **phiên bản JVM thực sự đang chạy ứng dụng**.

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnJava;
import org.springframework.boot.system.JavaVersion;

@Bean
@ConditionalOnJava(JavaVersion.TWENTY_ONE)
MyAdapter java21Adapter() {
    return new MyAdapter();
}
~~~

Đây là **đoạn mã minh họa**: `MyAdapter` và class chứa phương thức `@Bean` phải do dự án định nghĩa. Với cấu hình trên, định nghĩa bean `java21Adapter` chỉ được xét để đăng ký nếu JVM là Java 21 hoặc mới hơn. Nếu ứng dụng chạy trên Java 17 hay Java 20, phương thức bean đó không được đăng ký.

Hai điểm cần nhớ ngay từ đầu:

1. Annotation kiểm tra **JVM runtime**, không kiểm tra số phiên bản trong `build.gradle`, `pom.xml`, lựa chọn `--release` của trình biên dịch hay một property trong `application.yml`.
2. Annotation **không nâng cấp Java**, không biến bytecode Java 21 thành bytecode Java 17 và không sửa được lỗi khởi động do phiên bản JVM không tương thích.

Trong phạm vi Spring Boot **3.3**, Java 17 là mức tối thiểu để chạy framework. Vì vậy tất cả JVM được hỗ trợ bởi nhánh Spring Boot này đều đáp ứng điều kiện `JavaVersion.SEVENTEEN` trở lên; điều kiện có giá trị thực tế nhất khi so sánh các ngưỡng cao hơn.

## 2. Cú pháp, thuộc tính `value` và `range`

API:

~~~java
org.springframework.boot.autoconfigure.condition.ConditionalOnJava
~~~

Annotation dùng được ở **class** (`@Configuration` hoặc `@AutoConfiguration`) và **method** (`@Bean`). Nó có hai thuộc tính:

| Thuộc tính | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `value` | `org.springframework.boot.system.JavaVersion` | Phiên bản Java làm mốc; **bắt buộc** khai báo. |
| `range` | `ConditionalOnJava.Range` | Phía của mốc được chấp nhận; mặc định là `EQUAL_OR_NEWER`. |

`Range` có đúng **hai** hằng cần dùng trong Spring Boot 3.3:

| `range` | Phép so sánh trên Java feature version | Ngữ nghĩa biên |
| --- | --- | --- |
| `Range.EQUAL_OR_NEWER` | JVM hiện tại **≥** `value` | Bao gồm phiên bản ở mốc; không có giới hạn trên. |
| `Range.OLDER_THAN` | JVM hiện tại **<** `value` | **Không** bao gồm phiên bản ở mốc; không có giới hạn dưới trong chính annotation. |

Ví dụ:

~~~java
@ConditionalOnJava(JavaVersion.TWENTY_ONE)
~~~

Tương đương hoàn toàn với:

~~~java
@ConditionalOnJava(
    value = JavaVersion.TWENTY_ONE,
    range = ConditionalOnJava.Range.EQUAL_OR_NEWER
)
~~~

Cả hai chỉ khớp khi **Java ≥ 21**.

Ngược lại:

~~~java
@ConditionalOnJava(
    value = JavaVersion.TWENTY_ONE,
    range = ConditionalOnJava.Range.OLDER_THAN
)
~~~

Chỉ khớp khi **Java < 21**. Trên Spring Boot 3.3, nhóm JVM khả dụng điển hình cho điều kiện này bắt đầu từ Java 17 vì framework không hỗ trợ runtime thấp hơn.

**Dễ nhầm:** tên `OLDER_THAN` là so sánh **nhỏ hơn nghiêm ngặt**, không phải nhỏ hơn hoặc bằng. JVM Java 21 **không** khớp `OLDER_THAN(TWENTY_ONE)`.

## 3. Bảng đối chiếu JVM và khoảng phiên bản

Giả sử phiên bản trong bảng là **JVM chạy ứng dụng**, không phải JVM dùng để biên dịch:

| JVM đang chạy | `≥ 17` (mặc định `SEVENTEEN`) | `≥ 21` (mặc định `TWENTY_ONE`) | `< 21` (`OLDER_THAN TWENTY_ONE`) | `< 23` (`OLDER_THAN TWENTY_THREE`) |
| --- | :---: | :---: | :---: | :---: |
| Java 17 | Khớp | Không | Khớp | Khớp |
| Java 18 | Khớp | Không | Khớp | Khớp |
| Java 19 | Khớp | Không | Khớp | Khớp |
| Java 20 | Khớp | Không | Khớp | Khớp |
| Java 21 | Khớp | Khớp | Không | Khớp |
| Java 22 | Khớp | Khớp | Không | Khớp |
| Java 23 | Khớp | Khớp | Không | Không |

Trong Spring Boot 3.3, `JavaVersion` định nghĩa các mốc `SEVENTEEN`, `EIGHTEEN`, `NINETEEN`, `TWENTY`, `TWENTY_ONE`, `TWENTY_TWO` và `TWENTY_THREE`. Các hằng enum có sẵn phụ thuộc phiên bản của **Spring Boot library**, không phụ thuộc việc máy lập trình viên có cài JDK đó hay không.

Khi nói “chấp nhận Java 17 đến Java 20”, cần viết bất đẳng thức cho rõ: **17 ≤ Java < 21**. Trong một ứng dụng Spring Boot 3.3, yêu cầu dưới Java 17 đã bị framework loại trừ, nên một điều kiện `OLDER_THAN(TWENTY_ONE)` là đủ để tách nhánh **17–20**. Tuy nhiên, bản thân annotation này chỉ biểu diễn **Java < 21**; ràng buộc **Java ≥ 17** đến từ yêu cầu runtime của Spring Boot 3.3, không phải từ thuộc tính thứ hai trong annotation.

## 4. Phạm vi từ một phía so với khoảng có cả hai đầu

### 4.1. Mốc dưới: từ Java 21 trở lên

~~~java
@Bean
@ConditionalOnJava(JavaVersion.TWENTY_ONE)
RuntimeAdapter modernAdapter() {
    return new ModernAdapter();
}
~~~

Với Java 21, Java 22, Java 23: bean này có thể được đăng ký. Với Java 17–20: không đăng ký. Các kiểu `RuntimeAdapter`/`ModernAdapter` trong trích đoạn cần được dự án định nghĩa.

### 4.2. Mốc trên: trước Java 21

~~~java
@Bean
@ConditionalOnJava(
    value = JavaVersion.TWENTY_ONE,
    range = ConditionalOnJava.Range.OLDER_THAN
)
RuntimeAdapter legacyAdapter() {
    return new LegacyAdapter();
}
~~~

Với Java 17–20: bean có thể được đăng ký. Với Java 21 trở lên: không đăng ký.

Có thể dùng cặp điều kiện đối nhau này để đăng ký **một trong hai** adapter theo JVM runtime, miễn là hai nhánh đã được định nghĩa, triển khai và đóng gói tương thích với JVM mà chúng phải chạy.

### 4.3. Khoảng hai đầu, ví dụ `21 ≤ Java < 23`

**Không có** thuộc tính `min`, `max`, `between` hay `EQUAL` trong `@ConditionalOnJava` của Spring Boot 3.3. Mỗi lần sử dụng annotation chỉ mô tả **một ngưỡng** với một `range`; annotation không được khai báo là repeatable để gắn trực tiếp hai lần lên cùng một phần tử rồi ghép bằng AND.

Khi thật sự cần khoảng **21 ≤ Java < 23** (chỉ Java 21 và 22), một giải pháp rõ ràng là viết `Condition` riêng, sử dụng API phiên bản Java runtime:

File `src/main/java/com/example/demo/Java21To22Condition.java`:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class Java21To22Condition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    ) {
        int feature = Runtime.version().feature();
        return feature >= 21 && feature < 23;
    }
}
~~~

Sau đó đặt lên class cấu hình hoặc phương thức bean:

~~~java
@Conditional(Java21To22Condition.class)
@Bean
AdvancedAdapter advancedAdapter() {
    return new AdvancedAdapter();
}
~~~

Đoạn dùng `AdvancedAdapter` là **minh họa tích hợp** vì lớp nghiệp vụ phải do dự án định nghĩa. Class `Java21To22Condition` ở trên là một class Java hoàn chỉnh; nó đòi hỏi Spring Context trên compile classpath. `Runtime.version().feature()` là API từ Java 9, phù hợp cho baseline Java 17 của Spring Boot 3.3.

Điều kiện custom trả về `true` với runtime 21 hoặc 22, và `false` với 17–20, 23 trở lên. Khi cần khoảng khác, dùng bất đẳng thức có biên được kiểm soát và test cả các giá trị sát mốc.

**Không nên** cố đặt hai `@ConditionalOnJava` trên cùng method/class như hai annotation giống hệt nhau; phiên bản API đang xét không hỗ trợ cách khai báo đó.

## 5. Class-level và method-level: phạm vi ảnh hưởng

Annotation trên phương thức `@Bean` điều kiện hóa **riêng bean definition của phương thức**:

~~~java
@AutoConfiguration
class JvmAdaptersAutoConfiguration {

    @Bean
    @ConditionalOnJava(JavaVersion.TWENTY_ONE)
    RuntimeMarker modernMarker() {
        return new RuntimeMarker("modern");
    }

    @Bean
    @ConditionalOnJava(
        value = JavaVersion.TWENTY_ONE,
        range = ConditionalOnJava.Range.OLDER_THAN
    )
    RuntimeMarker legacyMarker() {
        return new RuntimeMarker("legacy");
    }
}
~~~

Trích đoạn này minh họa hai nhánh; `RuntimeMarker` cần được định nghĩa. Từ góc nhìn bean registration: JVM trước 21 nhận `legacyMarker`; JVM 21 trở lên nhận `modernMarker`.

Annotation ở cấp class điều kiện hóa cả cấu hình:

~~~java
@AutoConfiguration
@ConditionalOnJava(JavaVersion.TWENTY_ONE)
class ModernOnlyAutoConfiguration {

    @Bean
    RuntimeMarker modernMarker() {
        return new RuntimeMarker("modern");
    }
}
~~~

Nếu JVM là Java 17, Spring bỏ qua cấu hình đó, đồng nghĩa bean `modernMarker` bên trong cũng không được đăng ký qua cấu hình này. Các trích đoạn ở mục 5 chỉ mô tả cách tổ chức; ví dụ test có đủ class cần thiết nằm ở mục 6.

Điều kiện được đánh giá khi Spring **xử lý cấu hình và đăng ký bean**. Nó không theo dõi JVM đang chạy theo thời gian để thay đổi bean sau khi context đã khởi động. Một JVM không thể tự chuyển từ Java 17 sang Java 21 giữa vòng đời của cùng một process; đổi JDK và khởi động lại ứng dụng mới làm điều kiện được đánh giá theo runtime mới.

## 6. Ví dụ Java 17+ kiểm thử được bằng `ApplicationContextRunner`

Ví dụ sau kiểm tra trực tiếp nhánh tương thích với JVM chạy test. Trong một project Spring Boot 3.3 có `spring-boot-starter-test`, tạo file:

`src/test/java/com/example/demo/ConditionalOnJavaTest.java`

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnJava;
import org.springframework.boot.autoconfigure.condition.ConditionalOnJava.Range;
import org.springframework.boot.system.JavaVersion;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionalOnJavaTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(JvmAutoConfiguration.class));

    @AutoConfiguration
    static class JvmAutoConfiguration {

        @Bean("java17OrNewer")
        @ConditionalOnJava(JavaVersion.SEVENTEEN)
        String java17OrNewer() {
            return "supported";
        }

        @Bean("beforeJava21")
        @ConditionalOnJava(
                value = JavaVersion.TWENTY_ONE,
                range = Range.OLDER_THAN
        )
        String beforeJava21() {
            return "legacy";
        }

        @Bean("fromJava21")
        @ConditionalOnJava(JavaVersion.TWENTY_ONE)
        String fromJava21() {
            return "modern";
        }
    }

    @AutoConfiguration
    @ConditionalOnJava(JavaVersion.TWENTY_ONE)
    static class Java21Configuration {

        @Bean("classLevelBean")
        String classLevelBean() {
            return "java21-plus";
        }
    }

    @Test
    void methodLevelConditionsMatchActualRuntime() {
        boolean atLeast21 = Runtime.version().feature() >= 21;

        runner.run(context -> {
            assertThat(context.containsBean("java17OrNewer")).isTrue();
            assertThat(context.containsBean("beforeJava21"))
                    .isEqualTo(!atLeast21);
            assertThat(context.containsBean("fromJava21"))
                    .isEqualTo(atLeast21);
        });
    }

    @Test
    void classLevelConditionGatesWholeConfiguration() {
        boolean atLeast21 = Runtime.version().feature() >= 21;

        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(Java21Configuration.class))
                .run(context ->
                        assertThat(context.containsBean("classLevelBean"))
                                .isEqualTo(atLeast21));
    }

    @Test
    void environmentPropertyDoesNotImpersonateJvmVersion() {
        boolean atLeast21 = Runtime.version().feature() >= 21;

        runner.withPropertyValues("java.version=999")
                .run(context -> {
                    assertThat(context.containsBean("beforeJava21"))
                            .isEqualTo(!atLeast21);
                    assertThat(context.containsBean("fromJava21"))
                            .isEqualTo(atLeast21);
                });
    }
}
~~~

Chạy trong project đã có Spring Boot Gradle plugin, JUnit 5 và `spring-boot-starter-test`:

~~~bash
./gradlew test --tests "com.example.demo.ConditionalOnJavaTest"
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.demo.ConditionalOnJavaTest"
~~~

**Kết quả mong đợi: 3 test PASS** trên cả Java 17 và Java 21 khi project được thiết lập để sử dụng đúng JDK test. Điểm khác nhau là bean được tạo:

| JVM thực thi test | `java17OrNewer` | `beforeJava21` | `fromJava21` | `classLevelBean` trong context riêng |
| --- | --- | --- | --- | --- |
| Java 17 | Có | Có | Không | Không |
| Java 21 | Có | Không | Có | Có |
| Java 22 | Có | Không | Có | Có |

Test thứ ba cố ý thêm `java.version=999` **vào Spring Environment**. Đây không phải cách đổi JVM; condition vẫn xét phiên bản runtime thật. Điều này chứng minh không thể dùng `withPropertyValues(...)` để giả lập Java 21 khi test thực sự chạy trên Java 17.

Các assertion kiểm tra trạng thái context, **không tạo stdout cố định**. Ví dụ dùng bean `String` đơn giản để tách riêng hành vi `@ConditionalOnJava` khỏi nghiệp vụ.

### Kiểm thử biên đúng cách

Để kiểm tra cả hai phía của mốc Java 21, cần **chạy bài test dưới hai JVM thật**, chẳng hạn Java 17 và Java 21. `ApplicationContextRunner` không có tham số chuyển runtime Java trong cùng process. Nếu dùng Gradle Java toolchain cho tác vụ `test` hoặc cấu hình JVM test riêng của IDE/CI, xác nhận JDK thực sự khởi chạy test; Java dùng chạy Gradle daemon chưa chắc trùng Java chạy mọi `Test` task.

Một kiểm tra runtime trực tiếp khi ứng dụng đang chạy:

~~~java
System.out.println(Runtime.version().feature());
~~~

Ví dụ, process thật sự chạy trên Java 21 sẽ in:

~~~text
21
~~~

Lưu ý đây là **output phụ thuộc runtime**, không phải kết quả cố định cho mọi môi trường.

## 7. Phân biệt JVM runtime, compile target và compatibility

| Khía cạnh | Ví dụ | `@ConditionalOnJava` có xét trực tiếp không? |
| --- | --- | --- |
| Java chạy ứng dụng hoặc chạy test | Process Spring Boot thực sự chạy bằng JDK 21 | **Có.** |
| Java dùng để biên dịch source | `javac` của JDK 21 | Không, trừ khi bản thân runtime cũng là Java 21. |
| Bytecode target | `javac --release 17` | Không. Có thể chạy bytecode 17 trên JVM 21 nhưng condition vẫn thấy runtime 21. |
| Spring property | `app.java-version=21` trong `application.yml` | Không. |
| Maven/Gradle dependency | Dùng thư viện yêu cầu Java 21 | Không tự bảo đảm thư viện có thể nạp trên Java 17. |
| Class xuất hiện trên classpath | `@ConditionalOnClass` có thể kiểm tra | Là vấn đề khác, không thay thế version condition. |

**Giới hạn rất quan trọng:** một ứng dụng biên dịch toàn bộ thành class file của Java 21 có thể bị JVM 17 từ chối nạp **trước khi** điều kiện có cơ hội loại trừ bean. `@ConditionalOnJava` không phải “tường chắn” đảm bảo JVM cũ sẽ đọc được bytecode mới hoặc không đụng tới một API không tồn tại. Muốn hỗ trợ JVM cũ, phải đảm bảo phần bắt buộc nạp có bytecode phù hợp, chọn cách đóng gói tương thích (ví dụ tách module/artifact đúng runtime, cấu hình class loading thích hợp) và kiểm tra bằng test trên từng JVM hỗ trợ.

Ngược lại, nếu chỉ dùng JDK 21 để **build** một ứng dụng đặt `--release 17` rồi chạy ứng dụng bằng JVM 17, condition thấy **Java 17**. Nếu chạy đúng artifact đó bằng JVM 21, condition thấy **Java 21**.

## 8. Lỗi thường gặp và cách debug

1. **Đặt `@ConditionalOnJava(JavaVersion.TWENTY_ONE)` và kỳ vọng đúng bằng Java 21.** Mặc định là **≥ 21**; Java 22 hoặc 23 cũng khớp. Nếu yêu cầu chính xác một khoảng hẹp, dùng condition có cả hai mốc và kiểm thử biên.
2. **Nhầm `OLDER_THAN` với `≤`.** `OLDER_THAN(TWENTY_ONE)` loại Java 21; nó chỉ chấp nhận giá trị nhỏ hơn 21.
3. **Để trống `value`.** Thuộc tính `value` là bắt buộc; khác với một số annotation condition khác, không có mốc JVM mặc định.
4. **Dùng `application.properties` để “đổi phiên bản Java”.** `@ConditionalOnJava` xét JVM thật. Sửa Spring property không thay thế quá trình chạy bằng JDK khác.
5. **Nhầm JDK của IDE, Gradle và ứng dụng container.** Máy có JDK 21 nhưng container Docker chạy JRE 17 thì điều kiện xét Java 17; kiểm tra `java -version` *bên trong* container và `Runtime.version().feature()` của đúng process.
6. **Giả định mã chỉ dùng khi Java 21 có thể compile/run trên Java 17.** Source/API mới hoặc bytecode target cao vẫn có thể làm ứng dụng không khởi động; thiết kế compatibility cần từ build, packaging và class loading.
7. **Chọn mốc ngoài các `JavaVersion` enum mà thư viện Spring Boot đang dùng định nghĩa.** Không tự suy đoán có hằng `TWENTY_FOUR` hoặc `TWENTY_FIVE` trong Spring Boot 3.3; kiểm tra JavaDoc phiên bản Spring Boot đang dùng trước khi gõ tên enum.
8. **Nhầm điều kiện đăng ký với tình trạng “runtime đã sẵn sàng”.** Condition chỉ quyết định việc đưa bean/configuration vào context. Nó không kiểm tra thư viện đã hoạt động đúng, service có kết nối hay feature đã được phép bật theo property nghiệp vụ.
9. **Dùng condition JVM để thay thế kiểm tra classpath.** Nếu tính năng còn đòi thư viện tùy chọn, xem xét `@ConditionalOnClass` hoặc cơ chế phân chia cấu hình phù hợp; JVM đủ mới không đảm bảo dependency tồn tại.

Khi một bean bất ngờ bị bỏ qua, bật `--debug` hoặc `debug=true` trong Spring Boot để xem Condition Evaluation Report; tìm auto-configuration, Java condition và nguyên nhân match/did-not-match. Có thể kiểm tra report qua Actuator `/actuator/conditions` nếu endpoint được kích hoạt/expose theo cấu hình dự án. Đối chiếu với version chạy thực tế, rồi thêm test cho các mốc biên.

## 9. Tự kiểm tra kiến thức

1. JVM là Java 21; `@ConditionalOnJava(JavaVersion.TWENTY_ONE)` có khớp không? **Có**, vì mốc dưới bao gồm chính Java 21.
2. JVM là Java 21; `@ConditionalOnJava(value = JavaVersion.TWENTY_ONE, range = Range.OLDER_THAN)` có khớp không? **Không**, vì biên trên loại chính mốc 21.
3. JVM là Java 20; `@ConditionalOnJava(JavaVersion.TWENTY_ONE)` có khớp không? **Không**.
4. Ứng dụng biên dịch bằng JDK 21 với `--release 17` nhưng được chạy bằng JRE 17; condition quan sát phiên bản nào? **17**.
5. Chỉ dùng `@ConditionalOnJava` có thể biểu diễn chính xác `21 ≤ JVM < 23` không? **Không**; một annotation có một ngưỡng một phía. Cần xây dựng điều kiện khoảng phù hợp.
6. Một module Spring Boot 3.3 yêu cầu “Java từ 17 đến trước 21”. Vì sao `OLDER_THAN(TWENTY_ONE)` có thể đủ trong môi trường này? Vì **Spring Boot 3.3 đã có yêu cầu tối thiểu Java 17**, còn annotation bổ sung điều kiện **Java < 21**.

## Tài liệu chính thức

- [Spring Boot 3.3 — `@ConditionalOnJava` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnJava.html): `value` bắt buộc, `range` mặc định và ngữ nghĩa lower-inclusive/upper-exclusive.
- [Spring Boot 3.3 — `ConditionalOnJava.Range` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnJava.Range.html): `EQUAL_OR_NEWER` và `OLDER_THAN`.
- [Spring Boot 3.3 — `JavaVersion` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/system/JavaVersion.html): các mốc enum và API phiên bản runtime.
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): `ApplicationContextRunner` và gợi ý kiểm chứng điều kiện.
