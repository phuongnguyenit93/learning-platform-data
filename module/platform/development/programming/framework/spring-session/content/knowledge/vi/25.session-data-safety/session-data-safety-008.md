# Kiểm soát dữ liệu được giải tuần tự hóa và hạn chế kiểu đối tượng

Spring Session lưu các thuộc tính của `HttpSession` vào repository như Redis hoặc JDBC. Khi request tiếp theo cần đọc thuộc tính, repository phải giải tuần tự hóa dữ liệu để khôi phục đối tượng Java. Nếu ứng dụng lưu `SecurityContext`, principal tùy chỉnh, DTO hoặc collection, deserializer phải quyết định kiểu nào được phép tạo lại và cấu trúc dữ liệu nào được chấp nhận.

Giải tuần tự hóa dữ liệu không đáng tin cậy là một ranh giới bảo mật. Java native serialization có thể khôi phục object graph và kích hoạt logic trong quá trình đọc; JSON cũng có rủi ro nếu bật polymorphic typing quá rộng. Vì vậy, Spring Session cần một hợp đồng dữ liệu nhỏ, serializer có chính sách rõ ràng, allowlist kiểu đối tượng và giới hạn tài nguyên của payload.

## 1. Vì sao session cần được giải tuần tự hóa có kiểm soát?

Một session có thể chứa nhiều thuộc tính:

```java
session.setAttribute("userId", "user-42");
session.setAttribute("cartCount", 3);
session.setAttribute("preferences",
        new UserPreferences("vi", true));
session.setAttribute("recentItems",
        List.of("SKU-10", "SKU-20"));
```

Khi lưu, serializer chuyển các giá trị này thành byte hoặc văn bản. Ở request sau, deserializer tạo lại object để ứng dụng tiếp tục sử dụng.

Rủi ro xuất hiện khi:
- Kẻ tấn công có thể ghi hoặc sửa dữ liệu trong Redis/database.
- Một ứng dụng khác dùng chung Redis namespace nhưng có serializer hoặc classpath khác.
- Một session cũ chứa class đã bị đổi tên, xóa hoặc thay đổi cấu trúc.
- Payload khai báo một kiểu không thuộc hợp đồng session của ứng dụng.
- Payload có object graph quá sâu, mảng quá lớn hoặc quá nhiều tham chiếu.
- Một thư viện có lớp gadget bị kích hoạt trong quá trình native deserialization.

Chỉ kiểm tra rằng payload là JSON hợp lệ hoặc byte array có thể đọc được không đủ để bảo đảm an toàn. Cần kiểm tra kiểu đối tượng, kích thước, cấu trúc và nguồn dữ liệu.

## 2. Ranh giới tin cậy của session store

Spring Session thường đọc dữ liệu từ kho server-side, nhưng không nên mặc định kho đó luôn đáng tin cậy. Dữ liệu có thể bị thay đổi qua:
- Credential Redis/database bị lộ hoặc cấp quyền quá rộng.
- Một ứng dụng khác ghi nhầm vào cùng namespace.
- Công cụ vận hành, script migration hoặc tác vụ hỗ trợ sửa dữ liệu trực tiếp.
- Backup/restore từ môi trường hoặc phiên bản ứng dụng khác.
- Lỗi serialization hoặc bug khiến dữ liệu bị ghi sai định dạng.

Một session ID khó đoán và cookie được bảo vệ giúp giảm khả năng truy cập trái phép từ client, nhưng không bảo vệ kho dữ liệu khỏi một tài khoản vận hành bị xâm nhập. Hãy xem mọi byte được đưa vào deserializer là dữ liệu cần kiểm tra.

Các lớp bảo vệ nên kết hợp:
1. Redis/database chỉ cho phép ứng dụng và nhóm vận hành được ủy quyền truy cập.
2. Dùng TLS cho kết nối, credential riêng và quyền tối thiểu.
3. Tách namespace hoặc database/schema giữa các ứng dụng.
4. Dùng serializer với allowlist kiểu rõ ràng.
5. Giới hạn kích thước và độ phức tạp object graph.
6. Không lưu dữ liệu nhạy cảm hoặc object không cần thiết trong session.
7. Theo dõi lỗi deserialization và có quy trình thu hồi session lỗi.

## 3. Java Serialization mặc định của Spring Session

Theo cấu hình mặc định, Spring Session Redis dùng Java Serialization để tuần tự hóa các thuộc tính session. Spring Session JDBC cũng lưu giá trị thuộc tính dưới dạng byte array; mặc định byte array được tạo từ JDK Serialization.

Ví dụ object cần hỗ trợ serialization:

```java
public final class UserPreferences implements Serializable {

    private static final long serialVersionUID = 1L;

    private final String language;
    private final boolean compactMode;

    public UserPreferences(String language, boolean compactMode) {
        this.language = language;
        this.compactMode = compactMode;
    }

    public String getLanguage() {
        return language;
    }

    public boolean isCompactMode() {
        return compactMode;
    }
}
```

Native serialization giữ thông tin class và object graph, nên việc đổi package, tên lớp, cấu trúc trường hoặc dependency có thể ảnh hưởng khả năng đọc session cũ. Ngoài ra, deserialization có thể khôi phục các kiểu không mong muốn nếu dữ liệu bị chế tạo và filter không giới hạn.

`serialVersionUID` giúp kiểm soát tương thích nhị phân của một class, nhưng không phải cơ chế bảo mật và cũng không bảo đảm mọi thay đổi class đều tương thích về ngữ nghĩa.

## 4. Vì sao native deserialization nguy hiểm?

Java native deserialization có thể khôi phục một đồ thị đối tượng gồm nhiều lớp. Trong quá trình khôi phục, các hook như `readObject`, `readResolve` hoặc logic của thư viện có thể được gọi. Một số thư viện có các chuỗi lớp gadget; nếu payload được chế tạo và classpath có gadget phù hợp, việc đọc object có thể kích hoạt hành vi ngoài dự kiến.

Các rủi ro bao gồm:
- Thực thi logic nguy hiểm trong quá trình deserialization.
- Tiêu thụ CPU hoặc bộ nhớ quá mức do object graph lớn.
- Tạo collection hoặc mảng có kích thước bất thường.
- Khôi phục một kiểu hợp lệ về mặt Java nhưng không hợp lệ trong nghiệp vụ.
- Lỗi tương thích làm hỏng request hoặc khiến người dùng phải đăng nhập lại.

Không giải tuần tự hóa byte do người dùng gửi trực tiếp bằng `ObjectInputStream`. Không dùng native serialization cho dữ liệu không rõ nguồn gốc chỉ vì nó tiện lưu object Java. Nếu phải duy trì tương thích với session hiện có, hãy giới hạn lớp được phép và đặt giới hạn tài nguyên.

## 5. Allowlist kiểu đối tượng

Allowlist là danh sách các kiểu được phép khôi phục. Một allowlist phù hợp với session thường chỉ gồm:
- DTO session do ứng dụng sở hữu.
- Một số kiểu giá trị chuẩn như `String`, số, boolean và kiểu ngày giờ cần thiết.
- Collection cụ thể mà ứng dụng thực sự lưu.
- Các lớp Spring Security cần thiết nếu session chứa `SecurityContext`.
- Kiểu con đa hình được khai báo rõ trong hợp đồng dữ liệu.

Không cho phép toàn bộ classpath hoặc package rộng như `org.springframework.`, `com.` hay `java.` chỉ để serializer “đọc được mọi thứ”. Một package có thể chứa lớp không cần thiết, lớp mới được thêm bởi dependency hoặc gadget class.

Hãy xây allowlist từ object graph thực tế của session. Khi thêm một kiểu mới, cần có lý do nghiệp vụ, kiểm thử round-trip và kiểm tra ảnh hưởng bảo mật.

## 6. ObjectInputFilter và giới hạn Java native serialization

Từ Java 9, `ObjectInputFilter` (JEP 290) cho phép kiểm tra lớp, độ sâu object graph, số tham chiếu, kích thước stream và độ dài mảng trong lúc deserialization.

Một filter có thể:
- Cho phép một số lớp đã biết.
- Từ chối các lớp khác.
- Từ chối object graph quá sâu.
- Từ chối stream quá lớn.
- Từ chối mảng vượt kích thước cho phép.

Ví dụ cấu hình filter JVM-wide bằng pattern:

```text
-Djdk.serialFilter=maxdepth=20;maxrefs=1000;maxbytes=1048576;maxarray=100000;com.example.session.dto.*;java.lang.String;java.lang.Integer;java.lang.Long;java.lang.Boolean;java.util.ArrayList;java.util.HashMap;!*
```

Đây là ví dụ chính sách cần điều chỉnh, không phải allowlist dùng chung cho mọi ứng dụng. Một session thực tế có thể cần thêm các lớp collection, kiểu ngày giờ hoặc lớp Spring Security cụ thể. Chỉ thêm kiểu sau khi xác định nó nằm trong object graph hợp lệ.

Có thể cài đặt filter toàn JVM bằng `ObjectInputFilter.Config.setSerialFilter` ở giai đoạn khởi động, hoặc dùng thuộc tính hệ thống `jdk.serialFilter`. Filter toàn JVM có thể ảnh hưởng các thư viện khác cũng sử dụng `ObjectInputStream`, vì vậy phải kiểm thử toàn ứng dụng. Một số môi trường cần filter factory để kết hợp chính sách toàn cục với chính sách riêng theo luồng.

Nếu viết deserializer tùy chỉnh, có thể đặt filter riêng trên `ObjectInputStream` trước khi đọc object. Không giả định một serializer thư viện sẽ tự dùng filter riêng của ứng dụng nếu chưa xác minh đường tạo stream; filter JVM-wide áp dụng theo cơ chế JDK cho các stream tương ứng.

## 7. Giới hạn kích thước và độ phức tạp object graph

Allowlist chỉ giới hạn kiểu; nó không ngăn payload hợp lệ nhưng quá lớn. Cần đặt giới hạn tài nguyên:

| Giới hạn | Rủi ro được giảm |
|---|---|
| `maxdepth` | Object graph lồng nhau quá sâu gây tiêu thụ stack/CPU |
| `maxrefs` | Quá nhiều object reference gây áp lực bộ nhớ |
| `maxbytes` | Payload lớn gây tăng bộ nhớ và thời gian xử lý |
| `maxarray` | Mảng lớn gây cấp phát bộ nhớ quá mức |
| Giới hạn số thuộc tính | Session chứa quá nhiều attribute |
| Giới hạn kích thước từng attribute | Một giá trị đơn lẻ chiếm quá nhiều dung lượng |

Các con số cần dựa trên dữ liệu đo được. Đặt quá thấp có thể từ chối session hợp lệ; đặt quá cao làm giảm tác dụng bảo vệ. Hãy ghi nhận kích thước session p95/p99 và đặt ngưỡng có khoảng an toàn.

ObjectInputFilter kiểm soát graph của Java Serialization. Nếu dùng JSON, cần có giới hạn payload ở tầng HTTP/store, giới hạn độ sâu/nesting nếu parser hỗ trợ và kiểm tra kích thước attribute trước khi lưu.

## 8. Dùng JSON không tự động làm deserialization an toàn

JSON thường dễ quan sát và ít gắn chặt với Java class descriptor hơn native serialization. Tuy nhiên, JSON chỉ là định dạng dữ liệu. Nếu deserializer dùng metadata để tạo class tùy ý, rủi ro vẫn còn.

Một payload có thể chứa type metadata:

```json
{
  "@class": "com.example.session.UserPreferences",
  "language": "vi",
  "compactMode": true
}
```

Nếu ứng dụng cho phép payload chỉ định bất kỳ FQCN nào trong classpath, dữ liệu có thể yêu cầu tạo kiểu ngoài hợp đồng session. Vì vậy:
- Không bật polymorphic default typing không giới hạn.
- Dùng validator chỉ cho phép các kiểu con cụ thể.
- Ưu tiên logical type ID thay vì FQCN khi cần đa hình.
- Dùng DTO cụ thể và schema có version.
- Từ chối type ID không được đăng ký.

JSON giúp dễ xây migration và tương thích hơn, nhưng vẫn phải kiểm soát parser, kiểu, kích thước và nội dung.

## 9. Ưu tiên logical type ID thay cho tên lớp Java

Nếu một thuộc tính cần lưu nhiều implementation, có thể dùng mã định danh logic thay vì tên lớp đầy đủ.

Ví dụ:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CompactPreferences.class, name = "compact"),
    @JsonSubTypes.Type(value = DetailedPreferences.class, name = "detailed")
})
public interface DisplayPreferences {
}
```

Payload dùng `kind` với giá trị `compact` hoặc `detailed`. Jackson chỉ ánh xạ đến các kiểu con đã khai báo.

Lợi ích:
- Đổi package hoặc tên class không nhất thiết làm hỏng session cũ.
- Client không cần gửi FQCN.
- Hợp đồng dữ liệu rõ ràng và có thể version hóa.
- Có thể từ chối type ID không nằm trong danh sách.

Không tái sử dụng một type ID cho hai cấu trúc không tương thích. Nếu loại bỏ một kiểu, cần tiếp tục hỗ trợ đọc dữ liệu cũ trong thời gian session còn hiệu lực hoặc chạy migration có kiểm soát.

## 10. Jackson PolymorphicTypeValidator

Nếu cần Jackson default typing cho thuộc tính khai báo là `Object` hoặc interface, phải cấu hình `PolymorphicTypeValidator` giới hạn các subtype được phép. Không dùng validator cho phép mọi lớp.

Ví dụ khung với Jackson 2:

```java
PolymorphicTypeValidator validator =
        BasicPolymorphicTypeValidator.builder()
                .allowIfSubType("com.example.session.dto.")
                .allowIfSubType("com.example.session.security.SessionPrincipal")
                .build();

ObjectMapper mapper = JsonMapper.builder().build();

mapper.activateDefaultTyping(
        validator,
        ObjectMapper.DefaultTyping.NON_FINAL,
        JsonTypeInfo.As.PROPERTY
);
```

Ví dụ chỉ cho phép package DTO riêng và một lớp principal được chỉ định. Trong production, nên thu hẹp danh sách đến các lớp thực sự cần; cho phép cả package vẫn có thể rộng nếu package chứa nhiều kiểu không liên quan.

`DefaultTyping` và constructor serializer thay đổi theo phiên bản Jackson/Spring Data Redis. Một số API có thể bị deprecated ở phiên bản mới. Hãy kiểm tra Javadoc của phiên bản đang dùng và tránh sao chép cấu hình cũ mà không đánh giá validator.

Nếu có thể, dùng `@JsonTypeInfo`/`@JsonSubTypes` trên interface cụ thể thay cho bật default typing toàn cục cho mọi object.

## 11. Cấu hình serializer riêng cho Spring Session Redis

Spring Session Redis cho phép thay serializer mặc định bằng bean `RedisSerializer<Object>` có tên chính xác `springSessionDefaultRedisSerializer`. Tên bean là một phần của extension point; bean serializer khác tên có thể không được Spring Session sử dụng.

Ví dụ theo cấu hình Jackson 2 phổ biến:

```java
@Configuration
public class SessionRedisSerializationConfiguration {

    @Bean
    RedisSerializer<Object> springSessionDefaultRedisSerializer(
            ObjectMapper objectMapper) {
        ObjectMapper sessionMapper = objectMapper.copy();
        return new GenericJackson2JsonRedisSerializer(sessionMapper);
    }
}
```

Đây là ví dụ cấu hình serializer; `ObjectMapper` được truyền vào phải có chính sách type mapping và subtype validation phù hợp với các thuộc tính session. Không dùng nguyên application mapper nếu nó đã bật default typing rộng hoặc chứa module không cần thiết.

Với phiên bản Spring Session/Spring Data Redis mới, tài liệu có thể dùng `JacksonJsonRedisSerializer` thay cho `GenericJackson2JsonRedisSerializer`. Hãy chọn serializer theo dependency đang chạy và kiểm tra cách nó biểu diễn kiểu gốc, kiểu con và null.

Nếu session chứa Spring Security objects, cần đăng ký các Jackson modules của Spring Security để hỗ trợ những kiểu như `SecurityContext` và authentication implementation. Chỉ đăng ký module không thay thế allowlist cho DTO tùy chỉnh hoặc chính sách polymorphic typing.

## 12. Spring Security và SecurityContext trong session

`SecurityContext` thường chứa `Authentication`, principal và authorities. Nếu lưu context vào Spring Session Redis/JDBC, serializer phải đọc lại được toàn bộ object graph cần thiết.

Cần xác định:
- Principal implementation thực tế.
- Authentication token đang dùng.
- Kiểu authority.
- Các thuộc tính bổ sung trong principal.
- Jackson module cần thiết của Spring Security.
- Các lớp được phép khôi phục.
- Tính tương thích giữa phiên bản Spring Security cũ và mới.

Không thêm toàn bộ package Spring Security vào allowlist một cách tự động. Hãy kiểm tra object graph thực tế và chỉ cho phép các kiểu cần thiết. Không lưu mật khẩu thô, secret hoặc access token dài hạn trong principal/session nếu không cần.

Nếu một kiểu authentication không thể deserialize, Spring Security có thể không khôi phục được context và người dùng trở thành anonymous hoặc request phát sinh lỗi. Kiểm thử luồng login, request đã xác thực, logout và session cũ sau deploy.

## 13. Cấu hình serialization riêng cho Spring Session JDBC

Spring Session JDBC mặc định chuyển thuộc tính session thành byte array bằng JDK Serialization. Có thể tùy chỉnh quá trình chuyển đổi bằng `ConversionService` bean có tên `springSessionConversionService`.

Conversion service cần cung cấp hai hướng:
- `Object` sang `byte[]` khi lưu attribute.
- `byte[]` sang `Object` khi đọc attribute.

Khi dùng JSON, deserializer vẫn cần type mapping và allowlist như Redis. Chỉ thay converter không tự làm payload an toàn.

Ví dụ cấu trúc bean:

```java
@Bean("springSessionConversionService")
GenericConversionService springSessionConversionService(
        ObjectMapper objectMapper) {

    ObjectMapper sessionMapper = objectMapper.copy();
    GenericConversionService conversions = new GenericConversionService();

    conversions.addConverter(
            Object.class,
            byte[].class,
            new SessionJsonSerializer(sessionMapper)
    );

    conversions.addConverter(
            byte[].class,
            Object.class,
            new SessionJsonDeserializer(sessionMapper)
    );

    return conversions;
}
```

`SessionJsonSerializer` và `SessionJsonDeserializer` là các converter do ứng dụng định nghĩa để thực hiện JSON encode/decode với cùng mapper và chính sách kiểu. Cần xử lý exception, schema version và type ID không hợp lệ; không trả về object rỗng khi deserialize thất bại.

Với Spring Security, đăng ký các Jackson modules phù hợp và kiểm thử các kiểu principal/authentication được lưu. Không thay đổi global application mapper nếu chỉ session cần serializer riêng.

## 14. Schema JDBC phải khớp với định dạng serialization

Nếu JDBC converter ghi JSON nhưng cột database vẫn được thiết kế cho byte array nhị phân, truy vấn có thể thất bại hoặc lưu sai định dạng. Ví dụ PostgreSQL có thể dùng cột `JSONB` cho session attribute, nhưng schema và SQL insert/update phải được điều chỉnh tương ứng.

Cần phối hợp:
1. `springSessionConversionService` chuyển Object thành byte/text theo thiết kế.
2. Deserializer đọc lại đúng định dạng và khôi phục kiểu.
3. Cột attribute dùng kiểu dữ liệu phù hợp, ví dụ JSONB hoặc BLOB/BYTEA.
4. SQL của repository chuyển giá trị vào/ra đúng kiểu.
5. Mọi instance dùng cùng schema và converter.

Spring Session JDBC hỗ trợ tùy chỉnh query thông qua `SessionRepositoryCustomizer` và các setter query của `JdbcIndexedSessionRepository`. Cấu hình cụ thể phụ thuộc DBMS. Không giả định chỉ khai báo converter là đủ để chuyển một cột BYTEA sang JSONB.

## 15. Chỉ lưu DTO nhỏ, ổn định trong session

Cách giảm rủi ro tốt nhất là giảm số kiểu cần deserialize. Session nên chứa dữ liệu nhỏ và phục vụ trực tiếp request.

Nên lưu:
- User ID hoặc tenant ID.
- ID giỏ hàng hoặc ID quy trình.
- DTO nhỏ có schema ổn định.
- Lựa chọn giao diện hoặc trạng thái tạm thời.
- SecurityContext theo cấu hình Spring Security.

Tránh lưu:
- Entity JPA và lazy proxy.
- Đồ thị object lớn có tham chiếu vòng.
- `HttpServletRequest`, `HttpServletResponse` hoặc request-scoped object.
- Connection, socket, executor, thread hoặc file handle.
- Object phụ thuộc vào implementation của một thư viện dễ thay đổi.
- Dữ liệu nghiệp vụ chuẩn cần lấy lại từ database.

Ví dụ, thay vì lưu cả entity:

```java
session.setAttribute("order", orderEntity);
```

hãy lưu định danh:

```java
session.setAttribute("activeOrderId", order.getId());
```

Ở request sau, ứng dụng tải đơn hàng từ repository nghiệp vụ. Cách này giảm kích thước session, giảm số kiểu cần allowlist và giảm coupling với persistence layer.

## 16. Version hóa payload và tương thích rolling deployment

Trong rolling deployment, instance cũ và mới có thể cùng đọc/ghi session trong một khoảng thời gian. Nếu serializer hoặc DTO thay đổi không tương thích, một node có thể không đọc được dữ liệu node khác vừa ghi.

Các thay đổi rủi ro:
- Đổi package hoặc tên class trong Java Serialization.
- Đổi type ID trong JSON.
- Đổi kiểu dữ liệu của một field.
- Xóa field đang được code cũ yêu cầu.
- Thay đổi enum constant.
- Thay đổi Jackson module hoặc allowlist.
- Thay đổi cấu trúc SecurityContext/principal.

Có thể version hóa DTO:

```java
public record CartSessionData(
        int schemaVersion,
        List<String> productIds,
        String currency
) {
}
```

Khi đọc payload cũ, adapter có thể chuyển schema cũ sang model hiện tại. Giữ type ID và reader cũ trong thời gian session cũ còn hiệu lực. Nếu thay đổi không thể tương thích, cân nhắc namespace Redis mới, migration có kiểm soát hoặc yêu cầu đăng nhập lại theo chính sách sản phẩm.

Không để hai phiên bản serializer không tương thích cùng ghi vào một namespace mà chưa kiểm thử.

## 17. Không nhầm allowlist với xác thực tính toàn vẹn

Allowlist chỉ trả lời: “Kiểu này có được phép khôi phục không?”. Nó không trả lời: “Dữ liệu này có phải do ứng dụng hợp lệ ghi ra không?”.

Một attacker có quyền sửa Redis vẫn có thể thay đổi giá trị của một DTO hợp lệ, ví dụ đổi `role`, `accountId` hoặc `workflowState`. Deserializer có thể chấp nhận kiểu nhưng dữ liệu nghiệp vụ vẫn bị giả mạo.

Cần bảo vệ riêng:
- Redis/database ACL và credential tối thiểu.
- TLS cho kết nối.
- Network segmentation.
- Encryption at rest theo yêu cầu.
- Integrity protection hoặc chữ ký/MAC cho payload nếu threat model yêu cầu và có thiết kế key rotation phù hợp.
- Authorization kiểm tra từ nguồn nghiệp vụ có thẩm quyền, không chỉ tin session attribute.

Không dùng session attribute do client có thể điều khiển làm căn cứ duy nhất cho quyền quản trị, số dư hoặc quyền sở hữu tài nguyên.

## 18. Xử lý payload không hợp lệ

Khi deserialization thất bại, cần phân biệt:
- Kiểu không nằm trong allowlist.
- Payload bị cắt hoặc sai định dạng.
- Class không còn trên classpath.
- Schema version không được hỗ trợ.
- Payload vượt giới hạn kích thước/độ sâu.
- Object graph hợp lệ nhưng invariant nghiệp vụ sai.

Không nên bắt mọi exception rồi trả về session rỗng mà không ghi nhận. Điều đó có thể che lỗi tương thích hoặc tạo hành vi bảo mật không rõ ràng.

Chính sách thường gặp:
1. Từ chối khôi phục session lỗi.
2. Không cấp quyền dựa trên context chưa khôi phục.
3. Ghi metric và log loại lỗi, repository, serializer version.
4. Che session ID và không log payload đầy đủ.
5. Có thể xóa session hỏng nếu đã xác minh ID và hành động an toàn.
6. Yêu cầu đăng nhập lại khi không thể khôi phục SecurityContext.
7. Theo dõi tỷ lệ lỗi sau rolling deployment.

Nếu cần xóa session hỏng tự động, tránh xóa nhầm session mới được cập nhật đồng thời. Với Redis, hãy dùng API repository và cân nhắc race condition khi session hết hạn hoặc được ghi lại; không xóa key theo tên nội bộ mà không hiểu cấu trúc phiên bản.

## 19. Kiểm thử allowlist và deserialization

Kiểm thử phải bao gồm cả payload hợp lệ và không hợp lệ.

**Round-trip hợp lệ**
1. Tạo DTO session.
2. Serialize bằng serializer production.
3. Deserialize lại.
4. Xác nhận kiểu, field và giá trị được giữ nguyên.

**Từ chối kiểu không được phép**
1. Tạo payload có type ID không đăng ký hoặc class ngoài allowlist.
2. Thử deserialize.
3. Xác nhận bị từ chối và không tạo object không mong muốn.
4. Xác nhận lỗi được ghi nhận mà không lộ payload nhạy cảm.

**Giới hạn tài nguyên**
- Payload vượt `maxbytes`.
- Object graph vượt `maxdepth`.
- Quá nhiều references.
- Mảng quá lớn.
- Collection chứa quá nhiều phần tử.
- JSON lồng nhau quá sâu.

**Tương thích**
- Session được ghi bởi phiên bản trước.
- Type ID cũ.
- DTO thiếu field mới.
- Principal và SecurityContext cũ.
- Rolling deployment với hai phiên bản ứng dụng.

Test serializer độc lập chưa chứng minh repository thực sự dùng bean đó. Với Redis, chạy integration test qua Spring Session Redis repository. Với JDBC, kiểm tra `springSessionConversionService`, schema và SQL thực tế. Dùng Redis/database test thật hoặc Testcontainers khi phù hợp.

## 20. Kiểm thử bảo mật cho session repository

Một bộ test integration nên xác nhận:
- Bean Redis serializer có đúng tên `springSessionDefaultRedisSerializer`.
- JDBC conversion service có đúng tên `springSessionConversionService`.
- Các instance dùng cùng mapper, allowlist và schema version.
- SecurityContext được serialize/deserialize thành công.
- Principal không nằm trong allowlist bị từ chối.
- Type ID lạ bị từ chối.
- Session hỏng không được xem là đã xác thực.
- Logout và invalidate làm session không thể khôi phục.
- Payload quá lớn hoặc quá sâu bị từ chối.
- Session cũ sau deploy được đọc hoặc bị thu hồi theo chính sách đã định.

Không dùng payload độc hại thực thi mã trong môi trường production. Các test negative nên dùng lớp kiểm thử vô hại được thiết kế để chứng minh filter từ chối, cùng dữ liệu giả lập.

## 21. Quy trình triển khai thay đổi serializer

Khi thay serializer hoặc allowlist:

1. Liệt kê mọi session attribute và kiểu runtime đang được lưu.
2. Xác định repository là Redis hay JDBC.
3. Kiểm tra serializer/conversion service mà Spring Session thực sự sử dụng.
4. Chọn DTO nhỏ và type ID ổn định.
5. Xây allowlist tối thiểu.
6. Bật giới hạn kích thước và object graph.
7. Kiểm thử payload hợp lệ, payload không hợp lệ và session cũ.
8. Đồng bộ cấu hình trên mọi instance.
9. Triển khai theo cách tương thích hoặc dùng namespace mới.
10. Theo dõi lỗi deserialization, session bị thu hồi và tỷ lệ đăng nhập lại.

Không mở rộng allowlist toàn package chỉ để xử lý lỗi phát sinh sau deploy. Hãy xác định lớp nào đang được ghi, vì sao nó xuất hiện và liệu session có nên chứa lớp đó hay không.

## 22. Checklist an toàn

- Session chỉ chứa DTO nhỏ, ổn định và dữ liệu thật sự cần thiết.
- Không deserialize byte do client gửi trực tiếp bằng Java native serialization.
- Redis serializer được cấu hình qua bean `springSessionDefaultRedisSerializer`.
- JDBC converter được cấu hình qua `springSessionConversionService` nếu cần tùy chỉnh.
- Jackson polymorphic typing có validator/allowlist cụ thể.
- Ưu tiên logical type ID cho các kiểu đa hình.
- Java native serialization có ObjectInputFilter phù hợp nếu vẫn sử dụng.
- Giới hạn độ sâu, số tham chiếu, kích thước stream, mảng và số attribute.
- Principal và SecurityContext được kiểm thử với serializer thực tế.
- Không cho phép package hoặc class không cần thiết.
- Mọi instance dùng cùng serializer, schema và type mapping.
- Có kế hoạch version hóa, migration hoặc thu hồi session cũ.
- Redis/database được bảo vệ bằng ACL, TLS và quyền tối thiểu.
- Log lỗi không chứa cookie, session ID nguyên vẹn hoặc payload nhạy cảm.
- Có integration test với payload không hợp lệ và session cũ.

Spring Session chỉ có thể khôi phục an toàn những kiểu dữ liệu mà ứng dụng xác định rõ và kiểm soát được. Với Java Serialization, dùng ObjectInputFilter để giới hạn lớp và kích thước object graph; với JSON, giới hạn polymorphic type bằng allowlist hoặc logical type ID. Redis dùng bean `springSessionDefaultRedisSerializer` để tùy chỉnh serializer, còn JDBC dùng `springSessionConversionService` và schema/query tương thích. Kết hợp các biện pháp này với DTO nhỏ, version hóa payload, quyền truy cập kho dữ liệu tối thiểu và kiểm thử negative giúp giảm rủi ro deserialization và tránh lỗi session khi triển khai nhiều instance.

## Tài liệu tham khảo

- [Spring Session — Redis Configurations](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session — JDBC Configuration and JSON Attributes](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)
- [Oracle Java — ObjectInputFilter API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/ObjectInputFilter.html)
- [Jackson — Polymorphic Deserialization](https://github.com/FasterXML/jackson-docs/wiki/JacksonPolymorphicDeserialization)

