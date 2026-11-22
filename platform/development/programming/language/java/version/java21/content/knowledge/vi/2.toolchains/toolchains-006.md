# Đồng bộ JDK giữa IDE, build tool, test runner và production

Một dự án Java 21 chỉ thực sự có cấu hình nhất quán khi mã nguồn được biên dịch theo Java 21, các bài test chạy trên JDK đã định, IDE sử dụng đúng SDK, build tool chọn đúng compiler/test launcher và môi trường production có runtime tương thích. Chỉ đặt `JAVA_HOME` thành JDK 21 chưa bảo đảm tất cả những điều đó, vì IDE, Gradle, Maven và ứng dụng có thể khởi chạy bằng các JVM khác nhau.

Bài này trình bày cách thiết lập một baseline Java 21 có thể lặp lại trên máy lập trình viên, CI và production. Các ví dụ dùng Gradle và Maven hiện hành; hãy pin phiên bản wrapper và plugin mà dự án đã xác nhận tương thích.

## 1. Phân biệt các JDK/JVM trong một dự án

Trước khi cấu hình, cần nhận diện từng tiến trình sử dụng Java nào. Một máy có thể cài nhiều JDK cùng lúc và mỗi công cụ có lựa chọn riêng.

| Thành phần | JVM/JDK được dùng để làm gì? | Nơi cần cấu hình |
|---|---|---|
| IDE Project SDK | Phân tích mã, gợi ý API, biên dịch hoặc chạy trực tiếp từ IDE | Project SDK và language level |
| IDE build-tool JVM | Khởi chạy Gradle hoặc Maven khi IDE ủy quyền build cho công cụ đó | Gradle JVM hoặc Maven Runner JRE |
| Gradle daemon / Maven process | Chạy chính build tool và các plugin | JVM khởi chạy wrapper, hoặc cấu hình daemon/tool phù hợp |
| Compiler toolchain | Chạy `javac` để biên dịch source | Gradle Java toolchain hoặc Maven Toolchains |
| Test launcher | Chạy JVM fork để thực thi unit/integration test | Gradle test toolchain hoặc plugin Maven hỗ trợ toolchain |
| Production runtime | Chạy ứng dụng đã đóng gói | JDK/JRE trên máy chủ hoặc runtime image |

Hai điểm thường gây nhầm lẫn:

- **JVM chạy build tool không nhất thiết là compiler JDK.** Ví dụ, Gradle daemon có thể chạy trên một JDK tương thích với phiên bản Gradle đang dùng, trong khi Java toolchain chọn JDK 21 để biên dịch và chạy test.
- **Mức tương thích của bytecode không tự chọn JVM chạy test.** Cấu hình compiler nhắm Java 21 giúp kiểm soát ngôn ngữ, bytecode và API được phép dùng; test launcher vẫn cần được cấu hình hoặc xác minh riêng.

Với dự án có baseline Java 21, hợp đồng kỹ thuật nên được ghi rõ:

1. Mã nguồn được biên dịch với JDK 21.
2. Compiler giới hạn ngôn ngữ và API ở Java 21 bằng `--release 21`.
3. Unit test và integration test chạy trên Java 21, trừ khi dự án chủ động kiểm thử nhiều runtime.
4. CI dùng wrapper của dự án và chọn JDK 21 theo cùng quy tắc.
5. Production chạy trên Java 21 hoặc một runtime mới hơn đã được kiểm thử và phê duyệt.
6. JDK distribution và chính sách cập nhật bản vá được thống nhất trong nhóm.

Java 21 là một bản phát hành LTS. Khi chọn JDK để cài đặt, hãy dùng một distribution được tổ chức hỗ trợ, chẳng hạn Eclipse Temurin, Amazon Corretto, Azul Zulu hoặc Oracle JDK. Không cần mọi thành viên phải dùng cùng nhà cung cấp trong mọi trường hợp, nhưng nên thống nhất distribution cho CI và production; nếu ứng dụng phụ thuộc hành vi riêng của nhà cung cấp, hãy kiểm thử trên đúng distribution đó.

## 2. Cấu hình IDE

IDE thường có nhiều lựa chọn Java độc lập. Hãy kiểm tra cả SDK của project, JVM chạy build tool và JRE của cấu hình Run/Debug.

### Project SDK và language level

Đặt Project SDK là JDK 21 và language level là Java 21. Việc này giúp IDE hiểu đúng cú pháp, kiểu dữ liệu và API của baseline dự án.

Nếu IDE hỗ trợ đồng bộ cấu hình từ Gradle hoặc Maven, hãy refresh/reimport project sau khi thay đổi build file. Cấu hình trong IDE cần phản ánh cấu hình build của repository để tránh tình trạng IDE báo hợp lệ nhưng CI lại biên dịch bằng một mức Java khác.

### JVM chạy Gradle hoặc Maven trong IDE

- Với Gradle, đặt **Gradle JVM** thành JDK tương thích với phiên bản Gradle Wrapper. Nếu wrapper hỗ trợ chạy trên Java 21, có thể dùng JDK 21 để giảm khác biệt giữa máy lập trình viên và CI.
- Với Maven, kiểm tra **Maven Runner JRE** hoặc lựa chọn JRE dùng để chạy Maven. JVM này khởi chạy Maven; Maven Toolchains có thể chọn một JDK khác cho compiler và các plugin hỗ trợ toolchain.
- Với cấu hình Run/Debug chạy ứng dụng trực tiếp từ IDE, đặt JRE là JDK 21 hoặc cấu hình project SDK. Đây là lựa chọn riêng, không nên mặc định rằng nó luôn theo test toolchain.

Nếu dự án sử dụng Gradle hoặc Maven làm nguồn cấu hình build chính, nên để IDE ủy quyền build và test cho công cụ tương ứng. Cách này giúp thao tác trong IDE sử dụng cùng task, compiler options và test runtime với CI. Nếu nhóm chủ động dùng compiler/test runner tích hợp của IDE, hãy đồng bộ các lựa chọn Java tương đương và ghi rõ trong hướng dẫn phát triển.

Tên và vị trí menu có thể thay đổi theo phiên bản IDE; các mục cần kiểm tra vẫn là Project SDK, language level, Gradle JVM/Maven Runner JRE và JRE của Run/Debug configuration.

## 3. Cấu hình Gradle Java toolchain

Java toolchain cho Gradle chỉ định JDK mà các task Java cần dùng. Với Java plugin, cấu hình toolchain được áp dụng cho các task biên dịch, test và tạo Javadoc tương ứng.

Ví dụ với Kotlin DSL trong `build.gradle.kts`:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 21
}
```

Cấu hình trên có hai mục đích:

- `languageVersion = 21` yêu cầu Gradle tìm JDK 21 làm toolchain cho các task Java.
- `options.release = 21` yêu cầu compiler tuân theo API và định dạng bytecode của Java 21. Đây là cách rõ ràng để đặt baseline tương thích của source code.

Nếu dự án có task test tự định nghĩa hoặc cần thể hiện rõ launcher cho một task đặc biệt, có thể cấu hình launcher như sau:

```kotlin
tasks.withType<Test>().configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Với các task `Test` thông thường của Java plugin, toolchain đã cấu hình thường được Gradle sử dụng tự động. Đoạn cấu hình launcher tường minh hữu ích khi muốn kiểm soát task test riêng, chẳng hạn task integration test được đăng ký bổ sung. Hãy áp dụng cùng quy tắc cho mọi task chạy JVM do dự án tự tạo.

### JVM chạy Gradle daemon

Toolchain không đồng nghĩa với JVM chạy Gradle daemon. JVM của daemon phải nằm trong phạm vi tương thích mà phiên bản Gradle Wrapper hỗ trợ. Có thể xem JVM của Gradle bằng:

```bash
./gradlew --version
```

Liệt kê các toolchain Gradle nhận diện được bằng:

```bash
./gradlew -q javaToolchains
```

Nếu Gradle không tìm thấy JDK 21, hãy cài đặt JDK 21 hoặc cấu hình cơ chế phân giải/tải toolchain mà tổ chức cho phép. Không nên giả định mọi bản Gradle đều tự tải JDK khi thiếu toolchain; khả năng tự cấp phát phụ thuộc cấu hình resolver và chính sách mạng của môi trường.

Giữ Gradle Wrapper trong repository và yêu cầu thành viên/CI chạy `./gradlew` thay vì một bản Gradle cài toàn cục. Wrapper giúp thống nhất phiên bản build tool; toolchain giúp thống nhất JDK mà task Java sử dụng. Hai cấu hình này giải quyết hai vấn đề khác nhau.

## 4. Cấu hình Maven compiler và test toolchain

Với Maven, cần phân biệt JVM chạy Maven với JDK được các plugin sử dụng. `JAVA_HOME` thường quyết định JVM khởi chạy Maven. Maven Toolchains cho phép Maven chọn một JDK cụ thể cho các plugin có hỗ trợ toolchain, chẳng hạn Maven Compiler Plugin và Maven Surefire/Failsafe Plugin.

### Đặt Java release

Trong `pom.xml`, khai báo baseline:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Đảm bảo dự án pin một phiên bản Maven Compiler Plugin hiện hành có hỗ trợ thuộc tính `maven.compiler.release`. Thuộc tính `release` truyền lựa chọn tương ứng cho compiler, giới hạn cả cú pháp, bytecode và API Java được phép tham chiếu theo Java 21.

Chỉ đặt release không có nghĩa Maven sẽ tự chạy test bằng JDK 21. Để chọn JDK cho các plugin hỗ trợ toolchain, cấu hình Maven Toolchains Plugin.

### Khai báo JDK 21 cho Maven Toolchains

Ví dụ phần plugin trong `pom.xml`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-toolchains-plugin</artifactId>
            <version>3.3.0</version>
            <executions>
                <execution>
                    <goals>
                        <goal>toolchain</goal>
                    </goals>
                </execution>
            </executions>
            <configuration>
                <toolchains>
                    <jdk>
                        <version>21</version>
                    </jdk>
                </toolchains>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Maven Toolchains Plugin 3.3.0 vẫn hỗ trợ goal `toolchain` cùng file `toolchains.xml` như ví dụ trên. Plugin cũng có goal `select-jdk-toolchain` để tự phát hiện JDK cài trên máy và chọn theo version/vendor; có thể dùng goal này khi môi trường build cho phép cơ chế tự phát hiện. Với CI cần kiểm soát chính xác đường dẫn JDK, khai báo toolchain tường minh giúp việc lựa chọn dễ dự đoán hơn.

Maven cần biết vị trí JDK 21 trên từng máy. Khai báo toolchain trong file `~/.m2/toolchains.xml` của người dùng hoặc tạo file này trong CI:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
        </provides>
        <configuration>
            <jdkHome>/absolute/path/to/jdk-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Thay đường dẫn mẫu bằng thư mục JDK 21 thực tế của môi trường. Không commit đường dẫn tuyệt đối phụ thuộc máy cá nhân vào repository. CI cần cài JDK 21 và cung cấp toolchains file tương ứng trước khi chạy Maven.

Khi toolchain được chọn, các plugin có hỗ trợ toolchain có thể dùng JDK đó. Maven Compiler Plugin dùng nó để biên dịch; Surefire và Failsafe có thể dùng toolchain để chạy unit test và integration test. Hãy kiểm tra phiên bản plugin mà dự án đang pin và log build để xác nhận chúng thực sự nhận toolchain.

Lệnh sau cho biết JVM đang chạy Maven:

```bash
./mvnw -version
```

Kết quả này không tự chứng minh compiler hoặc test fork đang dùng cùng JDK. Khi cần chẩn đoán lựa chọn toolchain, chạy build với log chi tiết:

```bash
./mvnw -X test
```

Dùng Maven Wrapper (`./mvnw`) để cố định phiên bản Maven giữa máy cá nhân và CI. Không dựa vào Maven cài toàn cục vì mỗi máy có thể dùng phiên bản khác nhau.

## 5. Đồng bộ test runner

Test runner là một điểm cấu hình độc lập cần được kiểm tra. Một dự án có thể biên dịch bằng JDK 21 nhưng chạy test trên JVM khác nếu task test tùy chỉnh, IDE runner hoặc plugin Maven không dùng toolchain dự kiến.

Với Gradle, Java toolchain áp dụng cho các task `Test` do Java plugin quản lý. Kiểm tra thêm task integration test, test task do plugin khác tạo và task tự định nghĩa. Nếu task đó khởi chạy một JVM riêng, hãy chỉ định launcher JDK 21 rõ ràng.

Với Maven, xác nhận toolchain được chọn và các phiên bản Surefire/Failsafe đang dùng hỗ trợ nó. Nếu test được chạy trực tiếp bằng IDE, kiểm tra JRE của test configuration hoặc chuyển việc chạy test sang Gradle/Maven theo chuẩn của repository.

Một cách chẩn đoán đơn giản bên trong test là ghi nhận phiên bản runtime:

```java
System.out.println("Test runtime: " + Runtime.version());
```

Dùng thông tin này khi điều tra lỗi môi trường; không nhất thiết phải giữ câu lệnh in ra trong mọi test. Nếu nhóm cố ý kiểm thử trên nhiều Java version, hãy khai báo ma trận runtime đó trong CI và ghi rõ phiên bản nào là baseline production.

## 6. Đồng bộ CI với máy lập trình viên

CI cần thực hiện cùng quy trình mà nhóm dùng ở local:

1. Checkout repository và sử dụng Gradle Wrapper hoặc Maven Wrapper đã commit.
2. Cài đặt distribution JDK 21 theo chính sách của tổ chức.
3. Đặt `JAVA_HOME` và `PATH` để wrapper khởi chạy bằng JVM phù hợp.
4. Cung cấp Maven `toolchains.xml` nếu dự án dùng Maven Toolchains.
5. Chạy build và test qua wrapper.
6. Kiểm tra log để xác nhận compiler/test task chọn đúng JDK.

Ví dụ lệnh kiểm tra với Gradle:

```bash
java -version
javac -version
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean test
```

Ví dụ với Maven:

```bash
java -version
javac -version
./mvnw -version
./mvnw -B -ntp clean verify
```

Các lệnh `java -version` và `javac -version` phản ánh lệnh được phân giải qua môi trường shell hiện tại. `gradlew --version` hoặc `mvnw -version` cho biết JVM chạy build tool. Kết hợp với báo cáo toolchain và log task, chúng giúp phát hiện việc một máy đang dùng nhầm JDK.

Không nên chỉ kiểm tra một lần ở bước setup rồi giả định toàn bộ pipeline đã nhất quán. Các module con, task tùy chỉnh và job integration test có thể có cấu hình riêng. Nếu CI dùng ma trận nhiều JDK để kiểm tra khả năng tương thích, hãy tách rõ job kiểm thử bổ sung với job xác nhận baseline Java 21.

## 7. Chọn runtime cho production

Ứng dụng được biên dịch cho Java 21 cần runtime tương thích với bytecode và API mà ứng dụng sử dụng. Với cấu hình `--release 21`, class file được tạo theo mức Java 21; runtime cũ hơn Java 21 không thể chạy class file này. Nếu production dùng runtime cũ, lỗi có thể xuất hiện dưới dạng `UnsupportedClassVersionError`.

Với triển khai bằng container, có thể dùng JDK image ở build stage và runtime image Java 21 ở stage cuối. Ví dụ minh họa với Maven và Eclipse Temurin:

```dockerfile
FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace
COPY . .
RUN ./mvnw -B -ntp clean package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/target/app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Thay `target/app.jar` bằng tên artifact thực tế của dự án. Nếu ứng dụng cần công cụ JDK trong production để phục vụ tác vụ vận hành đã xác định, hãy chọn runtime image có các công cụ đó; nếu chỉ chạy ứng dụng, runtime image nhỏ hơn thường phù hợp hơn.

Để tái lập môi trường release, hãy:

- Dùng Java 21 runtime image được tổ chức phê duyệt.
- Pin image theo tag cụ thể và digest trong quy trình phát hành khi cần tính tái lập.
- Cập nhật bản vá bảo mật định kỳ thay vì giữ một image cũ vô thời hạn.
- Kiểm tra phiên bản Java ngay trong image hoặc môi trường triển khai, không chỉ kiểm tra JDK ở build stage.
- Chạy smoke test hoặc integration test trên đúng major runtime và distribution production sử dụng.

Nếu production chạy trên máy ảo hoặc máy chủ vật lý, thực hiện kiểm tra tương tự bằng `java -version` trong đúng user, service unit và môi trường khởi chạy ứng dụng. Dịch vụ có thể nhận một `PATH` hoặc `JAVA_HOME` khác với terminal đăng nhập của quản trị viên.

## 8. Nhận diện và xử lý lỗi lệch JDK

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| IDE không nhận cú pháp/API Java 21 | Project SDK hoặc language level thấp hơn 21 | Đặt Project SDK và language level là 21, sau đó đồng bộ lại project |
| IDE chạy được nhưng CI biên dịch thất bại | IDE dùng compiler/JDK khác với build tool của repository | Chạy build bằng wrapper ở local; kiểm tra toolchain và compiler release |
| Gradle không khởi động được sau khi đổi JDK | JVM của Gradle daemon không tương thích với phiên bản Gradle Wrapper | Xem `./gradlew --version`, kiểm tra ma trận tương thích và cấu hình JVM chạy daemon |
| Maven chạy bằng JDK mong muốn nhưng compiler dùng JDK khác | Maven process và Maven Toolchains là hai lựa chọn riêng | Kiểm tra `mvnw -version`, `toolchains.xml` và log chọn toolchain |
| Build thành công nhưng test chạy trên Java khác | IDE test runner hoặc task/plugin test không nhận toolchain | Kiểm tra test launcher, Surefire/Failsafe và runtime thực tế trong test |
| Ứng dụng lỗi `UnsupportedClassVersionError` ở production | Runtime production cũ hơn mức bytecode đã biên dịch | Kiểm tra Java trong đúng môi trường triển khai và nâng runtime lên mức tương thích |
| Ứng dụng biên dịch được nhưng lỗi khi gọi API mới | Compiler chỉ đặt source/target mà không giới hạn API bằng release | Dùng `--release 21` thông qua Gradle `options.release` hoặc Maven `maven.compiler.release` |

Khi đổi JDK, hãy khởi động lại IDE hoặc daemon nếu công cụ vẫn giữ tiến trình JVM cũ. Với Gradle, có thể dừng daemon bằng:

```bash
./gradlew --stop
```

Sau đó chạy lại wrapper và kiểm tra phiên bản JVM. Với Maven, mỗi lần chạy wrapper thường khởi tạo process mới; nếu Maven được gọi từ IDE hoặc service lâu dài, hãy kiểm tra lại JVM mà tiến trình đó đang giữ.

## 9. Checklist trước khi merge hoặc phát hành

- [ ] Repository pin Gradle Wrapper hoặc Maven Wrapper.
- [ ] Project SDK và language level trong IDE là Java 21.
- [ ] JVM chạy Gradle/Maven tương thích với phiên bản build tool đã pin.
- [ ] Compiler toolchain chọn JDK 21.
- [ ] Compiler dùng `--release 21` để giới hạn API và bytecode.
- [ ] Unit test và integration test chạy trên JDK 21 theo baseline dự án.
- [ ] CI cài đúng distribution JDK, cung cấp toolchain config và chạy wrapper.
- [ ] Run/Debug configuration trong IDE dùng runtime đã thống nhất.
- [ ] Production image hoặc máy chủ chạy runtime Java 21 tương thích.
- [ ] Bản vá JDK và runtime image có lịch cập nhật, kiểm thử và phát hành rõ ràng.

Khi cần kiểm tra nhanh, hãy xác minh từng lớp theo thứ tự: IDE SDK → JVM của wrapper/daemon → compiler toolchain → test launcher → runtime production. Ghi nhận phiên bản ở từng lớp sẽ giúp tìm đúng điểm lệch thay vì thay đổi ngẫu nhiên `JAVA_HOME`.

## Tài liệu tham khảo chính thức

- [Gradle: Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Maven: Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Apache Maven Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/)
- [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Maven Surefire Plugin: Using Toolchains](https://maven.apache.org/surefire/maven-surefire-plugin/examples/toolchains.html)
- [Oracle: Java SE 21 Documentation](https://docs.oracle.com/en/java/javase/21/)

