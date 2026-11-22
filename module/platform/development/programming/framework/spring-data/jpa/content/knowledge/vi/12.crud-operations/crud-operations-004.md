# saveAll và sự khác biệt với câu lệnh chèn theo lô

## 1. Ba khái niệm thường bị nhầm lẫn

Trong Spring Data JPA, saveAll() nhận một tập entity và lưu chúng. Tên phương thức dễ khiến người đọc nghĩ rằng toàn bộ danh sách sẽ được gửi xuống database bằng một câu INSERT hoặc một batch duy nhất. Thực tế, cần phân biệt ba cơ chế:

1. **saveAll() của Spring Data JPA:** API repository duyệt qua các entity và gọi save() cho từng entity. Đây là thao tác ở cấp entity.
2. **JDBC batching của Hibernate:** Hibernate gom nhiều lệnh INSERT có cùng cấu trúc vào JDBC batch và gửi theo nhóm qua PreparedStatement. Đây mới là batching ở tầng JDBC.
3. **Multi-row INSERT hoặc native bulk load:** database nhận một câu SQL có nhiều bộ giá trị, hoặc một lệnh nạp dữ liệu chuyên dụng. Đây là cơ chế bulk ở tầng database.

Ba cơ chế có thể được kết hợp trong một ứng dụng. Ví dụ, saveAll() có thể tạo các thao tác persist; Hibernate gom các INSERT đó thành JDBC batch nếu cấu hình và điều kiện cho phép. Tuy nhiên, saveAll() tự nó không bảo đảm có JDBC batch, cũng không bảo đảm database chỉ nhận một câu INSERT.

Lựa chọn đúng phụ thuộc vào số lượng bản ghi, loại ID, yêu cầu lifecycle của entity, transaction, bộ nhớ và khả năng của database/driver.

## 2. saveAll() thực sự làm gì?

### 2.1. saveAll là vòng lặp trên save

Trong implementation thông dụng của SimpleJpaRepository, saveAll() duyệt collection đầu vào và gọi save() cho từng entity, sau đó trả về danh sách kết quả.

Luồng khái quát:

```java
@Transactional
public <S extends T> List<S> saveAll(Iterable<S> entities) {
    List<S> result = new ArrayList<>();

    for (S entity : entities) {
        result.add(save(entity));
    }

    return result;
}
```

Đây là mô tả rút gọn của implementation Spring Data JPA; chi tiết source có thể thay đổi theo phiên bản. Điểm quan trọng là API xử lý từng entity qua save(), không phải một lệnh bulk INSERT duy nhất.

saveAll() vẫn hữu ích:
- Giảm code lặp ở service.
- Giữ API repository nhất quán với save().
- Tham gia transaction theo cấu hình repository và transaction bên ngoài.
- Cho phép JPA provider áp dụng cơ chế persistence, mapping, callback và batching nếu phù hợp.

Nhưng không nên suy luận số câu SQL từ số lần gọi saveAll(). Cần quan sát SQL và cấu hình Hibernate thực tế.

### 2.2. save() chọn persist hay merge

save() không phải lúc nào cũng gọi EntityManager.persist(). Spring Data JPA xác định entity có mới hay không, sau đó:

- Entity mới: gọi persist(entity), thường trả lại chính instance đầu vào.
- Entity không mới: gọi merge(entity), trả về instance managed nhận trạng thái từ object truyền vào.

Cơ chế nhận diện entity mới mặc định thường kiểm tra:
1. Nếu entity có thuộc tính @Version không phải kiểu primitive, giá trị version null cho biết entity mới.
2. Nếu không có version phù hợp, kiểm tra identifier: ID null thường được xem là mới.
3. Nếu entity implement Persistable, Spring Data dùng isNew() do entity cung cấp.

Điều này quan trọng với ID tự gán. Nếu một entity mới có ID được gán sẵn, Spring Data có thể xem nó là entity đã tồn tại và chọn merge(). Trong trường hợp đó, provider có thể phải đọc trạng thái hiện có hoặc thực hiện xử lý khác trước khi ghi. Không giả định entity mới có ID khác null sẽ luôn được persist.

Nếu domain dùng assigned ID, hãy thiết kế chiến lược nhận diện new rõ ràng, ví dụ dùng nullable @Version hoặc implement Persistable với isNew() phù hợp và cập nhật trạng thái sau khi persist.

### 2.3. Vì sao merge có thể làm chậm saveAll?

merge() có semantics khác persist(). JPA sao chép trạng thái từ object đầu vào sang một instance managed. Object đầu vào không nhất thiết trở thành instance managed. Vì vậy cần dùng giá trị trả về của save() hoặc saveAll() khi tiếp tục thao tác trong cùng persistence context.

Với entity detached hoặc entity có ID được gán sẵn, merge có thể khiến provider cần kiểm tra trạng thái hiện có và tạo thêm SELECT/UPDATE tùy tình huống. Một danh sách lớn bị nhận diện nhầm là detached/existing có thể phát sinh nhiều công việc hơn mong đợi.

Ví dụ:

```java
List<Employee> savedEmployees =
    employeeRepository.saveAll(newEmployees);

// Dùng savedEmployees nếu cần tiếp tục thao tác
// trên các instance được repository trả về.
```

Nếu tất cả entity là mới và được nhận diện đúng, persist path thường phù hợp hơn cho insert. Tuy nhiên, muốn tối ưu thật sự vẫn phải xem ID generation và JDBC batching.

### 2.4. saveAll không đồng nghĩa với flush hay commit

saveAll() thường đăng ký các thay đổi vào persistence context. SQL có thể được thực thi khi flush hoặc khi transaction commit, tùy provider và tình huống.

- saveAll(): yêu cầu lưu từng entity qua persist/merge.
- saveAllAndFlush(): gọi saveAll rồi flush persistence context.
- flush(): đồng bộ thay đổi đang chờ xuống database; chưa có nghĩa transaction đã commit.
- commit(): hoàn tất transaction và làm thay đổi trở nên bền vững theo transaction semantics.

saveAllAndFlush() không phải bulk insert. Nó chỉ ép provider đồng bộ các thay đổi hiện tại sớm hơn. Nếu transaction còn mở, database vẫn có thể rollback khi transaction thất bại.

## 3. Hibernate JDBC batching là gì?

### 3.1. Cơ chế PreparedStatement batch

JDBC hỗ trợ gom nhiều lần thực thi cùng một PreparedStatement thành batch:

```java
PreparedStatement ps = connection.prepareStatement(
    "insert into employee(name, department_id) values (?, ?)"
);

ps.setString(1, "An");
ps.setLong(2, 10L);
ps.addBatch();

ps.setString(1, "Binh");
ps.setLong(2, 10L);
ps.addBatch();

ps.executeBatch();
```

Đoạn mã minh họa cho thấy driver nhận nhiều bộ tham số cho cùng SQL statement rồi thực thi theo batch. Hibernate có thể sử dụng cơ chế này khi persist nhiều entity có câu INSERT tương thích.

JDBC batch giảm số lần round-trip so với việc gửi từng lệnh riêng biệt. Nó vẫn có thể chứa nhiều lần thực thi statement; driver/database quyết định cách tối ưu ở tầng giao thức.

### 3.2. Cấu hình Hibernate batching

Với Spring Boot, có thể cấu hình:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          batch_size: 50
        order_inserts: true
        order_updates: true
```

Ý nghĩa:

- hibernate.jdbc.batch_size: số statement tối đa Hibernate gom trong một batch.
- hibernate.order_inserts: sắp xếp INSERT theo entity/table để tăng khả năng gom các câu SQL cùng dạng.
- hibernate.order_updates: sắp xếp UPDATE theo entity/table, có thể cải thiện batching và giảm một số xung đột lock.

Giá trị 50 chỉ là điểm bắt đầu để đo, không phải con số tối ưu cho mọi hệ thống. Batch lớn hơn có thể giảm round-trip nhưng tăng bộ nhớ và kích thước request; batch quá nhỏ làm mất một phần lợi ích.

Hibernate chỉ gom được những statement tương thích. Nếu các entity tạo ra SQL khác nhau do mapping, dynamic insert hoặc cấu trúc dữ liệu khác nhau, số statement gom được có thể giảm.

### 3.3. saveAll kết hợp với JDBC batching

Khi gọi saveAll() cho các entity mới, Spring Data gọi persist() từng entity. Hibernate có thể trì hoãn INSERT trong persistence context và gom các lệnh cùng dạng thành batch lúc flush.

Luồng điển hình:

1. Service gọi repository.saveAll(entities).
2. Spring Data xác định entity mới và gọi EntityManager.persist() cho từng entity.
3. Hibernate quản lý entity trong persistence context.
4. Khi flush, Hibernate tạo các INSERT statement.
5. Nếu cấu hình batching và ID strategy cho phép, Hibernate đưa statement vào JDBC batch.
6. JDBC driver gửi batch xuống database.

Do đó, saveAll có thể sử dụng batching nhưng bản thân saveAll không tạo batch. Nếu thiếu cấu hình Hibernate, ID strategy không phù hợp hoặc statement không tương thích, Hibernate có thể thực thi từng INSERT riêng.

## 4. ID generation ảnh hưởng trực tiếp tới batching

### 4.1. GenerationType.IDENTITY

Với IDENTITY, database sinh ID khi INSERT. Hibernate cần nhận ID để hoàn tất trạng thái entity. Trong Hibernate, IDENTITY thường buộc INSERT thực thi ngay và ngăn JDBC batching cho INSERT của entity dùng chiến lược này.

Ví dụ:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Đây là lựa chọn đơn giản khi database dùng identity/auto-increment, nhưng có thể làm giảm throughput insert số lượng lớn.

### 4.2. GenerationType.SEQUENCE

Với database hỗ trợ sequence, Hibernate có thể lấy ID trước khi INSERT. Nhờ đó, provider có thể trì hoãn và gom các INSERT thành batch.

```java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "employee_seq"
)
@SequenceGenerator(
    name = "employee_seq",
    sequenceName = "employee_seq",
    allocationSize = 50
)
private Long id;
```

allocationSize cho phép provider cấp phát ID theo nhóm, giảm số lần gọi sequence. Cấu hình sequence và allocation size phải nhất quán với database và cách Hibernate quản lý optimizer. Không tự thay đổi allocationSize trong hệ thống đang chạy mà không kiểm tra schema, generator và các instance ứng dụng.

Sequence không bảo đảm mọi INSERT đều batch được, nhưng thường thuận lợi hơn IDENTITY cho batching của Hibernate.

### 4.3. Assigned ID hoặc UUID

Nếu ID được ứng dụng tạo trước, provider không cần chờ database trả ID để biết identity của entity. Các chiến lược này có thể thuận lợi cho batching, nhưng cần bảo đảm Spring Data nhận diện đúng entity mới và database có kiểu cột/index phù hợp.

Đừng chọn UUID hoặc assigned ID chỉ vì batching. Cần cân nhắc kích thước index, locality, tính duy nhất, quy trình đồng bộ và semantics domain.

## 5. Ví dụ sử dụng saveAll đúng cách

### 5.1. Lưu một danh sách nhỏ

Với số lượng entity vừa phải:

```java
@Service
public class EmployeeImportService {

    private final EmployeeRepository employeeRepository;

    public EmployeeImportService(EmployeeRepository employeeRepository) {
        this.employeeRepository = employeeRepository;
    }

    @Transactional
    public List<Employee> importEmployees(List<Employee> employees) {
        return employeeRepository.saveAll(employees);
    }
}
```

Transaction bao quanh use case. Repository lưu từng entity thông qua save(); Hibernate có thể batching nếu cấu hình phù hợp. Kết quả trả về nên được dùng khi cần tiếp tục thao tác vì merge có thể trả instance managed khác object đầu vào.

### 5.2. Chia dữ liệu thành chunk và flush/clear

Khi số lượng lớn, không nên giữ tất cả entity trong persistence context tới cuối một transaction rất dài. Có thể chia input thành chunk:

```java
@Service
public class EmployeeImportService {

    private static final int CHUNK_SIZE = 50;

    private final EmployeeRepository employeeRepository;
    private final EntityManager entityManager;

    public EmployeeImportService(
        EmployeeRepository employeeRepository,
        EntityManager entityManager
    ) {
        this.employeeRepository = employeeRepository;
        this.entityManager = entityManager;
    }

    @Transactional
    public void importEmployees(List<Employee> employees) {
        for (int start = 0; start < employees.size(); start += CHUNK_SIZE) {
            int end = Math.min(start + CHUNK_SIZE, employees.size());
            List<Employee> chunk = employees.subList(start, end);

            employeeRepository.saveAll(chunk);

            entityManager.flush();
            entityManager.clear();
        }
    }
}
```

Ý nghĩa:

- saveAll xử lý các entity trong chunk.
- flush gửi các thay đổi đang chờ xuống database và thực thi các batch đủ điều kiện.
- clear detach tất cả entity đang managed, giúp giảm bộ nhớ persistence context.
- Chunk size cần phù hợp với batch_size và tải thực tế.

Đây vẫn là một transaction duy nhất vì method service có @Transactional. Flush/clear không commit từng chunk. Nếu toàn bộ import kéo dài, transaction vẫn có thể giữ lock và connection lâu. Nếu cần commit từng chunk, phải thiết kế transaction boundary riêng và chấp nhận khả năng một số chunk đã commit trước khi chunk sau thất bại.

Không giữ tham chiếu tới entity rồi giả định chúng vẫn managed sau clear(). Nếu cần xử lý tiếp, dùng ID hoặc tải lại entity trong persistence context mới.

### 5.3. Chọn chunk size và batch size

Hai giá trị có mục đích khác nhau:

- JDBC batch size quyết định số statement Hibernate gom vào một lần executeBatch().
- Chunk size quyết định số entity được xử lý trước khi flush/clear trong vòng lặp ứng dụng.

Ví dụ batch size 50 và chunk size 500 có thể tạo nhiều JDBC batch trong một chunk. Không nhất thiết hai giá trị phải bằng nhau, nhưng chunk thường là bội số của batch size để dễ dự đoán.

Cần đo:
- Heap usage và thời gian GC.
- Thời gian flush.
- Số batch và số statement thực tế.
- Thời gian transaction và lock.
- Throughput tổng thể.
- Khả năng rollback khi lỗi.

Không chọn con số chỉ dựa trên ví dụ trong tài liệu.

## 6. JDBC batch, multi-row INSERT và native bulk load khác nhau

| Cơ chế | Cách thực thi | Điểm mạnh | Giới hạn |
|---|---|---|---|
| saveAll() | Lặp qua entity và gọi save() | Giữ semantics repository/JPA | Không tự bảo đảm batching |
| Hibernate JDBC batch | Gom nhiều statement tương thích trong PreparedStatement batch | Giữ phần lớn lifecycle ORM, giảm round-trip | Phụ thuộc ID strategy, SQL shape, driver và persistence context |
| Multi-row INSERT | Một câu INSERT chứa nhiều bộ VALUES | Ít statement ở database | Cú pháp và giới hạn tham số phụ thuộc database |
| JDBC batch qua JdbcTemplate | Ứng dụng gửi batch PreparedStatement trực tiếp | Kiểm soát SQL và batch size | Bỏ qua entity lifecycle/cascade |
| Native bulk load | Công cụ nạp dữ liệu riêng của database | Thường phù hợp dữ liệu cực lớn | Phụ thuộc database, format và quy trình vận hành |

### 6.1. Multi-row INSERT

Một câu SQL multi-row có dạng:

```sql
insert into employee(name, department_id)
values
    ('An', 10),
    ('Binh', 10),
    ('Chi', 11);
```

Đây là một SQL statement chứa nhiều bộ giá trị. Nó khác JDBC batch, nơi driver nhận nhiều lần bind parameter cho cùng PreparedStatement.

Multi-row INSERT có thể nhanh, nhưng phải cân nhắc:
- Giới hạn số parameter và kích thước statement của database/driver.
- Cách lấy generated keys.
- Kích thước câu SQL và bộ nhớ khi tạo câu lệnh.
- Khả năng tái sử dụng prepared statement.
- Constraint, trigger và transaction behavior.

Không nên ghép chuỗi SQL từ dữ liệu người dùng. Luôn dùng bind parameters hoặc API an toàn.

### 6.2. JDBC batch với Spring JdbcTemplate

Nếu use case là import dữ liệu thuần SQL và không cần lifecycle entity, có thể dùng Spring JDBC:

```java
int[][] counts = jdbcTemplate.batchUpdate(
    "insert into employee(name, department_id) values (?, ?)",
    employees,
    500,
    (ps, employee) -> {
        ps.setString(1, employee.name());
        if (employee.departmentId() == null) {
            ps.setNull(2, Types.BIGINT);
        } else {
            ps.setLong(2, employee.departmentId());
        }
    }
);
```

Ví dụ dùng overload batchUpdate với Collection và ParameterizedPreparedStatementSetter. Cần khai báo JdbcTemplate và các kiểu Java/import tương ứng trong component thực tế.

Ưu điểm là kiểm soát câu SQL và batch size rõ ràng. Nhược điểm là JDBC không tự thực thi:
- JPA cascade và orphanRemoval.
- Entity lifecycle callbacks như @PrePersist.
- Bean Validation được kích hoạt theo luồng JPA.
- Dirty checking và đồng bộ persistence context.
- Mapping association và conversion của entity.

Nếu dùng JDBC trong cùng transaction với JPA, cần bảo đảm cả hai cùng tham gia đúng transaction manager/DataSource. Sau JDBC update, entity đang managed có thể stale; cần refresh hoặc clear khi phù hợp.

### 6.3. Database-native bulk load

Với hàng triệu dòng, công cụ chuyên dụng như PostgreSQL COPY hoặc bulk loader của database có thể nhanh hơn ORM/JDBC batch. Đổi lại, cần thiết kế:
- Quy trình staging và validation.
- Quyền database phù hợp.
- Kiểm tra constraint và dữ liệu lỗi.
- Cập nhật index/statistics khi cần.
- Transaction, retry và khả năng chạy lại.
- Đồng bộ cache và các projection phụ thuộc.

Không đưa native bulk load vào hệ thống chỉ để tối ưu một tác vụ nhỏ. Hãy đo và chọn khi throughput thực sự là vấn đề.

## 7. Những yếu tố làm Hibernate không batch được như mong đợi

### 7.1. IDENTITY

Như đã nêu, IDENTITY thường yêu cầu INSERT ngay để lấy ID, hạn chế batching của Hibernate. Nếu insert throughput quan trọng và database hỗ trợ sequence, cân nhắc SEQUENCE với allocation phù hợp.

### 7.2. SQL không cùng hình dạng

Hibernate chỉ gom các statement tương thích. Nếu các entity có dynamic insert tạo ra tập cột khác nhau tùy giá trị null, SQL có thể khác nhau và giảm khả năng batch. Mapping khác nhau hoặc thao tác xen kẽ nhiều bảng cũng ảnh hưởng số lệnh trong batch.

### 7.3. Batch bị flush sớm

Một truy vấn, thao tác cần generated ID hoặc flush mode có thể khiến Hibernate flush trước thời điểm dự kiến. Nếu application gọi flush liên tục sau từng entity, batch không có đủ statement để gom.

Không gọi saveAndFlush() trong vòng lặp import trừ khi có yêu cầu đồng bộ thật sự sau từng entity. Thông thường, saveAll() rồi flush theo chunk sẽ có cơ hội batching tốt hơn.

### 7.4. Entity state không đúng

Nếu entity mới bị nhận diện thành detached và đi qua merge(), provider có thể thực hiện thêm thao tác kiểm tra hoặc cập nhật. Hãy xác nhận isNew strategy, ID và @Version.

### 7.5. Driver hoặc database

JDBC driver có thể có tham số tối ưu batch riêng. Ví dụ PostgreSQL driver hỗ trợ rewrite batch INSERT trong một số trường hợp qua tham số reWriteBatchedInserts. Khả năng và hiệu quả phụ thuộc phiên bản driver, SQL và cấu hình.

Không bật tham số driver mà không kiểm tra tài liệu đúng phiên bản và đo kết quả. JDBC batch vẫn có thể hoạt động mà không rewrite thành một multi-row statement; hai cơ chế này không đồng nhất.

## 8. Lifecycle và tính đúng đắn khi dùng đường insert nhanh

saveAll/persist đi qua JPA provider và có thể áp dụng entity lifecycle callbacks, cascade, Bean Validation, auditing listener và mapping converters theo cấu hình.

Đường JDBC hoặc native bulk insert bỏ qua phần lớn semantics entity đó. Nếu ứng dụng dựa vào @PrePersist để tạo mã, auditing listener để điền createdAt, callback để kiểm tra invariant hoặc cascade để lưu entity liên quan, JDBC trực tiếp không tự thực hiện những hành vi này.

Trước khi chuyển sang JDBC/native SQL, hãy đưa những quy tắc bắt buộc vào tầng phù hợp:
- Validation nghiệp vụ ở service/domain.
- Default và constraint quan trọng ở database.
- Audit columns được gán tường minh hoặc do database quản lý.
- Quan hệ được ghi đúng thứ tự và bảo toàn foreign key.
- Các sự kiện sau lưu được phát ra ở ranh giới transaction phù hợp.

Không để đường import nhanh tạo dữ liệu khác quy tắc với đường CRUD thông thường.

## 9. Transaction, lỗi giữa batch và khả năng chạy lại

### 9.1. Một transaction cho toàn bộ import

Một service method có @Transactional bao quanh saveAll hoặc nhiều chunk có thể bảo đảm toàn bộ thay đổi commit/rollback cùng nhau. Nhưng transaction rất dài có thể giữ connection, lock và tài nguyên database lâu.

Flush/clear theo chunk giảm memory pressure của persistence context, nhưng không chia transaction. Nếu transaction cuối cùng rollback, các thao tác đã flush trong transaction đó vẫn bị rollback theo database transaction.

### 9.2. Transaction riêng cho từng chunk

Nếu xử lý theo transaction riêng cho từng chunk, hệ thống có thể commit tiến độ từng phần. Cách này tăng khả năng resume và giảm transaction duration, nhưng không còn tính nguyên tử toàn bộ file import.

Cần có:
- Khóa/idempotency key để tránh insert trùng khi retry.
- Trạng thái tiến độ theo chunk.
- Cơ chế ghi nhận lỗi và xử lý lại.
- Quy tắc xử lý chunk đã commit khi chunk sau thất bại.
- Transaction boundary thực sự tách biệt; self-invocation trong cùng bean có thể không đi qua Spring proxy như mong muốn.

Không dùng REQUIRES_NEW hoặc transaction per chunk một cách tùy tiện. Hãy chọn dựa trên yêu cầu nhất quán và khả năng phục hồi.

### 9.3. Batch failure

JDBC batch có thể trả về update counts hoặc lỗi ở một phần batch tùy driver/database. Khi batch lỗi, cần xem transaction đã bị đánh dấu rollback-only hay chưa và database hỗ trợ rollback ra sao. Không tiếp tục dùng persistence context nếu trạng thái transaction không còn hợp lệ.

Sau lỗi, log cần ghi nhận batch/chunk, khóa nghiệp vụ hoặc ID có thể truy vết, nhưng không ghi dữ liệu nhạy cảm. Retry phải an toàn với unique constraint và side effect ngoài database.

## 10. Cách kiểm chứng saveAll có batching thật hay không

Không kết luận dựa trên tên method. Hãy đo:

1. Bật log SQL ở local/test.
2. Bật Hibernate statistics hoặc công cụ quan sát JDBC như datasource-proxy/P6Spy.
3. Insert một lượng dữ liệu đủ lớn, không chỉ vài entity.
4. So sánh số lần prepare/execute, batch count và thời gian.
5. Chạy lại với IDENTITY và SEQUENCE nếu database hỗ trợ cả hai.
6. Thử các cấu hình batch_size khác nhau.
7. Kiểm tra driver rewrite option nếu có.
8. Xác nhận dữ liệu cuối cùng, generated IDs, callbacks và constraint vẫn đúng.

Ví dụ bật Hibernate statistics:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        generate_statistics: true
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

Statistics có thể cho biết số entity insert, số statement và số batch tùy phiên bản Hibernate. Bind logging có thể làm lộ dữ liệu nhạy cảm; chỉ bật có kiểm soát và không để ở production.

Hãy so sánh các cách trên cùng database, cùng dữ liệu và cùng transaction assumptions. Nếu một cách nhanh hơn nhưng bỏ qua callback, validation hoặc audit bắt buộc, đó không phải phép so sánh tương đương.

## 11. Checklist lựa chọn

- [ ] Dữ liệu là entity mới hay detached entity?
- [ ] Spring Data nhận diện isNew đúng với ID và @Version chưa?
- [ ] Có thực sự cần saveAll hay có thể dùng persist cho luồng tạo mới rõ ràng?
- [ ] IDENTITY có đang ngăn Hibernate JDBC batching không?
- [ ] Batch size và order_inserts/order_updates đã được cấu hình và đo chưa?
- [ ] Có saveAndFlush/flush quá thường xuyên không?
- [ ] Persistence context có quá lớn và cần flush/clear theo chunk không?
- [ ] Transaction là một lần toàn bộ hay commit từng chunk?
- [ ] Driver/database có hỗ trợ tối ưu batch hoặc native bulk load không?
- [ ] Đường JDBC/native có bỏ qua callback, validation, cascade hoặc auditing nào không?
- [ ] Generated IDs, foreign keys và unique constraints có được xử lý đúng không?
- [ ] Đã đo SQL và kiểm thử trên database tương ứng với production chưa?

## 12. Kết luận

saveAll() là tiện ích repository để lưu nhiều entity bằng cách gọi save() cho từng phần tử. Nó không tự tạo một câu INSERT duy nhất và cũng không bảo đảm JDBC batching. Hibernate JDBC batching là cơ chế gom statement ở tầng JDBC; multi-row INSERT và native bulk load là những cơ chế riêng của database.

Muốn saveAll đạt hiệu năng tốt, cần entity được nhận diện đúng là mới, ID strategy hỗ trợ batching, Hibernate được cấu hình batch_size và SQL có thể gom nhóm. Với dữ liệu lớn, chia chunk, flush/clear và thiết kế transaction phù hợp giúp kiểm soát bộ nhớ và thời gian xử lý.

Khi cần throughput cao hơn, JDBC batch hoặc native bulk load có thể phù hợp, nhưng chúng bỏ qua nhiều semantics của JPA như cascade, lifecycle callback, validation và persistence context. Hãy chọn dựa trên yêu cầu nghiệp vụ, đo SQL thực tế và kiểm tra tính nhất quán của dữ liệu trước khi chuyển sang đường ghi nhanh.