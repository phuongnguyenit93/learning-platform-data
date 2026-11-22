# Cấu hình annotation processor và plugin phân tích mã

Trong build Java, annotation processor và plugin phân tích mã phục vụ hai mục đích khác nhau. Annotation processor chạy trong quá trình biên dịch để đọc annotation, kiểm tra mô hình kiểu hoặc sinh thêm source code. Plugin phân tích mã kiểm tra source hoặc bytecode để phát hiện vấn đề về style, cấu trúc, lỗi tiềm ẩn và chất lượng mã.

Với Java 21, cần cấu hình rõ annotation processor thay vì dựa vào việc compiler tự dò processor trên classpath. JDK 21 vẫn bật cơ chế dò ngầm và phát note cảnh báo; từ JDK 23, cơ chế này bị tắt mặc định vì lý do bảo mật. Khai báo processor tường minh giúp build ổn định giữa các JDK và kiểm soát được mã nào được phép chạy trong môi trường CI.

## 1. Phân biệt annotation processor và static analysis plugin

| Thành phần | Thời điểm chạy | Đầu vào | Kết quả |
|---|---|---|---|
| Annotation processor | Trong compile hoặc test-compile | Annotation, element model, source/type information | Source, resource hoặc metadata được sinh ra; có thể báo lỗi compile |
| Checkstyle | Thường trước hoặc trong verify/check | Java source | Vi phạm quy tắc định dạng và coding style |
| PMD | Trong verify/check | Java source và thông tin kiểu nếu được cấu hình | Vi phạm quy tắc code, độ phức tạp, lỗi cấu trúc và duplicate code qua CPD |
| SpotBugs | Sau khi compile | Bytecode .class | Cảnh báo bug pattern, lỗi API, concurrency và một số vấn đề bảo mật |
| Error Prone | Trong compile | Java source và compiler model | Diagnostic cho các lỗi hoặc mẫu code nguy hiểm |

Ví dụ annotation processor phổ biến:

- MapStruct sinh mapper implementation từ interface có annotation @Mapper.
- Hibernate Processor sinh JPA metamodel từ entity.
- Lombok can thiệp quá trình compile để cung cấp thành viên được sinh từ annotation.

Ví dụ static analysis:

- Checkstyle kiểm tra quy tắc đặt tên, import, format và cấu trúc source.
- PMD phát hiện code phức tạp, nhánh dư thừa, API sử dụng sai mẫu và code trùng lặp qua CPD.
- SpotBugs phân tích bytecode để tìm bug pattern mà kiểm tra cú pháp thông thường không phát hiện.

Không đưa annotation processor vào runtime classpath chỉ vì compiler cần nó. Processor là chương trình được thực thi trong lúc build; dependency của ứng dụng và dependency của compiler nên được khai báo ở đúng scope.

## 2. Thay đổi annotation processing cần biết khi dùng JDK 21

Trong JDK 21, javac vẫn tự tìm processor trên classpath nếu annotation processing chưa bị tắt. Khi phát hiện processor được chạy theo cách ngầm định này, compiler in note nhắc rằng hành vi mặc định có thể thay đổi ở bản JDK sau.

Các tùy chọn liên quan:

| Tùy chọn | Ý nghĩa |
|---|---|
| -processor A,B | Chỉ định tên các processor cần chạy, bỏ qua cơ chế dò mặc định |
| --processor-path | Chỉ định classpath dùng để tìm processor |
| --processor-module-path | Chỉ định module path dùng để tìm processor dạng module |
| -proc:full | Chạy annotation processing rồi tiếp tục biên dịch |
| -proc:only | Chỉ chạy annotation processing, không biên dịch source |
| -proc:none | Tắt annotation processing |
| -Akey=value | Truyền option riêng cho processor |

Từ JDK 23, javac không tự dò và chạy annotation processor nếu build không yêu cầu rõ ràng. Muốn build tiếp tục sinh code, cần chỉ định processor, processor path/module path hoặc bật processing bằng -proc:full/-proc:only.

Vì vậy, khi build bằng Java 21 nhưng có khả năng chạy trên JDK mới hơn, hãy khai báo processor cụ thể và đường dẫn processor. Dùng -proc:full chỉ khi chủ đích là cho phép dò toàn bộ processor có trên classpath. Cách này có thể thực thi processor ẩn được kéo vào từ dependency bắc cầu, nên không phải lựa chọn mặc định an toàn.

Nếu module không sử dụng annotation processor, hãy tắt processing bằng -proc:none. Điều này tránh chạy nhầm processor chỉ vì một dependency đưa file service provider vào classpath.

## 3. Cấu hình annotation processor trực tiếp với javac

Ví dụ dùng MapStruct: annotation API nằm trên compile classpath, còn processor được đặt riêng trên processor path:

~~~shell
javac --release 21 \
  -classpath mapstruct-1.6.3.jar \
  --processor-path mapstruct-processor-1.6.3.jar \
  -processor org.mapstruct.ap.MappingProcessor \
  -Amapstruct.defaultComponentModel=spring \
  -s target/generated-sources \
  -d target/classes \
  src/main/java/com/example/OrderMapper.java
~~~

Các phần quan trọng:

- --release 21 chọn ngôn ngữ, API Java SE và bytecode theo Java 21.
- -classpath cung cấp annotation API và dependency cần cho source.
- --processor-path cung cấp processor cùng dependency lúc chạy processor.
- -processor chỉ định processor được phép chạy.
- -A... truyền option riêng cho MapStruct.
- -s chọn thư mục chứa source được sinh.
- -d chọn thư mục class output.

Nếu processor được đóng gói thành module, dùng --processor-module-path theo cấu trúc module của nó. Không đặt đồng thời cùng một processor trên nhiều path nếu không có lý do rõ ràng.

Lưu ý: annotation processor được thực thi trong JVM chạy compiler, không phải trong môi trường API mà --release lựa chọn cho source. Vì vậy, --release 21 không làm cho processor biên dịch bằng JDK mới hơn tự chạy được trên JDK 21. Hãy kiểm tra bytecode version và yêu cầu JDK tối thiểu của processor cùng các dependency của nó.

Khi cần chẩn đoán compiler, có thể thêm:

~~~shell
javac -XprintRounds -XprintProcessorInfo ...
~~~

Hai tùy chọn này giúp quan sát các vòng annotation processing và processor nào được gọi. Chúng hữu ích khi code generated không xuất hiện, processor không nhận annotation hoặc nhiều processor tương tác với nhau.

## 4. Cấu hình Maven 3 với Maven Compiler Plugin 3.x

Với Maven 3 và Maven Compiler Plugin 3.x, dùng annotationProcessorPaths để giới hạn processor được tìm thấy. Ví dụ sau dùng MapStruct:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.mapstruct</groupId>
        <artifactId>mapstruct</artifactId>
        <version>1.6.3</version>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <release>21</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.mapstruct</groupId>
                        <artifactId>mapstruct-processor</artifactId>
                        <version>1.6.3</version>
                    </path>
                </annotationProcessorPaths>
                <compilerArgs>
                    <arg>-Amapstruct.defaultComponentModel=spring</arg>
                </compilerArgs>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

mapstruct là API mà source ứng dụng tham chiếu; mapstruct-processor chỉ chạy trong compile. Compiler Plugin chỉ dò processor trong annotationProcessorPaths, vì vậy các dependency runtime khác không vô tình trở thành processor.

Nếu muốn chỉ định class processor rõ hơn, có thể cấu hình annotationProcessors:

~~~xml
<annotationProcessors>
    <annotationProcessor>org.mapstruct.ap.MappingProcessor</annotationProcessor>
</annotationProcessors>
~~~

Chỉ thêm phần này khi biết chính xác tên processor và muốn khóa danh sách processor được gọi. Khi có nhiều processor, liệt kê đầy đủ tên tương ứng.

Với Maven Compiler Plugin 3.x, annotationProcessorPaths được hỗ trợ từ phiên bản 3.5. Nên dùng phiên bản plugin đã hỗ trợ JDK 21 và có xử lý tùy chọn proc phù hợp. Tránh dựa vào classpath scanning mặc định chỉ để làm mất note của JDK 21.

## 5. Maven 4 và Maven Compiler Plugin 4.x

Maven Compiler Plugin 4.x chuyển sang khai báo processor như dependency có type riêng. Cách này giúp phân biệt processor với dependency ứng dụng và cho phép chọn classpath hay module path:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.mapstruct</groupId>
        <artifactId>mapstruct</artifactId>
        <version>1.6.3</version>
    </dependency>

    <dependency>
        <groupId>org.mapstruct</groupId>
        <artifactId>mapstruct-processor</artifactId>
        <version>1.6.3</version>
        <type>classpath-processor</type>
    </dependency>
</dependencies>
~~~

Các type được hỗ trợ:

- processor: plugin tự suy luận nên đặt processor ở classpath hay module path.
- classpath-processor: đặt processor trên classpath.
- modular-processor: đặt processor trên module path.

Khi đã biết processor được thiết kế cho classpath hay module path, khai báo type tường minh giúp build có thể dự đoán được. Trong Maven Compiler Plugin 4.x, annotationProcessorPaths của cấu hình 3.x đã bị deprecated để chuyển sang dependency type mới. Không trộn hai cách khai báo nếu không cần thiết.

## 6. Cấu hình processor trong Gradle

Gradle có configuration riêng tên annotationProcessor. Processor được đặt ở configuration này sẽ đi vào processor path của Java compile task, không tự động trở thành dependency runtime của ứng dụng.

Ví dụ với Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation 'org.mapstruct:mapstruct:1.6.3'
    annotationProcessor 'org.mapstruct:mapstruct-processor:1.6.3'

    // Chỉ khai báo nếu test source cũng dùng annotation cần processor.
    testAnnotationProcessor 'org.mapstruct:mapstruct-processor:1.6.3'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
    options.compilerArgs += [
        '-Amapstruct.defaultComponentModel=spring'
    ]
}
~~~

Với processor như Lombok, annotation API thường cần có ở compile time trong khi processor cũng cần chạy trong compilation:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:1.18.42'
    annotationProcessor 'org.projectlombok:lombok:1.18.42'

    testCompileOnly 'org.projectlombok:lombok:1.18.42'
    testAnnotationProcessor 'org.projectlombok:lombok:1.18.42'
}
~~~

Hãy chọn phiên bản processor đã công bố hỗ trợ JDK 21. Ví dụ Lombok chỉ minh họa cách phân scope; phiên bản cụ thể cần được quản lý tập trung và cập nhật theo ma trận tương thích của thư viện.

Gradle cung cấp configuration riêng cho từng source set. annotationProcessor phục vụ source chính; testAnnotationProcessor phục vụ test source. Nếu một processor chỉ được dùng trong test, không cần thêm nó vào processor path của main compilation.

## 7. Annotation processing và incremental build

Annotation processor có thể ảnh hưởng đến tốc độ incremental compilation. Gradle hỗ trợ incremental annotation processing cho processor khai báo metadata loại xử lý trong file:

META-INF/gradle/incremental.annotation.processors

Ví dụ metadata cho một processor isolating:

~~~text
com.example.processor.MapperProcessor,isolating
~~~

Tên processor phải là fully qualified class name đúng với implementation. Một processor tạo output từ nhiều type đầu vào có thể cần khai báo aggregating. Nếu processor không thuộc hai dạng này hoặc không công bố metadata, hãy để Gradle xử lý như processor không incremental.

Các loại chính:

| Loại processor | Ý nghĩa | Ví dụ hành vi |
|---|---|---|
| Isolating | Output được tạo từ một input cụ thể | Sinh một mapper implementation từ một interface mapper |
| Aggregating | Output phụ thuộc nhiều input | Tạo registry hoặc index tổng hợp từ nhiều annotated type |
| Không khai báo incremental | Gradle không thể xác định phạm vi output an toàn | Có thể làm compilation phải chạy lại toàn bộ |

Chỉ đánh dấu processor là isolating hoặc aggregating nếu implementation thật sự tuân thủ hợp đồng đó. Khai báo sai có thể khiến build cache hoặc incremental compilation giữ output không đúng.

Khi build chậm bất thường, chạy Gradle với --info để xem processor nào làm mất incremental compilation. Đối chiếu với tài liệu processor trước khi tự viết metadata cho thư viện bên thứ ba.

Với Maven, compiler plugin quản lý thư mục generated source, mặc định thường là target/generated-sources/annotations. Không cần tự thêm cùng thư mục vào source root nhiều lần nếu plugin đã đăng ký nó. Generated source thường không nên commit vào repository trừ khi dự án có chính sách reproducible generation riêng.

## 8. Quản lý option và output của processor

Mỗi processor có thể định nghĩa option riêng, thường được truyền qua -Akey=value. Hãy quản lý option cùng version processor để developer, local build và CI tạo ra output giống nhau.

Ví dụ:

~~~xml
<compilerArgs>
    <arg>-Amapstruct.defaultComponentModel=spring</arg>
    <arg>-Amapstruct.suppressGeneratorTimestamp=true</arg>
</compilerArgs>
~~~

Các nguyên tắc:

- Đặt option ở build file dùng chung, không yêu cầu từng developer tự truyền tay.
- Không đặt secret, token hoặc credential trong compiler option vì log build có thể hiển thị chúng.
- Đặt output generated source vào thư mục build được xóa bởi clean.
- Đảm bảo code generated được compile trong cùng build và được IDE nhận diện.
- Khi processor tạo resource, kiểm tra resource có được đóng gói vào đúng artifact hay không.
- Không để hai processor sinh cùng một tên file hoặc cùng một type.

Nếu processor không chạy, kiểm tra thứ tự: dependency có resolve không, processor path có đúng không, processor có hỗ trợ annotation đó không, option có đúng không và compiler có báo lỗi trong processing round hay không.

## 9. Static analysis plugin kiểm tra điều gì?

Các công cụ phân tích mã có phạm vi khác nhau:

| Công cụ | Phạm vi | Dùng khi |
|---|---|---|
| Checkstyle | Quy tắc source và style | Muốn chuẩn hóa format, naming, import, header và cấu trúc |
| PMD | Quy tắc source, design và code smell | Muốn phát hiện logic phức tạp, code dư, lỗi mẫu và duplicate code qua CPD |
| SpotBugs | Bytecode sau compile | Muốn tìm bug pattern, nullness, concurrency và API misuse |
| Error Prone | Compile-time source analysis | Muốn phát hiện lỗi Java ngay trong compiler diagnostics |

Không bật tất cả rules ở mức nghiêm ngặt ngay trong một lần nếu repository đang có nhiều vi phạm cũ. Hãy thống nhất ruleset, chạy báo cáo baseline, xử lý dần và đặt ngưỡng CI cho vi phạm mới hoặc nhóm lỗi nghiêm trọng.

## 10. Cấu hình Checkstyle, PMD và SpotBugs trong Maven

Ví dụ sau gắn các kiểm tra vào phase verify. CI cần chạy mvn verify hoặc lifecycle cao hơn để các goal này được thực thi:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-checkstyle-plugin</artifactId>
            <version>3.6.0</version>
            <configuration>
                <configLocation>config/checkstyle/checkstyle.xml</configLocation>
                <encoding>UTF-8</encoding>
                <consoleOutput>true</consoleOutput>
                <failOnViolation>true</failOnViolation>
            </configuration>
            <executions>
                <execution>
                    <id>checkstyle-verify</id>
                    <phase>verify</phase>
                    <goals>
                        <goal>check</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-pmd-plugin</artifactId>
            <version>3.28.0</version>
            <configuration>
                <rulesets>
                    <ruleset>config/pmd/ruleset.xml</ruleset>
                </rulesets>
                <failOnViolation>true</failOnViolation>
            </configuration>
            <executions>
                <execution>
                    <id>pmd-verify</id>
                    <phase>verify</phase>
                    <goals>
                        <goal>check</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>

        <plugin>
            <groupId>com.github.spotbugs</groupId>
            <artifactId>spotbugs-maven-plugin</artifactId>
            <version>4.10.5.0</version>
            <configuration>
                <effort>Max</effort>
                <threshold>Medium</threshold>
            </configuration>
            <executions>
                <execution>
                    <id>spotbugs-verify</id>
                    <phase>verify</phase>
                    <goals>
                        <goal>check</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Các version trong ví dụ là version minh họa có tài liệu hỗ trợ. Hãy pin version plugin theo dependency policy của tổ chức và cập nhật có kiểm soát. Ruleset checkstyle.xml và ruleset.xml là file do dự án quản lý; cần review thay đổi ruleset như review code.

Vai trò các goal:

- checkstyle:check báo vi phạm và có thể làm build fail.
- pmd:check chạy PMD và làm build fail khi vượt ngưỡng vi phạm.
- spotbugs:check chạy phân tích bytecode và làm build fail khi tìm thấy bug theo cấu hình.

Nếu chỉ đặt plugin trong reporting, Maven tạo báo cáo site nhưng không có nghĩa goal đã được đưa vào build gate. Muốn CI fail theo kết quả, hãy cấu hình execution trong build như ví dụ.

## 11. Cấu hình plugin phân tích mã trong Gradle

Gradle cung cấp Checkstyle và PMD plugin tích hợp. SpotBugs được thêm qua plugin riêng:

~~~groovy
plugins {
    id 'java'
    id 'checkstyle'
    id 'pmd'
    id 'com.github.spotbugs' version '6.5.13'
}

checkstyle {
    toolVersion = '10.24.0'
    configFile = file('config/checkstyle/checkstyle.xml')
    maxWarnings = 0
}

pmd {
    toolVersion = '7.24.0'
    ruleSetFiles = files('config/pmd/ruleset.xml')
    consoleOutput = true
}

spotbugs {
    toolVersion = '4.10.5'
}
~~~

Các task của Checkstyle và PMD được nối vào task check; SpotBugs Gradle plugin cũng tạo task theo source set và nối chúng vào check. Chạy:

~~~shell
./gradlew --no-daemon clean check
~~~

Để build có thể tái lập, giữ plugin version, tool version và ruleset trong source control. Kiểm tra compatibility matrix giữa Gradle wrapper, plugin và JDK dùng để chạy Gradle; options.release = 21 cho Java compilation không tự bảo đảm mọi plugin bên ngoài hỗ trợ runtime của Gradle.

## 12. Tách source generated khỏi source do developer viết

Code generated thường không cần áp dụng toàn bộ quy tắc style như code do developer viết. Nếu không loại trừ, Checkstyle hoặc PMD có thể báo hàng loạt lỗi ở file được sinh tự động và làm báo cáo khó sử dụng.

Một chính sách thực tế:

- Phân biệt src/main/java, src/test/java và thư mục generated source.
- Chạy Checkstyle trên source do developer quản lý; loại generated source nếu ruleset không áp dụng cho code sinh.
- Quyết định rõ PMD có phân tích generated source hay không, dựa trên việc code đó có được đóng gói và bảo trì như code sản phẩm không.
- SpotBugs phân tích bytecode đã compile; cân nhắc loại trừ package generated chỉ khi đã xác định false positive và lưu lý do.
- Không loại trừ toàn bộ package hoặc module chỉ để làm build xanh.

Nếu code generated có bug hoặc API misuse, sửa template, annotation hoặc processor tạo ra nó. Sửa trực tiếp file generated thường bị ghi đè ở lần compile kế tiếp.

## 13. Thiết kế CI gate theo từng giai đoạn

Một pipeline phù hợp có thể chia thành các bước:

1. **Resolve và compile:** dùng JDK/toolchain đã pin, chạy annotation processor đã khai báo, compile với --release 21.
2. **Unit và integration test:** xác nhận code generated có mặt, test source cũng chạy processor nếu cần.
3. **Source analysis:** chạy Checkstyle và PMD trên source đã chọn.
4. **Bytecode analysis:** chạy SpotBugs sau compile.
5. **Report và gate:** lưu report làm artifact CI, fail build theo severity/threshold đã thống nhất.

Lệnh CI mẫu:

~~~shell
mvn -B clean verify
~~~

Hoặc:

~~~shell
./gradlew --no-daemon clean check
~~~

Nếu repository có technical debt từ trước, ghi nhận baseline trước khi bật gate nghiêm ngặt. Có thể bắt đầu bằng báo cáo không fail, sau đó fail theo lỗi priority cao hoặc vi phạm mới. Khi đã có baseline ổn định, không âm thầm tăng số lỗi được phép; mọi ngoại lệ cần có owner, lý do và thời hạn xử lý.

## 14. Bảo mật và tính tái lập của build

Annotation processor là code thực thi trong tiến trình build. Processor có thể đọc source, truy cập file và môi trường mà tài khoản CI được phép truy cập. Vì vậy:

- Chỉ khai báo processor thực sự cần thiết.
- Pin version và kiểm tra nguồn gốc dependency.
- Tránh để processor được phát hiện ngầm từ toàn bộ compile classpath.
- Không cấp credential production cho build job chạy processor.
- Dùng dependency verification/checksum và lockfile nếu hệ thống build hỗ trợ.
- Tách cache build giữa các nhánh hoặc môi trường khi chính sách yêu cầu.
- Giữ generated source và báo cáo phân tích trong thư mục build có thể tái tạo.

Static analysis plugin cũng là executable dependency. Plugin và engine version phải được review, pin và cập nhật như các dependency khác.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| JDK 21 in note về implicit annotation processing | Processor được tìm từ compile classpath mà build chưa cấu hình rõ | Khai báo annotationProcessorPaths, --processor-path hoặc processor name |
| Build chạy trên JDK 21 nhưng mất generated source khi nâng lên JDK mới | JDK 23+ tắt implicit processor discovery | Khai báo processor rõ ràng; không phụ thuộc default cũ |
| Processor không tìm thấy annotation | Processor path hoặc dependency API bị thiếu | Tách API dependency và processor dependency, kiểm tra đúng source set |
| Processor chạy nhưng không sinh code | Annotation không khớp, option sai hoặc processor lỗi | Dùng -XprintRounds, -XprintProcessorInfo và kiểm tra compiler output |
| Test compile thiếu generated class | Chỉ cấu hình processor cho main source set | Thêm test processor configuration nếu test source dùng annotation |
| Build Gradle không incremental | Processor không khai báo incremental metadata hoặc metadata sai | Kiểm tra tài liệu processor và log --info |
| CI báo nhiều lỗi từ generated source | Static analysis đang quét output sinh tự động | Cấu hình include/exclude theo source set, giữ nguyên kiểm tra source thật |
| Build xanh local nhưng fail CI | Plugin/tool version, JDK hoặc ruleset khác nhau | Pin JDK, wrapper, plugin, engine và cấu hình |

## 16. Checklist cấu hình

- [ ] Xác định processor nào thật sự cần cho main và test source.
- [ ] Tách annotation API khỏi processor artifact và runtime dependency.
- [ ] Khai báo processor path/module path hoặc processor name tường minh.
- [ ] Không dựa vào implicit classpath scanning khi build có thể chạy trên JDK 23+.
- [ ] Dùng -proc:none cho module không cần annotation processing.
- [ ] Dùng -Akey=value để quản lý processor options tập trung.
- [ ] Chọn output directory generated source được build tool quản lý.
- [ ] Kiểm tra incremental metadata nếu dùng Gradle.
- [ ] Pin Maven/Gradle plugin, analyzer engine và ruleset.
- [ ] Tách Checkstyle, PMD và SpotBugs theo mục đích phân tích.
- [ ] Loại generated source khỏi rule không phù hợp, nhưng không che giấu lỗi code sản phẩm.
- [ ] Chạy mvn verify hoặc gradle check trong CI để thực thi build gate.
- [ ] Lưu report, theo dõi baseline và quản lý ngoại lệ có owner.
- [ ] Không cấp quyền hoặc secret production không cần thiết cho build processor/plugin.

Cấu hình tốt giúp compiler chỉ chạy những annotation processor đã được dự án chấp thuận, còn các plugin phân tích mã tạo ra cổng chất lượng có thể lặp lại trên máy developer và CI. Với Java 21, hãy khai báo processor tường minh ngay từ đầu để tránh phụ thuộc vào implicit discovery đã thay đổi ở JDK 23, đồng thời pin plugin, tool version và ruleset để build giữ cùng một hành vi qua các lần nâng cấp.

## Tài liệu tham khảo

- [Oracle JDK 21 Release Notes — Implicit Annotation Processing](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html)
- [Oracle Java SE 21 — javac Command and Annotation Processing](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [Oracle JDK 23 Release Notes — Annotation Processing Disabled by Default](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html)
- [Apache Maven Compiler Plugin 3.14.1 — Annotation Processor Paths](https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.14.1/compile-mojo.html)
- [Apache Maven Compiler Plugin 4.x — Annotation Processors](https://maven.apache.org/plugins/maven-compiler-plugin-4.x/examples/annotation-processor.html)
- [Gradle Java Plugin — Annotation Processor Configuration](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle Checkstyle Plugin](https://docs.gradle.org/current/userguide/checkstyle_plugin.html)
- [Gradle PMD Plugin](https://docs.gradle.org/current/userguide/pmd_plugin.html)
- [SpotBugs Maven Plugin](https://spotbugs.github.io/spotbugs-maven-plugin/usage.html)
- [SpotBugs Gradle Plugin](https://spotbugs.readthedocs.io/en/stable/gradle.html)
- [Apache Maven Checkstyle Plugin](https://maven.apache.org/plugins/maven-checkstyle-plugin/usage.html)
- [Apache Maven PMD Plugin](https://maven.apache.org/plugins/maven-pmd-plugin/usage.html)
