# Chuẩn bị mô hình miền, dữ liệu và cấu hình tối thiểu

Một môi trường thực hành Spring Data Commons cần giúp bạn phân biệt được hai phần: **contract truy cập dữ liệu dùng chung** và **thành phần thực thi contract trên kho dữ liệu cụ thể**. Nếu chỉ thêm Commons rồi khai báo repository, bạn chưa có đủ một ứng dụng có thể lưu và truy vấn dữ liệu.

Bài học thuộc chương **Khởi tạo thực hành** của mô-đun **SPRING_DATA_COMMONS**. Chúng ta chuẩn bị một mô hình sản phẩm nhỏ, bộ dữ liệu có chủ đích và cấu hình tối thiểu để thực hành CRUD, derived query, phân trang và sắp xếp. Cùng mô hình này còn có thể dùng làm điểm xuất phát cho projection, Query by Example, auditing và mở rộng repository.

## 1. Phạm vi của môi trường thực hành

Bài học chọn **Spring Data JPA và H2 trong bộ nhớ** làm một môi trường thực thi cụ thể.

| Thành phần | Vai trò trong bài |
| --- | --- |
| Spring Data Commons | Cung cấp các contract như `CrudRepository`, `PagingAndSortingRepository`, `Pageable`, `Page` và `Sort` |
| Spring Data JPA | Tạo repository thực thi các contract và truy vấn trên JPA |
| JPA provider | Thực hiện mapping entity và thao tác persistence |
| H2 | Lưu dữ liệu thực hành trong bộ nhớ của tiến trình |
| Spring Boot | Tự cấu hình các thành phần phù hợp và khởi tạo ứng dụng |

H2 không phải một phần của Commons. Các annotation JPA trong mô hình cũng không phải annotation chung bắt buộc cho mọi mô-đun Spring Data.

Ví dụ mã trong bài dùng **Spring Boot 3.x, Jakarta Persistence và Java 17 trở lên**, với một bộ phiên bản tương thích đã được chọn cho dự án. Phần kiểm thử dùng package annotation của dòng Spring Boot 3.x. Không trộn `javax.persistence` với `jakarta.persistence` trong mô hình này.

Bài học trình bày các đoạn mã để tạo môi trường thực hành; không mặc định rằng chúng đã được chạy trong một dự án của bạn.

## 2. Chuẩn bị dependency theo bộ phiên bản đã chọn

Giả sử dự án Spring Boot đã có parent hoặc dependency management phù hợp. Những dependency cần cho ví dụ Maven là:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
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
```

Đây là phần dependency, không phải toàn bộ một `pom.xml` độc lập. Phiên bản đến từ cơ chế quản lý của dự án.

Starter JPA đưa vào mô-đun JPA và các dependency liên quan, trong đó có Commons. Không cần tự chọn thêm một phiên bản Commons khác để làm bài này.

H2 được dùng khi chạy ứng dụng. Starter kiểm thử cung cấp hạ tầng cần cho kiểm tra ở cuối bài. Môi trường này chưa cần web starter, controller hay API HTTP để quan sát hành vi repository.

## 3. Tổ chức package để cấu hình tự động nhận diện đúng

Cấu trúc minh họa:

```text
src/main/java/example/commonspractice/
  CommonsPracticeApplication.java
  domain/
    Product.java
  repository/
    ProductRepository.java
  config/
    PracticeDataConfiguration.java

src/main/resources/
  application-practice.yml

src/test/java/example/commonspractice/repository/
  ProductRepositoryTest.java
```

Lớp ứng dụng đặt tại package cha:

```java
package example.commonspractice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CommonsPracticeApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            CommonsPracticeApplication.class,
            args
        );
    }
}
```

Với cấu trúc này và auto-configuration phù hợp của starter JPA, entity và repository nằm trong phạm vi package mà ứng dụng dùng để phát hiện các thành phần liên quan.

Không cần thêm `@EnableJpaRepositories` hoặc `@EntityScan` cho cấu trúc đơn giản trên. Nếu chuyển entity hoặc repository ra ngoài phạm vi đó, phải điều chỉnh cấu hình tương ứng; không nên thêm annotation một cách ngẫu nhiên khi chưa xác định lỗi package.

## 4. Chọn mô hình nhỏ nhưng đủ để tạo các tình huống khác nhau

Đối tượng miền của bài là `Product`:

| Thuộc tính | Kiểu Java | Mục đích thực hành |
| --- | --- | --- |
| `id` | `Long` | Tìm, lưu và xóa theo định danh |
| `name` | `String` | Truy vấn chuỗi và projection |
| `category` | `String` | Lọc nhóm sản phẩm |
| `price` | `BigDecimal` | Lọc khoảng giá và sắp xếp |
| `active` | `boolean` | Điều kiện trạng thái và giá trị mặc định khi dùng QBE |

Mô hình chưa có quan hệ với entity khác. Điều này giúp tập trung vào abstraction repository mà chưa phải xử lý quan hệ, lazy loading hoặc cascade.

Một số quyết định cần được hiểu rõ:

- Dùng `Long` thay vì `long` cho ID được sinh để trạng thái chưa có định danh có thể biểu diễn bằng `null`.
- Dùng `BigDecimal` để biểu diễn giá tiền với số chữ số thập phân có chủ đích.
- Dùng mã danh mục ổn định như `ACCESSORY` thay vì phụ thuộc cách viết hoa/thường của nhãn hiển thị.
- Không coi tên sản phẩm là duy nhất.
- Có cả sản phẩm đang bán và ngừng bán để phát hiện truy vấn thiếu điều kiện.

Với một kho dữ liệu khác, bạn có thể giữ nhiều khái niệm miền này nhưng phải xem lại mapping, kiểu ID và khả năng truy vấn. Không mặc định entity JPA có thể được dùng nguyên trạng cho mọi mô-đun.

## 5. Cài đặt entity Product

Nội dung minh họa cho `domain/Product.java`:

```java
package example.commonspractice.domain;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, length = 40)
    private String category;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    protected Product() {
        // JPA sử dụng constructor không tham số.
    }

    public Product(
            String name,
            String category,
            BigDecimal price,
            boolean active) {
        this.name = requiredText(name, "name", 120);
        this.category = requiredText(category, "category", 40);
        this.price = validPrice(price);
        this.active = active;
    }

    private static String requiredText(
            String value,
            String field,
            int maxLength) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                field + " không được rỗng"
            );
        }

        String result = value.trim();

        if (result.length() > maxLength) {
            throw new IllegalArgumentException(
                field + " vượt quá độ dài cho phép"
            );
        }

        return result;
    }

    private static BigDecimal validPrice(BigDecimal value) {
        Objects.requireNonNull(value, "price không được null");

        BigDecimal result = value.setScale(
            2,
            RoundingMode.UNNECESSARY
        );

        if (result.signum() < 0 || result.precision() > 12) {
            throw new IllegalArgumentException(
                "price phải không âm và phù hợp precision 12, scale 2"
            );
        }

        return result;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isActive() {
        return active;
    }
}
```

### Vì sao mapping được đặt như vậy?

Annotation định danh nằm trên field, nên JPA dùng field access cho mô hình này. Không cần sinh setter công khai chỉ để JPA có thể gán các field.

Constructor không tham số có mức truy cập `protected` phục vụ JPA. Constructor công khai dùng để tạo sản phẩm mới có dữ liệu hợp lệ.

`GenerationType.IDENTITY` là lựa chọn cho bài thực hành JPA/H2 này. Nó không phải chiến lược định danh chung do Commons áp đặt.

Giá được chuẩn hóa về hai chữ số thập phân. `RoundingMode.UNNECESSARY` yêu cầu phép chuẩn hóa không làm mất giá trị; một giá cần làm tròn, chẳng hạn `1.234`, sẽ bị từ chối. Đây là quyết định của mô hình ví dụ, không phải hành vi tự có từ repository.

Khi khởi tạo giá trong mã, dùng chuỗi như `new BigDecimal("350000.00")` để biểu đạt giá trị thập phân rõ ràng.

## 6. Khai báo repository bằng contract của Commons

Nội dung minh họa cho `repository/ProductRepository.java`:

```java
package example.commonspractice.repository;

import example.commonspractice.domain.Product;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.PagingAndSortingRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long>,
                PagingAndSortingRepository<Product, Long> {

    Page<Product> findByActiveTrueAndCategory(
        String category,
        Pageable pageable
    );
}
```

Repository này cho phép thực hành ba nhóm hành vi:

| Khai báo | Khả năng được sử dụng |
| --- | --- |
| `CrudRepository<Product, Long>` | `save`, `saveAll`, `findById`, `count`, xóa theo contract CRUD |
| `PagingAndSortingRepository<Product, Long>` | `findAll(Pageable)` và `findAll(Sort)` |
| `findByActiveTrueAndCategory` | Derived query theo trạng thái và danh mục, nhận yêu cầu trang |

Việc kế thừa rõ cả hai interface giúp không dựa vào giả định rằng contract phân trang luôn kế thừa CRUD ở mọi dòng API.

Tên `Active` và `Category` trong phương thức dựa trên thuộc tính của mô hình Java. Không thay chúng bằng tên bảng hoặc tên cột SQL.

Không cần viết implementation cho phương thức này trong môi trường JPA được cấu hình phù hợp. Hạ tầng Spring Data JPA sử dụng các cơ chế chung và tích hợp JPA để cung cấp implementation.

Ngược lại, nếu chỉ có Commons trên classpath thì interface trên vẫn chưa có một engine tự lưu dữ liệu vào H2.

## 7. Cấu hình riêng cho profile thực hành

Nội dung minh họa cho `application-practice.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:commons_practice
    username: sa
    password: ""
  jpa:
    hibernate:
      ddl-auto: create-drop
    show-sql: true
```

Ý nghĩa của từng phần:

| Cấu hình | Tác dụng |
| --- | --- |
| `jdbc:h2:mem:commons_practice` | Kết nối tới cơ sở dữ liệu H2 trong bộ nhớ của tiến trình |
| `username`, `password` | Thông tin kết nối cho cơ sở dữ liệu thực hành |
| `ddl-auto: create-drop` | Cho Hibernate tạo schema khi khởi tạo và thực hiện dọn schema khi đóng |
| `show-sql: true` | Hỗ trợ quan sát SQL do provider thực thi |

Dữ liệu H2 trong cấu hình này không phải dữ liệu bền vững sau khi tiến trình kết thúc. Cơ chế `create-drop` phục vụ môi trường thực hành tạm thời này, không thay thế quy trình migration của một hệ thống cần lưu dữ liệu lâu dài.

Không cần đặt dialect hoặc driver class thủ công cho trường hợp tối thiểu nếu auto-configuration nhận diện được H2 từ URL và dependency.

Để dùng cấu hình, chạy lớp ứng dụng trong IDE với program argument:

```text
--spring.profiles.active=practice
```

Tên file `application-practice.yml` không tự làm profile trở thành active. Nếu không bật profile, cả cấu hình riêng và bộ nạp dữ liệu gắn profile ở phần sau sẽ không được áp dụng theo cách bài học dự kiến.

## 8. Thiết kế bộ dữ liệu mẫu có thể đối chiếu

Dữ liệu mẫu cần có nhiều hơn một dòng và có những khác biệt phục vụ từng kiểu truy vấn:

| Tên | Danh mục | Giá | Đang bán |
| --- | --- | ---: | --- |
| Bàn phím cơ | ACCESSORY | 850000.00 | true |
| Chuột không dây | ACCESSORY | 350000.00 | true |
| Đế laptop | ACCESSORY | 350000.00 | true |
| Tai nghe cũ | ACCESSORY | 250000.00 | false |
| Màn hình 24 inch | DISPLAY | 3200000.00 | true |
| Cáp USB-C | CABLE | 120000.00 | true |

Bộ dữ liệu có những đặc điểm có chủ đích:

- Có ba danh mục để kiểm tra điều kiện lọc.
- Danh mục `ACCESSORY` có bốn sản phẩm, nhưng chỉ ba sản phẩm đang bán.
- Sản phẩm ngừng bán có giá thấp hơn các sản phẩm đang bán cùng danh mục, giúp phát hiện việc quên điều kiện `active`.
- Hai sản phẩm có cùng giá để quan sát nhu cầu thêm khóa sắp xếp phụ.
- Ba sản phẩm đang bán thuộc `ACCESSORY` vừa đủ tạo hai trang khi kích thước trang là hai.

Không gắn kỳ vọng vào các ID cụ thể như 1, 2, 3. ID được sinh là chi tiết của cơ chế lưu trữ; một bộ kiểm tra tốt nên dùng ID từ kết quả lưu.

## 9. Nạp dữ liệu sau khi ứng dụng khởi tạo

Nội dung minh họa cho `config/PracticeDataConfiguration.java`:

```java
package example.commonspractice.config;

import java.math.BigDecimal;
import java.util.List;

import example.commonspractice.domain.Product;
import example.commonspractice.repository.ProductRepository;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("practice")
public class PracticeDataConfiguration {

    @Bean
    ApplicationRunner seedPracticeData(
            ProductRepository products) {
        return args -> {
            if (products.count() != 0) {
                throw new IllegalStateException(
                    "Bài thực hành yêu cầu kho dữ liệu ban đầu rỗng"
                );
            }

            products.saveAll(List.of(
                new Product(
                    "Bàn phím cơ", "ACCESSORY",
                    new BigDecimal("850000.00"), true
                ),
                new Product(
                    "Chuột không dây", "ACCESSORY",
                    new BigDecimal("350000.00"), true
                ),
                new Product(
                    "Đế laptop", "ACCESSORY",
                    new BigDecimal("350000.00"), true
                ),
                new Product(
                    "Tai nghe cũ", "ACCESSORY",
                    new BigDecimal("250000.00"), false
                ),
                new Product(
                    "Màn hình 24 inch", "DISPLAY",
                    new BigDecimal("3200000.00"), true
                ),
                new Product(
                    "Cáp USB-C", "CABLE",
                    new BigDecimal("120000.00"), true
                )
            ));

            System.out.println(
                "Đã nạp " + products.count()
                    + " sản phẩm thực hành."
            );
        };
    }
}
```

`ApplicationRunner` chạy sau khi các thành phần ứng dụng cần thiết đã được khởi tạo. Ở môi trường này, nó dùng repository đã được tạo để nạp dữ liệu.

Điều kiện kho rỗng giúp tránh việc vô tình chấp nhận một tập dữ liệu khác mà vẫn tưởng đang dùng đúng fixture của bài. Với H2 tạm thời và `create-drop`, mỗi lần khởi tạo môi trường như thiết kế sẽ bắt đầu từ schema mới.

Bài chọn một cách nạp dữ liệu bằng Java. Không cần đồng thời thêm `data.sql` để chèn lại cùng các dòng, vì như vậy có thể gây trùng dữ liệu hoặc khiến số lượng thực tế khác kỳ vọng.

Khi chạy thành công, thông báo dự kiến là:

```text
Đã nạp 6 sản phẩm thực hành.
```

Đây là kết quả kỳ vọng để bạn đối chiếu, không phải báo cáo một lần thực thi trong bài viết.

## 10. Xác định kết quả truy vấn trước khi chạy

Từ bộ dữ liệu trên, lời gọi sau cần trả về ba sản phẩm phù hợp trên hai trang:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

// Đoạn mã nằm trong phương thức đã có productRepository.
Pageable request = PageRequest.of(
    0,
    2,
    Sort.by("price").ascending()
        .and(Sort.by("id").ascending())
);

Page<Product> firstPage = productRepository
    .findByActiveTrueAndCategory("ACCESSORY", request);
```

Ở đoạn mã trên, `Product` là entity đã khai báo; nếu dùng trong một lớp khác, cần import kiểu từ package `example.commonspractice.domain`.

Kỳ vọng:

| Thuộc tính kết quả | Giá trị |
| --- | --- |
| Tổng số sản phẩm phù hợp | 3 |
| Tổng số trang | 2 |
| Số phần tử ở trang đầu | 2 |
| Giá của hai phần tử trang đầu | 350000.00 và 350000.00 |
| Còn trang tiếp theo | true |
| Số phần tử ở trang thứ hai | 1 |
| Giá của phần tử trang thứ hai | 850000.00 |

Khóa `id` bổ sung làm rõ thứ tự giữa hai sản phẩm cùng giá trong tập dữ liệu hiện tại. Không cần khẳng định sản phẩm nào có ID nhỏ hơn nếu bài kiểm tra không dựa vào ID được lưu thực tế.

Sắp xếp rõ ràng không tạo ra snapshot nhất quán qua nhiều lần đọc khi dữ liệu đang thay đổi. Ở giai đoạn khởi tạo này, bộ dữ liệu cố định giúp tách vấn đề đó khỏi việc học API.

## 11. Mã kiểm tra môi trường thực hành

Có thể dùng một JPA slice test để xác minh mapping, repository và truy vấn cùng hoạt động.

Ví dụ cho `ProductRepositoryTest.java`:

```java
package example.commonspractice.repository;

import java.math.BigDecimal;
import java.util.List;

import example.commonspractice.domain.Product;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository products;

    @BeforeEach
    void prepareData() {
        products.saveAll(List.of(
            new Product(
                "Bàn phím cơ", "ACCESSORY",
                new BigDecimal("850000.00"), true
            ),
            new Product(
                "Chuột không dây", "ACCESSORY",
                new BigDecimal("350000.00"), true
            ),
            new Product(
                "Đế laptop", "ACCESSORY",
                new BigDecimal("350000.00"), true
            ),
            new Product(
                "Tai nghe cũ", "ACCESSORY",
                new BigDecimal("250000.00"), false
            ),
            new Product(
                "Màn hình 24 inch", "DISPLAY",
                new BigDecimal("3200000.00"), true
            ),
            new Product(
                "Cáp USB-C", "CABLE",
                new BigDecimal("120000.00"), true
            )
        ));
    }

    @Test
    void filtersActiveProductsAndBuildsTwoPages() {
        assertThat(products.count()).isEqualTo(6);

        Page<Product> first = products
            .findByActiveTrueAndCategory(
                "ACCESSORY",
                PageRequest.of(
                    0,
                    2,
                    Sort.by("price").ascending()
                        .and(Sort.by("id").ascending())
                )
            );

        assertThat(first.getTotalElements()).isEqualTo(3);
        assertThat(first.getTotalPages()).isEqualTo(2);
        assertThat(first.hasNext()).isTrue();

        assertThat(first.getContent())
            .hasSize(2)
            .allSatisfy(product -> {
                assertThat(product.isActive()).isTrue();
                assertThat(product.getCategory())
                    .isEqualTo("ACCESSORY");
            });

        assertThat(first.getContent())
            .extracting(Product::getPrice)
            .containsExactly(
                new BigDecimal("350000.00"),
                new BigDecimal("350000.00")
            );

        Page<Product> second = products
            .findByActiveTrueAndCategory(
                "ACCESSORY",
                first.nextPageable()
            );

        assertThat(second.getContent())
            .extracting(Product::getPrice)
            .containsExactly(new BigDecimal("850000.00"));

        assertThat(second.hasNext()).isFalse();
    }

    @Test
    void savesAndFindsUsingTheGeneratedId() {
        Product saved = products.save(
            new Product(
                "Sổ tay", "STATIONERY",
                new BigDecimal("45000.00"), true
            )
        );

        assertThat(saved.getId()).isNotNull();

        assertThat(products.findById(saved.getId()))
            .hasValueSatisfying(found -> {
                assertThat(found.getName()).isEqualTo("Sổ tay");
                assertThat(found.getPrice())
                    .isEqualByComparingTo("45000.00");
            });
    }
}
```

Trong cấu hình mặc định phù hợp với ví dụ, `@DataJpaTest` sử dụng môi trường kiểm thử JPA với cơ sở dữ liệu nhúng có trên classpath và rollback giao dịch sau mỗi test. Vì vậy, mỗi test tự nạp fixture và không dựa vào kết quả của test khác.

Không bật profile `practice` cho lớp test này. Bộ nạp `ApplicationRunner` thuộc luồng chạy ứng dụng không phải nguồn dữ liệu mà test dựa vào.

Mã kiểm tra xác minh hai điều có ý nghĩa:

- Dữ liệu được mapping, lưu và tìm lại bằng ID do kho dữ liệu sinh.
- Điều kiện trạng thái, danh mục, phân trang và sắp xếp tạo đúng tập kết quả dự kiến.

Đây là kiểm tra tích hợp trong môi trường JPA/H2 đã chọn. Nó không chứng minh mọi kho dữ liệu khác có cùng mapping, SQL hoặc hành vi giao dịch.

## 12. Nhận diện lỗi thiết lập từ dấu hiệu cụ thể

| Dấu hiệu | Điều nên kiểm tra trước |
| --- | --- |
| Không có bean `ProductRepository` | Dependency JPA, auto-configuration và phạm vi package repository |
| Entity không được quản lý | Annotation `@Entity`, import Jakarta Persistence và phạm vi entity scan |
| Không tìm thấy driver hoặc không tạo được datasource | Dependency H2 runtime và cấu hình kết nối thực tế |
| Không xuất hiện sáu dòng dữ liệu mẫu | Profile `practice` có được bật và runner có chạy thành công không |
| Số lượng dữ liệu lớn hơn sáu | Có đồng thời runner, SQL initializer hoặc cơ chế nạp khác không |
| Truy vấn báo không có thuộc tính | Tên Java trong derived query và sort có khớp entity không |
| Không gọi được `findAll(Pageable)` | Interface có kế thừa contract phân trang phù hợp không |
| Giá không phù hợp dữ liệu kỳ vọng | Cách tạo `BigDecimal`, scale và ràng buộc precision |
| Test phụ thuộc thứ tự chạy | Fixture có tự đủ cho từng test và giao dịch có được cô lập như dự kiến không |

Không xử lý mọi lỗi bằng cách thêm dependency hoặc annotation. Hãy xác định lỗi thuộc classpath, mapping, repository, kết nối hay dữ liệu trước.

## 13. Những gì đã sẵn sàng và những gì sẽ bổ sung theo bài sau

Môi trường hiện tại đủ để:

- Thực hành các phương thức CRUD theo định danh.
- Tạo derived query đơn giản trên thuộc tính.
- Quan sát sự khác nhau giữa dữ liệu phù hợp điều kiện và toàn bộ dữ liệu.
- Thực hành `Pageable`, `Sort` và kết quả `Page`.
- Bổ sung projection dựa trên những thuộc tính đã có.

Một số khả năng cần chuẩn bị thêm khi đi vào bài tương ứng:

| Khả năng | Phần cần bổ sung hoặc quyết định |
| --- | --- |
| Query by Example | Contract executor phù hợp, cách tạo probe và `ExampleMatcher`; chú ý `active` là kiểu nguyên thủy |
| Auditing | Field thời gian/chủ thể, annotation và cơ chế kích hoạt auditing của mô-đun |
| Repository fragment | Interface hành vi tùy chỉnh và implementation phù hợp |
| Kiểm soát đồng thời | Chiến lược phiên bản hoặc cơ chế của kho dữ liệu theo yêu cầu |
| Mapping quan hệ | Ranh giới aggregate, kiểu quan hệ và hành vi tải/lưu cần thiết |

Không cần bật tất cả ngay từ đầu. Cấu hình tối thiểu tốt giúp bạn biết chính xác một khả năng mới đã thêm những thành phần nào và thay đổi hành vi ở đâu.

## 14. Điểm cần ghi nhớ

Môi trường thực hành có ích khi mô hình nhỏ, dữ liệu có chủ đích và kết quả dự kiến có thể đối chiếu. Trong bài này, `Product`, sáu dòng fixture và một profile H2 riêng tạo nền tảng để học các abstraction của Spring Data Commons qua một mô-đun JPA cụ thể.

Hãy giữ rõ ba lớp trách nhiệm: **Commons mô tả contract**, **mô-đun lưu trữ thực thi contract**, và **cấu hình cùng dữ liệu mẫu tạo điều kiện để quan sát hành vi**. Khi ba phần đó rõ ràng, việc bổ sung projection, QBE, auditing và các điểm mở rộng repository sẽ dễ kiểm soát hơn.
