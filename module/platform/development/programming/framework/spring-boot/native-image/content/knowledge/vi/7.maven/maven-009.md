# Truyền tham số, profile và quản lý phiên bản plugin một cách nhất quán

## 1. Vì sao cần quản lý tham số và phiên bản build?

Trong module **SPRING_BOOT_NATIVE_IMAGE**, Spring AOT chuẩn bị ứng dụng Spring Boot ở build time, sau đó GraalVM Native Image phân tích reachability và biên dịch executable native. Kết quả phụ thuộc vào nhiều đầu vào: phiên bản JDK/GraalVM, Spring Boot, Native Build Tools, Maven, cấu hình profile, property và tham số truyền cho compiler.

Nếu mỗi máy developer, CI và builder container dùng một tập tham số khác nhau, cùng một commit có thể tạo ra kết quả khác nhau: profile Spring khác làm thay đổi bean graph, plugin version khác tạo task behavior khác, hoặc build arguments khác thay đổi cách Native Image phân tích và link. Vì vậy cần **quản lý đầu vào build có chủ đích và có thể tái lập**.

Bài này tập trung vào ba nhóm:

- **Tham số Maven:** `-P`, `-D`, `-pl`, `-am`, `-DskipTests`, các tham số debug và cách truyền property.
- **Profile:** profile Maven điều khiển cấu hình build; profile Spring điều khiển cấu hình ứng dụng. Chúng có thể tương tác trong bước AOT nhưng không cùng một cơ chế.
- **Phiên bản plugin:** quản lý version Spring Boot Maven Plugin, GraalVM Native Build Tools và plugin hỗ trợ; dùng parent/BOM/properties để giảm sai lệch.

## 2. Các loại tham số thường dùng với Maven

Maven có nhiều loại đầu vào và vị trí truyền khác nhau:

| Cú pháp | Ý nghĩa | Ví dụ |
|---|---|---|
| `-P<id>` | Kích hoạt Maven profile | `-Pnative` |
| `-Dname=value` | Đặt Maven user property | `-DskipTests=true` |
| `-pl module` | Chọn project trong reactor | `-pl service-api` |
| `-am` | Build thêm project phụ thuộc trong reactor | `-pl service-api -am` |
| `-f path/pom.xml` | Chọn POM cụ thể | `-f app/pom.xml` |
| `-s settings.xml` | Dùng settings file cụ thể | `-s ci-settings.xml` |
| `-B` | Batch mode cho CI | `-B` |
| `-X` | Log debug chi tiết | `-X` |
| `-Dstyle.color=never` | Tắt màu log (tùy môi trường) | `-Dstyle.color=never` |

Ví dụ build native trong CI:

```bash
./mvnw -B -Pnative -DskipTests=false native:compile
```

`-DskipTests=false` làm rõ ý định chạy test nếu dự án có cấu hình kiểm thử gắn với lifecycle tương ứng. Tuy nhiên, gọi trực tiếp goal `native:compile` không tự động bảo đảm tất cả test lifecycle đã chạy; nếu yêu cầu verify test, chạy `verify` hoặc cấu hình pipeline riêng và kiểm tra execution thực tế.

Không dùng `-DskipTests` như một cách mặc định để “sửa” build native. Khi cần cô lập lỗi compiler, có thể bỏ test tạm thời, nhưng phải chạy lại test trước khi công nhận artifact.

## 3. Maven property và nơi định nghĩa giá trị

Một property có thể được định nghĩa ở nhiều nơi: POM, parent POM, profile, settings, command line hoặc environment được plugin đọc. Với cùng một tên property, thứ tự ưu tiên cụ thể phụ thuộc loại property và cách plugin sử dụng; **user property truyền bằng `-D` thường được dùng để override property cấu hình trong POM**.

Ví dụ khai báo version tập trung:

```xml
<properties>
    <java.version>21</java.version>
    <spring-boot.version>3.x.y</spring-boot.version>
    <native-build-tools.version>0.x.y</native-build-tools.version>
</properties>
```

Các chuỗi version trên chỉ là ký hiệu minh họa; thay bằng release thật đã được xác nhận tương thích. Nếu dùng `spring-boot-starter-parent`, version Spring Boot thường được khai báo ngay trong thẻ `parent`, và nhiều dependency/plugin được quản lý theo parent. Không nên tạo property version trùng lặp nếu parent đã quản lý chính xác phiên bản đó.

Property có thể dùng trong plugin configuration:

```xml
<configuration>
    <imageName>${native.image.name}</imageName>
</configuration>
```

Và truyền lúc chạy:

```bash
./mvnw -Pnative -Dnative.image.name=orders-service native:compile
```

Cách property được thay thế phụ thuộc vào cấu hình plugin; không phải mọi option CLI của GraalVM đều tự động trở thành Maven property. Phải khai báo mapping trong plugin configuration nếu muốn điều khiển option thông qua `-D`.

## 4. Quản lý phiên bản plugin tập trung

Một dự án Spring Boot Native Image thường có ít nhất hai plugin quan trọng:

- `org.springframework.boot:spring-boot-maven-plugin`: hỗ trợ các goal Spring Boot, bao gồm `process-aot`.
- `org.graalvm.buildtools:native-maven-plugin`: tích hợp Native Image compiler vào Maven.

Có thể khai báo version Native Build Tools tập trung:

```xml
<properties>
    <native-build-tools.version>0.x.y</native-build-tools.version>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>

        <plugin>
            <groupId>org.graalvm.buildtools</groupId>
            <artifactId>native-maven-plugin</artifactId>
            <version>${native-build-tools.version}</version>
        </plugin>
    </plugins>
</build>
```

`0.x.y` là placeholder, không phải version có thể dùng nguyên văn. Cần chọn release tương thích với Maven, JDK/GraalVM và Spring Boot đang dùng. Spring Boot parent quản lý một số plugin version, nhưng không được giả định nó luôn quản lý version Native Build Tools theo đúng nhu cầu dự án.

Trong Maven multi-module, cân nhắc khai báo version trong `pluginManagement` ở parent POM để các module dùng cùng một version:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.graalvm.buildtools</groupId>
                <artifactId>native-maven-plugin</artifactId>
                <version>${native-build-tools.version}</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Lưu ý: `pluginManagement` chỉ quản lý cấu hình/version mặc định; module vẫn phải khai báo plugin trong `build/plugins` để nó tham gia build. Đây là nguyên nhân phổ biến khiến người đọc thấy version trong parent nhưng không thấy goal chạy.

## 5. Profile Maven và profile Spring khác nhau

Hai loại profile có tên dễ nhầm:

| Loại profile | Cách kích hoạt | Mục đích |
|---|---|---|
| Maven profile | `-Pnative` | Chọn plugin, execution, property và cấu hình build |
| Spring profile | `-Dspring.profiles.active=prod` hoặc environment tương ứng | Chọn bean/configuration của ứng dụng Spring |

Ví dụ build native với Maven profile:

```bash
./mvnw -Pnative native:compile
```

Ví dụ chạy ứng dụng JVM với Spring profile:

```bash
java -Dspring.profiles.active=prod -jar target/orders.jar
```

Trong bước Spring AOT, profile/property Spring có thể tác động đến application context được phân tích. Nếu bean được bật hoặc tắt theo Spring profile tại thời điểm AOT, kết quả generated code có thể phản ánh cấu hình đó. Đổi `SPRING_PROFILES_ACTIVE` lúc chạy native không nhất thiết khôi phục được bean đã bị loại khỏi context trong build.

Có thể truyền property Spring cho tiến trình Maven:

```bash
./mvnw -Pnative -Dspring.profiles.active=production native:compile
```

Tuy nhiên, property chỉ ảnh hưởng Spring AOT nếu được truyền tới đúng JVM/plugin process và được Spring Boot plugin sử dụng cho AOT. Xác minh bằng log, cấu hình plugin và kết quả generated output; không mặc định mọi Maven user property đều tự động được chuyển tiếp.

## 6. Tổ chức profile native trong POM

Ví dụ rút gọn về cách nhóm execution native:

```xml
<profiles>
    <profile>
        <id>native</id>
        <properties>
            <spring.aot.enabled>true</spring.aot.enabled>
        </properties>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                    <executions>
                        <execution>
                            <id>process-aot</id>
                            <goals>
                                <goal>process-aot</goal>
                            </goals>
                        </execution>
                    </executions>
                </plugin>

                <plugin>
                    <groupId>org.graalvm.buildtools</groupId>
                    <artifactId>native-maven-plugin</artifactId>
                    <version>${native-build-tools.version}</version>
                    <extensions>true</extensions>
                    <executions>
                        <execution>
                            <id>native-compile</id>
                            <goals>
                                <goal>compile-no-fork</goal>
                            </goals>
                        </execution>
                    </executions>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
```

Đây là cấu trúc minh họa, không phải cấu hình bắt buộc cho mọi phiên bản. Property `spring.aot.enabled` chỉ có tác dụng khi plugin/version cụ thể có đọc property đó; không nên thêm property chỉ vì tên có vẻ hợp lý. Hãy đối chiếu tài liệu Spring Boot Maven Plugin và Native Build Tools cho phiên bản dự án.

Trong các cấu hình tích hợp được hỗ trợ, Spring Boot plugin và Native Build Tools có thể tự phối hợp execution, classpath và output AOT. Nếu dùng cấu hình thủ công, phải xác minh cả **thứ tự thực thi** và **đầu vào thật sự của Native Image**; chỉ đặt `dependsOn` không chứng minh generated classes/resources đã được truyền đúng.

## 7. Truyền build arguments cho GraalVM Native Image

Có thể cấu hình build arguments tại plugin thay vì đặt rải rác trong shell script. Ví dụ:

```xml
<configuration>
    <buildArgs>
        <buildArg>--verbose</buildArg>
        <buildArg>--no-fallback</buildArg>
    </buildArgs>
</configuration>
```

Các option phải được kiểm tra theo phiên bản GraalVM Native Image. `--verbose` giúp xem thêm thông tin build. `--no-fallback` yêu cầu build không tạo fallback image trong các tình huống mà phiên bản công cụ hỗ trợ fallback; khả năng và ý nghĩa cụ thể phụ thuộc GraalVM version. Không thêm option chỉ vì tìm thấy trong một snippet cũ.

Nếu muốn điều khiển option qua property:

```xml
<properties>
    <native.verbose>false</native.verbose>
</properties>

<configuration>
    <buildArgs>
        <buildArg>${native.build.arg}</buildArg>
    </buildArgs>
</configuration>
```

Đoạn trên cần định nghĩa `native.build.arg` và mapping có chủ đích. Một cách khác là dùng profile riêng chứa cấu hình verbose. Không nên để một property rỗng hoặc sai cú pháp sinh ra argument không hợp lệ.

## 8. Maven Wrapper, settings và môi trường CI

Để build tái lập, nên dùng Maven Wrapper trong repository:

```bash
./mvnw -version
```

Wrapper kiểm soát Maven distribution, nhưng không tự khóa JDK, GraalVM hay compiler/linker của hệ điều hành. CI nên pin:

- Commit và Maven Wrapper distribution.
- JDK/GraalVM distribution, version và architecture.
- Spring Boot parent/plugin version.
- Native Build Tools plugin version.
- Builder image và các package development của hệ điều hành.
- Profile/property được truyền vào build.

Nếu dùng private repository hoặc mirror, settings file cần được cung cấp có kiểm soát:

```bash
./mvnw -s ci-settings.xml -B -Pnative native:compile
```

Không commit credentials vào `pom.xml` hoặc shell history. Dùng secret store của CI và cấu hình server ID trong Maven settings. Khi báo cáo build, ghi tên profile và version, không đưa token/password.

Maven local repository có thể cache dependency; CI cache giúp giảm thời gian tải nhưng không nên dùng cache như bằng chứng plugin version đã được pin. POM và wrapper vẫn phải thể hiện version rõ ràng.

## 9. Kiểm tra effective configuration trước khi build

Khi có nhiều parent, profile và property, đừng suy đoán cấu hình cuối cùng. Dùng Maven Help Plugin:

```bash
./mvnw help:active-profiles -Pnative
./mvnw help:effective-pom -Pnative
./mvnw help:effective-settings
```

- `active-profiles`: cho biết profile nào đang active.
- `effective-pom`: cho thấy POM sau kế thừa và áp dụng profile, gồm plugin version và execution.
- `effective-settings`: cho thấy settings sau khi áp dụng user/global settings; kiểm tra cẩn thận trước khi chia sẻ vì có thể chứa thông tin nội bộ.

Có thể kiểm tra version plugin cụ thể bằng effective POM hoặc plugin help. Để xem log execution:

```bash
./mvnw -Pnative -X native:compile
```

Log debug có thể rất lớn và chứa property, đường dẫn hoặc thông tin môi trường. Chỉ bật khi cần; lọc thông tin nhạy cảm trước khi gửi cho người khác.

## 10. Ví dụ một lệnh CI có tham số rõ ràng

Một lệnh CI đơn giản có thể trông như sau:

```bash
./mvnw -B -Pnative \
  -DskipTests=false \
  -Dnative.image.name=orders-service \
  native:compile
```

Điều kiện để lệnh này có ý nghĩa:

1. Profile `native` tồn tại và khai báo đúng execution/plugin.
2. Plugin configuration thực sự tham chiếu property `native.image.name`.
3. Native Build Tools version tương thích với GraalVM và Maven.
4. JDK mà Maven sử dụng có Native Image và toolchain hệ điều hành sẵn sàng.
5. Test được chạy ở lifecycle/CI stage phù hợp; gọi trực tiếp goal native không thay thế `verify`.

Trong pipeline release, một quy trình rõ hơn thường chia thành các bước: JVM tests, build native, native smoke/integration tests, kiểm tra binary trong runtime image, rồi mới publish artifact. Điều này làm rõ stage nào thất bại và ngăn artifact chỉ build thành công nhưng chưa kiểm thử bị phát hành.

## 11. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `-Pnative` không có tác dụng | Sai profile ID, profile nằm trong POM khác hoặc bị điều kiện kích hoạt | `help:active-profiles`, xác nhận POM được dùng |
| Property `-D...` không thay đổi image name | Plugin không tham chiếu property đó hoặc dùng tên property khác | Kiểm tra plugin configuration/effective POM |
| Version plugin không như mong đợi | Parent/pluginManagement/profile override | Xem effective POM |
| Plugin không chạy dù có trong pluginManagement | Chưa khai báo plugin ở `build/plugins` | Khai báo plugin trong module cần build |
| Maven dùng JDK khác shell | JAVA_HOME, toolchains hoặc CI environment | `./mvnw -version`, kiểm tra toolchain |
| AOT chọn sai bean/profile | Spring property không đến được process AOT hoặc cấu hình build không đúng | Xem AOT log, profile Spring và generated output |
| Native compiler không nhận option | Option sai phiên bản hoặc cấu hình XML không đúng | Kiểm tra Native Image version và plugin help |
| Build khác nhau giữa local/CI | Version, architecture, environment hoặc profile khác nhau | Ghi lại toàn bộ đầu vào và so sánh effective POM |

Luôn phân loại lỗi theo lớp: **Maven model/profile**, **plugin execution**, **Spring AOT**, **Native Image compiler/linker**, hoặc **runtime**. Không giải quyết lỗi thiếu reflection metadata bằng cách đổi Maven profile nếu profile đã được áp dụng đúng.

## 12. Bài thực hành: chuẩn hóa build native

**Bối cảnh:** một ứng dụng Spring Boot đã có baseline JVM và cần thêm pipeline native.

**Bước 1 — Ghi lại phiên bản đầu vào.** Lưu Maven Wrapper version, JDK/GraalVM version, Spring Boot parent version, Native Build Tools version, OS và architecture.

**Bước 2 — Tạo profile.** Đặt ID `native`, khai báo Spring AOT execution và Native Build Tools execution theo tài liệu của phiên bản đang sử dụng.

**Bước 3 — Tập trung version.** Dùng parent/pluginManagement/property phù hợp. Loại bỏ các khai báo version trùng lặp và xác minh effective POM.

**Bước 4 — Truyền tham số.** Chọn image name và các build option qua property có mapping rõ ràng. Ghi lại lệnh CI chính xác.

**Bước 5 — Kiểm tra profile/config.** Chạy `help:active-profiles` và `help:effective-pom`; xác nhận profile, plugin version và execution.

**Bước 6 — Build và test.** Chạy native compile, native smoke tests, so sánh endpoint với bản JVM, sau đó đo readiness và RSS trên cùng môi trường.

Bảng kết quả mẫu:

| Đầu vào/đầu ra | Giá trị cần ghi |
|---|---|
| Maven Wrapper | Version |
| JDK/GraalVM | Distribution, version, architecture |
| Spring Boot parent | Version |
| Native Build Tools | Version |
| Maven profile | ID được kích hoạt |
| Spring profile cho AOT | Giá trị và cách truyền |
| Native Image args | Danh sách option thực tế |
| Artifact | Tên và đường dẫn executable |
| Kiểm thử | JVM/native pass-fail |
| Đo hiệu năng | Readiness, RSS, workload và số lần chạy |

## 13. Kết luận

Maven parameters, profiles và plugin versions là các đầu vào quan trọng của quá trình Spring Boot Native Image. **`-P` chọn cấu hình build, `-D` truyền property, Spring profile chọn cấu hình ứng dụng, còn plugin version quyết định cách Maven thực thi các goal.** Dùng parent POM và `pluginManagement` đúng cách giúp quản lý tập trung, nhưng cần kiểm tra effective POM để xác nhận cấu hình cuối cùng.

Khi build native, hãy pin version và môi trường, truyền tham số có mapping rõ ràng, xác minh Spring AOT nhận đúng cấu hình, rồi chạy lại bộ kiểm thử trên executable native. Quy trình đó giúp local và CI tạo artifact nhất quán, đồng thời làm cho kết quả đo startup/bộ nhớ có thể giải thích và tái lập.
