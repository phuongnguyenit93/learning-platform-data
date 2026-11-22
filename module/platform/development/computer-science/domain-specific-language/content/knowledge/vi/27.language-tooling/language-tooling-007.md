# Trình tạo dự án

Trong hệ sinh thái của ngôn ngữ chuyên biệt miền (Domain-Specific Language, DSL), **trình tạo dự án (project generator)** là công cụ khởi tạo một project mới từ lựa chọn và cấu hình của người dùng. Công cụ tạo sẵn cấu trúc thư mục, file cấu hình, mã nguồn khung, dependency, tài liệu, ví dụ và các thành phần cần thiết để người dùng có thể bắt đầu phát triển hoặc triển khai một ứng dụng dựa trên DSL.

Ví dụ, một người dùng muốn xây dựng dịch vụ xử lý đơn hàng bằng DSL có thể chạy lệnh tạo project, chọn target Java, loại ứng dụng service, database PostgreSQL và cấu hình kiểm thử. Project generator tạo một workspace có cấu trúc nhất quán, kèm file DSL mẫu, cấu hình build, mã nguồn adapter và hướng dẫn chạy thử.

~~~text
dsl create project don-hang-service
    --template java-service
    --database postgres
    --package com.example.order
~~~

Kết quả có thể gồm:

~~~text
don-hang-service/
  dsl/
    order-model.dsl
    shipping-policy.dsl
  src/
    main/
      java/
    test/
      java/
  config/
    application.yml
  build.gradle
  README.md
  .gitignore
~~~

Project generator giúp người dùng bắt đầu nhanh, giảm lỗi cấu hình ban đầu và tạo ra cách tổ chức thống nhất giữa các project. Trong một DSL toolchain, nó còn đóng vai trò kết nối ngôn ngữ với runtime, compiler, code generator, IDE, thư viện và nền tảng triển khai. Để hữu ích, công cụ phải tạo project có thể hiểu, build và chạy được; ghi rõ các lựa chọn đã áp dụng; đồng thời cho phép người dùng tùy biến mà không làm mất khả năng nâng cấp template về sau.

## 1. Trình tạo dự án là gì?

Project generator là một công cụ tự động tạo bộ khung ban đầu cho một project. Nó nhận đầu vào như tên project, loại ứng dụng, template, target platform và các tính năng được chọn, sau đó kết hợp những file mẫu cùng dữ liệu cấu hình để tạo workspace.

Một project generator có thể tạo:

- Cấu trúc thư mục và file nguồn.
- File DSL mẫu cùng model hoặc policy khởi đầu.
- Cấu hình compiler, runtime và generator.
- Build script và dependency.
- Cấu hình môi trường phát triển, kiểm thử và triển khai.
- Tài liệu hướng dẫn, ví dụ và lệnh chạy.
- Cấu hình IDE, formatter, linter và language server.
- Test skeleton, fixture và dữ liệu mẫu.
- Metadata quản lý project, version và template provenance.

### 1.1. Project generator khác với code generator

Code generator chuyển model hoặc chương trình DSL thành một artifact cụ thể như Java class, SQL schema hoặc JSON. Project generator tạo toàn bộ bộ khung project, thường gồm nhiều artifact và cấu hình liên quan.

Hai công cụ có thể phối hợp: project generator tạo workspace và cấu hình ban đầu; code generator sau đó đọc model DSL trong workspace để sinh mã nguồn hoặc schema.

### 1.2. Project generator khác với template file đơn lẻ

Template file tạo một file từ context. Project generator điều phối nhiều template, xác định đường dẫn, lựa chọn thành phần, giải quyết dependency và ghi kết quả thành một project hoàn chỉnh.

### 1.3. Project generator khác với package manager

Package manager cài đặt và quản lý dependency. Project generator có thể khai báo dependency cần dùng trong build file hoặc gọi package manager để khởi tạo môi trường, nhưng hai trách nhiệm khác nhau. Generator quyết định bộ khung và cấu hình ban đầu; package manager giải quyết phiên bản, tải và cập nhật package.

### 1.4. Project generator khác với project clone

Clone một repository sao chép một project có sẵn. Generator tạo project mới từ template có tham số, có thể chọn thành phần và đổi tên, package, target hoặc cấu hình theo nhu cầu. Template có thể được lưu trong repository, nhưng kết quả cần được cá thể hóa theo đầu vào.

## 2. Vai trò trong hệ sinh thái DSL

DSL thường đi cùng nhiều công cụ: parser, semantic analyzer, compiler, interpreter, code generator, runtime, plugin và IDE. Project generator tạo điểm bắt đầu để các thành phần này được sử dụng cùng nhau.

### 2.1. Khởi tạo môi trường sử dụng DSL

Người dùng có thể chưa biết cần cài những thư viện nào, cấu hình compiler ra sao hoặc đặt file DSL ở đâu. Generator tạo cấu trúc và cấu hình phù hợp với một use case đã chọn.

### 2.2. Chuẩn hóa kiến trúc project

Các project được tạo theo cùng template có thể dùng chung cách tổ chức thư mục, tên module, quy tắc build, test và triển khai. Điều này giúp nhóm phát triển hỗ trợ, review và tự động hóa dễ hơn.

### 2.3. Kết nối DSL với target platform

Một DSL có thể hỗ trợ nhiều target như Java, TypeScript, SQL hoặc cấu hình hạ tầng. Project generator chọn bộ file và dependency phù hợp với target, đồng thời tạo cấu hình để các bước compile và run sử dụng đúng toolchain.

### 2.4. Cung cấp ví dụ có thể chạy

Project mẫu giúp người dùng hiểu cách khai báo model, policy, workflow và cách gọi runtime. Một ví dụ có thể build hoặc chạy được thường có giá trị hướng dẫn cao hơn một đoạn cú pháp đứng riêng.

### 2.5. Hỗ trợ onboarding

Generator giảm số quyết định ban đầu mà người mới phải tự tìm hiểu. Người dùng có thể bắt đầu từ template đơn giản rồi mở rộng theo yêu cầu thay vì dựng toàn bộ project từ đầu.

### 2.6. Tạo nền tảng cho automation

CLI, IDE, portal nội bộ hoặc pipeline có thể gọi cùng generator API. Nhờ đó, việc khởi tạo project được thực hiện theo một quy trình thống nhất ở nhiều môi trường.

## 3. Các thành phần của project generator

Một generator thường gồm nhiều thành phần có trách nhiệm riêng.

| Thành phần | Vai trò |
|---|---|
| CLI hoặc UI | Thu thập lựa chọn và hiển thị kết quả |
| Project descriptor | Mô tả project, template và tính năng được chọn |
| Template catalog | Liệt kê template có thể sử dụng |
| Template engine | Render file từ template và context |
| Feature resolver | Xác định thành phần và dependency cần tạo |
| Configuration model | Chuẩn hóa lựa chọn của người dùng |
| File planner | Tính đường dẫn, nội dung và thao tác file |
| Output writer | Tạo thư mục và ghi file |
| Validator | Kiểm tra cấu hình và project vừa tạo |
| Report generator | Báo cáo file, lựa chọn và bước tiếp theo |

### 3.1. Project descriptor

Descriptor là mô tả có cấu trúc về project cần tạo. Nó có thể chứa tên, phiên bản DSL, template ID, target, package, feature, dependency và cấu hình môi trường.

### 3.2. Template catalog

Catalog cung cấp danh sách template, mô tả mục đích, phiên bản, yêu cầu tương thích và lựa chọn cấu hình. Catalog có thể được đóng gói trong công cụ hoặc tải từ một nguồn được quản lý.

### 3.3. Feature resolver

Feature resolver xác định khi chọn một tính năng thì cần thêm những file, dependency hoặc cấu hình nào. Ví dụ chọn REST API có thể kéo theo web framework, controller skeleton và test.

### 3.4. File planner

File planner tính danh sách file đầu ra trước khi ghi. Nó giúp phát hiện đường dẫn trùng, xung đột tên, file cần ghi đè và file phụ thuộc vào lựa chọn khác.

### 3.5. Output writer

Writer tạo thư mục và ghi nội dung. Nó cần quy định encoding, newline, quyền ghi, xử lý file đã tồn tại và cách phục hồi nếu một bước thất bại.

## 4. Luồng hoạt động tổng quát

Một quy trình tạo project thường đi từ lựa chọn đến xác thực đầu ra:

~~~mermaid
flowchart TD
    A[Người dùng yêu cầu project] --> B[Chọn template và target]
    B --> C[Thu thập cấu hình]
    C --> D[Validate input]
    D --> E[Resolve features và dependencies]
    E --> F[Build generation context]
    F --> G[Plan output files]
    G --> H[Render templates]
    H --> I[Write to destination]
    I --> J[Validate generated project]
    J --> K[Report next steps]
~~~

### 4.1. Chọn template

Người dùng chọn loại project phù hợp, ví dụ DSL library, backend service, data pipeline hoặc infrastructure module. Template cần mô tả rõ mục đích và những thành phần sẽ được tạo.

### 4.2. Thu thập cấu hình

Generator hỏi các thông tin như project name, package, target language, database, authentication, test framework hoặc deployment platform. Giá trị có thể đến từ CLI flags, interactive prompt, file cấu hình hoặc API.

### 4.3. Validate đầu vào

Trước khi tạo file, generator kiểm tra tên, package, phiên bản, lựa chọn không tương thích và quyền ghi vào destination. Lỗi cần được báo trước khi có thay đổi một phần trên filesystem.

### 4.4. Resolve features

Feature resolver tính các thành phần cần thiết và dependency kéo theo. Nếu người dùng chọn REST API, có thể cần web runtime; nếu chọn persistence, cần database adapter và cấu hình connection.

### 4.5. Render và ghi

Generator tạo context đã chuẩn hóa, render các template, lập kế hoạch file và ghi vào destination. Nên tạo vào thư mục tạm trước rồi công bố kết quả sau khi các bước cần thiết thành công.

### 4.6. Validate project

Kiểm tra các file quan trọng tồn tại, descriptor hợp lệ, cấu hình nhất quán và đường dẫn không bị sai. Có thể cung cấp lệnh build hoặc validate tiếp theo; không phải mọi generator đều tự chạy toàn bộ build.

### 4.7. Hướng dẫn bước tiếp theo

Kết quả nên chỉ ra thư mục đã tạo, lệnh cài dependency, lệnh chạy test, lệnh khởi động ứng dụng và nơi chỉnh sửa file DSL đầu tiên.

## 5. Template catalog và lựa chọn project

Template catalog là nơi người dùng khám phá các kiểu project được hỗ trợ.

### 5.1. Template metadata

Một template nên có metadata như:

- ID ổn định và tên hiển thị.
- Mô tả mục đích và trường hợp sử dụng.
- Phiên bản template.
- Phiên bản DSL hoặc runtime yêu cầu.
- Target platform và toolchain.
- Feature có thể bật/tắt.
- Các tham số bắt buộc và tùy chọn.
- License hoặc nguồn gốc nếu có.
- Mức hỗ trợ và trạng thái bảo trì.

### 5.2. Ví dụ descriptor template

~~~yaml
id: java-service
name: Java Service
version: 2.1.0
description: Starter project for a DSL-backed service
requires:
  dsl: ">=2.0 <3.0"
  java: ">=21"
features:
  - rest-api
  - persistence
  - tests
parameters:
  packageName:
    type: package
    required: true
~~~

Đây là cấu trúc minh họa. Schema thực tế cần xác định kiểu dữ liệu, biểu thức phiên bản và cách biểu diễn feature dependency.

### 5.3. Phân loại template

Catalog có thể nhóm template theo mục tiêu:

| Nhóm | Ví dụ |
|---|---|
| Learning | Tutorial, hello-world, sample DSL |
| Application | Backend service, desktop app, web app |
| DSL tooling | Language server, compiler plugin, formatter |
| Data | ETL pipeline, schema project, analytics job |
| Integration | REST client, message consumer, database adapter |
| Infrastructure | Deployment manifest, infrastructure module |
| Library | DSL extension, domain model package |

### 5.4. Template mặc định và template cộng đồng

Template chính thức thường được kiểm soát về tương thích và bảo trì. Template cộng đồng có thể mở rộng lựa chọn nhưng cần thông tin nguồn gốc, version, license và mức độ tin cậy.

### 5.5. Tìm kiếm và lọc

Catalog có thể lọc theo target, ngôn ngữ, loại ứng dụng, runtime, database hoặc mức độ kinh nghiệm. Mô tả nên giúp người dùng chọn đúng template mà không cần đọc toàn bộ nội dung bên trong.

### 5.6. Không phụ thuộc tên hiển thị

Template ID nên ổn định và được dùng trong cấu hình, automation và log. Tên hiển thị có thể đổi hoặc dịch sang ngôn ngữ khác mà không làm hỏng project descriptor.

## 6. Thu thập và xác thực cấu hình

Project generator cần biến câu trả lời của người dùng thành một configuration model có kiểu và giá trị rõ ràng.

### 6.1. Tham số bắt buộc và tùy chọn

Tên project và target thường là bắt buộc. Mô tả, license, database hoặc telemetry có thể tùy chọn. Mỗi tham số cần default được công bố nếu không bắt buộc.

### 6.2. Kiểu tham số

Tham số có thể là string, boolean, enum, version, package name, path, URL, secret reference hoặc danh sách lựa chọn. Không nên lưu mọi thứ thành chuỗi không kiểm tra.

### 6.3. Validation

Validation kiểm tra:

- Tên project có hợp lệ với filesystem và công cụ build không.
- Package hoặc namespace có đúng cú pháp target không.
- Phiên bản runtime có được hỗ trợ không.
- Các feature có tương thích với nhau không.
- Destination có thể ghi và không gây ghi đè ngoài ý muốn không.
- Giá trị cấu hình có đáp ứng constraint miền không.

### 6.4. Conditional questions

Chỉ hỏi database khi người dùng chọn persistence. Chỉ hỏi cloud region khi template có triển khai cloud. Conditional questions giúp giảm cấu hình không liên quan và tránh yêu cầu thông tin không cần thiết.

### 6.5. Interactive và non-interactive mode

Interactive mode hỏi từng câu và có thể giải thích lựa chọn. Non-interactive mode nhận tất cả giá trị qua flags hoặc descriptor để dùng trong CI và script.

### 6.6. Defaults và reproducibility

Default phải được ghi nhận trong project descriptor hoặc generation report. Nếu default thay đổi giữa phiên bản template, cùng một lệnh có thể tạo project khác; vì vậy cần version template và cho phép khóa lựa chọn quan trọng.

### 6.7. Secret handling

Không nên yêu cầu nhập password hoặc token rồi ghi trực tiếp vào source file. Generator có thể tạo placeholder tham chiếu biến môi trường hoặc secret manager, đồng thời hướng dẫn cách cấu hình giá trị thật.

## 7. Feature selection và dependency resolution

Một template thường có nhiều feature tùy chọn. Feature resolver quyết định tổ hợp file và dependency cần tạo.

### 7.1. Feature độc lập

Một số feature có thể bật riêng như formatter, test framework hoặc sample data. Khi được chọn, chúng thêm file cấu hình hoặc dependency tương ứng.

### 7.2. Feature kéo theo

Feature REST API có thể kéo theo HTTP runtime, JSON serialization và controller skeleton. Feature persistence có thể kéo theo database abstraction và migration support.

### 7.3. Dependency constraints

Hai feature có thể yêu cầu các phiên bản thư viện không tương thích. Resolver cần kiểm tra constraint trước khi render build file và báo xung đột có thể hiểu được.

### 7.4. Conflicts

Một project có thể chọn hai framework thay thế nhau hoặc hai cơ chế authentication không tương thích. Metadata nên khai báo conflict để generator từ chối tổ hợp sai.

### 7.5. Implied features

Nếu feature A yêu cầu feature B, generator có thể tự bật B hoặc yêu cầu người dùng xác nhận. Hành vi này cần được hiển thị trong report để người dùng hiểu vì sao dependency xuất hiện.

### 7.6. Feature graph

Có thể mô hình hóa feature và dependency thành đồ thị:

~~~mermaid
flowchart TD
    A[REST API] --> B[HTTP Runtime]
    A --> C[JSON Support]
    D[Persistence] --> E[Database Adapter]
    D --> F[Migration Support]
    G[Tests] --> H[Test Framework]
~~~

Feature resolver duyệt đồ thị, phát hiện chu trình, giải quyết phiên bản và tạo tập feature cuối cùng.

### 7.7. Dependency lock

Với project cần tái lập, generator có thể ghi phiên bản cụ thể hoặc tạo lock file. Điều này giúp build sau này không vô tình lấy dependency mới có hành vi khác.

## 8. Cấu trúc thư mục và tổ chức module

Project generator thường tạo một cấu trúc mặc định để phân chia source, test, configuration và tài liệu.

### 8.1. Cấu trúc đơn giản

~~~text
my-dsl-project/
  dsl/
  src/
  test/
  config/
  docs/
  build.gradle
  README.md
~~~

### 8.2. Cấu trúc nhiều module

Project lớn có thể tách module:

~~~text
order-platform/
  dsl-model/
  dsl-runtime/
  application/
  integration-tests/
  deployment/
  build.gradle
  settings.gradle
~~~

Mỗi module có trách nhiệm và dependency rõ ràng. Generator cần bảo đảm module graph không có dependency vòng ngoài ý muốn.

### 8.3. Phân biệt file nguồn và file generated

Nên có thư mục riêng cho file người dùng chỉnh sửa và artifact do generator tạo. Ví dụ:

~~~text
src/
  main/
    dsl/
    java/
generated/
  java/
  schema/
~~~

Tách vùng giúp tránh ghi đè thay đổi thủ công khi chạy code generator lần sau.

### 8.4. Quy tắc đặt tên

Tên project, module, package và file cần được chuẩn hóa theo target. Generator phải phát hiện tên khác nhau nhưng trùng sau khi chuẩn hóa, đặc biệt trên filesystem không phân biệt hoa thường.

### 8.5. Cấu trúc có thể cấu hình

Template có thể cho phép thay root source directory hoặc tên module. Tuy nhiên, cần giữ convention mặc định để plugin, IDE và build tool tìm thấy file dễ dàng.

## 9. Sinh file DSL khởi đầu

Project DSL thường cần một hoặc nhiều file mẫu để người dùng hiểu cách khai báo đầu tiên.

### 9.1. Hello-world

Template học tập có thể tạo một DSL tối thiểu:

~~~text
module hello

message greeting {
    text = "Xin chào DSL"
}
~~~

Ví dụ nên đủ nhỏ để người mới đọc được và có đường dẫn chạy rõ ràng.

### 9.2. Domain model

Template ứng dụng có thể tạo entity hoặc type mẫu:

~~~text
entity DonHang {
    id: OrderId primary
    tong_tien: Money<VND>
    trang_thai: OrderStatus
}
~~~

### 9.3. Policy và workflow

Project có thể có file policy và workflow riêng để tách mô hình dữ liệu khỏi quy tắc xử lý. Generator nên đặt tên và import nhất quán.

### 9.4. Placeholder có chủ đích

File mẫu nên phân biệt giá trị ví dụ hợp lệ với placeholder cần người dùng thay. Placeholder không được làm project mặc định thất bại khi build, trừ khi template có chủ đích tạo một bài tập chưa hoàn chỉnh.

### 9.5. Mẫu theo feature

Khi bật database, generator có thể thêm model persistence; khi bật REST API, thêm endpoint mẫu; khi bật scheduler, thêm schedule mẫu. Các file phải được tạo dựa trên feature đã resolve, tránh để lại cấu hình tham chiếu đến thành phần không tồn tại.

## 10. Tạo build configuration và dependency

Project mới cần biết cách lấy thư viện, compile DSL, sinh mã và chạy ứng dụng.

### 10.1. Build system

Generator có thể hỗ trợ Gradle, Maven, npm, pnpm, Cargo hoặc công cụ riêng tùy target. Build file cần chứa plugin, repository, dependency và task tối thiểu để validate project.

### 10.2. Dependency theo feature

Chỉ thêm dependency cần thiết cho feature đã chọn. Project không dùng database không nên mang theo database driver mặc định nếu template không yêu cầu.

### 10.3. Plugin DSL

Build configuration có thể khai báo plugin parser, compiler hoặc code generator. Phiên bản plugin nên tương thích với language version và runtime version trong descriptor.

### 10.4. Toolchain

Nếu target yêu cầu Java 21 hoặc một phiên bản Node cụ thể, generator nên tạo cấu hình toolchain hoặc ghi rõ prerequisite trong README.

### 10.5. Repository và dependency source

Repository cần được cấu hình rõ ràng. Không nên thêm nguồn package không tin cậy hoặc repository tạm thời mà người dùng không biết.

### 10.6. Lock file

Nếu hệ sinh thái hỗ trợ lock file, generator có thể tạo hoặc hướng dẫn tạo để giữ dependency graph ổn định. Lock file cần được cập nhật theo quy trình quản lý dependency của dự án.

### 10.7. Không nhúng secret vào build file

Credential để tải package riêng hoặc truy cập dịch vụ không nên được ghi cứng vào file build. Dùng environment variable, credential store hoặc secret manager.

## 11. Cấu hình compiler, runtime và code generator

Project generator cho DSL cần nối các file nguồn với đúng toolchain.

### 11.1. Language version

Descriptor nên ghi language version mà project sử dụng. Parser và semantic analyzer cần đọc cùng version để hiểu đúng grammar và semantics.

### 11.2. Runtime target

Project có thể chọn runtime profile như embedded, server hoặc distributed. Generator cần tạo dependency và cấu hình tương ứng.

### 11.3. Code generation target

Nếu DSL sinh Java hoặc TypeScript, project cần chỉ rõ target version, package, output directory và template bundle.

### 11.4. Source roots

Build tool cần biết file DSL nằm ở đâu, file generated nằm ở đâu và khi nào cần chạy generator. Không nên để cùng một file được sinh lại ở nhiều task không có dependency rõ ràng.

### 11.5. Compiler options

Các tùy chọn như strict type checking, warning policy, optimization và source mapping có thể được đưa vào config. Giá trị mặc định cần phù hợp với mục đích template.

### 11.6. Configuration profiles

Project có thể có profile development, test và production. Cần tránh đưa secret hoặc giá trị môi trường thật vào file mẫu được commit.

## 12. Tích hợp IDE và developer tooling

Một project có thể tạo sẵn cấu hình giúp editor nhận diện DSL ngay sau khi mở workspace.

### 12.1. Language server configuration

Generator có thể tạo cấu hình để IDE khởi chạy language server hoặc nhận diện file extension. Cấu hình nên dùng đường dẫn tương đối hoặc toolchain được quản lý, tránh phụ thuộc máy cá nhân.

### 12.2. File association

Project có thể khai báo extension của DSL và grammar support để editor tô màu, định dạng và cung cấp completion.

### 12.3. Formatter và linter

Template có thể tạo cấu hình formatter, lint rules và severity. Cần chọn rule set phù hợp với DSL version.

### 12.4. Debug configuration

Nếu runtime hỗ trợ debug, generator có thể tạo launch configuration mẫu với entry point và environment rõ ràng.

### 12.5. Editor settings

Workspace settings có thể xác định indentation, encoding, newline và file exclusion. Tránh áp đặt các thiết lập không cần thiết lên toàn bộ editor của người dùng.

### 12.6. IDE-neutral files

Nên ưu tiên cấu hình chung như language server metadata hoặc task script. Nếu tạo file riêng cho một IDE, cần đặt trong thư mục tùy chọn và mô tả rõ.

## 13. Sinh test, fixture và ví dụ

Project generator nên tạo nền tảng kiểm thử ngay từ đầu để người dùng có thể xác minh thay đổi.

### 13.1. Unit test skeleton

Template có thể tạo test cho domain model, helper hoặc generated adapter. Test mẫu cần thể hiện cách khởi tạo runtime và gọi thành phần.

### 13.2. DSL validation test

Có thể tạo fixture hợp lệ và không hợp lệ để kiểm tra parser, semantic analyzer và diagnostic. Fixture cần gắn với language version của project.

### 13.3. Integration test

Nếu project có database hoặc message broker, generator có thể tạo test cấu hình môi trường hoặc container test theo framework đã chọn.

### 13.4. Golden test

Với code generator, golden test lưu output mong đợi để phát hiện thay đổi template hoặc generator. Đây là cách kiểm tra tính ổn định của artifact.

### 13.5. Sample data

Dữ liệu mẫu nên nhỏ, không chứa dữ liệu cá nhân thật và có thể chạy trong môi trường local. Nếu cần secret, dùng placeholder hoặc biến môi trường.

### 13.6. Test command

README nên nêu lệnh chạy test. Build configuration cần bảo đảm task test tìm đúng source root và fixture.

## 14. Tài liệu và hướng dẫn được tạo cùng project

Project generator không chỉ tạo mã. Tài liệu ban đầu giúp người dùng hiểu project đã được cấu hình như thế nào.

### 14.1. README

README nên có:

- Mục đích và mô tả ngắn.
- Yêu cầu môi trường và toolchain.
- Cách cài dependency.
- Cách validate, test và chạy project.
- Vị trí file DSL quan trọng.
- Cách sinh lại artifact.
- Cấu hình cần cung cấp qua environment.
- Hướng dẫn mở rộng hoặc thêm module.

### 14.2. Architecture note

Template phức tạp có thể tạo tài liệu mô tả module, dependency và luồng thực thi. Tài liệu nên phản ánh feature đã chọn thay vì nội dung chung không chính xác.

### 14.3. Example gallery

Một thư mục examples có thể minh họa policy, workflow, query hoặc integration. Mỗi ví dụ cần có chú thích về mục tiêu và lệnh chạy.

### 14.4. Generated documentation

Generator có thể tạo tài liệu từ metadata template và project descriptor. Khi cấu hình thay đổi, tài liệu cần được cập nhật để không mô tả feature đã bị tắt.

### 14.5. Hướng dẫn nâng cấp

README có thể ghi template ID và version đã dùng, cùng cách nâng cấp project khi template mới được phát hành.

## 15. CLI và giao diện tương tác

Project generator thường cung cấp CLI vì dễ tích hợp vào script và CI, nhưng có thể có UI wizard cho người dùng mới.

### 15.1. CLI command design

Một CLI có thể có các lệnh:

~~~text
dsl templates list
dsl templates show java-service
dsl create project order-service
dsl project validate
dsl project info
~~~

Tên lệnh chỉ minh họa. Command cần có help, version và exit code nhất quán.

### 15.2. Interactive wizard

Wizard có thể hỏi tên, template, target và feature theo từng bước. Mỗi lựa chọn nên có mô tả ngắn, default rõ và khả năng quay lại.

### 15.3. Non-interactive mode

CI hoặc automation cần chạy không có prompt. Mọi thông tin bắt buộc phải được truyền qua flags, descriptor hoặc environment theo hợp đồng rõ.

### 15.4. Preview

Preview hiển thị template, feature, dependency và file dự kiến trước khi tạo. Người dùng có thể phát hiện lựa chọn sai trước khi filesystem thay đổi.

### 15.5. Dry run

Dry run tính toán và báo cáo kế hoạch mà không ghi file. Nó hữu ích để kiểm tra tổ hợp feature và đường dẫn.

### 15.6. Exit codes

CLI nên phân biệt input không hợp lệ, template không tồn tại, xung đột file, lỗi render và lỗi ghi file. Exit code ổn định giúp script xử lý đúng.

## 16. Cấu hình project sau khi tạo

Project generator tạo điểm bắt đầu, nhưng project cần tiếp tục được cấu hình theo môi trường thật.

### 16.1. Environment variables

File cấu hình có thể tham chiếu biến môi trường:

~~~yaml
database:
  url: $DB_URL
  username: $DB_USERNAME
  password: $DB_PASSWORD
~~~

Ví dụ này chỉ minh họa cách tham chiếu. Generator nên tạo file mẫu không chứa credential thật và hướng dẫn người dùng cung cấp giá trị.

### 16.2. Local và production profile

Profile local có thể dùng database container hoặc dữ liệu mẫu. Production profile nên lấy endpoint và secret từ hệ thống cấu hình được quản lý.

### 16.3. Không ghi đè cấu hình người dùng

Lần chạy generator tiếp theo hoặc lệnh update template không nên thay thế cấu hình đã được người dùng chỉnh sửa mà không có diff hoặc chính sách merge.

### 16.4. Configuration schema

Project descriptor và application config nên có schema để editor hỗ trợ completion, validation và documentation.

### 16.5. Kiểm tra cấu hình lúc khởi động

Runtime nên xác thực các trường bắt buộc trước khi thực thi. Generator có thể tạo cấu hình mẫu, nhưng không thể bảo đảm giá trị môi trường đã được cung cấp.

## 17. Tùy biến template và extension point

Người dùng thường cần điều chỉnh project theo convention của tổ chức.

### 17.1. Template override

Generator có thể cho phép override một số file hoặc fragment. Extension point cần được công bố để người dùng biết phần nào có thể thay đổi ổn định.

### 17.2. Hook

Hook có thể chạy trước hoặc sau khi render, ví dụ format file, tạo manifest hoặc cập nhật tên package. Hook cần có quyền và thời gian chạy giới hạn.

### 17.3. Plugin

Plugin có thể thêm template, feature resolver, validator hoặc post-generation action. Plugin cần khai báo version compatibility và nguồn gốc.

### 17.4. Custom template repository

Tổ chức có thể quản lý catalog nội bộ với template đã được phê duyệt. Generator cần xác thực nguồn, version và checksum nếu template được tải từ xa.

### 17.5. Không fork toàn bộ template nếu không cần

Fork template đầy đủ khiến việc nhận bản sửa và cải tiến từ upstream khó hơn. Nếu có thể, override fragment hoặc tham số thay đổi là cách dễ bảo trì hơn.

### 17.6. Extension API ổn định

Nếu plugin phụ thuộc vào internal class hoặc cấu trúc thư mục không được cam kết, mỗi lần generator đổi phiên bản có thể làm plugin hỏng. Extension API nên nhỏ, có version và tài liệu.

## 18. Nâng cấp project đã được tạo

Project generator có thể hỗ trợ update hoặc migration sau khi project ban đầu được tạo.

### 18.1. Template version

Project descriptor nên ghi template ID và version đã dùng. Điều này giúp xác định project bắt đầu từ bộ khung nào.

### 18.2. Update khác recreate

Recreate tạo project mới từ đầu. Update áp dụng thay đổi template vào project hiện tại. Update phải tính đến những file người dùng đã sửa.

### 18.3. Three-way merge

Một chiến lược update có thể so sánh:

- File template gốc ở version cũ.
- File hiện tại do người dùng có thể đã chỉnh sửa.
- File template mới.

Từ ba phiên bản, công cụ xác định thay đổi có thể merge tự động và xung đột cần người dùng giải quyết.

### 18.4. Generated file ownership

Manifest có thể ghi file nào do generator quản lý và checksum ban đầu. Khi update, generator biết file nào có thể cập nhật, file nào đã bị chỉnh sửa và file nào không còn được template tạo.

### 18.5. Breaking template changes

Đổi tên module, thay build plugin hoặc di chuyển source root có thể ảnh hưởng script và IDE. Update report cần chỉ rõ các thay đổi này.

### 18.6. Backup và preview

Update nên có dry run, diff và backup. Không nên xóa file hoặc ghi đè nội dung người dùng mà không thể xem trước.

## 19. Tính xác định và khả năng tái lập

Project generator đáng tin cậy cần tạo cùng cấu trúc khi nhận cùng đầu vào, template và dependency version.

### 19.1. Deterministic generation

Đầu ra không nên phụ thuộc vào thứ tự duyệt map, timezone máy, đường dẫn tuyệt đối hoặc timestamp hiện tại nếu các yếu tố đó không thuộc cấu hình.

### 19.2. Pin template version

Lệnh dùng template latest có thể tạo kết quả khác vào ngày khác. Project descriptor nên ghi version cụ thể hoặc release channel để có thể tái tạo.

### 19.3. Pin dependency

Dependency range rộng có thể kéo phiên bản mới khác hành vi. Lock file hoặc version catalog giúp kiểm soát dependency graph.

### 19.4. Stable file ordering

Manifest, import và danh sách module nên được sắp xếp ổn định để Git diff không thay đổi ngẫu nhiên.

### 19.5. Idempotent initialization

Chạy lại lệnh tạo project ở destination đã tồn tại cần có semantics rõ: từ chối, update, merge hoặc chỉ kiểm tra. Không nên âm thầm nhân đôi file hoặc ghi đè project hiện có.

### 19.6. Provenance

Project có thể ghi template ID, template version, generator version, thời điểm tạo và lựa chọn feature. Provenance giúp điều tra và lên kế hoạch nâng cấp.

## 20. An toàn khi tạo file và thực thi hook

Generator thao tác trên filesystem và có thể chạy plugin hoặc hook, vì vậy cần kiểm soát đầu vào và quyền.

### 20.1. Path traversal

Tên project hoặc tham số không được phép tạo đường dẫn ra ngoài destination. Chuẩn hóa path, loại thành phần nguy hiểm và xác minh mọi output path nằm trong root đã chọn.

### 20.2. File overwrite

Nếu destination đã có file, generator cần hỏi hoặc từ chối theo policy. Không nên xóa toàn bộ thư mục đích để tạo lại nếu chưa xác định đó là thư mục do generator sở hữu.

### 20.3. Symlink

Symlink trong destination có thể trỏ ra ngoài workspace. Writer cần quyết định có theo symlink hay từ chối và xác minh đường dẫn đích trước khi ghi.

### 20.4. Template trust

Template engine có thể hỗ trợ helper hoặc expression. Nếu template đến từ nguồn không tin cậy, cần sandbox, giới hạn quyền và giới hạn tài nguyên.

### 20.5. Hook execution

Post-generation hook có thể chạy lệnh hệ thống. Chỉ chạy hook từ nguồn được tin cậy, hiển thị lệnh và yêu cầu quyền phù hợp. Không nên thực thi lệnh lấy trực tiếp từ tham số người dùng mà không kiểm tra.

### 20.6. Dependency source

Không thêm repository hoặc package source lạ mà không công bố. Template cần khai báo nguồn dependency và phiên bản để người dùng kiểm tra.

### 20.7. Secret và dữ liệu cá nhân

Không lưu secret thật trong project mẫu, log hoặc report. Dữ liệu demo nên là dữ liệu giả và không chứa thông tin cá nhân.

## 21. Xử lý lỗi và báo cáo tạo project

Một generator cần phân biệt lỗi đầu vào, lỗi template, lỗi dependency và lỗi filesystem.

### 21.1. Input validation error

Tên project hoặc package không hợp lệ cần được báo ngay cùng quy tắc hợp lệ và vị trí tham số.

### 21.2. Template error

Template có thể thiếu file, tham chiếu biến không tồn tại hoặc dùng cú pháp sai. Report nên nêu template ID, file và vị trí lỗi nếu engine cung cấp.

### 21.3. Dependency conflict

Nếu feature yêu cầu hai phiên bản thư viện không tương thích, thông báo cần chỉ ra dependency nào kéo theo constraint nào và lựa chọn giải quyết.

### 21.4. File conflict

Nếu file đích đã tồn tại hoặc hai template cùng tạo một path, generator cần dừng hoặc áp dụng merge policy đã công bố.

### 21.5. Partial failure

Nếu tạo nhiều file và một bước thất bại, project có thể ở trạng thái dở dang. Staging directory và commit sau validation giúp giảm trạng thái nửa hoàn chỉnh.

### 21.6. Generation report

Report nên nêu:

- Destination.
- Template ID và version.
- Generator version.
- Feature được bật và feature kéo theo.
- File được tạo hoặc bỏ qua.
- Dependency được khai báo.
- Cảnh báo và lỗi.
- Lệnh tiếp theo để build, test hoặc run.

### 21.7. Exit status

CLI cần trả exit code khác 0 khi project không được tạo hoàn chỉnh. Nếu có warning nhưng tạo thành công, report phải phân biệt warning với failure.

## 22. Tích hợp CI/CD và automation

Project generator có thể được gọi từ pipeline để tạo project mới, module mới hoặc ví dụ kiểm thử.

### 22.1. Non-interactive generation

CI cần truyền descriptor hoặc flags đầy đủ, không chờ prompt. Default phải ổn định và không phụ thuộc môi trường máy chạy.

### 22.2. Template pinning

Pipeline nên khóa template version và generator version. Dùng latest không cố định có thể làm project mới thay đổi mà không có commit cập nhật cấu hình.

### 22.3. Validate generated output

Pipeline có thể kiểm tra descriptor, parse DSL mẫu, compile generated source và chạy test smoke. Generator nên cung cấp lệnh hoặc API validation có thể tự động hóa.

### 22.4. Artifact retention

Generation report và manifest có thể được lưu cùng build artifact để truy vết nguồn gốc project.

### 22.5. Tạo project từ mẫu chuẩn

Tổ chức có thể dùng generator để tạo module hoặc service mới theo architecture baseline, policy bảo mật và quy tắc build chung. Catalog nội bộ cần được version hóa và kiểm soát thay đổi.

### 22.6. Không tạo credential trong pipeline

Pipeline nên lấy secret từ secret store và truyền dưới dạng environment hoặc credential binding. Không ghi secret vào generated source hoặc log.

## 23. Quan sát, telemetry và quản trị catalog

Khi generator được dùng rộng rãi, nhóm phát triển cần hiểu template nào được sử dụng và lỗi thường xảy ra ở đâu.

### 23.1. Metrics

Có thể thu thập số lần tạo project, template được chọn, thời gian render, tỷ lệ lỗi và loại validation failure. Dữ liệu nên ở mức tổng hợp.

### 23.2. Template adoption

Thống kê sử dụng giúp nhóm biết template nào có giá trị, template nào ít được dùng và lựa chọn nào cần tài liệu tốt hơn.

### 23.3. Catalog health

Theo dõi template hết hỗ trợ, dependency lỗi thời, phiên bản DSL không còn được hỗ trợ và link tài liệu hỏng.

### 23.4. Compatibility metadata

Catalog nên ghi rõ template tương thích với DSL, runtime, generator và target version nào. Công cụ có thể lọc hoặc cảnh báo trước khi tạo.

### 23.5. Telemetry privacy

Không thu thập nội dung source, secret hoặc tên project nhạy cảm nếu không cần. Nếu cần thông tin chẩn đoán chi tiết, phải có chính sách rõ về consent, retention và quyền truy cập.

## 24. Kiểm thử project generator

Generator cần được kiểm thử ở mức template, feature resolver, filesystem và project đầu ra.

### 24.1. Unit test cho configuration model

Kiểm tra default, kiểu tham số, validation, conditional question và xung đột feature.

### 24.2. Template rendering test

Render từng template với context mẫu và xác minh nội dung, đường dẫn, encoding và newline.

### 24.3. Golden project test

Tạo project từ fixture rồi so sánh cây file và nội dung với kết quả chuẩn. Golden test giúp phát hiện thay đổi ngoài dự kiến khi template hoặc engine được nâng cấp.

### 24.4. Feature combination test

Kiểm tra tổ hợp feature độc lập, feature kéo theo và feature conflict. Không nhất thiết thử mọi tổ hợp nếu số lượng quá lớn; có thể kiểm tra các đường đi và constraint quan trọng.

### 24.5. Build smoke test

Project được tạo nên có thể chạy bước validate hoặc build tối thiểu trong môi trường kiểm thử. Điều này phát hiện dependency sai, source root thiếu hoặc plugin không tương thích.

### 24.6. Test theo target

Mỗi target language hoặc platform cần kiểm tra output bằng parser/compiler tương ứng. Một project Java hợp lệ không chứng minh template TypeScript cũng hợp lệ.

### 24.7. Filesystem test

Kiểm tra destination đã tồn tại, file trùng, path traversal, symlink, quyền ghi, đường dẫn có Unicode và lỗi giữa chừng.

### 24.8. Idempotence và determinism

Chạy lại cùng generation input trong destination mới và so sánh kết quả. Kiểm tra output ổn định và hành vi rõ ràng khi destination đã tồn tại.

### 24.9. Update migration test

Nếu hỗ trợ update template, cần fixture có file chưa sửa, file đã sửa, file bị xóa và file xung đột. Kiểm tra diff và merge report.

### 24.10. Compatibility test

Kiểm tra template mới với các DSL/runtime version được công bố. Kiểm tra plugin hoặc custom template dựa trên extension API.

## 25. Ví dụ tổng hợp: tạo project DSL xử lý đơn hàng

Giả sử người dùng muốn tạo backend service dùng DSL để mô tả domain model, policy và workflow.

### 25.1. Đầu vào

~~~text
dsl create project order-service
    --template java-service
    --package com.example.order
    --database postgres
    --features rest-api,tests,scheduler
~~~

### 25.2. Cấu hình được chuẩn hóa

~~~yaml
project:
  name: order-service
  template:
    id: java-service
    version: 2.1.0
  language:
    id: order-dsl
    version: 2.0
  target:
    language: java
    version: 21
  package: com.example.order
  features:
    - rest-api
    - tests
    - scheduler
    - persistence
  database:
    type: postgres
~~~

Persistence có thể được resolver bật như feature phụ thuộc của lựa chọn database. Descriptor cuối cùng cần ghi lại lựa chọn đó.

### 25.3. Cây thư mục

~~~text
order-service/
  dsl/
    model/
      order.dsl
    policy/
      shipping.dsl
    workflow/
      order-workflow.dsl
  src/
    main/
      java/
    test/
      java/
  config/
    application.yml
  generated/
    java/
  build.gradle
  settings.gradle
  project.yml
  README.md
  .gitignore
~~~

### 25.4. DSL mẫu

~~~text
entity DonHang {
    id: OrderId primary
    tong_tien: Money<VND>
    trang_thai: OrderStatus
}

workflow xu_ly_don_hang {
    task xac_nhan
    task tru_ton_kho after success(xac_nhan)
    task tao_hoa_don after success(tru_ton_kho)
}
~~~

### 25.5. Dependency và build

Build file khai báo DSL compiler plugin, runtime, web framework, PostgreSQL driver và test framework theo feature đã chọn. Phiên bản dependency được khóa theo catalog hoặc version policy.

### 25.6. Hướng dẫn chạy

README chỉ ra cách:

1. Cài toolchain yêu cầu.
2. Cấu hình DB_URL và credential qua environment.
3. Validate file DSL.
4. Sinh mã từ model.
5. Chạy test.
6. Khởi động service.

### 25.7. Kết quả generator

Report ghi template/version, feature, dependency, file được tạo và lệnh tiếp theo. Nếu một file đích đã tồn tại, generator báo conflict và không ghi đè âm thầm.

## 26. Những sai lầm thường gặp

### 26.1. Tạo project chỉ có thư mục và file rỗng

Cấu trúc rỗng không giúp người dùng hiểu cách sử dụng DSL. Nên có ví dụ tối thiểu hợp lệ, cấu hình cần thiết và hướng dẫn chạy.

### 26.2. Template tạo ra project không build được

Dependency, plugin, source root hoặc version có thể không nhất quán. Cần kiểm tra project mẫu bằng build smoke test trong môi trường hỗ trợ.

### 26.3. Hỏi quá nhiều tham số

Một wizard dài với nhiều lựa chọn không liên quan làm người dùng khó bắt đầu. Dùng default hợp lý và conditional questions.

### 26.4. Không ghi nhận template version

Nếu project không biết được tạo từ template nào, việc nâng cấp và điều tra khác biệt trở nên khó khăn. Lưu provenance trong descriptor.

### 26.5. Thêm mọi dependency mặc định

Dependency thừa làm tăng thời gian build, bề mặt bảo trì và rủi ro bảo mật. Chỉ thêm những gì template hoặc feature thực sự cần.

### 26.6. Ghi đè file người dùng

Update generator có thể phá cấu hình hoặc source đã chỉnh sửa. Cần ownership manifest, diff và merge policy.

### 26.7. Đường dẫn phụ thuộc máy

Ghi absolute path vào config khiến project không di chuyển được. Ưu tiên path tương đối và toolchain có thể cấu hình.

### 26.8. Đưa secret vào file mẫu

Credential mẫu có thể bị commit hoặc chia sẻ. Dùng environment variable và secret reference.

### 26.9. Không xử lý feature conflict

Người dùng có thể chọn hai framework không tương thích. Resolver cần kiểm tra trước khi render và giải thích xung đột.

### 26.10. Chạy hook không kiểm soát

Hook có thể thực thi lệnh ngoài ý muốn. Cần xác thực nguồn, quyền, command và thời gian chạy.

### 26.11. Không hỗ trợ non-interactive mode

Generator chỉ chạy được qua prompt sẽ khó dùng trong CI và automation. Cần descriptor hoặc flags đầy đủ.

### 26.12. Không có dry run hoặc report

Người dùng khó biết công cụ sẽ tạo gì và vì sao. Preview, dry run và generation report giúp quyết định có thể kiểm tra được.

## 27. Nguyên tắc thiết kế project generator

Một project generator tốt cần tạo ra workspace hữu ích, có thể tái lập và có đường nâng cấp rõ.

### 27.1. Template phải có mục tiêu cụ thể

Mỗi template nên phục vụ một use case rõ, mô tả feature và prerequisite. Tránh một template duy nhất với quá nhiều nhánh không liên quan.

### 27.2. Cấu hình có kiểu và được validate

Chuẩn hóa input thành configuration model. Phát hiện tên, version, feature và path không hợp lệ trước khi ghi file.

### 27.3. Feature resolution tường minh

Khai báo dependency, conflict và implied feature. Report cho biết thành phần nào được thêm và vì sao.

### 27.4. Project mặc định phải hữu ích

Tạo ví dụ DSL hợp lệ, build configuration nhất quán, test skeleton và README đủ để bắt đầu.

### 27.5. Tách file generated và file người dùng

Định nghĩa ownership và output directory để việc sinh lại không phá thay đổi thủ công.

### 27.6. Tạo và công bố kết quả có kiểm soát

Plan file trước, render vào staging, validate rồi mới ghi vào destination. Có chính sách rõ với file đã tồn tại.

### 27.7. Hỗ trợ CLI và automation

Interactive mode thân thiện với người mới; non-interactive mode có cấu hình đầy đủ, exit code ổn định và output máy đọc được.

### 27.8. Version và provenance

Ghi template, generator, DSL và target version. Khóa dependency khi cần tái lập.

### 27.9. Tùy biến qua extension point

Cho phép override và plugin qua API có version, tránh buộc người dùng fork toàn bộ template.

### 27.10. An toàn mặc định

Chặn path traversal, tránh ghi đè âm thầm, không lưu secret, kiểm soát hook và xác thực nguồn template.

### 27.11. Kiểm thử project đầu ra

Kiểm thử cấu trúc, nội dung, feature combination, build smoke, target compatibility và update behavior.

### 27.12. Hướng dẫn bước tiếp theo

Sau khi tạo, người dùng cần biết file nào để sửa, cách validate DSL, cách sinh mã và cách chạy ứng dụng.

## 28. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Project Generator | Công cụ tạo bộ khung project từ template và cấu hình |
| Scaffolding | Tạo cấu trúc thư mục, file và thành phần ban đầu |
| Template Catalog | Danh mục các template có thể chọn |
| Project Descriptor | Mô tả có cấu trúc về project và lựa chọn đã áp dụng |
| Feature Resolver | Thành phần giải quyết feature, dependency và conflict |
| Configuration Model | Mô hình dữ liệu chuẩn hóa các tham số đầu vào |
| Output Planner | Thành phần lập kế hoạch file sẽ được tạo hoặc cập nhật |
| Template Engine | Công cụ render template thành nội dung |
| Generated File | File được công cụ tạo tự động |
| Template Provenance | Thông tin nguồn gốc và phiên bản template |
| Non-interactive Mode | Chế độ chạy không cần hỏi người dùng |
| Dry Run | Tính toán và báo cáo thay đổi mà không ghi file |
| Feature Dependency | Quan hệ một feature yêu cầu feature khác |
| Dependency Conflict | Xung đột giữa các yêu cầu phiên bản hoặc thành phần |
| Extension Point | Điểm mở rộng được generator công bố |
| Template Override | Thay thế một phần template mặc định |
| Three-way Merge | Hợp nhất dựa trên bản gốc, bản hiện tại và bản mới |
| Ownership Manifest | Metadata ghi nhận file nào do generator quản lý |
| Deterministic Generation | Cùng đầu vào và phiên bản tạo cùng kết quả |
| Build Smoke Test | Kiểm tra nhanh project có thể build hoặc validate |

Trình tạo dự án là cửa ngõ đưa người dùng từ một ý tưởng DSL đến một workspace có cấu trúc và công cụ cần thiết để phát triển. Nó phối hợp template catalog, configuration model, feature resolver, dependency và file writer để tạo ra project phù hợp với target đã chọn. Một generator được thiết kế tốt tạo ví dụ DSL có thể dùng, cấu hình build nhất quán, test và tài liệu khởi đầu; đồng thời ghi nhận version, bảo vệ file người dùng, hỗ trợ automation và cung cấp đường nâng cấp. Khi đầu vào được xác thực, output được lập kế hoạch và kiểm tra, project generator giúp các project DSL bắt đầu nhanh hơn mà vẫn giữ được tính nhất quán và khả năng bảo trì lâu dài.
