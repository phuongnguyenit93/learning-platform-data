# SessionRepositoryCustomizer và tùy chỉnh repository được tạo sẵn

Trong ứng dụng Spring Session, repository thường được tạo bởi cấu hình Spring Session hoặc cơ chế auto-configuration của Spring Boot. Repository đó đã biết cách kết nối với Redis hay JDBC, quản lý dữ liệu phiên và tham gia vào vòng đời HTTP request. Khi cần thay đổi một số hành vi của repository mà vẫn muốn giữ triển khai có sẵn, ta có thể dùng `SessionRepositoryCustomizer`.

`SessionRepositoryCustomizer` là một hook cấu hình của Spring Session. Nó nhận đối tượng `SessionRepository` đã được cấu hình và cho phép điều chỉnh các thuộc tính trước khi repository hoàn tất khởi tạo. Ví dụ, ứng dụng có thể đổi tên bảng JDBC, tùy chỉnh câu SQL theo hệ quản trị cơ sở dữ liệu, thay cách ánh xạ dữ liệu phiên từ Redis hoặc điều chỉnh chính sách ghi dữ liệu.

Điểm quan trọng là customizer tác động lên một repository cụ thể đã được cấu hình. Nó không tự tạo kho dữ liệu, không thay thế repository bằng một loại khác và không chạy ở mỗi HTTP request. Hiểu rõ vòng đời này giúp tránh tạo cấu hình trùng lặp hoặc sửa nhầm tầng khi vận hành Spring Session trên nhiều instance.

## 1. Vai trò của `SessionRepositoryCustomizer`

### 1.1. Hợp đồng và package

Interface nằm trong package:

```java
org.springframework.session.config.SessionRepositoryCustomizer
```

Đây là functional interface có tham số generic đại diện cho loại repository cần tùy chỉnh. Dạng rút gọn của hợp đồng:

```java
@FunctionalInterface
public interface SessionRepositoryCustomizer<T extends SessionRepository> {

    void customize(T sessionRepository);

}
```

Interface này có từ Spring Session 2.2.0. Vì chỉ có một phương thức `customize`, ta có thể triển khai bằng một lớp riêng hoặc dùng lambda khi khai báo bean.

Tham số generic rất quan trọng. Ví dụ `SessionRepositoryCustomizer<JdbcIndexedSessionRepository>` chỉ rõ customizer dành cho repository JDBC; `SessionRepositoryCustomizer<RedisIndexedSessionRepository>` dành cho repository Redis dạng indexed. Spring Session có thể tìm customizer tương ứng với loại repository mà cấu hình đang tạo.

### 1.2. Hook được gọi ở giai đoạn nào?

Luồng cấu hình có thể hình dung như sau:

```mermaid
flowchart TD
    A[Khởi động ApplicationContext] --> B[Đọc cấu hình và chọn loại repository]
    B --> C[Tạo repository Redis hoặc JDBC]
    C --> D[Tìm SessionRepositoryCustomizer phù hợp]
    D --> E[Gọi customize(repository)]
    E --> F[Hoàn tất khởi tạo repository]
    F --> G[SessionRepositoryFilter phục vụ HTTP request]
```

Customizer được thiết kế để điều chỉnh repository trước khi nó được khởi tạo hoàn chỉnh. Vì vậy, đây là nơi phù hợp để đặt các tùy chọn cần được áp dụng một lần khi ứng dụng khởi động. Nó không phải interceptor cho request và không nên chứa logic nghiệp vụ theo từng người dùng.

Ví dụ, nếu repository JDBC đã được cấu hình để dùng `JdbcIndexedSessionRepository`, customizer có thể gọi `setTableName(...)` trên chính đối tượng đó. Cấu hình Spring Session vẫn chịu trách nhiệm tạo repository, gắn nó với `SessionRepositoryFilter` và quản lý vòng đời bean.

### 1.3. Khi nào nên dùng?

Hãy cân nhắc `SessionRepositoryCustomizer` khi:

- Cấu hình mặc định đã chọn đúng loại repository, nhưng cần thay một thuộc tính mà repository công khai setter.
- Cần điều chỉnh câu SQL của JDBC theo cú pháp hoặc hành vi đặc thù của hệ quản trị cơ sở dữ liệu.
- Cần thay cách repository Redis ánh xạ dữ liệu đã đọc từ Redis thành đối tượng phiên.
- Cần điều chỉnh `FlushMode`, `SaveMode`, thời hạn mặc định hoặc namespace trực tiếp trên repository.
- Muốn giữ cơ chế tạo repository có sẵn và giới hạn phần cấu hình riêng trong một bean nhỏ, dễ kiểm thử.

Nếu chỉ cần đặt một giá trị đã có thuộc tính cấu hình hoặc thuộc tính annotation, nên ưu tiên cách cấu hình tiêu chuẩn. Customizer hữu ích khi cần cấu hình bằng mã hoặc khi tùy chọn không được biểu diễn thuận tiện bằng property.

## 2. Phân biệt các tầng cấu hình

Spring Session có nhiều điểm mở rộng. Chọn đúng điểm mở rộng sẽ làm cấu hình dễ hiểu và tránh việc một bean đảm nhiệm quá nhiều trách nhiệm.

| Nhu cầu | Cơ chế thường phù hợp |
|---|---|
| Đặt thời hạn session trong cấu hình ứng dụng | `spring.session.timeout`, `SessionTimeout` bean trong phiên bản Spring Boot hỗ trợ, hoặc thuộc tính timeout của annotation tương ứng |
| Đổi tên bảng JDBC | `tableName` của `@EnableJdbcHttpSession` hoặc `SessionRepositoryCustomizer<JdbcIndexedSessionRepository>` |
| Đổi câu SQL của JDBC | Các setter `set*Query` trên `JdbcIndexedSessionRepository`, thường được gọi từ customizer |
| Đổi namespace Redis | Property của Spring Boot, thuộc tính `redisNamespace` của annotation hoặc setter repository phù hợp |
| Đổi serializer Redis | Bean `RedisSerializer<Object>` có tên `springSessionDefaultRedisSerializer` theo quy ước Spring Session |
| Đổi cookie hoặc cách truyền session ID | `CookieSerializer` hoặc `HttpSessionIdResolver` |
| Thay hẳn cách lưu trữ và triển khai repository | Tự cấu hình hoặc triển khai `SessionRepository` theo yêu cầu |
| Tùy chỉnh repository WebFlux | `ReactiveSessionRepositoryCustomizer` tương ứng, không dùng customizer Servlet |

`SessionRepositoryCustomizer` tác động vào repository. Nó không phải cách tổng quát để cấu hình mọi thành phần Spring Session. Chẳng hạn, thay cookie serializer là việc của lớp xử lý cookie; thay bộ tuần tự hóa thuộc tính Redis là việc của serializer; còn chọn kho Redis hay JDBC là quyết định ở bước cấu hình repository.

## 3. Tùy chỉnh repository JDBC

### 3.1. Đổi tên bảng bằng customizer

Spring Session JDBC sử dụng `JdbcIndexedSessionRepository`. Mặc định, dữ liệu phiên được lưu trong các bảng `SPRING_SESSION` và `SPRING_SESSION_ATTRIBUTES`. Nếu hệ thống cần tiền tố riêng hoặc quy ước tên bảng khác, có thể dùng thuộc tính `tableName` của `@EnableJdbcHttpSession`.

Ví dụ dùng customizer:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.config.SessionRepositoryCustomizer;
import org.springframework.session.jdbc.JdbcIndexedSessionRepository;
import org.springframework.session.jdbc.config.annotation.web.http.EnableJdbcHttpSession;

@Configuration
@EnableJdbcHttpSession
public class JdbcSessionConfiguration {

    @Bean
    SessionRepositoryCustomizer<JdbcIndexedSessionRepository> jdbcSessionRepositoryCustomizer() {
        return repository -> repository.setTableName("APP_HTTP_SESSION");
    }

}
```

Khi repository được tạo, customizer đặt tên bảng chính thành `APP_HTTP_SESSION`. Bảng thuộc tính tương ứng được đặt tên theo quy ước hậu tố `_ATTRIBUTES`, vì vậy schema phải có bảng `APP_HTTP_SESSION_ATTRIBUTES` cùng các khóa và kiểu cột phù hợp.

Nếu chỉ cần đổi tên bảng, cách khai báo trực tiếp sau thường ngắn gọn hơn:

```java
@Configuration
@EnableJdbcHttpSession(tableName = "APP_HTTP_SESSION")
public class JdbcSessionConfiguration {
}
```

Hai cách trên minh họa hai điểm cấu hình khác nhau. Không cần khai báo cả hai cùng đặt một giá trị. Hãy chọn annotation khi tùy chọn đã được hỗ trợ trực tiếp; chọn customizer khi cần thực hiện thêm logic hoặc kết hợp nhiều setter trên repository.

### 3.2. Tùy chỉnh câu SQL theo hệ quản trị cơ sở dữ liệu

Một lý do thực tế để dùng customizer là điều chỉnh câu SQL. Các hệ quản trị cơ sở dữ liệu có cú pháp khác nhau cho thao tác upsert, xử lý xung đột khóa duy nhất hoặc chuyển đổi kiểu dữ liệu. `JdbcIndexedSessionRepository` cung cấp các setter `set*Query` cho những câu SQL mà repository sử dụng.

Ví dụ sau minh họa cách đăng ký customizer cho một cấu hình PostgreSQL. Câu lệnh `ON CONFLICT` là cú pháp riêng của PostgreSQL; không sao chép nguyên văn sang MySQL, SQL Server, Oracle hoặc DB2.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.config.SessionRepositoryCustomizer;
import org.springframework.session.jdbc.JdbcIndexedSessionRepository;
import org.springframework.session.jdbc.config.annotation.web.http.EnableJdbcHttpSession;

@Configuration
@EnableJdbcHttpSession
public class JdbcSessionConfiguration {

    private static final String CREATE_ATTRIBUTE_QUERY = """
        INSERT INTO %TABLE_NAME%_ATTRIBUTES
            (SESSION_PRIMARY_ID, ATTRIBUTE_NAME, ATTRIBUTE_BYTES)
        VALUES (?, ?, ?)
        ON CONFLICT (SESSION_PRIMARY_ID, ATTRIBUTE_NAME) DO NOTHING
        """;

    @Bean
    SessionRepositoryCustomizer<JdbcIndexedSessionRepository> jdbcQueryCustomizer() {
        return repository -> repository.setCreateSessionAttributeQuery(CREATE_ATTRIBUTE_QUERY);
    }

}
```

Placeholder `%TABLE_NAME%` được Spring Session thay bằng tên bảng đã cấu hình cho repository. Câu truy vấn phải giữ đúng thứ tự tham số, tên cột và ngữ nghĩa mà repository mong đợi. Một câu SQL hợp lệ về cú pháp nhưng không đúng ngữ nghĩa có thể làm mất cập nhật thuộc tính hoặc khiến request đồng thời phát sinh lỗi.

Khi tùy chỉnh nhiều câu lệnh, hãy xem toàn bộ nhóm thao tác liên quan như tạo thuộc tính, cập nhật thuộc tính, xóa thuộc tính và cập nhật phiên. Chỉ thay câu lệnh cần thiết, giữ các câu còn lại theo mặc định và kiểm thử tình huống đồng thời. Spring Session JDBC cũng cung cấp một số customizer theo nhà cung cấp cơ sở dữ liệu để áp dụng truy vấn tối ưu cho các RDBMS phổ biến; nên kiểm tra phiên bản thư viện đang dùng trước khi tự viết lại những câu truy vấn đã có sẵn.

### 3.3. Những phần JDBC không nên nhét vào customizer

Không phải mọi tùy chỉnh JDBC đều thuộc `SessionRepositoryCustomizer`:

- Chọn `DataSource` dùng cho session có thể cần qualifier `@SpringSessionDataSource` khi ứng dụng có nhiều `DataSource`.
- Tùy chỉnh chuyển đổi/tuần tự hóa thuộc tính có thể cần `ConversionService` bean với tên `springSessionConversionService`.
- Xử lý BLOB có thể cần `LobHandler` bean với tên `springSessionLobHandler`.
- Tạo bảng và chỉ mục cần schema SQL đúng với nhà cung cấp cơ sở dữ liệu.

Customizer có thể gọi các setter công khai của repository, nhưng không thay thế những cơ chế cấu hình chuyên biệt nêu trên.

## 4. Tùy chỉnh repository Redis

### 4.1. Chọn đúng kiểu repository

Spring Session Redis có các triển khai khác nhau. `RedisSessionRepository` là lựa chọn cơ bản; `RedisIndexedSessionRepository` bổ sung khả năng lập chỉ mục và truy vấn session theo thông tin như principal. Kiểu repository được chọn ảnh hưởng đến generic type của customizer.

Ví dụ:

| Cấu hình repository | Kiểu customizer tương ứng |
|---|---|
| `@EnableRedisHttpSession` | `SessionRepositoryCustomizer<RedisSessionRepository>` |
| `@EnableRedisIndexedHttpSession` | `SessionRepositoryCustomizer<RedisIndexedSessionRepository>` |

Nếu cấu hình đang tạo `RedisSessionRepository` nhưng bean được khai báo cho `RedisIndexedSessionRepository`, customizer không khớp với kiểu đích và sẽ không được áp dụng như mong đợi. Hãy xác định repository thực tế trước khi viết generic type.

### 4.2. Điều chỉnh timeout, flush và save mode

Ví dụ dùng repository indexed:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.FlushMode;
import org.springframework.session.SaveMode;
import org.springframework.session.config.SessionRepositoryCustomizer;
import org.springframework.session.data.redis.RedisIndexedSessionRepository;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisIndexedHttpSession;

@Configuration
@EnableRedisIndexedHttpSession
public class RedisSessionConfiguration {

    @Bean
    SessionRepositoryCustomizer<RedisIndexedSessionRepository> redisSessionRepositoryCustomizer() {
        return repository -> {
            repository.setDefaultMaxInactiveInterval(Duration.ofMinutes(25));
            repository.setRedisKeyNamespace("portal:session");
            repository.setFlushMode(FlushMode.ON_SAVE);
            repository.setSaveMode(SaveMode.ON_SET_ATTRIBUTE);
        };
    }

}
```

Ví dụ đặt timeout mặc định 25 phút cho session mới, tách khóa Redis bằng namespace `portal:session`, chỉ ghi khi repository lưu session và chỉ lưu những thuộc tính đã được đặt hoặc thay đổi.

Hai chế độ `FlushMode` và `SaveMode` điều khiển hai khía cạnh khác nhau:

| Chế độ | Các giá trị | Ý nghĩa |
|---|---|---|
| `FlushMode` | `ON_SAVE`, `IMMEDIATE` | Quyết định thời điểm ghi thay đổi xuống kho lưu trữ. `ON_SAVE` ghi khi `save` được gọi; `IMMEDIATE` ghi sớm nhất có thể. |
| `SaveMode` | `ON_SET_ATTRIBUTE`, `ON_GET_ATTRIBUTE`, `ALWAYS` | Quyết định tập thuộc tính cần lưu. `ON_SET_ATTRIBUTE` lưu thuộc tính được thay đổi; `ON_GET_ATTRIBUTE` còn tính cả thuộc tính đã đọc; `ALWAYS` lưu tất cả thuộc tính. |

Trong môi trường có nhiều request đồng thời trên cùng session, `ON_SET_ATTRIBUTE` thường giảm nguy cơ một request ghi đè những thuộc tính mà nó không thay đổi. `ALWAYS` có thể ghi lại toàn bộ thuộc tính và tăng nguy cơ ghi đè thay đổi của request khác. Tuy nhiên, SaveMode không biến thao tác cập nhật session thành transaction nghiệp vụ; dữ liệu quan trọng vẫn cần thiết kế đồng bộ phù hợp.

`IMMEDIATE` có thể làm thay đổi được ghi xuống Redis ngay khi thao tác xảy ra, nhưng cũng có thể tăng số lần truy cập Redis và khiến trạng thái trung gian xuất hiện sớm hơn. `ON_SAVE` gom việc ghi theo điểm lưu của repository, thường phù hợp với vòng đời HTTP session. Chọn chế độ dựa trên yêu cầu về độ trễ, số lần ghi, khả năng nhìn thấy cập nhật và tải đồng thời.

### 4.3. Thay mapper đọc dữ liệu Redis

Một trường hợp nâng cao là tùy chỉnh cách chuyển dữ liệu Redis thành đối tượng session. Repository Redis đọc dữ liệu từ Redis dưới dạng map rồi dùng mapper để tạo `MapSession`. Nếu dữ liệu không đầy đủ hoặc không tương thích, mapper mặc định có thể ném lỗi.

Tài liệu Spring Session minh họa customizer có thể đặt một `RedisSessionMapper` tùy chỉnh. Mapper có thể ủy quyền cho mapper mặc định; nếu phát hiện dữ liệu phiên hỏng theo trường hợp đã xác định, ứng dụng có thể xóa bản ghi không còn sử dụng được và trả về kết quả không có session. Đây là cách xử lý lỗi dữ liệu cụ thể, không phải lý do để bỏ qua mọi exception khi đọc Redis.

Ví dụ hoàn chỉnh cho repository Redis cơ bản:

```java
import java.util.Map;
import java.util.function.BiFunction;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.MapSession;
import org.springframework.session.config.SessionRepositoryCustomizer;
import org.springframework.session.data.redis.RedisSessionMapper;
import org.springframework.session.data.redis.RedisSessionRepository;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisHttpSession;

@Configuration
@EnableRedisHttpSession
public class RedisSessionConfiguration {

    @Bean
    SessionRepositoryCustomizer<RedisSessionRepository> redisMapperCustomizer() {
        return repository -> repository.setRedisSessionMapper(new SafeRedisSessionMapper(repository));
    }

    static class SafeRedisSessionMapper implements BiFunction<String, Map<String, Object>, MapSession> {

        private final RedisSessionMapper delegate = new RedisSessionMapper();
        private final RedisSessionRepository repository;

        SafeRedisSessionMapper(RedisSessionRepository repository) {
            this.repository = repository;
        }

        @Override
        public MapSession apply(String sessionId, Map<String, Object> attributes) {
            try {
                return this.delegate.apply(sessionId, attributes);
            }
            catch (IllegalStateException ex) {
                this.repository.deleteById(sessionId);
                return null;
            }
        }
    }
}
```

Mapper ủy quyền việc đọc dữ liệu cho `RedisSessionMapper` mặc định. Nếu mapper mặc định ném `IllegalStateException` do dữ liệu phiên thiếu trường bắt buộc, ví dụ `creationTime`, custom mapper xóa phiên đó và trả về `null`. Đây là chính sách mẫu cho dữ liệu phiên hỏng đã xác định; nếu xóa session khi deserialize lỗi, hãy ghi nhận số liệu và log an toàn để điều tra nguyên nhân. Không bắt mọi exception rồi trả về `null`, vì lỗi kết nối Redis hoặc lỗi hạ tầng không có nghĩa dữ liệu phiên đơn giản là không tồn tại. Với `RedisIndexedSessionRepository`, cách xóa cần được thiết kế khác để tránh gọi ngược mapper trong quá trình `deleteById`.

## 5. Kết hợp customizer với Spring Boot

Spring Boot cung cấp auto-configuration cho Spring Session khi ứng dụng thêm starter tương ứng, ví dụ starter session data Redis hoặc session JDBC. Trong ứng dụng Servlet, Boot có thể cấu hình repository và filter mà không cần khai báo `@Enable*HttpSession` thủ công.

Khi cần can thiệp sâu vào repository, có thể dùng extension point mà cấu hình Spring Session đang sử dụng cung cấp. Trước khi thêm customizer, hãy kiểm tra:

1. Starter và dependency nào đang có mặt.
2. Repository thực tế được chọn là `RedisSessionRepository`, `RedisIndexedSessionRepository` hay `JdbcIndexedSessionRepository`.
3. Phiên bản Spring Boot và Spring Session đang dùng có hỗ trợ setter được gọi trong customizer hay không.
4. Auto-configuration còn hoạt động hay đã nhường chỗ cho cấu hình thủ công.

Nếu khai báo `@EnableJdbcHttpSession`, `@EnableRedisHttpSession` hoặc annotation tương ứng, cấu hình Spring Session thủ công sẽ làm Spring Boot auto-configuration lùi lại theo cơ chế back-off. Tránh trộn nhiều cơ chế kích hoạt repository nếu không hiểu rõ bean nào đang được tạo. Với Boot, ưu tiên starter và property cho cấu hình thông thường; dùng customizer khi thật sự cần tùy chỉnh đối tượng repository đã được tạo.

Một số cấu hình phiên bản mới của Spring Boot cung cấp `SessionTimeout` bean để đặt timeout theo cách chương trình. Nếu chỉ cần timeout, hãy cân nhắc cơ chế được tài liệu đúng phiên bản Boot khuyến nghị trước khi dùng customizer để gọi setter trực tiếp.

## 6. Điều kiện để customizer được áp dụng

### 6.1. Khai báo customizer thành bean

Customizer phải được Spring quản lý trong `ApplicationContext`, thường thông qua `@Bean` trong một lớp `@Configuration` hoặc một component được scan. Tạo một object customizer bằng `new` trong một dịch vụ không khiến cấu hình Spring Session tự động phát hiện object đó.

### 6.2. Generic type phải khớp repository thực tế

Generic type thể hiện loại repository đích. Ví dụ, nếu chọn JDBC thì dùng `JdbcIndexedSessionRepository`; nếu chọn Redis indexed thì dùng `RedisIndexedSessionRepository`. Không dùng raw type chung chung chỉ để né khai báo kiểu, vì điều đó làm cấu hình khó kiểm tra và có thể không được cấu hình repository nhận như mong muốn.

### 6.3. Phải có cấu hình tạo repository tương ứng

Customizer không tự kích hoạt Spring Session. Cần có starter/auto-configuration phù hợp hoặc cấu hình `@Enable*HttpSession` tạo repository. Nếu không có repository đích, phương thức `customize` không có đối tượng để tác động.

### 6.4. Không sửa repository sau khi request bắt đầu

Customizer được gọi ở giai đoạn cấu hình. Không lưu repository vào biến static rồi sửa tùy ý trong controller. Thay đổi runtime có thể gây sai khác giữa request, tạo race condition hoặc làm cấu hình không nhất quán giữa các instance.

### 6.5. Tránh side effect không cần thiết

Customizer nên thực hiện các phép gán cấu hình rõ ràng. Không nên dùng callback này để chạy migration, tạo schema, gửi thông báo, gọi dịch vụ bên ngoài hoặc thực hiện tác vụ có thể lặp lại và gây side effect. Schema, kết nối, secret và hạ tầng nên được quản lý bằng các cơ chế cấu hình và triển khai chuyên trách.

## 7. Kiểm thử customizer

Một customizer có thể biên dịch thành công nhưng không được áp dụng vì generic type không khớp hoặc cấu hình repository khác với dự kiến. Do đó, kiểm thử cần xác minh cả callback lẫn repository thật trong context.

### 7.1. Kiểm tra bean trong ApplicationContext

Với JDBC, có thể viết kiểm thử context để lấy repository và xác minh tên bảng sau khi context khởi động:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.session.jdbc.JdbcIndexedSessionRepository;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class JdbcSessionRepositoryConfigurationTest {

    @Autowired
    JdbcIndexedSessionRepository repository;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void persistsSessionToConfiguredTable() {
        var session = repository.createSession();
        repository.save(session);

        Integer rowCount = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM APP_HTTP_SESSION", Integer.class);

        assertThat(rowCount).isEqualTo(1);
    }
}
```

Ví dụ giả định context kiểm thử đã tạo schema gồm `APP_HTTP_SESSION` và `APP_HTTP_SESSION_ATTRIBUTES`, đồng thời chỉ có một session trong bảng khi assertion chạy. Một số thuộc tính repository không có getter công khai tương ứng. Trong trường hợp đó, nên kiểm tra hành vi thông qua repository hoặc tích hợp JDBC test thay vì dùng reflection để đọc field nội bộ.

### 7.2. Kiểm thử tích hợp với kho dữ liệu

Với JDBC, cần xác minh schema đúng, bảng phiên và bảng thuộc tính đúng tên, câu SQL tùy chỉnh hoạt động với dialect thực tế, và hai request đồng thời không gây lỗi trùng khóa hoặc mất cập nhật ngoài dự kiến.

Với Redis, cần xác minh namespace tạo đúng tiền tố khóa, session mới nhận timeout mong muốn, serializer có thể đọc lại thuộc tính, mapper xử lý dữ liệu lỗi theo chính sách và repository có hành vi flush/save như cấu hình.

### 7.3. Kiểm thử khởi động và nhiều instance

Trong môi trường nhiều instance, mỗi instance cần dùng cùng loại repository và cùng cấu hình tương thích. Hãy kiểm thử tạo session ở instance A rồi đọc ở instance B, cập nhật thuộc tính từ hai request gần đồng thời, hết hạn, đăng xuất và tình huống kho dữ liệu tạm thời không khả dụng. Nếu một instance áp dụng customizer còn instance khác không áp dụng, dữ liệu phiên có thể được diễn giải khác nhau hoặc một instance không thể đọc dữ liệu do instance kia ghi.

## 8. Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Customizer không chạy | Không có bean trong context hoặc không có repository được cấu hình | Kiểm tra component scan, cấu hình `@Enable*HttpSession` hoặc starter auto-configuration |
| Customizer không tác động repository đang dùng | Generic type chỉ tới repository khác loại | Kiểm tra loại repository thực tế và sửa generic type cho khớp |
| JDBC báo không tìm thấy bảng | Đổi `tableName` nhưng schema không có bảng chính và bảng `_ATTRIBUTES` tương ứng | Cập nhật schema và index theo đúng database vendor |
| SQL lỗi khi chạy | Câu query tùy chỉnh dùng cú pháp không đúng dialect hoặc sai placeholder/thứ tự tham số | Dùng query phù hợp DB, giữ `%TABLE_NAME%` và kiểm thử trên DB thật |
| Redis đọc session lỗi sau khi đổi serializer/mapper | Dữ liệu cũ được ghi bằng định dạng khác hoặc mapper giả định sai cấu trúc | Lập kế hoạch tương thích dữ liệu, kiểm thử nâng cấp và chỉ xử lý lỗi đã xác định |
| Cấu hình có tác dụng khác dự kiến | Property, annotation và customizer cùng thay một thuộc tính | Chọn một nguồn cấu hình chính và xác minh giá trị hiệu lực khi khởi động |
| Một instance hoạt động, instance khác lỗi | Các instance dùng khác version, generic target, namespace, serializer hoặc SQL | Đồng bộ cấu hình và kiểm thử rolling deployment |

Không nên khắc phục lỗi bằng cách bắt mọi exception rồi bỏ qua. Lỗi đọc repository có thể biểu thị Redis/JDBC không sẵn sàng; trong luồng xác thực, xử lý sai có thể dẫn tới việc ứng dụng ra quyết định dựa trên trạng thái phiên không đáng tin cậy.

## 9. Quy trình áp dụng trong dự án

Khi cần tùy chỉnh repository đã được Spring Session tạo, thực hiện theo trình tự:

1. Xác định yêu cầu cụ thể: đổi tên bảng, thay SQL, điều chỉnh TTL, flush/save mode hay mapper.
2. Xác định repository thực tế và phiên bản Spring Boot/Spring Session đang chạy.
3. Kiểm tra xem property hoặc annotation đã hỗ trợ tùy chọn đó chưa.
4. Nếu cần tùy chỉnh đối tượng repository, khai báo một bean `SessionRepositoryCustomizer` với generic type đúng.
5. Chỉ gọi các setter công khai và giữ thay đổi trong phạm vi cần thiết.
6. Kiểm thử ApplicationContext để chắc chắn customizer đã được áp dụng.
7. Kiểm thử tích hợp với Redis/JDBC, bao gồm TTL, cập nhật đồng thời, dữ liệu phiên cũ và lỗi kho lưu trữ.
8. Đảm bảo tất cả instance triển khai cùng cấu hình trước khi phát hành.

`SessionRepositoryCustomizer` giúp tinh chỉnh repository có sẵn ở thời điểm cấu hình. Dùng đúng hook sẽ giữ được lợi ích của triển khai Redis/JDBC do Spring Session quản lý, đồng thời cho phép ứng dụng thích ứng với schema, truy vấn và chính sách lưu trữ riêng. Khi nhu cầu là thay toàn bộ cơ chế lưu trữ, hãy thiết kế repository riêng; khi chỉ cần đổi thuộc tính cấu hình phổ biến, hãy dùng property hoặc annotation tương ứng.

## Tài liệu tham khảo

- [Spring Session API — SessionRepositoryCustomizer](https://docs.spring.io/spring-session/docs/current/api/org/springframework/session/config/SessionRepositoryCustomizer.html)
- [Spring Session JDBC — tùy chỉnh table name và SQL query](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)
- [Spring Session Redis — tùy chỉnh repository và session mapper](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Boot — Spring Session auto-configuration](https://docs.spring.io/spring-boot/reference/web/spring-session.html)
