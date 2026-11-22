# Lựa chọn kế thừa hoặc kết hợp đối tượng theo yêu cầu nghiệp vụ trong JPA

Trong Java Persistence API (JPA), một quan hệ giữa các khái niệm nghiệp vụ có thể được biểu diễn bằng **kế thừa** (*inheritance*) hoặc **kết hợp đối tượng** (*composition*). Lựa chọn này không chỉ ảnh hưởng đến việc thiết kế class Java mà còn quyết định cách JPA ánh xạ đối tượng vào bảng quan hệ, quản lý định danh, tạo truy vấn, xử lý vòng đời và triển khai thay đổi schema.

Ví dụ, hệ thống có hai loại sản phẩm:

- **Sản phẩm vật lý** có khối lượng, thông tin đóng gói và cần vận chuyển.
- **Sản phẩm số** có tài nguyên tải về, quyền truy cập và không cần vận chuyển hàng hóa vật lý.

Có thể đặt `PhysicalProduct extends Product` và `DigitalProduct extends Product`. Nhưng nếu một sản phẩm có **cả bản in và bản tải về**, hoặc những lựa chọn giao hàng có thể bật/tắt theo thời gian, thiết kế phân cấp kiểu này sẽ gặp khó khăn. Khi đó, một `Product` có nhiều `FulfillmentOption` có thể phản ánh nghiệp vụ tốt hơn.

**Nguyên tắc trung tâm:** Không bắt đầu bằng câu hỏi “dùng `@Inheritance` nào?”, mà bắt đầu bằng “đối tượng này **là một loại** đối tượng kia, hay **có một thành phần/khả năng** nào đó?”.

## 1. Phân biệt quan hệ *is-a* và *has-a*

### 1.1. Kế thừa biểu diễn *is-a*

~~~text
                  Product
                 /       \
                /         \
       PhysicalProduct   DigitalProduct
~~~

Một `PhysicalProduct` **là một** `Product`. Nếu các hành vi chung của Product áp dụng hợp lý cho mọi subtype, superclass có thể định nghĩa hợp đồng chung và subclass hiện thực phần chuyên biệt.

Ví dụ:

~~~java
public abstract class Product {
    public abstract String fulfillmentDescription();
}

public class PhysicalProduct extends Product {
    @Override
    public String fulfillmentDescription() {
        return "Giao hàng vật lý";
    }
}

public class DigitalProduct extends Product {
    @Override
    public String fulfillmentDescription() {
        return "Cấp quyền tải xuống";
    }
}
~~~

Khi dùng một danh sách `List<Product>`, code có thể gọi `fulfillmentDescription()` mà không cần biết subtype cụ thể. Đây là một biểu hiện của **đa hình** (*polymorphism*).

Tuy nhiên, nếu hầu hết subtype không thể đáp ứng hợp đồng chung hoặc phải liên tục ném `UnsupportedOperationException`, hệ phân cấp có thể đang mô hình hóa một quan hệ *is-a* không thực sự tồn tại.

### 1.2. Composition biểu diễn *has-a*

~~~text
                   Product
                      |
                      +-- FulfillmentOption(SHIPPING)
                      |
                      +-- FulfillmentOption(DOWNLOAD)
                      |
                      +-- FulfillmentOption(PICKUP)
~~~

Trong mô hình này, Product **có các phương án phân phối**. Một sản phẩm có thể hỗ trợ nhiều phương án đồng thời; thêm hoặc gỡ một phương án không nhất thiết làm thay đổi class Java của sản phẩm.

Composition có thể được hiện thực bằng:

- Một **value object** nhúng vào entity bằng `@Embeddable`/`@Embedded`.
- Một **entity phụ thuộc** qua `@OneToOne` hoặc `@OneToMany`.
- Một **entity tham chiếu độc lập** qua `@ManyToOne`.
- Một **đối tượng thực thi chiến lược** (*strategy*) ở tầng Java/service, không nhất thiết là entity JPA.

Composition không có nghĩa mọi thành phần đều phải nằm trong một bảng riêng hoặc đều phải là entity.

### 1.3. Tiêu chí lựa chọn ban đầu

| Câu hỏi | Tín hiệu nghiêng về kế thừa | Tín hiệu nghiêng về composition |
|---|---|---|
| Các loại có loại trừ nhau không? | Có, mỗi entity chỉ thuộc một subtype ổn định | Không, entity có thể có nhiều đặc điểm cùng lúc |
| “Loại” có đổi trong vòng đời không? | Hầu như không | Có thể bật/tắt, thêm/bớt hoặc thay đổi |
| Có hợp đồng hành vi chung không? | Có, và mọi subtype thực hiện được | Khác biệt là dữ liệu, chính sách hoặc khả năng |
| Có cần truy vấn mọi subtype như entity cha không? | Có nhu cầu đa hình rõ ràng | Có thể dùng một entity chính và các thành phần |
| Thuộc tính riêng có nhiều và có ràng buộc riêng không? | Có thể là subtype | Cũng có thể là entity thành phần |
| Có nhiều trục phân loại kết hợp được không? | Dễ phát sinh quá nhiều subclass | Thành phần thường diễn đạt các tổ hợp tốt hơn |
| Có cần quản lý lịch sử/thời điểm hiệu lực của đặc điểm không? | Ít phù hợp với subclass cố định | Entity liên kết có metadata thường phù hợp |

Không nên áp dụng bảng như một thuật toán cứng. Đây là những câu hỏi để hiểu **bất biến nghiệp vụ** trước khi quyết định mapping.

## 2. Kế thừa Java và kế thừa entity JPA khác nhau thế nào?

Trong Java, `extends` chỉ khai báo quan hệ giữa các class. JPA lại cần biết:

- Các class nào được quản lý như entity?
- Superclass có phải một entity có thể truy vấn không?
- Những field kế thừa được ánh xạ vào bảng nào?
- Khóa chính của superclass và subclass có quan hệ gì?
- Khi query superclass, provider có cần trả về các instance subtype không?

JPA thường có ba mô hình cần phân biệt:

| Mô hình | Annotation chủ chốt | Có entity cha truy vấn được không? |
|---|---|---|
| Entity inheritance | `@Entity` trên root và subtype; `@Inheritance` trên root | Có |
| Mapped superclass | `@MappedSuperclass` | Không, superclass không phải entity |
| Composition | `@Embedded`, `@OneToOne`, `@OneToMany`... | Không tạo subtype; quan hệ giữa object được ánh xạ riêng |

Ví dụ entity inheritance:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Product {
    // ...
}

@Entity
public class PhysicalProduct extends Product {
    // ...
}

@Entity
public class DigitalProduct extends Product {
    // ...
}
~~~

Trong mô hình này, JPQL có thể truy vấn cả hierarchy thông qua root entity:

~~~java
List<Product> products = entityManager.createQuery(
    "SELECT p FROM Product p", Product.class
).getResultList();
~~~

Kết quả có thể chứa `PhysicalProduct` và `DigitalProduct`. Đây là **truy vấn đa hình**: một entity root đại diện cho nhiều loại cụ thể.

## 3. Ba chiến lược inheritance của JPA

Đặc tả JPA cung cấp ba giá trị chính của `InheritanceType`:

1. `SINGLE_TABLE`: toàn bộ hierarchy trong một bảng.
2. `JOINED`: bảng chung và các bảng cho subclass.
3. `TABLE_PER_CLASS`: mỗi concrete entity có một bảng riêng chứa cả trường kế thừa.

Nếu có hierarchy entity nhưng không khai báo `@Inheritance` trên root, chiến lược mặc định là **`SINGLE_TABLE`**.

### 3.1. `SINGLE_TABLE` — Một bảng cho mọi subtype

Annotation ví dụ:

~~~java
@Entity
@Table(name = "product")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "product_kind",
    discriminatorType = DiscriminatorType.STRING
)
public abstract class Product {
}

@Entity
@DiscriminatorValue("PHYSICAL")
public class PhysicalProduct extends Product {
}

@Entity
@DiscriminatorValue("DIGITAL")
public class DigitalProduct extends Product {
}
~~~

Schema minh họa:

~~~sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    product_kind VARCHAR(30) NOT NULL,
    sku VARCHAR(40) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(14,2) NOT NULL,
    shipping_weight_grams BIGINT,
    download_location VARCHAR(500)
);
~~~

Dữ liệu:

~~~text
id | product_kind | sku      | shipping_weight_grams | download_location
---+--------------+----------+-----------------------+----------------------
 1 | PHYSICAL     | BOOK-01  | 600                   | NULL
 2 | DIGITAL      | EBOOK-01 | NULL                  | /downloads/book.epub
~~~

`@DiscriminatorColumn` giúp provider nhận biết kiểu entity trong hierarchy. `@DiscriminatorValue` đặt giá trị nhận dạng subtype. Discriminator phục vụ phân loại entity trong ORM, không phải khóa chính.

**Ưu điểm:**

- Schema đơn giản, một bảng.
- Truy vấn chung Product thường không cần JOIN với bảng subtype.
- Quan hệ FK từ các bảng khác trỏ đến Product thuận tiện vì tất cả ID nằm trong một bảng.
- Phù hợp với hierarchy nhỏ hoặc số field riêng chưa quá nhiều.

**Hạn chế:**

- Một bảng có thể nhiều cột nullable do mỗi subtype chỉ dùng một số cột.
- Không dễ đặt `NOT NULL` vô điều kiện lên một cột chỉ bắt buộc với subtype nhất định.
- Thêm subtype có thể cần thêm cột và cập nhật constraint theo discriminator.
- Nếu nhiều loại có bộ field rất khác nhau, bảng trở nên rộng và khó quản lý.

Ví dụ, `shipping_weight_grams` bắt buộc với PHYSICAL nhưng không có ý nghĩa với DIGITAL. Một ràng buộc DB có điều kiện có thể giúp bảo vệ dữ liệu:

~~~sql
ALTER TABLE product
ADD CONSTRAINT ck_product_subtype
CHECK (
    (product_kind = 'PHYSICAL'
        AND shipping_weight_grams IS NOT NULL)
    OR
    (product_kind = 'DIGITAL'
        AND download_location IS NOT NULL)
);
~~~

Cú pháp và khả năng áp dụng phụ thuộc database; khi thêm subtype cần cập nhật constraint tương ứng. JPA annotation ở subclass không phải lúc nào cũng đủ để sinh mọi ràng buộc có điều kiện theo nghiệp vụ.

### 3.2. `JOINED` — Một bảng gốc và bảng riêng cho subtype

~~~java
@Entity
@Table(name = "product")
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Product {
}

@Entity
@Table(name = "physical_product")
@PrimaryKeyJoinColumn(name = "product_id")
public class PhysicalProduct extends Product {
}

@Entity
@Table(name = "digital_product")
@PrimaryKeyJoinColumn(name = "product_id")
public class DigitalProduct extends Product {
}
~~~

Schema minh họa:

~~~sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(14,2) NOT NULL
);

CREATE TABLE physical_product (
    product_id BIGINT PRIMARY KEY REFERENCES product(id),
    shipping_weight_grams BIGINT NOT NULL
);

CREATE TABLE digital_product (
    product_id BIGINT PRIMARY KEY REFERENCES product(id),
    download_location VARCHAR(500) NOT NULL
);
~~~

Một `PhysicalProduct` được biểu diễn bằng dòng dữ liệu ở `product` và một dòng ở `physical_product` dùng cùng ID. Nhưng ở phía Java/JPA, chúng là **một entity thuộc subtype PhysicalProduct**, không phải hai entity khác nhau nối nhau bằng `@OneToOne`.

**Ưu điểm:**

- Field chung nằm ở bảng gốc, field riêng nằm ở bảng subtype.
- Có thể đặt constraint riêng như `NOT NULL` ở bảng subtype.
- Tránh phải thêm quá nhiều cột nullable cho mọi loại vào một bảng.
- Có một bảng Product chung để các quan hệ ngoài hierarchy tham chiếu.

**Hạn chế:**

- Truy vấn polymorphic có thể cần JOIN đến nhiều bảng con.
- Insert/remove một entity subtype có thể phải tác động nhiều bảng.
- Migration thêm subtype thường cần bảng và khóa ngoại mới.
- FK từ bảng con tới bảng cha chưa đủ để DB tự bảo đảm mọi bất biến về việc mỗi dòng gốc thuộc đúng một subtype; cần xem toàn bộ cơ chế ghi và constraint.

Chọn JOINED khi hệ thống cần hierarchy thực sự nhưng dữ liệu subtype khá khác nhau và cần schema rõ ràng.

### 3.3. `TABLE_PER_CLASS` — Mỗi concrete class có một bảng

~~~java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class Product {
}

@Entity
@Table(name = "physical_product")
public class PhysicalProduct extends Product {
}

@Entity
@Table(name = "digital_product")
public class DigitalProduct extends Product {
}
~~~

Schema ý tưởng:

~~~text
physical_product
    id
    sku
    name
    price
    shipping_weight_grams

digital_product
    id
    sku
    name
    price
    download_location
~~~

Các field chung bị lặp lại trong mỗi bảng concrete.

**Ưu điểm:** bảng của từng subtype tương đối độc lập, và truy vấn riêng một subtype có thể không cần JOIN bảng gốc.

**Hạn chế:**

- Truy vấn `SELECT p FROM Product p` có thể cần UNION hoặc kỹ thuật tổng hợp từ nhiều bảng.
- Khó có một FK chuẩn trỏ đến “Product bất kỳ” vì không tồn tại bảng Product chung chứa mọi record.
- Những cột chung bị lặp và migration thay đổi field chung phải xử lý nhiều bảng.
- Việc sinh ID cần bảo đảm phù hợp với identity của hierarchy; một số provider hạn chế IDENTITY cho TABLE_PER_CLASS.
- Tăng số subtype có thể làm truy vấn đa hình phức tạp và tốn kém hơn.

Không nhầm TABLE_PER_CLASS với JOINED: JOINED lưu trường chung **một lần ở bảng cha**; TABLE_PER_CLASS **lặp trường chung ở mỗi bảng con**.

### 3.4. So sánh ba chiến lược

| Tiêu chí | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
|---|---|---|---|
| Bảng gốc chung | Có, chứa mọi subtype | Có, chứa phần chung | Không bắt buộc có bảng vật lý gốc cho abstract root |
| Cột chung | Một lần | Một lần | Lặp ở các bảng concrete |
| Cột riêng | Trong bảng chung | Trong bảng subtype | Trong bảng concrete |
| Truy vấn đa hình | Thường đơn giản | Có thể nhiều JOIN | Có thể UNION |
| FK trỏ Product chung | Dễ hơn | Dễ hơn | Khó hơn |
| Constraint riêng subtype | Khó hơn, thường cần điều kiện | Tự nhiên hơn ở bảng con | Tự nhiên ở bảng concrete |
| Thêm subtype | Thêm cột/discriminator | Thêm bảng subtype | Thêm bảng concrete |
| Đánh đổi chính | Bảng rộng, cột nullable | JOIN và SQL nhiều bảng | Trùng cấu trúc, truy vấn đa hình |

Không thể chọn chiến lược chỉ bằng một quy tắc “JOINED luôn chuẩn hơn” hay “SINGLE_TABLE luôn nhanh hơn”. Phải xét lượng dữ liệu, loại truy vấn chính, index, số subtype và database cụ thể.

## 4. Ví dụ JPA inheritance hoàn chỉnh: PhysicalProduct và DigitalProduct

Giả sử sau phân tích, nghiệp vụ đã xác nhận:

- Mỗi Product là **chính xác một loại** vật lý hoặc số.
- Phân loại đó ổn định, không đổi tùy ý sau khi sản phẩm được tạo.
- Mọi Product có SKU, tên, giá.
- Loại vật lý bắt buộc có khối lượng.
- Loại số bắt buộc có đường dẫn tài nguyên.
- Các màn hình chung thường truy vấn Product bất kể loại.
- Các thuộc tính riêng đủ khác nhau để cân nhắc JOINED.

### 4.1. Root entity

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Inheritance;
import jakarta.persistence.InheritanceType;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.math.BigDecimal;

@Entity
@Table(name = "product")
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Product {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "product_id_generator"
    )
    @SequenceGenerator(
        name = "product_id_generator",
        sequenceName = "product_seq",
        allocationSize = 1
    )
    private Long id;

    @Version
    private long version;

    @Column(name = "sku", nullable = false, unique = true, length = 40)
    private String sku;

    @Column(name = "name", nullable = false, length = 200)
    private String name;

    @Column(name = "price", nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    protected Product() {
        // Constructor cho JPA.
    }

    protected Product(String sku, String name, BigDecimal price) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU is required");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name is required");
        }
        if (price == null || price.signum() < 0) {
            throw new IllegalArgumentException("Invalid price");
        }

        this.sku = sku;
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public abstract String fulfillmentDescription();
}
~~~

`Product` là một `@Entity` dù có từ khóa `abstract`. `@Id` đặt ở root; tất cả subtype chia sẻ mô hình khóa này. `@Version` là metadata JPA dùng cho optimistic locking, còn `price` chỉ được validate ở constructor làm ví dụ; ứng dụng thực phải bảo vệ invariant khi thay đổi giá ở các phương thức khác.

`SEQUENCE` trong ví dụ phù hợp với DB có sequence như PostgreSQL. Khi triển khai trên DB khác, chọn generator và migration tương thích.

### 4.2. Subclass PhysicalProduct

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.PrimaryKeyJoinColumn;
import jakarta.persistence.Table;

import java.math.BigDecimal;

@Entity
@Table(name = "physical_product")
@PrimaryKeyJoinColumn(name = "product_id")
public class PhysicalProduct extends Product {

    @Column(name = "shipping_weight_grams", nullable = false)
    private long shippingWeightGrams;

    protected PhysicalProduct() {
    }

    public PhysicalProduct(
            String sku, String name, BigDecimal price,
            long shippingWeightGrams) {

        super(sku, name, price);

        if (shippingWeightGrams <= 0) {
            throw new IllegalArgumentException(
                "Shipping weight must be positive"
            );
        }

        this.shippingWeightGrams = shippingWeightGrams;
    }

    @Override
    public String fulfillmentDescription() {
        return "Physical shipment";
    }

    public long getShippingWeightGrams() {
        return shippingWeightGrams;
    }
}
~~~

### 4.3. Subclass DigitalProduct

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.PrimaryKeyJoinColumn;
import jakarta.persistence.Table;

import java.math.BigDecimal;

@Entity
@Table(name = "digital_product")
@PrimaryKeyJoinColumn(name = "product_id")
public class DigitalProduct extends Product {

    @Column(name = "download_location", nullable = false, length = 500)
    private String downloadLocation;

    protected DigitalProduct() {
    }

    public DigitalProduct(
            String sku, String name, BigDecimal price,
            String downloadLocation) {

        super(sku, name, price);

        if (downloadLocation == null || downloadLocation.isBlank()) {
            throw new IllegalArgumentException(
                "Download location is required"
            );
        }

        this.downloadLocation = downloadLocation;
    }

    @Override
    public String fulfillmentDescription() {
        return "Digital download";
    }
}
~~~

Cả hai subclass không cần `@Id` mới. `@PrimaryKeyJoinColumn(name = "product_id")` chỉ định cột khóa chính ở bảng subtype dùng để join đến khóa của root entity.

### 4.4. SQL và persistence

Schema minh họa:

~~~sql
CREATE SEQUENCE product_seq
    START WITH 1 INCREMENT BY 1;

CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    sku VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(14,2) NOT NULL
);

CREATE TABLE physical_product (
    product_id BIGINT PRIMARY KEY REFERENCES product(id),
    shipping_weight_grams BIGINT NOT NULL
);

CREATE TABLE digital_product (
    product_id BIGINT PRIMARY KEY REFERENCES product(id),
    download_location VARCHAR(500) NOT NULL
);
~~~

Tạo một subtype:

~~~java
PhysicalProduct keyboard = new PhysicalProduct(
    "KEYBOARD-01",
    "Bàn phím cơ",
    new BigDecimal("1250000.00"),
    950
);

entityManager.persist(keyboard);
~~~

Provider sẽ ghi dữ liệu chung vào `product` và dữ liệu riêng vào `physical_product`, trong transaction. Không phải tạo một object Product rồi thêm một object PhysicalProduct khác: một `PhysicalProduct` đã là một Product về mặt Java/JPA.

### 4.5. Truy vấn đa hình

~~~java
List<Product> products = entityManager.createQuery(
    "SELECT p FROM Product p ORDER BY p.name",
    Product.class
).getResultList();

for (Product product : products) {
    System.out.println(
        product.getName() + " - " +
        product.fulfillmentDescription()
    );
}
~~~

Không cần `instanceof` chỉ để gọi hành vi chung của mọi Product. JPQL cũng có thể lọc theo entity type:

~~~java
List<Product> physical = entityManager.createQuery(
    "SELECT p FROM Product p " +
    "WHERE TYPE(p) = PhysicalProduct",
    Product.class
).getResultList();
~~~

Hoặc truy vấn trực tiếp subtype:

~~~java
List<PhysicalProduct> heavyProducts =
    entityManager.createQuery(
        "SELECT p FROM PhysicalProduct p " +
        "WHERE p.shippingWeightGrams > :grams",
        PhysicalProduct.class
    )
    .setParameter("grams", 1000L)
    .getResultList();
~~~

Việc root query có cần JOIN các bảng subtype phụ thuộc provider và chiến lược mapping. Với danh sách lớn chỉ cần tên/giá, có thể dùng projection/DTO thay vì luôn tải full entity.

## 5. Khi yêu cầu có thể kết hợp: Composition phù hợp hơn

Giờ xem yêu cầu khác:

> Một khóa học có thể bán bản ebook, gói tài liệu in hoặc cả hai. Những hình thức phân phối có thể được bật và tắt độc lập.

Nếu dùng subclass loại trừ nhau, sẽ phải phát minh `HybridProduct`. Khi thêm những hình thức khác như nhận hàng tại quầy, gia hạn, thuê bao..., số tổ hợp subtype tăng nhanh:

~~~text
PhysicalProduct
DigitalProduct
HybridProduct
DigitalPickupProduct
PhysicalSubscriptionProduct
...
~~~

Đây là dấu hiệu hierarchy đang biểu diễn **nhiều trục tính năng độc lập**. Một Product duy nhất có collection phương án phân phối thường rõ ràng hơn:

~~~text
Product
   |
   +-- FulfillmentOption(SHIPPING)
   +-- FulfillmentOption(DOWNLOAD)
   +-- FulfillmentOption(PICKUP)
~~~

Lợi ích:

- Một Product có nhiều option đồng thời.
- Bật/tắt option là cập nhật dữ liệu, không phải biến Product từ subclass này sang subclass khác.
- Có thể thêm metadata cho từng option: trạng thái, thời điểm hiệu lực, khu vực, giá bổ sung.
- Identity của Product được giữ ổn định.

Không phải composition giúp “không bao giờ cần migration”; nếu option mới có dữ liệu chuyên biệt, schema có thể vẫn phải thay đổi. Nhưng mô hình không buộc mọi tổ hợp chức năng trở thành một subtype của Product.

## 6. Composition với value object: `@Embeddable`

Một thành phần chỉ chứa dữ liệu và không cần identity có thể được nhúng vào entity.

Ví dụ một kiện hàng có kích thước:

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class Dimensions {

    @Column(name = "length_mm")
    private Integer lengthMm;

    @Column(name = "width_mm")
    private Integer widthMm;

    @Column(name = "height_mm")
    private Integer heightMm;

    protected Dimensions() {
    }

    public Dimensions(
            Integer lengthMm,
            Integer widthMm,
            Integer heightMm) {

        if (lengthMm == null || widthMm == null || heightMm == null
                || lengthMm <= 0 || widthMm <= 0 || heightMm <= 0) {
            throw new IllegalArgumentException(
                "All dimensions must be positive"
            );
        }

        this.lengthMm = lengthMm;
        this.widthMm = widthMm;
        this.heightMm = heightMm;
    }
}
~~~

Trong entity:

~~~java
@Entity
@Table(name = "parcel")
public class Parcel {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Embedded
    private Dimensions dimensions;

    protected Parcel() {
    }
}
~~~

Schema có thể chứa:

~~~sql
CREATE TABLE parcel (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    length_mm INTEGER,
    width_mm INTEGER,
    height_mm INTEGER
);
~~~

`Dimensions` không phải entity riêng, không có `@Id` và không được truy vấn như một entity root. Nó là giá trị của Parcel. Điều này tự nhiên hơn `Parcel extends Dimensions`, bởi một kiện hàng **có kích thước**, không **là một kích thước**.

### 6.1. Dùng cùng embeddable nhiều lần

Một kiện hàng có kích thước trước và sau đóng gói:

~~~java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "lengthMm",
        column = @Column(name = "original_length_mm")
    ),
    @AttributeOverride(
        name = "widthMm",
        column = @Column(name = "original_width_mm")
    ),
    @AttributeOverride(
        name = "heightMm",
        column = @Column(name = "original_height_mm")
    )
})
private Dimensions originalDimensions;

@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "lengthMm",
        column = @Column(name = "packed_length_mm")
    ),
    @AttributeOverride(
        name = "widthMm",
        column = @Column(name = "packed_width_mm")
    ),
    @AttributeOverride(
        name = "heightMm",
        column = @Column(name = "packed_height_mm")
    )
})
private Dimensions packedDimensions;
~~~

`@AttributeOverride` thay tên cột để tránh hai lần nhúng ghi vào cùng một cột. Đây là cách dùng composition để tái sử dụng một khái niệm giá trị mà không cần class inheritance.

### 6.2. Khi nào embeddable không đủ?

Khi thành phần cần:

- Có identity riêng để được entity khác tham chiếu.
- Có quyền truy cập hoặc quy tắc lifecycle riêng.
- Có nhiều bản ghi theo thời gian.
- Được quản lý/cập nhật độc lập.
- Cần nằm ở bảng riêng vì mô hình quan hệ, không chỉ vì số field.

Lúc đó, entity liên kết có thể phù hợp hơn value object nhúng.

## 7. Composition bằng `@OneToOne`: Một entity phần mở rộng

Giả sử thông số vật lý là một phần mở rộng riêng của Product:

~~~text
product                       physical_details
-----------------------       -------------------------------
id (PK)               <-----  product_id (PK và FK)
sku                             shipping_weight_grams
name                            package_description
~~~

Nếu mỗi Product có tối đa một PhysicalDetails, một liên kết one-to-one có thể phù hợp.

### 7.1. Parent entity

~~~java
@Entity
@Table(name = "product")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @OneToOne(
        mappedBy = "product",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private PhysicalDetails physicalDetails;

    protected Product() {
    }

    public void addPhysicalDetails(long weightGrams) {
        if (physicalDetails != null) {
            throw new IllegalStateException(
                "Physical details already exist"
            );
        }
        physicalDetails = new PhysicalDetails(this, weightGrams);
    }
}
~~~

### 7.2. Entity phần mở rộng dùng shared PK

~~~java
@Entity
@Table(name = "physical_details")
public class PhysicalDetails {

    @Id
    private Long id;

    @MapsId
    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Column(name = "shipping_weight_grams", nullable = false)
    private long shippingWeightGrams;

    protected PhysicalDetails() {
    }

    PhysicalDetails(Product product, long weightGrams) {
        if (product == null || weightGrams <= 0) {
            throw new IllegalArgumentException(
                "Invalid physical details"
            );
        }
        this.product = product;
        this.shippingWeightGrams = weightGrams;
    }
}
~~~

`@MapsId` cho phép entity con lấy ID từ Product. Khóa `physical_details.product_id` vừa là PK vừa là FK, nhưng **Product và PhysicalDetails là hai entity**, khác với `Product` và `PhysicalProduct` trong hierarchy JOINED.

### 7.3. Điểm khác nhau với inheritance JOINED

| Tiêu chí | `PhysicalProduct extends Product` + JOINED | `Product` có `PhysicalDetails` |
|---|---|---|
| Số entity Java | Một entity thuộc subtype | Hai entity riêng |
| Quan hệ class | *is-a* | *has-a* |
| PK/FK giữa hai bảng | Phần của chiến lược inheritance | Phần của association |
| Có thể gỡ phần thông số mà Product vẫn giữ nguyên kiểu? | Không phải thao tác đổi subtype thông thường | Có thể, theo lifecycle/orphanRemoval |
| Truy vấn chung Product | Polymorphic entity hierarchy | Một entity Product với association |
| Bộ sinh ID | Ở entity root | Product có ID; Details có thể `@MapsId` |
| Cascade giữa hai object | Không có association cha–subclass | Có thể cấu hình cascade/orphanRemoval |

**Schema giống không có nghĩa domain model giống.** Cùng có bảng gốc và bảng chứa PK/FK, nhưng inheritance là một entity có subtype, còn composition là các entity có liên kết.

### 7.4. Nếu component không cần bảng riêng?

Có thể cân nhắc `@Embedded`. Nếu chỉ muốn chia một entity ra nhiều bảng vật lý mà không cần entity thành phần có lifecycle riêng, cân nhắc `@SecondaryTable`. Việc tạo hai entity chỉ vì muốn “tách cột” có thể tăng độ phức tạp không cần thiết.

## 8. Composition bằng `@OneToMany`: Một sản phẩm có nhiều khả năng

Với nhiều hình thức fulfillment, tạo entity `FulfillmentOption`:

~~~java
public enum FulfillmentType {
    SHIPPING,
    DOWNLOAD,
    PICKUP
}
~~~

~~~java
@Entity
@Table(
    name = "fulfillment_option",
    uniqueConstraints = @UniqueConstraint(
        columnNames = {"product_id", "fulfillment_type"}
    )
)
public class FulfillmentOption {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Enumerated(EnumType.STRING)
    @Column(
        name = "fulfillment_type",
        nullable = false,
        length = 20
    )
    private FulfillmentType type;

    @Column(nullable = false)
    private boolean active;

    protected FulfillmentOption() {
    }

    FulfillmentOption(Product product, FulfillmentType type) {
        if (product == null || type == null) {
            throw new IllegalArgumentException(
                "Product and type are required"
            );
        }
        this.product = product;
        this.type = type;
        this.active = true;
    }

    public FulfillmentType getType() {
        return type;
    }

    public void deactivate() {
        this.active = false;
    }
}
~~~

Phía Product:

~~~java
@OneToMany(
    mappedBy = "product",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<FulfillmentOption> fulfillmentOptions =
    new ArrayList<>();

public void addFulfillmentOption(FulfillmentType type) {
    boolean exists = fulfillmentOptions.stream()
        .anyMatch(option -> option.getType() == type);

    if (exists) {
        throw new IllegalStateException(
            "Fulfillment type already exists"
        );
    }

    fulfillmentOptions.add(new FulfillmentOption(this, type));
}
~~~

Ưu điểm của mô hình:

- Một Product có nhiều option cùng lúc.
- Tắt DOWNLOAD không làm Product đổi class.
- Quy tắc “mỗi Product chỉ có tối đa một option theo type” được bảo vệ thêm bằng UNIQUE constraint ở DB.
- Nếu option có metadata riêng theo thời gian, có thể mở rộng entity phụ thuộc.

`CascadeType.ALL` và `orphanRemoval = true` chỉ là lựa chọn minh họa khi FulfillmentOption phụ thuộc vòng đời Product. Với entity dùng chung, không tự động cascade REMOVE. Không nên hiểu composition đồng nghĩa luôn phải cascade mọi thao tác.

## 9. `@MappedSuperclass`: Tái sử dụng field không đồng nghĩa phân loại entity

Một class cha chỉ để chia sẻ metadata và field không nhất thiết phải là entity root.

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.Version;

import java.time.Instant;

@MappedSuperclass
public abstract class AuditedRecord {

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at")
    private Instant updatedAt;

    @Version
    private long version;

    protected AuditedRecord() {
    }
}
~~~

Hai entity hoàn toàn khác nhau có thể kế thừa các field đó:

~~~java
@Entity
@Table(name = "product")
public class Product extends AuditedRecord {

    @Id
    private Long id;
}
~~~

~~~java
@Entity
@Table(name = "warehouse")
public class Warehouse extends AuditedRecord {

    @Id
    private Long id;
}
~~~

Cả Product và Warehouse có mapping các cột audit ở bảng của chúng. Nhưng `AuditedRecord` **không phải entity** và **không có một bảng riêng** chỉ vì được gắn `@MappedSuperclass`.

JPQL sau không hợp lệ trong mô hình đó:

~~~java
// AuditedRecord là @MappedSuperclass, không phải entity root:
entityManager.createQuery(
    "SELECT x FROM AuditedRecord x", AuditedRecord.class
);
~~~

### 9.1. Entity superclass và mapped superclass

| Đặc điểm | `@Entity` root | `@MappedSuperclass` |
|---|---|---|
| Bản thân là managed entity type | Có | Không |
| Có thể làm JPQL entity root | Có | Không |
| Có thể có association trỏ tới superclass | Có, nếu association target là entity | Không như một entity target |
| Subclass kế thừa field mapping | Có | Có |
| Có entity inheritance strategy | Có thể dùng `@Inheritance` | Không phải entity hierarchy root |
| Có bảng riêng | Theo inheritance strategy | Không |
| Mục tiêu | Phân loại nghiệp vụ/đa hình | Tái sử dụng metadata và field |

Nếu chỉ chung `createdAt` và `updatedAt`, tạo một entity cha có polymorphic query có thể không mang ý nghĩa nghiệp vụ. `@MappedSuperclass` thường phù hợp hơn.

Tuy nhiên, một value object như `Address`, `Money` hoặc `Dimensions` có thể nên dùng `@Embeddable` thay vì kế thừa field, vì “Product có một bộ kích thước” diễn đạt ý nghĩa domain rõ hơn “Product extends Dimensions”.

## 10. Vai trò thay đổi theo thời gian: Đừng ép vào subclass entity

Yêu cầu:

> Một UserAccount có thể vừa là Buyer vừa là Seller; về sau có thể được cấp hoặc thu hồi quyền Admin.

Thiết kế subclass ban đầu:

~~~text
UserAccount
    +-- BuyerAccount
    +-- SellerAccount
    +-- AdminAccount
~~~

khó biểu diễn khi một tài khoản có nhiều role đồng thời, hoặc role thay đổi mà identity user không thay đổi.

Composition phù hợp hơn:

~~~text
UserAccount 1 ----- N UserRole N ----- 1 Role
                            |
                            +-- grantedAt
                            +-- expiresAt
                            +-- grantedBy
~~~

Ví dụ entity liên kết:

~~~java
@Entity
@Table(name = "user_role")
public class UserRole {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private UserAccount user;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "role_id", nullable = false)
    private Role role;

    @Column(name = "granted_at", nullable = false)
    private Instant grantedAt;

    protected UserRole() {
    }
}
~~~

Đây là một association có metadata riêng của việc cấp quyền. Nếu không cần metadata hoặc entity Role riêng, một tập enum role cũng có thể đủ; quyết định phụ thuộc nghiệp vụ.

**Vai trò, trạng thái workflow và tính năng bật/tắt thường thay đổi trong vòng đời entity.** Không nên mặc định biến chúng thành subclass.

## 11. Chỉ khác một giá trị loại: Có thể chưa cần inheritance

Một hệ thống thông báo có ba kênh EMAIL, SMS, PUSH. Nếu cả ba có cùng cấu trúc lưu trữ và không có hành vi persistence chuyên biệt, một enum trên entity có thể là đủ:

~~~java
public enum NotificationChannel {
    EMAIL,
    SMS,
    PUSH
}
~~~

~~~java
@Entity
@Table(name = "notification")
public class Notification {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(name = "channel", nullable = false, length = 20)
    private NotificationChannel channel;

    @Column(name = "message", nullable = false, length = 500)
    private String message;

    protected Notification() {
    }
}
~~~

Không cần ngay lập tức tạo `EmailNotification`, `SmsNotification` và `PushNotification` chỉ vì có nhiều giá trị enum. Nếu trong tương lai từng kênh phát triển dữ liệu/behavior khác biệt nhiều, hãy đánh giá lại inheritance hoặc composition ở tầng phù hợp.

**Phân biệt:** một trường enum `channel` là dữ liệu nghiệp vụ. `@DiscriminatorColumn` của inheritance là metadata dùng để xác định subtype khi provider tải entity. Hai cơ chế có thể có bề ngoài tương tự trong bảng nhưng ý nghĩa ORM khác nhau.

## 12. Composition với Strategy Pattern khi khác biệt thuộc về hành vi

Không phải khác biệt hành vi nào cũng là một loại entity persistent. Ví dụ chính sách tính phí giao hàng thay đổi theo chiến dịch hoặc nhà vận chuyển.

~~~java
public interface ShippingFeePolicy {

    BigDecimal calculateFee(
        BigDecimal orderValue,
        long weightGrams
    );
}
~~~

~~~java
public final class StandardShippingFeePolicy
        implements ShippingFeePolicy {

    @Override
    public BigDecimal calculateFee(
            BigDecimal orderValue, long weightGrams) {

        if (weightGrams <= 0) {
            throw new IllegalArgumentException(
                "Weight must be positive"
            );
        }

        return new BigDecimal("30000.00");
    }
}
~~~

~~~java
public final class FreeShippingPolicy
        implements ShippingFeePolicy {

    private final BigDecimal threshold;

    public FreeShippingPolicy(BigDecimal threshold) {
        this.threshold = threshold;
    }

    @Override
    public BigDecimal calculateFee(
            BigDecimal orderValue, long weightGrams) {

        return orderValue.compareTo(threshold) >= 0
            ? BigDecimal.ZERO
            : new BigDecimal("30000.00");
    }
}
~~~

Ứng dụng có thể chọn implementation phù hợp bằng dependency injection, cấu hình hoặc một service chuyên trách. Entity Product hoặc Order không cần đổi subclass khi chính sách giao hàng thay đổi.

Nếu chính sách cần được lưu ở DB, xác định dữ liệu cấu hình nào là entity hoặc value object; object thực thi thuật toán không bắt buộc phải là entity JPA.

## 13. Lifecycle và identity: Khác biệt bản chất giữa hai mô hình

### 13.1. Inheritance: Một entity, có thể nhiều bảng

Với `PhysicalProduct extends Product` và JOINED:

- `PhysicalProduct` là một entity với một identity.
- Dữ liệu của nó có thể trải qua bảng `product` và `physical_product`.
- Không có cascade JPA giữa hai class như thể chúng là hai entity có association.
- Query root `Product` có thể trả instance `PhysicalProduct`.
- Không thể xử lý một thao tác đổi subtype của managed entity như một setter đơn giản.

Nếu một PhysicalProduct phải trở thành DigitalProduct trong một quy trình thường xuyên, đây là tín hiệu cần xem lại mô hình. Đổi discriminator hoặc di chuyển dòng giữa các bảng bằng SQL thủ công có thể ảnh hưởng persistence context, identity, constraint và lịch sử.

### 13.2. Composition: Nhiều entity có quan hệ

Với Product và PhysicalDetails:

- Product và PhysicalDetails là hai entity, dù có thể dùng chung PK qua `@MapsId`.
- Thêm/bớt thành phần là thay đổi quan hệ và vòng đời component.
- Có thể định nghĩa cascade, orphanRemoval và fetch.
- Product giữ nguyên class Java khi thêm thông số vật lý.
- Có thể thay đổi metadata của component trong transaction phù hợp.

Nếu component được dùng chung giữa nhiều aggregate, phải xem lại ownership: xóa Product không nhất thiết xóa entity dùng chung đó.

### 13.3. Cascade không được suy ra từ “có quan hệ”

Ví dụ:

~~~java
@OneToOne(
    mappedBy = "product",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private PhysicalDetails physicalDetails;
~~~

Có thể phù hợp khi PhysicalDetails phụ thuộc hoàn toàn Product.

Nhưng:

~~~java
@ManyToOne
private Supplier supplier;
~~~

không nên mặc định có `cascade = REMOVE` chỉ vì Product “có một Supplier”. Supplier có vòng đời độc lập, có thể được tham chiếu bởi nhiều Product.

## 14. Truy vấn và hiệu năng khi chọn inheritance hoặc composition

### 14.1. Polymorphic query

~~~java
List<Product> products = entityManager.createQuery(
    "SELECT p FROM Product p",
    Product.class
).getResultList();
~~~

Tùy strategy, provider có thể:

- Đọc một bảng với discriminator (`SINGLE_TABLE`).
- JOIN bảng gốc và bảng subtype (`JOINED`).
- UNION nhiều bảng (`TABLE_PER_CLASS`).

Nếu báo cáo chỉ cần SKU và giá, việc tải đầy đủ entity subtype có thể tốn chi phí không cần thiết. Có thể dùng DTO projection, query subtype cụ thể hoặc query được thiết kế theo màn hình.

### 14.2. Composition và lazy loading

Một Product có collection `fulfillmentOptions`:

~~~java
@OneToMany(mappedBy = "product", fetch = FetchType.LAZY)
private List<FulfillmentOption> fulfillmentOptions;
~~~

Trong nhiều trường hợp, query Product không cần tải toàn bộ option ngay. Nhưng khi duyệt hàng trăm Product rồi truy cập option từng cái, có thể phát sinh N+1 queries.

Khi màn hình cần cả option:

~~~java
List<Product> products = entityManager.createQuery(
    "SELECT DISTINCT p " +
    "FROM Product p LEFT JOIN FETCH p.fulfillmentOptions",
    Product.class
).getResultList();
~~~

Fetch join collection có thể nhân số dòng SQL và không phù hợp để phân trang trực tiếp một tập Product lớn. Cần thiết kế truy vấn hai bước hoặc projection theo use case. Không nên đặt mọi association EAGER chỉ để tránh một N+1, vì sẽ kéo theo tải dữ liệu không cần thiết ở các use case khác.

### 14.3. DTO cho API

Một API sản phẩm có thể trả:

~~~java
public record ProductSummaryDto(
    Long id,
    String sku,
    String name,
    BigDecimal price,
    List<String> supportedFulfillmentTypes
) {}
~~~

Hợp đồng API không nhất thiết phải bộc lộ hierarchy JPA hoặc toàn bộ đồ thị association. Điều này giúp giảm rủi ro vòng lặp JSON, lazy loading ngoài transaction và payload vượt nhu cầu.

## 15. Constraint của DB cần đi cùng mô hình

### 15.1. SINGLE_TABLE và NOT NULL theo subtype

`PhysicalProduct.shippingWeightGrams` bắt buộc nhưng `DigitalProduct` không có giá trị đó. Nếu mọi subtype cùng một bảng, không thể đặt `NOT NULL` toàn bảng cho cột chỉ có ý nghĩa với một subtype.

Có thể dùng validation domain và constraint có điều kiện theo discriminator. Nếu yêu cầu cột riêng phải NOT NULL cứng ở schema, JOINED có thể thuận tiện hơn.

### 15.2. JOINED và toàn vẹn gốc–con

FK từ `physical_product.product_id` tới `product.id` ngăn row subtype tham chiếu root không tồn tại. Nhưng chỉ FK chiều con→cha không tự bảo đảm mọi row root luôn có đúng một row subtype trong mọi đường ghi SQL. Provider quản lý hierarchy khi dùng JPA; nếu database được ghi trực tiếp từ hệ thống khác, cần xem thêm constraint và quyền ghi.

### 15.3. TABLE_PER_CLASS và identity toàn hierarchy

Không có bảng gốc chung khiến tham chiếu đến một Product bất kỳ trở nên phức tạp. Sinh ID riêng lẻ có thể cần phối hợp để tránh xung đột ngữ nghĩa identity trong polymorphic query tùy provider. Đừng mặc định mỗi bảng dùng một identity generator riêng luôn phù hợp.

### 15.4. Composition và FK/UNIQUE

Một one-to-one dùng FK riêng cần UNIQUE để bảo vệ tối đa một component cho một parent. Một one-to-many cần FK. Nếu mỗi Product có tối đa một FulfillmentOption của mỗi loại:

~~~sql
UNIQUE (product_id, fulfillment_type)
~~~

là constraint giúp bảo vệ invariant khi nhiều request xử lý đồng thời. `Set` trong Java hoặc kiểm tra danh sách trước khi thêm không thay thế constraint database.

## 16. Tiến hóa schema và migration

Quyết định inheritance hay composition thường khó thay đổi sau khi dữ liệu đã được lưu lâu dài.

### 16.1. Thêm subtype trong SINGLE_TABLE

Có thể phải:

1. Thêm giá trị discriminator.
2. Thêm các cột dành riêng cho subtype mới.
3. Cập nhật constraint có điều kiện.
4. Cập nhật query/DTO và logic nghiệp vụ.
5. Kiểm tra code phiên bản cũ nếu deployment diễn ra theo nhiều bước.

### 16.2. Thêm subtype trong JOINED

Thường phải tạo bảng subtype mới với PK/FK tới root, rồi đưa subtype vào persistence unit. Những truy vấn superclass và báo cáo cần hiểu thêm loại mới. SQL SELECT đa hình có thể trở nên phức tạp hơn.

### 16.3. Thêm subtype trong TABLE_PER_CLASS

Cần thêm bảng concrete mới và xem ảnh hưởng đến truy vấn tổng hợp/UNION, cách cấp ID, các ràng buộc duy nhất toàn hệ và các foreign key tham chiếu.

### 16.4. Chuyển từ inheritance sang composition

Không thể chỉ xóa `extends` rồi thêm `@OneToOne` và giả định dữ liệu tự chuyển. Cần kế hoạch:

- Kiểm kê PK, FK, discriminator và các bảng subtype.
- Thiết kế các bảng component/association mới.
- Backfill dữ liệu hiện có.
- Đổi mapping Java, repository, truy vấn JPQL và DTO.
- Xử lý optimistic locking, audit và lịch sử.
- Kiểm tra tương thích khi chạy đồng thời nhiều phiên bản ứng dụng.
- Thực hiện migration có kiểm soát, có phương án phục hồi khi lỗi.

### 16.5. Composition cũng có chi phí thay đổi

Nếu FulfillmentOption có thêm kiểu cần hàng chục field chuyên biệt, có thể phải thêm entity detail hoặc mapping riêng. Composition không bảo đảm loại bỏ mọi migration, nhưng có thể tránh nhu cầu tạo subclass cho từng tổ hợp đặc điểm.

## 17. Những dấu hiệu hierarchy đang có vấn đề

### 17.1. Phải ném exception trong subtype cho hành vi superclass

~~~java
public abstract class Product {
    public abstract void shipPhysicalPackage();
}

public class DigitalProduct extends Product {
    @Override
    public void shipPhysicalPackage() {
        throw new UnsupportedOperationException(
            "Digital product cannot be shipped physically"
        );
    }
}
~~~

Nếu không phải mọi Product đều có thể vận chuyển vật lý, hợp đồng superclass có thể sai. Có thể tách capability `Shippable` hoặc dùng composition với FulfillmentOption.

### 17.2. Class tên theo tổ hợp nhiều cờ

~~~text
PremiumPhysicalDiscountedProduct
PremiumDigitalDiscountedProduct
RegularPhysicalDiscountedProduct
RegularDigitalFullPriceProduct
~~~

Premium, physical/digital và discount là các trục phân loại có thể độc lập. Tổ hợp chúng thành class thường dẫn đến bùng nổ số lượng subtype. Một số trục nên thành property/component/strategy.

### 17.3. Liên tục kiểm tra `instanceof` ở mọi service

~~~java
if (product instanceof PhysicalProduct physical) {
    // ...
} else if (product instanceof DigitalProduct digital) {
    // ...
}
~~~

Một số trường hợp kiểm tra subtype là bình thường. Nhưng nếu mọi service lặp cùng chuỗi ép kiểu, cần xem có thể đặt hành vi đa hình phù hợp, dùng strategy hoặc chuyển đặc điểm sang association hay không.

Không nên nhồi logic gọi API, gửi email hoặc kết nối thanh toán vào entity chỉ để loại bỏ `instanceof`; ranh giới giữa domain và hạ tầng vẫn cần rõ ràng.

### 17.4. Một field trạng thái bị diễn đạt thành subclass

Ví dụ đơn hàng chuyển từ DRAFT sang CONFIRMED rồi SHIPPED. Nếu dùng subclass `DraftOrder`, `ConfirmedOrder` và `ShippedOrder`, chuyển trạng thái tương đương muốn đổi runtime class của managed entity. Một `Order` có enum status và state transition rule thường tự nhiên hơn.

## 18. Kết hợp cả inheritance và composition trong một hệ thống

Hai phương pháp không loại trừ nhau.

~~~text
                      InsurancePolicy
                         /       \
                        /         \
                  LifePolicy    VehiclePolicy
                      |              |
                      | has-many     | has-many
                      v              v
                 Beneficiary     CoveredVehicle
~~~

Nếu LifePolicy và VehiclePolicy thực sự có bản chất, hợp đồng và constraint khác nhau một cách ổn định, entity inheritance có thể hợp lý. Mỗi subtype lại sử dụng composition cho những thành phần riêng có vòng đời, dữ liệu hoặc khả năng thay đổi.

Mục tiêu là dùng **kế thừa cho trục loại nghiệp vụ thực sự**, và dùng **composition cho các phần cấu thành hoặc các khả năng có thể kết hợp**.

## 19. Quy trình ra quyết định thực hành

### Bước 1: Viết câu nghiệp vụ không chứa annotation

Ví dụ: “Một đơn hàng có phương thức vận chuyển có thể đổi trước khi xác nhận.” Đừng viết ngay `ExpressOrder extends Order`.

### Bước 2: Kiểm tra *is-a* và tính thay thế

Các loại con có thực sự là biến thể của entity cha với hợp đồng chung không? Một subtype có thể thay thế superclass trong các nghiệp vụ chung không?

### Bước 3: Kiểm tra đặc điểm có thể kết hợp và thay đổi

Nếu một đối tượng có thể có đồng thời nhiều khả năng, hoặc thay đổi loại theo thời gian, composition hay trạng thái thường phù hợp hơn subclass.

### Bước 4: Kiểm tra có cần identity riêng của thành phần không

- Không cần ID: `@Embeddable`.
- Cần entity phụ thuộc 1:1: `@OneToOne`, có thể `@MapsId`.
- Cần nhiều entity con: `@OneToMany`.
- Cần tham chiếu entity độc lập: `@ManyToOne`.
- Chỉ tái sử dụng field chung: `@MappedSuperclass`.

### Bước 5: Nếu dùng inheritance, chọn strategy bằng schema/query

- `SINGLE_TABLE`: ít JOIN, nhưng nhiều cột tùy subtype có thể NULL.
- `JOINED`: dữ liệu riêng ở bảng con, dễ constraint subtype, có chi phí JOIN.
- `TABLE_PER_CLASS`: bảng concrete độc lập, có thể tốn chi phí truy vấn polymorphic.

### Bước 6: Thiết kế constraint tại database

Vẽ PK, FK, UNIQUE, NOT NULL và CHECK cần thiết. Không chỉ dựa vào setter hoặc annotation Java để bảo vệ invariant trước concurrency.

### Bước 7: Xác định cascade, orphanRemoval và transaction

Thành phần có tồn tại độc lập không? Xóa parent có được xóa child không? Entity nào sở hữu FK? Cập nhật cần được thực hiện trong transaction nào?

### Bước 8: Xác định use case đọc dữ liệu

Đọc theo subtype, đọc chung, phân trang, lọc theo field riêng hay truy cập nhiều thành phần? Đo SQL/provider thực tế thay vì đoán từ sơ đồ Java.

### Bước 9: Xem chi phí thay đổi

Có thường thêm loại, thêm khả năng, thay đổi role, đổi state hoặc migration giữa các hệ thống không? Hệ mô hình càng thay đổi thường xuyên thì khả năng cập nhật bằng dữ liệu/composition càng đáng chú ý.

## 20. Bài tập áp dụng

### Bài 1. User có nhiều vai trò

Yêu cầu: một tài khoản vừa là Seller vừa là Buyer, và quyền Admin có thể được cấp/thu hồi.

**Câu hỏi:** Nên tạo `SellerUser extends UserAccount`, `BuyerUser extends UserAccount` và `AdminUser extends UserAccount` không?

**Đáp án gợi ý:** Composition với role/RoleAssignment thường phù hợp hơn, vì role có thể cùng tồn tại và thay đổi mà identity tài khoản không đổi.

### Bài 2. Kích thước của kiện hàng

Yêu cầu: Parcel có chiều dài, rộng, cao; bộ kích thước không cần truy vấn độc lập.

**Câu hỏi:** `Parcel extends Dimensions` hay `Parcel has-a Dimensions`?

**Đáp án gợi ý:** `@Embeddable Dimensions` cùng `@Embedded` ở Parcel. Parcel **có một bộ kích thước**, không **là một kích thước**.

### Bài 3. Chọn `SINGLE_TABLE` hay `JOINED`

Hai subtype có mỗi loại 30 field riêng bắt buộc và chỉ 5 field chung. Hệ thống vừa có truy vấn riêng subtype, vừa có báo cáo chung.

**Đáp án gợi ý:** JOINED đáng cân nhắc vì field riêng nhiều và các constraint subtype. SINGLE_TABLE có thể cần nhiều cột nullable và CHECK. Kết luận cuối cùng cần dựa trên query profile, số lượng dữ liệu và chi phí JOIN.

### Bài 4. Product có nhiều hình thức phân phối

Một Product vừa có ebook vừa có bản in. Người quản trị có thể tắt một hình thức.

**Đáp án gợi ý:** Composition với FulfillmentOption thường tự nhiên hơn tạo `HybridProduct`. Thêm/bớt option không đổi subtype của Product.

### Bài 5. Mapped superclass có query được không?

~~~java
@MappedSuperclass
abstract class AuditedRecord {
    Instant createdAt;
}

@Entity
class Product extends AuditedRecord {
    @Id Long id;
}
~~~

**Câu hỏi:** JPQL `SELECT x FROM AuditedRecord x` có hợp lệ không?

**Đáp án:** Không trong mô hình này, vì AuditedRecord không phải entity. Product vẫn kế thừa mapping field từ AuditedRecord.

### Bài 6. JOINED và shared-PK One-to-One

Một DB có bảng `product(id)` và `physical_details(product_id PRIMARY KEY REFERENCES product(id))`.

**Câu hỏi:** Chỉ nhìn schema có khẳng định đó là inheritance JOINED không?

**Đáp án:** Không. Schema tương tự có thể được dùng cho một subtype JOINED hoặc một entity thành phần qua `@OneToOne`/`@MapsId`. Ý nghĩa khác nhau: **một entity có subtype** hay **hai entity liên kết**.

### Bài 7. Đổi trạng thái đơn hàng

Order đi từ DRAFT → PAID → SHIPPED. Có nên tạo ba entity subtype và “chuyển” từ subclass này sang subclass khác?

**Đáp án gợi ý:** Thường không. Đây là trạng thái thay đổi trong vòng đời cùng Order. Một field status và các quy tắc transition thường phù hợp hơn; đổi subtype của managed entity không phải setter thông thường.

### Bài 8. Cột NOT NULL trong SINGLE_TABLE

Bảng Product có `shipping_weight_grams` cho PHYSICAL và `download_location` cho DIGITAL.

**Câu hỏi:** Có nên đặt cả hai là NOT NULL trên toàn bảng?

**Đáp án:** Không, vì một hàng thường chỉ sử dụng một nhóm field. Cần validation/constraint có điều kiện theo discriminator hoặc xem xét JOINED để có constraint riêng tại bảng subtype.

## 21. Nguyên tắc ghi nhớ

~~~text
Yêu cầu nghiệp vụ
        |
        v
Có thực sự là quan hệ "is-a" ổn định?
        |
        +-- Có --> Cần truy vấn và xử lý đa hình?
        |             |
        |             +-- Có --> @Entity inheritance
        |             |            |
        |             |            +-- SINGLE_TABLE
        |             |            +-- JOINED
        |             |            +-- TABLE_PER_CLASS
        |             |
        |             +-- Không --> Xem lại mục đích kế thừa:
        |                          có thể chỉ là chia sẻ mapping
        |
        +-- Không --> Đây là thành phần/khả năng?
                        |
                        +-- Value object --> @Embeddable
                        +-- Entity 1:1 --> @OneToOne
                        +-- Nhiều thành phần --> @OneToMany
                        +-- Hành vi thay thế --> Strategy/service
                        +-- Chỉ là trạng thái --> Enum/field

Chỉ muốn chia sẻ field mapping, không có entity cha nghiệp vụ?
        --> @MappedSuperclass.
~~~

Các nguyên tắc quan trọng:

1. **Kế thừa biểu diễn *is-a***, còn **composition biểu diễn *has-a* hoặc *uses-a***. Hai khái niệm không được thay thế cho nhau chỉ để tái sử dụng code.
2. **Subtype nên thể hiện loại ổn định, có hợp đồng chung**, không phải trạng thái tạm thời hoặc tập nhiều role có thể kết hợp.
3. **JPA entity inheritance** dùng `SINGLE_TABLE`, `JOINED` hoặc `TABLE_PER_CLASS`; chiến lược nào cũng tác động tới bảng, constraint và SQL.
4. **`@MappedSuperclass` tái sử dụng field mapping nhưng không tạo entity root** để truy vấn đa hình.
5. **`@Embeddable` phù hợp với value object**, còn `@OneToOne`/`@OneToMany` phù hợp với các entity thành phần có identity/vòng đời cần quản lý.
6. **JOINED khác shared-PK One-to-One:** cùng có PK/FK giữa bảng nhưng một bên là một entity có subtype, một bên là hai entity liên kết.
7. **Cascade, orphanRemoval, fetching và transaction phải chọn theo vòng đời thực**, không suy ra chỉ từ cú pháp Java.
8. **Không quên constraint DB và migration.** Một annotation đúng không tự bảo đảm mọi dữ liệu được ghi qua hệ thống khác vẫn tuân thủ invariant.
9. **Có thể phối hợp kế thừa và composition**, dùng inheritance cho trục phân loại thực sự, composition cho dữ liệu/khả năng có thể thêm bớt.
10. **Quan sát truy vấn và chi phí thay đổi** trước khi chốt mô hình có dữ liệu tồn tại lâu dài.

Một mô hình JPA tốt không phải mô hình có nhiều subclass hay ít bảng nhất, mà là mô hình giữ đúng ý nghĩa nghiệp vụ, bảo vệ được tính toàn vẹn dữ liệu và cho phép hệ thống tiến hóa mà không phải liên tục “đổi loại” các entity đã được lưu.
