# Phân biệt tham số JVM, tham số công cụ dựng và đối số ứng dụng

Khi chạy một ứng dụng Spring Boot, cùng một dòng lệnh có thể chứa tham số dành cho **máy ảo Java (JVM)**, **công cụ dựng dự án (Gradle)** và **chính ứng dụng**. Ba nhóm được xử lý ở những thời điểm khác nhau. Đặt đúng giá trị nhưng sai vị trí có thể khiến cấu hình không có tác dụng hoặc bị hiểu thành một đối số thông thường.

Mục tiêu của bài: xác định **ai nhận tham số**, **tham số tác động lên tiến trình nào**, **cách truyền qua `java -jar`, `bootRun` và IDE**, đồng thời kiểm chứng được giá trị thật sự tới ứng dụng.

## 1. Ba nhóm tham số khác nhau ở đâu?

| Nhóm | Bên nhận và thời điểm xử lý | Ví dụ | Tác động điển hình |
| --- | --- | --- | --- |
| **Tham số JVM** (VM options) | Java launcher/JVM nhận **trước khi** gọi `main` của tiến trình đích | `-Xmx512m`, `-Ddemo.mode=fast`, `--add-opens=...` | Dung lượng heap, system properties, một số hành vi của JVM |
| **Tham số công cụ dựng** (build-tool options/properties) | Gradle nhận khi xử lý lệnh dựng/chạy tác vụ | `--offline`, `--stacktrace`, `-PdemoMode=fast`, `-Dorg.gradle.jvmargs=...` | Cách Gradle cấu hình dự án, tải phụ thuộc, chạy tác vụ và JVM của Gradle |
| **Đối số ứng dụng** (application/program arguments) | `main(String[] args)` của ứng dụng nhận, sau đó Spring Boot có thể phân tích | `--server.port=9090`, `--spring.profiles.active=dev`, `input.csv` | Cấu hình Spring Boot qua dòng lệnh hoặc dữ liệu đầu vào riêng của ứng dụng |

**Điểm cốt lõi:** `-Ddemo.mode=fast` là *cú pháp JVM system property* khi đặt trong lệnh `java` trước lớp chính/`-jar`. Nhưng `-Ddemo.mode=fast` trong lệnh `gradlew` tác động tới **JVM chạy Gradle**; nó không mặc nhiên được chuyển sang JVM mà `bootRun` khởi tạo. Tương tự, `-PdemoMode=fast` chỉ tạo **project property của Gradle** trừ khi tập lệnh dựng chủ động chuyển giá trị đó sang ứng dụng.

Mô hình xử lý khi dùng Gradle:

~~~text
Shell / IDE
  └─ gradlew / Gradle: đọc tùy chọn Gradle, -P, -D của Gradle
       └─ tác vụ bootRun (kiểu JavaExec): tạo tiến trình Java chạy ứng dụng
            ├─ JVM đọc VM options và JVM system properties đã cấu hình cho bootRun
            └─ main(String[] args) nhận program arguments
                 └─ SpringApplication.run(..., args)
                      ├─ ApplicationArguments phân tích đối số
                      └─ Environment có thể nhận --key=value làm thuộc tính cấu hình
~~~

Với `java -jar`, không có lớp Gradle ở giữa; Java launcher trực tiếp nhận VM options và khởi động ứng dụng.

## 2. `java` và `java -jar`: vị trí quyết định ý nghĩa

Cú pháp thường gặp:

~~~text
java [VM options] -jar <đường-dẫn-jar> [đối-số-ứng-dụng...]
java [VM options] <TênLớpMain> [đối-số-ứng-dụng...]
~~~

Ví dụ chạy một JAR Spring Boot (thay `demo.jar` bằng tên JAR được tạo trong dự án):

~~~bash
java -Xms128m -Xmx512m -Ddemo.mode=fast -jar build/libs/demo.jar --spring.profiles.active=dev --server.port=9090 input.csv
~~~

Đọc từng phần:

- `-Xms128m`: kích thước heap khởi đầu do JVM xử lý.
- `-Xmx512m`: giới hạn heap tối đa của JVM.
- `-Ddemo.mode=fast`: thiết lập JVM system property; có thể đọc bằng `System.getProperty("demo.mode")`.
- `-jar build/libs/demo.jar`: yêu cầu Java launcher chạy JAR này.
- `--spring.profiles.active=dev` và `--server.port=9090`: các **đối số ứng dụng**, Spring Boot mặc định chuyển thành thuộc tính của `Environment`.
- `input.csv`: đối số ứng dụng không có dạng `--key=value`; ứng dụng tự quyết định cách sử dụng.

### Thử trực tiếp với Java 17+

Tạo tệp `LaunchArgsDemo.java` chứa toàn bộ chương trình sau; ví dụ này chỉ dùng JDK, giúp thấy rõ ranh giới trước khi thêm Spring Boot:

~~~java
import java.util.Arrays;

public class LaunchArgsDemo {
    public static void main(String[] args) {
        System.out.println("systemProperty="
                + System.getProperty("demo.mode", "<unset>"));
        System.out.println("args=" + Arrays.toString(args));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LaunchArgsDemo.java
java -Ddemo.mode=fast -Xmx512m LaunchArgsDemo --server.port=9090 input.csv
~~~

Đúng hai dòng do chương trình in:

~~~text
systemProperty=fast
args=[--server.port=9090, input.csv]
~~~

Đổi vị trí `-D` sang **sau** tên lớp:

~~~bash
java LaunchArgsDemo -Ddemo.mode=fast
~~~

Khi không có nguồn nào khác đặt `demo.mode`, chương trình in:

~~~text
systemProperty=<unset>
args=[-Ddemo.mode=fast]
~~~

Vì khi đó `-Ddemo.mode=fast` chỉ là một phần tử của `args`, không phải JVM option. Nguyên tắc tương tự áp dụng sau tên JAR: `java -jar demo.jar -Xmx512m` đưa chuỗi `-Xmx512m` vào đối số ứng dụng; nó **không** đặt giới hạn heap. Tùy cách ứng dụng phân tích đối số, chuỗi đặt sai vị trí có thể bị bỏ qua hoặc gây lỗi.

## 3. Gradle: phân biệt tham số của công cụ dựng với tham số của `bootRun`

`./gradlew` (Windows thường dùng `gradlew.bat`) là **Gradle Wrapper**. Gradle phân tích tùy chọn của chính nó, cấu hình dự án và thực thi tác vụ.

Ví dụ:

~~~bash
./gradlew --offline -PtargetEnv=local bootJar
~~~

Ở đây `--offline` yêu cầu Gradle tránh truy cập kho phụ thuộc qua mạng; `-PtargetEnv=local` tạo project property cho tập lệnh dựng; `bootJar` là tác vụ đóng gói. Lệnh này **không khởi chạy ứng dụng**, nên cũng không có `main(String[] args)` của ứng dụng để nhận đối số.

### Truyền đối số ứng dụng qua `bootRun`

Plugin Spring Boot cung cấp tác vụ `bootRun` dựa trên `JavaExec`. Gradle nhận tùy chọn tác vụ `--args`, rồi chuyển nội dung của nó thành các đối số cho tiến trình Java chạy ứng dụng:

~~~bash
./gradlew bootRun --args="--spring.profiles.active=dev --server.port=9090 input.csv"
~~~

Trên Windows:

~~~powershell
gradlew.bat bootRun --args="--spring.profiles.active=dev --server.port=9090 input.csv"
~~~

`--args` là tùy chọn mà Gradle xử lý; các chuỗi **bên trong** giá trị của nó mới là đối số mà ứng dụng nhận. Nhờ vậy `main(String[] args)` của ứng dụng nhìn thấy `--spring.profiles.active=dev`, `--server.port=9090` và `input.csv`.

### Truyền VM options vào đúng JVM của `bootRun`

Trong `build.gradle` dùng Groovy DSL, cấu hình trực tiếp tác vụ:

~~~groovy
tasks.named('bootRun') {
    jvmArgs '-Xmx512m'
    systemProperty 'demo.mode', project.findProperty('demoMode') ?: 'default'
}
~~~

Sau đó chạy:

~~~bash
./gradlew -PdemoMode=fast bootRun --args="--server.port=9090 input.csv"
~~~

Luồng giá trị là:

1. Gradle đọc project property `demoMode=fast` từ `-PdemoMode=fast`.
2. Cấu hình `bootRun` chủ động chuyển giá trị đó thành **system property `demo.mode=fast` của JVM ứng dụng**.
3. `jvmArgs '-Xmx512m'` áp dụng giới hạn heap cho **JVM ứng dụng**.
4. `--args="..."` chuyển các đối số vào `main(String[] args)`.

Nếu bỏ dòng `systemProperty ...` trong `build.gradle` thì `-PdemoMode=fast` **không tự xuất hiện** dưới tên `demo.mode` trong ứng dụng. Đây là cơ chế chuyển tiếp tường minh; tên project property và tên system property có thể khác nhau.

### Cảnh giác với `-D` và bộ nhớ của Gradle

- `./gradlew -Ddemo.mode=fast bootRun`: `-D` thiết lập system property trong môi trường **Gradle**; không nên giả định `System.getProperty("demo.mode")` trong ứng dụng nhận được `fast`. Hãy cấu hình `bootRun.systemProperty(...)` nếu muốn chuyển nó tới ứng dụng.
- `org.gradle.jvmargs=-Xmx2g` trong `gradle.properties`: cấu hình bộ nhớ JVM của **Gradle daemon**, không phải bộ nhớ JVM ứng dụng do `bootRun` khởi chạy.
- `./gradlew bootRun --args="--server.port=9090"`: cấu hình **đối số ứng dụng**, không thiết lập VM options.
- `./gradlew --stacktrace bootRun`: yêu cầu Gradle in stack trace cho lỗi khi thực thi build; đây không phải tùy chọn in stack trace của mã Java ứng dụng.

Vì `bootRun` mở tiến trình Java riêng, việc phân biệt hai JVM giải thích vì sao tăng heap của Gradle không nhất thiết giải quyết được `OutOfMemoryError` bên trong ứng dụng, và ngược lại.

## 4. Spring Boot nhận gì từ `main(String[] args)`?

Một lớp nguồn chính của dự án Spring Boot có thể như sau. Đây là **mã trong dự án đã có các phụ thuộc Spring Boot**, không phải chương trình JDK độc lập ở phần trước:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class RuntimeParametersApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuntimeParametersApplication.class, args);
    }

    @Bean
    ApplicationRunner printParameters(Environment environment) {
        return arguments -> {
            System.out.println("profiles="
                    + arguments.getOptionValues("spring.profiles.active"));
            System.out.println("port="
                    + environment.getProperty("server.port"));
            System.out.println("jvmMode="
                    + System.getProperty("demo.mode", "<unset>"));
            System.out.println("nonOptions="
                    + arguments.getNonOptionArgs());
        };
    }
}
~~~

Khi đóng gói JAR thực thi phù hợp và chạy:

~~~bash
java -Ddemo.mode=fast -jar build/libs/demo.jar --spring.profiles.active=dev --server.port=9090 input.csv
~~~

Các dòng **do bean `ApplicationRunner` in ra** (ngoài log khởi động thông thường của Spring Boot) là:

~~~text
profiles=[dev]
port=9090
jvmMode=fast
nonOptions=[input.csv]
~~~

Giải thích điểm khác nhau giữa các API:

| API | Loại dữ liệu đọc | Ví dụ |
| --- | --- | --- |
| `main(String[] args)` | Chuỗi đối số thô mà Java launcher chuyển cho ứng dụng | `["--server.port=9090", "input.csv"]`, còn có `--spring.profiles.active=dev` |
| `ApplicationArguments.getOptionValues("spring.profiles.active")` | Giá trị của đối số dạng `--tên=giá-trị` | `[dev]` |
| `ApplicationArguments.getNonOptionArgs()` | Đối số không có dạng tùy chọn `--...` | `[input.csv]` |
| `System.getProperty("demo.mode")` | JVM system property | `fast` nếu JVM ứng dụng nhận `-Ddemo.mode=fast` |
| `Environment.getProperty("server.port")` | Giá trị cấu hình Spring sau khi tổng hợp các nguồn | `9090` |

Mặc định, Spring Boot đưa các đối số dạng `--key=value` vào `Environment` như một nguồn thuộc tính dòng lệnh. Nó **không tự chuyển** mọi đối số thông thường như `input.csv` thành cấu hình có tên. Nếu mã gọi `SpringApplication.setAddCommandLineProperties(false)` thì cơ chế đưa đối số dòng lệnh vào `Environment` bị tắt, dù các đối số vẫn có thể được nhận qua `ApplicationArguments`.

### Cùng tên thuộc tính, khác nơi lưu

Xét lệnh:

~~~bash
java -Ddemo.mode=jvm -jar build/libs/demo.jar --demo.mode=cli
~~~

Theo cấu hình mặc định của Spring Boot:

- `System.getProperty("demo.mode")` cho `jvm` vì nó chỉ đọc JVM system properties.
- `Environment.getProperty("demo.mode")` cho `cli` vì thuộc tính dòng lệnh có độ ưu tiên cao hơn JVM system property trong hệ thống cấu hình mặc định.
- `ApplicationArguments.getOptionValues("demo.mode")` cho danh sách `[cli]` vì nó đọc đối số dạng `--...`.

Do đó, một thuộc tính có thể có cùng tên nhưng giá trị khác nhau khi xem qua các API khác nhau. Hãy kiểm tra **đúng nguồn** trước khi kết luận rằng một tùy chọn bị bỏ qua. Biến môi trường hệ điều hành (ví dụ `SPRING_PROFILES_ACTIVE=dev`) là một nguồn cấu hình khác; nó không tự trở thành phần tử của `main(String[] args)`.

## 5. Thiết lập trong IDE

Các IDE như IntelliJ IDEA hoặc Eclipse thường có những trường tương ứng:

| Trường cấu hình chạy | Đặt vào đó | Nơi nhận |
| --- | --- | --- |
| **VM options / JVM arguments** | `-Xmx512m -Ddemo.mode=fast` | JVM chạy ứng dụng |
| **Program arguments / Application arguments** | `--spring.profiles.active=dev --server.port=9090 input.csv` | `main(String[] args)`, rồi Spring Boot |
| **Gradle tasks/arguments** (khi chạy qua Gradle) | `bootRun`, `-PdemoMode=fast`, `--offline` | Gradle; muốn chuyển tiếp sang JVM/app phải cấu hình hoặc dùng `--args` đúng cách |
| **Environment variables** | `SPRING_PROFILES_ACTIVE=dev` | Môi trường của tiến trình; Spring Boot có thể đọc qua `Environment` |

Khi chạy trực tiếp lớp `main` từ IDE, không có lệnh `gradlew` đang xử lý tham số. Khi chọn chế độ chạy qua Gradle, IDE có thể tạo thêm tiến trình Gradle và tác vụ `bootRun`; cần xem trường nào tác động tới Gradle và trường nào tác động tới tiến trình ứng dụng.

## 6. Những lỗi dễ gặp và cách sửa

| Cách làm gây nhầm lẫn | Vì sao không đạt ý định | Cách đúng |
| --- | --- | --- |
| `java -jar demo.jar -Xmx512m` với ý định tăng heap | `-Xmx512m` nằm sau JAR, trở thành đối số ứng dụng | `java -Xmx512m -jar demo.jar` |
| `java -jar demo.jar -Ddemo.mode=fast` với ý định đặt system property | `-D...` nằm sau JAR | `java -Ddemo.mode=fast -jar demo.jar` |
| `./gradlew -PdemoMode=fast bootRun` và mong `System.getProperty("demo.mode")` nhận `fast` | `-P` chỉ thiết lập project property Gradle | Dùng `bootRun.systemProperty('demo.mode', project.findProperty('demoMode'))` |
| Tăng `org.gradle.jvmargs` để tăng heap ứng dụng | Tùy chọn đó điều chỉnh JVM của Gradle | Đặt `bootRun.jvmArgs '-Xmx...'` hoặc VM options của lệnh `java`/IDE |
| Đặt `--spring.profiles.active=dev` trong VM options | Đây là đối số/cấu hình Spring Boot, không phải VM option của Java launcher | Đặt trong Program arguments hoặc `bootRun --args` |
| Dùng `System.getProperty("server.port")` để kiểm tra `--server.port=9090` | Đối số dòng lệnh mặc định nằm trong `Environment`, không tự ghi vào JVM system properties | Dùng `Environment.getProperty("server.port")` hoặc `ApplicationArguments` |

## 7. Quy trình kiểm tra khi ứng dụng không nhận tham số

1. **Xác định cách chạy:** `java -jar`, chạy lớp `main` trong IDE hay `./gradlew bootRun`? Điều này quyết định có tiến trình Gradle ở giữa hay không.
2. **Tìm đúng người nhận:** cần thay đổi heap/JVM system property, cấu hình Gradle hay giá trị Spring Boot nhận trong ứng dụng?
3. **Kiểm tra vị trí và cách chuyển:** VM options đặt trước `-jar`/lớp chính; với `bootRun` dùng `jvmArgs`/`systemProperty` cho JVM đích và `--args` cho đối số ứng dụng; `-P` chỉ có tác dụng tới ứng dụng khi được ánh xạ.
4. **Đọc đúng API:** `System.getProperty` cho JVM; `ApplicationArguments` cho đối số; `Environment` cho thuộc tính Spring; `project.findProperty` trong build script cho Gradle.
5. **Kiểm tra độ ưu tiên nếu trùng tên:** một giá trị `--key=value` có thể thắng `-Dkey=value` khi đọc qua `Environment`, trong khi `System.getProperty` vẫn giữ giá trị JVM.

**Tự luyện tập:** Trước khi chạy, hãy dự đoán hai dòng chương trình `LaunchArgsDemo` sẽ in với các lệnh (a) `java -Ddemo.mode=fast LaunchArgsDemo a.txt` và (b) `java LaunchArgsDemo -Ddemo.mode=fast a.txt`. Sau đó thử chạy để kiểm chứng. Với một dự án Spring Boot, hãy so sánh `Environment.getProperty("demo.mode")` và `System.getProperty("demo.mode")` khi cùng truyền `-Ddemo.mode=jvm` và `--demo.mode=cli`. Nếu giải thích được kết quả bằng **đúng tiến trình, đúng vị trí, đúng API**, bạn đã phân biệt được ba loại tham số.

### Tài liệu tham khảo

- Spring Boot — Running Your Application with Gradle: https://docs.spring.io/spring-boot/gradle-plugin/running.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Gradle — Build Environment Configuration: https://docs.gradle.org/current/userguide/build_environment.html
