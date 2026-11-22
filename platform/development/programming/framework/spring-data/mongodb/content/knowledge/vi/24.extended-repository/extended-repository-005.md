# Sinh Q-type và xây điều kiện truy vấn có kiểu

## 1. Vì sao cần Q-type khi đã có Query và Criteria?

Một dịch vụ sản phẩm có màn hình tìm kiếm theo tenant, trạng thái, khoảng giá, từ khóa, tồn kho và nhiều bộ lọc tùy chọn. Một phương thức repository suy diễn cho mỗi tổ hợp sẽ nhanh chóng tạo ra tên rất dài:

~~~java
List<ProductDocument> findByTenantIdAndActiveAndPriceMinorBetween(
    String tenantId, boolean active, long minPrice, long maxPrice
);

List<ProductDocument> findByTenantIdAndNameContainingIgnoreCase(
    String tenantId, String name
);
~~~

**MongoTemplate** cho phép xây điều kiện động bằng Criteria nhưng tên field chủ yếu vẫn được truyền bằng chuỗi:

~~~java
Criteria.where("tenantId").is(tenantId)
    .and("active").is(true)
    .and("priceMinor").gte(minPrice);
~~~

Khi đổi tên Java property **priceMinor** thành **salePriceMinor**, compiler không nhất thiết phát hiện chuỗi "priceMinor" cũ. **Querydsl** cung cấp một cách khác: sinh ra lớp **Q-type** mô tả các property Java có kiểu. Thay vì chuỗi tên field, ứng dụng dùng:

~~~java
QProductDocument p = QProductDocument.productDocument;
var predicate = p.tenantId.eq(tenantId)
    .and(p.active.isTrue())
    .and(p.priceMinor.goe(minPrice));
~~~

Nếu property bị đổi tên, mã dùng Q-type cũ sẽ không còn biên dịch sau khi Q-type được sinh lại, giúp phát hiện sớm lỗi refactor.

Bài **Sinh Q-type và xây điều kiện truy vấn có kiểu** thuộc chương **Repository mở rộng** của module **SPRING_DATA_MONGODB**. Đây là một kỹ thuật để kết nối, ánh xạ document và truy vấn MongoDB qua repository; bên cạnh đó, MongoTemplate vẫn phù hợp với aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.

Mục tiêu:

1. Hiểu **Q-type**, **Predicate**, **BooleanExpression** và **BooleanBuilder**.
2. Sinh Q-class từ MongoDB entity bằng annotation processing.
3. Cấu hình Maven và Gradle để sử dụng **MongoAnnotationProcessor** đúng cách.
4. Mở rộng repository bằng **QuerydslPredicateExecutor**.
5. Viết điều kiện động AND/OR, điều kiện theo chuỗi/số/boolean và filter tenant.
6. Phân trang, sắp xếp, đếm và kiểm tra tồn tại qua Predicate.
7. Phân biệt cách dùng Querydsl trong repository đồng bộ và reactive.
8. Kiểm thử khả năng mapping tên BSON, kiểm soát quyền và đánh giá hiệu năng.

## 2. Luồng xử lý từ @Document tới MongoDB

~~~mermaid
flowchart TD
    A["Entity ProductDocument, @Document"] --> B["MongoAnnotationProcessor khi compile"]
    B --> C["Generated QProductDocument"]
    C --> D["Predicate / BooleanBuilder"]
    D --> E["QuerydslPredicateExecutor"]
    E --> F["Spring Data MongoDB mapping"]
    F --> G["MongoDB collection products"]
~~~

| Khái niệm | Trách nhiệm |
| --- | --- |
| **Entity** | Domain object ánh xạ BSON document. |
| **Q-type** | Mã Java được sinh, biểu diễn các property path có kiểu. |
| **BooleanExpression** | Điều kiện có thể nối and/or/not. |
| **BooleanBuilder** | Gom các điều kiện tùy chọn, thay đổi được khi xây filter. |
| **Predicate** | Hợp đồng biểu thức điều kiện cho Querydsl executor. |
| **QuerydslPredicateExecutor** | Mở rộng repository đồng bộ với find, count, exists theo Predicate. |
| **ReactiveQuerydslPredicateExecutor** | Mở rộng repository reactive với Mono/Flux. |
| **MongoTemplate** | Công cụ bổ sung khi cần Query/Criteria, projection, aggregation hoặc update chuyên sâu. |

**QProductDocument không phải document lưu trong database** và không phải DTO để trả ra API. Nó là mã trung gian do annotation processor sinh trong quá trình build.

## 3. Document và entity xuyên suốt bài học

Collection **products** có một document:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenant_id: "shop-a",
  sku: "BOOK-101",
  name: "Spring Data MongoDB thực hành",
  active: true,
  priceMinor: NumberLong("159000"),
  stock: NumberInt(12),
  tags: ["JAVA", "MONGODB"]
}
~~~

Tên **tenant_id** trong BSON khác tên **tenantId** của Java, giúp minh họa vai trò mapping. Entity:

~~~java
package com.example.catalog;

import java.util.ArrayList;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "products")
public class ProductDocument {

    @Id
    private ObjectId id;

    @Field("tenant_id")
    private String tenantId;

    private String sku;
    private String name;
    private boolean active;
    private long priceMinor;
    private int stock;
    private List<String> tags = new ArrayList<>();

    protected ProductDocument() {}

    public ProductDocument(
            String tenantId, String sku, String name,
            boolean active, long priceMinor, int stock) {
        this.tenantId = tenantId;
        this.sku = sku;
        this.name = name;
        this.active = active;
        this.priceMinor = priceMinor;
        this.stock = stock;
    }

    public ObjectId getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public boolean isActive() { return active; }
    public long getPriceMinor() { return priceMinor; }
    public int getStock() { return stock; }
    public List<String> getTags() { return tags; }
    public void setTags(List<String> tags) { this.tags = tags; }
}
~~~

**@Document** xác định collection, **@Id** ánh xạ Java id vào BSON _id, còn **@Field("tenant_id")** ánh xạ Java tenantId tới BSON tenant_id.

Trong hệ thống có nhiều tenant, luôn ràng buộc điều kiện tenant từ ngữ cảnh xác thực; không cho người dùng tự lựa chọn bất kỳ tenant nào chỉ bằng việc truyền một filter.

## 4. QProductDocument được sinh như thế nào?

Annotation processor xem metadata của ProductDocument rồi sinh một class Java dạng:

~~~java
// Mã MINH HỌA cấu trúc, không phải source cần tự tạo.
public class QProductDocument extends EntityPathBase<ProductDocument> {

    public static final QProductDocument productDocument = ...;

    public final StringPath tenantId = ...;
    public final StringPath sku = ...;
    public final StringPath name = ...;
    public final BooleanPath active = ...;
    public final NumberPath<Long> priceMinor = ...;
    public final NumberPath<Integer> stock = ...;
}
~~~

Các dấu **...** là nơi annotation processor sẽ điền biểu thức/constructor thật. **Không chép đoạn minh họa này vào source để biên dịch.**

Một số đường dẫn được sinh thường có:

| Property | Nhóm đường dẫn Querydsl | Phép toán thường dùng |
| --- | --- | --- |
| name, sku, tenantId | StringPath | eq, contains, startsWithIgnoreCase |
| active | BooleanPath | isTrue, isFalse |
| priceMinor | NumberPath<Long> | goe, loe, between |
| stock | NumberPath<Integer> | gt, lt, in |
| id | Path theo kiểu ObjectId | eq và phép so sánh được hỗ trợ |
| tags | Collection/ListPath phù hợp | contains khi được serializer hỗ trợ |
| Nested supplier | Đường dẫn nested type nếu processor sinh | Truy cập field nhúng |

Trong code nghiệp vụ:

~~~java
QProductDocument product = QProductDocument.productDocument;
~~~

Instance static thường có tên dạng camelCase từ entity. Nếu tên instance/path thực khác ví dụ, hãy xem generated source thay vì tự sửa Q-class.

### 4.1. Type-safety bảo vệ điều gì?

Ví dụ đổi tên priceMinor thành salePriceMinor ở entity, rồi tái biên dịch:

~~~java
// Code còn dùng property đã đổi tên sẽ bị compiler báo lỗi:
product.priceMinor.goe(100_000L);
~~~

Nhờ đó, refactor property có khả năng phát hiện lỗi ngay ở build. Nhưng Q-type không tự bảo đảm index tồn tại, input nghiệp vụ đúng, collection chứa schema tương thích hoặc caller có quyền xem dữ liệu.

## 5. Processor đúng cho Spring Data MongoDB

**Không chỉ dùng Querydsl JPA annotation processor.** Spring Data MongoDB có processor được chỉ định rõ:

~~~text
org.springframework.data.mongodb.repository.support.MongoAnnotationProcessor
~~~

Processor này giúp sinh Q-type theo mapping MongoDB, bao gồm entity với **@Document**. Cấu hình Querydsl JPA chỉ dựa trên jakarta.persistence.Entity có thể không tạo Q-class cho MongoDB domain.

Các yếu tố cần phù hợp nhau:

- Spring Boot và Spring Data MongoDB.
- Querydsl core, mongodb, apt cùng hệ phiên bản.
- Java compiler, Maven hoặc Gradle.
- Namespace jakarta/javax của dòng thư viện tương ứng.
- MongoDB driver do Spring Data quản lý.

**Không có một con số phiên bản Querydsl duy nhất phù hợp mọi dự án.** Các ví dụ bên dưới để version trong biến build và cần điều chỉnh theo BOM/cấu hình thực tế.

## 6. Gradle: cấu hình annotation processing

Ví dụ với Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'

    implementation("com.querydsl:querydsl-mongodb:$querydslVersion") {
        exclude group: 'org.mongodb', module: 'mongo-java-driver'
    }

    annotationProcessor "com.querydsl:querydsl-apt:$querydslVersion:jakarta"
    annotationProcessor "org.springframework.data:spring-data-mongodb"

    testAnnotationProcessor "com.querydsl:querydsl-apt:$querydslVersion:jakarta"
    testAnnotationProcessor "org.springframework.data:spring-data-mongodb"
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '-processor',
        'org.springframework.data.mongodb.repository.support.MongoAnnotationProcessor'
    ]
}
~~~

**querydslVersion** là property được khai báo trong cấu hình dự án. Với Spring Boot, dependency Spring Data nên được quản lý nhất quán qua BOM hoặc plugin của dự án.

Giải thích:

1. **querydsl-mongodb** cung cấp hỗ trợ Querydsl với MongoDB.
2. Loại **mongo-java-driver** kéo theo từ Querydsl để tránh xung đột với bộ driver được Spring Data quản lý.
3. **querydsl-apt** cung cấp công cụ sinh nguồn Q-class.
4. **annotationProcessor spring-data-mongodb** đặt MongoAnnotationProcessor lên processor classpath.
5. Tùy chọn **-processor** kích hoạt processor MongoDB bằng tên đầy đủ.

### 6.1. Đường dẫn Q-class trong Gradle

Với Java plugin, source generated thường xuất hiện ở:

~~~text
build/generated/sources/annotationProcessor/java/main/
    com/example/catalog/QProductDocument.java
~~~

Hãy kiểm tra file đó sau compile. Nếu chưa có, việc thêm import QProductDocument vào repository không khiến class tự sinh.

### 6.2. Vấn đề nhiều annotation processor

Khi chỉ định **-processor** tường minh, Java compiler có thể không tự quét và chạy các annotation processor khác. Nếu dự án dùng Lombok, MapStruct hoặc processor riêng, cần cấu hình đầy đủ danh sách/đường dẫn xử lý và test build sạch.

Lỗi “không sinh mapper” hoặc “không có getter” sau khi bật Querydsl đôi khi đến từ việc thay đổi processor settings, không phải bản thân API Querydsl.

## 7. Maven: cấu hình MongoAnnotationProcessor

Các phần thiết yếu cho pom.xml:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-mongodb</artifactId>
    </dependency>

    <dependency>
        <groupId>com.querydsl</groupId>
        <artifactId>querydsl-mongodb</artifactId>
        <version>${querydsl.version}</version>
        <exclusions>
            <exclusion>
                <groupId>org.mongodb</groupId>
                <artifactId>mongo-java-driver</artifactId>
            </exclusion>
        </exclusions>
    </dependency>

    <dependency>
        <groupId>com.querydsl</groupId>
        <artifactId>querydsl-apt</artifactId>
        <version>${querydsl.version}</version>
        <classifier>jakarta</classifier>
        <scope>provided</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <annotationProcessors>
                    <annotationProcessor>
                        org.springframework.data.mongodb.repository.support.MongoAnnotationProcessor
                    </annotationProcessor>
                </annotationProcessors>
                <generatedSourcesDirectory>
                    target/generated-sources/annotations
                </generatedSourcesDirectory>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là **đoạn POM** để ghép vào dự án đã có parent/BOM, properties và cấu hình compiler; không phải một pom.xml độc lập có thể chạy ngay. Dự án phải khai báo **querydsl.version**, phù hợp với framework đang dùng.

Với Maven Compiler Plugin/JDK mới, có thể cần **annotationProcessorPaths** hoặc khai báo processor dependency theo cơ chế riêng của phiên bản compiler plugin. Nếu cấu hình đường dẫn xử lý tách biệt, phải đặt cả Querydsl APT và Spring Data MongoDB processor (cùng dependencies cần thiết) vào processor path. Không nên thêm một JPA processor rồi bỏ MongoAnnotationProcessor.

### 7.1. Thư mục generated Maven

~~~text
target/generated-sources/annotations/
    com/example/catalog/QProductDocument.java
~~~

IDE đôi khi cần reload Maven project hoặc đánh dấu thư mục trên là generated source. Nếu CLI compile thành công nhưng IDE báo không tìm thấy QProductDocument, kiểm tra cấu hình IDE trước khi sửa code.

### 7.2. Generated code không phải source viết tay

Không nên chép QProductDocument vào **src/main/java** để chữa lỗi APT. Điều đó có thể gây:

- Q-type trùng class khi compiler sinh thêm một bản.
- Q-type cũ không cập nhật sau khi rename property.
- Build CI khác với IDE đang dùng generated files cũ.

Giữ Q-type ở generated sources và có chính sách commit rõ ràng nếu dự án thực sự cần lưu generated code trong version control.

## 8. Tương thích Querydsl, fork, jakarta và driver

Tài liệu Spring Data MongoDB hiện hành ghi nhận Querydsl có nhánh fork tại **OpenFeign**, groupId **io.github.openfeign.querydsl**, được hỗ trợ theo hướng **best effort**.

Ví dụ Gradle/Maven ở trên sử dụng groupId **com.querydsl** theo tài liệu tích hợp chính thức. Nếu chuyển sang fork, phải chọn một bộ artifact và version tương thích **nhất quán**, không chỉ sửa groupId ở một dependency.

### 8.1. Lỗi namespace javax/jakarta

Nếu compile báo thiếu class jakarta hoặc javax:

1. Kiểm tra phiên bản Spring Data và Querydsl.
2. Kiểm tra classifier của **querydsl-apt**.
3. Kiểm tra compiler annotation processor path.
4. Xem dependency tree có thư viện chuyển tiếp không phù hợp.

Không chữa bằng cách thêm bừa nhiều bản querydsl-core/querydsl-apt hoặc cả hai namespace vào cùng project.

### 8.2. Xung đột MongoDB driver

Một số artifact Querydsl có thể kéo driver MongoDB cũ. Trong hệ thống Spring Boot, nên để Spring Data/BOM quản lý bộ driver thích hợp và exclude dependency cũ theo hướng dẫn. Kiểm tra dependency tree và chạy integration test sau mỗi lần nâng cấp.

## 9. Repository mở rộng bằng QuerydslPredicateExecutor

~~~java
package com.example.catalog;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface ProductRepository
        extends MongoRepository<ProductDocument, ObjectId>,
                QuerydslPredicateExecutor<ProductDocument> {
}
~~~

Repository nhận thêm các thao tác sử dụng Predicate:

~~~java
QProductDocument p = QProductDocument.productDocument;
var predicate = p.tenantId.eq("shop-a")
    .and(p.active.isTrue());

Iterable<ProductDocument> products =
    repository.findAll(predicate);

long count = repository.count(predicate);
boolean exists = repository.exists(predicate);
~~~

**Không inject QProductDocument như một Spring bean**. Nó là mã generated có instance/path được tạo để dùng trong Java:

~~~java
QProductDocument p = QProductDocument.productDocument;
~~~

QuerydslPredicateExecutor là repository extension; nó không thay thế MongoRepository và không yêu cầu bạn tự viết implementation cho các method chuẩn này.

## 10. Các điều kiện có kiểu thông dụng

~~~java
QProductDocument p = QProductDocument.productDocument;

var byName = p.name.eq("Spring Data MongoDB thực hành");
var selling = p.active.isTrue();
var inStock = p.stock.gt(0);

var priceRange = p.priceMinor.between(
    100_000L, 300_000L
);

var minPrice = p.priceMinor.goe(100_000L);
var maxPrice = p.priceMinor.loe(300_000L);

var nameSearch = p.name.containsIgnoreCase("mongodb");
var skuPrefix = p.sku.startsWithIgnoreCase("BOOK");
~~~

Tên các phép toán cần hiểu:

| Phép toán | Ý nghĩa |
| --- | --- |
| eq(value) | Bằng |
| ne(value) | Khác |
| gt(value) | Lớn hơn |
| goe(value) | Lớn hơn hoặc bằng |
| lt(value) | Nhỏ hơn |
| loe(value) | Nhỏ hơn hoặc bằng |
| between(a,b) | Trong khoảng theo semantics của kiểu/path |
| isTrue(), isFalse() | Điều kiện boolean |
| containsIgnoreCase(s) | Chứa chuỗi không phân biệt hoa/thường theo serializer hỗ trợ |
| startsWithIgnoreCase(s) | Bắt đầu bằng chuỗi theo serializer hỗ trợ |

Ghép nhiều điều kiện:

~~~java
import com.querydsl.core.types.Predicate;

Predicate predicate = p.tenantId.eq("shop-a")
    .and(p.active.isTrue())
    .and(p.priceMinor.goe(100_000L))
    .and(p.priceMinor.loe(300_000L))
    .and(p.stock.gt(0));

Iterable<ProductDocument> result =
    repository.findAll(predicate);
~~~

Querydsl giúp dùng operator phù hợp với kiểu property tại compile time. Tuy vậy, biểu thức tạo được ở Java chưa chứng minh serializer MongoDB hỗ trợ mọi toán tử trong mọi tổ hợp; cần kiểm thử runtime cho trường hợp phức tạp.

## 11. AND/OR: phải nhóm điều kiện trước khi ràng buộc tenant

Yêu cầu: product thuộc shop-a, đang bán và **(name chứa "mongo" hoặc SKU bắt đầu bằng "BOOK")**.

~~~java
QProductDocument p = QProductDocument.productDocument;

var textSearch = p.name.containsIgnoreCase("mongo")
    .or(p.sku.startsWithIgnoreCase("BOOK"));

var predicate = p.tenantId.eq("shop-a")
    .and(p.active.isTrue())
    .and(textSearch);
~~~

Diễn giải:

\[
\text{tenant = shop-a}
\land \text{active = true}
\land (\text{name contains mongo}\ \lor\ \text{sku startsWith BOOK})
\]

**Sai về bảo mật** nếu viết A.and(B).or(C) mà vô tình cho phép nhánh C vượt qua filter tenant. Hãy gom bộ lọc tùy chọn của người dùng, rồi **AND điều kiện tenant và policy ở lớp ngoài cùng**.

Nếu truy vấn cho phép nested OR nhiều cấp, nên viết unit test trên cấu trúc biểu thức và integration test bằng dữ liệu của ít nhất hai tenant.

## 12. BooleanBuilder cho bộ lọc động

Input tìm kiếm:

~~~java
public record ProductFilter(
    String keyword,
    Long minPriceMinor,
    Long maxPriceMinor,
    Boolean activeOnly
) {}
~~~

Builder:

~~~java
package com.example.catalog;

import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.Predicate;

public final class ProductPredicates {

    private ProductPredicates() {}

    public static Predicate forSearch(
            String authenticatedTenantId,
            ProductFilter filter) {

        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant required");
        }
        if (filter == null) {
            throw new IllegalArgumentException("Filter required");
        }
        if (filter.minPriceMinor() != null
                && filter.maxPriceMinor() != null
                && filter.minPriceMinor() > filter.maxPriceMinor()) {
            throw new IllegalArgumentException("Invalid price range");
        }

        QProductDocument p = QProductDocument.productDocument;
        BooleanBuilder builder = new BooleanBuilder();

        // Điều kiện bắt buộc, không lấy từ input tự khai của client.
        builder.and(p.tenantId.eq(authenticatedTenantId));

        if (filter.keyword() != null
                && !filter.keyword().isBlank()) {
            String keyword = filter.keyword().trim();
            builder.and(
                p.name.containsIgnoreCase(keyword)
                    .or(p.sku.containsIgnoreCase(keyword))
            );
        }

        if (filter.minPriceMinor() != null) {
            builder.and(p.priceMinor.goe(
                filter.minPriceMinor()
            ));
        }

        if (filter.maxPriceMinor() != null) {
            builder.and(p.priceMinor.loe(
                filter.maxPriceMinor()
            ));
        }

        if (Boolean.TRUE.equals(filter.activeOnly())) {
            builder.and(p.active.isTrue());
        }

        return builder;
    }
}
~~~

BooleanBuilder cho phép thêm điều kiện khi tham số có mặt. Nó là **mutable**, vì vậy tạo builder mới cho mỗi request; không lưu BooleanBuilder singleton rồi thêm điều kiện của nhiều người dùng.

### 12.1. Null có hai ý nghĩa rất khác nhau

Nếu minPriceMinor không được truyền, ta **bỏ qua giới hạn dưới**, chứ không tìm product có giá null. Không dùng null input để đồng thời biểu diễn “không lọc” và “field BSON là null”.

Nếu nghiệp vụ cần tìm document có field thiếu hoặc null, hãy thêm một lựa chọn filter riêng, nêu rõ semantics và kiểm thử dữ liệu legacy.

### 12.2. Validate thay vì chỉ trông đợi type safety

BooleanBuilder không tự biết:

- Giá âm có hợp lệ không.
- Keyword dài hàng nghìn ký tự có gây truy vấn đắt không.
- activeOnly=false là “không lọc” hay “chỉ inactive”.
- Client có quyền lọc theo tất cả property không.
- Regex/contains có tuân theo collation và index của ứng dụng không.

Các quy tắc này nằm ở tầng API/service, trước khi tạo Predicate.

## 13. findAll, findOne, count và exists

~~~java
QProductDocument p = QProductDocument.productDocument;
var predicate = p.tenantId.eq("shop-a")
    .and(p.active.isTrue());

Iterable<ProductDocument> rows =
    repository.findAll(predicate);

long total = repository.count(predicate);
boolean any = repository.exists(predicate);

var single = repository.findOne(
    p.tenantId.eq("shop-a")
        .and(p.sku.eq("BOOK-101"))
);
~~~

| Method | Ý nghĩa | Cần lưu ý |
| --- | --- | --- |
| findAll(predicate) | Tìm tất cả document khớp | Không nên trả tập vô hạn ra API |
| findOne(predicate) | Tìm duy nhất một entity nếu có | Nhiều document khớp có thể gây lỗi |
| count(predicate) | Đếm document khớp | Truy vấn riêng, có chi phí |
| exists(predicate) | Kiểm tra có document khớp | Không thay thế phân quyền |
| findAll(predicate, pageable) | Trả Page trong executor đồng bộ | Có metadata, có thể cần count |
| findAll(predicate, orders...) | Sắp xếp qua Q OrderSpecifier | Không tự giới hạn số kết quả |

### 13.1. findOne không phải findFirst

Nếu predicate **name = "Sách"** khớp nhiều document, không dùng findOne để chọn ngẫu nhiên “document đầu tiên”. Hãy giới hạn bằng unique key hoặc dùng truy vấn danh sách có sort/limit.

Với SKU duy nhất trong tenant, có thể tạo:

~~~javascript
db.products.createIndex(
  { tenant_id: 1, sku: 1 },
  { unique: true }
);
~~~

Index trên bảo vệ tính duy nhất thực tế; type-safe Predicate không thay thế unique constraint.

### 13.2. Count không miễn phí

Nếu UI chỉ hiển thị “Tải thêm”, không bắt buộc đếm tổng số của toàn bộ filter ở mỗi request. Count có thể cần quét index hoặc nhiều document. Cân nhắc Slice/limit+1 hoặc keyset pagination khi phù hợp.

## 14. Sắp xếp có kiểu và phân trang đồng bộ

Q-path tạo được **OrderSpecifier**:

~~~java
Iterable<ProductDocument> ordered =
    repository.findAll(
        predicate,
        p.priceMinor.asc(),
        p.sku.asc()
    );
~~~

Phân trang theo Page:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.asc("priceMinor"),
        Sort.Order.asc("id")
    )
);

Page<ProductDocument> page =
    repository.findAll(predicate, pageable);
~~~

PageRequest bắt đầu từ số trang 0. Sort có khóa phụ id giúp thứ tự xác định khi nhiều document cùng giá.

**Lưu ý:** Sort trong PageRequest vẫn dùng tên property dạng chuỗi. Nếu nhận sort từ HTTP request, hãy giới hạn vào danh sách field được phép:

~~~java
Sort sort = switch (requestedSort) {
    case "price-asc" -> Sort.by(
        Sort.Order.asc("priceMinor"),
        Sort.Order.asc("id")
    );
    case "name-asc" -> Sort.by(
        Sort.Order.asc("name"),
        Sort.Order.asc("id")
    );
    default -> Sort.by(Sort.Order.asc("id"));
};
~~~

Không cho caller sort theo field nội bộ hoặc không có index nếu không được nghiệp vụ cho phép.

### 14.1. Thứ tự và thay đổi dữ liệu

Offset pagination có thể bị trùng hoặc bỏ sót khi writer khác thêm/xóa product giữa hai lần đọc. Khóa phụ id giúp kết quả sắp xếp rõ ràng, nhưng không tự tạo snapshot. Với dữ liệu rất lớn, cân nhắc keyset/seek pagination và cùng tiêu chí sort trong cursor.

## 15. Đường dẫn object nhúng và array

Nếu ProductDocument được mở rộng:

~~~java
public class SupplierInfo {
    private String code;
    private String region;

    public SupplierInfo() {}
    public String getCode() { return code; }
    public String getRegion() { return region; }
}
~~~

và có trường supplier:

~~~java
private SupplierInfo supplier;
~~~

Khi processor sinh đường dẫn nested thích hợp, cú pháp có thể là:

~~~java
var bySupplier = QProductDocument.productDocument
    .supplier.code.eq("SUP-01");
~~~

**Không mặc định mọi nested path có sẵn**: cách Q-type mở rộng object nhúng phụ thuộc metadata, khả năng APT và cấu hình tạo đường dẫn. Phải xem generated Q-class thật, đặc biệt khi cấu trúc dùng collection, map, polymorphism hoặc custom converters.

### 15.1. Collection property

Với tags là List<String>, có thể có path cho phép:

~~~java
var tagged = QProductDocument.productDocument
    .tags.contains("MONGODB");
~~~

Việc method compile được chưa đủ bảo đảm Spring Data MongoDB serializer dịch mọi collection predicate thành BSON như mong muốn. Với array embedded document cần nhiều điều kiện trên **cùng một phần tử**, đặc biệt phải hiểu **$elemMatch**.

### 15.2. Querydsl không phải SQL JOIN

Không suy rằng Q-path có tham chiếu tới một entity khác đồng nghĩa phép JOIN hoạt động như JPA. Tài liệu Spring Data MongoDB nêu hạn chế với DBRef joins, đặc biệt trong hỗ trợ reactive. Khi cần **$lookup**, **$group** hoặc **$project** để kết hợp/biến đổi document, hãy dùng aggregation.

## 16. @Field và _id: compile-time so với BSON runtime

Trong Java:

~~~java
@Field("tenant_id")
private String tenantId;
~~~

Predicate vẫn dùng:

~~~java
var predicate = p.tenantId.eq("shop-a");
~~~

MongoDB lại lưu **tenant_id**. Tầng Spring Data mapping có nhiệm vụ ánh xạ Java property path sang BSON field. Vì vậy, một test quan trọng là xác minh raw BSON thực và kết quả repository:

1. Insert ProductDocument có tenantId=shop-a.
2. Đọc BSON để xác nhận có **tenant_id**.
3. Gọi repository.findAll(p.tenantId.eq("shop-a")).
4. Xác nhận đúng product được trả.
5. Seed product của tenant khác và xác nhận không bị trả nhầm.

Property Java **id** ánh xạ thành BSON **_id**. MongoDB Java Driver thô không tự biết property id của entity; nếu gọi driver trực tiếp phải dùng tên BSON.

## 17. ReactiveQuerydslPredicateExecutor

Với ReactiveMongoRepository:

~~~java
package com.example.catalog;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import org.springframework.data.querydsl.ReactiveQuerydslPredicateExecutor;

public interface ReactiveProductRepository
        extends ReactiveMongoRepository<ProductDocument, ObjectId>,
                ReactiveQuerydslPredicateExecutor<ProductDocument> {
}
~~~

Sử dụng:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

QProductDocument p = QProductDocument.productDocument;
var predicate = p.tenantId.eq("shop-a")
    .and(p.active.isTrue());

Flux<ProductDocument> result =
    reactiveRepository.findAll(predicate);

Mono<Long> total =
    reactiveRepository.count(predicate);

Mono<Boolean> exists =
    reactiveRepository.exists(predicate);
~~~

Để sắp xếp có kiểu:

~~~java
Flux<ProductDocument> sorted =
    reactiveRepository.findAll(
        predicate,
        p.priceMinor.asc(),
        p.sku.asc()
    );
~~~

### 17.1. Pageable trong reactive executor

**Không giả định** overload Pageable của executor đồng bộ tồn tại với đúng chữ ký ở reactive executor:

~~~java
// Không xem đây là API bảo đảm của mọi ReactiveQuerydslPredicateExecutor:
reactiveRepository.findAll(predicate, pageable);
~~~

Tài liệu Spring Data MongoDB mô tả reactive executor với Flux/Mono và các overload Sort/OrderSpecifier, count, exists, fluent findBy. Nếu cần phân trang reactive bằng limit/skip hoặc keyset, sử dụng API hiện có trong phiên bản đang chạy, hoặc **ReactiveMongoTemplate** với Query/Criteria được đẩy xuống MongoDB.

**Không tải toàn bộ Flux rồi collectList để cắt trang trong Java.** Giới hạn phải áp dụng ở database.

### 17.2. Không block và không subscribe hai lần

Mono/Flux từ repository chỉ được thực thi khi có subscriber. Trong WebFlux, không gọi **block()** để chờ count hoặc findAll. Cũng không tự subscribe() rồi trả lại cùng publisher cho framework subscribe tiếp.

## 18. Service tìm kiếm có tenant và giới hạn kích thước trang

~~~java
package com.example.catalog;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

public class ProductSearchService {

    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    public Page<ProductDocument> search(
            String authenticatedTenantId,
            ProductFilter filter,
            int page,
            int size) {

        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException("Invalid page or size");
        }

        var predicate = ProductPredicates.forSearch(
            authenticatedTenantId, filter
        );

        var pageable = PageRequest.of(
            page, size,
            Sort.by(
                Sort.Order.asc("priceMinor"),
                Sort.Order.asc("id")
            )
        );

        return repository.findAll(predicate, pageable);
    }
}
~~~

**authenticatedTenantId** phải đến từ principal/session/token hoặc ngữ cảnh ủy quyền đáng tin cậy. Không chỉ nhận tenantId từ URL rồi truyền vào filter.

### 18.1. DTO là hợp đồng response riêng

Querydsl lọc **document nào khớp**; nó không tự tạo projection chỉ lấy một vài field. Endpoint công khai nên sử dụng DTO:

~~~java
public record ProductCardDto(
    String id,
    String sku,
    String name,
    long priceMinor
) {}
~~~

~~~java
public ProductCardDto toCard(ProductDocument p) {
    return new ProductCardDto(
        p.getId().toHexString(),
        p.getSku(),
        p.getName(),
        p.getPriceMinor()
    );
}
~~~

DTO kiểm soát dữ liệu công bố, nhưng nếu cần **giảm số field BSON truyền từ MongoDB**, phải thiết kế thêm projection hoặc fluent query/Query.fields() phù hợp. Không nhầm mapping DTO ở Java với projection database.

### 18.2. Tránh cho client tự tạo predicate không giới hạn

Spring Data có hỗ trợ **@QuerydslPredicate** cho một số hình thức web binding. Nếu dùng, cần whitelist field/toán tử và loại field nhạy cảm bằng cơ chế như **QuerydslBinderCustomizer**. Điều kiện tenant vẫn phải được server thêm vào Predicate cuối cùng bất kể caller gửi filter gì.

## 19. Khi nào nên dùng Querydsl, Criteria hay aggregation?

| Bài toán | Công cụ thích hợp |
| --- | --- |
| Filter cố định, ít tham số | Derived repository methods |
| Filter tùy chọn nhiều trường, muốn type-safe | Querydsl BooleanBuilder |
| Query có operator MongoDB chuyên biệt | MongoTemplate Query/Criteria |
| Xem một phần field, DTO projection | Repository projection / MongoTemplate fields |
| $group, $lookup, $project, $filter | Aggregation / @Aggregation |
| Bulk writes, update arrayFilters | MongoTemplate |
| Reactive query với paging/cursor đặc thù | ReactiveMongoTemplate hoặc API có hỗ trợ |
| Quy tắc phân quyền, transaction | Service/transaction boundary riêng |

QuerydslPredicateExecutor **không thay thế MongoTemplate**, không tự tạo index, không cung cấp SQL JOIN và không giải quyết transaction.

Nếu một truy vấn cần kết hợp Q-type filter với projection, collation, hint, aggregation và nhiều điều kiện business phức tạp, cân nhắc **custom repository fragment** với MongoTemplate thay vì cố nhồi tất cả vào một Predicate.

## 20. Hiệu năng: type-safe không đồng nghĩa query tối ưu

Một predicate:

~~~java
var predicate = p.tenantId.eq(tenantId)
    .and(p.active.isTrue())
    .and(p.priceMinor.between(100_000L, 300_000L));
~~~

về ý định tương đương filter BSON:

~~~javascript
db.products.find({
  tenant_id: "shop-a",
  active: true,
  priceMinor: { $gte: 100000, $lte: 300000 }
});
~~~

Một compound index cần đánh giá:

~~~javascript
db.products.createIndex({
  tenant_id: 1,
  active: 1,
  priceMinor: 1
});
~~~

Các field điều kiện bằng đứng trước field khoảng giá có thể hữu ích cho mẫu query này. Tuy nhiên, hiệu quả phụ thuộc dữ liệu, độ chọn lọc, sort, projection và workload.

### 20.1. Cẩn thận với containsIgnoreCase

~~~java
p.name.containsIgnoreCase("mongodb")
~~~

Tìm chuỗi con không phân biệt hoa/thường có thể cần cơ chế so khớp dạng pattern. **Không mặc định B-tree index trên name tối ưu mọi phép contains**, đặc biệt khi không có prefix cố định.

Nếu yêu cầu tìm kiếm từ vựng/độ liên quan/phân tích ngôn ngữ, đánh giá text index hoặc giải pháp search chuyên biệt thay vì suy rằng Querydsl thay thế search engine.

### 20.2. Dùng explain trên filter BSON thực

~~~javascript
db.products.find({
  tenant_id: "shop-a",
  active: true,
  priceMinor: { $gte: 100000, $lte: 300000 }
}).explain("executionStats");
~~~

| Chỉ số | Cần xác minh |
| --- | --- |
| winningPlan | Có sử dụng index phù hợp không? |
| totalKeysExamined | Bao nhiêu index key đã được duyệt? |
| totalDocsExamined | Bao nhiêu document gốc đã đọc? |
| nReturned | Bao nhiêu document khớp? |
| SORT và FETCH | Có sort/fetch tốn tài nguyên không? |
| executionTimeMillis | Độ trễ thực tế thế nào? |

Predicate biên dịch được không chứng minh MongoDB đang sử dụng đúng field, index hoặc collation. Với @Field/custom converter, kiểm tra cả filter BSON do framework thực thi.

## 21. Kiểm thử tích hợp repository Querydsl

Mock repository có thể test service ghép Predicate đúng về mặt Java, nhưng **không chứng minh processor sinh Q-type hay MongoDB thực thi filter đúng**. Cần ít nhất một integration test trên MongoDB dành riêng cho test, ví dụ Testcontainers.

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;

@DataMongoTest
class ProductQuerydslTest {

    @Autowired ProductRepository repository;

    @Test
    void filtersByTenantActiveAndPrice() {
        String tenant = "TEST-" + UUID.randomUUID();
        String otherTenant = "OTHER-" + UUID.randomUUID();

        ProductDocument a = repository.save(
            new ProductDocument(
                tenant, "TEST-BOOK", "Sách MongoDB", true, 150_000L, 10
            )
        );
        ProductDocument b = repository.save(
            new ProductDocument(
                tenant, "TEST-PEN", "Bút", false, 20_000L, 5
            )
        );
        ProductDocument other = repository.save(
            new ProductDocument(
                otherTenant, "TEST-OTHER", "Sách khác", true, 140_000L, 3
            )
        );

        try {
            QProductDocument p = QProductDocument.productDocument;
            var predicate = p.tenantId.eq(tenant)
                .and(p.active.isTrue())
                .and(p.priceMinor.goe(100_000L));

            List<ProductDocument> found = new ArrayList<>();
            repository.findAll(predicate).forEach(found::add);

            assertThat(found)
                .extracting(ProductDocument::getSku)
                .containsExactly("TEST-BOOK");

            assertThat(repository.count(predicate)).isEqualTo(1L);
            assertThat(repository.exists(predicate)).isTrue();
        } finally {
            repository.deleteAllById(
                List.of(a.getId(), b.getId(), other.getId())
            );
        }
    }
}
~~~

Test này xác minh:

1. QProductDocument đã được sinh và có thể biên dịch.
2. Repository có QuerydslPredicateExecutor hoạt động.
3. tenantId của Java được map sang **tenant_id** BSON.
4. Active/price filter loại đúng product không phù hợp.
5. Product của tenant khác không được trả.
6. Count/exists dùng cùng predicate cho kết quả phù hợp.

**Chỉ chạy trên database test**, không chạy trên production.

### 21.1. Kiểm chứng tên field raw BSON

Trong một test có sẵn mongoTemplate, saved và tenant:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Document raw = mongoTemplate.findOne(
    Query.query(Criteria.where("_id").is(saved.getId())),
    Document.class,
    "products"
);

assertThat(raw).isNotNull();
assertThat(raw.getString("tenant_id")).isEqualTo(tenant);
assertThat(raw.containsKey("tenantId")).isFalse();
~~~

Ví dụ này kiểm tra **dữ liệu MongoDB thực**, không chỉ object Java sau mapping.

### 21.2. Ma trận filter động cần test

| Input | Kết quả kỳ vọng |
| --- | --- |
| Không có filter tùy chọn | Chỉ áp tenant |
| activeOnly=true | Tenant AND active=true |
| Chỉ minPrice | Tenant AND priceMinor >= min |
| minPrice và maxPrice | Tenant AND giá trong khoảng |
| Keyword | Tenant AND (name OR sku) |
| minPrice > maxPrice | Báo validation error |
| tenant rỗng | Từ chối truy vấn |
| Keyword khớp tên ở tenant khác | Không trả kết quả tenant khác |

Với nested array/collection path, cần thêm test runtime cho đúng semantics MongoDB, không chỉ test Predicate.toString().

## 22. Những lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Cannot find symbol QProductDocument | APT chưa chạy hoặc source path chưa được nhận | Kiểm tra MongoAnnotationProcessor và generated sources |
| Chỉ có JPA Q-types | Kích hoạt JPA processor thay vì Mongo processor | Dùng MongoAnnotationProcessor |
| Lỗi jakarta/javax | Classifier hoặc version chưa khớp | Đồng bộ Querydsl, Spring Data, compiler |
| Lỗi thiếu class Querydsl runtime | Artifact không tương thích hoặc thiếu dependency | Kiểm tra dependency tree |
| Có driver MongoDB cũ | querydsl-mongodb kéo dependency cũ | Exclude và để Spring Data quản lý driver |
| IDE báo đỏ nhưng build thành công | IDE chưa nhận thư mục generated | Reload Maven/Gradle |
| CI không có Q-type | Local đang dùng generated files cũ | Clean compile trong CI |
| Q-type có property cũ | Chưa tái sinh sau khi đổi entity | Clean build |
| MapStruct/Lombok không chạy | -processor chỉ định duy nhất MongoAnnotationProcessor | Cấu hình các processor cần thiết |
| Predicate compile nhưng query không match | Mapping @Field/BSON không như tưởng | Test raw BSON và result |
| findOne lỗi nhiều kết quả | Predicate không unique | Bổ sung unique filter/index |
| OR trả dữ liệu ngoài tenant | Nhóm OR/AND sai | Luôn AND tenant ngoài nhóm tìm kiếm |
| API tìm kiếm chậm | Chưa có index hoặc string contains khó index | Đo explain |
| Reactive không có findAll(predicate,pageable) | Suy API đồng bộ sang reactive | Dùng overload được hỗ trợ hoặc ReactiveMongoTemplate |
| Client lọc được field nhạy cảm | Web binding không whitelist | Giới hạn binding và authorization |

### 22.1. Quy trình kiểm tra thiếu Q-class

1. Entity thuộc source set được biên dịch và có @Document đúng.
2. querydsl-mongodb và querydsl-apt ở phiên bản tương thích.
3. MongoAnnotationProcessor được kích hoạt.
4. Các processor dependencies hiện diện trong build.
5. Q-class có xuất hiện trong target/build generated sources không.
6. IDE đã reload project chưa.
7. Có processor khác bị -processor loại không.
8. Sau clean build còn lỗi không.
9. Integration test có thực thi Predicate được không.

**Không sửa generated Q-class bằng tay**. Nếu thiếu property, sửa entity/processor rồi sinh lại.

## 23. Bài tập thực hành

### Bài tập 1: Q-type có phải entity không?

**Câu hỏi:** Có cần lưu QProductDocument trong MongoDB?

**Đáp án:** Không. QProductDocument là generated Java type cho Predicate; ProductDocument mới là entity ánh xạ collection.

### Bài tập 2: processor đúng

Entity có @Document nhưng không sinh Q-class, project chỉ có JPAAnnotationProcessor. Sửa thế nào?

**Đáp án:** Bật **org.springframework.data.mongodb.repository.support.MongoAnnotationProcessor**, thêm processor dependencies thích hợp, compile và kiểm tra generated sources.

### Bài tập 3: lọc giá

~~~java
var condition = p.active.isTrue()
    .and(p.priceMinor.goe(100_000L))
    .and(p.priceMinor.loe(200_000L));
~~~

**Ý nghĩa:** sản phẩm active và giá trong khoảng 100.000–200.000.

### Bài tập 4: tham số tùy chọn

minPrice=null có nghĩa query tìm priceMinor = null không?

**Đáp án:** Không, theo contract tìm kiếm ở ví dụ thì minPrice null nghĩa **bỏ qua điều kiện minPrice**.

### Bài tập 5: OR và tenant

~~~java
var search = p.name.containsIgnoreCase("mongo")
    .or(p.sku.containsIgnoreCase("book"));

var secured = p.tenantId.eq("shop-a").and(search);
~~~

**Giải thích:** nhóm OR trước rồi AND với tenant.

### Bài tập 6: findOne

Nếu p.name.eq("Sách") khớp mười document, có thể dùng findOne để lấy tùy ý một document không?

**Đáp án:** Không. findOne được dùng khi cần kết quả duy nhất; dùng filter unique hoặc tìm danh sách có sort/limit.

### Bài tập 7: phân trang đồng bộ

**Câu hỏi:** API admin muốn Page và total. Chọn API nào?

**Đáp án:** QuerydslPredicateExecutor.findAll(predicate, Pageable), với index/sort phù hợp và hiểu rằng total có chi phí count.

### Bài tập 8: reactive

~~~java
interface ReactiveProductRepository
        extends ReactiveMongoRepository<ProductDocument, ObjectId>,
                ReactiveQuerydslPredicateExecutor<ProductDocument> {}

Mono<Long> total = reactiveRepository.count(predicate);
~~~

**Chú ý:** không mặc định overload Pageable có ở reactive executor.

### Bài tập 9: @Field

Java dùng p.tenantId nhưng BSON có tenant_id. Vì sao?

**Đáp án:** Q-type dựa trên property Java, Spring Data mapping xử lý tên trường BSON. Integration test cần xác minh điều này.

### Bài tập 10: type safety và index

Code p.name.containsIgnoreCase("java") biên dịch. Có chắc query nhanh?

**Đáp án:** Không. Type safety không tự tạo index hoặc tối ưu regex/pattern. Phải đo explain và xem workload.

### Bài tập 11: input độc hại

Client gửi tenantId khác trong bộ lọc web Querydsl. Server nên xử lý thế nào?

**Đáp án:** Không dùng tenant tùy ý của client làm quyền. Bỏ/từ chối binding tenant và AND tenant đã xác thực vào Predicate.

### Bài tập 12: aggregation

Query cần $lookup nhà cung cấp và $group theo khu vực. QuerydslPredicateExecutor có phải lựa chọn tốt nhất?

**Đáp án:** Không. Dùng aggregation Spring Data MongoDB/MongoTemplate; Querydsl phù hợp hơn với filter động của entity.

## 24. Checklist ứng dụng thực tế

- Entity có @Document, @Id và @Field đúng.
- MongoAnnotationProcessor được bật ở compile time.
- Maven/Gradle/IDE/CI đều sinh được Q-class từ clean build.
- Querydsl core/mongodb/apt cùng dòng version, tương thích framework.
- Jakarta/javax được chọn đúng thế hệ.
- Tránh MongoDB driver cũ xung đột trong dependency tree.
- Repository mở rộng QuerydslPredicateExecutor tương ứng sync/reactive.
- Predicate luôn có điều kiện tenant và quyền từ context đã xác thực.
- BooleanBuilder mới cho từng request, không chia sẻ mutable builder.
- Keyword, giá, size và sort được validate/giới hạn.
- Querydsl web binding không cho lọc field nhạy cảm tùy ý.
- DTO/projection không để lộ entity nội bộ.
- @Field/nested path/array có integration test trên MongoDB.
- Index và explain được đánh giá theo truy vấn BSON thực.
- Không giả định mọi cú pháp Querydsl hoặc overload đồng bộ có ở reactive.

## 25. Tổng kết

1. **Q-type** là mã Java được sinh tự động từ entity, dùng để xây đường dẫn truy vấn có kiểu.
2. Spring Data MongoDB tích hợp thông qua **MongoAnnotationProcessor**, không chỉ Querydsl JPA processor.
3. **QuerydslPredicateExecutor** mở rộng MongoRepository với find, count, exists và paging theo Predicate.
4. **BooleanExpression** và **BooleanBuilder** giúp ghép điều kiện AND/OR, đặc biệt với filter tùy chọn.
5. **Luôn AND điều kiện tenant/authorization từ server**, không trao quyền cho client qua filter tùy ý.
6. **@Field/@Id** vẫn do mapping Spring Data chuyển sang BSON; test runtime vì compiler không kiểm tra dữ liệu thực.
7. **ReactiveQuerydslPredicateExecutor** dùng Mono/Flux, có API khác executor đồng bộ.
8. **Querydsl không thay thế aggregation, MongoTemplate, transaction hoặc index**.
9. **Generated classes phải do build tái tạo**, không tự sửa Q-type.
10. **Hiệu năng cần đo bằng explain và index phù hợp**; Q-type chỉ giải quyết một lớp vấn đề type-safety.

Biết cách **sinh Q-type và xây điều kiện truy vấn có kiểu** giúp dịch vụ **SPRING_DATA_MONGODB** tổ chức repository mở rộng dễ refactor, xây filter động an toàn hơn và phối hợp đúng với MongoTemplate, aggregation, reactive access và kiểm thử trên MongoDB thực.

### Tài liệu tham khảo

- [Spring Data MongoDB — Querydsl Extension và cấu hình MongoAnnotationProcessor](https://docs.spring.io/spring-data/mongodb/reference/repositories/core-extensions.html)
- [Querydsl — mã nguồn và annotation processing](https://github.com/querydsl/querydsl)
- [OpenFeign Querydsl — community fork](https://github.com/OpenFeign/querydsl)
