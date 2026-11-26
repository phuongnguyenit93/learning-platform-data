# Quản lý dependency, annotation processor và Q-type sinh tự động

Tích hợp Querydsl với Spring Data không chỉ là thêm `QuerydslPredicateExecutor` vào repository. Một cấu hình hoạt động cần nối được thư viện chạy ứng dụng, công cụ xử lý annotation trong lúc biên dịch và các Q-type được sinh từ mô hình miền.

Nếu ba phần này bị trộn lẫn, dự án có thể chạy trong IDE nhưng thất bại trên CI, nhìn thấy entity nhưng không sinh `QProduct`, hoặc biên dịch được predicate rồi thiếu Q-type khi đóng gói. Bài học giải thích trách nhiệm của từng phần, minh họa cấu hình cho JPA và cách quản lý mã sinh trong dự án một hoặc nhiều mô-đun.

## 1. Phân biệt ba nhóm dependency

| Nhóm | Dùng khi nào? | Vai trò |
| --- | --- | --- |
| Dependency của ứng dụng | Biên dịch và chạy code nghiệp vụ | Cung cấp Querydsl API, tích hợp backend và các lớp ứng dụng trực tiếp sử dụng |
| Dependency của annotation processor | Trong quá trình biên dịch | Đọc metadata của mô hình và sinh Q-type |
| Dependency của store | Khi cấu hình repository và truy cập dữ liệu | Cung cấp mapping, repository factory và implementation thực thi predicate |

Ví dụ với JPA:

- `QuerydslPredicateExecutor` thuộc Spring Data Commons.
- Thư viện Querydsl JPA cung cấp các API phù hợp với backend JPA.
- Querydsl APT cung cấp annotation processor để sinh Q-type.
- Spring Data JPA cung cấp implementation tích hợp executor với metadata JPA và `EntityManager`.

Thêm Commons không tự sinh Q-type. Thêm Querydsl APT không tự cung cấp một repository implementation. Thêm thư viện runtime cũng không đủ để kết luận annotation processing đã được kích hoạt.

### Ba classpath có thể khác nhau

Cần phân biệt classpath biên dịch của mã ứng dụng, processor path và runtime classpath. Một thư viện xuất hiện ở classpath của ứng dụng không nhất thiết xuất hiện ở processor path đã được khai báo tách biệt.

Ngược lại, một dependency chỉ đặt trên processor path không tự trở thành thư viện runtime. Nếu code ứng dụng dùng `Predicate`, `StringPath` hoặc Q-type kế thừa các lớp Querydsl, runtime và compile classpath vẫn phải có các API tương ứng theo thiết kế dependency của dự án.

Không đưa toàn bộ annotation processor vào dependency runtime chỉ để sửa lỗi thiếu lớp lúc xử lý annotation. Cần bổ sung lớp còn thiếu vào đúng nơi đang dùng nó.

## 2. Q-type là gì và được sinh lúc nào?

Q-type là mô hình đường dẫn có kiểu dữ liệu để tạo biểu thức Querydsl. Với một entity `Product`, Q-type mặc định thường có tên `QProduct`.

```text
Mã nguồn mô hình miền
        |
        v
javac và annotation processor phù hợp
        |
        +--> Q-type dạng mã Java được sinh
        |
        v
Biên dịch mã nguồn và mã sinh
        |
        v
Product.class, QProduct.class và các lớp sử dụng chúng
        |
        v
Đóng gói artifact và chạy ứng dụng
```

Annotation processing diễn ra trong các vòng xử lý của quá trình biên dịch; sơ đồ thể hiện trách nhiệm, không yêu cầu luôn có một chương trình sinh mã độc lập chạy trước compiler.

Q-type không phải bảng database, không phải migration và không tự thực thi truy vấn. Nó giúp code Java tham chiếu đường dẫn thuộc tính một cách có kiểu.

Ví dụ:

```java
QProduct product = QProduct.product;

Predicate predicate = product.name.containsIgnoreCase("bàn phím")
    .and(product.price.goe(new BigDecimal("500000")));
```

`Predicate` ở đây là `com.querydsl.core.types.Predicate`, không phải `java.util.function.Predicate`. Code tạo một cây điều kiện; repository implementation và backend phù hợp mới thực thi cây điều kiện đó.

Nếu đổi tên hoặc đổi kiểu thuộc tính trong entity, Q-type phải được tái sinh. Mã sinh cũ có thể khiến IDE hiển thị một mô hình đã lệch với mã nguồn hiện tại.

## 3. Chọn một bộ dependency tương thích

Trước khi cấu hình processor, cần xác định:

1. Store và module Spring Data đang sử dụng.
2. Hệ phiên bản Java, Spring Data và persistence API của dự án.
3. Các artifact Querydsl runtime và processor tương thích với hệ đó.
4. Processor nào nhận diện được metadata của domain model.
5. Mô-đun nào sở hữu source entity và chịu trách nhiệm sinh Q-type.

### Không trộn namespace JPA tùy ý

Một mô hình dùng:

```java
import jakarta.persistence.Entity;
```

khác với mô hình dùng:

```java
import javax.persistence.Entity;
```

Processor phải nhận diện đúng namespace và có các API cần thiết trên processor path. Runtime Querydsl, bộ sinh mã và persistence stack cũng phải tương thích.

Việc thêm cả hai bộ API để “cho đủ lớp” có thể che sự không nhất quán thay vì sửa nó. Hãy xác định hệ mà dự án thực sự dùng rồi chọn cả bộ dependency phù hợp.

### Giữ runtime và processor cùng hệ

Trong một bộ artifact Querydsl, nên quản lý phiên bản runtime và APT nhất quán theo tổ hợp được hỗ trợ. Không nâng riêng processor rồi giữ runtime ở một hệ khác chỉ vì cả hai vẫn có package `com.querydsl`.

Tên package Java không tự xác định đầy đủ tọa độ dependency, classifier hay dòng phân phối mà dự án lựa chọn. Nếu dùng một bộ tọa độ khác với ví dụ trong bài, phải đối chiếu cả runtime, code generation và processor của bộ đó.

Dependency management có thể quản lý một phần phiên bản, nhưng không mặc định rằng mọi processor hoặc API trên processor path đều đã được quản lý. Cần hiểu chính công cụ build đang giải quyết các dependency đó như thế nào.

## 4. Mô hình JPA minh họa

Các ví dụ cấu hình tiếp theo giả định một module JPA dùng Jakarta, có entity sau:

```java
package example.catalog;

import java.math.BigDecimal;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Product {

    @Id
    private Long id;

    private String code;
    private String name;
    private BigDecimal price;

    protected Product() {
    }

    public Long getId() { return id; }
    public String getCode() { return code; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
}
```

Đoạn mã minh họa mapping phục vụ đọc dữ liệu, không mô tả toàn bộ quy tắc tạo mới hay sinh ID. `@Id` đặt trên field nên mô hình dùng truy cập trường trong JPA.

Với cách sinh Q-type mặc định tương ứng, có thể nhận được các đường dẫn:

| Thuộc tính entity | Đường dẫn trên Q-type | Kiểu path điển hình |
| --- | --- | --- |
| `id` | `QProduct.product.id` | `NumberPath<Long>` |
| `code` | `QProduct.product.code` | `StringPath` |
| `name` | `QProduct.product.name` | `StringPath` |
| `price` | `QProduct.product.price` | `NumberPath<BigDecimal>` |

Vị trí package, tiền tố và tên biến mặc định có thể chịu cấu hình sinh mã. Khi tùy chỉnh, phải bảo đảm cơ chế phân giải entity path của module repository tương thích với kết quả sinh ra.

Không viết tay `QProduct` để chữa lỗi cấu hình processor. File viết tay dễ trở nên lệch metadata hoặc xung đột với file được sinh khi build đã được sửa.

## 5. Minh họa cấu hình Maven

Các đoạn XML dưới đây là những phần cần ghép vào cấu hình Maven phù hợp của một module JPA đã có dependency Spring Data JPA và persistence stack cần thiết. Đây không phải một `pom.xml` độc lập.

Ví dụ chọn bộ tọa độ `com.querydsl` có biến thể Jakarta. Các thuộc tính sau phải được dự án định nghĩa với giá trị cụ thể và tương thích:

- `${querydsl.version}`
- `${jakarta.persistence.version}`
- `${jakarta.annotation.version}`
- `${maven.compiler.plugin.version}`

Không dùng tên biến như một phiên bản artifact thực tế và không coi chúng là các property luôn có sẵn trong mọi parent POM.

### 5.1. Runtime Querydsl JPA

```xml
<dependencies>
    <dependency>
        <groupId>com.querydsl</groupId>
        <artifactId>querydsl-jpa</artifactId>
        <version>${querydsl.version}</version>
        <classifier>jakarta</classifier>
    </dependency>
</dependencies>
```

Classifier là một phần của lựa chọn artifact. Nó không thay cho version và không bảo đảm rằng mọi phiên bản hoặc mọi dòng phân phối đều có cùng biến thể. Ví dụ chỉ phù hợp khi bộ artifact được chọn thực sự cung cấp các biến thể này.

### 5.2. Processor path tách biệt

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>${maven.compiler.plugin.version}</version>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.querydsl</groupId>
                        <artifactId>querydsl-apt</artifactId>
                        <version>${querydsl.version}</version>
                        <classifier>jakarta</classifier>
                    </path>
                    <path>
                        <groupId>jakarta.persistence</groupId>
                        <artifactId>jakarta.persistence-api</artifactId>
                        <version>${jakarta.persistence.version}</version>
                    </path>
                    <path>
                        <groupId>jakarta.annotation</groupId>
                        <artifactId>jakarta.annotation-api</artifactId>
                        <version>${jakarta.annotation.version}</version>
                    </path>
                </annotationProcessorPaths>
                <annotationProcessors>
                    <annotationProcessor>
                        com.querydsl.apt.jpa.JPAAnnotationProcessor
                    </annotationProcessor>
                </annotationProcessors>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Processor JPA được chọn tường minh. Các API xuất hiện trên processor path để quá trình xử lý annotation có thể thấy những lớp mà nó cần, thay vì chỉ trông vào classpath của ứng dụng.

`jakarta.annotation-api` được minh họa như một dependency hỗ trợ cho tổ hợp processor đã chọn; không phải mọi tổ hợp code generation đều dùng chính xác cùng tập API. Điều quan trọng là processor path phải đủ cho bộ công cụ thực tế.

Nếu module còn dùng các processor khác, chẳng hạn cho mapping hoặc sinh mã từ annotation khác, phải tích hợp chúng vào cấu hình. Danh sách `annotationProcessors` tường minh không nên chỉ còn Querydsl rồi vô tình bỏ các processor mà dự án đang cần.

Không thêm một plugin APT cũ và cấu hình compiler mới cùng sinh một bộ Q-type nếu không có chủ đích rõ ràng. Hai cơ chế xử lý cùng domain model có thể gây sinh trùng hoặc làm khó xác định cấu hình nào đang có hiệu lực.

## 6. Minh họa cấu hình Gradle

Ví dụ Groovy DSL dưới đây cũng giả định module đã có Java plugin và dependency JPA phù hợp. Những property phiên bản phải được định nghĩa bởi dự án; đoạn mã không tự chọn phiên bản thay dự án.

```groovy
def querydslVersion = providers.gradleProperty("querydslVersion").get()
def jakartaPersistenceVersion = providers.gradleProperty(
    "jakartaPersistenceVersion"
).get()
def jakartaAnnotationVersion = providers.gradleProperty(
    "jakartaAnnotationVersion"
).get()

dependencies {
    implementation("com.querydsl:querydsl-jpa:${querydslVersion}:jakarta")

    annotationProcessor(
        "com.querydsl:querydsl-apt:${querydslVersion}:jakarta"
    )
    annotationProcessor(
        "jakarta.persistence:jakarta.persistence-api:${jakartaPersistenceVersion}"
    )
    annotationProcessor(
        "jakarta.annotation:jakarta.annotation-api:${jakartaAnnotationVersion}"
    )
}
```

`implementation` phục vụ mã ứng dụng và runtime theo mô hình dependency của Gradle. `annotationProcessor` phục vụ quá trình sinh mã của source set chính.

Khi cần chọn processor tường minh cho module tối giản chỉ có processor này, có thể cấu hình task biên dịch chính:

```groovy
tasks.named("compileJava", JavaCompile) {
    options.compilerArgs += [
        "-processor",
        "com.querydsl.apt.jpa.JPAAnnotationProcessor"
    ]
}
```

Nếu có nhiều processor, danh sách tường minh phải thể hiện đầy đủ những processor cần hoạt động. Không sao chép đoạn trên để thay thế cấu hình chung mà chưa tính tới các công cụ sinh mã khác.

Không phụ thuộc vào giả định rằng mọi JDK và mọi công cụ build luôn tự dò processor chỉ vì JAR của nó xuất hiện ở classpath. Cấu hình processor path và cách kích hoạt phải được quản lý bởi build.

### Main và test là hai phạm vi khác nhau

Processor cho source set chính không tự có nghĩa mọi entity khai báo trong test cũng được sinh Q-type. Nếu test thực sự sở hữu thêm domain type cần xử lý, cấu hình processor cho test theo nhu cầu đó.

Ngược lại, test chỉ sử dụng `QProduct` của mã chính thì thường cần thấy các class đã biên dịch của main, không cần sinh lại cùng một Q-type cho cùng entity trong test.

Đây cũng là lý do ví dụ chọn `compileJava` thay vì áp một danh sách processor duy nhất lên mọi task biên dịch mà không xem source set và processor path của từng task.

## 7. Quản lý thư mục generated sources

Với cấu hình thông thường, công cụ build có thể đặt mã sinh ở các vị trí như:

```text
Maven:
  target/generated-sources/annotations/example/catalog/QProduct.java

Gradle Java plugin:
  build/generated/sources/annotationProcessor/java/main/example/catalog/QProduct.java
```

Đây là đường dẫn minh họa theo quy ước của công cụ, không phải yêu cầu cố định. Build có thể tùy chỉnh output directory.

Cần phân biệt hai loại output:

| Output | Vai trò |
| --- | --- |
| `QProduct.java` | Mã nguồn được processor sinh để compiler biên dịch |
| `QProduct.class` | Lớp đã biên dịch dùng khi xây dựng biểu thức hoặc được hạ tầng phân giải Q-type |

Không chỉnh sửa trực tiếp file Java trong thư mục generated sources. Thay đổi phải bắt đầu từ domain model, annotation hoặc cấu hình sinh mã rồi được tái sinh.

### Tránh đăng ký mã sinh nhiều lần

Các tích hợp compiler hiện đại có cơ chế biên dịch nguồn do annotation processor sinh ra. Trước khi thêm thủ công thư mục generated vào source set hoặc cài thêm plugin, cần hiểu công cụ hiện có đã xử lý việc đó chưa.

Đăng ký cùng một nguồn qua nhiều cơ chế, hoặc giữ thêm một bản Q-type trong `src/main/java`, có thể gây lỗi trùng lớp và làm quá trình xử lý annotation khó dự đoán.

### Có nên commit Q-type không?

Với quy trình sinh mã tái lập trong build, lựa chọn thường phù hợp là quản lý domain source và cấu hình build, còn generated sources được tạo lại. Thư mục output do build quản lý nên được loại khỏi version control theo chính sách repository.

Nếu một repository có chính sách chủ động lưu mã sinh, phải có một nguồn sinh và quy tắc đồng bộ rõ ràng. Không vừa xem file đã commit là source chính vừa để processor tạo thêm một bản trùng trong cùng quá trình biên dịch.

Dù không commit `QProduct.java`, artifact chạy ứng dụng vẫn có thể cần chứa `QProduct.class`. Không nhầm “không lưu mã sinh trong Git” với “không đóng gói lớp sinh”.

## 8. Từ Q-type đến repository thực thi

Khi sinh mã và dependency đã đầy đủ, repository JPA có thể khai báo:

```java
package example.catalog;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface ProductRepository
        extends JpaRepository<Product, Long>,
                QuerydslPredicateExecutor<Product> {
}
```

Service sử dụng Q-type trong cùng mô hình:

```java
import java.math.BigDecimal;

import com.querydsl.core.types.Predicate;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

QProduct product = QProduct.product;

Predicate predicate = product.name.containsIgnoreCase("bàn phím")
    .and(product.price.goe(new BigDecimal("500000")));

Page<Product> page = repository.findAll(
    predicate,
    PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.asc("price"), Sort.Order.asc("id"))
    )
);
```

Đoạn sử dụng giả định đã có `ProductRepository repository` và có thể tham chiếu các lớp trong package `example.catalog`. Q-type hỗ trợ tạo điều kiện theo kiểu; module Spring Data JPA vẫn chịu trách nhiệm tích hợp executor với backend.

Q-type có mặt không bảo đảm entity mapping đúng, connection hoạt động hoặc mọi biểu thức được database hỗ trợ. Compile thành công là một lớp xác nhận, còn thực thi đúng trên store là lớp khác.

Khi chuyển sang MongoDB hoặc một store khác, phải xem lại cơ chế sinh Q-type phù hợp với metadata của store đó và implementation executor tương ứng. Không dùng processor JPA cho một lớp chỉ có annotation document rồi mặc định rằng nó sẽ tự được nhận diện như JPA entity.

## 9. Tổ chức dự án nhiều mô-đun

Một cấu trúc có thể là:

```text
catalog-model
  - sở hữu Product.java
  - sinh và biên dịch QProduct
  - xuất artifact chứa các class cần dùng

catalog-data
  - phụ thuộc catalog-model
  - cấu hình repository và backend JPA
  - sử dụng QProduct để tạo predicate

catalog-app
  - cấu hình ứng dụng
  - gọi các service và repository phù hợp
```

Cần xác định rõ mô-đun nào chịu trách nhiệm sinh Q-type. Annotation processor thông thường xử lý các phần tử trong quá trình biên dịch phù hợp; chỉ thêm dependency chứa entity đã biên dịch vào module khác không đồng nghĩa processor ở module sau tự sinh lại toàn bộ Q-type cho các class đó.

Nếu `catalog-model` sở hữu việc sinh mã, artifact mà module sử dụng phải nhận được `QProduct.class`. Chỉ để file `.java` trong output tạm của máy người phát triển mà không biên dịch hoặc đóng gói đúng sẽ khiến module khác không dùng được.

### Dependency API hay implementation?

Nếu module công khai Q-type hoặc các kiểu Querydsl trong API của nó, module tiêu thụ cần thấy những kiểu liên quan trên compile classpath. Với mô hình `java-library` của Gradle, cần cân nhắc đúng ranh giới `api` và `implementation`, hoặc khai báo dependency trực tiếp ở module tiêu thụ theo thiết kế.

Không mặc định processor dependency được truyền sang các module khác. Processor là công cụ build của module chịu trách nhiệm sinh mã, không phải khả năng được tự động kế thừa chỉ vì một module phụ thuộc module đó.

Cũng không sinh Q-type của cùng entity độc lập trong nhiều module rồi đưa các bản trùng vào một ứng dụng. Việc đóng gói cần có một chủ sở hữu rõ ràng cho mỗi lớp sinh.

## 10. IDE, build sạch và CI phải cùng một quy trình

IDE có thể giữ Q-type cũ, tự bật annotation processing hoặc đánh dấu generated source root theo cấu hình riêng. Vì vậy, việc IDE không báo đỏ chưa đủ chứng minh build tái lập.

Một quy trình đáng tin cần đạt các điều kiện:

- Từ một checkout không chứa output cũ, build có thể sinh và biên dịch đủ Q-type cần dùng.
- Cấu hình processor nằm trong build, không chỉ trong thiết lập cá nhân của IDE.
- Phiên bản JDK và công cụ build trên CI phù hợp với cấu hình của dự án.
- Artifact đầu ra chứa các class mà module sau hoặc runtime cần.
- Khi sửa entity, mã sinh được cập nhật từ nguồn chính thay vì chỉnh tay.

Không dùng cache cũ làm một phần bắt buộc của quy trình. Cache có thể tăng tốc, nhưng build đúng không nên phụ thuộc vào Q-type chỉ tồn tại từ một lần chạy trước trên một máy cụ thể.

Nếu IDE dùng JDK khác với build hoặc CI, cần xác định compiler nào thực sự chạy processor. Việc các môi trường đều hiển thị cùng một phiên bản ngôn ngữ trong editor không tự bảo đảm annotation processing diễn ra giống nhau.

## 11. Chẩn đoán lỗi theo giai đoạn

| Biểu hiện | Lớp cần xem | Nguyên nhân có thể gặp |
| --- | --- | --- |
| `cannot find symbol QProduct` | Sinh mã và biên dịch | Processor chưa chạy, entity chưa được nhận diện hoặc nguồn sinh chưa được biên dịch |
| Không tìm thấy `JPAAnnotationProcessor` | Processor path | APT artifact thiếu hoặc tọa độ, classifier, cấu hình processor không phù hợp |
| Processor thiếu lớp persistence API | Processor path và namespace | Thiếu API trên processor path hoặc dùng nhầm hệ Jakarta/Javax |
| File Q không được cập nhật sau khi sửa entity | Sinh mã và output | Đang nhìn mã sinh cũ, task không xử lý source mong đợi hoặc cấu hình chỉ tồn tại trong IDE |
| `Attempt to recreate a file for type` | Annotation processing | Có cơ chế sinh trùng, processor trùng trách nhiệm hoặc mã sinh bị đưa vào xử lý lại |
| `duplicate class` với Q-type | Source roots và đóng gói | Có nhiều bản nguồn hoặc class cùng tên, gồm cả bản sinh và bản được quản lý thủ công |
| Module khác không nhận diện Q-type | Ranh giới module | Artifact chưa chứa lớp Q hoặc dependency compile chưa làm lộ các kiểu cần thiết |
| Runtime thiếu Q-type | Đóng gói và runtime classpath | Có mã nguồn sinh nhưng class không được đóng gói hoặc dependency chứa nó không có ở runtime |
| IDE chạy được, CI thất bại | Tính tái lập của build | IDE cấu hình processor riêng, khác JDK hoặc phụ thuộc output cũ |
| Có Q-type nhưng repository khởi tạo lỗi | Tích hợp store | Thiếu implementation executor, thư viện backend hoặc mapping hợp lệ |

Thông báo cụ thể phụ thuộc công cụ và phiên bản. Bảng phân loại nguyên nhân để tìm đúng lớp cấu hình, không khẳng định một thông báo luôn chỉ có duy nhất một nguyên nhân.

### Tránh sửa sai lớp

Nếu processor thiếu `jakarta.persistence.Entity`, thêm một dependency runtime có thể không giải quyết được processor path tách biệt. Nếu repository không có implementation Querydsl cho store, chạy sinh Q-type nhiều lần cũng không bổ sung implementation đó.

Tương tự, lỗi nhiều kết quả khi gọi `findOne` là vấn đề ngữ nghĩa truy vấn hoặc dữ liệu, không phải bằng chứng annotation processor hoạt động sai.

## 12. Đối chiếu khi nâng dependency hoặc đổi mô hình

Một thay đổi về Querydsl, persistence API, JDK hoặc công cụ build có thể tác động đồng thời runtime và quá trình sinh mã. Khi thực hiện một thay đổi như vậy, cần xác định:

1. Tọa độ, version và classifier của runtime cùng APT còn thuộc tổ hợp phù hợp không?
2. Processor path còn đủ API cần thiết không?
3. Việc kích hoạt processor còn được build khai báo rõ không?
4. Q-type có được tái sinh từ source mới không?
5. Các module tiêu thụ và artifact đóng gói có dùng đúng class mới không?
6. Module Spring Data của store còn hỗ trợ cách executor đang được sử dụng không?

Không chỉ cập nhật một con số phiên bản rồi giữ nguyên mã sinh cũ để làm cho compilation tạm thời đi qua. Mục tiêu là một chuỗi build có thể lặp lại từ domain source đến artifact chạy được.

## 13. Tình huống tự thực hành

Có thể dùng module minh họa để lần lượt đối chiếu:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Sinh từ entity Product ban đầu | Q-type xuất hiện đúng package và có các path theo kiểu dữ liệu |
| Đổi `name` thành một tên thuộc tính khác | Mã sinh mới phản ánh thay đổi; tham chiếu cũ được phát hiện khi biên dịch |
| Không còn output của lần build trước | Quy trình vẫn tự sinh và biên dịch Q-type |
| Tách entity sang một module riêng | Module dùng repository nhận được class Q từ artifact đúng |
| Test chỉ sử dụng entity của main | Không sinh trùng cùng một Q-type trong test |
| Đưa thêm một annotation processor khác | Cấu hình tường minh không vô tình loại processor đó |
| Kiểm tra artifact thay vì chỉ thư mục nguồn | Có các class cần thiết, không chỉ có file Java sinh tạm |
| Chuyển sang một mô hình document | Processor và implementation executor được đánh giá lại theo store |

Quản lý Querydsl hiệu quả cần một chủ sở hữu rõ ràng cho domain source và Q-type, một bộ dependency tương thích và một build tự thực hiện annotation processing. Commons cung cấp abstraction repository; Q-type và công cụ sinh mã hỗ trợ biểu thức có kiểu; module của store hoàn tất phần thực thi. Giữ đúng ranh giới này giúp giải quyết lỗi ở đúng giai đoạn thay vì phụ thuộc vào mã sinh cũ hoặc cấu hình riêng của IDE.