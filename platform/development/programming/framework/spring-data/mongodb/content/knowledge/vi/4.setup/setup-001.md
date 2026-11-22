# Chọn Java, Spring Boot, Spring Data, driver và MongoDB tương thích

Khi bắt đầu một ứng dụng **Spring Data MongoDB**, việc chọn phiên bản không dừng ở câu hỏi “Spring Boot mới nhất là phiên bản nào?”. Một ứng dụng chạy ổn định cần cả **JDK**, **Spring Boot**, **Spring Framework**, **Spring Data MongoDB**, **MongoDB Java Driver** và **MongoDB Server** phù hợp với nhau. Dù mã Java biên dịch thành công, kết nối hoặc một tính năng như aggregation, index, transaction, reactive stream vẫn có thể lỗi khi các thành phần không tương thích.

Bài học thuộc phần **Khởi tạo** của module `SPRING_DATA_MONGODB`. Mục tiêu là chọn bộ phiên bản có căn cứ, khởi tạo dự án với dependency được quản lý, kết nối đến server, xác minh phiên bản thực tế và biết cách xử lý khi phải nâng cấp. Sau bước này, bạn có thể tiếp tục thực hành ánh xạ document, `MongoRepository`, `MongoTemplate`, aggregation, index, transaction, truy cập reactive, kiểm thử và chẩn đoán hiệu năng.

> **Nguyên tắc chính:** Chọn một dòng **Spring Boot** được hỗ trợ trước; dùng **BOM** (bill of materials) của dòng đó để quản lý phiên bản Spring Data và driver, rồi đối chiếu **MongoDB Server** với ma trận của cả Spring Data lẫn MongoDB Java Driver. Chỉ ghi đè phiên bản khi có nhu cầu rõ ràng và đã kiểm chứng.

## 1. Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Mô tả vai trò của từng lớp trong bộ phiên bản Java → Spring Boot → Spring Data MongoDB → Java Driver → MongoDB Server.
2. Đọc ma trận tương thích và phân biệt **yêu cầu tối thiểu**, **phiên bản đã được kiểm thử**, **phạm vi hỗ trợ**.
3. Chọn bộ phiên bản để làm mới dự án, duy trì dự án cũ hoặc dùng MongoDB Server có sẵn.
4. Tạo cấu hình Maven cơ bản, biết chọn starter đồng bộ hoặc reactive và kiểm tra dependency tree.
5. Cấu hình URI đúng với Spring Boot 3.5 và Spring Boot 4.x.
6. Kiểm tra `ping`, phát hiện sai Java runtime, dependency lệch phiên bản và vấn đề kết nối.
7. Phác thảo quy trình nâng cấp phiên bản với kiểm thử tích hợp và tiêu chí nghiệm thu.

## 2. Hiểu từng tầng phụ thuộc

```mermaid
flowchart TD
    A["JDK: biên dịch và chạy Java"] --> B["Spring Boot: phiên bản nền tảng và BOM"]
    B --> C["Spring Framework + Spring Data release train"]
    C --> D["Spring Data MongoDB: mapping, template, repository"]
    D --> E["MongoDB Java Driver: giao thức, kết nối, BSON"]
    E --> F["MongoDB Server / Atlas: lưu trữ và thực thi lệnh"]
    F -. "Khả năng server + tính năng thực tế" .-> D
```

| Thành phần | Cần xác minh gì? | Ví dụ rủi ro |
| --- | --- | --- |
| **Java/JDK** | Phiên bản tối thiểu và tối đa đã được dòng Spring Boot kiểm chứng; JDK của IDE, Maven/Gradle, CI và máy chạy | Biên dịch bằng Java 21 nhưng runtime chỉ có Java 17 khi dùng tính năng Java 21 |
| **Spring Boot** | Nhánh phát hành được hỗ trợ; yêu cầu JDK, Spring Framework, Maven/Gradle; release notes | Nâng Boot lớn nhưng giữ cấu hình cũ không còn được bind |
| **Spring Framework** | Phiên bản mà Spring Boot/Spring Data yêu cầu | Tự ép Framework 6.x với Spring Data MongoDB 5.x đòi Framework 7.x |
| **Spring Data MongoDB** | Release train, phiên bản module, mức tối thiểu của Java Driver, phiên bản MongoDB được kiểm thử | Gọi API đã đổi chữ ký hoặc hoạt động khác ở release train mới |
| **MongoDB Java Driver** | Nhánh synchronous/reactive, phiên bản và server compatibility, thay đổi giao thức/codec | Hai phiên bản `mongodb-driver-core` và `mongodb-driver-sync` bị trộn; lỗi lúc runtime |
| **MongoDB Server** | Phiên bản, topology (standalone/replica set/sharded), tính năng cần dùng, chính sách hỗ trợ | Ứng dụng cần transaction nhiều document nhưng đang chạy MongoDB standalone |
| **Build tool** | Maven/Gradle và JDK mà plugin Spring Boot hỗ trợ | Plugin Boot mới không chạy với Gradle quá cũ |

**Hai kiểu tương thích khác nhau:**

- **Tương thích kỹ thuật:** các thành phần có thể khởi chạy và giao tiếp được.
- **Tương thích đã kiểm chứng/hỗ trợ:** tổ hợp được nhóm phát triển kiểm thử hoặc hỗ trợ theo tài liệu. Có thể kết nối thành công với server mới hơn nhưng tính năng mới chưa được Spring Data hoặc driver kiểm thử đầy đủ.

Không suy ra rằng “Spring Boot hỗ trợ Java 21” thì mọi phiên bản plugin, thư viện hoặc server trong dự án tự động hỗ trợ. Cần xem cả hệ sinh thái.

## 3. Bản đồ phiên bản để định hướng ban đầu

Bảng dưới đây mô tả các **dòng** phổ biến, không phải bảng khóa patch vĩnh viễn. Mối quan hệ Spring Boot → Spring Data được xác định bằng BOM của phiên bản Boot cụ thể; các dòng Spring Data và mức tối thiểu của driver được đối chiếu với ma trận chính thức.

| Spring Boot | Java tối thiểu | Spring Data train liên quan | Spring Data MongoDB | Driver tối thiểu theo Spring Data | MongoDB Server được Spring Data kiểm thử |
| --- | --- | --- | --- | --- | --- |
| **3.5.x** | Java 17 | **2025.0** | **4.5.x** | **5.5.x** | **6.x–8.x** |
| **4.0.x** | Java 17 | **2025.1** | **5.0.x** | **5.6.x** | **6.x–8.x** |
| **4.1.x** | Java 17 | **2026.0** | **5.1.x** | **5.6.x** | **6.x–8.x** |

Một vài lưu ý khi đọc bảng:

- Dòng Boot 3.5 sử dụng Spring Framework 6.2.x; các dòng Boot 4.x sử dụng Spring Framework 7.x tương ứng. Không chủ động ghép Spring Data MongoDB 5.x với nền Spring Framework 6.x.
- Cột “driver tối thiểu” **không** bảo rằng ứng dụng nhất định đang dùng đúng phiên bản đó. BOM Spring Boot thường chọn một bản tương thích mới hơn. Kiểm tra dependency tree để biết bản **thực tế được giải quyết**.
- Cột “MongoDB Server được kiểm thử” không có nghĩa tất cả server khác chắc chắn không chạy được. Với server mới hơn, kiểm tra thêm ma trận driver–server, release notes và chạy integration test; với server quá cũ phải đặc biệt lưu ý hỗ trợ đã bị loại bỏ.
- Bảng có thể thay đổi khi ra patch hoặc release train mới. Luôn quay về trang **Requirements** đúng dòng Spring Data và **System Requirements** đúng dòng Spring Boot trước khi chốt cho dự án thực tế.
- JDK tối thiểu là một giới hạn; chọn một bản Java LTS đang được nhóm vận hành hỗ trợ (ví dụ Java 21) có thể phù hợp cho dự án mới. Tuy nhiên, việc dùng Java mới hơn mức tài liệu đã kiểm chứng cũng phải được thử nghiệm.

### Ví dụ quyết định: Java 21, Boot 4.1, MongoDB 8.0

Một tổ hợp học tập hợp lý:

```text
JDK / runtime         : Java 21 (LTS)
Spring Boot           : 4.1.2 (ví dụ một patch cụ thể trong dòng 4.1)
Spring Data MongoDB   : 5.1.x do BOM quản lý
MongoDB Java Driver   : phiên bản do BOM quản lý, tương thích mức tối thiểu 5.6.x
MongoDB Server        : 8.0 (một nhánh nằm trong dải 6.x–8.x được kiểm thử)
Build tool            : Maven 3.9.x, hoặc Gradle phiên bản tương thích Boot 4.1
API dữ liệu           : MongoRepository / MongoTemplate (imperative)
```

Không cần điền phiên bản riêng cho `spring-data-mongodb` và `mongodb-driver-sync` nếu đã dùng starter và BOM của Spring Boot. Đây là **một tổ hợp minh họa**, không phải khẳng định patch nêu trên luôn là bản mới nhất.

### Khi dự án đang dùng Java 17 hoặc Spring Boot 3.5

Nếu nền tảng vận hành đã chuẩn hóa ở Java 17 và Boot 3.5, không buộc nâng Boot chỉ vì muốn học `MongoTemplate` hay repository. Dòng Boot 3.5 và Spring Data MongoDB 4.5 vẫn cung cấp khả năng cốt lõi; điểm cần theo dõi là lịch hỗ trợ, bảo mật, API của dự án và khả năng tương thích với MongoDB Server đang sử dụng.

### Khi hệ thống đang dùng MongoDB Server 9.x hoặc máy chủ quá cũ

Đừng mặc định áp dụng cột “6.x–8.x đã kiểm thử” cho MongoDB 9.x. Hãy kiểm tra ma trận driver–server mới nhất; các ô có ký hiệu **tương thích một phần** không đảm bảo hỗ trợ toàn bộ tính năng mới. Nếu phải giữ server cũ, kiểm tra cả thay đổi loại bỏ hỗ trợ của driver. Chẳng hạn, Java Driver 5.5 ngừng hỗ trợ MongoDB Server 4.0; việc dùng Spring Data phiên bản mới cho một server đã cũ có thể không khả thi dù mã ứng dụng vẫn biên dịch.

## 4. Quy trình chọn phiên bản có thể lặp lại

Để không “đoán phiên bản”, xác minh theo thứ tự sau:

1. **Liệt kê ràng buộc vận hành:** phiên bản JDK được phép, Maven/Gradle/CI, MongoDB Server đang có, hình thức triển khai (local/Atlas/replica set).
2. **Liệt kê tính năng cần dùng:** mapping, repository, aggregation, index, multi-document transaction, change streams, truy cập reactive, time-series/vector search (nếu có).
3. **Chọn dòng Spring Boot được hỗ trợ** phù hợp JDK và vòng đời bảo trì dự án; đối chiếu trang System Requirements đúng dòng.
4. **Đọc BOM Spring Boot** để biết Spring Data release train và Java Driver được quản lý. Tránh tự khai báo version từng thư viện khi không cần.
5. **Kiểm tra ma trận Spring Data MongoDB:** yêu cầu Spring Framework/JDK, driver tối thiểu và server được kiểm thử.
6. **Kiểm tra ma trận MongoDB Java Driver:** server cụ thể, xác thực, mã hóa/TLS, tính năng driver mới và hỗ trợ Java.
7. **Khởi tạo thử và chạy smoke test** trên một MongoDB instance cùng nhánh với môi trường mục tiêu; chạy integration tests trước khi duyệt tổ hợp.

Ví dụ hồ sơ quyết định có thể ghi ngay trong tài liệu kỹ thuật của dự án:

| Trường | Giá trị mẫu |
| --- | --- |
| Java build/runtime | 21 |
| Spring Boot | 4.1.2 |
| Spring Data MongoDB | 5.1.x (BOM) |
| Java Driver | Bản được BOM giải quyết; xác minh bằng dependency tree |
| MongoDB Server | 8.0 trên replica set cho kiểm thử transaction |
| Kiểu truy cập | Imperative; `MongoTemplate` và `MongoRepository` |
| Build/CI | Maven Wrapper; xác minh `mvnw -version` trên CI |
| Tiêu chí nghiệm thu | Kết nối, CRUD, index, aggregation, transaction và retry theo yêu cầu |

## 5. Tạo dự án Maven với dependency được quản lý

Ta dùng tổ hợp ví dụ **Java 21 + Spring Boot 4.1.2 + MongoDB 8.0**, Spring Data và driver được quản lý bởi Spring Boot.

Tại **Spring Initializr** hoặc trong dự án Maven, chọn các dependency cần thiết. Đây là `pom.xml` tối giản cho ứng dụng dùng `MongoTemplate`/repository đồng bộ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.learning</groupId>
    <artifactId>mongo-compat-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>21</java.version>
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

**Vì sao không viết version cho starter, Spring Data hoặc driver?** `spring-boot-starter-parent` kế thừa cơ chế dependency management của Spring Boot. Nhờ đó, toàn bộ nhóm Spring Data và các module driver được chọn thành một bộ nhất quán theo BOM. Nếu ứng dụng dùng parent khác, có thể import BOM `spring-boot-dependencies` với đúng phiên bản Boot trong `dependencyManagement` thay vì thêm version rải rác.

Nếu dùng Gradle, nguyên tắc tương tự: áp dụng plugin Spring Boot đúng dòng, dùng cơ chế quản lý phụ thuộc tương ứng (BOM qua dependency-management plugin hoặc Gradle `platform`) và khai báo starter không kèm phiên bản. Dùng Gradle Wrapper để cố định phiên bản build tool theo dự án.

### 5.1. Chọn starter đúng kiểu truy cập

| Nhu cầu | Dependency khởi đầu | API thường dùng |
| --- | --- | --- |
| Imperative / blocking | `spring-boot-starter-data-mongodb` | `MongoTemplate`, `MongoRepository` |
| Reactive / non-blocking | `spring-boot-starter-data-mongodb-reactive` | `ReactiveMongoTemplate`, `ReactiveMongoRepository` |
| Chỉ dùng MongoDB Java Driver trực tiếp, không cần Spring Data | `mongodb-driver-sync` hoặc driver reactive phù hợp | `MongoClient`, `MongoCollection`, BSON API |

Reactive driver dùng cơ chế Reactive Streams. **Không** biến các lệnh blocking thành non-blocking chỉ bằng cách đưa `Mono`/`Flux` vào chữ ký service. Chọn kiểu truy cập ngay từ đầu theo kiến trúc ứng dụng; nếu cả hai stack cùng tồn tại phải hiểu và cấu hình rõ các client/repository tương ứng.

Không thêm thủ công `mongodb-driver-core` hoặc `bson` nếu starter đã kéo vào; tránh các module driver nhận những phiên bản khác nhau do khai báo trực tiếp.

### 5.2. Xác minh phiên bản mà Maven/Gradle thực sự dùng

Chạy trong thư mục dự án của bạn (đây là **lệnh ví dụ**, không cần chạy khi đang đọc lý thuyết):

```bash
java -version
./mvnw -version
./mvnw dependency:tree
```

Trên Windows, dùng `.\mvnw.cmd -version` và `.\mvnw.cmd dependency:tree`. Trong kết quả, kiểm tra:

- `org.springframework.data:spring-data-mongodb`.
- `org.mongodb:mongodb-driver-sync` với imperative, hoặc `org.mongodb:mongodb-driver-reactivestreams` với reactive.
- `org.mongodb:mongodb-driver-core` và `org.mongodb:bson` cùng nhánh/phiên bản phù hợp.
- Các module Spring Framework và Spring Data Commons có phiên bản do cùng bộ BOM quản lý.

Với Gradle:

```bash
./gradlew -version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-mongodb --configuration runtimeClasspath
./gradlew dependencyInsight --dependency mongodb-driver-core --configuration runtimeClasspath
```

**Phân biệt bản khai báo và bản được chọn:** POM/Gradle build có thể khai báo version ở nhiều tầng; công cụ giải quyết xung đột dependency sẽ chọn bản cuối cùng. Khi chẩn đoán lỗi runtime, hãy dùng dependency tree hoặc dependencyInsight, thay vì chỉ đọc phần `dependencies`.

## 6. Cấu hình MongoDB URI theo đúng dòng Spring Boot

Một khác biệt quan trọng giữa **Spring Boot 3.5** và **Spring Boot 4.x** là tiền tố property kết nối MongoDB.

| Dòng Spring Boot | Cấu hình URI kết nối |
| --- | --- |
| **3.5.x** | `spring.data.mongodb.uri` |
| **4.0.x / 4.1.x** | `spring.mongodb.uri` |

Từ Spring Boot 4, nhiều thuộc tính kết nối chuyển từ `spring.data.mongodb.*` sang `spring.mongodb.*`. Một số thuộc tính phụ thuộc trực tiếp vào Spring Data (ví dụ `spring.data.mongodb.auto-index-creation`) vẫn giữ tiền tố cũ. Đừng chuyển tất cả các property bằng một phép thay chuỗi mù quáng.

### 6.1. Với Spring Boot 4.x

Ví dụ `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: mongo-compat-demo
  mongodb:
    uri: "mongodb://localhost:27017/learning_mongo"
```

Với Spring Boot 3.5, cấu hình URI tương đương là:

```yaml
spring:
  data:
    mongodb:
      uri: "mongodb://localhost:27017/learning_mongo"
```

Cả hai ví dụ dùng MongoDB local **không bật xác thực**, phù hợp môi trường học tập được cách ly. Khi triển khai thực tế, lấy URI từ biến môi trường hoặc secret manager, bật xác thực và TLS theo yêu cầu:

```yaml
spring:
  mongodb:
    uri: "${MONGODB_URI}"
```

Biến `MONGODB_URI` phải được cung cấp bởi môi trường triển khai; ví dụ ứng dụng sẽ không khởi động đúng nếu biến chưa được đặt. Không commit password hoặc connection string chứa credential thật vào mã nguồn. Nếu password nằm trong URI, cần encode ký tự đặc biệt đúng chuẩn URI.

### 6.2. Hiểu các kiểu connection string

```text
# Một máy chủ local:
mongodb://localhost:27017/learning_mongo

# Replica set (địa chỉ minh họa, cần triển khai thực tế):
mongodb://node1:27017,node2:27017,node3:27017/learning_mongo?replicaSet=rs0

# MongoDB Atlas (hostname minh họa):
mongodb+srv://USER:PASSWORD@cluster.example.mongodb.net/learning_mongo
```

- `mongodb://` dùng host, port và tham số kết nối; có thể khai báo nhiều host cho replica set.
- `mongodb+srv://` dùng DNS SRV/TXT để khám phá host và tham số của cluster; yêu cầu DNS, mạng và cấu hình TLS phù hợp.
- `authSource` chỉ nơi xác thực khi cần; tên database ứng dụng và database xác thực không nhất thiết trùng nhau.
- Driver có thể khởi tạo client và chỉ truy cập mạng khi thực hiện thao tác. Vì vậy ứng dụng khởi động thành công **chưa chứng minh** kết nối đã hoạt động.

## 7. Smoke test: xác nhận phiên bản, kết nối và mapping

Một phép thử tối thiểu là thực thi `ping` thực sự trên MongoDB từ ứng dụng.

```java
package dev.learning;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootApplication
public class MongoCompatDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MongoCompatDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner verifyMongo(MongoTemplate template) {
        return args -> {
            var response = template.executeCommand("{ ping: 1 }");
            System.out.println("MongoDB ping: " + response.toJson());
        };
    }
}
```

Nếu cấu hình đúng và MongoDB Server có thể truy cập được, lệnh sẽ trả kết quả chứa `"ok": 1`. Khi thất bại, xem **nguyên nhân gốc** trong stack trace: timeout, authentication, TLS, DNS/SRV, sai host/port hoặc xung đột classpath. Không in URI chứa mật khẩu ra console.

Tiếp theo, thử mapping và truy cập repository:

```java
package dev.learning;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("books")
public class Book {
    @Id
    private String id;

    private String title;

    public Book() {}

    public Book(String title) {
        this.title = title;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
}
```

```java
package dev.learning;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface BookRepository extends MongoRepository<Book, String> {
}
```

```java
@Bean
CommandLineRunner smokeTest(BookRepository books) {
    return args -> {
        Book saved = books.save(new Book("Spring Data MongoDB"));
        Book found = books.findById(saved.getId()).orElseThrow();
        System.out.println(found.getTitle());
    };
}
```

Đoạn `smokeTest` là phần có thể thêm vào lớp cấu hình Spring tương ứng; khi dùng chung với `verifyMongo`, có thể đặt cả hai bean trong lớp `@SpringBootApplication`. Đây là ví dụ **tạo dữ liệu thực** trong collection `books`, nên dùng database học tập riêng.

Một bài test khởi tạo phù hợp chỉ trả lời “có thể kết nối và CRUD cơ bản”. Để kiểm chứng các tính năng có yêu cầu server riêng, cần test chuyên biệt.

## 8. Chọn MongoDB Server theo tính năng và topology

**Chạy được CRUD cơ bản** không đồng nghĩa đã có đủ điều kiện cho mọi chức năng của Spring Data MongoDB.

| Nhu cầu | Cần xem xét |
| --- | --- |
| CRUD, mapping, `MongoRepository`, `MongoTemplate` | Driver–server tương thích, quyền truy cập collection, kiểu dữ liệu BSON |
| Aggregation pipeline | Các stage/operator thực sự tồn tại trên phiên bản server được dùng |
| Index (compound, TTL, text, wildcard, v.v.) | Tính năng index và giới hạn tương ứng của server; kế hoạch tạo index |
| Multi-document transactions | Deployment và cấu hình hỗ trợ transaction (replica set hoặc sharded cluster phù hợp); session và transaction manager |
| Change streams | Deployment hỗ trợ change streams, quyền truy cập và cơ chế tiếp tục khi mất kết nối |
| Reactive access | Reactive driver và API/reactive runtime phù hợp; server vẫn phải hỗ trợ lệnh cần dùng |
| Đo hiệu năng/diagnostics | Index, `explain`, profiler/metrics, dữ liệu thử và cấu hình gần môi trường thật |

### Standalone khác replica set

Một MongoDB standalone có thể đủ cho CRUD và bài nhập môn. Nhưng transaction trên nhiều document cần topology phù hợp; để học transaction có thể tạo **single-node replica set** ở local, còn môi trường sản xuất thường dùng replica set nhiều node hoặc sharded cluster theo yêu cầu độ sẵn sàng.

Tính năng mới của server không tự hiện diện qua Spring Data phiên bản cũ. Khi định dùng một aggregation operator hoặc loại index mới, cần kiểm tra **server supports → driver supports → Spring Data exposes**, và nếu Spring Data chưa có API tiện lợi có thể cần dùng API mức thấp (trong phạm vi được hỗ trợ) hoặc nâng phiên bản.

### MongoDB Atlas và hệ thống tự quản

Atlas quản lý nhiều khía cạnh triển khai nhưng ứng dụng vẫn phải chọn đúng URI, quyền, chính sách IP/network, TLS và phiên bản driver. Với server tự quản, nhóm vận hành cần theo dõi thêm topology, phiên bản server, lịch hỗ trợ, backup và quá trình nâng cấp.

## 9. Những xung đột phổ biến và cách xác minh

| Triệu chứng | Giả thuyết cần kiểm tra | Cách xác nhận |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Runtime Java thấp hơn mức bytecode đã biên dịch | `java -version`, `mvnw -version`, cấu hình Java compiler và JDK trên CI |
| `NoSuchMethodError` / `NoClassDefFoundError` | Thư viện Spring Data, Spring Framework, MongoDB driver bị lệch phiên bản | Dependency tree, BOM, các `exclusions` / dependency overrides |
| `ClassNotFoundException` với API reactive | Chưa thêm starter/driver reactive phù hợp | Dependency tree, kiểu repository/template |
| `MongoTimeoutException` / server selection timeout | Server không truy cập được, host/port/DNS/TLS/replica set sai | `ping` server, DNS, firewall, URI, topology, log driver |
| `MongoSecurityException` / authentication failed | Sai user/password/authSource hoặc quyền | Kiểm tra tài khoản và auth database; tránh log secret |
| Startup chạy nhưng query vào database sai | URI/default database hoặc property bị đổi sau khi nâng Boot | Kiểm tra `spring.mongodb.uri` ở Boot 4 và `spring.data.mongodb.uri` ở Boot 3.5 |
| Transaction báo không được hỗ trợ | Đang dùng standalone, thiếu manager hoặc ngữ cảnh transaction | Topology, `MongoTransactionManager` hoặc `ReactiveMongoTransactionManager`, cách gọi service |
| Lỗi khi gọi stage aggregation mới | Phiên bản server cũ hơn yêu cầu tính năng | Xem tài liệu và release notes của stage/operator đó |
| Query chậm dù phiên bản đều tương thích | Thiếu index, dữ liệu không phù hợp hoặc truy vấn chưa tối ưu | `explain`, profiler, metric, đối chiếu tải |

### Rủi ro khi “tự nâng driver cho nhanh”

Giả sử Spring Boot BOM quản lý `mongodb-driver-sync`, `mongodb-driver-core` và `bson`. Nếu bạn chỉ ghi đè riêng `mongodb-driver-sync` sang một bản khác, API có thể biên dịch nhưng runtime vẫn sử dụng `mongodb-driver-core` cũ.

Quy trình đúng là xác định **tại sao phải override**, kiểm tra hướng dẫn của Spring Boot/Spring Data, nâng cả nhóm phụ thuộc theo cơ chế được hỗ trợ, rồi kiểm thử kết nối và nghiệp vụ. Với lỗi bảo mật, ưu tiên nâng lên bản patch Boot/driver đã được dự án bảo trì trước khi tự lắp các phiên bản không thuộc cùng bộ BOM.

## 10. Nâng cấp từ Spring Boot 3.5 lên 4.x

Đây là thay đổi **major**, nên cần coi như một migration có kiểm chứng, không chỉ thay `<version>` trong `pom.xml`.

1. Đảm bảo JDK/build tool đáp ứng yêu cầu của Spring Boot mục tiêu; với Boot 4.1, cần Gradle 8.14+ nếu dùng Gradle 8 hoặc nhánh Gradle 9 được hỗ trợ.
2. Nâng Spring Boot parent/plugin và để BOM chọn lại Spring Framework, Spring Data, driver.
3. Đối chiếu migration guide của Spring Boot 4, đặc biệt các thay đổi starter, package và cấu hình.
4. Di chuyển thuộc tính URI từ `spring.data.mongodb.uri` sang `spring.mongodb.uri`; kiểm tra các thuộc tính khác theo tài liệu, tránh áp dụng thay thế hàng loạt.
5. Biên dịch lại toàn bộ, kiểm tra dependency tree, sửa API và cấu hình đã thay đổi.
6. Chạy smoke test, CRUD, mapping BSON, aggregation, index, transaction và reactive nếu ứng dụng có sử dụng.
7. Chạy kiểm thử tích hợp trên **đúng nhánh MongoDB Server** đang dùng và kiểm tra đường rollback nếu nâng cấp không thành công.

Ví dụ thay đổi cấu hình:

```diff
 spring:
-  data:
-    mongodb:
-      uri: "mongodb://localhost:27017/learning_mongo"
+  mongodb:
+    uri: "mongodb://localhost:27017/learning_mongo"
```

Lưu ý rằng không có bảo đảm mọi mã ở Boot 3.5 sẽ chạy nguyên trạng sau khi nâng Boot 4. Với các API tùy chỉnh, kiểm tra tài liệu migration tương ứng của Spring Data MongoDB.

## 11. Kiểm thử tính tương thích theo mức độ rủi ro

Một ứng dụng mới chỉ thực hành CRUD có thể dùng checklist đơn giản. Ứng dụng có transaction và reactive cần kiểm chứng thêm các trường hợp hiếm xảy ra.

| Mức | Kiểm tra | Tiêu chí đạt |
| --- | --- | --- |
| **Build** | Build bằng JDK được chọn, đúng Maven/Gradle Wrapper | Không có lỗi compiler, plugin hoặc dependency version |
| **Kết nối** | `ping` từ ứng dụng đến MongoDB mục tiêu | Có phản hồi thành công; không rò rỉ credential |
| **Mapping** | Lưu/đọc document có `@Id`, nested field, collection name, kiểu ngày/số/UUID theo nhu cầu | Dữ liệu đọc lại phù hợp định dạng mong muốn |
| **Query** | Repository query và `MongoTemplate` | Truy vấn và cập nhật đúng; không lỗi codec hoặc API |
| **Index/aggregation** | Tạo index trên môi trường thử, chạy pipeline đặc trưng | Không có command/operator không được server hỗ trợ |
| **Transaction** | Chuyển hai document cùng transaction rồi tạo lỗi có chủ ý | Thay đổi được rollback trên topology hỗ trợ |
| **Reactive** | CRUD với `ReactiveMongoTemplate` hoặc reactive repository; backpressure/cancellation nếu liên quan | Không trộn blocking call gây nghẽn luồng non-blocking |
| **Hiệu năng** | Đo `explain`, p95/p99 latency và pool metrics theo tải mẫu | Đáp ứng ngưỡng đã thống nhất của ứng dụng |

Nếu dùng Testcontainers, hãy chạy phiên bản MongoDB image tương ứng môi trường đích, không chỉ dùng `latest`. Cần topology replica set cho bài test transaction. Dữ liệu test phải độc lập với database sản xuất.

### Bài tập thực hành

**Bài 1 — Lập ma trận cho dự án mới:** Nhóm dùng Java 21 và MongoDB 8.0, muốn repository + aggregation + transaction. Chọn một dòng Spring Boot có hỗ trợ, xác định Spring Data MongoDB liên quan, yêu cầu driver tối thiểu và topology cần có. Ghi rõ nguồn tài liệu để người khác kiểm chứng.

**Bài 2 — Nhìn vào dependency tree:** Một đồng nghiệp báo `NoSuchMethodError` khi chạy. Hãy mô tả cách xác định bản `spring-data-mongodb`, `mongodb-driver-sync`, `mongodb-driver-core` và `bson` được resolve; đề xuất cách khôi phục sự nhất quán phiên bản.

**Bài 3 — Di chuyển cấu hình:** Ứng dụng chạy trên Boot 3.5 với `spring.data.mongodb.uri` được nâng lên Boot 4.1. Hãy sửa property, kiểm tra connection URI thực tế và mô tả phép thử đủ để khẳng định ứng dụng kết nối tới đúng database.

**Bài 4 — Kiểm thử server mới:** Một nhóm muốn nâng MongoDB Server lên phiên bản chưa nằm trong dải “được Spring Data kiểm thử”. Bạn sẽ đọc ma trận nào, làm những phép thử nào và cần bằng chứng gì trước khi chấp thuận triển khai?

### Đáp án gợi ý

1. Ví dụ Boot 4.1.x + Java 21 + Spring Data MongoDB 5.1.x do BOM quản lý, driver đạt mức yêu cầu, MongoDB 8.0 và replica set cho transaction; xác nhận patch/build tool theo tài liệu.
2. Kiểm tra dependency tree, tìm override và module không đồng bộ, trả quyền chọn phiên bản về BOM, rồi kiểm thử lại.
3. Đổi thành `spring.mongodb.uri` và chạy `ping` cùng phép ghi/đọc ở database kiểm thử; không lấy startup success làm bằng chứng duy nhất.
4. Đối chiếu ma trận **Spring Data → Java Driver → MongoDB Server**, release notes/điểm đổi tính năng, chạy integration test và thử tải trên bản server sẽ triển khai.

## 12. Checklist cuối bài

- [ ] Ghi rõ phiên bản **Java build/runtime** và cấu hình CI.
- [ ] Chọn **Spring Boot** dựa trên hỗ trợ và yêu cầu hệ thống, ghi patch version được chốt.
- [ ] Xác minh **Spring Data release train** và driver từ BOM/`dependency:tree`.
- [ ] Đối chiếu **MongoDB Server** với cả ma trận Spring Data và Java Driver.
- [ ] Chọn **imperative** hoặc **reactive** đúng với kiến trúc sử dụng.
- [ ] Dùng đúng key URI: `spring.data.mongodb.uri` ở Boot 3.5; `spring.mongodb.uri` ở Boot 4.x.
- [ ] Chạy `ping` và CRUD trong database thử nghiệm.
- [ ] Kiểm thử riêng aggregation, index, transaction, reactive theo tính năng thực tế.
- [ ] Giữ mật khẩu ngoài source code; kiểm tra TLS, network và quyền truy cập.
- [ ] Có hướng nâng cấp và rollback khi thay đổi major version.

## 13. Tài liệu chính thức để đối chiếu phiên bản

Các trang sau có thể được cập nhật theo từng patch/release train; khi dùng cho dự án thực tế, mở **đúng nhánh phiên bản** và ghi lại ngày kiểm tra:

1. [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html).
2. [Spring Boot 4.1 — System Requirements](https://docs.spring.io/spring-boot/4.1/system-requirements.html).
3. [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/4.1/appendix/application-properties/index.html), xem `spring.mongodb.*`.
4. [Spring Boot — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/4.1/reference/data/nosql.html).
5. [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide).
6. [Spring Data MongoDB — Requirements & Compatibility Matrix](https://docs.spring.io/spring-data/mongodb/reference/preface.html).
7. [Spring Data — Dependency Management / BOM](https://docs.spring.io/spring-data/mongodb/reference/data-commons/dependencies.html).
8. [MongoDB — Client Library Compatibility Tables](https://www.mongodb.com/docs/drivers/compatibility/?driver-language=java&java-driver-framework=java-sync).
9. [MongoDB Java Driver — Upgrade Driver Versions](https://www.mongodb.com/docs/drivers/java/sync/current/reference/upgrade/).

**Ghi nhớ:** Sự tương thích được chứng minh bằng **ma trận chính thức, dependency thực tế và bài kiểm thử trên server mục tiêu**. Một tổ hợp “khởi động được” chỉ là bước đầu để sử dụng Spring Data MongoDB ổn định.
