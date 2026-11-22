# Loại trừ đường dẫn, thêm đường dẫn theo dõi và dùng trigger file trong Spring Boot Devtools 3.3

## 1. Mục tiêu và bối cảnh

Khi lập trình Spring Boot, sửa một tệp Java, HTML, CSS, cấu hình hoặc tài nguyên bên ngoài có thể dẫn đến các hành động khác nhau: **khởi động lại application context**, **thông báo LiveReload**, **không làm gì** hoặc **đợi một thao tác xác nhận**. Spring Boot Devtools cho phép điều chỉnh hành vi này bằng ba nhóm cấu hình:

- `spring.devtools.restart.exclude` và `spring.devtools.restart.additional-exclude`: quy định **những đường dẫn thay đổi không cần full application restart**.
- `spring.devtools.restart.additional-paths`: mở rộng phạm vi **các thư mục được theo dõi** ngoài những thư mục có trên classpath.
- `spring.devtools.restart.trigger-file`: chỉ cho phép **kiểm tra và kích hoạt restart tại thời điểm bạn cập nhật một tệp kích hoạt**, thay vì restart mỗi lần IDE biên dịch.

Đây là bài học thuộc nhóm **Devtools**, tập trung trực tiếp vào cách phối hợp ba cơ chế trên với **classpath output** và công cụ build. Bài sử dụng Java 21, Spring Boot **3.3.13**, Maven và `spring-boot-devtools`.

Sau khi học, bạn phải làm được:

1. Phân biệt `restart` với `LiveReload` và refresh trình duyệt.
2. Hiểu khi nào việc sửa mã nguồn được Devtools nhìn thấy; vì sao `src/main/java` thay đổi chưa chắc đã kích hoạt restart nếu `target/classes` chưa được cập nhật.
3. Hiểu các đường dẫn loại trừ mặc định và khác biệt **ghi đè** so với **bổ sung** loại trừ.
4. Theo dõi một thư mục ngoài classpath và không nhầm **theo dõi thay đổi** với **nạp tệp vào Environment/classpath**.
5. Tạo trigger file tồn tại trên classpath, chỉ sửa nó khi muốn Devtools xét những thay đổi đang chờ.
6. Chạy dự án mẫu qua `mvn spring-boot:run`, thử thay đổi Java, static resource, thư mục bổ sung, trigger file.
7. Khắc phục tình trạng không restart, restart quá nhiều, trigger file không hiệu lực và các sai lầm về classloader/bảo mật.
8. Viết JUnit kiểm thử ứng dụng; biết phần restart file-watcher cần kiểm thử tích hợp/thủ công, không cố dùng unit test để khẳng định OS watcher luôn hoạt động.

**Giới hạn quan trọng:** Devtools là công cụ **phát triển cục bộ**, không phải production hot-deploy framework, không phải một cơ chế phân phối cấu hình tự động, cũng không thay thế rolling deployments.

## 2. Cơ chế nền: theo dõi tệp nào?

### 2.1. Devtools không theo dõi mọi thứ trên ổ đĩa

Spring Boot Devtools thường theo dõi các mục trên **runtime classpath** trỏ tới **thư mục**, ví dụ:

```text
Dự án Maven
src/main/java/com/example/demo/StatusController.java
                       |
                       | javac / mvn compile / IDE Build
                       v
target/classes/com/example/demo/StatusController.class
                       |
                       | Devtools file watcher phát hiện classpath đổi
                       v
Có cần restart? Có trigger file không?
                       |
                       +--> restart context (nếu đủ điều kiện)
```

Sửa `StatusController.java` trong editor nhưng chưa biên dịch/đồng bộ tệp `.class` tương ứng thì **không phải** Devtools đã nhận được một thay đổi classpath. Đó là lý do:

- Eclipse hoặc Spring Tools có thể cập nhật output khi Save/Build tùy thiết lập.
- IntelliJ IDEA thường cần `Build → Build Project` hoặc tự động biên dịch khi chạy nếu đã bật.
- Maven có thể dùng `mvn compile` trong một terminal khác.
- Nếu chạy ứng dụng thông qua build plugin, phải giữ chế độ **fork** phù hợp để restart classloader hoạt động; không cố tắt forking rồi kỳ vọng Devtools restart bình thường.

Classpath output cụ thể tùy IDE/build tool: `target/classes` với Maven thường gặp, `build/classes` hoặc `build/resources` với Gradle, hoặc một thư mục output của IDE. Phải biết JVM đang dùng classpath nào.

### 2.2. Hai classloaders và restart nhanh

Devtools restart thường dùng:

- **Base classloader** cho các thư viện ít thay đổi như JAR dependencies.
- **Restart classloader** cho các project classes/resources đang phát triển.

Khi restart, lớp restart bị thay bằng một instance mới, Spring application context được tạo lại và bean lifecycle tương ứng chạy lại. Thư viện đã nạp trong base classloader thường được tái sử dụng, nên thời gian restart có thể ngắn hơn cold start.

Đây **không** phải phép đổi body của một method đang chạy trong JVM mà không tạo lại Spring context. Bean cũ có thể bị destroy và bean mới được tạo, nên đối với session, cache hoặc dữ liệu in-memory phải cân nhắc khác biệt với hot code swapping thực sự.

### 2.3. Restart khác LiveReload

| Hành vi | Ứng dụng Spring | Trình duyệt |
| --- | --- | --- |
| **Full restart qua Devtools** | Đóng context cũ và khởi động lại context mới | Có thể được yêu cầu refresh khi LiveReload được dùng |
| **LiveReload** | Không nhất thiết restart context | Trình duyệt có LiveReload client/extension có thể reload |
| **Refresh thủ công** | Thường không restart Spring | Browser gửi request mới và hiển thị nội dung cập nhật |
| **Không có thay đổi classpath** | File watcher có thể không thấy thay đổi | Chưa có cơ sở để tự reload |

Devtools có LiveReload server trong chế độ phát triển khi tính năng bật và môi trường phù hợp. **Không nhầm** việc một static file được phục vụ bản mới sau F5 với việc Spring context đã restart. Muốn chứng minh restart, nên quan sát một log từ `ApplicationReadyEvent` hoặc kiểm tra lifecycle/instance mới.

## 3. Loại trừ đường dẫn mặc định

Một số thư mục tài nguyên không cần full restart mỗi khi chỉnh sửa. Theo tài liệu Spring Boot 3.3, mặc định Devtools loại trừ các nhóm:

- `META-INF/maven/**`
- `META-INF/resources/**`
- `resources/**`
- `static/**`
- `public/**`
- `templates/**`

Vì thế, sửa các tài nguyên tương ứng thường **không trigger full restart**, nhưng có thể dẫn đến **LiveReload** khi Devtools và LiveReload được dùng đúng điều kiện.

Ví dụ:

```text
src/main/resources/static/site.css
          |
          | copy resources:resources
          v
target/classes/static/site.css
          |
          +-- File mới được server đọc từ classpath output
          +-- Không cần xây lại Spring context theo mặc định
          +-- Browser có thể refresh thủ công hoặc qua LiveReload
```

Đường dẫn trong pattern nên được hiểu theo cơ chế matching của Devtools đối với thư mục nó đang theo dõi. Các dấu `**`/`*` là mẫu glob-style/Ant-style trong cấu hình, **không** phải tên một tệp thực.

### 3.1. Thay bộ loại trừ bằng restart.exclude

Ví dụ:

```properties
spring.devtools.restart.exclude=static/**,public/**
```

**Điểm cần nhớ:** `restart.exclude` là cách **tùy biến/thay thế danh sách mặc định**, không phải lệnh tự động nối thêm hai pattern này vào mọi default pattern.

Hệ quả: những nhóm vốn có thể được loại trừ theo mặc định, như `templates/**` hoặc `META-INF/resources/**`, có thể không còn được loại trừ nếu bạn chỉ đặt `static/**,public/**`. Khi sửa chúng, Devtools có thể restart mạnh hơn dự kiến.

Chỉ dùng `restart.exclude` khi **thực sự muốn quản lý toàn bộ tập loại trừ**, đã kiểm tra những pattern còn lại và chấp nhận thay đổi đối với restart/LiveReload behavior.

### 3.2. Giữ mặc định và thêm loại trừ: additional-exclude

Nếu muốn **giữ các default exclusions** và bổ sung thư mục build-generated hoặc tệp tạm:

```properties
spring.devtools.restart.additional-exclude=generated/**,**/*.tmp
```

Điều này có nghĩa các tệp khớp với những pattern bổ sung sẽ không buộc phải full restart theo chính sách loại trừ, trong khi `static/**`, `public/**`, `templates/**`... vẫn giữ vai trò mặc định.

Ví dụ chọn `generated/**` cho một thư mục chứa files do công cụ sinh ra liên tục trong classpath; mục đích là tránh mỗi lần cập nhật một file report hoặc metadata không liên quan đều gây restart. Cần đánh giá xem các tệp ấy **có thật sự không ảnh hưởng đến bean/config runtime hay không**: nếu một bean đọc nội dung một lần ở khởi động, việc loại trừ restart có thể khiến bean không bao giờ nạp lại giá trị mới.

**Không nên dùng `additional-exclude=**/*` hoặc pattern quá rộng**: như vậy nhiều thay đổi Java/classpath quan trọng có thể không kích hoạt restart và làm quá trình debug khó hiểu.

### 3.3. Bảng so sánh

| Cấu hình | Tập loại trừ mặc định | Pattern bổ sung |
| --- | --- | --- |
| Không khai báo gì | Giữ mặc định | Không |
| `spring.devtools.restart.exclude=static/**,public/**` | **Thay** bằng tập khai báo | Static, public |
| `spring.devtools.restart.additional-exclude=generated/**` | **Giữ** mặc định | Generated |
| Đặt cả `exclude` và `additional-exclude` | Dùng tập thay thế từ `exclude` | Nối thêm nhóm `additional-exclude` |

Khi kiểm tra behavior, đừng chỉ nhìn source file path. Phải xác định **tệp trên classpath/đường dẫn được watcher theo dõi** và mẫu mà Devtools dùng cho đường dẫn đó.

### 3.4. Loại trừ restart không có nghĩa loại khỏi classpath

Một `static/site.css` nằm trong classpath vẫn có thể được HTTP server phục vụ. `restart.additional-exclude` chỉ ảnh hưởng **quyết định reload/restart do thay đổi**, không xóa file khỏi JAR, không cấm Spring đọc file và không biến tệp thành bí mật.

Nếu file không được phép đóng gói/phát hành, cần sửa Maven resources, Gradle source sets, packaging hoặc security rules; không thể dùng `spring.devtools.restart.exclude` thay cho package exclusion.

## 4. Theo dõi thư mục bổ sung với additional-paths

Devtools theo dõi thư mục classpath theo mặc định. Đôi khi một dự án có thư mục nằm **ngoài** classpath nhưng vẫn cần phát hiện thay đổi trong quá trình phát triển:

```text
workspace/
├── local-dev-watch/             <-- ngoài classpath app
│   └── marker.txt
└── devtools-watch-demo/
    ├── pom.xml
    ├── src/main/java/...
    └── target/classes/...
```

Cấu hình tại `devtools-watch-demo/src/main/resources/application.properties`:

```properties
spring.devtools.restart.additional-paths=../local-dev-watch
```

Ví dụ trên giả định working directory của tiến trình khi chạy là **thư mục project**. Với IDE, build runner, container hoặc scripts, working directory có thể khác. Nếu cần chắc chắn, dùng **đường dẫn tuyệt đối theo môi trường phát triển** hoặc xác minh `user.dir` và địa chỉ thư mục tồn tại trước khi chạy. Không hardcode đường dẫn máy người khác vào repo nếu dự án dùng chung nhiều hệ điều hành.

### 4.1. Theo dõi không có nghĩa file được đọc tự động

`additional-paths` chỉ bổ sung **nguồn thay đổi** cho cơ chế file watching. Nó không tự:

- Thêm tệp vào Java classpath.
- Đưa thư mục vào `spring.config.import`.
- Tạo Spring bean mới cho file đó.
- Reload object đã đọc file từ trước theo ý nghĩa nghiệp vụ.
- Phân phối file tới mọi node trong Kubernetes.

Ví dụ, sửa `../local-dev-watch/marker.txt` có thể làm Devtools xét restart, nhưng nếu code ứng dụng **không đọc** `marker.txt` thì behavior nghiệp vụ không thay đổi. Nếu ứng dụng cần đọc cấu hình thực, phải cấu hình đường nạp file và hành vi khi startup rõ ràng.

### 4.2. Thay đổi additional-paths: restart hay LiveReload?

Các tệp trong additional paths có thể được xem là thay đổi cần full restart, trừ khi chính sách loại trừ match với chúng. Tài liệu Spring Boot cho phép dùng những cấu hình `restart.exclude` liên quan để chọn giữa full restart và LiveReload cho đường dẫn theo dõi bổ sung.

Một quy trình đúng:

1. Chỉ định một thư mục bổ sung đã tồn tại.
2. Chạy ứng dụng và chờ Devtools ổn định.
3. Sửa một file không bị exclude và quan sát restart.
4. Nếu cần tệp loại trừ, thêm pattern phù hợp với **cách Devtools matching đường dẫn thực**; kiểm tra kết quả trên đúng OS/build runner.
5. Nếu có trigger file, hãy cập nhật file trigger sau khi thay đổi và đưa nó lên classpath, thay vì mong thư mục bổ sung restart ngay.

**Không ngộ nhận:** `additional-exclude` và `additional-paths` không phải hai property đồng nghĩa. Một bên nói **không restart vì file nào**, bên kia nói **theo dõi thêm ở đâu**.

### 4.3. Theo dõi thư mục chứa dữ liệu biến động liên tục có tốt không?

Thường không. Một thư mục logs, upload, temporary outputs hoặc generated artifacts lớn có thể liên tục thay đổi, khiến Devtools tốn công quét hoặc restart nhiều lần. Không nên đặt cả thư mục `target`, `build`, database files, temporary upload hay git worktree lớn vào `additional-paths` khi không thực sự cần.

Nếu dự án multi-module, chỉ đưa các thư mục output thực sự có thay đổi hữu ích vào watcher; việc đưa mọi dependency JAR vào watcher không biến chúng thành classloader reloadable theo cách bạn mong đợi.

## 5. Trigger file: chỉ restart khi chủ động yêu cầu kiểm tra

### 5.1. Mục đích

Trong một IDE liên tục compile, Devtools có thể restart quá thường xuyên: người lập trình lưu file A, tiếp tục sửa file B, code vẫn chưa ở trạng thái biên dịch phù hợp hoặc application context phải tạo lại liên tục. **Trigger file** tạo một điểm xác nhận thủ công.

Ví dụ property:

```properties
spring.devtools.restart.trigger-file=.reloadtrigger
```

Tệp `.reloadtrigger` phải tồn tại **ở đâu đó trên runtime classpath**. Đặt nó trong `src/main/resources` để được copy vào output là một cách chuẩn:

```text
src/
└── main/
    └── resources/
        ├── application.properties
        ├── .reloadtrigger
        └── static/
            └── message.txt
```

Giá trị property là **tên tệp không kèm path**: `.reloadtrigger`, không phải `src/main/resources/.reloadtrigger` hoặc `target/classes/.reloadtrigger`.

### 5.2. Trigger file thực sự điều khiển điều gì?

Một lần cập nhật trigger file yêu cầu Devtools **kiểm tra các thay đổi đã được nhận biết**. Restart **chỉ thực sự xảy ra nếu Devtools phát hiện có việc phải làm**; chỉ chạm trigger file mà không có thay đổi đáng restart trước đó có thể không tạo ra một restart đáng quan sát.

Luồng thông thường:

```text
Sửa nhiều file Java
      |
      +-- IDE/Maven biên dịch, target/classes thay đổi
      |
      +-- Devtools ghi nhận thay đổi nhưng trigger-file chưa cập nhật
      |
Người lập trình sửa .reloadtrigger trên classpath
      |
      +-- Devtools kiểm tra các thay đổi đã xảy ra
      |
      +-- Nếu có thay đổi cần restart: đóng/restart context
      +-- Nếu không: không cần restart
```

**Nên coi trigger file là “check now”, không phải “force restart bất kể mọi điều kiện”.** Nếu bạn chỉ thay đổi một excluded static resource, context có thể không restart dù đã chạm trigger file; đó là hệ quả hợp lý của chính sách excludes.

### 5.3. Nguồn và output là hai vị trí khác nhau

Với Maven:

```text
src/main/resources/.reloadtrigger     <-- source
              |
              | Maven resources:resources / compile
              v
target/classes/.reloadtrigger         <-- runtime classpath output
              |
              +-- Devtools watcher nhìn ở đây
```

Chỉ sửa tệp source nhưng IDE/build tool **không copy nó vào output** có thể khiến Devtools không quan sát bất kỳ cập nhật trigger nào. Khi debug, hãy kiểm tra tệp thực tồn tại tại `target/classes/.reloadtrigger` (hoặc thư mục output tương đương).

**Thao tác chạm file cần làm thay đổi timestamp hoặc nội dung đủ để watcher nhìn thấy**. Nếu filesystem có timestamp resolution thấp, sửa nội dung bằng một marker mới có thể ổn định hơn một lần `touch` quá sát.

### 5.4. Có thể dùng trigger file toàn cục?

Trong môi trường phát triển cá nhân, Spring Boot Devtools hỗ trợ global settings để áp dụng cơ chế trigger file cho nhiều dự án. Điều này hữu ích khi IDE có auto-build, nhưng cần nhớ: mỗi ứng dụng vẫn cần trigger file xuất hiện trên **classpath của nó** và cách thực hiện cập nhật đúng với công cụ đang dùng.

Không bật hoặc tùy biến cấu hình toàn cục mà quên nó đang ảnh hưởng đến các dự án khác, khiến developer tưởng restart đã hỏng. Nếu muốn demo dễ tái hiện, nên đặt property trong project trước.

## 6. Phối hợp cả ba cấu hình

Một cấu hình phát triển đầy đủ:

```properties
spring.application.name=devtools-watch-demo
server.port=8080

# Giữ các default exclusions và bổ sung vài file sinh ra.
spring.devtools.restart.additional-exclude=generated/**,**/*.tmp

# Theo dõi thêm một thư mục cùng cấp project (ví dụ local).
spring.devtools.restart.additional-paths=../local-dev-watch

# Chỉ kiểm tra restart khi marker được cập nhật.
spring.devtools.restart.trigger-file=.reloadtrigger

# Có thể bật LiveReload cho môi trường phát triển.
spring.devtools.livereload.enabled=true
```

**Đây là ví dụ dành cho môi trường local, không phải production properties.**

Cấu hình này có ý nghĩa:

1. Java/classes thay đổi và được compile vào classpath → được theo dõi nhưng chờ trigger file để xét restart.
2. Static resources mặc định bị loại khỏi full restart → có thể LiveReload hoặc thấy thay đổi sau refresh khi output được cập nhật.
3. Files trong `generated/**` và tệp `*.tmp` theo policy cũng không bắt full restart.
4. `../local-dev-watch` được theo dõi dù không phải classpath; muốn restart do thay đổi cần đáp ứng trigger-file policy.
5. Chạm trigger file trên classpath → Devtools kiểm tra những thay đổi có ý nghĩa; nếu có, restart context.

### 6.1. Bảng dự đoán

| Thao tác khi app đang chạy | Đã cập nhật nơi được theo dõi? | Đã cập nhật trigger? | Kết quả cần quan sát |
| --- | --- | --- | --- |
| Chỉ sửa `.java` rồi chưa compile | Chưa có `.class` mới | Chưa | Thường không restart |
| Sửa `.java`, Maven compile | Có | Chưa | Chờ trigger |
| Sửa `.java`, compile, rồi cập nhật trigger classpath | Có | Có | Restart nếu có thay đổi thực cần restart |
| Sửa static file và copy resources | Có | Không | Không full restart theo defaults; LiveReload có thể có |
| Chỉ cập nhật trigger khi không có thay đổi khác | Trigger thay đổi | Có | Chỉ kiểm tra; không bảo đảm restart |
| Sửa `../local-dev-watch/marker.txt` | Có, qua additional-paths | Chưa | Có thể đợi trigger |
| Sửa file ngoài classpath không có trong additional-paths | Không | Có | Không restart chỉ vì file ngoài được sửa |
| Tắt Devtools restart hoàn toàn | Watcher không hoạt động bình thường | Có | Không được kỳ vọng auto-restart |

Bảng nêu cơ chế phổ biến của Spring Boot 3.3. Kết quả LiveReload cụ thể phụ thuộc browser extension, việc copy resources, matcher, trạng thái watcher và build/IDE.

## 7. Dự án mẫu Java 21 + Spring Boot 3.3.13

Dự án dùng Maven với hai lớp Java và vài resources. App có `GET /hello` trả `v1`; mỗi lần application context hoàn tất startup thành công sẽ in một mốc `DEMO READY at ...` để quan sát restart.

### 7.1. Cấu trúc dự án

```text
devtools-watch-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/devtools/
    │   │   ├── DevtoolsWatchApplication.java
    │   │   └── StatusController.java
    │   └── resources/
    │       ├── application.properties
    │       ├── .reloadtrigger
    │       └── static/
    │           └── message.txt
    └── test/
        └── java/com/example/devtools/
            └── StatusControllerTest.java

# Nằm ngoài project, tạo trước khi chạy:
../local-dev-watch/marker.txt
```

### 7.2. Maven pom.xml

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
    <artifactId>devtools-watch-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-devtools</artifactId>
            <scope>runtime</scope>
            <optional>true</optional>
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
            </plugin>
        </plugins>
    </build>
</project>
```

`runtime` bảo đảm Devtools có mặt lúc chạy phát triển, không phải thư viện để compile business code. `optional=true` tránh truyền dependency Devtools transitively sang project phụ thuộc vào module này.

**Quan trọng:** Spring Boot Maven repackaging mặc định loại `spring-boot-devtools` khỏi executable JAR; khi chạy `java -jar` bản đóng gói, Devtools thường bị vô hiệu hóa theo production-mode detection. Để thực hành restart, dùng `mvn spring-boot:run` hoặc IDE run có exploded classes, không dựa vào `java -jar target/...jar`.

### 7.3. DevtoolsWatchApplication.java

Tệp `src/main/java/com/example/devtools/DevtoolsWatchApplication.java`:

```java
package com.example.devtools;

import java.time.Instant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class DevtoolsWatchApplication {

    public static void main(String[] args) {
        SpringApplication.run(DevtoolsWatchApplication.class, args);
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("DEMO READY at " + Instant.now());
    }
}
```

Event handler trong bean được Spring quản lý sẽ được gọi khi Boot công bố `ApplicationReadyEvent`. Một lần restart Devtools tạo context mới và phát chuỗi startup events mới; log có thể xuất hiện nhiều lần với timestamp khác nhau. **Timestamp là động**, nên không cố ghi nguyên một ngày/giờ làm expected output.

Mốc ready này cho phép quan sát **application context startup/restart**, không chứng minh mọi external dependency hoặc async work của một ứng dụng production đã healthy.

### 7.4. StatusController.java

Tệp `src/main/java/com/example/devtools/StatusController.java`:

```java
package com.example.devtools;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {

    @GetMapping("/hello")
    public String hello() {
        return "v1";
    }
}
```

Sau này bạn chỉ cần đổi `"v1"` thành `"v2"`, compile vào classpath và cập nhật trigger. Nếu restart xảy ra, lần gọi `GET /hello` mới sẽ trả `v2`.

### 7.5. application.properties

Tệp `src/main/resources/application.properties`:

```properties
spring.application.name=devtools-watch-demo
server.port=8080
spring.devtools.restart.additional-exclude=generated/**,**/*.tmp
spring.devtools.restart.additional-paths=../local-dev-watch
spring.devtools.restart.trigger-file=.reloadtrigger
spring.devtools.livereload.enabled=true
```

Lưu ý: trong project này ta **không đặt `spring.devtools.restart.exclude`** để giữ các exclusions mặc định. Nếu muốn thử ghi đè, hãy đặt property ấy trong một lần thử riêng rồi so sánh behavior.

### 7.6. .reloadtrigger

Tệp `src/main/resources/.reloadtrigger`:

```text
initial
```

Nội dung là text bất kỳ; phần quan trọng là **tên file đúng với property** và **file xuất hiện trên runtime classpath**. Không cần tạo một Java class cho marker.

### 7.7. message.txt

Tệp `src/main/resources/static/message.txt`:

```text
static-v1
```

Tệp static này được Spring Boot web app phục vụ tại `GET /message.txt`. Thử sửa thành `static-v2`, copy resources vào output rồi refresh trình duyệt; đây là trường hợp giúp phân biệt cập nhật tài nguyên tĩnh với restart toàn context.

### 7.8. Tạo thư mục theo dõi bổ sung

Trong thư mục `devtools-watch-demo`, trên Bash/zsh:

```bash
mkdir -p ../local-dev-watch
printf 'marker-v1\n' > ../local-dev-watch/marker.txt
```

Hoặc PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path ../local-dev-watch
Set-Content -Path ../local-dev-watch/marker.txt -Value 'marker-v1'
```

Thư mục tồn tại **trước lần khởi động đầu**. Relative path chỉ đúng khi working directory là project; chạy từ IDE có thể cần đổi working directory cho phù hợp.

## 8. Chạy demo và kiểm tra ba cơ chế

### 8.1. Chuẩn bị output classpath

Trong project, sử dụng terminal A:

```bash
java -version
mvn -version
mvn -q compile
mvn spring-boot:run
```

Khi chạy, Maven plugin chuẩn sẽ sử dụng classes/resources của project thay vì bản executable JAR đã repackaged. Chờ ứng dụng khởi động; trong console bạn sẽ thấy một mốc dạng:

```text
DEMO READY at 2026-01-01T00:00:00Z
```

Đây là **mẫu định dạng**, không phải timestamp cố định. Khi chạy thực tế, thời gian do `Instant.now()` quyết định.

Trong terminal B:

```bash
curl -sS http://localhost:8080/hello
curl -sS http://localhost:8080/message.txt
```

Hai response bodies lần đầu tương ứng:

```text
v1
static-v1
```

Hai kết quả này là **hai request riêng**, không phải một response có hai dòng. `curl` có thể in chung liền nhau nếu bạn chạy hai lệnh mà không thêm newline; kiểm tra từng lệnh khi cần.

### 8.2. Đảm bảo trigger file đã có trên classpath

Với Maven, sau `mvn compile`, đường dẫn được kỳ vọng:

```text
target/classes/.reloadtrigger
```

Có thể kiểm tra bằng Bash:

```bash
test -f target/classes/.reloadtrigger && echo present
```

hoặc PowerShell:

```powershell
Test-Path target/classes/.reloadtrigger
```

Nếu `false`/không tồn tại, đừng tiếp tục giả định trigger file hiệu lực. Hãy đảm bảo Maven resources đã copy file từ `src/main/resources`, xác minh đường dẫn output classpath của JVM đang chạy và build lại khi cần.

### 8.3. Thử sửa Java khi chưa cập nhật trigger

Khi ứng dụng đang chạy tại terminal A:

1. Mở `StatusController.java`.
2. Đổi `return "v1";` thành `return "v2";`.
3. Biên dịch class mới ở terminal B:

```bash
mvn -q compile
```

4. Quan sát log ở terminal A và gọi lại `GET /hello`.

Trong cấu hình trigger file của demo, thay đổi classpath đã được ghi nhận, nhưng Devtools **chờ cập nhật marker để xét restart**. Vì thế ứng dụng vẫn có thể tiếp tục phục vụ code cũ `v1` cho tới khi marker được cập nhật.

**Điểm có thể gây nhầm:** hệ thống live/hot-reload khác (IDE hot swap, JRebel hoặc một plugin đặc biệt) có thể cập nhật method body mà không cần Spring restart. Nếu môi trường có những công cụ đó, tắt chúng trong thí nghiệm để chỉ quan sát Devtools.

### 8.4. Chủ động kích hoạt restart check

Sau khi biên dịch Java và đảm bảo `target/classes/.reloadtrigger` tồn tại, tại terminal B trên Bash:

```bash
printf '\ntrigger %s\n' "$(date +%s)" >> src/main/resources/.reloadtrigger
mvn -q resources:resources
```

Lệnh đầu cập nhật source marker; lệnh Maven thứ hai đưa marker mới vào output classpath. Khi Devtools đã nhận thấy `.class` thay đổi và marker được cập nhật, nó có thể thực hiện restart. Quan sát console: một mốc `DEMO READY at ...` mới có thể xuất hiện.

Một cách chẩn đoán nhanh hơn **chỉ dùng trong demo local** là sửa trực tiếp tệp marker trong classpath output:

```bash
printf '\ncheck-now\n' >> target/classes/.reloadtrigger
```

Nhưng thay đổi trong `target/classes` có thể bị ghi đè khi build tiếp theo; bình thường nên chỉnh source rồi dùng IDE/Maven copy resources.

Sau khi restart hoàn tất:

```bash
curl -sS http://localhost:8080/hello
```

Kỳ vọng response body:

```text
v2
```

Đây là kiểm chứng đồng thời rằng code Java mới đã được compile, trigger hoạt động và application context mới đang phục vụ.

### 8.5. Thử static resource không full restart

Đổi nội dung `src/main/resources/static/message.txt` từ `static-v1` sang `static-v2`, sau đó:

```bash
mvn -q resources:resources
curl -sS http://localhost:8080/message.txt
```

Khi classpath output được cập nhật và cơ chế phục vụ static resources không cache bản cũ, kết quả có thể là:

```text
static-v2
```

Nhờ default `static/**` exclusion, thay đổi resource này **không yêu cầu full Spring context restart**. Một LiveReload client có thể giúp browser tự refresh; nếu không có client, refresh thủ công. Với trigger file, không nên suy luận rằng chỉ vì file tĩnh đã đổi thì phải xuất hiện một `DEMO READY` mới.

Nếu static file vẫn là `static-v1`, kiểm tra copy resources, cache/browser, classpath output và proxy, trước khi sửa policy excludes.

### 8.6. Thử additional-paths

Sửa tệp bên ngoài project:

```bash
printf 'marker-v2\n' > ../local-dev-watch/marker.txt
```

Tại đây Java class và static resource có thể chưa đổi. Khi trigger-file đang bật, **đừng mong một lần sửa external marker phải restart ngay lập tức**. Sau khi update trigger file trên classpath, Devtools kiểm tra các changes đang chờ:

```bash
printf '\ncheck-external\n' >> target/classes/.reloadtrigger
```

Quan sát console để xem lần thay đổi ở `../local-dev-watch` có làm context restart không. Nếu không, kiểm tra working directory, sự tồn tại của thư mục, đường dẫn watcher thật, exclusions, timing của scanner và lần thay đổi marker; đừng suy luận `additional-paths` tự đưa tệp thành bean/config.

Một phép thử chuẩn hơn là thêm một lần update khác cho external marker rồi cập nhật trigger file sau khi IDE/build đã ổn định, để tránh hai thay đổi chồng lên khoảng quét của watcher.

### 8.7. Thử additional-exclude

Tạo một tài nguyên kiểu generated dưới classpath resources (nếu chưa có):

```bash
mkdir -p src/main/resources/generated
printf 'report-v1\n' > src/main/resources/generated/report.txt
mvn -q resources:resources
```

Khi có `spring.devtools.restart.additional-exclude=generated/**,**/*.tmp` và trigger file, sửa lại `report.txt`, copy vào classpath output rồi cập nhật trigger để xét restart. Kỳ vọng thay đổi thuộc nhóm đã exclude **không cần full restart**, trong khi có thể LiveReload tùy môi trường.

**Không dùng trường hợp này để chứng minh code Java không restart**: một file `generated/report.txt` là resource không ảnh hưởng bean instantiation. Muốn chứng minh full restart, sửa `StatusController.java` như mục 8.3.

### 8.8. PowerShell tương đương trên Windows

Nếu dùng Windows PowerShell, sau khi chỉnh `StatusController.java` và biên dịch:

```powershell
mvn -q compile

Add-Content -Path src/main/resources/.reloadtrigger -Value ("trigger " + (Get-Date).ToString("O"))
mvn -q resources:resources

Invoke-RestMethod http://localhost:8080/hello
```

Trong cấu hình Maven mặc định, trigger source cần được copy vào output. Nếu build/IDE sử dụng một output folder khác, cập nhật đúng tệp nằm **trên runtime classpath** thay vì đoán `target/classes` trong mọi tình huống.

## 9. Kiểm thử JUnit phần ứng dụng

JUnit có thể kiểm tra controller, context và request mapping. Nhưng một `@SpringBootTest` bình thường **không chứng minh** Devtools file-watcher/restart hoạt động với IDE, classpath output hoặc trigger file trong một tiến trình chạy liên tục. Nhiều test runners còn tắt Devtools restart theo cơ chế test.

### 9.1. StatusControllerTest.java

Tệp `src/test/java/com/example/devtools/StatusControllerTest.java`:

```java
package com.example.devtools;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class StatusControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void helloReturnsVersionOne() throws Exception {
        mvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("v1"));
    }
}
```

Chạy khi `StatusController.java` còn trả `v1`:

```bash
mvn test
```

Test này kiểm tra HTTP controller wiring mà không cần mở port thật. Nếu đã sửa controller thành `v2` cho thí nghiệm restart, cập nhật expected string trong test tương ứng hoặc hoàn nguyên source rồi chạy test.

**Không** coi test MockMvc thành phép kiểm tra thay thế cho Devtools watcher: một unit/integration test mới chỉ chạy context ở test process, không kiểm tra cơ chế “file đổi → compile → trigger → restart” khi app đang chạy.

### 9.2. Kịch bản kiểm thử restart đáng tin

Để xác minh Devtools có hoạt động, dùng một kiểm thử tiến trình dài hạn (thủ công hoặc tự động hóa tích hợp có kiểm soát):

1. Khởi động qua `mvn spring-boot:run` hoặc IDE run với exploded classes.
2. Ghi thời điểm/mốc `DEMO READY` đầu.
3. Thay đổi code `v1` → `v2`.
4. Compile và xác minh output classpath được cập nhật.
5. **Không** chạm trigger, quan sát context chưa restart vì thay đổi đó.
6. Cập nhật trigger trên output classpath.
7. Quan sát mốc `DEMO READY` mới và HTTP trả `v2`.
8. Thử static resource riêng, xác minh không cần full restart.
9. Thử external folder với additional-paths.
10. Đưa project về nguồn ban đầu sau thí nghiệm.

Không dùng `Thread.sleep(500)` tùy tiện rồi cho rằng restart hoàn tất; nếu tự động hóa, poll readiness/HTTP response với **deadline hữu hạn** và kiểm chứng timestamp/event đủ rõ. Thời gian debounce/scan của file watcher và tốc độ CPU/IDE có thể thay đổi.

## 10. Ghi đè excludes và thêm excludes: trường hợp trước/sau

### 10.1. Không đặt gì

```properties
# Không có restart.exclude hay additional-exclude.
```

Default groups như static/public/templates được loại khỏi full restart.

### 10.2. Chỉ đặt exclude

```properties
spring.devtools.restart.exclude=static/**,public/**
```

Giờ `templates/**` **không còn nhất thiết** là default exclusion. Điều này có thể gây restart khi sửa template mà trước đó chỉ cần LiveReload.

### 10.3. Thêm additional-exclude

```properties
spring.devtools.restart.additional-exclude=generated/**,**/*.tmp
```

Default exclusion vẫn được giữ, rồi thêm nhóm generated/temp.

### 10.4. Đặt cả hai

```properties
spring.devtools.restart.exclude=static/**,public/**
spring.devtools.restart.additional-exclude=generated/**
```

Tập policy bắt đầu từ `static/**,public/**`, rồi bổ sung `generated/**`. Đừng nhầm dòng `additional-exclude` sẽ âm thầm khôi phục `templates/**`.

### 10.5. Khi nào loại trừ một file là sai?

Ví dụ `src/main/resources/application.properties` chứa:

```properties
my.feature.enabled=false
```

Nếu một custom service đọc property ở bean initialization, thay đổi property rồi **loại trừ nó khỏi restart** có thể khiến service vẫn giữ giá trị cũ. Không được coi file config quan trọng giống một file ảnh tĩnh chỉ phục vụ trực tiếp cho browser.

**Tiêu chí chọn:** chỉ exclude những file mà việc thay đổi **không yêu cầu tái tạo ApplicationContext/beans** để có hiệu lực. Các file ảnh, CSS, template được engine hỗ trợ reload thích hợp; các file khởi tạo cấu hình và `.class` thường không nên exclude bừa bãi.

## 11. Devtools restart không phải production hot deployment

### 11.1. Devtools mặc định không chạy từ executable JAR đóng gói

Với Maven plugin, executable archives thường **không chứa Devtools**. Spring Boot còn có detection cho ứng dụng chạy bằng `java -jar`: nó xem đó là production-like launch và tắt Devtools theo mặc định.

Do đó, một quy trình sai để test đề bài là:

```bash
mvn package
java -jar target/devtools-watch-demo-0.0.1-SNAPSHOT.jar
# Sửa Java và mong JAR tự restart như IDE.
```

Bạn đang chạy một artifact đóng gói; lớp trong JAR không tự thay thế chỉ vì source files được lưu. Để test file-watcher, chạy `mvn spring-boot:run` hoặc IDE run trong môi trường development.

### 11.2. Không bật lại Devtools bằng system property ở production

Có cách buộc Devtools hoạt động ngay cả ở classloader khác, nhưng tài liệu Spring Boot cảnh báo rủi ro bảo mật khi bật nó ở production. Đừng dùng giải pháp đó để thay rolling deployment/blue-green release.

Devtools có các tính năng development-time defaults và LiveReload; chúng không được xem như hardening, cluster deployment hoặc secret management.

### 11.3. Restart tạo lại context, không bảo toàn mọi in-memory state

Một request, scheduled job hay stream đang xử lý có thể chịu ảnh hưởng nếu Devtools restart context. Khi phát triển, cần kiểm tra việc context cũ cleanup đúng: `@PreDestroy`, `SmartLifecycle.stop` và shutdown hooks. Devtools dựa vào Spring application context shutdown hook cho cơ chế restart; nếu vô hiệu hóa hook, restart có thể không hoạt động đúng.

Không dùng Devtools restart để thử kỹ thuật đảm bảo xử lý đúng một lần trong production. Với job quan trọng cần transaction, outbox/queue và retry/idempotency.

## 12. Phân biệt file-watching với restart classloader customization

Có hai nhóm cấu hình cùng chứa chữ `exclude` nhưng giải quyết **bài toán khác nhau**.

### 12.1. Excluding watched resource changes

```properties
spring.devtools.restart.additional-exclude=generated/**
```

Thuộc namespace application properties. Ý nghĩa: thay đổi của resource phù hợp **không buộc full restart** theo policy.

### 12.2. Tùy chỉnh base/restart classloader

Tệp `META-INF/spring-devtools.properties` có thể chứa entries kiểu `restart.include.*` và `restart.exclude.*` để đưa **classpath entries/JARs** qua base hoặc restart classloader. Những pattern này là **regular expressions** áp dụng lên classpath entries, **không phải** các file watcher exclusion patterns bên trên.

Ví dụ minh họa (không cần thêm vào demo):

```properties
restart.include.project-common=.*/project-common-[^/]+\.jar
```

Đây chỉ là ví dụ cú pháp regex trong `spring-devtools.properties`, **không** được copy vào `application.properties` rồi hy vọng nó hoạt động như `spring.devtools.restart.additional-exclude`.

Khi gặp `ClassCastException`, reflection mismatch hoặc lỗi deserialize vì hai classloaders, trước tiên xác minh restart là nguyên nhân, sau đó mới tìm cách tùy biến classloader. Không thêm regex include/exclude không cần thiết cho một bài toán chỉ là static file reload.

## 13. Điều chỉnh file watcher khi môi trường build chậm

Khi IDE build/copy hàng loạt tệp trong vài giây, Devtools có thể thấy nhiều đợt changes. Mục tiêu là tránh restart khi output chưa ổn định.

Một số cấu hình chuyên sâu của Devtools:

```properties
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
```

Đây là **ví dụ điều chỉnh**; hãy chọn thời gian có lý do. Poll interval ảnh hưởng tần suất kiểm tra thay đổi, quiet period là khoảng tĩnh cần có để tránh restart giữa đợt copy đang diễn ra.

Nếu quiet period quá ngắn so với thời gian Maven/IDE copy resources, ứng dụng có thể restart khi vẫn còn tệp chưa được đồng bộ. Nếu quá dài, restart chậm gây khó chịu. Dùng trigger file có thể giảm số lần restart do IDE auto-build, nhưng vẫn cần quan sát behavior thực tế trên hệ thống file và build tool đang dùng.

**Không cố sửa mọi tình trạng không restart bằng tăng poll interval**: phải kiểm tra Devtools đã được kích hoạt, classpath có thực đổi, trigger file tồn tại, policy excludes và output path chính xác trước.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Sửa `.java`, app không restart | Chưa biên dịch `.class` mới | IDE Build / `mvn compile` |
| Compile rồi vẫn không restart | Trigger file đang bật nhưng chưa đổi | Cập nhật marker nằm trên classpath |
| Chạm marker nhưng không restart | Không có thay đổi cần restart hoặc file không vào output | Kiểm tra compiled classes, exclusions, target/classes marker |
| Static CSS đổi mà toàn context restart | Đã ghi đè defaults bằng `restart.exclude` quá hẹp | Dùng `additional-exclude` thay vì exclude nếu chỉ thêm |
| File ngoài classpath không tạo restart | Không nằm trong additional-paths hoặc path sai relative to working dir | Kiểm tra actual path, quyền và file watcher |
| Thêm additional-paths nhưng file không được Java đọc | Watcher không tự thêm file vào classpath/config | Định nghĩa cách load file riêng |
| Không thấy LiveReload | Chưa có LiveReload browser client, file output chưa đổi, LiveReload server không hoạt động | Kiểm tra extension/network/refresh thủ công |
| Static file vẫn là bản cũ | IDE/Maven chưa copy resource hoặc browser cache | Copy resources và kiểm tra output, refresh/cache |
| `java -jar` không tự restart | Devtools disabled trong packaged app | Dùng Maven run/IDE dev launch |
| Test `@SpringBootTest` chạy nhưng restart vẫn lỗi | Test không kiểm tra watcher trong process lâu dài | Test restart qua process thực với deadline |
| Devtools restart liên tục | Thư mục được watch chứa generated/logs liên tục thay đổi | Loại trừ chính xác hoặc thu hẹp additional-paths |
| Biến cấu hình không cập nhật khi exclude | Bean chỉ đọc file lúc startup | Không exclude config đó; restart hợp lý |
| Trigger chỉ có trong `src/main/resources` | Chưa được copy vào runtime classpath | `mvn resources:resources` / kiểm tra output |
| File trigger name có cả path | Property nhận filename, không phải source path | `spring.devtools.restart.trigger-file=.reloadtrigger` |
| Multi-module ClassCastException sau restart | Class được nạp ở base/restart classloader không phù hợp | Chẩn đoán classloader, tùy chỉnh spring-devtools.properties khi cần |
| Tắt shutdown hook | Devtools restart không đóng context đúng | Khôi phục hook hoặc xem xét cơ chế quản lý lifecycle |
| Không biết có restart thật hay không | Chỉ nhìn browser refresh | Quan sát `ApplicationReadyEvent` hoặc lifecycle log |
| Trigger file restart khi không có code change | Có thể có thay đổi khác đã được watcher ghi nhận | Kiểm tra watched directories, generated files, logging |
| Excludes quá rộng | Bean/config mới không có hiệu lực | Giới hạn pattern, test từng nhóm |
| Đem devtools vào production | Rủi ro bảo mật và vận hành | Tách development-only runtime |

### 14.1. Checklist chẩn đoán

1. `spring-boot-devtools` đã có trong **runtime** classpath dev launch chưa?
2. Ứng dụng đang chạy từ IDE/`mvn spring-boot:run` hay bản `java -jar` đóng gói?
3. Có tắt restart qua `spring.devtools.restart.enabled=false` hoặc system property không?
4. Source file đã được biên dịch/copy thành file trên classpath chưa?
5. Output classpath thực là `target/classes` hay một thư mục khác?
6. File bị sửa có thuộc default exclude patterns không?
7. Có đặt `restart.exclude` khiến defaults bị ghi đè ngoài ý muốn không?
8. Có nên dùng `restart.additional-exclude` thay cho `exclude`?
9. `additional-paths` có trỏ đúng folder tồn tại và đúng working directory?
10. Thư mục ngoài classpath có được watcher thấy thay đổi thật không?
11. `trigger-file` có chỉ là **filename**?
12. Marker có tồn tại trong runtime classpath và đã được cập nhật chưa?
13. Khi trigger thay đổi, có thay đổi **cần restart** đang chờ không?
14. Maven/IDE có làm thay đổi output trong nhiều đợt vượt quiet period?
15. LiveReload client và browser refresh có đang bị nhầm với context restart?
16. Có generated/logs/cache directories làm watcher hoạt động quá thường xuyên?
17. Có JRebel/AspectJ instrumentation hoặc classloader incompatibility?
18. Spring shutdown hook có còn được đăng ký?
19. Có log `DEMO READY` mới sau thao tác không?
20. Thử cùng quy trình trên một demo nhỏ có giảm được yếu tố gây nhiễu không?

## 15. Bài tập thực hành

1. Giải thích sự khác nhau giữa lưu `.java` và cập nhật `.class` trên classpath.
2. Nêu sáu nhóm thư mục Devtools mặc định không buộc full restart.
3. So sánh `spring.devtools.restart.exclude` và `spring.devtools.restart.additional-exclude`.
4. Vì sao đặt `restart.exclude=static/**,public/**` có thể làm template thay đổi gây restart?
5. Chọn policy cho một dự án có static CSS, Thymeleaf templates và generated JSON.
6. Giải thích vì sao loại trừ watcher không loại tệp khỏi executable JAR.
7. Tạo folder `../local-dev-watch` ngoài project và cấu hình additional-paths.
8. Vì sao watcher thấy tệp ngoài classpath không có nghĩa Spring tự nạp file vào Environment?
9. Tạo marker `.reloadtrigger` trong `src/main/resources` và cấu hình trigger-file đúng.
10. Tại sao trigger-file property cần tên tệp, không phải đường dẫn source?
11. Vì sao phải đảm bảo marker đã được copy vào `target/classes`?
12. Sau khi đổi controller v1 → v2, compile nhưng chưa chạm trigger, bạn kỳ vọng điều gì?
13. Chạm trigger sau compile; kiểm tra điều gì chứng minh context đã restart?
14. Chỉ sửa một file `static/message.txt` và copy output; có phải restart context không?
15. Khi không có thay đổi cần restart, chạm trigger có bắt buộc restart không?
16. Thử đường dẫn ngoài classpath với additional-paths và trigger; ghi lại quan sát.
17. Vì sao đặt thêm cả thư mục `target` vào additional-paths thường không tốt?
18. Viết một JUnit MockMvc test cho `GET /hello` và giải thích vì sao test ấy không chứng minh file watching.
19. Đặt hai loại excludes để giữ default policy nhưng tránh `generated/**` và `*.tmp`.
20. Khi bật JRebel, restart của Devtools có tương tác thế nào?
21. Khi dùng `mvn spring-boot:run`, vì sao cần plugin chạy với forking phù hợp?
22. Nêu một tình huống mà browser LiveReload thành công nhưng Spring context chưa restart.
23. Phân biệt `spring.devtools.restart.additional-exclude` với `restart.exclude.X` trong `META-INF/spring-devtools.properties`.
24. Nếu app chạy được nhưng chỉ `java -jar` không restart, đâu là nguyên nhân hợp lý?
25. Thiết kế quy trình test restart có deadline, không sử dụng `Thread.sleep` như bằng chứng completion.
26. Vì sao không bật Devtools production để tự hot-deploy khi có thay đổi source?
27. Nếu watcher restart liên tục do file log, bạn sẽ sửa policy và directory scope thế nào?
28. Giải thích ảnh hưởng của `poll-interval` và `quiet-period` khi IDE copy files chậm.
29. Nếu một resource bị exclude nhưng bean chỉ đọc resource lúc khởi tạo, khi nào giá trị mới có hiệu lực?
30. Xây một ma trận test cho Java class change, static file change, additional-path change và trigger-only change.

**Tiêu chí đạt:** cấu hình đúng `exclude`/`additional-exclude`, `additional-paths` và `trigger-file` trên Spring Boot 3.3; chạy được Maven demo; chứng minh restart chỉ sau khi classpath cập nhật và trigger được thay đổi; phân biệt LiveReload với full restart; tránh đưa Devtools vào production.

## 16. Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Developer Tools: https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html
- Spring Boot 3.3 — Automatic Restart, Excluding Resources, Watching Additional Paths, Using a Trigger File: https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html#using.devtools.restart
- Spring Boot 3.3 — Devtools application properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html
- Spring Boot 3.3 — Maven plugin, Running Your Application: https://docs.spring.io/spring-boot/3.3/maven-plugin/run.html
- Spring Framework 6.1 — ApplicationReadyEvent (Spring Boot API): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
