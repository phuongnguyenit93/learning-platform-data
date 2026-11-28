# Chọn transaction manager với `@SpringSessionTransactionManager`

Spring Session JDBC cần một transaction manager để thực hiện các thao tác lưu session trong database. Ứng dụng Spring Boot có thể đồng thời dùng nhiều `PlatformTransactionManager`: một manager cho database nghiệp vụ, một manager cho database session, hoặc các manager riêng cho từng hệ thống dữ liệu. Nếu Spring Session chọn nhầm manager, thao tác đọc/ghi session có thể chạy trên sai DataSource, lỗi khi lấy connection hoặc không dùng transaction boundary mà kiến trúc mong muốn.

`@SpringSessionTransactionManager` là qualifier để đánh dấu bean `PlatformTransactionManager` dành cho Spring Session. Spring Boot có thể dùng qualifier này khi auto-configure Spring Session JDBC, nhờ đó ứng dụng chỉ rõ manager nào phải được repository session sử dụng. Annotation giúp chọn bean; nó không tự tạo transaction manager, không tạo DataSource và không biến hai database thành một transaction phân tán.

Bài học này trình bày vai trò của transaction manager trong Spring Session JDBC, cách dùng annotation khi có một hoặc nhiều manager, quan hệ với `@Primary` và `@Transactional`, các ranh giới transaction cần hiểu rõ, cùng cách kiểm tra cấu hình trong ứng dụng nhiều DataSource.

## 1. Vì sao Spring Session JDBC cần chọn transaction manager?

Spring Session JDBC lưu session và session attributes trong các bảng quan hệ. Repository dùng JDBC để tải session, lưu thay đổi, xóa phiên và dọn các bản ghi hết hạn. Những câu lệnh này cần chạy trên một `DataSource` cụ thể và trong transaction phù hợp.

Trong ứng dụng đơn giản, chỉ có một `DataSource` và một `PlatformTransactionManager`. Spring Boot thường có thể dùng manager đó cho cả các thao tác nghiệp vụ lẫn Spring Session. Khi ứng dụng mở rộng, có thể có nhiều manager:

- `businessTransactionManager` quản lý database đơn hàng.
- `sessionTransactionManager` quản lý database Spring Session.
- `auditTransactionManager` quản lý database audit hoặc báo cáo.

Khi có nhiều bean cùng kiểu `PlatformTransactionManager`, Spring cần quy tắc chọn bean. `@Primary` xác định bean ưu tiên chung cho các điểm inject không chỉ rõ qualifier. Tuy nhiên, Spring Session có thể cần một manager riêng, không nhất thiết là manager `@Primary` của nghiệp vụ. `@SpringSessionTransactionManager` cung cấp dấu hiệu chuyên biệt cho auto-configuration của Spring Boot.

```mermaid
flowchart TD
    A[Spring Boot ApplicationContext] --> B[PlatformTransactionManager beans]
    B --> C[businessTransactionManager]
    B --> D[sessionTransactionManager]
    B --> E[auditTransactionManager]
    D -->|@SpringSessionTransactionManager| F[Spring Session JDBC auto-configuration]
    F --> G[JdbcIndexedSessionRepository]
    G --> H[Session DataSource]
    C --> I[Business @Transactional services]
    I --> J[Business DataSource]
```

Chọn đúng manager giúp repository session dùng đúng tài nguyên và transaction strategy. Nó cũng làm cấu hình dễ đọc hơn: người bảo trì có thể nhìn vào bean được đánh dấu và biết transaction manager nào dành cho Spring Session.

## 2. `@SpringSessionTransactionManager` là qualifier, không phải transaction manager

Annotation này thuộc Spring Boot và được dùng để đánh dấu bean `PlatformTransactionManager` mà Spring Session nên sử dụng. Trong các phiên bản Spring Boot có hỗ trợ annotation, package thường dùng là:

```java
import org.springframework.boot.autoconfigure.session.SpringSessionTransactionManager;
```

Một ví dụ tối giản:

```java
@Bean
@SpringSessionTransactionManager
PlatformTransactionManager sessionTransactionManager(DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
```

Trong ví dụ, `new JdbcTransactionManager(dataSource)` tạo transaction manager thực sự. `@SpringSessionTransactionManager` chỉ đánh dấu bean đó để Spring Boot chọn làm manager cho Spring Session JDBC.

Annotation không làm các việc sau:

- Không tạo hoặc cấu hình `DataSource`.
- Không mở transaction ngay tại thời điểm ApplicationContext khởi động.
- Không tự áp dụng cho mọi phương thức `@Transactional` trong ứng dụng.
- Không thay thế `@Primary` hoặc qualifier dùng cho injection nghiệp vụ.
- Không cung cấp distributed transaction giữa nhiều database.
- Không bảo đảm thao tác lưu session luôn commit cùng transaction nghiệp vụ.

Hãy dùng annotation trên bean transaction manager, không đặt nó lên service method hoặc repository method. Cũng cần xác nhận phiên bản Spring Boot đang dùng có annotation này; với phiên bản cũ chưa hỗ trợ, dùng cách cấu hình thủ công phù hợp với API của phiên bản đó hoặc nâng cấp theo dependency management của dự án.

## 3. Trường hợp chỉ có một transaction manager

Nếu ứng dụng có một `DataSource` và một transaction manager JDBC, thường không cần đánh dấu manager riêng cho Spring Session. Auto-configuration có thể dùng manager duy nhất có sẵn.

Ví dụ:

```java
@Configuration
public class DatabaseConfiguration {

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
```

Trong một ứng dụng Spring Boot thông thường, bean `DataSource` và transaction manager có thể đã được tự cấu hình; ví dụ trên chỉ minh họa trường hợp ứng dụng tự khai báo manager. Khi chỉ có một manager, việc thêm qualifier không đem lại nhiều giá trị và có thể làm cấu hình phức tạp hơn mức cần thiết.

Trước khi tạo bean mới, kiểm tra xem Boot đã tạo transaction manager chưa. Nếu vừa có manager auto-configured vừa thêm một manager tùy chỉnh, có thể xuất hiện nhiều bean và làm việc chọn manager trở nên mơ hồ. Chỉ tự khai báo khi cần cấu hình cụ thể, chẳng hạn có nhiều DataSource hoặc cần thay đổi loại manager.

## 4. Đánh dấu manager riêng khi có nhiều DataSource

Một kiến trúc phổ biến tách database session khỏi database nghiệp vụ. Khi đó cần đánh dấu cả DataSource và transaction manager dành cho session. Spring Boot cung cấp `@SpringSessionDataSource` cho DataSource và `@SpringSessionTransactionManager` cho transaction manager trong các phiên bản có hỗ trợ.

Ví dụ cấu hình hai DataSource:

```java
import javax.sql.DataSource;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.boot.autoconfigure.session.SpringSessionDataSource;
import org.springframework.boot.autoconfigure.session.SpringSessionTransactionManager;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.jdbc.DataSourceBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class MultiDatabaseConfiguration {

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.business")
    HikariDataSource businessDataSource() {
        return DataSourceBuilder.create()
                .type(HikariDataSource.class)
                .build();
    }

    @Bean
    @SpringSessionDataSource
    @ConfigurationProperties("app.datasource.session")
    HikariDataSource sessionDataSource() {
        return DataSourceBuilder.create()
                .type(HikariDataSource.class)
                .build();
    }

    @Bean
    @Primary
    PlatformTransactionManager businessTransactionManager(
            DataSource businessDataSource) {
        return new JdbcTransactionManager(businessDataSource);
    }

    @Bean
    @SpringSessionTransactionManager
    PlatformTransactionManager sessionTransactionManager(
            @SpringSessionDataSource DataSource sessionDataSource) {
        return new JdbcTransactionManager(sessionDataSource);
    }
}
```

Ở ví dụ này:

- `businessDataSource` là `@Primary`, nên các injection không có qualifier thường nhận database nghiệp vụ.
- `sessionDataSource` được đánh dấu `@SpringSessionDataSource` để Spring Boot chọn cho Spring Session JDBC.
- `businessTransactionManager` là `@Primary`, phù hợp với các service nghiệp vụ dùng `@Transactional` mặc định.
- `sessionTransactionManager` được đánh dấu `@SpringSessionTransactionManager` để auto-configuration Spring Session chọn manager tương ứng.

Khi có nhiều bean cùng kiểu, việc đánh dấu `@Primary` cho manager nghiệp vụ tránh làm các service `@Transactional` không chỉ rõ manager bị chọn nhầm manager session. Đồng thời, qualifier chuyên biệt giúp Spring Session không phải dùng manager `@Primary` nếu manager đó quản lý DataSource khác.

Ví dụ property:

```yaml
app:
  datasource:
    business:
      jdbc-url: jdbc:postgresql://db-business:5432/orders
      username: orders_app
      password: ${ORDERS_DB_PASSWORD}
      maximum-pool-size: 20
    session:
      jdbc-url: jdbc:postgresql://db-session:5432/sessions
      username: session_app
      password: ${SESSION_DB_PASSWORD}
      maximum-pool-size: 10
```

Các prefix `app.datasource.*` là cấu hình do ứng dụng tự đặt. Spring Boot không tự bind chúng vào hai pool nếu không có các bean `@ConfigurationProperties` như ví dụ. Trong hệ thống thật, có thể cần cấu hình thêm driver, pool timeout, health check và secret management.

## 5. Quan hệ giữa `@SpringSessionTransactionManager` và `@Primary`

Hai annotation có mục đích khác nhau:

| Annotation | Phạm vi lựa chọn | Ý nghĩa |
| --- | --- | --- |
| `@Primary` | Injection chung khi có nhiều bean cùng kiểu và điểm inject không chỉ rõ qualifier | Bean mặc định được ưu tiên |
| `@SpringSessionTransactionManager` | Spring Boot auto-configuration của Spring Session JDBC | Đánh dấu manager dành cho các thao tác repository session |
| `@Qualifier("...")` | Điểm inject cụ thể trong code ứng dụng | Chọn bean theo tên/qualifier được chỉ định |

Một bean có thể mang cả `@Primary` và `@SpringSessionTransactionManager` nếu cùng một transaction manager thực sự phù hợp cho cả nghiệp vụ lẫn session. Nhưng khi hai database tách biệt, thường nên có manager riêng: manager nghiệp vụ là `@Primary`, manager session mang qualifier Spring Session.

Không dùng `@Primary` trên session manager chỉ để Spring Session nhận ra nó. Điều đó có thể khiến mọi service `@Transactional` mặc định chạy trên database session, gây lỗi hoặc ghi dữ liệu nghiệp vụ sai nơi. Hãy xác định rõ manager mặc định cho ứng dụng và manager chuyên biệt cho session.

## 6. Chỉ rõ transaction manager cho `@Transactional`

`@SpringSessionTransactionManager` không thay đổi quy tắc chọn manager cho mọi `@Transactional` trong ứng dụng. Các service nghiệp vụ vẫn nên chỉ rõ manager nếu có nhiều nguồn dữ liệu, hoặc dùng manager `@Primary` nếu đó là lựa chọn mặc định có chủ ý.

Ví dụ:

```java
@Service
public class OrderService {

    @Transactional("businessTransactionManager")
    public void submitOrder(long orderId) {
        // Cập nhật đơn hàng trong business database.
    }
}
```

Nếu một service thực sự thao tác trên database session (một trường hợp ít gặp ở code nghiệp vụ thông thường), có thể chỉ rõ manager session:

```java
@Transactional("sessionTransactionManager")
public void performSessionStoreMaintenance() {
    // Thao tác bảo trì dữ liệu session qua đúng repository/API được hỗ trợ.
}
```

Không nên truy cập trực tiếp bảng Spring Session bằng SQL trong service chỉ để sử dụng manager này. Hãy ưu tiên `SessionRepository` hoặc API Spring Session để tránh phụ thuộc schema nội bộ. Ví dụ `@Transactional` thứ hai chỉ minh họa cách chọn manager cho một phương thức cần thao tác trực tiếp với session database trong trường hợp có chủ đích.

## 7. Transaction manager của session có đồng bộ với transaction nghiệp vụ không?

Đây là điểm cần hiểu rõ nhất khi chọn manager. Transaction manager điều khiển transaction trên tài nguyên mà nó quản lý. Nếu session và nghiệp vụ dùng hai DataSource khác nhau, hai transaction manager tạo ra hai transaction độc lập. Commit ở database nghiệp vụ không tự commit hoặc rollback database session.

Trong luồng Servlet phổ biến:

1. Filter đọc session từ repository trước khi controller xử lý.
2. Service nghiệp vụ mở transaction qua `@Transactional`.
3. Service cập nhật database nghiệp vụ và commit.
4. Request tiếp tục hoàn tất.
5. Spring Session filter lưu thay đổi session qua transaction manager đã chọn cho Spring Session.

Vì save session thường diễn ra ở cuối request, sau khi transaction của service đã hoàn tất, hai thao tác thường không cùng một transaction. Có thể xảy ra tình huống đơn hàng đã commit nhưng việc lưu session thất bại; response có thể lỗi dù giao dịch nghiệp vụ đã thành công. Ngược lại, việc lưu một thuộc tính session không nên được xem là bằng chứng rằng giao dịch nghiệp vụ đã commit.

Nếu session và nghiệp vụ dùng chung một DataSource và cùng transaction manager, các thao tác có thể tham gia cùng transaction khi thực sự được gọi trong cùng transaction context và propagation phù hợp. Nhưng không được suy ra điều đó chỉ từ việc chúng trỏ đến cùng database. Filter lifecycle và thời điểm repository save là yếu tố quyết định.

Nếu cần cập nhật dữ liệu nghiệp vụ và trạng thái quan trọng theo cách nguyên tử, hãy lưu cả hai trong bảng nghiệp vụ thuộc cùng transaction. Session nên giữ dữ liệu giao diện hoặc tham chiếu có thể tái tạo. Nếu thực sự cần giao dịch phân tán giữa hai database, phải thiết kế giải pháp distributed transaction hoặc saga/outbox phù hợp; qualifier không cung cấp chức năng đó.

## 8. Điều gì xảy ra nếu không có bean được đánh dấu?

Hành vi auto-configuration phụ thuộc phiên bản Spring Boot và số lượng bean hiện có. Trong trường hợp chỉ có một transaction manager phù hợp, Boot thường có thể dùng manager duy nhất. Khi có nhiều manager, qualifier chuyên biệt giúp chọn manager cho Spring Session. Nếu không có bean phù hợp hoặc cấu hình nhiều manager mơ hồ, ứng dụng có thể không khởi động, repository có thể không được tạo đúng hoặc manager được chọn không phải manager mong muốn.

Khi chẩn đoán:

- Kiểm tra số bean `PlatformTransactionManager` trong ApplicationContext.
- Ghi nhận tên bean, loại manager và DataSource mà nó quản lý.
- Kiểm tra bean nào mang `@Primary`.
- Kiểm tra bean nào mang `@SpringSessionTransactionManager`.
- Kiểm tra DataSource session có mang `@SpringSessionDataSource` khi có nhiều DataSource.
- Kiểm tra điều kiện auto-configuration và log khởi động của Spring Boot.

Không chỉ nhìn vào tên bean như `transactionManager` hoặc `sessionTransactionManager` để kết luận. Spring chọn theo type, qualifier và điều kiện auto-configuration. Tên bean tự nó không có ý nghĩa đặc biệt nếu không được cấu hình hoặc tham chiếu rõ ràng.

## 9. Cấu hình thủ công ngoài Spring Boot auto-configuration

`@SpringSessionTransactionManager` là tiện ích của Spring Boot. Nếu ứng dụng không dùng Boot auto-configuration hoặc đang cấu hình Spring Session JDBC thủ công, cần tạo và truyền transaction operations/manager vào repository theo API của phiên bản Spring Session đang dùng.

Ở mức khái niệm, repository JDBC cần:

- `JdbcOperations` được kết nối đến session DataSource.
- `TransactionOperations` được tạo từ transaction manager quản lý chính DataSource đó.
- Cấu hình repository và filter Servlet được đăng ký một lần.

Ví dụ tạo `TransactionTemplate` tường minh:

```java
@Bean
TransactionOperations sessionTransactionOperations(
        @SpringSessionTransactionManager
        PlatformTransactionManager sessionTransactionManager) {
    return new TransactionTemplate(sessionTransactionManager);
}
```

Đây là một bean `TransactionOperations` có thể được dùng khi tự cấu hình repository. Cách nối bean này vào constructor hoặc custom configuration của `JdbcIndexedSessionRepository` phụ thuộc phiên bản API Spring Session. Với Spring Boot, thường nên để auto-configuration sử dụng qualifier thay vì tự tạo repository/filter song song.

Nếu dùng cấu hình thuần Spring Session, không giả định annotation Boot sẽ tự chọn manager vì auto-configuration của Boot có thể không tham gia. Khi đó, phải truyền đúng `TransactionOperations` vào repository hoặc dùng cơ chế cấu hình được phiên bản Spring Session cung cấp. Đọc API của phiên bản đang dùng và tránh đăng ký hai `SessionRepositoryFilter`.

## 10. Kiểm thử manager được chọn

Kiểm thử cần xác nhận không chỉ ApplicationContext khởi động thành công mà repository thực sự dùng đúng DataSource/manager.

Một số bước hữu ích:

1. Khởi động context có cả business và session DataSource.
2. Xác nhận `businessTransactionManager` là bean `@Primary` và `sessionTransactionManager` mang `@SpringSessionTransactionManager`.
3. Kiểm tra mỗi manager gắn với đúng DataSource.
4. Tạo session qua HTTP và xác nhận row được ghi vào session database.
5. Thực hiện một transaction nghiệp vụ và xác nhận dữ liệu chỉ xuất hiện trong business database.
6. Tạo lỗi có kiểm soát trong thao tác session hoặc repository test để xác minh rollback thuộc đúng database và không vô tình rollback transaction nghiệp vụ đã commit.
7. Chạy hai instance với cùng session DataSource để xác nhận cả hai đọc/ghi cùng phiên.
8. Kiểm tra startup failure khi cố tình bỏ qualifier hoặc cấu hình bean mơ hồ trong test context, nếu dự án muốn bảo vệ cấu hình bằng test.

Ví dụ kiểm tra metadata của hai DataSource bằng test có thể lấy `Connection` từ từng bean và xác nhận database product/catalog phù hợp. Không log JDBC URL có chứa credential, password hoặc thông tin kết nối nhạy cảm.

Một test có thể kiểm tra qualifier bằng cách truy vấn bean theo annotation hoặc inject theo qualifier:

```java
@Autowired
@SpringSessionTransactionManager
PlatformTransactionManager sessionTransactionManager;

@Autowired
@Qualifier("businessTransactionManager")
PlatformTransactionManager businessTransactionManager;
```

Test này xác nhận bean được đánh dấu có thể được inject. Để xác nhận repository thực sự sử dụng manager đó, cần kiểm tra hành vi ghi session trên đúng database hoặc theo dõi transaction ở integration test.

## 11. Các lỗi thường gặp

- **Đánh dấu sai manager:** session repository có thể chạy transaction trên DataSource nghiệp vụ hoặc không tìm thấy tài nguyên cần thiết.
- **Chỉ đánh dấu DataSource mà quên transaction manager:** khi có nhiều manager, việc chọn manager vẫn có thể mơ hồ hoặc không như dự kiến.
- **Dùng `@Primary` thay cho qualifier chuyên biệt:** manager nghiệp vụ mặc định có thể bị chọn làm manager session dù session database riêng.
- **Cho rằng annotation tạo manager:** bean `PlatformTransactionManager` vẫn phải được khai báo hoặc auto-configure.
- **Cho rằng `@Transactional` nghiệp vụ tự dùng session manager:** annotation này dành cho lựa chọn manager của Spring Session auto-configuration, không thay quy tắc mặc định của service.
- **Cho rằng hai manager trên hai database commit nguyên tử:** cần distributed transaction hoặc thiết kế nghiệp vụ khác; qualifier không đồng bộ commit.
- **Tạo nhiều manager cho cùng DataSource mà không có lý do:** có thể làm transaction resource binding khó hiểu và cấu hình mơ hồ.
- **Chỉ kiểm tra bean mà không kiểm tra repository:** ApplicationContext có bean đúng chưa đủ chứng minh session row được ghi vào đúng database.
- **Dùng annotation Boot trong cấu hình không có Boot auto-configuration:** annotation có thể không được thành phần nào sử dụng; cần cấu hình repository thủ công.

## 12. Checklist triển khai

Trước khi phát hành, xác nhận:

- [ ] Đã xác định số lượng `DataSource` và `PlatformTransactionManager` trong ứng dụng.
- [ ] Khi có một manager, đã tránh tạo bean dư thừa.
- [ ] Khi có nhiều manager, đã đánh dấu manager session bằng `@SpringSessionTransactionManager` nếu phiên bản Boot hỗ trợ.
- [ ] DataSource session được đánh dấu bằng `@SpringSessionDataSource` khi cần chọn riêng.
- [ ] Manager nghiệp vụ mặc định được đánh dấu `@Primary` hoặc được chỉ rõ bằng qualifier.
- [ ] Mỗi transaction manager quản lý đúng DataSource.
- [ ] Đã hiểu transaction lưu session và transaction nghiệp vụ có thể commit ở hai thời điểm khác nhau.
- [ ] Không kỳ vọng annotation cung cấp distributed transaction.
- [ ] Đã kiểm thử session row đi vào đúng database và business row đi vào đúng database.
- [ ] Đã kiểm thử nhiều instance cùng sử dụng session database.
- [ ] Nếu không dùng Boot auto-configuration, repository được cấu hình với `TransactionOperations` đúng và filter chỉ đăng ký một lần.

## 13. Tự kiểm tra kiến thức

Bạn đã hiểu bài học nếu có thể trả lời:

- `@SpringSessionTransactionManager` đánh dấu loại bean nào và phục vụ thành phần nào?
- Vì sao annotation là qualifier chứ không phải một transaction manager?
- Khi nào Spring Boot có thể dùng manager duy nhất mà không cần qualifier chuyên biệt?
- `@Primary` khác `@SpringSessionTransactionManager` như thế nào?
- Vì sao ứng dụng nhiều DataSource nên đánh dấu riêng session DataSource và session transaction manager?
- `@SpringSessionTransactionManager` có làm các service `@Transactional` tự động dùng manager session không?
- Vì sao transaction của session có thể độc lập với transaction nghiệp vụ dù cùng ứng dụng Spring?
- Cần kiểm tra gì để chứng minh session repository đang ghi vào đúng database?

`@SpringSessionTransactionManager` giúp Spring Boot chọn đúng transaction manager cho Spring Session JDBC trong ứng dụng có nhiều manager. Hãy coi nó là một dấu hiệu chọn bean rõ ràng: transaction manager vẫn phải quản lý đúng DataSource, `@Primary` vẫn phục vụ lựa chọn mặc định của ứng dụng và transaction session không tự động trở thành transaction nghiệp vụ. Kiểm thử repository với database thật là bước xác nhận cuối cùng rằng cấu hình đang hoạt động như kiến trúc dự kiến.
