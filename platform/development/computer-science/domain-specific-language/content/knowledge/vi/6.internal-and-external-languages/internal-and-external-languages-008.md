# So sánh chi phí công cụ

Khi lựa chọn cách triển khai một DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền), chi phí công cụ là một phần quan trọng của quyết định. Một DSL có thể được nhúng vào ngôn ngữ lập trình chủ (*internal/embedded DSL*) hoặc được xây dựng như ngôn ngữ độc lập (*external DSL*). Hai cách này tạo ra những nhu cầu khác nhau về parser, compiler, IDE, kiểm tra lỗi, tài liệu, tích hợp và bảo trì.

Không nên chỉ so sánh chi phí viết cú pháp ban đầu. Cần tính cả chi phí để người dùng tạo, đọc, kiểm tra, chạy, gỡ lỗi, nâng cấp và duy trì các chương trình DSL trong suốt vòng đời hệ thống.

## 1. Hai hình thức DSL và bộ công cụ đi kèm

### 1.1. DSL nhúng (internal hoặc embedded DSL)

DSL nhúng được biểu diễn bên trong một ngôn ngữ chủ (*host language*) như Kotlin, Java, Scala, Ruby hoặc Python. Nó tận dụng cú pháp, hàm, đối tượng, kiểu dữ liệu và công cụ phát triển của ngôn ngữ chủ để tạo cách diễn đạt phù hợp với miền.

Ví dụ, Gradle Kotlin DSL cho phép khai báo tác vụ build bằng Kotlin:

```kotlin
tasks.register("compileApp") {
    doLast {
        println("Compiling application")
    }
}
```

Người dùng viết một cấu trúc hướng đến miền build, nhưng vẫn dùng cú pháp Kotlin. Parser, compiler, hệ thống kiểu và phần lớn hỗ trợ IDE đến từ hệ sinh thái Kotlin và Gradle.

Một bộ công cụ cho DSL nhúng thường gồm:

- Ngôn ngữ chủ, compiler hoặc runtime của ngôn ngữ đó.
- Thư viện/API cung cấp từ vựng và hành vi của miền.
- IDE, formatter, debugger và công cụ kiểm tra của ngôn ngữ chủ.
- Bộ kiểm thử cho các quy tắc nghiệp vụ được cài đặt trong thư viện DSL.
- Công cụ build, quản lý dependency và phát hành phiên bản.

Nhà phát triển DSL vẫn phải thiết kế API, bảo vệ quy tắc miền, viết tài liệu và duy trì tương thích. Tuy nhiên, họ thường không cần tự xây dựng một parser hoàn chỉnh cho cú pháp mới.

### 1.2. DSL bên ngoài (external DSL)

DSL bên ngoài có cú pháp độc lập với ngôn ngữ lập trình chủ. Người dùng viết chương trình bằng một ngôn ngữ riêng, thường lưu trong tệp có phần mở rộng riêng hoặc được nạp vào một công cụ chuyên biệt.

Ví dụ, một DSL cấu hình triển khai giả định có thể viết:

```text
service "catalog" {
    replicas = 3
    region = "asia-southeast1"
    expose port 8080
}
```

Đây là cú pháp minh họa, không phải cú pháp của một sản phẩm cụ thể. Công cụ của DSL phải đọc tệp, phân tích cấu trúc, kiểm tra trường và quy tắc miền, sau đó tạo kế hoạch hoặc cấu hình cho nền tảng đích.

Một bộ công cụ cho DSL bên ngoài thường gồm:

- Đặc tả grammar và lexer/parser hoặc framework phân tích cú pháp.
- AST, bộ phân tích ngữ nghĩa, kiểm tra kiểu hoặc validator.
- Interpreter, runtime, compiler hoặc code generator.
- Thông báo lỗi, formatter, syntax highlighting và hỗ trợ IDE.
- Công cụ kiểm thử, tài liệu, quản lý phiên bản và cơ chế tương thích.
- Cách tích hợp với ngôn ngữ chủ, hệ thống build và môi trường triển khai nếu cần.

Không phải DSL bên ngoài nào cũng cần một compiler lớn. Một tệp cấu hình đơn giản có thể dùng parser có sẵn cho JSON, YAML hoặc TOML rồi thêm bước kiểm tra schema. Chi phí phụ thuộc vào mức độ riêng biệt và độ phức tạp của ngôn ngữ.

## 2. Các nhóm chi phí cần so sánh

Chi phí công cụ có thể được chia thành nhiều nhóm. Một lựa chọn rẻ ở giai đoạn đầu có thể tạo ra chi phí lớn hơn khi số người dùng, số chương trình và số môi trường triển khai tăng lên.

### 2.1. Chi phí thiết kế và xây dựng ban đầu

Với DSL nhúng, phần tốn công thường là thiết kế API có từ vựng rõ ràng, tổ chức các abstraction, xử lý kiểu và bảo vệ quy tắc miền. Nhóm phát triển cần tránh tạo ra một tập hàm rời rạc khó đọc hoặc một API phụ thuộc quá nhiều vào chi tiết của ngôn ngữ chủ.

Với DSL bên ngoài, nhóm cần xác định grammar, quy tắc cú pháp, AST, cách phân giải tên, kiểm tra ngữ nghĩa và đường đi đến runtime hoặc backend. Nếu cú pháp phức tạp, việc xây dựng parser, thông báo lỗi và các công cụ hỗ trợ có thể chiếm phần đáng kể công sức.

| Hạng mục ban đầu | DSL nhúng | DSL bên ngoài |
|---|---|---|
| Cú pháp | Tận dụng ngôn ngữ chủ; thiết kế API và cấu trúc lời gọi | Đặc tả và duy trì grammar riêng |
| Parser | Thường dùng parser của ngôn ngữ chủ | Cần parser riêng hoặc parser của định dạng nền |
| Kiểu dữ liệu | Có thể tận dụng hệ kiểu của ngôn ngữ chủ | Cần xác định và kiểm tra kiểu theo khả năng DSL |
| Ngữ nghĩa miền | Cài đặt trong thư viện/API | Cài đặt trong semantic analyzer, validator hoặc runtime |
| Thực thi | Thường chạy qua runtime của ngôn ngữ chủ và thư viện DSL | Cần interpreter, code generator hoặc engine phù hợp |
| IDE ban đầu | Có thể dùng IDE của ngôn ngữ chủ | Cần cấu hình hoặc xây dựng hỗ trợ riêng |

DSL nhúng thường có lợi thế khi nhóm đã quen ngôn ngữ chủ và công cụ hiện có. DSL bên ngoài có thể cần đầu tư ban đầu lớn hơn, đặc biệt khi muốn có trải nghiệm phát triển hoàn chỉnh. Tuy nhiên, nếu DSL bên ngoài chỉ là một schema nhỏ dựa trên định dạng chuẩn, chi phí ban đầu có thể rất thấp.

### 2.2. Chi phí công cụ cho người viết DSL

Người viết cần một môi trường để tạo, định dạng, kiểm tra và gỡ lỗi chương trình.

Với DSL nhúng, họ thường cần cài đặt ngôn ngữ chủ, SDK, thư viện, plugin IDE và công cụ build. Khi môi trường đó đã có sẵn trong tổ chức, chi phí bổ sung có thể thấp. Nếu người dùng chỉ là chuyên gia nghiệp vụ không quen lập trình, yêu cầu học ngôn ngữ chủ có thể làm tăng chi phí đào tạo.

Với DSL bên ngoài, người viết có thể chỉ cần một trình soạn thảo văn bản nếu cú pháp đơn giản. Tuy nhiên, để có trải nghiệm tốt, nhóm thường phải cung cấp syntax highlighting, gợi ý, kiểm tra lỗi trực tiếp, formatter, tài liệu cú pháp và công cụ chạy thử. Nếu thiếu các công cụ đó, lỗi chỉ xuất hiện khi chạy và việc tìm nguyên nhân có thể tốn thời gian.

### 2.3. Chi phí parser, kiểm tra và chẩn đoán lỗi

DSL nhúng thường nhận được lỗi cú pháp và lỗi kiểu từ compiler của ngôn ngữ chủ. Ví dụ, IDE có thể phát hiện sai kiểu đối số hoặc tên hàm không tồn tại. Tuy vậy, quy tắc nghiệp vụ vẫn cần được kiểm tra trong thư viện DSL; compiler không tự hiểu rằng một tài nguyên chỉ được phép có một vùng triển khai.

DSL bên ngoài cần xác định rõ các lớp lỗi:

- Lỗi từ vựng, như ký tự hoặc chuỗi không hợp lệ.
- Lỗi cú pháp, như thiếu dấu đóng hoặc sai thứ tự khai báo.
- Lỗi ngữ nghĩa, như tham chiếu đến tài nguyên không tồn tại.
- Lỗi kiểu hoặc quy tắc miền, như truyền sai loại giá trị hoặc vi phạm điều kiện nghiệp vụ.
- Lỗi khi thực thi, như dịch vụ đích từ chối cấu hình.

Parser generator và framework có thể giảm công sức xây dựng parser, nhưng không tự động giải quyết mọi vấn đề ngữ nghĩa, thông báo lỗi thân thiện hoặc tích hợp IDE. Cần tính chi phí để duy trì toàn bộ trải nghiệm kiểm tra và chẩn đoán.

### 2.4. Chi phí IDE và trải nghiệm phát triển

IDE có thể cung cấp tô màu cú pháp, tự hoàn thành, điều hướng đến khai báo, kiểm tra lỗi, định dạng và tái cấu trúc mã.

DSL nhúng được hưởng lợi từ hỗ trợ ngôn ngữ chủ, nhưng đôi khi cấu trúc DSL bị giới hạn bởi cú pháp của host language. Gợi ý mã có thể tốt ở cấp hàm và kiểu, nhưng không phải lúc nào cũng hiểu được ngữ cảnh nghiệp vụ.

DSL bên ngoài có thể tạo trải nghiệm gần với chuyên gia miền hơn, nhưng cần plugin hoặc Language Server Protocol (LSP) để cung cấp những tính năng như completion, diagnostics, hover và go-to-definition. Việc xây dựng một language server chất lượng có thể là khoản đầu tư đáng kể.

Không nhất thiết phải xây dựng mọi tính năng IDE ngay từ đầu. Một formatter, validator dòng lệnh và thông báo lỗi có vị trí nguồn tốt đôi khi đã đủ cho DSL nhỏ.

### 2.5. Chi phí tích hợp và triển khai

DSL nhúng thường tích hợp trực tiếp với chương trình của ngôn ngữ chủ. Nó có thể gọi thư viện, dùng kiểu miền, truy cập hệ thống logging, kiểm thử và quản lý dependency hiện có. Đổi lại, ứng dụng phải quản lý phiên bản host language và thư viện DSL tương thích với nhau.

DSL bên ngoài cần một đường tích hợp: ứng dụng đọc tệp DSL, gọi công cụ xử lý, nhận IR hoặc kết quả rồi chuyển tiếp đến hệ thống đích. Nếu DSL sinh mã, cần quản lý mã sinh và toolchain đích. Nếu DSL có runtime riêng, cần đóng gói, triển khai và giám sát runtime đó.

Các chi phí tích hợp có thể gồm:

- Kết nối với hệ thống build, CI/CD và quản lý cấu hình.
- Phân phối compiler, CLI, runtime hoặc plugin.
- Quản lý credential, quyền truy cập và môi trường chạy.
- Tương thích với API và dịch vụ bên ngoài.
- Quan sát, logging, tracing và xử lý lỗi khi thực thi.

### 2.6. Chi phí bảo trì và nâng cấp

DSL nhúng chịu ảnh hưởng từ vòng đời của ngôn ngữ chủ, compiler, thư viện và framework. Khi host language thay đổi cú pháp hoặc hệ kiểu, DSL có thể cần điều chỉnh API và ví dụ. Khi thư viện miền thay đổi, các chương trình DSL hiện có có thể cần nâng cấp dependency.

DSL bên ngoài có quyền kiểm soát grammar và ngữ nghĩa riêng, nhưng nhóm phải tự duy trì tương thích. Thay đổi cú pháp, kiểu hoặc ý nghĩa của một câu lệnh có thể làm hỏng tệp cấu hình đã được triển khai ở nhiều nơi. Cần chính sách phiên bản, deprecation, migration và kiểm thử tương thích.

Trong cả hai hình thức, chi phí bảo trì còn bao gồm sửa lỗi, cập nhật tài liệu, đào tạo người dùng, hỗ trợ môi trường mới và duy trì các ví dụ thực tế.

## 3. Bảng so sánh tổng thể

| Tiêu chí | DSL nhúng | DSL bên ngoài |
|---|---|---|
| Tận dụng công cụ sẵn có | Cao nếu host language đã được tổ chức sử dụng | Phụ thuộc định dạng, parser framework và công cụ riêng |
| Chi phí xây dựng parser | Thường thấp vì dùng parser host | Thường cao hơn nếu có grammar riêng |
| Kiểm tra kiểu | Có thể tận dụng hệ kiểu host | Cần thiết kế kiểm tra kiểu riêng hoặc dùng schema |
| IDE và refactoring | Thường có nền tảng tốt từ host IDE | Cần đầu tư plugin/LSP hoặc chấp nhận hỗ trợ hạn chế |
| Tự do thiết kế cú pháp | Bị giới hạn bởi host language | Cao hơn, có thể thiết kế sát ngôn ngữ miền |
| Đối tượng người dùng | Thuận tiện cho lập trình viên quen host language | Có thể phù hợp hơn với chuyên gia miền nếu cú pháp được thiết kế tốt |
| Tích hợp với ứng dụng | Thường trực tiếp trong cùng runtime | Thường cần parser/runtime/CLI hoặc giao diện tích hợp |
| Phụ thuộc nền tảng | Phụ thuộc host language và thư viện | Phụ thuộc parser, runtime và công cụ riêng |
| Kiểm soát phiên bản ngôn ngữ | Chia sẻ nhiều quy tắc tương thích với host | Chủ động định nghĩa phiên bản DSL và migration |
| Chi phí dài hạn | Tăng theo phụ thuộc host và độ phức tạp API | Tăng theo số công cụ riêng và cam kết tương thích |

Đây là xu hướng, không phải kết luận cố định. Một DSL bên ngoài dựa trên YAML và JSON Schema có thể rẻ hơn một DSL nhúng có API phức tạp. Ngược lại, một DSL bên ngoài có grammar riêng, nhiều backend và IDE chuyên dụng có thể cần đội ngũ duy trì đáng kể.

## 4. Ví dụ so sánh cùng một bài toán

Giả sử nhóm phát triển cần mô tả tác vụ build gồm hai bước: biên dịch ứng dụng và đóng gói sản phẩm. Có thể biểu diễn theo hai cách.

### 4.1. Dùng DSL nhúng

Ví dụ Kotlin DSL:

```kotlin
tasks.register("packageApp") {
    dependsOn("compileApp")
    doLast {
        println("Packaging application")
    }
}
```

Nhóm có thể tận dụng compiler Kotlin, Gradle, IDE và cơ chế dependency. Chi phí riêng tập trung vào việc thiết kế các task, plugin và quy tắc build của dự án. Người viết cần hiểu Kotlin DSL và mô hình Gradle.

### 4.2. Dùng DSL bên ngoài

Ví dụ cú pháp giả định:

```text
task "packageApp" {
    depends_on "compileApp"
    run "package-command"
}
```

Để thực thi, nhóm phải có công cụ đọc tệp, phân tích các khai báo, kiểm tra tên task, xây dựng đồ thị phụ thuộc và chạy lệnh tương ứng. Một CLI nhỏ có thể đủ cho bản đầu tiên. Nếu muốn hỗ trợ completion, diagnostics trực tiếp và tài liệu tương tác, cần đầu tư thêm công cụ.

### 4.3. Nhìn vào chi phí trong tình huống này

Nếu toàn bộ người dùng là lập trình viên đã sử dụng Gradle và Kotlin, DSL nhúng thường tận dụng tốt công cụ sẵn có. Nếu người dùng là nhóm vận hành hoặc chuyên gia build chỉ cần mô tả tác vụ bằng một cú pháp rất nhỏ, DSL bên ngoài có thể giảm phần kiến thức host language phải học, nhưng tổ chức cần chịu chi phí xây dựng và vận hành công cụ riêng.

Điểm quyết định không chỉ là số dòng cú pháp. Cần tính tổng thời gian của người xây dựng DSL, người viết cấu hình, người sửa lỗi và nhóm chịu trách nhiệm duy trì công cụ.

## 5. Tổng chi phí sở hữu (TCO) của công cụ DSL

Để so sánh thực tế, có thể dùng mô hình tổng chi phí sở hữu (*Total Cost of Ownership – TCO*) trong một khoảng thời gian xác định.

Một cách biểu diễn đơn giản:

```text
TCO = C_build
    + C_tooling
    + C_training
    + C_integration
    + C_operations
    + C_maintenance
    + C_migration
```

Trong đó:

- `C_build`: chi phí thiết kế và xây dựng DSL, thư viện, parser hoặc runtime.
- `C_tooling`: chi phí IDE, formatter, validator, debugger, CLI và tài liệu công cụ.
- `C_training`: chi phí đào tạo và thời gian người dùng làm quen.
- `C_integration`: chi phí kết nối với ứng dụng, CI/CD, hệ thống và nền tảng đích.
- `C_operations`: chi phí đóng gói, triển khai, giám sát và hỗ trợ khi chạy.
- `C_maintenance`: chi phí sửa lỗi, cập nhật dependency, bảo trì công cụ và hỗ trợ người dùng.
- `C_migration`: chi phí thay đổi phiên bản, chuyển đổi cú pháp và duy trì tương thích.

Đây là mô hình ước lượng, không phải công thức kế toán bắt buộc. Một nhóm có thể bổ sung chi phí giấy phép, hạ tầng, hỗ trợ nhà cung cấp hoặc rủi ro gián đoạn nếu chúng có ý nghĩa trong dự án.

### 5.1. Ước lượng bằng thời gian và nguồn lực

Đối với dự án nội bộ, có thể ước lượng mỗi nhóm chi phí bằng số giờ công nhân với chi phí trung bình theo vai trò. Ví dụ, chi phí thiết kế parser, xây dựng language server và đào tạo người dùng nên được ước lượng riêng vì cần kỹ năng và thời gian khác nhau.

Không nên chỉ tính giờ của nhóm xây dựng công cụ. Nếu DSL giúp người dùng viết cấu hình nhanh hơn, lợi ích đó cũng cần được đo; ngược lại, nếu người dùng phải học một ngôn ngữ mới hoặc chờ công cụ sửa lỗi, chi phí vận hành hằng ngày cần được tính vào.

### 5.2. So sánh theo quy mô sử dụng

Một DSL chỉ có ba người dùng và vài chục tệp cấu hình có thể không cần IDE riêng. Khi có hàng trăm người dùng và hàng nghìn cấu hình, chi phí thiếu formatter, validator và migration có thể tăng mạnh.

Vì vậy, TCO cần gắn với quy mô dự kiến:

- Số người viết và số người đọc DSL.
- Số chương trình hoặc tệp cấu hình đang được duy trì.
- Số dự án và môi trường cần hỗ trợ.
- Số backend hoặc nền tảng đích.
- Tần suất thay đổi cú pháp và quy tắc miền.
- Thời gian hỗ trợ và xử lý sự cố.

## 6. Những yếu tố làm thay đổi lựa chọn chi phí

### 6.1. Mức độ quen thuộc với ngôn ngữ chủ

Nếu tổ chức đã có compiler, IDE, quy trình build và đội ngũ thành thạo một ngôn ngữ, DSL nhúng có thể tận dụng khoản đầu tư hiện hữu. Nếu người dùng không biết ngôn ngữ chủ, chi phí đào tạo và hỗ trợ có thể xóa đi lợi thế đó.

### 6.2. Mức độ chuyên biệt của cú pháp

Nếu miền chỉ cần một số cấu trúc đơn giản, DSL nhúng hoặc schema trên định dạng chuẩn có thể đủ. Nếu miền cần cách diễn đạt rất khác với host language, DSL bên ngoài có thể đem lại trải nghiệm tốt hơn dù tốn chi phí công cụ.

### 6.3. Số lượng backend

Nếu chỉ chạy trong một ứng dụng dùng host language, DSL nhúng thường dễ tích hợp. Nếu cùng một mô tả cần chạy trên nhiều nền tảng, IR và backend độc lập của DSL bên ngoài có thể giúp tách phần mô tả khỏi môi trường thực thi. Tuy nhiên, việc hỗ trợ nhiều backend cũng tạo chi phí kiểm thử và tương thích.

### 6.4. Yêu cầu kiểm soát và an toàn

DSL bên ngoài có thể giới hạn tập lệnh và thao tác được phép, phù hợp với cấu hình hoặc quy tắc do nhiều nhóm cung cấp. Nhưng nếu DSL cho phép gọi mã tùy ý hoặc plugin không tin cậy, runtime vẫn cần kiểm soát quyền, tài nguyên và sandbox.

DSL nhúng chạy trong ngôn ngữ chủ có thể truy cập nhiều khả năng của host. Điều này thuận tiện cho lập trình viên, nhưng cần thiết kế API và quyền truy cập cẩn thận nếu người viết DSL không được phép thực hiện mọi thao tác của ứng dụng.

### 6.5. Yêu cầu về vòng đời và tương thích

Nếu cấu hình được lưu lâu dài, được chia sẻ giữa nhiều tổ chức hoặc cần tái hiện sau nhiều năm, chi phí quản lý phiên bản trở nên quan trọng. DSL bên ngoài cần migration cho grammar và schema; DSL nhúng cần quản lý phiên bản thư viện và host language. Cả hai đều cần kiểm thử các chương trình cũ khi nâng cấp.

## 7. Chiến lược giảm chi phí công cụ

Không nhất thiết phải xây dựng một bộ công cụ hoàn chỉnh ngay từ đầu. Có thể triển khai theo từng mức nhu cầu.

### 7.1. Tận dụng định dạng và công cụ có sẵn

Nếu nhu cầu chủ yếu là cấu hình, hãy xem xét JSON, YAML hoặc TOML cùng schema validator. Nếu nhu cầu là truy vấn, có thể dùng SQL hoặc một thư viện truy vấn hiện có. Nếu DSL nhúng đã có IDE tốt, hãy tận dụng formatter, debugger và hệ thống kiểm tra của host language.

### 7.2. Xây dựng công cụ tối thiểu có giá trị

Với DSL bên ngoài, bản đầu tiên có thể chỉ cần parser, validator, CLI và thông báo lỗi có vị trí nguồn. Khi có nhu cầu thực tế, mới bổ sung formatter, LSP, debugger hoặc công cụ trực quan.

Với DSL nhúng, nên bắt đầu từ một API nhỏ, có kiểu rõ ràng và tài liệu tốt. Tránh xây dựng một lớp trừu tượng lớn trước khi biết người dùng thực sự cần những cấu trúc nào.

### 7.3. Tái sử dụng parser generator hoặc framework

Nếu cần grammar riêng, parser generator hoặc framework parsing có thể giảm công sức xử lý token và cú pháp. Cần tính cả thời gian học framework, phụ thuộc phiên bản, chất lượng thông báo lỗi và khả năng tích hợp công cụ.

### 7.4. Dùng schema và metadata để tự động hóa

Từ schema của DSL, hệ thống có thể sinh tài liệu, completion, kiểm tra trường và mẫu cấu hình. Cách này giúp giảm trùng lặp giữa grammar, validator, tài liệu và IDE. Tuy nhiên, schema cần đủ biểu đạt các quy tắc thực tế; những quy tắc phức tạp vẫn cần logic riêng.

### 7.5. Quản lý phiên bản ngay từ đầu

Định nghĩa cách đánh phiên bản, deprecation, migration và thông báo lỗi khi gặp cú pháp cũ. Điều này giảm chi phí nâng cấp hàng loạt và giúp nhóm tránh những thay đổi phá vỡ không được kiểm soát.

### 7.6. Đo chi phí sử dụng thực tế

Theo dõi thời gian người dùng viết một cấu hình, số lỗi trước khi chạy, thời gian tìm nguyên nhân, số lần cần hỗ trợ và thời gian nâng cấp. Dữ liệu này giúp xác định khoản đầu tư công cụ nào đem lại hiệu quả rõ nhất.

## 8. Chọn DSL nhúng hay DSL bên ngoài theo tình huống

| Tình huống | Hướng thường phù hợp | Lý do |
|---|---|---|
| DSL chỉ dùng bởi lập trình viên của một ứng dụng | DSL nhúng | Tận dụng host language, kiểu và IDE hiện có |
| Cần mô tả quy tắc nghiệp vụ bằng cú pháp riêng | DSL bên ngoài | Có thể thiết kế từ vựng gần với chuyên gia miền |
| Chỉ cần cấu hình tài nguyên với vài trường | Định dạng chuẩn + schema | Giảm chi phí xây parser và công cụ riêng |
| Cần nhiều backend cho cùng một mô tả | DSL bên ngoài có IR hoặc kiến trúc tách backend | Giảm phụ thuộc mô tả vào một runtime cụ thể |
| Người dùng đã quen một ngôn ngữ và framework | DSL nhúng | Chi phí đào tạo và triển khai thấp hơn |
| Cần giới hạn mạnh các thao tác được phép | DSL bên ngoài hoặc API nhúng được giới hạn | Có thể định nghĩa bề mặt thao tác nhỏ, kiểm soát rõ |

Các lựa chọn trên là gợi ý ban đầu. Cần xác nhận bằng quy mô người dùng, độ phức tạp miền, kỹ năng của nhóm và chi phí bảo trì dự kiến.

## 9. Quy trình đánh giá chi phí cho một dự án

Một quy trình thực tế có thể gồm các bước:

1. **Xác định người dùng và công việc:** ai sẽ viết DSL, họ cần mô tả những quy tắc nào và tần suất sử dụng ra sao?
2. **Xác định mức độ riêng của ngôn ngữ:** có thể dùng API, schema hoặc định dạng có sẵn hay cần grammar riêng?
3. **Liệt kê công cụ cần có:** parser, validator, IDE, formatter, debugger, CLI, runtime, backend và tài liệu.
4. **Đánh giá tài sản hiện có:** host language, IDE, framework, parser generator, CI/CD và đội ngũ có thể tái sử dụng đến đâu?
5. **Ước lượng TCO theo vòng đời:** tính xây dựng, đào tạo, tích hợp, vận hành, bảo trì và migration trong cùng một khoảng thời gian.
6. **Làm thử một lát cắt nhỏ:** triển khai một trường hợp sử dụng đại diện ở cả hai hướng nếu chưa rõ lựa chọn.
7. **Đo kết quả:** so sánh thời gian viết, số lỗi, thời gian debug, công sức nâng cấp và mức độ hài lòng của người dùng.
8. **Chọn phương án và xác định lộ trình:** bắt đầu với mức công cụ cần thiết, ghi rõ trách nhiệm bảo trì và điều kiện xem xét mở rộng.

Một thử nghiệm nhỏ có thể phát hiện chi phí ẩn mà ước lượng trên giấy không thể hiện, chẳng hạn việc IDE không hỗ trợ completion cho cú pháp nhúng hoặc việc DSL bên ngoài cần quá nhiều công sức để tạo thông báo lỗi dễ hiểu.

## 10. Những hiểu nhầm thường gặp

**DSL nhúng không miễn phí công cụ.** Nó tận dụng parser, compiler và IDE của host language, nhưng vẫn cần API miền, tài liệu, kiểm thử, versioning và bảo trì.

**DSL bên ngoài không luôn đắt hơn.** Nếu dựa trên định dạng phổ biến và schema đơn giản, chi phí có thể thấp. Chi phí tăng khi cần cú pháp riêng, nhiều backend và trải nghiệm IDE đầy đủ.

**Có parser không đồng nghĩa có công cụ DSL hoàn chỉnh.** Người dùng còn cần kiểm tra ngữ nghĩa, thông báo lỗi, tài liệu, formatter, khả năng chạy thử và cách nâng cấp.

**Chi phí ban đầu thấp không bảo đảm TCO thấp.** Một API dễ viết nhưng khó đọc hoặc một tệp cấu hình thiếu validator có thể làm tăng thời gian hỗ trợ và xử lý sự cố.

**Không phải mọi DSL đều cần IDE riêng.** Công cụ nên được đầu tư theo nhu cầu và quy mô. CLI cùng validator tốt có thể đủ cho một DSL nhỏ.

**Không nên so sánh chỉ bằng số dòng code.** Cần tính thời gian của người xây dựng, người sử dụng và người duy trì, cùng chi phí tích hợp và rủi ro tương thích.

## 11. Ghi nhớ

- DSL nhúng tận dụng cú pháp và công cụ của ngôn ngữ chủ; DSL bên ngoài có cú pháp và thường có công cụ phân tích riêng.
- DSL nhúng thường giảm chi phí parser và IDE nếu host language đã được tổ chức sử dụng, nhưng tạo phụ thuộc vào host và yêu cầu người dùng biết ngôn ngữ đó.
- DSL bên ngoài cho phép thiết kế cú pháp sát miền và tách khỏi host language, nhưng có thể cần parser, validator, runtime, formatter và hỗ trợ IDE riêng.
- Chi phí công cụ gồm xây dựng, sử dụng, đào tạo, tích hợp, vận hành, bảo trì và migration.
- Tổng chi phí sở hữu phải tính cả thời gian của người viết DSL, người dùng và nhóm duy trì công cụ.
- Nên tận dụng công cụ có sẵn, bắt đầu từ bộ tính năng tối thiểu và mở rộng dựa trên nhu cầu đo được.

## 12. Câu hỏi tự kiểm tra

1. DSL nhúng tận dụng được những công cụ nào của ngôn ngữ chủ?
2. Vì sao một DSL bên ngoài thường cần đầu tư cho parser và thông báo lỗi?
3. Trong trường hợp nào DSL bên ngoài dựa trên YAML và schema có thể rẻ hơn DSL nhúng?
4. Nêu ít nhất năm thành phần cần được tính vào TCO của một DSL.
5. Vì sao chi phí đào tạo người dùng có thể làm thay đổi quyết định giữa DSL nhúng và DSL bên ngoài?
6. Một tổ chức đã dùng Kotlin và Gradle rộng rãi, người dùng DSL đều là lập trình viên. Hướng nào có thể tận dụng tài sản hiện có tốt hơn? Vì sao?
7. Một nhóm vận hành cần khai báo quy tắc đơn giản bằng ngôn ngữ gần nghiệp vụ. Những chi phí công cụ nào cần cân nhắc nếu xây DSL bên ngoài?
8. Hãy đề xuất một thử nghiệm nhỏ để so sánh chi phí của hai cách triển khai cho cùng một bài toán.
