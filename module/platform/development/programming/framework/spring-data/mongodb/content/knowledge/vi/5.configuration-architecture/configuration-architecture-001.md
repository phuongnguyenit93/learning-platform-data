# Auto-configuration của Spring Boot cho MongoDB

## 1. Auto-configuration giải quyết vấn đề gì?

Trong một ứng dụng Java sử dụng **Spring Data MongoDB**, lập trình viên cần kết nối đến MongoDB, ánh xạ document thành đối tượng, xây dựng truy vấn bằng `MongoTemplate` hoặc repository, cấu hình kết nối và kiểm soát tài nguyên. Nếu tự lắp ghép tất cả, ứng dụng phải định nghĩa từng bean kết nối, factory, converter, template và repository infrastructure.

**Auto-configuration của Spring Boot** là cơ chế quan sát thư viện có trên classpath, các bean đã được ứng dụng khai báo và các thuộc tính cấu hình để **tự đăng ký những bean thích hợp**. Nhờ đó, với một starter và vài dòng cấu hình, ứng dụng thường đã có thể inject:

- `com.mongodb.client.MongoClient` để truy cập MongoDB bằng Java Sync Driver;
- `MongoDatabaseFactory`, `MongoTemplate` và hạ tầng ánh xạ của Spring Data MongoDB;
- Các implementation của interface `MongoRepository` được Spring Data sinh ra tại runtime.

Auto-configuration **không cài đặt hoặc khởi động MongoDB server**, không tự quyết định thiết kế collection/index tối ưu, và không bảo đảm mọi kết nối hay câu lệnh đều thành công. Bean có thể được tạo lúc startup, trong khi lỗi mạng hoặc xác thực chỉ xuất hiện khi driver thực sự chọn server và thực thi thao tác.

> **Phạm vi phiên bản:** Tên thuộc tính và lớp cấu hình cụ thể trong các ví dụ tập trung vào **Spring Boot 3.x / Spring Data MongoDB 4.x** và Java 17 trở lên. Ở các phiên bản major khác (đặc biệt khi nâng lên Spring Boot 4.x), cần kiểm tra configuration metadata và tài liệu đúng phiên bản dự án trước khi sao chép tên package, property hoặc annotation.

## 2. Spring Boot nhận biết cần cấu hình MongoDB như thế nào?

Một ứng dụng Spring Boot thường bật auto-configuration qua `@SpringBootApplication` (bao gồm `@EnableAutoConfiguration`). Boot nạp tập hợp lớp auto-configuration tương ứng từ các thư viện có mặt và đánh giá **điều kiện** của chúng.

| Thành phần | Vai trò | Điều kiện/giới hạn cần nhớ |
|---|---|---|
`spring-boot-starter-data-mongodb` | Kéo các dependency cho MongoDB đồng bộ, Spring Data repositories và driver phù hợp | Phù hợp với ứng dụng truy cập dữ liệu kiểu chặn (imperative) |
`spring-boot-starter-data-mongodb-reactive` | Kéo Spring Data MongoDB reactive và MongoDB Reactive Streams Driver | Phù hợp luồng dữ liệu reactive với `Mono`/`Flux` |
`MongoAutoConfiguration` | Thường cung cấp `MongoClient` đồng bộ từ driver và cấu hình của Boot | Trong Boot 3.x; phụ thuộc classpath/bean hiện hữu |
`MongoDataAutoConfiguration` | Lắp ghép phần lớn hạ tầng MongoDB đồng bộ của Spring Data | Dùng factory, converter, mapping và template khi điều kiện phù hợp |
`MongoRepositoriesAutoConfiguration` | Kích hoạt repository theo quy ước quét package | Cần Spring Data repository và không bị tắt/ghi đè cơ chế cấu hình liên quan |
Các lớp auto-configuration reactive | Cấp client, factory, template và repository reactive | Chỉ có tác dụng khi driver và thư viện reactive tương ứng hiện diện |

Các annotation thường xuất hiện trong auto-configuration:

- `@ConditionalOnClass`: chỉ cấu hình nếu API cần thiết có trên classpath.
- `@ConditionalOnMissingBean`: tạo bean mặc định khi ứng dụng chưa cung cấp bean tương ứng.
- `@ConditionalOnBean`: phụ thuộc vào bean khác đã có.
- `@ConditionalOnProperty` và các điều kiện liên quan: quyết định theo property và trạng thái cấu hình.

Vì vậy, **“đã thêm starter” không đồng nghĩa với “chắc chắn có mọi bean”**. Bean do ứng dụng tự định nghĩa, package scanning hoặc điều kiện bị vô hiệu hóa có thể làm kết quả khác với mặc định.

~~~mermaid
flowchart TD
    A["Spring Boot startup"] --> B["Đọc classpath, Environment, bean definitions"]
    B --> C{"Có MongoDB Sync Driver và điều kiện phù hợp?"}
    C -->|"Có"| D["MongoClient / connection settings"]
    C -->|"Không"| X["Không đăng ký stack sync mặc định"]
    D --> E["MongoDatabaseFactory"]
    E --> F["Mapping context + MongoConverter"]
    E --> G["MongoTemplate / MongoOperations"]
    F --> G
    G --> H{"Có repository interface được quét?"}
    H -->|"Có"| I["Spring Data tạo MongoRepository proxy"]
    H -->|"Không"| J["Có thể dùng MongoTemplate trực tiếp"]
~~~

Sơ đồ biểu thị **quan hệ phụ thuộc về mặt khái niệm**, không phải thứ tự khởi tạo chính xác của mọi bean. Repository thông thường được xây dựng trên hạ tầng truy cập và mapping của Spring Data; driver là tầng kết nối thấp hơn.

## 3. Thiết lập tối thiểu cho MongoDB đồng bộ

### 3.1. Thêm starter

Với Gradle, sử dụng dependency có version được Spring Boot dependency management quản lý:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
}
~~~

Hoặc với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

Trong project sử dụng `spring-boot-starter-parent` hoặc BOM của Spring Boot, thông thường không cần tự đặt version riêng cho Spring Data MongoDB và MongoDB Java Driver. Trộn các version không tương thích có thể gây lỗi class/method lúc chạy.

### 3.2. Cấu hình URI và database

Ví dụ `application.yml` cho môi trường chạy MongoDB cục bộ:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://localhost:27017/book_catalog
~~~

Trong Spring Boot 3.x, `spring.data.mongodb.uri` là cấu hình URI thường dùng. Phần `book_catalog` là database của ví dụ. Nếu không có database trong URI, cần xác định database phù hợp theo cách cấu hình mà phiên bản Boot hỗ trợ. Hạn chế chỉ định database ở nhiều nơi khác nhau để tránh hiểu nhầm giá trị nào đang được áp dụng.

Một cách phù hợp hơn cho môi trường triển khai là truyền URI qua biến môi trường:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

Ví dụ giá trị của `MONGODB_URI` có thể là `mongodb://localhost:27017/book_catalog` trong local hoặc URI tới MongoDB cluster với xác thực và TLS ở môi trường thực. Biến môi trường `SPRING_DATA_MONGODB_URI` cũng có thể được Boot 3.x ánh xạ trực tiếp theo quy tắc relaxed binding.

Lưu ý:

- Giữ username, password và các khóa bí mật trong secret manager hoặc cấu hình môi trường; không commit credential thật vào Git.
- Nếu mật khẩu trong connection URI chứa ký tự đặc biệt, dùng đúng cách percent-encode phần thông tin xác thực theo URI.
- Tùy hệ thống, có thể cần cấu hình `authSource`, TLS, replica set, cơ chế xác thực hoặc SRV URI `mongodb+srv://...`; kiểm tra khả năng hỗ trợ của driver và hạ tầng.
- Boot có thể tạo `MongoClient` trước khi chắc chắn server có thể truy cập. Hãy thử thao tác thực sự (hoặc health check phù hợp) khi xác minh kết nối.

### 3.3. Ví dụ ứng dụng sử dụng bean do Boot tạo

Cấu trúc package:

~~~text
com.example.catalog
├── CatalogApplication.java
├── data
│   ├── Book.java
│   └── BookRepository.java
└── service
    └── BookCatalogService.java
~~~

File `CatalogApplication.java`:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

File `data/Book.java`:

~~~java
package com.example.catalog.data;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "books")
public class Book {
    @Id
    private String id;
    private String title;
    private String author;

    public Book() {}

    public Book(String title, String author) {
        this.title = title;
        this.author = author;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getAuthor() { return author; }
    public void setAuthor(String author) { this.author = author; }
}
~~~

File `data/BookRepository.java`:

~~~java
package com.example.catalog.data;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface BookRepository extends MongoRepository<Book, String> {
    List<Book> findByAuthor(String author);
}
~~~

File `service/BookCatalogService.java`:

~~~java
package com.example.catalog.service;

import com.example.catalog.data.Book;
import com.example.catalog.data.BookRepository;
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class BookCatalogService {
    private final BookRepository books;
    private final MongoTemplate mongoTemplate;

    public BookCatalogService(BookRepository books, MongoTemplate mongoTemplate) {
        this.books = books;
        this.mongoTemplate = mongoTemplate;
    }

    public Book add(String title, String author) {
        return books.save(new Book(title, author));
    }

    public List<Book> byAuthor(String author) {
        return books.findByAuthor(author);
    }

    public List<Book> byTitle(String title) {
        Query query = Query.query(Criteria.where("title").is(title));
        return mongoTemplate.find(query, Book.class);
    }
}
~~~

Ở đây **không có class `@Configuration` tự tạo `MongoClient`, `MongoTemplate` hay implementation của `BookRepository`**. Boot và Spring Data tạo các bean cần thiết khi starter, package scanning và cấu hình hợp lệ.

`@Document` quy định tên collection được ánh xạ; `@Id` quy định trường định danh. Annotation không có nghĩa là MongoDB tự tạo collection khi ứng dụng khởi động. Collection thường được tạo khi có dữ liệu ghi hoặc qua cơ chế khởi tạo riêng.

## 4. Những bean nào được cấu hình tự động?

### 4.1. MongoClient: kết nối và quản lý connection pool

`MongoClient` của driver đồng bộ thường là bean dùng chung, **thread-safe** và quản lý connection pool. Một ứng dụng không nên tạo `MongoClient` cho từng HTTP request. Driver chịu trách nhiệm chọn server, kết nối, pool, retry theo cấu hình; Spring Boot quản lý vòng đời bean mà nó tạo.

URI là đầu vào quan trọng, nhưng kết nối hiệu quả còn phụ thuộc:

- server selection timeout, connect timeout, socket timeout;
- kích thước pool, thời gian chờ lấy connection và tốc độ tăng tải;
- TLS, xác thực, topology/replica set, retry và read/write concern;
- độ ổn định mạng và sức khỏe của MongoDB server.

Các thông số này **không nên chỉnh theo cảm tính**. Hãy quan sát độ trễ, số request đồng thời, tình trạng pool và thống kê server trước khi thay đổi.

### 4.2. MongoDatabaseFactory, mapping và MongoTemplate

Trên `MongoClient`, Spring Data sử dụng `MongoDatabaseFactory` để truy cập database theo cách phù hợp với hạ tầng Spring. `MongoMappingContext` và `MappingMongoConverter` giúp ánh xạ `@Document`, `@Id`, `@Field` và các conversion được cấu hình. `MongoTemplate`/`MongoOperations` cung cấp API truy vấn, aggregation, cập nhật, bulk write và các thao tác với collection.

Ví dụ inject abstraction để giảm phụ thuộc vào implementation cụ thể:

~~~java
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.stereotype.Component;

@Component
public class MongoAccessProbe {
    private final MongoOperations operations;

    public MongoAccessProbe(MongoOperations operations) {
        this.operations = operations;
    }

    public boolean hasCollection(String name) {
        return operations.collectionExists(name);
    }
}
~~~

`MongoTemplate` vẫn áp dụng mapping Spring Data khi làm việc với entity; đó là một khác biệt quan trọng so với dùng `MongoCollection<Document>` của driver trực tiếp.

### 4.3. Repository proxy và phạm vi quét package

Với `@SpringBootApplication` đặt ở `com.example.catalog`, Boot có thể tìm các repository nằm trong các package con như `com.example.catalog.data`. Spring Data tạo implementation runtime cho interface `MongoRepository` và các query method được hỗ trợ.

Nếu repository nằm **ngoài vùng quét**, bean có thể không được tạo dù `MongoTemplate` vẫn hoạt động. Các phương án là chuyển lớp ứng dụng lên package gốc phù hợp hoặc cấu hình quét một cách tường minh:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableMongoRepositories(basePackages = "com.example.externalrepos")
public class MongoRepositoriesConfig {
}
~~~

Chỉ dùng cấu hình này nếu thật sự cần quét ngoài quy ước. Nếu tự bật repository scanning, kiểm tra vùng quét để không tạo trùng repository hoặc vô tình chọn nhầm `MongoTemplate` khi có nhiều database.

## 5. Điều gì xảy ra khi tự khai báo bean?

Một phần quan trọng của auto-configuration là cơ chế **back-off**: với những bean có điều kiện `@ConditionalOnMissingBean`, Boot tránh tạo bean mặc định khi ứng dụng đã cung cấp bean tương đương.

| Tình huống | Hành vi cần dự kiến |
|---|---|
Không tự khai báo bean nào, starter sync có mặt | Boot thường tạo stack mặc định |
Tự khai báo `MongoClient` | Phần cấu hình client mặc định có thể nhường chỗ; các bean Spring Data khác vẫn có thể sử dụng client được cung cấp |
Tự khai báo `MongoTemplate`/`MongoOperations` | Auto-configuration cho template có thể back-off; repository cần tham chiếu đúng template |
Tự khai báo converter/factory hoặc nhiều client | Một số bean mặc định có thể không còn được tạo theo cách mong muốn; cần xác định rõ ranh giới và dependency |
Loại trừ Mongo auto-configuration | Không được kỳ vọng stack tương ứng vẫn tự xuất hiện |

Chi tiết **bean nào** back-off phụ thuộc phiên bản và từng annotation điều kiện. Không nên giả định rằng tự khai báo một bean sẽ tắt toàn bộ MongoDB auto-configuration.

### 5.1. Ưu tiên property trước khi tự tạo MongoClient

Nếu cần thay URI hoặc database, dùng cấu hình. Nếu cần chỉnh driver settings mà property của phiên bản Boot đang dùng không diễn đạt được, hãy cân nhắc **`MongoClientSettingsBuilderCustomizer`** trước khi thay toàn bộ client.

Ví dụ cho Spring Boot 3.x:

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.boot.autoconfigure.mongo.MongoClientSettingsBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MongoClientTuning {
    @Bean
    MongoClientSettingsBuilderCustomizer selectionTimeout() {
        return settings -> settings.applyToClusterSettings(
                cluster -> cluster.serverSelectionTimeout(3, TimeUnit.SECONDS));
    }
}
~~~

Ví dụ giới hạn thời gian **chọn server** của driver; đó không phải timeout tổng cho mọi truy vấn. Giá trị `3` giây chỉ có tính minh họa. Customizer cho phép Boot vẫn sử dụng cơ chế tạo và quản lý client trong phạm vi phiên bản hỗ trợ.

### 5.2. Khi nào tự tạo MongoTemplate hoặc factory?

Ví dụ bạn cần nhiều database với quyền truy cập, converter hoặc cấu hình khác nhau. Khi đó có thể cần:

1. Định nghĩa các `MongoClient` hoặc `MongoDatabaseFactory` cần thiết.
2. Định nghĩa `MongoTemplate` theo từng database với tên rõ ràng.
3. Gắn nhóm repository với template cụ thể qua `@EnableMongoRepositories(mongoTemplateRef = "...")`.
4. Dùng `@Qualifier` hoặc `@Primary` có chủ đích; kiểm tra cả transaction manager và index management.

Ví dụ ý tưởng ánh xạ repository:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableMongoRepositories(
        basePackages = "com.example.catalog.primaryrepo",
        mongoTemplateRef = "catalogMongoTemplate")
public class CatalogRepositoryBinding {
}
~~~

Đoạn code này **chỉ minh họa ràng buộc**; muốn chạy phải định nghĩa bean có tên `catalogMongoTemplate` và cấu hình package phù hợp. Đối với ứng dụng chỉ có một database, dùng mặc định thường dễ bảo trì và kiểm thử hơn.

## 6. Auto-configuration và ứng dụng reactive

Ứng dụng truy cập MongoDB bất đồng bộ có thể dùng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb-reactive'
}
~~~

Với thư viện reactive trên classpath và điều kiện phù hợp, Boot 3.x có thể cấu hình:

- MongoDB Reactive Streams `MongoClient` (khác kiểu với client đồng bộ);
- `ReactiveMongoDatabaseFactory` và `ReactiveMongoTemplate`/`ReactiveMongoOperations`;
- implementation của `ReactiveMongoRepository`.

Ví dụ repository reactive:

~~~java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveBookRepository
        extends ReactiveMongoRepository<Book, String> {
    Flux<Book> findByAuthor(String author);
}
~~~

Ví dụ trên giả sử `Book` thuộc package được import đúng; với dự án thật nên tổ chức entity và package rõ ràng như ví dụ đồng bộ ở mục 3.

**Spring WebFlux không tự biến một `MongoTemplate` đồng bộ thành non-blocking.** Phải dùng driver và API reactive nhất quán trên đường xử lý. Nếu ứng dụng chứa cả hai starter, cả stack sync và reactive có thể cùng xuất hiện tùy điều kiện; cần chọn rõ loại repository/template được sử dụng và tránh inject nhầm kiểu client.

Không dùng `block()` tùy tiện trên luồng xử lý reactive. Nếu phải tích hợp hệ thống đồng bộ, cần thiết kế ranh giới bất đồng bộ và lịch thực thi phù hợp.

## 7. Transaction, index và auditing có được tạo tự động không?

**Kết nối và mapping** được Boot hỗ trợ nhiều hơn **chính sách nghiệp vụ**. Những khả năng sau thường yêu cầu cấu hình hay quyết định riêng:

### 7.1. Transaction nhiều document

MongoDB hỗ trợ transaction với topology phù hợp (replica set hoặc sharded cluster). Ứng dụng đồng bộ sử dụng `MongoTransactionManager` nếu muốn Spring quản lý session/transaction cho các thao tác tham gia:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {
    @Bean
    MongoTransactionManager mongoTransactionManager(MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

Sau đó `@Transactional` có thể được sử dụng ở ranh giới phương thức service thích hợp, với điều kiện transaction management đã được bật và mọi thao tác cần tham gia cùng hạ tầng/session. Không mặc định rằng chỉ thêm MongoDB starter là Boot đã tạo sẵn transaction manager nhiều document.

Trong hệ reactive, dùng `ReactiveMongoTransactionManager` và cách compose publisher tham gia transaction phù hợp; không trộn transaction manager đồng bộ và reactive.

### 7.2. Index

`@Indexed` và `@CompoundIndex` mô tả index trên model, nhưng việc **tự động tạo index** không được mặc định bật trong các phiên bản Spring Data MongoDB hiện đại. Với Boot 3.x có cấu hình liên quan `spring.data.mongodb.auto-index-creation`; chính sách production nên xác định rõ việc quản lý index/migration, quyền tạo index và thời điểm triển khai.

Index phải bám theo workload: bộ lọc, sort, cardinality, tần suất ghi, uniqueness và execution plan. Không bật auto-index chỉ để kỳ vọng mọi truy vấn chậm được sửa tự động.

### 7.3. Auditing và callback

Các trường như `createdAt`, `lastModifiedAt`, `createdBy` và `lastModifiedBy` cần cấu hình auditing thích hợp (ví dụ `@EnableMongoAuditing` và auditor provider nếu cần thông tin người dùng). Không có lý do để giả định chúng tự hoạt động chỉ vì dependency MongoDB có mặt.

Các entity callbacks/converters do ứng dụng định nghĩa cũng phải được đăng ký đúng và được sử dụng qua đường Spring Data mapping phù hợp. Truy cập collection bằng driver BSON trực tiếp không tự động áp dụng những callback này.

## 8. Cấu hình theo môi trường và bảo mật

Auto-configuration đọc property qua Spring `Environment`. Cấu hình có thể đến từ YAML/properties, environment variables, command-line arguments, profile hoặc cơ chế quản lý secret của hạ tầng. Thứ tự ưu tiên chịu quy tắc externalized configuration của Boot.

Ví dụ:

~~~yaml
# application.yml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

~~~yaml
# application-local.yml (chỉ dùng khi profile local được kích hoạt)
spring:
  data:
    mongodb:
      uri: mongodb://localhost:27017/book_catalog
~~~

Khi profile `local` được kích hoạt, profile-specific property có thể ghi đè giá trị cơ bản, nhưng vẫn có các nguồn cấu hình có độ ưu tiên cao hơn. Không lưu URI production có mật khẩu vào file profile trong repository.

Cần kiểm soát:

- **Người dùng MongoDB và quyền**: cấp quyền tối thiểu theo database/collection và thao tác cần thiết.
- **TLS và xác thực**: cấu hình theo topology, không vô hiệu hóa xác thực/chứng chỉ để “sửa” lỗi kết nối production.
- **Timeout và pool**: đặt theo nhu cầu và số instance ứng dụng, tránh tổng số kết nối vượt sức chứa MongoDB.
- **Logging**: tránh log connection string có credential, document chứa dữ liệu nhạy cảm hoặc toàn bộ query parameter.
- **Health/readiness**: tách trạng thái ứng dụng đã khởi động khỏi trạng thái backend dữ liệu sẵn sàng cho thao tác cần thiết.

## 9. Kiểm tra auto-configuration đang thực sự làm gì

### 9.1. Condition evaluation report

Khi không tìm thấy bean hoặc không rõ vì sao một bean được tạo, chạy ứng dụng Boot 3.x với `--debug` để hiển thị **conditions evaluation report** hoặc bật log cho lớp báo cáo điều kiện trong môi trường phù hợp.

Các mục cần tìm:

- Auto-configuration MongoDB nào **matched**, và điều kiện nào đã thỏa.
- Mục nào **did not match** vì thiếu class hoặc đã có bean tùy biến.
- Có đang bật configuration cho reactive hay imperative không.
- Repository package có nằm dưới vùng quét hay không.

Nếu sử dụng Spring Boot Actuator, endpoint `conditions` có thể hỗ trợ chẩn đoán khi được cấu hình và cho phép truy cập. Chỉ bật endpoint cần thiết và bảo vệ thông tin nội bộ.

### 9.2. Thử một thao tác thật

Khi startup thành công nhưng request báo lỗi, hãy kiểm tra thao tác và kết nối thực tế:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Component;

@Component
public class MongoPing {
    private final MongoTemplate mongoTemplate;

    public MongoPing(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public void verifyConnection() {
        mongoTemplate.executeCommand(new Document("ping", 1));
    }
}
~~~

Đoạn này chỉ minh họa lệnh ping có chủ đích; không nên gọi mỗi request. Ping thành công xác nhận một phần khả năng kết nối, **không** bảo đảm quyền truy vấn/ghi tất cả collection. Chẩn đoán lỗi phải gắn với thao tác nghiệp vụ thực tế.

### 9.3. Các sự cố thường gặp

| Triệu chứng | Nguyên nhân nên kiểm tra | Hướng xử lý |
|---|---|---|
`NoSuchBeanDefinitionException: MongoTemplate` | Thiếu starter sync, bean tùy biến, auto-config bị loại trừ hoặc dùng stack reactive | Kiểm tra dependency và condition report; inject đúng API |
`No qualifying bean of type BookRepository` | Repository nằm ngoài vùng quét hoặc auto-config repository không hoạt động | Kiểm tra package gốc và `@EnableMongoRepositories` nếu cần |
Không kết nối được/`server selection timeout` | Host/port sai, firewall, DNS, TLS, MongoDB chưa sẵn sàng | Kiểm tra URI hiệu lực, topology và mạng |
Lỗi authentication/authorization | Credential sai, `authSource`/cơ chế xác thực không đúng hoặc thiếu quyền | Kiểm tra cấu hình xác thực và quyền người dùng |
Có bean nhưng truy vấn vào database sai | Database trong URI/property, tên collection, nhiều factory/template | In cấu hình phi bí mật, kiểm tra bean được inject và mapping |
Chương trình WebFlux bị chặn thread | Dùng driver/`MongoTemplate` đồng bộ trong đường xử lý reactive | Chuyển sang stack reactive hoặc thiết kế ranh giới phù hợp |
`@Transactional` không tạo hiệu quả mong đợi | Chưa có transaction manager, topology không hỗ trợ, gọi ngoài proxy hoặc session | Kiểm tra transaction manager, topology và transaction boundary |
Truy vấn chậm dù cấu hình đúng | Index/query plan, số document scan, pool quá tải hoặc payload lớn | Dùng `explain`, metrics và kiểm tra kết quả truy vấn thực |

## 10. Kiểm thử cấu hình và tích hợp

Trong Spring Boot 3.x, `@DataMongoTest` là test slice tập trung vào Spring Data MongoDB, có thể giúp nạp repository và phần mapping cần thiết mà không kéo toàn bộ service/controller. Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.example.catalog.data.Book;
import com.example.catalog.data.BookRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;

@DataMongoTest
class BookRepositoryTest {
    @Autowired
    BookRepository books;

    @Test
    void savesAndQueriesByAuthor() {
        Book saved = books.save(new Book("MongoDB cơ bản", "An"));
        assertThat(saved.getId()).isNotBlank();
        assertThat(books.findByAuthor("An"))
                .extracting(Book::getTitle)
                .contains("MongoDB cơ bản");
    }
}
~~~

Test này cần **một MongoDB thực sự sẵn sàng cho môi trường kiểm thử**; `@DataMongoTest` không tự tạo server MongoDB. Có thể dùng Testcontainers để khởi động MongoDB và cung cấp URI động qua cơ chế phù hợp với phiên bản Spring Boot đang dùng.

Nếu bài kiểm thử cần transaction hoặc change streams, môi trường MongoDB phải hỗ trợ topology tương ứng. Nên dùng dữ liệu tách biệt giữa các test để không phụ thuộc trạng thái ngoài ý muốn.

Kiểm thử ở nhiều cấp độ:

1. **Configuration test**: xác minh các bean đồng bộ hoặc reactive thực sự tồn tại; bean tùy chỉnh đã back-off như dự kiến.
2. **Repository/template integration test**: xác minh mapping, truy vấn, sort, index cần thiết và các quy tắc cập nhật trên server thật.
3. **Transaction test**: đo hành vi commit/rollback trên topology hỗ trợ; kiểm tra xử lý lỗi và retry.
4. **Hiệu năng**: dùng dữ liệu có quy mô tương ứng, theo dõi query plan, độ trễ, connection pool và số lần gọi mạng. Chỉ đổi mức abstraction sau khi có bằng chứng.

## 11. Bài tập vận dụng

**Bài 1 — Phân tích condition report.** Tạo ứng dụng Boot 3.x với starter MongoDB sync và URI tới MongoDB local. Chạy với `--debug`, tìm các cấu hình MongoDB được chọn và chỉ ra bean nào thuộc driver, Spring Data mapping và repositories. Sau đó thử khai báo một bean client tùy biến trong nhánh thử nghiệm để quan sát thay đổi về condition report; không giữ cấu hình thừa trong ứng dụng chính.

**Bài 2 — Repository và template dùng chung hạ tầng.** Tạo entity `Book`, một query method ở `MongoRepository` và truy vấn bằng `MongoTemplate`. Ghi cùng một document bằng repository rồi đọc bằng template. Giải thích vai trò `MongoMappingContext` và `MappingMongoConverter`.

**Bài 3 — Cấu hình môi trường.** Chạy cùng một ứng dụng với URI local và một URI môi trường kiểm thử được cấp qua environment variable. Xác minh database đích, kết nối và quyền của người dùng; không in credential ra log.

**Bài 4 — Xử lý lỗi.** Xóa cấu hình hoặc đặt nhầm port trong môi trường thử nghiệm, quan sát sự khác biệt giữa lỗi tạo ApplicationContext và lỗi chọn server khi chạy query. Dùng condition report và thông điệp driver để xác định tầng xảy ra lỗi.

**Bài 5 — Reactive và transaction.** So sánh kiểu của `MongoTemplate`/`ReactiveMongoTemplate`, `MongoRepository`/`ReactiveMongoRepository`. Trình bày vì sao transaction nhiều document và non-blocking access cần hạ tầng riêng ngoài thao tác tự động tạo bean.

## 12. Những điều cần ghi nhớ

**Auto-configuration của Spring Boot** giúp kết nối và ánh xạ MongoDB bằng cách tạo stack mặc định **khi classpath, property và các điều kiện bean phù hợp**. Với starter sync, ứng dụng thường có sẵn `MongoClient`, `MongoDatabaseFactory`, `MongoTemplate` và repository; với starter reactive có hệ tương ứng dành cho publisher bất đồng bộ.

Hãy bắt đầu từ **starter + URI + entity/repository**. Khi cần thay đổi, ưu tiên property và customizer rồi mới thay bean mặc định. Các yêu cầu về **transaction nhiều document, index, auditing, nhiều database, bảo mật, hiệu năng và chính sách truy vấn** vẫn cần thiết kế và kiểm thử cụ thể. Công cụ quan trọng nhất để hiểu bean nào đã được Boot tạo là **condition evaluation report**, kết hợp với kiểm thử truy cập MongoDB thật.
