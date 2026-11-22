# Kiểm tra cấu trúc bằng sơ đồ phụ thuộc và quy tắc kiến trúc

Một ứng dụng có thể được chia thành các package `model`, `view` và `controller`, nhưng chỉ nhìn tên thư mục chưa đủ để biết các trách nhiệm MVC đã được phân tách đúng hay chưa. Controller vẫn có thể truy cập trực tiếp cơ sở dữ liệu, Model vẫn có thể phụ thuộc vào HTTP, hoặc các package có thể gọi lẫn nhau tạo thành một mạng phụ thuộc khó thay đổi.

Để đánh giá cấu trúc, nhóm phát triển cần nhìn được **ai phụ thuộc vào ai** và có những quy tắc nào cần được giữ ổn định. Sơ đồ phụ thuộc giúp quan sát các mối liên hệ; quy tắc kiến trúc giúp chuyển ý định thiết kế thành điều kiện có thể kiểm tra tự động. Kết hợp hai cách này giúp phát hiện sớm liên kết sai chiều, chu trình phụ thuộc, vi phạm phân lớp và những thay đổi làm cấu trúc ứng dụng lệch khỏi thiết kế.

Trong ứng dụng web theo mô hình **Model–View–Controller (MVC)**, việc kiểm tra cấu trúc cần xem xét cả các lớp Java, package, module, framework web, tầng nghiệp vụ và hạ tầng lưu trữ. Mục tiêu là bảo đảm trạng thái và quy tắc nghiệp vụ, trình bày và tiếp nhận tương tác có ranh giới rõ, đồng thời giữ cho các thành phần giao tiếp qua hợp đồng có chủ đích.

## 1. Vì sao cần kiểm tra cấu trúc mã?

Một ứng dụng nhỏ có thể bắt đầu với vài Controller, một số lớp Model và các template. Khi chức năng tăng lên, nhóm phát triển thường bổ sung dịch vụ, repository, DTO, bộ xử lý lỗi, tích hợp bên ngoài và các module dùng chung. Nếu không có quy tắc cấu trúc, các phụ thuộc có thể hình thành theo nhu cầu trước mắt:

- Controller tự gọi repository vì cách đó nhanh nhất để lấy dữ liệu.
- Domain object sử dụng annotation hoặc API của framework web để đọc session.
- View truy cập quan hệ ORM để tải dữ liệu trong lúc render.
- Một package dùng chung dần trở thành nơi chứa các tiện ích không liên quan.
- Hai package gọi lẫn nhau, khiến không thể thay đổi một phần mà không tác động phần còn lại.
- Các Controller khác nhau tự triển khai cùng một chính sách nghiệp vụ.

Những vấn đề này thường không làm ứng dụng hỏng ngay lập tức. Chúng làm chi phí thay đổi tăng lên: một yêu cầu nhỏ buộc phải sửa nhiều package, kiểm thử cần dựng nhiều thành phần hơn, hoặc một quy tắc bị triển khai khác nhau ở nhiều điểm vào.

Kiểm tra cấu trúc giúp trả lời:

1. Những thành phần nào đang phụ thuộc vào một lớp hoặc package?
2. Hướng phụ thuộc có phù hợp với các ranh giới đã chọn không?
3. Có chu trình phụ thuộc giữa các package hoặc module không?
4. Controller, Model, View và hạ tầng có đang làm đúng vai trò không?
5. Các quy tắc kiến trúc có được thực thi trong quá trình phát triển không?

## 2. Sơ đồ phụ thuộc biểu diễn điều gì?

Sơ đồ phụ thuộc (dependency diagram hoặc dependency graph) biểu diễn các thành phần và mối quan hệ sử dụng giữa chúng.

- **Nút (node):** có thể là lớp, package, module hoặc hệ thống bên ngoài.
- **Cạnh (edge):** thể hiện một thành phần phụ thuộc vào thành phần khác.
- **Hướng cạnh:** cho biết thành phần nào cần biết hoặc sử dụng thành phần nào.

Quy ước trong bài này: mũi tên đi từ bên phụ thuộc đến bên được sử dụng. Ví dụ `OrderController → OrderService` nghĩa là Controller cần OrderService để thực hiện chức năng.

~~~mermaid
flowchart TD
    C[OrderController] --> A[OrderApplicationService]
    A --> D[Order Domain Model]
    A --> P[OrderRepository Port]
    I[JpaOrderRepository] --> P
    I --> DB[(Database)]
    V[Order Detail View] --> VM[OrderViewData]
    C --> VM
~~~

Đây là sơ đồ khái quát của một cấu trúc có ranh giới tương đối rõ. Controller gọi application service; application service sử dụng domain model và hợp đồng repository; adapter lưu trữ triển khai hợp đồng đó. View nhận dữ liệu trình bày do tầng web chuẩn bị.

Sơ đồ phụ thuộc có thể được lập ở nhiều mức:

| Mức | Nút được biểu diễn | Câu hỏi thường gặp |
|---|---|---|
| Lớp | Class, interface, enum | Lớp nào đang phụ thuộc trực tiếp vào lớp nào? |
| Package | Nhóm lớp theo chức năng hoặc tầng | Package web có truy cập package persistence không? |
| Module | Maven/Gradle module hoặc JPMS module | Có thể biên dịch một module mà không kéo theo module không cần thiết không? |
| Hệ thống | Service, database, message broker, API bên ngoài | Ứng dụng phụ thuộc vào hệ thống nào khi chạy? |

Không nên gộp mọi loại quan hệ vào một sơ đồ mà không ghi rõ ý nghĩa. Một đường gọi phương thức lúc chạy, một import trong mã nguồn và một kết nối đến dịch vụ bên ngoài là các quan hệ khác nhau.

## 3. Phân biệt các loại phụ thuộc

Để đọc sơ đồ chính xác, cần hiểu sơ đồ đang mô tả loại phụ thuộc nào.

### 3.1. Phụ thuộc mã nguồn

Phụ thuộc mã nguồn xuất hiện khi một lớp sử dụng kiểu của lớp khác trong import, thuộc tính, tham số, kiểu trả về, generic, annotation, kế thừa hoặc lời gọi phương thức. Ví dụ:

~~~java
public class OrderController {
    private final OrderRepository repository;

    public OrderController(OrderRepository repository) {
        this.repository = repository;
    }
}
~~~

`OrderController` phụ thuộc vào kiểu `OrderRepository`. Nếu đây là repository lưu trữ cụ thể, Controller đang biết chi tiết persistence. Nếu đó là một hợp đồng phù hợp được cung cấp ở tầng ứng dụng, sự phụ thuộc có thể là một phần của thiết kế có chủ đích.

### 3.2. Phụ thuộc lúc chạy

Phụ thuộc lúc chạy (runtime dependency) xuất hiện khi một thành phần cần thành phần khác trong quá trình thực thi. Dependency injection có thể cung cấp implementation cho một interface, dù mã nguồn của bên gọi chỉ biết interface.

Ví dụ, `OrderApplicationService` phụ thuộc vào interface `OrderRepository`; lúc chạy, container cung cấp `JpaOrderRepository`. Sơ đồ mã nguồn và sơ đồ runtime vì vậy có thể khác nhau.

### 3.3. Phụ thuộc dữ liệu và giao tiếp

Một thành phần có thể phụ thuộc vào cấu trúc JSON, tên trường request, schema sự kiện hoặc định dạng dữ liệu được lưu. Những phụ thuộc này không phải lúc nào cũng hiện rõ qua import Java.

Ví dụ, Controller và View cùng dựa vào tên thuộc tính `orderStatusLabel` trong view model. Nếu một bên đổi tên mà template không được cập nhật, ứng dụng có thể lỗi lúc render dù sơ đồ class dependency không cho thấy toàn bộ vấn đề.

### 3.4. Phụ thuộc triển khai và cấu hình

Component scanning, tên bean, cấu hình route, reflection, serialization và template reference có thể tạo quan hệ mà công cụ phân tích bytecode không phát hiện đầy đủ. Do đó, một sơ đồ sinh tự động cần được hiểu theo phạm vi dữ liệu đầu vào của công cụ.

### 3.5. Phụ thuộc kiểm thử

Test có thể phụ thuộc vào package nội bộ để dựng fixture hoặc kiểm tra implementation. Nên phân biệt phụ thuộc của mã sản phẩm với phụ thuộc chỉ xuất hiện trong test. Một quy tắc kiến trúc có thể cần giới hạn phạm vi quét vào source set chính hoặc định nghĩa rõ các ngoại lệ cho test.

## 4. Hướng phụ thuộc phù hợp trong ứng dụng MVC

Một cấu trúc MVC thường có các nhóm thành phần như sau:

- **Web/Controller:** tiếp nhận request, binding, validation đầu vào và chọn phản hồi.
- **Application:** điều phối use case, transaction và các cộng tác viên.
- **Domain/Model:** bảo vệ trạng thái, hành vi và quy tắc nghiệp vụ.
- **Infrastructure:** triển khai truy cập dữ liệu, gửi thông điệp hoặc tích hợp dịch vụ bên ngoài.
- **View:** template hoặc component trình bày dữ liệu được cung cấp.

Một hướng phụ thuộc có thể dùng làm điểm khởi đầu:

~~~mermaid
flowchart TD
    W[Web / Controller] --> A[Application]
    A --> D[Domain / Model]
    A --> P[Ports / Interfaces]
    I[Infrastructure Adapters] --> P
    I --> D
    W --> VM[View Model]
    VM --> V[View]
~~~

Sơ đồ này thể hiện nguyên tắc tổng quát, không phải quy định bắt buộc cho mọi ứng dụng MVC. Tùy cách tổ chức, domain có thể không cần biết infrastructure; application service định nghĩa port và adapter hạ tầng triển khai port đó. Controller có thể gọi domain trực tiếp trong ứng dụng rất nhỏ, nhưng khi nghiệp vụ có nhiều bước hoặc cần giao dịch, application service thường giúp giữ ranh giới rõ hơn.

Một số nguyên tắc có thể chuyển thành quy tắc kiểm tra:

1. Domain không phụ thuộc vào HTTP, template engine hoặc chi tiết lưu trữ.
2. Controller không truy cập trực tiếp adapter persistence nếu kiến trúc yêu cầu đi qua application service.
3. View không gọi repository hoặc service nghiệp vụ để tự tải dữ liệu.
4. Application không phụ thuộc vào Controller hoặc View.
5. Infrastructure triển khai các port cần thiết và không trở thành nơi chứa quy tắc nghiệp vụ cốt lõi.
6. Các package nghiệp vụ không tạo chu trình phụ thuộc.

## 5. Nhận diện chu trình phụ thuộc

Chu trình (dependency cycle) xuất hiện khi A phụ thuộc B, B phụ thuộc C và C lại phụ thuộc A. Chu trình có thể xuất hiện giữa các lớp, package hoặc module.

Ví dụ:

~~~mermaid
flowchart LR
    A[order.controller] --> B[order.service]
    B --> C[customer.service]
    C --> A
~~~

Trong ví dụ này, `customer.service` cần gọi ngược vào `order.controller`. Điều đó thường cho thấy một trách nhiệm đang được đặt sai chỗ hoặc một hợp đồng dùng chung chưa được xác định rõ.

Chu trình làm nảy sinh các vấn đề:

- Khó xác định thứ tự khởi tạo và cấu hình dependency injection.
- Một thay đổi ở package này có thể buộc package kia thay đổi theo.
- Khó tách module thành thư viện hoặc dịch vụ độc lập.
- Kiểm thử đơn vị cần dựng nhiều thành phần liên quan.
- Ranh giới trách nhiệm trở nên mờ vì các package biết quá nhiều về nhau.

Không phải mọi chu trình đều lập tức gây lỗi biên dịch. Một số chu trình ở mức package vẫn biên dịch được nhưng làm kiến trúc khó bảo trì. Mục tiêu của quy tắc kiến trúc là phát hiện chúng trước khi chúng trở thành ràng buộc lớn.

### Cách xử lý chu trình

Khi phát hiện chu trình:

1. Xác định quan hệ nào thực sự cần thiết và quan hệ nào phát sinh do tiện lợi.
2. Tìm hành vi hoặc hợp đồng đang bị đặt sai package.
3. Chuyển hợp đồng về tầng có ý nghĩa sở hữu nó, thường là application hoặc domain tùy nội dung.
4. Dùng interface/port để đảo chiều phụ thuộc khi một tầng trong cần khả năng do tầng ngoài cung cấp.
5. Tách chức năng dùng chung thành thành phần có trách nhiệm rõ nếu nó thực sự độc lập.
6. Viết hoặc cập nhật quy tắc kiến trúc để chu trình không quay lại.

Không nên chỉ di chuyển lớp để làm sơ đồ hết vòng mà không xem xét ý nghĩa nghiệp vụ và quyền sở hữu hợp đồng.

## 6. Từ ý định thiết kế thành quy tắc kiến trúc

Một sơ đồ giúp con người quan sát, nhưng nó không tự ngăn một thay đổi sai được đưa vào mã nguồn. Quy tắc kiến trúc (architecture rule) mô tả điều gì được phép hoặc bị cấm và có thể được thực thi trong kiểm thử hoặc quá trình build.

Ví dụ:

| Ý định thiết kế | Quy tắc có thể kiểm tra |
|---|---|
| Domain độc lập với web | Package domain không phụ thuộc Servlet, Spring MVC hoặc template |
| Controller chỉ điều phối | Package controller không phụ thuộc trực tiếp persistence adapter |
| View chỉ trình bày | Package view/template không truy cập repository |
| Không có chu trình giữa các nhóm chức năng | Các slice package không có dependency cycle |
| Controller có quy ước đặt tên | Lớp trong package controller kết thúc bằng `Controller` |
| Module chỉ công khai API đã định | Module khác không import package nội bộ |

Một quy tắc tốt cần cụ thể, có thể kiểm tra và gắn với một quyết định kiến trúc thực sự. Không nên viết quy tắc chỉ vì có thể kiểm tra được; quy tắc quá cứng có thể ngăn một cách triển khai hợp lệ hoặc tạo nhiều ngoại lệ khó hiểu.

## 7. Kiểm tra quy tắc bằng ArchUnit

**ArchUnit** là thư viện Java cho phép viết test kiểm tra cấu trúc kiến trúc từ bytecode đã biên dịch. Nó có thể kiểm tra package, lớp, annotation, phụ thuộc, phân lớp và chu trình giữa các nhóm package.

ArchUnit không tự chứng minh ứng dụng đúng nghiệp vụ hoặc an toàn. Nó kiểm tra những quan hệ cấu trúc mà nhóm phát triển đã diễn đạt thành quy tắc.

### 7.1. Thêm ArchUnit vào dự án

Với dự án Maven, có thể khai báo dependency ở phạm vi test. Phiên bản cần được chọn theo chính sách dependency của dự án:

~~~xml
<dependency>
    <groupId>com.tngtech.archunit</groupId>
    <artifactId>archunit-junit5</artifactId>
    <version>${archunit.version}</version>
    <scope>test</scope>
</dependency>
~~~

Với Gradle, dependency tương ứng có thể được khai báo trong test scope:

~~~kotlin
dependencies {
    testImplementation("com.tngtech.archunit:archunit-junit5:$archunitVersion")
}
~~~

Không cần thêm ArchUnit vào runtime của ứng dụng chỉ để kiểm tra cấu trúc trong test.

### 7.2. Ngăn Domain phụ thuộc vào Web và Infrastructure

~~~java
@AnalyzeClasses(packages = "com.example.mvc")
class DomainArchitectureTest {

    @ArchTest
    static final ArchRule domain_must_not_depend_on_web_or_infrastructure =
            noClasses()
                    .that().resideInAPackage("..domain..")
                    .should().dependOnClassesThat()
                    .resideInAnyPackage(
                            "..web..",
                            "..infrastructure..",
                            "org.springframework.web..",
                            "jakarta.servlet.."
                    );
}
~~~

Quy tắc này phát hiện lớp trong package domain phụ thuộc vào package web, infrastructure hoặc một số API web của framework. Nếu dự án chủ ý dùng một annotation framework trong domain, nhóm cần quyết định đó có phù hợp với ranh giới mong muốn không; không nên thêm ngoại lệ chỉ để làm test xanh mà không hiểu tác động.

### 7.3. Kiểm tra hướng phụ thuộc giữa các tầng

~~~java
@AnalyzeClasses(packages = "com.example.mvc")
class LayerArchitectureTest {

    @ArchTest
    static final ArchRule layers_follow_the_dependency_direction =
            layeredArchitecture()
                    .consideringAllDependencies()
                    .layer("Controller").definedBy("..web.controller..")
                    .layer("Application").definedBy("..application..")
                    .layer("Domain").definedBy("..domain..")
                    .layer("Infrastructure").definedBy("..infrastructure..")

                    .whereLayer("Controller")
                    .mayOnlyAccessLayers("Application")
                    .whereLayer("Application")
                    .mayOnlyAccessLayers("Domain")
                    .whereLayer("Domain")
                    .mayNotAccessAnyLayer()
                    .whereLayer("Infrastructure")
                    .mayOnlyAccessLayers("Application", "Domain");
}
~~~

Ví dụ này mô tả một kiến trúc nghiêm ngặt: Controller gọi application; application gọi domain; infrastructure có thể phụ thuộc vào hợp đồng application và domain để triển khai adapter. Các package thực tế phải khớp với quy ước của dự án. Nếu Controller cần dùng DTO ở một package riêng hoặc application cần một abstraction khác, hãy điều chỉnh định nghĩa layer và quy tắc theo thiết kế đã thống nhất.

Các lớp không thuộc bất kỳ layer nào có thể cần được xem xét riêng. Không nên vô tình để một package quan trọng nằm ngoài tất cả quy tắc chỉ vì pattern package chưa bao phủ nó.

### 7.4. Phát hiện chu trình giữa các package chức năng

~~~java
@AnalyzeClasses(packages = "com.example.mvc")
class PackageCycleTest {

    @ArchTest
    static final ArchRule feature_packages_should_be_free_of_cycles =
            slices()
                    .matching("com.example.mvc.(*)..")
                    .should().beFreeOfCycles();
}
~~~

Trong ví dụ, mỗi package con đầu tiên dưới `com.example.mvc` được xem như một slice. ArchUnit kiểm tra các slice đó có phụ thuộc vòng hay không. Pattern cần được chọn phù hợp với cách chia package; nếu cấu trúc thực tế là `com.example.order`, `com.example.customer` thì biểu thức matching phải phản ánh đúng ranh giới feature.

### 7.5. Kiểm tra quy ước đặt tên Controller

~~~java
@AnalyzeClasses(packages = "com.example.mvc")
class NamingArchitectureTest {

    @ArchTest
    static final ArchRule controllers_should_have_controller_suffix =
            classes()
                    .that().resideInAPackage("..web.controller..")
                    .should().haveSimpleNameEndingWith("Controller");
}
~~~

Quy tắc đặt tên đơn giản giúp codebase nhất quán và dễ tìm kiếm. Chỉ nên dùng nếu nhóm thực sự chọn quy ước này; tên lớp không phải tiêu chí đủ để kết luận trách nhiệm được đặt đúng.

### 7.6. Đọc kết quả kiểm tra

Khi một quy tắc thất bại, báo cáo thường chỉ ra lớp vi phạm và đường phụ thuộc dẫn đến vi phạm. Hãy dùng thông tin đó để:

- Xác định import, kiểu thuộc tính, lời gọi hoặc annotation tạo phụ thuộc.
- Kiểm tra phụ thuộc đó có thực sự cần thiết không.
- Chuyển hợp đồng về package phù hợp hoặc dùng port/interface.
- Cập nhật sơ đồ nếu thiết kế đã thay đổi có chủ đích.
- Chỉ thêm ngoại lệ có giải thích khi có lý do kiến trúc rõ ràng.

Không nên bỏ qua toàn bộ quy tắc vì một test thất bại. Cũng không nên xóa quy tắc chỉ để build thành công mà không ghi nhận quyết định thay đổi kiến trúc.

## 8. Kiểm tra bằng module boundary của Java và build tool

Quy tắc package hữu ích, nhưng các package trong cùng một module thường vẫn có thể import lẫn nhau nếu không có kiểm tra. Khi hệ thống lớn hơn, có thể dùng ranh giới module để tăng mức bảo vệ.

### 8.1. Maven hoặc Gradle multi-module

Có thể chia ứng dụng thành các module như:

~~~text
mvc-app/
├── web/
├── application/
├── domain/
└── infrastructure/
~~~

Dependency giữa module được khai báo tường minh trong build file. Nếu module `domain` không khai báo dependency vào `web`, mã domain không thể sử dụng class của web qua compile classpath thông thường.

Tuy nhiên, cần thiết kế chiều dependency phù hợp. Một ví dụ:

~~~mermaid
flowchart TD
    W[web module] --> A[application module]
    A --> D[domain module]
    I[infrastructure module] --> A
    I --> D
~~~

Trong đó, application định nghĩa port cần thiết; infrastructure cung cấp implementation. Module boundary giúp ngăn một số phụ thuộc ở mức biên dịch, trong khi ArchUnit có thể kiểm tra các quy ước chi tiết bên trong module.

### 8.2. Java Platform Module System (JPMS)

JPMS cho phép module khai báo package được export và module được yêu cầu bằng `module-info.java`. Package không export không phải API công khai cho module khác theo cơ chế truy cập module thông thường.

JPMS hữu ích khi dự án muốn kiểm soát API công khai ở mức module. Nó không thay thế hoàn toàn quy tắc kiến trúc nội bộ, và cần xem xét cách framework, reflection và dependency hiện có tương tác với module system.

### 8.3. So sánh các cơ chế

| Cơ chế | Kiểm tra tốt ở mức | Điểm cần lưu ý |
|---|---|---|
| Review sơ đồ phụ thuộc | Lớp, package, module, hệ thống | Cần cập nhật và review cùng thay đổi mã |
| ArchUnit | Lớp, package, annotation, layer, cycle | Kiểm tra bytecode; không bao quát mọi cấu hình runtime hoặc template |
| Maven/Gradle module | Module và compile dependency | Cần chia module hợp lý, tránh module quá nhỏ |
| JPMS | Module và API package được export | Cần cấu hình module path và tương thích framework |
| Integration test | Hành vi tích hợp khi chạy | Không thay thế quy tắc cấu trúc tĩnh |

Các cơ chế này bổ sung cho nhau. Một dự án có thể bắt đầu với package và ArchUnit, sau đó tách module khi ranh giới đã ổn định.

## 9. Kết hợp sơ đồ sinh tự động và sơ đồ kiến trúc chủ đích

Sơ đồ sinh từ mã nguồn hữu ích vì phản ánh phụ thuộc hiện có. Tuy nhiên, nó có thể chứa rất nhiều chi tiết như getter, thư viện, annotation và kiểu dữ liệu kỹ thuật. Sơ đồ kiến trúc chủ đích thường giản lược để làm rõ ranh giới mà nhóm muốn giữ.

Nên phân biệt:

- **As-built diagram:** cấu trúc đang tồn tại trong mã nguồn hoặc hệ thống.
- **Target diagram:** cấu trúc mong muốn sau khi thiết kế hoặc refactor.
- **Rule set:** những điều kiện có thể kiểm tra để hạn chế khoảng cách giữa hai sơ đồ.

Ví dụ, sơ đồ target quy định `Controller → Application → Domain`, còn sơ đồ as-built cho thấy `Controller → JpaRepository`. Khoảng cách đó là phát hiện cần được đánh giá. Nhóm có thể chuyển truy cập dữ liệu vào application service hoặc quyết định rõ vì sao một use case đơn giản được phép đi theo đường khác.

Sơ đồ nên có tên, phạm vi, quy ước mũi tên và ngày hoặc phiên bản tương ứng. Nếu sơ đồ được sinh tự động, nên ghi công cụ và phạm vi phân tích để người đọc không nhầm nó là toàn bộ kiến trúc runtime.

## 10. Quy trình kiểm tra cấu trúc trong một lần thay đổi

Có thể tích hợp việc kiểm tra vào quy trình phát triển như sau:

1. **Xác định phạm vi:** chọn module, feature hoặc tầng cần xem xét.
2. **Thu thập phụ thuộc:** dùng IDE, công cụ phân tích bytecode hoặc báo cáo build để tìm các quan hệ quan trọng.
3. **Vẽ sơ đồ:** thể hiện các package/module chính và hướng phụ thuộc; bỏ chi tiết không phục vụ câu hỏi đang kiểm tra.
4. **Đối chiếu mục tiêu:** so sánh cấu trúc hiện tại với quy tắc MVC và các quyết định kiến trúc của dự án.
5. **Tìm chu trình và phụ thuộc sai chiều:** xem các cạnh bất thường, package dùng chung quá rộng và phụ thuộc trực tiếp vào framework.
6. **Viết quy tắc tự động:** chuyển các nguyên tắc ổn định thành ArchUnit test hoặc module boundary.
7. **Sửa theo từng nhóm:** chuyển trách nhiệm hoặc hợp đồng, giữ hành vi bên ngoài ổn định.
8. **Chạy kiểm tra:** chạy test kiến trúc cùng các test phù hợp của chức năng.
9. **Cập nhật tài liệu:** điều chỉnh sơ đồ as-built/target và giải thích ngoại lệ có chủ đích.

Trong code review, không cần yêu cầu sơ đồ mới cho mọi thay đổi nhỏ. Hãy dùng sơ đồ khi thay đổi tác động đến ranh giới package, module, hướng phụ thuộc hoặc cách tích hợp giữa các tầng.

## 11. Ví dụ chẩn đoán cấu trúc MVC

Giả sử sơ đồ hiện tại cho thấy:

~~~mermaid
flowchart LR
    C[OrderController] --> R[JpaOrderRepository]
    C --> V[OrderTemplate]
    V --> R
    D[Order Domain] --> H[HttpSession]
    R --> D
~~~

Có ba dấu hiệu cần điều tra:

1. Controller truy cập trực tiếp repository, có thể đang bỏ qua application service.
2. View truy cập repository, nghĩa là lúc render có thể tự truy vấn dữ liệu.
3. Domain phụ thuộc vào HTTP session, làm quy tắc nghiệp vụ gắn với chi tiết web.

Một hướng cấu trúc có thể là:

~~~mermaid
flowchart TD
    C[OrderController] --> A[OrderApplicationService]
    A --> D[Order Domain]
    A --> P[OrderRepository Port]
    I[JpaOrderRepository] --> P
    I --> DB[(Database)]
    C --> VM[OrderViewData]
    VM --> V[OrderTemplate]
~~~

Sau khi thay đổi:

- Controller gọi use case và chuẩn bị dữ liệu trình bày.
- View chỉ đọc dữ liệu đã được cung cấp.
- Domain nhận thông tin người dùng hoặc ngữ cảnh nghiệp vụ qua tham số có ý nghĩa, không đọc session.
- Repository port được định nghĩa ở tầng phù hợp; adapter JPA triển khai port.

Các quy tắc ArchUnit có thể kiểm tra rằng domain không phụ thuộc web, Controller không phụ thuộc persistence adapter và View không phụ thuộc repository. Nếu template không được ArchUnit phân tích, cần kiểm tra template bằng convention, test hoặc công cụ phù hợp với công nghệ View.

## 12. Những giới hạn cần hiểu khi kiểm tra tự động

Kiểm tra cấu trúc tự động có giá trị nhưng không thể thay thế đánh giá thiết kế.

- **Không hiểu hết ý nghĩa nghiệp vụ:** ArchUnit có thể thấy Controller phụ thuộc một service, nhưng không biết service có đang chứa đúng quy tắc hay không.
- **Không bao quát mọi quan hệ runtime:** reflection, component scanning, cấu hình DI, serialization và gọi dịch vụ qua mạng có thể không hiện đầy đủ trong đồ thị bytecode.
- **Template không phải lúc nào cũng nằm trong phạm vi:** JSP, Thymeleaf, Freemarker hoặc JavaScript có thể tham chiếu dữ liệu và endpoint mà phân tích Java không nhìn thấy.
- **Quy tắc quá chặt gây ma sát:** nếu một ngoại lệ hợp lệ xuất hiện thường xuyên, có thể ranh giới hoặc cách diễn đạt rule cần được xem lại.
- **Sơ đồ có thể lỗi thời:** sơ đồ thủ công không cập nhật theo mã nguồn sẽ mất giá trị. Cần gắn nó với thay đổi hoặc tạo từ nguồn dữ liệu đáng tin cậy.
- **Không chứng minh tính đúng đắn khi chạy:** một đồ thị không có chu trình vẫn có thể chứa logic sai, lỗi transaction hoặc lỗ hổng bảo mật.

Vì vậy, hãy kết hợp kiểm tra tĩnh, kiểm thử tích hợp, review mã và sơ đồ kiến trúc có phạm vi rõ.

## 13. Checklist review cấu trúc MVC

- [ ] Sơ đồ ghi rõ phạm vi và quy ước hướng mũi tên.
- [ ] Các package và module chính có trách nhiệm dễ hiểu.
- [ ] Controller không phụ thuộc trực tiếp vào chi tiết persistence ngoài chủ đích.
- [ ] Domain không phụ thuộc HTTP, View hoặc framework web.
- [ ] View không tự truy cập repository hoặc thực thi quy tắc nghiệp vụ.
- [ ] Application service điều phối use case qua hợp đồng rõ ràng.
- [ ] Infrastructure triển khai port mà tầng trong định nghĩa.
- [ ] Không có chu trình phụ thuộc không được giải thích giữa package hoặc module.
- [ ] Quy tắc kiến trúc quan trọng được kiểm tra tự động.
- [ ] Test kiến trúc chạy trong CI cùng các kiểm tra phù hợp.
- [ ] Ngoại lệ có lý do và phạm vi rõ, không vô hiệu hóa rule quá rộng.
- [ ] Sơ đồ as-built và target được cập nhật khi ranh giới thay đổi.

## Kết luận

Sơ đồ phụ thuộc giúp nhìn thấy hướng liên kết giữa lớp, package, module và hệ thống; quy tắc kiến trúc biến các quyết định thiết kế thành điều kiện có thể kiểm tra lặp lại. Với ứng dụng MVC, hãy dùng chúng để xác nhận Controller điều phối qua hợp đồng phù hợp, Model giữ quy tắc nghiệp vụ, View tập trung trình bày và infrastructure nằm ở ranh giới tích hợp. Phát hiện chu trình hoặc phụ thuộc sai chiều sớm giúp giảm thay đổi lan truyền và giữ cấu trúc dễ kiểm thử. ArchUnit, module boundary và kiểm thử tích hợp có thể phối hợp để duy trì cấu trúc, trong khi sơ đồ và code review vẫn cần được dùng để đánh giá ý nghĩa của các quan hệ.
