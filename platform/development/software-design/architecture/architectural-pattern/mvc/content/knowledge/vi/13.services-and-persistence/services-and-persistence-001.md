# Vai trò của dịch vụ ứng dụng trong một ca sử dụng

## Mục tiêu

Trong kiến trúc MVC, Controller tiếp nhận request và View trình bày kết quả. Model chứa trạng thái và quy tắc nghiệp vụ. Khi một thao tác cần phối hợp nhiều bước như tải dữ liệu, kiểm tra quyền, gọi hành vi domain, lưu thay đổi và tạo kết quả trả về, ứng dụng cần một nơi điều phối rõ ràng. Nơi đó thường được gọi là dịch vụ ứng dụng (Application Service).

Dịch vụ ứng dụng biểu diễn một ca sử dụng mà hệ thống cung cấp cho người dùng hoặc hệ thống khác. Nó kết nối ranh giới giao tiếp với Model/domain và các cổng hạ tầng như repository, nhưng không thay thế quy tắc nghiệp vụ của domain. Một dịch vụ ứng dụng tốt làm rõ luồng công việc, ranh giới transaction và kết quả của thao tác.

Bài học này giải thích vai trò của Application Service trong MVC, cách tổ chức một use case, cách phối hợp domain và persistence, cách xử lý transaction, quyền truy cập, lỗi và tác dụng phụ, cùng chiến lược kiểm thử. Ví dụ sử dụng Java và Spring để minh họa.

Sau khi học, người học có thể:

- Giải thích use case và vai trò của Application Service.
- Phân biệt Application Service với Controller, Domain Service và Repository.
- Thiết kế command, query và kết quả của một ca sử dụng.
- Điều phối việc tải dữ liệu, kiểm tra quyền, gọi domain và lưu thay đổi.
- Xác định ranh giới transaction và cách xử lý tác dụng phụ.
- Ánh xạ lỗi ứng dụng sang phản hồi MVC hoặc API.
- Kiểm thử ca sử dụng độc lập với web và cơ sở dữ liệu.

## 1. Use case là đơn vị hành vi mà ứng dụng cung cấp

Một ứng dụng không chỉ là tập hợp màn hình hoặc bảng dữ liệu. Nó cung cấp các hành động có ý nghĩa đối với người dùng: tạo đơn hàng, đăng ký khóa học, duyệt yêu cầu, thanh toán, cập nhật hồ sơ hoặc hủy đặt chỗ.

Mỗi hành động như vậy là một ca sử dụng (use case). Use case mô tả mục tiêu mà một actor muốn đạt được và cách ứng dụng phối hợp các bước để hoàn thành mục tiêu đó.

Ví dụ, ca sử dụng “Đăng ký khóa học” có thể gồm:

1. Nhận yêu cầu đăng ký và danh tính người học.
2. Tải khóa học và hồ sơ người học.
3. Kiểm tra người học có quyền đăng ký trong ngữ cảnh hiện tại.
4. Yêu cầu domain kiểm tra điều kiện đăng ký.
5. Tạo đăng ký và cập nhật trạng thái liên quan.
6. Lưu các thay đổi trong một transaction.
7. Trả kết quả đăng ký cho Controller.
8. Phát thông tin cần thiết cho các tác vụ tiếp theo sau khi dữ liệu đã được lưu thành công.

Controller không nên tự viết toàn bộ các bước này. Nếu một endpoint chứa logic tải nhiều repository, kiểm tra trạng thái, thay đổi entity và lưu dữ liệu, nó đang gánh trách nhiệm của use case.

Application Service cung cấp một điểm gọi có tên rõ ràng như RegisterForCourse. Controller gọi phương thức đó để thực hiện mục tiêu của người dùng.

## 2. Application Service đứng ở đâu trong kiến trúc MVC?

MVC phân chia trách nhiệm tiếp nhận tương tác, quản lý Model và trình bày View. Trong ứng dụng thực tế, một lớp ứng dụng thường nằm giữa Controller và domain để điều phối ca sử dụng.

    Browser / API Client
            |
            | HTTP request
            v
        Controller
            |
            | command / query
            v
      Application Service
            |
            | điều phối use case
            +--------------------+
            |                    |
            v                    v
       Domain Model         Repository Port
            |                    |
            | hành vi             | lưu / tải
            v                    v
       Domain Result       Persistence Adapter
            |                    |
            +---------+----------+
                      |
                      v
              Application Result
                      |
                      v
                  Controller
                      |
              View Model / DTO
                      |
                      v
                HTML / JSON

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm chính |
|---|---|
| Controller | Nhận HTTP request, binding đầu vào, phối hợp bảo mật ở ranh giới và tạo response |
| Application Service | Điều phối một use case, xác định trình tự gọi, ranh giới transaction và kết quả |
| Domain Model | Bảo vệ bất biến và thực hiện hành vi nghiệp vụ |
| Domain Service | Thực hiện quy tắc nghiệp vụ không tự nhiên thuộc về một entity/value object cụ thể |
| Repository | Cung cấp cách tải và lưu aggregate hoặc dữ liệu theo hợp đồng |
| Persistence Adapter | Triển khai repository bằng ORM, SQL hoặc hệ thống lưu trữ cụ thể |
| View / API Serializer | Biến dữ liệu trình bày thành HTML, JSON hoặc representation khác |

Application Service thuộc application layer. Nó biết use case cần phối hợp những gì, nhưng không nên phụ thuộc vào chi tiết giao thức HTTP, template engine hoặc câu SQL cụ thể.

### Controller gọi use case thay vì điều phối toàn bộ quy trình

Một Controller có thể ngắn như sau:

    @PostMapping("/courses/{courseId}/registrations")
    public String register(
            @PathVariable UUID courseId,
            @AuthenticationPrincipal AppPrincipal principal,
            RedirectAttributes redirectAttributes) {

        RegisterForCourseResult result =
                registerForCourse.execute(
                        new RegisterForCourseCommand(
                                principal.userId(),
                                courseId));

        redirectAttributes.addFlashAttribute(
                "message", "Đăng ký thành công");

        return "redirect:/registrations/" + result.registrationId();
    }

Controller lấy ID từ route và danh tính từ security context. Nó chuyển chúng thành command, gọi use case rồi chọn redirect. Nó không tự kiểm tra chỗ trống, thay đổi trạng thái khóa học hoặc ghi repository.

Với API JSON, một Controller khác có thể gọi cùng use case và chuyển kết quả thành response DTO. Như vậy, một hành vi ứng dụng có thể phục vụ nhiều giao diện mà không nhân đôi quy tắc.

## 3. Trách nhiệm của Application Service

Application Service không phải nơi chứa mọi logic. Nó có một tập trách nhiệm tương đối cụ thể.

### Điều phối các bước của use case

Nó xác định trình tự cần thiết: tải dữ liệu, kiểm tra điều kiện ở cấp ứng dụng, gọi hành vi domain, lưu thay đổi và trả kết quả.

Ví dụ, để tạo đơn hàng, Application Service có thể tải khách hàng, tải các sản phẩm được yêu cầu, gọi domain tạo đơn, lưu đơn và ghi nhận event cần phát sau transaction. Việc tính giá cuối cùng hoặc kiểm tra bất biến của đơn vẫn thuộc domain hoặc thành phần chuyên trách.

### Xác định ranh giới transaction

Một use case thường cần nhiều thao tác persistence được commit cùng nhau. Application Service là nơi tự nhiên để đặt ranh giới transaction, vì nó biết toàn bộ thao tác nào thuộc cùng một mục tiêu nghiệp vụ.

Ví dụ, tạo đăng ký có thể cần lưu Registration và cập nhật số chỗ đã giữ. Nếu hai thay đổi phải cùng thành công hoặc cùng thất bại, chúng cần nằm trong cùng transaction hoặc một cơ chế nhất quán được thiết kế rõ ràng.

### Điều phối các cổng hạ tầng

Application Service có thể gọi repository, cổng thanh toán, cổng gửi thông báo hoặc cổng đọc dữ liệu. Nó nên phụ thuộc vào interface/hợp đồng mà ứng dụng định nghĩa, để phần triển khai cụ thể có thể thay đổi.

### Xác định ngữ cảnh người thực hiện và quyền use case

Use case thường cần biết ai đang thực hiện hành động. Controller nên lấy danh tính từ principal đã xác thực và truyền actor ID hoặc một context phù hợp. Application Service có thể phối hợp kiểm tra quyền trên tài nguyên hoặc gọi một policy service.

Không lấy danh tính hoặc vai trò từ một trường request do client tự khai báo rồi tin tưởng giá trị đó.

### Trả kết quả có cấu trúc

Use case nên trả một kết quả đủ để lớp giao tiếp quyết định phản hồi. Kết quả có thể chứa ID tài nguyên mới, trạng thái hoặc dữ liệu cần cho bước tiếp theo. Không nên trả trực tiếp đối tượng HTTP ResponseEntity từ Application Service vì điều đó làm application layer phụ thuộc Spring MVC.

## 4. Những việc Application Service không nên sở hữu

Ranh giới rõ ràng giúp use case dễ thay đổi và kiểm thử.

| Việc | Nơi phù hợp hơn |
|---|---|
| Kiểm tra một đơn hàng có được chuyển trạng thái hay không | Domain Model |
| Tính quy tắc giá, giảm giá hoặc giới hạn nghiệp vụ | Domain Model / Domain Service |
| Chuyển chuỗi path thành UUID | Web binding / Controller boundary |
| Chọn template HTML hoặc status HTTP | Controller / presentation layer |
| Viết SQL và quản lý mapping ORM | Persistence Adapter |
| Tạo nội dung email theo mẫu giao diện | Notification Adapter hoặc presentation của thông báo |
| Quyết định một giao dịch phải commit hay rollback | Application Service và transaction infrastructure |

Application Service có thể gọi domain để hỏi hoặc yêu cầu thực hiện hành vi, nhưng không nên sao chép quy tắc domain thành một loạt câu if. Nếu quy tắc bị lặp trong nhiều use case, nó sẽ dễ lệch nhau khi chính sách thay đổi.

### Application Service và Domain Service

Tên hai lớp có thể giống nhau nhưng mục đích khác nhau.

**Application Service** điều phối use case. Nó biết một hành động cần tải aggregate nào, gọi phương thức nào, lưu gì và trả kết quả gì.

**Domain Service** diễn đạt một quy tắc nghiệp vụ không phù hợp tự nhiên với một entity hoặc value object. Nó làm việc với khái niệm domain và không nên điều khiển HTTP hay transaction ứng dụng.

Ví dụ, RegisterForCourse có thể là Application Service. Một RegistrationPolicy có thể là Domain Service nếu quyết định đủ điều kiện đăng ký cần phối hợp nhiều khái niệm domain.

### Application Service và Repository

Repository cung cấp khả năng tải/lưu aggregate hoặc truy vấn theo hợp đồng. Nó không quyết định use case hoàn chỉnh. Application Service gọi repository theo trình tự cần thiết, còn repository không nên biết Controller hoặc View.

### Không biến Application Service thành God Service

Một lớp có hàng chục phương thức không liên quan như RegisterCourse, SendInvoice, UpdateProfile, ExportReport và CancelSubscription thường đang gom nhiều use case. Có thể tổ chức theo hành vi hoặc nhóm nghiệp vụ, ví dụ RegistrationService, ProfileService và BillingService.

Không cần tạo một service class cho mỗi dòng CRUD nếu nó chỉ chuyển tiếp vô nghĩa. Hãy tạo abstraction khi nó thể hiện một hành vi ứng dụng, điều phối thực sự hoặc ranh giới có giá trị.

## 5. Thiết kế command, query và kết quả use case

Command biểu diễn yêu cầu thay đổi trạng thái. Query biểu diễn yêu cầu đọc dữ liệu. Tách hai loại giúp ý định và quyền tác động trở nên rõ ràng.

### Command

Một command nên chứa những dữ liệu cần thiết để thực hiện use case:

    public record RegisterForCourseCommand(
            UUID actorId,
            UUID courseId) {
    }

actorId đại diện người đã được xác thực ở ranh giới giao tiếp. courseId là tài nguyên được yêu cầu. Không đưa toàn bộ HTTP request, session hoặc servlet object vào command.

Command không nên mang các trường mà client không được phép quyết định, chẳng hạn registrationStatus, createdAt hoặc approvedBy.

### Kết quả

Một use case có thể trả result object:

    public record RegisterForCourseResult(
            UUID registrationId,
            RegistrationStatus status) {
    }

Kết quả không nhất thiết là toàn bộ entity. Nó chỉ cần cung cấp thông tin mà caller cần để hoàn thành phản hồi hoặc luồng điều khiển tiếp theo.

Nếu thao tác không cần trả dữ liệu, có thể dùng kiểu void hoặc một kết quả đơn giản. Nếu có nhiều kết quả nghiệp vụ dự kiến, có thể biểu diễn bằng kiểu kết quả rõ ràng hoặc exception theo quy ước của ứng dụng.

### Query

Query có thể được biểu diễn bằng một record riêng:

    public record GetCourseDetailsQuery(UUID courseId) {
    }

Application Service hoặc query handler gọi một query port và trả một projection/read model. Với thao tác đọc phức tạp, có thể dùng query service riêng để tối ưu truy vấn mà không cần tải toàn bộ aggregate.

### Command và Query không phải HTTP DTO

Một request DTO mô tả hợp đồng mà client gửi. Command/query mô tả yêu cầu nội bộ của application layer. Hai loại có thể giống nhau ở ứng dụng nhỏ, nhưng không bắt buộc phải trùng nhau.

Ví dụ, request API có thể nhận courseCode dạng chuỗi, Controller parse thành UUID rồi tạo command. Command không cần biết client gửi JSON hay form HTML.

## 6. Ví dụ Java: use case đăng ký khóa học

Ví dụ sau cho thấy Application Service phối hợp repository, domain model và transaction. Các interface là hợp đồng minh họa; implementation thực tế phụ thuộc hệ thống.

### Domain model

    public final class Course {
        private final UUID id;
        private final int capacity;
        private int registeredCount;
        private boolean registrationOpen;

        public Course(
                UUID id,
                int capacity,
                int registeredCount,
                boolean registrationOpen) {
            this.id = id;
            this.capacity = capacity;
            this.registeredCount = registeredCount;
            this.registrationOpen = registrationOpen;
        }

        public void registerOne() {
            if (!registrationOpen) {
                throw new RegistrationClosedException();
            }

            if (registeredCount >= capacity) {
                throw new CourseFullException();
            }

            registeredCount++;
        }

        public UUID id() {
            return id;
        }
    }

Course bảo vệ các điều kiện của chính nó. Bên gọi không thể tăng registeredCount tùy ý; nó phải yêu cầu hành vi registerOne(). Domain model là nơi duy trì bất biến rằng không được đăng ký khi đã đóng hoặc hết chỗ.

Trong ứng dụng thật, cần xem xét concurrency khi nhiều request đăng ký cùng lúc. Một phép kiểm tra trong bộ nhớ không đủ bảo vệ sức chứa nếu nhiều transaction cùng đọc một số chỗ còn lại và cùng cập nhật. Phần transaction và concurrency sẽ được bàn ở mục sau.

### Repository port

    public interface CourseRepository {
        Optional<Course> findById(UUID courseId);
        void save(Course course);
    }

    public interface RegistrationRepository {
        boolean existsByCourseAndStudent(
                UUID courseId,
                UUID studentId);

        void save(Registration registration);
    }

Repository interface thể hiện nhu cầu của application/domain. Implementation có thể dùng JPA, JDBC hoặc dịch vụ lưu trữ khác.

### Command và result

    public record RegisterForCourseCommand(
            UUID actorId,
            UUID courseId) {
    }

    public record RegisterForCourseResult(
            UUID registrationId,
            RegistrationStatus status) {
    }

### Application Service

    @Service
    public class RegisterForCourse {
        private final CourseRepository courses;
        private final RegistrationRepository registrations;
        private final RegistrationAccessPolicy accessPolicy;

        public RegisterForCourse(
                CourseRepository courses,
                RegistrationRepository registrations,
                RegistrationAccessPolicy accessPolicy) {
            this.courses = courses;
            this.registrations = registrations;
            this.accessPolicy = accessPolicy;
        }

        @Transactional
        public RegisterForCourseResult execute(
                RegisterForCourseCommand command) {

            accessPolicy.checkCanRegister(
                    command.actorId(),
                    command.courseId());

            Course course = courses.findById(command.courseId())
                    .orElseThrow(CourseNotFoundException::new);

            boolean alreadyRegistered =
                    registrations.existsByCourseAndStudent(
                            command.courseId(),
                            command.actorId());

            if (alreadyRegistered) {
                throw new DuplicateRegistrationException();
            }

            course.registerOne();

            Registration registration = Registration.create(
                    command.courseId(),
                    command.actorId());

            courses.save(course);
            registrations.save(registration);

            return new RegisterForCourseResult(
                    registration.id(),
                    registration.status());
        }
    }

Đoạn code minh họa cách phân chia trách nhiệm:

- Application Service xác định trình tự thực hiện use case.
- Access policy kiểm tra quyền trong ngữ cảnh nghiệp vụ.
- Repository tải dữ liệu cần thiết.
- Course thực thi bất biến sức chứa và trạng thái mở đăng ký.
- Registration tạo đối tượng đăng ký hợp lệ.
- Transaction bao trùm các thay đổi cần commit cùng nhau.
- Result trả ID và trạng thái cho Controller.

Ví dụ giả định các repository và domain object tham gia cùng persistence context hoặc được lưu trong cùng transaction manager. Nếu dữ liệu nằm ở nhiều hệ thống độc lập, một transaction cơ sở dữ liệu không thể tự bảo đảm tính nguyên tử xuyên các hệ thống đó; cần thiết kế quy trình phân tán phù hợp.

### Controller gọi use case

    @PostMapping("/courses/{courseId}/registrations")
    public ResponseEntity<RegistrationResponse> register(
            @PathVariable UUID courseId,
            @AuthenticationPrincipal AppPrincipal principal) {

        RegisterForCourseResult result = registerForCourse.execute(
                new RegisterForCourseCommand(
                        principal.userId(),
                        courseId));

        RegistrationResponse response =
                new RegistrationResponse(
                        result.registrationId(),
                        result.status().name());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(response);
    }

Controller nhận dữ liệu từ HTTP, lấy actor ID từ principal, gọi use case và ánh xạ result thành response DTO. Application Service không cần biết response được trả bằng JSON, HTML hay một client khác.

## 7. Ranh giới transaction thuộc về ca sử dụng

Transaction xác định nhóm thao tác lưu trữ phải được commit hoặc rollback cùng nhau. Ranh giới này thường trùng với một use case hoặc một đơn vị công việc ứng dụng.

Ví dụ, khi đăng ký khóa học, việc tạo Registration và cập nhật số lượng chỗ đã dùng có thể cần cùng thành công. Nếu chỉ một thao tác được lưu, dữ liệu có thể không nhất quán.

Với Spring, có thể đặt @Transactional trên phương thức Application Service:

    @Transactional
    public RegisterForCourseResult execute(
            RegisterForCourseCommand command) {
        // tải aggregate, gọi domain, lưu thay đổi
    }

Điều này giúp Controller không phải quản lý transaction. Controller chỉ gọi use case; application layer quyết định phạm vi công việc.

### Chọn phạm vi transaction

Transaction nên bao trùm các thao tác persistence cần nhất quán. Transaction quá nhỏ có thể để lại trạng thái dở dang; transaction quá lớn có thể giữ khóa lâu, làm giảm thông lượng và tăng khả năng xung đột.

Tránh giữ transaction mở trong khi:

- Chờ người dùng nhập dữ liệu.
- Gửi email qua mạng.
- Gọi một API bên ngoài có thời gian phản hồi khó dự đoán.
- Chờ một tác vụ nền hoàn tất.
- Trả response và chờ client xử lý.

Hãy hoàn thành phần cập nhật dữ liệu cần thiết trong transaction, sau đó xử lý tác dụng phụ theo cơ chế phù hợp.

### Rollback và exception

Trong Spring, quy tắc rollback mặc định của @Transactional thường rollback với unchecked exception và Error; checked exception không tự động rollback nếu không cấu hình. Nếu use case dùng checked exception để biểu diễn lỗi cần rollback, cần khai báo rollbackFor hoặc chọn kiểu exception phù hợp.

Không bắt exception rồi nuốt nó bên trong transaction nếu thao tác đã thất bại. Khi exception bị xử lý và phương thức kết thúc bình thường, transaction có thể commit nếu không được đánh dấu rollback-only. Hãy định nghĩa rõ lỗi nào làm rollback và lỗi nào là kết quả nghiệp vụ dự kiến.

### Transaction không thay thế bất biến

Ràng buộc database như unique constraint, foreign key và check constraint vẫn quan trọng. Domain model bảo vệ quy tắc ở cấp đối tượng; transaction bảo đảm nhóm thay đổi có tính nguyên tử; database constraint bảo vệ dữ liệu ngay cả khi có nhiều tiến trình cùng truy cập.

## 8. Xử lý cạnh tranh và tính nhất quán

Nhiều request có thể thực hiện cùng một use case đồng thời. Ví dụ, chỉ còn một chỗ trong khóa học nhưng hai người học cùng đăng ký gần như cùng lúc.

Nếu hai transaction cùng đọc registeredCount = 9 với capacity = 10, cả hai có thể thấy còn chỗ và cùng tăng lên 10 hoặc ghi đè lẫn nhau tùy cách lưu. Quy tắc trong một entity được tải riêng không tự giải quyết race condition.

Một số cơ chế thường dùng:

- Optimistic locking với version column để phát hiện cập nhật xung đột.
- Pessimistic locking khi cần khóa bản ghi trong lúc xử lý.
- Atomic update hoặc câu lệnh có điều kiện ở database.
- Unique constraint để ngăn đăng ký trùng.
- Retry có giới hạn khi xung đột có thể giải quyết bằng thử lại.

Ví dụ entity JPA có thể dùng:

    @Version
    private long version;

Nếu hai transaction cập nhật cùng một phiên bản, một transaction có thể thất bại với optimistic locking exception. Application Service hoặc tầng xử lý lỗi có thể ánh xạ xung đột thành kết quả phù hợp, hoặc retry nếu thao tác an toàn và chính sách cho phép.

Không nên tự động retry mọi use case. Nếu lệnh có tác dụng phụ bên ngoài hoặc không idempotent, retry có thể tạo kết quả trùng lặp. Cần hiểu transaction đã commit đến đâu và thiết kế idempotency phù hợp.

## 9. Điều phối tác dụng phụ: email, message và sự kiện

Một use case có thể cần gửi email xác nhận, phát event hoặc gọi hệ thống khác. Đây là các tác dụng phụ (side effects), và thời điểm thực hiện rất quan trọng.

### Không gửi email trước khi dữ liệu commit

Nếu email được gửi trong khi transaction vẫn có thể rollback, người nhận có thể nhận xác nhận cho một đăng ký chưa được lưu. Gọi dịch vụ bên ngoài trong transaction cũng kéo dài thời gian giữ kết nối và khóa.

Một cách đơn giản là thực hiện sau khi transaction commit thông qua callback hoặc event listener phù hợp. Tuy nhiên, callback trong bộ nhớ có thể mất event nếu tiến trình dừng ngay sau commit nhưng trước khi gửi.

### Transactional Outbox

Khi cần độ tin cậy cao, có thể ghi một bản ghi outbox trong cùng transaction với thay đổi nghiệp vụ. Một worker đọc outbox rồi gửi message đến broker hoặc adapter bên ngoài.

    Application Service
          |
          | transaction
          v
      Database
       |     |
       |     +--> Outbox record
       |
       +--> Business data
                  |
                  | commit
                  v
             Outbox Worker
                  |
                  v
             Message Broker
                  |
          +-------+-------+
          |               |
          v               v
      Email Adapter   Analytics

Vì business data và outbox record được lưu cùng transaction, ứng dụng không tạo trạng thái “đã đăng ký nhưng không có event cần phát” chỉ vì process dừng giữa hai thao tác. Worker có thể gửi lại nếu gặp lỗi.

Outbox thường cung cấp giao nhận ít nhất một lần, nên consumer cần xử lý message trùng một cách idempotent. Cần theo dõi retry, dead-letter hoặc trạng thái lỗi để không làm mất thông báo âm thầm.

### Domain event và integration event

Domain event diễn đạt một điều có ý nghĩa trong miền, ví dụ RegistrationCompleted. Integration event là hợp đồng được công bố để hệ thống khác nhận. Hai loại có thể liên quan nhưng không nhất thiết giống nhau: integration event thường cần schema ổn định, versioning và tránh lộ cấu trúc domain nội bộ.

Application Service có thể thu thập domain event sau khi hành vi domain chạy, rồi chuyển chúng sang cơ chế phát sự kiện. Domain model không cần biết broker hoặc email provider cụ thể.

## 10. Idempotency cho các thao tác có thể gửi lại

HTTP client có thể gửi lại request do timeout, mất kết nối hoặc người dùng nhấn nút nhiều lần. Một use case tạo dữ liệu như thanh toán hoặc đăng ký cần xem xét việc xử lý lặp.

Idempotency có nghĩa thực hiện cùng một yêu cầu nhiều lần vẫn tạo ra hiệu ứng nghiệp vụ tương đương với một lần, theo hợp đồng đã định nghĩa.

Một số cách thực hiện:

- Client gửi idempotency key cho một thao tác tạo hoặc thanh toán.
- Server lưu key cùng kết quả xử lý trong một phạm vi người dùng/use case.
- Unique constraint ngăn tạo hai bản ghi trùng theo khóa nghiệp vụ.
- Khi nhận lại key đã xử lý, server trả lại kết quả đã lưu thay vì tạo tác dụng phụ lần nữa.

Không phải mọi thao tác đều cần idempotency key. PUT và DELETE có semantics idempotent theo HTTP, nhưng implementation vẫn cần bảo đảm hành vi phù hợp. POST thường không mặc nhiên idempotent, nên các thao tác quan trọng cần hợp đồng rõ về retry và duplicate request.

## 11. Xử lý lỗi ở application layer và ánh xạ ở Controller

Application Service nên diễn đạt lỗi của use case bằng exception hoặc result có ý nghĩa trong ứng dụng, không trả status HTTP trực tiếp.

Ví dụ các lỗi có thể gồm:

- CourseNotFoundException: khóa học không tồn tại.
- RegistrationClosedException: đợt đăng ký đã đóng.
- CourseFullException: không còn chỗ.
- DuplicateRegistrationException: người học đã đăng ký.
- AccessDeniedException hoặc một lỗi quyền chuyên biệt: actor không được phép thực hiện thao tác.

Controller hoặc exception advice ánh xạ chúng sang representation phù hợp:

| Lỗi ứng dụng | API thường trả | Giao diện HTML có thể xử lý |
|---|---|---|
| Không tìm thấy khóa học | 404 Not Found | Trang 404 hoặc thông báo không tìm thấy |
| Đăng ký đã đóng | 409 Conflict hoặc mã lỗi theo hợp đồng | Hiển thị lý do và trạng thái khóa học |
| Hết chỗ | 409 Conflict | Thông báo khóa học đã đủ người |
| Đăng ký trùng | 409 Conflict hoặc trả kết quả hiện có theo chính sách | Điều hướng đến đăng ký hiện tại |
| Không đủ quyền | 403 Forbidden hoặc 404 theo chính sách tiết lộ | Trang không có quyền hoặc trang đăng nhập |

Lỗi validation cấu trúc thường được xử lý tại ranh giới request trước khi use case được gọi. Lỗi nghiệp vụ chỉ xuất hiện sau khi application/domain kiểm tra trạng thái thực tế.

Không đưa stack trace, câu SQL hoặc thông tin nội bộ vào response. Có thể ghi log với correlation ID để hỗ trợ điều tra.

### Result type hay exception?

Nếu một kết quả là nhánh bình thường của use case, chẳng hạn “đã đăng ký trước đó” và API muốn trả lại đăng ký hiện có, có thể biểu diễn bằng result type. Nếu thao tác vi phạm điều kiện khiến mục tiêu không thể hoàn thành, exception chuyên biệt cũng có thể phù hợp.

Hãy chọn một quy ước nhất quán. Tránh dùng exception cho mọi nhánh điều khiển thông thường nếu result object làm ý định rõ ràng hơn; cũng tránh tạo một cấu trúc Result quá phức tạp cho một use case đơn giản.

## 12. Read use case và query service

Không phải mọi use case đều thay đổi dữ liệu. Các thao tác đọc như xem chi tiết đơn hàng, tìm kiếm khóa học hoặc xem lịch sử đăng ký cũng có thể được tổ chức thành query service.

Ví dụ:

    public record GetRegistrationDetailsQuery(
            UUID actorId,
            UUID registrationId) {
    }

    public record RegistrationDetailsResult(
            UUID id,
            String courseTitle,
            String status,
            Instant createdAt) {
    }

    @Service
    public class GetRegistrationDetails {
        private final RegistrationQueryRepository registrations;
        private final RegistrationAccessPolicy accessPolicy;

        public GetRegistrationDetails(
                RegistrationQueryRepository registrations,
                RegistrationAccessPolicy accessPolicy) {
            this.registrations = registrations;
            this.accessPolicy = accessPolicy;
        }

        @Transactional(readOnly = true)
        public RegistrationDetailsResult execute(
                GetRegistrationDetailsQuery query) {

            accessPolicy.checkCanView(
                    query.actorId(),
                    query.registrationId());

            return registrations.findDetails(query.registrationId())
                    .orElseThrow(RegistrationNotFoundException::new);
        }
    }

Query service có thể trả projection được tối ưu cho màn hình hoặc API. Nó không nhất thiết phải tải aggregate đầy đủ nếu chỉ cần một số trường để hiển thị.

### Command–Query Responsibility Segregation (CQRS)

Một số hệ thống tách mô hình ghi và mô hình đọc rõ ràng hơn. Đây là hướng tiếp cận CQRS: command model xử lý thay đổi trạng thái, query model tối ưu cho việc đọc. CQRS không bắt buộc với mọi ứng dụng MVC và không đồng nghĩa phải dùng hai database hoặc message broker.

Ở ứng dụng nhỏ, cùng một domain model và database có thể phục vụ cả đọc và ghi. Hãy chỉ tách mô hình khi nhu cầu truy vấn, hiệu năng hoặc mức độ phức tạp thực sự yêu cầu.

## 13. Application Service trong MVC và API

Một ca sử dụng có thể được gọi từ nhiều adapter:

- Controller server-side nhận form HTML.
- REST Controller nhận JSON.
- Consumer nhận message từ broker.
- Tác vụ nền chạy theo lịch.
- CLI hoặc công cụ quản trị nội bộ.

Tất cả có thể gọi cùng Application Service nếu semantics của use case giống nhau. Mỗi adapter chịu trách nhiệm chuyển dữ liệu đầu vào thành command và ánh xạ result thành hình thức phản hồi riêng.

    HTML Form Controller ----\
                              \
    REST API Controller -------> RegisterForCourse
                              /
    Message Consumer --------/

Use case không nên biết caller là trình duyệt, mobile app hay message consumer. Điều này giúp tái sử dụng hành vi ứng dụng mà không kéo phụ thuộc giao thức vào application layer.

Tuy nhiên, không nên ép mọi adapter dùng cùng DTO. Form object, request JSON và message schema có thể có cấu trúc, versioning và quy tắc tương thích khác nhau. Hãy chuyển chúng thành command nội bộ rõ ràng.

## 14. Kiểm thử Application Service

Vì Application Service không nên phụ thuộc HTTP hoặc template, có thể kiểm thử use case mà không cần khởi động web server.

### Unit test với fake hoặc mock port

Có thể dùng fake repository trong bộ nhớ hoặc mock để kiểm tra trình tự và kết quả. Ví dụ:

    @Test
    void registersStudentWhenCourseHasCapacity() {
        UUID studentId = UUID.randomUUID();
        UUID courseId = UUID.randomUUID();

        Course course = new Course(
                courseId,
                10,
                4,
                true);

        CourseRepository courses = new InMemoryCourseRepository(course);
        RegistrationRepository registrations =
                new InMemoryRegistrationRepository();

        RegisterForCourse useCase = new RegisterForCourse(
                courses,
                registrations,
                new AllowRegistrationAccess());

        RegisterForCourseResult result = useCase.execute(
                new RegisterForCourseCommand(studentId, courseId));

        assertEquals(RegistrationStatus.CONFIRMED, result.status());
        assertTrue(registrations.existsByCourseAndStudent(
                courseId,
                studentId));
    }

Đây là ví dụ minh họa; fake repository và policy cần được triển khai trong test. Test tập trung vào kết quả use case, không cần kiểm tra HTTP status hoặc nội dung HTML.

### Các trường hợp cần kiểm thử

| Tình huống | Điều cần xác nhận |
|---|---|
| Khóa học tồn tại và còn chỗ | Đăng ký được tạo và trạng thái được cập nhật |
| Khóa học không tồn tại | Trả lỗi không tìm thấy; không lưu đăng ký |
| Đăng ký đã đóng | Domain từ chối; không có thay đổi |
| Khóa học đã đầy | Domain từ chối; số chỗ không vượt capacity |
| Người học đã đăng ký | Không tạo bản ghi trùng |
| Actor không có quyền | Use case từ chối trước khi thay đổi dữ liệu |
| Lỗi khi lưu | Transaction rollback theo cấu hình |
| Request lặp với cùng idempotency key | Không tạo hiệu ứng nghiệp vụ trùng |
| Lỗi khi phát thông báo | Dữ liệu đã commit và outbox/retry xử lý theo chính sách |

### Integration test

Unit test không chứng minh transaction, ORM mapping, unique constraint hoặc locking hoạt động như dự kiến. Có thể bổ sung integration test với database phù hợp để kiểm tra:

- Transaction commit và rollback.
- Optimistic/pessimistic locking.
- Unique constraint chống đăng ký trùng.
- Outbox record được ghi cùng dữ liệu nghiệp vụ.
- Query projection trả dữ liệu đúng.
- Cấu hình Spring transaction manager thực tế.

### Controller test

Controller test xác nhận HTTP contract: request được bind đúng, use case được gọi, status/redirect/body phù hợp. Không cần lặp lại toàn bộ quy tắc nghiệp vụ trong Controller test.

Tách lớp kiểm thử giúp khi một test thất bại, nhóm phát triển xác định được vấn đề nằm ở use case, adapter web hay persistence.

## 15. Dấu hiệu Application Service đang được thiết kế sai

Hãy xem xét refactor khi:

- Controller trực tiếp gọi nhiều repository và tự phối hợp transaction.
- Application Service chứa phép tính và quy tắc nghiệp vụ đáng lẽ thuộc domain.
- Domain model chỉ có getter/setter còn mọi quyết định nằm trong service.
- Một service duy nhất chứa các use case không liên quan.
- Application Service trả ResponseEntity, tên template hoặc kiểu HTTP.
- Use case nhận HttpServletRequest, HttpSession hoặc đối tượng framework web.
- Transaction kéo dài qua lời gọi mạng hoặc thao tác chờ lâu.
- Email được gửi trước khi dữ liệu commit.
- Một thao tác quan trọng có thể bị thực hiện lặp mà không có chính sách idempotency.
- Unit test cần khởi động database và web server cho mọi trường hợp.

Một quy trình refactor:

1. Ghi lại mục tiêu và các bước của use case.
2. Tách dữ liệu đầu vào thành command/query.
3. Chuyển quy tắc nghiệp vụ về entity, value object hoặc domain service.
4. Định nghĩa repository/gateway port theo nhu cầu của use case.
5. Đặt transaction quanh phần thay đổi dữ liệu cần nhất quán.
6. Chuyển tác dụng phụ sang cơ chế sau commit hoặc outbox nếu cần độ tin cậy.
7. Trả result nội bộ, để Controller ánh xạ thành HTTP hoặc View.
8. Viết unit test cho use case và integration test cho transaction/persistence.

Không đánh giá Application Service chỉ bằng số dòng hoặc số dependency. Hãy xem nó có diễn đạt được một mục tiêu ứng dụng rõ ràng và điều phối các bước đúng ranh giới hay không.

## 16. Checklist khi thiết kế một Application Service

Trước khi hoàn tất một use case, hãy kiểm tra:

- Tên lớp/phương thức diễn đạt một hành động ứng dụng cụ thể.
- Input command/query chỉ chứa dữ liệu cần thiết.
- Actor identity lấy từ ngữ cảnh đã xác thực.
- Quy tắc nghiệp vụ được thực thi bởi domain model hoặc domain service.
- Repository được gọi qua hợp đồng phù hợp.
- Transaction bao trùm đúng các thay đổi cần nguyên tử.
- Tác dụng phụ không làm transaction kéo dài hoặc gửi thông báo trước commit.
- Có chính sách concurrency và idempotency phù hợp với rủi ro thao tác.
- Lỗi ứng dụng không phụ thuộc status HTTP.
- Result không phụ thuộc View template hoặc response framework.
- Có unit test cho use case và integration test cho các hành vi persistence quan trọng.

## Kết luận

Application Service điều phối một ca sử dụng: nó nhận command hoặc query, tải dữ liệu cần thiết, phối hợp quyền truy cập, gọi hành vi domain, quản lý ranh giới transaction và trả kết quả cho caller. Trong MVC, Controller chuyển request thành lời gọi use case; View hoặc API adapter chuyển kết quả thành representation phù hợp.

Application Service không thay thế Domain Model, Repository hay Controller. Nó kết nối các thành phần đó theo một trình tự có ý nghĩa. Khi ranh giới được giữ rõ, quy tắc nghiệp vụ có một nơi sở hữu, transaction có phạm vi dễ hiểu, tác dụng phụ được kiểm soát và use case có thể kiểm thử độc lập với giao diện web.
