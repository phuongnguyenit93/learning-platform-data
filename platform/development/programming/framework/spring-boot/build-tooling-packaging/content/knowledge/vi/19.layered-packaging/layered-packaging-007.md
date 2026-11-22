# Liệt kê và trích xuất lớp bằng chế độ jarmode tools

## 1. Tại sao một Spring Boot JAR cần được chia thành lớp?

Khi ứng dụng Spring Boot được build thành **executable JAR**, Maven **spring-boot:repackage** hoặc Gradle **bootJar** thường đưa application classes/resources vào **BOOT-INF/classes**, dependencies vào **BOOT-INF/lib**, đồng thời thêm Spring Boot Loader. Người dùng có thể chạy toàn bộ file bằng:

~~~bash
java -jar target/layer-lab-1.0.0.jar
~~~

Cách phân phối một file rất thuận tiện. Nhưng nếu đặt nguyên JAR lớn vào Docker image, mỗi lần sửa một Java class rồi rebuild JAR, lớp image chứa file JAR đó có thể đổi nội dung, kéo theo việc truyền và lưu trữ lại một lượng dữ liệu lớn dù phần lớn third-party dependencies không đổi.

Spring Boot hỗ trợ **layered JAR/WAR**: archive vẫn chạy được như một executable archive, nhưng chứa metadata xác định những file thuộc lớp nào. Với Spring Boot 3.5, công cụ **spring-boot-jarmode-tools** đi kèm archive có thể:

- **list-layers** — liệt kê tên các lớp trong archive.
- **extract** — giải nén application/dependencies ra layout phù hợp để chạy từ thư mục.
- **extract --layers** — trích nội dung **theo từng lớp**, thuận tiện tạo những Docker image layers riêng biệt.
- **help** — tra cứu options của từng lệnh.

Lệnh trọng tâm:

~~~bash
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar list-layers
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar extract --layers --destination extracted
~~~

**Điểm mấu chốt:** **jarmode=tools** chạy công cụ đóng gói/trích xuất trong Java, **không chạy main() của ứng dụng** và cũng **không tự tạo Docker image**. Nó đọc archive đã build, liệt kê hoặc tạo file trên filesystem để bạn sử dụng ở bước deploy/containerize tiếp theo.

Bài này thuộc chủ đề cha **Đóng gói theo lớp** và sẽ giải thích rõ cơ chế, lệnh chính xác, kết quả dự kiến, ví dụ Maven/Gradle Java 17 chạy được, Dockerfile multi-stage, các kiểu trích xuất khác nhau và cách xử lý lỗi.

## 2. Kiến thức nền: layered archive vẫn là executable archive

Một layered JAR Spring Boot 3.5 có cấu trúc đại diện:

~~~text
layer-lab-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── ... Boot Loader classes ...
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/layerlab/LayerLabApplication.class
    │   ├── com/example/layerlab/LayerController.class
    │   └── application.properties
    ├── lib/
    │   ├── spring-boot-....jar
    │   ├── spring-web-....jar
    │   ├── spring-boot-jarmode-tools-....jar
    │   └── ...
    ├── classpath.idx    (có thể có)
    └── layers.idx       (mặc định khi layering được bật)
~~~

Các tên phụ thuộc và đường dẫn chi tiết chỉ minh họa; nội dung thật phải được kiểm tra sau khi build. **layers.idx** là metadata ánh xạ thành phần archive vào các lớp và mô tả thứ tự lớp, **không phải một thư mục chứa các bản sao class**.

**spring-boot-jarmode-tools** là một JAR công cụ do build plugin thêm vào runtime archive theo mặc định khi tạo layered archive. Nhờ nó, Boot Loader có thể nhận **jarmode=tools** và chuyển sang thực thi lệnh công cụ trước khi gọi application main.

Phân biệt ba thứ:

| Thành phần | Vai trò | Có phải một Docker image layer không? |
| --- | --- | --- |
| **BOOT-INF/layers.idx** | File chỉ mục lớp bên trong Boot JAR | Không |
| **Các lớp Spring Boot** | Nhóm logical entries theo độ ổn định | Chưa phải Docker layers |
| **Docker/OCI image layers** | Những lớp filesystem do image builder tạo từ Dockerfile/build process | Có |

**list-layers** chỉ cho biết nhóm logic trong archive. **extract --layers** tạo các thư mục đại diện cho nhóm đó. Để biến chúng thành những OCI layers, bạn còn phải viết Dockerfile có các câu lệnh **COPY** riêng rồi build image.

## 3. Bốn lớp mặc định của Spring Boot 3.5

Spring Boot Maven và Gradle plugins thường dùng bốn lớp:

| Lớp | Nội dung điển hình | Tính thay đổi |
| --- | --- | --- |
| **dependencies** | Third-party dependencies không có **SNAPSHOT** trong version | Ít thay đổi khi chỉ sửa application code |
| **spring-boot-loader** | Các classes/bootstrap của Spring Boot Loader | Thường chỉ đổi khi nâng Boot/plugin |
| **snapshot-dependencies** | Dependencies có version chứa **SNAPSHOT** | Có thể thay đổi thường xuyên |
| **application** | Application classes/resources và local project/module dependencies | Thường thay đổi mỗi lần sửa ứng dụng |

Thứ tự mặc định:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

Thứ tự này đặt những thành phần có xác suất thay đổi thấp ở trước để tận dụng Docker layer caching. Nếu sửa một controller mà versions của Spring/Jackson không đổi, các lớp dependencies và loader có thể vẫn dùng lại các image layers cũ, còn lớp application được cập nhật.

**Không diễn giải** tên lớp theo kiểu mọi file trong **BOOT-INF/lib** luôn thuộc **dependencies**. Một dependency **SNAPSHOT** có thể vào **snapshot-dependencies**; một Maven reactor module hoặc Gradle project dependency thuộc phần build hiện tại thường vào **application**. Tập rules thực tế còn phụ thuộc build tool và file cấu hình custom layers.

**Không bắt buộc lớp nào cũng có file đáng kể.** Một project không phụ thuộc SNAPSHOT có thể có lớp **snapshot-dependencies** rỗng hoặc gần như rỗng. **list-layers** vẫn có thể hiển thị tên lớp đã khai báo trong chỉ mục.

### 3.1. Vì sao thứ tự lớp quan trọng?

Trong mô hình Docker/OCI filesystem layers, các thay đổi ở một layer có thể làm layer phía trên phải xây lại hoặc ảnh hưởng khả năng tái sử dụng cache. Để tối ưu, nhóm ổn định như **dependencies** thường đặt trước, phần ứng dụng thay đổi nhiều nhất đặt sau.

Tuy nhiên, **layering không hứa chắc image build nhanh hơn trong mọi trường hợp**. Hiệu quả phụ thuộc dung lượng dependencies, tỷ lệ cache hit, remote registry, Docker builder, build context và việc bạn có copy layer theo thứ tự ổn định hay không. Đo trước/sau mới kết luận được lợi ích trong CI cụ thể.

## 4. Tiền đề để dùng jarmode=tools

Trước khi chạy lệnh, cần có:

1. **JDK/JRE tương thích** với Spring Boot và bytecode ứng dụng. Ví dụ bên dưới dùng Java 17.
2. **Spring Boot executable JAR/WAR** đã được Maven repackage hoặc Gradle bootJar/bootWar đúng cách; không dùng plain JAR nhầm lẫn.
3. Metadata **layers.idx** phù hợp nếu muốn liệt kê/trích theo layers.
4. **spring-boot-jarmode-tools** hiện diện trong archive; đừng cấu hình **includeTools=false**.
5. **Không có embedded launch script prefix** của fully executable Spring Boot JAR: tài liệu chính thức nêu rõ tools mode **không dùng được** với archive kiểu này.
6. Quyền đọc JAR và quyền ghi vào **destination directory** khi extract.
7. Một **destination mới/trống** hoặc xử lý rõ ràng khi destination đã có files, tránh trộn outputs cũ và mới.

Hai cờ thường dễ nhầm:

~~~text
-Djarmode=tools  -> JVM system property, phải truyền TRƯỚC -jar
-jar app.jar     -> archive Spring Boot chứa Boot Loader và tools
list-layers      -> subcommand do tools mode hiểu
extract          -> subcommand do tools mode hiểu
--layers         -> chọn cách trích xuất thành các lớp
--destination    -> vị trí đặt files được trích
~~~

**Đúng:**

~~~bash
java -Djarmode=tools -jar app.jar list-layers
~~~

**Không tương đương:**

~~~bash
java -jar app.jar -Djarmode=tools list-layers
~~~

Ở lệnh thứ hai, **-Djarmode=tools** nằm sau tên archive, nên thường chỉ là argument đưa cho application; JVM không nhận nó làm system property ở thời điểm chọn JarMode. Ứng dụng có thể khởi động thay vì in danh sách lớp. Luôn đặt **-Djarmode=tools** trước **-jar**.

## 5. Xem trợ giúp trực tiếp từ artifact

Sau khi build thành công, lệnh đơn giản nhất để biết JAR hỗ trợ những subcommands nào:

~~~bash
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar
~~~

Trong Spring Boot 3.5, phần usage thường có dạng:

~~~text
Usage:
  java -Djarmode=tools -jar my-app.jar

Available commands:
  extract      Extract the contents from the jar
  list-layers  List layers from the jar that can be extracted
  help         Help about any command
~~~

Tên JAR in trong usage có thể là artifact của bạn hoặc một tên mô tả; **không kiểm tra nguyên văn từng byte của dòng usage** để quyết định công cụ có hoạt động. Ba subcommand **extract**, **list-layers** và **help** mới là phần cần xác nhận.

Xem hướng dẫn của lệnh extract:

~~~bash
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar help extract
~~~

Một số tùy chọn được Spring Boot tools hỗ trợ:

| Option | Ý nghĩa |
| --- | --- |
| **--layers** | Trích nội dung theo các layer thay vì chỉ tạo layout bình thường; có thể chỉ định lớp cần trích theo cú pháp của phiên bản tools |
| **--destination** | Thư mục đích để đặt nội dung; nếu không chỉ định, mặc định dựa vào tên archive |
| **--libraries** | Tên thư mục libs khi dùng layout không trích launcher; mặc định **lib/** |
| **--application-filename** | Tên application JAR trong layout phù hợp |
| **--launcher** | Yêu cầu trích Spring Boot launcher theo chế độ hỗ trợ |
| **--force** | Cho phép trích vào vị trí không rỗng theo semantics của tools |

**Không gộp tất cả options rồi dùng một cách tùy ý.** Một số tùy chọn chỉ có tác dụng khi không bật **--launcher**. Cú pháp selection layer hoặc giá trị mặc định có thể thay đổi giữa phiên bản Boot, do đó **help extract của artifact thật** là nguồn tra cứu nhanh nhất.

Đặc biệt, **--force** không phải cách “sửa” directory bẩn trong CI: tốt hơn nên tạo output directory mới cho mỗi build để không giữ stale libraries hoặc file của artifact trước.

## 6. Liệt kê các lớp bằng list-layers

### 6.1. Lệnh với Maven JAR

Trong project dùng Spring Boot Maven Plugin:

~~~bash
./mvnw clean verify
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar list-layers
~~~

Trong ví dụ Spring Boot layered JAR dùng bốn lớp mặc định, kết quả thường có dạng:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

Đây là **output dự kiến theo định nghĩa mặc định**, không phải bản ghi của một lượt chạy thực tế đã được thực hiện trong bài viết. Nếu dự án có **layers.xml** custom, tên/thứ tự có thể khác. Hãy đọc output trực tiếp thay vì hardcode giả định vào pipeline khi tổ chức thay layer configuration.

### 6.2. Lệnh với Gradle JAR

Nếu project dùng Gradle và output mặc định của bootJar:

~~~bash
./gradlew clean test bootJar
java -Djarmode=tools -jar build/libs/layer-lab-1.0.0.jar list-layers
~~~

Chỉ chọn **một build tool**. Đừng chạy lệnh Maven rồi tìm artifact trong build/libs, hoặc chạy Gradle rồi tìm file trong target. Tên file có thể đổi theo classifier, archiveBaseName hoặc custom bootJar/repackage configuration.

### 6.3. list-layers không phải list-jar-entries

**list-layers** hiển thị **tên lớp**, không in mọi file thuộc mỗi lớp. Muốn xem entries của executable JAR nguyên gốc, có thể dùng:

~~~bash
jar tf target/layer-lab-1.0.0.jar
~~~

Ví dụ lọc trên Linux/macOS:

~~~bash
jar tf target/layer-lab-1.0.0.jar | grep 'BOOT-INF/layers.idx'
jar tf target/layer-lab-1.0.0.jar | grep 'spring-boot-jarmode-tools'
~~~

Trên PowerShell:

~~~powershell
jar tf .\target\layer-lab-1.0.0.jar |
    Select-String 'BOOT-INF/layers.idx|spring-boot-jarmode-tools'
~~~

**jar tf** chỉ liệt kê archive entries, trong khi **list-layers** đọc layer metadata. Hai thao tác bổ sung cho nhau, không thay thế nhau.

## 7. Trích xuất theo layer bằng extract --layers

Với Maven artifact trong ví dụ:

~~~bash
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar extract --layers --destination extracted
~~~

Ý nghĩa:
- **java** khởi động Boot Loader/JarMode Tools.
- **-Djarmode=tools** chọn tools mode.
- **extract** thực hiện trích archive.
- **--layers** tạo các thư mục nhóm theo layers thay vì chỉ một layout gộp.
- **--destination extracted** đặt output dưới thư mục **extracted** theo working directory hiện tại.

Đây là lệnh có trong ví dụ Dockerfile chính thức Spring Boot 3.5. **Không cần gọi unzip rồi tự phân loại các JAR**. Spring Boot tools sử dụng layer index để xác định thành phần của từng lớp.

### 7.1. Cấu trúc đầu ra khái niệm

Sau khi trích thành công, có thể thấy:

~~~text
extracted/
├── dependencies/
│   └── ... nội dung thuộc dependencies ...
├── spring-boot-loader/
│   └── ... nội dung thuộc spring-boot-loader ...
├── snapshot-dependencies/
│   └── ... nội dung thuộc snapshot-dependencies ...
└── application/
    └── ... nội dung thuộc application ...
~~~

**Đây là sơ đồ nhóm thư mục**, không phải danh sách tệp đầy đủ. Các nested dependencies khi trích thường được bố trí dưới **lib/** trong layout runtime hiệu quả; phần ứng dụng được đóng thành một **application.jar** nhỏ cùng manifest tham chiếu libraries. Nội dung chính xác từng folder còn phụ thuộc Spring Boot version, custom layers, artifact JAR/WAR và options.

Một nguyên tắc quan trọng: **không chạy java -jar extracted/application/application.jar ngay rồi kỳ vọng nó thấy mọi libraries**. Trong hướng dẫn container, bốn thư mục lớp được **COPY hợp nhất vào cùng một runtime working directory**, lúc đó các files ở **lib/** và **application.jar** mới có đường dẫn/classpath phù hợp.

### 7.2. Dùng lệnh quan sát sau khi trích

Linux/macOS:

~~~bash
find extracted -maxdepth 2 -type d
find extracted -type f | head -n 30
~~~

Nếu bạn đã cài **tree**, có thể:

~~~bash
tree -L 3 extracted
~~~

Các lệnh chỉ hiển thị cấu trúc, không chạy application. Trong CI, tốt hơn kiểm tra danh sách lớp và file chính yếu, không phụ thuộc số lượng tên JAR cố định vì dependency versions thay đổi.

Windows PowerShell:

~~~powershell
Get-ChildItem .\extracted -Directory
Get-ChildItem .\extracted -Recurse -File |
    Select-Object -First 30 FullName
~~~

Khi chạy nhiều lần, nên dùng **destination khác cho mỗi bản build** hoặc dọn đúng output directory do quy trình tạo ra; tránh trộn hai version thư viện rồi kết luận artifact hiện tại có file không thuộc nó.

### 7.3. --destination có bắt buộc không?

Không. **extract** có thư mục mặc định dựa theo tên JAR. Tuy nhiên, dùng một tên rõ ràng như **extracted** giúp script và Dockerfile dễ đọc và kiểm soát hơn.

**Không dùng một absolute destination ngẫu nhiên trong máy production** khi chưa kiểm tra owner/permissions. Quá trình trích ghi files lên filesystem; nên làm ở build stage hoặc một thư mục riêng được cấp quyền phù hợp.

## 8. extract không có --layers khác điều gì?

Đây là điểm dễ nhầm nhất trong jarmode tools hiện đại.

**Chế độ A — extract mặc định**:

~~~bash
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar extract
~~~

Theo tài liệu Spring Boot 3.5, tools tạo một **layout triển khai hiệu quả**: libraries được đưa ra thư mục **lib/**, đồng thời có một application JAR nhỏ chứa application classes và manifest tham chiếu tới libraries. Destination mặc định thường mang tên archive không có phần mở rộng, ví dụ:

~~~text
layer-lab-1.0.0/
├── lib/
│   ├── ... dependencies ...
│   └── ...
└── layer-lab-1.0.0.jar
~~~

Hình trên chỉ mô tả bố trí đại diện. Để khởi động layout theo hướng dẫn:

~~~bash
java -jar layer-lab-1.0.0/layer-lab-1.0.0.jar
~~~

**Chế độ B — extract --layers**:

~~~bash
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar extract --layers --destination extracted
~~~

Tools chia cùng các thành phần thành những thư mục **dependencies**, **spring-boot-loader**, **snapshot-dependencies**, **application** để có thể **COPY từng thư mục** vào OCI image. Kết quả sau khi kết hợp cần chứa runtime layout đúng (libraries và application JAR).

| Tiêu chí | **extract** | **extract --layers** |
| --- | --- | --- |
| Mục tiêu chính | Chạy từ exploded/efficient layout | Tách các thành phần theo lớp để Docker/OCI cache |
| Cấu trúc output | Một thư mục ứng dụng với lib/ và JAR nhỏ | Nhiều folder ứng với layer names |
| Cần gộp folders trước khi chạy? | Không, nếu layout đủ và path đúng | Có trong ví dụ Dockerfile chính thức |
| Có tạo Docker image ngay? | Không | Không |
| Có chạy SpringApplication.main()? | Không | Không |
| Công cụ phù hợp để xem options | help extract | help extract |

**Đừng đánh đồng jarmode=tools với jarmode=layertools cũ.** Cả hai đều liên quan layered archives nhưng options, output layout và cách khởi động có thay đổi qua các phiên bản.

## 9. Vì sao cách trích xuất mới tạo application.jar nhỏ?

Spring Boot 3.5 khuyến nghị layout triển khai mà nested libraries đã được trích thành files bên ngoài để giảm một phần overhead của việc đọc JAR-in-JAR khi startup. **extract** tạo application JAR nhỏ cùng metadata/classpath phù hợp để dùng những files trong **lib/**.

Khi làm theo Dockerfile chính thức, sau khi COPY hợp nhất từng layer:

~~~text
/application/
├── application.jar   (JAR chứa ứng dụng và manifest tham chiếu lib)
├── lib/
│   └── nhiều runtime dependency JAR files
└── ... file hỗ trợ theo layout ...
~~~

Tập files chính xác phụ thuộc build và Spring Boot plugin. Lệnh khởi động cho **layout được trích này** thường là:

~~~bash
java -jar application.jar
~~~

**Không coi application.jar sau khi trích là cùng binary với uber JAR ban đầu.** Uber JAR chứa tất cả nested dependencies; JAR mới chạy từ layout đã trích dẫn tới libraries nằm ngoài. Nếu chỉ copy mỗi application.jar mà không copy lib/ và những thành phần bắt buộc, có thể gặp **ClassNotFoundException/NoClassDefFoundError**.

Theo tài liệu Spring Boot 3.5, exploded layout có thể giúp startup hiệu quả hơn và thuận lợi cho **CDS/AOT cache**, nhưng **không nên cam kết** một số phần trăm tăng tốc cố định. Sau khi startup thành công, không nên kỳ vọng tốc độ xử lý request runtime tự động khác biệt chỉ vì trích JAR.

## 10. Ví dụ chạy được: Spring Boot 3.5 + Java 17

Để thao tác thật với **list-layers** và **extract --layers**, tạo một Spring Boot HTTP service đơn giản. Ví dụ dùng **Java 17**, **Spring Boot 3.5.16** và JUnit 5. Đây là tổ hợp cụ thể phục vụ bài học; dự án mới cần chọn nhánh Spring Boot còn nhận hỗ trợ theo chính sách tổ chức.

**Dùng Maven hoặc Gradle**, không phải hai tool cùng quản lý một artifact rồi nhầm outputs.

### 10.1. Cấu trúc project

~~~text
layer-lab/
├── pom.xml                         (nếu dùng Maven)
│   hoặc
├── build.gradle                    (nếu dùng Gradle)
├── settings.gradle                 (nếu dùng Gradle)
├── mvnw / mvnw.cmd / .mvn/wrapper/...       (Maven Wrapper)
├── gradlew / gradlew.bat / gradle/wrapper/... (Gradle Wrapper)
└── src/
    ├── main/
    │   ├── java/com/example/layerlab/
    │   │   ├── LayerLabApplication.java
    │   │   └── LayerController.java
    │   └── resources/application.properties
    └── test/java/com/example/layerlab/
        └── LayerControllerTest.java
~~~

Wrapper scripts/metadata phải được tạo bằng Spring Initializr hoặc công cụ Wrapper tương ứng. Nếu chỉ tạo POM hoặc build.gradle, **./mvnw** và **./gradlew** không tự xuất hiện.

### 10.2. Main class

Tệp **src/main/java/com/example/layerlab/LayerLabApplication.java**:

~~~java
package com.example.layerlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LayerLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(LayerLabApplication.class, args);
    }
}
~~~

**Jarmode tools** sử dụng Boot Loader trước khi gọi class trên; khi chạy **list-layers/extract**, **LayerLabApplication.main() không được gọi**. Điều này giúp việc trích xuất không cần kết nối database hay khởi động HTTP server.

### 10.3. Endpoint kiểm chứng runtime

Tệp **src/main/java/com/example/layerlab/LayerController.java**:

~~~java
package com.example.layerlab;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LayerController {

    @GetMapping("/layers")
    public String layers() {
        return "layer-extract-ok";
    }
}
~~~

Khi ứng dụng Spring Boot thực sự đang phục vụ HTTP, request **GET /layers** sẽ trả body:

~~~text
layer-extract-ok
~~~

Không suy luận endpoint đã chạy chỉ từ việc **list-layers** thành công; tools mode không tạo web server.

### 10.4. application.properties

Tệp **src/main/resources/application.properties**:

~~~properties
spring.application.name=layer-lab
server.port=8080
~~~

Nếu cổng 8080 bị chiếm, chạy Java với **--server.port=9090** và đổi URL kiểm tra tương ứng. Đây là Spring application option, không phải option của **tools extract**.

### 10.5. Test HTTP bằng MockMvc

Tệp **src/test/java/com/example/layerlab/LayerControllerTest.java**:

~~~java
package com.example.layerlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LayerControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void layersEndpointWorks() throws Exception {
        mvc.perform(get("/layers"))
                .andExpect(status().isOk())
                .andExpect(content().string("layer-extract-ok"));
    }
}
~~~

Test xác nhận code ứng dụng và Spring context hoạt động. **Nó không xác nhận extraction layout đúng** vì Maven/Gradle tests chạy trên build classpath. Bạn vẫn cần chạy artifact sau khi extract và gọi endpoint thật.

## 11. Build bằng Maven: layers và jarmode tools

### 11.1. pom.xml đầy đủ

Tệp **pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>layer-lab</artifactId>
    <version>1.0.0</version>

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
                        <enabled>true</enabled>
                    </layers>
                    <includeTools>true</includeTools>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Giải thích:
- **spring-boot-starter-parent** chuẩn bị Maven plugin/dependency versions và cấu hình **repackage**.
- **spring-boot-maven-plugin** tạo executable JAR có Boot Loader.
- **layers.enabled=true** bảo đảm layer index được tạo trong ví dụ, dù Spring Boot 3.5 đã bật layering mặc định.
- **includeTools=true** giữ **spring-boot-jarmode-tools** trong archive. Với Boot 3.5, đây cũng là mặc định.
- **spring-boot-starter-web** đưa Spring MVC + embedded server và runtime dependencies vào archive.
- **starter-test** chỉ phục vụ tests, không cần đưa test classes vào production Boot JAR.

**Không thêm executable=true** vào Maven plugin trong ví dụ này. Fully executable archive có embedded launch script **không tương thích tools mode** theo tài liệu Spring Boot 3.5.

Nếu project có corporate Maven parent thay vì starter-parent, cần xác nhận goal **spring-boot:repackage** được bind vào lifecycle, plugin version hợp lệ và application main class được tìm thấy. **Chỉ khai báo includeTools=true mà không chạy repackage sẽ không biến plain JAR thành Boot JAR.**

### 11.2. Build và liệt kê lớp

Linux/macOS:

~~~bash
./mvnw --version
./mvnw clean verify
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar list-layers
~~~

Windows dùng **mvnw.cmd** thay cho **./mvnw**. Khi Maven clean verify thành công, plugin repackage tạo archive ở **target/** theo artifact/version trong POM. Nếu POM có classifier, customized finalName hoặc outputDirectory, dùng đường dẫn thật.

Sau list-layers, trích:

~~~bash
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar extract --layers --destination extracted
~~~

Thư mục **extracted** là output của lần trích; không phải thư mục Maven build mặc định. Với CI nên đặt nó trong một workspace riêng để tránh rác từ build cũ.

### 11.3. Maven repackage so với plain Jar Plugin

Với Maven, task tạo plain JAR có thể chạy trước **spring-boot:repackage**. Nếu bạn dùng một **classifier** để giữ đồng thời plain JAR và executable JAR, phải trích **đúng Boot executable artifact**. Plain JAR không có Boot Loader, không có BOOT-INF/layers.idx và không chứa jarmode tools theo định dạng Boot.

Các lỗi thường gặp khi chọn sai:
- **no main manifest attribute** hoặc **Could not find or load main class**.
- Không có **BOOT-INF/layers.idx** khi dùng **jar tf**.
- Không có **spring-boot-jarmode-tools** trong archive.
- Java chạy application thay vì tools hoặc báo không hỗ trợ jar mode.

Không sửa bằng cách copy một thư viện tools ngẫu nhiên vào plain JAR; cần **build lại đúng format** với Spring Boot Maven Plugin.

## 12. Build bằng Gradle: bootJar và layered archive

Nếu chọn Gradle, dùng cùng mã nguồn Java nhưng không dùng POM ở trên.

### 12.1. settings.gradle

~~~groovy
rootProject.name = 'layer-lab'
~~~

### 12.2. build.gradle Groovy DSL

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    layered {
        enabled = true
    }
    includeTools = true
}
~~~

**bootJar** tạo executable Spring Boot archive. **layered.enabled=true** và **includeTools=true** được viết tường minh để minh họa; với Spring Boot Gradle Plugin 3.5, hành vi mặc định đã có layering và jar tools.

**io.spring.dependency-management** nhập bộ Spring Boot dependency versions để dependencies không cần version tường minh. Nếu project chọn native Gradle BOM support, phải khai báo **platform(...)** tương ứng, không đơn giản xóa plugin rồi nghĩ dependencies tự có version.

### 12.3. Thao tác Gradle

Với Gradle Wrapper tương thích (chẳng hạn Gradle 8.14 cho Spring Boot 3.5):

~~~bash
./gradlew --version
./gradlew clean test bootJar
java -Djarmode=tools -jar build/libs/layer-lab-1.0.0.jar list-layers
java -Djarmode=tools -jar build/libs/layer-lab-1.0.0.jar extract --layers --destination extracted
~~~

Trên Windows dùng **gradlew.bat**. **Gradle jar task** có thể tạo plain JAR, còn **bootJar** tạo Boot executable JAR. Chọn đúng output, không nhầm JAR có classifier **plain** với output của bootJar.

### 12.4. Kotlin DSL tương ứng với phần layered config

Trong **build.gradle.kts** đã có Spring Boot Plugin, có thể thêm:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    layered {
        enabled.set(true)
    }
    includeTools.set(true)
}
~~~

Đây là **đoạn trích config**, không phải toàn bộ file build.gradle.kts; những phần plugins/dependencies/toolchain phải viết theo cú pháp Kotlin DSL tương ứng.

Không gắn tùy chọn **includeTools** vào block **layered** theo cú pháp Gradle 2.x cũ như **includeLayerTools**. Trong Boot 3.5, BootArchive task có property **includeTools** riêng.

## 13. Dockerfile multi-stage: mỗi Spring Boot layer thành một image layer

Với một artifact Maven **target/layer-lab-1.0.0.jar** đã build và test thành công, tạo **Dockerfile** ở project root:

~~~dockerfile
# Stage 1: chi de trich cac layer; khong can Maven trong image
FROM eclipse-temurin:17-jre AS extractor
WORKDIR /builder

COPY target/layer-lab-1.0.0.jar application.jar
RUN java -Djarmode=tools -jar application.jar extract --layers --destination extracted

# Stage 2: runtime image chua output da trich
FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=extractor /builder/extracted/dependencies/ ./
COPY --from=extractor /builder/extracted/spring-boot-loader/ ./
COPY --from=extractor /builder/extracted/snapshot-dependencies/ ./
COPY --from=extractor /builder/extracted/application/ ./

USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

Đây là một **Dockerfile runnable với artifact Maven đúng tên**, giả sử đã có Docker engine và image base tương thích. Thay **COPY target/...** bằng **COPY build/libs/layer-lab-1.0.0.jar application.jar** nếu đã build bằng Gradle. Khi thực tế deploy, nên pin image tag/digest theo chính sách supply-chain security và chọn JDK runtime chính xác.

### 13.1. Tại sao lại có hai FROM?

- **extractor stage** copy **uber JAR**, chạy jarmode tools, tạo folders theo lớp.
- **runtime stage** chỉ copy kết quả trích và Java runtime, **không cần chứa original uber JAR như một file riêng**.
- Mỗi câu lệnh **COPY** trong runtime stage hình thành một image filesystem layer để Docker/OCI builder có thể cache và tái sử dụng.

Ở thời điểm runtime, command:

~~~bash
java -jar application.jar
~~~

khởi động **JAR nhỏ được tạo từ extraction**, không phải original uber JAR nằm ở stage extractor. Các dependencies nằm trên filesystem trong layout runtime tương ứng. Đây là điểm khác so với Dockerfile một dòng **COPY app.jar + java -jar /app/app.jar**.

### 13.2. Tại sao COPY theo thứ tự đó?

~~~text
dependencies            (ổn định, copy trước)
spring-boot-loader      (thay đổi khi nâng framework/plugin)
snapshot-dependencies   (có thể đổi thường xuyên)
application             (thay đổi khi sửa source, copy sau)
~~~

Nếu chỉ sửa endpoint Java, lớp application thường đổi nhưng các lớp dependencies ổn định có thể được tái sử dụng. Nếu nâng Spring Boot version hoặc thay một dependency, lớp dependency và có thể các lớp sau phải xây lại. Mức tiết kiệm phụ thuộc Docker cache và image registry thực tế.

### 13.3. Build image và chạy

Sau khi Maven build thành công:

~~~bash
docker build -t layer-lab:local .
docker run --rm -p 8080:8080 layer-lab:local
~~~

Từ terminal thứ hai:

~~~bash
curl http://localhost:8080/layers
~~~

Response body dự kiến:

~~~text
layer-extract-ok
~~~

Nếu máy host đã chiếm cổng 8080, dùng Docker port mapping khác, ví dụ **-p 9090:8080**, rồi gọi **http://localhost:9090/layers**.

**Không được coi docker build thành công là bằng chứng Spring Boot application đã chạy và phục vụ request.** Bước **docker run + curl** xác minh layout sau extraction có đủ libraries, manifest và permissions.

### 13.4. Tại sao không đặt tools mode làm ENTRYPOINT?

~~~dockerfile
ENTRYPOINT ["java", "-Djarmode=tools", "-jar", "application.jar"]
~~~

Đây **không** phải entrypoint của một web service: tools mode chỉ chạy thao tác công cụ, không gọi SpringApplication.main. Ở runtime, sau khi đã trích/gộp các lớp, dùng **java -jar application.jar** như Dockerfile phía trên.

### 13.5. Lưu ý với .dockerignore

Khi làm Docker build trong repository có **target/** hoặc **build/libs/**, không được viết một **.dockerignore** vô tình loại đúng JAR mà Dockerfile cần **COPY**. Nếu dùng mặc định bỏ **target/** khỏi build context, bạn sẽ gặp lỗi **COPY failed** hoặc artifact không tìm thấy.

Đồng thời tránh đưa vào context các file nhạy cảm như **.env**, private keys, credentials, local build caches, logs và temp directories. Chỉ include những artifacts/phần source cần thiết. Quản lý Docker build context là một phần của độ ổn định và bảo mật pipeline.

## 14. Kiểm tra output sau khi Docker hợp nhất layers

Sau khi COPY, layout hiệu quả thông thường có:

~~~text
/application/
├── application.jar
├── lib/
│   ├── ... Spring + third-party libraries ...
│   └── ...
└── ... layout metadata/phu tro, neu co ...
~~~

Để kiểm tra container đã có file application JAR và thư viện, có thể chạy một shell image nếu image có shell:

~~~bash
docker run --rm --entrypoint sh layer-lab:local -c 'ls -la /application; ls /application/lib | head'
~~~

Lệnh chỉ dùng để **kiểm tra file layout**. Nếu base image là **distroless** không có shell, lệnh sh sẽ không chạy; dùng debug image/build inspection theo quy trình phù hợp. Đừng thêm shell vào runtime image production chỉ để debug nếu policy security không cho phép.

**Lưu ý quan trọng:** layout sau trích có **application.jar nhỏ và lib/**, không phải **BOOT-INF/lib** của uber JAR ban đầu. Bài kiểm tra chính phải là **java -jar application.jar** kèm Spring app smoke test, không phải đòi runtime layout giống nguyên bản nội dung ZIP.

## 15. list-layers và layers.idx: kiểm tra từ metadata

Layer index trong Spring Boot executable JAR thường nằm tại:

~~~text
BOOT-INF/layers.idx
~~~

Ví dụ các entry dạng YAML-like:

~~~yaml
- "dependencies":
  - "BOOT-INF/lib/spring-core-..."
  - "BOOT-INF/lib/spring-context-..."
- "spring-boot-loader":
  - "org/springframework/boot/loader/"
- "snapshot-dependencies":
  - "BOOT-INF/lib/some-snapshot-..."
- "application":
  - "BOOT-INF/classes/"
~~~

Đây là **cú pháp mô tả mang tính minh họa**, không phải một layers.idx nguyên văn để dán vào archive. File thật do plugin tạo có entries/đường dẫn tương ứng với dependencies resolved của project.

**list-layers** là cách chính thức để hỏi archive có những layer names nào. **layers.idx** giải thích mapping file-to-layer. Khi muốn điều tra custom layer config, đọc cả hai. Không tự sửa layers.idx sau khi build trong ZIP rồi mong Spring Boot tools và Docker caching luôn tương thích; thay cấu hình Maven/Gradle và rebuild.

### 15.1. Có phải layers.idx làm Java class loading nhanh hơn?

Không trực tiếp. Spring Boot Loader chịu trách nhiệm class loading/nested-JAR access của executable archive. **layers.idx** chủ yếu phục vụ phân nhóm triển khai và cách tool tách archive để tối ưu image distribution/cache. Khi chạy nguyên uber JAR bằng **java -jar**, việc archive có layer metadata không tự đồng nghĩa runtime request nhanh hơn.

### 15.2. classpath.idx không phải layers.idx

**BOOT-INF/classpath.idx** (nếu có) ghi thứ tự dependencies trên classpath khi chạy executable archive theo cách được Boot hỗ trợ. **BOOT-INF/layers.idx** ghi file thuộc layer nào để hỗ trợ tách deployment. Chúng khác mục đích và không thay thế nhau.

## 16. Jarmode tools và layertools cũ: vì sao ví dụ Internet khác nhau?

Trên Internet có thể gặp lệnh cũ:

~~~bash
java -Djarmode=layertools -jar app.jar list
java -Djarmode=layertools -jar app.jar extract
~~~

Đó là **cơ chế cũ** dùng **spring-boot-jarmode-layertools**. Từ Spring Boot 3.3, **spring-boot-jarmode-tools** và **jarmode=tools** là hướng thay thế. Tài liệu Spring Boot 3.5 sử dụng:

~~~bash
java -Djarmode=tools -jar app.jar list-layers
java -Djarmode=tools -jar app.jar extract --layers --destination extracted
~~~

Sự khác nhau có ý nghĩa:

| Hành vi | Hướng cũ layertools | Hướng mới tools (Boot 3.5) |
| --- | --- | --- |
| JarMode property | **layertools** | **tools** |
| Lệnh liệt kê | **list** ở một số version cũ | **list-layers** |
| Trích các lớp | **extract** theo layout cũ | **extract --layers** theo layout mới |
| Trích layout hiệu quả không chia folder layers | Không đồng nhất với tools hiện đại | **extract** |
| JAR công cụ | **spring-boot-jarmode-layertools** | **spring-boot-jarmode-tools** |

**Không trộn CLI của hai hệ**. Nếu copy Dockerfile Boot 2.x/3.2 vào ứng dụng Boot 3.5, kết quả có thể khác về thư mục và cách khởi động. Với Boot 4.x, những cơ chế đã deprecated có thể bị loại; dùng tài liệu và lệnh **help** đúng nhánh Boot mà project thật đang build.

Không cần học cú pháp cũ để thực hiện bài; bảng chỉ giúp chẩn đoán những lệnh đã sao chép từ blog cũ.

## 17. Khi dự án dùng fully executable archive có launch script

Spring Boot còn có lựa chọn Maven:

~~~xml
<configuration>
    <executable>true</executable>
</configuration>
~~~

hoặc Gradle:

~~~groovy
tasks.named('bootJar') {
    launchScript()
}
~~~

Hai lựa chọn này chèn **Unix launch script prefix** vào đầu archive để chạy trực tiếp trên OS phù hợp (**./app.jar**). **Spring Boot 3.5 Dockerfiles documentation nói rõ jarmode=tools không dùng được với fully executable archive có script prefix.**

Nếu bạn cần **extract --layers**:
- Với Maven, **không bật executable=true** cho artifact dùng bởi extractor.
- Với Gradle, **không gọi launchScript()** trên BootJar dùng để extract.
- Nếu tổ chức cần cả hai, tạo **hai artifacts khác nhau**, đặt tên/classifier rõ ràng, kiểm thử riêng.
- Đừng tự bỏ shebang/ZIP prefix bằng thao tác binary không được kiểm soát rồi dùng file đó như bản release.

**Không nhầm fully executable với Spring Boot executable JAR chuẩn.** Boot JAR có Main-Class/Start-Class và chạy **java -jar** không mặc nhiên có embedded shell prefix; trường hợp chuẩn này chính là đầu vào phù hợp cho tools mode.

## 18. includeTools=false và layers.enabled=false không giống nhau

Với Spring Boot Maven Plugin 3.5, có hai cách tắt các chức năng khác nhau:

**A — Tắt jar tools, vẫn có thể giữ layer metadata:**

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <includeTools>false</includeTools>
    </configuration>
</plugin>
~~~

**B — Tắt layered archive metadata:**

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <layers>
            <enabled>false</enabled>
        </layers>
    </configuration>
</plugin>
~~~

Các đoạn chỉ là **plugin excerpts**, không phải pom.xml đầy đủ. Với Spring Boot **3.3+**, tắt layers không phải cách đáng tin để tự loại tools JAR — **includeTools** là cấu hình trực tiếp để kiểm soát việc có tools dependency.

Trong Gradle, ý nghĩa tương tự:

~~~groovy
tasks.named('bootJar') {
    includeTools = false
}
~~~

và:

~~~groovy
tasks.named('bootJar') {
    layered {
        enabled = false
    }
}
~~~

**Nếu muốn dùng list-layers/extract --layers, không được bật các cấu hình vô hiệu hóa trên.** Bảng kết quả tổng quát:

| Cấu hình | Archive có layer metadata? | Jarmode tools có được đóng kèm? | Có thể dùng list-layers/extract --layers? |
| --- | --- | --- | --- |
| Default Boot 3.5 | Có | Có | **Có** |
| includeTools=false | Có thể có | Không | **Không dùng tools mode từ archive đó** |
| layers.enabled=false, tools vẫn có | Không | Có thể vẫn có | Không có layers để liệt kê/trích theo layer |
| Có cả metadata và tools nhưng fully executable prefix | Có | Có | **Không hỗ trợ jarmode tools với prefix** |

**Không vội sửa code** khi lệnh tools fail. Trước tiên xem POM/Gradle config, manifest, file JAR được chọn và versions; đôi khi bạn đang chạy plain JAR hoặc artifact cũ.

## 19. Tuỳ chỉnh lớp và hệ quả đối với list-layers

Trong Spring Boot Maven Plugin, có thể dùng file **layers.xml** để đổi quy tắc nhóm dependencies/application files, thêm lớp **company-dependencies**, hoặc thay **layerOrder**. Gradle BootJar cũng hỗ trợ cấu hình layer rules. Điều này hữu ích khi thư viện nội bộ của tổ chức thay đổi thường xuyên hơn third-party libraries.

Ví dụ logic:

~~~text
dependencies           -> thư viện bên thứ ba ổn định
spring-boot-loader     -> boot loader
company-dependencies  -> thư viện nội bộ com.example
snapshot-dependencies -> bản SNAPSHOT
application            -> source/resources ứng dụng
~~~

Đây là **ví dụ tên layer tùy chỉnh**, không tự có trong cấu hình mặc định. Sau khi build archive với cấu hình đó:

~~~bash
java -Djarmode=tools -jar target/layer-lab-1.0.0.jar list-layers
~~~

sẽ cho những lớp được định nghĩa thực tế. Nếu Dockerfile chỉ **COPY** bốn tên mặc định mà archive có thêm **company-dependencies**, layer mới không được đưa vào runtime image, có thể gây thiếu classes.

**Nguyên tắc an toàn:** khi đổi custom layer rules, cập nhật Dockerfile hoặc pipeline theo danh sách lớp thật; chạy smoke test của extracted artifact. Không tự động hardcode một bốn-lớp giả định cho tất cả team repositories.

Đối với CI có nhiều Spring Boot applications khác nhau, nên chuẩn hóa layer policy hoặc sinh các COPY commands trong quy trình build được kiểm tra. Tuy nhiên, bất kỳ cơ chế sinh Dockerfile cũng phải bảo đảm không thiếu layer và bảo vệ build context/inputs.

## 20. Windows PowerShell: liệt kê và trích xuất

**Java jarmode tools là Java code**, không phải Unix shell script, nên có thể chạy trên Windows khi artifact là **standard Spring Boot executable JAR**, có Java runtime tương thích.

Tại project dùng Maven:

~~~powershell
& .\mvnw.cmd clean verify
java -Djarmode=tools -jar .\target\layer-lab-1.0.0.jar list-layers
java -Djarmode=tools -jar .\target\layer-lab-1.0.0.jar help extract
java -Djarmode=tools -jar .\target\layer-lab-1.0.0.jar extract --layers --destination extracted
~~~

Nếu dùng Gradle:

~~~powershell
& .\gradlew.bat clean test bootJar
java -Djarmode=tools -jar .\build\libs\layer-lab-1.0.0.jar list-layers
java -Djarmode=tools -jar .\build\libs\layer-lab-1.0.0.jar extract --layers --destination extracted
~~~

Đây là **hai lựa chọn build**, không cần thực hiện cả hai. Sau khi trích:

~~~powershell
Get-ChildItem .\extracted -Directory
Get-ChildItem .\extracted -Recurse -File |
    Select-Object -First 20 FullName
~~~

Cần chú ý thư mục hiện tại, đường dẫn có khoảng trắng và quyền ghi. Trong PowerShell, **-Djarmode=tools** được truyền như argument cho Java khi đặt đúng trước **-jar**; không dùng prefix **MODE=...** của shell Linux để thay nó.

## 21. Những vấn đề thực tế khi kiểm tra kết quả trích

### 21.1. Thư mục layers rỗng có phải lỗi không?

Không nhất thiết. Nếu project không có dependency version SNAPSHOT, lớp **snapshot-dependencies** có thể ít hoặc không có nội dung. Hãy xác định lớp đó có được list-layers in ra hay không, rồi kiểm tra những lớp còn lại có đủ các thư viện cần thiết không.

### 21.2. Tại sao thấy JAR trong BOOT-INF/lib nhưng không thấy trong dependencies layer?

Một module thuộc local reactor/project có thể được phân loại vào **application** thay vì **dependencies**. Một dependency SNAPSHOT sẽ thuộc **snapshot-dependencies**. Với custom layers, rule riêng có thể chuyển thành phần vào layer mới. Đừng kết luận file “mất” chỉ vì không nằm trong thư mục dự đoán.

### 21.3. Vì sao application.jar mới bé hơn uber JAR?

Vì các runtime JAR dependencies nằm trong **lib/** bên ngoài application JAR. **Không xóa lib/** sau extract và không ship mỗi application.jar riêng lẻ trừ khi bạn đã thay đổi classpath/packaging phù hợp.

### 21.4. Có phải extract là lệnh build lại Java classes?

Không. **extract** làm việc trên artifact đã build. Nó không gọi **javac**, Maven compiler, annotation processors hay JUnit. Nếu ứng dụng source có lỗi hoặc tests fail, lỗi cần được xử lý ở build phase trước. Không dùng extract để lách verification của pipeline.

### 21.5. Có thể trích mọi thứ vào /tmp rồi copy lên server không?

Có thể trích vào directory bạn kiểm soát, nhưng phải bảo vệ:
- quyền đọc/ghi của CI user;
- disk space và filesystem quotas;
- content của artifact đến từ nguồn tin cậy;
- cleanup và owner/permissions;
- không trộn output của các release khác nhau.

Không giải nén archive không đáng tin vào một thư mục chia sẻ có quyền cao. Khi triển khai production, dùng môi trường staging/build stage và artifact integrity checks.

## 22. Bảng chẩn đoán lỗi jarmode tools

| Hiện tượng | Nguyên nhân thường gặp | Hướng điều tra |
| --- | --- | --- |
| **UnsupportedClassVersionError** | Java runtime cũ hơn class files/Spring Boot | Kiểm tra java -version và project target JDK |
| Không có **list-layers** trong help | Dùng Boot/layertools version cũ hoặc artifact không đúng | Kiểm tra plugin version và jarmode help |
| **Unknown jarmode 'tools'** | Tools dependency vắng hoặc archive không hỗ trợ | Kiểm tra includeTools, jar tf và artifact thật |
| **no main manifest attribute** | Plain JAR, chưa repackage/bootJar | Kiểm tra Maven goal, Gradle bootJar, manifest |
| **java -jar** chạy app thay vì list-layers | Đặt -Djarmode=tools sau -jar hoặc gõ nhầm | Chuyển -Djarmode=tools lên trước -jar |
| Không thấy **BOOT-INF/layers.idx** | Layering bị tắt hoặc là plain JAR | Xem layers.enabled và output đúng |
| Có layers.idx nhưng list-layers không chạy | Tools bị exclude, sai version hoặc có fully executable prefix | Kiểm tra includeTools, script và logs |
| JAR có shell prefix **#!** | Fully executable archive không tương thích tools mode | Build standard executable Boot JAR không launchScript |
| extract báo destination không rỗng | Thư mục có output cũ | Dùng destination mới, chỉ dùng --force có kiểm soát |
| **Permission denied** khi extract | Không có quyền ghi nơi đích | Chọn writable directory, xem filesystem permissions |
| **No space left on device** | Trích nhiều dependencies/JARs, disk quota hết | Tăng dung lượng staging, dọn output đúng scope |
| **NoClassDefFoundError** khi chạy extracted JAR | Chưa copy đủ lib/layer hoặc path không đúng | Xem bốn COPY lines và runtime layout |
| Docker **COPY failed** | Artifact không có ở context hoặc .dockerignore loại target | Kiểm tra build context, COPY source path |
| Container khởi động rồi exit | App crash hoặc ENTRYPOINT vẫn là tools mode | Xem docker logs, ENTRYPOINT Java runtime |
| Docker image không cache dependencies | Lớp stable đổi bytes, ordering thay hoặc build cache bị vô hiệu | Inspect layer changes, registry/buildkit settings |
| Có custom **company-dependencies** nhưng Dockerfile thiếu | Dockerfile hardcode bốn layer defaults | Dùng list-layers thật, COPY mọi layer |
| Jar tools không chạy trên Windows | Nhầm dùng script Unix hoặc Java/path không đúng | Dùng java -Djarmode=tools trên standard JAR |
| Test pass nhưng container fail | Tests dùng build classpath, extracted runtime thiếu libs/config | Docker smoke test, dependency resolution |
| Layers list trống ngoài mong đợi | Không có hợp lệ layers index hoặc plugin config sai | jar tf, effective POM, Boot plugin version |

Lỗi trong bước **extract** khác với lỗi Spring ApplicationContext: khi tools mode đang chạy, SpringApplication.main **chưa được gọi**. Nếu container đã mở endpoint nhưng request fail do DB/auth/bean, classpath có thể đã ổn, cần chẩn đoán ở tầng ứng dụng.

## 23. Quy trình kiểm tra trước khi phát hành image

Một pipeline nên xác nhận:

1. **Build và tests PASS** trên cùng source commit và toolchain đã chốt.
2. Đầu ra thực sự là **Spring Boot executable JAR** có **layers.idx**, không phải plain JAR.
3. Archive có **spring-boot-jarmode-tools** và không có fully executable shell prefix.
4. **list-layers** trả về tập layer names dự kiến theo policy.
5. **extract --layers --destination** thành công trong một thư mục mới.
6. Các folder của layers có nội dung tương ứng và khi gộp thành runtime layout có **application.jar** cùng dependencies cần thiết.
7. Dockerfile **COPY đúng mọi layer theo thứ tự**, không thiếu custom layer.
8. Runtime image dùng **java -jar application.jar**; không dùng tools mode cho service.
9. Container chạy được bằng non-root user, có Java phù hợp và quyền filesystem cần thiết.
10. Smoke test HTTP/job trên image thật PASS.
11. Image scan, SBOM/provenance, dependency vulnerability checks và test requirements vẫn được thực hiện.
12. Theo dõi thời gian push/pull/image-size/registry cache qua các release, không tự tuyên bố lợi ích chỉ bằng số layer.

### 23.1. Bảng QA kết quả mong đợi

| Phép kiểm tra | Dấu hiệu PASS |
| --- | --- |
| Maven/Gradle build | Exit 0, tests đúng phạm vi đã PASS |
| list-layers | In tên các layer có trong archive, ví dụ bốn tên mặc định |
| extract --layers | Exit 0, destination có các folder theo layer |
| Runtime layout | application.jar + lib/ và những resources cần thiết |
| Docker build | Image được tạo thành công với đủ các COPY |
| Docker run | Java process startup, không thiếu classes |
| HTTP request | GET /layers trả body **layer-extract-ok** |
| Tối ưu caching | So sánh image layer digests và metrics trước/sau có bằng chứng |

**Không lấy một test PASS thay cho mọi kiểm tra khác.** Unit test chạy trong Gradle/Maven chưa chứng minh Dockerfile đã copy đủ layers; list-layers chạy thành công chưa chứng minh application có thể sử dụng database hoặc HTTP server khi deploy.

## 24. Câu hỏi tự đánh giá có đáp án

**Câu 1.** Vì sao không chỉ copy nguyên app.jar vào Docker image?

**Đáp án:** Có thể copy nguyên JAR, nhưng một thay đổi nhỏ trong app code làm byte của uber JAR đổi, dẫn tới Docker layer chứa JAR phải được cập nhật. Chia application/dependencies thành các nhóm riêng giúp cache và truyền lớp ổn định hiệu quả hơn.

**Câu 2.** list-layers có giải nén JAR ra disk không?

**Đáp án:** Không. Nó liệt kê layer names từ metadata. Lệnh **extract** mới tạo files trên filesystem.

**Câu 3.** Vì sao **-Djarmode=tools** phải đứng trước **-jar**?

**Đáp án:** Vì nó là **JVM system property**. Nếu đặt sau archive filename, Java launcher sẽ truyền nó như application argument, không thiết lập JarMode đúng thời điểm.

**Câu 4.** Bốn lớp mặc định là gì?

**Đáp án:** **dependencies**, **spring-boot-loader**, **snapshot-dependencies**, **application**, theo thứ tự đó.

**Câu 5.** **extract** và **extract --layers** có tạo cùng thư mục không?

**Đáp án:** Không. extract thông thường tạo layout gọn gồm application.jar và thư viện lib; extract --layers chia các thành phần thành thư mục theo layer để COPY riêng trong Dockerfile.

**Câu 6.** Sau extract --layers, chỉ copy extracted/application/ có đủ để chạy không?

**Đáp án:** Thường **không**. Phải gộp cả dependencies, loader, SNAPSHOT dependencies và application theo layer policy để có layout runtime hoàn chỉnh.

**Câu 7.** Nếu Maven có **includeTools=false**, nhưng layers.idx vẫn tồn tại, tools mode có chắc chạy không?

**Đáp án:** Không. includeTools=false loại jar tools dependency; layer index riêng lẻ không cung cấp CLI list-layers/extract.

**Câu 8.** Có dùng tools mode với fully executable Spring Boot JAR có launch script không?

**Đáp án:** Không theo hướng dẫn Spring Boot 3.5. Hãy build bản standard Boot executable JAR không có launch-script prefix.

**Câu 9.** Tại sao Dockerfile phải COPY lần lượt bốn lớp?

**Đáp án:** Để ghép đủ runtime files và giữ cache boundaries độc lập. Thứ tự từ ổn định đến thay đổi nhiều giúp tối ưu tái sử dụng image layers.

**Câu 10.** Dùng list-layers khi đã custom layers.xml có gì cần lưu ý?

**Đáp án:** Output có thể có tên lớp và thứ tự khác mặc định. Dockerfile hoặc pipeline phải dùng đúng lớp thật, tránh thiếu dependencies.

**Câu 11.** Chạy **java -Djarmode=tools -jar app.jar extract** có chạy tests không?

**Đáp án:** Không. Nó đọc artifact đã build để trích files; tests thuộc Maven/Gradle verification phases và phải chạy riêng.

**Câu 12.** Dockerfile sau trích chạy lệnh gì để khởi động Spring app?

**Đáp án:** **java -jar application.jar** theo layout được Spring Boot tools tạo. Nó không chạy original uber JAR từ extractor stage và không cần **-Djarmode=tools** lúc runtime.

## 25. Kết luận

Để liệt kê và trích xuất lớp của Spring Boot 3.5 executable JAR, ghi nhớ chuỗi thao tác:

~~~text
Maven spring-boot:repackage / Gradle bootJar
             |
             v
Spring Boot layered JAR có BOOT-INF/layers.idx
             |
             v
java -Djarmode=tools -jar app.jar list-layers
             |
             v
java -Djarmode=tools -jar app.jar extract --layers --destination extracted
             |
             v
extracted/dependencies/
extracted/spring-boot-loader/
extracted/snapshot-dependencies/
extracted/application/
             |
             v
Dockerfile COPY từng layer vào /application
             |
             v
java -jar application.jar
             |
             v
SpringApplication.run(...) + HTTP request
~~~

**Nhớ ba điều kiện:** archive phải là **Boot executable JAR**, có tools dependency, và **không có fully executable launch script prefix**. **list-layers** chỉ báo các lớp; **extract --layers** tạo output folders; **Dockerfile** mới biến những folders đó thành image layers. Thực hiện đủ build/test/extract/run/smoke-test mới xác nhận artifact phân lớp dùng được trong triển khai.

## 26. Tài liệu tham khảo chính thức

- Spring Boot 3.5.16 — Dockerfiles: jarmode tools, list-layers, extract --layers và Docker multi-stage: https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/dockerfiles.html
- Spring Boot 3.5 — Efficient Deployments: extract mặc định và layout có application JAR + lib: https://docs.spring.io/spring-boot/3.5/reference/packaging/efficient.html
- Spring Boot 3.5.16 — Maven Plugin, Packaging Executable Archives: layered JAR/WAR, layers.idx, includeTools: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Gradle Plugin, Packaging Executable Archives: bootJar, layered archive, includeTools: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html
- Spring Boot 3.5 — Executable JAR Format: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/index.html
- Spring Boot 3.5 — Nested JARs: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html
- Spring Boot 3.5 — Maven Plugin Using: https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html
- Spring Boot 3.5 — Gradle Plugin Getting Started: https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html
- Docker — Multi-stage builds: https://docs.docker.com/build/building/multi-stage/
- Docker — Build cache: https://docs.docker.com/build/cache/
