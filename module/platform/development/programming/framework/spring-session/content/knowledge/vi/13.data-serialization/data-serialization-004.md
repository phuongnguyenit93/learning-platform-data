# Ánh xạ kiểu dữ liệu, thông tin kiểu và giới hạn lớp được phép khôi phục

Spring Session lưu các thuộc tính của `HttpSession` vào repository như Redis hoặc JDBC. Khi request tiếp theo cần đọc thuộc tính, repository phải khôi phục lại đúng kiểu đối tượng để mã ứng dụng tiếp tục sử dụng. Vì dữ liệu được tuần tự hóa rồi giải tuần tự hóa qua ranh giới request, instance hoặc phiên bản ứng dụng, định dạng lưu trữ cần mô tả được kiểu dữ liệu, các kiểu con hợp lệ và giới hạn lớp được phép tạo lại.

Đây không chỉ là vấn đề định dạng JSON hay Java Serialization. Một serializer quá rộng có thể cho phép khôi phục những lớp không mong muốn; một allowlist quá hẹp có thể khiến session cũ không đọc được sau khi triển khai. Bài này trình bày cách ánh xạ kiểu, sử dụng type metadata, giới hạn lớp được giải tuần tự hóa và duy trì tương thích dữ liệu khi vận hành Spring Session trên nhiều instance.

## 1. Vì sao session cần ánh xạ kiểu dữ liệu?

Một session có thể chứa nhiều loại giá trị:

```java
session.setAttribute("userId", "user-42");
session.setAttribute("cartCount", 3);
session.setAttribute("lastSeen", Instant.now());
session.setAttribute("preferences", new UserPreferences("vi", true));
session.setAttribute("recentItems", List.of("A-10", "B-20"));
```

Khi lưu trong repository, serializer chuyển những đối tượng này thành dạng byte hoặc văn bản. Ở request khác, deserializer phải tạo lại các giá trị tương ứng.

Với một chuỗi đơn giản, kiểu dữ liệu có thể được suy ra dễ dàng. Nhưng với một thuộc tính có kiểu khai báo là `Object`, một interface hoặc một collection chứa nhiều loại phần tử, dữ liệu JSON có thể không đủ thông tin để xác định lớp cụ thể cần khôi phục.

Ví dụ, thuộc tính `payment` có thể chứa `CardPayment` hoặc `BankTransfer`. Nếu chỉ lưu các trường dữ liệu mà không có quy tắc phân biệt kiểu, deserializer không biết nên tạo implementation nào.

Ánh xạ kiểu dữ liệu giải quyết vấn đề đó bằng cách xác định quan hệ giữa:
- Kiểu mà ứng dụng khai báo hoặc mong đợi.
- Kiểu cụ thể của đối tượng được lưu.
- Thông tin kiểu được ghi vào dữ liệu tuần tự hóa.
- Lớp được phép tạo lại khi đọc dữ liệu.

## 2. Type metadata là gì?

Type metadata là thông tin đi kèm dữ liệu để deserializer nhận biết kiểu cụ thể. Tùy serializer, metadata có thể được lưu dưới dạng tên lớp, mã định danh logic hoặc cấu trúc bên ngoài payload.

Ví dụ JSON có thông tin tên lớp:

```json
{
  "@class": "com.example.session.UserPreferences",
  "language": "vi",
  "marketingEnabled": true
}
```

Một cách khác là dùng mã định danh logic:

```json
{
  "kind": "preferences",
  "language": "vi",
  "marketingEnabled": true
}
```

Hai cách này có ý nghĩa khác nhau:

| Cách biểu diễn | Ưu điểm | Hạn chế |
|---|---|---|
| Tên lớp đầy đủ (FQCN) | Có thể khôi phục trực tiếp kiểu Java cụ thể | Gắn dữ liệu với package và tên lớp; đổi package có thể làm dữ liệu cũ không đọc được |
| Mã định danh logic như `kind` | Định dạng ổn định hơn khi refactor tên lớp | Cần duy trì bảng ánh xạ ID sang kiểu Java |
| Không có metadata đa hình | Payload đơn giản, dễ đọc | Chỉ phù hợp khi kiểu đích đã biết rõ và cấu trúc không cần lựa chọn kiểu con |

Không phải mọi thuộc tính đều cần type metadata. Với DTO có kiểu cụ thể và cấu trúc ổn định, serializer có thể khôi phục trực tiếp kiểu đích. Metadata đa hình chỉ nên bật ở những điểm thực sự cần phân biệt các implementation.

## 3. Serialization mặc định và sự khác nhau giữa Redis với JDBC

Spring Session lưu thuộc tính session theo serializer hoặc cơ chế chuyển đổi của repository đang dùng. Không nên giả định một cấu hình serializer áp dụng giống nhau cho mọi loại repository.

### Redis

Với Spring Session Redis, serializer mặc định thường dựa trên Java Serialization. Ứng dụng có thể cung cấp bean `RedisSerializer<Object>` có tên `springSessionDefaultRedisSerializer` để tùy chỉnh cách tuần tự hóa thuộc tính session.

Ví dụ khai báo bean:

```java
@Bean
RedisSerializer<Object> springSessionDefaultRedisSerializer() {
    return new JdkSerializationRedisSerializer();
}
```

Đây là cách giữ serializer Java mặc định một cách tường minh, không phải lựa chọn được khuyến nghị cho mọi hệ thống. Nếu dùng JSON, serializer phải xử lý được những kiểu đối tượng thực tế mà session đang lưu.

### JDBC

Spring Session JDBC lưu thuộc tính session trong cột nhị phân của schema. Việc chuyển đổi đối tượng thành byte và ngược lại được thực hiện thông qua cơ chế conversion của repository. Cấu hình `RedisSerializer` không tự áp dụng cho JDBC.

Nếu cần tùy chỉnh serialization cho JDBC, hãy dùng extension point `ConversionService` mà phiên bản Spring Session JDBC đang hỗ trợ, thường được cấu hình qua bean conversion service dành cho Spring Session. Cần kiểm tra tên bean và API của phiên bản cụ thể trước khi cấu hình. Hãy bảo đảm cả converter ghi và converter đọc sử dụng cùng một định dạng, cùng quy tắc type mapping và cùng chính sách giới hạn kiểu.

Dù chọn Redis hay JDBC, mục tiêu vẫn giống nhau: các instance cần hiểu cùng định dạng dữ liệu và chỉ khôi phục những kiểu được ứng dụng cho phép.

## 4. Dùng JSON với thông tin kiểu rõ ràng

JSON có ưu điểm là dễ quan sát, có thể đọc bằng nhiều công cụ và ít phụ thuộc trực tiếp vào cơ chế Java Object Serialization. Tuy nhiên, JSON không tự giữ đầy đủ kiểu runtime của mọi đối tượng Java.

Một DTO đơn giản có thể được biểu diễn như sau:

```java
public record UserPreferences(
        String language,
        boolean marketingEnabled
) implements Serializable {
}
```

Nếu thuộc tính session luôn được đọc theo kiểu `UserPreferences`, serializer không nhất thiết cần lưu FQCN. Nhưng nếu thuộc tính khai báo là interface hoặc lớp cha, cần một quy tắc ánh xạ kiểu con.

Một cách dùng Jackson là khai báo type ID logic cho các kiểu con đã biết:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(
        value = CardPayment.class,
        name = "card"
    ),
    @JsonSubTypes.Type(
        value = BankTransfer.class,
        name = "bank-transfer"
    )
})
public interface PaymentMethod {
}
```

Khi serialize, payload có thể chứa `kind` với giá trị `card` hoặc `bank-transfer`. Jackson ánh xạ các ID này sang những lớp đã khai báo trong `@JsonSubTypes`.

Cách này không yêu cầu client gửi tên lớp Java. ID logic có thể được giữ ổn định khi package hoặc tên implementation thay đổi, miễn là ứng dụng tiếp tục hỗ trợ ID cũ hoặc có migration dữ liệu phù hợp.

## 5. GenericJackson2JsonRedisSerializer và default typing

Trong Spring Session Redis, một lựa chọn phổ biến là `GenericJackson2JsonRedisSerializer`. Serializer này hỗ trợ lưu các object có kiểu runtime khác nhau. Để khôi phục object đa hình, nó cần thông tin kiểu trong JSON; cấu hình mặc định của serializer có thể dùng type metadata gắn với tên lớp.

Ví dụ bean serializer cho Redis:

```java
@Bean(name = "springSessionDefaultRedisSerializer")
RedisSerializer<Object> springSessionDefaultRedisSerializer() {
    ObjectMapper mapper = JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .build();

    PolymorphicTypeValidator validator =
            BasicPolymorphicTypeValidator.builder()
                    .allowIfSubType("com.example.session.dto.")
                    .allowIfSubType(ArrayList.class)
                    .allowIfSubType(LinkedHashMap.class)
                    .allowIfSubType(LinkedHashSet.class)
                    .build();

    mapper.activateDefaultTyping(
            validator,
            ObjectMapper.DefaultTyping.NON_FINAL,
            JsonTypeInfo.As.PROPERTY
    );

    return new GenericJackson2JsonRedisSerializer(mapper);
}
```

Đây là ví dụ minh họa cho Jackson 2 và Spring Data Redis có API tương thích. Cần bổ sung import và điều chỉnh danh sách lớp theo mô hình dữ liệu thực tế. `JavaTimeModule` hỗ trợ các kiểu ngày giờ Java như `Instant` và `LocalDate`; việc thêm module không thay thế allowlist cho kiểu đa hình.

`activateDefaultTyping` làm serializer/deserializer sử dụng metadata cho các kiểu phù hợp với chính sách `DefaultTyping`. `PolymorphicTypeValidator` giới hạn kiểu con được phép. Không dùng validator cho phép mọi subtype trong ứng dụng production chỉ để tránh lỗi giải tuần tự hóa.

API Jackson và constructor serializer thay đổi theo phiên bản. Một số phiên bản Spring Data Redis mới có thể đánh dấu các API Jackson 2 cũ là deprecated khi hệ sinh thái chuyển sang Jackson 3. Hãy chọn cấu hình tương thích với phiên bản Spring Boot, Spring Data Redis và Spring Session mà dự án đang dùng.

## 6. Giới hạn lớp được phép khôi phục

Deserializer không nên tạo tùy ý bất kỳ lớp nào chỉ vì payload yêu cầu. Dữ liệu tuần tự hóa có thể bị sửa đổi nếu Redis/database bị truy cập trái phép, bị nạp dữ liệu từ môi trường khác hoặc chứa payload cũ không đáng tin cậy.

Một allowlist tốt chỉ cho phép:
- DTO session do ứng dụng kiểm soát.
- Các kiểu collection cụ thể mà serializer thực sự cần.
- Các kiểu giá trị chuẩn đã được kiểm thử, ví dụ một số kiểu ngày giờ.
- Những kiểu Spring Security cần thiết nếu session lưu `SecurityContext`.

Không nên cho phép toàn bộ package rộng như `org.springframework.` hoặc `com.` chỉ để serializer đọc được mọi object. Một package có thể chứa nhiều lớp không cần thiết hoặc thay đổi theo dependency trong tương lai.

Với `BasicPolymorphicTypeValidator`, có thể cho phép package DTO riêng của ứng dụng và các kiểu collection cụ thể. Danh sách trên phải phản ánh chính xác dữ liệu session được lưu, không phải toàn bộ classpath.

Nếu session có `SecurityContext` của Spring Security, serializer có thể cần khôi phục các lớp như `SecurityContextImpl`, authentication token và authorities. Không nên thêm cả package Spring Security một cách mù quáng. Hãy xác định object graph thực tế, giới hạn kiểu được phép và kiểm thử login, request đã xác thực, logout cùng các trường hợp session cũ.

## 7. Rủi ro khi giải tuần tự hóa lớp không tin cậy

Java Serialization có thể khôi phục object graph và gọi logic trong quá trình deserialization. Một số thư viện có lớp gadget mà khi kết hợp với dữ liệu được chế tạo có thể dẫn tới hành vi nguy hiểm. Vì vậy, việc đọc byte không đáng tin cậy bằng `ObjectInputStream` có thể tạo rủi ro thực thi mã hoặc truy cập tài nguyên ngoài dự kiến.

JSON cũng không mặc nhiên an toàn. Nếu bật polymorphic default typing quá rộng, payload có thể yêu cầu Jackson khởi tạo những subtype không mong muốn. Allowlist và `PolymorphicTypeValidator` là một lớp bảo vệ quan trọng.

Các nguyên tắc cần tuân thủ:

- Chỉ giải tuần tự hóa dữ liệu từ kho được bảo vệ và có kiểm soát quyền ghi.
- Bật xác thực, ACL, TLS và phân tách mạng cho Redis; giới hạn quyền truy cập database.
- Không nhận payload session trực tiếp từ người dùng hoặc endpoint upload rồi đưa vào deserializer.
- Không bật default typing với validator cho phép mọi lớp.
- Không dùng Java Serialization cho object graph tùy ý nếu không có nhu cầu tương thích rõ ràng.
- Cập nhật dependency và loại bỏ thư viện có gadget không cần thiết.
- Xem dữ liệu session trong Redis/database là dữ liệu nhạy cảm, cần kiểm soát backup, restore và quyền vận hành.

Bảo vệ Redis không thay thế allowlist; allowlist cũng không thay thế bảo vệ kho dữ liệu. Cần kết hợp các lớp kiểm soát.

## 8. Ánh xạ kiểu ổn định thay vì phụ thuộc tên lớp

Nếu JSON chứa FQCN, đổi package hoặc đổi tên lớp có thể làm dữ liệu session cũ không khôi phục được. Để giảm phụ thuộc này, hãy dùng type ID logic ổn định như `card` hoặc `bank-transfer`.

Ví dụ:

```java
@JsonTypeName("card")
public final class CardPayment implements PaymentMethod {
    private String lastFourDigits;
    // getter/setter
}

@JsonTypeName("bank-transfer")
public final class BankTransfer implements PaymentMethod {
    private String bankCode;
    // getter/setter
}
```

Các ID này trở thành một phần của schema lưu trữ. Khi đổi tên class, có thể giữ nguyên `@JsonTypeName` để dữ liệu cũ tiếp tục ánh xạ vào implementation mới. Khi bỏ một subtype, cần quyết định dữ liệu cũ sẽ được chuyển đổi, đọc tương thích hay hết hạn theo session timeout.

Không tái sử dụng cùng một type ID cho hai cấu trúc không tương thích. Nếu thay đổi cấu trúc lớn, hãy thêm version vào DTO hoặc type ID mới và viết migration rõ ràng.

## 9. Version hóa DTO và tương thích khi rolling deployment

Trong cụm nhiều instance, các phiên bản ứng dụng có thể cùng tồn tại trong một khoảng thời gian khi rolling update. Instance mới phải đọc được session do instance cũ ghi, và instance cũ có thể tiếp tục nhận request trong khi session đã được instance mới cập nhật.

Ví dụ DTO có phiên bản schema:

```java
public record CartSessionData(
        int schemaVersion,
        List<String> productIds,
        String currency
) implements Serializable {
}
```

Khi thay đổi cấu trúc:
- Thêm trường mới với giá trị mặc định hoặc cách xử lý khi trường bị thiếu.
- Tránh đổi kiểu trường hiện có mà không có migration.
- Giữ hỗ trợ type ID cũ trong giai đoạn chuyển đổi.
- Không xóa class cũ ngay khi còn session có thể chứa dữ liệu của class đó.
- Kiểm tra cả dữ liệu ghi bởi phiên bản cũ lẫn dữ liệu ghi bởi phiên bản mới.

Một phiên bản mới có thể dùng adapter để chuyển DTO cũ sang model mới sau khi đọc. Nếu serializer không còn nhận diện type ID cũ, session có thể phát sinh lỗi trước khi logic adapter được chạy. Vì vậy, compatibility phải được xử lý ở tầng serializer/type mapping đủ sớm.

Khi định dạng thay đổi không thể tương thích hai chiều, cân nhắc namespace Redis mới, migration có kiểm soát hoặc buộc người dùng đăng nhập lại theo chính sách sản phẩm. Không để hai serializer không tương thích cùng ghi vào một namespace mà chưa thử nghiệm.

## 10. Chọn kiểu dữ liệu phù hợp để lưu trong session

Session nên lưu dữ liệu nhỏ, ổn định và phục vụ trực tiếp việc xử lý request. Các kiểu phù hợp thường là:
- ID người dùng hoặc ID đối tượng nghiệp vụ.
- DTO nhỏ với các trường primitive, string và collection đơn giản.
- Lựa chọn giao diện hoặc trạng thái quy trình tạm thời.
- Thông tin xác thực mà Spring Security quản lý theo cấu hình tương thích.

Tránh lưu:
- Entity JPA còn gắn với persistence context hoặc lazy proxy.
- Đối tượng có tham chiếu vòng phức tạp.
- `HttpServletRequest`, `HttpServletResponse`, connection hoặc resource đang mở.
- Object chứa thread, executor, file handle hoặc socket.
- DTO lớn lặp lại dữ liệu đã có trong database.

Ví dụ, thay vì lưu cả entity đơn hàng:

```java
session.setAttribute("order", orderEntity);
```

hãy lưu ID hoặc DTO tối thiểu:

```java
session.setAttribute("activeOrderId", order.getId());
```

Ở request sau, ứng dụng tải dữ liệu mới nhất từ repository nghiệp vụ. Cách này giảm kích thước session, giảm coupling với entity mapping và làm serializer dễ kiểm soát hơn.

## 11. Lỗi thường gặp khi khôi phục dữ liệu

| Lỗi | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `ClassNotFoundException` | Class đã bị xóa/đổi package hoặc classpath instance không đồng nhất | Giữ compatibility class hoặc migration dữ liệu |
| `InvalidClassException` | `serialVersionUID` hoặc cấu trúc Java Serialization không tương thích | Version hóa dữ liệu và kiểm soát thay đổi class |
| Jackson `InvalidTypeIdException` | Type ID không được đăng ký hoặc bị validator từ chối | Kiểm tra mapping và allowlist; không mở toàn bộ subtype |
| Jackson `MismatchedInputException` | JSON không khớp kiểu đích hoặc schema thay đổi | Dùng DTO ổn định và migration |
| Không khôi phục được collection | Kiểu collection runtime không nằm trong allowlist hoặc metadata thiếu | Chọn kiểu collection ổn định và cho phép đúng kiểu cần thiết |
| Session cũ lỗi sau deploy | Các instance dùng serializer/type mapping khác nhau | Đồng bộ cấu hình và kiểm thử rolling update |

Không nên xử lý lỗi bằng cách cho phép tất cả lớp hoặc bỏ kiểm tra type metadata. Cần xác định payload nào được ghi bởi phiên bản nào, lớp nào cần thiết và liệu dữ liệu có đáng tin cậy hay không.

Trong production, tránh log nguyên payload session vì nó có thể chứa thông tin xác thực hoặc dữ liệu cá nhân. Log session ID đã che hoặc mã tham chiếu an toàn, tên thuộc tính và loại lỗi ở mức đủ để chẩn đoán.

## 12. Java Serialization và serialVersionUID

Nếu dùng Java Serialization, lớp cần triển khai `Serializable` và có thể khai báo `serialVersionUID`:

```java
public final class UserPreferences implements Serializable {

    private static final long serialVersionUID = 1L;

    private String language;
    private boolean marketingEnabled;
}
```

`serialVersionUID` giúp kiểm soát tương thích nhị phân giữa phiên bản class. Tuy nhiên, giữ nguyên UID không đảm bảo mọi thay đổi cấu trúc đều tương thích về ngữ nghĩa. Đổi kiểu trường, đổi quan hệ object graph hoặc thay đổi invariant có thể vẫn làm dữ liệu cũ không dùng được.

Không nên tự tăng hoặc giữ UID một cách máy móc. Cần xác định trường nào được thêm, bỏ hoặc đổi, rồi kiểm thử dữ liệu serialize bởi phiên bản cũ với code mới.

Java Object Serialization cũng có thể chịu ảnh hưởng của `ObjectInputFilter` để giới hạn lớp, độ sâu object graph, số tham chiếu và kích thước mảng khi khôi phục. Nếu xây dựng serializer Java tùy chỉnh, cần tích hợp filter theo API và runtime Java đang dùng. Không giả định mọi serializer mặc định của Spring Data tự động dùng chính sách filter mà ứng dụng mong muốn.

## 13. Kiểm thử serializer và allowlist

Kiểm thử serializer độc lập giúp phát hiện lỗi ánh xạ kiểu trước khi đưa vào Spring Session:

```java
@Test
void roundTripsKnownSessionType() {
    RedisSerializer<Object> serializer = springSessionDefaultRedisSerializer();

    UserPreferences source = new UserPreferences("vi", true);
    byte[] bytes = serializer.serialize(source);

    Object restored = serializer.deserialize(bytes);

    assertThat(restored).isInstanceOf(UserPreferences.class);
    assertThat(restored).isEqualTo(source);
}
```

Ngoài trường hợp hợp lệ, cần kiểm thử kiểu không được phép. Payload có type ID lạ phải bị từ chối, không được âm thầm tạo một lớp tùy ý.

Bộ kiểm thử nên bao gồm:
1. String, số, boolean và các kiểu giá trị chuẩn.
2. DTO session và collection được cho phép.
3. Các kiểu con đa hình đã đăng ký.
4. Type ID không có trong mapping.
5. Kiểu thuộc package không được phép.
6. Payload thiếu trường, có trường mới hoặc chứa schema version cũ.
7. Dữ liệu được ghi bởi phiên bản ứng dụng trước.
8. Session có `SecurityContext` nếu Spring Security lưu nó trong session.
9. Tạo, đọc, cập nhật và logout qua repository thật.
10. Hai instance có cùng serializer đọc được session do instance còn lại ghi.

Với Redis, nên dùng Redis thật trong integration test để kiểm tra serializer được Spring Session thực sự chọn. Với JDBC, kiểm tra conversion service và schema của repository JDBC riêng. Test serializer độc lập không chứng minh cấu hình bean đã được repository sử dụng.

## 14. Quy trình thay đổi type mapping an toàn

Khi thay serializer hoặc allowlist, thực hiện theo trình tự:

1. Liệt kê các thuộc tính session đang được ứng dụng lưu và kiểu runtime thực tế của chúng.
2. Xác định repository là Redis hay JDBC và extension point serialization của phiên bản đang dùng.
3. Chọn DTO ổn định, tránh lưu entity hoặc object graph không cần thiết.
4. Quyết định dùng kiểu đích cụ thể, type ID logic hay type metadata theo lớp.
5. Xây allowlist tối thiểu cho các DTO, collection và kiểu framework thật sự cần.
6. Kiểm thử payload hợp lệ, payload không được phép và session đã lưu từ phiên bản cũ.
7. Triển khai cấu hình serializer đồng nhất trên mọi instance.
8. Theo dõi lỗi deserialization, số session bị mất và tỷ lệ người dùng phải đăng nhập lại.
9. Chỉ xóa hỗ trợ type ID hoặc class cũ sau khi thời hạn session cũ đã qua hoặc dữ liệu đã được migration.

Không dùng một allowlist quá rộng để làm cho việc nâng cấp “chạy được”. Nếu một lớp mới xuất hiện trong payload, hãy xác định vì sao nó được lưu và liệu có nên là một phần của session contract hay không.

## 15. Nguyên tắc lựa chọn

Ánh xạ kiểu dữ liệu giúp Spring Session khôi phục đúng object graph từ repository. Type metadata giúp phân biệt kiểu con khi thuộc tính khai báo bằng interface hoặc `Object`. Allowlist và validator giới hạn những lớp được phép tạo lại, giảm rủi ro khi payload bị thay đổi hoặc chứa dữ liệu cũ không mong muốn.

Với Redis, có thể tùy chỉnh `RedisSerializer<Object>` qua bean `springSessionDefaultRedisSerializer`. Với JDBC, cần cấu hình conversion service theo extension point của repository JDBC; bean serializer Redis không điều khiển dữ liệu JDBC. Khi dùng Jackson polymorphic typing, chỉ cho phép các kiểu cụ thể mà session thực sự cần và ưu tiên type ID logic ổn định khi có thể.

Trước khi triển khai, hãy kiểm thử tương thích giữa các phiên bản ứng dụng, xác nhận mọi instance dùng cùng serializer và bảo đảm session chỉ chứa dữ liệu nhỏ, ổn định. Cách làm này giúp dữ liệu phiên được khôi phục có kiểm soát, tránh phụ thuộc mong manh vào tên lớp và giảm rủi ro từ deserialization không an toàn.

