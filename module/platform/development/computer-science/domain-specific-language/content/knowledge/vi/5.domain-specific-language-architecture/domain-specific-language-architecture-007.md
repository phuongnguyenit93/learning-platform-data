# Lưu trữ và phân phối

## 1. Vai trò của lưu trữ và phân phối trong kiến trúc DSL

Một Domain-Specific Language (DSL) thường có nhiều thành phần cùng tồn tại: định nghĩa cú pháp, quy tắc ngữ nghĩa, trình phân tích (parser), bộ kiểm tra, trình thông dịch hoặc trình sinh mã, thư viện hỗ trợ và các chương trình được viết bằng DSL đó. Khi DSL được dùng trong một nhóm hoặc nhiều hệ thống, cần xác định cách lưu những thành phần này, cách quản lý phiên bản và cách đưa chúng đến đúng môi trường thực thi.

**Lưu trữ** trả lời những câu hỏi như:

- Mã DSL do người dùng viết được lưu ở đâu và theo định dạng nào?
- Định nghĩa ngôn ngữ, schema, grammar và thư viện được quản lý ra sao?
- Có lưu cây cú pháp hoặc kết quả biên dịch không, hay tạo lại từ mã nguồn khi cần?
- Làm thế nào khôi phục một phiên bản cấu hình đã chạy trước đây?

**Phân phối** trả lời những câu hỏi như:

- Người viết DSL lấy compiler, runtime, plugin và thư viện ở đâu?
- Ứng dụng nhận chương trình DSL bằng cách đóng gói cùng ứng dụng, tải từ registry hay nhận qua API?
- Làm thế nào bảo đảm môi trường chạy dùng đúng phiên bản ngôn ngữ và phụ thuộc?
- Làm thế nào phát hành bản cập nhật mà không làm hỏng các chương trình DSL hiện có?

Hai vấn đề này ảnh hưởng trực tiếp đến khả năng tái lập, bảo trì, mở rộng và vận hành DSL. Một ngôn ngữ có cú pháp tốt nhưng không có cơ chế lưu trữ, phát hành và nâng cấp rõ ràng sẽ khó được sử dụng ổn định trong môi trường thực tế.

## 2. Những loại dữ liệu cần lưu

Không nên xem mọi thứ liên quan đến DSL là một loại tệp duy nhất. Một hệ thống thường có ít nhất bốn nhóm dữ liệu.

| Nhóm dữ liệu | Nội dung | Ví dụ |
|---|---|---|
| Định nghĩa DSL | Cú pháp, schema, kiểu dữ liệu, quy tắc ngữ nghĩa và phiên bản ngôn ngữ | Grammar ANTLR, JSON Schema, định nghĩa kiểu |
| Chương trình DSL | Nội dung do người dùng hoặc nhóm phát triển viết bằng DSL | Tệp quy tắc, workflow, YAML, SQL |
| Hiện vật được sinh ra | AST, bytecode, mã nguồn sinh tự động, gói đã biên dịch hoặc chỉ mục | AST cache, Java source sinh từ DSL, gói compiler |
| Dữ liệu vận hành | Lịch sử phát hành, trạng thái thực thi, log, kết quả, thông tin kiểm toán | Execution record, audit log, deployment record |

Các nhóm này có vòng đời khác nhau. Định nghĩa DSL thay đổi khi nhà phát triển ngôn ngữ phát hành phiên bản mới. Chương trình DSL thay đổi theo yêu cầu nghiệp vụ. Hiện vật biên dịch có thể được tạo lại từ mã nguồn và đúng bộ công cụ. Dữ liệu vận hành cần được lưu theo chính sách kiểm toán, thời hạn lưu giữ và yêu cầu khôi phục.

Ví dụ, một nền tảng tự động hóa có thể lưu:

- Định nghĩa workflow và phiên bản DSL trong Git.
- Bản phát hành compiler trong artifact repository.
- Workflow mà người dùng tạo trong cơ sở dữ liệu hoặc kho đối tượng.
- AST đã phân tích trong cache để giảm thời gian tải.
- Lịch sử chạy workflow trong cơ sở dữ liệu phục vụ tra cứu và kiểm toán.

Phân tách các loại dữ liệu giúp chọn đúng công nghệ lưu trữ và tránh dùng một kho dữ liệu làm nơi chứa mọi thứ.

## 3. Lưu trữ mã nguồn DSL

### 3.1. Mã nguồn thường là dữ liệu chuẩn

Với DSL dạng văn bản, mã nguồn là biểu diễn dễ đọc, dễ xem xét và thuận tiện để quản lý phiên bản. Ví dụ:

~~~yaml
languageVersion: "2.1"
workflow:
  name: publish-report
  steps:
    - action: load-data
      source: monthly-sales
    - action: generate-report
      format: pdf
    - action: publish
      destination: report-archive
~~~

Tệp trên mô tả một workflow. Nó có thể được lưu cùng mã nguồn ứng dụng trong Git, lưu trong một kho cấu hình, hoặc được quản lý qua một dịch vụ chuyên lưu chương trình DSL. Lựa chọn phụ thuộc vào ai tạo nội dung, tần suất cập nhật, yêu cầu cộng tác và cách triển khai.

Với chương trình DSL được quản lý trong Git, nhóm có thể:

- Xem lịch sử thay đổi và xác định ai đã thay đổi quy tắc.
- Review thay đổi qua pull request.
- So sánh hai phiên bản trước khi phát hành.
- Gắn tag hoặc commit cụ thể với một lần triển khai.
- Khôi phục cấu hình đã biết là hoạt động tốt.

Nếu người dùng nghiệp vụ cần chỉnh sửa chương trình qua giao diện, hệ thống có thể lưu nội dung trong cơ sở dữ liệu hoặc object storage. Dù lưu ở đâu, nên giữ được lịch sử phiên bản và thông tin tác giả, thời điểm sửa, trạng thái phê duyệt và phiên bản ngôn ngữ.

### 3.2. Chọn định dạng lưu trữ

Định dạng lưu trữ cần phản ánh bản chất của DSL:

- **Văn bản thuần hoặc cú pháp riêng:** phù hợp với DSL có grammar độc lập, cần comment, cấu trúc khối hoặc biểu thức.
- **JSON hoặc YAML:** phù hợp với DSL khai báo có cấu trúc dữ liệu rõ ràng, cần trao đổi giữa nhiều hệ thống.
- **Cơ sở dữ liệu quan hệ:** phù hợp khi chương trình DSL được quản lý như các bản ghi có quyền sở hữu, trạng thái phê duyệt, phiên bản và quan hệ với người dùng hoặc dự án.
- **Object storage:** phù hợp với tệp lớn, gói phát hành, tệp đính kèm và bản lưu trữ bất biến.
- **Git repository:** phù hợp với mã nguồn cần review, branching, merge và lịch sử thay đổi chi tiết.

Không có một định dạng tốt nhất cho mọi DSL. Một DSL dạng biểu thức có thể khó đọc nếu bị chuyển thành một cấu trúc JSON quá sâu. Ngược lại, DSL khai báo gồm nhiều trường và danh sách có thể dễ kiểm tra hơn khi được biểu diễn bằng YAML hoặc JSON.

### 3.3. Bảo toàn nội dung gốc

Khi người dùng chỉnh sửa DSL, cần xác định hệ thống có phải giữ nguyên cách viết ban đầu hay chỉ cần giữ ý nghĩa của chương trình.

Parser thường chuyển văn bản thành Abstract Syntax Tree (AST). AST biểu diễn cấu trúc và ý nghĩa cú pháp, nhưng có thể bỏ qua comment, khoảng trắng, dấu ngoặc tùy chọn hoặc cách định dạng ban đầu. Nếu hệ thống dùng AST để ghi ngược ra tệp, kết quả có thể tương đương về ngữ nghĩa nhưng không giống văn bản mà người dùng đã nhập.

Có hai cách lưu phổ biến:

1. Giữ mã nguồn nguyên bản làm dữ liệu chuẩn, AST là dữ liệu dẫn xuất có thể tạo lại.
2. Dùng mô hình cấu trúc làm dữ liệu chuẩn, đồng thời lưu thông tin vị trí, comment và định dạng nếu cần tái tạo nội dung gần với bản gốc.

Với công cụ lập trình và cấu hình được review trong Git, giữ mã nguồn nguyên bản thường phù hợp. Với trình biên tập trực quan, mô hình cấu trúc có thể là dữ liệu chuẩn; tuy vậy cần xác định rõ cách xử lý comment, thứ tự phần tử và các trường mở rộng chưa được phiên bản hiện tại hiểu.

## 4. Lưu AST và hiện vật biên dịch

Quy trình xử lý DSL thường có thể biểu diễn như sau:

~~~mermaid
flowchart TD
    A["Mã nguồn DSL"] --> B["Parser"]
    B --> C["AST"]
    C --> D["Kiểm tra ngữ nghĩa và kiểu"]
    D --> E["IR hoặc kế hoạch thực thi"]
    E --> F["Interpreter / Code Generator"]
    F --> G["Thực thi hoặc chương trình đích"]
    C -.-> H["AST cache"]
    E -.-> I["Artifact cache"]
~~~

AST (Abstract Syntax Tree) là cấu trúc cây mô tả các thành phần cú pháp sau khi phân tích. Intermediate Representation (IR) là biểu diễn trung gian thuận tiện cho các bước tối ưu hóa, kiểm tra hoặc sinh mã tiếp theo. Tùy kiến trúc, compiler có thể tạo bytecode, mã nguồn của ngôn ngữ khác hoặc một kế hoạch thực thi.

### 4.1. Có nên lưu AST không?

Lưu AST có thể giảm thời gian phân tích lại một chương trình lớn hoặc cho phép nhiều dịch vụ cùng sử dụng một biểu diễn đã chuẩn hóa. Tuy nhiên, AST phụ thuộc vào phiên bản parser, grammar và đôi khi cả phiên bản compiler. Nếu grammar thay đổi, AST cũ có thể không còn tương thích.

Vì vậy, nếu lưu AST, metadata nên cho biết ít nhất:

- Định danh và phiên bản của DSL.
- Phiên bản parser hoặc compiler đã tạo AST.
- Phiên bản schema hay bộ quy tắc ngữ nghĩa liên quan.
- Hash của mã nguồn đầu vào.
- Phiên bản định dạng AST.

Khi một trong các yếu tố ảnh hưởng đến kết quả phân tích thay đổi, hệ thống cần xác định AST có còn dùng được không. Nếu không, hãy tạo lại từ mã nguồn.

### 4.2. Cache và dữ liệu chuẩn

AST, IR và bytecode thường là dữ liệu dẫn xuất. Nếu có thể tạo lại một cách tin cậy từ mã nguồn và bộ công cụ xác định, chúng có thể được lưu trong cache hoặc artifact repository. Không nên để cache trở thành bản duy nhất của chương trình vì cache có thể bị xóa, hết hạn hoặc không tương thích.

Một cache key nên phụ thuộc vào các đầu vào thực sự ảnh hưởng kết quả, chẳng hạn:

~~~text
hash(source) + languageVersion + compilerVersion + dependencyLock
~~~

Nếu chỉ dùng tên tệp hoặc thời điểm sửa, cache có thể trả về kết quả cũ sau khi grammar, thư viện hoặc compiler đã thay đổi.

### 4.3. Lưu kết quả sinh mã

Nếu DSL sinh Java, SQL hoặc cấu hình triển khai, nên phân biệt mã nguồn do con người quản lý với mã sinh tự động. Mã sinh có thể được lưu như một artifact để triển khai hoặc gỡ lỗi, nhưng cần truy ngược được về:

- Mã DSL nguồn.
- Phiên bản compiler.
- Phiên bản các thư viện hoặc plugin.
- Tham số build.
- Hash hoặc định danh của lần build.

Thông tin này giúp tái tạo kết quả và giải thích vì sao hai lần build có thể khác nhau.

## 5. Quản lý phiên bản DSL

Một hệ thống DSL có nhiều loại phiên bản và không nên gộp chúng thành một con số duy nhất:

| Phiên bản | Ý nghĩa |
|---|---|
| Language version | Phiên bản cú pháp và ngữ nghĩa mà chương trình DSL tuân theo |
| Compiler/runtime version | Phiên bản công cụ phân tích, kiểm tra và thực thi DSL |
| Package/library version | Phiên bản thư viện hoặc extension mà chương trình DSL sử dụng |
| Program revision | Phiên bản của chính tài liệu hoặc chương trình DSL |
| Artifact version | Phiên bản gói được build và phát hành |

Ví dụ, một workflow có thể khai báo language version 2.1, được biên dịch bằng compiler 3.4.0, sử dụng thư viện sales-actions 1.8.2 và có revision 42. Những thông tin này trả lời các câu hỏi khác nhau khi cần tái lập hoặc điều tra một lần chạy.

### 5.1. Phiên bản ngôn ngữ và tương thích

Khi DSL phát triển, thay đổi có thể thuộc một trong các loại:

- **Tương thích ngược:** chương trình cũ vẫn có ý nghĩa và chạy được với compiler mới.
- **Bổ sung tính năng:** thêm cú pháp hoặc hành vi mới nhưng không làm thay đổi chương trình cũ.
- **Thay đổi có nguy cơ phá vỡ:** bỏ một cấu trúc, đổi ý nghĩa một biểu thức hoặc thay đổi quy tắc kiểm tra.

Một quy tắc quản lý phiên bản rõ ràng giúp người dùng biết chương trình nào cần sửa. Ví dụ, có thể dùng phiên bản ngôn ngữ dạng major.minor: thay đổi major có thể chứa thay đổi không tương thích; thay đổi minor bổ sung tính năng tương thích; patch sửa lỗi triển khai mà không thay đổi ngữ nghĩa công khai. Đây là chính sách do dự án DSL lựa chọn, không phải quy định bắt buộc cho mọi ngôn ngữ.

### 5.2. Khai báo phiên bản trong chương trình

Một chương trình nên khai báo phiên bản ngôn ngữ mà nó sử dụng hoặc được gắn metadata tương đương:

~~~yaml
languageVersion: "2.1"
name: monthly-report
steps:
  - action: load-data
    source: monthly-sales
  - action: export
    format: pdf
~~~

Khi tải chương trình, runtime có thể kiểm tra phiên bản này và chọn parser, schema hoặc chế độ tương thích phù hợp. Nếu không hỗ trợ phiên bản yêu cầu, hệ thống nên báo lỗi rõ ràng thay vì âm thầm diễn giải bằng phiên bản khác.

### 5.3. Migration và deprecation

Khi cấu trúc DSL cũ cần được thay thế, có thể cung cấp migration tool để chuyển đổi tự động hoặc bán tự động. Một lộ trình thường gồm:

1. Đánh dấu cú pháp cũ là deprecated và đưa ra cảnh báo.
2. Tài liệu hóa cú pháp mới và lý do thay đổi.
3. Cung cấp công cụ kiểm tra chương trình hiện tại có bị ảnh hưởng không.
4. Cung cấp migration tool nếu phép chuyển đổi đủ rõ ràng.
5. Duy trì bộ kiểm thử tương thích cho chương trình cũ trong thời gian chuyển tiếp.
6. Chỉ loại bỏ cú pháp cũ theo chính sách phiên bản đã công bố.

Migration cần có khả năng xem trước thay đổi và lưu bản gốc. Không nên tự động ghi đè hàng loạt chương trình đang chạy mà không có quy trình phê duyệt và khả năng rollback.

## 6. Đóng gói và phân phối DSL

Phân phối DSL có thể là phân phối bộ công cụ để phát triển ngôn ngữ, phân phối chương trình DSL đến runtime, hoặc cả hai. Cần phân biệt các mô hình sau.

### 6.1. Đóng gói cùng ứng dụng

Ứng dụng có thể đóng gói parser, compiler hoặc runtime cùng với chương trình DSL. Cách này giúp triển khai một đơn vị và bảo đảm phiên bản công cụ được kiểm soát cùng phiên bản ứng dụng.

Phù hợp khi DSL chỉ được dùng nội bộ trong một ứng dụng, số lượng chương trình không lớn và vòng đời của DSL gắn chặt với vòng đời ứng dụng.

Hạn chế là mỗi lần cập nhật compiler hoặc chương trình DSL có thể cần build và phát hành lại ứng dụng. Nếu có nhiều ứng dụng cùng dùng một DSL, việc đồng bộ phiên bản cũng có thể phức tạp.

### 6.2. Phân phối qua package hoặc artifact repository

Compiler, runtime, plugin và thư viện DSL có thể được đóng gói thành artifact rồi phát hành qua package registry hoặc artifact repository. Ví dụ, thư viện Java có thể được phát hành dưới dạng Maven artifact; plugin Gradle có thể được phân phối qua plugin portal hoặc repository riêng.

Một gói DSL nên có:

- Tên và phiên bản duy nhất.
- Metadata về phiên bản ngôn ngữ tương thích.
- Danh sách phụ thuộc.
- Tệp grammar, schema hoặc tài nguyên cần thiết.
- Compiler, runtime hoặc plugin nếu gói có cung cấp chúng.
- Tài liệu, ví dụ và ghi chú phát hành.
- Hash hoặc chữ ký để kiểm tra tính toàn vẹn và nguồn gốc.

Package manager giúp giải quyết phụ thuộc và tải đúng phiên bản. Với môi trường build có yêu cầu tái lập, nên khóa phiên bản phụ thuộc hoặc dùng dependency lock file thay vì luôn lấy phiên bản mới nhất.

### 6.3. Phân phối qua DSL registry

Một DSL registry là dịch vụ lưu trữ và cung cấp các chương trình, module, schema hoặc package theo định danh và phiên bản. Registry có thể là một dịch vụ nội bộ hoặc một thành phần của nền tảng DSL.

Ví dụ, một hệ thống quy tắc có thể lưu các module:

- pricing/discount-policy:2.3.0
- shipping/zone-rules:1.4.1
- fraud/transaction-checks:5.0.0

Ứng dụng yêu cầu một module theo định danh và phiên bản cụ thể. Registry trả về nội dung cùng metadata, chữ ký hoặc checksum. Nhờ đó nhiều dịch vụ có thể dùng chung quy tắc và nhóm vận hành có thể quản lý phát hành tập trung.

Registry cần hỗ trợ phân quyền, lịch sử phiên bản, trạng thái phát hành, tìm kiếm và chính sách lưu giữ. Với các chương trình có ảnh hưởng lớn đến nghiệp vụ, nên có quy trình review và phê duyệt trước khi chuyển phiên bản sang trạng thái production.

### 6.4. Phân phối qua API hoặc dịch vụ điều khiển

Thay vì tải tệp trực tiếp, ứng dụng có thể lấy chương trình DSL qua API. Dịch vụ điều khiển (control plane) quản lý phiên bản, phân quyền và quyết định chương trình nào được dùng ở môi trường nào. Runtime (data plane) tải đúng phiên bản đã được phê duyệt và thực thi.

Mô hình này hữu ích khi có nhiều runtime, cần cập nhật cấu hình tập trung hoặc cần quản lý chính sách theo tenant. Tuy nhiên, nó làm tăng phụ thuộc vào mạng và dịch vụ trung tâm. Cần xác định runtime sẽ làm gì khi registry hoặc control plane tạm thời không truy cập được: tiếp tục dùng bản đã cache, từ chối khởi động hay chuyển sang trạng thái an toàn.

## 7. Kiến trúc tham khảo cho một nền tảng DSL

Một nền tảng DSL dùng chung có thể được tổ chức thành các thành phần sau:

~~~mermaid
flowchart LR
    U["Người viết DSL"] --> E["Editor / CLI / API"]
    E --> S["Source Store"]
    S --> V["Version & Review"]
    V --> C["Compiler Service"]
    C --> A["Artifact Repository"]
    A --> R["Runtime"]
    R --> O["Execution Store / Logs"]
    P["Package Registry"] --> C
    P --> R
    M["Monitoring & Audit"] --- V
    M --- R
~~~

Vai trò của từng thành phần:

- **Editor, CLI hoặc API:** giúp tạo, chỉnh sửa, kiểm tra và gửi chương trình DSL.
- **Source Store:** lưu nội dung nguồn và lịch sử revision.
- **Version & Review:** quản lý phiên bản, trạng thái phê duyệt và quyền phát hành.
- **Compiler Service:** phân tích cú pháp, kiểm tra ngữ nghĩa, giải quyết phụ thuộc và tạo artifact.
- **Artifact Repository:** lưu các artifact bất biến theo định danh, phiên bản và hash.
- **Package Registry:** phân phối compiler, runtime, plugin và thư viện mở rộng.
- **Runtime:** tải artifact đã được phê duyệt và thực thi theo chính sách.
- **Execution Store và Logs:** lưu trạng thái, kết quả và thông tin phục vụ điều tra.
- **Monitoring & Audit:** theo dõi thao tác quản trị, lần phát hành và hành vi thực thi.

Không phải hệ thống nào cũng cần triển khai từng thành phần thành dịch vụ độc lập. Ở quy mô nhỏ, source store, compiler và registry có thể nằm trong cùng một ứng dụng. Khi tải và số nhóm sử dụng tăng, các ranh giới có thể được tách ra để mở rộng độc lập.

## 8. Quy trình từ viết DSL đến runtime

Một quy trình phát hành có kiểm soát có thể gồm các bước:

1. Người dùng tạo hoặc chỉnh sửa chương trình DSL trong editor, IDE hoặc repository.
2. Hệ thống xác thực định dạng, kiểm tra phiên bản ngôn ngữ và các trường bắt buộc.
3. Compiler phân tích cú pháp, kiểm tra kiểu và quy tắc ngữ nghĩa.
4. Hệ thống giải quyết phụ thuộc, tạo artifact và ghi metadata về đầu vào build.
5. Kiểm thử tự động chạy trên chương trình hoặc artifact.
6. Người có thẩm quyền review và phê duyệt phiên bản.
7. Artifact bất biến được phát hành vào registry hoặc repository.
8. Runtime tải đúng artifact và cấu hình đã được phê duyệt.
9. Lần thực thi ghi lại định danh phiên bản, kết quả và thông tin kiểm toán.

Ví dụ pipeline CI/CD cho một DSL có thể được mô tả như sau:

~~~mermaid
flowchart TD
    A["Commit chương trình DSL"] --> B["Lint và validate"]
    B --> C["Compile"]
    C --> D["Unit / Integration tests"]
    D --> E{"Review và approval"}
    E -->|Đạt| F["Publish artifact"]
    E -->|Không đạt| G["Sửa chương trình"]
    G --> A
    F --> H["Deploy hoặc cập nhật runtime"]
    H --> I["Theo dõi và audit"]
~~~

Điểm quan trọng là phiên bản được kiểm thử phải là phiên bản được phát hành. Nếu hệ thống biên dịch lại từ mã nguồn mới nhất tại thời điểm runtime khởi động, chương trình có thể khác với bản đã review. Phát hành artifact bất biến giúp tránh sự sai khác này.

## 9. Quản lý phụ thuộc giữa các module DSL

Một chương trình DSL có thể sử dụng module, hàm, schema hoặc plugin do nhóm khác phát hành. Ví dụ, workflow gọi sales-actions, còn module đó phụ thuộc common-types.

Khi phân phối, cần quản lý:

- Định danh package và phiên bản chính xác.
- Phạm vi phiên bản được chấp nhận.
- Quan hệ phụ thuộc trực tiếp và gián tiếp.
- Quy tắc xử lý khi hai package yêu cầu các phiên bản xung đột.
- Hash của package đã tải.
- Nguồn registry được phép sử dụng.

Với ứng dụng cần tái lập, nên tạo lock file hoặc manifest build ghi lại toàn bộ phiên bản phụ thuộc đã giải quyết. Runtime không nên tự động thay một thư viện bằng phiên bản mới chỉ vì phiên bản đó mới hơn.

Nếu DSL cho phép plugin do bên thứ ba cung cấp, cần xác định plugin chạy trong cùng tiến trình hay trong môi trường cách ly. Plugin chạy cùng tiến trình có thể có quyền truy cập rộng hơn, vì vậy cần kiểm soát nguồn phát hành, chữ ký, quyền được cấp và phiên bản tương thích.

## 10. Bảo mật và tính toàn vẹn khi lưu trữ, phân phối

Chương trình DSL có thể chứa logic ảnh hưởng đến tiền, dữ liệu khách hàng, hạ tầng hoặc quy trình sản xuất. Vì vậy, lưu trữ và phân phối phải có các biện pháp bảo vệ phù hợp.

### 10.1. Xác thực và phân quyền

Không phải người dùng nào cũng được sửa hoặc phát hành mọi chương trình. Có thể phân quyền theo dự án, tenant, môi trường và hành động:

- Đọc chương trình.
- Tạo revision hoặc sửa nội dung.
- Review và phê duyệt.
- Phát hành phiên bản.
- Triển khai vào môi trường production.
- Thu hồi hoặc ngừng sử dụng phiên bản.

Nên áp dụng nguyên tắc quyền tối thiểu. Người có quyền chỉnh sửa nội dung không nhất thiết có quyền triển khai nội dung đó vào production.

### 10.2. Kiểm tra tính toàn vẹn và nguồn gốc

Artifact được tải từ registry cần được kiểm tra hash hoặc chữ ký. Metadata phát hành nên cho biết ai hoặc pipeline nào tạo artifact, từ commit nào, bằng compiler nào và khi nào. Điều này giúp phát hiện artifact bị thay đổi ngoài quy trình.

Package registry nên bảo vệ thông tin xác thực, giới hạn quyền ghi và ghi audit log. Không nên cho phép ghi đè một phiên bản đã phát hành nếu quy ước của hệ thống coi phiên bản là bất biến.

### 10.3. Không lưu bí mật trực tiếp trong DSL

Chương trình DSL thường cần thông tin kết nối hoặc thông tin xác thực. Không nên nhúng mật khẩu, token hay private key trực tiếp vào tệp nguồn hoặc package. Thay vào đó, chương trình tham chiếu đến secret theo tên hoặc định danh; runtime lấy giá trị từ secret manager với quyền được giới hạn.

Ví dụ:

~~~yaml
connection:
  endpoint: https://api.example.internal
  credentialRef: secrets/report-service-token
~~~

Ở đây, DSL chỉ chứa tham chiếu. Giá trị bí mật được cấp tại thời điểm thực thi theo danh tính của runtime. Log và thông báo lỗi cũng cần tránh ghi lộ giá trị bí mật.

### 10.4. Giới hạn khả năng thực thi

Nếu DSL cho phép gọi hàm, plugin, truy cập tệp hoặc mạng, runtime cần áp dụng sandbox hoặc chính sách quyền phù hợp. Một chương trình DSL không nên tự động có toàn bộ quyền của tiến trình máy chủ chỉ vì nó được lưu trong registry đáng tin cậy.

Có thể giới hạn:

- Các hàm và module được phép gọi.
- Thư mục và tài nguyên được phép truy cập.
- Kết nối mạng được phép tạo.
- Thời gian chạy, bộ nhớ và số bước xử lý.
- Số lượng tác vụ đồng thời.

Định nghĩa DSL và chương trình DSL cũng cần được kiểm tra đầu vào. Không nên coi một chương trình hợp lệ về cú pháp là an toàn để thực thi.

## 11. Tính tái lập, khôi phục và vận hành

Một lần thực thi cần có đủ thông tin để xác định chính xác chương trình và môi trường đã tạo ra kết quả. Metadata thường gồm:

| Trường | Mục đích |
|---|---|
| Program ID và revision | Xác định chương trình cụ thể |
| Language version | Chọn đúng quy tắc cú pháp và ngữ nghĩa |
| Compiler/runtime version | Xác định cách phân tích hoặc thực thi |
| Dependency lock | Xác định các thư viện và plugin |
| Artifact hash | Kiểm tra artifact có đúng bản đã phát hành |
| Environment ID | Xác định môi trường thực thi |
| Execution ID và timestamp | Tra cứu một lần chạy cụ thể |

Khi cần rollback, hệ thống nên có thể trỏ runtime về một artifact đã phát hành trước đó. Rollback cần bao gồm các phụ thuộc tương thích, cấu hình môi trường và chính sách dữ liệu liên quan. Chỉ đổi mã chương trình mà bỏ qua thay đổi schema hoặc dữ liệu có thể không đủ để khôi phục hành vi cũ.

Với hệ thống có nhiều runtime, có thể dùng chiến lược triển khai theo từng nhóm:

- Canary: phát hành cho một tỷ lệ nhỏ runtime hoặc người dùng trước.
- Rolling update: cập nhật lần lượt các nhóm runtime.
- Blue-green: duy trì hai môi trường và chuyển lưu lượng sau khi kiểm tra.

Việc chọn chiến lược tùy mức ảnh hưởng của DSL, khả năng chạy song song nhiều phiên bản và yêu cầu gián đoạn dịch vụ.

## 12. Ví dụ cấu trúc một package DSL

Một package phân phối ngôn ngữ hoặc module có thể có cấu trúc:

~~~text
monthly-report-dsl/
├── manifest.yaml
├── grammar/
│   └── ReportDsl.g4
├── schema/
│   └── report.schema.json
├── libraries/
│   └── report-functions/
├── examples/
│   ├── monthly-report.dsl
│   └── quarterly-report.dsl
├── tests/
│   ├── valid/
│   └── invalid/
├── docs/
│   └── usage.md
└── artifacts/
    └── compiler-output/
~~~

Ví dụ manifest:

~~~yaml
package:
  name: monthly-report-dsl
  version: 1.4.0
  languageVersion: "2.1"
  compilerCompatibility: ">=3.2.0 <4.0.0"

dependencies:
  - name: common-report-types
    version: "2.0.1"

artifacts:
  grammar: grammar/ReportDsl.g4
  schema: schema/report.schema.json
~~~

Manifest giúp package manager hoặc compiler hiểu định danh package, phiên bản, tương thích và phụ thuộc. Đây là ví dụ minh họa; cấu trúc và tên trường thực tế phụ thuộc vào hệ sinh thái DSL được xây dựng.

Trong nhiều dự án, không nên đưa thư mục build tạm hoặc cache vào package nguồn. Chỉ phát hành các tệp cần thiết để sử dụng, kiểm tra hoặc tái tạo artifact. Nếu package chứa mã thực thi, cần kiểm tra nguồn gốc và quyền của mã trước khi cho phép cài đặt.

## 13. Lựa chọn mô hình lưu trữ và phân phối

Không có một kiến trúc duy nhất phù hợp với mọi DSL. Có thể chọn theo quy mô và cách sử dụng:

| Tình huống | Cách lưu trữ và phân phối phù hợp | Điểm cần quan tâm |
|---|---|---|
| DSL chỉ dùng trong một ứng dụng | Lưu tệp cùng repository; đóng gói compiler/runtime cùng ứng dụng | Đồng bộ phiên bản với bản phát hành ứng dụng |
| Nhiều nhóm cùng phát triển DSL | Git cho mã nguồn; package registry cho compiler và thư viện | Review, quyền truy cập và tương thích |
| Người dùng nghiệp vụ chỉnh sửa quy tắc | Source store hoặc database có revision; registry phát hành bản đã duyệt | Phân quyền, audit và rollback |
| Nhiều runtime cần dùng chung cấu hình | Registry hoặc API phân phối phiên bản bất biến | Cache, tính sẵn sàng và chính sách khi mất kết nối |
| DSL tạo artifact lớn hoặc build tốn thời gian | Object storage hoặc artifact repository; cache theo hash đầu vào | Tái lập build và dọn dẹp artifact hết hạn |
| Nhiều tenant hoặc môi trường | Kho dùng chung có phân vùng quyền, namespace và phiên bản theo tenant | Cách ly dữ liệu và kiểm soát phát hành |

Một kiến trúc có thể kết hợp nhiều cách. Chẳng hạn, mã nguồn được quản lý trong Git, compiler được phát hành qua Maven repository, chương trình người dùng được lưu trong database, artifact được lưu trong object storage và runtime lấy phiên bản đã phê duyệt qua API.

## 14. Các lỗi thường gặp

### Không ghi lại phiên bản ngôn ngữ

Khi chương trình chỉ lưu nội dung mà không ghi phiên bản DSL, runtime có thể diễn giải cùng một tệp theo quy tắc mới và tạo ra hành vi khác. Hãy lưu language version hoặc metadata tương đương cùng revision.

### Dùng bản mới nhất trong production

Nếu runtime luôn tải latest, một lần phát hành package có thể làm thay đổi hành vi mà không có lần review tương ứng. Hãy ghim phiên bản cụ thể và phát hành thay đổi qua quy trình có kiểm soát.

### Chỉ lưu AST hoặc bytecode

Nếu không giữ mã nguồn hoặc một biểu diễn chuẩn có thể chỉnh sửa, việc xem lại ý định ban đầu, diff và migration sẽ khó khăn. Hãy xác định rõ nguồn dữ liệu chuẩn và chính sách lưu giữ.

### Cache không gắn với phiên bản compiler

Cache được tạo bởi compiler cũ có thể không hợp lệ với compiler mới. Cache key cần bao gồm các phiên bản và phụ thuộc ảnh hưởng đến kết quả.

### Ghi đè artifact đã phát hành

Hai artifact cùng tên và phiên bản nhưng nội dung khác nhau làm mất khả năng tái lập. Nên coi artifact đã phát hành là bất biến; thay đổi nội dung phải tạo phiên bản mới.

### Không có lịch sử và audit

Khi quy tắc thay đổi, nhóm vận hành cần biết ai sửa, ai duyệt, phiên bản nào được triển khai và lần chạy nào chịu ảnh hưởng. Hãy lưu revision và sự kiện quan trọng theo chính sách kiểm toán.

### Phân phối plugin mà không kiểm soát quyền

Plugin có thể chạy mã tùy ý trong tiến trình. Cần xác minh nguồn gốc, giới hạn quyền, kiểm tra tương thích và cách ly nếu plugin đến từ bên ngoài.

## 15. Hướng dẫn thiết kế theo từng bước

Khi thiết kế cơ chế lưu trữ và phân phối cho một DSL mới, có thể đi theo trình tự:

1. **Liệt kê hiện vật.** Phân biệt định nghĩa ngôn ngữ, chương trình DSL, thư viện, artifact biên dịch và dữ liệu thực thi.
2. **Chọn nguồn dữ liệu chuẩn.** Xác định mã nguồn, mô hình cấu trúc hay tài liệu có revision là dữ liệu gốc.
3. **Chọn kho lưu trữ.** Cân nhắc Git, database, object storage hoặc package registry theo cách tạo và sử dụng dữ liệu.
4. **Thiết kế định danh và phiên bản.** Ghi rõ language version, compiler version, package version và program revision.
5. **Quyết định phần nào được cache.** Xác định AST hoặc artifact nào có thể tạo lại và điều kiện vô hiệu hóa cache.
6. **Chọn kênh phân phối.** Đóng gói cùng ứng dụng, dùng package manager, registry hoặc API tùy số lượng runtime và nhóm sử dụng.
7. **Thiết lập quy trình phát hành.** Kiểm tra, biên dịch, kiểm thử, review, phê duyệt rồi phát hành artifact bất biến.
8. **Bảo vệ dữ liệu và thực thi.** Áp dụng xác thực, phân quyền, chữ ký, quản lý secret, sandbox và audit.
9. **Thiết kế rollback và khôi phục.** Giữ phiên bản trước, metadata build và khả năng truy lại chương trình đã chạy.
10. **Theo dõi vận hành.** Ghi nhận thời gian tải, lỗi tương thích, lỗi biên dịch, cache hit, lần chạy và trạng thái phát hành.

## 16. Kết luận

Lưu trữ và phân phối là phần thiết yếu của kiến trúc DSL khi ngôn ngữ được sử dụng trong hệ thống thực tế. Cần phân biệt mã nguồn, định nghĩa ngôn ngữ, dữ liệu trung gian, artifact và dữ liệu vận hành; mỗi loại có vòng đời và yêu cầu lưu trữ riêng. Mã nguồn hoặc mô hình chuẩn phải được quản lý phiên bản, còn AST và artifact dẫn xuất cần gắn với compiler, grammar và phụ thuộc đã tạo ra chúng.

Một cơ chế phân phối tốt cung cấp đúng phiên bản compiler, runtime, thư viện và chương trình cho môi trường đích. Registry, package manager, API và pipeline CI/CD giúp phát hành có kiểm soát. Chữ ký, phân quyền, quản lý secret, sandbox, audit và khả năng rollback giúp bảo vệ tính toàn vẹn cũng như độ an toàn của hệ thống.

Khi thiết kế kiến trúc DSL, hãy xác định dữ liệu nào là nguồn chuẩn, phiên bản nào quyết định cách diễn giải, artifact được tạo và phân phối ra sao, và runtime sẽ làm gì khi phụ thuộc hoặc dịch vụ phân phối không sẵn sàng. Những quyết định này tạo nền tảng để DSL có thể được phát triển, triển khai và vận hành lâu dài.
