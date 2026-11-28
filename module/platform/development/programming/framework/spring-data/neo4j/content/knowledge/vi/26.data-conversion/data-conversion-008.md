# Kiểm thử đọc–ghi đối xứng, null và dữ liệu không hợp lệ

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích tính đối xứng giữa chuyển đổi khi ghi và chuyển đổi khi đọc.
- Thiết kế custom converter có quy tắc chuẩn hóa, kiểm tra đầu vào và xử lý null rõ ràng.
- Kiểm thử converter độc lập trước khi tích hợp với Spring Data Neo4j (SDN).
- Viết integration test xác nhận dữ liệu thực tế trong Neo4j có thể đọc lại đúng kiểu Java.
- Kiểm tra trường hợp property null, property không tồn tại và dữ liệu lưu sai định dạng.
- Chọn đúng phạm vi converter: toàn ứng dụng hoặc một property cụ thể.
- Phát hiện lỗi tương thích dữ liệu trước khi đưa thay đổi converter vào production.

## 1. Vì sao phải kiểm thử cả chiều ghi và chiều đọc?

SDN chuyển đổi dữ liệu theo hai chiều:

- **Ghi (write):** giá trị Java được chuyển thành kiểu Value của Neo4j Java Driver rồi lưu thành property của node hoặc relationship.
- **Đọc (read):** property Neo4j được driver trả về dưới dạng Value, sau đó SDN chuyển đổi thành kiểu Java trong domain entity.

Một converter chỉ chạy đúng chiều ghi chưa chắc đọc lại được dữ liệu. Ví dụ, ứng dụng ghi một đối tượng thành chuỗi ABC-12345, nhưng converter đọc lại lại mong chờ một số hoặc cấu trúc JSON khác. Khi đó thao tác lưu thành công nhưng repository không thể hydrate entity.

Một converter đáng tin cậy cần đáp ứng ba nhóm kiểm tra:

1. **Đối xứng:** giá trị ghi ra có thể được đọc lại thành giá trị domain tương đương.
2. **Null:** giá trị null và property không tồn tại được xử lý theo quy tắc rõ ràng.
3. **Dữ liệu không hợp lệ:** dữ liệu sai kiểu hoặc sai định dạng phải tạo lỗi có thể chẩn đoán, không âm thầm biến thành giá trị mặc định.

Với một giá trị domain x, quy tắc cơ bản là:

\[
read(write(x)) \equiv canonical(x)
\]

Dấu tương đương có nghĩa giá trị đọc lại bằng giá trị đã chuẩn hóa theo quy tắc domain. Nếu converter không chuẩn hóa, có thể kiểm tra bằng equals. Nếu converter làm tròn số, chuẩn hóa chữ hoa/thường hoặc chuẩn hóa múi giờ, hãy kiểm tra theo quy tắc tương đương đã công bố.

## 2. Chọn đúng converter để kiểm thử

SDN hỗ trợ các kiểu chuyển đổi mặc định và custom converter.

| Phạm vi | Cách cấu hình | Phù hợp khi |
|---|---|---|
| Toàn ứng dụng cho một kiểu dữ liệu | GenericConverter đăng ký qua Neo4jConversions | Một kiểu Java cần cùng cách chuyển đổi ở nhiều entity hoặc tham số truy vấn |
| Một thuộc tính cụ thể | @ConvertWith và Neo4jPersistentPropertyConverter | Chỉ một field của node hoặc relationship cần cách lưu riêng |
| Chuyển đổi kiểu Java thông thường | Converter của Spring được SDN nhận diện | Kiểu dữ liệu có quy tắc chuyển đổi phù hợp với mapping |

Với converter áp dụng cho property entity, cần kiểm thử cả hai hướng từ kiểu Java sang Value và từ Value về kiểu Java. Converter chỉ dùng để chuyển tham số cho một số custom repository query có thể chỉ cần chiều ghi sang Value.

@ConvertWith có thể đặt trên thuộc tính của @Node hoặc @RelationshipProperties. Annotation này nhận một lớp Neo4jPersistentPropertyConverter qua converter, hoặc tham chiếu bean Spring qua converterRef. Nếu cần áp dụng converter cho nhiều field, có thể đăng ký GenericConverter trong bean Neo4jConversions.

## 3. Xác định hợp đồng chuyển đổi trước khi viết converter

Trước khi cài đặt, hãy viết rõ cách dữ liệu được lưu và cách đọc lại.

Ví dụ một hệ thống có mã sản phẩm dạng ABC-12345:

| Thành phần | Quy tắc |
|---|---|
| Kiểu Java | ProductCode |
| Dạng lưu trong Neo4j | Chuỗi |
| Chuẩn hóa | Xóa khoảng trắng hai đầu và chuyển thành chữ hoa |
| Định dạng hợp lệ | Ba chữ cái, dấu gạch ngang, năm chữ số |
| Null | Ghi thành Values.NULL; property Neo4j không tồn tại |
| Chuỗi sai định dạng | Ném lỗi khi tạo value object hoặc khi đọc dữ liệu cũ |
| Giá trị đọc lại | ProductCode đã chuẩn hóa |

Hợp đồng này làm cho test có tiêu chí rõ ràng. Nếu sau này muốn đổi định dạng lưu thành JSON hoặc tách mã thành nhiều property, thay đổi đó phải đi kèm migration và test tương thích dữ liệu cũ.

## 4. Tạo value object có kiểm tra đầu vào

Dùng một kiểu domain bất biến thay vì để chuỗi tự do xuất hiện ở mọi nơi:

~~~java
import java.util.Locale;

public record ProductCode(String value) {

    public ProductCode {
        if (value == null) {
            throw new IllegalArgumentException("Product code must not be null");
        }

        value = value.trim().toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z]{3}-[0-9]{5}")) {
            throw new IllegalArgumentException("Invalid product code format");
        }
    }
}
~~~

Constructor thực hiện hai việc:

- Chuẩn hóa dữ liệu hợp lệ về một dạng duy nhất.
- Từ chối dữ liệu sai định dạng ngay tại biên domain.

Ví dụ:

~~~java
ProductCode code = new ProductCode(" abc-12345 ");

System.out.println(code.value()); // ABC-12345
~~~

Nếu đầu vào là AB-123 hoặc ABC-12X45, constructor ném IllegalArgumentException. Nhờ đó, converter chỉ nhận một giá trị domain đã hợp lệ khi ghi.

## 5. Cài đặt Neo4jPersistentPropertyConverter

Converter sẽ lưu ProductCode thành chuỗi Neo4j và tạo lại value object khi đọc:

~~~java
import org.neo4j.driver.Value;
import org.neo4j.driver.Values;
import org.springframework.data.neo4j.core.convert.Neo4jPersistentPropertyConverter;

public final class ProductCodeConverter
        implements Neo4jPersistentPropertyConverter<ProductCode> {

    @Override
    public Value write(ProductCode source) {
        if (source == null) {
            return Values.NULL;
        }

        return Values.value(source.value());
    }

    @Override
    public ProductCode read(Value source) {
        try {
            return new ProductCode(source.asString());
        } catch (RuntimeException ex) {
            throw new IllegalArgumentException(
                "Stored externalCode is not a valid ProductCode",
                ex
            );
        }
    }
}
~~~

Các điểm cần chú ý:

- write phải trả về một đối tượng Value, không trả về Java null.
- Khi giá trị Java là null, dùng Values.NULL để biểu diễn null của Neo4j.
- read nhận Value chứa property thực tế và chuyển thành kiểu domain.
- Nếu driver không thể đọc giá trị thành chuỗi hoặc chuỗi không hợp lệ, converter ném lỗi có nguyên nhân gốc.
- Không thay dữ liệu sai định dạng bằng chuỗi rỗng hoặc mã mặc định vì việc đó che giấu dữ liệu hỏng.

Theo hợp đồng của Neo4jPersistentPropertyConverter, SDN có thể truyền null vào write; converter nên trả Values.NULL. Với chiều đọc, property không tồn tại hoặc giá trị null được SDN xử lý ở tầng mapping; phương thức read được dùng cho giá trị thực tế cần chuyển đổi.

Nếu cần dùng converter như một Spring bean, có thể tham chiếu bằng @ConvertWith(converterRef = "..."). Với converter có constructor mặc định như ví dụ, chỉ định lớp qua converter là đủ.

## 6. Gắn converter vào entity

Ví dụ entity Product:

~~~java
import org.springframework.data.neo4j.core.convert.ConvertWith;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Product")
public class Product {

    @Id
    private String sku;

    private String name;

    @ConvertWith(converter = ProductCodeConverter.class)
    private ProductCode externalCode;

    protected Product() {
    }

    public Product(String sku, String name, ProductCode externalCode) {
        this.sku = sku;
        this.name = name;
        this.externalCode = externalCode;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public ProductCode getExternalCode() {
        return externalCode;
    }

    public void setExternalCode(ProductCode externalCode) {
        this.externalCode = externalCode;
    }
}
~~~

Repository:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface ProductRepository
        extends Neo4jRepository<Product, String> {
}
~~~

Khi gọi save, SDN dùng converter của field externalCode. Khi gọi findById, SDN dùng chiều read của cùng converter để khôi phục ProductCode.

## 7. Kiểm thử converter độc lập

Unit test không cần khởi động Spring context hoặc Neo4j server. Mục tiêu là kiểm tra hợp đồng của converter ở mức nhỏ nhất.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.neo4j.driver.Value;
import org.neo4j.driver.Values;

class ProductCodeConverterTest {

    private final ProductCodeConverter converter =
        new ProductCodeConverter();

    @Test
    void writeThenReadReturnsCanonicalValue() {
        ProductCode original = new ProductCode(" abc-12345 ");

        Value stored = converter.write(original);
        ProductCode restored = converter.read(stored);

        assertThat(stored.asString()).isEqualTo("ABC-12345");
        assertThat(restored).isEqualTo(original);
    }

    @Test
    void nullIsRepresentedAsNeo4jNull() {
        Value stored = converter.write(null);

        assertThat(stored.isNull()).isTrue();
    }

    @Test
    void rejectsMalformedStoredValue() {
        Value malformed = Values.value("AB-123");

        assertThatThrownBy(() -> converter.read(malformed))
            .isInstanceOf(IllegalArgumentException.class)
            .hasRootCauseInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rejectsWrongNeo4jValueType() {
        Value number = Values.value(12345L);

        assertThatThrownBy(() -> converter.read(number))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Test đầu tiên kiểm tra cả biểu diễn lưu và giá trị khôi phục. Test null xác nhận converter dùng Values.NULL. Hai test còn lại kiểm tra chuỗi sai định dạng và kiểu Neo4j không phải chuỗi.

Có thể bổ sung test biên cho value object:

~~~java
@Test
void normalizesLowercaseAndWhitespace() {
    assertThat(new ProductCode(" abc-12345 ").value())
        .isEqualTo("ABC-12345");
}

@Test
void rejectsInvalidDomainInput() {
    assertThatThrownBy(() -> new ProductCode("ABC-12X45"))
        .isInstanceOf(IllegalArgumentException.class);
}
~~~

Các unit test này chạy nhanh và xác định lỗi nằm trong logic converter hoặc value object. Tuy nhiên, chúng chưa chứng minh SDN đã áp dụng converter đúng cho repository.

## 8. Kiểm thử round-trip qua repository và Neo4j thật

Integration test xác nhận toàn bộ đường đi:

~~~text
ProductCode
    |
    v
ProductCodeConverter.write()
    |
    v
Neo4j Driver Value
    |
    v
Neo4j property
    |
    v
Neo4j Driver Value
    |
    v
ProductCodeConverter.read()
    |
    v
ProductCode
~~~

Dùng @DataNeo4jTest để nạp repository, Neo4jClient, Neo4jTemplate và transaction infrastructure. Test slice này không tự cung cấp database; cần cấu hình Neo4j Testcontainers hoặc Neo4j Test Harness.

Ví dụ cấu hình Testcontainers:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import org.testcontainers.neo4j.Neo4jContainer;

@Testcontainers
@DataNeo4jTest
class ProductConversionIntegrationTest {

    @Container
    static final Neo4jContainer<?> neo4j =
        new Neo4jContainer<>(DockerImageName.parse("neo4j:5"))
            .withAdminPassword("test-password");

    @DynamicPropertySource
    static void neo4jProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", neo4j::getBoltUrl);
        registry.add("spring.neo4j.authentication.username", () -> "neo4j");
        registry.add(
            "spring.neo4j.authentication.password",
            neo4j::getAdminPassword
        );
    }

    // Các test được khai báo ở những phần tiếp theo.
}
~~~

Dependency test cần có Spring Boot Starter Test, Testcontainers Neo4j module và Testcontainers JUnit integration tương ứng với phiên bản dự án. Dùng image Neo4j tương thích với phiên bản SDN và driver mà ứng dụng đang chạy.

### Kiểm tra giá trị lưu thực tế và đọc lại

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.neo4j.core.Neo4jClient;

@Autowired
private ProductRepository products;

@Autowired
private Neo4jClient client;

@Test
void savesCanonicalValueAndReadsItBack() {
    Product product = new Product(
        "sku-100",
        "Keyboard",
        new ProductCode("abc-12345")
    );

    products.save(product);

    String rawValue = client.query("""
            MATCH (p:Product {sku: $sku})
            RETURN p.externalCode AS externalCode
            """)
        .bind("sku-100").to("sku")
        .fetchAs(String.class)
        .one()
        .orElseThrow();

    Product loaded = products.findById("sku-100").orElseThrow();

    assertThat(rawValue).isEqualTo("ABC-12345");
    assertThat(loaded.getExternalCode())
        .isEqualTo(new ProductCode("ABC-12345"));
}
~~~

Test này có hai assertion quan trọng:

- Cypher đọc trực tiếp xác nhận Neo4j lưu chuỗi canonical ABC-12345.
- Repository đọc lại xác nhận SDN gọi chiều read và khôi phục đúng kiểu ProductCode.

Nếu chỉ kiểm tra products.save(...) không ném lỗi, ta mới biết thao tác ghi đã hoàn tất; chưa biết chiều đọc có đối xứng hay không.

## 9. Kiểm thử null và property không tồn tại

Neo4j không lưu property có giá trị null. Trong node hoặc relationship, biểu thức SET p.externalCode = null có tác dụng loại bỏ property. Vì vậy, khi đọc một property không tồn tại, SDN ánh xạ nó thành null trong field Java tương ứng.

Hãy phân biệt:

- Java null: đối tượng không có giá trị cho field.
- Values.NULL: giá trị null ở cấp Neo4j Driver.
- Property không tồn tại: trạng thái lưu trữ thực tế trong node hoặc relationship.

Đối với property node/relationship, Neo4j xem giá trị null và property không tồn tại là tương đương. Nếu nghiệp vụ cần phân biệt “chưa từng khai báo” với “đã chủ động xóa”, cần lưu thêm trạng thái hoặc event riêng; không thể biểu diễn hai trạng thái đó bằng một property null.

### Lưu entity với field null

~~~java
@Test
void nullPropertyIsAbsentAndReadsAsNull() {
    Product product = new Product(
        "sku-null",
        "Mouse",
        null
    );

    products.save(product);

    Boolean propertyIsNull = client.query("""
            MATCH (p:Product {sku: $sku})
            RETURN p.externalCode IS NULL
            """)
        .bind("sku-null").to("sku")
        .fetchAs(Boolean.class)
        .one()
        .orElseThrow();

    Product loaded = products.findById("sku-null").orElseThrow();

    assertThat(propertyIsNull).isTrue();
    assertThat(loaded.getExternalCode()).isNull();
}
~~~

Test này xác nhận field null không tạo ra property Neo4j có giá trị null và khi đọc entity, field vẫn là null.

### Xóa một property đã có giá trị

~~~java
@Test
void settingFieldToNullRemovesStoredProperty() {
    Product product = products.save(
        new Product(
            "sku-clear",
            "Monitor",
            new ProductCode("MON-54321")
        )
    );

    product.setExternalCode(null);
    products.save(product);

    Boolean propertyIsNull = client.query("""
            MATCH (p:Product {sku: $sku})
            RETURN p.externalCode IS NULL
            """)
        .bind("sku-clear").to("sku")
        .fetchAs(Boolean.class)
        .one()
        .orElseThrow();

    assertThat(propertyIsNull).isTrue();
}
~~~

Đây là kiểm thử quan trọng khi ứng dụng cập nhật entity: field Java được đặt thành null phải tạo ra trạng thái lưu trữ đúng với chính sách xóa property của Neo4j.

Với field có thể null, ưu tiên kiểu tham chiếu như Integer, Long, Boolean hoặc value object. Kiểu primitive như int và boolean không thể mang null, nên không thể biểu diễn trực tiếp trạng thái thiếu property.

## 10. Kiểm thử dữ liệu đã lưu sai định dạng

Dữ liệu trong database có thể được tạo bởi phiên bản ứng dụng cũ, import từ CSV, truy vấn Cypher thủ công hoặc một dịch vụ khác. Vì vậy, converter phải kiểm tra dữ liệu đọc từ Neo4j chứ không chỉ kiểm tra dữ liệu mới do Java tạo ra.

Có thể chèn dữ liệu sai định dạng bằng Neo4jClient để mô phỏng dữ liệu cũ:

~~~java
@Test
void failsWhenStoredValueHasInvalidFormat() {
    client.query("""
            CREATE (:Product {
                sku: $sku,
                name: $name,
                externalCode: $externalCode
            })
            """)
        .bind("sku-bad").to("sku")
        .bind("Old product").to("name")
        .bind("AB-123").to("externalCode")
        .run();

    assertThatThrownBy(() -> products.findById("sku-bad"))
        .hasRootCauseInstanceOf(IllegalArgumentException.class);
}
~~~

Khi repository đọc node, converter nhận chuỗi AB-123, value object từ chối định dạng và lỗi được truyền lên tầng persistence.

Tùy đường đi mapping, exception bên ngoài có thể được bọc bởi exception của Spring Data. Test nên xác nhận nguyên nhân gốc hoặc nhóm lỗi chuyển đổi thay vì phụ thuộc vào một message dễ thay đổi giữa các phiên bản.

### Dữ liệu sai kiểu

Ngoài định dạng sai, property có thể chứa kiểu Cypher khác với converter mong đợi:

~~~cypher
CREATE (:Product {
    sku: "sku-wrong-type",
    name: "Legacy product",
    externalCode: 12345
})
~~~

Converter gọi Value.asString() sẽ không thể đọc một số nguyên thành chuỗi theo hợp đồng của nó. Đây là lỗi dữ liệu cần được phát hiện và xử lý bằng migration hoặc quy tắc tương thích rõ ràng.

Không nên tự động đổi mọi lỗi thành null:

~~~java
// Không nên: che giấu dữ liệu hỏng.
try {
    return new ProductCode(source.asString());
} catch (RuntimeException ex) {
    return null;
}
~~~

Cách làm này biến dữ liệu sai thành dữ liệu thiếu, khiến hệ thống khó phân biệt lỗi nhập liệu, lỗi migration và trường hợp người dùng chủ động xóa property.

## 11. Kiểm thử chuyển đổi toàn ứng dụng bằng Neo4jConversions

Nếu một kiểu dữ liệu xuất hiện ở nhiều entity, có thể đăng ký converter ở phạm vi ứng dụng bằng GenericConverter và Neo4jConversions.

Ví dụ GenericConverter cho hai chiều:

~~~java
import java.util.Set;

import org.neo4j.driver.Value;
import org.neo4j.driver.Values;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.GenericConverter;

public final class ProductCodeGenericConverter implements GenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Set.of(
            new ConvertiblePair(ProductCode.class, Value.class),
            new ConvertiblePair(Value.class, ProductCode.class)
        );
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType
    ) {
        if (ProductCode.class.isAssignableFrom(sourceType.getType())) {
            ProductCode code = (ProductCode) source;
            return code == null ? Values.NULL : Values.value(code.value());
        }

        Value value = (Value) source;
        try {
            return new ProductCode(value.asString());
        } catch (RuntimeException ex) {
            throw new IllegalArgumentException(
                "Stored value is not a valid ProductCode",
                ex
            );
        }
    }
}
~~~

Trong ví dụ, cặp ProductCode → Value dùng để ghi và cặp Value → ProductCode dùng để đọc. Spring có thể xử lý null ở tầng conversion/mapping; converter vẫn cần kiểm tra null nếu được gọi trực tiếp hoặc nếu quy tắc chuyển đổi của ứng dụng yêu cầu.

Ví dụ cấu hình:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.convert.Neo4jConversions;

@Configuration
public class Neo4jConversionConfiguration {

    @Bean
    Neo4jConversions neo4jConversions() {
        return new Neo4jConversions(
            List.of(new ProductCodeGenericConverter())
        );
    }
}
~~~

Một GenericConverter cho property entity cần khai báo hai cặp chuyển đổi:

- ProductCode sang Neo4j Driver Value.
- Value sang ProductCode.

Unit test cho converter toàn cục vẫn cần kiểm tra hai chiều như phần trước. Integration test cần khởi tạo Spring context có bean Neo4jConversions, lưu entity qua repository, đọc lại entity và xác nhận dữ liệu raw trong Neo4j.

Nếu converter chỉ phục vụ tham số của custom repository query, tài liệu SDN cho phép chỉ đăng ký chiều chuyển đổi sang Value. Nhưng converter cho property entity cần cả hai chiều để đọc–ghi đối xứng.

Đối với converter chỉ áp dụng cho một field, @ConvertWith giúp phạm vi rõ ràng hơn và tránh ảnh hưởng đến các property cùng kiểu ở những entity khác.

Lưu ý: custom conversion trên property có thể tham gia mapping của derived query và Query by Example. Không mặc định rằng @ConvertWith sẽ tự áp dụng cho tham số trong chuỗi @Query viết bằng Cypher; với string-based query, hãy kiểm tra cơ chế bind và converter được đăng ký cho query đó.

## 12. Kiểm thử kiểu dữ liệu mặc định và độ chính xác

Không phải kiểu Java nào cũng được lưu thành cùng kiểu Cypher. Một số chuyển đổi mặc định có quy tắc biểu diễn riêng:

| Kiểu Java | Biểu diễn thường dùng trong Neo4j | Điểm cần kiểm tra |
|---|---|---|
| BigDecimal, BigInteger | String | Parse lại chính xác, giữ scale nếu nghiệp vụ cần |
| java.util.Date | Chuỗi ISO-8601 theo UTC | Quy tắc múi giờ và độ chính xác thời gian |
| Float, float[] | String | Quy tắc định dạng và parse |
| Instant, OffsetDateTime | DateTime | Offset, timezone và precision |
| Enum | String tên hằng | Tương thích khi đổi tên enum |
| UUID | String | Chuẩn hóa định dạng |

Khi kiểm thử các kiểu số thực, không nên luôn dùng so sánh bằng tuyệt đối. Phép biểu diễn và lưu trữ số thực có thể làm giá trị đọc lại khác rất nhỏ do độ chính xác nhị phân. Hãy chọn tolerance phù hợp với nghiệp vụ.

Với thời gian, hãy quyết định rõ ứng dụng cần bảo toàn instant hay cả timezone/offset ban đầu. Nếu chỉ cần một instant, so sánh thời điểm tương đương; nếu cần timezone gốc, hãy lưu thêm thông tin vùng giờ thay vì mong đợi mọi kiểu thời gian tự giữ nguyên toàn bộ ngữ cảnh.

Với enum, việc đổi tên hằng có thể khiến dữ liệu cũ không đọc được. Nếu tên enum là hợp đồng lưu trữ lâu dài, hãy dùng mã lưu trữ ổn định hoặc converter ánh xạ tên Java sang mã domain độc lập.

## 13. Bộ kiểm thử tối thiểu cho một converter

Có thể dùng checklist sau khi thêm hoặc thay đổi converter:

| Nhóm | Ca kiểm thử | Kết quả mong đợi |
|---|---|---|
| Ghi | Giá trị domain hợp lệ | Trả về Value đúng kiểu và biểu diễn |
| Đọc | Value hợp lệ | Tạo đúng kiểu domain |
| Đối xứng | read(write(x)) | Bằng giá trị canonical của x |
| Chuẩn hóa | Chữ hoa/thường, khoảng trắng, định dạng | Kết quả theo hợp đồng domain |
| Null ghi | Java null | Trả Values.NULL |
| Null lưu trữ | Property không tồn tại | Entity nhận null theo mapping |
| Null cập nhật | Đặt field từ có giá trị sang null | Property bị loại bỏ |
| Sai định dạng | Chuỗi không hợp lệ | Phát sinh lỗi chuyển đổi |
| Sai kiểu | Number thay vì String | Phát sinh lỗi chuyển đổi |
| Tích hợp | Save rồi findById | Đọc lại đúng value object |
| Tương thích | Dữ liệu do phiên bản cũ tạo | Đọc được hoặc lỗi migration có chủ đích |

Ngoài các ca này, hãy thêm kiểm thử cho giá trị biên, chuỗi rỗng, ký tự Unicode, giá trị quá dài và dữ liệu cũ nếu domain có yêu cầu.

## 14. Quy trình kiểm thử trước khi triển khai converter mới

Một quy trình an toàn có thể thực hiện theo thứ tự:

1. Viết hợp đồng lưu trữ: kiểu Cypher, format, null, quy tắc chuẩn hóa và xử lý lỗi.
2. Viết unit test cho value object và converter.
3. Chạy integration test với Neo4j thật bằng Testcontainers hoặc Test Harness.
4. Kiểm tra giá trị raw trong database bằng Cypher, không chỉ kiểm tra object Java.
5. Đọc lại qua repository để xác nhận chiều read.
6. Seed dữ liệu cũ và dữ liệu sai định dạng để kiểm tra tương thích.
7. Nếu format lưu thay đổi, viết migration và kiểm thử trước/sau migration.
8. Triển khai converter cùng thay đổi dữ liệu theo một thứ tự tương thích.

Không nên triển khai converter đọc format mới trước khi dữ liệu hiện có đã được chuyển đổi hoặc converter có hỗ trợ đọc cả format cũ và mới.

## Kết luận

Kiểm thử converter phải bao phủ cả chiều ghi và chiều đọc. Hãy xác định dạng lưu trữ, chuẩn hóa giá trị, xử lý null và chính sách lỗi trước khi cài đặt converter. Unit test xác nhận logic chuyển đổi; integration test với Neo4j xác nhận repository thực sự ghi và đọc đúng property.

Trong Neo4j, property null được xem như không tồn tại. Vì vậy, cần kiểm tra cả trường hợp tạo mới với null và trường hợp cập nhật một property từ có giá trị thành null. Dữ liệu sai định dạng hoặc sai kiểu phải tạo lỗi có thể chẩn đoán để ứng dụng xử lý bằng validation hoặc migration, thay vì âm thầm thay bằng giá trị mặc định.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.1: Conversions và custom converters](https://docs.spring.io/spring-data/neo4j/reference/8.1/appendix/conversions.html)
- [Spring Data Neo4j API: Neo4jPersistentPropertyConverter](https://docs.spring.io/spring-data/neo4j/docs/8.1.x/api/org/springframework/data/neo4j/core/convert/Neo4jPersistentPropertyConverter.html)
- [Spring Data Neo4j API: Neo4jConversionService](https://docs.spring.io/spring-data/neo4j/docs/8.1.x/api/org/springframework/data/neo4j/core/convert/Neo4jConversionService.html)
- [Spring Data Neo4j: Testing with @DataNeo4jTest](https://docs.spring.io/spring-data/neo4j/reference/testing/testing-with-spring-boot.html)
- [Neo4j: Understanding non-existent properties and NULL](https://support.neo4j.com/s/article/360049691994-Understanding-non-existent-properties-and-working-with-nulls)
