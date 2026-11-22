
# Lombok, MapStruct và khả năng tương thích với javac

Khi nâng cấp Java, mã nguồn sử dụng **Lombok** và **MapStruct** có thể đột ngột không biên dịch được, dù các class nghiệp vụ hầu như không đổi. Nguyên nhân thường nằm ở tầng **công cụ sinh mã và trình biên dịch**: phiên bản javac khác, cơ chế annotation processing thay đổi, module access chặt hơn, processor không được đăng ký, hoặc hai công cụ không nhìn thấy kết quả của nhau trong cùng một lượt biên dịch.

Đây là nội dung thuộc *Java Advance Compatibility Migration*, phần *Sinh mã và công cụ test*. Bài học trình bày sự khác biệt kỹ thuật giữa Lombok và MapStruct, cách chúng tương tác với javac, cách cấu hình Maven/Gradle, các dạng lỗi điển hình và phương pháp kiểm chứng nguồn được sinh cũng như artifact cuối cùng qua nhiều phiên bản JDK.

Mục tiêu không phải ghim mãi một phiên bản Lombok hay thêm cờ `--add-opens` tùy tiện, mà là **đưa annotation processing trở thành một phần có quản lý của quy trình build**: có version được kiểm chứng, dependency scope đúng, output rõ ràng và phép thử tái hiện được.

## 1. Vì sao annotation-driven code dễ gây sự cố migration?

Một project sử dụng annotation để tránh code lặp:

~~~java
import lombok.Getter;
import lombok.RequiredArgsConstructor;

@Getter
@RequiredArgsConstructor
public class Product {
    private final String code;
    private final long price;
}
~~~

Trong source chỉ có field và annotation. Nhưng consumer có thể gọi:

~~~java
Product product = new Product("BOOK-1", 100L);
System.out.println(product.getCode());
~~~

Constructor và getter được Lombok hỗ trợ tạo ra trong quá trình compile. Nếu Lombok không hoạt động, hai lời gọi trên có thể báo lỗi dù source của `Product` vẫn hiện diện.

Một project khác dùng MapStruct:

~~~java
import org.mapstruct.Mapper;

@Mapper
public interface ProductMapper {
    ProductDto toDto(Product product);
}
~~~

Code chỉ khai báo interface. MapStruct phải sinh một implementation cụ thể, thường có tên tương tự `ProductMapperImpl`, để runtime có thể tạo hoặc inject mapper đó.

Vì vậy, với code generation, cần phân biệt:

| Tầng | Lombok | MapStruct |
|---|---|---|
| Source do lập trình viên viết | Field, annotation và kiểu Java | Interface/abstract mapper và annotation |
| Cơ chế compiler | Tương tác sâu với javac AST và các giai đoạn compiler | Annotation processor theo `javax.annotation.processing` |
| Kết quả chính | Member được bổ sung trong class biên dịch | Java source mapper được sinh, rồi biên dịch thành class |
| Có cần processor khi compile? | Có, khi source dùng Lombok annotation | Có, khi cần sinh implementation mapper |
| Có cần processor ở runtime? | Thường không đối với những member đã được sinh | Không đối với mapper đã được biên dịch |
| Rủi ro khi đổi JDK | Phụ thuộc cấu trúc javac nội bộ | Thay đổi annotation processing, model, source language và toolchain |
| Khi phối hợp với nhau | Lombok tạo accessor/builder mà processor khác đọc | MapStruct phải nhận diện đúng accessor/builder từ Lombok |

Không được hiểu rằng hai công cụ chỉ “xử lý annotation giống nhau”. Chúng có cách làm khác nhau, do đó có những nguyên nhân lỗi và cách xử lý khác nhau.

## 2. javac biên dịch và annotation processing như thế nào?

`javac` là compiler của Java. Nó xử lý mã nguồn qua các giai đoạn như parse, symbol resolution, type checking, annotation processing và tạo class file. Annotation processing tiêu chuẩn được mô tả qua **JSR 269** và các API trong package:

~~~java
javax.annotation.processing
javax.lang.model
javax.tools
~~~

Lưu ý: package `javax.annotation.processing` vẫn là API của Java SE. Nó **không tự đổi sang `jakarta.annotation.processing`** chỉ vì một ứng dụng đang migration từ `javax.persistence` sang `jakarta.persistence`.

Một annotation processor tiêu chuẩn nhận các phần tử từ compiler, kiểm tra annotation và có thể sinh thêm source/resource file bằng `Filer`. MapStruct sử dụng mô hình này để tạo Java source cho mapper.

### 2.1. Mô hình các vòng xử lý

~~~mermaid
flowchart TD
    A["Source Java + annotations"] --> B["javac: parse và symbol model"]
    B --> C["Annotation processors"]
    C --> D{"Có source mới?"}
    D -->|Có| E["Sinh Java source vào generated-sources"]
    E --> C
    D -->|Không| F["Type checking và tạo bytecode"]
    F --> G["Class files trong artifact"]
~~~

Các processor có thể chạy qua nhiều vòng (**processing rounds**). Source mới được tạo trong một vòng có thể được nhìn thấy ở vòng sau. Tuy nhiên, compiler chỉ biết những thành phần được tạo đúng cách qua processing API; không phải mọi kỹ thuật sửa AST nội bộ đều được hỗ trợ theo cùng một hợp đồng.

### 2.2. Lombok khác annotation processor thông thường

Lombok đăng ký cơ chế tham gia compilation nhưng còn sử dụng tích hợp sâu với compiler để bổ sung member, constructor, getter, setter, builder và các cấu trúc khác mà source chưa viết trực tiếp.

Điều này giúp compiler nhìn thấy member được sinh như thể chúng thuộc class Java. Nhưng nó cũng khiến khả năng tương thích với **phiên bản javac** quan trọng hơn so với processor chỉ dùng API tiêu chuẩn.

Một JDK mới có thể thay đổi nội bộ compiler, cấu trúc AST, class hoặc cơ chế module access. Lombok cũ có thể thất bại với exception kiểu:

~~~text
java.lang.NoSuchFieldError
java.lang.IllegalAccessError
java.lang.ExceptionInInitializerError
~~~

Các exception này là ví dụ; lỗi thực tế phụ thuộc phiên bản Lombok, JDK và build. Không được chỉ dựa trên tên exception để kết luận chắc chắn nguyên nhân.

### 2.3. MapStruct sử dụng model của compiler để sinh mã

MapStruct đọc mapper interface/abstract class, kiểu nguồn, kiểu đích, getter/setter, constructor, builder và mapping annotations. Nó sinh code Java gọi trực tiếp các accessor/converter phù hợp.

Ví dụ:

~~~java
import org.mapstruct.Mapper;

@Mapper
public interface ProductMapper {
    ProductDto toDto(Product source);
}
~~~

Với các type phù hợp, output có thể có dạng:

~~~java
// Mã minh họa được sinh, không phải nguyên văn cho mọi version
public class ProductMapperImpl implements ProductMapper {
    @Override
    public ProductDto toDto(Product source) {
        if (source == null) {
            return null;
        }

        ProductDto result = new ProductDto();
        result.setCode(source.getCode());
        result.setPrice(source.getPrice());
        return result;
    }
}
~~~

Nếu compiler chưa nhìn thấy getter do Lombok tạo, MapStruct có thể cho rằng `Product` không có property `code` hoặc `price`. Khi đó lỗi biểu hiện như **missing property**, dù nguyên nhân sâu hơn là tương tác giữa hai công cụ.

## 3. Phân biệt API, processor và runtime dependency

Hai thư viện thường có những artifact giữ vai trò khác nhau:

| Vai trò | Artifact điển hình | Công dụng |
|---|---|---|
| Annotation và API MapStruct | `org.mapstruct:mapstruct` | Chứa `@Mapper`, `@Mapping` và các API liên quan |
| Processor MapStruct | `org.mapstruct:mapstruct-processor` | Chạy trong compilation để sinh mapper source |
| Lombok | `org.projectlombok:lombok` | Annotation và cơ chế hỗ trợ javac |
| Cầu nối tích hợp | `org.projectlombok:lombok-mapstruct-binding` | Hỗ trợ hai processor phối hợp trong cấu hình phù hợp |
| Implementation mapper đã compile | Class sinh trong chính artifact ứng dụng/thư viện | Chạy ở runtime để thực hiện mapping |

Các tọa độ trên chỉ biểu diễn **tên artifact**, không ấn định version. Mỗi dự án phải chọn bộ version phù hợp với JDK, compiler, framework và build plugin thực tế.

Một sai lầm thường gặp là chỉ thêm:

~~~groovy
implementation("org.mapstruct:mapstruct:VERSION")
~~~

rồi tưởng rằng MapStruct sẽ tự sinh implementation. Artifact API chứa annotation không thay thế `mapstruct-processor`. Nếu processor không được kích hoạt, code compile mapper interface có thể thành công, nhưng runtime gọi `Mappers.getMapper(...)` hoặc DI để lấy implementation sẽ thất bại.

Tương tự, Lombok không chỉ là dependency runtime. Processor của Lombok phải hoạt động ở compile time để tạo method/constructor mà code đang dùng.

### 3.1. Compile classpath và processor path khác nhau

Trong hệ build hiện đại cần phân biệt:

- **Compile classpath**: class, annotation, interface mà source Java được phép tham chiếu.
- **Annotation processor path**: processor được javac tìm/nạp và thực thi.
- **Runtime classpath**: class và thư viện ứng dụng cần lúc chạy.
- **Test compile/processor path**: classpath/processor dành riêng cho test source.

Một processor có thể nằm trong dependency graph nhưng không thực sự nằm trên processor path. Điều ngược lại cũng xảy ra: processor hoạt động khi compile nhưng không cần được đóng gói vào ứng dụng.

### 3.2. Annotation processor không phải implementation runtime

MapStruct processor chỉ tạo mã trong quá trình build. Khi `ProductMapperImpl.class` đã được biên dịch, runtime không cần nạp `mapstruct-processor` để thực thi mapping.

Đưa compiler internals hoặc processor vào fat JAR production thường không giúp được gì, còn có thể:

- Tăng kích thước và bề mặt phụ thuộc.
- Tạo conflict với dependency runtime khác.
- Mang theo class của compiler không cần thiết.
- Gây rủi ro khi tạo custom runtime bằng `jlink`.

Hãy kiểm tra runtime artifact sau packaging để bảo đảm dependency được dùng đúng nơi.

## 4. Cấu hình Gradle với Java, Lombok và MapStruct

Với Gradle sử dụng plugin `java` hoặc `java-library`, một cấu hình điển hình:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    // API MapStruct có mặt khi biên dịch code dùng @Mapper.
    implementation("org.mapstruct:mapstruct:MAPSTRUCT_VERSION")

    // Lombok annotation và transformer cần ở compile + processor path.
    compileOnly("org.projectlombok:lombok:LOMBOK_VERSION")
    annotationProcessor("org.projectlombok:lombok:LOMBOK_VERSION")

    // Processor dùng để sinh MapperImpl.
    annotationProcessor(
        "org.mapstruct:mapstruct-processor:MAPSTRUCT_VERSION"
    )

    // Dùng khi cấu hình Lombok/MapStruct cần cầu nối tương ứng.
    annotationProcessor(
        "org.projectlombok:lombok-mapstruct-binding:BINDING_VERSION"
    )

    // Nếu test source cũng trực tiếp sử dụng Lombok:
    testCompileOnly("org.projectlombok:lombok:LOMBOK_VERSION")
    testAnnotationProcessor("org.projectlombok:lombok:LOMBOK_VERSION")
}
~~~

`*_VERSION` là placeholder, không phải literal có thể resolve. Các version cần được quản lý qua version catalog, platform hoặc cấu hình tập trung của dự án.

### 4.1. Khi nào MapStruct API cần là api thay vì implementation?

Nếu đây là một **thư viện công khai** mà public method/annotation trong contract của nó lộ trực tiếp kiểu từ MapStruct hoặc API khác, Gradle `java-library` có thể cần `api(...)` để consumer nhận compile dependency.

Với ứng dụng sử dụng MapStruct như implementation detail, `implementation(...)` thường phù hợp. Điều quyết định là **hợp đồng xuất ra cho consumer**, không phải nhãn “thư viện sinh mã”.

### 4.2. Tách processor path cho test

Nếu các test Java có annotation tạo mã riêng, chúng có thể cần processor path riêng. Không được giả định `annotationProcessor` cho main source tự cấp đầy đủ cho `testAnnotationProcessor` trong mọi cấu hình.

Nếu test chỉ gọi code đã được biên dịch trong main source, chúng không nhất thiết cần chạy lại MapStruct processor. Cần phân biệt:

1. Main source khai báo mapper.
2. Test source khai báo thêm mapper.
3. Test source chỉ gọi mapper class đã được sinh ở main.

### 4.3. Dùng Java toolchain và --release đúng cách

Ví dụ muốn chạy build/compiler bằng JDK 21 nhưng phát hành bytecode tương thích Java 17:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Ba vấn đề cần tách riêng:

- **JDK thực thi compiler và annotation processors**: ví dụ JDK 21.
- **Source/API/bytecode target**: do `--release 17` điều chỉnh.
- **JDK runtime tối thiểu của sản phẩm**: cần thử artifact trên Java 17.

`--release` không khiến Lombok cũ “nghĩ rằng nó đang chạy dưới javac 17”. Processor vẫn chạy trong compiler JDK 21 và cần tương thích với javac của JDK 21.

Đây là một trong những nhầm lẫn thường gặp nhất khi nâng toolchain.

## 5. Cấu hình Maven Compiler Plugin

Với Maven, có thể cấu hình release và annotation processors bằng `maven-compiler-plugin`. Ví dụ khung:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<dependencies>
    <dependency>
        <groupId>org.mapstruct</groupId>
        <artifactId>mapstruct</artifactId>
        <version>MAPSTRUCT_VERSION</version>
    </dependency>

    <dependency>
        <groupId>org.projectlombok</groupId>
        <artifactId>lombok</artifactId>
        <version>LOMBOK_VERSION</version>
        <scope>provided</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>COMPILER_PLUGIN_VERSION</version>
            <configuration>
                <release>17</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.projectlombok</groupId>
                        <artifactId>lombok</artifactId>
                        <version>LOMBOK_VERSION</version>
                    </path>
                    <path>
                        <groupId>org.mapstruct</groupId>
                        <artifactId>mapstruct-processor</artifactId>
                        <version>MAPSTRUCT_VERSION</version>
                    </path>
                    <path>
                        <groupId>org.projectlombok</groupId>
                        <artifactId>lombok-mapstruct-binding</artifactId>
                        <version>BINDING_VERSION</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là **mẫu minh họa** cho Maven/JDK/plugin hỗ trợ cấu hình nêu trên. Không sao chép các giá trị placeholder vào dự án thực.

Một số phiên bản mới của Maven Compiler Plugin còn cung cấp mô hình khai báo processor dependency khác. Nên chọn một cơ chế được plugin và JDK mục tiêu hỗ trợ, rồi xác nhận processor thực sự được phát hiện. Không gộp các mẫu cấu hình không tương thích của nhiều thế hệ plugin chỉ để “thử cho chạy”.

### 5.1. Scope provided của Lombok không đồng nghĩa annotation processing đã bật

Đặt Lombok ở `provided` cho phép source compile tham chiếu annotation nhưng **không tự bảo đảm** processor được chạy, đặc biệt khi build chỉ cho phép processor nằm trên processor path riêng.

`annotationProcessorPaths` thể hiện rõ processor nào được phép nạp. Nếu build không kích hoạt processor, getters/builders vẫn thiếu dù Maven đã tải `lombok.jar`.

### 5.2. Không cài processor trên runtime classpath của server

Các artifact `mapstruct-processor` và thư viện hỗ trợ compiler thường không nên được đưa vào bản phân phối runtime nếu chỉ dùng ở build. Với Maven, đánh giá package JAR/WAR và dependency scopes thực tế; không giả định transitive dependency tự biến mất như mong muốn nếu chưa kiểm chứng artifact.

## 6. Thay đổi hành vi annotation processing của javac qua JDK

Bên cạnh tính tương thích của processor, bản thân `javac` cũng phát triển cách **tự động phát hiện** processor.

Ở các JDK cũ, dự án đôi khi “vô tình chạy được” vì javac tìm annotation processor từ classpath dù chưa có processor path rõ ràng. Trên JDK mới hơn, compiler có thể yêu cầu kích hoạt annotation processing hoặc khai báo processor tường minh hơn; ví dụ từ JDK 23, mặc định tự chạy processor không được phép dựa vào như trước nếu không có cấu hình thích hợp.

Vì vậy, khi migration, **đừng phụ thuộc vào processor được phát hiện tình cờ từ compile classpath**. Cần khai báo explicit processor path/processor module path, hoặc danh sách processor và chế độ xử lý mà JDK/build tool hỗ trợ.

### 6.1. Những tùy chọn javac liên quan

| Tùy chọn | Mục đích |
|---|---|
| `-processorpath <path>` / `--processor-path <path>` | Chỉ ra nơi tìm annotation processors |
| `-processor <names>` | Chỉ định processor class cụ thể |
| `-proc:none` | Không chạy annotation processing |
| `-proc:only` | Chỉ chạy processing, không tạo class code thông thường |
| `-proc:full` | Chạy processing và compilation khi JDK hỗ trợ tùy chọn này |
| `-s <directory>` | Thư mục sinh source từ annotation processing |
| `-XprintRounds` | In thông tin các vòng processor để chẩn đoán |
| `-XprintProcessorInfo` | In thông tin processor được compiler sử dụng |

Không phải mọi option xuất hiện trên mọi JDK theo cùng cú pháp; ví dụ `-proc:full` được bổ sung trong một số JDK hiện đại. Đọc `javac -help` hoặc tài liệu của compiler đang chạy thay vì giả định một command line đúng cho tất cả.

### 6.2. Chạy thử bằng javac trực tiếp

Ví dụ minh họa với classpath và processor path đã chuẩn bị:

~~~bash
javac \
  --release 17 \
  -cp "lib/mapstruct-api.jar:lib/lombok.jar" \
  -processorpath "lib/lombok.jar:lib/mapstruct-processor.jar:lib/lombok-mapstruct-binding.jar" \
  -s build/generated-src \
  -d build/classes \
  src/main/java/com/example/*.java
~~~

Đây là ví dụ shell kiểu Unix; trên Windows, dấu phân cách classpath/processor path là `;` thay cho `:`. Tên JAR chỉ là minh họa, không phải tên artifact Maven được bảo đảm.

Trong dự án thực, ưu tiên Maven/Gradle quản lý classpath và processor path. Chạy javac trực tiếp hữu ích để cô lập lỗi, nhưng không thay cho build và packaging thực tế.

### 6.3. Compile thành công không chứng minh processor đã chạy

Nếu mapper interface không được gọi ở compile time, build có thể đạt dù chưa sinh implementation. Tương tự, một class chỉ chứa Lombok annotation nhưng chưa có consumer gọi getter vẫn có thể không làm lỗi lộ ra.

Vì vậy, cần kiểm tra:

- Output generated source có `*MapperImpl.java` mong đợi không?
- Compiled class có `*MapperImpl.class` không?
- Consumer thật có gọi được các member Lombok sinh ra không?
- Mappers được DI container phát hiện không?
- Generated implementation có được đóng gói vào artifact cuối không?

## 7. Lombok có quan hệ đặc biệt với nội bộ javac

Lombok không chỉ đọc annotation; nó tích hợp sâu vào compiler internals. Vì vậy, rủi ro khi nâng JDK thường xuất hiện ngay khi javac khởi tạo processor hoặc thực hiện AST transformation.

### 7.1. Dấu hiệu incompatibility

Một số triệu chứng thường gặp:

~~~text
java.lang.NoSuchFieldError:
  Class com.sun.tools.javac.tree.JCTree$JCImport
  does not have member field ...

java.lang.IllegalAccessError:
  class ... cannot access class com.sun.tools.javac... 
  because module jdk.compiler does not export ...
~~~

Không có nghĩa mọi lỗi `NoSuchFieldError` đều do Lombok. Nhưng nếu stack trace có `lombok.javac` và các class `com.sun.tools.javac.*`, cần kiểm tra ngay **Lombok version so với JDK compiler version**.

### 7.2. Vì sao thêm --add-opens không phải sửa lỗi tận gốc?

Một số workaround lịch sử:

~~~text
--add-opens=jdk.compiler/com.sun.tools.javac.processing=ALL-UNNAMED
--add-exports=jdk.compiler/com.sun.tools.javac.tree=ALL-UNNAMED
~~~

Các dòng chỉ là ví dụ quyền mở/exports, **không phải cấu hình khuyến nghị để sao chép**. Chúng có thể giải quyết một số vấn đề module access trong bối cảnh cụ thể, nhưng không sửa được việc nội bộ javac đã đổi method, field, AST node hoặc semantics.

Hơn nữa:

- `--add-opens` và `--add-exports` không có cùng tác dụng.
- Cờ cấp cho JVM chạy compiler có thể khác cờ truyền vào javac.
- Build daemon và forked compiler có cấu hình JVM riêng.
- Mở nhiều package compiler có thể che dấu Lombok lỗi thời.

Ưu tiên dùng phiên bản Lombok được công bố hỗ trợ JDK đang chạy và loại dần workaround khi không cần.

### 7.3. Javac của build JDK quyết định rủi ro

Một dự án dùng:

~~~text
Build JDK: 21
javac --release: 17
Runtime JDK baseline: 17
~~~

Lombok chạy trong compiler JDK 21. Vì vậy, tương thích của Lombok cần được xét với **JDK 21**, không chỉ Java 17.

Nếu nhóm nâng build runner lên JDK mới hơn nhưng không đổi `--release`, Lombok vẫn có thể ngừng hoạt động vì compiler internals thay đổi.

### 7.4. Không mặc định mọi compiler hỗ trợ Lombok như nhau

IDE có thể dùng compiler riêng hoặc plugin xử lý editor model. IntelliJ, Eclipse/JDT, javac và build tool có những tích hợp khác nhau.

Một dự án có thể:

- IDE không gạch lỗi nhưng Maven build thất bại.
- Maven build thành công nhưng IDE báo thiếu getter.
- Eclipse compiler hoạt động khác javac.
- Build qua Gradle daemon dùng JDK khác JDK trên terminal.

Chẩn đoán phải bắt đầu bằng việc ghi **compiler nào thực sự chạy**, plugin nào đang bật và JDK version của cả build/daemon.

## 8. MapStruct sinh mã như thế nào?

MapStruct tạo implementation của mapper dựa trên kiểu nguồn/đích và mapping configuration.

Ví dụ hai DTO:

~~~java
public class CustomerEntity {
    private Long id;
    private String fullName;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getFullName() { return fullName; }
    public void setFullName(String fullName) {
        this.fullName = fullName;
    }
}
~~~

~~~java
public class CustomerDto {
    private Long id;
    private String name;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getName() { return name; }
    public void setName(String name) {
        this.name = name;
    }
}
~~~

Mapper:

~~~java
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

@Mapper
public interface CustomerMapper {
    @Mapping(source = "fullName", target = "name")
    CustomerDto toDto(CustomerEntity source);
}
~~~

MapStruct sẽ cố sinh implementation lấy `source.getFullName()` để gán vào `target.setName(...)`. Nếu getter/setter thay đổi, compiler có thể báo lỗi ngay lúc sinh hoặc biên dịch mapper.

### 8.1. Source sinh ra là Java code bình thường

Một ưu điểm của MapStruct là output không phụ thuộc reflection để map những property đơn giản. Vì vậy, có thể đọc code đã được sinh và đánh giá:

- Getter/setter hoặc constructor được gọi.
- Conversion method nào được chọn.
- Cách xử lý null.
- Mapping cho collection/map/enum.
- Cách sử dụng builder.
- Dependency injection pattern.
- Các mapping bị bỏ qua hoặc mặc định.

Generated code có thể thay đổi khi MapStruct version, source model hoặc compiler đổi. Không nên coi tên local variable hay thứ tự câu lệnh sinh ra là hợp đồng public, trừ khi dự án có yêu cầu đặc biệt và kiểm chứng tương ứng.

### 8.2. MapStruct API không tự bảo đảm implementation được đóng gói

Nếu thiếu processor hoặc source output bị loại khi compile/package, interface `CustomerMapper` vẫn tồn tại nhưng `CustomerMapperImpl` có thể không có trong artifact.

Với mô hình factory:

~~~java
import org.mapstruct.factory.Mappers;

CustomerMapper mapper =
        Mappers.getMapper(CustomerMapper.class);
~~~

runtime cần implementation có thể được tạo/nạp theo convention tương ứng. Với Spring hoặc CDI component model, mapper implementation cần được sinh với annotation component/injection phù hợp và container phải scan được.

### 8.3. Component model có thể tạo dependency bổ sung

Ví dụ:

~~~java
@Mapper(componentModel = "spring")
public interface CustomerMapper {
    CustomerDto toDto(CustomerEntity source);
}
~~~

Implementation được sinh có thể sử dụng Spring annotations và được container quản lý. Điều đó làm build và runtime phụ thuộc thêm vào Spring context và cấu hình quét component.

Nếu dùng `componentModel = "default"`, mapper thường được lấy qua MapStruct factory. Không copy cả hai mô hình rồi giả định bean xuất hiện trong DI container khi component model chưa đúng.

## 9. Vì sao Lombok + MapStruct dễ gặp lỗi trong cùng compile?

Xét source Lombok:

~~~java
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class Account {
    private long id;
    private String displayName;
}
~~~

Và mapper:

~~~java
import org.mapstruct.Mapper;

@Mapper
public interface AccountMapper {
    AccountDto toDto(Account source);
}
~~~

MapStruct cần nhìn thấy `getId()` và `getDisplayName()` như properties của `Account`. Lombok tạo những method đó trong quá trình compile nhưng **không sinh cùng một file Java mới theo cơ chế thông thường**.

Vì vậy, nếu MapStruct phân tích type model trước khi việc Lombok cập nhật AST trở nên khả dụng, MapStruct có thể nhận diện thiếu property.

Một lỗi điển hình:

~~~text
Unknown property "displayName" in result type ...
No property named "displayName" exists in source parameter(s)
~~~

Lỗi cũng có thể thực sự do typo, getter visibility, builder configuration hoặc quy tắc accessor; cần xác định bằng chứng trước khi quy về thứ tự processor.

### 9.1. Vai trò của lombok-mapstruct-binding

Trong những cấu hình Lombok và MapStruct tương ứng, `lombok-mapstruct-binding` là integration adapter giúp MapStruct phối hợp với các type được Lombok biến đổi. Đối với các thế hệ Lombok hiện đại, đây thường là dependency cần xét khi hai thư viện cùng xử lý source.

Ví dụ Gradle:

~~~groovy
annotationProcessor(
    "org.projectlombok:lombok-mapstruct-binding:BINDING_VERSION"
)
~~~

Cấu hình Maven đưa binding vào `annotationProcessorPaths` cùng Lombok và MapStruct processor.

Không nên thay binding bằng cách cố “sắp xếp thứ tự annotationProcessor dependencies” rồi coi đó là hợp đồng ổn định. Javac không bảo đảm phụ thuộc nội tại của một processor vào side effect không chuẩn từ processor khác chỉ dựa trên thứ tự liệt kê các JAR.

### 9.2. Tránh nhầm MapStruct mapping lỗi với Lombok lỗi

Khi MapStruct báo property không tồn tại:

1. Xem property thực sự có trong source không.
2. Xem Lombok annotation có đúng phạm vi không.
3. Xác nhận Lombok processor đã chạy và được javac hỗ trợ.
4. Xem getter/setter thực sự có trong compiled class hoặc qua `delombok`.
5. Kiểm tra binding và MapStruct processor path.
6. Xem mapper được compile trong cùng module/source set hay từ dependency đã build.
7. Kiểm tra tên property theo JavaBeans convention hoặc custom accessor naming strategy.
8. Xem builder, fluent accessor, record hoặc constructor mapping có thay đổi không.

Không thêm `@Mapping(ignore = true)` chỉ để làm lỗi biến mất nếu trường đó là dữ liệu nghiệp vụ bắt buộc.

## 10. @Builder, @Value, @Accessors và constructor mapping

Lombok có nhiều annotation thay đổi shape của API class. MapStruct phải chọn cách tạo object đích tương ứng.

### 10.1. Setter mapping

Với class có public no-args constructor và setter, MapStruct thường có thể tạo instance rồi gọi setter.

~~~java
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class ItemDto {
    private String sku;
    private int quantity;
}
~~~

Đây là dạng mapping dễ nhận diện qua JavaBeans accessor convention.

### 10.2. Immutable class với builder

~~~java
import lombok.Builder;
import lombok.Value;

@Value
@Builder
public class ItemView {
    String sku;
    int quantity;
}
~~~

Lombok có thể sinh builder và getter; class immutable không có setter thường. MapStruct cần nhận diện builder hoặc constructor phù hợp.

Các lỗi hay gặp:

- Builder factory không được phát hiện.
- Builder method name bị đổi bởi Lombok customization.
- `@Accessors(fluent = true)` khiến property convention khác.
- Constructor được sinh có visibility không phù hợp.
- Một processor nâng cấp thay đổi builder detection.
- Mapping tới field mới không có builder method.
- Cấu hình MapStruct vô hiệu hóa builder ngoài ý muốn.

Không nên đánh giá API chỉ qua field source. Sau khi compile, constructor, getter và builder method mới là các phần mà consumer có thể sử dụng.

### 10.3. @Accessors có thể ảnh hưởng naming

Ví dụ:

~~~java
import lombok.Getter;
import lombok.Setter;
import lombok.experimental.Accessors;

@Getter
@Setter
@Accessors(fluent = true)
public class Config {
    private String region;
}
~~~

Đường gọi có thể theo kiểu `config.region()` và `config.region("VN")` thay vì `getRegion()`/`setRegion()`. Điều này ảnh hưởng cách MapStruct và các framework khác nhận diện properties.

Cần kiểm tra version MapStruct, cấu hình accessor naming strategy và Lombok integration phù hợp. Một số convention không được hỗ trợ tự động trong mọi thế hệ.

### 10.4. Record và source features mới

Java record tự cung cấp accessor dạng `name()`, không phải getter `getName()`. MapStruct version phù hợp có thể hỗ trợ mapping record, nhưng cần xác minh với JDK/source level và MapStruct thực tế.

Ví dụ:

~~~java
public record ProductDto(String code, long price) {}
~~~

Không cần Lombok `@Getter` chỉ để có accessor của record. Khi chuyển DTO từ class Lombok sang record, binary API và constructor/accessor shape có thể thay đổi; cần kiểm tra consumer cũ, serializer và mapper.

## 11. Lombok thay đổi public API dù chỉ hiện dưới dạng annotation

Nhiều thành phần do Lombok sinh là API nhị phân có thật:

- Getter/setter.
- Constructor.
- `equals` và `hashCode`.
- `toString`.
- Builder class và builder methods.
- Wither hoặc helper methods.
- `@SneakyThrows` ảnh hưởng cách code trình bày checked exception.
- `@SuperBuilder` ảnh hưởng hệ thống builder trong class hierarchy.

Ví dụ:

~~~java
import lombok.AllArgsConstructor;
import lombok.Getter;

@Getter
@AllArgsConstructor
public class ApiModel {
    private final String id;
}
~~~

Consumer đã compile có thể gọi constructor `ApiModel(String)` và method `getId()`. Nếu đổi annotation khiến constructor khác, xóa getter hoặc đổi visibility, bytecode consumer cũ có thể gặp `NoSuchMethodError`.

Đó là **binary compatibility risk** dù trong source không có dòng constructor nào được viết thủ công.

### 11.1. Annotation version đổi có thể đổi generated shape

Nâng Lombok có thể sửa lỗi, thay validation, xử lý edge cases hoặc cách generate code với tính năng nhất định. Không nên mặc định code generated của hai version giống byte-for-byte hoặc luôn giữ cùng public member set.

Với public library, cần so sánh class file thực tế bằng:

~~~bash
javap -classpath build/classes/java/main -p -s com.example.ApiModel
~~~

Điều quan trọng là **method name, descriptor, visibility và behavior**, không phải source có annotation giống nhau.

### 11.2. Tùy chọn lombok.config là một phần của build input

File `lombok.config` có thể điều chỉnh cách Lombok sinh code, ví dụ accessors, generated annotation, cấu trúc constructor hoặc policy tương ứng.

Một thay đổi config ở parent directory hoặc module khác có thể ảnh hưởng source output mà người viết class không thấy trực tiếp.

Khi migration:

- Xác định những file `lombok.config` có hiệu lực.
- Kiểm tra cách cấu hình được kế thừa theo folder.
- Ghi version Lombok và các option quan trọng.
- Kiểm tra config nằm trong đúng project/module.
- Đảm bảo clean build nhận cùng cấu hình trong CI.

## 12. Generated source, generated class và reproducibility

MapStruct thường sinh Java source trong build output. Những đường dẫn thường gặp:

- Gradle: `build/generated/sources/annotationProcessor/java/main/`.
- Maven: `target/generated-sources/annotations/`.

Đường dẫn có thể khác theo plugin, custom source set, Kotlin/kapt hoặc cấu hình build; hãy xem output directory thực tế thay vì hardcode.

### 12.1. Có nên commit generated source?

Không có một câu trả lời đúng cho mọi dự án.

**Không commit** giúp tránh nhiễu diff và cập nhật thủ công, nếu build tái tạo deterministic và CI luôn chạy processor.

**Commit có kiểm soát** có thể hữu ích ở môi trường build đặc biệt hoặc khi output là một artifact được quản trị riêng, nhưng phải có quy tắc không sửa tay và kiểm chứng output sinh ra khớp với input.

Dù chọn cách nào, cần đảm bảo:

1. Generated source không bị sửa thủ công để che lỗi processor.
2. Clean build sinh lại đủ implementation.
3. Artifact cuối chứa generated classes cần thiết.
4. Thư mục output cũ không khiến build “xanh giả”.
5. CI không phụ thuộc IDE từng chạy generator trên máy cá nhân.

### 12.2. Clean build giúp phát hiện mã sinh cũ

Một `MapperImpl.class` còn trong build directory có thể che việc processor đã không chạy trong lần compile mới. Vì vậy, khi thay JDK hoặc cấu hình processor, chạy clean build trong môi trường cô lập và xem output được tạo từ đầu.

Trong hướng dẫn học tập có thể dùng:

~~~bash
./gradlew clean compileJava
~~~

hoặc:

~~~bash
mvn clean compile
~~~

Các lệnh là **hướng dẫn cho người học thực hành**, không phải bước đã thực hiện trong quá trình soạn bài này.

### 12.3. Delombok hỗ trợ xem code tương đương

Công cụ `delombok` giúp biểu diễn source sau xử lý Lombok ở dạng Java dễ đọc trong nhiều trường hợp. Đây là công cụ chẩn đoán hữu ích để hiểu getter, constructor, builder và annotation-generated code.

Tuy nhiên, đừng coi output delombok luôn là bytecode thực cuối cùng; hãy dùng `javap` khi kiểm tra binary API và class file version.

## 13. Những lỗi javac phổ biến và cách chẩn đoán

| Lỗi hoặc triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| `cannot find symbol: getX()` | Lombok processor không chạy, method bị đổi tên, thiếu annotation | Processor path, Lombok version, delombok/javap |
| `cannot find symbol: builder()` | Builder không được sinh hoặc tùy chỉnh tên | Lombok annotation/config và compiled class |
| MapStruct báo unknown source property | Getter không có hoặc MapStruct chưa thấy AST Lombok | Lombok/binding, accessor convention, generated source |
| Không có `*MapperImpl` | MapStruct processor không chạy hoặc compile chưa thành công | Processor path, javac rounds, output dir |
| `NoClassDefFoundError` với MapperImpl | Generated class thiếu trong runtime artifact | Packaging, classpath và DI discovery |
| `NoSuchMethodError` khi gọi getter/constructor | Binary API Lombok-generated đã đổi | So sánh `javap -s` bản cũ/mới |
| `NoSuchFieldError` trong `com.sun.tools.javac.*` | Lombok/compiler internals không tương thích | JDK compiler version, Lombok support |
| `IllegalAccessError` liên quan `jdk.compiler` | Truy cập nội bộ compiler bị module hạn chế | Nâng Lombok, xem cờ JVM workaround còn tồn tại |
| `ClassNotFoundException` processor | Processor dependency hoặc registration thiếu | Annotation processor path |
| `FilerException: Attempt to recreate a file` | Hai vòng/processor hoặc output trùng, generated source cũ | Processor configuration, clean build, duplicate generation |
| `UnsupportedClassVersionError` của processor | Processor JAR được build cho JDK cao hơn | Build JDK và class file version |
| `UnsupportedClassVersionError` khi chạy app | Generated/application bytecode cao hơn runtime | `--release` và dependency baseline |
| Build IDE khác CI | Compiler/JDK/processor path khác | Toolchain, IDE plugin và build log |
| DI không tìm thấy mapper bean | Component model, scan hoặc source generation sai | Generated annotations và runtime framework |

**Không mặc định mọi lỗi compile đều do Lombok.** Ví dụ một MapStruct property typo thực sự phải sửa mapping; thêm binding không làm nó tự trở thành hợp lệ.

### 13.1. Đọc stack trace theo tầng

Một lỗi javac có thể nằm ở:

1. Build tool daemon hoặc compiler fork.
2. Annotation processor discovery.
3. Lombok transformer.
4. MapStruct processor.
5. Generated Java source compile.
6. Classpath resolution.
7. Artifact packaging và runtime class loading.

Lỗi ở bước nào cần dữ liệu chẩn đoán bước đó. Ví dụ runtime không có `MapperImpl` có thể do processor không chạy, nhưng cũng có thể do file class bị minimizer/shader loại bỏ.

### 13.2. Ghi JDK thực tế thay vì dựa vào biến JAVA_HOME

Các kiểm tra hữu ích:

~~~bash
java -version
javac -version
./gradlew --version
mvn -version
~~~

Gradle daemon có thể chạy dưới JDK khác với `java` trên shell; Maven Toolchains cũng có thể chọn compiler khác với JVM chạy Maven. Khi phân tích, cần ghi cả:

- JDK chạy build tool.
- JDK chạy javac.
- JDK runtime test.
- `--release` hoặc source/target compatibility.
- Lombok/MapStruct/build plugin versions.

## 14. Diagnostic logging cho annotation processing

Khi cần xác định processor nào thực sự chạy, có thể dùng các tùy chọn javac:

~~~text
-XprintRounds
-XprintProcessorInfo
~~~

Ví dụ Gradle minh họa:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '-XprintRounds',
        '-XprintProcessorInfo'
    ]
}
~~~

Đây là cấu hình chẩn đoán tạm thời. Không nhất thiết cần giữ log chi tiết trên mọi build production vì có thể tăng kích thước log.

Điểm cần đọc:

- Processor của Lombok được phát hiện không?
- MapStruct processor có tham gia không?
- Có vòng processing sinh `MapperImpl` không?
- Lỗi xuất hiện ở vòng nào?
- Generated source directory có đúng không?
- Có processor được nạp từ version không mong muốn không?

### 14.1. Đọc dependency graph cho processor path

Với Gradle, kiểm tra configurations liên quan:

~~~bash
./gradlew dependencies --configuration annotationProcessor
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration testAnnotationProcessor
~~~

Với Maven, xem effective POM và compiler plugin configuration, rồi đối chiếu dependency tree và đường dẫn processor mà plugin dùng.

Một JAR Lombok xuất hiện trên compileClasspath nhưng **không có trong annotationProcessor** là dấu hiệu cần chú ý ở Gradle.

### 14.2. Không đoán bằng thứ tự JAR khi có nhiều processor

Trong Java annotation processing, việc processor được khám phá và tương tác có những quy tắc riêng. Một thay đổi tình cờ ở classpath hoặc build tool có thể làm lỗi biến mất trong một lần chạy mà không chứng minh giải pháp bền vững.

Thay vì reorder dependency để “sửa”, cần:

- Cấu hình đúng processor path.
- Bổ sung binding được dự án khuyến nghị khi tương thích.
- Căn version chính xác.
- Dùng test clean build và output inspection.
- Cô lập mapper/Lombok source nếu kiến trúc cần.

## 15. Tách module để giảm coupling giữa Lombok và MapStruct

Trong hệ thống phức tạp, một chiến lược là biên dịch các model Lombok trước, rồi để MapStruct của module khác sử dụng compiled classes.

Ví dụ:

~~~text
:domain-model
  - Lombok DTO/entities
  - compileJava tạo getter/constructor trong class files

:mapper
  - phụ thuộc :domain-model
  - MapStruct interfaces
  - compileJava sinh MapperImpl

:application
  - sử dụng :domain-model và :mapper
~~~

Ưu điểm:

- MapStruct đọc class API đã được compile, giảm phụ thuộc timing của AST transformation trong cùng compilation.
- Có thể version module model độc lập.
- Dễ kiểm tra binary API và public accessor shape.

Nhược điểm:

- Thêm module/build complexity.
- Cần quản lý dependency direction rõ.
- Có thể gây cyclic dependency nếu model phụ thuộc mapper.
- Không thay thế việc nâng Lombok khi javac version mới không tương thích.

Tách module là lựa chọn kiến trúc, không phải giải pháp bắt buộc cho mọi project.

## 16. Annotation processing với JPMS và module-info.java

Trong một project modular, compiler có thể dùng module path, processor path hoặc processor module path tùy cấu hình. Những vấn đề cần phân biệt:

- `module-info.java` của ứng dụng quyết định `requires`, `exports` và `opens` cho code runtime.
- Annotation processor được nạp trong môi trường compiler, không nhất thiết nằm trong module graph runtime.
- Lombok tương tác compiler internals, nên module access của `jdk.compiler` có thể quan trọng.
- MapStruct sinh code vào package/module của ứng dụng, và code được sinh phải biên dịch theo các quy tắc module của source.
- Nếu generated mapper dùng DI annotations, module phải có dependency thích hợp và runtime configuration phù hợp.

Không nên thêm các `requires`/`opens` vào module runtime chỉ để chữa một lỗi thiếu annotation processor ở build. Ngược lại, nếu generated code bị runtime reflection của DI/serializer truy cập trong named module, có thể cần opens của package ứng dụng cho framework.

### 16.1. Khi nào cần kiểm tra module opens?

Ví dụ generated mapper chỉ gọi public getter/setter, có thể không cần deep reflection. Nhưng framework DI/serialization sử dụng reflection vào implementation, constructor hoặc field có thể cần module openness.

Cần tách:

1. Lỗi **compile-time** khi processor không tạo được source.
2. Lỗi **runtime linkage** khi MapperImpl không có.
3. Lỗi **runtime reflective access** khi framework không instantiate hoặc inject được.
4. Lỗi **JDK compiler internals** do Lombok.

Một cờ module mở quyền chung không sửa được tất cả bốn nhóm.

## 17. Maven/Gradle incremental compilation và build cache

Annotation processing có thể tương tác với incremental build:

- Processor có thể phụ thuộc vào type graph rộng hơn một source file.
- Lombok thay AST khiến thông tin đầu vào của compiler trở nên phức tạp.
- MapStruct sinh source từ type model, nên một thay đổi property nguồn/đích phải khiến mapper được sinh lại.
- Build cache có thể che lỗi nếu output cũ vẫn tồn tại.
- Khi đổi JDK hoặc processor version, cache key phải phản ánh đầu vào mới.

Một số processor công bố hỗ trợ incremental annotation processing với những điều kiện cụ thể. Không nên giả định mọi combination Lombok–MapStruct–Gradle đều incremental-safe trong mọi version.

### 17.1. Phép thử thực dụng khi nâng toolchain

Sau khi cấu hình phiên bản mới:

1. Clean compile từ workspace trống.
2. Thay đổi một field model mà mapper sử dụng.
3. Compile lại và kiểm tra generated mapper được cập nhật.
4. Đổi annotation mapping và kiểm tra output mới.
5. Xóa generated output rồi compile lại.
6. Kiểm tra build cache không phục hồi implementation từ input cũ.
7. Chạy test trên artifact và runtime JDK tối thiểu.

Nếu một build chỉ đạt khi không chạy clean hoặc khi IDE đã generate code trước, quy trình không đáng tin cho CI.

### 17.2. Deterministic generated output

Một processor có thể thêm timestamp, version comment hoặc metadata trong source được sinh. Những chi tiết đó có thể làm checksum/generated source diff đổi giữa build dù logic mapper giống nhau.

Nếu dự án cần reproducible artifact:

- Cấu hình option giảm metadata không ổn định nếu processor hỗ trợ.
- Khóa JDK và processor versions.
- So sánh semantic API/behavior thay vì tin rằng mọi dòng generated source luôn bất biến.
- Kiểm tra artifact checksum trong quy trình release.
- Không tự chỉnh generated source sau compile.

## 18. Processor options và cấu hình MapStruct

MapStruct có các option cấu hình được truyền cho annotation processor hoặc qua mapper/config annotations.

Ví dụ:

~~~java
import org.mapstruct.Mapper;
import org.mapstruct.ReportingPolicy;

@Mapper(unmappedTargetPolicy = ReportingPolicy.ERROR)
public interface OrderMapper {
    OrderDto toDto(OrderEntity source);
}
~~~

Policy `ERROR` yêu cầu compiler báo lỗi khi target property không được map theo các quy tắc của MapStruct. Điều này có thể giúp phát hiện DTO thay đổi sau migration thay vì bỏ qua field quan trọng.

Một số build cũng đặt processor argument:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '-Amapstruct.defaultComponentModel=spring'
    ]
}
~~~

Giá trị này chỉ là ví dụ cho dự án có Spring; không áp đặt một default component model nếu ứng dụng không dùng Spring.

### 18.1. Cấu hình processor là đầu vào sinh mã

Khi source không đổi nhưng processor options đổi, generated code có thể khác:

- Component model: default, Spring, CDI hoặc cách khác.
- Injection strategy: field, constructor hoặc setter theo cấu hình.
- Null handling: có check, bỏ qua, trả về default.
- Unmapped target policy: ignore, warn hoặc error.
- Builder detection và mapping strategy.
- Package/class name conventions cho implementation.

Các option này là **một phần của build contract**, cần được version hóa và kiểm thử giống dependency.

### 18.2. Nâng MapStruct có thể làm lộ mapping thiếu

MapStruct mới có thể nhận diện property hoặc báo diagnostics chặt hơn phiên bản cũ. Khi compile lỗi:

- Đọc đúng property/type ở cả hai phía.
- Kiểm tra mapping inheritance.
- Kiểm tra constructor/builder target.
- Kiểm tra overloaded conversion method.
- Kiểm tra enum mapping và unmapped values.
- Kiểm tra annotation/configuration được kế thừa.
- So sánh generated code trước và sau khi nâng nếu có bản baseline.

Đừng tự động hạ `unmappedTargetPolicy` xuống IGNORE chỉ để build qua, vì điều đó có thể che sai dữ liệu.

## 19. Enum và các kiểu đổi sau migration

MapStruct có khả năng map enum và collection, nhưng hợp đồng dữ liệu cần được kiểm tra.

Ví dụ:

~~~java
public enum OldState {
    NEW, DONE, FAILED
}

public enum NewState {
    CREATED, COMPLETED, ERROR
}
~~~

Có thể viết mapping tường minh:

~~~java
import org.mapstruct.Mapper;
import org.mapstruct.ValueMapping;

@Mapper
public interface StateMapper {
    @ValueMapping(source = "NEW", target = "CREATED")
    @ValueMapping(source = "DONE", target = "COMPLETED")
    @ValueMapping(source = "FAILED", target = "ERROR")
    NewState toNewState(OldState state);
}
~~~

Nếu producer thêm một enum constant mới, mapper có thể cần cập nhật theo rule cụ thể. Đừng mặc định MapStruct sẽ chọn một mapping nghiệp vụ đúng chỉ vì tên gần giống.

Khi dùng Lombok `@Value` hoặc `@Builder` trong DTO immutable, phải kiểm tra constructor/builder mapping và hành vi null. Một mapping sai có thể không tạo compile error nếu field bị ignore hoặc default policy cho phép.

## 20. Source compatibility, binary compatibility và runtime compatibility

Code generation ảnh hưởng cả ba tầng:

| Tầng | Câu hỏi | Ví dụ |
|---|---|---|
| Source compatibility | Consumer compile lại có còn gọi được API? | Getter `getCode()` bị đổi thành `code()` |
| Binary compatibility | Bytecode cũ có tìm thấy member/descriptors không? | Constructor Lombok-generated biến mất |
| Compile tool compatibility | Processor có chạy với javac JDK đích? | Lombok cũ truy cập field nội bộ javac đã đổi |
| Generated-code compatibility | Output có biên dịch với `--release` đã công bố? | Mapper sinh code dùng API chỉ có ở JDK mới |
| Runtime compatibility | Artifact có đủ generated classes và dependency? | `OrderMapperImpl` không có trong JAR |
| Behavioral compatibility | Mapping/equals/builder có giữ semantics? | MapStruct bỏ trường tiền tệ sau DTO refactor |
| Framework compatibility | DI, reflection, module access có hoạt động? | Mapper generated không được Spring scan |

Đây là lý do cần kiểm tra cả **source đầu vào, generated source và compiled binary**, không chỉ kết quả `compileJava` cuối cùng.

### 20.1. Generated implementation có phải public API?

Một class `CustomerMapperImpl` thường là chi tiết triển khai do MapStruct sinh. Consumer nên phụ thuộc vào interface `CustomerMapper` hoặc component injection, không nên hardcode implementation class name nếu không có lý do được kiểm soát.

Nếu project thực sự expose `*MapperImpl` hoặc gọi constructor trực tiếp từ module khác, generated implementation đã trở thành một hợp đồng de facto và cần được đánh giá binary compatibility khi nâng processor.

### 20.2. Lombok-generated members có thể là API công khai

Ngược lại, getter/constructor/builder do Lombok sinh thường **chính là API được consumer gọi**. Nếu library phát hành chúng, đổi annotation có thể thay đổi contract. Cần so sánh class file/public descriptors giống bất kỳ code Java viết tay nào.

## 21. Kiểm chứng với javap và generated-sources

Sau khi build, kiểm tra kết quả thay vì suy đoán:

~~~bash
javap -classpath build/classes/java/main \
  -p -s com.example.Product

javap -classpath build/classes/java/main \
  -p -s com.example.ProductMapperImpl
~~~

Chú ý:

- Getter và constructor do Lombok sinh có tồn tại không?
- Access modifier và method descriptors có đúng không?
- Builder classes/methods có đúng hợp đồng không?
- MapperImpl implements interface và có các method mong đợi không?
- Method được compiler sinh có bridge/synthetic flag không?
- Class file major version có phù hợp JDK tối thiểu không?

Trong Maven, class files thường nằm dưới `target/classes`; trong Gradle, đường dẫn phụ thuộc source set và plugin.

### 21.1. Đọc generated source để phát hiện sai logic

Ví dụ generated mapper:

~~~java
@Override
public CustomerDto toDto(CustomerEntity source) {
    if (source == null) {
        return null;
    }

    CustomerDto target = new CustomerDto();
    target.setId(source.getId());
    // Nếu fullName -> name bị bỏ, dữ liệu bị mất.
    return target;
}
~~~

Nếu test chỉ kiểm tra đối tượng không null, nó sẽ bỏ sót dữ liệu không được map. Các test nên xác thực field quan trọng, conversion và null behavior.

### 21.2. Kiểm thử đúng artifact phát hành

Để đảm bảo không bị thiếu generated classes khi đóng gói:

~~~bash
jar tf build/libs/application.jar
~~~

Tìm `*MapperImpl.class`, DTO và classes liên quan. Với Spring Boot executable JAR hoặc nested JAR, đường dẫn class có thể theo cấu trúc packaging riêng; cần kiểm tra đúng artifact.

Không nên suy ra “class có trong build directory” thì “class có trong release JAR”.

## 22. IDE, CI và local build khác nhau như thế nào?

Lombok đặc biệt nhạy với IDE integration vì IDE phải hiểu code được sinh dù method chưa có trong source.

Một số nguyên nhân khác biệt:

- IDE bật/tắt annotation processing riêng.
- Plugin Lombok của IDE không khớp version source/build.
- IDE dùng JDK khác Gradle/Maven.
- Gradle toolchain khác JVM của Gradle daemon.
- Eclipse/JDT xử lý compilation khác javac.
- CI chạy clean build còn máy developer dùng output cũ.
- Caching và generated-sources directories được quản lý khác nhau.
- Maven/Gradle plugin version khác do wrapper hoặc profile.

Một quy tắc thực tế:

**CI build dùng đúng Gradle Wrapper/Maven Wrapper và toolchain được dự án công bố là nguồn phán quyết của build.** IDE cần được cấu hình để phản ánh quy trình đó, không phải ngược lại.

### 22.1. Khi IDE báo đỏ nhưng CLI build đạt

Kiểm tra:

1. IDE dùng đúng JDK language level.
2. Annotation processing có được bật không.
3. Plugin Lombok tương thích với IDE/JDK không.
4. IDE import project bằng Gradle/Maven model đúng không.
5. Generated source directories có được nhận diện không.
6. MapStruct processor có ở compiler processor path không.
7. Caches/index của IDE có cần được làm mới sau khi sửa cấu hình không.

Không cần thêm processor vào runtime artifact chỉ để làm editor ngừng báo lỗi.

### 22.2. Khi CLI build lỗi nhưng IDE không lỗi

Đừng xem editor màu xanh là bằng chứng. Cần kiểm tra compiler JDK thực tế của command line và CI. Một số IDE có thể mô phỏng member Lombok trong editor dù Gradle javac không thể chạy phiên bản Lombok đó.

## 23. Build an toàn khi nâng JDK từng bước

Một lộ trình thực tế có thể là:

### Giai đoạn A: Chụp baseline

Ghi lại:

- JDK dùng để compile và chạy runtime.
- Maven/Gradle Wrapper và compiler plugin version.
- Lombok, MapStruct và binding versions.
- Compiler `--release`, source/target.
- Processor path/processor options.
- Lombok config.
- Danh sách mapper generated files.
- Public API class file signatures của DTO/model được phát hành.
- Kết quả unit/integration test quan trọng.

### Giai đoạn B: Nâng công cụ sinh mã trước hoặc cùng build JDK

Đối chiếu khả năng hỗ trợ của Lombok, MapStruct và compiler plugin với JDK đích. Một cách giảm rủi ro là nâng các công cụ build cần thiết trong môi trường baseline trước, rồi mới chuyển compiler JDK, nhưng thứ tự cụ thể còn phụ thuộc version tương thích và yêu cầu project.

Nếu không thể nâng từng phần độc lập, thay đổi theo từng nhóm nhỏ có bằng chứng rõ.

### Giai đoạn C: Kích hoạt processor tường minh

Đảm bảo processor được khai báo ở processor path chứ không chỉ ở compile classpath. Kiểm tra binding Lombok–MapStruct nếu hai công cụ chạy cùng module.

### Giai đoạn D: Clean build trên JDK đích

Kiểm tra generated source được tạo, implementation được compile, bytecode đúng target, và không có lỗi liên quan đến `jdk.compiler`. Không dùng generated output cũ làm kết quả migration.

### Giai đoạn E: Kiểm tra generated behavior

Chạy:

- DTO/constructor/getter/builder tests.
- Mapper integration tests cho field quan trọng.
- Null/collection/enum/immutable mapping tests.
- DI bootstrap tests.
- Binary consumer cũ nếu library cam kết compatibility.
- Runtime smoke tests trên JDK tối thiểu.

### Giai đoạn F: Phát hành có bằng chứng

Lưu artifact checksum, compiler/JDK metadata, dependency graph, processor versions, test reports và những thay đổi generated API có liên quan.

Không tuyên bố “Lombok và MapStruct hỗ trợ Java mới” chỉ vì một module mẫu compile được. Phạm vi kiểm chứng phải phản ánh source/features và runtime integration thực tế.

## 24. Ma trận kiểm thử gợi ý

| Trục | Giá trị ví dụ | Kiểm tra |
|---|---|---|
| Compiler JDK | Baseline và JDK mới | Lombok javac internals |
| `--release` | JDK tối thiểu được hỗ trợ | Bytecode/API compatibility |
| Gradle/Maven plugin | Version được khóa | Processor discovery và options |
| Lombok | Version được duyệt | Getter/constructor/builder shape |
| MapStruct | Version được duyệt | Mapper source generation |
| Binding | Phiên bản tương thích | Lombok/MapStruct phối hợp |
| Source model | Class mutable, immutable, record | Accessor/constructor/builder |
| Mapper model | Default, Spring, CDI nếu dùng | Wiring/DI behavior |
| Build mode | Clean và incremental | Generated source freshness |
| Environment | CLI CI và IDE | Toolchain consistency |
| Runtime | JDK tối thiểu, JDK đích | Generated classes thực thi |

Không cần thử mọi tổ hợp vô hạn. Nên chọn **bộ version được hỗ trợ chính thức** và một vài đường migration quan trọng, rồi kiểm soát bằng CI.

## 25. Ví dụ migration tổng hợp: Lombok DTO + MapStruct mapper

Giả sử hệ thống có DTO:

~~~java
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class InvoiceDto {
    private final String number;
    private final String currency;
    private final long amountMinorUnits;
}
~~~

Entity:

~~~java
public class InvoiceEntity {
    private String number;
    private String currencyCode;
    private long minorUnits;

    public String getNumber() { return number; }
    public String getCurrencyCode() { return currencyCode; }
    public long getMinorUnits() { return minorUnits; }
}
~~~

Mapper:

~~~java
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

@Mapper
public interface InvoiceMapper {
    @Mapping(source = "currencyCode", target = "currency")
    @Mapping(source = "minorUnits", target = "amountMinorUnits")
    InvoiceDto toDto(InvoiceEntity source);
}
~~~

Trên JDK cũ, mapper tạo builder của `InvoiceDto` thành công. Khi chuyển JDK compiler mới, lỗi có thể xảy ra vì Lombok cũ không chạy được với javac. MapStruct vì vậy không nhận diện builder/getter và báo không có property ở target.

**Cách điều tra có cấu trúc:**

1. Ghi đúng JDK compiler đang chạy.
2. Xác nhận Lombok version được công bố hỗ trợ JDK đó.
3. Kiểm tra `annotationProcessor` chứa Lombok và MapStruct processor.
4. Thêm binding đúng thế hệ nếu cấu hình hai công cụ yêu cầu.
5. Clean build để loại bỏ generated source cũ.
6. Đọc `InvoiceMapperImpl.java`: nó có gọi `InvoiceDto.builder()` không?
7. Test một entity có `currencyCode = "VND"` và `minorUnits = 250000L`.
8. Xác minh DTO output giữ đúng cả ba field.
9. Kiểm tra class file của `InvoiceDto` và `InvoiceMapperImpl`.
10. Chạy artifact trên JDK runtime tối thiểu và kiểm tra DI/mapper factory.

Nếu output mapper vẫn sai sau khi build được, **không đánh dấu migration thành công**. Cần phân biệt compilation success với correctness của dữ liệu chuyển đổi.

## 26. Lỗi thực tế và hướng xử lý ngắn

### 26.1. "Lombok processor không load được ở JDK mới"

Điều tra stack trace, phiên bản javac/JDK và Lombok. Ưu tiên phiên bản Lombok được xác nhận tương thích; không giữ nhiều cờ exports/opens như giải pháp lâu dài.

### 26.2. "MapStruct không sinh implementation"

Kiểm tra processor path, chế độ processing, output directory, build plugin config và clean compilation. Có thể MapStruct API có mặt nhưng processor bị thiếu.

### 26.3. "Unknown property dù có @Getter"

Kiểm tra Lombok có thực sự tạo getter không; sau đó xem MapStruct/binding, property naming, fluent accessors và builder behavior.

### 26.4. "Ứng dụng khởi động nhưng DI không tìm thấy mapper"

Kiểm tra generated implementation có đúng component model và annotation framework, đã được đóng gói trong artifact và nằm trong package scan không.

### 26.5. "Compile trên Java 21 nhưng chạy Java 17 lỗi"

Kiểm tra `--release`, generated class file major version, dependency baseline và class được sinh bằng processor. Processor chạy được trên JDK 21 không tự chứng minh output tương thích Java 17.

### 26.6. "Mỗi máy cho kết quả khác"

Khóa build tool wrapper, JDK toolchain, processor versions, processor options và clean build. Kiểm tra IDE vs CI, caches và biến môi trường.

### 26.7. "Nâng Lombok làm consumer cũ lỗi"

So sánh getter/constructor/builder symbols ở class file; xem cấu hình Lombok và những thay đổi source annotation. Nếu public binary API đã thay đổi, cần migration hoặc giữ adapter/member cũ phù hợp.

### 26.8. "Generated mapper thiếu một field quan trọng"

Kiểm tra `@Mapping`, `unmappedTargetPolicy`, DTO shape và generated code. Bổ sung test theo dữ liệu nghiệp vụ; không chỉ test mapper instance khác null.

## 27. Checklist dành cho code review và CI

### Công cụ và phiên bản

- [ ] Đã xác định JDK thực sự chạy javac, không chỉ Java runtime.
- [ ] Đã ghi Lombok, MapStruct và binding versions.
- [ ] Đã xác nhận build plugin/Wrapper hỗ trợ JDK đích.
- [ ] Đã cấu hình `--release` phù hợp runtime baseline.
- [ ] Đã xem tài liệu compatibility của các công cụ khi nâng version.
- [ ] Không dựa vào workaround mở rộng `jdk.compiler` thiếu chủ sở hữu.

### Processor discovery

- [ ] Lombok có ở compile path và processor path theo build tool.
- [ ] MapStruct API được khai báo đúng scope.
- [ ] MapStruct processor có ở processor path.
- [ ] Binding được thêm khi combination đang dùng yêu cầu.
- [ ] Main và test source sets có processor config phù hợp.
- [ ] Không dựa vào processor auto-discovery tình cờ của compiler.
- [ ] Generated source directory được kiểm soát và đọc được sau clean build.

### Generated API và behavior

- [ ] Getter/setter/constructor/builder Lombok được sinh như mong đợi.
- [ ] Public method descriptors không đổi ngoài kế hoạch.
- [ ] MapperImpl được sinh và compile thành class.
- [ ] Mapping field quan trọng được test.
- [ ] Null, enum, collections và immutable mapping được kiểm tra.
- [ ] Component model và DI setup tương thích runtime.
- [ ] Generated classes có trong artifact cuối cùng.

### Migration và tái hiện

- [ ] Build từ workspace sạch trên JDK đích.
- [ ] Incremental build không dùng output cũ sai.
- [ ] CI, terminal và IDE dùng toolchain/version có thể đối chiếu.
- [ ] Đã chạy consumer compile lại và consumer nhị phân cũ khi cần.
- [ ] Đã kiểm chứng artifact trên JDK tối thiểu được công bố.
- [ ] Đã lưu compiler logs, generated-output evidence và dependency graph.
- [ ] Đã có phương án rollback khi code generation làm đổi public API hoặc mapping behavior.

## Kết luận

Lombok và MapStruct đều giảm code lặp, nhưng đứng ở hai vị trí khác nhau trong compilation: **Lombok can thiệp sâu vào javac để tạo member**, còn **MapStruct sử dụng annotation processing để sinh implementation Java của mapper**. Vì vậy, nâng JDK có thể làm Lombok mất tương thích với compiler internals, trong khi MapStruct có thể thất bại vì processor không được kích hoạt hoặc không nhìn thấy accessor/builder do Lombok tạo.

Chiến lược bền vững là **cấu hình processor tường minh, căn version theo JDK compiler, phối hợp binding khi cần, clean build, đọc generated source/class files và kiểm thử mapping thật**. Cuối cùng, phải xác minh class sinh ra nằm trong artifact phát hành và chạy trên runtime baseline. Một build “xanh” chỉ là điều kiện cần; migration thành công khi cả API, output sinh mã và hành vi dữ liệu đều đáp ứng hợp đồng đã công bố.

