# Plugin trong hệ sinh thái DSL

Một ngôn ngữ đặc tả miền (Domain-Specific Language, DSL) thường bắt đầu với một tập cú pháp, kiểu dữ liệu và thao tác đủ dùng cho một miền cụ thể. Khi nhu cầu tăng lên, người dùng có thể cần thêm hàm miền, validator, bộ sinh mã, định dạng file, kết nối dữ liệu hoặc tính năng hỗ trợ trong editor. Nếu mọi khả năng đều được đưa trực tiếp vào lõi ngôn ngữ, compiler và runtime sẽ ngày càng lớn, khó phát hành và khó tùy chỉnh cho từng dự án.

**Plugin** là một đơn vị mở rộng được nạp bởi một ứng dụng chủ (*host*) thông qua một hợp đồng đã xác định. Trong hệ sinh thái DSL, plugin có thể bổ sung hàm dựng sẵn, kiểu miền, phép kiểm tra, backend sinh mã, adapter dữ liệu, công cụ dòng lệnh hoặc tính năng cho language server. Lõi DSL cung cấp API và vòng đời; plugin triển khai phần mở rộng theo API đó.

Plugin giúp một DSL có thể phát triển theo mô-đun. Nhóm phát triển ngôn ngữ giữ lõi ổn định, còn nhóm ứng dụng có thể cài đặt những phần mở rộng phù hợp với miền của họ. Tuy nhiên, plugin cũng tạo ra những vấn đề về tương thích, phụ thuộc, bảo mật, quyền thực thi và khả năng tái tạo build. Vì vậy, thiết kế plugin cần xác định rõ hợp đồng, phạm vi quyền và cách quản lý vòng đời.

## 1. Plugin là gì?

### 1.1. Khái niệm

Plugin là một thành phần phần mềm được thiết kế để mở rộng chức năng của một chương trình khác. Nó không hoạt động độc lập hoàn toàn: plugin cần một host cung cấp môi trường, API và quy tắc nạp.

Trong một công cụ DSL:

- Host có thể là compiler, interpreter, runtime, IDE hoặc CLI.
- Plugin cung cấp một hay nhiều khả năng mở rộng.
- Plugin API định nghĩa cách host và plugin trao đổi dữ liệu.
- Manifest mô tả định danh, phiên bản, dependency và capability.
- Plugin manager chịu trách nhiệm tìm, kiểm tra, nạp và dỡ plugin.

Ví dụ, một DSL quy tắc đơn hàng có thể có lõi hỗ trợ biểu thức, kiểu và rule. Plugin commerce bổ sung kiểu Money, hàm tính thuế và validator đơn hàng. Plugin SQL backend bổ sung khả năng chuyển IR thành truy vấn SQL.

### 1.2. Plugin khác thư viện như thế nào?

Thư viện thường được ứng dụng gọi trực tiếp thông qua API mà ứng dụng chủ động sử dụng. Plugin thường được host phát hiện và nạp theo một cơ chế mở rộng; host gọi các điểm đăng ký hoặc callback do plugin cung cấp.

| Khía cạnh | Thư viện | Plugin |
|---|---|---|
| Ai khởi tạo lời gọi? | Thường là ứng dụng | Thường là host thông qua extension point |
| Cách được phát hiện | Dependency hoặc import | Registry, manifest hoặc cấu hình plugin |
| Vòng đời | Theo cách ứng dụng sử dụng | Có thể có initialize, activate và dispose |
| Mục tiêu | Cung cấp API tái sử dụng | Mở rộng host theo hợp đồng |
| Quyền | Thường theo quyền của tiến trình gọi | Có thể được host cấp capability riêng |

Một plugin vẫn có thể đóng gói hoặc sử dụng nhiều thư viện. Ranh giới quan trọng là plugin tuân theo cơ chế mở rộng của host.

### 1.3. Plugin khác cấu hình

Cấu hình thay đổi cách một chức năng có sẵn hoạt động, chẳng hạn đặt giới hạn discountRate tối đa là 0.2. Plugin có thể thêm một chức năng mới, chẳng hạn hàm calculateLoyaltyPoints hoặc backend tạo mã cho một nền tảng.

Không nên tạo plugin cho mọi giá trị cấu hình. Nếu chỉ cần đổi tham số, cấu hình thường đơn giản và dễ quản lý hơn.

### 1.4. Plugin khác fork

Fork tạo một nhánh mã nguồn riêng của host hoặc DSL. Plugin mở rộng host thông qua API mà không cần duy trì bản sao của lõi. Plugin thường dễ cập nhật hơn fork, nhưng chỉ mở rộng được những điểm mà host đã công bố.

## 2. Vai trò của plugin trong DSL

### 2.1. Bổ sung hàm và kiểu miền

Một DSL tổng quát có thể chỉ biết các kiểu số, chuỗi và Boolean. Plugin miền có thể đăng ký:

- Money và Currency.
- CustomerId và OrderStatus.
- Các hàm calculateTax, canRefund hoặc estimateShipping.
- Các phép toán và quy tắc so sánh theo miền.

Nhờ đó, người viết DSL sử dụng khái niệm gần với nghiệp vụ mà không phải đưa mọi kiểu vào lõi.

### 2.2. Thêm validator

Plugin có thể kiểm tra quy tắc đặc thù:

- Tỷ lệ giảm giá không vượt giới hạn.
- Một workflow phải có trạng thái kết thúc.
- Hai tài khoản chuyển tiền phải khác nhau.
- Một trường bắt buộc phải được khai báo trong schema.

Validator có thể chạy lúc biên dịch, lúc nạp mô hình hoặc lúc thực thi, tùy loại thông tin mà nó cần.

### 2.3. Thêm backend hoặc code generator

Một DSL có thể có backend sinh Java mặc định. Plugin backend khác có thể sinh SQL, bytecode hoặc cấu hình cho một nền tảng triển khai. Host cung cấp IR ổn định; plugin chuyển IR sang target tương ứng.

### 2.4. Kết nối nguồn dữ liệu

Plugin có thể cung cấp adapter cho database, API, message broker hoặc catalog dữ liệu. DSL có thể tham chiếu nguồn dữ liệu qua một abstraction thống nhất.

### 2.5. Mở rộng editor và language server

Plugin có thể đăng ký completion provider, tài liệu hover, semantic token classification, formatter hoặc code action cho một nhóm cú pháp hay schema.

### 2.6. Thêm công cụ và tích hợp

Plugin CLI có thể thêm lệnh kiểm tra, migrate hoặc export. Plugin IDE có thể thêm preview, diagram hoặc thao tác triển khai. Các phần mở rộng này nên dùng chung model và diagnostic của DSL core khi phù hợp.

## 3. Các loại plugin thường gặp

| Loại plugin | Khả năng mở rộng | Ví dụ |
|---|---|---|
| Language extension | Hàm, kiểu, toán tử hoặc cú pháp bổ sung | Kiểu Money và phép cộng tiền |
| Semantic validator | Kiểm tra quy tắc miền | Kiểm tra trạng thái workflow |
| Runtime provider | Cung cấp hàm hoặc dịch vụ lúc chạy | Kết nối hệ thống thanh toán |
| Compiler backend | Sinh mã hoặc artifact cho target | Backend SQL hoặc bytecode |
| Data connector | Đọc và ghi dữ liệu | Adapter PostgreSQL |
| Editor integration | Completion, hover, code action | Gợi ý field theo schema |
| Formatter/linter | Quy tắc định dạng và phong cách | Chuẩn hóa rule |
| CLI extension | Lệnh và workflow công cụ | Lệnh export model |
| Deployment adapter | Triển khai hoặc đóng gói | Adapter cho container platform |
| Observability extension | Log, trace và metrics | Theo dõi thời gian thực thi rule |

Một plugin có thể đảm nhiệm nhiều vai trò, nhưng manifest và API nên làm rõ những capability mà nó đăng ký.

## 4. Kiến trúc host và plugin

### 4.1. Thành phần chính

Một hệ thống plugin thường có:

- **Host:** ứng dụng quản lý và gọi plugin.
- **Plugin API:** hợp đồng kiểu và hàm mà plugin được phép sử dụng.
- **Plugin implementation:** mã triển khai khả năng mở rộng.
- **Manifest:** metadata và yêu cầu dependency.
- **Registry:** tập plugin đã được phát hiện hoặc đăng ký.
- **Plugin manager:** kiểm tra tương thích, nạp, kích hoạt và dỡ plugin.
- **Capability policy:** quy định tài nguyên plugin được phép truy cập.

### 4.2. Sơ đồ kiến trúc

~~~mermaid
flowchart TD
    A["DSL Host"] --> B["Plugin Manager"]
    B --> C["Manifest and Dependency Resolver"]
    C --> D["Compatibility and Trust Checks"]
    D --> E["Plugin Runtime"]
    E --> F["Plugin A"]
    E --> G["Plugin B"]
    E --> H["Plugin C"]
    F --> I["Extension Registry"]
    G --> I
    H --> I
    I --> J["Compiler / Runtime / Editor Services"]
~~~

Plugin manager kiểm tra metadata và dependency trước khi plugin được phép đăng ký chức năng. Extension registry lưu các khả năng đã đăng ký để compiler hoặc runtime sử dụng.

### 4.3. In-process plugin

Plugin chạy trong cùng tiến trình với host. Cách này có thể gọi API trực tiếp, ít overhead và dễ chia sẻ object model.

Đổi lại, plugin có thể ảnh hưởng trực tiếp đến bộ nhớ, trạng thái và độ ổn định của host. Một lỗi nghiêm trọng trong plugin có thể làm sập cả tiến trình.

### 4.4. Out-of-process plugin

Plugin chạy trong tiến trình riêng và trao đổi với host qua IPC, RPC hoặc message protocol.

Ưu điểm:

- Cách ly lỗi và tài nguyên tốt hơn.
- Có thể dùng ngôn ngữ lập trình khác.
- Có thể khởi động hoặc dừng độc lập.
- Dễ giới hạn quyền theo process.

Chi phí gồm serialization, độ trễ giao tiếp, quản lý tiến trình và xử lý lỗi kết nối.

### 4.5. WebAssembly hoặc sandbox runtime

Host có thể chạy plugin trong môi trường sandbox như WebAssembly runtime. Host chỉ cấp những import hoặc capability đã cho phép.

Cách này có thể tạo ranh giới thực thi rõ hơn so với plugin native in-process, nhưng sandbox vẫn cần cấu hình giới hạn bộ nhớ, thời gian và quyền truy cập host function.

### 4.6. Chọn mô hình thực thi

| Mô hình | Hiệu năng gọi | Cách ly | Độ phức tạp |
|---|---|---|---|
| In-process native | Thường cao | Thấp | Quản lý ABI và lỗi trong cùng process |
| Out-of-process | Có overhead IPC | Tốt hơn | Protocol và quản lý tiến trình |
| WebAssembly sandbox | Phụ thuộc runtime | Có thể tốt | Host imports, memory và capability |
| Declarative extension | Thường đơn giản | Giới hạn theo định dạng | Khả năng mở rộng ít linh hoạt hơn |

Không có một lựa chọn phù hợp cho mọi plugin. Plugin tin cậy, cần hiệu năng cao có thể chạy in-process; plugin bên thứ ba có thể cần process hoặc sandbox riêng.

## 5. Extension point và plugin API

### 5.1. Extension point là gì?

Extension point là vị trí mà host cho phép plugin bổ sung hành vi. Ví dụ:

~~~text
registerFunctionProvider(...)
registerValidator(...)
registerCodeGenerator(...)
registerDataSource(...)
registerCompletionProvider(...)
~~~

Host gọi những implementation đã đăng ký khi cần. Extension point phải có hợp đồng về input, output, lỗi, vòng đời và concurrency.

### 5.2. Thiết kế API nhỏ và rõ

Plugin API nên chỉ công bố những kiểu và thao tác cần thiết. API quá rộng làm plugin phụ thuộc sâu vào nội bộ host, khiến việc nâng cấp khó khăn.

Ví dụ interface khái niệm:

~~~java
public interface DslPlugin {
    PluginDescriptor descriptor();
    void initialize(PluginContext context);
    void registerExtensions(ExtensionRegistry registry);
    void dispose();
}
~~~

Đây là interface minh họa, không phải một chuẩn chung. Host thực tế cần xác định rõ exception, thread safety, timeout và cách xử lý plugin không tuân thủ hợp đồng.

### 5.3. PluginContext

Host có thể truyền một context chứa:

- Logger được quản lý.
- Cấu hình plugin.
- Registry hoặc service đã được cấp.
- Phiên bản API.
- Cancellation token.
- Capability đã được cấp.
- Đường dẫn workspace trong phạm vi cho phép.

Không nên truyền toàn bộ host internals nếu plugin chỉ cần một vài dịch vụ.

### 5.4. Extension Registry

Registry tiếp nhận các extension và quản lý chúng theo loại:

~~~text
FunctionRegistry
ValidatorRegistry
BackendRegistry
DataConnectorRegistry
EditorFeatureRegistry
~~~

Registry cần kiểm tra tên trùng, chữ ký xung đột và thứ tự ưu tiên. Nếu hai plugin cùng đăng ký một hàm với cùng chữ ký, host phải có quy tắc từ chối hoặc giải quyết rõ ràng.

### 5.5. API ổn định và API nội bộ

Phân biệt:

- Public plugin API: được tài liệu hóa và có chính sách tương thích.
- Internal implementation: có thể thay đổi giữa các phiên bản host.

Plugin chỉ nên dựa vào public API. Nếu phải truy cập internal class để hoạt động, plugin sẽ dễ hỏng khi host nâng cấp.

### 5.6. Không để plugin thay đổi registry tùy tiện

Sau khi quá trình khởi tạo hoàn tất, host có thể đóng băng registry hoặc chỉ cho phép thay đổi trong những giai đoạn xác định. Điều này giúp kết quả compile và runtime ổn định.

## 6. Manifest và metadata plugin

### 6.1. Vai trò manifest

Manifest mô tả plugin mà không cần chạy mã plugin. Plugin manager có thể dùng manifest để tìm, kiểm tra dependency và xác định tương thích trước khi nạp implementation.

### 6.2. Các trường thường có

Một manifest có thể gồm:

- Plugin ID duy nhất.
- Tên hiển thị và mô tả.
- Phiên bản plugin.
- Phiên bản plugin API yêu cầu.
- Phiên bản host tối thiểu và tối đa.
- Entry point hoặc artifact.
- Dependency và phiên bản dependency.
- Capability được yêu cầu.
- Loại plugin.
- Nhà phát hành và thông tin chữ ký.
- Cấu hình mặc định.

### 6.3. Ví dụ manifest

~~~yaml
id: com.example.dsl.commerce
name: Commerce DSL Extension
version: 2.1.0
apiVersion: 3
requires:
  host: ">= 4.0 < 5.0"
  plugins:
    - id: com.example.dsl.money
      version: "^2.0"
entrypoint: plugins/commerce-plugin.jar
capabilities:
  - dsl.functions.register
  - dsl.validators.register
~~~

Đây là schema minh họa. Một hệ thống thật cần định nghĩa cú pháp, quy tắc version range và cách xử lý trường không biết.

### 6.4. Plugin ID

Plugin ID nên ổn định, duy nhất và không phụ thuộc tên hiển thị. Đổi tên sản phẩm không nhất thiết phải đổi ID vì các cấu hình và dependency có thể đang tham chiếu đến nó.

### 6.5. Entry point

Entry point xác định implementation mà host cần nạp. Nó có thể là class, module, executable, WebAssembly module hoặc địa chỉ service tùy mô hình.

Manifest không nên cho phép entry point trỏ tùy tiện ra ngoài package nếu chính sách host yêu cầu plugin tự chứa.

### 6.6. Metadata và dữ liệu nhạy cảm

Manifest không nên chứa secret như API key hoặc mật khẩu. Cấu hình bí mật cần được cung cấp qua secret store hoặc cơ chế an toàn riêng.

## 7. Phát hiện, cài đặt và nạp plugin

### 7.1. Nguồn plugin

Plugin có thể đến từ:

- Thư mục plugin cục bộ.
- Package registry.
- Repository nội bộ.
- Artifact được đóng gói cùng ứng dụng.
- Một dịch vụ plugin từ xa.

Nguồn cần được xác định rõ trong cấu hình và chính sách tin cậy.

### 7.2. Discovery

Plugin manager tìm manifest trong những vị trí đã cấu hình, đọc metadata và xây dựng danh sách plugin có thể sử dụng.

Discovery không nên tự động thực thi implementation. Trước khi nạp, host cần kiểm tra package, dependency, version và trust policy.

### 7.3. Installation

Cài đặt thường gồm:

1. Chọn plugin và phiên bản.
2. Tải hoặc lấy artifact từ nguồn được phép.
3. Xác minh checksum hoặc chữ ký nếu có.
4. Kiểm tra manifest và dependency.
5. Lưu vào vị trí package được quản lý.
6. Ghi nhận nguồn và phiên bản đã cài.

### 7.4. Loading

Loading là bước đưa implementation vào runtime. Với plugin in-process, host có thể dùng class loader hoặc module loader. Với plugin ngoài tiến trình, host khởi chạy process hoặc kết nối đến service. Với sandbox, host tạo instance trong runtime cách ly.

### 7.5. Activation

Plugin có thể được cài nhưng chưa kích hoạt. Activation xảy ra khi host quyết định plugin cần tham gia phiên làm việc hoặc workspace cụ thể.

Tách installation khỏi activation giúp quản lý plugin theo dự án và giảm bề mặt thực thi.

### 7.6. Enable và disable

Một plugin có thể được bật ở một workspace nhưng tắt ở workspace khác. Server cần phân biệt trạng thái cài đặt toàn cục, trạng thái kích hoạt theo user và trạng thái theo project.

### 7.7. Không nạp trùng

Nếu cùng plugin ID và version được phát hiện từ nhiều nguồn, host cần có quy tắc ưu tiên hoặc báo xung đột. Không nên nạp cả hai implementation một cách ngẫu nhiên.

## 8. Vòng đời plugin

### 8.1. Các giai đoạn

Một vòng đời điển hình:

1. Discovered: manifest được phát hiện.
2. Validated: metadata và tương thích được kiểm tra.
3. Resolved: dependency được giải quyết.
4. Loaded: implementation được nạp.
5. Initialized: plugin nhận context và chuẩn bị tài nguyên.
6. Registered: extension được đăng ký với host.
7. Active: plugin phục vụ request.
8. Deactivated: plugin ngừng nhận công việc mới.
9. Disposed: tài nguyên được giải phóng.

Không phải mọi host đều dùng chính xác các trạng thái này. Nhưng ranh giới giữa kiểm tra, nạp, đăng ký và dỡ plugin cần được xác định.

### 8.2. Initialize

Initialize thường dùng để đọc cấu hình, kiểm tra môi trường và chuẩn bị resource. Không nên thực hiện thao tác nghiệp vụ lớn hoặc không thể đảo ngược trong giai đoạn này.

### 8.3. Register extensions

Plugin đăng ký hàm, validator hoặc backend trong giai đoạn được host cho phép. Host có thể kiểm tra chữ ký và phát hiện xung đột trước khi đưa extension vào registry.

### 8.4. Activate

Activation có thể tạo connection pool, mở index hoặc khởi động worker. Những tài nguyên này cần được giới hạn và có cơ chế đóng.

### 8.5. Deactivate và dispose

Khi tắt plugin, host nên:

- Ngừng gửi request mới.
- Hủy hoặc chờ tác vụ đang chạy theo policy.
- Đóng connection và thread.
- Gỡ extension khỏi registry nếu an toàn.
- Giải phóng file handle và resource.
- Ghi nhận lỗi dọn dẹp nếu có.

### 8.6. Lỗi trong lifecycle

Nếu initialize thất bại, plugin không nên được đánh dấu active. Host cần ghi nhận nguyên nhân, giải phóng phần tài nguyên đã tạo và quyết định có tiếp tục khởi động các plugin độc lập hay không.

## 9. Quản lý dependency giữa plugin

### 9.1. Dependency khai báo

Một plugin có thể yêu cầu plugin khác:

~~~text
commerce-plugin -> money-plugin
commerce-plugin -> schema-plugin
sql-backend -> query-ir
~~~

Dependency cần khai báo trong manifest để plugin manager giải quyết trước khi nạp.

### 9.2. Version range

Plugin có thể yêu cầu một khoảng phiên bản. Host cần dùng quy tắc version rõ ràng, thường dựa trên semantic versioning nếu hệ sinh thái áp dụng.

### 9.3. Dependency graph

Plugin manager xây đồ thị phụ thuộc và xác định thứ tự khởi tạo. Nếu A cần B, B phải sẵn sàng trước khi A đăng ký extension phụ thuộc vào B.

### 9.4. Circular dependency

Nếu A phụ thuộc B và B phụ thuộc A, plugin manager cần từ chối hoặc hỗ trợ một mô hình khởi tạo hai pha được định nghĩa rõ. Không nên để thứ tự nạp ngẫu nhiên quyết định kết quả.

### 9.5. Optional dependency

Một plugin có thể hoạt động với tính năng cơ bản mà không cần dependency tùy chọn. Manifest và implementation cần kiểm tra capability trước khi dùng phần mở rộng đó.

### 9.6. Dependency conflict

Hai plugin có thể yêu cầu hai phiên bản không tương thích của cùng một thư viện. Host có thể:

- Từ chối tổ hợp plugin.
- Dùng classloader isolation.
- Chạy plugin ở process riêng.
- Yêu cầu một phiên bản chung tương thích.

Giải pháp phụ thuộc mô hình runtime và chi phí cách ly.

### 9.7. Reproducible dependency resolution

Build hoặc workspace cần khóa phiên bản plugin và dependency để cùng một cấu hình tạo ra cùng tập extension. Không nên tự động lấy latest version trong môi trường production mà không có kiểm soát.

## 10. Đăng ký hàm DSL qua plugin

### 10.1. Function provider

Plugin có thể đăng ký hàm cho DSL:

~~~java
registry.registerFunction(
    "calculateShipping",
    FunctionSignature.of(
        List.of(Type.ORDER),
        Type.MONEY
    ),
    invocation -> shippingService.calculate(
        invocation.argument(0, Order.class)
    )
);
~~~

Đây là API minh họa. API thật cần xác định cách biểu diễn kiểu, đối số, context, lỗi và cancellation.

### 10.2. Chữ ký phải được công bố

Compiler cần biết chữ ký hàm trước khi kiểm tra lời gọi. Nếu plugin chỉ cung cấp implementation lúc runtime nhưng không cung cấp metadata, compiler khó phát hiện lỗi kiểu và completion không thể gợi ý chính xác.

### 10.3. Runtime binding

Sau khi compile, IR có thể lưu function ID hoặc symbol reference. Runtime dùng registry để ánh xạ tham chiếu đó đến implementation của plugin.

Không nên chỉ lưu tên chuỗi nếu tên có thể trùng hoặc bị thay đổi; symbol ID và phiên bản API giúp liên kết ổn định hơn.

### 10.4. Hàm có tác dụng phụ

Plugin cần khai báo nếu hàm đọc hoặc ghi dữ liệu, gọi mạng, truy cập đồng hồ hay tạo hành động bên ngoài. Optimizer không được xem hàm đó là pure nếu chưa có hợp đồng rõ.

### 10.5. Kiểm soát quyền gọi

Host có thể yêu cầu capability cụ thể trước khi đăng ký hoặc thực thi hàm. Ví dụ, plugin gửi email cần quyền Messaging.Send; plugin đọc dữ liệu cần quyền Data.Read trong phạm vi nguồn đã cấu hình.

## 11. Plugin validator và semantic analysis

### 11.1. Validator extension

Validator plugin nhận AST, model hoặc semantic context và kiểm tra một tập quy tắc:

~~~text
validate(rule, semanticContext) -> List<Diagnostic>
~~~

### 11.2. Phân loại validator

- Syntax-level validator: kiểm tra quy tắc cấu trúc bổ sung.
- Type-aware validator: dùng kiểu đã suy luận.
- Domain validator: kiểm tra bất biến nghiệp vụ.
- Security validator: kiểm tra quyền, nguồn dữ liệu hoặc thao tác nguy hiểm.
- Runtime validator: kiểm tra giá trị thực tế trước hành động.

### 11.3. Diagnostic thống nhất

Plugin nên trả diagnostic theo một schema chung gồm code, severity, message, source span và related information. Host chuyển diagnostic sang CLI, IDE hoặc log theo cùng quy tắc.

### 11.4. Validator độc lập và validator phụ thuộc thứ tự

Một số validator có thể chạy độc lập. Validator khác cần symbol hoặc kiểu đã được phân giải. Host cần xác định phase và dependency thay vì chạy mọi validator theo thứ tự tải plugin.

### 11.5. Không cho validator sửa model tùy tiện

Validator thường nên đọc model và phát diagnostic. Nếu plugin cần sửa hoặc normalize model, đó nên là một extension point transformation riêng với hợp đồng, thứ tự và khả năng kiểm tra rõ ràng.

## 12. Plugin backend và code generation

### 12.1. Backend contract

Host có thể cung cấp IR và target configuration cho backend:

~~~text
CodeGenerator.generate(
    validatedIR,
    targetOptions,
    outputSink
)
~~~

Backend cần định nghĩa loại artifact, source mapping, diagnostic và khả năng target hỗ trợ.

### 12.2. Capability target

Không phải mọi backend hỗ trợ mọi tính năng DSL. Plugin backend có thể công bố:

- Các kiểu dữ liệu được hỗ trợ.
- Những node IR được hỗ trợ.
- Khả năng async.
- Transaction hoặc streaming.
- Hạn chế về target version.

Nếu IR chứa tính năng không được hỗ trợ, backend nên phát lỗi cụ thể thay vì bỏ qua node.

### 12.3. Deterministic output

Với cùng IR, plugin version và target configuration, backend nên tạo output xác định. Điều này giúp cache, review và reproducible build.

### 12.4. Output ownership

Backend cần ghi vào output directory do host cấp. Không nên tự ghi tùy ý vào thư mục source hoặc vùng không thuộc project output.

### 12.5. Source map

Backend nên giữ liên kết từ đoạn mã sinh ra về node DSL gốc để diagnostics và debug có thể truy ngược.

## 13. Plugin connector và truy cập dữ liệu

### 13.1. Data source abstraction

Một DSL có thể mô tả nguồn dữ liệu qua abstraction:

~~~text
source customers: CustomerStore
source orders: OrderStore
~~~

Plugin connector cung cấp implementation để đọc dữ liệu từ hệ thống cụ thể.

### 13.2. Contract dữ liệu

Connector cần công bố:

- Schema hoặc metadata.
- Kiểu dữ liệu.
- Khả năng query/filter.
- Transaction support.
- Pagination hoặc streaming.
- Authentication method.
- Timeout và retry behavior.
- Error mapping.

### 13.3. Lazy connection

Không nhất thiết mở kết nối khi plugin được phát hiện hoặc khởi tạo. Có thể tạo connection khi thực sự cần để giảm thời gian startup và tránh giữ tài nguyên không dùng.

### 13.4. Credential

Credential nên được lấy từ secret provider do host quản lý. Không lưu mật khẩu hoặc token trong manifest hay source DSL.

### 13.5. Consistency và transaction

Hai connector khác nhau có thể có semantics transaction khác nhau. Một DSL workflow không nên giả định nhiều nguồn dữ liệu cùng tham gia một transaction nếu không có distributed transaction hoặc cơ chế bù trừ được hỗ trợ.

### 13.6. Query pushdown

Connector có thể công bố khả năng thực hiện filter, projection hoặc aggregation ở phía nguồn. Query planner dùng metadata đó để chọn kế hoạch, nhưng phải bảo toàn semantics của DSL.

## 14. Plugin cho editor và language server

### 14.1. Editor extension

Plugin có thể thêm:

- Completion item cho hàm và kiểu miền.
- Hover documentation.
- Semantic token classification.
- Code action.
- Formatter.
- Snippet.
- Diagram hoặc preview.

### 14.2. Language server extension

Nếu DSL dùng LSP, host có thể cung cấp extension API nội bộ để plugin đăng ký feature provider. Plugin không nhất thiết giao tiếp LSP trực tiếp; host có thể chuyển request LSP sang API của plugin.

### 14.3. Completion từ plugin

Plugin cung cấp danh sách symbol và metadata. Host kết hợp kết quả từ nhiều provider, lọc theo scope và kiểu rồi trả CompletionItem.

### 14.4. Diagnostics từ plugin

Validator hoặc plugin miền trả diagnostic theo source span. Language server chuyển chúng thành diagnostics của giao thức.

### 14.5. Xung đột provider

Hai plugin có thể cùng cung cấp formatter hoặc completion cho một loại file. Host cần quy tắc chọn provider, kết hợp kết quả hoặc yêu cầu cấu hình ưu tiên.

### 14.6. Không làm chậm thao tác gõ

Plugin editor phải tôn trọng cancellation và timeout. Một provider chậm không nên khiến toàn bộ completion hoặc hover bị treo.

## 15. Thứ tự ưu tiên và xung đột plugin

### 15.1. Trùng tên hàm

Nếu hai plugin đăng ký hàm cùng tên và chữ ký, host có thể:

- Từ chối registration.
- Yêu cầu namespace.
- Chọn provider theo cấu hình tường minh.
- Cho phép overload nếu chữ ký khác và quy tắc resolution rõ.

Không nên chọn plugin nạp sau cùng một cách âm thầm.

### 15.2. Namespace

Namespace giảm nguy cơ trùng tên:

~~~text
commerce.calculateTax(order)
finance.calculateTax(invoice)
~~~

DSL có thể cho phép import alias để rút gọn tên.

### 15.3. Provider priority

Một số extension point cho phép nhiều provider. Host có thể dùng priority, nhưng thứ tự cần được xác định và có thể tái tạo. Priority không nên là cách giải quyết mọi xung đột API.

### 15.4. Thay thế built-in

Nếu plugin muốn thay hàm built-in, host cần có chính sách rõ: cấm, cho phép override theo namespace hoặc yêu cầu cấu hình tường minh. Thay semantics ngầm có thể làm chương trình cũ thay đổi hành vi.

### 15.5. Conflict report

Khi có xung đột, diagnostic nên nêu plugin ID, extension name, chữ ký và nguồn đăng ký để người quản trị biết cách xử lý.

## 16. Phiên bản và tương thích

### 16.1. Nhiều lớp version

Một plugin có thể liên quan đến:

- Plugin version: phiên bản implementation.
- Host version: phiên bản ứng dụng chủ.
- Plugin API version: hợp đồng API.
- DSL language version: phiên bản cú pháp và semantics.
- IR version: phiên bản biểu diễn trung gian.
- Dependency version: phiên bản plugin hoặc thư viện phụ thuộc.

Những phiên bản này không nhất thiết tăng cùng nhau.

### 16.2. Semantic versioning

Nếu hệ sinh thái dùng SemVer:

- MAJOR biểu thị thay đổi không tương thích.
- MINOR thêm tính năng tương thích ngược.
- PATCH sửa lỗi tương thích ngược.

Quy tắc cụ thể cần áp dụng cho public plugin API và manifest. Không nên coi số version là bảo đảm nếu không có chính sách tương thích và kiểm thử.

### 16.3. API compatibility

Thay đổi interface, method signature, lifecycle hoặc semantics có thể phá plugin cũ. Host nên:

- Giữ API cũ trong giai đoạn deprecation nếu có thể.
- Cung cấp migration guide.
- Tăng API major khi phá vỡ hợp đồng.
- Kiểm thử plugin mẫu và plugin consumer.

### 16.4. Language compatibility

Plugin có thể yêu cầu DSL version cụ thể. Một plugin dùng node IR mới không thể chạy trên compiler chỉ hiểu IR cũ nếu không có adapter hoặc migration.

### 16.5. Runtime compatibility

Artifact được compile với plugin version nào cần được xác định. Nếu IR lưu function ID của plugin, runtime cần plugin tương thích để giải quyết ID đó.

### 16.6. Capability-based compatibility

Ngoài version range, host có thể kiểm tra capability cụ thể. Một plugin có thể hoạt động với nhiều host version nếu host cung cấp đủ API cần thiết.

## 17. Đóng gói và phân phối plugin

### 17.1. Package

Plugin package có thể chứa:

- Manifest.
- Implementation.
- Resource và template.
- Documentation.
- License.
- Checksum hoặc chữ ký.
- Dependency metadata.

### 17.2. Package registry

Registry lưu package và metadata để người dùng tìm, cài và cập nhật. Registry có thể là public hoặc nội bộ tổ chức.

### 17.3. Package integrity

Host nên xác minh checksum hoặc chữ ký để phát hiện package bị thay đổi trong quá trình phân phối. Chữ ký cần gắn với nhà phát hành hoặc trust root đã được cấu hình.

### 17.4. Lockfile

Project lockfile có thể khóa plugin ID, version, source và checksum. Nhờ vậy, developer và CI dùng cùng tập plugin.

### 17.5. Reproducible installation

Không nên để plugin manager tự nâng lên bản mới nhất trong mỗi lần build. Phiên bản và nguồn package cần được khóa hoặc quản lý bằng policy.

### 17.6. Offline installation

Môi trường build hoặc triển khai có thể không truy cập registry. Plugin package và dependency có thể được mirror hoặc cache trong repository nội bộ theo chính sách.

### 17.7. Uninstall

Gỡ plugin cần kiểm tra plugin nào đang phụ thuộc vào nó. Host nên từ chối hoặc yêu cầu gỡ các dependent plugin trước nếu thiếu dependency sẽ làm workspace không hợp lệ.

## 18. Discovery và quản lý plugin trong dự án

### 18.1. Global và project-level plugin

Plugin có thể được cài toàn cục cho user hoặc khai báo trong project. Project-level dependency giúp mỗi dự án có môi trường tái tạo được.

### 18.2. Workspace configuration

Một dự án có thể khai báo plugin:

~~~yaml
plugins:
  - id: com.example.dsl.commerce
    version: 2.1.0
  - id: com.example.dsl.sql
    version: 1.4.2
~~~

Đây là ví dụ cấu hình khái niệm. Hệ thống thật cần quy định nguồn package, checksum và cách khóa dependency.

### 18.3. Enablement

Plugin đã cài không nhất thiết được bật. Workspace có thể chọn plugin cần dùng và tắt plugin không liên quan để giảm thời gian startup và bề mặt quyền.

### 18.4. Plugin profile

Một profile có thể nhóm plugin theo mục đích, ví dụ authoring, database migration hoặc production runtime. Profile giúp chọn đúng tập plugin cho từng môi trường.

### 18.5. Không dùng plugin không xác định

Nếu workspace tham chiếu plugin không được cài hoặc không tương thích, host cần báo lỗi có plugin ID và phiên bản yêu cầu. Không nên âm thầm bỏ qua vì kết quả compile có thể thay đổi.

## 19. Cấu hình và quản lý bí mật

### 19.1. Cấu hình plugin

Plugin có thể có cấu hình riêng:

~~~yaml
plugins:
  com.example.dsl.sql:
    dialect: postgresql
    schema: sales
    batchSize: 500
~~~

Host cần validate cấu hình theo schema plugin công bố.

### 19.2. Default và override

Thứ tự ưu tiên có thể gồm default của plugin, cấu hình project, cấu hình môi trường và tham số runtime. Quy tắc cần rõ để kết quả không phụ thuộc thứ tự nạp ngẫu nhiên.

### 19.3. Secret provider

Credential nên được tham chiếu qua key:

~~~yaml
plugins:
  com.example.dsl.sql:
    credentialRef: secret://project/database
~~~

Host giải quyết secret reference và chỉ truyền credential cho plugin khi capability cho phép.

### 19.4. Không ghi secret vào log

Plugin và host cần che giá trị nhạy cảm trong exception, diagnostic và telemetry. Một lỗi kết nối không nên in nguyên connection string có mật khẩu.

### 19.5. Configuration change

Nếu cấu hình thay đổi, host cần xác định plugin có thể reload tại chỗ hay phải deactivate và initialize lại. Những tài nguyên như connection pool cần được đóng đúng cách.

## 20. Bảo mật và sandbox

### 20.1. Plugin là mã có thể thực thi

Cài plugin đồng nghĩa với việc cho phép một thành phần phần mềm chạy trong hoặc bên cạnh host. Plugin có thể có lỗi, hành vi độc hại hoặc dependency bị xâm phạm.

### 20.2. Least privilege

Chỉ cấp quyền tối thiểu mà plugin cần. Ví dụ, plugin formatter không cần quyền truy cập database; plugin đọc schema không cần quyền gửi email.

### 20.3. Capability-based security

Host có thể cấp object hoặc token đại diện cho quyền cụ thể. Plugin chỉ gọi được dịch vụ khi có capability tương ứng.

### 20.4. Process isolation

Chạy plugin trong process riêng giúp giới hạn crash và một số tài nguyên. Tuy nhiên, IPC vẫn cần xác thực peer, kiểm tra message và giới hạn kích thước request.

### 20.5. Sandbox

Sandbox có thể giới hạn:

- File system access.
- Network access.
- Environment variables.
- System calls.
- Bộ nhớ.
- CPU time.
- Số lượng thread hoặc task.

Sandbox cần được cấu hình ở host runtime; chỉ tuyên bố plugin “an toàn” trong manifest không tạo ra ranh giới bảo mật.

### 20.6. Supply chain

Plugin có thể kéo theo dependency khác. Cần kiểm soát nguồn package, checksum, chữ ký, dependency tree và quá trình cập nhật.

### 20.7. Plugin chạy trong compiler

Compiler có thể chạy trên CI với quyền truy cập source và secret. Plugin compile-time không nên được cấp quyền rộng chỉ để đăng ký một validator hoặc backend.

### 20.8. Không thực thi plugin chỉ để đọc metadata

Discovery và compatibility check nên đọc manifest tĩnh trước khi chạy implementation. Điều này giảm nguy cơ thực thi mã không đáng tin khi mở project.

## 21. Độ tin cậy, lỗi và cách ly

### 21.1. Plugin lỗi không nên làm sập toàn bộ host

Với plugin out-of-process, host có thể phát hiện process chết và đánh dấu plugin unavailable. Với plugin in-process, cách ly lỗi khó hơn; API cần giới hạn exception và trạng thái chia sẻ.

### 21.2. Timeout

Extension point nên có timeout hoặc cancellation nếu plugin có thể thực hiện công việc dài. Completion và diagnostics đặc biệt nhạy với độ trễ.

### 21.3. Circuit breaker

Nếu một plugin connector liên tục lỗi, host có thể tạm ngừng gửi request để tránh làm cạn tài nguyên. Sau khoảng thời gian hoặc thao tác kiểm tra, plugin có thể được thử lại.

### 21.4. Retry

Retry chỉ an toàn khi thao tác idempotent hoặc có idempotency key. Không nên tự retry thao tác ghi hoặc thanh toán nếu có nguy cơ thực hiện hai lần.

### 21.5. Error boundary

Host nên chuyển exception plugin thành lỗi có cấu trúc, ghi plugin ID và operation liên quan. Không để stack trace nội bộ hoặc secret bị lộ cho người dùng không có quyền.

### 21.6. Degraded mode

Nếu plugin không bắt buộc, host có thể tiếp tục hoạt động với chức năng cơ bản và báo rõ tính năng nào không khả dụng. Nếu plugin là dependency bắt buộc, host nên dừng thao tác phụ thuộc thay vì cho kết quả thiếu.

## 22. Quan sát và chẩn đoán plugin

### 22.1. Plugin identity trong log

Log cần gắn plugin ID, version, workspace hoặc runtime context để có thể xác định nguồn sự cố.

### 22.2. Metrics

Có thể theo dõi:

- Thời gian initialize và dispose.
- Số request.
- Thời gian trung bình và percentile.
- Số lỗi và timeout.
- Số lần restart.
- Bộ nhớ hoặc CPU nếu host có thể đo.

### 22.3. Diagnostics

Diagnostic về plugin nên nêu:

- Plugin ID và version.
- Extension point bị lỗi.
- Mã lỗi ổn định.
- Vị trí DSL nếu lỗi gắn với một node.
- Hướng xử lý như cài dependency, đổi version hoặc điều chỉnh capability.

### 22.4. Health check

Plugin connector hoặc service có thể cung cấp health check. Health check cần nhẹ, không tạo tác dụng phụ và không được coi là bằng chứng tuyệt đối rằng mọi thao tác sau đó sẽ thành công.

### 22.5. Audit

Việc cài, bật, tắt, nâng cấp và cấp quyền plugin có thể được ghi vào audit log. Điều này hữu ích trong môi trường nhiều người dùng hoặc có yêu cầu quản trị.

## 23. Kiểm thử plugin

### 23.1. Unit test

Kiểm thử logic nội bộ plugin mà không cần host đầy đủ. Các dependency bên ngoài có thể được thay bằng fake hoặc mock.

### 23.2. Plugin contract test

Host có thể cung cấp test suite xác nhận plugin tuân thủ:

- Manifest schema.
- Plugin API version.
- Lifecycle.
- Extension registration.
- Error handling.
- Cancellation và timeout.
- Dispose và giải phóng tài nguyên.

### 23.3. Integration test

Nạp plugin vào host thử nghiệm và xác nhận extension hoạt động qua API thật. Ví dụ, compile một rule có gọi hàm do plugin đăng ký.

### 23.4. Compatibility test

Kiểm thử plugin với các host/API version được công bố hỗ trợ. Có thể chạy matrix CI theo nhiều phiên bản.

### 23.5. Security test

Kiểm tra plugin không truy cập file hoặc network ngoài capability, không vượt giới hạn tài nguyên và không làm lộ secret.

### 23.6. Failure test

Thử plugin initialize thất bại, timeout, crash, trả dữ liệu sai schema hoặc dispose lỗi. Host cần ở trạng thái nhất quán sau mỗi trường hợp.

### 23.7. Reproducibility test

Với cùng lockfile, plugin package và cấu hình, build cần nạp cùng phiên bản và tạo cùng kết quả.

### 23.8. Test nhiều plugin

Kiểm thử tổ hợp plugin để phát hiện xung đột tên, dependency cycle, provider priority và khác biệt thứ tự khởi tạo.

## 24. Ví dụ: plugin bổ sung hàm tính phí vận chuyển

Giả sử DSL core hỗ trợ rule và biểu thức nhưng chưa có hàm shippingCost. Plugin logistics cung cấp hàm đó.

### 24.1. Manifest

~~~yaml
id: com.example.dsl.logistics
name: Logistics Functions
version: 1.3.0
apiVersion: 3
entrypoint: logistics-plugin.jar
capabilities:
  - dsl.functions.register
  - data.shipping.read
~~~

### 24.2. Chữ ký hàm

Plugin công bố:

~~~text
shippingCost(order: Order): Money
~~~

Compiler có thể dùng chữ ký để kiểm tra lời gọi và cung cấp completion.

### 24.3. Implementation khái niệm

~~~java
public final class LogisticsPlugin implements DslPlugin {
    private ShippingService shippingService;

    @Override
    public PluginDescriptor descriptor() {
        return PluginDescriptor.of(
            "com.example.dsl.logistics",
            "1.3.0"
        );
    }

    @Override
    public void initialize(PluginContext context) {
        this.shippingService =
            context.requireService(ShippingService.class);
    }

    @Override
    public void registerExtensions(ExtensionRegistry registry) {
        registry.registerFunction(
            "shippingCost",
            FunctionSignature.of(Type.ORDER, Type.MONEY),
            invocation -> shippingService.calculate(
                invocation.argument(0, Order.class)
            )
        );
    }

    @Override
    public void dispose() {
        // Đóng resource do plugin sở hữu nếu có.
    }
}
~~~

Đây là mã giả theo một API giả định. Implementation thật cần xử lý lỗi, timeout, cancellation, capability và concurrency theo contract của host.

### 24.4. Sử dụng trong DSL

~~~text
rule StandardShipping {
    when order.total < 1000000 VND
    then chargeShipping(shippingCost(order))
}
~~~

### 24.5. Compile-time và runtime

Ở compile-time, compiler cần biết chữ ký shippingCost và kiểu kết quả. Ở runtime, function registry ánh xạ function symbol đến implementation của plugin logistics.

Nếu plugin không có trong runtime deployment hoặc version không tương thích, host cần báo lỗi trước khi thực thi rule phụ thuộc vào nó.

### 24.6. Quyền và lỗi

Plugin chỉ nên nhận quyền đọc dữ liệu vận chuyển cần thiết. Nếu dịch vụ vận chuyển timeout, runtime trả lỗi có cấu trúc và không giả định phí bằng zero.

## 25. Ví dụ: plugin validator cho workflow

Một plugin workflow có thể kiểm tra mọi đường đi đều đến trạng thái kết thúc.

### 25.1. Validator contract

~~~text
interface ModelValidator {
    validate(model: SemanticModel): List<Diagnostic>
}
~~~

### 25.2. Logic kiểm tra

Plugin xây dựng đồ thị trạng thái, tìm các node có thể tiếp cận từ trạng thái bắt đầu và xác định có đường đến trạng thái kết thúc theo quy tắc được chọn hay không.

### 25.3. Diagnostic

~~~text
Code: WORKFLOW_NO_TERMINAL_PATH
Severity: Warning
Message: Trạng thái REVIEW không có đường đến trạng thái kết thúc.
Source: workflow.dsl, dòng 18
~~~

### 25.4. Đăng ký và chạy

Host gọi validator sau khi parse và phân giải các tham chiếu workflow. Plugin chỉ đọc semantic model và trả diagnostics; nó không sửa tài liệu nguồn.

## 26. Những sai lầm thường gặp

### 26.1. Plugin API quá phụ thuộc nội bộ

Nếu plugin cần truy cập class hoặc field nội bộ của host, mỗi lần refactor host có thể làm plugin hỏng. Cần một public API nhỏ và ổn định.

### 26.2. Không khai báo dependency

Plugin có thể hoạt động trên máy phát triển do dependency tình cờ được cài toàn cục nhưng thất bại trên CI. Dependency cần được khai báo và khóa version.

### 26.3. Nạp plugin trước khi kiểm tra trust

Đọc manifest và kiểm tra package trước khi thực thi implementation. Discovery không nên đồng nghĩa với loading.

### 26.4. Cấp quyền quá rộng

Plugin formatter không cần quyền database hoặc network. Capability nên được cấp theo chức năng và phạm vi cần thiết.

### 26.5. Không có lifecycle rõ

Nếu host không biết khi nào plugin được initialize, activate và dispose, resource có thể bị rò rỉ hoặc extension đăng ký trùng.

### 26.6. Xung đột tên được giải quyết ngẫu nhiên

Thứ tự load không nên quyết định plugin nào thắng. Cần namespace, policy hoặc conflict diagnostic.

### 26.7. Không version hóa API

Plugin cũ có thể được nạp với host mới nhưng chạy sai. API version và compatibility check cần là một phần của manifest.

### 26.8. Coi sandbox là bảo đảm tuyệt đối

Sandbox giảm quyền nhưng vẫn cần kiểm tra host imports, resource limits, IPC và dependency. Không nên dựa vào một nhãn sandbox mà bỏ qua threat model.

### 26.9. Cho plugin sửa model không kiểm soát

Transformation cần extension point riêng, thứ tự xác định và validation sau khi biến đổi. Validator thông thường nên chỉ đọc và báo lỗi.

### 26.10. Không test tổ hợp plugin

Hai plugin có thể hoạt động riêng nhưng xung đột khi cùng đăng ký một hàm hoặc yêu cầu dependency khác nhau. Cần test integration cho những tổ hợp được hỗ trợ.

## 27. Quy trình xây dựng hệ thống plugin

Một lộ trình triển khai có thể gồm:

1. **Xác định mục tiêu mở rộng:** liệt kê những phần cần cho plugin và những phần phải thuộc lõi.
2. **Thiết kế extension point:** định nghĩa loại provider, input, output và error contract.
3. **Thiết kế public API:** giữ API nhỏ, rõ và có version.
4. **Định nghĩa manifest:** plugin ID, version, dependency, entry point và capability.
5. **Chọn mô hình thực thi:** in-process, process riêng, sandbox hoặc declarative extension.
6. **Triển khai plugin manager:** discovery, validation, dependency resolution, loading và lifecycle.
7. **Xây registry:** đăng ký và phát hiện xung đột extension.
8. **Thiết lập trust policy:** nguồn package, chữ ký, checksum và quyền.
9. **Quản lý cấu hình:** default, project override và secret provider.
10. **Tích hợp compiler/runtime/editor:** chuyển extension vào các dịch vụ tương ứng.
11. **Thiết kế diagnostics và observability:** log, metrics, health và audit.
12. **Kiểm thử contract:** lifecycle, compatibility, security, failure và integration.
13. **Đóng gói và phân phối:** registry, lockfile và reproducible installation.
14. **Quản lý nâng cấp:** deprecation, migration và rollback.

## 28. Câu hỏi tự đánh giá

1. Plugin khác thư viện và cấu hình như thế nào?
2. Host, plugin API, manifest và plugin manager có trách nhiệm gì?
3. Khi nào nên dùng plugin in-process và khi nào cần process riêng?
4. Extension point là gì và vì sao cần hợp đồng ổn định?
5. Manifest nên chứa những metadata nào?
6. Discovery khác loading và activation như thế nào?
7. Dependency graph giúp xác định thứ tự khởi tạo ra sao?
8. Vì sao plugin API cần version độc lập với DSL version?
9. Plugin function provider cần công bố gì để compiler hỗ trợ type checking?
10. Capability-based security giúp giới hạn quyền plugin như thế nào?
11. Khi hai plugin đăng ký cùng một extension, host nên xử lý ra sao?
12. Lockfile và checksum hỗ trợ reproducible installation như thế nào?
13. Những trường hợp nào cần timeout, cancellation hoặc circuit breaker?
14. Plugin contract test cần kiểm tra những điều gì?

## Kết luận

Plugin là cơ chế mở rộng DSL thông qua những điểm kết nối do host công bố. Plugin có thể bổ sung hàm và kiểu miền, validator, backend, connector dữ liệu, tính năng editor hoặc lệnh công cụ. Một kiến trúc plugin tốt tách lõi khỏi phần mở rộng, dùng manifest để mô tả dependency và capability, đồng thời quản lý discovery, loading, activation và disposal theo vòng đời xác định.

Plugin cũng là mã có thể thực thi và có thể ảnh hưởng đến tính đúng đắn, bảo mật và khả năng tái tạo của hệ thống. Host cần public API có version, dependency resolution xác định, conflict handling, least privilege, sandbox phù hợp, timeout và kiểm thử contract. Khi những quy tắc đó được thiết kế rõ, plugin giúp DSL thích ứng với nhiều miền và môi trường mà không buộc lõi ngôn ngữ phải chứa mọi tính năng.
