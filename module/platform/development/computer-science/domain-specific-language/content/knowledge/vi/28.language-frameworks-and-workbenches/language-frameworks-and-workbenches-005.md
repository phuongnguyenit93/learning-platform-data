# Workbench tùy biến

Một ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL) thường cần nhiều công cụ hỗ trợ hơn một ô nhập văn bản. Người dùng có thể cần cây mô hình, trình soạn thảo có tô màu cú pháp, bảng thuộc tính, sơ đồ quan hệ, trình kiểm tra lỗi, cửa sổ chạy thử, lịch sử thay đổi và các lệnh thao tác theo miền nghiệp vụ. Một **workbench** là môi trường làm việc tích hợp các công cụ đó để người dùng tạo, xem, kiểm tra và vận hành tài nguyên của DSL.

**Workbench tùy biến (customizable workbench)** cho phép điều chỉnh giao diện, bố cục, công cụ, lệnh và quy trình làm việc theo vai trò hoặc nhu cầu của từng dự án. Người dùng có thể chọn những view cần thiết, sắp xếp khu vực làm việc, cấu hình cách hiển thị mô hình hoặc tạo bộ công cụ phù hợp với một nhiệm vụ. Ở cấp độ phát triển nền tảng, nhà phát triển DSL có thể mở rộng workbench bằng plugin, editor, view, command, wizard, validator và các điểm mở rộng được framework cung cấp.

Một workbench tốt cân bằng giữa tính nhất quán và khả năng tùy biến. Người mới cần một bố cục dễ hiểu, trong khi chuyên gia có thể muốn nhiều view, phím tắt và công cụ chuyên sâu. Nhóm phát triển cần mở rộng công cụ mà không làm hỏng các phần khác hoặc buộc người dùng phải học lại toàn bộ môi trường.

Bài học này trình bày khái niệm workbench, các lớp tùy biến, kiến trúc mở rộng, cách thiết kế extension point, cấu hình perspective và view, tích hợp editor cùng mô hình DSL, quản lý plugin, lưu trạng thái, bảo mật, khả năng tiếp cận, hiệu năng và kiểm thử.

## 1. Workbench là gì?

Workbench là môi trường làm việc tập hợp các công cụ tương tác với một tập tài nguyên hoặc một miền nghiệp vụ. Với DSL, tài nguyên có thể là file nguồn, mô hình, schema, workflow, query, quy tắc, biểu đồ hoặc kết quả thực thi.

Một workbench thường cung cấp:

- **Editor:** soạn thảo văn bản DSL, biểu thức, cấu hình hoặc mô hình.
- **Explorer:** duyệt project, module, entity, workflow và các tài nguyên liên quan.
- **Properties view:** xem và chỉnh sửa thuộc tính của phần tử đang chọn.
- **Outline:** hiển thị cấu trúc tài liệu hoặc mô hình.
- **Diagnostics:** tập hợp lỗi, cảnh báo và thông tin.
- **Console:** xem output, log hoặc kết quả chạy thử.
- **Diagram view:** trực quan hóa quan hệ, luồng hoặc cấu trúc.
- **Command system:** thực hiện lệnh theo ngữ cảnh.
- **Wizard:** hướng dẫn tạo tài nguyên hoặc cấu hình.
- **Search:** tìm symbol, tài nguyên và nội dung trong workspace.

Các thành phần này không nhất thiết phải xuất hiện đồng thời. Workbench có thể sắp xếp chúng thành những bố cục phù hợp với từng nhiệm vụ.

### 1.1. Workbench khác editor

Editor tập trung vào việc mở và chỉnh sửa một tài liệu. Workbench quản lý một môi trường rộng hơn, trong đó editor là một thành phần.

Ví dụ, khi chỉnh sửa một entity trong DSL mô hình dữ liệu, người dùng có thể đồng thời cần:

- Cây entity và quan hệ ở bên trái.
- Nội dung DSL ở giữa.
- Thuộc tính của entity đang chọn ở bên phải.
- Diagnostics và preview schema ở phía dưới.

Một editor đơn lẻ không nhất thiết quản lý các vùng này, nhưng workbench điều phối chúng theo cùng selection và workspace context.

### 1.2. Workbench khác IDE tổng quát

IDE tổng quát cung cấp công cụ cho nhiều ngôn ngữ và dự án. Workbench DSL có thể tập trung vào khái niệm của một miền cụ thể.

Ví dụ, workbench cho DSL workflow có thể trình bày:

- Danh sách workflow.
- Sơ đồ step và nhánh điều kiện.
- Bảng input/output của step.
- Cấu hình retry và timeout.
- Lịch sử chạy.
- Debugger theo từng step.

Workbench cho DSL schema lại có thể ưu tiên entity explorer, quan hệ, constraint, migration và schema preview.

### 1.3. Workbench là hệ thống có ngữ cảnh

Các view nên phối hợp theo selection và context hiện tại. Khi người dùng chọn entity Customer trong explorer, Properties view có thể hiển thị thuộc tính của Customer, Diagram view làm nổi bật các quan hệ liên quan và editor điều hướng đến khai báo tương ứng.

Điều này đòi hỏi workbench có mô hình selection, event và resource identity thống nhất.

## 2. Các lớp tùy biến

Tùy biến có thể diễn ra ở nhiều mức. Phân biệt chúng giúp thiết kế quyền, cấu hình và kiến trúc mở rộng rõ ràng.

### 2.1. Tùy biến giao diện cá nhân

Người dùng điều chỉnh môi trường làm việc của chính mình:

- Ẩn hoặc hiện view.
- Kéo thả và thay đổi kích thước panel.
- Chọn theme và cỡ chữ.
- Thiết lập phím tắt.
- Chọn tab editor hoặc chế độ preview.
- Lưu perspective yêu thích.
- Chọn thông tin hiển thị trong explorer.

Đây thường là tùy biến ít rủi ro và có thể lưu theo user profile.

### 2.2. Tùy biến theo project hoặc workspace

Một dự án có thể chia sẻ quy ước cho cả nhóm:

- Perspective mặc định.
- Bộ view được khuyến nghị.
- Cấu hình validator.
- Quy tắc hiển thị diagram.
- Target runtime.
- Danh sách công cụ hoặc plugin được phép.
- Template tạo tài nguyên.
- Cấu hình build và debug.

Cấu hình project nên được quản lý trong repository nếu nhóm cần mọi thành viên có trải nghiệm nhất quán. Những thiết lập cá nhân như vị trí cửa sổ có thể lưu riêng.

### 2.3. Tùy biến theo vai trò

Các vai trò có nhu cầu khác nhau:

| Vai trò | Công cụ thường ưu tiên |
| --- | --- |
| Người phân tích nghiệp vụ | Model explorer, diagram, properties, documentation |
| Người viết DSL | Source editor, outline, completion, diagnostics |
| Nhà phát triển runtime | Debugger, console, execution trace, runtime configuration |
| Người quản trị schema | Schema view, migration, compatibility report |
| Người kiểm thử | Test explorer, fixtures, coverage và execution result |

Workbench có thể cung cấp perspective riêng cho từng vai trò. Vai trò không nhất thiết quyết định quyền bảo mật; quyền truy cập vẫn phải được kiểm tra ở service hoặc resource layer.

### 2.4. Tùy biến bằng extension

Nhà phát triển nền tảng hoặc plugin author có thể thêm chức năng:

- Editor mới.
- View mới.
- Command và menu item.
- Context menu contribution.
- Wizard.
- Validator.
- Diagram renderer.
- Model importer/exporter.
- Debug adapter.
- Property page.
- Resource navigator.

Đây là mức tùy biến cần API ổn định, lifecycle, versioning và cơ chế kiểm soát plugin.

## 3. Perspective, view, editor và panel

Workbench thường tổ chức giao diện bằng các khái niệm perspective, view, editor và panel. Tên gọi cụ thể phụ thuộc framework, nhưng trách nhiệm nên được phân biệt.

### 3.1. Perspective

Perspective là bố cục tổng thể gồm các view, editor area, toolbar và vị trí mặc định của chúng.

Ví dụ, perspective Model Design có thể gồm:

~~~text
+----------------------+----------------------------+
| Model Explorer       | DSL Editor                 |
|                      |                            |
|                      |                            |
+----------------------+----------------------------+
| Properties           | Diagnostics / Preview      |
+----------------------+----------------------------+
~~~

Perspective Debug có thể dùng cùng editor nhưng thay Properties bằng Variables, Call Stack và Debug Console.

### 3.2. View

View là một vùng hiển thị thông tin hoặc thực hiện một nhiệm vụ cụ thể. View thường có thể mở, đóng, di chuyển hoặc dock vào vị trí khác.

Ví dụ:

- Model Explorer.
- Outline.
- Problems.
- Properties.
- Workflow Runs.
- Schema Preview.

Một view nên có trách nhiệm rõ và không tự quản lý toàn bộ trạng thái của workbench.

### 3.3. Editor

Editor mở một tài nguyên để người dùng chỉnh sửa. Có thể có nhiều loại editor:

- Text editor cho DSL source.
- Diagram editor cho mô hình đồ họa.
- Form editor cho cấu hình có cấu trúc.
- Read-only preview cho schema sinh ra.
- Composite editor kết hợp text và diagram.

Editor cần liên kết với resource identity và cơ chế lưu thay đổi chung của workspace.

### 3.4. Panel và vùng dock

Panel là khu vực chứa view hoặc công cụ. Người dùng có thể thay đổi kích thước, vị trí và trạng thái thu gọn. Layout engine cần xử lý kích thước cửa sổ nhỏ, màn hình lớn và thay đổi độ phân giải.

### 3.5. Toolbar, menu và context menu

Toolbar cung cấp lệnh thường dùng. Menu nhóm lệnh theo chức năng. Context menu hiển thị hành động phù hợp với phần tử đang chọn.

Không nên đưa mọi lệnh vào toolbar. Lệnh ít dùng có thể nằm trong menu hoặc command palette để tránh giao diện quá dày.

## 4. Kiến trúc workbench có thể mở rộng

Một workbench tùy biến thường cần lõi ổn định và các phần mở rộng có hợp đồng rõ ràng.

~~~text
Workbench Core
  |
  +-- Workspace / Resource Model
  +-- Selection and Context Service
  +-- Command and Action Registry
  +-- View and Editor Registry
  +-- Layout / Perspective Manager
  +-- Event Bus
  +-- Preference Service
  +-- Plugin / Extension Manager
  |
  +-----------------------------+
  |                             |
  v                             v
DSL Core Services          Extensions
  |                             |
  +-- Parser                    +-- Custom View
  +-- Type System               +-- Diagram Renderer
  +-- Symbol Index              +-- Wizard
  +-- Validator                 +-- Importer
  +-- Generator                 +-- Domain Commands
  +-- Runtime                   +-- Debug Adapter
~~~

### 4.1. Workbench core

Core quản lý vòng đời cửa sổ, workspace, layout, selection, command dispatch, event và extension registry. Core không nên chứa mọi logic riêng của DSL.

### 4.2. DSL services

Các service ngôn ngữ cung cấp parser, resolver, validator, generator và runtime. Editor và view sử dụng những service này thông qua API ổn định.

### 4.3. Extension layer

Extension bổ sung UI hoặc logic theo hợp đồng được công bố. Extension nên dùng service công khai thay vì truy cập trực tiếp vào cấu trúc nội bộ của core.

### 4.4. Presentation và domain logic

View có thể trình bày entity hoặc workflow, nhưng không nên tự triển khai một parser khác. Nó nên gọi domain service hoặc dùng model đã được phân tích.

Tách presentation khỏi domain logic giúp nhiều view dùng chung semantics và tránh kết quả khác nhau giữa editor, diagram và validator.

## 5. Extension point và extension contract

Extension point là vị trí mà core cho phép plugin đóng góp chức năng. Extension contract quy định plugin cần cung cấp gì và core sẽ gọi nó khi nào.

Ví dụ một extension cho view:

~~~text
ViewContribution
  id
  title
  icon
  defaultPosition
  factory
  supportedContexts
~~~

Một extension cho command:

~~~text
CommandContribution
  id
  title
  handler
  enablement
  visibility
  keybinding
~~~

### 5.1. Định danh ổn định

Mỗi extension, view và command cần ID duy nhất. ID được dùng trong cấu hình layout, keybinding, telemetry và tham chiếu giữa plugin.

Không nên dùng title hiển thị làm ID vì title có thể được dịch hoặc đổi tên.

### 5.2. Metadata và implementation

Registry có thể đọc metadata trước khi nạp implementation. Điều này giúp hiển thị tên, icon hoặc điều kiện khả dụng mà chưa phải khởi tạo plugin.

Metadata nên có schema và được validate khi cài hoặc khởi động.

### 5.3. Enablement và visibility

Một command có thể luôn hiển thị nhưng chỉ enabled khi selection phù hợp. Một view có thể chỉ được cung cấp khi plugin liên quan đã được cài.

Cần phân biệt:
- Visibility: người dùng có nhìn thấy lệnh hoặc view không?
- Enablement: hiện tại có thể thực hiện không?
- Authorization: người dùng có quyền thực hiện không?

Authorization phải được kiểm tra ở lớp có thẩm quyền, không chỉ dựa vào trạng thái nút trên UI.

### 5.4. Version của extension contract

Khi core thay đổi API, plugin cũ có thể không còn hoạt động. Extension contract cần version hoặc capability negotiation để core biết plugin hỗ trợ những tính năng nào.

Nếu API bị loại bỏ, nên có giai đoạn deprecation và tài liệu migration.

## 6. Plugin và quản lý vòng đời

Plugin là đơn vị đóng gói một nhóm chức năng mở rộng. Plugin có thể cung cấp view, command, editor, service hoặc integration.

### 6.1. Plugin manifest

Một manifest có thể mô tả:

~~~yaml
id: com.example.dsl.workflow-tools
version: 1.2.0
requires:
  workbench-api: ">=3.0 <4.0"
contributes:
  views:
    - id: workflow.timeline
      title: Workflow Timeline
  commands:
    - id: workflow.open-run
      title: Open Workflow Run
~~~

Đây là cấu trúc minh họa. Manifest thực tế cần schema, quy tắc dependency và cách phân giải phiên bản rõ ràng.

### 6.2. Dependency giữa plugin

Plugin có thể phụ thuộc plugin khác hoặc một capability của core. Dependency manager cần phát hiện:

- Plugin thiếu dependency.
- Phiên bản không tương thích.
- Dependency cycle.
- Extension point không tồn tại.
- Xung đột ID.

Không nên nạp plugin trong trạng thái dependency chưa thỏa mãn.

### 6.3. Lifecycle

Một lifecycle có thể gồm:

1. Discover: tìm manifest.
2. Validate: kiểm tra metadata và dependency.
3. Resolve: xây thứ tự khởi tạo.
4. Load: nạp module hoặc bundle.
5. Activate: đăng ký contribution và service.
6. Deactivate: dừng listener và task.
7. Unload: giải phóng tài nguyên nếu nền tảng hỗ trợ.

Plugin cần có cơ chế cleanup. Listener, timer, file handle hoặc background task không được tiếp tục chạy sau khi plugin bị tắt.

### 6.4. Lazy activation

Không phải plugin nào cũng cần được khởi tạo ngay khi workbench mở. Có thể chỉ activate khi người dùng mở view hoặc chạy command của plugin. Lazy activation giúp giảm thời gian khởi động và bộ nhớ.

### 6.5. Cài đặt và gỡ bỏ

Workbench có thể hỗ trợ cài, cập nhật, vô hiệu hóa và gỡ plugin. Các thao tác này cần kiểm tra dependency, quyền và trạng thái đang sử dụng.

Nếu gỡ plugin cung cấp view đang mở, workbench cần đóng view an toàn và lưu trạng thái cần thiết.

## 7. Tùy biến perspective và lưu layout

Người dùng cần có khả năng điều chỉnh bố cục mà không làm mất cấu hình khi đóng workbench.

### 7.1. Layout model

Layout có thể được biểu diễn bằng cây:

~~~text
WorkbenchLayout
  editorArea
  split
    left:
      ModelExplorer
    right:
      tabGroup
        DslEditor
        Diagram
  bottom:
    tabGroup
      Problems
      Console
~~~

Layout model giúp lưu, khôi phục và kiểm tra bố cục. Không nên chỉ lưu tọa độ pixel vì màn hình và kích thước cửa sổ có thể thay đổi.

### 7.2. Lưu theo user, project và role

Có thể có nhiều lớp cấu hình:

| Phạm vi | Ví dụ | Nơi lưu phù hợp |
| --- | --- | --- |
| User | Vị trí panel, theme, font | User profile |
| Workspace | View thường dùng, perspective đang chọn | Workspace metadata |
| Project | Validator, target profile, template | Project config |
| Organization | Plugin được phép, policy | Quản trị tập trung |
| Role | Perspective mặc định | Role configuration |

Cần định nghĩa thứ tự ưu tiên khi các lớp cấu hình xung đột.

### 7.3. Default layout và reset

Workbench nên cung cấp layout mặc định có thể khôi phục. Nếu cấu hình cá nhân bị hỏng hoặc view bị mất, người dùng có thể reset perspective mà không phải xóa toàn bộ project preferences.

### 7.4. Layout migration

Khi nâng cấp workbench, ID view hoặc cấu trúc layout có thể thay đổi. Cần migration để đổi ID cũ, loại contribution đã bị gỡ và đặt view mới vào vị trí hợp lý.

Nếu không thể khôi phục một view, nên bỏ qua phần đó và thông báo rõ, thay vì làm workbench không khởi động được.

### 7.5. Đồng bộ giữa thiết bị

Nếu layout được đồng bộ qua tài khoản, cần xác định dữ liệu nào được đồng bộ. Một layout có thể tham chiếu plugin chỉ được cài trên một máy. Khi mở ở máy khác, workbench cần xử lý contribution không có sẵn.

## 8. Selection, context và đồng bộ giữa các view

Một workbench tích hợp cần biết người dùng đang chọn tài nguyên hoặc phần tử nào.

### 8.1. Selection model

Selection có thể là:

~~~text
Selection
  resourceUri
  elementId
  elementKind
  sourceRange
  projectId
~~~

Dùng định danh phần tử ổn định giúp view không phụ thuộc vào vị trí dòng hiện tại. Khi tài liệu được format hoặc chỉnh sửa, element ID hoặc semantic identity có thể được dùng để khôi phục selection nếu còn hợp lệ.

### 8.2. Selection event

Khi người dùng chọn Customer trong Model Explorer:

1. Explorer phát selection event.
2. Workbench cập nhật active context.
3. Properties view tải thuộc tính Customer.
4. Diagram view highlight quan hệ.
5. Editor điều hướng đến declaration nếu được cấu hình.

Event nên chứa resource identity và selection rõ ràng, tránh gửi cả object lớn qua event bus.

### 8.3. Active editor và active view

Active editor là tài liệu hoặc công cụ đang nhận thao tác chỉnh sửa. Active view là vùng đang nhận focus hoặc context command.

Một lệnh Rename cần biết symbol tại vị trí con trỏ trong editor. Một lệnh Delete Model Element có thể dùng selection từ explorer hoặc diagram.

### 8.4. Tránh vòng lặp event

Nếu Properties view cập nhật selection, rồi phát event khiến Explorer chọn lại, có thể tạo vòng lặp. Cần quy ước nguồn event, correlation ID hoặc cơ chế phân biệt user action với programmatic update.

### 8.5. Context không còn hợp lệ

Selection có thể trỏ đến node đã bị xóa hoặc tài liệu đã đóng. View cần xử lý trạng thái empty hoặc stale, không tiếp tục hiển thị dữ liệu cũ như thể nó còn hiện hành.

## 9. Command system và hành động theo ngữ cảnh

Command system tách định nghĩa lệnh khỏi vị trí hiển thị. Một command có thể xuất hiện trong menu, toolbar, context menu hoặc command palette.

### 9.1. Command definition

Một command có thể gồm:

~~~text
Command
  id
  title
  description
  handler
  enablementExpression
  visibilityExpression
  keybinding
~~~

Handler thực hiện logic. Enablement xác định lệnh có thể chạy trong context hiện tại hay không.

### 9.2. Context menu

Context menu của entity có thể gồm:

- Open.
- Rename.
- Create Relationship.
- Generate Schema.
- Validate.
- Show References.

Context menu của workflow có thể gồm:

- Run.
- Debug.
- View History.
- Export Diagram.

Chỉ hiển thị lệnh liên quan giúp giao diện gọn và dễ học.

### 9.3. Command palette

Command palette cho phép tìm lệnh bằng tên. Nó hữu ích khi workbench có nhiều plugin và command.

Kết quả tìm kiếm nên hỗ trợ:
- Từ khóa.
- Alias.
- Nhóm chức năng.
- Phím tắt.
- Context hiện tại.
- Trạng thái enabled hoặc lý do disabled.

### 9.4. Keybinding

Phím tắt cần có hệ thống ưu tiên và phát hiện xung đột. Plugin không nên âm thầm ghi đè phím tắt cốt lõi.

Có thể cho người dùng tùy chỉnh và reset về mặc định. Keybinding cũng nên được tài liệu hóa và hỗ trợ accessibility.

### 9.5. Command history

Workbench có thể lưu các lệnh gần đây để người dùng chạy lại. Với command có side effect như xóa hoặc deploy, history không nên tự thực thi lại khi người dùng chọn nhầm; cần xác nhận và kiểm tra context mới.

## 10. Tùy biến editor cho DSL

Editor là một phần quan trọng của workbench. Nó cần hiểu cú pháp và cung cấp công cụ phù hợp với DSL.

### 10.1. Text editor

Các tính năng phổ biến:

- Syntax highlighting.
- Code completion.
- Hover documentation.
- Go to definition.
- Find references.
- Rename.
- Diagnostics.
- Formatting.
- Code actions.
- Folding và outline.

Các tính năng này nên dùng chung parser và semantic model để tránh mỗi tính năng tự hiểu DSL theo cách khác.

### 10.2. Form-based editor

Với người dùng không muốn viết cú pháp trực tiếp, workbench có thể cung cấp form để chỉnh sửa model element.

Ví dụ form Entity:

~~~text
Entity
  Name: Customer
  Description: Thông tin khách hàng

Properties
  id       UUID       Required
  name     String     Required
  email    Email      Required, Unique
~~~

Form cần biểu diễn được các quy tắc của DSL và cập nhật model theo cùng semantics với text editor.

### 10.3. Text và form cùng chỉnh sửa một nguồn

Nếu text editor và form editor cùng sửa một model, cần đồng bộ hai chiều. Thay đổi ở một bên phải cập nhật bên kia hoặc phát hiện conflict.

Một chiến lược là có canonical model trong memory:
- Text thay đổi thì parse và cập nhật model.
- Form thay đổi thì tạo model edit hoặc source edit.
- Editor khác nhận document change và cập nhật.
- Khi parse lỗi, form có thể giữ trạng thái trước hoặc hiển thị phần dữ liệu chưa phân giải.

Không nên duy trì hai bản dữ liệu độc lập mà không có cơ chế hợp nhất.

### 10.4. Diagram editor

Diagram editor có thể cho phép kéo thả node, tạo quan hệ và đổi thuộc tính. Thao tác đồ họa cần chuyển thành model edit có thể serialize về DSL.

Cần phân biệt vị trí node trên canvas với semantics của mô hình. Kéo node chỉ đổi layout; nối hai node có thể thay đổi quan hệ nghiệp vụ.

### 10.5. Preview và generated view

Workbench có thể hiển thị schema, code hoặc diagram được sinh từ model. Preview nên thể hiện nguồn và trạng thái cập nhật. Nếu source model có lỗi, preview cần báo đang stale thay vì hiển thị kết quả cũ như thể mới nhất.

## 11. Tùy biến explorer, outline và properties

Các view này giúp người dùng điều hướng và hiểu mô hình.

### 11.1. Explorer

Explorer có thể hiển thị cây:

~~~text
Project
  modules
    sales
      Customer
      Order
      OrderStatus
    billing
      Invoice
  workflows
    processOrder
~~~

Người dùng có thể lọc theo loại tài nguyên, namespace, trạng thái hoặc tag.

### 11.2. Outline

Outline hiển thị cấu trúc của tài liệu đang mở:

~~~text
Order
  Properties
    id
    total
    status
  Constraints
    nonNegativeTotal
  Operations
    calculateTax
~~~

Outline nên cập nhật theo nội dung và giữ selection đồng bộ với editor.

### 11.3. Properties view

Properties view hiển thị metadata của phần tử đang chọn. Có thể chia nhóm:

- General.
- Type and constraints.
- Documentation.
- References.
- Generated mapping.
- Validation status.

Không nên hiển thị mọi field nội bộ của model. Chỉ đưa ra thuộc tính người dùng có thể hiểu và có quyền sửa.

### 11.4. Property editor theo kiểu

Editor của một property cần phù hợp kiểu dữ liệu:
- Boolean dùng checkbox.
- Enum dùng danh sách chọn.
- Date dùng date picker.
- Reference dùng resource selector.
- Expression dùng DSL expression editor.
- Collection dùng bảng hoặc list editor.

Validation nên chạy ngay khi nhập ở mức phù hợp và cung cấp message rõ.

### 11.5. Custom property page

Plugin có thể thêm một trang thuộc tính chuyên biệt, chẳng hạn Persistence, API Exposure hoặc Security. Page cần khai báo loại element hỗ trợ và cách đọc/ghi dữ liệu.

## 12. Wizard và template tạo tài nguyên

Wizard hướng dẫn người dùng tạo cấu trúc mới bằng một chuỗi bước có kiểm tra.

Ví dụ Create Entity wizard:

1. Nhập tên entity.
2. Chọn namespace.
3. Chọn base type nếu có.
4. Thêm property.
5. Chọn key và constraint.
6. Xem trước DSL.
7. Tạo tài nguyên.

### 12.1. Wizard schema

Một wizard có thể định nghĩa:
- Input fields.
- Validation.
- Default values.
- Conditional steps.
- Preview generator.
- Finish action.

Wizard không nên tự ghi file trước khi toàn bộ input hợp lệ và người dùng xác nhận.

### 12.2. Template

Template giúp tạo nhanh cấu trúc phổ biến:

~~~text
entity \${EntityName} {
  id: UUID required
  createdAt: Instant required
}
~~~

Template có thể theo project, namespace hoặc loại mô hình. Placeholder cần được validate và escape đúng cú pháp DSL.

### 12.3. Template version

Template có thể thay đổi theo phiên bản DSL. Workbench nên lưu template version hoặc generator version để tài nguyên được tạo có thể tái lập.

### 12.4. Preview và conflict

Trước khi tạo file, wizard cần kiểm tra:
- Tên tài nguyên đã tồn tại chưa.
- Đường dẫn có xung đột không.
- Namespace có hợp lệ không.
- Project có quyền ghi không.
- Template có tương thích với phiên bản DSL không.

## 13. Tùy biến diagram và trực quan hóa

Diagram là một cách thể hiện cấu trúc mô hình hoặc luồng thực thi.

### 13.1. Các loại diagram

Workbench có thể hỗ trợ:
- Entity relationship diagram.
- Class diagram.
- Workflow diagram.
- State machine.
- Dependency graph.
- Data flow.
- Query plan.
- Runtime execution graph.

Mỗi loại diagram cần xác định node, edge, layout, interaction và semantics.

### 13.2. Renderer và layout

Renderer quyết định cách hiển thị node và edge. Layout engine xác định vị trí và cách sắp xếp.

Tách hai phần giúp plugin có thể thay theme hoặc layout mà không thay đổi model.

### 13.3. Custom node và edge

Extension có thể cung cấp node renderer cho một loại model element mới hoặc edge renderer cho quan hệ đặc biệt.

Node cần có identity ổn định để selection, undo và model synchronization hoạt động.

### 13.4. Diagram metadata

Vị trí, màu, nhóm và trạng thái collapse thường là presentation metadata. Cần quyết định chúng lưu trong file mô hình, file phụ hay user workspace.

Không nên để metadata trình bày làm thay đổi semantics của DSL trừ khi ngôn ngữ quy định rõ.

### 13.5. Đồng bộ diagram với source

Khi người dùng kéo node hoặc tạo quan hệ, workbench cần cập nhật model và source theo quy tắc. Khi source thay đổi bên ngoài, diagram cần refresh hoặc đánh dấu stale.

Nếu hai bên cùng sửa đồng thời, cần cơ chế conflict resolution.

## 14. Preference và cấu hình workbench

Preference là thiết lập điều khiển hành vi hoặc cách trình bày.

### 14.1. Phân loại preference

- Appearance: theme, font, density.
- Editor: tab size, formatting, completion.
- Explorer: grouping, sorting, filters.
- Validation: mức cảnh báo và validator.
- Runtime: target, timeout, debug options.
- Diagram: layout, labels, grid.
- Accessibility: contrast, motion, focus.
- Privacy: telemetry và data masking.

### 14.2. Scope của preference

Preference có thể thuộc user, workspace, project hoặc organization. Mỗi loại cần có nơi lưu và quyền chỉnh sửa riêng.

### 14.3. Default và override

Một hệ thống có thể áp dụng:

~~~text
Organization defaults
       |
       v
Project overrides
       |
       v
Workspace preferences
       |
       v
User preferences
~~~

Đây chỉ là một thứ tự minh họa. Cần xác định rõ cấu hình nào có quyền cao hơn và thiết lập nào không được phép override do policy.

### 14.4. Validate preference

Preference có kiểu và miền giá trị. Ví dụ timeout phải dương; font size nằm trong khoảng hợp lý; target version phải được runtime hỗ trợ.

Không nên chấp nhận giá trị sai rồi để một view hoặc service thất bại khi sử dụng.

### 14.5. Import và export settings

Người dùng có thể export settings để chia sẻ hoặc chuyển máy. File export cần phân biệt cấu hình cá nhân với cấu hình có thể chia sẻ trong project, tránh vô tình đưa thông tin bí mật hoặc đường dẫn máy cục bộ vào repository.

## 15. Event bus và giao tiếp giữa extension

Workbench có nhiều thành phần cần phản ứng với thay đổi của nhau. Event bus giúp giảm phụ thuộc trực tiếp giữa các view.

### 15.1. Event phổ biến

- WorkspaceOpened.
- ResourceCreated.
- ResourceChanged.
- SelectionChanged.
- ModelValidated.
- BuildCompleted.
- WorkflowRunStarted.
- WorkflowRunFailed.
- EditorSaved.
- PerspectiveChanged.

### 15.2. Event contract

Event nên có:
- Event ID hoặc type.
- Resource identity.
- Payload có schema.
- Timestamp nếu cần.
- Correlation ID để nối chuỗi sự kiện.
- Version của event contract.

Payload nên đủ dùng nhưng không quá lớn. View có thể truy vấn service để lấy dữ liệu chi tiết.

### 15.3. Đồng bộ và bất đồng bộ

Event UI như selection có thể được xử lý nhanh trên thread giao diện. Công việc nặng như parse workspace hoặc generate diagram nên chạy bất đồng bộ và trả kết quả khi hoàn thành.

Cần quản lý cancellation khi người dùng chuyển selection trước khi tác vụ cũ kết thúc.

### 15.4. Tránh phụ thuộc vòng

Nếu View A gọi trực tiếp View B, View B gọi View C và C lại gọi A, kiến trúc khó bảo trì. Event và shared service giúp các thành phần phối hợp mà không phụ thuộc lẫn nhau quá chặt.

### 15.5. Event ordering

Một số thao tác cần thứ tự: ResourceChanged phải được xử lý trước ModelValidated cho cùng phiên bản tài liệu. Có thể dùng document version hoặc sequence number để loại bỏ kết quả cũ đến muộn.

## 16. Tùy biến và tích hợp service DSL

Workbench là lớp giao diện; các dịch vụ DSL cung cấp semantics và dữ liệu.

### 16.1. Parser service

Editor, outline và diagram có thể dùng parser service chung. Khi tài liệu thay đổi, parser tạo AST mới hoặc cập nhật incremental model.

### 16.2. Symbol và type service

Completion, hover, rename, properties và diagram đều có thể dùng symbol index và type information.

### 16.3. Validation service

Problems view và editor marker lấy diagnostics từ validator. Cấu hình mức severity có thể tùy biến, nhưng không nên làm thay đổi quy tắc semantics mà compiler sử dụng nếu người dùng không chủ ý.

### 16.4. Generator service

Schema preview hoặc code preview gọi generator với target profile. Workbench cần thể hiện phiên bản cấu hình và trạng thái stale của kết quả.

### 16.5. Runtime và debugger service

Run view, workflow monitor và debugger sử dụng runtime API. UI chỉ điều khiển trong phạm vi quyền và capability được cấp.

### 16.6. Resource service

Service này quản lý URI, project, file, dirty state, save, rename và move. Extension nên dùng resource API thay vì tự thao tác filesystem tùy tiện.

## 17. Bảo mật trong workbench mở rộng

Plugin có thể truy cập tài nguyên, thực thi code hoặc gửi dữ liệu ra ngoài. Vì vậy, workbench cần xem extension như thành phần có quyền hạn rõ ràng.

### 17.1. Quyền của plugin

Có thể khai báo capability:
- Read project files.
- Write project files.
- Register commands.
- Access runtime.
- Launch process.
- Connect to network.
- Read secrets.
- Access user profile.

Plugin chỉ nhận quyền cần thiết. Workbench có thể yêu cầu người dùng hoặc administrator phê duyệt capability nhạy cảm.

### 17.2. Trust boundary

Không nên xem plugin từ bất kỳ nguồn nào là đáng tin. Cần xác minh nguồn phân phối, chữ ký hoặc checksum nếu nền tảng hỗ trợ, và policy cài đặt.

### 17.3. Sandboxing

Nếu plugin chạy trong process hoặc sandbox riêng, có thể giới hạn filesystem, network, CPU và memory. Mức cách ly phụ thuộc nền tảng; không nên tuyên bố plugin được sandbox an toàn nếu thực tế vẫn chạy với toàn quyền của host.

### 17.4. Command authorization

Ẩn command khỏi menu không phải biện pháp bảo mật. Handler và backend service phải kiểm tra quyền khi command được gọi.

### 17.5. Dữ liệu dự án

Plugin có thể đọc source, schema và dữ liệu nghiệp vụ. Cần xác định dữ liệu nào được chia sẻ, có được gửi telemetry không và cách người dùng thu hồi quyền.

## 18. Khả năng tiếp cận và đa ngôn ngữ

Workbench nên dùng được bằng bàn phím, screen reader và các cấu hình hiển thị khác nhau.

### 18.1. Keyboard navigation

Các view, editor, dialog và toolbar cần có thứ tự focus rõ. Người dùng có thể mở command palette, chuyển view và thao tác mà không cần chuột.

### 18.2. Focus management

Khi mở wizard hoặc dialog, focus cần chuyển đến vị trí hợp lý. Khi đóng, focus trở về vùng trước đó. Khi một view được cập nhật, không nên tự ý lấy focus khỏi editor đang nhập.

### 18.3. Screen reader

Control cần label, trạng thái và thông báo thay đổi. Diagram cần mô tả thay thế hoặc một cấu trúc outline tương đương để người dùng không dựa hoàn toàn vào hình ảnh.

### 18.4. Contrast và màu sắc

Không dùng màu sắc làm tín hiệu duy nhất cho error, warning hoặc trạng thái node. Có thể kết hợp icon, text label và pattern.

### 18.5. Localization

Title, command, tooltip và message cần dùng message catalog. ID nội bộ của view và command phải ổn định, không dịch theo locale.

### 18.6. Layout co giãn

Workbench cần hoạt động ở màn hình nhỏ, zoom lớn và font lớn. Người dùng cần có cách chuyển panel thành tab hoặc ẩn view phụ khi không đủ diện tích.

## 19. Hiệu năng và độ ổn định

Một workbench có thể có nhiều plugin và view. Nếu tất cả khởi tạo cùng lúc, thời gian mở project và mức sử dụng bộ nhớ sẽ tăng.

### 19.1. Lazy loading

Chỉ tạo view khi người dùng mở hoặc khi perspective yêu cầu. Plugin ít dùng có thể activate khi command đầu tiên được gọi.

### 19.2. Incremental update

Khi một property thay đổi, không nhất thiết phải parse lại toàn workspace hoặc render lại mọi diagram. Dùng dependency và event để cập nhật phần bị ảnh hưởng.

### 19.3. Debounce và cancellation

Trong khi người dùng gõ, validator có thể chờ một khoảng ngắn trước khi chạy. Nếu có input mới, tác vụ cũ được hủy hoặc kết quả cũ bị bỏ qua.

### 19.4. Virtualization

Explorer có thể chứa hàng chục nghìn phần tử. Chỉ render các node đang nhìn thấy và tải children khi mở rộng.

### 19.5. Resource cleanup

Khi đóng project hoặc view, giải phóng listener, subscription, file watcher, task và cache không còn cần thiết.

### 19.6. Plugin lỗi

Một plugin crash không nên làm sập toàn bộ workbench nếu kiến trúc hỗ trợ cách ly. Core cần ghi nhận lỗi, vô hiệu hóa contribution bị lỗi và cho phép người dùng tiếp tục công việc.

## 20. Kiểm thử workbench tùy biến

Kiểm thử cần bao phủ core, extension API, layout, tương tác và khả năng phục hồi.

### 20.1. Kiểm thử extension registry

- Manifest hợp lệ và không hợp lệ.
- ID trùng.
- Dependency thiếu.
- Version không tương thích.
- Extension point không tồn tại.
- Plugin activate và deactivate.
- Cleanup listener và resource.

### 20.2. Kiểm thử layout

- Mở perspective mặc định.
- Đóng và mở lại workbench.
- Lưu và khôi phục layout.
- View bị gỡ hoặc plugin không còn.
- Màn hình nhỏ và zoom lớn.
- Reset perspective.
- Migration layout qua phiên bản.

### 20.3. Kiểm thử selection và event

- Chọn element cập nhật properties.
- Chọn resource cập nhật editor.
- Event cũ không ghi đè selection mới.
- Không có vòng lặp selection.
- View xử lý resource đã bị xóa.

### 20.4. Kiểm thử command

- Enablement theo context.
- Authorization ở backend.
- Keybinding conflict.
- Command palette search.
- Command handler lỗi.
- Undo hoặc confirmation cho thao tác có side effect.

### 20.5. Kiểm thử tích hợp DSL

- Parser và validator dùng chung semantics.
- Diagram và text editor đồng bộ.
- Form edit tạo source hợp lệ.
- Generator preview được đánh dấu stale đúng lúc.
- Debugger mở đúng resource và source location.

### 20.6. Kiểm thử accessibility

- Keyboard-only navigation.
- Focus order.
- Screen reader labels.
- Contrast.
- Không phụ thuộc màu sắc.
- Localization và text dài.

### 20.7. Kiểm thử hiệu năng và độ bền

Đo thời gian mở workspace, khởi tạo perspective, tải explorer lớn, mở nhiều editor và activate nhiều plugin. Kiểm tra đóng/mở project nhiều lần không làm listener hoặc memory tăng liên tục.

## 21. Ví dụ: thiết kế workbench cho DSL workflow

Giả sử DSL mô tả quy trình xử lý đơn hàng:

~~~text
workflow processOrder(order: Order) {
  step validate {
    validateOrder(order)
  }

  step reserve {
    reserveInventory(order)
  }

  step charge {
    chargePayment(order)
  }

  step notify {
    publishConfirmation(order)
  }
}
~~~

Một workbench Workflow Design có thể gồm:

~~~text
+----------------------+-----------------------------+
| Workflow Explorer    | Workflow Editor             |
|                      |                             |
| processOrder         | [validate] -> [reserve]     |
| refundOrder          |      -> [charge] -> [notify]|
| cancelOrder          |                             |
+----------------------+-----------------------------+
| Properties           | Diagnostics / Run History  |
+----------------------+-----------------------------+
~~~

### 21.1. Workflow Explorer

Hiển thị workflow, step và resource liên quan. Người dùng có thể tạo workflow, mở editor và tìm kiếm theo tên.

### 21.2. Workflow Editor

Có thể cung cấp text editor, diagram hoặc chế độ kết hợp. Khi người dùng chọn step charge trên diagram, editor highlight declaration và Properties view hiển thị cấu hình timeout, retry và input/output.

### 21.3. Properties view

Khi chọn step reserve, view có thể hiển thị:
- Action được gọi.
- Input mapping.
- Output mapping.
- Retry policy.
- Timeout.
- Error handler.

Form chỉ cho sửa các trường hợp lệ theo type system và workflow semantics.

### 21.4. Run History

Run History hiển thị execution đã chạy, trạng thái và thời gian. Chọn một lần chạy mở workflow monitor hoặc debugger tại step phù hợp.

### 21.5. Extension cho action mới

Một plugin có thể đăng ký action payment provider với metadata:
- Tên action.
- Chữ ký input/output.
- Capability cần có.
- Tài liệu.
- Form cấu hình.
- Runtime adapter.

Workbench hiển thị action trong completion và palette. Validator kiểm tra chữ ký; runtime gọi implementation đã được cấp quyền.

### 21.6. Perspective theo vai trò

Người phân tích nghiệp vụ có thể dùng diagram và properties. Người phát triển dùng source editor, diagnostics và debugger. Người vận hành dùng Run History, logs và execution monitor.

Cùng một model và resource service được dùng chung, nhưng bố cục và công cụ ưu tiên khác nhau.

## 22. Quy trình thiết kế workbench tùy biến

Khi xây workbench cho DSL, có thể thực hiện theo các bước:

### Bước 1: Xác định người dùng và nhiệm vụ

Liệt kê vai trò, loại tài nguyên và các tác vụ chính. Không bắt đầu từ danh sách widget mà chưa hiểu người dùng cần hoàn thành việc gì.

### Bước 2: Xác định mô hình tài nguyên và selection

Định nghĩa resource identity, model element ID, workspace context và selection contract để mọi view phối hợp được.

### Bước 3: Thiết kế core services

Xác định command registry, view/editor registry, layout manager, event bus, preference service và resource service.

### Bước 4: Chọn extension point

Chỉ mở rộng các điểm cần thiết: view, command, editor, wizard, renderer, validator hoặc runtime service. Mỗi extension point cần schema và lifecycle rõ.

### Bước 5: Xây perspective mặc định

Cung cấp bố cục khởi đầu cho từng nhiệm vụ phổ biến. Cho phép tùy biến và reset về mặc định.

### Bước 6: Tích hợp DSL services

Dùng chung parser, symbol index, validator, generator và runtime. Tránh logic phân tích riêng trong từng view.

### Bước 7: Thiết kế lưu cấu hình

Phân biệt user, workspace, project và organization preferences. Xác định thứ tự override, import/export và migration.

### Bước 8: Thiết lập quyền và sandbox

Xác định capability của plugin, quyền đọc/ghi, network, runtime và secret. Backend phải xác minh quyền cho mọi thao tác nhạy cảm.

### Bước 9: Kiểm thử tương tác và vòng đời

Kiểm tra selection, event, command, layout, plugin activation, cleanup và xử lý lỗi.

### Bước 10: Đo hiệu năng và khả năng tiếp cận

Kiểm tra workspace lớn, nhiều plugin, bàn phím, screen reader, localization và màn hình nhỏ.

## 23. Những lỗi thiết kế thường gặp

**Đồng nhất workbench với một editor lớn.** Người dùng cần explorer, properties, diagram, diagnostics và runtime tools phối hợp. Hãy thiết kế môi trường làm việc theo nhiệm vụ.

**Cho phép tùy biến nhưng không có mặc định tốt.** Người mới có thể thấy màn hình trống hoặc quá phức tạp. Hãy cung cấp perspective mặc định và khả năng reset.

**View tự triển khai parser riêng.** Các view có thể hiểu model khác nhau. Hãy dùng DSL services và model chung.

**Dùng title làm ID.** Đổi tên hoặc dịch title sẽ phá cấu hình và tham chiếu. Hãy dùng ID ổn định.

**Không phân biệt visibility, enablement và authorization.** Ẩn nút không bảo vệ tài nguyên. Backend phải kiểm tra quyền.

**Lưu mọi cấu hình vào một nơi.** Thiết lập cá nhân có thể bị commit vào project hoặc policy tổ chức bị override. Hãy phân loại scope.

**Plugin không có lifecycle cleanup.** Listener và task tồn tại sau khi plugin bị tắt. Hãy yêu cầu activate/deactivate có quản lý tài nguyên.

**Layout phụ thuộc tọa độ cố định.** Màn hình khác nhau có thể làm panel biến mất. Hãy dùng layout model co giãn và migration.

**Event bus không có version hoặc ordering.** View có thể hiển thị dữ liệu stale. Hãy dùng resource version và event contract rõ.

**Tích hợp text và diagram không có nguồn chuẩn.** Hai editor có thể ghi đè nhau. Hãy dùng canonical model và conflict handling.

**Plugin có quá nhiều quyền.** Một extension nhỏ có thể đọc hoặc ghi mọi project. Hãy áp dụng capability tối thiểu và sandbox phù hợp.

**Không kiểm thử accessibility và hiệu năng.** Workbench có thể chỉ dùng được với chuột hoặc chậm khi project lớn. Hãy kiểm thử các tình huống sử dụng thực tế.

## 24. Kết luận

Workbench tùy biến là môi trường phát triển DSL có thể điều chỉnh theo nhiệm vụ, vai trò, project và người dùng. Nó kết hợp editor, explorer, properties, diagram, diagnostics, command, wizard, runtime tools và các extension. Các lớp tùy biến có thể gồm giao diện cá nhân, cấu hình project, perspective theo vai trò và plugin mở rộng chức năng.

Một kiến trúc bền vững cần workbench core, resource model, selection context, command registry, view/editor registry, layout manager, event bus, preference service và extension contract ổn định. Các view nên dùng chung parser, symbol index, validator, generator và runtime để giữ semantics nhất quán. Plugin cần manifest, dependency, lifecycle, quyền hạn và cleanup rõ ràng. Cấu hình cần được phân loại theo user, workspace, project và organization.

Hãy bắt đầu từ nhiệm vụ và vai trò của người dùng, sau đó thiết kế perspective mặc định cùng các extension point thực sự cần thiết. Khi workbench có cấu trúc mở rộng rõ, layout dễ khôi phục, quyền được kiểm soát và các công cụ dùng chung mô hình DSL, người dùng có thể xây dựng môi trường làm việc phù hợp mà vẫn giữ được tính nhất quán của nền tảng.

