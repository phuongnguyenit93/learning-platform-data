# Chọn phạm vi build trong monorepo mà không bỏ sót phụ thuộc

Monorepo thường chứa nhiều ứng dụng, thư viện và công cụ trong cùng một repository. Cách đơn giản nhất để bảo đảm mọi thay đổi đều được kiểm tra là build và test toàn bộ dự án sau mỗi lần push. Cách này an toàn nhưng có thể rất chậm khi repository lớn, nhiều nhóm cùng làm việc và phần lớn thay đổi chỉ tác động đến một vài project.

Tối ưu ngược lại bằng cách chỉ build thư mục có file thay đổi cũng có rủi ro. Một thay đổi trong thư viện dùng chung có thể ảnh hưởng đến hàng chục ứng dụng; thay đổi schema, file cấu hình gốc hoặc build plugin có thể tác động đến các project không nằm trong thư mục vừa sửa. Nếu pipeline bỏ sót một consumer, nó có thể báo xanh trong khi một project phụ thuộc đã bị hỏng.

Vì vậy, chọn phạm vi build trong monorepo cần kết hợp **danh sách file thay đổi, bản đồ project và đồ thị phụ thuộc**. Pipeline phải xác định project bị thay đổi, tìm tất cả project phụ thuộc trực tiếp hoặc gián tiếp, rồi tạo kế hoạch build/test theo đúng thứ tự. Khi không đủ dữ liệu để chứng minh phạm vi ảnh hưởng, pipeline cần mở rộng phạm vi hoặc chạy full build.

Bài học này trình bày cách xác định changed projects, phân tích dependency graph, xử lý file dùng chung, xây dựng selective build/test, kiểm soát rủi ro false green và đo hiệu quả tối ưu. Mục tiêu là giảm công việc không cần thiết mà vẫn giữ nguyên độ tin cậy của các quality gate.

## 1. Monorepo và bài toán xác định phạm vi thay đổi

Monorepo lưu nhiều project trong cùng một repository. Các project có thể là:

- Ứng dụng hoặc service có thể triển khai độc lập.
- Thư viện dùng chung giữa nhiều ứng dụng.
- Package hoặc module chứa API, schema và contract.
- Công cụ build, code generation hoặc migration.
- Bộ kiểm thử, fixture và test utilities.
- Hạ tầng, deployment manifest và cấu hình môi trường.

Ví dụ cấu trúc:

~~~text
repository/
  apps/
    web-store/
    admin-portal/
    order-api/
  libs/
    ui-components/
    order-domain/
    auth-client/
  schemas/
    events/
    openapi/
  tools/
    codegen/
    build-logic/
  config/
    lint/
    typescript/
  package.json
  lockfile
  build-config/
~~~

Nếu chỉ sửa apps/web-store, có thể chỉ cần kiểm tra web-store cùng những thư viện mà nó phụ thuộc. Nhưng nếu sửa libs/auth-client, các ứng dụng sử dụng thư viện này cũng cần được kiểm tra. Nếu sửa root lockfile hoặc build logic dùng chung, phạm vi có thể là toàn bộ repository.

Bài toán có hai câu hỏi:

1. **Project nào chứa file thay đổi?** Đây là bước ánh xạ path sang project sở hữu file.
2. **Project nào bị ảnh hưởng bởi project đó?** Đây là bước truy vấn đồ thị phụ thuộc, đặc biệt là các project phụ thuộc ngược (reverse dependents).

Chỉ giải quyết câu hỏi đầu tiên sẽ bỏ sót tác động lan truyền.

## 2. Mô hình project và dependency graph

Trước khi tính phạm vi build, repository cần có ranh giới project rõ ràng và metadata mô tả quan hệ giữa chúng.

Một project nên có định danh ổn định, thư mục gốc, loại project và tập target có thể chạy:

| Thuộc tính | Ví dụ | Ý nghĩa |
|---|---|---|
| Project ID | order-api | Tên định danh ổn định |
| Root path | apps/order-api | Thư mục sở hữu source và cấu hình |
| Type | application | Ứng dụng, thư viện hoặc tool |
| Targets | lint, test, build, package | Các tác vụ CI có thể chạy |
| Dependencies | order-domain, auth-client | Project mà project này sử dụng |
| Owner | team-orders | Nhóm chịu trách nhiệm |

Dependency graph biểu diễn các quan hệ phụ thuộc. Nếu A dùng B, có thể biểu diễn cạnh A → B theo nghĩa “A phụ thuộc B”. Khi B thay đổi, A có khả năng bị ảnh hưởng.

Ví dụ:

~~~mermaid
flowchart BT
    D["auth-client"] --> B["order-domain"]
    B --> A["order-api"]
    C["ui-components"] --> E["web-store"]
    D --> E
    F["event-schema"] --> B
    F --> A
~~~

Trong sơ đồ này:

- order-api phụ thuộc order-domain.
- order-domain phụ thuộc auth-client và event-schema.
- web-store phụ thuộc ui-components và auth-client.

Nếu auth-client thay đổi, không chỉ auth-client cần build/test. Các project phụ thuộc nó như order-domain, order-api và web-store cũng có thể cần được kiểm tra. Đây là reverse dependency traversal.

### 2.1. Phân biệt dependency trực tiếp và bắc cầu

Dependency trực tiếp là quan hệ được khai báo ngay giữa hai project. Dependency bắc cầu là quan hệ đi qua một hoặc nhiều project trung gian.

Ví dụ:

- order-api phụ thuộc order-domain.
- order-domain phụ thuộc auth-client.
- order-api không khai báo auth-client trực tiếp, nhưng vẫn có thể bị ảnh hưởng khi auth-client thay đổi.

Nếu chỉ lấy dependents trực tiếp của auth-client, pipeline sẽ kiểm tra order-domain nhưng bỏ qua order-api. Cần tính toàn bộ transitive reverse dependents.

### 2.2. Đồ thị cần mô tả đúng loại phụ thuộc

Không phải mọi quan hệ đều giống nhau. Nên phân biệt khi cần:

- Build dependency: cần project khác để biên dịch hoặc đóng gói.
- Runtime dependency: ứng dụng gọi service khác khi chạy.
- Test dependency: test cần fixture, service hoặc contract của project khác.
- Code generation dependency: source được sinh từ schema hoặc API definition.
- Deployment dependency: một project chỉ có thể triển khai khi thành phần khác sẵn sàng.

Đối với selective build, build/test dependency, generated-code dependency và contract dependency thường quan trọng nhất. Runtime dependency cũng có thể cần integration/contract test khi thay đổi API hoặc hành vi tương thích.

Nếu đồ thị chỉ chứa dependency khai báo trong package manager mà bỏ qua codegen, test fixture hoặc shared configuration, kết quả affected projects có thể thiếu.

## 3. Xác định các file đã thay đổi bằng Git

Bước đầu tiên là lấy danh sách file thay đổi giữa revision nền và revision đang kiểm tra.

Với pull request, revision nền thường là merge base giữa nhánh đích và nhánh nguồn. Với push trên một nhánh, có thể dùng before SHA và after SHA do CI provider cung cấp. Cần chọn đúng cặp commit cho loại trigger.

Ví dụ lấy merge base và danh sách thay đổi:

~~~bash
git fetch origin main
BASE="$(git merge-base origin/main HEAD)"
HEAD_SHA="$(git rev-parse HEAD)"

git diff --name-status --find-renames "$BASE" "$HEAD_SHA"
~~~

Dùng merge base giúp xét toàn bộ thay đổi của nhánh hiện tại so với điểm chung với nhánh đích. Với pull request nhiều commit, chỉ dùng HEAD~1 sẽ bỏ sót các file được sửa trong những commit trước đó.

Trong CI, nên ưu tiên base/head SHA rõ ràng từ provider. Nếu checkout nông (shallow clone) không có đủ lịch sử để tính merge base, hãy fetch thêm history. Nếu vẫn không xác định được base đáng tin cậy, dùng full build thay vì tự chọn một commit gần nhất rồi suy đoán.

### 3.1. Xử lý rename và delete

Danh sách thay đổi cần giữ trạng thái của file:

| Trạng thái Git | Ý nghĩa | Cách xử lý |
|---|---|---|
| A | File mới | Ánh xạ path mới sang project |
| M | File được sửa | Ánh xạ project sở hữu file |
| D | File bị xóa | Dùng path cũ để xác định project bị ảnh hưởng |
| R | File được đổi tên | Xem cả path cũ và path mới |
| C | File được copy | Xem path đích và quy tắc ownership |

Nếu chỉ xử lý file còn tồn tại trong working tree, pipeline có thể bỏ qua file đã xóa. File rename từ project A sang project B có thể ảnh hưởng cả hai project. Hãy đọc output dạng name-status hoặc dùng API diff có cấu trúc thay vì parse chuỗi path theo cách dễ mất thông tin.

### 3.2. Phân biệt thay đổi trong working tree và thay đổi của commit

CI thường kiểm tra một commit sạch, nhưng local workflow hoặc một số pipeline tùy biến có thể có file chưa commit. Cần xác định phạm vi đo dựa trên revision được build, không trộn lẫn file local ngoài commit vào kết quả mà không chủ ý.

Lưu lại base SHA, head SHA và danh sách file thay đổi trong log để có thể tái hiện quyết định affected projects sau này.

## 4. Ánh xạ file thay đổi sang project sở hữu

Sau khi có changed paths, pipeline cần tìm project sở hữu từng file.

Một cách đơn giản là khai báo root path cho từng project:

~~~yaml
projects:
  order-api:
    root: apps/order-api
    type: application

  order-domain:
    root: libs/order-domain
    type: library

  auth-client:
    root: libs/auth-client
    type: library

  web-store:
    root: apps/web-store
    type: application
~~~

File apps/order-api/src/OrderController.java thuộc order-api. File libs/auth-client/src/AuthClient.ts thuộc auth-client.

Trong thực tế, có thể dùng project manifest, workspace configuration hoặc build system để lấy thông tin thay vì duy trì một mapping riêng. Quan trọng là mapping phải được kiểm tra và có owner.

### 4.1. File không thuộc project cụ thể

Một số file có phạm vi rộng:

- Root package manifest hoặc lockfile.
- Build scripts và plugin dùng chung.
- Compiler configuration gốc.
- Quy tắc lint, formatter và test runner.
- CI workflow hoặc script tính affected projects.
- Code generation tool.
- Schema hoặc API contract được nhiều project sử dụng.
- Container base image hoặc toolchain definition.
- Script triển khai dùng chung.

Không nên mặc định mọi file nằm ngoài thư mục apps/ và libs/ đều không ảnh hưởng project nào. Cần phân loại chúng thành:

- Global inputs: thay đổi có thể ảnh hưởng tất cả project hoặc một tập project lớn.
- Shared inputs: thay đổi ảnh hưởng một nhóm project đã biết.
- Repository metadata: thay đổi chỉ cần một số kiểm tra riêng.
- Unknown paths: chưa có quy tắc ownership, cần mở rộng phạm vi hoặc full build.

### 4.2. Lockfile và dependency manifest

Nếu repository dùng một lockfile gốc cho toàn bộ workspace, thay đổi lockfile có thể cập nhật dependency của nhiều project. Khi không thể xác định package nào thay đổi và project nào sử dụng package đó, coi lockfile là global input.

Nếu mỗi package có lockfile riêng, có thể ánh xạ lockfile đó đến project tương ứng, nhưng cần tính đến workspace package hoặc dependency resolution dùng chung.

### 4.3. File cấu hình kế thừa

Một project có thể kế thừa tsconfig, lint config, compiler options hoặc build logic từ file gốc. Khi file gốc thay đổi, tất cả project tham chiếu đến nó đều có thể bị ảnh hưởng.

Không chỉ ánh xạ theo thư mục chứa file. Hãy mô hình hóa quan hệ cấu hình hoặc dùng rule rõ ràng cho các file global/shared.

## 5. Tính affected projects bằng reverse dependency traversal

Sau khi xác định project trực tiếp bị thay đổi (seed projects), cần tính các project phụ thuộc vào chúng.

Giả sử cạnh A → B nghĩa là A phụ thuộc B. Nếu B thay đổi, ta cần lấy B và tất cả project có đường đi đến B trong đồ thị này.

Thuật toán khái quát:

1. Tạo tập changed projects từ các file đã thay đổi.
2. Nếu có global input, thêm tất cả project trong phạm vi global.
3. Đưa changed projects vào hàng đợi.
4. Tìm tất cả reverse dependents của từng project.
5. Thêm project chưa được xử lý vào tập affected và hàng đợi.
6. Tiếp tục đến khi không còn project mới.
7. Trả về tập affected cùng lý do từng project được chọn.

Pseudo-code:

~~~text
affected = set(changed_projects)
queue = list(changed_projects)

while queue is not empty:
    changed = queue.pop()

    for dependent in reverse_dependencies[changed]:
        if dependent not in affected:
            affected.add(dependent)
            queue.push(dependent)

return affected
~~~

Dùng set để tránh xử lý lặp khi một project có nhiều đường phụ thuộc đến project thay đổi.

### 5.1. Ví dụ lan truyền ảnh hưởng

Giả sử đồ thị:

- order-domain phụ thuộc auth-client.
- order-api phụ thuộc order-domain.
- web-store phụ thuộc auth-client.
- admin-portal không phụ thuộc auth-client.

Nếu chỉ sửa auth-client, tập affected là:

- auth-client.
- order-domain.
- order-api.
- web-store.

admin-portal không cần build chỉ vì thay đổi này, miễn là dependency graph đầy đủ và không có shared/global input khác.

Nếu sửa order-api, chỉ order-api và các consumer phụ thuộc order-api (nếu có) cần được xem xét. Không cần build tất cả thư viện mà order-api sử dụng chỉ vì chúng là dependencies của nó, trừ khi build target cần tạo chúng hoặc test policy yêu cầu.

### 5.2. Build order và test order

Khi A phụ thuộc B, B thường phải được build trước A. Có thể dùng topological sort để tạo thứ tự build hợp lệ.

Các project độc lập có thể chạy song song. Các project có dependency phải tuân thủ thứ tự hoặc dùng build system có khả năng lập task graph.

Không nên tự viết thứ tự theo tên thư mục. Hãy lấy thứ tự từ dependency graph và task graph của build system.

## 6. Thay đổi trong dependency graph cần được xử lý đặc biệt

File khai báo dependency hoặc cấu hình workspace cũng có thể thay đổi. Ví dụ, order-api bắt đầu phụ thuộc auth-client hoặc một project bỏ dependency cũ.

Nếu chỉ dùng graph cũ để tính affected, pipeline có thể bỏ sót quan hệ mới. Nếu chỉ dùng graph mới, nó có thể bỏ sót consumer từng phụ thuộc vào một thư viện trước khi dependency bị xóa.

Một cách an toàn là tính ảnh hưởng từ cả graph trước và graph sau:

- Dùng graph ở base revision để tìm các project từng phụ thuộc vào thành phần bị thay đổi/xóa.
- Dùng graph ở head revision để tìm các project hiện phụ thuộc vào thành phần thay đổi/thêm mới.
- Hợp hai tập affected lại.
- Nếu không thể tạo hoặc so sánh graph đáng tin cậy, chạy full build.

Thay đổi project manifest, workspace configuration, build plugin hoặc script tính affected nên được xem là thay đổi có phạm vi rộng cho đến khi có kiểm tra chứng minh được phạm vi hẹp hơn.

### 6.1. Thay đổi thêm hoặc xóa project

Khi thêm project mới, cần kiểm tra project đó và những consumer mới nếu có. Khi xóa project, cần kiểm tra các project trước đây phụ thuộc nó để bảo đảm dependency đã được gỡ hoặc thay thế.

Nếu một project bị rename, cần xử lý cả định danh cũ và mới để không làm mất lịch sử hoặc bỏ sót dependency.

## 7. Chọn target build, test và lint cho affected projects

Affected projects là danh sách project cần xem xét. Nó chưa tự quyết định mọi target phải chạy.

Có thể dùng policy theo loại project và loại thay đổi:

| Loại project/thay đổi | Target thường cần chạy |
|---|---|
| Application source | lint, unit test, build |
| Library source | lint, unit test, build và test consumer |
| API/schema/contract | validate schema, generate code, contract test và consumer test |
| Test fixture/shared test utility | test các project sử dụng fixture |
| Build logic/plugin | build/test các project dùng logic đó, thường mở rộng toàn workspace |
| Root lockfile | dependency validation và build/test theo phạm vi lockfile |
| Documentation | link check, markdown lint hoặc docs build |
| Deployment manifest | validate manifest và kiểm tra policy triển khai |

Một thay đổi chỉ sửa tài liệu có thể không cần compile toàn bộ ứng dụng. Nhưng nếu tài liệu được sinh từ schema hoặc chứa code sample có kiểm thử, vẫn cần chạy các kiểm tra tương ứng.

### 7.1. Tách project selection khỏi target selection

Nên có hai bước độc lập:

- **Project selection:** xác định project nào có khả năng bị ảnh hưởng.
- **Target selection:** xác định lint/test/build/contract/deploy validation nào cần chạy cho từng project.

Tách hai bước giúp policy dễ hiểu và kiểm thử. Một project có thể cần test nhưng không cần deploy; một thay đổi schema có thể yêu cầu codegen và contract test ở nhiều consumer.

### 7.2. Kiểm tra consumer của library

Khi thư viện public API thay đổi, test riêng thư viện chưa đủ. Consumer có thể phụ thuộc vào method, type hoặc behavior cũ.

Cần chạy compile/test của consumer, hoặc contract compatibility test phù hợp. Nếu thư viện có nhiều consumer nhưng graph chưa mô tả đầy đủ, mở rộng phạm vi hoặc full build.

## 8. Xử lý file global, shared và unknown

Selective build chỉ đáng tin khi mọi file thay đổi đều được ánh xạ hoặc có quy tắc fallback.

Một policy tham khảo:

| Nhóm file | Phạm vi gợi ý |
|---|---|
| Source trong project root | Project sở hữu và reverse dependents |
| Shared library | Library và toàn bộ reverse dependents |
| Root lockfile | Toàn workspace hoặc các project sử dụng dependency bị đổi nếu có phân tích chính xác |
| Root build config/plugin | Các project kế thừa/sử dụng; full build nếu không chứng minh được |
| CI workflow hoặc affected script | Validate pipeline logic và full build trong thay đổi nhạy cảm |
| Schema dùng chung | Codegen, contract và tất cả consumer |
| File docs riêng | Docs checks và project docs liên quan |
| Path chưa được phân loại | Full build hoặc yêu cầu bổ sung ownership rule |

Không dùng rule kiểu “file không nằm trong apps/ thì bỏ qua”. Điều đó có thể bỏ qua root build logic hoặc shared config.

### 8.1. Thay đổi nhiều nhóm file

Một pull request có thể vừa sửa source một project, vừa sửa root config và schema dùng chung. Hãy hợp các tác động lại thành một tập affected duy nhất, sau đó chọn target tương ứng. Không chạy trùng cùng một project nhiều lần chỉ vì nó được chọn bởi nhiều rule.

### 8.2. Thay đổi không liên quan source

Các thay đổi như workflow, build script, dependency manifest, Dockerfile nền hoặc codegen tool có thể ảnh hưởng toàn repository dù không nằm trong project root. Cần đưa chúng vào global/shared input policy.

## 9. Tạo kế hoạch pipeline từ tập affected

Sau khi có affected projects và target, pipeline nên tạo một execution plan có thể quan sát và truy vết.

Một flow tổng quát:

~~~mermaid
flowchart TD
    A["Nhận base/head revision"] --> B["Lấy Git diff"]
    B --> C["Phân loại paths"]
    C --> D["Map paths thành seed projects"]
    D --> E{"Có global hoặc unknown input?"}
    E -- "Có" --> F["Mở rộng phạm vi / full build"]
    E -- "Không" --> G["Tính reverse dependents"]
    G --> H["Chọn targets theo project và change type"]
    F --> I["Tạo execution plan"]
    H --> I
    I --> J["Topological order và parallel scheduling"]
    J --> K["Build / test / lint"]
    K --> L["Tổng hợp required checks"]
    L --> M["Lưu affected report và kết quả"]
~~~

Execution plan nên lưu:

- Base SHA và head SHA.
- Danh sách changed paths và trạng thái A/M/D/R.
- Project sở hữu từng path.
- Seed projects và lý do chọn.
- Affected projects và đường phụ thuộc dẫn đến chúng.
- Target được chọn cho từng project.
- Lý do chạy full build nếu có.
- Kết quả của từng job và required check.

Nhờ đó, khi một project bị bỏ sót, nhóm có thể kiểm tra rule path mapping hoặc dependency graph thay vì chỉ thấy pipeline xanh.

## 10. Ví dụ lệnh và cấu hình selective build

Các công cụ monorepo thường có chức năng tính project bị ảnh hưởng. Cú pháp cụ thể phụ thuộc tool và phiên bản; hãy dùng base/head revision rõ ràng.

Ví dụ với Nx:

~~~bash
npx nx affected -t lint test build \
  --base=origin/main \
  --head=HEAD
~~~

Lệnh này minh họa việc yêu cầu Nx tính các project affected theo thay đổi Git và chạy các target đã chọn. Cần bảo đảm lịch sử Git đủ để xác định base và dependency graph được cập nhật đúng.

Với Gradle multi-project, có thể gọi task theo project path khi đã xác định được phạm vi:

~~~bash
./gradlew :order-domain:test :order-api:test
~~~

Đây là ví dụ task cụ thể. Việc xác định project affected vẫn cần dựa trên project graph, convention plugin hoặc logic riêng của repository. Không nên suy ra dependency chỉ từ tên module.

### 10.1. Ví dụ plan dạng YAML

~~~yaml
change_scope:
  base: "origin/main"
  head: "HEAD"
  changed_paths:
    - "libs/auth-client/src/AuthClient.ts"

  seed_projects:
    - auth-client

  affected_projects:
    - auth-client
    - order-domain
    - order-api
    - web-store

  targets:
    auth-client:
      - lint
      - test
      - build
    order-domain:
      - lint
      - test
      - build
    order-api:
      - lint
      - test
      - build
    web-store:
      - lint
      - test
      - build

  fallback:
    full_build: false
    reason: "All changed paths mapped and dependency graph validated"
~~~

Plan là dữ liệu giải thích quyết định, không phải nguồn sự thật độc lập. Nó phải được sinh từ revision và graph đã xác minh, đồng thời được lưu cùng pipeline run.

## 11. Path filters và những giới hạn thường gặp

Path filter có thể giúp bỏ qua workflow hoặc job khi thay đổi không liên quan. Tuy nhiên, path filter chỉ nhìn đường dẫn; nó không tự hiểu quan hệ phụ thuộc giữa project.

Ví dụ, chỉ thay đổi libs/auth-client nhưng workflow chỉ lọc apps/order-api sẽ không chạy nếu path filter không nhận ra thư viện được dùng gián tiếp.

Một số giới hạn:

- Không tự tính transitive dependents.
- Có thể bỏ sót file bị xóa hoặc rename nếu xử lý path không đầy đủ.
- Root config/lockfile có thể tác động nhiều project.
- Pull request nhiều commit cần so sánh đúng base/head.
- Một số CI provider có cách xử lý skipped workflow/check khác nhau; required check có thể vẫn được coi là pending hoặc không đạt theo policy.
- Path filter có thể không chạy workflow tổng hợp cần thiết để báo kết quả.

### 11.1. Giữ required check luôn có kết quả rõ ràng

Một pattern an toàn là tạo một job điều phối/aggregate luôn được chạy. Job này:

1. Tính changed projects và affected projects.
2. Tạo các job kiểm tra cần thiết.
3. Đánh dấu rõ project/target nào được skip theo policy.
4. Chờ tất cả required jobs kết thúc.
5. Trả kết quả pass chỉ khi toàn bộ gate bắt buộc đạt hoặc được skip hợp lệ theo rule đã định nghĩa.

Không để trạng thái “không chạy” bị hiểu nhầm là “đã kiểm tra thành công”. Báo cáo nên phân biệt **PASSED**, **FAILED**, **SKIPPED_BY_POLICY** và **NOT_EVALUATED**.

## 12. Bảo đảm tính đúng đắn của dependency graph

Selective build phụ thuộc vào độ chính xác của graph. Nếu graph thiếu một cạnh, pipeline có thể bỏ sót consumer. Nếu graph có cạnh thừa, pipeline chạy nhiều project hơn cần thiết nhưng thường vẫn an toàn.

Vì vậy, khi đánh đổi giữa false positive và false negative:

- False positive: build/test thêm project không bị ảnh hưởng, tốn thời gian.
- False negative: bỏ sót project bị ảnh hưởng, tạo false green và rủi ro phát hành.

False negative nguy hiểm hơn. Khi không chắc chắn, mở rộng phạm vi.

### 12.1. Graph cần được kiểm chứng

Nên có các kiểm tra:

- Mọi project có ID duy nhất và root path hợp lệ.
- Mọi dependency target tồn tại.
- Không có cycle ngoài trường hợp build system hỗ trợ rõ ràng.
- Mọi shared config có consumer mapping hoặc global rule.
- Generated-code inputs và outputs được mô tả.
- Project mới/xóa/rename được nhận diện.
- Graph được tạo từ đúng revision đang kiểm tra.
- Kết quả graph có thể tái lập từ cùng source và toolchain.

### 12.2. Tránh tin tuyệt đối vào graph do pull request thay đổi

Một pull request có thể sửa project manifest, script tính affected hoặc workflow. Nếu pipeline dùng logic mới từ chính pull request để quyết định bỏ qua các check bắt buộc, thay đổi có thể vô tình hoặc cố ý làm giảm phạm vi kiểm tra.

Với gate quan trọng:

- Giữ policy required checks trong cấu hình được bảo vệ.
- Validate thay đổi đối với project graph và affected script.
- Xem xét graph ở base và head khi dependency thay đổi.
- Không cho thay đổi untrusted tự tắt gate bắt buộc.
- Chạy full build hoặc yêu cầu review khi graph generator/policy thay đổi theo cách chưa được xác minh.

Selective build là tối ưu thực thi; nó không nên trở thành cách để mã thay đổi tự quyết định mức kiểm tra mà chính nó phải vượt qua.

## 13. Cache và artifact trong selective build

Selective build và caching bổ trợ nhau nhưng giải quyết hai vấn đề khác nhau:

- Affected analysis quyết định project/target nào cần chạy.
- Cache tái sử dụng kết quả hoặc dependency khi input tương ứng không đổi.

Cache key cần bao gồm những input có thể ảnh hưởng kết quả như source, lockfile, compiler/toolchain, build config và target. Cache key quá rộng làm giảm hit rate; key quá hẹp có thể trả kết quả cũ không hợp lệ.

Với remote cache:

- Chỉ tin kết quả từ nguồn/identity phù hợp.
- Không để pull request không tin cậy ghi cache dùng cho release có quyền cao.
- Tách namespace hoặc quyền read/write theo trust boundary.
- Gắn provenance hoặc metadata với artifact/cache result khi công cụ hỗ trợ.
- Khi graph hoặc cache key logic thay đổi, xác minh invalidation đúng.

Nếu nhiều project dùng cùng artifact hoặc generated output, cần xác định rõ owner và dependency. Không build lại một thư viện theo cách tạo artifact khác nhau cho từng consumer nếu có thể tạo một artifact xác định rồi tái sử dụng.

## 14. Khi nào nên chạy full build?

Full build là cơ chế fallback cần thiết, không phải thất bại của selective build.

Nên chạy full build khi:

- Không xác định được base/head revision đáng tin cậy.
- Git history thiếu và không thể fetch đủ.
- Có path chưa được phân loại.
- Root build logic, project graph generator hoặc affected algorithm thay đổi.
- Shared config có phạm vi tác động chưa rõ.
- Lockfile hoặc dependency resolution thay đổi nhưng không thể xác định consumer.
- Graph validation thất bại hoặc có dependency không giải quyết được.
- Có thay đổi cross-cutting như compiler, runtime, toolchain hoặc codegen.
- Đây là lịch nightly, release candidate hoặc đợt xác minh toàn repository theo policy.

Có thể dùng selective build cho pull request thông thường và chạy full build định kỳ hoặc trước release. Lịch full build giúp phát hiện những dependency ẩn mà graph hiện tại chưa mô tả.

### 14.1. Fallback phải có lý do

Khi full build được kích hoạt, báo cáo nên ghi lý do cụ thể: **UNKNOWN_PATH**, **GRAPH_INVALID**, **BASE_NOT_FOUND**, **ROOT_BUILD_CONFIG_CHANGED** hoặc **LOCKFILE_SCOPE_UNKNOWN**. Điều này giúp nhóm bổ sung rule để giảm fallback không cần thiết.

Không âm thầm biến lỗi tính affected thành danh sách rỗng. Nếu thuật toán lỗi và trả về zero projects, pipeline có thể báo xanh mà không chạy bất kỳ kiểm tra nào. Lỗi phân tích phạm vi phải làm job thất bại hoặc chuyển sang full build.

## 15. Đo hiệu quả và theo dõi false green

Một selective pipeline nhanh hơn chưa chắc tốt hơn nếu nó bỏ sót kiểm tra.

Nên theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Affected project count | Số project được chọn trên mỗi thay đổi |
| Full-build fallback rate | Tỷ lệ thay đổi phải chạy full build |
| Pipeline duration | Thời gian đầu-cuối |
| Required-check completion | Tỷ lệ gate bắt buộc hoàn tất đúng |
| Cache hit rate | Tỷ lệ kết quả/dependency được tái sử dụng |
| Graph validation failures | Số lần graph không hợp lệ |
| Unknown path rate | Tỷ lệ file chưa có ownership rule |
| Missed impact incidents | Sự cố phát hiện project bị bỏ sót sau merge/release |

Không có metric nào tự chứng minh selective build đúng. Cần kiểm tra bằng cách định kỳ chạy full build trên một phần thay đổi và so sánh kết quả với selective build. Nếu full build phát hiện lỗi mà selective build bỏ qua, đó là tín hiệu phải sửa graph hoặc policy.

### 15.1. Shadow validation

Có thể chạy affected analysis ở chế độ shadow:

- Pipeline vẫn dùng full build làm kết quả quyết định.
- Thu thập danh sách project mà selective algorithm dự kiến chọn.
- So sánh với phạm vi project được full build kiểm tra.
- Phân tích chênh lệch và sửa mapping/graph.
- Chỉ bật selective build sau khi có đủ bằng chứng và review.

Shadow mode đặc biệt hữu ích khi mới đưa monorepo vào selective CI hoặc thay đổi thuật toán affected.

## 16. Tình huống mẫu: thay đổi thư viện dùng chung

Giả sử developer chỉ sửa một hàm trong libs/auth-client. Repository có:

- order-domain phụ thuộc auth-client.
- order-api phụ thuộc order-domain.
- web-store phụ thuộc auth-client.
- admin-portal không phụ thuộc auth-client.

Quy trình:

1. Pipeline nhận base SHA và head SHA của pull request.
2. Git diff xác định file trong libs/auth-client đã thay đổi.
3. Path mapping chọn auth-client làm seed project.
4. Dependency graph được kiểm tra và xác nhận hợp lệ.
5. Reverse traversal tìm order-domain, order-api và web-store.
6. Pipeline tạo tập affected gồm auth-client, order-domain, order-api và web-store.
7. Build order theo dependency: auth-client trước order-domain, sau đó order-api; web-store có thể chạy song song sau auth-client.
8. Chạy lint/test/build cho các target tương ứng.
9. admin-portal được bỏ qua theo dependency graph đã xác minh.
10. Aggregate job chờ tất cả required checks và công bố kết quả.
11. Pipeline lưu changed path, graph revision, affected list và lý do bỏ qua admin-portal.

Nếu cùng pull request còn sửa root compiler config, policy global có thể mở rộng phạm vi sang tất cả project. Nếu graph không thể xác minh, pipeline chuyển sang full build.

## 17. Lộ trình thực hành

Có thể thực hành trên một monorepo mẫu theo các bước:

1. **Lập danh sách project:** ghi project ID, root path, type, owner và targets.
2. **Vẽ dependency graph:** khai báo build, test, codegen và contract dependencies.
3. **Tạo Git diff:** dùng base/head SHA phù hợp và kiểm tra add/modify/delete/rename.
4. **Map changed paths:** xác định project sở hữu file và nhóm global/shared/unknown.
5. **Tính reverse dependents:** thử thay đổi một shared library và xác nhận toàn bộ consumer được chọn.
6. **Kiểm tra dependency bắc cầu:** tạo chuỗi A phụ thuộc B, B phụ thuộc C; sửa C và xác nhận A được chọn.
7. **Xử lý graph change:** thêm/xóa dependency và so sánh ảnh hưởng từ graph base/head.
8. **Chọn targets:** xác định lint/test/build/contract test theo loại project và change type.
9. **Tạo execution plan:** lưu base/head, changed paths, seed, affected, target và fallback reason.
10. **Thử global input:** thay root lockfile hoặc build config và xác nhận phạm vi mở rộng đúng.
11. **Thử unknown path:** tạo file chưa có ownership rule và xác nhận full build được kích hoạt.
12. **Kiểm tra aggregate job:** bảo đảm skip hợp lệ được phân biệt với pass và mọi required check có kết quả.
13. **So sánh với full build:** chạy shadow validation và tìm chênh lệch.
14. **Đo hiệu quả:** so sánh pipeline duration, affected count và missed impact incidents.

### Tiêu chí hoàn thành

Người học có thể xem bài thực hành hoàn thành khi chứng minh được:

- Xác định đúng base/head revision cho pull request và push.
- Xử lý file mới, sửa, xóa và rename.
- Ánh xạ file sang project owner.
- Phân biệt direct dependency và transitive reverse dependency.
- Tính đầy đủ affected projects từ dependency graph.
- Xử lý root config, lockfile, schema, build logic và unknown paths.
- Tạo thứ tự build theo dependency và chạy song song khi an toàn.
- Tách project selection khỏi target selection.
- Không để path filter hoặc lỗi graph tạo false green.
- Có full-build fallback với lý do rõ ràng.
- Lưu được execution plan và bằng chứng affected analysis.
- So sánh selective build với full build để kiểm chứng độ bao phủ.

## Kết luận

Chọn phạm vi build trong monorepo đòi hỏi nhiều hơn việc tìm thư mục có file thay đổi. Pipeline cần xác định base/head revision chính xác, ánh xạ changed paths sang project owner, phát hiện global/shared inputs và tính toàn bộ reverse dependents trong dependency graph. Sau đó mới chọn target và sắp xếp build/test theo thứ tự phụ thuộc.

Selective build giúp giảm công việc không cần thiết khi graph đầy đủ và thuật toán được kiểm chứng. Khi graph, path mapping hoặc revision không đáng tin cậy, full build là fallback đúng đắn. Execution plan, aggregate required checks, shadow validation và theo dõi missed impact incidents giúp bảo đảm tối ưu thời gian không đánh đổi độ tin cậy của CI/CD.

