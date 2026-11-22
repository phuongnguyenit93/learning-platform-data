# Phân biệt monorepo, dự án nhiều mô-đun và build kết hợp

Khi một hệ thống Java lớn lên, mã nguồn thường được chia thành nhiều phần: ứng dụng, thư viện dùng chung, công cụ build, adapter tích hợp và các dịch vụ độc lập. Có nhiều cách tổ chức những phần này trong repository và trong Gradle. Ba thuật ngữ dễ bị dùng lẫn là **monorepo**, **multi-project build** và **composite build**.

Chúng mô tả những khía cạnh khác nhau:

- **Monorepo** nói về cách tổ chức mã nguồn trong hệ thống quản lý phiên bản: nhiều project hoặc thành phần cùng nằm trong một repository.
- **Multi-project build** nói về cấu trúc của một Gradle build: một root build quản lý nhiều Gradle project/subproject qua một settings file.
- **Composite build** nói về cách kết hợp nhiều Gradle build độc lập trong một lần làm việc: mỗi build giữ settings và ranh giới riêng, nhưng Gradle có thể phối hợp chúng, chẳng hạn thay dependency module bằng project source từ một included build.

Ba khái niệm này không loại trừ nhau. Một monorepo có thể chứa một multi-project build, nhiều Gradle build độc lập hoặc một composite build gồm nhiều build. Một multi-project build cũng có thể nằm trong repository chỉ chứa một ứng dụng. Composite build có thể kết hợp các build nằm cùng repository hoặc ở những repository khác nhau trên máy phát triển.

Muốn chọn cấu trúc phù hợp, cần tách biệt ba câu hỏi: mã nguồn được lưu ở đâu, Gradle build được chia thành những ranh giới nào, và các project phụ thuộc lẫn nhau ra sao.

## 1. Ba khái niệm trả lời ba câu hỏi khác nhau

| Khái niệm | Trả lời câu hỏi | Ranh giới chính | Cấu hình thường gặp |
|---|---|---|---|
| Monorepo | Các thành phần được lưu trong repository nào? | Repository/version control | Git repository, thư mục và quy ước ownership |
| Multi-project build | Một Gradle build gồm những project nào? | Gradle build root | `settings.gradle`, `include`, `project(...)` |
| Composite build | Những Gradle build độc lập nào được phối hợp? | Nhiều Gradle build root | `includeBuild(...)`, dependency substitution |

Có thể biểu diễn mối quan hệ như sau:

~~~mermaid
flowchart TD
    R["Git repository"] --> M["Monorepo: một repo chứa nhiều thành phần"]
    M --> B1["Gradle build A"]
    M --> B2["Gradle build B"]
    B1 --> P1["Project :app"]
    B1 --> P2["Project :domain"]
    B2 --> P3["Project :build-logic"]
    B1 -. "Composite build có thể include" .-> B2
~~~

Sơ đồ chỉ minh họa một cách tổ chức. Không có yêu cầu rằng một repository phải chứa đúng một Gradle build, hoặc một Gradle build phải chứa mọi thành phần của sản phẩm.

Một điểm cần nhớ nữa: **monorepo không đồng nghĩa với monolith**. Monorepo là lựa chọn lưu trữ mã nguồn. Monolith, modular monolith và microservices là những cách tổ chức kiến trúc hoặc triển khai phần mềm. Một monorepo hoàn toàn có thể chứa nhiều microservice được build và deploy độc lập.

## 2. Monorepo là mô hình tổ chức repository

Monorepo (monolithic repository) là cách lưu trữ nhiều project, thư viện, ứng dụng hoặc dịch vụ trong cùng một repository Git. Các thành phần có thể dùng chung lịch sử commit, công cụ phát triển, quy tắc review và một số cấu hình hạ tầng.

Ví dụ một repository Java:

~~~text
commerce-platform/
├── services/
│   ├── orders-service/
│   ├── payments-service/
│   └── inventory-service/
├── libraries/
│   ├── money-types/
│   ├── observability/
│   └── security-client/
├── tools/
│   └── data-migration/
├── build-logic/
├── docs/
└── README.md
~~~

Cấu trúc này chỉ thể hiện cách chia thư mục. Chưa thể kết luận repository có một Gradle build hay nhiều Gradle build. Mỗi thư mục service hoặc library có thể là subproject của một root build, hoặc là root của một Gradle build độc lập.

### 2.1. Ưu điểm của monorepo

Monorepo có thể đem lại một số lợi ích:

- **Thay đổi đồng bộ:** một commit có thể cập nhật API của library và các consumer cùng lúc.
- **Dễ tìm mã nguồn liên quan:** developer có thể tra cứu service, library và tài liệu trong cùng repository.
- **Chia sẻ quy ước:** nhóm có thể thống nhất formatter, static analysis, build logic và chính sách dependency.
- **Review thay đổi xuyên thành phần:** pull request có thể thể hiện đầy đủ tác động của một thay đổi tới nhiều project.
- **Quản lý phiên bản phối hợp:** khi cần, nhiều thành phần có thể được nâng version hoặc phát hành theo cùng một mốc.
- **Tái sử dụng tooling:** CI, scripts, convention plugins và quy trình kiểm tra có thể được tổ chức chung.

Những lợi ích này không tự xuất hiện chỉ vì mọi mã nguồn nằm chung một repository. Chúng cần quy ước ownership, cấu trúc thư mục, build boundaries và CI phù hợp.

### 2.2. Chi phí và thách thức của monorepo

Repository lớn cũng tạo ra một số vấn đề:

- Checkout, indexing hoặc thao tác Git có thể nặng khi repository chứa nhiều file và lịch sử.
- Build toàn bộ repository mỗi lần thay đổi có thể tốn thời gian.
- Một thay đổi ở library dùng chung có thể ảnh hưởng nhiều consumer.
- Quyền truy cập và ownership theo thư mục cần được thiết kế rõ.
- CI cần biết project nào bị ảnh hưởng để tránh chạy mọi pipeline không cần thiết.
- Các nhóm có thể bị phụ thuộc vào một lịch release chung nếu không thiết kế versioning phù hợp.
- Quy tắc build chung có thể trở nên phức tạp khi các thành phần có yêu cầu khác nhau.

Các vấn đề trên được giải quyết bằng cách tổ chức build, dependency và CI hợp lý. Chia thành nhiều repository không tự động làm chúng biến mất; nó chỉ chuyển một phần chi phí sang quản lý phiên bản, publication và tích hợp giữa các repository.

### 2.3. Monorepo không quy định Gradle build topology

Cùng một cấu trúc monorepo có thể triển khai theo nhiều cách.

**Một multi-project build:**

~~~text
commerce-platform/
├── settings.gradle
├── build.gradle
├── services/
│   ├── orders-service/
│   └── payments-service/
└── libraries/
    ├── money-types/
    └── observability/
~~~

**Nhiều Gradle build độc lập:**

~~~text
commerce-platform/
├── services/
│   ├── orders-service/
│   │   ├── settings.gradle
│   │   └── build.gradle
│   └── payments-service/
│       ├── settings.gradle
│       └── build.gradle
└── libraries/
    ├── money-types/
    │   ├── settings.gradle
    │   └── build.gradle
    └── observability/
        ├── settings.gradle
        └── build.gradle
~~~

**Nhiều build được kết hợp thành composite:**

~~~text
commerce-platform/
├── settings.gradle
├── services/
│   ├── orders-service/
│   └── payments-service/
├── libraries/
│   └── money-types/
└── build-logic/
~~~

Ở ví dụ cuối, settings của một build có thể dùng `includeBuild` để phối hợp build khác. Monorepo chỉ mô tả repository; cấu hình Gradle quyết định build topology.

## 3. Multi-project build: một Gradle build, nhiều project

Multi-project build là một Gradle build có root project và một hoặc nhiều subproject. Cấu trúc các project được khai báo trong settings file của root build.

Ví dụ:

~~~text
commerce-platform/
├── settings.gradle
├── build.gradle
├── orders-app/
│   └── build.gradle
├── orders-domain/
│   └── build.gradle
└── reporting/
    └── build.gradle
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'commerce-platform'

include 'orders-app'
include 'orders-domain'
include 'reporting'
~~~

Gradle nhận diện ba subproject với project path:

- `:orders-app`
- `:orders-domain`
- `:reporting`

Mỗi project có thể áp dụng plugin, khai báo dependency, tạo source set, task và artifact riêng. Root project có thể quản lý cấu hình chung hoặc điều phối task ở cấp toàn build.

### 3.1. Dependency giữa các subproject

Trong multi-project build, một project có thể khai báo project dependency trực tiếp:

~~~groovy
// orders-app/build.gradle
plugins {
    id 'application'
}

dependencies {
    implementation project(':orders-domain')
}
~~~

Điều đó cho Gradle biết output/component của `orders-domain` là dependency của `orders-app`. Gradle có thể thiết lập quan hệ task cần thiết để build producer trước khi consumer sử dụng output.

Ví dụ graph:

~~~text
:orders-app
    |
    +---- project dependency ----> :orders-domain
                                      |
                                      +---- external dependency ----> jackson
~~~

Project dependency được khai báo bằng project path trong cùng Gradle build. Đây là cơ chế phù hợp khi các module thuộc cùng một build boundary và cần được phát triển, kiểm thử hoặc build phối hợp.

### 3.2. Cấu hình chung ở root project

Root build có thể áp dụng cấu hình dùng chung. Ví dụ:

~~~groovy
allprojects {
    group = 'com.example'
    version = '1.0.0'
}

subprojects {
    repositories {
        mavenCentral()
    }
}
~~~

Hoặc khai báo plugin ở root nhưng không áp dụng ngay:

~~~groovy
plugins {
    id 'java' apply false
    id 'application' apply false
}
~~~

Sau đó từng subproject áp dụng plugin cần thiết. Với dự án lớn, convention plugins thường giúp tránh lặp lại các block cấu hình dài trong từng project.

Cần sử dụng cấu hình root có chủ đích. Những block như `allprojects` hoặc `subprojects` tác động rộng, có thể khiến project mới nhận cấu hình ngoài dự kiến. Một build logic rõ ràng giúp developer biết convention nào áp dụng cho project nào.

### 3.3. Một invocation có thể điều phối nhiều project

Từ root directory, có thể chạy task của một project:

~~~bash
./gradlew :orders-app:build
~~~

Hoặc chạy task cùng tên trên các project phù hợp:

~~~bash
./gradlew build
~~~

Gradle lập task graph từ các task được yêu cầu và dependency giữa chúng. Chạy `:orders-app:build` có thể kéo theo task cần thiết của `orders-domain` vì project dependency. Chạy `build` ở root có thể thực thi các task build được nối vào lifecycle task của các subproject, tùy cấu hình build.

Một build invocation không nhất thiết thực thi mọi task của mọi project. Gradle chỉ chạy những task có trong task graph được yêu cầu và các task phụ thuộc.

### 3.4. Ưu điểm của multi-project build

Multi-project build phù hợp khi các thành phần có quan hệ phát triển chặt:

- Project có thể tham chiếu nhau bằng project dependency.
- Một thay đổi API và consumer có thể được compile/test trong cùng invocation.
- Root build có thể chia sẻ toolchain, repository và convention.
- Task graph thể hiện quan hệ build giữa các project.
- Gradle có thể thực hiện các task độc lập song song khi điều kiện cho phép.
- Developer có một entry point rõ ràng để build hoặc test hệ thống.

### 3.5. Giới hạn của một build boundary lớn

Khi tất cả project nằm trong một build, settings và build logic trở thành trung tâm điều phối. Với repository rất lớn, điều này có thể dẫn tới:

- Settings và configuration logic phức tạp.
- Thời gian configuration tăng khi có nhiều project hoặc plugin.
- Các nhóm khó duy trì ranh giới build độc lập.
- Thay đổi cấu hình chung ảnh hưởng rộng.
- Release lifecycle của các project có thể bị gắn với nhau nếu quy trình không hỗ trợ versioning riêng.

Gradle có các cơ chế tối ưu như configuration cache và project isolation theo mức hỗ trợ của phiên bản/plugin, nhưng không nên xem chúng là lý do để gom mọi project vào một build duy nhất. Cấu trúc nên phản ánh ranh giới ownership, dependency và release thực tế.

## 4. Composite build: kết hợp nhiều Gradle build độc lập

Composite build là một tập hợp các Gradle builds độc lập được Gradle phối hợp trong một lần làm việc. Mỗi included build giữ settings, project structure và build logic của chính nó. Build chính khai báo các build khác bằng `includeBuild`.

Ví dụ:

~~~text
workspace/
├── orders-app/
│   ├── settings.gradle
│   └── build.gradle
└── money-types/
    ├── settings.gradle
    └── build.gradle
~~~

`orders-app` và `money-types` là hai Gradle build riêng. Mỗi build có settings file riêng. Khi phát triển local, build app có thể include build library:

~~~groovy
// orders-app/settings.gradle
rootProject.name = 'orders-app'

includeBuild('../money-types')
~~~

Nếu dependency trong app có tọa độ khớp với component được cung cấp bởi included build, Gradle có thể tự động thay external module dependency bằng project tương ứng từ included build. Đây là dependency substitution trong composite build.

Ví dụ build app khai báo:

~~~groovy
// orders-app/build.gradle
repositories {
    mavenCentral()
}

dependencies {
    implementation 'com.example:money-types:1.2.0'
}
~~~

Included build có project cung cấp module tương ứng:

~~~groovy
// money-types/build.gradle
group = 'com.example'
version = '1.2.0'
~~~

Nếu coordinates của project trong included build khớp với module dependency, Gradle có thể dùng source project local thay cho việc tải binary publication từ repository. Nhờ vậy, developer sửa library và kiểm tra consumer ngay trong workspace mà không phải publish snapshot cho mỗi lần thay đổi.

Cần bảo đảm group, module name và version/coordinates phù hợp với dependency đang được thay thế. Nếu không khớp, cần cấu hình substitution rõ ràng hoặc điều chỉnh publication identity.

### 4.1. Included build vẫn giữ ranh giới riêng

Composite build không biến các build thành một multi-project build lớn. Mỗi included build có:

- Settings file riêng.
- Root project riêng.
- Project paths riêng trong build của nó.
- Build logic và plugin management riêng.
- Dependency repositories và versioning riêng theo cấu hình.
- Khả năng build độc lập khi không được include.

Build chính phối hợp các build qua composite relationship. Đây là ranh giới quan trọng: included build không trở thành subproject chỉ vì được khai báo bằng `includeBuild`.

### 4.2. Dependency substitution trong composite build

Dependency substitution cho phép Gradle thay một module dependency bằng một component khác. Khi composite build tự nhận diện được coordinates, substitution có thể diễn ra tự động.

Nếu coordinates không trùng hoặc project không tự nhận diện đúng module, có thể cấu hình tường minh:

~~~groovy
// orders-app/settings.gradle
includeBuild('../money-types') {
    dependencySubstitution {
        substitute module('com.example:money-types')
            .using project(':')
    }
}
~~~

Trong ví dụ, dependency có tọa độ `com.example:money-types` được thay bằng root project của included build. Với included build có nhiều project, có thể trỏ tới project path tương ứng bên trong build đó.

Hãy kiểm tra chính xác module coordinates và project path. Substitution là quy tắc resolution có ảnh hưởng tới dependency graph; nếu khai báo nhầm, consumer có thể nhận component không đúng.

### 4.3. Composite build không yêu cầu publish trước để phát triển local

Một lợi ích quan trọng là có thể phát triển nhiều build độc lập như thể chúng đang phối hợp trong một workspace:

~~~text
workspace/
├── checkout-service/
├── pricing-library/
└── tax-library/
~~~

Build `checkout-service` có thể include hai build library. Khi dependency coordinates khớp, Gradle dùng project source từ các included builds. Developer có thể thay đổi API library và build consumer để phát hiện lỗi tích hợp sớm.

Khi CI hoặc release cần kiểm tra publication thật, vẫn cần kiểm tra riêng quy trình publish/consume từ repository. Composite substitution chứng minh tích hợp source trong workspace; nó không tự chứng minh publication metadata trên artifact repository đã đúng.

### 4.4. Chạy build độc lập và build kết hợp

Một included build vẫn có thể được chạy độc lập từ thư mục của chính nó:

~~~bash
cd money-types
./gradlew build
~~~

Khi cần phối hợp với consumer, chạy Gradle từ build chính có include build:

~~~bash
cd ../orders-app
./gradlew build
~~~

Gradle có thể resolve dependency của app qua included build và thực hiện task cần thiết ở build đó. Cách chạy cụ thể phụ thuộc task và dependency được yêu cầu.

Điểm quan trọng là build library vẫn có thể build/test độc lập. Composite build chỉ thêm khả năng phối hợp khi cần tích hợp.

## 5. Build logic cũng có thể là một included build

Một trường hợp thường gặp là tách convention plugins hoặc build logic ra thành một build riêng. Ví dụ:

~~~text
commerce-platform/
├── settings.gradle
├── build.gradle
├── services/
│   ├── orders/
│   └── payments/
└── build-logic/
    ├── settings.gradle
    └── convention/
        └── build.gradle
~~~

Build chính có thể include build logic trong plugin management:

~~~groovy
// settings.gradle
pluginManagement {
    includeBuild('build-logic')
}

rootProject.name = 'commerce-platform'
include 'services:orders'
include 'services:payments'
~~~

Build logic cung cấp convention plugin để các project áp dụng:

~~~groovy
plugins {
    id 'com.example.java-library-conventions'
}
~~~

Cách này giúp đóng gói build logic thành một Gradle build có cấu trúc riêng, dễ kiểm thử và tái sử dụng. Nó cũng tránh để root build script chứa quá nhiều cấu hình lặp.

`buildSrc` là một cơ chế khác để chứa build logic đặc biệt gắn với build hiện tại. Khi cần một build logic có ranh giới và khả năng tái sử dụng rõ ràng, included build như `build-logic` thường là lựa chọn linh hoạt hơn. Hai cơ chế có cách tích hợp khác nhau; không nên coi `buildSrc` và included build là cùng một khái niệm.

## 6. So sánh multi-project build và composite build

Hai cấu trúc đều cho phép phối hợp nhiều project hoặc thành phần, nhưng build boundary khác nhau.

| Tiêu chí | Multi-project build | Composite build |
|---|---|---|
| Số Gradle build | Một build | Nhiều build độc lập |
| Settings | Một settings file cho build | Mỗi included build có settings riêng |
| Project relationship | Subproject trong cùng build | Build chính include build khác |
| Dependency nội bộ | `project(':module')` | Thường dùng module coordinates và substitution |
| Build độc lập | Subproject không có settings/root build riêng theo cấu trúc thông thường | Included build có thể build độc lập |
| Build logic | Có thể chia sẻ từ root/convention plugin | Mỗi build giữ logic riêng; có thể include build logic dùng chung |
| Versioning | Có thể đồng bộ hoặc độc lập theo cấu hình | Các build có thể quản lý version độc lập |
| Use case điển hình | Các module thuộc cùng một sản phẩm và release/build lifecycle | Phối hợp các build độc lập hoặc phát triển library source cùng consumer |
| Ranh giới ownership | Thường nằm trong một build boundary | Có thể phản ánh team/repository/build boundary riêng |

### 6.1. Ví dụ multi-project

~~~groovy
// settings.gradle
rootProject.name = 'commerce-platform'
include 'orders-app', 'orders-domain'
~~~

~~~groovy
// orders-app/build.gradle
dependencies {
    implementation project(':orders-domain')
}
~~~

Hai project cùng một build. Quan hệ dependency dùng project path.

### 6.2. Ví dụ composite

~~~groovy
// orders-app/settings.gradle
rootProject.name = 'orders-app'
includeBuild('../orders-domain')
~~~

~~~groovy
// orders-app/build.gradle
dependencies {
    implementation 'com.example:orders-domain:1.0.0'
}
~~~

Build app và build domain độc lập. Khi coordinates khớp, composite build có thể thay module dependency bằng project source của included build.

Hai ví dụ có thể tạo ra trải nghiệm phát triển gần giống nhau, nhưng cách quản lý settings, project identity và build lifecycle khác nhau.

## 7. Monorepo, multi-project và composite có thể kết hợp ra sao?

Không nên xem ba khái niệm như ba lựa chọn loại trừ. Có nhiều tổ hợp hợp lệ.

| Repository | Gradle topology | Ví dụ |
|---|---|---|
| Một monorepo | Một multi-project build | Một root build quản lý app, library và module |
| Một monorepo | Nhiều build độc lập | Mỗi service có settings và pipeline riêng |
| Một monorepo | Composite build | Root/consumer build include library hoặc build-logic |
| Nhiều repository | Mỗi repo một build độc lập | Các service publish và consume library qua repository |
| Nhiều repository | Composite build local | Developer checkout nhiều repo và include build library source khi phát triển |
| Một repository | Một project đơn giản | Không cần multi-project hoặc composite chỉ vì repo có nhiều thư mục |

### 7.1. Một monorepo với nhiều build độc lập

Ví dụ:

~~~text
platform/
├── orders-service/
│   ├── settings.gradle
│   └── build.gradle
├── payments-service/
│   ├── settings.gradle
│   └── build.gradle
├── inventory-service/
│   ├── settings.gradle
│   └── build.gradle
└── shared-libraries/
    ├── money-types/
    └── api-contracts/
~~~

Mỗi service có thể được build/test/deploy độc lập. Shared libraries được publish lên repository nội bộ. Khi developer muốn sửa library và consumer cùng lúc, có thể checkout library và dùng composite build trong workspace local.

Cách này giữ ranh giới release của service nhưng vẫn hỗ trợ phát triển tích hợp.

### 7.2. Một multi-project build bên trong monorepo

Ví dụ:

~~~text
platform/
├── settings.gradle
├── build.gradle
├── services/
│   ├── orders/
│   └── payments/
└── libraries/
    ├── money-types/
    └── api-contracts/
~~~

Root settings include các project. Các service dùng project dependency tới library. CI có thể build các phần liên quan theo task graph và các quy tắc path filtering.

Cách này phù hợp khi nhóm muốn một build graph thống nhất và thay đổi API/consumer thường được kiểm tra đồng bộ.

### 7.3. Một composite build gồm các build cùng repository

Ví dụ:

~~~text
platform/
├── apps/
│   └── orders-app/
├── libraries/
│   └── money-types/
└── build-logic/
~~~

`orders-app` có settings riêng và include `money-types` cùng `build-logic`. Cả ba cùng nằm trong một Git repository nhưng vẫn là Gradle builds riêng. Điều này hữu ích khi muốn mỗi phần giữ cấu hình và vòng đời build độc lập.

## 8. Chọn cấu trúc theo ranh giới phụ thuộc và phát hành

Không có một topology tốt nhất cho mọi dự án. Cần xem xét những yếu tố thực tế.

### 8.1. Mức độ gắn kết của các project

Nếu các module luôn thay đổi cùng nhau, thường cần compile/test phối hợp và thuộc cùng một sản phẩm, multi-project build có thể đơn giản hơn.

Nếu các thư viện hoặc service có thể phát triển, kiểm thử và phát hành độc lập, các build riêng có thể phản ánh ranh giới đó tốt hơn. Composite build giúp phối hợp source khi cần mà không buộc các build phải nhập làm subproject.

### 8.2. Quyền sở hữu của team

Nếu nhiều team cùng làm trong một repository, cần xác định:

- Ai chịu trách nhiệm API của từng library?
- Ai duyệt thay đổi ở mỗi service?
- Convention build nào là bắt buộc?
- Thành phần nào được phép phát hành độc lập?
- Khi thay đổi library, consumer nào phải được kiểm tra?

Multi-project build không tự tạo ra ownership rõ ràng. Composite build cũng không tự bảo đảm độc lập team. Các ranh giới này cần được mô tả qua CODEOWNERS, quy trình review, API contract và release policy.

### 8.3. Versioning và release cadence

Các project trong multi-project build có thể dùng chung version hoặc version riêng. Gradle không bắt buộc mọi subproject phải có cùng version. Tuy nhiên, nếu nhiều project được phát hành theo một release train, dùng chung version có thể đơn giản hóa việc theo dõi tương thích.

Với các build độc lập, mỗi build thường có thể phát hành version riêng. Consumer khai báo module coordinates tương ứng. Composite build giúp thay dependency đã publish bằng source local trong quá trình phát triển.

Cần phân biệt:

- **Build version:** version được gán cho project/artifact.
- **Repository revision:** commit Git chứa source.
- **Release version:** version được công bố cho consumer.
- **Included build substitution:** source project local được dùng thay module dependency trong composite.

Các khái niệm này liên quan nhưng không nhất thiết trùng nhau.

### 8.4. Tác động tới CI

Với monorepo, CI thường cần xác định project nào bị ảnh hưởng bởi thay đổi. Có thể dùng:

- Phân tích đường dẫn file thay đổi.
- Dependency graph giữa project.
- Task graph Gradle.
- Convention để chọn test suite phù hợp.
- Remote build cache và configuration cache khi tương thích.

Với multi-project build, Gradle hiểu project dependency nội bộ và có thể lập task graph theo quan hệ đó. Nhưng pipeline vẫn cần quyết định có chạy lifecycle task ở root hay chỉ task của project liên quan.

Với nhiều build độc lập hoặc composite build, CI có thể chạy từng build theo pipeline riêng, hoặc tạo một integration job include các build cần thiết. Điều này cho phép giữ pipeline release độc lập nhưng vẫn có bước kiểm thử tương tác.

### 8.5. Thời gian configuration và quy mô build

Một build có rất nhiều project/plugin có thể tốn thời gian ở giai đoạn configuration. Chia build thành các build độc lập có thể giúp thu hẹp phạm vi configuration và ownership, nhưng cũng tăng số lượng settings, plugin management, repository và pipeline cần quản lý.

Không nên tách build chỉ dựa trên số lượng thư mục. Hãy đo thời gian configuration/execution, xem quan hệ dependency, tần suất thay đổi chung và nhu cầu release trước khi quyết định.

## 9. Dependency giữa các ranh giới build

Trong multi-project build, dependency nội bộ thường được khai báo bằng project dependency:

~~~groovy
dependencies {
    implementation project(':shared-library')
}
~~~

Trong composite build, consumer thường khai báo module dependency theo tọa độ:

~~~groovy
dependencies {
    implementation 'com.example:shared-library:2.1.0'
}
~~~

Sau đó settings include build cung cấp source project local:

~~~groovy
includeBuild('../shared-library')
~~~

Khi module coordinates được nhận diện và substitution áp dụng, Gradle dùng project từ included build thay cho module external.

### 9.1. Vì sao composite build thường dùng coordinates?

Mỗi included build giữ project identity riêng. Build chính không tham chiếu project của build khác bằng project path như cách dùng giữa subproject cùng build. Thay vào đó, consumer khai báo dependency theo module identity, rồi composite build quyết định module đó được cung cấp bởi included build nào.

Điều này giúp consumer vẫn có thể dùng cùng dependency declaration trong hai tình huống:

- Khi phát triển local có included build: Gradle có thể dùng source project.
- Khi build độc lập/CI không include source build: Gradle resolve module từ repository.

Nhờ vậy, build script consumer không nhất thiết phải thay đổi giữa local development và CI. Settings của workspace quyết định có include source build hay không.

### 9.2. Tránh nhiều included builds cùng cung cấp một module

Nếu nhiều included builds cùng cung cấp cùng coordinates, Gradle có thể gặp xung đột substitution hoặc lựa chọn không rõ ràng. Cần xác định một nguồn source provider cho mỗi module coordinates trong composite.

Đừng dùng composite build để âm thầm thay một dependency bằng project khác có API hoặc version identity không tương thích. Substitution nên phản ánh đúng module mà consumer mong đợi.

## 10. Convention plugins và cấu hình dùng chung

Khi có nhiều build độc lập, một thách thức là tránh copy-paste cấu hình plugin, compiler options, test setup và static analysis.

Có thể tách convention plugins thành một included build:

~~~text
workspace/
├── settings.gradle
├── orders-service/
├── payments-service/
└── build-logic/
    ├── settings.gradle
    └── src/main/groovy/
        └── com.example.java-library-conventions.gradle
~~~

Trong settings của build consumer:

~~~groovy
pluginManagement {
    includeBuild('../build-logic')
}
~~~

Sau đó áp dụng plugin:

~~~groovy
plugins {
    id 'com.example.java-library-conventions'
}
~~~

Convention plugin có thể cấu hình Java toolchain, compiler warnings, test framework, publication defaults và các quy tắc build chung. Mỗi build vẫn giữ settings và project structure riêng nhưng dùng cùng convention.

Một convention plugin tốt nên cung cấp chính sách ổn định và cho phép project khai báo phần khác biệt cần thiết. Tránh tạo plugin tổng quát đến mức mọi project đều phải đi vòng qua nhiều option khó hiểu.

## 11. Kiểm thử và phát triển khi dùng composite build

Composite build đặc biệt hữu ích khi một consumer cần thử thay đổi source của dependency mà không phát hành mỗi lần.

Ví dụ workspace:

~~~text
workspace/
├── checkout-service/
└── pricing-library/
~~~

Trong build app:

~~~groovy
// checkout-service/settings.gradle
includeBuild('../pricing-library')
~~~

Consumer khai báo module coordinates:

~~~groovy
dependencies {
    implementation 'com.example:pricing-library:3.0.0'
}
~~~

Developer có thể sửa code trong `pricing-library` rồi chạy test của `checkout-service`. Khi dependency substitution hoạt động, Gradle dùng source project local. Điều này giúp kiểm tra API integration trước khi publish library.

### 11.1. Kiểm tra cả hai chế độ

Nên kiểm tra hai trường hợp:

1. **Composite mode:** consumer include library source và resolve qua substitution.
2. **Published mode:** consumer không include build, resolve dependency từ repository release/snapshot thực tế.

Composite mode kiểm tra khả năng phối hợp source project. Published mode kiểm tra POM/Gradle metadata, artifact, version và repository. Chỉ kiểm tra composite mode có thể bỏ sót lỗi publication như thiếu dependency metadata hoặc artifact classifier.

### 11.2. Locking và verification

Dependency locking và dependency verification vẫn có vai trò trong build độc lập hoặc composite. Tuy nhiên, khi source module được thay bằng project dependency trong included build, phần được resolve không còn giống một binary module tải từ repository. Cần hiểu lock state và verification policy của từng build, đặc biệt khi CI thay đổi giữa composite mode và published mode.

## 12. Những lỗi thường gặp khi chọn hoặc cấu hình topology

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `Project with path ... could not be found` | Dùng project path không thuộc cùng multi-project build hoặc chưa include subproject | Kiểm tra settings và project path; nếu khác build, cân nhắc module dependency/composite |
| Included build không thay dependency external | Coordinates của included project không khớp module dependency hoặc substitution chưa cấu hình | Kiểm tra group/name/version và substitution rule |
| Consumer vẫn tải binary cũ | Included build chưa được include, module identity không khớp hoặc dependency khác đang được resolve | Xem dependencyInsight và composite settings |
| Nhiều project dùng chung cấu hình khó kiểm soát | Root script có quá nhiều cấu hình áp dụng rộng | Tách convention plugins và giới hạn phạm vi áp dụng |
| CI build quá nhiều project | Pipeline luôn chạy root lifecycle task hoặc không phân tích project bị ảnh hưởng | Dùng dependency graph và changed-path analysis |
| Local build pass nhưng published consumer fail | Chỉ kiểm tra source substitution, chưa kiểm tra publication thật | Chạy integration job consume từ repository |
| Nhiều included builds cung cấp cùng module | Coordinates trùng hoặc substitution mơ hồ | Chỉ định một provider hoặc sửa identity |
| Version library không rõ ràng | Dùng chung version hoặc release cadence không được quy định | Xác định versioning policy cho từng component |
| Build logic bị copy giữa nhiều repo | Chưa có convention plugin hoặc build-logic build dùng chung | Tạo và version hóa convention plugin phù hợp |
| Monorepo bị nhầm là một ứng dụng duy nhất | Đồng nhất repository boundary với architecture boundary | Tách khái niệm repo, build và deployment architecture |

## 13. Quy trình quyết định cấu trúc

Có thể dùng trình tự sau khi thiết kế repository và Gradle builds.

### Bước 1: Xác định ranh giới repository

Hỏi các thành phần có cần chia sẻ lịch sử Git, review, ownership và quy trình phát hành không. Nếu nhiều team cần thay đổi xuyên thành phần thường xuyên, monorepo có thể hữu ích. Nếu quyền sở hữu và release độc lập rõ rệt, nhiều repository có thể phù hợp hơn.

### Bước 2: Xác định ranh giới Gradle build

Hỏi project nào cần cùng một settings, plugin management và build lifecycle. Nếu các module thường được compile/test cùng nhau và dùng project dependency trực tiếp, multi-project build có thể phù hợp.

Nếu các thành phần có thể build và phát hành độc lập, có settings và build logic riêng, hãy cân nhắc nhiều Gradle builds.

### Bước 3: Xác định nhu cầu phối hợp source

Nếu các build độc lập nhưng developer thường sửa library và consumer cùng lúc, composite build có thể cung cấp local source substitution. Nếu không cần phát triển đồng thời, consumer có thể chỉ dùng publication từ repository.

### Bước 4: Thiết kế dependency identity

Với project dependency trong cùng build, dùng project path. Với dependency qua build boundary, dùng module coordinates và bảo đảm included build cung cấp đúng identity nếu muốn substitution.

### Bước 5: Thiết kế convention và CI

Quyết định convention plugin dùng chung, build cache, configuration cache, test scope, changed-path filtering, integration build và release workflow.

### Bước 6: Xác nhận hai chế độ tiêu thụ

Nếu dùng composite, kiểm tra cả source substitution và published artifact. Nếu dùng multi-project, kiểm tra task graph và các consumer project. Nếu dùng nhiều build độc lập, kiểm tra version/repository contract giữa chúng.

## 14. Ví dụ tổng hợp: monorepo chứa nhiều build và một composite workspace

Giả sử tổ chức có một monorepo:

~~~text
commerce/
├── services/
│   ├── orders/
│   │   ├── settings.gradle
│   │   └── build.gradle
│   └── payments/
│       ├── settings.gradle
│       └── build.gradle
├── libraries/
│   ├── money-types/
│   │   ├── settings.gradle
│   │   └── build.gradle
│   └── api-contracts/
│       ├── settings.gradle
│       └── build.gradle
└── build-logic/
    ├── settings.gradle
    └── build.gradle
~~~

Mỗi service và library là một Gradle build độc lập. Mỗi build có thể chạy riêng trong CI và phát hành version riêng. Khi phát triển orders cùng money-types, settings của orders có thể include library và build logic:

~~~groovy
// services/orders/settings.gradle
pluginManagement {
    includeBuild('../../build-logic')
}

rootProject.name = 'orders'

includeBuild('../../libraries/money-types')
includeBuild('../../libraries/api-contracts')
~~~

Build script của orders vẫn khai báo dependency theo coordinates:

~~~groovy
dependencies {
    implementation 'com.example:money-types:2.0.0'
    implementation 'com.example:api-contracts:1.5.0'
}
~~~

Nếu included build cung cấp đúng module identity, Gradle có thể thay dependency external bằng source project local. Khi chạy CI release của orders mà không include các library builds, dependency được resolve từ repository nội bộ theo version đã khai báo.

Mô hình này có cả ba khái niệm:

- Monorepo: tất cả thành phần được lưu trong Git repository commerce.
- Nhiều Gradle builds: service và library giữ settings/build boundary riêng.
- Composite build: orders phối hợp với library và build logic khi cần phát triển/tích hợp.

Nếu thay bằng một multi-project build, root settings sẽ include các project orders, payments, money-types và api-contracts trong cùng một Gradle build; dependency nội bộ có thể dùng project path. Đó là một topology khác, dù vẫn ở cùng monorepo.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Monorepo nghĩa là chỉ có một Gradle build | Một repo có thể chứa nhiều Gradle builds |
| Monorepo nghĩa là monolith | Repository layout không quyết định kiến trúc triển khai |
| Nhiều thư mục nghĩa là multi-project build | Subproject phải thuộc một Gradle build và được khai báo trong settings |
| `include()` và `includeBuild()` giống nhau | Một bên thêm subproject vào build; bên kia include một Gradle build độc lập |
| Composite build biến included build thành subproject | Included build giữ settings và project identity riêng |
| Có thể dùng `project(':x')` để tham chiếu project của build khác | Project dependency path chỉ có ý nghĩa trong build tương ứng; qua build boundary thường dùng module coordinates/substitution |
| Composite build luôn thay mọi dependency external | Chỉ module được nhận diện hoặc cấu hình substitution phù hợp mới được thay |
| Composite build thay thế publication | Nó hỗ trợ source development; vẫn cần kiểm tra published artifact/metadata |
| Multi-project build bắt buộc dùng chung một version | Version của từng project có thể được cấu hình độc lập |
| Mỗi service phải là một repository | Có thể có nhiều service độc lập trong monorepo |
| Nhiều repository không thể phát triển cùng lúc | Composite build có thể include các build local từ nhiều checkout |
| Convention plugin là một project dependency thông thường | Convention plugin là build logic được cung cấp qua plugin mechanism |
| Tách build luôn làm build nhanh hơn | Cần cân bằng chi phí configuration, orchestration, dependency và CI |

## 16. Checklist chọn mô hình phù hợp

Trước khi quyết định cấu trúc, hãy trả lời:

- [ ] Repository boundary có phản ánh ownership và quy trình review không?
- [ ] Có cần một commit thay đổi nhiều thành phần cùng lúc không?
- [ ] Những project nào thường xuyên compile/test cùng nhau?
- [ ] Chúng có cần dùng chung settings và plugin management không?
- [ ] Dependency giữa các module nên là project path hay module coordinates?
- [ ] Thành phần nào cần build và release độc lập?
- [ ] Developer có thường sửa library source cùng consumer không?
- [ ] Composite substitution có giúp giảm vòng lặp publish snapshot không?
- [ ] Publication từ repository có được kiểm tra riêng không?
- [ ] Convention plugins có thể chia sẻ build logic mà không tạo phụ thuộc quá rộng không?
- [ ] CI có thể chỉ chạy project/build bị ảnh hưởng không?
- [ ] Versioning policy và release cadence đã rõ chưa?
- [ ] Có cần integration build phối hợp nhiều service/library không?

## Kết luận

Monorepo, multi-project build và composite build mô tả ba lớp khác nhau. Monorepo quyết định nhiều thành phần được lưu trong cùng repository. Multi-project build gom nhiều Gradle project dưới một Gradle build root và thường dùng project dependency để nối chúng. Composite build phối hợp nhiều Gradle builds độc lập, giữ settings và project identity riêng, đồng thời có thể thay module dependency bằng source project local thông qua dependency substitution.

Các mô hình có thể kết hợp. Một monorepo có thể chứa một multi-project build, nhiều build độc lập hoặc một composite workspace. Lựa chọn nên dựa trên ranh giới ownership, mức độ thay đổi cùng nhau, dependency contract, release cadence và nhu cầu CI. Khi cần phát triển đồng thời các build độc lập, composite build tạo cầu nối hữu ích; khi các module thuộc cùng một build lifecycle, multi-project build thường đơn giản hơn.
