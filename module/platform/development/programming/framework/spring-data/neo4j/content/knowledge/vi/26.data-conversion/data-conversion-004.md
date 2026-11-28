# Chuyển đổi toàn cục và chuyển đổi theo thuộc tính bằng @ConvertWith

Spring Data Neo4j (SDN) ánh xạ kiểu Java sang kiểu property mà Neo4j hỗ trợ. Những kiểu phổ biến như String, Boolean, Long, Double, các kiểu ngày giờ và enum đã có chuyển đổi mặc định. Khi domain sử dụng kiểu riêng như số tiền, mã định danh bên ngoài hoặc giá trị nghiệp vụ, cần xác định cách biểu diễn kiểu đó trong graph và cách khôi phục nó khi đọc.

SDN cung cấp hai phạm vi chuyển đổi chính. **Chuyển đổi toàn cục** đăng ký converter trong Neo4jConversions để áp dụng cho một kiểu Java ở nhiều nơi trong ứng dụng. **Chuyển đổi theo thuộc tính** dùng @ConvertWith để gắn converter vào một field cụ thể của entity hoặc relationship properties. Chọn đúng phạm vi giúp tránh lặp mã, giữ được ý nghĩa dữ liệu và không làm thay đổi cách lưu các thuộc tính khác.

## Vì sao cần custom conversion?

Giả sử hệ thống bán hàng có kiểu miền VndAmount để biểu diễn số tiền bằng đồng Việt Nam. Kiểu này giúp domain thể hiện rõ đơn vị tiền và ngăn nhầm lẫn giữa một số nguyên thông thường với số tiền.

~~~java
public record VndAmount(long dong) {

    public VndAmount {
        if (dong < 0) {
            throw new IllegalArgumentException("Amount cannot be negative");
        }
    }
}
~~~

Một entity Product có thể dùng kiểu này:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Product")
public class Product {

    @Id
    private String sku;

    private String name;

    private VndAmount price;

    protected Product() {
    }

    public Product(String sku, String name, VndAmount price) {
        this.sku = sku;
        this.name = name;
        this.price = price;
    }

    public VndAmount getPrice() {
        return price;
    }
}
~~~

Neo4j không biết trực tiếp kiểu VndAmount. Ứng dụng phải chuyển nó thành một kiểu property mà Neo4j lưu được, ví dụ INTEGER, rồi chuyển INTEGER trở lại VndAmount khi đọc.

Với số tiền tính bằng đồng Việt Nam, lưu số nguyên theo đơn vị đồng giúp truy vấn so sánh và sắp xếp số học. Nếu hệ thống hỗ trợ nhiều loại tiền tệ, cần lưu thêm mã tiền tệ và quy định rõ đơn vị nhỏ nhất của từng loại; không nên giả định mọi tiền tệ đều có cùng số chữ số thập phân.

## Chuyển đổi toàn cục bằng GenericConverter

Chuyển đổi toàn cục phù hợp khi cùng một kiểu Java cần được biểu diễn nhất quán ở nhiều entity hoặc nhiều property. SDN sử dụng Spring Conversion API và nhận các converter bổ sung thông qua Neo4jConversions.

Để chuyển VndAmount thành Neo4j INTEGER và đọc lại từ INTEGER, triển khai GenericConverter với hai chiều chuyển đổi:

~~~java
import java.util.Set;

import org.neo4j.driver.Value;
import org.neo4j.driver.Values;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.GenericConverter;
import org.springframework.core.convert.converter.GenericConverter.ConvertiblePair;

public final class VndAmountConverter implements GenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Set.of(
            new ConvertiblePair(VndAmount.class, Value.class),
            new ConvertiblePair(Value.class, VndAmount.class)
        );
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {

        if (source == null) {
            return null;
        }

        if (VndAmount.class.isAssignableFrom(sourceType.getType())) {
            VndAmount amount = (VndAmount) source;
            return Values.value(amount.dong());
        }

        if (Value.class.isAssignableFrom(sourceType.getType())) {
            Value value = (Value) source;
            if (value.isNull()) {
                return null;
            }
            return new VndAmount(value.asLong());
        }

        throw new IllegalArgumentException(
            "Unsupported conversion from " + sourceType + " to " + targetType
        );
    }
}
~~~

Converter khai báo hai cặp kiểu:

- VndAmount sang Value để ghi dữ liệu.
- Value sang VndAmount để đọc dữ liệu.

Values.value(amount.dong()) tạo một Neo4j Driver Value chứa số nguyên. Khi đọc, value.asLong() lấy lại số nguyên và constructor VndAmount kiểm tra miền giá trị. Nếu dữ liệu trong graph âm, constructor từ chối giá trị không hợp lệ thay vì âm thầm tạo một đối tượng sai quy tắc domain.

Đăng ký converter bằng một bean Neo4jConversions:

~~~java
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.GenericConverter;
import org.springframework.data.neo4j.core.convert.Neo4jConversions;

@Configuration
public class Neo4jConversionConfiguration {

    @Bean
    public Neo4jConversions neo4jConversions() {
        Set<GenericConverter> converters = Set.of(
            new VndAmountConverter()
        );

        return new Neo4jConversions(converters);
    }
}
~~~

Neo4jConversions quản lý các chuyển đổi mặc định của SDN và nhận thêm các converter do ứng dụng cung cấp. Khi có nhiều kiểu miền cần chuyển đổi toàn cục, có thể đăng ký nhiều GenericConverter trong cùng collection.

Sau khi đăng ký, entity Product có thể lưu VndAmount như một property INTEGER. Không cần đặt annotation trên từng field price. Bất kỳ property nào dùng VndAmount đều có thể dùng cùng quy tắc chuyển đổi đã đăng ký.

### Kiểm tra kiểu dữ liệu được lưu

Sau khi lưu Product, có thể kiểm tra giá trị trực tiếp bằng Cypher:

~~~cypher
MATCH (p:Product {sku: $sku})
RETURN p.price AS storedPrice;
~~~

Với VndAmount(199000), giá trị lưu mong đợi là 199000 dưới kiểu INTEGER. Khi SDN đọc Product, converter chuyển Value trở lại VndAmount.

Có thể khai báo derived query nhận chính kiểu miền:

~~~java
import java.util.List;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface ProductRepository extends Neo4jRepository<Product, String> {

    List<Product> findByPriceGreaterThan(VndAmount minimumPrice);
}
~~~

Vì converter toàn cục đã đăng ký cặp VndAmount và Value, SDN có thể chuyển tham số kiểu miền thành giá trị Neo4j khi tạo điều kiện cho derived query. Cách này giúp tầng service tiếp tục làm việc với VndAmount thay vì tự bóc giá trị số ở mọi lời gọi.

Nếu converter chỉ phục vụ tham số cho custom repository query, có thể chỉ cần chiều ghi từ kiểu Java sang Value. Nếu kiểu đó cũng là property của entity và cần được đọc lại, phải cung cấp cả chiều Value sang kiểu Java.

## Chuyển đổi theo thuộc tính bằng @ConvertWith

Có trường hợp một kiểu Java chỉ cần cách lưu đặc biệt ở một field. Ví dụ, CustomerReference là mã tham chiếu từ hệ thống cũ. Một entity cần chuẩn hóa mã này thành chuỗi viết hoa, nhưng những field khác trong ứng dụng không nhất thiết phải dùng cùng quy tắc.

Tạo kiểu miền:

~~~java
public record CustomerReference(String value) {

    public CustomerReference {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Customer reference is required");
        }
    }
}
~~~

Triển khai Neo4jPersistentPropertyConverter:

~~~java
import java.util.Locale;

import org.neo4j.driver.Value;
import org.neo4j.driver.Values;
import org.springframework.data.neo4j.core.convert.Neo4jPersistentPropertyConverter;

public final class CustomerReferenceConverter
        implements Neo4jPersistentPropertyConverter<CustomerReference> {

    @Override
    public Value write(CustomerReference source) {
        if (source == null) {
            return Values.NULL;
        }

        return Values.value(source.value().toUpperCase(Locale.ROOT));
    }

    @Override
    public CustomerReference read(Value source) {
        return new CustomerReference(source.asString());
    }
}
~~~

write() chuyển giá trị Java thành Neo4j Driver Value. read() khôi phục kiểu CustomerReference từ Value đã lưu. Phương thức write phải trả về Values.NULL khi muốn biểu diễn null; read nhận một Value có giá trị, không nhận Values.NULL theo hợp đồng của interface.

Gắn converter vào đúng field bằng @ConvertWith:

~~~java
import org.springframework.data.neo4j.core.convert.ConvertWith;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Customer")
public class Customer {

    @Id
    private String customerId;

    @ConvertWith(converter = CustomerReferenceConverter.class)
    private CustomerReference legacyReference;

    protected Customer() {
    }

    public Customer(String customerId, CustomerReference legacyReference) {
        this.customerId = customerId;
        this.legacyReference = legacyReference;
    }

    public CustomerReference getLegacyReference() {
        return legacyReference;
    }
}
~~~

Converter chỉ được gắn với property legacyReference. Khi ghi Customer, SDN dùng CustomerReferenceConverter để lưu mã dưới dạng chuỗi viết hoa. Các property khác tiếp tục dùng mapping và converter mặc định hoặc converter toàn cục tương ứng.

@ConvertWith cũng có thể đặt trên property của entity được đánh dấu @Node và property trong lớp @RelationshipProperties. Điều này hữu ích khi một thuộc tính trên relationship cần cách biểu diễn riêng, ví dụ mã vai trò hoặc giá trị thời gian theo định dạng tương thích với hệ thống cũ.

## Dùng converterRef để lấy converter từ Spring bean

Nếu converter cần dependency do Spring quản lý, chẳng hạn một service chuẩn hóa hoặc cấu hình định dạng, không nên tự tạo instance bằng constructor mặc định. Có thể đăng ký converter thành bean và tham chiếu bằng converterRef:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.convert.Neo4jPersistentPropertyConverter;

@Configuration
public class PropertyConverterConfiguration {

    @Bean("customerReferenceConverter")
    public Neo4jPersistentPropertyConverter<CustomerReference>
            customerReferenceConverter() {
        return new CustomerReferenceConverter();
    }
}
~~~

Field dùng bean đó:

~~~java
@ConvertWith(converterRef = "customerReferenceConverter")
private CustomerReference legacyReference;
~~~

Bean được tham chiếu phải có tên đúng với converterRef và triển khai Neo4jPersistentPropertyConverter. Nếu không tìm thấy bean hoặc bean không đúng kiểu, mapping context sẽ báo lỗi khi khởi tạo.

@ConvertWith có ba thuộc tính quan trọng:

| Thuộc tính | Công dụng |
|---|---|
| converter | Lớp Neo4jPersistentPropertyConverter được tạo cho property |
| converterRef | Tên Spring bean chứa converter; được ưu tiên nếu được thiết lập |
| converterFactory | Factory tạo converter dựa trên metadata của property |

Converter có constructor mặc định thường chỉ cần khai báo converter. converterRef phù hợp khi cần dùng bean đã cấu hình trong Spring. converterFactory hữu ích khi cách chuyển đổi phụ thuộc metadata của property, ví dụ định dạng ngày hoặc quy tắc riêng được khai báo trên annotation. Factory có thể nhận Neo4jConversionService hoặc BeanFactory qua constructor mà SDN hỗ trợ.

## So sánh chuyển đổi toàn cục và chuyển đổi theo thuộc tính

| Tiêu chí | GenericConverter toàn cục | @ConvertWith theo thuộc tính |
|---|---|---|
| Phạm vi | Mọi nơi sử dụng cặp kiểu đã đăng ký | Một property được đánh dấu |
| API converter | Spring GenericConverter | Neo4jPersistentPropertyConverter |
| Kiểu đích/nguồn | Thường khai báo cặp Java type và Driver Value | read(Value), write(Java type) |
| Đăng ký | Bean Neo4jConversions | Annotation trên field hoặc meta-annotation |
| Phụ thuộc Spring bean | Có thể đăng ký converter trong cấu hình Spring | Có thể dùng converterRef |
| Dùng cho property entity | Có, nếu khai báo đủ hai chiều | Có |
| Dùng cho relationship properties | Có, theo kiểu dữ liệu | Có thể gắn trực tiếp lên property |
| Phạm vi tác động | Rộng, nhất quán theo kiểu | Hẹp, chỉ nơi được chú thích |

Nên chọn GenericConverter khi một kiểu miền luôn có cùng biểu diễn trong graph. Chọn @ConvertWith khi một property cần quy tắc đặc biệt hoặc cùng một kiểu Java có thể được lưu khác nhau ở những vị trí khác nhau.

Không nên đăng ký một converter toàn cục chỉ vì một field duy nhất có định dạng đặc biệt. Điều đó có thể làm thay đổi cách SDN lưu kiểu đó ở những entity khác mà người viết converter không dự tính.

## Ảnh hưởng đến tham số truy vấn repository

Custom conversion còn ảnh hưởng đến cách tham số Java được chuyển thành giá trị dùng trong truy vấn. Cần phân biệt derived query, Query by Example và truy vấn chuỗi khai báo bằng @Query.

Với @ConvertWith, SDN áp dụng chuyển đổi cho property entity và tham số repository method ánh xạ tới property đó. Điều này bao gồm derived queries và Query by Example. Ví dụ, nếu một repository method lọc theo legacyReference, converter gắn trên property có thể được dùng để chuyển tham số:

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface CustomerRepository extends Neo4jRepository<Customer, String> {

    Optional<Customer> findByLegacyReference(CustomerReference reference);
}
~~~

Đối với truy vấn khai báo bằng chuỗi @Query, không nên giả định property converter của field sẽ tự động được áp dụng cho tham số. Nếu @Query cần tham số kiểu CustomerReference, hãy đăng ký chuyển đổi toàn cục phù hợp từ CustomerReference sang Value hoặc chuyển đổi giá trị sang dạng Neo4j-native trước khi gọi query.

Ví dụ query dùng tham số kiểu chuỗi đã chuẩn hóa:

Thêm phương thức sau vào CustomerRepository:

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (c:Customer {legacyReference: $reference})
    RETURN c
    """)
Optional<Customer> findByStoredReference(
    @Param("reference") String normalizedReference
);
~~~

Trong ví dụ, service chịu trách nhiệm chuẩn hóa tham số thành chuỗi đúng với định dạng đã lưu. Cách này rõ ràng khi chỉ một query cần sử dụng dạng lưu trữ. Nếu nhiều query dùng kiểu miền đó, cân nhắc converter toàn cục để giảm việc chuyển đổi thủ công.

## Chuyển đổi cho property và chuyển đổi cho query parameter

Một converter phục vụ ghi property cần xử lý cả hai chiều để SDN có thể lưu và đọc entity. Một converter chỉ phục vụ tham số query có thể chỉ cần chuyển từ kiểu Java sang Value.

| Use case | Hướng chuyển đổi cần có |
|---|---|
| Lưu và đọc một property entity | Java type sang Value và Value sang Java type |
| Tham số derived query | Java type sang kiểu property được so khớp |
| Probe của Query by Example | Java type sang kiểu property được so khớp |
| Tham số cho custom string-based query | Chuyển sang Value hoặc kiểu Neo4j-native phù hợp |
| Chỉ ghi dữ liệu qua một custom query | Có thể chỉ cần chiều Java type sang Value |
| Đọc kết quả thành custom type | Cần chiều Value sang Java type hoặc mapping tường minh |

Hãy xác định rõ converter đang phục vụ property mapping, tham số query hay cả hai. Việc một converter hoạt động khi save entity không tự chứng minh rằng mọi custom query cũng dùng đúng converter đó.

## Xử lý null, lỗi định dạng và dữ liệu cũ

Converter nằm ở ranh giới giữa mô hình Java và kiểu lưu trữ. Cần định nghĩa rõ hành vi với null, dữ liệu không hợp lệ và giá trị đã được lưu từ phiên bản ứng dụng trước.

- **Null:** property converter nên trả Values.NULL khi write nhận null. Khi read, chỉ chuyển đổi Value có nội dung theo hợp đồng của interface.
- **Sai định dạng:** không trả về một giá trị mặc định có thể che giấu dữ liệu lỗi. Hãy báo lỗi chuyển đổi với thông tin đủ để xác định property và bản ghi.
- **Giới hạn giá trị:** kiểm tra miền giá trị trong constructor hoặc converter trước khi tạo đối tượng domain.
- **Định dạng lưu trữ:** giữ quy tắc mã hóa ổn định; thay đổi từ chuỗi sang số hoặc đổi định dạng chuỗi cần migration dữ liệu.
- **Tương thích ngược:** nếu graph chứa dữ liệu được ghi bởi phiên bản cũ, converter mới phải đọc được định dạng đó hoặc cần chuyển đổi dữ liệu trước khi triển khai.

Ví dụ, VndAmountConverter đọc bằng Value.asLong(). Nếu dữ liệu cũ được lưu dưới dạng chuỗi, converter sẽ không tự động đoán ý nghĩa chuỗi đó. Cần một migration chuyển property cũ sang INTEGER hoặc triển khai chiến lược đọc tương thích trong giai đoạn chuyển tiếp.

Có thể kiểm tra dữ liệu trước migration:

~~~cypher
MATCH (p:Product)
WHERE p.price IS NOT NULL
RETURN p.sku, p.price
LIMIT 50;
~~~

Truy vấn giúp quan sát các giá trị đang lưu. Kiểm tra kiểu property bằng công cụ Neo4j phù hợp với phiên bản DBMS đang chạy. Chỉ thực hiện chuyển đổi sau khi đã xác định các dạng dữ liệu thực tế, xử lý giá trị lỗi và thử migration trên bản sao dữ liệu.

## Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Quên đăng ký GenericConverter trong Neo4jConversions | SDN không nhận biết kiểu miền khi mapping | Khai báo bean Neo4jConversions có converter |
| Chỉ có chiều ghi nhưng entity cần được đọc | Không thể khôi phục kiểu Java từ Value | Bổ sung chiều Value sang kiểu miền |
| Dùng GenericConverter toàn cục cho một field đặc biệt | Những property cùng kiểu ở nơi khác bị ảnh hưởng | Dùng @ConvertWith tại field cần quy tắc riêng |
| Gắn @ConvertWith nhưng converter không có constructor phù hợp hoặc factory | Mapping context không tạo được converter | Dùng constructor mặc định, converterFactory hoặc converterRef |
| converterRef sai tên hoặc sai kiểu bean | Ứng dụng lỗi khi khởi tạo mapping context | Kiểm tra tên bean và kiểu Neo4jPersistentPropertyConverter |
| Cho rằng @ConvertWith tự áp dụng cho string-based @Query | Tham số query không được chuyển đổi như mong đợi | Dùng converter toàn cục hoặc truyền giá trị Neo4j-native |
| Trả null từ write thay vì Values.NULL | Vi phạm hợp đồng giá trị trả về của property converter | Trả Values.NULL để biểu diễn null |
| Thay đổi định dạng lưu mà không migration | Dữ liệu cũ không đọc được hoặc sai kiểu | Lập kế hoạch chuyển đổi và kiểm thử tương thích |
| Chỉ test converter độc lập | Không phát hiện lỗi tích hợp với mapping SDN | Kiểm thử round-trip qua repository và Neo4j |

## Bài tập thực hành

Xây dựng chuyển đổi cho hai kiểu miền:

1. Tạo VndAmount lưu số đồng bằng Neo4j INTEGER.
2. Viết GenericConverter hai chiều giữa VndAmount và Driver Value.
3. Đăng ký converter qua Neo4jConversions.
4. Khai báo Product có property price kiểu VndAmount và lưu một sản phẩm.
5. Đọc lại Product, xác nhận price được khôi phục thành VndAmount.
6. Viết derived query tìm sản phẩm có giá lớn hơn một VndAmount cho trước.
7. Tạo CustomerReference và converter chỉ chuẩn hóa mã ở property legacyReference.
8. Gắn @ConvertWith(converter = ...) vào field, sau đó thử thay bằng converterRef với Spring bean.
9. Viết repository method derived query theo legacyReference và kiểm tra tham số được chuyển đổi.
10. Viết custom @Query dùng tham số chuỗi đã chuẩn hóa, giải thích khác biệt với property converter.
11. Thử dữ liệu null, chuỗi sai định dạng và giá trị số âm.
12. Viết integration test kiểm tra dữ liệu sau save, sau read và kiểu property thực tế trong Neo4j.

Khi thiết kế custom conversion cho Spring Data Neo4j, hãy dùng GenericConverter đăng ký qua Neo4jConversions nếu một kiểu miền cần cùng cách biểu diễn ở nhiều nơi. Dùng @ConvertWith nếu chỉ một property hoặc một nhóm property cần quy tắc riêng. Kiểm tra cả chiều ghi, chiều đọc, tham số truy vấn và dữ liệu đã tồn tại để bảo đảm cách chuyển đổi nhất quán trong toàn bộ vòng đời dữ liệu.

Tài liệu tham khảo chính thức:

- [Spring Data Neo4j - Conversions](https://docs.spring.io/spring-data/neo4j/reference/appendix/conversions.html)
- [ConvertWith API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/convert/ConvertWith.html)
- [Neo4jPersistentPropertyConverter API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/convert/Neo4jPersistentPropertyConverter.html)

