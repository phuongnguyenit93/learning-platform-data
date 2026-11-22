# Đầu vào không tin cậy

Trong bảo mật ngôn ngữ chuyên biệt miền (Domain-Specific Language, DSL), **đầu vào không tin cậy (untrusted input)** là mọi dữ liệu đi vào parser, compiler, interpreter, build tool hoặc runtime mà hệ thống không thể mặc nhiên xem là an toàn. Nguồn dữ liệu có thể là file DSL do người dùng viết, cấu hình tải từ xa, biểu thức trong biểu mẫu, tham số API, template, plugin, package metadata, dữ liệu sinh tự động hoặc nội dung được chuyển tiếp từ một hệ thống khác.

Một file DSL trông có vẻ chỉ chứa khai báo dữ liệu vẫn có thể làm parser tiêu tốn quá nhiều bộ nhớ, tạo đường dẫn ghi file ra ngoài workspace, kích hoạt biểu thức ngoài ý muốn hoặc khiến runtime truy cập tài nguyên không được phép. Vì vậy, bảo mật DSL không chỉ là kiểm tra cú pháp. Hệ thống phải xác định ranh giới tin cậy, xác thực dữ liệu theo ngữ cảnh, giới hạn tài nguyên, kiểm soát quyền và bảo đảm mọi bước xử lý đều có semantics an toàn.

Ví dụ, một DSL triển khai có thể nhận tên artifact, đường dẫn output và tham số cấu hình từ người dùng:

~~~text
deployment order_service {
    artifact = "order-api"
    output = "build/releases/order-api"
    replicas = 3
}
~~~

Các trường này cần được kiểm tra theo kiểu và policy. Tên artifact phải thuộc namespace hợp lệ; output path phải nằm trong thư mục được phép; replicas phải nằm trong giới hạn vận hành. Nếu DSL cho phép gọi lệnh hoặc plugin, những quyền đó cần được kiểm soát riêng. Một chuỗi hợp lệ về mặt cú pháp chưa chắc an toàn để sử dụng trong filesystem, shell, database hay deployment API.

## 1. Đầu vào không tin cậy là gì?

Một đầu vào được xem là không tin cậy khi nguồn gốc, tính toàn vẹn hoặc quyền kiểm soát của nó không đủ để hệ thống dựa vào mà không xác thực. Không cần phải đến từ một kẻ tấn công; dữ liệu do người dùng hợp lệ cung cấp cũng có thể vô tình chứa giá trị sai, quá lớn hoặc không phù hợp với ngữ cảnh.

### 1.1. Dữ liệu do người dùng nhập

Tên module, biểu thức điều kiện, giá trị cấu hình, tham số build và nội dung template do người dùng nhập đều cần được kiểm tra. Người dùng có thể mắc lỗi, dùng phiên bản cú pháp khác hoặc cố tình cung cấp dữ liệu độc hại.

### 1.2. File được tải lên hoặc nhập từ bên ngoài

File DSL, archive, schema, model hoặc project template có thể chứa đường dẫn, tham chiếu và metadata không an toàn. Việc file có phần mở rộng đúng hoặc được parse thành công không chứng minh nội dung đáng tin.

### 1.3. Dữ liệu từ API và hệ thống tích hợp

DSL có thể nhận request từ web service, message broker, CI pipeline hoặc công cụ quản trị. Dữ liệu từ một service nội bộ vẫn cần xác thực vì service đó có thể bị cấu hình sai hoặc bị xâm nhập.

### 1.4. Dependency metadata

Thông tin package, plugin manifest, version descriptor và artifact metadata có thể đến từ registry. Resolver cần xác minh nguồn, cấu trúc và integrity thay vì tin mọi metadata tải về.

### 1.5. Generated input

Dữ liệu do một generator khác tạo ra vẫn có thể sai hoặc chứa giá trị nguy hiểm. Việc một thành phần trong cùng toolchain sinh dữ liệu không loại bỏ nhu cầu validation ở ranh giới tiếp nhận.

### 1.6. Dữ liệu đã được xác thực một phần

Một giá trị được kiểm tra là số nguyên có thể vẫn không hợp lệ khi dùng làm số worker, kích thước bộ nhớ hoặc cổng mạng. Validation luôn gắn với mục đích sử dụng và policy của trường.

## 2. Mô hình đe dọa và ranh giới tin cậy

Trước khi thiết kế biện pháp bảo vệ, cần xác định tài sản cần bảo vệ, nguồn dữ liệu, năng lực của đối tượng gửi dữ liệu và tác động có thể xảy ra.

### 2.1. Tài sản cần bảo vệ

Trong một DSL toolchain, tài sản có thể gồm:

- Source code, project và artifact.
- File trên filesystem và dữ liệu trong workspace.
- Secret, token, certificate và credential.
- Dependency registry và build cache.
- Máy chạy compiler, interpreter hoặc build worker.
- Hạ tầng cloud, cluster và dịch vụ production.
- Tính toàn vẹn của kết quả build và deployment.
- Dữ liệu người dùng và thông tin vận hành.

### 2.2. Trust boundary

Trust boundary là ranh giới mà dữ liệu đi từ một miền có mức tin cậy này sang miền khác. Ví dụ: trình duyệt gửi DSL đến API; API chuyển file vào compiler worker; compiler worker tạo artifact; deployment service sử dụng artifact để thay đổi hạ tầng.

~~~mermaid
flowchart LR
    A[User or external system] -->|Untrusted DSL and parameters| B[API boundary]
    B --> C[Parser and validator]
    C --> D[Restricted execution environment]
    D --> E[Artifact store]
    E --> F[Deployment controller]
    F --> G[Target infrastructure]
~~~

Mỗi ranh giới cần xác định dữ liệu nào được phép đi qua, danh tính nào được xác thực và quyền nào được cấp.

### 2.3. Attacker capability

Mô hình đe dọa cần nêu rõ người gửi có thể tải file, chọn template, khai báo biểu thức, thêm dependency, gọi plugin, điều khiển path hay yêu cầu tài nguyên đến mức nào. Không nên giả định người gửi chỉ sử dụng giao diện đúng cách.

### 2.4. Threat scenario

Một số tình huống cần xem xét:

- File DSL chứa cấu trúc lồng nhau cực sâu làm parser tràn stack.
- Biểu thức có vòng lặp hoặc phép tính tốn kém làm cạn CPU.
- Đường dẫn output thoát khỏi workspace và ghi đè file khác.
- Template chèn nội dung vào shell command mà không escape đúng.
- Plugin không tin cậy đọc secret từ environment.
- Dependency metadata trỏ đến artifact giả mạo.
- Error message vô tình ghi nội dung credential.

### 2.5. Threat modeling theo luồng dữ liệu

Vẽ luồng dữ liệu từ nguồn đến sink giúp phát hiện nơi cần kiểm tra. Sink là thao tác có thể tạo tác động như ghi file, thực thi lệnh, mở kết nối, tải package, truy vấn database hoặc triển khai resource.

### 2.6. Defense in depth

Không dựa vào một lần kiểm tra duy nhất. Parser, semantic validator, permission checker, sandbox, runtime guard và audit log cần bổ trợ nhau. Nếu một lớp bị bỏ qua hoặc có lỗi, lớp khác vẫn giới hạn được tác động.

## 3. Nguyên tắc xử lý dữ liệu an toàn

Một DSL an toàn nên áp dụng các nguyên tắc xuyên suốt vòng đời dữ liệu.

### 3.1. Mặc định không tin cậy

Chỉ nâng mức tin cậy khi dữ liệu đã qua kiểm tra và nguồn của nó được xác định. Không coi nội dung hợp lệ về cú pháp là an toàn để thực thi.

### 3.2. Validate theo ngữ cảnh

Một chuỗi có thể hợp lệ làm nhãn hiển thị nhưng không hợp lệ làm tên file, SQL identifier hoặc command argument. Dùng validator riêng cho từng ngữ cảnh.

### 3.3. Allowlist trước denylist

Ưu tiên xác định tập giá trị, kiểu, độ dài và cấu trúc được phép. Chặn một vài chuỗi nguy hiểm bằng denylist thường bỏ sót biến thể mã hóa hoặc cú pháp mới.

### 3.4. Least privilege

Parser không cần quyền ghi file; validator không cần quyền truy cập cloud; task build chỉ cần đọc source và ghi output đã khai báo. Mỗi thành phần chỉ nhận quyền tối thiểu.

### 3.5. Fail closed

Khi không thể xác định dữ liệu có an toàn hay không, từ chối thao tác có tác động. Không tự chuyển lỗi validation thành quyền truy cập rộng hoặc cấu hình mặc định nguy hiểm.

### 3.6. Explicit semantics

Định nghĩa rõ cách xử lý null, escape, coercion, path, encoding, timeout và lỗi. Hành vi ngầm định làm tăng khả năng mỗi lớp diễn giải cùng dữ liệu theo cách khác nhau.

### 3.7. Revalidate tại ranh giới quan trọng

Một object có thể được tạo từ dữ liệu đã validate, nhưng nếu nó bị biến đổi hoặc đi qua plugin không tin cậy thì cần kiểm tra lại trước khi thực hiện side effect.

### 3.8. Không dùng validation để thay thế authorization

Tên resource hợp lệ không có nghĩa người gửi được phép thay đổi resource đó. Validation kiểm tra hình dạng và miền dữ liệu; authorization kiểm tra danh tính và quyền.

## 4. Các lớp tiếp nhận đầu vào trong DSL

Đầu vào có thể đi qua nhiều lớp trước khi trở thành hành động.

### 4.1. Transport layer

API hoặc CLI tiếp nhận byte, file, request body và metadata. Lớp này cần giới hạn kích thước, xác thực danh tính, kiểm tra content type và thời gian nhận.

### 4.2. Decoding layer

Byte được chuyển thành văn bản hoặc cấu trúc theo encoding. Cần từ chối encoding không hỗ trợ, dữ liệu lỗi và chuỗi không hợp lệ theo chuẩn đã công bố.

### 4.3. Lexical layer

Lexer nhận diện token. Nó cần giới hạn kích thước token, xử lý comment/string/escape đúng grammar và tránh hành vi không nhất quán giữa các parser.

### 4.4. Parsing layer

Parser tạo AST từ token. Cần giới hạn độ sâu, số node, độ dài cấu trúc và thời gian parse.

### 4.5. Semantic layer

Semantic analyzer kiểm tra tên, kiểu, reference, phạm vi và ràng buộc miền. Một AST parse thành công vẫn có thể chứa reference không tồn tại hoặc biểu thức không hợp lệ.

### 4.6. Planning layer

Build/deploy planner chuyển model thành graph và kế hoạch thao tác. Cần xác minh dependency, quyền, resource budget và destination trước khi thực thi.

### 4.7. Execution layer

Interpreter, plugin hoặc task runner thực hiện thao tác. Đây là nơi cần sandbox, process isolation, permission check và runtime limit.

### 4.8. Output layer

Artifact, log, diagnostic và report có thể được tiêu thụ bởi hệ thống khác. Cần encode đúng ngữ cảnh và tránh đưa dữ liệu nhạy cảm vào output.

## 5. Giới hạn kích thước và tài nguyên đầu vào

Đầu vào nhỏ về dung lượng vẫn có thể tạo ra cấu trúc tốn nhiều tài nguyên. Giới hạn phải áp dụng cả trước và sau khi parse.

### 5.1. Kích thước request

Đặt giới hạn byte cho request body và file upload. Từ chối dữ liệu quá lớn trước khi đọc toàn bộ vào bộ nhớ.

### 5.2. Số lượng file

Project archive có thể chứa hàng trăm nghìn file nhỏ. Giới hạn số entry, tổng dung lượng giải nén và kích thước từng file.

### 5.3. Token và chuỗi

Giới hạn độ dài identifier, string literal, comment và token. Chuỗi khổng lồ có thể làm tăng chi phí copy, parse và lưu trữ.

### 5.4. Độ sâu lồng nhau

Giới hạn nesting depth của object, array, expression, block và AST. Parser đệ quy cần bảo vệ khỏi stack exhaustion.

### 5.5. Số lượng node và edge

Một DSL build có thể tạo graph rất lớn. Giới hạn số node, edge, dependency expansion và số lần tham chiếu để tránh memory exhaustion.

### 5.6. Thời gian xử lý

Đặt timeout cho decode, parse, validation, dependency resolution, expression evaluation và plugin execution. Timeout cần được truyền xuyên suốt thay vì mỗi lớp tự đặt một khoảng không liên quan.

### 5.7. Memory và concurrency budget

Giới hạn memory cho mỗi job và số job đồng thời. Một request hợp lệ riêng lẻ vẫn có thể gây cạn tài nguyên khi nhiều request chạy cùng lúc.

### 5.8. Decompression bomb

Archive có thể có kích thước nén nhỏ nhưng giải nén thành dữ liệu khổng lồ. Giới hạn tổng dung lượng sau giải nén và tỷ lệ mở rộng.

### 5.9. Budget theo tenant

Trong dịch vụ nhiều người dùng, áp dụng quota theo tenant để một người không chiếm hết CPU, memory, worker hoặc storage của các tenant khác.

## 6. Kiểm tra cú pháp và parser safety

Parser là ranh giới quan trọng vì nó xử lý dữ liệu có cấu trúc do bên ngoài cung cấp.

### 6.1. Grammar xác định

Grammar cần có quy tắc rõ cho token, precedence, associativity, string, comment và escape. Tránh để cùng một chuỗi được hiểu khác nhau giữa parser, formatter và runtime.

### 6.2. Parser không thực thi code

Parsing chỉ nên biến văn bản thành cấu trúc dữ liệu. Không thực thi function, tải plugin hoặc ghi file trong lúc parse.

### 6.3. Tránh parser khác biệt

Nếu frontend và backend dùng hai parser khác nhau, một file có thể được validator hiểu là an toàn nhưng runtime diễn giải theo cách khác. Nên dùng chung grammar/implementation hoặc kiểm tra tính tương đương.

### 6.4. Ambiguous grammar

Grammar nhập nhằng có thể gây tốn tài nguyên hoặc cho kết quả không nhất quán. Thiết kế precedence và associativity rõ, ưu tiên parser có hành vi thời gian dự đoán được.

### 6.5. Deep nesting

Input lồng nhau quá sâu có thể gây stack overflow. Dùng giới hạn độ sâu và parser iterative khi phù hợp.

### 6.6. Error recovery

Parser IDE có thể tiếp tục sau lỗi để hiển thị nhiều diagnostic. Tuy nhiên, AST phục hồi không nên được đưa vào execution path như một chương trình hợp lệ nếu chưa qua validation đầy đủ.

### 6.7. Source span

AST nên giữ vị trí nguồn để diagnostic chỉ ra dòng, cột và đoạn lỗi. Khi hiển thị đoạn source, encode đúng output context và giới hạn độ dài.

### 6.8. Unicode

Xác định encoding, chuẩn hóa identifier và cách xử lý ký tự vô hình. Các ký tự nhìn giống nhau có thể có code point khác nhau, gây nhầm lẫn trong tên module hoặc policy.

### 6.9. Parser differential tests

Kiểm thử cùng bộ input trên parser, formatter, validator và runtime để phát hiện khác biệt trong cách diễn giải.

## 7. Validation và type safety

Sau parsing, DSL cần xác thực cấu trúc và ý nghĩa của dữ liệu.

### 7.1. Schema validation

Kiểm tra field bắt buộc, field không được hỗ trợ, kiểu dữ liệu, cấu trúc lồng nhau và version schema.

### 7.2. Type checking

Xác minh biểu thức và giá trị có kiểu tương thích. Không tự động biến chuỗi thành command, path hoặc code chỉ vì một API downstream chấp nhận string.

### 7.3. Range validation

Giới hạn số lượng replica, timeout, kích thước batch, port và các giá trị số theo miền nghiệp vụ.

### 7.4. Enum validation

Dùng enum hoặc tập giá trị cho trạng thái, region, operation và mode. Giá trị ngoài tập cần bị từ chối thay vì fallback tùy tiện.

### 7.5. Cross-field validation

Một trường có thể phụ thuộc trường khác. Ví dụ bật TLS cần certificate reference; chọn deployment target cloud cần region hợp lệ; bật persistence cần storage configuration.

### 7.6. Unknown field

Field không được schema nhận diện có thể là typo hoặc cố gắng truyền option nguy hiểm. Nên từ chối hoặc cảnh báo theo policy, không âm thầm bỏ qua nếu điều đó làm thay đổi ý định.

### 7.7. Versioned schema

Gắn version cho schema DSL và xác định migration. Không dùng một parser mới để diễn giải file cũ theo semantics khác mà không có version boundary.

### 7.8. Validation result

Kết quả validation nên phân biệt error, warning và informational message. Chỉ trạng thái hợp lệ mới được đi vào execution path có side effect.

## 8. Injection và ranh giới giữa dữ liệu với câu lệnh

Injection xảy ra khi dữ liệu đầu vào bị diễn giải như một phần của cú pháp điều khiển ở hệ thống đích.

### 8.1. Command injection

Nếu DSL ghép chuỗi người dùng vào shell command, ký tự đặc biệt có thể làm thay đổi cấu trúc lệnh. Ưu tiên gọi process bằng executable và argument array, không tạo một chuỗi shell từ dữ liệu.

### 8.2. SQL injection

Nếu DSL tạo truy vấn database, dùng parameterized query và query builder có kiểu. Không nối trực tiếp input vào câu SQL.

### 8.3. Template injection

Template engine có thể diễn giải expression hoặc directive. Không render template không tin cậy với quyền truy cập object, filesystem hoặc function tùy ý.

### 8.4. Expression injection

Không đưa chuỗi do người dùng nhập vào evaluator như code nếu mục đích chỉ là dữ liệu. Dùng literal node hoặc parameter binding.

### 8.5. HTML và JavaScript output

Nếu DSL sinh web content, encode theo ngữ cảnh HTML text, attribute, URL hoặc JavaScript. Một cách escape chung không an toàn cho mọi ngữ cảnh.

### 8.6. Log injection

Chuỗi chứa newline hoặc ký tự điều khiển có thể giả mạo dòng log. Dùng structured logging, encode control characters và giới hạn trường do người dùng cung cấp.

### 8.7. Context-specific encoding

Encoding là bước cuối trước khi đưa dữ liệu vào sink. Nó không thay thế validation và không nên được dùng như một chuỗi thay thế ký tự tùy tiện.

## 9. An toàn khi đánh giá biểu thức DSL

Một số DSL cho phép người dùng viết biểu thức, predicate, function call hoặc script. Đây là bề mặt tấn công lớn nếu evaluator có quyền quá rộng.

### 9.1. Expression language giới hạn

Ưu tiên expression language khai báo với tập toán tử và function được kiểm soát thay vì nhúng ngôn ngữ lập trình tổng quát.

### 9.2. Không dùng eval tùy tiện

Không chuyển input thành source code rồi gọi cơ chế eval hoặc compiler động với quyền của ứng dụng chính.

### 9.3. Allowlist function

Chỉ cung cấp các hàm cần thiết, có semantics thuần và tài liệu rõ. Không tự động expose mọi method của object runtime.

### 9.4. Reflection và dynamic loading

Reflection, class loading và dynamic import có thể mở rộng quyền vượt khỏi DSL. Nếu không thật sự cần, không cung cấp; nếu cần, giới hạn package, class và capability.

### 9.5. Side effect

Condition nên là biểu thức thuần. Hành động có side effect nên được mô tả thành task riêng với quyền và dependency tường minh.

### 9.6. Recursion và loop

Nếu DSL hỗ trợ recursion hoặc loop, giới hạn độ sâu, số vòng lặp và tổng instruction. Một chương trình hợp lệ vẫn có thể không kết thúc.

### 9.7. Evaluation budget

Đặt budget cho số phép toán, function call, allocation và thời gian. Khi hết budget, dừng có kiểm soát và trả diagnostic.

### 9.8. Determinism

Với quyết định cần tái lập, tránh cho expression truy cập clock, randomness, environment hoặc network trực tiếp. Truyền những giá trị đó như input snapshot có version.

## 10. Path traversal và filesystem safety

DSL build và deploy thường nhận đường dẫn source, output, template, artifact hoặc file cấu hình. Đường dẫn do người dùng cung cấp phải được xử lý cẩn thận.

### 10.1. Path traversal

Path traversal xảy ra khi đường dẫn chứa thành phần điều hướng ra ngoài thư mục gốc được phép. Chỉ kiểm tra chuỗi có chứa hai dấu chấm là không đủ vì path có thể được encode, chuẩn hóa hoặc kết hợp từ nhiều phần.

### 10.2. Canonicalization

Chuyển path thành dạng chuẩn theo filesystem trước khi kiểm tra. So sánh đường dẫn đã resolve với root được phép và xác minh nó vẫn nằm bên trong root đó.

### 10.3. Symlink

Một đường dẫn nằm trong workspace có thể đi qua symlink trỏ ra ngoài. Cần quyết định có cho phép symlink hay không và kiểm tra target thực tế trước khi đọc/ghi.

### 10.4. TOCTOU

Time-of-check to time-of-use xảy ra khi đường dẫn được kiểm tra rồi bị thay đổi trước khi thao tác. Khi môi trường có thể bị thay đổi đồng thời, dùng API filesystem an toàn, handle đã mở và thao tác tương đối với directory handle nếu nền tảng hỗ trợ.

### 10.5. Archive extraction

Khi giải nén project, kiểm tra từng entry để bảo đảm không ghi ra ngoài destination. Kiểm soát symlink, absolute path, duplicate entry, tên file bất thường và dung lượng sau giải nén.

### 10.6. File overwrite

Không âm thầm ghi đè file người dùng hoặc file nằm ngoài vùng output được quản lý. Dùng staging directory, preview và policy conflict rõ.

### 10.7. File permissions

Không tạo file output với quyền rộng hơn cần thiết. Secret/config file cần quyền đọc hạn chế theo identity của tiến trình.

### 10.8. Temporary files

Tạo file tạm trong thư mục được kiểm soát, tên khó đoán và quyền hạn chế. Xóa file tạm khi hoàn tất hoặc khi job bị hủy.

## 11. Network, URL và remote resource

Một DSL có thể tham chiếu URL, registry, endpoint hoặc resource từ xa.

### 11.1. URL validation

Kiểm tra scheme, hostname, port và định dạng. Chỉ cho phép scheme cần thiết như HTTPS hoặc protocol nội bộ đã được phê duyệt.

### 11.2. Server-side request forgery

Nếu service tải URL do người dùng chỉ định, kẻ gửi có thể tìm cách truy cập địa chỉ nội bộ hoặc metadata endpoint. Áp dụng allowlist host, chặn dải địa chỉ nội bộ không được phép và kiểm tra lại sau DNS resolution.

### 11.3. Redirect

Một URL công khai có thể redirect đến địa chỉ khác. Giới hạn redirect, kiểm tra từng đích và không giữ credential qua redirect sang host không tin cậy.

### 11.4. DNS rebinding

Hostname có thể phân giải sang IP khác theo thời điểm. Với request nhạy cảm, cần kiểm tra địa chỉ đã resolve và bảo đảm kết nối thực tế không vượt policy.

### 11.5. Timeout và response size

Giới hạn connect timeout, read timeout, số redirect, response bytes và tốc độ tải. Không đọc response không giới hạn vào memory.

### 11.6. TLS verification

Không tắt xác minh certificate để “sửa” lỗi kết nối. Dùng trust store phù hợp và kiểm tra hostname.

### 11.7. Registry trust

Package registry và plugin repository cần được cấu hình theo policy. Không tự thêm repository tùy ý từ input DSL rồi tải và thực thi nội dung.

## 12. Serialization và deserialization an toàn

DSL có thể trao đổi dữ liệu qua JSON, YAML, XML, binary format hoặc AST serialization.

### 12.1. Chỉ dùng parser phù hợp

Dùng parser có cấu hình an toàn và được duy trì. Tránh parser cũ có lỗ hổng hoặc cấu hình cho phép thực thi object constructor từ dữ liệu.

### 12.2. YAML tags và object construction

Một số YAML loader hỗ trợ tag hoặc object construction có thể tạo object phức tạp. Với dữ liệu không tin cậy, dùng safe loading mode và schema hạn chế.

### 12.3. XML external entities

XML parser cần tắt external entity và external DTD nếu không cần. Nếu không, file có thể khiến parser đọc tài nguyên cục bộ hoặc gửi request ra mạng.

### 12.4. Polymorphic deserialization

Không cho dữ liệu bên ngoài tự chọn class tùy ý để deserialize. Dùng discriminator allowlist và kiểu DTO cụ thể.

### 12.5. Depth và size limit

Giới hạn kích thước, độ sâu, số phần tử, số key và độ dài string khi deserialize.

### 12.6. Schema evolution

Kiểm tra version và migration trước khi dùng object. Không giả định serialized object cũ luôn tương thích với runtime mới.

### 12.7. Integrity

Nếu artifact hoặc serialized model được lưu và tải qua nhiều hệ thống, có thể cần checksum hoặc signature để xác minh nguồn gốc và tính toàn vẹn.

## 13. An toàn cho template và code generation

Template và code generator có thể biến dữ liệu thành source code, configuration hoặc script.

### 13.1. Template context tối thiểu

Chỉ đưa những object và function cần thiết vào template context. Không expose toàn bộ runtime, filesystem hay secret store cho template.

### 13.2. Auto-escaping

Nếu template sinh HTML hoặc cấu hình có quy tắc quoting, dùng auto-escaping theo output format. Với source code, dùng AST builder hoặc serializer thay vì nối chuỗi thủ công.

### 13.3. Template trust level

Phân biệt template chính thức, template nội bộ đã review và template bên ngoài. Quyền của template phải phù hợp với nguồn và policy.

### 13.4. Code generation qua AST

Khi sinh code, xây AST hoặc cấu trúc typed rồi dùng printer của ngôn ngữ đích. Cách này giảm lỗi quoting và injection so với ghép source bằng chuỗi.

### 13.5. Generated file boundary

Chỉ ghi file vào output directory được phép. Đặt generated files trong vùng riêng và tránh ghi đè source do người dùng quản lý.

### 13.6. Post-generation hook

Hook chạy sau khi sinh code có thể thực thi lệnh. Cần allowlist command, giới hạn quyền, timeout, working directory và network access.

### 13.7. Reproducibility

Template output nên ổn định với cùng context. Không chèn dữ liệu môi trường nhạy cảm hoặc timestamp tùy tiện vào artifact.

## 14. Plugin và extension không tin cậy

Plugin có thể mở rộng parser, compiler, build system hoặc runtime. Chúng thường có quyền cao hơn dữ liệu cấu hình thông thường.

### 14.1. Plugin metadata

Khai báo ID, version, nguồn, API compatibility, capability, dependency và quyền cần thiết. Không nạp plugin chỉ dựa vào tên do input cung cấp.

### 14.2. Plugin signature

Có thể xác minh chữ ký hoặc checksum của plugin trước khi cài đặt. Integrity không thay thế review, nhưng giúp phát hiện nội dung bị thay đổi.

### 14.3. Process isolation

Chạy plugin trong process riêng giúp giới hạn crash, memory và quyền truy cập. IPC cần có schema, authentication và giới hạn kích thước.

### 14.4. Sandbox

Sandbox có thể giới hạn filesystem, network, system calls, CPU và memory. Cần kiểm tra cấu hình sandbox thực sự được áp dụng, không chỉ dựa vào nhãn “sandboxed”.

### 14.5. Capability-based access

Thay vì cấp plugin quyền truy cập toàn hệ thống, truyền các capability cụ thể như đọc source folder hoặc ghi output folder đã cấp.

### 14.6. Plugin lifecycle

Kiểm soát install, load, update và unload. Một plugin bị thu hồi hoặc không còn tương thích cần bị chặn ở lần chạy tiếp theo.

### 14.7. Không chạy plugin trong parser process

Parser cần hoạt động với quyền thấp và không thực thi extension tùy ý. Việc nạp plugin nên xảy ra ở giai đoạn riêng sau khi xác minh.

## 15. Secrets và dữ liệu nhạy cảm

Đầu vào DSL có thể chứa hoặc tham chiếu password, token, private key và thông tin cá nhân.

### 15.1. Không ghi secret trực tiếp vào source

Ưu tiên secret reference hoặc environment injection. File DSL và repository thường được chia sẻ rộng hơn nơi lưu credential.

### 15.2. Redaction

Đánh dấu trường nhạy cảm trong schema và che giá trị trong log, diagnostic, trace, report và UI.

### 15.3. Không log request body mặc định

Request DSL có thể chứa secret hoặc dữ liệu cá nhân. Log metadata cần thiết như request ID, kích thước và trạng thái thay vì toàn bộ nội dung.

### 15.4. Secret lifetime

Giới hạn thời gian secret tồn tại trong memory khi có thể. Tránh copy không cần thiết và không giữ secret trong cache dùng chung.

### 15.5. Secret access

Chỉ cấp secret cho task cần dùng. Parser và static analyzer không cần đọc password production.

### 15.6. Error handling

Exception không được chứa toàn bộ input hoặc secret. Diagnostic có thể nêu tên trường và loại lỗi mà không tiết lộ giá trị.

### 15.7. Data minimization

Chỉ thu thập và lưu dữ liệu cần cho xử lý. Xác định retention và quyền truy cập cho input archive, AST snapshot và audit record.

## 16. Sandbox và cô lập thực thi

Nếu DSL cho phép chạy biểu thức, plugin hoặc task do người dùng định nghĩa, cần cô lập môi trường thực thi.

### 16.1. Process boundary

Chạy job trong process riêng giúp áp dụng timeout, kill process và giới hạn resource. Process isolation không tự bảo đảm an toàn nếu process vẫn chạy với quyền host rộng.

### 16.2. Container isolation

Container có thể cung cấp filesystem view, network policy và resource limits. Cần cấu hình user không đặc quyền, read-only filesystem khi phù hợp, capability drop và giới hạn mount.

### 16.3. Operating system sandbox

Có thể dùng seccomp, namespaces, AppArmor, SELinux hoặc cơ chế tương đương để giới hạn system call và quyền truy cập. Cấu hình cụ thể phụ thuộc nền tảng.

### 16.4. Network isolation

Job parse hoặc compile thường không cần truy cập internet. Chặn network mặc định và chỉ mở endpoint được phép cho task cần tải dependency.

### 16.5. Filesystem isolation

Chỉ mount source input read-only và output folder được cấp. Không mount credential, socket quản trị hoặc thư mục host nhạy cảm vào sandbox nếu không cần.

### 16.6. Resource quotas

Giới hạn CPU, memory, process count, file descriptors, disk và thời gian. Theo dõi quota để phân biệt job bị giới hạn với lỗi logic.

### 16.7. Sandbox escape assumptions

Sandbox có thể có lỗ hổng hoặc cấu hình sai. Cập nhật kernel/runtime, giảm quyền host, dùng worker ephemeral và không đặt secret có giá trị cao trong môi trường xử lý input không tin cậy.

### 16.8. Multi-tenant isolation

Không dùng chung writable workspace, cache hoặc credential giữa tenant nếu không có namespace và permission isolation. Dọn dẹp dữ liệu tạm sau job theo policy.

## 17. An toàn trong build và deployment

DSL build/deploy có thể tác động đến package registry, cloud account và production infrastructure. Ranh giới giữa plan và apply cần được kiểm soát.

### 17.1. Plan trước apply

Tạo deployment plan và cho phép kiểm tra resource sẽ được tạo, sửa hoặc xóa. Không thực hiện thay đổi hạ tầng ngay trong lúc parse file.

### 17.2. Authorization theo resource

Kiểm tra caller có quyền trên project, environment, namespace và resource đích. Một deployment descriptor hợp lệ không cấp quyền tự động.

### 17.3. Environment separation

Tách credential và policy development, staging, production. Không để job xử lý input tùy ý có quyền production mặc định.

### 17.4. Approval gate

Thao tác có tác động lớn như xóa database, đổi network policy hoặc deploy production có thể cần approval riêng.

### 17.5. Destructive operation

Phân biệt create/update/delete. Xóa resource cần xác nhận target, ownership và tác động phụ thuộc trước khi apply.

### 17.6. Artifact provenance

Chỉ deploy artifact đã được build từ source và dependency đã xác minh. Gắn digest và build identity vào deployment record.

### 17.7. Plan/apply consistency

Nếu resource hoặc config thay đổi sau khi plan được tạo, cần phát hiện drift và tạo plan mới trước khi apply. Không áp dụng một kế hoạch đã lỗi thời mà không kiểm tra.

### 17.8. Rollback

Chuẩn bị chiến lược rollback hoặc compensation cho thao tác có thể thất bại giữa chừng. Không giả định mọi thay đổi đều có thể đảo ngược.

## 18. Kiểm soát quyền và capability

Authorization cần được thực hiện dựa trên danh tính và quyền cụ thể.

### 18.1. Authentication

Xác thực ai gửi DSL hoặc yêu cầu build/deploy. Không dùng tên người dùng trong file DSL làm bằng chứng danh tính.

### 18.2. Authorization

Kiểm tra principal có quyền đọc project, tải plugin, truy cập secret, ghi artifact hoặc triển khai environment hay không.

### 18.3. Capability

Capability là quyền cụ thể được truyền cho thành phần, chẳng hạn đọc một thư mục, ghi một output path hoặc gọi một API đã chọn.

### 18.4. Permission manifest

Plugin hoặc task có thể khai báo quyền cần thiết. Người quản trị có thể review và cấp quyền theo policy.

### 18.5. Context propagation

Giữ identity và tenant context qua queue, worker và plugin boundary. Tránh nâng quyền khi chuyển từ API sang worker.

### 18.6. Revocation

Quyền có thể bị thu hồi trong khi job đang chờ. Hệ thống cần xác định thời điểm kiểm tra lại và cách dừng job nếu quyền không còn hợp lệ.

## 19. Diagnostic và xử lý lỗi an toàn

Thông báo lỗi cần giúp sửa dữ liệu mà không tạo thêm rủi ro.

### 19.1. Vị trí lỗi

Chỉ ra file, dòng, cột và field liên quan. Điều này giúp người dùng sửa đúng chỗ mà không cần log toàn bộ request.

### 19.2. Không echo toàn bộ input

Không đưa nguyên văn nội dung độc hại, token hoặc secret vào log. Nếu cần hiển thị đoạn source, giới hạn độ dài và encode ký tự điều khiển.

### 19.3. Phân loại lỗi

Phân biệt syntax error, schema error, authorization failure, resource limit, dependency failure và execution error. Mã lỗi ổn định giúp client xử lý đúng.

### 19.4. Không lộ nội bộ

Không trả stack trace, absolute path host, environment variable hoặc thông tin hạ tầng nhạy cảm cho caller không có quyền.

### 19.5. Correlation ID

Gắn request ID hoặc job ID để tìm log nội bộ đã được bảo vệ mà không phải trả thông tin nhạy cảm về client.

### 19.6. Safe fallback

Khi validation thất bại, dừng thao tác có side effect. Không dùng default quyền rộng hoặc tiếp tục với AST chưa hoàn chỉnh.

### 19.7. Rate limiting

Giới hạn tần suất request parse, validate hoặc compile để giảm nguy cơ abuse. Rate limit nên gắn với identity hoặc tenant, đồng thời có giới hạn toàn hệ thống.

## 20. Supply chain và nguồn gốc đầu vào

Một project DSL có thể phụ thuộc vào source, template, plugin và package từ nhiều nguồn.

### 20.1. Source provenance

Ghi nguồn file, repository, commit, uploader và thời điểm tiếp nhận khi phù hợp. Điều này hỗ trợ điều tra và tái hiện.

### 20.2. Dependency pinning

Khóa dependency version và source repository. Tránh để một tên package có thể được giải quyết từ nhiều nguồn không rõ thứ tự.

### 20.3. Checksums và signatures

Xác minh checksum hoặc chữ ký của artifact trước khi dùng. Metadata chữ ký cần được kiểm tra theo trust policy.

### 20.4. SBOM

Sinh Software Bill of Materials từ dependency graph để biết những package nào được đưa vào artifact.

### 20.5. Build attestation

Ghi nhận source revision, toolchain, dependency lock và kết quả build. Attestation giúp consumer đánh giá artifact được tạo như thế nào.

### 20.6. Cache trust

Build cache có thể chứa artifact từ job khác. Chỉ chia sẻ cache giữa các trust domain tương thích và xác minh key, ownership, integrity.

### 20.7. Artifact quarantine

Artifact mới từ nguồn chưa được tin cậy có thể được đưa vào vùng cách ly để scan và xác minh trước khi phát hành hoặc deploy.

## 21. Quan sát, audit và phát hiện bất thường

Bảo mật cần có khả năng ghi nhận sự kiện đủ để điều tra.

### 21.1. Security events

Ghi nhận validation failure, authorization denial, sandbox termination, resource limit hit, plugin load và deployment approval.

### 21.2. Structured audit

Audit record nên có actor, action, target, timestamp, result, source revision và correlation ID. Không lưu secret hoặc nội dung file đầy đủ nếu không cần.

### 21.3. Anomaly detection

Có thể phát hiện job đột ngột tăng CPU, tạo nhiều file, tải nhiều package hoặc gọi endpoint ngoài policy.

### 21.4. Metrics

Theo dõi kích thước input, parse duration, AST node count, timeout, sandbox kill và validation error theo loại. Không dùng dữ liệu nhạy cảm làm metric label.

### 21.5. Retention

Xác định thời gian lưu input, artifact, log và audit. Dữ liệu không còn cần thiết nên được xóa theo policy.

### 21.6. Alerting

Cảnh báo khi có nhiều request vượt limit, nhiều lần truy cập bị từ chối hoặc plugin bất thường. Alert nên chứa thông tin điều tra cần thiết nhưng không chứa secret.

## 22. Kiểm thử bảo mật đầu vào

Kiểm thử cần bao phủ cả dữ liệu hợp lệ, dữ liệu sai và trường hợp cực đoan.

### 22.1. Negative tests

Kiểm tra file sai grammar, field không tồn tại, type mismatch, path không hợp lệ, URL bị cấm và permission thiếu.

### 22.2. Boundary tests

Kiểm tra kích thước tối đa, độ sâu tối đa, số node tối đa, giá trị số ở biên và thời gian timeout.

### 22.3. Fuzz testing

Fuzzer tạo nhiều input biến đổi để tìm crash, hang, parser disagreement hoặc lỗi memory. Fuzz parser nên chạy trong môi trường giới hạn tài nguyên.

### 22.4. Property-based testing

Định nghĩa thuộc tính như parser không crash với input bất kỳ trong giới hạn, canonical path không vượt root, hoặc validation không cấp quyền mới.

### 22.5. Differential testing

Đưa cùng input qua parser hoặc serializer khác nhau để phát hiện cách diễn giải không thống nhất.

### 22.6. Sandbox tests

Xác minh job không thể đọc file ngoài mount, truy cập network bị cấm, vượt quota hoặc gọi capability không được cấp.

### 22.7. Injection regression tests

Lưu fixture cho những lỗi injection đã được phát hiện. Kiểm tra output được parameterize hoặc encode đúng ở từng sink.

### 22.8. Secret leakage tests

Đưa canary secret giả vào test và xác minh nó không xuất hiện trong log, diagnostic, crash report hoặc artifact.

### 22.9. Archive tests

Kiểm tra path traversal, symlink, duplicate entries, file cực lớn, số lượng entry cao và decompression bomb.

### 22.10. Dependency security tests

Kiểm tra repository allowlist, checksum mismatch, package version không được phép và plugin signature invalid.

### 22.11. Regression và continuous testing

Chạy bộ kiểm thử bảo mật cùng pipeline thay đổi parser, evaluator, template engine hoặc deployment adapter. Một thay đổi hiệu năng không được vô tình bỏ qua guard.

## 23. Quy trình xử lý đầu vào an toàn

Một pipeline tiếp nhận DSL có thể chia thành các bước sau:

~~~mermaid
flowchart TD
    A[Receive request] --> B[Authenticate and authorize]
    B --> C[Enforce byte and rate limits]
    C --> D[Decode with strict encoding]
    D --> E[Parse without side effects]
    E --> F[Validate schema and types]
    F --> G[Check paths, references and permissions]
    G --> H[Build restricted execution plan]
    H --> I[Run in isolated worker with quotas]
    I --> J[Validate outputs and provenance]
    J --> K[Store or deploy with approval policy]
~~~

### 23.1. Tiếp nhận

Xác thực caller, giới hạn request và gắn correlation ID. Không cấp quyền chỉ dựa trên metadata trong file.

### 23.2. Decode và parse

Đọc dữ liệu theo encoding đã hỗ trợ, giới hạn kích thước và parse thành AST không tạo side effect.

### 23.3. Validate

Kiểm tra schema, type, range, reference, path, URL, dependency và các ràng buộc nghiệp vụ.

### 23.4. Authorize

Kiểm tra quyền trên từng resource, plugin, secret và environment sẽ được truy cập.

### 23.5. Plan

Tạo execution plan và graph. Xác định tài nguyên, thời gian, quyền và các thao tác có tác động.

### 23.6. Execute

Chạy trong worker được cô lập với quota và capability tối thiểu.

### 23.7. Verify output

Kiểm tra output path, artifact integrity, metadata và không có file ngoài phạm vi được phép.

### 23.8. Publish hoặc deploy

Chỉ chuyển artifact qua bước phát hành hoặc deployment sau các kiểm tra và approval cần thiết.

## 24. Ví dụ: xử lý an toàn một deployment descriptor

Giả sử người dùng gửi descriptor để triển khai một service:

~~~yaml
service:
  name: order-api
  image: registry.example/order-api:2.1.0
  replicas: 3
  outputDirectory: build/deploy/order-api
  resources:
    cpu: "500m"
    memory: "512Mi"
~~~

### 24.1. Kiểm tra schema

Xác minh chỉ có field được hỗ trợ; name là identifier hợp lệ; replicas là integer; image là reference theo schema.

### 24.2. Kiểm tra miền giá trị

Áp dụng giới hạn replicas, CPU và memory theo policy của tenant và environment. Không cho một project yêu cầu vô hạn worker hoặc resource.

### 24.3. Kiểm tra image source

Chỉ chấp nhận registry được phê duyệt, version hoặc digest hợp lệ và artifact có provenance cần thiết.

### 24.4. Kiểm tra output path

Resolve outputDirectory bên trong workspace được cấp. Từ chối absolute path hoặc symlink đưa thao tác ra ngoài root.

### 24.5. Kiểm tra quyền

Xác minh caller có quyền deploy service vào namespace và environment đích. Tên service hợp lệ không chứng minh quyền deploy.

### 24.6. Tạo plan

Hiển thị resource sẽ tạo hoặc cập nhật, replica count, image digest và dependency readiness. Thao tác destructive cần approval phù hợp.

### 24.7. Thực thi cô lập

Chạy deployment adapter trong worker có credential scope đúng với environment. Không đưa credential production vào parser hoặc validator.

### 24.8. Audit

Lưu actor, descriptor revision, image digest, plan ID, approval và kết quả. Không ghi secret hoặc toàn bộ environment vào audit.

## 25. Ví dụ: biểu thức không tin cậy trong DSL

Giả sử DSL cho phép người dùng định nghĩa điều kiện để phân loại yêu cầu:

~~~text
decision access_level {
    input role: Role
    input resource: ResourceType

    when role == ADMIN and resource in allowedResources
        then result = ALLOW
    else
        result = DENY
}
~~~

### 25.1. Dùng grammar giới hạn

Chỉ cho phép identifier, literal, toán tử Boolean, phép so sánh và hàm allowlist. Không cho biểu thức tự tạo class, truy cập file hoặc gọi method tùy ý.

### 25.2. Type checking

Role và ResourceType phải có kiểu xác định. Hàm allowedResources cần trả collection đúng kiểu.

### 25.3. Pure evaluation

Điều kiện không gọi API quản trị hoặc thay đổi quyền. Dữ liệu được cung cấp qua immutable input context.

### 25.4. Budget

Giới hạn số node biểu thức, số lần gọi function và thời gian đánh giá.

### 25.5. Authorization ngoài biểu thức

Kết quả ALLOW của decision DSL vẫn phải được kiểm tra trong authorization enforcement point. Không để một file DSL do người dùng không có quyền sửa tự cấp quyền cho chính người đó.

### 25.6. Trace

Ghi rule ID và reason code. Nếu input chứa thông tin nhạy cảm, trace chỉ lưu trường cần thiết và được redacted.

## 26. Những sai lầm thường gặp

### 26.1. Chỉ kiểm tra cú pháp

File parse thành công vẫn có thể chứa path traversal, biểu thức tốn tài nguyên hoặc reference không được phép. Cần semantic validation và authorization.

### 26.2. Dùng blacklist chuỗi nguy hiểm

Chặn vài ký tự hoặc từ khóa không bao phủ mọi encoding và cú pháp. Xác định grammar và allowlist theo ngữ cảnh hiệu quả hơn.

### 26.3. Nối input vào shell command

Chuỗi được ghép có thể bị shell diễn giải thành cú pháp điều khiển. Dùng executable và argument array, hoặc không cho DSL chạy shell nếu không cần.

### 26.4. Dùng evaluator ngôn ngữ tổng quát

Eval có thể cho phép truy cập filesystem, network, reflection hoặc process. Dùng expression language giới hạn và sandbox.

### 26.5. Tin file nội bộ

File từ repository nội bộ vẫn có thể bị sửa, sinh sai hoặc chứa nội dung độc hại. Xác minh provenance và kiểm tra tại trust boundary.

### 26.6. Kiểm tra path bằng chuỗi

Kiểm tra tiền tố hoặc loại bỏ một vài ký tự không xử lý symlink, canonicalization và TOCTOU. Dùng path API và xác minh target thực tế.

### 26.7. Không giới hạn tài nguyên

Input nhỏ có thể tạo AST hoặc graph khổng lồ. Giới hạn bytes, depth, node count, CPU, memory, disk và concurrency.

### 26.8. Cho plugin quyền của host

Plugin không tin cậy có thể đọc secret hoặc sửa workspace. Dùng process isolation, sandbox và capability hẹp.

### 26.9. Log toàn bộ request

Request có thể chứa secret và dữ liệu cá nhân. Log metadata, mã lỗi và source location; redaction nội dung nhạy cảm.

### 26.10. Bỏ qua dependency provenance

Package đúng tên chưa chắc đến từ nguồn đúng. Pin repository, checksum, signature và lock file.

### 26.11. Coi sandbox là ranh giới tuyệt đối

Sandbox có thể cấu hình sai hoặc có lỗ hổng. Kết hợp sandbox với worker ephemeral, least privilege, patching và secret isolation.

### 26.12. Validation một lần rồi tin mãi

Dữ liệu có thể bị biến đổi bởi plugin hoặc bước trung gian. Revalidate trước sink có side effect và kiểm tra output sau execution.

## 27. Nguyên tắc thiết kế DSL an toàn với đầu vào không tin cậy

Một DSL an toàn cần xác định rõ dữ liệu được phép mô tả điều gì và hệ thống có thể thực hiện hành động nào từ dữ liệu đó.

### 27.1. Xác định trust boundary

Ghi rõ nguồn, luồng dữ liệu, sink và tài sản cần bảo vệ. Đánh giá threat scenario trước khi mở rộng tính năng.

### 27.2. Parse tách khỏi execute

Parser chỉ tạo AST. Không tải plugin, chạy lệnh, ghi file hoặc truy cập network trong quá trình parse.

### 27.3. Grammar và schema chặt chẽ

Giới hạn syntax, field, type, range, nesting và version. Từ chối dữ liệu không được hỗ trợ.

### 27.4. Validate theo sink

Kiểm tra path trước filesystem, parameterize query trước database, encode trước output và allowlist trước network request.

### 27.5. Dùng expression language giới hạn

Không expose runtime tổng quát. Dùng function allowlist, pure expression và evaluation budget.

### 27.6. Least privilege và capability

Parser, compiler, plugin, build worker và deploy worker có quyền riêng. Chỉ cấp quyền cần thiết cho từng task.

### 27.7. Giới hạn tài nguyên

Áp dụng quota cho input, parser, graph, evaluator, archive, network, process và tenant.

### 27.8. Cô lập thực thi

Chạy code hoặc plugin không tin cậy trong process/container sandbox với filesystem và network được giới hạn.

### 27.9. Bảo vệ secret

Không đưa secret vào AST, log hoặc artifact. Chỉ cấp secret cho bước thực sự cần và redaction ở mọi diagnostic.

### 27.10. Xác minh supply chain

Kiểm tra nguồn, version, checksum, signature, license và provenance của dependency, plugin và artifact.

### 27.11. Plan và approval

Tách parse/validate/plan khỏi apply. Các thao tác có tác động lớn cần authorization và approval phù hợp.

### 27.12. Kiểm thử liên tục

Fuzz parser, test boundary, kiểm tra injection, sandbox, path, serialization và secret leakage trong pipeline.

### 27.13. Diagnostic an toàn

Trả lỗi có vị trí và mã ổn định, không lộ stack trace, path host, secret hoặc nội dung request không cần thiết.

### 27.14. Theo dõi và cập nhật

Audit hành động, theo dõi bất thường, cập nhật parser/plugin/runtime và thu hồi artifact hoặc plugin không còn tin cậy.

## 28. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Untrusted Input | Dữ liệu chưa đủ cơ sở để mặc nhiên xem là an toàn |
| Trust Boundary | Ranh giới giữa các miền có mức tin cậy khác nhau |
| Threat Model | Mô tả tài sản, đối tượng, năng lực và tình huống tấn công |
| Input Validation | Kiểm tra cấu trúc, kiểu và miền giá trị đầu vào |
| Allowlist | Tập giá trị hoặc hành vi được cho phép rõ ràng |
| Least Privilege | Chỉ cấp quyền tối thiểu cần thiết |
| Fail Closed | Từ chối thao tác khi không thể xác định điều kiện an toàn |
| Parser Safety | Bảo vệ parser trước input gây crash, ambiguity hoặc cạn tài nguyên |
| AST | Cây cú pháp trừu tượng được tạo từ source |
| Injection | Dữ liệu bị diễn giải thành cú pháp điều khiển ở hệ thống đích |
| Command Injection | Input làm thay đổi lệnh hệ điều hành được thực thi |
| SQL Injection | Input làm thay đổi cấu trúc câu truy vấn SQL |
| Path Traversal | Đường dẫn vượt khỏi thư mục được phép |
| Canonicalization | Chuyển dữ liệu hoặc đường dẫn về dạng chuẩn trước khi kiểm tra |
| TOCTOU | Lỗi do đối tượng thay đổi giữa lúc kiểm tra và lúc sử dụng |
| SSRF | Server-side request forgery, khiến server gửi request đến đích không được phép |
| Safe Deserialization | Chuyển dữ liệu thành object mà không thực thi constructor hoặc class tùy ý |
| Sandbox | Môi trường thực thi bị giới hạn quyền và tài nguyên |
| Capability | Quyền cụ thể được cấp cho một thành phần |
| Resource Quota | Giới hạn CPU, memory, disk, process hoặc thời gian |
| Fuzz Testing | Tạo input biến đổi để tìm lỗi parser và xử lý dữ liệu |
| Redaction | Che dữ liệu nhạy cảm trong log và diagnostic |
| Provenance | Thông tin nguồn gốc của file, dependency hoặc artifact |
| SBOM | Danh mục thành phần phần mềm có trong artifact |
| Artifact Attestation | Bằng chứng về nguồn và quy trình tạo artifact |

Đầu vào không tin cậy là một phần bình thường của mọi DSL có người dùng, file, API, plugin hoặc hệ thống tích hợp. Bảo vệ hệ thống đòi hỏi nhiều lớp: giới hạn dữ liệu ngay khi tiếp nhận, parse không side effect, validate schema và kiểu, kiểm tra quyền theo resource, kiểm soát injection tại từng sink và cô lập mọi thao tác có thể thực thi code hoặc thay đổi hệ thống. Khi kết hợp least privilege, resource quota, sandbox, provenance, audit và kiểm thử bảo mật liên tục, DSL có thể xử lý dữ liệu bên ngoài một cách dự đoán được mà vẫn giữ được khả năng mở rộng và tích hợp.
