# Một thư viện xuất hiện qua nhiều đường phụ thuộc

Trong một dự án Java, một thư viện có thể được đưa vào build qua nhiều dependency khác nhau. Ví dụ, ứng dụng phụ thuộc vào thư viện giao diện; thư viện giao diện lại phụ thuộc vào thư viện logging. Đồng thời, một thư viện HTTP khác cũng phụ thuộc vào cùng thư viện logging nhưng yêu cầu một phiên bản khác. Khi đó, thư viện logging xuất hiện qua nhiều đường trong đồ thị phụ thuộc.

Đây là tình huống phụ thuộc bắc cầu (transitive dependency) và thường được gọi là xung đột phiên bản (dependency version conflict). Công cụ build phải quyết định phiên bản nào được dùng trên classpath, đồng thời phải bảo đảm các thành phần được biên dịch và chạy với một tập thư viện tương thích.

Hiểu cách một thư viện xuất hiện qua nhiều đường giúp giải thích vì sao một phiên bản được chọn, cách kiểm tra cây phụ thuộc, cách quản lý phiên bản tập trung và khi nào cần loại trừ một dependency. Không nên chỉ nhìn tên thư viện trong POM hoặc build script; cần xem toàn bộ đường đi dẫn đến thư viện đó.

## 1. Phụ thuộc trực tiếp và phụ thuộc bắc cầu

Một dependency là trực tiếp khi dự án khai báo sử dụng nó. Dependency bắc cầu được đưa vào thông qua một dependency khác.

Ví dụ, ứng dụng khai báo:

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>reporting-client</artifactId>
            <version>2.1.0</version>
        </dependency>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>http-adapter</artifactId>
            <version>1.4.0</version>
        </dependency>
    </dependencies>

Giả sử hai thư viện có dependency như sau:

    reporting-client:2.1.0
        +----> com.example:shared-utils:1.8

    http-adapter:1.4.0
        +----> com.example:shared-utils:2.0

Ứng dụng không khai báo trực tiếp shared-utils, nhưng thư viện này được yêu cầu qua cả reporting-client và http-adapter. Cây phụ thuộc có dạng:

    application
       |----> reporting-client:2.1.0
       |          +----> shared-utils:1.8
       |
       +----> http-adapter:1.4.0
                  +----> shared-utils:2.0

Hai đường dẫn cùng dẫn tới module có tọa độ groupId và artifactId giống nhau nhưng yêu cầu hai version khác nhau. Công cụ build cần áp dụng quy tắc phân giải để xác định version dùng chung.

## 2. Nhận diện một module trong đồ thị phụ thuộc

Trong Maven, một artifact thường được xác định bằng:

- **groupId:** nhóm hoặc tổ chức sở hữu artifact.
- **artifactId:** tên artifact.
- **version:** phiên bản.
- **type/packaging:** loại artifact, chẳng hạn jar hoặc pom.
- **classifier:** biến thể bổ sung nếu có.

Trong Gradle, một module bên ngoài thường được nhận diện bởi group, name và version. Khi phân tích xung đột, trước tiên cần xác định các đường dẫn có thực sự yêu cầu cùng một module hay không.

Hai thư viện có tên gần giống nhau chưa chắc là cùng module. Ví dụ:

    org.example:json-core
    org.example:json-adapter

là hai artifact khác nhau. Ngược lại, các yêu cầu:

    com.example:shared-utils:1.8
    com.example:shared-utils:2.0

đều nhắm đến cùng module com.example:shared-utils nhưng khác version.

Nếu groupId hoặc artifactId khác nhau, quy tắc chọn version cho cùng một module không tự động áp dụng giữa chúng, dù hai thư viện có thể cung cấp chức năng tương tự hoặc cùng tên lớp Java.

## 3. Vì sao một thư viện có thể xuất hiện qua nhiều đường?

Các thư viện được xây dựng theo tầng. Một thư viện công khai API của nó thường cần những thư viện khác để thực hiện công việc. Khi dự án sử dụng thư viện đó, các dependency được công bố có thể được kéo vào theo.

Một số nguyên nhân phổ biến:

### Nhiều thư viện dùng chung một nền tảng

Các thư viện logging, JSON, HTTP, annotation, collections hoặc utility thường được nhiều thành phần sử dụng. Mỗi thành phần có thể được phát triển ở thời điểm khác nhau và khai báo version khác nhau.

### Thư viện được nâng cấp không đồng bộ

Một thư viện A đã nâng dependency lên version mới, trong khi thư viện B chưa cập nhật và vẫn yêu cầu version cũ. Khi ứng dụng dùng cả A và B, đồ thị có thể chứa nhiều yêu cầu cho cùng module.

### Dependency bắc cầu nhiều tầng

Xung đột không nhất thiết nằm ngay dưới dependency trực tiếp. Một thư viện có thể xuất hiện ở tầng thứ ba hoặc thứ tư:

    application
       +----> client-a
       |          +----> protocol
       |                     +----> shared-core:1.6
       |
       +----> client-b
                  +----> transport
                             +----> shared-core:2.1

Nếu chỉ đọc các dependency trực tiếp trong POM, ta sẽ không thấy shared-core được yêu cầu bởi những đường dẫn nào.

### Dependency được khai báo từ nhiều module nội bộ

Trong build nhiều module, module web và module batch có thể cùng phụ thuộc vào một thư viện nền tảng. Khi đóng gói ứng dụng tổng hợp, các đường phụ thuộc có thể gặp nhau và cần được phân giải theo quy tắc của công cụ build.

## 4. Cách Maven chọn phiên bản: nearest definition

Maven dùng quy tắc mediation để giải quyết trường hợp cùng artifact được yêu cầu với nhiều version. Quy tắc cơ bản là **nearest definition**: phiên bản được khai báo ở đường dẫn gần dependency gốc nhất thường được chọn.

Ví dụ:

    application
       +----> client-a
       |          +----> shared-core:1.6
       |
       +----> client-b
                  +----> transport
                             +----> shared-core:2.1

Nếu application không khai báo shared-core trực tiếp, đường qua client-a có độ sâu 2, còn đường qua client-b và transport có độ sâu 3. Theo quy tắc nearest definition, Maven chọn shared-core:1.6 vì nó xuất hiện ở độ sâu gần hơn.

Điều này có thể gây bất ngờ: version số lớn hơn không nhất thiết được chọn. Maven ưu tiên khoảng cách trong đồ thị theo quy tắc mediation, không đơn giản chọn version mới nhất.

### Khi hai version ở cùng độ sâu

Nếu hai yêu cầu có cùng độ sâu, Maven chọn dependency được khai báo đầu tiên theo thứ tự trong POM khai báo ở cùng mức. Vì vậy, việc thay đổi thứ tự dependency có thể ảnh hưởng kết quả phân giải trong tình huống hòa về độ sâu.

Không nên dựa vào thứ tự khai báo để quản lý version lâu dài. Cách rõ ràng hơn là chỉ định version mong muốn bằng dependencyManagement hoặc khai báo dependency trực tiếp khi ứng dụng cần kiểm soát version đó.

### Khai báo trực tiếp để điều khiển version

Nếu ứng dụng khai báo trực tiếp:

    <dependency>
        <groupId>com.example</groupId>
        <artifactId>shared-core</artifactId>
        <version>2.1</version>
    </dependency>

thì dependency trực tiếp ở độ sâu 1 gần hơn các yêu cầu bắc cầu. Maven thường chọn version 2.1 cho shared-core trong đồ thị đó.

Đây là cách điều khiển mediation, nhưng nó cũng có nghĩa ứng dụng chủ động chịu trách nhiệm về tính tương thích của version đã chọn với các thư viện phụ thuộc.

## 5. Quản lý phiên bản bằng dependencyManagement

Maven cho phép quản lý version tập trung bằng phần **dependencyManagement**. Cấu hình này định nghĩa version và các thuộc tính dependency mà dự án muốn áp dụng khi dependency tương ứng được khai báo hoặc được kéo vào.

Ví dụ:

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example</groupId>
                <artifactId>shared-core</artifactId>
                <version>2.1</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

Điểm quan trọng: dependencyManagement tự nó không thêm shared-core vào classpath. Nó cung cấp quy tắc quản lý cho dependency khi dependency đó được khai báo trực tiếp hoặc xuất hiện qua cây phụ thuộc.

Khi dependency bắc cầu có tọa độ phù hợp với mục được quản lý, Maven có thể áp dụng version được quản lý để kiểm soát version được phân giải. Cách này hữu ích khi nhiều module cần dùng cùng một version của thư viện nền tảng.

### Khác biệt giữa dependencies và dependencyManagement

| Phần POM | Vai trò |
| --- | --- |
| **dependencies** | Khai báo dependency mà project thực sự cần. |
| **dependencyManagement** | Quản lý version và thuộc tính dependency, thường được kế thừa hoặc áp dụng cho dependency được khai báo ở nơi khác. |

Ví dụ, POM cha có thể quản lý version:

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example</groupId>
                <artifactId>shared-core</artifactId>
                <version>2.1</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

POM của module con vẫn cần khai báo dependency nếu mã nguồn module đó sử dụng trực tiếp:

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>shared-core</artifactId>
        </dependency>
    </dependencies>

Version có thể được lấy từ dependencyManagement được kế thừa.

## 6. Dùng BOM để quản lý một nhóm version

BOM (Bill of Materials) là một POM đóng vai trò tập hợp quy tắc quản lý version cho nhiều dependency liên quan. Dùng BOM giúp các module chia sẻ một bộ version đã được kiểm soát.

Ví dụ:

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example.platform</groupId>
                <artifactId>platform-bom</artifactId>
                <version>5.2.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

Sau khi import BOM, project có thể khai báo các dependency do BOM quản lý mà không cần lặp lại version:

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>shared-core</artifactId>
        </dependency>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>http-client</artifactId>
        </dependency>
    </dependencies>

BOM không tự thêm tất cả thư viện vào ứng dụng. Nó cung cấp version và metadata quản lý. Project vẫn khai báo những dependency thực sự cần sử dụng.

Khi nhiều module cùng import một BOM tương thích, việc nâng phiên bản nền tảng có thể được thực hiện tập trung, giúp giảm tình trạng mỗi module chọn một version khác nhau.

## 7. Exclusion: loại bỏ dependency trên một đường dẫn

Đôi khi một thư viện kéo vào một dependency không cần thiết hoặc gây xung đột. Maven hỗ trợ **exclusions** để loại một dependency bắc cầu khỏi một dependency cụ thể.

Ví dụ:

    <dependency>
        <groupId>com.example</groupId>
        <artifactId>reporting-client</artifactId>
        <version>2.1.0</version>
        <exclusions>
            <exclusion>
                <groupId>com.example</groupId>
                <artifactId>shared-core</artifactId>
            </exclusion>
        </exclusions>
    </dependency>

Exclusion được áp dụng trên đường đi qua reporting-client. Nếu shared-core vẫn được kéo vào qua http-adapter, dependency đó vẫn có thể xuất hiện trong cây.

Sau khi loại bỏ, nếu ứng dụng cần shared-core, hãy khai báo version tương thích một cách rõ ràng:

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>shared-core</artifactId>
            <version>2.1</version>
        </dependency>
    </dependencies>

Không nên dùng exclusion chỉ để làm cây phụ thuộc ngắn hơn. Trước khi loại dependency, cần xác nhận thư viện cha có thể hoạt động mà không cần dependency đó, hoặc dependency được thay thế bằng một version tương thích khác. Exclusion sai có thể gây lỗi NoClassDefFoundError hoặc NoSuchMethodError lúc chạy.

## 8. Dependency scope ảnh hưởng đến classpath

Một dependency có thể được chọn về version nhưng vẫn không xuất hiện trên mọi classpath. Maven scope xác định dependency được dùng ở những giai đoạn nào và có được truyền tiếp hay không.

Một số scope phổ biến:

| Scope | Biên dịch mã nguồn chính | Chạy ứng dụng | Kiểm thử | Truyền tiếp |
| --- | --- | --- | --- | --- |
| **compile** | Có | Có | Có | Có |
| **provided** | Có | Thường do môi trường cung cấp | Có | Không truyền như compile thông thường |
| **runtime** | Không dùng cho biên dịch mã chính | Có | Có | Có |
| **test** | Không | Không | Có | Không truyền |

Ví dụ, một thư viện logging có thể được kéo vào qua dependency runtime. Nếu chỉ kiểm tra compile classpath, bạn có thể không thấy nó dù nó có mặt trong runtime dependency graph.

Khi điều tra xung đột, cần xem cả version được chọn và scope của dependency. Hai đường phụ thuộc có thể khác scope; công cụ build áp dụng quy tắc kết hợp scope riêng. Không nên kết luận rằng một thư viện không được dùng chỉ vì nó không có mặt trên compile classpath.

## 9. Xem cây phụ thuộc Maven

Lệnh quan trọng để điều tra dependency bắc cầu là:

    mvn dependency:tree

Lệnh hiển thị cấu trúc dependency theo từng đường dẫn. Khi cần tập trung vào một thư viện:

    mvn dependency:tree -Dincludes=com.example:shared-core

Có thể yêu cầu Maven hiển thị thêm thông tin:

    mvn dependency:tree -Dverbose

Tùy phiên bản Maven Dependency Plugin, chế độ verbose có thể cho thấy các node bị loại do conflict và giải thích vì sao một version không được chọn.

Ví dụ rút gọn:

    application
    +- reporting-client:2.1.0
    |  - shared-core:1.8
    - http-adapter:1.4.0
       - shared-core:2.0

Khi xem kết quả, hãy chú ý:

- Đường dẫn nào kéo thư viện vào.
- Version nào được yêu cầu ở mỗi đường.
- Version nào được chọn.
- Node nào bị loại do conflict.
- Scope của từng dependency.
- Có dependency nào bị loại do exclusion hoặc profile không.

Có thể lưu kết quả ra tệp để so sánh giữa các lần build:

    mvn dependency:tree -DoutputFile=dependency-tree.txt

Đây là cách hữu ích để xem một nâng cấp thư viện làm thay đổi cây phụ thuộc như thế nào.

## 10. Phân giải xung đột trong Gradle

Gradle cũng tạo đồ thị dependency và có cơ chế giải quyết nhiều version của cùng một module. Theo hành vi mặc định, Gradle thường chọn version cao nhất trong các version được yêu cầu cho cùng module, có xét đến version constraint, rule và metadata cấu hình.

Ví dụ, ứng dụng có hai dependency:

    dependencies {
        implementation 'com.example:shared-core:1.8'
        implementation 'com.example:http-adapter:2.0'
    }

Giả sử http-adapter kéo shared-core:2.1 vào. Gradle mặc định có thể chọn shared-core:2.1 khi giải quyết module đó.

Điều này khác với quy tắc nearest definition của Maven. Không nên áp dụng suy luận Maven cho một build Gradle hoặc ngược lại. Cần xem quy tắc của công cụ đang sử dụng.

### Xem dependency tree trong Gradle

Gradle cung cấp task dependencies:

    ./gradlew dependencies

Để xem một configuration cụ thể:

    ./gradlew dependencies --configuration runtimeClasspath

Để giải thích vì sao một module được chọn:

    ./gradlew dependencyInsight --dependency shared-core --configuration runtimeClasspath

Trên Windows, thay ./gradlew bằng gradlew.bat.

Task dependencyInsight thường hiển thị version được yêu cầu, version được chọn và nguyên nhân như conflict resolution, constraint hoặc rule. Đây là công cụ hữu ích khi một thư viện xuất hiện qua nhiều đường.

### Ép version và version constraint

Gradle có nhiều cơ chế để định hướng phiên bản:

- **constraints:** thêm yêu cầu hoặc giới hạn version cho module.
- **platform/BOM:** đồng bộ các version thuộc một nền tảng.
- **strictly:** giới hạn version được phép theo constraint nghiêm ngặt.
- **resolutionStrategy:** tùy chỉnh cách giải quyết dependency trong những trường hợp đặc biệt.

Ví dụ dùng platform:

    dependencies {
        implementation platform('com.example:platform-bom:5.2.0')
        implementation 'com.example:shared-core'
        implementation 'com.example:http-client'
    }

Platform đưa các dependency constraints từ BOM vào quá trình giải quyết. Các module được BOM quản lý có thể được đồng bộ về một bộ version tương thích.

Không nên dùng force một version chỉ để làm mất thông báo conflict. Version bị ép có thể không tương thích với một thư viện yêu cầu API khác. Hãy xác nhận compatibility và kiểm thử trước khi áp dụng.

## 11. Chọn version không đồng nghĩa với bảo đảm tương thích

Quy tắc mediation chỉ xác định version được đưa vào classpath. Nó không chứng minh rằng version đó tương thích với mọi thư viện phụ thuộc.

Ví dụ, reporting-client được biên dịch với shared-core:1.x và gọi phương thức:

    sharedCore.legacyFormat()

Ứng dụng chọn shared-core:2.x, nhưng phiên bản mới đã xóa phương thức đó. Build có thể vẫn biên dịch nếu mã nguồn ứng dụng không trực tiếp gọi phương thức bị xóa. Khi chạy reporting-client, JVM có thể phát sinh:

    java.lang.NoSuchMethodError

Các lỗi liên quan đến không tương thích có thể gồm:

- **NoSuchMethodError:** phương thức mà bytecode cần không tồn tại trong lớp được nạp.
- **NoClassDefFoundError:** lớp cần thiết không có trên runtime classpath hoặc không thể nạp.
- **AbstractMethodError:** triển khai không cung cấp phương thức trừu tượng mà mã đang gọi yêu cầu.
- **ClassCastException:** các kiểu runtime không tương thích với phép ép kiểu.

Vì vậy, sau khi thay version được chọn, cần chạy các kiểm thử phù hợp, đặc biệt là integration test hoặc kiểm thử đường đi sử dụng thư viện bị ảnh hưởng.

## 12. Ngăn nhiều version ngoài ý muốn

Một cây phụ thuộc có thể hợp lệ về mặt phân giải nhưng vẫn chứa những version không mong muốn. Dự án nên có chính sách phát hiện và ngăn xung đột quan trọng.

### Maven Enforcer Plugin

Maven Enforcer Plugin có rule **dependencyConvergence** để phát hiện trường hợp cùng dependency được yêu cầu với các version khác nhau trong cây.

Ví dụ:

    <build>
        <plugins>
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
        </plugins>
    </build>

Khi rule được kích hoạt trong lifecycle, build có thể thất bại nếu phát hiện version không hội tụ theo quy tắc. Nhóm cần quyết định có nên cho phép một số trường hợp ngoại lệ và cách xử lý chúng.

### Gradle kiểm tra xung đột

Gradle thường giải quyết conflict bằng cách chọn version theo quy tắc mặc định. Nếu muốn build thất bại khi có xung đột thay vì tự chọn, có thể cấu hình:

    configurations.configureEach {
        resolutionStrategy.failOnVersionConflict()
    }

Thiết lập này có thể hữu ích trong dự án muốn yêu cầu version nhất quán và buộc người phát triển xử lý xung đột rõ ràng. Cần đánh giá phạm vi áp dụng vì một số hệ sinh thái dependency được thiết kế để Gradle chọn version cao hơn theo quy tắc mặc định.

## 13. Quy trình xử lý khi một thư viện xuất hiện qua nhiều đường

Khi phát hiện cùng module được yêu cầu ở nhiều version, có thể xử lý theo trình tự:

1. **Xác định module:** so sánh groupId/artifactId hoặc group/name để chắc chắn các node là cùng một module.
2. **Xem toàn bộ đường dẫn:** dùng dependency:tree hoặc dependencyInsight để biết thư viện đến từ những dependency nào.
3. **Ghi nhận version được yêu cầu:** không chỉ ghi version cuối cùng được chọn.
4. **Hiểu quy tắc công cụ:** Maven dùng nearest definition; Gradle mặc định thường chọn version cao nhất, có xét constraints và rules.
5. **Kiểm tra compatibility:** xem release note, API thay đổi và yêu cầu version của các thư viện phụ thuộc.
6. **Chọn cách quản lý:** dùng dependencyManagement/BOM, platform/constraints hoặc khai báo version trực tiếp khi phù hợp.
7. **Chỉ exclusion khi cần:** loại đường phụ thuộc không mong muốn và bảo đảm dependency cần thiết vẫn được cung cấp.
8. **Kiểm thử:** chạy compile, unit test và integration test liên quan đến thư viện được thay version.
9. **Giữ chính sách lâu dài:** thêm rule kiểm tra convergence hoặc quy trình review dependency nếu xung đột thường xuyên tái diễn.

## 14. Ví dụ tổng hợp: điều tra shared-core

Giả sử ứng dụng có dependency tree:

    application
    +- com.example:reporting-client:2.1.0
    |  - com.example:shared-core:1.8
    - com.example:http-adapter:1.4.0
       - com.example:shared-core:2.0

Với Maven, nếu hai đường có cùng độ sâu, thứ tự khai báo dependency có thể quyết định version được chọn. Nếu một đường ngắn hơn, nearest definition sẽ ưu tiên version trên đường gần hơn.

Nhóm quyết định dùng shared-core:2.0. Có thể khai báo version trực tiếp hoặc quản lý bằng dependencyManagement:

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example</groupId>
                <artifactId>shared-core</artifactId>
                <version>2.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

Sau khi cập nhật, chạy:

    mvn dependency:tree -Dincludes=com.example:shared-core
    mvn clean verify

Kiểm tra cây cho thấy version nào thực sự được phân giải và verify thực hiện các bước kiểm tra đã cấu hình. Nếu reporting-client không tương thích với 2.0, cần nâng reporting-client lên version tương thích hoặc chọn một version shared-core mà cả hai thư viện hỗ trợ. Chỉ ép 2.0 không tự sửa được sự không tương thích API.

## 15. Những sai lầm thường gặp

### Nghĩ rằng Maven luôn chọn version cao nhất

Maven dùng nearest definition, không phải quy tắc chọn số version cao nhất. Hãy xem độ sâu đường dẫn và dependency tree.

### Nghĩ rằng Gradle và Maven phân giải giống nhau

Hai công cụ có quy tắc mặc định khác nhau. Hãy dùng đúng công cụ kiểm tra và đọc lý do version được chọn.

### Chỉ xem dependency trực tiếp

Xung đột thường nằm sâu trong dependency bắc cầu. Dùng cây phụ thuộc hoặc dependencyInsight để tìm đường dẫn đầy đủ.

### Thêm exclusion mà không thay thế dependency cần thiết

Loại một node khỏi một đường có thể làm mất lớp cần thiết ở runtime. Kiểm tra mọi đường còn lại và khai báo dependency thay thế nếu ứng dụng cần nó.

### Ép version mà không kiểm tra API

Một version duy nhất không đồng nghĩa với tương thích. Kiểm tra release note và chạy test sau khi thay đổi.

### Nhầm dependencyManagement với dependencies

dependencyManagement chỉ quản lý version và thuộc tính; nó không tự thêm thư viện vào project.

## 16. Kết luận

Khi một thư viện xuất hiện qua nhiều đường phụ thuộc, đồ thị build chứa nhiều yêu cầu cho cùng một module. Maven và Gradle áp dụng quy tắc phân giải để xác định version được dùng, nhưng quy tắc mặc định của hai công cụ khác nhau. Maven ưu tiên nearest definition; Gradle mặc định thường chọn version cao nhất trong các yêu cầu, có xét version constraints và rules.

Dependency tree và dependencyInsight giúp tìm nguồn của từng yêu cầu. dependencyManagement, BOM, platform và constraints giúp quản lý version nhất quán; exclusions giúp loại bỏ một đường phụ thuộc cụ thể khi có lý do rõ ràng. Sau khi giải quyết xung đột, cần kiểm tra tương thích API và chạy kiểm thử phù hợp, vì việc chọn được một version không tự chứng minh rằng mọi thư viện đều hoạt động đúng với version đó.
