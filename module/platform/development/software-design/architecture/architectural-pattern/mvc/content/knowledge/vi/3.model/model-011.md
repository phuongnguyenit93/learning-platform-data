# Ranh giới giữa Model, dịch vụ ứng dụng và lớp lưu trữ

Trong module **MODEL_VIEW_CONTROLLER**, Model giữ trạng thái và các quy tắc có ý nghĩa đối với ứng dụng. Khi một ứng dụng web phát triển, phần Model thường tương tác với dịch vụ ứng dụng và hệ thống lưu trữ. Nếu ba phần này bị trộn lẫn, quy tắc nghiệp vụ dễ bị khóa vào framework hoặc cơ sở dữ liệu; nếu tách chúng quá máy móc, mã nguồn lại phát sinh nhiều lớp chuyển tiếp mà không tạo thêm giá trị.

Bài học thuộc chương **Model** và tập trung vào một câu hỏi thiết kế: phần nào chịu trách nhiệm bảo vệ ý nghĩa nghiệp vụ, phần nào điều phối một ca sử dụng, và phần nào chuyển trạng thái sang nơi lưu trữ bền vững? Ta sẽ phân biệt ba ranh giới này, theo dõi một thao tác ghi dữ liệu, rồi áp dụng chúng vào cấu trúc mã Java.

## 1. Vì sao cần phân định ba trách nhiệm?

Hãy xét chức năng đăng ký một cuốn sách trong ứng dụng thư viện. Người dùng gửi tên sách, tác giả và ISBN. Ứng dụng cần:

- Kiểm tra dữ liệu có đủ và hợp lệ theo quy tắc của miền thư viện.
- Phối hợp các bước của ca sử dụng đăng ký sách.
- Kiểm tra những dữ liệu đã tồn tại và lưu sách mới.
- Xử lý giao dịch, lỗi lưu trữ và kết quả trả về cho giao diện.

Đây là một công việc nghiệp vụ duy nhất, nhưng nó chứa nhiều loại trách nhiệm. Nếu đặt tất cả trong Controller, Controller sẽ biết quá nhiều về nghiệp vụ và database. Nếu đặt tất cả trong một lớp Model, lớp đó có thể vừa kiểm tra trạng thái miền, vừa mở transaction, vừa chạy SQL. Nếu repository tự quyết định quy tắc nghiệp vụ, chính sách của ứng dụng bị phân tán trong các truy vấn.

Một thiết kế rõ ràng phân biệt:

| Thành phần | Câu hỏi mà thành phần chịu trách nhiệm trả lời | Ví dụ |
|---|---|---|
| **Model miền (Domain Model)** | Điều gì là hợp lệ theo nghiệp vụ? Trạng thái nào được phép chuyển đổi? | Một cuốn sách phải có ISBN hợp lệ; sách đã ngừng lưu hành không thể được phát hành lại theo quy tắc hiện tại |
| **Dịch vụ ứng dụng (Application Service)** | Ca sử dụng này cần phối hợp những bước nào và kết thúc ra sao? | Đăng ký sách, kiểm tra trùng ISBN, lưu thay đổi và trả kết quả |
| **Lớp lưu trữ (Persistence / Infrastructure)** | Trạng thái được đọc và ghi bằng công nghệ nào? | Dùng JPA, SQL, document database hoặc dịch vụ lưu trữ từ xa |

Ba phần phối hợp với nhau nhưng có lý do thay đổi khác nhau. Quy tắc miền thay đổi khi nghiệp vụ thay đổi; dịch vụ ứng dụng thay đổi khi quy trình của ca sử dụng thay đổi; adapter lưu trữ thay đổi khi cách truy cập dữ liệu hoặc công nghệ hạ tầng thay đổi.

## 2. Model trong MVC rộng hơn một lớp Entity

Từ “Model” trong MVC có thể chỉ toàn bộ phần trạng thái và hành vi mà View quan sát hoặc Controller điều phối. Trong một ứng dụng đơn giản, Model có thể chỉ là vài lớp dữ liệu và dịch vụ. Trong một hệ thống có miền nghiệp vụ phong phú, Model thường được tổ chức thành nhiều phần: domain model, quy tắc miền, dịch vụ miền, các hợp đồng truy cập dữ liệu và những mô hình đọc.

Vì vậy, không nên đồng nhất các khái niệm sau:

- **Domain Model** biểu diễn khái niệm, trạng thái, quan hệ và quy tắc nghiệp vụ.
- **ORM Entity** là đối tượng được framework ORM ánh xạ với cấu trúc lưu trữ. Nó có thể đồng thời là đối tượng miền trong một thiết kế phù hợp, nhưng hai vai trò không tự động giống nhau.
- **Database row/document** là dạng dữ liệu được lưu ở tầng hạ tầng.
- **DTO / View Model** là dữ liệu trao đổi qua một ranh giới hoặc phục vụ trình bày; nó không nhất thiết có hành vi nghiệp vụ.

Ví dụ, bảng BOOK có các cột ID, ISBN, TITLE, CREATED_AT. Đó là cấu trúc lưu trữ. Đối tượng Book trong miền có thể bảo vệ quy tắc ISBN, trạng thái xuất bản và hành vi ngừng lưu hành. Một BookRow dùng cho màn hình danh sách có thể chỉ gồm ID, TITLE và AUTHOR_NAME. Ba biểu diễn này liên quan đến cùng một cuốn sách nhưng phục vụ các mục đích khác nhau.

### 2.1. Trạng thái và hành vi thuộc về Model miền

Một đối tượng miền có ý nghĩa khi nó bảo vệ được các quy tắc áp dụng cho chính trạng thái của nó. Nếu mọi field đều public và bất kỳ nơi nào cũng có thể gán tùy ý, đối tượng chỉ là túi dữ liệu; quy tắc bị đẩy ra ngoài và có thể bị bỏ sót.

Ví dụ, thay vì cho phép mã gọi tự gán trạng thái sách:

~~~java
book.setStatus("PUBLISHED");
~~~

ta có thể cung cấp hành vi diễn đạt ý định:

~~~java
book.publish();
~~~

Phương thức publish() có thể kiểm tra sách đã có đủ thông tin cần thiết và đang ở trạng thái cho phép phát hành hay chưa. Đối tượng giữ quyền kiểm soát việc chuyển trạng thái. Caller chỉ yêu cầu một hành động, không tự sửa các chi tiết bên trong.

Không phải mọi đối tượng đều cần nhiều hành vi. Một Value Object bất biến như ISBN có thể chỉ xác thực và chuẩn hóa giá trị lúc khởi tạo. Một read model dùng để hiển thị có thể chỉ chứa dữ liệu. Mức độ hành vi phụ thuộc vào độ phức tạp và quy tắc thật sự của miền.

### 2.2. Entity và Value Object

Hai dạng đối tượng thường gặp trong Domain Model là Entity và Value Object.

| Đặc điểm | Entity | Value Object |
|---|---|---|
| Định danh | Có định danh ổn định qua thời gian | Không cần định danh riêng; được nhận diện bằng giá trị |
| So sánh | Thường so sánh theo identity | So sánh theo các thành phần giá trị |
| Vòng đời | Có thể thay đổi trạng thái | Nên bất biến; thay đổi bằng cách tạo giá trị mới |
| Ví dụ | Book, Member, Loan | ISBN, Money, Address, DateRange |

Một Book có thể đổi tiêu đề hoặc trạng thái nhưng vẫn là cùng một cuốn sách trong hệ thống vì ID không đổi. Một ISBN hợp lệ có thể được biểu diễn thành Value Object; hai ISBN có cùng giá trị sau chuẩn hóa được xem là bằng nhau.

Value Object giúp đưa validation vào đúng nơi. Nếu ISBN chỉ được tạo qua constructor hoặc factory có kiểm tra, các phần còn lại của miền có thể dựa vào cam kết rằng một ISBN đã tồn tại là hợp lệ theo định dạng đã chọn.

### 2.3. Aggregate và ranh giới nhất quán

Khi nhiều đối tượng miền phải thay đổi cùng nhau để bảo toàn một tập hợp quy tắc, chúng có thể được tổ chức thành một **Aggregate**. Aggregate có một Aggregate Root làm cửa vào cho các thay đổi bên ngoài. Caller yêu cầu hành vi trên root thay vì sửa trực tiếp các đối tượng con.

Ví dụ, một Loan có thể chứa các dòng mượn sách. Aggregate Root Loan bảo vệ quy tắc tổng số sách đang mượn, ngày đến hạn và trạng thái trả. Các thành phần bên ngoài gọi loan.returnBook(...) thay vì tự sửa trạng thái một dòng mượn và trạng thái tổng của khoản mượn theo hai thao tác rời rạc.

Ranh giới Aggregate cũng là gợi ý về phạm vi nhất quán giao dịch. Không nên tạo một Aggregate khổng lồ chỉ vì các bảng có quan hệ khóa ngoại. Hãy chọn ranh giới theo những quy tắc cần được bảo vệ cùng nhau. Những quy trình liên quan đến nhiều Aggregate thường cần một ca sử dụng điều phối và có thể cần cơ chế nhất quán cuối cùng thay vì một giao dịch kéo dài.

## 3. Dịch vụ ứng dụng điều phối ca sử dụng

Dịch vụ ứng dụng biểu diễn các thao tác mà hệ thống cung cấp cho bên ngoài. Nó nhận đầu vào đã được chuyển thành kiểu dữ liệu phù hợp, phối hợp Model và các cổng hạ tầng, xác định ranh giới giao dịch, rồi trả kết quả cho caller.

Ví dụ, ca sử dụng đăng ký sách có thể thực hiện các bước:

1. Nhận lệnh RegisterBook.
2. Kiểm tra ISBN đã tồn tại qua một cổng truy cập dữ liệu.
3. Tạo đối tượng Book hợp lệ.
4. Yêu cầu repository lưu Book.
5. Hoàn tất giao dịch và trả BookId.

Dịch vụ ứng dụng không cần tự thực hiện quy tắc như ISBN có định dạng đúng hay Book có được phép chuyển trạng thái hay không. Nó gọi hành vi miền để quy tắc được tập trung ở đối tượng có trách nhiệm bảo vệ trạng thái đó.

### 3.1. Application Service khác Domain Service

Hai loại dịch vụ có mục đích khác nhau:

| Loại dịch vụ | Trách nhiệm | Ví dụ |
|---|---|---|
| Application Service | Điều phối ca sử dụng, giao tiếp với các cổng, quản lý luồng và ranh giới giao dịch | RegisterBookService, ReturnLoanService |
| Domain Service | Biểu diễn quy tắc miền không tự nhiên thuộc về một Entity hoặc Value Object cụ thể | PricingPolicy tính giá dựa trên nhiều yếu tố miền |
| Infrastructure Service | Cung cấp chi tiết kỹ thuật như gửi email, truy cập file hoặc gọi dịch vụ bên ngoài | SmtpEmailSender, JpaBookRepository |

Application Service thường không nên trở thành nơi tập trung mọi quy tắc. Nếu một phương thức dịch vụ chứa nhiều điều kiện trạng thái và thuật toán nghiệp vụ, hãy xem xét chuyển phần hành vi đó vào Entity, Value Object hoặc Domain Service.

Ngược lại, không nên ép mọi thứ vào Entity. Một quy tắc cần phối hợp nhiều đối tượng và không có chủ sở hữu tự nhiên có thể phù hợp với Domain Service. Việc chọn nơi đặt logic dựa vào ý nghĩa nghiệp vụ, không dựa vào mong muốn làm cho một lớp có ít dòng code.

### 3.2. Application Service không phải Controller

Controller thuộc biên giao tiếp. Nó hiểu HTTP, route, status code, session, binding và định dạng phản hồi. Application Service hiểu ca sử dụng. Nó không nên nhận HttpServletRequest, HttpSession hoặc kiểu phản hồi của framework web.

Một ca sử dụng có thể được gọi từ nhiều adapter:

- Web Controller nhận request từ trình duyệt.
- REST Controller nhận request từ một client API.
- Message Consumer nhận thông điệp từ hàng đợi.
- Scheduled Job chạy một công việc định kỳ.
- CLI Adapter nhận lệnh từ terminal.

Các adapter có thể khác nhau về giao thức, nhưng cùng gọi một hợp đồng ứng dụng. Nhờ đó, nghiệp vụ không bị sao chép vào từng điểm vào.

## 4. Lớp lưu trữ chịu trách nhiệm về tính bền vững

Lớp lưu trữ biến các thao tác có ý nghĩa trong ứng dụng thành lệnh cụ thể cho database hoặc dịch vụ lưu trữ. Nó đảm nhiệm mapping, truy vấn, ghi, khóa, tối ưu truy cập và xử lý các lỗi kỹ thuật tương ứng.

Các thành phần thường gặp:

- **Repository:** cung cấp giao diện truy cập các đối tượng hoặc Aggregate theo ngôn ngữ của ứng dụng.
- **Repository Adapter:** triển khai giao diện đó bằng JPA, JDBC, SQL hoặc công nghệ cụ thể.
- **DAO (Data Access Object):** đóng gói thao tác truy cập dữ liệu ở mức gần với bảng hoặc truy vấn.
- **Unit of Work / Transaction Manager:** theo dõi và điều phối các thay đổi trong một giao dịch.
- **Mapper:** chuyển đổi giữa biểu diễn miền, biểu diễn ORM và DTO khi cần.

Repository và database không phải một. Repository là một hợp đồng mà ứng dụng sử dụng; database là một chi tiết lưu trữ. Trong thiết kế có đảo ngược phụ thuộc, interface repository nằm ở tầng miền hoặc tầng ứng dụng, còn implementation cụ thể nằm ở tầng hạ tầng.

### 4.1. Repository không nên chứa chính sách nghiệp vụ

Một repository nên cung cấp thao tác đọc và lưu phù hợp với Aggregate hoặc truy vấn. Ví dụ:

~~~java
public interface BookRepository {
    Optional<Book> findById(BookId id);

    boolean existsByIsbn(Isbn isbn);

    void save(Book book);
}
~~~

Hợp đồng này nói ứng dụng cần tìm Book theo ID, kiểm tra ISBN đã tồn tại và lưu Book. Nó không nói rằng dữ liệu phải nằm trong bảng SQL nào, dùng câu lệnh nào hoặc ORM nào.

Repository không nên tự quyết định một cuốn sách có được phát hành hay không. Nó có thể truy xuất dữ liệu cần thiết để Model hoặc Application Service đưa ra quyết định, nhưng quy tắc nghiệp vụ vẫn thuộc miền hoặc ca sử dụng.

### 4.2. Repository và DAO khác mức trừu tượng

DAO thường phản ánh cách truy cập dữ liệu: truy vấn một bảng, chạy câu SQL, ánh xạ một hàng dữ liệu. Repository thường phản ánh cách miền hoặc ứng dụng làm việc với đối tượng: tìm một Aggregate, lưu thay đổi hoặc thực hiện truy vấn theo ngôn ngữ nghiệp vụ.

Trong ứng dụng nhỏ, một DAO có thể đủ và không cần thêm repository chỉ để đổi tên phương thức. Trong hệ thống có Domain Model rõ ràng, Repository giúp miền không phụ thuộc vào cấu trúc bảng và API của ORM. Hãy chọn mức trừu tượng phù hợp với nhu cầu, tránh tạo nhiều lớp chỉ chuyển tiếp lời gọi.

### 4.3. Truy vấn đọc có thể dùng read model riêng

Không phải mọi truy vấn đều cần tải một Aggregate đầy đủ. Màn hình báo cáo có thể cần kết quả tổng hợp từ nhiều bảng, trong khi thao tác cập nhật cần một Aggregate có khả năng bảo vệ bất biến.

Có thể tách:

- **Write path:** tải Aggregate, thực hiện hành vi miền và lưu thay đổi.
- **Read path:** truy vấn trực tiếp dữ liệu cần thiết, ánh xạ thành DTO hoặc projection tối ưu cho màn hình.

Đây là cách tổ chức truy vấn đọc/ghi thường thấy trong ứng dụng phân lớp. Nó không bắt buộc phải triển khai CQRS đầy đủ. Mục tiêu là tránh tải cả đồ thị đối tượng phức tạp cho một bảng danh sách hoặc báo cáo chỉ cần vài cột.

## 5. Hướng phụ thuộc và luồng gọi khi chạy

Một nguyên tắc quan trọng là mã nguồn của tầng nghiệp vụ không nên phụ thuộc vào chi tiết lưu trữ. Ta có thể đạt được điều này bằng cách định nghĩa interface ở phía trong và để adapter hạ tầng triển khai interface đó.

~~~mermaid
flowchart TB
    subgraph Web["Biên giao tiếp"]
        Controller["MVC Controller"]
    end

    subgraph App["Tầng ứng dụng"]
        AppService["RegisterBookService"]
        AppPort["BookRepository interface"]
    end

    subgraph Domain["Model miền"]
        Book["Book Aggregate"]
        Isbn["ISBN Value Object"]
    end

    subgraph Infra["Tầng hạ tầng"]
        Adapter["JpaBookRepository"]
        ORM["ORM / JDBC"]
        DB[("Database")]
    end

    Controller --> AppService
    AppService --> AppPort
    AppService --> Book
    Book --> Isbn
    Adapter -. "implements" .-> AppPort
    Adapter --> ORM
    ORM --> DB
~~~

Trong sơ đồ, đường liền biểu diễn lời gọi hoặc tham chiếu đến hợp đồng; đường nét đứt biểu diễn adapter triển khai interface. Khi chạy, Application Service gọi BookRepository. Dependency Injection cung cấp đối tượng JpaBookRepository. Adapter thực hiện SQL và trả kết quả theo hợp đồng. Tầng ứng dụng không cần biết adapter đang dùng JPA hay JDBC.

Đây là sự khác biệt giữa **hướng phụ thuộc của mã nguồn** và **luồng điều khiển lúc chạy**. Lời gọi từ application service đi vào adapter, nhưng interface mà application service tham chiếu có thể được định nghĩa ở tầng ứng dụng. Adapter phụ thuộc vào interface để triển khai nó; tầng ứng dụng không cần phụ thuộc vào adapter cụ thể.

### 5.1. Không để ORM định hình toàn bộ Model

ORM giúp giảm mã truy cập dữ liệu, nhưng nếu mọi quy tắc và API nghiệp vụ bị viết xoay quanh entity của ORM, việc thay đổi framework hoặc lưu trữ sẽ rất tốn kém.

Một số dấu hiệu phụ thuộc quá chặt:

- Domain object kế thừa lớp nền của ORM chỉ để hoạt động.
- Quy tắc nghiệp vụ chỉ chạy trong callback hoặc lifecycle hook của persistence framework.
- Quan hệ lazy-loading khiến việc gọi một phương thức miền vô tình truy vấn database.
- View nhận trực tiếp ORM entity và làm lộ cấu trúc lưu trữ.
- Kiểm thử quy tắc miền bắt buộc phải khởi tạo Spring context hoặc database.

Không phải mọi dự án đều cần tách hoàn toàn persistence model khỏi domain model. Với ứng dụng CRUD đơn giản, dùng chung có thể là lựa chọn hợp lý. Khi quy tắc nghiệp vụ phong phú, vòng đời lưu trữ và miền khác nhau, hoặc cần thay công nghệ, việc tách mapping sẽ có lợi hơn.

### 5.2. Mapping ở đâu?

Có thể ánh xạ giữa Domain Model và persistence model tại adapter repository. Ví dụ, adapter đọc một hàng BOOK, tạo Book cùng ISBN Value Object, rồi trả về cho application service. Khi lưu, adapter chuyển Aggregate thành entity ORM và yêu cầu EntityManager ghi dữ liệu.

Việc mapping có thể thực hiện thủ công, bằng mapper hoặc bằng ORM. Điều cần giữ rõ là mapping thuộc ranh giới tích hợp. Domain Model không nên phải biết tên cột, kiểu SQL hoặc annotation của một công nghệ cụ thể nếu mục tiêu thiết kế là độc lập với hạ tầng.

## 6. Theo dõi một ca sử dụng từ Controller đến database

Hãy xem thao tác đăng ký sách. Dữ liệu HTTP đi qua các ranh giới như sau:

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant View as View
    participant C as BookController
    participant A as RegisterBookService
    participant R as BookRepository
    participant D as Book Domain Model
    participant DB as Database

    User->>View: Nhập tiêu đề và ISBN
    View->>C: POST /books
    C->>C: Binding và kiểm tra đầu vào
    C->>A: register(RegisterBookCommand)
    A->>R: existsByIsbn(isbn)
    R->>DB: SELECT kiểm tra ISBN
    DB-->>R: Kết quả
    R-->>A: Chưa tồn tại
    A->>D: Book.register(title, isbn)
    D-->>A: Book hợp lệ
    A->>R: save(book)
    R->>DB: INSERT trong transaction
    DB-->>R: Đã lưu
    R-->>A: Hoàn tất
    A-->>C: BookId
    C-->>View: Redirect hoặc response
    View-->>User: Hiển thị sách mới
~~~

Mỗi thành phần có một phần việc cụ thể:

1. Controller hiểu HTTP và chuyển request thành RegisterBookCommand.
2. Application Service điều phối ca sử dụng, kiểm tra dữ liệu cần tra cứu và gọi hành vi miền.
3. Book bảo vệ các quy tắc thuộc trạng thái của chính cuốn sách.
4. BookRepository cung cấp hợp đồng đọc/ghi.
5. JpaBookRepository hoặc adapter tương đương thực hiện truy vấn và lưu trữ.
6. Transaction Manager bảo đảm các thao tác trong phạm vi giao dịch tuân theo chính sách commit/rollback.

Nếu ISBN đã tồn tại, Application Service có thể trả một kết quả nghiệp vụ như DuplicateIsbn. Controller ánh xạ kết quả đó thành thông báo trên form hoặc mã lỗi API. Repository chỉ cung cấp thông tin tồn tại; nó không quyết định giao diện sẽ hiển thị thông báo gì.

### 6.1. Kiểm tra trước không thay thế ràng buộc database

Hai request có thể đồng thời kiểm tra cùng một ISBN và cả hai đều nhận kết quả “chưa tồn tại”. Sau đó cả hai cùng thử INSERT. Vì vậy, kiểm tra trước trong application service giúp đưa ra phản hồi dễ hiểu, nhưng không bảo đảm tính duy nhất khi có truy cập đồng thời.

Database vẫn cần unique constraint trên ISBN. Adapter cần chuyển lỗi vi phạm ràng buộc thành một kết quả hoặc ngoại lệ có ý nghĩa để tầng ứng dụng ánh xạ phù hợp. Đây là ví dụ về việc cùng một quy tắc cần được bảo vệ ở miền ứng dụng và được củng cố bằng ràng buộc toàn vẹn ở tầng lưu trữ.

### 6.2. Ranh giới transaction

Transaction thường nên bao quanh một ca sử dụng ghi dữ liệu hoặc một thao tác nhất quán của Aggregate. Application Service là nơi phù hợp để khai báo chính sách giao dịch vì nó biết toàn bộ các bước của ca sử dụng.

Không nên giữ transaction mở trong lúc chờ người dùng, gửi email chậm hoặc gọi dịch vụ ngoài không kiểm soát được thời gian. Nếu một ca sử dụng cần cập nhật database và phát thông điệp, hãy xem xét transactional outbox hoặc một cơ chế phối hợp phù hợp để tránh trường hợp database commit thành công nhưng thông điệp không được gửi.

## 7. Ví dụ Java: tách miền, ứng dụng và lưu trữ

Ví dụ sau minh họa các hợp đồng và trách nhiệm. Mã được rút gọn để tập trung vào ranh giới; cấu hình Dependency Injection, import và chi tiết framework được lược bỏ.

### 7.1. Value Object và Aggregate

~~~java
public record Isbn(String value) {
    public Isbn {
        if (value == null || !value.matches("[0-9X-]{10,17}")) {
            throw new IllegalArgumentException("ISBN không hợp lệ");
        }
    }
}

public final class Book {
    private final BookId id;
    private final Isbn isbn;
    private String title;
    private BookStatus status;

    private Book(BookId id, Isbn isbn, String title) {
        this.id = id;
        this.isbn = isbn;
        this.title = requireTitle(title);
        this.status = BookStatus.DRAFT;
    }

    public static Book register(BookId id, Isbn isbn, String title) {
        return new Book(id, isbn, title);
    }

    public void rename(String newTitle) {
        this.title = requireTitle(newTitle);
    }

    public void publish() {
        if (status != BookStatus.DRAFT) {
            throw new IllegalStateException("Chỉ sách ở trạng thái nháp mới được phát hành");
        }
        status = BookStatus.PUBLISHED;
    }

    private static String requireTitle(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Tên sách không được để trống");
        }
        return value.trim();
    }

    public BookId id() { return id; }
    public Isbn isbn() { return isbn; }
    public String title() { return title; }
    public BookStatus status() { return status; }
}
~~~

Book kiểm soát các thay đổi có ý nghĩa nghiệp vụ. Caller không thể gán trực tiếp một trạng thái bất kỳ; hành vi publish() tự kiểm tra điều kiện chuyển trạng thái. Isbn đảm bảo giá trị được tạo ra theo định dạng đã chọn.

Đoạn mã trên minh họa nguyên tắc, không phải bộ kiểm tra ISBN hoàn chỉnh cho mọi chuẩn và mọi quốc gia. Một hệ thống thực tế nên dùng quy tắc kiểm tra phù hợp với chuẩn ISBN mà nghiệp vụ chấp nhận.

### 7.2. Hợp đồng repository và command

~~~java
public record RegisterBookCommand(
    String isbn,
    String title
) {}

public record BookId(UUID value) {}

public interface BookRepository {
    boolean existsByIsbn(Isbn isbn);
    void save(Book book);
}
~~~

RegisterBookCommand là dữ liệu đầu vào của ca sử dụng. Nó không phải HTTP request và không cần chứa header, session hoặc chi tiết của framework web. BookRepository là hợp đồng mà application service cần để truy cập sách.

### 7.3. Application Service

~~~java
public final class RegisterBookService {
    private final BookRepository books;
    private final BookIdGenerator ids;

    public RegisterBookService(
        BookRepository books,
        BookIdGenerator ids
    ) {
        this.books = books;
        this.ids = ids;
    }

    public BookId register(RegisterBookCommand command) {
        var isbn = new Isbn(command.isbn());

        if (books.existsByIsbn(isbn)) {
            throw new DuplicateIsbnException(isbn);
        }

        var book = Book.register(
            ids.next(),
            isbn,
            command.title()
        );

        books.save(book);
        return book.id();
    }
}
~~~

Service điều phối các bước của ca sử dụng: tạo ISBN, kiểm tra trùng, khởi tạo Book, lưu và trả ID. Quy tắc tiêu đề không rỗng và trạng thái ban đầu nằm trong Book. Việc kiểm tra trùng được điều phối ở tầng ứng dụng vì nó cần tra cứu một tập hợp sách.

Trong ứng dụng thực tế, phương thức này sẽ chạy trong transaction do framework hoặc transaction runner quản lý. Cần xử lý cả trường hợp unique constraint bị vi phạm khi có request đồng thời; ví dụ trên lược bỏ phần ánh xạ ngoại lệ lưu trữ để tập trung vào ranh giới.

### 7.4. Persistence Adapter

~~~java
public final class JpaBookRepository implements BookRepository {
    private final EntityManager entityManager;
    private final BookMapper mapper;

    public JpaBookRepository(
        EntityManager entityManager,
        BookMapper mapper
    ) {
        this.entityManager = entityManager;
        this.mapper = mapper;
    }

    @Override
    public boolean existsByIsbn(Isbn isbn) {
        var count = entityManager.createQuery(
            "select count(b) from BookEntity b where b.isbn = :isbn",
            Long.class
        ).setParameter("isbn", isbn.value())
         .getSingleResult();

        return count > 0;
    }

    @Override
    public void save(Book book) {
        entityManager.persist(mapper.toEntity(book));
    }
}
~~~

JpaBookRepository biết EntityManager và BookEntity. Nó là chi tiết hạ tầng nên được phép phụ thuộc vào JPA. RegisterBookService chỉ biết BookRepository. BookMapper chịu trách nhiệm chuyển đổi giữa Book và biểu diễn persistence.

Đoạn code minh họa không bao gồm mọi chi tiết cập nhật entity đã tồn tại, khóa lạc quan, xử lý ngoại lệ hoặc cấu hình transaction. Khi triển khai, adapter cần bảo đảm mapping không làm mất trạng thái miền và transaction được mở ở đúng ranh giới.

## 8. Các lựa chọn tổ chức Model và persistence

Không có một cách tách lớp duy nhất phù hợp cho mọi ứng dụng. Mức độ tách biệt nên phản ánh độ phức tạp của nghiệp vụ và chi phí thay đổi.

| Cách tổ chức | Đặc điểm | Phù hợp khi | Rủi ro cần theo dõi |
|---|---|---|---|
| Active Record | Đối tượng dữ liệu thường chứa cả hành vi lưu/đọc | Ứng dụng CRUD nhỏ, nghiệp vụ đơn giản, framework hỗ trợ tốt | Model gắn chặt với database và framework |
| Data Mapper | Domain object độc lập; mapper/repository chuyển đổi với persistence model | Nghiệp vụ có quy tắc và vòng đời riêng | Tốn công mapping và cấu hình |
| Transaction Script | Mỗi ca sử dụng là một thủ tục điều phối dữ liệu và quy tắc | Quy trình đơn giản, ít hành vi miền phức tạp | Logic có thể lặp lại khi quy trình tăng |
| Domain Model phong phú | Entity, Value Object và Aggregate chứa hành vi, bảo vệ bất biến | Nghiệp vụ phức tạp và nhiều trạng thái | Dễ thiết kế quá mức nếu miền thực tế đơn giản |

Active Record không mặc nhiên là thiết kế xấu. Nếu ứng dụng chủ yếu quản lý danh mục đơn giản và framework đã cung cấp mô hình phù hợp, nó có thể giúp phát triển nhanh. Khi các quy tắc nghiệp vụ bắt đầu phụ thuộc vào nhiều đối tượng hoặc nhiều luồng thao tác, Data Mapper và Domain Model độc lập thường dễ kiểm soát hơn.

Một lỗi phổ biến là áp dụng kiến trúc nhiều tầng cho mọi bảng, dù mỗi tầng chỉ chuyển tiếp một lời gọi CRUD. Hãy tách khi có ranh giới thực sự cần bảo vệ: chính sách nghiệp vụ, khả năng thay công nghệ, quyền sở hữu dữ liệu, transaction hoặc hợp đồng tích hợp.

## 9. Các dấu hiệu ranh giới bị đặt sai

| Dấu hiệu | Vấn đề | Cách điều chỉnh |
|---|---|---|
| Controller chứa SQL và quy tắc trạng thái | Biên HTTP bị trộn với nghiệp vụ và lưu trữ | Chuyển điều phối ca sử dụng vào Application Service; truy cập dữ liệu qua port |
| Application Service chứa toàn bộ điều kiện nghiệp vụ | Model trở thành túi dữ liệu, quy tắc phân tán | Đưa hành vi bảo vệ trạng thái vào Entity, Value Object hoặc Domain Service |
| Repository quyết định có được phát hành/xóa đối tượng không | Chính sách nghiệp vụ bị gắn vào truy vấn và hạ tầng | Repository chỉ cung cấp dữ liệu; Model/ca sử dụng quyết định hành vi |
| Domain Model import EntityManager hoặc HttpServletRequest | Miền phụ thuộc vào chi tiết bên ngoài | Đưa kiểu framework về adapter và chuyển dữ liệu qua hợp đồng ổn định |
| View nhận ORM entity trực tiếp | Giao diện phụ thuộc schema và có thể kích hoạt truy vấn ngoài ý muốn | Tạo read DTO hoặc View Model phù hợp |
| Mỗi bảng có một interface/service/mapper chỉ chuyển tiếp | Tăng số lớp nhưng không tăng tính độc lập | Loại bỏ lớp không tạo ranh giới có ý nghĩa |
| Một transaction bao trùm cả lời gọi mạng chậm | Giữ khóa và kết nối quá lâu, khó phục hồi lỗi | Chia bước, dùng outbox hoặc quy trình bất đồng bộ khi cần |
| Chỉ kiểm tra dữ liệu tồn tại trước khi insert | Race condition vẫn có thể tạo bản ghi trùng | Giữ unique constraint và ánh xạ lỗi cạnh tranh ở adapter |

Khi thấy một lớp có quá nhiều lý do để thay đổi, hãy xác định nó đang trộn chính sách nghiệp vụ, điều phối ca sử dụng hay chi tiết kỹ thuật. Đặt logic theo lý do thay đổi thường giúp thiết kế dễ hiểu hơn việc tách lớp theo số lượng phương thức.

## 10. Kiểm thử từng ranh giới

Việc phân tách Model, Application Service và persistence tạo điều kiện kiểm thử theo đúng trách nhiệm.

### 10.1. Kiểm thử Model miền

Unit test cho Entity và Value Object không cần Spring, HTTP hoặc database. Kiểm tra các quy tắc trực tiếp:

- ISBN sai định dạng bị từ chối khi khởi tạo.
- Tiêu đề rỗng không thể dùng để đăng ký sách.
- Book mới bắt đầu ở trạng thái DRAFT.
- Chỉ Book ở trạng thái hợp lệ mới có thể publish().
- Các chuyển trạng thái bị cấm không làm thay đổi trạng thái hiện tại.

Các test này nên tập trung vào hành vi và bất biến, không kiểm tra chi tiết ORM mapping.

### 10.2. Kiểm thử Application Service

Dùng fake hoặc mock BookRepository để kiểm tra quy trình:

- ISBN chưa tồn tại thì service tạo Book và gọi save().
- ISBN đã tồn tại thì service trả lỗi nghiệp vụ và không lưu.
- Lỗi từ repository được xử lý hoặc truyền đi theo hợp đồng đã chọn.
- ID được tạo và trả về đúng với kết quả của ca sử dụng.

Test này không cần biết repository sử dụng JPA hay SQL. Nếu phải dựng database thật để kiểm tra một nhánh điều phối đơn giản, có thể application service đang phụ thuộc quá sâu vào hạ tầng cụ thể.

### 10.3. Kiểm thử Persistence Adapter

Adapter cần integration test với database thử nghiệm phù hợp để kiểm tra:

- Mapping giữa domain và persistence model giữ nguyên dữ liệu cần thiết.
- Truy vấn tìm đúng đối tượng và xử lý trường hợp không có kết quả.
- Lưu và tải lại không làm mất trạng thái miền.
- Unique constraint và các ràng buộc dữ liệu hoạt động như dự kiến.
- Transaction rollback khi một thao tác trong ca sử dụng thất bại.

Test adapter có thể phụ thuộc vào database và ORM vì mục tiêu của nó chính là xác minh tích hợp hạ tầng.

### 10.4. Kiểm thử kiến trúc

Ngoài test hành vi, có thể tự động kiểm tra quy tắc phụ thuộc giữa package/module. Ví dụ:

- Package domain không import package web hoặc persistence adapter.
- Application Service phụ thuộc vào interface repository, không phụ thuộc JpaBookRepository.
- Chỉ infrastructure package được import JPA hoặc JDBC.
- Controller không truy cập EntityManager trực tiếp.

Các quy tắc này giúp ngăn một thay đổi nhỏ làm ranh giới bị phá vỡ mà unit test nghiệp vụ vẫn chạy qua.

## 11. Checklist thiết kế ranh giới

- [ ] Model miền sở hữu các bất biến và hành vi liên quan đến trạng thái của nó.
- [ ] Entity, Value Object và Aggregate được dùng khi chúng diễn đạt được khái niệm thực của miền.
- [ ] Application Service điều phối ca sử dụng, không trở thành nơi chứa mọi quy tắc nghiệp vụ.
- [ ] Controller chỉ chuyển đổi giao thức đầu vào/đầu ra và gọi hợp đồng ứng dụng.
- [ ] Repository cung cấp hợp đồng truy cập dữ liệu phù hợp; implementation cụ thể nằm ở hạ tầng.
- [ ] Domain Model không cần biết SQL, EntityManager, HTTP request hoặc View.
- [ ] Mapping giữa domain và persistence được đặt tại ranh giới tích hợp.
- [ ] Transaction bao quanh đơn vị công việc cần nhất quán và không giữ mở trong lúc chờ dịch vụ ngoài.
- [ ] Các ràng buộc đồng thời quan trọng được bảo vệ ở database và được ánh xạ thành lỗi có ý nghĩa.
- [ ] Có unit test cho miền, test ca sử dụng và integration test cho adapter.

Khi thiết kế rõ ba ranh giới, Model có thể bảo vệ ý nghĩa nghiệp vụ, dịch vụ ứng dụng có thể điều phối ca sử dụng, còn lớp lưu trữ có thể thay đổi cách lưu dữ liệu mà không buộc quy tắc miền phải thay đổi theo.
