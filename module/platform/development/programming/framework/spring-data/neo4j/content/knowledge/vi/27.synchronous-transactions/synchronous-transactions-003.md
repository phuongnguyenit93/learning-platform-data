# Đặt @Transactional ở tầng dịch vụ

Một nghiệp vụ trong ứng dụng Spring Data Neo4j thường gồm nhiều thao tác dữ liệu: đọc node liên quan, kiểm tra điều kiện, tạo node mới, nối relationship và ghi lịch sử. Nếu mỗi thao tác tự chạy trong transaction riêng, ứng dụng có thể để lại đồ thị ở trạng thái dở dang khi một bước sau thất bại.

Đặt `@Transactional` ở tầng service giúp xác định ranh giới của một nghiệp vụ hoàn chỉnh. Các repository, `Neo4jTemplate` và `Neo4jClient` được gọi bên trong phương thức đó có thể tham gia cùng transaction Spring, miễn là chúng dùng cùng cấu hình transaction manager của Neo4j. Nhờ vậy, mọi thay đổi trong phạm vi nghiệp vụ được commit cùng nhau hoặc rollback cùng nhau.

## 1. Vì sao transaction nên nằm ở tầng service?

Repository thường đại diện cho thao tác trên một aggregate hoặc một loại entity. Một nghiệp vụ thực tế có thể cần phối hợp nhiều repository và nhiều loại thao tác.

Ví dụ đăng ký sinh viên vào khóa học cần:

1. Đọc `Student` và `Course`.
2. Kiểm tra sinh viên và khóa học tồn tại.
3. Kiểm tra khóa học đang nhận đăng ký.
4. Tạo node `Enrollment` nối với sinh viên và khóa học.
5. Tạo node lịch sử `EnrollmentAudit` ghi nhận sự kiện đăng ký.

Nếu bước 4 thành công nhưng bước 5 thất bại, dữ liệu đăng ký có thể tồn tại mà không có lịch sử tương ứng. Đây là trạng thái nghiệp vụ không mong muốn.

Khi đặt transaction ở service, toàn bộ các thao tác trên thuộc một đơn vị công việc. Service là nơi hiểu nghiệp vụ nào cần thành công cùng nhau, vì vậy đây thường là vị trí phù hợp để xác định transaction boundary.

Repository vẫn có thể khai báo transaction cho thao tác riêng lẻ. Tuy nhiên, transaction ở service thể hiện rõ ranh giới của nghiệp vụ phối hợp nhiều thao tác, thay vì để mỗi lời gọi repository tự quyết định thời điểm commit.

## 2. Spring Data Neo4j tham gia transaction như thế nào?

Spring Data Neo4j tích hợp transaction với Spring thông qua `Neo4jTransactionManager`. Trong ứng dụng Spring Boot sử dụng starter và cấu hình Driver chuẩn, transaction manager thường được auto-configure. Nếu tự cấu hình hạ tầng Neo4j, cần đăng ký transaction manager sử dụng cùng `Driver` và database selection mà các bean SDN đang dùng.

Khi một phương thức service được gọi qua Spring proxy và có `@Transactional`:

1. Transaction interceptor yêu cầu transaction manager bắt đầu hoặc tham gia transaction.
2. `Neo4jTransactionManager` mở transaction Neo4j và gắn session/transaction resource vào ngữ cảnh hiện tại.
3. Repository, `Neo4jTemplate` và `Neo4jClient` sử dụng transaction resource đang được quản lý.
4. Khi phương thức hoàn tất bình thường, Spring yêu cầu commit.
5. Khi có exception kích hoạt rollback, Spring yêu cầu rollback transaction.

Các thao tác phải dùng cùng transaction manager để tham gia chung một transaction. Không nên tự mở một session và transaction độc lập bằng Neo4j Java Driver rồi giả định nó tự tham gia transaction do Spring quản lý.

## 3. Ví dụ mô hình đăng ký khóa học

Giả sử đồ thị có các node `Student`, `Course`, `Enrollment` và `EnrollmentAudit`:

```text
(Enrollment)-[:FOR_STUDENT]->(Student)
(Enrollment)-[:FOR_COURSE]->(Course)
(EnrollmentAudit)-[:ABOUT]->(Enrollment)
```

`Enrollment` là node nghiệp vụ biểu diễn lần đăng ký. `EnrollmentAudit` lưu dấu vết tạo đăng ký. Cả hai node đều có thể được lưu trong cùng một transaction.

Ví dụ entity rút gọn:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Enrollment")
public class Enrollment {

    @Id
    private String enrollmentId;

    private String status;
    private ZonedDateTime registeredAt;

    @Relationship(type = "FOR_STUDENT", direction = Relationship.Direction.OUTGOING)
    private Student student;

    @Relationship(type = "FOR_COURSE", direction = Relationship.Direction.OUTGOING)
    private Course course;

    // Constructor, getters and domain methods
}
```

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("EnrollmentAudit")
public class EnrollmentAudit {

    @Id
    private String auditId;

    private String action;
    private ZonedDateTime occurredAt;

    @Relationship(type = "ABOUT", direction = Relationship.Direction.OUTGOING)
    private Enrollment enrollment;

    // Constructor and getters
}
```

`Student` và `Course` là các entity đã được ánh xạ riêng. Ví dụ `Course` có phương thức `isEnrollmentOpen()` để kiểm tra trạng thái nhận đăng ký.

## 4. Đặt @Transactional trên phương thức service

Service thực hiện toàn bộ nghiệp vụ trong một transaction:

```java
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EnrollmentService {

    private final StudentRepository studentRepository;
    private final CourseRepository courseRepository;
    private final EnrollmentRepository enrollmentRepository;
    private final EnrollmentAuditRepository auditRepository;

    public EnrollmentService(
            StudentRepository studentRepository,
            CourseRepository courseRepository,
            EnrollmentRepository enrollmentRepository,
            EnrollmentAuditRepository auditRepository) {
        this.studentRepository = studentRepository;
        this.courseRepository = courseRepository;
        this.enrollmentRepository = enrollmentRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Enrollment register(String studentId, String courseCode) {
        Student student = studentRepository.findById(studentId)
            .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy sinh viên"));

        Course course = courseRepository.findById(courseCode)
            .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy khóa học"));

        if (!course.isEnrollmentOpen()) {
            throw new IllegalStateException("Khóa học không nhận đăng ký");
        }

        ZonedDateTime now = ZonedDateTime.now(ZoneOffset.UTC);
        Enrollment enrollment = new Enrollment(
            UUID.randomUUID().toString(),
            "REGISTERED",
            now,
            student,
            course
        );

        Enrollment saved = enrollmentRepository.save(enrollment);

        EnrollmentAudit audit = new EnrollmentAudit(
            UUID.randomUUID().toString(),
            "ENROLLMENT_CREATED",
            now,
            saved
        );
        auditRepository.save(audit);

        return saved;
    }
}
```

`@Transactional` bao quanh lời gọi `register`. Hai lần `save` và các thao tác đọc trước đó tham gia transaction hiện tại. Nếu `auditRepository.save(audit)` phát sinh runtime exception và exception thoát khỏi phương thức, transaction rollback; node `Enrollment` vừa tạo cũng không được commit riêng lẻ.

Nếu bỏ `@Transactional` ở service, các phương thức repository vẫn có thể tự tạo transaction cho từng lần gọi. Khi đó, lần lưu `Enrollment` có thể commit trước khi lần lưu audit bắt đầu. Nếu audit thất bại, đăng ký vẫn có thể tồn tại. Đây là lý do transaction boundary của nghiệp vụ nhiều bước nên được đặt ở service.

## 5. Gọi Repository, Neo4jTemplate và Neo4jClient trong cùng transaction

Một service có thể phối hợp nhiều API SDN trong cùng phương thức:

```java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.data.neo4j.core.Neo4jTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CourseAdministrationService {

    private final CourseRepository courseRepository;
    private final Neo4jTemplate neo4jTemplate;
    private final Neo4jClient neo4jClient;

    public CourseAdministrationService(
            CourseRepository courseRepository,
            Neo4jTemplate neo4jTemplate,
            Neo4jClient neo4jClient) {
        this.courseRepository = courseRepository;
        this.neo4jTemplate = neo4jTemplate;
        this.neo4jClient = neo4jClient;
    }

    @Transactional
    public void closeCourse(String courseCode) {
        Course course = courseRepository.findById(courseCode)
            .orElseThrow();

        course.closeEnrollment();
        courseRepository.save(course);

        neo4jTemplate.save(CourseChange.closed(courseCode));

        neo4jClient.query("""
            MATCH (c:Course {courseCode: $courseCode})
            SET c.lastStatusCheck = datetime()
            """)
            .bind(courseCode).to("courseCode")
            .run();
    }
}
```

Đây là minh họa về việc các API cùng tham gia một transaction Spring; `CourseChange` là entity lịch sử giả định của ứng dụng. Điều kiện quan trọng là repository, template và client được tạo từ cùng cấu hình Spring Data Neo4j và cùng transaction manager. Không tự tạo một `Driver` khác hoặc mở transaction Driver độc lập trong một bước rồi mong transaction service điều khiển nó.

Tham số của `Neo4jClient` cần được bind riêng bằng `.bind(...).to(...)`. Dùng parameter giúp dữ liệu đầu vào không bị diễn giải thành cú pháp Cypher.

## 6. @Transactional ở cấp class và cấp method

Có thể đặt annotation ở cấp class:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class CourseQueryService {

    public Optional<Course> findCourse(String courseCode) {
        return courseRepository.findById(courseCode);
    }
}
```

Khi đặt ở class, các phương thức được áp dụng transaction theo cấu hình đó. Nếu một phương thức cần ghi, có thể ghi đè ở cấp method:

```java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public Course updateCourse(Course course) {
    return courseRepository.save(course);
}
```

Annotation ở method cụ thể có độ ưu tiên cao hơn metadata ở class. Cách tổ chức phổ biến là đặt `@Transactional(readOnly = true)` ở service chuyên đọc, còn các phương thức ghi đặt `@Transactional` riêng. Với service hỗn hợp đọc và ghi, có thể khai báo rõ từng phương thức để người đọc dễ nhận biết transaction mode.

Không nên gắn `readOnly = true` lên toàn bộ service rồi quên ghi đè cho phương thức cập nhật. `readOnly` là metadata/hint cho transaction manager và cơ chế truy cập dữ liệu; nó không phải một lớp phân quyền bảo mật thay thế quyền Neo4j.

## 7. Đọc dữ liệu với readOnly = true

Với thao tác chỉ đọc, có thể dùng:

```java
import org.springframework.transaction.annotation.Transactional;

@Transactional(readOnly = true)
public Optional<Enrollment> findEnrollment(String enrollmentId) {
    return enrollmentRepository.findById(enrollmentId);
}
```

`readOnly = true` thể hiện rõ ý định của phương thức và cho phép transaction manager tối ưu hoặc định tuyến truy vấn đọc tùy cấu hình hạ tầng Neo4j. Trong môi trường cluster có primary/secondary, routing có thể sử dụng metadata read-only để chọn nơi thực hiện truy vấn đọc.

Không xem `readOnly = true` là bảo đảm rằng mọi câu lệnh ghi sẽ bị chặn như một quyền database. Hãy thiết kế service chỉ đọc không gọi thao tác ghi và cấu hình quyền Neo4j phù hợp với yêu cầu bảo mật.

## 8. Cách Spring proxy kích hoạt transaction

Spring thường áp dụng `@Transactional` thông qua AOP proxy. Khi một bean khác gọi phương thức được quản lý, proxy mở transaction trước khi chuyển quyền điều khiển vào phương thức và hoàn tất transaction khi phương thức kết thúc.

Vì vậy, cần chú ý:

- Đặt annotation trên phương thức service được gọi qua Spring-managed bean.
- Tránh gọi một phương thức transactional khác bằng `this.method()` trong cùng class nếu kỳ vọng tạo transaction boundary mới; self-invocation không đi qua proxy.
- Tránh gọi trực tiếp constructor để tạo service bằng `new`; object tự tạo không có transaction proxy.
- Giữ transaction method ở phạm vi public và gọi từ bên ngoài bean để hành vi nhất quán với proxy mặc định.
- Không đặt annotation trên private method với kỳ vọng Spring proxy sẽ chặn lời gọi đó.

Ví dụ dễ gây hiểu nhầm:

```java
@Service
public class EnrollmentService {

    public void process(String studentId) {
        registerInternal(studentId); // self-invocation
    }

    @Transactional
    public void registerInternal(String studentId) {
        // Các thao tác ghi dữ liệu
    }
}
```

Lời gọi `registerInternal` từ `process` đi trực tiếp trong cùng instance, không qua proxy. Hãy chuyển nghiệp vụ transactional sang một service bean khác hoặc đặt transaction ở phương thức public bên ngoài được gọi trực tiếp từ bean khác.

## 9. Propagation: tham gia transaction hiện tại

`Propagation` xác định cách một phương thức transactional tương tác với transaction đang tồn tại. Với nghiệp vụ thông thường, `REQUIRED` là lựa chọn phù hợp và cũng là mặc định:

```java
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(propagation = Propagation.REQUIRED)
public Enrollment register(...) {
    // Nghiệp vụ đăng ký
}
```

Hành vi của `REQUIRED`:

- Nếu chưa có transaction, Spring bắt đầu transaction mới.
- Nếu đã có transaction, phương thức tham gia transaction đó.
- Nếu transaction chung rollback, các thao tác trong phương thức cũng rollback.

Ví dụ controller gọi `EnrollmentService.register`, sau đó service gọi `AuditService.record`. Nếu cả hai dùng `REQUIRED` và cùng transaction manager, thao tác audit tham gia transaction đăng ký hiện tại.

`REQUIRES_NEW` yêu cầu một transaction độc lập. Nếu dùng, cần hiểu rằng transaction bên trong có thể commit ngay cả khi transaction bên ngoài rollback. Đây thường không phải điều mong muốn đối với các bước phải nguyên tử cùng nghiệp vụ. Chỉ dùng khi dữ liệu bên trong được phép tồn tại độc lập và transaction manager được cấu hình hỗ trợ hành vi đó.

Không mặc định dùng `NESTED` như savepoint của SQL. Khả năng transaction lồng nhau phụ thuộc transaction manager và cơ chế Neo4j; hãy kiểm tra hỗ trợ của phiên bản đang dùng trước khi thiết kế dựa vào nested transaction.

## 10. Quy tắc rollback mặc định

Theo quy tắc mặc định của Spring:

- `RuntimeException` và `Error` làm transaction rollback.
- Checked exception không tự động làm rollback nếu không cấu hình thêm.

Nếu nghiệp vụ có checked exception và muốn rollback, khai báo `rollbackFor`:

```java
import org.springframework.transaction.annotation.Transactional;

@Transactional(rollbackFor = IOException.class)
public void importCourse(InputStream input) throws IOException {
    // Đọc dữ liệu và ghi nhiều entity
}
```

Có thể chỉ định nhiều loại exception trong `rollbackFor`. Nếu chỉ muốn loại trừ một exception khỏi rollback, Spring có `noRollbackFor`; chỉ sử dụng khi đã xác định rõ trạng thái dữ liệu sau exception đó.

Không nên bắt exception rồi bỏ qua:

```java
@Transactional
public void register(...) {
    enrollmentRepository.save(...);

    try {
        auditRepository.save(...);
    } catch (DataAccessException ex) {
        log.error("Không ghi được audit", ex);
        // Nuốt exception: transaction có thể vẫn commit
    }
}
```

Nếu exception bị bắt và không được ném tiếp, interceptor có thể coi phương thức hoàn tất bình thường và commit. Nếu lỗi khiến nghiệp vụ không thể hoàn tất, hãy ném exception phù hợp để rollback hoặc đánh dấu transaction rollback-only bằng cơ chế Spring.

## 11. Giữ transaction ngắn và tránh công việc bên ngoài

Transaction nên bao quanh các thao tác cần tính nguyên tử trong Neo4j. Không nên giữ transaction mở trong lúc gọi HTTP, chờ người dùng, gửi email hoặc xử lý tệp lớn.

Ví dụ, nếu đăng ký khóa học cần gửi email xác nhận, không nên gọi mail server trước khi transaction Neo4j kết thúc. Có thể:

1. Ghi `Enrollment` và một bản ghi outbox trong cùng transaction.
2. Commit transaction.
3. Một worker đọc outbox và gửi email sau đó.
4. Đánh dấu sự kiện đã gửi hoặc retry khi cần.

Neo4j transaction chỉ đảm bảo tính nguyên tử cho các thao tác nằm trong transaction Neo4j đó. Nó không tự tạo transaction phân tán bao trùm HTTP service, email provider, Kafka hoặc một database độc lập. Với nhiều hệ thống, cần thiết kế outbox, saga hoặc cơ chế bù trừ phù hợp.

Giữ transaction ngắn cũng giảm thời gian giữ lock và giúp hệ thống xử lý đồng thời tốt hơn.

## 12. Transaction không thay thế kiểm soát đồng thời

Transaction đảm bảo nhóm thao tác commit hoặc rollback theo ranh giới đã định, nhưng không tự giải quyết mọi race condition nghiệp vụ.

Ví dụ, hai request cùng đọc một khóa học còn chỗ, sau đó cả hai đều đăng ký. Nếu chỉ kiểm tra số chỗ trong Java rồi ghi, cả hai request có thể cùng vượt qua điều kiện nếu không có cơ chế phối hợp phù hợp.

Các lựa chọn kiểm soát đồng thời gồm:

- Cập nhật có điều kiện bằng Cypher để điều kiện và thay đổi được thực hiện trong cùng thao tác database.
- Dùng optimistic locking với `@Version` trên entity khi mô hình cập nhật qua Spring Data mapping phù hợp.
- Thiết kế uniqueness constraint cho định danh nghiệp vụ, ví dụ không cho một sinh viên đăng ký trùng cùng một khóa học theo quy tắc hệ thống.
- Dùng transaction và locking phù hợp với loại dữ liệu, sau đó xử lý xung đột/retry có giới hạn.

Ví dụ khai báo version field:

```java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Course")
public class Course {

    @Id
    private String courseCode;

    @Version
    private Long version;

    private boolean enrollmentOpen;
}
```

`@Version` hỗ trợ phát hiện cập nhật cạnh tranh qua cơ chế mapping của Spring Data Neo4j. Các câu Cypher ghi trực tiếp bên ngoài cơ chế version không tự động cập nhật hoặc kiểm tra version này; cần thiết kế riêng nếu có nhiều luồng ghi khác nhau.

## 13. Giao dịch đồng bộ và luồng reactive

Bài học này sử dụng `Neo4jRepository`, `Neo4jTemplate` và `Neo4jClient` imperative. Với mô hình đồng bộ, transaction được Spring quản lý gắn với luồng thực thi hiện tại. Không nên chuyển một phần công việc sang thread khác bằng `@Async`, executor hoặc callback bất đồng bộ rồi kỳ vọng transaction imperative tự truyền sang thread đó.

Nếu ứng dụng dùng reactive stack, hãy sử dụng `ReactiveNeo4jRepository`, `ReactiveNeo4jTemplate`, reactive transaction manager và Reactor transaction context. Không gọi API imperative blocking bên trong reactive pipeline để thay thế transaction reactive.

## 14. Kiểm thử transaction ở tầng service

Kiểm thử cần xác nhận tính nguyên tử của toàn bộ nghiệp vụ, không chỉ xác nhận từng repository method hoạt động riêng.

Một integration test cho đăng ký khóa học có thể thực hiện:

1. Chuẩn bị một `Student` và một `Course` đang mở đăng ký.
2. Gọi `EnrollmentService.register`.
3. Xác nhận node `Enrollment`, hai relationship và node `EnrollmentAudit` đã được lưu.
4. Tạo tình huống để thao tác lưu audit thất bại sau khi enrollment đã được lưu.
5. Gọi service và xác nhận exception được ném ra.
6. Đọc lại database và xác nhận cả `Enrollment` lẫn audit chưa được commit.
7. Kiểm tra trường hợp course đóng đăng ký; không có enrollment nào được tạo.

Test rollback nên đọc lại dữ liệu bằng transaction mới hoặc sau khi transaction test kết thúc để tránh chỉ kiểm tra trạng thái trong persistence context hiện tại. Nếu test framework tự bọc test trong transaction, hãy chú ý ranh giới transaction của test và transaction của service.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Lưu bước đầu thành công nhưng bước sau lỗi vẫn còn dữ liệu | Mỗi repository call đã commit riêng vì service không có transaction chung | Đặt `@Transactional` ở service method điều phối nghiệp vụ. |
| `@Transactional` không có tác dụng | Gọi qua self-invocation hoặc tự tạo object bằng `new` | Gọi qua Spring-managed proxy và giữ phương thức transactional ở public boundary. |
| Exception xảy ra nhưng dữ liệu vẫn commit | Exception checked hoặc bị catch rồi nuốt | Dùng `rollbackFor` khi cần hoặc ném lại exception; đánh dấu rollback-only nếu phù hợp. |
| Repository và Neo4jClient không rollback cùng nhau | Client/Driver dùng cấu hình hoặc transaction độc lập | Dùng bean `Neo4jClient` của Spring và cùng transaction manager. |
| `readOnly` method vẫn có thể gọi lệnh ghi | Nhầm read-only hint với quyền bảo mật | Không gọi write path trong method chỉ đọc và cấu hình quyền database. |
| Dữ liệu bị ghi đè khi có hai request đồng thời | Transaction không thay thế optimistic locking hoặc kiểm tra điều kiện | Dùng `@Version`, constraint hoặc cập nhật có điều kiện. |
| Transaction mất khi chạy tác vụ async | Transaction imperative gắn với thread hiện tại | Không chuyển việc sang thread khác trong transaction; dùng outbox hoặc reactive transaction phù hợp. |
| Transaction giữ quá lâu | Gọi API bên ngoài hoặc xử lý nặng bên trong transaction | Thu hẹp transaction vào phần đọc/ghi Neo4j cần nguyên tử. |

## 16. Quy trình đặt transaction ở tầng service

1. Xác định một nghiệp vụ hoàn chỉnh và các thay đổi Neo4j phải thành công cùng nhau.
2. Đặt `@Transactional` trên public service method được gọi qua Spring proxy.
3. Đảm bảo repository, `Neo4jTemplate` và `Neo4jClient` dùng cùng transaction manager.
4. Dùng `REQUIRED` mặc định để các service được gọi bên trong tham gia transaction hiện tại.
5. Chọn `readOnly = true` cho luồng đọc; dùng transaction read-write cho nghiệp vụ ghi.
6. Xác định quy tắc rollback, đặc biệt với checked exception và exception bị catch.
7. Giữ transaction ngắn; chuyển email, HTTP hoặc công việc bất đồng bộ sang bước sau commit.
8. Bổ sung kiểm soát đồng thời nếu nghiệp vụ có nguy cơ race condition.
9. Viết integration test chứng minh dữ liệu được commit cùng nhau hoặc rollback cùng nhau.

## 17. Ghi nhớ

Đặt `@Transactional` ở tầng service giúp gom nhiều thao tác repository, `Neo4jTemplate` và `Neo4jClient` thành một đơn vị nghiệp vụ. Spring transaction manager điều phối transaction Neo4j; các thao tác dùng cùng transaction manager sẽ tham gia transaction hiện tại. Khi phương thức hoàn tất bình thường, thay đổi được commit; khi exception kích hoạt rollback, toàn bộ thay đổi trong transaction được rollback.

Hãy chú ý Spring proxy, self-invocation, propagation và quy tắc rollback mặc định. `readOnly = true` thể hiện ý định đọc, không phải quyền bảo mật; transaction cũng không tự giải quyết race condition hoặc giao dịch với hệ thống bên ngoài. Giữ transaction ngắn, dùng cơ chế kiểm soát đồng thời khi cần và kiểm thử rollback ở cấp service để bảo đảm đồ thị luôn phản ánh một nghiệp vụ hoàn chỉnh.
