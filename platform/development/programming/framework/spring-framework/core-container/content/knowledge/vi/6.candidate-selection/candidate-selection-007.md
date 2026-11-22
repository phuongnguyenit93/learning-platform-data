# Tên tham số, tên bean và vai trò của tùy chọn biên dịch `-parameters` trong Spring

## 1. Tại sao tên tham số có thể quyết định bean được tiêm?

Trong Spring Core Container, **một injection point thường được xác định đầu tiên theo Java type**, chẳng hạn constructor cần một `Gateway`. Nếu có hai beans `emailGateway` và `smsGateway` cùng implement `Gateway`, việc chỉ nhìn type sẽ không đủ để chọn một đối tượng.

Spring có những quy tắc chọn ứng viên: **qualifier**, **primary/fallback**, generic type, tên field/tên tham số và các metadata khác. Trong trường hợp có nhiều ứng viên cùng type, **không có chỉ dẫn chọn khác đang ưu tiên**, Spring có thể so **tên của injection point** với **bean name hoặc alias**, rồi dùng ứng viên trùng tên.

Ví dụ:

~~~java
// Snippet bên trong một bean được Spring quản lý:
OrderService(Gateway smsGateway) {
    this.gateway = smsGateway;
}
~~~

Giả sử tồn tại hai beans:
- `emailGateway`, kiểu `Gateway`;
- `smsGateway`, cũng kiểu `Gateway`.

Nếu Spring có thể nhìn thấy **tên tham số Java thật là `smsGateway`**, nó có thể dùng tên ấy như dấu hiệu phân giải và tiêm bean `smsGateway`. Nhưng JVM **không bảo đảm giữ được tên tham số gốc cho reflection** sau mọi kiểu biên dịch. Đây chính là lý do cần hiểu tùy chọn **`javac -parameters`**.

### Ba khái niệm không được trộn lẫn

| Khái niệm | Ví dụ | Nơi phát sinh | Vai trò |
| --- | --- | --- | --- |
| **Tên bean** | `smsGateway` | Spring registration qua `@Bean`, `@Component`, XML, aliases | Định danh bean trong IoC Container |
| **Tên tham số Java** | `smsGateway` trong `OrderService(Gateway smsGateway)` | Chữ ký source Java, tùy compilation metadata | Spring có thể dùng khi chọn bean cùng type |
| **Tên field Java** | `private Gateway smsGateway;` | Khai báo field và thông tin field reflection | Spring có thể xem tên field cho field injection |

**`-parameters` liên quan tới metadata tên tham số của constructor/method**, chứ **không đổi tên bean**, không thêm `@Qualifier`, và **không biến tên field thành tên tham số**. Tên field có đường reflection riêng nên không cần `-parameters` để đọc chính tên field.

Mục tiêu bài học: xác định bean names đến từ đâu, Spring dùng tên của injection point khi nào, công dụng và giới hạn của `javac -parameters`, cách bật đúng trong Maven/IDE, phương pháp debug và kiểm chứng qua **Java 17 + Spring Framework 7.0.9**.

## 2. Bean name lấy từ đâu?

Spring quản lý các bean definitions bằng **bean name** trong một container. Tên này không nhất thiết là tên Java class hay tên biến mà bạn đặt trong business code.

### 2.1. `@Bean` mặc định lấy tên method

~~~java
@Configuration(proxyBeanMethods = false)
class GatewayConfig {
    @Bean
    Gateway emailGateway() {
        return new EmailGateway();
    }
}
~~~

Nếu không chỉ định tên tường minh, method `emailGateway()` thường đăng ký bean tên **`emailGateway`**. Class instance bên trong có thể là `EmailGateway` nhưng điều đó **không tự đổi bean name** thành `EmailGateway`.

Có thể đặt tên khác với method:

~~~java
@Bean("smsGateway")
Gateway createSmsChannel() {
    return new SmsGateway();
}
~~~

Method Java là `createSmsChannel`, nhưng bean name chính là **`smsGateway`** vì đã khai báo tường minh. Nếu injection point cần tên `smsGateway`, phải so với **bean name thực**, không được suy ra từ tên method hay concrete class.

### 2.2. Alias không tạo object mới

~~~java
@Bean(name = {"smsGateway", "oldSmsGateway"})
Gateway createSmsChannel() {
    return new SmsGateway();
}
~~~

Tên đầu thường là tên chính; tên còn lại là **alias** trỏ tới cùng bean. `getBean("oldSmsGateway")` và `getBean("smsGateway")` trong cùng context thường trả cùng reference với singleton mặc định. Một điểm inject có tên **`oldSmsGateway`** cũng có thể khớp thông qua alias.

### 2.3. `@Component` và naming strategy

~~~java
@Component("gatewayForTests")
class FakeGateway implements Gateway {
    // ...
}
~~~

Tại component scan phù hợp, bean name được chỉ rõ là `gatewayForTests`. Nếu không khai tên, Spring dùng tên được tạo bởi cơ chế naming strategy, thường dựa trên short class name theo quy ước. Quy tắc tên cho những class có chữ viết hoa bất thường, custom generator hoặc nested classes có thể khác; **hãy kiểm bean name thực**, đừng dựa vào đoán tên theo filename.

### 2.4. XML và chương trình đăng ký thủ công

~~~xml
<bean id="emailGateway" class="demo.EmailGateway"/>
<alias name="emailGateway" alias="primaryEmailGateway"/>
~~~

XML dùng `id/name` và aliases. API như `registerBean` cũng cho phép đặt tên khi đăng ký. **Bean names là metadata của container**, không phải thuộc tính được JVM gắn vào từng Java class.

**Lưu ý scope:** hai definitions có cùng bean class nhưng tên khác là **hai registrations**, có thể có instance/lifecycle/scope khác nhau. Còn alias không tạo registration thứ hai.

## 3. JVM lưu tên tham số Java như thế nào?

Java source:

~~~java
public ReportService(Gateway smsGateway, int retries) {
    // ...
}
~~~

Trong source, bạn nhìn thấy `smsGateway` và `retries`. Tuy nhiên, khi đọc method/constructor qua **Java Reflection**, tên tham số chỉ được bảo toàn dưới dạng metadata đáng tin cậy khi compiler được yêu cầu ghi nó.

Với **JDK 8+**, tùy chọn:

~~~bash
javac -parameters ReportService.java
~~~

yêu cầu Java compiler ghi **`MethodParameters` attribute** chứa parameter names vào `.class` file. Reflection có thể truy cập bằng `java.lang.reflect.Parameter.getName()` và kiểm tra `Parameter.isNamePresent()`.

Nếu **không** có metadata này, reflection thường báo các tên tổng hợp như `arg0`, `arg1`, kèm `isNamePresent() == false`. Các tên ấy **không phải tên tham số khai báo ban đầu** để Spring dựa vào như fallback bean-name matching.

| Khía cạnh | Biên dịch với `-parameters` | Không có `-parameters` |
| --- | --- | --- |
| Java bytecode chạy ứng dụng | Hoạt động | Hoạt động |
| Method/constructor parameters có metadata tên source | Có, cho code được compile với flag | Thường không |
| Reflection `getName()` | Ví dụ `smsGateway` | Thường là `arg0` |
| Reflection `isNamePresent()` | `true` | `false` |
| Spring suy luận tên tham số cho matching theo name | Có cơ sở metadata | Không nên dựa vào cơ chế này |
| `@Qualifier` explicit | Vẫn hoạt động khi bean/qualifier hợp lệ | Vẫn hoạt động, không phụ thuộc tên source |
| `@Primary` | Vẫn có tác dụng khi phù hợp | Vẫn có tác dụng |
| Java field names qua reflection | Vẫn có | Vẫn có |

**`-parameters` khác `-g`:** `-g` sinh thông tin debug như line/local-variable data; nó **không thay thế** `MethodParameters` cho parameter-name discovery trong Spring Framework 6.1+. Cũng không nhầm `-parameters` với JVM runtime option: đây là **tùy chọn lúc biên dịch**, không phải đối số của lệnh `java`.

## 4. Từ Spring 6.1: parameter-name discovery cần metadata đúng

Tài liệu Spring Framework và ghi chú nâng cấp xác nhận: **từ Spring Framework 6.1**, hỗ trợ suy luận tên tham số qua cách đọc **Local Variable Table** trong bytecode đã bị loại bỏ. Vì thế nếu ứng dụng dựa vào constructor/factory-method parameter names để chọn bean, hãy compile Java với **`-parameters`**.

Trước đó, một số trường hợp từng hoạt động nhờ debug information dù không bật flag. Sau nâng cấp lên 6.1/6.2/7.x, ứng dụng có thể gặp lỗi autowiring kiểu “multiple beans of type...” vì Spring không còn biết `smsGateway` là tên thật của tham số.

Từ **Spring 6.2**, trong trường hợp tên tham số trùng bean name và không có các quy tắc type/qualifier/primary/fallback khác ghi đè lựa chọn, Spring có thể dùng **fast shortcut resolution** cho name match. Đây là **tối ưu hóa**, không phải một thay đổi biến Spring thành hệ thống luôn chọn theo tên trước type.

Cần phát biểu chính xác:

- `@Autowired` vẫn là **type-driven dependency injection**.
- Tên tham số/field là **một dấu hiệu phân giải dự phòng** trong những tình huống đủ điều kiện.
- Primary, qualifiers, fallback và generic metadata có thể khiến một bean trùng tên **không** được chọn.
- **Tên phải tương thích với type**; bean name không thể làm một object sai Java type trở nên assignable.
- Một dependency cần **một bean** có thể lỗi khi không còn cách chọn giữa nhiều candidates; việc có `-parameters` không bảo đảm mọi trường hợp sẽ resolve được.
- Để yêu cầu bean một cách **rõ ràng và bền vững trước refactor**, dùng `@Qualifier` hoặc `@Primary` theo đúng ý nghĩa hợp đồng.

## 5. Quy trình chọn ứng viên và thứ tự ưu tiên cần hiểu

Khi Spring cần giải quyết:

~~~java
@Autowired
void configure(Gateway smsGateway) {
    // ...
}
~~~

Quy trình **khái niệm**:

~~~text
Injection point: Gateway smsGateway
                 |
                 v
      Tìm beans compatible với Gateway
                 |
                 v
   Lọc autowire candidates + qualifiers
                 |
                 v
   Có single candidate đã rõ không?
                 |
       Có điều kiện ưu tiên khác?
       /                    \
   Có primary/qualifier      Không có quy tắc
   hay fallback hợp lệ       ưu tiên override
       |                         |
       v                         v
    Chọn theo                 Có tên field hoặc
   metadata đó               tên parameter thật?
                                  |
                            Có bean trùng tên?
                             /           \
                           Có           Không
                            |               |
                            v               v
                     Xét candidate      Các bước resolution
                      trùng tên         còn lại hoặc lỗi
~~~

Sơ đồ chỉ dùng để tư duy; thuật toán nội bộ còn có các nhánh: dependency name shortcut, priority, default-candidate, tự tham chiếu (self reference), generic types, alias, `ObjectProvider`, collections và nhiều cơ chế đặc biệt.

**Những ví dụ phân biệt cụ thể:**

| Tình huống | Bean được chọn/thất bại |
| --- | --- |
| Hai `Gateway` là emailGateway và smsGateway, param `Gateway smsGateway`, có `-parameters`, không primary/qualifier | Có thể chọn **smsGateway** nhờ tên trùng |
| Hai beans cùng type, param `Gateway arbitraryName` và không có rule khác | Có thể báo ambiguity |
| Hai beans cùng type, emailGateway `@Primary`, param `Gateway smsGateway` | Thông thường chọn **emailGateway** (primary ưu tiên) |
| Param `@Qualifier("smsGateway") Gateway emailGateway` | Chọn **smsGateway** vì qualifier hợp lệ, dù tên param khác |
| `Gateway oldSmsGateway`, bean smsGateway có alias oldSmsGateway | Có thể chọn **smsGateway** qua alias |
| Param yêu cầu `SmsGateway`, bean trùng tên nhưng chỉ có type `EmailGateway` | Không tự vượt qua kiểm tra type |
| Chỉ có một candidate Gateway | Không cần dựa vào tên tham số |
| `List<Gateway>` thay vì `Gateway` | Có thể inject nhiều candidates, không dùng name matching để chọn đúng một |

**Cẩn trọng với names của tham số `@Bean`:** Code bên dưới dùng method factory `nameSelection(Gateway smsGateway,...)`, nên tên method được đăng ký là `nameSelection`, **không phải** tên tham số `smsGateway`. Spring resolve các tham số lúc gọi factory method rồi tạo object được trả về.

## 6. Cấu hình Maven để giữ tên tham số

Một dự án Maven sử dụng Java 17 và Spring Framework 7.0.9 có thể bật:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <maven.compiler.parameters>true</maven.compiler.parameters>
</properties>
~~~

Thuộc tính **`maven.compiler.parameters=true`** được Maven Compiler Plugin hỗ trợ; nó yêu cầu `javac` sinh reflection metadata tương ứng `-parameters`. Không cần thêm annotation processor riêng để Spring autowiring hoạt động: đây là compiler metadata, còn IoC xử lý injection ở runtime.

Cũng có thể cấu hình trực tiếp trong plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

**Chọn một nguồn cấu hình nhất quán** trong project thật. Ví dụ runnable ở mục 7 dùng **properties**, không lặp cấu hình parameters trong plugin. Khi dùng Gradle, IDE build hoặc `javac` thủ công, phải thiết lập flag ở **compiler thực sự tạo `.class`**, không chỉ thêm thuộc tính Maven trong một file không được build tool đó sử dụng.

### Xác minh đã bật flag thật sự

- Chạy `mvn -q clean compile` để xóa các class artifacts cũ rồi compile.
- Dùng `java.lang.reflect.Executable.getParameters()` và `Parameter.isNamePresent()` để xác nhận.
- Có thể dùng `javap -v -p` inspect class và tìm **`MethodParameters`**, khác với `LocalVariableTable`.
- Khi đổi IDE compiler settings, hãy **clean/rebuild**; đừng dựa vào class file từ lần build cũ.

**Cần kiểm tra cả compile và testCompile** nếu tests cũng có factory methods/constructor parameter naming; Maven Compiler Plugin hỗ trợ property cho các compilation goals. Nếu một module được build bởi hệ khác, property Maven của module bên cạnh không tự áp dụng.

## 7. Dự án runnable Spring 7.0.9 + Java 17

Demo có ba context độc lập và một bước Reflection:

1. **NameConfig không có `@Primary`:** có emailGateway và smsGateway (alias `oldSmsGateway`); một factory method nhận tham số **`Gateway smsGateway`** không gắn qualifier → Spring chọn **SMS** nhờ parameter name. Một tham số khác có `@Qualifier("emailGateway")` → chọn EMAIL bất kể tên `preferred`.
2. **AliasSelection** nhận `Gateway oldSmsGateway` → fallback name match alias → SMS. **FieldSelection** có field `@Autowired Gateway smsGateway` → chọn SMS theo **field name**, không cần `-parameters` để biết tên field.
3. **PrimaryConfig:** emailGateway được `@Primary`; tham số tên `smsGateway` vẫn nhận **EMAIL**. Tham số tên `emailGateway` có `@Qualifier("smsGateway")` lại nhận **SMS**.
4. **AmbiguousConfig:** hai beans cùng type, injection parameter tên `unknownGateway` không khớp bean name/alias, không có primary/qualifier → container không thể resolve một bean duy nhất; lỗi được catch.
5. **Java Reflection:** chương trình in tên tham số thực và `isNamePresent()` để xác nhận `-parameters` trên lớp vừa compile.

Không dùng Spring Boot, web server, database hoặc network call.

### 7.1. Tổ chức files

~~~text
parameter-names-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ParameterNamesDemo.java
~~~

Yêu cầu **JDK 17+**, Maven **3.9+**, có thể tải `spring-context` khi lần đầu build.

### 7.2. `pom.xml` đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>parameter-names-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.compiler.parameters>true</maven.compiler.parameters>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ParameterNamesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là cấu hình **bắt buộc đối với đúng expected output của demo**: tên tham số trong method `@Bean` phải được giữ. `maven.compiler.parameters` được dùng để Maven Compiler Plugin chuyển tương đương `-parameters` xuống `javac`.

### 7.3. `src/main/java/demo/ParameterNamesDemo.java` đầy đủ

~~~java
package demo;

import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.Arrays;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

public final class ParameterNamesDemo {
    private ParameterNamesDemo() {
    }

    @FunctionalInterface
    interface Gateway {
        String id();
    }

    static final class NameSelection {
        private final Gateway byParameterName;
        private final Gateway byQualifier;

        NameSelection(Gateway byParameterName, Gateway byQualifier) {
            this.byParameterName = byParameterName;
            this.byQualifier = byQualifier;
        }

        String paramId() {
            return byParameterName.id();
        }

        String qualifierId() {
            return byQualifier.id();
        }
    }

    static final class AliasSelection {
        private final Gateway gateway;

        AliasSelection(Gateway gateway) {
            this.gateway = gateway;
        }

        String id() {
            return gateway.id();
        }
    }

    static final class FieldSelection {
        @Autowired
        private Gateway smsGateway;

        String id() {
            return smsGateway.id();
        }
    }

    static final class PrimarySelection {
        private final Gateway byName;
        private final Gateway byQualifier;

        PrimarySelection(Gateway byName, Gateway byQualifier) {
            this.byName = byName;
            this.byQualifier = byQualifier;
        }

        String namedArgumentId() {
            return byName.id();
        }

        String qualifiedId() {
            return byQualifier.id();
        }
    }

    static final class AmbiguousSelection {
        AmbiguousSelection(Gateway gateway) {
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class NameConfig {
        @Bean("emailGateway")
        public Gateway emailGateway() {
            return () -> "EMAIL";
        }

        @Bean(name = {"smsGateway", "oldSmsGateway"})
        public Gateway smsGatewayFactory() {
            return () -> "SMS";
        }

        @Bean
        public NameSelection nameSelection(
                Gateway smsGateway,
                @Qualifier("emailGateway") Gateway preferred) {
            return new NameSelection(smsGateway, preferred);
        }

        @Bean
        public AliasSelection aliasSelection(Gateway oldSmsGateway) {
            return new AliasSelection(oldSmsGateway);
        }

        @Bean
        public FieldSelection fieldSelection() {
            return new FieldSelection();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class PrimaryConfig {
        @Bean("emailGateway")
        @Primary
        public Gateway emailGateway() {
            return () -> "EMAIL";
        }

        @Bean("smsGateway")
        public Gateway smsGateway() {
            return () -> "SMS";
        }

        @Bean
        public PrimarySelection primarySelection(
                Gateway smsGateway,
                @Qualifier("smsGateway") Gateway emailGateway) {
            return new PrimarySelection(smsGateway, emailGateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AmbiguousConfig {
        @Bean("emailGateway")
        public Gateway emailGateway() {
            return () -> "EMAIL";
        }

        @Bean("smsGateway")
        public Gateway smsGateway() {
            return () -> "SMS";
        }

        @Bean
        public AmbiguousSelection ambiguousSelection(Gateway unknownGateway) {
            return new AmbiguousSelection(unknownGateway);
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Method factory = NameConfig.class.getDeclaredMethod(
                "nameSelection", Gateway.class, Gateway.class);
        Parameter parameter = factory.getParameters()[0];
        System.out.println("reflection.name=" + parameter.getName());
        System.out.println("reflection.present=" + parameter.isNamePresent());

        try (var context =
                new AnnotationConfigApplicationContext(NameConfig.class)) {
            var named = context.getBean(NameSelection.class);
            var alias = context.getBean(AliasSelection.class);
            var field = context.getBean(FieldSelection.class);

            System.out.println("name.selected=" + named.paramId());
            System.out.println("name.qualified=" + named.qualifierId());
            System.out.println("alias.selected=" + alias.id());
            System.out.println("field.selected=" + field.id());
            String[] beanNames = context.getBeanNamesForType(Gateway.class);
            Arrays.sort(beanNames);
            System.out.println("names=" + String.join(",", beanNames));
            System.out.println("alias.same="
                    + (context.getBean("oldSmsGateway")
                       == context.getBean("smsGateway")));
        }

        try (var context =
                new AnnotationConfigApplicationContext(PrimaryConfig.class)) {
            var primary = context.getBean(PrimarySelection.class);
            System.out.println("primary.namedArgument="
                    + primary.namedArgumentId());
            System.out.println("primary.qualified=" + primary.qualifiedId());
        }

        try (var context =
                new AnnotationConfigApplicationContext(AmbiguousConfig.class)) {
            System.out.println("ambiguous.unexpected");
        } catch (BeansException expected) {
            System.out.println("ambiguous.failed=true");
        }
    }
}
~~~

**Giải thích:**
- `getDeclaredMethod(...)` truy vấn factory method hai tham số có type `Gateway`. Tên thật tham số đầu phải là **`smsGateway`** vì POM bật `-parameters`; Reflection `isNamePresent()` phải `true`.
- `NameConfig` đăng ký hai Gateway beans. `nameSelection(Gateway smsGateway, ...)` thiếu qualifier ở tham số đầu, nên **name matching** có thể phân giải type ambiguity thành SMS.
- Tham số `preferred` có **`@Qualifier("emailGateway")`** nên chọn EMAIL; tên param `preferred` không ảnh hưởng.
- `oldSmsGateway` là alias của `smsGateway`. Parameter `Gateway oldSmsGateway` có tên khớp alias nên chọn SMS.
- Field `@Autowired Gateway smsGateway` cũng chọn SMS vì field name; **tên field vẫn có ngay cả khi compiler không bật `-parameters`**.
- Trong `PrimaryConfig`, tham số tên `smsGateway` chọn **EMAIL** nhờ `@Primary` hợp lệ, chứng minh primary có thể thắng name fallback. Tham số `@Qualifier("smsGateway") Gateway emailGateway` lại chọn SMS.
- `AmbiguousConfig` cố ý không có primary/qualifier và param `unknownGateway` không match bean name; context tạo eager singleton bị từ chối, demo bắt `BeansException` và in một dòng.
- Mỗi context độc lập, nên các beans cùng tên trong configs khác **không đè lên nhau**.

**Hạn chế có chủ ý:** chương trình không sửa Java bytecode hay chạy compile thiếu `-parameters` tại runtime, bởi compiler options chỉ thay đổi được lúc build. Phép đối chứng bật/tắt thực hiện **ở ví dụ Java Reflection độc lập tại mục 9**.

## 8. Chạy Maven và expected stdout

Đứng trong thư mục `parameter-names-demo` chứa POM:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

Các lệnh `java -version`/`javac -version`/`mvn -version` có output theo môi trường; không có stdout cố định. Maven sẽ compile Java 17 với `-parameters`, rồi chạy class `demo.ParameterNamesDemo` và các Spring contexts.

**11 dòng stdout do application chủ động in** (không tính log/exception diagnostics của Maven hoặc Spring):

~~~text
reflection.name=smsGateway
reflection.present=true
name.selected=SMS
name.qualified=EMAIL
alias.selected=SMS
field.selected=SMS
names=emailGateway,smsGateway
alias.same=true
primary.namedArgument=EMAIL
primary.qualified=SMS
ambiguous.failed=true
~~~

**Những điểm cần xác nhận khi chạy:**

| Output | Ý nghĩa |
| --- | --- |
| `reflection.name=smsGateway` | Java compiler đã giữ tên tham số thật |
| `reflection.present=true` | Reflection đọc được metadata `MethodParameters` |
| `name.selected=SMS` | Name fallback chọn bean trùng parameter name khi không có primary/qualifier |
| `name.qualified=EMAIL` | Qualifier explicit không phụ thuộc tên tham số |
| `alias.selected=SMS` | Name fallback có thể match alias |
| `field.selected=SMS` | Tên field cũng dùng được cho fallback matching |
| `names=emailGateway,smsGateway` | Alias không trở thành bean definition thứ ba |
| `primary.namedArgument=EMAIL` | Primary có thể được ưu tiên hơn tên tham số |
| `primary.qualified=SMS` | Qualifier lọc candidates, chọn SMS dù param tên khác |
| `ambiguous.failed=true` | Không có rule để chọn một bean nên Spring báo failure |

**Chú ý log ngoài stdout:** Khi `AmbiguousConfig` thất bại tại `refresh()`, Spring có thể in warning/stack trace qua logger. Expected stdout ở đây chỉ tính những dòng từ `System.out.println` của chương trình. Không kiểm tra exact text của exception cause/stack trace vì chúng thay đổi theo phiên bản/launch context.

## 9. Java 17 thuần: đối chiếu có và không có `-parameters`

Tạo file riêng **`ParameterReflectionDemo.java`** tại một thư mục ví dụ không phụ thuộc Maven/Spring:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterReflectionDemo {
    static void configure(String emailGateway, int retries) {
    }

    public static void main(String[] args) throws Exception {
        Method method = ParameterReflectionDemo.class.getDeclaredMethod(
                "configure", String.class, int.class);
        for (Parameter parameter : method.getParameters()) {
            System.out.println("name=" + parameter.getName()
                    + ",present=" + parameter.isNamePresent());
        }
    }
}
~~~

### Biên dịch **có** lưu tên tham số

~~~bash
javac -parameters ParameterReflectionDemo.java
java ParameterReflectionDemo
~~~

Stdout chính xác với JDK 17:

~~~text
name=emailGateway,present=true
name=retries,present=true
~~~

### Biên dịch **không** lưu tên tham số

Biên dịch lại **cùng file**, ghi đè `ParameterReflectionDemo.class` bằng lệnh dưới (không giữ class file cũ từ bước trước):

~~~bash
javac ParameterReflectionDemo.java
java ParameterReflectionDemo
~~~

Stdout chính xác theo Java Reflection khi không có `MethodParameters` tên nguồn:

~~~text
name=arg0,present=false
name=arg1,present=false
~~~

**Dấu hiệu kỹ thuật:** `isNamePresent=false` chứng minh Reflection đang thấy tên tổng hợp, không phải `emailGateway`/`retries`. Hai lần chạy tạo cùng **hành vi method**, chỉ khác metadata phục vụ reflection/frameworks. Tên biến địa phương bên trong method không được tự bảo toàn chỉ vì bật `-parameters`.

Có thể quan sát class bằng:

~~~bash
javap -v -p ParameterReflectionDemo.class
~~~

và tìm phần **`MethodParameters`**. Với lần compile có flag, attribute mang tên `emailGateway` và `retries`; với lần không flag, metadata tên này không có. Nếu bạn vừa chuyển công cụ biên dịch, hãy clean/rebuild để tránh đọc nhầm class artifacts.

### Windows PowerShell, cmd và Linux

Các lệnh `javac` và `java` ở trên dùng được trong PowerShell, Command Prompt và shell Linux/macOS nếu `JAVA_HOME`/`PATH` đúng. Không dùng `export JAVA_TOOL_OPTIONS` hay lệnh đặt biến môi trường hệ điều hành để bật `-parameters`: flag thuộc **`javac`**, phải truyền ở compile step.

## 10. Lỗi thường gặp và cách debug

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Java Reflection báo `arg0`/`isNamePresent=false` | Class biên dịch thiếu `-parameters` | Bật flag trong tool biên dịch thực tế, clean compile |
| Spring 6.1+ trước chạy ổn, nâng version thì `NoUniqueBeanDefinitionException` | Từng dựa vào LocalVariableTable/debug symbols cho parameter names | Compile `-parameters`, hoặc dùng qualifier rõ ràng |
| Bật property Maven nhưng chạy trong IDE vẫn không chọn bean theo param name | IDE compiler không sử dụng config Maven, output class cũ | Xem build delegation/compiler args, clean rebuild và kiểm Reflection |
| Có `@Bean smsGateway()` nhưng Spring lại thấy tên khác | `@Bean(name=...)` override default method name hoặc naming strategy | Kiểm bean names thực qua `getBeanNamesForType` |
| Parameter tên khớp nhưng bean sai type | Name không thay được Java assignability | Sửa contract type, return type hoặc bean registrations |
| Bean `@Primary` được chọn dù tham số mang tên bean khác | Primary là selection rule hợp lệ | Dùng qualifier nếu use case đòi bean cụ thể |
| `@Qualifier("smsGateway")` chọn SMS dù param tên khác | Qualifier đang lọc candidates như thiết kế | Không nhầm name fallback với explicit qualifier |
| Không có bean trùng tên param, nhưng chỉ có một candidate | Dependency vẫn có thể resolve theo type | `-parameters` không bắt buộc cho mọi injection |
| Constructor có nhiều parameters cùng type | Từng param cần resolution độc lập; có thể phải dùng qualifier | Đặt tên có nghĩa, giữ metadata và thêm qualifier khi cần |
| Alias xuất hiện trong `getBeanNamesForType`? | Type discovery liệt kê bean names, alias không phải bean mới | So `getAliases(name)` và `containsBeanDefinition` |
| Đặt `-parameters` vào command `java` | Sai giai đoạn | Đặt vào `javac` hoặc Maven Compiler Plugin |
| Bật `-g` mà Spring vẫn không biết param name | Debug info không còn là fallback trong Spring 6.1+ | Dùng `-parameters` |
| Đổi tên tham số khiến wiring đổi | Đang phụ thuộc vào name fallback ngầm | Dùng `@Qualifier` hoặc policy `@Primary` rõ hơn |
| Field name có sẵn nhưng constructor name mất | Field reflection khác parameter-name metadata | Xem `Parameter.isNamePresent()`, không dựa vào field test |
| `NoUniqueBeanDefinitionException` khi có nhiều candidates | Không đủ selector theo injection point | Kiểm type, qualifier, primary/fallback, name/alias |
| App startup fail dù đã compile đúng flag | Có thể còn lỗi DI thật hoặc business config | Đọc root cause, kiểm registrations/context/bean types |

### Checklist chẩn đoán theo thứ tự

1. Xác nhận **đúng `ApplicationContext`** và bean registrations; in tên bằng `getBeanNamesForType(RequiredType.class)`.
2. Kiểm **type compatibility**, xem declared `@Bean` return types, generic qualifications và proxy nếu liên quan.
3. Kiểm point có **`@Qualifier`**, `@Primary`, `@Fallback`, `autowireCandidate` hay rule khác không.
4. Nếu đang dựa vào tên, xác định **field name hoặc method/constructor parameter name** chính xác và bean name/alias tương ứng.
5. Dùng **Reflection `isNamePresent()`** kiểm tra tên method/constructor parameters.
6. Đối chiếu `maven.compiler.parameters`, IDE compiler flags, toolchains và rebuild outputs.
7. Không tự sửa một bean thành primary chỉ để che sai cấu hình khi thực sự muốn chọn một implementation cụ thể.

## 11. Khi nào nên dựa vào tên tham số, khi nào nên dùng qualifier?

**Tên tham số có thể là fallback thuận tiện** khi nhiều beans cùng type và tên injection point có ý nghĩa tự nhiên. Nó giúp giảm annotation lặp và Spring 6.2+ có thể tối ưu resolution trong những trường hợp đơn giản. Nhưng nó vẫn là **hợp đồng phụ thuộc vào chữ ký source + compile metadata + quy tắc candidate selection**.

Cân nhắc dùng `@Qualifier` khi:
- Use case yêu cầu **một implementation cụ thể** dù bean khác được primary.
- Việc đổi tên param khi refactor không nên âm thầm đổi wiring.
- Nhiều beans cùng type thể hiện **vai trò** khác nhau, như `primaryGateway`, `auditGateway`.
- Việc gọi bean qua alias/name là policy đáng được mô tả rõ trong code review và integration tests.

Dùng `@Primary` khi thật sự có một **mặc định chung** hợp lý cho injection đơn, không phải khi mọi use case cần được gắn qualifier dài dòng.

Dùng `@Resource(name="...")` ở field/setter nếu yêu cầu là **tra cứu by-name** theo semantic Jakarta injection. Đây là cơ chế khác với `@Autowired` (type-driven) và không nên coi hai cách như các alias hoàn toàn tương đương.

**Ưu tiên constructor injection** cho dependency bắt buộc, để object hợp lệ ngay từ lúc tạo; dù dùng constructor, bạn vẫn có thể đặt `@Qualifier` lên tham số constructor nếu cần. Điều này không phụ thuộc vào việc class có setter hoặc field annotation.

## 12. Bài tập kiểm chứng từng quy tắc

Thực hiện mỗi thí nghiệm **trên một bản sao code**, khôi phục project gốc giữa các lần để expected stdout mục 8 còn nguyên.

1. **Bỏ `maven.compiler.parameters=true`** và clean rebuild. Dự đoán `reflection.present=false` và context `NameConfig` có thể fail vì thiếu parameter-name matching.
2. **Bật lại `-parameters`**; xác nhận Reflection trả đúng `smsGateway`, `name.selected=SMS`.
3. **Đổi tên tham số** `Gateway smsGateway` thành `Gateway gateway` mà không đổi beans. Dự đoán ambiguity ở context không có primary/qualifier.
4. **Giữ tên param sai nhưng thêm `@Qualifier("smsGateway")`**; dự đoán vẫn chọn SMS.
5. **Thêm `@Primary` cho emailGateway trong NameConfig**; dự đoán param tên smsGateway nhận EMAIL nếu không có qualifier.
6. **Đổi `@Qualifier("emailGateway")` thành `@Qualifier("smsGateway")`**; output qualified đổi sang SMS dù tên param là preferred.
7. **Đổi bean name tường minh** thành `@Bean("phoneGateway")`; xem field/parameter names cần cập nhật ra sao, hoặc phải thêm alias để tương thích.
8. **Xóa alias `oldSmsGateway`**; dự đoán injection theo tham số oldSmsGateway không còn có đường name matching, có thể fail khi có nhiều beans.
9. **Tên field không phụ thuộc `-parameters`:** sau khi bỏ flag, tạo một context chỉ đăng ký FieldSelection với Gateway beans; field smsGateway vẫn có thể resolve theo tên field.
10. **Không có ambiguity:** chỉ đăng ký một Gateway bean, dùng param `Gateway arbitraryName` và xem type injection không cần parameter-name fallback.
11. **Hai qualifiers:** tạo các bean có nhiều qualifier labels, thử injection point với selector minh bạch, không dựa vào raw parameter name.
12. **Reflection:** thử `javac -g` nhưng không `-parameters`; kiểm `isNamePresent()` và `MethodParameters`.
13. **Maven vs IDE:** biên dịch cùng source bằng hai công cụ, so output `Parameter.isNamePresent()` để phát hiện build path khác.
14. **Spring 6.2 fast path:** giải thích khi nào tối ưu name match áp dụng và vì sao `@Primary`/`@Qualifier` có thể làm đường tắt không áp dụng.
15. **Test wiring:** viết integration test với hai Gateway beans, assert đối tượng nhận bean đúng; viết unit test service bằng constructor fake để tách nghiệp vụ khỏi Spring.
16. **Generic types:** thử các beans `Store<String>` và `Store<Integer>` với param names giống bean names khác nhưng type generic không khớp; xác nhận tên không phá type filtering.

### Checklist hiểu bài

- [ ] Phân biệt **bean name**, **method/constructor parameter name**, **field name** và **alias**.
- [ ] Biết `@Bean` mặc định đặt tên theo method, hoặc dùng `@Bean(name=...)` để đặt tường minh.
- [ ] Hiểu `javac -parameters` sinh `MethodParameters` cho Java Reflection.
- [ ] Biết `Parameter.getName()`/`isNamePresent()` xác minh compiler metadata.
- [ ] Biết Spring 6.1+ không còn LocalVariableTable parameter-name fallback.
- [ ] Biết Spring 6.2+ có name-matching fast shortcut trong những trường hợp phù hợp.
- [ ] Không suy luận name fallback thắng `@Primary` hoặc `@Qualifier`.
- [ ] Biết field name không phụ thuộc `-parameters` giống tên tham số.
- [ ] Cấu hình Maven `maven.compiler.parameters=true`, clean compile, check IDE compiler.
- [ ] Chạy được **11 dòng stdout Spring demo** và hai kết quả Java Reflection có/không flag.
- [ ] Dùng qualifier/primary theo policy rõ khi dependency quan trọng.

## 13. Kết luận và tài liệu chính thức

**Tóm tắt:** Tên tham số có thể giúp Spring chọn bean trùng tên khi nhiều beans cùng type, nhưng đây là **một phần của dependency resolution**, không phải nguyên tắc “luôn tiêm theo tên”. Để Spring đọc đúng tên tham số của constructor/`@Bean` method từ Java class files, hãy bật `javac -parameters` (hoặc `maven.compiler.parameters=true`). Từ Spring 6.1, dựa vào debug symbols `-g` để cứu thiếu parameter names không còn phù hợp; từ 6.2, name match có thể có đường tắt xử lý trong trường hợp không bị các rule khác ghi đè.

Nguồn chính thức:
- [Spring Framework — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework — Primary and Fallback](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [Spring Framework — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Spring Framework — Bean Definition Naming](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
- [Spring Framework — 6.x Upgrade Notes / Parameter Name Retention](https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x)
- [Maven Compiler Plugin — compile mojo (`parameters` option)](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Java 17 — java.lang.reflect.Parameter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html)
- [Oracle javac `-parameters` option](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)

**Ghi nhớ để debug:** Hãy kiểm tra **type → qualifiers/primary/fallback → parameter/field name → bean name/alias → compiler metadata**. Nếu bean name trùng parameter mà Spring vẫn không chọn, hãy hỏi trước tiên: *đã biên dịch với `-parameters` và có rule chọn ứng viên khác ưu tiên hơn chưa?*