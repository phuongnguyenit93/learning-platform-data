# Đọc release train và ma trận Boot–Spring Data–driver–server

## 1. Vì sao phải đọc cả chuỗi phiên bản?

Ứng dụng sử dụng **Spring Data MongoDB** thường viết code với **MongoTemplate**, **MongoRepository**, **ReactiveMongoTemplate** hoặc repository reactive. Nhưng khi khởi chạy, những API đó còn dựa vào Spring Framework, MongoDB Java Driver và MongoDB Server. Một ứng dụng có thể biên dịch bình thường mà vẫn gặp lỗi khi kết nối hoặc đọc BSON do các thành phần không tương thích.

Trong chương **Phiên bản và nâng cấp** của module **SPRING_DATA_MONGODB**, mục tiêu là biết cách chọn và kiểm chứng **một tổ hợp phiên bản**, thay vì chỉ đổi số version của một dependency.

~~~mermaid
flowchart TB
    JDK["Java / JDK"]
    Boot["Spring Boot<br/>plugin + dependency management"]
    Train["Spring Data release train<br/>BOM đồng bộ các module"]
    SD["Spring Data MongoDB<br/>MongoTemplate / Repository"]
    Driver["MongoDB Java Driver<br/>sync / reactive / BSON"]
    Server[("MongoDB Server<br/>standalone / replica set / sharded")]
    Framework["Spring Framework<br/>container / transaction / conversion"]
    JDK --> Boot
    Boot --> Framework
    Boot --> Train
    Train --> SD
    Boot --> Driver
    SD --> Driver
    Driver <-->|"Wire protocol, command, tính năng"| Server
~~~

Tối thiểu cần trả lời **sáu câu hỏi** trước khi nâng cấp:

1. Ứng dụng đang dùng **Spring Boot** phiên bản nào và chạy trên **JDK** nào?
2. Boot đó quản lý **Spring Data release train** nào?
3. Release train đó chứa **spring-data-mongodb** phiên bản nào?
4. Phiên bản Spring Data MongoDB yêu cầu **MongoDB Java Driver tối thiểu** nào? Driver thực tế trên runtime classpath là bản nào?
5. Driver đó tương thích với **MongoDB Server** đang dùng ở mức nào?
6. Những tính năng ứng dụng sử dụng (transaction, change stream, aggregation, index, codec, query, TLS...) có còn hoạt động đúng trên tổ hợp mới không?

**Điểm cần nhớ:** “cùng chạy được” chưa chắc tương đương “được kiểm thử trong tổ hợp này”, “được hỗ trợ lâu dài” hoặc “mọi tính năng mới đều dùng được”.

## 2. Phân biệt năm hệ phiên bản thường bị nhầm

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Spring Boot** | 3.5.x, 4.0.x, 4.1.x | Nền tảng ứng dụng, auto-configuration, starter, BOM, các yêu cầu Java/Spring Framework |
| **Spring Data release train** | 2025.0.x, 2025.1.x, 2026.0.x | Nhóm phát hành đồng bộ các module Spring Data |
| **Spring Data MongoDB** | 4.5.x, 5.0.x, 5.1.x | Phiên bản cụ thể của thư viện mapping/repository cho MongoDB |
| **MongoDB Java Driver** | 5.5.x, 5.6.x, 5.8.x | Driver giao tiếp BSON, session, cluster topology và wire protocol |
| **MongoDB Server** | 6.0, 7.0, 8.0 | Phiên bản database thực thi command, aggregation và transaction |

**Spring Data release train không phải Spring Data MongoDB version.** Ví dụ, train **2026.0** chứa Spring Data MongoDB dòng **5.1.x** và Spring Data Commons dòng **4.1.x**. Không thể lấy số **2026.0** đặt vào phiên bản Maven artifact **spring-data-mongodb**.

**Spring Data MongoDB cũng không phải MongoDB Java Driver.** Artifact **org.springframework.data:spring-data-mongodb** triển khai mapping/repository; các artifact **org.mongodb:mongodb-driver-sync**, **mongodb-driver-reactivestreams**, **mongodb-driver-core**, **bson** thực hiện giao tiếp driver và xử lý BSON.

### Release train là gì?

**Spring Data** gồm nhiều module được phát triển và phát hành theo một lịch trình chung, trong khi mỗi module có lịch sử version riêng. Một **release train** gom tập các phiên bản đã được chọn để sử dụng cùng nhau thông qua **BOM** (Bill of Materials).

Từ các thế hệ Spring Data mới, tên release train có dạng calendar version:

~~~text
2026.0.2
│    │ └─ Service release / iteration
│    └─── Dòng phát hành trong năm
└──────── Năm phát hành
~~~

Ví dụ các dạng version:

| Mẫu | Diễn giải |
| --- | --- |
| **2026.0.0** | Bản GA đầu tiên của train 2026.0 |
| **2026.0.2** | Bản bảo trì của cùng train |
| **2026.1.0-M2** | Milestone của train mới, chưa nhất thiết phù hợp production |
| **2026.1.0-RC1** | Release candidate, cần xem chính sách triển khai |
| **2026.1.0-SNAPSHOT** | Snapshot đang phát triển, có thể thay đổi |

Khi thấy một thư viện **Spring Data MongoDB 5.1.2**, đừng tự suy luận đó là một phiên bản release train hoặc Spring Boot **5.1**. Phải tra BOM để thấy quan hệ cụ thể.

## 3. Đọc ma trận theo đúng thứ tự

Không có một bảng duy nhất thay thế mọi bảng tương thích. Cần ghép thông tin từ nhiều nguồn chính thức:

| Bảng / tài liệu | Câu hỏi được trả lời | Không chứng minh điều gì? |
| --- | --- | --- |
| **Spring Boot Managed Dependency Coordinates** | Boot ở phiên bản đang dùng sẽ chọn chính xác bản Spring Data MongoDB, driver và BSON nào nếu không override? | Không xác nhận server MongoDB thực tế tương thích mọi tính năng |
| **Spring Data Dependencies / Release Train BOM** | Train nào chứa các module Spring Data nào? | Không mô tả toàn bộ dependency của Spring Boot |
| **Spring Data MongoDB Requirements / Compatibility Matrix** | Train và Spring Data MongoDB liên hệ ra sao; driver tối thiểu và server đã được test? | Không phải danh sách tất cả driver patch được Boot quản lý |
| **MongoDB Java Driver Compatibility Tables** | Driver có tương thích server và Java runtime theo chính sách MongoDB không? | Không kiểm chứng code Spring Data, query hay nghiệp vụ của ứng dụng |
| **Migration Guide và Release Notes** | Những API, behavior, cấu hình hoặc kiểu lưu trữ nào thay đổi? | Không tự động sửa code hoặc dữ liệu |
| **Bản dependency thực tế của build** | Artifact cuối cùng đã resolve bản nào? | Không bảo đảm các bản đó tạo thành tổ hợp đã được hỗ trợ |

Quy trình đọc theo thứ tự:

~~~mermaid
flowchart TD
    A["Ghi nhận Boot và Java hiện tại"]
    B["Tra BOM của chính Boot patch đó"]
    C["Xác định Spring Data release train và module MongoDB"]
    D["Tra Requirements: driver tối thiểu, server đã test"]
    E["Tra compatibility driver ↔ server, Java"]
    F["Đọc migration guide + changelog"]
    G["Kiểm tra resolved dependencies trong build"]
    H["Integration test với server và topology thực tế"]
    A --> B --> C --> D --> E --> F --> G --> H
~~~

**Đọc từ trên xuống:** Boot quyết định tập dependency mặc định; Spring Data xác định mức hỗ trợ thư viện; driver quyết định tương tác server; còn kiểm thử ứng dụng chứng minh chức năng cụ thể.

## 4. Ma trận Spring Data MongoDB và MongoDB Java Driver

Bảng sau được rút từ mục **Compatibility Matrix** trong tài liệu Spring Data MongoDB, đối chiếu vào **20/11/2026**. Tài liệu có thể cập nhật khi có release mới, vì vậy trong lần nâng cấp thực tế phải mở lại trang đúng **release train** được chọn.

| Spring Data release train | Spring Data MongoDB | Driver tối thiểu được nêu | MongoDB Server đã được Spring Data test |
| --- | --- | --- | --- |
| **2026.0** | **5.1.x** | **5.6.x** | **6.x – 8.x** |
| **2025.1** | **5.0.x** | **5.6.x** | **6.x – 8.x** |
| **2025.0** | **4.5.x** | **5.5.x** | **6.x – 8.x** |
| **2024.1** | **4.4.x** | **5.2.x** | **4.4.x – 8.x** |
| **2024.0** | **4.3.x** | **4.11.x hoặc 5.x** | **4.4.x – 7.x** |

Nguồn: [Spring Data MongoDB — Requirements và Compatibility Matrix](https://docs.spring.io/spring-data/mongodb/reference/preface.html).

### Đọc một hàng như thế nào?

Ví dụ hàng **2026.0** cho biết:

1. Nếu chọn release train **2026.0**, module MongoDB thuộc dòng **5.1.x**.
2. Spring Data MongoDB thuộc dòng đó cần **MongoDB Java Driver 5.6.x trở lên** theo mức tối thiểu công bố.
3. Bộ test của Spring Data đã chạy với các **thế hệ server 6.x đến 8.x** được liệt kê.
4. **Không phải** Boot luôn resolve đúng driver **5.6.x**; BOM của Boot có thể chọn bản mới hơn.
5. **Không phải** mọi tổ hợp server ngoài dải được liệt kê đều thất bại; chúng cần đối chiếu thêm ma trận driver–server và kiểm thử.

### “Minimum driver” khác “managed driver”

Giả sử một train ghi **Minimum Driver Version = 5.6.x** và Spring Boot đang quản lý **5.8.1**:

- **5.6.x** là ngưỡng tối thiểu của Spring Data MongoDB trong tài liệu đó.
- **5.8.1** là phiên bản mà build có thể đang sử dụng nếu giữ quản lý dependency của Boot.
- Không cần hạ driver về **5.6.x** chỉ để khớp chính xác cột “minimum”.
- Không nên tự nâng lên một driver khác chỉ vì nó mới nhất: phải đánh giá khả năng hỗ trợ của Spring Data, Boot và Java runtime.

**“Tested database versions”** mô tả dải phiên bản server được kiểm tra trong test suite của Spring Data, không phải cam kết rằng mọi cấu hình server, mọi command và mọi tính năng đều được kiểm thử cho ứng dụng của bạn.

## 5. Gắn release train vào Spring Boot

Tổ hợp Boot–Spring Data phụ thuộc vào **phiên bản Boot cụ thể** và BOM đi kèm. Để hình dung các dòng phát hành, xem ví dụ sau:

| Dòng Spring Boot | Spring Data release train tương ứng | Spring Data MongoDB tương ứng |
| --- | --- | --- |
| **3.4.x** | **2024.1.x** | **4.4.x** |
| **3.5.x** | **2025.0.x** | **4.5.x** |
| **4.0.x** | **2025.1.x** | **5.0.x** |
| **4.1.x** | **2026.0.x** | **5.1.x** |

Đây là **quan hệ giữa các dòng**, không phải ma trận cho từng patch. Nếu ứng dụng dùng **Boot 3.5.3**, phải tra đúng tài liệu/BOM của patch đó; không được suy ra mọi dependency đều trùng với **Boot 3.5.13**.

Để kiểm tra chênh lệch patch một cách thực tế, tại thời điểm tham khảo tài liệu dependency của Boot:

| Bản Boot dùng làm ví dụ | Spring Data MongoDB do Boot quản lý | MongoDB Java Sync Driver do Boot quản lý |
| --- | --- | --- |
| **3.5.13** | **4.5.13** | **5.5.2** |
| **4.0.10** | **5.0.9** | **5.6.5** |
| **4.1.3** | **5.1.3** | **5.8.1** |

Nguồn là các trang [Boot 3.5 Managed Dependencies](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html), [Boot 4.0 Managed Dependencies](https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html) và [Boot 4.1 Managed Dependencies](https://docs.spring.io/spring-boot/4.1/appendix/dependency-versions/coordinates.html).

**Cách đọc chính xác:** lấy dòng **org.springframework.data:spring-data-mongodb** và **org.mongodb:mongodb-driver-sync** từ cùng một tài liệu Boot. Với reactive, tìm thêm **mongodb-driver-reactivestreams**. Với BSON, theo dõi cả **mongodb-driver-core** và **bson**, vì tự ghép patch lệch nhau có thể tạo classpath khó chẩn đoán.

Các dòng **Boot 4.2.x** và Spring Data mới hơn có thể được phát hành theo lịch riêng; hãy tra [Spring Project Generations](https://spring.io/projects/generations/) và BOM của Boot đúng version đang chọn thay vì suy luận bằng cách tăng số.

## 6. Kiểm tra ma trận MongoDB Java Driver ↔ Server

Sau khi biết driver runtime, tiếp tục kiểm tra [MongoDB Client Library Compatibility Tables](https://www.mongodb.com/docs/drivers/compatibility/?driver-language=java&java-driver-framework=java-sync).

Trong bảng của MongoDB, có thể gặp:

| Ký hiệu | Ý nghĩa thực tế |
| --- | --- |
| **✓** | Driver hỗ trợ đầy đủ các tính năng trong phạm vi compatibility được công bố cho server đó |
| **⊛** | Kết nối được nhưng chưa hỗ trợ toàn bộ tính năng mới của server |
| **✗** | Tổ hợp được đánh dấu không tương thích |
| **Trống** | Chưa được công bố là đã kiểm thử/tương thích trong bảng tương ứng |

Phải đọc cả **hàng driver** và **cột MongoDB Server**. Ví dụ, driver có thể kết nối được server mới nhưng chưa hỗ trợ một tính năng mới của server; ứng dụng đang dùng CRUD thông thường có thể vẫn chạy, còn ứng dụng dựa vào command mới phải nâng driver.

**Ba cấp độ xác minh độc lập:**

1. **Spring Data hỗ trợ driver**: xem minimum version và migration guide của Spring Data MongoDB.
2. **MongoDB hỗ trợ tổ hợp driver/server**: xem bảng compatibility chính thức của driver.
3. **Ứng dụng hỗ trợ tổ hợp thực tế**: chạy integration test và kiểm tra dữ liệu, hiệu năng, lỗi tại môi trường phù hợp.

Ngoài version của server, topology còn ảnh hưởng tới tính năng:

- **Transaction** cần replica set hoặc sharded cluster theo yêu cầu của MongoDB; standalone không trở thành môi trường test transaction chỉ vì đổi driver.
- **Change stream** cần replica set hoặc sharded cluster hỗ trợ; cần tính đến oplog/resume token và thời gian theo dõi.
- **Sharding**, phân vùng dữ liệu và routing qua **mongos** yêu cầu topology và quyền tương ứng.
- Các **aggregation operator**, **index type** và tính năng tìm kiếm đặc thù chỉ có trên những server/edition/topology nhất định.

Không lấy số version đủ điều kiện làm bằng chứng cho các điều kiện topology hoặc cấu hình đó.

## 7. Java và Spring Framework cũng nằm trong ma trận

Một ứng dụng không chỉ phải chạy với server MongoDB; nó còn phải đáp ứng yêu cầu **Java/JDK** và **Spring Framework** của Boot/Spring Data.

Ví dụ, Spring Data MongoDB **4.5.x** thuộc thế hệ sử dụng **Spring Framework 6.2** và yêu cầu Java tối thiểu **17**; Spring Data MongoDB **5.x** thuộc thế hệ **Spring Framework 7** và cũng công bố yêu cầu Java tối thiểu **17**. Tuy nhiên, với phiên bản Boot cụ thể, phải kiểm tra riêng Java compatibility, toolchain và toàn bộ ecosystem. Nâng từ Boot 3 sang Boot 4 có thể ảnh hưởng đến API, auto-configuration, thư viện thứ ba và namespace/phụ thuộc ngoài MongoDB.

### Vì sao JDK là một ràng buộc riêng?

- Bytecode của Spring Framework và driver cần được JVM hiện tại hiểu.
- Thư viện dùng reflection, native access, virtual threads hoặc TLS có thể có những yêu cầu khác nhau.
- Java driver có bảng hỗ trợ runtime Java riêng; không nên suy “driver mới luôn chạy trên mọi JDK cũ”.
- Plugin Gradle/Maven có thể yêu cầu JVM khởi chạy build khác với **Java toolchain** dùng để compile ứng dụng.

Một kế hoạch nâng cấp đầy đủ cần ghi **Java runtime thực tế ở production**, không chỉ giá trị **sourceCompatibility** trong project.

## 8. BOM và dependency management: để Boot chọn phiên bản

### 8.1. Maven với Spring Boot parent

Ví dụ một ứng dụng đồng bộ dùng **spring-boot-starter-data-mongodb**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.3</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mongo-version-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-mongodb</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Phiên bản Boot **4.1.3** ở đây chỉ là ví dụ có thể đối chiếu BOM, không phải yêu cầu mọi dự án phải nâng lên bản này. Điểm chính: không đặt version riêng cho **spring-data-mongodb** hoặc **mongodb-driver-sync** khi BOM của Boot đã chọn bộ dependency.

Nếu dự án không dùng **spring-boot-starter-parent** mà tự import **spring-boot-dependencies** trong Maven dependency management, vẫn cần xem thứ tự/quy tắc import BOM để biết version nào cuối cùng được chọn.

### 8.2. Gradle dùng Spring Boot plugin và quản lý dependency

Một ví dụ **build.gradle** với Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.3'
    id 'io.spring.dependency-management' version '1.1.7'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Ví dụ dùng plugin **io.spring.dependency-management** để import dependency management do Boot cung cấp. Nếu dự án sử dụng Gradle native platform/BOM hoặc convention plugin riêng, cách viết sẽ khác; cần kiểm tra **resolved dependencies** sau khi build cấu hình.

**Tránh khai báo cùng lúc** một version driver riêng và version BOM khác dòng Spring Data. Khi có nhiều nơi quyết định version, build có thể chọn bản không đúng ý người viết hoặc sinh conflict.

### 8.3. Khi nào cần import spring-data-bom riêng?

Với dự án Spring không dùng Spring Boot, có thể import **org.springframework.data:spring-data-bom** để đồng bộ các module Spring Data. Ví dụ Maven:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-bom</artifactId>
            <version>2026.0.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Khi đó, vẫn phải quản lý **Spring Framework**, driver và các thư viện ngoài phù hợp. **Spring Data BOM không thay thế toàn bộ Spring Boot BOM**. Trong dự án Boot, chỉ override release train nếu có lý do và đã đối chiếu bảng tương thích.

Trường hợp dùng Spring Boot Maven parent và muốn override train, tài liệu Spring Data có nhắc property **spring-data-bom.version**. Việc thay property này **không bảo đảm** mọi transitive dependency, API của Boot và Spring Framework đã tương thích; đặc biệt cẩn trọng khi nhảy qua ranh giới major version.

## 9. Xem phiên bản thực sự được resolve, không chỉ đọc build.gradle

File build chỉ cho biết **yêu cầu** và cơ chế quản lý version. Dependency graph mới phản ánh tập artifact được resolve cho một cấu hình cụ thể.

### 9.1. Gradle

Trên shell có Gradle wrapper:

~~~bash
# Xem tất cả thư viện trong classpath khi chạy ứng dụng:
./gradlew dependencies --configuration runtimeClasspath

# Xác định vì sao Spring Data MongoDB có phiên bản hiện tại:
./gradlew dependencyInsight --dependency spring-data-mongodb --configuration runtimeClasspath

# Kiểm tra driver đồng bộ hoặc reactive:
./gradlew dependencyInsight --dependency mongodb-driver-sync --configuration runtimeClasspath
./gradlew dependencyInsight --dependency mongodb-driver-reactivestreams --configuration runtimeClasspath

# Tìm version phụ thuộc lõi của driver và BSON:
./gradlew dependencyInsight --dependency mongodb-driver-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency bson --configuration runtimeClasspath
~~~

Trên Windows dùng **gradlew.bat** hoặc lệnh wrapper phù hợp với terminal. Với project multi-module, hãy kiểm tra đúng module (ví dụ **:app:dependencyInsight**) và đúng configuration có artifact runtime, tránh chỉ xem dependency của root project.

**Những dòng cần quan sát:**

- **Requested** và **selected/resolved version** có khác nhau không?
- Có conflict resolution, version constraint hoặc **force** nào không?
- Có một module đưa thêm MongoDB driver/codec qua dependency bắc cầu không?
- Driver sync và reactive có được chọn theo cùng một nhóm phiên bản tương thích không?

### 9.2. Maven

~~~bash
# Xem cây dependency có liên quan Spring Data và MongoDB:
./mvnw dependency:tree

# Xem effective POM, bao gồm dependencyManagement thực tế:
./mvnw help:effective-pom
~~~

Trên Windows dùng **mvnw.cmd**. Có thể lọc cây theo group/artifact bằng tùy chọn của Maven Dependency Plugin, nhưng trước khi tin vào bản rút gọn cần bảo đảm không bỏ sót transitive dependency.

### 9.3. Xác minh server

Trong **mongosh** kết nối tới deployment ứng dụng thực sự sử dụng:

~~~javascript
db.version()
db.hello()
db.runCommand({ buildInfo: 1 }).version
~~~

**db.version()** giúp xem server version; **db.hello()** cho biết thông tin topology và khả năng giao tiếp. Không được suy version server chỉ từ version MongoDB CLI/mongosh cài trên máy lập trình.

Nếu ứng dụng đi qua **mongos** hoặc dịch vụ cloud được quản lý, cần xác nhận version server mà service cung cấp và chính sách nâng cấp của nhà cung cấp. Trong sharded cluster, không giả định chỉ đọc một endpoint là đủ để đánh giá mọi thành phần đang ở cùng giai đoạn nâng cấp.

### 9.4. Tạo bảng inventory nhỏ trước khi nâng cấp

Ví dụ:

| Hạng mục | Hiện tại (minh họa) | Dự kiến | Nguồn xác minh |
| --- | --- | --- | --- |
| JDK runtime | 17 | 21 | Deployment image / runtime |
| Spring Boot | 3.5.x | 4.1.x | Maven/Gradle |
| Spring Data train | 2025.0.x | 2026.0.x | BOM |
| Spring Data MongoDB | 4.5.x | 5.1.x | dependencyInsight / dependency:tree |
| Mongo Java Driver | 5.5.x | Phiên bản Boot 4.1.x quản lý | resolved runtimeClasspath |
| MongoDB Server | 7.0 | 7.0 hoặc kế hoạch server riêng | db.version / nhà cung cấp |
| Topology | Replica set | Replica set | rs.status / hệ thống vận hành |

Đây là **mẫu ghi chép**, không phải cấu hình khuyến nghị bắt buộc. Một kế hoạch nâng JDK hoặc server phải được xác nhận riêng với yêu cầu và lịch hỗ trợ của hệ thống.

## 10. Những thay đổi có thể ảnh hưởng code và BSON khi nâng cấp

Ma trận version chỉ cho biết **khả năng tương thích nền tảng**. Khi thay **Spring Data MongoDB major version**, các hành vi cụ thể còn có thể thay đổi.

### 10.1. Driver API và dependency

Spring Data MongoDB **5.x** yêu cầu **MongoDB Java Driver 5.6+** và không còn hỗ trợ thế hệ driver **4.x**. Nếu một library cũ giữ chặt **mongodb-driver-core 4.x** hoặc các API driver đã bị loại bỏ, việc nâng Spring Data có thể gây **NoSuchMethodError**, **ClassNotFoundException** hoặc lỗi ở runtime.

Hãy kiểm tra:

- Tất cả artifact **org.mongodb** trong dependency graph.
- Code trực tiếp dùng Java Driver ngoài **MongoTemplate** hoặc repository.
- Các plugin hoặc library dùng driver: migration tool, schema validator, telemetry, test fixture, GridFS helper.
- Reactive driver nếu ứng dụng dùng **ReactiveMongoTemplate**.

Không cố sửa lỗi binary incompatibility bằng cách ép driver 4.x xuống dưới Spring Data 5.x.

### 10.2. UUID representation

Khi lưu UUID trong MongoDB, có các cách biểu diễn Binary với subtype/byte order khác nhau. Spring Data MongoDB 5.x không còn mặc định giúp thiết lập **UuidRepresentation** qua các lớp cấu hình như trước; migration guide yêu cầu chỉ định rõ khi cần lưu UUID.

Ví dụ với Java Driver:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import org.bson.UuidRepresentation;

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(
        new ConnectionString("mongodb://localhost:27017/demo")
    )
    .uuidRepresentation(UuidRepresentation.STANDARD)
    .build();
~~~

Đây là ví dụ driver settings độc lập. Trong Spring Boot, hãy bảo đảm **MongoClient mà MongoTemplate/repository sử dụng** nhận chính xác cấu hình đó, thay vì cấu hình một client khác.

Không đổi tất cả UUID sang STANDARD một cách mù quáng nếu dữ liệu cũ được ghi bằng biểu diễn legacy. Phải xem Binary thực tế, xác định mapping cũ, chuẩn bị migration và kiểm thử đọc/ghi chéo phiên bản.

### 10.3. BigDecimal, BigInteger và Decimal128

Trong nâng cấp sang Spring Data MongoDB 5.x, **biểu diễn mặc định của BigDecimal/BigInteger qua cấu hình tùy biến** là điểm được migration guide nhắc đến. Khi muốn lưu số thập phân theo BSON **Decimal128**, có thể chỉ định rõ ở property:

~~~java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

class InvoiceAmount {
    @Field(targetType = FieldType.DECIMAL128)
    BigDecimal total;
}
~~~

**@Field(targetType = FieldType.DECIMAL128)** chỉ rõ cách biểu diễn cho property. Nếu dữ liệu cũ đã được lưu dạng **String**, thay annotation hoặc mặc định của converter có thể làm document mới có BSON type khác; cần kiểm tra aggregation, sort, query range và các dịch vụ khác cùng đọc collection.

Không áp dụng converter chung cho toàn bộ collection khi chỉ một property cần thay đổi mà chưa kiểm tra tương thích.

### 10.4. Mapping và custom converters

Cần kiểm tra các entity sử dụng:

- **@PersistenceCreator**, constructor immutable, Java **record**.
- **_class**, **@TypeAlias** và các trường polymorphic.
- **@Field** đổi tên trường, mapping ID, enum, date/time.
- **MongoCustomConversions**, reading/writing converters và custom codec.
- Dữ liệu đã ghi bởi các phiên bản ứng dụng cũ.

Một bản test chỉ gọi **repository.save(entity)** rồi **findById()** với chính bản code mới có thể không phát hiện việc ứng dụng mới đọc sai BSON cũ. Cần bổ sung **raw BSON fixtures** được xây dựng từ những dạng dữ liệu thật đã ẩn danh.

### 10.5. Query, aggregation, transaction và change stream

Phải xem migration guide và release notes theo **bước nâng cấp thực tế**, ví dụ **4.x -> 5.x**. Những thay đổi có thể liên quan:

| Nhóm | Nội dung phải kiểm tra |
| --- | --- |
| **Derived query** | Tên property, conversion, regex, pagination và sort |
| **MongoTemplate Query/Criteria** | Cú pháp filter BSON và cơ chế mapping field |
| **Aggregation** | Operator trên server đích, alias, kiểu BSON đầu ra |
| **Index** | Unique, partial, TTL, compound và index được tạo tự động |
| **Transaction** | MongoTransactionManager, session, retry, rollback và replica set |
| **Change stream** | Consumer lifecycle, resume token, filter và xử lý khi restart |
| **Reactive access** | ReactiveMongoTemplate, Reactor/driver reactive, cancellation và timeout |
| **GridFS** | Upload/download, metadata, codec và truy cập stream |

Ví dụ: migration guide của Spring Data MongoDB 5.x còn nêu thay đổi ở **DefaultMessageListenerContainer**: chế độ auto-start của lifecycle được mặc định bật. Ứng dụng đang phụ thuộc việc tự khởi động listener cần xem xét startup order và quyền truy cập server trước khi deploy.

## 11. Trường hợp thực hành: đánh giá nâng cấp Boot 3.5 sang 4.1

Giả sử một ứng dụng đang dùng:

- **Spring Boot 3.5.x**, Spring Data train **2025.0.x**, Spring Data MongoDB **4.5.x**.
- **MongoDB Server 7.0** chạy dưới dạng replica set.
- **MongoTemplate**, repository, aggregation, transaction và change stream.
- Dữ liệu có trường UUID và BigDecimal được ghi qua nhiều phiên bản ứng dụng.

Mục tiêu là **Spring Boot 4.1.x** và train **2026.0.x**, với Spring Data MongoDB **5.1.x**. Không nên xem đây chỉ là đổi một dòng plugin.

### Bước 1 — Chốt baseline và tạo bản đối chiếu

Ghi version JDK, Boot, release train, MongoDB Driver **thực tế**, MongoDB Server, topology và các dependency bắc cầu. Chạy unit test và integration test trên trạng thái hiện tại để biết lỗi mới phát sinh từ nâng cấp.

### Bước 2 — Tra compatibility

Với **MongoDB Server 7.0**, bảng Spring Data cho biết cả các dòng **4.5.x** và **5.1.x** đều nằm trong dải server được kiểm thử. Tiếp tục tra phiên bản driver do **Boot 4.1.x** quản lý và ô tương ứng với MongoDB Server **7.0** trong bảng MongoDB Java Driver.

Đây mới chỉ là điều kiện cơ bản. Nếu dùng tính năng server đặc biệt, phải xem driver release notes và test chức năng đó.

### Bước 3 — Đọc thay đổi major version

Đối chiếu:

- **Boot 3 -> 4**: các thay đổi về Spring Framework, auto-configuration, starter, thư viện và ứng dụng.
- **Spring Data MongoDB 4 -> 5**: yêu cầu driver **5.6+**, cấu hình UUID, BigDecimal, lifecycle listener và API thay đổi.
- **MongoDB Java Driver 5.5 -> bản Boot 4.1 quản lý**: lớp API, connection options, TLS, codec và reactive nếu có.

Có thể thực hiện các nhịp nâng cấp riêng trong nhánh thử nghiệm, ví dụ kiểm tra trước ở **Boot 4.0** rồi mới lên **4.1**, để phân biệt lỗi theo thế hệ. Lộ trình cuối cùng phụ thuộc lịch hỗ trợ của hệ thống và mức độ thay đổi code.

### Bước 4 — Chạy test dữ liệu và chức năng

- Đọc **raw BSON fixture** của dữ liệu UUID/BigDecimal cũ; kiểm tra mapping không mất thông tin.
- Save/find/update qua **MongoTemplate** và **MongoRepository**.
- Chạy aggregation thật và so sánh kết quả với baseline.
- Test transaction **commit** và **rollback** trên replica set.
- Mở change stream, ghi event, kiểm tra consumer tiếp nhận đúng và xử lý resume.
- Với reactive, dùng **StepVerifier** và MongoDB thực cho các đường truy cập quan trọng.

### Bước 5 — Kiểm tra trước khi phát hành

Sau khi test xanh, rà soát log lỗi driver, warning deprecated API, pool connection, timeout, retry, p95/p99 latency, thời gian aggregate và những query quan trọng. Nên có cách quay lại artifact ứng dụng trước nâng cấp; nếu đã migrate dữ liệu hoặc thay BSON representation, **rollback code** có thể không đủ để phục hồi hệ thống.

## 12. Ma trận kiểm thử nâng cấp nên lập như thế nào?

Một bảng thử nghiệm nhỏ giúp tách lỗi ứng dụng khỏi lỗi server:

| Ứng dụng | MongoDB Server | Mục tiêu | Kết quả cần ghi nhận |
| --- | --- | --- | --- |
| **Bản cũ** | **Server hiện tại** | Baseline trước nâng cấp | Chức năng, số liệu hiệu năng, dạng BSON |
| **Bản mới** | **Server hiện tại** | Nâng Boot/Spring Data/driver nhưng giữ server | Tương thích backward với dữ liệu cũ |
| **Bản mới** | **Server dự kiến** | Kiểm tra tổ hợp đích | Query, index, aggregation, transaction, change stream |
| **Bản cũ** | **Server dự kiến** | Đánh giá rolling upgrade nếu hai app version cùng tồn tại | Có thể đọc/ghi chéo hay không; chỉ thử nếu bảng hỗ trợ |

Đối với deployment nhiều instance, cần thử **kịch bản mixed-version** trong khoảng chuyển đổi. Nếu ứng dụng mới ghi một định dạng BSON mà ứng dụng cũ không đọc được, quá trình rolling deploy có thể thất bại dù mỗi phiên bản chạy riêng đều xanh.

### Testcontainers có đủ không?

**Testcontainers** rất hữu ích để chọn image MongoDB Server phục vụ integration test:

~~~java
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

// Ví dụ với API Testcontainers MongoDB module ở dòng 1.x.
MongoDBContainer mongo =
    new MongoDBContainer(DockerImageName.parse("mongo:7.0"));
~~~

Nên cố định image major/minor tương ứng với hệ thống thật, và sử dụng replica set khi test transaction/change stream. Khi test bảo mật, sharding, cluster quản lý hay version feature cụ thể, môi trường container đơn giản có thể chưa mô phỏng đủ production.

Chạy test trên nhiều server version chỉ giúp phát hiện lỗi khi đã thực sự chạy những code path quan trọng. Không được coi việc container khởi động thành công là bằng chứng cho tính tương thích nghiệp vụ.

## 13. Các lỗi thường gặp khi đọc ma trận

| Nhầm lẫn | Hệ quả | Cách kiểm tra đúng |
| --- | --- | --- |
| Xem **2026.0** là version của artifact MongoDB | Khai báo dependency không tồn tại/sai | Dùng train cho BOM; dùng **5.1.x** cho module theo ma trận |
| Xem “driver tối thiểu 5.6” là driver phải pin chính xác | Tự hạ driver khỏi bản Boot quản lý | Kiểm tra **managed version** rồi đối chiếu minimum |
| Xem server “đã test 6.x–8.x” là mọi server mới hơn đều bị cấm | Bỏ qua lựa chọn có thể tương thích | Tra thêm bảng driver–server và release notes |
| Xem một kết nối thành công là tất cả tính năng tương thích | Lỗi chỉ xuất hiện khi chạy transaction/aggregation/change stream | Chạy integration tests theo use case |
| Nâng riêng **mongodb-driver-core** nhưng giữ **bson** cũ | Lỗi classpath/binary linkage | Dùng BOM và dependencyInsight cho toàn nhóm org.mongodb |
| Nâng riêng **spring-data-mongodb** qua major, giữ Spring Framework cũ | Lỗi class/method hoặc auto-configuration | Nâng theo release train và Boot tương thích |
| Chỉ đọc **build.gradle** | Bỏ qua version bị override/selected do dependency conflict | Xem **runtimeClasspath** thực tế |
| Test dữ liệu mới mà bỏ dữ liệu legacy | UUID/Decimal128/alias cũ có thể không đọc được | Test raw BSON fixture từ schema cũ |
| So sánh version mongosh với MongoDB Server | Đánh giá sai server runtime | Kết nối deployment thật và chạy **db.version()** |
| Chạy transaction trên standalone rồi kết luận driver lỗi | Nhầm giới hạn topology với version | Dùng replica set/sharded cluster phù hợp |
| Chọn preview **M/RC/SNAPSHOT** như stable mà không xét rủi ro | API thay đổi, thiếu hỗ trợ hoặc cần repository riêng | Xác định rõ trạng thái phát hành và chính sách sử dụng |
| Xem “compatible” đồng nghĩa “còn support/security fixes” | Dùng bản đã hết hỗ trợ | Kiểm tra chính sách hỗ trợ Spring và vòng đời MongoDB Server |

## 14. Quy trình nâng cấp có thể áp dụng lại

1. **Inventory**: ghi chính xác Boot, Java runtime, Spring Data train, Spring Data MongoDB, driver sync/reactive, BSON và MongoDB Server/topology hiện tại.
2. **Mục tiêu**: chọn dòng Boot và train được hỗ trợ; tách nâng ứng dụng khỏi nâng server khi cần khoanh vùng thay đổi.
3. **Tra bảng**: Boot BOM → Spring Data compatibility → MongoDB driver/server matrix → Java requirements.
4. **Đọc migration**: API bị xóa, UUID, BigDecimal, mapping, converter, transaction và change stream.
5. **Không tự ghép dependency**: ưu tiên BOM; kiểm tra runtimeClasspath/effective POM để phát hiện override.
6. **Kiểm thử dữ liệu cũ**: đọc BSON legacy và bảo đảm đường ghi mới không phá client cũ.
7. **Kiểm thử server thật**: CRUD, aggregation, index, transaction, reactive, change stream, TLS và retry theo ứng dụng.
8. **Đo hiệu năng**: so baseline và tổ hợp đích, chú ý pool, timeout, latency và số document quét.
9. **Triển khai thử và rollback**: có checkpoint, giám sát, phương án phục hồi dữ liệu nếu thay schema/BSON.
10. **Ghi lại bằng chứng**: lưu version resolved, kết quả test, link bảng dùng và ngày đối chiếu.

### Câu hỏi tự kiểm tra

**1. Spring Data release train 2026.0 có nghĩa là Spring Data MongoDB 2026.0 không?** Không. Theo ma trận ở trên, train **2026.0** chứa Spring Data MongoDB **5.1.x**.

**2. Nếu Spring Data MongoDB yêu cầu driver tối thiểu 5.6.x, có nên luôn pin 5.6.0?** Không. Ưu tiên driver do Spring Boot BOM quản lý, sau đó xác minh bản đã resolve đáp ứng yêu cầu và được kiểm thử trong tổ hợp thực tế.

**3. Nếu MongoDB Server 8.0 nằm trong dải test của Spring Data, có phải mọi driver thế hệ cũ đều chạy được?** Không. Vẫn phải tra ma trận Java Driver ↔ MongoDB Server; có thể có driver không hỗ trợ đầy đủ hoặc không tương thích.

**4. Có thể dùng MongoDB standalone để xác minh transaction sau nâng cấp không?** Không. Kiểm thử transaction cần topology MongoDB hỗ trợ transaction, thường là replica set.

**5. Một bài test save/find thành công có chứng minh UUID và BigDecimal legacy an toàn không?** Không. Phải thử đọc BSON được ghi từ phiên bản cũ và kiểm tra biểu diễn sau khi ghi mới.

**6. Vì sao nâng Boot mà không sửa dependency MongoDB vẫn có thể thay đổi driver?** Vì Spring Boot quản lý nhiều dependency qua BOM; khi đổi Boot, các phiên bản được quản lý có thể đổi theo.

**7. Ma trận tương thích và chính sách hỗ trợ khác nhau thế nào?** Ma trận trả lời tổ hợp nào có thể/đã được test về mặt kỹ thuật; support policy trả lời bản nào còn được bảo trì, vá lỗi và hỗ trợ theo lịch phát hành.

**8. Có cần kiểm tra Java dù mục tiêu chỉ là nâng Spring Data MongoDB?** Có. Các thế hệ Spring Data/driver và Spring Framework có yêu cầu runtime Java riêng, và Boot BOM có thể thay thế nhiều thành phần liên quan.

## Kết luận

Đọc ma trận **Boot–Spring Data–driver–server** là quá trình lần theo chuỗi phụ thuộc: **Spring Boot chọn BOM; release train đồng bộ Spring Data; Spring Data MongoDB yêu cầu driver; driver giao tiếp với MongoDB Server theo mức tương thích cụ thể**. Cần kiểm tra thêm **JDK**, topology và những thay đổi về BSON, API, transaction và change stream. Quyết định nâng cấp đáng tin phải dựa trên **version đã resolve**, tài liệu đúng dòng phát hành và integration test với dữ liệu cũng như server phù hợp, thay vì chỉ dựa trên một con số version.

## Tài liệu tham khảo chính thức

- [Spring Data MongoDB — Requirements và Compatibility Matrix](https://docs.spring.io/spring-data/mongodb/reference/preface.html)
- [Spring Data — Dependencies, Release Train BOM và dependency management](https://docs.spring.io/spring-data/mongodb/reference/data-commons/dependencies.html)
- [Spring Boot — Managed Dependency Coordinates (4.1)](https://docs.spring.io/spring-boot/4.1/appendix/dependency-versions/coordinates.html)
- [Spring Boot — Managed Dependency Coordinates (4.0)](https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html)
- [Spring Boot — Managed Dependency Coordinates (3.5)](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring — Project Generations](https://spring.io/projects/generations/)
- [MongoDB — Client Library Compatibility Tables](https://www.mongodb.com/docs/drivers/compatibility/?driver-language=java&java-driver-framework=java-sync)
- [Spring Data MongoDB — Migration Guide 4.x to 5.x](https://docs.spring.io/spring-data/mongodb/reference/migration-guide/migration-guide-4.x-to-5.x.html)
- [MongoDB — Release Notes](https://www.mongodb.com/docs/manual/release-notes/)

*Các con số minh họa và các hàng ma trận trong bài được đối chiếu ngày **20/11/2026**. Khi dùng bài này để nâng một dự án, phải kiểm tra lại tài liệu của đúng phiên bản trước khi chốt BOM, driver và MongoDB Server.*
