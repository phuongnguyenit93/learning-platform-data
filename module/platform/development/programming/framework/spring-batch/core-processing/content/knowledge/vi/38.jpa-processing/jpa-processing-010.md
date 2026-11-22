# Restart với database item trong Spring Batch JPA

Khi một Spring Batch job đọc dữ liệu bằng JPA, job có thể xử lý hàng nghìn hoặc hàng triệu entity. Nếu process dừng giữa chừng, lần chạy tiếp theo cần tiếp tục từ checkpoint đã commit gần nhất. Nếu reader bắt đầu lại từ đầu, job có thể tốn nhiều thời gian, ghi trùng dữ liệu hoặc tạo side effect lặp. Nếu reader bỏ qua quá nhiều item, dữ liệu có thể bị mất.

Với JPA, reader thường dùng là JpaPagingItemReader. Reader này lấy dữ liệu theo từng trang bằng JPQL, đồng thời hỗ trợ lưu trạng thái để Spring Batch khôi phục vị trí đọc khi restart. Tuy nhiên, checkpoint chỉ có ý nghĩa khi JobInstance, query, parameters, thứ tự dữ liệu và tập dữ liệu nguồn vẫn tương thích với lần chạy trước.

Bài học này giải thích cách restart database item với JPA, cách reader lưu và khôi phục state, các giới hạn của phân trang theo offset, vòng đời EntityManager, transaction, thay đổi dữ liệu nguồn và cách kiểm thử restart thực tế.

## 1. Restart trong Spring Batch nghĩa là gì?

Restart là tiếp tục một job/step execution đã dừng hoặc thất bại, dựa trên metadata và checkpoint đã lưu. Spring Batch không giữ nguyên bộ nhớ của process cũ; nó khởi tạo execution mới và khôi phục những trạng thái bền vững cần thiết.

Ví dụ step có chunk size 3:

~~~text
Chunk 1: Customer 1, 2, 3 -> ghi thành công -> COMMIT
Chunk 2: Customer 4, 5, 6 -> writer lỗi -> ROLLBACK
JobExecution 1 -> FAILED

Restart cùng JobInstance:
  Reader tiếp tục sau checkpoint của chunk 1
  Customer 4, 5, 6 được đọc lại
  Sau đó tiếp tục Customer 7, 8, 9, ...
~~~

Các item trong chunk chưa commit có thể được đọc và xử lý lại. Vì vậy, restart không đồng nghĩa mỗi item chỉ được xử lý đúng một lần trong mọi failure window. Writer và các side effect cần được thiết kế an toàn khi item được gửi lại.

## 2. JobInstance và JobExecution

Spring Batch phân biệt một lần chạy logic với một lần thực thi cụ thể:

- JobInstance được xác định bởi job name và identifying JobParameters.
- JobExecution là một lần thực thi của JobInstance.
- Một JobInstance có thể có nhiều JobExecution nếu lần chạy trước thất bại hoặc bị dừng và được restart.

Ví dụ:

~~~text
Job: importCustomers
Identifying parameter: businessDate=2026-11-15

JobInstance A
  |
  +-- JobExecution 1 -> FAILED
  |
  +-- JobExecution 2 -> COMPLETED
~~~

Để restart cùng job instance, truyền lại cùng identifying parameters. Nếu đổi businessDate, tenantId hoặc batchId là identifying parameter, Spring Batch tạo một JobInstance mới và reader không dùng checkpoint của instance cũ.

Không tạo một run.id mới khi mục tiêu là tiếp tục execution thất bại. RunIdIncrementer thường tạo tham số nhận diện mới cho lần chạy logic mới. Nó không phải thao tác khôi phục checkpoint.

Một JobInstance đã hoàn tất không thể được chạy lại như một restart thông thường với cùng identifying parameters. Muốn xử lý một batch mới, dùng parameter nhận diện mới theo nghiệp vụ.

## 3. ExecutionContext lưu checkpoint

ExecutionContext là một map key/value do Spring Batch quản lý và lưu qua JobRepository. Mỗi StepExecution có step execution context; JobExecution cũng có job execution context.

Reader có thể triển khai ItemStream với lifecycle:

- open(ExecutionContext): mở tài nguyên và khôi phục checkpoint đã lưu.
- update(ExecutionContext): ghi trạng thái hiện tại vào execution context.
- close(): giải phóng tài nguyên reader.

JpaPagingItemReader hỗ trợ ItemStream và lưu số lượng item đã đọc để xác định vị trí tiếp tục. Khi step commit chunk, trạng thái reader được cập nhật trong execution context. Khi chunk rollback, checkpoint của chunk chưa commit không trở thành mốc restart mới.

Chỉ lưu dữ liệu có thể serialize và khôi phục, ví dụ số item đã đọc, page position hoặc business key do reader tùy chỉnh quản lý. Không lưu EntityManager, Query, managed entity hoặc JPA resource vào ExecutionContext.

## 4. JpaPagingItemReader là gì?

JpaPagingItemReader đọc entity hoặc projection từ database bằng JPQL theo từng trang. Mỗi lần cần trang mới, reader thực hiện query với first result và maximum result được tính từ page size.

Reader thường được cấu hình với:

- EntityManagerFactory: factory dùng để tạo EntityManager.
- Query string: JPQL dùng để lấy dữ liệu.
- Parameter values: giá trị bind vào named parameter.
- Page size: số item trong một trang.
- Name: tên ổn định để tạo key trong execution context.
- Save state: bật lưu checkpoint khi cần restart.

Ví dụ:

~~~java
@Bean
@StepScope
JpaPagingItemReader<Customer> customerReader(
        EntityManagerFactory entityManagerFactory,
        @Value("#{jobParameters['customerStatus']}") String status) {

    return new JpaPagingItemReaderBuilder<Customer>()
        .name("customerJpaReader")
        .entityManagerFactory(entityManagerFactory)
        .queryString("""
            select c
            from Customer c
            where c.status = :status
            order by c.id
            """)
        .parameterValues(Map.of("status", status))
        .pageSize(200)
        .saveState(true)
        .build();
}
~~~

Ví dụ dùng Spring Batch 5 builder API. Tên package, builder và một số phương thức có thể khác ở phiên bản Spring Batch cũ; hãy dùng API đúng với dependency của dự án.

## 5. Vì sao cần tên reader ổn định?

Tên reader được dùng để tạo key trong execution context. Ví dụ:

~~~java
.name("customerJpaReader")
~~~

Nếu đổi tên reader giữa lần chạy đầu và lần restart, reader mới có thể tìm một key state khác và không khôi phục được checkpoint đã lưu theo tên cũ.

Quy tắc:

- Đặt tên có ý nghĩa và duy nhất trong step.
- Giữ tên ổn định qua các lần restart của cùng JobInstance.
- Không dùng cùng tên cho hai reader stateful độc lập trong cùng step.
- Khi thay đổi reader name hoặc cấu trúc state, đánh giá compatibility với execution cũ còn có thể restart.

Đổi tên reader có thể giống như thay đổi định dạng checkpoint. Không triển khai thay đổi này giữa một job dài hạn đang FAILED/STOPPED mà chưa có kế hoạch xử lý execution cũ.

## 6. saveState và khả năng restart

Khi reader lưu state, Spring Batch có thể khôi phục vị trí đọc dựa trên số item đã đọc tại checkpoint. Trong cấu hình, nên thể hiện rõ:

~~~java
.saveState(true)
~~~

Nếu tắt saveState, reader không ghi checkpoint stateful theo cơ chế mặc định. Lần chạy lại có thể bắt đầu từ đầu hoặc không khôi phục đúng vị trí trước đó.

Chỉ tắt lưu state khi chấp nhận đọc lại toàn bộ dữ liệu, hoặc có một cơ chế checkpoint khác được thiết kế và kiểm thử riêng. Với job xử lý lượng dữ liệu lớn, tắt saveState có thể kéo dài thời gian chạy và tạo side effect trùng nếu writer không idempotent.

saveState không tạo snapshot database. Nó chỉ lưu trạng thái reader. Tập dữ liệu mà query trả về vẫn có thể thay đổi giữa lần chạy đầu và lần restart.

## 7. JpaPagingItemReader khôi phục vị trí như thế nào?

JpaPagingItemReader kế thừa cơ chế paging và item counting của Spring Batch. Reader lưu số item đã đọc; khi restart, nó tính page chứa vị trí đó và query lại trang tương ứng. Về cơ bản, paging query sử dụng offset:

~~~text
firstResult = pageNumber * pageSize
maxResults  = pageSize
~~~

Ví dụ page size là 100 và checkpoint ghi nhận đã đọc 250 item:

~~~text
Page 0: offset 0,   item 1-100
Page 1: offset 100, item 101-200
Page 2: offset 200, item 201-300

Checkpoint: 250 item đã đọc
Restart: tải page 2, bỏ qua 50 item đầu trong page
Tiếp tục từ item thứ 251
~~~

Điều này giúp reader không cần lưu entity object của process cũ. Nó query lại trang cần thiết và bỏ qua phần đã được checkpoint trong trang đó.

Vì restart dựa trên vị trí trong kết quả query, query phải trả cùng thứ tự và tập dữ liệu tương thích. Nếu hàng bị thêm/xóa trước offset, vị trí 251 có thể không còn đại diện cho cùng một customer.

## 8. JPQL phải có thứ tự xác định

Không dựa vào thứ tự ngẫu nhiên mà database trả về khi query không có ORDER BY. Nếu kết quả query không có thứ tự xác định, trang tiếp theo hoặc lần restart có thể trả item theo thứ tự khác.

Ví dụ không nên dùng:

~~~sql
select c from Customer c
where c.status = :status
~~~

Nên sắp xếp theo một khóa duy nhất:

~~~sql
select c from Customer c
where c.status = :status
order by c.id
~~~

Nếu cần sắp xếp theo thời gian tạo và nhiều hàng có cùng timestamp, thêm primary key làm tie-breaker:

~~~sql
select c from Customer c
where c.status = :status
order by c.createdAt, c.id
~~~

ORDER BY trên một cột không duy nhất có thể không xác định thứ tự giữa các hàng có cùng giá trị. Dùng composite ordering để tạo thứ tự tổng thể ổn định.

## 9. Paging theo offset khác với keyset pagination

JpaPagingItemReader phân trang bằng offset/first result. Đây không phải keyset pagination dựa trên giá trị khóa cuối cùng.

Offset pagination:

~~~sql
select c
from Customer c
where c.status = :status
order by c.id
~~~

Reader lấy trang bằng vị trí bắt đầu và số lượng item. Nếu một hàng trước offset bị xóa, những hàng phía sau dịch chuyển vị trí.

Keyset pagination dùng điều kiện dựa trên khóa cuối cùng:

~~~sql
select c
from Customer c
where c.status = :status
  and c.id > :lastSeenId
order by c.id
~~~

Keyset pagination thường ổn định và hiệu quả hơn cho vị trí sâu trong tập dữ liệu, nhưng cần reader/custom query quản lý last key và checkpoint riêng. Không nên mô tả JpaPagingItemReader như thể nó tự động dùng keyset.

Nếu dữ liệu nguồn có thể thay đổi mạnh trong lúc job chạy hoặc restart, cân nhắc custom keyset reader, staging table hoặc một snapshot phù hợp.

## 10. Tác động của insert/delete trong lúc job chạy

Giả sử query trả các customer theo ID:

~~~text
Ban đầu:
ID 10, 20, 30, 40, 50, 60

Reader đã commit đến item thứ 3:
ID 10, 20, 30 [checkpoint], 40, 50, 60

Trong lúc job dừng, ID 20 bị xóa:
ID 10, 30, 40, 50, 60

Restart theo offset 3:
Vị trí tiếp theo có thể là ID 50
ID 40 có nguy cơ bị bỏ qua
~~~

Tương tự, nếu một hàng mới được chèn trước offset đã lưu, reader có thể đọc lại một hàng đã xử lý hoặc bỏ qua một hàng chưa xử lý.

ORDER BY không ngăn vấn đề này. ORDER BY chỉ xác định thứ tự của tập kết quả tại thời điểm query; nó không cố định membership của tập kết quả giữa hai lần chạy.

## 11. Cố định tập dữ liệu bằng batch ID hoặc cutoff

Một cách thực tế là xác định phạm vi dữ liệu ngay khi job bắt đầu:

- Dùng sourceBatchId để chỉ đọc các hàng thuộc một batch đã đóng.
- Dùng businessDate để giới hạn dữ liệu theo kỳ.
- Dùng cutoff timestamp được chụp một lần.
- Dùng high-water mark nếu khóa nguồn tăng đơn điệu và phù hợp.
- Dùng bảng staging bất biến cho dữ liệu cần restart lâu dài.

Ví dụ query:

~~~java
.queryString("""
    select c
    from Customer c
    where c.importBatchId = :batchId
      and c.id <= :maxId
    order by c.id
    """)
~~~

batchId và maxId phải được giữ nguyên trong JobParameters hoặc execution context phù hợp. Khi restart cùng JobInstance, không tính lại maxId mới nếu mục tiêu là tiếp tục đúng tập dữ liệu ban đầu.

High-water mark chỉ giới hạn phần trên của khóa. Nó không ngăn việc xóa hoặc sửa hàng đã tồn tại, cũng không giải quyết trường hợp ID không tăng đơn điệu. Cần hiểu cách hệ thống nguồn tạo dữ liệu.

## 12. JobParameters và query parameter phải nhất quán

Nếu query phụ thuộc status, tenant hoặc business date, những giá trị này ảnh hưởng trực tiếp tới tập kết quả. Chúng phải được giữ nguyên khi restart.

Ví dụ:

~~~java
@Bean
@StepScope
JpaPagingItemReader<Customer> customerReader(
        EntityManagerFactory entityManagerFactory,
        @Value("#{jobParameters['tenantId']}") String tenantId,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new JpaPagingItemReaderBuilder<Customer>()
        .name("tenantCustomerReader")
        .entityManagerFactory(entityManagerFactory)
        .queryString("""
            select c
            from Customer c
            where c.tenantId = :tenantId
              and c.businessDate = :businessDate
            order by c.id
            """)
        .parameterValues(Map.of(
            "tenantId", tenantId,
            "businessDate", LocalDate.parse(businessDate)
        ))
        .pageSize(250)
        .saveState(true)
        .build();
}
~~~

Khi restart, dùng lại đúng identifying JobParameters. Nếu tenantId hoặc businessDate thay đổi, đó là một lần chạy logic khác và nên có JobInstance riêng.

@StepScope giúp reader được tạo trong ngữ cảnh StepExecution, nhờ đó có thể dùng JobParameters. Nó không tự lưu checkpoint; saveState và ExecutionContext đảm nhiệm phần đó.

## 13. Vòng đời EntityManager của JpaPagingItemReader

JpaPagingItemReader tạo và quản lý EntityManager để thực hiện truy vấn. EntityManager được mở trong lifecycle của reader và đóng khi reader kết thúc. Reader lấy một page rồi clear persistence context để tránh giữ toàn bộ entity đã đọc trong bộ nhớ.

Hệ quả quan trọng là entity trả về thường ở trạng thái detached sau khi page được đọc. EntityManager của reader không phải persistence context mà processor/writer có thể dựa vào để tự động dirty-check và flush thay đổi.

Nếu processor thay đổi entity:

~~~java
@Override
public Customer process(Customer customer) {
    customer.setStatus("PROCESSED");
    return customer;
}
~~~

thay đổi trên detached object không tự động được ghi xuống database chỉ vì entity có setter. Writer phải thực hiện persist/merge/update rõ ràng bằng persistence context của nó hoặc dùng một writer JDBC/JPA phù hợp.

Đừng giữ reference đến entity để mong nó còn managed sau khi reader chuyển sang page tiếp theo. Hãy xử lý item như một object dữ liệu được trả về từ reader.

## 14. Lazy loading và detached entity

Vì entity được detach sau page, truy cập lazy association sau đó có thể gây LazyInitializationException:

~~~java
Customer customer = reader.read();
customer.getOrders().size(); // có thể lỗi nếu orders là LAZY
~~~

Các cách xử lý:

- Dùng JPQL fetch join cho quan hệ thực sự cần trong batch.
- Dùng EntityGraph hoặc query phù hợp để tải trước dữ liệu.
- Dùng DTO projection chỉ chứa field cần thiết.
- Enrich dữ liệu qua service có transaction riêng và batch lookup thay vì query từng item.
- Tránh truy cập lazy association tùy tiện trong processor.

Ví dụ fetch join:

~~~sql
select distinct c
from Customer c
left join fetch c.address
where c.status = :status
order by c.id
~~~

Không fetch join một collection lớn trong query phân trang mà chưa hiểu tác động. Join collection có thể nhân bản hàng kết quả và làm pagination sai hoặc kém hiệu quả tùy JPA provider. Với collection, cân nhắc query hai bước hoặc DTO projection.

## 15. Transaction của JpaPagingItemReader

JpaPagingItemReader quản lý việc đọc page bằng EntityManager riêng. Theo cấu hình mặc định, reader thực hiện query page trong transaction đọc của nó và commit sau khi lấy page; transaction này không nên bị nhầm với transaction chunk do step quản lý.

Step vẫn có transaction riêng cho chunk, bao gồm processor, writer và cập nhật metadata theo cấu hình JobRepository/transaction manager. Một page có thể được đọc trước khi các item của page đó được commit theo từng chunk.

Ví dụ page size 200, chunk size 50:

~~~text
JpaPagingItemReader tải page 1: 200 item
  |
  +-- Chunk 1: item 1-50 -> transaction step commit
  +-- Chunk 2: item 51-100 -> transaction step commit
  +-- Chunk 3: item 101-150 -> transaction step rollback
  +-- Chunk 4: chưa xử lý
~~~

Reader có thể đã tải toàn bộ page trong transaction đọc riêng, nhưng checkpoint step chỉ tiến theo chunk đã commit. Khi restart, reader khôi phục số item đã checkpoint và query lại page chứa vị trí tiếp theo.

Không giả định transaction đọc của JPA reader và transaction ghi của step luôn là cùng một transaction. Nếu cần một snapshot nhất quán xuyên suốt thời gian job, phải thiết kế isolation/snapshot ở database và transaction manager phù hợp; paging reader tự nó không bảo đảm snapshot toàn job.

## 16. Page size và chunk size

Hai thông số này có vai trò khác nhau:

| Thông số | Ý nghĩa | Tác động |
| --- | --- | --- |
| pageSize | Số entity được lấy trong một page query | Số lần query, memory và chi phí phân trang |
| chunk size | Số item được xử lý trước một lần commit | Transaction duration, rollback scope và checkpoint frequency |

Ví dụ:

~~~java
new JpaPagingItemReaderBuilder<Customer>()
    .name("customerJpaReader")
    .entityManagerFactory(entityManagerFactory)
    .queryString("select c from Customer c order by c.id")
    .pageSize(500)
    .saveState(true)
    .build();
~~~

~~~java
new StepBuilder("processCustomersStep", jobRepository)
    .<Customer, CustomerResult>chunk(100, transactionManager)
    .reader(customerReader)
    .processor(processor)
    .writer(writer)
    .build();
~~~

Reader lấy 500 entity mỗi page, còn step commit theo chunk 100 item. Một page có thể phục vụ nhiều chunk.

Page size lớn giảm số lần query nhưng tăng memory và có thể kéo dài transaction đọc của page. Chunk size lớn giảm số lần commit nhưng tăng thời gian giữ lock và phạm vi rollback. Chọn hai giá trị bằng benchmark và quan sát database.

## 17. Page size thay đổi giữa restart

Checkpoint của item-counting reader dựa trên số item đã đọc. Khi restart, reader tính lại page và vị trí bên trong page theo page size hiện tại.

Thay đổi page size không nhất thiết làm mất checkpoint về mặt số lượng item, nhưng có thể thay đổi cách phân trang, số query, memory usage và thời gian restart. Nó cũng làm việc phân tích execution cũ khó hơn nếu query hoặc tập dữ liệu thay đổi cùng lúc.

Đối với job cần restart ổn định, giữ page size và các thuộc tính reader nhất quán giữa các lần chạy. Nếu cần thay đổi cấu hình, kiểm thử restart một execution đã tạo bởi phiên bản trước và xác nhận không có duplicate/missing item.

Không dựa vào giả định rằng mọi thay đổi page size đều an toàn chỉ vì checkpoint là item count. Điều kiện quan trọng vẫn là cùng tập dữ liệu và cùng thứ tự.

## 18. Thay đổi query hoặc thứ tự giữa restart

Checkpoint lưu vị trí, không lưu toàn bộ nội dung query hay một snapshot của kết quả. Những thay đổi sau có thể làm checkpoint cũ không còn tương thích:

- Đổi WHERE predicate.
- Đổi giá trị parameter.
- Đổi ORDER BY hoặc thứ tự tie-breaker.
- Thêm/bớt join làm thay đổi số hàng.
- Đổi fetch strategy khiến query trả duplicate row.
- Thay đổi mapping hoặc filter khiến item bị loại ở phase khác.
- Đổi reader name hoặc state key.

Nếu cần thay đổi query khi một JobInstance cũ còn restart được, cần giữ phiên bản query hoặc có migration/reprocessing plan. Một cách là lưu query version/schema version trong JobParameters hoặc execution context và chọn reader phù hợp với version đó.

Không sửa query âm thầm rồi restart execution cũ với kỳ vọng checkpoint vẫn mang cùng ý nghĩa.

## 19. Entity state và writer khi restart

JpaPagingItemReader trả entity đã được detach. Nếu processor thay đổi entity, writer phải thực hiện ghi bằng transaction/persistence context của writer.

Ví dụ một JPA writer có thể merge entity:

~~~java
public class CustomerJpaWriter implements ItemWriter<Customer> {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public void write(Chunk<? extends Customer> chunk) {
        for (Customer customer : chunk) {
            entityManager.merge(customer);
        }
    }
}
~~~

Đây là ví dụ khái niệm; trong Spring Batch, cần bảo đảm EntityManager được inject/ủy quyền đúng transaction scope và persistence context của writer tham gia transaction chunk. Có thể dùng repository hoặc service transactional phù hợp thay vì tự quản lý EntityManager.

merge trả về một managed instance; object truyền vào vẫn có thể detached. Nếu các bước sau cần entity managed, dùng giá trị trả về từ merge hoặc query lại trong transaction tương ứng.

Restart sẽ đọc lại entity từ database, không khôi phục object Java đã được processor sửa trước khi process dừng. Mọi thông tin cần tồn tại qua restart phải được ghi bền vững hoặc tái tính được từ nguồn.

## 20. Không dùng entity object làm checkpoint

Không lưu entity đã đọc vào JobExecutionContext hoặc StepExecutionContext để tiếp tục xử lý. Entity có thể:

- Không serializable.
- Chứa proxy/lazy association của JPA provider.
- Có trạng thái detached hoặc proxy không còn EntityManager.
- Thay đổi theo database sau thời điểm lưu.
- Tạo payload metadata rất lớn.

Checkpoint nên là vị trí hoặc khóa ổn định, không phải toàn bộ object graph. Với JpaPagingItemReader, để reader quản lý item count. Với custom keyset reader, lưu last processed key hoặc composite key có thể serialize.

## 21. Dữ liệu thay đổi và isolation level

Một transaction đọc page không nhất thiết giữ snapshot cho toàn bộ job. Khi reader chuyển sang page mới, query tiếp theo có thể nhìn thấy dữ liệu mới tùy isolation level và database.

Ví dụ một hàng có status READY được đổi thành DONE giữa lúc job đang chạy. Hàng đó có thể rời khỏi tập query. Một hàng khác đổi từ DONE sang READY có thể được thêm vào tập kết quả ở page sau. Nếu các thay đổi xảy ra trước/sau offset, reader có thể đọc thiếu hoặc lặp.

Các lựa chọn:

- Chụp danh sách source ID vào staging table trước khi xử lý.
- Đánh dấu batch membership rồi chỉ đọc các hàng thuộc batch.
- Dùng cutoff/high-water mark phù hợp.
- Dùng transaction isolation/snapshot được database hỗ trợ nếu job có thể giữ snapshot đủ lâu.
- Dùng keyset reader để tránh một số vấn đề dịch chuyển offset.

Không tăng isolation level một cách tùy tiện. Snapshot dài có thể giữ version/row và gây áp lực lên database. Hãy cân nhắc thời lượng job, write workload và khả năng của database.

## 22. Restart khi query join

JPQL join có thể làm thay đổi số hàng mà reader phân trang:

~~~sql
select c
from Customer c
join c.orders o
where o.status = :orderStatus
order by c.id
~~~

Nếu một customer có nhiều order khớp, query có thể trả cùng customer nhiều lần. Dùng distinct khi phù hợp:

~~~sql
select distinct c
from Customer c
join c.orders o
where o.status = :orderStatus
order by c.id
~~~

Tuy nhiên, distinct kết hợp fetch join collection và pagination có thể không được JPA provider xử lý theo cách mong muốn. Một số provider có thể phải thực hiện pagination trong memory hoặc cảnh báo. Hãy kiểm tra SQL thực tế và kết quả trên provider/database production.

Một cách ổn định hơn là phân trang theo entity root ID, sau đó tải chi tiết cần thiết cho nhóm ID đó. Với aggregate lớn, custom reader hoặc query DTO có thể phù hợp hơn.

## 23. Reader name, step name và compatibility khi deploy

Restart có thể xảy ra sau khi ứng dụng đã được triển khai phiên bản mới. Khi đó code mới phải hiểu metadata của execution cũ.

Các thay đổi cần xem xét:

- Reader name hoặc step name.
- Query và parameter semantics.
- Sort order.
- Page size và fetch behavior.
- Entity mapping/schema.
- State serialization format.
- Spring Batch/JPA provider version.

Không phải mọi thay đổi đều phá checkpoint, nhưng một thay đổi có thể làm reader đọc tập dữ liệu khác hoặc tìm key state khác. Lập danh sách execution FAILED/STOPPED trước deploy và xác định chúng có cần restart bằng code mới hay không.

Nếu không thể bảo đảm compatibility, chọn chiến lược rõ ràng: giữ phiên bản cũ cho execution cũ, migrate metadata có kiểm soát, hoặc đánh dấu execution cũ cần reprocess với JobInstance mới theo nghiệp vụ.

## 24. @StepScope và reader instance khi restart

@StepScope tạo target bean trong scope của StepExecution. Điều này hữu ích khi query parameters đến từ JobParameters:

~~~java
@Bean
@StepScope
JpaPagingItemReader<Customer> reader(
        EntityManagerFactory entityManagerFactory,
        @Value("#{jobParameters['tenantId']}") String tenantId) {

    return new JpaPagingItemReaderBuilder<Customer>()
        .name("tenantCustomerReader")
        .entityManagerFactory(entityManagerFactory)
        .queryString("""
            select c
            from Customer c
            where c.tenantId = :tenantId
            order by c.id
            """)
        .parameterValues(Map.of("tenantId", tenantId))
        .pageSize(200)
        .saveState(true)
        .build();
}
~~~

Khi restart, Spring Batch tạo target reader cho StepExecution mới rồi gọi open với execution context đã lưu. Field runtime của reader cũ không tồn tại qua process restart; checkpoint trong JobRepository mới là nguồn phục hồi.

Không dùng static field để lưu page hoặc item count. Hai job chạy đồng thời có thể ghi đè state của nhau. Không chia sẻ một reader instance stateful cho nhiều step execution độc lập.

## 25. Multi-threaded step và JpaPagingItemReader

JpaPagingItemReader giữ trạng thái page và vị trí đọc, nên không nên mặc định dùng chung một instance cho nhiều thread cùng gọi read(). Nếu muốn parallelize, cần chọn mô hình phù hợp:

- Partitioning: mỗi partition có reader riêng với phạm vi dữ liệu riêng.
- Một reader được đồng bộ hóa: bảo vệ thao tác đọc nhưng có thể giới hạn throughput.
- Custom reader thread-safe: quản lý phân vùng/khóa và checkpoint riêng.

Với partitioning, mỗi worker nên nhận một khoảng ID hoặc batch key riêng, có query predicate riêng và reader name/state key riêng. Khi restart, từng partition khôi phục checkpoint của chính nó.

Đừng chỉ đặt saveState(false) để né vấn đề concurrency nếu job vẫn cần restart. Tắt state đồng nghĩa bỏ khả năng khôi phục mặc định; cần một chiến lược checkpoint khác nếu yêu cầu nghiệp vụ vẫn còn.

## 26. Thiết kế partition có restart

Ví dụ chia customer theo khoảng ID:

~~~text
Partition 1: id 1 - 100000
Partition 2: id 100001 - 200000
Partition 3: id 200001 - 300000
~~~

Mỗi partition có reader riêng:

~~~sql
select c
from Customer c
where c.id between :minId and :maxId
order by c.id
~~~

Các giới hạn minId/maxId phải được xác định và lưu bền vững cho lần chạy logic đó. Khi restart, mỗi partition dùng cùng phạm vi và checkpoint riêng.

Không để các partition có khoảng giao nhau nếu mỗi customer chỉ được xử lý một lần. Nếu dùng hash partitioning, hash function và số partition phải ổn định trong suốt vòng đời restart của JobInstance.

## 27. Kiểm thử restart với JpaPagingItemReader

Restart cần được kiểm thử bằng database và JobRepository có state tồn tại giữa hai lần launch. Một kịch bản cơ bản:

1. Tạo 10 customer với ID tăng dần và status READY.
2. Cấu hình JpaPagingItemReader với ORDER BY id, page size 4 và chunk size 2.
3. Writer cho chunk đầu commit thành công.
4. Writer cố ý thất bại ở chunk sau để step chuyển FAILED.
5. Xác nhận checkpoint của chunk đã commit được lưu.
6. Restart cùng JobInstance với đúng identifying parameters.
7. Xác nhận reader tiếp tục sau checkpoint và cuối cùng xử lý đủ customer.

Các assertion quan trọng:

- JobExecution đầu có status FAILED.
- JobExecution restart thuộc cùng JobInstance.
- Execution mới kết thúc COMPLETED.
- Mỗi business key cần xử lý đều xuất hiện ở đích.
- Không có duplicate nếu output có unique constraint theo source key.
- Item của chunk rollback được xử lý lại.

Không chỉ kiểm tra job status. Đọc bảng đích và so sánh tập business key với tập nguồn dự kiến.

## 28. Ví dụ writer fail một lần trong restart test

Có thể tạo writer test ném exception ở một lần gọi nhất định:

~~~java
public class FailOnceCustomerWriter implements ItemWriter<Customer> {

    private final CustomerRepository repository;
    private final AtomicBoolean shouldFail = new AtomicBoolean(true);

    public FailOnceCustomerWriter(CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public void write(Chunk<? extends Customer> chunk) {
        if (shouldFail.compareAndSet(true, false)) {
            throw new IllegalStateException("Simulated writer failure");
        }

        repository.saveAll(chunk.getItems());
    }
}
~~~

Đây là fixture minh họa. Cần đặt thời điểm fail sau khi ít nhất một chunk đã commit, nếu không test chỉ chứng minh restart từ đầu. Nếu muốn kiểm thử qua process restart thật, trạng thái fail-once cũng phải được điều khiển bên ngoài process hoặc dựa trên dữ liệu bền vững, không chỉ AtomicBoolean trong memory.

Trong test cùng process, AtomicBoolean có thể mô phỏng lỗi một lần giữa hai lần launch. Nó không mô phỏng việc JVM bị kill rồi khởi động lại vì state của boolean sẽ được tạo lại.

## 29. JobRepository phải lưu state bền vững

Restart qua process restart cần JobRepository bền vững. Nếu metadata chỉ nằm trong bộ nhớ, sau khi JVM dừng, JobExecution và ExecutionContext có thể mất.

Với integration test:

- Dùng database schema của Spring Batch hoặc repository phù hợp.
- Giữ JobRepository giữa lần launch thất bại và lần restart.
- Không xóa metadata giữa hai lần launch.
- Dùng cùng identifying parameters.
- Kiểm tra JobExplorer đọc được execution và step execution cũ.

Repository in-memory có thể phù hợp cho một số unit test hoặc test cùng process, nhưng không chứng minh khả năng restart sau khi process bị dừng thật.

## 30. Không bọc test restart trong transaction ngoài

Nếu test method được đánh dấu @Transactional và transaction test rollback toàn bộ khi kết thúc, có thể che giấu transaction boundary của chunk hoặc làm fixture/metadata không tồn tại như mong đợi giữa hai lần launch.

Một quy trình test dễ quan sát:

1. Tạo fixture và commit trước khi launch job.
2. Launch job và để step tự quản lý chunk transaction.
3. Đọc JobExecution/StepExecution sau lần chạy đầu.
4. Restart cùng JobInstance.
5. Kiểm tra bảng đích và execution metadata.
6. Dọn dữ liệu fixture ở bước teardown riêng.

Nếu test cần rollback để cô lập dữ liệu, hãy thiết kế transaction cleanup riêng và bảo đảm không rollback metadata/checkpoint trước khi restart.

## 31. Kiểm tra execution metadata

JobExplorer cho phép đọc lại JobExecution và StepExecution:

~~~java
JobExecution previousExecution =
    jobExplorer.getJobExecution(previousExecutionId);

assertThat(previousExecution).isNotNull();
assertThat(previousExecution.getStatus())
    .isEqualTo(BatchStatus.FAILED);

StepExecution failedStep = previousExecution.getStepExecutions()
    .stream()
    .filter(step -> step.getStepName().equals("processCustomersStep"))
    .findFirst()
    .orElseThrow();
~~~

Có thể kiểm tra execution context tồn tại và reader state được lưu. Tuy nhiên, key nội bộ do JpaPagingItemReader dùng có thể thay đổi theo phiên bản; không nên viết logic production phụ thuộc vào tên key nội bộ đó.

Hành vi dữ liệu là assertion quan trọng nhất: reader tiếp tục từ checkpoint, không bỏ sót và không xử lý trùng ngoài semantics được thiết kế.

## 32. Nhiều datasource và transaction manager

Một batch có thể đọc entity từ database nguồn, ghi dữ liệu sang database đích và lưu metadata ở một datasource khác. Khi đó phải xác định transaction manager nào quản lý từng resource.

Nếu business data đã commit nhưng checkpoint metadata chưa commit, restart có thể đọc lại item đã ghi. Nếu metadata checkpoint đã commit nhưng business write chưa commit, reader có thể bỏ qua item chưa được ghi.

Các lựa chọn:

- Dùng cùng transaction manager/database cho business write và batch metadata khi phù hợp.
- Dùng distributed transaction khi cần atomic commit thực sự và chấp nhận độ phức tạp vận hành.
- Thiết kế writer idempotent với unique key/upsert.
- Dùng outbox/inbox hoặc staging để đối soát trạng thái.
- Lưu operation ID để nhận diện thao tác đã được áp dụng.

JpaPagingItemReader không giải quyết sự nhất quán giữa các datasource. Nó chỉ lưu và khôi phục vị trí đọc.

## 33. Idempotency khi restart

Vì item trong chunk chưa commit có thể được đọc lại, writer nên được thiết kế để cùng một item được xử lý lại mà không gây sai lệch.

Ví dụ thao tác đặt trạng thái:

~~~sql
update customer
set status = 'PROCESSED'
where customer_id = :customerId
~~~

Thường idempotent nếu không có side effect phụ.

Ngược lại, thao tác cộng dồn:

~~~sql
update account
set balance = balance + :amount
where account_id = :accountId
~~~

không idempotent nếu chạy lại. Cần operation ID, bảng deduplication hoặc ledger ghi nhận giao dịch đã áp dụng.

Nếu processor gửi event hoặc gọi API, hãy dùng idempotency key ổn định theo batch/item. Không tạo key mới mỗi lần retry hoặc restart.

## 34. Skip, retry và restart với JPA reader

Restart, retry và skip giải quyết các vấn đề khác nhau:

| Cơ chế | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Retry | Thử lại lỗi tạm thời trong execution hiện tại | Deadlock khi writer update |
| Skip | Bỏ qua item không hợp lệ theo business policy | Customer thiếu mã bắt buộc |
| Restart | Tiếp tục JobInstance sau khi execution dừng/thất bại | JVM dừng sau chunk đã commit |

Lỗi JPQL, entity mapping hoặc database schema thường là lỗi cấu hình/triển khai, không nên skip rộng. Lỗi dữ liệu của một item có thể được xử lý ở processor và skip nếu nghiệp vụ cho phép.

Nếu reader query lỗi do datasource tạm thời, retry có thể phù hợp theo exception thực tế. Nếu query sai cú pháp, retry không giải quyết được nguyên nhân.

## 35. Những lỗi thường gặp khi restart JPA database item

**Query không có ORDER BY:** database không bảo đảm thứ tự kết quả. Dùng sort order xác định với khóa duy nhất.

**ORDER BY không duy nhất:** các hàng cùng giá trị có thể đổi thứ tự. Thêm primary key làm tie-breaker.

**Nguồn thay đổi giữa hai lần chạy:** offset có thể dịch chuyển và gây lặp/bỏ sót. Cố định batch membership hoặc dùng snapshot/keyset phù hợp.

**Đổi identifying JobParameters:** tạo JobInstance mới và không dùng checkpoint cũ. Dùng lại đúng parameters khi restart.

**Tạo run.id mới khi restart:** tạo instance mới thay vì tiếp tục execution cũ. Chỉ tăng run ID cho một lần chạy logic mới.

**Không bật saveState:** reader không lưu checkpoint. Bật state khi cần restart.

**Đổi reader name:** key execution context có thể khác. Giữ tên ổn định và kiểm tra compatibility khi deploy.

**Nhầm JpaPagingItemReader dùng keyset pagination:** reader phân trang theo offset/item count. Nếu cần keyset, triển khai reader riêng và checkpoint last key.

**Giữ entity managed sau khi page được clear:** entity có thể detached. Merge/update qua persistence context của writer khi cần lưu.

**Truy cập lazy association sau khi detach:** có thể gây LazyInitializationException. Fetch trước, dùng projection hoặc enrich có kiểm soát.

**Nhầm transaction đọc page với transaction chunk:** reader và step có thể dùng transaction khác nhau. Hiểu rõ resource và transaction manager.

**Cho rằng page size bằng chunk size:** hai thông số điều khiển hai ranh giới khác nhau. Chọn và đo riêng.

**Dùng reader stateful chung cho nhiều thread:** có thể làm page/count lẫn nhau. Dùng partition riêng hoặc mô hình reader thread-safe.

**Giả định restart bảo đảm exactly-once:** failure window và nhiều datasource vẫn có thể tạo side effect lặp. Dùng idempotency.

**Chỉ test trong memory:** không chứng minh restart qua process restart. Dùng JobRepository bền vững trong integration test.

## 36. Quy trình thiết kế restart với JPA trong production

Trước tiên, xác định tập entity cần xử lý và làm cho tập đó có thể tái lập. Dùng JpaPagingItemReader với JPQL có ORDER BY dựa trên khóa duy nhất; cố định JobParameters và batch membership. Nếu dữ liệu có thể bị thêm/xóa trước offset trong thời gian job chạy hoặc restart, cân nhắc staging snapshot hay custom keyset reader.

Tiếp theo, đặt reader name ổn định, bật saveState và dùng JobRepository bền vững. Dùng @StepScope khi reader cần query parameter từ JobParameters. Hiểu rằng reader khôi phục theo item count/page offset; entity được trả về có thể detached sau khi persistence context của reader được clear. Writer phải merge hoặc cập nhật bằng transaction phù hợp nếu cần lưu thay đổi.

Cuối cùng, kiểm thử bằng cách commit ít nhất một chunk, cố ý làm chunk tiếp theo thất bại rồi restart cùng JobInstance. Xác nhận dữ liệu đích đầy đủ, không trùng, reader tiếp tục sau checkpoint, query/order không đổi và transaction manager tham gia đúng datasource. Kiểm thử thêm tình huống source data thay đổi, version conflict, lazy loading và restart sau deploy nếu job cần hỗ trợ.

Restart với database item trong Spring Batch JPA dựa trên checkpoint bền vững và một truy vấn có thể tái lập. JpaPagingItemReader lưu vị trí đọc theo item count và phân trang theo offset; vì vậy thứ tự query và tập dữ liệu nguồn phải ổn định. Khi JobInstance parameters, reader identity, query, EntityManager lifecycle và transaction boundaries được thiết kế rõ, job có thể tiếp tục sau lỗi mà không phải xử lý lại toàn bộ dữ liệu. Writer idempotent và integration test qua JobRepository bền vững giúp bảo vệ dữ liệu khi item được đọc lại trong quá trình retry hoặc restart.
