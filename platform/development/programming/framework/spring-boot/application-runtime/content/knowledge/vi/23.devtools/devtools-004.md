# Điều kiện phát hiện thay đổi classpath và nhu cầu biên dịch lại trong Spring Boot Devtools

## 1. Mục tiêu và vấn đề thường gặp

Khi phát triển ứng dụng Spring Boot, ta thường mong muốn sửa code rồi thấy hành vi mới ngay mà không phải tự tắt và chạy lại server. **Spring Boot Devtools** cung cấp cơ chế **automatic restart** để rút ngắn vòng phản hồi này. Tuy nhiên, một hiểu nhầm phổ biến là:

> “Tôi đã lưu file Java trong IDE, tại sao Spring Boot không tự restart?”

Câu trả lời cốt lõi: **Devtools theo dõi thay đổi của các mục trong runtime classpath**, đặc biệt là những mục classpath trỏ đến **thư mục**. Nó **không đóng vai trò trình biên dịch Java** và không mặc định theo dõi trực tiếp mọi file mã nguồn trong `src/main/java`.

Để thay đổi Java code được Devtools nhận ra, thông thường phải đi qua chuỗi:

~~~mermaid
flowchart LR
    A["Sửa .java"] --> B["Lưu mã nguồn"]
    B --> C["IDE / Maven / Gradle biên dịch"]
    C --> D["File .class trong runtime classpath được cập nhật"]
    D --> E["Devtools FileSystemWatcher phát hiện thay đổi"]
    E --> F["Chờ quiet period"]
    F --> G["Đóng ApplicationContext cũ và restart"]
    G --> H["Context mới dùng bytecode mới"]
~~~

Nếu dừng ở bước **lưu `.java`** nhưng compiler chưa ghi `.class` vào đường dẫn đang được ứng dụng sử dụng, **không có cập nhật classpath có thể quan sát** để kích hoạt restart theo cơ chế chuẩn.

Bài này giải thích **điều kiện thật sự kích hoạt restart**, cách nhận biết thiếu bước compile, phân biệt classpath với mã nguồn, cấu hình exclude/trigger-file/watcher, điểm khác nhau giữa restart và LiveReload, cùng một dự án **Java 17+ / Spring Boot 3.5.x** có thể chạy và thử nghiệm.

## 2. Classpath trong thí nghiệm Devtools nghĩa là gì?

**Classpath** là tập hợp các thư mục và JAR mà JVM dùng để tìm class và resource của ứng dụng. Không phải mọi thư mục trong project đều tự động nằm trong runtime classpath.

Với Maven, cấu trúc điển hình:

~~~text
my-project/
├── pom.xml
├── src/
│   └── main/
│       ├── java/com/example/demo/
│       │   ├── DemoApplication.java
│       │   └── RevisionController.java
│       └── resources/
│           ├── application.properties
│           └── static/notice.txt
└── target/
    └── classes/
        ├── com/example/demo/
        │   ├── DemoApplication.class
        │   └── RevisionController.class
        ├── application.properties
        └── static/notice.txt
~~~

Trong một lần chạy development phổ biến qua `mvn spring-boot:run`:

- `src/main/java/.../RevisionController.java` là **nguồn** để compiler đọc.
- `target/classes/.../RevisionController.class` là **bytecode đã biên dịch**.
- `src/main/resources/application.properties` là **nguồn resource**.
- `target/classes/application.properties` là **bản resource được copy** vào output classpath.
- Các dependency JAR từ Maven repository là những classpath entries khác, thường được nạp từ lớp classloader khác.

Devtools nhìn vào **đường dẫn thực sự nằm trên classpath của process đang chạy**. Chỉ sửa file nguồn không có nghĩa chính process đó đang nhìn thấy một bytecode/resource mới.

### Với Gradle và IDE

Gradle thường tạo output ở những vị trí như:

~~~text
build/classes/java/main/
build/resources/main/
~~~

IDE có thể dùng `out/production/...`, `bin/main/...`, `target/classes` hoặc output do build tool quản lý. Không nên mặc định một đường dẫn là đúng trong mọi cấu hình IDE. Cách xác minh là xem **run configuration**, classpath của tiến trình hiện tại và timestamp/hash của file đầu ra sau compile.

### “Classpath entry là thư mục” rất quan trọng

Theo tài liệu Spring Boot 3.5, **mặc định Devtools theo dõi các classpath entries trỏ đến thư mục**. Đây là lý do ứng dụng chạy từ exploded classes khi phát triển thích hợp với restart. Nó **không vận hành như cơ chế thay các bytecode bên trong một JAR đã được JVM load**.

Với một ứng dụng **fully packaged** chạy bằng `java -jar target/app.jar`, Spring Boot thường coi nó là production-style launch và **Devtools tự vô hiệu hóa các tính năng devtools**, trừ khi cố tình override theo cách không nên dùng ở production.

## 3. Điều kiện cần để automatic restart thật sự hoạt động

Có thể phân tích theo các điều kiện sau:

| Điều kiện | Tại sao cần? | Nếu không thỏa |
| --- | --- | --- |
| Có dependency `spring-boot-devtools` trong development runtime | Cung cấp restart watcher và restart classloader | Không có cơ chế Devtools restart |
| Khởi chạy theo kiểu development với classes directory | Devtools có runtime classpath directory để giám sát | JAR đóng gói thường không kích hoạt devtools |
| `spring.devtools.restart.enabled` không bị tắt | Cho phép restart/watcher hoạt động | Thay đổi classpath có thể không gây restart |
| File **thật sự thay đổi tại classpath được theo dõi** | Đây là tín hiệu kích hoạt | Chỉ sửa `.java` không đủ nếu `.class` không đổi |
| File không thuộc nhóm bị loại khỏi **full restart** | Default excludes thường chỉ LiveReload | Không có restart dù resource cập nhật |
| Không bị trigger-file gate chặn | Khi có trigger file, restart chỉ xét sau khi trigger thay đổi | Compile xong nhưng chưa chạm trigger thì chưa restart |
| Watcher có thời gian polling + quiet period | Tránh restart khi compiler còn đang ghi nhiều file | Restart có thể trễ hoặc bị kích hoạt giữa các đợt ghi |
| Có lifecycle/context shutdown phù hợp | Devtools cần đóng context cũ để khởi tạo lại | Có thể gặp lỗi khi tắt shutdown hook hoặc custom lifecycle |
| Forking còn bật khi dùng build plugin | Cần isolated application classloader | Tắt forking có thể khiến restart không hoạt động đúng |
| Không dùng công nghệ không hỗ trợ tương ứng | Ví dụ AspectJ weaving theo tài liệu Devtools | Có thể không tương thích restart |

Đây là **điều kiện thực tiễn**, không phải lời hứa rằng Devtools chắc chắn restart với mọi công cụ biên dịch, loại classloader hoặc filesystem. Cần kiểm tra đúng đường chạy và log thực tế.

## 4. Vì sao lưu file .java thường chưa đủ?

Giả sử source `RevisionController.java` đang chứa:

~~~java
return "v1";
~~~

Bạn sửa thành:

~~~java
return "v2";
~~~

Nhưng compiler chưa chạy. File `RevisionController.class` cũ trong output classpath vẫn chứa bytecode của phiên bản trước. Khi process tiếp tục load class qua bytecode cũ, Devtools **không thể suy ra việc thay đổi logic Java** từ một file nguồn nằm ngoài classpath.

Thao tác cần thiết thông thường:

~~~bash
mvn compile
~~~

Hoặc build ở IDE để output `.class` được cập nhật. Nếu Maven/IDE phát hiện code không đổi hoặc không biên dịch lại vì một nguyên nhân khác, câu lệnh compile có thể hoàn tất nhưng **không tạo thay đổi file classpath**, nên cũng không có restart mới.

### Ví dụ Java 17 thuần: source khác compiled class

Có thể chứng minh cơ chế này **không cần Spring Boot**.

Tạo file **`SourceVsBytecode.java`**:

~~~java
public class SourceVsBytecode {
    public static void main(String[] args) {
        System.out.println("BYTECODE_V1");
    }
}
~~~

Chạy:

~~~bash
javac -d out SourceVsBytecode.java
java -cp out SourceVsBytecode
~~~

Output:

~~~text
BYTECODE_V1
~~~

Bây giờ **chỉ sửa file `SourceVsBytecode.java`**: đổi literal thành `"BYTECODE_V2"`, lưu lại, nhưng **chưa compile**. Chạy lại:

~~~bash
java -cp out SourceVsBytecode
~~~

Output vẫn là:

~~~text
BYTECODE_V1
~~~

Tiếp theo:

~~~bash
javac -d out SourceVsBytecode.java
java -cp out SourceVsBytecode
~~~

Output:

~~~text
BYTECODE_V2
~~~

Đây là kết quả xác định khi bạn thay đúng literal và compile thành công. Bài toán Devtools cũng dựa trên **file bytecode/resource mà JVM thực sự dùng**; sự khác nhau là Devtools có watcher để nhận biết các thay đổi đó và tự khởi tạo lại Spring context.

## 5. Maven dependency và lưu ý đóng gói

Dùng trong `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

`optional=true` là cách Spring Boot hướng dẫn cho Maven để devtools **không tự truyền xuyên suốt như dependency bắt buộc** sang những module khác dùng artifact này. Với Gradle:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

Đoạn Gradle này là **snippet**, cần build.gradle/plugin/dependency management tương ứng.

### Vì sao không đưa Devtools vào production?

- Devtools mặc định dành cho development, có những property defaults phục vụ lập trình, ví dụ tắt cache của một số template engine.
- Các tính năng tự restart, LiveReload và remote tools không phải một phần cần thiết của runtime production.
- Cố ép bật Devtools trong một production JAR có thể tạo **rủi ro bảo mật và vòng đời**.
- Một bản JAR được repackaged bởi Spring Boot thường **loại bỏ Devtools theo mặc định**.

Đừng kết luận vì `pom.xml` có devtools mà `java -jar` bắt buộc có `restartedMain` hoặc tự restart khi sửa source. Đó là **hai kiểu launch khác nhau**.

## 6. Dự án Spring Boot 3.5.16 / Java 17+ có thể chạy

Ví dụ này tạo một endpoint để dễ nhận biết lần tạo `ApplicationContext` và phiên bản code.

Sử dụng:
- Java 17+;
- Maven 3.6+ hoặc bản tương thích hiện có;
- Spring Boot **3.5.16**;
- Spring Web;
- Spring Boot Devtools trong development runtime.

Cấu trúc:

~~~text
devtools-classpath-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/devtools/
    │   ├── DevtoolsClasspathApplication.java
    │   └── RevisionController.java
    └── resources/
        ├── application.properties
        └── static/notice.txt
~~~

### 6.1 pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>devtools-classpath-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-devtools</artifactId>
            <optional>true</optional>
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
~~~

### 6.2 src/main/resources/application.properties

~~~properties
spring.application.name=devtools-classpath-demo
server.port=18086

demo.message=hello

# Chỉ dùng để quan sát watcher rõ trong lab.
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
~~~

Các giá trị `2s` và `1s` do bài học chọn, không phải mặc định. Polling/quiet period ảnh hưởng **độ trễ phát hiện** sau compile, không thay thế compile.

### 6.3 src/main/java/com/example/devtools/DevtoolsClasspathApplication.java

~~~java
package com.example.devtools;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DevtoolsClasspathApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                DevtoolsClasspathApplication.class, args);
    }
}
~~~

### 6.4 src/main/java/com/example/devtools/RevisionController.java

~~~java
package com.example.devtools;

import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RevisionController {

    private final String instanceId =
            UUID.randomUUID().toString();

    private final String message;

    public RevisionController(
            @Value("${demo.message:default}") String message) {
        this.message = message;
    }

    @GetMapping(value = "/revision", produces = "text/plain")
    public String revision() {
        return "v1|" + message + "|" + instanceId;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("LAB_READY version=v1"
                + " message=" + message
                + " instance=" + instanceId);
    }
}
~~~

**Tại sao có `instanceId`?** Mỗi lần Spring tạo một `RevisionController` mới, nó tạo một UUID mới. Khi Devtools **restart thành công và tạo context mới**, endpoint thường trả một UUID khác. UUID giúp quan sát instance/context, nhưng không đại diện cho **PID**: Devtools có thể restart context/classloader **trong cùng JVM**, không khởi chạy process mới.

Không có lý do business để gắn UUID này trong mọi controller production; đây là marker phục vụ thí nghiệm.

### 6.5 src/main/resources/static/notice.txt

~~~text
NOTICE_V1
~~~

File static giúp minh họa thay đổi resource có thể được phục vụ mới **mà không cần full restart** theo default exclusions. Nó không liên quan compiler Java.

### 6.6 Build trước lần chạy đầu

Trong thư mục chứa `pom.xml`:

~~~bash
mvn -q -DskipTests compile
~~~

Maven biên dịch source vào `target/classes` và copy `src/main/resources` vào output tương ứng theo build lifecycle.

**Chạy ở Terminal A và để process tiếp tục hoạt động:**

~~~bash
mvn spring-boot:run
~~~

Theo tài liệu Devtools, khi dùng Maven/Gradle build-plugin để restart phải giữ **forking được bật**. Không tự tắt forking trong cấu hình plugin. `spring-boot:run` chạy ứng dụng từ các development classpath entries, khác cách chạy packaged JAR.

Terminal A có thể hiển thị thông tin Devtools hoặc thread name liên quan restart; **không viết assertion cứng** vào text log nội bộ của một phiên bản plugin.

### 6.7 Đọc endpoint tại Terminal B

~~~bash
curl -fsS http://127.0.0.1:18086/revision
curl -fsS http://127.0.0.1:18086/notice.txt
~~~

Response đầu có dạng:

~~~text
v1|hello|<uuid-thực-tế-của-lần-chạy>
~~~

Dòng ở trên là **mẫu cấu trúc**, không phải literal output hoàn toàn cố định vì UUID được tạo ngẫu nhiên. Response thứ hai **chính xác** là:

~~~text
NOTICE_V1
~~~

Trong log có dòng do code tự in bắt đầu bằng:

~~~text
LAB_READY version=v1 message=hello instance=
~~~

và sau dấu `=` cuối là UUID. Log framework có thể xen vào; đây chỉ là prefix đáng tin của code demo.

## 7. Thí nghiệm A: sửa .java, chưa compile

Trong Terminal A, **giữ nguyên** lệnh `mvn spring-boot:run` đang chạy.

Mở `src/main/java/com/example/devtools/RevisionController.java` rồi đổi duy nhất:

~~~java
return "v1|" + message + "|" + instanceId;
~~~

thành:

~~~java
return "v2|" + message + "|" + instanceId;
~~~

Đồng thời đổi dòng log `"LAB_READY version=v1"` thành `"LAB_READY version=v2"` để thông tin log thống nhất.

**Chỉ lưu file nguồn, chưa bấm Build Project và chưa chạy `mvn compile`.**

Nếu IDE đang **tắt auto-build/auto-compile**, `target/classes/RevisionController.class` vẫn là bản cũ, nên `curl /revision` vẫn có prefix:

~~~text
v1|hello|
~~~

và chưa có restart do thay đổi bytecode.

**Nếu IDE đang tự động biên dịch ngay lúc Save**, bạn **có thể thấy restart rồi**. Điều này không phủ định quy tắc classpath: Devtools thấy `.class` đã được IDE cập nhật. Để test riêng “save không compile”, phải tắt auto-build tạm thời hoặc xác nhận timestamp/hash output class chưa đổi.

## 8. Thí nghiệm B: compile để cập nhật classpath

Giữ Terminal A đang chạy, mở **Terminal C** ở cùng project:

~~~bash
mvn -q -DskipTests compile
~~~

Trong thí nghiệm, vì bạn vừa sửa source nên compiler có lý do ghi bytecode mới vào `target/classes`. Khi watcher thấy classpath directory thay đổi và quiet period kết thúc, Devtools có thể đóng context cũ và tạo lại context mới.

Đọc lại:

~~~bash
curl -fsS http://127.0.0.1:18086/revision
~~~

Response sau restart có dạng:

~~~text
v2|hello|<uuid-mới>
~~~

So sánh:
- Trước compile, prefix `v1|hello|` nếu không có auto-build.
- Sau compile và restart, prefix `v2|hello|`.
- `instanceId` thường thay đổi vì Spring tạo controller mới.
- **PID JVM** có thể vẫn như cũ; không dùng thay đổi PID làm điều kiện duy nhất để kết luận Devtools restart.

**Lưu ý thời điểm:** `mvn compile` hoàn tất không nghĩa request ngay mili-giây tiếp theo phải đã thấy v2. Watcher còn có poll interval, quiet period và thời gian tạo lại context. Nếu request đi vào lúc restart, client có thể nhận lỗi kết nối tạm thời. Chờ log ready kế tiếp và thử lại.

### Quan sát bytecode thật sự

Trên Linux:

~~~bash
ls -l target/classes/com/example/devtools/RevisionController.class
stat target/classes/com/example/devtools/RevisionController.class
~~~

Trên PowerShell:

~~~powershell
Get-Item .\target\classes\com\example\devtools\RevisionController.class |
    Select-Object FullName, Length, LastWriteTime
~~~

Thời gian file mới là một dấu hiệu hữu ích, nhưng timestamp đơn lẻ có thể bị ảnh hưởng filesystem/copy/build cache. Kết hợp với thông tin compiler, classpath process, response version và restart log.

### Khi Maven không biên dịch lại

Nếu `mvn compile` báo classes up to date hoặc không ghi đầu ra mới, Devtools không có lý do restart chỉ vì lệnh Maven đã được chạy. Kiểm tra:
- file `.java` đã thực sự được lưu chưa;
- có sửa đúng source directory/module không;
- Maven có compile module chứa app đang chạy không;
- IDE đang chạy từ `out/production` nhưng Maven ghi vào `target/classes` không;
- code có lỗi compile hay không;
- output classpath có được watcher theo dõi không.

**Không dùng `mvn clean` như phản xạ đầu tiên** khi app đang chạy: xóa cả `target/classes` rồi build lại dễ tạo thêm thay đổi theo nhiều đợt và gây restart không ổn định. Trước tiên xác minh path và chạy compile bình thường.

## 9. Thí nghiệm C: thay đổi application.properties

Giữ Terminal A chạy. Sửa:

~~~properties
demo.message=hello
~~~

thành:

~~~properties
demo.message=updated
~~~

**Nếu chỉ sửa `src/main/resources/application.properties`**, chưa chắc ứng dụng đọc được file mới. Hãy copy resource vào thư mục runtime classpath bằng lifecycle Maven:

~~~bash
mvn -q -DskipTests compile
~~~

Maven chạy resource processing trước compile; nội dung mới thường được copy đến `target/classes/application.properties`.

Sau khi Devtools restart, `curl /revision` có cấu trúc:

~~~text
v2|updated|<uuid-mới>
~~~

Thay đổi property configuration trong `target/classes` thường thuộc đường classpath được theo dõi và có thể khiến **full restart**, trừ khi file/path bị loại trừ hoặc có trigger gate.

### Phân biệt Java compile và copy resources

Không phải mọi thay đổi resource đòi `javac`. Một YAML/properties file được copy vào classpath bằng `mvn resources:resources` hoặc build của IDE là đủ để Devtools thấy file mới. Tuy nhiên câu hỏi “có phải compile lại không?” cần trả lời dựa trên loại file:

| Thay đổi | Bước để output classpath cập nhật |
| --- | --- |
| `.java` implementation | Biên dịch thành `.class` |
| `.kt` / Scala code | Biên dịch tương ứng bằng compiler thích hợp |
| `application.properties`/`.yaml` ở resources | Copy/process resource vào output classpath |
| Thêm class mới | Compiler tạo `.class` mới trong đúng output folder |
| Xóa class | Build tool/IDE phải xóa stale `.class` nếu muốn thay đổi thật |
| Thay dependency version/JAR | Thường cần build/resolution và **khởi chạy lại process** để cập nhật base classloader |
| HTML/CSS/JS trong static/templates | Copy sang classpath nếu cần; mặc định thường **không full restart**, có thể LiveReload |
| Sửa một file ngoài classpath | Không mặc định bị watcher nhìn thấy; có thể cấu hình additional paths |

Vì thế “Maven compile” là một **lệnh tiện ích** có thể vừa compile classes vừa xử lý resources, không phải một quy tắc rằng mọi tài nguyên phải được compiler Java chuyển thành bytecode.

## 10. Thí nghiệm D: static resource cập nhật nhưng không full restart

File `src/main/resources/static/notice.txt` đang có:

~~~text
NOTICE_V1
~~~

Đổi thành:

~~~text
NOTICE_V2
~~~

Sau đó thực hiện:

~~~bash
mvn -q resources:resources
~~~

hoặc dùng IDE build/copy resources vào runtime classpath.

Khi cập nhật `target/classes/static/notice.txt`, theo **default exclusions** Devtools thường **không đóng toàn bộ ApplicationContext**, nhưng resource mới có thể được phục vụ và/hoặc phát **LiveReload** cho browser.

~~~bash
curl -fsS http://127.0.0.1:18086/notice.txt
~~~

Body kỳ vọng:

~~~text
NOTICE_V2
~~~

Đây là kết quả sau khi resource đã copy đúng và static serving không bị cache làm thấy bản cũ.

### Đừng nhầm LiveReload với Restart

| Cơ chế | Điều xảy ra | Cách nhận biết |
| --- | --- | --- |
| Full Devtools restart | Context/beans tạo lại, restart classloader mới | Có log startup/restart, marker bean mới |
| LiveReload | Phát tín hiệu để browser refresh khi resource thay đổi | Trang tải lại với extension/client hỗ trợ |
| Static resource served mới | Web server đọc/cung cấp nội dung mới khi file classpath cập nhật | Response tài nguyên thay đổi; context có thể không restart |
| Browser hard refresh | Browser tự tải lại tài nguyên | Không chứng minh Java code/beans mới |
| IDE debugger HotSwap | JVM có thể redefine một số class đang chạy | Không tương đương refresh Spring context/bean definitions |

**Một LiveReload event không đồng nghĩa Devtools đã tái tạo các beans**, và một static file thay đổi không cần full Spring context restart để browser nhìn thấy nội dung mới.

## 11. Các thư mục bị loại khỏi restart theo mặc định

Theo Spring Boot 3.5, các pattern phổ biến không kích hoạt **full restart** khi cập nhật là những tài nguyên dưới:

~~~text
META-INF/maven/**
META-INF/resources/**
resources/**
static/**
public/**
templates/**
~~~

Tài liệu thuộc tính còn liệt kê một số pattern khác như compiled test classes, `git.properties` và `META-INF/build-info.properties` trong default exclude. Điều quan trọng là **những tài nguyên này không nhất thiết yêu cầu context restart**; một thay đổi có thể chỉ cần LiveReload nếu ứng dụng và LiveReload server đang chạy đúng.

### Thay thế exclusions mặc định

~~~properties
spring.devtools.restart.exclude=static/**,public/**
~~~

Thuộc tính `exclude` có thể **thay tập mặc định** theo cấu hình, không nên vô tình dùng khi chỉ muốn thêm một ngoại lệ nhỏ. Nếu chỉ muốn bổ sung exclusions mà **giữ các default patterns**, dùng:

~~~properties
spring.devtools.restart.additional-exclude=generated/**,scratch/**
~~~

Hãy đối chiếu đường dẫn tương đối thực tế so với các directories được theo dõi, vì glob sai có thể làm exclusion không hoạt động.

### Không phải loại trừ thì file bị ngừng theo dõi hoàn toàn

Trong docs, các resources excluded khỏi restart thường vẫn có thể kích hoạt **LiveReload**. Vì thế câu “excluded nghĩa là Devtools hoàn toàn bỏ qua file” là không đúng. Đúng hơn: **không kích hoạt full restart theo cơ chế exclude**; tác động reload và classpath copying vẫn phụ thuộc cấu hình.

## 12. Theo dõi thêm đường dẫn bên ngoài classpath

Một project có thể dùng templates hoặc external resource nằm ngoài `src/main/resources`, ví dụ:

~~~text
devtools-classpath-demo/
├── shared-config/
│   └── local-rules.json
└── src/main/...
~~~

Devtools cho phép thêm paths để watch:

~~~properties
spring.devtools.restart.additional-paths=shared-config
~~~

Đây là ví dụ đường dẫn tương đối trong môi trường development; trong ứng dụng thật nên kiểm tra giá trị resolved directory theo working directory/launch configuration.

**Điểm cần phân biệt:** `additional-paths` cho phép watcher quan sát đường dẫn bổ sung, nhưng **không tự đưa file vào JVM classpath hoặc khiến `ClassLoader.getResource(...)` tìm được**. Nếu business code phải đọc file đó, nó vẫn cần cấu hình vị trí đọc file riêng.

Có thể dùng `spring.devtools.restart.exclude`/`additional-exclude` để chọn file cập nhật nào chỉ LiveReload thay vì full restart. Không dùng additional paths để giả lập việc compile Java source: việc đưa `.java` bên ngoài classpath vào watcher **không biến mã nguồn thành `.class`**.

## 13. Trigger file: kiểm soát thời điểm restart

Nếu IDE build liên tục, một chuỗi thay đổi nhỏ có thể tạo nhiều restart. Devtools hỗ trợ **trigger file**:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

File phải tồn tại **ở đâu đó trên runtime classpath**, ví dụ:

~~~text
src/main/resources/.reloadtrigger
target/classes/.reloadtrigger
~~~

Nếu đặt ở resource source directory, build/IDE phải **copy file vào output classpath** cho watcher nhìn thấy. Chỉ tạo `.reloadtrigger` tại project root nhưng không nằm trên classpath là sai điều kiện.

### Cách hoạt động

1. Devtools thấy các changes của classpath nhưng không tự restart ngay theo từng update.
2. Khi **trigger file** thay đổi, Devtools tiến hành restart check.
3. **Chỉ khi có thay đổi phù hợp** mà Devtools đã phát hiện, nó mới thực hiện restart.
4. Trigger file không phải “restart command luôn restart bất kể có thay đổi hay không”.

Làm mẫu:

~~~bash
# Đảm bảo source đã thay đổi và được compile trước.
mvn -q -DskipTests compile

# Sau đó cập nhật nội dung source trigger file.
# Dùng Linux/Bash:
printf 'trigger-1\n' >> src/main/resources/.reloadtrigger

# Copy trigger file đã đổi tới runtime classpath.
mvn -q resources:resources
~~~

**Lưu ý:** để chạy thí nghiệm này, hãy **thêm property trigger-file và file ban đầu trước khi khởi động app**. Nếu file `.reloadtrigger` chưa tồn tại, lệnh append có thể tạo nó, nhưng bạn vẫn cần bảo đảm nó được copy thành classpath resource. Trình tự compile → thay trigger → copy rất quan trọng: nếu chạm trigger **trước khi compiler ghi hết classes**, Devtools có thể restart với class files chưa đồng bộ.

Nếu một IDE hỗ trợ trigger file riêng (Spring Tools hoặc IntelliJ Ultimate theo tài liệu), có thể dùng chức năng tương ứng thay vì thao tác shell.

## 14. Poll interval và quiet period của FileSystemWatcher

Devtools sử dụng watcher dạng **polling**, sau khi phát hiện biến động thì chờ một khoảng không có thêm thay đổi (quiet period) trước khi hành động. Điều này giúp tránh restart khi IDE/Maven đang ghi nhiều `.class`/resources.

Ví dụ:

~~~properties
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
~~~

Ý nghĩa:
- `poll-interval=2s`: khoảng giữa các lượt kiểm tra filesystem.
- `quiet-period=1s`: yêu cầu không có thay đổi trong khoảng thời gian yên tĩnh trước restart.
- Không bảo đảm restart đúng sau `2+1=3` giây: scheduler, build duration, filesystem, CPU load và context refresh còn ảnh hưởng.
- Không làm compiler chạy tự động.

### Khi compile nhiều đợt gây restart nhiều lần

Một IDE hoặc build tool có thể ghi hàng trăm classes theo từng đợt. Nếu quiet period ngắn hơn khoảng nghỉ giữa các đợt, Devtools có thể restart sau đợt đầu rồi lại restart ở đợt sau; thậm chí transient `ClassNotFoundException`/dependency inconsistency có thể xảy ra.

Khi thực sự quan sát thấy điều đó, tăng poll/quiet periods có kiểm soát:

~~~properties
spring.devtools.restart.poll-interval=3s
spring.devtools.restart.quiet-period=2s
~~~

Những con số này **chỉ là cấu hình thử**, không nên copy nguyên sang mọi máy. Không tăng vô hạn vì sẽ làm vòng feedback rất chậm và có thể che vấn đề IDE output không đồng bộ.

### Khi filesystem timestamp lạ

Trên network drive, Docker volume mount, WSL, hoặc filesystem có độ phân giải thời gian mtime thấp, file watcher có thể nhận changes trễ hoặc không ổn định. Xác minh:
- file output thực sự đổi size/content;
- process nhìn thấy đúng mount/path;
- thời gian của container và host hợp lý;
- watcher đang chạy trong ứng dụng development;
- không có trigger gate/exclude đang chặn.

## 15. Restart classloader và Base classloader

Devtools tự restart nhanh nhờ **hai classloaders**:

~~~mermaid
flowchart TD
    JVM["JVM vẫn đang chạy"] --> BASE["Base classloader: thư viện JAR ổn định"]
    JVM --> R1["Restart classloader #1: application classes"]
    R1 --> C1["ApplicationContext #1"]
    CHANGE["Compiled classpath changed"] --> CLOSE["Đóng context cũ"]
    CLOSE --> DROP["Bỏ restart classloader #1"]
    DROP --> R2["Restart classloader #2"]
    BASE --> R2
    R2 --> C2["ApplicationContext #2 với classes mới"]
~~~

Thư viện từ dependency JAR thường thuộc base loader, còn project đang sửa thuộc restart loader. Lúc restart, Devtools thay restart loader và dựng context mới, nhưng base loader có thể được tái dùng; vì vậy restart thường nhanh hơn JVM process cold start.

### Hệ quả thực tiễn

- Bean singleton trong context cũ **không phải** singleton của context mới; nó được tạo lại.
- Static field của application class trong restart loader có thể được reset khi class được load lại.
- JVM process/PID không nhất thiết thay đổi.
- Những resources hoặc threads tự tạo **ngoài Spring lifecycle** có thể sống sót không mong muốn qua các lần restart và gây rò rỉ.
- Thêm/xóa dependency JAR hoặc đổi library version thường cần **restart process/build** vì base classloader không tự thay mọi JAR đã load.
- Nếu dự án multi-module hoặc reflection phức tạp, một class có thể bị nạp bởi loader khác với loader bạn kỳ vọng.

### Restart không phải class redefinition kiểu HotSwap

Debugger HotSwap có thể sửa method body của class đang load trong giới hạn khả năng JVM/debugger; Devtools tạo Spring context và restart classloader mới. Vì thế:
- đổi signature/bean definitions có thể yêu cầu Devtools restart thay vì HotSwap đơn giản;
- chỉ nhìn thấy mã mới trong debugger không bảo đảm bean wiring đã được tạo lại;
- không dùng HotSwap như bằng chứng watcher đã phát hiện cập nhật classpath.

## 16. Cách cập nhật classpath với IDE và build tools

### Eclipse / Spring Tool Suite

Theo Spring Boot 3.5, khi Eclipse build tự động đang bật, việc **Save file đã sửa** thường khiến IDE compile và cập nhật classpath output, từ đó kích hoạt restart.

Nếu không có restart:
1. Kiểm tra `Project > Build Automatically` hoặc chế độ build thật sự.
2. Kiểm tra phần lỗi biên dịch: IDE có thể giữ `.class` cũ khi source lỗi.
3. Xác minh thư mục output của project nằm trong classpath app đang chạy.
4. Kiểm tra trigger-file và excludes nếu đã cấu hình.
5. Không quy toàn bộ vấn đề cho Devtools khi compiler chưa ra output.

### IntelliJ IDEA

Theo tài liệu Devtools, **Build > Build Project** làm classpath cập nhật. Với một số cấu hình IDE, Save **không tự build**; người dùng phải build bằng menu/shortcut hoặc bật cơ chế auto make phù hợp với phiên bản IntelliJ.

Nếu chạy qua Spring Boot run configuration:
- xác định có devtools ở runtime dependencies;
- xác định compiler output directory IDE dùng;
- bảo đảm build đang ghi vào **đúng output directory** mà JVM process đang chạy đọc;
- nếu dùng Maven plugin để start app nhưng IntelliJ build vào output khác, file .class mới có thể **không** xuất hiện nơi watcher đang theo dõi.

Không ghi một shortcut phím cố định cho mọi OS/keymap. Dùng menu IDE để tránh khác biệt giữa Windows/macOS/Linux.

### Maven

Ở Terminal A:

~~~bash
mvn spring-boot:run
~~~

Ở Terminal B, sau khi sửa file Java:

~~~bash
mvn -q -DskipTests compile
~~~

Maven output thông thường là `target/classes` của project/module tương ứng. Không cần chạy lại nguyên `mvn spring-boot:run` bằng tay nếu Devtools đang hoạt động và watcher nhận đúng class change.

Nếu dự án đa module, phải compile **module chứa class đã đổi** và bảo đảm runtime của ứng dụng đã dùng output development folder của module đó; nếu module khác vẫn được load như dependency JAR trong base loader, thay JAR mà không restart JVM chưa chắc có tác dụng.

### Gradle

Ví dụ dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

Chạy app:

~~~bash
./gradlew bootRun
~~~

Ở shell khác, sau khi sửa Java:

~~~bash
./gradlew classes
~~~

Spring Boot docs cũng nêu `gradle build` có thể làm classpath cập nhật. Các output như `build/classes/java/main` và `build/resources/main` cần khớp với classpath mà `bootRun` dùng. Nếu script Gradle chạy trong một build daemon khác hoặc configuration đặc thù, xác minh việc cập nhật file class/resource, không chỉ nhìn task `BUILD SUCCESSFUL`.

**Không tắt forking** khi dùng Maven/Gradle plugin trong bối cảnh Devtools restart; theo docs, isolated classloader là điều kiện quan trọng.

## 17. Sự khác nhau giữa hai cách disable restart

### Chỉ tắt watcher/restart qua properties

~~~properties
spring.devtools.restart.enabled=false
~~~

Theo Spring Boot docs, cách này thường **không theo dõi file changes để restart**, nhưng restart classloader **vẫn có thể được khởi tạo**. Nó phù hợp khi muốn tắt automatic restart tạm thời trong một môi trường dev mà không thay toàn bộ thiết kế launch.

### Tắt hoàn toàn restart support

Trong `main`, **trước `SpringApplication.run`**:

~~~java
public static void main(String[] args) {
    System.setProperty(
            "spring.devtools.restart.enabled", "false");
    SpringApplication.run(MyApplication.class, args);
}
~~~

Đây là snippet cần class `MyApplication` và import `SpringApplication`. Nó thể hiện cách đặt **Java System property rất sớm** để bỏ toàn bộ restart support theo tài liệu Spring Boot. Đừng viết nó vào project lab ở mục 6 khi bạn đang muốn thử automatic restart.

Cũng có thể truyền JVM system property trước khi chạy app; cần phân biệt `-D...` là **JVM argument**, không phải một command line argument sau `-jar`.

### Khi không nên cưỡng bức bật Devtools

Spring Boot cho phép override production-style launch bằng `-Dspring.devtools.restart.enabled=true`, nhưng tài liệu cảnh báo **không làm vậy trong production vì rủi ro bảo mật**. Đừng dùng nó như “mẹo” để thay code bên trong production JAR mà không qua build/deploy. Vòng triển khai production cần release artifact mới, startup/rollback theo quản lý release.

## 18. Restart exclusions và classloader customization là hai việc khác

Có hai nhóm cấu hình dễ bị nhầm:

1. **File watcher/exclude** — đường dẫn file thay đổi nào kích hoạt full restart hay chỉ LiveReload.
2. **Classloader include/exclude** — những classpath entries nào được đưa vào restart loader hay base loader.

Ví dụ classloader customization trong file:

~~~text
src/main/resources/META-INF/spring-devtools.properties
~~~

Có thể khai báo các key mang prefix:

~~~properties
restart.include.company-common=company-common-.+\\.jar
restart.exclude.shared-output=.*/shared-output/.*
~~~

Các giá trị là **regular expressions áp dụng vào đường dẫn classpath**, không phải Ant glob của file watcher. Hai regex trên chỉ mang tính minh họa; với project thật phải đối chiếu full classpath entries và pattern syntax tương ứng.

Đừng tự đổi classloader split để giải quyết lỗi “lưu .java mà chưa compile”: đó là vấn đề **không có bytecode mới**. Classloader customization chỉ cần khi có vấn đề rõ ràng với class identity, reflection, serialization hoặc multi-module setup.

### Một ví dụ class identity issue

Hai class có cùng tên đầy đủ nhưng bị load bởi **hai classloaders khác nhau** không được JVM xem là cùng một class identity. Vì thế có thể thấy `ClassCastException` trông như một class “không cast được sang chính nó”. Khi xuất hiện:
- thử disable restart để đối chiếu;
- kiểm tra classpath split base/restart;
- xem thư viện dùng reflection/serialization;
- nếu đúng nguyên nhân, thêm `restart.include.*`/`restart.exclude.*` phù hợp.

Không sửa bằng `System.gc()` hoặc đổi thread context classloader bừa bãi.

## 19. Bảng chẩn đoán “sửa code nhưng không restart”

| Triệu chứng | Nguyên nhân khả dĩ | Phép thử / cách sửa |
| --- | --- | --- |
| Save `.java` nhưng không restart | Chưa compile | Build Project hoặc `mvn compile` |
| Maven compile thành công nhưng vẫn code cũ | Compiler không ghi file mới hoặc sai module | Xem timestamp/hash `.class` và output path |
| Compile ở IntelliJ nhưng app Maven vẫn code cũ | Hai công cụ dùng output directories khác nhau | So classpath JVM với folder compiler ghi |
| Chạy bằng `java -jar` không restart | Packaged app tự tắt devtools theo mặc định | Dùng `mvn spring-boot:run` hoặc run IDE trong development |
| Devtools không có ở runtime | Dependency thiếu/scope sai | Xem dependency runtime và build config |
| Có `spring.devtools.restart.enabled=false` | Automatic restart bị vô hiệu hóa | Chỉ bật lại trong local development |
| Chỉnh HTML/CSS nhưng context không restart | Default resource excludes | Đây thường là đúng; kiểm tra LiveReload/copy |
| Không thấy LiveReload trong browser | Thiếu LiveReload client hoặc server không chạy | Kiểm tra plugin và `spring.devtools.livereload.enabled` |
| Có trigger-file nhưng compile chưa restart | Chưa chạm trigger file trong classpath | Compile xong, cập nhật trigger và copy resource |
| Restart xảy ra nhiều lần sau build | Compiler ghi nhiều đợt, quiet period ngắn | Tăng quiet period sau khi đã xác minh nguyên nhân |
| Restart ngay giữa lúc build | Watcher thấy output chưa ổn định | Sử dụng trigger file hoặc tăng quiet period |
| Thêm dependency mà code cũ | JAR trong base loader chưa được thay | Khởi chạy process lại với dependency classpath mới |
| Có code mới nhưng bean state cũ | Có thể đang xem cache bên ngoài hoặc không phải đúng app/port | Kiểm tra instance ID/port, logs, request route |
| Port bị chiếm sau restart | Custom thread/server/resource không close | Kiểm tra bean destruction, shutdown hook và sockets |
| Spring reports classloading error | Base/restart split không tương thích | Tạm disable restart, xem `spring-devtools.properties` |
| Lỗi `ClassNotFoundException` sau nhiều restart | Output compilation thiếu đồng bộ hoặc restart sớm | Xem compiler errors, quiet period, module output |
| Chỉ một resource outside project không trigger | Không nằm trên watched classpath | Cấu hình `additional-paths` và xác minh path |
| JRebel được bật | JRebel thay cơ chế restart | Theo hướng dẫn integration đang dùng |
| AspectJ weaving đang dùng | Automatic restart không được hỗ trợ theo docs | Dùng workflow build/restart phù hợp |

### Quy trình debug 90 giây theo thứ tự hợp lý

1. **Xác nhận đúng URL/port và PID** đang phục vụ request; không gõ nhầm vào instance khác.
2. **Xác nhận khởi chạy development**, không phải `java -jar` production-style.
3. **Xác nhận có `spring-boot-devtools` trong runtime** và restart chưa bị disable.
4. **Thực hiện Build Project / `mvn compile`** sau khi sửa Java.
5. **Nhìn vào output classpath** xem `.class` đã thay đổi chưa.
6. **Đợi poll + quiet period + context refresh**, kiểm tra log restart.
7. Kiểm tra `exclude`, `trigger-file` và `additional-paths` nếu đã cấu hình.
8. Nếu vẫn không được, kiểm tra multi-module/classloader, shutdown hook và plugin forking.

Thứ tự này tránh việc thay đổi cả tá cấu hình khi nguyên nhân đơn giản chỉ là **IDE chưa compile**.

## 20. Điều gì xảy ra với state khi Devtools restart?

Một lần Devtools restart thường **đóng `ApplicationContext` cũ và tạo context mới**. Vì thế:
- Các beans sẽ được tạo lại theo dependency graph.
- `@PostConstruct`, BeanPostProcessors và runner/lifecycle callbacks có thể chạy lại.
- `ApplicationReadyEvent` có thể xuất hiện lần nữa sau restart thành công.
- Những dữ liệu chỉ nằm trong bean memory bị thay bằng instance mới.
- Database, Redis, file, session storage ngoài JVM **không tự được reset**.
- Static field của các classes trong restart loader có thể reset; static field của classes thuộc base loader có thể tồn tại.
- Nếu custom non-daemon threads/executor không stop đúng, chúng có thể chạy qua nhiều lần restart và gây trùng scheduler/job.
- Startup logic có side effects như gửi email, tạo bảng, seed dữ liệu hoặc gọi API phải được thiết kế idempotent.

**Không dùng restart làm “deploy an toàn”**: khi Devtools restart, request in-flight có thể bị ảnh hưởng; công nghệ này hướng đến local development, không phải cơ chế hot deploy sản xuất.

## 21. LiveReload, browser cache và nguồn “code cũ”

Khi bạn không thấy thay đổi trên browser, nguyên nhân không nhất thiết là Java code chưa được reload:

- **Browser cache** có thể giữ CSS/JS cũ.
- **Template engine caching** có thể giữ bản template trước; Devtools có development property defaults làm giảm vấn đề này nhưng tùy engine.
- **Reverse proxy/cache/CDN** có thể trả response từ cache.
- **Sai host/port** có thể trỏ đến app khác.
- **IDE debugger HotSwap** đã thay class trong một JVM khác với project đang build.
- **Static resource chưa copy vào classpath**, dù `src/main/resources` đã được sửa.
- **Backend bean chưa được recreate**, nếu full restart không xảy ra.

Trong demo, `curl /revision` và `curl /notice.txt` tách rõ **logic Java** và **static resource**. Bằng cách dùng marker UUID trong controller, bạn có thêm một chỉ dấu về việc bean đã được tạo lại.

Devtools có embedded LiveReload server. Trên browser cần extension/client hỗ trợ nếu muốn tự reload tab. Chỉ có Devtools phía server không đồng nghĩa mọi tab browser tự refresh được.

Theo docs, chỉ có **một LiveReload server** hoạt động trên một máy tại một thời điểm; khi chạy nhiều ứng dụng development, những app đến sau có thể không mở được server LiveReload dù automatic restart vẫn hoạt động.

## 22. Kiểm thử có kiểm soát và đo feedback time

Nếu muốn đánh giá chất lượng workflow, đừng chỉ nói “Devtools nhanh” mà không đo. Có thể ghi:

| Mốc | Định nghĩa |
| --- | --- |
| `T_save` | Lúc người lập trình lưu source |
| `T_compile_end` | Compiler thực sự ghi xong classes/resources |
| `T_watch_detect` | Watcher phát hiện thay đổi classpath |
| `T_restart_begin` | Context cũ bắt đầu đóng |
| `T_ready_again` | ApplicationReadyEvent lần tiếp theo |
| `T_endpoint_new` | Endpoint trả phiên bản mới ổn định |

Các chỉ số hữu ích:
- `compile_duration = T_compile_end - T_save`;
- `watch_and_restart_duration = T_ready_again - T_compile_end`;
- `end_to_end_feedback = T_endpoint_new - T_save`;
- số lần restart cho một lần Build Project;
- tỉ lệ build bị lỗi hoặc response thất bại trong quá trình restart.

**Đừng nhầm timestamp giữa nhiều process/máy** khi không đồng bộ clock. Với đo duration trong cùng JVM, dùng `System.nanoTime()`; giữa IDE/build tool và app, nên dùng log timestamps đã được đồng bộ hoặc công cụ quan sát bên ngoài.

### Vì sao không dùng benchmark một lần?

Filesystem cache, JIT, CPU load, số class được compile, compiler incremental build và bean graph đều làm thời gian khác nhau. Nếu điều chỉnh poll/quiet period, đo nhiều lượt cùng project/workload và so median/p95. Mức poll nhỏ hơn không đồng nghĩa tổng feedback nhanh hơn nếu gây restart giữa các đợt compile.

## 23. Checklist ứng dụng thực tế

- [ ] Dependency `spring-boot-devtools` nằm ở development runtime.
- [ ] Maven dùng `optional=true` hoặc Gradle `developmentOnly` theo hướng dẫn.
- [ ] Ứng dụng được chạy kiểu development có classpath directories.
- [ ] Không tắt build-plugin forking nếu phụ thuộc Devtools restart.
- [ ] `spring.devtools.restart.enabled` không bị disable.
- [ ] Đã xác minh file đang sửa thuộc **đúng module và source set**.
- [ ] IDE/Maven/Gradle đã compile `.java` thành `.class` mới.
- [ ] Resource cần quan sát đã được copy vào output classpath.
- [ ] Output directory của compiler trùng một watched classpath entry.
- [ ] Chờ polling và quiet period trước khi kết luận không hoạt động.
- [ ] Kiểm tra excludes đối với `static`, `public`, `templates`.
- [ ] Khi dùng trigger file, file đó nằm trong runtime classpath và đã được cập nhật **sau** compile.
- [ ] Nếu file ngoài classpath, cấu hình additional paths riêng.
- [ ] Không nhầm LiveReload/browser refresh với full context restart.
- [ ] Nếu multi-module/classloader lỗi, chẩn đoán classloader split có bằng chứng.
- [ ] Nếu thử disable restart, hiểu khác biệt properties vs System property sớm.
- [ ] Không cố bật Devtools trên production packaged JAR.
- [ ] Cleanup custom threads/resources đúng để không rò rỉ sau nhiều restart.
- [ ] Phân biệt lỗi compiler, lỗi startup sau restart và watcher không phát hiện.
- [ ] Đo feedback/latency thực, không suy luận chỉ từ một dòng log.

## 24. Câu hỏi ôn tập

**1. Devtools mặc định theo dõi gì?**  
Các classpath entries trỏ đến **thư mục**, không tự mặc định theo dõi tất cả `.java` dưới source tree.

**2. Chỉ Save một file Java có chắc kích hoạt restart không?**  
Không. Phải có cập nhật bytecode trong runtime classpath. Eclipse auto-build có thể làm việc đó ngay sau Save; IntelliJ thường cần Build Project theo workflow đang bật.

**3. Maven command nào có thể cập nhật compiled classes?**  
`mvn compile`, trong đúng module/project và không có lỗi compilation.

**4. Nếu Maven báo compile thành công nhưng không ghi file mới, Devtools có bắt buộc restart không?**  
Không. Nó cần thay đổi classpath được phát hiện, không phải sự kiện lệnh Maven kết thúc.

**5. Sửa application.properties có cần javac không?**  
Không nhất thiết; cần resource được copy/process vào directory classpath mà app đang dùng.

**6. Tại sao java -jar packaged app không restart theo Devtools mặc định?**  
Spring Boot coi đó là production-style launch và tự disable devtools mặc định.

**7. Thay CSS/HTML trong static có cần restart cả context không?**  
Thường không theo default exclusions; có thể phục vụ resource mới và dùng LiveReload.

**8. spring.devtools.restart.additional-exclude khác exclude như thế nào?**  
Additional-exclude bổ sung patterns trong khi giữ default exclusions, còn exclude có thể thay tập defaults.

**9. Trigger file có tự restart kể cả khi không có thay đổi nào khác không?**  
Không. Nó kích hoạt **restart check**, và chỉ restart khi Devtools có điều cần cập nhật.

**10. Trigger file nằm ở project root nhưng không trên classpath có hợp lệ không?**  
Không; theo docs nó phải xuất hiện ở đâu đó trong runtime classpath.

**11. poll-interval và quiet-period có compile Java không?**  
Không. Chúng chỉ điều chỉnh phát hiện và ổn định thay đổi filesystem.

**12. Vì sao Devtools restart không nhất thiết tạo PID mới?**  
Vì nó có thể giữ JVM và base classloader, chỉ thay restart classloader/context.

**13. Khi thêm library JAR mới, Devtools có chắc nạp phiên bản mới trong base classloader không?**  
Không. Thường cần restart process để tạo lại runtime classpath/base loader.

**14. Cách nào disable restart classloader hoàn toàn?**  
Set Java System property `spring.devtools.restart.enabled=false` **trước** `SpringApplication.run` theo hướng dẫn Boot.

**15. Vì sao một project nhiều module có thể code vẫn cũ sau compile?**  
App có thể dùng JAR của module đó trong base loader, trong khi compiler cập nhật một output directory khác.

**16. LiveReload server có khiến tất cả browser tabs tự refresh mà không cần client không?**  
Không; cần browser extension/client hỗ trợ, và còn phụ thuộc cache/network.

**17. Nếu dự án có AspectJ weaving, Devtools automatic restart có được hỗ trợ không?**  
Theo tài liệu Spring Boot 3.5, không hỗ trợ cùng cơ chế này.

**18. Vì sao không được xem Devtools như giải pháp hot deployment production?**  
Nó hướng đến development, có security/lifecycle implications và không thay thế release/deploy/rollback có kiểm soát.

## 25. Nguồn tài liệu chính thức

- [Spring Boot 3.5 — Developer Tools](https://docs.spring.io/spring-boot/3.5/reference/using/devtools.html): automatic restart, điều kiện cập nhật classpath, IDE/Maven/Gradle, LiveReload, trigger file, exclusions và hai classloaders.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): default `spring.devtools.restart.enabled`, exclude patterns, poll interval và quiet period.
- [Spring Boot 3.5 — Maven Plugin: Run](https://docs.spring.io/spring-boot/3.5/maven-plugin/run.html): chạy development app qua `spring-boot:run` và plugin configuration.
- [Spring Boot 3.5 — Gradle Plugin](https://docs.spring.io/spring-boot/3.5/gradle-plugin/running.html): `bootRun`, task và runtime configuration.
- [Spring Boot 3.5 — Application Properties: Devtools](https://docs.spring.io/spring-boot/3.5/reference/using/devtools.html#using.devtools): restart defaults và lựa chọn diagnostic.
- [Oracle JDK 17 — javac command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): compiler tạo `.class` từ `.java`.
- [Oracle JDK 17 — java command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): runtime classpath và `-jar` behavior.

**Kết luận:** với Spring Boot Devtools, **đổi source chưa phải đổi classpath**. Khi Java source được **compile thành bytecode mới trong output directory mà process đang dùng**, watcher mới có tín hiệu để restart. Resource files cần được **copy/process** vào classpath; static/templates có thể chỉ kích hoạt LiveReload. Muốn chẩn đoán nhanh, kiểm tra đúng **mode chạy → dependency → output path → compile/copy → excludes/trigger → polling → restart log**. Đừng dùng Devtools thay cho compiler hoặc một quy trình deploy production.