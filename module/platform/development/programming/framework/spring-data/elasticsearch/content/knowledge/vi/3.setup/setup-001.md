# Tạo ứng dụng Spring Boot với Spring Data Elasticsearch

Spring Data Elasticsearch giúp ứng dụng Spring Boot lưu trữ và truy vấn dữ liệu trên Elasticsearch thông qua các abstraction quen thuộc của Spring Data. Thay vì tự tạo HTTP request cho từng thao tác, ứng dụng có thể khai báo entity bằng annotation, định nghĩa repository và sử dụng các phương thức như `save`, `findById`, `findAll` hoặc các query method.

Trong bài này, chúng ta xây dựng một ứng dụng quản lý sản phẩm đơn giản. Ứng dụng kết nối tới một Elasticsearch node, lưu thông tin sản phẩm, tìm sản phẩm theo danh mục và cung cấp các endpoint REST để thử nghiệm. Qua ví dụ này, bạn sẽ thấy các thành phần cần có trong một ứng dụng Spring Boot dùng Spring Data Elasticsearch và cách chúng phối hợp với nhau.

## 1. Kiến trúc ứng dụng

Ứng dụng mẫu có các thành phần:

| Thành phần | Vai trò |
|---|---|
| Spring Boot | Khởi động ứng dụng, quản lý cấu hình và tự động cấu hình các thành phần tích hợp |
| Spring Data Elasticsearch | Cung cấp mapping, repository và API thao tác với Elasticsearch |
| Elasticsearch | Lưu trữ, lập chỉ mục và tìm kiếm tài liệu |
| Product | Entity biểu diễn một sản phẩm được lưu trong index `products` |
| ProductRepository | Repository cung cấp các thao tác đọc và ghi sản phẩm |
| ProductController | REST API nhận request và gọi repository |

Luồng xử lý khi tạo sản phẩm:

```text
HTTP request
     |
     v
ProductController
     |
     v
ProductRepository
     |
     v
Spring Data Elasticsearch
     |
     v
Elasticsearch Java Client
     |
     v
Elasticsearch cluster
     |
     v
Index: products
```

Spring Data Elasticsearch sử dụng Elasticsearch Java Client để giao tiếp với cluster. Repository che giấu phần lớn chi tiết gửi request, chuyển đổi entity và ánh xạ kết quả trả về.

## 2. Chuẩn bị môi trường

Bạn cần có:

- JDK phù hợp với phiên bản Spring Boot được chọn. Với các dự án Spring Boot 3.x, Java 17 trở lên là lựa chọn cơ bản.
- Maven hoặc Gradle, hoặc dùng Maven/Gradle Wrapper được tạo cùng dự án.
- Docker Desktop hoặc Docker Engine để chạy Elasticsearch cục bộ; có thể thay bằng một Elasticsearch cluster đã được cấp quyền truy cập.
- IDE hỗ trợ Java như IntelliJ IDEA, Eclipse hoặc Visual Studio Code.

Spring Boot và Spring Data Elasticsearch có các dòng phiên bản tương ứng. Hãy để Spring Boot quản lý phiên bản dependency thông qua dependency management/BOM của nó. Không nên tùy tiện ghi đè phiên bản `spring-data-elasticsearch` hoặc Elasticsearch Java Client bằng một phiên bản khác với dependency train đang dùng. Khi chọn phiên bản Elasticsearch server, hãy kiểm tra bảng tương thích của Spring Data Elasticsearch và client.

Ví dụ mã trong bài sử dụng các API phổ biến của Spring Boot 3.x và Spring Data Elasticsearch 5.x. Nếu dự án sử dụng một major version khác, hãy đối chiếu tài liệu của đúng phiên bản trước khi áp dụng cấu hình hoặc API cụ thể.

## 3. Tạo dự án Spring Boot

Mở Spring Initializr tại `https://start.spring.io/` và tạo một dự án với các lựa chọn cơ bản:

| Thuộc tính | Giá trị gợi ý |
|---|---|
| Project | Maven hoặc Gradle |
| Language | Java |
| Spring Boot | Một phiên bản đang được hỗ trợ |
| Group | `com.example` |
| Artifact | `catalog` |
| Name | `catalog` |
| Packaging | Jar |
| Java | Phiên bản tương thích với Spring Boot đã chọn |

Thêm hai dependency:

- **Spring Web**: tạo REST controller và nhận HTTP request.
- **Spring Data Elasticsearch**: kết nối Elasticsearch, ánh xạ entity và cung cấp repository.

Tải project, giải nén và mở thư mục dự án trong IDE. Spring Initializr tạo sẵn lớp ứng dụng, cấu hình build và Maven/Gradle Wrapper.

### 3.1. Dependency với Maven

Nếu đã tạo project bằng Spring Initializr, hai dependency tương ứng sẽ có trong `pom.xml`. Phần khai báo nằm trong thẻ `dependencies`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-elasticsearch</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Các dependency starter được quản lý phiên bản bởi Spring Boot parent hoặc BOM. Nếu tự tạo `pom.xml`, cần khai báo parent/BOM và Spring Boot Maven Plugin theo cấu hình do Initializr sinh ra; không sao chép riêng thẻ `dependencies` vào một project chưa có dependency management rồi kỳ vọng Maven tự chọn phiên bản tương thích.

### 3.2. Dependency với Gradle

Với Gradle, phần dependency tương ứng có dạng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-elasticsearch'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Project do Initializr tạo đã có plugin Spring Boot và cơ chế quản lý dependency phù hợp. Giữ nguyên cấu hình đó khi thêm starter.

## 4. Khởi chạy Elasticsearch cho môi trường phát triển

Ứng dụng Spring Boot cần một Elasticsearch endpoint đang hoạt động. Nếu chưa có cluster, có thể chạy một node cục bộ bằng Docker Compose.

Tạo file `compose.yaml` ở thư mục gốc của project:

```yaml
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.15.0
    container_name: catalog-elasticsearch
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - ES_JAVA_OPTS=-Xms1g -Xmx1g
    ports:
      - "9200:9200"
    volumes:
      - elasticsearch-data:/usr/share/elasticsearch/data

volumes:
  elasticsearch-data:
```

> **Lưu ý:** Cấu hình trên dành cho máy phát triển cục bộ. Nó tắt security và công khai cổng Elasticsearch trên máy host để đơn giản hóa bài thực hành. Không sử dụng cấu hình này cho môi trường production hoặc mạng có người khác truy cập. Khi dùng cluster thật, bật xác thực và TLS, quản lý credential bằng secret/environment variables và xác minh chứng chỉ máy chủ.

Khởi động container:

```bash
docker compose up -d
```

Kiểm tra node đã sẵn sàng bằng cách gửi request tới `http://localhost:9200`:

```bash
curl http://localhost:9200
```

Nếu node hoạt động, Elasticsearch trả về JSON chứa thông tin node, cluster, phiên bản và tagline. Nếu request chưa thành công ngay sau khi chạy Compose, kiểm tra trạng thái container và log vì Elasticsearch cần thời gian khởi động.

Tên image và phiên bản server trong Compose là ví dụ cố định để tái lập bài thực hành. Khi thay đổi phiên bản Spring Boot/Spring Data Elasticsearch, hãy chọn phiên bản Elasticsearch tương thích theo tài liệu của release train đang dùng.

## 5. Cấu hình kết nối trong Spring Boot

Tạo hoặc cập nhật file `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: catalog
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS:http://localhost:9200}
```

Thuộc tính `spring.elasticsearch.uris` xác định địa chỉ Elasticsearch mà ứng dụng kết nối tới. Cú pháp `${ELASTICSEARCH_URIS:http://localhost:9200}` có nghĩa là Spring Boot đọc biến môi trường `ELASTICSEARCH_URIS`; nếu biến này chưa được đặt thì dùng địa chỉ mặc định ở phía sau dấu `:`.

Khi chạy ứng dụng trên máy host cùng Docker Compose ở trên, `localhost:9200` là địa chỉ phù hợp. Nếu ứng dụng cũng chạy trong Docker Compose, `localhost` bên trong container ứng dụng trỏ về chính container ứng dụng. Khi đó, dùng tên service `elasticsearch` làm hostname, ví dụ `http://elasticsearch:9200`, và đặt hai service trên cùng Docker network.

Với cluster có bảo mật, cấu hình username/password và TLS theo phiên bản Spring Boot đang dùng. Ví dụ phần credential có thể được đưa vào qua biến môi trường:

```yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS}
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
```

Đây chỉ là phần khai báo credential; endpoint HTTPS còn phải được cấu hình trust cho CA/chứng chỉ của cluster theo cơ chế SSL được phiên bản Spring Boot hỗ trợ. Không đưa mật khẩu thật vào source control và không tắt xác minh TLS để né lỗi chứng chỉ.

## 6. Lớp khởi động ứng dụng

Spring Initializr tạo lớp main có annotation `@SpringBootApplication`. Ví dụ:

```java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

`@SpringBootApplication` kết hợp cấu hình, auto-configuration và component scanning. Spring Boot nhận biết starter Elasticsearch trên classpath, đọc các thuộc tính `spring.elasticsearch.*` và tự cấu hình các thành phần client cần thiết.

Đặt các package `domain`, `repository` và `controller` bên dưới package `com.example.catalog` để component scan và repository scan mặc định tìm thấy chúng. Chỉ cần dùng `@EnableElasticsearchRepositories` khi muốn cấu hình rõ package chứa repository hoặc repository nằm ngoài phạm vi scan mặc định.

## 7. Tạo entity Product

Entity là lớp Java biểu diễn tài liệu được lưu trong Elasticsearch. Tạo file `src/main/java/com/example/catalog/domain/Product.java`:

```java
package com.example.catalog.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products", createIndex = true)
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Long)
    private Long priceInCents;

    public Product() {
    }

    public Product(String id, String name, String category, Long priceInCents) {
        this.id = id;
        this.name = name;
        this.category = category;
        this.priceInCents = priceInCents;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }

    public Long getPriceInCents() {
        return priceInCents;
    }

    public void setPriceInCents(Long priceInCents) {
        this.priceInCents = priceInCents;
    }
}
```

Các annotation quan trọng:

- `@Document(indexName = "products")` liên kết entity với index `products`.
- `createIndex = true` yêu cầu Spring Data tạo index và mapping khi index chưa tồn tại theo cơ chế khởi tạo repository.
- `@Id` đánh dấu thuộc tính dùng làm document ID trong Elasticsearch.
- `@Field(type = FieldType.Text)` khai báo field văn bản được phân tích thành token.
- `@Field(type = FieldType.Keyword)` khai báo field chuỗi cần lưu như một giá trị để lọc hoặc so khớp chính xác.
- `@Field(type = FieldType.Long)` ánh xạ giá trị số nguyên dài.

Trong ví dụ, giá sản phẩm được lưu dưới dạng số nguyên `priceInCents` để tránh sai số nhị phân thường gặp khi dùng kiểu dấu phẩy động cho phép tính tiền. Ứng dụng có thể định dạng số tiền ở lớp API hoặc giao diện.

Khi index `products` chưa tồn tại, Spring Data Elasticsearch có thể tạo index và mapping dựa trên metadata của entity. Nếu index đã tồn tại, annotation không tự ghi đè mapping hiện tại. Khi thay đổi kiểu field hoặc analyzer, cần lập kế hoạch tạo index mới và reindex dữ liệu thay vì chỉ sửa annotation rồi khởi động lại ứng dụng.

## 8. Tạo ProductRepository

Tạo file `src/main/java/com/example/catalog/repository/ProductRepository.java`:

```java
package com.example.catalog.repository;

import java.util.List;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import com.example.catalog.domain.Product;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);
}
```

`ElasticsearchRepository<Product, String>` là repository dành cho entity `Product`, với kiểu ID là `String`. Spring Data cung cấp các thao tác cơ bản như:

| Phương thức | Công dụng |
|---|---|
| `save(product)` | Thêm mới hoặc cập nhật document theo ID |
| `findById(id)` | Tìm document theo ID |
| `findAll()` | Lấy các document |
| `existsById(id)` | Kiểm tra document theo ID có tồn tại không |
| `deleteById(id)` | Xóa document theo ID |
| `count()` | Đếm document theo repository |

Phương thức `findByCategory` là query method được suy ra từ tên phương thức. Vì `category` được mapping là `keyword`, phép so khớp theo giá trị danh mục phù hợp với kiểu dữ liệu này. Nếu cần tìm kiếm toàn văn theo tên sản phẩm, hãy chọn query như `match` trên field `name` thay vì mặc định coi một phương thức tìm kiếm chuỗi bất kỳ là full-text search.

Repository được Spring Data tự phát hiện nhờ package scan. Không cần viết lớp triển khai cho các phương thức repository thông thường.

## 9. Tạo REST controller

Tạo file `src/main/java/com/example/catalog/controller/ProductController.java`:

```java
package com.example.catalog.controller;

import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.example.catalog.domain.Product;
import com.example.catalog.repository.ProductRepository;

@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductRepository productRepository;

    public ProductController(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @PostMapping
    public Product create(@RequestBody Product product) {
        return productRepository.save(product);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Product> findById(@PathVariable String id) {
        return ResponseEntity.of(productRepository.findById(id));
    }

    @GetMapping
    public Iterable<Product> findAll() {
        return productRepository.findAll();
    }

    @GetMapping("/by-category/{category}")
    public List<Product> findByCategory(@PathVariable String category) {
        return productRepository.findByCategory(category);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> deleteById(@PathVariable String id) {
        if (!productRepository.existsById(id)) {
            return ResponseEntity.notFound().build();
        }

        productRepository.deleteById(id);
        return ResponseEntity.noContent().build();
    }
}
```

Constructor injection giúp controller nhận repository do Spring quản lý. Controller chỉ xử lý HTTP request và chuyển tiếp thao tác tới repository; Spring Data đảm nhiệm việc chuyển entity thành document và gửi thao tác tới Elasticsearch.

Đây là controller minh họa để kiểm tra tích hợp. Trong ứng dụng thực tế, nên bổ sung DTO cho request/response, kiểm tra dữ liệu đầu vào, xử lý lỗi tập trung và phân trang cho endpoint liệt kê. Không nên trả trực tiếp entity nội bộ nếu API cần một hợp đồng dữ liệu ổn định.

## 10. Cấu trúc project sau khi hoàn thành

Một cấu trúc thư mục đơn giản có thể như sau:

```text
catalog/
├── compose.yaml
├── pom.xml
├── mvnw
├── mvnw.cmd
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/catalog/
    │   │       ├── CatalogApplication.java
    │   │       ├── controller/
    │   │       │   └── ProductController.java
    │   │       ├── domain/
    │   │       │   └── Product.java
    │   │       └── repository/
    │   │           └── ProductRepository.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/
```

Nếu dùng Gradle, project sẽ có `build.gradle` hoặc `build.gradle.kts` cùng Gradle Wrapper thay cho `pom.xml` và Maven Wrapper.

## 11. Chạy và kiểm tra ứng dụng

Trước tiên, khởi động Elasticsearch:

```bash
docker compose up -d
```

Xác nhận `http://localhost:9200` trả về thông tin node. Sau đó, tại thư mục project, chạy Spring Boot.

Với Maven trên macOS/Linux:

```bash
./mvnw spring-boot:run
```

Với Maven trên Windows:

```powershell
.\mvnw.cmd spring-boot:run
```

Với Gradle, dùng `./gradlew bootRun` trên macOS/Linux hoặc `.\gradlew.bat bootRun` trên Windows.

Khi ứng dụng khởi động thành công, Spring Boot lắng nghe HTTP trên cổng mặc định `8080`. Spring Data Elasticsearch kết nối tới endpoint được khai báo trong `application.yml`.

### 11.1. Tạo một sản phẩm

Gửi request sau bằng Postman, curl hoặc file HTTP request trong IDE:

```http
POST http://localhost:8080/products
Content-Type: application/json

{
  "id": "p-100",
  "name": "Mechanical Keyboard",
  "category": "keyboard",
  "priceInCents": 1299000
}
```

Controller nhận JSON, chuyển thành `Product` rồi gọi `productRepository.save(product)`. Spring Data chuyển entity thành document và ghi vào index `products`.

### 11.2. Đọc sản phẩm theo ID

```http
GET http://localhost:8080/products/p-100
```

Repository gọi Elasticsearch để tìm document theo ID. Nếu tìm thấy, API trả về sản phẩm; nếu không, controller trả HTTP `404 Not Found`.

### 11.3. Liệt kê sản phẩm

```http
GET http://localhost:8080/products
```

Endpoint này minh họa `findAll()`. Trong môi trường thực tế, nên dùng `Pageable` và giới hạn kích thước trang để tránh tải quá nhiều document cùng lúc.

### 11.4. Tìm theo danh mục

```http
GET http://localhost:8080/products/by-category/keyboard
```

Spring Data thực thi query method `findByCategory` trên field `category`. Do field được khai báo `keyword`, giá trị `keyboard` được so khớp như một giá trị danh mục.

### 11.5. Xóa sản phẩm

```http
DELETE http://localhost:8080/products/p-100
```

Nếu document tồn tại, repository xóa document theo ID và controller trả HTTP `204 No Content`. Nếu ID không tồn tại, controller trả `404 Not Found`.

Elasticsearch là hệ thống tìm kiếm gần thời gian thực. Sau khi ghi hoặc xóa document, thay đổi có thể chưa xuất hiện ngay trong kết quả search cho tới lần refresh tiếp theo. Vì vậy, khi kiểm thử thao tác ghi rồi tìm kiếm ngay, hãy tính đến độ trễ refresh thay vì kết luận ngay rằng repository đã ghi thất bại.

## 12. Spring Boot tự cấu hình những gì?

Khi starter `spring-boot-starter-data-elasticsearch` có trên classpath và cấu hình kết nối hợp lệ, Spring Boot có thể tự cấu hình các thành phần cần thiết để Spring Data làm việc với Elasticsearch. Tùy phiên bản, những thành phần thường gặp gồm:

- Elasticsearch Java Client được cấu hình từ các thuộc tính kết nối.
- `ElasticsearchOperations` để thực hiện các thao tác cấp cao trên entity và query.
- Hạ tầng repository để tạo bean cho các interface kế thừa `ElasticsearchRepository`.
- Chuyển đổi giữa đối tượng Java và document Elasticsearch dựa trên mapping metadata.

Nhờ auto-configuration, ứng dụng cơ bản không cần tự tạo HTTP client hoặc tự viết lớp repository triển khai. Khi cần tùy chỉnh sâu hơn, có thể khai báo bean cấu hình client hoặc sử dụng `ElasticsearchOperations` theo API của phiên bản đang dùng. Chỉ nên thay thế bean auto-configured khi có yêu cầu cụ thể và đã hiểu ảnh hưởng tới các thành phần phụ thuộc.

## 13. Khi nào cần dùng ElasticsearchOperations?

Repository phù hợp với thao tác CRUD và query method phổ biến. Khi truy vấn phức tạp hơn, ví dụ kết hợp nhiều điều kiện, sort, aggregation, highlight hoặc cấu hình truy vấn chuyên biệt, có thể dùng `ElasticsearchOperations` cùng API query của Spring Data Elasticsearch.

Ví dụ dưới đây chỉ minh họa cách inject abstraction:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
```

Từ `ElasticsearchOperations`, service có thể dùng các API như `save`, `get`, `search` và `indexOps`. Khi tạo query, API cụ thể có thể khác giữa các release train; hãy dùng `NativeQuery` hoặc query abstraction được tài liệu phiên bản Spring Data Elasticsearch đang dùng hướng dẫn. Việc chọn query cần dựa trên semantics của Elasticsearch, chẳng hạn `match` cho full-text và `term` cho giá trị chính xác.

## 14. Kiểm tra index và mapping trong Elasticsearch

Sau khi ứng dụng khởi tạo entity/repository, kiểm tra index:

```http
GET http://localhost:9200/_cat/indices?v
```

Kiểm tra mapping của `products`:

```http
GET http://localhost:9200/products/_mapping
```

Mapping dự kiến thể hiện `name` là `text`, `category` là `keyword` và `priceInCents` là `long`. Mapping thực tế còn phụ thuộc phiên bản Spring Data, metadata entity và các cấu hình index đang có.

Kiểm tra document đã được ghi:

```http
GET http://localhost:9200/products/_search
```

Những request này giúp phân biệt lỗi ở tầng ứng dụng với lỗi ở tầng index. Ví dụ, nếu API lưu thành công nhưng document không xuất hiện ngay trong `_search`, hãy kiểm tra refresh và trạng thái index. Nếu mapping khác mong đợi, kiểm tra xem index đã tồn tại từ trước hay chưa.

## 15. Các lỗi thường gặp khi tích hợp

### Không kết nối được tới Elasticsearch

Các nguyên nhân thường gặp là Elasticsearch chưa khởi động, sai URI, sai port hoặc ứng dụng chạy trong container nhưng cấu hình hostname là `localhost`. Hãy kiểm tra container, log và gọi trực tiếp endpoint Elasticsearch từ đúng môi trường mạng của ứng dụng.

### Lỗi xác thực hoặc TLS

Cluster có security có thể yêu cầu username/password và kết nối HTTPS với CA đáng tin cậy. Credential sai gây lỗi xác thực; thiếu CA hoặc hostname không khớp chứng chỉ gây lỗi TLS. Kiểm tra cấu hình bảo mật của cluster và cách Spring Boot phiên bản đang dùng nạp SSL trust material.

### Repository không được tìm thấy

Đảm bảo interface repository kế thừa `ElasticsearchRepository` và nằm trong phạm vi package scan của lớp `@SpringBootApplication`. Nếu package nằm ngoài phạm vi đó, cấu hình `@EnableElasticsearchRepositories` với `basePackages` thích hợp.

### Index hoặc mapping không như mong đợi

`@Document` và `@Field` mô tả mapping cho entity, nhưng index đã tồn tại sẽ không tự bị ghi đè mỗi khi ứng dụng khởi động. Kiểm tra `_mapping`, xác định dữ liệu có cần giữ hay không và dùng quy trình migration/reindex khi thay đổi cấu trúc field.

### Không tìm thấy document ngay sau khi save

Search của Elasticsearch có tính gần thời gian thực. Một lần ghi thành công chưa đảm bảo document xuất hiện ngay trong search. Kiểm tra response của thao tác ghi, trạng thái index và refresh cycle.

### Sai kiểu query so với kiểu field

Field `text` được phân tích thành token, còn field `keyword` giữ giá trị như một term. Dùng query phù hợp với mapping. Nếu cần vừa tìm toàn văn vừa lọc/sort chính xác, cân nhắc multi-fields thay vì ép một field phục vụ mọi mục đích.

## 16. Lưu ý khi đưa ứng dụng vào môi trường thực tế

Ứng dụng mẫu tập trung vào luồng tích hợp cơ bản. Khi phát triển thành hệ thống thực tế, cần bổ sung một số quyết định thiết kế:

- **Bảo mật kết nối:** dùng HTTPS, xác thực, phân quyền tối thiểu và quản lý secret ngoài mã nguồn.
- **Quản lý index:** tạo mapping có chủ đích, version hóa index và có quy trình reindex/alias khi thay đổi cấu trúc.
- **Xử lý lỗi:** phân biệt lỗi validation, lỗi nghiệp vụ, lỗi mạng và lỗi Elasticsearch; trả HTTP status phù hợp.
- **Phân trang:** tránh trả toàn bộ index qua một endpoint `findAll()` không giới hạn.
- **Kiểm thử:** dùng Elasticsearch thật trong integration test, chẳng hạn qua Testcontainers, để xác minh mapping và query thay vì chỉ mock repository.
- **Quan sát hệ thống:** ghi log có ngữ cảnh, theo dõi thời gian phản hồi, lỗi kết nối, dung lượng index và tình trạng cluster.
- **Tính nhất quán:** thiết kế xử lý retry và idempotency phù hợp khi ứng dụng gặp timeout hoặc gửi lại thao tác ghi.

Không nên xem Elasticsearch như một cơ sở dữ liệu quan hệ thay thế trực tiếp. Hãy xác định dữ liệu nào cần tìm kiếm, cách cập nhật và xóa dữ liệu, yêu cầu độ trễ và mức độ nhất quán trước khi quyết định dùng Elasticsearch làm nơi lưu trữ chính hay làm search index đồng bộ từ hệ thống khác.

## 17. Quy trình triển khai từ đầu đến cuối

Khi tạo một ứng dụng Spring Boot dùng Spring Data Elasticsearch, trình tự triển khai cơ bản là:

1. Tạo project Spring Boot với Spring Web và Spring Data Elasticsearch.
2. Chọn các phiên bản Spring Boot, Spring Data Elasticsearch và Elasticsearch server tương thích.
3. Khởi động hoặc chuẩn bị Elasticsearch cluster.
4. Khai báo endpoint và thông tin xác thực bằng cấu hình ngoài mã nguồn.
5. Tạo entity với `@Document`, `@Id` và `@Field` để mô tả mapping.
6. Tạo repository kế thừa `ElasticsearchRepository`.
7. Tạo service/controller để đưa thao tác lưu và tìm kiếm ra API của ứng dụng.
8. Chạy ứng dụng, kiểm tra kết nối, index, mapping và document thực tế.
9. Bổ sung validation, phân trang, bảo mật, kiểm thử tích hợp và quy trình migration trước khi triển khai production.

Với cấu trúc này, phần lớn thao tác dữ liệu thông thường được thực hiện qua repository. Khi yêu cầu tìm kiếm phức tạp hơn, ứng dụng có thể mở rộng bằng `ElasticsearchOperations` và Query DSL mà vẫn giữ nguyên cơ chế quản lý dependency, cấu hình và vòng đời ứng dụng của Spring Boot.
