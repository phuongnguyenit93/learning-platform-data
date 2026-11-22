# Thiết kế bất biến nghiệp vụ khi người dùng có thể ghi trực tiếp vào entity

Đây là phần áp dụng chủ đề Mô hình miền trong Spring Data REST: thiết kế entity sao cho các quy tắc nghiệp vụ vẫn được giữ khi client có thể ghi trực tiếp vào tài nguyên REST. Trong Spring Data REST, một repository được export có thể tạo sẵn các endpoint để client đọc, tạo, sửa và xóa entity. Cách này giúp xây dựng API nhanh, nhưng request HTTP có thể cập nhật thuộc tính của entity trực tiếp qua cơ chế binding của Spring Data REST. Nếu quy tắc nghiệp vụ chỉ nằm trong service hoặc controller mà endpoint ghi không gọi đến, client có thể tạo ra trạng thái dữ liệu không hợp lệ.

Bài này tập trung vào cách bảo vệ bất biến của mô hình miền khi entity được ghi trực tiếp qua REST. Ví dụ quản lý sản phẩm có số lượng tồn kho và số lượng đã giữ chỗ. Quy tắc cốt lõi là:

- Giá sản phẩm không được âm.
- Tồn kho và số lượng giữ chỗ không được âm.
- Số lượng giữ chỗ không được lớn hơn tồn kho.
- Mã SKU do hệ thống sinh và không cho client thay đổi.
- Việc giữ hoặc giải phóng hàng phải tuân theo hành vi nghiệp vụ của entity.

Ta sẽ dùng nhiều lớp bảo vệ: hành vi trong entity, kiểm tra toàn bộ trạng thái trước khi repository lưu, Bean Validation và ràng buộc cơ sở dữ liệu. Với các thao tác có quy trình hoặc chuyển trạng thái phức tạp, ta sẽ chuyển sang API command gọi application service thay vì cho phép client sửa trực tiếp các thuộc tính liên quan.

## 1. Bất biến nghiệp vụ là gì?

Bất biến nghiệp vụ (business invariant) là điều kiện phải luôn đúng đối với một đối tượng hoặc một aggregate trong suốt vòng đời của nó. Một thao tác chỉ hợp lệ khi trạng thái trước và sau thao tác vẫn tuân thủ các điều kiện đó.

Có thể chia thành một số nhóm:

| Loại bất biến | Ví dụ | Nơi kiểm tra phù hợp |
|---|---|---|
| Một thuộc tính | Giá không âm, tên không rỗng | Value object, setter có kiểm soát, Bean Validation |
| Nhiều thuộc tính | Số lượng giữ chỗ không vượt tồn kho | Entity hoặc aggregate sau khi nhận đủ dữ liệu |
| Bất biến định danh | SKU không được đổi sau khi tạo | Entity, cấu hình JSON và cơ sở dữ liệu |
| Quy tắc chuyển trạng thái | Đơn đã giao không thể quay về trạng thái nháp | Phương thức nghiệp vụ và application service |
| Quy tắc liên quan nhiều aggregate | Không thể bán vượt tổng tồn kho của nhiều kho | Application service, transaction và cơ chế đồng bộ phù hợp |

Ví dụ, nếu sản phẩm có 10 đơn vị tồn kho và 3 đơn vị đã được giữ chỗ, số lượng có thể bán là 7. Trạng thái giữ chỗ 12 trên tồn kho 10 là không hợp lệ, dù từng con số riêng lẻ đều không âm.

## 2. Vì sao ghi entity trực tiếp qua Spring Data REST cần chú ý?

Khi repository được export, Spring Data REST có thể cung cấp các endpoint như:

- GET collection và item để đọc entity.
- POST để tạo entity.
- PUT hoặc PATCH để cập nhật entity.
- DELETE để xóa entity.
- Các endpoint search tương ứng với phương thức truy vấn được export.

Ví dụ, với repository ProductRepository, client có thể gửi JSON đến /api/products hoặc /api/products/1. Spring Data REST chuyển request thành thao tác trên entity và repository.

Luồng ghi khái quát:

1. Client gửi JSON.
2. Spring Data REST và Jackson ánh xạ dữ liệu request lên các thuộc tính có thể ghi của entity.
3. Spring Data REST phát sự kiện trước khi tạo hoặc lưu.
4. Repository lưu entity; JPA và cơ sở dữ liệu thực hiện các kiểm tra ở tầng persistence.
5. Server trả representation của tài nguyên hoặc lỗi.

Điểm cần nhớ là một request cập nhật thuộc tính không nhất thiết gọi phương thức nghiệp vụ như reserve(), approve() hoặc ship(). Nếu quy tắc chỉ được viết trong những phương thức đó, client có thể đi vòng qua quy tắc bằng cách ghi trực tiếp các thuộc tính được export.

Ví dụ, entity có phương thức reserve(5) kiểm tra lượng hàng còn lại trước khi giữ chỗ. Nhưng nếu API cho phép client gửi trực tiếp reservedQuantity = 100, phương thức reserve() không được gọi. Vì vậy, cần kiểm tra trạng thái cuối cùng ở đường ghi REST và quyết định rõ thuộc tính nào được phép ghi trực tiếp.

## 3. Tạo ứng dụng mẫu

Ví dụ sử dụng Java 17, Spring Boot 3.5.x, Spring Data JPA, Spring Data REST, H2 và Bean Validation. Cấu trúc mã nguồn:

~~~text
src
├── main
│   ├── java/com/example/invariants
│   │   ├── InvariantsApplication.java
│   │   ├── Product.java
│   │   ├── ProductRepository.java
│   │   ├── ProductRestEventHandler.java
│   │   └── ProductDataInitializer.java
│   └── resources/application.properties
└── test
    └── java/com/example/invariants/ProductInvariantTest.java
~~~

### 3.1. Dependency Maven

Tạo dự án Maven với các dependency sau. Spring Boot parent quản lý phiên bản tương thích cho các starter:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-data-rest-invariants</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-rest</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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
~~~

Các dependency chính:

- Spring Data JPA cung cấp repository và tích hợp ORM.
- Spring Data REST export repository thành REST API.
- Spring Boot Starter Validation cung cấp Jakarta Bean Validation và implementation tương ứng.
- H2 cung cấp database trong bộ nhớ cho ví dụ.
- Spring Boot Starter Test cung cấp JUnit và AssertJ.

### 3.2. Lớp khởi động

~~~java
package com.example.invariants;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InvariantsApplication {

    public static void main(String[] args) {
        SpringApplication.run(InvariantsApplication.class, args);
    }
}
~~~

### 3.3. Entity Product chứa quy tắc miền

~~~java
package com.example.invariants;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;
import java.util.UUID;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Long id;

    @Column(nullable = false, unique = true, updatable = false, length = 40)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String sku;

    @NotBlank
    @Column(nullable = false, length = 120)
    private String name;

    @NotNull
    @DecimalMin("0.00")
    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal unitPrice;

    @Min(0)
    @Column(nullable = false)
    private int stockQuantity;

    @Min(0)
    @Column(nullable = false)
    private int reservedQuantity;

    protected Product() {
        // JPA cần constructor không tham số.
    }

    public Product(
            String name,
            BigDecimal unitPrice,
            int stockQuantity,
            int reservedQuantity) {
        this.name = name;
        this.unitPrice = unitPrice;
        this.stockQuantity = stockQuantity;
        this.reservedQuantity = reservedQuantity;
        validateInvariants();
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public void setUnitPrice(BigDecimal unitPrice) {
        this.unitPrice = unitPrice;
    }

    public int getStockQuantity() {
        return stockQuantity;
    }

    public void setStockQuantity(int stockQuantity) {
        this.stockQuantity = stockQuantity;
    }

    public int getReservedQuantity() {
        return reservedQuantity;
    }

    public void setReservedQuantity(int reservedQuantity) {
        this.reservedQuantity = reservedQuantity;
    }

    public int getAvailableQuantity() {
        return stockQuantity - reservedQuantity;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng giữ chỗ phải lớn hơn 0.");
        }
        if (reservedQuantity + quantity > stockQuantity) {
            throw new IllegalArgumentException("Không đủ hàng có thể bán.");
        }
        reservedQuantity += quantity;
    }

    public void release(int quantity) {
        if (quantity <= 0 || quantity > reservedQuantity) {
            throw new IllegalArgumentException("Số lượng giải phóng không hợp lệ.");
        }
        reservedQuantity -= quantity;
    }

    void validateInvariants() {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên sản phẩm không được để trống.");
        }
        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Giá sản phẩm phải lớn hơn hoặc bằng 0.");
        }
        if (stockQuantity < 0 || reservedQuantity < 0) {
            throw new IllegalArgumentException("Số lượng không được âm.");
        }
        if (reservedQuantity > stockQuantity) {
            throw new IllegalArgumentException(
                    "Số lượng giữ chỗ không được lớn hơn tồn kho.");
        }
    }

    @PrePersist
    private void beforeInsert() {
        validateInvariants();
        if (sku == null) {
            sku = "PRD-" + UUID.randomUUID();
        }
    }

    @PreUpdate
    private void beforeUpdate() {
        validateInvariants();
    }
}
~~~

Các điểm đáng chú ý:

- ID và SKU chỉ có getter, không có setter. Jackson được cấu hình READ_ONLY để biểu diễn hai thuộc tính trong response nhưng bỏ qua giá trị client gửi lên.
- SKU được sinh trước khi insert. UUID được dùng để tránh phụ thuộc vào thứ tự ID của database.
- Giá, tồn kho và số lượng giữ chỗ có Bean Validation cho các điều kiện trên từng trường.
- reserve() và release() biểu diễn hành vi nghiệp vụ. Các thao tác nội bộ nên gọi những phương thức này để giữ đúng quy tắc chuyển trạng thái.
- validateInvariants() kiểm tra toàn bộ trạng thái, đặc biệt là quan hệ giữa reservedQuantity và stockQuantity.
- JPA callback chạy trước insert/update để tạo một lớp bảo vệ cuối cùng ở tầng persistence.

Các setter cho tồn kho và số lượng giữ chỗ không kiểm tra quan hệ chéo ngay lập tức. Lý do là JSON có thể gán các thuộc tính theo thứ tự khác nhau; trạng thái tạm thời giữa hai lần gán có thể không hợp lệ dù trạng thái cuối cùng hợp lệ. Ta kiểm tra quan hệ chéo sau khi request đã được ánh xạ đầy đủ, trong event handler ở phần tiếp theo.

### 3.4. Repository được export

~~~java
package com.example.invariants;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

Repository này làm cho Spring Data REST tạo collection resource tại /api/products và item resource tại /api/products/{id}. Client có thể gửi request trực tiếp đến các tài nguyên đó.

### 3.5. Kiểm tra trạng thái sau khi request được ánh xạ

~~~java
package com.example.invariants;

import org.springframework.data.rest.core.annotation.HandleBeforeCreate;
import org.springframework.data.rest.core.annotation.HandleBeforeSave;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
@RepositoryEventHandler(Product.class)
public class ProductRestEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Product product) {
        validate(product);
    }

    @HandleBeforeSave
    public void beforeSave(Product product) {
        validate(product);
    }

    private void validate(Product product) {
        try {
            product.validateInvariants();
        } catch (IllegalArgumentException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    ex.getMessage(),
                    ex);
        }
    }
}
~~~

Event handler này được gọi trước khi Spring Data REST tạo hoặc lưu Product. Lúc đó các thuộc tính trong request đã được ánh xạ lên entity, vì vậy handler có thể kiểm tra trạng thái cuối cùng thay vì kiểm tra một trạng thái trung gian trong lúc gán từng thuộc tính.

Nếu client gửi reservedQuantity lớn hơn stockQuantity, handler trả về lỗi HTTP 400 và repository không lưu trạng thái sai. Handler chỉ kiểm tra tính hợp lệ của trạng thái. Nó không thay thế application service cho các quy trình cần kiểm tra quyền, ghi lịch sử, phát sự kiện hoặc phối hợp nhiều aggregate.

JPA callback tiếp tục bảo vệ entity khi dữ liệu được lưu từ một luồng khác không đi qua Spring Data REST. Không nên dùng callback để gọi repository khác hoặc thực hiện các thao tác I/O; callback nên giữ nhiệm vụ kiểm tra đơn giản.

### 3.6. Nạp dữ liệu mẫu

~~~java
package com.example.invariants;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.math.BigDecimal;
import java.util.List;

@Configuration
public class ProductDataInitializer {

    @Bean
    CommandLineRunner seedProducts(ProductRepository repository) {
        return args -> {
            if (repository.count() == 0) {
                repository.saveAll(List.of(
                    new Product("Bàn phím", new BigDecimal("1290000.00"), 20, 4),
                    new Product("Chuột", new BigDecimal("450000.00"), 50, 10)
                ));
            }
        };
    }
}
~~~

Dữ liệu mẫu cũng đi qua constructor và kiểm tra bất biến. Với ứng dụng thật, migration hoặc quy trình seed có phiên bản thường phù hợp hơn CommandLineRunner.

### 3.7. Cấu hình H2 và Spring Data REST

Tạo application.properties:

~~~properties
spring.application.name=spring-data-rest-invariants

spring.datasource.url=jdbc:h2:mem:invariantsdb
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.show-sql=true

spring.h2.console.enabled=true
spring.h2.console.path=/h2-console

spring.data.rest.base-path=/api
~~~

H2 chạy trong bộ nhớ nên dữ liệu bị xóa khi ứng dụng dừng. ddl-auto=create-drop phù hợp cho demo, không phù hợp để giữ dữ liệu production. Khi triển khai thực tế, dùng database bền vững và công cụ migration như Flyway hoặc Liquibase.

## 4. Kiểm thử bất biến trong entity

Tạo ProductInvariantTest.java:

~~~java
package com.example.invariants;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ProductInvariantTest {

    @Test
    void availableQuantityIsStockMinusReserved() {
        Product product = new Product(
                "Bàn phím",
                new BigDecimal("100.00"),
                10,
                3);

        assertThat(product.getAvailableQuantity()).isEqualTo(7);
    }

    @Test
    void cannotReserveMoreThanAvailableStock() {
        Product product = new Product(
                "Bàn phím",
                new BigDecimal("100.00"),
                10,
                3);

        assertThatThrownBy(() -> product.reserve(8))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Không đủ hàng");
    }

    @Test
    void rejectsInvalidStateAfterDirectPropertyBinding() {
        Product product = new Product(
                "Bàn phím",
                new BigDecimal("100.00"),
                10,
                3);

        // Mô phỏng request cập nhật trực tiếp thuộc tính.
        product.setStockQuantity(2);

        assertThatThrownBy(product::validateInvariants)
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("không được lớn hơn tồn kho");
    }
}
~~~

Test thứ ba mô phỏng tình huống REST binder gọi setter thay vì gọi reserve(). Khi kiểm tra toàn bộ entity sau khi binding, bất biến vẫn phát hiện được. Event handler trong phần trước dùng chính phép kiểm tra đó trước khi repository lưu.

Chạy test:

~~~bash
./mvnw test
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd test
~~~

## 5. Thử ghi entity trực tiếp qua REST

Khởi động ứng dụng:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Đọc danh sách sản phẩm:

~~~bash
curl -i http://localhost:8080/api/products
~~~

Tạo sản phẩm hợp lệ:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Tai nghe","unitPrice":850000,"stockQuantity":10,"reservedQuantity":3}'
~~~

Client không cần gửi id hoặc sku. Server tạo ID và SKU. Response có thể biểu diễn SKU để client tham chiếu, nhưng JSON gửi lên không thể đặt lại hai thuộc tính này.

Thử tạo trạng thái không hợp lệ:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Loa","unitPrice":1500000,"stockQuantity":5,"reservedQuantity":8}'
~~~

Request này vi phạm điều kiện reservedQuantity không lớn hơn stockQuantity. Event handler từ chối trước khi repository lưu và trả lỗi HTTP 400.

Có thể thử PATCH một sản phẩm hiện có để giảm tồn kho xuống thấp hơn số lượng đã giữ chỗ:

~~~bash
curl -i -X PATCH http://localhost:8080/api/products/1 \
  -H "Content-Type: application/json" \
  -d '{"stockQuantity":2}'
~~~

Nếu sản phẩm đang có reservedQuantity lớn hơn 2, trạng thái cuối cùng không hợp lệ và request bị từ chối.

Lưu ý: ID trong ví dụ chỉ minh họa đường dẫn. ID thật do database sinh ra; hãy lấy ID từ response hoặc collection resource trước khi gọi PATCH.

## 6. Chọn đúng lớp bảo vệ cho từng loại quy tắc

Không có một annotation duy nhất giải quyết mọi bất biến. Nên đặt kiểm tra ở lớp gần với ý nghĩa của quy tắc nhất và bổ sung guard ở các đường ghi có thể bỏ qua lớp đó.

| Cơ chế | Phù hợp với | Giới hạn |
|---|---|---|
| Constructor và phương thức entity | Quy tắc tạo mới, thay đổi trạng thái, hành vi miền | REST binding có thể cập nhật setter mà không gọi phương thức nghiệp vụ |
| Bean Validation | Điều kiện trên trường như không rỗng, số không âm | Quy tắc liên quan nhiều trường cần validator cấp lớp hoặc kiểm tra riêng |
| Spring Data REST event handler | Kiểm tra entity sau khi request đã binding, trước create/save | Không tự biểu diễn quy trình nghiệp vụ nhiều bước hoặc so sánh lịch sử trạng thái nếu không tự nạp trạng thái cũ |
| JPA lifecycle callback | Guard trước insert/update từ các luồng persistence | Không nên chứa logic gọi dịch vụ, I/O hoặc quy trình nghiệp vụ |
| Ràng buộc database | NOT NULL, UNIQUE, CHECK, khóa ngoại | Thông báo lỗi thường ít thân thiện; không thay thế kiểm tra quyền và quy trình miền |
| Application service | Giao dịch, quyền, chuyển trạng thái, phối hợp nhiều entity | Cần một endpoint command gọi service thay vì mở toàn bộ đường ghi trực tiếp |

Một nguyên tắc hữu ích: kiểm tra một thuộc tính ở nơi thuộc tính được tạo hoặc thay đổi; kiểm tra quan hệ giữa nhiều thuộc tính sau khi đã có trạng thái đầy đủ; kiểm tra quy tắc chuyển trạng thái trong hành vi miền; kiểm tra quy trình nhiều bước trong application service.

## 7. Thuộc tính nào nên cho client ghi?

Không nên xem mọi trường của entity là dữ liệu đầu vào. Hãy phân loại trước khi export:

- **Có thể ghi trực tiếp:** tên hiển thị hoặc mô tả nếu việc sửa chúng không cần quy trình đặc biệt.
- **Chỉ đọc:** ID, SKU do hệ thống sinh, thời điểm tạo, người tạo, trạng thái dẫn xuất.
- **Chỉ thay đổi qua hành vi nghiệp vụ:** số lượng giữ chỗ, trạng thái duyệt, số dư, hạn mức, trạng thái thanh toán.
- **Không nên công khai:** dữ liệu nội bộ, thông tin bảo mật, trường phục vụ triển khai hoặc kiểm soát.

@JsonProperty(access = JsonProperty.Access.READ_ONLY) giữ thuộc tính trong response nhưng bỏ qua giá trị ghi từ JSON. @JsonIgnore có thể ẩn thuộc tính khỏi representation nếu client không cần thấy nó. @Column(updatable = false) ngăn JPA đưa cột vào câu UPDATE; riêng annotation này không phải cơ chế kiểm soát JSON binding. Nên phối hợp các cơ chế theo đúng mục đích.

Spring Data REST cũng cho phép không export repository hoặc một phương thức cụ thể. Ví dụ, nếu không muốn công khai CRUD trực tiếp của repository:

~~~java
@RepositoryRestResource(exported = false)
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

Sau đó, ứng dụng có thể cung cấp các endpoint riêng nhận command DTO và gọi application service. Cách này phù hợp khi gần như mọi thao tác ghi đều cần quy trình nghiệp vụ.

## 8. Khi nào cần application service và command endpoint?

Event handler có ích để bảo vệ trạng thái cuối cùng, nhưng không nên biến nó thành nơi thực hiện mọi use case.

Ví dụ, giữ chỗ hàng có thể cần:

1. Xác thực người dùng có quyền đặt hàng.
2. Đọc sản phẩm và kiểm tra lượng hàng hiện có.
3. Giữ chỗ trong transaction.
4. Tạo bản ghi reservation.
5. Ghi lịch sử thay đổi hoặc phát domain event.
6. Trả về mã reservation cho client.

Đây là một use case, không chỉ là cập nhật trường reservedQuantity. Có thể tổ chức như sau:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void reserve(Long productId, int quantity) {
        Product product = repository.findById(productId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Không tìm thấy sản phẩm: " + productId));

        product.reserve(quantity);
    }
}
~~~

Trong thiết kế này, endpoint command nhận productId và quantity, gọi ProductService.reserve(), còn entity tự bảo vệ bất biến. Nếu không muốn client bỏ qua use case bằng cách gọi repository REST, hãy tắt export tự động như ví dụ ở phần trước.

Với quy tắc liên quan nhiều aggregate hoặc nhiều request đồng thời, cần nghĩ thêm về transaction isolation, optimistic locking bằng @Version, khóa phù hợp và ràng buộc database. Một lần đọc tồn kho rồi ghi lại có thể bị race condition nếu hai request cùng giữ chỗ gần như đồng thời. Kiểm tra trong Java là cần thiết nhưng chưa đủ để giải quyết mọi vấn đề đồng thời.

## 9. Lỗi thường gặp

**Chỉ kiểm tra trong controller hoặc service**

Nếu repository được export và client ghi trực tiếp, request có thể không đi qua controller hoặc service đó. Đặt bất biến trong entity và kiểm tra lại ở event handler hoặc tắt export để buộc request qua application service.

**Chỉ dựa vào setter**

Setter của từng trường không đủ để kiểm tra quy tắc phụ thuộc nhiều trường. Ví dụ, việc gán tồn kho và số lượng giữ chỗ có thể diễn ra theo thứ tự khác nhau. Kiểm tra trạng thái cuối cùng sau binding.

**Cho client sửa trường định danh hoặc trạng thái nội bộ**

Không có setter không phải lúc nào cũng là chính sách API đầy đủ. Đánh dấu rõ thuộc tính chỉ đọc hoặc ẩn nó trong JSON; kiểm tra request thực tế bằng HTTP test. Không coi @Column(updatable = false) là biện pháp thay thế cho quyền ghi của API.

**Dùng JPA callback để thực hiện use case**

Callback thích hợp cho kiểm tra persistence đơn giản. Không gọi repository khác, gửi email hoặc gọi hệ thống bên ngoài từ callback; các việc đó cần application service và transaction/outbox phù hợp.

**Kiểm tra đúng trong một request nhưng sai khi có nhiều request đồng thời**

Hai request có thể cùng đọc một lượng tồn kho và cùng vượt qua kiểm tra trước khi lưu. Cân nhắc @Version, cập nhật nguyên tử hoặc khóa database tùy mô hình dữ liệu và mức tải.

**Mở toàn bộ repository cho người dùng chưa xác thực**

Spring Data REST tự tạo nhiều endpoint ghi. Cần cấu hình Spring Security, xác thực, phân quyền theo tài nguyên và kiểm soát các phương thức HTTP trước khi đưa API ra môi trường dùng thật.

## 10. Checklist thiết kế

Trước khi export một entity qua Spring Data REST, hãy trả lời:

1. Những trường nào client được phép tạo hoặc cập nhật?
2. Trường nào chỉ đọc hoặc do server sinh?
3. Những điều kiện nào liên quan đến nhiều thuộc tính?
4. Những thay đổi nào phải đi qua phương thức nghiệp vụ?
5. Event handler có kiểm tra trạng thái cuối cùng trước create/save không?
6. JPA và database có guard phù hợp cho các luồng ghi khác không?
7. Quy tắc có thể bị vi phạm bởi hai request đồng thời không?
8. Repository có nên export toàn bộ CRUD hay cần custom command endpoint?
9. Endpoint ghi đã được xác thực và phân quyền chưa?
10. Có test cho cả thao tác hợp lệ và request cố tình gửi trạng thái không hợp lệ chưa?

## 11. Kết luận

Khi Spring Data REST cho phép client ghi trực tiếp vào entity, mọi bất biến không được bảo vệ ở đường ghi đó đều có nguy cơ bị bỏ qua. Hãy đặt hành vi miền trong entity, dùng Bean Validation cho điều kiện trên trường, kiểm tra quan hệ giữa các trường sau khi request được binding, và giữ JPA/database như lớp bảo vệ bổ sung.

Với các quy trình có chuyển trạng thái, phân quyền, lịch sử hoặc phối hợp nhiều aggregate, hãy dùng command endpoint gọi application service và cân nhắc tắt export CRUD trực tiếp. Mục tiêu là để mọi đường ghi đều đi qua những quy tắc cần thiết, bất kể request đến từ REST API, batch job hay một luồng nội bộ khác.
