# Giới hạn dùng populator cho migration hoặc dữ liệu production

Repository populator của Spring Data thuận tiện khi cần nạp một tập dữ liệu mẫu nhỏ vào repository. Với migration hoặc dữ liệu production, yêu cầu còn bao gồm lịch sử thay đổi, chạy lại an toàn, kiểm soát đồng thời, xử lý lỗi và bảo vệ dữ liệu đang tồn tại. Populator cơ bản không tự cung cấp đầy đủ những cơ chế đó.

Bài học thuộc chương **Khởi tạo dữ liệu** của module **SPRING_DATA_COMMONS**. Trọng tâm là nhận biết phạm vi của cơ chế nạp dữ liệu qua Repository/CRUD, phân biệt fixture với migration và lựa chọn cách tổ chức phù hợp với khả năng transaction, mapping và metadata của từng store.

## 1. Populator thực hiện công việc gì?

Luồng cơ bản:

```text
Resource JSON hoặc XML
    -> ResourceReader chuyển thành đối tượng Java
    -> Xác định repository quản lý kiểu đối tượng
    -> Gọi thao tác save qua RepositoryInvoker
```

Ví dụ một fixture JSON:

```json
[
  {
    "_class": "com.example.catalog.Category",
    "id": "demo-books",
    "code": "DEMO_BOOKS",
    "name": "Sách mẫu"
  }
]
```

Giả định domain Category, cách mapping ID và repository đã được cấu hình phù hợp. `_class` giúp cơ chế đọc xác định kiểu đối tượng; fixture không tự định nghĩa schema, index hay chính sách cập nhật.

Spring Data mô tả populator ở tầng repository, với JSON hoặc XML thay cho việc gắn chặt dữ liệu đầu vào vào SQL. Xem phần **Repository Populators** trong [Spring Data Extensions](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html).

Một đặc điểm quan trọng là dữ liệu được đưa qua thao tác repository. Điều này giúp tận dụng mapping tương ứng, nhưng cũng kéo theo ngữ nghĩa save và lifecycle của store.

## 2. Phân biệt fixture, bootstrap, migration và import

| Công việc | Mục tiêu | Đặc điểm cần quan tâm |
| --- | --- | --- |
| Fixture cho demo/test | Có dữ liệu mẫu để thao tác | Nhỏ, tái tạo được, môi trường được kiểm soát |
| Bootstrap dữ liệu tham chiếu | Thiết lập một số giá trị hệ thống ban đầu | Khóa ổn định, chính sách khi đã tồn tại, phạm vi sở hữu |
| Migration | Đưa dữ liệu/schema từ trạng thái đã biết sang trạng thái mới | Phiên bản, điều kiện trước/sau, lịch sử thực thi |
| Import hoặc backfill | Nạp hay chuyển đổi nhiều dữ liệu đang vận hành | Batch, checkpoint, retry, báo cáo lỗi và khả năng tiếp tục |

Một file JSON không tự cho biết nó thuộc loại nào. Cùng một resource có thể được dùng làm fixture hoặc làm đầu vào cho một job có kiểm soát, nhưng yêu cầu vận hành của hai trường hợp khác nhau.

Ví dụ:

```text
Thêm 5 danh mục giả vào database demo
    -> Phù hợp với fixture populator

Chuyển trạng thái của 5 triệu đơn hàng đang tồn tại
    -> Cần một quy trình migration/backfill có thiết kế riêng
```

Tên resource như `initial-data.json` cũng không làm nội dung trở thành dữ liệu “chỉ chạy một lần”.

## 3. Những cơ chế migration mà populator cơ bản không tự bổ sung

Populator không tự tạo một hợp đồng đầy đủ cho các việc sau:

- Ghi lịch sử phiên bản thay đổi đã áp dụng trong database.
- Phát hiện resource cũ bị chỉnh sửa bằng checksum đã lưu.
- Khóa việc thực thi giữa nhiều instance của ứng dụng.
- Quyết định cách xử lý bản ghi đã tồn tại theo business key.
- Tạo checkpoint để tiếp tục một lần import lớn bị gián đoạn.
- Bảo đảm toàn bộ nhiều resource hoặc nhiều store cùng commit/rollback.
- Quản lý tương thích schema giữa phiên bản ứng dụng cũ và mới.
- Cung cấp kế hoạch khôi phục những field đã bị ghi đè.

Đây là giới hạn của cơ chế cơ bản, không phải khẳng định không thể xây thêm hạ tầng xung quanh nó. Nếu ứng dụng tự bổ sung các phần trên, trách nhiệm bảo đảm thuộc quy trình do ứng dụng thiết kế.

Các công cụ migration có mục đích riêng. Chẳng hạn Flyway lưu lịch sử, checksum và trạng thái thay đổi trong [schema history table](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/flyway-schema-history-table). Liquibase có cơ chế khóa thực thi đồng thời qua [DATABASECHANGELOGLOCK](https://docs.liquibase.com/community/user-guide-5-0/what-is-the-database-changelog-lock-table). Không suy ra những tính năng đó từ việc một bean populator được tạo thành công.

## 4. save không có nghĩa là một migration có thể chạy lại tùy ý

### 4.1. ID được sinh tự động có thể làm dữ liệu mẫu bị nhân đôi

Giả sử fixture không có ID và domain dùng cơ chế sinh ID:

```text
Khởi động lần 1 -> tạo Category với ID mới
Khởi động lần 2 -> có thể tạo thêm Category với ID khác
```

Nếu không có khóa nghiệp vụ và ràng buộc phù hợp, cùng một mục trong fixture có thể trở thành nhiều bản ghi.

Populator không tự nhận ra hai đối tượng có cùng tên hiển thị là cùng một thực thể nghiệp vụ.

### 4.2. ID cố định chưa bảo đảm không ghi đè

Giả sử fixture có ID ổn định:

```text
id   = demo-books
name = Sách mẫu
```

Sau khi chạy lần đầu, một người vận hành đổi name thành “Sách và tài liệu”. Một lần nạp lại có thể đưa giá trị cũ trở lại, hoặc gặp lỗi, tùy cách store nhận biết trạng thái entity và thực hiện save.

Không mô tả save như một lệnh luôn “chèn nếu thiếu, bỏ qua nếu có”. Nó có thể dẫn đến insert, update, merge hoặc lỗi do ràng buộc/trạng thái. ID, version và mapping ảnh hưởng đến hành vi thực tế.

### 4.3. Kiểm tra tồn tại rồi lưu chưa giải quyết cạnh tranh

Một ý tưởng thường gặp:

```java
if (!repository.existsByCode(code)) {
    repository.save(category);
}
```

Đây chỉ là minh họa một thao tác đọc rồi ghi, không phải một bảo đảm nguyên tử.

Hai instance có thể cùng đọc “chưa tồn tại” rồi cùng lưu. Cần ràng buộc duy nhất và cơ chế ghi/khóa/transaction tương ứng với store, đồng thời có chính sách xử lý xung đột.

Cũng không dùng `repository.count() == 0` để kết luận một tập dữ liệu cụ thể đã được nạp đúng. Kho dữ liệu có thể có sẵn một phần dữ liệu khác hoặc lần nạp trước chỉ hoàn thành một phần.

### 4.4. Idempotency phải được định nghĩa theo kết quả mong muốn

“Chạy lại không tạo thêm hàng” chỉ là một khía cạnh. Một quy trình còn có thể thay đổi:

```text
lastModifiedAt
version
Sự kiện phát sinh
Thông báo gửi ra ngoài
Field người dùng đã chỉnh sửa
```

Cần nêu rõ khi dữ liệu đã tồn tại thì bỏ qua, cập nhật những field hệ thống sở hữu, báo xung đột hay áp dụng một chuyển đổi có phiên bản. Populator không tự chọn chính sách đó.

## 5. Transaction và lỗi giữa chừng

### 5.1. Không mặc định một resource là một transaction

Trong implementation cơ bản, populator đọc đối tượng từ resource rồi gọi save cho từng phần tử. Không có một cam kết transaction bao toàn bộ tập chỉ vì các phần tử cùng nằm trong một file.

Giả sử lần lưu thứ 7 thất bại:

```text
save 1 -> thành công
save 2 -> thành công
...
save 6 -> thành công
save 7 -> lỗi ràng buộc
```

Nếu các lần lưu trước đã commit theo transaction riêng của repository/store, sáu bản ghi đó có thể vẫn còn. Dừng startup không tự chứng minh database đã trở về trạng thái trước khi nạp.

Cách lặp resource và gọi `invokeSave` có thể xem trong [ResourceReaderRepositoryPopulator](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/repository/init/ResourceReaderRepositoryPopulator.java).

### 5.2. Lỗi đọc và lỗi ghi là hai thời điểm khác nhau

Cần phân biệt:

| Lỗi | Điều cần xem xét |
| --- | --- |
| JSON không parse được | Resource đó có thể chưa tạo được collection đối tượng để lưu |
| Không tìm được repository cho kiểu dữ liệu | Những resource hoặc phần tử đã xử lý trước đó có thể đã được ghi |
| Lưu một phần tử thất bại | Những lần save trước có thể đã commit |
| Resource sau lỗi | Resource trước có thể đã hoàn tất |
| Sau ghi có sự kiện hoặc thao tác bên ngoài | Transaction database không tự rollback mọi hệ thống khác |

Không khẳng định “JSON lỗi ở dòng sau nên những dòng trước chắc chắn đã được lưu”, vì cách reader deserialize có thể đọc toàn bộ resource trước khi vòng lưu bắt đầu. Cũng không suy ra “file chưa hoàn tất nên không có bản ghi nào được lưu”.

### 5.3. Đặt Transactional sai chỗ không tạo transaction mong muốn

Đặt `@Transactional` trên phương thức `@Bean` tạo factory không tự chứng minh transaction đó bao lần populate được kích hoạt sau này theo lifecycle.

Transaction phải bao đúng thao tác thực thi, dùng đúng transaction manager và được cơ chế gọi của Spring áp dụng thực sự. Với nhiều repository thuộc nhiều store, còn phải xác định phạm vi transaction hỗ trợ.

Nếu cần atomicity toàn bộ một thay đổi nhỏ, thiết kế và xác nhận transaction đó. Với import lớn, có thể cần commit theo batch cùng checkpoint, thay vì giữ một transaction dài cho tất cả dữ liệu.

## 6. Khởi động ứng dụng không phải lịch sử migration toàn hệ thống

Factory populator gắn với sự kiện refresh của ApplicationContext được cấu hình. Implementation kiểm tra context của sự kiện rồi mới gọi populate; xem [AbstractRepositoryPopulatorFactoryBean](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/repository/init/AbstractRepositoryPopulatorFactoryBean.java).

Điều này không tạo ra một dấu “migration đã chạy” bền vững trong database.

Ví dụ có ba instance:

```text
Instance A tạo context -> có thể chạy populator
Instance B tạo context -> có thể chạy populator
Instance C tạo context -> có thể chạy populator
```

Các context thuộc những tiến trình khác nhau không tự chia sẻ một cờ hoàn thành trong bộ nhớ.

Một lần restart, triển khai lại hoặc tạo context mới cũng không tự biết dữ liệu đã được nạp bởi bản triển khai trước. Nếu ứng dụng cần “áp dụng thay đổi này một lần cho database”, phải có cơ chế định danh thay đổi và phối hợp thực thi ở đúng phạm vi.

Không đổi populator sang một callback startup khác rồi coi vấn đề đã được giải quyết. `ApplicationRunner` hay một listener khác vẫn cần cùng chính sách chạy lại và đồng thời nếu được dùng cho dữ liệu production.

## 7. Repository lifecycle không thay thế application service

Populator đi tới repository tương ứng, không tự đi qua một service nghiệp vụ chỉ vì service đó đang tồn tại.

So sánh:

```text
Use case thông thường:
Request -> Validation -> Application service -> Repository

Populator cơ bản:
Resource -> Deserialize -> Repository invoker -> Save
```

Hệ quả cần xét theo ứng dụng:

- Validation được khai báo ở controller không tự được gọi.
- Quy tắc phân quyền ở một service riêng không tự được áp dụng.
- Các bước nhiều aggregate hoặc thao tác ngoài database không tự được phối hợp.
- Callback persistence, auditing hoặc listener có thể được kích hoạt theo store và cấu hình.
- Side effect nếu có cần được xét khi chạy lại.

Không nói tuyệt đối rằng populator bỏ qua mọi validation: provider, entity lifecycle hoặc repository tùy chỉnh có thể có kiểm tra riêng. Điểm quan trọng là phải xác định đúng cơ chế nào thực sự chạy.

### 7.1. Auditing và version không nên được sao chép tùy ý

Fixture chứa createdAt, createdBy, lastModifiedBy hoặc version có thể không phù hợp với quy tắc persistence hiện tại.

Cần quyết định:

| Field | Quyết định cần làm rõ |
| --- | --- |
| ID | Khóa do nguồn dữ liệu hay store quản lý? |
| Business key | Dùng gì để nhận diện cùng một mục? |
| Version | Được provider quản lý hay có quy trình nhập lịch sử riêng? |
| Metadata auditing | Giữ dữ liệu lịch sử hay để auditing của lần ghi hiện tại tạo? |
| Field người dùng sở hữu | Có được cập nhật bởi một lần bootstrap không? |

Khởi tạo dữ liệu và nhập lịch sử nghiệp vụ là hai hợp đồng khác nhau. Không để giá trị mặc định trong một file mẫu quyết định ngầm việc ghi đè production.

## 8. Ví dụ giới hạn populator vào dữ liệu demo

Với Spring Data Commons 4.0 trở lên và hạ tầng Jackson tương thích, có thể đặt cấu hình fixture trong một profile được bật tường minh:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.data.repository.init
        .JacksonRepositoryPopulatorFactoryBean;

@Configuration
@Profile("demo-fixtures")
class DemoFixtureConfiguration {

    @Bean
    JacksonRepositoryPopulatorFactoryBean demoPopulator() {
        JacksonRepositoryPopulatorFactoryBean factory =
                new JacksonRepositoryPopulatorFactoryBean();

        factory.setResources(new Resource[] {
                new ClassPathResource(
                        "fixtures/catalog-demo.json")
        });

        return factory;
    }
}
```

Giả định resource tồn tại, nội dung phù hợp với domain, mapper đọc được dữ liệu và repository đã được cấu hình. Đoạn mã minh họa cấu hình trong bài, không phải một quy trình migration production hoàn chỉnh.

`JacksonRepositoryPopulatorFactoryBean` có từ Commons 4.0; API sử dụng hạ tầng Jackson tương ứng với thế hệ này. Xem [factory API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/repository/init/JacksonRepositoryPopulatorFactoryBean.html).

Ở thế hệ cũ có `Jackson2RepositoryPopulatorFactoryBean`. API đó được đánh dấu deprecated từ 4.0 để thay bằng factory mới; không trộn tên lớp và ObjectMapper giữa hai thế hệ mà không đối chiếu phiên bản. Xem [Jackson2 factory API](https://docs.spring.io/spring-data/commons/reference/4.0/api/java/org/springframework/data/repository/init/Jackson2RepositoryPopulatorFactoryBean.html).

Profile opt-in giúp thể hiện mục đích của cấu hình. Nó không tự xác nhận database đang kết nối là database demo. Hệ thống triển khai vẫn phải bảo đảm profile, tài khoản kết nối và resource phù hợp với môi trường.

Không bật profile này trong production rồi dựa vào tên “demo” để kết luận dữ liệu thật sẽ không bị tác động.

## 9. Dữ liệu production cần một quy trình có định danh

### 9.1. Migration schema hoặc dữ liệu nhỏ có phiên bản

Với các thay đổi phù hợp, dùng cơ chế migration quản lý phiên bản và lịch sử. Trong ứng dụng Spring Boot dùng SQL database, tài liệu có phần riêng về Flyway và Liquibase; xem [Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html).

Cần lựa chọn theo loại store và khả năng của công cụ, không mặc định một công cụ SQL là giải pháp trực tiếp cho mọi kho dữ liệu.

Không để nhiều cơ chế độc lập cùng sở hữu một thay đổi mà không có thứ tự rõ ràng: migration tạo dữ liệu, populator ghi đè dữ liệu đó, rồi startup hook lại cập nhật lần nữa.

Một thay đổi có phiên bản cần mô tả:

```text
Định danh thay đổi
Điều kiện trước khi chạy
Thao tác thay đổi dự kiến
Điều kiện xác nhận sau khi chạy
Chính sách khi đã áp dụng hoặc gặp xung đột
Cách xử lý khi thất bại
```

Sửa fixture cũ rồi triển khai lại không cho biết database nào đã nhận nội dung trước đó. Với thay đổi đã áp dụng, cần quản lý lịch sử và tạo thay đổi tiếp theo theo quy trình công cụ sử dụng.

### 9.2. Import hoặc backfill lớn

Một tập hàng triệu bản ghi cần được thiết kế khác với một collection fixture nhỏ:

- Đọc theo cách phù hợp với kích thước dữ liệu.
- Chia batch hoặc chunk có ranh giới commit.
- Ghi nhận tiến độ để tiếp tục.
- Phân loại lỗi và chính sách retry/skip rõ ràng.
- Kiểm tra tổng số đã đọc, đã thay đổi và bị từ chối.
- Kiểm soát tác động lên workload đang vận hành.

Spring Batch có mô hình [chunk-oriented processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html) và metadata thực thi như JobExecution, StepExecution, ExecutionContext trong [batch domain](https://docs.spring.io/spring-batch/reference/domain.html).

Việc dùng framework batch không tự giải quyết mọi yêu cầu nghiệp vụ. Reader, writer, transaction và checkpoint vẫn phải được cấu hình đúng với store và tính chất dữ liệu.

Không coi vòng lặp save của populator là một pipeline streaming/bulk có khả năng khởi động lại từ checkpoint. Driver hoặc provider có thể tối ưu một số thao tác, nhưng đó không phải cùng một hợp đồng vận hành.

## 10. Một kế hoạch bootstrap dữ liệu tham chiếu có kiểm soát

Giả sử production cần thêm danh mục hệ thống `BOOKS`, nhưng không được thay tên do người vận hành đã chỉnh sửa.

Một kế hoạch có thể là:

```text
1. Xác định BOOKS bằng business key có ràng buộc phù hợp.
2. Xác định đây là tạo mới khi thiếu, không reset toàn bộ bản ghi.
3. Giành quyền thực thi thay đổi ở phạm vi hệ thống.
4. Kiểm tra điều kiện và thực hiện thao tác ghi theo cơ chế store.
5. Xác nhận dữ liệu đáp ứng điều kiện sau.
6. Ghi trạng thái hoàn thành của thay đổi.
```

Nếu đã tồn tại BOOKS, hành vi phải theo chính sách: giữ nguyên tên người dùng sở hữu, bổ sung field hệ thống được phép hoặc báo xung đột. Không save lại toàn bộ object từ fixture nếu điều đó sẽ reset những field ngoài phạm vi.

Nếu ứng dụng tự xây một job thay đổi dữ liệu, metadata có thể cần gồm:

| Metadata | Mục đích |
| --- | --- |
| Change ID | Nhận diện thay đổi logic |
| Phiên bản/checksum đầu vào | Biết nội dung nào đã được áp dụng |
| Trạng thái thực thi | Phân biệt chưa chạy, đang chạy, thành công, thất bại |
| Số bản ghi theo từng kết quả | Đối chiếu tác động |
| Checkpoint nếu cần | Tiếp tục sau gián đoạn |
| Thời gian và thông tin lỗi phù hợp | Hỗ trợ chẩn đoán, vận hành |

Đây là thiết kế minh họa cho một quy trình tùy chỉnh, không phải các field mà populator mặc định tự sinh.

Quan trọng hơn, việc ghi dữ liệu và trạng thái hoàn thành phải có quan hệ nhất quán. Nếu dữ liệu đã commit nhưng bước ghi “đã hoàn tất” thất bại, lần chạy lại vẫn cần xử lý đúng. Một bảng trạng thái tự tạo chưa đủ để tuyên bố exactly-once.

## 11. Phục hồi, tương thích và nguồn dữ liệu

### 11.1. Chạy fixture cũ không phải rollback

Nếu một lần nạp ghi đè tên, trạng thái hoặc quan hệ, fixture trước đó không nhất thiết chứa giá trị thực tế ngay trước thay đổi.

Phương án phục hồi cần dựa trên thiết kế thay đổi: transaction được hỗ trợ, dữ liệu trước thay đổi đã được giữ phù hợp, corrective migration hoặc quy trình khôi phục đã xác định. Không suy ra thao tác đảo tự động từ việc có file JSON.

Side effect bên ngoài database cũng cần chính sách riêng. Một lần rollback dữ liệu không tự thu hồi được thông báo hoặc thao tác đã hoàn tất ở hệ thống khác.

### 11.2. JSON gắn với class Java có độ kết dính phiên bản

Fixture dùng tên class và cấu trúc domain hiện tại. Đổi package, constructor, kiểu ID hoặc field bắt buộc có thể làm resource cũ không còn deserialize hoặc lưu được.

Migration sống qua nhiều phiên bản ứng dụng cần một hợp đồng đầu vào và thao tác ổn định hơn việc mặc định mọi entity hiện tại đọc được dữ liệu của mọi phiên bản cũ.

### 11.3. Nguồn fixture phải được kiểm soát

Resource chứa thông tin kiểu và dữ liệu sẽ đi tới repository. Không xem populator như một cổng import tổng quát nhận tùy ý payload người dùng rồi ghi thẳng.

Với import có đầu vào bên ngoài, cần một hợp đồng nhận dữ liệu, kiểm tra kiểu/field, phạm vi dữ liệu và chính sách ghi rõ ràng. Tài khoản hoặc process thực thi cũng cần đúng quyền cho nhiệm vụ.

Điểm này trực tiếp liên quan đến việc ghi production: sự tin cậy của nguồn đầu vào không được suy ra chỉ từ việc nó có cú pháp JSON hợp lệ.

## 12. Chọn công cụ theo yêu cầu thực sự

| Yêu cầu | Cách tiếp cận cần xem xét |
| --- | --- |
| Dữ liệu mẫu nhỏ cho demo/test | Repository populator với phạm vi môi trường rõ ràng |
| Dữ liệu tham chiếu production nhỏ | Bootstrap có chính sách chạy lại, khóa và lịch sử phù hợp |
| Thay đổi schema hoặc dữ liệu theo phiên bản | Công cụ migration tương thích với store |
| Nạp/chuyển đổi dữ liệu lớn | Job import/backfill có batch, checkpoint và kiểm soát lỗi |
| Thao tác phải đi qua use case nghiệp vụ | Quy trình gọi service/domain đúng hợp đồng |
| Thay đổi nhiều store hoặc hệ thống ngoài | Thiết kế điều phối và phục hồi tương ứng |

Các tình huống có giá trị để xác nhận gồm: chạy lại, khởi động hai instance cùng lúc, lỗi ở lần save giữa tập, resource sau bị lỗi, dữ liệu đã được người dùng chỉnh sửa và domain đổi phiên bản.

Populator giải quyết phần đọc dữ liệu rồi đưa đối tượng vào repository. Khi yêu cầu chuyển thành migration hoặc thay đổi production, cần có thêm một hợp đồng thực thi và vận hành đủ rõ để bảo toàn dữ liệu đang tồn tại.
