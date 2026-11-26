# Phân biệt hướng gọi khi chạy với hướng phụ thuộc trong mã nguồn

Bài học này thuộc module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED** — **Học tổ chức phần mềm theo kiến trúc phân tầng**, trong chương **Ranh giới và quy tắc phân tầng**. Khi đọc một hệ thống phân tầng, cần trả lời riêng hai câu hỏi: lúc chương trình chạy, thành phần nào gọi thành phần nào; và để biên dịch, mã nguồn của thành phần nào cần biết đến kiểu hoặc module nào. Hai hướng này có liên quan nhưng không nhất thiết trùng nhau.

## 1. Hai loại hướng cần phân biệt

**Hướng gọi khi chạy (runtime call direction)** mô tả luồng điều khiển giữa các đối tượng hoặc thành phần trong một tình huống cụ thể. Mũi tên đi từ bên khởi tạo lời gọi đến bên nhận lời gọi. Có thể quan sát hướng này qua call stack, breakpoint, trace hoặc sequence diagram.

**Hướng phụ thuộc trong mã nguồn (source-code dependency direction)** mô tả quan hệ cần thiết để mã nguồn được biên dịch và liên kết. Một lớp phụ thuộc vào kiểu mà nó khai báo trong import, kiểu của field, tham số, kiểu trả về, lớp cha, interface được triển khai hoặc API mà nó sử dụng. Mũi tên phụ thuộc đi từ mã nguồn cần một kiểu sang nơi định nghĩa kiểu đó. Có thể quan sát hướng này qua package import, cấu trúc module, khai báo lớp và cấu hình build.

| Góc nhìn | Hướng gọi khi chạy | Hướng phụ thuộc mã nguồn |
|---|---|---|
| Câu hỏi | Ai gọi ai trong một lần xử lý? | Mã nguồn nào cần biết kiểu/API nào để biên dịch? |
| Bằng chứng | Call stack, trace, breakpoint, sequence diagram | Import, field, tham số, implements, module dependency |
| Mũi tên | Caller → callee | Bên sử dụng kiểu → nơi định nghĩa kiểu |
| Thời điểm | Khi một luồng thực thi cụ thể diễn ra | Khi biên dịch, kiểm tra kiểu hoặc xây dựng module |

Ví dụ, một service có thể gọi một phương thức qua interface **DonHangRepository**. Khi chạy, đối tượng nhận lời gọi có thể là **JpaDonHangRepository**. Nhưng mã nguồn của service chỉ cần phụ thuộc vào interface **DonHangRepository**; nó không cần import lớp triển khai JPA. Đây là điểm mấu chốt khiến hai đồ thị có thể chỉ theo hai hướng khác nhau tại một ranh giới.

## 2. Ví dụ luồng tạo đơn hàng trong Spring

Giả sử ứng dụng nhận yêu cầu HTTP tạo đơn hàng, áp dụng quy tắc nghiệp vụ rồi lưu đơn hàng vào cơ sở dữ liệu. Một cách chia trách nhiệm có thể gồm:

- **Presentation:** **DonHangController** tiếp nhận HTTP request, chuyển dữ liệu đầu vào thành command và định dạng HTTP response.
- **Application:** **TaoDonHangUseCase** mô tả thao tác mà ứng dụng cung cấp; **TaoDonHangService** điều phối ca sử dụng.
- **Domain:** **DonHang** giữ trạng thái và các quy tắc nghiệp vụ của đơn hàng.
- **Data access / Infrastructure:** **DonHangRepository** là hợp đồng lưu trữ mà application cần; **JpaDonHangRepository** chuyển hợp đồng đó thành thao tác JPA cụ thể.

Đây là cách tổ chức minh họa, không phải quy định rằng mọi hệ thống phải có đúng bốn layer hoặc phải dùng DDD. Một ứng dụng nhỏ có thể gộp một số trách nhiệm; điều quan trọng là các ranh giới và quy tắc phụ thuộc được xác định rõ.

### Hướng gọi khi chương trình chạy

Trong ví dụ này, Spring inject implementation vào các constructor. Khi có request, luồng gọi chính diễn ra như sau:

~~~mermaid
sequenceDiagram
    participant Client as HTTP Client
    participant Controller as DonHangController
    participant Service as TaoDonHangService
    participant Adapter as JpaDonHangRepository
    participant JPA as Spring Data JPA
    participant DB as Database

    Client->>Controller: POST /don-hang
    Controller->>Service: tao(command)
    Note over Controller,Service: Lời gọi được khai báo qua TaoDonHangUseCase
    Service->>Adapter: save(donHang)
    Note over Service,Adapter: Lời gọi được khai báo qua DonHangRepository
    Adapter->>JPA: save(entity)
    JPA->>DB: INSERT / UPDATE
    DB-->>JPA: Kết quả lưu
    JPA-->>Adapter: Entity đã lưu
    Adapter-->>Service: Hoàn tất
    Service-->>Controller: DonHangId
    Controller-->>Client: HTTP 201 Created
~~~

Mũi tên từ application đến persistence trong sơ đồ là hướng gọi tại thời điểm chạy. Service gọi phương thức trên tham chiếu repository mà nó nhận được. Đối tượng thực tế phía sau tham chiếu đó là **JpaDonHangRepository**, vì Spring đã chọn và inject bean tương ứng. Kết quả trả về đi ngược lại qua các lời gọi.

### Hướng phụ thuộc trong mã nguồn

Các hợp đồng được đặt ở phía cần sử dụng chúng. Ví dụ rút gọn:

~~~java
// application/TaoDonHangUseCase.java
public interface TaoDonHangUseCase {
    DonHangId tao(TaoDonHangCommand command);
}
~~~

~~~java
// application/DonHangRepository.java
public interface DonHangRepository {
    void save(DonHang donHang);
}
~~~

Service phụ thuộc vào các hợp đồng mà application cần:

~~~java
// application/TaoDonHangService.java
@Service
public class TaoDonHangService implements TaoDonHangUseCase {
    private final DonHangRepository repository;

    public TaoDonHangService(DonHangRepository repository) {
        this.repository = repository;
    }

    @Override
    @Transactional
    public DonHangId tao(TaoDonHangCommand command) {
        DonHang donHang = DonHang.tao(command);
        repository.save(donHang);
        return donHang.id();
    }
}
~~~

Adapter ở infrastructure triển khai hợp đồng và sử dụng công nghệ lưu trữ:

~~~java
// infrastructure/persistence/JpaDonHangRepository.java
@Repository
public class JpaDonHangRepository implements DonHangRepository {
    private final SpringDataDonHangJpaRepository jpa;

    public JpaDonHangRepository(SpringDataDonHangJpaRepository jpa) {
        this.jpa = jpa;
    }

    @Override
    public void save(DonHang donHang) {
        jpa.save(DonHangEntity.from(donHang));
    }
}
~~~

Controller cũng phụ thuộc vào hợp đồng application:

~~~java
// presentation/web/DonHangController.java
@RestController
public class DonHangController {
    private final TaoDonHangUseCase useCase;

    public DonHangController(TaoDonHangUseCase useCase) {
        this.useCase = useCase;
    }

    @PostMapping("/don-hang")
    public ResponseEntity<Void> tao(@RequestBody TaoDonHangRequest request) {
        DonHangId id = useCase.tao(request.toCommand());
        URI location = URI.create("/don-hang/" + id.value());
        return ResponseEntity.created(location).build();
    }
}
~~~

Từ các khai báo trên, hướng phụ thuộc mã nguồn có thể biểu diễn như sau:

~~~mermaid
flowchart TD
    C[DonHangController] -->|uses| U[TaoDonHangUseCase]
    S[TaoDonHangService] -->|implements| U
    S -->|uses| R[DonHangRepository]
    A[JpaDonHangRepository] -->|implements| R
    A -->|uses| J[SpringDataDonHangJpaRepository]
~~~

Đọc các mũi tên trong sơ đồ này theo nghĩa: lớp ở đầu mũi tên cần biết hợp đồng hoặc API ở cuối mũi tên. Vì **JpaDonHangRepository** khai báo **implements DonHangRepository**, mã nguồn adapter phải biết interface **DonHangRepository**. Chiều phụ thuộc biên dịch do đó đi từ adapter về interface. Interface không cần import hay biết tên lớp JPA cụ thể.

Hai sơ đồ mô tả hai điều khác nhau:

- **Khi chạy:** **TaoDonHangService** gọi đối tượng **JpaDonHangRepository** thông qua tham chiếu kiểu **DonHangRepository**.
- **Trong mã nguồn:** **TaoDonHangService** phụ thuộc vào **DonHangRepository**; **JpaDonHangRepository** cũng phụ thuộc vào **DonHangRepository** để triển khai hợp đồng đó.

Interface không tự thực hiện việc lưu dữ liệu. Nó chỉ xác định lời gọi hợp lệ. Cơ chế đa hình của Java dispatch lời gọi đến phương thức của lớp thực tế đang được tham chiếu. Spring hỗ trợ tạo và nối các bean; constructor injection làm cho yêu cầu phụ thuộc thể hiện rõ trong mã nguồn. Nếu có nhiều bean cùng triển khai một interface, ứng dụng cần quy tắc chọn rõ ràng, chẳng hạn **@Qualifier** hoặc cấu hình bean.

## 3. Vì sao hai hướng có thể khác nhau?

Sự khác biệt trên thường xuất hiện khi áp dụng **Dependency Inversion Principle (DIP)**. Quy tắc này khuyến khích phần chính sách ổn định của ứng dụng phụ thuộc vào abstraction do nó cần, còn chi tiết kỹ thuật triển khai abstraction đó. Trong ví dụ:

1. Application định nghĩa **DonHangRepository** vì ca sử dụng cần khả năng lưu đơn hàng.
2. Infrastructure viết **JpaDonHangRepository** để đáp ứng hợp đồng đó.
3. Adapter phụ thuộc vào interface để biên dịch; application chỉ phụ thuộc vào interface.
4. Khi chạy, service vẫn gọi repository và lời gọi được chuyển đến adapter đã được inject.

Nhờ vậy, thay JPA bằng một cách lưu khác có thể chỉ cần thay adapter và cấu hình nối bean, miễn là hợp đồng mà application cần vẫn giữ nguyên. Application không phải import **EntityManager**, **JpaRepository** hay lớp adapter cụ thể chỉ để yêu cầu lưu một đơn hàng.

Việc nối các implementation thường được thực hiện tại **composition root** — nơi khởi tạo hoặc cấu hình các thành phần của ứng dụng. Trong Spring Boot, component scanning và dependency injection có thể đảm nhiệm phần lớn việc này qua **@Service**, **@Repository** và constructor injection. Cấu hình vẫn phải bảo đảm có đúng bean phù hợp với từng interface.

Không nên suy ra rằng mọi lời gọi phải hướng vào trong, hoặc mọi dependency trong mọi kiến trúc đều phải đảo chiều. Hướng phụ thuộc hợp lệ phụ thuộc vào quy tắc layer mà nhóm chọn. Điểm cần giữ là quy tắc đó phải rõ ràng và nhất quán. Nếu application trực tiếp tạo **new JpaDonHangRepository(...)** hoặc khai báo field bằng lớp JPA cụ thể, nó đã có dependency mã nguồn đến infrastructure; lúc đó lợi ích tách hợp đồng khỏi implementation giảm đi.

## 4. Khi nào hai hướng trùng nhau?

Trong một thiết kế đơn giản, service có thể phụ thuộc trực tiếp vào một lớp DAO cụ thể:

~~~java
public class TaoDonHangService {
    private final JdbcDonHangDao dao;

    public TaoDonHangService(JdbcDonHangDao dao) {
        this.dao = dao;
    }

    public void tao(DonHang donHang) {
        dao.insert(donHang);
    }
}
~~~

Ở đây, service gọi **JdbcDonHangDao** khi chạy và mã nguồn service cũng phụ thuộc trực tiếp vào kiểu **JdbcDonHangDao**. Hai hướng cùng chỉ từ service đến DAO. Cách này có thể phù hợp với ứng dụng nhỏ, ít khả năng thay đổi hoặc khi abstraction chưa đem lại lợi ích đủ lớn. Đổi lại, service gắn với công nghệ hoặc implementation cụ thể hơn, và việc kiểm thử thường cần thay thế dependency theo cách khó hơn.

Vì vậy, không phải cứ thấy hướng gọi và hướng phụ thuộc trùng nhau là sai. Cũng không phải cứ đảo được hướng phụ thuộc là kiến trúc tốt hơn. Hãy cân nhắc khả năng thay đổi, ranh giới module, nhu cầu kiểm thử và chi phí duy trì abstraction. Interface hữu ích khi nó biểu đạt một hợp đồng có ý nghĩa tại ranh giới; tạo interface cho mọi lớp chỉ để tăng số lượng kiểu có thể làm thiết kế rườm rà.

## 5. Cách kiểm tra hai hướng trong một dự án

Khi điều tra một request cụ thể, hãy lần theo **hướng gọi khi chạy**:

1. Bắt đầu từ entry point, chẳng hạn controller hoặc message listener.
2. Dùng breakpoint, call stack hoặc trace để xác định phương thức được gọi tiếp theo.
3. Khi lời gọi đi qua interface, kiểm tra lớp thực tế của object nhận lời gọi.
4. Theo tiếp đến adapter, driver hoặc client bên ngoài; ghi nhận cả đường trả kết quả và xử lý lỗi.

Khi đánh giá ranh giới kiến trúc, hãy lần theo **hướng phụ thuộc mã nguồn**:

1. Xem import, field, constructor parameter, method signature và quan hệ extends/implements.
2. Kiểm tra package hoặc module nào cần module nào trong cấu hình build.
3. Với dependency injection, xác định interface được khai báo ở layer nào, implementation ở đâu và bean được nối bằng cơ chế nào.
4. Đối chiếu các dependency đó với quy tắc layer của dự án. Ví dụ, domain có được import Spring/JPA không; application có phụ thuộc vào web framework hoặc lớp persistence cụ thể không.

Trong Spring, việc controller nhận **TaoDonHangUseCase** qua constructor cho thấy dependency mã nguồn của controller là interface. Để biết implementation nào đang chạy, cần tìm bean triển khai interface và xem cấu hình, profile, qualifier hoặc điều kiện tạo bean. Chỉ đọc tên interface trong constructor chưa đủ để kết luận object runtime là lớp nào.

Kiểm thử cũng giúp xác nhận ranh giới. Có thể kiểm thử **TaoDonHangService** bằng một implementation giả của **DonHangRepository**, kiểm thử controller với mock **TaoDonHangUseCase**, rồi kiểm thử tích hợp **JpaDonHangRepository** với cơ sở dữ liệu thử nghiệm. Các bài kiểm thử này kiểm tra hợp đồng và hành vi ở những ranh giới khác nhau; chúng không thay thế việc kiểm tra dependency giữa package/module. Nếu cần thực thi quy tắc kiến trúc, có thể dùng công cụ như ArchUnit để kiểm tra rằng package domain không import package infrastructure, hoặc application không phụ thuộc vào package web.

## 6. Những nhầm lẫn thường gặp

- **Thấy service gọi xuống database rồi kết luận service phụ thuộc mã nguồn vào database.** Lời gọi runtime có thể đi qua interface và adapter; cần kiểm tra kiểu mà service thực sự khai báo.
- **Thấy service chỉ import interface rồi kết luận interface là object thực thi.** Interface mô tả hợp đồng; object runtime là instance của một lớp cụ thể.
- **Cho rằng dependency injection làm mất dependency.** DI thay đổi cách cung cấp implementation, nhưng dependency của lớp vẫn thể hiện qua kiểu mà constructor hoặc field yêu cầu.
- **Đọc mũi tên call graph như mũi tên dependency graph.** Mỗi sơ đồ cần chú thích loại mũi tên; nếu không, người đọc dễ hiểu sai.
- **Cho rằng hướng phụ thuộc luôn phải đảo chiều.** Đây là lựa chọn thiết kế theo ranh giới và chính sách của hệ thống, không phải công thức áp dụng máy móc cho mọi lớp.

## 7. Ghi nhớ khi thiết kế phân tầng

Trước khi kết luận một kiến trúc có tuân thủ layering hay không, hãy viết rõ hai quy tắc riêng: thành phần nào được phép gọi thành phần nào khi chạy, và mã nguồn ở layer nào được phép phụ thuộc vào layer hoặc abstraction nào. Sau đó kiểm tra cả hai bằng bằng chứng phù hợp: trace/call stack cho luồng chạy; import, khai báo kiểu và cấu hình module cho dependency.

Một hệ thống có thể cho phép application gọi adapter lưu trữ khi chạy, đồng thời giữ cho mã nguồn application chỉ biết interface do nó cần. Đó là một cách kết hợp kiến trúc phân tầng với dependency inversion. Thiết kế tốt khi các quy tắc được chủ động lựa chọn, có lý do rõ ràng, có thể kiểm tra và phù hợp với quy mô cũng như nhu cầu thay đổi của hệ thống.
