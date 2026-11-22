# Đồ thị phụ thuộc

Trong DSL xây dựng và triển khai, **đồ thị phụ thuộc (dependency graph)** là mô hình biểu diễn các thành phần và quan hệ mà một thành phần cần có trước khi được tạo, kiểm tra, đóng gói, chạy hoặc triển khai. Mỗi đỉnh (node) đại diện cho một thành phần như module, thư viện, task build, artifact, dịch vụ hoặc tài nguyên hạ tầng. Mỗi cạnh (edge) biểu diễn một quan hệ có hướng: thành phần này cần thành phần kia, hoặc một thao tác phải hoàn tất trước thao tác khác.

Ví dụ, một ứng dụng DSL có thể cần compiler để chuyển file nguồn thành mã Java; mã Java cần runtime library để biên dịch; ứng dụng được đóng gói thành container image; image cần được triển khai sau khi database và network đã sẵn sàng. Những quan hệ này tạo thành một đồ thị giúp toolchain biết thứ tự xử lý và xác định phần nào cần làm lại khi đầu vào thay đổi.

~~~mermaid
flowchart TD
    A[DSL source] --> B[DSL compiler]
    C[Runtime library] --> D[Compile application]
    B --> D
    D --> E[Application artifact]
    E --> F[Container image]
    G[Base image] --> F
    H[Database service] --> I[Deploy application]
    F --> I
    J[Network] --> I
~~~

Đồ thị phụ thuộc là nền tảng của build orchestration, package resolution, incremental compilation, task scheduling và deployment planning. Nó cho biết quan hệ nào bắt buộc, quan hệ nào chỉ là tùy chọn, thành phần nào có thể chạy song song và thay đổi ở đâu sẽ ảnh hưởng đến phần còn lại. Trong DSL, các quan hệ này cần được mô tả tường minh, có kiểu, có quy tắc phiên bản và được kiểm tra trước khi thực thi.

## 1. Đồ thị phụ thuộc là gì?

Đồ thị là một cấu trúc gồm tập đỉnh và tập cạnh. Với dependency graph, cạnh thường có hướng vì quan hệ “A phụ thuộc vào B” khác với “B phụ thuộc vào A”.

Nếu module application cần module domain, ta biểu diễn quan hệ có hướng giữa hai node theo quy ước của mô hình. Một số công cụ biểu diễn cạnh theo chiều prerequisite-to-dependent để dễ lập lịch. Điều quan trọng là DSL và engine phải thống nhất chiều cạnh và cách đọc nó.

### 1.1. Node

Node đại diện cho một đối tượng trong hệ thống build hoặc deploy. Node có thể chứa:

- ID ổn định và tên hiển thị.
- Loại thành phần: module, package, task, artifact, service hoặc resource.
- Phiên bản hoặc revision.
- Thuộc tính cấu hình.
- Input và output.
- Trạng thái hiện tại.
- Metadata về nguồn gốc và môi trường.

### 1.2. Edge

Edge biểu diễn quan hệ giữa hai node. Một cạnh có thể có nhãn như compile, runtime, requires, before, uses, deploy-after hoặc produces. Edge cũng có thể chứa constraint phiên bản, điều kiện áp dụng hoặc metadata phục vụ lập lịch.

### 1.3. Directed graph

Dependency thường có hướng. Nếu A cần B, việc tạo A có thể phải chờ B. Hướng cạnh giúp xác định predecessor, successor và thứ tự thực hiện.

### 1.4. Directed acyclic graph

Đồ thị có hướng không chu trình (Directed Acyclic Graph, DAG) là đồ thị có hướng không có đường đi nào quay lại node ban đầu. Nhiều build system mô hình hóa task dependency thành DAG để có thể sắp xếp thứ tự thực thi.

### 1.5. Graph không nhất thiết là DAG

Một dependency graph có thể chứa cycle do khai báo sai hoặc do một miền quan hệ thực sự có vòng lặp. Với build task và prerequisite thông thường, cycle thường là lỗi vì không thể tìm thứ tự thực thi tuyến tính đáp ứng tất cả quan hệ.

### 1.6. Graph và cây

Cây là một trường hợp đặc biệt của graph, trong đó mỗi node (trừ root) có đúng một parent theo cấu trúc cây. Dependency graph thường không phải cây: nhiều module có thể cùng phụ thuộc một thư viện, và một module có thể phụ thuộc nhiều module khác.

## 2. Vì sao DSL build và deploy cần dependency graph?

Khi project nhỏ, người dùng có thể chạy vài lệnh theo thứ tự thủ công. Khi project có nhiều module, plugin, thư viện, artifact và dịch vụ, thứ tự này trở nên khó quản lý.

### 2.1. Xác định thứ tự build

Nếu module B cần output của module A, A phải được build trước B. Graph cho phép engine suy ra thứ tự thay vì dựa vào thứ tự file hoặc danh sách do người dùng nhớ.

### 2.2. Tìm phần bị ảnh hưởng

Khi một module thay đổi, engine có thể duyệt các node phụ thuộc gián tiếp để xác định task nào cần chạy lại.

### 2.3. Chạy song song

Hai task không có quan hệ phụ thuộc trực tiếp hoặc gián tiếp có thể được thực thi đồng thời nếu tài nguyên và side effect cho phép.

### 2.4. Phát hiện lỗi cấu hình sớm

Graph giúp phát hiện module không tồn tại, dependency version không tương thích, task cycle, resource thiếu và quan hệ triển khai không hợp lệ trước khi chạy pipeline.

### 2.5. Quản lý dependency bắc cầu

Một module có thể phụ thuộc package A, còn package A phụ thuộc package B. Graph cho biết B cũng nằm trong dependency closure của module ban đầu.

### 2.6. Giải thích kết quả

Khi build hoặc deploy thất bại, graph giúp giải thích vì sao một task được chạy, vì sao artifact cần thư viện nào đó hoặc vì sao một dịch vụ chưa thể triển khai.

## 3. Các loại node trong dependency graph

Một hệ thống build và deploy có thể chứa nhiều loại node. Việc phân loại giúp áp dụng quy tắc phù hợp cho từng loại.

| Loại node | Ví dụ | Vai trò |
|---|---|---|
| Source node | File DSL, schema, resource definition | Đầu vào của quá trình |
| Module node | domain, service, adapter | Đơn vị tổ chức mã và dependency |
| Package node | Thư viện ngoài, plugin | Thành phần có version |
| Task node | parse, compile, test, package | Đơn vị công việc |
| Artifact node | JAR, image, manifest | Kết quả được tạo ra |
| Service node | API, database, broker | Thành phần runtime |
| Resource node | Network, volume, cluster | Tài nguyên triển khai |
| Environment node | dev, staging, production | Phạm vi cấu hình và triển khai |

### 3.1. Source node

Source node đại diện cho file hoặc dữ liệu đầu vào. Nó có thể là DSL source, schema, template, file cấu hình hoặc generated metadata.

### 3.2. Module node

Module gom source, public API, dependency và build configuration thành một đơn vị có thể tái sử dụng. Một module có thể phụ thuộc module khác trong cùng workspace hoặc package ngoài.

### 3.3. Task node

Task là công việc như parse DSL, compile, generate source, run test, package hoặc publish artifact. Task thường có input, output và prerequisite.

### 3.4. Artifact node

Artifact là kết quả của task, ví dụ compiled classes, JAR, executable, container image, deployment manifest hoặc generated documentation. Artifact có thể trở thành input của task hoặc deployment node khác.

### 3.5. Runtime resource node

Resource node đại diện database, network, volume, queue, secret reference, service account hoặc cluster. Trong deployment graph, resource có thể là prerequisite cho service.

### 3.6. Environment node

Environment node xác định phạm vi như development, staging hoặc production. Cùng một service có thể được triển khai ở nhiều environment với cấu hình và dependency khác nhau.

## 4. Các loại cạnh phụ thuộc

Không phải mọi dependency đều có cùng ý nghĩa. Một DSL tốt cần phân biệt loại quan hệ để build engine và deployment engine xử lý đúng.

| Loại cạnh | Ý nghĩa | Ví dụ |
|---|---|---|
| Compile dependency | Cần khi biên dịch | Module A dùng type từ B |
| Runtime dependency | Cần khi chạy | Service dùng runtime library |
| Test dependency | Cần khi kiểm thử | Module dùng test framework |
| Build dependency | Cần để thực hiện build task | Compiler plugin |
| Plugin dependency | Cần plugin hoặc extension | Code generator plugin |
| Task ordering | Task này phải hoàn tất trước task kia | Generate trước compile |
| Artifact dependency | Một artifact cần artifact khác | Image chứa application JAR |
| Service dependency | Một service cần service khác | API cần database |
| Resource dependency | Cần resource hạ tầng | Service cần network |
| Optional dependency | Chỉ cần khi bật feature | Metrics exporter |

### 4.1. Compile dependency

Compile dependency cung cấp type hoặc symbol cần thiết để compiler xử lý module. Nó thường ảnh hưởng đến compile classpath hoặc module resolution.

### 4.2. Runtime dependency

Runtime dependency cần có khi ứng dụng hoạt động, nhưng có thể không cần trong lúc compile nếu API không được tham chiếu trực tiếp.

### 4.3. Test dependency

Test dependency chỉ cần cho test source hoặc test task. Đưa nó vào runtime package có thể làm artifact nặng hơn hoặc tăng bề mặt rủi ro.

### 4.4. Build dependency

Build dependency là công cụ hoặc plugin được dùng để tạo artifact. Ví dụ, DSL compiler plugin có thể là build dependency của module application.

### 4.5. Task ordering

Task ordering biểu diễn thứ tự cần thiết giữa hai thao tác, kể cả khi task sau không dùng trực tiếp output của task trước. Ví dụ task tạo metadata phải chạy trước task đóng gói.

### 4.6. Optional dependency

Optional dependency chỉ được đưa vào graph khi feature tương ứng được bật hoặc điều kiện cấu hình thỏa mãn. Engine cần ghi nhận lý do node được thêm vào.

### 4.7. Dependency không đồng nghĩa với thứ tự

Quan hệ sử dụng một thư viện và quan hệ chạy task trước task khác có thể cần semantics riêng. DSL không nên gộp mọi quan hệ thành một cạnh không có loại, vì việc đó làm mất thông tin về classpath, runtime và scheduling.

## 5. Biểu diễn dependency graph trong DSL

DSL có thể biểu diễn dependency bằng khai báo module, task hoặc resource.

### 5.1. Khai báo module dependency

~~~text
module application {
    depends-on domain
    depends-on persistence
}

module persistence {
    depends-on domain
}
~~~

Trong ví dụ, application cần domain và persistence; persistence cũng cần domain.

### 5.2. Khai báo task dependency

~~~text
task compileDsl {
    input = files("src/main/dsl")
    output = directory("build/generated")
}

task compileJava {
    depends-on compileDsl
    input = files("src/main/java", "build/generated")
}
~~~

Task compileJava cần output do compileDsl tạo ra. Engine có thể suy ra thứ tự thực hiện từ cạnh prerequisite.

### 5.3. Khai báo artifact dependency

~~~text
artifact applicationJar {
    produced-by packageApplication
}

artifact containerImage {
    requires applicationJar
    requires baseImage
}
~~~

Artifact graph giúp nối bước compile, package và container image.

### 5.4. Khai báo deployment dependency

~~~text
service orderApi {
    requires database ordersDb
    requires network privateNetwork
}
~~~

Deployment engine cần bảo đảm resource prerequisite sẵn sàng theo semantics của platform.

### 5.5. Graph suy ra từ khai báo

Người dùng không nhất thiết phải viết graph tường minh. Compiler hoặc build planner có thể suy ra node và edge từ module declaration, task input/output, plugin và resource reference.

### 5.6. Graph tường minh và graph suy luận

Graph tường minh dễ kiểm tra nhưng có thể lặp lại thông tin. Graph suy luận giảm boilerplate nhưng cần quy tắc rõ và công cụ hiển thị kết quả suy luận để người dùng hiểu engine đã tạo quan hệ nào.

## 6. DAG và thứ tự thực thi

Build graph thường cần là DAG để có thể lập lịch theo thứ tự phụ thuộc.

### 6.1. Prerequisite

Nếu task B cần output của A, A là prerequisite của B. A phải hoàn tất thành công trước khi B chạy.

### 6.2. Topological ordering

Topological ordering là một thứ tự tuyến tính của các node trong DAG sao cho mỗi node xuất hiện sau tất cả prerequisite của nó. Có thể có nhiều thứ tự hợp lệ nếu graph có các nhánh độc lập.

Ví dụ:

~~~mermaid
flowchart TD
    A[Parse DSL] --> C[Generate source]
    B[Resolve dependencies] --> D[Compile]
    C --> D
    D --> E[Test]
    E --> F[Package]
~~~

Parse DSL và resolve dependencies có thể chạy song song nếu không có quan hệ phụ thuộc khác. Generate source phải hoàn tất trước compile; compile phải hoàn tất trước test.

### 6.3. Kahn's algorithm

Một cách topological sort phổ biến là tính indegree của mỗi node, đưa các node không có prerequisite vào hàng đợi rồi lần lượt loại chúng và giảm indegree của successor. Nếu cuối cùng còn node chưa được xử lý, graph có cycle.

### 6.4. Depth-first search

DFS có thể dùng màu trạng thái hoặc stack để phát hiện back edge và truy vết cycle. Nó cũng có thể tạo thứ tự topo bằng cách ghi node khi quay lui khỏi đệ quy.

### 6.5. Nhiều thứ tự hợp lệ

Nếu hai task không phụ thuộc nhau, cả hai thứ tự đều có thể đúng. Scheduler chọn thứ tự dựa trên tài nguyên, mức ưu tiên, cache và giới hạn concurrency.

### 6.6. Critical path

Critical path là đường có tổng thời gian thực hiện lớn nhất trong DAG nếu bỏ qua tranh chấp tài nguyên. Đường này đặt giới hạn dưới cho thời gian hoàn tất build. Tối ưu task trên critical path thường có tác động lớn hơn tối ưu một nhánh ngắn.

## 7. Phát hiện và xử lý dependency cycle

Cycle xảy ra khi một node phụ thuộc trực tiếp hoặc gián tiếp vào chính nó.

### 7.1. Cycle trực tiếp

~~~text
module A {
    depends-on A
}
~~~

Module A phụ thuộc chính nó. Đây thường là lỗi khai báo đơn giản.

### 7.2. Cycle gián tiếp

~~~mermaid
flowchart LR
    A[Module A] --> B[Module B]
    B --> C[Module C]
    C --> A
~~~

A phụ thuộc B, B phụ thuộc C và C phụ thuộc A. Không thể tìm thứ tự build tuyến tính đáp ứng tất cả prerequisite.

### 7.3. Diagnostic hữu ích

Thông báo cycle nên hiển thị đường đi, ví dụ A -> B -> C -> A, kèm file và vị trí khai báo cạnh nếu có. Một thông báo chung “circular dependency” khiến người dùng khó tìm nguyên nhân.

### 7.4. Sửa cycle

Có thể tách interface hoặc contract thành module nhỏ hơn, đảo dependency để module cấp cao phụ thuộc abstraction, hoặc loại bỏ cạnh không cần thiết. Với task build, có thể chia task thành các bước có input/output rõ hơn.

### 7.5. Strongly connected components

Strongly connected component (SCC) là tập node mà mỗi node có thể đi đến mọi node khác trong tập. SCC có nhiều hơn một node hoặc có self-loop cho biết vùng cycle. Thuật toán Tarjan hoặc Kosaraju có thể tìm SCC hiệu quả.

### 7.6. Cycle có chủ đích trong domain khác

Một số graph nghiệp vụ có thể biểu diễn quan hệ vòng, chẳng hạn liên kết giữa thực thể. Điều đó không có nghĩa task dependency cũng được phép có cycle. Cần phân biệt loại graph và semantics của từng edge.

## 8. Dependency trực tiếp và dependency bắc cầu

Một thành phần có thể phụ thuộc vào node khác thông qua nhiều tầng.

### 8.1. Direct dependency

Direct dependency được khai báo trực tiếp bởi module hoặc task. Ví dụ application khai báo dùng domain.

### 8.2. Transitive dependency

Nếu application phụ thuộc domain và domain phụ thuộc common-utils, common-utils là transitive dependency của application.

~~~mermaid
flowchart TD
    A[Application] --> B[Domain]
    B --> C[Common Utils]
    A --> D[HTTP Runtime]
    D --> E[Logging API]
~~~

Application có direct dependency domain và HTTP Runtime; common-utils và logging API là dependency bắc cầu.

### 8.3. Dependency closure

Dependency closure của một node là tập tất cả node có thể đạt tới theo quan hệ dependency. Build engine dùng closure để dựng classpath, package nội dung runtime hoặc xác định prerequisite.

### 8.4. Duplicate dependency

Hai nhánh có thể cùng dẫn đến một package. Resolver cần xác định có thể dùng chung một phiên bản hay phải giữ nhiều phiên bản theo cơ chế isolation.

### 8.5. Exclusion

Một module có thể loại dependency bắc cầu không cần thiết. Exclusion cần được áp dụng rõ và kiểm tra xem thành phần bị loại có còn được code khác cần hay không.

### 8.6. Optional transitive dependency

Dependency tùy chọn có thể chỉ được kéo vào khi feature hoặc adapter tương ứng được dùng. Resolver cần giữ thông tin điều kiện để tránh thêm package không cần thiết.

## 9. Scope của dependency

Scope cho biết dependency được dùng ở giai đoạn nào hoặc phạm vi nào.

| Scope | Phạm vi |
|---|---|
| Compile | Compile source chính |
| Runtime | Chạy ứng dụng |
| Test | Compile và chạy test |
| Build | Chạy build plugin/tool |
| Provided | Được môi trường runtime cung cấp |
| Development | Chỉ dùng khi phát triển |
| Deploy | Cần cho thao tác triển khai |
| Optional | Chỉ thêm khi feature được bật |

### 9.1. Compile scope

Compile dependency cần có khi compiler phân giải type và symbol. Nó có thể không cần nằm trong artifact runtime nếu API chỉ dùng ở compile time.

### 9.2. Runtime scope

Runtime dependency cần có khi ứng dụng thực thi. Nếu thiếu, chương trình có thể compile thành công nhưng lỗi khi khởi động hoặc gọi chức năng.

### 9.3. Test scope

Test framework và fixture library nên nằm trong test scope để không bị đóng gói cùng ứng dụng production.

### 9.4. Build scope

Compiler plugin, formatter hoặc code generator cần cho quá trình build nhưng không nhất thiết là dependency của ứng dụng.

### 9.5. Provided scope

Một thư viện có thể được nền tảng runtime cung cấp. Artifact không đóng gói nó, nhưng cần ghi rõ prerequisite của môi trường chạy.

### 9.6. Scope propagation

Dependency có thể được truyền sang consumer theo quy tắc. Ví dụ, một API công khai có thể yêu cầu type từ dependency khác xuất hiện trên compile classpath của consumer. Quy tắc export/transitive scope cần được đặc tả.

### 9.7. Scope mismatch

Nếu source runtime tham chiếu một package chỉ khai báo ở test scope, build có thể thành công trong test nhưng artifact production thiếu thư viện. Validator nên phát hiện trường hợp này.

## 10. Phiên bản dependency và constraint

Package hoặc plugin thường có nhiều version. Dependency graph cần mang thông tin version để resolver chọn được tập thành phần tương thích.

### 10.1. Exact version

~~~text
depends-on "org.example:domain-api:2.4.1"
~~~

Exact version tạo lựa chọn rõ ràng nhưng cần được cập nhật có chủ đích khi nâng cấp.

### 10.2. Version range

~~~text
depends-on "org.example:domain-api:[2.4,3.0)"
~~~

Range cho phép resolver chọn một version trong khoảng. Cần quy định endpoint đóng/mở và cách xử lý version prerelease.

### 10.3. Minimum version

Một constraint có thể yêu cầu version từ mức tối thiểu trở lên. Tuy nhiên, version mới hơn chưa chắc tương thích nếu có breaking change hoặc giới hạn runtime.

### 10.4. Semantic versioning

Semantic Versioning (SemVer) thường biểu diễn MAJOR.MINOR.PATCH. Dependency constraint có thể dùng thông tin này để diễn đạt tương thích, nhưng chỉ đáng tin khi nhà phát hành tuân thủ SemVer.

### 10.5. Version catalog

Project có thể quản lý version tập trung trong catalog để tránh nhiều module khai báo các phiên bản khác nhau của cùng thư viện.

### 10.6. Version alignment

Một nhóm package có thể cần cùng một release train hoặc platform version. Resolver có thể dùng BOM, platform constraint hoặc alignment rule để chọn tập version đồng bộ.

### 10.7. Dynamic version

Constraint như latest hoặc range rộng có thể cho kết quả khác theo thời điểm. Điều này làm build khó tái lập nếu không có lock file hoặc resolution record.

### 10.8. Version conflict

Nếu module A cần thư viện X phiên bản 2.x còn module B cần 3.x, resolver phải áp dụng policy rõ: chọn một version tương thích, dùng nhiều version trong isolation, hoặc báo conflict.

## 11. Dependency resolution

Dependency resolution là quá trình tìm một tập version và artifact thỏa mãn toàn bộ constraint của graph.

### 11.1. Thu thập yêu cầu

Resolver đọc direct dependency, transitive dependency, version range, exclusion, scope và platform constraint.

### 11.2. Tìm metadata

Metadata package có thể đến từ local cache, repository nội bộ hoặc package registry. Nó mô tả version, dependency con, checksum, license và compatibility.

### 11.3. Giải quyết constraint

Resolver tìm tổ hợp version thỏa mọi yêu cầu. Với constraint không tương thích, nó cần chỉ ra đường dependency dẫn đến xung đột.

### 11.4. Conflict resolution policy

Một số công cụ ưu tiên version cao nhất, một số dùng constraint nghiêm ngặt hoặc yêu cầu version được khóa. Chính sách cần được công bố vì nó ảnh hưởng nội dung build.

### 11.5. Capability và variant

Một package có thể phát hành nhiều variant theo platform, architecture, runtime hoặc feature. Resolver chọn variant phù hợp với consumer attributes.

### 11.6. Exclusion và substitution

Có thể loại một dependency hoặc thay một module bằng module khác. Quy tắc substitution cần được giới hạn rõ để không làm graph khác xa khai báo ban đầu.

### 11.7. Resolution report

Report nên cho biết dependency trực tiếp, dependency bắc cầu, version được chọn, version bị loại, constraint và đường dẫn đưa package vào graph.

## 12. Graph của task build

Build graph mô tả các thao tác cần thực hiện và quan hệ prerequisite giữa chúng.

### 12.1. Task inputs và outputs

Task nên khai báo input và output. Engine có thể suy ra dependency nếu output của task này được dùng làm input của task khác.

~~~text
task generateJava {
    input = files("src/main/dsl")
    output = directory("build/generated/java")
}

task compileJava {
    input = files("src/main/java", "build/generated/java")
    output = directory("build/classes")
}
~~~

### 12.2. Explicit dependency

Có thể khai báo compileJava depends-on generateJava nếu engine không suy ra từ input/output. Khai báo tường minh cần tương ứng với quan hệ dữ liệu thực.

### 12.3. Task graph và module graph

Module graph mô tả module dùng module nào; task graph mô tả thao tác nào cần chạy trước. Một module có thể có nhiều task, và mỗi task có dependency khác nhau.

### 12.4. Task lifecycle

Build tool có thể có các phase như configuration, execution và finalization. Task graph cần xác định task nào được yêu cầu, task nào được kéo theo và task nào chạy sau khi hoàn tất.

### 12.5. Finalizer và cleanup

Một task cleanup có thể chạy sau task khác kể cả khi task đó thất bại. Đây là quan hệ lifecycle riêng, không nhất thiết giống prerequisite thành công. DSL cần mô tả failure semantics rõ.

### 12.6. Task không có output

Task có side effect như publish hoặc deploy vẫn có thể là node trong graph. Vì không có output file để fingerprint, engine cần quy định caching và retry cẩn thận.

## 13. Incremental build và invalidation

Incremental build chỉ chạy lại những phần bị ảnh hưởng bởi thay đổi.

### 13.1. Input fingerprint

Engine có thể tính fingerprint từ nội dung file, cấu hình, dependency version và toolchain version. Nếu fingerprint không đổi và output còn hợp lệ, task có thể được bỏ qua.

### 13.2. Dirty node

Node được đánh dấu dirty khi input hoặc prerequisite thay đổi theo quy tắc invalidation. Dirty status có thể lan đến successor phụ thuộc vào output của node đó.

### 13.3. Reverse dependency graph

Để tìm phần bị ảnh hưởng, engine thường duyệt graph theo chiều ngược từ node thay đổi đến các consumer.

### 13.4. Granularity

Nếu cả project là một node duy nhất, thay đổi nhỏ có thể làm build lại toàn bộ. Chia module và task theo ranh giới input/output hợp lý giúp incremental build hiệu quả hơn.

### 13.5. Cache key

Cache key cần phản ánh mọi yếu tố có thể ảnh hưởng output: input content, compiler version, flags, environment được phép, dependency graph và platform attributes.

### 13.6. Cache invalidation

Khi toolchain, configuration hoặc dependency thay đổi, cache cũ có thể không còn hợp lệ. Bỏ sót một input trong fingerprint có thể tạo artifact stale và lỗi khó tái hiện.

### 13.7. Remote build cache

Nhiều máy hoặc CI runner có thể chia sẻ artifact cache. Cache cần content addressing, quyền truy cập, kiểm tra integrity và cách phân biệt artifact giữa platform khác nhau.

### 13.8. Không cache side effect tùy tiện

Task gửi message, publish package hoặc triển khai dịch vụ có side effect. Không nên coi chúng như task thuần có thể bỏ qua chỉ vì input fingerprint không đổi, trừ khi có semantics idempotency rõ.

## 14. Lập lịch và thực thi song song

DAG cho biết những node nào sẵn sàng chạy cùng lúc.

### 14.1. Ready queue

Node được đưa vào ready queue khi mọi prerequisite cần thiết đã hoàn tất. Scheduler lấy node từ hàng đợi dựa trên giới hạn concurrency và tài nguyên.

### 14.2. Parallel branches

Hai nhánh độc lập có thể chạy đồng thời. Ví dụ compile module A và module B có thể song song nếu chúng không phụ thuộc lẫn nhau và không ghi vào cùng output path.

### 14.3. Resource constraints

Task có thể yêu cầu CPU, memory, network slot, device hoặc license token. Scheduler cần tôn trọng giới hạn tài nguyên ngay cả khi graph cho phép chạy song song.

### 14.4. Race condition

Hai task có thể cùng ghi một file hoặc sửa một resource. Dependency graph cần mô tả xung đột hoặc engine phải có cơ chế khóa tài nguyên.

### 14.5. Deterministic scheduling

Thứ tự chạy các task độc lập có thể khác giữa các lần build. Nếu output phụ thuộc vào thứ tự đó, task đang có side effect hoặc thiếu dependency declaration.

### 14.6. Failure propagation

Nếu prerequisite thất bại, successor thường không thể chạy. Engine có thể đánh dấu successor skipped/blocked và vẫn chạy các nhánh độc lập để thu thập thêm lỗi.

### 14.7. Cancellation

Khi người dùng hủy build, scheduler cần dừng task đang chạy theo khả năng và không khởi chạy thêm node mới. Cleanup task có thể cần được thực hiện để giải phóng tài nguyên.

## 15. Deployment dependency graph

Deployment graph mô tả quan hệ giữa dịch vụ, tài nguyên hạ tầng và các thao tác triển khai.

### 15.1. Resource prerequisite

Service có thể cần network, database, storage, secret hoặc identity trước khi khởi chạy.

### 15.2. Service dependency

Một API có thể gọi identity service, payment service và message broker. Graph giúp thể hiện dependency vận hành và thứ tự triển khai ban đầu.

### 15.3. Provision trước deploy

Resource như network hoặc database có thể cần được provision trước khi deploy application. Sau khi provision, cần có bước kiểm tra readiness.

### 15.4. Startup ordering

Một service có thể chỉ khởi động sau khi dependency sẵn sàng. Chỉ có container đang chạy không đồng nghĩa service đã sẵn sàng nhận request.

### 15.5. Readiness và health

Deployment engine cần phân biệt created, started, ready và healthy. Dependency của service nên dựa trên điều kiện readiness phù hợp thay vì chỉ dựa trên thứ tự tạo resource.

### 15.6. Runtime dependency khác deployment ordering

Service A gọi service B trong runtime không nhất thiết yêu cầu A phải được deploy sau B nếu A có retry và B có thể chưa sẵn sàng. Graph cần phân biệt quan hệ sử dụng với quan hệ thứ tự triển khai bắt buộc.

### 15.7. Optional service

Một integration có thể chỉ được bật ở một environment. Khi feature bị tắt, node và edge tương ứng cần được loại khỏi deployment plan.

## 16. Triển khai theo môi trường và nhiều tầng

Một project có thể triển khai qua nhiều environment và nhiều tầng hạ tầng.

### 16.1. Environment graph

Development, staging và production có thể dùng chung logical service graph nhưng khác resource, endpoint, scale và policy.

### 16.2. Promotion

Artifact được build một lần có thể được promote qua các environment. Graph nên liên kết deployment node với cùng artifact digest để tránh build lại một nội dung khác khi promote.

### 16.3. Dependency giữa deployment stage

Staging deployment có thể phải hoàn tất smoke test trước khi production deployment được phép chạy. Đây là dependency giữa các stage của pipeline.

### 16.4. Approval gate

Một node approval có thể là prerequisite của production deployment. Nó là một dependency mang tính quy trình, không phải package dependency.

### 16.5. Environment-specific edges

Một service có thể phụ thuộc mock server trong test nhưng phụ thuộc dịch vụ thật ở production. Graph cần được tạo từ profile đã chọn và ghi lại các điều kiện đã áp dụng.

### 16.6. Promotion và configuration drift

Nếu mỗi environment dùng artifact khác nhau hoặc cấu hình thay đổi không được kiểm soát, kết quả test staging không bảo đảm phản ánh production. Cần theo dõi artifact identity và config revision riêng.

## 17. Dependency của plugin và extension

DSL toolchain thường mở rộng qua plugin, generator và adapter.

### 17.1. Plugin node

Plugin có thể đóng góp task, type, compiler phase, template hoặc deployment provider. Plugin trở thành node trong graph và có version constraint.

### 17.2. Plugin dependency

Plugin A có thể yêu cầu plugin B hoặc một version của DSL compiler. Resolver cần kiểm tra compatibility trước khi tải và khởi tạo plugin.

### 17.3. Extension ordering

Một số plugin cần chạy trước hoặc sau compiler phase khác. Đây là dependency theo phase, cần khai báo rõ.

### 17.4. Plugin isolation

Plugin không tin cậy có thể chạy code trong tiến trình build. Có thể cần sandbox, process isolation hoặc giới hạn quyền filesystem/network.

### 17.5. Plugin metadata

Metadata nên khai báo ID, version, API compatibility, dependency, capability, permissions và nguồn phân phối.

### 17.6. Plugin conflict

Hai plugin có thể cung cấp cùng capability hoặc đăng ký cùng tên task. Engine cần phát hiện collision và yêu cầu cấu hình rõ.

## 18. Dependency graph và package management

Package manager giải quyết dependency graph của thư viện và module.

### 18.1. Repository

Package metadata có thể được lấy từ public registry, private registry hoặc local repository. Nguồn phải được xác định và tin cậy.

### 18.2. Artifact coordinates

Một package thường có group, name, version và đôi khi classifier/platform attributes. Coordinates xác định artifact cần lấy.

### 18.3. Lock file

Lock file ghi lại phiên bản đã được resolver chọn để những lần build sau dùng cùng dependency graph.

### 18.4. Checksums

Checksum giúp xác minh nội dung artifact tải về khớp với nội dung được ghi nhận. Có thể dùng signature hoặc metadata provenance bổ sung.

### 18.5. Exclusions và constraints

Exclusion loại nhánh dependency; constraint giới hạn version có thể được chọn. Cần ghi rõ lý do vì chúng có thể ảnh hưởng module khác.

### 18.6. Dependency insight

Một lệnh insight có thể giải thích package được kéo vào bởi đường nào, version nào được yêu cầu và tại sao version cuối cùng được chọn.

### 18.7. Dependency updates

Tool có thể đề xuất version mới, nhưng cần kiểm tra breaking change, license, vulnerability, compatibility và test trước khi áp dụng.

## 19. Tái lập build và tính xác định

Một build tái lập tạo ra kết quả giống nhau khi đầu vào, toolchain và môi trường được kiểm soát.

### 19.1. Pin dependency graph

Khóa version của dependency trực tiếp và bắc cầu để resolver không tự chọn version khác theo thời điểm.

### 19.2. Pin toolchain

Compiler, build engine, plugin, container base image và generator version đều có thể ảnh hưởng output. Cần ghi nhận và khóa phiên bản quan trọng.

### 19.3. Stable inputs

Tránh phụ thuộc ngầm vào thời gian hiện tại, thứ tự file hệ thống, locale, timezone hoặc đường dẫn tuyệt đối nếu chúng không được khai báo.

### 19.4. Artifact digest

Gắn digest với artifact để so sánh nội dung giữa các stage và environment.

### 19.5. Build manifest

Manifest có thể ghi source revision, dependency lock, toolchain version, build parameters và artifact digest.

### 19.6. Hermetic build

Hermetic build chỉ sử dụng những input đã được khai báo và kiểm soát. Truy cập mạng hoặc đọc file ngoài graph có thể làm build không tái lập.

### 19.7. Time-dependent dependency

Nếu build lấy latest, snapshot repository hoặc dữ liệu remote không được pin, kết quả có thể thay đổi. Cần khóa snapshot hoặc ghi version chính xác.

## 20. Graph transformation và các pha xử lý

Graph được xây dựng và biến đổi qua nhiều bước trước khi thực thi.

### 20.1. Graph construction

Engine đọc DSL, module metadata, plugin và project descriptor để tạo graph ban đầu.

### 20.2. Conditional expansion

Feature flags và profile có thể thêm hoặc bỏ node/edge. Graph cuối cùng phải phản ánh cấu hình hiệu lực.

### 20.3. Dependency resolution

Resolver thêm dependency bắc cầu và gắn version đã chọn vào node package.

### 20.4. Validation

Validator kiểm tra node không tồn tại, cycle, version conflict, scope mismatch, duplicate output và quyền truy cập.

### 20.5. Optimization

Engine có thể gộp task tương đương, loại node không cần thiết hoặc lập index. Transformation phải bảo toàn semantics.

### 20.6. Scheduling graph

Scheduler có thể tạo một graph thực thi cụ thể với concurrency, resource constraints, retry và finalizer.

### 20.7. Deployment plan

Deployment engine có thể chuyển service/resource graph thành các thao tác create, update, wait-ready, health-check và rollback.

### 20.8. Graph snapshot

Lưu snapshot graph đã resolve giúp giải thích build hoặc deployment cụ thể. Nếu graph thay đổi theo registry hoặc profile, snapshot là bằng chứng quan trọng để tái hiện.

## 21. Phân tích graph và thuật toán hữu ích

Nhiều thuật toán graph cơ bản hỗ trợ build planner và dependency resolver.

| Thuật toán hoặc khái niệm | Ứng dụng |
|---|---|
| Topological sort | Tạo thứ tự thực thi DAG |
| DFS | Duyệt graph và phát hiện cycle |
| BFS | Tìm các node theo số bước hoặc khoảng cách |
| Strongly connected components | Xác định vùng cycle |
| Reachability | Kiểm tra node có phụ thuộc gián tiếp vào node khác |
| Transitive closure | Tập hợp mọi quan hệ có thể đi tới |
| Critical path | Tìm đường ảnh hưởng lớn nhất đến thời gian hoàn tất |
| Reverse graph traversal | Tìm consumer bị ảnh hưởng bởi thay đổi |

### 21.1. Reachability

Nếu có đường đi từ A đến B theo chiều dependency, B nằm trong dependency closure của A theo quy ước cạnh tương ứng. Reachability giúp xác định một module có gián tiếp cần package nào đó hay không.

### 21.2. Transitive reduction

Transitive reduction loại những cạnh có thể suy ra từ đường đi khác mà vẫn giữ reachability. Nó có thể giúp sơ đồ dễ đọc, nhưng không nên xóa quan hệ gốc khỏi metadata nếu quan hệ đó mang ý nghĩa trực tiếp.

### 21.3. Critical path

Nếu mỗi task có thời lượng ước tính, thuật toán trên DAG có thể tính earliest start, latest start và slack. Task trên critical path không có slack và ảnh hưởng trực tiếp đến tổng thời gian build.

### 21.4. Impact analysis

Khi một source node thay đổi, duyệt reverse dependency graph để tìm task và artifact có thể bị ảnh hưởng. Kết quả có thể dùng cho incremental build hoặc cảnh báo trong IDE.

### 21.5. Complexity

Topological sort và DFS thường có độ phức tạp O(V + E), với V là số node và E là số edge. Chi phí thực tế còn phụ thuộc dependency resolution, filesystem, remote repository và scheduling.

## 22. Quan sát và trực quan hóa dependency graph

Graph lớn khó hiểu nếu chỉ hiển thị dưới dạng danh sách.

### 22.1. Node label

Nhãn node nên hiển thị tên ngắn, loại, version hoặc trạng thái cần thiết. Tránh đưa quá nhiều metadata vào cùng một nhãn.

### 22.2. Edge label

Nhãn cạnh có thể cho biết compile/runtime/test, requires, order hoặc deploy-after. Màu sắc có thể phân biệt loại cạnh, nhưng cần có legend và không phụ thuộc riêng vào màu.

### 22.3. Grouping

Có thể nhóm node theo module, package, build phase, environment hoặc deployment layer để giảm độ rối.

### 22.4. Filtering

Người dùng có thể chỉ xem dependency trực tiếp, dependency bắc cầu, một scope hoặc một environment. Bộ lọc cần cho biết graph đang hiển thị một phần hay toàn bộ.

### 22.5. Expand và collapse

Node package có thể mở rộng để xem dependency con. Module có thể thu gọn để chỉ hiển thị dependency giữa các module cấp cao.

### 22.6. Path explanation

Một công cụ hữu ích cho phép hỏi “Vì sao package X có mặt?” và hiển thị đường đi từ module gốc đến package đó.

### 22.7. Cycle highlighting

Nếu graph có cycle, hiển thị rõ các node và cạnh tạo cycle. Cho phép nhảy đến khai báo nguồn của cạnh.

### 22.8. Graph export

Có thể xuất DOT, Mermaid, JSON hoặc định dạng riêng để lưu tài liệu và tích hợp công cụ khác. Export cần ghi rõ graph version và phạm vi được xuất.

## 23. Bảo mật và supply chain

Dependency graph cũng là mô hình về những thành phần bên ngoài mà project tin cậy.

### 23.1. Dependency provenance

Ghi nguồn package, repository, checksum, signature và version. Điều này giúp xác định artifact đến từ đâu.

### 23.2. Vulnerability analysis

Có thể đối chiếu package graph với vulnerability database để tìm dependency trực tiếp hoặc bắc cầu có lỗ hổng. Kết quả cần gắn version và thời điểm tra cứu.

### 23.3. License policy

Tổ chức có thể áp dụng policy cho license của dependency. Resolver hoặc validation phase có thể chặn package không được phép hoặc yêu cầu review.

### 23.4. Typosquatting và dependency confusion

Tên package gần giống package phổ biến hoặc package nội bộ có thể bị lợi dụng. Cần pin nguồn, kiểm soát namespace và ưu tiên repository đáng tin cậy.

### 23.5. Build plugin permissions

Plugin có thể chạy code với quyền của build process. Chỉ dùng plugin từ nguồn được tin cậy và giới hạn network/filesystem khi có thể.

### 23.6. Artifact integrity

Kiểm tra checksum hoặc chữ ký trước khi sử dụng artifact. Không coi package tải về là an toàn chỉ vì resolver tìm thấy version phù hợp.

### 23.7. Least privilege

Build job và deployment job chỉ nên có quyền cần thiết. Build graph có thể phân tách task cần secret hoặc quyền publish khỏi task compile/test thông thường.

### 23.8. SBOM

Software Bill of Materials (SBOM) liệt kê các thành phần có trong artifact. Dependency graph là một nguồn để tạo SBOM và truy vết dependency bắc cầu.

## 24. Xử lý lỗi, retry và rollback

Build và deployment graph cần xác định cách phản ứng khi node thất bại.

### 24.1. Failure state

Node có thể ở trạng thái pending, ready, running, succeeded, failed, skipped, blocked hoặc cancelled. Trạng thái cần phân biệt task chưa chạy với task bị chặn do prerequisite.

### 24.2. Failure propagation

Nếu compile thất bại, package task phụ thuộc vào output compile thường bị blocked. Các nhánh độc lập vẫn có thể chạy để thu thập thêm thông tin nếu policy cho phép.

### 24.3. Retry

Task có thể được retry khi lỗi tạm thời như network timeout. Retry cần giới hạn số lần, backoff và phân biệt lỗi tạm thời với lỗi cấu hình.

### 24.4. Idempotency

Task có side effect cần có cơ chế idempotency trước khi retry. Nếu deploy task tạo resource mới mỗi lần chạy, retry mù quáng có thể tạo tài nguyên trùng.

### 24.5. Compensation

Trong deployment, một số thao tác không thể rollback đơn giản. Có thể cần compensation action để hoàn tác hoặc đưa hệ thống về trạng thái an toàn.

### 24.6. Rollback graph

Rollback có thể là graph thao tác riêng, chạy theo thứ tự phụ thuộc ngược hoặc theo quy tắc migration cụ thể. Không phải lúc nào chỉ đảo ngược thứ tự deploy cũng an toàn.

### 24.7. Partial deployment

Nếu một service đã cập nhật nhưng service khác thất bại, hệ thống có thể ở trạng thái mixed version. Deployment plan cần xác định chiến lược tiếp tục, rollback hoặc giữ trạng thái chờ xử lý.

## 25. Kiểm thử dependency graph

Graph và scheduler cần được kiểm thử ở cả cấu trúc lẫn hành vi thực thi.

### 25.1. Node và edge construction

Từ một project descriptor fixture, xác minh graph có đủ node, edge đúng chiều và đúng loại.

### 25.2. Topological order

Kiểm tra mọi prerequisite xuất hiện trước dependent trong thứ tự được tạo. Không nên chỉ so sánh một thứ tự cố định nếu graph có nhiều thứ tự hợp lệ.

### 25.3. Cycle detection

Kiểm tra self-cycle, cycle gián tiếp và graph không cycle. Diagnostic nên chứa đường đi đủ để tìm khai báo.

### 25.4. Dependency resolution

Tạo fixture với version ranges, conflict, exclusions và transitive dependency. Xác minh version được chọn theo policy.

### 25.5. Scope propagation

Kiểm tra compile, runtime, test và build dependency không bị đưa nhầm sang scope khác.

### 25.6. Incremental invalidation

Thay đổi một node input và xác minh chỉ các successor liên quan bị đánh dấu dirty; node độc lập vẫn có thể dùng cache.

### 25.7. Parallel scheduling

Dùng task giả có timestamp hoặc synchronization để xác minh prerequisite không chạy đồng thời với dependent và các nhánh độc lập có thể chạy song song.

### 25.8. Failure propagation

Cho một prerequisite thất bại và xác minh successor bị blocked, nhánh độc lập xử lý theo policy và cleanup/finalizer được gọi đúng.

### 25.9. Deployment readiness

Kiểm tra service dependent chỉ được đánh dấu sẵn sàng khi resource prerequisite đạt readiness condition, không chỉ khi resource được tạo.

### 25.10. Reproducibility

Build hai lần với cùng graph snapshot, lock file và toolchain; so sánh artifact digest hoặc output đã chuẩn hóa.

### 25.11. Security checks

Kiểm tra package source, checksum, plugin permission, license policy và secret scope theo graph.

## 26. Ví dụ tổng hợp: build và deploy ứng dụng DSL

Giả sử project gồm module domain, persistence, API và một DSL compiler. Ứng dụng cần tạo source Java, chạy test, đóng gói container image rồi triển khai cùng database.

### 26.1. Module graph

~~~text
module domain {
    source = "modules/domain"
}

module persistence {
    source = "modules/persistence"
    depends-on domain
}

module api {
    source = "modules/api"
    depends-on domain
    depends-on persistence
}
~~~

Module api dùng domain model và persistence adapter. Persistence cũng dùng domain nên graph có một nhánh dùng chung.

### 26.2. Task graph

~~~text
task parseDsl
task generateJava depends-on parseDsl
task compileDomain depends-on generateJava
task compilePersistence depends-on compileDomain
task compileApi depends-on compilePersistence
task test depends-on compileApi
task package depends-on test
task buildImage depends-on package
~~~

Đây là một cách mô tả tuần tự đơn giản. Một build graph chi tiết hơn có thể cho compileDomain và một số task độc lập chạy song song, sau đó hội tụ ở compileApi.

### 26.3. Deployment graph

~~~mermaid
flowchart TD
    A[Provision network] --> D[Deploy database]
    B[Create secret reference] --> D
    D --> E[Wait for database ready]
    C[Build container image] --> F[Deploy API]
    E --> F
    G[Create service identity] --> F
    F --> H[Health check]
    H --> I[Route traffic]
~~~

API chỉ được route traffic sau khi image được triển khai, database sẵn sàng và health check thành công.

### 26.4. Thay đổi một file DSL

Khi domain model thay đổi, engine đánh dấu parse/generate/compile domain là dirty. Persistence và API có thể cần compile lại vì phụ thuộc domain. Các task không liên quan như tạo network không cần chạy lại.

### 26.5. Thay đổi cấu hình deploy

Nếu chỉ đổi replica count hoặc resource limit, có thể chỉ cần cập nhật deployment manifest và apply resource tương ứng. Không cần compile DSL nếu artifact không thay đổi.

### 26.6. Giải thích package bắc cầu

Nếu API kéo theo logging library qua persistence adapter, dependency insight hiển thị đường api -> persistence -> logging adapter -> logging API. Người dùng biết vì sao package xuất hiện và có thể quyết định có cần exclusion hay không.

### 26.7. Build manifest

Kết quả build có thể lưu source revision, DSL compiler version, dependency lock hash, container base image digest và artifact digest. Manifest giúp so sánh chính xác artifact được promote qua các environment.

## 27. Những sai lầm thường gặp

### 27.1. Không phân biệt các loại dependency

Gộp compile, runtime, test, build và deploy dependency thành một loại làm classpath, artifact và deployment plan khó kiểm soát.

### 27.2. Không khai báo task input/output

Task không công bố input/output khiến engine khó suy ra dependency và cache key. Incremental build có thể bỏ qua thay đổi cần thiết hoặc chạy lại quá nhiều.

### 27.3. Tạo cycle

Dependency vòng làm scheduler không tìm được thứ tự thực thi. Cần diagnostic hiển thị cycle path và cách tách abstraction hoặc task.

### 27.4. Tin rằng thứ tự file là thứ tự build

Thứ tự khai báo module trong file không nhất thiết là thứ tự prerequisite. Hãy mô tả quan hệ dependency và để graph planner xác định thứ tự.

### 27.5. Bỏ qua dependency bắc cầu

Một package không được khai báo trực tiếp vẫn có thể xuất hiện qua module khác. Cần xem resolution graph đầy đủ khi điều tra version hoặc vulnerability.

### 27.6. Dùng version động không kiểm soát

Version latest hoặc range rộng có thể làm build hôm nay khác ngày mai. Khóa graph bằng lock file và ghi toolchain version.

### 27.7. Chọn version chỉ theo số lớn nhất

Version cao hơn có thể không tương thích với runtime hoặc package khác. Resolver cần xét constraint, variant và alignment.

### 27.8. Chạy song song task có side effect chung

Hai task ghi cùng file hoặc resource có thể tạo race condition. Cần khai báo dependency hoặc cơ chế khóa.

### 27.9. Cache task có side effect

Publish hoặc deploy không thể được bỏ qua chỉ dựa vào input fingerprint nếu không có semantics idempotency và trạng thái đích.

### 27.10. Nhầm started với ready

Container đã chạy chưa chắc database đã nhận kết nối. Deployment graph cần readiness và health condition.

### 27.11. Không theo dõi graph đã resolve

Chỉ lưu source declaration không đủ để tái hiện version và dependency được chọn. Cần resolution report hoặc lock snapshot.

### 27.12. Không kiểm soát nguồn package

Resolver có thể lấy artifact từ nguồn không tin cậy hoặc nhầm namespace. Cần repository policy, checksum và provenance.

## 28. Nguyên tắc thiết kế dependency graph trong DSL

Một DSL build và deploy tốt cần làm cho quan hệ phụ thuộc rõ ràng, có thể kiểm tra và có thể tái lập.

### 28.1. Định danh node ổn định

Node cần ID rõ ràng và metadata về loại, version, input/output. Không phụ thuộc vào vị trí dòng hoặc thứ tự duyệt map để tạo identity.

### 28.2. Edge có kiểu và hướng

Phân biệt compile, runtime, test, build, task ordering, artifact và deployment dependency. Quy ước chiều cạnh phải được công bố.

### 28.3. Dùng DAG cho task prerequisite

Build task thông thường nên tạo DAG. Phát hiện cycle trước khi thực thi và hiển thị đường đi gây lỗi.

### 28.4. Resolve version tường minh

Dùng constraint, version catalog, lock file và resolution report. Tránh lựa chọn version động không được ghi nhận.

### 28.5. Khai báo input/output

Task nên công bố đầy đủ input và output để engine lập graph, tính cache key và xác định invalidation.

### 28.6. Giữ semantics khi tối ưu

Incremental build, parallel scheduling và graph transformation không được làm thay đổi kết quả của task hoặc thứ tự có ý nghĩa.

### 28.7. Tách build graph và deployment graph

Build graph mô tả cách tạo artifact; deployment graph mô tả resource, service và readiness. Hai graph liên kết qua artifact nhưng có lifecycle khác nhau.

### 28.8. Xử lý lỗi và side effect

Định nghĩa failure propagation, retry, cancellation, cleanup, idempotency và rollback. Không coi mọi task như thao tác thuần có thể chạy lại.

### 28.9. Quan sát và giải thích

Cung cấp graph visualization, dependency insight, cycle path, resolution report và impact analysis.

### 28.10. Bảo vệ supply chain

Xác minh nguồn package, checksum, signature, license và plugin permissions. Chỉ cấp secret và quyền triển khai cho task cần chúng.

### 28.11. Kiểm thử theo graph

Kiểm thử topology, cycle, resolution, scope, scheduling, invalidation, readiness và reproducibility.

### 28.12. Lưu graph snapshot

Ghi lại graph đã resolve cùng toolchain và artifact digest để build/deploy có thể được giải thích và tái hiện.

## 29. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Dependency Graph | Đồ thị biểu diễn các thành phần và quan hệ phụ thuộc |
| Node / Vertex | Đỉnh đại diện module, task, package, artifact hoặc resource |
| Edge | Cạnh biểu diễn quan hệ có hướng giữa hai node |
| Directed Graph | Đồ thị có các cạnh mang hướng |
| DAG | Đồ thị có hướng không chu trình |
| Topological Sort | Sắp xếp node sao cho prerequisite đứng trước dependent |
| Cycle | Đường đi quay lại node ban đầu |
| Strongly Connected Component | Tập node có thể đi đến nhau theo hướng cạnh |
| Direct Dependency | Dependency được khai báo trực tiếp |
| Transitive Dependency | Dependency được kéo theo qua dependency khác |
| Dependency Closure | Tập các dependency có thể đạt tới từ một node |
| Dependency Scope | Phạm vi compile, runtime, test hoặc build của dependency |
| Version Constraint | Ràng buộc phiên bản được phép chọn |
| Dependency Resolution | Quá trình chọn tập version và artifact phù hợp |
| Lock File | File ghi lại dependency graph đã được resolve |
| Task Graph | Đồ thị các task build và prerequisite |
| Artifact | Kết quả được tạo từ quá trình build |
| Incremental Build | Chỉ thực hiện lại phần bị ảnh hưởng bởi thay đổi |
| Cache Invalidation | Loại bỏ cache khi input hoặc điều kiện build thay đổi |
| Critical Path | Đường quyết định thời gian hoàn tất tối thiểu của DAG |
| Scheduler | Thành phần lập lịch và điều phối task |
| Readiness Probe | Kiểm tra service đã sẵn sàng nhận công việc |
| Deployment Graph | Đồ thị dependency giữa service và resource triển khai |
| Provenance | Thông tin nguồn gốc của dependency hoặc artifact |
| SBOM | Danh mục thành phần phần mềm có trong artifact |
| Idempotency | Tính chất chạy lại thao tác không tạo tác động trùng |
| Graph Snapshot | Bản ghi graph đã resolve tại một thời điểm |

Đồ thị phụ thuộc là mô hình cốt lõi để DSL build và deploy điều phối module, package, task, artifact, service và resource. Graph cho biết thứ tự prerequisite, dependency bắc cầu, các nhánh có thể chạy song song và phần bị ảnh hưởng khi input thay đổi. Một hệ thống tốt phân loại edge, kiểm tra cycle, giải quyết version có kiểm soát, khai báo input/output để hỗ trợ incremental build và tách rõ build graph khỏi deployment graph. Khi graph được version hóa, trực quan hóa và lưu cùng resolution metadata, nhóm phát triển có thể hiểu vì sao một thành phần được tạo hoặc triển khai, phát hiện rủi ro sớm và tái hiện kết quả một cách đáng tin cậy.
