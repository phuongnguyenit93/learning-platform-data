# Khi nên dùng JPA và khi nên chọn công cụ truy cập dữ liệu khác

## 1. Bắt đầu từ bài toán dữ liệu

JPA phù hợp với nhiều ứng dụng Java làm việc với cơ sở dữ liệu quan hệ, nhưng không phải mọi thao tác đọc ghi dữ liệu đều cần một ORM. Lựa chọn đúng phụ thuộc vào hình dạng dữ liệu, cách ứng dụng thay đổi dữ liệu, độ phức tạp của truy vấn, yêu cầu hiệu năng và mô hình xử lý đồng bộ hay bất đồng bộ.

Một nguyên tắc thực tế là: dùng JPA khi mô hình nghiệp vụ được biểu diễn tự nhiên bằng các entity có vòng đời và quan hệ; chọn công cụ SQL trực tiếp khi câu truy vấn, phép tổng hợp hoặc luồng xử lý dữ liệu mới là trọng tâm. Với hệ thống có nhiều loại workload, có thể dùng nhiều công cụ ở những phần phù hợp, miễn là ranh giới transaction và quyền sở hữu dữ liệu được thiết kế rõ ràng.

Trước khi quyết định, cần phân biệt ba khái niệm:

- **JPA (Jakarta Persistence)** là đặc tả chuẩn của Java cho việc ánh xạ và lưu trữ object vào cơ sở dữ liệu quan hệ. Đặc tả định nghĩa entity, persistence context, EntityManager, JPQL, quan hệ và các quy tắc vòng đời.
- **JPA provider** là thư viện hiện thực đặc tả. Hibernate ORM là lựa chọn phổ biến trong các ứng dụng Spring Boot; EclipseLink là một ví dụ khác. Provider chịu trách nhiệm chuyển thao tác trên entity thành SQL và thực thi qua JDBC.
- **Spring Data JPA** là lớp hỗ trợ của Spring giúp xây dựng repository trên JPA. Nó cung cấp các interface như `JpaRepository`, cơ chế tạo truy vấn từ tên phương thức, `@Query`, projection và tích hợp với transaction của Spring.

Vì vậy, Spring Data JPA không thay thế database, JDBC driver hay SQL. Nó giúp làm việc với JPA thuận tiện hơn. Khi cần, ứng dụng vẫn có thể dùng JPQL, native SQL hoặc một công cụ JDBC bên cạnh repository.

## 2. JPA làm gì và điều gì khiến nó hữu ích?

JPA ánh xạ dữ liệu quan hệ thành object Java. Một class được đánh dấu `@Entity` thường tương ứng với một bảng; thuộc tính được ánh xạ thành cột; quan hệ như `@ManyToOne`, `@OneToMany` và `@OneToOne` mô tả liên kết giữa các entity.

Điểm quan trọng của JPA không chỉ là ánh xạ object sang bảng. JPA còn quản lý **persistence context** — phạm vi theo dõi các entity đang được quản lý. Một entity thường trải qua các trạng thái:

- **New / transient:** object mới được tạo trong Java, chưa được persistence context quản lý.
- **Managed:** entity đang được quản lý. Thay đổi thuộc tính của entity trong transaction có thể được JPA phát hiện tự động.
- **Detached:** entity từng được quản lý nhưng hiện không còn gắn với persistence context.
- **Removed:** entity được đánh dấu xóa; câu lệnh SQL tương ứng được đồng bộ khi flush.

Với entity managed, JPA sử dụng cơ chế **dirty checking** để phát hiện thay đổi. Ứng dụng có thể tải một entity, gọi phương thức nghiệp vụ để thay đổi trạng thái, rồi commit transaction. Khi flush, provider tạo SQL cần thiết. Không nhất thiết phải gọi `save()` sau mỗi lần sửa một entity đang managed trong cùng transaction.

JPA cũng cung cấp một số khả năng có giá trị trong mô hình nghiệp vụ:

- Quản lý vòng đời entity và đồng bộ thay đổi trong một persistence context.
- Biểu diễn quan hệ giữa các entity, cùng cascade và orphan removal khi được cấu hình đúng.
- Tích hợp với transaction để nhiều thay đổi dữ liệu có thể commit hoặc rollback cùng nhau.
- Hỗ trợ JPQL, Criteria API và native SQL cho các kiểu truy vấn khác nhau.
- Hỗ trợ optimistic locking qua `@Version` để phát hiện cập nhật xung đột.
- Hỗ trợ fetch plan, batching và cache thông qua provider.

Những khả năng này hữu ích khi nghiệp vụ thao tác trên các đối tượng có quan hệ và cần bảo toàn quy tắc nhất quán. Tuy nhiên, chúng cũng tạo ra một lớp hành vi cần hiểu rõ. Một lời gọi repository có thể phát sinh nhiều câu SQL; quan hệ lazy có thể gây truy vấn bổ sung; việc flush có thể xảy ra trước commit. JPA giảm công việc ánh xạ thủ công, nhưng không làm cho SQL và thiết kế database biến mất.

## 3. Khi nào nên dùng JPA?

### 3.1. Dữ liệu có cấu trúc quan hệ và mô hình nghiệp vụ dựa trên entity

JPA là lựa chọn tự nhiên khi dữ liệu nằm trong các bảng quan hệ, có khóa chính, khóa ngoại và các ràng buộc toàn vẹn. Mô hình Java cũng có những đối tượng nghiệp vụ tương đối ổn định, ví dụ:

- Đơn hàng có các dòng hàng và trạng thái xử lý.
- Tài khoản có hồ sơ, địa chỉ và các thiết lập liên quan.
- Hợp đồng có các điều khoản, phụ lục và lịch sử trạng thái.
- Sản phẩm có danh mục, thuộc tính cố định và quan hệ với nhà cung cấp.

Trong những trường hợp này, ứng dụng thường tải một aggregate hoặc một nhóm entity, áp dụng quy tắc nghiệp vụ rồi lưu thay đổi trong transaction. Entity giúp gom dữ liệu và hành vi liên quan vào cùng một mô hình.

Không nên tạo quan hệ object chỉ vì database có khóa ngoại. Chỉ ánh xạ quan hệ khi ứng dụng thực sự cần điều hướng hoặc quản lý vòng đời của đối tượng liên quan. Quan hệ quá rộng có thể làm entity graph lớn, truy vấn khó đoán và tăng nguy cơ tải dữ liệu không cần thiết.

### 3.2. Nghiệp vụ cập nhật entity nhiều hơn là viết truy vấn SQL phức tạp

JPA phù hợp với luồng như:

1. Tìm entity theo định danh.
2. Kiểm tra trạng thái và quyền thực hiện.
3. Thay đổi dữ liệu thông qua phương thức nghiệp vụ.
4. Ghi nhận các thay đổi trong cùng transaction.

Ví dụ, xác nhận một đơn hàng có thể cần kiểm tra trạng thái đơn, cập nhật thời điểm xác nhận và thay đổi trạng thái của một số đối tượng liên quan. Khi các entity được quản lý trong persistence context, dirty checking giúp đồng bộ các thay đổi mà không cần tự viết câu `UPDATE` cho từng trường hợp.

### 3.3. Cần transaction và kiểm soát xung đột ở cấp entity

Với dữ liệu nghiệp vụ, một thao tác thường gồm nhiều lần đọc và ghi có liên quan. JPA tích hợp tốt với transaction của Spring, giúp đặt ranh giới ở service bằng `@Transactional`.

Nếu nhiều người dùng có thể sửa cùng một bản ghi, `@Version` hỗ trợ optimistic locking. Provider kiểm tra phiên bản khi cập nhật; nếu dữ liệu đã bị thay đổi bởi transaction khác, ứng dụng nhận được lỗi xung đột thay vì âm thầm ghi đè dữ liệu mới.

JPA đặc biệt hữu ích khi nhóm phát triển muốn biểu diễn quy tắc nghiệp vụ qua entity và cần một cơ chế nhất quán để theo dõi thay đổi trong transaction.

### 3.4. Truy vấn nằm trong phạm vi JPA xử lý rõ ràng

Các truy vấn tìm entity theo khóa, lọc theo một số thuộc tính, phân trang, sắp xếp, truy vấn quan hệ và projection thường phù hợp với repository hoặc JPQL.

Spring Data JPA hỗ trợ phương thức repository theo quy ước:

```java
public interface OrderRepository extends JpaRepository<Order, Long> {
    List<Order> findByStatusAndCustomerId(
        OrderStatus status,
        Long customerId
    );
}
```

Khi truy vấn cần biểu đạt rõ hơn, có thể dùng `@Query`, projection hoặc Specification. Khi SQL cụ thể trở nên dài, phụ thuộc mạnh vào database hoặc cần tối ưu chi tiết, đó là tín hiệu nên cân nhắc một công cụ SQL-first.

## 4. Khi nào nên chọn công cụ khác?

### 4.1. Báo cáo, tổng hợp và truy vấn đọc phức tạp

Một màn hình báo cáo có thể cần nhiều phép join, group by, window function, CTE, phép tổng hợp hoặc dữ liệu được biến đổi thành một cấu trúc chỉ phục vụ hiển thị. Trong trường hợp này, mục tiêu chính là truy vấn và tạo read model, không phải tải một entity graph để thay đổi vòng đời của entity.

JPA vẫn có thể chạy native SQL hoặc projection, nhưng nếu phần lớn logic phải viết bằng SQL và cần kiểm soát chính xác câu truy vấn, Spring JDBC, MyBatis hoặc jOOQ thường diễn đạt ý định rõ hơn. Không nên tải hàng nghìn entity chỉ để lấy vài cột và tính tổng.

### 4.2. Import, export hoặc cập nhật hàng loạt với số lượng lớn

Các tác vụ ETL, đồng bộ dữ liệu, nhập hàng triệu bản ghi, cập nhật hàng loạt hoặc xuất dữ liệu theo luồng thường cần throughput và mức sử dụng bộ nhớ có thể dự đoán.

JPA được thiết kế xoay quanh entity và persistence context. Nếu giữ quá nhiều entity managed, bộ nhớ tăng và quá trình dirty checking/flush có thể trở nên tốn kém. Provider có hỗ trợ JDBC batching, nhưng với thao tác khối lượng lớn, JDBC batch, câu lệnh SQL trực tiếp hoặc tính năng bulk của database thường đơn giản và hiệu quả hơn.

JPQL bulk update/delete cũng có một lưu ý: thao tác bulk được thực thi trực tiếp trên database và không đi qua vòng đời của từng entity managed. Persistence context hiện tại có thể giữ dữ liệu cũ. Sau bulk operation, cần chủ động đồng bộ, clear hoặc refresh persistence context khi phù hợp.

### 4.3. Cần kiểm soát SQL chặt chẽ

Nếu hiệu năng phụ thuộc vào một câu SQL cụ thể, hint riêng của database, execution plan, CTE, window function hoặc cấu trúc truy vấn đặc thù, công cụ SQL-first có thể phù hợp hơn.

JPA cho phép native SQL, vì vậy đây không phải giới hạn tuyệt đối. Nhưng nếu hầu hết thao tác đều phải viết native query, mapping thủ công hoặc xử lý khác biệt của provider, lợi ích của ORM có thể không còn đủ bù cho độ phức tạp.

### 4.4. Cần xử lý bất đồng bộ theo mô hình reactive

JPA hoạt động theo mô hình blocking vì dựa trên JDBC. Một thread thường chờ kết quả database trước khi tiếp tục. Nếu hệ thống cần một pipeline reactive từ đầu đến cuối và dùng cơ sở dữ liệu quan hệ, có thể xem xét R2DBC cùng Spring Data R2DBC.

Không nên chuyển sang R2DBC chỉ vì muốn dùng `Mono` hoặc `Flux`. Cần đánh giá toàn bộ đường đi của request: web stack, driver, transaction, thư viện tích hợp và cách xử lý lỗi. Nếu một phần lớn hệ thống vẫn blocking, việc thêm reactive data access có thể làm tăng độ phức tạp mà không tạo ra lợi ích tương ứng.

### 4.5. Dữ liệu không phải quan hệ

JPA nhắm đến mô hình quan hệ. Nếu dữ liệu chính là document, key-value, graph hoặc wide-column, hãy dùng driver và module Spring Data dành cho loại store đó, ví dụ MongoDB, Redis, Neo4j hoặc Cassandra. Cố gắng ép dữ liệu phi quan hệ vào mô hình entity-relational thường tạo ra nhiều lớp chuyển đổi không cần thiết.

## 5. So sánh các lựa chọn phổ biến

| Công cụ | Phù hợp khi | Điểm cần cân nhắc |
|---|---|---|
| JPA / Spring Data JPA | Mô hình quan hệ có entity, quan hệ và nghiệp vụ cập nhật theo aggregate | Cần hiểu persistence context, fetch plan, flush, dirty checking và SQL do provider sinh ra |
| Spring Data JDBC | Muốn repository và mapping object-relational đơn giản theo aggregate | Không có persistence context, lazy loading hay dirty checking như JPA; cập nhật aggregate theo cách rõ ràng hơn |
| Spring JDBC (`JdbcClient`, `NamedParameterJdbcTemplate`) | Muốn viết SQL trực tiếp, mapping kết quả vào DTO và kiểm soát truy vấn | Phải tự quản lý câu SQL và mapping; ít hành vi ORM tự động |
| MyBatis | SQL là trung tâm, cần ánh xạ kết quả truy vấn vào object | Có quyền kiểm soát SQL cao nhưng phải duy trì mapper và câu truy vấn |
| jOOQ | Cần SQL rõ ràng, có DSL và kiểm tra kiểu dữ liệu khi biên dịch | Phù hợp với hệ thống SQL-centric; cần quản lý quy trình sinh code từ schema và phiên bản thư viện |
| JDBC trực tiếp | Tác vụ nhỏ, đặc biệt hoặc cần kiểm soát thấp tầng | Phải tự xử lý connection, statement, result set, mapping và tài nguyên; thường nên ưu tiên Spring JDBC trong ứng dụng Spring |
| R2DBC | Cần truy cập relational database theo mô hình reactive end-to-end | API, transaction và driver khác JDBC/JPA; không dùng chung persistence context của JPA |
| Driver / Spring Data của NoSQL store | Dữ liệu chính thuộc document, key-value, graph hoặc wide-column | Cần thiết kế theo khả năng và giới hạn của từng loại database |

### Spring Data JDBC khác JPA ở điểm nào?

Cả hai đều cung cấp repository và mapping, nhưng mô hình hoạt động khác nhau.

Spring Data JDBC không duy trì persistence context để theo dõi entity. Nó không có dirty checking hay lazy loading như JPA. Việc lưu thường được tổ chức quanh aggregate root và các thao tác cập nhật có tính tường minh hơn. Điều này có thể dễ hiểu và dễ dự đoán khi domain không cần đồ thị entity phức tạp.

JPA phù hợp hơn khi ứng dụng cần quản lý entity trong một persistence context, điều hướng quan hệ và tận dụng dirty checking. Spring Data JDBC phù hợp khi muốn giữ mô hình aggregate nhưng không cần phần lớn hành vi của ORM.

### MyBatis và jOOQ khác Spring JDBC ở điểm nào?

Spring JDBC cung cấp API thực thi SQL và ánh xạ kết quả. MyBatis bổ sung cơ chế mapper để kết nối câu SQL với object và tham số. jOOQ cung cấp DSL cho SQL, có thể sinh kiểu Java từ schema để giúp kiểm tra tên bảng, cột và kiểu dữ liệu ở thời điểm biên dịch.

Cả ba đều hướng tới việc làm rõ câu SQL. Chọn theo phong cách nhóm phát triển, mức độ phức tạp của truy vấn và nhu cầu kiểm tra kiểu dữ liệu; không cần đưa thêm framework nếu Spring JDBC đã đáp ứng tốt.

## 6. Cách ra quyết định theo từng bước

Có thể dùng chuỗi câu hỏi sau để chọn công cụ:

1. **Dữ liệu có phải dữ liệu quan hệ không?** Nếu không, bắt đầu từ driver hoặc Spring Data module của store tương ứng.
2. **Ứng dụng có yêu cầu pipeline reactive end-to-end không?** Nếu có và database là relational, đánh giá R2DBC. Nếu không, mô hình blocking với JDBC/JPA vẫn là lựa chọn tự nhiên.
3. **Nghiệp vụ chủ yếu thao tác trên entity hoặc aggregate có vòng đời và quan hệ không?** Nếu có, JPA là ứng viên mạnh.
4. **Phần lớn công việc là truy vấn SQL, tổng hợp, báo cáo hoặc cập nhật khối lượng lớn?** Nếu có, ưu tiên Spring JDBC, MyBatis, jOOQ hoặc tính năng SQL của database.
5. **Chỉ cần persistence đơn giản theo aggregate, không cần persistence context?** Hãy cân nhắc Spring Data JDBC.
6. **Một công cụ có thực sự đáp ứng mọi workload không?** Nếu không, tách theo use case: JPA cho nghiệp vụ cập nhật entity; SQL-first cho báo cáo hoặc batch.

Đừng chọn công cụ chỉ dựa trên số lượng dòng code ban đầu. Hãy tính cả chi phí bảo trì, khả năng quan sát SQL, cách xử lý lỗi, yêu cầu transaction, hiệu năng dưới tải thật và mức độ quen thuộc của nhóm.

## 7. Kết hợp JPA với JDBC trong cùng ứng dụng

Một ứng dụng không bắt buộc chỉ sử dụng một công cụ truy cập dữ liệu. Một cách kết hợp thường gặp là:

- Dùng JPA cho luồng nghiệp vụ đọc và cập nhật aggregate.
- Dùng Spring JDBC hoặc jOOQ cho báo cáo, projection và truy vấn cần kiểm soát SQL.
- Dùng JDBC batch hoặc cơ chế bulk của database cho import/export.
- Dùng R2DBC ở một thành phần riêng khi thực sự cần reactive access.

Khi kết hợp, cần giữ các nguyên tắc sau:

- Xác định rõ transaction boundary và transaction manager. Chỉ giả định hai cách truy cập cùng transaction khi chúng thực sự dùng cùng DataSource và được cấu hình để tham gia cùng transaction.
- Nếu JDBC đọc dữ liệu vừa được thay đổi trong persistence context, cần cân nhắc thời điểm flush. Thay đổi trong entity managed có thể chưa được gửi xuống database trước khi flush.
- Sau bulk SQL hoặc JPQL update, persistence context có thể không còn đồng bộ với database. Hãy clear hoặc refresh entity liên quan trước khi tiếp tục sử dụng chúng.
- Giữ một nơi làm chủ quy tắc ghi cho mỗi use case. Tránh để nhiều tầng cùng cập nhật một dữ liệu mà không có quy ước rõ ràng.
- Kiểm thử transaction rollback và tính nhất quán khi một use case đi qua nhiều API truy cập dữ liệu.

Kết hợp công cụ giúp chọn đúng mức trừu tượng cho từng workload, nhưng cũng tạo thêm trách nhiệm về đồng bộ trạng thái và transaction. Chỉ nên kết hợp khi lợi ích thực tế lớn hơn chi phí đó.

## 8. Những lỗi thường gặp khi dùng JPA

### 8.1. Nghĩ rằng một lời gọi repository tương ứng với một câu SQL

Một truy vấn lấy entity có thể kéo theo truy vấn khác khi ứng dụng truy cập quan hệ lazy. Đây là nguyên nhân phổ biến của lỗi **N+1**: một truy vấn lấy danh sách cha, sau đó mỗi phần tử lại kích hoạt một truy vấn lấy dữ liệu liên quan.

Cách xử lý nên dựa trên use case:

- Dùng fetch join hoặc `@EntityGraph` khi biết trước quan hệ cần tải.
- Dùng DTO projection khi chỉ cần một số cột.
- Dùng batch fetching khi nhiều entity cần tải cùng một loại quan hệ.
- Kiểm tra SQL thực tế và số lần gọi database trong test hoặc môi trường quan sát được.

Không nên chuyển mọi quan hệ sang `EAGER` để chữa N+1. Eager loading có thể khiến các truy vấn khác tải dữ liệu dư thừa và làm hành vi khó dự đoán hơn.

### 8.2. Tải toàn bộ entity cho màn hình chỉ cần vài trường

Entity thường mang theo quan hệ, trạng thái và hành vi phục vụ nghiệp vụ. Màn hình danh sách hoặc báo cáo có thể chỉ cần mã, tên, trạng thái và ngày tạo. Dùng projection hoặc DTO query thường tiết kiệm dữ liệu hơn và giảm phụ thuộc của API vào cấu trúc entity.

### 8.3. Dùng collection fetch join cùng phân trang mà không kiểm tra

Join một collection có thể nhân số dòng kết quả theo số phần tử con. Khi kết hợp với phân trang, kết quả có thể không tương ứng với số entity cha mong muốn hoặc provider phải xử lý phân trang ở bộ nhớ. Hãy kiểm tra SQL sinh ra; có thể dùng truy vấn phân trang lấy ID trước, rồi truy vấn thứ hai tải dữ liệu cần thiết.

### 8.4. Không hiểu trạng thái managed và detached

Thay đổi một object detached không tự động được ghi xuống database. Ngược lại, entity managed trong transaction có thể được cập nhật nhờ dirty checking dù không gọi `save()` lần nữa.

Với `JpaRepository.save()`, Spring Data JPA lựa chọn `persist` hoặc `merge` tùy cách nhận diện entity mới. `merge` trả về instance managed; không nên mặc định rằng object truyền vào luôn trở thành instance được quản lý. Hãy hiểu vòng đời entity trước khi thiết kế luồng cập nhật.

### 8.5. Đặt transaction sai ranh giới

Nếu một thao tác nghiệp vụ cần nhiều lần đọc và ghi nhất quán, transaction thường nên nằm ở service thể hiện use case. Đặt transaction quá nhỏ có thể làm các bước không còn nguyên tử; đặt quá rộng có thể giữ connection và persistence context lâu, tăng lock và tiêu thụ tài nguyên.

Không nên dựa vào việc gọi repository riêng lẻ để suy ra toàn bộ use case đã có transaction đúng như mong muốn.

### 8.6. Dùng bulk update rồi tiếp tục tin vào entity đang managed

Bulk update/delete bỏ qua cơ chế cập nhật từng entity. Nếu persistence context đang giữ một entity bị tác động, giá trị trong bộ nhớ có thể cũ hơn database. Sau thao tác bulk, cân nhắc clear hoặc refresh trước khi đọc tiếp.

### 8.7. Coi cascade là cách thay thế thiết kế vòng đời

Cascade và orphan removal có thể hữu ích khi entity con thực sự thuộc vòng đời của aggregate cha. Nếu entity liên quan được chia sẻ giữa nhiều aggregate hoặc có vòng đời độc lập, cascade remove có thể xóa dữ liệu ngoài ý muốn. Hãy chọn cascade theo quan hệ sở hữu trong nghiệp vụ, không chỉ theo cấu trúc object.

### 8.8. Đánh giá hiệu năng mà không quan sát SQL

Khi có vấn đề, kiểm tra câu SQL, số lần truy vấn, số dòng trả về, execution plan và index. Cần phân biệt chi phí do database, do mapping, do tải quan hệ hay do logic Java. Tăng cache hoặc đổi framework khi chưa biết nút thắt thường không giải quyết đúng nguyên nhân.

## 9. Ví dụ chọn công cụ theo tình huống

### Tình huống A: Xác nhận đơn hàng

Use case tải một đơn hàng, kiểm tra trạng thái, cập nhật trạng thái xác nhận và ghi nhận thay đổi trong cùng transaction. Đơn hàng có các dòng hàng thuộc vòng đời của nó. Đây là dạng nghiệp vụ phù hợp với JPA.

Ví dụ minh họa phần service:

```java
@Transactional
public void confirmOrder(Long orderId) {
    Order order = orderRepository.findById(orderId)
        .orElseThrow(() -> new EntityNotFoundException("Order not found"));

    order.confirm();
}
```

Giả sử `order` là entity managed trong transaction, thay đổi do `confirm()` thực hiện sẽ được dirty checking ghi nhận. Mẫu này phù hợp khi phương thức nghiệp vụ nằm trên entity/aggregate và các thay đổi cần commit cùng nhau.

### Tình huống B: Báo cáo doanh thu theo khách hàng

Use case chỉ cần mã khách hàng và tổng doanh thu trong một khoảng thời gian. Nó không cần tải entity đơn hàng hay quản lý vòng đời của chúng. Một truy vấn tổng hợp SQL và DTO là phù hợp hơn.

Ví dụ minh họa với `JdbcClient`:

```java
record RevenueRow(long customerId, BigDecimal revenue) {}

List<RevenueRow> rows = jdbcClient.sql("""
        select customer_id, sum(total_amount) as revenue
        from purchase_order
        where created_at >= :from
        group by customer_id
        """)
    .param("from", from)
    .query((rs, rowNum) -> new RevenueRow(
        rs.getLong("customer_id"),
        rs.getBigDecimal("revenue")
    ))
    .list();
```

Đây là đoạn minh họa trong một component Spring đã được inject `JdbcClient`; cần khai báo kiểu `from` và import các kiểu Java tương ứng trong chương trình thực tế. SQL nói rõ dữ liệu cần lấy và database thực hiện phép tổng hợp.

### Tình huống C: Nhập dữ liệu lớn

Nếu phải nhập hàng trăm nghìn hoặc hàng triệu dòng, hãy cân nhắc batch insert qua JDBC, công cụ bulk load của database hoặc một pipeline chuyên dụng. Nếu vẫn dùng JPA, cần xử lý theo batch, flush và clear persistence context định kỳ, đồng thời đo bộ nhớ và thời gian thực thi. Không nên giữ toàn bộ entity trong một persistence context lớn.

### Tình huống D: API reactive truy cập relational database

Nếu yêu cầu thực sự là non-blocking từ HTTP đến database, đánh giá R2DBC và thiết kế transaction theo API reactive. Không thể biến một lời gọi JPA blocking thành non-blocking chỉ bằng cách bọc nó trong `Mono` hoặc chạy trên scheduler khác; thao tác JDBC vẫn chiếm một thread trong lúc chờ.

### Tình huống E: Quản lý document có cấu trúc linh hoạt

Nếu dữ liệu chính là document và các truy vấn xoay quanh document đó, dùng MongoDB hoặc một document store tương ứng. Việc ánh xạ document thành entity quan hệ rồi lưu qua JPA sẽ làm tăng chuyển đổi và không tận dụng mô hình của database.

## 10. Checklist trước khi chọn công cụ

Trước khi chốt thiết kế, hãy trả lời các câu hỏi sau:

- Dữ liệu chính là relational, document, key-value, graph hay một loại store khác?
- Use case cần thao tác trên entity/aggregate hay chủ yếu cần trả về một tập kết quả truy vấn?
- Có cần persistence context, dirty checking, quan hệ entity và optimistic locking không?
- Truy vấn có nhiều join, tổng hợp, CTE, window function hoặc phụ thuộc mạnh vào SQL của database không?
- Khối lượng dữ liệu và tốc độ ghi có phù hợp với việc quản lý entity trong bộ nhớ không?
- Ứng dụng có yêu cầu reactive end-to-end hay mô hình blocking là đủ?
- Transaction boundary, rollback và đồng bộ trạng thái giữa các công cụ được xác định như thế nào?
- Nhóm có thể quan sát và tối ưu SQL thực tế không?
- Chi phí học, vận hành và bảo trì của công cụ có tương xứng với lợi ích không?

Nếu câu trả lời cho thấy entity và vòng đời nghiệp vụ là trung tâm, bắt đầu với JPA là hợp lý. Nếu SQL, khối lượng dữ liệu hoặc mô hình reactive là trung tâm, hãy chọn công cụ thể hiện trực tiếp yêu cầu đó. Có thể dùng JPA và công cụ SQL-first cùng nhau khi mỗi công cụ có ranh giới trách nhiệm rõ ràng.

## 11. Kết luận

JPA là lựa chọn mạnh cho ứng dụng Java dùng cơ sở dữ liệu quan hệ, nơi nghiệp vụ được tổ chức quanh entity, aggregate và transaction. Spring Data JPA giúp triển khai repository thuận tiện, còn JPA provider đảm nhận việc quản lý persistence context và chuyển thay đổi entity thành SQL.

Spring Data JDBC phù hợp với persistence đơn giản theo aggregate; Spring JDBC, MyBatis và jOOQ phù hợp khi cần kiểm soát SQL; JDBC batch hoặc tính năng database phù hợp với luồng dữ liệu lớn; R2DBC dành cho nhu cầu reactive thực sự; driver và Spring Data chuyên biệt dành cho NoSQL.

Không có một công cụ tối ưu cho mọi kiểu truy cập dữ liệu. Hãy chọn theo workload cụ thể, kiểm tra SQL và transaction thực tế, rồi chỉ kết hợp nhiều công cụ khi ranh giới của chúng đủ rõ để hệ thống vẫn dễ hiểu và bảo trì.
