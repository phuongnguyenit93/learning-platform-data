# Đăng ký chuyển đổi bằng Neo4jConversions

Spring Data Neo4j (SDN) ánh xạ property giữa entity Java và kiểu dữ liệu mà Neo4j hỗ trợ. Những kiểu phổ biến như chuỗi, số, boolean, ngày giờ và collection giá trị đơn giản đã có chuyển đổi tích hợp. Khi domain model dùng value object riêng, chẳng hạn EmailAddress, Money hoặc mã định danh có kiểu mạnh, SDN cần biết cách biến kiểu đó thành giá trị có thể lưu trong Neo4j và cách khôi phục nó khi đọc.

Neo4jConversions là nơi đăng ký các converter dùng chung cho toàn bộ mapping context. Sau khi đăng ký, SDN có thể dùng chúng khi đọc/ghi thuộc tính entity, relationship properties và trong các trường hợp chuyển đổi tham số truy vấn được hỗ trợ. Bài học này trình bày cách viết converter hai chiều, đăng ký bean Neo4jConversions và kiểm tra dữ liệu round-trip.

## 1. Khi nào cần custom conversion?

Neo4j lưu property bằng các kiểu dữ liệu được hỗ trợ bởi Cypher và Neo4j Java Driver. Một object Java tùy ý không thể được lưu trực tiếp thành property lồng nhau. Ví dụ, nếu entity có trường EmailAddress, SDN cần biết biểu diễn nó dưới dạng String, số hoặc một kiểu property phù hợp khác.

Có thể chọn một trong các hướng sau:

- Dùng kiểu Java đã được SDN hỗ trợ sẵn nếu kiểu đó thể hiện đúng ý nghĩa nghiệp vụ.
- Dùng custom converter khi một kiểu domain được biểu diễn thống nhất thành một kiểu property Neo4j.
- Dùng converter gắn với thuộc tính cụ thể nếu chỉ một field cần cách chuyển đổi riêng.
- Mô hình hóa thành node và relationship nếu đối tượng có định danh, vòng đời hoặc liên kết riêng trong graph.

Không nên tạo converter chỉ để thay đổi cách biểu diễn một kiểu đã được hỗ trợ tốt. Chuyển đổi tùy chỉnh làm tăng trách nhiệm tương thích dữ liệu và cần được kiểm thử khi schema hoặc format thay đổi.

## 2. Phân biệt chiều đọc và chiều ghi

Một converter cho SDN thường cần xác định rõ hai chiều:

| Chiều | Đầu vào | Đầu ra | Mục đích |
| --- | --- | --- | --- |
| Ghi | Kiểu domain Java | Neo4j Driver Value | Chuẩn bị property để lưu vào graph |
| Đọc | Neo4j Driver Value | Kiểu domain Java | Khôi phục property thành object Java |

Ví dụ, domain dùng EmailAddress nhưng Neo4j lưu giá trị email thành chuỗi:

~~~text
Java: EmailAddress("an@example.com")
             |
             | converter ghi
             v
Neo4j property: "an@example.com"
             |
             | converter đọc
             v
Java: EmailAddress("an@example.com")
~~~

Hai chiều phải thống nhất cùng một định dạng. Nếu converter ghi lưu một định dạng mà converter đọc không hiểu, dữ liệu có thể được tạo thành công nhưng lỗi khi tải entity trở lại.

## 3. Tạo value object trong domain

Bắt đầu bằng một record biểu diễn địa chỉ email:

~~~java
public record EmailAddress(String value) {

    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Email không được để trống");
        }
    }
}
~~~

Entity có thể sử dụng kiểu domain này trực tiếp:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;

    private EmailAddress email;

    // Constructor, getter và setter được lược bỏ.
}
~~~

Domain model giữ kiểu EmailAddress xuyên suốt logic nghiệp vụ. Các lớp service không cần chuyển email thành String mỗi lần đọc hoặc ghi. Việc chuyển đổi được tập trung tại persistence boundary.

## 4. Viết converter hai chiều bằng GenericConverter

Với custom property type của SDN, tài liệu hiện hành hướng dẫn dùng GenericConverter và khai báo các cặp kiểu mà converter hỗ trợ. Trong ví dụ này, converter xử lý EmailAddress sang Neo4j Driver Value khi ghi và Value sang EmailAddress khi đọc.

~~~java
import java.util.Set;

import org.neo4j.driver.Value;
import org.neo4j.driver.Values;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.GenericConverter;

public final class EmailAddressConverter implements GenericConverter {

    private static final Set<GenericConverter.ConvertiblePair> CONVERTIBLE_TYPES = Set.of(
        new GenericConverter.ConvertiblePair(EmailAddress.class, Value.class),
        new GenericConverter.ConvertiblePair(Value.class, EmailAddress.class)
    );

    @Override
    public Set<GenericConverter.ConvertiblePair> getConvertibleTypes() {
        return CONVERTIBLE_TYPES;
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {

        if (source == null) {
            return null;
        }

        if (EmailAddress.class.isAssignableFrom(sourceType.getType())) {
            EmailAddress email = (EmailAddress) source;
            return Values.value(email.value());
        }

        if (Value.class.isAssignableFrom(sourceType.getType())) {
            Value value = (Value) source;
            return new EmailAddress(value.asString());
        }

        throw new IllegalArgumentException(
            "Không hỗ trợ chuyển đổi từ " + sourceType.getType().getName()
        );
    }
}
~~~

Converter khai báo hai ConvertiblePair tách biệt. Cặp EmailAddress → Value phục vụ chiều ghi; cặp Value → EmailAddress phục vụ chiều đọc. Values.value(...) tạo giá trị String theo định dạng property mà Neo4j hỗ trợ. Khi đọc, asString() lấy lại chuỗi để tạo value object.

GenericConverter nhận TypeDescriptor của nguồn và đích, vì vậy implementation kiểm tra kiểu nguồn trước khi chuyển đổi. Không nên giả định mọi object Java đều có thể được chuyển thành Value; chỉ xử lý những cặp kiểu đã khai báo.

Nếu muốn dùng hai converter có kiểu cụ thể thay vì một GenericConverter, có thể triển khai Converter<EmailAddress, Value> và Converter<Value, EmailAddress>. Khi source và target đều là kiểu native hoặc có thể gây mơ hồ về chiều, dùng @WritingConverter hoặc @ReadingConverter để chỉ rõ mục đích đăng ký.

## 5. Đăng ký converter trong Neo4jConversions

Tạo bean Neo4jConversions trong cấu hình Spring:

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
            List.of(new EmailAddressConverter())
        );
    }
}
~~~

Spring Data Neo4j sử dụng bean Neo4jConversions này để đăng ký converter bổ sung. Constructor nhận collection converter; có thể truyền nhiều converter khi ứng dụng có nhiều value object cần ánh xạ.

Neo4jConversions quản lý cả các chuyển đổi mặc định của SDN lẫn converter tùy chỉnh được cung cấp. Vì vậy, khi khai báo bean, hãy tạo Neo4jConversions với danh sách converter bổ sung thay vì tự xây dựng một conversion service riêng rồi bỏ qua các chuyển đổi mặc định.

Các converter được đăng ký tường minh. Chỉ đánh dấu class bằng @Component hoặc đặt nó trong package component scan không có nghĩa SDN tự động đưa converter vào Neo4jConversions. Cần đăng ký instance trong bean nói trên.

## 6. SDN sử dụng converter khi đọc và ghi entity

Sau khi converter được đăng ký, thao tác repository có thể làm việc với EmailAddress như một property domain thông thường:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {
}
~~~

~~~java
Person person = new Person(
    "person-100",
    "An",
    new EmailAddress("an@example.com")
);

personRepository.save(person);

Person loaded = personRepository.findById("person-100")
    .orElseThrow();

EmailAddress email = loaded.getEmail();
~~~

Khi lưu, converter chuyển EmailAddress thành Value chứa chuỗi để SDN ghi property. Khi đọc, converter nhận Value và khôi phục EmailAddress. Service và domain tiếp tục sử dụng kiểu EmailAddress ở cả hai phía.

Dữ liệu lưu trong Neo4j có thể được kiểm tra bằng Cypher:

~~~cypher
MATCH (person:Person {id: $personId})
RETURN person.email AS email
~~~

Kết quả email là một property dạng String. Converter không tạo một node EmailAddress hoặc một map lồng nhau; nó ánh xạ value object thành một property đơn.

## 7. Chuyển đổi cho tham số truy vấn

Custom conversion cũng hữu ích khi kiểu domain được dùng làm tham số trong repository query hoặc thao tác truy vấn SDN. Ví dụ method nhận EmailAddress:

~~~java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (person:Person {email: $email})
        RETURN person
        """)
    Optional<Person> findByEmail(@Param("email") EmailAddress email);
}
~~~

SDN cần chuyển EmailAddress thành giá trị mà Driver có thể bind vào tham số Cypher. Với trường hợp converter chỉ phục vụ custom query parameter, tài liệu SDN cho phép chỉ cung cấp chiều ghi sang Value. Tuy nhiên, khi cùng kiểu được dùng làm property entity và cần đọc lại, phải đăng ký cả chiều đọc và chiều ghi.

Không ghép giá trị email trực tiếp vào chuỗi Cypher. Dùng named parameter như $email để giữ cấu trúc truy vấn tách biệt khỏi dữ liệu đầu vào.

## 8. Khi nào converter áp dụng toàn cục, khi nào chỉ áp dụng một field?

Neo4jConversions đăng ký converter theo cặp kiểu. Nếu EmailAddress được dùng ở nhiều entity, mọi property tương ứng có thể sử dụng cùng quy tắc chuyển đổi đó. Đây là lựa chọn phù hợp khi một kiểu domain luôn có một biểu diễn lưu trữ nhất quán.

Nếu cùng một kiểu Java cần hai cách biểu diễn khác nhau tùy thuộc field, converter toàn cục có thể quá rộng. SDN cung cấp @ConvertWith để gắn một Neo4jPersistentPropertyConverter vào thuộc tính cụ thể, kể cả property trong entity @Node và relationship properties.

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Một kiểu domain luôn lưu theo cùng định dạng | Đăng ký converter trong Neo4jConversions |
| Một field đặc biệt có format riêng | Cân nhắc @ConvertWith |
| Một object có định danh và quan hệ graph | Mô hình hóa bằng node/relationship |
| Kiểu đã được SDN hỗ trợ mặc định | Dùng chuyển đổi tích hợp |

Đừng đăng ký converter toàn cục cho một kiểu dùng nhiều ý nghĩa khác nhau nếu mỗi nơi cần format riêng. Hãy chọn converter theo thuộc tính hoặc tách kiểu domain để hợp đồng dữ liệu rõ ràng.

## 9. Các chuyển đổi mặc định và lưu ý thời gian

SDN đã cung cấp nhiều converter mặc định, bao gồm chuyển đổi cho các kiểu thời gian JSR-310 và các kiểu dữ liệu Neo4j/Driver hỗ trợ. Trước khi viết custom converter, hãy kiểm tra xem kiểu Java có được hỗ trợ sẵn hay không.

Một số chuyển đổi temporal mặc định giữa kiểu local date/time và java.util.Date phụ thuộc timezone mặc định của hệ thống. Nếu domain cần quy tắc timezone cụ thể, hãy thống nhất cách lưu trữ, chuyển đổi và đọc lại giữa các môi trường. Không ghi đè converter mặc định chỉ vì muốn thay đổi cách hiển thị ở API; định dạng API thường nên được xử lý ở tầng serialization hoặc DTO.

Với kiểu ngày giờ biểu diễn một thời điểm tuyệt đối, cân nhắc Instant hoặc kiểu có offset/zone phù hợp với yêu cầu nghiệp vụ. Với thời gian địa phương không gắn timezone, dùng LocalDateTime khi đó thực sự là ý nghĩa của dữ liệu. Converter tùy chỉnh phải bảo toàn đúng ngữ nghĩa thời gian, không chỉ bảo toàn chuỗi ký tự.

## 10. Kiểm thử converter và round-trip

Converter nên được kiểm thử độc lập trước khi kiểm thử qua repository. Với EmailAddress, kiểm tra hai chiều:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.neo4j.driver.Value;
import org.neo4j.driver.Values;
import org.springframework.core.convert.TypeDescriptor;
import org.junit.jupiter.api.Test;

class EmailAddressConverterTest {

    private final EmailAddressConverter converter =
        new EmailAddressConverter();

    @Test
    void convertsDomainValueToNeo4jValue() {
        EmailAddress email = new EmailAddress("an@example.com");

        Value stored = (Value) converter.convert(
            email,
            TypeDescriptor.valueOf(EmailAddress.class),
            TypeDescriptor.valueOf(Value.class)
        );

        assertThat(stored.asString()).isEqualTo("an@example.com");
    }

    @Test
    void convertsNeo4jValueToDomainValue() {
        Value stored = Values.value("an@example.com");

        EmailAddress email = (EmailAddress) converter.convert(
            stored,
            TypeDescriptor.valueOf(Value.class),
            TypeDescriptor.valueOf(EmailAddress.class)
        );

        assertThat(email.value()).isEqualTo("an@example.com");
    }
}
~~~

Tiếp theo, kiểm thử tích hợp với Neo4j để xác nhận mapping context thực sự sử dụng bean Neo4jConversions:

1. Tạo một Person có EmailAddress.
2. Lưu entity bằng repository.
3. Đọc property email bằng Cypher và xác nhận giá trị String được lưu đúng.
4. Đọc lại Person bằng repository.
5. Xác nhận email được khôi phục thành EmailAddress và bằng giá trị ban đầu.

Round-trip test giúp phát hiện trường hợp converter ghi đúng nhưng converter đọc sai, hoặc converter đã viết nhưng chưa được đăng ký trong cấu hình SDN.

Cũng cần kiểm tra giá trị null, chuỗi không hợp lệ và dữ liệu cũ nếu định dạng lưu trữ đã tồn tại trước khi converter mới được triển khai. Hành vi null cần phù hợp với quy tắc property của Neo4j: property có giá trị null không được lưu như một giá trị riêng trong node.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không thể lưu value object | Chưa có converter ghi hoặc converter không được đăng ký | Kiểm tra cặp kiểu domain → Value và bean Neo4jConversions |
| Đọc entity bị lỗi chuyển kiểu | Thiếu converter đọc hoặc converter không xử lý kiểu Value | Đăng ký cặp Value → domain type và kiểm tra dữ liệu |
| Converter không được gọi | Chỉ khai báo class mà không thêm vào Neo4jConversions | Đăng ký instance trong bean |
| Converter bị chọn sai chiều | Cặp kiểu hoặc ý định đọc/ghi không rõ | Khai báo đúng ConvertiblePair; dùng @ReadingConverter/@WritingConverter với typed Converter khi cần |
| Dữ liệu cũ không đọc được | Format lưu trữ đã thay đổi | Thiết kế migration hoặc converter tương thích format cũ |
| Cùng kiểu domain có nhiều format | Converter toàn cục áp dụng quá rộng | Dùng @ConvertWith cho field cụ thể hoặc tách kiểu domain |
| Query parameter không bind được | Thiếu chuyển đổi từ domain type sang Value | Đăng ký converter chiều ghi cho tham số |

Khi gặp lỗi, kiểm tra theo thứ tự: kiểu nguồn/đích, cặp converter đã khai báo, bean Neo4jConversions, định dạng property thực tế và phiên bản SDN/Driver đang dùng.

## 12. Quy trình thêm một converter mới

1. Xác định kiểu Java và kiểu property Neo4j sẽ dùng để lưu.
2. Kiểm tra kiểu đó chưa được SDN hỗ trợ sẵn theo cách phù hợp.
3. Viết converter ghi từ domain type sang Neo4j Driver Value.
4. Viết converter đọc từ Value về domain type nếu entity cần được tải lại.
5. Đăng ký converter instance trong bean Neo4jConversions.
6. Kiểm thử độc lập cả hai chiều và các trường hợp null/invalid.
7. Kiểm thử round-trip qua repository với Neo4j thật hoặc môi trường tích hợp tương thích.
8. Nếu format lưu trữ thay đổi, chuẩn bị migration hoặc khả năng đọc dữ liệu cũ.

Mỗi converter nên có một trách nhiệm chuyển đổi rõ ràng. Tránh để converter chứa quy tắc nghiệp vụ, truy vấn database hoặc gọi service; những việc đó thuộc các tầng khác của ứng dụng.

## 13. Bài tập tự kiểm tra

1. Neo4jConversions có vai trò gì trong mapping của Spring Data Neo4j?
2. Vì sao converter property thường cần cả chiều ghi và chiều đọc?
3. GenericConverter khai báo các cặp kiểu bằng phương thức nào?
4. Vì sao chỉ đánh dấu converter bằng @Component chưa đủ để SDN sử dụng nó?
5. Khi nào chỉ cần converter ghi sang Value cho tham số custom query?
6. Khi nào nên dùng @ConvertWith thay cho converter toàn cục?
7. Vì sao cần kiểm thử round-trip sau khi đăng ký converter?
8. Những rủi ro nào xuất hiện khi thay đổi format lưu trữ của một value object đã có dữ liệu?

Khi hoàn thành bài học, bạn cần có thể viết converter cho kiểu domain riêng, đăng ký chúng bằng Neo4jConversions và xác minh cả chiều đọc lẫn chiều ghi. Cách làm này giữ domain model giàu kiểu dữ liệu trong Java, đồng thời bảo đảm property được biểu diễn bằng các kiểu mà Neo4j lưu trữ và truy vấn được.

## Tài liệu tham khảo

- [Spring Data Neo4j – Conversions](https://docs.spring.io/spring-data/neo4j/reference/appendix/conversions.html)
- [Neo4jConversions API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/convert/Neo4jConversions.html)
- [Spring Data – Custom Conversions](https://docs.spring.io/spring-data/commons/reference/custom-conversions.html)

