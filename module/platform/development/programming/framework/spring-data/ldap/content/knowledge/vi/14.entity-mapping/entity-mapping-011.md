# Cấu hình chuyển đổi kiểu theo khả năng ODM của phiên bản sử dụng

> **Chương:** Ánh xạ thực thể  
> **Module:** SPRING_DATA_LDAP — truy cập dịch vụ thư mục LDAP qua Spring Data LDAP bằng mô hình repository và ánh xạ entry phân cấp sang đối tượng Java. Người học làm việc với DN, objectClass, schema, truy vấn repository/LdapTemplate, CRUD, filter an toàn, bảo mật kết nối và kiểm thử với directory.

Một entry LDAP lưu dữ liệu theo attribute và syntax do schema quy định. Ứng dụng Java lại thường muốn dùng enum, value object, kiểu ngày giờ hoặc kiểu nhị phân có ý nghĩa nghiệp vụ. Ví dụ, directory lưu employeeStatus là chuỗi active, trong khi domain model muốn nhận EmploymentStatus.ACTIVE.

ODM (Object-Directory Mapping) chuyển đổi dữ liệu giữa hai phía khi đọc và ghi entry. Cách cấu hình converter phụ thuộc phiên bản Spring LDAP mà Spring Data LDAP đang sử dụng. Một số API cũ như ConverterManager đã deprecated; các phiên bản mới dùng Spring ConversionService và Converter chuẩn.

Bài này hướng dẫn xác định đúng tầng ánh xạ, chọn API theo phiên bản, đăng ký converter hai chiều, cấu hình ObjectDirectoryMapper, xử lý dữ liệu chuỗi/nhị phân/thời gian và kiểm thử round-trip để bảo đảm dữ liệu không bị biến đổi ngoài ý muốn.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích luồng chuyển đổi từ LDAP attribute sang Java field và ngược lại.
2. Phân biệt Spring LDAP ODM với cơ chế chuyển đổi chung của Spring Data Commons.
3. Xác định API chuyển đổi tương ứng với phiên bản Spring LDAP.
4. Dùng @Attribute để khai báo tên, syntax, kiểu chuỗi/nhị phân và thuộc tính chỉ đọc.
5. Viết converter từ chuỗi LDAP sang enum/value object và converter ngược để ghi dữ liệu.
6. Cấu hình ConversionService cho DefaultObjectDirectoryMapper.
7. Kết nối mapper đã cấu hình với LdapTemplate và Spring Data LDAP repository.
8. Phân biệt conversion với validation, escaping, DN mapping và schema enforcement.
9. Kiểm thử dữ liệu đọc/ghi, giá trị không hợp lệ, attribute thiếu, multi-valued và binary.
10. Tránh sử dụng API cũ khi phiên bản thư viện đã chuyển sang ConversionService.

## 2. Luồng chuyển đổi trong ODM

Spring Data LDAP repository sử dụng các annotation ODM của Spring LDAP để ánh xạ entity. Repository cần một DN làm ID và dựa vào LdapTemplate/mapping layer để đọc hoặc ghi entry.

~~~mermaid
flowchart LR
    LDAP["LDAP entry"]
    ATTR["LDAP attributes<br/>String / byte[] / values"]
    ODM["Spring LDAP ODM<br/>ObjectDirectoryMapper"]
    CS["ConversionService<br/>registered Converter"]
    JAVA["Java entity<br/>enum / value object / time"]
    REPO["LdapRepository / LdapTemplate"]

    LDAP --> ATTR
    ATTR --> ODM
    ODM <--> CS
    CS <--> JAVA
    JAVA <--> ODM
    ODM <--> REPO
~~~

Khi đọc:

1. LDAP server trả entry và attribute values.
2. JNDI provider biểu diễn giá trị, thường là String hoặc byte[] tùy attribute và cấu hình.
3. ODM đọc metadata của entity, gồm @Entry, @Id, @Attribute, @DnAttribute và @Transient.
4. Mapping layer dùng converter phù hợp để chuyển kiểu nguồn sang kiểu field Java.
5. Entity được trả về cho service/repository.

Khi ghi:

1. Ứng dụng thay đổi field trên entity.
2. ODM đọc metadata và lấy giá trị Java.
3. ConversionService chọn converter từ kiểu Java sang kiểu mà LDAP/JNDI có thể ghi.
4. Mapper tạo attribute values và thực hiện thao tác LDAP.
5. Directory server kiểm tra schema, ACL và quy tắc của entry.

**Converter chỉ xử lý biểu diễn dữ liệu.** Nó không tạo objectClass còn thiếu, không tự cấp quyền, không sửa schema, không kiểm tra uniqueness toàn directory và không thay thế quy tắc DN.

## 3. Xác định đúng tầng chuyển đổi

Có nhiều API mang tên gần nhau nhưng phục vụ các mapping layer khác nhau.

| Thành phần | Vai trò | Dùng trong bài này? |
|---|---|---|
| Spring LDAP ODM | Ánh xạ entity có annotation sang LDAP entry | **Có** |
| ObjectDirectoryMapper | Mapping object và LDAP entry bên trong Spring LDAP | **Có** |
| Spring ConversionService | Chọn và chạy converter theo cặp kiểu nguồn/đích | **Có** |
| Spring Converter<S,T> | Logic chuyển đổi một cặp kiểu | **Có** |
| Spring Data Commons CustomConversions | Hạ tầng chuyển đổi cho các store/mapping module dùng nó | Không tự động thay converter của Spring LDAP ODM |
| AttributesMapper | Tự ánh xạ kết quả của một truy vấn thủ công | Dùng khi cần mapping thủ công, không phải converter ODM |
| PropertyEditor | Cơ chế chuyển đổi kiểu cũ của một số framework | Không nên chọn cho cấu hình ODM mới |

Spring Data LDAP yêu cầu entity repository dùng annotation ODM của Spring LDAP. Vì vậy, nếu entity được quản lý qua LdapRepository, hãy cấu hình converter trong ObjectDirectoryMapper được LdapTemplate sử dụng.

Đừng giả định rằng khai báo một bean CustomConversions hoặc thêm annotation ReadingConverter của Spring Data Commons sẽ tự động được Spring LDAP ODM dùng. Hai cơ chế chỉ kết nối với nhau khi một mapping module cụ thể tích hợp chúng.

## 4. Chọn API theo phiên bản Spring LDAP

Khả năng cấu hình converter đã thay đổi qua các phiên bản. Cần xem phiên bản **Spring LDAP thực tế** trong dependency graph/BOM của ứng dụng; không chỉ nhìn phiên bản Spring Boot hoặc Spring Data LDAP.

| Dòng phiên bản Spring LDAP | Cách ODM hoạt động | Hướng cấu hình chuyển đổi |
|---|---|---|
| 1.x | ODM dùng OdmManager riêng | ConverterManager, ConverterManagerFactoryBean và cấu hình converter kiểu cũ |
| 2.0 đến 3.2.x | Chức năng ODM được tích hợp vào LdapTemplate qua ObjectDirectoryMapper | Có thể gặp các API ConverterManager/ConversionServiceConverterManager trong tài liệu cùng thời kỳ |
| 3.3.x trở lên | DefaultObjectDirectoryMapper hỗ trợ trực tiếp Spring ConversionService | Dùng DefaultObjectDirectoryMapper.setConversionService(...) và ConverterUtils.addDefaultConverters(...) |
| 4.x | Tiếp tục dùng ConversionService trực tiếp | Ưu tiên API mới; tránh API cũ đã deprecated |

Các mốc quan trọng:

- Từ **Spring LDAP 2.0**, chức năng ODM có sẵn trong LdapTemplate; không cần tự tạo OdmManagerImplFactoryBean theo ví dụ đời 1.x.
- Từ **Spring LDAP 3.3**, các API như ConverterManager, ConverterManagerImpl, ConversionServiceConverterManager và ConverterManagerFactoryBean đã deprecated; tài liệu khuyến nghị dùng ConversionService trực tiếp.
- ConverterUtils.addDefaultConverters(...) được giới thiệu từ 3.3 để đăng ký các converter mặc định dành cho Spring LDAP.
- Với Spring Boot, tài liệu Spring LDAP hiện hành mô tả việc đăng ký các bean Converter theo cách thông thường để ObjectDirectoryMapper do Boot cấu hình nhận được chúng. Với ứng dụng không dùng Boot, cần cấu hình mapper và ConversionService tường minh.

**Quy tắc thực hành:** code cấu hình ở các mục sau dùng API Spring LDAP **3.3+**. Nếu dự án đang dùng 1.x, 2.x hoặc 3.2.x, đối chiếu Javadoc/reference đúng phiên bản trước khi sao chép; không thêm API mới vào classpath cũ.

## 5. ODM hỗ trợ những gì trước khi cần custom converter?

Không phải mọi field đều cần converter riêng.

| Kiểu dữ liệu | Hướng ánh xạ thường gặp | Lưu ý |
|---|---|---|
| String | LDAP Directory String ↔ Java String | Phải phù hợp syntax và matching rule của attribute |
| Name | DN string ↔ Java Name | Spring LDAP có converter hỗ trợ Name/String |
| byte[] | Binary LDAP attribute ↔ byte[] | Khai báo kiểu BINARY khi cần |
| Integer/Long/Boolean | Có thể dùng chuyển đổi chuẩn nếu ConversionService hỗ trợ | Phải khớp cách server biểu diễn và syntax |
| Enum/value object riêng | Cần converter khi không có chuyển đổi phù hợp | Nên khai báo quy tắc đọc và ghi rõ ràng |
| Instant/LocalDate/OffsetDateTime | Phụ thuộc format, converter và timezone | Không mặc định mọi LDAP time syntax giống ISO-8601 |
| Collection | Một field có thể biểu diễn attribute nhiều giá trị | Kiểm tra cardinality và kiểu từng phần tử |
| Attribute operational/read-only | Có thể đọc nhưng không nên ghi | Dùng @Attribute(readonly = true) khi phù hợp |

Spring LDAP có các converter riêng như StringToNameConverter và NameToStringConverter. ConverterUtils.addDefaultConverters(...) đăng ký các converter mặc định của Spring LDAP vào một ConverterRegistry.

Spring DefaultConversionService cũng cung cấp nhiều phép chuyển đổi thông dụng. Tuy nhiên, khả năng có thể thay đổi theo Spring Framework và phiên bản dependency; **đừng suy luận chỉ từ tên kiểu Java**. Có thể kiểm tra bằng conversionService.canConvert(sourceType, targetType) và xác nhận bằng test thực tế.

## 6. Vai trò của @Attribute

@Attribute ánh xạ field Java tới attribute LDAP. Một số phần tử quan trọng:

| Thuộc tính annotation | Ý nghĩa |
|---|---|
| name | Tên attribute LDAP; mặc định dùng tên field nếu bỏ trống |
| syntax | LDAP syntax OID của attribute; hữu ích khi cần xác định chính xác syntax |
| type | Cho JNDI biết attribute được xem là STRING hay BINARY |
| readonly | Cho phép đọc nhưng không persist field trở lại LDAP |

Ví dụ:

~~~java
@Attribute(
    name = "employeeStatus",
    syntax = "1.3.6.1.4.1.1466.115.121.1.15",
    type = Attribute.Type.STRING
)
private EmploymentStatus status;

@Attribute(
    name = "jpegPhoto",
    type = Attribute.Type.BINARY
)
private byte[] photo;

@Attribute(
    name = "modifyTimestamp",
    readonly = true
)
private String modifyTimestamp;
~~~

OID 1.3.6.1.4.1.1466.115.121.1.15 là syntax Directory String. Hãy dùng syntax đúng theo schema thực tế; ví dụ không thể lấy OID của Directory String để mô tả một attribute binary.

type = Attribute.Type.BINARY có nghĩa JNDI provider trả giá trị dưới dạng byte[]. Nó **không** tự giải mã ảnh, certificate, SID hay cấu trúc binary tùy biến. Nếu Java field là một value object, cần converter từ/đến byte array hoặc mapping thủ công.

syntax mô tả cú pháp LDAP, không thay thế converter. Cần phân biệt ba câu hỏi:

1. Directory cho phép attribute chứa dữ liệu theo syntax nào?
2. JNDI đưa giá trị vào Java dưới dạng String hay byte[]?
3. Domain model cần kiểu Java nào và converter nào thực hiện chuyển đổi?

## 7. Ví dụ nghiệp vụ: enum trạng thái nhân viên

Directory lưu trạng thái theo chuỗi:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
objectClass: appPersonAux
uid: lan
cn: Tran Thi Lan
sn: Tran
employeeStatus: active
~~~

Ứng dụng muốn dùng enum thay vì so sánh chuỗi rải rác:

**Lưu ý về schema:** employeeStatus là attribute minh họa do ứng dụng định nghĩa; nó không phải attribute mặc định của inetOrgPerson trong schema chuẩn. Directory test phải khai báo attribute này với syntax Directory String và cho phép nó qua một auxiliary objectClass, ví dụ appPersonAux. OID và schema definition thực tế phải do tổ chức quản trị directory cấp/quản lý; không sao chép một OID minh họa vào production.

~~~java
public enum EmploymentStatus {

    ACTIVE("active"),
    SUSPENDED("suspended"),
    LEFT("left");

    private final String directoryValue;

    EmploymentStatus(String directoryValue) {
        this.directoryValue = directoryValue;
    }

    public String directoryValue() {
        return directoryValue;
    }

    public static EmploymentStatus fromDirectoryValue(String value) {
        if (value == null) {
            throw new IllegalArgumentException(
                    "employeeStatus must not be null");
        }

        for (EmploymentStatus status : values()) {
            if (status.directoryValue.equalsIgnoreCase(value.trim())) {
                return status;
            }
        }

        throw new IllegalArgumentException(
                "Unsupported employeeStatus value");
    }
}
~~~

Ở đây chuỗi trong LDAP là hợp đồng lưu trữ. Tên hằng enum Java có thể khác chuỗi directory. Ví dụ, Java dùng SUSPENDED nhưng LDAP lưu suspended.

Không nên dùng Enum.valueOf(source) nếu format directory không giống tên hằng enum hoặc không thống nhất chữ hoa/chữ thường.

## 8. Viết converter cho cả hai chiều

Dùng interface org.springframework.core.convert.converter.Converter<S,T> của Spring Framework:

~~~java
import org.springframework.core.convert.converter.Converter;

public final class StringToEmploymentStatus
        implements Converter<String, EmploymentStatus> {

    @Override
    public EmploymentStatus convert(String source) {
        return EmploymentStatus.fromDirectoryValue(source);
    }
}
~~~

Converter ngược:

~~~java
import org.springframework.core.convert.converter.Converter;

public final class EmploymentStatusToString
        implements Converter<EmploymentStatus, String> {

    @Override
    public String convert(EmploymentStatus source) {
        if (source == null) {
            throw new IllegalArgumentException(
                    "EmploymentStatus must not be null");
        }
        return source.directoryValue();
    }
}
~~~

Hai converter tách biệt:

| Chiều | Source | Target | Khi nào dùng |
|---|---|---|---|
| Đọc LDAP | String | EmploymentStatus | ODM dựng entity từ entry |
| Ghi LDAP | EmploymentStatus | String | ODM ghi entity thành LDAP attribute |

Việc có cả hai chiều giúp mapping round-trip rõ ràng. Nếu chỉ có converter đọc, thao tác ghi có thể thất bại vì không biết cách chuyển enum về chuỗi LDAP.

Không nên âm thầm map giá trị không nhận biết sang ACTIVE hoặc một trạng thái mặc định. Khi directory chứa giá trị lạ, hãy báo lỗi có ngữ cảnh để phát hiện dữ liệu không tương thích. Nếu nghiệp vụ thật sự có trạng thái UNKNOWN, hãy đưa nó thành một giá trị được định nghĩa rõ trong hợp đồng schema/domain.

## 9. Cấu hình ConversionService không dùng Spring Boot

Với Spring LDAP 3.3+, có thể tạo DefaultConversionService, thêm converter mặc định của Spring LDAP rồi đăng ký converter nghiệp vụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.ldap.convert.ConverterUtils;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.odm.core.ObjectDirectoryMapper;
import org.springframework.ldap.odm.core.impl.DefaultObjectDirectoryMapper;

@Configuration
public class LdapOdmConversionConfiguration {

    @Bean
    public ConversionService ldapOdmConversionService() {
        DefaultConversionService conversionService =
                new DefaultConversionService();

        ConverterUtils.addDefaultConverters(conversionService);

        conversionService.addConverter(
                new StringToEmploymentStatus());
        conversionService.addConverter(
                new EmploymentStatusToString());

        return conversionService;
    }

    @Bean
    public ObjectDirectoryMapper objectDirectoryMapper(
            ConversionService ldapOdmConversionService) {

        DefaultObjectDirectoryMapper mapper =
                new DefaultObjectDirectoryMapper();

        mapper.setConversionService(ldapOdmConversionService);
        return mapper;
    }

    @Bean
    public LdapTemplate ldapTemplate(
            ContextSource contextSource,
            ObjectDirectoryMapper objectDirectoryMapper) {

        LdapTemplate template = new LdapTemplate(contextSource);
        template.setObjectDirectoryMapper(objectDirectoryMapper);
        return template;
    }
}
~~~

Điểm quan trọng:

- ConverterUtils.addDefaultConverters(...) thêm converter đặc thù Spring LDAP, ví dụ chuyển đổi Name và String.
- Converter nghiệp vụ được thêm vào cùng registry.
- DefaultObjectDirectoryMapper.setConversionService(...) gắn ConversionService vào ODM.
- LdapTemplate.setObjectDirectoryMapper(...) bảo đảm các thao tác ODM dùng mapper đã cấu hình.
- Spring Data LDAP repository mặc định tìm bean LdapTemplate tên ldapTemplate; nếu ứng dụng có nhiều template, phải nối repository tới template phù hợp.

### Lưu ý khi tự khai báo ConversionService

Spring LDAP có ConversionServiceBeanFactoryPostProcessor để thêm converter mặc định vào ConversionService mặc định. Tài liệu API lưu ý post-processor này **bỏ qua** một bean ConversionService do người dùng tự khai báo tên conversionService. Khi tạo ConversionService riêng, gọi ConverterUtils.addDefaultConverters(...) như ví dụ để không bỏ mất các converter LDAP mặc định.

Không tạo nhiều ConversionService với cùng tên/ý nghĩa rồi để mapper và service khác nhau tự chọn ngẫu nhiên. Hãy đặt tên rõ và inject đúng bean.

## 10. Đăng ký converter khi dùng Spring Boot

Tài liệu Spring LDAP hiện hành mô tả cách đơn giản hơn khi dùng Spring Boot: publish các Spring Converter như bean để ObjectDirectoryMapper mà Boot cấu hình có thể nhận chúng.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;

@Configuration
public class EmploymentStatusConverters {

    @Bean
    Converter<String, EmploymentStatus> employmentStatusReader() {
        return new StringToEmploymentStatus();
    }

    @Bean
    Converter<EmploymentStatus, String> employmentStatusWriter() {
        return new EmploymentStatusToString();
    }
}
~~~

Trước khi áp dụng, kiểm tra:

1. Ứng dụng đang dùng phiên bản Spring Boot/Spring LDAP có hỗ trợ tích hợp ODM converter theo tài liệu tương ứng.
2. LdapTemplate và ObjectDirectoryMapper thực tế được Boot auto-configure đúng như dự kiến.
3. Không có mapper tự khai báo khác đang thay thế mapper mặc định.
4. Nếu ứng dụng tự khai báo ConversionService, các converter mặc định của Spring LDAP vẫn được đăng ký.
5. Repository sử dụng đúng bean LdapTemplate có mapper đó.

Nếu có nhiều LDAP template cho nhiều directory khác nhau và mỗi directory có format khác nhau, nên cấu hình mapper/ConversionService tách biệt theo từng template. Không đăng ký converter toàn cục có thể biến đổi dữ liệu của directory khác ngoài ý muốn.

## 11. Ánh xạ entity bằng ODM

Ví dụ entity có enum và một binary field:

~~~java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top",
        "person",
        "organizationalPerson",
        "inetOrgPerson",
        "appPersonAux"
    }
)
public class DirectoryPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(
        name = "employeeStatus",
        syntax = "1.3.6.1.4.1.1466.115.121.1.15",
        type = Attribute.Type.STRING
    )
    private EmploymentStatus employmentStatus;

    @Attribute(
        name = "jpegPhoto",
        type = Attribute.Type.BINARY
    )
    private byte[] photo;

    @Attribute(
        name = "modifyTimestamp",
        readonly = true
    )
    private String modifyTimestamp;

    public DirectoryPerson() {
    }

    // Getter và setter cho các field.
}
~~~

Trong ví dụ:

- dn có kiểu Name và là ID của entry.
- employmentStatus dùng converter hai chiều đã đăng ký.
- photo là dữ liệu nhị phân, JNDI trả về byte[].
- modifyTimestamp là field chỉ đọc; không persist trở lại directory.
- Các objectClass phải phù hợp schema thực tế. Converter không làm cho một attribute chưa được schema cho phép trở thành hợp lệ.

Không dùng annotation @Id của Spring Data Commons thay cho org.springframework.ldap.odm.annotations.Id. Spring Data LDAP repositories yêu cầu annotation ODM của Spring LDAP và ID kiểu javax.naming.Name.

## 12. Dùng entity với LdapTemplate và LdapRepository

Với mapper đã được gắn vào template, các phương thức ODM có thể đọc/ghi entity:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

DirectoryPerson person = ldapTemplate.findOne(
        query()
                .base("ou=people")
                .where("uid").is("lan"),
        DirectoryPerson.class);

EmploymentStatus status = person.getEmploymentStatus();

person.setEmploymentStatus(EmploymentStatus.SUSPENDED);
ldapTemplate.update(person);
~~~

Khi đọc, attribute employeeStatus: active được chuyển thành EmploymentStatus.ACTIVE. Khi cập nhật, enum được chuyển lại thành chuỗi suspended trước khi ghi.

Repository có thể sử dụng cùng LdapTemplate:

~~~java
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
}
~~~

Ví dụ:

~~~java
DirectoryPerson person = repository.findById(personDn)
        .orElseThrow();

person.setEmploymentStatus(EmploymentStatus.SUSPENDED);
repository.save(person);
~~~

Repository không tự có một converter riêng biệt cho enum trong ví dụ. Nó dựa vào mapping layer của Spring LDAP thông qua template được cấu hình. Nếu LdapTemplate trong repository khác với template đã gắn mapper, kết quả mapping có thể không như mong đợi.

## 13. Value object: converter cho mã nhân viên

Một value object có thể đóng gói validation và semantics:

~~~java
public record EmployeeCode(String value) {

    public EmployeeCode {
        if (value == null || !value.matches("EMP-[0-9]{6}")) {
            throw new IllegalArgumentException(
                    "Invalid employee code");
        }
    }
}
~~~

Converter đọc:

~~~java
import org.springframework.core.convert.converter.Converter;

public final class StringToEmployeeCode
        implements Converter<String, EmployeeCode> {

    @Override
    public EmployeeCode convert(String source) {
        return new EmployeeCode(source);
    }
}
~~~

Converter ghi:

~~~java
import org.springframework.core.convert.converter.Converter;

public final class EmployeeCodeToString
        implements Converter<EmployeeCode, String> {

    @Override
    public String convert(EmployeeCode source) {
        return source.value();
    }
}
~~~

Thêm hai converter vào ConversionService theo cách giống enum. Khi đó domain model có thể dùng:

~~~java
@Attribute(name = "employeeNumber")
private EmployeeCode employeeCode;
~~~

Converter đọc sẽ gọi constructor và validation của value object. Nếu dữ liệu LDAP cũ không đúng format, việc dựng entity thất bại sớm thay vì đưa một mã không hợp lệ đi sâu vào nghiệp vụ.

Đừng dùng converter để che giấu dữ liệu sai. Nếu directory có nhiều format hợp lệ qua các thời kỳ, hãy thiết kế parser tương thích có chủ đích, kiểm thử dữ liệu cũ và lên kế hoạch migration.

## 14. Attribute nhiều giá trị và collection

Một LDAP attribute có thể có nhiều giá trị. ODM hỗ trợ ánh xạ các giá trị đó vào collection Java phù hợp; ví dụ Spring LDAP minh họa group có field Set<Name> cho attribute uniqueMember.

~~~java
@Entry(
    objectClasses = {"top", "groupOfUniqueNames"},
    base = "ou=groups"
)
public class DirectoryGroup {

    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String name;

    @Attribute(name = "uniqueMember")
    private Set<Name> members;
}
~~~

Spring LDAP có converter cho Name/String; vì vậy DN values có thể được biểu diễn thành Name trong entity.

Khi collection chứa kiểu riêng, cần xác nhận phiên bản ODM có áp dụng converter tới từng phần tử như mong muốn. Kiểm thử với nhiều giá trị, một giá trị, không có giá trị và giá trị sai kiểu. Không mặc định rằng mọi loại collection hay nested generic đều được hỗ trợ giống nhau.

Lưu ý:

- LDAP attribute values không có thứ tự nghiệp vụ mặc định; nếu thứ tự quan trọng, phải lưu thứ tự như dữ liệu riêng.
- Set phù hợp khi chỉ cần tập giá trị duy nhất.
- List không tạo ra bảo đảm thứ tự trong directory.
- Không ghi lại toàn bộ collection chỉ để thêm một member nếu có thể dùng một ModifyRequest ADD_ATTRIBUTE riêng.
- Schema có thể yêu cầu tối thiểu một giá trị, ví dụ groupOfNames.member; converter không thể làm mất ràng buộc đó.

## 15. Binary attribute: phân biệt byte[] với value object

Với attribute nhị phân như jpegPhoto hoặc certificate, JNDI có thể trả byte[]. Khai báo:

~~~java
@Attribute(
    name = "userCertificate",
    type = Attribute.Type.BINARY
)
private byte[] certificate;
~~~

Nếu field Java là byte[], thường không cần custom converter. Annotation type = BINARY hướng dẫn ODM/JNDI xử lý dữ liệu nhị phân.

Nếu domain muốn dùng một kiểu riêng:

~~~java
public record CertificateBytes(byte[] value) {
}
~~~

thì có thể viết converter byte[] -> CertificateBytes và chiều ghi CertificateBytes -> byte[]. Converter phải giữ nguyên bytes; không tự chuyển sang Base64 trừ khi schema/ứng dụng thực sự lưu Base64 dưới dạng chuỗi.

| Cách lưu | Giá trị Java nguồn | Annotation |
|---|---|---|
| Binary LDAP attribute | byte[] | Attribute.Type.BINARY |
| Chuỗi Base64 trong Directory String | String | Attribute.Type.STRING |
| Value object bọc binary | CertificateBytes | BINARY cộng converter hai chiều |

Không log bytes certificate/photo hoặc đưa chúng vào exception message. Dùng fingerprint/hash an toàn nếu cần đối chiếu trong kiểm thử.

## 16. Chuyển đổi ngày giờ và LDAP syntax

Dữ liệu thời gian cần quy ước rõ ràng. LDAP có syntax như GeneralizedTime và UTCTime; chúng không đồng nghĩa với mọi chuỗi ISO-8601.

Trước khi viết converter, xác định:

1. Attribute schema dùng syntax OID nào.
2. Directory trả timezone UTC hay offset.
3. Có phần giây lẻ hay không.
4. Độ chính xác của dữ liệu có cần giữ nguyên không.
5. Java domain muốn Instant, OffsetDateTime, LocalDate hay kiểu khác.
6. Khi ghi, ứng dụng chuẩn hóa về timezone/format nào.

Ví dụ chuỗi GeneralizedTime đơn giản có thể có dạng:

~~~text
20261126153045Z
~~~

Chữ Z chỉ UTC. Nếu ứng dụng chỉ hỗ trợ format UTC đến giây, converter phải từ chối chuỗi có offset hoặc fractional seconds ngoài hợp đồng đó. Đừng dùng một DateTimeFormatter rút gọn rồi tuyên bố hỗ trợ toàn bộ grammar GeneralizedTime.

Không giả định Spring LDAP hay Spring Data Commons tự cung cấp converter đúng cho mọi java.time type và mọi LDAP syntax. Hãy kiểm tra ConversionService và test cả chiều đọc/ghi. Đặc biệt, chuyển LocalDateTime sang instant bằng system default timezone có thể cho kết quả khác nhau giữa các máy; chọn timezone tường minh.

## 17. Syntax OID không thay thế converter

@Attribute(syntax = "...") có thể khai báo LDAP syntax của attribute và giúp ODM phân biệt kiểu dữ liệu chính xác hơn. Tuy nhiên, nó không tự chuyển một chuỗi tùy ý thành domain object.

Ví dụ:

- Attribute có syntax Directory String thường được JNDI biểu diễn thành String.
- Attribute binary được đọc thành byte[] khi cấu hình BINARY.
- Attribute integer vẫn cần giá trị hợp lệ theo syntax; việc Java field là Integer không làm server tự sửa dữ liệu chuỗi không hợp lệ.
- Attribute GeneralizedTime cần parser/formatter khớp quy ước thời gian.

Nếu hai attribute đều được JNDI trả thành String nhưng có format nghiệp vụ khác nhau, converter theo cặp String -> TargetType có thể không đủ thông tin để phân biệt theo tên attribute. Khi đó, cân nhắc:

- Tạo value object khác nhau cho từng format.
- Dùng converter riêng theo source/target type.
- Dùng mapping thủ công cho field đặc biệt.
- Kiểm tra lại khả năng truyền syntax metadata trong phiên bản ODM đang dùng.

Không dựa vào tên attribute để suy luận syntax. Schema directory mới là nguồn định nghĩa attribute type và syntax.

## 18. Xử lý giá trị thiếu, rỗng và không hợp lệ

Các tình huống dưới đây khác nhau:

| Trạng thái LDAP | Ý nghĩa có thể có | Cách xử lý |
|---|---|---|
| Attribute không tồn tại | Không có giá trị được lưu | Dùng nullable/Optional theo domain contract |
| Attribute tồn tại với chuỗi rỗng | Có giá trị rỗng nếu schema/server cho phép | Validate riêng, không coi như absent |
| Attribute có giá trị hợp lệ | Dữ liệu đọc được | Convert bình thường |
| Attribute có giá trị ngoài enum | Dữ liệu không tương thích hoặc version mới | Báo lỗi rõ hoặc hỗ trợ UNKNOWN có chủ đích |
| Attribute binary nhưng mapper mong String | Sai khai báo type/mapping | Sửa @Attribute.type |
| Multi-valued nhưng Java field đơn trị | Cardinality không khớp | Đổi field thành collection hoặc xác định quy tắc chọn |
| Một giá trị không parse được trong collection | Dữ liệu entry không đồng nhất | Báo lỗi kèm attribute context, không âm thầm bỏ |

Converter không nên trả null cho mọi lỗi parse. Làm vậy có thể biến dữ liệu sai thành “không có dữ liệu”, khiến lỗi chỉ xuất hiện ở tầng nghiệp vụ sau đó.

Với enum, quyết định rõ giá trị không nhận biết là lỗi dữ liệu hay trạng thái tương lai cần hỗ trợ. Với thuộc tính tùy chọn, cho phép field nullable và kiểm thử hành vi ODM khi attribute vắng mặt.

## 19. Những gì converter không làm

| Yêu cầu | Converter có giải quyết? | Cơ chế phù hợp |
|---|---|---|
| String thành enum | Có | ConversionService converter |
| byte[] thành value object | Có | Converter binary hai chiều |
| DN string thành Name | Có converter LDAP mặc định | Spring LDAP default converters |
| Đổi tên entry khi RDN thay đổi | Không chỉ bằng converter | ODM DN mapping/ModifyDN |
| Escape LDAP filter | Không | LdapQueryBuilder/Filter API |
| Escape DN input | Không | LdapNameBuilder/LdapEncoder phù hợp ngữ cảnh |
| Kiểm tra objectClass/schema | Không | Directory schema/server |
| Kiểm tra quyền đọc/ghi | Không | LDAP ACL và bind identity |
| Bảo đảm giá trị duy nhất | Không | Schema constraint hoặc logic ứng dụng |
| Đồng bộ nhiều entry | Không | Quy trình nghiệp vụ/LDAP operations |
| Mã hóa mật khẩu | Không nên nhét vào converter chung | Cơ chế password/credential chuyên biệt và policy bảo mật |

Đặc biệt, không viết converter String -> String để escape mọi giá trị LDAP. Escaping phụ thuộc ngữ cảnh: DN, search filter, LDIF và dữ liệu attribute có quy tắc khác nhau. Converter của ODM chỉ chuyển kiểu dữ liệu attribute; filter và DN được xây bằng API tương ứng.

## 20. Kiểm tra converter trước khi gắn vào ODM

Có thể test converter độc lập:

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class EmploymentStatusConverterTest {

    private final StringToEmploymentStatus reader =
            new StringToEmploymentStatus();

    private final EmploymentStatusToString writer =
            new EmploymentStatusToString();

    @Test
    void readsDirectoryValue() {
        assertEquals(
                EmploymentStatus.ACTIVE,
                reader.convert("active"));
    }

    @Test
    void writesDirectoryValue() {
        assertEquals(
                "suspended",
                writer.convert(EmploymentStatus.SUSPENDED));
    }

    @Test
    void rejectsUnknownDirectoryValue() {
        assertThrows(
                IllegalArgumentException.class,
                () -> reader.convert("pending-review"));
    }

    @Test
    void rejectsNullDirectoryValue() {
        assertThrows(
                IllegalArgumentException.class,
                () -> reader.convert(null));
    }
}
~~~

Test này xác minh logic converter, nhưng chưa chứng minh ODM thực sự dùng converter đó. Cần test thêm trên ConversionService:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

ConverterUtils.addDefaultConverters(conversionService);
conversionService.addConverter(new StringToEmploymentStatus());
conversionService.addConverter(new EmploymentStatusToString());

assertTrue(conversionService.canConvert(
        String.class, EmploymentStatus.class));

assertTrue(conversionService.canConvert(
        EmploymentStatus.class, String.class));

assertEquals(
        EmploymentStatus.ACTIVE,
        conversionService.convert("active", EmploymentStatus.class));

assertEquals(
        "left",
        conversionService.convert(EmploymentStatus.LEFT, String.class));
~~~

Trong test thực tế, import assertTrue từ JUnit và cấu hình ConversionService cùng converter giống cấu hình ứng dụng. Kiểm tra cả canConvert lẫn giá trị kết quả; chỉ có bean tồn tại chưa chứng minh mapper đã sử dụng nó.

## 21. Integration test round-trip qua LDAP

Dùng LDAP test độc lập có schema cho inetOrgPerson và schema mở rộng cho employeeStatus qua appPersonAux. Không chạy thử dữ liệu schema tự định nghĩa trên production.

Quy trình:

1. Tạo DirectoryPerson có employmentStatus = ACTIVE.
2. Gọi ldapTemplate.create(person).
3. Đọc raw LDAP attribute và xác nhận giá trị được lưu là active.
4. Gọi findOne(...) hoặc repository để đọc entry lại.
5. Xác nhận field Java trở thành EmploymentStatus.ACTIVE.
6. Đổi trạng thái sang SUSPENDED và gọi update/save.
7. Đọc raw attribute để xác nhận suspended.
8. Thử giá trị LDAP không nằm trong enum và xác nhận lỗi được báo đúng.
9. Thử attribute thiếu, binary, multi-valued và read-only theo mapping tương ứng.
10. Kiểm tra converter không ảnh hưởng entity/attribute khác.

Ví dụ test minh họa:

~~~java
@Test
void convertsStatusWhenCreatingAndReadingEntry() {
    DirectoryPerson person = new DirectoryPerson();
    person.setDn(LdapNameBuilder.newInstance("ou=people")
            .add("uid", "lan-converter-test")
            .build());
    person.setUid("lan-converter-test");
    person.setCommonName("Lan Converter Test");
    person.setSurname("Test");
    person.setEmploymentStatus(EmploymentStatus.ACTIVE);

    ldapTemplate.create(person);

    DirectoryPerson loaded = ldapTemplate.findOne(
            query()
                    .base("ou=people")
                    .where("uid").is("lan-converter-test"),
            DirectoryPerson.class);

    assertEquals(
            EmploymentStatus.ACTIVE,
            loaded.getEmploymentStatus());
}
~~~

Đây là ví dụ khung; fixture, getter/setter, base DN và bean cấu hình phải khớp test project. Nên có bước đọc raw attribute riêng để chứng minh chiều ghi lưu đúng chuỗi, không chỉ chứng minh Java object sau read có trạng thái đúng.

## 22. Kiểm thử schema, version và cấu hình thật

Trước khi kết luận converter hoạt động, kiểm tra:

- Phiên bản Spring LDAP được resolve thực tế.
- Dependency không kéo đồng thời nhiều version Spring LDAP.
- ODM dùng đúng ObjectDirectoryMapper.
- LdapTemplate mà repository dùng chính là template đã cấu hình mapper.
- Converter được đăng ký trong ConversionService mà mapper nhận.
- Spring LDAP default converters không bị bỏ khi custom ConversionService.
- Entity dùng annotation từ org.springframework.ldap.odm.annotations.
- @Id có kiểu Name.
- @Attribute.syntax và @Attribute.type khớp schema/provider.
- Directory schema cho phép attribute và objectClass tương ứng.
- Bind identity có quyền đọc/ghi attribute.
- Test có dữ liệu đại diện: absent, valid, invalid, multi-valued, binary.

Một dấu hiệu hay gặp là converter test unit chạy qua nhưng repository vẫn báo lỗi chuyển đổi. Nguyên nhân thường là converter đã được tạo nhưng chưa nằm trong ConversionService mà ODM sử dụng, hoặc repository đang nhận một LdapTemplate khác.

## 23. Chuyển từ ConverterManager cũ sang ConversionService

Nếu ứng dụng đang dùng API cũ, lập kế hoạch chuyển đổi theo từng bước:

| API cũ | Hướng thay thế từ Spring LDAP 3.3+ |
|---|---|
| ConverterManager | Spring ConversionService |
| ConverterManagerImpl | DefaultConversionService hoặc ConversionService phù hợp |
| ConversionServiceConverterManager | Dùng ConversionService trực tiếp |
| ConverterManagerFactoryBean | Tự đăng ký converter vào ConversionService |
| org.springframework.ldap.odm.typeconversion.impl.Converter | org.springframework.core.convert.converter.Converter<S,T> |
| DefaultObjectDirectoryMapper.setConverterManager(...) | DefaultObjectDirectoryMapper.setConversionService(...) |
| Converter mặc định cấu hình thủ công đời cũ | ConverterUtils.addDefaultConverters(...) |

Checklist migration:

1. Ghi nhận phiên bản Spring LDAP hiện tại và các API deprecated đang sử dụng.
2. Liệt kê converter cũ, kiểu nguồn/đích và LDAP syntax liên quan.
3. Chuyển từng converter sang Spring Converter<S,T>.
4. Tạo ConversionService và đăng ký default converters của Spring LDAP.
5. Gắn ConversionService vào DefaultObjectDirectoryMapper.
6. Gắn mapper vào LdapTemplate được repository sử dụng.
7. Chạy unit test converter và integration test round-trip.
8. Xác minh các trường binary, temporal và collection.
9. Chỉ xóa cấu hình cũ sau khi toàn bộ mapping đã được kiểm chứng.

Không đổi dependency version chỉ để dùng một API mới nếu Spring Boot BOM hoặc module khác chưa tương thích. Cập nhật phiên bản theo dependency management của dự án và chạy bộ test tích hợp phù hợp.

## 24. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không convert String sang enum | Chưa đăng ký converter đọc | Thêm Converter<String, Enum> vào ConversionService |
| Đọc được nhưng ghi lỗi | Thiếu converter chiều Java sang LDAP | Đăng ký Converter<Enum, String> |
| Converter không được gọi | Mapper đang dùng ConversionService khác | Kiểm tra bean wiring của LdapTemplate |
| Mất Name/String conversion sau khi custom | Custom ConversionService thiếu converter mặc định LDAP | Gọi ConverterUtils.addDefaultConverters |
| Code cũ cảnh báo deprecated | Dùng ConverterManager hoặc ConverterManagerFactoryBean từ 3.3+ | Chuyển sang ConversionService |
| Repository không dùng ODM mong muốn | Dùng sai LdapTemplate hoặc sai bean name | Kiểm tra repository template wiring |
| Binary bị lỗi kiểu | Field/annotation type không khớp | Dùng byte[] và Attribute.Type.BINARY |
| Date lệch giờ | Không thống nhất timezone/format | Chọn UTC/offset và converter tường minh |
| Giá trị lạ biến thành null | Converter nuốt lỗi parse | Báo lỗi hoặc định nghĩa UNKNOWN có chủ đích |
| Multi-valued bị mất phần tử | Field/cardinality không khớp hoặc mapping collection sai | Kiểm thử Set/List và schema |
| LDAP từ chối attribute | Schema không cho phép hoặc ACL thiếu | Kiểm tra objectClass, syntax, ACL |
| Update field read-only bị lỗi | Operational attribute bị ghi lại | Dùng readonly=true hoặc loại khỏi mapping ghi |
| Custom converter String -> String áp dụng quá rộng | Converter không phân biệt attribute cụ thể | Dùng value object/kiểu riêng hoặc mapping thủ công |
| @DnAttribute không nhận kiểu custom | Annotation chỉ hỗ trợ String | Chuyển đổi DN component riêng; không áp converter tùy ý vào @DnAttribute |

Khi đọc stack trace, tìm nguyên nhân gốc: không tìm thấy converter, converter ném lỗi parse, JNDI trả kiểu không mong đợi, schema từ chối ghi hay ACL từ chối thao tác. Không quy mọi lỗi thành “ODM không hỗ trợ kiểu này”.

## 25. Bài tập thực hành

**Bối cảnh:** hệ thống nhân sự lưu employeeStatus dưới dạng Directory String với các giá trị active, suspended, left. Ứng dụng Java muốn dùng enum EmploymentStatus. Một số entry có jpegPhoto dạng binary và modifyTimestamp chỉ đọc.

Thực hiện trên LDAP test:

1. Xác định phiên bản Spring LDAP và Spring Data LDAP đang dùng từ dependency graph của ứng dụng.
2. Viết bảng quyết định API converter tương ứng phiên bản đó.
3. Tạo enum EmploymentStatus có giá trị directory tường minh.
4. Viết converter đọc String sang enum và converter ghi enum sang String.
5. Đăng ký hai converter trong ConversionService.
6. Với Spring LDAP 3.3+, gọi ConverterUtils.addDefaultConverters(...) trước khi thêm converter nghiệp vụ.
7. Gắn ConversionService vào DefaultObjectDirectoryMapper, sau đó gắn mapper vào LdapTemplate.
8. Nếu dùng Spring Boot, thử đăng ký converter dưới dạng bean và xác minh mapper auto-config nhận chúng.
9. Tạo entity có @Id Name, @Attribute employeeStatus, binary jpegPhoto và read-only modifyTimestamp.
10. Dùng LdapTemplate hoặc LdapRepository tạo entry rồi đọc lại; kiểm tra raw LDAP value và Java enum.
11. Thử giá trị pending-review ngoài enum; xác định lỗi và chính sách tương thích.
12. Viết converter cho EmployeeCode value object và kiểm tra validation.
13. Thử một attribute multi-valued ánh xạ thành Set<Name> hoặc collection phù hợp.
14. Kiểm tra trường hợp attribute vắng mặt và attribute rỗng.
15. Viết integration test xác minh schema/ACL và round-trip trên directory test.
16. Nếu dự án còn dùng ConverterManager, lập migration checklist sang ConversionService mà không thay đổi semantics dữ liệu.

**Tiêu chí hoàn thành:** người học chọn đúng API theo phiên bản Spring LDAP, đăng ký được converter hai chiều, chứng minh LdapTemplate/repository sử dụng đúng mapper, giữ nguyên dữ liệu LDAP khi round-trip và phân biệt được lỗi conversion với lỗi schema/ACL.

## 26. Tổng kết và tài liệu tham khảo

Cấu hình chuyển đổi kiểu trong Spring Data LDAP phải theo đúng mapping layer của Spring LDAP ODM. Repository sử dụng annotation ODM của Spring LDAP và dựa vào LdapTemplate/ObjectDirectoryMapper để đọc ghi entity.

Những điểm cần nhớ:

- Xác định phiên bản Spring LDAP trước khi chọn API.
- Từ 3.3+, dùng Spring ConversionService trực tiếp; các API ConverterManager cũ đã deprecated.
- Đăng ký converter cho cả chiều đọc và chiều ghi nếu entity cần round-trip.
- Dùng ConverterUtils.addDefaultConverters(...) khi tự tạo ConversionService để giữ converter mặc định của Spring LDAP.
- Dùng @Attribute(type = BINARY) cho dữ liệu binary và syntax OID đúng với schema.
- Kiểm soát timezone/format khi chuyển dữ liệu thời gian.
- Đảm bảo repository và LdapTemplate dùng cùng mapper đã cấu hình.
- Kiểm thử raw LDAP values và entity Java sau khi đọc lại.
- Converter không thay thế validation, DN/filter escaping, schema hoặc ACL.

Tài liệu tham khảo:

- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): cấu hình ODM, converter với Spring Boot và ứng dụng không dùng Boot, annotation và mapping methods.
- [Spring LDAP — DefaultObjectDirectoryMapper API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/odm/core/impl/DefaultObjectDirectoryMapper.html): setConversionService và setConverterManager deprecated.
- [Spring LDAP — ConverterUtils API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/convert/ConverterUtils.html): đăng ký converter mặc định, có từ 3.3.
- [Spring LDAP — Attribute annotation API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/odm/annotations/Attribute.html): name, syntax, type và readonly.
- [Spring LDAP — Deprecated API list](https://docs.spring.io/spring-ldap/reference/api/java/deprecated-list.html): các API chuyển đổi cũ và hướng thay thế.
- [Spring Data LDAP — Repository Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): repository yêu cầu ODM annotations và ID kiểu javax.naming.Name.
- [Spring LDAP 3.2 API — ConverterManager](https://docs.spring.io/spring-ldap/docs/3.2.x/api/org/springframework/ldap/odm/typeconversion/ConverterManager.html): tài liệu tham khảo cho ứng dụng chưa nâng lên 3.3.
