# Biểu diễn module graph và quan hệ phụ thuộc

Một modular monolith có thể chứa nhiều application module trong cùng một tiến trình, nhưng mỗi module vẫn cần ranh giới và hợp đồng rõ ràng. Khi số lượng module tăng, việc đọc package tree hoặc lần theo từng import không còn đủ để hiểu toàn bộ cấu trúc. Spring Modulith cung cấp `ApplicationModules` để tạo mô hình module từ code và `Documenter` để biểu diễn mô hình đó thành sơ đồ cùng tài liệu có thể đưa vào tài liệu phát triển.

Module graph cho biết module nào phụ thuộc module nào và quan hệ thuộc loại nào. Nó là góc nhìn kiến trúc tĩnh được suy ra từ package, kiểu Java và metadata. Graph không phải call graph của runtime, không thể hiện thứ tự các phương thức được gọi trong một request và cũng không chứng minh một nhánh nghiệp vụ đã chạy.

## 1. Tạo module model làm nguồn dữ liệu cho graph

Spring Modulith thường phát hiện application module từ các package con trực tiếp của package chứa lớp Spring Boot application. Annotation như `@ApplicationModule`, `@NamedInterface`, named interface và `allowedDependencies` bổ sung thông tin về ranh giới cũng như hợp đồng giữa các module.

Ví dụ một ứng dụng bán hàng:

```text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderManagement.java
│   └── events
├── catalog
│   └── ProductManagement.java
├── customers
│   └── CustomerManagement.java
└── inventory
    └── InventoryManagement.java
```

Tạo mô hình bằng `ApplicationModules.of(...)`:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
```

Nếu muốn chỉ tạo tài liệu cho một cấu trúc đã vượt qua các quy tắc kiến trúc, có thể xác minh ngay khi tạo mô hình:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class)
        .verify();
```

`ApplicationModules` là tập hợp các `ApplicationModule` đã được Spring Modulith nhận diện. Mô hình này là đầu vào chung cho việc xem module, truy vấn dependency và tạo tài liệu. Nếu package chưa được nhận diện đúng, sơ đồ tạo ra cũng sẽ thiếu hoặc thể hiện sai module; vì vậy cần kiểm tra cấu trúc và metadata trước khi dùng graph làm tài liệu kiến trúc.

## 2. Đọc hướng mũi tên trong module graph

Trong dependency graph, mũi tên đi từ module nguồn tới module đích mà module nguồn phụ thuộc. Ví dụ:

```text
orders ─────> catalog
orders ─────> customers
inventory ──> orders
```

Ý nghĩa:

- `orders` tham chiếu API hoặc type được công khai bởi `catalog`.
- `orders` phụ thuộc hợp đồng được công khai bởi `customers`.
- `inventory` tham chiếu một hợp đồng thuộc `orders`; nếu hợp đồng đó là event, quan hệ có thể là listener dependency.

Đừng diễn giải mũi tên thành thứ tự gọi hàm. Ví dụ, nếu `inventory` lắng nghe event `OrderPlaced` được công khai bởi `orders`, hướng phụ thuộc tĩnh là `inventory -> orders`, vì listener phải biết kiểu event. Hướng truyền event khi chạy là `orders -> inventory listener`, vì `orders` phát và `inventory` nhận.

## 3. Các loại quan hệ được biểu diễn

Spring Modulith phân loại dependency giữa module thành các `DependencyType`:

| Dependency type | Ý nghĩa trên graph |
|---|---|
| `USES_COMPONENT` | Module nguồn sử dụng component của module đích; module đích cần được bootstrap để module nguồn chạy được |
| `EVENT_LISTENER` | Module nguồn khai báo listener cho event được module đích công khai; module đích không cần bootstrap chỉ để chạy module nguồn |
| `ENTITY` | Module nguồn tham chiếu entity thuộc module đích |
| `DEFAULT` | Quan hệ phụ thuộc chưa được phân loại thành một loại chuyên biệt hơn |

Một cặp module có thể có nhiều quan hệ. Chẳng hạn `inventory` vừa sử dụng component của `orders`, vừa lắng nghe event do `orders` công khai. Khi nhìn graph, hãy đọc nhãn quan hệ thay vì gộp tất cả thành một mũi tên không phân biệt.

Có thể truy vấn dependency record trực tiếp từ module model:

```java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

ApplicationModule orders = modules.getModuleByName("orders")
        .orElseThrow();

orders.getDirectDependencies(modules).stream()
        .forEach(dependency -> System.out.printf(
                "%s -> %s | %s | %s -> %s%n",
                orders.getDisplayName(),
                dependency.getTargetModule().getDisplayName(),
                dependency.getDependencyType(),
                dependency.getSourceType().getName(),
                dependency.getTargetType().getName()));
```

Module nguồn trong ví dụ là `orders`, vì ta đang truy vấn `orders.getDirectDependencies(...)`. `getSourceType()` cho biết kiểu Java nguồn tạo ra quan hệ, `getTargetType()` cho biết kiểu được tham chiếu và `getTargetModule()` xác định module chứa kiểu đích. Các thông tin này giúp truy ngược một cạnh trong graph về source code cụ thể.

`getDirectDependencies()` chỉ trả về quan hệ trực tiếp. `getAllDependencies()` bao gồm cả quan hệ bắc cầu. Khi muốn giải thích một cạnh được vẽ giữa hai module, hãy bắt đầu với dependency trực tiếp để không gán nhầm quan hệ của module trung gian cho module nguồn.

## 4. Sinh component diagram bằng Documenter

Spring Modulith cung cấp `Documenter` trong artifact `spring-modulith-docs`. Artifact này thường được thêm ở test scope vì việc sinh sơ đồ và tài liệu là một phần của quy trình kiểm tra hoặc build.

Gradle:

```groovy
dependencies {
    testImplementation 'org.springframework.modulith:spring-modulith-docs'
}
```

Maven:

```xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-docs</artifactId>
    <scope>test</scope>
</dependency>
```

Nếu dự án đã import Spring Modulith BOM, không cần khai báo version riêng cho artifact này.

Tạo component diagram cho toàn bộ ứng dụng và diagram riêng cho từng module:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocumentationTests {

    @Test
    void writeModuleDiagrams() {
        ApplicationModules modules = ApplicationModules
                .of(ShopApplication.class)
                .verify();

        new Documenter(modules)
                .writeModulesAsPlantUml()
                .writeIndividualModulesAsPlantUml();
    }
}
```

`writeModulesAsPlantUml()` tạo sơ đồ tổng quan chứa các module và quan hệ giữa chúng. `writeIndividualModulesAsPlantUml()` tạo thêm sơ đồ theo từng module, tập trung vào module đó và những module mà nó phụ thuộc. Sơ đồ được ghi dưới dạng PlantUML để có thể đưa vào Asciidoctor hoặc render thành hình ảnh bằng công cụ PlantUML.

Muốn tạo toàn bộ sơ đồ và module canvas trong một lời gọi, dùng:

```java
new Documenter(modules)
        .writeDocumentation();
```

`writeDocumentation()` tạo overview component diagram, component diagram cho từng module, Application Module Canvas và tài liệu tổng hợp `all-docs.adoc`. Nếu trước đó chỉ gọi riêng các phương thức sinh diagram hoặc canvas, có thể tạo file tổng hợp sau bằng:

```java
new Documenter(modules)
        .writeAggregatingDocument();
```

File tổng hợp liên kết tới các component diagram và canvas đã được tạo. Nếu chưa có các tài liệu đó, lời gọi này không tạo ra nội dung tổng hợp.

## 5. Chọn C4 hoặc UML và điều chỉnh phạm vi graph

`Documenter.DiagramOptions` điều chỉnh cách biểu diễn module graph. Spring Modulith hỗ trợ hai kiểu chính:

| Kiểu | Khi phù hợp |
|---|---|
| `DiagramStyle.C4` | Sơ đồ component theo cách trình bày C4, phù hợp để trao đổi ranh giới module ở mức kiến trúc |
| `DiagramStyle.UML` | UML component diagram truyền thống, phù hợp khi nhóm quen đọc ký hiệu UML |

Nên chọn kiểu tường minh để kết quả tài liệu ổn định giữa các phiên bản hoặc môi trường build:

```java
import org.springframework.modulith.docs.Documenter.DiagramOptions;
import org.springframework.modulith.docs.Documenter.DiagramOptions.DiagramStyle;

DiagramOptions diagramOptions = DiagramOptions.defaults()
        .withStyle(DiagramStyle.C4);

new Documenter(modules)
        .writeModulesAsPlantUml(diagramOptions)
        .writeIndividualModulesAsPlantUml(diagramOptions);
```

Ngoài kiểu sơ đồ, có thể điều chỉnh những quan hệ được vẽ:

```java
import org.springframework.modulith.core.DependencyDepth;
import org.springframework.modulith.core.DependencyType;

DiagramOptions diagramOptions = DiagramOptions.defaults()
        .withStyle(DiagramStyle.UML)
        .withDependencyDepth(DependencyDepth.ALL)
        .withDependencyTypes(
                DependencyType.USES_COMPONENT,
                DependencyType.EVENT_LISTENER,
                DependencyType.ENTITY);
```

Các tùy chọn quan trọng:

- `withDependencyTypes(...)` chọn loại quan hệ được đưa vào sơ đồ. Có thể bỏ một loại nếu sơ đồ đang tập trung vào một câu hỏi kiến trúc cụ thể.
- `withDependencyDepth(...)` điều chỉnh phạm vi module liên quan trong sơ đồ module riêng. `IMMEDIATE` chỉ đưa các phụ thuộc trực tiếp; `ALL` mở rộng tới các phụ thuộc bắc cầu; `NONE` không mở rộng dependency.
- `withExclusions(...)` loại module khỏi sơ đồ theo predicate.
- `withElementsWithoutRelationships(...)` quyết định có giữ module không có quan hệ với module khác trong sơ đồ hay không.
- `withTargetFileName(...)` đặt tên file đầu ra. Khi sinh diagram riêng cho nhiều module, tên file cần có placeholder `%s` để thay bằng tên module.

Không nên lọc dependency type chỉ để sơ đồ gọn hơn nếu người đọc cần nhìn toàn bộ quan hệ. Hãy ghi rõ phạm vi lọc trong tên hoặc chú thích của tài liệu, để người xem không hiểu nhầm graph rút gọn là toàn bộ dependency model.

## 6. Đọc Application Module Canvas

Component diagram cho biết module và quan hệ giữa chúng. Application Module Canvas bổ sung một bảng thông tin về từng module. Dùng `writeModuleCanvases()` để sinh canvas cho tất cả module:

```java
new Documenter(modules)
        .writeModuleCanvases();
```

Canvas có thể bao gồm:

| Phần | Thông tin |
|---|---|
| Base package | Package gốc của application module |
| Spring components | Bean được expose, nhóm theo stereotype như service, repository hoặc component |
| Aggregate roots | Entity có repository hoặc được đánh dấu aggregate bằng jMolecules |
| Published events | Event do module phát, nếu event được nhận diện bằng metadata jMolecules tương ứng |
| Events listened to | Event mà listener của module đăng ký xử lý |
| Configuration properties | Các property được phát hiện từ metadata cấu hình Spring Boot |

Việc phát hiện một số mục phụ thuộc metadata bổ sung:

- Event được module phát cần được đánh dấu bằng jMolecules `@DomainEvent` hoặc implement interface `DomainEvent` để được nhận diện trong phần published events.
- Listener được suy ra từ phương thức dùng `@EventListener`, `@TransactionalEventListener`, jMolecules `@DomainEventHandler` hoặc bean implement `ApplicationListener`.
- Configuration properties cần artifact `spring-boot-configuration-processor` để trích xuất metadata.

Canvas mặc định tập trung vào các thành phần được expose. Để hiển thị cả thành phần nội bộ, có thể dùng `CanvasOptions.revealInternals()`:

```java
import org.springframework.modulith.docs.Documenter.CanvasOptions;

CanvasOptions canvasOptions = CanvasOptions.defaults()
        .revealInternals();

new Documenter(modules)
        .writeModuleCanvases(canvasOptions);
```

Chỉ bật `revealInternals()` khi tài liệu cần phục vụ phân tích nội bộ. Với tài liệu hợp đồng module dành cho nhóm tiêu thụ module, nên giữ canvas mặc định để tránh làm lộ chi tiết triển khai không thuộc API công khai.

`CanvasOptions.withApiBase(...)` có thể đặt base URL của Javadoc để các type trong canvas được tạo liên kết tới API documentation. `groupingBy(...)` cho phép định nghĩa nhóm bean tùy chỉnh; `withoutDefaultGroupings()` tạo options không đăng ký các nhóm mặc định của Spring và jMolecules.

## 7. Quản lý thư mục tài liệu sinh ra

Theo mặc định, `Documenter` ghi tài liệu vào thư mục `spring-modulith-docs` trong build directory của build tool:

| Build tool | Thư mục thường dùng |
|---|---|
| Gradle | `build/spring-modulith-docs` |
| Maven | `target/spring-modulith-docs` |

Có thể đổi thư mục bằng `Documenter.Options`:

```java
import org.springframework.modulith.docs.Documenter;

var documenterOptions = Documenter.Options.defaults()
        .withOutputFolder("build/generated-modulith-docs");

new Documenter(modules, documenterOptions)
        .writeDocumentation()
        .writeAggregatingDocument();
```

Lưu ý: `withOutputFolder(...)` tạo thư mục nếu chưa tồn tại và mặc định xóa nội dung thư mục đích trước khi ghi tài liệu mới. Hãy chọn một thư mục riêng dành cho generated artifacts, không trỏ vào thư mục chứa tài liệu viết tay hoặc file cần giữ lại. Nếu muốn giữ nội dung cũ trong output folder, `Documenter.Options.withoutClean()` tắt bước dọn thư mục trước khi ghi.

Nên sinh tài liệu trong test hoặc một task build riêng. Không cần commit mọi file trung gian nếu nhóm đã có quy trình tái tạo tài liệu trong CI; điều quan trọng là output có thể được sinh lặp lại từ cùng một module model và phiên bản code.

## 8. Dùng graph để rà soát kiến trúc

Khi review một module graph, hãy đặt các câu hỏi cụ thể thay vì chỉ nhìn số lượng mũi tên:

1. **Module nào có nhiều phụ thuộc trực tiếp?** Kiểm tra module đó có đang ôm quá nhiều trách nhiệm hoặc cần tách hợp đồng không.
2. **Có module nào phụ thuộc ngược vào module điều phối?** Xem quan hệ có thể chuyển sang event contract hoặc abstraction do bên tiêu thụ sở hữu không.
3. **Có nhiều `EVENT_LISTENER` không?** Đảm bảo event contract được công khai và hướng dependency không bị nhầm với luồng event runtime.
4. **Có module cô lập không có quan hệ?** Xác nhận module đó thực sự độc lập hoặc có thể bị bỏ sót khỏi phạm vi phát hiện.
5. **Có quan hệ `ENTITY` giữa các module?** Đánh giá mức độ chia sẻ mô hình dữ liệu và quyền sở hữu entity.
6. **Graph overview quá dày?** Dùng diagram riêng theo module hoặc lọc loại quan hệ với chú thích phạm vi rõ ràng.

Ví dụ graph tổng quan:

```text
             ┌───────────┐
             │ customers │
             └─────▲─────┘
                   │ depends on
┌────────┐   ┌─────┴─────┐       ┌───────────┐
│catalog │◄──│  orders   │       │ inventory │
└────────┘   └───────────┘       └─────┬─────┘
                                      │ listens to
                                      └────────> orders
```

Sơ đồ trên chỉ minh họa cách đọc quan hệ; module graph thật phải được sinh từ code và metadata của ứng dụng. Khi phát hiện một cạnh bất thường, truy vấn dependency record để xem `sourceType`, `targetType` và `DependencyType`, rồi mở source code để tìm nguyên nhân.

## 9. Kết hợp graph, canvas và verification

Một quy trình tài liệu hóa hiệu quả có thể gom xác minh và sinh tài liệu trong cùng architecture test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;
import org.springframework.modulith.docs.Documenter.CanvasOptions;
import org.springframework.modulith.docs.Documenter.DiagramOptions;
import org.springframework.modulith.docs.Documenter.DiagramOptions.DiagramStyle;

class ModuleDocumentationTests {

    @Test
    void verifiesAndDocumentsModuleStructure() {
        var modules = ApplicationModules.of(ShopApplication.class).verify();

        var diagrams = DiagramOptions.defaults()
                .withStyle(DiagramStyle.C4);

        var canvases = CanvasOptions.defaults();

        new Documenter(modules)
                .writeDocumentation(diagrams, canvases);
    }
}
```

Thứ tự này có ý nghĩa: `verify()` xác nhận cấu trúc module trước; chỉ khi verification thành công, `Documenter` mới sinh sơ đồ và canvas từ mô hình đó. Nếu dependency graph chứa một quan hệ ngoài ý muốn, sửa code hoặc metadata rồi chạy lại kiểm tra và sinh tài liệu.

Tài liệu được sinh không thay thế mô tả kiến trúc có chủ đích. Hãy bổ sung phần giải thích cho các quyết định quan trọng như lý do module phụ thuộc, trách nhiệm của event listener, hợp đồng named interface và những giới hạn được chấp nhận. Sơ đồ cho biết cấu trúc; tài liệu của nhóm giải thích lý do cấu trúc đó tồn tại.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Module graph là runtime call graph | Graph biểu diễn quan hệ phụ thuộc tĩnh suy ra từ code và metadata |
| Mũi tên luôn chỉ nơi nhận event | Mũi tên dependency đi từ module listener tới module công khai event contract; runtime event đi theo chiều publisher tới listener |
| Mỗi cặp module chỉ có một quan hệ | Một cặp có thể có nhiều dependency record với loại khác nhau |
| Sơ đồ tổng quan và sơ đồ module riêng có cùng phạm vi | Sơ đồ riêng có thể chỉ bao gồm module đang xét và các dependency theo `DependencyDepth` |
| Canvas mặc định hiển thị mọi internal type | Canvas mặc định ẩn internal; `revealInternals()` mới đưa chúng vào |
| Sinh PlantUML đồng nghĩa đã render PNG/SVG | `Documenter` sinh source PlantUML và Asciidoctor snippets; việc render hình ảnh là bước riêng của công cụ tài liệu |
| Output folder là nơi lưu tài liệu viết tay | `Documenter.Options.withOutputFolder()` mặc định dọn thư mục đích trước khi ghi; dùng thư mục generated riêng |
| Graph đẹp nghĩa là kiến trúc hợp lệ | Cần `ApplicationModules.verify()` để kiểm tra quy tắc, sau đó mới dùng graph làm tài liệu |

## 11. Checklist tạo module graph và tài liệu

- [ ] Đã tạo `ApplicationModules` từ đúng lớp Spring Boot application.
- [ ] Đã xác nhận module được phát hiện đúng theo package và metadata.
- [ ] Đã chạy `verify()` trước khi sinh tài liệu kiến trúc.
- [ ] Đã thêm `spring-modulith-docs` ở test scope.
- [ ] Đã chọn rõ C4 hoặc UML cho component diagram.
- [ ] Đã chọn dependency type và dependency depth phù hợp với mục tiêu sơ đồ.
- [ ] Đã phân biệt dependency direction với runtime event flow.
- [ ] Đã sinh module overview, individual diagrams và module canvases khi cần.
- [ ] Đã quyết định có cần `revealInternals()` hay chỉ công khai API trong canvas.
- [ ] Đã cấu hình output folder riêng cho generated artifacts.
- [ ] Đã đọc graph và giải thích các quan hệ bất thường trong tài liệu kiến trúc.

`ApplicationModules` cung cấp một mô hình module có thể truy vấn và xác minh; `Documenter` biến mô hình đó thành component diagram và module canvas. Khi đọc đúng hướng phụ thuộc, phân biệt các loại quan hệ và quản lý output rõ ràng, nhóm có thể duy trì tài liệu kiến trúc gần với code và phát hiện sớm những thay đổi làm lệch ranh giới module.

## Tài liệu tham khảo

- [Spring Modulith – Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html)
- [Documenter API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/docs/Documenter.html)
- [Documenter.DiagramOptions API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/docs/Documenter.DiagramOptions.html)
- [Documenter.CanvasOptions API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/docs/Documenter.CanvasOptions.html)
- [Documenter.Options API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/docs/Documenter.Options.html)
- [DependencyType API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/DependencyType.html)
- [DependencyDepth API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/DependencyDepth.html)
