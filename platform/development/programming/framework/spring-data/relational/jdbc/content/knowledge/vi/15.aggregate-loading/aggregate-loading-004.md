# Single Query Loading: mục tiêu và cách kích hoạt

**Single Query Loading** là cơ chế tải aggregate của Spring Data JDBC bằng một câu lệnh SELECT duy nhất, thay vì tải aggregate root trước rồi phát thêm các câu truy vấn riêng để lấy collection entity con. Mục tiêu chính là giảm số lần round-trip giữa ứng dụng và database, đặc biệt khi một truy vấn trả về nhiều aggregate có các collection được sở hữu.

Tính năng này được giới thiệu từ Spring Data JDBC 3.2. Để bật, cần gọi §setSingleQueryLoadingEnabled(true)§ trên §JdbcMappingContext§. Tuy nhiên, bật cờ chỉ cho phép framework thử sử dụng cơ chế này; aggregate, repository method và database dialect vẫn phải đáp ứng các điều kiện hỗ trợ. Nếu không đáp ứng, Spring Data JDBC tự quay về cách tải aggregate mặc định.

Bài học giải thích vấn đề mà Single Query Loading nhắm đến, ý tưởng SQL phía sau, cách cấu hình mapping context, các giới hạn cần biết và cách quan sát hiệu quả trong ứng dụng.

## 1. Bài toán tải aggregate trong Spring Data JDBC

Spring Data JDBC làm việc với **aggregate**: một aggregate root và các entity được sở hữu bên trong nó. Khi ứng dụng đọc aggregate, mục tiêu ở mức domain là nhận được root cùng các thành phần thuộc aggregate theo đúng mô hình.

Ví dụ một đơn hàng có nhiều dòng hàng:

§§§text
PurchaseOrder aggregate
┌──────────────────────────────┐
│ PurchaseOrder                │
│ id = 501                     │
│ status = "CONFIRMED"         │
│                              │
│ lines                        │
│   ├── OrderLine A            │
│   ├── OrderLine B            │
│   └── OrderLine C            │
└──────────────────────────────┘
§§§

Mã nghiệp vụ có thể gọi:

§§§java
PurchaseOrder order = orderRepository.findById(501L)
        .orElseThrow();
§§§

Khi đó, ứng dụng mong muốn có một object hoàn chỉnh để dùng các dòng hàng. Nhưng **một lời gọi repository không nhất thiết tương ứng với một câu SQL**. Với cách tải truyền thống, Spring Data JDBC có thể thực hiện truy vấn root trước, rồi truy vấn các entity con bằng những câu lệnh riêng.

Với một aggregate có collection:

§§§sql
SELECT id, status
FROM purchase_orders
WHERE id = ?;

SELECT order_id, line_position, sku, quantity
FROM order_lines
WHERE order_id = ?;
§§§

Với một aggregate đơn lẻ, hai câu truy vấn như trên có thể hoàn toàn chấp nhận được. Vấn đề rõ hơn khi ứng dụng tải nhiều aggregate cùng lúc.

## 2. N+1 query xuất hiện như thế nào?

Giả sử màn hình quản trị cần tải 100 đơn hàng, mỗi đơn hàng có collection §lines§. Cách tải truyền thống có thể hoạt động theo mô hình:

1. Chạy một câu §SELECT§ để lấy 100 hàng §purchase_orders§.
2. Với mỗi đơn hàng, chạy thêm một câu §SELECT§ để lấy các dòng hàng thuộc đơn đó.

Số câu truy vấn:

§§§text
1 câu truy vấn lấy 100 aggregate roots
+
100 câu truy vấn lấy collection của từng root
=
101 câu truy vấn
§§§

Đây là dạng **N+1 query problem**: một câu truy vấn ban đầu cộng với N câu truy vấn phát sinh theo số lượng root.

Nếu aggregate có nhiều collection ở cùng cấp, mỗi root có thể cần truy vấn riêng cho từng collection. Ví dụ một §Minion§ có danh sách §toys§ và §hobbies§:

§§§text
SELECT * FROM minions;

Với mỗi Minion:
    SELECT * FROM toys WHERE minion_id = ?;
    SELECT * FROM hobbies WHERE minion_id = ?;
§§§

Nếu tải N minion với hai collection, số truy vấn theo cách này có thể là §1 + 2N§. Khi N tăng, số lần trao đổi giữa ứng dụng và database cũng tăng theo.

### 2.1. Vì sao N+1 tốn kém?

Chi phí không chỉ nằm ở thời gian database thực thi câu SQL:

- Mỗi câu truy vấn cần gửi qua kết nối JDBC và nhận kết quả.
- Mỗi lần round-trip có độ trễ mạng/driver.
- Database phải xử lý nhiều lần chuẩn bị, thực thi và trả kết quả.
- Connection pool và thread của ứng dụng có thể bị chiếm dụng lâu hơn.
- Khi tải nhiều aggregate, chi phí tăng theo số root thay vì chỉ theo số lượng dữ liệu cần trả về.

Ngay cả khi từng câu truy vấn chạy nhanh, tổng thời gian của hàng trăm lần round-trip có thể đáng kể.

### 2.2. Một repository call không đồng nghĩa một SQL statement

Cần phân biệt hai cấp độ:

| Cấp độ | Ý nghĩa |
| --- | --- |
| **Repository call** | Một lời gọi Java như §findAll()§ hoặc §findById(id)§. |
| **SQL statement** | Một câu lệnh thực sự được gửi đến database. |

Cách tải truyền thống có thể dùng nhiều SQL statement bên trong một repository call. Single Query Loading thay đổi cách framework tạo câu lệnh đọc để tải aggregate phù hợp trong một SELECT.

## 3. Mục tiêu của Single Query Loading

Single Query Loading cố gắng tải **nhiều aggregate hoàn chỉnh trong một câu SQL**, bao gồm root và các entity con được hỗ trợ, giảm số lần round-trip.

Ví dụ tải 100 đơn hàng:

§§§text
Cách tải truyền thống:
    SELECT purchase_orders ...          (1 lần)
    SELECT order_lines WHERE order_id=? (lặp theo từng order)
    SELECT order_lines WHERE order_id=?
    ...
    SELECT order_lines WHERE order_id=?

Single Query Loading:
    SELECT ... root + child collections ...  (1 lần)
§§§

Điều này đặc biệt hữu ích khi:

- Một repository method tải nhiều aggregate.
- Mỗi aggregate có collection entity được sở hữu.
- Số lượng aggregate đủ lớn để round-trip trở thành chi phí đáng kể.
- Database hỗ trợ các analytic/window functions cần thiết.
- Mô hình aggregate và phương thức truy vấn nằm trong phạm vi tính năng hỗ trợ.

Single Query Loading tập trung vào **đọc dữ liệu**. Nó không thay đổi cách insert, update hoặc delete aggregate, cũng không biến một aggregate thành một truy vấn nghiệp vụ tùy ý.

### 3.1. Không phải mọi trường hợp đều cần Single Query Loading

Nếu ứng dụng chỉ tải một aggregate có một collection nhỏ, cách tải mặc định có thể đủ nhanh và đơn giản. Nếu truy vấn chỉ lấy root mà không cần collection, lợi ích của việc gộp tải collection không đáng kể.

Mục tiêu không phải giảm số SQL bằng mọi giá. Mục tiêu là giảm chi phí truy cập dữ liệu trong những luồng tải aggregate mà N+1 thực sự ảnh hưởng đến hiệu năng.

## 4. Vì sao không chỉ JOIN tất cả collection?

Một cách nghĩ tự nhiên là dùng một câu SQL với nhiều §JOIN§:

§§§sql
SELECT *
FROM minions m
LEFT JOIN toys t ON t.minion_id = m.id
LEFT JOIN hobbies h ON h.minion_id = m.id;
§§§

Cách này có thể tạo **tích Descartes giữa các collection** của cùng một root.

Giả sử một minion có:

- 2 toy.
- 3 hobby.

Khi join đồng thời hai collection, kết quả có thể có §2 × 3 = 6§ hàng cho cùng minion:

§§§text
Minion  Toy          Hobby
------  -----------  ----------------
1       Teddy        Hold Teddy
1       Blue Light   Hold Teddy
1       Teddy        Look Cute
1       Blue Light   Look Cute
1       Teddy        Follow Kevin
1       Blue Light   Follow Kevin
§§§

Khi collection lớn hơn, số hàng lặp tăng nhanh. Với 5 collection, mỗi collection có 10 phần tử, join ngây thơ có thể tạo ra §10 × 10 × 10 × 10 × 10 = 100.000§ tổ hợp cho một root, dù dữ liệu thực chỉ có 50 phần tử con.

Điều đó làm tăng:

- Số hàng database phải tạo và trả về.
- Dữ liệu root và child bị lặp trên đường truyền.
- Công việc ánh xạ và loại bỏ dữ liệu trùng ở ứng dụng.
- Bộ nhớ và thời gian xử lý kết quả.

Single Query Loading dùng một kỹ thuật khác để ghép các collection mà không cần tạo toàn bộ tích Descartes này.

## 5. Ý tưởng kỹ thuật: window functions và row number

Single Query Loading sử dụng **analytic functions**, còn gọi là **window functions**, mà database hỗ trợ. Một ví dụ quan trọng là §ROW_NUMBER() OVER (PARTITION BY ...)§.

Window function tính toán trên một nhóm hàng nhưng vẫn giữ từng hàng trong kết quả. Với collection con, framework có thể đánh số vị trí của từng phần tử trong phạm vi root sở hữu nó.

Ví dụ bảng §toys§:

§§§sql
SELECT
    minion_id,
    name,
    ROW_NUMBER() OVER (
        PARTITION BY minion_id
        ORDER BY id
    ) AS toy_row
FROM toys;
§§§

Kết quả khái niệm:

§§§text
minion_id | name       | toy_row
----------+------------+--------
1         | Teddy      | 1
1         | Blue Light | 2
2         | ...        | 1
§§§

Tương tự với §hobbies§:

§§§sql
SELECT
    minion_id,
    name,
    ROW_NUMBER() OVER (
        PARTITION BY minion_id
        ORDER BY id
    ) AS hobby_row
FROM hobbies;
§§§

Kết quả:

§§§text
minion_id | name        | hobby_row
----------+-------------+----------
1         | Hold Teddy  | 1
1         | Look Cute   | 2
1         | Follow Kevin| 3
2         | ...         | 1
§§§

Framework có thể ghép các tập con theo root ID và số thứ tự hàng, thay vì ghép mọi phần tử toy với mọi phần tử hobby. Thuật toán thực tế còn xử lý trường hợp collection rỗng và các cột không có giá trị tương ứng để tái tạo cấu trúc aggregate chính xác.

Kết quả mong muốn có dạng:

§§§text
Minion id | Toy          | Hobby
----------+--------------+----------------
1         | Teddy        | Hold Teddy
1         | Blue Light   | Look Cute
1         |              | Follow Kevin
2         | ...          | ...
§§§

Thay vì 6 hàng tích Descartes ở ví dụ trước, kết quả có thể biểu diễn các phần tử theo các vị trí tương ứng mà không nhân chéo toàn bộ collection.

### 5.1. Vì sao cần row number?

Database trả về một bảng phẳng, trong khi Java cần một object graph có root và các collection. Số thứ tự giúp xác định phần tử nào thuộc vị trí nào trong từng collection.

Về khái niệm:

- Root có một hàng đại diện.
- Mỗi collection có số thứ tự riêng trong phạm vi root.
- Các collection được căn chỉnh theo số thứ tự để tạo một tập kết quả phẳng.
- Mapper đọc tập kết quả và dựng lại object aggregate cùng các collection.

Đây là cách biến dữ liệu quan hệ thành cấu trúc aggregate trong một lần đọc kết quả.

**Lưu ý:** các câu SQL trên chỉ minh họa ý tưởng window function. Spring Data JDBC tự tạo câu SQL Single Query Loading; ứng dụng không cần tự viết các subquery, row number hay join phức tạp này.

## 6. Điều kiện và giới hạn hỗ trợ

Bật Single Query Loading không có nghĩa mọi aggregate và mọi repository method đều tự động dùng một câu truy vấn. Theo tài liệu Spring Data Relational 4.1.2, cần chú ý các điều kiện sau:

| Điều kiện | Phạm vi hỗ trợ hiện được tài liệu nêu |
| --- | --- |
| Phiên bản | Có từ Spring Data JDBC 3.2. |
| Kiểu aggregate | Không có nested collections; giới hạn này bao gồm cả §Map§ lồng nhau. |
| Embedded entity | Aggregate không sử dụng embedded entities. |
| AggregateReference | Aggregate không sử dụng §AggregateReference§. |
| Database dialect | Dialect phải hỗ trợ các analytic/window functions cần thiết. |
| H2 và HSQL | Các dialect này không hỗ trợ Single Query Loading theo tài liệu Spring Data JDBC hiện tại. |
| Repository methods | Chỉ các phương thức find của §CrudRepository§. |
| Derived query | Chưa nằm trong phạm vi Single Query Loading. |
| Annotated query | Các phương thức dùng §@Query§ chưa nằm trong phạm vi Single Query Loading. |
| Cấu hình | Phải bật trên §JdbcMappingContext§ bằng §setSingleQueryLoadingEnabled(true)§. |

Tài liệu cũng nêu rõ: nếu một trong các điều kiện không thỏa mãn, Spring Data JDBC **fallback về cách tải aggregate mặc định**. Vì vậy, việc ứng dụng vẫn chạy không chứng minh Single Query Loading đã được sử dụng.

### 6.1. Nested collection khác nhiều collection ở cùng cấp

Ví dụ có hai collection trực tiếp dưới root:

§§§text
Order
  ├── lines[]
  └── notes[]
§§§

Đây là các collection cùng cấp.

Ví dụ có collection lồng bên trong phần tử con:

§§§text
Order
  └── lines[]
        └── adjustments[]
§§§

Đây là nested collection. Tài liệu hiện tại liệt kê nested collections là giới hạn của Single Query Loading. Không nên suy luận rằng cứ có nhiều collection là không được hỗ trợ; cần xét cấu trúc aggregate cụ thể và các giới hạn được công bố.

### 6.2. AggregateReference và embedded entity

Ví dụ aggregate có tham chiếu khác:

§§§java
@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        AggregateReference<Customer, Long> customer,
        String status
) {
}
§§§

Hoặc embedded entity:

§§§java
@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        @Embedded(prefix = "delivery_")
        DeliveryAddress deliveryAddress
) {
}
§§§

Các kiểu aggregate này nằm ngoài điều kiện Single Query Loading được tài liệu 4.1.2 nêu. Khi dùng chúng, hãy dự kiến cơ chế tải mặc định sẽ được sử dụng.

### 6.3. Database dialect phải hỗ trợ

Spring Data JDBC dùng dialect để biết cách tạo SQL phù hợp với database. Single Query Loading cần analytic/window functions; không phải mọi dialect đều hỗ trợ cơ chế này trong Spring Data JDBC.

Tài liệu Spring Data Relational 4.1.2 nêu các dialect được cung cấp đều hỗ trợ, ngoại trừ H2 và HSQL. Vì vậy, nếu chạy test bằng H2 nhưng production dùng PostgreSQL, kết quả quan sát số câu SQL ở test có thể khác production.

Không nên kết luận rằng tính năng không hoạt động trên mọi database chỉ vì test H2 fallback về cách tải mặc định.

### 6.4. Phương thức repository phải nằm trong phạm vi hỗ trợ

Ví dụ các thao tác find từ §CrudRepository§:

§§§java
public interface MinionRepository
        extends CrudRepository<Minion, Long> {
}
§§§

Các phương thức như §findById§, §findAll§ và §findAllById§ thuộc nhóm find methods của §CrudRepository§.

Một truy vấn suy diễn:

§§§java
List<Minion> findByName(String name);
§§§

hoặc truy vấn gắn §@Query§:

§§§java
@Query("SELECT * FROM minions WHERE name = :name")
List<Minion> findNamed(@Param("name") String name);
§§§

không nằm trong phạm vi Single Query Loading được tài liệu hiện tại nêu. Những phương thức này vẫn có thể tải aggregate theo cách mặc định, kể cả khi mapping context đã bật cờ.

## 7. Cách kích hoạt Single Query Loading

Single Query Loading được bật qua §JdbcMappingContext§ bằng phương thức:

§§§java
mappingContext.setSingleQueryLoadingEnabled(true);
§§§

§JdbcMappingContext§ kế thừa §RelationalMappingContext§. Phương thức này đặt cờ để Spring Data JDBC thử dùng Single Query Loading khi dialect và aggregate hỗ trợ.

Đây không phải một thuộc tính cấu hình datasource như §spring.datasource.url§. Tài liệu hướng dẫn bật tính năng bằng API của mapping context, nên cần cấu hình bean đúng cách.

### 7.1. Cấu hình bằng AbstractJdbcConfiguration

Một cách tùy biến infrastructure là kế thừa §AbstractJdbcConfiguration§ và override bean §jdbcMappingContext§. Ví dụ dưới đây theo API Spring Data Relational 3.3.x/4.x với ba tham số của phương thức cấu hình:

§§§java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.data.jdbc.core.convert.JdbcCustomConversions;
import org.springframework.data.jdbc.core.mapping.JdbcMappingContext;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;
import org.springframework.data.relational.RelationalManagedTypes;
import org.springframework.data.relational.core.mapping.NamingStrategy;

@Configuration
public class SingleQueryLoadingJdbcConfiguration
        extends AbstractJdbcConfiguration {

    @Override
    @Bean
    public JdbcMappingContext jdbcMappingContext(
            Optional<NamingStrategy> namingStrategy,
            JdbcCustomConversions customConversions,
            RelationalManagedTypes jdbcManagedTypes
    ) {
        JdbcMappingContext context = super.jdbcMappingContext(
                namingStrategy,
                customConversions,
                jdbcManagedTypes
        );

        context.setSingleQueryLoadingEnabled(true);

        return context;
    }
}
§§§

Giải thích:

1. §AbstractJdbcConfiguration§ cung cấp các bean hạ tầng cần thiết cho Spring Data JDBC.
2. Phương thức §jdbcMappingContext§ tạo mapping context cùng naming strategy, custom conversions và managed types.
3. Gọi §super.jdbcMappingContext(...)§ để giữ cấu hình mặc định của Spring Data JDBC.
4. Gọi §setSingleQueryLoadingEnabled(true)§ trên chính context đó.
5. Trả về context đã được bật cờ để converter và repository dùng chung.

**Điểm quan trọng:** phải tùy biến §JdbcMappingContext§ mà hạ tầng JDBC đang sử dụng. Không tạo thêm một mapping context độc lập rồi gọi setter trên nó, vì repository có thể vẫn đang dùng bean context khác.

Nếu ứng dụng đã có một lớp kế thừa §AbstractJdbcConfiguration§, hãy thêm phần override vào lớp cấu hình hiện tại. Tránh khai báo hai bean §JdbcMappingContext§ cạnh tranh nhau. Với cấu hình Spring Boot, cần giữ cho repository infrastructure và converter cùng dùng một mapping context đã được tùy biến. Nếu dùng Spring Data JDBC không qua Spring Boot, vẫn cần cấu hình việc bật repositories theo cách ứng dụng đang sử dụng, chẳng hạn §@EnableJdbcRepositories§.

### 7.2. Vì sao gọi super trước khi bật cờ?

Phương thức cấu hình của lớp cha tạo mapping context dựa trên các dependency được Spring Data JDBC quản lý:

- §NamingStrategy§ để xác định tên bảng/cột.
- §JdbcCustomConversions§ để đăng ký chuyển đổi kiểu.
- §RelationalManagedTypes§ để cung cấp các kiểu được quản lý/phát hiện.

Nếu tự tạo §new JdbcMappingContext()§ một cách tùy tiện, bạn có thể bỏ qua những cấu hình này. Gọi §super.jdbcMappingContext(...)§ giữ lại cơ chế khởi tạo chuẩn rồi chỉ thay đổi cờ Single Query Loading.

### 7.3. Nếu đã có JdbcMappingContext bean tùy chỉnh

Nếu ứng dụng tự khai báo bean §JdbcMappingContext§ ở nơi khác, hãy thêm setter vào bean hiện có:

§§§java
JdbcMappingContext context = ...; // context đã được cấu hình đúng
context.setSingleQueryLoadingEnabled(true);
return context;
§§§

Nguyên tắc vẫn là **chỉ cấu hình context được sử dụng thực sự**. Không tạo hai bean cùng kiểu và hy vọng Spring Data tự chọn đúng bean.

## 8. Ví dụ aggregate phù hợp để thử nghiệm

Để quan sát Single Query Loading, hãy dùng một aggregate đơn giản có root và một collection trực tiếp, không có nested collection, embedded entity hay AggregateReference.

Ví dụ bảng minion và hobby:

§§§sql
CREATE TABLE minions (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE hobbies (
    minion_id BIGINT NOT NULL REFERENCES minions(id),
    hobby_position INTEGER NOT NULL,
    name VARCHAR(150) NOT NULL,
    PRIMARY KEY (minion_id, hobby_position)
);
§§§

Aggregate root:

§§§java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("minions")
public record Minion(
        @Id Long id,
        String name,

        @MappedCollection(
                idColumn = "minion_id",
                keyColumn = "hobby_position"
        )
        List<Hobby> hobbies
) {
}
§§§

Entity con:

§§§java
import org.springframework.data.relational.core.mapping.Table;

@Table("hobbies")
public record Hobby(String name) {
}
§§§

Repository:

§§§java
import org.springframework.data.repository.CrudRepository;

public interface MinionRepository
        extends CrudRepository<Minion, Long> {
}
§§§

Thử tải nhiều aggregate:

§§§java
List<Minion> minions = StreamSupport
        .stream(minionRepository.findAll().spliterator(), false)
        .toList();
§§§

Hoặc tải theo ID:

§§§java
Minion minion = minionRepository.findById(1L)
        .orElseThrow();
§§§

Khi Single Query Loading được bật và điều kiện được đáp ứng, Spring Data JDBC có thể dùng một SELECT để tải root cùng collection. Khi không đáp ứng điều kiện, framework tự fallback sang cách tải mặc định.

Ví dụ này chỉ minh họa mô hình phù hợp; để xác nhận cơ chế đang hoạt động, cần quan sát SQL thực tế chứ không chỉ nhìn kết quả Java.

## 9. Quan sát Single Query Loading có thực sự được dùng không

Sau khi bật cấu hình, hãy kiểm tra bằng dữ liệu có nhiều aggregate và nhiều entity con. Nếu chỉ có một root hoặc collection rỗng, số câu SQL có thể chưa thể hiện rõ lợi ích.

### 9.1. Chuẩn bị dữ liệu thử

Ví dụ:

- 50 minion.
- Mỗi minion có 5 hobby.
- Gọi §findAll()§ để tải toàn bộ aggregate.

Với cách tải truyền thống, có thể quan sát một câu lấy root cộng nhiều câu lấy collection theo từng root. Với Single Query Loading, mục tiêu là tải các aggregate phù hợp trong một câu SELECT.

### 9.2. Kiểm tra số câu truy vấn

Có thể dùng công cụ theo dõi SQL như datasource-proxy, P6Spy hoặc logging JDBC trong môi trường phát triển để đếm số statement.

Khi kiểm tra, hãy phân biệt:

- Câu SQL đọc root.
- Câu SQL đọc collection.
- Câu truy vấn do một service khác phát sinh trong cùng request.
- Câu SQL của migration, health check hoặc transaction metadata.

Chỉ so sánh các statement thuộc thao tác tải aggregate đang thử.

### 9.3. So sánh cùng điều kiện

Một phép đo có ý nghĩa nên giữ nguyên:

- Cùng database và phiên bản.
- Cùng dữ liệu.
- Cùng repository method.
- Cùng số lượng aggregate.
- Cùng kích thước collection.
- Cùng trạng thái cache và connection pool.
- Cùng cách đo thời gian.

Theo dõi ít nhất:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Số SQL statements | Có giảm số lần round-trip không? |
| Tổng thời gian | Tốc độ toàn thao tác có tốt hơn không? |
| Số hàng kết quả | Query có trả quá nhiều hàng không? |
| Dữ liệu truyền về | Có lặp nhiều cột hoặc dữ liệu lớn không? |
| CPU database | Query mới có tốn thêm xử lý window function không? |
| CPU và heap ứng dụng | Mapping result set có tạo thêm áp lực bộ nhớ không? |

### 9.4. Không suy luận chỉ từ số lượng câu SQL

Một câu SQL phức tạp có thể tốn thời gian hơn vài câu truy vấn nhỏ trong một số workload. Single Query Loading giảm round-trip, nhưng không bảo đảm mọi ứng dụng đều nhanh hơn trong mọi trường hợp.

Hãy xem execution plan, lượng dữ liệu, số hàng kết quả và thời gian thực tế. Nếu aggregate rất lớn hoặc query tải quá nhiều dữ liệu không cần thiết, việc giảm số statement có thể không đủ để cải thiện tổng thể.

## 10. Fallback hoạt động ra sao?

Một điểm hữu ích của cơ chế này là framework có thể tự quay về cách tải mặc định khi không thể dùng Single Query Loading.

Ví dụ:

| Tình huống | Kết quả dự kiến |
| --- | --- |
| Cờ chưa bật | Dùng cách tải aggregate mặc định. |
| Cờ bật, dialect hỗ trợ, aggregate phù hợp và dùng CrudRepository find method | Thử dùng Single Query Loading. |
| Cờ bật nhưng database dialect không hỗ trợ | Fallback về cách tải mặc định. |
| Aggregate có nested collection | Fallback về cách tải mặc định. |
| Aggregate dùng AggregateReference hoặc embedded entity | Fallback về cách tải mặc định. |
| Dùng derived query | Không dùng Single Query Loading; tải theo cách mặc định. |
| Dùng method có @Query | Không dùng Single Query Loading; tải theo cách mặc định. |

Fallback giúp ứng dụng vẫn có thể tải aggregate theo cơ chế truyền thống. Tuy nhiên, nó cũng có nghĩa **không thể dùng việc ứng dụng chạy thành công làm bằng chứng rằng Single Query Loading đã được kích hoạt thực tế**.

## 11. Những nhầm lẫn thường gặp

**“Một lần gọi findAll luôn chỉ tạo một câu SQL.”** Không đúng. Repository call có thể phát nhiều SQL statement để tải root và collection. Single Query Loading là cơ chế giúp giảm các statement này trong phạm vi hỗ trợ.

**“Bật setSingleQueryLoadingEnabled(true) là mọi query đều chạy một câu.”** Không đúng. Dialect, cấu trúc aggregate và loại repository method đều phải phù hợp.

**“Single Query Loading là tính năng của database.”** Không hẳn. Database cung cấp window functions; Spring Data JDBC tạo SQL và ánh xạ kết quả theo cơ chế Single Query Loading.

**“Chỉ cần JOIN mọi collection vào root.”** Không đúng. JOIN nhiều collection có thể tạo tích Descartes và nhân số hàng. Single Query Loading sử dụng window functions để căn chỉnh collection.

**“Single Query Loading thay thế @Query.”** Không đúng. Đây là cơ chế tải aggregate tự động cho các find methods được hỗ trợ; các query tùy chỉnh vẫn là một phạm vi riêng.

**“Nếu dùng H2 test thì có thể đánh giá đầy đủ tính năng.”** Không đúng theo dialect support hiện tại trong tài liệu Spring Data JDBC. H2/HSQL không nằm trong danh sách dialect hỗ trợ Single Query Loading; cần kiểm tra trên database tương thích với production.

**“Tính năng này ảnh hưởng đến save và delete.”** Không đúng. Single Query Loading tập trung vào tải/đọc aggregate; các thao tác ghi có cơ chế riêng.

**“Một aggregate có hai collection trực tiếp chắc chắn là nested collection.”** Không đúng. Nested collection là collection nằm bên trong một collection/entity con. Hai collection cùng là property trực tiếp của root không phải cùng một cấu trúc với collection lồng nhau; tuy nhiên vẫn cần kiểm tra các giới hạn khác.

**“Không thấy query count giảm nghĩa là setter không hoạt động.”** Chưa thể kết luận. Có thể method đang dùng không được hỗ trợ, aggregate có cấu trúc không tương thích, dialect fallback hoặc logging đang đếm cả truy vấn khác.

**“Một query luôn nhanh hơn nhiều query.”** Không đúng. Cần đo thời gian, execution plan, số hàng và lượng dữ liệu truyền về trong workload thực tế.

## 12. Quy trình bật và đánh giá trong dự án

Có thể triển khai theo các bước sau:

1. **Kiểm tra phiên bản Spring Data JDBC:** tính năng có từ 3.2; phiên bản phải có API §setSingleQueryLoadingEnabled§.
2. **Xác định database dialect:** kiểm tra dialect của database thực tế có hỗ trợ window functions theo Spring Data JDBC hay không.
3. **Chọn aggregate phù hợp:** tránh nested collections, embedded entities và AggregateReference trong aggregate được thử.
4. **Chọn repository method:** bắt đầu bằng §CrudRepository.findAll()§, §findById()§ hoặc find method được tài liệu hỗ trợ.
5. **Bật cờ trên JdbcMappingContext:** override bean trong §AbstractJdbcConfiguration§ hoặc tùy biến bean context hiện có.
6. **Chuẩn bị dữ liệu đủ lớn:** nhiều aggregate và collection có phần tử để thấy khác biệt về số statement.
7. **Quan sát SQL:** đếm statement và kiểm tra câu SELECT được sinh.
8. **Đo hiệu năng:** so sánh thời gian, execution plan, số hàng và dữ liệu truyền.
9. **Kiểm tra fallback:** thử một method hoặc aggregate ngoài phạm vi hỗ trợ để hiểu hành vi mặc định.
10. **Quyết định theo kết quả:** chỉ giữ cấu hình nếu workload thực tế có lợi và nhóm vận hành hiểu giới hạn của tính năng.

§§§mermaid
flowchart TD
    A["Có nhu cầu giảm round-trip khi tải aggregate"] --> B{"Spring Data JDBC >= 3.2?"}
    B -->|No| C["Không có Single Query Loading"]
    B -->|Yes| D{"Dialect hỗ trợ window functions?"}
    D -->|No| E["Dùng cách tải mặc định"]
    D -->|Yes| F{"Aggregate không có nested collection,<br/>AggregateReference hoặc embedded entity?"}
    F -->|No| E
    F -->|Yes| G{"Dùng find method của CrudRepository?"}
    G -->|No| E
    G -->|Yes| H["Bật JdbcMappingContext"]
    H --> I["Quan sát SQL và đo workload"]
    I --> J{"Hiệu quả thực tế?"}
    J -->|Có| K["Giữ cấu hình và theo dõi"]
    J -->|Không| L["Đánh giá lại query/model/index"]
§§§

## 13. Câu hỏi tự luyện

1. Vì sao một lời gọi §findAll()§ có thể tạo nhiều SQL statement trong Spring Data JDBC?
2. N+1 query problem xuất hiện thế nào khi tải N aggregate có một collection?
3. Vì sao join đồng thời hai collection có thể tạo tích Descartes?
4. Window function §ROW_NUMBER() OVER (PARTITION BY ...)§ giúp Single Query Loading ghép các collection ra sao?
5. Single Query Loading được giới thiệu từ phiên bản Spring Data JDBC nào?
6. Cần gọi phương thức nào trên §JdbcMappingContext§ để kích hoạt?
7. Vì sao phải cấu hình đúng bean mapping context đang được converter và repository sử dụng?
8. Những trường hợp aggregate nào hiện không tương thích theo tài liệu Spring Data Relational 4.1.2?
9. Vì sao H2/HSQL không phải môi trường phù hợp để xác minh tính năng theo dialect support hiện tại?
10. Vì sao một phương thức repository có §@Query§ không mặc nhiên sử dụng Single Query Loading?
11. Nếu cờ đã bật nhưng aggregate không phù hợp, framework làm gì?
12. Một câu SQL duy nhất có luôn nhanh hơn nhiều câu SQL nhỏ không? Cần đo những chỉ số nào?

### Bài tập thực hành

Tạo một aggregate §Minion§ với collection §hobbies§ như ví dụ:

1. Tạo 50 minion, mỗi minion có 5 hobby.
2. Chạy §findAll()§ khi Single Query Loading chưa bật và đếm SQL statement.
3. Bật §setSingleQueryLoadingEnabled(true)§ trong mapping context.
4. Chạy lại cùng repository method với cùng dữ liệu và database hỗ trợ.
5. So sánh số statement, thời gian và số hàng kết quả.
6. Thêm một nested collection vào mô hình thử nghiệm hoặc chuyển sang method dùng §@Query§.
7. Quan sát cơ chế fallback và giải thích vì sao kết quả không còn sử dụng Single Query Loading.
8. Chạy lại trên database dùng ở production để tránh kết luận dựa trên một dialect không hỗ trợ.

## 14. Ghi nhớ

- Single Query Loading được giới thiệu từ Spring Data JDBC 3.2 để tải nhiều aggregate trong một SELECT, giảm round-trip và hạn chế N+1 khi tải collection.
- Cơ chế dùng analytic/window functions, đặc biệt là row numbering, để ghép các collection vào kết quả phẳng mà tránh tích Descartes của JOIN ngây thơ.
- Bật bằng §JdbcMappingContext.setSingleQueryLoadingEnabled(true)§.
- Khi tùy biến, cần cấu hình đúng §JdbcMappingContext§ mà Spring Data JDBC thực sự sử dụng; không tạo context phụ.
- Theo tài liệu Spring Data Relational 4.1.2, aggregate không được có nested collections (bao gồm Map), AggregateReference hoặc embedded entities; dialect phải hỗ trợ; method phải thuộc nhóm find của §CrudRepository§.
- Derived queries và annotated queries không nằm trong phạm vi hiện tại được tài liệu nêu.
- Dialect H2 và HSQL không hỗ trợ Single Query Loading theo tài liệu Spring Data JDBC hiện tại.
- Nếu một điều kiện không đáp ứng, framework fallback về cách tải aggregate mặc định.
- Single Query Loading là tính năng được tài liệu đánh dấu experimental; cần đo workload thực tế trước khi quyết định sử dụng.
- Tính năng này ảnh hưởng đến tải dữ liệu, không thay đổi cơ chế insert, update hoặc delete.

Khi hiểu rõ Single Query Loading, bạn có thể nhận diện lúc nào một repository call đang tạo N+1, biết cách bật đúng mapping context và kiểm tra xem database có thực sự sử dụng cơ chế tải một câu truy vấn hay không. **Mục tiêu là giảm chi phí đọc aggregate trong workload phù hợp, đồng thời giữ đúng giới hạn của mapping và dialect.**

## Tài liệu tham khảo

- [Spring Data Relational — Persisting Entities / Loading Aggregates](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Data Relational — RelationalMappingContext API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/RelationalMappingContext.html)
- [Spring Blog — Introducing Single Query Loading](https://spring.io/blog/2023/08/31/this-is-the-beginning-of-the-end-of-the-n-1-problem-introducing-single-query/)

