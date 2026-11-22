# Đồ thị phụ thuộc thay đổi dù mã nguồn không thay đổi

Một commit có thể giữ nguyên toàn bộ mã nguồn nhưng hai lần build vẫn phân giải ra các đồ thị phụ thuộc khác nhau. Ứng dụng có thể nhận một phiên bản thư viện mới, một dependency bắc cầu khác, một variant khác hoặc một plugin khác chỉ vì repository đã cập nhật metadata, một selector động được phân giải lại, cấu hình môi trường thay đổi hoặc cache hết hạn.

Điều này ảnh hưởng trực tiếp đến tính tái lập của build. Nếu chỉ lưu commit mã nguồn mà không kiểm soát các đầu vào bên ngoài, cùng một commit chưa chắc tạo ra cùng classpath hoặc artifact. Để điều tra và ngăn hiện tượng này, cần hiểu đồ thị phụ thuộc được tạo như thế nào, yếu tố nào có thể thay đổi nó, và cơ chế nào giúp cố định phiên bản cũng như xác minh nội dung artifact.

## 1. Đồ thị phụ thuộc là gì?

Đồ thị phụ thuộc (dependency graph) mô tả các module mà một project cần, các phiên bản được yêu cầu, quan hệ bắc cầu giữa chúng và cách công cụ build chọn thành phần để đưa vào từng configuration hoặc classpath.

Ví dụ:

    application
       |----> reporting-client:2.1
       |          +----> shared-core:1.8
       |
       +----> http-adapter:1.4
                  +----> shared-core:2.0

Đồ thị ban đầu có hai đường dẫn tới shared-core. Công cụ build áp dụng quy tắc phân giải để chọn phiên bản phù hợp. Kết quả đó ảnh hưởng tới compile classpath, runtime classpath, test classpath hoặc các configuration khác.

Đồ thị phụ thuộc khác với task graph:

- **Dependency graph** cho biết thư viện/module nào được sử dụng và phiên bản/variant nào được chọn.
- **Task graph** cho biết những bước build nào được chọn và thứ tự thực hiện chúng.

Thay đổi dependency graph có thể làm thay đổi đầu vào của task biên dịch, kiểm thử hoặc đóng gói. Task graph cũng có thể thay đổi do build script, plugin hoặc điều kiện môi trường, nhưng đó là một loại thay đổi khác.

## 2. Vì sao mã nguồn không đổi nhưng dependency graph vẫn đổi?

Mã nguồn ứng dụng chỉ là một phần đầu vào của quá trình phân giải. Dependency graph còn phụ thuộc vào:

- Các phiên bản được khai báo trực tiếp và các dependency bắc cầu trong metadata của thư viện.
- Quy tắc version selector, version range, constraint và conflict resolution.
- Nội dung và metadata hiện tại của remote repository.
- Chính sách cập nhật và cache cục bộ.
- POM, Gradle Module Metadata hoặc metadata khác mà repository cung cấp.
- Repository order, mirror, profile và nội dung repository được phép phục vụ.
- Cấu hình plugin, settings, version catalog và convention plugin.
- Thuộc tính variant như target JVM, operating system, architecture và usage.
- Các rule tùy chỉnh trong build script hoặc init script.

Vì vậy, hai lần build có thể dùng cùng commit nhưng nhận được những dependency khác nhau. Đôi khi khác biệt đến từ một thay đổi có chủ ý của nhóm; đôi khi nó xuất hiện âm thầm do một selector linh động hoặc repository có nội dung thay đổi.

## 3. Selector động và version range

### Phiên bản động trong Gradle

Gradle cho phép khai báo các selector linh động, ví dụ:

    dependencies {
        implementation 'com.example:shared-core:1.+'
        implementation 'com.example:http-client:latest.release'
    }

Selector **1.+** cho phép Gradle chọn một version phù hợp mới nhất trong dòng 1.x theo metadata mà repository cung cấp. Selector **latest.release** yêu cầu một release mới nhất theo quy tắc của Gradle và metadata.

Giả sử hôm nay repository có:

    shared-core:1.8
    shared-core:1.9

Build có thể chọn 1.9. Sau đó nhóm phát hành 1.10. Khi cache hết hạn hoặc Gradle làm mới dependency, cùng selector 1.+ có thể chọn 1.10 dù build script và mã nguồn ứng dụng không thay đổi.

Đây là nguồn gây drift rõ ràng: version được chọn phụ thuộc vào thời điểm phân giải và nội dung repository.

### Version range trong Maven

Maven hỗ trợ version range, ví dụ:

    <dependency>
        <groupId>com.example</groupId>
        <artifactId>shared-core</artifactId>
        <version>[1.8,2.0)</version>
    </dependency>

Range này cho phép các version từ 1.8 trở lên nhưng nhỏ hơn 2.0. Nếu repository bổ sung một version mới trong khoảng đó, kết quả phân giải có thể thay đổi tùy metadata, trạng thái local cache và quy tắc chọn version của Maven.

Version range có thể hữu ích khi một thư viện tương thích với nhiều phiên bản, nhưng làm giảm khả năng dự đoán nếu không ghi lại kết quả đã chọn.

### Không nên nhầm selector động với dependency bắc cầu

Một dependency có version cố định vẫn có thể làm đồ thị thay đổi nếu metadata của chính artifact đó bị thay đổi hoặc bị thay thế. Ví dụ, POM của một thư viện release có thể bị ghi đè để khai báo một dependency mới. Khi đó, tọa độ và version trực tiếp không đổi nhưng cây dependency bắc cầu đã đổi.

Điều này vi phạm kỳ vọng thông thường rằng release artifact là bất biến. Repository release nên ngăn việc ghi đè cùng một tọa độ đã phát hành.

## 4. SNAPSHOT và changing module

### Maven SNAPSHOT

Dependency:

    <dependency>
        <groupId>com.example</groupId>
        <artifactId>catalog-api</artifactId>
        <version>2.4.0-SNAPSHOT</version>
    </dependency>

không trỏ tới một nội dung duy nhất trong suốt vòng đời phát triển. Mỗi lần deploy snapshot có thể tạo một bản timestamped mới và cập nhật metadata. Cùng version logic 2.4.0-SNAPSHOT vì thế có thể phân giải tới các bytecode hoặc POM khác nhau theo thời điểm.

Nếu một snapshot mới thay đổi dependency bắc cầu trong POM, dependency graph của ứng dụng cũng có thể đổi dù POM của ứng dụng không đổi.

Maven dùng update policy và local metadata để quyết định khi nào kiểm tra bản snapshot mới. Tùy chọn:

    mvn -U clean verify

yêu cầu Maven kiểm tra cập nhật snapshot và artifact còn thiếu theo cơ chế của nó. Tùy chọn này có thể làm lộ khác biệt giữa hai lần build.

### Changing module trong Gradle

Gradle có khái niệm changing module cho dependency mà nội dung có thể thay đổi dù tọa độ không đổi. Dependency SNAPSHOT từ Maven repository thường được coi là changing theo mặc định.

Có thể khai báo rõ:

    dependencies {
        implementation('com.example:catalog-api:2.4.0-SNAPSHOT') {
            changing = true
        }
    }

Gradle cache metadata và artifact của changing module theo một khoảng thời gian. Có thể cấu hình thời gian cache:

    configurations.configureEach {
        resolutionStrategy.cacheChangingModulesFor 0, 'seconds'
    }

Thiết lập này yêu cầu Gradle kiểm tra changing module thường xuyên hơn, nhưng có thể làm tăng số request tới repository và thời gian build. Trong môi trường phát triển, cập nhật thường xuyên có thể hữu ích; trong CI phát hành, nên ưu tiên dependency bất biến và đầu vào được cố định.

## 5. Metadata repository có thể làm thay đổi đồ thị

Khi phân giải dependency, công cụ build không chỉ tải JAR. Nó cần metadata để biết module phụ thuộc vào những gì và có thể cung cấp những variant nào.

Các nguồn metadata phổ biến:

- POM của Maven.
- Gradle Module Metadata.
- Metadata version và snapshot của repository.
- Metadata được tạo hoặc biến đổi bởi repository manager.

Ví dụ, version 1.5 của một thư viện ban đầu có POM khai báo:

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>logging-api</artifactId>
            <version>3.0</version>
        </dependency>
    </dependencies>

Nếu cùng tọa độ release 1.5 bị deploy lại với POM yêu cầu logging-api:4.0, đồ thị bắc cầu có thể thay đổi mà ứng dụng không sửa dependency trực tiếp.

Đây là lý do repository release nên bất biến. Một tọa độ release chỉ nên được publish một lần; khi metadata hoặc nội dung cần thay đổi, hãy phát hành version mới.

Repository manager cũng có thể cache metadata từ upstream. Khi upstream cập nhật, cache của repository manager và cache cục bộ có thể cập nhật ở những thời điểm khác nhau. Vì vậy, hai máy cùng dùng một URL repository manager vẫn có thể nhìn thấy trạng thái metadata khác nhau trong một khoảng thời gian.

## 6. Thứ tự repository và nguồn artifact

Một module cùng tọa độ có thể xuất hiện ở nhiều repository. Thay đổi thứ tự repository, mirror hoặc content filter có thể khiến công cụ tìm thấy module ở một nguồn khác.

Với Gradle, repository được khai báo theo thứ tự và nguồn tìm thấy module ảnh hưởng nơi tải artifact. Nếu repository nội bộ chứa một module cùng tọa độ với một repository công khai, thay đổi thứ tự hoặc phạm vi nội dung có thể làm thay đổi nguồn metadata và artifact.

Ví dụ:

    repositories {
        maven {
            url = uri('https://repo.example.com/releases/')
        }
        mavenCentral()
    }

Nếu module được tìm thấy trong repository đầu tiên, Gradle gắn module với nguồn đó. Việc thay đổi repository order hoặc nội dung repository có thể làm thay đổi kết quả phân giải.

Với Maven, repository được kết hợp từ POM, parent POM, profile và settings; mirror trong settings.xml có thể thay URL được truy cập. Nếu hai môi trường có settings.xml hoặc mirror khác nhau, chúng có thể tải metadata từ các nguồn khác nhau.

Để tránh nguồn không mong muốn:

- Dành group nội bộ cho repository nội bộ.
- Giới hạn nội dung repository theo group hoặc module khi công cụ hỗ trợ.
- Dùng exclusive content trong Gradle khi module chỉ được phép đến từ một nguồn.
- Dùng mirror và repository manager tập trung trong Maven.
- Không cho phép ghi đè release.
- Ghi lại nguồn và checksum artifact khi cần truy vết.

## 7. Dependency conflict resolution có thể chọn kết quả khác

Ngay cả khi các dependency yêu cầu giống nhau, quy tắc giải quyết xung đột cũng có thể thay đổi kết quả khi cấu hình build thay đổi.

### Maven nearest definition

Maven thường dùng quy tắc nearest definition: version ở đường dẫn gần project gốc hơn được ưu tiên. Nếu hai yêu cầu có cùng độ sâu, thứ tự khai báo có thể ảnh hưởng kết quả.

Ví dụ:

    application
       +----> client-a
       |          +----> shared-core:1.8
       |
       +----> client-b
                  +----> transport
                             +----> shared-core:2.0

Version 1.8 nằm gần hơn nên có thể được chọn. Nếu dependency trực tiếp hoặc thứ tự cây thay đổi, kết quả có thể khác.

### Gradle conflict resolution

Gradle mặc định thường chọn version cao hơn trong các version yêu cầu cho cùng module, có xét đến constraints và resolution rules. Nếu một plugin hoặc build script thêm constraint, force hoặc rule mới, kết quả có thể thay đổi dù khai báo dependency trực tiếp không đổi.

Ví dụ:

    dependencies {
        implementation 'com.example:shared-core:1.8'
        implementation 'com.example:http-adapter:2.0'
    }

Nếu http-adapter yêu cầu shared-core:2.1, Gradle có thể chọn 2.1. Sau đó, một constraint strict hoặc platform được thêm vào có thể giới hạn version được phép.

### Platform và BOM

Maven dependencyManagement hoặc BOM, Gradle platform/BOM và dependency constraints có thể đồng bộ hoặc giới hạn version của nhiều module. Khi version của BOM thay đổi, nhiều node trong đồ thị có thể thay đổi cùng lúc dù các dependency khai báo riêng lẻ không đổi.

Vì vậy, khi điều tra graph drift, cần kiểm tra cả BOM, parent POM, version catalog, constraints và rule resolution, không chỉ dòng implementation hoặc dependency trong module.

## 8. Variant selection và thuộc tính môi trường

Gradle có thể chọn variant của một module dựa trên thuộc tính của consumer và producer. Các thuộc tính có thể gồm:

- Usage: compile hay runtime.
- Category: library, platform hoặc documentation.
- Target JVM version.
- Operating system hoặc architecture trong các hệ sinh thái hỗ trợ.
- Các attribute tùy chỉnh do plugin khai báo.

Ví dụ một thư viện có variant cho JVM 17 và JVM 21. Consumer yêu cầu target JVM 17 có thể nhận variant tương ứng; consumer target JVM 21 có thể nhận variant khác. Vì thế, hai máy dùng cùng tọa độ dependency nhưng cấu hình toolchain hoặc attribute khác nhau có thể chọn variant khác.

Đây không nhất thiết là lỗi. Đó có thể là kết quả đúng của variant-aware dependency management. Tuy nhiên, nếu mục tiêu là tái lập build, cần cố định các thuộc tính ảnh hưởng tới variant selection, đặc biệt target JVM, usage và platform.

Maven truyền thống không có cùng mô hình variant selection như Gradle Module Metadata, nhưng profile, classifier, packaging và dependency metadata vẫn có thể làm thay đổi artifact được chọn.

## 9. Plugin và build logic cũng là dependency

Mã nguồn ứng dụng có thể không đổi nhưng plugin build thay đổi. Plugin có thể:

- Thêm hoặc cập nhật dependency vào configuration.
- Thay đổi repository hoặc metadata source.
- Thay đổi quy tắc conflict resolution.
- Thêm variant attribute hoặc task.
- Thay đổi cách compiler, test runner hoặc packaging hoạt động.

Với Gradle, plugin được phân giải qua pluginManagement và có thể kéo theo dependency riêng. Cần cố định version plugin trong plugins DSL hoặc version catalog; tránh selector động cho plugin trong build phát hành.

Với Maven, Maven plugin cũng có dependency riêng và nên được khai báo version rõ ràng. Plugin version không cố định có thể khiến hành vi build thay đổi khi metadata repository cập nhật.

Các build script, convention plugin, init script và plugin portal/repository là đầu vào của build. Chỉ khóa dependency ứng dụng mà bỏ qua plugin build vẫn chưa đủ để tái lập toàn bộ quá trình.

## 10. Profile, settings và môi trường có thể thay đổi đồ thị

Hai lần build cùng commit có thể dùng cấu hình hiệu lực khác nhau do:

- Maven settings.xml khác nhau giữa máy phát triển và CI.
- Maven profile được kích hoạt bởi OS, JDK, property hoặc file tồn tại.
- Maven mirror hoặc repository credentials khác nhau.
- Gradle init script thay đổi repository hoặc dependency resolution.
- settings.gradle thay đổi project, plugin repository hoặc dependency resolution management.
- Biến môi trường hoặc Gradle property làm bật/tắt dependency.
- Version catalog hoặc convention plugin được lấy từ nguồn khác.
- JDK/toolchain và attribute môi trường khác nhau làm thay đổi variant được chọn.

Ví dụ Maven profile:

    <profiles>
        <profile>
            <id>use-company-client</id>
            <activation>
                <property>
                    <name>companyClient</name>
                </property>
            </activation>
            <dependencies>
                <dependency>
                    <groupId>com.company</groupId>
                    <artifactId>client</artifactId>
                    <version>3.1.0</version>
                </dependency>
            </dependencies>
        </profile>
    </profiles>

Chạy với property:

    mvn verify -DcompanyClient=true

có thể làm dependency graph khác với lần chạy không kích hoạt profile.

Với Gradle, dependency có thể được thêm theo property hoặc cấu hình build. Cách này có thể hợp lý cho các môi trường khác nhau, nhưng phải ghi nhận rõ cấu hình nào được dùng trong từng pipeline.

## 11. Cache làm kết quả thay đổi theo thời điểm

Cache giúp giảm truy cập mạng và tăng tốc build, nhưng cũng khiến hai máy có thể quan sát trạng thái repository khác nhau trong một khoảng thời gian.

### Maven local repository

Maven lưu artifact và metadata trong local repository. Với release bất biến, cache thường có thể được tái sử dụng. Với SNAPSHOT và version range, update policy quyết định khi nào Maven kiểm tra lại remote.

Tùy chọn:

    mvn -U dependency:resolve

yêu cầu Maven kiểm tra cập nhật snapshot và artifact còn thiếu. Nó hữu ích để chẩn đoán khi local metadata cũ, nhưng cũng có thể làm dependency graph thay đổi nếu remote đã cập nhật.

### Gradle dependency cache

Gradle cache metadata và artifact đã phân giải. Dynamic version và changing module có cache policy riêng. Khi thời gian cache hết hạn, Gradle có thể kiểm tra repository lại và chọn version hoặc nội dung mới.

Có thể yêu cầu làm mới:

    ./gradlew build --refresh-dependencies

Lệnh này làm mới trạng thái dependency theo cơ chế của Gradle. Nó không đảm bảo tải lại từng byte nếu Gradle xác định nội dung đã cache vẫn hợp lệ.

### Cache không phải nguồn sự thật lâu dài

Một build thành công trên máy đã cache không chứng minh một máy sạch sẽ phân giải ra cùng graph. Để xác nhận tính tái lập, nên chạy thử trên workspace sạch hoặc CI mới với cùng cấu hình repository, lockfile và toolchain.

## 12. Khóa dependency graph trong Gradle

Gradle hỗ trợ dependency locking để ghi lại các version đã được chọn cho những configuration được khóa. Khi build sau phân giải lại, lock state giúp ngăn version selector hoặc dependency mới tự động làm thay đổi phiên bản đã được ghi.

Có thể bật locking cho mọi configuration:

    dependencyLocking {
        lockAllConfigurations()
    }

Sau đó chạy một task có phân giải các configuration và yêu cầu ghi lock state:

    ./gradlew build --write-locks

Gradle có thể tạo hoặc cập nhật tệp **gradle.lockfile** cho các dependency configuration đã được khóa và giải quyết trong lần chạy đó.

Lockfile thường ghi tọa độ module và version được chọn. Nó giúp cố định version nhưng không thay thế kiểm tra nội dung artifact. Nếu repository cho phép ghi đè cùng tọa độ release, cùng version vẫn có thể trỏ tới byte khác nhau.

### Cập nhật lockfile có chủ đích

Khi muốn nâng dependency:

1. Thay đổi version selector, constraint hoặc BOM phù hợp.
2. Chạy task cần thiết với **--write-locks**.
3. Xem diff của gradle.lockfile.
4. Kiểm tra dependencyInsight và test.
5. Commit lockfile cùng thay đổi build có chủ đích.

Không nên cập nhật lockfile một cách tự động mà không xem version nào thay đổi. Diff lockfile là bằng chứng hữu ích để review tác động của việc nâng dependency.

### Locking và plugin

Dependency locking chủ yếu áp dụng cho các dependency configuration được khóa trong project. Plugin resolution ở settings/pluginManagement và build logic có thể có cơ chế riêng; không nên giả định gradle.lockfile đã khóa mọi plugin và mọi thành phần của build. Hãy cố định plugin version và kiểm soát build logic riêng.

## 13. Quản lý version trong Maven

Maven không có dependency lockfile tích hợp tương đương Gradle dependency locking theo cùng mô hình. Có thể tăng tính ổn định bằng cách:

- Dùng version cố định thay vì version range hoặc SNAPSHOT cho build cần tái lập.
- Quản lý version tập trung bằng dependencyManagement hoặc BOM.
- Cố định version Maven plugin trong build/plugins và pluginManagement.
- Dùng release repository bất biến, không cho ghi đè tọa độ đã phát hành.
- Kiểm tra cây dependency trong CI.
- Dùng Maven Enforcer để phát hiện dependency convergence hoặc version không được phép.
- Lưu effective POM, dependency tree và thông tin môi trường build khi cần truy vết.

Ví dụ Enforcer có thể phát hiện dependency version không hội tụ:

    <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-enforcer-plugin</artifactId>
        <version>3.5.0</version>
        <executions>
            <execution>
                <id>enforce-dependency-convergence</id>
                <goals>
                    <goal>enforce</goal>
                </goals>
                <configuration>
                    <rules>
                        <dependencyConvergence/>
                    </rules>
                </configuration>
            </execution>
        </executions>
    </plugin>

Rule này phát hiện một số dạng version không hội tụ, nhưng không phải lockfile và không chứng minh artifact bytes bất biến. Nó là một gate kiểm tra cấu trúc dependency.

## 14. Khóa nội dung artifact bằng dependency verification

Khóa version giúp xác định tọa độ dependency, nhưng không bảo đảm nội dung của artifact không bị thay thế. Để kiểm tra nội dung, cần checksum hoặc chữ ký.

### Gradle dependency verification

Gradle hỗ trợ dependency verification qua metadata trong thư mục **gradle/verification-metadata.xml**. Có thể tạo metadata checksum ban đầu bằng:

    ./gradlew --write-verification-metadata sha256 help

Lệnh trên có thể ghi nhận checksum cho dependency được resolve trong quá trình chạy. Cần review tệp được tạo, xác nhận nguồn và commit metadata đáng tin cậy.

Ở các lần build sau, Gradle có thể kiểm tra nội dung artifact theo checksum đã ghi. Nếu artifact cùng tọa độ bị thay đổi, xác minh có thể thất bại.

Không nên xem việc tự động sinh checksum từ một nguồn không được xác minh là bảo đảm an toàn. Nếu artifact đã bị thay thế trước lần tạo metadata đầu tiên, checksum mới có thể ghi nhận nội dung sai. Việc review nguồn và bảo vệ repository vẫn rất quan trọng.

### Maven checksum và signature

Maven repository thường cung cấp checksum cho artifact. Maven có thể kiểm tra checksum theo cấu hình và transport. Đối với yêu cầu xác thực mạnh hơn, có thể dùng chữ ký GPG hoặc cơ chế xác minh do repository manager và CI cung cấp.

Checksum xác nhận dữ liệu tải về khớp giá trị checksum đã công bố; nó không tự chứng minh người phát hành là đáng tin cậy nếu nguồn checksum cũng bị kiểm soát bởi cùng một bên không đáng tin.

## 15. Cố định plugin, wrapper và toolchain

Dependency graph của ứng dụng chỉ là một phần của môi trường build. Để build tái lập hơn, cần kiểm soát công cụ và plugin.

### Gradle Wrapper

Commit các tệp wrapper:

    gradlew
    gradlew.bat
    gradle/wrapper/gradle-wrapper.properties
    gradle/wrapper/gradle-wrapper.jar

Trong gradle-wrapper.properties, cố định distribution URL tới một phiên bản Gradle cụ thể. Không dùng URL trỏ tới phiên bản động hoặc latest nếu mục tiêu là tái lập.

### Maven Wrapper

Commit các script và cấu hình Maven Wrapper do dự án sử dụng, bao gồm wrapper properties và các thành phần cần thiết để khởi chạy wrapper.

### Plugin version

Khai báo version plugin rõ ràng. Tránh version động hoặc không xác định nếu build cần tái lập. Plugin có thể kéo thêm dependency và thay đổi hành vi resolution.

### Java toolchain

Gradle có thể chọn JDK theo toolchain:

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(21)
        }
    }

Cố định toolchain giúp kiểm soát compiler và thuộc tính target JVM. Nó không tự khóa dependency bên ngoài, nhưng có thể ảnh hưởng variant selection nếu module công bố variant theo JVM version.

## 16. Ghi lại đồ thị để so sánh hai lần build

Khi nghi ngờ graph drift, trước tiên hãy lưu lại kết quả phân giải ở hai lần build để so sánh.

### Maven

Xuất dependency tree:

    mvn dependency:tree -DoutputFile=dependency-tree.txt

Xuất effective POM:

    mvn help:effective-pom -Doutput=effective-pom.xml

Xem profile đang hoạt động:

    mvn help:active-profiles

So sánh các tệp giữa hai lần build để tìm:

- Version trực tiếp hoặc bắc cầu thay đổi.
- Dependency mới hoặc bị loại.
- Scope thay đổi.
- Profile khác nhau.
- Repository hoặc plugin khác nhau.

### Gradle

Xem graph của configuration:

    ./gradlew dependencies --configuration runtimeClasspath

Giải thích một module cụ thể:

    ./gradlew dependencyInsight --dependency shared-core --configuration runtimeClasspath

Có thể xuất dependency report qua task hoặc plugin phù hợp nếu cần lưu artifact CI. Hãy so sánh cùng configuration; runtimeClasspath và compileClasspath có thể khác nhau hợp lệ.

### So sánh có ý nghĩa

Để phép so sánh hữu ích, cần chạy trong điều kiện tương đương:

- Cùng commit.
- Cùng Gradle/Maven wrapper version.
- Cùng JDK/toolchain.
- Cùng profile và build properties.
- Cùng repository/mirror policy.
- Cùng configuration hoặc task selector.
- Ghi nhận trạng thái cache và cờ refresh.

Nếu một trong các điều kiện này khác, graph khác nhau có thể là kết quả của cấu hình khác chứ không phải lỗi ngẫu nhiên.

## 17. Ví dụ: graph đổi do dynamic version

Giả sử build.gradle khai báo:

    dependencies {
        implementation 'com.example:json-core:3.+'
    }

Ngày đầu, repository có version 3.4.0 và 3.5.0. Gradle chọn 3.5.0. Một tuần sau, version 3.6.0 được publish. Khi cache hết hạn hoặc build dùng --refresh-dependencies, Gradle có thể chọn 3.6.0.

Mã nguồn không thay đổi nhưng:

    Lần A: json-core:3.5.0
    Lần B: json-core:3.6.0

Nếu 3.6.0 thay đổi API hoặc hành vi, kết quả test và artifact có thể khác. Cách kiểm soát là chọn version cố định hoặc dùng dependency locking để ghi nhận version được chọn. Nếu muốn nâng, cập nhật lockfile và review diff có chủ đích.

## 18. Ví dụ: graph đổi do metadata của SNAPSHOT

Giả sử application phụ thuộc vào catalog-api:2.4.0-SNAPSHOT. Lần deploy đầu tiên, POM của snapshot phụ thuộc vào shared-core:1.8. Lần deploy sau, nhóm catalog-api cập nhật POM để dùng shared-core:2.0 và triển khai lại cùng version logic.

Hai lần phân giải có thể là:

    Lần A:
      catalog-api:2.4.0-SNAPSHOT (timestamp A)
        +----> shared-core:1.8

    Lần B:
      catalog-api:2.4.0-SNAPSHOT (timestamp B)
        +----> shared-core:2.0

POM của application không đổi nhưng đồ thị dependency bắc cầu thay đổi. Với release build cần tái lập, nên dùng version release bất biến của catalog-api thay vì SNAPSHOT. Nếu cần build phát triển với SNAPSHOT, cần ghi lại bản timestamped cụ thể hoặc artifact checksum được sử dụng.

## 19. Ví dụ: graph đổi do profile hoặc môi trường

Một POM có profile thêm implementation theo môi trường:

    <profiles>
        <profile>
            <id>cloud</id>
            <activation>
                <property>
                    <name>deploymentTarget</name>
                    <value>cloud</value>
                </property>
            </activation>
            <dependencies>
                <dependency>
                    <groupId>com.example</groupId>
                    <artifactId>cloud-storage-client</artifactId>
                    <version>4.2.0</version>
                </dependency>
            </dependencies>
        </profile>
    </profiles>

Lệnh:

    mvn verify -DdeploymentTarget=cloud

có dependency graph khác với lệnh không truyền property. Mã nguồn và POM không đổi, nhưng môi trường build đã yêu cầu một cấu hình khác.

Đây có thể là thiết kế hợp lệ. Để tái lập, cần ghi lại property và profile dùng trong từng build, không chỉ lưu commit.

## 20. Quy trình chẩn đoán graph drift

Khi hai lần build cùng commit cho dependency graph khác nhau, hãy làm theo thứ tự:

1. **Xác nhận cùng mã nguồn:** so sánh commit và working tree.
2. **Xác nhận cùng công cụ:** wrapper, Maven/Gradle version, JDK và toolchain.
3. **Xác nhận cùng cấu hình:** profile, property, environment variable, init script, settings và version catalog.
4. **Xuất graph:** dùng dependency:tree hoặc dependencies/dependencyInsight.
5. **Tìm node thay đổi:** module nào được thêm, xóa hoặc đổi version/variant?
6. **Truy đường dẫn:** dependency nào kéo node đó vào và metadata nào yêu cầu version đó?
7. **Kiểm tra repository:** URL, mirror, content filter, metadata và artifact có thay đổi không?
8. **Kiểm tra selector:** dynamic version, range, SNAPSHOT hoặc changing module có đang được dùng không?
9. **Kiểm tra cache:** hai máy có cache state hoặc refresh policy khác nhau không?
10. **Chọn biện pháp kiểm soát:** pin version, lock dependency, cố định plugin, dùng repository bất biến hoặc xác minh checksum.

Không nên xóa toàn bộ cache ngay khi thấy graph khác. Làm vậy có thể thay đổi kết quả thêm một lần nữa và làm mất bằng chứng. Hãy lưu dependency report, effective configuration và log trước khi làm mới cache.

## 21. Thiết kế pipeline để tái lập dependency graph

Một pipeline có thể tăng độ tin cậy bằng cách:

- Dùng version cố định cho dependency và plugin trong build phát hành.
- Tránh dynamic version, version range và SNAPSHOT trong release build.
- Dùng Gradle dependency locking cho các configuration quan trọng.
- Dùng dependency verification để kiểm tra checksum/signature.
- Quản lý version qua Maven BOM/dependencyManagement hoặc Gradle platform/version catalog.
- Cố định repository và mirror, giới hạn nguồn cung cấp module.
- Không cho phép ghi đè release artifact.
- Commit wrapper và cấu hình toolchain.
- Ghi lại profile, property và biến môi trường ảnh hưởng dependency.
- Lưu dependency graph hoặc dependency report làm artifact của CI.
- Chạy build từ workspace sạch để phát hiện sự phụ thuộc vào cache cá nhân.

Đối với Maven, nơi chưa có lockfile tích hợp cùng mô hình như Gradle, cần kết hợp version pinning, dependencyManagement, repository bất biến, Enforcer và lưu báo cáo phân giải. Đối với Gradle, lockfile giúp cố định version nhưng vẫn cần plugin version, verification metadata và repository policy để kiểm soát đầy đủ hơn.

## 22. Reproducible dependency resolution và reproducible artifact

Hai khái niệm có liên quan nhưng không giống nhau:

### Dependency resolution có thể tái lập

Cùng đầu vào build và cùng cấu hình sẽ chọn cùng module, version và variant. Lockfile, version cố định, repository policy và metadata ổn định hỗ trợ mục tiêu này.

### Artifact build có thể tái lập

Cùng đầu vào sẽ tạo ra cùng nội dung artifact. Ngoài dependency graph, kết quả còn phụ thuộc:

- Compiler và JDK.
- Plugin và build tool version.
- Timestamp được nhúng vào archive.
- Thứ tự tệp trong archive.
- Locale, timezone và environment variables.
- Generated source và tài nguyên.
- Thông tin build được ghi vào manifest.

Một dependency graph giống nhau là điều kiện quan trọng nhưng chưa đủ để bảo đảm hai JAR có checksum giống hệt. Cần kiểm soát toàn bộ đầu vào và cách đóng gói nếu yêu cầu reproducible artifact ở mức byte.

## 23. Các lỗi thường gặp khi cố định dependency

### Chỉ pin dependency trực tiếp

Dependency bắc cầu vẫn có thể dùng selector động hoặc metadata thay đổi. Hãy kiểm tra toàn bộ graph và dùng locking hoặc version management phù hợp.

### Có lockfile nhưng repository release cho phép ghi đè

Lockfile ghi version, không tự bảo đảm bytes của artifact không đổi. Dùng repository bất biến và dependency verification.

### Chỉ cố định version catalog

Version catalog quản lý các alias và version được khai báo, nhưng không tự khóa mọi dependency bắc cầu. Kết hợp dependency locking nếu cần.

### Cập nhật lockfile không review

Lockfile có thể thay đổi nhiều node cùng lúc. Hãy xem diff, truy nguyên version mới và chạy test trước khi commit.

### Chỉ so sánh runtimeClasspath

Compile, test, annotationProcessor, plugin và các configuration khác có thể có graph riêng. So sánh đúng configuration mà task sử dụng.

### Dùng cache cũ làm bằng chứng tái lập

Máy cá nhân có thể build xanh nhờ cache trong khi máy sạch không thể phân giải cùng dependency. Kiểm tra trên workspace mới với cấu hình đã ghi nhận.

## 24. Bảng kiểm soát các nguồn gây thay đổi đồ thị

| Nguồn thay đổi | Dấu hiệu | Biện pháp kiểm soát |
| --- | --- | --- |
| Dynamic version | Version được chọn tăng theo thời gian | Pin version hoặc dependency locking |
| Version range | Repository có version mới trong khoảng | Pin version cụ thể, review nâng cấp |
| SNAPSHOT/changing module | Nội dung cùng tọa độ thay đổi | Dùng release bất biến, ghi nhận timestamp/checksum |
| POM/module metadata thay đổi | Dependency bắc cầu thêm hoặc đổi | Không ghi đè release, xác minh metadata |
| Repository order/mirror | Cùng tọa độ đến từ nguồn khác | Cố định repository, filter và mirror |
| Conflict rule/BOM/constraint | Version được chọn thay đổi | Quản lý tập trung và review rule |
| Variant attributes | Chọn variant khác theo JVM/OS/usage | Cố định toolchain và thuộc tính consumer |
| Plugin/build logic | Graph hoặc rule resolution thay đổi | Pin plugin và wrapper, review build logic |
| Profile/environment | Dependency chỉ xuất hiện ở một môi trường | Ghi lại profile và properties |
| Cache policy | Một máy nhận metadata mới, máy khác dùng cache cũ | Cấu hình cache rõ, kiểm thử trên workspace sạch |

## 25. Nguyên tắc thực hành

- Xem dependency graph là đầu vào của build, không chỉ là hệ quả của mã nguồn.
- Tránh selector động và SNAPSHOT trong build cần tái lập.
- Dùng release artifact bất biến và repository có chính sách không ghi đè.
- Cố định plugin, wrapper, toolchain và cấu hình build.
- Dùng dependency locking trong Gradle khi cần giữ version đã chọn.
- Dùng dependency verification để kiểm tra nội dung artifact.
- Với Maven, kết hợp dependencyManagement/BOM, Enforcer, version pinning và báo cáo graph.
- Ghi nhận profile, settings, repository và thuộc tính ảnh hưởng resolution.
- So sánh cùng configuration và cùng môi trường khi điều tra graph drift.
- Không xóa cache trước khi lưu bằng chứng về kết quả phân giải hiện tại.

Đồ thị phụ thuộc có thể thay đổi dù mã nguồn không đổi vì quá trình phân giải còn dựa vào metadata, repository, selector, plugin, cấu hình và môi trường. Muốn build tái lập, cần kiểm soát các đầu vào đó một cách có chủ đích: cố định version, dùng lockfile, xác minh artifact, giữ repository bất biến và ghi lại cấu hình phân giải. Khi đó, một commit có thể được build lại với cùng dependency graph và có cơ sở tốt hơn để tạo ra kết quả nhất quán.
