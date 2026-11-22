# Bật, tắt và tùy chỉnh lớp bằng Maven plugin

## 1. Bài toán và mục tiêu

Khi đóng gói Spring Boot thành executable JAR, Maven thường tạo một archive có **class ứng dụng**, **resource**, **Spring Boot loader** và nhiều **dependency JAR**. Nếu đưa toàn bộ archive vào một Docker image dưới dạng một file rồi thay đổi một Java class, container build có thể cần tạo lại lớp chứa **toàn bộ** executable JAR, dù phần lớn dependency không đổi.

**Đóng gói theo lớp** (*layered JAR*) cho phép Spring Boot Maven Plugin ghi thêm thông tin phân nhóm các entry trong archive. Build tool hoặc công cụ trích xuất có thể dùng thông tin đó để tạo các lớp container riêng cho những phần có tần suất thay đổi khác nhau. Thư viện ổn định thường ở lớp nền; class và resource của ứng dụng thường ở lớp sau cùng.

Chủ đề này trả lời đúng ba câu hỏi thực hành:

1. **Bật** layering trong `spring-boot-maven-plugin` bằng cách nào, và kiểm tra được nó thực sự xuất hiện ở đâu?
2. **Tắt** layering khi không cần Docker layering ra sao, mà vẫn giữ JAR chạy được bằng `java -jar`?
3. **Tùy chỉnh** tên lớp, nhóm dependency, thứ tự layer và cách các entry được gán qua file `layers.xml` như thế nào?

Sau bài này, bạn sẽ có thể tạo một ứng dụng Spring Boot 4.1.2 với Java 17, đóng gói bằng Maven, xem `BOOT-INF/layers.idx`, dùng `jarmode=tools` để liệt kê/trích xuất lớp, sửa quy tắc trong file XML, kiểm tra chức năng app sau khi đổi layering và nhận biết những trường hợp cache container **không tự được cải thiện**.

**Phiên bản:** ví dụ sử dụng Spring Boot Maven Plugin **4.1.2**, Java **17+** và Maven tương thích với Spring Boot 4.1.x. Ở phiên bản này, công cụ trích xuất dùng **`-Djarmode=tools`** và tùy chọn plugin **`<includeTools>`**. Đừng sao chép nguyên `layertools`/`includeLayerTools` từ một số bài hướng dẫn cho phiên bản cũ mà không kiểm tra plugin đang dùng.

## 2. Layered JAR là gì — và không phải là gì?

Một Boot executable JAR thông thường chứa:

~~~text
layer-demo-1.0.0.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── dev/example/layer/LayerDemoApplication.class
    │   ├── dev/example/layer/LayerMessage.class
    │   └── application.properties
    └── lib/
        ├── spring-boot-*.jar
        ├── spring-core-*.jar
        └── ...
~~~

Khi **layering được bật**, archive vẫn có **cùng nguyên tắc BOOT-INF/classes và BOOT-INF/lib** để chạy. Sự khác biệt chính là thêm metadata, thường là:

~~~text
BOOT-INF/layers.idx
~~~

File `layers.idx` mô tả **entry nào thuộc lớp nào** và thứ tự các lớp. Nó **không** có nghĩa mỗi layer tự trở thành một JAR riêng bên trong archive, cũng không phải Docker image đã được tạo sẵn. Chỉ khi Dockerfile, Cloud Native Buildpacks hoặc một công cụ khác **dùng thông tin phân lớp** để phân chia filesystem/container layers thì cache theo lớp mới phát huy tác dụng.

### Những điều layering không tự thay đổi

- Không đổi API Java, kết quả business logic hoặc Spring MVC mappings.
- Không thay cách chạy thông thường: `java -jar target/layer-demo-1.0.0.jar` vẫn là lệnh chính.
- Không làm ứng dụng tự khởi động nhanh hơn chỉ vì `layers.idx` tồn tại.
- Không tự khóa dependency version hay làm build reproducible; `outputTimestamp`, toolchains và generated contents là mối quan tâm riêng.
- Không tự tạo Docker image. `spring-boot:build-image` là tính năng khác với `spring-boot:repackage`; Dockerfile cũng là một lựa chọn độc lập.
- Không bảo đảm mọi lần build container tận dụng cache. Việc Docker COPY theo từng lớp, thứ tự lớp và nội dung thực sự thay đổi mới quyết định cache reuse.

## 3. Bốn lớp mặc định của Spring Boot Maven Plugin

Khi Spring Boot 4.1.2 repackage một executable JAR, layered archive **được bật mặc định** và có bốn layer tiêu chuẩn:

| Layer mặc định | Thành phần | Tần suất thay đổi mong đợi |
| --- | --- | --- |
| `dependencies` | Dependency không có `SNAPSHOT` trong version | Thường ít đổi |
| `spring-boot-loader` | Các class Spring Boot loader | Thường chỉ đổi khi thay Spring Boot |
| `snapshot-dependencies` | Dependency có `SNAPSHOT` trong version | Có thể đổi nhiều |
| `application` | Class/resource của ứng dụng và các local module dependencies thuộc cùng build | Thường đổi nhất |

Thứ tự mặc định trong `layerOrder`:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

Các phần ít thay đổi hơn được ưu tiên sớm để công cụ container có thể cache các lớp đó qua nhiều lần build.

### Một điểm dễ bỏ qua trong multi-module Maven

Spring Boot nhận diện **module dependency** bằng các module **thuộc cùng Maven build/reactor hiện tại**. Dependency được lấy từ module đã cài vào `~/.m2` nhưng **không nằm trong reactor hiện tại** có thể được xem là **dependency thường**, thay vì module dependency. Vì vậy `mvn -pl web-app -am package` và build riêng app dựa vào một core đã install có thể dẫn đến **phân lớp dependency khác nhau**, dù cùng tọa độ artifact.

Hãy kiểm tra `layers.idx` trong **kiểu build CI thực tế**. Việc thay đổi phân loại này không đồng nghĩa code sai, nhưng có thể ảnh hưởng khả năng tận dụng cache.

## 4. Maven plugin: ba nhóm cấu hình cần phân biệt

Trong `spring-boot-maven-plugin`, các cấu hình liên quan là:

| Tham số | Vị trí | Ý nghĩa |
| --- | --- | --- |
| `layers.enabled` | `<layers><enabled>...</enabled></layers>` | Bật/tắt việc ghi thông tin phân lớp |
| `layers.configuration` | `<layers><configuration>path</configuration></layers>` | Đọc file XML mô tả layer rules |
| `layers.configurationName` | `<layers><configurationName>name</configurationName></layers>` | Nạp cấu hình tên `name` từ classpath của **Maven plugin** |
| `includeTools` | `<configuration><includeTools>...</includeTools></configuration>` của plugin, **ngoài `layers`** | Có đưa Spring Boot JAR tools vào executable archive hay không |
| `repackage` | Goal của Boot Maven Plugin | Tạo executable archive và áp dụng layering |
| `outputTimestamp` | Goal `repackage` / `project.build.outputTimestamp` | Ổn định timestamp của archive entries; **không phải công tắc layering** |
| `classifier` | Goal `repackage` | Tách executable artifact khỏi ordinary main JAR; **không quyết định layer rules** |

**Cú pháp đúng Spring Boot 4.1.x** khi bật, với cấu hình plugin:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <layers>
            <enabled>true</enabled>
        </layers>
        <includeTools>true</includeTools>
    </configuration>
</plugin>
~~~

Với **`spring-boot-starter-parent`**, execution `repackage` được parent cấu hình sẵn; child chỉ cần khai báo plugin và các phần muốn chỉnh. Với corporate parent/BOM thuần, hãy xem mục 13 vì khi đó phải bind goal `repackage` tường minh.

### Bật mặc định khác bật tường minh

Nếu không có `<layers>` trong plugin configuration, Spring Boot 4.1 vẫn tạo layered archive theo mặc định. Đặt `<enabled>true</enabled>` có ích cho người học, pipeline/policy và mục đích kiểm thử toggling, nhưng không phải bước bắt buộc để được `layers.idx`.

## 5. Dự án mẫu chạy được bằng Java 17 và Spring Boot 4.1.2

Ví dụ sử dụng ứng dụng dòng lệnh đơn giản, không mở HTTP server, để quá trình chạy và đối chiếu output thuận tiện. Chúng ta sẽ thay đổi **chỉ cấu hình packaging**, không đổi code Java, rồi kiểm tra rằng `java -jar` vẫn hoạt động.

### 5.1. Cấu trúc project

~~~text
layer-demo/
├── pom.xml
├── src/
│   ├── layers.xml                        # chỉ dùng ở bài tùy chỉnh, ngoài resources
│   ├── main/
│   │   ├── java/dev/example/layer/
│   │   │   ├── LayerDemoApplication.java
│   │   │   └── LayerMessage.java
│   │   └── resources/
│   │       └── application.properties
│   └── test/
│       └── java/dev/example/layer/
│           └── LayerMessageTest.java
└── target/                                # Maven tạo sau khi build
~~~

File `src/layers.xml` ở ví dụ **chưa cần có** cho bước bật mặc định. Chỉ tạo file đó trước khi chuyển sang cấu hình tùy chỉnh ở mục 10. Không đặt nó dưới `src/main/resources` nếu chỉ muốn file này làm **cấu hình build plugin**; nếu đặt trong resources, file sẽ bị đóng gói vào application classpath ngoài ý muốn.

### 5.2. `pom.xml` hoàn chỉnh — bật lớp tường minh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>layer-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <layers.enabled>true</layers.enabled>
        <layers.tools.enabled>true</layers.tools.enabled>
        <project.build.outputTimestamp>1704067200</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <layers>
                        <enabled>${layers.enabled}</enabled>
                    </layers>
                    <includeTools>${layers.tools.enabled}</includeTools>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích từng quyết định:**

1. Starter parent `4.1.2` quản lý versions và pre-configured execution `repackage`, nên không cần tự thêm execution với ID khác.
2. `<layers.enabled>true</layers.enabled>` là **property tự đặt trong POM**, không phải một Maven built-in flag. `<enabled>${layers.enabled}</enabled>` cho phép đổi bằng `-Dlayers.enabled=false` ở dòng lệnh.
3. `<layers.tools.enabled>true</layers.tools.enabled>` cũng là property do bài ví dụ định nghĩa để điều khiển `includeTools`. Nó không có tác dụng nếu quên nối vào `<includeTools>${layers.tools.enabled}</includeTools>`.
4. `<includeTools>` nằm cùng cấp với `<layers>`, **không** nằm trong `<layers>`. Trong Spring Boot 4.1.2, công cụ trích xuất có tên `spring-boot-jarmode-tools`.
5. `project.build.outputTimestamp=1704067200` là mốc cố định tương đương `2024-01-01T00:00:00Z`; nó giúp archive entries có timestamp ổn định để so sánh, **không bắt buộc để bật layering**. Không dùng giá trị từ đồng hồ mỗi lần build nếu mục tiêu là reproducibility.
6. Project không dùng web starter; ta sẽ dùng `CommandLineRunner` để in output rồi kết thúc. Packaging layer works cả với CLI app, HTTP app, JAR hoặc WAR theo những layout được plugin hỗ trợ.

**Cú pháp property ở XML:** ở đoạn POM thật, các giá trị chính xác là `${layers.enabled}` và `${layers.tools.enabled}`; Maven thực hiện property interpolation. Việc đổi property trên CLI **chỉ có tác dụng vì POM đã tham chiếu chúng**.

### 5.3. Class Java — `src/main/java/dev/example/layer/LayerMessage.java`

~~~java
package dev.example.layer;

public final class LayerMessage {

    private LayerMessage() {
    }

    public static String text() {
        return "LAYER_DEMO_OK";
    }
}
~~~

`LayerMessage` là Java 17 class thuần; không phụ thuộc Spring, giúp test logic độc lập.

### 5.4. Spring Boot application — `LayerDemoApplication.java`

Tệp đầy đủ: `src/main/java/dev/example/layer/LayerDemoApplication.java`.

~~~java
package dev.example.layer;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LayerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LayerDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner showMessage() {
        return args -> System.out.println(LayerMessage.text());
    }
}
~~~

Khi app chạy, Spring Boot thực thi `CommandLineRunner` và in chuỗi từ Java API. Không có thread HTTP server giữ tiến trình, vì cấu hình bên dưới đặt `web-application-type=none`.

### 5.5. `src/main/resources/application.properties`

~~~properties
spring.application.name=layer-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
~~~

Các property này giảm log trong ví dụ. Chúng **không đảm bảo** mọi runtime/JDK hoặc bên thứ ba không xuất thêm thông tin trên stderr. Khi kiểm chứng, tập trung vào dòng do `LayerDemoApplication` in, thay vì giả định toàn bộ console chỉ có một dòng.

### 5.6. Unit test — `src/test/java/dev/example/layer/LayerMessageTest.java`

~~~java
package dev.example.layer;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LayerMessageTest {

    @Test
    void messageIsStable() {
        assertEquals("LAYER_DEMO_OK", LayerMessage.text());
    }
}
~~~

`LayerMessageTest` được Maven Surefire nhận theo pattern `*Test` tại phase `test`. Test logic **không chứng minh** `layers.idx` tồn tại hoặc được đặt đúng; QA về packaging phải kiểm tra archive sau phase `package`.

## 6. Bật layering và đọc layer index

Tại thư mục project có `pom.xml`:

~~~bash
java -version
mvn -version
mvn clean verify
~~~

Bản executable mặc định:

~~~text
target/layer-demo-1.0.0.jar
~~~

**Kiểm tra entry trong archive:**

~~~bash
jar tf target/layer-demo-1.0.0.jar
~~~

Khi lớp được bật, cần có các entry đáng chú ý:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/dev/example/layer/LayerDemoApplication.class
BOOT-INF/classes/dev/example/layer/LayerMessage.class
BOOT-INF/classes/application.properties
BOOT-INF/lib/...
BOOT-INF/layers.idx
org/springframework/boot/loader/...
~~~

Danh sách đầy đủ phụ thuộc các transitive dependencies của phiên bản Boot cụ thể. `BOOT-INF/layers.idx` là **bằng chứng trực tiếp** cho metadata phân lớp.

### 6.1. Xem nội dung `layers.idx`

Trên Linux/macOS, nếu có `unzip`:

~~~bash
unzip -p target/layer-demo-1.0.0.jar BOOT-INF/layers.idx
~~~

Nội dung có cấu trúc tên lớp và các đường dẫn, khái niệm tương tự:

~~~text
- "dependencies":
  - "BOOT-INF/lib/..."
- "spring-boot-loader":
  - "org/springframework/boot/loader/..."
- "snapshot-dependencies":
- "application":
  - "BOOT-INF/classes/"
~~~

**Đây là bản minh họa đã rút gọn**, không phải nội dung từng byte của file `layers.idx`: JAR thật có nhiều artifact names và entry paths; có lớp trống nếu demo không có SNAPSHOT. Không dựa vào khoảng trắng hoặc danh sách này để viết parser thủ công; dùng `jarmode=tools` hoặc công cụ ZIP có hỗ trợ format.

Nếu `unzip` không có trên Windows, có thể tạo thư mục tạm, chạy `jar xf` **trong thư mục đó** rồi đọc `BOOT-INF/layers.idx`. Không giải nén bừa vào project root hoặc thư mục có dữ liệu quan trọng.

### 6.2. Liệt kê lớp bằng Spring Boot JAR tools

Khi `includeTools=true` và có executable layered JAR:

~~~bash
java -Djarmode=tools -jar target/layer-demo-1.0.0.jar list-layers
~~~

Các tên lớp mong đợi trong chế độ mặc định (theo thứ tự):

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

Lệnh trên **không chạy business app** và không in `LAYER_DEMO_OK`. Nó khởi động special `tools` mode để đọc thông tin của archive.

### 6.3. Trích xuất các lớp

~~~bash
java -Djarmode=tools -jar target/layer-demo-1.0.0.jar \
    extract --layers --destination target/layer-extract
~~~

Trên Windows PowerShell, dùng một dòng:

~~~powershell
java -Djarmode=tools -jar target\layer-demo-1.0.0.jar extract --layers --destination target\layer-extract
~~~

Kết quả tạo thư mục trích xuất có các lớp tương ứng, ví dụ:

~~~text
target/layer-extract/
├── dependencies/
├── spring-boot-loader/
├── snapshot-dependencies/
└── application/
~~~

**Thư mục rỗng có thể không có nội dung đáng kể** khi project không dùng SNAPSHOT dependency. Dùng công cụ liệt kê file để kiểm tra từng layer chứa những entry nào. Đây là output trên filesystem do command tools tạo; **không phải** cấu trúc thư mục riêng đã có sẵn bên trong JAR trước khi extract.

Nếu muốn chạy lại `extract`, hãy chọn một **đích trống** khác, hoặc dọn đúng thư mục do bài thực hành tự tạo. Không ghi đè tùy tiện vào thư mục có dữ liệu.

### 6.4. Chạy ứng dụng như bình thường

~~~bash
java -jar target/layer-demo-1.0.0.jar
~~~

**Dòng do Java code in:**

~~~text
LAYER_DEMO_OK
~~~

**Điểm quan trọng:** việc tồn tại `layers.idx` không làm đổi output của app. Packaging metadata phục vụ container/repackaging tools, không thay đổi giá trị trả về của `LayerMessage.text()`.

## 7. Tắt layering nhưng vẫn giữ executable JAR

**Phương án trực tiếp:** trong plugin configuration, đặt:

~~~xml
<configuration>
    <layers>
        <enabled>false</enabled>
    </layers>
</configuration>
~~~

Đây là **fragment** cần nằm trong `spring-boot-maven-plugin`. Khi áp dụng vào POM đầy đủ ở mục 5, chỉ cần override property tương đương:

~~~bash
mvn clean verify -Dlayers.enabled=false
~~~

Vì `<enabled>${layers.enabled}</enabled>` đã được nối với Maven property, lệnh trên tắt **việc tạo metadata phân lớp** của Boot repackaging. Đây **không** phải một property system chuẩn tự hoạt động với mọi POM; nếu bạn sao chép lệnh sang POM không có interpolation này, hãy xem effective POM hoặc dùng XML fragment trực tiếp.

### Bằng chứng PASS khi tắt

1. `target/layer-demo-1.0.0.jar` vẫn được tạo vì goal `repackage` vẫn chạy.
2. `jar tf target/layer-demo-1.0.0.jar` **không còn entry `BOOT-INF/layers.idx`**.
3. `BOOT-INF/classes` và `BOOT-INF/lib` vẫn có; đó là layout executable JAR bình thường.
4. `java -jar target/layer-demo-1.0.0.jar` vẫn in `LAYER_DEMO_OK`.
5. Không dùng `java -Djarmode=tools ... list-layers` làm QA chính cho trạng thái tắt, vì archive có thể không chứa tools hoặc không có dữ liệu layer để liệt kê. Hãy kiểm tra index và runtime trực tiếp.

**Không nhầm các cách tắt:**

| Cách làm | Thực chất | Có tạo executable JAR? |
| --- | --- | --- |
| `layers.enabled=false` | Không tạo layer index | **Có**, nếu `repackage` còn chạy |
| `includeTools=false` | Không nhúng jar tools để extract | **Có**, layering có thể vẫn bật và còn `layers.idx` |
| `spring-boot.repackage.skip=true` | Bỏ qua goal repackage | Không có **Boot executable output từ goal đó** |
| Bỏ hẳn Boot plugin | Không có Boot repackage execution theo cấu hình thông thường | Plain JAR có thể vẫn được tạo |
| `layout=NONE` | Đóng dependencies mà không có Boot launcher | Không phải executable JAR theo kiểu `java -jar` thông thường |

**Không dùng `skip` hoặc `layout=NONE` để “tắt lớp”** nếu mục tiêu vẫn là có executable JAR. Chúng thay đổi hợp đồng đóng gói khác hẳn.

## 8. Tắt công cụ trích xuất mà vẫn giữ layers

Trong Spring Boot 4.1.2, khi tạo layered JAR, plugin có thể đưa thư viện `spring-boot-jarmode-tools` vào executable archive. Đây là công cụ hỗ trợ các lệnh `list-layers` và `extract`; nó **không phải bắt buộc để ứng dụng chạy bằng `java -jar`**.

Nếu yêu cầu release không bao gồm tools, đặt **ở cấp plugin configuration**:

~~~xml
<configuration>
    <layers>
        <enabled>true</enabled>
    </layers>
    <includeTools>false</includeTools>
</configuration>
~~~

Với POM đầy đủ của mục 5:

~~~bash
mvn clean verify -Dlayers.enabled=true -Dlayers.tools.enabled=false
~~~

**Dấu hiệu kỳ vọng:**

- Archive vẫn có `BOOT-INF/layers.idx` vì layering bật.
- Archive **không được đính kèm `spring-boot-jarmode-tools`**, nên không nên mong `java -Djarmode=tools -jar ... list-layers` hoạt động.
- Ứng dụng vẫn chạy bằng `java -jar` và in `LAYER_DEMO_OK`.
- Dockerfile nào phụ thuộc `jarmode=tools extract` sẽ phải thay workflow hoặc bật tools trong stage build; không thể vừa loại tool khỏi archive vừa giả định lệnh extract nội bộ còn khả dụng.

**Quy tắc:** `layers.enabled` điều khiển **metadata layer**; `includeTools` điều khiển **công cụ xử lý layer**. Đây là hai công tắc độc lập về mục đích. Trong tài liệu Spring Boot 4.1.x, dùng tên **`includeTools`**, không dùng tham số cũ `includeLayerTools`.

## 9. Tại sao cần file `layers.xml`?

Bốn layer mặc định đủ cho nhiều ứng dụng, nhưng không phải mọi dependency đều thay đổi với cùng tần suất. Ví dụ:

- Một dự án phụ thuộc nhiều module `org.springframework` ít thay đổi trong suốt một release train.
- Có một nhóm dependency nội bộ `com.acme:*` thường thay đổi theo policy riêng.
- Một số local modules trong reactor thay đổi cùng application source, nên có thể giữ chúng trong `application` layer.
- Một số SNAPSHOT dependencies được tái tạo thường xuyên hơn release dependencies.

**Mục đích tùy chỉnh** là đưa nội dung có lịch thay đổi tương tự vào cùng nhóm, và đặt nhóm ổn định trước nhóm hay đổi. File `layers.xml` được dùng **khi `spring-boot:repackage` chạy**, không phải cấu hình Spring `application.properties` lúc runtime.

### Cách bật file tùy chỉnh

Trong `spring-boot-maven-plugin`:

~~~xml
<configuration>
    <layers>
        <enabled>true</enabled>
        <configuration>${project.basedir}/src/layers.xml</configuration>
    </layers>
</configuration>
~~~

Giá trị `${project.basedir}` trỏ tới thư mục của **POM hiện tại**. Nếu dùng multi-module, mỗi module có `project.basedir` riêng; khi dùng fragment trong module `web-app`, file XML phải ở `web-app/src/layers.xml` hoặc bạn phải cung cấp đường dẫn tương ứng.

**Không đặt `layers.xml` vào `<resources>` chỉ để plugin tìm thấy nó.** File này là build-time plugin configuration. Trường hợp cấu hình được đóng sẵn trong một **plugin dependency JAR** là cơ chế `configurationName` khác, được nói riêng ở mục 12.

## 10. File `src/layers.xml` hợp lệ cho Spring Boot 4.1.x

Ví dụ dưới đây **thực sự tách thêm một layer `spring-framework`** cho các dependency có groupId `org.springframework`. Với app chỉ dùng `spring-boot-starter`, Spring Framework modules như `spring-core` thuộc groupId này và có thể được kiểm tra trong layer tương ứng.

### 10.1. Nội dung XML hoàn chỉnh

Tệp: **`src/layers.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<layers xmlns="http://www.springframework.org/schema/boot/layers"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="
          http://www.springframework.org/schema/boot/layers
          https://www.springframework.org/schema/boot/layers/layers-4.1.xsd">

    <application>
        <into layer="spring-boot-loader">
            <include>org/springframework/boot/loader/**</include>
        </into>
        <into layer="application" />
    </application>

    <dependencies>
        <into layer="application">
            <includeModuleDependencies />
        </into>

        <into layer="snapshot-dependencies">
            <include>*:*:*SNAPSHOT</include>
        </into>

        <into layer="spring-framework">
            <include>org.springframework:*</include>
        </into>

        <into layer="dependencies" />
    </dependencies>

    <layerOrder>
        <layer>dependencies</layer>
        <layer>spring-framework</layer>
        <layer>spring-boot-loader</layer>
        <layer>snapshot-dependencies</layer>
        <layer>application</layer>
    </layerOrder>
</layers>
~~~

**Đây là file XML hoàn chỉnh**, không phải snippet. Namespace và XSD **`layers-4.1.xsd`** phù hợp Spring Boot Maven Plugin 4.1.x. Khi chuyển sang version Boot khác, kiểm tra XSD mới thay vì giữ mãi schema version này.

### 10.2. Vì sao chọn thứ tự `<into>` như vậy?

Spring Boot xét các `<into>` từ **trên xuống dưới** trong từng section để “nhận” nội dung:

- **`<application>`:** đầu tiên bắt các class của Boot launcher với Ant-style path pattern `org/springframework/boot/loader/**` vào `spring-boot-loader`. Phần còn lại của application classes/resources vào `application`.
- **`<dependencies>`:** đầu tiên các dependency **thuộc reactor hiện tại** vào `application`. Tiếp theo các dependency có version `...SNAPSHOT` vào `snapshot-dependencies`. Tiếp theo groupId `org.springframework` vào `spring-framework`. Phần chưa được nhận vào `dependencies`.
- Mỗi `<into>` phía sau chỉ xét phần **chưa bị rule trước nhận**. Nếu một dependency vừa là local module vừa là SNAPSHOT, nó được nhận theo rule module dependency đầu tiên, không bị xếp lại vào snapshot.
- `<into layer="dependencies" />` không có `<include>` là **catch-all** cho dependency chưa khớp. `<into layer="application" />` cũng là catch-all trong application section.

**Đặt rule riêng trước catch-all.** Nếu cho catch-all `dependencies` lên đầu, hầu hết dependencies bị nhận ngay và custom `spring-framework` hoặc `snapshot-dependencies` ở dưới có thể trống. Đây là lỗi cấu hình XML rất hay gặp.

### 10.3. `<layerOrder>` không giống thứ tự matching rules

Các `<into>` định nghĩa **quy tắc chọn entry**; `<layerOrder>` định nghĩa **thứ tự ghi layer** dùng cho cache:

~~~text
dependencies
spring-framework
spring-boot-loader
snapshot-dependencies
application
~~~

Tất cả tên layer được tham chiếu bởi `<into>` phải có trong `<layerOrder>`. Quên `spring-framework` hoặc viết sai tên có thể làm build lỗi. Lưu ý `spring-boot-loader` là một lớp được khai báo ở phần `application` XML, nhưng được đặt gần các lớp ổn định trong `layerOrder`.

### 10.4. Điều gì xảy ra với dependency trong bài mẫu?

- Các JAR thuộc groupId `org.springframework`, ví dụ `spring-core`, được rule `spring-framework` nhận nếu chưa được rule trước nhận.
- Các dependency release khác đi vào `dependencies`.
- Với project không có SNAPSHOT dependency, `snapshot-dependencies` có thể không chứa entry đáng kể nhưng tên layer vẫn có trong cấu hình.
- Demo một module không có local module dependency, nên `<includeModuleDependencies />` không nhận gì; vẫn giữ rule để cấu hình hoạt động hợp lý khi project được chuyển sang multi-module Maven.
- Các class `LayerDemoApplication.class`, `LayerMessage.class` và resource `application.properties` thuộc `application`; Boot launcher classes thuộc `spring-boot-loader`.

**Không dùng ví dụ `<include>com.acme:*</include>` rồi khẳng định layer mới chắc có file** nếu POM không có dependency tương ứng. Với rule `org.springframework:*`, bản demo có khả năng quan sát rõ một layer tùy chỉnh không rỗng.

## 11. Kích hoạt XML tùy chỉnh và xác minh

Sau khi tạo `src/layers.xml`, **chỉnh đúng block `<layers>`** của POM ở mục 5 thành:

~~~xml
<layers>
    <enabled>${layers.enabled}</enabled>
    <configuration>${project.basedir}/src/layers.xml</configuration>
</layers>
~~~

Giữ nguyên `<includeTools>${layers.tools.enabled}</includeTools>` bên ngoài block. Không tạo hai block `<layers>` cùng cấp trong một plugin configuration; chỉ có **một** block cấu hình layer.

Chạy:

~~~bash
mvn clean verify -Dlayers.enabled=true -Dlayers.tools.enabled=true
~~~

**Bước A — kiểm tra index:**

~~~bash
jar tf target/layer-demo-1.0.0.jar
unzip -p target/layer-demo-1.0.0.jar BOOT-INF/layers.idx
~~~

Cần thấy layer mới `spring-framework` và entry dependency `org.springframework` được phân loại theo quy tắc XML. Không tự khẳng định số file trong layer, vì transitive dependencies khác nhau theo phiên bản/resolution.

**Bước B — hỏi JAR tools:**

~~~bash
java -Djarmode=tools -jar target/layer-demo-1.0.0.jar list-layers
~~~

Danh sách layer mong đợi theo `layerOrder`:

~~~text
dependencies
spring-framework
spring-boot-loader
snapshot-dependencies
application
~~~

**Bước C — trích xuất ra thư mục riêng:**

~~~bash
java -Djarmode=tools -jar target/layer-demo-1.0.0.jar \
    extract --layers --destination target/custom-layer-extract
~~~

Trong thư mục trích xuất phải có cách phân tách các file theo cấu hình XML, trong đó `spring-framework` là tên layer mới. Kiểm tra `target/custom-layer-extract/spring-framework/` và `target/custom-layer-extract/dependencies/` để xem sự khác biệt. **Lớp mới tồn tại trong index nhưng không có file** là một tín hiệu cần xem lại rule/pattern hoặc dependency thực tế, không nhất thiết là lỗi của parser.

**Bước D — kiểm chứng runtime không đổi:**

~~~bash
java -jar target/layer-demo-1.0.0.jar
~~~

Stdout do application code in vẫn chứa:

~~~text
LAYER_DEMO_OK
~~~

Nếu app không khởi động sau khi đổi layering, lỗi thường nằm ở cú pháp XML, phân loại không bao phủ một số entry, hoặc archive layout/plugin execution bị tùy biến sai, không phải do business code thay đổi.

## 12. Các cách tùy chỉnh nâng cao

### 12.1. Đưa dependency nội bộ vào layer riêng

Khi một ứng dụng có dependency thực `com.acme:inventory-client:1.2.3`, có thể thêm một rule:

~~~xml
<into layer="company-dependencies">
    <include>com.acme:*</include>
</into>
~~~

Đặt nó trong `<dependencies>` **sau các rule ưu tiên cao hơn nhưng trước catch-all**. Đồng thời phải thêm:

~~~xml
<layer>company-dependencies</layer>
~~~

vào `<layerOrder>` ở vị trí phù hợp với độ biến động của dependency nội bộ. Nếu muốn SNAPSHOT nội bộ vào `snapshot-dependencies`, giữ rule SNAPSHOT trước rule `com.acme:*`. Nếu muốn tất cả com.acme deps, kể cả SNAPSHOT, vào company layer, chuyển company rule lên trước SNAPSHOT (và chú ý module dependency đã được rule đầu nhận).

**Không đưa `includeModuleDependencies` vào company layer mà vẫn mong project library thuộc reactor giữ ở `application`:** đó là thay đổi chính sách phân nhóm và cần kiểm tra cache khi một local module đổi.

### 12.2. Tách application resources vào layer khác

`<application>` hỗ trợ Ant-style `<include>`/`<exclude>` patterns. Có thể dùng rule để đặt những resource/config ổn định vào một layer riêng, nhưng phải xác định **entry path thực tế** trong JAR trước khi viết glob. Đừng mặc định path source `src/main/resources/...` trùng với entry path trong executable archive. Kiểm tra `jar tf` và tài liệu matching semantics của phiên bản plugin, sau đó bổ sung rule chuyên biệt **trước catch-all `<into layer="application" />`**.

Mọi tên layer mới phải được thêm vào `layerOrder`; kiểm tra index và kết quả extract. Nếu config/secrets được generate động, tách chúng ra layer riêng không biến chúng thành ổn định: đó vẫn là content thay đổi và có thể làm cache invalidated.

### 12.3. Dùng `configurationName` thay cho đường dẫn file

Spring Boot Maven Plugin 4.1.x cũng hỗ trợ cấu hình layer trong **classpath của chính Maven plugin**. Ví dụ một plugin dependency JAR chứa:

~~~text
META-INF/spring/layers/custom.xml
~~~

Bạn có thể cấu hình:

~~~xml
<layers>
    <enabled>true</enabled>
    <configurationName>custom</configurationName>
</layers>
~~~

và thêm dependency JAR chứa file vào `<dependencies>` của **spring-boot-maven-plugin** (plugin dependencies, không phải dependency runtime của ứng dụng).

Cơ chế này thích hợp khi tổ chức muốn áp dụng quy tắc chung từ một artifact build tool. Nó **không tương đương** việc đặt `META-INF/spring/layers/custom.xml` trong `src/main/resources` của ứng dụng; app runtime classpath và Maven plugin classpath là hai môi trường khác nhau. Không cấu hình đồng thời `configuration` và `configurationName` rồi dựa vào một ưu tiên không được tài liệu xác nhận; chọn một cách.

### 12.4. Repackage artifact có classifier

Maven plugin có thể tạo executable `-exec.jar` trong khi giữ ordinary JAR làm artifact chính. Điều đó là cơ chế `<classifier>exec</classifier>` của `repackage`, **tách biệt với layer rules**. Nếu dùng classifier, QA phải kiểm tra `layers.idx` ở **đúng file executable `-exec.jar`**, không kiểm tra nhầm plain main JAR.

Tương tự, một WAR có layout `WEB-INF/classes`, `WEB-INF/lib` và `WEB-INF/lib-provided` theo đặc thù servlet packaging; không dùng cứng path `BOOT-INF/layers.idx` của JAR làm giả định cho mọi WAR. Ví dụ trong bài này dùng `jar` packaging.

## 13. Maven corporate parent hoặc BOM thuần

Khi project **không** dùng `spring-boot-starter-parent` mà chỉ import `spring-boot-dependencies` BOM, không thể mặc định có plugin execution `repackage`. Cần pin phiên bản plugin và bind goal trong phase `package`:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>4.1.2</version>
    <configuration>
        <layers>
            <enabled>true</enabled>
            <configuration>${project.basedir}/src/layers.xml</configuration>
        </layers>
        <includeTools>true</includeTools>
    </configuration>
    <executions>
        <execution>
            <id>repackage</id>
            <phase>package</phase>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Đây là **fragment cho `build/plugins`**, không phải POM hoàn chỉnh. Maven `jar` lifecycle cần tạo source JAR trước khi Boot goal `repackage` chạy; với custom Jar Plugin executions cùng phase, đặt Jar Plugin trước Spring Boot Plugin để tránh nguồn chưa được tạo.

Muốn dùng fragment trên, project còn phải tự quản lý dependency versions, compiler release `17`, test plugins và resources theo corporate build policy. **Import BOM chỉ quản lý phiên bản dependencies, không tự cung cấp plugin executions.**

Để kiểm tra cấu hình hiệu lực:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
mvn clean verify
~~~

Trong effective POM, tìm đúng một `spring-boot-maven-plugin` có execution `repackage`, một block `layers` với values mong muốn và file `src/layers.xml` có thật. Không vô tình gắn `repackage` vào Maven parent packaging `pom` hoặc library module không có application main class.

## 14. Docker caching: khi nào tách lớp thật sự mang lại lợi ích?

Một Dockerfile có thể copy executable JAR dưới dạng **một** file:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/layer-demo-1.0.0.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

Đoạn này **không tự tận dụng `layers.idx` để chia Docker layers**: lệnh `COPY` vẫn nhận cả file JAR, nên sửa một class thường làm invalidated lớp Docker chứa JAR.

Để tận dụng layering, build stage cần trích xuất:

~~~dockerfile
FROM eclipse-temurin:17-jre AS unpack
WORKDIR /builder
COPY target/layer-demo-1.0.0.jar application.jar
RUN java -Djarmode=tools -jar application.jar extract --layers --destination extracted

FROM eclipse-temurin:17-jre
WORKDIR /application
COPY --from=unpack /builder/extracted/dependencies/ ./
COPY --from=unpack /builder/extracted/spring-boot-loader/ ./
COPY --from=unpack /builder/extracted/snapshot-dependencies/ ./
COPY --from=unpack /builder/extracted/application/ ./
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

**Đây là Dockerfile minh họa cho bốn layer mặc định**, không phải hướng dẫn production bảo mật đầy đủ. Nó giả định layer tools đã được include, `layers.idx` có dữ liệu và runtime dùng Java 17. Khi chuyển sang **custom `spring-framework` layer**, phải thêm một lệnh `COPY --from=unpack /builder/extracted/spring-framework/ ./` **đúng theo `layerOrder`**; nếu quên, runtime có thể thiếu các dependency đã bị chuyển sang layer đó.

Với production nên thêm non-root user, pinned base image digest, image scanning, provenance, .dockerignore và nguyên tắc secret handling theo chính sách tổ chức. Trong ví dụ tối giản này, mục tiêu chỉ là **chứng minh quan hệ giữa layer index và Docker COPY boundaries**.

### Ba lưu ý về cache

1. **Thứ tự lớp quan trọng**: nếu layer dễ thay đổi đặt trước layer ổn định, các lớp sau dễ bị rebuild theo cache dependency rules.
2. **Nội dung lớp quan trọng**: một SNAPSHOT dependency đổi thường xuyên sẽ invalidated layer chứa nó, nhưng không nhất thiết làm invalidated các lớp ổn định trước đó.
3. **Cách dựng image quan trọng**: layering trong JAR **không tự** tạo thêm Docker layers. Công cụ build container phải sử dụng `layers.idx` (qua jarmode/buildpacks hoặc cơ chế tương ứng). Hãy đo `docker history`, image layers và cache hits thực tế thay vì khẳng định luôn tiết kiệm một con số cố định.

## 15. Quy trình QA cho ba chế độ

| Chế độ | Maven invocation | Kết quả kỳ vọng |
| --- | --- | --- |
| **Layer mặc định/bật** | `mvn clean verify -Dlayers.enabled=true -Dlayers.tools.enabled=true` | Có `BOOT-INF/layers.idx`, tools list/extract dùng được, app chạy |
| **Tắt layering** | `mvn clean verify -Dlayers.enabled=false` | Không có `BOOT-INF/layers.idx`, app executable vẫn chạy |
| **Tùy chỉnh XML** | Thêm `src/layers.xml` và cấu hình `layers.configuration`, rồi `mvn clean verify -Dlayers.enabled=true -Dlayers.tools.enabled=true` | Có `spring-framework` layer, XML rules/`layerOrder` phản ánh trong index/tools, app chạy |
| **Bật layers nhưng bỏ tools** | `mvn clean verify -Dlayers.enabled=true -Dlayers.tools.enabled=false` | Có index; không có jar tools trong archive; app chạy |

**Không được so kết quả của hai chế độ chỉ bằng số file JAR:** cả bốn đều có thể xuất cùng tên `target/layer-demo-1.0.0.jar` do `repackage` chạy. Khác biệt nằm ở **layer index, tool dependency và entry assignments**.

### Lệnh QA mẫu trên Linux/macOS: layering mặc định

~~~bash
set -eu
mvn -B -ntp clean verify -Dlayers.enabled=true -Dlayers.tools.enabled=true

JAR=target/layer-demo-1.0.0.jar
jar tf "$JAR" | grep -Fx 'BOOT-INF/layers.idx'
java -Djarmode=tools -jar "$JAR" list-layers
java -jar "$JAR" | grep -Fx 'LAYER_DEMO_OK'
~~~

Lệnh `jar tf` + `grep -Fx` xác nhận entry layer index chính xác. Lệnh `java -jar` được dùng để kiểm chứng runtime không bị thay đổi. **Nhưng test này không tự đảm bảo một Dockerfile nào đó đã tận dụng cache**; đó là phép kiểm tra riêng khi build container.

### Lệnh QA mẫu trên Linux/macOS: đã tắt layering

~~~bash
set -eu
mvn -B -ntp clean verify -Dlayers.enabled=false

JAR=target/layer-demo-1.0.0.jar

if jar tf "$JAR" | grep -Fx 'BOOT-INF/layers.idx'; then
    echo "FAIL: layers.idx must not exist"
    exit 1
fi

java -jar "$JAR" | grep -Fx 'LAYER_DEMO_OK'
echo "LAYERING_DISABLED_AND_APP_OK"
~~~

**Lưu ý đường ống shell:** ví dụ dùng `set -eu` nhưng không dùng `pipefail`; ở đây `grep` đóng vai trò kiểm tra `layers.idx` qua `if` và ứng dụng có một dòng riêng. Trong CI nghiêm ngặt, thêm `set -o pipefail` khi shell hỗ trợ và kiểm tra exit code của Java trực tiếp để tránh mất lỗi ở bên trái pipeline.

### Windows PowerShell: đọc output không cần `unzip`

~~~powershell
mvn clean verify -Dlayers.enabled=true -Dlayers.tools.enabled=true
if ($LASTEXITCODE -ne 0) { throw "Maven build failed" }

jar tf target\layer-demo-1.0.0.jar |
    Select-String -SimpleMatch 'BOOT-INF/layers.idx'

java -Djarmode=tools -jar target\layer-demo-1.0.0.jar list-layers
if ($LASTEXITCODE -ne 0) { throw "Layer tools failed" }

java -jar target\layer-demo-1.0.0.jar
if ($LASTEXITCODE -ne 0) { throw "java -jar failed" }
~~~

Với PowerShell, đầu ra `Select-String` cho biết có match nhưng trong CI phải kiểm tra có ít nhất một kết quả, ví dụ lưu vào biến và kiểm tra `$null`. Dùng phiên bản Maven/Java từ môi trường đã cài sẵn hoặc Wrapper của project nếu được cung cấp.

## 16. Những lỗi phổ biến và chẩn đoán

| Triệu chứng | Nguyên nhân đáng kiểm tra | Cách xử lý |
| --- | --- | --- |
| `mvn package` tạo JAR nhưng không có `layers.idx` | `layers.enabled=false`, plugin/version không phù hợp hoặc đang kiểm tra nhầm ordinary JAR | Xem effective POM, đúng Boot repackaged JAR và `jar tf` |
| Chạy `mvn spring-boot:repackage` riêng báo thiếu JAR đầu vào | Goal repackage cần source jar/war từ package phase | Dùng `mvn clean package` / `mvn clean verify` |
| `java -Djarmode=tools` không chạy | `includeTools=false`, tools không có trong archive, archive đã đổi layout, JAR bị build sai | Kiểm tra includeTools và `jar tf`, bật tools nếu cần extract |
| Một bài hướng dẫn dùng `-Djarmode=layertools` | Hướng dẫn cho Spring Boot bản cũ | Dùng `-Djarmode=tools` cho Boot 4.1.x |
| Custom XML bị từ chối vì XSD | Sai namespace, dùng schema 3.x/4.0 cho 4.1 hoặc sai cấu trúc | Dùng `layers-4.1.xsd` và mẫu `<layers>` hợp lệ |
| Maven báo không tìm thấy `src/layers.xml` | `project.basedir` sai module, chưa tạo file, filename case khác | Kiểm tra đường dẫn của POM hiện tại |
| Lớp custom không xuất hiện trong `list-layers` | Không bật cấu hình XML hoặc kiểm tra nhầm archive cũ | Xem plugin configuration và chạy `clean verify` |
| Layer mới có tên nhưng trống | `include` không match dependency group/path nào | Kiểm tra `dependency:tree`, `jar tf`, XML pattern |
| SNAPSHOT bị xếp nhầm vào company layer | Thứ tự `<into>` khiến rule company nhận trước | Chuyển SNAPSHOT rule lên trước nếu đó là policy |
| Local module dependency rơi vào `dependencies` | Core không thuộc cùng reactor hiện tại | Build reactor nhất quán hoặc chấp nhận policy phân loại khác |
| `layerOrder` thiếu layer custom | Tên tham chiếu không được liệt kê đủ | Bổ sung tên layer chính xác vào `layerOrder` |
| Dockerfile custom thiếu dependencies | Thêm layer XML nhưng quên `COPY` layer đó | Cập nhật Dockerfile theo `list-layers` |
| Docker vẫn rebuild cả JAR khi đổi một class | Dockerfile chỉ `COPY app.jar` làm một layer | Dùng jarmode extract/buildpacks và COPY per-layer |
| `includeTools=false` nhưng vẫn kỳ vọng extract | Tools là thành phần tùy chọn tách khỏi layer index | Dùng tools ở build artifact/stage hoặc đổi workflow |
| App không chạy sau khi sửa packaging | Source JAR/manifest/classifier hoặc missing dependency do config khác | Kiểm tra `Main-Class`, `Start-Class`, `BOOT-INF/lib` và chạy `java -jar` |
| `layers.idx` khác giữa hai build cùng commit | Reactor membership, dependency resolution, plugin config khác | So effective POM, dependency graph, versions và build flags |
| Java 17 không chạy do bytecode version | JDK/toolchain cấu hình sai, compile target cao hơn runtime | `java -version`, Maven compiler release, JDK policy |

**Quy trình tìm lỗi:** (1) đọc Maven goal/execution thực sự chạy → (2) xem effective POM → (3) kiểm tra đúng archive → (4) xem `BOOT-INF/layers.idx` → (5) dùng `list-layers`/`extract` khi có tools → (6) thử `java -jar` → (7) kiểm tra container caching. Sửa **đúng lớp gây lỗi**, không thay đổi app code khi chỉ có vấn đề packaging metadata.

## 17. Bài tập tự kiểm tra và đáp án

**1. Lớp mặc định của Spring Boot Maven Plugin là những lớp nào?**

Đáp án: `dependencies`, `spring-boot-loader`, `snapshot-dependencies` và `application`; thứ tự mặc định cũng được sắp từ lớp thường ổn định đến lớp thường hay thay đổi.

**2. Bật layering có khiến `jar tf` hiển thị một file JAR riêng cho mỗi layer không?**

Không. Layering chủ yếu thêm `BOOT-INF/layers.idx`; các công cụ extract/container build mới phân tách filesystem hoặc Docker layers.

**3. Đặt `<layers><enabled>false</enabled></layers>` có làm ứng dụng không chạy được `java -jar` không?**

Không, nếu `spring-boot:repackage` vẫn chạy và tạo executable JAR hợp lệ. Chỉ tắt thông tin phân lớp, không tắt Boot launcher hay dependencies.

**4. Sự khác nhau giữa `enabled=false` và `includeTools=false` là gì?**

`enabled=false` không tạo layer index; `includeTools=false` loại công cụ JAR tools dù layer index vẫn có thể tồn tại nếu enabled=true.

**5. Muốn dùng XML custom, cần khai báo gì trong POM?**

Dùng `<layers><enabled>true</enabled><configuration>${project.basedir}/src/layers.xml</configuration></layers>` bên trong Spring Boot Maven Plugin configuration. Tạo file XML thật tại đường dẫn đã khai báo.

**6. Schema XML nào phù hợp Spring Boot Maven Plugin 4.1.x?**

`https://www.springframework.org/schema/boot/layers/layers-4.1.xsd` cùng namespace `http://www.springframework.org/schema/boot/layers`.

**7. Trong XML, thứ tự các `<into>` có quan trọng không?**

Có. Các rule chạy từ trên xuống, rule trước nhận nội dung phù hợp, rule sau chỉ thấy phần còn lại. Đặt catch-all quá sớm sẽ “nuốt” nội dung dành cho layer riêng.

**8. `layerOrder` có thể bỏ layer `spring-framework` nếu XML đã khai báo nó ở `<dependencies>` không?**

Không. Mọi layer được tham chiếu cần được liệt kê trong `layerOrder`; tên layer phải khớp.

**9. Vì sao một module dependency cùng tọa độ có thể được phân lớp khác nhau giữa hai lần build?**

Nếu một lần core thuộc cùng Maven reactor còn lần khác chỉ có JAR đã install ở local repository, Boot có thể nhận diện nó lần đầu là module dependency và lần sau là regular dependency.

**10. Nếu Dockerfile chỉ `COPY target/app.jar app.jar` thì có tận dụng layer index không?**

Không tự động. Một lệnh COPY file JAR chỉ tạo layer Docker chứa toàn archive; cần bước extract/COPY phân lớp hoặc build tool dùng metadata.

**11. Nếu đặt `includeTools=false`, có thể vẫn dùng `java -jar` bình thường không?**

Có. JAR tools phục vụ trích xuất/kiểm tra layer, không phải business runtime của Spring Boot app.

**12. `layers.idx` tồn tại có đảm bảo container image nhỏ hơn không?**

Không. Tính năng giúp cache theo lớp và tối ưu rebuild trong kịch bản phù hợp; tổng dung lượng image và cache hit phụ thuộc dependency graph, Dockerfile, base image và tần suất thay đổi.

## 18. Checklist áp dụng vào dự án thật

- [ ] Spring Boot Maven Plugin đúng phiên bản với project; hiểu cách goal `repackage` được bind.
- [ ] Nếu dùng starter parent, không tạo execution `repackage` trùng không cần thiết.
- [ ] `layers.enabled` được xác định rõ theo nhu cầu, không phụ thuộc ngẫu nhiên vào config từ profile.
- [ ] Khi bật, `jar tf` cho thấy `BOOT-INF/layers.idx`.
- [ ] Nếu CI dùng `jarmode=tools`, `includeTools=true`.
- [ ] Khi tắt, không còn `layers.idx` nhưng `java -jar` vẫn chạy.
- [ ] File `src/layers.xml` có đúng XML namespace và XSD tương thích Boot 4.1.
- [ ] Các rule `<into>` theo thứ tự ưu tiên, catch-all ở cuối.
- [ ] `layerOrder` chứa đầy đủ tên layer được dùng trong XML.
- [ ] Chạy `list-layers` và xác minh layer custom thật sự nhận dependency/entry mong muốn.
- [ ] Nếu thêm layer mới, chỉnh Dockerfile/OCI tool copy theo layer order.
- [ ] Module dependencies được nhận diện nhất quán theo reactor build CI.
- [ ] Không nhầm layer index với classpath layout/Java packages.
- [ ] Tách quyền build container và runtime secrets; không đóng secrets vào JAR.
- [ ] Kiểm tra artifact identity, Java runtime, unit tests và app smoke test trước phát hành.
- [ ] Đánh giá cache hit bằng build container thực tế, không chỉ suy luận từ số layer.
- [ ] Tách reproducibility (checksum, timestamp, dependency locking) khỏi vấn đề cache-layering.

**Kết luận:** Spring Boot Maven Plugin có **ba thao tác cốt lõi** với layered executable archive: `<layers><enabled>true</enabled></layers>` để bật, `false` để tắt, và `<layers><configuration>.../layers.xml</configuration></layers>` để tùy chỉnh. Kiểm tra bằng `BOOT-INF/layers.idx` và `-Djarmode=tools`, sau đó bảo đảm Dockerfile hay buildpacks thực sự sử dụng thứ tự phân lớp. **Layering giúp quản lý cache container, không thay thế việc kiểm thử executable JAR và không tự thay đổi chức năng ứng dụng.**

## 19. Tài liệu tham khảo chính thức

1. [Spring Boot Maven Plugin 4.1.2 — Packaging Executable Archives / Layered Jar or War](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
2. [Spring Boot Maven Plugin — Repackage Goal Parameters: layers, includeTools, outputTimestamp](https://docs.spring.io/spring-boot/maven-plugin/packaging.html#spring-boot:repackage)
3. [Spring Boot — Dockerfiles / Using JAR Tools and Layers](https://docs.spring.io/spring-boot/reference/packaging/container-images/dockerfiles.html)
4. [Spring Boot — Executable JAR Format and Nested JARs](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
5. [Spring Boot Maven Plugin — Using the Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html)
6. [Spring Boot Maven Plugin — Spring Boot 4.1 Layers XSD](https://www.springframework.org/schema/boot/layers/layers-4.1.xsd)
7. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
8. [Apache Maven — Introduction to Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
9. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
10. [Spring Boot Maven Plugin — Build Image](https://docs.spring.io/spring-boot/maven-plugin/build-image.html)
