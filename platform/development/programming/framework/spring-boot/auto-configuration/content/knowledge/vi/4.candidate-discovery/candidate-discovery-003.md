# Đăng ký lớp lồng nhau bằng tên nhị phân có ký tự $ trong Spring Boot Auto-configuration

## 1. Vì sao tên lớp lồng nhau có dấu $?

Khi một lớp `@AutoConfiguration` được khai báo **bên trong** một lớp Java khác, mã nguồn thường dùng dấu chấm để tham chiếu nó, nhưng tệp khai báo ứng viên auto-configuration của Spring Boot phải dùng **binary name (tên nhị phân)**. Ranh giới giữa lớp chứa (*outer class*) và lớp thành viên lồng (*nested member class*) trong binary name được biểu diễn bằng ký tự `$`.

Ví dụ lớp Java:

```java
package com.example.autoconfig;

import org.springframework.boot.autoconfigure.AutoConfiguration;

public final class OuterAutoConfigurations {
    private OuterAutoConfigurations() {}

    @AutoConfiguration
    public static class GreetingAutoConfiguration {
    }
}
```

Ba cách biểu diễn khác nhau của lớp `GreetingAutoConfiguration`:

| Khái niệm | Chuỗi cụ thể | Khi nào dùng |
| --- | --- | --- |
| Tên đơn giản | `GreetingAutoConfiguration` | `getSimpleName()`; hiển thị |
| Tên canonical / cú pháp source | `com.example.autoconfig.OuterAutoConfigurations.GreetingAutoConfiguration` | Tham chiếu type trong mã nguồn Java, `getCanonicalName()` |
| **Tên nhị phân** | `com.example.autoconfig.OuterAutoConfigurations$GreetingAutoConfiguration` | `Class.getName()`, `Class.forName(...)`, **`AutoConfiguration.imports`** |

Dấu `.` nối các phần của **package** vẫn giữ nguyên. Chỉ dấu phân cách **outer class và nested class** thay thành `$`. Nếu lồng nhiều tầng như `Outer.Middle.Inner`, tên nhị phân là `Outer$Middle$Inner` (với tiền tố package phù hợp).

Quy tắc này xuất phát từ đặc tả Java (JLS `13.1). **Spring Boot không sáng tạo ra cú pháp riêng**; Boot sử dụng định danh class dạng nhị phân của Java khi đọc những tên class được liệt kê trong tệp imports.

Đích của bài: tự xác định đúng tên cần khai báo, hiểu cơ chế khám phá ứng viên, tạo được dự án minh họa chạy thực tế, biết cách kiểm tra classfile/resource sau khi đóng gói và chẩn đoán lỗi sai tên.

## 2. Vì sao dấu chấm trong Java source lại không dùng được trong imports?

Trong mã nguồn, Java cho phép:

```java
OuterAutoConfigurations.GreetingAutoConfiguration.class
```

Vì compiler biết `GreetingAutoConfiguration` là **member class** của `OuterAutoConfigurations`. Nhưng file tài nguyên bên ngoài mã nguồn chỉ chứa **chuỗi tên class**; ở đó không có cú pháp phân giải tên Java source. Công cụ nạp class theo tên nhị phân như `Class.forName(...)` cần dấu `$` tại vị trí member class.

Với ví dụ trên:

```java
Class<?> nested = OuterAutoConfigurations.GreetingAutoConfiguration.class;
System.out.println(nested.getCanonicalName());
System.out.println(nested.getName());
```

Kết quả hai dòng:

```text
com.example.autoconfig.OuterAutoConfigurations.GreetingAutoConfiguration
com.example.autoconfig.OuterAutoConfigurations$GreetingAutoConfiguration
```

Đây là đoạn minh họa thực thi **trong class Java có thể truy cập kiểu trên**, không phải một file Java độc lập.

Cũng cần phân biệt tên nhị phân và đường dẫn file:

- **Binary name:** `com.example.autoconfig.OuterAutoConfigurations$GreetingAutoConfiguration`.
- **Đường dẫn classfile:** `com/example/autoconfig/OuterAutoConfigurations$GreetingAutoConfiguration.class`.
- **Tên nội bộ JVM ở những nơi khác:** có thể dùng dấu `/` thay dấu chấm package.
- **Tên bean Spring:** ví dụ `defaultGreeter`, là định danh của **bean**, không phải tên lớp auto-config.

Không thay toàn bộ `.` bằng `$`: làm vậy sẽ biến phần package thành chuỗi không hợp lệ.

## 3. Ví dụ Java 17 thuần để kiểm tra tên nhị phân

Đây là chương trình **không phụ thuộc Spring**. Tạo file `src/com/example/NestedNamesDemo.java`:

```java
package com.example;

public class NestedNamesDemo {
    public static class Nested {
        public static class Deep {
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        Class<?> nested = Nested.class;
        Class<?> deep = Nested.Deep.class;

        System.out.println("SIMPLE=" + nested.getSimpleName());
        System.out.println("CANONICAL=" + nested.getCanonicalName());
        System.out.println("BINARY=" + nested.getName());
        System.out.println("DEEP_BINARY=" + deep.getName());

        Class<?> loaded = Class.forName("com.example.NestedNamesDemo$Nested");
        System.out.println("CLASS_FOR_NAME=" + (loaded == nested));

        try {
            Class.forName("com.example.NestedNamesDemo.Nested");
            System.out.println("DOTTED_LOOKUP=found");
        } catch (ClassNotFoundException ex) {
            System.out.println("DOTTED_LOOKUP=not-found");
        }
    }
}
```

Tại thư mục chứa `src`, dùng JDK 17+:

```bash
javac -encoding UTF-8 -d out src/com/example/NestedNamesDemo.java
java -cp out com.example.NestedNamesDemo
```

Stdout **chính xác**:

```text
SIMPLE=Nested
CANONICAL=com.example.NestedNamesDemo.Nested
BINARY=com.example.NestedNamesDemo$Nested
DEEP_BINARY=com.example.NestedNamesDemo$Nested$Deep
CLASS_FOR_NAME=true
DOTTED_LOOKUP=not-found
```

`Class.getName()` trả binary name, còn `getCanonicalName()` trả tên canonical đối với named member class thông thường. `Class.forName("...$Nested")` tìm đúng class, còn `Class.forName("...NestedNamesDemo.Nested")` không hiểu dấu chấm đó là member-class separator.

Mã nguồn Java có `$` nằm trong **string literal** nên không cần escape đặc biệt. Nếu lệnh được nhập trực tiếp vào shell, dấu `$` có thể bị shell hiểu là biến: cách quote lệnh được trình bày ở phần gỡ lỗi.

Lưu ý: `Class.forName` không khởi tạo một bean Spring, không tự tạo `ApplicationContext` và không quyết định điều kiện `@ConditionalOnMissingBean`. Nó chỉ minh họa cách Java định danh/nạp class.

## 4. Spring Boot khám phá auto-configuration candidate ở đâu?

Trong **Spring Boot 3.x**, thư viện công bố auto-configuration qua tài nguyên:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Định dạng cơ bản: **mỗi dòng một binary class name**, có thể có dòng chú thích bắt đầu bằng `#`.

**Đúng đối với nested auto-configuration ở phần 1:**

```text
com.example.autoconfig.OuterAutoConfigurations$GreetingAutoConfiguration
```

**Sai: tên canonical với dấu chấm của Java source:**

```text
com.example.autoconfig.OuterAutoConfigurations.GreetingAutoConfiguration
```

**Sai: đường dẫn classfile:**

```text
com/example/autoconfig/OuterAutoConfigurations$GreetingAutoConfiguration.class
```

**Sai: khai báo cú pháp import Java thay vì tên lớp:**

```java
import com.example.autoconfig.OuterAutoConfigurations.GreetingAutoConfiguration;
```

Trong file imports, Boot cần đúng **tên của class đang mang `@AutoConfiguration`**, không phải lớp chứa nó (trừ khi lớp chứa cũng được thiết kế và đăng ký làm auto-config theo cách riêng).

Một auto-configuration candidate được phát hiện **chưa chắc tạo bean**. Các điều kiện như `@ConditionalOnClass`, `@ConditionalOnProperty` và `@ConditionalOnMissingBean` có thể khiến phần cấu hình hoặc một số `@Bean` không được áp dụng. Phân biệt rõ **candidate được tìm** với **bean được đăng ký**.

### 4.1. Vì sao nên khai báo nested class là static?

Một non-static inner class thông thường mang tham chiếu ngầm tới instance của outer class. Nested auto-configuration nên là **named static member class**, ví dụ `public static class GreetingAutoConfiguration`, để nó có thể được Spring tạo độc lập mà không cần một outer instance.

`static` ở khai báo class **không đồng nghĩa** mọi phương thức `@Bean` bên trong phải là static. Nó chỉ nói rằng nested class không phụ thuộc vào một outer instance.

Đừng dùng local/anonymous class làm auto-config candidate. Tên do compiler tạo có thể gồm số như `Outer$1` hoặc `Outer$1Local`, không thích hợp làm định danh công khai và bền vững trong imports file.

### 4.2. Auto-configuration không nên được component scanning phát hiện

Tài liệu Spring Boot yêu cầu auto-configuration được tải thông qua danh sách imports, nằm trong package riêng và tránh bị component scanning phát hiện như một component ứng dụng. Nếu đưa auto-config vào vùng scan, ta có thể làm thay đổi điều kiện/đường import vốn được Boot thiết kế.

Ở ví dụ chạy bên dưới, application main class nằm ở `com.example.app` còn auto-configuration nằm ở `com.example.autoconfig`. Do không phải package con của app package, nested configuration sẽ được xem xét theo **imports file**.

## 5. Ví dụ Spring Boot hoàn chỉnh: lớp lồng được đăng ký qua binary name

Ví dụ dùng **Java 17+**, **Maven**, **Spring Boot 3.3.13**. Nó cung cấp một bean mặc định thông qua nested auto-configuration, in tên nhị phân/canonical và thử hành vi back-off khi ứng dụng tự cung cấp bean.

### 5.1. Cấu trúc project

```text
nested-auto-config-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/
    │   ├── api/Greeter.java
    │   ├── app/DemoApplication.java
    │   └── autoconfig/OuterAutoConfigurations.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>nested-auto-config-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
```

### 5.3. `src/main/java/com/example/api/Greeter.java`

```java
package com.example.api;

@FunctionalInterface
public interface Greeter {
    String greet(String name);
}
```

`Greeter` là API Java thuần; `@FunctionalInterface` không tự đăng ký bean.

### 5.4. `src/main/java/com/example/autoconfig/OuterAutoConfigurations.java`

```java
package com.example.autoconfig;

import com.example.api.Greeter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

public final class OuterAutoConfigurations {
    private OuterAutoConfigurations() {
    }

    @AutoConfiguration
    public static class GreetingAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(Greeter.class)
        Greeter defaultGreeter() {
            return name -> "AUTO: Hello, " + name + "!";
        }
    }
}
```

- Outer class `OuterAutoConfigurations` là **container** Java thông thường.
- Nested static class `GreetingAutoConfiguration` mang `@AutoConfiguration`, nên là class cần nêu trong imports.
- `defaultGreeter` là tên method/bean mặc định; nó **khác binary name** của nested class.
- `@ConditionalOnMissingBean(Greeter.class)` cho phép bean mặc định nhường chỗ nếu ứng dụng đã khai báo một `Greeter` phù hợp.
- Để thử nghiệm trong một Maven project, auto-configuration và interface API nằm cùng source tree. Khi xuất bản thư viện thật, thường tách API và module auto-config/starter theo kiến trúc phù hợp.

### 5.5. `src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import com.example.api.Greeter;
import com.example.autoconfig.OuterAutoConfigurations;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner show(Greeter greeter, ApplicationContext context) {
        return args -> {
            Class<?> type =
                OuterAutoConfigurations.GreetingAutoConfiguration.class;

            System.out.println("BINARY=" + type.getName());
            System.out.println("CANONICAL=" + type.getCanonicalName());
            System.out.println("DEFAULT_BEAN="
                    + context.containsBean("defaultGreeter"));
            System.out.println("MESSAGE=" + greeter.greet("Spring Boot"));
        };
    }
}
```

`OuterAutoConfigurations.GreetingAutoConfiguration.class` là cách ghi **hợp lệ trong Java source**. `type.getName()` phản ánh chính xác binary name được liệt kê trong file imports, còn `type.getCanonicalName()` cho dạng Java source.

Runner được tạo khi context khởi động; Spring dùng DI tiêm bean `Greeter`. Nếu không có bean phù hợp (ví dụ do imports file bị sai), quá trình tạo runner có thể thất bại.

### 5.6. `src/main/resources/application.properties`

```properties
spring.main.banner-mode=off
spring.main.web-application-type=none
logging.level.root=OFF
```

Chế độ non-web cho ứng dụng chạy runner rồi thoát. Tắt log nhằm làm output minh họa dễ đọc, không quyết định auto-configuration.

### 5.7. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Nội dung **một dòng**:

```text
com.example.autoconfig.OuterAutoConfigurations$GreetingAutoConfiguration
```

File phải tồn tại với đúng tên/đường dẫn khi **đóng gói tài nguyên vào runtime classpath**. Không thêm `import`, dấu `;`, `.class`, dấu `/` hoặc thay `$` bằng dấu chấm giữa outer/nested.

### 5.8. Biên dịch và chạy

Đứng tại thư mục chứa `pom.xml`:

```bash
mvn -q -DskipTests package
java -jar target/nested-auto-config-demo-1.0.0.jar
```

Stdout do application tự in (không tính thông báo từ công cụ/môi trường):

```text
BINARY=com.example.autoconfig.OuterAutoConfigurations$GreetingAutoConfiguration
CANONICAL=com.example.autoconfig.OuterAutoConfigurations.GreetingAutoConfiguration
DEFAULT_BEAN=true
MESSAGE=AUTO: Hello, Spring Boot!
```

**Giải thích:** Boot tìm đúng nested configuration qua binary name, conditions thỏa, bean `defaultGreeter` được đăng ký và DI vào runner. Vì `com.example.autoconfig` không nằm dưới `com.example.app`, đây là bằng chứng thực hành về khai báo bằng imports file, không phải scanning của package ứng dụng.

### 5.9. Thử nghiệm override để phân biệt phát hiện candidate và tạo bean

Bổ sung đoạn sau **bên trong class `DemoApplication`**, ngang cấp phương thức `show(...)`, rồi build/run lại:

```java
@Bean
Greeter customGreeter() {
    return name -> "CUSTOM: Hi, " + name + "!";
}
```

Đây là **đoạn bổ sung**, không phải file chạy độc lập. Stdout kỳ vọng:

```text
BINARY=com.example.autoconfig.OuterAutoConfigurations$GreetingAutoConfiguration
CANONICAL=com.example.autoconfig.OuterAutoConfigurations.GreetingAutoConfiguration
DEFAULT_BEAN=false
MESSAGE=CUSTOM: Hi, Spring Boot!
```

Nested auto-configuration vẫn được **nhận diện**, nhưng `@ConditionalOnMissingBean(Greeter.class)` không khớp vì đã có bean do ứng dụng khai báo, nên default **không được đăng ký**. Dấu `$` chỉ giải quyết chuyện định danh candidate; nó không ép bean mặc định luôn phải tồn tại.

## 6. Kiểm tra classfile và imports resource sau khi đóng gói

Sau Maven package, hai classfile liên quan thường có dạng:

```text
target/classes/com/example/autoconfig/OuterAutoConfigurations.class
target/classes/com/example/autoconfig/OuterAutoConfigurations$GreetingAutoConfiguration.class
```

Lưu ý outer và nested là **hai classfile**. Không chỉ vì thấy outer class mà ta có thể ghi tên outer vào imports thay cho nested.

Có thể liệt kê JAR:

```bash
jar tf target/nested-auto-config-demo-1.0.0.jar
```

Trong ứng dụng Spring Boot JAR, tìm những entry:

```text
BOOT-INF/classes/com/example/autoconfig/OuterAutoConfigurations.class
BOOT-INF/classes/com/example/autoconfig/OuterAutoConfigurations$GreetingAutoConfiguration.class
BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Các entry khác có thể xuất hiện; mục tiêu là xác minh nested classfile và imports file **đều được đóng gói**.

Dùng JDK `javap` (sau khi compile):

```bash
javap -classpath target/classes 'com.example.autoconfig.OuterAutoConfigurations$GreetingAutoConfiguration'
```

Trong **Bash/Zsh và PowerShell**, dấu nháy đơn bảo vệ `$` khỏi bị hiểu là một phần của biến. Nếu dùng dấu nháy kép trên shell có mở rộng biến, một chuỗi kiểu `Outer$GreetingAutoConfiguration` có thể bị thay đổi trước khi tới `javap`. Windows `cmd.exe` có quy tắc mở rộng biến khác, vì vậy áp dụng cách quote theo shell thực tế.

Không cần đoán tên bằng tay khi có thể gọi `OuterAutoConfigurations.GreetingAutoConfiguration.class.getName()` trong Java. Đây là cách trực tiếp lấy binary name để đối chiếu.

## 7. Những nhầm lẫn thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy `Outer.Nested` khi Boot đọc imports | Dùng tên canonical thay vì binary | Ghi `Outer$Nested`, giữ nguyên dấu chấm của package |
| Có `Outer$Nested.class` nhưng auto-config không hoạt động | Sai tên/đường dẫn imports file, tài nguyên không được package, hoặc sai điều kiện | Kiểm tra JAR và condition report |
| Viết `Outer` trong imports | Trỏ tới class chứa thay vì nested class có `@AutoConfiguration` | Dùng binary name chính xác của nested candidate |
| Viết `Outer$Nested` trong Java source như cách truy cập member | Nhầm định danh nhị phân và cú pháp Java | Dùng `Outer.Nested` trong source |
| Có imports đúng nhưng bean `@Bean` không tồn tại | Điều kiện bean/class/property không khớp | Kiểm tra `@Conditional...` và bean definitions |
| Dùng non-static inner class | Inner instance đòi hỏi outer instance | Chuyển thành named static nested class |
| Lệnh shell trông đúng nhưng `javap` lỗi | `$` bị shell mở rộng | Quote literal chính xác |
| Ghi `com$example$Outer$Nested` | Thay cả dấu chấm package | Chỉ ranh giới lớp lồng sử dụng `$` |
| Viết `Outer$Nested.class` vào imports | Nhầm tên class và tên tệp | Bỏ phần mở rộng `.class` |
| Chỉ thêm tên vào imports mà không có classfile thực | Khai báo candidate không tạo ra Java class | Biên dịch và đóng gói class thực tế |

### 7.1. Nested auto-config khác nested configuration bên trong auto-config

Một class `@Configuration` lồng **bên trong một auto-configuration đã đăng ký** có thể được xử lý như cấu hình nội bộ nếu Spring import/parse đúng và các điều kiện cho phép. Trường hợp này **không mặc định đòi hỏi mọi nested helper đều phải xuất hiện thành một dòng riêng trong imports**.

Bài toán của hàng này là tình huống **chính nested class là auto-configuration candidate cần liệt kê**. Khi ấy mới phải khai báo đúng `Outer$NestedAutoConfiguration` trong file imports.

### 7.2. Tên binary trong các cấu hình khác

Những API nhận **class literal** (ví dụ `@Import(Outer.Nested.class)`) dùng cú pháp Java source bình thường. Những API nhận **tên class dưới dạng chuỗi** (ví dụ `@AutoConfiguration(afterName = "...")` hoặc loại trừ auto-config bằng tên) cần nhận diện đúng class đích, đặc biệt khi nó lồng nhau. Đừng đưa bean name hay đường dẫn file vào một thuộc tính đang mong đợi class name.

Với `spring.autoconfigure.exclude`, nếu muốn loại nested auto-config, có thể khai báo theo binary name:

```properties
spring.autoconfigure.exclude=com.example.autoconfig.OuterAutoConfigurations$GreetingAutoConfiguration
```

Trong file properties đây là dấu `$` literal. Nếu nhập qua command-line, hãy xét quy tắc shell quoting. Nếu loại trừ mà ứng dụng vẫn yêu cầu `Greeter` nhưng không cung cấp bean khác, dependency injection có thể thất bại khi khởi động.

## 8. Quy trình áp dụng và gỡ lỗi có hệ thống

1. **Xác định class mang `@AutoConfiguration`:** class top-level hay named nested member? Đừng chỉ nhìn tên outer container.
2. **Lấy binary name:** tốt nhất từ `SomeNested.class.getName()` hoặc đối chiếu classfile. Với nhiều tầng, chú ý mọi `$`.
3. **Ghi imports:** một tên class chuẩn mỗi dòng trong tài nguyên `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
4. **Kiểm tra classfile:** class nested đã biên dịch, thật sự có mặt trong runtime JAR và đúng package chưa?
5. **Kiểm tra tài nguyên:** imports file có được đóng gói theo đường dẫn chính xác không?
6. **Khởi động ứng dụng tiêu thụ:** không chỉ xem Maven compile thành công; cần xem context có khởi động và nhận candidate không.
7. **Kiểm tra condition report:** bật `--debug` để xem *Condition Evaluation Report* nếu class đã được nạp nhưng bean không hiện diện; một condition không khớp có thể là hành vi đúng thiết kế.
8. **Kiểm tra override:** khai báo bean ứng dụng cùng type để xác nhận `@ConditionalOnMissingBean` của default hoạt động.
9. **Khi đổi tên outer/nested class:** cập nhật imports file, các chuỗi ordering/exclusion và cân nhắc cơ chế auto-configuration replacements khi phát hành thư viện có người tiêu thụ.

Với ví dụ demo, có thể chạy:

```bash
java -jar target/nested-auto-config-demo-1.0.0.jar --debug --logging.level.root=DEBUG
```

Khi đó báo cáo điều kiện có thể hiển thị thông tin về `GreetingAutoConfiguration` và `defaultGreeter`. Nếu nhập sai tên binary trong imports, một lỗi class loading có thể xảy ra **trước khi có báo cáo điều kiện đầy đủ**; không phải mọi tình huống không thấy bean đều là missing-bean condition.

## 9. Tự kiểm tra kiến thức

**Câu 1.** Lớp `MyAutoConfiguration` được khai báo `public static` bên trong `com.acme.Outer`. Viết tên nào trong imports?

**Đáp án:** `com.acme.Outer$MyAutoConfiguration`.

**Câu 2.** Nếu class lồng hai tầng `Outer.Middle.Inner` thì sao?

**Đáp án:** `Outer$Middle$Inner`, kèm tiền tố package với dấu `.` như thường.

**Câu 3.** Vì sao `Class.getCanonicalName()` không phải cách an toàn nhất để tạo dòng imports cho nested class?

**Đáp án:** Đối với named member class, nó dùng dấu `.` giữa outer và member, trong khi imports cần **binary name** có `$`. Dùng `Class.getName()`.

**Câu 4.** Có phải mọi class lồng nằm bên trong một auto-config đều phải có dòng riêng trong imports?

**Đáp án:** Không. Chỉ class được thiết kế như **auto-configuration candidate riêng** cần được liệt kê theo cơ chế này. Nested helper configuration có thể được xử lý trong cấu hình đã import.

**Câu 5.** Imports file đúng nhưng `defaultGreeter` không tồn tại, có phải dấu `$` sai?

**Đáp án:** Không thể kết luận vậy. Auto-config có thể được import đúng nhưng bean không được đăng ký do `@ConditionalOnMissingBean` hoặc điều kiện khác.

**Câu 6.** Dùng `@Import(Outer.Nested.class)` trong Java có cần đổi thành `Outer$Nested.class` không?

**Đáp án:** Không. `@Import` nhận class literal từ Java source, nên dùng cú pháp `Outer.Nested.class`.

**Câu 7.** Vì sao ví dụ dùng `public static class GreetingAutoConfiguration`?

**Đáp án:** Class static lồng có thể được Spring xem như một cấu hình độc lập, không cần tạo outer instance; tên nhị phân cố định, dễ đăng ký và đóng gói.

## 10. Tài liệu tham khảo

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): phần *Locating Auto-configuration Candidates* chỉ rõ ví dụ chính thức `com.example.Outer$NestedAutoConfiguration`.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getName()` trả binary name của class, `getCanonicalName()` trả canonical name khi có.
- [Java Language Specification `13.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.1): quy tắc binary name của member class.
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): cơ chế nhận candidate, điều kiện và khả năng cấu hình người dùng thay thế default.

**Ghi nhớ:** `Outer.Nested` là cách tham chiếu tự nhiên trong **Java source**; `Outer$Nested` là cách định danh nested member class trong **binary name**. Với `AutoConfiguration.imports` của Spring Boot 3.x, hãy ghi **binary name**, đóng gói đúng classfile/tài nguyên rồi kiểm tra riêng việc candidate được tìm thấy và việc bean có được tạo hay không.
