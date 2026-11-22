# Vai trò của tùy chọn biên dịch `-parameters` khi Spring gắn dữ liệu qua constructor

Trong Java, mã nguồn có thể khai báo constructor `RegistrationForm(String username, Integer age)`, nhưng tên `username` và `age` **không nhất thiết còn trong metadata mà Java Reflection đọc được sau khi biên dịch**. Mặc định, trình biên dịch Java có thể chỉ lưu đủ thông tin về kiểu và thứ tự tham số. Với mã thông thường biên dịch mà không có `-parameters`, Reflection thường thấy các tên giả như `arg0`, `arg1`.

Tùy chọn của **trình biên dịch Java** `javac -parameters` yêu cầu lưu **tên thật của các tham số phương thức và constructor vào bytecode** để các framework có thể truy xuất ở runtime. Điều này đặc biệt quan trọng với **constructor binding** trong Spring: Spring cần ghép tên tham số constructor với tên dữ liệu đầu vào như `username=Mai&age=21`. Nếu không có tên phù hợp hoặc cơ chế đặt tên tường minh khác, quá trình khởi tạo object từ request có thể không thực hiện được như kỳ vọng.

**Mấu chốt:** `-parameters` giúp Spring *biết tham số nào nhận dữ liệu nào*. Nó **không tự thực hiện chuyển kiểu, không kiểm tra dữ liệu hợp lệ, không tạo constructor, không tự cấp quyền sửa trường, và không thay thế cấu hình binding**.

## 1. Từ tên trong mã Java đến dữ liệu cần cho constructor binding

Giả sử DTO bất biến:

~~~java
public final class RegistrationForm {
    private final String username;
    private final Integer age;

    public RegistrationForm(String username, Integer age) {
        this.username = username;
        this.age = age;
    }

    public String getUsername() {
        return username;
    }

    public Integer getAge() {
        return age;
    }
}
~~~

Đối với một yêu cầu HTTP:

~~~http
GET /registrations/preview?username=Mai&age=21 HTTP/1.1
Host: localhost:8080
~~~

Spring MVC có thể cần thực hiện theo trình tự:

~~~text
Request values
  username = "Mai"
  age      = "21"
        |
        v
Phát hiện constructor RegistrationForm(String username, Integer age)
        |
        v
Lấy tên từng tham số: "username", "age"
        |
        v
Tra cứu giá trị đầu vào theo tên
        |
        v
Chuyển "21" từ String sang Integer bằng cơ chế conversion
        |
        v
new RegistrationForm("Mai", 21)
        |
        v
Áp dụng validation nếu có cấu hình/kích hoạt
        |
        v
Controller nhận RegistrationForm
~~~

Ở đây có **ba việc tách biệt**:

1. **Tìm tên:** `username`, `age` trên constructor. `-parameters` có thể cung cấp chúng.
2. **Binding và conversion:** tìm `username=...`, `age=...`; chuyển giá trị đầu vào sang kiểu Java cần thiết.
3. **Validation:** kiểm tra ràng buộc như tuổi tối thiểu hoặc tên không được để trống, nếu validator được cấu hình và kích hoạt.

Việc một field có tên `age` **không đủ** để Reflection của constructor tự suy ra tham số `Integer age`. Field name và **constructor parameter name** là hai loại metadata khác nhau.

## 2. `-parameters` làm gì trong file `.class`?

Tùy chọn `-parameters` xuất hiện từ Java 8. Khi biên dịch, nó yêu cầu `javac` phát sinh thuộc tính class-file **`MethodParameters`** (khi thích hợp) chứa tên và một số thông tin về các tham số của method/constructor. Java Reflection truy xuất được qua:

~~~java
Constructor<?> ctor = MyType.class.getDeclaredConstructors()[0];
Parameter[] parameters = ctor.getParameters();

for (Parameter parameter : parameters) {
    System.out.println(parameter.getName());
    System.out.println(parameter.isNamePresent());
}
~~~

Đây là **đoạn minh họa**, cần import `java.lang.reflect.Constructor`, `java.lang.reflect.Parameter` và kiểu `MyType` phù hợp; ở mục 3 có chương trình độc lập chạy được.

Hai API quan trọng:

- `Parameter.getName()` trả tên mà Reflection thấy. Nếu không có tên thật, Java có thể tạo tên tổng hợp như `arg0`.
- `Parameter.isNamePresent()` cho biết metadata tên thật có sẵn theo Reflection hay không. Nếu `false`, **không được** coi `getName()` là tên trong hợp đồng request.

Bảng phân biệt:

| Thành phần | `-parameters` | `-g` / debug symbols |
| --- | --- | --- |
| Metadata chính | `MethodParameters` | `LineNumberTable`, `LocalVariableTable` và thông tin debug phù hợp |
| Mục tiêu | Giữ tên tham số cho Reflection/framework | Hỗ trợ debugger, mapping mã nguồn và biến cục bộ |
| `Parameter.isNamePresent()` với class Java thường | Có thể là `true` | Không được bảo đảm |
| Khả năng thay thế cho Spring Framework 6.1+ | Đúng hướng khi cần tên tham số | **Không thay thế** `-parameters` |

**Vì sao nhấn mạnh Spring 6.1?** `LocalVariableTableParameterNameDiscoverer` đã bị loại khỏi Spring Framework 6.1. Spring không còn dựa vào việc phân tích Local Variable Table trong bytecode để đoán tên tham số Java. Cơ chế tiêu chuẩn dựa trên Reflection, chẳng hạn `StandardReflectionParameterNameDiscoverer`, cần metadata có thể truy cập được; thông thường đó là kết quả biên dịch với `-parameters`.

Đừng nhầm `-parameters` với tùy chọn khi **chạy JVM**. Đây là cờ dành cho **`javac` lúc build**, không phải đối số của `java` lúc khởi động service. Thêm cờ vào startup command không thể bổ sung metadata đã bị bỏ khỏi `.class`.

## 3. Chương trình Java 17+ kiểm chứng bằng Reflection

Ví dụ này dùng JDK thuần; **không cần Spring, Gradle hoặc Maven**. Tạo file `ParameterNamesDemo.java`:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public final class ParameterNamesDemo {

    public static final class RegistrationInput {
        private final String username;
        private final int age;

        public RegistrationInput(String username, int age) {
            this.username = username;
            this.age = age;
        }

        public String username() {
            return username;
        }

        public int age() {
            return age;
        }
    }

    public static void main(String[] args) throws Exception {
        Constructor<RegistrationInput> constructor =
                RegistrationInput.class.getDeclaredConstructor(
                        String.class, int.class);

        for (Parameter parameter : constructor.getParameters()) {
            System.out.println(parameter.getName()
                    + " / " + parameter.isNamePresent());
        }
    }
}
~~~

### 3.1. Biên dịch không có `-parameters`

Trên Linux/macOS, tạo thư mục output rồi biên dịch/chạy:

~~~bash
mkdir -p out/plain out/named out/debug
javac -d out/plain ParameterNamesDemo.java
java -cp out/plain ParameterNamesDemo
~~~

Stdout của chương trình:

~~~text
arg0 / false
arg1 / false
~~~

JVM vẫn biết constructor cần `String` rồi `int`, nhưng Reflection không biết đó là `username` và `age`.

### 3.2. Biên dịch có `-parameters`

~~~bash
javac -parameters -d out/named ParameterNamesDemo.java
java -cp out/named ParameterNamesDemo
~~~

Stdout:

~~~text
username / true
age / true
~~~

Các method Java và constructor không thay đổi logic. Sự khác nhau nằm trong metadata của bytecode.

### 3.3. Chỉ bật `-g` không tương đương

~~~bash
javac -g -d out/debug ParameterNamesDemo.java
java -cp out/debug ParameterNamesDemo
~~~

Với ví dụ class thông thường này, stdout vẫn là:

~~~text
arg0 / false
arg1 / false
~~~

Chú ý phải biên dịch lại vào **thư mục độc lập** như trên. Nếu chạy class từ một output directory cũ hoặc classpath bị trộn với JAR khác, kết quả có thể đánh lừa người kiểm tra.

Trên Windows PowerShell, thay bước tạo thư mục bằng:

~~~powershell
New-Item -ItemType Directory -Force -Path out/plain,out/named,out/debug
~~~

Các lệnh `javac -d ...` và `java -cp ...` vẫn dùng được trong PowerShell khi JDK nằm trên `PATH`.

Đây là bằng chứng trực tiếp của vai trò `-parameters`: cùng source code, cùng JDK, chỉ thay tùy chọn biên dịch thì tên tham số mà Reflection đọc được thay đổi.

## 4. Spring MVC thực sự dùng tên đó khi nào?

Trong Spring MVC, một method controller như:

~~~java
@GetMapping("/registrations/preview")
public RegistrationResponse preview(
        @ModelAttribute("registration") RegistrationForm form) {
    return new RegistrationResponse(
            form.getUsername(), form.getAge());
}
~~~

có thể yêu cầu Spring tạo `RegistrationForm` từ dữ liệu request. Nếu model chưa có object tương ứng, Spring có thể khởi tạo bằng **primary constructor** rồi dùng tên tham số đã truy xuất để đọc các giá trị cần thiết. Theo mặc định, Spring MVC hỗ trợ cả constructor binding và property binding trong quá trình xử lý `@ModelAttribute`, nhưng object bất biến không có setter giúp giới hạn đường ghi bằng property.

Khi nguồn input là query/form parameters, path variables hoặc headers phù hợp, Spring có thể dùng các giá trị đã được xác định để bind; cách ưu tiên nguồn và việc chọn constructor phụ thuộc ngữ cảnh Spring MVC. Không thể chỉ đặt `-parameters` rồi kỳ vọng framework sẽ bind mọi kind of request vào mọi constructor.

Lỗi thiếu metadata có thể biểu hiện qua exception về việc không thể xác định tên tham số constructor, thất bại khi khởi tạo model attribute hoặc lỗi bind. **Thông báo và HTTP status cụ thể phụ thuộc phiên bản Spring, exception handler và nơi xảy ra lỗi.** Vì thế cần kiểm tra class `.class` thực sự mà runtime tải, thay vì sửa ngẫu nhiên response handler.

### 4.1. Cẩn thận với `@RequestBody` JSON

Với:

~~~java
@PostMapping("/registrations")
public void create(@RequestBody RegistrationForm form) {
    // ...
}
~~~

đường xử lý khác: HTTP message converter, thường là Jackson, deserialize JSON thành object. Jackson có cơ chế riêng cho constructor/record, `@JsonCreator`, `@JsonProperty` và module hỗ trợ tên tham số. **Spring MVC constructor binding của `@ModelAttribute` không tự áp dụng tương tự cho `@RequestBody`.** Một bản build có `-parameters` có thể hữu ích cho một số thư viện, nhưng không bảo đảm Jackson sẽ tạo được mọi kiểu bất biến nếu thiếu cấu hình phù hợp.

### 4.2. Không nhầm constructor binding với constructor injection

Hai trường hợp đều dùng constructor nhưng ý nghĩa khác nhau:

| Trường hợp | Constructor nhận | Tên tham số dùng để làm gì |
| --- | --- | --- |
| `@ModelAttribute` constructor binding | Giá trị dữ liệu của request/form | Ghép tên parameter với tên field/parameter đầu vào |
| Spring bean constructor injection | Các dependency được container quản lý | Có thể hỗ trợ phân giải khi có nhiều bean cùng kiểu hoặc cấu hình theo tên |
| `@ConfigurationProperties` constructor binding | Các thuộc tính cấu hình ứng dụng | Ghép key cấu hình với constructor parameter khi áp dụng |
| `@RequestBody` JSON deserialization | Giá trị JSON do message converter giải mã | Tùy chiến lược deserializer; không đồng nhất với `DataBinder` |

Đối với dependency injection, nếu có nhiều bean cùng kiểu, việc lưu tên constructor parameter có thể giúp một số quy tắc phân giải theo tên; cách rõ ràng hơn khi cần lựa chọn có chủ ý thường là `@Qualifier`. Với constructor binding của request, tên là một phần của cách ánh xạ dữ liệu và cần ổn định theo hợp đồng API.

## 5. Ví dụ Spring Boot hoàn chỉnh: immutable form được tạo qua constructor

Ví dụ dùng Java 17 và Spring Boot 3.3.x, Spring Framework 6.1.x, khai báo Gradle rõ cờ biên dịch. Đây là ứng dụng độc lập có thể chạy sau khi thiết lập JDK/Gradle.

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'parameters-binding-demo'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Ở một số dự án Spring Boot Gradle, plugin đã thiết lập `-parameters` cho `JavaCompile`. Dòng cấu hình tường minh ở ví dụ giúp làm rõ hợp đồng build; nên kiểm tra giá trị trên task compile thực tế khi project dùng nhiều plugin hoặc multi-module. Lưu ý các version ở đây chỉ để ví dụ tái lập; dự án thực tế dùng bộ version phù hợp với chính dự án.

Tạo `src/main/java/com/example/parameters/ParametersApplication.java`:

~~~java
package com.example.parameters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ParametersApplication {

    public static void main(String[] args) {
        SpringApplication.run(ParametersApplication.class, args);
    }
}
~~~

Tạo `src/main/java/com/example/parameters/RegistrationForm.java`:

~~~java
package com.example.parameters;

public final class RegistrationForm {
    private final String username;
    private final Integer age;

    public RegistrationForm(String username, Integer age) {
        this.username = username;
        this.age = age;
    }

    public String getUsername() {
        return username;
    }

    public Integer getAge() {
        return age;
    }
}
~~~

Đây là một DTO **bất biến về tham chiếu/giá trị field**, chỉ có constructor hai tham số, **không có constructor không tham số và không có setter**. Spring muốn tạo instance mới phải xác định các đối số constructor.

Tạo `src/main/java/com/example/parameters/RegistrationController.java`:

~~~java
package com.example.parameters;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/registrations")
public class RegistrationController {

    @GetMapping("/preview")
    public Map<String, Object> preview(
            @ModelAttribute("registration") RegistrationForm form) {

        return Map.of(
                "username", form.getUsername(),
                "age", form.getAge());
    }
}
~~~

Chạy dự án nếu đã có Gradle Wrapper:

~~~bash
./gradlew clean bootRun
~~~

Hoặc trên Windows PowerShell:

~~~powershell
.\gradlew.bat clean bootRun
~~~

Nếu chưa tạo wrapper, dùng Gradle tương thích cài sẵn để chạy `gradle bootRun` hoặc tạo wrapper cho project trước. Request:

~~~bash
curl --get --data-urlencode "username=Mai" --data-urlencode "age=21" http://localhost:8080/registrations/preview
~~~

Kết quả kỳ vọng: HTTP `200 OK`; JSON có hai cặp giá trị sau (thứ tự key JSON không cố định):

~~~json
{
  "username": "Mai",
  "age": 21
}
~~~

Spring biết `username` và `age` từ metadata constructor, lấy tham số tương ứng và chuyển `"21"` sang `Integer`. Controller nhận object đã được tạo. Việc có thể khởi tạo object từ request **không chứng minh** tên hợp lệ hoặc người gọi có quyền tạo tài khoản; ví dụ chỉ minh họa constructor binding, chưa thực hiện validation nghiệp vụ.

Nếu bỏ `-parameters` khỏi build và compile sạch các class Java bình thường như `RegistrationForm` mà không có cách cung cấp tên khác, việc suy ra hai tên có thể thất bại. **Không dựa vào kết quả một lần chạy khi class cũ vẫn còn trong output directory**: cần clean/recompile, kiểm tra metadata và thử lại.

## 6. Kiểm thử tự động cả metadata và hành vi HTTP

Với dependency `spring-boot-starter-test` ở ví dụ trên, tạo `src/test/java/com/example/parameters/ParameterBindingTest.java`:

~~~java
package com.example.parameters;

import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ParameterBindingTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void constructorParametersRetainTheirNames() throws Exception {
        Constructor<RegistrationForm> ctor =
                RegistrationForm.class.getDeclaredConstructor(
                        String.class, Integer.class);

        Parameter[] params = ctor.getParameters();

        assertEquals(2, params.length);
        assertTrue(params[0].isNamePresent());
        assertTrue(params[1].isNamePresent());
        assertEquals("username", params[0].getName());
        assertEquals("age", params[1].getName());
    }

    @Test
    void mvcBindsFormThroughConstructor() throws Exception {
        mvc.perform(get("/registrations/preview")
                .param("username", "Mai")
                .param("age", "21"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("Mai"))
                .andExpect(jsonPath("$.age").value(21));
    }
}
~~~

Chạy:

~~~bash
./gradlew clean test
~~~

Kiểm thử đầu tiên xác nhận **class do build tạo ra** giữ tên parameter theo Reflection. Kiểm thử thứ hai xác nhận **Spring MVC** thật sự bind các giá trị theo tên và gọi controller. Cả hai cần thiết: chỉ có metadata đúng chưa bảo đảm cấu hình MVC hoàn chỉnh, và chỉ có HTTP test pass không tự chứng minh build nào cũng giữ tên tham số (đặc biệt nếu code thay đổi thành record hoặc khai báo tên tường minh).

Nếu test fail vì thiếu tên, kiểm tra task compile và class được nạp trước. Nếu test fail vì conversion hoặc validation, phân biệt với lỗi metadata; xử lý đúng lớp nguyên nhân.

## 7. Cấu hình `-parameters` trong các hệ thống build

### 7.1. Dùng `javac` trực tiếp

~~~bash
javac -parameters -d out/classes src/main/java/com/example/parameters/RegistrationForm.java
~~~

Cần tạo trước thư mục `out/classes` nếu chưa có. Cờ áp dụng cho **lần biên dịch đó**. Khi một constructor được khai báo trong module A nhưng chương trình chạy từ module B, cần cấu hình compile **module A** để metadata đi theo class của A.

### 7.2. Gradle Groovy DSL

Trong `build.gradle` của module chứa các class được bind:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}
~~~

Trong project đa module, mỗi module Java có thể có task `compileJava`, `compileTestJava` hoặc task compile riêng. Đừng chỉ bật cờ ở ứng dụng chạy cuối nếu DTO được biên dịch ở một thư viện con. Với Java toolchain hoặc custom compile task, xác nhận compiler args thực tế thay vì chỉ nhìn một build script ở root.

### 7.3. Gradle Kotlin DSL

Trong `build.gradle.kts`:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Dòng import đặt ở đầu file Gradle Kotlin DSL. Đây là cờ cho các task biên dịch **Java**; nếu dùng Kotlin source, Kotlin compiler và metadata Kotlin cần cấu hình/tìm hiểu riêng.

### 7.4. Maven

Trong `pom.xml`, cấu hình `maven-compiler-plugin` (đoạn plugin trong `<build><plugins>`):

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

Cấu hình `<parameters>true</parameters>` tương ứng với `javac -parameters`. Khi dự án kế thừa `spring-boot-starter-parent`, Spring Boot thường đã thiết lập mặc định này, nhưng không có nghĩa mọi POM chỉ import BOM hoặc mọi module phụ đều có cùng compiler configuration. Kiểm tra effective POM và class build thực tế khi gặp sự cố.

### 7.5. IDE, CI và artifact cuối

Một lỗi rất thường gặp là chạy bình thường trong IDE nhưng fail trong CI, hoặc ngược lại:

- IDE có thể dùng compiler riêng, trong khi CI gọi Gradle/Maven.
- Multi-module có class DTO được biên dịch từ một module/artefact khác.
- Lệnh tăng tốc incremental compilation có thể giữ class cũ.
- Quá trình shade, obfuscate, AOT hoặc biến đổi bytecode có thể tác động đến metadata; cần kiểm tra JAR **sau cùng**.
- Khác biệt giữa test runtime và application runtime có thể do classpath chọn một bản class khác.

Vì vậy, dùng một build pipeline thống nhất, chạy clean build khi điều tra và xác nhận tên qua Reflection từ **artefact thực sự chạy**.

## 8. Nếu không thể thay compiler args thì làm gì?

Tùy vấn đề, có thể cung cấp metadata tên theo cách tường minh. Tuy nhiên, cách đó có phạm vi riêng và không tương đương bật `-parameters` cho mọi method.

### 8.1. `@BindParam` cho tên input của constructor binding trong Spring MVC

Ví dụ một external request gửi key `user-name`, khác identifier Java `username`:

~~~java
import org.springframework.web.bind.annotation.BindParam;

public final class RegistrationForm {
    private final String username;
    private final Integer age;

    public RegistrationForm(
            @BindParam("user-name") String username,
            @BindParam("age") Integer age) {
        this.username = username;
        this.age = age;
    }

    public String getUsername() {
        return username;
    }

    public Integer getAge() {
        return age;
    }
}
~~~

Đây là **phương án thay thế file `RegistrationForm.java`** trong ví dụ MVC, với import thuộc Spring Web MVC tương ứng; nó không được đặt cùng lúc cạnh class cũ có cùng tên. Khi đó request có thể dùng `user-name=Mai&age=21`. `@BindParam` giúp chỉ định key input; annotation này đặc biệt hữu ích khi API dùng dấu gạch ngang, snake_case hoặc tên ổn định khác tên parameter Java.

Bật `-parameters` vẫn là thực hành tốt cho dự án Java Spring. `@BindParam` mô tả **hợp đồng tên của từng input**, còn `-parameters` làm tên Java sẵn có rộng rãi cho Reflection/framework.

### 8.2. `@ConstructorProperties` khi cần khai báo danh sách tên constructor

Java cung cấp `java.beans.ConstructorProperties`:

~~~java
import java.beans.ConstructorProperties;

public final class Coordinate {
    private final int x;
    private final int y;

    @ConstructorProperties({"x", "y"})
    public Coordinate(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public int getX() {
        return x;
    }

    public int getY() {
        return y;
    }
}
~~~

Một số cơ chế Spring/JavaBeans hỗ trợ đọc annotation này khi phân giải tên tham số constructor. **Đừng nhầm:** `@ConstructorProperties` là metadata khai báo tường minh cho một constructor; nó **không làm** `Parameter.isNamePresent()` chuyển từ `false` thành `true` nếu class vẫn được `javac` biên dịch không có `-parameters`. Cần kiểm tra đường binding cụ thể trước khi chọn annotation như giải pháp thay thế.

### 8.3. Tên method argument đã có annotation

Trong controller, `@RequestParam("age") Integer age` hoặc `@PathVariable("id") Long id` đã khai báo tên tương ứng cho cơ chế argument binding đó. Các annotation này **không tự cung cấp tên cho tham số constructor của một DTO khác**. Vì vậy việc sửa một `@RequestParam` trong controller không giải quyết được metadata bị thiếu trên `RegistrationForm(String username, Integer age)`.

### 8.4. Record và Kotlin

Java record, Kotlin primary constructor và các annotation liên quan có thể có **cơ chế metadata riêng**. Chúng không phải bằng chứng rằng mọi Java class thường đều giữ parameter names. Với Java class được Spring dùng qua Reflection, vẫn nên bật `-parameters`; với Kotlin, cần cấu hình và kiểm tra Kotlin compiler (chẳng hạn `-java-parameters` khi cần tương tác với Java reflection) và các cơ chế Kotlin reflection theo framework sử dụng. Không trộn cờ Java javac với cờ của trình biên dịch Kotlin.

## 9. Khi đổi tên tham số, hợp đồng API có thể đổi theo

Giả sử constructor đang là:

~~~java
public RegistrationForm(String username, Integer age) { ... }
~~~

Nếu có `-parameters` và Spring lấy tên trực tiếp từ constructor, request key `username` có thể được bind. Sau khi refactor thành:

~~~java
public RegistrationForm(String loginName, Integer age) { ... }
~~~

kiểu và vị trí tham số vẫn như cũ, nhưng metadata đã thành `loginName`. Client tiếp tục gửi `username` có thể không còn khớp. Đây là **thay đổi hành vi của contract ở runtime**, dù Java compiler không báo lỗi cho những client gửi HTTP request.

Khi API cần tên ổn định:

1. Chọn tên parameter hợp đồng nhất quán với input.
2. Dùng `@BindParam("username")` nếu muốn tên bên ngoài ổn định dù tên biến Java thay đổi.
3. Viết integration test gửi key thật mà client sử dụng.
4. Đánh giá tương thích ngược như với thay đổi tên field trong JSON/form.
5. Không bind trực tiếp các field nhạy cảm từ client vào persistence entity.

**Lưu ý bảo mật:** `-parameters` chỉ giữ tên và metadata; không tự ngăn mass assignment. Với `@ModelAttribute`, Spring có thể dùng cả constructor và property binding mặc định. Nên dùng input DTO chỉ chứa trường được phép, hoặc giới hạn property binding bằng các cơ chế như `allowedFields`/constructor-only binding khi phù hợp. Phân quyền và kiểm tra bất biến nghiệp vụ phải được thực hiện ở tầng thích hợp.

## 10. Chẩn đoán sự cố thiếu tên tham số

| Dấu hiệu | Nguyên nhân cần kiểm tra | Bước xác minh |
| --- | --- | --- |
| Spring báo không xác định được parameter names | Class thiếu metadata hoặc đường phân giải tên không phù hợp | Dùng `Parameter.isNamePresent()` trên đúng constructor class chạy |
| Runtime thấy `arg0`, `arg1` | Bytecode Java thường thiếu `MethodParameters` | Compile clean với `-parameters` |
| Đã bật `-g` mà vẫn lỗi | Debug info không thay metadata Reflection | Đổi sang `-parameters` |
| Đã thêm compiler args nhưng không thay đổi | Build output cũ, IDE/CI dùng compiler khác | Clean build, kiểm tra output/JAR và compiler task |
| Chỉ một module bị lỗi | DTO nằm trong module không có cờ hoặc dependency đã build trước | Cấu hình compile ngay tại module sở hữu class |
| Constructor có tên đúng nhưng binding vẫn sai | Request key khác tên, thiếu converter hoặc constructor không phù hợp | Đối chiếu key, `@BindParam`, chữ ký và ConversionService |
| Data binding thành công, validation thất bại | Lỗi ràng buộc dữ liệu sau khi tạo object | Kiểm tra validator và `BindingResult` |
| `@RequestBody` hoạt động khác `@ModelAttribute` | Jackson có cơ chế deserialize riêng | Kiểm tra Jackson annotations/modules và message conversion |
| IDE chạy được, JAR CI không chạy | Kết quả compiler hoặc bytecode transformation khác nhau | So sánh artefact thực tế, test metadata trong CI |

Một trình tự kiểm tra ít tốn thời gian:

~~~text
1. Xác định kiểu target và chính constructor Spring đang dùng.
2. Xác định request key thực tế (username, age, ...).
3. Chạy Reflection với đúng class được nạp: getParameters(), isNamePresent().
4. Nếu thiếu tên, kiểm tra args của compiler ở module sở hữu class.
5. Clean/recompile và kiểm tra artefact runtime mới.
6. Nếu tên đã đúng, điều tra conversion, validation, allowed fields và binding errors.
7. Viết test để lỗi không quay lại khi thay build plugin hay refactor.
~~~

**Phân biệt lỗi metadata với lỗi dữ liệu:** nếu input `age="abc"` không thể convert sang `Integer`, bật `-parameters` sẽ không sửa được. Nếu Spring không biết tham số Java nào tương ứng key `age`, thêm validator cũng không sửa nguyên nhân. Hãy kiểm tra từng giai đoạn theo đúng thứ tự.

## 11. Các hiểu nhầm thường gặp

- **“Có field `username` nên constructor chắc chắn nhận giá trị từ key `username`.”** Không: để gắn theo tham số, Spring cần tên của tham số constructor (hoặc metadata đặt tên tường minh).
- **“Thêm `-parameters` khi chạy `java -jar` là đủ.”** Sai: phải thêm khi biên dịch Java.
- **“Compile với `-g` đã có tên cho Reflection.”** Không được bảo đảm; trong Spring 6.1+ không dựa vào LocalVariableTableParameterNameDiscoverer.
- **“Chỉ cần bật cờ ở module web.”** Sai nếu target constructor nằm trong module thư viện được build riêng.
- **“`Parameter.getName()` luôn là tên gốc.”** Khi `isNamePresent() == false`, tên như `arg0` chỉ là tên tổng hợp.
- **“Có `-parameters` thì mọi `@RequestBody` JSON đều deserialize immutable object.”** Sai: JSON converter có cơ chế riêng.
- **“`-parameters` bật luôn validation.”** Sai: validation cần validator/ràng buộc và điểm kích hoạt.
- **“Refactor tên tham số không ảnh hưởng client.”** Có thể ảnh hưởng nếu Spring dựa vào tên parameter để bind form/query.
- **“Dữ liệu gắn được qua constructor thì đã an toàn.”** Sai: vẫn phải giới hạn field đầu vào, validate và kiểm tra quyền.
- **“Bật `-parameters` sẽ làm tất cả dependency JAR có tên tham số.”** Không: mỗi JAR mang bytecode từ build của chính nó.

## 12. Câu hỏi thực hành

1. `javac -parameters` tạo metadata nào và `Parameter.isNamePresent()` cho kết quả gì?
2. Vì sao `javac -g` không thay thế `-parameters` đối với Spring Framework 6.1+?
3. Trong ví dụ `RegistrationForm(String username, Integer age)`, Spring cần thông tin gì để ghép request `age=21` với đối số thứ hai?
4. Nếu một thư viện ngoài có class thiếu parameter metadata, thêm cờ vào module consumer có sửa được JAR đã build không?
5. Vì sao `@ModelAttribute` constructor binding khác `@RequestBody` JSON deserialization?
6. Khi đổi tên `username` thành `loginName`, có thể giữ input key cũ bằng cách nào?
7. Test nào chứng minh metadata được giữ? Test nào chứng minh Spring MVC dùng metadata đúng?
8. Nếu metadata đúng nhưng giá trị `age=abc` thất bại, nên điều tra bước nào?
9. Vì sao input DTO bất biến vẫn cần validation và authorization?
10. Trong multi-module Gradle/Maven, cấu hình compiler cần nằm ở đâu?

**Ghi nhớ:** `-parameters` là một phần **hợp đồng build của Java bytecode**: nó giữ tên constructor/method parameter để Spring truy xuất qua Reflection khi cần. Trong constructor binding, metadata này giúp nối **tên input → đối số constructor → đối tượng Java**. Cần cấu hình ở đúng module, biên dịch lại, kiểm tra metadata bằng Reflection và xác nhận hành vi bằng test binding. Conversion, validation, authorization và định dạng JSON là những trách nhiệm riêng.

### Tài liệu tham khảo

- Spring Framework — Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Framework — `@ModelAttribute`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.1 Release Notes — Parameter Name Retention: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes
- Spring Boot — Gradle plugin reference: https://docs.spring.io/spring-boot/gradle-plugin/
- Spring Boot — Maven plugin configuration: https://docs.spring.io/spring-boot/maven-plugin/using.html
- Java SE — `java.lang.reflect.Parameter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html
- Java `javac` documentation: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
