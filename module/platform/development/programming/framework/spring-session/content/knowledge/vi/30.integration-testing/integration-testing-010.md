# Kiểm tra tương thích serializer giữa hai phiên bản ứng dụng

Khi triển khai rolling deployment, các instance Spring Session của phiên bản cũ và phiên bản mới có thể cùng đọc, ghi một kho session trong một khoảng thời gian. Nếu hai phiên bản serialize hoặc deserialize session attributes theo những định dạng không tương thích, request đi qua node mới có thể chạy được nhưng request tiếp theo quay về node cũ lại lỗi. Người dùng có thể bị đăng xuất, request trả 5xx hoặc một attribute bị mất sau khi deserialize.

Kiểm thử tương thích serializer phải kiểm tra cả hai chiều: payload do phiên bản cũ ghi có được phiên bản mới đọc đúng không, và payload do phiên bản mới ghi có được phiên bản cũ đọc đúng không. Trong rolling deployment, chiều thứ hai thường là điểm dễ bị bỏ sót vì node cũ vẫn còn nhận traffic sau khi node mới đã bắt đầu ghi dữ liệu. Bài này xây dựng chiến lược kiểm thử cho session dùng Redis hoặc JDBC, từ DTO contract đến kiểm thử hai phiên bản chạy song song và quy trình nâng cấp an toàn.

## 1. Vì sao serializer là một phần của session contract?

Spring Session lưu session metadata và các attributes trong một repository. Repository chịu trách nhiệm lưu và khôi phục session, còn serializer/converter quyết định object trong attribute được biểu diễn thành bytes hoặc dữ liệu backend như thế nào.

Một session có thể chứa:

- Thông tin giao diện và tùy chọn người dùng.
- Tham chiếu giỏ hàng hoặc trạng thái quy trình nhiều bước.
- Principal và SecurityContext do Spring Security quản lý.
- Các attribute do ứng dụng hoặc thư viện thêm vào.

Khi node A ghi session, node B phải hiểu được định dạng và kiểu object mà A đã lưu. Việc hai node cùng dùng một Redis namespace hoặc cùng bảng JDBC chỉ bảo đảm chúng nhìn thấy cùng dữ liệu; nó không bảo đảm chúng deserialize được cùng dữ liệu.

Các thành phần phải tương thích:

1. Repository implementation và key/table layout.
2. Serializer hoặc ConversionService được cấu hình.
3. Class name, package, field, type metadata và DTO contract.
4. Phiên bản thư viện/framework có object được lưu trong session.
5. Quy tắc mặc định cho field mới, field thiếu, enum mới và null.
6. Chính sách xử lý payload cũ, payload lỗi và session hết hạn.

Không thay serializer hoặc cấu trúc DTO một cách độc lập ở một node trong khi node khác vẫn đọc cùng session store, trừ khi đã kiểm thử khả năng tương thích hai chiều.

## 2. Phân biệt repository với serializer

Repository quản lý vòng đời session: tạo, tìm, lưu, xóa và expiration. Serializer quản lý cách attributes được mã hóa/giải mã. Hai khái niệm có liên quan nhưng là hai lớp khác nhau.

| Thành phần | Trách nhiệm | Ví dụ thay đổi gây lỗi |
| --- | --- | --- |
| Session ID resolver | Đọc/ghi session ID qua cookie hoặc header | Cookie name/path khác làm client không gửi đúng ID |
| Session repository | Lưu và khôi phục metadata/attributes | Hai node dùng namespace hoặc table khác |
| Serializer/converter | Chuyển attribute thành bytes và ngược lại | Java serialization UID khác, JSON type metadata khác |
| DTO contract | Định nghĩa dữ liệu ứng dụng lưu trong session | Đổi tên field, package, enum hoặc kiểu dữ liệu |
| Framework security types | Lưu Authentication/SecurityContext | Hai phiên bản class không deserialize tương thích |

Khi test thất bại, cần xác định lỗi ở lớp nào. Không quy mọi lỗi khôi phục session cho serializer: cookie không đến, namespace sai hoặc record hết hạn cũng có thể làm node mới không tìm thấy session.

## 3. Java native serialization và các ràng buộc tương thích

Một số cấu hình Spring Session Redis sử dụng Java serialization làm mặc định cho session attributes. Cần kiểm tra serializer thực tế trong phiên bản Spring Session/Spring Boot của ứng dụng, vì cấu hình có thể đã được tùy chỉnh. Với Java serialization, class thường cần triển khai Serializable và có thể khai báo serialVersionUID ổn định.

Ví dụ DTO:

~~~java
package com.example.session.contract;

import java.io.Serializable;

public final class PreferencesV1 implements Serializable {

    private static final long serialVersionUID = 1L;

    private final String theme;
    private final String locale;

    public PreferencesV1(String theme, String locale) {
        this.theme = theme;
        this.locale = locale;
    }

    public String getTheme() {
        return theme;
    }

    public String getLocale() {
        return locale;
    }
}
~~~

Khi deserialize payload Java, JVM cần tìm class tương ứng và kiểm tra serialization metadata. Các lỗi hay gặp:

- ClassNotFoundException: node đọc không có class mà payload tham chiếu.
- InvalidClassException: serialVersionUID không tương thích.
- ClassCastException: code kỳ vọng kiểu khác với kiểu object đã khôi phục.
- Lỗi trong readObject/readResolve hoặc object graph có class phụ không còn tương thích.

Việc thêm field thường có thể tương thích theo quy tắc Java serialization nếu giữ UID và field mới có giá trị mặc định chấp nhận được. Tuy nhiên, đổi kiểu field, thay đổi hierarchy, đổi UID hoặc đổi semantics có thể làm payload cũ không đọc được hoặc tạo object thiếu dữ liệu. Đổi tên package/class thường làm reader không tìm được class.

Không dựa vào việc compiler tự tính serialVersionUID. Thay đổi cấu trúc class có thể làm UID tự sinh đổi. Nếu buộc dùng Java serialization, khai báo UID tường minh, giữ class tương thích trong thời gian session cũ còn tồn tại và kiểm thử payload được ghi bởi artifact cũ.

## 4. JSON serialization cũng cần versioning

JSON dễ quan sát hơn binary serialization nhưng không tự động tương thích ngược. Các thay đổi có thể phá reader cũ:

- Đổi tên property hoặc thay kiểu dữ liệu.
- Chuyển một field từ scalar sang object hoặc ngược lại.
- Thêm field bắt buộc mà reader cũ không biết.
- Xóa enum constant hoặc đổi tên enum.
- Thay format ngày giờ, timezone hoặc precision của số.
- Đổi type discriminator hoặc class metadata.
- Thay chính sách null, missing field và default value.

Ví dụ JSON contract:

~~~json
{
  "schemaVersion": 1,
  "theme": "DARK",
  "locale": "vi",
  "compactMode": true
}
~~~

Một field mới có thể được thêm theo hướng tương thích nếu reader cũ bỏ qua field không biết và writer mới vẫn cung cấp các field cũ theo định dạng cũ. Ngược lại, nếu reader mới yêu cầu field mới nhưng session cũ chưa có, reader mới phải có default hoặc migration khi đọc.

Khi dùng Jackson, cần kiểm tra ObjectMapper, naming strategy, module, date/time configuration, enum handling và type metadata giống nhau ở các node. Tránh bật polymorphic default typing toàn cục cho object tùy ý; type metadata không giới hạn có thể mở rộng bề mặt deserialization gadget. Ưu tiên DTO rõ ràng, kiểu dữ liệu cụ thể và allowlist các type được phép.

## 5. Đừng lưu object nội bộ của ứng dụng vào session

Session attributes tồn tại qua nhiều lần deploy. Các object sau thường có độ gắn kết cao với phiên bản ứng dụng:

- Entity ORM có proxy/lazy relationship.
- Spring Data projection hoặc Hibernate proxy.
- Request, response, servlet object, stream hoặc connection.
- Object framework nội bộ và implementation class không phải API ổn định.
- Lambda, anonymous class hoặc class được tạo tự động.
- Object chứa graph lớn, tham chiếu vòng hoặc resource không thể serialize.

Thay vào đó, định nghĩa DTO contract nhỏ trong package hoặc module dùng chung. DTO nên có kiểu dữ liệu đơn giản, field có ý nghĩa ổn định và version rõ ràng. Lưu identifier thay vì lưu toàn bộ entity nếu có thể tải dữ liệu từ service/database.

Ví dụ:

~~~java
package com.example.session.contract;

import java.io.Serializable;

public record UserSessionPreferences(
        int schemaVersion,
        String theme,
        String locale,
        boolean compactMode
) implements Serializable {
    private static final long serialVersionUID = 1L;
}
~~~

Record này minh họa một contract nhỏ. Nếu serializer dùng Java serialization, kiểm tra cách record được hỗ trợ trong runtime Java đang triển khai. Nếu serializer dùng JSON, kiểm tra constructor/creator và naming policy. Không giả định một DTO tự tương thích chỉ vì nó implements Serializable.

## 6. Tổ chức session attributes có namespace và version

Tên attribute cũng là một phần contract. Tránh key chung chung như user, preferences hoặc cart nếu nhiều module/ứng dụng cùng ghi session.

Ví dụ:

~~~java
static final String PREFERENCES_V1 =
        "com.example.portal.preferences.v1";
~~~

Key có namespace giúp giảm va chạm; suffix version cho phép ứng dụng nhận biết format. Khi chuyển sang V2, có thể đọc cả V1 và V2 trong giai đoạn chuyển tiếp:

~~~java
Object value = session.getAttribute(PREFERENCES_V2);
if (value == null) {
    value = session.getAttribute(PREFERENCES_V1);
}
~~~

Đây chỉ là bước chọn key. Phải kiểm tra type, schemaVersion và dữ liệu sau khi lấy; không cast trực tiếp một object không tin cậy. Nếu V1 được đọc thành công, có thể chuyển đổi sang model nội bộ hiện tại và ghi V2 theo chiến lược đã chọn.

Không xóa key V1 ngay khi node mới được triển khai. Node cũ có thể vẫn cần đọc nó, và session cũ có thể tồn tại đến hết TTL.

## 7. Thiết kế chuyển đổi V1 sang V2

Giả sử V1 lưu theme và locale:

~~~json
{
  "schemaVersion": 1,
  "theme": "DARK",
  "locale": "vi"
}
~~~

V2 bổ sung compactMode và timeZone:

~~~json
{
  "schemaVersion": 2,
  "theme": "DARK",
  "locale": "vi",
  "compactMode": true,
  "timeZone": "Asia/Ho_Chi_Minh"
}
~~~

Reader V2 cần đọc V1 và gán default có chủ đích cho field mới. Reader V1 không biết compactMode/timeZone; nếu V2 writer ghi payload mà V1 serializer không bỏ qua được field mới, request quay về node V1 sẽ thất bại. Do đó, chỉ thêm field vào JSON chưa chắc an toàn nếu reader cũ có schema strict hoặc type metadata thay đổi.

Một cách triển khai an toàn là giữ contract payload V1 trong giai đoạn node cũ còn chạy, hoặc triển khai reader tương thích V1/V2 trên tất cả node trước khi cho phép writer tạo V2. Nếu không thể làm reader cũ hiểu V2, trì hoãn ghi V2 cho tới khi không còn node cũ nhận traffic.

## 8. Compatibility matrix bắt buộc

Với hai artifact ứng dụng A (cũ) và B (mới), ít nhất phải kiểm tra:

| Writer | Reader | Mục tiêu | Kết quả mong đợi |
| --- | --- | --- | --- |
| A | A | Baseline cũ | Đọc payload cũ đúng |
| A | B | Forward compatibility | Node mới đọc session đang tồn tại |
| B | B | Baseline mới | Đọc payload mới đúng |
| B | A | Backward compatibility | Node cũ đọc được trong giai đoạn rolling nếu còn nhận traffic |

Hai phép thử A→B và B→A quan trọng nhất khi hai phiên bản cùng chạy. Nếu B→A không hỗ trợ, phải có chiến lược deploy bảo đảm node A không đọc payload B đã ghi.

Thêm các trường hợp:

- Payload không có field mới.
- Payload có field lạ.
- Field có giá trị null.
- Enum value mới hoặc không còn được hỗ trợ.
- Payload từ session có SecurityContext.
- Session được tạo trước lần deploy gần nhất.
- Session có attributes do module khác ghi.
- Payload lỗi/cắt cụt hoặc type metadata không hợp lệ.

## 9. Kiểm thử bằng hai artifact thật

Không nên chỉ tạo hai class trong cùng source tree rồi giả lập tên phiên bản bằng hai test method. Classpath test có thể chỉ nạp một định nghĩa class; khi hai phiên bản có cùng fully qualified class name, test có thể không tái hiện được khác biệt thật.

Các cách kiểm thử tốt:

1. Build artifact A từ release cũ và artifact B từ source/version mới.
2. Khởi chạy hai ứng dụng độc lập, mỗi ứng dụng dùng classpath riêng.
3. Cho cả hai trỏ tới cùng Redis test instance và cùng namespace.
4. Tạo session qua A, giữ cookie/session ID trong test harness.
5. Gửi request qua B với cùng ID và xác minh attribute.
6. Tạo hoặc cập nhật session qua B.
7. Gửi lại request qua A và xác minh khả năng deserialize.
8. Lặp lại với JDBC bằng cùng database/schema/table.

Nếu không thể khởi chạy hai ứng dụng cùng lúc, có thể dùng fixture payload được tạo bởi artifact A rồi đọc bằng B, và ngược lại. Fixture cần được tạo từ DTO không nhạy cảm, lưu cùng test metadata về version/serializer; không lấy session production hoặc cookie người dùng làm fixture.

## 10. Kiểm thử qua Spring Session repository và HTTP filter

Nên có hai lớp test:

**Repository/serializer contract test**

- Ghi một session có đầy đủ attributes.
- Đọc lại qua serializer/repository của phiên bản khác.
- So sánh type, field, null/default và semantics.
- Xác minh session hết hạn vẫn không được khôi phục.
- Xác minh lỗi deserialize không bị biến thành session miss một cách âm thầm.

**HTTP integration test**

- Khởi chạy node A và node B.
- Gửi request tạo session tới A.
- Lấy cookie trong bộ nhớ test, không ghi ra log.
- Gửi request có cookie tới B.
- B đọc được cùng attribute và trả kết quả đúng.
- B cập nhật attribute.
- A đọc lại session theo policy tương thích.
- Kiểm tra logout và session ID rotation.

Test HTTP quan trọng vì nó xác minh resolver, filter, repository, serializer và response cookie hoạt động cùng nhau. Chỉ gọi ObjectMapper trực tiếp không chứng minh Spring Session đang dùng ObjectMapper đó.

## 11. Kiểm thử Redis serializer

Với Spring Session Redis, serializer mặc định và cách cấu hình serializer phụ thuộc phiên bản. Nếu ứng dụng khai báo bean như springSessionDefaultRedisSerializer, mọi node dùng chung namespace cần có cấu hình tương thích. Không chỉ so sánh tên bean; hãy xác minh payload được ghi và đọc thực tế.

Test Redis nên:

1. Dùng Redis riêng qua Testcontainers hoặc service test cô lập.
2. Dùng namespace dành riêng cho test.
3. Khởi chạy artifact A và B với cùng Redis endpoint/namespace.
4. Ghi session qua A, đọc qua B.
5. Ghi session qua B, đọc qua A.
6. Kiểm tra TTL, invalidation và key phụ theo repository implementation.
7. Xác minh serializer config không khác nhau ngoài ý muốn giữa hai node.

Không hard-code key layout nội bộ của Spring Session vào business code. Nếu test cần xem payload hoặc key để chẩn đoán, giữ việc đó trong integration test gắn với đúng phiên bản repository và không dùng nó làm contract công khai.

## 12. Kiểm thử JDBC serializer/converter

Spring Session JDBC dùng schema và cơ chế chuyển đổi attribute riêng của repository. Tùy phiên bản và cấu hình, việc serialize có thể đi qua ConversionService hoặc converter được cung cấp. Không mặc định serializer Redis và JDBC có cùng format chỉ vì cùng lưu một DTO.

Test JDBC cần:

- Dùng đúng database engine/version gần production.
- Tạo schema bằng migration tương ứng.
- Khởi chạy artifact A/B với cùng database/schema/table.
- Ghi attribute ở A, đọc ở B; sau đó đảo chiều.
- Xác minh column type có thể chứa payload, kích thước và encoding phù hợp.
- Kiểm tra quyền runtime và cleanup không làm mất dữ liệu đang test.

Nếu Redis và JDBC cùng được hỗ trợ trong hệ thống, chạy contract suite trên cả hai backend. Không chia sẻ cùng session giữa một Redis node và một JDBC node nếu chưa có cơ chế đồng bộ/chuyển đổi rõ ràng; hai backend riêng không tự động là một repository chung.

## 13. Serializer tùy chỉnh cho Redis

Spring Session Redis cho phép tùy chỉnh serializer theo cơ chế được phiên bản hỗ trợ, thường thông qua bean có tên springSessionDefaultRedisSerializer. Khi chọn JSON serializer, cần quyết định rõ:

- Type metadata có cần thiết không và được biểu diễn ra sao.
- Các type nào được phép deserialize.
- DTO contract nào là ổn định.
- Unknown property, missing property và enum lạ được xử lý thế nào.
- Cách giữ tương thích với payload đang tồn tại.

Ví dụ cấu trúc bean minh họa, trong đó factory serializer là thành phần ứng dụng định nghĩa theo allowlist type:

~~~java
@Bean
RedisSerializer<Object> springSessionDefaultRedisSerializer() {
    return sessionAttributeSerializer();
}
~~~

sessionAttributeSerializer() ở đây là factory do dự án triển khai để cấu hình ObjectMapper, type allowlist và DTO contract. Không dùng đoạn code này như implementation hoàn chỉnh. Cách tạo serializer cụ thể phụ thuộc Spring Data Redis/Spring Session version và có thể cần xử lý cả SecurityContext cùng các attribute framework.

Không bật default typing cho mọi class trên classpath chỉ để deserialize Object. Nếu dùng polymorphic type metadata, giới hạn type được phép bằng allowlist chặt và kiểm thử payload không được phép. Tốt hơn, tránh lưu nhiều kiểu object tùy ý; lưu DTO cụ thể hoặc envelope có discriminator được kiểm soát.

## 14. SecurityContext và Spring Security

Session của ứng dụng có thể chứa SecurityContext, Authentication, principal và các object do ứng dụng tự định nghĩa. Đây là phần có rủi ro tương thích cao vì class có thể phụ thuộc phiên bản Spring Security, custom UserDetails hoặc authority implementation.

Khi nâng phiên bản ứng dụng, kiểm thử riêng:

- Authentication do phiên bản cũ tạo có được phiên bản mới đọc không.
- Custom principal class có còn cùng package/type contract không.
- GrantedAuthority và custom attributes có serializer tương thích không.
- Node cũ có đọc được SecurityContext do node mới ghi không.
- Session fixation protection có rotate ID đúng và client nhận ID mới không.
- Logout/invalidation từ một node có tác động đúng tới node khác không.

Không bỏ qua SecurityContext trong test chỉ vì DTO tùy chọn người dùng đã tương thích. Một session có thể chứa nhiều attribute; chỉ một attribute không deserialize được cũng có thể làm việc khôi phục session thất bại.

Nếu chia sẻ session giữa hai ứng dụng có security stack hoặc trust boundary khác nhau, hãy cân nhắc SSO bằng OpenID Connect thay vì serialize SecurityContext dùng chung. Mỗi ứng dụng có thể tạo security context riêng từ token đã xác minh.

## 15. Rolling deployment theo chiến lược expand/contract

Một chiến lược an toàn thường có các pha:

**Pha 1 — Mở rộng reader**

Triển khai phiên bản có thể đọc format cũ và mới, nhưng vẫn ghi format cũ. Trong giai đoạn này, tất cả node đang chạy nên hiểu payload hiện tại.

**Pha 2 — Chờ hết node cũ**

Xác minh không còn instance cũ nhận traffic. Kiểm tra worker, scheduled job, consumer hoặc service phụ cũng có đọc session store hay không.

**Pha 3 — Chuyển writer**

Cho phép phiên bản mới ghi format mới. Nếu vẫn cần rollback về phiên bản cũ, chỉ làm khi reader cũ có thể hiểu payload mới hoặc đã có kế hoạch rollback không dùng lại session cũ.

**Pha 4 — Chuyển đổi dữ liệu cũ**

Có thể migrate khi đọc/ghi hoặc chạy job có kiểm soát. Không cần rewrite toàn bộ session nếu TTL ngắn và dữ liệu cũ tự hết hạn, nhưng phải bảo đảm reader mới hiểu chúng đến hết vòng đời.

**Pha 5 — Thu hẹp reader**

Chỉ bỏ hỗ trợ format cũ sau khi session cũ đã hết TTL cộng khoảng grace, không còn writer cũ và không còn payload cũ cần đọc.

~~~mermaid
flowchart LR
    A[Deploy reader V1+V2, writer V1] --> B[Remove all old nodes]
    B --> C[Enable writer V2]
    C --> D[Wait or migrate V1 sessions]
    D --> E[Remove V1 reader after TTL + grace]
~~~

Nếu node cũ không thể đọc format mới và không thể trì hoãn writer mới, cần tách namespace/repository theo version hoặc chấp nhận invalidate session có kế hoạch. Không để hai phiên bản ghi hai format không tương thích vào cùng namespace.

## 16. Thời gian sống của session quyết định thời gian giữ tương thích

Session có thể tồn tại lâu hơn thời gian rolling deployment. Nếu timeout là 12 giờ, payload V1 có thể còn được gửi tới node mới trong nhiều giờ sau khi deploy hoàn tất. Nếu session không có absolute lifetime, người dùng hoạt động liên tục có thể kéo dài idle lifetime.

Khi bỏ hỗ trợ format cũ, cần tính:

- Idle timeout tối đa.
- Absolute lifetime nếu ứng dụng có áp dụng.
- Cookie/session retention phía client.
- Cleanup lag của Redis/JDBC.
- Replica lag hoặc backup/restore có thể đưa payload cũ trở lại hay không.
- Session của user đang hoạt động liên tục có thể được refresh hay không.

Chỉ dựa vào thời gian deploy xong để xóa code đọc V1 là không đủ. Có thể theo dõi số session V1 được đọc; chỉ bỏ reader cũ khi số lượng đã bằng 0 trong một khoảng dài hơn TTL và grace đã thiết kế.

## 17. Xử lý deserialize failure an toàn

Nếu payload không đọc được, không trả một session rỗng rồi tiếp tục như người dùng chưa đăng nhập mà không ghi nhận lỗi. Với session có SecurityContext, việc bỏ qua lỗi có thể làm sai trạng thái xác thực.

Chính sách cần xác định:

- Phân biệt record không tồn tại/hết hạn với payload deserialize failure.
- Không biến lỗi datastore hoặc serializer thành kết quả session miss âm thầm.
- Không dùng object một phần hoặc default authentication khi deserialize thất bại.
- Ghi metric/log theo exception class, application version và serializer version; không log payload hoặc session ID.
- Cân nhắc invalidate riêng session hỏng hoặc yêu cầu đăng nhập lại theo policy.
- Giữ nguyên bằng chứng cần thiết để điều tra, nhưng không lưu credential trong log.

Không xóa toàn bộ Redis namespace hoặc bảng session chỉ vì một số payload lỗi. Xác định đúng session/attribute bị ảnh hưởng và phạm vi lỗi trước khi cleanup.

## 18. Bảng kiểm thử tương thích chi tiết

| Dữ liệu/đường đi | Phiên bản cũ ghi | Phiên bản mới đọc | Phiên bản mới ghi | Phiên bản cũ đọc |
| --- | --- | --- | --- | --- |
| Preferences DTO V1 | Payload baseline | Đọc và chuyển đổi được | — | — |
| Preferences DTO V2 | — | — | Payload mới | Đọc được nếu backward-compatible |
| Field mới optional | Không có field | Default đúng | Có field | Bỏ qua an toàn hoặc đọc theo contract |
| Enum mới | Enum cũ | Mapping/default có chủ đích | Giá trị mới | Không lỗi nếu node cũ còn chạy |
| Date/time | Format cũ | Đọc đúng instant/zone | Format mới | Đọc đúng nếu còn hỗ trợ |
| SecurityContext | Framework cũ | Khôi phục đúng principal/authority | Framework mới | Khôi phục được khi cần rollback |
| Attribute type lạ | Payload chứa type không allowlist | Từ chối an toàn | — | — |
| Payload hỏng | — | Lỗi được phân loại | — | Lỗi được phân loại |

Ngoài payload chính, kiểm tra:

- Session không có attribute tùy chọn.
- Session có attribute null.
- Session chứa attribute cũ do phiên bản trước nhiều release ghi.
- Session hết hạn trong lúc rolling deployment.
- Logout trong khi hai phiên bản cùng chạy.
- Hai request đồng thời ghi attribute ở hai phiên bản khác nhau.
- Session ID rotation sau authentication.

## 19. Ví dụ test fixture hai chiều

Có thể lưu fixture JSON hoặc serialized bytes được tạo bởi build cũ trong test resources. Fixture chỉ chứa dữ liệu giả và có metadata rõ ràng:

~~~text
src/test/resources/session-fixtures/
    app-v1-preferences.json
    app-v1-session.bin
    fixture-manifest.txt
~~~

Manifest nên ghi:

- Artifact/version tạo fixture.
- Serializer và cấu hình serializer.
- Schema version của DTO.
- Các attribute có trong fixture.
- Java/Spring/Spring Security version nếu ảnh hưởng serialization.

Test ở build mới đọc fixture V1 để kiểm tra forward compatibility. Build cũ được kiểm thử với fixture V2 trong pipeline compatibility riêng để kiểm tra backward compatibility. Không đưa session ID, cookie, username thật hoặc SecurityContext production vào fixture.

Fixture phải được tạo bằng artifact thực tế, không tự viết bytes giả hoặc JSON tự đoán. Khi serializer thay đổi, tạo fixture mới và giữ fixture cũ cho tới khi bỏ hỗ trợ phiên bản đó.

## 20. Test schema evolution cho DTO

Một contract test có thể xác minh các quy tắc:

~~~java
@Test
void v1PayloadMapsToCurrentPreferences() {
    UserPreferences current = compatibilityReader.read(v1Fixture);

    assertThat(current.theme()).isEqualTo("DARK");
    assertThat(current.locale()).isEqualTo("vi");
    assertThat(current.compactMode()).isFalse();
}
~~~

Test trên minh họa ý tưởng; compatibilityReader và v1Fixture là thành phần test do dự án cung cấp. Test cần chạy qua serializer thực tế mà Spring Session repository sử dụng hoặc qua adapter đúng cấu hình đó. Nếu chỉ dùng ObjectMapper khác bean production, test có thể pass nhưng ứng dụng vẫn lỗi.

Thêm test ngược:

~~~java
@Test
void v2PayloadCanBeReadByPreviousRelease() {
    byte[] v2Payload = currentSerializer.serialize(v2Preferences);

    PreviousReleaseReader oldReader = previousReleaseReader();
    UserPreferencesV1 oldValue = oldReader.deserialize(v2Payload);

    assertThat(oldValue.theme()).isEqualTo("DARK");
}
~~~

Test này thường cần chạy previous release reader trong process/artifact riêng vì class cùng tên không thể được thay thế an toàn trong một classloader thông thường. Có thể dùng process/container riêng hoặc pipeline chạy hai build độc lập.

## 21. Test hai node cùng Redis namespace

Một integration scenario:

1. Tạo Redis test instance cô lập.
2. Khởi chạy app V1 trên port riêng với namespace cố định của test.
3. Khởi chạy app V2 trên port khác với cùng namespace và serializer contract.
4. Gọi endpoint tạo session qua V1; nhận cookie trong bộ nhớ test.
5. Gửi cookie tới V2; xác minh đọc được attribute V1.
6. Cập nhật attribute qua V2.
7. Gửi cookie tới V1; xác minh V1 đọc được payload V2 nếu rolling policy yêu cầu.
8. Gọi logout ở V2; xác minh V1 không khôi phục được session cũ.
9. Thu thập metrics serializer failure của cả hai node.

Đừng bật sticky routing trong phép thử nếu muốn chứng minh hai node cùng dùng repository. Gọi trực tiếp từng port hoặc cấu hình load balancer test có thể chuyển request xác định.

## 22. Test hai phiên bản với JDBC

Lặp lại scenario trên với một database test cùng engine production. Cả hai artifact phải dùng cùng schema/table và migration state. Kiểm tra:

- Payload attribute cũ được đọc bởi phiên bản mới.
- Payload mới được đọc bởi phiên bản cũ khi còn node cũ.
- Schema migration tương thích trong giai đoạn rolling.
- Runtime account của cả hai phiên bản có quyền phù hợp.
- Không có thay đổi column type làm payload cũ bị cắt hoặc không đọc được.
- Transaction/update semantics không tạo lost update khi hai node cùng ghi.

Không dùng H2 làm bằng chứng duy nhất cho tương thích PostgreSQL/MySQL/SQL Server. Khác biệt dialect, BLOB type, transaction isolation và locking có thể che lỗi.

## 23. Thay đổi serializer là một migration dữ liệu

Nếu đổi từ Java serialization sang JSON hoặc thay ObjectMapper/type metadata, dữ liệu cũ vẫn nằm trong repository. Deploy serializer mới có thể khiến node mới không đọc được session cũ dù code DTO không đổi.

Quy trình:

1. Xác định serializer hiện tại từ bean/config/runtime, không suy đoán từ dependency.
2. Tạo fixture bằng serializer cũ.
3. Thử serializer mới đọc fixture cũ.
4. Nếu không đọc được, xây dựng dual-reader hoặc migration.
5. Chỉ bật writer mới khi mọi reader đang hoạt động hiểu format mới.
6. Giữ reader cũ ít nhất bằng session lifetime tối đa cộng grace.
7. Sau khi không còn payload cũ, bỏ serializer cũ trong release riêng.

Không đổi serializer, DTO schema và repository layout cùng một lần nếu có thể tránh. Chia thay đổi thành các bước giúp xác định nguyên nhân khi rollout thất bại.

## 24. Observability cho tương thích serializer

Theo dõi:

- Số lần serialize/deserialize thành công và thất bại.
- Exception class như InvalidClassException, ClassNotFoundException, JsonMappingException hoặc lỗi converter.
- Schema version của DTO (không dùng session ID làm label).
- Application version/node ID và serializer version.
- Số session V1 còn được đọc sau deploy.
- Tỷ lệ request cần fallback từ V2 sang V1.
- Tỷ lệ session bị yêu cầu đăng nhập lại do payload lỗi.

Không ghi session ID, cookie, raw serialized bytes, access token hoặc SecurityContext vào log. Nếu cần trace, dùng request correlation ID và mã phiên bản payload không nhạy cảm.

Alert nên phân biệt lỗi tương thích tăng đột biến với session miss bình thường. Session miss có thể do cookie cũ/hết hạn; deserialize failure cho thấy reader không hiểu payload hoặc dữ liệu hỏng.

## 25. Checklist trước rolling deployment

- [ ] Đã xác định serializer thực tế cho Redis/JDBC và cấu hình từng node.
- [ ] Session attributes dùng DTO contract nhỏ, ổn định, không lưu entity/proxy/framework internals tùy tiện.
- [ ] Có version/schemaVersion và namespace key cho attributes cần evolution.
- [ ] Có fixture được tạo bởi artifact cũ.
- [ ] Test A→B và B→A đã chạy với artifact thật.
- [ ] Test SecurityContext/custom principal nếu session có Spring Security.
- [ ] Test unknown field, missing field, null, enum mới và type metadata.
- [ ] Các node dùng cùng repository namespace/schema và serializer-compatible config.
- [ ] Reader mới hỗ trợ payload cũ trước khi writer mới phát payload mới.
- [ ] Không còn node cũ trước khi bật writer không tương thích.
- [ ] Có kế hoạch giữ reader cũ qua TTL + grace hoặc migrate/invalidate có kiểm soát.
- [ ] Có metrics/alert cho deserialize failure và session version.
- [ ] Không log session credential hoặc payload nhạy cảm.

## 26. Kết luận

Tương thích serializer giữa hai phiên bản ứng dụng là điều kiện để Spring Session hoạt động ổn định trong rolling deployment. Cùng repository không đủ: hai phiên bản phải hiểu cùng định dạng attributes, class/type metadata, DTO contract và các object framework được lưu trong session. Kiểm thử quan trọng nhất là payload do bản cũ ghi được bản mới đọc và payload do bản mới ghi vẫn được bản cũ đọc trong thời gian hai phiên bản cùng nhận traffic.

Thiết kế DTO có version, giữ reader tương thích trước khi chuyển writer, kiểm thử hai artifact thật trên Redis/JDBC test backend và chỉ bỏ format cũ sau khi session cũ hết vòng đời. Nếu không thể duy trì tương thích hai chiều, cần tách namespace/repository theo version hoặc chủ động yêu cầu đăng nhập lại với kế hoạch rõ ràng. Mọi lỗi deserialize phải được quan sát và xử lý riêng, không biến thành session miss âm thầm hoặc xóa toàn bộ session store.
