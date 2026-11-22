# Đóng gói, phạm vi development-only và kiểm tra artifact triển khai

Trong quá trình phát triển Spring Boot, ứng dụng thường chạy thành công bằng IDE hoặc các lệnh `spring-boot:run`, `bootRun`. Tuy nhiên, điều đó **chưa chứng minh artifact được đóng gói có thể triển khai thành công**. Một ứng dụng có thể chạy tốt trên máy lập trình viên vì IDE cung cấp classpath, dependency và biến môi trường, nhưng khi chuyển thành JAR, WAR hoặc container image lại gặp lỗi thiếu thư viện, sai phiên bản Java, không tìm thấy resource, lộ cấu hình nội bộ hoặc mang theo công cụ chỉ dành cho development.

Bài học **“Đóng gói, phạm vi development-only và kiểm tra artifact triển khai”** thuộc **Spring Boot Fundamentals → Công cụ phát triển** tập trung vào ba vấn đề liên quan chặt chẽ:

1. **Đóng gói:** biến mã nguồn, resource và dependency cần thiết thành đầu ra có thể chạy trong môi trường mục tiêu.
2. **Tách development-only:** giữ công cụ hỗ trợ lập trình, test và build ra khỏi runtime artifact khi chúng không cần thiết cho production.
3. **Kiểm tra artifact thực tế:** kiểm tra chính file sẽ được phát hành, không chỉ dựa vào kết quả chạy từ source.

Mục tiêu là hiểu được nguyên tắc và thao tác với cả **Maven** và **Gradle**, đồng thời xây dựng thói quen kiểm tra đúng những gì sẽ được đưa lên server hoặc container.

## 1. Artifact triển khai là gì?

**Artifact** là đầu ra của quá trình build có thể được lưu trữ, chuyển giao và sử dụng ở bước tiếp theo của quy trình triển khai.

Với Spring Boot, các artifact thường gặp gồm:

| Artifact | Mục đích | Điểm cần lưu ý |
|---|---|---|
| Executable JAR | Chạy ứng dụng bằng `java -jar` | Chứa code ứng dụng, resource và thư viện runtime theo cách đóng gói của Boot |
| Executable WAR | Chạy bằng `java -jar` hoặc triển khai theo mô hình servlet container phù hợp | Cấu trúc và dependency khác JAR; cần cấu hình đúng |
| Plain JAR | Thư viện hoặc JAR thông thường | Không mặc nhiên có đủ runtime dependency và launcher để chạy độc lập |
| Container image | Chứa artifact cùng runtime OS/JVM và cấu hình image | Cần kiểm tra cả JAR lẫn cách image khởi động |
| Native executable | Chương trình tạo bằng quy trình native image riêng | Không áp dụng nguyên xi cách kiểm tra nội dung executable JAR |

Trong bài này, **executable JAR** là trường hợp chính vì đây là cách phổ biến để triển khai nhiều ứng dụng Spring Boot.

Một artifact có thể là file hợp lệ nhưng **chưa chắc deploy được**. Có ít nhất bốn lớp kiểm tra khác nhau:

~~~text
Mã nguồn build thành công?
          |
          v
Artifact đúng cấu trúc và đủ dependency?
          |
          v
Artifact chạy được với JDK/JRE và cấu hình mục tiêu?
          |
          v
Ứng dụng thực sự sẵn sàng phục vụ chức năng cần thiết?
~~~

Mỗi bước có thể thành công hoặc thất bại độc lập. Vì vậy, quy trình phát hành nên kiểm tra tuần tự thay vì chỉ nhìn thông báo `BUILD SUCCESS`.

## 2. Từ source code đến ứng dụng được triển khai

Một dự án Spring Boot điển hình:

~~~text
src/
  main/
    java/
      com/example/orders/OrdersApplication.java
      com/example/orders/OrderService.java
    resources/
      application.yml
      templates/
        receipt.html
  test/
    java/
      com/example/orders/OrderServiceTest.java
    resources/
      fixtures/
        sample-order.json
pom.xml hoặc build.gradle
~~~

Trong quá trình build, tool thường thực hiện những việc như:

1. Giải quyết plugin và dependency.
2. Compile mã nguồn ứng dụng.
3. Xử lý các resource cần đưa vào runtime.
4. Compile và chạy test theo lifecycle/tác vụ đã chọn.
5. Tạo archive.
6. Với plugin Spring Boot, **repackage** hoặc tạo executable archive có launcher cùng các thư viện cần chạy.
7. Đưa artifact ra thư mục build để pipeline phát hành sử dụng.

Sơ đồ:

~~~text
src/main/java --------> compile ------+
                                      |
src/main/resources -------------------+--> classes/resources
                                      |
runtime dependencies -----------------+
                                      |
                                      v
                             Spring Boot packaging
                                      |
                                      v
                              executable JAR/WAR
                                      |
                                      v
                         deploy / java -jar / image
~~~

`src/test/java` và `src/test/resources` tham gia quá trình test, nhưng **không nên bị đóng gói như thành phần ứng dụng production** trong cấu hình thông thường.

Một điểm dễ nhầm: build có thể tạo **nhiều file JAR**. Chúng có thể không có cùng khả năng chạy hoặc cùng danh sách dependency. Cần biết chính xác file nào là executable artifact được đưa đi deploy.

## 3. Spring Boot executable JAR khác plain JAR thế nào?

Một JAR Java thông thường có thể chứa class và resource nhưng không chứa tất cả dependency cần thiết. Nếu cần nhiều thư viện, người chạy có thể phải tự thiết lập classpath.

Spring Boot executable JAR được thiết kế để chạy theo cách đơn giản:

~~~bash
java -jar orders-api.jar
~~~

Trong cấu trúc thường gặp của Spring Boot:

~~~text
orders-api.jar
|
+-- META-INF/
|    +-- MANIFEST.MF
|
+-- BOOT-INF/
|    +-- classes/
|    |    +-- com/example/orders/OrdersApplication.class
|    |    +-- application.yml
|    |    +-- templates/receipt.html
|    |
|    +-- lib/
|         +-- spring-boot-*.jar
|         +-- spring-context-*.jar
|         +-- ...
|
+-- org/springframework/boot/loader/
     +-- ... các lớp launcher ...
~~~

Chi tiết launcher và vị trí cụ thể của một số file có thể thay đổi theo phiên bản Spring Boot, nhưng vai trò chính vẫn là:

- **`BOOT-INF/classes`:** class và resource của ứng dụng.
- **`BOOT-INF/lib`:** các JAR dependency runtime được đóng kèm.
- **Manifest và launcher:** thông tin để `java -jar` kích hoạt ứng dụng với cấu trúc dependency của Boot.

### Manifest quan trọng thế nào?

Trong executable JAR thường có manifest chứa những trường như:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.orders.OrdersApplication
~~~

Đây là một ví dụ cho các phiên bản có launcher package như trên; không nên hardcode tên launcher như quy định bất biến cho mọi phiên bản Spring Boot.

**Main-Class** trỏ tới launcher hoặc entry point mà JVM gọi. **Start-Class** trỏ tới class ứng dụng Spring Boot khi dùng cơ chế đóng gói tương ứng.

Nếu một JAR báo lỗi:

~~~text
no main manifest attribute
~~~

có thể bạn đang chạy **plain JAR** thay vì executable JAR, hoặc cấu hình packaging chưa tạo manifest đúng.

### Không phải mọi dependency đều được bỏ vào BOOT-INF/lib

Chỉ những dependency phù hợp với runtime packaging mới nên có mặt. Ví dụ, thư viện test như JUnit không cần có trong JAR production, annotation processor không cần chạy trong process production, và devtools nên được loại khỏi artifact triển khai.

Vì vậy, kiểm tra JAR không chỉ là “có các class ứng dụng” mà còn là “có đúng các dependency và không mang theo các thành phần không cần thiết”.

## 4. Hai cách chạy: từ source và từ artifact

Trong lúc phát triển, Maven và Gradle có các lệnh tiện dụng:

~~~bash
./mvnw spring-boot:run
~~~

~~~bash
./gradlew bootRun
~~~

Hai lệnh này chạy ứng dụng dựa trên classpath được build tool thiết lập cho tác vụ development. Các dependency development-only có thể được đưa vào classpath đó.

Còn khi phát hành, thường dùng:

~~~bash
java -jar orders-api.jar
~~~

Lần chạy này phải dựa trên **những gì thực sự nằm trong artifact** và môi trường chạy xung quanh nó.

So sánh:

| Đặc điểm | Chạy từ build tool | Chạy executable JAR |
|---|---|---|
| Mục tiêu | Phát triển, debug, thử nhanh | Mô phỏng cách deploy thực tế |
| Classpath | Do Maven/Gradle thiết lập | Launcher đọc dependency đóng gói |
| Devtools | Có thể có trong classpath development | Thông thường phải được loại khỏi archive |
| Resource | Thường từ thư mục output | Có thể nằm bên trong JAR |
| Rủi ro bị che | Dependency hoặc path có sẵn cục bộ | Phơi bày thiếu sót packaging/runtime |
| Lệnh | `spring-boot:run`, `bootRun` | `java -jar` |

**Chạy thành công với `bootRun` không bảo đảm `bootJar` sẽ chạy thành công.** Đây chính là lý do phải kiểm tra artifact sau khi đóng gói.

## 5. Đóng gói Spring Boot bằng Maven

Với dự án Maven dùng Spring Boot starter parent hoặc dependency management phù hợp, một cấu hình plugin thường gặp:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Khi sử dụng Spring Boot starter parent, execution cho mục tiêu `repackage` thường đã được cấu hình sẵn. Nếu **không dùng starter parent**, dự án có thể phải khai báo execution của plugin tường minh để bảo đảm goal `repackage` chạy sau khi tạo JAR/WAR thông thường.

Ví dụ khai báo execution khi cần:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Trong dự án cụ thể, nên chọn **một cấu hình plugin nhất quán**, tránh khai báo trùng execution không cần thiết.

### Lệnh package

Trên Linux/macOS, nếu dự án có Maven Wrapper:

~~~bash
./mvnw clean package
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd clean package
~~~

Với một dự án có cấu hình thông thường, artifact xuất hiện trong thư mục `target`:

~~~text
target/
  orders-api-0.0.1-SNAPSHOT.jar
  ...
~~~

Tên file phụ thuộc `artifactId`, `version` và `finalName` của dự án.

Sau đó chạy đúng file:

~~~bash
java -jar target/orders-api-0.0.1-SNAPSHOT.jar
~~~

Không nên lấy tên file ví dụ rồi cho rằng tên đó giống trong mọi dự án; cần xem chính thư mục `target` của project.

### spring-boot:repackage thực hiện gì?

Goal `repackage` lấy JAR/WAR của project và tổ chức lại thành archive có thể chạy theo mô hình của Spring Boot, kèm launcher và dependency phù hợp.

Với một số cấu hình Maven, build có thể giữ lại file JAR gốc dưới dạng backup như `.jar.original`. File này **không phải** artifact executable mà bạn nên chuyển cho người vận hành chỉ vì tên gần giống.

Điểm cần kiểm tra: file nào có `BOOT-INF/classes`, `BOOT-INF/lib` và manifest đúng cho mô hình `java -jar`.

### Không nhầm package với compile

~~~bash
./mvnw compile
~~~

là bước biên dịch mã nguồn, không phải sự bảo đảm rằng executable JAR đã được tạo. Muốn kiểm tra deploy artifact, phải dùng goal/lifecycle phù hợp với việc đóng gói và chỉ định **file đầu ra thực tế**.

Maven `package` thông thường cũng gắn với các giai đoạn test trước đó. Trong một quy trình CI, không nên vô tình bỏ qua test chỉ để quá trình đóng gói “xanh” nhanh hơn. Bài học này mô tả lệnh để người học thực hành, không yêu cầu chạy build hay test ở bước soạn tài liệu.

## 6. Phân biệt dependency scope trong Maven

Maven có các scope như `compile`, `runtime`, `provided` và `test`. Chúng ảnh hưởng đến classpath trong các giai đoạn khác nhau.

| Scope Maven | Dùng chủ yếu khi nào? | Cần suy nghĩ gì khi package? |
|---|---|---|
| `compile` | Dependency cần khi compile và thường cả runtime | Thông thường có mặt trong runtime archive phù hợp |
| `runtime` | Dependency không cần tại lúc compile nhưng cần khi chạy | Thông thường có mặt trong executable JAR |
| `provided` | Dependency dự kiến được môi trường cung cấp | Phụ thuộc loại archive và mô hình triển khai |
| `test` | Thư viện chỉ để compile/chạy test | Không được đưa vào executable JAR production như dependency runtime |

Ví dụ:

~~~xml
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
~~~

Khi dùng Spring Boot dependency management, phiên bản starter thường được quản lý tập trung. Không cần khai báo phiên bản rời rạc cho từng starter nếu BOM/parent đã quản lý đúng.

### Đừng nhầm optional với scope test

Trong Maven, `<optional>true</optional>` có vai trò khác với `<scope>test</scope>`.

- `test`: dependency dành cho classpath test.
- `optional`: chủ yếu thể hiện rằng dependency không nên được tự động truyền tiếp đến các dự án phụ thuộc vào artifact này. Nó **không có nghĩa** dependency tự động bị loại khỏi mọi hình thức packaging hoặc mọi cách chạy.

Vì vậy, với devtools, cần hiểu đồng thời cả phần khai báo dependency và hành vi **loại devtools khỏi archive** của Spring Boot Maven Plugin.

## 7. Đóng gói Spring Boot bằng Gradle

Trong một dự án Gradle đã cấu hình Spring Boot plugin, tác vụ quan trọng là:

~~~bash
./gradlew clean bootJar
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat clean bootJar
~~~

`bootJar` tạo executable JAR theo cơ chế của Spring Boot. Output thường nằm dưới:

~~~text
build/libs/
  orders-api-0.0.1-SNAPSHOT.jar
  ...
~~~

Để chạy:

~~~bash
java -jar build/libs/orders-api-0.0.1-SNAPSHOT.jar
~~~

Giống Maven, tên cụ thể do cấu hình project quyết định.

### bootJar khác jar

Với Spring Boot Gradle plugin, bạn có thể gặp hai task:

- **`jar`:** tạo JAR Java thông thường.
- **`bootJar`:** tạo executable JAR theo cấu trúc Spring Boot.

Ở một số dự án, cả hai task đều tạo output. Plain artifact có thể mang classifier như `plain` hoặc tên khác do cấu hình Gradle xác định.

Ví dụ thư mục:

~~~text
build/libs/
  orders-api-0.0.1-SNAPSHOT.jar
  orders-api-0.0.1-SNAPSHOT-plain.jar
~~~

Không nên chọn file bằng wildcard rồi mặc định mọi JAR trong thư mục đều tương đương nhau. Hãy xác định file nào là đầu ra của `bootJar` và dùng đúng file đó khi tạo image hay phát hành.

### Đặt tên executable JAR cố định khi cần

Trong Gradle Groovy DSL:

~~~groovy
tasks.named('bootJar') {
    archiveFileName = 'orders-api.jar'
}
~~~

Từ đó pipeline có thể tham chiếu:

~~~text
build/libs/orders-api.jar
~~~

Đặt tên ổn định giúp Dockerfile và script đơn giản, nhưng cần bảo đảm tên artifact và version vẫn được ghi nhận ở metadata hoặc hệ thống release để hỗ trợ truy xuất nguồn gốc.

### Maven package và Gradle bootJar không phải hai lệnh hoàn toàn tương đương

Maven `package` là một phase trong lifecycle, thường đi qua cả các giai đoạn test. Gradle `bootJar` là một task có dependency graph riêng; không nên mặc định chỉ gọi `bootJar` tương đương chạy toàn bộ `check` hoặc `test`.

Một pipeline Gradle thường có thể lựa chọn:

~~~bash
./gradlew clean check bootJar
~~~

Đó là ví dụ về một quy trình kiểm tra kết hợp build, không phải lệnh cần chạy ở bước soạn Markdown hiện tại.

## 8. development-only nghĩa là gì?

Một dependency **development-only** hỗ trợ lập trình và debug trên máy phát triển nhưng không phải chức năng cần có khi ứng dụng phục vụ production.

Ví dụ quen thuộc là `spring-boot-devtools`, cung cấp các tiện ích như restart trong môi trường phát triển và hỗ trợ quá trình lặp nhanh khi sửa code.

Mục tiêu của việc phân tách:

~~~text
Development:
  App classes
  Runtime libraries
  Developer tooling (devtools, ...)
  Test tooling khi chạy test
            |
            v
Production artifact:
  App classes
  Runtime libraries
  Không mang theo phần chỉ dành cho development
~~~

Khi công cụ development không cần có trong production:

- Giảm số thành phần cần quản lý và cập nhật.
- Tránh những tính năng phát triển không cần thiết tồn tại trong môi trường triển khai.
- Giảm nguy cơ khác biệt hành vi do công cụ hỗ trợ lập trình.
- Hạn chế diện tích tấn công và các cảnh báo dependency không cần thiết.
- Giúp artifact thể hiện chính xác runtime dependency của ứng dụng.

**Development-only không phải là tên chung có cùng cú pháp trong Maven và Gradle.** Cách biểu diễn phụ thuộc build tool và plugin.

## 9. spring-boot-devtools trong Gradle: developmentOnly

Khi dùng Spring Boot Gradle plugin, cách khai báo thường gặp:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    developmentOnly 'org.springframework.boot:spring-boot-devtools'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đoạn này giả định project đã cấu hình Spring Boot plugin và cơ chế quản lý phiên bản dependency phù hợp. Không nên copy riêng phần `dependencies` vào một build file thiếu plugin rồi mong mọi configuration đã có sẵn.

Ở đây:

- `implementation`: dependency cho code chính và runtime tương ứng.
- `developmentOnly`: dependency cần ở classpath development, không dành cho executable archive được đóng gói.
- `testImplementation`: dependency dùng cho việc compile và chạy test.

Một lệnh phát triển:

~~~bash
./gradlew bootRun
~~~

có thể sử dụng dependency development-only như devtools theo cách plugin Spring Boot thiết lập.

Khi đóng gói:

~~~bash
./gradlew bootJar
~~~

`spring-boot-devtools` khai báo bằng `developmentOnly` không nên xuất hiện trong executable JAR được tạo theo cấu hình thông thường.

### Vì sao không nên dùng implementation cho devtools?

Nếu đặt:

~~~groovy
implementation 'org.springframework.boot:spring-boot-devtools'
~~~

bạn đang khai báo nó như một dependency thông thường của ứng dụng, khiến ý định tách development-only không còn rõ. Một số packaging mechanism của Boot có thể vẫn có hành vi loại devtools riêng, nhưng **không nên dựa vào ngoại lệ đó để thay thế mô hình dependency đúng**.

Hãy khai báo theo đúng mục đích. Sau đó kiểm tra JAR thực tế để xác nhận việc loại trừ, không suy đoán chỉ từ build file.

## 10. spring-boot-devtools trong Maven: optional và loại khỏi repackage

Với Maven, tài liệu Spring Boot thường dùng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <scope>runtime</scope>
    <optional>true</optional>
</dependency>
~~~

Ở đây:

- `runtime`: devtools có thể tham gia classpath khi chạy ứng dụng trong quá trình phát triển.
- `optional=true`: tránh áp đặt dependency này lên các dự án khác như một dependency truyền tiếp mặc định.
- **Spring Boot Maven Plugin** có cơ chế loại `spring-boot-devtools` khỏi executable JAR/WAR được repackage theo mặc định trong cấu hình thông dụng.

Điểm cần ghi nhớ: **optional không tự đồng nghĩa “devtools không nằm trong JAR”.** Hành vi đóng gói phụ thuộc Spring Boot plugin và cấu hình của project. Nếu project không dùng repackage đúng cách, dùng plugin khác hoặc có custom assembly, phải tự kiểm tra kết quả.

### Tùy chọn excludeDevtools

Spring Boot Maven Plugin có tùy chọn điều khiển việc loại devtools khỏi archive, ví dụ:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <excludeDevtools>true</excludeDevtools>
    </configuration>
</plugin>
~~~

Thông thường đây là hành vi mặc định, nên đoạn cấu hình chủ yếu minh họa mục đích. Nếu một dự án cố ý đổi cấu hình hoặc sử dụng packaging không chuẩn, cần đọc behavior của plugin thực tế và kiểm tra file đầu ra.

### Devtools có thật sự hoạt động trong packaged application không?

Devtools được thiết kế cho phát triển, và các tính năng như automatic restart không được kỳ vọng dùng trong ứng dụng fully packaged chạy production. Nhưng **không có lý do để đưa devtools vào artifact rồi chỉ dựa vào việc tính năng của nó có thể bị vô hiệu hóa**.

Nguyên tắc tốt hơn là loại dependency không cần thiết khỏi artifact ngay từ build, và kiểm chứng sự vắng mặt đó bằng lệnh kiểm tra archive.

## 11. Phân loại dependency theo mục đích thực tế

Ngoài devtools, build thường chứa các nhóm dependency khác nhau.

| Nhu cầu | Maven điển hình | Gradle điển hình | Có nên có trong artifact production? |
|---|---|---|---|
| Web framework cần lúc chạy | `compile` mặc định | `implementation` | Có, nếu ứng dụng cần |
| JDBC driver dùng lúc chạy | `runtime` hoặc phù hợp | `runtimeOnly` | Có, nếu ứng dụng cần |
| Thư viện unit test | `test` | `testImplementation` | Không |
| Tool xử lý annotation lúc build | Cấu hình annotation processor của compiler plugin | `annotationProcessor` | Không cần ở runtime chỉ vì nó chạy lúc compile |
| API chỉ cần để biên dịch | Phụ thuộc cách tổ chức project | `compileOnly` | Không, trừ khi runtime do môi trường cung cấp theo thiết kế |
| Developer tooling | `runtime + optional` kết hợp loại devtools bởi Boot plugin | `developmentOnly` | Không nên |
| Embedded servlet container cho Boot JAR | Dependency theo starter web | Dependency runtime theo starter web | Có trong cấu hình executable JAR tương ứng |

Một dependency có thể có nhiều vai trò trong các dự án khác nhau. Không nên tự đặt `compileOnly` cho bất kỳ thư viện nào muốn “giảm kích thước JAR” nếu code thực sự cần dùng class của thư viện đó tại runtime.

### Ví dụ annotation processor

Với Gradle, một thư viện như Lombok thường được khai báo theo vai trò compile-time:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'

    testCompileOnly 'org.projectlombok:lombok'
    testAnnotationProcessor 'org.projectlombok:lombok'
}
~~~

Đoạn ví dụ giả định có cơ chế quản lý version cho Lombok. Mục tiêu là cho compiler chạy annotation processor trong build, chứ không đóng công cụ đó vào executable JAR để code production thực thi.

Không nên lấy việc Lombok “không có trong JAR” làm dấu hiệu thiếu dependency nếu annotation processor đã sinh code Java bytecode cần thiết từ lúc compile.

## 12. Development-only khác development profile

Đây là hai khái niệm dễ bị lẫn:

**Development-only dependency** là phạm vi dependency/classpath do build tool và plugin quản lý.

**Spring profile** là cơ chế chọn cấu hình và bean tại thời điểm chạy, chẳng hạn `dev`, `test` hoặc `prod`.

Ví dụ:

~~~yaml
# application-dev.yml
logging:
  level:
    com.example.orders: DEBUG
~~~

~~~yaml
# application-prod.yml
logging:
  level:
    com.example.orders: INFO
~~~

Đây là cấu hình theo profile. Chúng không tự khiến dependency `spring-boot-devtools` bị loại khỏi executable archive.

Ngược lại, khi khai báo:

~~~groovy
developmentOnly 'org.springframework.boot:spring-boot-devtools'
~~~

bạn đang phân loại dependency cho build/runtime classpath. Điều đó không tạo ra một Spring profile tên `developmentOnly` hay tự kích hoạt profile `dev`.

So sánh:

| Khái niệm | Quyết định |
|---|---|
| `developmentOnly` của Gradle | Dependency nào được dùng lúc phát triển và không đóng vào archive |
| `optional` của Maven | Dependency có truyền tiếp mặc định sang project phụ thuộc khác hay không |
| `spring.profiles.active=dev` | Bộ cấu hình/bean phù hợp với profile dev |
| `application-dev.yml` | Giá trị cấu hình chỉ được dùng khi profile phù hợp hoạt động |
| `spring-boot-maven-plugin` / `bootJar` | Cách tạo executable archive và lựa chọn dependency |

**Đặt tên profile là `prod` không tự làm artifact an toàn.** Một `application-dev.yml` chứa secret vẫn có thể được đóng vào JAR nếu nó nằm trong resources và build không có cơ chế loại phù hợp. Dù file đó không active, nội dung vẫn có thể bị trích xuất từ archive.

## 13. Tài nguyên nào được đóng gói?

Với cấu trúc project chuẩn:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  templates/invoice.html
  data/countries.json

src/test/resources/
  fixtures/test-order.json
~~~

Khi build executable JAR thông thường:

- Resource trong `src/main/resources` được đưa vào classpath của ứng dụng.
- Resource trong `src/test/resources` chủ yếu dùng cho test; thường không nằm trong production artifact.
- File trong `src/main/resources` có thể nằm bên trong `BOOT-INF/classes` thay vì là file riêng trên đĩa.

Ví dụ:

~~~text
BOOT-INF/classes/application.yml
BOOT-INF/classes/application-dev.yml
BOOT-INF/classes/templates/invoice.html
BOOT-INF/classes/data/countries.json
~~~

**Đừng dùng `new File("src/main/resources/...")` để đọc resource tại runtime.** Đường dẫn source không còn tồn tại như vậy khi JAR được chuyển sang máy chạy khác.

Khi chỉ đọc tài nguyên đóng kèm, dùng resource abstraction của Spring:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:data/countries.json"
);

try (InputStream input = resource.getInputStream()) {
    // Parse nội dung.
}
~~~

Một resource nằm trong executable JAR không nhất thiết có `java.io.File` tương ứng. Vì vậy, trong trường hợp đọc, `getInputStream()` thường phù hợp hơn `getFile()`.

### Không nên đóng secret vào resources

Đặt mật khẩu, token hoặc private key trong `application-prod.yml` bên trong JAR không làm chúng an toàn chỉ vì file nằm trong archive. Người có quyền tải file có thể liệt kê hoặc giải nén archive.

Nên đưa secret vào nguồn cấu hình phù hợp lúc triển khai, chẳng hạn biến môi trường, mounted secret file hoặc hệ thống quản lý bí mật.

## 14. Kiểm tra artifact: bắt đầu từ đúng file

Sau khi build, việc đầu tiên là xác định **đúng file sẽ phát hành**.

Với Maven:

~~~text
target/orders-api-0.0.1-SNAPSHOT.jar
~~~

Với Gradle:

~~~text
build/libs/orders-api-0.0.1-SNAPSHOT.jar
~~~

Đây là tên minh họa. Project có thể đặt tên khác hoặc sinh nhiều output như plain JAR, source JAR và backup JAR.

Một quy trình kiểm tra tốt phải trả lời được:

1. File được chọn do task/goal nào tạo?
2. Kích thước file có hợp lý so với ứng dụng và dependencies không?
3. Nó có cấu trúc Spring Boot executable archive không?
4. Manifest có thông tin khởi động đúng không?
5. Đã gồm các dependency cần thiết chưa?
6. Đã loại dependency development/test không cần thiết chưa?
7. Có chứa secret hoặc dữ liệu nội bộ không nên phát hành không?
8. Có thể chạy chính file này trong môi trường gần với deployment thực tế không?

Đừng kiểm tra một JAR rồi lại deploy một JAR khác chỉ vì tên gần giống.

## 15. Kiểm tra cấu trúc bên trong JAR bằng jar tf

JDK có công cụ `jar`. Để liệt kê nội dung:

~~~bash
jar tf target/orders-api-0.0.1-SNAPSHOT.jar
~~~

Đối với Gradle:

~~~bash
jar tf build/libs/orders-api-0.0.1-SNAPSHOT.jar
~~~

Có thể lọc nhanh trên Linux/macOS:

~~~bash
jar tf build/libs/orders-api.jar | grep 'BOOT-INF'
~~~

Trên PowerShell:

~~~powershell
jar tf .\build\libs\orders-api.jar |
    Select-String 'BOOT-INF'
~~~

Với Spring Boot executable JAR điển hình, hãy tìm:

~~~text
BOOT-INF/classes/com/example/orders/OrdersApplication.class
BOOT-INF/classes/application.yml
BOOT-INF/lib/spring-boot-*.jar
BOOT-INF/lib/spring-context-*.jar
~~~

Kết quả trên chỉ là ví dụ tên mục, không phải danh sách bắt buộc cố định.

### Kiểm tra launcher và manifest

Có thể dùng công cụ archive như `unzip` trên Linux/macOS để đọc manifest:

~~~bash
unzip -p target/orders-api-0.0.1-SNAPSHOT.jar \
  META-INF/MANIFEST.MF
~~~

Trên Windows, có thể dùng phần mềm archive phù hợp hoặc trích riêng manifest bằng công cụ `jar` vào thư mục tạm an toàn rồi xem nội dung. Khi dùng `jar xf`, nhớ rằng thao tác giải nén sẽ tạo file ở working directory hiện tại, vì vậy nên chọn một thư mục tạm riêng thay vì chạy trong thư mục source.

Đọc manifest để phân biệt:

- Có entry point phù hợp cho `java -jar` hay không?
- Start class có đúng class chứa `main` mong đợi không?
- File đang kiểm tra có phải archive được Spring Boot repackage không?

Cấu trúc Boot thực tế có thể khác nếu ứng dụng dùng kiểu đóng gói đặc biệt, ví dụ WAR hoặc native image. Không áp dụng nguyên xi kiểm tra `BOOT-INF/lib` cho mọi loại artifact.

## 16. Kiểm tra devtools không lọt vào artifact

Với Gradle:

~~~bash
jar tf build/libs/orders-api.jar | grep 'spring-boot-devtools'
~~~

Với PowerShell:

~~~powershell
jar tf .\build\libs\orders-api.jar |
    Select-String 'spring-boot-devtools'
~~~

Nếu không có dòng nào, đó là dấu hiệu devtools không nằm trong archive.

Với Maven:

~~~bash
jar tf target/orders-api-0.0.1-SNAPSHOT.jar |
  grep 'spring-boot-devtools'
~~~

Ở cấu hình đóng gói production thông thường, **không nên có** mục như:

~~~text
BOOT-INF/lib/spring-boot-devtools-*.jar
~~~

Lưu ý:

- Kiểm tra **chính artifact dùng deploy**.
- Việc devtools có trong dependency cache của Maven/Gradle không đồng nghĩa nó nằm trong JAR.
- Việc classpath development chứa devtools là bình thường.
- Không nên chỉ grep build file rồi kết luận về nội dung artifact; packaging plugin có thể thực hiện thao tác loại trừ.
- Nếu thấy devtools trong production JAR, cần xem lại dependency scope/configuration và plugin đóng gói, thay vì chỉ tắt một property của devtools lúc runtime.

### Kiểm tra test libraries

Tương tự, hãy xem có những thư viện chỉ phục vụ test như JUnit, Mockito hoặc những fixture không mong muốn trong archive không.

~~~bash
jar tf build/libs/orders-api.jar |
  grep -E 'junit|mockito|spring-boot-starter-test'
~~~

Tên `spring-boot-starter-test` có thể là starter điều phối dependency ở giai đoạn build, không nhất thiết xuất hiện dưới dạng JAR cùng tên; khi kiểm tra hãy tập trung cả những dependency con liên quan.

Nếu một thư viện test thật sự có mặt trong `BOOT-INF/lib` mà ứng dụng không sử dụng ở runtime, cần tìm lý do vì sao nó bị khai báo sai scope hoặc được kéo vào qua dependency khác.

**Không kết luận mọi tên có chữ `test` đều độc hại**: một số thư viện production có tên hoặc package không theo quy ước đơn giản. Khi thấy thành phần lạ, cần xác định chính xác module, version và mục đích trước khi loại bỏ.

## 17. Kiểm tra dependency nào thực sự cần lúc chạy

Một lỗi packaging phổ biến là ứng dụng compile được nhưng lúc `java -jar` lại báo:

~~~text
java.lang.NoClassDefFoundError: ...
~~~

hoặc:

~~~text
java.lang.ClassNotFoundException: ...
~~~

Có thể do:

- Dependency chỉ được khai báo `compileOnly` nhưng code lại cần nó lúc chạy.
- Maven dùng scope không phù hợp.
- Plugin build đã loại nhầm một dependency.
- Có xung đột version giữa các thư viện.
- Ứng dụng dùng reflection hoặc thư viện động mà class không có trong runtime classpath.
- JAR được chọn là plain JAR thay vì executable JAR.

Với Maven, có thể xem dependency graph bằng:

~~~bash
./mvnw dependency:tree
~~~

Với Gradle, có thể xem runtime dependencies bằng:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Các lệnh này giúp xem cách một dependency xuất hiện trong đồ thị. Nhưng **dependency graph không thay thế kiểm tra artifact**, vì plugin packaging có thể loại hoặc biến đổi một số thành phần.

Khi gặp lỗi, cần kết hợp:

1. Chữ ký lỗi trong stack trace.
2. Dependency graph có hiệu lực.
3. Nội dung JAR.
4. Cấu hình compile/runtime scopes.
5. Cách ứng dụng được chạy trong môi trường thật.

Không nên sửa lỗi ClassNotFound bằng cách chuyển tất cả dependency sang `implementation` hoặc `compile` một cách thiếu kiểm soát.

## 18. Kiểm tra version Java và tính tương thích runtime

Một artifact Spring Boot có thể được build bởi Java mới hơn runtime trên server. Khi chạy, JVM có thể báo:

~~~text
java.lang.UnsupportedClassVersionError
~~~

Điều đó thường cho thấy bytecode được compile cho phiên bản Java cao hơn phiên bản JVM đang chạy, hoặc có library tương ứng yêu cầu runtime cao hơn.

Các bước cần xác định:

~~~bash
java -version
~~~

Trong môi trường build cũng có thể xem:

~~~bash
./mvnw -version
~~~

hoặc:

~~~bash
./gradlew --version
~~~

Không nên mặc định output của IDE và output của pipeline build dùng cùng một JDK.

Ví dụ một project định hướng Java 21 có thể dùng:

~~~xml
<properties>
    <java.version>21</java.version>
</properties>
~~~

Trong dự án Gradle, có thể dùng Java toolchain:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Các đoạn này chỉ minh họa cách quy định Java version trong những dự án hỗ trợ cấu hình tương ứng. Phiên bản Java thực tế phải phù hợp với bản Spring Boot, dependency và môi trường deploy của hệ thống.

### Build reproducibility và môi trường runtime

Lý tưởng là:

- JDK cho compile được kiểm soát.
- Dependency versions được quản lý tập trung.
- Runtime JVM có version tương thích.
- Docker base image có version rõ ràng, không bị trôi ngoài ý muốn.
- Artifact được build một lần rồi promote qua các môi trường, thay vì build lại từ source cho từng môi trường.

Nhờ vậy, sự khác biệt giữa staging và production chủ yếu đến từ externalized configuration và tài nguyên môi trường, không phải từ việc artifact bị build khác nhau.

## 19. Chạy smoke test từ chính artifact

**Smoke test** là phép thử ngắn kiểm tra rằng artifact có thể bắt đầu chạy và thực hiện một chức năng tối thiểu trong môi trường dự kiến.

Nó không thay thế unit test, integration test hoặc load test.

Với executable JAR:

~~~bash
java -jar target/orders-api-0.0.1-SNAPSHOT.jar
~~~

Hoặc chỉ rõ cổng và profile:

~~~bash
java -jar target/orders-api-0.0.1-SNAPSHOT.jar \
  --server.port=18080 \
  --spring.profiles.active=smoke
~~~

Đây là ví dụ lệnh cho một ứng dụng web đã hỗ trợ những property tương ứng. Phải bảo đảm profile `smoke` tồn tại hoặc cấu hình mặc định cho phép chạy với môi trường test phù hợp.

Từ một terminal khác, gọi endpoint an toàn của ứng dụng:

~~~bash
curl -i http://localhost:18080/actuator/health
~~~

Endpoint Actuator chỉ có nếu dependency và cấu hình exposure cho phép. Nếu project không có Actuator, dùng một endpoint ping/health do project cung cấp và được thiết kế để kiểm tra nội bộ.

### Không chỉ xem process còn chạy

Một service có thể mở cổng nhưng chưa sẵn sàng nghiệp vụ vì:

- Runner đồng bộ chưa xong.
- Tác vụ chuẩn bị bất đồng bộ đang xử lý.
- Dependency bắt buộc bị mất kết nối.
- Readiness probe vẫn báo không đạt.
- API chính gặp lỗi dù trang chủ trả HTTP 200.

Do đó, smoke test tối thiểu nên kiểm tra:

1. JVM khởi động với đúng version.
2. Không có exception startup nghiêm trọng.
3. Ứng dụng đạt trạng thái sẵn sàng phù hợp.
4. Một request chức năng cơ bản trả kết quả mong đợi.
5. Việc dừng process diễn ra có kiểm soát.
6. Cấu hình ngoài artifact được đọc đúng, không dựa vào file trên máy developer.

Lệnh thử trên production cần tuân theo quy trình vận hành, không được tùy tiện tạo dữ liệu hoặc tác động người dùng thật.

## 20. Ví dụ ứng dụng nhỏ để minh họa đóng gói

Giả sử project có một Spring Boot application:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Một controller:

~~~java
package com.example.orders;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SystemController {

    @GetMapping("/api/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }
}
~~~

Cấu hình:

~~~properties
spring.application.name=orders-api
server.port=8080
~~~

Nếu project dùng `spring-boot-starter-web` và plugin Boot packaging phù hợp, có thể:

1. Build executable JAR.
2. Tìm artifact trong `target` hoặc `build/libs`.
3. Kiểm tra cấu trúc với `jar tf`.
4. Chạy `java -jar` từ một thư mục độc lập với source tree.
5. Gửi:

~~~bash
curl -i http://localhost:8080/api/ping
~~~

Kết quả minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"ok"}
~~~

Đây là cách kiểm tra rằng **class controller và web runtime thực sự có thể được khởi động từ artifact**, không phải chỉ từ môi trường IDE.

Để chứng minh ứng dụng có thể triển khai độc lập, tốt hơn nên chạy file JAR tại một vị trí không phải thư mục source và không vô tình tham chiếu các file local chỉ có trên máy developer.

## 21. Đóng gói JAR cho Docker hoặc container image

Một container image thường chứa:

- Java runtime tương thích.
- Executable JAR thực tế.
- Cấu hình khởi động và working directory.
- Những thư mục cần mount hoặc quyền truy cập phù hợp.

Ví dụ Dockerfile tối giản:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app

COPY build/libs/orders-api.jar /app/orders-api.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/orders-api.jar"]
~~~

Ở đây giả định:

- Project tạo `build/libs/orders-api.jar`, chẳng hạn bằng cách đặt `archiveFileName` trong `bootJar`.
- Artifact được biên dịch tương thích với Java 21.
- Ứng dụng dùng port 8080 hoặc nhận cấu hình cổng tương ứng.

**COPY phải trỏ đến đúng executable JAR**, không phải một file plain JAR. Sử dụng wildcard quá rộng như `build/libs/*.jar` có thể chọn nhầm file hoặc không rõ file nào được copy nếu thư mục có nhiều đầu ra.

### Tạo image không có nghĩa artifact đã được kiểm tra

Một Docker build có thể hoàn thành dù JAR sai entry point hoặc thiếu một class chỉ được dùng lúc runtime. Cần smoke test image thật, kiểm tra log và health/readiness như với JAR.

Ngoài ra, một image có đúng JAR nhưng lại sai biến môi trường, thiếu CA certificate hoặc mount sai đường dẫn vẫn có thể không hoạt động trong production.

### Cân nhắc security của image

Trong môi trường thực tế nên xem xét:

- Dùng runtime image đủ nhỏ và được cập nhật bảo mật.
- Chạy bằng user không phải root khi có thể.
- Chỉ copy artifact và file thật sự cần.
- Không đưa file `.env` chứa secret vào build context/image.
- Không chứa Maven/Gradle cache, source tree hoặc test reports trong image runtime nếu không cần.
- Quản lý cấu hình và secret từ môi trường triển khai thay vì bake vào image.

Các biện pháp này bổ sung cho việc loại devtools; chúng không thay thế kiểm tra dependency của chính JAR.

## 22. Multi-stage build: tách môi trường build và runtime

Một lựa chọn phổ biến là dùng **multi-stage Dockerfile** để build bằng image có Maven/JDK, sau đó chạy bằng image chỉ có JRE.

Ví dụ với một dự án Maven đã tạo executable JAR theo tên ổn định `orders-api.jar`:

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21 AS build

WORKDIR /workspace
COPY pom.xml .
COPY src ./src

RUN mvn -B package

FROM eclipse-temurin:21-jre

WORKDIR /app
COPY --from=build /workspace/target/orders-api.jar /app/app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Để ví dụ này chạy đúng, project phải được cấu hình để tạo file `target/orders-api.jar`, chẳng hạn bằng `<finalName>orders-api</finalName>`, và phải có toàn bộ nguồn build cần thiết trong context Docker. Nếu dự án cần Maven Wrapper, modules khác, parent POM, resource bổ sung hoặc file cấu hình build, Dockerfile phải copy các thành phần đó tương ứng.

Ưu điểm:

~~~text
Build stage:
  Maven + JDK + source + cache build
                  |
                  v
             executable JAR
                  |
                  v
Runtime stage:
  JRE + executable JAR
  Không cần source hoặc Maven để vận hành
~~~

Multi-stage giảm việc mang build tool và source vào runtime image, nhưng **không tự chứng minh rằng dependency development-only đã được loại khỏi JAR**. Muốn xác minh cần kiểm tra artifact được copy giữa các stage.

Với project lớn, có thể dùng image build chuyên biệt, cache dependencies và cơ chế tạo image của Spring Boot như buildpacks. Dù chọn cách nào, đối tượng cần quan sát vẫn là **artifact/image sẽ được deploy**.

## 23. Khi nào dùng WAR?

Executable JAR phù hợp cho nhiều ứng dụng Spring Boot triển khai độc lập. WAR có thể phù hợp khi cần tích hợp với một servlet container ngoài theo yêu cầu hạ tầng.

Với Maven:

~~~xml
<packaging>war</packaging>
~~~

Một ứng dụng truyền thống triển khai ra servlet container ngoài có thể cần mở rộng `SpringBootServletInitializer`:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
import org.springframework.boot.builder.SpringApplicationBuilder;

@SpringBootApplication
public class OrdersApplication extends SpringBootServletInitializer {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application
    ) {
        return application.sources(OrdersApplication.class);
    }
}
~~~

Đây là ví dụ cho Spring Boot dựa trên **Servlet**; không áp dụng y nguyên cho một ứng dụng thuần WebFlux hoặc các mô hình runtime khác.

Khi triển khai WAR, dependency của servlet container phải được quản lý phù hợp với mô hình server ngoài, thường sử dụng `provided` hoặc cấu hình tương ứng. Một executable WAR của Spring Boot cũng có thể có cơ chế bố trí dependency để phục vụ `java -jar`, ví dụ vùng `WEB-INF/lib-provided` cho dependency do container ngoài cung cấp.

**Không áp dụng quy tắc “mọi WAR đều thiếu Tomcat” hoặc “mọi WAR đều chạy bằng java -jar”**. Cần xem cấu hình plugin, kiểu WAR được tạo và servlet container mục tiêu.

Nếu hạ tầng không bắt buộc WAR, executable JAR thường cho mô hình vận hành đơn giản hơn: build một artifact, chạy nó với JVM phù hợp.

## 24. Artifact và externalized configuration

Mục tiêu của đóng gói là tạo artifact **có thể chuyển giữa môi trường**. Những giá trị thay đổi giữa development, staging và production nên được cung cấp qua cơ chế cấu hình ngoài.

Ví dụ:

~~~properties
# application.properties trong JAR
spring.application.name=orders-api
server.port=8080
~~~

Ở production:

~~~bash
SERVER_PORT=18080 java -jar orders-api.jar
~~~

Hoặc:

~~~bash
java -jar orders-api.jar --server.port=18080
~~~

Với cấu hình database hoặc secret, có thể dùng biến môi trường, mounted file hoặc hệ thống quản lý secret phù hợp.

### Không nhầm configuration profile với artifact khác nhau

Một artifact có thể chứa cấu hình chung và nhiều file theo profile:

~~~text
application.yml
application-dev.yml
application-prod.yml
~~~

Kích hoạt profile:

~~~bash
java -jar orders-api.jar --spring.profiles.active=prod
~~~

Nhưng chỉ chọn profile `prod` không khiến secret trong `application-dev.yml` biến mất khỏi JAR. Nếu một file không nên được phát hành, cần kiểm soát ngay từ build/resources, không chỉ trông vào profile selection.

### Smoke test phải phản ánh môi trường thật

Nếu ứng dụng production dùng dữ liệu từ:

~~~text
file:/etc/orders/rules.json
~~~

cần bảo đảm trong container hoặc server thực tế đường dẫn đó tồn tại và process có quyền đọc. Việc file tồn tại trên máy developer không có giá trị chứng minh cho runtime container.

## 25. Kiểm tra checksum và tính toàn vẹn artifact

Nếu một artifact đi qua nhiều giai đoạn (build → staging → production), nên có cách xác nhận đó là cùng một file.

Trên Linux/macOS:

~~~bash
sha256sum orders-api.jar
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 .\orders-api.jar
~~~

Một bản ghi phát hành có thể ghi:

~~~text
artifact: orders-api.jar
version: 1.2.0
sha256: <giá trị SHA-256 do pipeline tạo>
java-runtime: 21
build-commit: <mã commit>
~~~

Đây là metadata minh họa; thay các placeholder bằng giá trị thật của pipeline.

Checksum giúp phát hiện file bị thay đổi giữa các bước. Nó **không tự chứng minh artifact an toàn, có nguồn gốc đáng tin hoặc không bị thay thế cả artifact lẫn checksum**. Với yêu cầu supply-chain cao hơn, cần kết hợp quyền truy cập artifact repository, chữ ký/attestation và chính sách release.

### Build once, deploy many

Một nguyên tắc có ích:

~~~text
Source commit X
      |
      v
CI build + tests + package
      |
      v
Artifact A (hash H)
      |
      +----> Staging (hash H)
      |
      +----> Production (hash H)
~~~

Nhờ cùng một artifact, nếu staging và production khác hành vi, người điều tra có cơ sở tập trung vào environment, cấu hình và external dependencies thay vì phải đoán hai lần build đã khác nhau.

## 26. Vấn đề security khi đóng gói

Ngoài devtools, artifact có thể vô tình chứa thông tin nhạy cảm:

- File private key hoặc certificate có secret không được phép công bố.
- Password được hardcode trong `application-prod.yml`.
- File test fixture chứa dữ liệu người dùng thật.
- Các file `.env` hoặc backup được copy nhầm vào resources.
- Dependency cũ có lỗ hổng bảo mật.
- Cấu hình cho phép truy cập endpoint quản trị không phù hợp.
- Tool development/diagnostic không cần cho runtime.

Việc kiểm tra nên kết hợp:

1. **Danh sách file bên trong artifact**: phát hiện resource không nên phát hành.
2. **Danh sách dependency và version**: phục vụ kiểm tra thành phần và các cảnh báo bảo mật.
3. **Quy trình secret scanning**: tránh secret lẫn trong file cấu hình, resource hoặc source.
4. **Thiết lập quyền truy cập và cấu hình runtime**: bảo vệ Actuator, database, message broker và hệ thống giám sát.
5. **Kiểm tra container image** nếu artifact được phân phối dưới dạng image.

### Không nên grep và in secret ra log pipeline

Khi nghi ngờ artifact chứa thông tin nhạy cảm, bước kiểm tra phải tránh làm lộ chính nội dung đó trong log CI/CD. Có thể quét theo tên file hoặc sử dụng secret scanner với cơ chế masking và quyền truy cập phù hợp, thay vì giải nén và in toàn bộ `application-prod.yml` vào console công khai.

Một JAR có thể chứa resource hoàn toàn hợp lệ cho production nhưng vẫn yêu cầu phân quyền riêng. Không nên phán đoán dựa duy nhất vào đuôi file.

## 27. Dependency tree và SBOM

Khi một ứng dụng có nhiều starter, thư viện runtime thường đi vào classpath **gián tiếp** qua dependency bắc cầu.

Ví dụ:

~~~text
spring-boot-starter-web
    |
    +-- spring-web
    +-- spring-webmvc
    +-- embedded servlet container
    +-- logging dependencies
    +-- ...
~~~

Vì vậy, một project có thể không khai báo trực tiếp một JAR nhưng JAR đó vẫn xuất hiện trong `BOOT-INF/lib`.

Có hai nguồn thông tin bổ sung:

- **Dependency graph** của Maven/Gradle: cho biết module nào yêu cầu module nào.
- **SBOM (Software Bill of Materials)**: danh sách thành phần phần mềm và metadata của bản phát hành, nếu pipeline có công cụ tạo.

Khi xử lý một dependency lỗi thời hoặc có CVE, cần xác định **phiên bản thực sự được chọn cho runtime artifact**, chứ không chỉ phiên bản trong một dòng dependency declaration.

Nếu pipeline tạo SBOM, hãy liên hệ SBOM với artifact/image tương ứng để tránh báo cáo danh sách của một build khác.

## 28. Những lỗi packaging thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| `no main manifest attribute` | Chạy plain JAR hoặc thiếu repackage | Kiểm tra manifest và task/goal tạo file |
| `ClassNotFoundException` | Thiếu dependency runtime hoặc chọn sai artifact | Xem `BOOT-INF/lib` và dependency graph |
| `NoClassDefFoundError` | Class có lúc compile nhưng thiếu lúc chạy | Kiểm tra `compileOnly`, `provided`, xung đột version |
| `UnsupportedClassVersionError` | Runtime JVM không tương thích bytecode | So sánh Java version build và runtime |
| Chạy bằng IDE được, `java -jar` không đọc được template | Dùng đường dẫn `src/main/resources` hoặc `getFile()` với resource trong JAR | Dùng classpath resource và InputStream |
| `Port already in use` | Cổng deploy bị chiếm | Điều chỉnh `server.port` hoặc hạ tầng |
| `Application failed to start` vì thiếu cấu hình | Biến môi trường/secret không được cấp trong runtime | Kiểm tra configuration source và profile |
| Devtools có trong JAR | Scope/plugin exclude chưa phù hợp | Kiểm tra `developmentOnly` hoặc cấu hình Maven |
| JUnit/Mockito xuất hiện trong `BOOT-INF/lib` | Dependency test bị khai báo sai phạm vi | Xem scope/configuration và lý do transitive |
| Docker image build được nhưng container thoát ngay | ENTRYPOINT, JRE hoặc JAR sai | Xem log, inspect archive và smoke test |
| Container không đọc được file mount | Path/quyền trong container khác host | Kiểm tra mount path và user runtime |
| WAR không chạy đúng trên servlet container | Packaging/provided dependency hoặc bootstrap sai | Kiểm tra `SpringBootServletInitializer` và tương thích server |

Không nên chữa tất cả lỗi trên bằng cách thêm dependency hay đổi plugin một cách ngẫu nhiên. Hãy xác định **lỗi xảy ra ở giai đoạn nào**: compile, package, startup, readiness hay runtime.

## 29. Trường hợp không nên đưa devtools vào production bằng mọi giá

Một số dự án thử bật devtools trong production để debug một lỗi khó. Đây không phải cách mặc định nên chọn.

Giải pháp có kiểm soát hơn:

- Điều chỉnh log level tạm thời cho package cần điều tra.
- Dùng metrics và tracing.
- Sử dụng endpoint quản trị được bảo vệ, nếu chính sách cho phép.
- Reproduce bằng executable artifact tương tự production trong staging.
- Bổ sung thông tin lỗi tại boundary của request/job.
- Phát hành bản sửa hoặc instrumentation chính thức sau khi kiểm tra.

Nếu cần thêm công cụ chẩn đoán, nên xác định rõ rủi ro và phạm vi thay vì đưa cả công cụ hỗ trợ development vào runtime artifact vô thời hạn.

### Development-only không có nghĩa “không ảnh hưởng production ở mọi tình huống”

Nếu một dependency được khai báo sai cách, build script có custom packaging, hoặc image copy cả thư mục runtime classpath thay vì executable JAR, công cụ development vẫn có thể lọt vào môi trường triển khai.

Do đó, **ý định trong build file phải được kiểm tra lại bằng nội dung artifact thực tế**. Đây là nguyên tắc quan trọng nhất của bài học.

## 30. Một quy trình kiểm tra artifact thực tế

Một đội dự án có thể chuẩn hóa công việc theo các bước:

### Bước 1 — Xác nhận công cụ build

Dự án dùng Maven hay Gradle? Có dùng Spring Boot plugin phù hợp không? Artifact mong đợi là executable JAR, WAR hay native image?

### Bước 2 — Phân loại dependency

Đặt đúng scope cho:

- Runtime libraries.
- Test libraries.
- Annotation processors.
- Developer tooling như devtools.
- Dependency do external servlet container cung cấp nếu dùng WAR.

### Bước 3 — Build theo quy trình có kiểm soát

Ví dụ Maven:

~~~bash
./mvnw clean package
~~~

Ví dụ Gradle:

~~~bash
./gradlew clean check bootJar
~~~

Mỗi pipeline có thể chọn tập lệnh khác nhau; điều cốt lõi là tạo đúng đầu ra và thực hiện các bước kiểm tra đã được đội dự án quy định.

### Bước 4 — Chọn chính xác artifact

Không chọn bừa file có đuôi `.jar`. Xác minh đường dẫn output của Maven/Gradle và tên archive chính thức.

### Bước 5 — Kiểm tra cấu trúc

Dùng `jar tf` và manifest để xác định JAR có launcher, classes, resources và runtime dependencies phù hợp.

### Bước 6 — Xác minh development-only không được đóng gói

Kiểm tra không có `spring-boot-devtools` và các thư viện test không cần thiết trong archive production.

### Bước 7 — Kiểm tra Java runtime và cấu hình ngoài

Xác định JVM runtime, profile, biến môi trường, mount files, network và các phụ thuộc hạ tầng quan trọng.

### Bước 8 — Smoke test chính artifact

Chạy `java -jar` hoặc image thực tế; kiểm tra startup, readiness và ít nhất một chức năng cơ bản theo môi trường test an toàn.

### Bước 9 — Ghi nhận checksum và phát hành

Lưu version, hash, build commit và metadata cần thiết. Promote cùng artifact qua các môi trường nếu quy trình cho phép.

Có thể biểu diễn ngắn:

~~~text
Dependency scopes
       |
       v
Reproducible build
       |
       v
Exact executable artifact
       |
       +-- Check structure / manifest
       |
       +-- Check runtime dependencies
       |
       +-- Exclude devtools / test tools
       |
       +-- Check resources / sensitive content
       |
       v
Smoke test artifact / image
       |
       v
Record version + checksum
       |
       v
Deploy
~~~

## 31. Bài tập 1 — Phân biệt bootJar và jar

Giả sử Gradle tạo:

~~~text
build/libs/orders-api-1.0.0.jar
build/libs/orders-api-1.0.0-plain.jar
~~~

Hãy:

1. Xác định task đã tạo mỗi file.
2. Kiểm tra cả hai bằng `jar tf`.
3. Tìm `BOOT-INF/classes` và `BOOT-INF/lib`.
4. Thử giải thích file nào nên chạy bằng `java -jar`.
5. Kiểm tra manifest của file tương ứng.

**Điểm cần rút ra:** file JAR nào cũng là Java archive, nhưng không phải file nào cũng là executable Spring Boot archive có đủ runtime dependencies.

## 32. Bài tập 2 — Kiểm tra developmentOnly

Trong một project Gradle có Spring Boot plugin, thêm:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

Sau đó:

1. Chạy ứng dụng với `bootRun` trong môi trường phát triển.
2. Đóng gói bằng `bootJar`.
3. Liệt kê nội dung JAR.
4. Tìm `spring-boot-devtools` trong archive.
5. Giải thích vì sao dependency có thể phục vụ quá trình phát triển nhưng không nên xuất hiện trong production JAR.

Điểm cần rút ra: **classpath của IDE/build tool có thể khác classpath của executable archive**.

## 33. Bài tập 3 — Maven optional và test scope

Giả sử Maven POM có:

~~~xml
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
~~~

Hãy trả lời:

1. `optional=true` có giống `scope=test` không?
2. Dependency nào hỗ trợ development?
3. Dependency nào phục vụ test?
4. Cơ chế nào loại devtools khỏi executable JAR khi dùng Spring Boot Maven Plugin?
5. Muốn xác nhận artifact sạch, cần xem POM hay file JAR thực tế?

**Đáp án trọng tâm:** optional không tương đương test scope. Devtools chủ yếu dành cho development; starter-test thuộc test scope; packaging behavior của plugin và nội dung archive cần được kiểm tra.

## 34. Bài tập 4 — Điều tra lỗi khi chạy từ JAR

Một ứng dụng đọc file:

~~~java
Path path = Path.of("src/main/resources/data/rates.csv");
String content = Files.readString(path);
~~~

Trong IDE chạy được; khi deploy executable JAR báo không tìm thấy file.

Hãy sửa để đọc tài nguyên đóng gói:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:data/rates.csv"
);

try (InputStream input = resource.getInputStream()) {
    // Đọc nội dung bằng parser phù hợp.
}
~~~

Và giải thích tại sao `getInputStream()` là lựa chọn phù hợp hơn `getFile()` đối với resource nằm bên trong JAR.

## 35. Bài tập 5 — Thiết kế một release checklist

Cho một service xử lý đơn hàng có cấu hình:

~~~text
Java 21
Spring Boot web starter
PostgreSQL JDBC driver
spring-boot-devtools
JUnit / Mockito
application-dev.yml
application-prod.yml
~~~

Hãy thiết kế một checklist release tối thiểu:

1. JDBC driver phải có mặt ở runtime nếu ứng dụng dùng PostgreSQL.
2. Devtools và thư viện test không nên nằm trong executable JAR.
3. Không đóng secret vào bất kỳ file config nào trong artifact.
4. Xác minh JVM runtime tương thích.
5. Chạy `java -jar` với externalized configuration của môi trường test.
6. Kiểm tra readiness và một API cơ bản.
7. Lưu hash của artifact sẽ phát hành.

Giải thích thêm: việc file `application-prod.yml` có trong JAR **không tự sai** nếu nó chỉ chứa cấu hình không nhạy cảm; điều sai là đóng dữ liệu bí mật hoặc giả định profile không active thì file không thể bị đọc.

## 36. Những hiểu lầm thường gặp

**“Ứng dụng chạy được bằng bootRun thì artifact chắc chắn chạy được.”** Không đúng. Runtime classpath và layout của executable JAR khác với cách chạy từ build tool.

**“JAR nào cũng dùng java -jar được.”** Không. Plain JAR có thể thiếu main manifest và dependency.

**“Development-only chỉ là profile dev.”** Không. Dependency scope và Spring profile phục vụ hai mục đích khác nhau.

**“Maven optional=true tự loại dependency khỏi mọi JAR.”** Không. Optional chủ yếu điều khiển tính truyền tiếp của dependency; packaging còn phụ thuộc plugin.

**“Đã khai báo devtools developmentOnly thì không cần kiểm tra.”** Nên kiểm tra archive, nhất là khi có custom packaging.

**“Bỏ test dependency vào runtime không gây vấn đề gì.”** Không nên. Nó tăng thành phần, chi phí và rủi ro không cần thiết.

**“Chỉ cần test bằng IDE là đủ.”** Không. Phải smoke test chính artifact dùng deploy.

**“application-dev.yml không active thì không thể lộ secret.”** Sai. File có thể vẫn nằm trong JAR.

**“Có BOOT-INF/lib là ứng dụng đã sẵn sàng nghiệp vụ.”** Không. Cấu trúc JAR đúng chỉ chứng minh một phần của packaging.

**“Docker build thành công tức là ứng dụng chạy được.”** Không. Image có thể chứa sai JAR, sai JRE hoặc thiếu runtime configuration.

**“Checksum cho biết ứng dụng an toàn.”** Không. Nó chỉ là một tín hiệu tính toàn vẹn; còn cần provenance và kiểm tra bảo mật.

**“Đưa mọi dependency thành implementation sẽ chắc chắn đủ runtime.”** Có thể che lỗi scope và làm artifact phình to. Nên phân loại đúng theo nhu cầu.

**“JAR chứa tất cả cấu hình production.”** Không nên. Artifact bất biến nên kết hợp externalized configuration và secret management.

**“Chỉ cần kiểm tra package là không cần kiểm tra deploy.”** Không. Runtime Java, filesystem, network và các phụ thuộc ngoài có thể khác hoàn toàn môi trường build.

## Kết luận

Đóng gói Spring Boot là quá trình biến source code, resource và dependency runtime thành một **artifact có thể chạy trong môi trường mục tiêu**. Với executable JAR, Spring Boot Maven Plugin hoặc Gradle `bootJar` thường tổ chức class/resource trong `BOOT-INF/classes` và dependency runtime trong `BOOT-INF/lib`, đồng thời cung cấp launcher phù hợp cho `java -jar`.

**Development-only** giúp công cụ hỗ trợ lập trình như `spring-boot-devtools` phục vụ quá trình sửa code nhanh mà không trở thành thành phần không cần thiết trong production. Với Gradle, cách phổ biến là `developmentOnly`; với Maven, thường khai báo devtools `runtime` và `optional=true`, kết hợp cơ chế loại devtools của Spring Boot Maven Plugin. Không nên nhầm những thiết lập đó với Spring profile `dev`.

Cuối cùng, **kiểm tra artifact triển khai có nghĩa kiểm tra chính file hoặc image sẽ được phát hành**: đúng launcher, có class và dependency cần chạy, không chứa devtools/test tooling không cần thiết, không lộ secret, tương thích JVM, hoạt động với externalized configuration và vượt qua smoke test phù hợp. Xác nhận cấu trúc bằng `jar tf`, kiểm tra manifest, chạy `java -jar` và lưu checksum giúp giảm đáng kể các lỗi chỉ xuất hiện khi rời khỏi máy phát triển.
