# Đánh giá lựa chọn populator, tác vụ ứng dụng hoặc công cụ migration

## 1. Bài toán: cùng là tạo dữ liệu nhưng khác trách nhiệm

Một ứng dụng dùng Spring Data có thể cần nạp danh mục mẫu khi chạy local, bổ sung cấu hình nghiệp vụ sau một bản phát hành, hoặc chuyển dữ liệu cũ sang cấu trúc mới. Cả ba việc đều có thao tác ghi dữ liệu, nhưng yêu cầu về thời điểm thực thi, khả năng chạy lại và lịch sử thay đổi rất khác nhau.

Trong phạm vi Spring Data Commons, cần phân biệt ba lựa chọn:

- **Repository populator** đọc dữ liệu đầu vào, xác định kiểu đối tượng và ghi thông qua repository. Cách này phù hợp với bộ dữ liệu nhỏ, có sẵn, thường dùng cho demo hoặc môi trường phát triển.
- **Tác vụ ứng dụng** là mã Java do ứng dụng điều phối, có thể gọi repository, dịch vụ nghiệp vụ và các thành phần khác. Cách này phù hợp khi việc khởi tạo cần tính toán, điều kiện hoặc quy trình riêng.
- **Công cụ migration** quản lý các thay đổi dữ liệu hoặc cấu trúc theo phiên bản và lưu lịch sử thực thi. Cách này phù hợp với quá trình nâng cấp có kiểm soát, đặc biệt trong môi trường production.

Repository, CRUD và metadata kiểu miền là các abstraction dùng chung. Chúng không làm cho transaction, upsert, khóa, tạo index hoặc migration trở nên giống nhau trên mọi kho dữ liệu. Quyết định phải dựa trên yêu cầu nghiệp vụ và khả năng của Spring Data module cùng datastore thực tế.

### Tình huống xuyên suốt

Hệ thống quản lý học tập có ba nhu cầu:

1. Local cần một số khách hàng và khóa học để lập trình viên thử phân trang, sắp xếp và truy vấn.
2. Môi trường triển khai cần tạo bản ghi cấu hình mặc định khi chưa tồn tại, với giá trị phụ thuộc cấu hình ứng dụng.
3. Bản phát hành mới cần bổ sung trường `normalized_email` cho dữ liệu khách hàng cũ và thiết lập ràng buộc duy nhất khi phù hợp.

Không nên mặc định chọn cùng một cơ chế cho cả ba nhu cầu. Bộ dữ liệu local, việc tính giá trị mặc định và việc nâng cấp dữ liệu đang vận hành có vòng đời khác nhau.

## 2. Xác định loại công việc trước khi chọn công cụ

| Loại công việc | Ví dụ | Yêu cầu chính | Lựa chọn thường phù hợp |
| --- | --- | --- | --- |
| Fixture hoặc dữ liệu demo | Một số khách hàng để thử màn hình tìm kiếm | Dễ đọc, dễ tạo lại, cách ly môi trường | Populator hoặc bộ nạp dữ liệu của test |
| Khởi tạo có điều kiện | Tạo cấu hình mặc định theo tenant | Quy tắc nghiệp vụ, kiểm soát chạy lại và đồng thời | Tác vụ ứng dụng |
| Dữ liệu tham chiếu theo phiên bản | Thêm mã trạng thái bắt buộc cho phiên bản mới | Thứ tự thay đổi, lịch sử triển khai | Migration hoặc tác vụ có sổ theo dõi tương đương |
| Thay đổi cấu trúc | Thêm cột, index, ràng buộc | Khả năng riêng của datastore, tương thích khi triển khai | Công cụ migration phù hợp kho dữ liệu |
| Backfill quy mô lớn | Tính lại trường cho hàng triệu bản ghi | Chia lô, checkpoint, giới hạn tải, tiếp tục sau lỗi | Tác vụ chuyên biệt, có thể phối hợp migration |

Dữ liệu tham chiếu không tự động đồng nghĩa với dữ liệu demo. Nếu một bản ghi bắt buộc phải xuất hiện trong production để phiên bản ứng dụng mới hoạt động đúng, việc bổ sung nó cần có trách nhiệm triển khai và khả năng kiểm chứng rõ ràng.

Cũng cần tách **khởi tạo dữ liệu** khỏi **tạo cấu trúc lưu trữ**. Repository populator không thay thế công cụ tạo bảng, collection, index hoặc ràng buộc. Cơ chế khởi tạo bằng script SQL của framework cũng là một lựa chọn khác; không nên gọi mọi cơ chế nạp dữ liệu lúc startup là repository populator.

## 3. Repository populator: nạp đối tượng qua repository

### 3.1. Luồng xử lý

Một repository populator đi theo luồng khái quát:

```text
Tài nguyên dữ liệu
    -> đọc và chuyển thành đối tượng miền
    -> xác định repository quản lý kiểu miền đó
    -> gọi thao tác lưu qua repository
    -> datastore thực hiện ghi theo mapping và semantics của module
```

Điểm quan trọng là populator hoạt động ở mức đối tượng và repository. Nó không có cùng vai trò với trình chạy SQL hoặc hệ thống version hóa cơ sở dữ liệu.

Ví dụ dữ liệu JSON cho bộ đọc populator dựa trên Jackson có thể có dạng:

```json
[
  {
    "_class": "com.example.learning.Customer",
    "id": "demo-customer-001",
    "name": "Lan",
    "email": "lan@example.test"
  },
  {
    "_class": "com.example.learning.Customer",
    "id": "demo-customer-002",
    "name": "Minh",
    "email": "minh@example.test"
  }
]
```

Trong cơ chế này, `_class` cung cấp thông tin kiểu để bộ đọc tạo đối tượng phù hợp. Đây là metadata của đầu vào populator; không được suy ra rằng mọi datastore sẽ lưu nguyên trường `_class` theo cùng một cách. Metadata được lưu trong kho còn phụ thuộc converter và mapping của module.

Kiểu `Customer` phải có repository được đăng ký, có cấu hình ánh xạ hợp lệ và có thể được bộ đọc tạo đối tượng. Đoạn JSON chỉ minh họa đầu vào; nó chưa phải cấu hình chạy đầy đủ. Cách đăng ký factory, bộ đọc và tài nguyên cần khớp với phiên bản Spring Data cùng thư viện JSON/XML đang sử dụng.

### 3.2. Khi nào nên dùng

Populator có giá trị khi dữ liệu tương đối nhỏ, ít logic, được quản lý cùng mã nguồn và có thể nạp lại trong môi trường có vòng đời ngắn. Ví dụ, một bộ dữ liệu local giúp lập trình viên quan sát kết quả của derived queries, projection hoặc `Pageable` với dữ liệu biết trước.

Đối với test, cần xem fixture được nạp lúc nào và được dọn thế nào. Test chia sẻ cùng một Spring context hoặc datastore có thể ảnh hưởng lẫn nhau nếu cùng sửa fixture. Số bản ghi ban đầu đúng không bảo đảm từng test được cách ly.

### 3.3. Những điều populator không tự bảo đảm

- **Không tự có lịch sử migration:** việc nạp thành công không mặc nhiên tạo phiên bản thay đổi, checksum hoặc lịch sử vận hành.
- **Không tự idempotent:** nạp lại có thể thêm bản ghi, cập nhật bản ghi hoặc thất bại, tùy ID, cách nhận diện entity mới, ràng buộc và implementation của repository.
- **Không tự có một transaction cho toàn bộ tài nguyên:** phạm vi transaction phụ thuộc cách gọi và transaction manager thực tế. Một lỗi ở giữa có thể để lại dữ liệu đã ghi trước đó.
- **Không bảo đảm thứ tự phụ thuộc nghiệp vụ chỉ từ danh sách JSON:** quan hệ giữa các đối tượng cần mapping, thứ tự nạp hoặc quy trình riêng phù hợp.
- **Không tự đồng bộ nhiều instance:** nếu nhiều bản sao ứng dụng cùng nạp, cần xử lý xung đột và cạnh tranh ở tầng phù hợp.

ID cố định giúp định danh fixture, nhưng chưa đủ để chứng minh an toàn khi chạy lại. Chẳng hạn, entity có ID gán trước có thể được repository nhận diện là mới hay đã tồn tại theo metadata khác nhau. Cần hiểu cơ chế phát hiện entity mới của module; không nên mặc định `save` là một lệnh upsert đồng nhất trên mọi kho dữ liệu.

Nếu nạp lại một đối tượng chứa giá trị mặc định, thao tác lưu còn có thể thay thế các giá trị người dùng đã chỉnh. Do đó, populator cho demo nên được bật rõ ràng trong môi trường được phép dùng dữ liệu mẫu.

## 4. Tác vụ ứng dụng: linh hoạt nhưng phải tự quản lý vòng đời

### 4.1. Vai trò của tác vụ

Tác vụ ứng dụng phù hợp khi việc tạo dữ liệu cần đọc cấu hình, tính giá trị, gọi dịch vụ nghiệp vụ hoặc xử lý theo từng tenant. Trong ứng dụng Spring Boot, `ApplicationRunner` là một điểm tích hợp có thể dùng để gọi logic khởi tạo sau khi context đã được tạo. `ApplicationRunner` thuộc Spring Boot, không phải abstraction do Spring Data Commons cung cấp.

Ví dụ dưới đây minh họa một tác vụ local có thể gọi dịch vụ riêng:

```java
@Configuration
@Profile("local")
class LocalSeedConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "app.seed",
        name = "enabled",
        havingValue = "true"
    )
    ApplicationRunner seedDefaults(DefaultSettingsInitializer initializer) {
        return args -> initializer.ensureDefaults();
    }
}
```

```yaml
# Cấu hình minh họa cho môi trường local
app:
  seed:
    enabled: true
```

Các đoạn mã cấu hình lược bỏ import và phần khai báo bean dịch vụ. `DefaultSettingsInitializer` nên là bean riêng để giữ logic nghiệp vụ và, nếu cần, áp dụng transaction qua proxy phù hợp. Không nên đặt toàn bộ quy trình khởi tạo vào constructor hoặc chỉ dựa vào một lời gọi nội bộ để kỳ vọng annotation transaction luôn có hiệu lực.

### 4.2. Định nghĩa chính sách ghi trước khi cài đặt

Giả sử repository quản lý cấu hình:

```java
interface SettingRepository extends CrudRepository<Setting, String> {
    Optional<Setting> findByCode(String code);
}
```

`Setting` là đối tượng miền được ánh xạ theo module thực tế; ví dụ không giả định annotation hay kiểu ID dùng chung cho mọi datastore. Phương thức derived query cũng cần được module đang dùng hỗ trợ.

Logic ứng dụng có thể được mô tả bằng mã giả:

```text
ensureDefaults():
    đọc cấu hình mong muốn
    tìm bản ghi theo khóa nghiệp vụ "course.page-size"
    nếu chưa có:
        tạo bản ghi với giá trị mặc định
    nếu đã có:
        giữ nguyên giá trị người vận hành đã chỉnh
    ghi nhận kết quả và lý do bỏ qua
```

Cần phân biệt ba chính sách:

| Chính sách | Khi chạy lại | Rủi ro cần xử lý |
| --- | --- | --- |
| Chỉ tạo khi thiếu | Giữ nguyên dữ liệu đã tồn tại | Cạnh tranh giữa kiểm tra và tạo |
| Đồng bộ về trạng thái mong muốn | Cập nhật dữ liệu khác cấu hình | Ghi đè chỉnh sửa hợp lệ |
| Chuyển đổi một lần theo phiên bản | Bỏ qua khi bước đó đã hoàn tất | Cần lịch sử và cơ chế tiếp tục sau lỗi |

Chính sách thứ ba gần với migration. Nếu tự xây dựng bằng Java, ứng dụng phải tự cung cấp những khả năng cần thiết, như mã bước thay đổi, trạng thái, khóa điều phối và kiểm chứng hoàn tất.

### 4.3. Idempotency không đồng nghĩa với an toàn khi chạy đồng thời

Mẫu `findByCode` rồi `save` có thể cho kết quả đúng khi một tiến trình chạy hai lần liên tiếp. Nó vẫn có thể tạo trùng khi hai tiến trình cùng thấy rằng bản ghi chưa tồn tại.

```text
Instance A: tìm -> chưa có
Instance B: tìm -> chưa có
Instance A: tạo bản ghi
Instance B: cũng tạo bản ghi
```

Tùy datastore, cần kết hợp một hoặc nhiều biện pháp:

- Ràng buộc hoặc unique index cho khóa nghiệp vụ.
- Thao tác ghi có điều kiện hoặc upsert nguyên tử khi kho dữ liệu hỗ trợ đúng semantics cần thiết.
- Khóa điều phối hoặc cơ chế chọn một tiến trình chạy tác vụ.
- Xử lý lỗi trùng khóa và đọc lại bản ghi đã được tiến trình khác tạo.

Không nên bắt mọi exception rồi coi là thành công. Lỗi kết nối, lỗi mapping và vi phạm dữ liệu khác phải được xử lý riêng. Với kho có transaction, một lỗi ghi có thể khiến transaction không còn dùng được; việc đọc lại hoặc retry cần đặt ở ranh giới transaction thích hợp.

### 4.4. Dữ liệu lớn cần tác vụ có thể tiếp tục

Không nên nạp toàn bộ dữ liệu bằng `findAll()` rồi sửa trong bộ nhớ nếu số lượng bản ghi lớn. Có thể dùng phân trang, sắp xếp ổn định hoặc truy vấn theo mốc ID để chia lô, tùy API và module hỗ trợ.

Nếu tác vụ cập nhật chính trường dùng để lọc tập chưa xử lý, phân trang theo offset có thể bỏ sót bản ghi khi tập kết quả co lại. Một chiến lược theo khóa ổn định hoặc lấy lại lô đầu tiên của tập chưa xử lý có thể phù hợp hơn. Mỗi chiến lược vẫn cần xét dữ liệu được ghi thêm trong lúc chạy.

Tác vụ dài nên có checkpoint, số bản ghi đã xử lý, cách retry và điều kiện hoàn tất. Những việc này thường nên tách khỏi startup để một lần backfill lớn không làm ứng dụng chậm sẵn sàng hoặc liên tục khởi động thất bại.

## 5. Công cụ migration: quản lý sự tiến hóa theo phiên bản

### 5.1. Những khả năng cần tìm

Một công cụ migration phù hợp thường cung cấp hoặc hỗ trợ xây dựng:

- Danh sách thay đổi có thứ tự hoặc quan hệ phụ thuộc rõ ràng.
- Lịch sử thay đổi đã áp dụng cho từng môi trường.
- Cơ chế phát hiện thay đổi nội dung đã được áp dụng, tùy loại migration và cấu hình.
- Điều phối để tránh nhiều tiến trình cùng thực thi một bước thay đổi.
- Kết quả và lỗi phục vụ vận hành, cùng khả năng chạy trong quy trình triển khai.

Không phải mọi công cụ đều cung cấp cùng một cơ chế rollback, transaction hoặc checksum. Ví dụ, Flyway và Liquibase thường được dùng trong hệ sinh thái cơ sở dữ liệu quan hệ; khả năng hỗ trợ datastore cụ thể, edition, extension và kiểu thay đổi cần được xác nhận cho công cụ đã chọn. Không suy ra rằng công cụ chạy SQL sẽ quản lý được mọi repository của Spring Data.

### 5.2. Ví dụ thay đổi dữ liệu có phiên bản

Trong một ứng dụng dùng cơ sở dữ liệu quan hệ, một bước migration có thể thêm mã trạng thái bắt buộc:

```sql
-- Ví dụ minh họa cho một bước migration có phiên bản.
-- Giả định bảng course_status đã tồn tại.
INSERT INTO course_status (code, label)
VALUES ('ARCHIVED', 'Đã lưu trữ');
```

Nếu bước này được quản lý bằng loại migration có phiên bản chạy một lần, công cụ dựa vào lịch sử để biết đã áp dụng. Bản thân câu `INSERT` trên không idempotent nếu bị chạy trực tiếp lần thứ hai. Đó là hai lớp bảo vệ khác nhau: **quản lý lần thực thi** và **semantics của câu lệnh**.

Vẫn cần định nghĩa ràng buộc duy nhất cho `code` và cách xử lý trường hợp dữ liệu đã được tạo ngoài migration. Lịch sử migration không sửa được trạng thái dữ liệu đã bị thay đổi thủ công. Khi cần tương thích với dữ liệu có sẵn, dùng tiền điều kiện hoặc câu lệnh phù hợp với dialect và chính sách của hệ thống.

Với thay đổi đã được áp dụng trong môi trường dùng chung, thông thường nên tạo migration tiếp theo để sửa dữ liệu, thay vì âm thầm sửa nội dung migration cũ. Việc sửa lịch sử, repair hoặc đánh dấu bỏ qua phải tuân theo quy trình của công cụ và được kiểm chứng riêng.

### 5.3. Transaction và rollback có giới hạn thực tế

Không thể mặc định tất cả DDL và DML đều được rollback chung. Khả năng transaction của thao tác thay đổi cấu trúc phụ thuộc cơ sở dữ liệu; một số công cụ còn chia phạm vi transaction theo cách riêng.

Cũng không thể coi rollback ứng dụng là rollback dữ liệu. Khi người dùng đã tạo dữ liệu theo cấu trúc mới, quay về binary cũ có thể không đủ an toàn. Một kế hoạch nâng cấp cần xác định:

1. Phiên bản cũ và mới cùng chạy được trong khoảng chuyển tiếp hay không.
2. Dữ liệu nào có thể phục hồi từ backup hoặc bản sao trước chuyển đổi.
3. Khi nào dùng migration bổ sung để sửa tiến về phía trước.
4. Thao tác nào là không thể đảo ngược mà không mất thông tin.

Một hướng triển khai thường hữu ích là thêm cấu trúc tương thích trước, backfill có kiểm soát, chuyển ứng dụng sang sử dụng cấu trúc mới, rồi mới bỏ cấu trúc cũ khi đã hết phụ thuộc.

## 6. Ma trận đánh giá ba lựa chọn

| Tiêu chí | Repository populator | Tác vụ ứng dụng | Công cụ migration |
| --- | --- | --- | --- |
| Đầu vào chủ yếu | Tài nguyên mô tả đối tượng miền | Mã Java và cấu hình | Script hoặc changeset theo công cụ |
| Qua repository | Có trong cơ chế populator repository | Có thể, do người viết chọn | Không bắt buộc; thường thao tác trực tiếp với datastore |
| Logic nghiệp vụ phức tạp | Hạn chế, dễ vượt mục đích | Linh hoạt | Phụ thuộc công cụ; không nên làm changelog khó kiểm soát |
| Lịch sử thay đổi | Phải bổ sung | Phải bổ sung | Là năng lực cốt lõi của công cụ phù hợp |
| Khả năng chạy lại | Phụ thuộc dữ liệu và thao tác lưu | Phải thiết kế | Phụ thuộc loại migration và lịch sử |
| Nhiều instance | Cần cơ chế riêng | Cần cơ chế riêng | Thường có điều phối, cần kiểm tra phạm vi bảo đảm |
| Thay đổi schema/index | Không phải trách nhiệm chính | Có thể gọi API riêng của datastore | Phù hợp nếu công cụ hỗ trợ datastore đó |
| Backfill lớn | Thường không phù hợp | Phù hợp khi có chia lô và checkpoint | Có thể điều phối; cần xét tải và transaction |
| Tính độc lập với phiên bản entity | Bị ràng buộc vào kiểu miền và mapping | Bị ràng buộc nếu dùng entity hiện tại | Có thể tách khỏi entity nếu dùng script/API ổn định |
| Trường hợp điển hình | Demo, fixture nhỏ | Khởi tạo có điều kiện, xử lý nghiệp vụ | Tiến hóa cấu trúc và dữ liệu theo bản phát hành |

Bảng này không thay thế việc kiểm tra module cụ thể. Ví dụ, `CrudRepository` cho API CRUD dùng chung nhưng không quy định một cơ chế khóa phân tán, không tự cung cấp unique index và không biến thao tác ghi lên hai datastore thành một transaction chung.

Một rủi ro của migration viết qua repository là mã của migration cũ có thể tiếp tục phụ thuộc entity đã thay đổi ở phiên bản mới. Khi dựng một môi trường mới và chạy lại toàn bộ lịch sử, migration cũ có thể không còn tương thích. Nếu chọn hướng này, cần thiết kế dữ liệu và lớp truy cập ổn định cho từng bước thay đổi, thay vì mặc định dùng entity mới nhất cho mọi phiên bản lịch sử.

## 7. Quy trình ra quyết định

Có thể lần lượt trả lời các câu hỏi sau:

1. **Dữ liệu có được phép xuất hiện trong production không?** Nếu chỉ là demo, giới hạn rõ môi trường và ưu tiên cơ chế đơn giản, có thể tạo lại.
2. **Đây có phải một bước nâng cấp bắt buộc theo phiên bản không?** Nếu có, ưu tiên migration hoặc cơ chế tương đương có lịch sử và điều phối.
3. **Có cần tính toán, truy cập dịch vụ hoặc quyết định theo tenant không?** Nếu có, tác vụ ứng dụng thường phù hợp hơn tệp dữ liệu tĩnh.
4. **Có bao nhiêu bản ghi và có thể chạy trong cửa sổ triển khai không?** Dữ liệu lớn có thể cần backfill độc lập, thay vì giữ một transaction dài.
5. **Chạy lại, chạy đồng thời và lỗi giữa chừng sẽ để lại trạng thái nào?** Nếu chưa trả lời được, thiết kế chưa đủ để đưa vào vận hành.
6. **Datastore hỗ trợ điều gì?** Xác định cụ thể transaction, uniqueness, thao tác ghi có điều kiện, DDL và cơ chế khóa mà phương án cần dùng.

Các cơ chế có thể phối hợp. Điều cần tránh là để hai cơ chế cùng sở hữu một tập dữ liệu mà không có ranh giới. Ví dụ, migration vừa thêm nhãn trạng thái mới trong khi runner luôn đồng bộ về danh sách cũ sẽ khiến trạng thái sau triển khai khó dự đoán.

## 8. Áp dụng vào ba tình huống

### 8.1. Bộ dữ liệu local phục vụ học Repository

**Chọn:** populator với tài nguyên dữ liệu được quản lý cùng ứng dụng.

**Lý do:** dữ liệu ít, giá trị cố định và môi trường có thể tạo lại. Lập trình viên cần dữ liệu ổn định để thử CRUD, derived query, phân trang, sắp xếp và projection.

**Điều kiện triển khai:** bật bằng profile/cấu hình local; bảo đảm datastore đích đúng; tạo ID và quan hệ phù hợp module; xác định chạy lại sẽ cập nhật hay báo lỗi. Nếu mục tiêu là bắt đầu từ trạng thái sạch, quy trình tạo lại datastore phải được thiết kế riêng, không gắn thao tác xóa rộng vào khởi động thông thường.

**Kiểm chứng:** dữ liệu mẫu xuất hiện đầy đủ; chạy lại không tạo kết quả ngoài chính sách; môi trường production không bật bộ nạp demo.

### 8.2. Cấu hình mặc định theo tenant

**Chọn:** tác vụ ứng dụng hoặc quy trình khởi tạo tenant.

**Lý do:** giá trị phụ thuộc cấu hình và trạng thái hiện tại. Tenant có thể được tạo sau thời điểm startup, nên runner lúc khởi động chưa chắc là điểm kích hoạt đầy đủ.

**Điều kiện triển khai:** có khóa nghiệp vụ như `(tenant_id, code)` với biện pháp chống trùng phù hợp; phân biệt giá trị mặc định với giá trị người dùng đã chỉnh; đặt transaction và retry theo module; quy định ai được chạy tác vụ.

**Kiểm chứng:** gọi lại không ghi đè cấu hình đã chỉnh; hai tiến trình khởi tạo cùng tenant không tạo trùng; lỗi giữa chừng có thể tiếp tục theo chính sách đã định.

### 8.3. Bổ sung `normalized_email` cho dữ liệu đang vận hành

**Chọn:** migration để quản lý thay đổi cấu trúc và mốc triển khai, kết hợp tác vụ backfill nếu dữ liệu lớn.

**Lý do:** đây là sự tiến hóa dữ liệu production, cần thứ tự và khả năng theo dõi. Tính toán có thể gặp email trùng hoặc không hợp lệ, nên không thể chỉ thêm index duy nhất rồi kỳ vọng mọi dữ liệu cũ đều thỏa mãn.

**Trình tự minh họa:**

1. Xác định quy tắc chuẩn hóa và cách xử lý xung đột.
2. Thêm trường/cột tương thích với phiên bản ứng dụng đang chạy.
3. Triển khai logic ghi giá trị chuẩn hóa cho bản ghi mới hoặc được cập nhật.
4. Backfill dữ liệu cũ theo lô, với checkpoint và xử lý cạnh tranh để không ghi đè giá trị mới bằng dữ liệu đọc cũ.
5. Kiểm tra bản ghi thiếu, không hợp lệ và trùng theo quy tắc nghiệp vụ.
6. Thiết lập ràng buộc/index khi điều kiện đã thỏa mãn và datastore hỗ trợ.
7. Chuyển truy vấn sang trường mới và dọn cấu trúc cũ ở bản phát hành thích hợp.

Không đặt toàn bộ quy trình này vào populator chỉ vì cuối cùng nó cũng ghi các đối tượng khách hàng.

## 9. Quan hệ với auditing, callback và truy vấn

Nếu dữ liệu được ghi qua repository, các callback, sự kiện hoặc auditing có thể tham gia tùy module, cấu hình và đường ghi cụ thể. Không nên suy ra rằng mọi dạng bulk operation, cập nhật trực tiếp hoặc migration script sẽ kích hoạt cùng cơ chế.

Ví dụ, `@CreatedDate`, `@LastModifiedDate` hoặc thông tin người thực hiện không tự có ý nghĩa chỉ vì dữ liệu được đưa vào lúc startup. Cần xác định auditing đã bật chưa, nguồn thời gian là gì và `AuditorAware` trả về ai khi không có người dùng đăng nhập. Với migration ghi trực tiếp, nếu nghiệp vụ cần các cột audit, script hoặc tác vụ phải quản lý chúng theo chính sách tương ứng.

Projection hữu ích để đọc một tập trường phục vụ kiểm tra hoặc đối soát; nó không tự trở thành đối tượng miền có thể lưu bằng populator. Tương tự, derived query hoặc query by example có thể hỗ trợ tìm bản ghi đã tồn tại, nhưng không tạo tính nguyên tử cho chuỗi kiểm tra rồi ghi và không thay thế unique constraint/index.

Khi đối soát theo trang, dùng thứ tự ổn định và tính đến thay đổi đồng thời. Nếu cần tổng số bản ghi, cần cân nhắc chi phí truy vấn đếm; không phải tác vụ nào cũng cần tải một `Page` có tổng số phần tử cho từng lô.

## 10. Kiểm chứng phương án trước khi đưa vào sử dụng

Một phương án khởi tạo nên có kết quả mong đợi cho các tình huống sau:

| Tình huống | Kết quả cần xác định |
| --- | --- |
| Datastore mới, chưa có dữ liệu | Đủ dữ liệu và cấu trúc cần thiết |
| Chạy lại trên trạng thái đã hoàn tất | Bỏ qua hoặc cập nhật đúng chính sách, không tạo trùng ngoài ý muốn |
| Đã có dữ liệu do người dùng chỉnh | Giữ nguyên hoặc chuyển đổi theo quy tắc được phê duyệt |
| Lỗi ở giữa quá trình | Nhận biết phần đã thực hiện, có cách tiếp tục hoặc phục hồi |
| Hai instance cùng chạy | Không tạo trạng thái sai do cạnh tranh |
| Nâng cấp từ dữ liệu của phiên bản trước | Các bước chạy đúng thứ tự và tương thích |
| Tạo mới môi trường từ toàn bộ lịch sử | Migration cũ vẫn thực thi được với mã và công cụ hiện tại |

Thông tin vận hành tối thiểu nên gồm định danh tác vụ hoặc migration, datastore/tenant đích, phiên bản dữ liệu, thời điểm bắt đầu/kết thúc, số bản ghi tạo/cập nhật/bỏ qua/lỗi và checkpoint nếu có. Tránh ghi dữ liệu cá nhân hoặc bí mật vào log chỉ để chứng minh việc khởi tạo đã chạy.

Với nhiều kho dữ liệu, cần theo dõi trạng thái của từng kho và xử lý trường hợp một kho thành công, kho khác thất bại. Transaction ở một repository không tự bao phủ repository thuộc datastore khác.

## 11. Bài tập vận dụng

Một ứng dụng có 30 bản ghi demo, 12 mã nghiệp vụ bắt buộc trong production và 2 triệu bản ghi cần bổ sung trường tìm kiếm mới.

Hãy thiết kế phương án cho từng nhóm dữ liệu, làm rõ:

1. Cơ chế nào chịu trách nhiệm tạo hoặc chuyển đổi dữ liệu.
2. Điều kiện kích hoạt và người/tiến trình sở hữu việc thực thi.
3. Chính sách khi chạy lại và khi dữ liệu đã bị chỉnh.
4. Cách chống cạnh tranh giữa nhiều instance.
5. Cách phát hiện hoàn tất, xử lý lỗi và tiếp tục sau gián đoạn.

Một hướng giải hợp lý là dùng populator cho demo, migration cho danh mục bắt buộc theo phiên bản, và phối hợp migration với tác vụ backfill có checkpoint cho dữ liệu lớn. Nếu chọn phương án khác, cần chứng minh nó vẫn đáp ứng các yêu cầu về lịch sử, tính đúng đắn và vận hành.

## 12. Kết luận

Chọn repository populator khi cần nạp bộ đối tượng nhỏ, tĩnh và có thể kiểm soát vòng đời môi trường. Chọn tác vụ ứng dụng khi cần logic nghiệp vụ, điều kiện hoặc quy trình có thể tiếp tục. Chọn công cụ migration khi cần quản lý sự tiến hóa của cấu trúc và dữ liệu theo phiên bản.

Spring Data Commons giúp thống nhất cách biểu đạt repository và nhiều thao tác truy cập dữ liệu. Trách nhiệm bảo đảm chạy lại, chống trùng, điều phối, transaction, auditing và khả năng nâng cấp vẫn cần được thiết kế theo module cùng kho dữ liệu thực tế.
