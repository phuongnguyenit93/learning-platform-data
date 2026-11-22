# Đọc `META-INF/MANIFEST.MF` và phân biệt `Main-Class` với `Start-Class`

**Câu hỏi cốt lõi:** Khi chạy `java -jar app.jar`, JVM gọi class nào đầu tiên? Trong một **executable Spring Boot JAR**, vì sao manifest lại có cả `Main-Class` và `Start-Class`, và tên class nào mới là class chứa `@SpringBootApplication`?

**Đáp án ngắn:**

- **`Main-Class`** là thuộc tính chuẩn của định dạng Java JAR. Java launcher đọc giá trị này khi chạy `java -jar` và gọi phương thức `public static void main(String[] args)` của class được chỉ định. Với executable Spring Boot JAR thông dụng, giá trị là **Spring Boot launcher**, ví dụ `org.springframework.boot.loader.launch.JarLauncher` ở Spring Boot 3.3.
- **`Start-Class`** là thuộc tính **riêng mà Spring Boot launcher sử dụng** để tìm class ứng dụng thực sự, ví dụ `com.example.demo.ManifestDemoApplication`. JVM không tự diễn giải `Start-Class` như entry point chuẩn; **Boot launcher** đọc nó sau khi được gọi.
- **`META-INF/MANIFEST.MF`** là file metadata trong archive JAR. Nó giúp xác định entry point và có thể chứa các thuộc tính bổ sung. Chỉ đọc manifest **chưa đủ** để khẳng định archive chứa mọi class/dependency cần để chạy; phải kiểm tra cả nội dung và chạy artifact.

Bài học nằm trong bối cảnh **JAR thực thi** của Spring Boot, tập trung vào thao tác đọc manifest, hiểu cơ chế nạp class và chẩn đoán lỗi entry point. Các ví dụ dùng **Java 17+**, Spring Boot **3.3.5** và một phiên bản Gradle tương thích làm phiên bản cố định để tái hiện; đây **không phải** tuyên bố về bản Spring Boot mới nhất.

## 1. Manifest của JAR là gì?

JAR (*Java ARchive*) là archive theo định dạng ZIP chứa class, resources và metadata. Một JAR có thể có file `META-INF/MANIFEST.MF`. File này tuân theo cú pháp các cặp thuộc tính:

~~~text
Attribute-Name: Attribute value
Another-Attribute: Another value

~~~

Phần đầu của manifest chứa các **main attributes** dùng ở phạm vi archive. Có thể có các section bổ sung cho những entry cụ thể. `Manifest-Version` mô tả phiên bản định dạng manifest; `Main-Class` là thuộc tính được Java launcher hiểu cho executable JAR thông thường.

### Ví dụ một manifest Java JAR thuần

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Hello

~~~

Với cấu trúc này, nếu `com.example.Hello` tồn tại trong archive và có phương thức main hợp lệ, Java có thể thực hiện:

~~~bash
java -jar hello.jar
~~~

`Main-Class` trỏ **trực tiếp** tới class ứng dụng. JAR thuần không bắt buộc có `Start-Class` và Java launcher không cần thuộc tính đó.

### Ví dụ một manifest Spring Boot executable JAR

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.demo.ManifestDemoApplication
Spring-Boot-Version: 3.3.5
Spring-Boot-Classes: BOOT-INF/classes/
Spring-Boot-Lib: BOOT-INF/lib/

~~~

Đây là **một mẫu các thuộc tính quan trọng có thể xuất hiện**, không phải bản chép nguyên văn của mọi JAR Boot. Các thuộc tính phụ và thứ tự có thể khác tùy Spring Boot plugin, Gradle/Maven, archive layout hoặc cấu hình build. Điểm mấu chốt là hai dòng:

- `Main-Class` → class bootstrap/launcher của Spring Boot;
- `Start-Class` → class do người phát triển viết, chứa phương thức `main`.

Không đặt thêm phần đuôi `.class` hoặc dấu gạch chéo path vào tên class trong hai thuộc tính này: cả hai dùng tên **fully qualified Java class**, chẳng hạn `com.example.demo.ManifestDemoApplication`.

### Cẩn thận khi đọc text manifest

Manifest là file text có quy tắc riêng:

1. Tên thuộc tính và giá trị được ngăn bằng dấu hai chấm và khoảng trắng.
2. Dòng dài có thể **bị gấp (fold)** sang dòng vật lý kế tiếp, bắt đầu bằng **một dấu cách**; đó vẫn là cùng một giá trị logic.
3. Các section có thể phân tách bằng dòng trống, và line ending có thể không giống cách một text editor hiển thị.
4. Tên/giá trị lạ có thể là thuộc tính do framework hoặc công cụ build quy định, không có nghĩa Java launcher hỗ trợ nó.
5. Nếu muốn đọc một cách chính xác trên mọi hệ điều hành, có thể dùng Java API `java.util.jar.JarFile` và `java.util.jar.Manifest` thay vì tự split từng dòng.

**Không** tự viết parser giả định “mỗi dòng là một thuộc tính hoàn chỉnh”; các giá trị dài có thể khiến cách đọc đó báo kết quả sai.

## 2. `Main-Class` là entry point Java chuẩn

Khi dùng:

~~~bash
java -jar my-application.jar
~~~

Java launcher mở JAR, tìm main section trong `META-INF/MANIFEST.MF`, đọc `Main-Class` và cố gắng chạy class tương ứng có phương thức:

~~~java
public static void main(String[] args)
~~~

Đây là điểm vào của tiến trình Java theo cơ chế `-jar`. Nếu `Main-Class` vắng mặt, Java launcher thường báo lỗi tương tự:

~~~text
no main manifest attribute, in my-application.jar
~~~

Nếu class được chỉ định không tồn tại trong classpath mà launcher có thể nhìn thấy, hoặc không có main method hợp lệ, ứng dụng cũng không thể khởi động bình thường. Thông điệp cụ thể có thể khác theo Java version và nguyên nhân.

### `Main-Class` không phải khái niệm của annotation Spring Boot

Annotation `@SpringBootApplication` trên một class **không tự khiến Java launcher chọn class đó**. Annotation hỗ trợ Spring Boot cấu hình và auto-configuration; lựa chọn class vào `java -jar` được điều khiển trước hết bởi manifest và cơ chế Boot launcher. Vì vậy:

- Một JAR thuần có thể có `Main-Class: com.example.Hello` mà không sử dụng Spring.
- Một Boot JAR có thể có `Main-Class: ...JarLauncher` trong khi class annotated `@SpringBootApplication` được ghi ở `Start-Class`.
- Chỉ đặt `Start-Class` trong JAR thuần nhưng thiếu `Main-Class` **không** làm `java -jar` chạy được.

### Có thể dùng `java -cp` thay cho `java -jar` không?

Cú pháp:

~~~bash
java -cp path/to/classes com.example.Hello
~~~

truyền **class trực tiếp** để JVM chạy thay vì yêu cầu JVM lấy entry point từ `Main-Class` của JAR. Với `java -jar`, `-cp` không hoạt động như cơ chế ghép classpath tùy ý của `java -cp`; Java launcher dùng archive `-jar` và các quy tắc đi kèm. Spring Boot executable JAR còn có nested dependencies và loader riêng, nên không thể đơn giản thay `java -jar boot.jar` bằng `java -cp boot.jar com.example.demo.ManifestDemoApplication` mà mong behavior tương đương.

## 3. `Start-Class` là chỉ dẫn của Spring Boot launcher

Với **executable Spring Boot JAR** có cấu trúc mặc định, Spring Boot launcher làm công việc mà Java launcher thuần không tự thực hiện: mở cấu trúc bên trong archive, tạo class loader có thể thấy **class ứng dụng và nested dependency JAR**, rồi gọi class ứng dụng thực sự.

Dòng điều khiển:

~~~text
Người dùng
  |
  v
java -jar manifest-demo.jar
  |
  v
JVM đọc META-INF/MANIFEST.MF
  |
  +-- Main-Class = org.springframework.boot.loader.launch.JarLauncher
  |       |
  |       v
  |   JVM chạy main() của JarLauncher
  |       |
  |       +-- Boot launcher xác lập classpath:
  |       |      BOOT-INF/classes/
  |       |      BOOT-INF/lib/*.jar (nested JARs)
  |       |
  |       +-- Đọc Start-Class từ manifest
  |       |      com.example.demo.ManifestDemoApplication
  |       |
  |       v
  |   Loader gọi main(String[] args) của application
  |       |
  |       v
  |   SpringApplication.run(...) khởi tạo Spring context
  |
  v
Ứng dụng bắt đầu chạy
~~~

Điều cần nhớ: **JVM dùng `Main-Class` để biết ai chạy trước; Spring Boot loader dùng `Start-Class` để biết main class ứng dụng là ai.**

`Start-Class` là một thuộc tính manifest tùy biến hợp lệ: Java không coi nó là entry point chuẩn, nhưng framework có thể đọc nó. Spring Boot build plugins thông thường sẽ xác định application main class, ghi `Start-Class` và đặt `Main-Class` thành Boot launcher tương ứng.

### Vì sao cần launcher trung gian?

Một executable Boot JAR thường không “bung” mọi dependency vào một thư mục class đơn nhất. Nó dùng nested JARs để giữ phụ thuộc theo artifact. Java launcher thông thường không tự hiểu nested JAR ở `BOOT-INF/lib` như những JAR độc lập trên classpath truyền bằng `-cp`. Spring Boot launcher thực hiện bước nạp chuyên dụng để có thể chạy archive trực tiếp.

Vì vậy **`Main-Class` trỏ tới JarLauncher không phải dấu hiệu sai**: đó là thiết kế của executable Spring Boot JAR. Nếu bạn sửa nó thành class ứng dụng trong khi vẫn giữ layout mặc định `BOOT-INF/...`, JVM thuần có thể không tìm thấy class hoặc dependency. Thay đổi manifest thủ công không đồng nghĩa thay đổi archive layout/class loading.

## 4. Đọc cấu trúc archive song song với manifest

Một executable Spring Boot JAR phổ biến:

~~~text
manifest-demo.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/JarLauncher.class
└── BOOT-INF/
    ├── classes/
    │   └── com/example/demo/ManifestDemoApplication.class
    ├── lib/
    │   ├── spring-boot-<version>.jar
    │   ├── spring-context-<version>.jar
    │   └── các thư viện runtime khác
    └── classpath.idx                    (có thể có)
~~~

Cây trên là **sơ đồ**, không phải danh sách đầy đủ hoặc literal listing. Tên file thực tế trong `BOOT-INF/lib` chứa version cụ thể, không chứa dấu `<version>`. Các file index, metadata layering và chi tiết loader có thể thay đổi theo plugin/version.

Đối chiếu:

| Kiểm tra | Thuộc tính/đường dẫn | Ý nghĩa |
| --- | --- | --- |
| JVM được yêu cầu chạy class nào? | `Main-Class` | Entry point theo Java launcher |
| Boot loader được yêu cầu chạy application class nào? | `Start-Class` | Entry point ứng dụng dưới cơ chế Boot loader |
| Loader bytecode có trong JAR không? | `org/springframework/boot/loader/...` | Có thành phần launcher phù hợp với manifest? |
| Class ứng dụng có được package không? | `BOOT-INF/classes/...` | Application class có mặt trong executable archive? |
| Thư viện runtime có được package không? | `BOOT-INF/lib/...` | Các nested dependency JAR cần thiết có mặt? |
| Build sử dụng Boot version nào? | `Spring-Boot-Version` nếu có | Metadata tham khảo; kiểm chứng bằng plugin và JAR thực tế |
| Có thông tin classpath order/layering không? | Index files/manifest attributes khi có | Metadata phụ thuộc layout/build; không quyết định application main class |

`Main-Class` và `Start-Class` **chỉ là metadata**. Chúng không chứng minh file class có thật hoặc đúng bytecode. Hãy đọc cả danh sách entry nếu có lỗi khi chạy.

### `JarLauncher`, `WarLauncher` và `PropertiesLauncher`

Trong Spring Boot 3.3:

- `org.springframework.boot.loader.launch.JarLauncher`: launcher cho executable JAR, tìm ứng dụng ở `BOOT-INF/classes` và dependency ở `BOOT-INF/lib`.
- `org.springframework.boot.loader.launch.WarLauncher`: launcher cho executable WAR, dùng layout `WEB-INF/classes`, `WEB-INF/lib` và `WEB-INF/lib-provided` phù hợp.
- `org.springframework.boot.loader.launch.PropertiesLauncher`: launcher linh hoạt hơn, hỗ trợ cấu hình các vị trí thư viện bên ngoài thông qua các lựa chọn `loader.path` và metadata tương ứng khi được dùng.

Đừng mặc định mọi archive Boot đều có cùng giá trị `Main-Class`. Muốn biết launcher nào đang hoạt động, hãy **đọc manifest của đúng artifact**. Với WAR được deploy vào **external servlet container**, cơ chế startup có thể không phải trực tiếp `java -jar`, nên vai trò của launcher và Servlet initializer cần được phân biệt theo kịch bản.

### Cẩn thận với phiên bản Spring Boot

Trong Spring Boot 3.3, tên launcher điển hình là `org.springframework.boot.loader.launch.JarLauncher`. Các phiên bản cũ (ví dụ Spring Boot 2.x và 3.0) dùng đường dẫn như `org.springframework.boot.loader.JarLauncher`. **Cả hai tên đều có thể đúng trong artifact thuộc version tương ứng.**

Không tự “sửa” manifest Boot 2.x thành tên lớp launcher của Boot 3.3 khi bytecode loader bên trong JAR không chứa class đó. Sau nâng cấp, so sánh **version plugin, manifest và nội dung archive**; không dùng một ví dụ trên Internet làm chuẩn cứng cho mọi release.

## 5. Ba cách đọc `META-INF/MANIFEST.MF`

### 5.1. Kiểm tra JAR có entry manifest bằng JDK

JDK có sẵn công cụ `jar`:

~~~bash
jar tf build/libs/manifest-demo.jar
~~~

`jar tf` chỉ **liệt kê entry** trong archive, không in nội dung manifest. Trong output, tìm dòng:

~~~text
META-INF/MANIFEST.MF
~~~

Nếu không thấy dòng này, hãy xác minh đúng file được mở (executable Boot JAR, plain JAR hay file khác). Sự hiện diện của entry chỉ chứng minh có file manifest, **không chứng minh giá trị hai thuộc tính đúng**.

### 5.2. Xem trực tiếp bằng `unzip -p` khi có utility

Trên Linux/macOS hoặc hệ thống đã cài `unzip`:

~~~bash
unzip -p build/libs/manifest-demo.jar META-INF/MANIFEST.MF
~~~

`-p` đưa nội dung entry ra stdout mà không cần giải nén archive ra filesystem. Đây là cách nhanh để xem bản văn. Nếu chỉ cần so `Main-Class` và `Start-Class`, tìm hai dòng cùng tên trong output; nếu giá trị bị wrap, phải ghép continuation line cho đúng. Trên Windows không có `unzip` ở mọi môi trường, nên có thể dùng Java inspector ở mục tiếp theo.

### 5.3. Giải nén đúng một entry bằng lệnh JDK `jar xf`

Ví dụ trên Linux/macOS:

~~~bash
mkdir -p inspect-manifest
cd inspect-manifest
jar xf ../build/libs/manifest-demo.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
~~~

Ở đây `inspect-manifest/` được tạo từ thư mục gốc của project và file JAR nằm trong `../build/libs/`. Dùng thư mục riêng để tránh vô tình **ghi đè `META-INF/MANIFEST.MF` hiện có** trong project. `jar xf` tạo file ở filesystem, còn `unzip -p` chỉ in nội dung. Không chạy giải nén toàn bộ archive chỉ để xem hai thuộc tính.

Windows có thể dùng `jar xf` tương tự, rồi `Get-Content .\META-INF\MANIFEST.MF` trong PowerShell, nhưng cách phổ biến và ít phụ thuộc shell nhất vẫn là dùng Java API.

## 6. Viết một Java 17 manifest inspector thật sự chạy được

Java API cho phép đọc thuộc tính logic từ manifest, bao gồm cả giá trị bị fold qua nhiều dòng, mà không phải tự phân tích text.

Tạo file **`ManifestInspector.java`** ở một thư mục bất kỳ:

~~~java
import java.io.IOException;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class ManifestInspector {
    private ManifestInspector() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java ManifestInspector <path-to-jar>");
            System.exit(2);
        }

        try (JarFile jar = new JarFile(args[0])) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                System.out.println("MANIFEST_MISSING");
                return;
            }

            Attributes attributes = manifest.getMainAttributes();

            System.out.println("Main-Class=" +
                    show(attributes.getValue(Attributes.Name.MAIN_CLASS)));
            System.out.println("Start-Class=" +
                    show(attributes.getValue("Start-Class")));
        }
    }

    private static String show(String value) {
        return value == null ? "(absent)" : value;
    }
}
~~~

Đây là **chương trình Java độc lập**, không cần Spring Boot dependency. Nó làm hai việc:

1. Dùng `JarFile#getManifest()` để đọc manifest từ archive được truyền qua command line.
2. Dùng `Attributes#getValue(Attributes.Name.MAIN_CLASS)` và `getValue("Start-Class")` để truy xuất hai trường. Với JAR không có `Start-Class`, chương trình in `(absent)`.

Biên dịch bằng JDK 17+:

~~~bash
javac ManifestInspector.java
~~~

Khi đã build executable Spring Boot JAR như ví dụ ở phần tiếp theo:

~~~bash
java ManifestInspector build/libs/manifest-demo.jar
~~~

Hai dòng kết quả **dự kiến cho ví dụ Spring Boot 3.3.5 bên dưới**:

~~~text
Main-Class=org.springframework.boot.loader.launch.JarLauncher
Start-Class=com.example.demo.ManifestDemoApplication
~~~

Chương trình sẽ in **giá trị thực tế** trong artifact bạn truyền vào, không hard-code hai class name. Nếu bạn đưa một plain Java JAR được tạo bằng `jar --main-class`, nó thường in `Start-Class=(absent)`. Nếu JAR không tồn tại hoặc không hợp lệ, `JarFile` báo lỗi; không nên coi đó là trường hợp manifest không có.

**Vì sao dùng `JarFile`?** Nó hiểu cấu trúc ZIP/JAR và parser manifest chuẩn (bao gồm continuation lines). Bạn có thể mở rộng inspector để in thêm `Spring-Boot-Version` hoặc `Spring-Boot-Classes`, nhưng đó là thuộc tính tùy biến và có thể không xuất hiện trong mọi archive.

## 7. Thí nghiệm 1 — JAR Java thuần: chỉ cần `Main-Class`

Trước khi xem Spring Boot, tạo một JAR Java 17+ không phụ thuộc thư viện ngoài. Tạo file **`Hello.java`**:

~~~java
public final class Hello {
    public static void main(String[] args) {
        System.out.println("HELLO_FROM_PLAIN_JAR");
    }
}
~~~

Trong thư mục chứa `Hello.java`, trên Linux/macOS:

~~~bash
mkdir -p classes
javac -d classes Hello.java
jar --create --file hello.jar --main-class Hello -C classes .
java -jar hello.jar
~~~

Stdout do ứng dụng in:

~~~text
HELLO_FROM_PLAIN_JAR
~~~

Nếu chạy inspector đã biên dịch ở cùng thư mục:

~~~bash
java ManifestInspector hello.jar
~~~

Kết quả:

~~~text
Main-Class=Hello
Start-Class=(absent)
~~~

Giải thích: `jar --main-class Hello` ghi entry point chuẩn vào manifest. `Hello.class` được đặt ở root của JAR vì class này nằm trong **default package**; ví dụ chỉ để minh họa tối thiểu. Trong project Java thực tế, nên dùng package có tên rõ ràng.

Bạn có thể xem manifest bằng `unzip -p hello.jar META-INF/MANIFEST.MF` hoặc các cách ở mục 5. **Không thêm `Start-Class` cho JAR thuần để “bắt chước Spring Boot”** — JVM chuẩn không đọc thuộc tính đó.

## 8. Thí nghiệm 2 — Spring Boot 3.3: `Main-Class` trỏ loader, `Start-Class` trỏ ứng dụng

Ví dụ sử dụng Gradle **Groovy DSL**, Java 17 và Spring Boot 3.3.5. Nó tạo executable JAR thực sự, in một dòng để xác nhận class `main` đã được Boot launcher gọi.

Cấu trúc thư mục:

~~~text
manifest-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── com/example/demo/ManifestDemoApplication.java
~~~

### 8.1. File `settings.gradle`

~~~groovy
rootProject.name = 'manifest-demo'
~~~

### 8.2. File `build.gradle` — cấu hình đầy đủ

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.demo.ManifestDemoApplication'
}

tasks.named('bootJar') {
    archiveFileName.set('manifest-demo.jar')
}
~~~

Ý nghĩa:

- `java` và `org.springframework.boot` plugin thiết lập build tasks, gồm `bootJar`.
- `io.spring.dependency-management` giúp quản lý dependency versions của Boot trong dự án này.
- `spring-boot-starter` tạo đủ Spring Boot runtime cơ bản, **không** thêm web server vì không dùng web starter.
- `springBoot { mainClass = ... }` xác định application main class bằng tên fully qualified, tránh phụ thuộc auto-detection khi dự án có nhiều main methods.
- `tasks.named('bootJar')` chỉ đổi output file name; **Spring Boot plugin** chịu trách nhiệm manifest/launcher/layout cho executable JAR.
- Không tự gán `Main-Class` thành class ứng dụng. Mục đích là để plugin ghi `Main-Class=JarLauncher` và `Start-Class=ManifestDemoApplication` đúng cơ chế.

Ví dụ này cố định version 3.3.5 để người học so sánh kết quả; dự án sản xuất phải dùng một bộ Gradle/Spring Boot/JDK phù hợp với chính sách hỗ trợ hiện tại.

### 8.3. File `src/main/java/com/example/demo/ManifestDemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ManifestDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ManifestDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner marker() {
        return args -> System.out.println("BOOT_MAIN_CALLED");
    }
}
~~~

Code đúng Java 17+, tên `public class` trùng tên file. `main` được gọi thông qua launcher khi ứng dụng chạy từ executable Boot JAR. Sau khi khởi tạo Spring context, `CommandLineRunner` in một dòng marker.

### 8.4. Build và đọc manifest

Giả định đã có Gradle Wrapper tương thích với Spring Boot 3.3.5 (ví dụ Gradle 8.7). Trên Linux/macOS:

~~~bash
./gradlew clean bootJar
jar tf build/libs/manifest-demo.jar
unzip -p build/libs/manifest-demo.jar META-INF/MANIFEST.MF
~~~

`jar tf` liệt kê archive entries; `unzip -p` in manifest khi utility `unzip` có sẵn. Các dòng **cần thấy trong manifest của artifact ví dụ này**:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.demo.ManifestDemoApplication
~~~

Manifest có thể có thêm các trường như `Manifest-Version`, `Spring-Boot-Version`, `Spring-Boot-Classes`, `Spring-Boot-Lib`, các thuộc tính liên quan build metadata và index. Không nên kiểm tra bằng cách yêu cầu file manifest đúng số dòng, đúng thứ tự hay đúng mọi metadata phụ.

Nếu đã lưu file `ManifestInspector.java` từ mục 6 ở thư mục project (hoặc đặt được vào thư mục công cụ riêng), có thể biên dịch và đọc:

~~~bash
javac ManifestInspector.java
java ManifestInspector build/libs/manifest-demo.jar
~~~

Stdout có đúng hai dòng ở mục 6.

### 8.5. Chạy executable Boot JAR

~~~bash
java -jar build/libs/manifest-demo.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Dòng do **ứng dụng** in khi khởi động thành công:

~~~text
BOOT_MAIN_CALLED
~~~

Các dòng do Gradle, Spring Boot hoặc JVM in thêm có thể thay đổi theo môi trường; đầu ra trên chỉ là marker do `CommandLineRunner` in, không phải cam kết toàn bộ stdout chỉ gồm một dòng. Vì dùng `spring-boot-starter` cơ bản và không có web server, ứng dụng kết thúc sau khi runner hoàn thành.

**Chuỗi sự kiện thực tế:**

1. JVM đọc `Main-Class` và chạy `JarLauncher.main(...)`.
2. Boot loader chuẩn bị class loader cho `BOOT-INF/classes` và các nested JAR trong `BOOT-INF/lib`.
3. Loader lấy `Start-Class` để xác định `ManifestDemoApplication`.
4. Loader gọi `ManifestDemoApplication.main(...)`.
5. Application gọi `SpringApplication.run(...)`, Spring context được khởi tạo.
6. `CommandLineRunner` in `BOOT_MAIN_CALLED`.

Chạy `./gradlew bootRun` là con đường khác: Gradle khởi động ứng dụng từ runtime classpath khi phát triển; không nhất thiết đi qua manifest/executable JAR. Muốn kiểm tra đúng `Main-Class`/`Start-Class` của artifact, phải **build và chạy chính JAR đó**.

### 8.6. Kiểm tra bytecode để chứng minh class thật sự có trong archive

~~~bash
jar tf build/libs/manifest-demo.jar
~~~

Trong danh sách dài, tìm các entry có ý nghĩa:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/com/example/demo/ManifestDemoApplication.class
BOOT-INF/lib/...
~~~

Dòng `BOOT-INF/lib/...` là **ký hiệu minh họa** cho các JAR nested, không phải literal entry của lệnh `jar tf`. Nếu `Start-Class` ghi class ứng dụng nhưng không tìm thấy class tương ứng trong `BOOT-INF/classes` hoặc một vị trí mà launcher nạp, hãy xem task `bootJar` đang đóng gói đúng module/source set hay chưa.

### 8.7. Windows PowerShell

Dùng `.\gradlew.bat` thay `./gradlew`. Các lệnh `java`, `javac` và `jar` có trong JDK; `unzip` có thể chưa cài. Java inspector chạy bằng `java ManifestInspector build\libs\manifest-demo.jar` sau khi biên dịch là cách không phụ thuộc `unzip`. Đối số ứng dụng khi chạy `java -jar` có thể đặt trên một dòng để tránh khác biệt cú pháp xuống dòng của shell.

## 9. Maven: đọc kết quả `spring-boot:repackage`

Maven dùng `spring-boot-maven-plugin` để tạo executable Boot archive bằng goal `repackage`. Khi kết hợp với `spring-boot-starter-parent`, plugin thường nhận được phiên bản và execution mặc định từ parent, nhưng bạn vẫn phải **kích hoạt plugin** ở `<build><plugins>` trong cấu hình ứng dụng (hoặc có cơ chế kế thừa/kích hoạt khác tương đương).

Ví dụ `pom.xml` hoàn chỉnh cho đúng Java application ở mục 8:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>manifest-demo</artifactId>
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
                <configuration>
                    <mainClass>com.example.demo.ManifestDemoApplication</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Lưu ý đây là **phương án Maven thay thế** cho `build.gradle`; không cần giữ cả hai build systems cho cùng ví dụ. File Java ở `src/main/java/com/example/demo/ManifestDemoApplication.java` giữ nguyên.

Chạy:

~~~bash
mvn clean package
jar tf target/manifest-demo-1.0.0.jar
java -jar target/manifest-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Dòng do ứng dụng in:

~~~text
BOOT_MAIN_CALLED
~~~

Với starter parent và plugin cấu hình ở trên, `repackage` tạo Boot executable JAR và manifest có ý nghĩa giống phần Gradle: **`Main-Class` là launcher, `Start-Class` là application class**. Tên file JAR phụ thuộc `artifactId`/`version`, `finalName` và classifier khi có; ví dụ trên dự kiến `target/manifest-demo-1.0.0.jar`.

### BOM khác plugin packaging

Nếu Maven project **chỉ import `spring-boot-dependencies` BOM** mà không dùng starter parent, BOM chủ yếu giúp quản lý **dependency versions**. Nó **không tự gắn execution `repackage`** vào lifecycle; phải cấu hình `spring-boot-maven-plugin`, version và execution phù hợp nếu muốn executable JAR.

Nếu bạn build `mvn package` nhưng không có `repackage`, file tạo bởi `maven-jar-plugin` có thể là **plain JAR**, manifest không có `Start-Class` và không chạy được bằng `java -jar` như executable Boot JAR. Không chỉnh manifest thủ công để bù cho thiếu build plugin: phải sửa pipeline packaging trước.

## 10. Cấu hình đúng application main class

### Gradle Groovy DSL

Trong project đã áp dụng Spring Boot plugin:

~~~groovy
springBoot {
    mainClass = 'com.example.demo.ManifestDemoApplication'
}
~~~

Hoặc cấu hình riêng task `bootJar`:

~~~groovy
tasks.named('bootJar') {
    mainClass.set('com.example.demo.ManifestDemoApplication')
}
~~~

Hai đoạn trên là **hai vị trí cấu hình có thể lựa chọn**; không nên đặt hai giá trị khác nhau khi không có lý do. Giá trị chính là class ứng dụng sẽ được ghi dưới `Start-Class` cho executable Boot JAR. Spring Boot plugin thường phát hiện main class có `public static void main(String[])` nếu project chỉ có một class phù hợp; cấu hình tường minh giúp tránh ambiguity.

### Gradle Kotlin DSL

Nếu dùng `build.gradle.kts` thay `build.gradle`:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    mainClass.set("com.example.demo.ManifestDemoApplication")
}
~~~

Đây là snippet Kotlin DSL đặt trong project đã áp dụng Boot/Java plugins. Không chép cú pháp generic `named<BootJar>` vào Groovy DSL.

### Maven

Trong `spring-boot-maven-plugin`:

~~~xml
<configuration>
    <mainClass>com.example.demo.ManifestDemoApplication</mainClass>
</configuration>
~~~

Khi goal `repackage` chạy, plugin dùng giá trị application main class để tạo `Start-Class` phù hợp. Đừng nhầm parameter `mainClass` của plugin với thuộc tính manifest chuẩn `Main-Class`. Cùng tên “main class” trong giao diện cấu hình plugin nhưng **plugin còn phải sinh launcher entry point** để executable archive chạy được.

### Khi có nhiều `main()` trong một module

Nếu code có `Application.java`, `ImportTool.java` và `MigrationTool.java`, mỗi class đều có `public static void main(String[])`, khả năng auto-detection có thể không xác định được một class duy nhất hoặc chọn class không như dự kiến (tùy build plugin/version). Thiết lập một class phù hợp cho **archive cần phân phối**:

~~~text
Spring Boot executable JAR dùng khi triển khai:
Start-Class: com.example.demo.ManifestDemoApplication

Công cụ import chạy độc lập:
com.example.tools.ImportTool
~~~

Không cố tạo một manifest có nhiều dòng `Start-Class` để chọn ứng dụng bằng ý muốn. Một executable Boot JAR được đóng gói với một main application class cụ thể; nếu cần nhiều entry points, cân nhắc tạo các task/artifact riêng và đặt tên/launcher rõ ràng.

### Một lưu ý cho Kotlin application

Với Kotlin, top-level `fun main` thường được biên dịch thành class JVM có hậu tố `Kt` (trừ khi đổi bằng `@JvmName`). Vì vậy giá trị main class cho Spring Boot Gradle/Maven plugin phải là **tên class JVM thực tế**, không nhất thiết trùng tên file nguồn không có hậu tố. Kiểm tra archive bytecode khi cấu hình Kotlin.

## 11. Những lỗi phổ biến khi đọc hoặc sửa manifest

| Triệu chứng | Nguyên nhân cần xem | Cách kiểm chứng/sửa |
| --- | --- | --- |
| `no main manifest attribute` | JAR không có `Main-Class` hợp lệ | Dùng inspector; xem có chạy nhầm plain JAR hoặc thiếu `bootJar`/`repackage` |
| `Could not find or load main class ...JarLauncher` | `Main-Class` trỏ launcher không tồn tại trong archive, sai Boot version hoặc JAR bị sửa hỏng | Đọc manifest, dùng `jar tf` tìm đúng launcher class path |
| Lỗi nạp application class ghi ở `Start-Class` | Sai fully qualified name; class không có trong archive; cấu hình mainClass sai | So `Start-Class` với `BOOT-INF/classes/<package-path>.class` |
| `Start-Class` bị thiếu trong Boot JAR | Packaging không đúng kiểu, manifest bị custom override hoặc đang xem sai artifact | Xác minh `bootJar`/`repackage`, file output, class main configuration |
| `Main-Class` trỏ trực tiếp tới application trong Boot nested layout | Manifest custom ghi đè launcher | Để Boot plugin sinh launcher; sửa cấu hình plugin thay vì sửa manifest thủ công |
| `Main-Class` là `org.springframework.boot.loader.JarLauncher` nhưng ví dụ dạy tên `...loader.launch.JarLauncher` | Artifact thuộc Spring Boot đời cũ | Kiểm tra Spring Boot version và launcher class thực sự |
| `Start-Class` là đúng tên nhưng app lỗi `NoClassDefFoundError` | Một dependency khác thiếu/không tương thích | Kiểm tra `BOOT-INF/lib` và dependency graph, đọc `Caused by` |
| `UnsupportedClassVersionError` | JVM runtime cũ hơn bytecode của application/loader/dependency | So `java --version` và Java toolchain/target |
| Đã sửa `build.gradle` nhưng manifest không đổi | Chạy JAR của lần build cũ, task up-to-date, nhầm output hoặc multi-module | Build clean đúng module, đọc đúng file path/classifier |
| Không thấy `META-INF/MANIFEST.MF` qua `jar tf` | Mở nhầm file hoặc archive không đúng | Xác định đúng artifact và file type |
| Dòng manifest dài bị xuống dòng lạ | Manifest có continuation lines theo spec | Đọc qua `JarFile#getManifest()` thay vì regex đơn giản |
| WAR deploy vào external Tomcat nhưng startup khác `java -jar` | Kịch bản external servlet container có cơ chế khởi động riêng | Kiểm tra packaging WAR, Servlet initializer và container runtime |

**Điểm cần phân biệt:** một lỗi khởi động sau `JarLauncher` không nhất thiết do `Start-Class` sai. Ví dụ loader gọi đúng main class nhưng `SpringApplication.run` không khởi tạo được datasource do credential hoặc network, thì hai thuộc tính manifest có thể hoàn toàn chính xác. Phải xem **exception gốc**.

### Mất class do nhầm plain JAR với Boot JAR

Spring Boot Gradle plugin có thể cho phép cả task `jar` và `bootJar` cùng tạo sản phẩm, thường với quy ước tên khác nhau (chẳng hạn classifier `plain` cho JAR thường ở các version Boot). Nếu người dùng chạy nhầm file `*-plain.jar`, biểu hiện có thể là `no main manifest attribute` hoặc thiếu runtime dependencies. Giải pháp là kiểm tra đúng artifact của task cần chạy, **không** mặc định mọi `.jar` trong `build/libs` đều là executable Boot JAR.

### Không sửa manifest bằng cách kéo thả file ZIP

Manifest là metadata được toolchain tạo và có thể liên quan chữ ký, reproducible build và class loader. Thay đổi file manifest trong archive đã build có thể phá tính nhất quán của artifact, làm mất chữ ký hoặc dẫn tới mismatch với các entry còn lại. Nếu cần đổi main class, **thay cấu hình build plugin rồi rebuild và kiểm chứng**. Nếu muốn tạo JAR thường không dùng launcher Boot, dùng đúng task/plugin của Java packaging thay vì sửa `Main-Class` ngẫu nhiên.

### `Class-Path` manifest có phải thay `BOOT-INF/lib` không?

Với ordinary Java JAR, manifest có thể chứa thuộc tính chuẩn `Class-Path` trỏ các JAR bên ngoài theo quy tắc Java. Với executable Spring Boot JAR dùng `JarLauncher`, classpath cho nested dependencies được launcher xác lập từ cấu trúc archive; **không cần tự liệt kê từng nested JAR ở `Class-Path`**. Việc thêm thủ công các entry `Class-Path` kiểu `BOOT-INF/lib/x.jar` không thay thế cơ chế của Spring Boot loader.

## 12. Quy trình kiểm tra artifact trước khi triển khai

Khi nhận một JAR từ CI/CD, không dựa chỉ vào tên file. Dùng checklist:

1. **Xác định artifact chính xác.** Có thể là Boot executable JAR, plain JAR, executable WAR hoặc một file khác. Ghi lại tên, hash/version nếu quy trình release hỗ trợ.
2. **Xem manifest.** Dùng `JarFile` hoặc `unzip -p`; ghi giá trị `Main-Class` và `Start-Class`. Với Spring Boot 3.3 executable JAR thông thường, hai giá trị lần lượt là Boot `JarLauncher` và application class.
3. **Kiểm tra launcher tồn tại.** `jar tf` phải có class phù hợp với `Main-Class`. Đừng áp tên loader từ release mới lên archive cũ.
4. **Kiểm tra application class tồn tại.** Với default Boot JAR, path phải tương ứng `BOOT-INF/classes/com/example/.../Application.class`.
5. **Kiểm tra runtime libraries.** Quan sát `BOOT-INF/lib`; một manifest đúng nhưng thiếu dependency cần thiết vẫn có thể lỗi khi chạy.
6. **Chạy đúng artifact.** `java -jar file.jar` trong môi trường kiểm thử tương thích, truyền arguments/profiles cần thiết, đọc đầy đủ exception chain.
7. **Nếu cần đổi entry point, chỉnh build.** Gradle `springBoot.mainClass` hoặc `bootJar.mainClass`; Maven `spring-boot-maven-plugin.mainClass`. Rebuild, đọc manifest và chạy lại.
8. **Phân biệt lỗi manifest với lỗi runtime.** Sai `Main-Class`, sai `Start-Class`, thiếu class, Java version và môi trường cấu hình là những lớp khác nhau.

Một workflow ngắn với Gradle:

~~~bash
./gradlew clean bootJar
jar tf build/libs/manifest-demo.jar
java ManifestInspector build/libs/manifest-demo.jar
java -jar build/libs/manifest-demo.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Với Maven:

~~~bash
mvn clean package
jar tf target/manifest-demo-1.0.0.jar
java ManifestInspector target/manifest-demo-1.0.0.jar
java -jar target/manifest-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Lưu ý các lệnh inspector giả định bạn đã biên dịch `ManifestInspector.java` vào current classpath. Nếu đặt class ở một thư mục khác, chạy bằng `java -cp <directory-containing-inspector> ManifestInspector ...`. Đây là công cụ độc lập để kiểm tra archive và **không cần** khởi chạy ứng dụng mới đọc được manifest.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Trong manifest:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.demo.ManifestDemoApplication
~~~

JVM chạy class nào trước?

**Đáp án:** `JarLauncher` vì JVM đọc `Main-Class`. Sau đó Spring Boot loader đọc `Start-Class` và gọi `ManifestDemoApplication.main`.

**Câu 2.** Một plain Java JAR có `Main-Class: Hello` và không có `Start-Class`. Nó có thể chạy bằng `java -jar` không?

**Đáp án:** Có, nếu class `Hello` và main method hợp lệ cùng các dependency cần thiết có thể được nạp. `Start-Class` không phải thuộc tính bắt buộc của Java launcher.

**Câu 3.** Đặt duy nhất `Start-Class: com.example.App` trong một JAR thuần có đủ cho `java -jar` không?

**Đáp án:** Không. JVM Java launcher chuẩn cần `Main-Class`; nó không tự dùng `Start-Class`.

**Câu 4.** Vì sao một Boot JAR có `Main-Class=JarLauncher` nhưng class `ManifestDemoApplication` nằm sâu dưới `BOOT-INF/classes` vẫn chạy được?

**Đáp án:** Boot launcher hiểu layout executable JAR, tạo class loader cho `BOOT-INF/classes` và nested dependencies ở `BOOT-INF/lib`, rồi gọi application main.

**Câu 5.** Khi nào `org.springframework.boot.loader.JarLauncher` (không có `.launch.`) có thể là giá trị hợp lệ?

**Đáp án:** Với các thế hệ Spring Boot cũ có class loader theo package đó. Phải so với version và bytecode trong chính artifact, không áp cứng ví dụ của Boot 3.3.

**Câu 6.** `jar tf app.jar` cho biết cả nội dung `META-INF/MANIFEST.MF` chưa?

**Đáp án:** Chưa. Nó chỉ liệt kê tên entry. Dùng `unzip -p`, giải nén manifest riêng hoặc Java `JarFile#getManifest()` để xem giá trị.

**Câu 7.** Lỗi `ClassNotFoundException` sau khi loader đã gọi đúng `Start-Class` có luôn nghĩa là manifest sai?

**Đáp án:** Không. Có thể một library hoặc class bắc cầu bị thiếu, sai version hoặc bị exclude khỏi archive. Kiểm tra exception chain, `BOOT-INF/lib` và dependency graph.

**Câu 8.** Trong Spring Boot Gradle plugin, cần cấu hình gì để đổi tên class ứng dụng mà không tự phá `Main-Class`?

**Đáp án:** Đặt `springBoot.mainClass` hoặc `bootJar.mainClass` tới class hợp lệ, sau đó build lại. Boot plugin chịu trách nhiệm tạo manifest và launcher entry point đúng với executable layout.

## Tài liệu tham khảo

- [Spring Boot — Launching Executable Jars](https://docs.spring.io/spring-boot/3.4/specification/executable-jar/launching.html): `JarLauncher`/`WarLauncher`/`PropertiesLauncher`, `Main-Class` và `Start-Class`.
- [Spring Boot 3.3 — Gradle Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html): `bootJar`, main class, archive và manifest.
- [Spring Boot 3.3 — Maven Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html): `repackage` và main class.
- [Oracle Java 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): cú pháp manifest, `Main-Class`, line folding và `Class-Path`.
- [Spring Boot 3.2 — The Executable Jar Format](https://docs.spring.io/spring-boot/docs/3.2.x/reference/html/executable-jar.html): cấu trúc nested JAR và các launchers ở dòng Boot 3.2.

**Kết luận:** `Main-Class` là **entry point tiêu chuẩn mà Java launcher gọi**; `Start-Class` là **entry point ứng dụng do Spring Boot launcher sử dụng**. Với executable Spring Boot JAR mặc định, hai thuộc tính thường **cố ý khác nhau**. Hãy đọc manifest bằng công cụ phù hợp, kiểm tra class thực sự được đóng gói và chạy đúng artifact trước khi kết luận lỗi khởi động.
