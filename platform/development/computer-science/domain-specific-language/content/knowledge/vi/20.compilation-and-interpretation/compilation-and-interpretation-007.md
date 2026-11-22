# Runtime độc lập

Trong quá trình xây dựng một **Domain-Specific Language (DSL)**, compiler hoặc interpreter thường được phát triển cùng một môi trường công cụ: parser, validator, thư viện phát triển, debugger và lệnh chạy thử. Khi đưa chương trình DSL tới người dùng hoặc hệ thống triển khai, không phải lúc nào cũng muốn cài đặt toàn bộ môi trường phát triển đó. Một giải pháp là cung cấp **runtime độc lập (standalone runtime)**: thành phần có thể tiếp nhận chương trình hoặc artifact đã được chuẩn bị, thực thi nó và cung cấp những dịch vụ cần thiết mà không phụ thuộc vào compiler hay IDE trong lúc chạy.

Runtime độc lập thường được đóng gói như một thư viện, executable, dịch vụ hoặc image triển khai. Nó có thể chạy source DSL bằng interpreter, chạy bytecode trên virtual machine, hoặc hỗ trợ mã đã được biên dịch trước. Điểm quan trọng là runtime có hợp đồng và các thành phần cần thiết để thực thi chương trình ở môi trường đích.

Ví dụ, một nhóm phát triển có thể dùng compiler và IDE để xây dựng quy tắc tính giá:

~~~text
rule "bulk-discount" {
    when order.quantity >= 10
    then order.discountRate = 0.15
}
~~~

Sau khi kiểm tra và biên dịch, nhóm triển khai một artifact chứa rule đã biên dịch cùng runtime cần thiết. Dịch vụ xử lý đơn hàng chỉ nạp artifact và gọi runtime để đánh giá rule. Máy chủ chạy ứng dụng không cần cài parser, grammar generator hay toàn bộ bộ công cụ phát triển DSL.

## 1. Runtime độc lập là gì?

**Runtime** là môi trường chịu trách nhiệm cung cấp những dịch vụ cần thiết để chương trình hoạt động. Tùy DSL, runtime có thể:

- Nạp và diễn giải source hoặc artifact đã biên dịch.
- Quản lý giá trị, kiểu dữ liệu và bộ nhớ.
- Thực hiện phép toán và lời gọi hàm tích hợp.
- Quản lý trạng thái, biến, scope và module.
- Cung cấp I/O, thời gian, mạng hoặc truy cập tài nguyên theo chính sách.
- Lập lịch tác vụ, xử lý bất đồng bộ và đồng thời.
- Báo lỗi runtime, ghi log và phát telemetry.
- Kiểm soát quyền và giới hạn tài nguyên.

Runtime độc lập là runtime có thể được triển khai và sử dụng như một đơn vị thực thi riêng, với các phụ thuộc cần thiết được xác định và cung cấp rõ ràng. Người vận hành không cần dùng trực tiếp công cụ xây dựng ngôn ngữ để chạy chương trình đã được chuẩn bị.

Từ “độc lập” ở đây cần được hiểu theo ranh giới kiến trúc. Runtime vẫn cần một nền tảng thực thi như hệ điều hành, CPU, môi trường ngôn ngữ chủ hoặc dịch vụ bên ngoài. Một runtime chạy trên JVM vẫn cần Java runtime; một runtime đóng gói trong container vẫn dùng kernel của host. Mục tiêu là độc lập với toolchain phát triển DSL và các thành phần không cần thiết trong lúc chạy, đồng thời kiểm soát rõ những phụ thuộc thực sự cần thiết.

### 1.1. Runtime độc lập không đồng nghĩa với không có phụ thuộc

Một gói runtime có thể tự chứa interpreter, thư viện chuẩn và metadata của DSL, nhưng vẫn cần:

- Hệ điều hành và kiến trúc CPU được hỗ trợ.
- Một runtime nền như JVM, .NET hoặc native system libraries.
- Cấu hình, secret hoặc dữ liệu đầu vào do môi trường cung cấp.
- Database, message broker hoặc API bên ngoài nếu chương trình sử dụng.

Do đó, khi nói runtime độc lập, cần chỉ rõ nó độc lập với thành phần nào: compiler, IDE, server phát triển, thư viện build-time hay một dịch vụ cụ thể.

## 2. Phân biệt compiler, interpreter và runtime

Ba khái niệm này liên quan nhưng có vai trò khác nhau:

- **Compiler** phân tích source, kiểm tra ngữ nghĩa và chuyển chương trình sang một dạng khác như bytecode, IR, mã nguồn đích hoặc mã máy.
- **Interpreter** đọc cấu trúc chương trình hoặc artifact và trực tiếp thực hiện các thao tác theo ngữ nghĩa của DSL.
- **Runtime** cung cấp môi trường và dịch vụ cần thiết trong lúc thực thi. Interpreter có thể là một thành phần của runtime; mã native được biên dịch trước cũng có thể cần runtime library.

Ví dụ:

~~~mermaid
flowchart LR
    A[DSL source] --> B[Compiler]
    B --> C[Bytecode / IR]
    C --> D[Standalone runtime]
    D --> E[Execution]
~~~

Một kiến trúc interpreter có thể là:

~~~mermaid
flowchart LR
    A[DSL source] --> B[Standalone interpreter]
    B --> C[Parser / AST]
    C --> D[Evaluation engine]
    D --> E[Host services]
~~~

Trong kiến trúc thứ nhất, compiler chạy ở giai đoạn build hoặc triển khai artifact; runtime chỉ cần nạp dạng trung gian. Trong kiến trúc thứ hai, runtime phải có parser hoặc evaluator đủ để xử lý source khi chạy.

Không nên đồng nhất “đã biên dịch” với “không cần runtime”. Một chương trình native có thể vẫn gọi runtime library để quản lý string, exception, garbage collection, async hoặc các kiểu dữ liệu đặc thù.

## 3. Vì sao cần runtime độc lập?

### 3.1. Triển khai mà không cài toolchain phát triển

Máy chủ production thường chỉ cần chạy artifact. Cài compiler, IDE hoặc công cụ tạo grammar lên đó có thể làm tăng kích thước, bề mặt tấn công và chi phí bảo trì.

### 3.2. Tách build-time và run-time

Compiler có thể thay đổi thường xuyên trong quá trình phát triển. Runtime production có thể được phát hành theo lịch riêng, với API và định dạng artifact có phiên bản rõ ràng.

### 3.3. Nhúng DSL vào ứng dụng khác

Một ứng dụng thương mại có thể cho phép người dùng viết rule hoặc biểu thức. Runtime độc lập có thể được nhúng như thư viện để ứng dụng chủ nạp và thực thi những rule đó.

### 3.4. Triển khai nhiều môi trường

Cùng một artifact có thể chạy trong máy chủ, container, worker, ứng dụng desktop hoặc môi trường edge nếu runtime có bản build phù hợp và hợp đồng nền tảng tương thích.

### 3.5. Quản lý phiên bản và bảo mật

Runtime production có thể chỉ chứa các capability được cho phép, thay vì toàn bộ công cụ phát triển. Điều này giúp giới hạn quyền, kiểm soát thư viện và cập nhật thành phần chạy độc lập.

### 3.6. Tái sử dụng cùng ngữ nghĩa

Một runtime được dùng bởi nhiều ứng dụng chủ có thể bảo đảm các chương trình DSL được diễn giải theo cùng một quy tắc, miễn là các ứng dụng dùng phiên bản runtime tương thích.

## 4. Ranh giới giữa build-time và run-time

Thiết kế runtime độc lập bắt đầu bằng việc xác định công việc nào diễn ra khi xây dựng artifact và công việc nào phải xảy ra khi chạy.

| Công việc | Build-time | Run-time |
|---|---|---|
| Parse source | Thường có | Chỉ cần nếu runtime nhận source |
| Kiểm tra grammar | Có | Có thể bỏ qua với artifact tin cậy đã xác thực |
| Name resolution | Có thể làm trước | Có thể còn resolve symbol động |
| Type checking | Thường làm trước | Có thể cần runtime checks cho dữ liệu động |
| Sinh bytecode/IR | Có với compiler | Nạp và thực thi |
| Đánh giá biểu thức | Có thể tính hằng | Tính với dữ liệu thực tế |
| Kết nối database | Thường không | Khi chương trình yêu cầu |
| Quản lý quyền | Đóng gói capability policy | Enforcement khi thực thi |
| Log và telemetry | Ghi metadata build | Ghi hoạt động thực tế |

Một mục tiêu phổ biến là chuyển càng nhiều kiểm tra tĩnh sang build-time càng tốt. Artifact sau đó chứa đủ thông tin để runtime không phải lặp lại các bước đó. Tuy nhiên, runtime vẫn phải xác thực artifact, kiểm tra đầu vào động và thực thi chính sách bảo mật.

Ví dụ, compiler có thể xác nhận một rule gọi đúng hàm có trong thư viện chuẩn. Runtime vẫn cần kiểm tra quyền truy cập database của lần chạy cụ thể vì quyền đó phụ thuộc môi trường.

## 5. Những mô hình runtime độc lập thường gặp

### 5.1. Interpreter độc lập

Gói triển khai chứa interpreter, parser hoặc AST loader, thư viện chuẩn và chương trình DSL:

~~~text
deployment/
├── dsl-runtime
├── stdlib/
├── config/
└── rules/
    └── pricing.dsl
~~~

Runtime đọc source hoặc AST, kiểm tra các điều kiện cần thiết rồi diễn giải chương trình. Mô hình này thuận tiện khi source cần được nạp hoặc thay đổi thường xuyên.

Đổi lại, runtime cần mang theo parser hoặc evaluator, có thể tốn thời gian khởi động và phải xử lý source chưa tin cậy nếu người dùng được phép tải file lên.

### 5.2. Bytecode virtual machine

Compiler chuyển DSL thành bytecode. Gói runtime chứa virtual machine, thư viện chuẩn và artifact:

~~~text
deployment/
├── dsl-vm
├── runtime-libraries/
├── manifest.json
└── program.bytecode
~~~

VM đọc instruction và thực hiện chúng. Bytecode có thể nhỏ hơn source sau khi bỏ comment, trivia và thông tin chỉ dùng cho editor. Nó cũng có thể giúp chuẩn hóa cách thực thi giữa các nền tảng.

VM phải quản lý instruction set, stack hoặc register, kiểu giá trị, exception, module và phiên bản bytecode. Nếu compiler sinh bytecode mới mà runtime cũ không hiểu, artifact không thể chạy hoặc có thể bị diễn giải sai.

### 5.3. Runtime cho mã đã biên dịch trước

Compiler có thể sinh mã nguồn của ngôn ngữ chủ hoặc mã native. Artifact vẫn có thể phụ thuộc vào runtime library:

~~~text
DSL source
    -> compiler
    -> generated host code
    -> linker
    -> executable + required runtime libraries
~~~

Runtime library có thể cung cấp kiểu DSL, xử lý lỗi, scheduler, serialization hoặc API host. Cách này phù hợp khi cần hiệu năng cao hoặc muốn tích hợp với hệ sinh thái nền tảng.

### 5.4. Runtime nhúng (embedded runtime)

Runtime được đóng gói thành thư viện để ứng dụng chủ khởi tạo và gọi qua API:

~~~text
Host application
    |
    +-- create runtime
    +-- load DSL artifact
    +-- provide host services
    +-- invoke entry point
    +-- collect result
    +-- dispose runtime
~~~

Ứng dụng chủ kiểm soát vòng đời, cấu hình, quyền và cách trao đổi dữ liệu. Runtime cần định nghĩa rõ API, ownership của object, xử lý exception và thread-safety.

### 5.5. Runtime như một dịch vụ riêng

Một dịch vụ runtime có thể chạy độc lập qua HTTP, gRPC hoặc message queue. Ứng dụng khác gửi artifact hoặc yêu cầu đánh giá, nhận kết quả và diagnostics.

Mô hình này giúp tách tiến trình và giới hạn môi trường thực thi. Đổi lại, cần xử lý xác thực, phân quyền, mạng, timeout, retry, tính sẵn sàng và cách cô lập các tenant.

## 6. Thành phần bên trong một runtime độc lập

Một runtime cho DSL có thể bao gồm nhiều thành phần:

~~~mermaid
flowchart TD
    A[Runtime API / CLI] --> B[Artifact loader]
    B --> C[Version and integrity checks]
    C --> D[Execution engine]
    D --> E[Value and type system]
    D --> F[Standard library]
    D --> G[Scheduler]
    D --> H[Host capability bridge]
    D --> I[Error and diagnostics]
    D --> J[Resource manager]
    H --> K[Host application / OS]
~~~

### 6.1. Artifact loader

Loader đọc file hoặc dữ liệu artifact, xác định định dạng, phiên bản, entry point và các module phụ thuộc. Nó cần kiểm tra kích thước, cấu trúc và integrity trước khi cấp dữ liệu cho execution engine.

### 6.2. Execution engine

Execution engine thực thi AST, bytecode, IR hoặc mã đã được liên kết. Nó quản lý frame, stack, instruction pointer, trạng thái chương trình và luồng điều khiển tùy kiến trúc.

### 6.3. Value và type system

Runtime cần biểu diễn các kiểu mà DSL hỗ trợ: số, chuỗi, boolean, list, record, object miền, optional, function hoặc reference. Quy tắc so sánh, chuyển kiểu và equality lúc chạy phải phù hợp với ngữ nghĩa đã được compiler kiểm tra.

### 6.4. Standard library

Thư viện chuẩn cung cấp các hàm và kiểu tích hợp như toán học, chuỗi, ngày giờ, collection, serialization hoặc truy vấn. Runtime cần bảo đảm thư viện chuẩn có phiên bản tương thích với artifact.

### 6.5. Host capability bridge

Bridge kết nối chương trình DSL với dịch vụ của ứng dụng chủ: đọc cấu hình, truy cập dữ liệu, ghi log hoặc gọi API. Không nên để chương trình DSL truy cập tùy ý toàn bộ đối tượng nội bộ của host.

### 6.6. Resource manager

Resource manager quản lý bộ nhớ, file handle, socket, task, transaction và tài nguyên cần giải phóng. Nó có thể áp dụng quota và timeout theo từng lần chạy.

### 6.7. Error và diagnostics

Runtime cần chuyển lỗi thực thi thành cấu trúc có thể quan sát được: loại lỗi, vị trí source nếu artifact giữ mapping, stack trace, correlation ID và ngữ cảnh phù hợp.

## 7. Artifact thực thi và manifest

Runtime độc lập thường nhận một **artifact** đã được đóng gói. Artifact có thể là source, AST đã serialize, bytecode, IR hoặc executable. Một manifest mô tả định dạng và yêu cầu runtime.

Ví dụ manifest khái niệm:

~~~json
{
  "artifactFormat": "example-dsl-bytecode",
  "artifactVersion": 3,
  "languageVersion": "2.1",
  "minimumRuntimeVersion": "2.4",
  "entryPoint": "main",
  "modules": ["stdlib.core", "stdlib.math"],
  "capabilities": ["logging", "read-config"],
  "target": {
    "os": "linux",
    "architecture": "x86_64"
  }
}
~~~

Các trường trên chỉ là ví dụ thiết kế. Hợp đồng thật cần xác định:

- Loại artifact và phiên bản định dạng.
- Phiên bản ngôn ngữ hoặc grammar liên quan.
- Phiên bản runtime tối thiểu và tối đa nếu có.
- Entry point hoặc danh sách module cần nạp.
- Các thư viện và extension cần thiết.
- Capability mà chương trình yêu cầu.
- Target platform nếu artifact phụ thuộc nền tảng.
- Hash, chữ ký hoặc metadata xác thực nếu cần.

Manifest giúp runtime từ chối artifact không tương thích trước khi thực thi. Nó cũng hỗ trợ hệ thống triển khai chọn đúng image hoặc runtime version.

## 8. Thiết kế định dạng artifact

Định dạng artifact cần phù hợp với mô hình thực thi.

### 8.1. Source DSL

Ưu điểm là dễ đọc, dễ sửa và có thể giữ comment. Runtime cần parser và semantic analysis đủ để xử lý source. Nếu source do người dùng cung cấp, phải xem nó là đầu vào không đáng tin cậy.

### 8.2. AST đã serialize

AST có thể tránh bước parse lại và giữ cấu trúc chương trình. Tuy nhiên, định dạng AST thường gắn với phiên bản compiler hoặc grammar. Cần quản lý schema version và không giả định AST của mọi phiên bản đều tương thích.

### 8.3. Bytecode hoặc IR

Bytecode/IR thường phù hợp khi runtime có VM ổn định. Artifact có thể gọn và dễ thực thi hơn source. Cần version instruction set, kiểu dữ liệu, module reference và quy tắc xác thực.

### 8.4. Mã nguồn hoặc mã máy được sinh ra

Artifact có thể là mã của ngôn ngữ chủ hoặc executable. Nó có thể tận dụng compiler/linker nền tảng nhưng cần quản lý ABI, thư viện liên kết và target platform.

| Artifact | Runtime cần gì? | Điểm cần quản lý |
|---|---|---|
| Source DSL | Parser và evaluator/compiler | Grammar, source validation |
| Serialized AST | AST loader và engine | AST schema, language version |
| Bytecode/IR | VM hoặc IR executor | Instruction set, runtime ABI |
| Host source | Host compiler hoặc binary đã build | Host language/runtime version |
| Native executable | OS và thư viện runtime cần thiết | CPU, ABI, dynamic libraries |

Không có định dạng tốt nhất cho mọi DSL. Lựa chọn phụ thuộc khả năng cập nhật chương trình, yêu cầu hiệu năng, mức độ tin cậy của source và nền tảng triển khai.

## 9. API của runtime và vòng đời thực thi

Nếu runtime được nhúng hoặc cung cấp dưới dạng thư viện, cần có API ổn định để ứng dụng chủ sử dụng.

Một API khái niệm:

~~~java
RuntimeOptions options = RuntimeOptions.builder()
    .timeout(Duration.ofSeconds(5))
    .memoryLimit(64 * 1024 * 1024)
    .build();

try (DslRuntime runtime = DslRuntime.create(options)) {
    runtime.registerCapability("read-config", configProvider);
    Program program = runtime.load(Path.of("pricing.bundle"));
    Value result = program.invoke("calculate", input);
    System.out.println(result);
}
~~~

Đây là pseudocode minh họa, không phải API của một thư viện cụ thể. Nó thể hiện các bước thường cần:

1. Tạo runtime với cấu hình và giới hạn.
2. Đăng ký capability hoặc dịch vụ host được phép.
3. Nạp và xác thực artifact.
4. Gọi entry point hoặc hàm được export.
5. Nhận kết quả hoặc lỗi.
6. Giải phóng tài nguyên.

### 9.1. Runtime lifecycle

Một vòng đời có thể gồm:

- **Created:** runtime được tạo nhưng chưa nạp chương trình.
- **Configured:** capability, thư viện và policy đã được đăng ký.
- **Loaded:** artifact đã được xác thực và nạp.
- **Running:** một hoặc nhiều invocation đang thực thi.
- **Stopping:** ngừng nhận công việc mới và chờ hoặc hủy tác vụ đang chạy theo policy.
- **Disposed:** tài nguyên đã được giải phóng.

API cần quy định thao tác nào hợp lệ ở mỗi trạng thái. Ví dụ, không nên gọi invoke sau dispose; không nên thay đổi capability giữa một invocation nếu việc đó làm mất tính nhất quán.

### 9.2. Quản lý invocation

Một runtime có thể giữ trạng thái toàn cục cho nhiều lần gọi hoặc tạo context riêng cho từng invocation. Cần xác định:

- Biến và trạng thái nào được chia sẻ giữa các lần gọi?
- Invocation có độc lập và an toàn đồng thời không?
- Exception có làm hỏng toàn bộ runtime hay chỉ invocation hiện tại?
- Có thể hủy một invocation mà không ảnh hưởng các invocation khác không?
- Artifact có được unload hoặc thay phiên bản khi đang chạy không?

## 10. Runtime nhúng và ranh giới với ứng dụng chủ

Khi nhúng DSL vào ứng dụng, runtime không hoạt động trong khoảng trống. Nó chia sẻ process, bộ nhớ, thread và tài nguyên với host.

Một hợp đồng tích hợp nên xác định:

- Cách host khởi tạo và hủy runtime.
- Cách truyền input và nhận output.
- Kiểu dữ liệu nào được trao đổi trực tiếp.
- Cách chuyển exception hoặc cancellation.
- Quy tắc ownership của object và buffer.
- Thread-safety và concurrency.
- Capability nào được expose.
- Cách host cung cấp logger, clock, storage hoặc network.

Ví dụ host có thể đăng ký một dịch vụ đọc cấu hình:

~~~text
runtime.registerCapability(
    name = "read-config",
    inputType = ConfigKey,
    outputType = Optional<String>,
    handler = hostConfigProvider
)
~~~

Chương trình DSL chỉ gọi capability đã đăng ký. Runtime kiểm tra kiểu input/output, quyền sử dụng và giới hạn gọi. Cách này tạo ranh giới rõ giữa ngôn ngữ và ứng dụng chủ.

### 10.1. Tránh phụ thuộc ngược vào compiler

Runtime không nên cần truy cập compiler project, parser generator hoặc thư mục source của toolchain chỉ để thực thi artifact. Nếu runtime dùng chung một thư viện với compiler, nên tách phần API và implementation cần thiết thành module runtime riêng, có dependency graph rõ.

### 10.2. Không để lộ implementation nội bộ của host

Nếu DSL có thể truy cập mọi object của ứng dụng chủ, runtime khó bảo đảm tương thích và bảo mật. Nên expose interface nhỏ, có kiểu và capability rõ, thay vì toàn bộ object graph.

## 11. Thư viện chuẩn và extension

Một DSL có thể cung cấp thư viện chuẩn như:

- Core: kiểu cơ bản, equality, conversion và collection.
- Math: phép toán, thống kê và đơn vị.
- Text: xử lý chuỗi và pattern.
- Time: ngày giờ, duration và timezone.
- Data: serialization, schema và truy vấn.
- Workflow: task, event, retry và scheduling.
- Logging: log có cấu trúc và diagnostic context.

Runtime cần xác định thư viện nào là bắt buộc và thư viện nào là extension tùy chọn. Nếu artifact gọi hàm trong stdlib, runtime phải có implementation tương thích.

### 11.1. Extension API

Extension cho phép host hoặc plugin bổ sung hàm và kiểu miền. Extension cần có:

- Định danh và phiên bản.
- Chữ ký hàm hoặc schema kiểu.
- Capability yêu cầu.
- Quy tắc đăng ký và khởi tạo.
- Chính sách tương thích với runtime.
- Cơ chế xử lý lỗi và giải phóng tài nguyên.

Không nên tự động nạp mọi plugin tìm thấy trên filesystem. Runtime cần một allowlist hoặc cơ chế tin cậy phù hợp.

### 11.2. Tương thích thư viện

Thay đổi chữ ký hàm, kiểu trả về hoặc ngữ nghĩa một hàm chuẩn có thể làm artifact cũ đổi hành vi. Manifest nên ghi phiên bản library hoặc API profile mà artifact yêu cầu.

## 12. Tương thích phiên bản giữa compiler và runtime

Compiler và runtime có thể được phát hành độc lập. Vì vậy, cần một chính sách tương thích rõ ràng.

Ví dụ:

- Compiler 2.5 sinh bytecode format 3.
- Runtime 2.4 chỉ hỗ trợ bytecode format 2.
- Runtime 2.6 hỗ trợ format 2 và 3.

Trong trường hợp đó, artifact mới không thể chạy trên runtime 2.4. Loader nên phát hiện và báo lỗi tương thích trước khi thực thi.

### 12.1. Những phiên bản cần quản lý

Một hệ thống có thể có nhiều version riêng:

- Language version: phiên bản cú pháp và ngữ nghĩa DSL.
- Compiler version: phiên bản công cụ sinh artifact.
- Artifact format version: schema hoặc instruction format.
- Runtime version: phiên bản engine.
- Standard library version: phiên bản API tích hợp.
- Extension ABI/API version: hợp đồng plugin.

Không nên dùng một số version duy nhất để đại diện cho tất cả nếu các thành phần có vòng đời khác nhau.

### 12.2. Chính sách tương thích

Có thể quy định:

- Runtime mới đọc được artifact cũ trong một khoảng version.
- Runtime cũ từ chối artifact mới hơn.
- Artifact ghi minimum runtime version.
- Breaking change cần tăng artifact format hoặc language version.
- Migration được thực hiện ở build-time thay vì tự sửa artifact trong production.
- Extension chỉ được nạp khi ABI/API tương thích.

### 12.3. Kiểm tra trước khi chạy

Loader có thể kiểm tra manifest, version, module và capability trước khi tạo execution context. Nếu không tương thích, lỗi cần nêu phiên bản yêu cầu và phiên bản runtime hiện tại.

Ví dụ:

~~~text
Artifact requires runtime >= 2.6.
Current runtime version: 2.4.
Upgrade the runtime or rebuild the artifact for a supported target.
~~~

## 13. Đóng gói và phân phối runtime

Runtime có thể được phân phối theo nhiều cách.

### 13.1. Executable độc lập

Đóng gói engine cùng thư viện cần thiết thành một executable hoặc một thư mục triển khai. Cách này đơn giản cho vận hành qua command line hoặc service manager.

### 13.2. Thư viện nhúng

Phân phối library theo hệ sinh thái của host, chẳng hạn JAR, NuGet package hoặc native library. Host chịu trách nhiệm khởi tạo runtime và quản lý vòng đời.

### 13.3. Container image

Container image chứa runtime, thư viện, cấu hình mặc định và artifact hoặc cách tải artifact. Nó giúp chuẩn hóa filesystem và user-space dependencies giữa các môi trường.

Container vẫn dùng kernel của host và cần cấu hình network, volume, identity và resource limit. Container không tự động làm chương trình an toàn nếu capability và quyền hệ điều hành vẫn quá rộng.

### 13.4. Gói cài đặt theo nền tảng

Có thể tạo package cho Windows, Linux hoặc macOS. Cần xác định target OS, CPU architecture, thư viện native và quy trình cập nhật.

### 13.5. So sánh

| Cách phân phối | Điểm mạnh | Điều cần quản lý |
|---|---|---|
| Executable | Dễ chạy và tự động hóa | Native dependencies, cập nhật |
| Library | Tích hợp trực tiếp vào host | ABI/API, lifecycle, thread-safety |
| Container | Môi trường user-space nhất quán | Image size, kernel, volume, network |
| Package cài đặt | Tích hợp hệ điều hành | Nhiều target và quy trình upgrade |
| Runtime service | Cô lập process, dùng chung engine | Mạng, auth, availability, tenancy |

## 14. Khởi động, nạp artifact và hiệu năng

Thời gian khởi động và thời gian thực thi là hai loại chi phí khác nhau. Runtime độc lập có thể cần:

- Khởi tạo engine và thư viện chuẩn.
- Đọc manifest và xác thực artifact.
- Nạp module hoặc giải mã bytecode.
- Resolve symbol và chuẩn bị function table.
- Tạo execution context.
- Thực hiện invocation.

Với workload ngắn hoặc serverless, startup latency có thể quan trọng. Với workload dài, throughput và chi phí mỗi invocation có thể quan trọng hơn.

Các kỹ thuật có thể dùng:

- Lazy loading cho module chưa cần.
- Cache artifact đã xác thực hoặc module đã nạp.
- Reuse runtime instance nếu lifecycle cho phép.
- Precompile hoặc AOT compilation cho phần ổn định.
- Tối ưu representation của value và instruction.
- Đặt giới hạn cache để không tiêu tốn bộ nhớ vô hạn.

Cache phải gắn với artifact identity và runtime/library version. Không nên tái sử dụng kết quả compile hoặc module đã nạp nếu dependency tương ứng đã thay đổi.

## 15. Quản lý bộ nhớ và tài nguyên

Runtime có thể chạy nhiều chương trình hoặc nhiều invocation trong cùng process. Vì vậy, cần quản lý tài nguyên theo phạm vi rõ ràng.

### 15.1. Bộ nhớ

Tùy ngôn ngữ triển khai, runtime có thể dùng:

- Garbage collection.
- Reference counting.
- Ownership và lifetime tường minh.
- Arena hoặc region allocation.
- Quản lý object theo invocation.

Điều quan trọng là object không bị giữ lại ngoài vòng đời cần thiết và runtime có thể giới hạn bộ nhớ cho một chương trình.

### 15.2. File, socket và handle

Nếu DSL được phép mở file hoặc kết nối mạng, runtime cần kiểm soát:

- Path hoặc endpoint được phép.
- Số lượng handle đồng thời.
- Timeout và cancellation.
- Cleanup khi invocation kết thúc hoặc lỗi.
- Giới hạn dung lượng đọc/ghi.

### 15.3. Task và thread

Nếu DSL hỗ trợ async hoặc parallel execution, runtime cần scheduler và quy tắc cancellation. Cần xác định tác vụ con có bị hủy khi invocation cha thất bại không, exception được truyền về đâu và tài nguyên nào được chia sẻ.

### 15.4. Quota theo invocation

Runtime có thể đặt giới hạn:

- Thời gian CPU.
- Thời gian wall-clock.
- Số instruction hoặc bước đánh giá.
- Bộ nhớ.
- Số task đồng thời.
- Số lần gọi capability.
- Kích thước input/output.

Quota giúp một chương trình lỗi hoặc độc hại không chiếm toàn bộ tài nguyên của host.

## 16. Bảo mật và sandbox

Chương trình DSL có thể do người dùng, tenant hoặc hệ thống bên ngoài cung cấp. Runtime phải xem artifact và input là dữ liệu cần kiểm tra, kể cả khi artifact đã qua compiler.

### 16.1. Capability-based security

Một cách thiết kế là chỉ cấp cho chương trình những capability đã được cho phép:

~~~text
runtime policy:
    allow logging
    allow read-config
    deny arbitrary-file-write
    deny process-spawn
    allow database-query with read-only credentials
~~~

Chương trình chỉ có thể thực hiện thao tác qua capability được runtime hoặc host đăng ký. Quyền không nên được suy ra từ tên hàm trong source.

### 16.2. Sandbox

Sandbox có thể giới hạn:

- Filesystem path.
- Network destination.
- System call hoặc process creation.
- Bộ nhớ và CPU.
- Module và extension được phép nạp.
- Quyền truy cập secret.

Sandbox ở cấp runtime cần phối hợp với cơ chế cô lập của hệ điều hành hoặc container khi chương trình có thể gọi mã native hay thư viện bên ngoài.

### 16.3. Artifact integrity

Runtime có thể kiểm tra hash hoặc chữ ký để xác nhận artifact không bị thay đổi sau khi build hoặc phát hành. Chữ ký cần gắn với trust policy và key management của hệ thống.

### 16.4. Extension không đáng tin cậy

Plugin chạy trong cùng process có thể có quyền tương đương runtime host. Nếu extension đến từ nguồn không tin cậy, cần cô lập process hoặc sandbox phù hợp, không chỉ dựa vào interface plugin.

### 16.5. Phục hồi sau lỗi

Runtime cần xử lý exception, timeout, cancellation và lỗi host service. Một invocation lỗi không nên làm hỏng trạng thái của các invocation khác nếu kiến trúc cam kết isolation.

## 17. Tính xác định và khả năng tái hiện

Với DSL dùng cho rule, tính toán hoặc workflow, cùng một input có thể cần tạo cùng một kết quả. Runtime nên xác định các nguồn không xác định:

- Đồng hồ hệ thống và timezone.
- Random number generator.
- Thứ tự iteration của collection.
- Scheduling và concurrency.
- Trạng thái database hoặc API bên ngoài.
- Locale và định dạng số.

Nếu cần reproducibility, runtime có thể nhận clock, random seed và external service mock từ host; ghi lại version artifact, cấu hình và input; hoặc dùng execution trace để tái hiện lỗi.

Không phải mọi DSL đều cần deterministic execution. Với workflow tương tác hoặc hệ thống phân tán, một số kết quả phụ thuộc thời gian và trạng thái bên ngoài. Điều quan trọng là xác định phần nào được bảo đảm và phần nào phụ thuộc môi trường.

## 18. Logging, tracing và diagnostics lúc chạy

Runtime độc lập thường chạy ngoài môi trường phát triển, vì vậy cần khả năng quan sát đủ để vận hành.

Các thông tin có thể ghi:

- Runtime version và artifact ID.
- Invocation ID hoặc correlation ID.
- Entry point và thời điểm bắt đầu/kết thúc.
- Thời gian CPU và wall-clock.
- Số instruction hoặc số bước xử lý nếu có.
- Capability được gọi.
- Kết quả thành công, lỗi, timeout hoặc cancellation.
- Source span nếu artifact giữ debug mapping.

Không nên log toàn bộ input hoặc secret theo mặc định. Cần có chính sách che dữ liệu nhạy cảm và giới hạn kích thước log.

### 18.1. Source mapping

Nếu compiler loại bỏ source structure hoặc tạo bytecode, runtime có thể giữ mapping từ instruction tới source span. Khi lỗi xảy ra, runtime có thể hiển thị:

~~~text
pricing.dsl:18:12
Division by zero while evaluating discountRatio.
Invocation: 8f...
Artifact: pricing-rules-2026-04
~~~

Mapping có thể được đóng gói riêng để giảm kích thước artifact production hoặc được giữ đầy đủ trong bản debug.

## 19. Cập nhật chương trình và triển khai nhiều phiên bản

Một runtime service có thể cần chạy nhiều phiên bản artifact cùng lúc. Ví dụ, một số request tiếp tục dùng rule version cũ trong khi request mới dùng rule version mới.

Các chiến lược:

- **Replace in place:** nạp bản mới rồi chuyển toàn bộ invocation mới sang bản đó.
- **Versioned artifacts:** giữ nhiều phiên bản và chọn theo tenant, request hoặc cấu hình.
- **Blue/green deployment:** chạy hai nhóm runtime, chuyển traffic sau khi kiểm tra.
- **Canary:** chuyển một phần nhỏ traffic sang artifact mới trước khi mở rộng.

Runtime cần quy định thời điểm unload bản cũ. Không được giải phóng module hoặc object mà invocation đang chạy vẫn sử dụng.

### 19.1. Rollback

Artifact và runtime version nên được phát hành theo cách có thể xác định lại bản trước. Rollback cần xem xét cả schema dữ liệu, side effect đã xảy ra và compatibility của runtime. Quay lại artifact cũ không thể tự đảo ngược một thao tác database hoặc triển khai đã thực hiện.

## 20. Kiểm thử runtime độc lập

Kiểm thử runtime cần xác nhận artifact chạy đúng trong môi trường mục tiêu và không phụ thuộc ngầm vào toolchain phát triển.

### 20.1. Kiểm thử độc lập với compiler

Tạo artifact trong build environment, sau đó đưa artifact cùng runtime package sang một môi trường sạch chỉ có các phụ thuộc đã công bố. Kiểm tra chương trình chạy mà không cần compiler hoặc IDE.

### 20.2. Kiểm thử tương thích

- Artifact cũ trên runtime mới trong khoảng hỗ trợ.
- Artifact mới trên runtime cũ phải bị từ chối rõ ràng nếu không tương thích.
- Standard library và extension đúng version.
- Target OS/CPU phù hợp.
- Manifest thiếu hoặc sai trường.

### 20.3. Kiểm thử vòng đời

- Tạo và dispose runtime.
- Nạp artifact hợp lệ và không hợp lệ.
- Gọi entry point nhiều lần.
- Hủy invocation.
- Xử lý exception và timeout.
- Giải phóng file, socket và task.

### 20.4. Kiểm thử cô lập và tài nguyên

- Chương trình không thể dùng capability bị cấm.
- Quota bộ nhớ và thời gian được thực thi.
- Artifact hỏng không làm crash host.
- Invocation lỗi không ảnh hưởng invocation khác theo cam kết isolation.
- Input quá lớn hoặc cấu trúc bất thường được xử lý có kiểm soát.

### 20.5. Kiểm thử hiệu năng

Đo riêng startup, load artifact, thời gian invocation, throughput, memory footprint và chi phí bridge host. Cần dùng workload đại diện cho cách runtime được triển khai.

## 21. Ví dụ thiết kế một runtime độc lập cho DSL rule

Giả sử DSL cho phép định nghĩa quy tắc giảm giá:

~~~text
rule "bulk-discount" {
    when order.quantity >= 10
    then order.discountRate = 0.15
}
~~~

Một kiến trúc có thể gồm:

1. Compiler parse và kiểm tra rule.
2. Compiler resolve order và quantity theo schema đã biết.
3. Compiler kiểm tra kiểu Decimal, Integer và Boolean.
4. Compiler sinh bytecode hoặc serialized rule model.
5. Build tạo artifact cùng manifest và phiên bản standard library.
6. Runtime độc lập nạp artifact.
7. Host cung cấp Order input và capability cần thiết.
8. Runtime đánh giá điều kiện.
9. Nếu điều kiện đúng, runtime tạo kết quả hoặc effect theo policy.
10. Host áp dụng thay đổi vào transaction của ứng dụng.

Sơ đồ:

~~~mermaid
flowchart TD
    A[Rule source] --> B[DSL compiler]
    B --> C[Semantic checks]
    C --> D[Rule artifact + manifest]
    D --> E[Standalone rule runtime]
    F[Host application] --> G[Input and capabilities]
    G --> E
    E --> H[Evaluation result]
    H --> F
~~~

Runtime không cần quyền ghi database trực tiếp nếu host muốn kiểm soát transaction. Nó có thể trả về một kết quả mô tả discountRate mới; host quyết định có commit hay không.

### 21.1. Hợp đồng đầu vào và đầu ra

Một hợp đồng đơn giản có thể là:

~~~text
Input:
    order.quantity: Integer
    order.discountRate: Decimal

Output:
    decision: Boolean
    proposedChanges:
        order.discountRate: Decimal
~~~

Hợp đồng giúp host và runtime độc lập với cấu trúc object nội bộ của nhau. Schema có version và có thể được kiểm tra khi load artifact.

### 21.2. Chính sách capability

Rule có thể chỉ cần đọc order và trả đề xuất thay đổi. Runtime không cần quyền truy cập filesystem, network hoặc process. Nếu một rule cần gửi thông báo, host có thể cung cấp capability send-notification riêng và giới hạn phạm vi sử dụng.

## 22. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Runtime phụ thuộc compiler project | Production phải cài toolchain không cần thiết | Tách module runtime và API tối thiểu |
| Không có manifest hoặc version | Artifact có thể được nạp bởi runtime không tương thích | Ghi artifact format và minimum runtime version |
| Cho rằng native code không cần runtime | Thiếu thư viện hỗ trợ hoặc ABI lúc chạy | Tài liệu hóa runtime dependencies |
| Nạp plugin tùy ý | Tăng nguy cơ thực thi mã không tin cậy | Allowlist, ký số hoặc cô lập process |
| Expose toàn bộ host object graph | DSL phụ thuộc implementation và có quyền quá rộng | Dùng capability bridge có kiểu |
| Không giới hạn tài nguyên | Một invocation có thể làm cạn bộ nhớ hoặc CPU | Đặt quota, timeout và cancellation |
| Không định nghĩa lifecycle | Rò rỉ tài nguyên hoặc dùng runtime sau dispose | Quy định trạng thái và ownership |
| Không giữ source mapping | Khó chẩn đoán lỗi trong production | Đóng gói debug metadata phù hợp |
| Chia sẻ trạng thái giữa invocation ngoài dự kiến | Dữ liệu rò rỉ giữa request hoặc tenant | Tách execution context và xác định state scope |
| Cập nhật artifact đang được sử dụng | Invocation cũ có thể lỗi hoặc đọc module đã unload | Quản lý version và lifecycle của artifact |
| Dùng container như ranh giới bảo mật duy nhất | Process vẫn có thể có quyền host quá rộng | Kết hợp OS isolation, capability và quota |
| Không thử trên môi trường sạch | Phụ thuộc ngầm chỉ xuất hiện khi triển khai | Kiểm thử package trong target environment |

## 23. Quy trình thiết kế và triển khai runtime độc lập

Một quy trình thực tế có thể gồm:

1. **Xác định người tiêu thụ:** runtime được gọi từ CLI, thư viện host, service hay worker?
2. **Chọn mô hình thực thi:** interpreter, AST evaluator, bytecode VM, IR executor hay mã native.
3. **Tách build-time và run-time:** quyết định parser, compiler và validator nào không cần có trong production.
4. **Định nghĩa artifact:** format, manifest, entry point, module, debug mapping và integrity metadata.
5. **Định nghĩa runtime API:** lifecycle, load, invoke, result, exception và dispose.
6. **Xác định host boundary:** input/output, capability, ABI và ownership.
7. **Đóng gói thư viện:** standard library, extension và native dependencies.
8. **Thiết lập version policy:** language, compiler, artifact, runtime, stdlib và extension.
9. **Thiết kế bảo mật:** sandbox, capability, quota, xác thực artifact và isolation.
10. **Thiết kế vận hành:** logging, tracing, health check, metrics, update và rollback.
11. **Kiểm thử môi trường sạch:** xác nhận không cần toolchain phát triển.
12. **Tài liệu hóa target support:** OS, CPU, host runtime, dependency và quy trình nâng cấp.

Kết quả của quy trình không chỉ là một executable. Nó là hợp đồng triển khai có thể kiểm chứng giữa compiler, artifact, runtime, ứng dụng chủ và môi trường vận hành.

## 24. Tiêu chí của một runtime độc lập tốt

Một runtime độc lập tốt thực thi artifact theo đúng ngữ nghĩa DSL, có phụ thuộc được công bố, có API và lifecycle rõ ràng, đồng thời cung cấp các giới hạn cần thiết để chạy an toàn trong môi trường đích.

Các câu hỏi quan trọng:

- Runtime có cần parser/compiler khi chạy hay chỉ cần artifact đã chuẩn bị?
- Artifact format và phiên bản runtime được xác định như thế nào?
- Thư viện chuẩn và extension nào bắt buộc?
- Host truyền dữ liệu và capability qua hợp đồng nào?
- Runtime quản lý invocation, bộ nhớ, task và tài nguyên ra sao?
- Chương trình được phép truy cập filesystem, network và service nào?
- Timeout, cancellation và quota được thực thi ở đâu?
- Lỗi runtime được ánh xạ về source và quan sát như thế nào?
- Có thể cập nhật hoặc rollback artifact mà không làm hỏng invocation đang chạy không?
- Gói triển khai có chạy được trong môi trường sạch với các phụ thuộc đã công bố không?

Runtime độc lập tách việc phát triển ngôn ngữ khỏi việc vận hành chương trình DSL. Khi artifact, API, versioning, capability và lifecycle được thiết kế rõ, compiler có thể phục vụ quá trình xây dựng trong khi runtime nhỏ gọn và có kiểm soát đảm nhận việc thực thi ở production, trong ứng dụng chủ hoặc trên nhiều nền tảng được hỗ trợ.
