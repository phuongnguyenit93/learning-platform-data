# Khai báo annotation processor phù hợp trong Gradle hoặc Maven cho Spring Boot

## 1. Annotation processor tạo ra thứ gì?

Khi một thư viện hoặc ứng dụng Spring Boot công bố cấu hình bằng `@ConfigurationProperties`, IDE có thể gợi ý tên property, kiểu dữ liệu, giá trị mặc định và mô tả khi người dùng viết `application.yml` hoặc `application.properties`. Để tạo dữ liệu hỗ trợ này, Spring Boot cung cấp artifact:

~~~text
org.springframework.boot:spring-boot-configuration-processor
~~~

Artifact chứa một **Java annotation processor**. Trong lúc biên dịch source, processor đọc metadata của các class/method được đánh dấu `@ConfigurationProperties` và sinh file:

~~~text
META-INF/spring-configuration-metadata.json
~~~

File metadata mô tả cấu hình theo định dạng chuẩn của Spring Boot, để IDE, công cụ tài liệu và tooling khác có thể cung cấp completion/documentation.

Điểm cần phân biệt ngay:
- `@ConfigurationProperties` định nghĩa prefix và cấu trúc dữ liệu có thể bind.
- `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan` đăng ký bean properties trong Spring context.
- `spring-boot-configuration-processor` sinh **metadata phục vụ tooling** khi compile.

Processor **không đăng ký bean**, không thực hiện binding lúc ứng dụng chạy và không thay thế `@EnableConfigurationProperties`. Thiếu processor thường không làm ứng dụng mất khả năng đọc cấu hình; phần dễ thấy nhất là metadata không được sinh nên IDE thiếu gợi ý.

## 2. Chọn đúng dependency và đúng scope

Artifact cần khai báo là:

~~~text
org.springframework.boot:spring-boot-configuration-processor
~~~

Dùng phiên bản cùng dòng với Spring Boot mà project đang chạy, ví dụ project Boot 3.3 dùng processor 3.3.x. Nếu project đã áp dụng Spring Boot Gradle plugin hoặc Spring Boot dependency management/BOM, version thường được quản lý tập trung. Nếu không dùng dependency management, khai báo version rõ ràng hoặc import đúng Boot BOM.

**Đây là dependency phục vụ build.** Nó nên nằm trong processor path của compiler, không phải dependency runtime của ứng dụng.

| Build tool | Cấu hình nên dùng | Ý nghĩa |
| --- | --- | --- |
| Gradle Java | `annotationProcessor` | Đưa processor vào processor path của compile task |
| Maven compiler plugin hiện đại | `annotationProcessorPaths` | Khai báo rõ processor path của compiler |
| Maven theo cấu hình dependency optional truyền thống | Dependency `optional=true` | Cho phép compiler phát hiện processor mà không truyền dependency này xuống consumer |

Không dùng `implementation` hoặc `compileOnly` như một cách thay thế tùy tiện cho `annotationProcessor` trong Gradle. `implementation` đưa thư viện vào compile/runtime classpath; `compileOnly` chỉ làm dependency hiện diện ở compile classpath nhưng không nói rõ processor path. Cấu hình chuyên biệt giúp build xác định processor nào được chạy.

## 3. Gradle Groovy DSL: cấu hình chuẩn

Với project Java dùng Gradle, thêm dependency trong `build.gradle`:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Nếu project dùng Spring Boot Gradle plugin hoặc dependency management plugin và Boot BOM đã được áp dụng, có thể không cần ghi version ở dòng dependency. Nếu không có BOM, ghi rõ version tương thích, ví dụ:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor:3.3.13'
}
~~~

Đừng khai báo processor là `implementation` chỉ để “IDE nhìn thấy” nó. Annotation processor được thực thi trong compile task, còn dependency `annotationProcessor` được giữ trong configuration riêng cho mục đích này.

### Gradle Kotlin DSL

Nếu build file là `build.gradle.kts`, cú pháp tương ứng:

~~~kotlin
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
~~~

Hai đoạn Gradle Groovy và Kotlin có cùng ý nghĩa. Dùng đúng cú pháp với loại build file hiện tại.

### Chỉ thêm vào module có source properties

Trong multi-module build, đặt processor ở module **thực sự biên dịch các class `@ConfigurationProperties`**. Ví dụ:

~~~text
root
├── app
├── acme-autoconfigure
└── acme-starter
~~~

Nếu `AcmeProperties.java` nằm trong module `acme-autoconfigure`, thêm `annotationProcessor` vào build file của module đó. Chỉ thêm ở root hoặc starter không bảo đảm processor chạy trong module chứa source. Mỗi module Java cần tạo metadata riêng cho source mà nó biên dịch.

## 4. Maven: khai báo processor path cho compiler

Với Maven Compiler Plugin 3.12.0 trở lên, có thể cấu hình processor tường minh qua `annotationProcessorPaths`. Ví dụ project Spring Boot 3.3.13, Java 17:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-configuration-processor</artifactId>
                        <version>3.3.13</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Trong ví dụ, version processor được đặt cùng dòng Spring Boot 3.3.13; khi nâng Spring Boot, hãy nâng version processor tương ứng. Nếu dùng `spring-boot-starter-parent` hoặc BOM, có thể tổ chức version management để không phải lặp version, nhưng cần chắc chắn Maven giải quyết được version cho processor path.

`annotationProcessorPaths` là danh sách riêng: nếu project dùng nhiều processor như Lombok hoặc MapStruct, thêm chúng vào cùng danh sách. Khi khai báo danh sách này, đừng giả định processor khác tự xuất hiện từ dependency thông thường trên classpath.

### Cách khai báo Maven optional theo tài liệu Spring Boot 3.3

Tài liệu Spring Boot 3.3 cũng mô tả cách khai báo processor là dependency optional:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-configuration-processor</artifactId>
        <optional>true</optional>
    </dependency>
</dependencies>
~~~

Cách này thường dùng trong project Maven cấu hình annotation processor theo cơ chế discovery của compiler. `optional=true` ngăn dependency processor bị truyền transitive như dependency thông thường tới ứng dụng tiêu thụ thư viện.

Với Maven compiler plugin hiện đại, **ưu tiên processor path tường minh** khi muốn build có thể dự đoán được trên các JDK mới. Chọn một cách cấu hình phù hợp với compiler/plugin hiện tại; tránh khai báo trùng lặp không cần thiết ở cả dependency discovery và processor path. Nếu project đang dùng compiler cũ theo hướng dẫn của Boot 3.3, có thể dùng dependency optional truyền thống và kiểm tra processor thực sự chạy trong compile.

## 5. Class properties mà processor có thể đọc

Ví dụ JavaBean:

~~~java
package com.acme.server;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.server")
public class ServerProperties {

    /**
     * Host name or IP address used by the server.
     */
    private String host = "127.0.0.1";

    /**
     * Port used by the embedded server.
     */
    private int port = 8080;

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }
}
~~~

Processor đọc prefix `acme.server`, property qua getter/setter và một số default value có thể suy ra từ source. Metadata có thể mô tả:
- `acme.server.host` — kiểu `java.lang.String`, giá trị mặc định `127.0.0.1`.
- `acme.server.port` — kiểu `java.lang.Integer`, giá trị mặc định `8080`.
- Description lấy từ Javadoc trên field khi field thuộc source đang biên dịch.

Javadoc của property nên là plain text vì processor đưa nội dung vào JSON metadata; không viết HTML hoặc cú pháp Markdown kỳ vọng được render.

### Record và constructor binding

Processor cũng hỗ trợ cấu hình immutable dùng constructor/record. Ví dụ:

~~~java
package com.acme.server;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("acme.server")
public record ServerProperties(String host, int port) {
}
~~~

Với record, mô tả từng component nên đặt bằng Javadoc tag `@param` ở class-level, ví dụ:

~~~java
/**
 * Server connection settings.
 *
 * @param host Host name or IP address.
 * @param port Listening port.
 */
@ConfigurationProperties("acme.server")
public record ServerProperties(String host, int port) {
}
~~~

Processor trích property từ constructor parameter theo quy tắc của Spring Boot. Với class có nhiều constructor hoặc dùng `@ConstructorBinding`, kiểm tra đúng constructor mà binder sử dụng; processor không thể suy đoán tùy ý mọi factory method.

## 6. Metadata được sinh ở đâu và kiểm tra thế nào?

Sau khi compile, file thường xuất hiện trong output directory của module:

| Build | Đường dẫn thường gặp |
| --- | --- |
| Gradle Java | `build/classes/java/main/META-INF/spring-configuration-metadata.json` |
| Maven | `target/classes/META-INF/spring-configuration-metadata.json` |

Đường dẫn output có thể khác nếu project tùy chỉnh source set, compiler output hoặc build directory. File quan trọng là resource `META-INF/spring-configuration-metadata.json` trong output/artifact.

Gradle:

~~~bash
./gradlew clean compileJava
~~~

Maven:

~~~bash
mvn clean compile
~~~

Sau khi compile, kiểm tra file trong output directory. Khi đóng gói JAR, kiểm tra resource được đưa vào artifact:

~~~bash
jar tf build/libs/acme-autoconfigure-1.0.0.jar
~~~

Hoặc với Maven:

~~~bash
jar tf target/acme-autoconfigure-1.0.0.jar
~~~

Trong danh sách entry, tìm:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Lệnh `jar tf` chỉ liệt kê entry của JAR; nếu muốn đọc nội dung JSON, giải nén file hoặc mở bằng công cụ archive. Không nên chỉ nhìn vào autocomplete trong IDE để kết luận processor đã chạy: IDE có thể giữ cache metadata cũ.

### Ví dụ một phần metadata được sinh

Tên và thứ tự field có thể khác theo source, nhưng cấu trúc thường tương tự:

~~~json
{
  "groups": [
    {
      "name": "acme.server",
      "type": "com.acme.server.ServerProperties",
      "sourceType": "com.acme.server.ServerProperties"
    }
  ],
  "properties": [
    {
      "name": "acme.server.host",
      "type": "java.lang.String",
      "description": "Host name or IP address used by the server.",
      "sourceType": "com.acme.server.ServerProperties",
      "defaultValue": "127.0.0.1"
    },
    {
      "name": "acme.server.port",
      "type": "java.lang.Integer",
      "description": "Port used by the embedded server.",
      "sourceType": "com.acme.server.ServerProperties",
      "defaultValue": 8080
    }
  ],
  "hints": []
}
~~~

Đây là ví dụ rút gọn để minh họa schema, không phải lời cam kết output byte-for-byte cho mọi version processor.

## 7. Thêm metadata thủ công khi processor không suy ra đủ

Không phải mọi property đều xuất phát trực tiếp từ class `@ConfigurationProperties`. Có thể cần mô tả property do code khác đọc, bổ sung default value không thể suy ra tĩnh, thêm deprecation hoặc gợi ý giá trị.

Tạo resource:

`src/main/resources/META-INF/additional-spring-configuration-metadata.json`

Ví dụ:

~~~json
{
  "properties": [
    {
      "name": "acme.server.mode",
      "type": "java.lang.String",
      "description": "Server operating mode.",
      "defaultValue": "standalone"
    }
  ],
  "hints": [
    {
      "name": "acme.server.mode",
      "values": [
        {
          "value": "standalone",
          "description": "Runs as a standalone server."
        },
        {
          "value": "cluster",
          "description": "Joins a server cluster."
        }
      ]
    }
  ]
}
~~~

Processor tự merge nội dung file additional vào metadata chính khi chạy. File này là tùy chọn; không cần tạo nếu không có property/hint bổ sung.

### Gradle: bảo đảm resource có mặt khi compile

Với Gradle, khi dùng `additional-spring-configuration-metadata.json`, cấu hình `compileJava` nhận `processResources` làm input để task resource chạy trước khi processor đọc metadata:

~~~groovy
tasks.named('compileJava') {
    inputs.files(tasks.named('processResources'))
}
~~~

Kotlin DSL:

~~~kotlin
tasks.named("compileJava") {
    inputs.files(tasks.named("processResources"))
}
~~~

Cấu hình này đặc biệt quan trọng khi metadata thủ công được xử lý trong cùng build. Không cần thêm nếu project không dùng file additional.

### Metadata thủ công có thể bổ sung hoặc ghi đè

Nếu entry thủ công trùng property đã tự sinh, một số trường như description, default value và deprecation có thể được override theo metadata bổ sung. Entry chưa tồn tại có thể được thêm mới. Phần `ignored.properties` có thể loại property khỏi danh sách được sinh.

Hãy giữ file JSON hợp lệ, đúng tên property và đúng kiểu dữ liệu. Metadata sai có thể khiến IDE gợi ý giá trị không phù hợp dù runtime binder vẫn có hành vi khác.

## 8. Những gì processor tự phát hiện và giới hạn

Processor có thể đọc:
- Class hoặc method được đánh dấu `@ConfigurationProperties`.
- Property theo getter/setter JavaBean.
- Property từ constructor/record theo quy tắc binding.
- Nested property; inner class thường được nhận diện tự động.
- Collection và Map như các property có kiểu tổng quát.
- Một số annotation Lombok phổ biến như `@Data`, `@Value`, `@Getter` và `@Setter`.

Một số giới hạn cần nhớ:

1. **Default value phải suy ra được từ source đang compile.** Default lấy từ constant của class khác hoặc biểu thức động có thể không được phát hiện.
2. **Collection default không tự suy ra đầy đủ.** Nếu cần hiển thị default cho collection hoặc enum, bổ sung metadata thủ công.
3. **Source từ dependency đã compile:** processor không có source của class đó nên không thể lấy đầy đủ Javadoc/default value. Có thể cung cấp metadata manual hoặc metadata source tương ứng.
4. **Nested class ở ngoài:** dùng `@NestedConfigurationProperty` trên field/getter khi muốn một class thông thường được xem như nested property; collection và map đã có xử lý riêng.
5. **Custom meta-annotation:** không mặc định rằng annotation tự tạo được meta-annotate bằng `@ConfigurationProperties` sẽ được processor hiểu như annotation gốc.
6. **Javadoc:** chỉ plain text; với record dùng tag `@param` cho component.

Không coi processor là một bộ phân tích mọi expression Java. Metadata là mô hình tĩnh phục vụ tooling, không phải bản dump toàn bộ giá trị runtime.

## 9. Lombok, AspectJ và nhiều annotation processor

Một project có thể dùng nhiều processor. Khi đó thứ tự và số lần chạy quan trọng.

### Lombok

Nếu class properties dùng Lombok để sinh getter/setter, processor của Lombok cần chạy **trước** `spring-boot-configuration-processor` để metadata có thể nhìn thấy cấu trúc được Lombok tạo.

Gradle:

~~~groovy
dependencies {
    annotationProcessor 'org.projectlombok:lombok'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Maven với compiler plugin có danh sách processor rõ ràng cần sắp Lombok trước configuration processor và khai báo cả hai trong `annotationProcessorPaths`/`annotationProcessors` phù hợp. Không chỉ thêm Lombok vào runtime dependency rồi kỳ vọng processor tự chạy đúng thứ tự.

Nếu dùng Lombok, cấu hình dependency/processor path phải khớp với version Lombok và JDK của project.

### AspectJ

Nếu AspectJ và Maven compiler cùng kích hoạt annotation processing, có nguy cơ processor chạy hai lần. Chọn một nơi thực hiện annotation processing. Nếu AspectJ đã chạy tất cả processor, có thể tắt processing trong Maven compiler plugin bằng:

~~~xml
<configuration>
    <proc>none</proc>
</configuration>
~~~

Chỉ dùng `proc=none` khi một compiler/processor pipeline khác đã thực hiện công việc cần thiết; nếu tắt ở mọi nơi, metadata sẽ không được tạo.

## 10. Multi-module và starter: đặt processor ở đúng nơi

Ví dụ:

~~~text
acme-library/
├── acme-core/
├── acme-autoconfigure/
│   └── src/main/java/com/acme/ServerProperties.java
└── acme-starter/
~~~

Nếu `ServerProperties` nằm trong `acme-autoconfigure`, processor phải được khai báo trong build file của module `acme-autoconfigure`. Module starter chỉ gom dependency; nếu không chứa source properties thì không cần processor riêng.

Nếu properties class sử dụng type nested từ một module khác, metadata của type phụ thuộc có thể không đầy đủ vì processor không đọc source của dependency đã compile. Spring Boot cung cấp `@ConfigurationPropertiesSource` cho các type source cần cung cấp metadata có thể tái sử dụng; trường hợp type bên ngoài mà không kiểm soát, cung cấp metadata thủ công nếu cần.

Khi build module riêng, kiểm tra task compile của chính module đó:

~~~bash
./gradlew :acme-autoconfigure:clean :acme-autoconfigure:compileJava
~~~

Maven:

~~~bash
mvn -pl acme-autoconfigure -am clean compile
~~~

Không chỉ chạy compile ở root nếu reactor/build configuration không thực sự đưa module chứa properties vào lifecycle.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không có `spring-configuration-metadata.json` | Chưa khai báo processor hoặc khai báo sai scope | Gradle dùng `annotationProcessor`; Maven cấu hình processor path/dependency discovery |
| File tồn tại nhưng IDE không gợi ý key | IDE chưa reload project hoặc metadata không nằm trong module đang mở | Reload Gradle/Maven, clean compile, kiểm tra resource trong module |
| Chỉ một số property xuất hiện | Getter/setter/constructor không phù hợp hoặc property nằm trong compiled dependency | Kiểm tra source model; thêm metadata manual cho phần không thể suy ra |
| Default collection không hiển thị | Processor không tự phát hiện default collection đầy đủ | Khai báo `defaultValue` trong additional metadata |
| Description bị thiếu | Thiếu Javadoc hoặc class source không được compile trong module | Viết plain-text Javadoc ở field; với record dùng `@param` |
| Lombok property không được nhận diện | Lombok processor chạy sau hoặc không có trên processor path | Thêm Lombok vào processor path và sắp trước Boot processor |
| Metadata manual bị bỏ qua | File sai tên hoặc sai vị trí resource | Dùng đúng `META-INF/additional-spring-configuration-metadata.json` |
| Gradle không thấy metadata manual | `processResources` chưa là input/dependency của `compileJava` | Cấu hình `inputs.files(tasks.named('processResources'))` |
| Maven/JDK mới không chạy processor | Compiler không discovery processor tự động | Khai báo `annotationProcessorPaths` tường minh |
| Metadata bị sinh hai lần | AspectJ và compiler cùng chạy processor | Chỉ để một pipeline xử lý; cấu hình `proc=none` ở pipeline còn lại nếu phù hợp |
| Processor bị đóng gói thành runtime dependency | Khai báo sai scope | Chuyển sang processor path hoặc dependency Maven optional |

### Checklist nhanh

- [ ] Đúng artifact `spring-boot-configuration-processor`.
- [ ] Version cùng dòng Spring Boot.
- [ ] Gradle: `annotationProcessor` trong đúng module.
- [ ] Maven: `annotationProcessorPaths` hoặc cách dependency optional được compiler hỗ trợ.
- [ ] Lombok đứng trước processor Boot nếu sử dụng.
- [ ] Clean compile và kiểm tra file `META-INF/spring-configuration-metadata.json`.
- [ ] Kiểm tra JAR phát hành có chứa metadata.
- [ ] Không nhầm metadata tooling với bean registration/runtime binding.

## 12. Tự kiểm tra kiến thức

1. Processor sinh file nào? **`META-INF/spring-configuration-metadata.json`**.
2. Gradle Java khai báo processor trong configuration nào? **`annotationProcessor`**.
3. Maven compiler plugin hiện đại khai báo processor path ở đâu? **`annotationProcessorPaths`**.
4. Có nên khai báo processor như dependency runtime của ứng dụng không? **Không**; đây là dependency của build/compiler.
5. Processor có tạo bean `ServerProperties` trong Spring context không? **Không**; cần cơ chế đăng ký properties bean riêng.
6. Processor có tự sinh mô tả từ Javadoc của source field không? **Có**, khi source được compile và Javadoc là plain text.
7. Vì sao default collection có thể thiếu trong metadata? Processor không thể suy ra đầy đủ giá trị collection từ source model; bổ sung manual metadata.
8. File metadata bổ sung có tên gì? **`META-INF/additional-spring-configuration-metadata.json`**.
9. Nếu Lombok sinh getter/setter thì thứ tự processor thế nào? **Lombok trước Spring Boot configuration processor**.
10. Nếu source properties nằm trong module autoconfigure, module nào cần processor? **Module autoconfigure**, nơi source được compile.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/reference/configuration-metadata.html): mục tiêu metadata, annotation processor, cấu hình Gradle/Maven, metadata bổ sung và giới hạn phát hiện.
- [Spring Boot — Generating Your Own Metadata by Using the Annotation Processor](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html): processor path Maven, `annotationProcessor` Gradle, Lombok/AspectJ, nested properties và metadata manual.
- [Spring Boot 3.3 — `@ConfigurationProperties` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html): annotation định nghĩa properties source.
- [Gradle — Java Plugin: Annotation Processor Path](https://docs.gradle.org/current/userguide/java_plugin.html): configuration `annotationProcessor` và compile task.
- [Apache Maven Compiler Plugin — Annotation Processor Paths](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html#annotationProcessorPaths): khai báo processor path cho Maven compiler.
