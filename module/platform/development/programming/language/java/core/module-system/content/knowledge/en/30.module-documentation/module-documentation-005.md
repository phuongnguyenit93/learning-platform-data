# Module graph trong tài liệu kiến trúc

Khi thiết kế một ứng dụng Java dùng Java Platform Module System (JPMS), sơ đồ package hay danh sách dependency Maven/Gradle chưa đủ mô tả các ranh giới giữa những phần của hệ thống. JPMS tổ chức code thành các **named module**, liên kết chúng bằng directive **requires** và kiểm soát việc truy cập API qua **exports**, **opens** và quan hệ readability. Trong những kiến trúc có service provider hoặc custom ModuleLayer, tập module xuất hiện lúc chạy còn phụ thuộc vào root modules, ModuleFinder và cấu hình runtime.

Một **module graph** có giá trị trong tài liệu kiến trúc phải làm rõ những module nào tồn tại, quan hệ phụ thuộc của chúng, package nào được công bố, provider nào được dùng qua service contract và module nào thực sự được resolve trong từng môi trường chạy. Tài liệu này giúp reviewer đánh giá chiều phụ thuộc, giúp người vận hành khởi chạy đúng cấu hình và giúp lập trình viên biết nơi cần sửa khi một module đổi tên, thay đổi descriptor hoặc bị thiếu ở runtime.

Không nên xem module graph là một bức hình trang trí. Nó cần có định nghĩa rõ ràng, nguồn dữ liệu có thể đối chiếu và quy trình cập nhật cùng source code.

## 1. Mục đích và phạm vi

Một trang kiến trúc module nên giúp trả lời các câu hỏi:

- Hệ thống được chia thành những named module nào? Mỗi module có trách nhiệm gì?
- Module nào là entry point của ứng dụng? Những module nào chỉ là thư viện?
- Chiều dependency giữa các module có đúng layering và ranh giới domain không?
- Quan hệ nào là **requires**, **requires transitive** hoặc **requires static**?
- Module nào là chủ sở hữu API, package nào được export, package nào chỉ là implementation?
- Service nào được dùng bằng **uses**, implementation nào khai báo **provides**?
- Runtime có những root modules nào? Provider modules có thực sự được resolve không?
- Plugin nằm trong boot layer hay custom layer, dùng class loader nào?
- Sự thay đổi module name hoặc package boundary ảnh hưởng tới consumer và cấu hình launcher nào?

Tài liệu có thể gồm một overview graph cho toàn hệ thống và một số graph chi tiết cho từng subsystem. Với hệ thống lớn, nên phân nhóm các module thay vì đưa mọi module của JDK và mọi thư viện vào một sơ đồ quá tải.

Module graph **không thay thế** module-info.java: descriptor vẫn là nguồn thực thi của module system. Tài liệu bổ sung ý nghĩa kiến trúc và giải thích vì sao những ranh giới đó được lựa chọn.

## 2. Phân biệt các loại graph

Không phải mọi mũi tên giữa hai module đều mang cùng ngữ nghĩa. Nên ghi **Graph type** ở ngay đầu sơ đồ.

| Loại graph | Nguồn xác định | Ý nghĩa |
|---|---|---|
| Declared dependency graph | Các directive requires trong descriptor | Module nào trực tiếp khai báo phụ thuộc module nào |
| Resolved module graph | Root set, module finder, module configuration | Module nào được đưa vào cấu hình runtime |
| Readability graph | Quy tắc JPMS và bổ sung tại runtime | Module nào có thể đọc module nào |
| Service relationship graph | uses và provides | Consumer cần service type nào và module nào cung cấp |
| ModuleLayer topology | Cấu hình parent/child layer và class loader | Module được định nghĩa trong runtime context nào |

Một đồ thị **requires** không tự biểu diễn quyền deep reflection. Một đồ thị **uses/provides** không chứng minh consumer có **requires** tới module provider. Một JAR có thể quan sát trên module path nhưng chưa thuộc resolved graph.

Trong tài liệu nên tách những góc nhìn này, hoặc sử dụng nhãn và legend thật rõ nếu cần kết hợp vào một hình.

## 3. Node và edge phải dựa trên module name

Một node của declared dependency graph thường đại diện cho module name lấy từ module descriptor:

~~~java
module com.acme.orders.app {
    requires com.acme.orders.api;
    requires java.logging;
}
~~~

Các node liên quan:

- **com.acme.orders.app**: ứng dụng điều phối.
- **com.acme.orders.api**: hợp đồng API.
- **java.logging**: system module do Java runtime cung cấp.

Hai cạnh đi từ **com.acme.orders.app** tới **com.acme.orders.api** và **java.logging**, bởi đó là chiều được khai báo trong requires. Không đảo chiều mũi tên theo hướng “module thư viện phục vụ ứng dụng”; điều này sẽ khiến đồ thị dependency gây hiểu nhầm.

Node nên dùng **JPMS module name**, không dùng tên file JAR hoặc Maven artifactId làm nhãn chính. Ví dụ:

~~~text
JPMS module name: com.acme.orders.api
Maven coordinates: com.acme:orders-contract:2.1.0
Artifact filename: orders-contract-2.1.0.jar
Source descriptor: modules/orders-contract/src/main/java/module-info.java
~~~

Ba tên có thể giống nhau một phần, nhưng không bắt buộc trùng. Tên module và package cũng là hai khái niệm khác nhau. Module có thể sở hữu nhiều package; package được công bố hay không lại do exports/opens quyết định.

## 4. Ví dụ module graph cho hệ thống báo cáo

Giả sử hệ thống có bốn module ứng dụng và hai module provider:

- **com.acme.report.app**: điểm vào ứng dụng, điều phối yêu cầu xuất báo cáo.
- **com.acme.report.api**: public API và service interface ReportExporter.
- **com.acme.report.csv**: implementation xuất CSV.
- **com.acme.report.json**: implementation xuất JSON.

Descriptor API:

~~~java
module com.acme.report.api {
    exports com.acme.report.api;
}
~~~

Descriptor của app:

~~~java
module com.acme.report.app {
    requires com.acme.report.api;
    requires java.logging;

    uses com.acme.report.api.ReportExporter;
}
~~~

Descriptor CSV provider:

~~~java
module com.acme.report.csv {
    requires com.acme.report.api;

    provides com.acme.report.api.ReportExporter
        with com.acme.report.csv.CsvReportExporter;
}
~~~

Descriptor JSON provider:

~~~java
module com.acme.report.json {
    requires com.acme.report.api;

    provides com.acme.report.api.ReportExporter
        with com.acme.report.json.JsonReportExporter;
}
~~~

Ứng dụng chỉ phụ thuộc interface và API. Việc thêm provider JSON không bắt buộc app khai báo requires tới implementation JSON. Chính sự độc lập này là một quyết định kiến trúc cần được thể hiện rõ trong tài liệu.

## 5. Vẽ declared requires graph bằng Mermaid

Markdown trong repository có thể chứa nguồn sơ đồ Mermaid để người đọc review như source code.

~~~mermaid
flowchart LR
    App["com.acme.report.app"]
    Api["com.acme.report.api"]
    Csv["com.acme.report.csv"]
    Json["com.acme.report.json"]
    Logging["java.logging"]

    App -->|"requires"| Api
    App -->|"requires"| Logging
    Csv -->|"requires"| Api
    Json -->|"requires"| Api
~~~

Sơ đồ này chỉ biểu diễn **declared requires graph**. Nó không nói rằng provider CSV/JSON đã được resolve vào boot layer, cũng không khẳng định app có direct requires tới provider.

Nên đặt bên cạnh sơ đồ một đoạn metadata:

~~~text
View: declared requires graph
Scope: report application modules
Entry module: com.acme.report.app
Source: module-info.java của từng module
JDK target: phiên bản JDK trong build/release
Runtime variant: chưa biểu diễn service binding
Owner: nhóm phụ trách kiến trúc report
~~~

Nếu không hỗ trợ Mermaid, có thể render thành hình nhưng vẫn giữ file nguồn Mermaid/DOT trong repository. Sơ đồ chỉ lưu dưới dạng ảnh thường khó diff, review và bảo trì.

## 6. Ghi khác biệt giữa requires, transitive và static

Các modifier trong descriptor thay đổi cách các module kết nối.

Ví dụ:

~~~java
module com.acme.shop.facade {
    requires transitive com.acme.shop.api;
    requires static com.acme.annotations;
    requires java.logging;
}
~~~

Tài liệu nên phân biệt:

- **requires**: dependency bắt buộc trực tiếp trong module configuration.
- **requires transitive**: dependency bắt buộc đồng thời truyền readability theo quy tắc JPMS tới những module đọc facade.
- **requires static**: dependency cần ở compile time nhưng có thể vắng mặt ở runtime; code vẫn phải quản lý những nhánh thực thi cần nó.

Sơ đồ:

~~~mermaid
flowchart LR
    Facade["com.acme.shop.facade"]
    Api["com.acme.shop.api"]
    Anno["com.acme.annotations"]
    Log["java.logging"]

    Facade -->|"requires transitive"| Api
    Facade -.->|"requires static"| Anno
    Facade -->|"requires"| Log
~~~

Nét đứt là quy ước của tài liệu cho **requires static**, không phải cú pháp JPMS. Phần legend cần giải thích điều đó.

Không đổi một edge từ requires sang requires transitive chỉ để giảm số dòng requires của consumer. Modifier transitive thường phản ánh API được công bố và có ảnh hưởng tới downstream modules.

## 7. Readability không đồng nghĩa với package access

Một named module đọc được module khác không đồng nghĩa nó có thể truy cập mọi class public trong module kia.

Ví dụ:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Và:

~~~java
module com.acme.web {
    requires com.acme.customer;
}
~~~

**com.acme.web** có readability tới **com.acme.customer**, nhưng package **com.acme.customer.internal** không được export. Consumer không thể import class trong package nội bộ chỉ vì có requires.

Vì thế, tài liệu cần thêm bảng package boundary:

| Module nguồn | Package | Directive | Phạm vi truy cập |
|---|---|---|---|
| com.acme.customer | com.acme.customer.api | exports | Các named module đọc được customer |
| com.acme.customer | com.acme.customer.spi | exports ... to com.acme.integrations | Consumer được chỉ định |
| com.acme.customer | com.acme.customer.model | opens ... to com.acme.json | Deep reflection từ framework chỉ định |
| com.acme.customer | com.acme.customer.internal | Không export/open | Implementation nội bộ |

Các quyền cần phân biệt:

- **exports**: cho phép truy cập các kiểu public trong package với điều kiện readability.
- **qualified exports**: chỉ export cho các named module được chỉ định.
- **opens**: cho phép deep reflection tại runtime cho phạm vi nêu trong descriptor.
- **qualified opens**: mở package cho một số module reflection cụ thể.
- **open module**: mở các package ở phạm vi rộng hơn và cần được ghi nhận là quyết định kiến trúc.

Không vẽ cạnh **requires** chỉ vì một module sở hữu package mở cho framework khác. Đó là quan hệ cấp quyền reflection, không nhất thiết là dependency từ module nguồn đến framework.

## 8. Vẽ service graph riêng với dependency graph

Service graph minh họa quan hệ consumer và provider qua một **service type**:

~~~mermaid
flowchart LR
    App["com.acme.report.app"]
    Contract["ReportExporter"]
    Csv["com.acme.report.csv"]
    Json["com.acme.report.json"]

    App -->|"uses"| Contract
    Csv -->|"provides"| Contract
    Json -->|"provides"| Contract
~~~

Trong tài liệu, cần ghi rõ rằng đường **provides** không thay thế dependency **requires** của provider tới API module. Tương tự, app khai báo **uses** không có nghĩa app trực tiếp đọc module implementation.

Khi ứng dụng chạy, provider module cần được resolve ở layer thích hợp. Một phương án là chọn provider làm root với **--add-modules**; một phương án khác trong cấu hình lập trình là **Configuration.resolveAndBind(...)** để bổ sung provider module theo những service được sử dụng.

Mỗi runtime variant nên ghi:

~~~text
Service contract: com.acme.report.api.ReportExporter
Consumer: com.acme.report.app
Providers: com.acme.report.csv, com.acme.report.json
Provider discovery: ServiceLoader
Provider resolution: root thêm hoặc service binding
Service API owner: com.acme.report.api
~~~

Không dùng một cạnh service để diễn đạt rằng provider đã tồn tại trong runtime graph; cần có bằng chứng resolution riêng nếu tài liệu muốn khẳng định điều đó.

## 9. Phân biệt observable và resolved modules

JAR nằm trên module path chỉ có nghĩa nó **có thể được tìm thấy** bởi cơ chế module finder tương ứng. Module có được đưa vào configuration hay không phụ thuộc root set và quá trình resolution.

Giả sử:

~~~text
dist/modules/
├── com.acme.report.app.jar
├── com.acme.report.api.jar
├── com.acme.report.csv.jar
└── com.acme.report.json.jar
~~~

Nếu chạy chỉ với root **com.acme.report.app**, app sẽ resolve dependency được requires từ nó, nhưng hai provider không mặc nhiên xuất hiện chỉ vì các JAR của chúng ở cùng thư mục.

Vì vậy, tài liệu cần ghi riêng:

- Tập **observable modules** hoặc nguồn finder.
- Root modules được chọn để resolve.
- Dependency closure.
- Provider modules được thêm thông qua service binding hay bổ sung root.
- Module nào thực sự được định nghĩa trong boot layer hoặc custom layer.

Nếu dùng **--limit-modules**, tập module có thể quan sát còn có thể bị giới hạn. Nếu dùng **--add-reads**, graph readability runtime có thể khác những cạnh requires đã khai báo trong descriptor.

Không nên vẽ toàn bộ thư mục JAR như một tập resolved modules mà chưa kiểm tra cấu hình chạy.

## 10. Ghi runtime variant của module graph

Một hệ thống có thể có nhiều graph hợp lệ cho các mục đích khác nhau:

- Application production.
- Application trong integration test.
- Runtime image được tạo bằng jlink.
- Host với CSV plugin.
- Host với JSON và CSV plugin.
- Phần ứng dụng chạy trong custom ModuleLayer.

Nên lập một trang **runtime variants**, mỗi variant có metadata:

~~~text
Variant name: production-report
Entry module: com.acme.report.app
Main class: com.acme.report.app.Main
JDK target: phiên bản trong manifest build
Module path: dist/modules
Root modules: com.acme.report.app
Extra roots: com.acme.report.csv
Service binding: mô tả nếu áp dụng
Runtime image: dist/runtime (nếu có)
VM module flags: danh sách nếu có
~~~

Hai variant có thể dùng cùng source descriptor nhưng khác resolved graph. Khi so sánh thiết kế với runtime, phải nói rõ đang kiểm tra variant nào và artifact thuộc release/commit nào.

Điều này quan trọng khi một lỗi chỉ xảy ra ở CI hoặc trong container, nơi module path và runtime image có thể khác máy phát triển.

## 11. Automatic module và unnamed module trong tài liệu migration

Một dự án đang chuyển từ classpath sang module path có thể chứa nhiều loại module.

| Trạng thái | Cách mô tả trong sơ đồ |
|---|---|
| Explicit named module | Node mang module name từ module-info.class |
| Automatic module | Node mang tên automatic và nhãn **automatic** |
| Unnamed module/classpath | Khối riêng mang nhãn **classpath / unnamed**, không giả làm named module |
| System module | Nhóm module của JDK, ví dụ java.base và java.logging |

Một automatic module là named module nhưng descriptor được tạo tự động; nó có cơ chế tương thích rộng hơn explicit module. Tài liệu nên gắn nhãn để tránh xem phạm vi export của automatic module như một API contract đã được chủ thư viện review.

Một unnamed module không có tên để dùng trong directive **requires**. Không vẽ một cạnh requires thông thường từ explicit named module sang một khối classpath như thể JPMS resolve được unnamed module bằng tên.

Nếu có giải pháp chuyển tiếp qua **--add-reads** hoặc **--add-exports**, ghi đó là escape hatch runtime có owner và thời hạn thu hồi. Nếu bỏ nhãn này, sơ đồ có thể che khuất dependency chưa được modular hóa.

## 12. ModuleLayer topology cho kiến trúc plugin

Trong hệ thống plugin, chỉ declared requires graph thường chưa đủ. Có thể có một boot layer chứa host và API, cùng các child layers chứa provider.

~~~text
Boot layer
├── com.acme.host
└── com.acme.plugin.api

CSV plugin layer
└── com.acme.plugin.csv

JSON plugin layer
└── com.acme.plugin.json
~~~

Sơ đồ topology:

~~~mermaid
flowchart TB
    Boot["Boot layer: host + plugin API"]
    Csv["CSV plugin layer"]
    Json["JSON plugin layer"]

    Boot -->|"parent of"| Csv
    Boot -->|"parent of"| Json
~~~

Các cạnh **parent of** không phải requires. Trong tài liệu nên ghi rõ:

1. ModuleFinder và thư mục artifact của mỗi child layer.
2. Root set và parent configuration.
3. Class loader strategy: một loader chung, nhiều loader hay mapping tùy chỉnh.
4. Module service API được chia sẻ từ layer cha.
5. Cơ chế ServiceLoader tra cứu provider ở layer nào.
6. Quan hệ lifecycle của plugin với host.

Hai module trong các layer độc lập có thể có cùng tên nhưng thuộc các runtime context khác nhau. Không dùng một tên module string như định danh duy nhất cho mọi module object trong toàn JVM.

Các sibling layers không tự động đọc module của nhau. Nếu hai plugin cần cùng API, đặt service contract trong một parent layer phù hợp thay vì copy nhiều bản API vào từng plugin.

## 13. Công cụ đối chiếu tài liệu với module thực tế

Tài liệu kiến trúc nên chỉ ra cách lặp lại các kiểm tra kỹ thuật từ JDK.

### 13.1. Đọc descriptor trong modular JAR

~~~bash
jar --describe-module --file dist/modules/com.acme.report.app.jar
~~~

Dùng để xác nhận module name, requires, exports, opens và service declarations trong artifact đã build. Đây là nguồn tốt để kiểm tra sơ đồ có trùng bản phát hành thực tế hay không.

### 13.2. Quan sát module resolution khi chạy

~~~bash
java --show-module-resolution \
     --module-path dist/modules \
     -m com.acme.report.app/com.acme.report.app.Main
~~~

Output giúp điều tra những module được resolve và quan hệ dependency runtime. Khi thiếu module hoặc graph không hợp lệ, launcher có thể dừng trước main. Cần giữ nguyên tên module và exception để chẩn đoán.

### 13.3. Phân tích dependency bằng jdeps

~~~bash
jdeps --module-path dist/modules \
      --print-module-deps dist/modules/com.acme.report.app.jar
~~~

**jdeps** hỗ trợ phân tích dependency trong bytecode và module metadata. Tuy nhiên, nó không thể mô tả đầy đủ dependency chỉ xuất hiện thông qua reflection, service provider được chọn động hoặc cấu hình runtime bên ngoài bytecode.

Không lấy một output jdeps làm toàn bộ graph kiến trúc mà thiếu giải thích nguồn, cách tạo và giới hạn.

### 13.4. Đọc module graph tại runtime bằng Java API

~~~java
ModuleLayer.boot().modules().stream()
    .map(Module::getName)
    .sorted()
    .forEach(System.out::println);
~~~

Có thể kiểm tra module cụ thể:

~~~java
boolean present = ModuleLayer.boot()
    .findModule("com.acme.report.api")
    .isPresent();
~~~

Các lệnh này phản ánh module trong boot layer hoặc tìm trong parent layers theo API liên quan. Với một custom plugin layer, hãy kiểm tra chính layer đó thay vì giả định boot layer chứa tất cả module đã được định nghĩa trong JVM.

## 14. Mẫu module catalog

Bên cạnh sơ đồ nên có danh mục module có thể tìm kiếm.

| Trường | Ví dụ |
|---|---|
| Module name | com.acme.report.api |
| Responsibility | Report contracts và service types |
| Source path | modules/report-api |
| Artifact | com.acme:report-api |
| Descriptor | modules/report-api/src/main/java/module-info.java |
| Owner | Nhóm duy trì Report API |
| Exported packages | com.acme.report.api |
| Required modules | java.base (implicit) |
| Service contracts | ReportExporter |
| Runtime layer | Boot layer |
| Stability | Public API, được version theo policy |
| References | ADR về service interface, integration tests |

Danh mục này giúp người đọc chuyển từ graph node tới source và owner. Nên dùng đường dẫn tương đối trong repository hoặc liên kết tới tài liệu có version phù hợp, thay vì link tới branch không khớp với release.

Không cần copy nguyên văn descriptor vào mọi trang. Chỉ nên đưa phần quan trọng và chỉ tới file module-info.java để giảm nguy cơ mô tả cũ hơn source.

## 15. Đề xuất cấu trúc tài liệu kiến trúc

Một dự án có thể tổ chức:

~~~text
docs/
└── architecture/
    └── modules/
        ├── README.md
        ├── graph.md
        ├── catalog.md
        ├── packages.md
        ├── services.md
        ├── runtime-variants.md
        └── decisions/
            └── adr-0007-service-providers.md
~~~

Một trang graph nên có ít nhất:

- **Scope**: subsystem, JDK target, application variant và release/commit.
- **Graph definition**: declared requires, readability, service hay runtime resolution.
- **Diagram**: sơ đồ với node module name và chiều cạnh nhất quán.
- **Legend**: requires, transitive, static, service hoặc layer parent.
- **Module catalog**: liên kết tới owner, source descriptor và artifact.
- **Boundary table**: package export/open quan trọng.
- **Runtime differences**: root set, service binding, ModuleLayer và escape hatches.
- **Verification**: lệnh kiểm tra artifact và runtime, link tới CI run.
- **Architecture decisions**: lý do về chiều dependency và kế hoạch migration.

Sơ đồ giúp quan sát nhanh; các bảng và phần giải thích giúp người đọc kiểm tra chính xác. Không nên đưa mọi chi tiết về exports, opens, versions và owner trực tiếp lên từng mũi tên khiến sơ đồ khó đọc.

## 16. Quản lý thay đổi graph cùng source code

Module graph có nguy cơ lỗi thời nếu module-info.java thay đổi mà tài liệu không được cập nhật. Có thể đưa các bước sau vào pull request review:

1. Xác định module descriptor được thay đổi.
2. So sánh tên module và những requires trước/sau.
3. Cập nhật nhãn edge nếu requires đổi thành transitive hoặc static.
4. Cập nhật module catalog khi thêm, xóa hoặc đổi module name.
5. Cập nhật bảng boundary nếu exports hoặc opens thay đổi.
6. Cập nhật service graph khi uses/provides thay đổi.
7. Cập nhật runtime variants nếu root modules hoặc launcher flags thay đổi.
8. Chạy compile/integration tests trên module path của variant liên quan.
9. Kiểm tra downstream consumer bị ảnh hưởng bởi module name hoặc package visibility.
10. Dẫn tới ADR nếu thay đổi làm dịch chuyển ranh giới kiến trúc hoặc chiều dependency.

Những thay đổi lớn cần ghi được lý do. Ví dụ đổi từ app requires provider implementation sang app uses service contract là thay đổi kiến trúc quan trọng, không chỉ sửa hai dòng trong descriptor.

## 17. Sử dụng CI để phát hiện tài liệu lệch

Có thể tự động hóa từng phần:

- Kiểm tra tất cả named modules được phát hành đều có bản ghi catalog.
- So sánh tên module trong artifact với tên module được tài liệu hóa.
- Báo thay đổi requires/exports để reviewer cập nhật graph.
- Phát hiện automatic module mới trong một runtime variant đã có policy explicit-only.
- Kiểm tra các quy tắc phân lớp, ví dụ domain API không phụ thuộc adapter infrastructure.
- Chạy startup test với **--show-module-resolution** cho deployment configuration mục tiêu.
- Chạy integration test cho service provider và custom layer.
- Giữ bằng chứng check gắn với commit và artifact đã build.

Các phép kiểm tra tự động có giới hạn. Tool phân tích bytecode không thể thay thế việc đọc phản hồi từ framework reflection hoặc provider được chọn động. Tài liệu kiến trúc vẫn cần sự giải thích của người chịu trách nhiệm về module boundary.

## 18. Những lỗi tài liệu thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Vẽ node bằng JAR filename | Nhầm module name với artifact | Đọc tên từ module-info.class |
| Đảo chiều requires | Hiểu sai dependency direction | Vẽ từ consumer tới dependency |
| Vẽ uses như requires tới provider | Sai quan hệ service | Tách service graph |
| Không ghi transitive/static | Mất ý nghĩa readability/compile dependency | Gắn modifier lên cạnh |
| Gộp exports và opens thành một loại | Nhầm API access với reflection | Dùng bảng package boundary |
| Giả định tất cả JAR trên path đều resolved | Runtime graph sai | Ghi root set và kiểm tra resolution |
| Coi unnamed module như named node | Giấu dependency classpath | Gắn nhãn migration boundary |
| Không vẽ layer topology khi có plugin | Không rõ module identity/runtime context | Ghi parent layers và class loaders |
| Chỉ có PNG tĩnh | Khó diff và review | Giữ nguồn Mermaid/DOT |
| Không gắn graph với release/JDK | Người đọc không biết sơ đồ nào đang đúng | Bổ sung source revision và runtime variant |
| Không chỉ ra cách kiểm tra graph | Khó dùng cho troubleshooting | Đính kèm lệnh JDK và CI artifact |

Một tài liệu graph đáng tin cậy phải cho phép người đọc đi từ sơ đồ đến descriptor và artifact thật, chứ không chỉ đưa ra nhận xét “module A phụ thuộc module B” không rõ thời điểm.

## 19. Đánh giá ảnh hưởng khi sửa kiến trúc

Giả sử nhóm muốn bỏ một export của module **com.acme.report.api**. Từ dependency graph, có thể tìm các module có readability tới API module. Nhưng chỉ có readability chưa chứng minh module nào đang import class cụ thể từ package đó; cần kết hợp source search và compile tests.

Nếu đổi tên module, cần cập nhật:

- Directive requires của các consumer.
- --module/-m và --add-modules trong script khởi chạy.
- ModuleFinder root names trong code tạo custom layer.
- Build plugin, jlink configuration và tài liệu runtime variants.
- Các test kiểm tra module name hoặc service provider resolution.

Nếu thay đổi một **requires** thành **requires transitive**, đồ thị phải cập nhật nhãn edge và giải thích tác động tới downstream readability. Nếu bổ sung provider mới, app có thể không đổi requires nhưng service graph và runtime configuration có thể đổi.

Graph là công cụ tìm vị trí cần đánh giá, không tự khẳng định mọi consumer đều bị ảnh hưởng về source code.

## 20. Bài tập thực hành

1. Tạo module API, app và hai provider như ví dụ report.
2. Vẽ declared dependency graph bằng Mermaid.
3. Vẽ service relationship graph riêng, phân biệt uses/provides với requires.
4. Thêm một module facade dùng **requires transitive** rồi cập nhật legend.
5. Thêm dependency **requires static** và giải thích giới hạn runtime.
6. Lập bảng exports, qualified exports và opens cho một module demo.
7. Đóng gói thành modular JAR, dùng **jar --describe-module** để kiểm tra.
8. Chạy app với **--show-module-resolution** rồi so sánh với sơ đồ.
9. Thử thêm provider bằng **--add-modules** và ghi runtime variant mới.
10. Đặt một provider vào custom ModuleLayer, vẽ topology parent/child.
11. Tạo một node automatic module có nhãn migration rõ ràng.
12. Thay đổi module name trong descriptor, liệt kê tài liệu và consumer cần cập nhật.
13. Tạo một CI check nhận biết thay đổi requires trong artifact.
14. Viết ADR giải thích vì sao app phụ thuộc API thay vì implementation.
15. Review graph để phát hiện dependency đi ngược hướng kiến trúc mong muốn.

## 21. Những nguyên tắc cần ghi nhớ

- Module graph cần nêu rõ đang thể hiện **declared dependencies**, **resolved modules**, **readability**, **service relationships** hay **layer topology**.
- Node JPMS nên dùng **module name**; Maven coordinates, package và JAR filename là metadata khác.
- **requires**, **requires transitive** và **requires static** cần nhãn khác nhau.
- **exports** và **opens** mô tả package access, không tự tạo requires edge.
- Có mặt trên module path không bảo đảm module đã được resolve.
- Service contract giúp consumer tránh requires trực tiếp provider implementation.
- Automatic module và unnamed module phải được ghi trạng thái đúng khi migration.
- Custom ModuleLayer và class loader cần được giải thích riêng khi có plugin.
- Sơ đồ nên có nguồn Mermaid/DOT và liên kết với module-info.java.
- Tài liệu phải ghi rõ scope, commit/release, JDK, root modules và runtime variant.
- Đối chiếu với artifact và runtime qua **jar --describe-module**, **jdeps**, **--show-module-resolution** và integration tests.
- Cập nhật graph cùng module descriptor để tránh lệch với thiết kế thật.

**Module graph trong tài liệu kiến trúc cần trả lời được: module nào phụ thuộc module nào, quyền truy cập nào được công bố và runtime nào thực sự kết nối chúng.** Khi đồ thị có định nghĩa rõ ràng và có thể đối chiếu với descriptor, nó trở thành công cụ hữu ích cho code review, migration, troubleshooting và quản lý ranh giới hệ thống.