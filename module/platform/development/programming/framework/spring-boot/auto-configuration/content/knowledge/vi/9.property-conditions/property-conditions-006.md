# Phân biệt thuộc tính không tồn tại, chuỗi rỗng và giá trị `false`

## 1. Mục tiêu bài học

Trong Spring Boot Auto Configuration, một cấu hình có thể được bật hoặc bỏ qua dựa trên `@ConditionalOnProperty`. Ba trạng thái dễ bị nhầm lẫn nhất là:

1. **Thuộc tính không tồn tại (missing):** `Environment` không giải quyết được giá trị cho khóa đã hỏi; ví dụ không có `demo.feature` trong bất kỳ nguồn cấu hình có hiệu lực nào.
2. **Thuộc tính tồn tại nhưng giá trị là chuỗi rỗng (empty string):** khóa `demo.feature` có giá trị `""`, tức chuỗi dài 0 ký tự. Đây vẫn là một giá trị đã được cung cấp.
3. **Thuộc tính có giá trị `false`:** khóa có giá trị chuỗi `"false"` khi Spring Boot kiểm tra điều kiện. Đây là giá trị cụ thể, **không phải** “không có giá trị”.

Mục tiêu thực hành: dự đoán chính xác lúc nào `@ConditionalOnProperty` khớp, hiểu vai trò của `havingValue` và `matchIfMissing`, và biết khi nào cần một `Condition` tùy chỉnh để phân biệt **chính xác chuỗi rỗng** với mọi giá trị khác.

Bài này xét **điều kiện thuộc tính** trong Spring Boot 3.3.x. Đối tượng được đánh giá là giá trị từ `Environment` tại thời điểm xử lý cấu hình, không phải biến Java boolean đang được inject và cũng không phải việc bean khác có tồn tại hay không.

## 2. Cùng một khóa, ba trạng thái khác nhau

Giả sử ứng dụng sử dụng khóa `demo.feature`.

### 2.1. Không tồn tại

Trong `application.properties` **không có** dòng `demo.feature`; đồng thời các nguồn cấu hình khác (tham số khởi động, biến môi trường, profile, v.v.) cũng không cung cấp khóa đó.

```properties
# Không khai báo demo.feature
demo.display-name=Example
```

Khi đó:

- `environment.getProperty("demo.feature")` trả về `null` nếu không có giá trị được giải quyết.
- `@ConditionalOnProperty(name = "demo.feature")` **không khớp** theo mặc định.
- `matchIfMissing = true` là tham số chuyên dùng để cho phép điều kiện khớp trong trường hợp này.

**Chú ý:** việc không ghi khóa trong *một* file chưa đủ để kết luận “missing”. Nếu command line, biến môi trường hoặc một nguồn có hiệu lực khác cung cấp giá trị, khóa vẫn được coi là có giá trị.

### 2.2. Chuỗi rỗng

Trong `application.properties`:

```properties
demo.feature=
```

Hoặc trong `application.yml`, viết rõ chuỗi rỗng:

```yaml
demo:
  feature: ""
```

Kết quả mong đợi là giá trị chuỗi `""` với độ dài bằng 0. Khóa đã hiện diện trong nguồn cấu hình và không bị xem là missing chỉ vì không có ký tự nào sau dấu bằng. Viết `feature: ""` trong YAML giúp tránh nhập nhằng với một giá trị YAML `null`.

Với Spring Boot 3.3, `@ConditionalOnProperty(name = "demo.feature")` **khớp** khi giá trị là `""`, bởi kiểm tra mặc định chỉ loại đúng chuỗi `"false"` (không phân biệt chữ hoa/chữ thường); `""` khác `"false"`.

Đây là điểm thường gây bất ngờ: một cấu hình “để trống” có thể **bật** auto-configuration nếu chỉ dùng điều kiện mặc định.

### 2.3. Giá trị `false`

Trong `application.properties`:

```properties
demo.feature=false
```

Hoặc trong `application.yml`:

```yaml
demo:
  feature: false
```

Giá trị được sử dụng cho việc kiểm tra tương ứng với chuỗi `"false"`. Khi ấy:

- Điều kiện mặc định `@ConditionalOnProperty(name = "demo.feature")` **không khớp**.
- Điều kiện `@ConditionalOnProperty(name = "demo.feature", havingValue = "false")` **khớp**.
- `matchIfMissing = true` **không** biến `false` thành true; tùy chọn đó chỉ tác động khi giá trị thực sự thiếu.

Không nhầm ba khái niệm: **missing = không giải quyết được giá trị**, **empty = có chuỗi dài 0**, **false = có chuỗi mang nội dung “false”**.

## 3. Cơ chế chính xác của `@ConditionalOnProperty`

Ví dụ:

```java
@ConditionalOnProperty(prefix = "demo", name = "feature")
@Configuration(proxyBeanMethods = false)
class FeatureAutoConfiguration {
    // Các bean ở đây chỉ được xử lý khi điều kiện khớp.
}
```

Spring Boot hình thành khóa đầy đủ từ `prefix` và `name`: `demo.feature`. Về mặt kết quả, có thể hình dung phép quyết định cho một khóa như sau:

```text
                  Đọc demo.feature từ Environment
                                |
                    Có giá trị giải quyết được?
                         /                 \
                      Không                 Có
                       |                    |
             Trả về matchIfMissing     Xét havingValue
                                            |
                            havingValue có chuỗi khác rỗng?
                                 /                 \
                               Không                Có
                                |                   |
                     Giá trị KHÁC "false"?  Giá trị BẰNG havingValue?
                                |                   |
                              Kết quả              Kết quả
```

Điều này diễn đạt cách so khớp của `OnPropertyCondition` trong Spring Boot 3.3: so chuỗi theo hướng không phân biệt chữ hoa/thường đối với trường hợp `"false"` và `havingValue`.

**Hai mặc định quan trọng:**

- `havingValue = ""`: mặc định. **Không** có nghĩa “chỉ khớp khi giá trị bằng chuỗi rỗng”; nghĩa của nó là **giá trị hiện diện và khác `"false"`**.
- `matchIfMissing = false`: mặc định. Khi khóa thiếu thì điều kiện không khớp, **bất kể** `havingValue` đang là giá trị nào.

Với `@ConditionalOnProperty(prefix = "demo", name = "feature")`, các câu hỏi lần lượt là “có giá trị không?” rồi “giá trị đó có khác `false` không?”. Không có bước ép kiểu thành boolean theo ý nghĩa thường thấy của “truthy/falsy”.

### 3.1. Bảng chân trị cần nhớ

Các cột minh họa năm cách khai báo sau:

- **Mặc định**: `@ConditionalOnProperty(name = "demo.feature")`.
- **Chỉ true**: `@ConditionalOnProperty(name = "demo.feature", havingValue = "true")`.
- **Chỉ false**: `@ConditionalOnProperty(name = "demo.feature", havingValue = "false")`.
- **Mặc định + cho phép thiếu**: `@ConditionalOnProperty(name = "demo.feature", matchIfMissing = true)`.
- **Chỉ true + cho phép thiếu**: `@ConditionalOnProperty(name = "demo.feature", havingValue = "true", matchIfMissing = true)`.

| Giá trị được giải quyết | Mặc định | Chỉ true | Chỉ false | Mặc định + cho phép thiếu | Chỉ true + cho phép thiếu |
| --- | :---: | :---: | :---: | :---: | :---: |
| Không tồn tại (`null`) | Không | Không | Không | **Có** | **Có** |
| Chuỗi rỗng `""` | **Có** | Không | Không | **Có** | Không |
| `"false"` | Không | Không | **Có** | Không | Không |
| `"FALSE"` | Không | Không | **Có** | Không | Không |
| `"true"` | **Có** | **Có** | Không | **Có** | **Có** |
| `"off"` | **Có** | Không | Không | **Có** | Không |
| `"0"` | **Có** | Không | Không | **Có** | Không |
| `" "` (một dấu cách) | **Có** | Không | Không | **Có** | Không |

Bảng này được xét trong ngữ cảnh giá trị chuỗi mà `Environment` trả về. `"off"` và `"0"` không bằng literal `"false"`, nên **điều kiện mặc định vẫn khớp**, dù một cơ chế bind boolean khác có thể hiểu chúng là false. `" "` không phải chuỗi rỗng và cũng không bằng `"false"`.

**Quy tắc cho `havingValue`:**

- Nếu là chuỗi **khác rỗng**, Spring Boot so sánh giá trị giải quyết được với chuỗi đó (không phân biệt hoa/thường).
- Nếu là `""` (mặc định hoặc ghi tường minh), nó sử dụng nhánh “khác `false`”, chứ không kiểm tra “bằng chuỗi rỗng”.
- Nếu giá trị thiếu, `matchIfMissing` quyết định trước; vì vậy `havingValue = "true", matchIfMissing = true` **vẫn khớp khi missing**.

### 3.2. So sánh với ép kiểu boolean

Hai câu dưới đây **không tương đương trong mọi trường hợp**:

```java
@ConditionalOnProperty(name = "demo.feature")
```

và:

```java
Boolean enabled = environment.getProperty(
    "demo.feature", Boolean.class
);
```

Câu đầu là điều kiện riêng của Spring Boot: với giá trị `"off"` hoặc `"0"`, điều kiện mặc định có thể khớp do chuỗi khác `"false"`. Câu sau yêu cầu bộ chuyển đổi kiểu của `Environment` diễn giải một chuỗi như boolean, có quy tắc khác; kết quả cũng có thể là `null` khi khóa thiếu.

Nếu `demo.feature` thực sự là công tắc bật/tắt, thường chọn:

```java
@ConditionalOnProperty(
    prefix = "demo",
    name = "feature",
    havingValue = "true",
    matchIfMissing = false
)
```

Khi đó chỉ giá trị rõ ràng `true` mới bật tính năng. Không nên dùng điều kiện mặc định rồi ngầm mong `off`, `0`, hoặc giá trị trống đều tắt tính năng.

## 4. Chọn điều kiện theo yêu cầu nghiệp vụ

| Yêu cầu | Cách khai báo / kiểm tra | Missing | Empty | False |
| --- | --- | --- | --- | --- |
| Bật khi khóa có giá trị khác literal `false` | `@ConditionalOnProperty(name = "demo.feature")` | Tắt | **Bật** | Tắt |
| Chỉ bật khi cấu hình là `true` | `havingValue = "true"` | Tắt | Tắt | Tắt |
| Chạy nhánh riêng khi cấu hình là `false` | `havingValue = "false"` | Tắt | Tắt | **Bật** |
| Mặc định bật nếu chưa khai báo, nhưng `false` tắt | `matchIfMissing = true` | **Bật** | **Bật** | Tắt |
| Chỉ xử lý khi khóa tồn tại **và chính xác rỗng** | `Condition` tùy chỉnh so `"".equals(environment.getProperty(key))` | Tắt | **Bật** | Tắt |

**Không thể dùng `havingValue = ""` để chọn duy nhất chuỗi rỗng.** Với Spring Boot 3.3, giá trị đó là ký hiệu của chế độ mặc định và khớp với cả `true`, `yes`, `off`, `0`, v.v. nếu các giá trị này được nhìn thấy dưới dạng chuỗi khác `false`.

Nếu bạn cần phân biệt “không đặt cấu hình” với “đặt nhưng để trống”, hãy đọc giá trị giải quyết được và kiểm tra riêng: `value == null` cho trạng thái thiếu và `"".equals(value)` cho chuỗi rỗng. Nếu cần phân biệt một giá trị `null` được khai báo tường minh trong một loại nguồn cấu hình cụ thể, phải kiểm tra quy tắc chuyển đổi và thứ tự các `PropertySource`; không suy ra từ hình dạng YAML hay tên biến môi trường.

## 5. Ví dụ Java 17+ chạy độc lập: quan sát tất cả trạng thái

Ví dụ dùng Spring Boot **3.3.5** (phiên bản 3.3.x đã phát hành) với `AnnotationConfigApplicationContext`. Mỗi lần chạy tạo một application context mới; nguồn cấu hình mô phỏng được đưa vào trước khi `refresh()`. Mọi điều kiện nằm trên **lớp cấu hình**, nên chỉ các bean tương ứng mới được tạo.

Cấu trúc thư mục:

```text
property-state-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── PropertyStatesDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>property-state-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
            <version>3.3.5</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/PropertyStatesDemo.java`:

```java
package demo;

import java.util.Map;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class PropertyStatesDemo {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(prefix = "demo", name = "feature")
    static class DefaultConfig {
        @Bean("defaultBean")
        String defaultBean() {
            return "default";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
        prefix = "demo", name = "feature", havingValue = "true"
    )
    static class TrueConfig {
        @Bean("trueBean")
        String trueBean() {
            return "true";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
        prefix = "demo", name = "feature", havingValue = "false"
    )
    static class FalseConfig {
        @Bean("falseBean")
        String falseBean() {
            return "false";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
        prefix = "demo", name = "feature", matchIfMissing = true
    )
    static class MissingAllowedConfig {
        @Bean("missingAllowedBean")
        String missingAllowedBean() {
            return "missing-allowed";
        }
    }

    // @ConditionalOnProperty(havingValue = "") không có nghĩa
    // "chỉ khi rỗng", nên dùng Condition riêng nếu cần.
    static final class ExactEmptyCondition implements Condition {
        @Override
        public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
        ) {
            return "".equals(
                context.getEnvironment().getProperty("demo.feature")
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Conditional(ExactEmptyCondition.class)
    static class ExactEmptyConfig {
        @Bean("exactEmptyBean")
        String exactEmptyBean() {
            return "exact-empty";
        }
    }

    private static void scenario(String label, String value) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

            if (value != null) {
                context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource(
                        "scenario",
                        Map.of("demo.feature", value)
                    )
                );
            }
            // value == null biểu diễn "không thêm khóa này".
            // Lớp cấu hình được đăng ký sau khi đã đặt Environment.
            context.register(
                DefaultConfig.class,
                TrueConfig.class,
                FalseConfig.class,
                MissingAllowedConfig.class,
                ExactEmptyConfig.class
            );
            context.refresh();

            System.out.printf(
                "%s: default=%s, true=%s, false=%s, " +
                "missingAllowed=%s, exactEmpty=%s%n",
                label,
                context.containsBean("defaultBean"),
                context.containsBean("trueBean"),
                context.containsBean("falseBean"),
                context.containsBean("missingAllowedBean"),
                context.containsBean("exactEmptyBean")
            );
        }
    }

    public static void main(String[] args) {
        scenario("missing", null);
        scenario("empty", "");
        scenario("false", "false");
        scenario("FALSE", "FALSE");
        scenario("true", "true");
        scenario("off", "off");
        scenario("zero", "0");
        scenario("space", " ");
    }
}
```

Với **JDK 17+**, **Maven 3.8+** và quyền tải dependencies, chạy tại thư mục `property-state-demo`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.PropertyStatesDemo
```

Tám dòng do chương trình in ra (không tính thông báo từ Maven hoặc môi trường):

```text
missing: default=false, true=false, false=false, missingAllowed=true, exactEmpty=false
empty: default=true, true=false, false=false, missingAllowed=true, exactEmpty=true
false: default=false, true=false, false=true, missingAllowed=false, exactEmpty=false
FALSE: default=false, true=false, false=true, missingAllowed=false, exactEmpty=false
true: default=true, true=true, false=false, missingAllowed=true, exactEmpty=false
off: default=true, true=false, false=false, missingAllowed=true, exactEmpty=false
zero: default=true, true=false, false=false, missingAllowed=true, exactEmpty=false
space: default=true, true=false, false=false, missingAllowed=true, exactEmpty=false
```

**Giải thích:**

1. `missing`: phương thức không thêm property source cho `demo.feature`. Chỉ điều kiện `matchIfMissing = true` được chấp nhận.
2. `empty`: khóa tồn tại và giá trị `""` khác `false` nên hai cấu hình `DefaultConfig` và `MissingAllowedConfig` được kích hoạt. Condition tùy chỉnh khớp chính xác chuỗi rỗng.
3. `false` và `FALSE`: điều kiện `havingValue = "false"` khớp; điều kiện mặc định không khớp, chứng minh việc so sánh không phân biệt hoa/thường.
4. `true`: điều kiện mặc định, `havingValue = "true"` và `matchIfMissing = true` đều khớp.
5. `off` và `zero`: điều kiện mặc định vẫn khớp vì giá trị chuỗi không bằng `false`. Đây **không** phải kết quả ép kiểu boolean theo Java hay `Binder`.
6. `space`: chuỗi chứa một dấu cách khác `""`; vì vậy điều kiện tùy chỉnh `ExactEmptyCondition` không khớp. Nó cũng khác literal `false` nên điều kiện mặc định khớp.

**Phạm vi ví dụ:** đây là một chương trình Spring Context thuần dùng các annotation điều kiện của Spring Boot để quan sát quy tắc. Trong một starter/auto-configuration thực tế, có thể dùng `@AutoConfiguration` và khai báo trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; logic so khớp thuộc tính vẫn theo cùng quy tắc.

## 6. Dùng trong auto-configuration thực tế

Giả sử một starter có tính năng gửi thông báo; không được gửi thông báo ngoài ý muốn nếu người dùng để trống cấu hình.

### 6.1. Thiết kế “chỉ bật khi true”

```java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "notifications",
    name = "enabled",
    havingValue = "true"
)
public class NotificationAutoConfiguration {
    // @Bean NotificationSender ...
}
```

Đây là **snippet minh họa**, giả định bean và dependencies liên quan đã được định nghĩa. Giá trị mặc định của `matchIfMissing` là `false`, nên missing và empty đều không kích hoạt. Trong `application.properties`:

```properties
notifications.enabled=true
```

Đặt `false` hoặc để trống đều tắt. Điều này an toàn hơn cho một công tắc yêu cầu người dùng chủ động bật.

### 6.2. Thiết kế “bật mặc định, chỉ false mới tắt”

```java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "notifications",
    name = "enabled",
    matchIfMissing = true
)
public class NotificationAutoConfiguration {
    // @Bean NotificationSender ...
}
```

Với thiết kế này, missing nghĩa là dùng mặc định **bật**. Tuy nhiên empty cũng **bật** vì nó là giá trị đã tồn tại và khác `false`; điều đó có thể bất ngờ nếu người vận hành tưởng ô trống là tắt. Nếu kỳ vọng “missing bật, nhưng empty tắt”, `@ConditionalOnProperty` đơn thuần không diễn đạt trọn yêu cầu; hãy định nghĩa một `Condition` cụ thể và test ba trạng thái.

### 6.3. Phối hợp nhiều khóa

```java
@ConditionalOnProperty(
    prefix = "notifications",
    name = {"enabled", "remote"},
    havingValue = "true"
)
```

Điều kiện khớp khi **cả hai** khóa `notifications.enabled` và `notifications.remote` giải quyết thành `true`. Nếu một khóa missing (với mặc định `matchIfMissing = false`), empty hoặc false thì điều kiện không khớp. Không hiểu `name = {a, b}` là “chỉ cần một trong hai”.

### 6.4. Khác biệt nguồn cấu hình

Cùng một giá trị cuối cùng có thể đến từ file `application.properties`, `application.yml`, profile, biến môi trường, hệ thống cấu hình bên ngoài hoặc command line. `@ConditionalOnProperty` xét **giá trị cuối cùng mà `Environment` giải quyết được**, sau cơ chế ưu tiên nguồn cấu hình; nó không xét có hay không có dòng literal trong riêng một file.

Ví dụ khởi động một Spring Boot ứng dụng hoàn chỉnh với:

```bash
java -jar app.jar --notifications.enabled=
```

sẽ đặt một giá trị command-line rỗng cho khóa tương ứng nếu ứng dụng sử dụng cấu hình mặc định cho tham số dòng lệnh. Vì thế “không ghi trong file” và “đặt rỗng bằng tham số dòng lệnh” tạo hai tình huống khác nhau. Đừng giả định mọi hệ điều hành/CI đều giữ biến môi trường rỗng theo cùng cách; khi test, dùng `MapPropertySource` như ví dụ để kiểm soát trạng thái rõ ràng.

## 7. Chẩn đoán khi kết quả không như mong đợi

1. **Xác định khóa đầy đủ:** `prefix = "demo"`, `name = "feature"` thành `demo.feature`; theo khuyến nghị API, tên cấu hình nên theo dashed notation khi có nhiều từ (ví dụ `my-feature`).
2. **Kiểm tra giá trị thật:** đọc `environment.getProperty("demo.feature")`. `null`, `""`, `"false"` và `"False"` không thể suy ra chính xác chỉ từ giao diện hiển thị của một màn hình cấu hình. Khi giá trị nhạy cảm, không log nội dung thật ra hệ thống nhật ký.
3. **Kiểm tra tham số điều kiện:** có khai báo `havingValue` không, hay đang dùng mặc định `""`? `matchIfMissing` có thực sự là true không?
4. **Kiểm tra các property source:** một profile, biến môi trường hoặc command line có thể đang ghi đè giá trị trong `application.yml`. Hãy dùng một test context cô lập để loại bỏ sự phụ thuộc môi trường.
5. **Xem Condition Evaluation Report:** với một ứng dụng Spring Boot đầy đủ, có thể bật `--debug` để xem nguyên nhân các auto-configuration conditions khớp hoặc không khớp; Actuator `/actuator/conditions` cũng hỗ trợ khi endpoint được cài đặt và cấu hình phù hợp.
6. **Kiểm thử chính xác:** tách riêng ba tình huống missing/empty/false thay vì chỉ có test true/false. Kiểm tra thêm `"off"`, `"0"` nếu dữ liệu được nhận từ người dùng hoặc nhiều hệ cấu hình.

Đừng nhầm lẫn việc Spring **bind** thuộc tính vào một biến `boolean`/`Boolean` trong `@ConfigurationProperties` với việc `@ConditionalOnProperty` so khớp chuỗi. Hai thành phần phục vụ mục tiêu khác nhau và không nhất thiết có cùng semantics cho mọi ký hiệu của false.

## 8. Lỗi thường gặp

| Hiểu nhầm | Sự thật / hướng sửa |
| --- | --- |
| “Không khai báo” và “khai báo `key=`” giống nhau | Missing cho giá trị giải quyết được `null`; `key=` thường tạo chuỗi `""`. Kiểm thử riêng từng trường hợp. |
| `havingValue = ""` dùng để yêu cầu rỗng | Trong Boot 3.3 nó vẫn là chế độ mặc định: hiện diện và khác `"false"`. Muốn **chỉ rỗng**, dùng `Condition` tùy chỉnh. |
| `matchIfMissing = true` làm mọi giá trị khớp | Nó chỉ thay đổi nhánh missing; giá trị `false` vẫn thất bại với điều kiện mặc định. |
| `"off"` hoặc `"0"` chắc chắn tắt `@ConditionalOnProperty` | Theo so chuỗi mặc định, chúng khác `"false"` nên khớp. Nếu cần bật/tắt rõ ràng, dùng `havingValue = "true"`. |
| `havingValue = "false"` có nghĩa “thiếu hoặc false” | Chỉ khi giá trị đúng `false` mới khớp; muốn missing cũng khớp phải cân nhắc `matchIfMissing = true`. |
| Không có khóa trong `application.yml` nên điều kiện missing | Nguồn khác vẫn có thể cung cấp giá trị; phải xét `Environment` tổng hợp. |
| Giá trị `" "` là chuỗi rỗng | Đây là chuỗi dài một ký tự khoảng trắng; nếu muốn trim, phải làm rõ quy tắc nghiệp vụ và kiểm tra riêng. |
| Có hai tên trong `name` nghĩa là OR | Chúng kết hợp theo AND: mọi khóa đều phải đáp ứng điều kiện. |
| Dùng một phép so khớp thuộc tính để kiểm tra mảng/list | `@ConditionalOnProperty` không đáng tin cậy cho mọi dạng collection indexed; dùng điều kiện tùy chỉnh khi cần. |

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Với `@ConditionalOnProperty(name = "demo.feature")`, hãy đánh giá lần lượt `demo.feature` không tồn tại, `demo.feature=`, và `demo.feature=false`.  
**Đáp án:** Không khớp, khớp, không khớp. Missing dùng `matchIfMissing = false`; empty là chuỗi hiện diện khác `false`.

**Câu 2.** `@ConditionalOnProperty(name = "demo.feature", havingValue = "false")` có khớp nếu khóa không tồn tại không?  
**Đáp án:** Không, bởi `matchIfMissing` mặc định false. Nó khớp khi khóa hiện diện với chuỗi `false`, kể cả `FALSE`.

**Câu 3.** `@ConditionalOnProperty(name = "demo.feature", havingValue = "true", matchIfMissing = true)` có khớp khi khóa missing không?  
**Đáp án:** Có. `matchIfMissing = true` áp dụng ở nhánh thiếu, cho dù `havingValue` đã được khai báo.

**Câu 4.** Vì sao `havingValue = ""` không giúp chọn một chuỗi rỗng?  
**Đáp án:** Chuỗi rỗng là giá trị mặc định đặc biệt của tham số `havingValue`; Spring Boot diễn giải thành “giá trị khác literal `false`”, không phải so bằng `""`. Cần `Condition` tự so `"".equals(...)` nếu mục tiêu là exact empty.

**Câu 5.** Vì sao `demo.feature=off` có thể bật auto-configuration mặc định?  
**Đáp án:** Vì điều kiện mặc định kiểm tra chuỗi khác `false`, trong khi `off` không bằng `false`. Nên dùng `havingValue = "true"` cho một cờ chỉ được bật khi giá trị xác nhận là true.

## 10. Ghi nhớ và tài liệu chính thức

- **Missing:** không giải quyết được giá trị → mặc định không khớp; `matchIfMissing` quyết định ngoại lệ.
- **Empty:** có giá trị `""` → **khớp với điều kiện mặc định**, không khớp với `havingValue = "true"` hoặc `"false"`.
- **False:** có giá trị `"false"` → không khớp mặc định; khớp với `havingValue = "false"`.
- **Yêu cầu chỉ bật khi true:** chọn `havingValue = "true"`, xác định rõ policy cho trường hợp missing.
- **Yêu cầu chỉ khớp chuỗi rỗng:** dùng một `Condition` có phép so chính xác và kiểm thử.
- **Nguồn sự thật tại thời điểm đánh giá:** giá trị cuối cùng do Spring `Environment` giải quyết, không phải riêng một file cấu hình.

Tham khảo:

1. Spring Boot 3.3 — [`@ConditionalOnProperty` API và bảng `havingValue`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html).
2. Spring Boot 3.3 — [Creating Your Own Auto-configuration / Property Conditions](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
3. Spring Boot 3.3.5 — [thông báo phát hành chính thức](https://spring.io/blog/2024/10/24/spring-boot-3-3-5-available-now/).