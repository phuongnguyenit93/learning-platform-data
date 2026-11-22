# Tài nguyên web, cấu hình WAR và kiểm tra sản phẩm bàn giao trong Maven và Spring Boot

## 1. Mục tiêu và phạm vi

Khi xây dựng ứng dụng Java phục vụ HTTP trên servlet container, **WAR (Web Application Archive)** là một định dạng bàn giao phổ biến. Khác JAR thư viện thông thường, WAR có quy ước riêng cho **web root**, **classpath của ứng dụng**, **thư viện trong WEB-INF/lib** và **deployment descriptors**. Maven WAR Plugin tạo cấu trúc đó; Spring Boot Maven Plugin có thể tiếp tục **repackage** thành một WAR vừa triển khai trong servlet container tương thích, vừa chạy độc lập với `java -jar`.

Một thay đổi tưởng nhỏ như đặt file HTML vào `src/main/resources` thay vì `src/main/webapp` có thể làm thay đổi vị trí của file trong WAR. Một file xuất hiện trong `target/classes` không chứng minh file cuối cùng đã có đúng path; một build `BUILD SUCCESS` cũng chưa chứng minh WAR chạy được trên container đích.

Sau bài học, người đọc có thể:

1. Hiểu `<packaging>war</packaging>`, phase `package` và goal `war:war`.
2. Tách đúng **web assets**, **application classpath resources**, **test fixtures** và dữ liệu cấu hình runtime.
3. Dùng `src/main/webapp`, `src/main/resources`, `webResources`, `targetPath`, `includes` và `excludes` đúng mục đích.
4. Cấu hình Maven WAR Plugin, xử lý `web.xml` hoặc khởi tạo Servlet bằng Java/Spring Boot.
5. Phân biệt **WAR truyền thống** với **Spring Boot executable WAR**, classpath `WEB-INF/lib` và `WEB-INF/lib-provided`.
6. Đọc và kiểm tra artifact cuối bằng `jar tf`, `java.util.zip.ZipFile`, test và HTTP smoke test.
7. Khoanh vùng lỗi deployment, resource 404, context path, xung đột servlet API, thiếu dependencies và file bí mật lọt vào WAR.
8. Xây dựng một dự án Java 17 + Spring Boot 3.3.5 có unit/integration-style MockMvc tests và một chương trình kiểm tra WAR sau package.

**Điểm chốt:** bàn giao WAR phải được đánh giá từ **file `.war` cuối cùng và môi trường triển khai thật**, không chỉ từ source tree hoặc trạng thái IDE.

## 2. WAR, JAR, plugin và lifecycle khác nhau thế nào?

| Khái niệm | Ví dụ | Tác dụng |
| --- | --- | --- |
| Project packaging | `war` | Chọn main artifact WAR và default lifecycle bindings |
| Maven build phase | `package` | Mốc đóng gói trong default lifecycle |
| Plugin | `org.apache.maven.plugins:maven-war-plugin:3.4.0` | Tạo nội dung và file WAR |
| Plugin goal | `war:war` | Đóng gói WAR từ project hiện tại |
| Main artifact | `demo:war-delivery-lab:1.0.0`, extension `war` | Artifact chính để install/deploy |
| Web root | `src/main/webapp` | Tài nguyên nằm gần gốc WAR hoặc dưới WEB-INF |
| Classpath resource | `src/main/resources` | Resource đi qua `target/classes` tới `WEB-INF/classes` |
| Dependency | `spring-webmvc`, `jakarta.servlet-api`, Tomcat... | Được đặt vào WAR tùy Maven scope và repackaging |
| Spring Boot repackage | `spring-boot:repackage` | Tạo executable WAR với Boot loader và layout tương ứng |

Một project Maven bình thường có thể có:

```xml
<modelVersion>4.0.0</modelVersion>
<groupId>demo</groupId>
<artifactId>war-delivery-lab</artifactId>
<version>1.0.0</version>
<packaging>war</packaging>
```

Theo default lifecycle, `war:war` được gắn ở phase `package`. Với `finalName` mặc định, Maven có thể sinh:

```text
target/war-delivery-lab-1.0.0.war
```

Khác với file `.jar`, project `war` được thiết kế theo layout **Servlet web application**. Nó không mặc nhiên cần phương thức `main` nếu chỉ triển khai vào một servlet container bên ngoài.

### 2.1. Các lệnh Maven cần phân biệt

```bash
mvn -B test
mvn -B package
mvn -B clean verify
mvn org.apache.maven.plugins:maven-war-plugin:3.4.0:war
```

- `mvn test` chạy compile và test theo lifecycle, thường **chưa** đóng gói WAR.
- `mvn package` chạy các phase trước và tạo WAR.
- `mvn clean verify` xóa output cũ, đi qua packaging và các phase tiếp theo; phù hợp để kiểm chứng build sạch.
- Gọi **goal `war:war` trực tiếp** không tự chạy mọi phase của default lifecycle. Nếu class, resource hoặc generated output còn thiếu, file WAR có thể sai hoặc build fail.

**Không thay thế clean verify bằng lời gọi trực tiếp goal `war:war`** trong quy trình QA. Một archive có thể tồn tại dù pipeline test chưa chạy đúng.

## 3. Cấu trúc chuẩn của WAR truyền thống

Một WAR có thể được hình dung như sau:

```text
war-delivery-lab-1.0.0.war
├── META-INF/
│   └── MANIFEST.MF
├── pages/
│   └── about.html
├── meta/
│   └── release.txt
└── WEB-INF/
    ├── classes/
    │   ├── demo/war/WarLabApplication.class
    │   ├── demo/war/GreetingController.class
    │   ├── application.properties
    │   └── static/assets/site.css
    ├── lib/
    │   └── <cac-thu-vien-runtime>.jar
    ├── lib-provided/          (khi Spring Boot repackage executable WAR)
    │   └── <thu-vien-container-provided>.jar
    └── private-note.txt
```

Đây là **sơ đồ có chọn lọc**, không phải danh sách đầy đủ mọi entry của plugin/framework. WAR thật có thể có thêm Boot loader, Maven metadata, resource/class khác và những directory entries của ZIP.

Các vùng quan trọng:

- **Web root**: `pages/about.html`, images, CSS, JS ở gốc webapp. Servlet container có thể phục vụ tài nguyên phù hợp theo các quy tắc bảo vệ/servlet mapping của nó.
- **`WEB-INF`**: vùng nội bộ của ứng dụng web. Servlet container chuẩn không trực tiếp phục vụ file ở đây như một static URL công khai.
- **`WEB-INF/classes`**: class sản phẩm và application resources. Đây là một classpath root khi ứng dụng triển khai theo mô hình WAR.
- **`WEB-INF/lib`**: các JAR cần ở runtime theo scope/packaging, được container đưa vào application classloader.
- **`WEB-INF/lib-provided`**: vùng do Spring Boot executable WAR sử dụng cho dependencies cung cấp bởi container bên ngoài khi deploy; Boot loader có thể sử dụng chúng khi chạy `java -jar`.
- **`META-INF/MANIFEST.MF`**: metadata, không đồng nghĩa toàn bộ nội dung deployment.

**Không được coi `WEB-INF` là kho bí mật an toàn tuyệt đối.** Nó bị ngăn truy cập HTTP trực tiếp theo tiêu chuẩn container, nhưng bất kỳ ai nhận được WAR vẫn có thể giải nén archive và đọc file. Secrets cần secret manager/config runtime, không nhúng vào WAR.

## 4. Bốn nhóm tài nguyên cần tách

| Nhóm | Đường dẫn input phổ biến | Đường dẫn trong WAR | Ý nghĩa |
| --- | --- | --- | --- |
| Web-root assets | `src/main/webapp/pages/about.html` | `pages/about.html` | Nội dung thuộc webapp root |
| App classpath resources | `src/main/resources/static/assets/site.css` | `WEB-INF/classes/static/assets/site.css` | Spring Boot static resource handler phục vụ HTTP khi cấu hình mặc định phù hợp |
| Java bytecode | `src/main/java/demo/war/...java` | `WEB-INF/classes/demo/war/...class` | Code servlet/controller của ứng dụng |
| Test-only files | `src/test/resources/fixtures/test-only.txt` | Thường **không có** trong WAR | Chỉ có trên test classpath |
| Extra webResources | `src/main/war-assets/release.txt` | Ví dụ `meta/release.txt` | Thêm resource từ directory riêng bằng WAR Plugin |
| External runtime secrets | Environment variable / secret mount / config service | **Không đóng gói** | Dữ liệu chỉ cấp khi deploy/runtime |

Sự khác biệt giữa hai thư mục quan trọng nhất:

### 4.1. src/main/webapp là web root

Maven WAR Plugin có parameter `warSourceDirectory`, mặc định là `${basedir}/src/main/webapp`. Nội dung trong đó được đưa vào webapp root theo cấu hình.

Ví dụ:

```text
src/main/webapp/
├── pages/about.html
└── WEB-INF/private-note.txt
```

Khi `war:war` chạy, file thường tương ứng với entries:

```text
pages/about.html
WEB-INF/private-note.txt
```

`pages/about.html` là asset ở web root. `WEB-INF/private-note.txt` thuộc nội bộ container; tên "private" trong bài chỉ là minh họa vị trí, **không lưu thông tin nhạy cảm thật** trong đó.

### 4.2. src/main/resources là Java classpath resources

Với Maven Resources Plugin, `src/main/resources` thường được copy vào `target/classes` ở phase `process-resources`. WAR Plugin đặt những file này dưới `WEB-INF/classes`:

```text
src/main/resources/static/assets/site.css
     ↓ resources:resources
target/classes/static/assets/site.css
     ↓ war:war
WEB-INF/classes/static/assets/site.css
```

Trong Spring Boot MVC, thư mục classpath `/static` nằm trong nhóm static resource locations mặc định. Với cấu hình thích hợp, HTTP path `/assets/site.css` được map tới resource `/static/assets/site.css`. **Không nhầm đường dẫn HTTP với đường dẫn vật lý bên trong WAR**.

Một ứng dụng thuần Servlet không tự nhận toàn bộ quy tắc static resource của Spring Boot; Servlet container và servlet mappings quyết định cách resource được phục vụ.

### 4.3. src/test/resources không phải web asset phát hành

Các file `src/test/resources` đi vào `target/test-classes`, phục vụ unit/integration tests, và **không được thêm vào main WAR mặc định**. Nếu test fixture xuất hiện trong WAR, cần kiểm tra build/resource roots hoặc cấu hình WAR Plugin có copy quá rộng không.

Một phép thử JUnit đọc được fixture **không chứng minh** fixture đã bị/không bị đóng gói; phải kiểm tra archive `.war` sau phase `package`.

## 5. Maven WAR Plugin: cấu hình nào ảnh hưởng nội dung?

Các parameter của `maven-war-plugin:3.4.0:war` đáng chú ý:

| Parameter | Tác dụng và rủi ro |
| --- | --- |
| `warSourceDirectory` | Web root input, mặc định `src/main/webapp` |
| `warSourceIncludes` / `warSourceExcludes` | Chọn file trong web root; có thể vô tình bỏ asset |
| `webResources` | Thêm resource từ directory khác, có `filtering`, `targetPath`, include/exclude |
| `webXml` | Chỉ định deployment descriptor khi dự án cần |
| `failOnMissingWebXml` | Cách xử lý khi không có web.xml; dự án Servlet hiện đại có thể không cần |
| `packagingIncludes` / `packagingExcludes` | Lọc entries trước khi package; sai pattern có thể loại `WEB-INF/lib` |
| `webappDirectory` | Thư mục staging WAR exploded, thường `target/<finalName>` |
| `outputDirectory` | Thư mục chứa file WAR, thường `target` |
| `primaryArtifact` | Có xem output này là artifact chính không; mặc định true |
| `classifier` | Tạo WAR attached khi đặt classifier, thay vì main WAR |
| `overlays` | Gộp nội dung từ WAR dependencies, phải quản lý collisions |
| `resourceEncoding` / `propertiesEncoding` | Encoding cho filtered resources |
| `delimiters` / `useDefaultDelimiters` | Quy tắc placeholder interpolation |
| `outputTimestamp` | Hỗ trợ archive entry timestamp ổn định |

**Không tự suy ra mọi parameter đều có user property CLI `-D` cùng tên.** Tra trang goal của đúng version. Đặc biệt, `packagingExcludes` là một bộ lọc cuối trên archive, **không phải lý do để bỏ kiểm thử asset**.

### 5.1. Thư mục staging và WAR file là hai đầu ra khác nhau

Khi Maven WAR Plugin chạy, nó có thể tạo:

```text
target/war-delivery-lab-1.0.0/
target/war-delivery-lab-1.0.0.war
```

Thư mục thứ nhất là **exploded/staging webapp directory**; file thứ hai là **artifact bàn giao**. Một file có trong staging nhưng bị exclude khi đóng gói có thể không nằm trong `.war`. QA cuối phải kiểm tra **ZIP entries bên trong WAR**, không chỉ xem staging directory.

Nếu Spring Boot Maven Plugin chạy `repackage` sau WAR Plugin, file `.war` có thể được viết lại với Boot loader và nested dependencies. Khi đó phải kiểm tra **WAR cuối sau repackage**, không chỉ bản archive tạm trước đó.

## 6. Có cần WEB-INF/web.xml không?

Trong các ứng dụng Servlet cũ, `WEB-INF/web.xml` khai báo servlet, filters, listeners, mappings, startup và những metadata triển khai khác. Ví dụ khái niệm:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         version="6.0">
    <!-- Có thể khai báo servlet/filter nếu ứng dụng cần -->
</web-app>
```

Đây chỉ là **mẫu cấu trúc để nhận biết descriptor**, không phải cấu hình ứng dụng runnable trong bài. Một `web.xml` thật phải tuân schema Jakarta EE/Servlet version cụ thể của container.

Với Servlet 3.0+ và Spring Boot theo hướng annotation/`SpringBootServletInitializer`, project thường **không cần** file `web.xml`. Maven WAR Plugin 3.4.0 có `failOnMissingWebXml`; theo tài liệu, từ 3.1.0 default có thể là false nếu project có dependency Servlet 3.0 API hoặc mới hơn. Để tránh phụ thuộc suy đoán, ví dụ trong bài đặt tường minh:

```xml
<failOnMissingWebXml>false</failOnMissingWebXml>
```

**Không vì thiếu web.xml mà tự thêm một file rỗng để "sửa" Spring Boot WAR.** Hãy xác định ứng dụng dùng ServletInitializer/annotation hay descriptor truyền thống. Ngược lại, nếu một hệ thống legacy phụ thuộc web.xml, không thể chỉ đổi flag để ứng dụng hoạt động mà bỏ cấu hình bắt buộc.

## 7. Cấu hình thêm tài nguyên web bằng webResources

Mặc định `src/main/webapp` đã được WAR Plugin nhận diện. Nhưng có thể cần đưa file từ directory khác vào WAR, ví dụ build metadata công khai hoặc các asset đã được pipeline tạo từ trước.

Ví dụ POM:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-war-plugin</artifactId>
    <version>3.4.0</version>
    <configuration>
        <webResources>
            <resource>
                <directory>${project.basedir}/src/main/war-assets</directory>
                <targetPath>meta</targetPath>
                <filtering>true</filtering>
                <includes>
                    <include>release.txt</include>
                </includes>
            </resource>
        </webResources>
        <delimiters>
            <delimiter>@</delimiter>
        </delimiters>
        <useDefaultDelimiters>false</useDefaultDelimiters>
        <resourceEncoding>UTF-8</resourceEncoding>
    </configuration>
</plugin>
```

Đây là **đoạn plugin**; khi cần thêm vào POM thật, phải hợp nhất với cấu hình WAR Plugin đang có, không khai báo hai plugin khác version vô tình ghi đè nhau.

Nếu file `src/main/war-assets/release.txt` chứa:

```text
build.version=@project.version@
```

và version project là `1.0.0`, đầu ra mong đợi trong WAR:

```text
meta/release.txt
```

với nội dung:

```text
build.version=1.0.0
```

`targetPath` chỉ vị trí file trong WAR **tương đối với web root**, không tạo một main Java source root. `<filtering>true</filtering>` yêu cầu thay token, còn việc giới hạn `includes` giúp tránh filter nhầm ảnh hay JAR nhị phân.

### 7.1. Filtering và dữ liệu nhạy cảm

Filtering là phép thay **giá trị build-time** vào file. Nó phù hợp cho version/name không nhạy cảm nhưng có rủi ro:

- Giá trị environment-specific khiến WAR từ cùng commit có byte khác nhau.
- Một token của JavaScript/template/framework bị thay ngoài ý muốn.
- File binary bị hỏng khi lọc như text.
- Secrets được ghi thẳng vào artifact hoặc CI log.

Chỉ filter **những file text được chỉ định**; giữ các assets khác không filtering. Với file JSON/YAML phức tạp, phải parse/validate output, không chỉ thấy token đã được thay. Với token runtime như `${DB_PASSWORD}` hay `${SPRING_PROFILES_ACTIVE}`, đừng để Maven filtering thay và nhúng secret trong WAR. Dùng runtime configuration từ môi trường triển khai.

### 7.2. Binary assets cần bảo toàn byte

WAR có thể chứa PNG, JPEG, font, PDF, ZIP và nhiều loại file binary. Nếu hệ thống cần bảo đảm byte còn nguyên vẹn, hãy để chúng đi qua **copy không filtering** và so SHA-256 trước/sau khi trích xuất từ WAR.

Maven WAR Plugin hỗ trợ `nonFilteredFileExtensions` khi dùng webResources filtering; tuy nhiên việc tách hẳn filtered text ra directory/`includes` riêng thường dễ review hơn. Đừng coi phần mở rộng filename là bằng chứng file hợp lệ; công cụ nên kiểm tra nội dung thật.

### 7.3. Excludes có thể loại bỏ các file quan trọng

Đoạn cấu hình:

```xml
<packagingExcludes>**/*.bak,**/.DS_Store</packagingExcludes>
```

được dùng trong ví dụ runnable để loại backup/editor noise khỏi archive. Nhưng cần đặc biệt thận trọng khi viết pattern rộng hơn, ví dụ loại nhầm `WEB-INF/lib/**`, `WEB-INF/classes/**`, service descriptors hoặc JSP dependency. WAR vẫn có thể tạo ra nhưng không chạy được.

## 8. WAR truyền thống so với Spring Boot WAR

| Đặc điểm | WAR truyền thống | Spring Boot executable WAR |
| --- | --- | --- |
| Maven packaging | `war` | `war` |
| Bước chính | `maven-war-plugin:war` | WAR Plugin, sau đó Boot `repackage` |
| Cần container bên ngoài? | Thường có | Có thể deploy ngoài **hoặc** chạy embedded |
| Khởi chạy `java -jar` | Không mặc định | Có khi Boot plugin đóng gói executable WAR |
| Entry trong manifest | Không bắt buộc có Java Main-Class | Boot launcher `WarLauncher` và `Start-Class` |
| Class sản phẩm | `WEB-INF/classes` | `WEB-INF/classes` |
| Libraries thông thường | `WEB-INF/lib` | `WEB-INF/lib` |
| Dependencies provided | Không đóng gói vào runtime libs của WAR truyền thống | Boot repackage có thể đặt ở `WEB-INF/lib-provided` |
| Khởi tạo web app | web.xml/Servlet initializer/annotations | `SpringBootServletInitializer` khi deploy ngoài |
| Static files | Servlet container/config framework quyết định | Boot MVC tự cấu hình static locations như `classpath:/static/` |
| Tính tương thích | Phụ thuộc Servlet spec và container | Phụ thuộc thêm Boot/Spring/Jakarta namespace versions |

**Không phải mọi Spring Boot application đều nên dùng WAR.** Nhiều dịch vụ Spring Boot được phát hành dưới dạng executable JAR. WAR đặc biệt có ý nghĩa khi phải triển khai vào một servlet container bên ngoài, cần tương thích một môi trường WAR legacy, hoặc có yêu cầu phân phối riêng.

### 8.1. Spring Boot WAR cần SpringBootServletInitializer

Với Spring Boot MVC, một class ứng dụng có thể mở rộng `SpringBootServletInitializer` và override `configure(SpringApplicationBuilder)`. Khi servlet container truyền thống khởi tạo WAR, đường này giúp xây dựng Spring ApplicationContext.

Phương thức `public static void main` vẫn cần cho kiểu chạy độc lập với Boot launcher. Dự án ví dụ ở phần 12 thực hiện **cả hai**.

### 8.2. Phạm vi provided của embedded Tomcat

Khi WAR được deploy vào Tomcat bên ngoài, servlet container cung cấp Tomcat/Servlet engine. Nếu ứng dụng cũng đưa engine khác version vào `WEB-INF/lib`, có thể xảy ra xung đột classloader hoặc API.

Theo hướng dẫn Spring Boot, với Maven có thể khai báo `spring-boot-starter-tomcat` ở scope `provided`. Với executable WAR được Boot plugin repackage, các dependency provided cần thiết khi tự chạy có thể được đặt ở `WEB-INF/lib-provided`. Boot `WarLauncher` biết đọc chúng khi chạy `java -jar`; Tomcat bên ngoài không tự xem chúng là application libraries trong `WEB-INF/lib`.

Lưu ý scope dependency của Spring Boot cần được Maven Resolver quyết định theo effective POM. Đừng chỉ đoán từ dependency tree của riêng `spring-boot-starter-web` khi project có nhiều dependency trực tiếp/gián tiếp.

### 8.3. Cần chọn Servlet container/JDK phù hợp

Spring Boot 3.x dùng hệ sinh thái **Jakarta**; Tomcat 10.1 là một ví dụ servlet container phù hợp dòng Servlet 6.0. Tomcat 9 dùng các API `javax.servlet` cũ và **không phải** môi trường tương đương để triển khai WAR Spring Boot 3.x như ví dụ.

Cần kiểm tra:

- Java bytecode target release, JDK chạy Maven và JDK chạy servlet container.
- Servlet API/package namespace và phiên bản Tomcat/Jetty/Undertow được hỗ trợ.
- Cấu hình context path và reverse proxy của môi trường đích.
- Cách container cung cấp servlet engine và các JAR có scope provided.
- Hướng dẫn phát hành thực tế của Boot/container version, không chỉ coi “file có đuôi war” là tương thích.

**Spring WebFlux** không được hỗ trợ theo đường deploy WAR Servlet truyền thống trong hướng dẫn Spring Boot; không chuyển `packaging` của ứng dụng reactive Netty sang war rồi mặc định tương đương với Spring MVC.

## 9. Bảo mật của WEB-INF, META-INF và dữ liệu bàn giao

Các file trong `WEB-INF` thường không được servlet container phục vụ trực tiếp qua URL. Tuy nhiên:

1. **WAR có thể bị trích xuất bằng công cụ ZIP** nên dữ liệu trong đó không được xem là bí mật.
2. Java class/resource trên classpath có thể đọc file `WEB-INF/classes/...` nếu chương trình có quyền truy cập.
3. Một static asset ở web root có thể được phục vụ bởi container hoặc resource handler, tùy cấu hình.
4. Nếu cấu hình sai đã copy `secrets.properties` vào web root thay vì runtime config, hệ thống có nguy cơ rò rỉ.
5. Nếu file nằm trong WAR mà không dùng ở runtime, nó vẫn tăng bề mặt kiểm tra bảo mật và kích thước phân phối.

Không đóng gói password, private key, database dump, test fixture chứa dữ liệu thật hoặc file môi trường nội bộ vào WAR. Dùng secret manager, environment variables, mounted files hoặc config provider phù hợp.

**Một file `WEB-INF/private-note.txt` trong ví dụ chỉ chứa chữ demo**, không chứng minh nên lưu credential tại đó.

## 10. Build outputs cần kiểm chứng theo thứ tự

Đối với một project WAR:

```text
src/main/java                   → compile                → target/classes
src/main/resources              → process-resources     → target/classes
src/main/webapp                 → war:war               → root entries của WAR
src/main/war-assets             → war:webResources      → meta/... trong WAR
src/test/java                   → test-compile          → target/test-classes
src/test/resources              → process-test-resources → target/test-classes
target/classes                  → war:war               → WEB-INF/classes
Maven runtime dependencies      → war:war               → WEB-INF/lib
Spring Boot Maven Plugin        → repackage             → Boot loader + executable WAR layout
```

Đây là sơ đồ logic; danh sách plugin goals/phase và thứ tự execution thực tế phụ thuộc POM. Bài demo sẽ dùng Spring Boot starter parent, WAR Plugin và Boot Maven Plugin với repackage binding do parent cung cấp.

### 10.1. Không kiểm tra nhầm output tạm

- `target/classes`: chứng minh compiler/resources đã chạy.
- `target/test-classes`: chứng minh test source/resource đã được chuẩn bị.
- `target/<finalName>/`: WAR staging/exploded layout.
- `target/<finalName>.war`: **file bàn giao**.
- `target/surefire-reports`: bằng chứng unit test, không phải WAR content.
- `target/<finalName>.war.original` hoặc một bản dự phòng tương tự: có thể được Boot Plugin tạo khi repackage; không phải tự động là artifact bàn giao.
- `target/reports`: không phải nơi chứa WAR chính.

Trong CI, cần thu đúng WAR **sau tất cả các plugin post-processing**, tránh đưa nhầm bản WAR tiền repackage lên server.

## 11. Context path và URL khi deploy

Cùng một WAR có thể chạy theo hai cách:

1. **Chạy standalone** bằng `java -jar`: Boot dùng embedded container; với cấu hình mặc định thường lắng nghe ở port 8080 và context path root `/`.
2. **Deploy vào Tomcat bên ngoài**: WAR được đặt vào một context; Tomcat thường suy ra context path từ tên file WAR khi dùng auto-deployment, ví dụ `war-delivery-lab.war` → `/war-delivery-lab`, nhưng cấu hình host/context cụ thể có thể ghi đè.

Vì vậy endpoint controller `/api/hello` có thể được gọi bằng:

```text
http://localhost:8080/api/hello                    (standalone, root context)
http://localhost:8080/war-delivery-lab/api/hello    (external Tomcat, context path tương ứng)
```

Đây là **các URL ví dụ cho môi trường người học đã tự khởi động**, không phải dịch vụ thật đang hoạt động. Nếu deploy lên một context khác, phải thay prefix URL đúng với cấu hình container hoặc reverse proxy.

**Không cố giải quyết mọi lỗi 404 bằng việc copy thêm tài nguyên**. Trước tiên kiểm tra context path, dispatcher mappings, static resource handler, welcome file và URL thực tế mà HTTP client đang gọi.

## 12. Dự án thực hành hoàn chỉnh: Java 17 + Spring Boot WAR

Ví dụ này có:

- **Spring Boot MVC** với một REST endpoint `GET /api/hello`.
- File CSS ở **classpath static resources**.
- File HTML ở **web root** `src/main/webapp`.
- File resource nội bộ dưới `WEB-INF` (chỉ chứa nội dung minh họa).
- `webResources` lọc một file release metadata vào `meta/release.txt`.
- Fixture chỉ có trên **test classpath**.
- Bốn JUnit tests dùng Spring Boot MockMvc và classpath.
- `spring-boot-maven-plugin:repackage` để WAR vừa chạy `java -jar` vừa phù hợp external container khi môi trường tương thích.
- Một tool Java 17 đọc chính WAR cuối để kiểm chứng layout, file filtering, manifest và absence của test fixture.

### 12.1. Điều kiện và phiên bản

- **JDK 17+**; ví dụ biên dịch nhắm Java 17.
- Maven 3.6.3+ tương thích với các plugin được chọn.
- Spring Boot **3.3.5** và dependency versions được Spring Boot BOM quản lý.
- Maven WAR Plugin **3.4.0**, được khai báo tường minh.
- Có quyền truy cập Maven repository chứa dependencies/plugins, hoặc cache hợp lệ.
- Nếu muốn deploy external, sử dụng servlet container tương thích, ví dụ **Tomcat 10.1** với Java hỗ trợ.

Các phiên bản được chọn để bài thực hành ổn định, **không phải khẳng định mới nhất tại thời điểm đọc**. Với dự án sản xuất cần theo chính sách security/support và cập nhật các bản vá được phê duyệt.

### 12.2. Cây thư mục

```text
war-delivery-lab/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/demo/war/
│   │   │   ├── WarLabApplication.java
│   │   │   └── GreetingController.java
│   │   ├── resources/
│   │   │   ├── application.properties
│   │   │   └── static/assets/site.css
│   │   ├── webapp/
│   │   │   ├── pages/about.html
│   │   │   └── WEB-INF/private-note.txt
│   │   └── war-assets/
│   │       └── release.txt
│   └── test/
│       ├── java/demo/war/WarLabApplicationTests.java
│       └── resources/fixtures/test-only.txt
└── tools/
    └── InspectWar.java
```

`tools/InspectWar.java` nằm ngoài Maven Java source roots; nó là công cụ kiểm tra sau package bằng Java source-file mode. Không cần thêm nó vào main WAR.

### 12.3. pom.xml hoàn chỉnh

Tệp `war-delivery-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>demo</groupId>
    <artifactId>war-delivery-lab</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>
    <name>war-delivery-lab</name>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-war-plugin</artifactId>
                <version>3.4.0</version>
                <configuration>
                    <warSourceDirectory>${project.basedir}/src/main/webapp</warSourceDirectory>
                    <failOnMissingWebXml>false</failOnMissingWebXml>
                    <warSourceExcludes>**/*.bak,**/.DS_Store</warSourceExcludes>

                    <webResources>
                        <resource>
                            <directory>${project.basedir}/src/main/war-assets</directory>
                            <targetPath>meta</targetPath>
                            <filtering>true</filtering>
                            <includes>
                                <include>release.txt</include>
                            </includes>
                        </resource>
                    </webResources>

                    <delimiters>
                        <delimiter>@</delimiter>
                    </delimiters>
                    <useDefaultDelimiters>false</useDefaultDelimiters>
                    <resourceEncoding>UTF-8</resourceEncoding>
                    <propertiesEncoding>UTF-8</propertiesEncoding>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**Vì sao cấu hình này có thể chạy?**

1. `spring-boot-starter-parent:3.3.5` quản lý một tập dependency/plugin versions và cấu hình **`repackage`** cho Spring Boot Maven Plugin khi plugin được khai báo trong build.
2. `packaging=war` khiến Maven WAR Plugin tạo WAR ở phase `package`; Boot Plugin tiếp tục `repackage` vào executable WAR theo cấu hình parent.
3. `spring-boot-starter-web` cung cấp MVC và các thành phần ứng dụng web.
4. Khai báo trực tiếp `spring-boot-starter-tomcat` với scope `provided` là hướng dẫn của Spring Boot để tránh trùng container khi external deploy. Với Boot repackage, các dependency provided cần cho standalone run được đưa vào `WEB-INF/lib-provided`.
5. WAR Plugin dùng `webResources` để copy/filter đúng một file text. Những file `src/main/webapp` khác được copy theo war source.
6. Không có `web.xml`; Spring Boot application sẽ dùng `SpringBootServletInitializer` và cơ chế Servlet initializer.
7. Các `*.java` được compile vào `WEB-INF/classes`; `src/test` không được đóng vào main WAR.
8. `project.build.outputTimestamp` giúp ổn định archive entry timestamps; nó **không tự bảo đảm** WAR tái lập từng byte nếu những inputs khác vẫn thay đổi.

**Lưu ý:** vì dùng Spring Boot starter parent, POM mẫu **không tự khai báo thêm execution `spring-boot:repackage` lần hai**. Nếu dự án của bạn không dùng starter parent, phải cấu hình plugin execution phù hợp theo tài liệu Boot Maven Plugin; không sao chép mù cấu hình này sang POM có parent/BOM khác.

### 12.4. Lớp ứng dụng: WarLabApplication.java

Tệp `src/main/java/demo/war/WarLabApplication.java`:

```java
package demo.war;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarLabApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(WarLabApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WarLabApplication.class, args);
    }
}
```

Phương thức `configure` phục vụ startup khi WAR được triển khai trong external servlet container. Phương thức `main` phục vụ executable WAR chạy với Boot loader. Chúng phải cùng cấu hình application sources để tránh hai cách khởi động cho hành vi khác nhau.

Chúng ta dùng package `demo.war` làm package gốc, nên Spring Boot component scanning có thể nhận controller ở cùng package.

### 12.5. REST endpoint: GreetingController.java

Tệp `src/main/java/demo/war/GreetingController.java`:

```java
package demo.war;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping(value = "/api/hello",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return "WAR OK";
    }
}
```

Đây là REST endpoint rất nhỏ, không truy cập database/network bên ngoài. Với Spring MVC ứng dụng chạy tại root context, HTTP GET `/api/hello` trả response body chính xác:

```text
WAR OK
```

Dòng trên là **HTTP response body**, không phải toàn bộ console log khi khởi động Spring Boot. Header, status line và stack trace startup không được viết như một stdout cố định.

### 12.6. Application properties và static CSS trên classpath

Tệp `src/main/resources/application.properties`:

```properties
spring.application.name=war-delivery-lab
```

Không đặt `server.servlet.context-path` hay `server.port` trong bài để giữ giá trị mặc định khi chạy standalone. Khi external deploy, servlet container/context settings có quyền quyết định prefix URL.

Tệp `src/main/resources/static/assets/site.css`:

```css
body {
    color: navy;
}
```

Sau process-resources, CSS nằm ở `target/classes/static/assets/site.css`. Trong WAR, đường dẫn tương ứng là:

```text
WEB-INF/classes/static/assets/site.css
```

Với Spring Boot MVC static resource handler mặc định, HTTP path tương ứng khi chạy tại root context là:

```text
/assets/site.css
```

Đừng mở URL `/WEB-INF/classes/static/assets/site.css`: đó là **internal archive path**, không phải public HTTP URL.

### 12.7. Web-root page và internal WEB-INF resource

Tệp `src/main/webapp/pages/about.html`:

```html
<!doctype html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>WAR Delivery Lab</title>
</head>
<body>
    <h1>WAR Delivery Lab</h1>
    <p>Đây là trang HTML được đóng gói từ src/main/webapp.</p>
</body>
</html>
```

Sau WAR packaging, phải có entry:

```text
pages/about.html
```

Việc HTTP request `/pages/about.html` có được phục vụ hay không còn chịu ảnh hưởng Servlet container, DispatcherServlet mappings và resource handler, nhất là khi deploy ngoài. Bài thực hành **kiểm tra WAR entry này**, không mặc định coi một URL chưa test là thành công.

Tệp `src/main/webapp/WEB-INF/private-note.txt`:

```text
Internal demo resource, not a secret.
```

Đầu ra là `WEB-INF/private-note.txt`. Servlet container chuẩn không đưa file này ra public static URL, nhưng bất kỳ ai có file WAR đều có thể giải nén và đọc nó. Không thay nội dung demo bằng credential thật.

### 12.8. File được WAR Plugin filtering

Tệp `src/main/war-assets/release.txt`:

```text
build.version=@project.version@
```

WAR Plugin được cấu hình `webResources`, `filtering=true`, delimiter `@` và `targetPath=meta`. Vì POM khai báo `<version>1.0.0</version>`, file trong WAR phải là:

```text
meta/release.txt
```

với nội dung:

```text
build.version=1.0.0
```

Đây là ví dụ build metadata **không nhạy cảm**. Nếu dùng `@DB_PASSWORD@` trong cùng cơ chế, WAR có thể nhúng secret vào artifact, cần tránh.

### 12.9. Fixture dành riêng cho test

Tệp `src/test/resources/fixtures/test-only.txt`:

```text
fixture-only
```

Maven copy tới `target/test-classes/fixtures/test-only.txt` khi chạy test. Nó **không** được đưa vào main WAR mặc định. Bài test sẽ xác nhận fixture có trên test classpath, còn công cụ kiểm tra WAR sẽ xác nhận không có entry `fixtures/test-only.txt`.

### 12.10. Bốn bài kiểm thử bằng Spring Boot Test và MockMvc

Tệp `src/test/java/demo/war/WarLabApplicationTests.java`:

```java
package demo.war;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class WarLabApplicationTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void helloEndpointReturnsBody() throws Exception {
        mockMvc.perform(get("/api/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("WAR OK"));
    }

    @Test
    void classpathCssIsServedBySpringMvc() throws Exception {
        mockMvc.perform(get("/assets/site.css"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("color: navy;")));
    }

    @Test
    void cssExistsOnTestClasspath() throws IOException {
        try (InputStream stream = getClass().getResourceAsStream(
                "/static/assets/site.css")) {
            assertNotNull(stream);
            String css = new String(stream.readAllBytes(),
                                    StandardCharsets.UTF_8);
            assertTrue(css.contains("color: navy;"));
        }
    }

    @Test
    void testOnlyFixtureExistsForTests() throws IOException {
        try (InputStream stream = getClass().getResourceAsStream(
                "/fixtures/test-only.txt")) {
            assertNotNull(stream);
            String value = new String(stream.readAllBytes(),
                                      StandardCharsets.UTF_8).strip();
            assertEquals("fixture-only", value);
        }
    }
}
```

Giải thích:

- `@SpringBootTest` và `@AutoConfigureMockMvc` tạo Spring context và mô phỏng HTTP qua MockMvc **không cần khởi chạy một Tomcat thật trên cổng TCP**.
- Hai test đầu kiểm tra controller và static resource handler.
- Test thứ ba xác nhận CSS cũng hiện diện trên classpath, không chỉ có một HTTP mapping tình cờ trả nội dung khác.
- Test cuối chứng minh fixture chỉ phục vụ test classpath, **chưa chứng minh** fixture vắng trong WAR. Điều đó sẽ được kiểm tra ở `tools/InspectWar.java`.
- Cả bốn test dùng Java 17, JUnit Jupiter 5 và các thư viện test được `spring-boot-starter-test` quản lý.
- Test MockMvc **không** thay thế smoke test trên external Tomcat. Cần deployment smoke test riêng để xác nhận context path, container API, classloading và static resources thật.

## 13. Kiểm tra dự án sau mvn clean verify

Từ thư mục `war-delivery-lab/`:

```bash
mvn -version
mvn -B clean verify
```

Khi project, Maven repository và JDK phù hợp, thứ tự dự kiến:

1. Clean Plugin xóa `target` cũ.
2. Resources Plugin copy `application.properties` và `static/assets/site.css`.
3. Compiler Plugin biên dịch `WarLabApplication` và `GreetingController`.
4. Test resources và test compilation chuẩn bị fixture cùng test class.
5. Surefire chạy **4 tests**, dự kiến `0 failures, 0 errors, 0 skipped`.
6. WAR Plugin tạo `target/war-delivery-lab-1.0.0.war` theo layout Servlet WAR.
7. Spring Boot Maven Plugin repackage WAR, thêm Boot loader, nested dependencies và manifest cho executable WAR.
8. Maven đi tới phase `verify`, báo thành công nếu mọi goal bắt buộc đã hoàn tất.

Tệp bàn giao chính:

```text
target/war-delivery-lab-1.0.0.war
```

Báo cáo unit test thường ở:

```text
target/surefire-reports/
```

**Không suy ra 4 tests đã chạy chỉ từ exit code Maven** nếu POM đã bị người học sửa thành skip tests. Đọc các XML/TXT mới của Surefire.

### 13.1. Kiểm tra WAR entries với jar tf

Từ project root:

```bash
jar tf target/war-delivery-lab-1.0.0.war
```

Tìm các entries:

```text
META-INF/MANIFEST.MF
WEB-INF/classes/demo/war/WarLabApplication.class
WEB-INF/classes/demo/war/GreetingController.class
WEB-INF/classes/application.properties
WEB-INF/classes/static/assets/site.css
pages/about.html
WEB-INF/private-note.txt
meta/release.txt
org/springframework/boot/loader/launch/WarLauncher.class
```

Đây là **tập entry quan trọng**, không phải toàn bộ output của `jar tf`. Spring Boot repackage còn tạo các nested JAR dưới `WEB-INF/lib` và `WEB-INF/lib-provided`, cộng những metadata khác.

Main WAR **không nên có**:

```text
WEB-INF/classes/demo/war/WarLabApplicationTests.class
fixtures/test-only.txt
WEB-INF/classes/fixtures/test-only.txt
```

Test class và fixture không thuộc nguồn sản phẩm. Nếu chúng xuất hiện, cần điều tra Maven resources/test resources và plugin copy/packaging, không coi đó là bình thường chỉ vì test đã pass.

### 13.2. Kiểm tra file release đã được thay thế placeholder

Chỉ nhìn `jar tf` thấy `meta/release.txt` **không đủ** chứng minh filtering thành công. Cần đọc nội dung entry. Có thể dùng `jar xf` vào một thư mục xem tạm hoặc chương trình Java ở phần 14.

Giá trị mong đợi chính xác:

```text
build.version=1.0.0
```

Nếu vẫn thấy `@project.version@`, kiểm tra `webResources`, `filtering`, `delimiters` và plugin version. Nếu output khác version POM, kiểm tra user property/profile/effective POM trước khi sửa file WAR bằng tay.

## 14. Công cụ Java 17 kiểm tra **chính WAR bàn giao**

Dùng `java.util.zip.ZipFile` để đọc archive và `java.util.jar.Manifest` để đọc manifest. Bởi vì đây là WAR được Spring Boot repackage, chúng ta kiểm tra cả **WAR layout chuẩn** lẫn **Boot launcher**, chứ không chỉ kiểm tra file tồn tại.

Tệp `tools/InspectWar.java`:

```java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.jar.Attributes;
import java.util.jar.Manifest;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

public final class InspectWar {
    private InspectWar() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Provide exactly one WAR path");
        }

        try (ZipFile zip = new ZipFile(Path.of(args[0]).toFile())) {
            ZipEntry manifestEntry =
                    zip.getEntry("META-INF/MANIFEST.MF");
            if (manifestEntry == null) {
                throw new IllegalStateException("Missing WAR manifest");
            }

            Manifest manifest;
            try (InputStream stream = zip.getInputStream(manifestEntry)) {
                manifest = new Manifest(stream);
            }

            Attributes attrs = manifest.getMainAttributes();
            System.out.println("WAR main: "
                    + attrs.getValue(Attributes.Name.MAIN_CLASS));
            System.out.println("WAR start: "
                    + attrs.getValue("Start-Class"));
            System.out.println("API class: "
                    + (zip.getEntry(
                        "WEB-INF/classes/demo/war/GreetingController.class")
                       != null));
            System.out.println("Static asset: "
                    + (zip.getEntry(
                        "WEB-INF/classes/static/assets/site.css")
                       != null));
            System.out.println("Webroot page: "
                    + (zip.getEntry("pages/about.html") != null));

            ZipEntry release = zip.getEntry("meta/release.txt");
            if (release == null) {
                throw new IllegalStateException("Missing release metadata");
            }
            String releaseText;
            try (InputStream stream = zip.getInputStream(release)) {
                releaseText = new String(stream.readAllBytes(),
                        StandardCharsets.UTF_8).strip();
            }
            System.out.println("Filtered metadata: " + releaseText);

            System.out.println("Test class: "
                    + (zip.getEntry(
                        "WEB-INF/classes/demo/war/WarLabApplicationTests.class")
                       != null));
            System.out.println("Test fixture: "
                    + (zip.getEntry("fixtures/test-only.txt") != null));
            System.out.println("Boot loader: "
                    + (zip.getEntry(
                        "org/springframework/boot/loader/launch/WarLauncher.class")
                       != null));
            boolean hasProvided = zip.stream().anyMatch(
                    entry -> entry.getName().startsWith("WEB-INF/lib-provided/")
                          && entry.getName().endsWith(".jar"));
            System.out.println("Provided libs: " + hasProvided);
        }
    }
}
```

Java 17 hỗ trợ **source-file mode**. Sau khi tạo file `tools/InspectWar.java`, từ project root chạy:

```bash
java tools/InspectWar.java target/war-delivery-lab-1.0.0.war
```

Với POM mẫu và Spring Boot 3.3.5 repackage đúng, **stdout dự kiến của riêng lệnh này**:

```text
WAR main: org.springframework.boot.loader.launch.WarLauncher
WAR start: demo.war.WarLabApplication
API class: true
Static asset: true
Webroot page: true
Filtered metadata: build.version=1.0.0
Test class: false
Test fixture: false
Boot loader: true
Provided libs: true
```

Các dòng này dựa trên cấu trúc đã khai báo. Nếu actual stdout khác, **không sửa stdout mẫu để che lỗi**: dùng chính khác biệt để chẩn đoán Spring Boot repackage, WAR Plugin/webResources hoặc nguồn test bị đóng nhầm. Chương trình kiểm tra có thể vẫn in giá trị false mà không trả exit code khác 0, nên để dùng trong CI thực sự cần thêm assertions/exit policy cho từng điều kiện bắt buộc, hoặc một script parse output có kiểm chứng.

### 14.1. Java API kiểm tra khác với unzip thủ công

`jar tf` cho thấy **tên file trong WAR**. `ZipFile` giúp kiểm tra:

- Manifest có `Main-Class`/`Start-Class` phù hợp không?
- Class/controller đã vào `WEB-INF/classes`?
- CSS có đúng entry thuộc classpath static resources?
- Webroot HTML và filtered metadata có trong archive?
- Test class/fixture đã bị loại khỏi sản phẩm?
- Boot loader và `WEB-INF/lib-provided` có sau repackage?

Đây là kiểm tra **artifact của đúng lần build**, mạnh hơn việc chỉ thấy một thư mục `target` trong workspace.

Nếu muốn kiểm tra binary assets, lấy đúng bytes của ZipEntry và so checksum với input. Không dùng `String` để so file binary như PNG/PDF.

## 15. Chạy standalone executable WAR

Sau `mvn -B clean verify`:

```bash
java -jar target/war-delivery-lab-1.0.0.war
```

Đây là tiến trình server chạy liên tục, **không phải một lệnh in một dòng rồi thoát**. Nếu port 8080 còn trống và môi trường hợp lệ, Spring Boot khởi động embedded Tomcat. Console có nhiều log startup phụ thuộc Boot/logging/JDK, nên bài học không giả vờ cung cấp stdout startup chính xác.

Mở **terminal thứ hai** để thử API:

```bash
curl -fsS http://localhost:8080/api/hello
```

Response body kỳ vọng:

```text
WAR OK
```

Kiểm tra CSS:

```bash
curl -fsS http://localhost:8080/assets/site.css
```

Response body kỳ vọng chứa:

```css
body {
    color: navy;
}
```

Nếu yêu cầu byte-for-byte, kết quả có thể có hoặc không có newline ở cuối tùy file được tạo; nội dung CSS chính là file `site.css` trong source.

**Không yêu cầu `curl` truy cập `/WEB-INF/classes/...`**: đó là đường dẫn đóng gói nội bộ, không phải URL public của Spring MVC static resources.

Dừng server bằng cơ chế bình thường (ví dụ Ctrl+C trên terminal đã khởi chạy). Nếu port 8080 bận, truyền runtime option được Boot hỗ trợ:

```bash
java -jar target/war-delivery-lab-1.0.0.war --server.port=8081
```

Sau đó thử `http://localhost:8081/api/hello`. Tùy chọn này áp dụng khi chạy Boot standalone; với Tomcat bên ngoài, HTTP connector/port thường do external container quản lý chứ không phải chỉ thay `server.port` trong WAR.

## 16. Deploy cùng WAR lên external Tomcat

Một WAR Spring Boot MVC được cấu hình với `SpringBootServletInitializer` và Tomcat scope provided có thể deploy vào **Tomcat bên ngoài tương thích**. Ví dụ Tomcat 10.1 với Java hỗ trợ và không có xung đột ứng dụng/container.

Quy trình khái niệm:

1. Xác nhận WAR final đã pass Maven build/test và artifact inspection.
2. Xác nhận version Tomcat/Servlet/JDK theo compatibility matrix.
3. Dừng hoặc dùng cơ chế deploy an toàn theo quy trình vận hành.
4. Deploy file WAR đã được kiểm chứng vào context được phép.
5. Đợi container báo application startup thành công.
6. Thử endpoint cùng context path thực tế.
7. Kiểm tra static assets và external configuration/secret injection.
8. Theo dõi server logs và quy trình rollback.

Nếu Tomcat dùng auto-deploy của thư mục `webapps` và file được đặt tên `war-delivery-lab.war`, context thường là `/war-delivery-lab`. Khi đó URL có thể là:

```text
http://localhost:8080/war-delivery-lab/api/hello
```

Response body vẫn là `WAR OK` nếu app khởi động thành công. **Không tự kết luận context path từ artifactId nếu môi trường deploy dùng cấu hình riêng**, chẳng hạn file `context.xml`, virtual host, proxy rewrite hoặc root context.

### 16.1. Tại sao deploy ngoài không cần embedded Tomcat trong WEB-INF/lib?

Tomcat bên ngoài tự cấp engine Servlet; những bản tomcat-embed nằm trong `WEB-INF/lib-provided` của **Boot executable WAR** không được container đối xử như thư viện webapp thông thường tại `WEB-INF/lib`. Khi chạy `java -jar`, Boot loader lại có khả năng đưa các dependency provided đó vào classpath standalone.

Đây là một điểm cốt lõi khiến **Spring Boot executable WAR** khác WAR truyền thống chỉ có `WEB-INF/classes` và `WEB-INF/lib`. Đừng tự copy các JAR từ `WEB-INF/lib-provided` vào `WEB-INF/lib` như một bước deploy nếu không có hướng dẫn tương thích cụ thể.

### 16.2. Chọn giữa JAR và WAR

Nếu ứng dụng chỉ cần chạy standalone/container image, executable Spring Boot JAR thường đơn giản hơn. Chọn WAR khi có lý do rõ ràng: external servlet container do tổ chức quản lý, integration với hệ thống WAR hiện có hoặc hợp đồng deploy cụ thể.

Không gắn chiến lược external WAR cho ứng dụng Spring WebFlux với Reactor Netty theo giả định nó giống Spring MVC. Theo hướng dẫn Spring Boot, **WebFlux traditional WAR deployment không được hỗ trợ** theo cách này.

## 17. Kiểm tra bản bàn giao, không chỉ file xuất hiện

Một lần bàn giao WAR có thể gồm:

| Bằng chứng | Cần xác nhận |
| --- | --- |
| Maven command | `mvn -B clean verify` từ đúng commit/module |
| Maven exit code | Thành công và không che lỗi bằng cờ skip |
| Test report | JUnit/Surefire XML mới, số test phù hợp, không có failure/error ngoài policy |
| Artifact path | `target/war-delivery-lab-1.0.0.war` là file cuối sau repackage |
| Archive integrity | File đọc được bằng `jar tf`/`ZipFile`, không bị hỏng |
| Class layout | `WEB-INF/classes` có controller/application |
| Static assets | `WEB-INF/classes/static/assets/site.css` và `pages/about.html` ở vị trí đúng |
| Filtered resource | `meta/release.txt` chứa đúng version, không còn placeholder |
| Internal resources | Không nhúng secrets; `WEB-INF` không được xem là hệ thống bảo vệ credential |
| Dependencies | `WEB-INF/lib`/`WEB-INF/lib-provided` đúng theo cách triển khai |
| Boot manifest | `WarLauncher` và `Start-Class` đúng khi cần executable WAR |
| Test artifacts | Không có test class/fixture/Surefire reports trong WAR |
| Runtime smoke | API, static assets và context path hoạt động ở môi trường đã chọn |
| Security/provenance | SHA-256, scan dependencies, chính sách phát hành và nơi lưu artifact |
| Rollback | Có đúng version/artifact trước và cách quay lại trạng thái ổn định |

**Mục đích:** kiểm chứng được **nội dung**, **khả năng chạy** và **khả năng tái hiện nguồn gốc** của artifact, không chỉ việc Maven đã tạo ra một file có đuôi `.war`.

### 17.1. Tên file local, artifact coordinates và classifier

Với project GAV `demo:war-delivery-lab:1.0.0` và `packaging=war`, main artifact thường là WAR classifier rỗng. Thay `project.build.finalName` có thể đổi tên file trong `target` nhưng không tự đổi GAV trên Maven repository.

Khi build thêm attached WAR có classifier hoặc Boot Plugin được cấu hình để attach một artifact khác, cần biết **file nào được install/deploy**. Không upload một file `*.war` tùy ý vì tên giống, nhất là khi còn bản `original`/`plain` hoặc nhiều classifier.

### 17.2. Tính tái lập và checksum

Maven WAR Plugin và Spring Boot Maven Plugin có cơ chế hỗ trợ timestamp ổn định. Nhưng WAR vẫn có thể khác byte giữa hai build vì version dependency/plugin, output sinh động, manifest, file order, encoding và runtime JDK.

Trên Linux/macOS:

```bash
sha256sum target/war-delivery-lab-1.0.0.war
```

Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 target\war-delivery-lab-1.0.0.war
```

Đây là lệnh đọc checksum thực tế; bài không đưa một giá trị SHA-256 cố định vì byte artifact phụ thuộc build. Nếu hai clean builds cùng commit khác hash, đừng vội kết luận WAR Plugin lỗi; phân tích toàn bộ build inputs và packaging stages.

## 18. CI: nên thu những gì khi build WAR?

Một quy trình CI khái niệm:

```text
Checkout / resolve Maven Wrapper / JDK
          │
          ▼
mvn -B clean verify
          │
          ├── Surefire TEST-*.xml để publish kết quả kiểm thử
          │
          └── target/*.war đã được đóng gói và repackage
                    │
                    ▼
            jar tf / ZipFile inspection
                    │
                    ▼
            kiểm tra manifest, assets, version, test leakage
                    │
                    ▼
            smoke deploy/running qua môi trường phù hợp
                    │
                    ▼
            archive signed/checksummed artifact, promote nếu QA pass
```

Các lệnh kiểm tra artifact demo:

```bash
mvn -B clean verify
jar tf target/war-delivery-lab-1.0.0.war
java tools/InspectWar.java target/war-delivery-lab-1.0.0.war
```

CI phải lưu Surefire XML **cả khi Maven fail**. Nếu chỉ upload report/artifact trong nhánh success, failure quan trọng có thể mất log chẩn đoán. Đồng thời không nên publish WAR cho environment thật nếu test/inspection/smoke checks chưa đạt theo policy.

**Không archive cả thư mục `target` vô điều kiện**: nó có thể chứa intermediate outputs, test reports nhạy cảm, bản WAR trước repackage hoặc file tạm. Thu đúng đường dẫn/extension và kiểm tra quyền truy cập artifact.

### 18.1. Nếu Java InspectWar chỉ in true/false, CI nên fail thế nào?

Chương trình demo được tối ưu để quan sát kiến thức, nên nó in kết quả thay vì chấm tất cả lỗi bằng exit code. Khi đưa vào CI sản xuất, có thể chuyển các điều kiện sang:

```java
if (zip.getEntry("WEB-INF/classes/demo/war/GreetingController.class") == null) {
    throw new IllegalStateException("Required controller missing");
}
```

Đây chỉ là **đoạn nâng cấp cho bên trong block try của InspectWar**, không phải class Java độc lập. Tương tự, nếu fixture test xuất hiện, cần báo fail. Khi chương trình ném exception không được bắt, `java` trả exit code khác 0, giúp CI chặn bàn giao không hợp lệ.

Kiểm tra **response HTTP thực tế** cũng nên có expected status/body rõ ràng, không chỉ dùng curl để tải URL rồi bỏ qua response.

## 19. Các tình huống lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra / xử lý |
| --- | --- | --- |
| Không thấy `target/*.war` | `packaging` không phải war, build dừng trước package hoặc tên file khác | Xem POM, lifecycle log, `project.build.finalName` |
| WAR tạo được nhưng thiếu class | Compiler chưa chạy, source root sai, output bị exclude | Xem `target/classes` và `WEB-INF/classes` trong WAR |
| Có CSS ở `target/classes` nhưng request HTTP 404 | Sai URL/static handler/context path hoặc file không nằm đúng entry | So `WEB-INF/classes/static/...` và HTTP mapping |
| `src/main/webapp/pages/about.html` không vào WAR | WAR source directory/includes/excludes sai | Xem `warSourceDirectory`, `jar tf` |
| `meta/release.txt` thiếu | `webResources` sai directory/targetPath/includes | Kiểm tra POM WAR Plugin và WAR entries |
| File release còn `@project.version@` | Filtering chưa bật/delimiter khác | Xem `webResources filtering`, plugin version |
| PNG/font bị hỏng | Filtering nhị phân, encoding hoặc bước frontend build | Copy không filter, so checksum input/entry |
| WAR báo thiếu `web.xml` | Cấu hình WAR plugin/Servlet API/legacy descriptor không phù hợp | Dùng `failOnMissingWebXml=false` khi app thực sự không cần |
| Spring Boot WAR chạy với `java -jar` báo thiếu main | Boot repackage chưa chạy hoặc manifest sai | Kiểm tra Boot Plugin, parent/execution, WarLauncher |
| Có `WEB-INF/lib-provided` nhưng external container lỗi | Container/JDK/Servlet namespace không tương thích | So Tomcat, Boot, Jakarta Servlet và dependency scope |
| `ClassNotFoundException javax.servlet.*` | Dùng thư viện/container Servlet cũ với Boot 3.x Jakarta | Nâng libraries/container theo compatibility |
| `NoClassDefFoundError` một thư viện ứng dụng | Dependency scope sai, WAR lib thiếu hoặc collision | Xem `WEB-INF/lib` và dependency tree |
| Test pass nhưng deploy fail | MockMvc chưa kiểm tra container thật, context path/container config khác | Smoke test trên Tomcat và xem server logs |
| 404 sau deploy ngoài nhưng standalone chạy | External context path khác root, servlet mapping khác | Kiểm tra context/virtual host/reverse proxy |
| Test fixture xuất hiện trong WAR | Copy cả `src/test` hoặc output test vào web root | So resources/testResources và WAR excludes |
| Secrets lọt vào WAR | Filter/packaging đã nhúng cấu hình runtime | Xử lý credential, sửa pipeline và đánh giá artifact đã phát hành |
| Không có file WAR sau `mvn test` | Chưa chạy phase `package` | Dùng `mvn package`/`verify` |
| Chạy direct `war:war` cho WAR thiếu resource | Bỏ qua lifecycle compile/process-resources | Gọi `mvn clean package` |
| Spring Boot repackaging tạo nhiều file | Có bản archive tiền repackage/attached classifier | Xác định artifact cuối được install/deploy |
| WAR thiếu JAR khi chạy ngoài Tomcat | Scope/transitive resolution hoặc config skinny WAR sai | Đọc WAR lib layout và dependency tree |
| Tomcat 9 không chạy Boot 3.x WAR | Namespace `javax` không tương thích `jakarta` | Chọn Tomcat phù hợp Servlet/Jakarta version |
| Tệp trong `WEB-INF` vẫn đọc được bằng unzip | Đây là bản archive, không phải vault mã hóa | Không lưu secret trong WAR |
| Deploy WAR xong nhưng server port bận | Port/container configuration không đúng | Kiểm tra log startup, port binding và external server |
| Hai WAR giống source khác checksum | Timestamp, resource filter, nested dependencies hoặc JDK khác | Pin build inputs, kiểm tra outputTimestamp |
| JSP hoạt động local nhưng fail ở deployment khác | JSP compiler/servlet container/Jasper khác nhau | Kiểm tra JSP support và version/container |
| CI lấy nhầm WAR original | Bản trung gian trước Boot repackage được chọn | Kiểm tra manifest `WarLauncher` và artifact path cuối |

### 19.1. Thứ tự chẩn đoán khi ứng dụng báo 404

1. Ghi **URL đầy đủ** gồm scheme/host/port/context path.
2. Kiểm tra app đã deploy/start thành công trong container chưa.
3. Xác định endpoint là **Spring MVC controller**, **classpath static resource**, **web-root resource**, JSP hay Servlet mapping.
4. Nếu là controller, xác nhận Spring component scan và path mapping.
5. Nếu là static CSS, kiểm tra WAR entry `WEB-INF/classes/static/assets/site.css` và URL `/assets/site.css` ở đúng context.
6. Nếu là webroot HTML, kiểm tra entry `pages/about.html` và config của container/DispatcherServlet.
7. Xem reverse proxy, auth filters, Spring Security và error logs nếu có.
8. Test lại bằng một HTTP client gửi request rõ ràng, không dựa vào browser cache.

**Lỗi 404 không chứng minh WAR thiếu file**; có thể file đúng trong archive nhưng URL bị rewrite hoặc resource handler không map tới vị trí đó.

### 19.2. Phân biệt lỗi build, package và runtime

- `mvn compile` fail: ưu tiên sửa Java source/JDK/dependency.
- `mvn test` fail: đọc test reports và lỗi MockMvc/configuration.
- `war:war` fail: xem webResources path, permissions, filtering, web.xml/overlays.
- `spring-boot:repackage` fail: xem Boot plugin/main class/layout và artifact input.
- `java -jar` fail: kiểm tra WarLauncher, Start-Class, provided libs, port, configuration.
- External container deploy fail: kiểm tra Jakarta Servlet compatibility, JDK, context, JNDI/config, classloader và server logs.
- Deploy thành công nhưng asset sai: kiểm tra request path, war layout, content filtering/cache và browser network errors.

Đây là những ranh giới hữu ích để tránh sửa **Maven WAR Plugin** khi lỗi thật nằm ở code, container hoặc reverse proxy.

## 20. Những bẫy riêng khi làm Spring Boot WAR

### 20.1. Đưa static CSS vào đâu?

Với Boot MVC, cách phổ biến và dễ kiểm chứng là:

```text
src/main/resources/static/assets/site.css
    -> WEB-INF/classes/static/assets/site.css
    -> HTTP /assets/site.css (khi mapping mặc định)
```

Nếu đặt CSS trong `src/main/webapp/assets`, WAR Plugin có thể đóng nó ở web root, nhưng cách Servlet container/DispatcherServlet phục vụ nó phải được kiểm tra riêng. Đừng tự giả định hai kiểu resource root có cùng semantics.

### 20.2. JSP không giống static HTML

File JSP thường nằm dưới `src/main/webapp` và cần JSP engine/container hỗ trợ; các trường hợp embedded vs external, executable JAR vs WAR có ràng buộc riêng. Không chỉ đặt `.jsp` vào `src/main/resources/static` rồi kỳ vọng Boot MVC render JSP. Với ứng dụng chủ yếu dùng REST/static HTML, không cần đưa JSP vào ví dụ chỉ để làm WAR trông “đủ chuẩn”.

### 20.3. WEB-INF/lib-provided không phải WAR lib thông thường

Đối với executable WAR Boot, `WEB-INF/lib-provided` hỗ trợ launcher standalone. Không tự coi đây là các JAR được external container dùng khi deploy. External container có engine riêng; việc copy provided Tomcat JAR vào `WEB-INF/lib` có thể tạo xung đột.

### 20.4. Main-Class của executable WAR là Boot launcher

Khi Boot repackage WAR, manifest thường có:

```text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: demo.war.WarLabApplication
```

Không cấu hình WAR Plugin như một JAR thường với `Main-Class=demo.war.WarLabApplication` rồi đòi nó tự xử lý nested JARs. Với Boot executable WAR, plugin repackage quản lý loader/manifest.

### 20.5. Không hardcode môi trường vào WAR

File `application.properties` trong WAR nên chứa default công khai. Những giá trị thay đổi theo environment hoặc mang secret nên được cấp từ outside artifact, theo nguyên tắc cấu hình an toàn của tổ chức. Một WAR có `build.version=1.0.0` là metadata ổn; một WAR chứa database password production là rủi ro.

### 20.6. Thứ tự chạy test rồi package không đủ cho deployment QA

MockMvc kiểm tra Spring MVC handler, nhưng **không** thay thế external servlet container test. Vì thế sau khi Maven build và InspectWar pass, môi trường staging cần deploy thật để kiểm tra context path, listener, filter, classpath conflicts, static resource behavior, startup timeout và external configuration.

## 21. Checklist bàn giao WAR

Trước khi đánh dấu một WAR sẵn sàng:

- [ ] `<packaging>war</packaging>` đúng mục tiêu, plugin versions được pin?
- [ ] Maven WAR Plugin được cấu hình đúng web root, `webResources` và packaging filters?
- [ ] Không cần `web.xml` thì cơ chế ServletInitializer/annotations đã được kiểm chứng?
- [ ] Java classes nằm dưới `WEB-INF/classes`, runtime libraries đúng `WEB-INF/lib`?
- [ ] Với Boot executable WAR, `WarLauncher`/`Start-Class` và `WEB-INF/lib-provided` đúng?
- [ ] External container/JDK/Servlet namespace tương thích với Boot version?
- [ ] Static assets và web-root HTML ở đúng path bên trong WAR?
- [ ] Filtered release metadata đã được thay placeholder, file binary vẫn nguyên byte?
- [ ] Fixture/test class/report không lọt vào WAR chính?
- [ ] Không có credential, token hoặc config môi trường nhạy cảm trong archive?
- [ ] `mvn -B clean verify` chạy test thật, Surefire XML xác nhận số test?
- [ ] `jar tf` và `InspectWar` đối chiếu WAR cuối, không chỉ staging directory?
- [ ] Standalone smoke test trên `java -jar` pass khi có yêu cầu executable WAR?
- [ ] External container smoke test kiểm tra context path, endpoints và static assets?
- [ ] Artifact cuối được xác định chính xác theo GAV, không upload nhầm bản original/attached?
- [ ] Có checksum/provenance, phương án rollback và quy trình lưu trữ artifact?
- [ ] Công cụ CI thu test logs cả khi build fail, không trộn report từ các lần chạy?

**Kết luận:** Maven WAR Plugin đóng gói Java web application theo layout gồm **web root, WEB-INF/classes và WEB-INF/lib**. Spring Boot Maven Plugin có thể tiếp tục repackage thành **executable WAR** với `WarLauncher` và `WEB-INF/lib-provided`. Chất lượng bàn giao phụ thuộc vào **tài nguyên đúng vị trí, cấu hình lọc an toàn, dependency/container tương thích, test thực sự chạy và kiểm chứng file WAR cuối cùng**. Một WAR có thể mở được bằng `jar tf` nhưng vẫn không chạy đúng trên Tomcat; một build MockMvc pass cũng chưa chứng minh deployment. Vì vậy cần phối hợp **archive inspection + test reports + runtime smoke tests**.

### Tài liệu tham khảo chính thức

- [Apache Maven WAR Plugin 3.4.0 — war:war](https://maven.apache.org/plugins-archives/maven-war-plugin-3.4.0/war-mojo.html)
- [Apache Maven WAR Plugin — Adding and Filtering External Web Resources](https://maven.apache.org/plugins/maven-war-plugin/examples/adding-filtering-webresources.html)
- [Apache Maven WAR Plugin — Including and Excluding Files](https://maven.apache.org/plugins/maven-war-plugin/examples/including-excluding-files-from-war.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Spring Boot — Traditional Deployment](https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html)
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot — Executable WAR Layout and Nested JARs](https://docs.spring.io/spring-boot/3.4/specification/executable-jar/nested-jars.html)
- [Spring Boot — Launching Executable Archives](https://docs.spring.io/spring-boot/specification/executable-jar/launching.html)
- [Spring Boot — Servlet Web Applications / Static Content](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
