# SessionRepositoryCustomizer và thay đổi cấu hình repository

Spring Session cung cấp SessionRepository để lưu và tải phiên thông qua một kho dữ liệu như Redis hoặc JDBC. Khi dùng Spring Boot, repository thường được tạo tự động từ dependency và cấu hình ứng dụng. Với trường hợp JDBC, Spring Boot có thể tạo JdbcIndexedSessionRepository, kết nối repository đó với DataSource và đưa nó vào SessionRepositoryFilter để ứng dụng Servlet tiếp tục sử dụng HttpSession.

Trong nhiều ứng dụng, các thuộc tính cấu hình có sẵn đã đủ. Khi cần điều chỉnh một chi tiết của repository bằng Java API, SessionRepositoryCustomizer là điểm mở rộng dành cho việc đó. Nó cho phép tùy chỉnh repository do Spring Boot tự cấu hình trước khi repository được sử dụng để xử lý session. Cách này hữu ích khi cần thay đổi một thiết lập chuyên biệt mà cấu hình ngoài chưa đáp ứng, đồng thời vẫn giữ cơ chế tự cấu hình của Spring Boot.

## 1. SessionRepository và vị trí của repository trong ứng dụng

SessionRepository là abstraction chịu trách nhiệm tạo, tìm, lưu và xóa session. Ứng dụng Servlet thường không gọi repository trực tiếp; SessionRepositoryFilter tích hợp repository với API HttpSession.

Với Spring Session JDBC, JdbcIndexedSessionRepository lưu thông tin phiên và thuộc tính phiên trong các bảng quan hệ. Các instance Spring có thể cùng truy cập database để sử dụng chung session. Repository cần một DataSource phù hợp và schema tương thích với phiên bản Spring Session.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["application.yml / cấu hình môi trường"] --> B["Spring Boot auto-configuration"]
    C["DataSource và JdbcOperations"] --> B
    B --> D["JdbcIndexedSessionRepository"]
    E["SessionRepositoryCustomizer<JdbcIndexedSessionRepository>"] --> D
    D --> F["SessionRepositoryFilter"]
    F --> G["Controller / Service dùng HttpSession"]
    D --> H[("Database<br/>SPRING_SESSION và thuộc tính phiên")]
~~~

SessionRepositoryCustomizer tác động lên repository đã được tạo. Nó không thay thế DataSource, không thay đổi bộ lọc Servlet, không tự tạo schema và cũng không cấu hình cookie. Mỗi phần có trách nhiệm riêng:

- DataSource xác định kết nối, pool và thông tin truy cập database.
- Migration hoặc schema initialization quản lý cấu trúc bảng.
- SessionRepositoryCustomizer điều chỉnh hành vi hoặc thuộc tính của repository.
- SessionRepositoryFilter nối repository với HttpSession.
- CookieSerializer quyết định cách session ID được gửi đến trình duyệt.

Phân biệt các trách nhiệm này giúp tránh đưa mọi thay đổi vào một customizer duy nhất.

## 2. SessionRepositoryCustomizer là gì?

SessionRepositoryCustomizer<T> là một extension point của Spring Boot dành cho repository session. T là kiểu repository được tùy chỉnh. Khi ứng dụng dùng JDBC, kiểu cụ thể thường là JdbcIndexedSessionRepository.

Một bean customizer có thể được khai báo như sau:

~~~java
import org.springframework.boot.autoconfigure.session.SessionRepositoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.jdbc.JdbcIndexedSessionRepository;

@Configuration
class JdbcSessionRepositoryConfiguration {

    @Bean
    SessionRepositoryCustomizer<JdbcIndexedSessionRepository>
            jdbcSessionRepositoryCustomizer() {
        return repository -> {
            // Điều chỉnh repository tại đây.
        };
    }
}
~~~

Spring Boot tìm bean customizer có kiểu tương thích với repository mà auto-configuration đang tạo và gọi customize(repository) trong quá trình cấu hình repository. Sau khi tùy chỉnh, repository được sử dụng bởi cơ chế Spring Session.

Generic type rất quan trọng. Customizer cho JdbcIndexedSessionRepository chỉ có ý nghĩa khi ứng dụng thực sự dùng repository JDBC tương ứng. Nếu ứng dụng chuyển sang Redis, customizer JDBC không phải nơi cấu hình RedisIndexedSessionRepository.

Không tự tạo một repository JDBC thứ hai trong customizer. Hãy chỉnh instance được truyền vào. Tạo thêm repository có thể khiến ứng dụng có nhiều bean cạnh tranh, filter dùng nhầm instance hoặc các instance ghi session vào những nơi khác nhau.

## 3. Khi nào dùng application properties, khi nào dùng customizer?

Spring Boot đã cung cấp nhiều thuộc tính để cấu hình Spring Session JDBC. Nên dùng properties cho các giá trị tĩnh, có thể quản lý theo môi trường và không cần logic Java.

Ví dụ:

~~~yaml
spring:
  session:
    timeout: 30m
    jdbc:
      initialize-schema: never
      table-name: APP_SESSION
      cleanup-cron: "0 * * * * *"
      flush-mode: on-save
      save-mode: on-set-attribute
~~~

Các thuộc tính cụ thể có thể thay đổi theo phiên bản Spring Boot. Hãy xác nhận tên property và giá trị enum được hỗ trợ bởi phiên bản dự án.

SessionRepositoryCustomizer phù hợp khi:

- Cần gọi một API của repository không được biểu diễn bằng property chuẩn.
- Cần cài một thành phần chuyên biệt, ví dụ IndexResolver hoặc ConversionService đã được ứng dụng cấu hình.
- Cần áp dụng logic Java có điều kiện theo môi trường hoặc theo bean đã được inject.
- Cần cấu hình một chi tiết của implementation JDBC mà auto-configuration không có property tương ứng.

Nếu yêu cầu thay đổi cách lưu trữ căn bản, cách truy vấn hoặc giao thức repository, một customizer có thể không đủ. Khi đó cần xem xét triển khai SessionRepository riêng hoặc dùng một extension point chuyên biệt của implementation.

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Đặt thời hạn session mặc định | spring.session.timeout |
| Đổi tên bảng session theo cấu hình | Property spring.session.jdbc.table-name nếu phiên bản hỗ trợ |
| Đặt flush mode và save mode tĩnh | JDBC properties nếu phiên bản hỗ trợ |
| Cài IndexResolver tùy chỉnh | SessionRepositoryCustomizer |
| Cài ConversionService chuyên biệt | Customizer nếu API repository hỗ trợ |
| Đổi toàn bộ cách lưu hoặc transaction | Đánh giá repository implementation riêng |

Tránh cấu hình cùng một thuộc tính ở nhiều nơi nếu không có quy tắc rõ ràng. Khi property và customizer cùng đặt một giá trị, kết quả phụ thuộc thứ tự cấu hình của phiên bản Spring Boot. Nên chọn một nguồn cấu hình chính cho từng thuộc tính và kiểm tra repository thực tế sau khi khởi động.

## 4. Ví dụ: tùy chỉnh JdbcIndexedSessionRepository

Ví dụ sau đổi tên bảng, chọn chế độ flush và save, đồng thời đặt lịch dọn session hết hạn. Các thuộc tính này cũng có thể được cấu hình bằng Spring Boot properties ở các phiên bản hỗ trợ; customizer minh họa cách thao tác trực tiếp trên repository.

~~~java
import org.springframework.boot.autoconfigure.session.SessionRepositoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.FlushMode;
import org.springframework.session.SaveMode;
import org.springframework.session.jdbc.JdbcIndexedSessionRepository;

@Configuration
class JdbcSessionRepositoryConfiguration {

    @Bean
    SessionRepositoryCustomizer<JdbcIndexedSessionRepository>
            jdbcSessionRepositoryCustomizer() {
        return repository -> {
            repository.setTableName("APP_SESSION");
            repository.setFlushMode(FlushMode.ON_SAVE);
            repository.setSaveMode(SaveMode.ON_SET_ATTRIBUTE);
            repository.setCleanupCron("0 * * * * *");
        };
    }
}
~~~

Ý nghĩa:

- setTableName cấu hình tên bảng gốc mà repository sử dụng. Schema thực tế phải có các bảng và cột tương ứng với quy ước của Spring Session JDBC.
- FlushMode.ON_SAVE gom các thay đổi và ghi khi hoàn tất thao tác lưu session theo vòng đời request. Điều này thường giảm số lần ghi so với lưu ngay sau từng thay đổi.
- SaveMode.ON_SET_ATTRIBUTE giới hạn việc theo dõi thay đổi chủ yếu ở những thuộc tính được đặt. Lựa chọn này có thể giảm thao tác lưu, nhưng ứng dụng phải cập nhật thuộc tính qua API session đúng cách.
- setCleanupCron đặt lịch chạy tác vụ dọn session hết hạn. Cần chọn tần suất phù hợp với số lượng phiên và tải database.

Các setter và enum cần đối chiếu với phiên bản Spring Session đang dùng. Không giả định mọi phiên bản Spring Boot hoặc Spring Session đều có cùng API. Nếu một method không tồn tại ở dependency của dự án, kiểm tra API tương ứng và chọn property hoặc extension point được hỗ trợ.

## 5. Thay đổi tên bảng và schema JDBC

Spring Session JDBC mặc định sử dụng các bảng session được cung cấp trong schema của thư viện, thường gồm bảng lưu metadata session và bảng lưu thuộc tính session. Khi đổi tên bảng, schema database phải được thay đổi đồng bộ.

Ví dụ nếu repository được cấu hình dùng APP_SESSION, migration cần tạo đúng cấu trúc bảng tương ứng và bảng thuộc tính theo quy ước của phiên bản Spring Session. Không chỉ đổi tên một bảng rồi giữ nguyên bảng còn lại. Các câu lệnh SQL nội bộ của repository cần tìm đúng các bảng, khóa chính, cột và kiểu dữ liệu.

Trong production, nên quản lý schema bằng Flyway, Liquibase hoặc quy trình migration tương đương:

1. Tạo migration dựa trên schema mẫu của đúng phiên bản Spring Session.
2. Thay tên bảng và các ràng buộc theo quy ước đặt tên của tổ chức.
3. Triển khai migration trước hoặc theo thứ tự tương thích với ứng dụng.
4. Cấu hình repository trỏ đến tên bảng/schema mới.
5. Kiểm thử tạo, đọc, cập nhật, xóa và dọn session hết hạn.

Không bật schema initialization tự động ở production nếu quy trình migration đã quản lý schema. Tài khoản runtime chỉ nên có quyền cần thiết để thao tác trên các bảng session; tài khoản migration có thể cần quyền DDL riêng.

Nếu database dùng schema riêng, catalog riêng hoặc tên bảng có quy tắc đặc thù, xác nhận cách repository và phiên bản thư viện hỗ trợ cấu hình schema. Không ghép chuỗi tên schema trực tiếp từ input người dùng hoặc giá trị không được kiểm soát.

## 6. Tùy chỉnh IndexResolver

JdbcIndexedSessionRepository hỗ trợ chỉ mục để tra cứu session theo principal name. Điều này hữu ích khi cần tìm các phiên của một người dùng, ví dụ để quản lý giới hạn số phiên đăng nhập hoặc thu hồi phiên theo người dùng.

Repository sử dụng IndexResolver để xác định các giá trị chỉ mục từ session. Trong trường hợp ứng dụng lưu danh tính theo cấu trúc riêng, có thể cần resolver tùy chỉnh. Ví dụ, ứng dụng có thể lưu một thuộc tính principal đã chuẩn hóa và muốn repository lập chỉ mục theo thuộc tính đó.

Mã minh họa dưới đây cho thấy hình dạng của một resolver tùy chỉnh:

~~~java
import java.util.Collections;
import java.util.Map;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.IndexResolver;
import org.springframework.session.Session;

class ApplicationPrincipalIndexResolver implements IndexResolver<Session> {

    @Override
    public Map<String, String> resolveIndexesFor(Session session) {
        Object principal = session.getAttribute("APP_PRINCIPAL_NAME");
        if (principal == null) {
            return Collections.emptyMap();
        }

        return Map.of(
            FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
            principal.toString()
        );
    }
}
~~~

Có thể gắn resolver vào repository bằng customizer nếu phiên bản cung cấp setter tương ứng:

~~~java
@Bean
SessionRepositoryCustomizer<JdbcIndexedSessionRepository>
        principalIndexCustomizer() {
    return repository ->
        repository.setIndexResolver(new ApplicationPrincipalIndexResolver());
}
~~~

Đây là ví dụ cho trường hợp ứng dụng tự quản lý thuộc tính principal. Nếu dùng Spring Security theo cấu hình mặc định, resolver mặc định có thể đã biết cách tìm principal trong SecurityContext. Thay thế resolver mặc định mà không giữ logic đó có thể làm chức năng tìm session theo username ngừng hoạt động.

Một resolver phải trả về chỉ mục ổn định, không chứa dữ liệu bí mật và có cùng cách chuẩn hóa ở mọi instance. Không dùng email hoặc username chưa chuẩn hóa nếu hệ thống coi chữ hoa/thường hoặc alias là tương đương. Thay đổi cách lập chỉ mục có thể làm các session cũ không còn tìm thấy theo index cho đến khi được cập nhật hoặc hết hạn.

## 7. Tùy chỉnh chuyển đổi thuộc tính session

Repository JDBC phải chuyển thuộc tính session từ object Java sang dạng lưu trữ và ngược lại. Spring Session sử dụng cơ chế chuyển đổi/serialization phù hợp với phiên bản và cấu hình của repository.

Trong một số tình huống, ứng dụng cần một ConversionService chuyên biệt hoặc hỗ trợ kiểu dữ liệu riêng. Có thể cấu hình thành phần chuyển đổi rồi gắn vào repository bằng API mà phiên bản đang dùng cung cấp. Trước khi làm vậy, cần xác định:

- Kiểu dữ liệu nào thực sự được lưu trong session.
- Serializer hoặc converter hiện tại đang xử lý kiểu đó ra sao.
- Dữ liệu đã ghi trước đó có đọc được bằng converter mới không.
- Mọi instance đang chạy có cùng cấu hình chuyển đổi không.
- Dữ liệu có tương thích qua rolling deployment không.

Không thay converter trong khi dữ liệu session cũ còn tồn tại mà chưa có kế hoạch chuyển đổi. Ví dụ, nếu converter cũ ghi một kiểu thành chuỗi và converter mới mong đợi JSON object, repository không thể tự suy ra cách chuyển đổi. Có thể cần chờ session cũ hết hạn, dùng namespace mới hoặc viết migration đọc định dạng cũ và ghi định dạng mới.

Ưu tiên lưu DTO nhỏ, có cấu trúc ổn định và dễ chuyển đổi. Tránh lưu đối tượng framework, entity ORM, connection hoặc object graph lớn vào session.

## 8. FlushMode và SaveMode ảnh hưởng đến hiệu năng như thế nào?

FlushMode quyết định thời điểm thay đổi session được ghi xuống repository. SaveMode quyết định mức độ thuộc tính session được lưu. Hai thiết lập này ảnh hưởng đến số câu lệnh SQL, lượng dữ liệu ghi và cách thay đổi được quan sát.

| Thiết lập | Đặc điểm | Khi cân nhắc |
| --- | --- | --- |
| FlushMode.ON_SAVE | Ghi thay đổi khi session được lưu ở cuối vòng xử lý | Phù hợp với phần lớn request thông thường |
| FlushMode.IMMEDIATE | Đẩy thay đổi xuống repository sớm hơn | Khi cần thấy thay đổi ngay, chấp nhận thêm thao tác I/O |
| SaveMode.ON_SET_ATTRIBUTE | Lưu thuộc tính được đặt qua API session | Khi ứng dụng cập nhật thuộc tính tường minh |
| SaveMode.ON_GET_ATTRIBUTE | Theo dõi cả thuộc tính được truy cập theo chính sách hỗ trợ | Khi cần lưu những thay đổi có thể phát sinh từ việc đọc |
| SaveMode.ALWAYS | Lưu rộng hơn các thuộc tính session | Khi ưu tiên độ đơn giản và chấp nhận ghi nhiều hơn |

Tên và hành vi chính xác của các enum phụ thuộc phiên bản. Kiểm tra tài liệu API và kiểm thử với repository thật trước khi thay đổi. Không chọn IMMEDIATE hoặc ALWAYS chỉ vì chúng có vẻ an toàn hơn; chúng có thể làm tăng số lần ghi và tải database.

Với ON_SET_ATTRIBUTE, tránh sửa trực tiếp một object mutable lấy từ session mà không gọi setAttribute lại. Ví dụ:

~~~java
CartState cart = (CartState) session.getAttribute("cart");
cart.add(product);
session.setAttribute("cart", cart);
~~~

Việc gọi setAttribute sau khi thay đổi giúp repository nhận biết thuộc tính cần lưu theo chế độ save tương ứng. Nếu chỉ sửa object tại chỗ và không đặt lại thuộc tính, thay đổi có thể không được lưu như mong đợi tùy SaveMode.

## 9. Tùy chỉnh lịch dọn session hết hạn

Session hết hạn theo thời gian không hoạt động có thể không bị xóa vật lý khỏi bảng ngay tại thời điểm timeout. JDBC repository thường có tác vụ dọn các bản ghi hết hạn theo lịch. Lịch dọn ảnh hưởng đến kích thước bảng và chi phí truy vấn.

Khi điều chỉnh cleanup cron:

- Chọn tần suất đủ để dữ liệu hết hạn không tích tụ quá lâu.
- Tránh chạy quá dày nếu bảng lớn và database đang chịu tải.
- Theo dõi thời gian thực thi, số dòng bị xóa và lock contention.
- Kiểm tra index trên các cột được dùng để tìm bản ghi hết hạn theo schema của phiên bản.
- Đảm bảo nhiều instance không tạo ra lịch dọn cạnh tranh ngoài ý muốn.

Nếu mọi instance đều khởi tạo scheduler, cần hiểu cơ chế điều phối của phiên bản Spring Session đang dùng. Không tự tạo thêm job dọn cùng bảng nếu repository đã quản lý cleanup, trừ khi đã thiết kế rõ việc phân phối công việc và chống chạy trùng.

## 10. Nhiều customizer và thứ tự áp dụng

Ứng dụng có thể khai báo nhiều SessionRepositoryCustomizer cùng kiểu repository. Nếu nhiều customizer sửa cùng một thuộc tính, thứ tự gọi có thể ảnh hưởng giá trị cuối cùng.

Ví dụ không nên có hai bean độc lập cùng đặt tableName thành hai giá trị khác nhau. Điều đó làm cấu hình khó dự đoán và dễ gây lỗi khi triển khai theo môi trường.

Nếu thật sự cần nhiều customizer:

- Phân chia rõ trách nhiệm, mỗi bean điều chỉnh một nhóm thiết lập.
- Dùng cơ chế ordering của Spring như @Order hoặc Ordered khi phiên bản Boot hỗ trợ thứ tự đó.
- Tránh phụ thuộc thứ tự mặc định của bean.
- Kiểm thử giá trị cuối cùng trên repository được tạo.
- Ghi rõ cấu hình có điều kiện theo profile nếu môi trường khác nhau.

Một customizer tập trung thường dễ đọc hơn nhiều bean nhỏ cùng thay đổi một repository. Không đưa secret, mật khẩu hoặc thông tin kết nối vào customizer; các giá trị đó thuộc cấu hình DataSource và secret management.

## 11. Customizer có được gọi khi ứng dụng tự khai báo repository?

SessionRepositoryCustomizer được thiết kế để tùy chỉnh repository do Spring Boot auto-configuration tạo. Nếu ứng dụng tự khai báo một bean SessionRepository và làm cho auto-configuration lùi lại, customizer có thể không được áp dụng theo cách mong đợi.

Khi tự tạo repository, ứng dụng chịu trách nhiệm cấu hình đầy đủ:

- DataSource hoặc JdbcOperations.
- Transaction manager cần thiết.
- Tên bảng/schema và schema migration.
- Flush mode, save mode, timeout và cleanup.
- Index resolver và conversion/serialization.
- Việc đăng ký repository với SessionRepositoryFilter.

Không đồng thời tự tạo repository mới và kỳ vọng customizer tự tìm đúng bean nếu ứng dụng có nhiều repository. Cần kiểm tra điều kiện auto-configuration và bean thực tế được inject vào filter.

Nếu mục tiêu chỉ là đổi một thuộc tính được hỗ trợ, giữ auto-configuration và dùng property/customizer thường đơn giản hơn việc tự tạo toàn bộ repository.

## 12. Kiểm thử cấu hình repository đã tùy chỉnh

Kiểm thử cần xác nhận cả cấu hình và hành vi. Chỉ kiểm tra bean customizer tồn tại chưa chứng minh repository đã nhận thiết lập.

Một bộ kiểm thử tích hợp có thể bao gồm:

1. Khởi động ứng dụng với profile và database test riêng.
2. Xác nhận repository được tạo là JdbcIndexedSessionRepository.
3. Tạo session, đặt thuộc tính và lưu qua repository.
4. Tải lại session bằng ID và xác nhận dữ liệu chính xác.
5. Kiểm tra dữ liệu được ghi vào đúng bảng/schema đã cấu hình.
6. Nếu có custom index resolver, kiểm tra tìm session theo principal.
7. Kiểm tra save/flush mode bằng cách quan sát thay đổi được ghi theo hành vi mong đợi.
8. Kiểm tra cleanup bằng session có timeout ngắn trong môi trường test.
9. Khởi động hai instance dùng cùng database và xác nhận cả hai đọc được cùng session.
10. Nếu có converter tùy chỉnh, kiểm tra dữ liệu được ghi bởi phiên bản cũ có thể đọc được.

Không dùng database production để kiểm thử. Tạo schema riêng cho test và dọn dữ liệu sau mỗi lần chạy. Với kiểm thử cleanup theo cron, nên gọi cơ chế được hỗ trợ trong test hoặc chờ điều kiện có giới hạn; không dựa vào một khoảng sleep ngắn và giả định scheduler đã chạy.

## 13. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Customizer không được gọi | Repository không được Spring Boot auto-configure hoặc generic type không khớp | Kiểm tra repository bean và kiểu customizer |
| Ứng dụng không khởi động vì thiếu method | API repository khác phiên bản | Đối chiếu phiên bản Spring Session/Boot và API thực tế |
| Lỗi SQL sau khi đổi table name | Schema chưa được migration đồng bộ | Kiểm tra tất cả bảng, cột, khóa và tên bảng |
| Không tìm được session theo principal | IndexResolver không lưu đúng chỉ mục hoặc dữ liệu cũ chưa có index | Kiểm tra resolver, thuộc tính principal và session cũ |
| Thuộc tính thay đổi nhưng không được lưu | SaveMode và cách cập nhật object mutable không phù hợp | Gọi setAttribute hoặc điều chỉnh SaveMode sau khi kiểm thử |
| Database tăng tải sau tùy chỉnh | FlushMode/SaveMode hoặc cleanup quá thường xuyên | Đo số câu SQL, độ trễ và tần suất cleanup |
| Một instance đọc được, instance khác lỗi | Các instance có customizer, schema hoặc converter khác nhau | Đồng bộ artifact và cấu hình toàn cụm |

Khi điều tra, kiểm tra repository thực tế được filter sử dụng, cấu hình sau khi customizer chạy, schema database và log SQL. Tránh kết luận chỉ từ file YAML vì giá trị cuối cùng có thể bị ghi đè bởi profile, biến môi trường hoặc customizer khác.

## 14. Quy trình áp dụng trong production

- [ ] Xác định repository JDBC và phiên bản Spring Boot/Spring Session đang dùng.
- [ ] Kiểm tra property chuẩn trước khi viết customizer.
- [ ] Khai báo customizer với generic type chính xác.
- [ ] Chỉ thay đổi các thuộc tính thực sự cần thiết.
- [ ] Đồng bộ schema migration với tên bảng và cấu trúc repository.
- [ ] Kiểm thử create, read, update, delete và cleanup session.
- [ ] Kiểm thử nhiều instance dùng chung database.
- [ ] Kiểm thử tương thích serializer/converter khi session tồn tại qua rolling deployment.
- [ ] Đồng bộ customizer, schema và cấu hình ở mọi replica.
- [ ] Theo dõi SQL latency, connection pool, số session và thời gian cleanup.

SessionRepositoryCustomizer là cách Spring Boot cho phép điều chỉnh repository session đã được auto-configure bằng Java API. Với JDBC, nó giúp tinh chỉnh JdbcIndexedSessionRepository mà vẫn giữ luồng cấu hình tiêu chuẩn. Hãy ưu tiên properties cho thiết lập thông thường, dùng customizer cho các điểm mở rộng chuyên biệt và chỉ tự triển khai repository khi yêu cầu thay đổi vượt quá khả năng tùy chỉnh sẵn có. Schema, serializer, index và cấu hình phải đồng nhất giữa các instance để session được đọc và ghi ổn định.
