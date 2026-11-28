# Những tính năng framework hỗ trợ và phần ứng dụng phải tự thiết kế

Spring Shell cung cấp hạ tầng để xây dựng giao diện dòng lệnh cho ứng dụng Spring. Framework đảm nhận nhiều công việc lặp lại của một CLI: khởi tạo shell, nhận và phân tích lệnh, ánh xạ đối số vào tham số, chuyển đổi kiểu dữ liệu, hiển thị trợ giúp, gợi ý lệnh và làm việc với terminal. Ứng dụng vẫn phải quyết định người dùng được phép làm gì, mỗi lệnh có ý nghĩa nghiệp vụ ra sao, dữ liệu được lưu thế nào và kết quả nào được xem là thành công.

Hiểu đúng ranh giới này giúp command handler gọn, quy tắc nghiệp vụ có thể tái sử dụng và CLI hoạt động ổn định trong cả phiên tương tác lẫn quy trình tự động.

## 1. Ranh giới trách nhiệm nhìn từ luồng thực thi

Một lệnh thường đi qua các lớp sau:

```text
Người dùng hoặc script
        |
        v
Terminal và shell runtime             Spring Shell
        |
        v
Phân tích cú pháp, tìm command,
chuyển đổi tham số                    Spring Shell
        |
        v
Command handler / CLI adapter         Mã ứng dụng
        |
        v
Application service / use case        Mã ứng dụng
        |
        v
Domain, repository, hệ thống ngoài    Mã ứng dụng
        |
        v
Kết quả và mã thoát                   Ứng dụng + cấu hình runtime
```

Spring Shell xử lý cách một yêu cầu CLI được tiếp nhận và chuyển đến command. Ứng dụng định nghĩa ý nghĩa của yêu cầu đó. Command handler là điểm nối giữa hai phía: nó nhận dữ liệu đã được framework phân tích, gọi use case phù hợp và chuyển kết quả thành dạng người dùng CLI có thể hiểu.

| Mối quan tâm | Spring Shell hỗ trợ | Ứng dụng phải thiết kế |
|---|---|---|
| Khởi động shell | Tích hợp với hệ sinh thái Spring, quản lý bean và runtime của shell | Cấu hình ứng dụng, profile, dependency và cách triển khai |
| Khai báo command | Cơ chế đăng ký, định tuyến và metadata của command | Tên lệnh, nhóm lệnh, mô tả và hành vi cụ thể |
| Đối số và option | Phân tích cú pháp, binding tham số, giá trị mặc định và chuyển đổi kiểu có hỗ trợ | Hợp đồng đầu vào, kiểu miền riêng và ý nghĩa của từng tham số |
| Validation | Các điểm tích hợp để kiểm tra tham số và validation framework | Quy tắc nghiệp vụ, kiểm tra liên trường và thông báo dễ hiểu |
| Help và completion | Trợ giúp dựa trên metadata, cơ chế mở rộng gợi ý | Nội dung hướng dẫn và các giá trị gợi ý có ý nghĩa với nghiệp vụ |
| Tương tác terminal | API làm việc với terminal, prompt và thành phần hiển thị | Trình tự hỏi đáp, xác nhận, hủy và phương án chạy tự động |
| Output | Cơ chế trả kết quả và các tiện ích trình bày | Nội dung, định dạng, hợp đồng đầu ra và mức độ ổn định |
| Lỗi và mã thoát | Cơ chế thực thi, báo lỗi và điểm mở rộng xử lý kết quả | Phân loại lỗi nghiệp vụ, thông điệp, mã thoát và chính sách retry |
| Dữ liệu và bảo mật | Tích hợp Spring để ứng dụng kết nối các thành phần cần thiết | Phân quyền, xác thực, giao dịch, lưu trữ và bảo vệ dữ liệu |

Ranh giới trong bảng là ranh giới về trách nhiệm. Ứng dụng có thể cấu hình hoặc mở rộng nhiều cơ chế của Spring Shell, nhưng việc có một extension point không có nghĩa framework tự quyết định chính sách nghiệp vụ thay cho ứng dụng.

## 2. Những phần Spring Shell cung cấp

### 2.1. Shell runtime và tích hợp Spring

Spring Shell cung cấp môi trường để ứng dụng nhận lệnh và làm việc với terminal. Khi dùng cùng Spring Boot, ứng dụng có thể tận dụng dependency injection, cấu hình bên ngoài, profile và vòng đời bean của Spring.

Nhờ đó, command handler có thể nhận các service qua constructor injection. Handler không cần tự tạo kết nối cơ sở dữ liệu hoặc khởi tạo lại các thành phần dùng chung.

Framework cung cấp cơ chế chạy shell; ứng dụng vẫn quyết định cấu hình nào được nạp, service nào được đăng ký và môi trường nào được phép thực hiện một thao tác.

### 2.2. Đăng ký và định tuyến command

Spring Shell hỗ trợ khai báo command bằng annotation hoặc cơ chế đăng ký theo API của phiên bản đang dùng. Metadata có thể mô tả tên lệnh, mô tả, tham số và cách người dùng gọi command. Một số phiên bản còn có API đăng ký command theo hướng lập trình.

Ví dụ dưới đây minh họa phong cách annotation phổ biến trong các phiên bản Spring Shell hiện đại:

```java
@ShellComponent
class ProjectCommands {

    private final ProjectService projectService;

    ProjectCommands(ProjectService projectService) {
        this.projectService = projectService;
    }

    @Command(
        command = "project create",
        description = "Tạo project mới"
    )
    String create(@Option(longNames = "name") String name) {
        Project project = projectService.create(name);
        return "Đã tạo project: " + project.name();
    }
}
```

Khi người dùng gọi `project create --name demo`, shell tìm command tương ứng và chuyển giá trị của option vào tham số `name`. Handler sau đó được gọi.

Framework giúp định tuyến lệnh và binding tham số. Ứng dụng phải chọn tên lệnh dễ hiểu, quy định option nào bắt buộc, giá trị mặc định là gì và thao tác tạo project phải tuân theo quy tắc nào.

> API khai báo command thay đổi theo dòng phiên bản. Một số dự án cũ dùng `@ShellMethod` và `@ShellOption`; dự án mới có thể dùng `@Command`, `@Option` và `@Argument`. Hãy dùng nhất quán API mà phiên bản Spring Shell của dự án hỗ trợ, tránh trộn ví dụ từ các phiên bản khác nhau.

### 2.3. Phân tích cú pháp và chuyển đổi kiểu

Người dùng nhập dữ liệu dưới dạng văn bản. Shell cần phân biệt tên command, option, argument và giá trị đi kèm; sau đó chuyển dữ liệu sang kiểu tham số mà handler yêu cầu.

Ví dụ, tham số kiểu số có thể được chuyển từ chuỗi thành số nguyên; một giá trị tương ứng với enum có thể được ánh xạ thành hằng enum. Cơ chế chuyển đổi của Spring giúp giảm việc tự gọi `parseInt`, tách chuỗi hoặc kiểm tra kiểu trong mọi command.

Khi kiểu dữ liệu thuộc miền nghiệp vụ, ứng dụng có thể bổ sung converter phù hợp. Chẳng hạn, một mã project có thể cần được chuyển thành đối tượng `ProjectId`. Converter chỉ nên chịu trách nhiệm chuyển biểu diễn đầu vào thành kiểu đích. Việc mã đó có tồn tại, người dùng có quyền truy cập hay project có đang ở trạng thái cho phép thao tác hay không vẫn thuộc về lớp nghiệp vụ.

Chuyển đổi kiểu và validation cũng là hai việc khác nhau:

- Chuyển đổi trả lời: “Văn bản này có thể trở thành kiểu dữ liệu được yêu cầu không?”
- Validation trả lời: “Giá trị đã chuyển đổi có thỏa điều kiện được phép không?”

Ví dụ, `"abc"` không thể chuyển thành số nguyên; còn `-3` có thể chuyển thành số nguyên nhưng không hợp lệ nếu số lượng phải lớn hơn hoặc bằng 0.

### 2.4. Validation ở mức tham số

Spring Shell cung cấp cơ chế khai báo ràng buộc và có thể tích hợp với các cơ chế validation của Spring hoặc Jakarta Bean Validation khi ứng dụng cấu hình dependency và kích hoạt tương ứng.

Các kiểm tra như tham số bắt buộc, kiểu dữ liệu, giới hạn số hoặc chuỗi có thể được thực hiện tại biên nhận lệnh. Tuy nhiên, không nên chỉ kiểm tra quy tắc nghiệp vụ ở command handler. Một quy tắc như “tên project phải duy nhất” cần được bảo vệ trong use case hoặc domain service để mọi nơi gọi nghiệp vụ đều tuân theo, kể cả khi thao tác không xuất phát từ CLI.

Có thể chia validation thành ba lớp:

1. **Cú pháp đầu vào:** command có nhận đủ option bắt buộc không, giá trị có chuyển đổi được không.
2. **Ràng buộc dữ liệu:** chuỗi không rỗng, số nằm trong giới hạn, ngày có định dạng và miền giá trị hợp lệ.
3. **Quy tắc nghiệp vụ:** project đã tồn tại chưa, trạng thái hiện tại có cho phép xóa không, người gọi có quyền thực hiện thao tác không.

Spring Shell và các thư viện tích hợp hỗ trợ lớp đầu; ứng dụng khai báo và phối hợp các kiểm tra phù hợp cho cả ba lớp.

### 2.5. Help và tự hoàn thành

Metadata của command giúp Spring Shell xây dựng trợ giúp và mô tả cách gọi lệnh. Người dùng có thể khám phá các command và tham số thay vì phải ghi nhớ toàn bộ cú pháp. Cơ chế completion có thể gợi ý tên command, option hoặc giá trị thông qua các provider và điểm mở rộng tương ứng.

Framework cung cấp cơ chế hiển thị và truy vấn gợi ý. Ứng dụng cần cung cấp nội dung có ích: mô tả rõ tác động của lệnh, ví dụ sử dụng, các giá trị hợp lệ và nguồn dữ liệu để gợi ý những giá trị thuộc miền nghiệp vụ.

Ví dụ, shell có thể hỗ trợ hoàn thành tên option `--status`; ứng dụng phải xác định các trạng thái hợp lệ như `ACTIVE`, `ARCHIVED` hoặc `SUSPENDED`. Nếu completion cần đọc dữ liệu từ hệ thống bên ngoài, ứng dụng cũng phải cân nhắc quyền truy cập, độ trễ và cách xử lý khi nguồn dữ liệu không khả dụng.

### 2.6. Tương tác với terminal

Spring Shell cung cấp các abstraction và thành phần hỗ trợ tương tác trên terminal, chẳng hạn nhập dữ liệu, hiển thị thông tin, định dạng bảng hoặc thể hiện tiến trình. Những tiện ích này giúp ứng dụng không phải tự xử lý mọi chi tiết điều khiển terminal.

Ứng dụng vẫn quyết định trải nghiệm của từng use case:

- Khi nào cần hỏi thêm thông tin?
- Khi nào cần yêu cầu xác nhận trước thao tác nguy hiểm?
- Người dùng có thể hủy ở bước nào?
- Nếu chạy trong môi trường không có terminal tương tác thì hành vi thay thế là gì?
- Thông tin nào được hiển thị và thông tin nào phải được che đi?

Một prompt xác nhận không nên là điều kiện duy nhất bảo vệ thao tác nguy hiểm. Use case vẫn cần kiểm tra quyền và trạng thái dữ liệu ở phía nghiệp vụ.

### 2.7. Chạy tương tác và chạy tự động

Spring Shell hướng đến việc xây dựng shell tương tác, đồng thời hỗ trợ các cách thực thi command không cần người dùng nhập từng lệnh tại prompt. Tùy phiên bản và cấu hình, ứng dụng có thể được gọi với command từ tham số khởi chạy hoặc tích hợp luồng lệnh/script.

Khả năng thực thi command không tự làm cho một quy trình trở nên an toàn để tự động hóa. Ứng dụng phải xác định rõ:

- Lệnh có yêu cầu prompt hay có thể nhận mọi dữ liệu qua option?
- Giá trị mặc định có an toàn khi không có người giám sát không?
- Output có ổn định để script đọc được không?
- Lệnh có thể chạy lặp lại mà gây tạo dữ liệu trùng hoặc tác động ngoài ý muốn không?
- Lỗi có được phản ánh bằng mã thoát khác 0 không?

Một command tốt nên tách phần nhập liệu khỏi use case. Nhờ vậy, cùng một use case có thể được gọi từ prompt, từ command không tương tác hoặc từ một thành phần khác trong ứng dụng.

### 2.8. Trả kết quả và xử lý lỗi

Spring Shell cung cấp cơ chế để command trả kết quả và để runtime hiển thị hoặc xử lý kết quả đó. Ứng dụng có thể sử dụng các thành phần trình bày phù hợp với terminal và mở rộng cách xử lý kết quả khi cần.

Framework không thể tự biết một lỗi có ý nghĩa gì đối với người dùng. Ví dụ, lỗi kết nối cơ sở dữ liệu, project không tồn tại và người dùng không có quyền là ba tình huống khác nhau. Ứng dụng cần phân loại lỗi, chọn thông điệp phù hợp và quyết định mã thoát cho từng nhóm kết quả.

## 3. Những phần ứng dụng phải tự thiết kế

### 3.1. Mô hình nghiệp vụ và use case

Đây là trách nhiệm quan trọng nhất của ứng dụng. Spring Shell không định nghĩa project, đơn hàng, tài khoản hay quy trình của sản phẩm. Framework cũng không quyết định điều kiện nào cho phép tạo, sửa, xóa hoặc chuyển trạng thái một đối tượng.

Nên để command handler đóng vai trò adapter mỏng:

1. Nhận tham số từ shell.
2. Chuyển tham số sang kiểu đầu vào của use case nếu cần.
3. Gọi application service.
4. Chuyển kết quả hoặc lỗi thành phản hồi CLI.

Quy tắc nghiệp vụ nên nằm trong application service hoặc domain model. Khi đó, cùng một use case có thể được dùng từ REST API, tác vụ nền, kiểm thử hoặc một giao diện khác mà không phụ thuộc vào Spring Shell.

### 3.2. Hợp đồng lệnh và trải nghiệm người dùng

Ứng dụng phải thiết kế command như một giao diện công khai. Tên lệnh, option, argument, alias và giá trị mặc định cần nhất quán. Các thao tác có tác động lớn nên có cách gọi dễ nhận biết và yêu cầu xác nhận phù hợp.

Ví dụ, `project delete --id 42` cần làm rõ project nào sẽ bị xóa, việc xóa có thể khôi phục không và có cần xác nhận hay không. Chỉ thêm một prompt không đủ nếu command còn được chạy trong script. Ứng dụng phải định nghĩa một cách truyền xác nhận rõ ràng hoặc một chính sách an toàn cho môi trường tự động.

### 3.3. Quy tắc nghiệp vụ và thông báo lỗi

Ứng dụng cần xác định lỗi nào có thể sửa bằng cách nhập lại, lỗi nào do trạng thái dữ liệu, lỗi nào do quyền và lỗi nào do hạ tầng. Thông báo nên nói rõ điều gì đã xảy ra và người dùng có thể làm gì tiếp theo, đồng thời tránh tiết lộ thông tin nhạy cảm.

Không nên để thông báo lỗi phụ thuộc hoàn toàn vào tên exception hoặc stack trace. Stack trace hữu ích cho log chẩn đoán; người dùng CLI thường cần một thông báo ngắn, có ngữ cảnh và có thể hành động.

### 3.4. Dữ liệu, giao dịch và bảo mật

Ứng dụng chịu trách nhiệm kết nối repository, API và hệ thống bên ngoài; quản lý giao dịch; kiểm tra quyền; bảo vệ bí mật; và xác định hành vi khi thao tác thất bại giữa chừng.

Việc command đã được đăng ký không có nghĩa mọi người dùng đều được phép gọi command đó. Ẩn command khỏi help hoặc completion cũng không thay thế cho kiểm tra phân quyền tại use case hoặc service bảo mật.

### 3.5. Hợp đồng output và mã thoát

Output có thể phục vụ hai nhóm người đọc: con người và chương trình khác. Với người dùng trực tiếp, bảng, màu sắc và thông điệp có thể giúp đọc nhanh. Với script, output cần dự đoán được và ít thay đổi ngoài ý muốn.

Ứng dụng nên quyết định:

- Kết quả thành công hiển thị những trường nào?
- Kết quả rỗng được biểu diễn thế nào?
- Có cần hỗ trợ định dạng máy đọc như JSON hoặc CSV không?
- Lỗi được ghi ra đâu và có lẫn với dữ liệu đầu ra hay không?
- Mã thoát nào đại diện cho thành công, lỗi đầu vào, lỗi nghiệp vụ hoặc lỗi hệ thống?

Không nên dùng nội dung câu thông báo làm giao thức duy nhất để script xác định thành công. Mã thoát và định dạng output được thiết kế rõ ràng sẽ đáng tin cậy hơn.

## 4. Ví dụ: chia command adapter và nghiệp vụ

Giả sử ứng dụng cần tạo project mới. Service chịu trách nhiệm kiểm tra quy tắc và lưu dữ liệu:

```java
@Service
class ProjectService {

    private final ProjectRepository repository;

    ProjectService(ProjectRepository repository) {
        this.repository = repository;
    }

    Project create(String rawName) {
        String name = rawName == null ? "" : rawName.trim();

        if (name.isBlank()) {
            throw new InvalidProjectNameException();
        }

        if (repository.existsByName(name)) {
            throw new ProjectAlreadyExistsException(name);
        }

        return repository.save(new Project(name));
    }
}
```

Command handler tập trung vào giao diện CLI:

```java
@ShellComponent
class ProjectCommands {

    private final ProjectService projectService;

    ProjectCommands(ProjectService projectService) {
        this.projectService = projectService;
    }

    @Command(
        command = "project create",
        description = "Tạo project mới"
    )
    String create(@Option(longNames = "name") String name) {
        Project project = projectService.create(name);
        return "Đã tạo project: " + project.name();
    }
}
```

Trong ví dụ này, Spring Shell giúp nhận lệnh và binding option `--name`. Command handler chuyển yêu cầu đến service. Service chuẩn hóa tên, kiểm tra tên rỗng, kiểm tra trùng và lưu project. Các exception minh họa cần được ứng dụng định nghĩa và ánh xạ sang thông báo phù hợp.

Nếu sau này ứng dụng bổ sung REST API để tạo project, API có thể gọi cùng `ProjectService`. Quy tắc tạo project vẫn được áp dụng mà không phải sao chép vào controller hoặc command handler.

## 5. Theo dõi một lần thực thi

Với lệnh:

```bash
project create --name "Learning Platform"
```

luồng xử lý có thể được đọc theo các bước:

1. Shell runtime nhận dòng lệnh từ terminal.
2. Parser nhận diện command `project create` và option `--name`.
3. Framework chuyển giá trị option thành tham số của handler.
4. Command handler gọi `ProjectService.create(...)`.
5. Service kiểm tra quy tắc nghiệp vụ và gọi repository.
6. Handler nhận kết quả, tạo phản hồi CLI.
7. Runtime hiển thị kết quả; ứng dụng xác định cách phản ánh lỗi và mã thoát nếu có.

Điểm cần giữ rõ là parser không kiểm tra project đã tồn tại; repository không quyết định cách hiển thị thông báo; terminal không quyết định người dùng có quyền tạo project. Mỗi lớp có một trách nhiệm riêng và trao đổi qua hợp đồng rõ ràng.

## 6. Những lỗi thiết kế thường gặp

**Đặt toàn bộ nghiệp vụ trong command handler.** Ban đầu cách này có vẻ nhanh, nhưng logic khó tái sử dụng và khó kiểm thử khi ứng dụng có thêm giao diện khác. Hãy giữ handler mỏng và chuyển quy tắc vào use case.

**Chỉ validation ở đầu vào CLI.** Một lệnh có thể được gọi từ nhiều điểm khác nhau. Quy tắc quan trọng phải được bảo vệ trong lớp nghiệp vụ; validation ở CLI chủ yếu giúp phản hồi sớm và cải thiện trải nghiệm nhập liệu.

**Cho rằng có help là người dùng sẽ hiểu nghiệp vụ.** Help chỉ trình bày metadata và hướng dẫn do ứng dụng cung cấp. Mô tả cần nêu tác động, điều kiện và ví dụ đủ rõ.

**Bắt buộc prompt trong mọi trường hợp.** Prompt có thể làm quy trình script bị treo hoặc không thể tự động hóa. Hãy tách dữ liệu đầu vào khỏi tương tác và định nghĩa hành vi khi không có terminal tương tác.

**Dùng thông báo hiển thị làm tín hiệu máy đọc.** Câu chữ có thể thay đổi theo ngôn ngữ hoặc phiên bản. Script nên dựa vào mã thoát và định dạng output đã công bố.

**Xem việc ẩn command là bảo mật.** Help và completion là tiện ích khám phá. Phân quyền phải được kiểm tra tại lớp nghiệp vụ hoặc lớp bảo mật phù hợp.

**Để command handler tự quản lý trạng thái dài hạn.** Bean Spring thường có vòng đời dài. Trạng thái của một lần chạy lệnh không nên vô tình lưu trong field dùng chung của command bean; hãy truyền dữ liệu theo lời gọi hoặc dùng thành phần quản lý trạng thái có chủ đích.

## 7. Cách quyết định đặt logic ở đâu

Khi thêm một chức năng, hãy tự hỏi câu hỏi sau:

| Câu hỏi | Vị trí phù hợp |
|---|---|
| Chuỗi lệnh được phân tích và tham số được binding thế nào? | Cơ chế Spring Shell |
| Tên command, option và cách người dùng gọi là gì? | Command adapter của ứng dụng |
| Giá trị văn bản chuyển thành kiểu miền ra sao? | Converter ở biên CLI hoặc lớp ánh xạ |
| Giá trị có hợp lệ theo quy tắc sản phẩm không? | Validation và domain/application service |
| Người dùng có quyền thực hiện thao tác không? | Lớp bảo mật và use case |
| Dữ liệu được đọc, ghi và giao dịch thế nào? | Repository và application service |
| Kết quả cần hiển thị ra terminal ra sao? | Command adapter hoặc lớp trình bày |
| Script nhận biết thành công và thất bại thế nào? | Hợp đồng output và mã thoát của ứng dụng |

Một quy tắc thực tế: nếu logic vẫn phải đúng khi gọi use case từ một giao diện khác, logic đó không nên chỉ nằm trong command handler. Nếu logic chỉ liên quan đến cú pháp hoặc cách tương tác với terminal, nó thường thuộc lớp adapter CLI hoặc cơ chế của Spring Shell.

## 8. Checklist khi xây dựng command

- [ ] Command có tên, mô tả và ví dụ đủ rõ.
- [ ] Option và argument có kiểu, tính bắt buộc và giá trị mặc định hợp lý.
- [ ] Lỗi cú pháp và lỗi chuyển đổi được phản hồi dễ hiểu.
- [ ] Quy tắc nghiệp vụ được kiểm tra trong use case hoặc domain.
- [ ] Command handler không chứa quy trình nghiệp vụ dài.
- [ ] Completion chỉ đưa ra giá trị phù hợp và không làm lộ dữ liệu người dùng không được phép xem.
- [ ] Các thao tác nguy hiểm có chính sách xác nhận và kiểm tra quyền.
- [ ] Command có hành vi xác định khi chạy không tương tác hoặc trong script.
- [ ] Output và mã thoát đủ ổn định cho tự động hóa.
- [ ] Có kiểm thử cho use case, command adapter và các tình huống lỗi quan trọng.

Spring Shell giúp ứng dụng tập trung vào việc thiết kế một giao diện dòng lệnh nhất quán bằng cách cung cấp runtime, parser, command registration, help, completion và tiện ích terminal. Chất lượng của CLI vẫn phụ thuộc vào cách ứng dụng tổ chức use case, bảo vệ quy tắc nghiệp vụ, xử lý lỗi và công bố hợp đồng đầu vào/đầu ra. Giữ ranh giới rõ ràng giúp CLI dễ mở rộng, dễ kiểm thử và có thể phục vụ cả người dùng tương tác lẫn hệ thống tự động.

