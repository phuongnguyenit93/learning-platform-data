# Dialect và ranh giới giữa chức năng chung với khả năng riêng của cơ sở dữ liệu

Spring Data Relational cung cấp một mô hình lập trình tương đối thống nhất để ánh xạ đối tượng Java với dữ liệu quan hệ. Tuy nhiên, mỗi hệ quản trị cơ sở dữ liệu (database) có cú pháp SQL, kiểu dữ liệu và tính năng riêng. Một câu lệnh hợp lệ trên PostgreSQL chưa chắc chạy được trên MySQL hoặc SQL Server. Cách đánh dấu tham số, phân trang, khóa bản ghi và trả về khóa sinh tự động cũng có thể khác nhau.

Spring Data giải quyết một phần khác biệt đó bằng **dialect**. Dialect mô tả cho framework những quy tắc và khả năng SQL đặc thù mà framework cần biết khi tạo câu lệnh. Nó giúp các thao tác được hỗ trợ hoạt động trên nhiều hệ quản trị cơ sở dữ liệu mà không phải viết lại toàn bộ repository cho từng loại database.

Tuy nhiên, dialect không biến mọi database thành một hệ thống có cùng ngữ nghĩa. Nó không phải bộ chuyển đổi có thể tự động làm cho mọi câu SQL, kiểu dữ liệu, hàm hoặc tính năng độc quyền trở nên portable. Để thiết kế đúng, cần biết phần nào do Spring Data cung cấp chung, phần nào do dialect mô tả, phần nào thuộc R2DBC driver và phần nào chỉ database mới quyết định.

## 1. Dialect là gì?

Trong ngữ cảnh truy cập dữ liệu quan hệ, **dialect** là tập hợp quy tắc mô tả cách một framework nên tạo hoặc xử lý SQL cho một hệ quản trị cơ sở dữ liệu cụ thể. Mỗi database có thể triển khai cùng một ý tưởng SQL theo cú pháp hoặc quy tắc khác nhau. Dialect cung cấp thông tin để framework thích nghi với những khác biệt đã được hỗ trợ.

Ví dụ, một repository có thể yêu cầu lấy một nhóm bản ghi theo thứ tự và giới hạn số dòng. Về mặt nghiệp vụ, yêu cầu đó giống nhau ở mọi database. Nhưng câu SQL biểu diễn giới hạn và offset có thể khác nhau:

~~~sql
-- Một dạng thường gặp trên PostgreSQL và MySQL
SELECT id, name
FROM customer
ORDER BY id
LIMIT 20 OFFSET 40;
~~~

~~~sql
-- SQL Server dùng cú pháp OFFSET/FETCH
SELECT id, name
FROM customer
ORDER BY id
OFFSET 40 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

SQL Server yêu cầu ORDER BY khi dùng OFFSET/FETCH. Khác biệt này không chỉ là thay tên một từ khóa; câu SQL còn phải đáp ứng quy tắc của database đích.

Spring Data có thể dùng dialect để tạo phần SQL phân trang phù hợp trong những API mà module hỗ trợ. Lập trình viên nhờ đó có thể làm việc ở mức repository hoặc abstraction chung mà không phải tự ghép cú pháp phân trang cho từng database.

Trong hệ sinh thái Spring Data Relational, dialect là một abstraction ở tầng framework. Với R2DBC, abstraction dành cho truy cập quan hệ reactive được biểu diễn bằng **R2dbcDialect**. Dialect được dùng trong quá trình xây dựng SQL và mapping ở những điểm có khác biệt theo nhà cung cấp database.

## 2. Dialect nằm ở đâu trong kiến trúc?

Một luồng truy cập dữ liệu điển hình có thể hình dung như sau:

~~~text
Ứng dụng
   |
   v
Repository / DatabaseClient / Spring Data Relational
   |
   +---- Mapping metadata, entity, aggregate, query
   |
   +---- Dialect
   |       Quy tắc SQL, bind marker, identifier,
   |       phân trang và các khả năng được framework hỗ trợ
   |
   v
R2DBC SPI
   |
   v
R2DBC Driver
   Protocol, kết nối, gửi lệnh, bind giá trị,
   giải mã kết quả và chuyển lỗi từ database
   |
   v
Database Server
   Parser, optimizer, thực thi SQL, transaction,
   constraint, locking, kiểu dữ liệu và hàm riêng
~~~

Các tầng có trách nhiệm khác nhau:

- **Spring Data Relational** cung cấp repository abstraction, mapping metadata, chuyển đổi dữ liệu và cách biểu diễn aggregate. Nó tạo các thao tác persistence dựa trên mô hình mà ứng dụng khai báo.
- **Dialect** cung cấp quy tắc vendor-specific mà Spring Data cần để tạo SQL cho các thao tác được hỗ trợ. Dialect không trực tiếp mở socket, quản lý connection hay thực thi câu lệnh.
- **R2DBC SPI** định nghĩa hợp đồng lập trình reactive để ứng dụng làm việc với connection, statement, result và transaction.
- **R2DBC driver** hiện thực SPI cho database cụ thể. Driver giao tiếp theo protocol của database, bind tham số, mã hóa/giải mã kiểu dữ liệu và chuyển kết quả về API R2DBC.
- **Database server** phân tích, lập kế hoạch và thực thi SQL; áp dụng constraint, transaction, locking, quyền truy cập và ngữ nghĩa của các tính năng riêng.

Dialect và driver đều có yếu tố phụ thuộc database, nhưng không thay thế nhau. Có driver R2DBC không đồng nghĩa Spring Data đã có dialect tương ứng. Ngược lại, có dialect cũng không đủ nếu không có driver có thể kết nối và thực thi lệnh trên database.

## 3. Những phần Spring Data cung cấp tương đối chung

Spring Data Relational cố gắng giữ cách lập trình nhất quán giữa các database ở những thao tác phổ biến. Tùy module và phiên bản, các chức năng chung thường gồm:

- Ánh xạ class và thuộc tính Java với bảng và cột thông qua mapping metadata.
- Nhận diện ID và chuyển đổi giá trị giữa kiểu Java với kiểu dữ liệu được hỗ trợ.
- Biểu diễn aggregate root và các đối tượng thuộc aggregate.
- Cung cấp repository abstraction cho các thao tác CRUD.
- Tạo một số câu lệnh insert, update, delete và select từ metadata.
- Hỗ trợ query derivation hoặc query được khai báo theo khả năng của module.
- Tích hợp conversion service để ứng dụng bổ sung cách chuyển đổi kiểu dữ liệu.

Ví dụ một repository reactive:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByStatus(String status);

    Mono<Customer> findByEmail(String email);
}
~~~

Ứng dụng mô tả thao tác ở mức repository. Spring Data phân tích tên phương thức, metadata và dialect để tạo câu truy vấn phù hợp trong phạm vi query derivation mà module hỗ trợ. Kết quả vẫn phụ thuộc vào khả năng của database và driver.

Một ví dụ khác là mapping bảng:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("display_name")
    private String name;

    private String status;
}
~~~

Các annotation như @Table, @Id và @Column biểu diễn metadata của mô hình dữ liệu. Chúng không làm cho mọi kiểu cột hoặc mọi tính năng SQL của các database trở nên giống nhau. Ví dụ, một thuộc tính Java kiểu mảng, JSON hoặc kiểu enum đặc thù vẫn cần được database, driver và cơ chế conversion hỗ trợ tương ứng.

## 4. Những khác biệt mà dialect có thể mô tả

Phạm vi cụ thể thay đổi theo phiên bản Spring Data và dialect của từng database. Những nhóm khác biệt thường cần dialect xử lý gồm:

### 4.1. Bind marker và cách đánh dấu tham số

SQL có tham số giúp tránh nối trực tiếp dữ liệu đầu vào vào câu lệnh, đồng thời cho phép driver bind giá trị theo đúng kiểu. Nhưng ký hiệu placeholder không giống nhau ở mọi driver:

~~~sql
-- Một số driver dùng dấu hỏi
SELECT id, name FROM customer WHERE status = ?
~~~

~~~sql
-- PostgreSQL thường dùng vị trí đánh số
SELECT id, name FROM customer WHERE status = $1
~~~

R2DBC driver có thể yêu cầu dạng bind marker riêng. Dialect cung cấp thông tin hoặc cơ chế tạo bind marker để phần SQL do Spring Data sinh ra phù hợp với driver tương ứng.

Khi dùng API Spring có hỗ trợ named parameter, ứng dụng thường viết câu lệnh theo tên tham số:

~~~java
Mono<Customer> customer =
    databaseClient.sql(
            "SELECT id, display_name FROM customer WHERE email = :email"
        )
        .bind("email", email)
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("display_name", String.class)
        ))
        .one();
~~~

Spring có thể mở rộng named parameter thành bind marker phù hợp với dialect và driver trong phạm vi API hỗ trợ. Điều này giúp code không phải tự đánh số placeholder. Dù vậy, cách bind cụ thể vẫn phải tuân theo API và giới hạn của phiên bản Spring Data R2DBC đang dùng.

### 4.2. Xử lý tên bảng, tên cột và identifier

Tên bảng hoặc cột có thể trùng từ khóa SQL, chứa ký tự đặc biệt hoặc có quy tắc phân biệt chữ hoa/chữ thường. Cách quote identifier khác nhau giữa database:

~~~sql
-- Ví dụ các dạng quote identifier thường gặp
SELECT * FROM "order";   -- PostgreSQL
SELECT * FROM `order`;   -- MySQL
SELECT * FROM [order];   -- SQL Server
~~~

Dialect có thể cung cấp quy tắc xử lý identifier như ký tự quote và cách chuẩn hóa tên. Nhờ đó, framework có thể tạo câu SQL phù hợp khi làm việc với tên bảng/cột từ mapping metadata.

Tuy nhiên, quote identifier không phải công cụ sửa schema. Tên bảng, tên cột và cách phân biệt chữ hoa/chữ thường vẫn cần nhất quán với schema thật. Đặc biệt, việc đổi tên bảng hoặc cột trong annotation không tự thực hiện migration cho database.

### 4.3. Phân trang và giới hạn kết quả

Phân trang có cùng mục tiêu nhưng có thể khác cú pháp, thứ tự mệnh đề và điều kiện bắt buộc. Như ví dụ ở phần đầu, một database dùng LIMIT/OFFSET trong khi database khác dùng OFFSET/FETCH.

Nếu sử dụng API repository hoặc query builder có hỗ trợ phân trang, Spring Data có thể dựa trên dialect để tạo phần SQL tương ứng. Nhưng khi tự viết SQL trong @Query hoặc DatabaseClient, câu lệnh do ứng dụng cung cấp vẫn phải đúng cú pháp database đích. Không nên giả định framework sẽ viết lại mọi câu SQL tùy ý.

Ngoài ra, phân trang cần thứ tự ổn định. Nếu ORDER BY không xác định duy nhất thứ tự bản ghi, dữ liệu có thể lặp hoặc bị bỏ qua giữa các trang khi bảng thay đổi. Đây là vấn đề thiết kế truy vấn, dialect không thể tự giải quyết thay cho ứng dụng.

### 4.4. Câu lệnh khóa và các mảnh SQL đặc thù

Một số database có cú pháp hoặc khả năng khác nhau cho locking, chẳng hạn khóa bản ghi khi đọc. Dialect có thể cung cấp mảnh SQL cho các kiểu lock được framework hỗ trợ. Tuy nhiên, ý nghĩa và mức độ hỗ trợ của lock vẫn do database quyết định.

Không thể chỉ nhìn thấy một từ khóa lock trong câu SQL rồi kết luận hai database có hành vi giống nhau. Cần xét isolation level, loại lock, phạm vi khóa, thời điểm giải phóng và cách database xử lý cạnh tranh transaction.

### 4.5. Kiểu dữ liệu và khả năng đặc biệt

Một số dialect cung cấp metadata hoặc abstraction cho khả năng như array, kiểu dữ liệu đặc thù hay cách tạo SQL liên quan. Phạm vi hỗ trợ tùy database và phiên bản Spring Data.

Đây là một vùng dễ nhầm lẫn: dialect có thể cho framework biết database có khả năng nào đó, nhưng việc chuyển một giá trị Java thành giá trị trên wire và ngược lại còn phụ thuộc R2DBC driver cùng conversion của Spring Data.

## 5. Những gì thuộc riêng database hoặc driver

Không phải khác biệt nào cũng được dialect che giấu. Một số tính năng có ngữ nghĩa quá đặc thù hoặc không nằm trong abstraction chung của Spring Data.

| Nhóm chức năng | Thành phần quyết định chính | Điều cần lưu ý |
|---|---|---|
| Protocol kết nối và xác thực | R2DBC driver và database | Dialect không mở connection thay driver |
| Mã hóa/giải mã giá trị trên wire | Driver và kiểu dữ liệu database | Cần driver hỗ trợ codec tương ứng |
| Cú pháp và ngữ nghĩa SQL | Database server | SQL độc quyền vẫn phụ thuộc vendor |
| JSON operator, full-text search, spatial query | Database và SQL cụ thể | Không có bảo đảm một câu lệnh chạy trên mọi vendor |
| Stored procedure, trigger, function riêng | Database và driver/API gọi tương ứng | Cách gọi và kết quả có thể khác nhau |
| Sequence, identity, generated column | Database; dialect/driver hỗ trợ phần framework cần | Cách sinh và lấy giá trị không hoàn toàn giống nhau |
| Locking, isolation, deadlock | Database và transaction manager/driver | Cùng cú pháp không có nghĩa cùng ngữ nghĩa |
| Query optimizer và execution plan | Database server | Dialect không quyết định kế hoạch thực thi |
| Constraint, collation, index và partition | Database server | Phải thiết kế theo khả năng và quy tắc vendor |

Ví dụ, PostgreSQL có JSON operator và kiểu JSONB với các toán tử riêng. MySQL có bộ hàm JSON và quy tắc riêng. SQL Server có các hàm JSON theo cách biểu diễn khác. Dialect không thể tự động biến mọi biểu thức JSON của một database thành biểu thức tương đương ở database khác, nhất là khi ngữ nghĩa hoặc chỉ mục hỗ trợ không giống nhau.

Tương tự, cú pháp upsert cũng khác nhau: PostgreSQL có ON CONFLICT, MySQL có ON DUPLICATE KEY UPDATE, còn SQL Server có những cách triển khai khác. Nếu nghiệp vụ phụ thuộc vào hành vi upsert cụ thể, cần viết và kiểm thử theo database đích hoặc xây một abstraction nghiệp vụ do ứng dụng kiểm soát.

## 6. Phân biệt dialect với R2DBC driver

Dialect và driver thường được nhắc cùng nhau vì cả hai đều gắn với database vendor. Có thể phân biệt bằng câu hỏi mà mỗi thành phần trả lời:

- **Dialect:** Framework cần tạo câu SQL như thế nào để phù hợp với database này?
- **Driver:** Làm thế nào gửi lệnh qua protocol của database, bind giá trị và đọc kết quả?

Ví dụ, dialect có thể cung cấp bind marker factory cho SQL được sinh ra. Driver chịu trách nhiệm thực sự bind giá trị vào statement và chuyển giá trị thành biểu diễn mà protocol của database yêu cầu.

Với kiểu dữ liệu JSON, Spring Data có thể dùng conversion để chuyển đổi giữa object Java và representation mà ứng dụng lựa chọn. R2DBC driver phải biết cách gửi và đọc kiểu dữ liệu mà database hỗ trợ. Database lại quyết định kiểu JSON đó có operator, index hoặc hành vi so sánh nào.

Vì vậy, khi một kiểu dữ liệu không hoạt động, cần xác định lỗi nằm ở đâu:

1. Mapping metadata có nhận diện đúng thuộc tính và kiểu Java không?
2. Spring conversion có chuyển đổi đúng giá trị không?
3. Driver có codec hoặc cách bind phù hợp không?
4. Cột trong database có kiểu dữ liệu tương thích không?
5. Câu SQL và phép toán có hợp lệ trên database đó không?

Thêm converter không thể sửa một driver không hỗ trợ protocol cần thiết. Đổi dialect cũng không thể tự bổ sung codec còn thiếu trong driver.

## 7. Spring Data nhận diện dialect như thế nào?

Trong ứng dụng R2DBC, Spring Data thường xác định dialect dựa trên metadata của ConnectionFactory và loại database mà driver công bố. Cơ chế resolver chọn dialect tương ứng trong số những dialect mà phiên bản framework hỗ trợ.

Luồng khái quát:

~~~text
ConnectionFactory
       |
       v
ConnectionFactoryMetadata
       |
       v
Dialect resolver
       |
       v
R2dbcDialect phù hợp
       |
       v
Spring Data dùng dialect khi tạo SQL
~~~

Việc tự nhận diện chỉ thành công nếu framework biết database/driver đó và có dialect tương ứng. Với database ít phổ biến, driver tùy biến hoặc phiên bản framework chưa hỗ trợ, ứng dụng có thể không tìm được dialect phù hợp.

Khi gặp tình huống đó, cần kiểm tra:

- Database thực tế mà ConnectionFactory đang kết nối.
- Driver R2DBC đã dùng và metadata mà driver công bố.
- Phiên bản Spring Boot, Spring Data Relational và Spring Data R2DBC.
- Phiên bản framework có cung cấp dialect cho database đó hay không.
- Có cần tích hợp một dialect implementation hoặc provider tùy chỉnh theo SPI của đúng phiên bản đang dùng hay không.

Không nên tự chọn dialect chỉ dựa trên tên database ghi trong cấu hình nếu ConnectionFactory thực tế trỏ sang một loại database khác. Dialect phải tương thích với driver và database mà ứng dụng thực sự sử dụng.

## 8. SQL do framework sinh ra và SQL do ứng dụng tự viết

Ranh giới này đặc biệt quan trọng khi dùng Spring Data R2DBC.

Với repository method hoặc thao tác CRUD được Spring Data tạo từ metadata, framework có thể áp dụng dialect để điều chỉnh các phần SQL cần thiết. Lập trình viên tập trung vào entity, aggregate và ý định truy vấn.

Với SQL do ứng dụng tự khai báo, ví dụ trong @Query hoặc DatabaseClient, ứng dụng chịu trách nhiệm về cú pháp và ngữ nghĩa của câu lệnh. Framework có thể hỗ trợ mở rộng tham số và bind giá trị theo dialect, nhưng không có nghĩa nó dịch toàn bộ SQL vendor-specific thành SQL portable.

Ví dụ câu SQL sau dùng LIMIT:

~~~java
Flux<Customer> customers =
    databaseClient.sql(
        "SELECT id, display_name FROM customer ORDER BY id LIMIT :size"
    )
    .bind("size", 20)
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("display_name", String.class)
    ))
    .all();
~~~

Named parameter có thể được Spring mở rộng thành bind marker tương ứng, nhưng từ khóa LIMIT vẫn là cú pháp trong nội dung SQL mà ứng dụng đã viết. Nếu database đích không hỗ trợ cú pháp đó, việc bind tham số đúng không làm câu SQL trở nên hợp lệ.

Với SQL có tính năng đặc thù, nên cô lập câu lệnh trong repository hoặc adapter riêng cho vendor đó. Điều này giúp phần còn lại của ứng dụng không phụ thuộc trực tiếp vào cú pháp database.

## 9. Chiến lược giữ tính portable

Không phải ứng dụng nào cũng cần hỗ trợ nhiều database. Nhưng ngay cả khi chỉ triển khai một database, phân định ranh giới rõ ràng vẫn giúp thay đổi schema, nâng cấp driver và xử lý lỗi dễ hơn.

### Ưu tiên SQL chuẩn trong phần nghiệp vụ phổ biến

Đối với CRUD, lọc, sắp xếp và join thông thường, ưu tiên các cấu trúc SQL phổ biến được database mục tiêu hỗ trợ. Dùng repository abstraction khi nó diễn đạt được ý định truy vấn mà không làm mất khả năng kiểm soát cần thiết.

### Giữ SQL đặc thù ở một nơi

Nếu cần JSON operator, full-text search, upsert, stored procedure hoặc tính năng độc quyền, đặt truy vấn đó trong một repository/adapter có tên rõ ràng. Tránh để cú pháp vendor-specific rải rác trong nhiều service.

Có thể định nghĩa một interface theo ý nghĩa nghiệp vụ:

~~~java
public interface CustomerSearch {

    Flux<Customer> searchByProfileAttribute(
        String attribute,
        String value
    );
}
~~~

Sau đó triển khai riêng cho database đang sử dụng. Service chỉ phụ thuộc interface và không phải biết câu SQL cụ thể.

### Quản lý schema bằng migration

Dialect không thay thế công cụ quản lý schema. Việc tạo bảng, index, sequence, constraint, view hoặc function nên được quản lý bằng migration có phiên bản. Migration cần phản ánh đúng khả năng và cú pháp của database đích.

Nếu ứng dụng hỗ trợ nhiều vendor, có thể cần migration riêng theo vendor hoặc các migration dùng chung phần SQL chuẩn và tách phần đặc thù.

### Không xem H2 là bản thay thế hoàn toàn cho database production

H2 hữu ích cho kiểm thử nhanh, nhưng khác biệt về kiểu dữ liệu, SQL, transaction, locking và generated key có thể khiến bài test chạy qua trong H2 nhưng lỗi ở database production. Kiểm thử tích hợp các luồng persistence quan trọng trên đúng loại database triển khai giúp phát hiện khác biệt thực tế.

### Quan sát SQL và kiểm tra phiên bản

Khi truy vấn sinh ra không đúng như mong đợi, bật logging phù hợp để quan sát SQL và tham số ở môi trường phát triển. Đồng thời kiểm tra phiên bản Spring Data, dialect và driver. Một thay đổi phiên bản có thể bổ sung hoặc điều chỉnh cách hỗ trợ một tính năng SQL.

## 10. Kiểm thử dialect và khả năng riêng của database

Nên phân biệt kiểm thử mapping chung với kiểm thử tích hợp database:

1. **Kiểm thử mapping và conversion:** xác nhận thuộc tính Java được ánh xạ đúng, converter cho kết quả mong đợi và repository method biểu diễn đúng ý định truy vấn.
2. **Kiểm thử SQL sinh ra:** khi có khác biệt về bind marker, quote identifier hoặc phân trang, kiểm tra câu SQL mà framework tạo và cách tham số được bind.
3. **Kiểm thử tích hợp với database thật:** chạy các thao tác insert, update, delete, truy vấn, transaction, generated ID, locking hoặc kiểu dữ liệu đặc thù trên database và phiên bản mục tiêu.
4. **Kiểm thử migration:** tạo schema từ đầu bằng toàn bộ migration để chắc rằng database sạch có thể được khởi tạo đúng.
5. **Kiểm thử nâng cấp:** khi thay Spring Data hoặc driver, chạy lại các luồng persistence quan trọng để phát hiện thay đổi về SQL, codec hoặc transaction.

Testcontainers là một lựa chọn hữu ích để khởi chạy database thật trong kiểm thử tự động. Nếu production dùng PostgreSQL, nên có kiểm thử tích hợp với PostgreSQL; nếu dùng SQL Server, kiểm thử quan trọng cũng cần chạy trên SQL Server. Dùng database cùng họ và cùng phiên bản mục tiêu giúp kết quả đáng tin cậy hơn.

## 11. Một số lỗi thường gặp và hướng tìm nguyên nhân

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không tìm được dialect | Database hoặc driver chưa được phiên bản Spring Data hỗ trợ; metadata không nhận diện đúng | Kiểm tra ConnectionFactory, driver, metadata và phiên bản framework |
| Lỗi cú pháp gần dấu hỏi hoặc ký hiệu tham số | Bind marker không phù hợp hoặc câu SQL dùng placeholder sai | Kiểm tra dialect, API bind và SQL thực tế |
| Lỗi tên bảng/cột không tồn tại | Identifier bị quote hoặc chuẩn hóa khác; khác biệt chữ hoa/chữ thường; schema chưa đúng | Kiểm tra mapping, tên thật trong schema và SQL được sinh |
| Truy vấn phân trang chạy trên database này nhưng lỗi ở database khác | SQL tự viết dùng cú pháp riêng hoặc database yêu cầu mệnh đề bổ sung | Kiểm tra câu SQL và khả năng phân trang của database đích |
| Giá trị JSON, array hoặc UUID không bind/đọc được | Thiếu codec, converter hoặc kiểu cột không tương thích | Kiểm tra lần lượt conversion, driver codec và kiểu cột |
| ID sinh tự động không được trả về | Cách sinh khóa hoặc lấy generated value khác nhau | Kiểm tra cấu hình ID, dialect, driver và loại cột |
| Kiểm thử H2 thành công nhưng production thất bại | SQL hoặc ngữ nghĩa database khác nhau | Chạy integration test trên đúng database production |

Không nên xử lý mọi lỗi bằng cách thay dialect. Cần xác định tầng phát sinh lỗi trước, vì cùng một biểu hiện có thể đến từ SQL, driver, mapping hoặc schema.

## 12. Khi nào cần dialect tùy chỉnh?

Dialect tùy chỉnh có thể cần thiết khi:

- Ứng dụng dùng database hoặc driver mà Spring Data chưa cung cấp dialect tương ứng.
- Database có khác biệt về SQL cần framework biết để tạo các thao tác repository được hỗ trợ.
- Một khả năng vendor-specific cần được biểu diễn qua extension point của Spring Data thay vì tự tạo SQL ở nhiều nơi.

Trước khi viết dialect mới, cần kiểm tra phiên bản Spring Data đang dùng đã có hỗ trợ hay extension point phù hợp chưa. API của dialect có thể thay đổi giữa các phiên bản; implementation phải tương thích với đúng release train và driver.

Dialect tùy chỉnh cũng có giới hạn. Nó có thể dạy framework tạo một mảnh SQL hoặc mô tả một khả năng, nhưng không thay thế driver, không thêm tính năng cho database server và không tự chuyển đổi ngữ nghĩa của một câu SQL tùy ý. Với một truy vấn độc quyền đơn lẻ, repository adapter riêng thường đơn giản và dễ kiểm thử hơn việc mở rộng dialect toàn cục.

## 13. Cách xác định đúng ranh giới khi thiết kế

Khi gặp một yêu cầu truy cập dữ liệu, có thể lần lượt đặt các câu hỏi:

1. Đây có phải thao tác CRUD hoặc truy vấn phổ biến mà Spring Data đã hỗ trợ không? Nếu có, ưu tiên abstraction chung.
2. Framework có cần biết cú pháp hoặc quy tắc vendor-specific để tự tạo SQL không? Nếu có, kiểm tra dialect hiện tại.
3. Đây là SQL do ứng dụng tự viết hay SQL do Spring Data sinh? SQL tự viết phải tuân theo database đích.
4. Vấn đề có liên quan đến protocol, bind, codec hoặc kết nối không? Nếu có, kiểm tra R2DBC driver.
5. Đây có phải tính năng hoặc ngữ nghĩa riêng của database như JSON operator, full-text, locking hay stored procedure không? Nếu có, giữ phần phụ thuộc vendor trong adapter phù hợp.
6. Đã kiểm thử trên đúng database và phiên bản triển khai chưa? Nếu chưa, kết quả từ một database khác chưa đủ để khẳng định tính tương thích.

| Nhu cầu | Nơi nên bắt đầu tìm hiểu |
|---|---|
| Repository CRUD, aggregate mapping | Spring Data Relational |
| Cú pháp SQL do framework sinh, bind marker, identifier | Dialect |
| Kết nối, protocol, bind/codec, đọc kết quả | R2DBC driver |
| Hàm SQL, JSON operator, index, constraint, locking semantics | Database và tài liệu vendor |
| Chuyển đổi kiểu Java theo quy tắc ứng dụng | Spring Data converters / custom converter |
| Tạo và thay đổi schema | Database migration |

## 14. Ghi nhớ

- Dialect mô tả những khác biệt SQL mà Spring Data cần biết để tạo câu lệnh phù hợp với database.
- Spring Data Relational cung cấp abstraction chung cho mapping, aggregate và repository trong phạm vi module hỗ trợ.
- R2dbcDialect thuộc tầng Spring Data; nó không phải R2DBC driver và không trực tiếp giao tiếp với database server.
- R2DBC driver đảm nhiệm protocol, kết nối, bind, codec và chuyển kết quả.
- Database server quyết định cú pháp, ngữ nghĩa, transaction, locking, kiểu dữ liệu và các tính năng độc quyền.
- Dialect có thể hỗ trợ các phần như bind marker, identifier, phân trang hoặc khả năng đặc thù được framework biểu diễn; phạm vi cụ thể phụ thuộc phiên bản và vendor.
- SQL tự viết vẫn phải đúng cú pháp database đích. Dialect không tự động dịch mọi câu SQL vendor-specific.
- Muốn bảo đảm tính tương thích, hãy cô lập SQL đặc thù, quản lý schema bằng migration và kiểm thử trên đúng database cùng driver sẽ triển khai.
